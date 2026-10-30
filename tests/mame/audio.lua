-- Audio en MAME: título -> Menu, ← elige la última canción (la del final de la M1) y la deja sonar en el Menu.
-- Cada 60 cuadros anota la posición del stream en el Z80 (g_sh.pos), sus cuadros aplicados, la respuesta y,
-- con NGBAND_DEBUG, las desincronías que ve el 68000 (g_audio.desync_count). El WAV lo graba run.sh.
-- Uso: tests/mame/run.sh audio
local probe = tonumber(os.getenv("NGBAND_PROBE"), 16)
local audio = tonumber(os.getenv("NGBAND_AUDIO") or "0", 16)
local zsh = tonumber(os.getenv("NGBAND_Z80_SH"), 16)
local out = os.getenv("NGBAND_OUT") or "build/smoke"
local frames = tonumber(os.getenv("NGBAND_AUDIO_FRAMES") or "3600")
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local zmem = manager.machine.devices[":audiocpu"].spaces["program"]
local fields = {}
for _, port in pairs(manager.machine.ioport.ports) do
  for name, fl in pairs(port.fields) do fields[name] = fields[name] or fl end
end
local start = fields["1 Player Start"] or fields["P1 Start"]
local left = fields["P1 Left"]
-- ShadowRegs en el Z80 (SDCC, little endian, sin relleno): reg[2][256], muted, inst_mask[4], start, pos, end, ret,
-- rep_left, drums, drum_count, drum_next, drum_muted, paused, replay, keyon[4], sfx_active, sfx_id, sfx_pos, sfx_mix, frames
local SH_START, SH_POS, SH_END, SH_FRAMES = 0x20A, 0x20E, 0x212, 0x22B
local f = 0
local log = io.open(out .. "/audio.txt", "w")
emu.register_frame_done(function()
  f = f + 1
  if f % 60 == 0 then
    local desync = audio ~= 0 and mem:read_u16(audio + 40) or -1
    local last = audio ~= 0 and string.format(" (esperaba %d, Z80 %d)", mem:read_u8(audio + 42), mem:read_u8(audio + 43)) or ""
    log:write(string.format("frame %d screen %d song %d start %06X pos %06X end %06X zframes %d desync %d%s\n",
      f, mem:read_u16(probe), mem:read_u16(probe + 16),
      zmem:read_u32(zsh + SH_START), zmem:read_u32(zsh + SH_POS), zmem:read_u32(zsh + SH_END),
      zmem:read_u8(zsh + SH_FRAMES), desync, last))
    log:flush()
  end
  if f == 240 then start:set_value(1) end
  if f == 244 then start:set_value(0) end
  if f == 300 then left:set_value(1) end
  if f == 304 then left:set_value(0) end
  if f == frames then manager.machine:exit() end
end)
