"""Lector de VGM para el YM2610 (Neo Geo).

Un VGM guarda la música como escrituras a los registros del chip con esperas en muestras de 44.1 kHz.
Aquí se lee `.vgm` o `.vgz` (el mismo formato comprimido con gzip, con el lector genérico de bandcore) y se saca:

  - las escrituras del YM2610 con su instante (`Write`; chip "ym0" = puerto A, VGM `0x58`; "ym1" = puerto B, `0x59`);
  - los bloques de datos de ADPCM-A (tipo `0x81`) y ADPCM-B (tipo `0x82`);
  - el bucle, la duración y las etiquetas GD3;
  - la lista de comandos que no se entienden (`Vgm.unsupported`): se informan y se sigue con lo demás.

El juego corre a 60 cuadros por segundo: `frame_of` redondea un instante al cuadro más cercano.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from bandcore import vgm as core
from bandcore.vgm import frame_of, unrolled_writes  # noqa: F401  (las usan songgen.py y las pruebas)

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


def parse_vgm(raw: bytes, name: str = "VGM") -> Vgm:
    """Interpreta los bytes de un VGM (con o sin gzip) con el lector de bandcore. Lanza ValueError si no es un VGM
    del YM2610."""
    v = core.parse_vgm(raw, name)
    writes = [
        Write(w.sample, "ym0" if w.port == 0 else "ym1", w.reg, w.value)
        for w in v.writes
        if w.chip == "ym2610" and w.index == 0
    ]
    blocks: list[DataBlock] = []
    unknown: list[tuple[int, str]] = []  # (instante, descripción) de lo que no se entiende
    unknown += [(w.sample, _describe(w.cmd)) for w in v.writes if not (w.chip == "ym2610" and w.index == 0)]
    for b in v.blocks:
        if b.type in (BLOCK_ADPCM_A, BLOCK_ADPCM_B) and len(b.data) >= 8:
            rom_size, block_start = struct.unpack_from("<II", b.data, 0)
            kind = "adpcma" if b.type == BLOCK_ADPCM_A else "adpcmb"
            blocks.append(DataBlock(kind, rom_size, block_start, b.data[8:]))
        else:
            unknown.append((b.sample, f"bloque de datos tipo ${b.type:02X} (no soportado)"))
    unknown += [(d.sample, "comandos $8n/$E0 (DAC del YM2612, no es del YM2610)") for d in v.dac]
    unknown += [(o.sample, _describe(o.cmd)) for o in v.other]
    unsupported = dict.fromkeys(text for _, text in sorted(unknown, key=lambda u: u[0]))
    if not writes:
        raise ValueError(f"{name}: no trae comandos del YM2610")
    clock = v.clocks.get("ym2610", 0)
    return Vgm(writes, v.total_samples, v.loop_sample, v.loop_samples, v.tags, clock or YM_CLOCK_DEFAULT, blocks, list(unsupported))


def read_vgm(path: Path | str) -> Vgm:
    """Lee un `.vgm` o `.vgz`."""
    path = Path(path)
    return parse_vgm(path.read_bytes(), str(path))


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
