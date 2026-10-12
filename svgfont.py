"""Extract stroke polylines per glyph from the OP-1 opfont.svg."""
import re, math, xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'

def decode_id(i):
    s = re.sub(r'_x([0-9A-Fa-f]{2})_', lambda m: chr(int(m.group(1), 16)), i)
    return s

def nums(s):
    return [float(x) for x in re.findall(r'-?\d*\.?\d+(?:e-?\d+)?', s)]

def bez(p0, p1, p2, p3, n=6):
    out = []
    for k in range(1, n + 1):
        t = k / n; u = 1 - t
        out.append((u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                    u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))
    return out

def path_polys(d):
    toks = re.findall(r'[MmLlHhVvCcSsZzQqTtAa]|-?\d*\.?\d+(?:e-?\d+)?', d)
    polys, cur, pos, start, cmd, lastc = [], [], (0.0, 0.0), (0.0, 0.0), None, None
    i = 0
    def take(n):
        nonlocal i
        v = [float(t) for t in toks[i:i + n]]; i += n; return v
    while i < len(toks):
        t = toks[i]
        if re.match(r'[A-Za-z]', t):
            cmd = t; i += 1
            if cmd in 'Zz':
                if cur: cur.append(start); polys.append(cur); cur = []
                pos = start; lastc = None
                continue
        rel = cmd.islower(); C = cmd.upper()
        ox, oy = pos if rel else (0.0, 0.0)
        if C == 'M':
            x, y = take(2); pos = (ox + x, oy + y)
            if cur: polys.append(cur)
            cur = [pos]; start = pos; cmd = 'l' if rel else 'L'; lastc = None
        elif C == 'L':
            x, y = take(2); pos = (ox + x, oy + y); cur.append(pos); lastc = None
        elif C == 'H':
            x, = take(1); pos = ((ox if rel else 0) + x, pos[1]); cur.append(pos); lastc = None
        elif C == 'V':
            y, = take(1); pos = (pos[0], (oy if rel else 0) + y); cur.append(pos); lastc = None
        elif C == 'C':
            a = take(6); p1 = (ox + a[0], oy + a[1]); p2 = (ox + a[2], oy + a[3]); p3 = (ox + a[4], oy + a[5])
            cur += bez(pos, p1, p2, p3); pos = p3; lastc = p2
        elif C == 'S':
            a = take(4)
            p1 = (2 * pos[0] - lastc[0], 2 * pos[1] - lastc[1]) if lastc else pos
            p2 = (ox + a[0], oy + a[1]); p3 = (ox + a[2], oy + a[3])
            cur += bez(pos, p1, p2, p3); pos = p3; lastc = p2
        elif C == 'Q':
            a = take(4); q = (ox + a[0], oy + a[1]); p3 = (ox + a[2], oy + a[3])
            p1 = (pos[0] + 2/3*(q[0]-pos[0]), pos[1] + 2/3*(q[1]-pos[1])); p2 = (p3[0] + 2/3*(q[0]-p3[0]), p3[1] + 2/3*(q[1]-p3[1]))
            cur += bez(pos, p1, p2, p3); pos = p3; lastc = None
        else:
            raise ValueError('unsupported path cmd ' + cmd)
    if cur: polys.append(cur)
    return polys

def elem_polys(e, stroke='#000000'):
    tag = e.tag.replace(NS, '')
    stroke = e.get('stroke', stroke)
    if tag != 'g' and stroke.upper() != '#000000':
        return []
    f = lambda k: float(e.get(k, 0))
    if tag == 'path': return path_polys(e.get('d'))
    if tag == 'line': return [[(f('x1'), f('y1')), (f('x2'), f('y2'))]]
    if tag in ('polyline', 'polygon'):
        v = nums(e.get('points')); pts = list(zip(v[0::2], v[1::2]))
        if tag == 'polygon': pts.append(pts[0])
        return [pts]
    if tag == 'rect':
        x, y, w, h = f('x'), f('y'), f('width'), f('height')
        return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
    if tag in ('circle', 'ellipse'):
        cx, cy = f('cx'), f('cy'); rx = f('r') or f('rx'); ry = f('r') or f('ry')
        return [[(cx + rx * math.cos(a * math.pi / 6), cy + ry * math.sin(a * math.pi / 6)) for a in range(13)]]
    if tag == 'g':
        out = []
        for c in e: out += elem_polys(c, stroke)
        return out
    return []

def load(path):
    root = ET.parse(path).getroot()
    glyphs = {}
    for e in root:
        i = e.get('id')
        if not i: continue
        ch = decode_id(i)
        if len(ch) != 1: continue
        if e.get('transform'): raise ValueError('transform on glyph ' + ch)
        glyphs[ch] = elem_polys(e)
    return glyphs

if __name__ == '__main__':
    import sys
    g = load(sys.argv[1])
    for ch in sorted(g):
        pts = [p for poly in g[ch] for p in poly]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        print(repr(ch), len(g[ch]), 'x %.1f..%.1f y %.1f..%.1f' % (min(xs), max(xs), min(ys), max(ys)))
