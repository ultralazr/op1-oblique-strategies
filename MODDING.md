# Writing your own OP-1 firmware mods: a guide for humans and coding agents

Everything here applies to the **original OP-1** with firmware **R246** (`op1_246.op1`, SHA-256
`c5315218f825f143b415ca554516541898abee843d3a236df0b54c04e1fb13a9`). The OP-1 field, OP-Z and OP-XY use encrypted
firmware and none of this applies to them. Addresses are R246 load addresses unless noted.

Each fact is marked:
- **[hw]** verified on hardware by this project
- **[op1r]** relied on by the op1r mods, which run on many units
- **[static]** found by reading code only

---

## 1. Ground rules

1. **Never modify `te-boot.ldr`.** As long as the bootloader is intact, holding **COM** at power-on → firmware
   update can always flash the original `op1_246.op1` back. Make every build check that `te-boot.ldr` is
   byte-identical to stock.
2. **Don't redistribute TE firmware or assets.** Ship your own code plus a patcher that takes the user's
   original file, checks its SHA-256 and applies diffs (see `patch_oblique.py`, or op1r's `patch_op1.py`).
3. **Back up the device** (disk mode) before flashing a test build. A mod that saves unknown engine/FX ids into
   patches can make *stock* firmware crash on load, which needs a factory reset.
4. A crash shows an assert/exception screen. Ask for a photo; it usually names a source file and line, or a PC.

## 2. Toolchain

| Tool | Version used | Purpose |
|---|---|---|
| Python 3 | 3.12 | packing/unpacking, patchers, data generators (standard library only) |
| binutils `--target=bfin-elf` | 2.42 | `bfin-elf-as/ld/objcopy/objdump/nm` |
| GCC `--target=bfin-elf` | 13.3.0 | C → Blackfin. Freestanding, C only, no newlib needed |
| Ghidra + [sualk/ghidra-blackfin](https://github.com/sualk/ghidra-blackfin) | 12.1.4 + JDK 21 | decompiling, call graphs |

### binutils + GCC

**Linux / WSL:**
```sh
# binutils
../binutils-2.42/configure --target=bfin-elf --prefix=/opt/bfin --disable-nls --disable-werror --disable-gdb --disable-sim
make -j && make install
# gcc (out of tree)
../gcc-13.3.0/configure --target=bfin-elf --prefix=/opt/bfin --enable-languages=c --without-headers --with-newlib \
  --disable-nls --disable-shared --disable-threads --disable-libssp --disable-libquadmath --disable-libgomp
make -j all-gcc all-target-libgcc && make install-gcc install-target-libgcc
```

**Windows:** do the same inside MSYS2 (UCRT64). Install `base-devel`, `mingw-w64-ucrt-x86_64-toolchain`, `gmp`,
`mpfr`, `mpc`, `isl`, `texinfo`, `bison` and `flex`. Two quirks:
- Current MSYS2 ships GCC 16, which can't compile GCC 13's sources at its default language standard. Configure
  with `CFLAGS="-O2 -std=gnu17" CXX="g++ -std=gnu++17" CXX_FOR_BUILD="g++ -std=gnu++17"`.
- To run the tools from Git Bash or PowerShell, copy the UCRT runtime DLLs from `C:\msys64\ucrt64\bin` next to
  the executables in `bin\`, `bfin-elf\bin\` and `libexec\gcc\bfin-elf\13.3.0\`.

Check: `bfin-elf-gcc -mcpu=bf524 -O2 -c t.c && bfin-elf-objdump -d t.o`.

### Ghidra

1. Build ghidra-blackfin (`gradle -PGHIDRA_INSTALL_DIR=<ghidra>`) and unzip the result into
   `<ghidra>/Extensions/Ghidra`. For Ghidra 12, apply `tools/ghidra-blackfin-ghidra12.patch` first. It only
   touches the plugin's `.ldr` loader; the processor module is unchanged.
2. Import the **flat image**, not the LDR: `-loader BinaryLoader -loader-baseAddr 0x01000000 -processor blackfin:LE:32:default`.
3. A raw binary has no entry points. Run `tools/ghidra_scripts/MarkLinkFunctions.java` as a pre-script: it
   creates a function at every `LINK` prologue (about 4,200 of them). Without it, decompiles start
   mid-function and get truncated.
4. Headless usage:
   ```
   analyzeHeadless <projdir> op1 -import sdram_code.bin -processor blackfin:LE:32:default -cspec default \
     -loader BinaryLoader -loader-baseAddr 0x01000000 -scriptPath tools/ghidra_scripts \
     -preScript MarkLinkFunctions.java -analysisTimeoutPerFile 7200
   analyzeHeadless <projdir> op1 -process sdram_code.bin -noanalysis -readOnly -scriptPath tools/ghidra_scripts \
     -postScript DecompileAt.java <outdir> 0x01a3bb20            # writes <outdir>/0x01a3bb20.c
   analyzeHeadless ... -postScript CallersOf.java 3 0x01a24a4c  # caller tree, 3 levels
   ```
5. Limits:
   - Many DSP and parallel (`||`) instructions have no p-code, so decompiles often stop with
     "halt_unimplemented".
   - Indirect tail jumps show up as `UNRECOVERED_JUMPTABLE`.

   **Always cross-check with `bfin-elf-objdump`**, which disassembles everything correctly.

## 3. Getting the code

```sh
python3 tools/mkimage.py op1_246.op1 fw/   # unpacked tree, fw/sdram.bin, fw/sdram_code.bin, fw/l1/*.bin
bfin-elf-objdump -D -b binary -m bfin --adjust-vma=0x01000000 \
  --start-address=0x018ab7cc --stop-address=0x01aa7078 fw/sdram_code.bin > stock_code.dis
```

- **`.op1` container:**
  - Layout: `u32 CRC32 (LE, over the rest)` + LZMA "alone" stream + tar (GNU) containing `content/`,
    `OP1_vdk.ldr` and `te-boot.ldr`.
  - Repack with LZMA1 `preset 9, lc 3, lp 1, pb 2, dict 2**23` (op1repacker's settings) and keep the original
    tar member order and metadata.
  - Wrong settings give `Alloc failed`, `Decode failed` or `Missing ustar tag` on the device.
  - Output must stay below about 15 MB.
- **`OP1_vdk.ldr`:** a BF52x boot stream (`tools/ldr.py`). Each 16-byte block header is
  `{u32 0xAD<xor><flags16>, addr, count, arg}`, and the XOR of all 16 bytes is 0.
  - Normal payload blocks use flags `0x0006`; FILL blocks use `0x0106`, and their `arg` is the fill word.
  - The FIRST block's `arg` is `filesize - 16`. Fix it, and its XOR byte, when you insert data.
  - Code runs from the boot stream's FINAL block, which must stay last apart from a trailing IGNORE block.
- **Encryption:**
  - Only 45 blocks are XTEA-encrypted (flags `0x2406`). All of them are L1 SRAM (`0xFF8…`/`0xFF9…` data,
    `0xFFA00000` code), about 80 KB in total. Only the first 8 bytes of each 24-byte chunk are encrypted.
  - **All SDRAM code is plaintext**, so most mods never need decryption.
  - If you need L1 (for example the encoder/keyboard readers or AGG scanline code), see
    [sualk/op1-decryptor](https://github.com/sualk/op1-decryptor) and the public OTP dump in
    [Tolsi/op1dumps](https://github.com/Tolsi/op1dumps). The 128-bit key is one of the OTP pages, as
    big-endian words.
- **Memory map (SDRAM, from LDR blocks):**
  - code ≈ `0x018AB7CC–0x01AA7078`
  - rodata/strings ≈ `0x018B…–0x0190…`
  - vtables ≈ `0x0190E…–0x0191…`
  - bss `0x01AA7078–0x01DFFF34` (FILL)
  - **unused gap `0x01DFFF34–0x02000000`**
  - data `0x02000000–0x02025800`
  - gap `0x02025800–0x02040000`
  - bss `0x02040000–0x027D1FE0`
- **Free memory for your code:**
  - op1r loads about 200 KB at `0x01E00000` **[op1r]**.
  - This mod loads at `0x01E40000` **[hw]**.
  - stfj's scale mod used `0x02030000` in the second gap **[hw, stfj]**.
  - Put your block somewhere that doesn't collide with these, and say where in your README.
- **Source paths in assert strings** (`..\src\gui\screens\*.cpp:<line> <expr>`) are the best landmarks. Find code
  that loads a string address with `Px.H = hi; Px.L = lo` pairs. `tools/xrefs.py` does this for call targets, and
  the same regex finds data references.

## 4. Calling convention and C++ layout

- **Calling convention:** VisualDSP and GCC's `bfin-elf` ABI are compatible.
  - Arguments go in `R0, R1, R2`; the 4th and later go on the stack at `[SP+12]`, `[SP+16]`… The caller always
    reserves 12 bytes for the register arguments.
  - The return value is in `R0`. `R4–R7`, `P3–P5`, `FP` and `SP` are callee-saved.
  - GCC-compiled C can call stock functions through casted pointers, e.g. `((void(*)(int,int))0x019b6c74)(k, s)`,
    and stock code can call GCC functions **[hw]**.
- **Fixed point:** GUI coordinates are fixed point with 10 fractional bits (`px << 10`). A `kScreenWidth` of 320
  shows up as `320 << 10`.
- **C++ objects:**
  - An object's vtable pointer is followed by entries of 8 bytes, `{s32 this_adjust, u32 fn}`.
  - A virtual call loads `fn = [vt + 8k + 4]` and `adj = W[vt + 8k]`, then calls `fn(this + adj, ...)`.
  - The base `Screen` vtable is `0x01911474`, with `draw(this, dt)` at offset `+0x1c` **[static]**.
- **CALL instruction:** `CALL pcrel24` is `0xE3hh 0xllll` (little-endian halfwords), with
  `target = pc + 2*sext24(hh:llll)` and a range of ±16 MB. `JUMP.L` is the same with `0xE2`. Redirecting one
  existing `CALL` to your function is the cleanest hook.
  - **Keep the next target in a variable**, so your hook can chain to whatever was there before, such as
    another mod's hook. See `obl_next_key` and how `patch_oblique.py` fills it in.
- **If you hook by replacing other instructions:** use a proper `LINK`/`UNLINK` frame in the wrapper, replay
  every instruction you overwrote, and restore the registers you clobbered. Per stfj's notes, frameless
  `CALL…; RTS` wrappers froze disk mode.

## 5. Firmware internals that are useful for mods

### Input [hw/static]

- **Key event queue:** u16 entries at `0x01DD5044` of the form `(pressed<<8)|keycode`, read index at
  `0x01DD5244`, write index at `0x01DD5248`. Producers:
  - the key reader in L1
  - the encoder reader `0xFFA04A44` (encoder pushes)
  - `0x019EFE40` (virtual keys `56+i`)
- **Input loop** `0x019C2CC0`: pops each event and does `CALL 0x019B6C74(keycode, pressed)` at
  **`0x019C2D3E`**. op1r and this mod hook that call.
- **`0x019B6C74` key handler:**
  - It gets the active *controller* (`0x019E97FC`).
  - On a press it calls `vt+0x1c` when shift is held and `vt+0x14` otherwise; on a release it calls `vt+0x24`.
  - Encoder turns go through `0x019B6C0C(idx, delta*)`, using `idx+4` while shift is held, to `vt+0x2c`.
  - Encoder deltas accumulate in `0x01DD5250[4]`.
- **Shift held:** `0x019D7C6C()`, which returns the byte at `0x01DD7F78`.
- **Keycodes** (CTRL-mode MIDI CC = keycode + 5):

| code | key | code | key |
|---|---|---|---|
| 0 | help | 21 | sequencer |
| 1 | metronome | 33 / 34 / 35 | rec / play / stop |
| 2–5 | synth, drum, tape, mixer | 36 / 37 | left / right |
| 6–9 | T1–T4 | 38 | shift |
| 10–12 | lift, drop, scissors | 43 | mic/input |
| 16–20, 45–47 | keys 1–8 | 44 | COM |
| 59–62 | encoder push blue, green, white, **orange** **[hw]** | 56, 57 | virtual (GPIO callback) |

`pressed` is 1 on press and 0 on release. op1r injects keys by writing this queue itself (its MIDI-CC handler,
`0x1E01A74` in op1r 14).

### Rendering [hw/static]

- **GUI frame** `0x01A3BB20(screens[0x44])`, once per frame:
  1. Re-colour if needed.
  2. `0x01A23466(raster)` begins the frame.
  3. For each screen: `if (vt+0x14)(screen)` then `(vt+0x1c)(screen, dt)`.
  4. `0x01A0D1E0(dt, …)`.
  5. **`CALL 0x019D7ED0` at `0x01A3BC0E`**. Hook this call to draw on top of everything.
- **Rasterizer:** `0x01A3B490()` returns the global `s_raster` at `0x01DF4E34`, which is set once at boot.
- **Line drawing:**
  ```c
  typedef struct { int x, y; } pt_t;   // px << 10, screen 320 x 160
  void drawLine(void *raster, const pt_t *a, const pt_t *b, int width /* 0x400 = 1px */,
                const unsigned char rgba[4]);   // 0x01A24A4C
  ```
  Points pass through the display base transform at `0x01DE5E68` (3×3, column-major, .10). A very wide
  line works as a filled rectangle **[hw]**.
- **Colours:** `{r,g,b,a}`. The OP-1 palette used by op1r: blue `4d9eff`, green `00ed95`, white `ffffff`,
  red/orange `ff3a5d`, greys `aeb1dc` and `6f7173`.
- **Text:** the stock font is `content/display/opfont.svg`. Its glyph ids are single characters; lowercase ids
  draw uppercase-style shapes, and there are no `'` or `( )`. Stock `Font.cpp`/`Text.cpp` build text into SVG
  documents. Both op1r and this mod skip that and draw strokes with `drawLine` (see `gen_data.py`, which
  converts the SVG glyphs into polylines).
- **Screens:**
  - Screens are SVG documents (`content/display/*.svg`, parsed by RapidXML plus a minimal TE SVG layer).
  - Code finds nodes by id with `0x01A3B580(screen, "id")` and shows, hides or transforms them.
  - Keep stock ids and group structure. Inkscape output breaks the parser; Illustrator-style SVGs work best.
  - New screens and engines need vtable/table work. op1r's manifest (`data/manifest.json`) shows which
    pointer tables it rewrites.

### Data

- `content/op1_factory.db` (SQLite) holds `synth_types`, `fx_types` and presets. Live settings are on a hidden
  system disk.
- Hidden engines (`filter` fx id 2, `iter` synth id 11) are enabled by DB rows (op1repacker).

## 6. Debugging without a console

- **AIF logging [hw, stfj]:**
  1. Store log words in RAM.
  2. Hook the filesync AIF export (`0x0199D8B4 → 0x019D16BC`) so the buffer is written into the first exported
     `.aif` in disk mode.
  3. Only the high 16 bits of each 32-bit word survive.

  See the notes in
  [stfj/OP-1-Note-Quantization-PublicGit](https://github.com/stfj/OP-1-Note-Quantization-PublicGit).
- **Visual:** draw values on screen with your own frame hook. It's the quickest feedback loop.
- **Asserts:** `0x01919AA8(fmt, …)` is the assert/printf-to-screen used throughout stock code.

## 7. Workflow that worked for this mod

1. Find a feature you want to change. Search its strings or `*.cpp` asserts, then find the code referencing them
   (`xrefs.py`, or Ghidra `CallersOf`).
2. Read the function in objdump, decompile it in Ghidra, and identify one `CALL` site to redirect.
3. Use op1r's manifest as an oracle: `tools/fmap.py` maps its byte edits to addresses, so you can see what an
   existing mod already hooks.
4. Write freestanding C:
   - no libc
   - avoid division and modulo (they pull in libgcc)
   - put state in `static` variables
   - put everything in one linker section at a fixed address (`link.ld`)
5. Patch the image:
   - insert one LDR block before FINAL
   - rewrite the `CALL`(s)
   - fix the FIRST block's `arg` and XOR
   - repack
   - verify by unpacking again and checking that `te-boot.ldr` is unchanged
6. Flash, test, and recover with COM-boot + stock firmware if needed.

## 8. Files in `tools/`

| File | What |
|---|---|
| `ldr.py` | LDR block parser / lister: `python3 tools/ldr.py OP1_vdk.ldr all` |
| `mkimage.py` | `.op1` → unpacked tree + flat SDRAM/L1 images |
| `fmap.py` | file offset ↔ load address for an LDR |
| `xrefs.py` | call/jump targets (direct + `Px.H/Px.L` absolute) from an objdump listing |
| `ghidra_scripts/MarkLinkFunctions.java` | seed functions at every `LINK` |
| `ghidra_scripts/MarkFunctions.java` | create functions at given addresses |
| `ghidra_scripts/DecompileAt.java` | decompile addresses to `<outdir>/<addr>.c` |
| `ghidra_scripts/CallersOf.java` | caller tree |
| `ghidra-blackfin-ghidra12.patch` | makes sualk/ghidra-blackfin build against Ghidra 12 |
