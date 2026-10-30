"""Pruebas de songgen.py y de la CLI `ngband` (import-song, channels)."""

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngband_tools import chart as ch  # noqa: E402
from ngband_tools import songgen  # noqa: E402
from ngband_tools.cli import main  # noqa: E402
from ngband_tools.frames import decode_stream, parse_c_array  # noqa: E402

NOTES = 30
NOTE_FRAMES = 30  # 15 con tecla y 15 sin ella


def make_vgm(loop: bool = True) -> bytes:
    """VGM sintético: 30 notas en FM 1 con alturas distintas, una cada 30 cuadros."""
    body = bytearray()
    for i in range(NOTES):
        fnum = 400 + 30 * (i % 7)
        body += bytes((0x58, 0xA5, (4 << 3) | (fnum >> 8), 0x58, 0xA1, fnum & 0xFF, 0x58, 0x28, 0xF1))
        body += bytes((0x62,)) * 1 + bytes((0x61,)) + struct.pack("<H", 735 * 14)  # 15 cuadros con la tecla
        body += bytes((0x58, 0x28, 0x01))
        body += bytes((0x61,)) + struct.pack("<H", 735 * 15)
    body += bytes((0x66,))
    header = bytearray(0x80)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x151)
    struct.pack_into("<I", header, 0x18, NOTES * NOTE_FRAMES * 735)
    if loop:
        struct.pack_into("<I", header, 0x1C, 0x80 - 0x1C)
        struct.pack_into("<I", header, 0x20, NOTES * NOTE_FRAMES * 735)
    struct.pack_into("<I", header, 0x34, 0x80 - 0x34)
    struct.pack_into("<I", header, 0x4C, 8_000_000)
    return bytes(header + body)


@pytest.fixture()
def vgm_file(tmp_path):
    path = tmp_path / "demo.vgm"
    path.write_bytes(make_vgm())
    return path


def test_import_song_writes_song_c_and_import_json(tmp_path, vgm_file):
    opts = {"name": "demo", "source": str(vgm_file), "title": "Demo canción", "game": "Prueba",
            "duration": 40, "guitarra": "fm1"}
    lines = songgen.import_song(opts, root=tmp_path)
    folder = tmp_path / "src" / "songs" / "demo"
    assert (folder / "import.json").is_file()
    assert json.loads((folder / "import.json").read_text(encoding="utf-8")) == opts
    text = (folder / "song.c").read_text(encoding="utf-8")
    assert "const Song song_demo" in text and 'song_demo_name[] = "DEMO CANCION"' in text
    for diff in ("facil", "medio", "dificil", "experto"):
        assert f"guitarra_{diff}[]" in text
    assert any("guitarra" in line for line in lines)
    # Los charts generados se leen de vuelta y son jugables
    chart = ch.chart_from_c(text.split("static const ChartEv guitarra_experto[]")[1].split("};")[0])
    assert chart
    ch.check_playable(chart)


def test_duration_repeats_the_loop(tmp_path, vgm_file):
    # El VGM dura 15 s; con --duration 40 el stream llena exactamente 2400 cuadros
    songgen.import_song({"name": "demo", "source": str(vgm_file), "duration": 40, "guitarra": "fm1"}, root=tmp_path)
    text = (tmp_path / "src" / "songs" / "demo" / "song.c").read_text(encoding="utf-8")
    frames = decode_stream(parse_c_array(text.replace("static const u8", "const unsigned char"), "song_stream"))
    assert len(frames) == 2400
    # cada repetición del bucle (900 cuadros) coincide con la anterior
    assert frames[901:1800] == frames[1:900]
    assert frames[1801:2400] == frames[1:600]
    assert frames[900] == frames[1800]
    assert f".total_frames = {songgen.LEAD_IN + 2400}" in text


def test_invalid_vgm_writes_nothing(tmp_path):
    bad = tmp_path / "bad.vgm"
    bad.write_bytes(b"no soy un vgm")
    with pytest.raises(ValueError):
        songgen.import_song({"name": "bad", "source": str(bad)}, root=tmp_path)
    assert not (tmp_path / "src").exists()


def test_cli_channels(tmp_path, vgm_file, capsys):
    assert main(["channels", str(vgm_file)]) == 0
    out = capsys.readouterr().out
    assert "fm1" in out and "sugerencia:" in out
    assert main(["channels", str(tmp_path / "no_existe.vgm")]) == 1


def test_unknown_channel_is_an_error(tmp_path, vgm_file):
    with pytest.raises(ValueError, match="canal"):
        songgen.import_song({"name": "demo", "source": str(vgm_file), "guitarra": "fm9"}, root=tmp_path)


# --- 4.11: reimport, edits.json, drums.json, errores ---------------------------------------------------

OPTS = {"title": "Demo", "game": "Prueba", "duration": 40, "guitarra": "fm1"}


def _import(tmp_path, vgm_file, **extra):
    opts = {"name": "demo", "source": str(vgm_file), **OPTS, **extra}
    songgen.import_song(opts, root=tmp_path)
    return tmp_path / "src" / "songs" / "demo"


def _chart(folder, label):
    text = (folder / "song.c").read_text(encoding="utf-8")
    return ch.chart_from_c(text.split(f"static const ChartEv {label}[]")[1].split("};")[0])


def test_reimport_is_idempotent_and_applies_edits(tmp_path, vgm_file):
    from ngband_tools import chartedit as ce
    folder = _import(tmp_path, vgm_file)
    first = (folder / "song.c").read_text(encoding="utf-8")
    songgen.reimport_song("demo", root=tmp_path)
    assert (folder / "song.c").read_text(encoding="utf-8") == first
    auto = _chart(folder, "guitarra_facil")
    victim = auto[3].frame
    ce.save_edits(folder, {"guitarra/facil": [{"op": "delete", "frame": victim}]})
    songgen.reimport_song("demo", root=tmp_path)
    edited = _chart(folder, "guitarra_facil")
    assert victim not in {n.frame for n in edited} and len(edited) == len(auto) - 1


def test_orphan_edits_are_skipped_with_warning(tmp_path, vgm_file):
    from ngband_tools import chartedit as ce
    folder = _import(tmp_path, vgm_file)
    first = (folder / "song.c").read_text(encoding="utf-8")
    ce.save_edits(folder, {"guitarra/facil": [{"op": "delete", "frame": 999999}],
                           "bajo/facil": [{"op": "delete", "frame": 1}]})
    lines = songgen.reimport_song("demo", root=tmp_path)
    assert sum("aviso: edits.json" in line for line in lines) == 2
    assert (folder / "song.c").read_text(encoding="utf-8") == first


def test_drums_json_generated_once_and_kept(tmp_path, vgm_file):
    from ngband_tools import drums as dr
    folder = _import(tmp_path, vgm_file, bateria="fm1")
    assert (folder / "drums.json").is_file()
    groups = dr.load_drums(folder)
    key = next(iter(groups))
    groups[key] = {"lane": "tom2", "cymbal": False}
    dr.save_drums(folder, groups)
    saved = (folder / "drums.json").read_text(encoding="utf-8")
    songgen.reimport_song("demo", root=tmp_path)
    assert (folder / "drums.json").read_text(encoding="utf-8") == saved


def test_reimport_errors_write_nothing(tmp_path, vgm_file):
    folder = _import(tmp_path, vgm_file)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    vgm_file.write_bytes(b"roto")
    with pytest.raises(ValueError):
        songgen.reimport_song("demo", root=tmp_path)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    with pytest.raises(ValueError, match="import.json"):
        songgen.reimport_song("no_existe", root=tmp_path)
    assert main(["reimport", "no_existe"]) == 1


def test_vgm_without_ym2610_writes_nothing(tmp_path):
    header = bytearray(0x80)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x151)
    struct.pack_into("<I", header, 0x34, 0x80 - 0x34)
    path = tmp_path / "vacio.vgm"
    path.write_bytes(bytes(header) + bytes((0x66,)))
    with pytest.raises(ValueError, match="YM2610"):
        songgen.import_song({"name": "vacio", "source": str(path)}, root=tmp_path)
    assert not (tmp_path / "src").exists()


def test_perfect_score_matches_judge_multiplier():
    # El Judge sube el combo y luego calcula el Multiplier: el golpe 10 ya vale x2, el 20 x3, el 30 x4
    chart = [ch.ChartNote(10 * i, 1) for i in range(1, 36)]
    expected = 9 * 50 + 10 * 100 + 10 * 150 + 6 * 200
    assert songgen.perfect_score(chart) == expected
    assert songgen.perfect_score([ch.ChartNote(1, 0b11)] * 5) == 9 * 50 + 100  # acorde: 1 Note por botón; la décima ya vale x2


def test_inst_mask_in_song_c(tmp_path, vgm_file):
    folder = _import(tmp_path, vgm_file)
    text = (folder / "song.c").read_text(encoding="utf-8")
    assert ".inst_mask = { 0x01, 0x00, 0x00, 0x00 }" in text
    assert songgen.channel_mask(["fm4", "ssg3", "adpcma"]) == 0b1001000
