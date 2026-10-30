#include "fix.h"
#include "vram_queue.h"

FixShadow g_fix;

void fix_init(void) { fix_shadow_init(&g_fix); }

u8 fix_text(u8 col, u8 row, const char *s, u16 tile_base, u8 pal)
{
  u8 n = 0;
  for (; *s && col + n < FIX_COLS; s++, n++) {
    u8 ch = (u8)*s;
    fix_put(&g_fix, (u8)(col + n), row, (u16)(tile_base + (ch >= 32 && ch < 127 ? ch : 32)), pal);
  }
  return n;
}

u16 fix_flush(void)
{
  u16 n;
  g_vq_lock = 1;
  n = fix_flush_to(&g_fix, &g_vq);
  g_vq_lock = 0;
  return n;
}
