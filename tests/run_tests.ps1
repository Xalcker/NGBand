# Corre las pruebas de NGBand en MAME. Envoltorio de `uv run ngband test` (igual en macOS y Windows).
# Uso:  .\tests\run_tests.ps1 [--no-build] [--rapida] [-j 4] [--lista] [--sin-ventana] [patron ...]
# (los argumentos pasan tal cual a `ngband test`; ver tests/run_tests.sh)
# Ojo: NGBand todavía no se puede compilar en Windows (build.sh usa ngdevkit); en Windows corre con --no-build
# sobre una ROM compilada en otra máquina (build/rom, build/ngband.sym y build/gen).
$root = Split-Path $PSScriptRoot -Parent
& uv run --project $root ngband test @args
exit $LASTEXITCODE
