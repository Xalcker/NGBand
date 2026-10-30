/* Estado compartido entre escenas: selección de la partida y escena activa. */
#ifndef NGBAND_GAME_H
#define NGBAND_GAME_H
#include "types.h"
#include "options.h"
#include "song.h"

#define SONG_LEAD_IN 128   /* cuadros de autopista antes de la música; igual a LEAD_IN de songgen.py */

typedef enum {
  SCENE_PLAY, SCENE_END, SCENE_MENU,
  SCENE_TITLE, SCENE_OPTIONS, SCENE_INITIALS
} Scene;   /* SCENE_MENU también es el destino de B en pausa (R3.10) */

typedef struct {
  u8   song;          /* índice en ngband_songs[] (orden alfabético) */
  u8   instrument;    /* INST_GUITAR..INST_DRUMS */
  u8   difficulty;    /* 0 fácil .. 3 experto */
  bool no_fail;
  u8   players;       /* MPLAY_SOLO / VS / COOP (menu_logic.h); la partida de 2 jugadores es la tarea 18.4 */
  u8   instrument2;   /* jugador 2 */
  u8   difficulty2;
  Options opt;
} GameSel;

extern GameSel g_sel;

/* Generado por `ngband list-songs` (build/gen/song_list.c). */
extern const unsigned char ngband_num_songs;
extern const Song *const ngband_songs[];

/* Escena de juego (play.c). play_enter prepara una partida; play_frame corre un cuadro de video. */
void  play_enter(void);
Scene play_frame(void);
/* Resultados: puntos, precisión, combo máximo y estrellas; Start vuelve a jugar. */
void  end_enter(void);
Scene end_frame(void);   /* Start: SCENE_INITIALS si hay NUEVO RECORD; si no, SCENE_MENU */
/* Datos de la última partida terminada (para la pantalla de iniciales). */
bool results_new_record(void);
u8   results_stars(void);
/* Puntaje del récord de la última partida: el del jugador 1 solo, o el de la banda en COOP. */
u32  results_record_score(void);

/* Título, Menu, Options_Screen y entrada de iniciales (screens.c). */
void  title_enter(void);
Scene title_frame(void);
void  menu_enter(void);
Scene menu_frame(void);
void  options_enter(void);
Scene options_frame(void);
void  initials_enter(void);
Scene initials_frame(void);

#endif /* NGBAND_GAME_H */
