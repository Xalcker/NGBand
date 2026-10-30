# Estado de NGBand y cómo continuar

Última sesión (2026-10-30, tarde): las 10 canciones entran y el audio suena en MAME; el arnés completo ya corre.
Este archivo es el punto de partida para cualquier agente o persona que siga el trabajo. Léelo junto con
`CLAUDE.md`, `README.md` y la spec en `.kiro/specs/neogeo-band/` (requirements.md, design.md, tasks.md).

## Resumen en una línea

La ROM compila con **las 10 canciones** y en MAME **suena**. Las 249 pruebas del host pasan. En
`tests/run_tests.sh` (última corrida limpia, con `-DNGBAND_DEBUG`): **14 de 55 casos pasan**, **0 desincronías**
de audio y los bots perfectos aciertan todas las Notes en todos los modos (espejo, velocidades, VS, Co-Op,
batería). Casi todo lo que falla es **rendimiento** (cuadros perdidos), sobre todo con 2 jugadores (~40%).

## Sesión 3 (2026-10-30, noche): por qué el bot fallaba y qué se arregló

- **Verificación del audio por bytes:** el Z80 responde cuántos bytes procesó (`rx_count`, solo CMD_RESET lo pone
  en 0) y el 68000 lo compara con los enviados (`AudioCmd.sent`). Contar cuadros era ambiguo con reinicios
  seguidos (el Menu cambia de canción) y el Z80 atrasado. `expected` (cuadros) queda para el sync del bot.
- **Toques en cuadros sin paso (velocidad 50%/75%):** `play_frame` guarda los flancos (`s_held_edge`) hasta el
  siguiente paso del Judge; antes se perdían.
- **Bot y ESPEJO:** el bot toca el botón físico invertido (`phys_lane`).

- **Toques perdidos (bug real del juego):** `input_poll` corre en el ISR y recalculaba el flanco en cada VBlank;
  si el bucle principal perdía un cuadro, el flanco de ese VBlank se pisaba. Ahora el ISR invierte un bit por
  flanco (`s_tog`) y `input_take()` (al empezar cada paso, en main.c) junta los flancos desde el paso anterior.
- **Audio atrasado ~11 cuadros respecto a la Chart:** la cola del 68000 traía los cuadros de la vista previa del
  Menu. `play_enter` hace `ac_flush`, y `ac_next_byte` recupera atraso (salta HOLD de sobra, junta FRAME+FRAME en
  FRAME2). Antes un MUTE/UNMUTE (2 bytes) dejaba un byte de atraso para siempre.
- **Verificación del audio (`ac_check`):** tras RESET/SILENCE_ALL/SONG_START espera (hasta `AC_RESTART_WAIT`) a que
  el Z80 reinicie su cuenta; tolera atrasos de hasta 16 cuadros que no duren 30 VBlanks. El primer cuadro de una
  canción (~145 pares) le toma ~3 VBlanks al Z80.
- **Cuadros perdidos (550 → 1 en experto):**
  - `stage_draw.c`: `pulse` y `flash` son cuentas regresivas; se comparaban tal cual y el Stage se rehacía en
    cada cuadro. Ahora el Stage usa una **paleta viva** (`STAGE_LIVE_PAL` = 32): cambiar la luz copia 16 colores en
    vez de cambiar la paleta de cada sprite; solo el público y el rayo rehacen el dibujo.
  - `stage_layout.c`: no cuenta línea por línea mientras el total del Highway + los sprites del Stage no lleguen al
    presupuesto (`go_exact` cuando hace falta; `stg_count_lines` llena `line_cnt` para las pruebas).
  - `highway_layout.c`: sin `% 24` (era una división de 32 bits por Note); `hud.c`: dígitos con `divu`.
  - `vram_queue.c`: `vq_flush` vacía los arreglos con punteros (sin `vq_pop` por palabra).
  - El HUD espera un cuadro si el Stage se rehizo en ese cuadro.
- **Bot (`autoplay.lua`):** botones `P1 A..D`; toca una Note en cuanto `now >= frame` (hasta 2 cuadros tarde, una
  vez), porque el reloj puede avanzar 2 entre VBlanks. `NGBAND_BOT_DEBUG=1` anota toques que el juego no vio.
- **Aviso de MAME** ("WRONG CHECKSUMS", BIOS libre): `ini/ui.ini` con `skip_warnings 1`, que MAME lee al correr
  desde la raíz del repositorio. Sin confirmar que lo quite (sin `-video none` no se puede ver desde aquí).

## Herramientas instaladas (macOS, Apple Silicon)

```bash
brew tap dciabrin/ngdevkit && brew trust dciabrin/ngdevkit && brew install ngdevkit   # GCC m68k, romtool, BIOS libre
brew install sdcc        # el SDCC de ngdevkit NO trae cc1 (no compila C); el driver Z80 usa este
brew install mame uv pkg-config
```

- `m68k-neogeo-elf-gcc` y `pkg-config --cflags/--libs ngdevkit` (crt0, cabecera de ROM, `rom_callback_VBlank`).
- `romtool.py` está en `$(brew --prefix)/Cellar/ngdevkit/*/bin/` y se llama con `sh romtool.py ...`
  (el archivo es un script de shell, no de Python).
- La BIOS libre (`neogeo.zip`, `aes.zip`) sale de `pkg-config --variable=sharedir ngdevkit`.

## Compilar, jugar y probar

```bash
./build.sh                                   # deja build/rom/ngband.zip, neogeo.xml, la BIOS y build/ngband.sym
mame neogeo -hash build/rom -rp build/rom -cart1 ngband -w      # jugar (1 = Start, flechas, Ctrl=A, Alt=B, Espacio=C)
uv run pytest tests/host pctools/tests       # pruebas del host (245)
tests/mame/run.sh smoke                      # humo en MAME sin ventana: pantallas, VBlanks vs pasos, capturas
tests/mame/run.sh audio                      # Menu con la última canción: WAV (RMS por segundo) y stream del Z80
tests/mame/run.sh trace                      # perfil: instrucciones del 68000 por función en 3 cuadros de juego
NGBAND_CFLAGS=-DNGBAND_DEBUG tests/run_tests.sh      # el bot completo (DEBUG para contar desincronías del audio)
NGBAND_MAME_WINDOW=1 tests/mame/run.sh smoke # con ventana, sin quitarte el foco (también en run_tests.sh)
NGBAND_SONGS=demo,tormenta ./build.sh        # elegir canciones
NGBAND_CFLAGS="-DNGBAND_EXP_NO_HWY" ./build.sh   # experimentos: _NO_HWY, _NO_STAGE, _TIMING (ver play.c draw())
```

En `log.txt` del humo, `step` debe crecer igual que `vblank`; si crece menos, el bucle principal pierde cuadros.
Las advertencias "WRONG CHECKSUMS" de MAME son normales: vienen de la BIOS libre de ngdevkit.
`NGBAND_MAME_WINDOW=1` (tests/mame/mame.sh) abre la ventana de MAME en segundo plano y le devuelve el foco a la app
que estaba al frente (con `lsappinfo`/`open -b`; puede verse un parpadeo). El sonido sigue apagado; el audio queda
en el WAV.

## Cómo se arma la ROM (build.sh)

1. `ngband gfx` (C1/C2/S1, `gfx_data.h`), `ngband adpcm` (por ahora vacío), `ngband list-songs`.
   `list-songs` también escribe `build/gen/z80/z80_songs.c`: los Frame_Streams y `song_table` para el Z80, y
   elige las canciones que caben (`songlist.py`, `M1_STREAM_BUDGET`).
2. Z80: `sdasz80` (src/z80/crt0.s) + `sdcc -mz80` (driver.c, shadow.c, z80_songs.c) + `sdldz80` con
   `-b _CODE=0x0100 -b _DATA=0xF800`. El driver debe caber en los 32 KB fijos (0x0000-0x7FFF). Detrás van los
   Frame_Streams **comprimidos** (`build/gen/z80/streams.bin`, desde 0x8000 de la M1); la M1 se rellena a una
   potencia de 2 (hoy 256 KB, 176 KB de streams). `z80_songs.c` solo trae la tabla de posiciones.
3. 68000: GCC de ngdevkit con `$(pkg-config --cflags ngdevkit)` y `-DNGBAND_NO_STREAM` (los song.c dejan fuera
   de P1 su stream: P1 bajó de 822 KB a 170 KB), enlace con `$(pkg-config --libs ngdevkit)`
   (**sin** `--gc-sections`: se lleva el juego). P1 = objcopy binario, relleno a 1 MB y `dd conv=swab`.
4. C1/C2 (2 MB), S1 (128 KB) y V1 (512 KB, vacía) rellenos; `romtool` arma el zip y `neogeo.xml`.

## Audio del Z80 (lo que hay que saber)

- **Arranque:** la BIOS deja al Z80 en un bucle en RAM (`jr $` en 0xFFFE) con la NMI apuntando a nuestra M1. El
  driver no corre hasta que llega `CMD_RESET` (0x03), que el 68000 manda en `ac_hw_init`; la NMI salta a 0x0000 y
  crt0 limpia la RAM. **Antes de esta sesión el driver nunca arrancaba: el juego no tenía música.**
- **Protocolo:** 0x03 es `CMD_RESET` (sin argumento, también lo usa la BIOS); `CMD_SONG_SEEK` pasó a 0x0C. La NMI
  solo encola el byte (sabe qué bytes son argumentos, para no reiniciar con un 3 de argumento); el bucle principal
  procesa y escribe la respuesta. Un comando largo ya no anida NMIs.
- **Bancos:** `map_stream` pone la posición en la ventana de 16 KB (0x8000, `IN (0x0B)`) y los 8 KB siguientes en
  la de 0xC000 (`IN (0x0A)`): desde cualquier inicio de cuadro se ven `SH_MAP_SPAN` (8 KB) seguidos. shadow.c usa
  posiciones lineales de 32 bits y una función `map` (en el host, base + posición), así sigue probado en el host.
- **MAME solo direcciona 256 KB de M1** (los bancos dan la vuelta en 0x40000; se midió leyendo las ventanas). Por
  eso los streams van comprimidos: `frames.compress_stream` cambia rachas de cuadros ya tocados por
  `FS_REPEAT` (count = 254, desplazamiento de 24 bits, n de 16 bits); la racha citada nunca trae otro REPEAT, así
  que el driver solo guarda un punto de regreso (`ret`, `rep_left`). 637 KB → 176 KB. El build verifica que se
  expande igual al original. Un cuadro literal de exactamente 254 pares ahora sale como continuación + 0.
- **Verificación de sincronía (`ac_check`):** tolera que la respuesta vaya hasta `AC_MAX_LAG` (4) cuadros atrás
  durante menos de `AC_LAG_LIMIT` (30) VBlanks (un cuadro pesado del stream tarda ~1 cuadro de video en el Z80), y no
  verifica unos VBlanks tras `CMD_RESET`/`SILENCE_ALL`/`SONG_START`. `shadow_silence_all` usa `memset` (el bucle de
  C sobre 512 bytes tomaba casi un cuadro del Z80).
- `g_sh` (la sombra del Z80) es global para que salga en `build/obj/z80/m1.map`; `tests/mame/audio.lua` lee de ahí
  `start/pos/end/frames` (offsets en el comentario del script: cambian si cambia `ShadowRegs`).

## Pendientes, en orden sugerido

1. **Rendimiento (37 casos fallan por cuadros perdidos).** Con 2 jugadores se pierde ~40% (VS/Co-Op: 2800-7200
   cuadros); batería ~245; bajo/teclado 50-100; guitarra experto ~27; fácil 4. En 1 jugador cada cuadro va justo
   (idle ≈ 0): lo que más pesa es `spr_flush`/`spr_set` (~6-10K instrucciones), `hwy_build`/`admit` y el ISR que
   vacía la cola de VRAM. Para perfilar: traza con `-debug -debugger none` durante el juego del bot (envolver
   `tests/autoplay.lua` con `dofile` y `dbg:command("trace ...")`) y separar por entrada a `rom_callback_VBlank`.
   Ideas: no rehacer/rediferenciar sprites que no se movieron, escribir sin cola los sprites del Highway que
   cambian todos los cuadros, menos filas/gemas visibles con 2 jugadores.
2. **Récord que no sobrevive al apagar** (`demo-record-persiste`): se guarda (se ve `NGBR` y `BOT` en
   `build/test-nvram-records/neogeo/saveram`) pero al principio de la backup RAM (0xD00000), que en el MVS es de
   la BIOS (su firma y sus datos; puede reinicializarla al arrancar). Lo correcto en Neo Geo: la cabecera del
   cartucho apunta a un bloque de RAM de trabajo y la BIOS lo guarda y restaura. Revisar qué ofrece ngdevkit.
3. **Practice** (`marcha-practica`): el bot no ve vueltas (`vueltas None`); revisar `bot.log` del caso.
4. **Bot humano:** pierde 0% en experto (debe rondar 45%): ajustar `HUMAN` en `tests/autoplay.lua`.
5. **Sprite suelto en la pantalla de resultados** (un tile rojo arriba, sigue el carril de la última Note;
   probablemente la primera pieza del rayo). La sombra lo da por oculto.
6. **Escuchar el audio con oído**; **hardware real**. La paridad vive solo en `../NESBand/docs/paridad.md`
   (columna NG, actualizada el 2026-10-30); actualízala ahí al terminar cada mejora.

## Cuidado

- **`ini/`**: MAME lee `ini/mame.ini` (siempre en ventana, nunca pantalla completa) e `ini/ui.ini`
  (`skip_warnings`) cuando se corre desde la raíz del repositorio. Las pruebas usan `-video none` (sin ventana);
  `NGBAND_MAME_WINDOW=1` la muestra en segundo plano.

- **No corras dos `tests/run_tests.sh` a la vez:** cada uno recompila (`./build.sh` borra `build/rom`, `build/obj`)
  y escriben en las mismas carpetas `build/test-*`; los resultados salen mezclados.
- `g_audio.desync_count` solo cuenta con `-DNGBAND_DEBUG`; sin eso el arnés siempre ve 0 desincronías.

- NGBand no es un repositorio git todavía, así que `./build.sh --release` se niega.
- `build/` se borra y regenera en cada `./build.sh`. Los scripts de MAME viven en `tests/mame/`.
- Las direcciones de RAM cambian en cada compilación: léelas siempre de `build/ngband.sym`.
