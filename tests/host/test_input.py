"""Pruebas de input_map.c (R6): mapa de carriles y filtro ← / →."""
from hypothesis import given, strategies as st

PAD = dict(UP=0x1, DOWN=0x2, LEFT=0x4, RIGHT=0x8, A=0x10, B=0x20, C=0x40, D=0x80, START=0x100)

CDEF = """
typedef struct { PadInput in; bool power, power_edge; bool pause_edge; uint16_t prev_raw; } PadState;
uint8_t input_lane_mask(uint16_t raw);
void input_update(PadState *s, uint16_t raw);
"""


def _api(ffi):
    try:
        ffi.typeof("PadState")
    except Exception:
        ffi.cdef(CDEF)


def _expected(raw):
    both = raw & PAD["LEFT"] and raw & PAD["RIGHT"]
    m = 0
    if raw & PAD["LEFT"] and not both: m |= 1
    if raw & PAD["DOWN"]: m |= 2
    if raw & PAD["RIGHT"] and not both: m |= 4
    if raw & PAD["B"]: m |= 8
    if raw & PAD["C"]: m |= 16
    return m


# Feature: neogeo-band, Property 13: Filtro de izquierda y derecha
# **Validates: Requirements 6.1, 6.2**
@given(st.integers(0, 0x1FF))
def test_lane_mask_filter(ffi, lib, raw):
    _api(ffi)
    assert lib.input_lane_mask(raw) == _expected(raw)


def test_left_right_ignored_but_others_kept(ffi, lib):
    _api(ffi)
    m = lib.input_lane_mask(PAD["LEFT"] | PAD["RIGHT"] | PAD["DOWN"])
    assert m == 2


@given(st.lists(st.integers(0, 0x1FF), min_size=1, max_size=20))
def test_edges_and_power_pause(ffi, lib, seq):
    _api(ffi)
    s = ffi.new("PadState *")
    prev = 0
    for raw in seq:
        lib.input_update(s, raw)
        assert getattr(s, "in").pressed == _expected(raw)
        assert getattr(s, "in").edge == _expected(raw) & ~_expected(prev) & 0xFF
        assert bool(s.power) == bool(raw & PAD["A"])
        assert bool(s.power_edge) == bool(raw & PAD["A"] and not prev & PAD["A"])
        assert bool(s.pause_edge) == bool(raw & PAD["START"] and not prev & PAD["START"])
        prev = raw
