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
--   Shift+L   change the colour / brightness of the light you're looking at
--   Ctrl+wheel or +/-  make what you're holding or placing bigger or smaller
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

local function sizeText(h)
  local s = h.scale or 1
  return math.abs(s - 1) > 0.001 and string.format(', size %d%%', math.floor(s * 100 + 0.5)) or ''
end

local function refreshHud()
  if grab then
    local deg = math.floor(math.deg(grab.yaw) % 360 + 0.5) % 360
    local up = grab.lift ~= 0 and string.format(', raised %+d', grab.lift) or ''
    setHud(string.format('Workshop: moving %s  (facing %d°%s%s)\n' ..
      'wheel: turn 15°   Shift+wheel: turn 1°   Ctrl+wheel or +/-: size   PageUp/PageDown: raise/lower (Shift: fine)   Shift+G: set down   Shift+X: cancel',
      grab.name, deg, up, sizeText(grab)))
  elseif armed and armed.brush then
    setHud(string.format('Workshop: painting with %s  (patch %d wide)\n' ..
      'Shift+J: paint a patch where you aim   PageUp/PageDown: bigger/smaller patch   Shift+X: stop',
      armed.name, armed.radius * 2))
  elseif armed then
    local deg = math.floor(math.deg(armed.yaw or 0) % 360 + 0.5) % 360
    local up = (armed.lift or 0) ~= 0 and string.format(', raised %+d', armed.lift) or ''
    setHud(string.format('Workshop: placing %s  (facing %d°%s%s)%s\n' ..
      'Shift+J: place it here   wheel / Shift+wheel: turn   %sPageUp/PageDown: raise/lower   Shift+X: stop',
      armed.name, deg, up, sizeText(armed), (armed.obj or armed.group) and (armed.prefab and '  - a prefab' or '') or
        (armed.prefab and '  - a prefab' or '  - no preview for this one'),
      armed.prefab and '' or 'Ctrl+wheel or +/-: size   '))
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
local libItems, prefabItems, brushItems = {}, {}, {}
local function suggestions()
  local out = {}
  libItems, prefabItems, brushItems = {}, {}, {}
  local pfByFile = {}
  if not vfs.fileExists(STATE) then return out end
  local ok, text = pcall(function()
    local f = vfs.open(STATE); local t = f:read('*a'); f:close(); return t
  end)
  if not ok or not text then return out end
  for line in text:gmatch('[^\r\n]+') do
    local tag, id, name, group = line:match('^(palette)\t([^\t]*)\t([^\t]*)\t([^\t]*)')
    if tag then out[#out + 1] = { id = id, name = name, kind = group } end
    local lid, lname, licon, lfile = line:match('^lib\t([^\t]*)\t([^\t]*)\t?([^\t]*)\t?([^\t]*)')
    if lid then
      -- a model brought in after the game started isn't among the game's files until it starts again
      local fresh = lfile ~= '' and not vfs.fileExists(lfile)
      libItems[#libItems + 1] = { id = lid, name = lname, lib = true, fresh = fresh,
                                  kind = fresh and 'new: start the game again to use it' or 'your model',
                                  icon = licon ~= '' and licon or nil }
    end
    local pf, pname, pn = line:match('^prefab\t([^\t]*)\t([^\t]*)\t([^\t]*)')
    if pf then
      local e = { id = pf, name = pname, kind = pn .. ' objects', prefab = true, items = {} }
      prefabItems[#prefabItems + 1] = e
      pfByFile[pf] = e
    end
    -- one object of a prefab: where it sits from the prefab's middle (for the preview)
    local pff, rid, dx, dy, dz, rz = line:match('^pfitem\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)')
    if pff and pfByFile[pff] then
      local its = pfByFile[pff].items
      its[#its + 1] = { id = rid, dx = tonumber(dx) or 0, dy = tonumber(dy) or 0, dz = tonumber(dz) or 0, rz = tonumber(rz) or 0 }
    end
    local bk, bname, bgap, bn = line:match('^brush\t([^\t]*)\t([^\t]*)\t([^\t]*)\t?([^\t]*)')
    if bk then
      brushItems[#brushItems + 1] = { id = bk, name = bname, gap = tonumber(bgap) or 200, brush = true,
                                      kind = (bk:sub(1, 3) == 'my:' and 'your brush, ' or 'grows here, ') .. (bn ~= '' and bn or '?') .. ' kinds' }
    end
  end
  return out
end

-- ------------------------------------------------------------------ build menu
local closeMenu
local renderMenu

local function disarm()
  if armed and armed.obj then core.sendGlobalEvent('WsGhostEnd', { obj = armed.obj }) end
  if armed and armed.group then core.sendGlobalEvent('WsGhostGroupEnd', { objs = armed.group }) end
  armed = nil
end

-- a prefab's preview: every object of it, following the crosshair together
local groupSeq = 0
local function startGroup()
  if not (armed and armed.prefab and armed.items and #armed.items > 0) then return end
  groupSeq = groupSeq + 1
  armed.groupSeq = groupSeq
  core.sendGlobalEvent('WsGhostGroupStart', { items = armed.items, player = self, seq = groupSeq })
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
  if e.lib and e.fresh then
    ui.showMessage(name .. ' was added to your Library after the game started. Start the game again to use it.')
    return
  end
  if e.lib then
    -- your own model: the Workshop makes its record in your mod, then readies it here
    say('libarm\t%s', e.id)
    closeMenu()
    ui.showMessage('Getting ' .. name .. ' ready...')
    return
  end
  if e.prefab then
    disarm()
    armed = { prefab = e.id, id = '', name = name, yaw = self.rotation:getYaw() + math.pi, lift = 0, items = e.items }
    closeMenu()
    startGroup()
    refreshHud()
    ui.showMessage('Placing the prefab ' .. name .. ': aim where you want it and press Shift+J.')
    return
  end
  if e.brush then
    disarm()
    armed = { brush = e.id, id = '', name = name, gap = e.gap, radius = 256 }
    say('disarm')                          -- (nothing single is readied in the Workshop now)
    closeMenu()
    refreshHud()
    ui.showMessage('Painting with ' .. name .. ': aim at the ground and press Shift+J.')
    return
  end
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
  -- (an icon made after the game started isn't in its files yet)
  if e.icon and vfs.fileExists(iconPath(e.icon)) then
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
  local list = menuState.tab == 'suggested' and menuState.suggested or menuState.tab == 'library' and libItems
    or menuState.tab == 'prefabs' and prefabItems or menuState.tab == 'brushes' and brushItems or menuState.results
  local rows = {}
  if menuState.tab == 'suggested' and #list == 0 then
    rows[1] = label('No suggestions for this place yet. Try Search.', 15, DIM)
  elseif menuState.tab == 'library' and #list == 0 then
    rows[1] = label('Nothing in your Library yet: add models on the Library page in the Workshop.', 15, DIM)
  elseif menuState.tab == 'prefabs' and #list == 0 then
    rows[1] = label('No prefabs yet: select a few objects in the Workshop and save them as a prefab.', 15, DIM)
  elseif menuState.tab == 'brushes' and #list == 0 then
    rows[1] = label('No brushes here: make your own with + New brush in the Workshop\'s Scatter tool.', 15, DIM)
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
              button('My Library', menuState.tab == 'library', function() menuState.tab = 'library'; renderMenu() end),
              button('Prefabs', menuState.tab == 'prefabs', function() menuState.tab = 'prefabs'; renderMenu() end),
              button('Brushes', menuState.tab == 'brushes', function() menuState.tab = 'brushes'; renderMenu() end),
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
    if res.hitObject == held or (res.hitObject and res.hitObject.recordId == 'player') then return end   -- the object itself, or you
    local pos = res.hitPos
    -- (the gap from its origin to its bottom grows and shrinks with its size)
    if h.bottomOffset then pos = util.vector3(pos.x, pos.y, pos.z + h.bottomOffset * (h.scale or 1) / (h.origScale or 1)) end
    pos = util.vector3(pos.x, pos.y, pos.z + (h.lift or 0))
    h.target = pos
    core.sendGlobalEvent('WsGrabMove', { obj = held, pos = pos, yaw = h.yaw, scale = h.scale })
  end
  aimBusy = true
  -- skip the player too: in third-person view the aim passes through your own character
  local ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to, { ignore = { held, self } })
  if not ok then ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to, { ignore = held }) end
  if not ok then
    ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to)
    if not ok then aimBusy = false end
  end
end

-- the same for a prefab's preview: the whole group moves (and turns) around the spot aimed at
local function followAimGroup(h)
  if aimBusy or not h or not h.group then return end
  local from = camera.getPosition()
  local dir = camera.viewportToWorldVector(util.vector2(0.5, 0.5))
  local to = from + dir * 6000
  local grp = h.group
  local skip = { self }
  for _, g in ipairs(grp) do skip[#skip + 1] = g.obj end
  local function onHit(res)
    aimBusy = false
    if h.group ~= grp or not (res and res.hit and res.hitPos) then return end
    if res.hitObject and res.hitObject.recordId == 'player' then return end
    for _, g in ipairs(grp) do if res.hitObject == g.obj then return end end
    local pos = util.vector3(res.hitPos.x, res.hitPos.y, res.hitPos.z + (h.lift or 0))
    h.target = pos
    core.sendGlobalEvent('WsGhostGroupMove', { objs = grp, pos = pos, yaw = h.yaw })
  end
  aimBusy = true
  local ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to, { ignore = skip })
  if not ok then ok = pcall(nearby.asyncCastRenderingRay, async:callback(onHit), from, to, { ignore = self }) end
  if not ok then aimBusy = false end
end

-- bigger or smaller, 5% a step (the game's own limits: half to twice the size)
local function resize(h, dir)
  h.scale = math.max(0.5, math.min(2.0, math.floor(((h.scale or 1) * (dir > 0 and 1.05 or 1 / 1.05)) * 100 + 0.5) / 100))
  if h.obj and h.target then
    core.sendGlobalEvent('WsGrabMove', { obj = h.obj, pos = h.target, yaw = h.yaw, scale = h.scale })
  end
  refreshHud()
end

-- a light's colour, from a small window in game (Shift+L while looking at it). The Workshop makes a
-- light of that colour (the game keeps colour in the kind of light, not in each lamp) and swaps it in.
local SWATCHES = {
  { 'Warm', 255, 200, 140 }, { 'Candle', 255, 160, 80 }, { 'White', 235, 240, 255 }, { 'Red', 255, 70, 50 },
  { 'Green', 90, 255, 110 }, { 'Blue', 90, 140, 255 }, { 'Purple', 190, 90, 255 }, { 'Teal', 70, 230, 210 },
}
local lightMenu = nil
local function closeLightMenu()
  if lightMenu then lightMenu:destroy(); lightMenu = nil end
  if I.UI.getMode() == I.UI.MODE.Interface then I.UI.removeMode(I.UI.MODE.Interface) end
end
local function openLightMenu(o)
  if lightMenu or menu then return end
  local kind, name = cellInfo(o.cell)
  local function send(r, g, b, mul, label)
    say('lightcolor\t%s\t%.1f\t%.1f\t%.1f\t%s\t%s\t%d\t%d\t%d\t%.3f', o.recordId, o.position.x, o.position.y, o.position.z,
        kind, name, r, g, b, mul)
    closeLightMenu()
    ui.showMessage('Workshop: ' .. label .. '...')
  end
  local row = {}
  for _, s in ipairs(SWATCHES) do
    local col = util.color.rgb(s[2] / 255, s[3] / 255, s[4] / 255)
    row[#row + 1] = {
      template = I.MWUI.templates.box,
      content = ui.content({ { type = ui.TYPE.Text, props = { text = '  ' .. s[1] .. '  ', textSize = 16, textColor = col },
        events = { mouseClick = async:callback(function() send(s[2], s[3], s[4], 1, 'making it ' .. s[1]:lower()) end) } } }),
    }
  end
  lightMenu = ui.create({
    layer = 'Windows', template = I.MWUI.templates.boxSolid,
    props = { relativePosition = util.vector2(0.5, 0.5), anchor = util.vector2(0.5, 0.5) },
    content = ui.content({ { type = ui.TYPE.Flex, props = { position = util.vector2(8, 8) }, content = ui.content({
      label('Workshop: colour of this light (' .. o.recordId .. ')', 18, GOLD),
      label('Only this lamp changes. Undo in the Workshop or with Shift+Z.', 14, DIM),
      { type = ui.TYPE.Flex, props = { horizontal = true }, content = ui.content(row) },
      { type = ui.TYPE.Flex, props = { horizontal = true }, content = ui.content({
        button('Brighter (reaches further)', false, function() send(-1, -1, -1, 1.3, 'making it brighter') end),
        button('Dimmer', false, function() send(-1, -1, -1, 0.75, 'making it dimmer') end),
        button('Close', false, function() closeLightMenu() end) }) },
      label(' ', 8) }) } }),
  })
  I.UI.setMode(I.UI.MODE.Interface, { windows = {} })
end

-- a brush in game: spots spread over a patch of ground around where you aim, each set on the surface
-- found right there (the Workshop picks what goes on each, from the brush, and saves them)
local function paintBrush()
  local res = lookRay()
  if not (res.hit and res.hitPos) or (res.hitNormal and res.hitNormal.z < 0.6) then
    ui.showMessage('Workshop: aim at the ground or a floor to paint'); return
  end
  local c, R = res.hitPos, armed.radius or 256
  local gap = math.max(40, armed.gap or 200)
  local tries = math.max(1, math.min(80, math.floor(math.pi * R * R / (gap * gap) + 0.5)))
  local pts, near = {}, {}
  for _ = 1, tries * 3 do
    if #pts >= tries then break end
    local a, d = math.random() * math.pi * 2, math.sqrt(math.random()) * R
    local x, y = c.x + math.cos(a) * d, c.y + math.sin(a) * d
    local okSpot = true
    for _, p in ipairs(near) do
      if (p[1] - x) ^ 2 + (p[2] - y) ^ 2 < (gap * 0.7) ^ 2 then okSpot = false; break end
    end
    if okSpot then
      -- looked at from the camera, like aiming at that spot (a ray from above would hit a ceiling indoors)
      local eye = camera.getPosition()
      local to = util.vector3(x, y, c.z)
      local okR, hit = pcall(nearby.castRay, eye, eye + (to - eye) * 1.6, { ignore = self })
      -- only ground or floor right at the spot: skipped when a wall or something else is in the way
      -- (the line stopped short of it), when it lands on a wall's side, or far above / below the aim
      local near_ = okR and hit and hit.hit and hit.hitPos and
        ((hit.hitPos.x - x) ^ 2 + (hit.hitPos.y - y) ^ 2) < 32 ^ 2 and math.abs(hit.hitPos.z - c.z) < 96 and
        not (hit.hitNormal and hit.hitNormal.z < 0.6)
      if near_ and not (hit.hitObject and hit.hitObject.type == types.NPC) then
        pts[#pts + 1] = string.format('%.0f,%.0f,%.0f', hit.hitPos.x, hit.hitPos.y, hit.hitPos.z)
        near[#near + 1] = { x, y }
      end
    end
  end
  if #pts == 0 then ui.showMessage('Workshop: no ground to paint there'); return end
  local kind, name = cellInfo(self.cell)
  say('placebrush\t%s\t%s\t%s\t%s', armed.brush, kind, name, table.concat(pts, ';'))
  ui.showMessage(string.format('Workshop: painting %d things...', #pts))
end

local function startGrab()
  local res = lookRay()
  local o = res.hitObject
  if not o then ui.showMessage('Workshop: look at the object you want to move'); return end
  if o.type == types.NPC and o.recordId == 'player' then return end
  -- walls and floors are easy to grab by mistake: ask for a second press
  local bb = boundingBox(o)
  -- (a room piece is a 256-wide square; furniture is narrower one way or the other)
  local big = bb and (bb.halfSize.x > 200 or bb.halfSize.y > 200 or (bb.halfSize.x > 110 and bb.halfSize.y > 110))
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
           name = (okName and n and n ~= '' and n) or o.recordId, scale = o.scale or 1, origScale = o.scale or 1 }
  if bb then grab.bottomOffset = o.position.z - (bb.center.z - bb.halfSize.z) end
  core.sendGlobalEvent('WsGrabStart', { obj = o })
  refreshHud()
end

local function dropGrab(cancel)
  if not grab then return end
  local o = grab.obj
  if cancel then
    core.sendGlobalEvent('WsGrabMove', { obj = o, pos = grab.orig, yaw = grab.origYaw, scale = grab.origScale })
  else
    local kind, name, gx, gy = cellInfo(o.cell)
    local p = grab.target or o.position
    say('move\t%s\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s\t%d\t%d\t%.3f', o.recordId,
        grab.orig.x, grab.orig.y, grab.orig.z, p.x, p.y, p.z, grab.yaw,
        kind, name, gx, gy, grab.scale or 1)
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
  elseif armed and armed.group then
    followAimGroup(armed)
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
  -- bigger / smaller while holding or placing something
  if h and not h.prefab and not h.brush and ((K.Equals and key.code == K.Equals) or (K.Minus and key.code == K.Minus) or
      (K.NP_Plus and key.code == K.NP_Plus) or (K.NP_Minus and key.code == K.NP_Minus)) then
    resize(h, (key.code == K.Equals or key.code == K.NP_Plus) and 1 or -1)
    return
  end
  if armed and armed.brush and (key.code == K.PageUp or key.code == K.PageDown) then
    -- a brush: a bigger or smaller patch
    armed.radius = math.max(64, math.min(1024, (armed.radius or 256) * (key.code == K.PageUp and 1.25 or 0.8)))
    refreshHud()
    return
  end
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
    if armed and armed.brush then
      paintBrush()
    elseif armed and armed.prefab then
      -- where the preview stands (or, without one, where you aim)
      local res = lookRay(armed.group and armed.group[1] and armed.group[1].obj or nil)
      local p = armed.group and armed.target or (res.hit and res.hitPos and
        util.vector3(res.hitPos.x, res.hitPos.y, res.hitPos.z + (armed.lift or 0)))
      if p then
        say('placeprefab\t%s\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s', armed.prefab, p.x, p.y, p.z, armed.yaw, kind, name)
        ui.showMessage('Workshop: placing ' .. armed.name)
        if armed.group then
          -- the preview stays put until the real objects show up, and a fresh one follows the aim
          core.sendGlobalEvent('WsGhostGroupDrop', { objs = armed.group })
          armed.group, armed.target = nil, nil
          startGroup()
        end
      else
        ui.showMessage('Workshop: look at a floor or surface to place it')
      end
    elseif armed and armed.obj and armed.target then
      -- place exactly where the preview stands, turned the way it's turned
      local p = armed.target
      say('placeat\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s\t%d\t%d\t%s\texact\t%.3f', p.x, p.y, p.z, armed.yaw,
          kind, name, gx, gy, armed.id, armed.scale or 1)
      core.sendGlobalEvent('WsGhostDrop', { obj = armed.obj })
      armed.obj, armed.target = nil, nil
      core.sendGlobalEvent('WsGhostStart', { id = armed.id, player = self })   -- a fresh preview for the next one
      ui.showMessage('Workshop: placed ' .. armed.name)
    else
      local res = lookRay()
      if res.hit and res.hitPos then
        say('placeat\t%.1f\t%.1f\t%.1f\t%.4f\t%s\t%s\t%d\t%d\t%s\t\t%.3f', res.hitPos.x, res.hitPos.y,
            res.hitPos.z + (armed and armed.lift or 0), armed and armed.yaw or self.rotation:getYaw() + math.pi,
            kind, name, gx, gy, armed and armed.id or '', armed and armed.scale or 1)
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
  elseif key.code == K.L then
    local o = lookRay().hitObject
    if o and o.type == types.Light then openLightMenu(o)
    else ui.showMessage('Workshop: look at a light (a lamp, candle or torch) to change its colour') end
  end
end

local function onMouseWheel(vertical)
  local h = grab or armed
  if h and vertical and vertical ~= 0 then
    if input.isCtrlPressed and input.isCtrlPressed() and not h.prefab and not h.brush then
      resize(h, vertical > 0 and 1 or -1)
      return
    end
    local fine = input.isShiftPressed and input.isShiftPressed()
    h.yaw = (h.yaw or 0) + (vertical > 0 and 1 or -1) * math.rad(fine and 1 or 15)
    if h.obj and h.target then
      core.sendGlobalEvent('WsGrabMove', { obj = h.obj, pos = h.target, yaw = h.yaw, scale = h.scale })
    elseif h.group and h.target then
      core.sendGlobalEvent('WsGhostGroupMove', { objs = h.group, pos = h.target, yaw = h.yaw })
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
      if lightMenu and data.newMode == nil then
        lightMenu:destroy(); lightMenu = nil
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
    -- a prefab's preview objects (those the game could make)
    WsGhostGroupReady = function(data)
      if not (armed and armed.prefab and armed.groupSeq == data.seq) or not data.objs or #data.objs == 0 then
        if data.objs and #data.objs > 0 then core.sendGlobalEvent('WsGhostGroupEnd', { objs = data.objs }) end
        return
      end
      armed.group = data.objs
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
