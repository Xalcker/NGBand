/* Escenas de título, Menu, Options_Screen y entrada de iniciales (R7, R8.1, R9). Todo el texto va en la
 * Fix_Layer; la lógica de navegación y edición está en menu_logic.c (se prueba en el host).
 *
 * Controles del Menu: ↑/↓ renglón (con vuelta), ←/→ valor, Start juega, A abre las opciones, B regresa al título.
 * Mientras se elige suena la canción seleccionada (se repite al terminar). */
#include "game.h"
#include "audio_cmd.h"
#include "fix.h"
#include "hud.h"
#include "input.h"
#include "menu_logic.h"
#include "platform.h"
#include "probe.h"
#include "records.h"
#include "spr.h"
#include "track.h"

#ifndef NGBAND_VERSION
#define NGBAND_VERSION "0"
#endif

_Static_assert(MROW_SONG == PR_ROW_SONG && MROW_INSTR == PR_ROW_INSTR && MROW_DIFF == PR_ROW_DIFF &&
               MROW_FAIL == PR_ROW_FAIL && MROW_PLAYERS == PR_ROW_PLAYERS && MROW_COUNT == PR_ROW_COUNT,
               "los renglones del Menu deben coincidir con probe.h");

#define COL_CURSOR 1
#define COL_LABEL  3
#define COL_VALUE  16
#define COL_VALUE2 29

/* ---- Controles: flancos de todos los botones del jugador 1 ---- */
static u16 s_prev_raw;

static u16 s_prev_raw2;   /* jugador 2: solo elige su Instrument y Difficulty en el Menu */

static void nav_sync(void)
{
  s_prev_raw = input_get(0)->prev_raw;
  s_prev_raw2 = input_get(1)->prev_raw;
}

static u16 nav_edges2(void)
{
  u16 raw = input_get(1)->prev_raw;
  u16 e = (u16)(raw & ~s_prev_raw2);
  s_prev_raw2 = raw;
  return e;
}

static u16 nav_edges(void)
{
  u16 raw = input_get(0)->prev_raw;
  u16 e = (u16)(raw & ~s_prev_raw);
  s_prev_raw = raw;
  return e;
}

static void sfx(u8 id) { ac_push(&g_audio, CMD_SFX, id); }

/* ---- Utilidades de texto ---- */
static void text_center(u8 row, const char *s, u8 pal)
{
  u8 n = 0;
  while (s[n]) n++;
  fix_text(n >= FIX_COLS ? 0 : (u8)((FIX_COLS - n) / 2), row, s, 0, pal);
}

/* Pantalla nueva: Fix_Layer vacía y sin sprites (el Highway del cuadro anterior). */
static void screen_reset(u16 code)
{
  fix_clear(&g_fix);
  track_hide();
  spr_pool_begin(&g_spr);
  spr_commit();
  nav_sync();
  g_probe.screen = code;
}

/* ---- Música de la canción elegida (título y Menu): se manda un CMD_FRAME por cuadro y, al
 * terminar el stream, vuelve a empezar. ---- */
static u16 s_pframe;
static bool s_playing;

static const Song *song_at(u8 i)
{
  return ngband_num_songs ? ngband_songs[i < ngband_num_songs ? i : 0] : 0;
}

static void preview_start(u8 song)
{
  ac_push(&g_audio, CMD_SILENCE_ALL, 0);
  s_pframe = 0;
  s_playing = song_at(song) != 0;
  if (s_playing) ac_push(&g_audio, CMD_SONG_START, song);
}

static void preview_stop(void)
{
  ac_push(&g_audio, CMD_SILENCE_ALL, 0);
  s_playing = false;
}

static void preview_tick(u8 song)
{
  const Song *sg = song_at(song);
  if (!s_playing || !sg) return;
  if (s_pframe >= sg->total_frames) { preview_start(song); return; }
  if (ac_pending(&g_audio) < 8) { ac_push(&g_audio, CMD_FRAME, 0); s_pframe++; }
}

/* ======================= Título ======================= */
void title_enter(void)
{
  screen_reset(PR_SCREEN_TITLE);
  text_center(8, "N G B A N D", HUD_PAL_AMARILLO);
  text_center(12, "UN JUEGO DE RITMO PARA NEO GEO", HUD_PAL_BLANCO);
  text_center(26, "NGBAND V" NGBAND_VERSION " - GPL-2.0", HUD_PAL_BLANCO);
  preview_start(0);        /* música del título: la primera canción, en bucle */
  fix_flush();
}

Scene title_frame(void)
{
  static u16 blink;
  u16 e = nav_edges();
  blink++;
  text_center(18, (blink % 60) < 40 ? "PRESIONA START" : "              ", HUD_PAL_VERDE);
  preview_tick(0);
  fix_flush();
  if (e & PAD_START) {
    sfx(SFX_ACCEPT);
    return SCENE_MENU;
  }
  return SCENE_TITLE;
}

/* ======================= Menu ======================= */
static MenuSel s_menu;
static u8 s_row2;   /* renglón del jugador 2 (M2ROW_*) */

static const u8 menu_y[MROW_COUNT] = { 5, 10, 12, 14, 16 };
#define MENU_RECORD_ROW 20

/* Bit i = la canción tiene Chart del instrumento i. */
static u8 avail_mask(u8 song)
{
  const Song *sg = song_at(song);
  u8 i, m = 0;
  if (!sg) return 1;
  for (i = 0; i < MENU_INSTRUMENTS; i++)
    if (sg->chart[i][0].ev) m |= (u8)(1u << i);
  return m ? m : 1;
}

static void menu_to_sel(void)
{
  g_sel.song = s_menu.song;
  g_sel.instrument = s_menu.instr;
  g_sel.difficulty = s_menu.diff;
  g_sel.no_fail = s_menu.no_fail;
  g_sel.players = s_menu.players;
  g_sel.instrument2 = s_menu.instr2;
  g_sel.difficulty2 = s_menu.diff2;
}

static void sel_to_menu(void)
{
  s_menu.song = g_sel.song;
  s_menu.instr = g_sel.instrument & 3;
  s_menu.diff = g_sel.difficulty & 3;
  s_menu.no_fail = g_sel.no_fail;
  s_menu.players = g_sel.players < MPLAY_COUNT ? g_sel.players : MPLAY_SOLO;
  s_menu.instr2 = g_sel.instrument2 & 3;
  s_menu.diff2 = g_sel.difficulty2 & 3;
  if (ngband_num_songs && s_menu.song >= ngband_num_songs) s_menu.song = 0;
}

/* Récord de la selección: "00029920 ABC *****" o "---"; también lo publica para el Test_Harness. */
static void draw_record(void)
{
  RecordEntry r;
  const Song *sg = song_at(s_menu.song);
  char buf[24];
  u8 i;
  g_probe.best_score = 0;
  for (i = 0; i < 3; i++) g_probe.best_ini[i] = 0;
  fix_text(COL_LABEL, MENU_RECORD_ROW, "RECORD", 0, HUD_PAL_AMARILLO);
  if (sg && record_get(sg->title_hash, s_menu.instr, s_menu.diff, &r)) {
    hud_format_uint(buf, r.score, HUD_SCORE_DIGITS);
    buf[HUD_SCORE_DIGITS] = ' ';
    for (i = 0; i < 3; i++) {
      buf[HUD_SCORE_DIGITS + 1 + i] = r.initials[i];
      g_probe.best_ini[i] = (u8)r.initials[i];
    }
    buf[HUD_SCORE_DIGITS + 4] = ' ';
    for (i = 0; i < 5; i++) buf[HUD_SCORE_DIGITS + 5 + i] = i < r.stars ? '*' : '-';
    buf[HUD_SCORE_DIGITS + 10] = 0;
    g_probe.best_score = r.score;
    fix_text(COL_VALUE, MENU_RECORD_ROW, buf, 0, HUD_PAL_BLANCO);
  } else {
    fix_text(COL_VALUE, MENU_RECORD_ROW, "---", 0, HUD_PAL_BLANCO);
  }
}

static void menu_draw(void)
{
  u8 r;
  const Song *sg = song_at(s_menu.song);
  bool two = s_menu.players != MPLAY_SOLO;
  fix_clear(&g_fix);
  text_center(3, "N G B A N D", HUD_PAL_AMARILLO);
  text_center(25, "START JUEGA  A OPCIONES  B REGRESA", HUD_PAL_VERDE);
  for (r = 0; r < MROW_COUNT; r++) {
    u8 y = menu_y[r], pal = r == s_menu.row ? HUD_PAL_AMARILLO : HUD_PAL_BLANCO;
    fix_text(COL_CURSOR, y, r == s_menu.row ? ">" : " ", 0, HUD_PAL_AMARILLO);
    fix_text(COL_LABEL, y, menu_row_label(r), 0, pal);
    switch (r) {
      case MROW_SONG:
        if (sg) {
          fix_text(COL_LABEL, (u8)(y + 1), sg->title, 0, pal);
          fix_text(COL_LABEL, (u8)(y + 2), sg->game, 0, HUD_PAL_AMARILLO);
        } else {
          fix_text(COL_LABEL, (u8)(y + 1), "SIN CANCIONES", 0, HUD_PAL_ROJO);
        }
        break;
      case MROW_INSTR:
        fix_text(COL_VALUE, y, menu_instr_name(s_menu.instr), 0, pal);
        if (two) {
          fix_text((u8)(COL_VALUE2 - 1), y, s_row2 == M2ROW_INSTR ? ">" : " ", 0, HUD_PAL_ROJO);
          fix_text(COL_VALUE2, y, menu_instr_name(s_menu.instr2), 0, HUD_PAL_ROJO);
        }
        break;
      case MROW_DIFF:
        fix_text(COL_VALUE, y, menu_diff_name(s_menu.diff), 0, pal);
        if (two) {
          fix_text((u8)(COL_VALUE2 - 1), y, s_row2 == M2ROW_DIFF && s_menu.players == MPLAY_COOP ? ">" : " ", 0,
                   HUD_PAL_ROJO);
          fix_text(COL_VALUE2, y, menu_diff_name(menu_diff_of_p2(&s_menu)), 0, HUD_PAL_ROJO);
        }
        break;
      case MROW_FAIL:
        fix_text(COL_VALUE, y, s_menu.no_fail ? "SIN FALLO" : "SI", 0, pal);
        break;
      case MROW_PLAYERS:
        fix_text(COL_VALUE, y, menu_players_name(s_menu.players), 0, pal);
        if (two) {
          fix_text(COL_VALUE, (u8)(y + 1), "J1", 0, HUD_PAL_AMARILLO);
          fix_text(COL_VALUE2, (u8)(y + 1), "J2", 0, HUD_PAL_ROJO);
        }
        break;
    }
  }
  draw_record();
  g_probe.menu_row = s_menu.row;
  g_probe.menu_song = s_menu.song;
  g_probe.menu_instr = s_menu.instr;
  g_probe.menu_diff = s_menu.diff;
  g_probe.menu_nofail = s_menu.no_fail;
  g_probe.menu_players = s_menu.players;
  g_probe.menu_instr2 = s_menu.instr2;
  g_probe.menu_diff2 = s_menu.diff2;
}

void menu_enter(void)
{
  screen_reset(PR_SCREEN_MENU);
  s_row2 = M2ROW_INSTR;
  sel_to_menu();
  menu_fix_instruments(&s_menu, avail_mask(s_menu.song));
  menu_to_sel();
  menu_draw();
  preview_start(s_menu.song);
  fix_flush();
}

Scene menu_frame(void)
{
  u16 e = nav_edges();
  u16 e2 = nav_edges2();
  u8 avail = avail_mask(s_menu.song);
  bool moved = false;

  if (e & PAD_START) {
    menu_to_sel();
    preview_stop();
    return SCENE_PLAY;
  }
  if (e & PAD_B) {
    preview_stop();
    sfx(SFX_BACK);
    return SCENE_TITLE;
  }
  if (e & PAD_A) {
    menu_to_sel();
    preview_stop();
    sfx(SFX_ACCEPT);
    return SCENE_OPTIONS;
  }
  if (e & (PAD_UP | PAD_DOWN)) { menu_move(&s_menu, (e & PAD_UP) ? -1 : 1); moved = true; }
  if (e & (PAD_LEFT | PAD_RIGHT)) {
    if (menu_change(&s_menu, (e & PAD_LEFT) ? -1 : 1, ngband_num_songs, avail)) {
      menu_fix_instruments(&s_menu, avail_mask(s_menu.song));   /* canción nueva: sus instrumentos */
      preview_start(s_menu.song);
    }
    moved = true;
  }
  if (s_menu.players != MPLAY_SOLO) {   /* el jugador 2 elige con su control */
    if (e2 & (PAD_UP | PAD_DOWN)) { s_row2 = s_row2 == M2ROW_INSTR ? M2ROW_DIFF : M2ROW_INSTR; moved = true; }
    if (e2 & (PAD_LEFT | PAD_RIGHT)) {
      menu_change2(&s_menu, s_row2, (e2 & PAD_LEFT) ? -1 : 1, avail);
      moved = true;
    }
  }
  if (moved) {
    menu_to_sel();
    menu_draw();
    sfx(SFX_MOVE);
  }
  preview_tick(s_menu.song);
  fix_flush();
  return SCENE_MENU;
}

/* ======================= Options_Screen ======================= */
static u8 s_opt_row;

static void options_draw(void)
{
  u8 i;
  const Options *o = &g_sel.opt;
  const u8 vals[OPT_COUNT] = { o->mirror, o->speed_idx, o->fall_idx, o->practice, o->practice_start, o->fail_fx };
  fix_clear(&g_fix);
  text_center(3, "OPCIONES", HUD_PAL_AMARILLO);
  text_center(25, "START JUEGA  B REGRESA", HUD_PAL_VERDE);
  for (i = 0; i < OPT_COUNT; i++) {
    u8 y = (u8)(7 + 2 * i), pal = i == s_opt_row ? HUD_PAL_AMARILLO : HUD_PAL_BLANCO;
    fix_text(COL_CURSOR, y, i == s_opt_row ? ">" : " ", 0, HUD_PAL_AMARILLO);
    fix_text(COL_LABEL, y, options_label(i), 0, pal);
    fix_text(26, y, options_value_name(i, vals[i]), 0, pal);
  }
}

void options_enter(void)
{
  screen_reset(PR_SCREEN_OPTIONS);
  s_opt_row = 0;
  options_draw();
  fix_flush();
}

Scene options_frame(void)
{
  u16 e = nav_edges();
  bool moved = false;
  if (e & PAD_START) {
    sfx(SFX_ACCEPT);
    return SCENE_PLAY;                       /* Start empieza la partida con estas opciones */
  }
  if (e & PAD_B) {
    sfx(SFX_BACK);
    return SCENE_MENU;
  }
  if (e & (PAD_UP | PAD_DOWN)) {
    s_opt_row = (u8)((s_opt_row + OPT_COUNT + ((e & PAD_UP) ? -1 : 1)) % OPT_COUNT);
    moved = true;
  }
  if (e & (PAD_LEFT | PAD_RIGHT)) {
    options_change(&g_sel.opt, s_opt_row, (e & PAD_LEFT) ? -1 : 1);
    moved = true;
  }
  if (moved) {
    options_draw();
    sfx(SFX_MOVE);
  }
  fix_flush();
  return SCENE_OPTIONS;
}

/* ======================= NUEVO RECORD: iniciales ======================= */
static IniEdit s_ini;

static void initials_draw(void)
{
  u8 i;
  char c[2];
  c[1] = 0;
  for (i = 0; i < 3; i++) {
    bool cur = i == s_ini.pos && !s_ini.done;
    c[0] = s_ini.ini[i];
    fix_text((u8)(18 + 2 * i), 15, c, 0, cur ? HUD_PAL_AMARILLO : HUD_PAL_BLANCO);
    fix_text((u8)(18 + 2 * i), 16, cur ? "-" : " ", 0, HUD_PAL_AMARILLO);
  }
  fix_text(18, 18, s_ini.done ? "LISTO" : "     ", 0, HUD_PAL_VERDE);
}

void initials_enter(void)
{
  const Song *sg = song_at(g_sel.song);
  char buf[HUD_SCORE_DIGITS + 1];
  screen_reset(PR_SCREEN_INITIALS);
  text_center(3, "NUEVO RECORD", HUD_PAL_VERDE);
  if (sg) text_center(6, sg->title, HUD_PAL_BLANCO);
  text_center(8, menu_instr_name(g_sel.instrument & 3), HUD_PAL_AMARILLO);
  text_center(9, menu_diff_name(g_sel.difficulty & 3), HUD_PAL_AMARILLO);
  hud_format_uint(buf, results_record_score(), HUD_SCORE_DIGITS);
  text_center(11, buf, HUD_PAL_BLANCO);
  text_center(13, "ESCRIBE TUS INICIALES", HUD_PAL_AMARILLO);
  text_center(25, "ARRIBA/ABAJO LETRA  START LISTO", HUD_PAL_VERDE);
  ini_init(&s_ini, last_initials);
  initials_draw();
  fix_flush();
}

Scene initials_frame(void)
{
  u16 e = nav_edges();
  bool changed = false;
  if (e & (PAD_START | PAD_A | PAD_C)) {
    const Song *sg = song_at(g_sel.song);
    ini_confirm(&s_ini);
    sfx(SFX_ACCEPT);
    /* record_submit ya guardó el récord con las iniciales anteriores; aquí se reescribe con las nuevas */
    if (sg)
      record_save(sg->title_hash, g_sel.instrument & 3, g_sel.difficulty & 3, results_record_score(), s_ini.ini,
                  results_stars());
    return SCENE_MENU;
  }
  if (e & (PAD_UP | PAD_DOWN)) { ini_letter(&s_ini, (e & PAD_UP) ? 1 : -1); changed = true; }
  if (e & (PAD_LEFT | PAD_RIGHT)) { ini_move(&s_ini, (e & PAD_LEFT) ? -1 : 1); changed = true; }
  if (changed) {
    initials_draw();
    sfx(SFX_MOVE);
  }
  fix_flush();
  return SCENE_INITIALS;
}
