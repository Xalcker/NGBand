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

import json
from dataclasses import dataclass
from pathlib import Path

from .chart import DIFFICULTIES, DRUM_BLOCKED_PAIRS, BeatGrid, ChartNote, Note, check_playable, mask_lanes, star_notes

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_name(pitch: int) -> str:
    return f"{NAMES[pitch % 12]}{pitch // 12 - 1}"


DRUMS_FILE = "drums.json"
DRUMS_VERSION = 1
ROLE_LANE = {"tom3": 0, "snare": 1, "tom1": 2, "tom2": 3, "kick": 4}
ROLE_LABELS = {"kick": "Bombo (barra naranja)", "snare": "Tarola (rojo)", "tom1": "Tom 1 / Hi-hat (amarillo)",
               "tom2": "Tom 2 / Ride (azul)", "tom3": "Tom 3 / Crash (verde)"}
ROLES = tuple(ROLE_LABELS)
ROLE_WEIGHT = {"kick": 3, "snare": 3, "tom1": 2, "tom2": 2, "tom3": 2}
# Con menos dificultad los toms se juntan en los que quedan: fácil usa bombo, tarola y tom 1; medio agrega el 2
FOLD = {"facil": {"tom2": "tom1", "tom3": "tom1"}, "medio": {"tom3": "tom2"}, "dificil": {}, "experto": {}}
# Botones a la vez (R4.6): fácil 1 (y solo de los tres pads permitidos), medio 2, difícil y experto 3
MAX_BUTTONS = {"facil": 1, "medio": 2, "dificil": 3, "experto": 3}
EASY_LANES = {ROLE_LANE["kick"], ROLE_LANE["snare"], ROLE_LANE["tom1"]}
MAX_HANDS = 2  # golpes de mano a la vez (sin el bombo)
PRO_CYMBALS = {"experto"}
CYMBAL_WEIGHT_PENALTY = 0.5
MERGE_FRAMES = 1  # golpes a esta distancia son el mismo momento
MIN_GROUP_HITS = 3  # sugerencia: grupos con menos golpes no se asignan

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
    termina la anterior es la misma con otro tono (el barrido del bombo)."""
    ordered = sorted(ns, key=lambda n: n.frame)
    if channel in UNPITCHED:
        return ordered
    out: list[Note] = []
    end = None
    for n in ordered:
        if end is not None and n.frame == end and out:
            end = n.frame + n.duration
            continue
        out.append(n)
        end = n.frame + n.duration
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


def load_drums(song_dir: Path) -> dict[str, dict] | None:
    """La asignación guardada (grupo -> {"lane", "cymbal"}), o None si la canción aún no tiene."""
    path = song_dir / DRUMS_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != DRUMS_VERSION:
        raise ValueError(f"{path}: versión de drums.json no soportada ({data.get('version')})")
    return data.get("groups", {})


def check_assignment(assignment: dict[str, dict]) -> None:
    for key, item in assignment.items():
        if item.get("lane") not in (*ROLES, None):
            raise ValueError(f"{key}: papel desconocido {item.get('lane')!r}")


def dump_drums(assignment: dict[str, dict]) -> str:
    lines = [f'{{\n  "version": {DRUMS_VERSION},\n  "groups": {{']
    lines.append(",\n".join(
        f"    {json.dumps(key, ensure_ascii=False)}: {json.dumps({'lane': item.get('lane'), 'cymbal': bool(item.get('cymbal'))})}"
        for key, item in sorted(assignment.items())))
    lines.append("  }\n}\n")
    return "\n".join(lines)


def save_drums(song_dir: Path, assignment: dict[str, dict]) -> None:
    check_assignment(assignment)
    (song_dir / DRUMS_FILE).write_text(dump_drums(assignment), encoding="utf-8", newline="\n")


# --- Chart --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    frame: int
    role: str
    cymbal: bool


def drum_hits(notes: dict[str, list[Note]], channels: list[str], assignment: dict[str, dict]) -> list[Hit]:
    hits = []
    for name in channels:
        for note in channel_strikes(name, notes.get(name, [])):
            item = assignment.get(group_key(name, note.pitch))
            if item and item.get("lane"):
                hits.append(Hit(note.frame, item["lane"], bool(item.get("cymbal")) and item["lane"] not in ("kick", "snare")))
    return sorted(hits, key=lambda h: h.frame)


def build_drum_chart(hits: list[Hit], difficulty_name: str, grid: BeatGrid, lead_in: int) -> list[ChartNote]:
    """El Chart de batería de una Difficulty.

    1. Los toms se juntan según la Difficulty (FOLD) y los golpes casi simultáneos son un "momento".
    2. De cada momento quedan hasta MAX_BUTTONS botones (primero bombo y tarola), con a lo más MAX_HANDS
       golpes de mano y sin verde + amarillo.
    3. Se quitan momentos hasta que ninguno quede a menos de min_gap cuadros de otro, conservando los
       tiempos fuertes y los de bombo y tarola.
    4. Los platillos solo se marcan en las Difficulties Pro (PRO_CYMBALS)."""
    difficulty = next(d for d in DIFFICULTIES if d.name == difficulty_name)
    fold, max_buttons = FOLD[difficulty_name], MAX_BUTTONS[difficulty_name]
    moments: list[dict] = []
    for hit in hits:
        role = fold.get(hit.role, hit.role)
        weight = ROLE_WEIGHT[role] - (CYMBAL_WEIGHT_PENALTY if hit.cymbal else 0)
        if moments and hit.frame - moments[-1]["frame"] <= MERGE_FRAMES:
            lanes = moments[-1]["lanes"]
            old = lanes.get(ROLE_LANE[role])
            lanes[ROLE_LANE[role]] = (max(weight, old[0]) if old else weight, hit.cymbal and (old[1] if old else True))
        else:
            moments.append({"frame": hit.frame, "lanes": {ROLE_LANE[role]: (weight, hit.cymbal)}})
    pro = difficulty_name in PRO_CYMBALS
    for moment in moments:
        lanes = moment["lanes"]
        if not pro and any(not cymbal for _, cymbal in lanes.values()):
            lanes = {lane: value for lane, value in lanes.items() if not value[1]}
        ranked = sorted(lanes.items(), key=lambda item: -item[1][0])
        kept: dict[int, tuple] = {}
        for lane, value in ranked:
            is_hand = lane != ROLE_LANE["kick"]
            hands = sum(1 for other in kept if other != ROLE_LANE["kick"])
            if (len(kept) < max_buttons and (not is_hand or hands < MAX_HANDS)
                    and not any({lane, other} in DRUM_BLOCKED_PAIRS for other in kept)):
                kept[lane] = value
        moment["lanes"] = kept
        moment["weight"] = max((w for w, _ in kept.values()), default=0)
    moments = [m for m in moments if m["lanes"]]
    by_priority = sorted(moments, key=lambda m: (-grid.strength(m["frame"]), -m["weight"], m["frame"]))
    chosen: list[dict] = []
    for moment in by_priority:
        if all(abs(moment["frame"] - other["frame"]) >= difficulty.min_gap for other in chosen):
            chosen.append(moment)
    chosen.sort(key=lambda m: m["frame"])
    masks = [sum(1 << lane for lane in m["lanes"]) for m in chosen]
    stars = star_notes(len(chosen), [mask & (mask - 1) != 0 for mask in masks])
    return [
        ChartNote(lead_in + m["frame"], mask, None, star,
                  pro and any(cymbal for lane, (_, cymbal) in m["lanes"].items() if lane not in (ROLE_LANE["kick"], ROLE_LANE["snare"])))
        for m, mask, star in zip(chosen, masks, stars)
    ]


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
