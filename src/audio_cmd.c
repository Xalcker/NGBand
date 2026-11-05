#include "audio_cmd.h"

void ac_init(AudioCmd *a)
{
  u8 *p = (u8 *)a;
  u16 i;
  for (i = 0; i < sizeof(*a); i++) p[i] = 0;
  a->check_enabled = 1;
}

u8 ac_pending(const AudioCmd *a)
{
  return (u8)(a->tail - a->head);
}

u8 ac_push(AudioCmd *a, u8 cmd, u8 arg)
{
  if (cmd == CMD_NONE || cmd >= CMD_COUNT) return 0;
  if (ac_pending(a) >= AC_QUEUE_SIZE) { a->overflow = 1; return 0; }
  a->q[a->tail & (AC_QUEUE_SIZE - 1)] = (u16)(((u16)cmd << 8) | (CMD_HAS_ARG(cmd) ? arg : 0));
  a->tail++;
  return 1;
}

u8 ac_next_byte(AudioCmd *a, u8 *byte)
{
  u16 e;
  u8 cmd;
  if (a->arg_pending) {
    a->arg_pending = 0;
    *byte = a->arg;
    a->sent++;
    return 1;
  }
  if (!ac_pending(a)) return 0;
  e = a->q[a->head & (AC_QUEUE_SIZE - 1)];
  a->head++;
  cmd = (u8)(e >> 8);
  /* Con atraso en la cola (un comando de dos bytes, como un silencio al fallar, deja un byte de más que nunca
   * se recupera a un byte por VBlank), se recupera: un HOLD de sobra no se manda (el stream no avanza con él)
   * y dos FRAME seguidos van como un FRAME2. */
  while (cmd == CMD_HOLD && ac_pending(a)) {
    e = a->q[a->head & (AC_QUEUE_SIZE - 1)];
    a->head++;
    cmd = (u8)(e >> 8);
  }
  if (cmd == CMD_FRAME && ac_pending(a) && (a->q[a->head & (AC_QUEUE_SIZE - 1)] >> 8) == CMD_FRAME) {
    a->head++;
    cmd = CMD_FRAME2;
  }
  *byte = cmd;
  if (CMD_HAS_ARG(cmd)) {
    a->arg = (u8)e;
    a->arg_pending = 1;
  }
  a->sent++;
  /* Cuadros del stream desde el último SILENCE_ALL/SONG_START (los que el Z80 aplicó cuando procese todo). */
  switch (cmd) {
    case CMD_RESET:
      a->grace = AC_RESTART_WAIT;
      a->boot_wait = AC_RESET_WAIT;
      a->sent = 0;                 /* el Z80 rearranca con la cuenta en 0: el RESET mismo no se cuenta */
      /* fall through */
    case CMD_SILENCE_ALL:
    case CMD_SONG_START:
      a->expected = 0;
      break;
    case CMD_FRAME:      a->expected++; break;
    case CMD_FRAME2:     a->expected = (u8)(a->expected + 2); break;
    default: break;
  }
  return 1;
}

void ac_flush(AudioCmd *a)
{
  a->head = a->tail;   /* solo escribe `head`: el ISR lo avanza, pero nunca toca `tail` */
}

u8 ac_check(AudioCmd *a, u8 reply)
{
  const u8 lag = (u8)(a->sent - reply);
  if (!a->check_enabled) return 1;
  if (a->grace) {
    if (lag <= AC_MAX_LAG) a->grace = 0;   /* el Z80 ya rearrancó */
    else { a->grace--; return 1; }
  }
  if (lag == 0) { a->lag_run = 0; return 1; }
  if (lag <= AC_MAX_LAG && a->lag_run < AC_LAG_LIMIT) { a->lag_run++; return 1; }
  a->lag_run = 0;
  a->desync_count++;
  a->last_expected = a->sent;
  a->last_reply = reply;
  a->sent = reply;                          /* se resincroniza para no repetirla en cascada */
  return 0;
}

u8 ac_pump(AudioCmd *a, u8 (*reply)(void), void (*write)(u8))
{
  u8 n = 0, b;
  u16 spin;
  if (a->boot_wait) { a->boot_wait--; return 0; }   /* la respuesta todavía es la del driver de la BIOS */
  while (n < AC_BYTES_PER_VBLANK && (a->arg_pending || ac_pending(a))) {
    /* CMD_RESET (el primero que se manda, con el driver de la BIOS todavía corriendo) no espera respuesta. */
    const u8 reset = !a->arg_pending && (u8)(a->q[a->head & (AC_QUEUE_SIZE - 1)] >> 8) == CMD_RESET;
    if (!reset) {
      for (spin = 0; reply() != a->sent; spin++) {
        if (spin >= AC_ACK_SPIN) {
          /* Sin respuesta: el Z80 no ha tomado el byte anterior. Escribir ahora lo pisaría; se reintenta en el
           * siguiente VBlank. Si no llega en AC_LAG_LIMIT VBlanks, el byte se perdió: se cuenta y se sigue. */
          if (n == 0 && ++a->stall >= AC_LAG_LIMIT) {
            a->stall = 0;
            a->desync_count++;
            a->last_expected = a->sent;
            a->last_reply = reply();
            a->sent = a->last_reply;
            continue;
          }
          return n;
        }
      }
    }
    a->stall = 0;
    if (!ac_next_byte(a, &b)) break;
    write(b);
    n++;
    if (reset) break;   /* el Z80 rearranca: lo demás espera al siguiente VBlank */
  }
  return n;
}

void ac_set_expected(AudioCmd *a, u8 frames)
{
  a->expected = frames;
  a->check_enabled = 1;
}

#ifndef NGBAND_HOST
#include "neogeo.h"

AudioCmd g_audio;

/* El Z80 arranca con el driver de sonido de la BIOS, que se queda esperando en un bucle en RAM; aunque la M1
 * del cartucho ya esté mapeada, nuestro driver no corre hasta recibir CMD_RESET (salta a 0x0000). */
void ac_hw_init(void)
{
  ac_init(&g_audio);
  ac_push(&g_audio, CMD_RESET, 0);
}

static u8 hw_reply(void) { return REG_SOUND_REPLY; }
static void hw_write(u8 b) { REG_SOUND = b; }

void ac_vblank(void)
{
#ifdef NGBAND_DEBUG
  /* El Z80 ya procesó todo lo escrito en cuadros anteriores. Una desincronía queda contada en
   * g_audio.desync_count (visible en ngband.sym para el Test_Harness). */
  (void)ac_check(&g_audio, REG_SOUND_REPLY);
#endif
  (void)ac_pump(&g_audio, hw_reply, hw_write);
}
#endif
