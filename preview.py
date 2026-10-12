"""Render glyph strokes / a card layout to PNG for checking."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import svgfont
ROWS = [-142.4, -57.4, 27.6, 112.7, 197.7, 282.8]
def norm(g):
    out = {}
    for ch, polys in g.items():
        pts = [p for poly in polys for p in poly]
        if not pts: continue
        x0 = min(p[0] for p in pts); y0 = min(p[1] for p in pts)
        top = max(r for r in ROWS if r <= y0 + 1.0)
        out[ch] = [[(x - x0, y - top) for x, y in poly] for poly in polys]
    return out
if __name__ == '__main__':
    g = norm(svgfont.load(sys.argv[1]))
    chars = sorted(c for c in g if not c.isupper())
    S = 0.5
    img = Image.new('RGB', (40 * 16, 50 * ((len(chars) + 15) // 16)), 'black')
    d = ImageDraw.Draw(img)
    for k, ch in enumerate(chars):
        ox, oy = 10 + 40 * (k % 16), 10 + 50 * (k // 16)
        for poly in g[ch]:
            d.line([(ox + x * S, oy + y * S) for x, y in poly], fill='white', width=2)
    img.save(sys.argv[2])
