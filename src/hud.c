#include "hud.h"

#define ROW_SCORE 3   /* las filas 0-1 de la Fix_Layer no se ven en pantalla */
#define ROW_COMBO 4
#define ROW_LIFE  5
#define ROW_STAR  6
#define COL_LABEL 1
#define COL_VALUE 10

/* *v /= 10 y devuelve el resto. En el 68000, con dos divu de 32/16 (la división de 32 bits de libgcc costaba
 * cientos de instrucciones por dígito y el HUD se redibuja en cada acierto). */
static u8 div10(u32 *v)
{
#if defined(__m68k__)
  u32 hi = *v >> 16, lo;
  __asm__("divu.w #10,%0" : "+d"(hi));           /* hi: resto << 16 | cociente */
  lo = (hi & 0xFFFF0000u) | (*v & 0xFFFFu);       /* resto * 65536 + parte baja < 655360: cabe en 16 bits */
  __asm__("divu.w #10,%0" : "+d"(lo));
  *v = ((hi & 0xFFFFu) << 16) | (lo & 0xFFFFu);
  return (u8)(lo >> 16);
#else
  u8 r = (u8)(*v % 10);
  *v /= 10;
  return r;
#endif
}

void hud_format_uint(char *out, u32 value, u8 digits)
{
  u32 max = 1;
  for (u8 i = 0; i < digits && max <= 0xFFFFFFFFu / 10; i++) max *= 10;
  if (digits < 10 && value >= max) value = max - 1;
  for (u8 i = digits; i--; ) out[i] = (char)('0' + div10(&value));
  out[digits] = '\0';
}

u16 hud_meter_tile(u16 value, u16 i)
{
  s32 fill = (s32)value - (s32)i * 8;
  return (u16)(HUD_TILE_METER + (fill <= 0 ? 0 : fill >= 8 ? 8 : fill));
}

u8 hud_life_pal(s16 life)
{
  return life < LIFE_MAX / 4 ? HUD_PAL_ROJO : life < LIFE_MAX * 5 / 8 ? HUD_PAL_AMARILLO : HUD_PAL_VERDE;
}

static u8 put_text(FixShadow *f, u8 col, u8 row, const char *s, u8 pal)
{
  u8 n = 0;
  for (; s[n] && col + n < FIX_COLS; n++) {
    u8 ch = (u8)s[n];
    fix_put(f, (u8)(col + n), row, ch >= 32 && ch < 127 ? ch : 32, pal);
  }
  return n;
}

static void put_meter(FixShadow *f, u8 col, u8 row, u16 value, u16 tiles, u8 pal)
{
  for (u16 i = 0; i < tiles; i++) fix_put(f, (u8)(col + i), row, hud_meter_tile(value, i), pal);
}

void hud_draw2(FixShadow *f, const JudgeState *j, u8 player)
{
  char buf[HUD_SCORE_DIGITS + 1];
  u8 c = HUD2_COL(player), v = (u8)(c + 4);
  u8 mp = j->multiplier > 1 ? HUD_PAL_AMARILLO : HUD_PAL_BLANCO;

  put_text(f, c, ROW_SCORE, player ? "J2" : "J1", player ? HUD_PAL_ROJO : HUD_PAL_AZUL);
  hud_format_uint(buf, j->score, HUD_SCORE_DIGITS);
  put_text(f, v, ROW_SCORE, buf, HUD_PAL_BLANCO);

  put_text(f, c, ROW_COMBO, "CMB", HUD_PAL_AMARILLO);
  hud_format_uint(buf, j->combo, HUD_COMBO_DIGITS);
  put_text(f, v, ROW_COMBO, buf, HUD_PAL_BLANCO);
  fix_put(f, (u8)(v + HUD_COMBO_DIGITS), ROW_COMBO, ' ', HUD_PAL_BLANCO);
  fix_put(f, (u8)(v + HUD_COMBO_DIGITS + 1), ROW_COMBO, 'X', mp);
  fix_put(f, (u8)(v + HUD_COMBO_DIGITS + 2), ROW_COMBO, (u16)('0' + (j->multiplier % 10)), mp);

  put_text(f, c, ROW_LIFE, "VID", HUD_PAL_AMARILLO);
  if (j->failed && !j->no_fail) {
    put_text(f, v, ROW_LIFE, "CAIDO         ", HUD_PAL_ROJO);
  } else if (j->no_fail) {
    put_text(f, v, ROW_LIFE, "SIN FALLO     ", HUD_PAL_AZUL);
  } else {
    u16 life = j->life < 0 ? 0 : (u16)j->life;
    put_meter(f, v, ROW_LIFE, life, HUD_LIFE_TILES, hud_life_pal(j->life));
    put_text(f, (u8)(v + HUD_LIFE_TILES), ROW_LIFE, "        ", HUD_PAL_BLANCO);
  }

  put_text(f, c, ROW_STAR, "EST", HUD_PAL_AMARILLO);
  put_meter(f, v, ROW_STAR, j->star_bar, HUD_STAR_TILES,
            j->star_active ? HUD_PAL_AMARILLO : HUD_PAL_AZUL);
  put_text(f, (u8)(v + HUD_STAR_TILES), ROW_STAR,
           j->star_active ? "*" : j->star_bar >= STAR_MIN ? "!" : " ",
           j->star_active ? HUD_PAL_NARANJA : HUD_PAL_VERDE);
}

void hud_draw(FixShadow *f, const JudgeState *j)
{
  char buf[HUD_SCORE_DIGITS + 1];
  u8 mp = j->multiplier > 1 ? HUD_PAL_AMARILLO : HUD_PAL_BLANCO;

  put_text(f, COL_LABEL, ROW_SCORE, "PUNTOS", HUD_PAL_AMARILLO);
  hud_format_uint(buf, j->score, HUD_SCORE_DIGITS);
  put_text(f, COL_VALUE, ROW_SCORE, buf, HUD_PAL_BLANCO);

  put_text(f, COL_LABEL, ROW_COMBO, "COMBO", HUD_PAL_AMARILLO);
  hud_format_uint(buf, j->combo, HUD_COMBO_DIGITS);
  put_text(f, COL_VALUE, ROW_COMBO, buf, HUD_PAL_BLANCO);
  fix_put(f, COL_VALUE + HUD_COMBO_DIGITS, ROW_COMBO, ' ', HUD_PAL_BLANCO);
  fix_put(f, COL_VALUE + HUD_COMBO_DIGITS + 1, ROW_COMBO, 'X', mp);
  fix_put(f, COL_VALUE + HUD_COMBO_DIGITS + 2, ROW_COMBO, (u16)('0' + (j->multiplier % 10)), mp);

  put_text(f, COL_LABEL, ROW_LIFE, "VIDA", HUD_PAL_AMARILLO);
  if (j->no_fail) {
    put_text(f, COL_VALUE, ROW_LIFE, "SIN FALLO     ", HUD_PAL_AZUL);
  } else {
    u16 life = j->life < 0 ? 0 : (u16)j->life;
    put_meter(f, COL_VALUE, ROW_LIFE, life, HUD_LIFE_TILES, hud_life_pal(j->life));
    put_text(f, COL_VALUE + HUD_LIFE_TILES, ROW_LIFE, "        ", HUD_PAL_BLANCO);
  }

  put_text(f, COL_LABEL, ROW_STAR, "ESTRELLA", HUD_PAL_AMARILLO);
  put_meter(f, COL_VALUE, ROW_STAR, j->star_bar, HUD_STAR_TILES,
            j->star_active ? HUD_PAL_AMARILLO : HUD_PAL_AZUL);
  put_text(f, COL_VALUE + HUD_STAR_TILES + 1, ROW_STAR,
           j->star_active ? "ACTIVA " : j->star_bar >= STAR_MIN ? "PODER! " : "       ",
           j->star_active ? HUD_PAL_NARANJA : HUD_PAL_VERDE);
}
