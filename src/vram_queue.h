#ifndef NGBAND_VRAM_QUEUE_H
#define NGBAND_VRAM_QUEUE_H
#include "spr_diff.h"

extern VQueue g_vq;
/* 1 mientras el bucle principal encola (spr_commit, fix_flush): ese VBlank no vacía la cola. */
extern volatile u8 g_vq_lock;

void vq_hw_init(void);
/* Llamar solo desde el ISR de VBlank. Vacía hasta `budget` entradas,
 * primero las de prioridad alta (Highway y HUD). Devuelve las escritas. */
u16  vq_flush(u16 budget);

#endif /* NGBAND_VRAM_QUEUE_H */
