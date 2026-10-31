"""Charts de NGBand: el generador común está en bandcore (`bandcore.chart`, ahí se explica cómo se arma un chart;
también `check_playable`, que rechaza verde (←) y amarillo (→) a la vez, R6.2, y amarillo + naranja por ESPEJO, R8.2).

Formato `ChartEv` (2 bytes, ver design.md): `delta_lo` = cuadros desde el evento anterior; `lanes` con los bits
0-4 = carriles, bit 5 = estelar, bit 6 = sustain (en batería: platillo), bit 7 = fin de cola. `lanes = 0xFF`
cierra el Chart. Un delta de 255 cuadros o más se parte con eventos de extensión (255, 0) sin carriles: por eso
`chart_entries` y `chart_size` son los de aquí y no los de bandcore.
"""

from __future__ import annotations

import re

# El generador de charts, la nota y las reglas de lo que se puede tocar son los mismos en los cuatro juegos:
# viven en bandcore (aquí se vuelven a exportar para el resto del juego)
from bandcore.chart import (  # noqa: F401
    BLOCKED_PAIRS,
    CHART_END,
    DIFFICULTIES,
    DRUM_BLOCKED_PAIRS,
    END_FLAG,
    KEYS_WINDOW,
    MAX_DELTA,
    MIN_SUSTAIN,
    ROLES,
    STAR_FIRST,
    STAR_FLAG,
    STAR_PHRASE_LEN,
    STAR_SPACING,
    SUSTAIN_FLAG,
    SUSTAIN_GAP,
    SUSTAIN_TRIM,
    BeatGrid,
    ChartNote,
    Difficulty,
    Note,
    arpeggio_pitch,
    assign_lanes,
    build_chart,
    check_playable,
    chord_masks,
    estimate_beat,
    lanes_clash,
    merge_attacks,
    reduce_notes,
    second_lane,
    star_notes,
    sustain_ends,
)


LANE_MASK = 0x1F


def build_charts(
    notes: list[Note], grid: BeatGrid, lead_in: int, role: str = "lead", partner: list[Note] | None = None
) -> list[list[ChartNote]]:
    """Los Charts de las 4 Difficulties (facil, medio, dificil, experto), ya verificados con check_playable."""
    charts = [build_chart(notes, d, grid, lead_in, role, partner) for d in DIFFICULTIES]
    for chart in charts:
        check_playable(chart)
    return charts


def mask_lanes(mask: int) -> tuple[int, ...]:
    return tuple(b for b in range(5) if mask >> b & 1)


# --- Formato ChartEv ----------------------------------------------------------------------------------------


def chart_entries(chart: list[ChartNote]) -> list[tuple[int, int]]:
    """El Chart como pares `ChartEv` (delta_lo, lanes). Un delta de 255 o más se parte con eventos de extensión
    (255, 0) sin carriles. Una nota con cola lleva SUSTAIN_FLAG y su fin es otra entrada con END_FLAG."""
    events: list[tuple[int, int]] = []
    end_masks: dict[int, int] = {}
    for note in chart:
        mask = note.mask | (STAR_FLAG if note.star else 0)
        if note.cymbal:
            if note.end is not None:
                raise ValueError(f"nota del cuadro {note.frame}: un platillo no lleva cola (comparten el bit $40)")
            mask |= SUSTAIN_FLAG
        if note.end is None:
            events.append((note.frame, mask))
        else:
            events.append((note.frame, mask | SUSTAIN_FLAG))
            end_masks[note.end] = end_masks.get(note.end, 0) | note.mask
    events += [(frame, END_FLAG | mask) for frame, mask in end_masks.items()]
    events.sort(key=lambda e: e[0])  # estable: a igual cuadro, las notas van antes que los fines

    entries: list[tuple[int, int]] = []
    previous = 0
    for frame, mask in events:
        delta = frame - previous
        if delta < 0:
            raise ValueError(f"evento fuera de orden en el cuadro {frame}")
        while delta >= MAX_DELTA:
            entries.append((MAX_DELTA, 0))
            delta -= MAX_DELTA
        entries.append((delta, mask))
        previous = frame
    entries.append((0, CHART_END))
    return entries


def chart_size(chart: list[ChartNote]) -> int:
    return 2 * len(chart_entries(chart))


def chart_from_entries(entries: list[tuple[int, int]], drums: bool = False) -> list[ChartNote]:
    """Lee pares `ChartEv` y reconstruye el Chart (inverso de chart_entries). Con `drums`, el bit $40 es un
    platillo y no una cola."""
    notes: list[dict] = []
    open_tails: list[dict] = []
    frame = 0
    for delta, lanes in entries:
        frame += delta
        if lanes == CHART_END:
            break
        if lanes == 0:
            continue  # evento de extensión
        if lanes & END_FLAG:
            released = lanes & LANE_MASK
            for tail in [t for t in open_tails if t["mask"] & released == t["mask"]]:
                tail["end"] = frame
                open_tails.remove(tail)
            continue
        note = {"frame": frame, "mask": lanes & LANE_MASK, "star": bool(lanes & STAR_FLAG), "end": None, "cymbal": False}
        if lanes & SUSTAIN_FLAG:
            if drums:
                note["cymbal"] = True
            else:
                open_tails.append(note)
        notes.append(note)
    else:
        raise ValueError("Chart sin marca de fin ($FF)")
    if open_tails:
        raise ValueError(f"cola sin fin en el cuadro {open_tails[0]['frame']}")
    return [ChartNote(n["frame"], n["mask"], n["end"], n["star"], n["cymbal"]) for n in notes]


def chart_to_c(label: str, chart: list[ChartNote]) -> str:
    """El Chart como un arreglo C de `ChartEv` ({delta_lo, lanes})."""
    lines = [f"static const ChartEv {label}[] = {{"]
    entries = chart_entries(chart)
    for i in range(0, len(entries), 6):
        lines.append("    " + " ".join(f"{{{d}, 0x{m:02X}}}," for d, m in entries[i : i + 6]))
    lines.append("};")
    return "\n".join(lines) + "\n"


_EV_RE = re.compile(r"\{\s*(\d+)\s*,\s*0[xX]([0-9A-Fa-f]{1,2})\s*\}")


def entries_from_c(text: str) -> list[tuple[int, int]]:
    """Lee de vuelta los pares `ChartEv` de un arreglo escrito por chart_to_c."""
    return [(int(d), int(m, 16)) for d, m in _EV_RE.findall(text)]


def chart_from_c(text: str, drums: bool = False) -> list[ChartNote]:
    return chart_from_entries(entries_from_c(text), drums)


def chart_buttons(chart: list[ChartNote]) -> int:
    """Notas del Chart como las cuenta el Judge: cada botón de un acorde es una Note (R2.4)."""
    return sum(bin(n.mask & LANE_MASK).count("1") for n in chart)
