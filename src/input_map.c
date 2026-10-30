#include "input_map.h"

u8 input_lane_mask(u16 raw) {
  u8 m = 0;
  bool both = (raw & PAD_LEFT) && (raw & PAD_RIGHT);
  if (!both) {
    if (raw & PAD_LEFT)  m |= LANE_GREEN;
    if (raw & PAD_RIGHT) m |= LANE_YELLOW;
  }
  if (raw & PAD_DOWN) m |= LANE_RED;
  if (raw & PAD_B)    m |= LANE_BLUE;
  if (raw & PAD_C)    m |= LANE_ORANGE;
  return m;
}

void input_update(PadState *s, u16 raw) {
  u8 now = input_lane_mask(raw);
  u8 before = input_lane_mask(s->prev_raw);
  bool power = (raw & PAD_A) != 0;
  bool power_before = (s->prev_raw & PAD_A) != 0;

  s->in.pressed = now;
  s->in.edge = (u8)(now & ~before);
  s->power = power;
  s->power_edge = power && !power_before;
  s->pause_edge = (raw & PAD_START) && !(s->prev_raw & PAD_START);
  s->prev_raw = raw;
}
