/* HUD en la Fix_Layer (R5.9, R7.8): puntaje, combo, multiplicador, vida y Star_Power.
 * Lógica pura: arma el mapa deseado en un FixShadow; fix_flush() encola solo lo que cambió.
 * Tiles de la fuente: código ASCII (32..126). Medidor: HUD_TILE_METER + 0..8 píxeles. */
#ifndef NGBAND_HUD_H
#define NGBAND_HUD_H
#include "spr_diff.h"
#include "gameplay.h"

#define HUD_TILE_METER   0x80
#define HUD_PAL_BLANCO   0
#define HUD_PAL_AMARILLO 1
#define HUD_PAL_ROJO     2
#define HUD_PAL_VERDE    3
#define HUD_PAL_AZUL     4
#define HUD_PAL_NARANJA  5

#define HUD_LIFE_TILES   ((LIFE_MAX + 7) / 8)
#define HUD_STAR_TILES   ((STAR_MAX + 7) / 8)
#define HUD_SCORE_DIGITS 8
#define HUD_COMBO_DIGITS 4

/* Escribe `value` con `digits` dígitos, con ceros a la izquierda, saturado al máximo
 * representable. `out` recibe digits+1 bytes (con '\0'). */
void hud_format_uint(char *out, u32 value, u8 digits);
/* Tile del medidor `i` (0 = izquierda) para `value` de `max` unidades (1 unidad = 1 píxel). */
u16  hud_meter_tile(u16 value, u16 i);
/* Paleta de la vida: verde, amarillo (< 5/8) o rojo (< 1/4). */
u8   hud_life_pal(s16 life);
/* Dibuja todo el HUD en `f` (no limpia el resto de la capa). */
void hud_draw(FixShadow *f, const JudgeState *j);
/* HUD compacto de 2 jugadores (R5.10): `player` 0 en la mitad izquierda, 1 en la derecha.
 * Cada mitad ocupa HUD2_WIDTH columnas desde HUD2_COL(player). */
#define HUD2_WIDTH   19
#define HUD2_COL(p)  ((p) ? 21 : 1)
void hud_draw2(FixShadow *f, const JudgeState *j, u8 player);
#endif /* NGBAND_HUD_H */
