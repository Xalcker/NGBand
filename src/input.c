#include "input.h"
#include "neogeo.h"

static PadState pads[2];          /* lo que lee el ISR en cada VBlank */
static PadState taken[2];         /* lo que ve el paso del bucle principal (input_take) */
/* Flancos entre el ISR y el bucle principal: cada flanco invierte su bit (carriles 0-4, A = 5, Start = 6).
 * Solo el ISR escribe s_tog y solo el bucle principal escribe s_seen, así que no hace falta apagar las
 * interrupciones. Si el bucle pierde un VBlank, el flanco de ese VBlank no se pierde: lo ve el paso siguiente. */
static volatile u8 s_tog[2];
static u8 s_seen[2];

/* Convierte el byte de lógica negativa en lógica positiva con Start en bit 8. */
static u16 raw_read(u8 cnt, u8 status, u8 start_bit) {
  u16 raw = (u16)(~cnt & 0xFF);
  if (!((status >> start_bit) & 1)) raw |= PAD_START;
  return raw;
}

static void poll_one(u8 p, u16 raw) {
  PadState *s = &pads[p];
  input_update(s, raw);
  s_tog[p] ^= (u8)(s->in.edge | (s->power_edge ? 0x20 : 0) | (s->pause_edge ? 0x40 : 0));
}

void input_poll(void) {
  u8 status = REG_STATUS_B;
  poll_one(0, raw_read(REG_P1CNT, status, 0));
  poll_one(1, raw_read(REG_P2CNT, status, 2));
}

void input_take(void) {
  u8 p;
  for (p = 0; p < 2; p++) {
    const u8 tog = s_tog[p];
    const u8 e = (u8)(tog ^ s_seen[p]);
    s_seen[p] = tog;
    taken[p] = pads[p];
    taken[p].in.edge = (u8)(e & 0x1F);
    taken[p].power_edge = (e & 0x20) != 0;
    taken[p].pause_edge = (e & 0x40) != 0;
  }
}

const PadState *input_get(u8 player) {
  return &taken[player & 1];
}
