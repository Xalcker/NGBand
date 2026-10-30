#!/usr/bin/env bash
# Compila NGBand: deja build/ngband.* (la ROM) y build/ngband.sym (los símbolos, para las pruebas).
#
#   ./build.sh               compilación normal (entran todas las canciones de src/songs/)
#   ./build.sh --release     ROM para publicar en build/release/ngband-v<versión>.* con .sha256 y licencia
#
# --release se niega si `git status --porcelain src/ audio/` no está vacío y solo incluye las canciones
# que git versiona (las importadas de juegos comerciales están ignoradas y nunca salen en una release).
# Necesita ngdevkit (brew tap dciabrin/ngdevkit; GCC m68k y romtool), SDCC de Homebrew (Z80) y uv.
# Orden: ngband gfx -> ngband adpcm -> ngband list-songs -> SDCC (Z80) -> GCC m68k -> build/ngband.*
set -euo pipefail
cd "$(dirname "$0")"

release=0
for arg in "$@"; do
    case "$arg" in
        --release) release=1 ;;
        *) echo "Opción desconocida: $arg (uso: ./build.sh [--release])" >&2; exit 2 ;;
    esac
done

PREFIX="${PREFIX:-m68k-neogeo-elf-}"
VERSION=$(tr -d ' \n' < VERSION)
OUT=build
GEN="$OUT/gen"
ROMDIR="$OUT/rom"
GAMEROM=ngband
# Tamaños de cada chip (los de los ejemplos de ngdevkit). La M1 crece con las canciones (paso 2).
PROMSIZE=1048576 CROMSIZE=2097152 SROMSIZE=131072 VROMSIZE=524288

# Reproducibilidad (R1.5): fecha, zona horaria y locale fijos; el entorno no se filtra a la ROM
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"
export TZ=UTC LC_ALL=C

need() { command -v "$1" >/dev/null || { echo "Falta $1: $2" >&2; exit 1; }; }
pad() { python3 -c 'import sys;f=open(sys.argv[1],"r+b");n=int(sys.argv[2]);d=f.seek(0,2)
if d>n: sys.exit(f"{sys.argv[1]}: {d} bytes, no cabe en {n}")
f.write(bytes([int(sys.argv[3],0)])*(n-d))' "$1" "$2" "${3:-0}"; }

# R1.4: sin cambios sin commit en src/ ni audio/ (incluye archivos nuevos sin versionar)
if [ $release -eq 1 ]; then
    need git "instala git"
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "No se puede hacer la release: esto no es un repositorio git." >&2
        exit 1
    fi
    dirty=$(git status --porcelain src/ audio/)
    if [ -n "$dirty" ]; then
        echo "No se puede hacer la release: hay cambios sin commit en src/ o audio/:" >&2
        echo "$dirty" >&2
        exit 1
    fi
fi

need uv "https://docs.astral.sh/uv/"
need sdcc "instala SDCC (brew install sdcc): el SDCC de ngdevkit no compila C"
need "${PREFIX}gcc" "instala ngdevkit: brew tap dciabrin/ngdevkit && brew install ngdevkit"
need pkg-config "brew install pkg-config"
pkg-config --exists ngdevkit || { echo "pkg-config no encuentra ngdevkit" >&2; exit 1; }
NGCFLAGS=$(pkg-config --cflags ngdevkit)
NGLDFLAGS=$(pkg-config --libs ngdevkit)
NGSHARE=$(pkg-config --variable=sharedir ngdevkit)
ROMTOOL=$(ls "$(brew --prefix 2>/dev/null || echo /opt/homebrew)"/Cellar/ngdevkit/*/bin/romtool.py 2>/dev/null | tail -1)
[ -n "$ROMTOOL" ] || ROMTOOL=$(command -v romtool.py || true)
[ -n "$ROMTOOL" ] || { echo "Falta romtool.py (viene con ngdevkit)" >&2; exit 1; }

# Parte de cero para que dos compilaciones no dependan de restos anteriores
rm -rf "$OUT/obj" "$GEN" "$ROMDIR"
mkdir -p "$OUT/obj/z80" "$GEN" "$ROMDIR"

# 1. Gráficos, samples y lista de canciones: se generan aquí, no en el arranque de la ROM (R1.9)
uv run ngband gfx --out "$GEN"
uv run ngband adpcm --out "$GEN"
list_args=(--out "$GEN")
[ $release -eq 1 ] && list_args+=(--release)
uv run ngband list-songs "${list_args[@]}" >/dev/null     # R1.7 y R1.8: orden alfabético; en release, sin comerciales
echo "Canciones: $(tr '\n' ' ' < "$GEN/songs.txt")"

# 2. Driver Z80 (SDCC) -> ROM M1. El código en los 32 KB fijos (0x0000-0x7FFF), la RAM en 0xF800 y los
#    Frame_Streams (z80/streams.bin) desde 0x8000 de la M1, que el driver lee por bancos (src/z80/driver.c).
Z=$OUT/obj/z80
sdasz80 -g -o "$Z/crt0.rel" src/z80/crt0.s
for f in src/z80/driver.c src/shadow.c "$GEN/z80/z80_songs.c"; do
    sdcc -mz80 --no-std-crt0 --opt-code-size -Isrc -c "$f" -o "$Z/$(basename "${f%.c}").rel"
done
sdldz80 -n -m -i -b _CODE=0x0100 -b _DATA=0xF800 -k "$(dirname "$(command -v sdcc)")/../share/sdcc/lib/z80" -l z80 \
    "$Z/m1.ihx" "$Z/crt0.rel" "$Z/driver.rel" "$Z/shadow.rel" "$Z/z80_songs.rel"
# el código no puede pasar a la ventana de bancos (0x8000)
python3 - "$Z/m1.map" <<'PY'
import re, sys
top = 0
for line in open(sys.argv[1]):
    m = re.match(r"^(_CODE|_HOME|_INITIALIZER|_GSINIT|_GSFINAL)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", line)
    if m:
        top = max(top, int(m.group(2), 16) + int(m.group(3), 16))
if top > 0x8000:
    sys.exit(f"El driver Z80 ocupa hasta 0x{top:04X}: pasa de los 32 KB fijos (0x8000)")
print(f"Z80: driver hasta 0x{top:04X} de 0x8000")
PY
M1="$ROMDIR/$GAMEROM-m1.m1"
makebin -s 32768 "$Z/m1.ihx" "$M1"
cat "$GEN/z80/streams.bin" >> "$M1"
# la M1 mide una potencia de 2 (128 KB como mínimo)
MROMSIZE=$(python3 -c 'import os,sys
n, s = os.path.getsize(sys.argv[1]), 131072
while s < n: s *= 2
print(s)' "$M1")
pad "$M1" $MROMSIZE 0xFF
echo "M1: $(( $(wc -c < "$GEN/z80/streams.bin") / 1024 )) KB de streams, ROM de $(( MROMSIZE / 1024 )) KB"

# 3. 68000 (GCC de ngdevkit): NGBAND_VERSION se inyecta desde VERSION para el título (R1.6).
#    NGBAND_NO_STREAM deja fuera de P1 los Frame_Streams (van en la M1).
#    Sin rutas absolutas (-ffile-prefix-map), sin __DATE__/__TIME__ (-Werror=date-time), sin ident.
CFLAGS=($NGCFLAGS -std=gnu11 -O2 -fomit-frame-pointer -Wall -Wextra -Wno-enum-compare
        -Isrc -I"$GEN" -DNGBAND_VERSION="\"$VERSION\"" -DNGBAND_NO_STREAM
        -ffile-prefix-map="$PWD"=. -fno-ident -Wdate-time -Werror=date-time ${NGBAND_CFLAGS:-})
SONG_SRC=""
while IFS= read -r name; do
    [ -n "$name" ] && SONG_SRC+="src/songs/$name/song.c"$'\n'
done < "$GEN/songs.txt"
C_SRC=$( { ls src/*.c "$GEN"/*.c 2>/dev/null || true; printf '%s' "$SONG_SRC"; } | grep -v '^$' | LC_ALL=C sort -u || true)
OBJS=()
for f in $C_SRC; do
    # el nombre del objeto incluye el directorio para que dos song.c no choquen
    o="$OUT/obj/$(echo "${f%.c}" | tr '/' '_').o"
    "${PREFIX}gcc" "${CFLAGS[@]}" -frandom-seed="$f" -c "$f" -o "$o"
    OBJS+=("$o")
done

# 4. Enlace con el crt0 de ngdevkit (cabecera de la ROM, vectores, rom_callback_VBlank), ROM P1 y símbolos
"${PREFIX}gcc" -o "$OUT/ngband.elf" "${OBJS[@]}" $NGLDFLAGS -Wl,--build-id=none -Wl,-Map="$OUT/ngband.map"
P1="$ROMDIR/$GAMEROM-p1.p1"
"${PREFIX}objcopy" -O binary -S -R .text2 --gap-fill 0xff --pad-to $PROMSIZE "$OUT/ngband.elf" "$P1"
dd if="$P1" of="$P1" conv=notrunc,swab status=none        # el 68000 es big endian; la ROM va en palabras invertidas
"${PREFIX}nm" -n "$OUT/ngband.elf" > "$OUT/ngband.sym"

# 5. Gráficos (C1/C2, S1) y samples (V1, vacía por ahora)
C1="$ROMDIR/$GAMEROM-c1.c1" C2="$ROMDIR/$GAMEROM-c2.c2" S1="$ROMDIR/$GAMEROM-s1.s1" V1="$ROMDIR/$GAMEROM-v1.v1"
cp "$GEN/gfx_c1.bin" "$C1"; pad "$C1" $CROMSIZE
cp "$GEN/gfx_c2.bin" "$C2"; pad "$C2" $CROMSIZE
cp "$GEN/gfx_s.bin" "$S1";  pad "$S1" $SROMSIZE
: > "$V1"; pad "$V1" $VROMSIZE

# 6. Cartucho para MAME: zip, neogeo.xml (hash) y la BIOS libre de ngdevkit
RT=(sh "$ROMTOOL" -p "$P1" -c "$C1" "$C2" -v "$V1" -s "$S1" -m "$M1" -n $GAMEROM -l "NGBand $VERSION")
"${RT[@]}" -b cartridge -f zip -o "$ROMDIR/$GAMEROM.zip"
"${RT[@]}" -b hash -f mame -o "$ROMDIR/neogeo.xml"
cp "$NGSHARE/neogeo.zip" "$NGSHARE/aes.zip" "$ROMDIR/"
for f in "$ROMDIR"/$GAMEROM-*; do cp "$f" "$OUT/ngband.${f##*.}"; done
echo "Listo: $ROMDIR/$GAMEROM.zip (MAME) y $OUT/ngband.sym"
echo "Jugar: mame neogeo -hash $ROMDIR -rp $ROMDIR -cart1 $GAMEROM -w"

# 5. Release (R1.3): ROM renombrada con la versión, suma SHA-256 y licencia
if [ $release -eq 1 ]; then
    REL="$OUT/release"
    rm -rf "$REL"
    mkdir -p "$REL"
    roms=()
    for f in "$OUT"/ngband.*; do
        case "$f" in *.elf|*.map|*.sym) continue ;; esac     # solo los archivos de la ROM
        dest="ngband-v$VERSION.${f##*.}"
        cp "$f" "$REL/$dest"
        roms+=("$dest")
    done
    [ ${#roms[@]} -gt 0 ] || { echo "No hay archivos de ROM en $OUT/" >&2; exit 1; }
    [ -f LICENSE ] || { echo "Falta LICENSE (GPL-2.0-or-later)" >&2; exit 1; }
    cp LICENSE "$REL/LICENSE"
    (
        cd "$REL"
        if command -v sha256sum >/dev/null; then sum=(sha256sum); else sum=(shasum -a 256); fi
        "${sum[@]}" "${roms[@]}" > "ngband-v$VERSION.sha256"
    )
    echo "Release: $REL/ngband-v$VERSION.* (ver ngband-v$VERSION.sha256)"
fi
