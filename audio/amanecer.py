"""Amanecer Digital: himno de trance en Sol menor (128 BPM) con bombo en DPCM. Luce el pulso 1 (sintetizador)
sobre arpegios velocisimos del pulso 2 y un bajo que late a contratiempo.

Uso (desde la raiz del repositorio):  uv run python audio/amanecer.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, arpegio, bombo_dpcm, escribir, tarola_dpcm

AQUI = Path(__file__).parent
SOL_MENOR = Escala(["G", "A", "A#", "C", "D", "D#", "F"])

instrumentos = {
    "Sintetizador": Instrumento([14, 14, 13, 13, 12, 12, 11, 11], [2]),
    "Pluck": Instrumento([10, 8, 6, 4, 3, 2], [0]),
    "Coro": Instrumento([11, 11, 10, 10, 9, 9], [1]),
    "Bajo": Instrumento(),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
    "Percusion": Instrumento(mapeo=[("C1", "Bombo"), ("C#1", "Tarola")]),
}
muestras = {"Bombo": bombo_dpcm(), "Tarola": tarola_dpcm()}

# Acordes: Sol menor, Mi bemol, Si bemol y Fa (D# = Mi bemol, A# = Si bemol)
raices4 = ["G2", "D#2", "A#2", "F2"]

# --- Sintetizador: notas largas en la entrada y el quiebre, melodia en la caida ------------------------------------
sostenidas = ["G5:16", "D#5:16", "A#4:16", "F5:16"]
caida = [
    "D6:6 D6:2 F6:4 D6:4",  # Sol menor
    "D#6:6 D#6:2 G6:4 D#6:4",  # Mi bemol
    "A#5:6 A#5:2 D6:4 A#5:4",  # Si bemol
    "C6:6 C6:2 A5:4 C6:4",  # Fa
    "G6:4 F6:4 D6:4 F6:4",  # Sol menor
    "G6:4 F6:2 D#6:2 D6:8",  # Mi bemol
    "F6:4 D6:4 A#5:4 D6:4",  # Si bemol
    "C6:8 F6:4 A5:4",  # Fa
]
quiebre = ["G5:8 A#5:8", "D#5:8 G5:8", "A#4:8 D5:8", "C5:8 F5:8"]

lead = ["@Sintetizador " + sostenidas[0]] + sostenidas[1:] + sostenidas
lead += caida + caida + quiebre * 2 + caida + caida

raices = raices4 * 2 + raices4 * 4 + raices4 * 2 + raices4 * 4

# --- Pulso 2: arpegios de semicorchea y, en la caida, terceras bajo el sintetizador ----------------------------------
RAPIDO = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1, 2, 3]
def rapido(r):
    return arpegio(r, SOL_MENOR, RAPIDO, 1)

def armonia(compases):
    return [armonizar(c, SOL_MENOR, -2) for c in compases]

def con(instrumento, compases):
    return ["@" + instrumento + " " + compases[0]] + compases[1:]

pluck = con("Pluck", [rapido(r) for r in raices4 * 2])
pluck += con("Pluck", [rapido(r) for r in raices4 * 2]) + con("Coro", armonia(caida))
pluck += con("Pluck", [rapido(r) for r in raices4 * 2])
pluck += con("Coro", armonia(caida) + armonia(caida))

# --- Triangulo: un golpe a contratiempo en cada semicorchea par ------------------------------------------------------
def latido(r):
    return " ".join(f"r:1 {r}:1" for _ in range(8))

bajo = [latido(r) for r in raices]

# --- Percusion: bombo en cada tiempo (DPCM), palmas y platillos a contratiempo (ruido) -----------------------------------
BOMBO = "K...K...K...K..."
BOMBO_RELLENO = "K...K...K.K.KKKK"
BOMBO_QUIEBRE = "K..............."
DPCM_INTRO = [BOMBO] * 7 + [BOMBO_RELLENO]
DPCM_CAIDA = ([BOMBO] * 7 + [BOMBO_RELLENO]) * 2
DPCM_QUIEBRE = [BOMBO_QUIEBRE] * 7 + [BOMBO_RELLENO]
dpcm = DPCM_INTRO + DPCM_CAIDA + DPCM_QUIEBRE + DPCM_CAIDA

SOLO_HATS = "..H...H...H...H."
PALMAS = "..H.S.H...H.S.H."
ruido = [SOLO_HATS] * 8 + [PALMAS] * 16 + [SOLO_HATS] * 8 + [PALMAS] * 16

cancion = Cancion(
    "Amanecer Digital", 7, instrumentos,
    {"pulso1": lead, "pulso2": pluck, "triangulo": bajo, "ruido": ruido, "dpcm": dpcm},
    {"pulso1": "Sintetizador", "pulso2": "Pluck", "triangulo": "Bajo", "ruido": "Platillo", "dpcm": "Percusion"},
    muestras,
)
escribir(cancion, AQUI / "amanecer.txt")
