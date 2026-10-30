/* API pura del Judge. Sin dependencia de hardware. */
#ifndef NGBAND_GAMEPLAY_H
#define NGBAND_GAMEPLAY_H

#include "types.h"
#include "chart.h"

/* Vida (R3.1-R3.5). Misma escala que GENBand. */
#define LIFE_MAX         48
#define LIFE_START       (LIFE_MAX * 2 / 3)
#define LIFE_HIT         1
#define LIFE_MISS        2   /* Note perdida; 1 en fácil */
#define LIFE_MISS_EASY   1
#define LIFE_AIR         1

/* Star_Power (R3.6, R3.7). */
#define STAR_MAX         100
#define STAR_PHRASE      25  /* por frase estelar completa */
#define STAR_MIN         50  /* barra mínima para activar */
#define STAR_DRAIN_FRAMES 8  /* cuadros por punto gastado mientras está activo */

typedef struct {
  u8  lanes;            /* 3, 4 o 5 según Difficulty */
  u16 combo, max_combo;
  u8  multiplier;       /* 1..4 */
  s16 life;             /* 0..LIFE_MAX */
  u32 score;
  u32 score_base;       /* sin Star_Power ni Sustain, para estrellas */
  u8  star_bar;         /* 0..100 */
  bool star_active, muted, failed;
  bool easy;            /* Difficulty fácil: la Note perdida resta 1 */
  bool no_fail;         /* SIN FALLO: la vida no termina la partida */
  bool phrase_done;     /* se completó una frase estelar en este paso (Stage) */
  u8  star_drain;       /* cuadros acumulados del gasto de Star_Power */
  u16 notes_hit;        /* botones acertados (una Note por botón de acorde, R2.4) */
  u8  last_lane;        /* carril del último botón acertado (rayo del Stage, R11.6) */
} JudgeState;

typedef struct {
  u8 pressed, edge;     /* máscara de 5 carriles */
} PadInput;

/* Reloj de la partida: cuadro de la canción y cuadro del Frame_Stream
 * avanzan juntos y se detienen juntos en la pausa (R3.8, R3.9). */
typedef struct {
  bool paused;
  u16  frame;           /* cuadro de la canción que recibe el Judge */
  u16  stream_frame;    /* cuadros del Frame_Stream aplicados */
} PlayClock;

/* Estado inicial: vida LIFE_START, Multiplier 1, todo lo demás en cero. */
void judge_init(JudgeState *j, u8 lanes, bool easy, bool no_fail);

void judge_step(JudgeState *j, const Chart *chart, ChartCursor *cur,
                PadInput in, u16 frame);
u8   judge_multiplier(u16 combo);
u8   judge_stars(u32 score_base, u32 perfect);

/* Botón de poder estelar (R3.7). Devuelve true si se activó. */
bool judge_star_power(JudgeState *j);

void clock_init(PlayClock *c);
/* Start alterna pausa/reanudar (R3.8, R3.9). Devuelve true si queda en pausa. */
bool clock_toggle_pause(PlayClock *c);

/* Un cuadro de video de la partida. Con `start_edge` alterna la pausa. En pausa no
 * toca el Judge, el cursor ni los relojes. Devuelve true si el juego avanzó. */
bool play_step(PlayClock *c, JudgeState *j, const Chart *chart, ChartCursor *cur,
               PadInput in, bool star_edge, bool start_edge);

#endif /* NGBAND_GAMEPLAY_H */
