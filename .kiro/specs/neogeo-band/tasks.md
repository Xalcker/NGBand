# Implementation Plan: NGBand (neogeo-band)

## Overview

El diseño usa C (`ngdevkit`, GCC m68k) para el 68000, SDCC para el driver Z80 y Python con `uv` para las herramientas de PC, así que no hace falta elegir lenguaje. La lógica pura (Judge, récords, Stage, armado de sprites, modelo de sombra del driver) se escribe en C compilable también para el host (`tests/host/`) y se prueba con Hypothesis vía `cffi`/`ctypes`. Lo que depende del hardware se prueba con MAME + Lua.

El orden sigue las fases de R20: fase 1 (Highway, canción, puntaje), fase 2 (vida, Star_Power, Sustain, Instruments, Difficulties), fase 3 (título, Menu, opciones, práctica, récords), fase 4 (10 canciones, efectos, batería ADPCM-A, Stage) y fase 5 (2 jugadores, editor, release reproducible).

## Tasks

- [x] 1. Estructura del proyecto y compilación
  - [x] 1.1 Crear la estructura del proyecto y el Build_System base
    - Crear `src/`, `audio/`, `pctools/ngband_tools/`, `pctools/tests/`, `tests/host/`, `VERSION`, `pyproject.toml` (uv, comando `ngband`) y `.gitignore` con `songs_src/`
    - Escribir `build.sh` que ejecute `ngband gfx`, `ngband adpcm`, SDCC (Z80) y GCC m68k, y emita `build/ngband.*` y `build/ngband.sym`
    - Inyectar `NGBAND_VERSION` desde `VERSION` para el título; generar gráficos en compilación y no en el arranque
    - _Requirements: 1.1, 1.2, 1.6, 1.9, 14.11_

  - [x] 1.2 Implementar `--release`, reproducibilidad y orden de canciones
    - `--release` falla si `git status --porcelain src/ audio/` no está vacío; produce `build/release/ngband-v<versión>.*`, `.sha256` y licencia
    - Compilación sin marcas de tiempo ni rutas absolutas, con `SOURCE_DATE_EPOCH` fijo
    - Excluir canciones comerciales y ordenar `src/songs/` alfabéticamente
    - _Requirements: 1.3, 1.4, 1.5, 1.7, 1.8_

  - [ ]* 1.3 Escribir prueba de propiedad del orden de canciones
    - **Property 33: Orden de canciones**
    - **Validates: Requirements 1.8**

  - [ ]* 1.4 Escribir pruebas de humo del Build_System
    - Compilar dos veces y comparar hashes; comprobar que `--release` falla con cambios sin commit
    - _Requirements: 1.4, 1.5_

- [x] 2. Núcleo de reglas del juego (Judge, vida, Star_Power)
  - [x] 2.1 Crear el arnés de pruebas en el host para el C
    - Definir tipos comunes (`JudgeState`, `PadInput`, `Chart`, `ChartEv`) en cabeceras sin dependencia de hardware
    - Compilar `src/*.c` puros como biblioteca de host y exponerlos con `cffi`/`ctypes` en `tests/host/conftest.py` con Hypothesis
    - _Requirements: 2.1, 2.10_

  - [x] 2.2 Implementar el Judge en `gameplay.c`
    - Hit_Window de ±6 cuadros, 50 puntos por el Multiplier (x1/x2/x3/x4 en combo 0/10/20/30), una Note por botón de acorde
    - Golpe al aire y Note perdida rompen el Combo y silencian; Sustain de 10 puntos cada 8 cuadros; estrellas por umbrales 20/40/60/80/95
    - Carriles por Difficulty (3, 4, 5, 5) y un paso por cuadro
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [ ]* 2.3 Escribir prueba de propiedad de la Hit_Window
    - **Property 1: Aciertos solo dentro de la Hit_Window**
    - **Validates: Requirements 2.2**

  - [ ]* 2.4 Escribir prueba de propiedad de puntaje y Multiplier
    - **Property 2: Puntaje y Multiplier**
    - **Validates: Requirements 2.3, 2.5**

  - [ ]* 2.5 Escribir prueba de propiedad de acordes
    - **Property 3: Los acordes cuentan una Note por botón**
    - **Validates: Requirements 2.4**

  - [ ]* 2.6 Escribir prueba de propiedad de fallos
    - **Property 4: Un fallo rompe el Combo y silencia el Instrument**
    - **Validates: Requirements 2.6, 2.7**

  - [ ]* 2.7 Escribir prueba de propiedad de Sustain
    - **Property 5: Puntos de Sustain**
    - **Validates: Requirements 2.8**

  - [ ]* 2.8 Escribir prueba de propiedad de estrellas
    - **Property 6: Estrellas por umbral**
    - **Validates: Requirements 2.9**

  - [x] 2.9 Implementar vida, Star_Power y pausa en `gameplay.c`
    - Life_Meter +1 acierto, −2 pérdida (−1 en fácil), −1 golpe al aire; fin de partida en 0 salvo SIN FALLO
    - Barra de Star_Power +25 por frase completa, tope 100, activación desde 50
    - Pausa y reanudación que conservan Judge, cursor del Chart y cuadro del stream
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 2.10 Escribir prueba de propiedad de la vida
    - **Property 7: Dinámica de la vida**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

  - [ ]* 2.11 Escribir prueba de propiedad de Star_Power
    - **Property 8: Star_Power**
    - **Validates: Requirements 3.6, 3.7**

  - [ ]* 2.12 Escribir prueba de propiedad de pausa
    - **Property 9: Pausar y reanudar conserva el estado**
    - **Validates: Requirements 3.8, 3.9, 12.7**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Herramientas de PC: VGM, Frame_Stream, Charts e importador
  - [x] 4.1 Implementar el lector de VGM y el seguimiento del YM2610
    - `vgm.py`: cabecera, bucle, `.vgm`/`.vgz`, comandos YM2610 y bloques ADPCM; informar comandos no soportados
    - `ym2610.py`: estado de registros, key-on, FM por bloque y F-number, SSG por periodo
    - _Requirements: 13.5, 14.3_

  - [x] 4.2 Implementar la extracción de notas
    - `notes.py`: una nota por key-on; un cambio de más de 3/4 de semitono con la tecla presionada es otra nota
    - _Requirements: 14.6_

  - [ ]* 4.3 Escribir prueba de propiedad de detección de notas FM
    - **Property 28: Detección de notas FM**
    - **Validates: Requirements 14.6**

  - [x] 4.4 Implementar el Frame_Stream
    - `frames.py`: agrupar escrituras por cuadro a 60 Hz, eliminar las que repiten valor, codificar `count` + pares y eventos `DRUM` (registro `0xFE`)
    - Incluir lector de prueba que decodifica el stream serializado
    - _Requirements: 14.2, 14.12_

  - [ ]* 4.5 Escribir prueba de propiedad del round trip del Frame_Stream
    - **Property 26: Round trip del Frame_Stream**
    - **Validates: Requirements 14.2, 14.12**

  - [x] 4.6 Implementar el Chart_Generator compartido
    - `chart.py` y `drums.py`: Charts de 4 Difficulties, `check_playable` (sin verde y amarillo a la vez), límites de acordes de batería, serialización y lectura del formato `ChartEv`
    - _Requirements: 2.11, 4.6, 14.7, 14.13_

  - [ ]* 4.7 Escribir prueba de propiedad de Charts jugables
    - **Property 10: Charts generados son jugables**
    - **Validates: Requirements 2.11, 4.6**

  - [ ]* 4.8 Escribir prueba de propiedad del round trip del Chart
    - **Property 27: Round trip del Chart**
    - **Validates: Requirements 14.2, 14.13**

  - [x] 4.9 Implementar `songgen.py` y la CLI `ngband`
    - Comandos `channels`, `import-song` (opciones `--title`, `--game`, `--duration`, `--guitarra`, `--teclado`, `--bajo`, `--bateria`, `--beat-frames`), `list-songs`, y registrar `gfx` y `adpcm`
    - Escribir `src/songs/<n>/song.c` (Frame_Stream y 12 Charts) e `import.json`; repetir el bucle hasta `--duration`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.9_

  - [ ]* 4.10 Escribir prueba de propiedad de duración con bucle
    - **Property 29: Duración con bucle**
    - **Validates: Requirements 14.5**

  - [x] 4.11 Implementar `reimport`, `edits.json`, `drums.json` y manejo de errores
    - `reimport` con las opciones de `import.json`; aplicar `edits.json` y omitir con aviso las ediciones huérfanas
    - Generar `drums.json` si no existe y conservarlo; error descriptivo sin escribir archivos ante VGM inválido o sin YM2610
    - _Requirements: 13.3, 13.5, 14.8, 14.10, 16.5_

  - [ ]* 4.12 Escribir prueba de propiedad de reimportar
    - **Property 30: Reimportar es idempotente y conserva ediciones**
    - **Validates: Requirements 13.3, 14.8, 16.5**

  - [ ]* 4.13 Escribir prueba de propiedad de entradas inválidas
    - **Property 31: Entradas inválidas no escriben archivos**
    - **Validates: Requirements 13.5, 14.10**

- [x] 5. Conversión ADPCM-A
  - [x] 5.1 Implementar `adpcma.py`
    - Convertir PCM a ADPCM-A, construir el mapa de samples y fallar con tamaño y sobrante si exceden la ROM `V`
    - Mapear cada golpe sampleado de un VGM a un evento `DRUM(n)` válido
    - _Requirements: 13.1, 13.2_

  - [ ]* 5.2 Escribir prueba de propiedad de la conversión ADPCM-A
    - **Property 25: Conversión ADPCM-A**
    - **Validates: Requirements 13.2**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Audio_Driver (Z80) y protocolo con el 68000
  - [x] 7.1 Implementar el núcleo del Audio_Driver y el modelo de sombra
    - Driver Z80 (SDCC) con comandos `CMD_SILENCE_ALL`, `CMD_SONG_START`, `CMD_FRAME`, `CMD_HOLD`, `CMD_MUTE_INST`, `CMD_UNMUTE_INST` (comando y argumento en dos bytes)
    - `ShadowRegs`: silenciar escribe el mínimo al chip sin tocar la sombra; restaurar copia de la sombra; respuesta con el último cuadro aplicado
    - Modelo de sombra en C compilable para el host
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.8, 12.9_

  - [ ]* 7.2 Escribir prueba de propiedad del modelo de sombra
    - **Property 24: Silenciar y restaurar en el driver**
    - **Validates: Requirements 12.3, 12.4, 12.6**

  - [x] 7.3 Completar el driver: batería, efectos, pausa y búsqueda
    - Eventos `DRUM(n)` en canales ADPCM-A round-robin; silenciar batería hasta el siguiente acierto
    - `CMD_SFX` (menú y 3 efectos de fallo) con reposición de canales desde la sombra; `CMD_PAUSE`/`CMD_RESUME`; `CMD_SONG_SEEK`
    - _Requirements: 12.5, 12.6, 12.7, 13.1, 13.4_

  - [x] 7.4 Implementar `audio_cmd.c` en el 68000
    - Envío de comandos al registro de comando y lectura de la respuesta; comando por cuadro desde el ISR de VBlank; verificación de desincronía en depuración
    - _Requirements: 12.1, 12.2, 12.8_

- [x] 8. Gráficos, sprites y Highway
  - [x] 8.1 Implementar el compilador de gráficos `ngband gfx`
    - Generar la tabla `persp[]` (`PerspRow`) a partir de horizonte, línea de golpe y anchos; al menos 7 niveles de gema
    - Convertir arte PNG y la fuente *Bongo-8 Mono* a ROM `C` y tiles fijos
    - _Requirements: 5.1, 5.2, 5.3, 7.7, 1.9_

  - [ ]* 8.2 Escribir prueba de propiedad de monotonía de la perspectiva
    - **Property 11: Monotonía de la perspectiva**
    - **Validates: Requirements 5.1, 5.2**

  - [x] 8.3 Implementar `spr.c`, `fix.c` y `vram_queue.c`
    - `SpritePool` por clase, `SpriteShadow[381]` y `FixShadow[40*32]` con diff; cola de VRAM vaciada en el ISR de VBlank con prioridad al Highway y al HUD
    - _Requirements: 5.7, 18.3, 18.4_

  - [ ]* 8.4 Escribir prueba de propiedad del diff de cuadros
    - **Property 34: El diff de cuadros es exacto**
    - **Validates: Requirements 18.3**

  - [x] 8.5 Implementar `input.c`
    - Lectura única por cuadro en el ISR, mapa verde ←, rojo ↓, amarillo →, azul B, naranja C, poder A, pausa Start; ignorar ← y → simultáneos; segundo puerto para el jugador 2
    - _Requirements: 6.1, 6.2, 6.4, 6.5_

  - [ ]* 8.6 Escribir prueba de propiedad del filtro izquierda/derecha
    - **Property 13: Filtro de izquierda y derecha**
    - **Validates: Requirements 6.1, 6.2**

  - [x] 8.7 Implementar `highway.c`
    - Gemas escaladas por profundidad, colas de Sustain, líneas de tiempo, velocidades de caída 6/5/4/3, columnas de batería con bombo, platillos como rombos o toms, Star_Power azul
    - Presupuesto de 96 sprites por línea con descarte de líneas de tiempo y colas lejanas; `x_origin` por jugador
    - _Requirements: 4.2, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8, 5.10_

  - [ ]* 8.8 Escribir prueba de propiedad del presupuesto de sprites
    - **Property 12: Presupuesto de sprites por línea**
    - **Validates: Requirements 5.6**

  - [x] 8.9 Implementar `hud.c` en la Fix_Layer
    - Puntaje, combo, multiplicador, medidor de vida y de Star_Power, textos en español
    - _Requirements: 5.9, 7.8_

- [x] 9. Integración de la fase 1
  - [x] 9.1 Implementar `main.c`, `isr.c` y la escena de juego
    - Bucle de estados esperando la bandera de VBlank; un paso por cuadro; Judge, Highway, HUD y audio conectados
    - Incluir una canción de demostración importada y reproducirla con puntaje y Combo
    - _Requirements: 2.10, 12.2, 18.1, 20.1_

  - [x] 9.2 Implementar el Test_Harness de MAME
    - `tests/run_tests.sh [patrón] [--no-build]` con MAME sin ventana, scripts Lua que inyectan entradas y leen RAM con `ngband.sym`
    - Bots perfecto, nada y machacar; guardar capturas, `audio.wav` y registro en `build/test-<nombre>/`; fallar si se pierden más de 2 cuadros
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.8, 17.9, 17.11_

  - [ ]* 9.3 Escribir pruebas de integración de la fase 1
    - Arranque en MAME, Highway en perspectiva, Bot perfecto con todas las Notes
    - _Requirements: 20.1, 17.2_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Fase 2: Instruments, Difficulties y resultados
  - [x] 11.1 Integrar vida, Star_Power, Sustain, pausa y resultados en el juego
    - Los cuatro Instruments y las cuatro Difficulties, FALLASTE, SIN FALLO, regreso al Menu con B en pausa
    - Pantalla de resultados con precisión, combo máximo y estrellas
    - _Requirements: 3.4, 3.10, 4.1, 4.3, 7.5, 20.2_

- [x] 12. Opciones y modo práctica
  - [x] 12.1 Implementar la lógica de `options.c` y `practice.c`
    - ESPEJO (invierte carriles, salvo batería), VELOCIDAD (k = 4, 3, 2, 5 pasos cada 4 cuadros con `CMD_HOLD` en los cuadros sin paso), CAIDA DE NOTAS, EFECTO AL FALLAR
    - Practice_Mode: bucle hasta 1/4, 1/2, 3/4 o final, puntos de inicio, marcas con mínimo de 4 segundos, controles A/B/C en pausa
    - Limitador de 3 efectos por segundo, cada uno distinto del anterior
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12_

  - [ ]* 12.2 Escribir prueba de propiedad de ESPEJO
    - **Property 14: ESPEJO es una involución**
    - **Validates: Requirements 8.2**

  - [ ]* 12.3 Escribir prueba de propiedad de pasos por velocidad
    - **Property 15: Pasos por velocidad**
    - **Validates: Requirements 8.3, 12.8**

  - [ ]* 12.4 Escribir prueba de propiedad de marcas y puntos de práctica
    - **Property 16: Marcas y puntos de la práctica**
    - **Validates: Requirements 8.5, 8.6, 8.7, 8.8, 8.9**

  - [ ]* 12.5 Escribir prueba de propiedad del limitador de efectos
    - **Property 17: Limitador de efectos de fallo**
    - **Validates: Requirements 8.12**

- [x] 13. Récords en backup RAM
  - [x] 13.1 Implementar `records.c`
    - `records_encode`/`records_decode` puros en big endian con firma `NGBR` y suma de comprobación; tabla vacía si no coinciden
    - Acceso a backup RAM con `unlock/lock`, cuerpo primero y firma al final; ejecutar con la tabla en RAM si no hay backup RAM
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 13.2 Escribir prueba de propiedad del round trip de récords
    - **Property 18: Round trip de la tabla de récords**
    - **Validates: Requirements 9.1, 9.2, 9.6, 9.7**

  - [ ]* 13.3 Escribir prueba de propiedad de tablas corruptas
    - **Property 19: Tablas corruptas se descartan**
    - **Validates: Requirements 9.3, 9.4**

  - [x] 13.4 Implementar `is_record_eligible` y la actualización del mejor récord
    - Falso si perdió, SIN FALLO, opciones distintas de la normal (salvo EFECTO AL FALLAR) o VS; en COOP solo si los dos terminan en pie
    - _Requirements: 9.5, 10.3, 10.8_

  - [ ]* 13.5 Escribir prueba de propiedad de elegibilidad
    - **Property 20: Elegibilidad y mejor récord**
    - **Validates: Requirements 9.5, 10.3, 10.8**

- [x] 14. Pantallas: título, Menu y opciones
  - [x] 14.1 Implementar las escenas de título, Menu, Options_Screen y resultados
    - Título con versión y música en bucle; Menu con canción, instrumento, dificultad, fallo y jugadores, récord o `---`, reproducción de la canción elegida
    - Controles del Menu (↑/↓, ←/→, Start, A, B); NUEVO RECORD con entrada de tres iniciales
    - _Requirements: 6.3, 7.1, 7.2, 7.3, 7.4, 7.6, 8.1, 20.3_

  - [ ]* 14.2 Escribir pruebas de ejemplo de pantallas y textos
    - Textos en español, `---` sin récord, entrada de iniciales, mapa de controles, velocidades de caída y 7 niveles de gema
    - _Requirements: 5.3, 5.8, 6.3, 7.4, 7.6, 7.8_

- [x] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Escenario
  - [x] 16.1 Implementar la máquina de estados `stage.c`
    - `stage_step` con público (quieto, brazos, salto), fase de luz cian/rojo/amarillo/violeta solo con Star_Power, latido, rayo y destello, luces apagadas si todos perdieron
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ]* 16.2 Escribir prueba de propiedad del Stage
    - **Property 23: Estado del Stage**
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.7**

  - [x] 16.3 Dibujar el Stage con sprites del pool "escenario"
    - Bocinas, torres con foco, haces de luz y público con el presupuesto restante tras el Highway; torre central entre Highways en 2 jugadores
    - _Requirements: 11.1, 11.8, 20.4_

- [x] 17. Canciones originales
  - [x] 17.1 Implementar la conversión de FamiStudio a VGM del YM2610
    - `famistudio.py`: pulso 1 en FM 1, pulso 2 en FM 2, triángulo en FM 3, ruido y DPCM a batería; patch FM por nombre de instrumento y volumen a atenuación
    - _Requirements: 15.2, 15.3_

  - [x] 17.2 Importar las diez canciones y los efectos de sonido
    - Importar las diez canciones de NESBand (*Cumbia del Cartucho* con `--beat-frames 36`) a `src/songs/`, incluir los efectos de `efectos.txt` y la nota de licencia GPL-2.0-or-later
    - _Requirements: 15.1, 15.4, 15.5, 12.5_

- [x] 18. Dos jugadores (VS y Co-Op)
  - [x] 18.1 Implementar `versus.c` (reglas de VS y COOP)
    - VS: estado por jugador, `GANA J1 POR n`, `GANA J2 POR n`, `EMPATE`, ganador si el otro pierde
    - COOP: puntaje, Combo y Star_Power compartidos, vida individual, revivir con media barra, fin cuando caen los dos, instrumentos distintos
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [ ]* 18.2 Escribir prueba de propiedad del resultado de VS
    - **Property 21: Resultado de VS**
    - **Validates: Requirements 10.1, 10.2, 10.3**

  - [ ]* 18.3 Escribir prueba de propiedad de las reglas de COOP
    - **Property 22: Reglas de COOP**
    - **Validates: Requirements 10.4, 10.5, 10.6**

  - [x] 18.4 Integrar el modo de 2 jugadores
    - Dos Highways, segundo puerto de control, presupuesto de sprites dividido, selección en el Menu, récord de banda en COOP
    - _Requirements: 5.10, 6.4, 10.8, 11.8, 20.5_

- [x] 19. Chart_Editor
  - [x] 19.1 Implementar el servidor del editor y las ediciones
    - `ngband edit-chart [canción]` en `127.0.0.1`; ediciones (`add`, `move`, `delete`, `set_flags`) con deshacer/rehacer; guardar solo la diferencia en `edits.json`; `check_playable` para marcar Notes inválidas; tabla de papeles de batería con rehacer inmediato
    - _Requirements: 16.1, 16.3, 16.4, 16.8, 16.9_

  - [x] 19.2 Implementar la interfaz web y Escuchar
    - Línea de tiempo con canales FM 1-4, SSG 1-3, ADPCM-A/B y rejilla; emulador JS del YM2610 con el mismo Frame_Stream; silenciar (M) y solo (S) por canal
    - _Requirements: 16.2, 16.6, 16.7_

  - [ ]* 19.3 Escribir prueba de propiedad de las ediciones
    - **Property 32: Ediciones del editor**
    - **Validates: Requirements 16.3, 16.4, 16.8**

- [x] 20. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 21. Pruebas automáticas completas
  - [x] 21.1 Completar el Test_Harness de MAME
    - Bot humano (~90% de partidas terminadas, ~45% perdidas en la dificultad más alta); sincronía de audio con el Chart dentro de un cuadro, incluso tras pausar
    - Casos de ESPEJO, velocidades, Practice_Mode, SIN FALLO, batería, récords con persistencia tras reiniciar, VS y COOP; rendimiento en 1 y 2 jugadores con el peor caso de sprites
    - Asegurar que `uv run pytest` cubra lector de VGM, notas, generador, editor y ADPCM-A
    - _Requirements: 17.5, 17.6, 17.7, 17.10, 17.12, 18.1, 18.2, 20.6_

- [x] 22. Documentación y paridad
  - [x] 22.1 Escribir README, CLAUDE.md, LICENSE y actualizar la paridad
    - `README.md` en español (instalación, compilación, controles, reglas, importación, editor, pruebas, hoja de ruta, aviso de código escrito por IA y de que no hay relación con SNK), `CLAUDE.md` que exige actualizar `../NESBand/docs/paridad.md`, `LICENSE` GPL-2.0-or-later
    - Agregar la fila y columna NGBand en la paridad
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

- [x] 23. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Las sub-tareas marcadas con `*` son opcionales y se pueden omitir para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints validan el avance de forma incremental
- Las pruebas de propiedades (Hypothesis, mínimo 100 ejemplos) validan las propiedades 1 a 34 del diseño; cada una lleva la etiqueta `Feature: neogeo-band, Property N: ...`
- La lógica pura en C se prueba en el host con la misma fuente que va en la ROM
- Lo que depende del hardware (VBlank, VRAM, Z80, backup RAM, rendimiento) se cubre con pruebas de integración en MAME

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.2", "4.4", "4.6", "5.2", "8.1"] },
    { "id": 2, "tasks": ["1.3", "2.2", "4.3", "4.5", "4.7", "4.8", "4.9", "8.2", "8.3", "8.5"] },
    { "id": 3, "tasks": ["1.4", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "4.10", "4.11", "7.1", "8.4", "8.6", "8.7"] },
    { "id": 4, "tasks": ["2.10", "2.11", "2.12", "4.12", "4.13", "7.2", "7.3", "7.4", "8.8", "8.9", "12.1", "13.1"] },
    { "id": 5, "tasks": ["9.1", "12.2", "12.3", "12.4", "12.5", "13.2", "13.3", "13.4", "16.1", "17.1", "18.1", "19.1"] },
    { "id": 6, "tasks": ["9.2", "11.1", "13.5", "16.2", "17.2", "18.2", "18.3", "19.2"] },
    { "id": 7, "tasks": ["9.3", "14.1", "19.3"] },
    { "id": 8, "tasks": ["14.2", "16.3"] },
    { "id": 9, "tasks": ["18.4"] },
    { "id": 10, "tasks": ["21.1"] },
    { "id": 11, "tasks": ["22.1"] }
  ]
}
```
