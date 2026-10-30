"""Pruebas del Chart_Generator compartido (chart.py y drums.py)."""
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ngband_tools.chart import (  # noqa: E402
    DIFFICULTIES,
    END_FLAG,
    STAR_FLAG,
    SUSTAIN_FLAG,
    BeatGrid,
    ChartNote,
    Note,
    assign_lanes,
    build_chart,
    chart_entries,
    chart_from_c,
    chart_from_entries,
    chart_to_c,
    check_playable,
    estimate_beat,
    merge_attacks,
    reduce_notes,
    star_notes,
    sustain_ends,
)
from ngband_tools.drums import (  # noqa: E402
    MAX_BUTTONS,
    Hit,
    build_drum_chart,
    check_drum_chart,
    drum_groups,
    dump_drums,
    suggest_assignment,
)


def _melody(pitches, spacing=40, duration=10):
    return [Note(i * spacing, p, duration) for i, p in enumerate(pitches)]


def test_estimate_beat_doubles_subdivision():
    grid = estimate_beat(list(range(0, 400, 5)))
    assert grid.frames_per_beat == 20 and grid.first_beat == 0


def test_reduce_notes_keeps_strong_beats_and_gap():
    notes = [Note(f, 60, 5) for f in range(0, 80, 5)]
    kept = reduce_notes(notes, DIFFICULTIES[0], BeatGrid(20, 0))
    assert [n.frame for n in kept] == [0, 40, 70]


def test_merge_attacks_joins_pitch_sweeps():
    sweep = [Note(10 + i, 53 - 2 * i, 1) for i in range(8)]
    merged = merge_attacks(sweep + [Note(20, 45, 8)])
    assert [(n.frame, n.pitch, n.duration) for n in merged] == [(10, 53, 8), (20, 45, 8)]


def test_assign_lanes_follows_contour():
    lanes = assign_lanes(_melody([60, 62, 64, 64, 62, 60], 10), 5)
    assert lanes[0] < lanes[1] < lanes[2] and lanes[2] == lanes[3] > lanes[4] > lanes[5]


def test_check_playable_rejects_impossible_charts():
    check_playable([ChartNote(0, 0b00011), ChartNote(10, 0b10001, end=40), ChartNote(50, 0b00100)])
    for bad in (
        [ChartNote(0, 0b00101)],  # verde + amarillo
        [ChartNote(0, 0b10100)],  # amarillo + naranja (con ESPEJO sería verde + amarillo)
        [ChartNote(0, 0b00001, end=40), ChartNote(20, 0b00100)],  # amarillo cae sosteniendo verde
    ):
        with pytest.raises(ValueError):
            check_playable(bad)


def test_sustain_ends_cut_before_next_note_in_lane():
    notes = [Note(0, 60, 100), Note(50, 64, 5)]
    assert sustain_ends(notes, [0, 2])[0] == 50 - 3 - 4
    assert sustain_ends(notes, [0, 4])[0] == 100 - 4


def test_chart_entries_use_deltas_and_extension_events():
    chart = [ChartNote(128, 0x01), ChartNote(140, 0x02), ChartNote(800, 0x04)]
    assert chart_entries(chart) == [(128, 0x01), (12, 0x02), (255, 0), (255, 0), (150, 0x04), (0, 0xFF)]
    assert chart_entries([ChartNote(255, 0x01)]) == [(255, 0), (0, 0x01), (0, 0xFF)]


def test_chart_entries_flags():
    chart = [ChartNote(100, 0x01, end=160, star=True), ChartNote(130, 0x04)]
    assert chart_entries(chart) == [(100, 0x01 | SUSTAIN_FLAG | STAR_FLAG), (30, 0x04), (30, 0x01 | END_FLAG), (0, 0xFF)]


def test_star_phrases_skip_chords():
    chords = [False] * 100
    chords[12] = True
    stars = star_notes(100, chords)
    assert not any(s and c for s, c in zip(stars, chords)) and any(stars)


# --- Round trip (P27) --------------------------------------------------------------------------------


def test_round_trip_with_sustain_and_stars():
    chart = [ChartNote(10, 0b00011, end=60, star=True), ChartNote(70, 0b00100), ChartNote(900, 0b01000, end=1000)]
    assert chart_from_entries(chart_entries(chart)) == chart
    assert chart_from_c(chart_to_c("x", chart)) == chart


@given(st.lists(st.integers(30, 90), min_size=1, max_size=120), st.sampled_from(["lead", "keys", "bass"]),
       st.sampled_from(DIFFICULTIES), st.integers(0, 300))
@settings(max_examples=100, deadline=None)
def test_generated_charts_are_playable_and_round_trip(pitches, role, difficulty, lead_in):
    notes = [Note(i * 7, p, 3 + (i % 5) * 20) for i, p in enumerate(pitches)]
    chart = build_chart(notes, difficulty, BeatGrid(21, 0), lead_in, role, notes[::-1])
    check_playable(chart)
    assert chart_from_c(chart_to_c("c", chart)) == chart


# --- Batería (R4.6) ------------------------------------------------------------------------------------


@given(st.lists(st.tuples(st.integers(0, 3000), st.sampled_from(["kick", "snare", "tom1", "tom2", "tom3"]), st.booleans()), max_size=200))
@settings(max_examples=100, deadline=None)
def test_drum_chords_respect_limits(raw):
    hits = sorted((Hit(f, r, c) for f, r, c in raw), key=lambda h: h.frame)
    for difficulty in DIFFICULTIES:
        chart = build_drum_chart(hits, difficulty.name, BeatGrid(21, 0), 0)
        check_drum_chart(chart, difficulty.name)
        assert chart_from_c(chart_to_c("d", chart), drums=True) == chart


def test_drum_limits_and_cymbals_only_in_expert():
    hits = [Hit(f, r, True) for f in range(0, 600, 30) for r in ("kick", "snare", "tom1", "tom2", "tom3")]
    easy = build_drum_chart(hits, "facil", BeatGrid(30, 0), 0)
    assert all(bin(n.mask).count("1") <= 1 and not n.cymbal for n in easy)
    expert = build_drum_chart(hits, "experto", BeatGrid(30, 0), 0)
    assert all(bin(n.mask).count("1") <= MAX_BUTTONS["experto"] for n in expert)
    assert any(n.cymbal for n in expert)
    with pytest.raises(ValueError):
        check_drum_chart([ChartNote(0, 0b11010)], "dificil")  # 3 botones sí; 4 no cabe
        check_drum_chart([ChartNote(0, 0b11110)], "dificil")


def test_suggest_assignment_for_adpcma():
    notes = {"adpcma": [Note(f, s, 2) for f, s in zip(range(0, 100, 5), [0, 1, 0, 2] * 5)]}
    groups = drum_groups(notes, ["adpcma"])
    assignment = suggest_assignment(groups)
    assert assignment["adpcma:0"]["lane"] == "kick" and assignment["adpcma:1"]["lane"] == "snare"
    assert '"adpcma:0"' in dump_drums(assignment)
