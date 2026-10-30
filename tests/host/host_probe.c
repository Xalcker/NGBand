/* Sonda del arnés: expone tamaños de los tipos comunes para comprobar que
 * el diseño de memoria visto desde Python coincide con el de C. */
#include "gameplay.h"
#include "probe.h"
#include "stage_layout.h"   /* _Static_assert del diseño de ChartCursor que usa tests/autoplay.lua */

TestProbe g_probe;
ChartCursor g_cursor[2];

u32 ngb_sizeof_judge_state(void) { return (u32)sizeof(JudgeState); }
u32 ngb_sizeof_pad_input(void)   { return (u32)sizeof(PadInput); }
u32 ngb_sizeof_chart_ev(void)    { return (u32)sizeof(ChartEv); }
u32 ngb_sizeof_chart(void)       { return (u32)sizeof(Chart); }

/* ---- Stage dibujado (stage_layout.c): una escena sintética, sin datos generados ---- */
#define PROBE_ROWS 177
static HwyRow s_rows[PROBE_ROWS];
static HwyList s_hwy;
static StageList s_stg;
static const StageGeom s_sgeom = { 100, 101, 102, 103, 104, 105, 106, 20, 0 };   /* sin paleta viva */

u8 ngb_stage_pal(u8 phase, u8 pulse, u8 flash, u8 off)
{
  StageState st = { 0 };
  st.light_phase = phase; st.pulse = pulse; st.flash = flash; st.lights_off = off != 0;
  return stg_light_pal(&s_sgeom, &st);
}

/* Arma el Stage sobre un Highway que ya usa `hwy_fill` sprites en cada línea del jugador 0.
 * lines_out[224] = sprites del Stage por línea; devuelve n | dropped << 16. */
u32 ngb_stage_probe(u8 nplayers, u8 hwy_fill, u8 flash, u8 bolt_lane, u8 crowd, u8 off,
                    u8 *lines_out, u16 *first_x)
{
  HwyGeom g;
  HwyView v[2];
  StageState st = { 0 };
  u16 i;
  u8 p;
  for (i = 0; i < PROBE_ROWS; i++) {
    int w = 80 + 120 * (int)i / 136, k;
    s_rows[i].y = (u16)(48 + i);
    for (k = 0; k < HWY_LANES; k++) s_rows[i].x_lane[k] = (s16)(160 + (k - 2) * w / 5);
  }
  for (i = 0; i < sizeof g; i++) ((u8 *)&g)[i] = 0;
  g.rows = s_rows; g.nrows = PROBE_ROWS; g.hit_row = 136; g.x_center = 160;
  for (i = 0; i < sizeof v; i++) ((u8 *)v)[i] = 0;
  for (p = 0; p < 2; p++) {
    v[p].player = p; v[p].nplayers = nplayers; v[p].ncols = 5; v[p].xscale = nplayers == 2 ? 192 : 256;
    v[p].x_origin = nplayers == 2 ? (p ? 240 : 80) : 160;
  }
  for (i = 0; i < sizeof s_hwy; i++) ((u8 *)&s_hwy)[i] = 0;
  for (i = 0; i < HWY_SCREEN_LINES; i++) s_hwy.line_cnt[0][i] = hwy_fill;
  s_hwy.exact[0] = s_hwy.exact[1] = true;   /* line_cnt ya está lleno a mano */
  s_hwy.total[0] = hwy_fill;                /* al menos `fill` sprites (los de una línea) */
  st.crowd_state = crowd; st.flash = flash; st.bolt_lane = bolt_lane; st.lights_off = off != 0;
  stg_build(&s_stg, &s_sgeom, &st, nplayers, &g, v, nplayers, &s_hwy);
  stg_count_lines(&s_stg);
  for (i = 0; i < HWY_SCREEN_LINES; i++) lines_out[i] = s_stg.line_cnt[i];
  *first_x = s_stg.n ? (u16)s_stg.s[0].x : 0;
  return (u32)s_stg.n | ((u32)s_stg.dropped << 16);
}
