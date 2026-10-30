"""Arnés de pruebas en el host para la lógica pura en C.

Compila los `src/*.c` puros (sin hardware) junto con `host_probe.c` como
biblioteca compartida y los expone con cffi (modo ABI). Las declaraciones
se leen de las mismas cabeceras que usa la ROM.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings
from cffi import FFI

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
HERE = Path(__file__).resolve().parent

# Cabeceras que se leen para el cdef, en orden de dependencia.
HEADERS = ["types.h", "chart.h", "gameplay.h", "records.h", "stage.h", "options.h", "practice.h", "versus.h", "menu_logic.h"]

# Fuentes de src/ sin dependencia de hardware. Se compilan solo las que existen.
PURE_SOURCES = [
    "gameplay.c", "records.c", "stage.c", "versus.c", "practice.c",
    "options.c", "chart.c", "shadow.c", "perspective.c", "spr_diff.c",
    "input_map.c", "highway_layout.c", "stage_layout.c", "audio_cmd.c", "menu_logic.c",
]

# Declaraciones de la sonda.
PROBE_CDEF = """
uint32_t ngb_sizeof_judge_state(void);
uint32_t ngb_sizeof_pad_input(void);
uint32_t ngb_sizeof_chart_ev(void);
uint32_t ngb_sizeof_chart(void);
uint8_t ngb_stage_pal(uint8_t phase, uint8_t pulse, uint8_t flash, uint8_t off);
uint32_t ngb_stage_probe(uint8_t nplayers, uint8_t hwy_fill, uint8_t flash, uint8_t bolt_lane,
                         uint8_t crowd, uint8_t off, uint8_t *lines_out, uint16_t *first_x);
"""

# Mínimo 100 ejemplos por propiedad (ver tasks.md).
settings.register_profile(
    "ngband",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ngband")


def _cdef_from_headers() -> str:
    """Devuelve el texto de los .h sin directivas del preprocesador ni
    comentarios, apto para `ffi.cdef`. Los typedefs de `types.h` usan
    <stdint.h>, que cffi ya conoce."""
    parts: list[str] = []
    for name in HEADERS:
        text = (SRC / name).read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        parts.append("\n".join(lines))
    return "\n".join(parts)


def _compile(out_dir: Path) -> Path:
    cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        pytest.skip("No hay compilador de C en el host")
    sources = [HERE / "host_probe.c"] + [
        SRC / n for n in PURE_SOURCES if (SRC / n).exists()
    ]
    ext = ".dylib" if sys.platform == "darwin" else ".so"
    lib = out_dir / f"libngband_host{ext}"
    cmd = [
        cc, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
        "-fPIC", "-shared", "-DNGBAND_HOST", f"-I{SRC}", "-o", str(lib),
        *map(str, sources),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return lib


@pytest.fixture(scope="session")
def ngb(tmp_path_factory):
    """Devuelve `(ffi, lib)` con la lógica pura del juego cargada en el host."""
    lib_path = _compile(tmp_path_factory.mktemp("host_lib"))
    ffi = FFI()
    ffi.cdef(_cdef_from_headers())
    ffi.cdef(PROBE_CDEF)
    return ffi, ffi.dlopen(str(lib_path))


@pytest.fixture(scope="session")
def ffi(ngb):
    return ngb[0]


@pytest.fixture(scope="session")
def lib(ngb):
    return ngb[1]
