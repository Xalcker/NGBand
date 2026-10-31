"""Compilador de gráficos de NGBand: `ngband gfx` (R1.9, R5.1-R5.3, R7.7).
Los gráficos se generan en compilación, no al arrancar la ROM. Salidas en --out:
  gfx_c1.bin, gfx_c2.bin  ROM C: tiles de sprite de 16x16, 4 bpp, repartidos en dos ROM (planos 0-1 y 2-3)
  gfx_s.bin               ROM S: tiles fijos de 8x8 (la Fix_Layer): la fuente Bongo-8 Mono y símbolos
  gfx_data.h / gfx_data.c  PerspRow persp[], niveles de gema, paletas y la posición de cada arte en la ROM C
Los formatos de tile siguen el de la Neo Geo (ver encode_crom_tile y encode_srom_tile).
El arte sale de dos sitios: las gemas se dibujan aquí (7 tamaños, 5 carriles + estelar) y los PNG de
assets/gfx/*.png (anchos y altos múltiplos de 16, hasta 15 colores y transparencia) se añaden después.
La fuente se lee de assets/fonts/bongo8_glyphs.txt (versionado, no necesita Pillow); para regenerarlo
desde la TTF hace falta Pillow:  uv run --with pillow ngband gfx --rebuild-font
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from . import png

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"

# --- Tabla de perspectiva (R5.1, R5.2) ---------------------------------------------------------------
NUM_LANES = 5
GEM_LEVELS = 7           # R5.3: al menos 7 tamaños de gema
HSHRINK_MAX = 15
VSHRINK_MAX = 255
# Pantalla de 320x224: horizonte, línea de golpe y anchos del trapecio (en píxeles)
Y_HORIZON, Y_HIT, W_HORIZON, W_HIT, X_CENTER, Y_PAST_HIT = 48, 184, 80, 200, 160, 24


@dataclass(frozen=True)
class PerspRow:
    y: int
    hshrink: int
    vshrink: int
    x_lane: tuple[int, ...]
    width: int               # ancho del trapecio en esa fila (no va a la ROM; sirve para las pruebas)
    gem_level: int


def build_persp(y_h: int = Y_HORIZON, y_g: int = Y_HIT, w_h: int = W_HORIZON, w_g: int = W_HIT,
                x_center: int = X_CENTER, y_end: int | None = None) -> list[PerspRow]:
    """Una fila por línea de pantalla desde el horizonte (fila 0) hasta `y_end` (por defecto, un poco
    más abajo de la línea de golpe, para las Notes perdidas). El ancho crece linealmente con y, y la
    escala es s = ancho / w_g (s = 1 en la línea de golpe): hshrink = round(15 s), vshrink = round(255 s)."""
    if not (0 <= y_h < y_g) or not (0 < w_h <= w_g):
        raise ValueError("hace falta 0 <= horizonte < línea de golpe y 0 < w_h <= w_g")
    if y_end is None:
        y_end = y_g + Y_PAST_HIT
    if y_end < y_g:
        raise ValueError("y_end debe estar en la línea de golpe o más abajo")
    rows = []
    for y in range(y_h, y_end + 1):
        width = w_h + (w_g - w_h) * (y - y_h) / (y_g - y_h)
        s = width / w_g
        hs = min(HSHRINK_MAX, round(HSHRINK_MAX * s))
        vs = min(VSHRINK_MAX, round(VSHRINK_MAX * s))
        # los GEM_LEVELS niveles se reparten entre la escala del horizonte y la de la línea de golpe
        t = (min(s, 1.0) - w_h / w_g) / (1 - w_h / w_g) if w_h < w_g else 1.0
        level = min(GEM_LEVELS - 1, int(t * GEM_LEVELS))
        lanes = tuple(x_center + round((i - NUM_LANES // 2) * width / NUM_LANES) for i in range(NUM_LANES))
        rows.append(PerspRow(y, hs, vs, lanes, round(width), level))
    return rows


def gem_scale(level: int) -> tuple[int, int]:
    """(hshrink, vshrink) base de un nivel de gema: el nivel L ocupa (L+1)/GEM_LEVELS del tamaño completo."""
    s = (level + 1) / GEM_LEVELS
    return round(HSHRINK_MAX * s), round(VSHRINK_MAX * s)


# --- Formatos de tile de la Neo Geo ------------------------------------------------------------------
def encode_crom_tile(tile: bytes) -> tuple[bytes, bytes]:
    """Tile de 16x16 (un byte por píxel, 0..15) -> (bytes para C1, bytes para C2), 64 cada uno.
    Cuatro bloques de 8x8 en el orden superior-derecho, inferior-derecho, superior-izquierdo,
    inferior-izquierdo; por renglón, los planos 0 y 1 van a C1 y los 2 y 3 a C2 (el bit x es el
    píxel x del bloque)."""
    if len(tile) != 256:
        raise ValueError("un tile de sprite es de 16x16 píxeles")
    c1, c2 = bytearray(), bytearray()
    for start in (8, 136, 0, 128):
        for y in range(8):
            planes = [0, 0, 0, 0]
            for x in range(8):
                col = tile[start + y * 16 + x]
                if col > 15:
                    raise ValueError("color de tile fuera de 0..15")
                for p in range(4):
                    planes[p] |= ((col >> p) & 1) << x
            c1 += bytes(planes[:2])
            c2 += bytes(planes[2:])
    return bytes(c1), bytes(c2)


def encode_srom_tile(tile: bytes) -> bytes:
    """Tile fijo de 8x8 (un byte por píxel) -> 32 bytes: columnas (4,5), (6,7), (0,1), (2,3), cada
    una como 8 renglones de un byte (píxel par en el nibble bajo)."""
    if len(tile) != 64:
        raise ValueError("un tile fijo es de 8x8 píxeles")
    out = bytearray()
    for xa, xb in ((4, 5), (6, 7), (0, 1), (2, 3)):
        for y in range(8):
            out.append((tile[y * 8 + xb] << 4) | tile[y * 8 + xa])
    return bytes(out)


def neo_color(r: int, g: int, b: int, dark: bool = False) -> int:
    """Color de 16 bits de la Neo Geo: bit 15 oscuro, bits 14-12 = LSB de R, G, B, y R/G/B en los
    nibbles altos (4 bits cada uno); los canales de 8 bits se reducen a 5."""
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    return ((int(dark) << 15) | ((r5 & 1) << 14) | ((g5 & 1) << 13) | ((b5 & 1) << 12)
            | ((r5 >> 1) << 8) | ((g5 >> 1) << 4) | (b5 >> 1))


# --- Arte dibujado aquí: gemas -----------------------------------------------------------------------
GEM_OUTLINE, GEM_BODY, GEM_LIGHT, GEM_SHADE = 1, 2, 3, 4
LANE_COLORS = {
    "verde": (60, 220, 80), "rojo": (240, 60, 60), "amarillo": (250, 230, 60),
    "azul": (70, 120, 250), "naranja": (250, 150, 40),
}
STAR_COLOR = (240, 240, 255)


def _inside(dx2: int, dy2: int, a: int, b: int) -> bool:
    return dx2 * dx2 * b * b + dy2 * dy2 * a * a <= a * a * b * b


def draw_gem(level: int) -> bytes:
    """Gema de 16x16 para el nivel de tamaño `level`. El arte siempre llena el tile (el hardware lo
    reduce); los niveles lejanos llevan menos detalle para que no parpadee al reducirse."""
    if not 0 <= level < GEM_LEVELS:
        raise ValueError("nivel de gema fuera de rango")
    px = bytearray(256)
    for y in range(16):
        for x in range(16):
            dx2, dy2 = abs(2 * x - 15), abs(2 * y - 15)
            if not _inside(dx2, dy2, 16, 14):
                continue
            c = GEM_BODY
            if level >= 2 and not _inside(dx2, dy2, 12, 10):
                c = GEM_OUTLINE
            elif level >= 3 and y >= 10:
                c = GEM_SHADE
            elif level >= 4 and 3 <= x <= 6 and 3 <= y <= 5:
                c = GEM_LIGHT
            px[y * 16 + x] = c
    return bytes(px)


def _shade(rgb: tuple[int, int, int], num: int, den: int) -> tuple[int, int, int]:
    return tuple(c * num // den for c in rgb)  # type: ignore[return-value]


def gem_palette(rgb: tuple[int, int, int]) -> list[int]:
    light = tuple(min(255, c + (255 - c) // 2) for c in rgb)
    cols = [0] * 16
    cols[GEM_OUTLINE] = neo_color(*_shade(rgb, 1, 4))
    cols[GEM_BODY] = neo_color(*rgb)
    cols[GEM_LIGHT] = neo_color(*light)
    cols[GEM_SHADE] = neo_color(*_shade(rgb, 3, 5))
    return cols


# Piezas de la autopista con la paleta de la gema (la del carril): la cola es una barra continua (se encoge
# a lo ancho y se estira a lo alto, así que el tile entero es cuerpo), el bombo una banda que se repite de lado
# sin cortes y el platillo un rombo.
def draw_tail() -> bytes:
    px = []
    for _ in range(16):
        for x in range(16):
            px.append(GEM_OUTLINE if x in (0, 15) else GEM_LIGHT if 6 <= x <= 8 else GEM_BODY)
    return bytes(px)


def draw_kick() -> bytes:
    px = []
    for y in range(16):
        for _ in range(16):
            px.append(0 if y < 4 or y > 11 else GEM_OUTLINE if y in (4, 11) else GEM_LIGHT if y == 5 else
                      GEM_SHADE if y == 10 else GEM_BODY)
    return bytes(px)


def draw_cymbal() -> bytes:
    px = []
    for y in range(16):
        for x in range(16):
            d = abs(x - 7.5) / 7.5 + abs(y - 7.5) / 7.5
            px.append(0 if d > 1 else GEM_OUTLINE if d > 0.8 else GEM_LIGHT if y < 6 else GEM_BODY)
    return bytes(px)


HWY_PIECES = (("COLA", draw_tail), ("BOMBO", draw_kick), ("ROMBO", draw_cymbal))


# --- Arte dibujado aquí: escenario (R11.1) -----------------------------------------------------------
# Las 10 paletas del escenario comparten los colores fijos (0..11) y cambian solo los de luz (12..15):
#   fase 0..3 (cian, rojo, amarillo, violeta) x {tenue, latido} = 0..7;  8 = luces apagadas;  9 = destello.
ESC_CLEAR, ESC_BLACK, ESC_CABINET, ESC_GRILLE, ESC_METAL, ESC_SHINE, ESC_AMBER, ESC_DARK, ESC_LIT = range(9)
ESC_LIGHT_DIM, ESC_LIGHT, ESC_LIGHT_HI, ESC_WHITE = 12, 13, 14, 15
STAGE_PAL_COUNT = 10
STAGE_PAL_OFF, STAGE_PAL_FLASH = 8, 9
LIGHT_PHASES = ((60, 220, 255), (255, 60, 60), (250, 230, 60), (170, 80, 255))   # cian, rojo, amarillo, violeta
ESC_FIXED = {ESC_BLACK: (4, 4, 8), ESC_CABINET: (52, 52, 64), ESC_GRILLE: (28, 28, 36), ESC_METAL: (110, 110, 140),
             ESC_SHINE: (170, 170, 200), ESC_AMBER: (224, 160, 64), ESC_DARK: (14, 10, 24), ESC_LIT: (58, 44, 88)}
BOLT_SEGMENT_H = 16
class Tile:
    """Lienzo de w x h píxeles con índices de color 0..15."""
    def __init__(self, w: int = 16, h: int = 16) -> None:
        self.w, self.h = w, h
        self.px = [[0] * w for _ in range(h)]
    def set(self, x: int, y: int, c: int) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c
    def rect(self, x0: int, y0: int, x1: int, y1: int, c: int) -> None:
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.set(x, y, c)
    def disc(self, cx: float, cy: float, r: float, c: int) -> None:
        for y in range(self.h):
            for x in range(self.w):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.set(x, y, c)
    def tiles(self) -> list[bytes]:
        """Tiles de 16x16 de una columna, de arriba abajo."""
        return [bytes(self.px[ty * 16 + y][x] for y in range(16) for x in range(16)) for ty in range(self.h // 16)]
def draw_speaker() -> Tile:
    """Bocina de 16x32: gabinete con rejilla, tweeter arriba, woofer abajo y un piloto ámbar."""
    t = Tile(16, 32)
    t.rect(0, 0, 16, 32, ESC_BLACK)
    t.rect(1, 1, 15, 31, ESC_CABINET)
    t.rect(2, 2, 14, 30, ESC_GRILLE)
    for y in range(2, 30):
        for x in range(2, 14):
            if (x + y) % 3 == 0:
                t.set(x, y, ESC_BLACK)
    t.disc(7.5, 9.5, 3.5, ESC_BLACK)
    t.disc(7.5, 9.5, 2.5, ESC_CABINET)
    t.disc(7.5, 9.5, 1, ESC_METAL)
    t.disc(7.5, 21.5, 5.5, ESC_BLACK)
    t.disc(7.5, 21.5, 4.5, ESC_CABINET)
    t.disc(7.5, 21.5, 3, ESC_GRILLE)
    t.disc(7.5, 21.5, 1.5, ESC_METAL)
    t.rect(3, 28, 6, 29, ESC_AMBER)
    return t
def draw_lamp() -> Tile:
    """Cabeza de foco de 16x16: soporte, lata y lente encendido (colores de luz)."""
    t = Tile()
    t.rect(6, 0, 10, 3, ESC_METAL)
    t.rect(2, 3, 14, 11, ESC_CABINET)
    t.rect(2, 3, 14, 4, ESC_SHINE)
    t.rect(1, 11, 15, 15, ESC_BLACK)
    t.rect(2, 11, 14, 14, ESC_LIGHT)
    t.rect(4, 11, 12, 13, ESC_LIGHT_HI)
    return t
def draw_truss() -> Tile:
    """Torre de 16x32: dos tubos con diagonales en zigzag."""
    t = Tile(16, 32)
    for y in range(32):
        for x in (4, 5, 10, 11):
            t.set(x, y, ESC_METAL if x in (5, 10) else ESC_SHINE)
    for y0 in range(0, 32, 8):
        down = (y0 // 8) % 2 == 0
        for i in range(8):
            t.set(6 + i // 2 if down else 9 - i // 2, y0 + i, ESC_METAL)
    t.rect(2, 30, 14, 32, ESC_BLACK)
    return t
def draw_beam() -> Tile:
    """Haz de 16x32 que baja hacia la izquierda y se abre: trama de un píxel sí y otro no."""
    t = Tile(16, 32)
    for y in range(32):
        center = 13 - y * 11 / 31
        half = 1.5 + y * 3 / 31
        for x in range(16):
            if abs(x - center) <= half and (x + y) % 2 == 0:
                t.set(x, y, ESC_LIGHT if abs(x - center) <= half / 2 else ESC_LIGHT_DIM)
    return t
def draw_crowd(arms: bool) -> Tile:
    """Público de 16x32 a contraluz: dos siluetas; con brazos arriba se levantan dos trazos. El borde
    de las cabezas usa el color de la luz."""
    t = Tile(16, 32)
    for cx in (4, 11):
        t.disc(cx, 22, 2.5, ESC_DARK)
        t.set(cx - 1, 20, ESC_LIGHT)
        t.set(cx, 19, ESC_LIGHT)
        t.rect(cx - 4, 25, cx + 4, 32, ESC_DARK)
        t.rect(cx - 4, 25, cx + 4, 26, ESC_LIT)
        if arms:
            for k in range(8):
                t.set(cx - 3 + k // 4, 24 - k, ESC_DARK)
                t.set(cx + 3 - k // 4, 24 - k, ESC_DARK)
            t.set(cx - 3, 15, ESC_LIGHT_HI)
            t.set(cx + 3, 15, ESC_LIGHT_HI)
    return t
def draw_bolt() -> Tile:
    """Segmento de rayo de 16x16: zigzag que entra y sale por el centro (se alterna con su espejo)."""
    t = Tile()
    pts = [(8, 0), (4, 5), (11, 9), (8, 15)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(n + 1):
            x, y = x0 + round((x1 - x0) * i / n), y0 + round((y1 - y0) * i / n)
            t.set(x - 1, y, ESC_LIGHT_HI)
            t.set(x + 1, y, ESC_LIGHT_HI)
            t.set(x, y, ESC_WHITE)
    return t
def stage_palette(phase: int, bright: bool) -> list[int]:
    r, g, b = LIGHT_PHASES[phase]
    cols = [0] * 16
    for i, rgb in ESC_FIXED.items():
        cols[i] = neo_color(*rgb)
    if bright:
        light = (r, g, b)
        hi = tuple(min(255, c + (255 - c) // 2) for c in light)
        dim = _shade(light, 1, 2)
    else:
        light = _shade((r, g, b), 1, 2)
        hi = _shade((r, g, b), 3, 4)
        dim = _shade((r, g, b), 1, 4)
    cols[ESC_LIGHT_DIM], cols[ESC_LIGHT], cols[ESC_LIGHT_HI] = (neo_color(*c) for c in (dim, light, hi))
    cols[ESC_WHITE] = neo_color(255, 255, 255)
    return cols
def stage_palettes() -> list[list[int]]:
    """Las STAGE_PAL_COUNT paletas del escenario: 4 fases x {tenue, latido}, apagado y destello."""
    pals = [stage_palette(ph, br) for ph in range(4) for br in (False, True)]
    off = stage_palette(0, False)
    for i in (ESC_LIGHT_DIM, ESC_LIGHT, ESC_LIGHT_HI):
        off[i] = neo_color(10 + 4 * (i - 12), 10 + 4 * (i - 12), 14 + 4 * (i - 12))
    flash = stage_palette(0, True)
    for i, v in ((ESC_LIGHT_DIM, 160), (ESC_LIGHT, 220), (ESC_LIGHT_HI, 255)):
        flash[i] = neo_color(v, v, v)
    return pals + [off, flash]
STAGE_ART = (("ESC_BOCINA", draw_speaker), ("ESC_FOCO", draw_lamp), ("ESC_TORRE", draw_truss),
             ("ESC_HAZ", draw_beam), ("ESC_PUBLICO", lambda: draw_crowd(False)),
             ("ESC_PUBLICO_BRAZOS", lambda: draw_crowd(True)), ("ESC_RAYO", draw_bolt))
# --- Arte dibujado aquí: la pista fija (superficie de la autopista) ---------------------------------
# Un trapecio de 14 columnas x 10 filas de tiles (224 x 160 px) desde el horizonte: superficie, bordes,
# divisores de carril y aros de golpe. Se escribe una vez al empezar la canción; las franjas se mueven
# solas con la autoanimación del LSPC (8 fases: el tile de cada celda es base + fase). Las gemas bajan
# 8 px cada fall_frames en línea recta por la pantalla (highway_layout.c, row_of), así que las franjas
# también: periodo de TRACK_PERIOD px en Y y TRACK_PERIOD / 8 px por fase.
TRACK_COLS, TRACK_ROWS, TRACK_PHASES, TRACK_PERIOD = 14, 10, 8, 32
TRACK_X0 = X_CENTER - TRACK_COLS * 8
TRACK_Y0 = Y_HORIZON
TRK_SURF, TRK_STRIPE, TRK_LANE, TRK_EDGE, TRK_RING_IN = 1, 2, 3, 4, 5
TRK_RING = 6                        # 6..10: aro de cada carril
TRACK_RGB = {TRK_SURF: (18, 28, 74), TRK_STRIPE: (28, 42, 104), TRK_LANE: (70, 90, 190),
             TRK_EDGE: (130, 160, 255), TRK_RING_IN: (30, 30, 52)}
RING_RX, RING_RY = 17, 7


def track_palette() -> list[int]:
    cols = [0] * 16
    for i, rgb in TRACK_RGB.items():
        cols[i] = neo_color(*rgb)
    for i, rgb in enumerate(LANE_COLORS.values()):
        cols[TRK_RING + i] = neo_color(*rgb)
    return cols


# Variantes de la pista: (nombre, carril del Chart de cada columna, para el color del aro). Como en NESBand, se
# dibujan siempre los 5 carriles aunque fácil y medio usen 3 o 4. Con ESPEJO el Judge invierte solo los carriles
# en uso (options_mirror_ev), así que cada cantidad tiene su orden de aros. La batería tiene 4 pads (drum_cols de
# highway_layout.c) y el bombo como barra.
TRACK_VARIANTS = (("PISTA", (0, 1, 2, 3, 4)), ("PISTA_E3", (2, 1, 0, 3, 4)), ("PISTA_E4", (3, 2, 1, 0, 4)),
                  ("PISTA_E5", (4, 3, 2, 1, 0)), ("PISTA_BAT", (1, 2, 3, 0)))


def draw_track(phase: int, persp: list[PerspRow] | None = None, lanes: tuple[int, ...] = (0, 1, 2, 3, 4)) -> Tile:
    """La superficie en la fase `phase` (0..7) con un carril por columna de `lanes` (el carril del Chart de cada
    columna, para el color del aro); las franjas bajan TRACK_PERIOD / 8 px por fase."""
    rows = {r.y: r for r in (persp or build_persp())}
    ncols = len(lanes)
    t = Tile(TRACK_COLS * 16, TRACK_ROWS * 16)
    step = TRACK_PERIOD // TRACK_PHASES
    for py in range(t.h):
        y = TRACK_Y0 + py
        r = rows.get(y)
        if r is None:
            continue
        lane_w = r.width / NUM_LANES
        x0 = X_CENTER - lane_w * ncols / 2
        x1 = X_CENTER + lane_w * ncols / 2
        light = ((y - Y_HIT - step * phase) % TRACK_PERIOD) < TRACK_PERIOD // 2
        for px in range(t.w):
            x = TRACK_X0 + px
            if x0 <= x <= x1:
                t.set(px, py, TRK_STRIPE if light else TRK_SURF)
        for i in range(1, ncols):
            t.set(round(x0 + lane_w * i) - TRACK_X0, py, TRK_LANE)
        for xe in (x0, x1):
            t.set(round(xe) - TRACK_X0, py, TRK_EDGE)
            t.set(round(xe) - TRACK_X0 + (1 if xe == x0 else -1), py, TRK_EDGE)
    hit = rows[Y_HIT]
    for col, lane in enumerate(lanes):
        cx = round(X_CENTER + (col - (ncols - 1) / 2) * hit.width / NUM_LANES)
        for dy in range(-RING_RY, RING_RY + 1):
            for dx in range(-RING_RX, RING_RX + 1):
                d = (dx / RING_RX) ** 2 + (dy / RING_RY) ** 2
                if d > 1:
                    continue
                t.set(cx + dx - TRACK_X0, Y_HIT + dy - TRACK_Y0, TRK_RING + lane if d >= 0.6 else TRK_RING_IN)
    return t


def track_tiles(persp: list[PerspRow] | None = None, lanes: tuple[int, ...] = (0, 1, 2, 3, 4)) -> list[bytes]:
    """Tiles de la pista: por columna y fila, las 8 fases seguidas (la autoanimación cambia los 3 bits bajos)."""
    phases = [draw_track(p, persp, lanes) for p in range(TRACK_PHASES)]
    out = []
    for c in range(TRACK_COLS):
        for r in range(TRACK_ROWS):
            for img in phases:
                out.append(bytes(img.px[r * 16 + y][c * 16 + x] for y in range(16) for x in range(16)))
    return out


# --- Arte desde PNG ----------------------------------------------------------------------------------
def png_to_sprite(path: Path) -> tuple[int, int, list[bytes], list[int]]:
    """(columnas, filas, tiles en orden de columna, paleta de 16 colores) de un PNG. Los tiles van
    columna por columna porque un sprite de la Neo Geo es una columna de tiles. El índice 0 es el
    transparente (alfa < 128); los demás colores se numeran por orden de aparición."""
    width, height, rows = png.decode(path.read_bytes())
    if width % 16 or height % 16 or not width or not height:
        raise ValueError(f"{path.name}: el tamaño ({width}x{height}) debe ser múltiplo de 16")
    index: dict[tuple[int, int, int], int] = {}
    pixels = bytearray(width * height)
    for y, row in enumerate(rows):
        for x, (r, g, b, a) in enumerate(row):
            if a < 128:
                continue
            if (r, g, b) not in index:
                if len(index) == 15:
                    raise ValueError(f"{path.name}: más de 15 colores")
                index[(r, g, b)] = len(index) + 1
            pixels[y * width + x] = index[(r, g, b)]
    cols, nrows = width // 16, height // 16
    tiles = []
    for cx in range(cols):
        for cy in range(nrows):
            tile = bytearray()
            for y in range(16):
                o = (cy * 16 + y) * width + cx * 16
                tile += pixels[o:o + 16]
            tiles.append(bytes(tile))
    palette = [0] * 16
    for rgb, i in index.items():
        palette[i] = neo_color(*rgb)
    return cols, nrows, tiles, palette


# --- Fuente y tiles fijos ----------------------------------------------------------------------------
# Caracteres de la fuente del juego; su tile fijo es su código ASCII
FONT_CHARS = " !%'()*+,-./0123456789:<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TILE_METER = 0x80        # 0x80..0x88: barra horizontal de 0 a 8 píxeles de ancho (vida y Star_Power)
FONT_FILE = ASSETS / "fonts" / "bongo8_glyphs.txt"
FONT_TTF = ASSETS / "fonts" / "Bongo-8_Mono.ttf"
GAME_SYMBOLS = {   # no salen de la fuente
    "*": ["...1....", "...1....", "1111111.", ".11111..", "..111...", ".11.11..", ".1...1..", "........"],
    "<": ["....11..", "...11...", "..11....", ".11.....", "..11....", "...11...", "....11..", "........"],
    ">": [".11.....", "..11....", "...11...", "....11..", "...11...", "..11....", ".11.....", "........"],
}
EMPTY_GLYPH = ["........"] * 8
FIX_PALETTES = {   # color 1 = trazo del texto; la paleta es el atributo del tile
    "blanco": (255, 255, 255), "amarillo": (250, 230, 60), "rojo": (240, 60, 60), "verde": (60, 220, 80),
    "azul": (90, 140, 255), "naranja": (250, 150, 40), "gris": (150, 150, 150),
}
FIX_PALETTE_SLOTS = 16   # las paletas 0..15 son las de la Fix_Layer; las de sprites empiezan en 16


def glyphs_from_ttf(path: Path) -> dict[str, list[str]]:
    """Glifos de FONT_CHARS desde una TTF de píxeles de 8 px, sin suavizado (necesita Pillow)."""
    from PIL import Image, ImageDraw, ImageFont  # solo aquí: compilar la ROM no necesita Pillow
    font = ImageFont.truetype(str(path), 8)
    glyphs = {}
    for ch in FONT_CHARS:
        image = Image.new("L", (8, 8), 0)
        draw = ImageDraw.Draw(image)
        draw.fontmode = "1"
        draw.text((0, 0), ch, font=font, fill=255)
        glyphs[ch] = ["".join("1" if image.getpixel((x, y)) else "." for x in range(8)) for y in range(8)]
    return glyphs


def write_glyph_cache(glyphs: dict[str, list[str]], path: Path) -> None:
    lines = ["# Generado por `ngband gfx --rebuild-font` desde Bongo-8_Mono.ttf (CC0) - no editar a mano",
             "# <código ASCII en hex> <8 renglones de 8 columnas>"]
    lines += [f"{ord(ch):02X} " + " ".join(glyphs[ch]) for ch in FONT_CHARS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def read_glyph_cache(path: Path) -> dict[str, list[str]]:
    glyphs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        code, *rows = line.split()
        if len(rows) != 8 or any(not re.fullmatch(r"[.1]{8}", r) for r in rows):
            raise ValueError(f"{path.name}: glifo mal formado: {line!r}")
        glyphs[chr(int(code, 16))] = rows
    return glyphs


def load_glyphs(font_file: Path = FONT_FILE) -> dict[str, list[str]]:
    return read_glyph_cache(font_file)


def fix_tiles(glyphs: dict[str, list[str]]) -> dict[int, bytes]:
    """Tiles fijos por número: la fuente (número = código ASCII) y las barras de medidor."""
    tiles: dict[int, bytes] = {}
    for ch in FONT_CHARS:
        rows = GAME_SYMBOLS.get(ch) or glyphs.get(ch) or EMPTY_GLYPH
        if len(rows) != 8 or any(len(r) != 8 for r in rows):
            raise ValueError(f"el glifo de {ch!r} no es de 8x8")
        tiles[ord(ch)] = bytes(1 if c == "1" else 0 for r in rows for c in r)
    for n in range(9):
        tiles[TILE_METER + n] = bytes(1 if x < n and 1 <= y <= 6 else 0 for y in range(8) for x in range(8))
    return tiles


# --- Armado ------------------------------------------------------------------------------------------
@dataclass
class SpriteArt:
    name: str
    first_tile: int
    cols: int
    rows: int
    palette: int


@dataclass
class GfxResult:
    c1: bytes
    c2: bytes
    srom: bytes
    palettes: list[list[int]]
    sprites: list[SpriteArt]
    gem_tiles: list[int]       # primer tile de cada nivel de gema
    persp: list[PerspRow]
    stage_pal: int = 0         # primera de las STAGE_PAL_COUNT paletas del escenario


def _ident(name: str) -> str:
    return re.sub(r"\W", "_", name).upper()


def build(assets: Path = ASSETS, sprite_base: int = 0, font_file: Path | None = None) -> GfxResult:
    c1, c2 = bytearray(), bytearray()
    sprites: list[SpriteArt] = []
    palettes: list[list[int]] = [[0] * 16 for _ in range(FIX_PALETTE_SLOTS)]

    def add_tiles(tiles: list[bytes]) -> int:
        first = sprite_base + len(c1) // 64
        for t in tiles:
            a, b = encode_crom_tile(t)
            c1.extend(a)
            c2.extend(b)
        return first

    # gemas: un tile por nivel; una paleta por carril y otra para la estelar
    gem_tiles = [add_tiles([draw_gem(lv)]) for lv in range(GEM_LEVELS)]
    for name, rgb in (*LANE_COLORS.items(), ("estelar", STAR_COLOR)):
        sprites.append(SpriteArt(f"GEM_{_ident(name)}", gem_tiles[0], 1, GEM_LEVELS, len(palettes)))
        palettes.append(gem_palette(rgb))
    # cola, bombo y rombo (si assets/gfx no trae su propio PNG con ese nombre)
    gfx_dir = assets / "gfx"
    for name, fn in HWY_PIECES:
        if not (gfx_dir / f"{name.lower()}.png").exists():
            sprites.append(SpriteArt(name, add_tiles([fn()]), 1, 1, len(palettes) - 1))
    # escenario: una paleta base y 9 más (ver stage_palettes); cada arte lleva sus tiles de columna
    stage_pal = len(palettes)
    palettes.extend(stage_palettes())
    for name, fn in STAGE_ART:
        t = fn()
        sprites.append(SpriteArt(name, add_tiles(t.tiles()), 1, t.h // 16, stage_pal))
    # pista fija: el primer tile en múltiplo de 8 (la autoanimación reemplaza los 3 bits bajos del tile)
    while (sprite_base + len(c1) // 64) % TRACK_PHASES:
        add_tiles([bytes(256)])
    for name, lanes in TRACK_VARIANTS:
        sprites.append(SpriteArt(name, add_tiles(track_tiles(lanes=lanes)), TRACK_COLS, TRACK_ROWS, len(palettes)))
    palettes.append(track_palette())
    # PNG de assets/gfx, en orden alfabético
    for path in sorted(gfx_dir.glob("*.png")) if gfx_dir.is_dir() else []:
        cols, nrows, tiles, pal = png_to_sprite(path)
        sprites.append(SpriteArt(_ident(path.stem), add_tiles(tiles), cols, nrows, len(palettes)))
        palettes.append(pal)
    if len(palettes) > 256:
        raise ValueError("más de 256 paletas")

    for i, rgb in enumerate(FIX_PALETTES.values()):
        palettes[i][1] = neo_color(*rgb)
    ff = font_file or assets / "fonts" / "bongo8_glyphs.txt"
    tiles = fix_tiles(load_glyphs(ff))
    srom = bytearray(32 * (max(tiles) + 1))
    for n, t in tiles.items():
        srom[n * 32:n * 32 + 32] = encode_srom_tile(t)
    return GfxResult(bytes(c1), bytes(c2), bytes(srom), palettes, sprites, gem_tiles, build_persp(), stage_pal)


def render_header(r: GfxResult) -> str:
    L = ["/* generado por `ngband gfx` - no editar */", "#ifndef NGBAND_GFX_DATA_H", "#define NGBAND_GFX_DATA_H",
         '#include "types.h"', "",
         "typedef struct {", "  u16 y;           /* posición Y en pantalla */",
         "  u8  hshrink;     /* 0..15 (15 = tamaño completo) */", "  u8  vshrink;     /* 0..255 */",
         "  s16 x_lane[5];   /* X central de cada carril a esa profundidad */", "} PerspRow;", "",
         f"#define PERSP_ROWS {len(r.persp)}", f"#define PERSP_Y_HORIZON {r.persp[0].y}",
         f"#define PERSP_Y_HIT {Y_HIT}", f"#define GEM_LEVELS {GEM_LEVELS}",
         f"#define GFX_NUM_PALETTES {len(r.palettes)}", f"#define GFX_FIX_PALETTES {FIX_PALETTE_SLOTS}",
         f"#define GFX_STAGE_PAL_BASE {r.stage_pal}  /* {STAGE_PAL_COUNT} paletas: fase*2+latido, 8 apagado, 9 destello */",
         f"#define FIX_TILE_METER 0x{TILE_METER:02X}  /* +0..8 = barra de 0 a 8 píxeles */",
         f"#define GFX_C_TILES {len(r.c1) // 64}", f"#define GFX_S_TILES {len(r.srom) // 32}",
         f"#define GFX_PISTA_X0 {TRACK_X0}  /* esquina superior izquierda de la pista con 1 jugador */",
         f"#define GFX_PISTA_Y0 {TRACK_Y0}", f"#define GFX_PISTA_PHASES {TRACK_PHASES}",
         f"#define GFX_PISTA_PERIOD {TRACK_PERIOD}  /* px de pantalla por vuelta de las 8 fases */", "",
         "extern const PerspRow persp[PERSP_ROWS];",
         "extern const u8 persp_gem_level[PERSP_ROWS];   /* nivel de gema de cada fila */",
         "extern const u8 gem_hshrink[GEM_LEVELS];", "extern const u8 gem_vshrink[GEM_LEVELS];",
         "extern const u16 gem_tile[GEM_LEVELS];         /* tile de arte de cada nivel */",
         "extern const u16 gfx_palettes[GFX_NUM_PALETTES][16];", ""]
    for s in r.sprites:
        L += [f"#define GFX_{s.name}_TILE {s.first_tile}", f"#define GFX_{s.name}_COLS {s.cols}",
              f"#define GFX_{s.name}_ROWS {s.rows}", f"#define GFX_{s.name}_PAL {s.palette}"]
    return "\n".join(L + ["", "#endif /* NGBAND_GFX_DATA_H */", ""])


def render_c(r: GfxResult) -> str:
    L = ["/* generado por `ngband gfx` - no editar */", '#include "gfx_data.h"', "",
         "const PerspRow persp[PERSP_ROWS] = {"]
    for p in r.persp:
        L.append(f"  {{ {p.y}, {p.hshrink}, {p.vshrink}, {{ {', '.join(map(str, p.x_lane))} }} }},")
    L += ["};", "", "const u8 persp_gem_level[PERSP_ROWS] = {"]
    L += [f"  {', '.join(str(p.gem_level) for p in r.persp[i:i + 16])}," for i in range(0, len(r.persp), 16)]
    scales = [gem_scale(lv) for lv in range(GEM_LEVELS)]
    L += ["};", "", f"const u8 gem_hshrink[GEM_LEVELS] = {{ {', '.join(str(h) for h, _ in scales)} }};",
          f"const u8 gem_vshrink[GEM_LEVELS] = {{ {', '.join(str(v) for _, v in scales)} }};",
          f"const u16 gem_tile[GEM_LEVELS] = {{ {', '.join(map(str, r.gem_tiles))} }};", "",
          "const u16 gfx_palettes[GFX_NUM_PALETTES][16] = {"]
    L += ["  { " + ", ".join(f"0x{c:04X}" for c in pal) + " }," for pal in r.palettes]
    return "\n".join(L + ["};", ""])


def write_outputs(r: GfxResult, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "gfx_c1.bin").write_bytes(r.c1)
    (out / "gfx_c2.bin").write_bytes(r.c2)
    (out / "gfx_s.bin").write_bytes(r.srom)
    for name, text in (("gfx_data.h", render_header(r)), ("gfx_data.c", render_c(r))):
        (out / name).write_text(text, encoding="utf-8", newline="\n")


def run(out: Path, assets: Path = ASSETS, rebuild_font: bool = False) -> GfxResult:
    if rebuild_font:
        write_glyph_cache(glyphs_from_ttf(assets / "fonts" / "Bongo-8_Mono.ttf"),
                          assets / "fonts" / "bongo8_glyphs.txt")
    r = build(assets)
    write_outputs(r, out)
    return r
