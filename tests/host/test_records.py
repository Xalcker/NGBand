"""Pruebas de records.c (R9): codificación big endian, firma y suma."""
from hypothesis import given, strategies as st

SIZE = 6 + 128 * 14 + 2

entry = st.fixed_dictionaries({
    "title_hash": st.integers(0, 2**32 - 1),
    "instrument": st.integers(0, 3),
    "difficulty": st.integers(0, 3),
    "stars": st.integers(0, 5),
    "initials": st.lists(st.integers(65, 90), min_size=3, max_size=3),
    "score": st.integers(0, 2**32 - 1),
})


def _fill(ffi, entries):
    t = ffi.new("RecordTable *")
    t.count = len(entries)
    for i, d in enumerate(entries):
        e = t.e[i]
        e.title_hash, e.instrument, e.difficulty = d["title_hash"], d["instrument"], d["difficulty"]
        e.stars, e.score = d["stars"], d["score"]
        for k, c in enumerate(d["initials"]):
            e.initials[k] = bytes([c])
    return t


def _encode(ffi, lib, t):
    buf = ffi.new("uint8_t[]", SIZE)
    assert lib.records_encode(t, buf) == SIZE
    return buf


def test_encoded_layout(ffi, lib):
    t = _fill(ffi, [{"title_hash": 0x01020304, "instrument": 1, "difficulty": 2, "stars": 3,
                     "initials": [65, 66, 67], "score": 0x0A0B0C0D}])
    raw = bytes(_encode(ffi, lib, t))
    assert raw[:4] == b"NGBR" and raw[5] == 1
    assert raw[6:20] == bytes([1, 2, 3, 4, 1, 2, 3, 65, 66, 67, 0x0A, 0x0B, 0x0C, 0x0D])


# Feature: neogeo-band, Property 18: Round trip de la tabla de récords
@given(st.lists(entry, max_size=128))
def test_roundtrip(ffi, lib, entries):
    buf = _encode(ffi, lib, _fill(ffi, entries))
    out = ffi.new("RecordTable *")
    assert lib.records_decode(buf, SIZE, out)
    assert out.count == len(entries)
    for d, e in zip(entries, out.e):
        assert (e.title_hash, e.instrument, e.difficulty, e.stars, e.score) == (
            d["title_hash"], d["instrument"], d["difficulty"], d["stars"], d["score"])
        assert [ord(e.initials[k]) for k in range(3)] == d["initials"]


# Feature: neogeo-band, Property 19: Tablas corruptas se descartan
@given(st.lists(entry, max_size=20), st.integers(0, SIZE - 1), st.integers(1, 255))
def test_corrupt_is_discarded(ffi, lib, entries, pos, xor):
    buf = _encode(ffi, lib, _fill(ffi, entries))
    buf[pos] ^= xor
    out = ffi.new("RecordTable *")
    assert not lib.records_decode(buf, SIZE, out)
    assert out.count == 0 and bytes(ffi.buffer(out.magic)) == b"NGBR"


def test_short_buffer_is_empty(ffi, lib):
    out = ffi.new("RecordTable *")
    assert not lib.records_decode(ffi.new("uint8_t[]", 10), 10, out)
    assert out.count == 0


def test_save_get_beats_without_backup(ffi, lib):
    lib.records_init()
    assert not lib.records_backup_ok()
    assert not lib.record_beats(7, 0, 1, 0)
    assert lib.record_beats(7, 0, 1, 100)
    lib.record_save(7, 0, 1, 100, b"XYZ", 4)
    assert not lib.record_beats(7, 0, 1, 100)
    assert lib.record_beats(7, 0, 1, 101)
    out = ffi.new("RecordEntry *")
    assert lib.record_get(7, 0, 1, out) and out.score == 100 and out.stars == 4
    assert not lib.record_get(7, 0, 2, out)


def _run(ffi, mode=0, **kw):
    r = ffi.new("RecordRun *")
    r.mode, r.speed_default, r.fall_default = mode, True, True
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_eligibility_examples(ffi, lib):
    assert lib.is_record_eligible(_run(ffi))
    assert lib.is_record_eligible(_run(ffi, 2))
    for k in ("lost", "no_fail", "mirror", "practice"):
        assert not lib.is_record_eligible(_run(ffi, **{k: True}))
    assert not lib.is_record_eligible(_run(ffi, speed_default=False))
    assert not lib.is_record_eligible(_run(ffi, fall_default=False))
    assert not lib.is_record_eligible(_run(ffi, 1))
    assert not lib.is_record_eligible(_run(ffi, 2, p2_lost=True))


def test_submit_keeps_best_eligible(ffi, lib):
    lib.records_init()
    h = 0xABCD0001
    assert lib.record_submit(_run(ffi), h, 1, 3, 500, b"AAA", 3)
    assert not lib.record_submit(_run(ffi), h, 1, 3, 400, b"BBB", 5)      # no supera
    assert not lib.record_submit(_run(ffi, no_fail=True), h, 1, 3, 900, b"CCC", 5)  # inelegible
    assert lib.record_submit(_run(ffi), h, 1, 3, 600, b"DDD", 4)
    out = ffi.new("RecordEntry *")
    assert lib.record_get(h, 1, 3, out) and out.score == 600 and out.stars == 4
