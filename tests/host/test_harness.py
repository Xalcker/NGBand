"""Humo del arnés: los tipos comunes se ven igual desde C y desde Python."""
from hypothesis import given, strategies as st


def test_type_sizes_match(ffi, lib):
    assert lib.ngb_sizeof_judge_state() == ffi.sizeof("JudgeState")
    assert lib.ngb_sizeof_pad_input() == ffi.sizeof("PadInput") == 2
    assert lib.ngb_sizeof_chart_ev() == ffi.sizeof("ChartEv") == 2
    assert lib.ngb_sizeof_chart() == ffi.sizeof("Chart")


@given(lanes=st.integers(0, 0x7F), delta=st.integers(0, 254))
def test_chart_ev_roundtrip(ffi, lanes, delta):
    ev = ffi.new("ChartEv *", {"delta_lo": delta, "lanes": lanes})
    chart = ffi.new("Chart *", {"count": 1, "ev": ev})
    assert chart.ev[0].delta_lo == delta
    assert chart.ev[0].lanes == lanes
