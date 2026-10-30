"""Cumbia del Cartucho: cumbia en Si menor (100 BPM). Luce el acordeon (pulso 1) sobre un bajo de tumbao.

Uso (desde la raiz del repositorio):  uv run python audio/cumbia.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, escribir, midi, nombre

AQUI = Path(__file__).parent
SI_MENOR = Escala(["B", "C#", "D", "E", "F#", "G", "A"])

instrumentos = {
    "Acordeon": Instrumento([13, 13, 12, 12, 11, 11, 10, 10], [2]),
    "Guitarra": Instrumento([11, 9, 7, 5, 3, 2], [1]),
    "Coro": Instrumento([10, 10, 9, 9, 8, 8], [2]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Acordeon: frases de pregunta y respuesta ------------------------------------------------------------
estrofa = [
    "B4:2 D5:2 F#5:4 E5:2 D5:2 B4:4",  # Si menor
    "D5:2 F#5:2 B5:4 A5:2 F#5:2 D5:4",  # Si menor
    "E5:2 G5:2 B5:4 A5:2 G5:2 E5:4",  # Mi menor
    "G5:2 B5:2 E6:4 D6:2 B5:2 G5:4",  # Mi menor
    "F#5:2 A5:2 C#6:4 B5:2 A5:2 F#5:4",  # Fa sostenido menor
    "A5:2 C#6:2 F#6:4 E6:2 C#6:2 A5:4",  # Fa sostenido menor
    "B5:4 A5:2 F#5:2 D5:4 F#5:4",  # Si menor
    "C#6:6 B5:2 A5:4 F#5:4",  # Fa sostenido menor
]
coro = [
    "B5:4 D6:4 G6:4 D6:4",  # Sol
    "A5:4 C#6:4 F#6:4 C#6:4",  # Fa sostenido menor
    "G5:4 B5:4 E6:4 B5:4",  # Mi menor
    "D6:8 B5:4 F#5:4",  # Si menor
    "D6:2 B5:2 G5:4 B5:2 D6:2 G6:4",  # Sol
    "C#6:2 A5:2 F#5:4 A5:2 C#6:2 F#6:4",  # Fa sostenido menor
    "E6:4 D6:4 B5:4 G5:4",  # Mi menor
    "B5:8 D6:4 F#6:4",  # Si menor
]
final = [
    "B5:4 D6:4 F#6:4 B5:4",  # Si menor
    "G5:4 B5:4 E6:4 G5:4",  # Mi menor
    "A5:4 C#6:4 F#6:4 C#6:4",  # Fa sostenido menor
    "B5:16",  # Si menor
]
acordeon = ["@Acordeon " + estrofa[0]] + estrofa[1:4] + estrofa + coro + estrofa + coro + final

raices_estrofa = ["B2", "B2", "E2", "E2", "F#2", "F#2", "B2", "F#2"]
raices_coro = ["G2", "F#2", "E2", "B2", "G2", "F#2", "E2", "B2"]
raices_final = ["B2", "E2", "F#2", "B2"]
raices = raices_estrofa[:4] + raices_estrofa + raices_coro + raices_estrofa + raices_coro + raices_final

def con(instrumento, compases):
    return ["@" + instrumento + " " + compases[0]] + compases[1:]

# --- Guitarra (pulso 2): rasgueo de tresillo (3+3+2) en la estrofa, terceras bajo el acordeon en el coro ---------
def rasgueo(r):
    t = SI_MENOR.triada(r)
    a, b = nombre(t[1] + 12), nombre(t[2] + 12)
    grupo = f"{a}:1 r:2 {b}:1 r:2 {a}:1 r:1"
    return grupo + " " + grupo

guitarra = con("Guitarra", [rasgueo(r) for r in raices_estrofa[:4] + raices_estrofa])
guitarra += con("Coro", [armonizar(c, SI_MENOR, -2) for c in coro])
guitarra += con("Guitarra", [rasgueo(r) for r in raices_estrofa])
guitarra += con("Coro", [armonizar(c, SI_MENOR, -2) for c in coro])
guitarra += con("Guitarra", [rasgueo(r) for r in raices_final])

# --- Triangulo: tumbao en la estrofa, corcheas en el coro -------------------------------------------------------
def tumbao(r):
    q = nombre(SI_MENOR.mover(midi(r), 4))
    return f"{r}:3 r:1 {q}:2 r:2 {r}:3 r:1 {q}:2 r:2"

def corcheas(r):
    q = nombre(SI_MENOR.mover(midi(r), 4))
    return f"{r}:2 {r}:2 {q}:2 {r}:2 {r}:2 {r}:2 {q}:2 {r}:2"

bajo = [tumbao(r) for r in raices_estrofa[:4] + raices_estrofa]
bajo += [corcheas(r) for r in raices_coro]
bajo += [tumbao(r) for r in raices_estrofa]
bajo += [corcheas(r) for r in raices_coro]
bajo += [tumbao(r) for r in raices_final[:3]] + [f"{raices_final[3]}:16"]

# --- Percusion: guiro (platillo) y bombo/tarola de cumbia -----------------------------------------------------
BASE = "K.HHS.H.K.HHS.H."
CORO = "K.HHS.HHK.HHS.HH"
RELLENO = "K.HHS.H.SSKKSSSS"
def seccion(base, n):
    return [base] * (n - 1) + [RELLENO]

ruido = [BASE] * 3 + [RELLENO]
ruido += seccion(BASE, 8) + seccion(CORO, 8) + seccion(BASE, 8) + seccion(CORO, 8)
ruido += [BASE] * 3 + ["K..............."]

cancion = Cancion(
    "Cumbia del Cartucho", 9, instrumentos,
    {"pulso1": acordeon, "pulso2": guitarra, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Acordeon", "pulso2": "Guitarra", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "cumbia.txt")
