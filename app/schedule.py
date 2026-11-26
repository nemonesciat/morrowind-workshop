"""A person's week (the person card's 📅 Day): blocks of hours on chosen days, each at a spot in a place (their own,
or another), standing there with the game's idles or wandering about it. One global Lua script in the mod,
"wsschedule", keeps them to it in OpenMW: in the same place they walk to the spot at the hour; when the block is
somewhere else they walk out through the door that leads there while the player watches (else they are moved), and
whoever is due in the place the player comes into is there already. Anyone hurt, dead or with a weapon out is left to
the game. A person with a week of their own leaves Populate's daily routines (routines.py), so the two never pull
against each other.

The weeks are kept in the script itself, a line of JSON per person between marker lines for the Workshop and the table
the game reads beside it, so Undo takes a change back with the rest of the mod (a user's request, 2026-11-26, after a
look at another tool's schedule editor: "work on schedules")."""
import json
import math
import re

from editing import EditError, commit, _require_project

SCRIPT = 'wsschedule'
BEGIN = '  -- BEGIN WEEKS (kept by the Workshop: a person\'s card, 📅 Day)'
END = '  -- END WEEKS'
# the game's days, as OpenMW's calendar numbers them ('%w': 0 is Sundas)
DAYS = ['Sundas', 'Morndas', 'Tirdas', 'Middas', 'Turdas', 'Fredas', 'Loredas']
ACTS = ('stand', 'wander')
CELL = 8192

LUA = '''-- Made by Morrowind Workshop: the weeks of the people you gave one (a person's card, 📅 Day).
-- Each person below has blocks of hours on chosen days, each at a spot. In the same place they walk there at the
-- hour; when it is somewhere else they walk out through the door that leads there while you watch (else they are
-- moved), and whoever is due where you come in is there already. Anyone hurt, dead or with a weapon out is left to
-- the game. The Workshop writes this whole script each time a week changes (so its fixes reach your mod): changes of
-- your own belong in a script of your own.
local world = require('openmw.world')
local core = require('openmw.core')
local types = require('openmw.types')
local util = require('openmw.util')
local calendar = require('openmw_aux.calendar')

-- NPC record id (lower case) -> { home = place, b = { { days, from, to, place, x, y, z, facing, wander }, ... } }
-- days: the days' numbers ("0123456", 0 = Sundas); place: an interior's name, or "" outdoors
local WEEKS = {
''' + BEGIN + '''
''' + END + '''
}

local CHECK = 1.0        -- seconds between looks
local ARRIVED = 48       -- this near the spot is there
local AT_DOOR = 110      -- this near the door is through it
local STUCK = 45         -- seconds of walking before they are put there
local DOOR_STUCK = 25    -- seconds of walking to a door before they are through it
local CELL = 8192
local timer = 0
local state = {}         -- actor id -> { block = key, walking = seconds or nil, door = door or nil }
local hurtAt = {}
local CALM = 60
local lastPlace = nil    -- the player's place last look, to bring in whoever is due there

local function now()
  local t = core.getGameTime()
  local d = tonumber(calendar.formatGameTime('%w', t)) or 0
  return d, (t / 3600) % 24
end

-- the block for this day and hour: the last one listed that holds it (a block past midnight belongs to the day
-- it started on)
local function blockAt(w, d, h)
  local found = nil
  for _, b in ipairs(w.b) do
    local from, to = b[2], b[3]
    local ok
    if from <= to then ok = h >= from and h < to and b[1]:find(tostring(d), 1, true)
    else ok = (h >= from and b[1]:find(tostring(d), 1, true)) or (h < to and b[1]:find(tostring((d + 6) % 7), 1, true)) end
    if ok then found = b end
  end
  return found
end

local function placeOf(cell)
  if cell.isExterior then return '' end
  return (cell.name or ''):lower()
end
local function samePlace(cell, b) return placeOf(cell) == b[4]:lower() end
local function at(b) return util.vector3(b[5], b[6], b[7]) end
local function key(b) return b[1] .. b[2] .. b[4] .. b[5] .. b[6] end

local function busy(o)
  if types.Actor.isDead(o) then return true end
  local ok, hurt = pcall(function()
    local t = core.getSimulationTime()
    local hp = types.Actor.stats.dynamic.health(o).current
    local h = hurtAt[o.id]
    if not h then h = { hp = hp, at = -1e9 }; hurtAt[o.id] = h end
    if hp < h.hp - 0.5 then h.at = t end
    h.hp = hp
    return t - h.at < CALM
  end)
  if ok and hurt then return true end
  local ok2, stance = pcall(function() return types.Actor.getStance(o) end)
  if ok2 and stance and stance ~= types.Actor.STANCE.Nothing then return true end
  return false
end

local function idle(o, b)
  o:sendEvent('StartAIPackage', { type = 'Wander', distance = b[9], duration = 0, isRepeat = true })
end

local function putThere(o, b)
  pcall(function()
    o:teleport(b[4], at(b), { rotation = util.transform.rotateZ(b[8]), onGround = true })
  end)
  idle(o, b)
end

-- the door out of here toward the block's place: straight there if one leads there, else out of doors
local function doorToward(o, b)
  local best, bestD = nil, 1e12
  for _, dr in ipairs(o.cell:getAll(types.Door)) do
    local ok, tp = pcall(function() return types.Door.isTeleport(dr) and types.Door.destCell(dr) end)
    if ok and tp then
      local score = (placeOf(tp) == b[4]:lower()) and 0 or ((tp.isExterior and not o.cell.isExterior) and 1 or nil)
      if score then
        local dd = (dr.position - o.position):length() + score * 1e6
        if dd < bestD then best, bestD = dr, dd end
      end
    end
  end
  return best
end

-- (the player in the same room, or outdoors within half a cell: they would see them vanish)
local function watched(o)
  local p = world.players[1]
  if not (p and p.cell and o.cell) then return false end
  if p.cell.isExterior and o.cell.isExterior then return (p.position - o.position):length() < CELL / 2 end
  return p.cell.id == o.cell.id
end

local function look(o, w, d, h)
  local b = blockAt(w, d, h)
  if not b then state[o.id] = nil; return end
  local st = state[o.id]
  local k = key(b)
  if samePlace(o.cell, b) then
    if not st or st.door then
      -- (just come into play here, or come through the door: they have been at it all along)
      state[o.id] = { block = k }
      if (o.position - at(b)):length() > ARRIVED then putThere(o, b) else idle(o, b) end
      return
    end
    if st.walking then
      st.walking = st.walking + CHECK
      if (o.position - at(b)):length() <= ARRIVED then st.walking = nil; idle(o, b)
      elseif st.walking > STUCK then st.walking = nil; putThere(o, b) end
    end
    if st.block ~= k then
      st.block = k; st.walking = 0
      o:sendEvent('StartAIPackage', { type = 'Travel', destPosition = at(b) })
    end
    return
  end
  -- somewhere else: out through the door while watched, else moved there
  if not watched(o) then putThere(o, b); state[o.id] = { block = k }; return end
  if not st or st.block ~= k or not st.door then
    local dr = doorToward(o, b)
    if not dr then putThere(o, b); state[o.id] = { block = k }; return end
    state[o.id] = { block = k, walking = 0, door = dr }
    o:sendEvent('StartAIPackage', { type = 'Travel', destPosition = dr.position })
    return
  end
  st.walking = st.walking + CHECK
  -- (through it once at it, or once they have stopped close by: people stop short of a door; in the game Fargoth
  -- stood 300 off the Tradehouse's door for a while, 2026-11-26)
  local gap = (o.position - st.door.position):length()
  local moved = st.last and (o.position - st.last):length() or 1e9
  st.last = o.position
  st.still = (moved < 8) and (st.still or 0) + CHECK or 0
  if gap <= AT_DOOR or (gap < 320 and st.still >= 3) or st.walking > DOOR_STUCK then putThere(o, b); st.walking = nil end
end

-- whoever is due in the player's place and not here yet: found where their week keeps them and set at the spot
local function bringIn(p, d, h, live)
  for rid, w in pairs(WEEKS) do
    local b = blockAt(w, d, h)
    if b and not live[rid] and samePlace(p.cell, b) and (b[4] ~= '' or (at(b) - p.position):length() < CELL * 1.5) then
      local places = { [w.home] = true }
      for _, x in ipairs(w.b) do places[x[4]] = true end
      local found = nil
      for name in pairs(places) do
        if found then break end
        local ok, list = pcall(function()
          if name == '' then return world.getObjectsByRecordId(rid, 'sys::default', true) end
          local c = world.getCellByName(name)
          if not c then return {} end
          local all = c:getAll(types.NPC)
          for _, o in ipairs(c:getAll(types.Creature)) do table.insert(all, o) end      -- (a creature can have a week too)
          return all
        end)
        if ok and list then
          for _, o in ipairs(list) do
            if tostring(o.recordId):lower() == rid and o:isValid() and not types.Actor.isDead(o) then found = o; break end
          end
        end
      end
      if found then putThere(found, b) end
    end
  end
end

local function onUpdate(dt)
  timer = timer + dt
  if timer < CHECK then return end
  timer = 0
  local d, h = now()
  local live = {}
  for _, o in ipairs(world.activeActors) do
    local rid = o.recordId and tostring(o.recordId):lower()
    local w = rid and WEEKS[rid]
    if w and o:isValid() then
      live[rid] = true
      if busy(o) then state[o.id] = nil else pcall(look, o, w, d, h) end
    end
  end
  local p = world.players[1]
  if p and p.cell then
    local here = placeOf(p.cell) .. math.floor(h)
    if here ~= lastPlace then lastPlace = here; pcall(bringIn, p, d, h, live) end
  end
  for id in pairs(hurtAt) do if not state[id] then hurtAt[id] = nil end end
end

return {
  engineHandlers = { onUpdate = onUpdate },
}
'''


def script(db):
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == SCRIPT), None)


def weeks(db):
    """{NPC record id (lower case): {'blocks': [...], 'home': place}} as the script keeps them."""
    s = script(db)
    m = re.search(re.escape(BEGIN) + r'\n(.*?)' + re.escape(END), (s or {}).get('text') or '', re.S)
    out = {}
    for line in (m.group(1) if m else '').splitlines():
        line = line.strip()
        if line.startswith('-- {'):
            try:
                d = json.loads(line[3:])
                out[d['id'].lower()] = d
            except (ValueError, KeyError):
                continue
    return out


def _lua_str(s):
    return '"%s"' % str(s).replace('\\', '\\\\').replace('"', '\\"')


def _lua_lines(d):
    rows = ', '.join('{ %s, %.2f, %.2f, %s, %.1f, %.1f, %.1f, %.4f, %d }' % (
        _lua_str(''.join(str(x) for x in sorted(b['days']))), b['from'], b['to'], _lua_str(b['place'].lower()),
        b['pos'][0], b['pos'][1], b['pos'][2], b['facing'], b['wander'] if b['act'] == 'wander' else 0) for b in d['blocks'])
    return ('  -- %s\n  [%s] = { home = %s, b = { %s } },\n' % (json.dumps(d, ensure_ascii=False), _lua_str(d['id'].lower()),
                                                            _lua_str((d.get('home') or '').lower()), rows))


def _write(db, table):
    body = ''.join(_lua_lines(v) for _k, v in sorted(table.items()))
    s = script(db)
    if not table:
        if s is not None:
            db.project.lua.remove(s)
        return
    text = LUA.replace(BEGIN + '\n' + END, BEGIN + '\n' + body + END)
    if s is None:
        db.project.lua.append({'name': SCRIPT, 'kind': 'GLOBAL', 'text': text})
    else:
        s['text'] = text


def get(db, rid):
    _require_project(db)
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] not in ('NPC_', 'CREA'):
        raise EditError('There is no person or creature called "%s".' % rid)
    r = db.recs[ri]
    d = weeks(db).get(r[1].lower()) or {'id': r[1], 'blocks': [], 'home': ''}
    import routines
    return {'id': r[1], 'name': r[2] or r[1], 'blocks': d['blocks'], 'home': d.get('home', ''), 'days': DAYS,
            'routine': r[1].lower() in routines.routines(db), 'lua': bool(db.project.lua_allowed())}


def _clean(db, b):
    try:
        days = sorted({int(x) for x in b.get('days') or []})
    except (TypeError, ValueError):
        raise EditError('The days must be picked from the week.')
    if not days or any(x < 0 or x > 6 for x in days):
        raise EditError('Pick at least one day.')
    try:
        fr, to = float(b.get('from')), float(b.get('to'))
    except (TypeError, ValueError):
        raise EditError('Give the hours as numbers, 0 to 24.')
    if not (0 <= fr <= 24 and 0 <= to <= 24) or fr == to:
        raise EditError('The hours run from 0 to 24, and a block needs some time in it.')
    act = b.get('act') or 'stand'
    if act not in ACTS:
        raise EditError('They can stand or wander there.')
    pos = b.get('pos') or []
    if len(pos) < 3:
        raise EditError('Pick where they are: Here, or right-click the spot.')
    place = str(b.get('place') or '').strip()
    if place:
        import mapdata
        info = mapdata.cell_info(db, place.lower())
        if not info:
            raise EditError('There is no place called "%s".' % place)
        place = info.get('name') or place
    return {'days': days, 'from': round(fr % 24, 2) if fr != 24 else 24.0, 'to': round(to, 2), 'place': place,
            'pos': [round(float(v), 1) for v in pos[:3]], 'facing': round(float(b.get('facing') or 0), 4),
            'act': act, 'wander': max(0, min(2048, int(b.get('wander') or (256 if act == 'wander' else 0)))),
            'note': str(b.get('note') or '').strip()[:60]}


def save(db, rid, blocks, home=''):
    """A person's week, every block checked first (a bad one refuses the lot and leaves nothing); one Undo."""
    _require_project(db)
    if not db.project.lua_allowed():
        raise EditError('A week needs OpenMW Lua: save your mod as an .omwaddon (File › Save as).')
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] not in ('NPC_', 'CREA'):
        raise EditError('There is no person or creature called "%s".' % rid)
    r = db.recs[ri]
    clean = [_clean(db, b) for b in (blocks or [])][:40]
    table = weeks(db)
    if clean:
        table[r[1].lower()] = {'id': r[1], 'blocks': clean, 'home': str(home or '')}
    else:
        table.pop(r[1].lower(), None)
    _write(db, table)
    import routines
    routines.unregister(db, [r[1].lower()])     # (their own week wins over Populate's daily routine)
    commit(db, ('Set the week of %s (%d block%s)' % (r[2] or r[1], len(clean), '' if len(clean) == 1 else 's')) if clean
           else 'Cleared the week of %s' % (r[2] or r[1]))
    return get(db, r[1])
