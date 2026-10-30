"""Resumen de un WAV de MAME (-wavwrite): nivel RMS por segundo, para ver si hay audio y dónde se calla."""
import array
import math
import sys
import wave

with wave.open(sys.argv[1], "rb") as w:
    rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
    if width != 2:
        sys.exit(f"WAV de {width * 8} bits: se esperaban 16")
    data = array.array("h", w.readframes(w.getnframes()))
if sys.byteorder == "big":
    data.byteswap()
step = rate * ch
levels = []
for k in range(0, len(data), step):
    chunk = data[k:k + step]
    levels.append(math.sqrt(sum(x * x for x in chunk) / max(1, len(chunk))))
print("RMS por segundo:", " ".join(f"{v:.0f}" for v in levels))
silent = sum(1 for v in levels if v < 50)
print(f"{len(levels)} s de audio, {silent} s en silencio (RMS < 50), pico {max(abs(x) for x in data) if data else 0}")
