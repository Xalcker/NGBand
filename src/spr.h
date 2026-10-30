#ifndef NGBAND_SPR_H
#define NGBAND_SPR_H
#include "spr_diff.h"

extern SpriteShadow g_spr;

void spr_init(void);
/* Encola los cambios del cuadro en la cola de VRAM (R18.3). */
u16  spr_commit(void);

#endif /* NGBAND_SPR_H */
