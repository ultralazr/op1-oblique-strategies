#!/usr/bin/env python3
"""Parse BF52x LDR boot streams (OP-1 OP1_vdk.ldr / te-boot.ldr).

Block header (16 bytes, LE): block_code, target_addr, byte_count, argument.
block_code: [31:24] 0xAD signature, [23:16] header XOR checksum, [15:0] flags.
"""
import struct
import sys

FLAGS = [(0x8000, 'FINAL'), (0x4000, 'FIRST'), (0x2000, 'INDIRECT'), (0x1000, 'IGNORE'),
         (0x0800, 'INIT'), (0x0200, 'CALLBACK'), (0x0100, 'FILL'), (0x0080, 'QUICKBOOT'),
         (0x0020, 'AUX'), (0x0010, 'SAVE')]
FILL, IGNORE, FIRST = 0x0100, 0x1000, 0x4000


def header_xor(hdr):
    """XOR of all header bytes must be 0 (checksum byte included)."""
    x = 0
    for b in hdr:
        x ^= b
    return x


def blocks(data):
    off = 0
    while off + 16 <= len(data):
        code, addr, count, arg = struct.unpack_from('<IIII', data, off)
        if code >> 24 != 0xAD:
            raise ValueError(f'bad block signature at {off:#x}: {code:#010x}')
        flags = code & 0xffff
        payload = 0 if flags & FILL else count
        yield dict(off=off, code=code, flags=flags, addr=addr, count=count, arg=arg,
                   data_off=off + 16, payload=payload, xor_ok=header_xor(data[off:off + 16]) == 0)
        off += 16 + payload


def flagstr(f):
    return '|'.join(n for b, n in FLAGS if f & b) or '-'


def memory_image(data, decrypted=None):
    """{addr: bytes} of all non-ignored payload blocks (fill blocks expanded lazily skipped)."""
    out = []
    for b in blocks(data):
        if b['flags'] & (IGNORE | FIRST) or b['flags'] & FILL or not b['payload']:
            continue
        out.append((b['addr'], data[b['data_off']:b['data_off'] + b['payload']], b))
    return out


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    n = 0
    for b in blocks(d):
        n += 1
        if len(sys.argv) > 2 or n < 40 or b['flags'] & 0xfe00 & ~0x0200:
            print(f"{b['off']:#09x} {b['addr']:#010x} {b['count']:#08x} arg={b['arg']:#010x} "
                  f"{flagstr(b['flags'])}{'' if b['xor_ok'] else ' BADXOR'}")
    print(n, 'blocks')
