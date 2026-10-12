/* Oblique Strategies overlay for the original OP-1, firmware R246.
 *
 * Shift + press the orange encoder shows a random card on top of the current screen;
 * any key press closes it (that press and its release are swallowed).
 *
 * Hooks (patched CALL sites in stock R246, see patch_oblique.py):
 *   0x019c2d3e  CALL key_handler(key, state)  -> obl_key
 *   0x01a3bc0e  CALL 0x019d7ed0 (end of GUI frame, after all screens drew) -> obl_frame
 */
#include "obl.h"

typedef struct { int x, y; } pt_t;                  /* screen px, 10 fractional bits */

/* next handlers in the chain; the patcher overwrites these with whatever the hooked CALLs
 * targeted before (stock functions, or another mod's hooks such as op1r's) */
void (*obl_next_key)(int, int) = (void (*)(int, int))0x019b6c74;
void (*obl_next_frame)(void) = (void (*)(void))0x019d7ed0;
#define KEY_HANDLER   obl_next_key
#define FRAME_TAIL    obl_next_frame
#define SHIFT_HELD    ((int (*)(void))0x019d7c6c)
#define GET_RASTER    ((void *(*)(void))0x01a3b490)
#define DRAW_LINE     ((void (*)(void *, const pt_t *, const pt_t *, int, const unsigned char *))0x01a24a4c)

#define KEY_ENC_ORANGE 62                            /* encoder push switches are keycodes 59..62 */

static const unsigned char c_black[4] = {0, 0, 0, 255};
static const unsigned char c_frame[4] = {0x6f, 0x71, 0x73, 255};
static const unsigned char c_title[4] = {0xff, 0x3a, 0x5d, 255};
static const unsigned char c_text[4]  = {0xff, 0xff, 0xff, 255};

static volatile int g_active;
static volatile int g_card = -1;
static unsigned int g_rng;
static unsigned char g_swallow[64];                 /* release events to drop */

static unsigned int cycles(void)
{
	unsigned int c;
	__asm__ volatile ("%0 = CYCLES;" : "=d"(c));
	return c;
}

static unsigned int rnd(void)
{
	g_rng = g_rng * 1664525u + 1013904223u + cycles();
	return g_rng >> 8;
}

static void pick_card(void)
{
	int n = obl_ncards, c;
	do {
		c = (int)(((rnd() & 0xffff) * (unsigned)n) >> 16);
	} while (n > 1 && c == g_card);
	g_card = c;
}

void obl_key(int key, int state)
{
	int k = key & 63;

	if (!state && g_swallow[k]) {
		g_swallow[k] = 0;
		return;
	}
	if (g_active) {
		if (state) {                                 /* any press closes the card */
			g_active = 0;
			g_swallow[k] = 1;
			return;
		}
		KEY_HANDLER(key, state);                     /* releases of keys held before */
		return;
	}
	if (state && key == KEY_ENC_ORANGE && SHIFT_HELD()) {
		pick_card();
		g_active = 1;
		g_swallow[k] = 1;
		return;
	}
	KEY_HANDLER(key, state);
}

static void line(void *r, int x0, int y0, int x1, int y1, int w, const unsigned char *col)
{
	pt_t a, b;
	a.x = x0; a.y = y0; b.x = x1; b.y = y1;
	DRAW_LINE(r, &a, &b, w, col);
}

/* draw one string; x16/y16 = top-left in px*16 */
static void text(void *r, const obl_line_t *ln, int scale, int gap, int space, int w, const unsigned char *col)
{
	int x = ln->x16 << 6, y = ln->y16 << 6;           /* -> .10 fixed */
	const char *s = ln->text;

	for (; *s; s++) {
		int ch = *s & 0x7f;
		if (ch == ' ') {
			x += space;
			continue;
		}
		unsigned ofs = obl_glyph_ofs[ch];
		if (ofs == 0xffff)
			continue;
		const unsigned char *p = obl_strokes + ofs;
		int n;
		while ((n = *p++) != 0) {
			int px = x + p[0] * scale, py = y + p[1] * scale;
			p += 2;
			while (--n > 0) {
				int qx = x + p[0] * scale, qy = y + p[1] * scale;
				line(r, px, py, qx, qy, w, col);
				px = qx; py = qy;
				p += 2;
			}
		}
		x += obl_glyph_w[ch] * scale + gap;
	}
}

static void draw_card(void)
{
	void *r = GET_RASTER();
	int i;

	/* background: one very wide line covering the screen */
	line(r, 0, 80 << 10, 320 << 10, 80 << 10, 160 << 10, c_black);
	/* frame */
	line(r, 3 << 10, 3 << 10, 317 << 10, 3 << 10, 1 << 10, c_frame);
	line(r, 317 << 10, 3 << 10, 317 << 10, 157 << 10, 1 << 10, c_frame);
	line(r, 317 << 10, 157 << 10, 3 << 10, 157 << 10, 1 << 10, c_frame);
	line(r, 3 << 10, 157 << 10, 3 << 10, 3 << 10, 1 << 10, c_frame);

	text(r, &obl_title, obl_scale_title, obl_gap_title, obl_space_title, 0x480, c_title);
	for (i = obl_card_first[g_card]; i < obl_card_first[g_card + 1]; i++)
		text(r, &obl_lines[i], obl_scale_body, obl_gap_body, obl_space_body, 0x600, c_text);
}

void obl_frame(void)
{
	if (g_active && g_card >= 0)
		draw_card();
	FRAME_TAIL();
}
