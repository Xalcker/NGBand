/* Máquina de estados del Stage (R11). Sin dependencia de hardware. */
#ifndef NGBAND_STAGE_H
#define NGBAND_STAGE_H

#include "types.h"

#define STAGE_CHEER        10  /* Combo desde el que el público se anima (R11.2, R11.3) */
#define STAGE_ATTACK       6   /* cuadros tras cada tiempo en que el público salta y la luz late */
#define STAGE_FLASH_FRAMES 8   /* duración del destello de frase estelar (R11.6) */

enum { CROWD_QUIETO = 0, CROWD_BRAZOS = 1, CROWD_SALTO = 2 };
enum { LIGHT_CIAN = 0, LIGHT_ROJO = 1, LIGHT_AMARILLO = 2, LIGHT_VIOLETA = 3 };

typedef struct {
  u16  combo;           /* Combo máximo entre los jugadores en pie */
  bool star_active;     /* Star_Power activo */
  bool beat_tick;       /* este cuadro empieza un tiempo de la canción */
  bool phrase_done;     /* se completó una frase estelar en este cuadro */
  bool all_failed;      /* todos los jugadores perdieron */
  u8   players;         /* 1 o 2 */
  u8   last_lane;       /* carril de la última Note (para el rayo) */
} StageInput;

typedef struct {
  u8 crowd_state;       /* CROWD_QUIETO | CROWD_BRAZOS | CROWD_SALTO */
  u8 light_phase;       /* 0..3: cian, rojo, amarillo, violeta */
  u8 pulse;             /* latido de luces: cuadros restantes tras el tiempo */
  u8 flash, bolt_lane;  /* destello (cuadros restantes) y carril del rayo */
  bool lights_off;
} StageState;

void stage_init(StageState *s);
/* true si `frame` es el inicio de un tiempo: pasado el LEAD_IN, cada `beat_frames` cuadros. */
bool stage_is_beat(u16 frame, u16 lead_in, u16 beat_frames);
void stage_step(StageState *s, const StageInput *in);

#endif /* NGBAND_STAGE_H */
