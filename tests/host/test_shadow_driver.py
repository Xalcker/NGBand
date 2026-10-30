"""Tarea 7.3: batería, efectos, pausa y búsqueda del modelo de sombra (shadow.c).

shadow.h no está en HEADERS de conftest (tiene punteros a función), así que se declara a mano.
"""
from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

CMD_SILENCE_ALL, CMD_SONG_START, CMD_RESET, CMD_FRAME, CMD_HOLD = 1, 2, 3, 4, 5
CMD_SONG_SEEK = 0x0C
CMD_PAUSE, CMD_RESUME, CMD_MUTE_INST, CMD_UNMUTE_INST, CMD_SFX = 6, 7, 8, 9, 10
INST_DRUMS = 3
SFX_COUNT = 6
SFX_LENGTHS = [3, 14, 10, 13, 11, 20]  # pasos de cada efecto (un cuadro por paso)
SH_MAP_SPAN = 0x2000

SHADOW_CDEF = """
typedef void (*ShadowWriteFn)(u8 port, u8 reg, u8 value);
typedef void (*ShadowDrumFn)(u8 sample);
typedef const u8 *(*ShadowMapFn)(u32 addr);
typedef struct { u32 stream; u32 end; u16 inst_mask[4]; } SongInfo;
typedef struct { u16 start; u16 end; } DrumSample;
typedef struct {
  u8 reg[2][256];
  u16 muted;
  u16 inst_mask[4];
  u32 start;
  u32 pos;
  u32 end;
  u32 ret;
  u16 rep_left;
  const DrumSample *drums;
  u8 drum_count;
  u8 drum_next;
  u8 drum_muted;
  u8 paused;
  u8 replay;
  u8 keyon[4];
  u8 sfx_active;
  u8 sfx_id;
  u8 sfx_pos;
  u8 sfx_mix;
  u8 frames;
  u8 pending;
  const SongInfo *songs;
  u8 song_count;
  ShadowWriteFn write;
  ShadowDrumFn drum;
  ShadowMapFn map;
  u8 rx_count;
} ShadowRegs;
void shadow_init(ShadowRegs *s, ShadowWriteFn write, ShadowDrumFn drum, ShadowMapFn map,
                 const SongInfo *songs, u8 song_count);
void shadow_set_drums(ShadowRegs *s, const DrumSample *drums, u8 count);
void shadow_rx(ShadowRegs *s, u8 byte);
void shadow_command(ShadowRegs *s, u8 cmd, u8 arg);
void shadow_write(ShadowRegs *s, u8 port, u8 reg, u8 value);
u8 shadow_response(const ShadowRegs *s);
u16 shadow_stream_frames(const ShadowRegs *s, u32 start, u32 end);
"""

_declared = False


def frame_bytes(pairs):
    """Un cuadro del Frame_Stream: con más de 254 pares, bloques de 255 (continuación) y el resto."""
    pairs = list(pairs)
    out = []
    while len(pairs) > 254:
        out.append(255)
        for a, b in pairs[:254]:
            out += [a, b]
        pairs = pairs[254:]
    out.append(len(pairs))
    for a, b in pairs:
        out += [a, b]
    return out


class Rig:
    """Un ShadowRegs con un chip simulado (registro de escrituras y último valor por registro).

    Con `windowed=True`, `map` imita los bancos del Z80: copia solo SH_MAP_SPAN bytes desde la posición
    pedida a una ventana y deja basura (0xFF) después, así que leer fuera de la ventana se nota."""

    def __init__(self, ffi, lib, frames=(), drums=(), base=0, windowed=False, raw=None):
        self.ffi, self.lib = ffi, lib
        self.log: list[tuple[int, int, int]] = []
        self.chip = {}
        self.drum_events: list[int] = []

        @ffi.callback("void(u8,u8,u8)")
        def write(port, reg, value):
            self.log.append((port, reg, value))
            self.chip[(port, reg)] = value

        @ffi.callback("void(u8)")
        def drum(n):
            self.drum_events.append(n)

        data = raw if raw is not None else bytes(b for f in frames for b in frame_bytes(f))
        self.data = data
        self.stream = ffi.new("u8[]", data or b"\0")
        self.window = ffi.new("u8[]", SH_MAP_SPAN + 512)
        self.maps: list[int] = []

        @ffi.callback("const u8 *(u32)")
        def map_(addr):
            self.maps.append(addr)
            off = addr - base
            if not windowed:
                return self.stream + off
            chunk = data[off:off + SH_MAP_SPAN]
            ffi.memmove(self.window, chunk + b"\xFF" * (SH_MAP_SPAN + 512 - len(chunk)), SH_MAP_SPAN + 512)
            return self.window

        self._cbs = (write, drum, map_)
        self.songs = ffi.new("SongInfo[1]")
        self.songs[0].stream = base
        self.songs[0].end = base + len(data)
        self.drum_tab = ffi.new("DrumSample[]", [(a, b) for a, b in drums] or [(0, 0)])
        self.s = ffi.new("ShadowRegs *")
        lib.shadow_init(self.s, write, drum, map_, self.songs, 1)
        lib.shadow_set_drums(self.s, self.drum_tab, len(drums))
        self.log.clear()

    def cmd(self, c, arg=None):
        self.lib.shadow_rx(self.s, c)
        if arg is not None:
            self.lib.shadow_rx(self.s, arg)

    def start(self):
        self.cmd(CMD_SONG_START, 0)
        self.log.clear()

    def frame(self, n=1):
        for _ in range(n):
            self.cmd(CMD_FRAME)

    def keyons(self):
        """Canales ADPCM-A disparados, en orden."""
        return [v.bit_length() - 1 for p, r, v in self.log if p == 1 and r == 0 and 0 < v < 0x40]


@pytest.fixture()
def rig(ffi, lib):
    global _declared
    if not _declared:
        ffi.cdef(SHADOW_CDEF)
        _declared = True
    return lambda frames=(), drums=(), **kw: Rig(ffi, lib, frames, drums, **kw)


# ---- Batería (R13.1, R13.4) ----

def test_drums_round_robin_and_sample_regs(rig):
    drums = [(0x10, 0x1F), (0x20, 0x2F)]
    r = rig(frames=[[(0xFE, i % 2)] for i in range(8)], drums=drums)
    r.start()
    r.frame(8)
    assert r.keyons() == [0, 1, 2, 3, 4, 5, 0, 1]
    assert r.drum_events == [0, 1, 0, 1, 0, 1, 0, 1]
    # El primer golpe usa el sample 0 en el canal 0.
    assert r.log.index((1, 0x10, 0x10)) < r.log.index((1, 0x00, 0x01))
    assert (1, 0x20, 0x1F) in r.log and (1, 0x18, 0x00) in r.log and (1, 0x28, 0x00) in r.log


def test_drum_out_of_range_sample_is_ignored(rig):
    r = rig(frames=[[(0xFE, 5)]], drums=[(1, 2)])
    r.start()
    r.frame()
    assert r.keyons() == []


def test_mute_drums_until_unmute(rig):
    r = rig(frames=[[(0xFE, 0)]] * 3, drums=[(1, 2)])
    r.start()
    r.cmd(CMD_MUTE_INST, INST_DRUMS)
    assert (1, 0x00, 0xBF) in r.log  # corta los canales ADPCM-A
    r.log.clear()
    r.frame()
    assert r.keyons() == []
    r.cmd(CMD_UNMUTE_INST, INST_DRUMS)
    r.frame()
    assert r.keyons() == [0]


# ---- Pausa (R12.7) ----

def test_pause_keeps_cursor_and_frame_then_resumes_state(rig):
    frames = [
        [(0xB1, 0x07), (0x41, 0x10), (0xA5, 0x22), (0xA1, 0x55), (0x28, 0xF1), (0x08, 12)],
        [(0x08, 9)],
        [(0x08, 7)],
    ]
    r = rig(frames=frames)
    r.start()
    r.frame()
    pos = r.s.pos
    resp = r.s.frames
    r.cmd(CMD_PAUSE)
    assert r.chip[(0, 0x28)] == 0x06 and r.chip[(0, 0x08)] == 0
    r.frame(5)
    assert r.s.pos == pos and r.s.frames == resp
    r.log.clear()
    r.cmd(CMD_RESUME)
    assert r.chip[(0, 0x08)] == 12 and r.chip[(0, 0x41)] == 0x10
    assert (0, 0x28, 0xF1) in r.log  # la tecla presionada se repone
    assert r.log.index((0, 0xA5, 0x22)) < r.log.index((0, 0xA1, 0x55))
    r.frame()
    assert r.chip[(0, 0x08)] == 9  # el siguiente cuadro, sin saltarse ninguno
    assert r.s.frames == resp + 1


# ---- Efectos (R12.5, R12.6) ----

def test_sfx_takes_ssg3_and_restores_from_shadow(rig):
    song_writes = [(0x04, 0x34), (0x05, 0x02), (0x07, 0xFB), (0x0A, 9)]
    r = rig(frames=[song_writes] + [[(0x0A, 5), (0x04, 0x77)]] + [[]] * 40)
    r.start()
    r.frame()
    r.cmd(CMD_SFX, 1)  # SFX_ACCEPT
    assert r.chip[(0, 0x0A)] == 12 and r.chip[(0, 0x07)] & 0x04 == 0
    r.frame()  # la canción pide cambios en el canal que ocupa el efecto: no llegan al chip
    assert r.chip[(0, 0x04)] != 0x77 and r.chip[(0, 0x0A)] != 5
    r.frame(SFX_LENGTHS[1])
    assert not r.s.sfx_active
    for reg in (0x04, 0x05, 0x06, 0x07, 0x0A):
        assert r.chip[(0, reg)] == r.s.reg[0][reg]
    assert r.chip[(0, 0x0A)] == 5 and r.chip[(0, 0x04)] == 0x77


@pytest.mark.parametrize("sfx", range(SFX_COUNT))
def test_every_sfx_ends_after_its_steps(rig, sfx):
    r = rig(frames=[[]] * 40)
    r.start()
    r.cmd(CMD_SFX, sfx)
    assert r.s.sfx_active
    r.frame(SFX_LENGTHS[sfx] - 1)
    assert r.s.sfx_active
    r.frame()
    assert not r.s.sfx_active


def test_sfx_invalid_id_is_ignored(rig):
    r = rig()
    r.start()
    r.cmd(CMD_SFX, SFX_COUNT)
    assert not r.s.sfx_active and r.log == []


def test_sfx_plays_while_paused_and_survives_hold(rig):
    r = rig(frames=[[(0x0A, 9)]] * 3)
    r.start()
    r.cmd(CMD_PAUSE)
    r.cmd(CMD_SFX, 0)
    assert r.chip[(0, 0x0A)] == 12
    r.cmd(CMD_HOLD)
    assert r.s.sfx_pos == 1


# ---- Búsqueda (R8.6) ----

def test_seek_quarter_positions_stream_and_chip(rig):
    n = 16
    r = rig(frames=[[(0x08, i + 1), (0x41, 0x10 + i)] for i in range(n)])
    r.start()
    r.frame(3)
    r.cmd(CMD_SONG_SEEK, 2)  # mitad: 8 cuadros aplicados
    assert r.s.frames == 8
    assert r.chip[(0, 0x08)] == 8 and r.chip[(0, 0x41)] == 0x10 + 7
    r.frame()
    assert r.chip[(0, 0x08)] == 9  # sigue desde el cuadro 8


def test_seek_zero_restarts_and_preserves_mute_and_pause(rig):
    r = rig(frames=[[(0x08, i + 1)] for i in range(8)])
    r.songs[0].inst_mask[0] = 0x10  # guitarra = SSG 1
    r.start()
    r.frame(4)
    r.cmd(CMD_MUTE_INST, 0)
    r.cmd(CMD_PAUSE)
    r.cmd(CMD_SONG_SEEK, 0)
    assert r.s.frames == 0 and r.s.paused and r.s.muted == 0x10
    assert r.chip[(0, 0x08)] == 0
    r.cmd(CMD_RESUME)
    assert r.chip[(0, 0x08)] == 0  # sigue silenciado
    r.frame()
    assert r.s.reg[0][0x08] == 1


def test_seek_invalid_quarter_or_no_song_is_ignored(rig):
    r = rig(frames=[[(0x08, 1)]] * 4)
    r.cmd(CMD_SONG_SEEK, 1)  # sin canción
    r.start()
    r.frame(2)
    r.cmd(CMD_SONG_SEEK, 4)
    assert r.s.frames == 2


def test_stream_frames_counts_continuations(ffi, lib, rig):
    r = rig()
    big = [255] + [0x08, 1] * 254 + [1, 0x09, 2]  # un cuadro continuado
    data = bytes(big + frame_bytes([(0x08, 3)]))
    buf = ffi.new("u8[]", data)
    keep = ffi.callback("const u8 *(u32)", lambda addr: buf + addr)
    r.s.map = keep
    assert lib.shadow_stream_frames(r.s, 0, len(data)) == 2


def test_response_counts_processed_bytes(rig):
    """La respuesta es la cuenta de bytes procesados (un comando con argumento cuenta 2); CMD_RESET la pone en 0."""
    r = rig(frames=[[(0x08, 1)]] * 4)
    assert r.lib.shadow_response(r.s) == 0
    r.cmd(CMD_SONG_START, 0)
    r.frame(3)
    assert r.lib.shadow_response(r.s) == 5
    for _ in range(300):
        r.cmd(CMD_HOLD)
    assert r.lib.shadow_response(r.s) == (305 & 0xFF)
    r.cmd(CMD_RESET)
    assert r.lib.shadow_response(r.s) == 0


def test_bios_reset_command_takes_no_argument_and_stops_song(rig):
    """La BIOS manda 0x03 al Z80 del cartucho: no debe tragarse el byte siguiente (el primer comando del juego)."""
    r = rig(frames=[[(0x08, i + 1)] for i in range(4)])
    r.start()
    r.frame()
    r.cmd(CMD_RESET)
    assert r.s.pending == 0 and r.s.start == r.s.end
    r.cmd(CMD_SONG_START, 0)
    r.frame()
    assert r.chip[(0, 0x08)] == 1


# ---- Bancos del Z80: el stream se lee por ventanas ----

def test_banked_stream_maps_each_frame_at_its_linear_address(rig):
    frames = [[(0x08, i + 1)] * (i % 3 + 1) for i in range(6)]
    r = rig(frames=frames, base=0x8000, windowed=True)
    r.start()
    r.frame(6)
    sizes = [len(frame_bytes(f)) for f in frames]
    assert r.maps == [0x8000 + sum(sizes[:i]) for i in range(6)]
    assert r.s.pos == r.s.end == 0x8000 + sum(sizes)
    r.maps.clear()
    r.frame()  # fin del stream: no se lee nada
    assert r.maps == []


def test_banked_stream_crossing_window_boundaries(rig):
    """Un stream de varias ventanas (con un cuadro continuado) suena igual leído por ventanas que de corrido."""
    frames = [[(0x41, i & 0x7F), (0x08, (i * 7) & 0x0F)] for i in range(3000)]
    frames[1500] = [(0x09, k & 0x0F) for k in range(300)]  # cuadro con continuación
    a = rig(frames=frames, base=0x1FFF0, windowed=True)
    b = rig(frames=frames)
    for r in (a, b):
        r.start()
        r.frame(len(frames))
    assert a.log == b.log
    assert a.s.pos - a.s.start == len(a.data)


REGS = st.sampled_from([0x00, 0x01, 0x08, 0x09, 0x0A, 0x41, 0x42, 0x31, 0xB1, 0xB2, 0xA5, 0xA1])
FRAME = st.lists(st.tuples(REGS, st.integers(0, 127)), max_size=4)


# Feature: neogeo-band, Property 24 (parcial, 7.3): buscar equivale a reproducir hasta ese cuadro
# **Validates: Requirements 12.6, 12.7**
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow], deadline=None)
@given(frames=st.lists(FRAME, min_size=4, max_size=40), quarter=st.integers(0, 3))
def test_seek_equals_sequential_playback(rig, frames, quarter):
    a = rig(frames=frames)
    a.start()
    a.cmd(CMD_SONG_SEEK, quarter)
    target = (len(frames) // 4) * quarter
    b = rig(frames=frames)
    b.start()
    b.frame(target)
    assert bytes(a.ffi.buffer(a.s.reg)) == bytes(b.ffi.buffer(b.s.reg))
    assert a.s.pos - a.s.start == b.s.pos - b.s.start
    assert a.s.frames == b.s.frames
    for k in set(a.chip) & {(0, 0x08), (0, 0x09), (0, 0x0A)}:
        assert a.chip[k] == b.chip[k]


# ---- FS_REPEAT: el stream comprimido de la M1 suena igual que el original ----

def _compress(data):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pctools"))
    from ngband_tools.frames import compress_stream, expand_stream
    packed = compress_stream(data)
    assert expand_stream(packed) == data
    return packed


def test_repeat_plays_like_the_original_stream(rig):
    bar = [[(0x08, k), (0x41, 0x20 + k)] for k in range(8)] + [[]] * 4
    frames = bar * 6 + [[(0x09, 3)]] + bar * 2
    raw = bytes(b for f in frames for b in frame_bytes(f))
    packed = _compress(raw)
    assert len(packed) < len(raw) // 2 and packed.count(254) >= 1
    a = rig(raw=packed, base=0x24000, windowed=True)
    b = rig(frames=frames)
    for r in (a, b):
        r.start()
        r.frame(len(frames) + 2)
    assert a.log == b.log
    assert a.s.pos == a.s.end and a.s.rep_left == 0
    assert a.lib.shadow_stream_frames(a.s, a.s.start, a.s.end) == len(frames)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow], deadline=None)
@given(frames=st.lists(st.sampled_from([[], [(0x08, 1)], [(0x08, 2), (0x41, 5)], [(0x09, 7)] * 3]),
                       min_size=4, max_size=120), quarter=st.integers(0, 3))
def test_seek_in_compressed_stream_equals_original(rig, frames, quarter):
    raw = bytes(b for f in frames for b in frame_bytes(f))
    a = rig(raw=_compress(raw), windowed=True)
    b = rig(frames=frames)
    for r in (a, b):
        r.start()
        r.cmd(CMD_SONG_SEEK, quarter)
        r.frame(3)
    assert bytes(a.ffi.buffer(a.s.reg)) == bytes(b.ffi.buffer(b.s.reg))
    assert a.s.frames == b.s.frames
