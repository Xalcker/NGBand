"""Pruebas del Judge (R2.1-R2.10): ejemplos y una propiedad del jugador perfecto."""
from hypothesis import given, strategies as st

SUSTAIN, END, STAR = 0x40, 0x80, 0x20


def entries(notes):
    """notes: [(frame, lanes_byte)] ordenados -> pares (delta, lanes) con extensión y cierre."""
    out, prev = [], 0
    for frame, lanes in notes:
        d = frame - prev
        while d >= 255:
            out.append((255, 0))
            d -= 255
        out.append((d, lanes))
        prev = frame
    out.append((0, 0xFF))
    return out


class Sim:
    def __init__(self, ffi, lib, notes, lanes=5, easy=False, no_fail=False):
        self.ffi, self.lib = ffi, lib
        ents = entries(notes)
        self.ev = ffi.new("ChartEv[]", [{"delta_lo": d, "lanes": l} for d, l in ents])
        self.chart = ffi.new("Chart *", {"count": len(ents), "ev": self.ev})
        self.j = ffi.new("JudgeState *")
        lib.judge_init(self.j, lanes, easy, no_fail)
        self.cur = ffi.new("ChartCursor *")

    def step(self, frame, edge=0, pressed=None):
        pad = self.ffi.new("PadInput *", {"pressed": edge if pressed is None else pressed, "edge": edge})
        self.lib.judge_step(self.j, self.chart, self.cur, pad[0], frame)


def test_hit_window_edges(ffi, lib):
    s = Sim(ffi, lib, [(20, 0x01), (60, 0x01)])
    for f in range(0, 15):
        s.step(f)
    assert s.j.score == 0 and s.j.combo == 0
    s.step(14, edge=1)          # 20 - 14 = 6: dentro
    assert s.j.combo == 1 and s.j.score == 50
    s2 = Sim(ffi, lib, [(20, 0x01)])
    for f in range(0, 13):
        s2.step(f)
    s2.step(13, edge=1)         # 7 cuadros antes: golpe al aire
    assert s2.j.combo == 0 and s2.j.muted and s2.j.score == 0


def test_miss_breaks_combo_and_mutes(ffi, lib):
    s = Sim(ffi, lib, [(10, 0x01), (40, 0x02)])
    for f in range(0, 11):
        s.step(f, edge=1 if f == 10 else 0)
    assert s.j.combo == 1 and not s.j.muted
    for f in range(11, 48):
        s.step(f)
    assert s.j.combo == 0 and s.j.multiplier == 1 and s.j.muted


def test_air_hit_then_hit_unmutes(ffi, lib):
    s = Sim(ffi, lib, [(30, 0x01)])
    s.step(0, edge=0x02)
    assert s.j.muted and s.j.combo == 0
    for f in range(1, 31):
        s.step(f, edge=1 if f == 30 else 0)
    assert not s.j.muted and s.j.combo == 1


def test_chord_counts_one_note_per_button(ffi, lib):
    s = Sim(ffi, lib, [(10, 0x07)])
    for f in range(0, 11):
        s.step(f, edge=0x07 if f == 10 else 0)
    assert s.j.combo == 3 and s.j.score == 150


def test_multiplier_thresholds(ffi, lib):
    assert [lib.judge_multiplier(c) for c in (0, 9, 10, 19, 20, 29, 30, 500)] == [1, 1, 2, 2, 3, 3, 4, 4]
    notes = [(10 + 10 * i, 0x01) for i in range(31)]
    s = Sim(ffi, lib, notes)
    total = 0
    for f in range(0, 10 + 10 * 30 + 1):
        hit = f >= 10 and (f - 10) % 10 == 0
        if hit:
            total += 50 * lib.judge_multiplier(s.j.combo + 1)
        s.step(f, edge=1 if hit else 0)
    assert s.j.combo == 31 and s.j.multiplier == 4 and s.j.score == total == s.j.score_base


def test_sustain_points_every_8_frames(ffi, lib):
    s = Sim(ffi, lib, [(10, 0x01 | SUSTAIN), (50, 0x01 | END)])
    for f in range(0, 60):
        s.step(f, edge=1 if f == 10 else 0, pressed=1 if 10 <= f < 60 else 0)
    # cola de 40 cuadros (10..49): 40 pasos -> 5 puntajes
    assert s.j.score == 50 + 5 * 10
    assert s.j.score_base == 50


def test_sustain_released_early_stops_points(ffi, lib):
    s = Sim(ffi, lib, [(10, 0x01 | SUSTAIN), (80, 0x01 | END)])
    for f in range(0, 90):
        s.step(f, edge=1 if f == 10 else 0, pressed=1 if 10 <= f < 20 else 0)
    assert s.j.score == 50 + 10


def test_stars_thresholds(ffi, lib):
    assert [lib.judge_stars(v, 100) for v in (0, 19, 20, 39, 40, 59, 60, 79, 80, 94, 95, 100)] == \
        [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert lib.judge_stars(5, 0) == 0


@given(a=st.integers(0, 10**6), b=st.integers(0, 10**6), perfect=st.integers(1, 10**6))
def test_stars_monotonic(lib, a, b, perfect):
    lo, hi = sorted((a, b))
    assert lib.judge_stars(lo, perfect) <= lib.judge_stars(hi, perfect) <= 5


@given(gaps=st.lists(st.integers(0, 300), min_size=1, max_size=40),
       masks=st.lists(st.integers(1, 0x1F), min_size=40, max_size=40))
def test_perfect_player_hits_every_button(ffi, lib, gaps, masks):
    frame, notes = 10, []
    for g, m in zip(gaps, masks):
        frame += max(g, 8)
        notes.append((frame, m))
    s = Sim(ffi, lib, notes)
    by_frame = dict(notes)
    for f in range(0, frame + 20):
        s.step(f, edge=by_frame.get(f, 0))
    buttons = sum(bin(m).count("1") for _, m in notes)
    assert s.j.combo == buttons == s.j.max_combo and not s.j.muted
