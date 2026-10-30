/* Máquina de estados del Stage (R11). Pura: el dibujo está en el módulo de escenario. */
#include "stage.h"

void stage_init(StageState *s)
{
  s->crowd_state = CROWD_QUIETO;
  s->light_phase = LIGHT_CIAN;
  s->pulse = 0;
  s->flash = 0;
  s->bolt_lane = 0;
  s->lights_off = false;
}

bool stage_is_beat(u16 frame, u16 lead_in, u16 beat_frames)
{
  return beat_frames && frame >= lead_in && (u16)(frame - lead_in) % beat_frames == 0;
}

void stage_step(StageState *s, const StageInput *in)
{
  /* R11.7: luces apagadas si y solo si todos perdieron; el público queda quieto. */
  s->lights_off = in->all_failed;
  if (in->all_failed) {
    s->crowd_state = CROWD_QUIETO;
    s->pulse = 0;
    s->flash = 0;
    return;
  }

  /* R11.5: el color avanza con cada tiempo solo con Star_Power activo. */
  if (in->beat_tick && in->star_active)
    s->light_phase = (u8)((s->light_phase + 1) & 3);

  /* R11.2-R11.4: público y latido dependen del Combo y del tiempo. */
  if (in->combo < STAGE_CHEER) {
    s->crowd_state = CROWD_QUIETO;
    s->pulse = 0;
  } else {
    if (in->beat_tick)
      s->pulse = STAGE_ATTACK;
    else if (s->pulse)
      s->pulse--;
    s->crowd_state = s->pulse ? CROWD_SALTO : CROWD_BRAZOS;
  }

  /* R11.6: rayo sobre el carril de la última Note y destello. */
  if (in->phrase_done) {
    s->flash = STAGE_FLASH_FRAMES;
    s->bolt_lane = in->last_lane;
  } else if (s->flash) {
    s->flash--;
  }
}
