/* Lógica pura del Practice_Mode (R8.5-R8.10). */
#include "practice.h"

u16 practice_quarter_frame(u16 total_frames, u8 q) {
  return (u16)(((u32)total_frames * q) / 4u);
}

void practice_init(Practice *p, u8 mode, u8 start_q, u16 total_frames) {
  p->active = mode != 0;
  p->marks = false;
  p->total = total_frames;
  p->loop_start = practice_quarter_frame(total_frames, (u8)(start_q > 3 ? 3 : start_q));
  p->loop_end = mode >= 1 && mode <= 3 ? practice_quarter_frame(total_frames, mode) : total_frames;
  if ((s32)p->loop_end - (s32)p->loop_start < PRACTICE_MIN_LOOP) p->loop_end = total_frames;
}

u8 practice_seek_quarter(const Practice *p) {
  u8 q;
  for (q = 3; q > 0; q--)
    if (practice_quarter_frame(p->total, q) <= p->loop_start) break;
  return q;
}

void practice_skip_notes(const Practice *p, const Chart *chart, ChartCursor *cur) {
  while (cur->index < chart->count) {
    const ChartEv *ev = &chart->ev[cur->index];
    u16 frame;
    if (ev->lanes == CHART_EV_END) break;
    frame = (u16)(cur->frame + ev->delta_lo);
    if (frame >= p->loop_start) break;
    cur->frame = frame;
    cur->index++;
  }
}

bool practice_at_end(const Practice *p, u16 frame) {
  return p->active && frame >= p->loop_end;
}

bool practice_mark_start(Practice *p, u16 pause_frame) {
  s32 start = (s32)pause_frame - PRACTICE_LEAD;
  if (!p->active) return false;
  if (start < 0) start = 0;
  if ((s32)p->loop_end - start < PRACTICE_MIN_LOOP) return false;
  p->loop_start = (u16)start;
  p->marks = true;
  return true;
}

bool practice_mark_end(Practice *p, u16 pause_frame) {
  if (!p->active) return false;
  if (pause_frame > p->total) return false;
  if ((s32)pause_frame - (s32)p->loop_start < PRACTICE_MIN_LOOP) return false;
  p->loop_end = pause_frame;
  p->marks = true;
  return true;
}

bool practice_pause_exit(bool c_edge) { return c_edge; }
