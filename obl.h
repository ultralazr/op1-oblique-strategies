#ifndef OBL_H
#define OBL_H
typedef struct { short x16, y16; const char *text; } obl_line_t;   /* px * 16 */
extern const unsigned char obl_strokes[];
extern const unsigned short obl_glyph_ofs[128];
extern const unsigned char obl_glyph_w[128];
extern const obl_line_t obl_lines[];
extern const unsigned short obl_card_first[];
extern const int obl_ncards;
extern const obl_line_t obl_title;
extern const int obl_scale_body, obl_scale_title, obl_gap_body, obl_gap_title, obl_space_body, obl_space_title;
#endif
