/* Escena de juego: un paso por cuadro de video que conecta Input, Judge, Highway, HUD y audio (R2.10, R12.2). */
#include "game.h"
#include "audio_cmd.h"
#include "fix.h"
#include "gameplay.h"
#include "highway.h"
#include "hud.h"
#include "input.h"
#include "menu_logic.h"
#include "options.h"
#include "platform.h"
#include "probe.h"
#include "records.h"
#include "stage.h"
#include "stage_draw.h"
#include "track.h"
#include "spr.h"
#include "versus.h"

ChartCursor g_cursor[2];

#define ROW_MSG 12
#define COL_MSG 16

static const Song *s_song;
static const Chart *s_chart[2];
static JudgeState s_judge[2];      /* 1 jugador y VS */
static CoopState s_coop;           /* COOP (los dos JudgeState viven aquí) */
static u8 s_np;                    /* jugadores: 1 o 2 */
static u8 s_mode;                  /* RECORD_MODE_SOLO / VS / COOP */
static u8 s_inst[2], s_diff[2];
static StageState s_stage;
/* Flancos de un cuadro de video sin paso del Judge (velocidad 50% o 75%): esperan al siguiente paso. */
static u8 s_held_edge[2];
static bool s_held_power[2];
static StageInput s_stage_in;   /* eventos del cuadro de video; se acumulan entre los pasos del Judge */
static PlayClock s_clock;
static SpeedClock s_speed;
static HwyView s_view[2];
static bool s_drums[2];
static bool s_was_muted[2];
static bool s_started;      /* hay canción y Chart jugables */
static FxLimiter s_fxlim;   /* golpes al aire: máx. 3 efectos por segundo (R8.12) */
static u32 s_vframe;        /* cuadros de video desde play_enter, para el limitador */
static u8 s_red;            /* cuadros que le quedan al fondo rojo de EFECTO AL FALLAR */
static u16 s_backdrop;      /* color normal del fondo */
static bool s_prev_b[2];    /* B del cuadro anterior de cada control (para el flanco) */
static u16 s_total[2];      /* botones del Chart de cada jugador (para la precisión) */
static u8 s_stars;          /* estrellas de la partida (en COOP, las de la banda) */
static u8 s_stars_p[2];
static bool s_new_record;
static u16 s_hit_prev1;     /* notes_hit del jugador 2 en el cuadro anterior (rayo del Stage) */
static u8 s_winner;         /* VS_* */
static char s_vs_text[24];
static u32 s_record_score;
static bool s_hud_valid;     /* el HUD dibujado corresponde a s_hud[] */

/* Datos de la última partida (los lee la pantalla final y el Test_Harness vía ngband.sym). */
JudgeState g_result, g_result2;   /* jugador 1 y 2 (en COOP con el puntaje de la banda) */

static void zero(void *p, u16 n)
{
  u8 *b = (u8 *)p;
  while (n--) *b++ = 0;
}

/* Estado del Judge del jugador `p`. */
static JudgeState *J(u8 p)
{
  return s_mode == RECORD_MODE_COOP ? &s_coop.p[p] : &s_judge[p];
}

/* Chart de la selección; si el instrumento no tiene Chart en esa Difficulty prueba con los demás. */
static const Chart *pick_chart(const Song *song, u8 *instr, u8 diff)
{
  u8 i;
  const Chart *c = &song->chart[*instr & 3][diff & 3];
  if (c->ev) return c;
  for (i = 0; i < 4; i++) {
    c = &song->chart[i][diff & 3];
    if (c->ev) { *instr = i; return c; }
  }
  return 0;
}

static void msg(const char *s)
{
  fix_text(COL_MSG, ROW_MSG, s, 0, HUD_PAL_BLANCO);
}

void play_enter(void)
{
  static const u8 lanes_by_diff[4] = { 3, 4, 5, 5 };
  u8 lanes[2], p;
  s_started = false;
  fix_clear(&g_fix);
  s_mode = g_sel.players == MPLAY_VS ? RECORD_MODE_VS : g_sel.players == MPLAY_COOP ? RECORD_MODE_COOP : RECORD_MODE_SOLO;
  s_np = s_mode == RECORD_MODE_SOLO ? 1 : 2;
  s_song = ngband_num_songs ? ngband_songs[g_sel.song < ngband_num_songs ? g_sel.song : 0] : 0;
  if (!s_song) return;
  s_inst[0] = g_sel.instrument & 3;
  s_diff[0] = g_sel.difficulty & 3;
  s_inst[1] = g_sel.instrument2 & 3;
  s_diff[1] = s_mode == RECORD_MODE_COOP ? (g_sel.difficulty2 & 3) : s_diff[0];   /* en VS, la misma (R10.1) */
  for (p = 0; p < s_np; p++) {
    s_chart[p] = pick_chart(s_song, &s_inst[p], s_diff[p]);
    if (!s_chart[p]) return;
  }
  g_sel.instrument = s_inst[0];
  if (s_np == 2) g_sel.instrument2 = s_inst[1];
  for (p = 0; p < s_np; p++) {
    s_drums[p] = s_inst[p] == INST_DRUMS;
    lanes[p] = s_drums[p] ? 5 : lanes_by_diff[s_diff[p]];
    zero(&g_cursor[p], sizeof g_cursor[p]);           /* el cursor del Chart empieza en cero */
    s_held_edge[p] = 0;
    s_held_power[p] = false;
  }
  if (s_mode == RECORD_MODE_COOP) {
    coop_init(&s_coop, lanes[0], s_diff[0] == 0, g_sel.no_fail);
    s_coop.p[1].lanes = lanes[1];
    s_coop.p[1].easy = s_diff[1] == 0;
  } else {
    for (p = 0; p < s_np; p++) judge_init(&s_judge[p], lanes[p], s_diff[p] == 0, g_sel.no_fail);
  }
  stage_init(&s_stage);
  stage_draw_reset();
  s_hud_valid = false;
  zero(&s_stage_in, sizeof s_stage_in);
  clock_init(&s_clock);
  speed_init(&s_speed);
  for (p = 0; p < s_np; p++) {
    highway_view_init(&s_view[p], p, s_np, s_diff[p], s_drums[p], lanes[p]);
    s_view[p].mirror = g_sel.opt.mirror && !s_drums[p];   /* mismo criterio que la lectura del Judge */
    s_view[p].fall_frames = options_fall_frames(&g_sel.opt, s_diff[p]);
    s_view[p].beat_frames = 0;   /* sin líneas de tiempo con sprites: el movimiento lo dan las franjas de la pista */
    s_was_muted[p] = false;
    s_prev_b[p] = input_get(p)->prev_raw & PAD_B;
    s_total[p] = 0;
    s_stars_p[p] = 0;
  }
  track_show(s_view, s_np, g_sel.opt.speed_idx);   /* la superficie fija, una vez por canción */
  fxlim_init(&s_fxlim);
  s_vframe = 0;
  s_red = 0;
  s_backdrop = PALETTE_BACKDROP;
  s_stars = 0;
  s_new_record = false;
  s_hit_prev1 = 0;
  s_winner = VS_TIE;
  s_vs_text[0] = 0;
  s_record_score = 0;
  /* La música arranca al terminar el LEAD_IN: hasta entonces el stream no avanza (CMD_HOLD).
   * Lo que quedaba de la vista previa del Menu se descarta: atrasaría el audio respecto a la Chart. */
  ac_flush(&g_audio);
  ac_push(&g_audio, CMD_SILENCE_ALL, 0);
  ac_push(&g_audio, CMD_SONG_START, g_sel.song);
  s_started = true;
  g_probe.screen = PR_SCREEN_PLAY;
  g_probe.song_frame = 0;
  g_probe.paused = 0;
}

/* ESPEJO en la lectura del Judge: el botón físico de la columna c acierta el carril ncols-1-c,
 * que es lo que muestra el Highway con view.mirror. */
static PadInput judge_input(const PadState *pad, u8 p)
{
  PadInput in = pad->in;
  if (g_sel.opt.mirror && !s_drums[p]) {
    in.pressed = options_mirror_ev(in.pressed, J(p)->lanes, false);
    in.edge = options_mirror_ev(in.edge, J(p)->lanes, false);
  }
  return in;
}

/* Golpes al aire de este cuadro: cada flanco de carril o acierta una Note o es un golpe al aire. */
static u8 air_count(const JudgeState *j, PadInput in, u16 hit_before)
{
  u8 m = (u8)(in.edge & ((1u << j->lanes) - 1u));
  u8 n = 0;
  for (; m; m &= (u8)(m - 1)) n++;
  return (u8)(n - (u8)(j->notes_hit - hit_before));
}

/* EFECTO AL FALLAR (R8.11, R8.12): sonido (limitado) y fondo rojo. */
static void air_fx(u8 air)
{
  while (air--) {
    int fx = fxlim_air(&s_fxlim, s_vframe, (u8)(s_vframe + J(0)->notes_hit + J(s_np - 1)->notes_hit));
    if (fx < 0) continue;
    if (options_fail_sound(&g_sel.opt)) ac_push(&g_audio, CMD_SFX, (u8)fx);
    if (options_fail_shake_red(&g_sel.opt)) s_red = 6;
  }
}

static void red_tick(void)
{
  if (s_red) {
    PALETTE_BACKDROP = 0x0F00;       /* rojo */
    s_red--;
  } else {
    PALETTE_BACKDROP = s_backdrop;
  }
}

/* Un paso del Stage por cuadro de video, con lo ocurrido en los pasos del Judge de este cuadro. */
static void stage_frame(void)
{
  const JudgeState *a = J(0), *b = J(s_np - 1);
  bool hit2 = s_np == 2 && b->notes_hit != s_hit_prev1;
  s_stage_in.combo = s_np == 2 && s_mode == RECORD_MODE_VS && b->combo > a->combo ? b->combo : a->combo;
  s_stage_in.star_active = a->star_active || b->star_active;
  s_stage_in.all_failed = !g_sel.no_fail && a->failed && b->failed;
  s_stage_in.players = s_np;
  s_stage_in.last_lane = hit2 ? b->last_lane : a->last_lane;
  s_hit_prev1 = b->notes_hit;
  stage_step(&s_stage, &s_stage_in);
  s_stage_in.beat_tick = false;
  s_stage_in.phrase_done = false;
}

#ifdef NGBAND_EXP_TIMING
volatile u16 g_t[8];
#define TMARK(i) (g_t[i] = (u16)((*(volatile u16 *)0x3C0006) >> 7))
#else
#define TMARK(i) ((void)0)
#endif
/* Lo que muestra el HUD de un jugador: solo se redibuja si algo cambió (en el 68000 formatear y escribir
 * los cuatro renglones cada cuadro cuesta una cuarta parte del cuadro). */
typedef struct { u32 score; u16 combo; s16 life; u8 mult, star_bar; bool star_active, no_fail, failed; } HudKey;
static HudKey s_hud[2];

static bool hud_changed(u8 p, const JudgeState *j)
{
  HudKey k;
  k.score = j->score; k.combo = j->combo; k.life = j->life; k.mult = j->multiplier; k.star_bar = j->star_bar;
  k.star_active = j->star_active; k.no_fail = j->no_fail; k.failed = j->failed;
  if (s_hud_valid && k.score == s_hud[p].score && k.combo == s_hud[p].combo && k.life == s_hud[p].life &&
      k.mult == s_hud[p].mult && k.star_bar == s_hud[p].star_bar && k.star_active == s_hud[p].star_active &&
      k.no_fail == s_hud[p].no_fail && k.failed == s_hud[p].failed)
    return false;
  s_hud[p] = k;
  return true;
}

static void draw(void)
{
  const Chart *charts[2];
  const ChartCursor *curs[2];
  static bool s_hud_deferred;
  bool stage_rebuilt = false;
  u8 p;
  TMARK(0);
  spr_pool_begin(&g_spr);            /* el Stage comparte este pool */
  for (p = 0; p < s_np; p++) {
    charts[p] = s_chart[p];
    curs[p] = &g_cursor[p];
    s_view[p].star_active = J(p)->star_active;
  }
#ifndef NGBAND_EXP_NO_HWY
  highway_draw(s_view, s_np, charts, curs, s_clock.frame);
#endif
  TMARK(1);
#ifndef NGBAND_EXP_NO_STAGE
  stage_rebuilt = stage_draw(&s_stage, s_np, s_view, s_np);   /* con el presupuesto que el Highway deja libre */
#endif
  TMARK(2);
  spr_commit();
  TMARK(3);
  /* Si el Stage se rehízo (p. ej. el rayo al cerrar una frase estelar), el HUD espera un cuadro: juntos
   * (con lo que mandan a la VRAM) se pasaban del cuadro. Nunca dos cuadros seguidos. */
  if (stage_rebuilt && s_hud_valid && !s_hud_deferred) {
    s_hud_deferred = true;
  } else if (s_np == 1) {
    s_hud_deferred = false;
    if (hud_changed(0, &s_judge[0])) hud_draw(&g_fix, &s_judge[0]);
  } else {
    bool any = false;
    for (p = 0; p < 2; p++) {
      JudgeState v;
      if (s_mode == RECORD_MODE_COOP) coop_view(&s_coop, p, &v);
      else v = s_judge[p];
      if (hud_changed(p, &v)) { hud_draw2(&g_fix, &v, p); any = true; }
    }
    (void)any;
    s_hud_deferred = false;
  }
  s_hud_valid = true;
  TMARK(4);
  fix_flush();
  TMARK(5);
}

/* Botones del Chart que el Judge puede acertar con los carriles de esta partida. */
static u16 chart_total(const Chart *chart, u8 lanes)
{
  u16 i, total = 0;
  u8 lane_mask = (u8)((1u << lanes) - 1u);
  for (i = 0; i < chart->count; i++) {
    u8 l = chart->ev[i].lanes;
    u8 m;
    if (l == CHART_EV_END) break;
    if (l & CHART_FLAG_END) continue;
    for (m = l & CHART_LANE_MASK & lane_mask; m; m &= (u8)(m - 1)) total++;
  }
  return total;
}

static bool lost_of(const JudgeState *j) { return j->failed && !g_sel.no_fail; }

/* La partida terminó por vida: sola, VS (cualquiera) o COOP (los dos). */
static bool game_over(void)
{
  switch (s_mode) {
    case RECORD_MODE_VS:   return !g_sel.no_fail && vs_over(&s_judge[0], &s_judge[1]);
    case RECORD_MODE_COOP: return !g_sel.no_fail && coop_over(&s_coop);
    default:               return lost_of(&s_judge[0]);
  }
}

/* Estrellas, total y récord de la partida terminada (R9.5: solo partidas elegibles). */
static void finish_run(void)
{
  RecordRun run;
  u8 p, inst = s_inst[0], diff = s_diff[0];
  u32 perfect = s_song->perfect[inst][diff];
  for (p = 0; p < s_np; p++) {
    s_total[p] = chart_total(s_chart[p], J(p)->lanes);
    s_stars_p[p] = (u8)judge_stars(J(p)->score_base, s_song->perfect[s_inst[p]][s_diff[p]]);
  }
  if (s_mode == RECORD_MODE_COOP) {   /* la banda: puntaje compartido contra lo perfecto de los dos */
    perfect += s_song->perfect[s_inst[1]][s_diff[1]];
    s_stars = (u8)judge_stars(s_coop.score_base, perfect);
    s_record_score = s_coop.score;
  } else {
    s_stars = s_stars_p[0];
    s_record_score = g_result.score;
  }
  if (s_mode == RECORD_MODE_VS) {
    VsResult r = vs_result(&s_judge[0], &s_judge[1]);
    s_winner = r.outcome;
    vs_result_text(&r, s_vs_text, sizeof s_vs_text);
  }
  run.mode = s_mode;
  run.lost = lost_of(&g_result);
  run.p2_lost = s_np == 2 && lost_of(&g_result2);
  run.no_fail = g_sel.no_fail;
  run.mirror = g_sel.opt.mirror != 0;
  run.speed_default = g_sel.opt.speed_idx == SPEED_100;
  run.fall_default = g_sel.opt.fall_idx == 0;
  run.practice = g_sel.opt.practice != 0;
  s_new_record = record_submit(&run, s_song->title_hash, inst, diff, s_record_score, last_initials, s_stars);
}

static void fill_result(ProbeResult *r, const JudgeState *j, u16 total, u8 stars, bool new_record)
{
  r->score = j->score;
  r->hit = j->notes_hit;
  r->total = total;
  r->max_combo = j->max_combo;
  r->stars = stars;
  r->failed = lost_of(j);
  r->new_record = new_record;
}

/* Resultado de la partida para el Test_Harness (probe.h). */
static void probe_result(void)
{
  g_probe.screen = PR_SCREEN_RESULTS;
  fill_result(&g_probe.p1, &g_result, s_total[0], s_stars_p[0], s_new_record);
  if (s_np == 2) {
    JudgeState band = g_result;
    fill_result(&g_probe.p2, &g_result2, s_total[1], s_stars_p[1], false);
    if (s_mode == RECORD_MODE_COOP) {
      band.notes_hit = (u16)(g_result.notes_hit + g_result2.notes_hit);
      band.failed = g_result.failed && g_result2.failed;
      fill_result(&g_probe.band, &band, (u16)(s_total[0] + s_total[1]), s_stars, s_new_record);
    }
    g_probe.winner = s_winner;
  }
}

/* Estado de silencio por Instrument: si los dos tocan el mismo, suena mientras alguno lo toque bien. */
static void mute_sync(void)
{
  u8 p;
  for (p = 0; p < s_np; p++) {
    bool m = J(p)->muted;
    if (s_np == 2 && s_inst[0] == s_inst[1]) {
      if (p) break;
      m = J(0)->muted && J(1)->muted;
    }
    if (m != s_was_muted[p]) {
      ac_push(&g_audio, m ? CMD_MUTE_INST : CMD_UNMUTE_INST, s_inst[p]);
      s_was_muted[p] = m;
    }
  }
}

/* Un cuadro del Judge de todos los jugadores. `first` = primer paso del cuadro de video. */
static void judge_frame(const PadState *pads[2], PadInput in[2], bool first)
{
  u16 frame = s_clock.frame;
  u16 hit_before[2];
  bool was_failed[2];
  PadInput step_in[2];
  u8 p;
  for (p = 0; p < s_np; p++) {
    hit_before[p] = J(p)->notes_hit;
    was_failed[p] = J(p)->failed;
    step_in[p] = in[p];
    if (!first) step_in[p].edge = 0;          /* los flancos cuentan una sola vez por cuadro de video */
  }
  for (p = 0; p < s_np; p++) {
    bool star = first && (pads[p]->power_edge || s_held_power[p]);
    if (s_mode == RECORD_MODE_COOP) {
      if (star) coop_star_press(&s_coop, p);
      coop_step(&s_coop, p, s_chart[p], &g_cursor[p], step_in[p], frame);
    } else {
      if (star) judge_star_power(&s_judge[p]);
      judge_step(&s_judge[p], s_chart[p], &g_cursor[p], step_in[p], frame);
    }
  }
  s_clock.frame++;
  s_clock.stream_frame++;
  for (p = 0; p < s_np; p++) {
    if (J(p)->phrase_done) s_stage_in.phrase_done = true;
    if (!was_failed[p] && !J(p)->failed) air_fx(air_count(J(p), step_in[p], hit_before[p]));
  }
  if (stage_is_beat(frame, SONG_LEAD_IN, s_song->beat_frames)) s_stage_in.beat_tick = true;
}

Scene play_frame(void)
{
  const PadState *pads[2];
  PadInput in[2];
  bool was_paused = s_clock.paused;
  bool b_edge = false, start_edge;
  u8 steps, i, p, sent = 0;
  s_vframe++;

  pads[0] = input_get(0);
  pads[1] = input_get(1);
  if (!s_started) {
    msg("SIN CANCIONES");
    fix_flush();
    return pads[0]->pause_edge ? SCENE_END : SCENE_PLAY;
  }
  start_edge = false;
  for (p = 0; p < s_np; p++) {
    bool b = (pads[p]->prev_raw & PAD_B) != 0;
    if (b && !s_prev_b[p]) b_edge = true;
    s_prev_b[p] = b;
    if (pads[p]->pause_edge) start_edge = true;
    in[p] = judge_input(pads[p], p);
  }

  if (was_paused && b_edge && !start_edge) {   /* B en pausa vuelve al Menu (R3.10) */
    ac_push(&g_audio, CMD_SILENCE_ALL, 0);
    PALETTE_BACKDROP = s_backdrop;
    msg("      ");
    fix_flush();
    return SCENE_MENU;
  }
  if (start_edge) {                      /* Start alterna pausa y reanuda (R3.8, R3.9) */
    clock_toggle_pause(&s_clock);
    track_pause(s_clock.paused);
    ac_push(&g_audio, s_clock.paused ? CMD_PAUSE : CMD_RESUME, 0);
    msg(s_clock.paused ? "PAUSA " : "      ");
  } else if (!was_paused) {
    steps = speed_frame(&s_speed, g_sel.opt.speed_idx);
    for (p = 0; p < s_np; p++) in[p].edge |= s_held_edge[p];
    if (!steps) {   /* nada que juzgar en este cuadro: el toque cuenta en el siguiente paso */
      for (p = 0; p < s_np; p++) {
        s_held_edge[p] = in[p].edge;
        s_held_power[p] = s_held_power[p] || pads[p]->power_edge;
      }
    }
    for (i = 0; i < steps; i++) {
      if (s_clock.frame >= SONG_LEAD_IN) sent++;
      judge_frame(pads, in, i == 0);
    }
    if (steps)
      for (p = 0; p < s_np; p++) { s_held_edge[p] = 0; s_held_power[p] = false; }
    /* Un solo byte por VBlank: dos cuadros del stream en el mismo cuadro de video van en CMD_FRAME2. */
    if (sent >= 2) ac_push(&g_audio, CMD_FRAME2, 0);
    else if (sent == 1) ac_push(&g_audio, CMD_FRAME, 0);
    else ac_push(&g_audio, CMD_HOLD, 0);          /* el stream no avanza en este cuadro (R12.8) */
    mute_sync();
  }
  red_tick();
  if (!s_clock.paused) stage_frame();   /* en pausa el Stage queda congelado */
  draw();
  g_probe.song_frame = s_clock.frame;
  g_probe.paused = s_clock.paused;

  if (game_over() || s_clock.frame >= s_song->total_frames) {
    if (s_mode == RECORD_MODE_COOP) {
      coop_view(&s_coop, 0, &g_result);
      coop_view(&s_coop, 1, &g_result2);
    } else {
      g_result = s_judge[0];
      g_result2 = s_judge[s_np - 1];
    }
    PALETTE_BACKDROP = s_backdrop;
    finish_run();
    probe_result();
    return SCENE_END;
  }
  return SCENE_PLAY;
}

static void end_line(u8 col, u8 row, const char *label, const char *val, u8 pal)
{
  fix_text(col, row, label, 0, HUD_PAL_AMARILLO);
  fix_text((u8)(col + 11), row, val, 0, pal);
}

void end_enter(void)
{
  char buf[HUD_SCORE_DIGITS + 1];
  ac_push(&g_audio, CMD_SILENCE_ALL, 0);
  fix_clear(&g_fix);
  track_hide();
  spr_pool_begin(&g_spr);            /* sin altas: oculta el Highway del cuadro anterior */
  spr_commit();
  if (s_started) {
    u8 i;
    u16 hit = g_result.notes_hit, total = s_total[0];
    u8 pct;
    char stars[6];
    if (s_mode == RECORD_MODE_COOP) { hit = (u16)(hit + g_result2.notes_hit); total = (u16)(total + s_total[1]); }
    pct = total ? (u8)((u32)hit * 100u / total) : 0;
    if (s_mode == RECORD_MODE_VS) {
      msg(s_vs_text);
      for (i = 0; i < 2; i++) {
        const JudgeState *j = i ? &g_result2 : &g_result;
        hud_format_uint(buf, j->score, HUD_SCORE_DIGITS);
        fix_text(COL_MSG - 6, (u8)(ROW_MSG + 2 + i), i ? "J2 PUNTOS" : "J1 PUNTOS", 0, HUD_PAL_AMARILLO);
        fix_text(COL_MSG + 5, (u8)(ROW_MSG + 2 + i), buf, 0, HUD_PAL_BLANCO);
        fix_text(COL_MSG + 15, (u8)(ROW_MSG + 2 + i), lost_of(j) ? "CAIDO" : "     ", 0, HUD_PAL_ROJO);
      }
    } else {
      msg(s_mode == RECORD_MODE_COOP ? (coop_over(&s_coop) && !g_sel.no_fail ? "FALLARON" : "FIN")
                                     : (lost_of(&g_result) ? "FALLASTE" : "FIN"));
      fix_text(COL_MSG - 2, ROW_MSG + 2, "PUNTOS", 0, HUD_PAL_AMARILLO);
      hud_format_uint(buf, g_result.score, HUD_SCORE_DIGITS);
      fix_text(COL_MSG + 5, ROW_MSG + 2, buf, 0, HUD_PAL_BLANCO);
      fix_text(COL_MSG - 2, ROW_MSG + 3, "PRECISION", 0, HUD_PAL_AMARILLO);
      hud_format_uint(buf, pct, 3);
      buf[3] = '%'; buf[4] = 0;
      fix_text(COL_MSG + 8, ROW_MSG + 3, buf, 0, HUD_PAL_BLANCO);
      fix_text(COL_MSG - 2, ROW_MSG + 4, "COMBO MAX", 0, HUD_PAL_AMARILLO);
      hud_format_uint(buf, g_result.max_combo, HUD_COMBO_DIGITS);
      fix_text(COL_MSG + 8, ROW_MSG + 4, buf, 0, HUD_PAL_BLANCO);
      for (i = 0; i < 5; i++) stars[i] = i < s_stars ? '*' : '-';
      stars[5] = 0;
      fix_text(COL_MSG - 2, ROW_MSG + 5, "ESTRELLAS", 0, HUD_PAL_AMARILLO);
      fix_text(COL_MSG + 8, ROW_MSG + 5, stars, 0, HUD_PAL_BLANCO);
      if (s_mode == RECORD_MODE_COOP) {
        end_line(COL_MSG - 2, ROW_MSG + 6, "J1", lost_of(&g_result) ? "CAIDO" : "EN PIE",
                 lost_of(&g_result) ? HUD_PAL_ROJO : HUD_PAL_VERDE);
        end_line(COL_MSG - 2, ROW_MSG + 7, "J2", lost_of(&g_result2) ? "CAIDO" : "EN PIE",
                 lost_of(&g_result2) ? HUD_PAL_ROJO : HUD_PAL_VERDE);
      }
      if (s_new_record) fix_text(COL_MSG - 2, ROW_MSG + 8, "NUEVO RECORD", 0, HUD_PAL_VERDE);
    }
  }
  fix_text(COL_MSG - 4, ROW_MSG + 10, "START: CONTINUAR", 0, HUD_PAL_VERDE);
  fix_flush();
}

Scene end_frame(void)
{
  bool start = input_get(0)->pause_edge || (s_np == 2 && input_get(1)->pause_edge);
  fix_flush();
  if (!start) return SCENE_END;
  return s_started && s_new_record ? SCENE_INITIALS : SCENE_MENU;
}

bool results_new_record(void) { return s_new_record; }
u8 results_stars(void) { return s_stars; }
u32 results_record_score(void) { return s_record_score; }
