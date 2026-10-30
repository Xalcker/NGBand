"""Conversión de proyectos de FamiStudio (los de NESBand) a VGM del YM2610 (R15.2, R15.3).

Lee el export de texto de FamiStudio (`famistudio-txt-export`; un `.txt` ya exportado se usa tal cual) y escribe un
VGM que `vgm.py` lee y `songgen.py` importa como cualquier otro:

    pulso 1 -> FM 1 (guitarra)   pulso 2 -> FM 2 (teclado)   triángulo -> FM 3 (bajo)
    ruido y DPCM -> batería en FM 4 (cada golpe es un tono propio y un patch percusivo)

Cada instrumento de FamiStudio recibe un patch FM según su nombre (`patch_for`) y su envolvente de volumen (0-15,
un paso por cuadro) se traduce a atenuación del total level (TL) de los operadores portadores (`attenuation`).
La batería va en FM 4 y no en ADPCM-A porque así el VGM no necesita samples: `drums.py` agrupa sus golpes por tono
(`fm4:C2`, ...). Todo ocurre a 60 cuadros por segundo (735 muestras de 44.1 kHz por cuadro), igual que el juego.

Uso: `python -m ngband_tools.famistudio fuente.txt salida.vgm [--song N]`.
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import re
import struct
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .vgm import SAMPLES_PER_FRAME

YM_CLOCK = 8_000_000
MELODIC = {"Square1": 0, "Square2": 1, "Triangle": 2}  # tipo de canal de FamiStudio -> canal FM (0-based)
DRUM_CHANNEL = 3  # FM 4
DRUM_TYPES = ("Noise", "DPCM")

_ATTR = re.compile(r'(\w+)="([^"]*)"')
_NOTE_NAME = re.compile(r"^([A-G])(#?)(-?\d)$")
_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


# --- Patches FM -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Op:
    """Un operador: detune, multiple, total level, key scale, attack, decay, sustain rate, sustain level, release."""

    mul: int
    tl: int
    ar: int = 31
    dr: int = 0
    sr: int = 0
    sl: int = 0
    rr: int = 7
    dt: int = 0
    ks: int = 0


@dataclass(frozen=True)
class Patch:
    name: str
    alg: int
    fb: int
    ops: tuple[Op, Op, Op, Op]  # operadores 1 a 4

    @property
    def carriers(self) -> tuple[int, ...]:
        """Índices (0-3) de los operadores que suenan, según el algoritmo."""
        return {0: (3,), 1: (3,), 2: (3,), 3: (3,), 4: (1, 3), 5: (1, 2, 3), 6: (1, 2, 3), 7: (0, 1, 2, 3)}[self.alg]


PATCHES: dict[str, Patch] = {p.name: p for p in [
    Patch("guitarra", 4, 5, (Op(1, 30, dr=12, sr=6, sl=5), Op(1, 0, dr=8, sr=4, sl=3),
                             Op(2, 40, dr=14, sr=6, sl=6), Op(2, 6, dr=10, sr=5, sl=4))),
    Patch("lead", 4, 4, (Op(1, 34, sr=0, sl=1), Op(1, 0, sr=0, sl=1), Op(3, 46), Op(2, 10, sl=1))),
    Patch("teclado", 4, 3, (Op(1, 36, dr=10, sr=4, sl=5), Op(1, 0, dr=9, sr=3, sl=4),
                            Op(4, 50, dr=14, sr=6, sl=6), Op(2, 8, dr=11, sr=4, sl=5))),
    Patch("organo", 7, 0, (Op(1, 4), Op(2, 12), Op(4, 20), Op(8, 30))),
    Patch("acordeon", 5, 5, (Op(1, 28, sl=1), Op(1, 6, sl=1), Op(2, 8, sl=1), Op(2, 8, sl=1, dt=3))),
    Patch("pad", 4, 2, (Op(1, 40, ar=18, sl=1, rr=5), Op(1, 6, ar=18, sl=1, rr=5),
                        Op(2, 44, ar=16, sl=1, rr=5), Op(1, 10, ar=16, sl=1, rr=5))),
    Patch("pluck", 4, 4, (Op(1, 24, dr=18, sr=8, sl=8, rr=9), Op(1, 0, dr=16, sr=7, sl=7, rr=9),
                          Op(3, 40, dr=20, sr=9, sl=9, rr=9), Op(1, 8, dr=18, sr=8, sl=8, rr=9))),
    Patch("bajo", 0, 5, (Op(1, 28, dr=10, sr=3, sl=3), Op(1, 36, dr=8, sr=2, sl=2), Op(1, 32, dr=8, sr=2, sl=2),
                         Op(1, 0, dr=6, sr=2, sl=2))),
    Patch("bombo", 0, 6, (Op(1, 22, dr=24, sr=14, sl=10, rr=12), Op(1, 30, dr=22, sr=12, sl=10, rr=12),
                          Op(1, 34, dr=22, sr=12, sl=10, rr=12), Op(1, 0, dr=20, sr=12, sl=10, rr=12))),
    Patch("tarola", 7, 7, (Op(15, 10, dr=22, sr=12, sl=8, rr=10), Op(7, 6, dr=20, sr=12, sl=8, rr=10),
                           Op(5, 8, dr=24, sr=13, sl=8, rr=10), Op(1, 0, dr=20, sr=10, sl=6, rr=10))),
    Patch("platillo", 7, 7, (Op(15, 6, dr=28, sr=16, sl=10, rr=12), Op(13, 8, dr=28, sr=16, sl=10, rr=12),
                             Op(11, 10, dr=28, sr=16, sl=10, rr=12), Op(9, 4, dr=26, sr=16, sl=10, rr=12))),
    Patch("abierto", 7, 7, (Op(15, 6, dr=16, sr=12, sl=6, rr=8), Op(13, 8, dr=16, sr=12, sl=6, rr=8),
                            Op(11, 10, dr=16, sr=12, sl=6, rr=8), Op(9, 4, dr=14, sr=12, sl=6, rr=8))),
]}

# Palabras del nombre del instrumento (sin acentos, en minúsculas) -> patch. Gana la primera que coincide.
PATCH_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("guitarra", "guitar", "riff", "distor"), "guitarra"),
    (("bajo", "bass", "bwomp", "thud"), "bajo"),
    (("piano", "teclado", "keys", "clav"), "teclado"),
    (("organo", "organ"), "organo"),
    (("acordeon", "accordion"), "acordeon"),
    (("coro", "choir", "lamento", "pad", "surf", "cuerda", "string"), "pad"),
    (("pluck", "arpegio", "arp", "clank", "chop"), "pluck"),
    (("trompeta", "trumpet", "flauta", "flute", "melodia", "sintetizador", "synth", "lead", "blip"), "lead"),
]
CHANNEL_DEFAULT = {"Square1": "guitarra", "Square2": "teclado", "Triangle": "bajo"}

# Golpes de batería: palabras del nombre -> tipo. Cada tipo tiene tono, duración máxima, patch y prioridad propios.
DRUM_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("bombo", "kick", "thud", "bwomp"), "bombo"),
    (("tarola", "snare", "clank", "chop"), "tarola"),
    (("abierto", "open"), "abierto"),
    (("platillo", "hat", "cymbal", "crash", "ride"), "platillo"),
]
DRUM_PITCH = {"bombo": 43, "tarola": 50, "platillo": 74, "abierto": 77}  # G2, D3, D5, F5
DRUM_FRAMES = {"bombo": 8, "tarola": 8, "platillo": 3, "abierto": 10}  # duración máxima de la tecla
DRUM_PRIORITY = {"bombo": 0, "tarola": 1, "abierto": 2, "platillo": 3}
KICK_SWEEP = (0, 2, 4)  # semitonos que baja el bombo en los primeros cuadros (lo une drums.channel_strikes)


def _norm(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", name.lower()) if not unicodedata.combining(c))


def patch_for(instrument: str | None, channel_type: str) -> Patch:
    """El patch FM de un instrumento por su nombre; sin coincidencia, el de su canal (guitarra, teclado o bajo)."""
    name = _norm(instrument or "")
    for words, patch in PATCH_KEYWORDS:
        if any(w in name for w in words):
            return PATCHES[patch]
    return PATCHES[CHANNEL_DEFAULT[channel_type]]


def drum_kind(instrument: str | None, sample: str | None, pitch: int) -> str:
    """Tipo de golpe por el nombre del sample (DPCM), del instrumento o, sin pistas, por la altura del ruido."""
    for text in (sample, instrument):
        name = _norm(text or "")
        for words, kind in DRUM_KEYWORDS:
            if any(w in name for w in words):
                return kind
    return "bombo" if pitch <= 48 else "tarola" if pitch <= 53 else "platillo"


def attenuation(volume: int) -> int:
    """Volumen de FamiStudio (0-15) a atenuación en pasos de TL (0,75 dB): 15 -> 0, 0 -> 127 (silencio)."""
    if volume <= 0:
        return 127
    return min(127, round(-20 * math.log10(min(volume, 15) / 15) / 0.75))


# --- Frecuencias ------------------------------------------------------------------------------------------------


def fm_freq(pitch: int, clock: int = YM_CLOCK) -> tuple[int, int]:
    """(bloque, F-number) de una altura MIDI. Inverso de `ym2610.fm_pitch`: se usa el menor bloque que quepa en 11 bits."""
    freq = 440 * 2 ** ((pitch - 69) / 12)
    for block in range(8):
        fnum = round(freq * (1 << (21 - block)) / (clock / 144))
        if fnum < 2048:
            return block, max(1, fnum)
    return 7, 2047


# --- Lectura del texto de FamiStudio ------------------------------------------------------------------------------


@dataclass
class Note:
    frame: int
    pitch: int
    duration: int
    instrument: str | None


@dataclass
class Instrument:
    name: str
    volume: list[int] = field(default_factory=list)  # envolvente de volumen, un valor por cuadro (vacía = 15 fijo)
    dpcm: dict[int, str] = field(default_factory=dict)  # nota MIDI -> nombre del sample

    def volume_at(self, age: int) -> int:
        if not self.volume:
            return 15
        return self.volume[min(age, len(self.volume) - 1)]


@dataclass
class Song:
    name: str
    attrs: dict[str, str]
    pattern_frames: list[int] = field(default_factory=list)
    notes: dict[str, list[Note]] = field(default_factory=dict)

    @property
    def length_frames(self) -> int:
        return sum(self.pattern_frames)

    @property
    def loop_frame(self) -> int:
        """Cuadro donde empieza el bucle (inicio del patrón `LoopPoint`)."""
        point = int(self.attrs.get("LoopPoint", "0"))
        return sum(self.pattern_frames[:point])


@dataclass
class Project:
    attrs: dict[str, str]
    instruments: dict[str, Instrument]
    songs: list[Song]


def note_to_midi(value: str) -> int | None:
    match = _NOTE_NAME.match(value)
    if not match:
        return None  # "Stop", "Release"...
    letter, sharp, octave = match.groups()
    return 12 * (int(octave) + 1) + _PITCH_CLASS[letter] + (1 if sharp else 0)


def parse_text(text: str) -> Project:
    """Lee el archivo de `famistudio-txt-export` (Project > Instrument > Song > Channel > Pattern > Note)."""
    project_attrs: dict[str, str] = {}
    instruments: dict[str, Instrument] = {}
    songs: list[Song] = []
    patterns: dict[str, list[tuple[int, int, int, str | None]]] = {}
    instances: list[tuple[int, str]] = []
    custom: dict[int, dict[str, str]] = {}
    instrument: Instrument | None = None
    channel = pattern = ""

    def finish_channel() -> None:
        if songs and channel:
            song = songs[-1]
            starts = [sum(song.pattern_frames[:i]) for i in range(len(song.pattern_frames))]
            notes = [Note(starts[index] + time, pitch, duration, inst)
                     for index, name in instances if index < len(starts)
                     for time, pitch, duration, inst in patterns.get(name, [])]
            song.notes[channel] = sorted(notes, key=lambda n: n.frame)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        tag = stripped.split(" ", 1)[0]
        attrs = dict(_ATTR.findall(stripped))
        if tag == "Project":
            project_attrs = attrs
            if attrs.get("TempoMode", "FamiStudio") != "FamiStudio":
                raise ValueError("El proyecto usa tempo de FamiTracker. Conviértelo a tempo FamiStudio en FamiStudio.")
        elif tag == "Instrument":
            instrument = instruments[attrs["Name"]] = Instrument(attrs["Name"])
        elif tag == "Envelope" and instrument is not None and attrs.get("Type") == "Volume":
            instrument.volume = [int(v) for v in attrs.get("Values", "").split(",") if v]
        elif tag == "DPCMMapping" and instrument is not None:
            midi = note_to_midi(attrs["Note"])
            if midi is not None:
                instrument.dpcm[midi] = attrs.get("Sample", "")
        elif tag == "Song":
            finish_channel()
            channel, patterns, instances, custom, instrument = "", {}, [], {}, None
            songs.append(Song(attrs.get("Name", f"Song {len(songs)}"), attrs))
        elif tag == "PatternCustomSettings":
            custom[int(attrs["Time"])] = attrs
        elif tag == "Channel":
            finish_channel()
            if songs and not songs[-1].pattern_frames:
                song = songs[-1]
                for index in range(int(song.attrs["Length"])):
                    settings = custom.get(index, song.attrs)
                    length = settings["Length" if index in custom else "PatternLength"]
                    song.pattern_frames.append(int(length) * int(settings["NoteLength"]))
            channel, patterns, instances = attrs["Type"], {}, []
        elif tag == "Pattern":
            pattern = attrs["Name"]
            patterns[pattern] = []
        elif tag == "Note" and "Value" in attrs:
            pitch = note_to_midi(attrs["Value"])
            if pitch is not None:
                patterns[pattern].append((int(attrs["Time"]), pitch, int(attrs.get("Duration", "1")), attrs.get("Instrument")))
        elif tag == "PatternInstance":
            instances.append((int(attrs["Time"]), attrs["Pattern"]))
    finish_channel()
    return Project(project_attrs, instruments, songs)


# --- Línea de tiempo de escrituras -----------------------------------------------------------------------------------


@dataclass
class _Event:
    """Una nota ya resuelta para un canal FM: monofónica, con su patch, tono y volumen por cuadro."""

    start: int
    end: int  # exclusivo
    pitch: int
    patch: Patch
    instrument: Instrument | None
    constant_volume: bool = False  # el triángulo no tiene volumen en el NES
    sweep: tuple[int, ...] = ()  # semitonos que baja la altura en los primeros cuadros (bombo)

    def volume(self, frame: int) -> int:
        if self.constant_volume or self.instrument is None:
            return 15
        return self.instrument.volume_at(frame - self.start)

    def midi(self, frame: int) -> int:
        age = frame - self.start
        return self.pitch - (self.sweep[min(age, len(self.sweep) - 1)] if self.sweep else 0)


def _monophonic(events: list[_Event], limit: int) -> list[_Event]:
    """Corta cada nota donde empieza la siguiente y al final de la canción; descarta lo que cae fuera."""
    events = sorted(events, key=lambda e: e.start)
    out: list[_Event] = []
    for event in events:
        if event.start >= limit:
            continue
        if out and out[-1].start == event.start:
            continue  # dos notas en el mismo cuadro: se queda la primera
        if out:
            out[-1].end = min(out[-1].end, event.start)
        out.append(event)
    for event in out:
        event.end = min(event.end, limit)
    return [e for e in out if e.end > e.start]


def _melodic_events(song: Song, project: Project, channel_type: str, limit: int) -> list[_Event]:
    events = []
    for note in song.notes.get(channel_type, []):
        inst = project.instruments.get(note.instrument or "")
        events.append(_Event(note.frame, note.frame + max(1, note.duration), note.pitch,
                             patch_for(note.instrument, channel_type), inst, channel_type == "Triangle"))
    return _monophonic(events, limit)


def _drum_events(song: Song, project: Project, limit: int) -> list[_Event]:
    """Los golpes de ruido y DPCM juntos, en un solo canal. Con varios en el mismo cuadro gana el de más prioridad."""
    strikes: list[tuple[int, str, Instrument | None]] = []
    for channel_type in DRUM_TYPES:
        for note in song.notes.get(channel_type, []):
            inst = project.instruments.get(note.instrument or "")
            sample = inst.dpcm.get(note.pitch) if inst and channel_type == "DPCM" else None
            strikes.append((note.frame, drum_kind(note.instrument, sample, note.pitch), inst))
    strikes.sort(key=lambda s: (s[0], DRUM_PRIORITY[s[1]]))
    events = []
    for frame, kind, inst in strikes:
        events.append(_Event(frame, frame + DRUM_FRAMES[kind], DRUM_PITCH[kind], PATCHES[kind], inst,
                             sweep=KICK_SWEEP if kind == "bombo" else ()))
    return _monophonic(events, limit)


class _Channel:
    """Lo que el chip tiene cargado en un canal FM, para escribir solo lo que cambia."""

    def __init__(self, index: int) -> None:
        self.port = index // 2
        self.offset = index % 2 + 1  # los canales FM del YM2610 usan los desplazamientos 1 y 2 de cada puerto
        self.keycode = (1, 2, 5, 6)[index]
        self.patch: Patch | None = None
        self.tls: tuple[int, ...] | None = None
        self.freq: tuple[int, int] | None = None
        self.keyed = False

    def forget(self) -> None:
        self.patch = self.tls = self.freq = None


_SLOT = (0, 8, 4, 12)  # desplazamiento de registro de los operadores 1, 2, 3 y 4


def _timeline(song: Song, project: Project) -> tuple[list[list[tuple[int, int, int]]], int]:
    """Las escrituras (puerto, registro, valor) de cada cuadro, y el total de cuadros."""
    total = song.length_frames
    if total <= 0:
        raise ValueError(f"la canción {song.name!r} no tiene cuadros")
    loop = song.loop_frame
    per_channel = {i: _melodic_events(song, project, t, total) for t, i in MELODIC.items()}
    per_channel[DRUM_CHANNEL] = _drum_events(song, project, total)
    channels = {i: _Channel(i) for i in per_channel}
    frames: list[list[tuple[int, int, int]]] = [[] for _ in range(total)]

    def put(frame: int, ch: _Channel, base: int, value: int, slot: int | None = None) -> None:
        reg = base + ch.offset + (_SLOT[slot] if slot is not None else 0)
        frames[frame].append((ch.port, reg, value))

    def key(frame: int, ch: _Channel, on: bool) -> None:
        frames[frame].append((0, 0x28, (0xF0 if on else 0) | ch.keycode))
        ch.keyed = on

    for frame in range(total):
        if frame == 0:
            frames[0].append((0, 0x07, 0xFF))  # SSG callado: la música es solo FM
            for ch in channels.values():
                key(0, ch, False)
                put(0, ch, 0xB4, 0xC0)  # salida a ambos lados, sin LFO
        if frame == loop and frame > 0:
            for ch in channels.values():
                ch.forget()  # al volver al bucle solo se repite desde aquí: lo que cada nota usa se reescribe
        for index, events in per_channel.items():
            ch = channels[index]
            current = next((e for e in events if e.start <= frame < e.end), None)
            if current is None:
                if ch.keyed:
                    key(frame, ch, False)
                continue
            if current.start == frame or (frame == loop and not ch.keyed):
                if ch.keyed:
                    key(frame, ch, False)
                _load_patch(frame, ch, current.patch, put)
                ch.tls = None
            tls = tuple(
                min(127, op.tl + attenuation(current.volume(frame))) if i in current.patch.carriers else op.tl
                for i, op in enumerate(current.patch.ops)
            )
            if tls != ch.tls:
                for slot, value in enumerate(tls):
                    put(frame, ch, 0x40, value, slot)
                ch.tls = tls
            freq = fm_freq(current.midi(frame))
            if freq != ch.freq:
                put(frame, ch, 0xA4, (freq[0] << 3) | (freq[1] >> 8))
                put(frame, ch, 0xA0, freq[1] & 0xFF)
                ch.freq = freq
            if not ch.keyed:
                key(frame, ch, True)
    return frames, total


def _load_patch(frame: int, ch: _Channel, patch: Patch, put) -> None:
    if ch.patch == patch:
        return
    put(frame, ch, 0xB0, (patch.fb << 3) | patch.alg)
    for slot, op in enumerate(patch.ops):
        put(frame, ch, 0x30, (op.dt << 4) | op.mul, slot)
        put(frame, ch, 0x50, (op.ks << 6) | op.ar, slot)
        put(frame, ch, 0x60, op.dr, slot)
        put(frame, ch, 0x70, op.sr, slot)
        put(frame, ch, 0x80, (op.sl << 4) | op.rr, slot)
        put(frame, ch, 0x90, 0, slot)
    ch.patch = patch


# --- Escritura del VGM -------------------------------------------------------------------------------------------


def _gd3(title: str, game: str, author: str) -> bytes:
    fields = [title, "", game, "", "Neo Geo", "", author, "", "", "NGBand famistudio.py", ""]
    text = b"".join(f.encode("utf-16-le") + b"\0\0" for f in fields)
    return b"Gd3 " + struct.pack("<II", 0x100, len(text)) + text


def build_vgm(song: Song, project: Project, *, title: str | None = None, game: str = "NGBand") -> bytes:
    """El VGM (versión 1.51, YM2610 a 8 MHz) de una canción. El bucle empieza en su `LoopPoint`."""
    frames, total = _timeline(song, project)
    loop = song.loop_frame
    body = bytearray()
    loop_pos = None
    for frame, writes in enumerate(frames):
        if frame == loop:
            loop_pos = len(body)
        for port, reg, value in writes:
            body += bytes([0x58 + port, reg, value])
        body.append(0x62)  # 735 muestras = un cuadro
    # Al final se sueltan las teclas para que el bucle no arrastre notas colgadas
    for keycode in (1, 2, 5, 6):
        body += bytes([0x58, 0x28, keycode])
    body.append(0x66)

    header_size = 0x80
    gd3 = _gd3(title or song.name, game, project.attrs.get("Author", ""))
    header = bytearray(header_size)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x04, header_size + len(body) + len(gd3) - 4)
    struct.pack_into("<I", header, 0x08, 0x151)
    struct.pack_into("<I", header, 0x14, header_size + len(body) - 0x14)
    struct.pack_into("<I", header, 0x18, total * SAMPLES_PER_FRAME)
    if loop_pos is not None:
        struct.pack_into("<I", header, 0x1C, header_size + loop_pos - 0x1C)
        struct.pack_into("<I", header, 0x20, (total - loop) * SAMPLES_PER_FRAME)
    struct.pack_into("<I", header, 0x34, header_size - 0x34)
    struct.pack_into("<I", header, 0x4C, YM_CLOCK)
    return bytes(header) + bytes(body) + gd3


def convert_text(text: str, song_index: int = 0, title: str | None = None) -> bytes:
    project = parse_text(text)
    if not 0 <= song_index < len(project.songs):
        raise ValueError(f"el proyecto tiene {len(project.songs)} canciones; pediste la {song_index}")
    return build_vgm(project.songs[song_index], project, title=title)


# --- FamiStudio por línea de comandos (para .fms, .ftm y .nsf) ----------------------------------------------------------


def find_famistudio(root: Path) -> Path:
    """Variable FAMISTUDIO, o la copia en tools/famistudio de este repositorio (o del de NESBand, si está al lado)."""
    env = os.environ.get("FAMISTUDIO")
    if env:
        return Path(env)
    exe = {"Windows": "FamiStudio.exe", "Darwin": "FamiStudio.app"}.get(platform.system(), "FamiStudio")
    for base in (root, root.parent / "NESBand"):
        candidate = base / "tools" / "famistudio" / exe
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No encontré FamiStudio: define la variable FAMISTUDIO o pasa un export de texto (.txt).")


def export_text(source: Path, song_index: int, root: Path) -> str:
    """El export de texto de FamiStudio de un proyecto (.fms, .ftm...)."""
    fs = find_famistudio(root)
    command = [str(fs)]
    if fs.suffix.lower() == ".app":
        command = ["dotnet", str(fs / "Contents" / "MacOS" / "FamiStudio.dll")]
    out = source.with_suffix(".export.tmp.txt")
    env = {**os.environ, "DOTNET_ROLL_FORWARD": os.environ.get("DOTNET_ROLL_FORWARD", "Major")}
    try:
        result = subprocess.run([*command, str(source), "famistudio-txt-export", str(out), f"-export-songs:{song_index}"],
                                capture_output=True, text=True, env=env)
        if result.returncode != 0 or not out.exists():
            raise RuntimeError(f"FamiStudio falló:\n{result.stdout}{result.stderr}")
        return out.read_text(encoding="utf-8")
    finally:
        out.unlink(missing_ok=True)


def convert_file(source: Path, output: Path, song_index: int = 0, root: Path | None = None, title: str | None = None) -> Path:
    """Convierte un proyecto de FamiStudio a VGM. Un `.txt` se lee directo; lo demás pasa por FamiStudio."""
    root = root or Path(__file__).resolve().parents[2]
    if source.suffix.lower() == ".txt":
        text, index = source.read_text(encoding="utf-8"), song_index
    else:
        text, index = export_text(source, song_index, root), 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(convert_text(text, index, title))
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convierte un proyecto de FamiStudio a VGM del YM2610")
    parser.add_argument("source", type=Path, help="export de texto (.txt), .fms o .ftm")
    parser.add_argument("output", type=Path, help="VGM de salida")
    parser.add_argument("--song", type=int, default=0, help="índice de la canción dentro del proyecto (0 es la primera)")
    parser.add_argument("--title", help="título (por omisión, el nombre de la canción)")
    args = parser.parse_args(argv)
    try:
        print(f"escribí {convert_file(args.source, args.output, args.song, title=args.title)}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
