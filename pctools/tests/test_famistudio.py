"""Pruebas de la conversión de FamiStudio a VGM del YM2610 (famistudio.py)."""
import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ngband_tools import famistudio as fs  # noqa: E402
from ngband_tools import notes as nt  # noqa: E402
from ngband_tools import songgen, vgm  # noqa: E402
from ngband_tools.ym2610 import fm_pitch  # noqa: E402

PATTERNS = 8  # patrones de 16 filas x 6 cuadros = 96 cuadros cada uno


def project_text(loop_point: int = 0) -> str:
    """Un proyecto de texto de FamiStudio: melodías en los tres canales, ruido y DPCM."""
    lines = [
        'Project Version="4.5.3" TempoMode="FamiStudio" Name="Prueba" Author="NESBand"',
        '\tInstrument Name="Guitarra"',
        '\t\tEnvelope Type="Volume" Length="4" Values="15,12,8,4"',
        '\tInstrument Name="Teclado"',
        '\tInstrument Name="Bajo"',
        '\tInstrument Name="Bombo"',
        '\t\tEnvelope Type="Volume" Length="3" Values="15,8,0"',
        '\tInstrument Name="Tarola"',
        '\tInstrument Name="Platillo"',
        '\tInstrument Name="Percusion"',
        '\t\tDPCMMapping Note="C1" Sample="Bombo" Pitch="12" Loop="False" Bank="0"',
        '\t\tDPCMMapping Note="C#1" Sample="Tarola" Pitch="12" Loop="False" Bank="0"',
        f'\tSong Name="Cancion" Length="{PATTERNS}" LoopPoint="{loop_point}" PatternLength="16" BeatLength="4" NoteLength="6"',
    ]

    def channel(kind: str, notes: list[str]) -> None:
        lines.append(f'\t\tChannel Type="{kind}"')
        lines.append('\t\t\tPattern Name="P"')
        lines.extend(f"\t\t\t\t{n}" for n in notes)
        lines.extend(f'\t\t\tPatternInstance Time="{i}" Pattern="P"' for i in range(PATTERNS))

    def note(time: int, value: str, duration: int, inst: str) -> str:
        return f'Note Time="{time}" Value="{value}" Duration="{duration}" Instrument="{inst}"'

    scale = ["C5", "D5", "E5", "G5", "A5", "G5", "E5", "D5"]
    channel("Square1", [note(12 * i, scale[i], 11, "Guitarra") for i in range(8)])
    channel("Square2", [note(24 * i, n, 23, "Teclado") for i, n in enumerate(["E4", "G4", "A4", "C5"])])
    channel("Triangle", [note(24 * i, n, 23, "Bajo") for i, n in enumerate(["C3", "G2", "A2", "E3"])])
    channel("Noise", [note(0, "A#2", 8, "Bombo"), note(24, "D#3", 8, "Tarola"), note(36, "G#3", 4, "Platillo"),
                      note(48, "A#2", 8, "Bombo"), note(72, "D#3", 8, "Tarola"), note(84, "G#3", 4, "Platillo")])
    channel("DPCM", [note(6, "C1", 4, "Percusion"), note(60, "C#1", 4, "Percusion")])
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def vgm_bytes():
    return fs.convert_text(project_text())


def test_output_is_a_ym2610_vgm_readable_by_vgm_py(vgm_bytes):
    data = vgm.parse_vgm(vgm_bytes)
    assert data.clock == 8_000_000
    assert data.unsupported == []
    assert data.total_samples == PATTERNS * 96 * vgm.SAMPLES_PER_FRAME
    assert data.loop_sample == 0 and data.loop_samples == data.total_samples
    assert data.tags["title"] == "Cancion" and data.tags["author"] == "NESBand"


def test_channels_map_to_fm_and_drums_to_fm4_and_ssg1(vgm_bytes):
    data = vgm.parse_vgm(vgm_bytes)
    found = nt.extract_notes(data)
    by_channel = {c: [n for n in found if n.channel == c] for c in ("fm1", "fm2", "fm3", "fm4", "ssg1")}
    assert not [n for n in found if n.channel in ("ssg2", "ssg3")]   # el SSG 3 es de los efectos
    # pulso 1: 8 notas por patrón; pulso 2 y triángulo: 4; la melodía coincide con la escala escrita
    assert len(by_channel["fm1"]) == 8 * PATTERNS
    assert [n.midi for n in by_channel["fm1"][:8]] == [72, 74, 76, 79, 81, 79, 76, 74]
    assert len(by_channel["fm2"]) == 4 * PATTERNS and len(by_channel["fm3"]) == 4 * PATTERNS
    assert [n.midi for n in by_channel["fm3"][:4]] == [48, 43, 45, 52]
    # bombo (ruido y DPCM) en el FM 4: arranca en G3 y baja con el barrido
    kicks = [n for n in by_channel["fm4"] if round(n.midi) == fs.DRUM_PITCH["bombo"]]
    assert [n.start for n in kicks[:3]] == [0, 6, 48]
    # tarola y platillo en el ruido del SSG 1, cada uno con su tono (para agrupar los golpes)
    noise = [(n.start, round(n.midi)) for n in by_channel["ssg1"] if n.start < 96]
    assert noise == [(24, fs.DRUM_PITCH["tarola"]), (36, fs.DRUM_PITCH["platillo"]), (60, fs.DRUM_PITCH["tarola"]),
                     (72, fs.DRUM_PITCH["tarola"]), (84, fs.DRUM_PITCH["platillo"])]
    # la nota empieza en el cuadro que dice el proyecto (pulso 1: Time 12 -> cuadro 12)
    assert by_channel["fm1"][1].start == 12


def test_patch_by_instrument_name_and_channel_fallback():
    assert fs.patch_for("Guitarra", "Square2").name == "guitarra"
    assert fs.patch_for("Teclado", "Square2").name == "organo"      # como en GENBand
    assert fs.patch_for("Surf", "Square1").name == "limpia"
    assert fs.patch_for("Órgano", "Square1").name == "organo"
    assert fs.patch_for("Bajo", "Square1").name == "bajo"
    assert fs.patch_for("Desconocido", "Square1").name == "guitarra"
    assert fs.patch_for(None, "Square2").name == "organo"
    assert fs.patch_for("Nada", "Triangle").name == "bajo"


def test_every_instrument_of_the_songs_has_a_sound():
    """Los instrumentos melódicos de audio/*.txt tienen nombre exacto en INSTRUMENT_PATCH."""
    root = Path(__file__).resolve().parents[2] / "audio"
    for path in root.glob("*.txt"):
        if path.stem == "efectos":
            continue
        project = fs.parse_text(path.read_text(encoding="utf-8"))
        for song in project.songs:
            for kind in fs.MELODIC:
                for note in song.notes.get(kind, []):
                    assert note.instrument in fs.INSTRUMENT_PATCH, (path.name, note.instrument)


def test_volume_is_fixed_per_instrument(vgm_bytes):
    """El volumen máximo de la envolvente del NES fija la atenuación una vez; el FM hace su propia caída."""
    assert fs.volume_extra(13) == 0 and fs.volume_extra(15) == 0 and fs.volume_extra(9) == 6
    data = vgm.parse_vgm(vgm_bytes)
    # FM 1 = puerto A, desplazamiento 1; portadores del algoritmo 4: operadores 2 y 4 (+8 y +12)
    tl = {w.value for w in data.writes if w.chip == "ym0" and w.reg == 0x40 + 1 + 8}
    assert tl == {fs.PATCHES["guitarra"].ops[1].tl + fs.volume_extra(15)}
    # el teclado va 2 pasos abajo (CHANNEL_MIX) y los moduladores no cambian
    tl2 = {w.value for w in data.writes if w.chip == "ym0" and w.reg == 0x40 + 2 + 12}
    assert tl2 == {fs.PATCHES["organo"].ops[3].tl + fs.CHANNEL_MIX[1]}
    mod = {w.value for w in data.writes if w.chip == "ym0" and w.reg == 0x40 + 1}
    assert mod == {fs.PATCHES["guitarra"].ops[0].tl}


def test_triangle_ignores_volume_envelope():
    text = project_text().replace('\tInstrument Name="Bajo"', '\tInstrument Name="Bajo"\n\t\tEnvelope Type="Volume" Length="2" Values="3,1"')
    data = vgm.parse_vgm(fs.convert_text(text))
    # FM 3 = puerto B, desplazamiento 1; algoritmo 0: portador = operador 4 (+12)
    values = {w.value for w in data.writes if w.chip == "ym1" and w.reg == 0x40 + 1 + 12}
    assert values == {fs.PATCHES["bajo"].ops[3].tl}


def test_ssg_volume_maps_psg_steps():
    assert fs.ssg_volume(15) == 15 and fs.ssg_volume(0) == 0
    values = [fs.ssg_volume(v) for v in range(1, 16)]
    assert values == sorted(values) and min(values) >= 1


def test_loop_point_sets_loop_offset():
    data = vgm.parse_vgm(fs.convert_text(project_text(loop_point=2)))
    assert vgm.frame_of(data.loop_sample) == 2 * 96
    assert data.loop_samples == (PATTERNS - 2) * 96 * vgm.SAMPLES_PER_FRAME


def test_keys_are_released_at_the_end(vgm_bytes):
    data = vgm.parse_vgm(vgm_bytes)
    tail = [(w.reg, w.value) for w in data.writes[-5:]]
    assert tail == [(0x28, 1), (0x28, 2), (0x28, 5), (0x28, 6), (0x08, 0)]


def test_song_is_importable_by_songgen(tmp_path):
    source = tmp_path / "prueba.vgm"
    source.write_bytes(fs.convert_text(project_text()))
    opts = {"name": "prueba", "source": str(source), "guitarra": "fm1", "teclado": "fm2", "bajo": "fm3", "bateria": "fm4,ssg1"}
    lines = songgen.import_song(opts, root=tmp_path)
    assert isinstance(lines, list)
    text = (tmp_path / "src" / "songs" / "prueba" / "song.c").read_text(encoding="utf-8")
    assert "const Song song_prueba" in text


def test_convert_file_and_cli(tmp_path):
    src = tmp_path / "p.txt"
    src.write_text(project_text(), encoding="utf-8")
    out = tmp_path / "out" / "p.vgm"
    assert fs.main([str(src), str(out)]) == 0
    assert vgm.read_vgm(out).total_samples > 0
    assert fs.main([str(src), str(out), "--song", "5"]) == 1


def test_tempo_mode_famitracker_is_rejected():
    with pytest.raises(ValueError):
        fs.parse_text('Project Version="4.5.3" TempoMode="FamiTracker"\n')


@given(st.integers(min_value=24, max_value=108))
def test_fm_freq_round_trips_pitch(pitch):
    """El F-number y el bloque elegidos suenan en la altura pedida (a menos de 3 centésimas de semitono... 0,1)."""
    block, fnum = fs.fm_freq(pitch)
    assert 0 <= block <= 7 and 1 <= fnum <= 2047
    assert abs(fm_pitch(block, fnum) - pitch) < 0.1
