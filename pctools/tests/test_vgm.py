"""Pruebas del lector de VGM y del seguimiento del YM2610."""

import gzip
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngband_tools.vgm import frame_of, parse_vgm, unrolled_writes  # noqa: E402
from ngband_tools.ym2610 import Event, Ym2610State, fm_pitch, ssg_pitch  # noqa: E402


def make_vgm(body: bytes, clock: int = 8_000_000, loop_at: int | None = None, loop_samples: int = 0, total: int = 0) -> bytes:
    header = bytearray(0x50)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x151)
    struct.pack_into("<I", header, 0x18, total)
    if loop_at is not None:
        struct.pack_into("<I", header, 0x1C, 0x50 + loop_at - 0x1C)
        struct.pack_into("<I", header, 0x20, loop_samples)
    struct.pack_into("<I", header, 0x34, 0x50 - 0x34)
    struct.pack_into("<I", header, 0x4C, clock)
    out = bytes(header) + body + b"\x66"
    return out


def test_reads_ym2610_writes_and_waits():
    body = bytes([0x58, 0x28, 0xF1, 0x62, 0x59, 0x00, 0x01, 0x61, 0xE8, 0x03])
    vgm = parse_vgm(make_vgm(body))
    assert [(w.sample, w.chip, w.reg, w.value) for w in vgm.writes] == [(0, "ym0", 0x28, 0xF1), (735, "ym1", 0, 1)]
    assert vgm.clock == 8_000_000
    assert vgm.unsupported == []


def test_vgz_equals_vgm():
    raw = make_vgm(bytes([0x58, 0x07, 0x38]))
    assert parse_vgm(gzip.compress(raw)).writes == parse_vgm(raw).writes


def test_loop_and_unrolled_writes():
    body = bytes([0x58, 0x00, 0x01, 0x62, 0x58, 0x01, 0x02, 0x62])
    vgm = parse_vgm(make_vgm(body, loop_at=len(b"\x58\x00\x01\x62"), loop_samples=735, total=1470))
    assert vgm.loop_sample == 735
    frames = [f for f, _ in unrolled_writes(vgm, 5)]
    assert frames == [0, 1, 2, 3, 4]
    assert frame_of(735) == 1


def test_adpcm_blocks_and_unsupported_commands():
    # Tipos de la especificación de VGM: $82 = ADPCM-A del YM2610, $83 = su ADPCM-B (DELTA-T); $81 es del YM2608
    payload = struct.pack("<II", 16, 4) + b"\xAA\xBB"
    block = bytes([0x67, 0x66, 0x82]) + struct.pack("<I", len(payload)) + payload
    payload_b = struct.pack("<II", 8, 0) + b"\xCC"
    block_b = bytes([0x67, 0x66, 0x83]) + struct.pack("<I", len(payload_b)) + payload_b
    other = bytes([0x67, 0x66, 0x81]) + struct.pack("<I", 2) + b"\x01\x02"
    body = block + block_b + other + bytes([0x52, 0x2A, 0x10, 0x58, 0x07, 0x00])
    vgm = parse_vgm(make_vgm(body))
    rom = vgm.rom("adpcma")
    assert len(rom) == 16 and rom[4:6] == b"\xAA\xBB"
    assert vgm.rom("adpcmb") == b"\xCC" + bytes(7)
    assert len(vgm.unsupported) == 2 and any("$52" in u for u in vgm.unsupported)
    assert any("$81" in u for u in vgm.unsupported)


@pytest.mark.parametrize("raw", [b"", b"nope" * 20, make_vgm(b"\x62"), make_vgm(b"\x58\x00")[:0x52]])
def test_invalid_input_raises(raw):
    with pytest.raises(ValueError):
        parse_vgm(raw)


def test_fm_key_on_and_pitch():
    chip = Ym2610State(8_000_000)
    chip.write(0, 0xA4, (4 << 3) | 0x02)
    assert chip.write(0, 0xA1, 0x9A) == [Event("fm_freq", 0)]
    assert chip.fm_freq(0) == (4, 0x29A)
    assert chip.write(0, 0x28, 0xF1) == [Event("fm_on", 0)]
    assert chip.write(0, 0x28, 0xF1) == []
    assert chip.write(0, 0x28, 0x01) == [Event("fm_off", 0)]
    # puerto B, canales 3 y 4
    chip.write(1, 0xA4, (3 << 3) | 0x01)
    chip.write(1, 0xA2, 0x00)
    assert chip.fm_freq(3) == (3, 0x100)
    assert chip.write(0, 0x28, 0xF6) == [Event("fm_on", 3)]
    assert chip.write(0, 0x28, 0xF0) == []  # código 0 no existe en el YM2610
    # una octava más arriba (bloque + 1) sube 12 semitonos
    assert fm_pitch(5, 0x29A) - fm_pitch(4, 0x29A) == pytest.approx(12)


def test_ssg_period_and_pitch():
    chip = Ym2610State(8_000_000)
    chip.write(0, 0x02, 0x1C)
    chip.write(0, 0x03, 0x01)
    assert chip.ssg_period(1) == 0x11C  # 284: ~440 Hz con reloj de 8 MHz
    assert chip.ssg_pitch(1) == pytest.approx(69, abs=0.05)
    assert ssg_pitch(0) is None
    chip.write(0, 0x09, 0x0F)
    chip.write(0, 0x07, 0x3D)  # tono B activo, resto apagado
    assert chip.ssg_audible(1) and not chip.ssg_audible(0)


def test_adpcma_key_on_and_range():
    chip = Ym2610State()
    chip.write(1, 0x10, 0x02)
    chip.write(1, 0x18, 0x00)
    chip.write(1, 0x20, 0x05)
    chip.write(1, 0x28, 0x00)
    assert chip.adpcma_range(0) == (0x200, 0x5FF)
    assert chip.write(1, 0x00, 0x05) == [Event("adpcma_on", 0), Event("adpcma_on", 2)]
    assert chip.write(1, 0x00, 0x81) == [Event("adpcma_off", 0)]
