"""Reglas de VS y COOP (R10.1-R10.7)."""
from hypothesis import given, strategies as st

from test_judge import entries

STAR_MIN, LIFE_MAX = 50, 48
u32 = st.integers(0, 2**32 - 1)


def vs_pair(ffi, lib, s1, s2, f1=False, f2=False):
    a, b = ffi.new("JudgeState *"), ffi.new("JudgeState *")
    lib.judge_init(a, 5, False, False)
    lib.judge_init(b, 5, False, False)
    a.score, b.score, a.failed, b.failed = s1, s2, f1, f2
    return a, b


def text(ffi, lib, a, b):
    r = lib.vs_result(a, b)
    buf = ffi.new("char[40]")
    n = lib.vs_result_text(ffi.new("VsResult *", r), buf, 40)
    s = ffi.string(buf).decode()
    assert n == len(s)
    return r, s


# Feature: neogeo-band, Property 21: Resultado de VS
@given(u32, u32)
def test_vs_text_by_score(ffi, lib, s1, s2):
    a, b = vs_pair(ffi, lib, s1, s2)
    assert not lib.vs_over(a, b)
    _, t = text(ffi, lib, a, b)
    if s1 == s2:
        assert t == "EMPATE"
    elif s1 > s2:
        assert t == f"GANA J1 POR {s1 - s2}"
    else:
        assert t == f"GANA J2 POR {s2 - s1}"


@given(u32, u32)
def test_vs_loser_gives_win_to_other(ffi, lib, s1, s2):
    a, b = vs_pair(ffi, lib, s1, s2, f1=True)
    assert lib.vs_over(a, b)
    assert text(ffi, lib, a, b)[1].startswith("GANA J2 POR ")
    a, b = vs_pair(ffi, lib, s1, s2, f2=True)
    assert text(ffi, lib, a, b)[1].startswith("GANA J1 POR ")


def coop(ffi, lib, lanes=5):
    c = ffi.new("CoopState *")
    lib.coop_init(c, lanes, False, False)
    return c


def test_coop_revive_costs_half_bar(ffi, lib):
    c = coop(ffi, lib)
    c.p[1].failed, c.p[1].life = True, 0
    c.star_bar = STAR_MIN - 1
    assert not lib.coop_revive(c, 1) and c.p[1].failed
    c.star_bar = 80
    assert lib.coop_star_press(c, 0)          # el botón revive al caído
    assert not c.p[1].failed and c.p[1].life == LIFE_MAX // 2
    assert c.star_bar == 80 - STAR_MIN and not c.star_active


def test_coop_no_revive_if_both_down_or_alive(ffi, lib):
    c = coop(ffi, lib)
    c.star_bar = 100
    assert not lib.coop_revive(c, 0)          # en pie
    c.p[0].failed = c.p[1].failed = True
    assert not lib.coop_revive(c, 0) and lib.coop_over(c)


def test_coop_star_press_without_fallen_activates(ffi, lib):
    c = coop(ffi, lib)
    c.star_bar = 60
    assert lib.coop_star_press(c, 1) and c.star_active and c.star_bar == 60


@given(st.booleans(), st.booleans())
def test_coop_over_iff_both_down(ffi, lib, f0, f1):
    c = coop(ffi, lib)
    c.p[0].failed, c.p[1].failed = f0, f1
    assert bool(lib.coop_over(c)) == (f0 and f1)


def test_coop_shared_score_combo_and_individual_life(ffi, lib):
    c = coop(ffi, lib)
    mk = lambda notes: _chart(ffi, notes)
    ch0, cu0 = mk([(10, 1), (40, 1)])
    ch1, cu1 = mk([(10, 2), (40, 2)])
    for f in range(0, 60):
        pad0 = ffi.new("PadInput *", {"pressed": 1, "edge": 1 if f == 10 else 0})
        pad1 = ffi.new("PadInput *", {"pressed": 2, "edge": 2 if f == 10 else 0})
        lib.coop_step(c, 0, ch0, cu0, pad0[0], f)
        lib.coop_step(c, 1, ch1, cu1, pad1[0], f)
    # P1 y P2 acertaron a la vez (combo 2 compartido); ambos perdieron una Note después
    assert c.max_combo == 2 and c.combo == 0
    assert c.score == 50 * 1 + 50 * 1
    assert c.p[0].life == c.p[1].life == 32 + 1 - 2


def test_coop_star_drain_once_per_frame(ffi, lib):
    c = coop(ffi, lib)
    c.star_bar = 60
    lib.coop_star_press(c, 0)
    ch, cu0 = _chart(ffi, [(1000, 1)])
    _, cu1 = _chart(ffi, [(1000, 1)])
    pad = ffi.new("PadInput *")
    for f in range(8 * 5):
        lib.coop_step(c, 0, ch, cu0, pad[0], f)
        lib.coop_step(c, 1, ch, cu1, pad[0], f)
    assert c.star_bar == 60 - 5


def test_instruments(ffi, lib):
    assert not lib.coop_instruments_ok(2, 2) and lib.coop_instruments_ok(0, 1)
    assert lib.coop_next_instrument(0, 1, 4, 1) == 2
    assert lib.coop_next_instrument(0, 3, 4, -1) == 2
    for cur in range(4):
        for other in range(4):
            assert lib.coop_next_instrument(cur, other, 4, 1) != other or cur == other


def _chart(ffi, notes):
    ents = entries(notes)
    ev = ffi.new("ChartEv[]", [{"delta_lo": d, "lanes": l} for d, l in ents])
    chart = ffi.new("Chart *", {"count": len(ents), "ev": ev})
    cur = ffi.new("ChartCursor *")
    _keep.append((ev, chart, cur))
    return chart, cur


_keep = []


def test_coop_view_has_band_values_and_own_life(ffi, lib):
    c = ffi.new("CoopState *")
    lib.coop_init(c, 5, False, False)
    c.score, c.combo, c.multiplier, c.star_bar = 900, 12, 2, 70
    c.p[1].life = 7
    v = ffi.new("JudgeState *")
    lib.coop_view(c, 1, v)
    assert (v.score, v.combo, v.multiplier, v.star_bar, v.life) == (900, 12, 2, 70, 7)
