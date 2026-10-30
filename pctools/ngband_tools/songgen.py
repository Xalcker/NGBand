"""Song_Importer: de un VGM del YM2610 a `src/songs/<n>/song.c` e `import.json` (R14.1-R14.5, R14.9).

Pasos de `import_song`:
  1. Lee el VGM (`.vgm`/`.vgz`) y repite el bucle hasta `--duration` segundos (R14.5).
  2. Agrupa las escrituras por cuadro y codifica el Frame_Stream (frames.py).
  3. Extrae las notas FM/SSG (notes.py) y los golpes de ADPCM-A (el índice de sample es la altura).
  4. Genera los Charts de las 4 Difficulties de guitarra, teclado y bajo (12 Charts) y de la batería.
  5. Escribe song.c (Frame_Stream + Charts + ficha `Song`) e import.json. Nada se escribe si algo falla.

Los Charts llevan `LEAD_IN` cuadros de autopista antes de que arranque la música.
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path

from . import chart as ch
from . import chartedit as ce
from . import drums as dr
from . import frames as fr
from . import notes as nt
from . import vgm
from .songlist import ROOT
from .ym2610 import Ym2610State

SONGS_DIR = ROOT / "src" / "songs"

LEAD_IN = 128  # cuadros de autopista antes de la música
DEFAULT_DURATION = 120  # segundos, si el VGM tiene bucle y no se pide otra cosa
MAX_FRAMES = 65000  # el juego cuenta los cuadros en 16 bits
TEXT_MAX = 26  # caracteres que caben en el menú

CHANNEL_NAMES = ["fm1", "fm2", "fm3", "fm4", "ssg1", "ssg2", "ssg3", "adpcma", "adpcmb"]
MELODIC_CHANNELS = CHANNEL_NAMES[:7]
INSTRUMENTS = [("guitarra", "lead"), ("teclado", "keys"), ("bajo", "bass")]
DRUMS = "bateria"
PARTNER = {"guitarra": "teclado", "teclado": "guitarra"}
OPTION_KEYS = ("title", "game", "duration", "beat_frames", "guitarra", "teclado", "bajo", DRUMS)
ADPCMA_HIT_FRAMES = 4  # duración nominal de un golpe de ADPCM-A en el Chart


class ImportError_(ValueError):
    """Error de importación con mensaje para el usuario (no se escribió nada)."""


def clean_text(text: str) -> str:
    """Mayúsculas sin acentos ni símbolos que la fuente no tiene."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9 .,:!?'&()/+-]", " ", text.upper())
    return re.sub(r" +", " ", text).strip()[:TEXT_MAX]


def song_hash(title: str, game: str) -> int:
    """ID del récord (R9.2): no cambia si la canción cambia de lugar en el Menu."""
    return zlib.crc32(f"{title}\n{game}".encode()) & 0xFFFFFFFF


def c_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_channels(text: str | list[str] | None, allow_adpcm: bool = False) -> list[str] | None:
    """Lista de canales (`fm1,ssg2`) validada; None si no se dijo."""
    if not text:
        return None
    names = text if isinstance(text, list) else text.split(",")
    out = []
    for raw in names:
        name = raw.strip().lower()
        if name not in CHANNEL_NAMES or (not allow_adpcm and name not in MELODIC_CHANNELS):
            valid = CHANNEL_NAMES if allow_adpcm else MELODIC_CHANNELS
            raise ImportError_(f"canal desconocido o no melódico: {name} (válidos: {', '.join(valid)})")
        out.append(name)
    return out


# --- notas ------------------------------------------------------------------------------------------


def to_chart_note(n: nt.Note) -> ch.Note:
    """Adaptador de `notes.Note` (inicio/fin/altura decimal) a `chart.Note` (cuadro/altura entera/duración)."""
    return ch.Note(n.start, n.midi, max(1, n.end - n.start), None, n.channel)


def adpcma_hits(writes: list[tuple[int, vgm.Write]], clock: int) -> tuple[list[tuple[int, int]], int]:
    """Golpes de ADPCM-A como (cuadro, índice de sample) y cuántos samples distintos suenan.

    El índice es el orden (por dirección de inicio) de los samples distintos."""
    state = Ym2610State(clock)
    raw: list[tuple[int, int]] = []
    for frame, w in writes:
        for ev in state.write(w.port, w.reg, w.value):
            if ev.kind == "adpcma_on":
                raw.append((frame, state.adpcma_range(ev.channel)[0]))
    starts = sorted({s for _, s in raw})
    index = {s: i for i, s in enumerate(starts)}
    return [(f, index[s]) for f, s in raw], len(starts)


def adpcmb_count(writes: list[tuple[int, vgm.Write]], clock: int) -> int:
    state = Ym2610State(clock)
    return sum(1 for _, w in writes for ev in state.write(w.port, w.reg, w.value) if ev.kind == "adpcmb_on")


def summarize(notes: dict[str, list[ch.Note]]) -> dict[str, tuple[int, float, int]]:
    """(notas tras juntar los adornos, altura mediana, alturas distintas) por canal melódico."""
    out = {}
    for name, ns in notes.items():
        if name not in MELODIC_CHANNELS or not ns:
            continue
        merged = ch.merge_attacks(ns)
        out[name] = (len(merged), statistics.median(n.pitch for n in merged), len({n.pitch for n in merged}))
    return out


def auto_assign(notes: dict[str, list[ch.Note]]) -> dict[str, list[str]]:
    """Elige un canal por instrumento si no se dijo cuál: bajo = el más grave (mediana < Mi 3); guitarra =
    el que más notas tiene contando más las agudas; teclado = el siguiente. Solo cuentan canales con al
    menos 20 notas y 5 alturas distintas. `ngband channels` muestra los canales para corregirlo."""
    stats = {c: s[:2] for c, s in summarize(notes).items() if s[0] >= 20 and s[2] >= 5}
    out: dict[str, list[str]] = {}
    low = [c for c, (_, median) in stats.items() if median < 52]
    if low:
        bass = min(low, key=lambda c: stats[c][1])
        out["bajo"] = [bass]
        stats.pop(bass)
    for name in ("guitarra", "teclado"):
        if stats:
            c = max(stats, key=lambda k: stats[k][0] * max(0.25, 1 + (stats[k][1] - 60) / 24))
            out[name] = [c]
            stats.pop(c)
    return out


def drum_channel_names(notes: dict[str, list[ch.Note]], melodic: set[str]) -> list[str]:
    """Canales de batería si no se dijeron: ADPCM-A si suena, y los canales que casi no cambian de tono."""
    out = [c for c in ("adpcma",) if notes.get(c)]
    for name, (count, _, distinct) in summarize(notes).items():
        if name not in melodic and count >= 20 and distinct < 5:
            out.append(name)
    return out


# --- lectura de la canción ----------------------------------------------------------------------------


@dataclass
class SongData:
    opts: dict
    name: str
    title: str
    game: str
    stream: bytes
    stream_frames: int
    notes: dict[str, list[ch.Note]]
    assign: dict[str, list[str]]
    drums: list[str]
    grid: ch.BeatGrid
    sample_count: int
    folder: Path
    unsupported: list[str]

    def channel_notes(self, names: list[str]) -> list[ch.Note]:
        return sorted((n for c in names for n in self.notes.get(c, [])), key=lambda n: n.frame)


def _music_frames(data: vgm.Vgm, duration: float | None) -> int:
    if duration is None and data.loop_sample is not None:
        duration = DEFAULT_DURATION
    frames = vgm.frame_of(data.total_samples) if duration is None else int(duration * 60)
    return max(1, min(frames, MAX_FRAMES - LEAD_IN - 60))


def load_song(opts: dict, root: Path = ROOT) -> SongData:
    """Lee el VGM y arma todo lo que necesita song.c. No escribe nada."""
    name = opts["name"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ImportError_(f"nombre inválido: {name} (minúsculas, números y _; empieza con letra)")
    source = Path(opts["source"])
    path = source if source.is_absolute() else root / source
    try:
        data = vgm.read_vgm(path)
    except OSError as exc:
        raise ImportError_(f"no se pudo leer {path}: {exc}") from exc
    title = clean_text(opts.get("title") or data.tags.get("title") or name)
    game = clean_text(opts.get("game") or data.tags.get("game") or "")

    frames = _music_frames(data, opts.get("duration"))
    writes = [(f, w) for f, w in vgm.unrolled_writes(data, frames) if f < frames]
    stream = fr.encode_stream(fr.build_frames(writes, frames))

    notes: dict[str, list[ch.Note]] = {c: [] for c in CHANNEL_NAMES}
    for n in nt.extract_notes_from_writes(writes, data.clock, end_frame=frames):
        notes[n.channel].append(to_chart_note(n))
    hits, sample_count = adpcma_hits(writes, data.clock)
    notes["adpcma"] = [ch.Note(f, idx, ADPCMA_HIT_FRAMES, None, "adpcma") for f, idx in hits]

    assign = auto_assign(notes)
    for inst, _ in INSTRUMENTS:
        chosen = parse_channels(opts.get(inst))
        if chosen is not None:
            assign[inst] = chosen
    used = {c for cs in assign.values() for c in cs}
    drums = parse_channels(opts.get(DRUMS), allow_adpcm=True) or drum_channel_names(notes, used)
    onsets = [n.frame for c, ns in notes.items() if c in used or c in drums for n in ns]
    grid = ch.estimate_beat(onsets, opts.get("beat_frames"))
    return SongData(opts, name, title, game, stream, frames, notes, assign, drums, grid, sample_count,
                    root / "src" / "songs" / name, data.unsupported)


# --- Charts -------------------------------------------------------------------------------------------


def drum_assignment(sd: SongData) -> dict | None:
    """Papeles de la batería: los de drums.json si existe, si no la sugerencia (el guardado es de reimport)."""
    if not sd.drums:
        return None
    saved = dr.load_drums(sd.folder)
    return saved if saved is not None else dr.suggest_assignment(dr.drum_groups(sd.notes, sd.drums))


def auto_charts(sd: SongData) -> dict[str, list[ch.ChartNote]]:
    """Charts generados, por clave "instrumento/dificultad"."""
    charts: dict[str, list[ch.ChartNote]] = {}
    for inst, role in INSTRUMENTS:
        names = sd.assign.get(inst)
        if not names:
            continue
        partner_names = sd.assign.get(PARTNER.get(inst, ""), [])
        mine = sd.channel_notes(names)
        partner = sd.channel_notes(partner_names) if partner_names else []
        for diff in ch.DIFFICULTIES:
            charts[f"{inst}/{diff.name}"] = ch.build_chart(mine, diff, sd.grid, LEAD_IN, role, partner)
    assignment = drum_assignment(sd)
    hits = dr.drum_hits(sd.notes, sd.drums, assignment) if assignment else []
    if hits:
        for diff in ch.DIFFICULTIES:
            charts[f"{DRUMS}/{diff.name}"] = dr.build_drum_chart(hits, diff.name, sd.grid, LEAD_IN)
    return charts


def apply_chart_edits(sd: SongData, charts: dict[str, list[ch.ChartNote]]) -> list[str]:
    """Aplica edits.json a los Charts generados (R16.5). Devuelve los avisos de ediciones huérfanas, que se
    omiten. Falla (sin escribir nada) si un Chart editado no se puede tocar."""
    warnings: list[str] = []
    for key, ops in sorted(ce.load_edits(sd.folder).items()):
        if key not in charts:
            warnings.append(f"edits.json: {key}: el Chart ya no existe ({len(ops)} ediciones omitidas)")
            continue
        edited = ce.apply_edits(charts[key], ops, lambda text, key=key: warnings.append(f"edits.json: {key}: {text}"))
        ce.validate_chart(key, edited)
        charts[key] = edited
    return warnings


def load_import_options(name: str, root: Path = ROOT) -> dict:
    """Las opciones guardadas en import.json de una canción (para `reimport`, R14.8)."""
    path = root / "src" / "songs" / name / "import.json"
    try:
        opts = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ImportError_(f"no se pudo leer {path}: {exc}") from exc
    except ValueError as exc:
        raise ImportError_(f"{path}: JSON inválido ({exc})") from exc
    if not isinstance(opts, dict) or "source" not in opts:
        raise ImportError_(f"{path}: faltan las opciones de importación (source)")
    opts["name"] = name
    return opts


def perfect_score(chart: list[ch.ChartNote]) -> int:
    """Puntaje perfecto sin Star_Power ni Sustain: 50 por el Multiplier (1/2/3/4 con combo 0/10/20/30) de cada
    botón. Igual que el Judge de gameplay.c: el combo sube primero y el Multiplier sale del combo ya
    incrementado, así que el golpe número 10 ya vale x2 (R2.3-R2.5)."""
    total = 0
    combo = 0
    for note in chart:
        for _ in ch.mask_lanes(note.mask):
            combo += 1
            total += 50 * (1 + min(3, combo // 10))
    return total


def channel_mask(names: list[str]) -> int:
    """Máscara de canales del driver (FM1-4 = bits 0-3, SSG1-3 = bits 4-6); ADPCM no entra."""
    return sum(1 << MELODIC_CHANNELS.index(n) for n in names if n in MELODIC_CHANNELS)


def render_song_c(sd: SongData, charts: dict[str, list[ch.ChartNote]]) -> tuple[str, list[str]]:
    """El texto de song.c y el reporte por instrumento."""
    out = [
        "/* Generado por `ngband import-song`: no editar a mano (las opciones están en import.json) */",
        f"/* TITULO: {sd.title} */",
        '#include <stddef.h>',
        '#include "song.h"',
        "",
        f"const char song_{sd.name}_name[] = {c_string(sd.title)};",
        "",
        "#ifndef NGBAND_NO_STREAM   /* el 68000 no lo usa: el stream va en la ROM M1 (build.sh) */",
        fr.format_c_array(sd.stream, "song_stream").replace("const unsigned char", "static const u8", 1),
        "#define SONG_STREAM song_stream",
        "#else",
        "#define SONG_STREAM NULL",
        "#endif",
    ]
    chart_refs: list[str] = []
    inst_masks: list[str] = []
    perfect_rows: list[str] = []
    report: list[str] = []
    for inst in [i for i, _ in INSTRUMENTS] + [DRUMS]:
        refs, perfect = [], []
        for diff in ch.DIFFICULTIES:
            key = f"{inst}/{diff.name}"
            if key not in charts:
                refs.append("{ 0, NULL }")
                perfect.append("0")
                continue
            chart = charts[key]
            if inst == DRUMS:
                dr.check_drum_chart(chart, diff.name)
            else:
                ch.check_playable(chart)
            label = f"{inst}_{diff.name}"
            out.append(ch.chart_to_c(label, chart))
            refs.append(f"{{ {len(ch.chart_entries(chart))}, {label} }}")
            perfect.append(f"{perfect_score(chart)}u")
        chart_refs.append("{ " + ", ".join(refs) + " }")
        perfect_rows.append("{ " + ", ".join(perfect) + " }")
        names = sd.drums if inst == DRUMS else sd.assign.get(inst, [])
        inst_masks.append(f"0x{channel_mask(names):02X}")
        if names:
            counts = [str(ch.chart_buttons(charts[f"{inst}/{d.name}"])) if f"{inst}/{d.name}" in charts else "0"
                      for d in ch.DIFFICULTIES]
            report.append(f"  {inst}: {', '.join(names)} ({', '.join(counts)} notas)")
    nl = ",\n        "
    out.append(
        f"""const Song song_{sd.name} = {{
    .title_hash = 0x{song_hash(sd.title, sd.game):08X}u,
    .title = {c_string(sd.title)},
    .game = {c_string(sd.game)},
    .total_frames = {LEAD_IN + sd.stream_frames},
    .beat_frames = {sd.grid.frames_per_beat},
    .perfect = {{
        {nl.join(perfect_rows)}
    }},
    .chart = {{
        {nl.join(chart_refs)}
    }},
    .stream = SONG_STREAM,
    .stream_len = {len(sd.stream)},
    .sample_count = {sd.sample_count},
    .inst_mask = {{ {", ".join(inst_masks)} }},
}};
"""
    )
    return "\n".join(out), report


def write_song(sd: SongData, charts: dict[str, list[ch.ChartNote]]) -> list[str]:
    """Escribe song.c e import.json. Todo se arma antes de tocar el disco."""
    text, report = render_song_c(sd, charts)
    meta = json.dumps(sd.opts, indent=2, ensure_ascii=False) + "\n"
    new_drums = None
    if sd.drums and dr.load_drums(sd.folder) is None:  # drums.json se genera una vez y luego se conserva (R13.3)
        new_drums = dr.suggest_assignment(dr.drum_groups(sd.notes, sd.drums))
        dr.check_assignment(new_drums)
    sd.folder.mkdir(parents=True, exist_ok=True)
    if new_drums is not None:
        dr.save_drums(sd.folder, new_drums)
    (sd.folder / "song.c").write_text(text, encoding="utf-8", newline="\n")
    (sd.folder / "import.json").write_text(meta, encoding="utf-8", newline="\n")
    return report


def import_song(opts: dict, root: Path = ROOT) -> list[str]:
    """Importa una canción con las opciones de import.json y devuelve las líneas del informe."""
    sd = load_song(opts, root)
    charts = auto_charts(sd)
    warnings = apply_chart_edits(sd, charts)
    report = write_song(sd, charts)
    bpm = 3600 / sd.grid.frames_per_beat
    lines = [f"{sd.folder / 'song.c'}: {sd.title} / {sd.game}",
             f"  {sd.stream_frames / 60:.0f} s, {len(sd.stream)} bytes de música, tempo {bpm:.0f} BPM ({sd.grid.frames_per_beat} cuadros)"]
    lines += report or ["  (ningún instrumento: revisa los canales con `ngband channels`)"]
    lines += [f"  aviso: {u}" for u in sd.unsupported]
    lines += [f"  aviso: {w}" for w in warnings]
    return lines


def reimport_song(name: str, root: Path = ROOT) -> list[str]:
    """Repite la importación con las opciones de import.json, conserva drums.json y aplica edits.json (R14.8)."""
    return import_song(load_import_options(name, root), root)


def describe_channels(path: Path, duration: float | None = None) -> list[str]:
    """Líneas de `ngband channels`: notas y altura de cada canal, y la sugerencia de asignación."""
    try:
        data = vgm.read_vgm(path)
    except OSError as exc:
        raise ImportError_(f"no se pudo leer {path}: {exc}") from exc
    frames = int(duration * 60) if duration else None
    writes = vgm.unrolled_writes(data, frames)
    notes: dict[str, list[ch.Note]] = {c: [] for c in CHANNEL_NAMES}
    for n in nt.extract_notes_from_writes(writes, data.clock):
        notes[n.channel].append(to_chart_note(n))
    hits, samples = adpcma_hits(writes, data.clock)
    notes["adpcma"] = [ch.Note(f, i, ADPCMA_HIT_FRAMES) for f, i in hits]
    stats = summarize(notes)
    lines = []
    for name in CHANNEL_NAMES:
        if name in stats:
            count, median, distinct = stats[name]
            lines.append(f"  {name:6} {count:5d} notas, altura mediana {median:.0f} ({dr.midi_to_name(round(median))}), {distinct} alturas")
        elif name == "adpcma":
            if hits:
                lines.append(f"  {name:6} {len(hits):5d} golpes, {samples} samples")
        elif name == "adpcmb":
            count = adpcmb_count(writes, data.clock)
            if count:
                lines.append(f"  {name:6} {count:5d} golpes")
    guess = auto_assign(notes)
    parts = [f"--{k} {','.join(v)}" for k, v in guess.items()]
    if notes["adpcma"]:
        parts.append(f"--{DRUMS} adpcma")
    lines.append("sugerencia: " + " ".join(parts))
    lines += [f"aviso: {u}" for u in data.unsupported]
    return lines
