# Requirements Document

## Introduction

NGBand es la versión para la SNK Neo Geo (MVS/AES) de la familia de juegos de ritmo estilo Guitar Hero / Rock Band formada por NESBand (referencia de reglas), GBBand y GENBand. Este documento define el alcance del port. NESBand es la base del juego (reglas, charts, menús, récords, opciones, escenario). De GENBand se toman la autopista en perspectiva, el importador de VGM y el editor de charts con Escuchar. La Neo Geo escala sprites por hardware, así que la perspectiva se logra con sprites reducidos y no con interrupciones por línea como en la Genesis.

Los charts se generan con el generador compartido (`chart.py`, `drums.py`) y el audio de la Neo Geo (YM2610: 4 canales FM, 3 SSG, ADPCM-A de 6 canales y ADPCM-B de 1 canal, controlado por un Z80) se alimenta de archivos VGM.

### Supuestos (por confirmar)

- **S1. Formato de entrega:** cartucho MVS/AES (ROM `.neo` o juego MAME), no Neo Geo CD. El CD queda fuera de alcance.
- **S2. Toolchain:** `ngdevkit` (GCC para m68k, SDCC para el Z80, herramientas de gráficos y sonido), con Python/`uv` para las herramientas de PC como en GENBand. El emulador de juego es MAME (con Lua para las pruebas automáticas) y opcionalmente GnGeo.
- **S3. Lenguaje:** C para el 68000, igual que GENBand. Ensamblador solo donde el rendimiento lo exija.
- **S4. Audio:** un driver Z80 propio o el de `ngdevkit` reproduce un flujo de escrituras de registros del YM2610 por cuadro, análogo al flujo de GENBand. Las canciones se importan de VGM del YM2610 y las 10 originales se convierten desde los proyectos de NESBand a patches FM del YM2610.
- **S5. Controles:** la Neo Geo tiene palanca de 4 direcciones y 4 botones (A, B, C, D) más Start y Select. Mapa propuesto: verde ←, rojo ↓, amarillo →, azul B, naranja C, poder estelar A y pausa Start. Es el mismo mapa de 3 botones de GENBand.
- **S6. Región y tiempo:** NTSC, un paso del juego por cuadro de video (~59.19 Hz de la Neo Geo; se usa como "60 Hz" en las reglas). PAL no se soporta.
- **S7. Guardado:** los récords van en la memoria de respaldo (backup RAM del MVS / tarjeta de memoria del AES).
- **S8. Base de código:** el port parte de la columna NES de `NESBand/docs/paridad.md`, y NGBand agrega su propia columna.
- **S9. Licencia:** GPL-2.0-or-later, como las demás versiones.

### Preguntas abiertas

- **P1.** ¿Se confirma ROM de cartucho (S1) y `ngdevkit` (S2)?
- **P2.** ¿Qué ocurre con la batería: ADPCM-A (6 canales de samples, más natural en la Neo Geo) o parches FM/SSG como en GB? Se asume ADPCM-A.
- **P3.** ¿Cuántos jugadores en la primera versión: solo 1 jugador, o también 2 (VS y Co-Op)? La Neo Geo tiene 2 puertos de control. Se asume 1 y 2 jugadores, con 2P en una fase posterior.
- **P4.** ¿Las canciones comerciales importadas se quedan fuera del repositorio, como en GENBand (`songs_src/` en `.gitignore`)? Se asume que sí.
- **P5.** ¿Los gráficos se generan por código al arrancar (como GENBand) o se precompilan con herramientas de PC en la compilación? Se asume precompilarlos, para evitar el arranque lento de GENBand.

## Glossary

- **NGBand**: El juego de ritmo para Neo Geo que define este documento.
- **ROM**: El archivo de cartucho de NGBand que se ejecuta en la Neo Geo o en un emulador.
- **Highway**: La autopista de 5 carriles por la que bajan las notas.
- **Perspective_Highway**: El Highway dibujado como trapecio, con sprites escalados por hardware.
- **Sprite_Scaler**: El mecanismo de la Neo Geo que reduce sprites en horizontal (16 niveles) y en vertical (256 niveles) mediante los registros de escala de cada sprite.
- **Fix_Layer**: La capa fija de la Neo Geo de tiles de 8x8, usada para HUD y textos.
- **Note**: Una gema que el jugador debe tocar en un carril en el momento indicado por el Chart.
- **Lane**: Uno de los 5 carriles del Highway (verde, rojo, amarillo, azul, naranja).
- **Chart**: La secuencia de pares (cuadros desde la nota anterior, carriles) de un instrumento y dificultad, en el formato de NESBand.
- **Chart_Generator**: Las herramientas de PC (`chart.py`, `drums.py`) que crean los Charts a partir de las notas de una canción.
- **Instrument**: Guitarra, teclado, bajo o batería.
- **Difficulty**: Fácil (3 carriles), medio (4), difícil (5) o experto (5).
- **Judge**: El módulo que compara las pulsaciones con las Notes.
- **Hit_Window**: La tolerancia de ±6 cuadros alrededor de una Note.
- **Combo**: El número de aciertos consecutivos.
- **Multiplier**: El factor de puntaje (x1, x2 desde 10 de Combo, x3 desde 20, x4 desde 30).
- **Star_Power**: El modo de puntaje doble que se activa con una barra de al menos la mitad.
- **Life_Meter**: El medidor de vida del jugador.
- **Sustain**: Una cola de Note que se mantiene con el botón presionado.
- **Song**: Una canción con su audio y sus 12 Charts (3 instrumentos melódicos por 4 dificultades, más batería).
- **VGM**: El formato de archivo de registros de chips de sonido (`.vgm`, `.vgz`), aquí con comandos del YM2610.
- **YM2610**: El chip de sonido de la Neo Geo.
- **Audio_Driver**: El programa del Z80 que aplica al YM2610 el flujo de escrituras por cuadro.
- **Frame_Stream**: El flujo de escrituras de registros agrupadas por cuadro de video, sin las que repiten el valor.
- **ADPCM_A**: Los 6 canales de samples del YM2610 usados para la batería.
- **Song_Importer**: La herramienta de PC (`ngband import-song`) que convierte un VGM en los datos de una Song.
- **Chart_Editor**: El editor de charts en el navegador, con la función Escuchar.
- **Menu**: La pantalla donde se eligen canción, instrumento, dificultad, fallo y jugadores.
- **Options_Screen**: La pantalla de modificadores (espejo, velocidad, caída de notas, práctica, efecto al fallar).
- **Practice_Mode**: El modo que repite un tramo de la canción sin fallo y sin resultados.
- **Records_Store**: El módulo que guarda y lee los récords en la memoria de respaldo.
- **Stage**: El escenario de concierto (bocinas, torres con foco, haces de luz y público) alrededor del Highway.
- **Build_System**: El script `build.sh` que compila la ROM y las herramientas de PC.
- **Test_Harness**: Las pruebas automáticas (`tests/run_tests.sh` con MAME y Lua, y `pytest`).
- **Parity_Document**: El archivo `NESBand/docs/paridad.md` que compara las versiones.
- **Bot**: El jugador automático de las pruebas (perfecto, nada, machacar, humano).

## Requirements

### Requirement 1: Estructura del proyecto y compilación

**User Story:** As a developer, I want a reproducible build of the Neo Geo ROM, so that I can compile and run NGBand on any machine with the toolchain.

#### Acceptance Criteria

1. THE Build_System SHALL compile el código C del 68000, el Audio_Driver del Z80 y los datos de gráficos y audio en una ROM ejecutable en MAME.
2. THE Build_System SHALL escribir `build/ngband.*` (la ROM) y `build/ngband.sym` (los símbolos que usan las pruebas).
3. WHEN el desarrollador ejecuta `./build.sh --release`, THE Build_System SHALL producir `build/release/ngband-v<versión>.*` con su archivo `.sha256` y la licencia.
4. IF existen cambios sin commit en `src/` o `audio/` durante `./build.sh --release`, THEN THE Build_System SHALL negarse a producir la release e informar el motivo.
5. WHEN se compila dos veces con las mismas herramientas y el mismo commit, THE Build_System SHALL producir archivos de ROM idénticos.
6. THE Build_System SHALL leer la versión del archivo `VERSION` y la ROM SHALL mostrarla en la pantalla de título.
7. THE Build_System SHALL excluir de una release las canciones importadas de juegos comerciales.
8. THE Build_System SHALL incluir en la ROM todas las canciones de `src/songs/` en orden alfabético.
9. THE Build_System SHALL generar los gráficos del juego durante la compilación y no durante el arranque de la ROM.

### Requirement 2: Reglas del núcleo del juego

**User Story:** As a player, I want the same rules as NESBand, so that a song plays the same on every version of the family.

#### Acceptance Criteria

1. THE Judge SHALL usar 3 carriles en fácil, 4 en medio y 5 en difícil y experto.
2. THE Judge SHALL aceptar una pulsación como acierto cuando cae dentro de la Hit_Window de una Note del mismo Lane.
3. WHEN una Note se acierta, THE Judge SHALL sumar 50 puntos multiplicados por el Multiplier vigente.
4. THE Judge SHALL contar cada botón de un acorde como una Note.
5. WHEN el Combo llega a 10, 20 y 30, THE Judge SHALL subir el Multiplier a x2, x3 y x4.
6. IF el jugador presiona un Lane sin una Note dentro de la Hit_Window, THEN THE Judge SHALL romper el Combo y silenciar el Instrument del jugador hasta su siguiente acierto.
7. IF una Note sale de la Hit_Window sin acertarse, THEN THE Judge SHALL romper el Combo y silenciar el Instrument del jugador.
8. WHEN el jugador acierta una Note con Sustain y mantiene el botón, THE Judge SHALL sumar 10 puntos cada 8 cuadros mientras pasa la cola.
9. THE Judge SHALL calcular las estrellas como el porcentaje del puntaje (sin Star_Power ni Sustain) contra el puntaje perfecto, con umbrales de 20, 40, 60, 80 y 95 por ciento.
10. THE NGBand SHALL avanzar la canción y las Notes un paso por cuadro de video.
11. FOR ALL Charts generados, THE Chart_Generator SHALL evitar pedir verde y amarillo a la vez, para que `check_playable` pase.

### Requirement 3: Vida, Star Power y pausa

**User Story:** As a player, I want life, star power and pause, so that the game has the same challenge and flow as NESBand.

#### Acceptance Criteria

1. WHEN el jugador acierta una Note, THE Life_Meter SHALL subir 1.
2. WHEN el jugador pierde una Note, THE Life_Meter SHALL bajar 2 (1 en fácil).
3. WHEN el jugador golpea al aire, THE Life_Meter SHALL bajar 1.
4. IF el Life_Meter llega a 0, THEN THE NGBand SHALL terminar la partida del jugador, silenciar su Instrument y mostrar FALLASTE.
5. WHERE SIN FALLO está activo, THE NGBand SHALL ocultar el Life_Meter y no terminar la partida por vida.
6. WHEN el jugador acierta las 4 Notes de una frase estelar, THE NGBand SHALL subir la barra de Star_Power 25%.
7. WHEN el jugador presiona el botón de poder estelar con la barra en la mitad o más, THE NGBand SHALL activar Star_Power, duplicar el puntaje y teñir el Highway de azul.
8. WHEN el jugador presiona Start durante la partida, THE NGBand SHALL pausar la canción y la música sin perder la sincronía.
9. WHILE el juego está en pausa, WHEN el jugador presiona Start, THE NGBand SHALL reanudar con la música y las Notes sincronizadas.
10. WHILE el juego está en pausa, WHEN el jugador presiona B, THE NGBand SHALL regresar al Menu.

### Requirement 4: Instrumentos y batería

**User Story:** As a player, I want guitar, keyboard, bass and drums, so that I can play any part of a song.

#### Acceptance Criteria

1. THE NGBand SHALL ofrecer guitarra, teclado, bajo y batería como Instruments.
2. THE Highway de la batería SHALL mostrar 4 columnas (rojo, amarillo, azul, verde) y el bombo como una barra naranja que cruza el Highway.
3. WHEN el jugador presiona C en la batería, THE Judge SHALL evaluar la pulsación como bombo.
4. WHERE la Difficulty es experto, THE Highway SHALL dibujar los platillos como rombos.
5. WHERE la Difficulty no es experto, THE Highway SHALL dibujar los platillos como toms.
6. THE Chart_Generator SHALL limitar los acordes de batería a 3 botones simultáneos en difícil y experto, a 2 en medio y a bombo, tarola y tom 1 en fácil.

### Requirement 5: Autopista en perspectiva con escalado de sprites

**User Story:** As a player, I want the highway drawn in perspective, so that notes appear to come toward me like in GENBand.

#### Acceptance Criteria

1. THE Perspective_Highway SHALL dibujarse como un trapecio más angosto en el horizonte y más ancho cerca de la línea de golpe.
2. WHILE una Note baja por el Highway, THE Sprite_Scaler SHALL reducir la gema en horizontal y en vertical en proporción a su distancia a la línea de golpe.
3. THE Perspective_Highway SHALL usar al menos 7 niveles de tamaño de gema entre el horizonte y la línea de golpe.
4. WHILE una Note con Sustain baja por el Highway, THE Perspective_Highway SHALL ajustar el ancho y el largo de su cola a la perspectiva con sprites escalados.
5. THE Perspective_Highway SHALL dibujar las líneas de tiempo con sprites escalados, sin usar interrupciones por línea.
6. THE Perspective_Highway SHALL mantener en pantalla como máximo 96 sprites por línea de barrido.
7. THE NGBand SHALL actualizar los sprites del Highway durante el blanqueo vertical, sin que se vean desgarros en pantalla.
8. WHEN la Difficulty cambia, THE Perspective_Highway SHALL cambiar la velocidad de caída a 6, 5, 4 y 3 cuadros por cada 8 píxeles de recorrido en fácil, medio, difícil y experto.
9. THE NGBand SHALL dibujar el HUD (puntaje, Combo, Multiplier, medidor, textos) en la Fix_Layer.
10. WHERE el modo es de 2 jugadores, THE NGBand SHALL dibujar dos Perspective_Highways, uno en cada mitad de la pantalla.

### Requirement 6: Controles

**User Story:** As a player, I want to play with the Neo Geo stick and four buttons, so that the game feels native to the console.

#### Acceptance Criteria

1. THE NGBand SHALL mapear verde a ←, rojo a ↓, amarillo a →, azul a B, naranja a C, poder estelar a A y pausa a Start.
2. WHEN el jugador presiona izquierda y derecha a la vez, THE NGBand SHALL ignorar la combinación en los carriles verde y amarillo.
3. WHILE el Menu está activo, THE NGBand SHALL usar ↑/↓ para elegir el renglón, ←/→ para cambiar el valor, Start para jugar, A para abrir las opciones y B para regresar al título.
4. WHERE el modo es de 2 jugadores, THE NGBand SHALL leer el jugador 2 del segundo puerto de control.
5. THE NGBand SHALL leer los controles una vez por cuadro de video.

### Requirement 7: Menús, título y resultados

**User Story:** As a player, I want title, menu and results screens, so that I can choose a song and see how I did.

#### Acceptance Criteria

1. WHEN la ROM arranca, THE NGBand SHALL mostrar el título con la música del título (`audio/titulo.txt`) en bucle.
2. THE Menu SHALL permitir elegir canción, instrumento, dificultad, fallo y número de jugadores.
3. WHILE el Menu está activo, THE NGBand SHALL reproducir la canción elegida.
4. THE Menu SHALL mostrar el récord de la canción, el instrumento y la dificultad elegidos (puntaje, iniciales y estrellas) o `---` si no existe.
5. WHEN termina una canción, THE NGBand SHALL mostrar los resultados con la precisión, el combo máximo y las estrellas.
6. WHEN el jugador supera un récord, THE NGBand SHALL mostrar NUEVO RECORD y pedir tres iniciales con ↑/↓ para cambiar la letra, ←/→ para cambiar de letra y Start para guardar.
7. THE NGBand SHALL dibujar los textos con la fuente *Bongo-8 Mono* (CC0) de NESBand.
8. THE NGBand SHALL mostrar los textos en español.

### Requirement 8: Opciones y modo práctica

**User Story:** As a player, I want modifiers and a practice mode, so that I can learn hard parts of a song.

#### Acceptance Criteria

1. THE Options_Screen SHALL ofrecer ESPEJO, VELOCIDAD, CAIDA DE NOTAS, PRACTICA, INICIO DE LA PRACTICA y EFECTO AL FALLAR.
2. WHERE ESPEJO está activo, THE NGBand SHALL invertir los carriles al leer el Chart (verde con naranja, rojo con azul) y dejar la batería sin cambios.
3. WHERE VELOCIDAD es 100%, 75%, 50% o 125%, THE NGBand SHALL avanzar la canción, las Notes y la música 4, 3, 2 o 5 pasos cada 4 cuadros.
4. WHERE CAIDA DE NOTAS no es AUTO, THE Perspective_Highway SHALL usar la velocidad de caída elegida, de la de fácil a la de experto, sin importar la Difficulty.
5. WHERE PRACTICA está activa, THE Practice_Mode SHALL repetir la canción hasta 1/4, 1/2, 3/4 o el final, sin fallo y sin resultados.
6. WHERE INICIO DE LA PRACTICA se elige (principio, 1/4, 1/2 o 3/4), THE Practice_Mode SHALL adelantar la música hasta ese punto y omitir las Notes de los primeros segundos.
7. WHILE el juego está en pausa en Practice_Mode, WHEN el jugador presiona A, THE Practice_Mode SHALL iniciar el bucle 2 segundos antes del punto de la pausa.
8. WHILE el juego está en pausa en Practice_Mode, WHEN el jugador presiona B, THE Practice_Mode SHALL terminar el bucle en el punto de la pausa.
9. IF la marca de bucle dejaría un bucle de menos de 4 segundos, THEN THE Practice_Mode SHALL rechazar la marca.
10. WHILE el juego está en pausa en Practice_Mode, WHEN el jugador presiona C, THE NGBand SHALL regresar al Menu.
11. WHERE EFECTO AL FALLAR es SI, SOLO SONIDO o NO, THE NGBand SHALL aplicar el temblor, el rojo y el sonido de acuerdo con el valor elegido.
12. WHEN el jugador golpea al aire, THE NGBand SHALL reproducir uno de tres efectos distintos del anterior y limitarlos a 3 por segundo en una racha de fallos.

### Requirement 9: Récords en memoria de respaldo

**User Story:** As a player, I want my best scores saved, so that I can see them after turning the console off.

#### Acceptance Criteria

1. THE Records_Store SHALL guardar el mejor puntaje de cada combinación de canción, instrumento y dificultad en la memoria de respaldo.
2. THE Records_Store SHALL identificar cada canción con un hash de su título y su juego, y no con su posición en el Menu.
3. THE Records_Store SHALL guardar una firma y una suma de comprobación junto con la tabla.
4. IF la firma o la suma de comprobación no coincide al arrancar, THEN THE Records_Store SHALL iniciar con la tabla vacía.
5. IF el jugador perdió, jugó SIN FALLO o usó una opción distinta de la normal (salvo EFECTO AL FALLAR), THEN THE Records_Store SHALL omitir el guardado del récord.
6. WHEN se guarda un récord y se reinicia la consola, THE Records_Store SHALL devolver el mismo puntaje, iniciales y estrellas.
7. FOR ALL tablas de récords válidas, escribir la tabla y leerla SHALL producir una tabla equivalente (round-trip).

### Requirement 10: Dos jugadores (VS y Co-Op)

**User Story:** As a player, I want to play with a friend on the same console, so that we can compete or play as a band.

#### Acceptance Criteria

1. WHERE el modo es 2 JUGADORES VS, THE NGBand SHALL usar la misma Difficulty para los dos jugadores y evaluar el puntaje, el Combo y la vida de cada jugador por separado.
2. WHERE el modo es VS, THE NGBand SHALL mostrar al final `GANA J1 POR n`, `GANA J2 POR n` o `EMPATE`.
3. IF un jugador pierde en VS, THEN THE NGBand SHALL terminar la partida, declarar ganador al otro y omitir el guardado del récord.
4. WHERE el modo es 2 JUGADORES COOP, THE NGBand SHALL compartir el puntaje, el Combo y el Star_Power de la banda, y llevar la vida de cada jugador por separado.
5. WHERE el modo es COOP, WHILE un jugador está caído, WHEN el otro presiona el botón de poder estelar con media barra, THE NGBand SHALL revivir al caído y gastar media barra.
6. IF los dos jugadores caen en COOP, THEN THE NGBand SHALL terminar la partida.
7. WHERE el modo es COOP, THE NGBand SHALL impedir que los dos jugadores elijan el mismo Instrument.
8. WHERE el modo es COOP, THE Records_Store SHALL guardar el récord de banda por canción y por la mayor Difficulty de los dos, solo cuando los dos terminan en pie.

### Requirement 11: Escenario

**User Story:** As a player, I want a concert stage that reacts to my playing, so that the game feels alive.

#### Acceptance Criteria

1. THE Stage SHALL dibujar bocinas, torres con foco, haces de luz y público alrededor del Highway.
2. WHILE el Combo es menor que 10, THE Stage SHALL mantener quieto al público.
3. WHILE el Combo es 10 o más, THE Stage SHALL levantar los brazos del público y saltarlo al inicio de cada tiempo de la canción.
4. WHILE el Combo es 10 o más, THE Stage SHALL hacer latir las luces con cada tiempo.
5. WHILE Star_Power está activo, THE Stage SHALL cambiar el color de las luces en cada tiempo entre cian, rojo, amarillo y violeta.
6. WHEN el jugador completa una frase estelar, THE Stage SHALL dibujar un rayo sobre el carril de la última Note y destellar las luces.
7. IF todos los jugadores han perdido, THEN THE Stage SHALL apagar las luces.
8. WHERE el modo es de 2 jugadores, THE Stage SHALL dibujar una torre con dos focos entre los dos Highways.

### Requirement 12: Audio YM2610 y Audio_Driver

**User Story:** As a player, I want the music to play on the real Neo Geo sound chip and go quiet when I miss, so that the game sounds like the other versions.

#### Acceptance Criteria

1. THE Audio_Driver SHALL aplicar al YM2610 las escrituras del Frame_Stream una vez por cuadro de video.
2. THE NGBand SHALL sincronizar el Z80 con el 68000 mediante los registros de comando y respuesta de la Neo Geo, de modo que cada cuadro del Frame_Stream corresponda al mismo cuadro del juego.
3. WHEN el jugador falla, THE Audio_Driver SHALL poner al mínimo el volumen de los operadores portadores del canal FM del Instrument (o la atenuación del SSG) y recordar el valor que pide la canción.
4. WHEN el jugador acierta tras un fallo, THE Audio_Driver SHALL restaurar el volumen que pide la canción en el mismo cuadro.
5. THE Audio_Driver SHALL reproducir los efectos de menú (mover, aceptar, volver) y los tres efectos de fallo de `audio/nesband/efectos.txt`.
6. WHILE suena un efecto, THE Audio_Driver SHALL guardar lo que la canción pide al canal usado por el efecto y restaurarlo al terminar.
7. WHEN el juego se pausa, THE Audio_Driver SHALL detener la música y, al reanudar, continuar desde el mismo cuadro.
8. WHERE VELOCIDAD no es 100%, THE Audio_Driver SHALL detener el avance del Frame_Stream en los cuadros sin paso.
9. WHEN una canción empieza, THE Audio_Driver SHALL silenciar todos los canales del YM2610 y dejar los registros en su estado inicial.

### Requirement 13: Batería con samples ADPCM-A

**User Story:** As a player, I want drums that play real samples, so that imported songs keep their drum sound.

#### Acceptance Criteria

1. THE Audio_Driver SHALL reproducir los golpes de batería con los canales de ADPCM_A del YM2610.
2. THE Song_Importer SHALL convertir cada golpe de batería sampleado de un VGM en un sample ADPCM-A de la ROM de samples y en un evento "toca el sample n" del Frame_Stream.
3. THE Song_Importer SHALL escribir un `drums.json` con el papel de cada grupo de golpes (bombo, tarola, tom 1 a 3, platillo) cuando no exista, y conservarlo en `reimport`.
4. WHEN el jugador falla en la batería, THE Audio_Driver SHALL silenciar los canales ADPCM_A de la batería hasta el siguiente acierto.
5. IF un VGM trae el stream de ADPCM-A o ADPCM-B en un formato que el Song_Importer no entiende, THEN THE Song_Importer SHALL informar el comando no soportado y continuar con los demás canales.

### Requirement 14: Importación de canciones VGM

**User Story:** As a developer, I want to import YM2610 VGM files, so that I can add songs from other Neo Geo games.

#### Acceptance Criteria

1. WHEN el desarrollador ejecuta `ngband channels <archivo>`, THE Song_Importer SHALL mostrar las notas y la altura de cada canal (`fm1` a `fm4`, `ssg1` a `ssg3`, `adpcma`, `adpcmb`) y sugerir guitarra, teclado y bajo.
2. WHEN el desarrollador ejecuta `ngband import-song <archivo> --name <n>`, THE Song_Importer SHALL escribir `src/songs/<n>/song.c` con el Frame_Stream, los 12 Charts y la ficha de la canción, junto con `import.json`.
3. THE Song_Importer SHALL aceptar `.vgm` y `.vgz`.
4. THE Song_Importer SHALL aceptar las opciones `--title`, `--game`, `--duration`, `--guitarra`, `--teclado`, `--bajo`, `--bateria` y `--beat-frames`.
5. WHEN el VGM tiene bucle y se pide `--duration S`, THE Song_Importer SHALL repetir el bucle hasta S segundos.
6. THE Song_Importer SHALL deducir las notas FM de cada key-on y de la altura por bloque y F-number, y tratar un cambio de más de 3/4 de semitono con la tecla presionada como otra nota.
7. THE Song_Importer SHALL generar los Charts con el Chart_Generator compartido y aplicar después las ediciones de `edits.json`.
8. WHEN el desarrollador ejecuta `ngband reimport`, THE Song_Importer SHALL volver a importar todas las canciones con las opciones de su `import.json`.
9. WHEN el desarrollador ejecuta `ngband list-songs`, THE Song_Importer SHALL listar las canciones de `src/songs/`.
10. IF el archivo no es un VGM válido o no trae comandos del YM2610, THEN THE Song_Importer SHALL devolver un error descriptivo y no escribir archivos.
11. THE Song_Importer SHALL registrar `songs_src/` en `.gitignore`.
12. FOR ALL Frame_Streams generados, serializar el flujo a `song.c` y leerlo con el reproductor de prueba SHALL producir las mismas escrituras de registros por cuadro (round-trip).
13. FOR ALL Charts generados, serializar el Chart y leerlo SHALL producir los mismos pares (cuadros, carriles) (round-trip).

### Requirement 15: Canciones originales y de NESBand

**User Story:** As a player, I want the ten NESBand songs on the Neo Geo, so that the family shares its repertoire.

#### Acceptance Criteria

1. THE NGBand SHALL incluir las diez canciones originales de NESBand: *Primer Ensayo*, *Tormenta de Neón*, *Luz de Luna*, *Salto Mortal*, *Marcha del Cartucho*, *Noche sin Estrellas*, *Carrera de Fuego*, *Brisa de Verano*, *Cumbia del Cartucho* y *Amanecer Digital*.
2. THE herramientas de audio SHALL convertir los proyectos de FamiStudio de NESBand a VGM del YM2610, con pulso 1 en FM 1 (guitarra), pulso 2 en FM 2 (teclado), triángulo en FM 3 (bajo) y ruido y DPCM en la batería.
3. THE herramientas de audio SHALL asignar a cada instrumento de FamiStudio un patch FM del YM2610 según su nombre y traducir su volumen a atenuación.
4. WHERE se importa *Cumbia del Cartucho*, THE Song_Importer SHALL usar `--beat-frames 36`.
5. THE NGBand SHALL incluir la letra de licencia GPL-2.0-or-later para las canciones originales.

### Requirement 16: Editor de charts

**User Story:** As a chart author, I want a browser editor with playback, so that I can fix and tune generated charts.

#### Acceptance Criteria

1. WHEN el desarrollador ejecuta `ngband edit-chart [canción]`, THE Chart_Editor SHALL abrir una página local servida solo en `127.0.0.1`.
2. THE Chart_Editor SHALL mostrar los canales de la canción (FM 1-4, SSG 1-3, ADPCM-A y ADPCM-B) sobre una línea de tiempo con la rejilla de tiempos.
3. THE Chart_Editor SHALL permitir agregar, mover, borrar y marcar como acorde, cola o estelar las Notes de un Chart, y deshacer y rehacer los cambios.
4. WHEN el desarrollador guarda, THE Chart_Editor SHALL escribir solo la diferencia con el chart automático en `edits.json`.
5. IF una edición guardada ya no encuentra su Note tras un `reimport`, THEN THE Song_Importer SHALL avisar y omitir la edición.
6. WHEN el desarrollador presiona Escuchar, THE Chart_Editor SHALL tocar la canción con un emulador del YM2610 en JavaScript que reproduce el mismo Frame_Stream que la ROM.
7. THE Chart_Editor SHALL permitir silenciar (M) o dejar solo (S) cada canal durante Escuchar.
8. THE Chart_Editor SHALL mostrar en rojo las Notes que incumplan `check_playable`.
9. THE Chart_Editor SHALL permitir editar la tabla de papeles de la batería y rehacer al momento los Charts de batería.

### Requirement 17: Pruebas automáticas

**User Story:** As a developer, I want automated tests in an emulator, so that I can detect regressions in gameplay, audio and timing.

#### Acceptance Criteria

1. WHEN el desarrollador ejecuta `tests/run_tests.sh`, THE Test_Harness SHALL compilar la ROM y ejecutar cada caso en MAME sin ventana.
2. WHEN el Bot perfecto juega una canción, THE Test_Harness SHALL comprobar que el juego acierte todas las Notes con 5 estrellas.
3. WHEN el Bot nada no toca, THE Test_Harness SHALL comprobar que la partida se pierda.
4. WHEN el Bot machacar golpea al aire, THE Test_Harness SHALL comprobar que el Combo se rompa.
5. THE Test_Harness SHALL comprobar que cada alta de nota del audio coincide con la Note del Chart dentro de un cuadro, incluso después de pausar.
6. THE Test_Harness SHALL probar ESPEJO, las velocidades, Practice_Mode con sus marcas, SIN FALLO, la batería, los récords con sus iniciales y la persistencia tras reiniciar.
7. WHERE el modo es de 2 jugadores, THE Test_Harness SHALL probar el empate en VS, el ganador cuando el otro pierde y la continuidad de Co-Op cuando un jugador cae.
8. IF el juego pierde más de 2 cuadros en una prueba, THEN THE Test_Harness SHALL marcar la prueba como fallida.
9. WHEN una prueba termina, THE Test_Harness SHALL guardar capturas, audio (`audio.wav`) y registro en `build/test-<nombre>/`.
10. WHEN el desarrollador ejecuta `uv run pytest`, THE Test_Harness SHALL probar el lector de VGM, la extracción de notas, el Chart_Generator, el editor y la conversión de ADPCM-A.
11. THE Test_Harness SHALL aceptar un patrón de nombre de caso y la opción `--no-build`.
12. WHERE existe un Bot humano, THE Test_Harness SHALL comprobar que termina alrededor del 90% de las partidas y pierde alrededor del 45% en la dificultad más alta.

### Requirement 18: Rendimiento

**User Story:** As a player, I want a stable frame rate, so that the notes and music stay in sync.

#### Acceptance Criteria

1. WHILE una partida de 1 jugador está en curso, THE NGBand SHALL completar cada cuadro de lógica y de actualización de sprites dentro de un cuadro de video.
2. WHILE una partida de 2 jugadores está en curso, THE NGBand SHALL completar cada cuadro de lógica y de actualización de sprites dentro de un cuadro de video.
3. THE NGBand SHALL actualizar solo los sprites y los tiles de la Fix_Layer que cambiaron respecto del cuadro anterior.
4. THE NGBand SHALL cargar en la VRAM los gráficos del Highway antes de empezar la canción.

### Requirement 19: Documentación y paridad

**User Story:** As a maintainer, I want the docs to keep the family in sync, so that each version knows what it lacks.

#### Acceptance Criteria

1. THE NGBand SHALL incluir un `README.md` en español con instalación, compilación, controles, reglas, importación, editor, pruebas y hoja de ruta.
2. THE NGBand SHALL incluir un `CLAUDE.md` que pida actualizar `../NESBand/docs/paridad.md` al terminar cada mejora.
3. WHEN termina una mejora, THE mantenedor SHALL actualizar en el Parity_Document la fila y la columna NGBand y anotar en "Pendientes por versión" lo que falte en NES, GB y GEN.
4. THE NGBand SHALL incluir `LICENSE` (GPL-2.0-or-later) y un aviso de que es un proyecto de aficionados sin relación con SNK.
5. THE NGBand SHALL declarar en su README que su código lo escribió una IA, como las demás versiones.

### Requirement 20: Fases de entrega

**User Story:** As a maintainer, I want the port delivered in phases, so that each step produces something playable and testable.

#### Acceptance Criteria

1. WHEN termina la fase 1, THE NGBand SHALL arrancar en MAME, mostrar un Highway en perspectiva de 1 jugador y tocar una canción con sus notas, el puntaje y el Combo.
2. WHEN termina la fase 2, THE NGBand SHALL incluir vida, Star_Power, Sustain, pausa, resultados, estrellas y las cuatro Difficulties con los cuatro Instruments.
3. WHEN termina la fase 3, THE NGBand SHALL incluir título, Menu, Options_Screen, Practice_Mode y Records_Store.
4. WHEN termina la fase 4, THE NGBand SHALL incluir las diez canciones, los efectos de sonido, la batería con ADPCM-A, el Stage y el silencio al fallar.
5. WHEN termina la fase 5, THE NGBand SHALL incluir 2 jugadores (VS y Co-Op), el Chart_Editor y la release reproducible.
6. WHEN termina cada fase, THE Test_Harness SHALL pasar todas las pruebas de las fases terminadas.
