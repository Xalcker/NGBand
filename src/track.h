/* Pista fija: la superficie de la autopista (carriles, bordes y aros) con sprites que se escriben una vez por
 * canción, y franjas que bajan solas con la autoanimación del LSPC (sin trabajo del 68000 por cuadro). */
#ifndef NGBAND_TRACK_H
#define NGBAND_TRACK_H
#include "types.h"
#include "highway_layout.h"

/* Muestra la pista de cada Highway. `speed_idx` es la VELOCIDAD (options.h): las franjas siguen a las gemas. */
void track_show(const HwyView *views, u8 nviews, u8 speed_idx);
/* Congela (pausa) o reanuda el movimiento de las franjas. */
void track_pause(bool paused);
/* Oculta la pista (al salir del juego). */
void track_hide(void);

#endif /* NGBAND_TRACK_H */
