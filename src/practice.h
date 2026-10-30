/* Practice_Mode (R8.5-R8.10): bucle, puntos de inicio y marcas. Lógica pura. */
#ifndef NGBAND_PRACTICE_H
#define NGBAND_PRACTICE_H

#include "types.h"
#include "chart.h"

#define PRACTICE_FPS        60
#define PRACTICE_MIN_LOOP   (4 * PRACTICE_FPS)   /* R8.9: bucle mínimo de 4 s */
#define PRACTICE_LEAD       (2 * PRACTICE_FPS)   /* R8.7: la marca A cae 2 s antes de la pausa */

typedef struct {
  bool active;
  bool marks;        /* el jugador marcó inicio o fin con A/B */
  u16  total;        /* duración de la canción en cuadros */
  u16  loop_start;   /* cuadro donde inicia el bucle */
  u16  loop_end;     /* cuadro donde termina el bucle (exclusivo) */
} Practice;

/* `mode`: 0 = NO, 1..4 = hasta 1/4, 1/2, 3/4 o toda. `start_q`: 0..3 = principio, 1/4, 1/2, 3/4.
 * Si el fin no deja al menos 4 s tras el inicio, el fin pasa al final de la canción. */
void practice_init(Practice *p, u8 mode, u8 start_q, u16 total_frames);

/* Cuadro del punto de inicio `q` (0..3): total * q / 4. */
u16 practice_quarter_frame(u16 total_frames, u8 q);

/* Cuarto para CMD_SONG_SEEK (0..3): el mayor cuarto con cuadro <= loop_start. El resto
 * (loop_start - quarter_frame) lo adelanta el juego. */
u8 practice_seek_quarter(const Practice *p);

/* Omite del cursor las Notes anteriores a `loop_start` (R8.6) y fija su cuadro. */
void practice_skip_notes(const Practice *p, const Chart *chart, ChartCursor *cur);

/* Cuadro actual: true si llegó al fin del bucle y hay que reiniciar en loop_start. */
bool practice_at_end(const Practice *p, u16 frame);

/* Controles en pausa; `pause_frame` es el cuadro de la pausa. A (R8.7): inicio del bucle
 * 2 s antes. B (R8.8): fin del bucle. Rechazan (false, sin cambios) si el bucle resultante
 * dura menos de 4 s (R8.9). */
bool practice_mark_start(Practice *p, u16 pause_frame);
bool practice_mark_end(Practice *p, u16 pause_frame);

/* Botón C en pausa (R8.10): true si debe regresar al Menu. */
bool practice_pause_exit(bool c_edge);

#endif /* NGBAND_PRACTICE_H */
