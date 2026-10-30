"""Salto Mortal: funk en Mi dorico (112 BPM). Luce el bajo (triangulo).

Uso (desde la raiz del repositorio):  uv run python audio/salto.py
"""

from pathlib import Path

from compose import Cancion, Instrumento, escribir

AQUI = Path(__file__).parent

instrumentos = {
    "Chop": Instrumento([12, 8, 4, 2], [1]),
    "Teclado": Instrumento([11, 10, 9, 8, 7, 6, 5, 4], [2]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Bajo (triangulo): los riffs son lo que se luce -----------------------------------------------------
BAJO = {
    "Ea": "E2:3 E2:1 r:2 G2:2 A2:2 r:1 B2:1 D3:2 B2:2",
    "Eb": "E2:2 r:1 E2:1 E3:2 r:2 D3:2 B2:2 G2:2 E2:2",
    "Aa": "A2:3 A2:1 r:2 C#3:2 E3:2 r:1 G3:1 E3:2 C#3:2",
    "Ab": "A2:2 r:1 A2:1 A3:2 r:2 G3:2 E3:2 C#3:2 A2:2",
    "G": "G2:3 G2:1 r:2 B2:2 D3:2 r:1 B2:1 G2:2 D3:2",
    "Epausa": "E2:4 r:4 E2:4 r:4",
    "Apausa": "A2:4 r:4 A2:4 r:4",
    "Gpausa": "G2:4 r:4 G2:4 r:4",
}
# Cada compas: (acorde para la guitarra, riff del bajo)
estrofa = [("E", "Ea"), ("E", "Eb"), ("A", "Aa"), ("A", "Ab"), ("E", "Ea"), ("E", "Eb"), ("G", "G"), ("A", "Aa")]
coro = [("G", "G"), ("A", "Aa"), ("E", "Eb"), ("E", "Ea"), ("G", "G"), ("A", "Ab"), ("E", "Ea"), ("A", "Ab")]
puente = [("E", "Epausa"), ("E", "Epausa"), ("G", "Gpausa"), ("A", "Apausa")]
intro = estrofa[:4]
partes = intro + estrofa + coro + estrofa + puente + coro + coro
bajo = [BAJO[riff] for _, riff in partes]

# --- Guitarra (pulso 1): golpes cortos a contratiempo sobre cada acorde ------------------------------------
GOLPES_ACORDE = {
    "E": ["B4", "E5", "G5", "E5"],
    "A": ["C#5", "E5", "A5", "E5"],
    "G": ["D5", "G5", "B5", "G5"],
}
def chop(acorde):
    return " ".join(f"r:2 {n}:1 r:1" for n in GOLPES_ACORDE[acorde])

guitarra = ["@Chop " + chop(partes[0][0])] + [chop(a) for a, _ in partes[1:]]

# --- Teclado (pulso 2): frases cortas que contestan al bajo ------------------------------------------------
verso = [
    "r:4 B5:2 r:2 G5:2 E5:2 r:2 D5:2",
    "E5:2 G5:2 B5:4 r:4 A5:2 G5:2",
    "r:4 C#6:2 r:2 A5:2 E5:2 r:2 E5:2",
    "A5:2 C#6:2 E6:4 r:4 D6:2 C#6:2",
    "r:4 B5:2 r:2 G5:2 E5:2 r:2 D5:2",
    "G5:4 B5:4 D6:4 B5:4",
    "r:4 D6:2 r:2 B5:2 G5:2 r:4",
    "E6:2 D6:2 C#6:4 A5:4 r:2 E5:2",
]
gancho = [
    "B5:4 D6:4 G6:4 D6:4",
    "C#6:4 E6:4 A6:4 E6:4",
    "B5:6 G5:2 E5:8",
    "E5:2 G5:2 B5:4 D6:8",
    "B5:4 D6:4 G6:4 D6:4",
    "C#6:4 E6:4 A6:4 E6:4",
    "B5:4 G5:4 E5:4 G5:4",
    "A5:8 E5:4 C#6:4",
]
quiebre = ["B5:8 D6:8", "E6:8 B5:8", "D6:8 B5:8", "C#6:8 E6:8"]
teclado = ["@Teclado " + verso[0]] + verso[1:4] + verso + gancho + verso + quiebre + gancho + gancho

# --- Bateria: groove de funk con hats abiertos --------------------------------------------------------------
GROOVE = "K..H.S.HK.KH.S.H"
ABIERTO = "K.OH.S.HK.KH.S.O"
RELLENO = "K.OH.S.HKSKSSSKS"
QUIEBRE = "K...S...K...S..."
def seccion(n):
    return [GROOVE, ABIERTO] * ((n - 1) // 2) + [GROOVE] * ((n - 1) % 2) + [RELLENO]

ruido = seccion(4) + seccion(8) + seccion(8) + seccion(8) + [QUIEBRE] * 3 + [RELLENO] + seccion(8) + seccion(8)

cancion = Cancion(
    "Salto Mortal", 8, instrumentos,
    {"pulso1": guitarra, "pulso2": teclado, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Chop", "pulso2": "Teclado", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "salto.txt")
