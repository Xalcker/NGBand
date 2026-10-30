/* Judge: reglas del núcleo (R2). Sin dependencia de hardware; compila en el
 * 68000 y en el host. Un paso por cuadro de video (R2.10). */
#include "gameplay.h"

#define HIT_WINDOW   6   /* R2.2: +-6 cuadros */
#define NOTE_POINTS  50  /* R2.3 */
#define HOLD_POINTS  10  /* R2.8 */
#define HOLD_PERIOD  8
#define Q_CAP        24
#define HOLD_UNKNOWN 0xFFFFu

u8 judge_multiplier(u16 combo) {
  u16 m = (u16)(1 + combo / 10);
  return (u8)(m > 4 ? 4 : m);
}

u8 judge_stars(u32 score_base, u32 perfect) {
  static const u8 thresholds[5] = {20, 40, 60, 80, 95};
  u8 n = 0;
  if (perfect == 0) return 0;
  while (n < 5 && (uint64_t)score_base * 100u >= (uint64_t)perfect * thresholds[n]) n++;
  return n;
}

static PendingNote *q_at(ChartCursor *c, u8 i) {
  return &c->q[(u8)((c->head + i) % Q_CAP)];
}


static void break_combo(JudgeState *j) {
  j->combo = 0;
  j->multiplier = 1;
  j->muted = true;
}

/* Resta vida (R3.2-R3.4). En 0 la partida termina salvo SIN FALLO (R3.5). */
static void lose_life(JudgeState *j, u8 amount) {
  j->life = (s16)(j->life > amount ? j->life - amount : 0);
  if (j->life == 0 && !j->no_fail) {
    j->failed = true;
    j->muted = true;
  }
}

void judge_init(JudgeState *j, u8 lanes, bool easy, bool no_fail) {
  uint8_t *p = (uint8_t *)j;
  u32 i;
  for (i = 0; i < sizeof *j; i++) p[i] = 0;
  j->lanes = lanes;
  j->multiplier = 1;
  j->life = LIFE_START;
  j->easy = easy;
  j->no_fail = no_fail;
}

bool judge_star_power(JudgeState *j) {
  if (j->failed || j->star_active || j->star_bar < STAR_MIN) return false;
  j->star_active = true;
  j->star_drain = 0;
  return true;
}

/* Una frase estelar termina cuando la Note siguiente no es estelar o el Chart
 * se acabó. Si no se perdió ninguna de sus Notes, sube la barra (R3.6). */
static void phrase_check(JudgeState *j, ChartCursor *c) {
  if (!c->phrase_active) return;
  if (c->count) {
    if (c->q[c->head].flags & CHART_FLAG_STAR) return;
  } else if (!c->done) {
    return; /* la Note siguiente aún no se lee */
  }
  if (c->phrase_ok) {
    u16 bar = (u16)(j->star_bar + STAR_PHRASE);
    j->star_bar = (u8)(bar > STAR_MAX ? STAR_MAX : bar);
    j->phrase_done = true;
  }
  c->phrase_active = false;
}

/* Un fin de cola pertenece a la nota con cola más reciente en esos carriles. */
static void apply_end(ChartCursor *c, u8 lanes, u16 frame) {
  u8 i;
  for (i = c->count; i > 0; i--) {
    PendingNote *n = q_at(c, (u8)(i - 1));
    if ((n->flags & CHART_FLAG_SUSTAIN) && n->end == 0 && (n->mask & lanes)) {
      n->end = frame;
      return;
    }
  }
  for (i = 0; i < 5; i++)
    if (((c->hold_lanes >> i) & 1) && (lanes >> i & 1) && c->hold_end[i] == HOLD_UNKNOWN)
      c->hold_end[i] = frame;
}

/* Lee eventos hasta el cuadro `limit` (ahora + Hit_Window). */
static void read_ahead(ChartCursor *c, const Chart *chart, u8 lane_mask, u16 limit) {
  while (!c->done) {
    u16 frame;
    const ChartEv *ev;
    if (c->index >= chart->count) { c->done = true; break; }
    ev = &chart->ev[c->index];
    if (ev->lanes == CHART_EV_END) { c->done = true; break; }
    frame = (u16)(c->frame + ev->delta_lo);
    if (frame > limit) break;
    if (ev->lanes & CHART_FLAG_END) {
      apply_end(c, (u8)(ev->lanes & CHART_LANE_MASK), frame);
    } else if (ev->lanes & CHART_LANE_MASK) {
      PendingNote *n;
      if (c->count >= Q_CAP) break; /* cola llena: se sigue leyendo el cuadro siguiente */
      n = q_at(c, c->count++);
      n->frame = frame;
      n->end = 0;
      n->mask = (u8)(ev->lanes & CHART_LANE_MASK & lane_mask);
      n->open = n->mask;
      n->flags = (u8)(ev->lanes & (CHART_FLAG_STAR | CHART_FLAG_SUSTAIN));
      n->pad = 0;
      if (!n->mask) c->count--; /* solo carriles que la Difficulty no usa */
    }
    c->frame = frame;
    c->index++;
  }
}

static void hit(JudgeState *j, ChartCursor *c, PendingNote *n, u8 lane, u16 now) {
  if (n->open == n->mask && j->life < LIFE_MAX) /* una Note da +1 aunque sea acorde (R3.1) */
    j->life++;
  n->open &= (u8)~(1u << lane);
  j->notes_hit++;
  j->last_lane = lane;
  j->combo++;
  if (j->combo > j->max_combo) j->max_combo = j->combo;
  j->multiplier = judge_multiplier(j->combo);
  j->score_base += (u32)NOTE_POINTS * j->multiplier;
  j->score += (u32)NOTE_POINTS * j->multiplier * (j->star_active ? 2u : 1u);
  j->muted = false;
  if ((n->flags & CHART_FLAG_SUSTAIN) && (n->end == 0 || n->end > now)) {
    c->hold_lanes |= (u8)(1u << lane);
    c->hold_end[lane] = n->end ? n->end : HOLD_UNKNOWN;
  }
}

void judge_step(JudgeState *j, const Chart *chart, ChartCursor *cur,
                PadInput in, u16 frame) {
  u8 lane_mask = (u8)((1u << j->lanes) - 1u);
  u8 lane, i;

  j->phrase_done = false;
  if (j->failed) { /* partida terminada: el Chart sigue avanzando, sin puntaje ni vida */
    in.edge = 0;
    in.pressed = 0;
  }

  read_ahead(cur, chart, lane_mask, (u16)(frame + HIT_WINDOW));

  /* Pulsaciones: cada botón acierta la nota más vieja de su carril en la ventana. */
  for (lane = 0; lane < j->lanes; lane++) {
    PendingNote *found = 0;
    if (j->failed) break;
    if (!((in.edge >> lane) & 1)) continue;
    for (i = 0; i < cur->count; i++) {
      PendingNote *n = q_at(cur, i);
      if (n->frame > (u16)(frame + HIT_WINDOW)) break;
      if (((n->open >> lane) & 1) && (u16)(n->frame + HIT_WINDOW) >= frame) {
        found = n;
        break;
      }
    }
    if (found) hit(j, cur, found, lane, frame);
    else { /* golpe al aire (R2.6, R3.3) */
      break_combo(j);
      lose_life(j, LIFE_AIR);
    }
  }

  /* La Note de la cabeza sale de la cola cuando se acertó entera o venció su
   * ventana sin acertarse (R2.7, R3.2). Así las frases se resuelven en orden. */
  while (cur->count) {
    PendingNote *n = q_at(cur, 0);
    bool missed = false;
    if (n->open) {
      if ((u16)(n->frame + HIT_WINDOW) >= frame) break;
      missed = true;
    }
    if (!j->failed) {
      if (missed) {
        break_combo(j);
        lose_life(j, j->easy ? LIFE_MISS_EASY : LIFE_MISS);
      }
      if (n->flags & CHART_FLAG_STAR) {
        if (!cur->phrase_active) {
          cur->phrase_active = true;
          cur->phrase_ok = true;
        }
        if (missed) cur->phrase_ok = false;
      }
    }
    cur->head = (u8)((cur->head + 1) % Q_CAP);
    cur->count--;
    if (j->failed) cur->phrase_active = false;
    phrase_check(j, cur);
  }
  phrase_check(j, cur);

  /* Sustain (R2.8): suelta el botón o llega el fin de la cola. */
  for (lane = 0; lane < 5; lane++)
    if (((cur->hold_lanes >> lane) & 1) &&
        (!((in.pressed >> lane) & 1) || (cur->hold_end[lane] != HOLD_UNKNOWN && frame >= cur->hold_end[lane])))
      cur->hold_lanes &= (u8)~(1u << lane);
  if (cur->hold_lanes) {
    cur->hold_timer++;
    if (cur->hold_timer % HOLD_PERIOD == 0) j->score += HOLD_POINTS;
  } else {
    cur->hold_timer = 0;
  }

  /* Star_Power se gasta mientras está activo (R3.7). */
  if (j->star_active && ++j->star_drain >= STAR_DRAIN_FRAMES) {
    j->star_drain = 0;
    if (j->star_bar) j->star_bar--;
    if (!j->star_bar) j->star_active = false;
  }
}

void clock_init(PlayClock *c) {
  c->paused = false;
  c->frame = 0;
  c->stream_frame = 0;
}

bool clock_toggle_pause(PlayClock *c) {
  c->paused = !c->paused;
  return c->paused;
}

bool play_step(PlayClock *c, JudgeState *j, const Chart *chart, ChartCursor *cur,
               PadInput in, bool star_edge, bool start_edge) {
  if (start_edge) {
    clock_toggle_pause(c);
    return false; /* el cuadro de la pausa o la reanudación no avanza la partida */
  }
  if (c->paused) return false;
  if (star_edge) judge_star_power(j);
  judge_step(j, chart, cur, in, c->frame);
  c->frame++;
  c->stream_frame++;
  return true;
}
