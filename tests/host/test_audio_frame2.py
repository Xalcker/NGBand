"""Integración 9.1/9.2: CMD_FRAME2 (velocidad 125%), cola de audio y diseño de ChartCursor para autoplay.lua."""
from __future__ import annotations

from test_shadow_driver import CMD_FRAME, CMD_HOLD, CMD_SONG_START, frame_bytes  # noqa: F401
from test_shadow_driver import rig  # noqa: F401  (fixture)

AUDIO_CDEF = """
typedef struct {
  u16 q[16]; u8 head, tail; u8 arg_pending; u8 arg; u8 expected; u8 check_enabled; u8 overflow;
  u16 desync_count; u8 last_expected, last_reply; u8 grace; u8 lag_run; u8 sent; u8 stall; u8 boot_wait;
} AudioCmd;
void ac_init(AudioCmd *a);
u8 ac_push(AudioCmd *a, u8 cmd, u8 arg);
u8 ac_pending(const AudioCmd *a);
u8 ac_next_byte(AudioCmd *a, u8 *byte);
u8 ac_check(AudioCmd *a, u8 reply);
void ac_flush(AudioCmd *a);
u8 ac_pump(AudioCmd *a, u8 (*reply)(void), void (*write)(u8));
"""
_declared = False

CMD_SILENCE_ALL = 0x01
CMD_RESET = 0x03
CMD_MUTE_INST = 0x08
CMD_FRAME2 = 0x0B
CMD_COUNT = 0x0D


def test_frame2_applies_two_frames(rig):
    r = rig(frames=[[(0x07, i)] for i in range(1, 5)])
    r.start()
    r.cmd(CMD_FRAME2)
    assert [v for _, reg, v in r.log if reg == 0x07] == [1, 2]
    assert r.s.frames == 2
    r.cmd(CMD_FRAME)
    assert r.s.frames == 3


def _audio(ffi, lib):
    global _declared
    if not _declared:
        ffi.cdef(AUDIO_CDEF)
        _declared = True
    a = ffi.new("AudioCmd *")
    assert ffi.offsetof("AudioCmd", "desync_count") == 40   # lo lee autoplay.lua (probe.h)
    lib.ac_init(a)
    return a


def test_speed_125_fits_one_byte_per_vblank(ffi, lib):
    """5 pasos cada 4 cuadros de video: 1,1,1,2 -> un comando por VBlank, sin desbordar la cola."""
    a = _audio(ffi, lib)
    sent = []
    byte = ffi.new("u8 *")
    for vb in range(400):
        steps = 2 if vb % 4 == 3 else 1
        assert lib.ac_push(a, CMD_FRAME2 if steps == 2 else CMD_FRAME, 0) == 1
        assert lib.ac_next_byte(a, byte) == 1
        sent.append(byte[0])
    assert not a.overflow
    assert lib.ac_pending(a) == 0
    assert a.expected == (500 & 0xFF)          # 400 VBlanks * 5/4
    assert lib.ac_check(a, a.sent) == 1              # el Z80 procesó todo lo enviado
    assert sent.count(CMD_FRAME2) == 100


def test_frame2_is_valid_command_and_count(ffi, lib):
    a = _audio(ffi, lib)
    assert lib.ac_push(a, CMD_FRAME2, 0) == 1
    assert lib.ac_push(a, CMD_COUNT, 0) == 0


def test_chart_cursor_layout_matches_autoplay_lua(ffi):
    """Constantes de tests/autoplay.lua (CURSOR_*, PN_*); el 68000 alinea a 2 y no hay punteros."""
    assert ffi.sizeof("ChartCursor") == 214
    assert ffi.sizeof("PendingNote") == 8
    off = lambda t, f: ffi.offsetof(t, f)  # noqa: E731
    assert (off("ChartCursor", "head"), off("ChartCursor", "count"), off("ChartCursor", "q")) == (5, 6, 8)
    assert [off("PendingNote", f) for f in ("frame", "end", "mask", "open", "flags")] == [0, 2, 4, 5, 6]
    assert ffi.sizeof("PendingNote") * 24 + 8 <= 214


def test_check_tolerates_short_lag_but_not_a_lasting_one(ffi, lib):
    """Un cuadro pesado atrasa al Z80 unos VBlanks: no es desincronía; un byte perdido (atraso fijo), sí."""
    a = _audio(ffi, lib)
    a.sent = 40
    assert lib.ac_check(a, 39) == 1 and lib.ac_check(a, 20) == 1
    assert lib.ac_check(a, 40) == 1 and a.desync_count == 0
    assert lib.ac_check(a, 3) == 0 and a.desync_count == 1        # 37 bytes atrás: desincronía
    a.sent = 20
    results = [lib.ac_check(a, 19) for _ in range(31)]
    assert results[:30] == [1] * 30 and results[30] == 0          # un byte perdido: el atraso no baja
    assert a.sent == 19 and lib.ac_check(a, 19) == 1               # se resincronizó con la respuesta
    assert lib.ac_check(a, 20) == 0                                # adelantada: nunca es atraso


def test_menu_restarts_do_not_confuse_the_check(ffi, lib):
    """Cambiar de canción muy seguido (SILENCE_ALL + SONG_START + cuadros) con el Z80 atrasado no es desincronía."""
    a = _audio(ffi, lib)
    byte = ffi.new("u8 *")
    sent = 0
    z80 = 0                                  # bytes que procesó el Z80: tras cada cambio se atasca 4 VBlanks
    stuck = 0
    for vb in range(200):
        if vb % 7 == 0:
            lib.ac_push(a, CMD_SILENCE_ALL, 0)
            lib.ac_push(a, CMD_SONG_START, vb % 10)
            stuck = 4
        lib.ac_push(a, CMD_FRAME, 0)
        assert lib.ac_check(a, z80 & 0xFF) == 1
        if lib.ac_next_byte(a, byte):
            sent += 1
        if stuck:
            stuck -= 1
        else:
            z80 = sent                       # se pone al día
    assert a.desync_count == 0


def test_reset_waits_for_the_z80_to_restart(ffi, lib):
    byte = ffi.new("u8 *")
    a = _audio(ffi, lib)
    a.sent = 77
    lib.ac_push(a, CMD_RESET, 0)
    assert lib.ac_next_byte(a, byte) and byte[0] == CMD_RESET and a.sent == 0
    for _ in range(20):
        assert lib.ac_check(a, 0xC3) == 1      # respuesta vieja de la BIOS mientras arranca
    assert lib.ac_check(a, 0) == 1 and a.grace == 0 and a.desync_count == 0
    a = _audio(ffi, lib)
    lib.ac_push(a, CMD_RESET, 0)
    lib.ac_next_byte(a, byte)
    assert [lib.ac_check(a, 0x80) for _ in range(61)][-1] == 0   # nunca arrancó: se cuenta


def _drain(ffi, lib, a):
    byte = ffi.new("u8 *")
    out = []
    while lib.ac_next_byte(a, byte):
        out.append(byte[0])
    return out


def test_backlog_merges_frames_and_drops_extra_holds(ffi, lib):
    """Un comando de dos bytes deja un byte de atraso; se recupera sin perder cuadros del stream."""
    a = _audio(ffi, lib)
    byte = ffi.new("u8 *")
    lib.ac_push(a, CMD_MUTE_INST, 0)
    lib.ac_push(a, CMD_FRAME, 0)
    sent = []
    for _ in range(6):                     # un comando por paso y un byte por VBlank
        lib.ac_push(a, CMD_FRAME, 0)
        assert lib.ac_next_byte(a, byte)
        sent.append(byte[0])
    assert sent[:2] == [CMD_MUTE_INST, 0]
    assert CMD_FRAME2 in sent
    assert a.expected == 7 and lib.ac_pending(a) <= 1
    a2 = _audio(ffi, lib)
    for c in (CMD_HOLD, CMD_HOLD, CMD_FRAME):
        lib.ac_push(a2, c, 0)
    assert _drain(ffi, lib, a2) == [CMD_FRAME]
    lib.ac_push(a2, CMD_HOLD, 0)
    assert _drain(ffi, lib, a2) == [CMD_HOLD]   # sin atraso, el HOLD sí se manda


def test_flush_keeps_a_half_sent_argument(ffi, lib):
    a = _audio(ffi, lib)
    byte = ffi.new("u8 *")
    lib.ac_push(a, CMD_SONG_START, 5)
    for _ in range(5):
        lib.ac_push(a, CMD_FRAME, 0)
    assert lib.ac_next_byte(a, byte) and byte[0] == CMD_SONG_START
    lib.ac_flush(a)
    assert _drain(ffi, lib, a) == [5]


# ---- ac_pump: varios bytes por VBlank con confirmación del Z80 (NMI responde los bytes recibidos) ----
CMD_SFX = 0x0A
CMD_UNMUTE_INST = 0x09
AC_LAG_LIMIT = 30


class FakeZ80:
    """Latch de un byte: escribir sobre un byte que la NMI no ha leído lo pisa. `delay` lecturas de la respuesta
    pasan antes de que la NMI tome el byte; con `dead` nunca lo toma."""

    def __init__(self, ffi, delay=0, dead=False, reply=0):
        self.got, self.lost, self.count, self.delay, self.dead = [], 0, 0, delay, dead
        self.latch, self.wait, self.bios_reply = None, 0, reply
        self.reply_cb = ffi.callback("u8(void)", self._reply)
        self.write_cb = ffi.callback("void(u8)", self._write)

    def _nmi(self):
        b, self.latch = self.latch, None
        self.got.append(b)
        self.count = 0 if b == CMD_RESET and (len(self.got) == 1 or self.got[-2] not in (0x02, 0x08, 0x09, 0x0A, 0x0C)) \
            else (self.count + 1) & 0xFF
        self.bios_reply = None

    def _reply(self):
        if self.latch is not None and not self.dead:
            if self.wait <= 0:
                self._nmi()
            else:
                self.wait -= 1
        return self.count if self.bios_reply is None else self.bios_reply

    def _write(self, b):
        if self.latch is not None:
            self.lost += 1
        self.latch, self.wait = b, self.delay

    def vblank_end(self):
        """Entre VBlanks el Z80 siempre alcanza a tomar el byte."""
        if self.latch is not None and not self.dead:
            self._nmi()


def _pump(lib, a, z):
    n = lib.ac_pump(a, z.reply_cb, z.write_cb)
    z.vblank_end()
    return n


def test_pump_sends_reset_without_ack_and_waits(ffi, lib):
    a = _audio(ffi, lib)
    z = FakeZ80(ffi, reply=0x5A)                  # la BIOS deja otra respuesta
    lib.ac_push(a, CMD_RESET, 0)
    lib.ac_push(a, CMD_SILENCE_ALL, 0)
    assert _pump(lib, a, z) == 1                  # solo el RESET en ese VBlank
    assert _pump(lib, a, z) == 0                  # AC_RESET_WAIT: el driver arranca
    assert _pump(lib, a, z) == 0
    assert _pump(lib, a, z) == 1
    assert z.got == [CMD_RESET, CMD_SILENCE_ALL] and z.lost == 0


def test_pump_miss_does_not_delay_frame(ffi, lib):
    """Un fallo (silencio + efecto, 4 bytes) sale en el mismo VBlank que su CMD_FRAME: el stream no se atrasa."""
    a = _audio(ffi, lib)
    z = FakeZ80(ffi, delay=3)
    lib.ac_push(a, CMD_SONG_START, 1)
    _pump(lib, a, z)
    for vb in range(200):
        lib.ac_push(a, CMD_FRAME, 0)
        if vb % 7 == 3:
            lib.ac_push(a, CMD_MUTE_INST, 0)
            lib.ac_push(a, CMD_SFX, 5)
        if vb % 7 == 5:
            lib.ac_push(a, CMD_UNMUTE_INST, 0)
        _pump(lib, a, z)
        assert lib.ac_pending(a) == 0 and not a.arg_pending
        assert a.expected == vb + 1
    assert z.lost == 0 and a.desync_count == 0
    assert z.got.count(CMD_FRAME) == 200 and z.got.count(CMD_FRAME2) == 0


def test_pump_never_overwrites_unread_byte(ffi, lib):
    a = _audio(ffi, lib)
    z = FakeZ80(ffi, delay=10_000)                # más lento que AC_ACK_SPIN: un byte por VBlank
    for _ in range(4):
        lib.ac_push(a, CMD_FRAME, 0)
    assert _pump(lib, a, z) == 1
    assert z.lost == 0


def test_pump_recovers_from_dead_z80(ffi, lib):
    a = _audio(ffi, lib)
    z = FakeZ80(ffi, dead=True)
    lib.ac_push(a, CMD_FRAME, 0)
    lib.ac_push(a, CMD_SILENCE_ALL, 0)             # (dos FRAME se juntarían en un FRAME2)
    assert _pump(lib, a, z) == 1                  # el primero sale; el Z80 nunca lo confirma
    for _ in range(AC_LAG_LIMIT - 1):
        assert _pump(lib, a, z) == 0
    z.dead, z.latch = False, None                 # el byte se perdió; el Z80 vuelve
    n = _pump(lib, a, z)
    assert (n, a.stall, a.sent, a.desync_count, z.got) == (1, 0, 1, 1, [CMD_SILENCE_ALL])
    assert a.desync_count == 1
