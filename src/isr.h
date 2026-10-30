/* Interrupción de VBlank (R18.1): lectura de controles, audio y volcado de la cola de VRAM.
 * El bucle principal espera la bandera con isr_wait_frame() y hace un paso de juego por cuadro. */
#ifndef NGBAND_ISR_H
#define NGBAND_ISR_H
#include "types.h"
void isr_init(void);
/* Bloquea hasta el siguiente VBlank ya atendido por el ISR. */
void isr_wait_frame(void);
/* Cuadros de video desde isr_init. */
u32  isr_frames(void);
/* Cuadros perdidos: VBlanks en que el bucle principal aún no había consumido el anterior.
 * Visible en ngband.sym (g_lost_frames) para el Test_Harness (R17.9). */
extern volatile u16 g_lost_frames;
#endif /* NGBAND_ISR_H */
