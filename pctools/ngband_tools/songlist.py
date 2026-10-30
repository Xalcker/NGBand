"""Lista de canciones de la ROM: `src/songs/*/song.c` en orden alfabético (R1.8).

Con `release=True` solo entran las canciones que git versiona (las originales); las importadas de juegos
comerciales están ignoradas en git y nunca llegan a una release (R1.7).
"""
import os
import re
import subprocess
from pathlib import Path

from . import frames as fr

ROOT = Path(__file__).resolve().parents[2]


def tracked_songs(root: Path = ROOT) -> set[str]:
    """Nombres de las canciones con `song.c` versionado en git."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "src/songs"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {m.group(1) for line in out.splitlines()
            if (m := re.fullmatch(r"src/songs/([^/]+)/song\.c", line))}


def song_names(root: Path = ROOT, release: bool = False) -> list[str]:
    """Canciones de la ROM en orden alfabético (por bytes, igual en cualquier máquina)."""
    names = sorted(p.parent.name for p in (root / "src" / "songs").glob("*/song.c"))
    if release:
        tracked = tracked_songs(root)
        names = [n for n in names if n in tracked]
    return names


def render_song_list(names: list[str]) -> str:
    """C generado: tablas de canciones en el orden dado (sin fechas ni rutas, para que sea reproducible).
    `ngband_songs[i]` es la ficha `Song` de la canción i (el índice que recibe CMD_SONG_START)."""
    lines = ["/* generado por `ngband list-songs`: canciones en orden alfabético */",
             "#include <stddef.h>", '#include "song.h"', ""]
    lines += [f"extern const char song_{n}_name[];" for n in names]
    lines += [f"extern const Song song_{n};" for n in names]
    lines += ["", f"const unsigned char ngband_num_songs = {len(names)};",
              "const char *const ngband_song_table[] = {"]
    lines += [f"    song_{n}_name," for n in names]
    if not names:
        lines.append("    NULL,")
    lines += ["};", "", "const Song *const ngband_songs[] = {"]
    lines += [f"    &song_{n}," for n in names]
    if not names:
        lines.append("    NULL,")
    lines += ["};", ""]
    return "\n".join(lines)


# Mapa de la ROM M1 (ver src/z80/driver.c): el driver en los 32 KB fijos y los Frame_Streams desde 0x8000, que el
# Z80 lee por bancos. MAME solo direcciona 256 KB de M1 (con más, los bancos dan la vuelta en 0x40000), así que
# los streams van comprimidos con FS_REPEAT (frames.compress_stream): las 10 canciones caben en ~180 KB.
M1_STREAM_BASE = 0x8000
M1_MAX_SIZE = 0x40000
M1_STREAM_BUDGET = M1_MAX_SIZE - M1_STREAM_BASE
MAP_SPAN = 0x2000      # SH_MAP_SPAN de shadow.h: bytes seguidos que ve el Z80 desde el inicio de un cuadro

_STREAM_RE = re.compile(r"song_stream\[(\d+)\]\s*=\s*\{(.*?)\};", re.S)
_MASK_RE = re.compile(r"\.inst_mask\s*=\s*\{([^}]*)\}")


def song_stream(root: Path, name: str) -> tuple[bytes, list[int]]:
    """El Frame_Stream y las máscaras de canales por instrumento de `src/songs/<name>/song.c`."""
    text = (root / "src" / "songs" / name / "song.c").read_text(encoding="utf-8")
    m = _STREAM_RE.search(text)
    if not m:
        raise ValueError(f"{name}/song.c no trae song_stream")
    data = bytes(int(t, 0) for t in re.findall(r"0[xX][0-9A-Fa-f]+|\d+", m.group(2)))
    if len(data) != int(m.group(1)):
        raise ValueError(f"{name}/song.c: song_stream declara {m.group(1)} bytes y trae {len(data)}")
    mm = _MASK_RE.search(text)
    masks = [int(t, 0) for t in mm.group(1).split(",") if t.strip()] if mm else []
    return data, (masks + [0, 0, 0, 0])[:4]


def m1_stream(root: Path, name: str) -> bytes:
    """El Frame_Stream comprimido como va en la M1 (verificado: se expande al original)."""
    data = song_stream(root, name)[0]
    packed = fr.compress_stream(data)
    if fr.expand_stream(packed) != data:
        raise ValueError(f"{name}: el stream comprimido no se expande igual al original")
    return packed


def fit_songs(names: list[str], root: Path, budget: int) -> tuple[list[str], list[str]]:
    """Las canciones cuyos streams (comprimidos) caben en `budget` bytes: `demo` primero y luego de la más chica a
    la más grande; se devuelven en orden alfabético, junto con las que no cupieron."""
    sizes = {n: len(m1_stream(root, n)) for n in names}
    order = sorted(names, key=lambda n: (n != "demo", sizes[n], n))
    kept, used = set(), 0
    for n in order:
        if used + sizes[n] <= budget:
            kept.add(n)
            used += sizes[n]
    return [n for n in names if n in kept], [n for n in names if n not in kept]


def frame_sizes(data: bytes) -> list[int]:
    """Bytes de cada cuadro del Frame_Stream (un cuadro continuado cuenta entero; un REPEAT mide 6)."""
    sizes, p = [], 0
    while p < len(data):
        frame = fr._one_frame(data, p)
        sizes.append(len(frame))
        p += len(frame)
    return sizes


def z80_streams(names: list[str], root: Path) -> tuple[bytes, list[tuple[int, int, list[int]]]]:
    """Los Frame_Streams seguidos (lo que va en la M1 desde M1_STREAM_BASE) y, por canción, su posición en la
    M1, su fin y sus máscaras."""
    blob, table = bytearray(), []
    for n in names:
        masks = song_stream(root, n)[1]
        data = m1_stream(root, n)
        big = max(frame_sizes(data), default=0)
        if big > MAP_SPAN:
            raise ValueError(f"{n}: un cuadro del stream ocupa {big} bytes; el driver Z80 ve {MAP_SPAN} seguidos")
        start = M1_STREAM_BASE + len(blob)
        blob += data
        table.append((start, start + len(data), masks))
    return bytes(blob), table


def render_z80_songs(names: list[str], table: list[tuple[int, int, list[int]]]) -> str:
    """C para SDCC: la tabla SongInfo que lee el driver (mismo índice que ngband_songs). Los streams no van aquí
    sino en `z80/streams.bin`, que build.sh pega en la M1 desde M1_STREAM_BASE."""
    lines = ["/* generado por `ngband list-songs`: posiciones de los Frame_Streams en la ROM M1 (driver Z80) */",
             '#include "shadow.h"', "",
             f"const u8 song_count = {len(names)};", f"const SongInfo song_table[{max(1, len(names))}] = {{"]
    for n, (start, end, masks) in zip(names, table):
        lines.append(f"  {{ 0x{start:06X}, 0x{end:06X}, {{ {', '.join(f'0x{m:02X}' for m in masks)} }} }},  /* {n} */")
    if not names:
        lines.append("  { 0, 0, { 0, 0, 0, 0 } },")
    lines += ["};", "", "/* Sin samples ADPCM-A todavía: las canciones originales tocan la batería en FM 4. */",
              "const u8 drum_count = 0;", "const DrumSample drum_table[1] = { { 0, 0 } };", ""]
    return "\n".join(lines)


def write_song_list(out_dir: Path, root: Path = ROOT, release: bool = False,
                    budget: int | None = M1_STREAM_BUDGET) -> list[str]:
    names = song_names(root, release)
    wanted = os.environ.get("NGBAND_SONGS")
    if wanted:
        pick = [w.strip() for w in wanted.split(",") if w.strip()]
        missing = [w for w in pick if w not in names]
        if missing:
            raise ValueError(f"NGBAND_SONGS pide canciones que no están en src/songs/: {', '.join(missing)}")
        names = [n for n in names if n in pick]
    if budget is not None:
        names, left_out = fit_songs(names, root, budget)
        if left_out:
            print(f"aviso: no caben en la ROM M1 ({budget} bytes de stream): {', '.join(left_out)}",
                  file=__import__("sys").stderr)
    blob, table = z80_streams(names, root)
    (out_dir / "z80").mkdir(parents=True, exist_ok=True)
    (out_dir / "z80" / "z80_songs.c").write_text(render_z80_songs(names, table), encoding="utf-8", newline="\n")
    (out_dir / "z80" / "streams.bin").write_bytes(blob)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "song_list.c", "w", encoding="utf-8", newline="\n") as f:
        f.write(render_song_list(names))
    (out_dir / "songs.txt").write_text("".join(f"{n}\n" for n in names), encoding="utf-8", newline="\n")
    return names
