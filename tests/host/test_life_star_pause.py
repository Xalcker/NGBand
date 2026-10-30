"""Vida, Star_Power y pausa (R3.1-R3.9)."""
from hypothesis import given, strategies as st

from test_judge import Sim, STAR

LIFE_MAX, LIFE_START = 48, 32


def run(s, upto, hits=(), air=()):
    for f in range(upto):
        s.step(f, edge=(1 if f in hits else 0) | (2 if f in air else 0))


def test_initial_life(ffi, lib):
    s = Sim(ffi, lib, [(10, 1)])
    assert s.j.life == LIFE_START and not s.j.failed


def test_hit_adds_one_life(ffi, lib):
    s = Sim(ffi, lib, [(10, 1), (30, 1)])
    run(s, 12, hits={10})
    assert s.j.life == LIFE_START + 1


def test_chord_adds_one_life(ffi, lib):
    s = Sim(ffi, lib, [(10, 7)])
    s.step(10, edge=7)
    assert s.j.life == LIFE_START + 1


def test_miss_costs_two_one_in_easy(ffi, lib):
    s = Sim(ffi, lib, [(10, 1)])
    run(s, 30)
    assert s.j.life == LIFE_START - 2
    e = Sim(ffi, lib, [(10, 1)], easy=True)
    run(e, 30)
    assert e.j.life == LIFE_START - 1


def test_air_hit_costs_one(ffi, lib):
    s = Sim(ffi, lib, [(100, 1)])
    s.step(0, edge=2)
    assert s.j.life == LIFE_START - 1


def test_life_capped(ffi, lib):
    notes = [(10 + 10 * i, 1) for i in range(40)]
    s = Sim(ffi, lib, notes)
    hits = {f for f, _ in notes}
    run(s, 450, hits=hits)
    assert s.j.life == LIFE_MAX


def test_zero_life_fails_and_mutes(ffi, lib):
    s = Sim(ffi, lib, [(1000, 1)])
    for f in range(LIFE_START):
        s.step(f, edge=2)
    assert s.j.life == 0 and s.j.failed and s.j.muted
    # tras fallar, nada cambia
    score, combo = s.j.score, s.j.combo
    s.step(LIFE_START, edge=1)
    assert s.j.score == score and s.j.combo == combo and s.j.life == 0


def test_no_fail_never_ends(ffi, lib):
    s = Sim(ffi, lib, [(1000, 1)], no_fail=True)
    for f in range(100):
        s.step(f, edge=2)
    assert s.j.life == 0 and not s.j.failed


@given(events=st.lists(st.sampled_from(["hit", "miss", "air"]), max_size=60),
       easy=st.booleans(), no_fail=st.booleans())
def test_life_dynamics(ffi, lib, events, easy, no_fail):
    """Property 7: modelo de referencia contra el Judge."""
    frame, notes, plan = 20, [], []
    for e in events:
        if e == "air":
            plan.append((frame, "air"))
            frame += 8  # sin nota cercana: golpe al aire
        else:
            notes.append((frame + 20, 1))
            plan.append((frame + 20, e))
            frame += 40
    s = Sim(ffi, lib, notes, easy=easy, no_fail=no_fail)
    by_frame = dict(plan)
    for f in range(frame + 30):
        s.step(f, edge={"hit": 1, "air": 2}.get(by_frame.get(f), 0))
    # Modelo: la pérdida de una Note se aplica 7 cuadros después de su cuadro.
    life, failed = LIFE_START, False
    timeline = []
    for f, e in plan:
        timeline.append((f if e != "miss" else f + 7, e))
    for _, e in sorted(timeline, key=lambda t: t[0]):
        if failed:
            break
        if e == "hit":
            life = min(LIFE_MAX, life + 1)
        elif e == "air":
            life = max(0, life - 1)
        else:
            life = max(0, life - (1 if easy else 2))
        if life == 0 and not no_fail:
            failed = True
    assert s.j.life == life
    assert bool(s.j.failed) == failed
    assert 0 <= s.j.life <= LIFE_MAX


def phrase_chart(n_star, extra=2):
    notes = [(20 + 10 * i, 1 | STAR) for i in range(n_star)]
    notes += [(20 + 10 * (n_star + i), 1) for i in range(extra)]
    return notes


def test_star_phrase_adds_25(ffi, lib):
    notes = phrase_chart(4)
    s = Sim(ffi, lib, notes)
    run(s, 120, hits={f for f, _ in notes})
    assert s.j.star_bar == 25


def test_star_phrase_missed_note_gives_nothing(ffi, lib):
    notes = phrase_chart(4)
    s = Sim(ffi, lib, notes)
    run(s, 120, hits={f for f, _ in notes[:3]} | {f for f, _ in notes[4:]})
    assert s.j.star_bar == 0


def test_star_phrase_at_chart_end(ffi, lib):
    notes = phrase_chart(4, extra=0)
    s = Sim(ffi, lib, notes)
    run(s, 100, hits={f for f, _ in notes})
    assert s.j.star_bar == 25 and s.j.phrase_done is False  # phrase_done es de un solo paso


def test_star_bar_capped_at_100(ffi, lib):
    notes = []
    for p in range(6):
        base = 20 + p * 100
        notes += [(base + 10 * i, 1 | STAR) for i in range(2)] + [(base + 30, 1)]
    s = Sim(ffi, lib, notes)
    run(s, 700, hits={f for f, _ in notes})
    assert s.j.star_bar == 100


def test_star_power_activation_threshold(ffi, lib):
    s = Sim(ffi, lib, [(500, 1)])
    s.j.star_bar = 49
    assert not lib.judge_star_power(s.j) and not s.j.star_active
    s.j.star_bar = 50
    assert lib.judge_star_power(s.j) and s.j.star_active


def test_star_power_doubles_score_and_drains(ffi, lib):
    s = Sim(ffi, lib, [(10, 1)])
    s.j.star_bar = 100
    lib.judge_star_power(s.j)
    run(s, 12, hits={10})
    assert s.j.score == 100 and s.j.score_base == 50
    s2 = Sim(ffi, lib, [(5000, 1)])
    s2.j.star_bar = 50
    lib.judge_star_power(s2.j)
    run(s2, 8 * 50 + 1)
    assert s2.j.star_bar == 0 and not s2.j.star_active


@given(bar=st.integers(0, 100), presses=st.integers(1, 3))
def test_star_power_only_from_half(ffi, lib, bar, presses):
    s = Sim(ffi, lib, [(5000, 1)])
    s.j.star_bar = bar
    for _ in range(presses):
        lib.judge_star_power(s.j)
    assert bool(s.j.star_active) == (bar >= 50)


def make_clock(ffi, lib):
    c = ffi.new("PlayClock *")
    lib.clock_init(c)
    return c


def pad(ffi, edge):
    return ffi.new("PadInput *", {"pressed": edge, "edge": edge})[0]


def test_pause_blocks_and_resume_continues(ffi, lib):
    s = Sim(ffi, lib, [(10, 1), (40, 1)])
    c = make_clock(ffi, lib)
    for _ in range(5):
        assert lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 0), False, False)
    assert lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 0), False, True) is False
    assert c.paused
    snap = (c.frame, c.stream_frame, s.j.score, s.cur.index, s.j.life)
    for _ in range(100):
        assert not lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 1), True, False)
    assert (c.frame, c.stream_frame, s.j.score, s.cur.index, s.j.life) == snap
    lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 0), False, True)
    assert not c.paused
    assert lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 0), False, False)
    assert c.frame == snap[0] + 1 and c.stream_frame == snap[1] + 1


@given(pause_at=st.integers(0, 80), length=st.integers(1, 60),
       gaps=st.lists(st.integers(8, 30), min_size=1, max_size=6))
def test_pause_resume_preserves_state(ffi, lib, pause_at, length, gaps):
    """Property 9: pausar y reanudar equivale a no pausar."""
    notes, f = [], 10
    for g in gaps:
        f += g
        notes.append((f, 1))
    hits = {fr for fr, _ in notes}

    def play(with_pause):
        s = Sim(ffi, lib, notes)
        c = make_clock(ffi, lib)
        for step in range(f + 30):
            if with_pause and step == pause_at:
                lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 0), False, True)
                for _ in range(length):
                    lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 1), True, False)
                lib.play_step(c, s.j, s.chart, s.cur, pad(ffi, 0), False, True)
            lib.play_step(c, s.j, s.chart, s.cur,
                          pad(ffi, 1 if c.frame in hits else 0), False, False)
        return (c.frame, c.stream_frame, s.j.score, s.j.combo, s.j.life, s.cur.index,
                s.cur.count, s.cur.frame)

    assert play(True) == play(False)
