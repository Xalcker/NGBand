"""Seguimiento del estado de registros del YM2610.

El YM2610 tiene cuatro canales FM, tres tonos SSG (más ruido), seis canales ADPCM-A y un canal ADPCM-B.
Se accede por dos puertos: A (VGM `0x58`) y B (VGM `0x59`).

  Puerto A   $00-$0D  SSG; $10-$1C  ADPCM-B; $22 LFO; $24-$27 timers; $28 key-on FM; $30-$BF FM (canales 1 y 2)
  Puerto B   $00-$2D  ADPCM-A; $30-$BF FM (canales 3 y 4)

`Ym2610State.write` guarda el valor y devuelve los eventos que importan para extraer notas: key-on/off de
FM, cambios de frecuencia (bloque y F-number), cambios de periodo y volumen del SSG, y disparos de ADPCM-A/B.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

YM_CLOCK = 8_000_000  # reloj típico del YM2610 en la Neo Geo (el VGM trae el suyo en la cabecera)

FM_CHANNELS = 4
SSG_CHANNELS = 3
ADPCMA_CHANNELS = 6

PORT_A, PORT_B = 0, 1

# Registro $28: los bits 0-2 eligen el canal. El YM2610 solo usa estos códigos (0 y 4 no existen; 3 y 7 tampoco).
_KEYON_CODE_TO_FM = {1: 0, 2: 1, 5: 2, 6: 3}


@dataclass(frozen=True)
class Event:
    """Algo que pasó al escribir un registro.

    kind: "fm_on", "fm_off", "fm_freq", "ssg_period", "ssg_volume", "ssg_mixer", "adpcma_on", "adpcma_off",
    "adpcmb_on", "adpcmb_off". `channel` es el índice del canal (0-based) o 0 si no aplica."""

    kind: str
    channel: int = 0


def fm_pitch(block: int, fnum: int, clock: int = YM_CLOCK) -> float | None:
    """Altura MIDI (con decimales) de un canal FM a partir de su bloque (0-7) y F-number (11 bits).

    Frecuencia = fnum * (clock / 144) / 2^(21 - block)."""
    if fnum <= 0:
        return None
    freq = fnum * clock / 144 / (1 << (21 - block))
    return 69 + 12 * math.log2(freq / 440)


def ssg_pitch(period: int, clock: int = YM_CLOCK) -> float | None:
    """Altura MIDI (con decimales) de un tono SSG a partir de su periodo de 12 bits.

    El SSG del YM2610 corre a clock/4 y divide entre 16 por el periodo: frecuencia = clock / (64 * periodo)."""
    if period <= 0:
        return None
    freq = clock / (64 * period)
    return 69 + 12 * math.log2(freq / 440)


class Ym2610State:
    """Los registros de los dos puertos y lo que se deduce de ellos."""

    def __init__(self, clock: int = YM_CLOCK) -> None:
        self.clock = clock
        self.regs = [[0] * 256, [0] * 256]
        self.keyed = [False] * FM_CHANNELS
        self._freq = [(0, 0)] * FM_CHANNELS  # (bloque, F-number) que ya se aplicó
        self._latch = [0, 0]  # parte alta de la frecuencia ($A4-$A6) que espera a la baja, por puerto
        self.adpcma_on = [False] * ADPCMA_CHANNELS

    # --- consultas ---------------------------------------------------------------------------------

    def fm_freq(self, channel: int) -> tuple[int, int]:
        """(bloque, F-number) vigentes del canal FM `channel` (0-3)."""
        return self._freq[channel]

    def fm_pitch(self, channel: int) -> float | None:
        return fm_pitch(*self._freq[channel], clock=self.clock)

    def ssg_period(self, channel: int) -> int:
        """Periodo de 12 bits del tono SSG `channel` (0-2)."""
        return ((self.regs[0][channel * 2 + 1] & 0x0F) << 8) | self.regs[0][channel * 2]

    def ssg_pitch(self, channel: int) -> float | None:
        return ssg_pitch(self.ssg_period(channel), self.clock)

    def ssg_volume(self, channel: int) -> int:
        """Volumen 0-15 del canal SSG; con el bit de envolvente (bit 4) se cuenta como 15."""
        v = self.regs[0][8 + channel]
        return 15 if v & 0x10 else v & 0x0F

    def ssg_tone_enabled(self, channel: int) -> bool:
        return not (self.regs[0][7] >> channel) & 1

    def ssg_noise_enabled(self, channel: int) -> bool:
        return not (self.regs[0][7] >> (channel + 3)) & 1

    def ssg_noise_period(self) -> int:
        return self.regs[0][6] & 0x1F

    def ssg_audible(self, channel: int) -> bool:
        return self.ssg_volume(channel) > 0 and (self.ssg_tone_enabled(channel) or self.ssg_noise_enabled(channel))

    def adpcma_range(self, channel: int) -> tuple[int, int]:
        """(inicio, fin) en bytes de la ROM ADPCM-A del canal (0-5). Las direcciones se guardan en unidades de 256."""
        b = self.regs[PORT_B]
        start = ((b[0x18 + channel] << 8) | b[0x10 + channel]) << 8
        end = (((b[0x28 + channel] << 8) | b[0x20 + channel]) << 8) | 0xFF
        return start, end

    def adpcmb_range(self) -> tuple[int, int]:
        """(inicio, fin) en bytes de la ROM ADPCM-B."""
        a = self.regs[PORT_A]
        start = ((a[0x13] << 8) | a[0x12]) << 8
        end = (((a[0x15] << 8) | a[0x14]) << 8) | 0xFF
        return start, end

    # --- escritura ---------------------------------------------------------------------------------

    def write(self, port: int, reg: int, value: int) -> list[Event]:
        """Aplica una escritura y devuelve los eventos que provoca."""
        reg &= 0xFF
        value &= 0xFF
        self.regs[port][reg] = value
        if port == PORT_A:
            if reg <= 0x0D:
                return self._write_ssg(reg)
            if reg == 0x10:
                # Bit 7 = inicio de la reproducción; bit 0 es el reset
                return [Event("adpcmb_on")] if value & 0x80 else [Event("adpcmb_off")] if value & 0x01 else []
            if reg == 0x28:
                return self._write_keyon(value)
        else:
            if reg == 0x00:
                return self._write_adpcma_key(value)
        return self._write_fm_freq(port, reg, value)

    def _write_ssg(self, reg: int) -> list[Event]:
        if reg <= 5:
            return [Event("ssg_period", reg // 2)]
        if reg == 7:
            return [Event("ssg_mixer")]
        if 8 <= reg <= 10:
            return [Event("ssg_volume", reg - 8)]
        return []

    def _write_keyon(self, value: int) -> list[Event]:
        channel = _KEYON_CODE_TO_FM.get(value & 7)
        if channel is None:
            return []
        on = bool(value & 0xF0)
        was = self.keyed[channel]
        self.keyed[channel] = on
        if on and not was:
            return [Event("fm_on", channel)]
        if not on and was:
            return [Event("fm_off", channel)]
        return []

    def _write_adpcma_key(self, value: int) -> list[Event]:
        events = []
        dump = bool(value & 0x80)  # 1 = apagar los canales marcados; 0 = encenderlos
        for ch in range(ADPCMA_CHANNELS):
            if not (value >> ch) & 1:
                continue
            if dump:
                self.adpcma_on[ch] = False
                events.append(Event("adpcma_off", ch))
            else:
                self.adpcma_on[ch] = True
                events.append(Event("adpcma_on", ch))
        return events

    def _write_fm_freq(self, port: int, reg: int, value: int) -> list[Event]:
        # Los canales FM usan los desplazamientos 1 y 2 de cada puerto (el 0 no existe en el YM2610)
        if 0xA4 <= reg <= 0xA6:
            self._latch[port] = value
            return []
        if 0xA0 <= reg <= 0xA2:
            offset = reg - 0xA0
            if offset not in (1, 2):
                return []
            channel = port * 2 + offset - 1
            high = self._latch[port]
            self._freq[channel] = ((high >> 3) & 7, ((high & 7) << 8) | value)
            return [Event("fm_freq", channel)]
        return []
