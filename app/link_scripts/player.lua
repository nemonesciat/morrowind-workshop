-- Morrowind Workshop live link (player side).
--
-- In-game building controls (all with Shift held):
--   Shift+B   open the build menu: search everything, or pick from suggestions for this place
--   Shift+J   place the chosen object where you're looking (repeat to place more)
--   Shift+G   grab the object you're looking at; it follows your aim, mouse wheel turns it,
--             Shift+G again sets it down (Shift+X cancels)
--   Shift+K   select the object you're looking at in the Workshop
--   Shift+Delete  remove the object you're looking at
--   Shift+Z   undo the last change
-- Every change is sent to the Workshop, which saves it in your mod and updates the game.

local self = require('openmw.self')
local input = require('openmw.input')
local camera = require('openmw.camera')
local nearby = require('openmw.nearby')
local util = require('openmw.util')
local ui = require('openmw.ui')
local core = require('openmw.core')
local types = require('openmw.types')
local vfs = require('openmw.vfs')
local async = require('openmw.async')
local I = require('openmw.interfaces')

local STATE = 'workshop_link/state.txt'
local GOLD = util.color.rgb(0.94, 0.80, 0.53)
local TEXT = util.color.rgb(0.87, 0.83, 0.74)
local DIM = util.color.rgb(0.6, 0.56, 0.48)

local last = nil
local timer, beat = 0, 0
local armed = nil          -- { id, name } chosen for Shift+J
local grab = nil           -- { obj, yaw, t }
local hud = nil
local menu = nil
local menuState = { tab = 'suggested', query = '', results = {} }
local catalog = nil        -- every placeable record, built the first time the menu opens
local pendingBig = nil     -- a wall/floor the player tried to grab (needs a second press)

local function say(fmt, ...)
  print('[WSLINK] ' .. string.format(fmt, ...))
end

local function cellInfo(c)
  return c.isExterior and 'ext' or 'int', c.name or '', c.gridX or 0, c.gridY or 0
end

local function lookRay(ignore)
  local from = camera.getPosition()
  local dir = camera.viewportToWorldVector(util.vector2(0.5, 0.5))
  local to = from + dir * 6000
  local ok, res = pcall(nearby.castRenderingRay, from, to, { ignore = ignore or self })
  if ok then return res end
  return nearby.castRenderingRay(from, to)
end

-- ------------------------------------------------------------------ HUD hint
local function setHud(text)
  if hud then hud:destroy(); hud = nil end
  if not text then return end
  hud = ui.create({
    layer = 'HUD',
    type = ui.TYPE.Text,
    props = {
      relativePosition = util.vector2(0.5, 0.08), anchor = util.vector2(0.5, 0),
      text = text, textSize = 18, textColor = GOLD, textShadow = true,
    },
  })
end

local function refreshHud()
  if grab then
    local deg = math.floor(math.deg(grab.yaw) % 360 + 0.5) % 360
    local up = grab.lift ~= 0 and string.format(', raised %+d', grab.lift) or ''
    setHud(string.format('Workshop: moving %s  (facing %d°%s)\n' ..
      'wheel: turn 15°   Shift+wheel: turn 1°   PageUp/PageDown: raise/lower (Shift: fine)   Shift+G: set down   Shift+X: cancel',
      grab.name, deg, up))
  elseif armed then
    local deg = math.floor(math.deg(armed.yaw or 0) % 360 + 0.5) % 360
    local up = (armed.lift or 0) ~= 0 and string.format(', raised %+d', armed.lift) or ''
    setHud(string.format('Workshop: placing %s  (facing %d°%s)%s\n' ..
      'Shift+J: place it here   wheel / Shift+wheel: turn   PageUp/PageDown: raise/lower   Shift+X: stop',
      armed.name, deg, up, armed.obj and '' or '  - no preview for this one'))
  else
    setHud(nil)
  end
end

-- ------------------------------------------------------------------ catalog / search
local KINDS = {
  { 'Static', 'Static' }, { 'Activator', 'Activator' }, { 'Container', 'Container' }, { 'Door', 'Door' },
  { 'Light', 'Light' }, { 'Miscellaneous', 'Misc item' }, { 'Book', 'Book' }, { 'Weapon', 'Weapon' },
  { 'Armor', 'Armor' }, { 'Clothing', 'Clothing' }, { 'Potion', 'Potion' }, { 'Ingredient', 'Ingredient' },
  { 'Apparatus', 'Apparatus' }, { 'Lockpick', 'Lockpick' }, { 'Probe', 'Probe' }, { 'Repair', 'Repair tool' },
  { 'NPC', 'NPC' }, { 'Creature', 'Creature' },
}

local function buildCatalog()
  catalog = {}
  for _, k in ipairs(KINDS) do
    local t = types[k[1]]
    local ok, recs = pcall(function() return t.records end)
    if ok and recs then
      for i = 1, #recs do
        local r = recs[i]
        local okName, name = pcall(function() return r.name end)
        name = (okName and name) or ''
        local okIcon, icon = pcall(function() return r.icon end)
        catalog[#catalog + 1] = { id = r.id, name = name, kind = k[2], hay = (r.id .. ' ' .. name):lower(),
                                  icon = (okIcon and icon and icon ~= '') and icon or nil }
      end
    end
  end
end

local function search(query)
  local words = {}
  for w in query:lower():gmatch('%S+') do words[#words + 1] = w end
  if #words == 0 then return {} end
  local exact, rest = {}, {}
  for _, e in ipairs(catalog) do
    local ok = true
    for _, w in ipairs(words) do
      if not e.hay:find(w, 1, true) then ok = false; break end
    end
    if ok then
      if e.name:lower():find(words[1], 1, true) == 1 or e.id:lower():find(words[1], 1, true) == 1 then
        exact[#exact + 1] = e
      else
        rest[#rest + 1] = e
      end
      if #exact >= 40 then break end
    end
  end
  for _, e in ipairs(rest) do
    if #exact >= 40 then break end
    exact[#exact + 1] = e
  end
  return exact
end

-- suggestions for the current place, written by the Workshop into the state file
local function suggestions()
  local out = {}
  if not vfs.fileExists(STATE) then return out end
  local ok, text = pcall(function()
    local f = vfs.open(STATE); local t = f:read('*a'); f:close(); return t
  end)
  if not ok or not text then return out end
  for line in text:gmatch('[^\r\n]+') do
    local tag, id, name, group = line:match('^(palette)\t([^\t]*)\t([^\t]*)\t([^\t]*)')
    if tag then out[#out + 1] = { id = id, name = name, kind = group } end
  end
  return out
end

-- ------------------------------------------------------------------ build menu
local closeMenu
local renderMenu

local function disarm()
  if armed and armed.obj then core.sendGlobalEvent('WsGhostEnd', { obj = armed.obj }) end
  armed = nil
end

-- Ready an object for placing, with a live preview ("ghost") that follows the crosshair
local function arm(id, name)
  disarm()
  armed = { id = id, name = name, yaw = self.rotation:getYaw() + math.pi, lift = 0 }
  core.sendGlobalEvent('WsGhostStart', { id = id, player = self })
  refreshHud()
end

local function choose(e)
  local name = (e.name ~= '' and e.name) or e.id
  say('arm\t%s\t%s', e.id, name)
  closeMenu()
  arm(e.id, name)
  ui.showMessage('Placing ' .. name .. ': aim where you want it and press Shift+J.')
end

local function iconPath(p)
  p = p:gsub('\\', '/')
  if not p:lower():find('^icons/') then p = 'icons/' .. p end
  return p
end

local function label(text, size, color)
  return { type = ui.TYPE.Text, props = { text = text, textSize = size or 16, textColor = color or TEXT } }
end

local function button(text, active, onClick)
  return {
    template = I.MWUI.templates.box,
    content = ui.content({
      { type = ui.TYPE.Text,
        props = { text = '  ' .. text .. '  ', textSize = 16, textColor = active and GOLD or DIM },
        events = { mouseClick = async:callback(onClick) } },
    }),
  }
end

local function row(e)
  local name = (e.name ~= '' and e.name) or e.id
  local extra = e.name ~= '' and ('  ' .. e.id) or ''
  local icon = { type = ui.TYPE.Widget, props = { size = util.vector2(28, 24) } }
  if e.icon then
    local ok, tex = pcall(ui.texture, { path = iconPath(e.icon) })
    if ok and tex then
      icon = { type = ui.TYPE.Image, props = { resource = tex, size = util.vector2(24, 24) },
               events = { mouseClick = async:callback(function() choose(e) end) } }
    end
  end
  return {
    type = ui.TYPE.Flex,
    props = { horizontal = true },
    content = ui.content({
      icon,
      { type = ui.TYPE.Text, props = { text = ' ', textSize = 16 } },
      { type = ui.TYPE.Text, props = { text = name, textSize = 16, textColor = TEXT },
        events = { mouseClick = async:callback(function() choose(e) end) } },
      { type = ui.TYPE.Text, props = { text = extra .. '  (' .. (e.kind or '') .. ')', textSize = 13, textColor = DIM },
        events = { mouseClick = async:callback(function() choose(e) end) } },
    }),
  }
end

renderMenu = function()
  if not menu then return end
  local list = menuState.tab == 'suggested' and menuState.suggested or menuState.results
  local rows = {}
  if menuState.tab == 'suggested' and #list == 0 then
    rows[1] = label('No suggestions for this place yet. Try Search.', 15, DIM)
  elseif menuState.tab == 'search' and #list == 0 then
    rows[1] = label(menuState.query == '' and 'Type above to search every object in your game.' or 'Nothing found.', 15, DIM)
  end
  for i = 1, math.min(#list, 22) do rows[#rows + 1] = row(list[i]) end
  -- the window itself is the solid box (it sizes itself to what's inside)
  menu.layout.content = ui.content({
        {
          type = ui.TYPE.Flex,
          props = { position = util.vector2(8, 8) },
          content = ui.content({
            label('Morrowind Workshop: build', 20, GOLD),
            label('Click something to choose it, then look at a spot and press Shift+J.', 14, DIM),
            { type = ui.TYPE.Flex, props = { horizontal = true }, content = ui.content({
              button('Suggested here', menuState.tab == 'suggested', function() menuState.tab = 'suggested'; renderMenu() end),
              button('Search everything', menuState.tab == 'search', function() menuState.tab = 'search'; renderMenu() end),
              button('Undo last change', false, function() say('undo'); ui.showMessage('Workshop: undoing...') end),
              button('Close', false, function() closeMenu() end),
            }) },
            menuState.tab == 'search' and {
              name = 'search',
              template = I.MWUI.templates.textEditLine,
              props = { text = menuState.query, size = util.vector2(540, 24) },
              events = { textChanged = async:callback(function(text)
                menuState.query = text
                menuState.results = search(text)
                renderMenu()
              end) },
            } or label(' ', 6),
            { type = ui.TYPE.Flex, content = ui.content(rows) },
            label(' ', 8),
          }),
        },
  })
  menu:update()
end

local function openMenu()
  if menu then return end
  if not catalog then buildCatalog() end
  menuState.suggested = suggestions()
  if #menuState.suggested == 0 then menuState.tab = 'search' end
  menu = ui.create({
    layer = 'Windows',
    template = I.MWUI.templates.boxSolid,
    props = { relativePosition = util.vector2(0.5, 0.5), anchor = util.vector2(0.5, 0.5) },
    content = ui.content({}),
  })
  I.UI.setMode(I.UI.MODE.Interface, { windows = {} })
  renderMenu()
end

closeMenu = function()
  if menu then menu:destroy(); menu = nil end
  if I.UI.getMode() == I.UI.MODE.Interface then I.UI.removeMode(I.UI.MODE.Interface) end
end

-- ------------------------------------------------------------------ grab / move
local function boundingBox(o)
  local ok, bb = pcall(function() return o:getBoundingBox() end)
  if ok and bb then return bb end
  return nil
end

-- Move the held object to where the player is aiming. During normal frames
-- OpenMW only allows the delayed ("async") version of the aim check.
local aimBusy = false
-- h is whatever follows the crosshair: the grabbed object, or the preview of what's being placed
local function followAim(h)
  if aimBusy or not h or not h.obj then return end
  local from = camera.getPosition()
  local dir = camera.viewportToWorldVector(util.vector2(0.5, 0.5))
  local to = from + dir * 6000
  local held = h.obj
  local function onHit(res)
    aimBusy = false
    if h.obj ~= held or not (res and res.hit and res.hitPos) then return end
    if res.hitObject == held then return end          -- the ray hit the object itself
    local pos = res.hitPos
    if h.bottomOffset then pos = util.vector3(pos.x, pos.y, pos.z + h.bottomOffset) end
    pos = util.vector3(pos.x, pos.y, pos.z + (h.lift or 0))
    h.target = pos
    core.sendGlobalEvent('WsGrabMove', { obj = held, pos = pos, yaw = h.yaw })
  end
  aimBusy = true
  local ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to, { ignore = held })
  if not ok then
    ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to)
    if not ok then aimBusy = false end
  end
end

local function startGrab()
  local res = lookRay()
  local o = res.hitObject
  if not o then ui.showMessage('Workshop: look at the object you want to move'); return end
  if o.type == types.NPC and o.recordId == 'player' then return end
  -- walls and floors are easy to grab by mistake: ask for a second press
  local bb = boundingBox(o)
  local big = bb and (bb.halfSize.x > 200 or bb.halfSize.y > 200)
  local now = core.getRealTime and core.getRealTime() or 0
  if big and not (pendingBig and pendingBig.obj == o and now - pendingBig.t < 3) then
    pendingBig = { obj = o, t = now }
    ui.showMessage('Workshop: that looks like part of the building (' .. o.recordId ..
                   '). Press Shift+G again to move it anyway.')
    return
  end
  pendingBig = nil
  local okName, n = pcall(function() return o.type.record(o).name end)
  grab = { obj = o, orig = o.position, yaw = o.rotation:getYaw(), origYaw = o.rotation:getYaw(), t = 0, lift = 0,
           name = (okName and n and n ~= '' and n) or o.recordId }
  if bb then grab.bottomOffset = o.position.z - (bb.center.z - bb.halfSize.z) end
  core.sendGlobalEvent('WsGrabStart', { obj = o })
  refreshHud()
end

local function dropGrab(cancel)
  if not grab then return end
  local o = grab.obj
  if cancel then
    core.sendGlobalEvent('WsGrabMove', { obj = o, pos = grab.orig, yaw = grab.origYaw })
  else
    local kind, name, gx, gy = cellInfo(o.cell)
    local p = grab.target or o.position
    say('move\t%s\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s\t%d\t%d', o.recordId,
        grab.orig.x, grab.orig.y, grab.orig.z, p.x, p.y, p.z, grab.yaw,
        kind, name, gx, gy)
    ui.showMessage('Workshop: set down ' .. grab.name)
  end
  grab = nil
  refreshHud()
end

-- ------------------------------------------------------------------ engine handlers
local function onUpdate(dt)
  if grab then
    if not grab.obj:isValid() then grab = nil; refreshHud()
    else followAim(grab) end
  elseif armed and armed.obj then
    if not armed.obj:isValid() then armed.obj = nil; refreshHud()
    else followAim(armed) end
  end
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

local function onKeyPress(key)
  local K = input.KEY
  local h = grab or armed
  if h and (key.code == K.PageUp or key.code == K.PageDown) then
    local step = key.withShift and 1 or 8
    h.lift = (h.lift or 0) + (key.code == K.PageUp and step or -step)
    refreshHud()
    return
  end
  if not key.withShift then return end
  if key.code == K.B then
    if menu then closeMenu() else openMenu() end
  elseif key.code == K.K then
    local o = lookRay().hitObject
    if o then
      local kind, name, gx, gy = cellInfo(o.cell)
      say('pick\t%s\t%.1f\t%.1f\t%.1f\t%s\t%s\t%d\t%d', o.recordId, o.position.x, o.position.y, o.position.z,
          kind, name, gx, gy)
      ui.showMessage('Workshop: selected ' .. o.recordId)
    else
      ui.showMessage('Workshop: nothing under the crosshair')
    end
  elseif key.code == K.J then
    local kind, name, gx, gy = cellInfo(self.cell)
    if armed and armed.obj and armed.target then
      -- place exactly where the preview stands, turned the way it's turned
      local p = armed.target
      say('placeat\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s\t%d\t%d\t%s\texact', p.x, p.y, p.z, armed.yaw,
          kind, name, gx, gy, armed.id)
      core.sendGlobalEvent('WsGhostDrop', { obj = armed.obj })
      armed.obj, armed.target = nil, nil
      core.sendGlobalEvent('WsGhostStart', { id = armed.id, player = self })   -- a fresh preview for the next one
      ui.showMessage('Workshop: placed ' .. armed.name)
    else
      local res = lookRay()
      if res.hit and res.hitPos then
        say('placeat\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s\t%d\t%d\t%s', res.hitPos.x, res.hitPos.y,
            res.hitPos.z + (armed and armed.lift or 0), armed and armed.yaw or self.rotation:getYaw() + math.pi,
            kind, name, gx, gy, armed and armed.id or '')
        ui.showMessage(armed and ('Workshop: placing ' .. armed.name) or 'Workshop: placing...')
      else
        ui.showMessage('Workshop: look at a floor or surface to place something')
      end
    end
  elseif key.code == K.G then
    if grab then dropGrab(false) else
      if armed then disarm(); refreshHud() end
      startGrab()
    end
  elseif key.code == K.X then
    if grab then dropGrab(true)
    elseif armed then
      disarm(); refreshHud()
      say('disarm')                                  -- so the Workshop knows too
      ui.showMessage('Workshop: stopped placing')
    end
  elseif key.code == K.Delete then
    local o = lookRay().hitObject
    if o then
      local kind, name, gx, gy = cellInfo(o.cell)
      say('del\t%s\t%.1f\t%.1f\t%.1f\t%s\t%s\t%d\t%d', o.recordId, o.position.x, o.position.y, o.position.z,
          kind, name, gx, gy)
      ui.showMessage('Workshop: removing ' .. o.recordId)
    end
  elseif key.code == K.Z then
    say('undo')
    ui.showMessage('Workshop: undoing the last change...')
  end
end

local function onMouseWheel(vertical)
  local h = grab or armed
  if h and vertical and vertical ~= 0 then
    local fine = input.isShiftPressed and input.isShiftPressed()
    h.yaw = (h.yaw or 0) + (vertical > 0 and 1 or -1) * math.rad(fine and 1 or 15)
    if h.obj and h.target then
      core.sendGlobalEvent('WsGrabMove', { obj = h.obj, pos = h.target, yaw = h.yaw })
    end
    refreshHud()
  end
end

return {
  engineHandlers = {
    onUpdate = onUpdate,
    onKeyPress = onKeyPress,
    onMouseWheel = onMouseWheel,
  },
  eventHandlers = {
    UiModeChanged = function(data)
      -- Esc or anything else that closes the interface also closes our menu
      if menu and data.newMode == nil then
        menu:destroy(); menu = nil
      end
    end,
    -- the preview object for what's being placed was created by the global script
    WsGhostReady = function(data)
      if not armed or armed.id:lower() ~= (data.id or ''):lower() then
        core.sendGlobalEvent('WsGhostEnd', { obj = data.obj })      -- no longer wanted
        return
      end
      armed.obj = data.obj
      local bb = boundingBox(data.obj)
      if bb then armed.bottomOffset = data.obj.position.z - (bb.center.z - bb.halfSize.z) end
      refreshHud()
    end,
    WsGhostFailed = function(data)
      if armed and armed.id:lower() == (data.id or ''):lower() then
        armed.obj = nil
        refreshHud()
      end
    end,
    -- the Workshop readied something (palette / search there): place it with a preview here too
    WsArm = function(data)
      if data.id and (not armed or armed.id:lower() ~= data.id:lower()) then arm(data.id, data.name or data.id) end
    end,
    WsDisarm = function()
      if armed then disarm(); refreshHud(); ui.showMessage('Workshop: stopped placing') end
    end,
  },
}
