"""Máquina de estados del Stage (R11.2-R11.7)."""
from hypothesis import given, strategies as st

QUIETO, BRAZOS, SALTO = 0, 1, 2
ATTACK, FLASH = 6, 8


def make(ffi, lib):
    s = ffi.new("StageState *")
    lib.stage_init(s)
    return s


def step(ffi, lib, s, combo=0, star=False, beat=False, phrase=False,
         failed=False, lane=0):
    i = ffi.new("StageInput *")
    i.combo, i.star_active, i.beat_tick = combo, star, beat
    i.phrase_done, i.all_failed, i.players, i.last_lane = phrase, failed, 1, lane
    lib.stage_step(s, i)


def test_crowd_still_below_ten(ffi, lib):
    s = make(ffi, lib)
    step(ffi, lib, s, combo=9, beat=True)
    assert s.crowd_state == QUIETO and s.pulse == 0


def test_crowd_jumps_on_beat_then_arms(ffi, lib):
    s = make(ffi, lib)
    step(ffi, lib, s, combo=10, beat=True)
    assert s.crowd_state == SALTO and s.pulse > 0
    for _ in range(ATTACK):
        step(ffi, lib, s, combo=10)
    assert s.crowd_state == BRAZOS


def test_flash_and_bolt(ffi, lib):
    s = make(ffi, lib)
    step(ffi, lib, s, phrase=True, lane=3)
    assert s.flash == FLASH and s.bolt_lane == 3
    step(ffi, lib, s)
    assert s.flash == FLASH - 1


def test_all_failed_turns_lights_off(ffi, lib):
    s = make(ffi, lib)
    step(ffi, lib, s, combo=50, failed=True)
    assert s.lights_off and s.crowd_state == QUIETO


inputs = st.lists(
    st.tuples(st.integers(0, 40), st.booleans(), st.booleans(),
              st.booleans(), st.booleans()),
    max_size=80)


# Feature: neogeo-band, Property 23: Estado del Stage
# **Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.7**
@given(inputs)
def test_property_stage_state(ffi, lib, seq):
    s = make(ffi, lib)
    for combo, star, beat, phrase, failed in seq:
        prev = s.light_phase
        step(ffi, lib, s, combo, star, beat, phrase, failed)
        assert bool(s.lights_off) == failed
        if failed:
            continue
        if combo < 10:
            assert s.crowd_state == QUIETO
        else:
            assert s.crowd_state in (BRAZOS, SALTO)
            if beat:
                assert s.crowd_state == SALTO and s.pulse > 0
        if star and beat:
            assert s.light_phase == (prev + 1) % 4
        else:
            assert s.light_phase == prev
# ---- Dibujo del Stage (tarea 16.3): presupuesto por línea, torre central, rayo ----
HWY_LINE_BUDGET = 96
def probe(ffi, lib, players=1, fill=0, flash=0, bolt=2, crowd=0, off=0):
    lines = ffi.new("uint8_t[224]")
    fx = ffi.new("uint16_t *")
    r = lib.ngb_stage_probe(players, fill, flash, bolt, crowd, off, lines, fx)
    return r & 0xFFFF, r >> 16, list(lines), fx[0]
def test_light_palette_priority(ffi, lib):
    assert lib.ngb_stage_pal(2, 1, 0, 0) == 20 + 2 * 2 + 1
    assert lib.ngb_stage_pal(3, 0, 0, 0) == 20 + 6
    assert lib.ngb_stage_pal(3, 1, 4, 0) == 20 + 9          # destello gana al latido
    assert lib.ngb_stage_pal(3, 1, 4, 1) == 20 + 8          # apagado gana a todo
def test_is_beat(ffi, lib):
    assert not lib.stage_is_beat(127, 128, 30) and lib.stage_is_beat(128, 128, 30)
    assert lib.stage_is_beat(188, 128, 30) and not lib.stage_is_beat(189, 128, 30)
    assert not lib.stage_is_beat(500, 128, 0)
def test_one_player_draws_all_pieces(ffi, lib):
    n, dropped, lines, _ = probe(ffi, lib)
    assert dropped == 0 and 20 <= n <= 101 and max(lines) > 0
def test_two_players_central_tower(ffi, lib):
    n, _, lines, first_x = probe(ffi, lib, players=2)
    assert 0 < n and first_x == 136                  # primer foco, a la izquierda de la torre central
    assert all(lines[y] == 0 for y in range(200, 224))   # nada abajo: el centro es solo la torre
def test_bolt_only_on_flash(ffi, lib):
    quiet, _, _, _ = probe(ffi, lib)
    bolt, _, _, _ = probe(ffi, lib, flash=3)
    assert bolt > quiet
    assert probe(ffi, lib, flash=3, off=1)[0] == quiet
def test_full_highway_leaves_no_room(ffi, lib):
    n, dropped, lines, _ = probe(ffi, lib, fill=HWY_LINE_BUDGET)
    assert n == 0 and all(c == 0 for c in lines)
@given(st.integers(1, 2), st.integers(0, HWY_LINE_BUDGET), st.integers(0, 3),
       st.integers(0, 4), st.integers(0, 2), st.booleans())
def test_property_stage_respects_line_budget(ffi, lib, players, fill, flash, bolt, crowd, off):
    # Feature: neogeo-band, Property 12: presupuesto de sprites por línea (parte del Stage)
    # **Validates: Requirements 11.1, 11.8, 20.4**
    n, _, lines, _ = probe(ffi, lib, players, fill, flash, bolt, crowd, int(off))
    assert n <= 101
    assert all(fill + c <= HWY_LINE_BUDGET for c in lines)
