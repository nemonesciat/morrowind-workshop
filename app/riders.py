"""Things standing on a sliding panel ride with it. The game's Move only moves the scripted object, so a
bookshelf made a sliding panel (mechanism.make_slide) would slide out from under its books. This module
keeps one global Lua script in the mod, "wsriders" (kind GLOBAL, in the project's Lua scripts like any the
user writes, so it shows on the Scripts page and packs with the mod), with a table of the panel records to
watch and each one's model box. In the game the script notes, when a watched panel comes into play, every
object in its cell whose box stands on or inside the panel's box (not actors, doors or other panels), with
its offset from the panel; whenever the panel's position changes the riders are teleported to keep their
offsets, so when SetAtStart puts the panel back they are back too. Something picked up or carried away
drops out quietly.

register / unregister change db.project.lua without committing: mechanism commits them with the panel as
one undo step (Project.state() carries the Lua scripts)."""
import re

SCRIPT = 'wsriders'
BEGIN = '  -- BEGIN PANELS (kept by the Workshop: Secret entrance > Sliding panel)'
END = '  -- END PANELS'
SLACK_XY = 12.0      # how far a thing may overhang the panel's edge and still ride (units: a book tipped over the front)
SLACK_Z = 12.0       # how far above the panel's top (or below its bottom) a thing's underside may be

LUA = '''-- Made by Morrowind Workshop: things standing on a sliding panel (Secret entrance > Sliding panel)
-- slide with it. The game's Move only moves the panel itself, so this script notes, when a panel in the
-- list below comes into play, everything in its cell that stands on it or on its shelves (not actors,
-- not doors), with its offset from the panel; whenever the panel moves they are moved to keep that
-- offset, and when the panel is back at its start so are they. Something picked up or carried away
-- drops out of the list quietly. The Workshop keeps the list when a panel is made or made an ordinary
-- object again; the rest of the script is yours to change.
local world = require('openmw.world')
local types = require('openmw.types')
local util = require('openmw.util')

-- record id (lower case) -> the panel model's own box { x0, y0, z0, x1, y1, z1 }
local PANELS = {
''' + BEGIN + '''
''' + END + '''
}

local SLACK_XY = %g      -- how far a thing may overhang the panel's edge and still ride (units)
local SLACK_Z = %g       -- how far above the panel's top (a vase on it) or below its bottom a thing's underside may be
local SETTLE = 3         -- frames to wait after a panel appears before looking at what stands on it
local SWEEP = 2          -- seconds between looks for a listed panel in the player's cell that is not tracked yet

local tracked = {}       -- panel object id -> { obj, last, riders = { { obj, off } }, again }
local pending = {}       -- panel object id -> { obj, frames }
local sweepTimer = 0

local function listed(obj)
  return obj.recordId ~= nil and PANELS[obj.recordId] ~= nil
end

local function sameCell(a, b)
  if not (a and b) then return false end
  return a.name == b.name and a.gridX == b.gridX and a.gridY == b.gridY
end

local function vmin(a, b) return util.vector3(math.min(a.x, b.x), math.min(a.y, b.y), math.min(a.z, b.z)) end
local function vmax(a, b) return util.vector3(math.max(a.x, b.x), math.max(a.y, b.y), math.max(a.z, b.z)) end

-- the panel's box in the world: the model's own box from the list, scaled and turned as the panel stands
local function panelBox(obj)
  local b = PANELS[obj.recordId]
  local s = obj.scale or 1
  local lo, hi = nil, nil
  for _, cx in ipairs({ b[1], b[4] }) do
    for _, cy in ipairs({ b[2], b[5] }) do
      for _, cz in ipairs({ b[3], b[6] }) do
        local p = obj.position + obj.rotation:apply(util.vector3(cx * s, cy * s, cz * s))
        if lo then lo, hi = vmin(lo, p), vmax(hi, p) else lo, hi = p, p end
      end
    end
  end
  return lo, hi
end

-- another object's box in the world (the game's own bounds; just its position when it has none)
local function objBox(o)
  local ok, box = pcall(function() return o:getBoundingBox() end)
  if ok and box and box.vertices then
    local lo, hi = nil, nil
    for _, p in ipairs(box.vertices) do
      if lo then lo, hi = vmin(lo, p), vmax(hi, p) else lo, hi = p, p end
    end
    if lo then return lo, hi end
  end
  return o.position, o.position
end

-- does this thing stand on the panel: its footprint within the panel's (a little overhang allowed) and its
-- underside between the panel's bottom and a little above its top (so a book on a shelf counts, and a vase
-- on top; a wall behind it or a rug wider than it does not)
local function rides(o, plo, phi)
  local olo, ohi = objBox(o)
  if olo.x < plo.x - SLACK_XY or ohi.x > phi.x + SLACK_XY then return false end
  if olo.y < plo.y - SLACK_XY or ohi.y > phi.y + SLACK_XY then return false end
  if olo.z < plo.z - SLACK_Z or olo.z > phi.z + SLACK_Z then return false end
  return true
end

local function look(panel)
  if not (panel:isValid() and panel.cell) then return end
  local plo, phi = panelBox(panel)
  local t = { obj = panel, last = panel.position, riders = {}, again = false }
  for _, o in ipairs(panel.cell:getAll()) do
    if o.id ~= panel.id and o:isValid() and not listed(o)
       and not types.Actor.objectIsInstance(o) and not types.Door.objectIsInstance(o) then
      local ok, yes = pcall(rides, o, plo, phi)
      if ok and yes then
        t.riders[#t.riders + 1] = { obj = o, off = o.position - panel.position }
      end
    end
  end
  tracked[panel.id] = t
  print(string.format('[WSRIDERS] %%s carries %%d things', panel.recordId, #t.riders))
end

-- keep the riders at their offsets whenever the panel has moved (and once more after a rider that was
-- still on its way last frame, so none is left a step behind when the panel stops)
local function follow(t)
  local panel = t.obj
  if not panel:isValid() then return false end
  local p = panel.position
  if not t.again and (p - t.last):length() < 0.01 then return true end
  t.last = p
  t.again = false
  for i = #t.riders, 1, -1 do
    local r = t.riders[i]
    local o = r.obj
    if not (o:isValid() and o.cell and sameCell(o.cell, panel.cell)) then
      table.remove(t.riders, i)
    elseif (o.count or 0) > 0 then
      pcall(function() o:teleport(o.cell, p + r.off, { rotation = o.rotation, onGround = false }) end)
    else
      t.again = true
    end
  end
  return true
end

local function onObjectActive(obj)
  if listed(obj) and not pending[obj.id] then
    pending[obj.id] = { obj = obj, frames = 0 }
  end
end

local function onUpdate(dt)
  for id, w in pairs(pending) do
    w.frames = w.frames + 1
    if w.frames >= SETTLE then
      pending[id] = nil
      if w.obj:isValid() then pcall(look, w.obj) end
    end
  end
  for id, t in pairs(tracked) do
    local ok, keep = pcall(follow, t)
    if not (ok and keep) then tracked[id] = nil end
  end
  -- (a listed panel the engine did not announce, or one from before a loaded save: looked for now and then)
  sweepTimer = sweepTimer + dt
  if sweepTimer >= SWEEP then
    sweepTimer = 0
    local player = world.players[1]
    if player and player.cell then
      for _, o in ipairs(player.cell:getAll()) do
        if listed(o) and not tracked[o.id] and not pending[o.id] then
          pending[o.id] = { obj = o, frames = 0 }
        end
      end
    end
  end
end

return {
  engineHandlers = {
    onObjectActive = onObjectActive,
    onUpdate = onUpdate,
  },
}
''' % (SLACK_XY, SLACK_Z)


def script(db):
    """The mod's riders script, or None."""
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == SCRIPT), None)


def panels(db):
    """{panel record id (lower case): [x0, y0, z0, x1, y1, z1]} the script watches."""
    s = script(db)
    out = {}
    if not s:
        return out
    for m in re.finditer(r'\["([^"]+)"\]\s*=\s*\{([^}]*)\}', _block(s.get('text') or '')):
        try:
            out[m.group(1).lower()] = [float(v) for v in m.group(2).split(',')]
        except ValueError:
            continue
    return out


def _block(text):
    m = re.search(re.escape(BEGIN) + r'\n(.*?)' + re.escape(END), text, re.S)
    return m.group(1) if m else ''


def _with_block(text, table):
    lines = ''.join('  ["%s"] = { %s },\n' % (k, ', '.join('%g' % v for v in b)) for k, b in sorted(table.items()))
    new = BEGIN + '\n' + lines + END
    if BEGIN in text and END in text:
        return re.sub(re.escape(BEGIN) + r'\n.*?' + re.escape(END), lambda _m: new, text, count=1, flags=re.S)
    return LUA.replace(BEGIN + '\n' + END, new)      # (the markers were edited away: the script starts afresh)


def register(db, panel_id, bounds):
    """Watch this panel record (bounds: its model's box, 6 floats; a guess when unknown). Makes the script
    when the mod has none. No commit."""
    p = db.project
    s = script(db)
    if s is None:
        s = {'name': SCRIPT, 'kind': 'GLOBAL', 'attach': [], 'text': LUA}
        p.lua.append(s)
    table = panels(db)
    table[panel_id.lower()] = [float(v) for v in (bounds or (-64.0, -32.0, 0.0, 64.0, 32.0, 128.0))]
    s['text'] = _with_block(s.get('text') or LUA, table)
    return s


def unregister(db, panel_id):
    """Stop watching a panel record; the script goes with its last panel (unless the user changed the rest
    of it). True when it was watched. No commit."""
    s = script(db)
    table = panels(db)
    if s is None or panel_id.lower() not in table:
        return False
    del table[panel_id.lower()]
    if not table and _with_block(s.get('text') or '', {}) == LUA:
        db.project.lua.remove(s)
    else:
        s['text'] = _with_block(s.get('text') or LUA, table)
    return True


# ------------------------------------------------------------------ the same test, in the Workshop
def _world_box(p, b, scale):
    """[x0, y0, z0, x1, y1, z1] of a placed thing from its model box, scaled and turned the game's way (Z,
    then Y, then X, clockwise for positive angles: what the script's obj.rotation:apply does with the real
    bounds)."""
    import math
    cx_, sx_ = math.cos(-p[3]), math.sin(-p[3])
    cy_, sy_ = math.cos(-p[4]), math.sin(-p[4])
    cz_, sz_ = math.cos(-p[5]), math.sin(-p[5])

    def turn(x, y, z):
        x, y = x * cz_ - y * sz_, x * sz_ + y * cz_                  # Z
        x, z = x * cy_ + z * sy_, -x * sy_ + z * cy_                 # Y
        y, z = y * cx_ - z * sx_, y * sx_ + z * cx_                  # X
        return x, y, z
    lo = hi = None
    for cx in (b[0], b[3]):
        for cy in (b[1], b[4]):
            for cz in (b[2], b[5]):
                wx, wy, wz = turn(cx * scale, cy * scale, cz * scale)
                pt = (p[0] + wx, p[1] + wy, p[2] + wz)
                lo = pt if lo is None else tuple(min(a, q) for a, q in zip(lo, pt))
                hi = pt if hi is None else tuple(max(a, q) for a, q in zip(hi, pt))
    return list(lo) + list(hi)


def aboard(db, cell_key, refkey):
    """What the script would carry on this placed panel as the cell stands now: [{k, id, name, type}],
    by the same rule (footprint within the panel's, underside between its bottom and a little over its
    top; no actors, doors or listed panels)."""
    import mapdata
    m = mapdata.cellmap(db, cell_key)
    refs = m.get('refs') or []
    panel = next((r for r in refs if r['k'] == refkey), None)
    if not panel or not panel.get('b'):
        return []
    watched = panels(db)
    plo = _world_box(panel['p'], panel['b'], panel.get('s') or 1.0)
    out = []
    for r in refs:
        if r['k'] == refkey or r['type'] in ('NPC_', 'CREA', 'DOOR') or r['id'].lower() in watched:
            continue
        if r.get('b'):
            o = _world_box(r['p'], r['b'], r.get('s') or 1.0)
        else:
            o = list(r['p'][:3]) * 2
        if o[0] < plo[0] - SLACK_XY or o[3] > plo[3] + SLACK_XY or o[1] < plo[1] - SLACK_XY or o[4] > plo[4] + SLACK_XY:
            continue
        if o[2] < plo[2] - SLACK_Z or o[2] > plo[5] + SLACK_Z:
            continue
        out.append({'k': r['k'], 'id': r['id'], 'name': r.get('name') or '', 'type': r['type']})
    return out
