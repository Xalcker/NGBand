# Funciones para correr MAME en las pruebas (se carga con `source`).
#
#   run_mame <log> <argumentos de MAME...>
#
# Por defecto MAME corre sin ventana (-video none y SDL_VIDEODRIVER=dummy: en macOS -video none solo sigue
# abriendo una ventana). Con NGBAND_MAME_WINDOW=1 abre su ventana, pero en segundo
# plano: en macOS la ventana de MAME (SDL) toma el foco al aparecer, así que se le devuelve a la aplicación que
# estaba al frente y se puede seguir trabajando mientras corre la prueba. MAME no se pausa al perder el foco y
# el teclado no le llega (el bot de Lua maneja los controles). El sonido sigue apagado (-sound none); el audio
# de la prueba queda en el WAV de -wavwrite.
MAME="${MAME:-mame}"

_front_asn() { lsappinfo front 2>/dev/null || true; }   # la aplicación al frente (vacío fuera de macOS)
_bundle_id() { lsappinfo info -only bundleid "$1" 2>/dev/null | sed -n 's/.*"CFBundleIdentifier"="\(.*\)".*/\1/p'; }

run_mame() {
    local log=$1
    shift
    if [ "${NGBAND_MAME_WINDOW:-0}" != 1 ]; then
        SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-dummy}" "$MAME" "$@" -video none >"$log" 2>&1
        return
    fi
    local front id pid now i
    front=$(_front_asn)
    id=""
    if [ -n "$front" ]; then id=$(_bundle_id "$front"); fi
    "$MAME" "$@" -window -nomaximize -resolution 640x448 >"$log" 2>&1 &
    pid=$!
    # hasta 5 s para que aparezca la ventana; en cuanto cambia la app al frente, se devuelve el foco
    if [ -n "$id" ]; then
        for i in $(seq 1 50); do
            sleep 0.1
            kill -0 $pid 2>/dev/null || break
            now=$(_front_asn)
            if [ -n "$now" ] && [ "$now" != "$front" ]; then
                open -b "$id"
                break
            fi
        done
    fi
    wait $pid
}
