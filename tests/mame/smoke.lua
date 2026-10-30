-- Humo rápido en MAME: pasa título -> Menu -> juego con Start y cada 60 cuadros anota pantalla, VBlanks
-- y pasos del bucle principal (si step crece menos que vblank, se pierden cuadros). Capturas en 200, 360, 900.
-- Uso: tests/mame/run.sh smoke     (lee la dirección de g_probe de build/ngband.sym)
local probe = tonumber(os.getenv("NGBAND_PROBE"), 16)
local out = os.getenv("NGBAND_OUT") or "build/smoke"
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local start
for _, port in pairs(manager.machine.ioport.ports) do
  for name, fl in pairs(port.fields) do if name == "1 Player Start" or name == "P1 Start" then start = start or fl end end
end
local f = 0
local log = io.open(out .. "/log.txt", "w")
emu.register_frame_done(function()
  f = f + 1
  if f % 60 == 0 then log:write(string.format("frame %d screen %d vblank %d step %d\n", f, mem:read_u16(probe), mem:read_u32(probe+8), mem:read_u32(probe+12))); log:flush() end
  if f == 200 or f == 360 or f == 900 then manager.machine.video:snapshot() end
  if f == 240 or f == 400 then start:set_value(1) end
  if f == 244 or f == 404 then start:set_value(0) end
  if f == 960 then manager.machine:exit() end
end)
