/* Opciones (R8): ESPEJO, VELOCIDAD, CAIDA DE NOTAS, PRACTICA, INICIO DE LA PRACTICA y
 * EFECTO AL FALLAR. Lógica pura, sin dependencia de hardware. */
#ifndef NGBAND_OPTIONS_H
#define NGBAND_OPTIONS_H

#include "types.h"

/* Renglones de la Options_Screen, en orden de pantalla (R8.1). */
enum {
  OPT_MIRROR, OPT_SPEED, OPT_FALL, OPT_PRACTICE, OPT_START, OPT_FAIL_FX, OPT_COUNT
};

/* Valores de VELOCIDAD (speed_idx): 100%, 75%, 50%, 125% (R8.3). */
enum { SPEED_100, SPEED_75, SPEED_50, SPEED_125, SPEED_COUNT };

/* EFECTO AL FALLAR (fail_fx): SI = temblor, rojo y sonido; SOLO SONIDO; NO (R8.11). */
enum { FAILFX_YES, FAILFX_SOUND, FAILFX_NO, FAILFX_COUNT };

/* Cuadros por cada 8 px de caída (R5.8): de fácil a experto. */
#define FALL_FRAMES_EASY    6
#define FALL_FRAMES_EXPERT  3

/* Espejo de GameConfig (design.md). practice: 0 = NO, 1..4 = hasta 1/4, 1/2, 3/4 o toda.
 * practice_start: 0 = principio, 1..3 = 1/4, 1/2, 3/4. fall_idx: 0 = AUTO, 1..4 = fácil..experto. */
typedef struct {
  u8 mirror, speed_idx, fall_idx, practice, practice_start, fail_fx;
} Options;

/* Valores por defecto: ESPEJO NO, 100%, AUTO, PRACTICA NO, INICIO principio, EFECTO SI. */
void options_init(Options *o);

/* Número de valores del renglón `item` y sus textos en español (R8.1, R7.8). */
u8 options_count(u8 item);
const char *options_label(u8 item);
const char *options_value_name(u8 item, u8 value);

/* Cambia el renglón con vuelta circular; `delta` es -1 o +1. Devuelve true si el
 * cambio invalida las marcas de práctica (PRACTICA o INICIO). */
bool options_change(Options *o, u8 item, s8 delta);

/* true si alguna opción distinta de la normal impide guardar récords. EFECTO AL FALLAR no cuenta. */
bool options_changed(const Options *o);

/* ESPEJO (R8.2): invierte `lane -> lanes-1-lane` en el campo `lanes` de un evento de Chart.
 * Conserva los bits de bandera (estelar, sustain, fin de cola) y el cierre 0xFF.
 * La batería no cambia. */
u8 options_mirror_ev(u8 ev_lanes, u8 lanes, bool drums);

/* VELOCIDAD (R8.3): pasos por cada 4 cuadros (4, 3, 2 o 5). */
u8 speed_steps_per4(u8 speed_idx);

/* Acumulador de pasos. Cada cuadro de video llama a speed_frame; devuelve cuántos pasos de
 * juego (y cuadros del Frame_Stream) corresponden a este cuadro: 0, 1 o 2. Con 0 el 68000
 * manda CMD_HOLD; con n = 1 manda CMD_FRAME y n = 2 manda CMD_FRAME2 (un byte por VBlank). Tras N cuadros el total es floor(N*k/4). */
typedef struct { u8 acc; } SpeedClock;
void speed_init(SpeedClock *s);
u8 speed_frame(SpeedClock *s, u8 speed_idx);

/* CAIDA DE NOTAS (R8.4): cuadros por 8 px. AUTO usa la de la Difficulty (0 fácil .. 3 experto). */
u8 options_fall_frames(const Options *o, u8 difficulty);

/* EFECTO AL FALLAR (R8.11). */
bool options_fail_shake_red(const Options *o);
bool options_fail_sound(const Options *o);

/* Limitador de efectos de golpe al aire (R8.12): como máximo FXLIM_MAX por FXLIM_WINDOW
 * cuadros y cada efecto distinto del anterior. */
#define FXLIM_MAX     3
#define FXLIM_WINDOW  60

typedef struct {
  u32 t[3];           /* cuadros de los últimos efectos emitidos (anillo) */
  u8  n, head;
  u8  last;           /* último SFX emitido; 0xFF = ninguno */
} FxLimiter;

void fxlim_init(FxLimiter *l);
/* Golpe al aire en el cuadro `now` (no decreciente). `rnd` elige entre los dos efectos
 * distintos del anterior. Devuelve el SFX_FAIL_* a reproducir o -1 si se suprime. */
int fxlim_air(FxLimiter *l, u32 now, u8 rnd);

#endif /* NGBAND_OPTIONS_H */
