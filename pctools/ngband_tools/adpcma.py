"""Conversión de PCM a ADPCM-A del YM2610 y mapa de samples (R13.1, R13.2).

- ``encode`` / ``decode``: códec ADPCM-A (12 bits, nibbles de 4 bits) idéntico al
  decodificador del chip. El resultado se rellena a bloques de 256 bytes, que es
  la granularidad de direccionamiento de ADPCM-A.
- ``build_sample_map``: coloca los samples en la ROM ``V`` y falla con el tamaño
  y el sobrante si no caben (``AdpcmRomOverflow``).
- ``map_drum_hits``: convierte los golpes sampleados de un VGM en eventos
  ``DRUM(n)`` con ``n`` siempre válido para el mapa de samples.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from typing import Iterable, Sequence

BLOCK_BYTES = 256
BLOCK_SAMPLES = BLOCK_BYTES * 2  # dos nibbles por byte
# Espacio de direcciones de ADPCM-A: 16 bits de bloques de 256 bytes = 16 MiB.
MAX_ROM_BYTES = 0x10000 * BLOCK_BYTES
# El índice de DRUM(n) viaja en un byte del Frame_Stream.
MAX_SAMPLES = 256

_STEPS = (
    16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
    97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371,
    408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552,
)
_INDEX_ADJUST = (-1, -1, -1, -1, 2, 5, 7, 9)
# Relleno de fin de bloque: 0x80 = nibbles (8, 0), que se compensan entre sí.
_PAD_BYTE = 0x80


class AdpcmRomOverflow(Exception):
    """Los samples exceden la ROM ``V``."""

    def __init__(self, size: int, capacity: int):
        self.size = size
        self.capacity = capacity
        self.excess = size - capacity
        super().__init__(
            f"Los samples ADPCM-A ocupan {size} bytes y la ROM V tiene "
            f"{capacity} bytes: sobran {self.excess} bytes"
        )


class UnknownDrumSample(KeyError):
    """Un golpe sampleado no tiene sample en el mapa."""


def _sext12(v: int) -> int:
    v &= 0xFFF
    return v - 0x1000 if v & 0x800 else v


def _step(accum: int, index: int, nibble: int) -> tuple[int, int]:
    delta = ((2 * (nibble & 7) + 1) * _STEPS[index]) >> 3
    accum = _sext12(accum - delta if nibble & 8 else accum + delta)
    index = min(48, max(0, index + _INDEX_ADJUST[nibble & 7]))
    return accum, index


def _padded_len(nbytes: int) -> int:
    return max(1, -(-nbytes // BLOCK_BYTES)) * BLOCK_BYTES


def encode(pcm: Sequence[int]) -> bytes:
    """Codifica PCM de 16 bits con signo a ADPCM-A, en bloques de 256 bytes."""
    if len(pcm) == 0:
        raise ValueError("El PCM está vacío")
    nibbles: list[int] = []
    accum, index = 0, 0
    for s in pcm:
        target = max(-2048, min(2047, int(s) >> 4))  # 16 bits -> 12 bits
        best, best_err, best_state = 0, None, (accum, index)
        for n in range(16):
            a, i = _step(accum, index, n)
            err = abs(a - target)
            if best_err is None or err < best_err:
                best, best_err, best_state = n, err, (a, i)
        nibbles.append(best)
        accum, index = best_state
    if len(nibbles) % 2:
        nibbles.append(0)
    data = bytearray(
        (nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2)
    )
    data.extend(bytes([_PAD_BYTE]) * (_padded_len(len(data)) - len(data)))
    return bytes(data)


def decode(data: bytes) -> list[int]:
    """Decodifica ADPCM-A a muestras de 12 bits con signo."""
    out: list[int] = []
    accum, index = 0, 0
    for byte in data:
        for nibble in (byte >> 4, byte & 0xF):
            accum, index = _step(accum, index, nibble)
            out.append(accum)
    return out


@dataclass(frozen=True)
class SampleEntry:
    name: str
    index: int
    start_block: int  # dirección inicial en bloques de 256 bytes
    end_block: int  # último bloque (inclusive), como en los registros del chip
    size: int  # bytes, múltiplo de 256


@dataclass(frozen=True)
class SampleMap:
    entries: tuple[SampleEntry, ...]
    rom_size: int
    used: int
    rom: bytes  # contenido de la ROM V (sin relleno hasta rom_size)

    def __len__(self) -> int:
        return len(self.entries)

    def index_of(self, name: str) -> int:
        for e in self.entries:
            if e.name == name:
                return e.index
        raise UnknownDrumSample(name)


def build_sample_map(
    samples: Iterable[tuple[str, bytes]], rom_size: int = MAX_ROM_BYTES
) -> SampleMap:
    """Coloca samples ADPCM-A ya codificados, uno tras otro, en la ROM ``V``.

    Lanza ``AdpcmRomOverflow`` con el tamaño y el sobrante si no caben.
    """
    if not 0 < rom_size <= MAX_ROM_BYTES:
        raise ValueError(f"rom_size debe estar entre 1 y {MAX_ROM_BYTES}")
    items = list(samples)
    if len(items) > MAX_SAMPLES:
        raise ValueError(f"Hay {len(items)} samples; el máximo es {MAX_SAMPLES}")
    names = [n for n, _ in items]
    if len(set(names)) != len(names):
        raise ValueError("Hay nombres de sample repetidos")

    padded = []
    for name, data in items:
        if not data:
            raise ValueError(f"El sample {name!r} está vacío")
        padded.append((name, bytes(data) + bytes([_PAD_BYTE]) * (_padded_len(len(data)) - len(data))))

    total = sum(len(d) for _, d in padded)
    if total > rom_size:
        raise AdpcmRomOverflow(total, rom_size)

    entries, rom, offset = [], bytearray(), 0
    for i, (name, data) in enumerate(padded):
        entries.append(
            SampleEntry(
                name, i, offset // BLOCK_BYTES,
                (offset + len(data)) // BLOCK_BYTES - 1, len(data),
            )
        )
        rom.extend(data)
        offset += len(data)
    return SampleMap(tuple(entries), rom_size, total, bytes(rom))


def convert_samples(
    pcm_samples: Iterable[tuple[str, Sequence[int]]], rom_size: int = MAX_ROM_BYTES
) -> SampleMap:
    """PCM -> ADPCM-A -> mapa de samples en un solo paso."""
    return build_sample_map(((n, encode(p)) for n, p in pcm_samples), rom_size)


def map_drum_hits(
    hits: Iterable[tuple[int, str]], sample_map: SampleMap
) -> list[tuple[int, int]]:
    """Convierte golpes sampleados ``(cuadro, nombre_de_sample)`` en ``(cuadro, n)``.

    ``n`` es el índice de ``DRUM(n)`` y siempre cumple ``0 <= n < len(sample_map)``.
    Un golpe sin sample en el mapa lanza ``UnknownDrumSample``.
    """
    lookup = {e.name: e.index for e in sample_map.entries}
    events = []
    for frame, name in hits:
        if name not in lookup:
            raise UnknownDrumSample(name)
        events.append((frame, lookup[name]))
    return events


def read_wav_pcm(path: str) -> list[int]:
    """Lee un WAV (8 o 16 bits) y lo mezcla a mono de 16 bits con signo."""
    with wave.open(path, "rb") as w:
        ch, width, raw = w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())
    if width == 1:
        vals = [(b - 128) << 8 for b in raw]
    elif width == 2:
        vals = [int.from_bytes(raw[i:i + 2], "little", signed=True) for i in range(0, len(raw) - 1, 2)]
    else:
        raise ValueError(f"Ancho de muestra no soportado: {width} bytes")
    if ch == 1:
        return vals
    return [sum(vals[i:i + ch]) // ch for i in range(0, len(vals) - ch + 1, ch)]
