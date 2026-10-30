/* Reglas de dos jugadores (R10): VS y COOP. Lógica pura sobre JudgeState. */
#ifndef NGBAND_VERSUS_H
#define NGBAND_VERSUS_H

#include "types.h"
#include "gameplay.h"

/* ---- VS (R10.1-R10.3) ---- */
enum { VS_TIE = 0, VS_P1_WINS = 1, VS_P2_WINS = 2 };

typedef struct {
  u8  outcome;   /* VS_* */
  u32 margin;    /* diferencia de puntaje; 0 si gana el otro porque un jugador perdió por vida */
} VsResult;

/* La partida VS termina en cuanto un jugador pierde (R10.3). */
bool vs_over(const JudgeState *p1, const JudgeState *p2);

/* Resultado: si solo uno perdió, gana el otro; si no, decide el puntaje. `margin` es la
 * diferencia de puntaje en ambos casos. */
VsResult vs_result(const JudgeState *p1, const JudgeState *p2);

/* Escribe `GANA J1 POR n`, `GANA J2 POR n` o `EMPATE` (terminado en NUL).
 * Devuelve la longitud sin el NUL; `cap` incluye el NUL. */
u8 vs_result_text(const VsResult *r, char *out, u8 cap);

/* ---- COOP (R10.4-R10.7) ----
 * Puntaje, Combo y Star_Power son de la banda; la vida es de cada jugador. */
typedef struct {
  JudgeState p[2];
  /* Estado compartido de la banda. */
  u32  score, score_base;
  u16  combo, max_combo;
  u8   multiplier;
  u8   star_bar;
  bool star_active;
  u8   star_drain;
} CoopState;

/* Dificultad común (R10.1); `easy` y `no_fail` aplican a los dos. */
void coop_init(CoopState *c, u8 lanes, bool easy, bool no_fail);

/* Avanza al jugador `who` (0 o 1) un cuadro: carga el estado de la banda, corre el Judge
 * y lo guarda. Hay que llamar a los dos jugadores cada cuadro, primero el 0; el gasto de
 * Star_Power se aplica una sola vez por cuadro. */
void coop_step(CoopState *c, u8 who, const Chart *chart, ChartCursor *cur,
               PadInput in, u16 frame);

/* Botón de poder estelar del jugador `who` (R10.5). Si el otro está caído y la banda
 * tiene media barra, lo revive y gasta media barra; si no, activa Star_Power como en
 * solitario. Devuelve true si hizo una de las dos cosas. */
bool coop_star_press(CoopState *c, u8 who);

/* Revive a `who` si está caído, el otro está en pie y hay media barra (STAR_MIN).
 * Gasta exactamente STAR_MIN y lo deja con media barra de vida. */
bool coop_revive(CoopState *c, u8 who);

/* Vista del jugador `who` con lo de la banda (puntaje, Combo, Multiplier, Star_Power) y lo
 * suyo (vida, caído, carriles), para dibujar el HUD. */
void coop_view(const CoopState *c, u8 who, JudgeState *out);

/* La partida termina si y solo si los dos están caídos (R10.6). */
bool coop_over(const CoopState *c);

/* R10.7: los dos jugadores no pueden elegir el mismo Instrument. */
bool coop_instruments_ok(u8 a, u8 b);

/* Siguiente Instrument (`dir` = +1 o -1) entre `count` que no sea `other`. */
u8 coop_next_instrument(u8 cur, u8 other, u8 count, s8 dir);

#endif /* NGBAND_VERSUS_H */
