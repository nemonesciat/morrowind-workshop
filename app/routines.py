"""Daily routines for the people Populate places (populate-plan stage 5): a day for each, slept by their own bed,
eaten at a table, worked where the cast stands them, the evening at the table or the fire, and one global Lua script
in the mod, "wsroutines", that keeps them to it in OpenMW.

The game's own people mostly have none: one Wander from their record, day and night. A routine is the Workshop's
own, written from templates by role as Populate's lines are (no AI), each person's hours shifted a little so a
household doesn't move as one. In the game, the script looks at the people the player can see: when one comes into
play it sets them where the hour puts them (they have been there all along), and while the player watches, at the
turn of the hour they walk there (a Travel package), then idle or wander a little (a Wander). Anyone hurt, dead or with
a weapon out is left to the game, and so is anything the player sets going (a follower stays one). Moves stay in the
person's own place: going out to the tavern is not part of it yet. Plain Morrowind ignores the script.

The script's table of routines sits between marker lines; register/unregister rewrite only that, the rest is the
user's to change (as riders.py keeps the sliding panels'). register doesn't commit: populate.place commits it with
the people, one Undo."""
import math
import random
import re

SCRIPT = 'wsroutines'
BEGIN = '  -- BEGIN ROUTINES (kept by the Workshop: Populate > Daily routines)'
END = '  -- END ROUTINES'
# the day by role: (hour, what) from that hour on; 'bed', 'table', 'work', 'fire' are where (see plan()). The
# household works from eight, the tavern's keeper and patrons keep later hours, servants rise first.
DAYS = {
    'head': ((6.0, 'table'), (8.0, 'work'), (19.5, 'table'), (21.5, 'fire'), (22.5, 'bed')),
    'family': ((6.5, 'table'), (8.5, 'work'), (19.5, 'table'), (21.0, 'fire'), (22.0, 'bed')),
    'servant': ((5.5, 'fire'), (7.0, 'work'), (20.5, 'table'), (21.5, 'bed')),
    'lodger': ((7.0, 'table'), (8.5, 'work'), (20.0, 'fire'), (23.0, 'bed')),
    'tavern': ((9.0, 'table'), (11.0, 'work'), (2.0, 'bed')),
}
NO_ROUTINE = ('guard', 'patron', 'leader', 'band')      # (on duty, or not of the household)
SHIFT = 0.75             # each person's hours moved by up to this much, either way
WANDER = {'work': 0, 'table': 0, 'fire': 64, 'bed': 0}   # (how far they idle about once there)

LUA = '''-- Made by Morrowind Workshop: daily routines for the people Populate placed (Populate > Daily routines).
-- Each person below has a day: from each hour on, a spot in their own place. When one comes into play they are
-- set where the hour puts them; while the player watches, at the turn of the hour they walk there and then idle.
-- Anyone hurt, dead or with a weapon out is left to the game. The Workshop keeps the list when people are placed
-- or taken out; the rest of the script is yours to change.
local world = require('openmw.world')
local core = require('openmw.core')
local types = require('openmw.types')
local util = require('openmw.util')

-- NPC record id (lower case) -> { { from hour, x, y, z, facing, wander }, ... } by hour
local ROUTINES = {
''' + BEGIN + '''
''' + END + '''
}

local CHECK = 1.0        -- seconds between looks
local ARRIVED = 48       -- this near the spot is there
local STUCK = 45         -- seconds of walking before they are put there
local timer = 0
local state = {}         -- actor id -> { slot = index, walking = seconds or nil }

local function hourNow()
  return (core.getGameTime() / 3600) % 24
end

-- the slot the hour falls in: the last one started (before the first of the day, last night's)
local function slotAt(r, h)
  local cur = #r
  for i, s in ipairs(r) do
    if s[1] <= h then cur = i end
  end
  return cur
end

-- left to the game: dead, hurt (a fight, most likely) or with a weapon or a spell out
local function busy(o)
  if types.Actor.isDead(o) then return true end
  local ok, hurt = pcall(function()
    local hp = types.Actor.stats.dynamic.health(o)
    return hp.current < hp.base + hp.modifier - 1
  end)
  if ok and hurt then return true end
  local ok2, stance = pcall(function() return types.Actor.getStance(o) end)
  if ok2 and stance and stance ~= types.Actor.STANCE.Nothing then return true end
  return false
end

local function at(s)
  return util.vector3(s[2], s[3], s[4])
end

local function idle(o, s)
  o:sendEvent('StartAIPackage', { type = 'Wander', distance = s[6], duration = 0, isRepeat = true })
end

local function setThere(o, s)
  pcall(function()
    o:teleport(o.cell, at(s), { rotation = util.transform.rotateZ(s[5]), onGround = true })
  end)
  idle(o, s)
end

local function look(o, r, h)
  local st = state[o.id]
  local i = slotAt(r, h)
  local s = r[i]
  if not st then
    -- (just come into play: they have been at it all along)
    state[o.id] = { slot = i }
    if (o.position - at(s)):length() > ARRIVED then setThere(o, s) else idle(o, s) end
    return
  end
  if st.walking then
    st.walking = st.walking + CHECK
    if (o.position - at(s)):length() <= ARRIVED then
      st.walking = nil
      idle(o, s)
    elseif st.walking > STUCK then
      st.walking = nil
      setThere(o, s)
    end
  end
  if st.slot ~= i then
    st.slot = i
    st.walking = 0
    o:sendEvent('StartAIPackage', { type = 'Travel', destPosition = at(s) })
  end
end

local function onUpdate(dt)
  timer = timer + dt
  if timer < CHECK then return end
  timer = 0
  local h = hourNow()
  local live = {}
  for _, o in ipairs(world.activeActors) do
    local r = o.recordId and ROUTINES[o.recordId]
    if r and o:isValid() then
      live[o.id] = true
      if busy(o) then
        state[o.id] = nil      -- (left to the game; set again when it's over)
      else
        pcall(look, o, r, h)
      end
    end
  end
  -- (out of play: forgotten, so they are set again when next seen)
  for id in pairs(state) do
    if not live[id] then state[id] = nil end
  end
end

return {
  engineHandlers = { onUpdate = onUpdate },
}
'''


def script(db):
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == SCRIPT), None)


def _block(text):
    m = re.search(re.escape(BEGIN) + r'\n(.*?)' + re.escape(END), text, re.S)
    return m.group(1) if m else ''


def routines(db):
    """{NPC record id (lower case): [[hour, x, y, z, facing, wander], ...]} the script keeps."""
    s = script(db)
    out = {}
    for m in re.finditer(r'\["([^"]+)"\]\s*=\s*\{(.*?)\},\s*$', _block((s or {}).get('text') or ''), re.M):
        rows = re.findall(r'\{([^{}]*)\}', m.group(2))
        try:
            out[m.group(1).lower()] = [[float(v) for v in row.split(',')] for row in rows]
        except ValueError:
            continue
    return out


def _lua_line(rid, rows):
    return '  ["%s"] = { %s },' % (rid.replace('"', ''), ', '.join(
        '{ %.2f, %.1f, %.1f, %.1f, %.4f, %d }' % tuple(r[:5] + [int(r[5])]) for r in rows))


def _write(db, table):
    lines = ''.join(_lua_line(k, v) + '\n' for k, v in sorted(table.items()))
    new = BEGIN + '\n' + lines + END
    s = script(db)
    if s is None:
        db.project.lua.append({'name': SCRIPT, 'kind': 'GLOBAL', 'text': LUA.replace(BEGIN + '\n' + END, new)})
        return
    text = s.get('text') or ''
    if BEGIN in text and END in text:
        s['text'] = re.sub(re.escape(BEGIN) + r'\n.*?' + re.escape(END), lambda _m: new, text, count=1, flags=re.S)
    else:
        s['text'] = LUA.replace(BEGIN + '\n' + END, new)     # (the markers were edited away: the script starts afresh)


def register(db, rows_by_id):
    """Add or replace routines ({record id: rows}); no commit."""
    table = routines(db)
    for k, v in rows_by_id.items():
        if v:
            table[k.lower()] = v
    _write(db, table)


def unregister(db, rids):
    table = routines(db)
    for k in rids:
        table.pop(k.lower(), None)
    if script(db) is not None:
        _write(db, table)


def _role(p, setting):
    rel = (p.get('relation') or '').lower()
    if rel in NO_ROUTINE or (p.get('role') or '') == 'guard':
        return None
    if setting == 'tavern' and rel == 'head':
        return 'tavern'
    if rel in DAYS:
        return rel
    if rel in ('spouse', 'child', 'kin'):
        return 'family'
    return 'lodger' if rel else 'family'


def _floor(info, x, y, z):
    """The floor under (x, y) nearest below z (a room's), or None when no room is there."""
    best = None
    for rm in info.get('rooms') or []:
        if rm['x_min'] + 16 <= x <= rm['x_max'] - 16 and rm['y_min'] + 16 <= y <= rm['y_max'] - 16 and rm['floor'] <= z + 60:
            if best is None or rm['floor'] > best:
                best = rm['floor']
    return best


def _beside(db, info, f, d, taken):
    """A spot by a piece of furniture, facing it, on a room's floor and clear of things and of the other spots:
    its front first, then its sides, nearer and further, then its back. (x, y, z, facing) or None."""
    import furnish
    import populate
    try:
        fr = furnish.front_of(db, f['id'])
    except Exception:
        fr = None
    fx, fy = fr or (0.0, -1.0)
    # (clear of everything first; failing that, on the floor and away from the others, a chair's corner let be)
    for strict in (True, False):
        for lx, ly in ((fx, fy), (-fy, fx), (fy, -fx), (-fx, -fy)):
            for k in (1.0, 0.75, 1.35, 1.7):
                wx, wy = populate._world(lx, ly, f['p'][5])
                x, y = f['p'][0] + wx * d * k, f['p'][1] + wy * d * k
                fl = _floor(info, x, y, f['p'][2])
                if fl is None:
                    continue
                if strict and not populate._clear(info, taken, x, y):
                    continue
                if not strict and any(math.hypot(x - a, y - b) < 40 for a, b in taken):
                    continue
                return x, y, fl + 4, math.atan2(-wx, -wy) % (2 * math.pi)
    return None


def plan(db, info, made, seed=0):
    """The routines for people just placed: made [(record id, person)] with their spots; {record id: rows}."""
    rng = random.Random(seed or len(made))
    furn = info.get('furniture') or []
    beds = [f for f in furn if f.get('fam') in ('bed', 'bedroll')]
    tables = [f for f in furn if f.get('fam') in ('table', 'counter')] or [f for f in furn if f.get('fam') in ('chair', 'bench')]
    fires = [f for f in furn if f.get('fam') == 'fire'] or tables
    used_beds, n_at = set(), {}
    taken = [tuple(m[1]['spot'][:2]) for m in made if m[1].get('spot')]
    out = {}
    order = sorted(made, key=lambda m: 0 if (m[1].get('relation') == 'head') else 1)
    for nid, p in order:
        role = _role(p, info.get('setting'))
        sp = p.get('spot')
        if not role or not sp:
            continue
        work = (float(sp[0]), float(sp[1]), float(sp[2]), float(sp[3]))

        def near(cands, key):
            if not cands:
                return None
            pick = sorted(cands, key=lambda f: math.hypot(f['p'][0] - work[0], f['p'][1] - work[1]) + 400 * n_at.get((key, f['k']), 0))[0]
            n_at[(key, pick['k'])] = n_at.get((key, pick['k']), 0) + 1
            return pick

        free_beds = [b for b in beds if b['k'] not in used_beds]
        bed = sorted(free_beds, key=lambda f: math.hypot(f['p'][0] - work[0], f['p'][1] - work[1]))[0] if free_beds else None
        if bed:
            used_beds.add(bed['k'])
        where = {'work': work}
        # (each spot kept clear of the ones already given: two at a table stand round it, not in one another)
        for what, f_, d in (('bed', bed, 45), ('table', near(tables, 'table'), 60), ('fire', near(fires, 'fire'), 80)):
            if f_ is None:
                continue
            got = _beside(db, info, f_, d, taken)
            if got:
                where[what] = got
                taken.append(got[:2])
        shift = rng.uniform(-SHIFT, SHIFT)
        rows = []
        for h, what in DAYS[role]:
            w = where.get(what) or where['work']
            rows.append([round((h + shift) % 24, 2), round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 4), WANDER.get(what, 0)])
        rows.sort(key=lambda r: r[0])
        # (two slots at the same spot in a row are one)
        merged = [rows[0]]
        for r in rows[1:]:
            if r[1:4] != merged[-1][1:4]:
                merged.append(r)
        if len(merged) >= 2:
            out[nid.lower()] = merged
    return out
