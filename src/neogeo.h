/* Registros del LSPC de la Neo Geo usados por el driver de VRAM. */
#ifndef NGBAND_NEOGEO_H
#define NGBAND_NEOGEO_H
#include "types.h"

#define REG_VRAMADDR (*(volatile u16 *)0x3C0000)
#define REG_VRAMRW   (*(volatile u16 *)0x3C0002)
#define REG_VRAMMOD  (*(volatile u16 *)0x3C0004)

/* Controles (lógica negativa: 0 = presionado). */
#define REG_P1CNT    (*(volatile u8 *)0x300000)  /* bits: 0 ↑, 1 ↓, 2 ←, 3 →, 4 A, 5 B, 6 C, 7 D */
#define REG_P2CNT    (*(volatile u8 *)0x340000)
#define REG_STATUS_B (*(volatile u8 *)0x380000)  /* bit 0 P1 Start, 2 P2 Start (lógica negativa) */

/* Z80: escribir dispara la NMI; leer devuelve la respuesta del Z80 (0x320000 en ambos casos). */
#define REG_SOUND       (*(volatile u8 *)0x320000)
#define REG_SOUND_REPLY (*(volatile u8 *)0x320000)

#endif /* NGBAND_NEOGEO_H */
