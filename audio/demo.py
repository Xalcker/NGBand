"""Genera audio/demo.vgm: canción de demostración original (YM2610, 3 canales FM, sin samples).

    uv run python audio/demo.py
    uv run ngband import-song audio/demo.vgm --name demo --title "Demo" --game "NGBand" \
        --guitarra fm1 --teclado fm2 --bajo fm3 --beat-frames 30 --duration 60

Melodía en FM 1, acordes en FM 2 y bajo en FM 3, 120 BPM (30 cuadros por tiempo). Es determinista.
Licencia: GPL-2.0-or-later, como el resto del proyecto.
"""
import struct
from pathlib import Path

CLOCK = 8_000_000
SAMPLES_PER_FRAME = 735          # 44100 / 60
BEAT = 30                        # cuadros por tiempo
BARS = 16

# (puerto VGM, desplazamiento de canal, código de key-on) de FM 1, FM 2 y FM 3
CHANNELS = ((0x58, 1, 0x01), (0x58, 2, 0x02), (0x59, 1, 0x05))
KEYON = 0x28


def fnum_block(midi: float) -> tuple[int, int]:
    freq = 440 * 2 ** ((midi - 69) / 12)
    for block in range(8):
        fnum = round(freq * (1 << (21 - block)) / (CLOCK / 144))
        if fnum < 1100:
            return fnum, block
    raise ValueError(midi)


class Writer:
    def __init__(self) -> None:
        self.body = bytearray()
        self.samples = 0

    def reg(self, port: int, reg: int, val: int) -> None:
        self.body += bytes((port, reg, val))

    def wait(self, frames: int) -> None:
        n = frames * SAMPLES_PER_FRAME
        self.samples += n
        while n:
            step = min(n, 0xFFFF)
            self.body += b"\x61" + struct.pack("<H", step)
            n -= step


def patch(w: Writer, ch: int, port: int, off: int, tl: int, mul: int) -> None:
    """Patch sencillo: algoritmo 4 (dos pares modulador-portador) con envolvente de pluma."""
    for op in range(4):
        o = off + 4 * op
        carrier = op in (1, 3)
        w.reg(port, 0x30 + o, (0 if not carrier else 0) << 4 | (mul if carrier else 1))
        w.reg(port, 0x40 + o, tl if carrier else 0x2A)
        w.reg(port, 0x50 + o, 0x1F)
        w.reg(port, 0x60 + o, 0x0A if carrier else 0x08)
        w.reg(port, 0x70 + o, 0x04)
        w.reg(port, 0x80 + o, 0x35)
    w.reg(port, 0xB0 + off, (4 << 3) | 4)
    w.reg(port, 0xB4 + off, 0xC0)


def note(w: Writer, idx: int, midi: float) -> None:
    port, off, code = CHANNELS[idx]
    fnum, block = fnum_block(midi)
    w.reg(port, 0xA4 + off, (block << 3) | (fnum >> 8))
    w.reg(port, 0xA0 + off, fnum & 0xFF)
    w.reg(0x58, KEYON, 0xF0 | code)


def off(w: Writer, idx: int) -> None:
    w.reg(0x58, KEYON, CHANNELS[idx][2])


def build() -> bytes:
    w = Writer()
    for idx, (port, o, _) in enumerate(CHANNELS):
        patch(w, idx, port, o, (0x18, 0x20, 0x14)[idx], (1, 1, 1)[idx])
    scale = (0, 2, 4, 7, 9, 12, 9, 7)           # pentatónica de Do mayor
    roots = (48, 45, 41, 43)                     # C, Am, F, G
    for bar in range(BARS):
        root = roots[bar % 4]
        for beat in range(4):
            step = bar * 4 + beat
            note(w, 0, 60 + scale[(step * 3 + (step >> 2)) % 8] + (12 if step % 5 == 4 else 0))
            if beat in (0, 2):
                note(w, 1, root + 12 + (7 if beat == 2 else 4))
                note(w, 2, root - 12 + (0 if beat == 0 else 7))
            w.wait(BEAT // 2 + BEAT // 4)
            off(w, 0)
            w.wait(BEAT // 4)
            if beat in (1, 3):
                off(w, 1)
                off(w, 2)
    w.body += b"\x66"
    header = bytearray(0x80)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x151)
    struct.pack_into("<I", header, 0x18, w.samples)
    struct.pack_into("<I", header, 0x1C, 0x80 - 0x1C)    # bucle desde el inicio de los datos
    struct.pack_into("<I", header, 0x20, w.samples)
    struct.pack_into("<I", header, 0x34, 0x80 - 0x34)
    struct.pack_into("<I", header, 0x4C, CLOCK)
    struct.pack_into("<I", header, 0x04, len(header) + len(w.body) - 4)
    return bytes(header + w.body)


if __name__ == "__main__":
    out = Path(__file__).with_name("demo.vgm")
    out.write_bytes(build())
    print(f"{out} ({out.stat().st_size} bytes)")
