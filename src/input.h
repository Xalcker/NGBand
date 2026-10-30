/* Lectura de controles de la Neo Geo (R6). */
#ifndef NGBAND_INPUT_H
#define NGBAND_INPUT_H

#include "input_map.h"

/* Una lectura por cuadro, desde el ISR de VBlank. */
void input_poll(void);
/* Al empezar cada paso del bucle principal: toma lo último leído con los flancos juntados desde el paso
 * anterior (un VBlank que el bucle no atendió no pierde sus flancos). */
void input_take(void);
/* Lo tomado por input_take para el jugador 0 o 1. */
const PadState *input_get(u8 player);

#endif /* NGBAND_INPUT_H */
