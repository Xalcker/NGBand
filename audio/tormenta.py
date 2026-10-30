"""Tormenta de Neon: rock rapido en La menor (180 BPM). Luce la guitarra (pulso 1).

Uso (desde la raiz del repositorio):  uv run python audio/tormenta.py
"""

from pathlib import Path

from compose import Cancion, Escala, Instrumento, armonizar, arpegio, escribir

AQUI = Path(__file__).parent
LA_MENOR = Escala(["A", "B", "C", "D", "E", "F", "G"])

instrumentos = {
    "Guitarra": Instrumento([13, 13, 12, 12, 11, 11, 10, 10], [1]),
    "Teclado": Instrumento([9, 8, 8, 7, 6, 5, 4, 3], [2]),
    "Coro": Instrumento([10, 10, 9, 9, 8, 8], [2]),
    "Bajo": Instrumento(),
    "Bombo": Instrumento([15, 12, 9, 6, 3, 1, 0]),
    "Tarola": Instrumento([13, 11, 8, 6, 4, 2, 1, 0]),
    "Platillo": Instrumento([7, 4, 2, 0]),
    "Abierto": Instrumento([9, 7, 6, 5, 4, 3, 2, 1, 0]),
}

# --- Melodia (pulso 1), un compas por cadena: 16 filas cada uno ---------------------------------
estrofa = [
    "A4:2 C5:2 E5:4 r:2 E5:2 D5:2 C5:2",  # La menor
    "F5:4 E5:2 C5:2 A4:4 r:2 C5:2",  # Fa
    "G4:2 C5:2 E5:4 G5:4 E5:2 C5:2",  # Do
    "D5:4 B4:2 D5:2 G5:6 r:2",  # Sol
    "E5:2 E5:2 A5:4 G5:2 E5:2 C5:4",  # La menor
    "A5:4 G5:2 F5:2 E5:4 C5:4",  # Fa
    "D5:2 G5:2 B5:4 A5:2 G5:2 D5:4",  # Sol
    "E5:8 r:4 G5:2 B5:2",  # Mi menor
]
coro = [
    "C6:4 A5:4 F5:4 A5:4",  # Fa
    "D6:4 B5:4 G5:4 B5:4",  # Sol
    "E6:6 C6:2 A5:4 C6:4",  # La menor
    "B5:6 G5:2 E5:8",  # Mi menor
    "C6:2 C6:2 A5:4 F5:2 A5:2 C6:4",  # Fa
    "D6:2 D6:2 B5:4 G5:2 B5:2 D6:4",  # Sol
    "E6:4 D6:2 C6:2 A5:8",  # La menor
    "A5:8 E5:2 A5:2 C6:4",  # La menor (vuelve a la estrofa)
]
puente = [
    "D5:8 F5:4 A5:4",  # Re menor
    "E5:8 C5:4 E5:4",  # La menor
    "F5:6 A5:2 C6:8",  # Fa
    "B5:4 A5:4 G5:4 D5:4",  # Sol
]
intro = [
    "A4:2 A4:2 r:2 A4:2 A4:2 r:2 C5:2 r:2",  # riff de calentamiento sobre La menor
    "F4:2 F4:2 r:2 F4:2 F4:2 r:2 A4:2 r:2",  # y sobre Fa
    estrofa[0],
    estrofa[1],
]
final = [
    "A5:4 E5:4 C5:4 A4:4",
    "G5:4 D5:4 B4:4 G4:4",
    "A5:4 C6:4 E6:4 A5:4",
    "A5:16",
]
pulso1 = ["@Guitarra " + intro[0]] + intro[1:] + estrofa + coro + estrofa + puente + puente + coro + coro + final

# --- Acordes por compas (raiz del bajo): de aqui salen el bajo y el acompanamiento ---------------
raices_intro = ["A2", "F2", "A2", "F2"]
raices_estrofa = ["A2", "F2", "C3", "G2", "A2", "F2", "G2", "E2"]
raices_coro = ["F2", "G2", "A2", "E2", "F2", "G2", "A2", "A2"]
raices_puente = ["D3", "A2", "F2", "G2"]
raices_final = ["A2", "G2", "A2", "A2"]
raices = (
    raices_intro + raices_estrofa + raices_coro + raices_estrofa + raices_puente * 2
    + raices_coro * 2 + raices_final
)

# --- Pulso 2: arpegios en la estrofa, terceras bajo la melodia en el coro, acordes largos en el puente
ARPEGIO = [0, 1, 2, 1, 0, 1, 2, 1]
LENTO = [0, 1, 2, 3]
def acomp(r, orden=ARPEGIO, filas=2):
    return arpegio(r, LA_MENOR, orden, filas)

pulso2 = ["@Teclado " + acomp(raices_intro[0])] + [acomp(r) for r in raices_intro[1:]]
pulso2 += [acomp(r) for r in raices_estrofa]
pulso2 += ["@Coro " + armonizar(coro[0], LA_MENOR, -2)] + [armonizar(c, LA_MENOR, -2) for c in coro[1:]]
pulso2 += ["@Teclado " + acomp(raices_estrofa[0])] + [acomp(r) for r in raices_estrofa[1:]]
pulso2 += ["@Coro " + acomp(r, LENTO, 4) for r in raices_puente] * 2
pulso2 += ["@Coro " + armonizar(coro[0], LA_MENOR, -2)] + [armonizar(c, LA_MENOR, -2) for c in coro[1:]]
pulso2 += [armonizar(c, LA_MENOR, -2) for c in coro]
pulso2 += ["@Teclado " + acomp(r) for r in raices_final]

# --- Triangulo: corcheas en la estrofa, galope en el coro, notas largas en el puente ----------------
def bajo_corcheas(r):
    alta = r[0] + str(int(r[1:]) + 1)
    return f"{r}:2 {r}:2 {alta}:2 {r}:2 {r}:2 {r}:2 {alta}:2 {r}:2"

def bajo_galope(r):
    return f"{r}:2 {r}:1 {r}:1 {r}:2 {r}:2 {r}:2 {r}:1 {r}:1 {r}:2 {r}:2"

def bajo_largo(r):
    alta = r[0] + str(int(r[1:]) + 1)
    return f"{r}:8 {alta}:4 {r}:4"

# Las raices con sostenido no existen en esta tonalidad, asi que la octava es solo cambiar el numero.
bajo = [bajo_corcheas(r) for r in raices_intro + raices_estrofa]
bajo += [bajo_galope(r) for r in raices_coro]
bajo += [bajo_corcheas(r) for r in raices_estrofa]
bajo += [bajo_largo(r) for r in raices_puente] * 2
bajo += [bajo_galope(r) for r in raices_coro * 2]
bajo += [bajo_corcheas(r) for r in raices_final[:3]] + [f"{raices_final[3]}:16"]

# --- Bateria (16 caracteres por compas) -------------------------------------------------------------
RITMO = "K.H.S.H.K.H.S.H."
RELLENO = "K.H.S.H.SSKKSSSS"
CORO = "K.O.S.O.K.K.S.O."
PUENTE = "K...S...K.K.S..."
SOLO_HAT = "H.H.H.H.H.H.H.H."
def con_relleno(base, n):
    return [base] * (n - 1) + [RELLENO]

ruido = [SOLO_HAT, SOLO_HAT, RITMO, RELLENO]
ruido += con_relleno(RITMO, 8)
ruido += con_relleno(CORO, 8)
ruido += con_relleno(RITMO, 8)
ruido += [PUENTE] * 3 + [RELLENO] + [PUENTE] * 3 + [RELLENO]
ruido += con_relleno(CORO, 8) * 2
ruido += [RITMO, RITMO, RITMO, "K..............."]

cancion = Cancion(
    "Tormenta de Neon", 5, instrumentos,
    {"pulso1": pulso1, "pulso2": pulso2, "triangulo": bajo, "ruido": ruido},
    {"pulso1": "Guitarra", "pulso2": "Teclado", "triangulo": "Bajo", "ruido": "Bombo"},
)
escribir(cancion, AQUI / "tormenta.txt")
