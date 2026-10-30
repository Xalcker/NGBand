"""Revisa el resultado de un caso del Test_Harness (lo llama tests/run_tests.sh).

Uso: check_result.py <carpeta> <modo> <nombre> <jugadores> <modo2> <opciones> <max_perdidos>

Lee <carpeta>/resultado.txt (lo escribe tests/autoplay.lua), <carpeta>/audio.wav y bot.log; imprime una
línea "ok" o "FALLA" con los problemas y sale con 0 o 1.
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path


def check(d: Path, mode: str, players: int, mode2: str, max_lost: int) -> tuple[dict, list[str]]:
    r = dict(line.strip().split("=", 1) for line in open(d / "resultado.txt") if "=" in line)
    n = {k: int(v) for k, v in r.items() if v.lstrip("-").isdigit()}
    problems: list[str] = []
    if mode in ("perfecto", "pausa"):                                         # R17.2
        # (con 2 jugadores el combo y las estrellas de J1 dependen del otro: en Co-Op son de la banda y en VS
        # la partida se corta si el otro pierde; eso se revisa abajo)
        solo_or_clean = not players or (players == 1 and mode2 == "perfecto")
        if n["notas"] != n["total"] and not (players == 1 and mode2 == "nada"):
            problems.append(f"acertó {n['notas']} de {n['total']}")
        if solo_or_clean and n["combo_max"] != n["total"]:
            problems.append(f"combo máximo {n['combo_max']} (debe ser {n['total']})")
        if solo_or_clean and n["estrellas"] != 5:
            problems.append(f"{n['estrellas']} estrellas (deben ser 5)")
        if n["fallo"]:
            problems.append("perdió")
    elif mode == "nada":                                                      # R17.3
        if not n["fallo"]:
            problems.append("no perdió sin tocar nada")
    elif mode == "sinfallo":
        if n["fallo"]:
            problems.append("perdió con SIN FALLO")
        if n["notas"]:
            problems.append("acertó notas sin tocar")
    elif mode == "machacar":                                                  # R17.4
        if n["notas"] != n["total"]:
            problems.append(f"acertó {n['notas']} de {n['total']}")
        if n["combo_max"] >= n["total"]:
            problems.append("los golpes al aire no rompieron el combo")
        if n["fallo"]:
            problems.append("perdió")
    elif mode == "record":                                                    # R17.6
        if n["notas"] != n["total"]:
            problems.append(f"acertó {n['notas']} de {n['total']}")
        if not n["nuevo_record"]:
            problems.append("no dijo NUEVO RECORD (con la backup RAM vacía)")
        if n["record"] != n["puntaje"] or r.get("iniciales") != "BOT":
            problems.append(f"el récord guardado es {n['record']} {r.get('iniciales')} (debía ser {n['puntaje']} BOT)")
    elif mode == "leer_record":
        if not n["record"] or r.get("iniciales") != "BOT":
            problems.append(f"al volver a encender, el récord es {n['record']} {r.get('iniciales')}")
    elif mode == "practica":
        if n.get("vueltas", 0) < 2:
            problems.append(f"la práctica no se repitió (vueltas: {r.get('vueltas')})")
    elif mode == "marcas":
        if n.get("vueltas", 0) < 3:
            problems.append(f"la práctica no se repitió (vueltas: {r.get('vueltas')})")
        if abs(n["fin_bucle"] - n["marca"]) > 5:
            problems.append(f"el bucle terminó en {r['fin_bucle']} y la marca de fin estaba en {r['marca']}")
    elif mode == "mitad":
        if n["notas"] == 0:
            problems.append("no acertó ninguna")
    elif mode == "humano":                                                    # R17.12: la tasa se revisa en check_human.py
        if n["notas"] == 0 and not n["fallo"]:
            problems.append("el bot humano no acertó ninguna Note y no perdió")
    if mode == "pausa":                                                       # R17.5: audio alineado tras pausar
        if n.get("pausa_etapa", 0) != 3:
            problems.append(f"la prueba de pausa no se completó (etapa {n.get('pausa_etapa')} de 3)")
        if n.get("pausa_cuadros", 0) < 150:
            problems.append(f"la pausa duró solo {n.get('pausa_cuadros')} cuadros")
        if n.get("pausa_deriva", 0) != 0:
            problems.append(f"el reloj de la canción avanzó {n['pausa_deriva']} cuadros durante la pausa")
    if players:
        # Dos jugadores: lo del jugador 2, la banda (Co-Op) y quién ganó (VS)
        if mode2 == "perfecto" and n["j2_notas"] != n["j2_total"]:
            problems.append(f"J2 acertó {n['j2_notas']} de {n['j2_total']}")
        if players == 1:
            if mode == mode2 == "perfecto":
                expected = 0 if n["puntaje"] == n["j2_puntaje"] else (1 if n["puntaje"] > n["j2_puntaje"] else 2)
                if n["ganador"] != expected:
                    problems.append(f"ganador {n['ganador']} con {n['puntaje']} contra {n['j2_puntaje']}")
            if mode2 == "nada":
                if not n["j2_fallo"] or n["ganador"] != 1:
                    problems.append(f"J2 no perdió o no ganó J1 (ganador {n['ganador']})")
                if n["notas"] == n["total"]:
                    problems.append("en VS, si J2 pierde la partida se corta: J1 no debía terminar la canción")
        if players == 2:
            if mode == mode2 == "perfecto" and (n["banda_notas"] != n["banda_total"] or n["banda_estrellas"] != 5):
                problems.append(f"la banda: {n['banda_notas']}/{n['banda_total']}, {n['banda_estrellas']} estrellas")
            if mode2 == "nada" and (not n["j2_fallo"] or n["banda_fallo"]):
                problems.append(f"en Co-Op, con J2 caído la banda debe seguir (J2 cayó {n['j2_fallo']}, banda perdió {n['banda_fallo']})")

    # R17.8: cuadros perdidos = VBlanks sin su paso del bucle principal
    if n.get("perdidos", 0) > max_lost:
        problems.append(f"se perdieron {n['perdidos']} cuadros (más de {max_lost}): {n['vblanks']} VBlanks, {n['pasos']} pasos")
    # R17.5: cada cuadro de la Chart tiene su cuadro de audio (dentro de un cuadro), también tras pausar
    if mode not in ("leer_record", "practica", "marcas"):
        if n.get("sync_muestras", 0) == 0:
            problems.append("no se midió la sincronía del audio con la Chart")
        elif n.get("sync_fuera", 0) or n.get("sync_max", 0) > 1:
            problems.append(f"el audio se separó de la Chart hasta {n['sync_max']} cuadros ({n['sync_fuera']} de {n['sync_muestras']} muestras)")
    # Desincronía del Z80 (R12.8): la respuesta del driver debe coincidir con los cuadros enviados
    if n.get("desync", 0):
        problems.append(f"el driver de audio se desincronizó {n['desync']} veces")
    # El audio: que haya sonado algo (solo si se jugó)
    if mode not in ("leer_record",):
        try:
            with wave.open(str(d / "audio.wav")) as w:
                data = w.readframes(w.getnframes())
            s = struct.unpack(f"<{len(data) // 2}h", data[: len(data) // 2 * 2])
            sub = s[::97]
            rms = math.sqrt(sum(x * x for x in sub) / max(1, len(sub)))
            r["audio_rms"] = f"{rms:.0f}"
            if rms < 200:
                problems.append(f"el audio está casi en silencio (RMS {rms:.0f})")
        except Exception as e:  # noqa: BLE001 - cualquier fallo de lectura es una falla de la prueba
            problems.append(f"no se pudo leer el audio: {e}")
    return r, problems


def main(argv: list[str]) -> int:
    d, mode, name = Path(argv[1]), argv[2], argv[3]
    players, mode2, max_lost = int(argv[4]), argv[5], int(argv[7])
    r, problems = check(d, mode, players, mode2, max_lost)
    if mode == "leer_record":
        summary = f"récord {r.get('record')} {r.get('iniciales')}"
    elif mode in ("practica", "marcas"):
        summary = f"vueltas {r.get('vueltas')}, marca {r.get('marca')}, fin del bucle {r.get('fin_bucle')}"
    else:
        summary = (f"notas {r['notas']}/{r['total']}, puntaje {r['puntaje']}, estrellas {r['estrellas']}, "
                   f"combo {r['combo_max']}, fallo {r['fallo']}, cuadros perdidos {r.get('perdidos', '-')}, "
                   f"sync {r.get('sync_max', '-')}, audio RMS {r.get('audio_rms', '-')}")
        if players:
            summary += f", J2 {r.get('j2_notas')}/{r.get('j2_total')} fallo {r.get('j2_fallo')}"
            summary += f", ganador {r.get('ganador')}" if players == 1 else f", banda {r.get('banda_puntaje')} {r.get('banda_estrellas')}*"
    print(("FALLA " if problems else "ok    ") + f"{name}: {summary}" + "".join(f"\n      - {p}" for p in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
