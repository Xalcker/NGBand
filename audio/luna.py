"""Luz de Luna: balada en Do mayor (112 BPM). Luce el teclado (pulso 2).

Uso (desde la raiz del repositorio):  uv run python audio/luna.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, arpegio, escribir, midi, nombre

AQUI = Path(__file__).parent
DO_MAYOR = Escala(["C", "D", "E", "F", "G", "A", "B"])

instrumentos = {
    "Piano": Instrumento([12, 12, 11, 10, 9, 8, 8, 7], [2]),
    "Guitarra": Instrumento([8, 7, 7, 6, 6, 5, 5, 4], [1]),
    "Coro": Instrumento([8, 8, 7, 7, 6, 6], [1]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Melodia del piano (pulso 2) ----------------------------------------------------------------
estrofa = [
    "E5:4 G5:4 C6:6 B5:2",  # Do
    "D6:4 B5:4 G5:8",  # Sol
    "A5:4 C6:4 E6:6 D6:2",  # La menor
    "C6:8 A5:4 F5:4",  # Fa
    "G5:2 E5:2 G5:4 C6:4 E6:4",  # Do
    "D6:6 B5:2 G5:8",  # Sol
    "A5:4 C6:4 F6:4 E6:4",  # Fa
    "D6:8 B5:4 G5:4",  # Sol
]
coro = [
    "F6:6 E6:2 C6:8",  # Fa
    "D6:6 E6:2 B5:8",  # Sol
    "E6:4 D6:4 C6:8",  # Do
    "A5:6 C6:2 E6:8",  # La menor
    "A5:4 C6:4 F6:8",  # Fa
    "G6:4 F6:2 E6:2 D6:8",  # Sol
    "E6:8 C6:4 G5:4",  # Do
    "C6:16",  # Do
]
puente = [
    "E6:4 C6:4 A5:8",  # La menor
    "B5:4 G5:4 E5:8",  # Mi menor
    "A5:4 C6:4 F6:4 C6:4",  # Fa
    "D6:4 B5:4 D6:8",  # Sol
]
final = [
    "G5:4 C6:4 E6:8",  # Do
    "D6:4 B5:4 G5:8",  # Sol
    "A5:4 C6:4 F6:8",  # Fa
    "C6:16",  # Do
]
teclado = (
    ["@Piano " + estrofa[0]] + estrofa[1:4] + estrofa + coro + estrofa + puente + coro + final
)

# --- Acordes por compas (raiz del bajo) ------------------------------------------------------------
raices_estrofa = ["C3", "G2", "A2", "F2", "C3", "G2", "F2", "G2"]
raices_coro = ["F2", "G2", "C3", "A2", "F2", "G2", "C3", "C3"]
raices_puente = ["A2", "E2", "F2", "G2"]
raices_final = ["C3", "G2", "F2", "C3"]
raices = (
    raices_estrofa[:4] + raices_estrofa + raices_coro + raices_estrofa + raices_puente
    + raices_coro + raices_final
)

# --- Pulso 1: arpegio lento en la estrofa, terceras bajo el piano en el coro ----------------------------
def lento(r, orden, filas):
    return arpegio(r, DO_MAYOR, orden, filas)

ESTROFA = [0, 1, 2, 1]
CORO = [0, 1, 2, 3, 2, 1, 2, 1]
guitarra = ["@Guitarra " + lento(raices_estrofa[0], ESTROFA, 4)] + [lento(r, ESTROFA, 4) for r in raices_estrofa[1:4]]
guitarra += [lento(r, ESTROFA, 4) for r in raices_estrofa]
guitarra += ["@Coro " + armonizar(coro[0], DO_MAYOR, -2)] + [armonizar(c, DO_MAYOR, -2) for c in coro[1:]]
guitarra += ["@Guitarra " + lento(raices_estrofa[0], ESTROFA, 4)] + [lento(r, ESTROFA, 4) for r in raices_estrofa[1:]]
guitarra += [lento(r, [0, 1, 2, 3], 4) for r in raices_puente]
guitarra += ["@Coro " + armonizar(coro[0], DO_MAYOR, -2)] + [armonizar(c, DO_MAYOR, -2) for c in coro[1:]]
guitarra += ["@Guitarra " + lento(r, CORO, 2) for r in raices_final]

# --- Triangulo: raiz larga, quinta y raiz ------------------------------------------------------------
def bajo_balada(r):
    quinta = nombre(DO_MAYOR.mover(midi(r), 4))
    return f"{r}:8 {quinta}:4 {r}:4"

bajo = [bajo_balada(r) for r in raices]

# --- Bateria suave ---------------------------------------------------------------------------------------
INTRO = "H.......H......."
ESTROFA_B = "K...H...K...H..."
CORO_B = "K...S.H.K...S.H."
PUENTE_B = "H...H...H...H..."
RELLENO = "K...S.H.K.K.SSSS"
ruido = [INTRO] * 4
ruido += [ESTROFA_B] * 7 + [RELLENO]
ruido += [CORO_B] * 7 + [RELLENO]
ruido += [ESTROFA_B] * 7 + [RELLENO]
ruido += [PUENTE_B] * 3 + [RELLENO]
ruido += [CORO_B] * 7 + [RELLENO]
ruido += [ESTROFA_B] * 3 + ["K..............."]

cancion = Cancion(
    "Luz de Luna", 8, instrumentos,
    {"pulso1": guitarra, "pulso2": teclado, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Guitarra", "pulso2": "Piano", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "luna.txt")
