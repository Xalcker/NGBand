/* Contrato entre la ROM y el Test_Harness de MAME (tests/autoplay.lua; vive en src/ para que la ROM lo incluya).
 *
 * La ROM define UNA instancia `TestProbe g_probe;` (sin `static`, para que aparezca en build/ngband.sym)
 * y la actualiza en cada cuadro: el ISR de VBlank incrementa `vblank_count` y el bucle principal
 * incrementa `step_count` una vez por VBlank procesado (también en pausa). Los demás campos los
 * escribe la escena que corresponda (menú, juego, resultados). Todo es big endian (68000), sin relleno
 * oculto: los desplazamientos están fijados con _Static_assert y los lee autoplay.lua (tabla PROBE).
 *
 * Además, autoplay.lua lee estos símbolos del juego (sin cambios de formato):
 *   g_cursor[2]  ChartCursor de cada jugador (chart.h), para ver las Notes por entrar a la Hit_Window
 *   g_audio      AudioCmd (audio_cmd.h); se usa g_audio.desync_count (desplazamiento 40)
 *
 * Solo hace falta para pruebas: es barato (92 bytes) y se deja siempre compilado.
 */
#ifndef NGBAND_PROBE_H
#define NGBAND_PROBE_H
#include "types.h"
#include "chart.h"

/* Códigos de pantalla (probe.screen) */
enum { PR_SCREEN_BOOT = 0, PR_SCREEN_TITLE, PR_SCREEN_MENU, PR_SCREEN_PLAY,
       PR_SCREEN_RESULTS, PR_SCREEN_OPTIONS, PR_SCREEN_INITIALS };
/* Renglones del Menu (probe.menu_row) */
enum { PR_ROW_SONG = 0, PR_ROW_INSTR, PR_ROW_DIFF, PR_ROW_FAIL, PR_ROW_PLAYERS, PR_ROW_COUNT };

typedef struct {
  u32 score;
  u16 hit, total, max_combo, stars, failed, new_record;
} ProbeResult;                  /* 16 bytes */

typedef struct {
  u16 screen;                   /*  0 */
  u16 song_frame;               /*  2  PlayClock.frame */
  u16 paused;                   /*  4 */
  u16 menu_row;                 /*  6  renglón con el cursor */
  u32 vblank_count;             /*  8  +1 en cada VBlank (ISR) */
  u32 step_count;               /* 12  +1 por cada VBlank que el bucle principal atendió */
  u16 menu_song;                /* 16  índice en el orden de build/gen/songs.txt */
  u16 menu_instr;               /* 18  0 guitarra, 1 teclado, 2 bajo, 3 batería */
  u16 menu_diff;                /* 20  0 fácil .. 3 experto */
  u16 menu_nofail;              /* 22  1 = SIN FALLO */
  u16 menu_players;             /* 24  0 solo, 1 VS, 2 COOP */
  u16 menu_instr2;              /* 26 */
  u16 menu_diff2;               /* 28 */
  u16 reserved;                 /* 30 */
  ProbeResult p1, p2, band;     /* 32, 48, 64  (válidos en la pantalla de resultados) */
  u16 winner;                   /* 80  0 empate, 1 J1, 2 J2 */
  u16 pad;                      /* 82 */
  u32 best_score;               /* 84  récord de la selección del menú (0 = sin récord) */
  u8  best_ini[3];              /* 88 */
  u8  pad2;                     /* 91 */
} TestProbe;                    /* 92 bytes */

extern TestProbe g_probe;

/* ChartCursor / PendingNote tal como los lee autoplay.lua (CURSOR_*, PN_*). El 68000 alinea a 2 bytes
 * y no hay punteros, así que el diseño es el mismo en el host. */
extern ChartCursor g_cursor[2];
_Static_assert(sizeof(PendingNote) == 8, "PENDING_SIZE");
_Static_assert(sizeof(ChartCursor) == 214, "CURSOR_STRIDE");
_Static_assert(__builtin_offsetof(ChartCursor, head) == 5, "CURSOR_HEAD");
_Static_assert(__builtin_offsetof(ChartCursor, count) == 6, "CURSOR_COUNT");
_Static_assert(__builtin_offsetof(ChartCursor, q) == 8, "CURSOR_Q");
_Static_assert(__builtin_offsetof(PendingNote, end) == 2 && __builtin_offsetof(PendingNote, mask) == 4 &&
               __builtin_offsetof(PendingNote, open) == 5 && __builtin_offsetof(PendingNote, flags) == 6, "PN_*");

#ifdef __m68k__
_Static_assert(sizeof(ProbeResult) == 16, "ProbeResult");
_Static_assert(sizeof(TestProbe) == 92, "TestProbe");
_Static_assert(__builtin_offsetof(TestProbe, vblank_count) == 8, "vblank_count");
_Static_assert(__builtin_offsetof(TestProbe, menu_song) == 16, "menu_song");
_Static_assert(__builtin_offsetof(TestProbe, p1) == 32, "p1");
_Static_assert(__builtin_offsetof(TestProbe, winner) == 80, "winner");
_Static_assert(__builtin_offsetof(TestProbe, best_score) == 84, "best_score");
#endif
#endif /* NGBAND_PROBE_H */
