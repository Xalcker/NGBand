/* Layout puro del Stage dibujado (R11.1, R11.6, R11.8): bocinas, torres con foco, haces de luz, público
 * y rayo con sprites de la clase "escenario". Sin hardware ni datos generados (el arte llega en
 * StageGeom), así que compila en el 68000 y en el host. `stage_draw.c` lo une con `gfx_data.h` y `g_spr`.
 *
 * Presupuesto (R5.6, R20.4): el Highway se arma primero; el Stage solo admite un sprite si en todas las
 * líneas de barrido que cubre quedan libres, descontando lo que usaron todos los Highways, de las
 * HWY_LINE_BUDGET. Prioridad de admisión: rayo, torres y focos, haces, público y, al final, bocinas.
 */
#ifndef NGBAND_STAGE_LAYOUT_H
#define NGBAND_STAGE_LAYOUT_H
#include "types.h"
#include "stage.h"
#include "highway_layout.h"
#define STG_MAX_SPRITES   SPR_POOL_STAGE
#define STG_PAL_COUNT     10   /* fase*2 + latido (0..7), apagado, destello */
#define STG_PAL_OFF       8
#define STG_PAL_FLASH     9
typedef struct {
  u16 speaker, lamp, truss, beam, crowd, crowd_arms, bolt;   /* primer tile de cada arte */
  u8  pal_base;                                               /* primera de las STG_PAL_COUNT paletas */
  u8  live_pal;   /* 0: cada pieza iluminada lleva la paleta de su luz (stg_light_pal). Si no, todas llevan
                     esta paleta y quien dibuja copia en ella los colores de stg_light_pal: cambiar la luz
                     es escribir 16 colores, no la paleta de cada sprite del Stage en la VRAM. */
} StageGeom;
typedef struct {
  s16 x, y;
  u16 tile;
  u8  pal, height, flip;     /* altura en tiles (1 o 2); flip: bit 0 = horizontal */
} StageSprite;
typedef struct {
  StageSprite s[STG_MAX_SPRITES];
  u16 n;
  u16 dropped;                                /* candidatos rechazados por presupuesto o pool */
  u8  line_cnt[HWY_SCREEN_LINES];             /* sprites del Stage por línea (ver `exact`) */
  u8  exact;                                  /* 0: line_cnt y used no se llenaron (no hacía falta) */
  u8  hwy_max;                                /* cota de sprites del Highway en su línea más llena */
  u8  used[HWY_SCREEN_LINES];                 /* sprites del Highway por línea (si exact) */
  const HwyList *hwy;
} StageList;
/* Paleta de las luces: apagado > destello > latido; si no, la fase de luz (R11.4-R11.7). */
u8 stg_light_pal(const StageGeom *g, const StageState *st);
/* Arma el Stage. `hwy` es la lista ya armada del Highway (su uso por línea se descuenta);
 * `views`/`nviews` son los Highways (el rayo cae sobre el carril de cada uno); `geom` su geometría. */
void stg_build(StageList *l, const StageGeom *g, const StageState *st, u8 nplayers,
               const HwyGeom *geom, const HwyView *views, u8 nviews, const HwyList *hwy);
/* Llena line_cnt si stg_build no lo contó (cuando ninguna línea podía llegar al presupuesto). */
void stg_count_lines(StageList *l);
/* Reparte la lista en el SpritePool de `sh` (entre spr_pool_begin y spr_pool_end). */
void stg_apply(const StageList *l, SpriteShadow *sh);
#endif /* NGBAND_STAGE_LAYOUT_H */
