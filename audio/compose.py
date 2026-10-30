"""Motor para componer canciones originales de NESBand como proyectos de texto de FamiStudio.

Las canciones del juego son originales (GPL-2.0-or-later) y se escriben en Python con una
notacion corta; este modulo las convierte a `audio/<cancion>.txt`, que `nesband import-song`
importa igual que cualquier otro proyecto de FamiStudio.

Notacion de un compas (16 filas, cada fila es una semicorchea):

    "E5:2 G5:2 r:4 A5:8"      nota:filas, `r` es silencio; las filas de un compas suman 16
    "@Riff"                   cambia de instrumento (vale para lo que sigue en ese canal)

La bateria se escribe con 16 caracteres por compas, uno por fila:

    "K.H.S.H.K.H.S.H."        K bombo, S tarola, H platillo cerrado, O platillo abierto, . silencio

Uso: define las listas de compases de cada canal, arma un `Cancion` y llama a `escribir`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

NOMBRES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FILAS_POR_COMPAS = 16
TONO_DPCM = 12  # indice de velocidad del DMC: 12 = ~16.9 kHz (15 seria 33 kHz y ocuparia el doble)
FRECUENCIA_DPCM = 1789773 / 106

# Cada golpe de bateria usa una altura distinta del canal de ruido y su propio instrumento.
GOLPES = {
    "K": ("A#2", "Bombo"),
    "S": ("D#3", "Tarola"),
    "H": ("G#3", "Platillo"),
    "O": ("G#3", "Abierto"),
}


def midi(nombre: str) -> int:
    """'C#4' -> 61 (como en FamiStudio: C4 es la nota 60)."""
    alt = 2 if nombre[1] in "#b" else 1
    letra = nombre[:alt]
    if letra.endswith("b"):
        letra = NOMBRES[(NOMBRES.index(letra[0]) - 1) % 12]
    return 12 * (int(nombre[alt:]) + 1) + NOMBRES.index(letra)


def nombre(n: int) -> str:
    return f"{NOMBRES[n % 12]}{n // 12 - 1}"


@dataclass
class Escala:
    """Una escala (clases de altura) para armar acordes por grados y armonizar a terceras."""

    clases: list[str]

    def __post_init__(self) -> None:
        pcs = {midi(c + "4") % 12 for c in self.clases}
        self.notas = [n for n in range(24, 100) if n % 12 in pcs]

    def grado(self, n: int) -> int:
        return self.notas.index(n)

    def mover(self, n: int, pasos: int) -> int:
        """Sube o baja `pasos` grados dentro de la escala (-2 = una tercera abajo)."""
        return self.notas[self.grado(n) + pasos]

    def triada(self, raiz: str) -> list[int]:
        g = self.grado(midi(raiz))
        return [self.notas[g], self.notas[g + 2], self.notas[g + 4]]


def parsear(compas: str, instrumento: str) -> tuple[list[tuple[int, str | None, int, str]], str]:
    """Convierte un compas a [(fila, nota o None, filas, instrumento)] y el instrumento vigente."""
    fila, notas = 0, []
    for ficha in compas.split():
        if ficha.startswith("@"):
            instrumento = ficha[1:]
            continue
        n, filas = ficha.split(":")
        filas = int(filas)
        notas.append((fila, None if n == "r" else n, filas, instrumento))
        fila += filas
    if fila != FILAS_POR_COMPAS:
        raise ValueError(f"el compas '{compas}' suma {fila} filas y deberian ser {FILAS_POR_COMPAS}")
    return notas, instrumento


# Percusion con samples DPCM: cada golpe es una nota que dispara un sample (ver bombo_dpcm y tarola_dpcm)
PERCUSION = {
    "K": ("C1", "Percusion"),
    "S": ("C#1", "Percusion"),
}


def bateria(compas: str, golpes: dict[str, tuple[str, str]] = GOLPES) -> str:
    """'K.H.S.H.K.H.S.H.' -> fichas de nota:filas para parsear (cada golpe dura una fila)."""
    if len(compas) != FILAS_POR_COMPAS:
        raise ValueError(f"el compas de bateria '{compas}' no tiene {FILAS_POR_COMPAS} caracteres")
    fichas = []
    for c in compas:
        fichas.append(f"@{golpes[c][1]} {golpes[c][0]}:1" if c in golpes else "r:1")
    return " ".join(fichas)


@dataclass
class Instrumento:
    volumen: list[int] | None = None
    duty: list[int] | None = None  # 0 = 12.5%, 1 = 25%, 2 = 50%, 3 = 75%
    mapeo: list[tuple[str, str]] | None = None  # instrumento DPCM: (nota, nombre del sample)


@dataclass
class Cancion:
    titulo: str
    fila_cuadros: int  # cuadros por fila: 6 = 150 BPM, 5 = 180, 8 = 112
    instrumentos: dict[str, Instrumento]
    canales: dict[str, list[str]] = field(default_factory=dict)  # canal -> compases
    inicial: dict[str, str] = field(default_factory=dict)  # canal -> instrumento inicial
    muestras: dict[str, str] = field(default_factory=dict)  # nombre del sample -> datos DPCM en hexadecimal

    @property
    def compases(self) -> int:
        return len(next(iter(self.canales.values())))


def _env(tipo: str, valores: list[int]) -> str:
    return f'\t\t\tEnvelope Type="{tipo}" Length="{len(valores)}" Values="{",".join(map(str, valores))}"\n'


def escribir(c: Cancion, ruta: Path) -> None:
    largos = {k: len(v) for k, v in c.canales.items()}
    if len(set(largos.values())) != 1:
        raise ValueError(f"los canales no miden lo mismo (en compases): {largos}")
    f = c.fila_cuadros
    out = [
        f'Project Version="4.5.3" TempoMode="FamiStudio" Name="{c.titulo}" Author="NESBand" '
        f'Copyright="NESBand (GPL-2.0-or-later)"\n'
    ]
    for nom, datos in c.muestras.items():
        out.append(f'\tDPCMSample Name="{nom}" Data="{datos}"\n')
    for n, ins in c.instrumentos.items():
        out.append(f'\tInstrument Name="{n}"\n')
        for nota, muestra in ins.mapeo or []:
            out.append(
                f'\t\tDPCMMapping Note="{nota}" Sample="{muestra}" Pitch="{TONO_DPCM}" Loop="False" Bank="0"\n'
            )
        if ins.volumen:
            out.append(_env("Volume", ins.volumen))
        if ins.duty:
            out.append(_env("DutyCycle", ins.duty))
    out.append(
        f'\tSong Name="{c.titulo}" Length="{c.compases}" LoopPoint="0" PatternLength="{FILAS_POR_COMPAS}" '
        f'BeatLength="4" NoteLength="{f}" Groove="{f}" GroovePaddingMode="Middle"\n'
    )
    tipos = [("Square1", "pulso1"), ("Square2", "pulso2"), ("Triangle", "triangulo"), ("Noise", "ruido"), ("DPCM", "dpcm")]
    for tipo, clave in tipos:
        if clave not in c.canales:
            continue
        out.append(f'\t\tChannel Type="{tipo}"\n')
        patrones: dict[str, str] = {}  # contenido -> nombre
        instancias = []
        instrumento = c.inicial.get(clave, next(iter(c.instrumentos)))
        for i, compas in enumerate(c.canales[clave]):
            if clave == "ruido":
                compas = bateria(compas)
            elif clave == "dpcm":
                compas = bateria(compas, PERCUSION)
            notas, instrumento = parsear(compas, instrumento)
            lineas = []
            extra = ' DeltaCounter="32"' if clave == "dpcm" else ""  # cada golpe arranca desde el centro
            for fila, n, filas, ins in notas:
                if n is not None:
                    lineas.append(
                        f'\t\t\t\t\tNote Time="{fila * f}" Value="{n}" Duration="{filas * f - 1}" '
                        f'Instrument="{ins}"{extra}\n'
                    )
            cuerpo = "".join(lineas)
            if cuerpo not in patrones:
                patrones[cuerpo] = f"P{len(patrones) + 1}"
                out.append(f'\t\t\tPattern Name="{patrones[cuerpo]}"\n{cuerpo}')
            instancias.append(f'\t\t\tPatternInstance Time="{i}" Pattern="{patrones[cuerpo]}"\n')
        out.extend(instancias)
    if "dpcm" not in c.canales:
        out.append('\t\tChannel Type="DPCM"\n')
    ruta.write_text("".join(out), encoding="utf-8", newline="\n")
    print(f"{ruta}: {c.compases} compases, {c.compases * FILAS_POR_COMPAS * f / 60:.0f} s")


def armonizar(compas: str, escala: Escala, pasos: int) -> str:
    """Mueve cada nota `pasos` grados dentro de la escala (por ejemplo -2: una tercera abajo)."""
    fichas = []
    for ficha in compas.split():
        if ficha.startswith("@") or ficha.startswith("r:"):
            fichas.append(ficha)
            continue
        n, filas = ficha.split(":")
        fichas.append(f"{nombre(escala.mover(midi(n), pasos))}:{filas}")
    return " ".join(fichas)


def arpegio(raiz: str, escala: Escala, orden: list[int], filas: int = 2, octava: int = 12) -> str:
    """Compas de arpegio: `orden` indexa la triada (0 raiz, 1 tercera, 2 quinta, 3 raiz arriba)."""
    t = escala.triada(raiz)
    t = [n + octava for n in t] + [t[0] + octava + 12]
    fichas = [f"{nombre(t[i])}:{filas}" for i in orden]
    total = len(orden) * filas
    if total != FILAS_POR_COMPAS:
        raise ValueError("el arpegio no llena el compas")
    return " ".join(fichas)


def _modular(onda: list[float]) -> str:
    """Codifica una onda (-1..1) como modulacion delta de 1 bit: el contador del DMC (0..63, empieza
    en 32) sube un escalon con un 1 y baja uno con un 0. Los bits salen del menos significativo al mas."""
    nivel, bits = 32, []
    for x in onda:
        objetivo = 32 + 30 * x
        if nivel < objetivo:
            bits.append(1)
            nivel = min(63, nivel + 1)
        else:
            bits.append(0)
            nivel = max(0, nivel - 1)
    while len(bits) % 128:  # el sample mide un multiplo de 16 bytes
        bits.append(1 if len(bits) % 2 else 0)
    datos = bytearray()
    for i in range(0, len(bits), 8):
        datos.append(sum(b << k for k, b in enumerate(bits[i : i + 8])))
    return datos.hex()


def bombo_dpcm() -> str:
    """Bombo: un seno que cae de 105 a 42 Hz mientras se apaga."""
    n, fase, onda = int(0.17 * FRECUENCIA_DPCM), 0.0, []
    for i in range(n):
        t = i / n
        fase += 2 * math.pi * (42 + 63 * math.exp(-9 * t)) / FRECUENCIA_DPCM
        onda.append(0.8 * math.exp(-4.5 * t) * math.sin(fase))
    return _modular(onda)


def tarola_dpcm() -> str:
    """Tarola: ruido que se apaga rapido sobre un tono de unos 190 Hz."""
    azar, n, onda = random.Random(7), int(0.15 * FRECUENCIA_DPCM), []
    for i in range(n):
        t = i / n
        tono = math.sin(2 * math.pi * 190 * i / FRECUENCIA_DPCM) * math.exp(-10 * t)
        ruido = azar.uniform(-1, 1) * math.exp(-5 * t)
        onda.append(0.35 * tono + 0.65 * ruido)
    return _modular(onda)
