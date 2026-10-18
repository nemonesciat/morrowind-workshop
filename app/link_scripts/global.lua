-- Morrowind Workshop live link (global side).
-- Reads workshop_link/state.txt (written by the Workshop) and makes the running
-- game match it: places, moves, hides and restores objects, and teleports the
-- player on request. Talks back to the Workshop by printing [WSLINK] lines to
-- openmw.log. Only loaded when the game is started from the Workshop.

local world = require('openmw.world')
local util = require('openmw.util')
local vfs = require('openmw.vfs')
local types = require('openmw.types')
local core = require('openmw.core')
local I = require('openmw.interfaces')

local STATE = 'workshop_link/state.txt'
local POLL = 0.5

local live = {}        -- refkey -> { obj, kind, orig = {pos, rot, scale, enabled} }
local wanted = {}      -- refkey -> parsed entry (current state file)
local lastText = nil
local lastVersion = -1
local lastTp = nil
local timer = 0
local cleanupPending = nil
local failed = {}      -- refkey -> true when it could not be applied (don't retry every frame)
local ghosts = {}      -- preview objects following the crosshair: object id -> object (by id: an object
                       -- passed in an event is a new handle, so it can't be a table key itself)
local placedGhosts = {}  -- previews set down with Shift+J, waiting for the Workshop to confirm: { obj, t }
local clock = 0
local lastArm = nil
local doorDest = {}    -- object id -> where a door placed while the game runs leads (it has no link of its own)
local doorHandler = false
local librecs = {}     -- Library records of the mod (lower-case id -> { tag, model, name })
local alias = {}       -- Library record made after the game started -> the stand-in record made for it here
local function say(fmt, ...)
  print('[WSLINK] ' .. string.format(fmt, ...))
end

-- Objects of a record: the game's own, or (for a Library model your mod got after the game started)
-- a stand-in record with the same model, made here once
local TYPES = { STAT = 'Static', ACTI = 'Activator', CONT = 'Container', MISC = 'Miscellaneous', DOOR = 'Door', LIGH = 'Light' }
local function create(rid)
  local ok, obj = pcall(world.createObject, rid, 1)
  if ok and obj then return obj end
  local lr = librecs[rid:lower()]
  if not lr then return nil end
  if not alias[rid:lower()] then
    local made = nil
    -- (a light is tried with all its settings, then fewer, in case this OpenMW doesn't take some)
    local tries = lr.tag == 'LIGH' and { { 'Light', 3 }, { 'Light', 2 }, { 'Light', 1 }, { 'Static', 0 } }
      or { { TYPES[lr.tag] or 'Static', 0 }, { 'Static', 0 } }
    for _, try in ipairs(tries) do
      local tname, level = try[1], try[2]
      local t = types[tname]
      local okR, rec = pcall(function()
        local fields = { model = lr.model }
        if tname ~= 'Static' then fields.name = lr.name ~= '' and lr.name or rid end
        if tname == 'Miscellaneous' then fields.value = 1; fields.weight = 1 end
        if tname == 'Container' then fields.weight = 0; fields.capacity = 100 end
        if tname == 'Light' and lr.radius then
          local f = lr.flags or 1
          fields.radius = lr.radius
          fields.color = util.color.rgb(lr.r / 255, lr.g / 255, lr.b / 255)
          if level >= 2 then
            fields.isDynamic = f % 2 == 1
            fields.isFlicker = math.floor(f / 8) % 2 == 1
            fields.isFire = math.floor(f / 16) % 2 == 1
            fields.isFlickerSlow = math.floor(f / 64) % 2 == 1
            fields.isPulse = math.floor(f / 128) % 2 == 1
            fields.isPulseSlow = math.floor(f / 256) % 2 == 1
            fields.isCarriable = math.floor(f / 2) % 2 == 1
            fields.duration = -1
            fields.weight = 0
            fields.value = 0
          end
          if level >= 3 and lr.sound then fields.sound = lr.sound end
        end
        if fields.model == '' then fields.model = nil end
        return world.createRecord(t.createRecordDraft(fields))
      end)
      if okR and rec then made = rec; break end
    end
    if not made then return nil end
    alias[rid:lower()] = made.id
    say('alias\t%s\t%s', made.id, rid)
  end
  local ok2, obj2 = pcall(world.createObject, alias[rid:lower()], 1)
  if ok2 then return obj2 end
  return nil
end

-- An object being moved this frame has a count of 0 until the move is done (end of the frame), and
-- can't be removed until then: such ones are removed on a later frame.
local toRemove = {}
local function removeSoon(o)
  if not (o and o:isValid()) then return end
  if (o.count or 0) > 0 and pcall(function() o:remove() end) then return end
  toRemove[#toRemove + 1] = { obj = o, tries = 0 }
end
local function removeLater()
  for i = #toRemove, 1, -1 do
    local r = toRemove[i]
    r.tries = r.tries + 1
    if not r.obj:isValid() or r.tries > 120 then
      table.remove(toRemove, i)
    elseif (r.obj.count or 0) > 0 and pcall(function() r.obj:remove() end) then
      table.remove(toRemove, i)
    end
  end
end

local function same(objRid, rid)
  return objRid == rid or (alias[rid] ~= nil and objRid:lower() == alias[rid]:lower())
end

local function split(s, sep)
  local out = {}
  for part in (s .. sep):gmatch('(.-)' .. sep) do out[#out + 1] = part end
  return out
end

local function makeRot(rx, ry, rz)
  return util.transform.rotateZ(rz) * util.transform.rotateY(ry) * util.transform.rotateX(rx)
end

local function readState()
  if not vfs.fileExists(STATE) then return nil end
  local ok, text = pcall(function()
    local f = vfs.open(STATE)
    local t = f:read('*a')
    f:close()
    return t
  end)
  if ok then return text end
  return nil
end

local function getCell(e)
  if e.kind == 'int' then return world.getCellByName(e.cellName) end
  return world.getExteriorCell(e.gx, e.gy)
end

local function playerNear(e)
  local player = world.players[1]
  if not player then return false end
  local pc = player.cell
  if e.kind == 'int' then
    return (not pc.isExterior) and pc.name:lower() == e.cellName:lower()
  end
  return pc.isExterior and math.abs(pc.gridX - e.gx) <= 1 and math.abs(pc.gridY - e.gy) <= 1
end

-- ------------------------------------------------------------------ quest testing
-- The Workshop sends one-off commands ("cmd" lines: set a quest stage, give an item...)
-- and says what to keep it told about ("watch" lines: global variables, item counts).
-- Quest stages are always reported.
local lastCmd = nil
local watch = { global = {}, item = {} }
local told = { quest = {}, global = {}, item = {} }
local reportTimer = 0

local function questOf(player, qid)
  local qs = types.Player.quests(player)
  return qs[qid] or qs[qid:lower()]
end

local function runCommand(c)
  local player = world.players[1]
  if not player then return 'no player' end
  local v, a, b = c.verb, c.args[1], c.args[2]
  if v == 'journal' then
    questOf(player, a):addJournalEntry(tonumber(b))
  elseif v == 'stage' then
    questOf(player, a).stage = tonumber(b)
  elseif v == 'finish' then
    questOf(player, a).finished = b == '1'
  elseif v == 'reset' then
    local q = questOf(player, a)
    q.stage = 0
    q.finished = false
  elseif v == 'global' then
    world.mwscript.getGlobalVariables(player)[a] = tonumber(b)
  elseif v == 'give' then
    world.createObject(a, math.max(1, tonumber(b) or 1)):moveInto(types.Actor.inventory(player))
  elseif v == 'take' then
    local left = math.max(1, tonumber(b) or 1)
    for _, o in ipairs(types.Actor.inventory(player):findAll(a)) do
      if left <= 0 then break end
      local n = math.min(left, o.count)
      o:remove(n)
      left = left - n
    end
  elseif v == 'topic' then
    types.Player.addTopic(player, a)
  else
    return 'unknown command ' .. tostring(v)
  end
  return nil
end

local function runCommands(cmds)
  local top = 0
  for _, c in ipairs(cmds) do top = math.max(top, c.seq) end
  if lastCmd == nil then lastCmd = top; return end      -- already there when the game started
  table.sort(cmds, function(x, y) return x.seq < y.seq end)
  for _, c in ipairs(cmds) do
    if c.seq > lastCmd then
      lastCmd = c.seq
      local ok, err = pcall(runCommand, c)
      if not ok then err = tostring(err) end
      say('done\t%d\t%s', c.seq, (err and err:gsub('[\t\r\n]', ' ')) or 'ok')
    end
  end
end

-- tell the Workshop what changed since last time
local function report()
  local player = world.players[1]
  if not player then return end
  pcall(function()
    for _, q in pairs(types.Player.quests(player)) do
      local s = string.format('%d\t%d', q.stage or 0, q.finished and 1 or 0)
      if told.quest[q.id] ~= s then
        told.quest[q.id] = s
        say('quest\t%s\t%s', q.id, s)
      end
    end
  end)
  local okG, globs = pcall(world.mwscript.getGlobalVariables, player)
  for name in pairs(watch.global) do
    local ok, val = pcall(function() return globs[name] end)
    local s = (okG and ok and val ~= nil) and string.format('%.7g', val) or '?'
    if told.global[name] ~= s then
      told.global[name] = s
      say('global\t%s\t%s', name, s)
    end
  end
  local inv = types.Actor.inventory(player)
  for id in pairs(watch.item) do
    local ok, n = pcall(function() return inv:countOf(id) end)
    local s = ok and tostring(n) or '?'
    if told.item[id] ~= s then
      told.item[id] = s
      say('item\t%s\t%s', id, s)
    end
  end
end

local function parse(text)
  local entries, version, tp, arm = {}, 0, nil, nil
  local cmds, newWatch = {}, { global = {}, item = {} }
  for line in text:gmatch('[^\r\n]+') do
    local f = split(line, '\t')
    if f[1] == 'cmd' then
      cmds[#cmds + 1] = { seq = tonumber(f[2]) or 0, verb = f[3], args = { f[4], f[5] } }
    elseif f[1] == 'watch' and newWatch[f[2]] and f[3] and f[3] ~= '' then
      newWatch[f[2]][f[3]] = true
    elseif f[1] == 'version' then
      version = tonumber(f[2]) or 0
    elseif f[1] == 'librec' and f[2] and f[2] ~= '' then
      librecs[f[2]:lower()] = { tag = f[3], model = f[4], name = f[5] or '', radius = tonumber(f[6]),
                                r = tonumber(f[7]) or 255, g = tonumber(f[8]) or 255, b = tonumber(f[9]) or 255,
                                flags = tonumber(f[10]), sound = f[11] ~= '' and f[11] or nil }
    elseif f[1] == 'arm' then
      arm = { seq = tonumber(f[2]), id = f[3], name = f[4] }
    elseif f[1] == 'tp' then
      tp = { seq = tonumber(f[2]), kind = f[3], cellName = f[4], gx = tonumber(f[5]), gy = tonumber(f[6]),
             x = tonumber(f[7]), y = tonumber(f[8]), z = tonumber(f[9]), yaw = tonumber(f[10]) }
    elseif f[1] == 'ref' then
      -- ref key action recordId kind cellName gx gy | orig x y z rx ry rz s | target x y z rx ry rz s
      local e = { key = f[2], action = f[3], recordId = f[4]:lower(), kind = f[5], cellName = f[6],
                  gx = tonumber(f[7]), gy = tonumber(f[8]) }
      if f[9] ~= '-' then
        e.orig = { util.vector3(tonumber(f[9]), tonumber(f[10]), tonumber(f[11])),
                   makeRot(tonumber(f[12]), tonumber(f[13]), tonumber(f[14])), tonumber(f[15]) }
      end
      if f[16] ~= '-' then
        e.target = { util.vector3(tonumber(f[16]), tonumber(f[17]), tonumber(f[18])),
                     makeRot(tonumber(f[19]), tonumber(f[20]), tonumber(f[21])), tonumber(f[22]) }
      end
      -- | door kind cellName gx gy x y z rz : where a door leads
      if f[23] == 'door' then
        e.door = { kind = f[24], cellName = f[25], gx = tonumber(f[26]), gy = tonumber(f[27]),
                   pos = util.vector3(tonumber(f[28]), tonumber(f[29]), tonumber(f[30])), rz = tonumber(f[31]) or 0 }
      end
      entries[e.key] = e
    end
  end
  runCommands(cmds)
  watch = newWatch
  return version, entries, tp, arm
end

local adopted = {}     -- objects picked up in game with Shift+G: { obj, pos, angles }

local function findOriginal(e)
  if not e.orig then return nil end
  -- something the player is moving / has moved by hand: match where it originally stood
  for i, a in ipairs(adopted) do
    if a.obj:isValid() and same(a.obj.recordId, e.recordId) and (a.pos - e.orig[1]):length() < 24 then
      table.remove(adopted, i)
      return a.obj, a
    end
  end
  local cell = getCell(e)
  if not cell then return nil end
  local best, bestD = nil, 24
  for _, o in ipairs(cell:getAll()) do
    if same(o.recordId, e.recordId) then
      local d = (o.position - e.orig[1]):length()
      if d < bestD then best, bestD = o, d end
    end
  end
  return best
end

local function place(obj, cell, t)
  obj:teleport(cell, t[1], { rotation = t[2], onGround = false })
  if t[3] and math.abs((obj.scale or 1) - t[3]) > 0.001 then obj:setScale(t[3]) end
end

local putBack

-- Put one entry into the state the Workshop asked for. Returns true when done.
local function apply(e)
  if not playerNear(e) then return false end
  local cell = getCell(e)
  if not cell then return true end
  local l = live[e.key]
  if e.action == 'new' then
    -- a preview the player just set down with Shift+J becomes the real thing (no flicker, no double)
    if not (l and l.obj:isValid()) then
      for i, gh in ipairs(placedGhosts) do
        if gh.obj:isValid() and same(gh.obj.recordId, e.recordId) and (gh.obj.position - e.target[1]):length() < 48 then
          table.remove(placedGhosts, i)
          live[e.key] = { obj = gh.obj, kind = 'created' }
          l = live[e.key]
          break
        end
      end
    end
    if l and l.obj:isValid() then
      place(l.obj, cell, e.target)
    else
      local obj = create(e.recordId)
      if not obj then
        say('error\tcannot create %s (new records only appear after restarting the game)', e.recordId)
        failed[e.key] = true
        return true
      end
      place(obj, cell, e.target)
      live[e.key] = { obj = obj, kind = 'created' }
    end
    doorDest[live[e.key].obj.id] = e.door
    return true
  end
  -- mod / del: an object that already exists in the game. (Something made here for this entry that
  -- is now a different object, e.g. a lamp swapped back: that goes, and the original is found again.)
  if l and l.kind == 'created' and l.obj:isValid() and not same(l.obj.recordId, e.recordId) then
    putBack(l)
    live[e.key] = nil
    l = nil
  end
  local obj = l and l.obj
  if not (obj and obj:isValid()) then
    local a
    obj, a = findOriginal(e)
    if not obj then
      say('error\tcould not find %s to change it', e.recordId)
      failed[e.key] = true
      return true
    end
    if a then
      live[e.key] = { obj = obj, kind = 'existing', orig = { a.pos, a.angles, a.scale, true } }
    else
      local z, y, x = obj.rotation:getAnglesZYX()
      live[e.key] = { obj = obj, kind = 'existing',
                      orig = { obj.position, { x, y, z }, obj.scale or 1, obj.enabled } }
    end
  end
  if e.action == 'del' then
    obj.enabled = false
  else
    obj.enabled = true
    place(obj, cell, e.target)
    -- a door whose destination was changed in the Workshop leads there from now on
    doorDest[obj.id] = e.door
  end
  return true
end

putBack = function(l)
  if not (l.obj and l.obj:isValid()) then return end
  if l.kind == 'created' then
    doorDest[l.obj.id] = nil
    removeSoon(l.obj)
  elseif l.orig then
    doorDest[l.obj.id] = nil
    local a = l.orig[2]
    l.obj.enabled = l.orig[4] ~= false
    l.obj:teleport(l.obj.cell, l.orig[1], { rotation = makeRot(a[1], a[2], a[3]), onGround = false })
    if math.abs((l.obj.scale or 1) - l.orig[3]) > 0.001 then l.obj:setScale(l.orig[3]) end
  end
end

-- Undo a live change that the Workshop no longer wants.
local function revert(key)
  local l = live[key]
  if not l then return end
  putBack(l)
  live[key] = nil
end

local pending = {}

local function sync(text)
  local version, entries, tp, arm = parse(text)
  -- requests already there when the game started are old: skip those, but not ones that come later
  if lastArm == nil then lastArm = arm and arm.seq or 0 end
  if lastTp == nil then lastTp = tp and tp.seq or 0 end
  -- something chosen in the Workshop to place in game
  if arm and arm.seq then
    if arm.seq > lastArm then
      lastArm = arm.seq
      local player = world.players[1]
      if player then
        if arm.id and arm.id ~= '' then player:sendEvent('WsArm', { id = arm.id, name = arm.name })
        else player:sendEvent('WsDisarm', {}) end            -- "stop placing" from the Workshop
      end
    end
  end
  -- teleport requests run once each
  if tp and tp.seq then
    if tp.seq > lastTp then
      lastTp = tp.seq
      local player = world.players[1]
      local cell = tp.kind == 'int' and world.getCellByName(tp.cellName) or world.getExteriorCell(tp.gx, tp.gy)
      if player and cell then
        player:teleport(cell, util.vector3(tp.x, tp.y, tp.z), { rotation = util.transform.rotateZ(tp.yaw or 0) })
        say('teleported\t%d', tp.seq)
      end
    end
  end
  if version == lastVersion then return end
  lastVersion = version
  for key in pairs(live) do
    if not entries[key] then revert(key) end
  end
  wanted = entries
  failed = {}
  pending = {}
  for key, e in pairs(entries) do pending[key] = e end
  say('received\t%d', version)
end

local function work()
  local done = 0
  for key, e in pairs(pending) do
    local ok, finished = pcall(apply, e)
    if not ok then
      say('error\t%s', tostring(finished))
      pending[key] = nil
    elseif finished then
      pending[key] = nil
      done = done + 1
    end
    if done >= 40 then break end      -- spread big changes over a few frames
  end
  if done > 0 and next(pending) == nil then say('applied\t%d', lastVersion) end
end

-- A door placed while the game runs: take whoever opens it where the Workshop says it leads.
local function useDoor(door, actor)
  local d = doorDest[door.id]
  if not d then return end                      -- an ordinary door: the game handles it
  if d.kind == 'none' then return false end     -- its link was removed in the Workshop
  local cell = d.kind == 'int' and world.getCellByName(d.cellName) or world.getExteriorCell(d.gx, d.gy)
  if not cell then return end
  pcall(function() core.sound.playSound3d(types.Door.record(door).openSound, door) end)
  actor:teleport(cell, d.pos, { rotation = util.transform.rotateZ(d.rz) })
  return false
end

local function onUpdate(dt)
  if not doorHandler and I.Activation then
    doorHandler = true
    I.Activation.addHandlerForType(types.Door, useDoor)
  end
  clock = clock + dt
  if cleanupPending then
    for _, l in ipairs(cleanupPending) do pcall(putBack, l) end
    cleanupPending = nil
  end
  -- previews the Workshop never confirmed (e.g. it refused the placement)
  for i = #placedGhosts, 1, -1 do
    local gh = placedGhosts[i]
    if not gh.obj:isValid() then table.remove(placedGhosts, i)
    elseif clock - gh.t > 15 then removeSoon(gh.obj); table.remove(placedGhosts, i) end
  end
  removeLater()
  timer = timer + dt
  if timer >= POLL then
    timer = 0
    local text = readState()
    if text and text ~= lastText then
      lastText = text
      sync(text)
    end
    -- objects in cells the player just walked into
    if next(pending) == nil then
      for key, e in pairs(wanted) do
        if not live[key] and not failed[key] and playerNear(e) then pending[key] = e end
      end
    end
  end
  if next(pending) ~= nil then work() end
  reportTimer = reportTimer + dt
  if reportTimer >= 1 then
    reportTimer = 0
    report()
  end
end

return {
  engineHandlers = {
    onUpdate = onUpdate,
    -- Live changes are only a preview. If the game gets saved anyway, remember
    -- what we touched so it can be put back when that save is loaded.
    onSave = function()
      local list = {}
      for _, l in pairs(live) do list[#list + 1] = l end
      for _, o in pairs(ghosts) do list[#list + 1] = { obj = o, kind = 'created' } end
      for _, gh in ipairs(placedGhosts) do list[#list + 1] = { obj = gh.obj, kind = 'created' } end
      return { live = list }
    end,
    onLoad = function(data)
      if data and data.live then cleanupPending = data.live end
      say('hello\tloaded')
    end,
    onInit = function() say('hello\tnew') end,
  },
  eventHandlers = {
    -- Shift+G in game: remember where the object stood, then move it with the player's aim
    WsGrabStart = function(data)
      local o = data.obj
      if not (o and o:isValid()) then return end
      for _, l in pairs(live) do
        if l.obj == o then return end            -- already tracked by the Workshop
      end
      for _, a in ipairs(adopted) do
        if a.obj == o then return end
      end
      local z, y, x = o.rotation:getAnglesZYX()
      adopted[#adopted + 1] = { obj = o, pos = o.position, angles = { x, y, z }, scale = o.scale or 1 }
    end,
    -- a preview of the object being placed
    WsGhostStart = function(data)
      local player = data.player or world.players[1]
      local obj = create(data.id)
      if not obj then
        player:sendEvent('WsGhostFailed', { id = data.id })
        return
      end
      -- start it just in front of the player (it follows the crosshair from the next frame)
      local okF, pos = pcall(function() return player.position + (player.rotation * util.vector3(0, 150, 0)) end)
      if not okF or not pos then pos = player.position end
      obj:teleport(player.cell, pos, { onGround = false })
      ghosts[obj.id] = obj
      player:sendEvent('WsGhostReady', { obj = obj, id = data.id })
    end,
    WsGhostEnd = function(data)
      local o = data.obj
      if o and ghosts[o.id] then
        ghosts[o.id] = nil
        removeSoon(o)
      end
    end,
    WsGhostDrop = function(data)
      local o = data.obj
      if o and ghosts[o.id] then
        ghosts[o.id] = nil
        placedGhosts[#placedGhosts + 1] = { obj = o, t = clock }
      end
    end,
    -- a prefab's preview: each of its objects the game can make, laid out as in the prefab
    WsGhostGroupStart = function(data)
      local player = data.player or world.players[1]
      local out = {}
      local okF, pos = pcall(function() return player.position + (player.rotation * util.vector3(0, 200, 0)) end)
      if not okF or not pos then pos = player.position end
      for _, it in ipairs(data.items or {}) do
        local obj = it.id and it.id ~= '' and create(it.id) or nil
        if obj then
          obj:teleport(player.cell, pos + util.vector3(it.dx, it.dy, it.dz), { onGround = false })
          ghosts[obj.id] = obj
          out[#out + 1] = { obj = obj, dx = it.dx, dy = it.dy, dz = it.dz, rz = it.rz }
        end
      end
      player:sendEvent('WsGhostGroupReady', { objs = out, seq = data.seq })
    end,
    WsGhostGroupMove = function(data)
      local c, s = math.cos(data.yaw or 0), math.sin(data.yaw or 0)
      for _, g in ipairs(data.objs or {}) do
        local o = g.obj
        if o and o:isValid() then
          -- turned clockwise round the middle, like the Workshop places them
          local p = data.pos + util.vector3(g.dx * c + g.dy * s, -g.dx * s + g.dy * c, g.dz)
          if (o.count or 0) > 0 then                    -- (still on its way from the last move: skip a frame)
            o:teleport(o.cell, p, { rotation = makeRot(0, 0, (g.rz or 0) + (data.yaw or 0)), onGround = false })
          end
        end
      end
    end,
    WsGhostGroupEnd = function(data)
      for _, g in ipairs(data.objs or {}) do
        local o = g.obj
        if o and ghosts[o.id] then
          ghosts[o.id] = nil
          removeSoon(o)
        end
      end
    end,
    WsGhostGroupDrop = function(data)
      for _, g in ipairs(data.objs or {}) do
        local o = g.obj
        if o and ghosts[o.id] then
          ghosts[o.id] = nil
          placedGhosts[#placedGhosts + 1] = { obj = o, t = clock }
        end
      end
    end,
    WsGrabMove = function(data)
      local o = data.obj
      if not (o and o:isValid() and data.pos) or (o.count or 0) == 0 then return end   -- (mid-move: next frame)
      local _, y, x = o.rotation:getAnglesZYX()
      o:teleport(o.cell, data.pos, { rotation = makeRot(x, y, data.yaw or 0), onGround = false })
      if data.scale and math.abs((o.scale or 1) - data.scale) > 0.001 then pcall(function() o:setScale(data.scale) end) end
    end,
  },
}
