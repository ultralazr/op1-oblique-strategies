#!/usr/bin/env python3
"""Patch OP-1 firmware R246 with the Oblique Strategies overlay.

    python3 patch_oblique.py op1_246.op1 [-o op1_246-oblique.op1] [--payload build/obl.bin --sym build/obl.sym]

Steps: verify the input (stock R246 or an op1r-patched R246), unpack (CRC32 + LZMA + tar), insert one LDR
block with our code at 0x01E40000 just before the FINAL block, redirect two CALLs into it, repack
(original tar order, op1repacker LZMA settings) and re-verify the result by unpacking it again.
te-boot.ldr is never modified.
"""
import argparse, binascii, copy, hashlib, io, lzma, os, struct, sys, tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK_SHA256 = 'c5315218f825f143b415ca554516541898abee843d3a236df0b54c04e1fb13a9'
STOCK_LDR_SHA256 = 'f79d299f6f9019c998013a4176223a6a1bc999a2d8c54451346861f6ea455c74'
LOAD_ADDR = 0x01E40000
LZMA_FILTERS = [{'id': lzma.FILTER_LZMA1, 'preset': 9, 'lc': 3, 'lp': 1, 'pb': 2, 'dict_size': 2 ** 23}]
FILL, IGNORE, FIRST, FINAL = 0x0100, 0x1000, 0x4000, 0x8000

# (call site, stock target, our entry symbol, our 'next' pointer symbol)
HOOKS = [
    (0x019C2D3E, 0x019B6C74, '_obl_key', '_obl_next_key'),       # input loop -> key handler(key, state)
    (0x01A3BC0E, 0x019D7ED0, '_obl_frame', '_obl_next_frame'),   # end of GUI frame, after all screens drew
]


def die(msg):
    sys.exit('ERROR: ' + msg)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def blocks(d):
    off = 0
    while off + 16 <= len(d):
        code, addr, count, arg = struct.unpack_from('<IIII', d, off)
        if code >> 24 != 0xAD:
            die(f'bad LDR block signature at {off:#x}')
        flags = code & 0xffff
        payload = 0 if flags & FILL else count
        yield dict(off=off, flags=flags, addr=addr, count=count, arg=arg, data=off + 16, payload=payload)
        off += 16 + payload


def header(flags, addr, count, arg):
    h = bytearray(struct.pack('<IIII', 0xAD000000 | flags, addr, count, arg))
    x = 0
    for b in h:
        x ^= b
    h[2] = x                                   # XOR of all 16 header bytes must be 0
    return bytes(h)


def fix_header_xor(d, off):
    h = bytearray(d[off:off + 16]); h[2] = 0
    x = 0
    for b in h:
        x ^= b
    d[off + 2] = x


def addr2off(d, addr):
    for b in blocks(d):
        if b['payload'] and not b['flags'] & (FILL | IGNORE | FIRST) and b['addr'] <= addr < b['addr'] + b['payload']:
            return b['data'] + addr - b['addr']
    die(f'address {addr:#x} not found in LDR')


def call_insn(pc, target):
    rel = target - pc
    if rel & 1 or not -(1 << 24) <= rel < (1 << 24):
        die(f'CALL {pc:#x} -> {target:#x} out of range')
    imm = (rel >> 1) & 0xffffff
    return struct.pack('<HH', 0xE300 | (imm >> 16), imm & 0xffff)


def call_target(pc, insn):
    h0, h1 = struct.unpack('<HH', insn)
    if h0 >> 8 != 0xE3:
        return None
    imm = ((h0 & 0xff) << 16) | h1
    if imm & 0x800000:
        imm -= 1 << 24
    return pc + 2 * imm


def patch_ldr(ldr, payload, syms, allow_modded):
    d = bytearray(ldr)
    payload = bytearray(payload)
    bl = list(blocks(d))
    if any(b['addr'] <= LOAD_ADDR + len(payload) and LOAD_ADDR < b['addr'] + b['count']
           for b in bl if not b['flags'] & (IGNORE | FIRST)):
        die('load range 0x%x.. overlaps an existing block (already patched?)' % LOAD_ADDR)
    for site, orig, sym, nxt in HOOKS:
        o = addr2off(d, site)
        cur = call_target(site, bytes(d[o:o + 4]))
        if cur is None or (cur != orig and not allow_modded):
            die(f'unexpected instruction at {site:#x}: {d[o:o + 4].hex()} (not stock / conflicting mod?)')
        if cur != orig:
            print(f'  note: {site:#x} already hooked by another mod ({cur:#x}); chaining to it')
        struct.pack_into('<I', payload, syms[nxt] - LOAD_ADDR, cur)
        d[o:o + 4] = call_insn(site, syms[sym])
    final = [b for b in bl if b['flags'] & FINAL]
    if len(final) != 1:
        die('expected exactly one FINAL block')
    pad = payload + b'\0' * (-len(payload) % 4)
    blk = header(0x0006, LOAD_ADDR, len(pad), 0) + pad
    d[final[0]['off']:final[0]['off']] = blk
    first = bl[0]
    if not first['flags'] & FIRST:
        die('first block is not FIRST')
    struct.pack_into('<I', d, 12, first['arg'] + len(blk))   # offset to next DXE grows
    fix_header_xor(d, 0)
    list(blocks(d))                                            # re-parse: must stay consistent
    return bytes(d)


def unpack(op1):
    if struct.unpack('<L', op1[:4])[0] != binascii.crc32(op1[4:]):
        die('CRC-32 mismatch: firmware file is damaged')
    raw = lzma.decompress(op1[4:], format=lzma.FORMAT_ALONE)
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        return [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]


def pack(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as t:
        for info, data in members:
            info = copy.copy(info)
            if data is not None:
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
            else:
                t.addfile(info)
    comp = lzma.compress(buf.getvalue(), format=lzma.FORMAT_ALONE, filters=LZMA_FILTERS)
    return struct.pack('<L', binascii.crc32(comp)) + comp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('firmware')
    ap.add_argument('-o', '--output')
    ap.add_argument('--payload', default=os.path.join(HERE, 'build', 'obl.bin'))
    ap.add_argument('--sym', default=os.path.join(HERE, 'build', 'obl.sym'))
    ap.add_argument('--allow-modded', action='store_true', help='accept a non-stock R246 (e.g. op1r output)')
    a = ap.parse_args()

    op1 = open(a.firmware, 'rb').read()
    if sha256(op1) != STOCK_SHA256 and not a.allow_modded:
        die('input is not the original op1_246.op1 (use --allow-modded for an op1r-patched R246)')
    payload = open(a.payload, 'rb').read()
    syms = {}
    for line in open(a.sym):
        v, _, name = line.split()
        syms[name] = int(v, 16)
    for h in HOOKS:
        for s in h[2:]:
            if s not in syms:
                die(f'symbol {s} missing from {a.sym}')

    members = unpack(op1)
    names = [m.name for m, _ in members]
    i = names.index('OP1_vdk.ldr')
    boot = names.index('te-boot.ldr')
    ldr = members[i][1]
    if sha256(op1) == STOCK_SHA256 and sha256(ldr) != STOCK_LDR_SHA256:
        die('OP1_vdk.ldr does not match stock R246')
    new_ldr = patch_ldr(ldr, payload, syms, a.allow_modded)
    boot_before = members[boot][1]
    members[i] = (members[i][0], new_ldr)
    out = pack(members)
    if len(out) > 15_000_000:
        die('output larger than the OP-1 accepts')

    # verify: unpack the result again
    check = unpack(out)
    cn = {m.name: dt for m, dt in check}
    if cn['te-boot.ldr'] != boot_before:
        die('te-boot.ldr changed - refusing')
    if cn['OP1_vdk.ldr'] != new_ldr or [m.name for m, _ in check] != names:
        die('repacked archive does not round-trip')

    dst = a.output or os.path.splitext(a.firmware)[0] + '-oblique.op1'
    open(dst, 'wb').write(out)
    print(f'OK: {dst}  ({len(out):,} bytes)  sha256 {sha256(out)}')
    print(f'  block @ {LOAD_ADDR:#010x}, {len(payload)} bytes; hooks: ' +
          ', '.join(f'{h[0]:#x}->{syms[h[2]]:#x}' for h in HOOKS))


if __name__ == '__main__':
    main()
