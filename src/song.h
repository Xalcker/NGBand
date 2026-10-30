/* Ficha de canción en ROM, generada por `ngband import-song` en src/songs/<n>/song.c. */
#ifndef NGBAND_SONG_H
#define NGBAND_SONG_H

#include "types.h"
#include "chart.h"

typedef struct {
  u32 title_hash;           /* hash de título + juego, ID del récord (R9.2) */
  const char *title;
  const char *game;
  u16 total_frames;
  u16 beat_frames;
  u32 perfect[4][4];        /* puntaje perfecto por instrumento y dificultad */
  Chart chart[4][4];        /* instrumento x dificultad (guitarra, teclado, bajo, batería) */
  const u8 *stream;         /* Frame_Stream, en la ventana del Z80 */
  u32 stream_len;
  u8 sample_count;
  u16 inst_mask[4];         /* canales de cada instrumento para silenciarlo (SongInfo.inst_mask):
                               FM1-4 = bits 0-3, SSG1-3 = bits 4-6; la batería ADPCM-A no usa bits */
} Song;

#endif /* NGBAND_SONG_H */
