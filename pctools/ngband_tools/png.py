"""Lector mínimo de PNG (sin Pillow): 8 bits o menos por canal, sin entrelazado.
Devuelve una imagen como (ancho, alto, filas de píxeles RGBA). Sirve para leer el arte de assets/gfx/.
"""
from __future__ import annotations
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

RGBA = tuple[int, int, int, int]


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> list[bytearray]:
    rows: list[bytearray] = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        cur = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if len(cur) != stride:
            raise ValueError("PNG truncado")
        for i in range(stride):
            a = cur[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ftype == 1:
                cur[i] = (cur[i] + a) & 255
            elif ftype == 2:
                cur[i] = (cur[i] + b) & 255
            elif ftype == 3:
                cur[i] = (cur[i] + ((a + b) >> 1)) & 255
            elif ftype == 4:
                cur[i] = (cur[i] + _paeth(a, b, c)) & 255
            elif ftype != 0:
                raise ValueError(f"filtro PNG desconocido: {ftype}")
        rows.append(cur)
        prev = cur
    return rows


def _samples(row: bytearray, depth: int, count: int) -> list[int]:
    if depth == 8:
        return list(row[:count])
    mask = (1 << depth) - 1
    per_byte = 8 // depth
    return [(row[i // per_byte] >> (8 - depth * (i % per_byte + 1))) & mask for i in range(count)]


def decode(data: bytes) -> tuple[int, int, list[list[RGBA]]]:
    """Decodifica un PNG a (ancho, alto, filas de (r, g, b, a))."""
    if data[:8] != SIGNATURE:
        raise ValueError("no es un PNG")
    pos = 8
    ihdr = None
    palette: list[tuple[int, int, int]] = []
    trns = b""
    idat = bytearray()
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if ihdr is None:
        raise ValueError("PNG sin IHDR")
    width, height, depth, ctype, _comp, _filt, interlace = ihdr
    if interlace:
        raise ValueError("PNG entrelazado no soportado")
    if ctype not in CHANNELS or depth not in (1, 2, 4, 8) or (depth < 8 and ctype not in (0, 3)):
        raise ValueError(f"PNG no soportado (tipo {ctype}, {depth} bits)")
    channels = CHANNELS[ctype]
    stride = (width * channels * depth + 7) // 8
    bpp = max(1, channels * depth // 8)
    rows = _unfilter(zlib.decompress(bytes(idat)), height, stride, bpp)
    out: list[list[RGBA]] = []
    for row in rows:
        s = _samples(row, depth, width * channels)
        px: list[RGBA] = []
        for x in range(width):
            if ctype == 3:
                i = s[x]
                r, g, b = palette[i]
                a = trns[i] if i < len(trns) else 255
            elif ctype == 0:
                v = s[x] * 255 // ((1 << depth) - 1)
                r = g = b = v
                a = 255
            elif ctype == 4:
                r = g = b = s[2 * x]
                a = s[2 * x + 1]
            elif ctype == 2:
                r, g, b = s[3 * x:3 * x + 3]
                a = 255
            else:
                r, g, b, a = s[4 * x:4 * x + 4]
            px.append((r, g, b, a))
        out.append(px)
    return width, height, out


def encode(width: int, height: int, rows: list[list[RGBA]]) -> bytes:
    """PNG RGBA de 8 bits (para pruebas y para generar arte de ejemplo)."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in rows)
    return (SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
