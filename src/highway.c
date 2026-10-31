/* Perspective_Highway: une el layout puro (highway_layout.c) con los datos de `ngband gfx`
 * (gfx_data.h) y con el SpritePool global (spr.h). */
#include <stddef.h>
#include "highway.h"
#include "gfx_data.h"
#include "spr.h"

/* highway_layout.c lee la tabla de perspectiva como HwyRow: mismo diseño que PerspRow. */
_Static_assert(sizeof(HwyRow) == sizeof(PerspRow), "HwyRow y PerspRow deben coincidir");
_Static_assert(offsetof(HwyRow, y) == offsetof(PerspRow, y), "y");
_Static_assert(offsetof(HwyRow, hshrink) == offsetof(PerspRow, hshrink), "hshrink");
_Static_assert(offsetof(HwyRow, vshrink) == offsetof(PerspRow, vshrink), "vshrink");
_Static_assert(offsetof(HwyRow, x_lane) == offsetof(PerspRow, x_lane), "x_lane");
_Static_assert(HWY_LANES == 5, "la tabla de perspectiva tiene 5 carriles");

/* Arte opcional: los PNG de assets/gfx (cola.png, linea.png, rombo.png) dan sus propios tiles;
 * sin ellos se reutiliza la gema (el layout funciona igual, solo cambia el dibujo). */
#ifdef GFX_COLA_TILE
#define TAIL_TILE GFX_COLA_TILE
#else
#define TAIL_TILE gem_tile[GEM_LEVELS - 1]
#endif
#ifdef GFX_LINEA_TILE
#define LINE_TILE GFX_LINEA_TILE
#else
#define LINE_TILE gem_tile[GEM_LEVELS - 1]
#endif
#ifdef GFX_BOMBO_TILE
#define KICK_TILE GFX_BOMBO_TILE
#else
#define KICK_TILE 0
#endif
#ifdef GFX_ROMBO_TILE
#define CYMBAL_TILE GFX_ROMBO_TILE
#else
#define CYMBAL_TILE gem_tile[GEM_LEVELS - 1]
#endif

#define SCREEN_CENTER_X 160
#define XSCALE_TWO      192   /* 2 jugadores: 200 px de tabla * 3/4 = 150 px caben en media pantalla */

static HwyList s_list;
static HwyGeom s_geom;
static bool s_geom_ready;

static void geom_init(void)
{
  s_geom.rows = (const HwyRow *)persp;
  s_geom.nrows = PERSP_ROWS;
  s_geom.row_level = persp_gem_level;
  s_geom.gem_hshrink = gem_hshrink;
  s_geom.gem_vshrink = gem_vshrink;
  s_geom.gem_tile = gem_tile;
  s_geom.levels = GEM_LEVELS;
  s_geom.hit_row = (u16)(PERSP_Y_HIT - persp[0].y);
  s_geom.x_center = persp[s_geom.hit_row].x_lane[2];
  s_geom.cymbal_tile = (u16)(CYMBAL_TILE);
  s_geom.tail_tile = (u16)(TAIL_TILE);
  s_geom.kick_tile = (u16)(KICK_TILE);
  s_geom.line_tile = (u16)(LINE_TILE);
  s_geom.lane_pal[0] = GFX_GEM_VERDE_PAL;
  s_geom.lane_pal[1] = GFX_GEM_ROJO_PAL;
  s_geom.lane_pal[2] = GFX_GEM_AMARILLO_PAL;
  s_geom.lane_pal[3] = GFX_GEM_AZUL_PAL;
  s_geom.lane_pal[4] = GFX_GEM_NARANJA_PAL;
  s_geom.star_pal = GFX_GEM_ESTELAR_PAL;
  s_geom.blue_pal = GFX_GEM_AZUL_PAL;
  s_geom.line_pal = GFX_GEM_ESTELAR_PAL;
  s_geom_ready = true;
}

u8 highway_fall_frames(u8 difficulty)
{
  static const u8 fall[4] = { 6, 5, 4, 3 };   /* R5.8 */
  return fall[difficulty & 3];
}

void highway_view_init(HwyView *v, u8 player, u8 nplayers, u8 difficulty, bool drums, u8 lanes)
{
  u8 *p = (u8 *)v;
  u32 i;
  for (i = 0; i < sizeof *v; i++) p[i] = 0;
  v->player = player;
  v->nplayers = nplayers ? nplayers : 1;
  v->drums = drums;
  v->expert = difficulty == 3;
  v->ncols = drums ? 4 : HWY_LANES;   /* como en NESBand: siempre 5 carriles; fácil y medio usan los primeros */
  v->lane_mask = drums ? 0x1F : (u8)((1u << lanes) - 1u);
  v->fall_frames = highway_fall_frames(difficulty);
  if (v->nplayers == 1) {
    v->x_origin = SCREEN_CENTER_X;
    v->xscale = 256;
  } else {
    v->x_origin = player == 0 ? SCREEN_CENTER_X / 2 : SCREEN_CENTER_X + SCREEN_CENTER_X / 2;
    v->xscale = XSCALE_TWO;
  }
}

void highway_draw(const HwyView *views, u8 nviews, const Chart *const *charts,
                  const ChartCursor *const *cur, u16 now)
{
  u8 i;
  if (!s_geom_ready) geom_init();
  hwy_list_begin(&s_list);
  for (i = 0; i < nviews; i++)
    hwy_build(&s_list, &s_geom, &views[i], charts[i], cur[i], now);
  hwy_apply(&s_list, &g_spr);
}

u16 highway_dropped(void) { return s_list.dropped; }

const HwyList *highway_list(void) { return &s_list; }
const HwyGeom *highway_geom(void)
{
  if (!s_geom_ready) geom_init();
  return &s_geom;
}
