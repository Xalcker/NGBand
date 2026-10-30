"""Pruebas de la conversión a ADPCM-A y del mapa de samples (R13.1, R13.2, R17.10)."""
import math
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngband_tools import adpcma  # noqa: E402


def sine(n, amp=12000, period=40):
    return [int(amp * math.sin(2 * math.pi * i / period)) for i in range(n)]


def test_encode_pads_to_256_byte_blocks():
    assert len(adpcma.encode(sine(100))) == 256
    assert len(adpcma.encode(sine(513))) == 512


def test_empty_pcm_is_rejected():
    with pytest.raises(ValueError):
        adpcma.encode([])


def test_decode_follows_the_signal():
    pcm = sine(1000)
    out = adpcma.decode(adpcma.encode(pcm))[:1000]
    # el decodificador entrega 12 bits: se compara contra el PCM escalado
    err = sum(abs(a - (b >> 4)) for a, b in zip(out[100:], pcm[100:])) / 900
    assert err < 150


@settings(max_examples=100, deadline=None)
@given(st.lists(st.integers(-32768, 32767), min_size=1, max_size=600))
def test_encode_size_and_range_property(pcm):
    data = adpcma.encode(pcm)
    assert len(data) % adpcma.BLOCK_BYTES == 0 and len(data) >= len(pcm) // 2
    assert all(-2048 <= x <= 2047 for x in adpcma.decode(data))


def test_sample_map_places_samples_back_to_back():
    m = adpcma.convert_samples([("bombo", sine(600)), ("caja", sine(100))])
    a, b = m.entries
    assert (a.index, b.index) == (0, 1)
    assert a.start_block == 0 and b.start_block == a.end_block + 1
    assert m.used == len(m.rom) == a.size + b.size


def test_sample_map_overflow_reports_sizes():
    with pytest.raises(adpcma.AdpcmRomOverflow) as e:
        adpcma.convert_samples([("a", sine(2000))], rom_size=256)
    assert e.value.capacity == 256 and e.value.excess == e.value.size - 256 > 0


def test_map_drum_hits_indices_are_valid():
    m = adpcma.convert_samples([("bombo", sine(100)), ("caja", sine(100))])
    events = adpcma.map_drum_hits([(10, "caja"), (20, "bombo")], m)
    assert events == [(10, 1), (20, 0)]
    assert all(0 <= n < len(m) for _, n in events)
    with pytest.raises(adpcma.UnknownDrumSample):
        adpcma.map_drum_hits([(1, "platillo")], m)
