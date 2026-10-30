/* Layout puro del Perspective_Highway. Ver highway_layout.h. */
#include "highway_layout.h"

#define KICK_LANE      4     /* batería: el bombo es el carril naranja (bit 4) */
#define TAIL_W_DIV     3     /* la cola mide 1/3 del ancho de la gema de su fila */
#define MAX_BEATS      32

/* Columna de cada carril del Chart en batería: verde, rojo, amarillo y azul (R4.2). */
static const s8 drum_cols[HWY_LANES] = { 3, 0, 1, 2, -1 };

typedef struct {
  u8  lane;
  bool open_end;     /* sin fin conocido: llega al horizonte */
  s16 dt0, dt1;      /* cuadros respecto a `now` del inicio y del fin */
} Tail;

/* ---- utilidades ---- */

u8 hwy_player_budget(const HwyView *v)
{
  u8 total = v->line_budget ? v->line_budget : HWY_LINE_BUDGET;
  u8 n = v->nplayers ? v->nplayers : 1;
  return (u8)(total / n);
}

void hwy_sprite_lines(const HwySprite *s, s16 *top, u16 *count)
{
  /* Una fila de tiles (16 px) reducida a (vshrink+1)/256 de su alto, redondeada hacia arriba. */
  *top = s->y;
  *count = (u16)(((u16)s->vshrink + 1u + 15u) / 16u);
}

/* Solo los contadores: los sprites s[0..n) se escriben antes de leerse. Las cuentas por línea se borran
 * de a 32 bits (es lo que más pesa en el 68000). */
static void zero_words(void *p, u16 bytes)
{
  u32 *w = (u32 *)p;
  u16 n = (u16)(bytes / 4);
  while (n--) *w++ = 0;
}

void hwy_list_begin(HwyList *l)
{
  l->n = 0;
  l->dropped = 0;
  zero_words(l->used, sizeof l->used);
  zero_words(l->line_cnt, sizeof l->line_cnt);
  l->total[0] = l->total[1] = 0;
  l->exact[0] = l->exact[1] = false;
}

static void sprite_span(const HwySprite *s, s32 *lo, s32 *hi)
{
  s16 top;
  u16 cnt;
  hwy_sprite_lines(s, &top, &cnt);
  *lo = top < 0 ? 0 : top;
  *hi = (s32)top + cnt > HWY_SCREEN_LINES ? HWY_SCREEN_LINES : (s32)top + cnt;
}

/* Suma a line_cnt los sprites del jugador p que no estaban contados. */
static void count_player(HwyList *l, u8 p)
{
  u16 i;
  for (i = 0; i < l->n; i++) {
    HwySprite *s = &l->s[i];
    s32 lo, hi;
    u8 *c, *end;
    if (s->player != p || s->counted) continue;
    sprite_span(s, &lo, &hi);
    for (c = &l->line_cnt[p][lo], end = &l->line_cnt[p][hi]; c < end; c++) (*c)++;
    s->counted = 1;
  }
  l->exact[p] = true;
}

void hwy_count_lines(HwyList *l)
{
  u8 p;
  for (p = 0; p < HWY_MAX_PLAYERS; p++)
    if (!l->exact[p]) count_player(l, p);
}

static u8 fall_of(const HwyView *v) { return v->fall_frames ? v->fall_frames : 4; }

/* Fila de perspectiva de una Note a `dt` cuadros de la línea de golpe (R5.8: 8 px cada fall_frames). */
static s32 row_of(const HwyGeom *g, const HwyView *v, s32 dt)
{
  /* |dt| <= 4000 basta para cualquier fila visible; así dt*8 cabe en 16 bits y la división es divs */
  s16 d = (s16)(dt > 4000 ? 4000 : dt < -4000 ? -4000 : dt);
  return (s32)g->hit_row - (s16)((s16)(d * 8) / (s16)fall_of(v));
}

/* Multiplicación 16x16 -> 32 (una instrucción muls en el 68000, sin la rutina de 32 bits). */
static s32 mul16(s16 a, s16 b) { return (s32)a * (s32)b; }

static s32 clampi(s32 x, s32 lo, s32 hi) { return x < lo ? lo : (x > hi ? hi : x); }

/* -1 si el carril no se dibuja como columna (bombo, o fuera de las columnas). */
static int lane_col(const HwyView *v, u8 lane)
{
  if (v->drums) return lane < HWY_LANES ? drum_cols[lane] : -1;
  if (lane >= v->ncols) return -1;
  return v->mirror ? (int)v->ncols - 1 - lane : lane;
}

static s32 span_of(const HwyRow *r) { return (s32)r->x_lane[4] - r->x_lane[0]; }

static s32 center_x(const HwyGeom *g, const HwyView *v, const HwyRow *r)
{
  return v->x_origin + mul16((s16)(r->x_lane[2] - g->x_center), (s16)v->xscale) / 256;
}

/* X central de la columna `col` en una fila: columnas centradas, con la separación de la tabla. */
static s32 col_x(const HwyGeom *g, const HwyView *v, const HwyRow *r, int col)
{
  s32 off = mul16((s16)(2 * col - ((s16)v->ncols - 1)), (s16)span_of(r)) / 8;
  return center_x(g, v, r) + mul16((s16)off, (s16)v->xscale) / 256;
}

s16 hwy_lane_x(const HwyGeom *g, const HwyView *v, u16 row, u8 lane)
{
  const HwyRow *r;
  int col;
  if (row >= g->nrows) return v->x_origin;
  r = &g->rows[row];
  col = lane_col(v, lane);
  return (s16)(col < 0 ? center_x(g, v, r) : col_x(g, v, r, col));
}

/* Admite un sprite si cabe en el pool del jugador y en todas sus líneas de barrido (R5.6). */
static bool admit(HwyList *l, const HwyView *v, u8 cls, s16 x, s16 y, u16 tile, u8 pal,
                  u8 hs, u8 vs)
{
  HwySprite t;
  s16 top;
  u16 cnt;
  s32 lo, hi;
  u8 p = v->player < HWY_MAX_PLAYERS ? v->player : 0;
  u8 shift = v->nplayers >= 2 ? 1 : 0;          /* 1 o 2 jugadores: dividir es un corrimiento */
  u8 budget = (u8)((v->line_budget ? v->line_budget : HWY_LINE_BUDGET) >> shift);
  t.x = x; t.y = y; t.tile = tile; t.pal = pal; t.hshrink = hs; t.vshrink = vs; t.cls = cls;
  t.player = p; t.counted = 0;
  hwy_sprite_lines(&t, &top, &cnt);
  if ((s32)x + hs + 1 <= 0 || x >= HWY_SCREEN_WIDTH) return false;   /* fuera de pantalla */
  if ((s32)top + cnt <= 0 || top >= HWY_SCREEN_LINES) return false;
  if (l->n >= HWY_MAX_SPRITES || l->used[p][cls] >= (spr_class_size(cls) >> shift)) {
    l->dropped++;
    return false;
  }
  if (!l->exact[p] && l->total[p] < budget) {
    /* con menos sprites que el presupuesto ninguna línea puede llenarse: no hace falta contar */
  } else {
    u8 *c, *end;
    if (!l->exact[p]) count_player(l, p);
    lo = top < 0 ? 0 : top;
    hi = (s32)top + cnt > HWY_SCREEN_LINES ? HWY_SCREEN_LINES : (s32)top + cnt;
    /* una sola pasada: cuenta y, si alguna línea ya estaba llena, deshace */
    for (c = &l->line_cnt[p][lo], end = &l->line_cnt[p][hi]; c < end; c++) {
      if (*c >= budget) {
        while (c > &l->line_cnt[p][lo]) (*--c)--;
        l->dropped++;
        return false;
      }
      (*c)++;
    }
    t.counted = 1;
  }
  l->s[l->n++] = t;
  l->used[p][cls]++;
  l->total[p]++;
  return true;
}
/* ---- gemas y bombo ---- */

static void add_kick(HwyList *l, const HwyGeom *g, const HwyView *v, s32 row)
{
  const HwyRow *r = &g->rows[row];
  u8 level = g->row_level[row];
  u8 hs = r->hshrink;
  u8 vs = g->gem_vshrink[level];
  s32 w = (s32)hs + 1;
  s32 total = mul16((s16)(v->ncols * (span_of(r) / 4)), (s16)v->xscale) / 256;
  s32 n = (total + w - 1) / w;
  s32 left, i, h = ((s32)vs + 16) / 16;
  if (n > HWY_MAX_BAR_SPR) n = HWY_MAX_BAR_SPR;
  left = center_x(g, v, r) - (n * w) / 2;
  for (i = 0; i < n; i++)
    admit(l, v, HWY_CLS_GEM, (s16)(left + i * w), (s16)((s32)r->y - h / 2), g->gem_tile[level],
          g->lane_pal[KICK_LANE], hs, vs);
}

static void add_gem(HwyList *l, const HwyGeom *g, const HwyView *v, u8 lane, s32 dt, u8 flags)
{
  s32 row = row_of(g, v, dt);
  const HwyRow *r;
  u8 level, hs, vs;
  int col;
  bool cymbal, star;
  s32 h;
  if (row < 0 || row >= g->nrows) return;
  if (v->drums && lane == KICK_LANE) { add_kick(l, g, v, row); return; }
  col = lane_col(v, lane);
  if (col < 0) return;
  r = &g->rows[row];
  level = g->row_level[row];
  hs = g->gem_hshrink[level];
  vs = g->gem_vshrink[level];
  h = ((s32)vs + 16) / 16;
  /* En batería el bit de cola del Chart marca el platillo (rombo en experto, tom en las demás). */
  cymbal = v->drums && v->expert && (flags & CHART_FLAG_SUSTAIN);
  star = (flags & CHART_FLAG_STAR) != 0;
  admit(l, v, HWY_CLS_GEM, (s16)(col_x(g, v, r, col) - ((s32)hs + 1) / 2), (s16)((s32)r->y - h / 2),
        cymbal ? g->cymbal_tile : g->gem_tile[level], star ? g->star_pal : g->lane_pal[lane], hs, vs);
}

/* ---- colas de Sustain (R5.4) ---- */

static void add_tail(HwyList *l, const HwyGeom *g, const HwyView *v, const Tail *t)
{
  int col = lane_col(v, t->lane);
  s32 r0 = row_of(g, v, t->dt0);
  s32 r1 = t->open_end ? 0 : row_of(g, v, t->dt1);
  s32 y_b, y_top;
  u8 pal;
  if (col < 0) return;
  if (r0 > (s32)g->hit_row) r0 = g->hit_row;          /* la cola no pasa de la línea de golpe */
  if (r0 >= g->nrows) r0 = (s32)g->nrows - 1;
  if (r1 < 0) r1 = 0;
  if (r0 < 0 || r1 >= r0) return;
  pal = v->star_active ? g->blue_pal : g->lane_pal[t->lane];
  y_b = g->rows[r0].y;
  y_top = g->rows[r1].y;
  while (y_b > y_top) {
    s32 seg = y_b - y_top;
    s32 idx;
    const HwyRow *r;
    u8 hs, vs;
    s32 w;
    if (seg > 16) seg = 16;
    idx = clampi(y_b - seg / 2 - g->rows[0].y, 0, (s32)g->nrows - 1);
    r = &g->rows[idx];
    hs = (u8)((((s32)r->hshrink + 1) / TAIL_W_DIV) > 0 ? (((s32)r->hshrink + 1) / TAIL_W_DIV) - 1 : 0);
    vs = (u8)(seg * 16 - 1);
    w = (s32)hs + 1;
    admit(l, v, HWY_CLS_TAIL, (s16)(col_x(g, v, r, col) - w / 2), (s16)(y_b - seg), g->tail_tile, pal,
          hs, vs);
    y_b -= seg;
  }
}

/* ---- líneas de tiempo (R5.5) ---- */

static void add_lines(HwyList *l, const HwyGeom *g, const HwyView *v, u16 now)
{
  u32 beat = v->beat_frames;
  u32 past, fut, lo, k, f;
  u8 pal;
  int n = 0;
  if (!beat) return;
  past = ((u32)(g->nrows - 1 - g->hit_row) * fall_of(v)) / 8;
  fut = ((u32)g->hit_row * fall_of(v)) / 8;
  lo = now > past ? now - past : 0;
  pal = v->star_active ? g->blue_pal : g->line_pal;
  for (k = (lo + beat - 1) / beat; n < MAX_BEATS; k++, n++) {
    s32 row;
    const HwyRow *r;
    u8 hs, vs;
    s32 thick, w;
    int c;
    f = k * beat;
    if (f > (u32)now + fut) break;
    row = row_of(g, v, (s32)f - (s32)now);
    if (row < 0 || row >= g->nrows) continue;
    r = &g->rows[row];
    hs = r->hshrink;
    thick = 1 + r->vshrink / 128;
    vs = (u8)(thick * 16 - 1);
    w = (s32)hs + 1;
    for (c = 0; c < v->ncols; c++)
      admit(l, v, HWY_CLS_LINE, (s16)(col_x(g, v, r, c) - w / 2), r->y, g->line_tile, pal, hs, vs);
  }
}

/* ---- armado ---- */

void hwy_build(HwyList *l, const HwyGeom *g, const HwyView *v, const Chart *chart,
               const ChartCursor *cur, u16 now)
{
  Tail tails[HWY_MAX_TAILS];
  int ntails = 0;
  int open[HWY_LANES];
  u8 lane, i;
  s32 max_dt, ev_i;
  u16 frame;
  u8 mask = v->lane_mask;

  for (lane = 0; lane < HWY_LANES; lane++) open[lane] = -1;

  /* Notas por acertar, ya leídas por el Judge (dentro de la Hit_Window). */
  for (i = 0; i < cur->count; i++) {
    u8 k = (u8)(cur->head + i);      /* head e i < 24: sin módulo (en el 68000 es una división de 32 bits) */
    const PendingNote *n;
    if (k >= 24) k = (u8)(k - 24);
    n = &cur->q[k];
    s16 dt = (s16)(n->frame - now);
    for (lane = 0; lane < HWY_LANES; lane++) {
      if (!((n->open >> lane) & 1) || !((mask >> lane) & 1)) continue;
      add_gem(l, g, v, lane, dt, n->flags);
      if (!v->drums && (n->flags & CHART_FLAG_SUSTAIN) && ntails < HWY_MAX_TAILS) {
        Tail *t = &tails[ntails];
        t->lane = lane;
        t->dt0 = dt;
        t->open_end = n->end == 0;
        t->dt1 = n->end ? (s16)(n->end - now) : 0;
        open[lane] = t->open_end ? ntails : -1;
        ntails++;
      }
    }
  }

  /* Colas que se están sosteniendo: se van comiendo desde la línea de golpe. */
  if (!v->drums) {
    for (lane = 0; lane < HWY_LANES && ntails < HWY_MAX_TAILS; lane++) {
      if (!((cur->hold_lanes >> lane) & 1) || !((mask >> lane) & 1)) continue;
      if (cur->hold_end[lane] != 0xFFFFu && (s16)(cur->hold_end[lane] - now) <= 0) continue;
      tails[ntails].lane = lane;
      tails[ntails].dt0 = 0;
      tails[ntails].open_end = cur->hold_end[lane] == 0xFFFFu;
      tails[ntails].dt1 = tails[ntails].open_end ? 0 : (s16)(cur->hold_end[lane] - now);
      if (tails[ntails].open_end) open[lane] = ntails;
      ntails++;
    }
  }

  /* Eventos que el Judge aún no lee, hasta el horizonte. */
  max_dt = ((s32)g->hit_row * fall_of(v)) / 8 + fall_of(v);
  frame = cur->frame;
  for (ev_i = cur->index; !cur->done && ev_i < chart->count && ev_i < (s32)cur->index + HWY_LOOKAHEAD_EV; ev_i++) {
    const ChartEv *ev = &chart->ev[ev_i];
    s16 dt;
    u8 lanes;
    if (ev->lanes == CHART_EV_END) break;
    frame = (u16)(frame + ev->delta_lo);
    dt = (s16)(frame - now);
    if (dt > max_dt) break;
    if (ev->lanes & CHART_FLAG_END) {
      for (lane = 0; lane < HWY_LANES; lane++) {
        if (((ev->lanes >> lane) & 1) && open[lane] >= 0) {
          tails[open[lane]].open_end = false;
          tails[open[lane]].dt1 = dt;
          open[lane] = -1;
        }
      }
      continue;
    }
    lanes = (u8)(ev->lanes & CHART_LANE_MASK & mask);
    for (lane = 0; lane < HWY_LANES; lane++) {
      if (!((lanes >> lane) & 1)) continue;
      add_gem(l, g, v, lane, dt, ev->lanes);
      if (!v->drums && (ev->lanes & CHART_FLAG_SUSTAIN) && ntails < HWY_MAX_TAILS) {
        tails[ntails].lane = lane;
        tails[ntails].dt0 = dt;
        tails[ntails].open_end = true;
        tails[ntails].dt1 = 0;
        open[lane] = ntails++;
      }
    }
  }

  /* Prioridad: gemas (arriba), colas de cerca a lejos y al final las líneas de tiempo. */
  for (i = 0; i < ntails; i++) add_tail(l, g, v, &tails[i]);
  add_lines(l, g, v, now);
}

void hwy_apply(const HwyList *l, SpriteShadow *sh)
{
  u16 i;
  for (i = 0; i < l->n; i++) {
    const HwySprite *s = &l->s[i];
    int idx = spr_pool_alloc(sh, s->cls);
    if (idx < 0) continue;
    spr_set(sh, (u16)idx, s->x, s->y, s->tile, s->pal, s->hshrink, s->vshrink, 1, 0);
  }
}
