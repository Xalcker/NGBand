"""Batería: de los golpes de los canales de batería de un VGM a un Chart de 4 pads y bombo (R4.6, R13.3).

Mismo generador que NESBand y GENBand. Un VGM no dice qué es cada golpe, así que primero se agrupan: cada grupo
es un canal y un tono (en ADPCM-A, el índice del sample; en un canal FM o SSG que toca batería, la altura). Cada
grupo recibe un papel; la asignación vive en `src/songs/<canción>/drums.json`, aparte del Chart, para que
`ngband reimport` no la pierda (R13.3). Con ella se genera un Chart por Difficulty (build_drum_chart).

Papeles y carriles (cada carril es el color de siempre):
    tarola = rojo (↓)   tom 1 / hi-hat = amarillo (→)   tom 2 / ride = azul (B)   tom 3 / crash = verde (←)
    bombo = naranja (C), la barra
En experto los platillos se marcan con el bit $40 (rombos, R4.4); en las demás Difficulties se tocan como toms.

Límites de acordes (R4.6): 3 botones en difícil y experto, 2 en medio; en fácil solo bombo, tarola y tom 1.
"""

from __future__ import annotations

from dataclasses import dataclass

# Papeles, drums.json y el chart de batería son los mismos en los cuatro juegos: viven en bandcore
from bandcore.drums import (  # noqa: F401
    CYMBAL_WEIGHT_PENALTY,
    DRUMS_FILE,
    DRUMS_VERSION,
    FOLD,
    MAX_BUTTONS,
    MAX_HANDS,
    MERGE_FRAMES,
    MIN_GROUP_HITS,
    PRO_CYMBALS,
    ROLES,
    ROLE_LABELS,
    ROLE_LANE,
    ROLE_WEIGHT,
    Hit,
    build_drum_chart,
    check_assignment,
    dump_drums,
    load_drums,
    save_drums,
)

from .chart import DIFFICULTIES, DRUM_BLOCKED_PAIRS, BeatGrid, ChartNote, Note, check_playable, mask_lanes


NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_name(pitch: int) -> str:
    return f"{NAMES[pitch % 12]}{pitch // 12 - 1}"


EASY_LANES = {ROLE_LANE["kick"], ROLE_LANE["snare"], ROLE_LANE["tom1"]}

UNPITCHED = ("adpcma",)  # canales cuyos golpes se distinguen por sample, no por altura


@dataclass(frozen=True)
class Group:
    key: str  # "adpcma:2" (por sample) o "fm4:G3" (un canal FM o SSG, por tono)
    channel: str
    pitch: int
    instrument: str
    count: int
    avg_duration: float
    first_frame: int

    @property
    def tone(self) -> str:
        return f"sample {self.pitch}" if self.channel in UNPITCHED else midi_to_name(self.pitch)


def group_key(channel: str, pitch: int) -> str:
    return f"{channel}:{pitch}" if channel in UNPITCHED else f"{channel}:{midi_to_name(pitch)}"


def channel_strikes(channel: str, ns: list[Note]) -> list[Note]:
    """Los golpes de un canal. En ADPCM-A cada nota ya es un golpe; en FM/SSG una nota que empieza donde
    termina la anterior con un tono más grave es la misma (el barrido del bombo, que solo baja); si el tono sube,
    es otro golpe pegado al anterior."""
    ordered = sorted(ns, key=lambda n: n.frame)
    if channel in UNPITCHED:
        return ordered
    out: list[Note] = []
    end = last = None
    for n in ordered:
        if end is not None and n.frame == end and out and n.pitch <= last:
            end, last = n.frame + n.duration, n.pitch
            continue
        out.append(n)
        end, last = n.frame + n.duration, n.pitch
    return out


def drum_groups(notes: dict[str, list[Note]], channels: list[str]) -> list[Group]:
    """Los grupos de golpes de los canales de batería (por nombre: "adpcma", "fm4"...), ordenados por canal y tono."""
    found: dict[str, tuple[str, list[Note]]] = {}
    for name in channels:
        for note in channel_strikes(name, notes.get(name, [])):
            found.setdefault(group_key(name, note.pitch), (name, []))[1].append(note)
    groups = [
        Group(key, channel, ns[0].pitch, ns[0].instrument or "", len(ns),
              sum(n.duration for n in ns) / len(ns), min(n.frame for n in ns))
        for key, (channel, ns) in found.items()
    ]
    order = {name: i for i, name in enumerate(channels)}
    return sorted(groups, key=lambda g: (order[g.channel], g.pitch))


def suggest_assignment(groups: list[Group]) -> dict[str, dict]:
    """Una primera asignación (el punto de partida para corregir drums.json).

    En ADPCM-A los samples más usados son bombo y tarola; los demás, toms. En un canal FM o SSG el tono más
    grave es el bombo y los siguientes, toms. Los grupos con menos de MIN_GROUP_HITS golpes no se asignan."""
    assignment: dict[str, dict] = {g.key: {"lane": None, "cymbal": False} for g in groups}
    used: set[str] = set()

    def give(group: Group, preferred: list[str]) -> None:
        role = next((r for r in preferred if r not in used), preferred[-1])
        assignment[group.key] = {"lane": role, "cymbal": False}
        used.add(role)

    sampled = sorted((g for g in groups if g.channel in UNPITCHED and g.count >= MIN_GROUP_HITS), key=lambda g: (-g.count, g.pitch))
    for index, group in enumerate(sampled):
        give(group, ["kick"] if index == 0 else ["snare"] if index == 1 else ["tom3", "tom2", "tom1"])
    tonal = sorted((g for g in groups if g.channel not in UNPITCHED and g.count >= MIN_GROUP_HITS), key=lambda g: g.pitch)
    for index, group in enumerate(tonal):
        give(group, ["kick", "tom3", "tom2", "tom1"] if index == 0 else ["snare", "tom3", "tom2", "tom1"] if "snare" not in used else ["tom3", "tom2", "tom1"])
    return assignment


# --- drums.json -----------------------------------------------------------------------------------


# --- Chart --------------------------------------------------------------------------------------------


def drum_hits(notes: dict[str, list[Note]], channels: list[str], assignment: dict[str, dict]) -> list[Hit]:
    hits = []
    for name in channels:
        for note in channel_strikes(name, notes.get(name, [])):
            item = assignment.get(group_key(name, note.pitch))
            if item and item.get("lane"):
                hits.append(Hit(note.frame, item["lane"], bool(item.get("cymbal")) and item["lane"] not in ("kick", "snare")))
    return sorted(hits, key=lambda h: h.frame)


def build_drum_charts(hits: list[Hit], grid: BeatGrid, lead_in: int) -> list[list[ChartNote]]:
    """Los Charts de batería de las 4 Difficulties, verificados con check_drum_chart."""
    charts = [build_drum_chart(hits, d.name, grid, lead_in) for d in DIFFICULTIES]
    for difficulty, chart in zip(DIFFICULTIES, charts):
        check_drum_chart(chart, difficulty.name)
    return charts


def check_drum_chart(chart: list[ChartNote], difficulty_name: str) -> None:
    """Falla si un Chart de batería rompe check_playable (verde + amarillo) o los límites de acorde de R4.6."""
    check_playable(chart, DRUM_BLOCKED_PAIRS)
    limit = MAX_BUTTONS[difficulty_name]
    for note in chart:
        lanes = mask_lanes(note.mask)
        if len(lanes) > limit:
            raise ValueError(f"cuadro {note.frame}: {len(lanes)} botones, el máximo en {difficulty_name} es {limit}")
        if difficulty_name == "facil" and not set(lanes) <= EASY_LANES:
            raise ValueError(f"cuadro {note.frame}: en fácil solo bombo, tarola y tom 1 (carriles {list(lanes)})")
