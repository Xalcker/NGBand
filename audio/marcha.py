"""Marcha del Cartucho: marcha chiptune en Do mayor (128 BPM). Luce el pulso 1 (la trompeta).

Uso (desde la raiz del repositorio):  uv run python audio/marcha.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, escribir, midi, nombre

AQUI = Path(__file__).parent
DO_MAYOR = Escala(["C", "D", "E", "F", "G", "A", "B"])

instrumentos = {
    "Trompeta": Instrumento([13, 13, 12, 12, 12, 11, 11, 11], [2]),
    "Flauta": Instrumento([9, 9, 8, 8, 7, 7], [0]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Tema (pulso 1): parte A (8 compases) y trio B (8 compases) ----------------------------------------------
A = [
    "C5:3 C5:1 C5:2 E5:2 G5:4 E5:4",  # Do
    "G5:3 G5:1 G5:2 E5:2 C5:8",  # Do
    "A5:3 A5:1 A5:2 F5:2 C5:4 F5:4",  # Fa
    "G5:4 F5:2 E5:2 D5:4 B4:4",  # Sol
    "C5:3 C5:1 E5:2 G5:2 C6:4 G5:4",  # Do
    "A5:3 A5:1 A5:2 C6:2 E6:4 C6:4",  # La menor
    "A5:4 F5:4 C5:4 F5:4",  # Fa
    "G5:8 B5:4 D6:4",  # Sol
]
B = [
    "F5:2 A5:2 C6:4 A5:2 F5:2 A5:4",  # Fa
    "G5:2 C6:2 E6:4 C6:2 G5:2 C6:4",  # Do
    "D6:4 B5:4 G5:4 B5:4",  # Sol
    "C6:8 G5:4 E5:4",  # Do
    "F5:2 A5:2 C6:4 F6:4 E6:2 D6:2",  # Fa
    "D6:4 A5:4 F5:4 A5:4",  # Re menor
    "B5:4 D6:4 G6:4 F6:2 D6:2",  # Sol
    "C6:12 G5:2 E5:2",  # Do
]
final = [
    "C6:4 G5:4 E5:4 C5:4",  # Do
    "D6:4 B5:4 G5:4 D5:4",  # Sol
    "E6:4 G5:4 C6:8",  # Do
    "C6:16",  # Do
]
trompeta = ["@Trompeta " + A[0]] + A[1:4] + A + B + A + B + A + final

raices_A = ["C3", "C3", "F2", "G2", "C3", "A2", "F2", "G2"]
raices_B = ["F2", "C3", "G2", "C3", "F2", "D3", "G2", "C3"]
raices_final = ["C3", "G2", "C3", "C3"]
raices = raices_A[:4] + raices_A + raices_B + raices_A + raices_B + raices_A + raices_final

# --- Pulso 2: contratiempos en la parte A, terceras bajo el tema en el trio ------------------------------------
def contratiempo(r):
    t = DO_MAYOR.triada(r)
    tercera, quinta = nombre(t[1] + 12), nombre(t[2] + 12)
    return f"r:4 {tercera}:2 r:2 r:4 {quinta}:2 r:2"

flauta = ["@Flauta " + contratiempo(raices_A[0])] + [contratiempo(r) for r in raices_A[1:4]]
flauta += [contratiempo(r) for r in raices_A]
flauta += [armonizar(b, DO_MAYOR, -2) for b in B]
flauta += [contratiempo(r) for r in raices_A]
flauta += [armonizar(b, DO_MAYOR, -2) for b in B]
flauta += [contratiempo(r) for r in raices_A]
flauta += [contratiempo(r) for r in raices_final]

# --- Triangulo: "oom-pah" (raiz en 1 y 3, quinta en 2 y 4) -------------------------------------------------
def oom_pah(r):
    quinta = nombre(DO_MAYOR.mover(midi(r), 4))
    return f"{r}:2 r:2 {quinta}:2 r:2 {r}:2 r:2 {quinta}:2 r:2"

bajo = [oom_pah(r) for r in raices[:-1]] + ["C3:16"]

# --- Bateria: redoble de marcha -----------------------------------------------------------------------------
MARCHA = "K.S.S.SSK.S.S.SS"
RELLENO = "K.S.S.SSSSSSSSSS"
ruido = [MARCHA] * 3 + [RELLENO]
ruido +=([MARCHA] * 7 + [RELLENO]) * 5
ruido += [MARCHA] * 3 + ["K..............."]

cancion = Cancion(
    "Marcha del Cartucho", 7, instrumentos,
    {"pulso1": trompeta, "pulso2": flauta, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Trompeta", "pulso2": "Flauta", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "marcha.txt")
