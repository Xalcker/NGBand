/* Canal de comandos 68000 -> Z80 (R12.1, R12.2, R12.8).
 *
 * El registro de comando admite un byte por escritura y cada escritura dispara una NMI en el Z80,
 * así que el ISR de VBlank envía como máximo UN byte por cuadro: un comando sin argumento ocupa un
 * cuadro y uno con argumento ocupa dos (comando, luego argumento). La lógica del juego encola
 * comandos con ac_push (normalmente CMD_FRAME o CMD_HOLD en cada cuadro).
 *
 * La parte de cola y la verificación de desincronía son puras (sin hardware) y se prueban en el
 * host. Solo ac_vblank/ac_hw_init tocan los registros y se excluyen con NGBAND_HOST. */
#ifndef NGBAND_AUDIO_CMD_H
#define NGBAND_AUDIO_CMD_H
#include "types.h"
#include "audio_proto.h"

#define AC_QUEUE_SIZE 16   /* potencia de 2 */
/* Verificación (NGBAND_DEBUG): el Z80 responde cuántos bytes procesó y se compara con los enviados. El Z80
 * procesa en su bucle principal y un cuadro con muchas escrituras (el primero de cada canción, ~145 pares) le
 * toma unos VBlanks: ir atrasado no es una desincronía mientras no dure; un byte perdido deja la diferencia fija
 * y sí se cuenta. Tras CMD_RESET el Z80 rearranca y su respuesta vieja no cuenta por unos VBlanks. */
#define AC_MAX_LAG    32   /* bytes que el Z80 puede ir atrasado (su cola es de 64) */
#define AC_LAG_LIMIT  30   /* VBlanks seguidos con atraso que ya cuentan como desincronía */
#define AC_RESTART_WAIT 60 /* VBlanks de espera tras CMD_RESET */

typedef struct {
  u16 q[AC_QUEUE_SIZE];   /* (comando << 8) | argumento */
  u8  head, tail;         /* índices crecientes; cuenta = tail - head */
  u8  arg_pending;        /* 1 si falta enviar el argumento del último comando */
  u8  arg;
  u8  expected;           /* cuadros del stream enviados desde el último SONG_START (lo lee el Test_Harness) */
  u8  check_enabled;      /* verificación activa (ac_init y ac_set_expected la encienden) */
  u8  overflow;           /* se descartó algún comando por cola llena */
  u16 desync_count;       /* cuadros en que la respuesta no coincidió */
  u8  last_expected, last_reply;   /* datos de la última desincronía */
  u8  grace;              /* VBlanks que quedan sin verificar tras CMD_RESET */
  u8  lag_run;            /* VBlanks seguidos con la respuesta atrasada */
  u8  sent;               /* bytes enviados al Z80, módulo 256 (CMD_RESET lo pone en 0) */
} AudioCmd;

void ac_init(AudioCmd *a);
/* Encola un comando. Devuelve 1 si entró; 0 si la cola está llena o el comando es inválido. */
u8   ac_push(AudioCmd *a, u8 cmd, u8 arg);
u8   ac_pending(const AudioCmd *a);
/* Descarta lo que falta por enviar (p. ej. los cuadros de la vista previa del Menu al empezar a jugar; si no,
 * quedan en la cola y el audio va atrasado respecto a la Chart). Un argumento a medio enviar sí se manda. */
void ac_flush(AudioCmd *a);
/* Saca el siguiente byte a escribir. Devuelve 0 si no hay nada que enviar. Si la cola trae atraso, salta
 * los HOLD que no son el último y junta dos FRAME en un FRAME2. */
u8   ac_next_byte(AudioCmd *a, u8 *byte);
/* Compara la respuesta del Z80 con los cuadros enviados hasta el VBlank anterior.
 * Devuelve 1 si coincide, si va atrasada a lo más AC_MAX_LAG cuadros por menos de AC_LAG_LIMIT VBlanks
 * seguidos, o si la verificación está desactivada; 0 si hay desincronía.
 * Ante una desincronía cuenta el evento y se resincroniza para no repetirlo en cascada. */
u8   ac_check(AudioCmd *a, u8 reply);
/* Fija el valor esperado (p. ej. tras un SEEK, cuyo efecto en la cuenta define 7.3) y reactiva la verificación. */
void ac_set_expected(AudioCmd *a, u8 frames);

#ifndef NGBAND_HOST
void ac_hw_init(void);
/* Llamar una vez por cuadro desde el ISR de VBlank, antes de otros trabajos de audio:
 * lee la respuesta, verifica (si NGBAND_DEBUG) y escribe como máximo un byte. */
void ac_vblank(void);
extern AudioCmd g_audio;
#endif

#endif /* NGBAND_AUDIO_CMD_H */
