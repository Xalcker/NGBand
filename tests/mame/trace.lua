-- Traza todas las instrucciones del 68000 durante 3 cuadros de juego (cuadros 700-703) en build/smoke/tr.txt.
-- Necesita MAME con -debug -debugger none. Luego: python3 tests/mame/trace_report.py
local start
for _, port in pairs(manager.machine.ioport.ports) do for name, fl in pairs(port.fields) do if name == "1 Player Start" then start = fl end end end
local dbg = manager.machine.debugger
local f = 0
emu.register_frame_done(function()
  f = f + 1
  if f == 2 then dbg:command("go") end
  if f == 240 or f == 400 then start:set_value(1) end
  if f == 244 or f == 404 then start:set_value(0) end
  if f == 700 then dbg:command("trace build/smoke/tr.txt,maincpu,noloop") end
  if f == 703 then dbg:command("trace off,maincpu") end
  if f == 705 then manager.machine:exit() end
end)
