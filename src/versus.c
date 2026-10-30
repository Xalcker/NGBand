/* Reglas de dos jugadores (R10). Sin dependencia de hardware. */
#include "versus.h"

/* ---- VS ---- */

bool vs_over(const JudgeState *p1, const JudgeState *p2) {
  return p1->failed || p2->failed;
}

VsResult vs_result(const JudgeState *p1, const JudgeState *p2) {
  VsResult r;
  u32 a = p1->score, b = p2->score;
  r.margin = a > b ? a - b : b - a;
  if (p1->failed != p2->failed)
    r.outcome = p1->failed ? VS_P2_WINS : VS_P1_WINS;
  else if (a == b)
    r.outcome = VS_TIE;
  else
    r.outcome = a > b ? VS_P1_WINS : VS_P2_WINS;
  return r;
}

static u8 put_str(char *out, u8 cap, u8 n, const char *s) {
  while (*s && (u8)(n + 1) < cap) out[n++] = *s++;
  return n;
}

static u8 put_u32(char *out, u8 cap, u8 n, u32 v) {
  char tmp[10];
  u8 k = 0;
  do { tmp[k++] = (char)('0' + v % 10u); v /= 10u; } while (v);
  while (k && (u8)(n + 1) < cap) out[n++] = tmp[--k];
  return n;
}

u8 vs_result_text(const VsResult *r, char *out, u8 cap) {
  u8 n = 0;
  if (!cap) return 0;
  if (r->outcome == VS_TIE) {
    n = put_str(out, cap, n, "EMPATE");
  } else {
    n = put_str(out, cap, n, r->outcome == VS_P1_WINS ? "GANA J1 POR " : "GANA J2 POR ");
    n = put_u32(out, cap, n, r->margin);
  }
  out[n] = 0;
  return n;
}

/* ---- COOP ---- */

void coop_init(CoopState *c, u8 lanes, bool easy, bool no_fail) {
  uint8_t *b = (uint8_t *)c;
  u32 i;
  for (i = 0; i < sizeof *c; i++) b[i] = 0;
  judge_init(&c->p[0], lanes, easy, no_fail);
  judge_init(&c->p[1], lanes, easy, no_fail);
  c->multiplier = 1;
}

static void band_load(const CoopState *c, JudgeState *j) {
  j->score = c->score;
  j->score_base = c->score_base;
  j->combo = c->combo;
  j->max_combo = c->max_combo;
  j->multiplier = c->multiplier;
  j->star_bar = c->star_bar;
  j->star_active = c->star_active;
  j->star_drain = c->star_drain;
}

static void band_store(CoopState *c, const JudgeState *j) {
  c->score = j->score;
  c->score_base = j->score_base;
  c->combo = j->combo;
  c->max_combo = j->max_combo;
  c->multiplier = j->multiplier;
  c->star_bar = j->star_bar;
  c->star_active = j->star_active;
  c->star_drain = j->star_drain;
}

void coop_step(CoopState *c, u8 who, const Chart *chart, ChartCursor *cur,
               PadInput in, u16 frame) {
  JudgeState *j = &c->p[who & 1];
  u8 bar0 = c->star_bar;
  bool act0 = c->star_active;
  u8 drain0 = c->star_drain;

  band_load(c, j);
  judge_step(j, chart, cur, in, frame);

  if (who & 1) {
    /* El gasto de Star_Power ya lo aplicó el jugador 0 en este cuadro: se deshace y,
     * si hubo frase estelar, solo se suma su premio. */
    if (j->phrase_done) {
      u16 bar = (u16)(bar0 + STAR_PHRASE);
      j->star_bar = (u8)(bar > STAR_MAX ? STAR_MAX : bar);
    } else {
      j->star_bar = bar0;
    }
    j->star_active = act0;
    j->star_drain = drain0;
  }
  band_store(c, j);
}

bool coop_revive(CoopState *c, u8 who) {
  JudgeState *j = &c->p[who & 1];
  const JudgeState *other = &c->p[(who & 1) ^ 1];
  if (!j->failed || other->failed || c->star_bar < STAR_MIN) return false;
  c->star_bar = (u8)(c->star_bar - STAR_MIN);
  if (!c->star_bar) c->star_active = false;
  j->failed = false;
  j->muted = false;
  j->life = LIFE_MAX / 2;
  return true;
}

bool coop_star_press(CoopState *c, u8 who) {
  JudgeState *j = &c->p[who & 1];
  bool ok;
  if (j->failed) return false;
  if (coop_revive(c, (u8)((who & 1) ^ 1))) return true;
  band_load(c, j);
  ok = judge_star_power(j);
  band_store(c, j);
  return ok;
}

void coop_view(const CoopState *c, u8 who, JudgeState *out) {
  *out = c->p[who & 1];
  band_load(c, out);
}

bool coop_over(const CoopState *c) {
  return c->p[0].failed && c->p[1].failed;
}

bool coop_instruments_ok(u8 a, u8 b) {
  return a != b;
}

u8 coop_next_instrument(u8 cur, u8 other, u8 count, s8 dir) {
  u8 i, v = cur;
  if (count < 2) return cur;
  for (i = 0; i < count; i++) {
    v = (u8)((v + (dir < 0 ? count - 1 : 1)) % count);
    if (v != other) return v;
  }
  return cur;
}
