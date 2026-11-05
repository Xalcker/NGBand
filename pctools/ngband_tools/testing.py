"""Pruebas de NGBand en MAME: los casos del bot (tests/autoplay.lua) y sus revisores.

Se corren con ``uv run ngband test`` (ver ``bandcore.testrun``). Los revisores viven en ``tests/check_result.py``
(un caso) y ``tests/check_human.py`` (las partidas del bot humano en conjunto); aquí solo se arman los casos.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from bandcore import testrun
from bandcore.testrun import Case, Result

ROOT = Path(__file__).resolve().parents[2]
MAX_LOST = 2        # R17.8: más de 2 cuadros perdidos es una falla


def _load(name: str, root: Path):
    spec = importlib.util.spec_from_file_location(name, root / "tests" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# nombre, canción ("DEMO" = la de demostración), instrumento, dificultad, modo [, opciones] [, TWO]
# TWO = (jugadores, instrumento2, dificultad2, modo2)
def _table(demo: str):
    D = demo
    one = [
        # Fase 1: la canción de demostración con los tres bots de R17.2 a R17.4
        ("demo-perfecto-experto", D, 0, 3, "perfecto"),
        ("demo-perfecto-facil", D, 0, 0, "perfecto"),
        ("demo-nada", D, 0, 1, "nada"),
        ("demo-machacar", D, 0, 2, "machacar"),
        ("demo-sinfallo", D, 0, 0, "sinfallo"),
        ("demo-mitad", D, 0, 3, "mitad"),
    ]
    options = [
        # Opciones (R17.6): ESPEJO, VELOCIDAD (75%, 50% y 125%), CAIDA y Practice_Mode con y sin marcas. Con
        # VELOCIDAD los pasos por cuadro cambian a propósito, pero el reloj y el Frame_Stream deben seguir juntos.
        ("tormenta-espejo", "tormenta", 0, 3, "perfecto", "espejo=1"),
        ("tormenta-espejo-bajo", "tormenta", 2, 3, "perfecto", "espejo=1"),
        ("tormenta-lenta", "tormenta", 0, 3, "perfecto", "velocidad=1"),
        ("tormenta-media", "tormenta", 0, 3, "perfecto", "velocidad=2"),
        ("tormenta-rapida", "tormenta", 0, 3, "perfecto", "velocidad=3 caida=4"),
        ("tormenta-caida-facil", "tormenta", 0, 0, "perfecto", "caida=1"),
        ("marcha-practica", "marcha", 0, 2, "practica", "practica=3 inicio=2"),
        ("marcha-marcas", "marcha", 0, 2, "marcas", "practica=4 inicio=1"),
    ]
    levels = [
        # SIN FALLO y niveles de dificultad por instrumento (R17.2, R17.6)
        ("tormenta-sinfallo", "tormenta", 0, 0, "sinfallo"),
        ("tormenta-mitad", "tormenta", 0, 3, "mitad"),
        ("tormenta-machacar", "tormenta", 0, 2, "machacar"),
        ("tormenta-guitarra-experto", "tormenta", 0, 3, "perfecto"),
        ("tormenta-teclado-facil", "tormenta", 1, 0, "perfecto"),
        ("luna-teclado-dificil", "luna", 1, 2, "perfecto"),
        ("tormenta-bajo-dificil", "tormenta", 2, 2, "perfecto"),
        ("carrera-guitarra-experto", "carrera", 0, 3, "perfecto"),
        ("cumbia-bajo-experto", "cumbia", 2, 3, "perfecto"),
        # Batería (ADPCM-A): el bot toca los pads y el bombo (carril naranja)
        ("tormenta-bateria-experto", "tormenta", 3, 3, "perfecto"),
        ("cumbia-bateria-facil", "cumbia", 3, 0, "perfecto"),
        # Audio contra la Chart (R17.5): pausa ~3 s a mitad de canción y reanuda
        ("tormenta-pausa", "tormenta", 0, 3, "pausa"),
        ("cumbia-pausa-bajo", "cumbia", 2, 2, "pausa"),
        ("tormenta-pausa-rapida", "tormenta", 0, 3, "pausa", "velocidad=3"),
    ]
    two = [
        # Dos jugadores (R17.7): VS con el mismo chart (empate), VS donde J2 pierde (la partida se corta y gana J1),
        # Co-Op perfecto (guitarra y bajo) y Co-Op con J2 caído (la banda sigue)
        ("vs-empate", "tormenta", 0, 3, "perfecto", "", (1, 0, 3, "perfecto")),
        ("vs-j2-pierde", "tormenta", 0, 3, "perfecto", "", (1, 0, 3, "nada")),
        ("coop-perfecto", "tormenta", 0, 3, "perfecto", "", (2, 2, 2, "perfecto")),
        ("coop-j2-cae", "carrera", 0, 2, "perfecto", "", (2, 3, 1, "nada")),
        ("vs-pausa", "tormenta", 0, 3, "pausa", "", (1, 2, 2, "perfecto")),
    ]
    perf = [
        # Rendimiento (R18.1, R18.2): el peor caso de sprites (experto con CAIDA rápida y golpes al aire)
        ("perf-1p-peor", "tormenta", 0, 3, "machacar", "caida=4", None),
        ("perf-vs-peor", "tormenta", 0, 3, "machacar", "caida=4", (1, 0, 3, "machacar")),
        ("perf-coop-peor", "tormenta", 0, 3, "machacar", "caida=4", (2, 2, 3, "machacar")),
        ("perf-vs-bateria", "tormenta", 0, 3, "perfecto", "", (1, 3, 3, "perfecto")),
    ]
    return one, options, levels, two, perf


# Un subconjunto para cambios del motor
RAPIDA = {"demo-perfecto-experto", "demo-nada", "demo-machacar", "demo-record", "demo-record-persiste",
          "tormenta-pausa", "tormenta-espejo", "marcha-practica", "vs-empate", "coop-perfecto", "tormenta-bateria-experto"}


def song_index(root: Path, song: str) -> int | None:
    """El lugar de una canción en el menú: el orden de build/gen/songs.txt (alfabético, R1.8)."""
    f = root / "build" / "gen" / "songs.txt"
    if not f.exists():
        return None
    names = f.read_text(encoding="utf-8").splitlines()
    return names.index(song) if song in names else None


def build_cases(args, root: Path = ROOT) -> list[Case]:
    demo = os.environ.get("NGBAND_DEMO_SONG", "demo")
    sym = root / "build" / "ngband.sym"
    cases: list[Case] = []
    check_result = _load("check_result", root)

    def check(case: Case, d: Path, code: int) -> Result:
        mode, players, mode2 = case.extra["mode"], case.extra["players"], case.extra["mode2"]
        r, problems = check_result.check(d, mode, players, mode2, MAX_LOST)
        return Result(testrun.FAIL if problems else testrun.OK, check_result.summary_line(r, mode, players), problems)

    def add(name, song, instr, diff, mode, opts="", two=None, nvram=None, fresh=False, seed=1):
        idx = song_index(root, song)
        c = Case(name, check=check, serial=nvram is not None, nvram=nvram, fresh_nvram=fresh)
        players, instr2, diff2, mode2 = two or (0, 0, 0, "perfecto")
        if idx is None:
            c.skip = f"la canción {song} no está en build/gen/songs.txt"
            c.skip_is_failure = song == demo
        else:
            c.env = {"NGBAND_SYM": str(sym), "NGBAND_OUT": str(root / "build" / f"test-{name}"),
                     "NGBAND_SONG": str(idx), "NGBAND_INSTR": str(instr), "NGBAND_DIFF": str(diff),
                     "NGBAND_MODE": mode, "NGBAND_OPTS": opts, "NGBAND_PLAYERS": str(players),
                     "NGBAND_INSTR2": str(instr2), "NGBAND_DIFF2": str(diff2), "NGBAND_MODE2": mode2,
                     "NGBAND_SEED": str(seed)}
        c.extra = {"mode": mode, "players": players, "mode2": mode2}
        cases.append(c)

    one, options, levels, two, perf = _table(demo)
    nv_rec, nv_vs = root / "build" / "test-nvram-records", root / "build" / "test-nvram-vs"
    for n, s, i, d, m in one:
        add(n, s, i, d, m)
    # Récords: con la backup RAM vacía, el juego perfecto es récord y se escriben las iniciales; al volver a
    # encender (la misma carpeta de nvram) el récord sigue ahí (R17.6)
    add("demo-record", demo, 0, 1, "record", nvram=nv_rec, fresh=True)
    add("demo-record-persiste", demo, 0, 1, "leer_record", nvram=nv_rec)
    for n, s, i, d, m, o in options:
        add(n, s, i, d, m, opts=o)
    for row in levels:
        add(*row)
    for n, s, i, d, m, o, t in two:
        add(n, s, i, d, m, opts=o, two=t)
    add("vs-record", demo, 0, 1, "record", two=(1, 1, 1, "perfecto"), nvram=nv_vs, fresh=True)
    for n, s, i, d, m, o, t in perf:
        add(n, s, i, d, m, opts=o, two=t)
    # Bot humano (R17.12): 4 canciones x 4 Difficulties x NGBAND_HUMAN_SEEDS; check_human.py comprueba al final
    # que termine ~90% de las partidas y pierda ~45% en experto
    for song in ("tormenta", "carrera", "cumbia", "luna"):
        for diff in range(4):
            for seed in range(1, int(os.environ.get("NGBAND_HUMAN_SEEDS", "1")) + 1):
                add(f"humano-{song}-d{diff}-s{seed}", song, 0, diff, "humano", seed=seed)
    if getattr(args, "rapida", False):
        cases = [c for c in cases if c.name in RAPIDA]
    return cases


def emulator(root: Path = ROOT, window: bool = True) -> testrun.Mame:
    game = os.environ.get("NGBAND_MAME_GAME", "ngband")
    rompath = os.environ.get("NGBAND_MAME_ROMPATH", str(root / "build" / "rom"))
    debug = ["-debug", "-debugger", "none"] if os.environ.get("NGBAND_TRACE") else []  # perfil (autoplay.lua)
    return testrun.Mame(lambda case: ["neogeo", "-hash", rompath, "-rompath", rompath, "-cart1", game, *debug],
                        root / "tests" / "autoplay.lua", window=window, resolution="640x448")


def post(root: Path, results: dict[str, Result]) -> dict[str, Result]:
    """check_human.py: la tasa del bot humano en conjunto (solo si corrió alguna de sus partidas)."""
    if not any(n.startswith("humano-") for n in results):
        return {}
    human = _load("check_human", root)
    summary, problems = human.evaluate(human.read_games(root / "build"))
    return {"humano-conjunto": Result(testrun.FAIL if problems else testrun.OK, summary, problems)}
