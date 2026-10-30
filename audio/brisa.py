"""Brisa de Verano: surf en Sol mayor (128 BPM). Luce el pulso 1 con notas picadas muy rapidas,
sobre un bajo que camina por el acorde.

Uso (desde la raiz del repositorio):  uv run python audio/brisa.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, escribir, nombre

AQUI = Path(__file__).parent
SOL_MAYOR = Escala(["G", "A", "B", "C", "D", "E", "F#"])

instrumentos = {
    "Surf": Instrumento([13, 12, 12, 11, 11, 10, 10, 9], [0]),
    "Organo": Instrumento([8, 8, 7, 7, 6, 6], [2]),
    "Coro": Instrumento([10, 10, 9, 9, 8, 8], [2]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Estrofa: notas repetidas muy rapido (como la pua de una guitarra surf) y frases que suben ------------------
estrofa = [
    "G5:1 G5:1 G5:1 G5:1 B5:1 B5:1 B5:1 B5:1 D6:2 B5:2 G5:2 B5:2",  # Sol
    "E5:1 E5:1 E5:1 E5:1 G5:1 G5:1 G5:1 G5:1 B5:2 G5:2 E5:2 G5:2",  # Mi menor
    "C6:1 C6:1 C6:1 C6:1 E6:1 E6:1 E6:1 E6:1 G6:2 E6:2 C6:2 E6:2",  # Do
    "D6:1 D6:1 D6:1 D6:1 F#6:1 F#6:1 F#6:1 F#6:1 A6:2 F#6:2 D6:2 A5:2",  # Re
    "G5:2 B5:2 D6:4 G6:4 D6:4",  # Sol
    "E6:4 B5:4 G5:4 B5:4",  # Mi menor
    "C6:2 E6:2 G6:4 E6:2 C6:2 G5:4",  # Do
    "D6:8 A5:4 F#5:4",  # Re
]
coro = [
    "E6:4 G6:4 E6:4 C6:4",  # Do
    "F#6:4 A6:4 F#6:4 D6:4",  # Re
    "B5:6 D6:2 G6:8",  # Sol
    "E6:4 D6:4 B5:8",  # Mi menor
    "C6:2 E6:2 G6:4 E6:4 C6:4",  # Do
    "A5:2 D6:2 F#6:4 A6:4 F#6:4",  # Re
    "G6:4 D6:4 B5:4 G5:4",  # Sol
    "G5:8 B5:4 D6:4",  # Sol
]
puente = [
    "A5:8 C6:4 E6:4",  # La menor
    "F#5:8 A5:4 D6:4",  # Re
    "A5:8 C6:4 E6:4",  # La menor
    "D6:16",  # Re
]
final = [
    "G5:4 B5:4 D6:4 G6:4",  # Sol
    "E6:4 B5:4 G5:4 E5:4",  # Mi menor
    "C6:4 E6:4 G6:4 E6:4",  # Do
    "G5:16",  # Sol
]

raices_estrofa = ["G2", "E2", "C3", "D3", "G2", "E2", "C3", "D3"]
raices_coro = ["C3", "D3", "G2", "E2", "C3", "D3", "G2", "G2"]
raices_puente = ["A2", "D3", "A2", "D3"]
raices_final = ["G2", "E2", "C3", "G2"]
raices = (
    raices_estrofa[:4] + raices_estrofa + raices_coro + raices_estrofa + raices_coro
    + raices_puente + raices_coro + raices_final
)

def con(instrumento, compases):
    return ["@" + instrumento + " " + compases[0]] + compases[1:]

def armonia(compases):
    return [armonizar(c, SOL_MAYOR, -2) for c in compases]

# --- Pulso 1: surf en estrofa y final, melodia cantada en el coro y el puente --------------------------------------
surf = con("Surf", estrofa[:4] + estrofa + coro + estrofa + coro + puente + coro + final)

# --- Pulso 2 (organo): acordes a contratiempo en la estrofa, terceras bajo la melodia en el coro -------------------
def contratiempo(r):
    t = SOL_MAYOR.triada(r)
    quinta, tercera = nombre(t[2] + 12), nombre(t[1] + 12)
    return " ".join(f"r:2 {n}:2" for n in [quinta, tercera, quinta, tercera])

organo = con("Organo", [contratiempo(r) for r in raices_estrofa[:4] + raices_estrofa])
organo += con("Coro", armonia(coro))
organo += con("Organo", [contratiempo(r) for r in raices_estrofa])
organo += con("Coro", armonia(coro))
organo += con("Organo", [contratiempo(r) for r in raices_puente])
organo += con("Coro", armonia(coro))
organo += con("Organo", [contratiempo(r) for r in raices_final])

# --- Triangulo: el bajo camina por el acorde (raiz, tercera, quinta, tercera) ----------------------------------------
def camina(r):
    t = SOL_MAYOR.triada(r)
    return " ".join(f"{nombre(n)}:4" for n in [t[0], t[1], t[2], t[1]])

bajo = [camina(r) for r in raices[:-1]] + [f"{raices_final[3]}:16"]

# --- Bateria: surf con platillo abierto ----------------------------------------------------------------------------
BASE = "K.H.S.H.K.KHS.H."
CORO = "K.O.S.O.K.K.S.O."
PUENTE = "K...H...S...H..."
RELLENO = "K.H.S.H.SSKKSSSS"
def seccion(base, n):
    return [base] * (n - 1) + [RELLENO]

ruido = [BASE] * 3 + [RELLENO]
ruido += seccion(BASE, 8) + seccion(CORO, 8) + seccion(BASE, 8) + seccion(CORO, 8)
ruido += [PUENTE] * 3 + [RELLENO] + seccion(CORO, 8)
ruido += [BASE] * 3 + ["K..............."]

cancion = Cancion(
    "Brisa de Verano", 7, instrumentos,
    {"pulso1": surf, "pulso2": organo, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Surf", "pulso2": "Organo", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "brisa.txt")
