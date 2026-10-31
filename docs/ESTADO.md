# Estado de NGBand y cómo continuar

Última sesión (2026-10-30, tarde): las 10 canciones entran y el audio suena en MAME; el arnés completo ya corre.
Este archivo es el punto de partida para cualquier agente o persona que siga el trabajo. Léelo junto con
`CLAUDE.md`, `README.md` y la spec en `.kiro/specs/neogeo-band/` (requirements.md, design.md, tasks.md).

## Resumen en una línea

La ROM compila con **las 10 canciones**, en MAME **suena**, y la autopista tiene **pista fija** (sprites) con
franjas que se mueven solas. Repositorio público: <https://github.com/Xalcker/NGBand>. Las 250 pruebas del host
pasan. En `tests/run_tests.sh` (`-DNGBAND_DEBUG`): **34 de 55 casos pasan**, 0 desincronías; los bots perfectos
aciertan todo en todos los modos. Lo que falla: sincronía audio/Chart con fallos (14), 2 jugadores (cuadros
perdidos), récord tras apagar, Practice y la calibración del bot humano.

## Sesión 5 (2026-10-30): bandcore

- `pctools/ngband_tools/vgm.py` ahora lee con **bandcore** (repo hermano en `../bandcore`, dependencia de uv por
  ruta): el lector genérico de VGM que comparten GENBand y NGBand. Entrega lo mismo que antes (se comprobó con una
  huella de los 10 VGM de `audio/`) y las pruebas del host pasan igual (128, 123 saltadas en Windows).
- `uv run band inspect archivo.vgz` (desde `../bandcore`) dice qué chips usa un VGM y para qué juego sirve.
- Las páginas del editor de charts (editor.html, home.html, menú) ahora son las de **bandcore**, iguales en los cuatro
  juegos; `editor.py` solo pone el perfil de la Neo Geo (`PROFILE`) y el adaptador de `ngplayer.js`. Se probó en Chrome
  sin ventana: la página abre, Escuchar suena y avanza, las teclas silencian canales y la de inicio no ofrece
  «Nueva canción» (NGBand importa por línea de comandos).
- `chartedit.py` y `ChartNote`, `check_playable`, `lanes_clash` y las parejas bloqueadas de `chart.py` ahora vienen de
  bandcore (eran iguales en los cuatro juegos). `ngband reimport` de las 10 canciones da los mismos charts; solo mueve
  una línea vacía en cada `song.c`, igual que con el código anterior (es de `songgen.py`, ya pasaba).
- El servidor del editor (rutas, App, Handler) es el de bandcore (`bandcore.editor.server`); `editor.py` define
  `Game` con lo propio de la Neo Geo. `make_server(name, port, root)` y `App(sd, root)` siguen igual para las pruebas.
  Probado en Chrome: abrir, Escuchar, Guardar y Exportar.
- El generador de charts (`Note`, dificultades, carriles, acordes, colas, frases estelares, `build_chart`) y la
  batería (papeles, drums.json, `build_drum_chart`) vienen de bandcore. NGBand conserva `chart_entries` y `chart_size`
  (su formato parte también los saltos de 255 exactos), lo de `song.c` y la agrupación de golpes del ADPCM.
  `ngband reimport` de las 10 canciones da los mismos archivos que antes. Los `song.c` se regeneraron una vez para que
  la línea vacía que movía `songgen.py` deje de aparecer como cambio.
- **Primer VGM comercial (Metal Slug, Stage 1):** importa y suena en el reproductor del editor. Destapó un error: los
  bloques de datos de ADPCM se leían con los tipos corridos ($81/$82); la especificación de VGM dice $82 = ADPCM-A y
  $83 = ADPCM-B (los VGM de Metal Slug traen 1.4 MB de ADPCM-A en $82). Corregido en `vgm.py`. Los VGM propios de
  NGBand no traen bloques, por eso no se había notado. Falta compilar una ROM con un VGM comercial y oírla en MAME.

## Sesión 4 (2026-10-30): pista fija y repositorio

- **Pista fija** (`src/track.c`, arte en `gfx.py` `draw_track`): trapecio de 14 columnas x 10 tiles con la
  superficie, bordes, 4 divisores y los aros de golpe. Usa los sprites de hardware 1-28 (14 por jugador; con 2
  jugadores se encoge a columnas de 12 px), que se escriben una vez al empezar la canción (`track_show`) y se
  ocultan al salir (`track_hide`, también en `screen_reset`). La sombra de sprites empieza en el 29
  (`SPR_HW_BASE`): la pista queda detrás de todo y el sprite 0 ya no se usa (con eso desapareció el tile rojo
  suelto de la pantalla de resultados).
- **Franjas que bajan sin CPU:** cada celda trae 8 tiles (una fase cada uno, alineados a 8) y la autoanimación de
  3 bits del LSPC (`SCB1` bit 3) los cicla. `REG_LSPCMODE` (bits 15-8) fija cuadros por fase = 2·caída/pasos
  (redondeado), así que van a la velocidad de las gemas (exacto en 100% con caída par); el bit 3 las congela en
  pausa. Periodo de 32 px en Y, lineal como el movimiento de las gemas (`row_of`).
- **Sin líneas de tiempo con sprites** (`beat_frames = 0` en `play.c`): usaban el tile de la gema y se veían como
  bloques; quitarlas bajó los cuadros perdidos (VS de 2847 a ~45, fácil de 4 a 1).
- **5 carriles siempre** (como NESBand): `highway_view_init` pone `ncols = 5` (batería: 4) y fácil/medio usan los
  primeros 3/4; antes se centraban 3 o 4 columnas y las gemas no caían en los carriles de la pista. Con ESPEJO se
  invierten solo los carriles en uso (`lane_col`, igual que `options_mirror_ev`). La pista tiene 5 variantes
  (`TRACK_VARIANTS` en gfx.py: normal, espejo con 3/4/5 carriles y batería) y `track.c` elige por vista.
- **Cola, bombo y platillo con arte propio** (`HWY_PIECES` en gfx.py): la cola es una barra continua y el bombo
  una banda; antes se apilaba el tile de la gema. Pendiente: la cola se ve unos px a la derecha de la gema.
- **Audio comparado contra la referencia** (`ngplayer.js`, el reproductor del editor): misma afinación (0 cents),
  mismo balance por bandas y tempo estable (1418 de 1440 VBlanks aplican 1 cuadro; 11 veces 0 y luego 2). El driver
  toca lo que dice el stream; si la música "suena mal", es el arreglo o los patches FM de las canciones
  (convertidas de FamiStudio, 4 canales FM, la batería en FM 4), no el Z80. Se corrigió el reset del ADPCM-B
  (escribía 0x80 = START en el registro 0x10). WAVs para comparar de oído: `build/audiocmp/ref.wav` y `mame.wav`.
- **Git:** `git init`, autor `Xalcker` con el correo noreply de GitHub, y `gh repo create Xalcker/NGBand --public`.
  `docs/paridad-ngband.md` y `docs/paridad-propuesta.md` quedaron fuera (`.git/info/exclude`): la paridad vive
  solo en NESBand. Se pueden borrar.

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
git clone https://github.com/Xalcker/bandcore.git ../bandcore   # lector de VGM compartido (dependencia de uv)
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

1. **Sincronía audio/Chart con fallos** (14 casos, 2-4 cuadros pasajeros; 7-10 con 2 jugadores): MUTE/UNMUTE y
   SFX son de 2 bytes y la cola (`AC_QUEUE_SIZE` 16, un byte por VBlank) se atrasa o se llena. Ideas: cola más
   grande, mandar los FRAME antes que los silencios, juntar MUTE+UNMUTE del mismo instrumento.
2. **2 jugadores:** VS pierde ~45 cuadros, Co-Op que cae ~160. Perfilar como en la sesión 3.
3. **Récord que no sobrevive al apagar** (`demo-record-persiste`): se guarda al inicio de la backup RAM
   (0xD00000), que en el MVS es de la BIOS. Usar el bloque que la BIOS guarda y restaura (cabecera del cartucho).
4. **Practice** (`marcha-practica`: el bot no ve vueltas) y **bot humano** (pierde 0% en experto).
5. **Pista:** ajustar colores/franjas a gusto; el poder estelar podría cambiar la paleta de la pista
   (`GFX_PISTA_PAL`); las líneas de tiempo, si vuelven, mejor dentro del arte que con sprites.
6. **Escuchar el audio con oído**; **hardware real**. La paridad vive solo en `../NESBand/docs/paridad.md`
   (columna NG); actualízala ahí al terminar cada mejora.

## Cuidado

- **`ini/`**: MAME lee `ini/mame.ini` (siempre en ventana, nunca pantalla completa) e `ini/ui.ini`
  (`skip_warnings`) cuando se corre desde la raíz del repositorio. Las pruebas usan `-video none` (sin ventana);
  `NGBAND_MAME_WINDOW=1` la muestra en segundo plano.

- **No corras dos `tests/run_tests.sh` a la vez:** cada uno recompila (`./build.sh` borra `build/rom`, `build/obj`)
  y escriben en las mismas carpetas `build/test-*`; los resultados salen mezclados.
- `g_audio.desync_count` solo cuenta con `-DNGBAND_DEBUG`; sin eso el arnés siempre ve 0 desincronías.

- `build/` se borra y regenera en cada `./build.sh`. Los scripts de MAME viven en `tests/mame/`.
- Las direcciones de RAM cambian en cada compilación: léelas siempre de `build/ngband.sym`.
