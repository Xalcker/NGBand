/* Pista fija (ver track.h). El arte lo genera `ngband gfx` (gfx.py, draw_track): TRACK_COLS columnas de
 * GFX_PISTA_ROWS tiles; cada celda tiene 8 tiles seguidos, uno por fase, y la autoanimación de 3 bits del LSPC
 * reemplaza los 3 bits bajos del tile con su contador. */
#include "track.h"
#include "gfx_data.h"
#include "neogeo.h"
#include "options.h"
#include "spr_diff.h"
#include "vram_queue.h"

#define REG_LSPCMODE (*(volatile u16 *)0x3C0006)   /* bits 15-8: cuadros por paso de la autoanimación - 1 */
#define LSPC_ANIM_OFF 0x0008                       /* bit 3: autoanimación detenida */
#define SCB1_ANIM8    0x0008                       /* atributo: autoanimación de 3 bits (8 tiles) */
#define PER_PLAYER    (SPR_TRACK_COUNT / 2)

_Static_assert(GFX_PISTA_COLS <= PER_PLAYER, "la pista no cabe en los sprites reservados");
_Static_assert(GFX_PISTA_TILE % GFX_PISTA_PHASES == 0, "la autoanimación necesita tiles alineados a 8");

static u16 s_anim;      /* REG_LSPCMODE con la pista en marcha */

static void push(u16 addr, u16 val)
{
  (void)vq_push(&g_vq, VQ_PRIO_HI, addr, val);
}

void track_show(const HwyView *views, u8 nviews, u8 speed_idx)
{
  u8 v, c, r;
  u8 steps = speed_steps_per4(speed_idx);   /* pasos de la canción cada 4 cuadros de video */
  u8 fall = views[0].fall_frames ? views[0].fall_frames : 4;
  u16 n;
  /* Las gemas bajan 8 px cada `fall` pasos; las franjas, PERIOD/PHASES px por fase:
   * cuadros de video por fase = (PERIOD/PHASES) * fall / 8 * 4 / steps. */
  n = (u16)(((u16)(GFX_PISTA_PERIOD / GFX_PISTA_PHASES) * fall * 4 + steps * 4) / (8u * steps));
  if (n < 1) n = 1;
  s_anim = (u16)((n - 1) << 8);
  g_vq_lock = 1;
  for (v = 0; v < nviews && v < 2; v++) {
    const HwyView *w = &views[v];
    const u8 hs = (u8)((16 * w->xscale + 128) / 256 - 1);   /* ancho de columna - 1 */
    for (c = 0; c < PER_PLAYER; c++) {
      const u16 spr = (u16)(SPR_TRACK_BASE + v * PER_PLAYER + c);
      if (c >= GFX_PISTA_COLS) { push((u16)(VRAM_SCB3 + spr), 0); continue; }
      /* X de la columna: la de 1 jugador escalada alrededor del centro del Highway */
      s16 x = (s16)(w->x_origin + ((s32)(GFX_PISTA_X0 + c * 16 - 160) * w->xscale) / 256);
      for (r = 0; r < GFX_PISTA_ROWS; r++) {
        const u32 tile = (u32)GFX_PISTA_TILE + ((u32)c * GFX_PISTA_ROWS + r) * GFX_PISTA_PHASES;
        push((u16)(VRAM_SCB1 + spr * 64 + r * 2), (u16)tile);
        push((u16)(VRAM_SCB1 + spr * 64 + r * 2 + 1),
             (u16)((GFX_PISTA_PAL << 8) | (((tile >> 16) & 0xF) << 4) | SCB1_ANIM8));
      }
      push((u16)(VRAM_SCB2 + spr), (u16)(((u16)hs << 8) | 0xFF));
      push((u16)(VRAM_SCB3 + spr), (u16)((((496 - GFX_PISTA_Y0) & 0x1FF) << 7) | GFX_PISTA_ROWS));
      push((u16)(VRAM_SCB4 + spr), (u16)((x & 0x1FF) << 7));
    }
  }
  for (; v < 2; v++)
    for (c = 0; c < PER_PLAYER; c++) push((u16)(VRAM_SCB3 + SPR_TRACK_BASE + v * PER_PLAYER + c), 0);
  g_vq_lock = 0;
  REG_LSPCMODE = s_anim;
}

void track_pause(bool paused)
{
  REG_LSPCMODE = (u16)(s_anim | (paused ? LSPC_ANIM_OFF : 0));
}

void track_hide(void)
{
  u16 i;
  g_vq_lock = 1;
  for (i = 0; i < SPR_TRACK_COUNT; i++) push((u16)(VRAM_SCB3 + SPR_TRACK_BASE + i), 0);
  g_vq_lock = 0;
  REG_LSPCMODE = LSPC_ANIM_OFF;
}
