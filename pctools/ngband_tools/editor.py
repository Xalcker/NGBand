"""Servidor del Chart_Editor (R16): `ngband edit-chart [canción]`, en 127.0.0.1.

Es el editor de NESBand y GENBand con los canales del YM2610 (FM 1-4, SSG 1-3, ADPCM-A y ADPCM-B). Los
datos salen de la misma tubería que `import-song` (songgen.py: load_song, auto_charts, apply_chart_edits);
encima van las ediciones de edits.json (chartedit.py). Guardar escribe solo la diferencia contra el Chart
automático en edits.json (R16.4) y la asignación de la batería en drums.json; Exportar además repite la
importación (reimport), que regenera song.c con las ediciones. Las Notes que `check_playable` rechazaría se
marcan como errores (R16.8).

La interfaz web son editor.html, home.html y menu.html (plantillas con __DATA__, __MENU__ y, en el editor,
__NGPLAYER__) y Escuchar es ngplayer.js: un emulador del YM2610 en JavaScript que toca el mismo Frame_Stream que la
ROM (R16.6). Si falta una plantilla, la página explica que no está y `/api/state` entrega los datos.
"""

from __future__ import annotations

import base64
import re
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

from bandcore import editor as bandeditor
from bandcore.editor import server as bandserver

from . import drums as dr
from . import songgen as sg
from . import vgm as vgmlib
from .chart import DIFFICULTIES, ChartNote, chart_size
from .chartedit import (
    EDITS_FILE,
    chart_problems,
    diff_charts,
    save_edits,
    validate_chart,
)

# Las páginas (editor.html, home.html y el menú Archivo) son las de bandcore, compartidas con NESBand, GBBand y
# GENBand; aquí van el perfil de la Neo Geo y su reproductor
HTML_PATH = bandeditor.EDITOR_HTML
HOME_PATH = bandeditor.HOME_HTML  # la página sin canción abierta
PLAYER_PATH = Path(__file__).with_name("ngplayer.js")  # Escuchar: el YM2610 en JavaScript

PROFILE = {
    "game": "NGBand",
    "cli": "ngband",
    "pads": ["←", "↓", "→", "B", "C"],
    "channels": [
        {"id": "fm1", "label": "FM 1", "color": "#58d0ff", "discrete": False},
        {"id": "fm2", "label": "FM 2", "color": "#b58cff", "discrete": False},
        {"id": "fm3", "label": "FM 3", "color": "#6be88a", "discrete": False},
        {"id": "fm4", "label": "FM 4", "color": "#4fb8e8", "discrete": False},
        {"id": "ssg1", "label": "SSG 1", "color": "#e8e070", "discrete": False},
        {"id": "ssg2", "label": "SSG 2", "color": "#d0c860", "discrete": False},
        {"id": "ssg3", "label": "SSG 3", "color": "#b8b050", "discrete": False},
        {"id": "adpcma", "label": "ADPCM-A", "color": "#ff6b5e", "discrete": True, "pitchLabel": "sample"},
        {"id": "adpcmb", "label": "ADPCM-B", "color": "#ffb45e", "discrete": True},
    ],
    "drumInstrument": False,  # los golpes del ADPCM no traen nombre de instrumento
    "exportLabel": "Exportar song.c",
    "exportTitle": "Guarda y vuelve a importar la canción: su song.c sale con los charts editados",
    "playerTitle": "Toca la canción con el YM2610 emulado (FM, SSG y ADPCM)",
    "import": None,  # se importa con ngband import-song
}
# ngplayer.js toca el Frame_Stream (en base64) con las ROM de samples ADPCM-A y ADPCM-B
_PLAYER_ADAPTER = """
window.BandPlayer = {
  FPS: NgPlayer.FPS,
  render(player, data, opts) {
    const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return NgPlayer.render(bytes(player.stream), player.frames, {
      ...opts, clock: player.clock, adpcmaRom: bytes(player.adpcma), adpcmbRom: bytes(player.adpcmb),
    });
  },
};
"""

SOURCE_SUFFIXES = (".vgm", ".vgz")
SONG_NAME = re.compile(r"[a-z][a-z0-9_]*")


# --- Ediciones con deshacer / rehacer ---------------------------------------------------------------------


class EditSession:
    """Un Chart que se edita con add / move / delete / set_flags, con deshacer y rehacer.

    Es la lógica que la página aplica en el navegador, aquí sin interfaz para poder probarla. Cada edición
    guarda una copia del Chart anterior; una edición nueva descarta lo que se podía rehacer."""

    def __init__(self, auto: list[ChartNote], edited: list[ChartNote] | None = None):
        self.auto = list(auto)
        self.notes: dict[int, ChartNote] = {n.frame: n for n in (self.auto if edited is None else edited)}
        self._undo: list[dict[int, ChartNote]] = []
        self._redo: list[dict[int, ChartNote]] = []

    @property
    def chart(self) -> list[ChartNote]:
        return sorted(self.notes.values(), key=lambda n: n.frame)

    def _push(self) -> None:
        self._undo.append(dict(self.notes))
        self._redo.clear()

    def add(self, frame: int, mask: int, end: int | None = None, star: bool = False, cymbal: bool = False) -> None:
        if frame < 0 or not 0 < mask <= 0x1F:
            raise ValueError(f"nota inválida: cuadro {frame}, máscara {mask}")
        self._push()
        self.notes[frame] = ChartNote(frame, mask, end, star, cymbal)

    def move(self, frame: int, new_frame: int) -> None:
        if frame not in self.notes:
            raise ValueError(f"no hay nota en el cuadro {frame}")
        if new_frame < 0 or (new_frame != frame and new_frame in self.notes):
            raise ValueError(f"no se puede mover al cuadro {new_frame}")
        note = self.notes[frame]
        end = None if note.end is None else note.end + (new_frame - frame)  # la cola se mueve con la nota
        self._push()
        del self.notes[frame]
        self.notes[new_frame] = replace(note, frame=new_frame, end=end)

    def delete(self, frame: int) -> None:
        if frame not in self.notes:
            raise ValueError(f"no hay nota en el cuadro {frame}")
        self._push()
        del self.notes[frame]

    def set_flags(self, frame: int, **changes) -> None:
        """Cambia mask, end, star o cymbal de la nota del cuadro `frame`."""
        if frame not in self.notes:
            raise ValueError(f"no hay nota en el cuadro {frame}")
        unknown = set(changes) - {"mask", "end", "star", "cymbal"}
        if unknown:
            raise ValueError(f"campos desconocidos: {sorted(unknown)}")
        note = replace(self.notes[frame], **changes)
        if not 0 < note.mask <= 0x1F:
            raise ValueError(f"máscara inválida: {note.mask}")
        self._push()
        self.notes[frame] = note

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(dict(self.notes))
        self.notes = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(dict(self.notes))
        self.notes = self._redo.pop()
        return True

    def edits(self) -> list[dict]:
        """La diferencia contra el Chart automático: lo único que va a edits.json."""
        return diff_charts(self.auto, self.chart)


# --- Datos de la canción ----------------------------------------------------------------------------------


def chart_json(chart: list[ChartNote]) -> list[dict]:
    return [{"frame": n.frame, "mask": n.mask, "end": n.end, "star": n.star, "cymbal": n.cymbal} for n in chart]


def lanes_for(key: str) -> int:
    """Carriles de la dificultad de un chart ("guitarra/facil" -> 3)."""
    difficulty = key.split("/")[1]
    return next(d.lanes for d in DIFFICULTIES if d.name == difficulty)


def problems_for(key: str, chart: list[ChartNote]) -> list[dict]:
    """Errores y avisos de un chart; los "error" son lo que check_playable / el generador rechazan (R16.8).
    (En la batería todos los pads valen en todas las dificultades.)"""
    drums = key.startswith(sg.DRUMS + "/")
    return chart_problems(chart, 5 if drums else lanes_for(key), drums)


def auto_charts_for(sd: sg.SongData, assignment: dict | None = None) -> dict[str, list[ChartNote]]:
    """Los Charts automáticos; con `assignment` la batería se arma con esos papeles en vez de los de drums.json."""
    charts = sg.auto_charts(sd)
    if assignment is not None:
        for key in [k for k in charts if k.startswith(sg.DRUMS + "/")]:
            del charts[key]
        hits = dr.drum_hits(sd.notes, sd.drums, assignment) if sd.drums else []
        if hits:
            for diff in DIFFICULTIES:
                charts[f"{sg.DRUMS}/{diff.name}"] = dr.build_drum_chart(hits, diff.name, sd.grid, sg.LEAD_IN)
    return charts


def edited_charts(sd: sg.SongData, auto: dict[str, list[ChartNote]]) -> tuple[dict[str, list[ChartNote]], list[str]]:
    charts = {key: list(chart) for key, chart in auto.items()}
    warnings = sg.apply_chart_edits(sd, charts)
    return charts, warnings


def drums_payload(sd: sg.SongData, assignment: dict | None, suggested: dict | None) -> dict:
    return {
        "groups": [{"key": g.key, "channel": g.channel, "tone": g.tone, "count": g.count,
                    "avgDuration": round(g.avg_duration, 1)}
                   for g in (dr.drum_groups(sd.notes, sd.drums) if sd.drums else [])],
        "assignment": assignment or {},
        "suggested": suggested or {},
        "roles": [{"id": role, "label": dr.ROLE_LABELS[role], "lane": dr.ROLE_LANE[role]} for role in dr.ROLES],
    }


def build_payload(sd: sg.SongData) -> dict:
    """Todo lo que la página necesita, como JSON."""
    lead_in = sg.LEAD_IN
    assignment = sg.drum_assignment(sd)
    suggested = dr.suggest_assignment(dr.drum_groups(sd.notes, sd.drums)) if sd.drums else None
    auto = auto_charts_for(sd)
    charts, warnings = edited_charts(sd, auto)
    channels = {name: [[lead_in + n.frame, n.pitch, n.duration] for n in ns] for name, ns in sd.notes.items()}
    instruments = []
    for name, _ in sg.INSTRUMENTS:
        if any(k.startswith(name + "/") for k in charts):
            instruments.append({"name": name, "channel": ", ".join(sd.assign[name])})
    if any(k.startswith(sg.DRUMS + "/") for k in charts):
        instruments.append({"name": sg.DRUMS, "channel": ", ".join(sd.drums)})
    return {
        "name": sd.name,
        "title": sd.title,
        "game": sd.game,
        "leadIn": lead_in,
        "endFrame": lead_in + sd.stream_frames,
        "framesPerBeat": sd.grid.frames_per_beat,
        "firstBeat": lead_in + sd.grid.first_beat,
        "channelNames": sg.CHANNEL_NAMES,
        # [cuadro, altura, duración] por canal; los cuadros ya cuentan la entrada de la autopista
        "channels": channels,
        "instruments": instruments,
        "difficulties": [{"name": d.name, "lanes": d.lanes} for d in DIFFICULTIES],
        "charts": {key: chart_json(chart) for key, chart in charts.items()},
        "auto": {key: chart_json(chart) for key, chart in auto.items()},
        "problems": {key: problems_for(key, chart) for key, chart in charts.items()},
        "warnings": warnings,
        "chartBytes": sum(chart_size(chart) for chart in charts.values()),
        "drums": drums_payload(sd, assignment, suggested),
        "editable": False,
    }


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def sample_roms(sd: sg.SongData) -> tuple[bytes, bytes, int]:
    """Las ROM de samples ADPCM-A y ADPCM-B del VGM de la canción y el reloj del YM2610. Escuchar las necesita
    porque el Frame_Stream solo trae los registros, no los datos. Sin VGM legible, vacías (esos canales callan)."""
    source = Path(sd.opts["source"])
    path = source if source.is_absolute() else sd.folder.parents[2] / source
    try:
        data = vgmlib.read_vgm(path)
    except (OSError, ValueError):
        return b"", b"", vgmlib.YM_CLOCK_DEFAULT
    # Los ceros del final no suenan distinto de no tener datos: se recortan para no mandar la ROM entera
    return data.rom("adpcma").rstrip(b"\0"), data.rom("adpcmb").rstrip(b"\0"), data.clock


def player_payload(sd: sg.SongData) -> dict:
    """Lo que Escuchar necesita: el Frame_Stream (el mismo que va en song.c), el reloj del chip y las ROM de samples."""
    rom_a, rom_b, clock = sample_roms(sd)
    return {"stream": _b64(sd.stream), "frames": sd.stream_frames, "clock": clock,
            "adpcma": _b64(rom_a), "adpcmb": _b64(rom_b)}


def drums_response(sd: sg.SongData, assignment: dict) -> dict:
    """Otra asignación de papeles: los Charts de batería se rehacen al instante (con las ediciones ya guardadas
    encima), sin tocar el disco."""
    dr.check_assignment(assignment)
    auto = {k: v for k, v in auto_charts_for(sd, assignment).items() if k.startswith(sg.DRUMS + "/")}
    charts, warnings = edited_charts(sd, auto)
    charts = {k: v for k, v in charts.items() if k.startswith(sg.DRUMS + "/")}
    return {
        "charts": {k: chart_json(c) for k, c in charts.items()},
        "auto": {k: chart_json(c) for k, c in auto.items()},
        "problems": {k: problems_for(k, c) for k, c in charts.items()},
        "warnings": [w for w in warnings if f"{sg.DRUMS}/" in w],
    }


def save_edits_from_page(sd: sg.SongData, charts: dict[str, list[ChartNote]],
                         assignment: dict | None = None) -> dict[str, list[dict]]:
    """Guarda en edits.json solo lo que difiere de los Charts automáticos (y en drums.json la asignación de la
    batería, si la manda la página). Falla sin escribir nada si algún Chart no se puede tocar."""
    if assignment is not None:
        dr.check_assignment(assignment)
    auto = auto_charts_for(sd, assignment)
    if set(charts) != set(auto):
        raise ValueError(f"faltan o sobran charts: se esperaban {sorted(auto)}")
    edits = {}
    for key, chart in charts.items():
        validate_chart(key, chart)
        edits[key] = diff_charts(auto[key], chart)
    if assignment is None and dr.load_drums(sd.folder) is None and any(
            ops for key, ops in edits.items() if key.startswith(sg.DRUMS + "/")):
        assignment = sg.drum_assignment(sd)   # las ediciones de la batería van atadas a su asignación
    sd.folder.mkdir(parents=True, exist_ok=True)
    if assignment is not None:
        dr.save_drums(sd.folder, assignment)
    save_edits(sd.folder, edits)
    return edits


def export_song(sd: sg.SongData, charts: dict[str, list[ChartNote]], assignment: dict | None = None,
                root: Path = sg.ROOT) -> str:
    """Guarda las ediciones y repite la importación: song.c sale con los Charts editados."""
    save_edits_from_page(sd, charts, assignment)
    lines = sg.reimport_song(sd.name, root)
    return "\n".join(lines)


# --- Canciones disponibles --------------------------------------------------------------------------------


def load_song_source(name: str, root: Path = sg.ROOT) -> sg.SongData:
    if not SONG_NAME.fullmatch(name) or not (root / "src" / "songs" / name / "import.json").exists():
        raise ValueError(f"{name} no tiene import.json: impórtala con import-song (o elige una de src/songs/)")
    return sg.load_song(sg.load_import_options(name, root), root)


def list_songs(root: Path = sg.ROOT) -> list[dict]:
    songs = []
    for options in sorted((root / "src" / "songs").glob("*/import.json")):
        song_c = options.parent / "song.c"
        text = song_c.read_text(encoding="utf-8") if song_c.exists() else ""
        title = re.search(r"/\* TITULO: (.*) \*/", text)
        game = re.search(r'\.game = "([^"]*)"', text)
        songs.append({
            "name": options.parent.name,
            "title": title.group(1) if title else options.parent.name,
            "game": game.group(1) if game else "",
            "edited": (options.parent / EDITS_FILE).exists(),
        })
    return songs


# --- HTTP: el servidor de bandcore, con lo propio de la Neo Geo --------------------------------------------


def render_page(payload: dict, template: Path = HTML_PATH) -> str:
    """La página del editor de bandcore con el perfil de la Neo Geo."""
    return Game().render(payload, template)


class Game(bandserver.EditorGame):
    """Lo propio de NGBand para el servidor del editor. `root` es la raíz del proyecto (las pruebas usan otra)."""

    profile = PROFILE

    def __init__(self, root: Path = sg.ROOT):
        self.root = root

    def player_js(self) -> str:
        return PLAYER_PATH.read_text(encoding="utf-8") + _PLAYER_ADAPTER

    def open(self, name: str) -> sg.SongData:
        return load_song_source(name, self.root)

    def payload(self, sd: sg.SongData) -> dict:
        return build_payload(sd)

    def player(self, sd: sg.SongData) -> dict:
        return player_payload(sd)

    def problems(self, key: str, chart: list[ChartNote]) -> list[dict]:
        return problems_for(key, chart)

    def drums(self, sd: sg.SongData, assignment: dict) -> dict:
        return drums_response(sd, assignment)

    def save(self, sd: sg.SongData, charts: dict, assignment: dict | None) -> dict:
        return save_edits_from_page(sd, charts, assignment)

    def export(self, sd: sg.SongData, charts: dict, assignment: dict | None) -> tuple[str, sg.SongData]:
        return export_song(sd, charts, assignment, self.root), sd

    def songs(self) -> list[dict]:
        return list_songs(self.root)


Handler = bandserver.Handler


class App(bandserver.App):
    """La canción abierta (o ninguna) del servidor; `sd` es la canción (`song` en bandcore)."""

    def __init__(self, sd: sg.SongData | None = None, root: Path = sg.ROOT):
        super().__init__(Game(root), sd)
        self.root = root

    @property
    def sd(self) -> sg.SongData | None:
        return self.song

    @sd.setter
    def sd(self, value: sg.SongData | None) -> None:
        self.song = value


def open_song(app: App, name: str) -> None:
    app.song = app.game.open(name)


def make_server(name: str | None, port: int = 0, root: Path = sg.ROOT) -> ThreadingHTTPServer:
    """El servidor, ya ligado a 127.0.0.1 (nunca a otra interfaz, R16.1)."""
    return bandserver.make_server(App(load_song_source(name, root) if name else None, root), port)


def serve(name: str | None, port: int, open_browser: bool, root: Path = sg.ROOT) -> None:
    bandserver.serve(App(load_song_source(name, root) if name else None, root), port, open_browser)
