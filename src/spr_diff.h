/* Lógica pura de sprites, Fix_Layer y cola de VRAM (sin hardware).
 * Compila en el 68000 y en el host (Property 34, R18.3).
 *
 * Mapa de VRAM (palabras de 16 bits), n = sprite de hardware (ver SPR_HW_BASE):
 *   SCB1 0x0000 + n*64 + fila*2 (+1)  tile bajo / atributos
 *   FIX  0x7000 + col*32 + fila       paleta<<12 | tile         (40x32)
 *   SCB2 0x8000 + n                   hshrink<<8 | vshrink
 *   SCB3 0x8200 + n                   (496 - y)<<7 | altura     (altura 0 = oculto)
 *   SCB4 0x8400 + n                   x<<7
 */
#ifndef NGBAND_SPR_DIFF_H
#define NGBAND_SPR_DIFF_H
#include "types.h"

/* Sprites de hardware: 1..381 (el 0 no se usa). Los primeros SPR_TRACK_COUNT son la pista fija (track.c, se
 * escriben una vez por canción y quedan detrás de todo: en la Neo Geo el índice menor se dibuja debajo). La
 * sombra maneja el resto: su índice i es el sprite de hardware SPR_HW_BASE + i. */
#define SPR_HW_SPRITES 381
#define SPR_TRACK_COUNT 28                       /* 14 columnas por jugador */
#define SPR_TRACK_BASE 1
#define SPR_HW_BASE    (SPR_TRACK_BASE + SPR_TRACK_COUNT)
#define SPR_COUNT      (SPR_HW_SPRITES - SPR_TRACK_COUNT)
#ifndef SPR_ROWS_MAX
#define SPR_ROWS_MAX   2          /* filas de tiles por sprite que se guardan en la sombra */
#endif
#define SPR_SCB1_WORDS (SPR_ROWS_MAX * 2)

#define VRAM_SCB1      0x0000u
#define VRAM_FIX       0x7000u
#define VRAM_SCB2      0x8000u
#define VRAM_SCB3      0x8200u
#define VRAM_SCB4      0x8400u

#define FIX_COLS       40
#define FIX_ROWS       32
#define FIX_TILES      (FIX_COLS * FIX_ROWS)

/* Prioridad de la cola: el Highway y el HUD salen antes que el escenario. */
#define VQ_PRIO_HI     0
#define VQ_PRIO_LO     1
#define VQ_HI_CAP      1024
#define VQ_LO_CAP      512

/* Clases del SpritePool: rangos fijos de índices (suman SPR_COUNT). */
enum { SPR_CLASS_GEM, SPR_CLASS_TAIL, SPR_CLASS_LINE, SPR_CLASS_STAGE, SPR_CLASS_COUNT };
#define SPR_POOL_GEM    120
#define SPR_POOL_TAIL   120
#define SPR_POOL_LINE   40
#define SPR_POOL_STAGE  (SPR_COUNT - SPR_POOL_GEM - SPR_POOL_TAIL - SPR_POOL_LINE)

typedef struct { u16 addr, val; } VqEntry;
typedef struct {
  VqEntry hi[VQ_HI_CAP];
  VqEntry lo[VQ_LO_CAP];
  u16 nhi, nlo;
  u16 head_hi, head_lo;   /* lectura (FIFO) */
} VQueue;

typedef struct {
  u16 scb1[SPR_COUNT * SPR_SCB1_WORDS];
  u16 scb2[SPR_COUNT];
  u16 scb3[SPR_COUNT];
  u16 scb4[SPR_COUNT];
} SpriteFrame;

/* want = cuadro armado; sent = lo ya encolado/enviado (la VRAM empieza en 0). */
typedef struct {
  SpriteFrame want, sent;
  u8 pool_cur[SPR_CLASS_COUNT];   /* cursor del cuadro en curso */
  u8 pool_prev[SPR_CLASS_COUNT];  /* usados en el cuadro anterior */
  /* Sprites cuyo `want` cambió desde el último spr_flush: solo esos se comparan con `sent`
   * (en el 68000 revisar los 381 cada cuadro no cabe en el tiempo de un cuadro). */
  u16 dirty_list[SPR_COUNT];
  u16 ndirty;
  u8  dirty[SPR_COUNT];
} SpriteShadow;

typedef struct {
  u16 want[FIX_TILES];
  u16 sent[FIX_TILES];
  u8  dirty[FIX_COLS];   /* columnas con cambios desde el último fix_flush_to */
} FixShadow;

/* Cola */
void vq_init(VQueue *q);
bool vq_push(VQueue *q, u8 prio, u16 addr, u16 val);
bool vq_pop(VQueue *q, VqEntry *out);        /* HI antes que LO */
u16  vq_pending(const VQueue *q);

/* Diff genérico: encola las palabras de want distintas de sent y actualiza sent
 * solo de las encoladas (si la cola se llena, el resto queda pendiente). */
u16  vdiff_words(const u16 *want, u16 *sent, u16 n, u16 vram_base, VQueue *q, u8 prio);

/* Sprites */
void spr_shadow_init(SpriteShadow *s);
u16  spr_class_base(u8 cls);
u16  spr_class_size(u8 cls);
void spr_pool_begin(SpriteShadow *s);
int  spr_pool_alloc(SpriteShadow *s, u8 cls);     /* índice, o -1 si la clase está llena */
void spr_pool_end(SpriteShadow *s);               /* oculta los usados antes y no ahora */
void spr_set(SpriteShadow *s, u16 idx, s16 x, s16 y, u32 tile, u8 pal,
             u8 hshrink, u8 vshrink, u8 height, u8 flip);
void spr_hide(SpriteShadow *s, u16 idx);
u16  spr_flush(SpriteShadow *s, VQueue *q);       /* encola solo los cambios */

/* Fix_Layer */
void fix_shadow_init(FixShadow *f);
void fix_put(FixShadow *f, u8 col, u8 row, u16 tile, u8 pal);
void fix_clear(FixShadow *f);
u16  fix_flush_to(FixShadow *f, VQueue *q);

#endif /* NGBAND_SPR_DIFF_H */
