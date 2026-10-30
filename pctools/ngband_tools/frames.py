"""Frame_Stream: las escrituras del YM2610 agrupadas por cuadro de video (60 Hz).

Formato (ver design.md, "Frame_Stream"). Cada cuadro es:

    count            1 byte, 0..254; 255 = el cuadro continúa (ver abajo)
    count * (a, b)   pares de 2 bytes

  - Un par normal es `(registro, valor)`.
  - Cada cuadro empieza en el puerto A del YM2610. Para escribir en el puerto B se antepone el par
    reservado `(0xFD, puerto)`; el puerto elegido sigue vigente hasta el final del cuadro.
  - El evento de batería `DRUM(n)` es el par reservado `(0xFE, n)` (n = índice de sample ADPCM-A).
  - `count = 255` significa "siguen 254 pares y el MISMO cuadro continúa en el próximo `count`".
    Un cuadro vacío es un solo `count = 0`.

Los registros reales del YM2610 son todos menores que 0xB8, así que 0xFD y 0xFE nunca chocan.

Eliminación de repetidos: una escritura se omite si deja el registro con el mismo valor que ya tiene
(el último escrito en cualquier cuadro anterior o en este mismo). No se omiten las escrituras de
registros que son comandos y no estado (key-on, control de ADPCM, timers): ver `EVENT_REGS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence, Union

REG_PORT_SELECT = 0xFD
REG_DRUM = 0xFE
CONTINUATION = 255
MAX_PAIRS = 254
# count = 254 no es un cuadro de 254 pares (esos salen como CONTINUATION + 0): es REPEAT, solo en la M1 comprimida
REPEAT = 254
REPEAT_SIZE = 6        # REPEAT, desplazamiento (24 bits, desde el inicio del stream), cuadros (16 bits)

# (puerto, registro) que disparan una acción al escribirse: repetir el mismo valor sí tiene efecto.
EVENT_REGS = frozenset(
    {
        (0, 0x10),  # control de ADPCM-B (start/reset)
        (0, 0x27),  # modo del canal 3 y timers
        (0, 0x28),  # key-on / key-off FM
        (1, 0x00),  # key-on / key-off (dump) de ADPCM-A
    }
)


@dataclass(frozen=True)
class RegWrite:
    port: int  # 0 = puerto A, 1 = puerto B
    reg: int
    value: int


@dataclass(frozen=True)
class Drum:
    index: int


Event = Union[RegWrite, Drum]


def _as_event(item) -> Event:
    """Acepta `RegWrite`, `Drum` o un `vgm.Write` (cualquier objeto con port/reg/value)."""
    if isinstance(item, (RegWrite, Drum)):
        return item
    return RegWrite(item.port, item.reg, item.value)


def _check(ev: Event) -> None:
    if isinstance(ev, Drum):
        if not 0 <= ev.index <= 0xFF:
            raise ValueError(f"índice de sample fuera de rango: {ev.index}")
        return
    if ev.port not in (0, 1):
        raise ValueError(f"puerto inválido: {ev.port}")
    if not 0 <= ev.reg < REG_PORT_SELECT:
        raise ValueError(f"registro inválido (0..0xFC): {ev.reg:#x}")
    if not 0 <= ev.value <= 0xFF:
        raise ValueError(f"valor inválido: {ev.value}")


def group_by_frame(items: Iterable[tuple[int, object]], frames: int | None = None) -> list[list[Event]]:
    """Agrupa pares `(cuadro, escritura|Drum)` en una lista de cuadros, conservando el orden.

    Con `frames` el resultado tiene exactamente esa cantidad de cuadros (se descartan los posteriores);
    sin él llega hasta el último cuadro con eventos."""
    items = list(items)
    if any(f < 0 for f, _ in items):
        raise ValueError("cuadro negativo")
    if frames is None:
        frames = max((f for f, _ in items), default=-1) + 1
    out: list[list[Event]] = [[] for _ in range(frames)]
    for f, item in items:
        if f < frames:
            ev = _as_event(item)
            _check(ev)
            out[f].append(ev)
    return out


def dedup_frames(frames: Sequence[Sequence[Event]]) -> list[list[Event]]:
    """Quita las escrituras que repiten el valor que ya tiene el registro. Los `Drum` y `EVENT_REGS` se conservan."""
    shadow: dict[tuple[int, int], int] = {}
    out: list[list[Event]] = []
    for frame in frames:
        kept: list[Event] = []
        for ev in frame:
            if isinstance(ev, RegWrite):
                key = (ev.port, ev.reg)
                if key not in EVENT_REGS and shadow.get(key) == ev.value:
                    continue
                shadow[key] = ev.value
            kept.append(ev)
        out.append(kept)
    return out


def build_frames(items: Iterable[tuple[int, object]], frames: int | None = None) -> list[list[Event]]:
    """Agrupa por cuadro y elimina los repetidos: lo que se serializa."""
    return dedup_frames(group_by_frame(items, frames))


def encode_stream(frames: Sequence[Sequence[Event]]) -> bytes:
    """Codifica los cuadros tal cual (la eliminación de repetidos es de `dedup_frames`/`build_frames`)."""
    out = bytearray()
    for frame in frames:
        pairs: list[tuple[int, int]] = []
        port = 0
        for ev in frame:
            _check(ev)
            if isinstance(ev, Drum):
                pairs.append((REG_DRUM, ev.index))
                continue
            if ev.port != port:
                port = ev.port
                pairs.append((REG_PORT_SELECT, port))
            pairs.append((ev.reg, ev.value))
        while len(pairs) >= MAX_PAIRS:   # un resto de 254 pares se confundiría con REPEAT
            out.append(CONTINUATION)
            for a, b in pairs[:MAX_PAIRS]:
                out += bytes((a, b))
            pairs = pairs[MAX_PAIRS:]
        out.append(len(pairs))
        for a, b in pairs:
            out += bytes((a, b))
    return bytes(out)


def decode_stream(data: bytes) -> list[list[Event]]:
    """Lector de prueba: el inverso de `encode_stream`. Lanza ValueError si el stream está truncado."""
    frames: list[list[Event]] = []
    pos = 0
    n = len(data)
    while pos < n:
        frame: list[Event] = []
        port = 0
        while True:
            if pos >= n:
                raise ValueError("Frame_Stream truncado: falta el count")
            count = data[pos]
            pos += 1
            pairs = MAX_PAIRS if count == CONTINUATION else count
            if pos + 2 * pairs > n:
                raise ValueError("Frame_Stream truncado: faltan pares")
            for i in range(pairs):
                a, b = data[pos + 2 * i], data[pos + 2 * i + 1]
                if a == REG_DRUM:
                    frame.append(Drum(b))
                elif a == REG_PORT_SELECT:
                    if b not in (0, 1):
                        raise ValueError(f"puerto inválido en el stream: {b}")
                    port = b
                else:
                    frame.append(RegWrite(port, a, b))
            pos += 2 * pairs
            if count != CONTINUATION:
                break
        frames.append(frame)
    return frames


def format_c_array(data: bytes, name: str = "song_stream", per_line: int = 16) -> str:
    """Serializa el stream como arreglo C (lo que va en `song.c`)."""
    lines = []
    for i in range(0, len(data), per_line):
        lines.append("    " + ", ".join(f"0x{b:02X}" for b in data[i : i + per_line]) + ",")
    body = "\n".join(lines)
    return f"const unsigned char {name}[{len(data)}] = {{\n{body}\n}};\n" if data else f"const unsigned char {name}[1] = {{ 0 }};\n"


def parse_c_array(text: str, name: str = "song_stream") -> bytes:
    """Lee de vuelta el arreglo C escrito por `format_c_array`."""
    m = re.search(rf"\b{re.escape(name)}\s*\[\s*(\d+)\s*\]\s*=\s*\{{(.*?)\}}\s*;", text, re.S)
    if not m:
        raise ValueError(f"no se encontró el arreglo {name}")
    size = int(m.group(1))
    data = bytes(int(tok, 0) for tok in re.findall(r"0[xX][0-9A-Fa-f]+|\d+", m.group(2)))
    if len(data) != size and not (size == 1 and data == b"\0" and "{ 0 }" in m.group(0)):
        raise ValueError(f"tamaño declarado {size} distinto de los {len(data)} bytes del arreglo")
    return b"" if len(data) == 1 and size == 1 and data == b"\0" and "{ 0 }" in m.group(0) else data


def split_frames(data: bytes) -> list[bytes]:
    """Los cuadros codificados de un Frame_Stream (un cuadro continuado va entero)."""
    out, p = [], 0
    while p < len(data):
        start = p
        while True:
            count = data[p]
            p += 1 + 2 * (MAX_PAIRS if count == CONTINUATION else count)
            if count != CONTINUATION or p >= len(data):
                break
        if p > len(data):
            raise ValueError("Frame_Stream truncado")
        out.append(data[start:p])
    return out


def compress_stream(data: bytes, window: int = 64) -> bytes:
    """Comprime un Frame_Stream para la ROM M1: una racha de cuadros que ya sonó se cambia por
    REPEAT(desplazamiento, cuadros), que el driver Z80 lee de la misma ROM. La racha citada es siempre de
    cuadros literales (sin REPEAT dentro), así el driver solo guarda un punto de regreso."""
    frames = split_frames(data)
    n = len(frames)
    literal_at: list[int | None] = [None] * n   # posición en la salida de cada cuadro que quedó literal
    seen: dict[bytes, list[int]] = {}
    out = bytearray()
    i = 0
    while i < n:
        best_bytes, best_j, best_len = 0, -1, 0
        for j in seen.get(frames[i], [])[-window:]:
            length = size = 0
            while (i + length < n and j + length < i and length < 0xFFFF and literal_at[j + length] is not None
                   and frames[j + length] == frames[i + length]
                   and literal_at[j + length] == literal_at[j] + size):
                size += len(frames[i + length])
                length += 1
            if size > best_bytes:
                best_bytes, best_j, best_len = size, j, length
        if best_bytes > REPEAT_SIZE + 2:
            off = literal_at[best_j]
            out += bytes((REPEAT, off & 0xFF, (off >> 8) & 0xFF, off >> 16, best_len & 0xFF, best_len >> 8))
            i += best_len
        else:
            literal_at[i] = len(out)
            seen.setdefault(frames[i], []).append(i)
            out += frames[i]
            i += 1
    if len(out) >= 1 << 24:
        raise ValueError("Frame_Stream comprimido de más de 16 MB")
    return bytes(out)


def expand_stream(data: bytes) -> bytes:
    """El inverso de `compress_stream` (como lo lee el driver Z80)."""
    out = bytearray()
    p = 0
    while p < len(data):
        if data[p] == REPEAT:
            off = data[p + 1] | data[p + 2] << 8 | data[p + 3] << 16
            count = data[p + 4] | data[p + 5] << 8
            q = off
            for _ in range(count):
                (frame,) = split_frames(_one_frame(data, q))
                if frame[0] == REPEAT:
                    raise ValueError("REPEAT dentro de una racha citada")
                out += frame
                q += len(frame)
            p += REPEAT_SIZE
        else:
            frame = _one_frame(data, p)
            out += frame
            p += len(frame)
    return bytes(out)


def _one_frame(data: bytes, p: int) -> bytes:
    if data[p] == REPEAT:
        return data[p:p + REPEAT_SIZE]
    start = p
    while True:
        count = data[p]
        p += 1 + 2 * (MAX_PAIRS if count == CONTINUATION else count)
        if count != CONTINUATION:
            return data[start:p]
