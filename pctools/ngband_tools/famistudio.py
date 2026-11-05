"""Conversión de proyectos de FamiStudio (los de NESBand) a VGM del YM2610 (R15.2, R15.3).

Lee el export de texto de FamiStudio (`famistudio-txt-export`; un `.txt` ya exportado se usa tal cual) y escribe un
VGM que `vgm.py` lee y `songgen.py` importa como cualquier otro:

    pulso 1 -> FM 1 (guitarra)   pulso 2 -> FM 2 (teclado)   triángulo -> FM 3 (bajo)
    ruido y DPCM -> batería: el bombo al FM 4 y la tarola y los platillos al ruido del SSG 1

Es el mismo arreglo de GENBand (audio/nesband_fm.py): cada instrumento toma un sonido FM de GENBand por su nombre
(`patch_for`) y su volumen (el máximo de su envolvente del NES) se traduce una sola vez a atenuación de los
portadores (`volume_extra`); la caída la hace el FM. La batería no usa ADPCM-A para que el VGM no necesite samples:
`drums.py` agrupa sus golpes por tono (`fm4:G3` el bombo; `ssg1:D3`, `ssg1:D5`, `ssg1:F5` los de ruido). Todo
ocurre a 60 cuadros por segundo (735 muestras de 44.1 kHz por cuadro), igual que el juego.

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


# --- Sonidos FM ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Op:
    """Un operador: multiple, total level, attack, decay (D1R), sustain rate (D2R), sustain level (D1L), release,
    detune y key scale."""

    mul: int
    tl: int
    ar: int = 31
    dr: int = 0
    sr: int = 0
    sl: int = 0
    rr: int = 15
    dt: int = 0
    ks: int = 0


@dataclass(frozen=True)
class Patch:
    name: str
    alg: int
    fb: int
    ops: tuple[Op, Op, Op, Op]  # operadores 1 a 4
    sweep: tuple[int, ...] = ()  # semitonos que se suman a la nota en cada cuadro (el bombo)

    @property
    def carriers(self) -> tuple[int, ...]:
        """Índices (0-3) de los operadores que suenan, según el algoritmo."""
        return {0: (3,), 1: (3,), 2: (3,), 3: (3,), 4: (1, 3), 5: (1, 2, 3), 6: (1, 2, 3), 7: (0, 1, 2, 3)}[self.alg]


def _op(mul: int = 1, dt: int = 0, tl: int = 0, ar: int = 31, d1r: int = 0, d2r: int = 0, d1l: int = 0,
        rr: int = 15, rs: int = 0) -> Op:
    """Un operador con los nombres de GENBand (audio/sonidos.py)."""
    return Op(mul, tl, ar, d1r, d2r, d1l, rr, dt, rs)


# Los sonidos de GENBand (audio/sonidos.py, GPL-2.0-or-later como este proyecto). El YM2610 y el YM2612 son de la
# misma familia (OPN): los operadores tienen los mismos registros, así que los parches se copian tal cual.
PATCHES: dict[str, Patch] = {p.name: p for p in [
    # Guitarra: dos pares (algoritmo 4) con el modulador saturado y los portadores desafinados al revés
    Patch("guitarra", 4, 6, (_op(mul=1, tl=24, d1r=6, d2r=2, d1l=3, rr=7), _op(mul=1, dt=3, tl=8, d1r=4, d2r=2, d1l=2, rr=7),
                             _op(mul=2, tl=30, d1r=8, d2r=3, d1l=4, rr=7), _op(mul=1, dt=7, tl=10, d1r=3, d2r=2, d1l=2, rr=7))),
    # La guitarra apagada con la palma: cae rápido
    Patch("apagada", 4, 6, (_op(mul=1, tl=22, d1r=10, d2r=6, d1l=5, rr=9), _op(mul=1, dt=3, tl=10, d1r=9, d2r=6, d1l=4, rr=9),
                            _op(mul=2, tl=28, d1r=10, d2r=6, d1l=5, rr=9), _op(mul=1, dt=7, tl=12, d1r=9, d2r=6, d1l=4, rr=9))),
    # Guitarra limpia y brillante (surf)
    Patch("limpia", 4, 3, (_op(mul=1, tl=32, d1r=8, d2r=3, d1l=4, rr=7), _op(mul=1, dt=2, tl=8, d1r=5, d2r=3, d1l=3, rr=7),
                           _op(mul=3, tl=40, d1r=10, d2r=4, d1l=5, rr=7), _op(mul=1, dt=6, tl=10, d1r=5, d2r=3, d1l=3, rr=7))),
    # Sierra (sintetizador): los cuatro operadores suenan
    Patch("sierra", 7, 7, (_op(mul=1, tl=22, rr=6), _op(mul=1, dt=3, tl=30, rr=6), _op(mul=2, tl=38, rr=6),
                           _op(mul=1, dt=7, tl=30, rr=6))),
    # Metal (trompeta): ataque un poco lento
    Patch("metal", 4, 5, (_op(mul=1, tl=26, ar=22, d1r=4, d1l=2, rr=7), _op(mul=1, dt=2, tl=8, ar=24, d1r=2, d1l=1, rr=7),
                          _op(mul=1, tl=34, ar=20, d1r=4, d1l=2, rr=7), _op(mul=1, dt=6, tl=12, ar=24, d1r=2, d1l=1, rr=7))),
    # Flauta: casi un seno, ataque suave
    Patch("flauta", 4, 0, (_op(mul=1, tl=44, ar=18, rr=6), _op(mul=1, tl=8, ar=18, rr=6), _op(mul=2, tl=60, ar=18, rr=6),
                           _op(mul=1, dt=3, tl=14, ar=18, rr=6))),
    # Acordeón: moduladores una octava arriba, portadores desafinados
    Patch("acordeon", 4, 4, (_op(mul=2, tl=32, ar=26, rr=6), _op(mul=1, dt=2, tl=10, ar=26, rr=6),
                             _op(mul=2, tl=34, ar=26, rr=6), _op(mul=1, dt=6, tl=12, ar=26, rr=6))),
    # Órgano: los 4 operadores suenan, cada uno en un armónico
    Patch("organo", 7, 3, (_op(mul=1, tl=26, rr=7), _op(mul=2, tl=34, rr=7), _op(mul=4, tl=42, rr=7),
                           _op(mul=1, dt=3, tl=30, rr=7))),
    # Piano eléctrico: cuerpo y una lengüeta metálica que se apaga rápido
    Patch("piano", 4, 2, (_op(mul=1, tl=34, d1r=8, d2r=3, d1l=5, rr=6), _op(mul=1, tl=8, d1r=5, d2r=3, d1l=4, rr=6),
                          _op(mul=14, tl=52, d1r=14, d2r=8, d1l=8, rr=8), _op(mul=1, dt=3, tl=12, d1r=5, d2r=3, d1l=5, rr=6))),
    # Cuerda pulsada corta (arpegios)
    Patch("pulsada", 4, 3, (_op(mul=1, tl=30, d1r=12, d2r=8, d1l=6, rr=9), _op(mul=1, tl=8, d1r=9, d2r=7, d1l=5, rr=9),
                            _op(mul=3, tl=42, d1r=14, d2r=9, d1l=7, rr=9), _op(mul=1, dt=3, tl=12, d1r=9, d2r=7, d1l=5, rr=9))),
    # Coro: ataque lento, un modulador suave sobre tres portadores
    Patch("coro", 5, 2, (_op(mul=1, tl=36, ar=20, rr=5), _op(mul=1, dt=2, tl=24, ar=14, rr=5), _op(mul=2, tl=32, ar=14, rr=5),
                         _op(mul=1, dt=6, tl=24, ar=14, rr=5))),
    # Bajo: cadena de operadores (algoritmo 0) con ataque seco
    Patch("bajo", 0, 4, (_op(mul=0, tl=30, d1r=10, d1l=6, rr=8), _op(mul=1, tl=40, d1r=12, d1l=6, rr=8),
                         _op(mul=1, tl=32, d1r=8, d1l=4, rr=8), _op(mul=1, tl=4, d1r=5, d2r=4, d1l=2, rr=9))),
    # Bombo: un seno (solo suena el operador 4) que baja de tono en 6 cuadros
    Patch("bombo", 7, 0, (_op(tl=127), _op(tl=127), _op(tl=127), _op(mul=1, tl=0, d1r=13, d2r=10, d1l=3, rr=12)),
          sweep=(19, 12, 7, 3, 1, 0)),
]}

# Instrumentos de las canciones de NESBand -> sonido (como SONIDOS en GENBand/audio/nesband_fm.py)
INSTRUMENT_PATCH = {
    "Guitarra": "guitarra", "Melodia": "guitarra", "Surf": "limpia", "Chop": "apagada", "Sintetizador": "sierra",
    "Trompeta": "metal", "Flauta": "flauta", "Lamento": "flauta", "Acordeon": "acordeon", "Piano": "piano",
    "Organo": "organo", "Teclado": "organo", "Coro": "coro", "Pluck": "pulsada", "Arpegio": "pulsada", "Bajo": "bajo",
}
# Sin nombre exacto: palabras del nombre (sin acentos, en minúsculas) -> sonido. Gana la primera que coincide.
PATCH_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("apagad", "chop", "palm", "mute"), "apagada"),
    (("surf", "limpia", "clean"), "limpia"),
    (("guitarra", "guitar", "riff", "distor", "melodia"), "guitarra"),
    (("bajo", "bass"), "bajo"),
    (("piano", "keys", "clav"), "piano"),
    (("organo", "organ", "teclado"), "organo"),
    (("acordeon", "accordion"), "acordeon"),
    (("coro", "choir", "pad", "cuerda", "string"), "coro"),
    (("flauta", "flute", "lamento"), "flauta"),
    (("trompeta", "trumpet", "metal", "brass"), "metal"),
    (("pluck", "arpegio", "arp", "pulsada"), "pulsada"),
    (("sintetizador", "synth", "lead", "sierra", "saw"), "sierra"),
]
CHANNEL_DEFAULT = {"Square1": "guitarra", "Square2": "organo", "Triangle": "bajo"}

# Volumen: como GENBand, fijo por instrumento (el máximo de su envolvente del NES); el FM hace su propia caída.
VOLUME_REFERENCE = 13  # el volumen del NES (0-15) que suena sin atenuar
TL_PER_STEP = 1.5  # atenuación (en pasos de TL, 0,75 dB) por cada paso de volumen del NES debajo de la referencia
CHANNEL_MIX = {1: 2}  # atenuación extra por canal FM (0-based): el teclado un poco abajo, como en GENBand

# Batería: el bombo al FM 4 (sonido "bombo" sobre C2); la tarola y los platillos al ruido del SSG 1 (el SSG 3 es
# de los efectos). Cada golpe de ruido pone en el SSG 1 un periodo de tono propio (con el tono apagado) para que
# `drums.py` agrupe los golpes por altura: "ssg1:D3" la tarola, "ssg1:D5" el platillo y "ssg1:F5" el abierto.
DRUM_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("bombo", "kick", "thud", "bwomp"), "bombo"),
    (("tarola", "snare", "clank", "chop"), "tarola"),
    (("abierto", "open"), "abierto"),
    (("platillo", "hat", "cymbal", "crash", "ride"), "platillo"),
]
KICK_PITCH = 36  # C2 (con el barrido arranca en G3: el grupo es "fm4:G3")
KICK_ROWS = 2  # filas que suena el bombo (como GENBand)
DRUM_PITCH = {"bombo": KICK_PITCH + PATCHES["bombo"].sweep[0], "tarola": 50, "platillo": 74, "abierto": 77}
DRUM_PRIORITY = {"bombo": 0, "tarola": 1, "abierto": 2, "platillo": 3}
SSG_DRUM_CHANNEL = 0  # SSG 1
# Envolventes de GENBand (volumen del PSG por cuadro, 15 = lo más fuerte) y periodo del ruido del SSG. GENBand usa
# ruido blanco a N/1024 en la tarola y N/512 en los platillos: el periodo de la tarola es el doble.
NOISE_ENVELOPE = {
    "tarola": (15, 14, 12, 10, 8, 7, 6, 5, 4, 3, 2, 1, 0),
    "platillo": (10, 7, 4, 2, 0),
    "abierto": (11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
}
NOISE_PERIOD = {"tarola": 18, "platillo": 9, "abierto": 9}
SSG_MIXER = 0x37  # tonos apagados; ruido solo en el SSG 1


def _norm(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", name.lower()) if not unicodedata.combining(c))


def patch_for(instrument: str | None, channel_type: str) -> Patch:
    """El sonido FM de un instrumento por su nombre; sin coincidencia, el de su canal (guitarra, órgano o bajo)."""
    if instrument in INSTRUMENT_PATCH:
        return PATCHES[INSTRUMENT_PATCH[instrument]]
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


def volume_extra(volume: int) -> int:
    """Atenuación de los portadores (pasos de TL) para un instrumento cuyo volumen máximo en el NES es `volume`."""
    return max(0, round((VOLUME_REFERENCE - volume) * TL_PER_STEP))


def ssg_volume(psg: int) -> int:
    """Volumen del PSG de la Genesis (0-15, pasos de 2 dB) al del SSG (0-15, pasos de ~3 dB)."""
    if psg <= 0:
        return 0
    return max(1, 15 - round((15 - min(psg, 15)) * 2 / 3))


def ssg_period(pitch: int) -> int:
    """Periodo de tono del SSG (12 bits) para una altura MIDI: solo sirve para agrupar los golpes."""
    return max(1, min(4095, round(YM_CLOCK / 4 / 16 / (440 * 2 ** ((pitch - 69) / 12)))))


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
    """Una nota ya resuelta para un canal FM: monofónica, con su sonido y la atenuación de sus portadores."""

    start: int
    end: int  # exclusivo
    pitch: int
    patch: Patch
    extra: int = 0  # pasos de TL que se suman a los portadores (volumen del instrumento y mezcla del canal)

    def midi(self, frame: int) -> int:
        sweep = self.patch.sweep
        return self.pitch + (sweep[min(frame - self.start, len(sweep) - 1)] if sweep else 0)


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


def _max_volume(inst: Instrument | None) -> int:
    return max(inst.volume) if inst and inst.volume else 15


def _melodic_events(song: Song, project: Project, channel_type: str, limit: int) -> list[_Event]:
    events = []
    mix = CHANNEL_MIX.get(MELODIC[channel_type], 0)
    for note in song.notes.get(channel_type, []):
        inst = project.instruments.get(note.instrument or "")
        volume = 15 if channel_type == "Triangle" else _max_volume(inst)  # el triángulo no tiene volumen en el NES
        events.append(_Event(note.frame, note.frame + max(1, note.duration), note.pitch,
                             patch_for(note.instrument, channel_type), volume_extra(volume) + mix))
    return _monophonic(events, limit)


def _drum_strikes(song: Song, project: Project, limit: int) -> tuple[list[_Event], list[tuple[int, str]]]:
    """Los golpes de ruido y DPCM: los bombos (eventos del FM 4) y los golpes de ruido [(cuadro, tipo)], uno por
    cuadro (si coinciden, gana el de más prioridad: tarola, abierto, platillo)."""
    row = int(song.attrs.get("NoteLength", "6"))
    kicks: list[_Event] = []
    noise: dict[int, str] = {}
    for channel_type in DRUM_TYPES:
        for note in song.notes.get(channel_type, []):
            if note.frame >= limit:
                continue
            inst = project.instruments.get(note.instrument or "")
            sample = inst.dpcm.get(note.pitch) if inst and channel_type == "DPCM" else None
            kind = drum_kind(note.instrument, sample, note.pitch)
            if kind == "bombo":
                kicks.append(_Event(note.frame, note.frame + KICK_ROWS * row, KICK_PITCH, PATCHES["bombo"]))
            elif note.frame not in noise or DRUM_PRIORITY[kind] < DRUM_PRIORITY[noise[note.frame]]:
                noise[note.frame] = kind
    return _monophonic(kicks, limit), sorted(noise.items())


class _Channel:
    """Lo que el chip tiene cargado en un canal FM, para escribir solo lo que cambia."""

    def __init__(self, index: int) -> None:
        self.port = index // 2
        self.offset = index % 2 + 1  # los canales FM del YM2610 usan los desplazamientos 1 y 2 de cada puerto
        self.keycode = (1, 2, 5, 6)[index]
        self.loaded: tuple[Patch, int] | None = None
        self.freq: tuple[int, int] | None = None
        self.keyed = False

    def forget(self) -> None:
        self.loaded = self.freq = None


_SLOT = (0, 8, 4, 12)  # desplazamiento de registro de los operadores 1, 2, 3 y 4


def _timeline(song: Song, project: Project) -> tuple[list[list[tuple[int, int, int]]], int]:
    """Las escrituras (puerto, registro, valor) de cada cuadro, y el total de cuadros."""
    total = song.length_frames
    if total <= 0:
        raise ValueError(f"la canción {song.name!r} no tiene cuadros")
    loop = song.loop_frame
    per_channel = {i: _melodic_events(song, project, t, total) for t, i in MELODIC.items()}
    per_channel[DRUM_CHANNEL], noise = _drum_strikes(song, project, total)
    channels = {i: _Channel(i) for i in per_channel}
    frames: list[list[tuple[int, int, int]]] = [[] for _ in range(total)]

    def put(frame: int, ch: _Channel, base: int, value: int, slot: int | None = None) -> None:
        reg = base + ch.offset + (_SLOT[slot] if slot is not None else 0)
        frames[frame].append((ch.port, reg, value))

    def key(frame: int, ch: _Channel, on: bool) -> None:
        frames[frame].append((0, 0x28, (0xF0 if on else 0) | ch.keycode))
        ch.keyed = on

    frames[0].append((0, 0x07, SSG_MIXER))
    for reg in (0x08, 0x09, 0x0A):
        frames[0].append((0, reg, 0))
    for frame in range(total):
        if frame == 0:
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
                _load_patch(frame, ch, current.patch, current.extra, put)
            freq = fm_freq(current.midi(frame))
            if freq != ch.freq:
                put(frame, ch, 0xA4, (freq[0] << 3) | (freq[1] >> 8))
                put(frame, ch, 0xA0, freq[1] & 0xFF)
                ch.freq = freq
            if not ch.keyed:
                key(frame, ch, True)
    _noise_writes(frames, noise, total, loop, int(song.attrs.get("NoteLength", "6")))
    return frames, total


def _noise_writes(frames: list[list[tuple[int, int, int]]], noise: list[tuple[int, str]], total: int, loop: int,
                  row: int) -> None:
    """Los golpes de ruido en el SSG 1: cada uno con su envolvente hasta el siguiente golpe."""
    vol_reg, tone_reg = 0x08 + SSG_DRUM_CHANNEL, 2 * SSG_DRUM_CHANNEL
    volume = 0
    period = noise_period = None
    for i, (frame, kind) in enumerate(noise):
        if frame == loop or (i and noise[i - 1][0] < loop <= frame):
            period = noise_period = None  # el bucle vuelve aquí: se reescribe todo
            volume = -1
        until = min(noise[i + 1][0] if i + 1 < len(noise) else frame + 4 * row, total)
        if volume:
            frames[frame].append((0, vol_reg, 0))  # corta el golpe anterior: el siguiente es otro golpe
            volume = 0
        tone = ssg_period(DRUM_PITCH[kind])
        if tone != period:
            frames[frame].append((0, tone_reg, tone & 0xFF))
            frames[frame].append((0, tone_reg + 1, tone >> 8))
            period = tone
        if NOISE_PERIOD[kind] != noise_period:
            frames[frame].append((0, 0x06, NOISE_PERIOD[kind]))
            noise_period = NOISE_PERIOD[kind]
        envelope = NOISE_ENVELOPE[kind]
        for k in range(until - frame):
            v = ssg_volume(envelope[min(k, len(envelope) - 1)])
            if v != volume:
                frames[frame + k].append((0, vol_reg, v))
                volume = v
            if k >= len(envelope):
                break


def _load_patch(frame: int, ch: _Channel, patch: Patch, extra: int, put) -> None:
    if ch.loaded == (patch, extra):
        return
    put(frame, ch, 0xB0, (patch.fb << 3) | patch.alg)
    for slot, op in enumerate(patch.ops):
        put(frame, ch, 0x30, (op.dt << 4) | op.mul, slot)
        put(frame, ch, 0x40, min(127, op.tl + extra) if slot in patch.carriers else op.tl, slot)
        put(frame, ch, 0x50, (op.ks << 6) | op.ar, slot)
        put(frame, ch, 0x60, op.dr, slot)
        put(frame, ch, 0x70, op.sr, slot)
        put(frame, ch, 0x80, (op.sl << 4) | op.rr, slot)
        put(frame, ch, 0x90, 0, slot)
    ch.loaded = (patch, extra)


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
    body += bytes([0x58, 0x08 + SSG_DRUM_CHANNEL, 0])
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
