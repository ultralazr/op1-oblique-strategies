#!/usr/bin/env bash
# Build the payload: build/obl.bin (loads at 0x01E40000) + build/obl.sym (entry/hook symbols).
#   bash build.sh path/to/op1_246.op1      (the font is read from the original firmware, never shipped)
# Needs bfin-elf binutils + gcc on PATH (tested: binutils 2.42, GCC 13.3.0) and Python 3.
set -euo pipefail
for PY in python3 python; do "$PY" -c "" 2>/dev/null && break; done
cd "$(dirname "$0")"
[ $# -ge 1 ] || { echo "usage: $0 op1_246.op1" >&2; exit 1; }
mkdir -p build
"$PY" - "$1" build/opfont.svg <<'PY'
import sys, lzma, io, tarfile
d = open(sys.argv[1], 'rb').read()
t = tarfile.open(fileobj=io.BytesIO(lzma.decompress(d[4:], format=lzma.FORMAT_ALONE)))
open(sys.argv[2], 'wb').write(t.extractfile('content/display/opfont.svg').read())
PY
"$PY" gen_data.py build/opfont.svg cards.txt build/obl_data.c
CFLAGS="-mcpu=bf524 -O2 -ffreestanding -fno-builtin -nostdlib -fno-common -Wall -Wextra -I."
bfin-elf-gcc $CFLAGS -c oblique.c -o build/oblique.o
bfin-elf-gcc $CFLAGS -c build/obl_data.c -o build/obl_data.o
bfin-elf-ld -T link.ld -o build/obl.elf build/oblique.o build/obl_data.o -Map build/obl.map
bfin-elf-objcopy -O binary -j .image build/obl.elf build/obl.bin
bfin-elf-nm build/obl.elf | grep -E ' [TDdt] _obl_(key|frame|next_key|next_frame)$' > build/obl.sym
bfin-elf-size build/obl.elf
cat build/obl.sym
