"""Extracción de notas por canal (R14.6).

FM: una nota por key-on. Con la tecla presionada, un cambio de altura de más de 3/4 de semitono respecto
a la altura de la nota actual cierra esa nota y abre otra (vibrato y portamento pequeños no cortan la nota).
Un cambio de frecuencia en el mismo cuadro del key-on se toma como la altura inicial de la nota (hay drivers
que escriben la frecuencia después del key-on).
SSG: igual, pero la nota dura mientras el canal suena (volumen > 0 y tono o ruido activos).

Los canales se llaman `fm1`..`fm4` y `ssg1`..`ssg3`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .vgm import Vgm, Write, unrolled_writes
from .ym2610 import FM_CHANNELS, SSG_CHANNELS, Ym2610State

SPLIT_SEMITONES = 0.75  # un cambio mayor que esto con la tecla presionada es otra nota


@dataclass(frozen=True)
class Note:
    channel: str  # "fm1".."fm4", "ssg1".."ssg3"
    start: int  # cuadro de inicio
    end: int  # cuadro en que se suelta (exclusivo)
    pitch: float  # altura MIDI con decimales, la del F-number (o periodo) al inicio de la nota

    @property
    def midi(self) -> int:
        return round(self.pitch)


class _Open:
    """Nota en curso de un canal."""

    __slots__ = ("start", "pitch")

    def __init__(self, start: int, pitch: float | None) -> None:
        self.start = start
        self.pitch = pitch


def _track(
    name: str,
    notes: list[Note],
    cur: dict[str, _Open | None],
    frame: int,
    active: bool,
    pitch: float | None,
    retrigger: bool,
) -> None:
    """Actualiza la nota en curso de `name` tras un evento. `retrigger` = hubo un key-on nuevo."""
    open_note = cur[name]
    if open_note is not None and (not active or retrigger):
        _close(name, notes, cur, frame)
        open_note = None
    if not active:
        return
    if open_note is None:
        cur[name] = _Open(frame, pitch)
        return
    if pitch is None:
        return
    if open_note.pitch is None or (open_note.start == frame and not retrigger):
        # Altura aún sin definir, o corrección en el mismo cuadro del key-on
        open_note.pitch = pitch
    elif abs(pitch - open_note.pitch) > SPLIT_SEMITONES:
        _close(name, notes, cur, frame)
        cur[name] = _Open(frame, pitch)


def _close(name: str, notes: list[Note], cur: dict[str, _Open | None], frame: int) -> None:
    n = cur[name]
    cur[name] = None
    if n is not None and n.pitch is not None and frame > n.start:
        notes.append(Note(name, n.start, frame, n.pitch))


def extract_notes_from_writes(
    writes: list[tuple[int, Write]], clock: int, end_frame: int | None = None
) -> list[Note]:
    """Notas FM y SSG de una lista de (cuadro, escritura) en orden. Ordenadas por inicio y canal."""
    state = Ym2610State(clock)
    names = [f"fm{i + 1}" for i in range(FM_CHANNELS)] + [f"ssg{i + 1}" for i in range(SSG_CHANNELS)]
    cur: dict[str, _Open | None] = {n: None for n in names}
    notes: list[Note] = []
    last = 0
    for frame, w in writes:
        last = max(last, frame)
        for ev in state.write(w.port, w.reg, w.value):
            if ev.kind in ("fm_on", "fm_off", "fm_freq"):
                ch = ev.channel
                _track(
                    f"fm{ch + 1}", notes, cur, frame,
                    active=state.keyed[ch], pitch=state.fm_pitch(ch), retrigger=ev.kind == "fm_on",
                )
            elif ev.kind in ("ssg_period", "ssg_volume", "ssg_mixer"):
                chans = range(SSG_CHANNELS) if ev.kind == "ssg_mixer" else [ev.channel]
                for ch in chans:
                    _track(
                        f"ssg{ch + 1}", notes, cur, frame,
                        active=state.ssg_audible(ch), pitch=state.ssg_pitch(ch), retrigger=False,
                    )
    final = end_frame if end_frame is not None else last
    for n in names:
        _close(n, notes, cur, final)
    notes.sort(key=lambda x: (x.start, x.channel))
    return notes


def extract_notes(vgm: Vgm, frames: int | None = None) -> list[Note]:
    """Notas de un VGM, repitiendo el bucle hasta `frames` cuadros si se pide."""
    return extract_notes_from_writes(unrolled_writes(vgm, frames), vgm.clock, end_frame=frames)
