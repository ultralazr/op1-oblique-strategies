#!/usr/bin/env python3
"""Unpack an OP-1 .op1 and build analysis images from OP1_vdk.ldr.

    python3 tools/mkimage.py op1_246.op1 outdir/

Writes:
  outdir/<members>            the unpacked firmware tree (content/, OP1_vdk.ldr, te-boot.ldr)
  outdir/sdram.bin            flat SDRAM image, base 0x0 (FILL blocks expanded)
  outdir/sdram_code.bin       0x01000000..0x01C00000 slice (load in Ghidra/objdump at base 0x01000000)
  outdir/l1/<addr>.bin        L1 SRAM blocks (0xFF8xxxxx data, 0xFFAxxxxx code)
Blocks with flag 0x0400 (L1 only, ~80 KB) are XTEA-encrypted; they are written as-is (still encrypted).
"""
import io, lzma, os, struct, sys, tarfile, binascii
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldr


def main(src, out):
    d = open(src, 'rb').read()
    if struct.unpack('<L', d[:4])[0] != binascii.crc32(d[4:]):
        sys.exit('CRC mismatch')
    raw = lzma.decompress(d[4:], format=lzma.FORMAT_ALONE)
    os.makedirs(out, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        t.extractall(out, filter='data')
    v = open(os.path.join(out, 'OP1_vdk.ldr'), 'rb').read()
    regs, enc = [], 0
    for b in ldr.blocks(v):
        if b['flags'] & (ldr.IGNORE | ldr.FIRST):
            continue
        if b['flags'] & ldr.FILL:
            if b['count']:
                regs.append((b['addr'], struct.pack('<I', b['arg']) * (b['count'] // 4)))
        elif b['payload']:
            enc += bool(b['flags'] & 0x0400)
            regs.append((b['addr'], v[b['data_off']:b['data_off'] + b['payload']]))
    top = max(a + len(x) for a, x in regs if a < 0x10000000)
    img = bytearray(top)
    os.makedirs(os.path.join(out, 'l1'), exist_ok=True)
    for a, x in regs:
        if a < 0x10000000:
            img[a:a + len(x)] = x
        else:
            open(os.path.join(out, 'l1', f'{a:08x}.bin'), 'wb').write(x)
    open(os.path.join(out, 'sdram.bin'), 'wb').write(img)
    open(os.path.join(out, 'sdram_code.bin'), 'wb').write(img[0x01000000:0x01C00000])
    print(f'sdram image up to {top:#x}; {enc} encrypted L1 blocks left as-is')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
