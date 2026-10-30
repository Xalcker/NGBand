/* Layout puro del Stage dibujado. Ver stage_layout.h. */
#include "stage_layout.h"

#define TILE        16
#define CROWD_Y     192
#define CROWD_JUMP  6      /* píxeles que sube el público al saltar */

static void lines_clear(StageList *l)
{
  u32 *w = (u32 *)l->line_cnt;
  u16 k = sizeof l->line_cnt / 4;
  while (k--) *w++ = 0;
}

/* Mientras la cota de la línea más llena del Highway (al principio, su total de sprites) más los sprites del
 * Stage ya admitidos no lleguen al presupuesto, ninguna línea puede llenarse y no se cuenta nada línea por
 * línea (contar era lo más caro del Stage en el 68000). Si se llega, se cuenta todo y se sigue exacto. */
static void list_clear(StageList *l, const HwyList *hwy)
{
  u16 bound = 0;
  u8 p;
  for (p = 0; p < HWY_MAX_PLAYERS; p++) bound = (u16)(bound + hwy->total[p]);
  l->n = 0;
  l->dropped = 0;
  l->exact = 0;
  l->hwy = hwy;
  l->hwy_max = bound > 255 ? 255 : (u8)bound;
}

/* Cuentas exactas: el uso por línea del Highway y los sprites del Stage ya admitidos. */
static void go_exact(StageList *l)
{
  u16 ln;
  u8 p, umax = 0;
  hwy_count_lines((HwyList *)l->hwy);
  for (ln = 0; ln < HWY_SCREEN_LINES; ln++) {
    u16 sum = 0;
    for (p = 0; p < HWY_MAX_PLAYERS; p++) sum = (u16)(sum + l->hwy->line_cnt[p][ln]);
    l->used[ln] = sum > 255 ? 255 : (u8)sum;
    if (l->used[ln] > umax) umax = l->used[ln];
  }
  l->hwy_max = umax;
  stg_count_lines(l);
}

/* Admite un sprite si cabe en el pool y en todas sus líneas de barrido junto con el Highway. */
static bool admit(StageList *l, const u8 *hwy_used, s16 x, s16 y, u16 tile, u8 pal, u8 height, u8 flip)
{
  s32 lo, hi, ln;
  if (x + TILE <= 0 || x >= HWY_SCREEN_WIDTH) return false;
  if (y + height * TILE <= 0 || y >= HWY_SCREEN_LINES) return false;
  if (l->n >= STG_MAX_SPRITES) { l->dropped++; return false; }
  if (!l->exact) {
    if ((u16)l->hwy_max + l->n + 1 < HWY_LINE_BUDGET) goto keep;
    go_exact(l);
  }
  hwy_used = l->used;
  lo = y < 0 ? 0 : y;
  hi = (s32)y + height * TILE > HWY_SCREEN_LINES ? HWY_SCREEN_LINES : (s32)y + height * TILE;
  {
    u8 *c = &l->line_cnt[lo], *end = &l->line_cnt[hi];
    const u8 *u = &hwy_used[lo];
    for (; c < end; c++, u++) {
      if ((u16)*u + *c >= HWY_LINE_BUDGET) {
        while (c > &l->line_cnt[lo]) (*--c)--;
        l->dropped++;
        return false;
      }
      (*c)++;
    }
  }
  (void)ln;
keep:
  l->s[l->n].x = x;
  l->s[l->n].y = y;
  l->s[l->n].tile = tile;
  l->s[l->n].pal = pal;
  l->s[l->n].height = height;
  l->s[l->n].flip = flip;
  l->n++;
  return true;
}

/* La paleta que llevan las piezas iluminadas. */
static u8 lit_pal(const StageGeom *g, const StageState *st)
{
  return g->live_pal ? g->live_pal : stg_light_pal(g, st);
}

u8 stg_light_pal(const StageGeom *g, const StageState *st)
{
  if (st->lights_off) return (u8)(g->pal_base + STG_PAL_OFF);
  if (st->flash) return (u8)(g->pal_base + STG_PAL_FLASH);
  return (u8)(g->pal_base + (st->light_phase & 3) * 2 + (st->pulse ? 1 : 0));
}

/* Una pieza y su espejo en el lado derecho (x = ancho - 16 - x, flip horizontal invertido). */
static void admit_pair(StageList *l, const u8 *u, s16 x, s16 y, u16 tile, u8 pal, u8 height, u8 flip)
{
  admit(l, u, x, y, tile, pal, height, flip);
  admit(l, u, (s16)(HWY_SCREEN_WIDTH - TILE - x), y, tile, pal, height, (u8)(flip ^ 1));
}

/* R11.6: el rayo baja por el carril de la última Note, del horizonte a la línea de golpe. */
static void add_bolt(StageList *l, const u8 *u, const StageGeom *g, const StageState *st,
                     const HwyGeom *geom, const HwyView *views, u8 nviews)
{
  u8 v;
  u16 y;
  if (!st->flash || st->lights_off || !geom->nrows) return;
  for (v = 0; v < nviews; v++) {
    u8 k = 0;
    for (y = geom->rows[0].y; y <= geom->rows[geom->hit_row].y; y = (u16)(y + TILE), k++) {
      u16 row = (u16)(y - geom->rows[0].y);
      s16 x = (s16)(hwy_lane_x(geom, &views[v], row, st->bolt_lane) - TILE / 2);
      admit(l, u, x, (s16)y, g->bolt, lit_pal(g, st), 1, (u8)(k & 1));
    }
  }
}

/* Torres con foco y haces. En 1 jugador, una torre a cada lado; en 2, una central con dos focos
 * entre los Highways (R11.8). */
static void add_towers(StageList *l, const u8 *u, const StageGeom *g, u8 lamp_pal, u8 nplayers)
{
  u8 i;
  if (nplayers >= 2) {
    s16 cx = HWY_SCREEN_WIDTH / 2 - TILE / 2;
    admit(l, u, (s16)(cx - TILE), 8, g->lamp, lamp_pal, 1, 0);
    admit(l, u, (s16)(cx + TILE), 8, g->lamp, lamp_pal, 1, 1);
    for (i = 0; i < 4; i++) admit(l, u, cx, (s16)(40 + i * 32), g->truss, g->pal_base, 2, 0);
    return;
  }
  /* torre izquierda en x=40 (la derecha es su espejo) */
  admit_pair(l, u, 40, 16, g->lamp, lamp_pal, 1, 0);
  admit_pair(l, u, 40, 32, g->truss, g->pal_base, 2, 0);
}

static void add_beams(StageList *l, const u8 *u, const StageGeom *g, u8 lamp_pal, u8 nplayers)
{
  if (nplayers >= 2) {
    admit_pair(l, u, 120, 40, g->beam, lamp_pal, 2, 0);
    return;
  }
  admit_pair(l, u, 24, 48, g->beam, lamp_pal, 2, 0);    /* hacia el borde de la pantalla */
  admit_pair(l, u, 8, 80, g->beam, lamp_pal, 2, 0);
  admit_pair(l, u, 56, 48, g->beam, lamp_pal, 2, 1);    /* hacia el Highway, sin pasar de su borde */
  admit_pair(l, u, 72, 80, g->beam, lamp_pal, 2, 1);
}

/* R11.2, R11.3: quieto; con brazos arriba; y al saltar sube CROWD_JUMP píxeles. */
static void add_crowd(StageList *l, const u8 *u, const StageGeom *g, const StageState *st, u8 nplayers)
{
  u8 i;
  u16 tile = st->crowd_state == CROWD_QUIETO ? g->crowd : g->crowd_arms;
  s16 y = (s16)(st->crowd_state == CROWD_SALTO ? CROWD_Y - CROWD_JUMP : CROWD_Y);
  u8 pal = lit_pal(g, st);
  if (nplayers >= 2) return;      /* los dos Highways ocupan todo el ancho de la pantalla */
  for (i = 0; i < 3; i++) admit_pair(l, u, (s16)(i * TILE), y, tile, pal, 2, 0);
}

static void add_speakers(StageList *l, const u8 *u, const StageGeom *g, u8 nplayers)
{
  u8 c, r;
  if (nplayers >= 2) return;
  for (r = 0; r < 2; r++)
    for (c = 0; c < 2; c++)
      admit_pair(l, u, (s16)(c * TILE), (s16)(112 + r * 32), g->speaker, g->pal_base, 2, 0);
}

void stg_build(StageList *l, const StageGeom *g, const StageState *st, u8 nplayers,
               const HwyGeom *geom, const HwyView *views, u8 nviews, const HwyList *hwy)
{
  u8 lamp_pal = lit_pal(g, st);
  const u8 *used = l->used;            /* se llena solo si hace falta (go_exact) */
  list_clear(l, hwy);
  add_bolt(l, used, g, st, geom, views, nviews);
  add_towers(l, used, g, lamp_pal, nplayers);
  add_beams(l, used, g, lamp_pal, nplayers);
  add_crowd(l, used, g, st, nplayers);
  add_speakers(l, used, g, nplayers);
}

void stg_count_lines(StageList *l)
{
  u16 i;
  if (l->exact) return;
  lines_clear(l);
  for (i = 0; i < l->n; i++) {
    const StageSprite *s = &l->s[i];
    s16 lo = s->y < 0 ? 0 : s->y;
    s16 hi = (s16)(s->y + s->height * TILE);
    if (hi > HWY_SCREEN_LINES) hi = HWY_SCREEN_LINES;
    for (; lo < hi; lo++) l->line_cnt[lo]++;
  }
  l->exact = 1;
}

void stg_apply(const StageList *l, SpriteShadow *sh)
{
  u16 i;
  for (i = 0; i < l->n; i++) {
    const StageSprite *s = &l->s[i];
    int idx = spr_pool_alloc(sh, SPR_CLASS_STAGE);
    if (idx < 0) continue;
    spr_set(sh, (u16)idx, s->x, s->y, s->tile, s->pal, 15, 255, s->height, s->flip);
  }
}
