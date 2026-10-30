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
import json
import re
import threading
import webbrowser
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import drums as dr
from . import songgen as sg
from . import vgm as vgmlib
from .chart import DIFFICULTIES, ChartNote, chart_size
from .chartedit import (
    EDITS_FILE,
    chart_from_json,
    chart_problems,
    diff_charts,
    save_edits,
    validate_chart,
)

HTML_PATH = Path(__file__).with_name("editor.html")
HOME_PATH = Path(__file__).with_name("home.html")  # la página sin canción abierta
MENU_PATH = Path(__file__).with_name("menu.html")  # el menú Archivo, compartido por las dos
PLAYER_PATH = Path(__file__).with_name("ngplayer.js")  # Escuchar: el YM2610 en JavaScript

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


class App:
    """La canción abierta (o ninguna) del servidor. Un candado evita que dos acciones se pisen."""

    def __init__(self, sd: sg.SongData | None = None, root: Path = sg.ROOT):
        self.sd = sd
        self.root = root
        self.lock = threading.RLock()


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


def open_song(app: App, name: str) -> None:
    app.sd = load_song_source(name, app.root)


# --- HTTP -------------------------------------------------------------------------------------------------


def render_page(payload: dict, template: Path = HTML_PATH) -> str:
    if not template.exists():
        return ("<!doctype html><meta charset=utf-8><title>Editor de charts</title>"
                f"<p>Falta la plantilla {template.name} (interfaz web). "
                "Los datos están en <a href=/api/state>/api/state</a>.</p>")
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    menu = MENU_PATH.read_text(encoding="utf-8") if MENU_PATH.exists() else ""
    player = PLAYER_PATH.read_text(encoding="utf-8") if PLAYER_PATH.exists() else ""
    page = template.read_text(encoding="utf-8")
    # (los datos van al final: así nada de lo insertado antes puede contener otro marcador)
    return page.replace("__NGPLAYER__", player, 1).replace("__MENU__", menu, 1).replace("__DATA__", data, 1)


class Handler(BaseHTTPRequestHandler):
    app: App  # lo fija serve()

    def log_message(self, format, *args):  # sin ruido en la terminal
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/json")

    def _need_song(self) -> sg.SongData:
        if self.app.sd is None:
            raise ValueError("no hay canción abierta")
        return self.app.sd

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            with self.app.lock:
                if path == "/":
                    if self.app.sd is None:
                        page = render_page({"home": True}, HOME_PATH)
                    else:
                        page = render_page({**build_payload(self.app.sd), "editable": True, "player": True})
                    self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/api/state":
                    self._json(200, {**build_payload(self._need_song()), "editable": True})
                elif path == "/api/player":
                    self._json(200, player_payload(self._need_song()))
                elif path == "/api/songs":
                    self._json(200, {"songs": list_songs(self.app.root)})
                else:
                    self._send(404, b"no encontrado", "text/plain; charset=utf-8")
        except (ValueError, KeyError) as error:
            self._json(400, {"error": str(error)})

    def do_POST(self) -> None:
        # Solo la propia página: otro origen (una web cualquiera) no puede escribir en el proyecto
        if self.headers.get("Origin") not in (None, f"http://{self.headers.get('Host')}"):
            self._json(403, {"error": "origen no permitido"})
            return
        app = self.app
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("cuerpo inválido")
            with app.lock:
                if self.path == "/api/open":
                    open_song(app, str(body.get("name", "")))
                    self._json(200, {"message": f"abierta {app.sd.name}"})
                elif self.path == "/api/close":
                    app.sd = None
                    self._json(200, {"message": "cerrada"})
                elif self.path in ("/api/validate", "/api/save", "/api/export", "/api/drums"):
                    sd = self._need_song()
                    if body.get("song") != sd.name:
                        raise ValueError("la canción de esta página ya no es la abierta: recarga la página")
                    if self.path == "/api/validate":
                        self._json(200, {"problems": problems_for(body["key"], chart_from_json(body["chart"]))})
                    elif self.path == "/api/drums":
                        self._json(200, drums_response(sd, body["assignment"]))
                    else:
                        charts = {key: chart_from_json(items) for key, items in body["charts"].items()}
                        assignment = body.get("drums")
                        if self.path == "/api/save":
                            edits = save_edits_from_page(sd, charts, assignment)
                            self._json(200, {"message": f"guardado ({sum(len(o) for o in edits.values())} ediciones)"})
                        else:
                            self._json(200, {"message": export_song(sd, charts, assignment, app.root)})
                else:
                    self._json(404, {"error": "no encontrado"})
        except (ValueError, KeyError, TypeError) as error:
            self._json(400, {"error": str(error)})


def make_server(name: str | None, port: int = 0, root: Path = sg.ROOT) -> ThreadingHTTPServer:
    """El servidor, ya ligado a 127.0.0.1 (nunca a otra interfaz, R16.1)."""
    app = App(load_song_source(name, root) if name else None, root)
    return ThreadingHTTPServer(("127.0.0.1", port), type("Bound", (Handler,), {"app": app}))


def serve(name: str | None, port: int, open_browser: bool, root: Path = sg.ROOT) -> None:
    server = make_server(name, port, root)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Editor de charts{f' de {name!r}' if name else ''}: {url}  (Ctrl+C para cerrar)")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
