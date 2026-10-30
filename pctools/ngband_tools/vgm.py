"""Lector de VGM para el YM2610 (Neo Geo).

Un VGM guarda la música como escrituras a los registros del chip con esperas en muestras de 44.1 kHz.
Aquí se lee `.vgm` o `.vgz` (el mismo formato comprimido con gzip) y se saca:

  - las escrituras del YM2610 con su instante (`Write`; chip "ym0" = puerto A, VGM `0x58`; "ym1" = puerto B, `0x59`);
  - los bloques de datos de ADPCM-A (tipo `0x81`) y ADPCM-B (tipo `0x82`);
  - el bucle, la duración y las etiquetas GD3;
  - la lista de comandos que no se entienden (`Vgm.unsupported`): se informan y se sigue con lo demás.

El juego corre a 60 cuadros por segundo: `frame_of` redondea un instante al cuadro más cercano.
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass, field
from pathlib import Path

SAMPLE_RATE = 44100
SAMPLES_PER_FRAME = 735  # 44100 / 60
YM_CLOCK_DEFAULT = 8_000_000  # reloj del YM2610 si el VGM no lo trae

# Tipos de bloque de datos (comando $67) del YM2610
BLOCK_ADPCM_A = 0x81
BLOCK_ADPCM_B = 0x82


@dataclass(frozen=True)
class Write:
    sample: int  # instante (muestras de 44.1 kHz desde el inicio)
    chip: str  # "ym0" (puerto A) o "ym1" (puerto B)
    reg: int
    value: int

    @property
    def port(self) -> int:
        return 0 if self.chip == "ym0" else 1


@dataclass(frozen=True)
class DataBlock:
    """Un trozo de la ROM de samples: `data` va en `start` dentro de una ROM de `rom_size` bytes."""

    kind: str  # "adpcma" o "adpcmb"
    rom_size: int
    start: int
    data: bytes


@dataclass
class Vgm:
    writes: list[Write]
    total_samples: int
    loop_sample: int | None  # dónde empieza el bucle (None = no tiene)
    loop_samples: int
    tags: dict[str, str]
    clock: int  # reloj del YM2610 de la cabecera
    blocks: list[DataBlock] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)  # comandos que no se entienden, sin repetir

    def rom(self, kind: str) -> bytes:
        """La ROM de samples `kind` ("adpcma" o "adpcmb") armada con todos sus bloques (vacía si no hay)."""
        blocks = [b for b in self.blocks if b.kind == kind]
        if not blocks:
            return b""
        rom = bytearray(max(b.rom_size for b in blocks))
        for b in blocks:
            end = min(len(rom), b.start + len(b.data))
            rom[b.start : end] = b.data[: end - b.start]
        return bytes(rom)


def _command_length(cmd: int, pos: int) -> int:
    """Bytes que ocupa un comando que no se interpreta (incluido el comando)."""
    if 0x20 <= cmd <= 0x3F or cmd in (0x4F, 0x50):
        return 2
    if 0x40 <= cmd <= 0x4E or 0x51 <= cmd <= 0x5F or 0xA0 <= cmd <= 0xBF:
        return 3
    if 0xC0 <= cmd <= 0xDF:
        return 4
    if 0xE0 <= cmd <= 0xFF:
        return 5
    if cmd == 0x64:
        return 4
    if cmd == 0x68:
        return 12
    if cmd in (0x90, 0x91, 0x95):
        return 5
    if cmd == 0x92:
        return 6
    if cmd == 0x93:
        return 11
    if cmd == 0x94:
        return 2
    raise ValueError(f"comando VGM desconocido ${cmd:02X} en el byte {pos:#x}")


def _gd3(data: bytes, offset: int) -> dict[str, str]:
    if not offset or data[offset : offset + 4] != b"Gd3 ":
        return {}
    length = struct.unpack_from("<I", data, offset + 8)[0]
    text = data[offset + 12 : offset + 12 + length].decode("utf-16-le", errors="replace")
    fields = text.split("\0")
    names = ["title", "title_jp", "game", "game_jp", "system", "system_jp", "author", "author_jp", "date", "ripper", "notes"]
    return {name: value for name, value in zip(names, fields) if value}


def parse_vgm(raw: bytes, name: str = "VGM") -> Vgm:
    """Interpreta los bytes de un VGM (con o sin gzip). Lanza ValueError si no es un VGM del YM2610."""
    try:
        return _parse(raw, name)
    except (struct.error, IndexError) as exc:
        raise ValueError(f"{name}: archivo VGM truncado o dañado ({exc})") from exc
    except (OSError, EOFError) as exc:  # gzip dañado
        raise ValueError(f"{name}: no se pudo descomprimir ({exc})") from exc


def read_vgm(path: Path | str) -> Vgm:
    """Lee un `.vgm` o `.vgz`."""
    path = Path(path)
    return parse_vgm(path.read_bytes(), str(path))


def _parse(raw: bytes, name: str) -> Vgm:
    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    if data[:4] != b"Vgm " or len(data) < 0x40:
        raise ValueError(f"{name}: no es un archivo VGM")
    version = struct.unpack_from("<I", data, 0x08)[0]
    gd3_offset = struct.unpack_from("<I", data, 0x14)[0]
    total = struct.unpack_from("<I", data, 0x18)[0]
    loop_offset = struct.unpack_from("<I", data, 0x1C)[0]
    loop_samples = struct.unpack_from("<I", data, 0x20)[0]
    start = 0x40
    if version >= 0x150:
        rel = struct.unpack_from("<I", data, 0x34)[0]
        if rel:
            start = 0x34 + rel
    clock = 0
    if version >= 0x151 and start >= 0x50:
        clock = struct.unpack_from("<I", data, 0x4C)[0] & 0x3FFFFFFF
    loop_pos = 0x1C + loop_offset if loop_offset else None

    writes: list[Write] = []
    blocks: list[DataBlock] = []
    unsupported: dict[str, None] = {}
    sample = 0
    loop_sample = None
    pos = start
    while pos < len(data):
        if loop_pos is not None and pos == loop_pos:
            loop_sample = sample
        cmd = data[pos]
        if cmd == 0x66:
            break
        if cmd in (0x58, 0x59):
            writes.append(Write(sample, "ym0" if cmd == 0x58 else "ym1", data[pos + 1], data[pos + 2]))
            pos += 3
        elif cmd == 0x61:
            sample += struct.unpack_from("<H", data, pos + 1)[0]
            pos += 3
        elif cmd == 0x62:
            sample += 735
            pos += 1
        elif cmd == 0x63:
            sample += 882
            pos += 1
        elif 0x70 <= cmd <= 0x7F:
            sample += (cmd & 0x0F) + 1
            pos += 1
        elif cmd == 0x67:
            if data[pos + 1] != 0x66:
                raise ValueError(f"{name}: bloque de datos mal formado en el byte {pos:#x}")
            btype = data[pos + 2]
            size = struct.unpack_from("<I", data, pos + 3)[0] & 0x7FFFFFFF
            payload = data[pos + 7 : pos + 7 + size]
            if len(payload) < size:
                raise ValueError(f"{name}: bloque de datos truncado en el byte {pos:#x}")
            if btype in (BLOCK_ADPCM_A, BLOCK_ADPCM_B) and size >= 8:
                rom_size, block_start = struct.unpack_from("<II", payload, 0)
                kind = "adpcma" if btype == BLOCK_ADPCM_A else "adpcmb"
                blocks.append(DataBlock(kind, rom_size, block_start, bytes(payload[8:])))
            else:
                unsupported[f"bloque de datos tipo ${btype:02X} (no soportado)"] = None
            pos += 7 + size
        else:
            length = _command_length(cmd, pos)
            unsupported[_describe(cmd)] = None
            pos += length
    tags = _gd3(data, 0x14 + gd3_offset if gd3_offset else 0)
    if not writes:
        raise ValueError(f"{name}: no trae comandos del YM2610")
    return Vgm(writes, total or sample, loop_sample, loop_samples, tags, clock or 8_000_000, blocks, list(unsupported))


def _describe(cmd: int) -> str:
    if cmd in (0x52, 0x53):
        return f"comando ${cmd:02X} (YM2612, no es del YM2610)"
    if cmd in (0x50, 0x4F):
        return f"comando ${cmd:02X} (PSG, no es del YM2610)"
    if cmd in (0xA8, 0xA9):
        return f"comando ${cmd:02X} (segundo YM2610, se ignora)"
    if 0x90 <= cmd <= 0x95:
        return f"comando ${cmd:02X} (stream de DAC, no soportado)"
    if cmd == 0x68:
        return "comando $68 (escritura a PCM RAM, no soportado)"
    return f"comando ${cmd:02X} (no soportado)"


def frame_of(sample: int) -> int:
    return (sample + SAMPLES_PER_FRAME // 2) // SAMPLES_PER_FRAME


def unrolled_writes(vgm: Vgm, frames: int | None = None) -> list[tuple[int, Write]]:
    """Las escrituras con su cuadro, repitiendo el bucle hasta llenar `frames` cuadros (si se pide).

    Sin `frames` se toca una sola vez, hasta el final del archivo."""
    out = [(frame_of(w.sample), w) for w in vgm.writes]
    if frames is None:
        return out
    if vgm.loop_sample is not None and vgm.loop_samples:
        loop = [w for w in vgm.writes if w.sample >= vgm.loop_sample]
        offset = vgm.total_samples
        period = vgm.total_samples - vgm.loop_sample
        while loop and period > 0 and frame_of(offset) < frames:
            out += [(frame_of(w.sample - vgm.loop_sample + offset), w) for w in loop]
            offset += period
    return [(f, w) for f, w in out if f < frames]
