/* Perspective_Highway sobre el SpritePool global (R5). La lógica de armado y el presupuesto de
 * sprites viven en highway_layout.c (puro y probado en el host). */
#ifndef NGBAND_HIGHWAY_H
#define NGBAND_HIGHWAY_H
#include "highway_layout.h"
#include "gameplay.h"

/* Valores de HwyView.fall_frames por Difficulty (fácil, medio, difícil, experto) (R5.8). */
u8   highway_fall_frames(u8 difficulty);

/* Rellena una vista con los valores por defecto de 1 o 2 jugadores: x_origin en el centro de su
 * mitad de pantalla (R5.10) y ancho reducido cuando son dos. */
void highway_view_init(HwyView *v, u8 player, u8 nplayers, u8 difficulty, bool drums, u8 lanes);

/* Un cuadro: arma el Highway de cada jugador y lo vuelca a la sombra. El llamador hace antes
 * `spr_pool_begin(&g_spr)` (el Stage comparte el pool) y después `spr_commit()`. `cur[i]` es el
 * cursor del Judge del jugador i. */
void highway_draw(const HwyView *views, u8 nviews, const Chart *const *charts,
                  const ChartCursor *const *cur, u16 now);

/* Lista y geometría del último cuadro: el Stage reparte el presupuesto que el Highway deja libre. */
const HwyList *highway_list(void);
const HwyGeom *highway_geom(void);
/* Sprites rechazados por presupuesto en el último cuadro (depuración). */
u16  highway_dropped(void);

#endif /* NGBAND_HIGHWAY_H */
