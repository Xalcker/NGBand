#!/usr/bin/env bash
# Pruebas de NGBand en MAME: el bot (tests/autoplay.lua) juega cada caso y se revisa su resultado.
# MAME corre sin ventana (-video none), sin esperar al reloj real (-nothrottle). Con NGBAND_MAME_WINDOW=1
# muestra su ventana sin quitarle el foco a lo que estés usando (ver tests/mame/mame.sh).
#
#   tests/run_tests.sh              compila y corre todos los casos
#   tests/run_tests.sh --no-build   con la ROM que ya está en build/
#   tests/run_tests.sh 'demo-*'     solo los casos cuyo nombre coincide (acepta comodines)
#
# Cada caso deja en build/test-<nombre>/ el resultado (resultado.txt), el registro del bot (bot.log),
# las capturas, el audio (audio.wav) y mame.log, y aquí se comprueba lo que debe cumplir.
#
# Cómo arranca MAME (se puede cambiar con variables de entorno):
#   NGBAND_MAME_GAME      nombre del cartucho (por defecto ngband): se carga como `neogeo -cart1 <nombre>`
#   NGBAND_MAME_ROMPATH   rompath y hash de MAME (por defecto build/rom: ahí build.sh deja el zip, neogeo.xml
#                         y la BIOS libre de ngdevkit)
#   NGBAND_DEMO_SONG      carpeta de la canción de demostración en src/songs/ (por defecto demo)
#   NGBAND_HUMAN_SEEDS    partidas del bot humano por canción y Difficulty (por defecto 1; con más hay más
#                         partidas y la tasa de R17.12 sale menos ruidosa)
# Los casos sin la canción en src/songs/ se saltan con un aviso (las canciones importadas no van en git).
#   MAME                  el ejecutable (por defecto mame)
set -uo pipefail
cd "$(dirname "$0")/.."

build=1
only=""
for arg in "$@"; do
    case "$arg" in
        --no-build) build=0 ;;
        *) only="$arg" ;;
    esac
done
if [ $build = 1 ]; then
    ./build.sh || exit 1
fi
source tests/mame/mame.sh
command -v "$MAME" >/dev/null || { echo "Falta MAME: brew install mame" >&2; exit 1; }
[ -f build/ngband.sym ] || { echo "Falta build/ngband.sym: compila primero (./build.sh)" >&2; exit 1; }

GAME="${NGBAND_MAME_GAME:-ngband}"
ROMPATH="${NGBAND_MAME_ROMPATH:-$PWD/build/rom}"
SYM="$PWD/build/ngband.sym"
DEMO="${NGBAND_DEMO_SONG:-demo}"
MAX_LOST=2     # R17.8: más de 2 cuadros perdidos es una falla
fails=0
ran=0
skipped=0
human_ran=0

# El lugar de una canción en el menú (por su carpeta de src/songs/): el orden de build/gen/songs.txt
# (alfabético, R1.8), que cambia según las canciones que haya
song_index() {
    grep -n -x -- "$1" build/gen/songs.txt | head -n1 | cut -d: -f1 | awk '{print $1 - 1}'
}

# caso: nombre canción instrumento dificultad modo [opciones] [nvram]   (canción: su carpeta)
# (con 2 jugadores: TWO="modo instrumento2 dificultad2 modo2" antes de run_case)
run_case() {
    local name=$1 song=$2 instr=$3 diff=$4 mode=$5 opts=${6:-} nvram=${7:-}
    if [ -n "$only" ] && [[ "$name" != $only ]]; then return; fi
    local idx
    idx=$(song_index "$song")
    if [ -z "$idx" ]; then
        if [ "$song" = "$DEMO" ]; then
            ran=$((ran + 1))
            echo "FALLA $name: la canción $song no está en build/gen/songs.txt"; fails=$((fails + 1))
        else
            echo "salta $name: la canción $song no está en build/gen/songs.txt"; skipped=$((skipped + 1))
        fi
        return
    fi
    ran=$((ran + 1))
    [ "$mode" = humano ] && human_ran=1
    local players=0 instr2=0 diff2=0 mode2=perfecto
    if [ -n "${TWO:-}" ]; then read -r players instr2 diff2 mode2 <<< "$TWO"; fi
    local dir="$PWD/build/test-$name"
    rm -rf "$dir"
    mkdir -p "$dir"
    NGBAND_SYM="$SYM" NGBAND_OUT="$dir" NGBAND_SONG=$idx NGBAND_INSTR=$instr NGBAND_DIFF=$diff \
    NGBAND_MODE=$mode NGBAND_OPTS="$opts" NGBAND_PLAYERS=$players NGBAND_INSTR2=$instr2 NGBAND_DIFF2=$diff2 \
    NGBAND_MODE2=$mode2 NGBAND_SEED=${SEED:-1} run_mame "$dir/mame.log" neogeo -hash "$ROMPATH" -rompath "$ROMPATH" -cart1 "$GAME" -sound none -nothrottle \
        -skip_gameinfo -frameskip 0 -noautoframeskip \
        -wavwrite "$dir/audio.wav" -snapshot_directory "$dir" -cfg_directory "$dir/cfg" \
        -nvram_directory "${nvram:-$dir/nvram}" -autoboot_script tests/autoplay.lua
    if [ ! -f "$dir/resultado.txt" ]; then
        echo "FALLA $name: el bot no llegó a los resultados (ver $dir/bot.log y mame.log)"
        fails=$((fails + 1))
        return
    fi
    python3 tests/check_result.py "$dir" "$mode" "$name" "$players" "$mode2" "$opts" "$MAX_LOST" || fails=$((fails + 1))
}

# Fase 1: la canción de demostración con los tres bots de R17.2 a R17.4
run_case demo-perfecto-experto   "$DEMO" 0 3 perfecto
run_case demo-perfecto-facil     "$DEMO" 0 0 perfecto
run_case demo-nada               "$DEMO" 0 1 nada
run_case demo-machacar           "$DEMO" 0 2 machacar
run_case demo-sinfallo           "$DEMO" 0 0 sinfallo
run_case demo-mitad              "$DEMO" 0 3 mitad
# Récords: con la backup RAM vacía, el juego perfecto es récord y se escriben las iniciales; al volver
# a encender (la misma carpeta de nvram) el récord sigue ahí (R17.6)
rm -rf "$PWD/build/test-nvram-records"
run_case demo-record             "$DEMO" 0 1 record "" "$PWD/build/test-nvram-records"
run_case demo-record-persiste    "$DEMO" 0 1 leer_record "" "$PWD/build/test-nvram-records"

# Opciones (R17.6): ESPEJO, VELOCIDAD (75%, 50% y 125%), CAIDA y Practice_Mode con y sin marcas. Con VELOCIDAD
# los pasos por cuadro cambian a propósito, pero el reloj y el Frame_Stream deben seguir juntos (sync).
run_case tormenta-espejo         tormenta 0 3 perfecto "espejo=1"
run_case tormenta-espejo-bajo    tormenta 2 3 perfecto "espejo=1"
run_case tormenta-lenta          tormenta 0 3 perfecto "velocidad=1"
run_case tormenta-media          tormenta 0 3 perfecto "velocidad=2"
run_case tormenta-rapida         tormenta 0 3 perfecto "velocidad=3 caida=4"
run_case tormenta-caida-facil    tormenta 0 0 perfecto "caida=1"
run_case marcha-practica         marcha   0 2 practica "practica=3 inicio=2"
run_case marcha-marcas           marcha   0 2 marcas   "practica=4 inicio=1"
# SIN FALLO y niveles de dificultad por instrumento (R17.2, R17.6)
run_case tormenta-sinfallo       tormenta 0 0 sinfallo
run_case tormenta-mitad          tormenta 0 3 mitad
run_case tormenta-machacar       tormenta 0 2 machacar
run_case tormenta-guitarra-experto tormenta 0 3 perfecto
run_case tormenta-teclado-facil  tormenta 1 0 perfecto
run_case luna-teclado-dificil    luna     1 2 perfecto
run_case tormenta-bajo-dificil   tormenta 2 2 perfecto
run_case carrera-guitarra-experto carrera 0 3 perfecto
run_case cumbia-bajo-experto     cumbia   2 3 perfecto
# Batería (ADPCM-A): el bot toca los pads y el bombo (carril naranja)
run_case tormenta-bateria-experto tormenta 3 3 perfecto
run_case cumbia-bateria-facil    cumbia   3 0 perfecto
# Audio contra la Chart (R17.5): pausa ~3 s a mitad de canción y reanuda; el reloj no avanza en la pausa y
# el Frame_Stream sigue alineado con la Chart (se mide en todos los casos, aquí también tras pausar)
run_case tormenta-pausa          tormenta 0 3 pausa
run_case cumbia-pausa-bajo       cumbia   2 2 pausa
run_case tormenta-pausa-rapida   tormenta 0 3 pausa "velocidad=3"
# Dos jugadores (R17.7): VS con el mismo chart (empate), VS donde J2 pierde (la partida se corta y gana J1),
# Co-Op perfecto (guitarra y bajo) y Co-Op con J2 caído (la banda sigue)
TWO="1 0 3 perfecto" run_case vs-empate        tormenta 0 3 perfecto
TWO="1 0 3 nada"     run_case vs-j2-pierde     tormenta 0 3 perfecto
TWO="2 2 2 perfecto" run_case coop-perfecto    tormenta 0 3 perfecto
TWO="2 3 1 nada"     run_case coop-j2-cae      carrera  0 2 perfecto
TWO="1 2 2 perfecto" run_case vs-pausa         tormenta 0 3 pausa
rm -rf "$PWD/build/test-nvram-vs"
TWO="1 1 1 perfecto" run_case vs-record        "$DEMO" 0 1 record "" "$PWD/build/test-nvram-vs"
# Rendimiento (R18.1, R18.2): cada caso ya mide los cuadros perdidos (R17.8); estos fuerzan el peor caso de
# sprites: experto con CAIDA rápida y golpes al aire (efectos extra) en 1 jugador, VS y Co-Op
run_case perf-1p-peor            tormenta 0 3 machacar "caida=4"
TWO="1 0 3 machacar" run_case perf-vs-peor     tormenta 0 3 machacar "caida=4"
TWO="2 2 3 machacar" run_case perf-coop-peor   tormenta 0 3 machacar "caida=4"
TWO="1 3 3 perfecto" run_case perf-vs-bateria  tormenta 0 3 perfecto
# Bot humano (R17.12): 4 canciones x 4 Difficulties x NGBAND_HUMAN_SEEDS; al final check_human.py comprueba
# que termine ~90% de las partidas y pierda ~45% en experto
for song in tormenta carrera cumbia luna; do
    for diff in 0 1 2 3; do
        for ((seed = 1; seed <= ${NGBAND_HUMAN_SEEDS:-1}; seed++)); do
            SEED=$seed run_case "humano-$song-d$diff-s$seed" "$song" 0 $diff humano
        done
    done
done
if [ $human_ran = 1 ]; then
    python3 tests/check_human.py build || fails=$((fails + 1))
fi

if [ $skipped -gt 0 ]; then echo "$skipped caso(s) saltados por falta de canciones"; fi
if [ $ran -eq 0 ]; then
    echo "Ningún caso coincide con '${only}'" >&2
    exit 1
fi
if [ $fails -gt 0 ]; then
    echo "$fails caso(s) fallaron"
    exit 1
fi
echo "Todo bien"
