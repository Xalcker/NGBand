-- Bot de pruebas de NGBand para MAME (driver neogeo): pasa el título, elige en el menú como lo haría
-- un jugador (control 1), toca la canción leyendo las Notes de la RAM y, en los resultados, escribe
-- resultado.txt y capturas. Lo corre tests/run_tests.sh. Portado de GENBand/tests/autoplay.lua.
--
-- La RAM se lee por los símbolos de build/ngband.sym (salida de nm) y el contrato con la ROM está en
-- src/probe.h (g_probe), más g_cursor[2] (chart.h) y g_audio (audio_cmd.h).
--
-- Parámetros (variables de entorno):
--   NGBAND_SYM    símbolos de la ROM (build/ngband.sym)
--   NGBAND_OUT    carpeta donde van resultado.txt, bot.log y las capturas
--   NGBAND_SONG, NGBAND_INSTR, NGBAND_DIFF   lo que se elige en el menú (números desde 0; la canción es
--                 su lugar en build/gen/songs.txt)
--   NGBAND_PLAYERS   0 = 1 jugador, 1 = 2 jugadores VS, 2 = 2 jugadores Co-Op
--   NGBAND_INSTR2, NGBAND_DIFF2, NGBAND_MODE2   lo del jugador 2 (control 2)
--   NGBAND_OPTS   opciones, como "espejo=1 velocidad=1 practica=1 inicio=0" (valor = número de opción)
--   NGBAND_MODE   perfecto (acierta todo), nada (no toca: debe perder), machacar (acierta todo y además
--                 golpea al aire cada 2 s: el Combo se rompe; "aire" es sinónimo), mitad (falla una de
--                 cada dos), sinfallo (no toca, con SIN FALLO), practica / marcas (Practice_Mode),
--                 record (acierta y escribe las iniciales BOT), leer_record (no juega: lee el récord del
--                 menú, para ver que sobrevivió a apagar la consola), humano (R17.12: falla notas con
--                 rachas y toca con algo de desfase; ver HUMAN abajo), pausa (perfecto, y a mitad de la
--                 canción pausa unos 3 s y reanuda: el audio debe seguir alineado con el Chart, R17.5)
--   NGBAND_SEED   semilla del bot humano (por defecto 1; el jugador 2 usa la semilla + 1000)
--   NGBAND_HUMAN_MISS   si está definida, reemplaza la probabilidad base de falla del bot humano (0..1)
--   NGBAND_DRY    si está definida, no hay MAME: solo comprueba la configuración (lo usa el humo de la CI)
--   NGBAND_BOT_DEBUG  si está definida, bot.log anota las Notes tocadas que siguen abiertas 2 cuadros después
--                 (el juego no vio el toque)

local sym_path = os.getenv("NGBAND_SYM")
local out = os.getenv("NGBAND_OUT")
local want_song = tonumber(os.getenv("NGBAND_SONG") or "0")
local want_instr = tonumber(os.getenv("NGBAND_INSTR") or "0")
local want_diff = tonumber(os.getenv("NGBAND_DIFF") or "3")
local mode = os.getenv("NGBAND_MODE") or "perfecto"
if mode == "aire" then mode = "machacar" end
local seed = tonumber(os.getenv("NGBAND_SEED") or "1")
local human_miss = tonumber(os.getenv("NGBAND_HUMAN_MISS") or "")
local want_players = tonumber(os.getenv("NGBAND_PLAYERS") or "0")
local want_instr2 = tonumber(os.getenv("NGBAND_INSTR2") or "0")
local want_diff2 = tonumber(os.getenv("NGBAND_DIFF2") or "0")
local mode2 = os.getenv("NGBAND_MODE2") or "perfecto"
if mode2 == "aire" then mode2 = "machacar" end
local opts = {}
for k, v in (os.getenv("NGBAND_OPTS") or ""):gmatch("(%w+)=(%d+)") do opts[k] = tonumber(v) end
local OPTION_ORDER = { "espejo", "velocidad", "caida", "practica", "inicio", "efecto" } -- options.h

-- ---------------------------------------------------------------------------------------------
-- Contrato con la ROM (src/probe.h)
-- ---------------------------------------------------------------------------------------------
local SCREEN_TITLE, SCREEN_MENU, SCREEN_PLAY, SCREEN_RESULTS, SCREEN_OPTIONS, SCREEN_INITIALS = 1, 2, 3, 4, 5, 6
local ROW_SONG, ROW_INSTR, ROW_DIFF, ROW_FAIL, ROW_PLAYERS, ROW_COUNT = 0, 1, 2, 3, 4, 5
-- desplazamiento y tamaño en bytes de cada campo de TestProbe
local PROBE = {
    screen = { 0, 2 }, song_frame = { 2, 2 }, paused = { 4, 2 }, menu_row = { 6, 2 },
    vblank_count = { 8, 4 }, step_count = { 12, 4 },
    menu_song = { 16, 2 }, menu_instr = { 18, 2 }, menu_diff = { 20, 2 }, menu_nofail = { 22, 2 },
    menu_players = { 24, 2 }, menu_instr2 = { 26, 2 }, menu_diff2 = { 28, 2 },
    best_score = { 84, 4 },
}
local RESULT_BASE = { p1 = 32, p2 = 48, band = 64 }        -- ProbeResult: score u32, hit, total, max_combo, stars, failed, new_record
local PROBE_WINNER, PROBE_BEST_INI = 80, 88
-- ChartCursor (chart.h) en el 68000: alineación de 2 bytes, tamaño 214
local CURSOR_STRIDE, CURSOR_HEAD, CURSOR_COUNT, CURSOR_Q, CURSOR_QN, PENDING_SIZE = 214, 5, 6, 8, 24, 8
local PN_FRAME, PN_END, PN_MASK, PN_OPEN, PN_FLAGS = 0, 2, 4, 5, 6
local CHART_FLAG_SUSTAIN = 0x40
local AUDIO_DESYNC_OFFSET = 40                              -- AudioCmd.desync_count
-- AudioCmd (audio_cmd.h): q[16] u16 (comando << 8 | argumento), head u8 en 32, tail u8 en 33, expected u8 en 36
local AUDIO_Q, AUDIO_HEAD, AUDIO_TAIL, AUDIO_EXPECTED, AUDIO_QSIZE = 0, 32, 33, 36, 16
local CMD_FRAME, CMD_FRAME2 = 0x04, 0x0B                    -- audio_proto.h
local SONG_LEAD_IN = 128                                    -- game.h: cuadros de Highway antes de la música
local SYNC_TOLERANCE = 1                                    -- R17.5: dentro de un cuadro
local LATE_MAX = 2                                          -- cuadros que el bot puede tocar tarde (ver play_player)
-- Bot humano: por Difficulty (0 fácil .. 3 experto), probabilidad base de fallar una Note, probabilidad de
-- empezar una racha de distracción por Note, y probabilidad de fallar dentro de la racha (3 a 8 Notes).
-- Son cifras de partida para R17.12 (~90% de partidas terminadas, ~45% perdidas en experto); la
-- proporción real depende de cuántas Notes tenga la canción. tests/check_human.py avisa si se alejan.
local HUMAN = {
    [0] = { base = 0.10, lapse = 0.005, lapse_miss = 0.5 },
    [1] = { base = 0.18, lapse = 0.010, lapse_miss = 0.6 },
    [2] = { base = 0.24, lapse = 0.010, lapse_miss = 0.6 },
    [3] = { base = 0.29, lapse = 0.020, lapse_miss = 0.7 },
}
local MAX_LOST_FRAMES = 2                                   -- R17.8
local TIMEOUT = 60 * 60 * 8                                 -- cuadros: ninguna canción dura tanto

local sym = {}
for line in io.lines(sym_path) do
    local addr, _, name = line:match("^(%x+) (%a) (%S+)$")
    if addr then sym[name] = tonumber(addr, 16) & 0xFFFFFF end
end
for _, name in ipairs({ "g_probe", "g_cursor", "g_audio" }) do
    assert(sym[name], "falta el símbolo " .. name .. " en " .. sym_path)
end

if os.getenv("NGBAND_DRY") then return { sym = sym, probe = PROBE } end

-- ---------------------------------------------------------------------------------------------
-- Máquina y controles
-- ---------------------------------------------------------------------------------------------
local mem = manager.machine.devices[":maincpu"].spaces["program"]

-- Busca los campos por nombre en todos los puertos (el tag cambia entre el MVS con ctrl1/ctrl2 y el
-- AES con edge:joy). Neo Geo: botones 1..4 = A, B, C, D.
local by_name = {}
for _, port in pairs(manager.machine.ioport.ports) do
    for name, f in pairs(port.fields) do
        if by_name[name] == nil then by_name[name] = f end
    end
end
local function find(...)
    for _, n in ipairs({ ... }) do if by_name[n] then return by_name[n] end end
    local names = {}
    for n in pairs(by_name) do names[#names + 1] = n end
    table.sort(names)
    error("no hay un control llamado " .. (...) .. "; hay: " .. table.concat(names, ", "))
end
local function pad_fields(p, startname)
    local f = {
        up = find("P" .. p .. " Up"), down = find("P" .. p .. " Down"),
        left = find("P" .. p .. " Left"), right = find("P" .. p .. " Right"),
        a = find("P" .. p .. " A", "P" .. p .. " Button 1", "P" .. p .. " Button A"),
        b = find("P" .. p .. " B", "P" .. p .. " Button 2", "P" .. p .. " Button B"),
        c = find("P" .. p .. " C", "P" .. p .. " Button 3", "P" .. p .. " Button C"),
        start = find(startname, "P" .. p .. " Start"),
    }
    return f
end
local field = pad_fields(1, "1 Player Start")
local field2 = pad_fields(2, "2 Players Start")

-- Cada jugador: su modo, sus carriles (verde ←, rojo ↓, amarillo →, azul B, naranja C) y lo presionado
local bots = {
    { mode = mode, lane_field = { field.left, field.down, field.right, field.b, field.c }, release = {}, hold = {}, done = {} },
    { mode = mode2, lane_field = { field2.left, field2.down, field2.right, field2.b, field2.c }, release = {}, hold = {}, done = {} },
}

local function rd(name)
    local off, size = PROBE[name][1], PROBE[name][2]
    if size == 4 then return mem:read_u32(sym.g_probe + off) end
    return mem:read_u16(sym.g_probe + off)
end

local frame = 0
local log = io.open(out .. "/bot.log", "w")
local function note(text) log:write(string.format("%6d %s\n", frame, text)) log:flush() end

local function snapshot(name)
    manager.machine.video:snapshot()
    note("captura " .. name)
end

-- Cola de acciones del menú: un campo (tap), {until_, press}, {screen}, {shot}, {row}, {plan2}
local queue = {}
local function tap(f) table.insert(queue, f) end

local function menu_plan()
    -- Cada renglón: el cursor baja hasta él (↓ con vuelta) y el valor se cambia con → hasta el pedido
    local function row(r, getter, target)
        table.insert(queue, { until_ = function() return rd("menu_row") == r end, press = field.down })
        table.insert(queue, { until_ = function() return getter() == target end, press = field.right })
    end
    row(ROW_SONG, function() return rd("menu_song") end, want_song)
    row(ROW_PLAYERS, function() return rd("menu_players") end, want_players)
    row(ROW_INSTR, function() return rd("menu_instr") end, want_instr)
    row(ROW_DIFF, function() return rd("menu_diff") end, want_diff)
    row(ROW_FAIL, function() return rd("menu_nofail") end, (mode == "sinfallo") and 1 or 0)
    -- El jugador 2 elige con su control (cambiar el instrumento del 1 mueve el suyo, así que va al final)
    if want_players > 0 then table.insert(queue, { plan2 = true }) end
    if next(opts) then
        -- Opciones: A las abre; cada renglón empieza en su valor normal (0)
        tap(field.a)
        table.insert(queue, { screen = SCREEN_OPTIONS })
        for _, name in ipairs(OPTION_ORDER) do
            for _ = 1, (opts[name] or 0) do tap(field.right) end
            tap(field.down)
        end
        -- (como en GENBand, Start desde la Options_Screen empieza la partida con esas opciones)
    end
    tap(field.start)
end

local state = "titulo"
local wait = 0
local shots = {}
local missed_on_purpose, air_hits = 0, 0
local title_frames = 0
local loops, last_now, marked, restarted_after_mark, loop_end, loop_frame, leaving = 0, nil, nil, nil, nil, 0, false
local vb0, st0
local sync_max, sync_n, sync_bad = 0, 0, 0
local pause_stage, pause_count, pause_song, pause_drift, pause_resumed_song = 0, 0, 0, 0, 0

local function release_all()
    for _, f in pairs(field) do f:set_value(0) end
    for _, f in pairs(field2) do f:set_value(0) end
end

-- Las Notes por entrar a la Hit_Window del jugador i: cola circular de ChartCursor
local function pending(i)
    local base = sym.g_cursor + (i - 1) * CURSOR_STRIDE
    local head, count = mem:read_u8(base + CURSOR_HEAD), mem:read_u8(base + CURSOR_COUNT)
    local k = 0
    return function()
        if k >= count then return nil end
        local q = base + CURSOR_Q + ((head + k) % CURSOR_QN) * PENDING_SIZE
        k = k + 1
        return {
            frame = mem:read_u16(q + PN_FRAME), end_ = mem:read_u16(q + PN_END),
            mask = mem:read_u8(q + PN_MASK), open = mem:read_u8(q + PN_OPEN), flags = mem:read_u8(q + PN_FLAGS),
        }
    end
end

-- Generador pseudoaleatorio propio (LCG de 31 bits), para que cada semilla repita la misma partida
local rng_state = { seed % 2147483647 + 1, (seed + 1000) % 2147483647 + 1 }
local function rnd(i)
    rng_state[i] = (rng_state[i] * 1103515245 + 12345) % 2147483648
    return (rng_state[i] >> 8) / 8388608.0
end

-- Decisión del bot humano para una Note (se toma la primera vez que se ve y se recuerda): si la falla y con
-- cuántos cuadros de desfase la toca (-3..3)
local human_cache = {}
local human_lapse = { 0, 0 }
local function human_decide(i, n)
    local key = i .. ":" .. n.frame .. ":" .. n.mask
    local d = human_cache[key]
    if d then return d.miss, d.delay end
    local p = HUMAN[(i == 1) and want_diff or want_diff2] or HUMAN[3]
    local pmiss = human_miss or p.base
    if human_lapse[i] == 0 and rnd(i) < p.lapse then human_lapse[i] = 3 + math.floor(rnd(i) * 6) end
    if human_lapse[i] > 0 then
        pmiss = math.max(pmiss, p.lapse_miss)
        human_lapse[i] = human_lapse[i] - 1
    end
    d = { miss = rnd(i) < pmiss, delay = math.floor((rnd(i) + rnd(i) - 1) * 3 + 0.5) }
    human_cache[key] = d
    return d.miss, d.delay
end

-- ESPEJO (options.h): el juego invierte los botones físicos antes de juzgar, en las 3/4/5 columnas de la
-- Difficulty (la batería no se invierte). El bot toca el botón físico que acierta el carril de la Note.
local LANES_BY_DIFF = { [0] = 3, 4, 5, 5 }
local INST_DRUMS = 3
local function phys_lane(i, lane)
    if (opts.espejo or 0) == 0 then return lane end
    local instr = (i == 1) and want_instr or want_instr2
    if instr == INST_DRUMS then return lane end
    local n = LANES_BY_DIFF[(i == 1) and want_diff or want_diff2] or 5
    if lane > n then return lane end
    return n + 1 - lane
end

local function play_player(i, now)
    local bot = bots[i]
    local fields = bot.lane_field
    -- Colas largas: el fin se lee del Chart cuando entra a la pantalla; mientras tanto se sigue la Note
    for lane = 1, 5 do
        local h = bot.hold[lane]
        if h then
            local found = false
            for n in pending(i) do
                if n.frame == h.frame and n.mask & (1 << (lane - 1)) ~= 0 then
                    found = true
                    if n.end_ > 0 then bot.release[lane] = math.max(n.end_, now + 1); bot.hold[lane] = nil end
                end
            end
            if not found then bot.release[lane] = now + 1; bot.hold[lane] = nil end
        end
    end
    for lane = 1, 5 do
        if bot.release[lane] and now >= bot.release[lane] and not bot.hold[lane] then
            fields[phys_lane(i, lane)]:set_value(0)
            bot.release[lane] = nil
        end
    end
    if bot.mode == "nada" or bot.mode == "sinfallo" then return end
    -- Golpe al aire (machacar): el carril naranja si no hay Note cerca
    if bot.mode == "machacar" and now % 120 == 60 and not bot.release[5] and not bot.hold[5] then
        local free = true
        for n in pending(i) do
            if n.mask & 0x10 ~= 0 and n.frame <= now + 10 and n.frame + 10 >= now then free = false end
        end
        if free then
            fields[5]:set_value(1)
            bot.release[5] = now + 2
            air_hits = air_hits + 1
            if air_hits == 3 then shots.aire = frame + 4 end
        end
    end
    -- Tocar las Notes de este cuadro (el juego las juzga en el siguiente paso con este mismo `now`). Si el
    -- juego dio dos pasos entre dos VBlanks (se puso al día tras un cuadro lento), `now` salta uno: la Note
    -- se toca en cuanto se ve, hasta LATE_MAX cuadros tarde (la Hit_Window es de ±6), y una sola vez.
    for n in pending(i) do
        local open = n.mask & n.open
        local miss, delay = false, 0
        if open ~= 0 and bot.mode == "humano" then miss, delay = human_decide(i, n) end
        local key = n.frame .. ":" .. n.mask
        local due = n.frame + delay
        if open ~= 0 and due <= now and now - due <= LATE_MAX and not bot.done[key] then
            bot.done[key] = true
            bot.pressed_at = bot.pressed_at or {}
            bot.pressed_at[key] = now
            bot.skip = not bot.skip
            if (bot.mode == "mitad" and bot.skip) or miss then
                missed_on_purpose = missed_on_purpose + 1
            else
                for lane = 1, 5 do
                    if open & (1 << (lane - 1)) ~= 0 and bot.release[lane] then
                        note(string.format("carril %d ocupado para la Note del cuadro %d (cuadro %d)", lane, n.frame, now))
                    end
                    if open & (1 << (lane - 1)) ~= 0 and not bot.release[lane] then
                        fields[phys_lane(i, lane)]:set_value(1)
                        local until_frame = now + 3
                        if n.flags & CHART_FLAG_SUSTAIN ~= 0 then
                            if n.end_ > 0 then
                                until_frame = math.max(until_frame, n.end_)
                            else
                                until_frame = now + 6000
                                bot.hold[lane] = { frame = n.frame }
                            end
                        end
                        bot.release[lane] = until_frame
                    end
                end
            end
        end
    end
end

local play_last_now = 0
local function play()
    local now = rd("song_frame")
    if rd("paused") ~= 0 then return end        -- en pausa el bot no toca
    if now < play_last_now then                 -- la Practice vuelve a empezar: las Notes se tocan otra vez
        bots[1].done, bots[2].done = {}, {}
    end
    play_last_now = now
    if os.getenv("NGBAND_BOT_DEBUG") then      -- Notes tocadas que siguen abiertas 2 cuadros después
        for n in pending(1) do
            local k = n.frame .. ":" .. n.mask
            local at = bots[1].pressed_at and bots[1].pressed_at[k]
            if at and now >= at + 2 and n.mask & n.open ~= 0 and not (bots[1].reported or {})[k] then
                bots[1].reported = bots[1].reported or {}
                bots[1].reported[k] = true
                note(string.format("la Note %s sigue abierta (0x%02X): se tocó en %d, ahora %d", k, n.mask & n.open, at, now))
            end
        end
    end
    play_player(1, now)
    if want_players > 0 then play_player(2, now) end
end

-- R17.5: los cuadros del Frame_Stream que el 68000 mandó al Z80 (g_audio.expected, más los que siguen en la
-- cola de comandos) deben coincidir con los de la Chart (cuadro de la canción menos el LEAD_IN). La
-- Chart y el stream salen del mismo VGM, así que si coinciden cada alta de nota suena en el cuadro de su
-- Note. La respuesta real del Z80 la compara el driver en cada VBlank (g_audio.desync_count).
local function sample_sync(now)
    if now < 20 then return end                 -- (hasta que el Z80 recibe SONG_START la cuenta es la del Menu)
    local a = sym.g_audio
    local expected = mem:read_u8(a + AUDIO_EXPECTED)
    local head, tail = mem:read_u8(a + AUDIO_HEAD), mem:read_u8(a + AUDIO_TAIL)
    local queued = 0
    for k = head, tail - 1 do
        local cmd = mem:read_u16(a + AUDIO_Q + (k % AUDIO_QSIZE) * 2) >> 8
        if cmd == CMD_FRAME then queued = queued + 1 elseif cmd == CMD_FRAME2 then queued = queued + 2 end
    end
    local diff = (math.max(0, now - SONG_LEAD_IN) - expected - queued) & 0xFF
    if diff >= 128 then diff = diff - 256 end
    sync_n = sync_n + 1
    if math.abs(diff) > sync_max then sync_max = math.abs(diff) end
    if math.abs(diff) > SYNC_TOLERANCE then
        sync_bad = sync_bad + 1
        if sync_bad <= 5 then note(string.format("audio fuera de sincronía: cuadro %d, esperado %d, en cola %d, diferencia %d", now, expected, queued, diff)) end
    end
end

-- Pausa a mitad de la canción (modo "pausa"): en un hueco sin Notes, Start; ~3 s después, Start de nuevo
local function pause_test(now)
    local paused = rd("paused")
    if pause_stage == 0 then
        if now >= 1000 and #queue == 0 and not bots[1].hold[1] then
            local quiet = true
            for lane = 1, 5 do if bots[1].release[lane] or bots[1].hold[lane] then quiet = false end end
            for p = 1, math.max(1, want_players) do
                for n in pending(p) do
                    if n.frame <= now + 40 and n.frame + 12 >= now then quiet = false end
                end
            end
            if quiet then
                release_all()
                pause_song = now
                tap(field.start)
                pause_stage = 1
                note("pausa pedida en el cuadro " .. now)
            end
        end
    elseif pause_stage == 1 then
        if paused ~= 0 then
            pause_count = pause_count + 1
            if pause_count == 1 then pause_song = now end
            if pause_count >= 180 and #queue == 0 then
                pause_drift = now - pause_song          -- debe ser 0: el reloj se detiene
                tap(field.start)
                pause_stage = 2
                note("reanudar tras " .. pause_count .. " cuadros, deriva " .. pause_drift)
            end
        end
    elseif pause_stage == 2 and paused == 0 then
        pause_stage = 3
        pause_resumed_song = now
    end
end

local function read_result(base)
    local a = sym.g_probe + base
    return {
        score = mem:read_u32(a), hit = mem:read_u16(a + 4), total = mem:read_u16(a + 6), max_combo = mem:read_u16(a + 8),
        stars = mem:read_u16(a + 10), failed = mem:read_u16(a + 12), new_record = mem:read_u16(a + 14),
    }
end

local function read_best()
    local g = sym.g_probe
    local ini = string.char(mem:read_u8(g + PROBE_BEST_INI), mem:read_u8(g + PROBE_BEST_INI + 1), mem:read_u8(g + PROBE_BEST_INI + 2))
    return rd("best_score"), ini
end

-- Rendimiento (R17.8): cada VBlank debe tener su paso del bucle principal
local function lost_frames()
    if not vb0 then return 0, 0, 0 end
    local dv = (rd("vblank_count") - vb0) & 0xFFFFFFFF
    local ds = (rd("step_count") - st0) & 0xFFFFFFFF
    return dv - ds, dv, ds
end

local function write_result_file(extra)
    local f = io.open(out .. "/resultado.txt", "w")
    f:write(string.format("modo=%s\ncancion=%d\ninstrumento=%d\ndificultad=%d\n", mode, want_song, want_instr, want_diff))
    local lost, dv, ds = lost_frames()
    f:write(string.format("cuadros=%d\nvblanks=%d\npasos=%d\nperdidos=%d\ndesync=%d\n", frame, dv, ds, lost,
        mem:read_u16(sym.g_audio + AUDIO_DESYNC_OFFSET)))
    f:write(string.format("sync_max=%d\nsync_muestras=%d\nsync_fuera=%d\n", sync_max, sync_n, sync_bad))
    if mode == "pausa" or mode2 == "pausa" then
        f:write(string.format("pausa_etapa=%d\npausa_cuadros=%d\npausa_deriva=%d\n", pause_stage, pause_count, pause_drift))
    end
    f:write(extra or "")
    f:close()
end

local function result_text(prefix, r)
    return string.format("%spuntaje=%d\n%snotas=%d\n%stotal=%d\n%scombo_max=%d\n%sestrellas=%d\n%sfallo=%d\n%snuevo_record=%d\n",
        prefix, r.score, prefix, r.hit, prefix, r.total, prefix, r.max_combo, prefix, r.stars, prefix, r.failed, prefix, r.new_record)
end

local function write_result()
    local text = result_text("", read_result(RESULT_BASE.p1))
    if want_players > 0 then
        text = text .. result_text("j2_", read_result(RESULT_BASE.p2)) .. result_text("banda_", read_result(RESULT_BASE.band))
        text = text .. string.format("ganador=%d\n", mem:read_u16(sym.g_probe + PROBE_WINNER))
    end
    write_result_file(text)
end

local function finish_simple(text)
    write_result_file(text)
    state = "fin"
    wait = 3
end

-- Perfil (NGBAND_TRACE=<cuadro de la canción>, MAME con -debug -debugger none): traza el 68000 durante 3 cuadros
-- desde ese cuadro en <salida>/tr.txt. Luego: python3 tests/mame/trace_report.py <salida>/tr.txt
local trace_at = tonumber(os.getenv("NGBAND_TRACE") or "")
local LOST_DEBUG = os.getenv("NGBAND_LOST_DEBUG") == "1"
local lost_seen = 0
local trace_end
emu.register_frame_done(function()
    frame = frame + 1
    if trace_at then
        local dbg = manager.machine.debugger
        if frame == 2 then dbg:command("go") end
        if not trace_end and frame > 400 and rd("screen") == 3 and rd("song_frame") >= trace_at then
            dbg:command("trace " .. out .. "/tr.txt,maincpu,noloop")
            trace_end = frame + 3
        elseif trace_end and frame == trace_end then
            dbg:command("trace off,maincpu")
        end
    end
    if frame > TIMEOUT then
        note("se acabó el tiempo")
        manager.machine:exit()
        return
    end

    -- Pulsaciones de menú: cada una dura 2 cuadros y deja 4 libres
    if wait > 0 then
        wait = wait - 1
        if wait == 4 then release_all() end
        return
    end

    local s = rd("screen")
    if LOST_DEBUG and vb0 then   -- NGBAND_LOST_DEBUG=1: anota cada cuadro perdido (para perfilar con NGBAND_TRACE)
        local lost = lost_frames()
        if lost > lost_seen then
            note(string.format("cuadro perdido: canción %d (total %d)", rd("song_frame"), lost))
            lost_seen = lost
        end
    end
    if frame % 600 == 0 then
        local lost, dv, ds = lost_frames()
        note(string.format("pantalla %d, cuadro de la canción %d, estado %s, cola %d, vblank %d, pasos %d, perdidos %d, pc %06X",
            s, rd("song_frame"), state, #queue, dv, ds, lost, manager.machine.devices[":maincpu"].state["PC"].value))
    end
    if state == "titulo" then
        if s == SCREEN_TITLE then title_frames = title_frames + 1 end
        if title_frames > 60 then
            snapshot("titulo")
            tap(field.start)
            state = "al_menu"
        end
    elseif state == "al_menu" then
        if s == SCREEN_MENU and mode == "leer_record" then
            wait = 30
            state = "leyendo_record"
            return
        end
        if s == SCREEN_MENU then
            state = "menu"
            wait = 30
            return
        end
    elseif state == "leyendo_record" then
        local score, ini = read_best()
        snapshot("menu con record")
        finish_simple(string.format("record=%d\niniciales=%s\npuntaje=0\nnotas=0\ntotal=0\ncombo_max=0\nestrellas=0\nfallo=0\n", score, ini))
        return
    elseif state == "menu" then
        if #queue == 0 then
            menu_plan()
            state = "eligiendo"
        end
    elseif state == "eligiendo" then
        if #queue == 1 then snapshot("menu") end
        if #queue == 0 and s == SCREEN_PLAY then
            state = "jugando"
            vb0, st0 = rd("vblank_count"), rd("step_count")
            note("juego: modo " .. mode)
        end
    elseif state == "jugando" then
        if s == SCREEN_PLAY then
            play()
            local now = rd("song_frame")
            if mode ~= "practica" and mode ~= "marcas" then sample_sync(now) end
            if mode == "pausa" then pause_test(now) end
            if mode == "practica" or mode == "marcas" then
                if last_now and now + 30 < last_now then
                    -- (el primer reinicio tras marcar es el de la marca; el siguiente, el fin del bucle)
                    if marked and restarted_after_mark and not loop_end then loop_end = last_now end
                    if marked then restarted_after_mark = true end
                    loops = loops + 1
                    loop_frame = frame
                    note("la práctica volvió a empezar")
                end
                last_now = now
                -- Marcas: en la primera vuelta, a los 6 s, pausa y B (el bucle termina ahí)
                if mode == "marcas" and loops == 1 and not marked and frame > loop_frame + 360 and #queue == 0 then
                    marked = now
                    note("marca de fin en el cuadro " .. now)
                    release_all()
                    tap(field.start)
                    tap(field.b)
                end
                if loops >= (mode == "marcas" and 3 or 2) and frame > loop_frame + 120 and #queue == 0 and not leaving then
                    leaving = true
                    note("a la pausa y al menú, en el cuadro " .. now)
                    release_all()
                    tap(field.start)
                    tap(field.c)
                end
            end
            if shots.aire and frame == shots.aire then snapshot("aire") end
            if now == 1200 and not shots.juego then
                shots.juego = true
                snapshot("juego")
            end
        elseif s == SCREEN_RESULTS then
            release_all()
            state = "resultados"
            wait = 60
            return
        elseif s == SCREEN_MENU and (mode == "practica" or mode == "marcas") then
            note("de vuelta en el menú tras " .. loops .. " vueltas")
            finish_simple(string.format("vueltas=%d\nmarca=%d\nfin_bucle=%d\npuntaje=0\nnotas=0\ntotal=0\ncombo_max=0\nestrellas=0\nfallo=0\n",
                loops, marked or 0, loop_end or 0))
            return
        end
    elseif state == "resultados" then
        snapshot("resultados")
        write_result()
        if mode == "record" then
            -- Iniciales: de las que traiga (AAA la primera vez) a BOT
            tap(field.start)
            table.insert(queue, { screen = SCREEN_INITIALS })
            table.insert(queue, { shot = "iniciales" })
            tap(field.up)
            tap(field.right)
            for _ = 1, 14 do tap(field.up) end
            tap(field.right)
            for _ = 1, 19 do tap(field.up) end
            tap(field.start)
            if want_players == 1 then tap(field2.start) end     -- VS: el jugador 2 deja las que traiga
            table.insert(queue, { screen = SCREEN_MENU })
            state = "iniciales"
            return
        end
        note("fin (notas falladas a propósito: " .. missed_on_purpose .. ", golpes al aire: " .. air_hits .. ")")
        state = "fin"
        wait = 3
        return
    elseif state == "iniciales" then
        if #queue == 0 then
            wait = 30           -- el Menu necesita unos cuadros para mostrar el récord nuevo
            state = "iniciales_leer"
            return
        end
    elseif state == "iniciales_leer" then
        local score, ini = read_best()
        local f = io.open(out .. "/resultado.txt", "a")
        f:write(string.format("record=%d\niniciales=%s\n", score, ini))
        f:close()
        snapshot("menu con record")
        note("récord guardado: " .. score .. " " .. ini)
        state = "fin"
        wait = 3
        return
    elseif state == "fin" then
        manager.machine:exit()
        return
    end

    if #queue > 0 then
        local f = queue[1]
        if type(f) == "table" and f.plan2 then
            -- El jugador 2 elige con su control: aprieta hasta que la RAM tenga lo pedido
            table.remove(queue, 1)
            local steps = { { until_ = function() return rd("menu_instr2") == want_instr2 end, press = field2.right } }
            if want_players == 2 then
                table.insert(steps, field2.down)
                table.insert(steps, { until_ = function() return rd("menu_diff2") == want_diff2 end, press = field2.right })
            end
            for k = #steps, 1, -1 do table.insert(queue, 1, steps[k]) end
            return
        end
        if type(f) == "table" and f.shot then
            table.remove(queue, 1)
            snapshot(f.shot)
            return
        end
        if type(f) == "table" and f.until_ then
            if f.until_() then
                table.remove(queue, 1)
                return
            end
            f.press:set_value(1)
            wait = 6
            return
        end
        if type(f) == "table" and f.screen then
            -- Esperar a que la pantalla esté lista (y unos cuadros más) antes de seguir
            if s == f.screen then
                table.remove(queue, 1)
                wait = 20
            end
            return
        end
        table.remove(queue, 1)
        f:set_value(1)
        wait = 6
    end
end)
