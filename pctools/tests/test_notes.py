"""Pruebas de la extracción de notas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ngband_tools.notes import extract_notes_from_writes  # noqa: E402
from ngband_tools.vgm import SAMPLES_PER_FRAME, Write  # noqa: E402
from ngband_tools.ym2610 import fm_pitch  # noqa: E402


def w(frame, reg, value, port=0):
    return (frame, Write(frame * SAMPLES_PER_FRAME, "ym0" if port == 0 else "ym1", reg, value))


def freq(frame, block, fnum):
    return [w(frame, 0xA4, (block << 3) | (fnum >> 8)), w(frame, 0xA0 + 1, fnum & 0xFF)]


KEY_ON, KEY_OFF = w(0, 0x28, 0xF1), None


def test_one_note_per_key_on():
    ws = freq(0, 4, 600) + [w(0, 0x28, 0xF1), w(10, 0x28, 0x01), w(12, 0x28, 0xF1), w(20, 0x28, 0x01)]
    notes = extract_notes_from_writes(ws, 8_000_000)
    assert [(n.channel, n.start, n.end) for n in notes] == [("fm1", 0, 10), ("fm1", 12, 20)]
    assert notes[0].pitch == fm_pitch(4, 600)


def test_small_change_keeps_note_large_change_splits():
    ws = freq(0, 4, 600) + [w(0, 0x28, 0xF1)]
    ws += freq(5, 4, 603)  # ~0.09 semitonos: misma nota
    ws += freq(8, 4, 650)  # ~1.4 semitonos: otra nota
    ws += [w(15, 0x28, 0x01)]
    notes = extract_notes_from_writes(ws, 8_000_000)
    assert [(n.start, n.end) for n in notes] == [(0, 8), (8, 15)]
    assert notes[1].pitch == fm_pitch(4, 650)


def test_frequency_written_after_key_on_in_same_frame_sets_pitch():
    ws = [w(0, 0x28, 0xF1)] + freq(0, 4, 700) + [w(6, 0x28, 0x01)]
    notes = extract_notes_from_writes(ws, 8_000_000)
    assert len(notes) == 1 and notes[0].pitch == fm_pitch(4, 700)


def test_ssg_note_while_audible():
    ws = [w(0, 0, 0x7C), w(0, 1, 0x01), w(0, 7, 0x38), w(2, 8, 0x0F), w(9, 8, 0x00)]
    notes = extract_notes_from_writes(ws, 8_000_000)
    assert [(n.channel, n.start, n.end) for n in notes] == [("ssg1", 2, 9)]
