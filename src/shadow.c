/* Modelo de sombra del Audio_Driver. Ver shadow.h. */
#include "shadow.h"
#include "audio_proto.h"
#include <string.h>


/* Operadores portadores por algoritmo, en el orden de los registros (S1, S3, S2, S4 = bits 0..3). */
static const u8 carriers[8] = { 0x8, 0x8, 0x8, 0x8, 0xC, 0xE, 0xE, 0xF };

/* ---- Efectos de sonido (R12.5) ----
 * Cada efecto es una secuencia de pasos de un cuadro sobre el canal SSG 3 (tono + ruido).
 * Derivados de los efectos de menú y de fallo de GENBand (sfx_data.c): periodos del SN76489
 * llevados al SSG del YM2610 (x1.12) y atenuación a volumen (15 - atenuación). */
#define ST(p, v, n) { (u8)((p) & 0xFF), (u8)((p) >> 8), (v), (n) }
#define SFX_LEN(a) ((u8)(sizeof(a) / sizeof((a)[0])))

static const SfxStep sfx_move[] = {
  ST(96, 12, 0), ST(96, 10, 0), ST(96, 8, 0)
};
static const SfxStep sfx_accept[] = {
  ST(120, 12, 0), ST(120, 10, 0), ST(120, 8, 0),
  ST(95, 12, 0),  ST(95, 10, 0),  ST(95, 8, 0),
  ST(80, 12, 0),  ST(80, 10, 0),  ST(80, 8, 0),
  ST(60, 12, 0),  ST(60, 10, 0),  ST(60, 8, 0), ST(60, 6, 0), ST(60, 3, 0)
};
static const SfxStep sfx_back[] = {
  ST(160, 12, 0), ST(160, 10, 0), ST(160, 8, 0), ST(160, 6, 0),
  ST(240, 12, 0), ST(240, 10, 0), ST(240, 8, 0), ST(240, 6, 0), ST(240, 4, 0), ST(240, 2, 0)
};
static const SfxStep sfx_clank[] = {
  ST(1014, 15, 10), ST(1014, 14, 10), ST(1014, 12, 10), ST(1014, 12, 10), ST(1014, 11, 10),
  ST(1014, 10, 10), ST(1014, 9, 10),  ST(1014, 8, 10),  ST(1014, 7, 10),  ST(1014, 6, 10),
  ST(1014, 5, 10),  ST(1014, 4, 10),  ST(1014, 2, 10)
};
static const SfxStep sfx_thud[] = {
  ST(1140, 15, 0), ST(1140, 15, 0), ST(1140, 14, 0), ST(1140, 12, 0), ST(1140, 10, 0),
  ST(1140, 8, 0),  ST(1140, 6, 0),  ST(1140, 4, 0),  ST(1140, 3, 0),  ST(1140, 2, 0), ST(1140, 1, 0)
};
static const SfxStep sfx_bwomp[] = {
  ST(760, 13, 0),  ST(760, 13, 0),  ST(760, 12, 0),  ST(760, 12, 0),
  ST(960, 12, 0),  ST(960, 12, 0),  ST(960, 11, 0),  ST(960, 11, 0),
  ST(1140, 11, 0), ST(1140, 10, 0), ST(1140, 10, 0), ST(1140, 9, 0), ST(1140, 8, 0),
  ST(1140, 7, 0),  ST(1140, 6, 0),  ST(1140, 5, 0),  ST(1140, 4, 0), ST(1140, 3, 0),
  ST(1140, 2, 0),  ST(1140, 1, 0)
};

typedef struct {
  const SfxStep *steps;
  u8 len;
} SfxDef;

static const SfxDef sfx_defs[SFX_COUNT] = {
  { sfx_move,   SFX_LEN(sfx_move) },    /* SFX_MOVE */
  { sfx_accept, SFX_LEN(sfx_accept) },  /* SFX_ACCEPT */
  { sfx_back,   SFX_LEN(sfx_back) },    /* SFX_BACK */
  { sfx_clank,  SFX_LEN(sfx_clank) },   /* SFX_FAIL_CLANK */
  { sfx_thud,   SFX_LEN(sfx_thud) },    /* SFX_FAIL_THUD */
  { sfx_bwomp,  SFX_LEN(sfx_bwomp) },   /* SFX_FAIL_BWOMP */
};

/* El efecto toma el canal SSG 3: tono (4, 5), ruido (6) y volumen (0x0A), más los bits
 * 0x24 del mezclador. */
#define SFX_MIX_BITS 0x24

static bool is_muted(const ShadowRegs *s, u8 ch)
{
  return (s->muted >> ch) & 1;
}

/* Canal FM (0..3) a su puerto y número de canal dentro del puerto (registro & 3 = 1 o 2). */
static u8 fm_port(u8 ch) { return ch >> 1; }
static u8 fm_c(u8 ch)    { return (u8)((ch & 1) + 1); }

static u8 fm_carriers(const ShadowRegs *s, u8 ch)
{
  return carriers[s->reg[fm_port(ch)][0xB0 + fm_c(ch)] & 7];
}

static bool sfx_holds_reg(const ShadowRegs *s, u8 reg)
{
  return s->sfx_active && (reg == 0x04 || reg == 0x05 || reg == 0x06 || reg == 0x0A);
}

/* Deja el canal en el chip como corresponde a su estado de silencio actual. */
static void apply_channel(ShadowRegs *s, u8 ch)
{
  u8 k;
  if (ch < SH_CH_SSG1) {
    const u8 port = fm_port(ch), c = fm_c(ch), mask = fm_carriers(s, ch);
    for (k = 0; k < 4; k++)
      if (mask & (1 << k)) {
        const u8 reg = (u8)(0x40 + 4 * k + c);
        s->write(port, reg, is_muted(s, ch) ? SH_TL_MIN_VOL : s->reg[port][reg]);
      }
  } else if (ch < SH_CH_SSG1 + SH_SSG_COUNT) {
    const u8 reg = (u8)(0x08 + ch - SH_CH_SSG1);
    if (sfx_holds_reg(s, reg)) return;   /* el efecto manda en el canal */
    s->write(0, reg, (is_muted(s, ch) || s->paused) ? 0 : s->reg[0][reg]);
  }
}

/* Escritura al chip de un valor de la canción, con el filtro de silencio, pausa y efecto.
 * No toca la sombra. */
static void chip_write(ShadowRegs *s, u8 port, u8 reg, u8 value)
{
  u8 out = value;

  if (port == 0) {
    if (sfx_holds_reg(s, reg)) return;
    if (reg == 0x07 && s->sfx_active) {
      out = (u8)((value & ~SFX_MIX_BITS) | s->sfx_mix);
    } else if (reg == 0x28) {
      if (s->paused) return;   /* la tecla se repone al reanudar */
    } else if (reg >= 0x08 && reg <= 0x0A) {
      if (is_muted(s, (u8)(SH_CH_SSG1 + reg - 0x08)) || s->paused) out = 0;
    }
  }
  if (reg >= 0x40 && reg < 0x50 && ((reg & 3) == 1 || (reg & 3) == 2)) {
    const u8 ch = (u8)(port * 2 + (reg & 3) - 1);
    const u8 k = (reg >> 2) & 3;
    if (is_muted(s, ch) && (fm_carriers(s, ch) & (1 << k))) out = SH_TL_MIN_VOL;
  } else if (reg >= 0xB1 && reg <= 0xB2) {
    /* Cambió el algoritmo: cambian los portadores. Si el canal está silenciado, se reaplica. */
    const u8 ch = (u8)(port * 2 + reg - 0xB1);
    s->write(port, reg, value);
    if (is_muted(s, ch)) apply_channel(s, ch);
    return;
  }
  s->write(port, reg, out);
}

/* Registra en la sombra. El key-on (0x28) también se recuerda para reponerlo tras una pausa o un salto. */
static void store_reg(ShadowRegs *s, u8 port, u8 reg, u8 value)
{
  s->reg[port][reg] = value;
  if (port == 0 && reg == 0x28) {
    const u8 code = value & 7;
    const u8 idx = (code == 1) ? 0 : (code == 2) ? 1 : (code == 5) ? 2 : (code == 6) ? 3 : 4;
    if (idx < SH_FM_COUNT) s->keyon[idx] = (value & 0xF0) ? value : 0;
  }
}

/* ---- Efectos ---- */
static void sfx_apply(ShadowRegs *s)
{
  const SfxStep *st = &sfx_defs[s->sfx_id].steps[s->sfx_pos];
  const bool tone = (st->tone_lo | st->tone_hi) != 0;
  s->sfx_mix = (u8)((tone ? 0 : 0x04) | (st->noise ? 0 : 0x20));
  s->write(0, 0x04, st->tone_lo);
  s->write(0, 0x05, (u8)(st->tone_hi & 0x0F));
  s->write(0, 0x06, (u8)(st->noise & 0x1F));
  s->write(0, 0x07, (u8)((s->reg[0][0x07] & ~SFX_MIX_BITS) | s->sfx_mix));
  s->write(0, 0x0A, (u8)(st->vol & 0x0F));
}

/* Fin del efecto: el canal vuelve a lo que pide la canción (R12.6). */
static void sfx_release(ShadowRegs *s)
{
  u8 r;
  s->sfx_active = 0;
  for (r = 0x04; r <= 0x07; r++) chip_write(s, 0, r, s->reg[0][r]);
  chip_write(s, 0, 0x0A, s->reg[0][0x0A]);
}

static void sfx_tick(ShadowRegs *s)
{
  if (!s->sfx_active) return;
  s->sfx_pos++;
  if (s->sfx_pos >= sfx_defs[s->sfx_id].len) sfx_release(s);
  else sfx_apply(s);
}

void shadow_sfx(ShadowRegs *s, u8 id)
{
  if (id >= SFX_COUNT) return;
  s->sfx_id = id;
  s->sfx_pos = 0;
  s->sfx_active = 1;
  sfx_apply(s);
}

/* ---- Batería ADPCM-A (R13.1, R13.4) ---- */
static void adpcma_dump_all(ShadowRegs *s)
{
  s->write(1, 0x00, 0x80 | 0x3F);
}

static void drum_trigger(ShadowRegs *s, u8 n)
{
  u8 ch;
  const DrumSample *d;
  if (s->replay) return;
  if (s->drum) s->drum(n);
  if (s->drum_muted || s->paused || s->drums == 0 || n >= s->drum_count) return;
  ch = s->drum_next;
  s->drum_next = (u8)(ch + 1 >= SH_ADPCMA_CHANNELS ? 0 : ch + 1);
  d = &s->drums[n];
  s->write(1, 0x01, 0x3F);                          /* volumen maestro */
  s->write(1, 0x00, (u8)(0x80 | (1 << ch)));        /* corta lo que suene en el canal */
  s->write(1, (u8)(0x08 + ch), 0xDF);               /* izquierda y derecha, volumen máximo */
  s->write(1, (u8)(0x10 + ch), (u8)(d->start & 0xFF));
  s->write(1, (u8)(0x18 + ch), (u8)(d->start >> 8));
  s->write(1, (u8)(0x20 + ch), (u8)(d->end & 0xFF));
  s->write(1, (u8)(0x28 + ch), (u8)(d->end >> 8));
  s->write(1, 0x00, (u8)(1 << ch));                 /* key-on */
}

void shadow_set_drums(ShadowRegs *s, const DrumSample *drums, u8 count)
{
  s->drums = drums;
  s->drum_count = count;
}

void shadow_init(ShadowRegs *s, ShadowWriteFn write, ShadowDrumFn drum, ShadowMapFn map,
                 const SongInfo *songs, u8 song_count)
{
  u8 i;
  s->write = write;
  s->drum = drum;
  s->map = map;
  s->rx_count = 0;
  s->songs = songs;
  s->song_count = song_count;
  s->start = 0;
  s->pos = 0;
  s->end = 0;
  s->rep_left = 0;
  s->drums = 0;
  s->drum_count = 0;
  s->sfx_active = 0;
  for (i = 0; i < 4; i++) s->inst_mask[i] = 0;
  shadow_silence_all(s);
}

void shadow_write(ShadowRegs *s, u8 port, u8 reg, u8 value)
{
  store_reg(s, port, reg, value);
  chip_write(s, port, reg, value);
}

void shadow_silence_all(ShadowRegs *s)
{
  u8 port, k, c, i;
  s->muted = 0;
  s->pending = CMD_NONE;
  s->frames = 0;
  s->paused = 0;
  s->replay = 0;
  s->sfx_active = 0;
  s->sfx_mix = 0;
  s->drum_muted = 0;
  s->drum_next = 0;
  for (i = 0; i < SH_FM_COUNT; i++) s->keyon[i] = 0;
  memset(s->reg, 0, sizeof(s->reg));   /* en el Z80, un bucle de C sobre 512 bytes toma casi un cuadro */
  /* Estado inicial: operadores FM en la atenuación máxima. */
  for (port = 0; port < 2; port++)
    for (k = 0; k < 4; k++)
      for (c = 1; c <= 2; c++) {
        const u8 reg = (u8)(0x40 + 4 * k + c);
        s->reg[port][reg] = SH_TL_MIN_VOL;
        s->write(port, reg, SH_TL_MIN_VOL);
      }
  /* FM: key-off de los cuatro canales. */
  s->write(0, 0x28, 0x01);
  s->write(0, 0x28, 0x02);
  s->write(0, 0x28, 0x05);
  s->write(0, 0x28, 0x06);
  /* SSG: mezclador apagado y volumen 0. */
  s->reg[0][0x07] = 0xFF;
  s->write(0, 0x07, 0xFF);
  for (i = 0x08; i <= 0x0A; i++) s->write(0, i, 0);
  /* ADPCM-A: dump de los 6 canales; ADPCM-B: reset. */
  s->write(1, 0x00, 0xBF);
  s->write(0, 0x10, 0x80);
}

void shadow_song_start(ShadowRegs *s, u8 index)
{
  shadow_silence_all(s);
  s->start = 0;
  s->pos = 0;
  s->end = 0;
  s->rep_left = 0;
  if (index >= s->song_count) return;   /* sin canción: los cuadros no hacen nada */
  s->start = s->songs[index].stream;
  s->pos = s->start;
  s->rep_left = 0;
  s->end = s->songs[index].end;
  {
    u8 i;
    for (i = 0; i < 4; i++) s->inst_mask[i] = s->songs[index].inst_mask[i];
  }
}

/* Fin de lectura del cuadro que empieza en `pos`: el fin del stream o el de la ventana de `map`. */
static const u8 *frame_limit(const u8 *p, u32 pos, u32 end)
{
  const u32 left = end - pos;
  return p + (left < SH_MAP_SPAN ? (u16)left : SH_MAP_SPAN);
}

/* Al empezar un cuadro: si en `pos` hay un FS_REPEAT, la lectura salta a la racha citada. */
static const u8 *enter_repeat(ShadowRegs *s, const u8 *p0)
{
  if (s->rep_left || p0[0] != FS_REPEAT) return p0;
  s->ret = s->pos + FS_REPEAT_SIZE;
  s->rep_left = (u16)(p0[4] | (p0[5] << 8));
  s->pos = s->start + ((u32)p0[3] << 16 | (u16)(p0[1] | (p0[2] << 8)));
  return s->map(s->pos);
}

/* Aplica el cuadro siguiente del stream (o solo lo registra en la sombra durante un salto). */
static void apply_frame(ShadowRegs *s)
{
  if (s->pos < s->end) {
    const u8 *const p0 = enter_repeat(s, s->map(s->pos));
    const u8 *const lim = frame_limit(p0, s->pos, s->end);
    const u8 *p = p0;
    u8 port = 0;
    u8 count;
    do {
      u8 pairs;
      count = *p++;
      pairs = (count == FS_CONTINUATION) ? FS_MAX_PAIRS : count;
      while (pairs--) {
        const u8 a = p[0], b = p[1];
        p += 2;
        if (a == FS_REG_PORT_SELECT)
          port = b & 1;
        else if (a == FS_REG_DRUM)
          drum_trigger(s, b);
        else if (s->replay)
          store_reg(s, port, a, b);
        else
          shadow_write(s, port, a, b);
      }
    } while (count == FS_CONTINUATION && p < lim);
    s->pos += (u16)(p - p0);
    if (s->rep_left && --s->rep_left == 0) s->pos = s->ret;
  }
}

void shadow_frame(ShadowRegs *s)
{
  sfx_tick(s);
  if (s->paused) return;   /* el cuadro y el cursor se conservan (R12.7) */
  apply_frame(s);
  s->frames++;
}

void shadow_hold(ShadowRegs *s)
{
  sfx_tick(s);   /* el stream no avanza ni se consumen escrituras (R12.8); los efectos siguen */
}

void shadow_mute_inst(ShadowRegs *s, u8 inst)
{
  u8 ch;
  u16 newly;
  if (inst >= 4) return;
  if (inst == INST_DRUMS) {
    /* R13.4: corta los canales ADPCM-A y no dispara más DRUM(n) hasta desilenciar. */
    s->drum_muted = 1;
    adpcma_dump_all(s);
  }
  newly = s->inst_mask[inst] & (u16)~s->muted;
  s->muted |= s->inst_mask[inst];
  for (ch = 0; ch < SH_CH_SSG1 + SH_SSG_COUNT; ch++)
    if ((newly >> ch) & 1) apply_channel(s, ch);
}

void shadow_unmute_inst(ShadowRegs *s, u8 inst)
{
  u8 ch;
  u16 changed;
  if (inst >= 4) return;
  if (inst == INST_DRUMS) s->drum_muted = 0;
  changed = s->inst_mask[inst] & s->muted;
  s->muted &= (u16)~s->inst_mask[inst];
  for (ch = 0; ch < SH_CH_SSG1 + SH_SSG_COUNT; ch++)
    if ((changed >> ch) & 1) apply_channel(s, ch);
}

/* ---- Pausa y búsqueda ---- */

/* Repone el chip entero desde la sombra (respetando silencio, pausa y efecto). */
static void resync_chip(ShadowRegs *s)
{
  u8 port, r;
  for (r = 0; r <= 0x0C; r++) chip_write(s, 0, r, s->reg[0][r]);   /* SSG (sin la forma de envolvente) */
  chip_write(s, 0, 0x22, s->reg[0][0x22]);                          /* LFO */
  for (port = 0; port < 2; port++) {
    /* Parte alta de la frecuencia primero: la baja es la que la aplica. */
    for (r = 0x30; r <= 0xB6; r++) {
      if ((r & 3) == 0 || (r & 3) == 3) continue;
      if ((r & 0xFC) == 0xA0 || (r & 0xFC) == 0xA8) continue;
      chip_write(s, port, r, s->reg[port][r]);
    }
    for (r = 0xA0; r <= 0xAA; r++) {
      if ((r & 0xFC) != 0xA0 && (r & 0xFC) != 0xA8) continue;
      if ((r & 3) == 0 || (r & 3) == 3) continue;
      chip_write(s, port, r, s->reg[port][r]);
    }
  }
  if (!s->paused)   /* teclas que seguían presionadas */
    for (r = 0; r < SH_FM_COUNT; r++)
      if (s->keyon[r]) s->write(0, 0x28, s->keyon[r]);
}

void shadow_pause(ShadowRegs *s)
{
  u8 i;
  if (s->paused) return;
  s->paused = 1;
  /* Silencio sin tocar la sombra: FM en key-off, SSG a volumen 0 (salvo un efecto) y batería cortada. */
  s->write(0, 0x28, 0x01);
  s->write(0, 0x28, 0x02);
  s->write(0, 0x28, 0x05);
  s->write(0, 0x28, 0x06);
  for (i = 0; i < SH_SSG_COUNT; i++) apply_channel(s, (u8)(SH_CH_SSG1 + i));
  adpcma_dump_all(s);
}

void shadow_resume(ShadowRegs *s)
{
  if (!s->paused) return;
  s->paused = 0;
  resync_chip(s);
}

u16 shadow_stream_frames(const ShadowRegs *s, u32 pos, u32 end)
{
  u16 n = 0;
  u8 count;
  while (pos < end) {
    const u8 *const p0 = s->map(pos);
    const u8 *const lim = frame_limit(p0, pos, end);
    const u8 *p = p0;
    if (p0[0] == FS_REPEAT) {
      n += (u16)(p0[4] | (p0[5] << 8));
      pos += FS_REPEAT_SIZE;
      continue;
    }
    do {
      count = *p++;
      p += 2u * ((count == FS_CONTINUATION) ? FS_MAX_PAIRS : count);
    } while (count == FS_CONTINUATION && p < lim);
    pos += (u16)(p - p0);
    n++;
  }
  return n;
}

void shadow_song_seek(ShadowRegs *s, u8 quarter)
{
  u16 total, target, i, muted;
  u8 drum_muted, paused, sfx_active, sfx_id, sfx_pos;

  if (s->start == s->end || quarter > 3) return;
  total = shadow_stream_frames(s, s->start, s->end);
  target = (u16)((total >> 2) * quarter);

  muted = s->muted;
  drum_muted = s->drum_muted;
  paused = s->paused;
  sfx_active = s->sfx_active;
  sfx_id = s->sfx_id;
  sfx_pos = s->sfx_pos;

  shadow_silence_all(s);   /* chip en silencio y sombra limpia */
  s->muted = muted;
  s->drum_muted = drum_muted;
  s->paused = paused;

  /* Se vuelve a leer el stream desde el inicio solo hasta la sombra. */
  s->pos = s->start;
  s->rep_left = 0;
  s->replay = 1;
  for (i = 0; i < target; i++) apply_frame(s);
  s->replay = 0;
  s->frames = (u8)target;

  s->sfx_active = sfx_active;
  s->sfx_id = sfx_id;
  s->sfx_pos = sfx_pos;
  resync_chip(s);
  if (sfx_active) sfx_apply(s);
}

void shadow_command(ShadowRegs *s, u8 cmd, u8 arg)
{
  switch (cmd) {
    case CMD_SILENCE_ALL: shadow_silence_all(s); break;
    case CMD_RESET:       shadow_song_start(s, 0xFF); s->rx_count = 0; break;   /* silencio, sin canción */
    case CMD_SONG_START:  shadow_song_start(s, arg); break;
    case CMD_SONG_SEEK:   shadow_song_seek(s, arg); break;
    case CMD_FRAME:       shadow_frame(s); break;
    case CMD_FRAME2:      shadow_frame(s); shadow_frame(s); break;
    case CMD_HOLD:        shadow_hold(s); break;
    case CMD_PAUSE:       shadow_pause(s); break;
    case CMD_RESUME:      shadow_resume(s); break;
    case CMD_MUTE_INST:   shadow_mute_inst(s, arg); break;
    case CMD_UNMUTE_INST: shadow_unmute_inst(s, arg); break;
    case CMD_SFX:         shadow_sfx(s, arg); break;
    default: break;
  }
}

void shadow_rx(ShadowRegs *s, u8 byte)
{
  s->rx_count++;   /* (en el Z80, CMD_RESET reinicia el driver desde la NMI y no llega aquí: la cuenta queda en 0) */
  if (s->pending != CMD_NONE) {
    const u8 cmd = s->pending;
    s->pending = CMD_NONE;
    shadow_command(s, cmd, byte);
  } else if (byte > CMD_NONE && byte < CMD_COUNT) {
    if (CMD_HAS_ARG(byte)) s->pending = byte;
    else shadow_command(s, byte, 0);
  }
}

u8 shadow_response(const ShadowRegs *s)
{
  return s->rx_count;
}
