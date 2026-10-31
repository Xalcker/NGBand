"""Pruebas del servidor del Chart_Editor (editor.py): ediciones, guardado de la diferencia y HTTP."""

import base64
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_songgen import make_vgm  # noqa: E402

from ngband_tools import editor, songgen  # noqa: E402
from ngband_tools.chart import ChartNote  # noqa: E402
from ngband_tools.chartedit import apply_edits, load_edits  # noqa: E402
from ngband_tools.cli import main  # noqa: E402

KEY = "guitarra/experto"


@pytest.fixture()
def root(tmp_path):
    (tmp_path / "demo.vgm").write_bytes(make_vgm())
    songgen.import_song({"name": "demo", "source": str(tmp_path / "demo.vgm"), "duration": 40, "guitarra": "fm1"},
                        root=tmp_path)
    return tmp_path


@pytest.fixture()
def sd(root):
    return editor.load_song_source("demo", root)


def test_edit_session_ops_undo_redo():
    auto = [ChartNote(100, 1, None, False, False), ChartNote(200, 2, None, False, False)]
    s = editor.EditSession(auto)
    s.add(150, 4)
    s.move(100, 120)
    s.set_flags(200, star=True, end=260)
    s.delete(150)
    edited = s.chart
    assert [n.frame for n in edited] == [120, 200]
    assert edited[1].star and edited[1].end == 260
    assert apply_edits(auto, s.edits()) == edited  # la diferencia guardada reproduce el chart editado
    while s.undo():
        pass
    assert s.chart == auto and s.edits() == []
    while s.redo():
        pass
    assert s.chart == edited
    with pytest.raises(ValueError):
        s.move(120, 200)  # cuadro ocupado
    with pytest.raises(ValueError):
        s.delete(999)


def test_save_writes_only_the_diff(root, sd):
    auto = editor.auto_charts_for(sd)
    charts = {k: list(v) for k, v in auto.items()}
    victim = charts[KEY][3]
    del charts[KEY][3]
    edits = editor.save_edits_from_page(sd, charts)
    assert edits[KEY] == [{"op": "delete", "frame": victim.frame}]
    assert all(not ops for k, ops in edits.items() if k != KEY)
    assert load_edits(sd.folder) == {KEY: edits[KEY]}


def test_save_without_changes_removes_edits_file(root, sd):
    charts = editor.auto_charts_for(sd)
    editor.save_edits_from_page(sd, {**charts, KEY: charts[KEY][1:]})
    assert (sd.folder / "edits.json").exists()
    editor.save_edits_from_page(sd, charts)
    assert not (sd.folder / "edits.json").exists()


def test_unplayable_chart_is_flagged_and_not_saved(root, sd):
    charts = editor.auto_charts_for(sd)
    bad = list(charts[KEY])
    bad[0] = ChartNote(bad[0].frame, 0b00101, None, False, False)  # verde + amarillo
    assert any(p["kind"] == "error" for p in editor.problems_for(KEY, bad))
    with pytest.raises(ValueError):
        editor.save_edits_from_page(sd, {**charts, KEY: bad})
    assert not (sd.folder / "edits.json").exists()


def test_export_regenerates_song_c_with_edits(root, sd):
    charts = editor.auto_charts_for(sd)
    before = (sd.folder / "song.c").read_text(encoding="utf-8")
    msg = editor.export_song(sd, {**charts, KEY: charts[KEY][2:]}, root=root)
    assert "guitarra" in msg
    assert (sd.folder / "song.c").read_text(encoding="utf-8") != before


def test_payload_has_charts_and_channels(sd):
    payload = editor.build_payload(sd)
    assert payload["name"] == "demo" and KEY in payload["charts"]
    assert payload["channelNames"][:4] == ["fm1", "fm2", "fm3", "fm4"]
    assert payload["channels"]["fm1"] and payload["problems"][KEY] is not None
    assert payload["instruments"][0]["name"] == "guitarra"


@pytest.fixture()
def server(root):
    srv = editor.make_server("demo", 0, root)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _post(url, body, headers=None):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_http_state_validate_save(server, root):
    srv, url = server
    assert srv.server_address[0] == "127.0.0.1"
    with urllib.request.urlopen(url + "/api/state") as r:
        state = json.load(r)
    chart = state["charts"][KEY]
    status, data = _post(url + "/api/validate", {"song": "demo", "key": KEY, "chart": chart})
    assert status == 200 and data["problems"] == state["problems"][KEY]
    status, _ = _post(url + "/api/save", {"song": "demo", "charts": {**state["charts"], KEY: chart[1:]}})
    assert status == 200
    assert load_edits(root / "src" / "songs" / "demo")[KEY] == [{"op": "delete", "frame": chart[0]["frame"]}]
    status, data = _post(url + "/api/save", {"song": "otra", "charts": {}})
    assert status == 400


def test_http_rejects_foreign_origin(server):
    _, url = server
    status, _ = _post(url + "/api/close", {}, {"Origin": "http://evil.example"})
    assert status == 403


def test_cli_registers_edit_chart(capsys):
    with pytest.raises(SystemExit):
        main(["edit-chart", "--help"])
    assert "--port" in capsys.readouterr().out
    assert main(["edit-chart", "no_existe", "--no-browser"]) == 1


# --- Interfaz web y Escuchar (19.2) -----------------------------------------------------------------------


def _get(url):
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8")


def _inline_scripts(page):
    return re.findall(r"<script>(.*?)</script>", page, re.S)


def test_editor_page_is_complete(server):
    _, url = server
    page = _get(url + "/")
    assert not re.findall(r"__(?:DATA|MENU|NGPLAYER)__", page)  # sin marcadores sin reemplazar
    assert "const DATA = {" in page and "const NgPlayer" in page and "filemenu" in page
    # Los canales llegan en el perfil (JSON) de la página compartida de bandcore
    for channel in ("ssg3", "adpcma", "adpcmb"):
        assert f'"id":"{channel}"' in page
    assert '"id":"dac"' not in page and "GenPlayer" not in page and "genband" not in page.lower()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está instalado")
def test_page_scripts_are_valid_javascript(server, tmp_path):
    _, url = server
    for name, page in (("editor", _get(url + "/")),):
        scripts = _inline_scripts(page)
        assert len(scripts) >= 4
        for i, code in enumerate(scripts):
            path = tmp_path / f"{name}{i}.js"
            path.write_text(code, encoding="utf-8")
            done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            assert done.returncode == 0, f"{name} script {i}: {done.stderr}"


def test_home_page_without_song(root):
    srv = editor.make_server(None, 0, root)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        page = _get(f"http://127.0.0.1:{srv.server_address[1]}/")
        assert '"home":true' in page and "dlgOpen" in page and "No hay ninguna canción abierta" in page
        # Sin importador en el editor: el perfil lo dice y el menú no ofrece «Nueva canción»
        assert '"import":null' in page and "NgPlayer" not in page
    finally:
        srv.shutdown()
        srv.server_close()


def test_player_payload_is_the_rom_stream(server, sd):
    _, url = server
    player = json.loads(_get(url + "/api/player"))
    assert base64.b64decode(player["stream"]) == sd.stream
    assert player["frames"] == sd.stream_frames and player["clock"] == 8_000_000
    assert base64.b64decode(player["adpcma"]) == b"" and base64.b64decode(player["adpcmb"]) == b""
