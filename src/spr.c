#include "spr.h"
#include "vram_queue.h"

SpriteShadow g_spr;

void spr_init(void) { spr_shadow_init(&g_spr); }

u16 spr_commit(void)
{
  u16 n;
  spr_pool_end(&g_spr);
  g_vq_lock = 1;
  n = spr_flush(&g_spr, &g_vq);
  g_vq_lock = 0;
  return n;
}
