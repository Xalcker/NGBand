"""Pruebas del compilador de gráficos (`ngband gfx`, tarea 8.1)."""
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from ngband_tools import gfx, png
from ngband_tools.cli import main


def decode_crom_tile(c1: bytes, c2: bytes) -> bytes:
    """Inverso de encode_crom_tile (orden de bloques de la Neo Geo)."""
    tile = bytearray(256)
    i = 0
    for start in (8, 136, 0, 128):
        for y in range(8):
            p0, p1, p2, p3 = c1[i], c1[i + 1], c2[i], c2[i + 1]
            i += 2
            for x in range(8):
                tile[start + y * 16 + x] = (((p3 >> x) & 1) << 3 | ((p2 >> x) & 1) << 2
                                            | ((p1 >> x) & 1) << 1 | ((p0 >> x) & 1))
    return bytes(tile)


@given(st.binary(min_size=256, max_size=256).map(lambda b: bytes(c & 15 for c in b)))
def test_crom_roundtrip(tile):
    c1, c2 = gfx.encode_crom_tile(tile)
    assert len(c1) == len(c2) == 64
    assert decode_crom_tile(c1, c2) == tile


def test_crom_pixel_position():
    tile = bytearray(256)
    tile[8] = 0b0101           # píxel (8, 0): primer bloque en C1/C2
    c1, c2 = gfx.encode_crom_tile(bytes(tile))
    assert c1[0] == 1 and c1[1] == 0 and c2[0] == 1 and c2[1] == 0


def test_srom_tile_order():
    tile = bytearray(64)
    tile[4], tile[5] = 0x3, 0xA     # fila 0, columnas 4 y 5 -> primer byte
    tile[0] = 0x7                   # fila 0, columna 0 -> byte 16
    s = gfx.encode_srom_tile(bytes(tile))
    assert len(s) == 32 and s[0] == 0xA3 and s[16] == 0x07


def test_neo_color():
    assert gfx.neo_color(0, 0, 0) == 0
    assert gfx.neo_color(255, 255, 255) == 0x7FFF
    assert gfx.neo_color(255, 0, 0) == 0x4F00


def test_persp_shape():
    rows = gfx.build_persp()
    assert rows[0].y == gfx.Y_HORIZON
    hit = next(r for r in rows if r.y == gfx.Y_HIT)
    assert (hit.hshrink, hit.vshrink, hit.width) == (15, 255, gfx.W_HIT)
    assert len({r.gem_level for r in rows}) >= 7
    assert all(0 <= r.hshrink <= 15 and 0 <= r.vshrink <= 255 for r in rows)
    assert all(a.y + 1 == b.y for a, b in zip(rows, rows[1:]))
    assert all(a.hshrink <= b.hshrink and a.vshrink <= b.vshrink and a.width <= b.width
               for a, b in zip(rows, rows[1:]))


def test_persp_rejects_bad_params():
    with pytest.raises(ValueError):
        gfx.build_persp(y_h=100, y_g=100)
    with pytest.raises(ValueError):
        gfx.build_persp(w_h=300, w_g=200)


def test_png_roundtrip_and_sprite(tmp_path):
    red, blue = (255, 0, 0, 255), (0, 0, 255, 255)
    rows = [[red if x < 16 else blue if y < 16 else (0, 0, 0, 0) for x in range(32)] for y in range(32)]
    data = png.encode(32, 32, rows)
    assert png.decode(data) == (32, 32, rows)
    p = tmp_path / "a.png"
    p.write_bytes(data)
    cols, nrows, tiles, pal = gfx.png_to_sprite(p)
    assert (cols, nrows, len(tiles)) == (2, 2, 4)
    assert tiles[0] == bytes([1]) * 256                    # columna 0, fila 0: rojo
    assert tiles[3] == bytes(256)                          # columna 1, fila 1: transparente
    assert pal[1] == gfx.neo_color(255, 0, 0) and pal[2] == gfx.neo_color(0, 0, 255)


def test_png_bad_size(tmp_path):
    p = tmp_path / "b.png"
    p.write_bytes(png.encode(10, 10, [[(1, 2, 3, 255)] * 10 for _ in range(10)]))
    with pytest.raises(ValueError):
        gfx.png_to_sprite(p)


STAGE_TILES = sum(fn().h // 16 for _, fn in gfx.STAGE_ART)


def test_stage_art_palettes_and_tiles():
    pals = gfx.stage_palettes()
    assert len(pals) == gfx.STAGE_PAL_COUNT and all(len(p) == 16 for p in pals)
    assert len({p[gfx.ESC_LIGHT] for p in pals[:8]}) == 8      # 4 fases x {tenue, latido}
    assert pals[0][gfx.ESC_BLACK] == pals[9][gfx.ESC_BLACK]    # colores fijos iguales
    for _, fn in gfx.STAGE_ART:
        t = fn()
        assert t.w == 16 and t.h in (16, 32) and any(any(r) for r in t.px)
        for tile in t.tiles():
            gfx.encode_crom_tile(tile)


def test_stage_defines_in_header(tmp_path):
    r = gfx.run(tmp_path)
    h = (tmp_path / 'gfx_data.h').read_text()
    for name, _ in gfx.STAGE_ART:
        assert f'#define GFX_{name}_TILE' in h
    assert f'#define GFX_STAGE_PAL_BASE {r.stage_pal}' in h
    assert len(r.palettes) >= r.stage_pal + gfx.STAGE_PAL_COUNT


def test_cli_gfx_outputs_and_determinism(tmp_path):
    (tmp_path / "gfx").mkdir()
    (tmp_path / "gfx" / "logo.png").write_bytes(png.encode(16, 32, [[(9, 9, 9, 255)] * 16] * 32))
    for out in ("o1", "o2"):
        r = gfx.run(tmp_path / out, assets=_assets_with(tmp_path))
    files = ["gfx_c1.bin", "gfx_c2.bin", "gfx_s.bin", "gfx_data.c", "gfx_data.h"]
    for f in files:
        assert (tmp_path / "o1" / f).read_bytes() == (tmp_path / "o2" / f).read_bytes()
    before_track = gfx.GEM_LEVELS + len(gfx.HWY_PIECES) + STAGE_TILES
    track = gfx.TRACK_COLS * gfx.TRACK_ROWS * gfx.TRACK_PHASES * len(gfx.TRACK_VARIANTS)
    assert len(r.c1) == len(r.c2) == 64 * (before_track + (-before_track) % 8 + track + 2)
    assert "#define GFX_LOGO_ROWS 2" in (tmp_path / "o1" / "gfx_data.h").read_text()
    assert "PerspRow persp[PERSP_ROWS]" in (tmp_path / "o1" / "gfx_data.c").read_text()
    assert len(r.srom) % 32 == 0 and r.srom[ord("A") * 32:ord("A") * 32 + 32] != bytes(32)


def _assets_with(tmp_path: Path) -> Path:
    """assets de prueba: la fuente real más el PNG de tmp_path/gfx."""
    fonts = tmp_path / "fonts"
    fonts.mkdir(exist_ok=True)
    (fonts / "bongo8_glyphs.txt").write_bytes(gfx.FONT_FILE.read_bytes())
    return tmp_path


def test_cli_command(tmp_path, capsys):
    assert main(["gfx", "--out", str(tmp_path / "g")]) == 0
    assert (tmp_path / "g" / "gfx_data.c").stat().st_size > 1000


def test_track_art_phases_and_alignment():
    """Pista fija: tiles alineados a 8 (autoanimación), franjas que bajan PERIOD/8 px por fase y aros en la línea
    de golpe con el color de cada carril."""
    r = gfx.build()
    for name, _ in gfx.TRACK_VARIANTS:
        pista = next(s for s in r.sprites if s.name == name)
        assert pista.first_tile % gfx.TRACK_PHASES == 0
        assert (pista.cols, pista.rows) == (gfx.TRACK_COLS, gfx.TRACK_ROWS)
    a, b = gfx.draw_track(0), gfx.draw_track(1)
    step = gfx.TRACK_PERIOD // gfx.TRACK_PHASES
    x = gfx.X_CENTER - gfx.TRACK_X0 - 30           # dentro del carril 1, lejos de los divisores
    y = 120 - gfx.TRACK_Y0
    assert [a.px[y + k][x] for k in range(20)] == [b.px[y + step + k][x] for k in range(20)]
    hit = {p.y: p for p in r.persp}[gfx.Y_HIT]
    for lane, cx in enumerate(hit.x_lane):
        assert a.px[gfx.Y_HIT - gfx.TRACK_Y0 - gfx.RING_RY][cx - gfx.TRACK_X0] == gfx.TRK_RING + lane


def test_track_lanes_match_gem_columns():
    """Los divisores y los aros caen donde el juego pone las gemas: `ncols` columnas centradas separadas por un
    quinto del ancho (highway_layout.c, col_x); con 3 y 4 carriles la pista es más angosta."""
    hit = {p.y: p for p in gfx.build_persp()}[gfx.Y_HIT]
    lane_w = hit.width / gfx.NUM_LANES
    for _, lanes in gfx.TRACK_VARIANTS:
        img = gfx.draw_track(0, lanes=lanes)
        n = len(lanes)
        for col, lane in enumerate(lanes):
            gem_x = round(gfx.X_CENTER + (2 * col - (n - 1)) * (4 * lane_w) / 8)   # col_x con span = 4 carriles
            ring_top = gfx.Y_HIT - gfx.RING_RY - gfx.TRACK_Y0
            assert img.px[ring_top][gem_x - gfx.TRACK_X0] == gfx.TRK_RING + lane
        edge = round(gfx.X_CENTER + lane_w * n / 2) + 3 - gfx.TRACK_X0          # afuera del borde derecho
        assert img.px[gfx.Y_HIT - gfx.TRACK_Y0][edge] == 0
