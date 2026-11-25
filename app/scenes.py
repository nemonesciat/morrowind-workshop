"""The scene player: the mod's cutscenes (openmw-scene/1, kept in the mod by bridge.py) played in OpenMW by Lua the
Workshop writes beside the mod (project.lua_outputs), with the rest of its Lua.

Files, under scripts/<mod>/scene/:
  data.lua     every scene of the mod, as a Lua table (the scene files as they were sent, the trigger included)
  global.lua   the clock; actors found and set on their marks; clips, voices and the end; triggers; save and load
  player.lua   the camera (fixed and aimed shots, moves), fades and letterbox, music, controls, skip
  actor.lua    on each actor while a scene plays: its AI held, its clips, its effects

Played from outside with global events (any program, or the OpenMW Suite's live link for a preview):
  WsScene_Play {scene=id, t=0[, data=<a scene table>, mod=<this mod's slug>]}   WsScene_Pause / WsScene_Resume
  WsScene_Seek {t}   WsScene_Stop   WsScene_Skip      and the interface I.WorkshopScenes_<slug>
It says WsScene_Started {scene, mod} and WsScene_Ended {scene, mod, how}, and claims the camera with
CameraClaim {name} / CameraRelease {name} (another program's claim makes it let go until released).

Agreed rules (the Suite's authors and the user, 2026-11-25): the end always runs (finishing, skip, a save loaded
mid-scene, a missing actor); offsets are in the aimed actor's own frame (x right, y ahead, z up), at its aim height;
fixed shots are world positions with a compass yaw (0 north, clockwise) and a pitch (below 0 looks down)."""
import json
import re

VERSION = '1'


def lua_value(v, ind=''):
    """A JSON value as Lua source."""
    if v is None:
        return 'nil'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'
    nxt = ind + '  '
    if isinstance(v, (list, tuple)):
        if not v:
            return '{}'
        if all(isinstance(x, (int, float, str, bool)) for x in v):
            return '{' + ', '.join(lua_value(x) for x in v) + '}'
        return '{\n' + ',\n'.join(nxt + lua_value(x, nxt) for x in v) + '\n' + ind + '}'
    if isinstance(v, dict):
        if not v:
            return '{}'
        parts = []
        for k, x in v.items():
            k = str(k)
            key = k if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', k) and k not in LUA_WORDS else '[' + lua_value(k) + ']'
            parts.append('%s%s = %s' % (nxt, key, lua_value(x, nxt)))
        return '{\n' + ',\n'.join(parts) + '\n' + ind + '}'
    return lua_value(str(v))


LUA_WORDS = {'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'goto', 'if', 'in', 'local',
             'nil', 'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while'}


def movie_ids(slug):
    """The global variable and MWScript that play the mod's movies (PlayBink can't be called from Lua)."""
    base = 'ws' + slug[:24]
    return base + '_mv', base + '_mvs'


def movies(scenes):
    """Every movie file the scenes play, in a fixed order (its number is what the scene player sets)."""
    out = []
    for _k, sc in sorted((scenes or {}).items()):
        for c in (sc.get('screen') or []) if isinstance(sc, dict) else []:
            f = isinstance(c, dict) and c.get('movie')
            if isinstance(f, str) and f.strip():
                f = re.sub(r'^(?i:video)/', '', f.strip().replace('\\', '/'))
                if f not in out:
                    out.append(f)
    return out


def movie_records(db):
    """Keep the mod's movie global, its MWScript and start script in step with the scenes (called before the
    scene change is committed, so one Undo takes both back). A mod whose scenes play no movie has none of them."""
    import struct
    import mwscript
    from project import join_subs, zs
    p = db.project
    gv, sid = movie_ids(p.lua_slug())
    files = movies(p.scenes)
    if not files:
        for tag, key in (('SSCR', sid.lower()), ('SCPT', sid.lower()), ('GLOB', gv.lower())):
            if (p.records.get(tag + '|' + key) or {}).get('created'):
                p.remove_record(tag, key)
        db.sync_project()
        return
    p.set_record('GLOB', gv.lower(), 0, join_subs([('NAME', zs(gv)), ('FNAM', b's'), ('FLTV', struct.pack('<f', 0.0))]),
                 created=True)
    db.sync_project()
    branches = '\n'.join('%s ( n == %d )\n  PlayBink "%s" 1' % ('if' if i == 0 else 'elseif', i + 1, f.replace('"', ''))
                         for i, f in enumerate(files))
    text = ('; Made by Morrowind Workshop: plays the movies of this mod\'s scenes when the scene player asks.\n'
            'Begin %s\nshort n\nset n to %s\nif ( n == 0 )\n  return\nendif\nset %s to 0\n%s\nendif\nEnd\n'
            % (sid, gv, gv, branches))
    mwscript.save(db, sid, text, create=mwscript._winner(db, sid) is None, save=False)
    p.set_record('SSCR', sid.lower(), 0, join_subs([('DATA', zs(sid.lower())), ('NAME', zs(sid))]), created=True)
    db.sync_project()


def outputs(slug, scenes):
    """{relative path: text} and the .omwscripts lines for a mod's scenes ({} and [] when it has none)."""
    if not scenes:
        return {}, []
    base = 'scripts/%s/scene/' % slug
    data = '-- Made by Morrowind Workshop: the scenes of this mod (openmw-scene/1).\nreturn ' + lua_value(
        {k: v for k, v in sorted(scenes.items())}) + '\n'
    mv = movies(scenes)
    sub = lambda t: (t.replace('%SLUG%', slug).replace('%VERSION%', VERSION).replace('%MOVIEVAR%', movie_ids(slug)[0])
                     .replace('%MOVIES%', lua_value({f: i + 1 for i, f in enumerate(mv)})))
    out = {base + 'data.lua': data, base + 'global.lua': sub(GLOBAL), base + 'player.lua': sub(PLAYER),
           base + 'actor.lua': sub(ACTOR)}
    lines = ['GLOBAL: ' + base + 'global.lua', 'PLAYER: ' + base + 'player.lua', 'CUSTOM: ' + base + 'actor.lua']
    return out, lines


GLOBAL = r'''-- Made by Morrowind Workshop: plays this mod's scenes (scene player %VERSION%, openmw-scene/1).
local world = require('openmw.world')
local core = require('openmw.core')
local types = require('openmw.types')
local util = require('openmw.util')
local vfs = require('openmw.vfs')

local SLUG = '%SLUG%'
local okData, SCENES = pcall(require, 'scripts.%SLUG%.scene.data')
if not okData then print('[WsScene] ' .. SLUG .. ': no scene data: ' .. tostring(SCENES)); SCENES = {} end
local ACTOR = 'scripts/%SLUG%/scene/actor.lua'
local EV = 'WsScene_' .. SLUG .. '_'
local NAME = 'scene:' .. SLUG
local MOVIEVAR = '%MOVIEVAR%'
local MOVIES = %MOVIES%     -- movie file -> its number for the MWScript that plays it (PlayBink isn't in Lua)

local cur = nil            -- the scene playing: {id, sc, t, paused, actors, fired, preview}
local played = {}          -- scenes whose trigger said once and that have run (kept in the save)
local pendingEnd = nil     -- a scene that was playing when the game was saved: its end runs once play resumes
local held = {}            -- other programs holding the camera
local checkT = 0

local function say(...) print('[WsScene] ' .. string.format(...)) end
local function player() return world.players[1] end
local function deg(v) return (tonumber(v) or 0) * math.pi / 180 end
local function v3(p) return util.vector3(tonumber(p[1]) or 0, tonumber(p[2]) or 0, tonumber(p[3]) or 0) end

local function cellName(sc)
  if type(sc.cell) == 'string' then return sc.cell end
  return ''                                            -- (outdoors: the position says where)
end

local function findActor(a, near)
  if type(a.ref) == 'table' and a.ref.file and a.ref.index then
    local ok, id = pcall(core.getFormId, a.ref.file, tonumber(a.ref.index))
    if ok and id then
      local ok2, obj = pcall(world.getObjectByFormId, id)
      if ok2 and obj and obj:isValid() then return obj end
    end
    return nil
  end
  if a.id then
    local best, bd = nil, math.huge
    local ok, list = pcall(world.getObjectsByRecordId, string.lower(a.id))
    if ok and list then
      for _, o in ipairs(list) do
        if o:isValid() and o.count > 0 and o.cell then
          local d = near and (o.position - near):length() or 0
          if d < bd then best, bd = o, d end
        end
      end
    end
    return best
  end
  return nil
end

local function missing(obj)
  if not obj or not obj:isValid() or obj.count == 0 then return true end
  local ok, dead = pcall(types.Actor.isDead, obj)
  return ok and dead
end

local function sendPlayer(name, data)
  local p = player()
  if p then p:sendEvent(EV .. name, data or {}) end
end

local function finish(how)
  if not cur then return end
  local sc, actors = cur.sc, cur.actors
  local id = cur.id
  cur = nil
  local p = player()
  local endv = type(sc['end']) == 'table' and sc['end'] or {}
  for _, d in ipairs(type(endv['do']) == 'table' and endv['do'] or {}) do
    local ok, err = pcall(function()
      if d.quest and p then
        local q = types.Player.quests(p)[string.lower(d.quest)]
        if q.addJournalEntry then q:addJournalEntry(tonumber(d.stage) or 0) else q.stage = tonumber(d.stage) or 0 end
      elseif d.global and p then
        world.mwscript.getGlobalVariables(p)[d.global] = tonumber(d.value) or 0
      elseif d.event then
        core.sendGlobalEvent(d.event, type(d.data) == 'table' and d.data or {})
      end
    end)
    if not ok then say('%s: an end step failed: %s', id, tostring(err)) end
  end
  for _, obj in pairs(actors or {}) do
    if obj:isValid() and obj ~= p then obj:sendEvent(EV .. 'End', {}) end
  end
  sendPlayer('End', {how = how, controls = true})
  core.sendGlobalEvent('CameraRelease', {name = NAME})
  core.sendGlobalEvent('WsScene_Ended', {scene = id, mod = SLUG, how = how})
  say('%s ended (%s)', id, how)
end

local function onMissing(key)
  local endv = type(cur.sc['end']) == 'table' and cur.sc['end'] or {}
  if (endv.onMissingActor or 'end') == 'end' then
    say('%s: actor %s is missing or dead: ending', cur.id, tostring(key)); finish('actor_missing'); return true
  end
  return false
end

local function place(obj, mark)
  if not mark or not obj then return end
  local rot = util.transform.rotateZ(deg(mark[4]))
  local cn = (obj.cell and not obj.cell.isExterior) and obj.cell.name or ''
  pcall(function() obj:teleport(cn, v3(mark), {rotation = rot, onGround = true}) end)
end

local function start(id, t, data)
  if cur then finish('replaced') end
  local sc = data or SCENES[id]
  if type(sc) ~= 'table' then say('no scene %s', tostring(id)); return end
  local p = player()
  if not p then return end
  local actors, keys = {player = p}, {}
  local marks = type(sc.marks) == 'table' and sc.marks or {}
  cur = {id = id, sc = sc, t = 0, paused = false, actors = actors, fired = {}, preview = data ~= nil}
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    if a.key then
      local obj = findActor(a, p.position)
      if missing(obj) then
        if onMissing(a.key) then return end
      else
        actors[a.key] = obj
        keys[#keys + 1] = a.key
        if not obj:hasScript(ACTOR) then obj:addScript(ACTOR) end
        obj:sendEvent(EV .. 'Begin', {vfx = sc.vfx})
        if a.mark and marks[a.mark] then place(obj, marks[a.mark]) end
      end
    end
  end
  local pl = type(sc.player) == 'table' and sc.player or {}
  if pl.mark and marks[pl.mark] then
    local m = marks[pl.mark]
    pcall(function() p:teleport(cellName(sc), v3(m), {rotation = util.transform.rotateZ(deg(m[4])), onGround = true}) end)
  end
  core.sendGlobalEvent('CameraClaim', {name = NAME})
  sendPlayer('Begin', {id = id, sc = sc, actors = actors, held = next(held) ~= nil})
  core.sendGlobalEvent('WsScene_Started', {scene = id, mod = SLUG})
  say('%s started with %d actors', id, #keys)
  if t and t > 0 then cur.t = t; sendPlayer('Seek', {t = t}) end
end

local function lineSay(ln)
  local who = cur.actors[ln.who or ln.actor or '']
  if who and ln.voice and vfs.fileExists(ln.voice) then
    local ok, err = pcall(core.sound.say, ln.voice, who, ln.text)
    if ok then return end
    say('%s: voice %s failed: %s', cur.id, tostring(ln.voice), tostring(err))
  end
  if ln.text then sendPlayer('Text', {text = ln.text}) end
end

local function seek(t)
  if not cur then return end
  cur.t = math.max(0, tonumber(t) or 0)
  cur.fired = {}
  local sc = cur.sc
  -- clips: each actor's latest clip at or before t plays from its start; lines and effects before t are passed
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    local last, li = nil, nil
    for i, c in ipairs(type(a.clips) == 'table' and a.clips or {}) do
      if (tonumber(c.at) or 0) <= cur.t then last, li = c, i; cur.fired['clip:' .. a.key .. ':' .. i] = true end
    end
    if last and cur.actors[a.key] then cur.actors[a.key]:sendEvent(EV .. 'Clip', {clip = last}) end
  end
  for i, ln in ipairs(type(sc.lines) == 'table' and sc.lines or {}) do
    if (tonumber(ln.at) or 0) <= cur.t then cur.fired['line:' .. i] = true end
  end
  for i, v in ipairs(type(sc.vfx) == 'table' and sc.vfx or {}) do
    if v.at and (tonumber(v.at) or 0) <= cur.t then cur.fired['vfx:' .. i] = true end
  end
  for i, c in ipairs(type(sc.screen) == 'table' and sc.screen or {}) do
    if c.movie and (tonumber(c.at) or 0) <= cur.t then cur.fired['movie:' .. i] = true end
  end
  sendPlayer('Seek', {t = cur.t})
end

local function step(dt)
  if not cur or cur.paused then return end
  cur.t = cur.t + dt
  local sc, t = cur.sc, cur.t
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    local obj = cur.actors[a.key]
    if obj then
      if missing(obj) then
        cur.actors[a.key] = nil
        if onMissing(a.key) then return end
      else
        for i, c in ipairs(type(a.clips) == 'table' and a.clips or {}) do
          local k = 'clip:' .. a.key .. ':' .. i
          if not cur.fired[k] and (tonumber(c.at) or 0) <= t then
            cur.fired[k] = true
            obj:sendEvent(EV .. 'Clip', {clip = c})
          end
        end
      end
    end
  end
  for i, ln in ipairs(type(sc.lines) == 'table' and sc.lines or {}) do
    if not cur.fired['line:' .. i] and (tonumber(ln.at) or 0) <= t then cur.fired['line:' .. i] = true; lineSay(ln) end
  end
  for i, c in ipairs(type(sc.screen) == 'table' and sc.screen or {}) do
    if c.movie and not cur.fired['movie:' .. i] and (tonumber(c.at) or 0) <= t then
      cur.fired['movie:' .. i] = true
      local f = string.gsub(string.gsub(c.movie, '\\', '/'), '^[Vv][Ii][Dd][Ee][Oo]/', '')
      local n = MOVIES[f]
      local p = player()
      if n and p then
        local ok, err = pcall(function() world.mwscript.getGlobalVariables(p)[MOVIEVAR] = n end)
        if not ok then say('%s: movie %s: %s', cur.id, f, tostring(err)) end
      else
        say("%s: movie %s is not in this mod's list (a preview plays only movies of saved scenes)", cur.id, f)
      end
    end
  end
  for i, v in ipairs(type(sc.vfx) == 'table' and sc.vfx or {}) do
    if v.at and not cur.fired['vfx:' .. i] and (tonumber(v.at) or 0) <= t then
      cur.fired['vfx:' .. i] = true
      local obj = cur.actors[v.on or '']
      if obj then obj:sendEvent(EV .. 'Vfx', {vfx = v}) end
    end
  end
  if t >= (tonumber(sc.length) or 0) then finish('finish') end
end

-- triggers: what starts a scene (the Workshop sets them; the scene file leaves them out)
local function triggers()
  local p = player()
  if not p then return end
  for id, sc in pairs(SCENES) do
    local tr = type(sc) == 'table' and sc.trigger or nil
    if type(tr) == 'table' and not (tr.once ~= false and played[id]) then
      local go = false
      if tr.kind == 'area' and tr.center then
        local inCell = (type(tr.cell) ~= 'string') or (p.cell and string.lower(p.cell.name or '') == string.lower(tr.cell))
        local outdoor = type(tr.cell) ~= 'string' and p.cell and p.cell.isExterior
        if (inCell or outdoor) and (p.position - v3(tr.center)):length() <= (tonumber(tr.radius) or 300) then go = true end
      elseif tr.kind == 'quest' and tr.quest then
        local ok, q = pcall(function() return types.Player.quests(p)[string.lower(tr.quest)] end)
        if ok and q and (q.stage or 0) >= (tonumber(tr.stage) or 0) and (tonumber(tr.stage) or 0) > 0 then go = true end
      elseif tr.kind == 'global' and tr.name then
        local ok, g = pcall(function() return world.mwscript.getGlobalVariables(p)[tr.name] end)
        if ok and g and g == (tonumber(tr.value) or 1) then
          go = true
          pcall(function() world.mwscript.getGlobalVariables(p)[tr.name] = 0 end)
        end
      end
      if go then
        played[id] = true
        start(id, 0)
        return
      end
    end
  end
end

local function onUpdate(dt)
  if pendingEnd then
    local id = pendingEnd
    pendingEnd = nil
    local sc = SCENES[id]
    if sc then cur = {id = id, sc = sc, t = 0, actors = {}, fired = {}}; finish('load')
    else sendPlayer('End', {how = 'load', controls = true}) end
  end
  if cur then step(dt); return end
  checkT = checkT + dt
  if checkT >= 0.5 then checkT = 0; triggers() end
end

local api = {
  version = '%VERSION%',
  scenes = function() local l = {}; for k in pairs(SCENES) do l[#l + 1] = k end; table.sort(l); return l end,
  play = function(id, t, data) start(id, t or 0, data) end,
  pause = function() if cur then cur.paused = true; sendPlayer('Pause', {}) end end,
  resume = function() if cur then cur.paused = false; sendPlayer('Resume', {}) end end,
  seek = seek,
  stop = function() finish('stop') end,
  state = function() return cur and {scene = cur.id, t = cur.t, paused = cur.paused, length = cur.sc.length} or nil end,
}

return {
  interfaceName = 'WorkshopScenes_' .. SLUG,
  interface = api,
  engineHandlers = {
    onUpdate = onUpdate,
    onSave = function() return {played = played, playing = cur and not cur.preview and cur.id or nil} end,
    onLoad = function(data)
      played = (data and data.played) or {}
      if data and data.playing then pendingEnd = data.playing end
    end,
  },
  eventHandlers = {
    WsScene_Play = function(e)
      if e.data and e.mod ~= SLUG then return end              -- (a preview is for the mod it names)
      if not e.data and not SCENES[e.scene or ''] then return end
      start(e.scene or (e.data and e.data.scene) or 'preview', tonumber(e.t) or 0, e.data)
    end,
    WsScene_Pause = function() api.pause() end,
    WsScene_Resume = function() api.resume() end,
    WsScene_Seek = function(e) seek(e.t) end,
    WsScene_Stop = function() finish('stop') end,
    WsScene_Skip = function()
      if not cur then return end
      local endv = type(cur.sc['end']) == 'table' and cur.sc['end'] or {}
      if endv.onSkip == 'none' then return end
      finish('skip')
    end,
    CameraClaim = function(e)
      if e.name and e.name ~= NAME then held[e.name] = true; sendPlayer('Hold', {on = true}) end
    end,
    CameraRelease = function(e)
      if e.name and e.name ~= NAME then
        held[e.name] = nil
        if next(held) == nil then sendPlayer('Hold', {on = false}) end
      end
    end,
  },
}
'''

PLAYER = r'''-- Made by Morrowind Workshop: the camera, screen and controls of this mod's scenes (scene player %VERSION%).
local camera = require('openmw.camera')
local core = require('openmw.core')
local self = require('openmw.self')
local types = require('openmw.types')
local ui = require('openmw.ui')
local util = require('openmw.util')
local input = require('openmw.input')
local vfs = require('openmw.vfs')
local okA, ambient = pcall(require, 'openmw.ambient')

local EV = 'WsScene_%SLUG%_'
local S = nil              -- {sc, actors, t, paused, mode, switches, bars, fade, music}
local hold = false
local SWITCHES = {'Controls', 'Fighting', 'Jumping', 'Looking', 'Magic', 'ViewMode', 'VanityMode'}

local function deg(v) return (tonumber(v) or 0) * math.pi / 180 end
local function v3(p) return util.vector3(tonumber(p[1]) or 0, tonumber(p[2]) or 0, tonumber(p[3]) or 0) end

local function setControls(on, keep)
  local P = types.Player
  for _, n in ipairs(SWITCHES) do
    local sw = P.CONTROL_SWITCH[n]
    if sw then
      if not on and keep then keep[n] = P.getControlSwitch(self, sw) end
      local want = on
      if on and keep and keep[n] ~= nil then want = keep[n] end
      pcall(P.setControlSwitch, self, sw, want)
    end
  end
end

-- where an actor's aim point is: its feet, chest or head (from its bounds, so race and scale count)
local function aimPoint(obj, at)
  local p = obj.position
  local ok, box = pcall(function() return obj:getBoundingBox() end)
  local top, mid = p.z + 110 * (obj.scale or 1), p.z + 70 * (obj.scale or 1)
  if ok and box then top = box.center.z + box.halfSize.z * 0.86; mid = box.center.z + box.halfSize.z * 0.25 end
  if at == 'feet' then return util.vector3(p.x, p.y, p.z + 5) end
  if at == 'chest' then return util.vector3(p.x, p.y, mid) end
  return util.vector3(p.x, p.y, top)               -- 'head'
end

local function frame(obj)
  local yaw = obj.rotation:getYaw()
  local fwd = util.vector3(math.sin(yaw), math.cos(yaw), 0)
  local right = util.vector3(math.cos(yaw), -math.sin(yaw), 0)
  return fwd, right
end

local function ease(x, kind)
  x = math.max(0, math.min(1, x))
  if kind == 'in' then return x * x end
  if kind == 'out' then return 1 - (1 - x) * (1 - x) end
  if kind == 'linear' then return x end
  return x * x * (3 - 2 * x)                       -- inOut
end

local function lerp(a, b, f) return a + (b - a) * f end

local function shotNow()
  local cur, nxt = nil, nil
  for _, s in ipairs(type(S.sc.shots) == 'table' and S.sc.shots or {}) do
    if (tonumber(s.at) or 0) <= S.t then cur = s end
  end
  return cur
end

local function offsetAt(s)
  local o = s.offset or {0, -150, 0}
  local mv = s.move
  if type(mv) == 'table' and type(mv.to) == 'table' and mv.to.offset then
    local f = ease((S.t - (tonumber(s.at) or 0)) / math.max(0.01, tonumber(mv.dur) or 1), mv.ease)
    o = {lerp(o[1] or 0, mv.to.offset[1] or 0, f), lerp(o[2] or 0, mv.to.offset[2] or 0, f), lerp(o[3] or 0, mv.to.offset[3] or 0, f)}
  end
  return o
end

local function look(from, to)
  local d = to - from
  local yaw = math.atan2(d.x, d.y)
  local pitch = -math.atan2(d.z, math.sqrt(d.x * d.x + d.y * d.y))     -- (the camera's pitch: above 0 looks down)
  return yaw, pitch
end

local function placeCamera()
  local s = shotNow()
  if not s then return end
  local pos, yaw, pitch
  if s.pos then
    pos = v3(s.pos)
    local mv = s.move
    if type(mv) == 'table' and type(mv.to) == 'table' and mv.to.pos then
      local f = ease((S.t - (tonumber(s.at) or 0)) / math.max(0.01, tonumber(mv.dur) or 1), mv.ease)
      pos = pos + (v3(mv.to.pos) - pos) * f
    end
    yaw, pitch = deg(s.yaw), -deg(s.pitch)
  else
    local aim = type(s.aim) == 'table' and s.aim or {}
    local target = S.actors[aim.actor or '']
    if not target or not target:isValid() then return end
    local P = aimPoint(target, aim.at or 'head')
    if type(s.from) == 'table' then
      local f = S.actors[s.from.actor or 'player'] or self.object
      local fwd, right = frame(f)
      local side = (s.from.shoulder == 'left') and -1 or 1
      pos = aimPoint(f, 'head') + right * (28 * side) - fwd * 45 + util.vector3(0, 0, 6)
    else
      local fwd, right = frame(target)
      local o = offsetAt(s)
      local base = util.vector3(target.position.x, target.position.y, P.z)
      pos = base + right * (o[1] or 0) + fwd * (o[2] or 0) + util.vector3(0, 0, o[3] or 0)
    end
    yaw, pitch = look(pos, P)
  end
  camera.setStaticPosition(pos)
  camera.setYaw(yaw)
  camera.setPitch(pitch)
  if s.fov then camera.setFieldOfView(deg(s.fov)) end
end

local function black(alpha, y, h)
  return ui.create({layer = 'HUD', type = ui.TYPE.Image, props = {
    resource = ui.texture({path = 'white'}), color = util.color.rgb(0, 0, 0), alpha = alpha,
    relativePosition = util.vector2(0, y), relativeSize = util.vector2(1, h)}})
end

local function clearScreen()
  if S and S.bars then for _, e in ipairs(S.bars) do e:destroy() end; S.bars = nil end
  if S and S.fade then S.fade.el:destroy(); S.fade = nil end
end

local function screenCues()
  for i, c in ipairs(type(S.sc.screen) == 'table' and S.sc.screen or {}) do
    if not S.fired[i] and (tonumber(c.at) or 0) <= S.t then
      S.fired[i] = true
      if c.letterbox and not S.bars then
        local ratio = tonumber(c.letterbox) or 2.39
        local sz = ui.screenSize()
        local bar = (1 - (sz.x / sz.y) / ratio) / 2
        if bar > 0.005 then S.bars = {black(1, 0, bar), black(1, 1 - bar, bar)} end
      elseif c.letterbox == false and S.bars then
        for _, e in ipairs(S.bars) do e:destroy() end; S.bars = nil
      end
      if c.fade == 'in' or c.fade == 'out' then
        if S.fade then S.fade.el:destroy() end
        S.fade = {el = black(c.fade == 'in' and 1 or 0, 0, 1), from = (c.fade == 'in') and 1 or 0,
                  to = (c.fade == 'in') and 0 or 1, t0 = S.t, dur = tonumber(c.dur) or 1}
      end
    end
  end
  if S.fade then
    local f = math.max(0, math.min(1, (S.t - S.fade.t0) / S.fade.dur))
    S.fade.el.layout.props.alpha = S.fade.from + (S.fade.to - S.fade.from) * f
    S.fade.el:update()
    if f >= 1 and S.fade.to == 0 then S.fade.el:destroy(); S.fade = nil end
  end
  for i, c in ipairs(type(S.sc.sound) == 'table' and S.sc.sound or {}) do
    local k = 's' .. i
    if not S.fired[k] and (tonumber(c.at) or 0) <= S.t then
      S.fired[k] = true
      if c.music and okA and vfs.fileExists(c.music) then pcall(ambient.streamMusic, c.music); S.music = true end
      if c.sound and okA and vfs.fileExists(c.sound) then pcall(ambient.playSoundFile, c.sound) end
    end
  end
end

local function finish(how)
  if not S then return end
  clearScreen()
  pcall(function() camera.setFieldOfView(camera.getBaseFieldOfView()) end)
  pcall(camera.setMode, S.mode or camera.MODE.ThirdPerson, true)
  setControls(true, S.switches)
  if S.music and okA then pcall(ambient.stopMusic) end
  S = nil
end

return {
  engineHandlers = {
    onUpdate = function(dt)
      if not S or S.paused then return end
      S.t = S.t + dt
      screenCues()
    end,
    onFrame = function()
      if S and not hold then placeCamera() end
    end,
    onKeyPress = function(key)
      if S and (key.code == input.KEY.Space or key.code == input.KEY.Enter) then core.sendGlobalEvent('WsScene_Skip', {}) end
    end,
    onSave = function() return S and {active = true, switches = S.switches, mode = S.mode} or nil end,
    onLoad = function(data)
      -- (saved in the middle of a scene: the player gets the controls and camera back; the scene's end runs too)
      if data and data.active then setControls(true, data.switches); pcall(camera.setMode, data.mode or camera.MODE.ThirdPerson, true) end
    end,
  },
  eventHandlers = {
    [EV .. 'Begin'] = function(e)
      finish('replaced')
      S = {sc = e.sc, actors = e.actors or {}, t = 0, paused = false, fired = {}, switches = {}, mode = camera.getMode()}
      hold = e.held or false
      local pl = type(e.sc.player) == 'table' and e.sc.player or {}
      if pl.controls ~= 'on' then setControls(false, S.switches) end
      if pl.sheathe then pcall(function() types.Actor.setStance(self, types.Actor.STANCE.Nothing) end) end
      camera.setMode(camera.MODE.Static, true)
      screenCues()
    end,
    [EV .. 'Seek'] = function(e) if S then S.t = tonumber(e.t) or 0; S.fired = {}; clearScreen() ; screenCues() end end,
    [EV .. 'Pause'] = function() if S then S.paused = true end end,
    [EV .. 'Resume'] = function() if S then S.paused = false end end,
    [EV .. 'Text'] = function(e) if e.text then ui.showMessage(e.text) end end,
    [EV .. 'Hold'] = function(e) hold = e.on and true or false end,
    [EV .. 'End'] = function(e)
      if S then finish(e.how) elseif e.controls then setControls(true) end
    end,
  },
}
'''

ACTOR = r'''-- Made by Morrowind Workshop: an actor in one of this mod's scenes (scene player %VERSION%).
local self = require('openmw.self')
local anim = require('openmw.animation')
local async = require('openmw.async')
local I = require('openmw.interfaces')

local EV = 'WsScene_%SLUG%_'
local active, last, keys, vfx = false, nil, {}, {}
local hooked = {}

local function addVfx(v)
  if not v or not v.model then return end
  local id = 'wsscene_' .. tostring(v.id or v.model)
  pcall(anim.addVfx, self, v.model, {boneName = v.bone or '', vfxId = id, loop = v.loop and true or false})
  if v.dur then
    async:newUnsavableSimulationTimer(tonumber(v.dur) or 1, function() pcall(anim.removeVfx, self, id) end)
  end
end

local function onKey(group, key)
  local what = active and keys[group] and keys[group][key]
  if type(what) == 'string' and what:sub(1, 4) == 'vfx:' then
    local id = what:sub(5)
    for _, v in ipairs(vfx) do if v.id == id then addVfx(v) end end
  end
end

return {
  eventHandlers = {
    [EV .. 'Begin'] = function(e)
      active, vfx = true, (type(e.vfx) == 'table' and e.vfx) or {}
      pcall(function() self:enableAI(false) end)
    end,
    [EV .. 'Clip'] = function(e)
      local c = e.clip or {}
      if not c.group then return end
      if not anim.hasGroup(self, c.group) then
        print('[WsScene] ' .. tostring(self.recordId) .. ' has no animation group ' .. tostring(c.group))
        return
      end
      if last and last ~= c.group then pcall(anim.cancel, self, last) end
      anim.clearAnimationQueue(self, false)
      local opts = {speed = tonumber(c.speed) or 1}
      if not c.loop then opts.loops = 0 end
      anim.playQueued(self, c.group, opts)
      last = c.group
      if type(c.keys) == 'table' then
        keys[c.group] = c.keys
        if not hooked[c.group] and I.AnimationController then
          hooked[c.group] = true
          I.AnimationController.addTextKeyHandler(c.group, onKey)
        end
      end
    end,
    [EV .. 'Vfx'] = function(e) addVfx(e.vfx) end,
    [EV .. 'End'] = function()
      active = false
      if last then pcall(anim.cancel, self, last); last = nil end
      pcall(function() self:enableAI(true) end)
    end,
  },
  engineHandlers = {
    onSave = function() return {active = active} end,
    onLoad = function(data)
      -- (saved during a scene: the actor walks again)
      if data and data.active then pcall(function() self:enableAI(true) end) end
    end,
  },
}
'''
