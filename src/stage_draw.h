/* Dibujo del Stage (R11) sobre el SpritePool global: une stage_layout.c con los datos de `ngband gfx`. */
#ifndef NGBAND_STAGE_DRAW_H
#define NGBAND_STAGE_DRAW_H
#include "stage.h"
#include "highway_layout.h"
/* Un cuadro: llamar después de `highway_draw` y antes de `spr_commit` (usa lo que el Highway dejó libre).
 * Devuelve true si rehízo el Stage (un cuadro caro: el llamador puede dejar otro trabajo para el siguiente). */
bool stage_draw(const StageState *st, u8 nplayers, const HwyView *views, u8 nviews);
/* Olvida el Stage guardado (al empezar una partida: las demás pantallas ocultan los sprites). */
void stage_draw_reset(void);
#endif /* NGBAND_STAGE_DRAW_H */
