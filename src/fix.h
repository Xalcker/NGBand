#ifndef NGBAND_FIX_H
#define NGBAND_FIX_H
#include "spr_diff.h"

extern FixShadow g_fix;

void fix_init(void);
/* Texto ASCII (32..126); `tile_base` es el tile de ' '. Devuelve las columnas escritas. */
u8   fix_text(u8 col, u8 row, const char *s, u16 tile_base, u8 pal);
/* Encola solo los tiles distintos del cuadro anterior. */
u16  fix_flush(void);

#endif /* NGBAND_FIX_H */
