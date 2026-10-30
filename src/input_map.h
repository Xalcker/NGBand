/* Mapa puro de controles (R6). Sin dependencia de hardware. */
#ifndef NGBAND_INPUT_MAP_H
#define NGBAND_INPUT_MAP_H

#include "types.h"
#include "gameplay.h"

/* Lectura cruda con lógica positiva (1 = presionado). */
#define PAD_UP     0x0001
#define PAD_DOWN   0x0002
#define PAD_LEFT   0x0004
#define PAD_RIGHT  0x0008
#define PAD_A      0x0010
#define PAD_B      0x0020
#define PAD_C      0x0040
#define PAD_D      0x0080
#define PAD_START  0x0100

/* Bits de carril en PadInput (R6.1). */
#define LANE_GREEN   0x01  /* ← */
#define LANE_RED     0x02  /* ↓ */
#define LANE_YELLOW  0x04  /* → */
#define LANE_BLUE    0x08  /* B */
#define LANE_ORANGE  0x10  /* C */

typedef struct {
  PadInput in;          /* carriles filtrados: pressed y edge */
  bool power, power_edge; /* poder estelar (A) */
  bool pause_edge;      /* Start recién presionado */
  u16  prev_raw;        /* lectura filtrada del cuadro anterior (uso interno) */
} PadState;

/* Convierte una lectura cruda en máscara de carriles; ← y → a la vez
 * dejan verde y amarillo sin pulsar (R6.2). */
u8   input_lane_mask(u16 raw);

/* Avanza un cuadro: actualiza pressed/edge/power/pausa a partir de `raw`. */
void input_update(PadState *s, u16 raw);

#endif /* NGBAND_INPUT_MAP_H */
