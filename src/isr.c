#include "isr.h"
#include "platform.h"
#include "audio_cmd.h"
#include "input.h"
#include "probe.h"
#include "vram_queue.h"

volatile u16 g_lost_frames;
static volatile u8  s_vblank_flag;
static volatile u32 s_frames;

void isr_init(void)
{
  s_vblank_flag = 0;
  s_frames = 0;
  g_lost_frames = 0;
}

/* ngdevkit enlaza esta función en el vector de VBlank (confirma la interrupción antes de llamarla). */
void rom_callback_VBlank(void)
{
  REG_WATCHDOG = 0;
  ac_vblank();                 /* primero el audio: todo lo pendiente, byte por byte con confirmación */
  input_poll();                /* una lectura de controles por cuadro */
  (void)vq_flush(VBLANK_VQ_BUDGET);
  if (s_vblank_flag) g_lost_frames++;   /* el bucle principal no llegó a consumir el cuadro anterior */
  s_vblank_flag = 1;
  s_frames++;
  g_probe.vblank_count++;
}

void isr_wait_frame(void)
{
  while (!s_vblank_flag) { }
  s_vblank_flag = 0;
}

u32 isr_frames(void) { return s_frames; }
