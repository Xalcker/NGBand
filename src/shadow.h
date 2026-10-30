/* Modelo de sombra del Audio_Driver (R12.1-R12.4, R12.8, R12.9).
 * Sin dependencia de hardware: compila con SDCC (Z80) y con el compilador del host.
 * Las escrituras al YM2610 salen por el callback `write`. */
#ifndef NGBAND_SHADOW_H
#define NGBAND_SHADOW_H

#include "types.h"

/* Bits de la máscara de canales (silenciado y mapa de instrumentos). */
#define SH_CH_FM1   0   /* FM 1..4 = bits 0..3 */
#define SH_CH_SSG1  4   /* SSG 1..3 = bits 4..6 */
#define SH_FM_COUNT  4
#define SH_SSG_COUNT 3

#define SH_TL_MIN_VOL 0x7F   /* atenuación máxima de un operador FM */

typedef void (*ShadowWriteFn)(u8 port, u8 reg, u8 value);
typedef void (*ShadowDrumFn)(u8 sample);

/* Los Frame_Streams se direccionan con una posición lineal de 32 bits (en el Z80, el desplazamiento en la
 * ROM M1, que pasa de los 64 KB que ve la CPU). `map` deja visible esa posición y devuelve un puntero con al
 * menos SH_MAP_SPAN bytes contiguos a partir de ella: en el Z80 cambia los bancos de 0x8000-0xDFFF; en el
 * host es base + posición. Ningún cuadro del stream ocupa más de SH_MAP_SPAN bytes (lo verifica el build). */
#define SH_MAP_SPAN 0x2000
typedef const u8 *(*ShadowMapFn)(u32 addr);

typedef struct {
  u32 stream;           /* posición del Frame_Stream de la canción */
  u32 end;              /* un byte después del último */
  u16 inst_mask[4];     /* canales de cada instrumento (bits SH_CH_*) */
} SongInfo;

/* Sample ADPCM-A (R13.1): bloques de 256 bytes en la ROM V, como en SampleEntry de adpcma.py
 * (start_block, end_block inclusive). El índice en la tabla es el n de DRUM(n). */
typedef struct {
  u16 start;
  u16 end;
} DrumSample;

#define SH_ADPCMA_CHANNELS 6

/* Un paso de efecto de sonido: un cuadro de duración sobre el canal SSG 3.
 * Tono si (tone_lo | tone_hi) != 0; ruido si noise != 0 (periodo 1..31); vol 0..15. */
typedef struct {
  u8 tone_lo;
  u8 tone_hi;
  u8 vol;
  u8 noise;
} SfxStep;

typedef struct {
  u8 reg[2][256];       /* lo que pide la canción por puerto y registro */
  u16 muted;            /* canales silenciados */
  u16 inst_mask[4];
  u32 start;            /* inicio del stream de la canción vigente (start == end sin canción) */
  u32 pos;              /* siguiente cuadro por leer */
  u32 end;
  u32 ret;              /* dentro de un FS_REPEAT: dónde sigue el stream al terminar la racha */
  u16 rep_left;         /* cuadros que faltan de la racha (0 = no hay FS_REPEAT en curso) */
  const DrumSample *drums;  /* tabla de samples ADPCM-A (NULL si no hay) */
  u8 drum_count;
  u8 drum_next;         /* siguiente canal ADPCM-A (round-robin) */
  u8 drum_muted;        /* batería silenciada hasta el siguiente CMD_UNMUTE_INST (R13.4) */
  u8 paused;            /* CMD_PAUSE activo (R12.7) */
  u8 replay;            /* durante CMD_SONG_SEEK: solo se actualiza la sombra */
  u8 keyon[SH_FM_COUNT];/* último valor de key-on (registro 0x28) de cada canal FM, 0 = apagado */
  u8 sfx_active;        /* efecto en curso sobre el canal SSG 3 (R12.5, R12.6) */
  u8 sfx_id;
  u8 sfx_pos;
  u8 sfx_mix;           /* bits 0x24 del mezclador que impone el efecto */
  u8 frames;            /* cuadros aplicados desde CMD_SONG_START, módulo 256 */
  u8 pending;           /* comando a la espera de su argumento (CMD_NONE si no hay) */
  const SongInfo *songs;
  u8 song_count;
  ShadowWriteFn write;
  ShadowDrumFn drum;    /* puede ser NULL */
  ShadowMapFn map;
  u8 rx_count;          /* bytes recibidos y procesados, módulo 256 (CMD_RESET lo pone en 0) */
} ShadowRegs;

void shadow_init(ShadowRegs *s, ShadowWriteFn write, ShadowDrumFn drum, ShadowMapFn map,
                 const SongInfo *songs, u8 song_count);

/* Escritura de la canción: actualiza la sombra y el chip (con el mínimo si el canal está silenciado). */
void shadow_write(ShadowRegs *s, u8 port, u8 reg, u8 value);

void shadow_silence_all(ShadowRegs *s);          /* CMD_SILENCE_ALL (R12.9) */
void shadow_song_start(ShadowRegs *s, u8 index); /* CMD_SONG_START */
void shadow_frame(ShadowRegs *s);                /* CMD_FRAME (R12.1) */
void shadow_hold(ShadowRegs *s);                 /* CMD_HOLD (R12.8) */
void shadow_mute_inst(ShadowRegs *s, u8 inst);   /* CMD_MUTE_INST (R12.3) */
void shadow_unmute_inst(ShadowRegs *s, u8 inst); /* CMD_UNMUTE_INST (R12.4) */
void shadow_pause(ShadowRegs *s);                /* CMD_PAUSE (R12.7) */
void shadow_resume(ShadowRegs *s);               /* CMD_RESUME (R12.7) */
void shadow_song_seek(ShadowRegs *s, u8 quarter);/* CMD_SONG_SEEK: cuarto 0..3 (R8.6) */
void shadow_sfx(ShadowRegs *s, u8 id);           /* CMD_SFX (R12.5, R12.6) */

/* Tabla de samples ADPCM-A para los eventos DRUM(n) (R13.1). */
void shadow_set_drums(ShadowRegs *s, const DrumSample *drums, u8 count);
/* Cuadros del stream entre `start` y `end` (los cuenta sin aplicarlos). */
u16 shadow_stream_frames(const ShadowRegs *s, u32 start, u32 end);

/* Un comando completo (con su argumento si lo lleva). */
void shadow_command(ShadowRegs *s, u8 cmd, u8 arg);
/* Un byte recibido por el registro de comando: junta comando y argumento. */
void shadow_rx(ShadowRegs *s, u8 byte);
/* Registro de respuesta: bytes procesados (rx_count). El 68000 lo compara con los que mandó: la diferencia es lo
 * que el Z80 tiene atrasado; si no baja, se perdió un byte. */
u8 shadow_response(const ShadowRegs *s);

#endif /* NGBAND_SHADOW_H */
