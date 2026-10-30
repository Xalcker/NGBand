/* Lógica pura de las opciones (R8.1-R8.4, R8.11, R8.12). Compila en el 68000 y en el host. */
#include "options.h"
#include "audio_proto.h"
#include "chart.h"

static const u8 counts[OPT_COUNT] = {2, SPEED_COUNT, 5, 5, 4, FAILFX_COUNT};

static const char *const labels[OPT_COUNT] = {
  "ESPEJO", "VELOCIDAD", "CAIDA DE NOTAS", "PRACTICA", "INICIO DE LA PRACTICA",
  "EFECTO AL FALLAR",
};
static const char *const mirror_names[] = {"NO", "SI"};
static const char *const speed_names[] = {"100%", "75%", "50%", "125%"};
static const char *const fall_names[] = {"AUTO", "FACIL", "MEDIO", "DIFICIL", "EXPERTO"};
static const char *const practice_names[] = {"NO", "HASTA 1/4", "HASTA 1/2", "HASTA 3/4", "TODA"};
static const char *const start_names[] = {"PRINCIPIO", "1/4", "1/2", "3/4"};
static const char *const fx_names[] = {"SI", "SOLO SONIDO", "NO"};
static const char *const *const names[OPT_COUNT] = {
  mirror_names, speed_names, fall_names, practice_names, start_names, fx_names,
};

static const u8 steps_per4[SPEED_COUNT] = {4, 3, 2, 5};
static const u8 fall_table[4] = {6, 5, 4, 3};

void options_init(Options *o) {
  o->mirror = 0;
  o->speed_idx = SPEED_100;
  o->fall_idx = 0;
  o->practice = 0;
  o->practice_start = 0;
  o->fail_fx = FAILFX_YES;
}

u8 options_count(u8 item) { return item < OPT_COUNT ? counts[item] : 0; }
const char *options_label(u8 item) { return item < OPT_COUNT ? labels[item] : ""; }
const char *options_value_name(u8 item, u8 value) {
  if (item >= OPT_COUNT || value >= counts[item]) return "";
  return names[item][value];
}

bool options_change(Options *o, u8 item, s8 delta) {
  u8 *v;
  u8 n;
  switch (item) {
    case OPT_MIRROR:   v = &o->mirror; break;
    case OPT_SPEED:    v = &o->speed_idx; break;
    case OPT_FALL:     v = &o->fall_idx; break;
    case OPT_PRACTICE: v = &o->practice; break;
    case OPT_START:    v = &o->practice_start; break;
    case OPT_FAIL_FX:  v = &o->fail_fx; break;
    default: return false;
  }
  n = counts[item];
  *v = (u8)((*v + n + delta) % n);
  return item == OPT_PRACTICE || item == OPT_START;
}

bool options_changed(const Options *o) {
  return o->mirror || o->speed_idx != SPEED_100 || o->fall_idx || o->practice ||
         o->practice_start;
}

u8 options_mirror_ev(u8 ev_lanes, u8 lanes, bool drums) {
  u8 mask, out = 0, i;
  if (drums || ev_lanes == CHART_EV_END || lanes == 0 || lanes > 5) return ev_lanes;
  mask = (u8)((1u << lanes) - 1u);
  for (i = 0; i < lanes; i++)
    if ((ev_lanes >> i) & 1) out |= (u8)(1u << (lanes - 1 - i));
  return (u8)((ev_lanes & ~mask) | out);
}

u8 speed_steps_per4(u8 speed_idx) {
  return speed_idx < SPEED_COUNT ? steps_per4[speed_idx] : 4;
}

void speed_init(SpeedClock *s) { s->acc = 0; }

u8 speed_frame(SpeedClock *s, u8 speed_idx) {
  u8 total = (u8)(s->acc + speed_steps_per4(speed_idx));
  s->acc = (u8)(total % 4);
  return (u8)(total / 4);
}

u8 options_fall_frames(const Options *o, u8 difficulty) {
  if (o->fall_idx >= 1 && o->fall_idx <= 4) return fall_table[o->fall_idx - 1];
  return fall_table[difficulty > 3 ? 3 : difficulty];
}

bool options_fail_shake_red(const Options *o) { return o->fail_fx == FAILFX_YES; }
bool options_fail_sound(const Options *o) { return o->fail_fx != FAILFX_NO; }

void fxlim_init(FxLimiter *l) {
  u8 i;
  for (i = 0; i < FXLIM_MAX; i++) l->t[i] = 0;
  l->n = 0;
  l->head = 0;
  l->last = 0xFF;
}

int fxlim_air(FxLimiter *l, u32 now, u8 rnd) {
  u8 fx;
  if (l->n >= FXLIM_MAX && now - l->t[l->head] < FXLIM_WINDOW) return -1;
  if (l->last == 0xFF) fx = (u8)(rnd % 3);
  else fx = (u8)((l->last - SFX_FAIL_CLANK + 1 + (rnd & 1)) % 3);
  fx = (u8)(SFX_FAIL_CLANK + fx);
  /* anillo: con el anillo lleno, `head` es el más viejo y se sobrescribe */
  l->t[l->head] = now;
  l->head = (u8)((l->head + 1) % FXLIM_MAX);
  if (l->n < FXLIM_MAX) l->n++;
  l->last = fx;
  return fx;
}
