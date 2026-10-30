"""Pruebas del Frame_Stream."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngband_tools.frames import (  # noqa: E402
    Drum,
    RegWrite,
    build_frames,
    decode_stream,
    encode_stream,
    format_c_array,
    parse_c_array,
)
from ngband_tools.vgm import Write  # noqa: E402


def test_dedup_and_exact_bytes():
    items = [
        (0, RegWrite(0, 0x07, 0x38)),
        (1, RegWrite(0, 0x07, 0x38)),  # repite: se omite
        (1, RegWrite(1, 0x30, 0x71)),
        (3, Drum(5)),
    ]
    frames = build_frames(items)
    assert frames == [[RegWrite(0, 7, 0x38)], [RegWrite(1, 0x30, 0x71)], [], [Drum(5)]]
    assert encode_stream(frames) == bytes([1, 7, 0x38, 2, 0xFD, 1, 0x30, 0x71, 0, 1, 0xFE, 5])


def test_event_registers_and_drums_are_not_deduped():
    items = [(0, RegWrite(0, 0x28, 0xF1)), (1, RegWrite(0, 0x28, 0xF1)), (1, Drum(2)), (2, Drum(2))]
    frames = build_frames(items)
    assert [len(f) for f in frames] == [1, 2, 1]


def test_accepts_vgm_writes():
    frames = build_frames([(0, Write(0, "ym1", 0x10, 0x80))])
    assert frames == [[RegWrite(1, 0x10, 0x80)]]


def test_continuation_roundtrip():
    frame = [RegWrite(0, 0x30 + (i % 0x40), i % 256) for i in range(254)] + [Drum(i % 6) for i in range(300)]
    frames = [frame, [], [Drum(1)]]
    data = encode_stream(frames)
    assert 255 in data[:1]
    assert decode_stream(data) == frames


def test_c_array_roundtrip():
    frames = build_frames([(0, RegWrite(0, 7, 1)), (2, Drum(3))])
    data = encode_stream(frames)
    assert decode_stream(parse_c_array(format_c_array(data))) == frames


def test_truncated_stream_fails():
    with pytest.raises(ValueError):
        decode_stream(bytes([2, 1, 1]))


def test_invalid_register_rejected():
    with pytest.raises(ValueError):
        build_frames([(0, RegWrite(0, 0xFE, 0))])


def test_254_pairs_never_look_like_repeat():
    frames = [[RegWrite(0, 0x30, i % 256) for i in range(254)], [Drum(1)]]
    data = encode_stream(frames)
    assert data[0] == 255 and data[1 + 2 * 254] == 0
    assert decode_stream(data) == frames


def test_compress_roundtrip_and_shrinks_repeated_bars():
    from ngband_tools.frames import compress_stream, expand_stream, _one_frame, REPEAT
    bar = [[RegWrite(0, 0x08, k), RegWrite(1, 0x41, k)] for k in range(16)] + [[]] * 8
    data = encode_stream(bar * 10 + [[Drum(2)]] + bar * 3)
    packed = compress_stream(data)
    assert expand_stream(packed) == data
    assert len(packed) < len(data) // 5
    # una racha citada nunca contiene otro REPEAT
    p = 0
    while p < len(packed):
        if packed[p] == REPEAT:
            off = packed[p + 1] | packed[p + 2] << 8 | packed[p + 3] << 16
            assert packed[off] != REPEAT
            p += 6
        else:
            p += len(_one_frame(packed, p))
