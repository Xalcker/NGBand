/* Dibujo del Stage: arma StageGeom con los tiles generados y reparte la lista en g_spr. */
#include "stage_draw.h"
#include "stage_layout.h"
#include "highway.h"
#include "gfx_data.h"
#include "spr.h"
#include "platform.h"

_Static_assert(STG_PAL_COUNT == 10, "gfx.py genera 10 paletas de escenario");

/* Paleta viva del Stage (ver StageGeom.live_pal): la primera libre después de las de gfx.py. */
#define STAGE_LIVE_PAL GFX_NUM_PALETTES
_Static_assert(STAGE_LIVE_PAL < 256, "la Neo Geo tiene 256 paletas");

static StageList s_list;
static StageGeom s_geom;
static bool s_geom_ready;

static void geom_init(void)
{
  s_geom.speaker = GFX_ESC_BOCINA_TILE;
  s_geom.lamp = GFX_ESC_FOCO_TILE;
  s_geom.truss = GFX_ESC_TORRE_TILE;
  s_geom.beam = GFX_ESC_HAZ_TILE;
  s_geom.crowd = GFX_ESC_PUBLICO_TILE;
  s_geom.crowd_arms = GFX_ESC_PUBLICO_BRAZOS_TILE;
  s_geom.bolt = GFX_ESC_RAYO_TILE;
  s_geom.pal_base = GFX_STAGE_PAL_BASE;
  s_geom.live_pal = STAGE_LIVE_PAL;
  s_geom_ready = true;
}

/* El Stage casi no cambia entre cuadros y armarlo cuesta en el 68000: se rehace cuando cambia su estado
 * (o cada STAGE_REBUILD cuadros, para seguir el presupuesto por línea del Highway). Entre tanto se reservan
 * los mismos índices del pool: la sombra de sprites ya tiene lo que se dibujó. */
#define STAGE_REBUILD 8
static StageState s_last;
static u8 s_last_np, s_age, s_count;
static bool s_valid;

/* Lo que cambia el dibujo: `pulse` y `flash` son cuentas regresivas que bajan cada cuadro, pero al Stage solo
 * le importa si están activas (paleta, público y rayo); compararlas tal cual lo rehacía en cada cuadro. */
/* Las luces (fase, latido, destello, apagado) solo cambian los colores de la paleta viva; el dibujo cambia con
 * el público y con el rayo (destello con luces, sobre el carril de la última Note). */
static bool bolt_on(const StageState *s) { return s->flash && !s->lights_off; }

static bool same_state(const StageState *a, const StageState *b)
{
  return a->crowd_state == b->crowd_state && bolt_on(a) == bolt_on(b) &&
         (!bolt_on(a) || a->bolt_lane == b->bolt_lane);
}

/* Copia en la paleta viva los colores de la luz actual, si cambió. */
static u8 s_live_src = 0xFF;
static void live_palette(const StageState *st)
{
  const u8 src = stg_light_pal(&s_geom, st);
  u8 c;
  if (src == s_live_src) return;
  s_live_src = src;
  for (c = 0; c < 16; c++)
    PALETTE_RAM[STAGE_LIVE_PAL * 16 + c] = gfx_palettes[src][c];
}

void stage_draw_reset(void) { s_valid = false; s_live_src = 0xFF; }

bool stage_draw(const StageState *st, u8 nplayers, const HwyView *views, u8 nviews)
{
  if (!s_geom_ready) geom_init();
  live_palette(st);
  if (s_valid && s_age < STAGE_REBUILD && nplayers == s_last_np && same_state(st, &s_last) &&
      g_spr.pool_cur[SPR_CLASS_STAGE] == 0) {
    g_spr.pool_cur[SPR_CLASS_STAGE] = s_count;
    s_age++;
    return false;
  }
  stg_build(&s_list, &s_geom, st, nplayers, highway_geom(), views, nviews, highway_list());
  stg_apply(&s_list, &g_spr);
  s_count = g_spr.pool_cur[SPR_CLASS_STAGE];
  s_last = *st;
  s_last_np = nplayers;
  s_age = 0;
  s_valid = true;
  return true;
}
