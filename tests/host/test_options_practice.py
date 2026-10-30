"""Pruebas de options.c y practice.c (R8)."""
from hypothesis import given, strategies as st

K = [4, 3, 2, 5]
FPS = 60
MIN_LOOP = 240
LEAD = 120
SFX_FAIL = (3, 4, 5)


# ---- ESPEJO (Property 14) ----
@given(st.integers(3, 5), st.integers(0, 0xFF), st.booleans())
def test_mirror_involution(lib, lanes, ev, drums):
    once = lib.options_mirror_ev(ev, lanes, drums)
    assert lib.options_mirror_ev(once, lanes, drums) == ev
    if drums or ev == 0xFF:
        assert once == ev


def test_mirror_five_lanes(lib):
    assert lib.options_mirror_ev(0b00001, 5, False) == 0b10000   # verde <-> naranja
    assert lib.options_mirror_ev(0b00010, 5, False) == 0b01000   # rojo <-> azul
    assert lib.options_mirror_ev(0b00100, 5, False) == 0b00100
    assert lib.options_mirror_ev(0x40 | 0b00001, 5, False) == 0x40 | 0b10000  # conserva banderas


# ---- VELOCIDAD (Property 15) ----
@given(st.integers(0, 3), st.integers(0, 2000))
def test_speed_steps(ffi, lib, idx, n):
    s = ffi.new("SpeedClock *")
    lib.speed_init(s)
    total = 0
    for i in range(1, n + 1):
        steps = lib.speed_frame(s, idx)
        assert steps <= 2
        total += steps
        assert total == i * K[idx] // 4
    assert total == n * K[idx] // 4


# ---- Opciones ----
def test_options_defaults_and_changes(ffi, lib):
    o = ffi.new("Options *")
    lib.options_init(o)
    assert not lib.options_changed(o)
    assert lib.options_change(o, 1, 1) is False and o.speed_idx == 1
    assert lib.options_changed(o)
    lib.options_change(o, 1, -1)
    lib.options_change(o, 5, 1)           # EFECTO AL FALLAR no impide récords
    assert not lib.options_changed(o)
    assert lib.options_change(o, 3, 1) is True    # PRACTICA invalida marcas
    assert [ffi.string(lib.options_value_name(1, v)) for v in range(4)] == [
        b"100%", b"75%", b"50%", b"125%"]
    assert ffi.string(lib.options_label(4)) == b"INICIO DE LA PRACTICA"


def test_fall_and_fail_fx(ffi, lib):
    o = ffi.new("Options *")
    lib.options_init(o)
    assert [lib.options_fall_frames(o, d) for d in range(4)] == [6, 5, 4, 3]
    o.fall_idx = 4
    assert [lib.options_fall_frames(o, d) for d in range(4)] == [3, 3, 3, 3]
    o.fall_idx = 1
    assert lib.options_fall_frames(o, 3) == 6
    for fx, shake, sound in ((0, True, True), (1, False, True), (2, False, False)):
        o.fail_fx = fx
        assert lib.options_fail_shake_red(o) == shake and lib.options_fail_sound(o) == sound


# ---- Limitador (Property 17) ----
@given(st.lists(st.integers(0, 40), max_size=60), st.lists(st.integers(0, 255), min_size=60, max_size=60))
def test_fx_limiter(ffi, lib, gaps, rnds):
    l = ffi.new("FxLimiter *")
    lib.fxlim_init(l)
    now, emitted, last = 0, [], None
    for g, r in zip(gaps, rnds):
        now += g
        fx = lib.fxlim_air(l, now, r)
        if fx >= 0:
            assert fx in SFX_FAIL and fx != last
            last = fx
            emitted.append(now)
    for i, t in enumerate(emitted):
        # a lo sumo 3 efectos en cualquier ventana de 60 cuadros
        assert len([u for u in emitted if t <= u < t + FPS]) <= 3
    # sin supresión innecesaria: si hay menos de 3 en los últimos 60 cuadros, se emite
    l2 = ffi.new("FxLimiter *")
    lib.fxlim_init(l2)
    assert all(lib.fxlim_air(l2, t, 0) >= 0 for t in (0, 1, 2))
    assert lib.fxlim_air(l2, 3, 0) == -1
    assert lib.fxlim_air(l2, 60, 0) >= 0


# ---- Practice (Property 16) ----
def _practice(ffi, lib, mode, start, total):
    p = ffi.new("Practice *")
    lib.practice_init(p, mode, start, total)
    return p


@given(st.integers(1, 4), st.integers(0, 3), st.integers(1200, 20000))
def test_practice_points(ffi, lib, mode, start, total):
    p = _practice(ffi, lib, mode, start, total)
    assert p.loop_start == total * start // 4
    assert p.loop_end - p.loop_start >= MIN_LOOP
    q = lib.practice_seek_quarter(p)
    assert total * q // 4 <= p.loop_start
    if q < 3:
        assert total * (q + 1) // 4 > p.loop_start


@given(st.integers(1, 4), st.integers(1200, 20000), st.integers(0, 20000), st.integers(0, 20000))
def test_practice_marks(ffi, lib, mode, total, a, b):
    p = _practice(ffi, lib, mode, 0, total)
    start0, end0 = p.loop_start, p.loop_end
    ok = lib.practice_mark_start(p, a)
    new_start = max(a - LEAD, 0)
    assert ok == (end0 - new_start >= MIN_LOOP)
    assert p.loop_start == (new_start if ok else start0)
    s1 = p.loop_start
    ok = lib.practice_mark_end(p, b)
    assert ok == (b <= total and b - s1 >= MIN_LOOP)
    assert p.loop_end == (b if ok else end0)


def test_practice_exact_four_seconds(ffi, lib):
    p = _practice(ffi, lib, 4, 0, 6000)
    assert lib.practice_mark_end(p, 240)
    assert not lib.practice_mark_end(p, 239) and p.loop_end == 240
    assert lib.practice_at_end(p, 240) and not lib.practice_at_end(p, 239)
    assert lib.practice_pause_exit(True) and not lib.practice_pause_exit(False)


def test_practice_skips_early_notes(ffi, lib):
    evs = ffi.new("ChartEv[]", [(10, 1), (50, 2), (50, 4), (0, 0xFF)])
    chart = ffi.new("Chart *", (4, evs))
    p = _practice(ffi, lib, 4, 2, 400)     # inicia en 200
    cur = ffi.new("ChartCursor *")
    lib.practice_skip_notes(p, chart, cur)
    assert cur.index == 3 and cur.frame == 110   # todas antes de 200 omitidas, queda el END
    p = _practice(ffi, lib, 4, 1, 400)     # inicia en 100
    cur = ffi.new("ChartCursor *")
    lib.practice_skip_notes(p, chart, cur)
    assert cur.index == 2 and cur.frame == 60
