# NGBand

- **Empieza por `docs/ESTADO.md`:** el estado real, cómo compilar y probar, y los pendientes en orden.
- **Paridad entre versiones:** al terminar una mejora, actualiza `../NESBand/docs/paridad.md` (la fila y la columna NGBand) y anota en
  "Pendientes por versión" lo que falta en NES, GB y GEN. Pide permiso antes de editar ese otro repositorio.
- **Estado real:** la ROM compila (`./build.sh`) con las 10 canciones y corre en MAME; el arnés (`tests/run_tests.sh`)
  pasa 44 de 57 casos (ver `docs/ESTADO.md`) y el audio no se ha escuchado con oído. No afirmes que algo "funciona en la consola" si solo
  lo cubren las pruebas del host (`uv run pytest`) o el humo de `tests/mame/run.sh`; en la paridad usa 🟡 para eso.
- Al terminar una sesión, actualiza `docs/ESTADO.md`.
- **MAME sin ventana:** `uv run ngband test --sin-ventana` (o `SDL_VIDEODRIVER=dummy` con `-video none`); en macOS
  `-video none` solo sigue abriendo una ventana.
