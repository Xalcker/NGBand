/* Formato de Chart en ROM. Sin dependencia de hardware. */
#ifndef NGBAND_CHART_H
#define NGBAND_CHART_H

#include "types.h"

#define CHART_LANE_MASK   0x1F  /* bits 0..4 = carriles */
#define CHART_FLAG_STAR   0x20  /* bit 5 = estelar */
#define CHART_FLAG_SUSTAIN 0x40 /* bit 6 = sustain */
#define CHART_FLAG_END    0x80  /* bit 7 = fin de cola (lanes = carriles que sueltan) */
#define CHART_EV_END      0xFF  /* lanes = 0xFF cierra el Chart */

typedef struct {
  u8 delta_lo;  /* cuadros desde la nota anterior, con extensión */
  u8 lanes;     /* bits 0..4 = carriles; bit 5 = estelar; bit 6 = sustain */
} ChartEv;      /* 2 bytes; delta >= 255 usa un evento de extensión */

typedef struct {
  u16 count;
  const ChartEv *ev;
} Chart;

/* Nota leída por adelantado, dentro (o por entrar a) la Hit_Window. */
typedef struct {
  u16 frame;       /* cuadro absoluto de la nota */
  u16 end;         /* cuadro de fin de cola; 0 = aún sin fin leído */
  u8  mask;        /* carriles del evento */
  u8  open;        /* carriles aún sin acertar ni perder */
  u8  flags;       /* CHART_FLAG_STAR | CHART_FLAG_SUSTAIN */
  u8  pad;
} PendingNote;

/* Posición de lectura dentro de un Chart y estado del Judge ligado a él.
 * Se inicializa en cero (memset) al empezar la canción. */
typedef struct {
  u16 index;       /* siguiente evento por leer */
  u16 frame;       /* cuadro absoluto del último evento leído (0 al inicio) */
  bool done;       /* se leyó el fin del Chart */
  u8  head, count; /* cola circular de notas pendientes (capacidad 24) */
  PendingNote q[24];
  u8  hold_lanes;  /* carriles con cola sostenida en curso */
  u8  hold_timer;  /* cuadros con alguna cola sostenida (mod 8 da el puntaje) */
  u16 hold_end[5]; /* fin de cola por carril; 0xFFFF = aún desconocido */
  bool phrase_active; /* hay una frase estelar en curso (R3.6) */
  bool phrase_ok;     /* todas las Notes de la frase en curso se acertaron */
} ChartCursor;

#endif /* NGBAND_CHART_H */
