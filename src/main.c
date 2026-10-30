/* NGBand: arranque de la Neo Geo y bucle de escenas.
 * ngdevkit aporta la cabecera de la ROM, el vector de reset (crt0) y el enlace de rom_callback_VBlank (isr.c);
 * aquí se inicializan la VRAM, las paletas y los módulos, y cada cuadro se espera la bandera de VBlank. */
#include "game.h"
#include "audio_cmd.h"
#include "fix.h"
#include "gfx_data.h"
#include "isr.h"
#include "input.h"
#include "menu_logic.h"
#include "neogeo.h"
#include "platform.h"
#include "probe.h"
#include "records.h"
#include "spr.h"
#include "vram_queue.h"

GameSel g_sel;
TestProbe g_probe;   /* contrato con el Test_Harness de MAME (probe.h); no es static para aparecer en ngband.sym */

/* Deja la VRAM en cero (sprites ocultos, Fix_Layer vacía), igual que la sombra al arrancar. */
static void vram_clear(void)
{
  u32 a;
  REG_VRAMMOD = 1;
  REG_VRAMADDR = 0;
  for (a = 0; a < 0x8600u; a++) REG_VRAMRW = 0;
}

static void palettes_load(void)
{
  u16 p, c;
  for (p = 0; p < GFX_NUM_PALETTES; p++)
    for (c = 0; c < 16; c++) PALETTE_RAM[p * 16 + c] = gfx_palettes[p][c];
  PALETTE_BACKDROP = 0x8000;   /* negro */
}

static void game_defaults(void)
{
  g_sel.song = 0;
  g_sel.instrument = INST_GUITAR;
  g_sel.difficulty = 1;
  g_sel.no_fail = false;
  g_sel.players = MPLAY_SOLO;
  g_sel.instrument2 = INST_GUITAR;
  g_sel.difficulty2 = 1;
  options_init(&g_sel.opt);
}

static void scene_enter(Scene s)
{
  switch (s) {
    case SCENE_TITLE:    title_enter(); break;
    case SCENE_MENU:     menu_enter(); break;
    case SCENE_OPTIONS:  options_enter(); break;
    case SCENE_INITIALS: initials_enter(); break;
    case SCENE_PLAY:     play_enter(); break;
    case SCENE_END:      end_enter(); break;
  }
}

static Scene scene_frame(Scene s)
{
  switch (s) {
    case SCENE_TITLE:    return title_frame();
    case SCENE_MENU:     return menu_frame();
    case SCENE_OPTIONS:  return options_frame();
    case SCENE_INITIALS: return initials_frame();
    case SCENE_PLAY:     return play_frame();
    case SCENE_END:
    default:             return end_frame();
  }
}

int main(void)
{
  Scene scene = SCENE_TITLE, next;
  vram_clear();
  palettes_load();
  vq_hw_init();
  spr_init();
  fix_init();
  ac_hw_init();
  records_init();
  isr_init();
  game_defaults();
  scene_enter(scene);
  for (;;) {
    isr_wait_frame();
    input_take();
    g_probe.step_count++;          /* un paso por VBlank atendido, también en pausa */
    next = scene_frame(scene);
    if (next != scene) scene_enter(next);
    scene = next;
  }
  return 0;
}
