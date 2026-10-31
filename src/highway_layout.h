/* Layout puro del Perspective_Highway (R4.2, R4.4, R4.5, R5.1-R5.6, R5.8, R5.10).
 * Sin hardware ni datos generados: la geometría y el arte llegan en HwyGeom, así que compila en el
 * 68000 y en el host (Property 12, tarea 8.8). `highway.c` enlaza esto con `gfx_data.h` y `g_spr`.
 *
 * Flujo de un cuadro:
 *   hwy_list_begin(list);
 *   hwy_build(list, geom, view_j1, chart, cursor, now);   // una vez por jugador
 *   hwy_apply(list, &shadow);                             // reparte índices del SpritePool
 *
 * Presupuesto (R5.6): `hwy_build` admite sprites por prioridad (gemas y bombo, colas de cerca a lejos,
 * líneas de tiempo) y rechaza cualquiera que haría pasar una línea de barrido del límite del jugador.
 * Por eso lo primero que se descarta son las líneas de tiempo y después las colas lejanas.
 */
#ifndef NGBAND_HIGHWAY_LAYOUT_H
#define NGBAND_HIGHWAY_LAYOUT_H
#include "types.h"
#include "chart.h"
#include "spr_diff.h"

#define HWY_LANES         5
#define HWY_MAX_PLAYERS   2
#define HWY_SCREEN_LINES  224
#define HWY_SCREEN_WIDTH  320
#define HWY_LINE_BUDGET   96     /* R5.6: sprites por línea de barrido, entre todos los jugadores */
#define HWY_MAX_SPRITES   320    /* >= SPR_POOL_GEM + SPR_POOL_TAIL + SPR_POOL_LINE */
#define HWY_MAX_TAILS     48
#define HWY_MAX_BAR_SPR   16     /* sprites contiguos de un bombo */
#define HWY_LOOKAHEAD_EV  160    /* eventos del Chart por mirar adelante */

/* Mismo diseño que `PerspRow` de gfx_data.h (highway.c lo comprueba con _Static_assert). */
typedef struct {
  u16 y;
  u8  hshrink;
  u8  vshrink;
  s16 x_lane[HWY_LANES];
} HwyRow;

/* Geometría y arte (de `ngband gfx`). */
typedef struct {
  const HwyRow *rows;        /* una fila por línea de pantalla desde el horizonte */
  u16 nrows;
  const u8 *row_level;       /* nivel de gema de cada fila */
  const u8 *gem_hshrink;     /* por nivel */
  const u8 *gem_vshrink;
  const u16 *gem_tile;
  u8  levels;
  u16 hit_row;               /* fila de la línea de golpe */
  s16 x_center;              /* centro X con el que se generó la tabla */
  u16 cymbal_tile;           /* rombo de platillo (experto) */
  u16 tail_tile;
  u16 kick_tile;             /* banda del bombo (se repite de lado) */
  u16 line_tile;
  u8  lane_pal[HWY_LANES];   /* paleta de cada carril del Chart (verde, rojo, amarillo, azul, naranja) */
  u8  star_pal;              /* gemas estelares */
  u8  blue_pal;              /* Star_Power activo: colas y líneas azules (R3.7) */
  u8  line_pal;
} HwyGeom;

/* Un jugador. */
typedef struct {
  u8  player;        /* 0 o 1 */
  u8  nplayers;      /* 1 o 2: divide el presupuesto y el SpritePool (R5.10) */
  u8  ncols;         /* columnas: 5 (fácil y medio usan las primeras 3 o 4); 4 en batería (R4.2) */
  bool drums;
  bool expert;       /* batería: platillos como rombos (R4.4) o toms (R4.5) */
  bool mirror;       /* ESPEJO: lane -> n-1-lane con n = carriles de lane_mask, salvo batería (R8.2) */
  bool star_active;  /* Star_Power: colas y líneas azules */
  u8  lane_mask;     /* carriles del Chart que la Difficulty usa */
  u8  fall_frames;   /* cuadros por cada 8 px: 6, 5, 4 o 3 (R5.8) */
  s16 x_origin;      /* X central del Highway de este jugador */
  u16 xscale;        /* 8.8: 256 = ancho de la tabla; < 256 para caber en media pantalla */
  u16 beat_frames;   /* separación de las líneas de tiempo; 0 = sin líneas */
  u8  line_budget;   /* sprites por línea para todo el Highway; 0 = HWY_LINE_BUDGET */
} HwyView;

enum { HWY_CLS_GEM, HWY_CLS_TAIL, HWY_CLS_LINE, HWY_CLS_COUNT };

/* Siempre una fila de tiles (altura 1). */
typedef struct {
  s16 x, y;
  u16 tile;
  u8  pal, hshrink, vshrink, cls;
  u8  player;        /* jugador del sprite */
  u8  counted;       /* ya está en line_cnt */
} HwySprite;

typedef struct {
  HwySprite s[HWY_MAX_SPRITES];
  u16 n;
  u16 dropped;                                  /* candidatos rechazados por presupuesto o pool */
  u16 used[HWY_MAX_PLAYERS][HWY_CLS_COUNT];
  /* Sprites por línea de cada jugador. Mientras un jugador tenga menos sprites que su presupuesto ninguna línea
   * puede pasarse, así que no se cuentan (en el 68000 es lo que más cuesta): `exact[p]` dice si line_cnt[p]
   * ya incluye todos sus sprites. hwy_count_lines() los completa para quien los necesite (el Stage). */
  u8  line_cnt[HWY_MAX_PLAYERS][HWY_SCREEN_LINES];
  u16 total[HWY_MAX_PLAYERS];
  bool exact[HWY_MAX_PLAYERS];
} HwyList;

void hwy_list_begin(HwyList *l);

/* Deja line_cnt con todos los sprites de la lista (lo usa el Stage). */
void hwy_count_lines(HwyList *l);

/* Arma el Highway de un jugador. `cur` es el cursor del Judge de ese jugador (notas pendientes,
 * colas sostenidas y posición de lectura); `now` es el cuadro de la canción. */
void hwy_build(HwyList *l, const HwyGeom *g, const HwyView *v, const Chart *chart,
               const ChartCursor *cur, u16 now);

/* Líneas de pantalla que cubre un sprite: primera línea y cantidad (puede salirse de 0..223). */
void hwy_sprite_lines(const HwySprite *s, s16 *top, u16 *count);

/* X central de un carril del Chart en una fila de la tabla (el bombo y los carriles fuera de las
 * columnas dan el centro del Highway). Lo usa el rayo del Stage (R11.6). */
s16 hwy_lane_x(const HwyGeom *g, const HwyView *v, u16 row, u8 lane);
/* Presupuesto por línea de un jugador. */
u8 hwy_player_budget(const HwyView *v);

/* Reparte la lista en el SpritePool de `sh` (llamar entre spr_pool_begin y spr_pool_end). */
void hwy_apply(const HwyList *l, SpriteShadow *sh);

#endif /* NGBAND_HIGHWAY_LAYOUT_H */
