# NGBand

Un juego de ritmo estilo Guitar Hero / Rock Band para la SNK Neo Geo (MVS/AES, cartucho). Es de la familia de
[NESBand](https://github.com/Xalcker/NESBand), GBBand y GENBand: las mismas reglas y el mismo generador de charts,
con la autopista en perspectiva de GENBand (aquí hecha con sprites escalados por hardware) y el sonido del
YM2610, con la batería en ADPCM-A.

**Estado actual (v0.1.0): la ROM compila y arranca en MAME, con las 10 canciones y su música.** Ver
`docs/ESTADO.md` para el detalle.

- `./build.sh` produce `build/rom/ngband.zip` (con ngdevkit y SDCC) y se juega con
  `mame neogeo -hash build/rom -rp build/rom -cart1 ngband -w`.
- La música va en la ROM M1 del Z80 (256 KB): el driver la lee por bancos y comprimida (repite los compases que ya
  sonaron). En MAME suena y se verificó por WAV y por la posición del stream; falta escucharla con oído.
- No se ha probado en hardware.

Hasta que eso se haga, no hay garantía de que la ROM arranque. Lo que sí hay, por funciones: título con música, menú
(canción, instrumento, dificultad, fallo, jugadores), juego para **1 o 2 jugadores** (VS y Co-Op) con pausa, notas
sostenidas, frases de poder estelar, medidor de vida, resultados con precisión, combo máximo y estrellas, opciones y
modo práctica, récords en la memoria de respaldo, escenario con público, 10 canciones originales, importador de
VGM del YM2610 y editor de charts con Escuchar.

## Sobre este proyecto

Todo el código de NGBand lo escribió una IA (Claude), igual que el de las demás versiones.

**Aviso:** NGBand es un proyecto de aficionados, sin relación con SNK, Harmonix ni Activision, ni con Guitar
Hero ni Rock Band. "Neo Geo" solo indica la plataforma para la que está hecho.

## Instalación (macOS)

```bash
brew install uv sdcc mame
```

Falta el compilador del 68000: **ngdevkit** (`m68k-neogeo-elf-gcc` y sus herramientas). Sigue sus instrucciones
de instalación en <https://github.com/dciabrin/ngdevkit>; `build.sh` falla con un mensaje claro si no lo encuentra.

- **ngdevkit**: GCC para el 68000 (y, en general, las herramientas de gráficos y sonido de la Neo Geo).
- **SDCC**: el compilador del Z80, para el driver de audio.
- **uv**: para las herramientas de Python (`uv sync` crea el venv).
- **MAME**: el emulador para jugar y para las pruebas automáticas (tiene Lua). Necesita la BIOS `neogeo`
  (no se incluye en el repositorio).

`tools/` está en `.gitignore`: cada máquina baja sus propias herramientas. `PREFIX=` cambia el prefijo del
compilador (por defecto `m68k-neogeo-elf-`).

## Compilar y jugar

```bash
./build.sh
```

Deja `build/ngband.*` (la ROM) y `build/ngband.sym` (los símbolos, que usan las pruebas). El orden es: gráficos
(`ngband gfx`), samples ADPCM-A (`ngband adpcm`), lista de canciones (`ngband list-songs`), driver Z80 (SDCC) y
68000 (GCC). Las canciones ya convertidas viven en `src/songs/`. La compilación es reproducible (fecha, zona
horaria y locale fijos, sin rutas absolutas).

Para jugar, `build/rom` trae el cartucho (`ngband.zip`), su `neogeo.xml` y la BIOS libre de ngdevkit:
`mame neogeo -hash build/rom -rp build/rom -cart1 ngband -w`.

**Release:** `./build.sh --release` deja `build/release/ngband-v<versión>.*` con su suma de verificación (`.sha256`)
y la licencia. Solo usa lo que está en git (si hay cambios sin commit en `src/` o `audio/`, se niega): las
canciones importadas de juegos comerciales nunca entran. La versión sale del archivo `VERSION` y se ve en la
pantalla de título.

La ROM es para **NTSC (~59.19 Hz)**: el juego avanza un paso por cuadro de video y las reglas lo llaman "60 Hz". PAL
no se soporta.

### Controles

La palanca de la Neo Geo tiene 4 direcciones y 4 botones (A, B, C, D), más Start. Es el mismo mapa de 3 botones de
GENBand.

**Menú:** ↑/↓ elige el renglón, ←/→ cambia el valor, Start juega, **A abre las opciones** y B regresa al título.
Mientras eliges, suena la canción.

**Juego:**

| Carril        | Botón |
|---------------|-------|
| Verde         | ←     |
| Rojo          | ↓     |
| Amarillo      | →     |
| Azul          | B     |
| Naranja       | C     |
| Poder estelar | A     |
| Pausa         | Start |

← y → a la vez no cuentan (la cruz no los debe dar juntos); los charts no piden verde + amarillo a la vez. En la
pausa, Start sigue y B sale al menú (en una práctica: A y B ponen las marcas y C sale).

**Dos jugadores:** en JUGADORES, ←/→ cambia entre `1 JUGADOR`, `2 JUGADORES VS` y `2 JUGADORES COOP`. El jugador 2
elige su instrumento y su dificultad con el **segundo control**. Con la misma lógica de NESBand y GENBand:

- **VS:** cada quien juega su partida sobre las mismas notas. Gana el mayor puntaje; si un jugador pierde, gana el
  otro y esa partida no graba récord.
- **Co-Op (banda):** el puntaje, el combo y el poder estelar son de la banda; la vida es de cada quien. El que
  sigue en pie puede revivir al caído con media barra de poder estelar. El récord de banda es aparte.

**Opciones (A en el menú):** ESPEJO, VELOCIDAD (100%, 75%, 50%, 125%), CAIDA DE NOTAS, PRACTICA (bucle con marcas
A/B en la pausa), INICIO DE LA PRACTICA y EFECTO AL FALLAR. Con cualquier opción distinta de la normal no se
guardan récords (salvo EFECTO AL FALLAR).

**Batería** (4º instrumento): bombo como barra naranja (**C**), tarola en rojo (↓), tom 1 / hi-hat en amarillo (→),
tom 2 / ride en azul (B) y tom 3 / crash en verde (←). Los platillos se ven como rombos solo en experto. Se toca con
samples ADPCM-A.

### Reglas

Son las de NESBand:

- Fácil usa 3 carriles, medio 4, difícil y experto los 5. A más dificultad, las notas bajan más rápido
  (6, 5, 4 y 3 cuadros por cada 8 píxeles).
- Tolerancia de ±6 cuadros (~100 ms). Presionar un carril sin nota cerca rompe el combo y calla tu instrumento.
- Cada nota vale 50 por el multiplicador (x1, x2 desde 10 de combo, x3 desde 20, x4 desde 30). Cada botón de un
  acorde cuenta como una nota.
- **Notas sostenidas:** acierta la gema y mantén el botón mientras pasa la cola: 10 puntos cada 8 cuadros.
- **Poder estelar:** las gemas en forma de diamante son frases de 4 notas; si las aciertas todas, la barra sube
  25%. Con la mitad o más, **A** lo activa: todo vale el doble.
- **Vida:** cada acierto sube 1; perder una nota baja 2 (1 en fácil) y un golpe al aire 1. Si llega a 0, pierdes.
  **SIN FALLO** quita el medidor.
- **Estrellas:** salen del puntaje (sin el poder estelar ni las colas) contra el puntaje perfecto: 20, 40, 60, 80 y
  95%.

**Escenario:** alrededor de la autopista hay un escenario de concierto con luces y público que reacciona al combo,
al poder estelar y a las frases estelares, como en las otras versiones.

**Récords:** el juego guarda el mejor puntaje de cada **canción, instrumento y dificultad**, con tus iniciales y
estrellas. Viven en la **memoria de respaldo** (backup RAM del MVS / tarjeta de memoria del AES). Cada canción se
identifica por un hash de su título y su juego, no por su lugar en el menú. Si la memoria falta o está dañada, el
juego arranca con la tabla vacía y sigue funcionando.

## Importar canciones

La música se importa de **VGM** (`.vgm`, o `.vgz` si está comprimido) con comandos del YM2610: son las escrituras
a los registros del chip tal como las hizo el juego. Hay colecciones en [vgmrips.net](https://vgmrips.net/). Pon los
tuyos en `songs_src/` (está en `.gitignore`: la música de juegos comerciales tiene copyright y no se sube a git).

```bash
uv run ngband channels "songs_src/Juego/01 Tema.vgz"
```

Muestra las notas de cada canal. Después importa:

```bash
uv run ngband import-song "songs_src/Juego/01 Tema.vgz" --name tema --duration 90
```

Deja `src/songs/<nombre>/song.c` (la música, los 12 charts y la ficha de la canción) e `import.json` (las
opciones). `./build.sh` incluye todas las canciones que haya en `src/songs/`, en orden alfabético.
`uv run ngband reimport` las vuelve a importar con las mismas opciones y `uv run ngband list-songs` las lista.
Ejecuta `uv run ngband import-song --help` para ver todas las opciones (canales por instrumento, batería, tempo).

Los charts se generan con el mismo generador de NESBand (`chart.py` y `drums.py`). Los samples de la batería se
convierten a ADPCM-A con `uv run ngband adpcm`.

### Editor de charts

```bash
uv run ngband edit-chart            # abre en blanco: eliges la canción desde el menú
uv run ngband edit-chart tormenta   # o directo una canción
```

Es el editor de las otras versiones, con los canales del YM2610: una página local en el navegador (el servidor solo
escucha en `127.0.0.1`; `--port` cambia el puerto y `--no-browser` no abre el navegador). Guardar escribe solo la
diferencia con el chart automático en `src/songs/<nombre>/edits.json`, que sobrevive a `reimport`. **Escuchar**
toca la canción con `ngplayer.js`, un emulador del YM2610 en JavaScript.

## Canciones originales

Las diez canciones son las de NESBand, convertidas a parches FM del YM2610 (GPL-2.0-or-later): *Primer Ensayo*
(`demo`), *Tormenta de Neón*, *Luz de Luna*, *Salto Mortal*, *Marcha del Cartucho*, *Noche sin Estrellas*,
*Carrera de Fuego*, *Brisa de Verano*, *Cumbia del Cartucho* y *Amanecer Digital*. Se componen en Python en
`audio/` (`audio/<nombre>.py` genera el `.vgm`), y los efectos de sonido están en `audio/efectos.txt`.

## Pruebas

```bash
uv run pytest
```

Prueba, en el host, el lector y escritor de VGM, el generador de charts, las notas, el editor, el reproductor
de JavaScript y la lógica pura del juego en C (la misma fuente que va en la ROM, compilada para el host), con
pruebas de propiedades (Hypothesis). **Esto es lo que pasa hoy.**

```bash
tests/run_tests.sh
```

Compila y juega cada caso en MAME, sin ventana y a toda velocidad (con `NGBAND_MAME_WINDOW=1` se ve la ventana,
sin quitarle el foco a lo que estés usando), con un bot (`tests/autoplay.lua`) que lee las
notas de la RAM, toca y anota los resultados (juego perfecto, sin tocar, machacar, humano; 2 jugadores; pausa;
opciones; récords; audio; cuadros perdidos). `tests/run_tests.sh 'demo-*'` corre solo los casos que coinciden;
`--no-build` usa la ROM que ya está. **Ya corre, pero los casos todavía fallan** (el bot pierde notas y se
pierden cuadros; ver `docs/ESTADO.md`).

## Cómo está hecho

- **C con ngdevkit** para el 68000 y **SDCC** para el Z80, compilados con `build.sh`. Los gráficos no son
  imágenes: se generan en Python al compilar (`uv run ngband gfx`), así que la ROM los trae ya en tiles.
- **La autopista en perspectiva:** la Neo Geo no tiene planos de fondo ni interrupciones por línea como la Genesis,
  así que todo son sprites. La pista (superficie, carriles, bordes y aros) es un trapecio fijo de 14 columnas de
  sprites que se escribe una vez por canción; sus franjas bajan solas con la autoanimación del LSPC (8 fases de
  tiles), sin trabajo del 68000. Las gemas y las colas se reducen con los registros de escala de cada sprite. Los
  textos y el HUD van en la capa fija (Fix).
- **El audio:** un driver propio en el Z80 (`src/z80/`) aplica al YM2610 el flujo de escrituras por cuadro
  (FM, SSG y la batería en ADPCM-A); el 68000 le manda órdenes (`src/audio_proto.h`). Para fallar, baja el volumen
  del canal del instrumento y lo restaura al acertar.
- **La lógica pura** (juez, vida, poder estelar, menús, opciones, práctica, récords) no depende del hardware y se
  prueba en el host con la misma fuente que va en la ROM.

## Hoja de ruta

1. ~~Compilar la ROM~~ (hecho) y ~~meter las 10 canciones con su música~~ (hecho: bancos y streams comprimidos).
2. **Que pasen los casos de `tests/run_tests.sh`** (notas que pierde el bot, cuadros perdidos, sincronía del audio).
3. Probar en hardware (MVS/AES, MiSTer o flash cart), sobre todo el driver del Z80 y la memoria de respaldo.
4. Release publicada (subir `VERSION`).
5. Pendientes comunes a la familia: ver `../NESBand/docs/paridad.md` (columna NG; es la única fuente).

## Licencia

GPL-2.0-or-later (ver `LICENSE`).

- **La fuente de las letras** es la de NESBand: *Bongo-8 Mono* de Caffinate (Nathan Scott), de dominio público
  (CC0 1.0).
- ngdevkit, SDCC y MAME tienen sus propias licencias y no se incluyen en el repositorio. La BIOS de la Neo Geo
  tampoco.
