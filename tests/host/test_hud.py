"""Pruebas de hud.c (R5.9, R7.8): formato numérico y mapa de la Fix_Layer."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cffi import FFI
from hypothesis import given, strategies as st

SRC = Path(__file__).resolve().parents[2] / "src"
CDEF = """
typedef struct { uint16_t want[1280]; uint16_t sent[1280]; uint8_t dirty[40]; } FixShadow;
typedef struct { uint8_t lanes; uint16_t combo, max_combo; uint8_t multiplier; int16_t life;
  uint32_t score; uint32_t score_base; uint8_t star_bar; _Bool star_active, muted, failed;
  _Bool easy; _Bool no_fail; _Bool phrase_done; uint8_t star_drain; } JudgeState;
void hud_format_uint(char *out, uint32_t value, uint8_t digits);
uint16_t hud_meter_tile(uint16_t value, uint16_t i);
uint8_t hud_life_pal(int16_t life);
void hud_draw(FixShadow *f, const JudgeState *j);
void hud_draw2(FixShadow *f, const JudgeState *j, uint8_t player);
void fix_shadow_init(FixShadow *f);
"""


@pytest.fixture(scope="module")
def h(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        pytest.skip("No hay compilador de C en el host")
    d = tmp_path_factory.mktemp("hud")
    lib = d / ("hud.dylib" if sys.platform == "darwin" else "hud.so")
    subprocess.run([cc, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
                    f"-I{SRC}", "-o", str(lib), str(SRC / "hud.c"), str(SRC / "spr_diff.c")],
                   check=True, capture_output=True, text=True)
    ffi = FFI()
    ffi.cdef(CDEF)
    return ffi, ffi.dlopen(str(lib))


def _text(f, row, col, n):
    return "".join(chr(f.want[(col + i) * 32 + row] & 0xFF) for i in range(n))


def _fmt(h, v, d):
    ffi, lib = h
    b = ffi.new("char[]", 16)
    lib.hud_format_uint(b, v, d)
    return ffi.string(b).decode()


@given(st.integers(0, 2**32 - 1), st.integers(1, 8))
def test_format_uint(h, v, d):
    s = _fmt(h, v, d)
    assert len(s) == d and s.isdigit()
    assert int(s) == min(v, 10**d - 1)


def test_format_examples(h):
    assert _fmt(h, 42, 8) == "00000042"
    assert _fmt(h, 12345, 4) == "9999"


def test_meter_tiles(h):
    _, lib = h
    assert [lib.hud_meter_tile(12, i) for i in range(3)] == [0x88, 0x84, 0x80]
    assert lib.hud_meter_tile(0, 0) == 0x80


def test_draw_layout_and_spanish(h):
    ffi, lib = h
    f, j = ffi.new("FixShadow *"), ffi.new("JudgeState *")
    lib.fix_shadow_init(f)
    j.score, j.combo, j.multiplier, j.life, j.star_bar = 1234, 57, 4, 48, 60
    lib.hud_draw(f, j)
    assert _text(f, 3, 1, 6) == "PUNTOS" and _text(f, 3, 10, 8) == "00001234"
    assert _text(f, 4, 1, 5) == "COMBO" and _text(f, 4, 10, 7) == "0057 X4"
    assert _text(f, 5, 1, 4) == "VIDA" and f.want[10 * 32 + 5] & 0xFF == 0x88
    assert _text(f, 6, 1, 8) == "ESTRELLA" and _text(f, 6, 24, 5) == "PODER"
    j.no_fail = True
    lib.hud_draw(f, j)
    assert _text(f, 5, 10, 9) == "SIN FALLO"


def test_life_palette(h):
    _, lib = h
    assert (lib.hud_life_pal(48), lib.hud_life_pal(20), lib.hud_life_pal(5)) == (3, 1, 2)


def test_draw2_halves_do_not_overlap(h):
    ffi, lib = h
    f, j = ffi.new("FixShadow *"), ffi.new("JudgeState *")
    lib.fix_shadow_init(f)
    j.score, j.combo, j.multiplier, j.life, j.star_bar = 77, 3, 2, 48, 60
    lib.hud_draw2(f, j, 0)
    lib.hud_draw2(f, j, 1)
    assert _text(f, 3, 1, 2) == "J1" and _text(f, 3, 21, 2) == "J2"
    assert _text(f, 3, 5, 8) == "00000077" and _text(f, 3, 25, 8) == "00000077"
    assert _text(f, 4, 5, 7) == "0003 X2"
    j.failed = True
    lib.hud_draw2(f, j, 1)
    assert _text(f, 5, 25, 5) == "CAIDO"
