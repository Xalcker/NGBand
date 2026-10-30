"use strict";
// NgPlayer: toca la música de una canción de NGBand en el navegador (o en Node) con un emulador del YM2610
// de la Neo Geo: 4 canales FM, 3 tonos SSG (con ruido y envolvente), 6 canales ADPCM-A y el canal ADPCM-B.
//
// La entrada es el mismo Frame_Stream que toca la ROM (ver frames.py y design.md): por cada cuadro de video,
// `count` (1 byte; 255 = el cuadro continúa) y `count` pares (registro, valor). Cada cuadro empieza en el
// puerto A; el par (0xFD, p) elige el puerto p hasta el fin del cuadro; el par (0xFE, n) es el evento
// DRUM(n) (se ignora aquí: el flujo que sale de un VGM trae las escrituras reales de ADPCM-A y no usa DRUM).
// Las escrituras de cada cuadro se aplican al empezar el cuadro, como hace el driver Z80.
//
// Cada canal se renderiza por separado (fm1-4, ssg1-3, adpcma = los 6 canales ADPCM-A juntos, adpcmb): la mezcla
// completa es su suma, así que silenciar (M) o dejar solo (S) un canal en el editor es sumar solo los que se oyen.
//
// No es una emulación exacta ciclo por ciclo. El FM sigue la estructura del chip (como en genplayer.js, sin
// SSG-EG ni el modo especial del canal 3); el SSG es el de un AY-3-8910 (tono, ruido, mezclador, envolvente);
// ADPCM-A y ADPCM-B decodifican los datos de las ROM de samples que trae el VGM (opts.adpcmaRom / adpcmbRom;
// sin ellas esos canales callan). Se emula a la frecuencia propia del FM (reloj / 144, unos 55.6 kHz con 8 MHz) y
// se baja a la frecuencia de salida promediando.

const NgPlayer = (() => {
  const FPS = 60;                              // el Frame_Stream se arma a 60 cuadros por segundo (vgm.py)
  const CHANNEL_IDS = ["fm1", "fm2", "fm3", "fm4", "ssg1", "ssg2", "ssg3", "adpcma", "adpcmb"];
  const CHANNELS = CHANNEL_IDS.length;
  const DEFAULT_CLOCK = 8000000;

  // --- Tablas del FM (las mismas del YM2612/YM2610) ---
  const SIN = new Float32Array(1024);
  for (let i = 0; i < 1024; i++) SIN[i] = Math.sin(((i + 0.5) * 2 * Math.PI) / 1024);
  const ATT = new Float32Array(1024);          // atenuación de 10 bits (0.09375 dB por paso) -> amplitud
  for (let i = 0; i < 1024; i++) ATT[i] = Math.pow(10, (-i * 0.09375) / 20);

  const EG_INC = [
    0, 1, 0, 1, 0, 1, 0, 1,   0, 1, 0, 1, 1, 1, 0, 1,   0, 1, 1, 1, 0, 1, 1, 1,   0, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,   1, 1, 1, 2, 1, 1, 1, 2,   1, 2, 1, 2, 1, 2, 1, 2,   1, 2, 2, 2, 1, 2, 2, 2,
    2, 2, 2, 2, 2, 2, 2, 2,   2, 2, 2, 4, 2, 2, 2, 4,   2, 4, 2, 4, 2, 4, 2, 4,   2, 4, 4, 4, 2, 4, 4, 4,
    4, 4, 4, 4, 4, 4, 4, 4,   4, 4, 4, 8, 4, 4, 4, 8,   4, 8, 4, 8, 4, 8, 4, 8,   4, 8, 8, 8, 4, 8, 8, 8,
    8, 8, 8, 8, 8, 8, 8, 8,
  ];
  const EG_SHIFT = new Uint8Array(64), EG_SELECT = new Uint8Array(64);
  for (let r = 0; r < 64; r++) {
    const rate = r >> 2;
    if (rate < 12) { EG_SHIFT[r] = 11 - rate; EG_SELECT[r] = r & 3; }
    else if (rate < 15) { EG_SHIFT[r] = 0; EG_SELECT[r] = 4 * (rate - 11) + (r & 3); }
    else { EG_SHIFT[r] = 0; EG_SELECT[r] = 16; }
  }
  const DT = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 8, 8, 8, 8],
    [1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 8, 8, 9, 10, 11, 12, 13, 14, 16, 16, 16, 16],
    [2, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 8, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 20, 22, 22, 22, 22],
  ];
  const FN_NOTE = [0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3, 3, 3, 3];
  const LFO_HZ = [3.98, 5.56, 6.02, 6.37, 6.88, 9.63, 48.1, 72.2];
  const PMS_CENTS = [0, 3.4, 6.7, 10, 14, 20, 40, 80];
  const AMS_SHIFT = [8, 3, 1, 0];
  const SLOT_OP = [0, 2, 1, 3];                // los registros van en el orden op1, op3, op2, op4
  const OFF = 0, RELEASE = 1, SUSTAIN = 2, DECAY = 3, ATTACK = 4;

  // --- Mezcla: cuánto pesa cada fuente en la salida (-1..1) ---
  const FM_GAIN = 0.085 / 8192;                // un canal FM a todo volumen pesa 0.085
  const SSG_GAIN = 0.03;                       // un tono SSG a todo volumen (onda de -1 a 1)
  const ADPCMA_GAIN = FM_GAIN * 4;             // un golpe ADPCM-A a todo volumen: la mitad de un canal FM
  const ADPCMB_GAIN = FM_GAIN / 4;

  // --- ADPCM-A (el mismo algoritmo de adpcma.py) ---
  const A_STEPS = [
    16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157,
    173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166,
    1282, 1411, 1552,
  ];
  const A_ADJUST = [-1, -1, -1, -1, 2, 5, 7, 9];
  const sext12 = (v) => ((v & 0xfff) ^ 0x800) - 0x800;
  // ADPCM-B
  const B_ADJUST = [57, 57, 57, 57, 77, 102, 128, 153];

  function newOp() {
    return { dt: 0, mul: 0, tl: 127, rs: 0, ar: 0, d1r: 0, d2r: 0, sl: 0, rr: 0, am: 0,
             phase: 0, incr: 0, vol: 1023, state: OFF, key: false };
  }
  function newChannel() {
    return { fnum: 0, block: 0, kc: 0, alg: 0, fb: 0, ams: 0, pms: 0, pan: 3, fb0: 0, fb1: 0,
             op: [newOp(), newOp(), newOp(), newOp()] };
  }

  function makeChip(clock) {
    const native = clock / 144;
    return {
      clock, native,
      ch: [0, 1, 2, 3].map(newChannel), latch: [0, 0], lfoOn: false, lfoHz: 0, lfoPhase: 0, egCnt: 0, egSub: 0,
      ssg: {
        regs: new Uint8Array(16), tone: [1, 1, 1], tcount: [0, 0, 0], tout: [0, 0, 0],
        ncount: 0, lfsr: 1, nout: 1, ecount: 0, estep: 0, elevel: 0, eholding: false,
        ticks: clock / 4 / 8 / native,             // tics del SSG (media vuelta de un tono = periodo tics de reloj / 4 / 8) por muestra del FM
      },
      a: {
        regs: new Uint8Array(0x30), total: 0,
        ch: Array.from({ length: 6 }, () => ({ on: false, pos: 0, end: 0, accum: 0, index: 0, level: 0, pan: 3, out: 0 })),
      },
      b: {
        regs: new Uint8Array(0x20), on: false, pos: 0, end: 0, accum: 0, delta: 127, frac: 0, nibble: 0, out: 0, prev: 0,
      },
      romA: new Uint8Array(0), romB: new Uint8Array(0),
    };
  }

  // --- FM ---
  function updateIncr(c) {
    c.kc = (c.block << 2) | FN_NOTE[c.fnum >> 7];
    const fc = (c.fnum << c.block) >> 1;
    for (const o of c.op) {
      const dt = DT[o.dt & 3][c.kc] * (o.dt & 4 ? -1 : 1);
      const mul2 = o.mul ? o.mul * 2 : 1;
      o.incr = (((fc + dt) & 0x1ffff) * mul2) >> 1;
    }
  }
  function keyOn(o) { if (o.key) return; o.key = true; o.phase = 0; o.state = ATTACK; }
  function keyOff(o) { if (!o.key) return; o.key = false; if (o.state > RELEASE) o.state = RELEASE; }

  // Registros FM ($30-$BF) de un puerto. En el YM2610 solo existen los desplazamientos 1 y 2 de cada puerto:
  // puerto A -> FM 1 y 2, puerto B -> FM 3 y 4.
  function writeFM(chip, port, reg, v) {
    const n = reg & 3;
    if (n === 3 || n === 0) return;
    const c = chip.ch[port * 2 + n - 1];
    if (reg < 0xa0) {
      const o = c.op[SLOT_OP[(reg >> 2) & 3]];
      switch (reg & 0xf0) {
        case 0x30: o.dt = (v >> 4) & 7; o.mul = v & 15; updateIncr(c); break;
        case 0x40: o.tl = v & 127; break;
        case 0x50: o.rs = v >> 6; o.ar = v & 31; break;
        case 0x60: o.am = v >> 7; o.d1r = v & 31; break;
        case 0x70: o.d2r = v & 31; break;
        case 0x80: o.sl = (v >> 4) === 15 ? 992 : (v >> 4) * 32; o.rr = v & 15; break;
        default: break;                         // $90: SSG-EG (no se emula)
      }
    } else if (reg >= 0xa4 && reg <= 0xa6) chip.latch[port] = v;
    else if (reg >= 0xa0 && reg <= 0xa2) {
      c.fnum = ((chip.latch[port] & 7) << 8) | v;
      c.block = (chip.latch[port] >> 3) & 7;
      updateIncr(c);
    } else if (reg >= 0xb0 && reg <= 0xb2) { c.fb = (v >> 3) & 7; c.alg = v & 7; c.fb0 = c.fb1 = 0; }
    else if (reg >= 0xb4 && reg <= 0xb6) { c.ams = (v >> 4) & 3; c.pms = v & 7; c.pan = v >> 6; }
  }

  // --- SSG ---
  function writeSSG(chip, reg, v) {
    const s = chip.ssg;
    s.regs[reg] = v;
    if (reg <= 5) {
      const i = reg >> 1;
      s.tone[i] = ((s.regs[i * 2 + 1] & 15) << 8) | s.regs[i * 2];
    } else if (reg === 13) {                     // forma de la envolvente: reinicia
      s.estep = 0;
      s.ecount = 0;
      s.eholding = false;
      envLevel(s);
    }
  }
  // Nivel (0-31) de la envolvente en el paso actual (estep sigue contando); bits de la forma: 3 = continuar,
// 2 = ataque, 1 = alternar, 0 = mantener
  function envLevel(s) {
    const shape = s.regs[13] & 15;
    const attack = (shape & 4) !== 0, alt = (shape & 2) !== 0;
    if (s.estep >= 32 && (!(shape & 8) || (shape & 1))) {   // terminó la primera rampa y se queda fijo
      const end = attack ? 31 : 0;
      s.elevel = !(shape & 8) ? 0 : alt ? 31 - end : end;
      s.eholding = true;
      return;
    }
    const up = attack !== (alt && ((s.estep >> 5) & 1) === 1);   // con "alternar" cada rampa cambia de sentido
    const pos = s.estep & 31;
    s.elevel = up ? pos : 31 - pos;
  }
  const SSG_VOL = Array.from({ length: 16 }, (_, i) => (i === 0 ? 0 : Math.pow(10, (-3 * (15 - i)) / 20)));
  const SSG_ENV = Array.from({ length: 32 }, (_, i) => (i === 0 ? 0 : Math.pow(10, (-1.5 * (31 - i)) / 20)));

  // Los 3 tonos del SSG, una muestra del FM: escribe en out[4..6]
  function ssgSample(chip, out) {
    const s = chip.ssg, r = s.regs;
    // Ruido
    s.ncount -= s.ticks;
    const nper = Math.max(1, r[6] & 31) * 2;     // el ruido va a la mitad de la frecuencia de los tonos
    while (s.ncount <= 0) {
      s.ncount += nper;
      const bit = (s.lfsr ^ (s.lfsr >> 3)) & 1;
      s.lfsr = (s.lfsr >> 1) | (bit << 16);
      s.nout = s.lfsr & 1;
    }
    // Envolvente
    const eper = Math.max(1, (r[12] << 8) | r[11]);   // un paso de la envolvente (de 32) = 8 * periodo ciclos del SSG
    if (!s.eholding) {
      s.ecount -= s.ticks;
      while (s.ecount <= 0) { s.ecount += eper; s.estep++; envLevel(s); if (s.eholding) break; }
    }
    for (let i = 0; i < 3; i++) {
      s.tcount[i] -= s.ticks;
      const per = Math.max(1, s.tone[i]);
      while (s.tcount[i] <= 0) { s.tcount[i] += per; s.tout[i] ^= 1; }
      const toneOn = !((r[7] >> i) & 1), noiseOn = !((r[7] >> (i + 3)) & 1);
      // Con el mezclador, un canal "apagado" vale 1 (así deja pasar al otro)
      const bit = (toneOn ? s.tout[i] : 1) & (noiseOn ? s.nout : 1);
      const v = r[8 + i];
      const amp = v & 0x10 ? SSG_ENV[s.elevel] : SSG_VOL[v & 15];
      // Un periodo de 0 o 1 es una señal fija; la salida es unipolar, se centra para quitar la parte continua
      out[4 + i] = (toneOn && s.tone[i] <= 1 && !noiseOn ? 0 : (bit ? 1 : -1)) * amp;
    }
  }

  // --- ADPCM-A ---
  function writeAdpcmA(chip, reg, v) {
    const a = chip.a;
    a.regs[reg] = v;
    if (reg === 0x00) {
      const dump = v & 0x80;
      for (let i = 0; i < 6; i++) {
        if (!((v >> i) & 1)) continue;
        const c = a.ch[i];
        if (dump) c.on = false;
        else {
          c.on = true;
          c.pos = (((a.regs[0x18 + i] << 8) | a.regs[0x10 + i]) << 8) * 2;      // en nibbles
          c.end = ((((a.regs[0x28 + i] << 8) | a.regs[0x20 + i]) << 8) | 0xff) * 2 + 2;
          c.accum = 0; c.index = 0;
          c.level = a.regs[0x08 + i] & 31; c.pan = a.regs[0x08 + i] >> 6;
        }
      }
    } else if (reg === 0x01) a.total = v & 63;
    else if (reg >= 0x08 && reg <= 0x0d) { const c = a.ch[reg - 8]; c.level = v & 31; c.pan = v >> 6; }
  }
  // Los 6 canales ADPCM-A sumados, una muestra de ADPCM-A (clock / 432)
  function adpcmaStep(chip) {
    const a = chip.a, rom = chip.romA;
    let sum = 0;
    for (const c of a.ch) {
      if (!c.on) continue;
      if (c.pos >= c.end || (c.pos >> 1) >= rom.length) { c.on = false; continue; }
      const byte = rom[c.pos >> 1];
      const nibble = c.pos & 1 ? byte & 15 : byte >> 4;
      c.pos++;
      const delta = ((2 * (nibble & 7) + 1) * A_STEPS[c.index]) >> 3;
      c.accum = sext12(nibble & 8 ? c.accum - delta : c.accum + delta);
      c.index = Math.min(48, Math.max(0, c.index + A_ADJUST[nibble & 7]));
      // Atenuación de 0.75 dB por paso (canal + total); con pan apagado el canal no suena
      const att = (c.level ^ 0x1f) + (a.total ^ 0x3f);
      const gain = (15 - (att & 7)) / Math.pow(2, 4 + (att >> 3));
      c.out = c.pan ? c.accum * gain : 0;
      sum += c.out;
    }
    a.sum = sum;
  }

  // --- ADPCM-B ---
  function writeAdpcmB(chip, reg, v) {
    const b = chip.b;
    b.regs[reg] = v;
    if (reg === 0x10) {
      if (v & 1) { b.on = false; b.out = 0; }
      if (v & 0x80) {
        b.on = true;
        b.pos = (((b.regs[0x13] << 8) | b.regs[0x12]) << 8) * 2;
        b.end = ((((b.regs[0x15] << 8) | b.regs[0x14]) << 8) | 0xff) * 2 + 2;
        b.accum = 0; b.delta = 127; b.frac = 1; b.out = 0; b.prev = 0;
      }
    }
  }
  // Una muestra del FM de ADPCM-B: avanza deltaN/65536 nibbles
  function adpcmbSample(chip) {
    const b = chip.b, rom = chip.romB;
    if (!b.on) return 0;
    b.frac += ((b.regs[0x1a] << 8) | b.regs[0x19]) / 65536;
    while (b.frac >= 1) {
      b.frac -= 1;
      if (b.pos >= b.end) {
        if (b.regs[0x10] & 0x10) {              // repetir
          b.pos = (((b.regs[0x13] << 8) | b.regs[0x12]) << 8) * 2;
          b.accum = 0; b.delta = 127;
        } else { b.on = false; b.out = 0; return 0; }
      }
      if ((b.pos >> 1) >= rom.length) { b.on = false; b.out = 0; return 0; }
      const byte = rom[b.pos >> 1];
      const nibble = b.pos & 1 ? byte & 15 : byte >> 4;
      b.pos++;
      const d = ((2 * (nibble & 7) + 1) * b.delta) >> 3;
      b.accum = Math.max(-32768, Math.min(32767, nibble & 8 ? b.accum - d : b.accum + d));
      b.delta = Math.max(127, Math.min(24576, (b.delta * B_ADJUST[nibble & 7]) >> 6));
      b.prev = b.out;
      b.out = b.accum;
    }
    if (!(b.regs[0x11] & 0xc0)) return 0;
    return b.out * (b.regs[0x1b] / 255) / 4;
  }

  // --- Escrituras del chip ---
  function writeChip(chip, port, reg, v) {
    if (port === 0) {
      if (reg <= 0x0d) return writeSSG(chip, reg, v);
      if (reg >= 0x10 && reg <= 0x1c) return writeAdpcmB(chip, reg, v);
      if (reg < 0x30) {
        if (reg === 0x22) { chip.lfoOn = !!(v & 8); chip.lfoHz = LFO_HZ[v & 7]; }
        else if (reg === 0x28) {
          const ch = { 1: 0, 2: 1, 5: 2, 6: 3 }[v & 7];
          if (ch === undefined) return;
          const c = chip.ch[ch];
          for (let i = 0; i < 4; i++) ((v >> (4 + i)) & 1 ? keyOn : keyOff)(c.op[i]);
        }
        return;
      }
      if (reg < 0xc0) writeFM(chip, 0, reg, v);
    } else {
      if (reg <= 0x2d) return writeAdpcmA(chip, reg, v);
      if (reg >= 0x30 && reg < 0xc0) writeFM(chip, 1, reg, v);
    }
  }

  // Aplica las escrituras de un cuadro del Frame_Stream. Devuelve la nueva posición, o -1 al terminar.
  function frameWrites(chip, s, pos) {
    let port = 0;
    for (;;) {
      if (pos >= s.length) return -1;
      const count = s[pos++];
      const pairs = count === 255 ? 254 : count;
      for (let i = 0; i < pairs; i++, pos += 2) {
        const reg = s[pos], v = s[pos + 1];
        if (reg === 0xfd) port = v & 1;
        else if (reg === 0xfe) continue;        // DRUM(n): sin sample map aquí
        else writeChip(chip, port, reg, v);
      }
      if (count !== 255) return pos;
    }
  }

  // --- Envolvente y canal FM (como genplayer.js) ---
  function rate(r, o, c) {
    if (!r) return 0;
    return Math.min(63, r + (c.kc >> (3 - o.rs)));
  }
  function stepEnvelope(chip) {
    const cnt = ++chip.egCnt;
    for (const c of chip.ch) {
      for (const o of c.op) {
        if (o.state === OFF) continue;
        let r;
        if (o.state === ATTACK) r = rate(o.ar * 2, o, c);
        else if (o.state === DECAY) r = rate(o.d1r * 2, o, c);
        else if (o.state === SUSTAIN) r = rate(o.d2r * 2, o, c);
        else r = rate(o.rr * 4 + 2, o, c);
        if (o.state === ATTACK && r >= 62) { o.vol = 0; o.state = DECAY; continue; }
        if (!r) continue;
        const shift = EG_SHIFT[r];
        if (cnt & ((1 << shift) - 1)) continue;
        const inc = EG_INC[EG_SELECT[r] * 8 + ((cnt >> shift) & 7)];
        if (o.state === ATTACK) {
          o.vol += (~o.vol * inc) >> 4;
          if (o.vol <= 0) { o.vol = 0; o.state = DECAY; }
        } else {
          o.vol += inc;
          if (o.state === DECAY && o.vol >= o.sl) o.state = SUSTAIN;
          if (o.vol >= 1023) { o.vol = 1023; if (o.state === RELEASE) o.state = OFF; }
        }
      }
    }
  }
  function op(o, mod, amAtt) {
    const att = o.vol + (o.tl << 3) + (o.am ? amAtt : 0);
    if (att >= 1024) return 0;
    return SIN[((o.phase >> 10) + (mod | 0)) & 1023] * ATT[att] * 8192;
  }
  function channelSample(chip, c, lfoTri) {
    const amAtt = chip.lfoOn ? (Math.round(lfoTri * 126) >> AMS_SHIFT[c.ams]) : 0;
    let pm = 1;
    if (chip.lfoOn && c.pms) pm = Math.pow(2, ((lfoTri * 2 - 1) * PMS_CENTS[c.pms]) / 1200);
    for (const o of c.op) o.phase = (o.phase + o.incr * pm) % 1048576;
    const [o1, o2, o3, o4] = c.op;
    const fb = c.fb ? (c.fb0 + c.fb1) * Math.pow(2, c.fb - 10) : 0;
    const m1 = op(o1, fb, amAtt);
    c.fb1 = c.fb0;
    c.fb0 = m1;
    let out;
    switch (c.alg) {
      case 0: out = op(o4, op(o3, op(o2, m1 / 2, amAtt) / 2, amAtt) / 2, amAtt); break;
      case 1: out = op(o4, op(o3, (m1 + op(o2, 0, amAtt)) / 2, amAtt) / 2, amAtt); break;
      case 2: out = op(o4, (m1 + op(o3, op(o2, 0, amAtt) / 2, amAtt)) / 2, amAtt); break;
      case 3: out = op(o4, (op(o2, m1 / 2, amAtt) + op(o3, 0, amAtt)) / 2, amAtt); break;
      case 4: out = op(o2, m1 / 2, amAtt) + op(o4, op(o3, 0, amAtt) / 2, amAtt); break;
      case 5: out = op(o2, m1 / 2, amAtt) + op(o3, m1 / 2, amAtt) + op(o4, m1 / 2, amAtt); break;
      case 6: out = op(o2, m1 / 2, amAtt) + op(o3, 0, amAtt) + op(o4, 0, amAtt); break;
      default: out = m1 + op(o2, 0, amAtt) + op(o3, 0, amAtt) + op(o4, 0, amAtt); break;
    }
    return c.pan ? Math.max(-8192, Math.min(8191, out)) : 0;   // pan apagado: el canal no suena
  }

  // Toca `frames` cuadros del Frame_Stream. opts: sampleRate (44100), clock (el del YM2610, 8 MHz),
  // adpcmaRom / adpcmbRom (Uint8Array con las ROM de samples), onProgress(f), yieldFn() (para no colgar la página).
  // Devuelve { audio: Float32Array (la mezcla), stems: [Int16Array o null por canal, en CHANNEL_IDS], sampleRate }.
  async function render(stream, frames, opts = {}) {
    const rate = opts.sampleRate || 44100;
    const chip = makeChip(opts.clock || DEFAULT_CLOCK);
    chip.romA = opts.adpcmaRom || new Uint8Array(0);
    chip.romB = opts.adpcmbRom || new Uint8Array(0);
    const NATIVE = chip.native;
    const total = Math.ceil((frames / FPS) * rate);
    const audio = new Float32Array(total);
    const stems = new Array(CHANNELS).fill(null);
    const ch = new Float32Array(CHANNELS);
    const acc = new Float64Array(CHANNELS);
    const gains = [FM_GAIN, FM_GAIN, FM_GAIN, FM_GAIN, SSG_GAIN, SSG_GAIN, SSG_GAIN, ADPCMA_GAIN, ADPCMB_GAIN];
    let pos = 0, native = 0, outIndex = 0, accCount = 0, aPhase = 0;
    const perOut = NATIVE / rate;
    let nextOut = perOut;
    for (let f = 0; f < frames && outIndex < total; f++) {
      if (pos >= 0) pos = frameWrites(chip, stream, pos);
      const end = ((f + 1) * NATIVE) / FPS;
      for (; native < end; native++) {
        if (++chip.egSub === 3) { chip.egSub = 0; stepEnvelope(chip); }
        const lfoTri = chip.lfoOn ? 1 - Math.abs(((chip.lfoPhase = (chip.lfoPhase + chip.lfoHz / NATIVE) % 1) * 2) - 1) : 0;
        for (let i = 0; i < 4; i++) ch[i] = channelSample(chip, chip.ch[i], lfoTri);
        ssgSample(chip, ch);
        if ((aPhase += 1 / 3) >= 1) { aPhase -= 1; adpcmaStep(chip); }   // ADPCM-A: clock / 432
        ch[7] = chip.a.sum || 0;
        ch[8] = adpcmbSample(chip);
        for (let i = 0; i < CHANNELS; i++) acc[i] += ch[i];
        accCount++;
        if (native + 1 >= nextOut) {
          let mix = 0;
          for (let i = 0; i < CHANNELS; i++) {
            const v = (acc[i] / accCount) * gains[i];
            acc[i] = 0;
            if (v !== 0 && !stems[i]) stems[i] = new Int16Array(total);
            if (stems[i]) stems[i][outIndex] = Math.max(-32767, Math.min(32767, Math.round(v * 32767)));
            mix += v;
          }
          accCount = 0;
          audio[outIndex++] = Math.max(-1, Math.min(1, mix));
          nextOut += perOut;
          if (outIndex >= total) break;
        }
      }
      if (f % 300 === 299) {
        if (opts.onProgress) opts.onProgress(f / frames);
        if (opts.yieldFn) await opts.yieldFn();
      }
    }
    return { audio, stems, sampleRate: rate };
  }

  return { render, FPS, CHANNELS, CHANNEL_IDS };
})();

if (typeof module !== "undefined") module.exports = NgPlayer;
