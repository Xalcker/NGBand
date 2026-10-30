"""Pruebas de los revisores del Test_Harness de MAME (tests/check_result.py y tests/check_human.py) con
resultados de muestra: sin MAME ni ROM se comprueba que cada criterio de R17 detecta lo que debe."""
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS))

import check_human  # noqa: E402
import check_result  # noqa: E402

GOOD = {
    "modo": "perfecto", "cancion": 0, "instrumento": 0, "dificultad": 3,
    "cuadros": 8000, "vblanks": 7000, "pasos": 7000, "perdidos": 0, "desync": 0,
    "sync_max": 0, "sync_muestras": 7000, "sync_fuera": 0,
    "puntaje": 12345, "notas": 400, "total": 400, "combo_max": 400, "estrellas": 5, "fallo": 0, "nuevo_record": 0,
}


def make_case(tmp_path: Path, **over) -> Path:
    r = {**GOOD, **over}
    r = {k: v for k, v in r.items() if v is not None}
    (tmp_path / "resultado.txt").write_text("".join(f"{k}={v}\n" for k, v in r.items()))
    with wave.open(str(tmp_path / "audio.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        tone = [int(8000 * math.sin(i / 7)) for i in range(20000)]
        w.writeframes(b"".join(struct.pack("<hh", s, s) for s in tone))
    return tmp_path


def run(d: Path, mode="perfecto", players=0, mode2="perfecto", max_lost=2):
    return check_result.check(d, mode, players, mode2, max_lost)[1]


def test_perfect_game_passes(tmp_path):
    assert run(make_case(tmp_path)) == []


@pytest.mark.parametrize("over,text", [
    ({"notas": 399}, "acertó 399 de 400"),
    ({"estrellas": 4}, "estrellas"),
    ({"perdidos": 3}, "cuadros"),
    ({"desync": 1}, "desincronizó"),
    ({"sync_max": 2, "sync_fuera": 10}, "separó de la Chart"),
    ({"sync_muestras": 0}, "no se midió"),
])
def test_perfect_game_failures_are_reported(tmp_path, over, text):
    problems = run(make_case(tmp_path, **over))
    assert any(text in p for p in problems), problems


def test_lost_frames_up_to_two_are_tolerated(tmp_path):
    assert run(make_case(tmp_path, perdidos=2)) == []


def test_nothing_bot_must_lose(tmp_path):
    assert run(make_case(tmp_path, notas=0, fallo=1), "nada") == []
    assert run(make_case(tmp_path, notas=0, fallo=0), "nada") != []


def test_smashing_must_break_combo(tmp_path):
    assert run(make_case(tmp_path, combo_max=200), "machacar") == []
    assert any("combo" in p for p in run(make_case(tmp_path), "machacar"))


def test_pause_case_requires_frozen_clock(tmp_path):
    ok = {"pausa_etapa": 3, "pausa_cuadros": 180, "pausa_deriva": 0}
    assert run(make_case(tmp_path, **ok), "pausa") == []
    assert any("avanzó" in p for p in run(make_case(tmp_path, **{**ok, "pausa_deriva": 4}), "pausa"))
    assert any("no se completó" in p for p in run(make_case(tmp_path, **{**ok, "pausa_etapa": 1}), "pausa"))
    assert any("solo" in p for p in run(make_case(tmp_path, **{**ok, "pausa_cuadros": 20}), "pausa"))


def two_players(**over):
    return {"j2_puntaje": 12345, "j2_notas": 400, "j2_total": 400, "j2_fallo": 0, "ganador": 0,
            "banda_notas": 800, "banda_total": 800, "banda_estrellas": 5, "banda_fallo": 0, "banda_puntaje": 1, **over}


def test_versus_tie_and_winner(tmp_path):
    assert run(make_case(tmp_path, **two_players()), players=1) == []
    bad = run(make_case(tmp_path, **two_players(ganador=1)), players=1)
    assert any("ganador" in p for p in bad)


def test_versus_when_player_two_loses_the_match_is_cut(tmp_path):
    cut = two_players(j2_notas=3, j2_fallo=1, ganador=1)
    assert run(make_case(tmp_path, notas=200, **cut), players=1, mode2="nada") == []
    full = run(make_case(tmp_path, **cut), players=1, mode2="nada")
    assert any("se corta" in p for p in full)
    assert any("no perdió" in p for p in run(make_case(tmp_path, notas=200, **two_players(ganador=1)), players=1, mode2="nada"))


def test_coop_band_continues_when_player_two_falls(tmp_path):
    assert run(make_case(tmp_path, **two_players(j2_fallo=1, j2_notas=5)), players=2, mode2="nada") == []
    bad = run(make_case(tmp_path, **two_players(j2_fallo=1, banda_fallo=1)), players=2, mode2="nada")
    assert any("banda debe seguir" in p for p in bad)
    bad = run(make_case(tmp_path, **two_players(banda_estrellas=3)), players=2)
    assert any("la banda" in p for p in bad)


def test_practice_modes_skip_sync_and_check_loops(tmp_path):
    extra = {"sync_muestras": 0, "vueltas": 3, "marca": 700, "fin_bucle": 702}
    assert run(make_case(tmp_path, **extra), "marcas") == []
    assert any("bucle terminó" in p for p in run(make_case(tmp_path, **{**extra, "fin_bucle": 900}), "marcas"))
    assert any("no se repitió" in p for p in run(make_case(tmp_path, **{**extra, "vueltas": 1}), "practica"))


def test_record_and_persistence(tmp_path):
    (rec := make_case(tmp_path, nuevo_record=1, record=12345)).joinpath("resultado.txt").open("a").write("iniciales=BOT\n")
    assert run(rec, "record") == []
    d = tmp_path / "leer"
    d.mkdir()
    make_case(d, record=0)
    assert run(d, "leer_record") != []


def test_main_prints_summary_line(tmp_path, capsys):
    make_case(tmp_path)
    code = check_result.main(["check_result.py", str(tmp_path), "perfecto", "caso", "0", "perfecto", "", "2"])
    assert code == 0
    assert capsys.readouterr().out.startswith("ok    caso:")


# ---- Bot humano (R17.12) ----

def games(lost_by_diff, per_diff=10):
    out = []
    for diff, lost in lost_by_diff.items():
        out += [{"dificultad": diff, "fallo": 1 if k < lost else 0} for k in range(per_diff)]
    return out


def test_human_rates_in_band_pass():
    summary, problems = check_human.evaluate(games({0: 0, 1: 0, 2: 1, 3: 5}))
    assert problems == [] and "terminadas" in summary


def test_human_too_good_or_too_bad_fail():
    _, problems = check_human.evaluate(games({0: 0, 1: 0, 2: 0, 3: 0}))
    assert any("experto" in p for p in problems)
    _, problems = check_human.evaluate(games({0: 8, 1: 8, 2: 8, 3: 9}))
    assert any("terminó" in p for p in problems)


def test_human_few_games_are_informative_only():
    summary, problems = check_human.evaluate(games({3: 0}, per_diff=3))
    assert problems == [] and "informativo" in summary


def test_human_reads_games_from_build_folder(tmp_path):
    for k, fallo in enumerate((0, 1)):
        d = tmp_path / f"test-humano-x-d3-s{k}"
        d.mkdir()
        (d / "resultado.txt").write_text(f"dificultad=3\nfallo={fallo}\n")
    assert [g["fallo"] for g in check_human.read_games(tmp_path)] == [0, 1]
