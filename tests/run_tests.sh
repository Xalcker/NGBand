#!/usr/bin/env bash
# Compila y corre las pruebas de NGBand en MAME: el bot (tests/autoplay.lua) juega cada caso y se revisa su resultado.
# Envoltorio de `uv run ngband test`, que es igual en macOS y Windows (ver bandcore.testrun).
#
#   tests/run_tests.sh                 compila y corre todos los casos
#   tests/run_tests.sh --no-build      con la ROM que ya está en build/
#   tests/run_tests.sh --rapida        un subconjunto representativo
#   tests/run_tests.sh -j 4 'demo-*'   4 casos a la vez, solo los que coinciden (comodines y comas)
#   tests/run_tests.sh --lista         solo muestra los casos
#   tests/run_tests.sh --sin-ventana   MAME sin ventana (por omisión abre en ventana, nunca en pantalla completa;
#                                      en macOS le devuelve el foco a lo que estés usando)
#
# Cada caso deja en build/test-<nombre>/ el resultado (resultado.txt), el registro del bot (bot.log), las capturas,
# el audio (audio.wav) y emulador.log. Las fallas que ya se conocen van en tests/known_failures.txt: no cambian
# el código de salida; una falla nueva sí.
#
# Variables de entorno: NGBAND_MAME_GAME (cartucho, ngband), NGBAND_MAME_ROMPATH (build/rom), NGBAND_DEMO_SONG (demo),
# NGBAND_HUMAN_SEEDS (partidas del bot humano por canción y dificultad, 1) y MAME (el ejecutable).
# Los casos sin la canción en src/songs/ se saltan con un aviso (las canciones importadas no van en git).
exec uv run --project "$(cd "$(dirname "$0")/.." && pwd)" ngband test "$@"
