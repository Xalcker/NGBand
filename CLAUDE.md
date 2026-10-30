# NGBand

- **Empieza por `docs/ESTADO.md`:** el estado real, cómo compilar y probar, y los pendientes en orden.
- **Paridad entre versiones:** al terminar una mejora, actualiza `../NESBand/docs/paridad.md` (la fila y la columna NGBand) y anota en
  "Pendientes por versión" lo que falta en NES, GB y GEN. Pide permiso antes de editar ese otro repositorio.
- **Estado real:** la ROM compila (`./build.sh`) y corre en MAME (título, Menu y juego), pero solo trae 2 canciones, el
  audio no se ha escuchado y `tests/run_tests.sh` no se ha corrido. No afirmes que algo "funciona en la consola" si solo
  lo cubren las pruebas del host (`uv run pytest`) o el humo de `tests/mame/run.sh`; en la paridad usa 🟡 para eso.
- Al terminar una sesión, actualiza `docs/ESTADO.md`.
