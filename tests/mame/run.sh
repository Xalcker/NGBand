#!/usr/bin/env bash
# tests/mame/run.sh smoke | trace | audio   — corre la ROM de build/rom en MAME sin ventana.
#   audio: elige la última canción en el Menu, graba build/smoke/audio.wav y anota en build/smoke/audio.txt
#          la posición del stream en el Z80 (compila con NGBAND_CFLAGS=-DNGBAND_DEBUG para ver desincronías).
# NGBAND_MAME_WINDOW=1 muestra la ventana de MAME sin quitarle el foco a lo que estés usando (tests/mame/mame.sh).
set -euo pipefail
cd "$(dirname "$0")/../.."
source tests/mame/mame.sh
mode=${1:-smoke}
mkdir -p build/smoke
export NGBAND_PROBE=$(awk '$3=="g_probe"{print $1}' build/ngband.sym)
export NGBAND_AUDIO=$(awk '$3=="g_audio"{print $1}' build/ngband.sym)
export NGBAND_Z80_SH=$(awk '$2=="_g_sh"{print $1}' build/obj/z80/m1.map | head -1)
args=(neogeo -hash build/rom -rp build/rom -cart1 ngband -sound none -nothrottle -skip_gameinfo
      -snapshot_directory build/smoke -cfg_directory build/smoke/cfg -nvram_directory build/smoke/nvram)
if [ "$mode" = trace ]; then
    rm -f build/smoke/tr.txt
    run_mame build/smoke/mame.log "${args[@]}" -debug -debugger none -autoboot_script tests/mame/trace.lua
    python3 tests/mame/trace_report.py
elif [ "$mode" = audio ]; then
    rm -f build/smoke/audio.wav
    run_mame build/smoke/mame.log "${args[@]}" -wavwrite build/smoke/audio.wav -autoboot_script tests/mame/audio.lua
    cat build/smoke/audio.txt
    python3 tests/mame/wav_report.py build/smoke/audio.wav
else
    rm -rf build/smoke/neogeo
    run_mame build/smoke/mame.log "${args[@]}" -autoboot_script tests/mame/smoke.lua
    cat build/smoke/log.txt
    echo "capturas: build/smoke/neogeo/*.png"
fi
