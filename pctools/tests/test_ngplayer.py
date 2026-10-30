"""Escuchar (R16.6): el emulador del YM2610 en JavaScript (ngplayer.js) toca el mismo Frame_Stream que la ROM.

Se prueba con Node (si no está instalado, se omiten): se arma un Frame_Stream con frames.py, se renderiza y se mide
qué canales suenan y a qué frecuencia."""

import base64
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngband_tools import adpcma  # noqa: E402
from ngband_tools.frames import RegWrite, build_frames, encode_stream  # noqa: E402
from ngband_tools.ym2610 import fm_pitch, ssg_pitch  # noqa: E402

PLAYER = Path(__file__).resolve().parents[1] / "ngband_tools" / "ngplayer.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js no está instalado")

CLOCK = 8_000_000
IDS = ["fm1", "fm2", "fm3", "fm4", "ssg1", "ssg2", "ssg3", "adpcma", "adpcmb"]

# Mide un stem: energía y frecuencia (cruces ascendentes por cero con histéresis) desde 0.3 s hasta el final
SCRIPT = f"""
const P = require({json.dumps(str(PLAYER))});
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", async () => {{
  const req = JSON.parse(input);
  const b = (s) => Uint8Array.from(Buffer.from(s, "base64"));
  const r = await P.render(b(req.stream), req.frames, {{ sampleRate: 44100, clock: req.clock,
    adpcmaRom: b(req.adpcma), adpcmbRom: b(req.adpcmb) }});
  const out = r.stems.map((s) => {{
    if (!s) return null;
    const from = Math.floor(0.3 * r.sampleRate);
    let peak = 0, sq = 0;
    for (let i = from; i < s.length; i++) {{ peak = Math.max(peak, Math.abs(s[i])); sq += s[i] * s[i]; }}
    let up = 0, armed = false;
    for (let i = from; i < s.length; i++) {{
      if (s[i] < -peak * 0.2) armed = true;
      else if (armed && s[i] > peak * 0.2) {{ up++; armed = false; }}
    }}
    return {{ peak, rms: Math.sqrt(sq / (s.length - from)), freq: up / ((s.length - from) / r.sampleRate) }};
  }});
  process.stdout.write(JSON.stringify({{ stems: out, mixPeak: Math.max(...r.audio.map(Math.abs)), len: r.audio.length }}));
}});
"""


def render(writes_by_frame, frames, adpcma_rom=b"", adpcmb_rom=b""):
    """writes_by_frame: {cuadro: [(puerto, reg, valor)]} -> resultado de medir cada canal."""
    items = [(f, RegWrite(p, r, v)) for f, ws in writes_by_frame.items() for p, r, v in ws]
    stream = encode_stream(build_frames(items, frames))
    req = {"stream": base64.b64encode(stream).decode(), "frames": frames, "clock": CLOCK,
           "adpcma": base64.b64encode(adpcma_rom).decode(), "adpcmb": base64.b64encode(adpcmb_rom).decode()}
    done = subprocess.run([NODE, "-e", SCRIPT], input=json.dumps(req), capture_output=True, text=True, timeout=110)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    return {name: stem for name, stem in zip(IDS, result["stems"])}, result


def fm_setup(port, offset, fnum, block):
    """Un tono FM puro (algoritmo 7, solo el operador 1 audible) en el canal con ese puerto y desplazamiento."""
    ws = []
    for slot, tl in enumerate((0, 127, 127, 127)):  # el orden de los registros es op1, op3, op2, op4
        base = offset + 4 * slot
        ws += [(port, 0x30 + base, 0x01), (port, 0x40 + base, tl), (port, 0x50 + base, 0x1F),
               (port, 0x60 + base, 0x00), (port, 0x70 + base, 0x00), (port, 0x80 + base, 0x0F)]
    ws += [(port, 0xB0 + offset, 0x07), (port, 0xB4 + offset, 0xC0),
           (port, 0xA4 + offset, (block << 3) | (fnum >> 8)), (port, 0xA0 + offset, fnum & 0xFF)]
    return ws


@pytest.mark.parametrize("name,port,offset,keycode", [("fm1", 0, 1, 1), ("fm2", 0, 2, 2), ("fm3", 1, 1, 5), ("fm4", 1, 2, 6)])
def test_each_fm_channel_sounds_alone_at_its_pitch(name, port, offset, keycode):
    fnum, block = 672, 4
    stems, result = render({0: fm_setup(port, offset, fnum, block) + [(0, 0x28, 0xF0 | keycode)]}, 90)
    assert [n for n, s in stems.items() if s] == [name]
    expected = 440 * 2 ** ((fm_pitch(block, fnum, CLOCK) - 69) / 12)
    assert stems[name]["freq"] == pytest.approx(expected, rel=0.03)
    assert result["mixPeak"] > 0.01
    assert result["len"] == 90 * 735


def test_fm_key_off_silences_the_channel():
    on = {0: fm_setup(0, 1, 672, 4) + [(0, 0x28, 0xF1)]}
    off = {**on, 6: [(0, 0x28, 0x01)]}  # antes de que empiece a medirse (0.3 s)
    released = render(off, 90)[0]["fm1"]
    assert render(on, 90)[0]["fm1"]["rms"] > 0 and (released is None or released["rms"] < 50)


def test_ssg_tone_pitch_and_mixer():
    period = 256
    ws = [(0, 0, period & 0xFF), (0, 1, period >> 8), (0, 7, 0x3E), (0, 8, 0x0F)]  # solo el tono A
    stems, _ = render({0: ws}, 90)
    assert [n for n, s in stems.items() if s] == ["ssg1"]
    expected = 440 * 2 ** ((ssg_pitch(period, CLOCK) - 69) / 12)
    assert stems["ssg1"]["freq"] == pytest.approx(expected, rel=0.03)


def test_ssg_noise_and_envelope_sound():
    noise = [(0, 6, 8), (0, 7, 0x37), (0, 10, 0x0F)]  # ruido en el canal C
    assert render({0: noise}, 60)[0]["ssg3"]["rms"] > 0
    env = [(0, 0, 0x80), (0, 1, 0), (0, 7, 0x3E), (0, 8, 0x10), (0, 11, 0x40), (0, 12, 0x00), (0, 13, 0x0E)]
    assert render({0: env}, 60)[0]["ssg1"]["rms"] > 0


def sine_pcm(freq, rate, seconds):
    return [int(12000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(int(rate * seconds))]


def test_adpcma_plays_rom_samples_at_their_pitch():
    rate = CLOCK / 432  # 18518.5 Hz, la frecuencia de ADPCM-A
    rom = adpcma.encode(sine_pcm(1000, rate, 2))
    blocks = len(rom) // 256
    ws = [(1, 0x01, 0x3F), (1, 0x08, 0xDF), (1, 0x10, 0), (1, 0x18, 0), (1, 0x20, (blocks - 1) & 0xFF),
          (1, 0x28, (blocks - 1) >> 8), (1, 0x00, 0x01)]
    stems, _ = render({0: ws}, 80, adpcma_rom=rom)
    assert [n for n, s in stems.items() if s] == ["adpcma"]
    assert stems["adpcma"]["freq"] == pytest.approx(1000, rel=0.05)
    assert render({0: ws}, 80)[0]["adpcma"] is None  # sin datos de samples no suena


def test_adpcma_dump_stops_the_channel():
    rate = CLOCK / 432
    rom = adpcma.encode(sine_pcm(1000, rate, 2))
    blocks = len(rom) // 256
    start = [(1, 0x01, 0x3F), (1, 0x08, 0xDF), (1, 0x10, 0), (1, 0x18, 0), (1, 0x20, blocks - 1), (1, 0x28, 0), (1, 0x00, 0x01)]
    assert render({0: start, 15: [(1, 0x00, 0x81)]}, 80, adpcma_rom=rom)[0]["adpcma"]["rms"] < \
        0.5 * render({0: start}, 80, adpcma_rom=rom)[0]["adpcma"]["rms"]


def encode_adpcmb(pcm):
    """Codificador ADPCM-B mínimo (el mismo algoritmo que decodifica ngplayer.js), para la prueba."""
    accum, delta, nibbles = 0, 127, []
    for target in pcm:
        best = min(range(16), key=lambda n: abs(
            max(-32768, min(32767, accum + (-1 if n & 8 else 1) * (((2 * (n & 7) + 1) * delta) >> 3))) - target))
        step = ((2 * (best & 7) + 1) * delta) >> 3
        accum = max(-32768, min(32767, accum - step if best & 8 else accum + step))
        delta = max(127, min(24576, (delta * (57, 57, 57, 57, 77, 102, 128, 153)[best & 7]) >> 6))
        nibbles.append(best)
    nibbles += [0] * (-len(nibbles) % 512)
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def test_adpcmb_plays_rom_samples_at_delta_n_rate():
    rate = 8000
    rom = encode_adpcmb(sine_pcm(400, rate, 2))
    blocks = len(rom) // 256
    delta_n = round(rate / (CLOCK / 144) * 65536)
    ws = [(0, 0x11, 0xC0), (0, 0x12, 0), (0, 0x13, 0), (0, 0x14, (blocks - 1) & 0xFF), (0, 0x15, (blocks - 1) >> 8),
          (0, 0x19, delta_n & 0xFF), (0, 0x1A, delta_n >> 8), (0, 0x1B, 0xFF), (0, 0x10, 0x80)]
    stems, _ = render({0: ws}, 80, adpcmb_rom=rom)
    assert [n for n, s in stems.items() if s] == ["adpcmb"]
    assert stems["adpcmb"]["freq"] == pytest.approx(400, rel=0.05)


def test_empty_stream_is_silent():
    stems, result = render({}, 30)
    assert all(s is None for s in stems.values()) and result["mixPeak"] == 0
