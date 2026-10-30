"""Carrera de Fuego: rock de arcade en Re mayor (180 BPM) con bombo y tarola en DPCM.
Guitarra y teclado se turnan la melodia como un duelo.

Uso (desde la raiz del repositorio):  uv run python audio/carrera.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, arpegio, bombo_dpcm, escribir, nombre, tarola_dpcm

AQUI = Path(__file__).parent
RE_MAYOR = Escala(["D", "E", "F#", "G", "A", "B", "C#"])

instrumentos = {
    "Guitarra": Instrumento([13, 13, 12, 12, 11, 11, 10, 10], [1]),
    "Organo": Instrumento([9, 9, 8, 8, 7, 7], [2]),
    "Coro": Instrumento([11, 11, 10, 10, 9, 9], [2]),
    "Bajo": Instrumento(),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
    "Percusion": Instrumento(mapeo=[("C1", "Bombo"), ("C#1", "Tarola")]),
}
muestras = {"Bombo": bombo_dpcm(), "Tarola": tarola_dpcm()}

# --- Estrofa: la guitarra lleva la melodia -------------------------------------------------------------------
estrofa = [
    "D5:3 D5:1 F#5:2 A5:2 F#5:4 D5:4",  # Re
    "E5:3 E5:1 A5:2 C#6:2 B5:4 A5:4",  # La
    "D6:4 B5:2 D6:2 F#6:4 D6:4",  # Si menor
    "B5:3 B5:1 D6:2 G6:2 F#6:4 D6:4",  # Sol
    "D5:3 D5:1 F#5:2 A5:2 F#5:4 D5:4",  # Re
    "E5:2 A5:2 C#6:4 E6:4 C#6:4",  # La
    "B5:4 G5:4 D5:4 G5:4",  # Sol
    "E5:8 A5:4 C#6:4",  # La
]
# --- Coro: el organo lleva la melodia y la guitarra la armoniza una tercera abajo -----------------------------
coro = [
    "B5:4 D6:4 G6:4 D6:4",  # Sol
    "A5:4 D6:4 F#6:4 D6:4",  # Re
    "C#6:6 E6:2 A6:8",  # La
    "E6:4 C#6:4 A5:8",  # La
    "B5:2 D6:2 G6:4 F#6:4 D6:4",  # Sol
    "F#6:4 A6:4 F#6:4 D6:4",  # Re
    "E6:2 C#6:2 A5:4 C#6:4 E6:4",  # La
    "D6:16",  # Re
]
# --- Puente: el organo canta y la guitarra hace arpegios veloces ------------------------------------------------
puente = [
    "D6:8 B5:4 F#5:4",  # Si menor
    "B5:4 D6:4 F#6:8",  # Si menor
    "G5:8 B5:4 D6:4",  # Sol
    "E6:8 C#6:4 A5:4",  # La
    "D6:4 F#6:4 D6:8",  # Si menor
    "B5:4 G5:4 D6:8",  # Sol
    "C#6:4 E6:4 A5:8",  # La
    "A5:16",  # La
]
final = [
    "D5:4 F#5:4 A5:4 D6:4",  # Re
    "E5:4 A5:4 C#6:4 E6:4",  # La
    "B5:4 G5:4 D5:4 B4:4",  # Sol
    "D5:16",  # Re
]

raices_estrofa = ["D3", "A2", "B2", "G2", "D3", "A2", "G2", "A2"]
raices_coro = ["G2", "D3", "A2", "A2", "G2", "D3", "A2", "D3"]
raices_puente = ["B2", "B2", "G2", "A2", "B2", "G2", "A2", "A2"]
raices_final = ["D3", "A2", "G2", "D3"]
raices = (
    raices_estrofa[:4] + raices_estrofa + raices_coro + raices_estrofa + raices_coro
    + raices_puente + raices_coro + raices_final
)

# --- Pulso 1 (guitarra) ---------------------------------------------------------------------------------------------
RAPIDO = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1, 2, 3]
def armonia(compases):
    return [armonizar(c, RE_MAYOR, -2) for c in compases]

def con(instrumento, compases):
    return ["@" + instrumento + " " + compases[0]] + compases[1:]

guitarra = con("Guitarra", estrofa[:4] + estrofa)
guitarra += con("Coro", armonia(coro))
guitarra += con("Guitarra", estrofa)
guitarra += con("Coro", armonia(coro))
guitarra += con("Guitarra", [arpegio(r, RE_MAYOR, RAPIDO, 1) for r in raices_puente])
guitarra += con("Coro", armonia(coro))
guitarra += con("Guitarra", final)

# --- Pulso 2 (organo): corcheas bombeadas en la estrofa, melodia en el coro y el puente ---------------------------
def bombeo(r):
    t = RE_MAYOR.triada(r)
    notas = [nombre(t[0] + 12), nombre(t[2] + 12)] * 4
    return " ".join(f"{n}:1 r:1" for n in notas)

organo = con("Organo", [bombeo(r) for r in raices_estrofa[:4] + raices_estrofa])
organo += con("Organo", coro)
organo += con("Organo", [bombeo(r) for r in raices_estrofa])
organo += con("Organo", coro)
organo += con("Organo", puente)
organo += con("Organo", coro)
organo += con("Organo", [bombeo(r) for r in raices_final])

# --- Triangulo ------------------------------------------------------------------------------------------------------
def corcheas(r):
    alta = r[0] + str(int(r[1:]) + 1)
    return f"{r}:2 {r}:2 {alta}:2 {r}:2 {r}:2 {r}:2 {alta}:2 {r}:2"

def negras(r):
    return f"{r}:4 {r}:4 {r}:4 {r}:4"

bajo = (
    [corcheas(r) for r in raices_estrofa[:4] + raices_estrofa + raices_coro + raices_estrofa + raices_coro]
    + [negras(r) for r in raices_puente]
    + [corcheas(r) for r in raices_coro]
    + [corcheas(r) for r in raices_final[:3]] + [f"{raices_final[3]}:16"]
)

# --- Bateria: hats en el ruido, bombo y tarola en DPCM --------------------------------------------------------------
HATS = "H.H.H.H.H.H.H.H."
HATS_CORO = "O.H.O.H.O.H.O.H."
HATS_PUENTE = "H.......H......."
GOLPE = "K...S...K.K.S..."
GOLPE_CORO = "K.K.S.K.K.K.S.S."
GOLPE_PUENTE = "K.......S......."
RELLENO = "K...S...KKSSSSSS"
def seccion(base, n):
    return [base] * (n - 1) + [RELLENO]

dpcm = [GOLPE] * 3 + [RELLENO]
dpcm += seccion(GOLPE, 8) + seccion(GOLPE_CORO, 8) + seccion(GOLPE, 8) + seccion(GOLPE_CORO, 8)
dpcm += seccion(GOLPE_PUENTE, 8) + seccion(GOLPE_CORO, 8)
dpcm += [GOLPE] * 3 + ["K..............."]

ruido = [HATS] * 4 + [HATS] * 8 + [HATS_CORO] * 8 + [HATS] * 8 + [HATS_CORO] * 8
ruido += [HATS_PUENTE] * 8 + [HATS_CORO] * 8 + [HATS] * 4

cancion = Cancion(
    "Carrera de Fuego", 5, instrumentos,
    {"pulso1": guitarra, "pulso2": organo, "triangulo": bajo, "ruido": ruido, "dpcm": dpcm},
    {"pulso1": "Guitarra", "pulso2": "Organo", "triangulo": "Bajo", "ruido": "Platillo", "dpcm": "Percusion"},
    muestras,
)
escribir(cancion, AQUI / "carrera.txt")
