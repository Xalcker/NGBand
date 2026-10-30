"""Chart_Generator compartido con NESBand y GENBand (R2.11, R4.6, R14.7, R14.13).

Genera los Charts de las 4 Difficulties a partir de las notas de un canal:
  1. Reducir: según la dificultad se quitan notas demasiado juntas, conservando primero los tiempos fuertes.
  2. Carriles: la nota más aguda de su vecindario va a la derecha y la más grave a la izquierda,
     respetando el contorno de la melodía.
  3. Acordes (medio, difícil y experto): de 2 carriles, por un arpegio o por la armonía del canal compañero.
  4. Sustain y frases de Star_Power.

`check_playable` rechaza lo que no se puede tocar con la cruz del stick: verde (←) y amarillo (→) a la vez
(R6.2), y también amarillo + naranja, que con ESPEJO (R8.2) se volverían verde + amarillo.

Formato `ChartEv` (2 bytes, ver design.md): `delta_lo` = cuadros desde el evento anterior; `lanes` con los bits
0-4 = carriles, bit 5 = estelar, bit 6 = sustain (en batería: platillo), bit 7 = fin de cola. `lanes = 0xFF`
cierra el Chart. Un delta de 255 cuadros o más se parte con eventos de extensión (255, 0) sin carriles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ROLES = ("lead", "keys", "bass")
KEYS_WINDOW = 6  # vecindario de notas (a cada lado) con el que el teclado reparte sus carriles (la guitarra usa 4)


@dataclass(frozen=True)
class Note:
    """Una nota extraída de un canal (frame = cuadro a 60 Hz, pitch = altura MIDI, duration en cuadros)."""

    frame: int
    pitch: int
    duration: int
    extra: int | None = None  # segunda altura de un arpegio fusionado
    instrument: str | None = None


@dataclass(frozen=True)
class Difficulty:
    name: str
    lanes: int  # cuántos carriles usa (desde el verde)
    min_gap: int  # cuadros mínimos entre dos notas
    chord_gap: int = 0  # cuadros mínimos entre dos acordes (0 = sin acordes)
    chord_notes: int = 0  # notas sueltas mínimas entre dos acordes


DIFFICULTIES = [
    Difficulty("facil", lanes=3, min_gap=24),
    Difficulty("medio", lanes=4, min_gap=14, chord_gap=150, chord_notes=8),
    Difficulty("dificil", lanes=5, min_gap=9, chord_gap=72, chord_notes=6),
    Difficulty("experto", lanes=5, min_gap=5, chord_gap=42, chord_notes=5),
]


@dataclass(frozen=True)
class BeatGrid:
    frames_per_beat: int
    first_beat: int  # cuadro (relativo a la música) del primer tiempo

    def strength(self, frame: int) -> int:
        """3 = en el tiempo, 2 = medio tiempo, 1 = cuarto de tiempo, 0 = otra cosa."""
        offset = (frame - self.first_beat) % self.frames_per_beat
        for level, divisions in ((3, 1), (2, 2), (1, 4)):
            step = self.frames_per_beat / divisions
            nearest = round(offset / step) * step
            if abs(offset - nearest) <= 1:
                return level
        return 0


def estimate_beat(onsets: list[int], hint: int | None = None) -> BeatGrid:
    """Estima la duración del tiempo a partir de todos los ataques de la canción (o usa `hint`)."""
    onsets = sorted(set(onsets))
    if hint:
        period = hint
    else:
        counts: dict[int, int] = {}
        for a, b in zip(onsets, onsets[1:]):
            gap = b - a
            if 3 <= gap <= 48:
                counts[gap] = counts.get(gap, 0) + 1
        step = max(counts, key=lambda g: (counts[g], -g)) if counts else 8
        period = step
        while period < 18:
            period *= 2
    best_phase = max(range(period), key=lambda p: sum(1 for f in onsets if (f - p) % period == 0))
    return BeatGrid(period, best_phase)


def merge_attacks(notes: list[Note], max_gap: int = 2) -> list[Note]:
    """Junta en una sola nota los "gestos" hechos de notas cortísimas (golpes, barridos de tono, arpegios
    rapidísimos). El grupo toma el tono de su nota más larga y empieza en la primera."""
    groups: list[list[Note]] = []
    for note in notes:
        last = groups[-1][-1] if groups else None
        if last and last.duration <= max_gap and note.frame - last.frame <= max_gap:
            groups[-1].append(note)
        else:
            groups.append([note])
    merged = []
    for group in groups:
        first, last = group[0], group[-1]
        main = max(group, key=lambda n: n.duration)
        merged.append(Note(first.frame, main.pitch, last.frame + last.duration - first.frame, arpeggio_pitch(group, main)))
    return merged


def arpeggio_pitch(group: list[Note], main: Note) -> int | None:
    """La otra altura de un arpegio (3+ notas, 2+ alturas, no un barrido), o None. Se toma la altura más
    lejana a la principal si está a entre 3 y 12 semitonos."""
    if len(group) < 3:
        return None
    pitches = [n.pitch for n in group]
    if len(set(pitches)) < 2 or pitches == sorted(pitches) or pitches == sorted(pitches, reverse=True):
        return None
    far = max(set(pitches), key=lambda p: (abs(p - main.pitch), p))
    return far if 3 <= abs(far - main.pitch) <= 12 else None


def reduce_notes(notes: list[Note], difficulty: Difficulty, grid: BeatGrid, role: str = "lead") -> list[Note]:
    """Quita notas hasta que ninguna quede a menos de min_gap cuadros de otra (primero los tiempos fuertes;
    el bajo, además, prefiere las notas largas)."""
    if role == "bass":
        by_priority = sorted(notes, key=lambda n: (-grid.strength(n.frame), -n.duration, n.frame))
    else:
        by_priority = sorted(notes, key=lambda n: (-grid.strength(n.frame), n.frame))
    kept: list[Note] = []
    for note in by_priority:
        if all(abs(note.frame - other.frame) >= difficulty.min_gap for other in kept):
            kept.append(note)
    return sorted(kept, key=lambda n: n.frame)


def assign_lanes(notes: list[Note], lanes: int, window: int = 4) -> list[int]:
    """Un carril (0..lanes-1) por nota, siguiendo la altura y el contorno."""
    result: list[int] = []
    for i, note in enumerate(notes):
        neighborhood = sorted({n.pitch for n in notes[max(0, i - window) : i + window + 1]})
        if len(neighborhood) == 1:
            lane = result[-1] if result else lanes // 2
        else:
            rank = neighborhood.index(note.pitch)
            lane = round(rank * (lanes - 1) / (len(neighborhood) - 1))
        if result:
            prev_lane, prev_pitch = result[-1], notes[i - 1].pitch
            if note.pitch == prev_pitch:
                lane = prev_lane
            elif note.pitch > prev_pitch and lane <= prev_lane:
                lane = min(prev_lane + 1, lanes - 1)
            elif note.pitch < prev_pitch and lane >= prev_lane:
                lane = max(prev_lane - 1, 0)
        result.append(lane)
    return result


STAR_FLAG = 0x20  # forma parte de una frase de Star_Power
STAR_PHRASE_LEN = 4  # notas por frase (si aciertas todas, la barra sube 25)
STAR_FIRST = 10  # índice de la primera nota de la primera frase
STAR_SPACING = 24  # notas entre el inicio de una frase y el de la siguiente
SUSTAIN_FLAG = 0x40  # la nota tiene cola (su fin va en otra entrada); en batería, platillo
END_FLAG = 0x80  # entrada de fin de cola: los bits 0-4 son los carriles que la sueltan
LANE_MASK = 0x1F
MIN_SUSTAIN = 16  # cuadros mínimos de cola
SUSTAIN_TRIM = 4  # la cola termina un poco antes de que acabe la nota
SUSTAIN_GAP = 3  # cuadros libres entre el fin de una cola y la siguiente nota del mismo carril


@dataclass(frozen=True)
class ChartNote:
    frame: int  # cuadro en que suena (contando la entrada de la autopista)
    mask: int  # bits 0-4 = carriles
    end: int | None = None  # cuadro en que termina su cola (None = nota normal)
    star: bool = False  # nota de una frase de Star_Power
    cymbal: bool = False  # solo batería (sin colas): el pad es un platillo, no un tom


def sustain_ends(notes: list[Note], lanes: list[int | tuple[int, ...]]) -> list[int | None]:
    """Fin de la cola de cada nota, o None si dura muy poco. Termina antes de la siguiente nota que choque
    con sus carriles (SUSTAIN_GAP cuadros libres). Un elemento de `lanes` es un carril o la tupla de un acorde."""
    sets = [set(lane) if isinstance(lane, tuple) else {lane} for lane in lanes]
    ends: list[int | None] = []
    for i, note in enumerate(notes):
        limit = note.frame + note.duration
        for other, other_lanes in zip(notes[i + 1 :], sets[i + 1 :]):
            if lanes_clash(other_lanes, sets[i]):
                limit = min(limit, other.frame - SUSTAIN_GAP)
                break
        length = limit - note.frame - SUSTAIN_TRIM
        ends.append(note.frame + length if length >= MIN_SUSTAIN else None)
    return ends


# Verde = ←, amarillo = → (R6.1): no se pueden apretar a la vez (R6.2). Con ESPEJO (R8.2) verde↔naranja y
# rojo↔azul, así que amarillo + naranja se volvería verde + amarillo: tampoco se piden juntos.
BLOCKED_PAIRS = ({0, 2}, {2, 4})
# En la batería el bombo (naranja) se pisa con el pie y ESPEJO no aplica: solo verde + amarillo es imposible.
DRUM_BLOCKED_PAIRS = ({0, 2},)


def lanes_clash(a: set[int], b: set[int], blocked=BLOCKED_PAIRS) -> bool:
    """¿Dos notas con estos carriles no pueden estar activas a la vez? (mismo carril o pareja bloqueada)"""
    return bool(a & b) or any({x, y} in blocked for x in a for y in b)


def second_lane(lane: int, lanes: int, delta: int) -> int | None:
    """Carril del segundo botón de un acorde, a 1 carril (terceras) o 2 del primero, del lado de la otra
    altura si cabe; nunca una pareja bloqueada. None si no cabe."""
    step = 1 if abs(delta) < 5 else 2
    sign = 1 if delta > 0 else -1
    for distance in (step, 3 - step):
        for direction in (sign, -sign):
            candidate = lane + direction * distance
            if 0 <= candidate < lanes and {lane, candidate} not in BLOCKED_PAIRS:
                return candidate
    return None


def chord_masks(
    notes: list[Note], lanes: list[int], difficulty: Difficulty, grid: BeatGrid, role: str, partner: list[Note]
) -> list[int]:
    """La máscara de carriles de cada nota: un bit, o dos si la nota se vuelve acorde."""
    masks = [1 << lane for lane in lanes]
    if not difficulty.chord_gap or role == "bass":
        return masks
    min_strength = 2 if role == "lead" else 1
    by_frame = {n.frame: n for n in partner}
    last_chord = -(10**9)
    last_chord_index = -(10**9)
    for i, (note, lane) in enumerate(zip(notes, lanes)):
        next_gap = notes[i + 1].frame - note.frame if i + 1 < len(notes) else 10**9
        if (
            i < 2
            or note.frame - last_chord < difficulty.chord_gap
            or i - last_chord_index <= difficulty.chord_notes
            or next_gap < difficulty.min_gap * 2
            or grid.strength(note.frame) < min_strength
        ):
            continue
        other = note.extra
        if other is None:
            for d in range(-2, 3):
                near = by_frame.get(note.frame + d)
                if near and abs(near.pitch - note.pitch) >= 3:
                    other = near.pitch
                    break
        if other is None:
            continue
        lane2 = second_lane(lane, difficulty.lanes, other - note.pitch)
        if lane2 is not None and lane2 != lane:
            masks[i] |= 1 << lane2
            last_chord = note.frame
            last_chord_index = i
    return masks


def build_chart(
    notes: list[Note],
    difficulty: Difficulty,
    grid: BeatGrid,
    lead_in: int,
    role: str = "lead",
    partner: list[Note] | None = None,
) -> list[ChartNote]:
    """El Chart de una Difficulty. Guarda cuadros, no filas, así sirve para cualquier velocidad de caída."""
    reduced = reduce_notes(merge_attacks(notes), difficulty, grid, role)
    lanes = assign_lanes(reduced, difficulty.lanes, window=KEYS_WINDOW if role == "keys" else 4)
    masks = chord_masks(reduced, lanes, difficulty, grid, role, merge_attacks(partner or []))
    ends = sustain_ends(reduced, [mask_lanes(mask) for mask in masks])
    stars = star_notes(len(reduced), [mask & (mask - 1) != 0 for mask in masks])
    return [
        ChartNote(lead_in + note.frame, mask, None if end is None else lead_in + end, star)
        for note, mask, end, star in zip(reduced, masks, ends, stars)
    ]


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


def star_notes(count: int, chords: list[bool] | None = None) -> list[bool]:
    """Qué notas forman frases de Star_Power: grupos de STAR_PHRASE_LEN notas sueltas (nunca acordes) separados
    por STAR_SPACING notas. El final de una frase es la nota siguiente que ya no es estelar."""
    chords = chords or [False] * count
    stars = [False] * count
    for start in range(STAR_FIRST, count - STAR_PHRASE_LEN, STAR_SPACING):
        for begin in range(start, min(start + STAR_SPACING - STAR_PHRASE_LEN - 1, count - STAR_PHRASE_LEN)):
            if not any(chords[begin : begin + STAR_PHRASE_LEN]):
                for i in range(begin, begin + STAR_PHRASE_LEN):
                    stars[i] = True
                break
    return stars


# --- Formato ChartEv ----------------------------------------------------------------------------------------

CHART_END = 0xFF  # lanes = $FF marca el fin del Chart
MAX_DELTA = 255


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


def check_playable(chart: list[ChartNote], blocked=BLOCKED_PAIRS) -> None:
    """Falla si el Chart pide algo imposible: carriles de una pareja bloqueada (verde y amarillo, y con ESPEJO
    amarillo y naranja; en batería DRUM_BLOCKED_PAIRS) a la vez, en un acorde o tocando una nota mientras se
    sostiene otra."""
    sets = [set(mask_lanes(n.mask)) for n in chart]
    for i, (note, lanes) in enumerate(zip(chart, sets)):
        if any({x, y} in blocked for x in lanes for y in lanes):
            raise ValueError(f"acorde imposible en el cuadro {note.frame}: carriles {sorted(lanes)}")
        if note.end is None:
            continue
        for other, other_lanes in zip(chart[i + 1 :], sets[i + 1 :]):
            if other.frame >= note.end:
                break
            if lanes_clash(other_lanes, lanes, blocked):
                raise ValueError(f"la nota del cuadro {other.frame} cae mientras se sostiene la del {note.frame}")
