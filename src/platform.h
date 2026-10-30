/* Registros de la Neo Geo que usan main.c e isr.c (el resto está en neogeo.h). */
#ifndef NGBAND_PLATFORM_H
#define NGBAND_PLATFORM_H
#include "types.h"
#define REG_WATCHDOG   (*(volatile u8 *)0x300001)   /* escribir cualquier valor reinicia el watchdog */
#define PALETTE_RAM    ((volatile u16 *)0x400000)   /* 256 paletas x 16 colores */
#define PALETTE_BACKDROP (*(volatile u16 *)0x401FFE)
/* Palabras de VRAM que se encolan como máximo por VBlank (el resto espera al siguiente). */
#define VBLANK_VQ_BUDGET 360
#endif /* NGBAND_PLATFORM_H */
