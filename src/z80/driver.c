/* Audio_Driver (Z80, SDCC). Recibe los comandos del 68000 por NMI y maneja el YM2610.
 * La lógica está en shadow.c (la misma que se prueba en el host); aquí solo va el acceso a hardware.
 *
 * Puertos de la Neo Geo (Z80):
 *   IN  0x00  registro de comando (leerlo lo consume)
 *   OUT 0x0C  registro de respuesta
 *   IN/OUT 0x04..0x07  YM2610: A dirección, A dato, B dirección, B dato (IN 0x04 = estado, bit 7 = ocupado)
 *   OUT 0x08  habilita la NMI
 *   IN  0x0A / 0x0B  bancos de la M1 (NEO-ZMC): el byte alto del puerto (registro B) elige el banco de
 *             8 KB en 0xC000-0xDFFF / de 16 KB en 0x8000-0xBFFF
 *
 * Mapa: el driver vive en los 32 KB fijos (0x0000-0x7FFF) y los Frame_Streams después, desde 0x8000 de la
 * M1, que puede medir hasta 1 MB. `map_stream` pone la posición pedida en la ventana de 16 KB y los 8 KB
 * siguientes en la de 0xC000, así que desde ella se ven al menos SH_MAP_SPAN bytes seguidos.
 *
 * La NMI solo guarda el byte recibido en una cola; el bucle principal lo procesa y escribe la respuesta.
 * Así un comando largo (CMD_SONG_SEEK) no anida NMIs ni pierde los bytes que llegan mientras tanto.
 *
 * `song_table`/`song_count` los genera el build a partir de src/songs/ (posiciones en la M1).
 * `drum_table`/`drum_count` salen del mapa de samples de `ngband adpcm`.
 * Los efectos (CMD_SFX), la pausa, la búsqueda y los eventos DRUM(n) los resuelve shadow.c;
 * el cuadro lo marca CMD_FRAME/CMD_HOLD del 68000 (los efectos avanzan con esos mismos comandos). */
#include "../shadow.h"
#include "../audio_proto.h"

__sfr __at(0x00) port_cmd;
__sfr __at(0x04) port_ym_a_addr;
__sfr __at(0x05) port_ym_a_data;
__sfr __at(0x06) port_ym_b_addr;
__sfr __at(0x07) port_ym_b_data;
__sfr __at(0x08) port_nmi_enable;
__sfr __at(0x0C) port_reply;

extern const SongInfo song_table[];
extern const u8 song_count;
/* Mapa de samples ADPCM-A (start/end en bloques de 256 bytes, ver adpcma.py), generado por el build. */
extern const DrumSample drum_table[];
extern const u8 drum_count;

ShadowRegs g_sh;   /* global para que salga en el mapa (pruebas en MAME) */

#define RX_SIZE 64   /* potencia de 2: más de un segundo de comandos (el 68000 manda uno por cuadro) */
static volatile u8 rx_buf[RX_SIZE];
static volatile u8 rx_head, rx_tail;
static u8 cur_bank = 0xFF;

/* Banco de 16 KB `bank` en 0x8000-0xBFFF y el de 8 KB que le sigue en 0xC000-0xDFFF (A = bank). */
static void set_banks(u8 bank) __naked
{
  (void)bank;
  __asm
    ld  b, a
    ld  c, #0x0B
    in  a, (c)
    ld  a, b
    add a, a
    add a, #2
    ld  b, a
    ld  c, #0x0A
    in  a, (c)
    ret
  __endasm;
}

static const u8 *map_stream(u32 addr)
{
  const u8 bank = (u8)(addr >> 14);
  if (bank != cur_bank) {
    cur_bank = bank;
    set_banks(bank);
  }
  return (const u8 *)(0x8000u + ((u16)addr & 0x3FFFu));
}

static void ym_write(u8 port, u8 reg, u8 value)
{
  while (port_ym_a_addr & 0x80) { }   /* espera a que el chip no esté ocupado */
  if (port) {
    port_ym_b_addr = reg;
    while (port_ym_a_addr & 0x80) { }
    port_ym_b_data = value;
  } else {
    port_ym_a_addr = reg;
    while (port_ym_a_addr & 0x80) { }
    port_ym_a_data = value;
  }
}

static u8 rx_arg;   /* 1 si el siguiente byte es el argumento de un comando */

/* Llamada desde crt0.s en la NMI (con los registros guardados).
 * Al arrancar, la BIOS deja al Z80 en un bucle en RAM (`jr $` en 0xFFFE) y, con la M1 del cartucho ya
 * mapeada, manda 0x03 (CMD_RESET): el driver tiene que reiniciarse desde 0x0000. Si no, `main` nunca corre.
 * 0x03 como argumento (canción 3, batería, SFX 3) no reinicia: por eso se sigue qué bytes son argumentos. */
void nmi_handler(void)
{
  const u8 b = port_cmd;
  if (rx_arg) {
    rx_arg = 0;
  } else if (b == CMD_RESET) {
    __asm
      jp  0x0000
    __endasm;
  } else if (CMD_HAS_ARG(b)) {
    rx_arg = 1;
  }
  rx_buf[rx_tail & (RX_SIZE - 1)] = b;
  rx_tail++;
}

void main(void)
{
  shadow_init(&g_sh, ym_write, 0, map_stream, song_table, song_count);
  shadow_set_drums(&g_sh, drum_table, drum_count);
  port_reply = 0;
  port_nmi_enable = 0;
  for (;;) {
    while (rx_head != rx_tail) {
      const u8 b = rx_buf[rx_head & (RX_SIZE - 1)];
      rx_head++;
      shadow_rx(&g_sh, b);
      port_reply = shadow_response(&g_sh);
    }
  }
}
