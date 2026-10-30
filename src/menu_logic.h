/* Lógica pura del Menu, la Options_Screen y la entrada de iniciales (R7, R8.1, R9). Sin hardware:
 * compila en el 68000 y en el host. Las escenas (menu.c) solo dibujan y leen controles. */
#ifndef NGBAND_MENU_LOGIC_H
#define NGBAND_MENU_LOGIC_H
#include "types.h"

/* Renglones del Menu; mismos valores que PR_ROW_* de probe.h (menu.c lo comprueba). */
enum { MROW_SONG, MROW_INSTR, MROW_DIFF, MROW_FAIL, MROW_PLAYERS, MROW_COUNT };

/* Jugadores: 1 jugador, 2 jugadores VS, 2 jugadores COOP (probe.menu_players). */
enum { MPLAY_SOLO, MPLAY_VS, MPLAY_COOP, MPLAY_COUNT };

#define MENU_INSTRUMENTS 4
#define MENU_DIFFICULTIES 4

typedef struct {
  u8 row;
  u8 song, instr, diff;
  bool no_fail;
  u8 players;
  u8 instr2, diff2;
} MenuSel;

/* Estado inicial: cursor en CANCION, valores de partida por defecto (dificultad media). */
void menu_sel_init(MenuSel *m);

/* ↑/↓: mueve el cursor con vuelta circular. `delta` es -1 o +1. */
void menu_move(MenuSel *m, s8 delta);

/* Siguiente instrumento de `avail` (bit i = el instrumento i tiene Chart) en la dirección `delta`,
 * saltando `taken` (0xFF = ninguno). Devuelve `cur` si no hay otro. */
u8 menu_next_instr(u8 avail, u8 cur, s8 delta, u8 taken);

/* Hace que los instrumentos elegidos existan en la canción y, en COOP, no coincidan. */
void menu_fix_instruments(MenuSel *m, u8 avail);

/* ←/→: cambia el valor del renglón actual. `nsongs` canciones; `avail` instrumentos de la
 * canción vigente. Tras cambiar de canción el llamador debe repetir menu_fix_instruments con los
 * instrumentos de la canción nueva. Devuelve true si cambió la canción. */
bool menu_change(MenuSel *m, s8 delta, u8 nsongs, u8 avail);

/* Renglones propios del jugador 2 (control 2): INSTRUMENTO y, solo en COOP, DIFICULTAD. */
enum { M2ROW_INSTR, M2ROW_DIFF };

/* ←/→ del jugador 2 sobre `row2`. Su Instrument es de los de `avail` y, en COOP, distinto del del 1;
 * en VS su Difficulty es la del 1, así que ahí no cambia. Sin efecto en 1 jugador. */
void menu_change2(MenuSel *m, u8 row2, s8 delta, u8 avail);

/* Difficulty que usa el jugador 2 en la partida (VS: la del 1; COOP: la suya). */
u8 menu_diff_of_p2(const MenuSel *m);

/* Textos en español (R7.8). */
const char *menu_row_label(u8 row);
const char *menu_instr_name(u8 instr);
const char *menu_diff_name(u8 diff);
const char *menu_players_name(u8 players);

/* ---- Entrada de las tres iniciales (R9.3) ---- */
typedef struct {
  char ini[3];
  u8 pos;
  bool done;
} IniEdit;

/* Empieza con las últimas iniciales escritas (letras fuera de A-Z se vuelven 'A'). */
void ini_init(IniEdit *e, const char *start);
/* ↑ (+1) / ↓ (-1): cambia la letra bajo el cursor, A-Z con vuelta circular. */
void ini_letter(IniEdit *e, s8 delta);
/* → (+1) / ← (-1): cambia de letra con vuelta circular. */
void ini_move(IniEdit *e, s8 delta);
/* Start/A/C: listo. */
void ini_confirm(IniEdit *e);

#endif /* NGBAND_MENU_LOGIC_H */
