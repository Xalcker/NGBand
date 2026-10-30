"""Revisa las partidas del Bot humano en conjunto (R17.12). Lo llama tests/run_tests.sh al final.

Uso: check_human.py <carpeta build> [--min-games N]

Junta build/test-humano-*/resultado.txt y comprueba que el bot humano termine alrededor del 90% de las
partidas (todas las Difficulties) y pierda alrededor del 45% en la más alta (experto, dificultad 3). Las
bandas son anchas a propósito: cada tanda tiene pocas partidas. Si hay menos de N partidas (por defecto 8)
solo se informa. Sale con 0 si todo está en las bandas y 1 si no.
"""
from __future__ import annotations

import sys
from pathlib import Path

FINISH_TARGET, FINISH_TOL = 0.90, 0.10      # terminadas: de 80% a 100%
EXPERT_LOSS_TARGET, EXPERT_LOSS_TOL = 0.45, 0.25   # perdidas en experto: de 20% a 70%


def read_games(build: Path) -> list[dict[str, int]]:
    games = []
    for f in sorted(build.glob("test-humano-*/resultado.txt")):
        r = dict(line.strip().split("=", 1) for line in open(f) if "=" in line)
        games.append({k: int(v) for k, v in r.items() if v.lstrip("-").isdigit()})
    return games


def evaluate(games: list[dict[str, int]], min_games: int = 8) -> tuple[str, list[str]]:
    """Devuelve (resumen, problemas)."""
    if not games:
        return "sin partidas del bot humano", []
    lost = [g["fallo"] != 0 for g in games]
    finished = 1 - sum(lost) / len(games)
    expert = [g for g in games if g.get("dificultad") == 3]
    expert_loss = sum(g["fallo"] != 0 for g in expert) / len(expert) if expert else None
    summary = f"{len(games)} partidas, terminadas {finished:.0%}"
    if expert_loss is not None:
        summary += f", perdidas en experto {expert_loss:.0%} de {len(expert)}"
    problems: list[str] = []
    if len(games) >= min_games:
        if abs(finished - FINISH_TARGET) > FINISH_TOL:
            problems.append(f"terminó {finished:.0%} de las partidas (debe ser alrededor de {FINISH_TARGET:.0%})")
        if expert_loss is not None and abs(expert_loss - EXPERT_LOSS_TARGET) > EXPERT_LOSS_TOL:
            problems.append(f"perdió {expert_loss:.0%} en experto (debe ser alrededor de {EXPERT_LOSS_TARGET:.0%}); "
                            "ajusta HUMAN en tests/autoplay.lua o NGBAND_HUMAN_MISS")
    else:
        summary += f" (menos de {min_games}: solo informativo)"
    return summary, problems


def main(argv: list[str]) -> int:
    build = Path(argv[1]) if len(argv) > 1 else Path("build")
    min_games = int(argv[argv.index("--min-games") + 1]) if "--min-games" in argv else 8
    summary, problems = evaluate(read_games(build), min_games)
    print(("FALLA " if problems else "ok    ") + f"bot humano: {summary}" + "".join(f"\n      - {p}" for p in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
