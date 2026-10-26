-- Morrowind Workshop live link (player side).
--
-- Tells the Workshop where you are (for Follow my character and Go here in game). Nothing in the game
-- changes your mod: you build in the Workshop, and your edits show up here within a second.
-- (The in-game building keys, Shift+B/J/G/X/K/L/Z/Delete, were taken out after 2.4.11: Shift is the run
-- key, so running while pressing J for the journal placed things, and Shift+Z undid the Workshop's own
-- last change. The user: "those in-game editing keys", obsolete next to the 3D view.)

local self = require('openmw.self')

local last = nil
local timer, beat = 0, 0

local function say(fmt, ...)
  print('[WSLINK] ' .. string.format(fmt, ...))
end

local function cellInfo(c)
  return c.isExterior and 'ext' or 'int', c.name or '', c.gridX or 0, c.gridY or 0
end

local function onUpdate(dt)
  timer = timer + dt
  beat = beat + dt
  if timer < 0.5 then return end
  timer = 0
  local p, c = self.position, self.cell
  local yaw = self.rotation:getYaw()
  local moved = not last or (p - last.p):length() > 24 or c ~= last.c or math.abs(yaw - last.yaw) > 0.25
  if moved or beat > 3 then
    beat = 0
    local kind, name, gx, gy = cellInfo(c)
    say('pos\t%s\t%s\t%d\t%d\t%.1f\t%.1f\t%.1f\t%.3f', kind, name, gx, gy, p.x, p.y, p.z, yaw)
    last = { p = p, c = c, yaw = yaw }
  end
end

return {
  engineHandlers = {
    onUpdate = onUpdate,
  },
}
