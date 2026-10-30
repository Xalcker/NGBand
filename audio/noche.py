"""Noche sin Estrellas: tema oscuro en Re menor (150 BPM). Luce el teclado con arpegios rapidos.

Uso (desde la raiz del repositorio):  uv run python audio/noche.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, arpegio, escribir

AQUI = Path(__file__).parent
RE_MENOR = Escala(["D", "E", "F", "G", "A", "A#", "C"])

instrumentos = {
    "Lamento": Instrumento([13, 13, 12, 12, 11, 11, 10, 10, 9, 9], [1]),
    "Arpegio": Instrumento([10, 9, 8, 7, 6, 5], [0]),
    "Coro": Instrumento([10, 10, 9, 9, 8, 8], [2]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Melodia (pulso 1). A# es el Si bemol. ------------------------------------------------------------------
estrofa = [
    "D5:6 F5:2 A5:4 G5:4",  # Re menor
    "F5:6 D5:2 A#4:8",  # Si bemol
    "G5:4 A#5:4 D6:8",  # Sol menor
    "E5:8 A5:4 C6:4",  # La menor
    "A5:4 G5:2 F5:2 E5:4 D5:4",  # Re menor
    "D6:6 C6:2 A#5:8",  # Si bemol
    "C6:4 G5:4 E5:4 G5:4",  # Do
    "D5:12 D#5:2 E5:2",  # Re menor (el Mi bemol da la tension)
]
coro = [
    "A#5:2 D6:2 F6:4 D6:2 A#5:2 D6:4",  # Si bemol
    "C6:2 E6:2 G6:4 E6:2 C6:2 E6:4",  # Do
    "D6:6 A5:2 F5:8",  # Re menor
    "A5:4 D6:4 F6:8",  # Re menor
    "G5:2 A#5:2 D6:4 A#5:2 G5:2 A#5:4",  # Sol menor
    "F6:4 D6:4 A#5:4 D6:4",  # Si bemol
    "E6:6 C6:2 A5:8",  # La menor
    "A5:4 C6:4 E6:8",  # La menor
]
puente = [
    "D5:8 D#5:4 E5:4",  # Re menor
    "F5:8 E5:4 D5:4",  # Re menor
    "A#4:8 C5:4 D5:4",  # Si bemol
    "C#5:8 E5:4 A5:4",  # La (con la sensible)
]
final = [
    "D5:6 F5:2 A5:8",  # Re menor
    "A#4:8 D5:8",  # Si bemol
    "A4:4 C#5:4 E5:8",  # La
    "D5:16",  # Re menor
]
lamento = ["@Lamento " + estrofa[0]] + estrofa[1:4] + estrofa + coro + estrofa + puente + coro + coro + final

raices_estrofa = ["D3", "A#2", "G2", "A2", "D3", "A#2", "C3", "D3"]
raices_coro = ["A#2", "C3", "D3", "D3", "G2", "A#2", "A2", "A2"]
raices_puente = ["D3", "D3", "A#2", "A2"]
raices_final = ["D3", "A#2", "A2", "D3"]
raices = (
    raices_estrofa[:4] + raices_estrofa + raices_coro + raices_estrofa + raices_puente
    + raices_coro * 2 + raices_final
)

# --- Pulso 2: arpegios rapidos (una fila por nota) y terceras bajo la melodia en el coro ---------------------
RAPIDO = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1, 2, 3]
def rapido(r):
    return arpegio(r, RE_MENOR, RAPIDO, 1)

arpegios = ["@Arpegio " + rapido(raices_estrofa[0])] + [rapido(r) for r in raices_estrofa[1:4]]
arpegios += [rapido(r) for r in raices_estrofa]
arpegios += ["@Coro " + armonizar(coro[0], RE_MENOR, -2)] + [armonizar(c, RE_MENOR, -2) for c in coro[1:]]
arpegios += ["@Arpegio " + rapido(raices_estrofa[0])] + [rapido(r) for r in raices_estrofa[1:]]
arpegios += [rapido(r) for r in raices_puente]
arpegios += ["@Coro " + armonizar(coro[0], RE_MENOR, -2)] + [armonizar(c, RE_MENOR, -2) for c in coro[1:]]
arpegios += [armonizar(c, RE_MENOR, -2) for c in coro]
arpegios += ["@Arpegio " + rapido(r) for r in raices_final]

# --- Triangulo: pulso constante en la estrofa, salto en el coro, pedal en el puente --------------------------
def pulso(r):
    return " ".join([f"{r}:2"] * 8)

def salto(r):
    return f"{r}:4 {r}:2 {r}:2 {r}:4 {r}:2 {r}:2"

bajo = [pulso(r) for r in raices_estrofa[:4] + raices_estrofa]
bajo += [salto(r) for r in raices_coro]
bajo += [pulso(r) for r in raices_estrofa]
bajo += [f"{r}:16" for r in raices_puente]
bajo += [salto(r) for r in raices_coro * 2]
bajo += [pulso(r) for r in raices_final[:3]] + [f"{raices_final[3]}:16"]

# --- Bateria: lenta y pesada -------------------------------------------------------------------------------
ESTROFA_B = "K...H...S..K.H.."
CORO_B = "K.H.S.H.K.KHS.H."
PUENTE_B = "H...H...H...H..."
RELLENO = "K.H.S.H.SSKKSSSS"
ruido = [ESTROFA_B] * 3 + [RELLENO]
ruido += [ESTROFA_B] * 7 + [RELLENO]
ruido += [CORO_B] * 7 + [RELLENO]
ruido += [ESTROFA_B] * 7 + [RELLENO]
ruido += [PUENTE_B] * 3 + [RELLENO]
ruido += ([CORO_B] * 7 + [RELLENO]) * 2
ruido += [ESTROFA_B] * 3 + ["K..............."]

cancion = Cancion(
    "Noche sin Estrellas", 6, instrumentos,
    {"pulso1": lamento, "pulso2": arpegios, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Lamento", "pulso2": "Arpegio", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "noche.txt")
