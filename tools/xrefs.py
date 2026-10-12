"""Collect call/jump targets (direct + absolute Px.H/Px.L loads) from an objdump listing."""
import re, sys, collections
def targets(lines):
    regs, out = {}, []
    for l in lines:
        m = re.match(r'\s*([0-9a-f]+):', l)
        if not m: continue
        pc = int(m.group(1), 16)
        m = re.search(r'(CALL|JUMP\.L|JUMP\.S|JUMP) 0x0x([0-9a-f]+)', l)
        if m and m.group(1) == 'CALL': out.append((pc, int(m.group(2), 16), 'call'))
        m = re.search(r'\b([PR]\d)\.([LH]) = 0x([0-9a-f]+);', l)
        if m:
            r = regs.setdefault(m.group(1), [None, None])
            r[0 if m.group(2) == 'L' else 1] = int(m.group(3), 16)
        m = re.search(r'(CALL|JUMP) \((P\d)\)', l)
        if m and m.group(2) in regs and None not in regs[m.group(2)]:
            lo, hi = regs[m.group(2)]
            out.append((pc, (hi << 16) | lo, 'icall' if m.group(1) == 'CALL' else 'ijump'))
        if re.search(r'\bRTS;|UNLINK', l): regs = {}
    return out
if __name__ == '__main__':
    t = targets(open(sys.argv[1]).read().splitlines())
    lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
    c = collections.defaultdict(list)
    for pc, a, k in t:
        if lo <= a < hi: c[a].append((pc, k))
    for a in sorted(c):
        print(f'{a:#x} n={len(c[a])} from ' + ' '.join(f'{p:#x}{k[0]}' for p, k in c[a][:6]))
