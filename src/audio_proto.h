/* Protocolo 68000 -> Z80 (R12.1, R12.2). Compartido por el driver Z80 y por audio_cmd.c.
 * Un byte por escritura en el registro de comando. Los comandos con argumento se envían como
 * dos bytes consecutivos: comando y argumento (no hay RAM compartida entre las dos CPU). */
#ifndef NGBAND_AUDIO_PROTO_H
#define NGBAND_AUDIO_PROTO_H

#define CMD_NONE         0x00  /* no es un comando; nunca se envía */
#define CMD_SILENCE_ALL  0x01  /* sin argumento */
#define CMD_SONG_START   0x02  /* arg: índice de canción */
#define CMD_RESET        0x03  /* sin argumento: lo manda la BIOS al pasar el Z80 al cartucho; para la canción */
#define CMD_FRAME        0x04  /* sin argumento */
#define CMD_HOLD         0x05  /* sin argumento */
#define CMD_PAUSE        0x06  /* sin argumento */
#define CMD_RESUME       0x07  /* sin argumento */
#define CMD_MUTE_INST    0x08  /* arg: instrumento */
#define CMD_UNMUTE_INST  0x09  /* arg: instrumento */
#define CMD_SFX          0x0A  /* arg: id de efecto (SFX_*) */
#define CMD_FRAME2       0x0B  /* sin argumento: aplica dos cuadros (velocidad 125%: 5 pasos en 4 cuadros) */
#define CMD_SONG_SEEK    0x0C  /* arg: cuarto 0..3 (no usa 0x03: ese código lo envía la BIOS sin argumento) */
#define CMD_COUNT        0x0D

/* Efectos de sonido (argumento de CMD_SFX, R12.5): menú y 3 efectos de fallo. */
#define SFX_MOVE         0
#define SFX_ACCEPT       1
#define SFX_BACK         2
#define SFX_FAIL_CLANK   3
#define SFX_FAIL_THUD    4
#define SFX_FAIL_BWOMP   5
#define SFX_COUNT        6

/* Instrumentos (argumento de CMD_MUTE_INST / CMD_UNMUTE_INST). */
#define INST_GUITAR      0
#define INST_KEYS        1
#define INST_BASS        2
#define INST_DRUMS       3
#define INST_COUNT       4

/* Formato del Frame_Stream (ver pctools/ngband_tools/frames.py). */
#define FS_CONTINUATION    255   /* count = 255: siguen 254 pares y el cuadro continúa */
#define FS_MAX_PAIRS       254
/* count = 254 (solo en la M1, ver compress_stream): REPEAT, desplazamiento de 24 bits desde el inicio del
 * stream y n de 16 bits. Suenan los n cuadros literales que empiezan ahí y la lectura sigue tras el REPEAT. */
#define FS_REPEAT          254
#define FS_REPEAT_SIZE     6
#define FS_REG_PORT_SELECT 0xFD  /* (0xFD, puerto): puerto vigente hasta el fin del cuadro */
#define FS_REG_DRUM        0xFE  /* (0xFE, n): evento DRUM(n) */

/* Devuelve 1 si el comando lleva un byte de argumento. */
#define CMD_HAS_ARG(c) ((c) == CMD_SONG_START || (c) == CMD_SONG_SEEK || \
                        (c) == CMD_MUTE_INST || (c) == CMD_UNMUTE_INST || (c) == CMD_SFX)

#endif /* NGBAND_AUDIO_PROTO_H */
