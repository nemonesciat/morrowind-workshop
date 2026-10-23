"""Your own magic effects (2026-10-23), made the way Tamriel Data makes its own in OpenMW: a new effect is a copy
of one of the game's effects (its template: school, icon, colours, the sounds and pictures of casting, flying,
hitting), with its own name, icon, base cost and description, made as the game loads by a load script
(OpenMW 0.50's `openmw.content`). What it does is not the template's: the engine only knows its own effects by
their number, so a new one does nothing by itself. What it does is what you pick, run by small scripts the
Workshop writes for you, in the spirit of Tamriel Data's own (scripts/TamrielData/actor_magic.lua and
global_magic.lua): one on every actor that reads the spells working on it each frame, one global one for what
only the world can do (move, resize, teleport, place, weather, globals), one on the player for messages.

Each step of what an effect does has a when (as it lands, each second while it lasts, as it ends), whom it
works on (anyone, NPCs, creatures, undead, Daedra, the player, anyone but the player) and a chance:
  health / magicka / fatigue   take away or give back (the magnitude, each second or once)
  push / pull / launch / dash  Unrelenting Force away from the caster, telekinesis towards them, thrown up into
                               the air, a sprint forward: moved a little each frame, stopping at walls
  scale                        grow or shrink by a factor; back to the size it was when it ends
  calm / frenzy                Fight 0 or 100 while it lasts, as it was afterwards
  aura                         the magnitude off (or onto) everyone within so many feet, each second
  leech                        the magnitude taken from them and given to the caster, each second
  swap                         the caster and the one it lands on change places
  cast                         a spell of the game's (or yours) cast on them: chains and combos
  weather                      the region's weather changes (a storm, ash, blight, snow...)
  teleport / spawn / global / message   as before
  lua                          your own code, with helpers (ctx.push, ctx.launch, ctx.scale, ctx.change...)

Kept in the mod's Lua scripts: "my_effects" (kind LOAD) holds the list as JSON between markers and makes the
effects; "my_effects_actor", "my_effects_global" and "my_effects_player" are written from it. The spell,
enchantment and potion editors offer the effects (tdeffects.effects lists them with Tamriel Data's), and a
record using one carries its template meanwhile, put right as the game loads by the "td_effects" script."""
import json
import re

from editing import EditError, commit, _require_project
from esm import iter_subrecords, zstr

SCRIPT = 'my_effects'
ACTOR, GLOBAL, PLAYER = 'my_effects_actor', 'my_effects_global', 'my_effects_player'
BEGIN = '--[[ WORKSHOP MY EFFECTS (kept by the Workshop: the magic effect maker writes this)'
END = 'WORKSHOP MY EFFECTS END ]]'
STATS = ('health', 'magicka', 'fatigue')
MOVES = ('push', 'pull', 'launch', 'dash')
WHENS = ('land', 'second', 'end')
ONLY = ('any', 'npc', 'creature', 'undead', 'daedra', 'player', 'notplayer')
WEATHERS = ('clear', 'cloudy', 'foggy', 'overcast', 'rain', 'thunderstorm', 'ashstorm', 'blight', 'snow', 'blizzard')
DOES = [
    ('health', 'Health', 'Take away or give back health, by the magnitude: each second while it lasts, or once.'),
    ('magicka', 'Magicka', 'Take away or give back magicka, by the magnitude: each second while it lasts, or once.'),
    ('fatigue', 'Fatigue', 'Take away or give back fatigue, by the magnitude: each second while it lasts, or once.'),
    ('push', 'Push away', 'Unrelenting Force: thrown back from the caster, so many feet (or the magnitude), stopping at walls.'),
    ('pull', 'Pull in', 'Telekinesis: dragged towards the caster, so many feet (or the magnitude).'),
    ('launch', 'Launch up', 'Thrown up into the air so many feet (or the magnitude), then they fall.'),
    ('dash', 'Dash forward', 'A sprint the way they face, so many feet (or the magnitude): Whirlwind Sprint, on Self.'),
    ('scale', 'Grow or shrink', 'Bigger or smaller by a factor (2 = twice the size, 0.5 = half); back to normal when it ends.'),
    ('calm', 'Calm', 'They won\'t fight while it lasts.'),
    ('frenzy', 'Frenzy', 'They attack anyone near while it lasts.'),
    ('aura', 'Aura', 'Each second, the magnitude off (or onto) the health, magicka or fatigue of everyone within so many feet.'),
    ('leech', 'Leech', 'Each second, the magnitude taken from their health, magicka or fatigue and given to the caster.'),
    ('swap', 'Swap places', 'The caster and the one it lands on change places.'),
    ('cast', 'Cast a spell on them', 'Another spell (the game\'s, or one of yours) cast on them: for chains and combos.'),
    ('weather', 'Change the weather', 'The region\'s weather turns to a storm, ash, blight, snow, rain or clear skies.'),
    ('transmute', 'Transmute', 'One of the first item it finds in their inventory, of the pairs you list (iron ore into silver, silver into gold...), becomes the next.'),
    ('teleport', 'Teleport', 'Send the one it lands on to a place: a cell and a spot in it.'),
    ('spawn', 'Place something', 'Place an object or a creature beside the one it lands on.'),
    ('global', 'Set a global variable', 'Set one of the game\'s global variables, so an MWScript or a dialogue line can react.'),
    ('message', 'Show a message', 'Show a line of text to the player.'),
    ('lua', 'Lua of your own', 'Your own code, run when you choose, with helpers for the steps above. The Assistant can write it from a description.'),
]
# (where each kind is done: on the actor itself, or by the global script for what only the world can do)
WORLD = ('teleport', 'spawn', 'global', 'message', 'scale', 'weather', 'swap', 'transmute')
FT = 22.1                     # (game units to a foot, as Tamriel Data's Blink reckons it)


def _script(db, name):
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == name), None)


def effects_raw(db):
    """[effect dict] as kept in the mod's my_effects script."""
    s = _script(db, SCRIPT)
    if not s:
        return []
    text = s.get('text') or ''
    a, b = text.find(BEGIN), text.find(END)
    if a < 0 or b < 0:
        return []
    try:
        return json.loads(text[a + len(BEGIN):b]) or []
    except ValueError:
        return []


_vcache = {}


def _vanilla(db):
    """{number: {name, school, cost, icon, key (OpenMW's id, e.g. 'firedamage'), magnitude, duration}}."""
    if _vcache.get('recs') is db.recs:
        return _vcache['out']
    import items
    out = {}
    for e in items.effects(db, vanilla_only=True):
        out[e['index']] = dict(e, key=re.sub(r'[^a-z]', '', e['name'].lower()), icon='')
    for (tag, key), lst in db.by_key.items():
        if tag != 'MGEF' or not lst or lst[-1] in db.dead or not key.lstrip('-').isdigit():
            continue
        r = db.recs[lst[-1]]
        for st, sd in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
            if st == 'ITEX' and int(key) in out:
                out[int(key)]['icon'] = zstr(sd)
    _vcache.update(recs=db.recs, out=out)
    return out


def templates(db):
    """The game's effects to start from, for the maker: [{index, name, school, cost, icon, magnitude, duration}]."""
    v = _vanilla(db)
    return sorted(({k: e[k] for k in ('index', 'name', 'school', 'cost', 'icon', 'magnitude', 'duration')} for e in v.values()),
                  key=lambda e: (e['school'], e['name']))


def effects(db):
    """The mod's own effects as the editors list effects (index = its id, td True, mine True, template)."""
    v = _vanilla(db)
    out = []
    for e in effects_raw(db):
        t = v.get(int(e.get('template', -1)))
        if not t:
            continue
        out.append({'index': e['id'], 'name': e['name'], 'school': t['school'], 'cost': float(e.get('cost') or t['cost']),
                    'skill': False, 'attribute': False, 'magnitude': bool(e.get('magnitude', True)),
                    'duration': bool(e.get('duration', True)), 'td': True, 'mine': True, 'template': t['index'],
                    'icon': e.get('icon') or t['icon'], 'enchanting': True, 'spellmaking': True})
    return out


def read(db):
    return {'effects': effects_raw(db), 'templates': templates(db),
            'does': [{'kind': k, 'label': l, 'what': w} for k, l, w in DOES],
            'whens': list(WHENS), 'only': list(ONLY), 'weathers': list(WEATHERS)}


def _slug(name):
    s = re.sub(r'[^A-Za-z0-9]+', ' ', name or '').title().replace(' ', '')
    return s[:24] or 'Effect'


def _num(v, what, default=0.0):
    if v in (None, ''):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        raise EditError('%s must be a number.' % what)


def _step(db, d):
    """One step of what an effect does, checked: the kind's own fields, and when, whom and how likely."""
    k = d.get('kind')
    label = dict((a, b) for a, b, _w in DOES).get(k)
    if not label:
        return None
    # (2.3.12's steps said "per": second or once; once is "as it lands")
    when = d.get('when') or ('land' if d.get('per') == 'once' else 'second' if k in STATS + ('aura', 'leech') else 'land')
    out = {'kind': k, 'when': when if when in WHENS else 'land', 'only': d.get('only') if d.get('only') in ONLY else 'any',
           'chance': max(0.0, min(100.0, _num(d.get('chance'), label + ': the chance', 100.0)))}
    if k in STATS:
        out['sign'] = -1 if int(_num(d.get('sign'), label, -1)) < 0 else 1
    elif k in MOVES:
        out['feet'] = max(0.0, _num(d.get('feet'), label + ': the distance', 0.0))        # (0: the magnitude, in feet)
    elif k == 'scale':
        out['factor'] = _num(d.get('factor'), label + ': the factor', 2.0)
        if not 0.1 <= out['factor'] <= 10:
            raise EditError('Grow or shrink: the factor is between 0.1 (a tenth the size) and 10.')
        out['when'] = 'land'
    elif k in ('calm', 'frenzy', 'swap'):
        out['when'] = 'land'
    elif k in ('aura', 'leech'):
        out['stat'] = d.get('stat') if d.get('stat') in STATS else 'health'
        if k == 'aura':
            out['sign'] = -1 if int(_num(d.get('sign'), label, -1)) < 0 else 1
            out['feet'] = max(1.0, _num(d.get('feet'), label + ': the reach', 10.0))
        out['when'] = 'second'
    elif k == 'cast':
        sid = (d.get('id') or '').strip()
        ri = db.resolve_id(sid) if sid else None
        if ri is None or db.recs[ri][0] != 'SPEL':
            raise EditError('Cast a spell on them: there is no spell called "%s".' % sid)
        out['id'] = db.recs[ri][1]
    elif k == 'weather':
        w = (d.get('weather') or '').strip().lower()
        if w not in WEATHERS:
            raise EditError('Change the weather: pick one of %s.' % ', '.join(WEATHERS))
        out['weather'] = w
    elif k == 'transmute':
        # (pairs, tried in order: the first whose "from" they carry is the one changed, one at a time, as
        # Oblivion's and Skyrim's Transmute turn iron ore into silver and silver into gold)
        pairs = []
        for pr in d.get('pairs') or []:
            a, b = (pr.get('from') or '').strip(), (pr.get('to') or '').strip()
            if not a and not b:
                continue
            ra, rb = db.resolve_id(a) if a else None, db.resolve_id(b) if b else None
            if ra is None or rb is None:
                raise EditError('Transmute: there is no item called "%s".' % (a if ra is None else b))
            pairs.append({'from': db.recs[ra][1], 'to': db.recs[rb][1]})
        if not pairs:
            raise EditError('Transmute: list what becomes what (e.g. iron ore into silver ore).')
        out['pairs'] = pairs[:12]
        out['count'] = max(1, int(_num(d.get('count'), 'Transmute: how many', 1)))
    elif k == 'teleport':
        out.update(cell=(d.get('cell') or '').strip(), x=_num(d.get('x'), 'Teleport: x'), y=_num(d.get('y'), 'Teleport: y'),
                   z=_num(d.get('z'), 'Teleport: z'))
    elif k == 'spawn':
        sid = (d.get('id') or '').strip()
        ri = db.resolve_id(sid) if sid else None
        if ri is None:
            raise EditError('Place something: there is no object or creature called "%s".' % sid)
        out['id'] = db.recs[ri][1]
    elif k == 'global':
        gname = (d.get('name') or '').strip()
        if not db.by_key.get(('GLOB', gname.lower())):
            raise EditError('Set a global variable: there is no global variable called "%s".' % gname)
        out.update(name=gname, value=_num(d.get('value'), 'Set a global variable: the value'))
    elif k == 'message':
        text = (d.get('text') or '').strip()
        if not text:
            return None
        out['text'] = text[:300]
    elif k == 'lua':
        code = (d.get('code') or '').strip('\n')
        if not code.strip():
            return None
        import lua_check
        probs = [p for p in lua_check.check('local function f(ctx)\n%s\nend\nreturn {}' % code, 'NPC') if p['level'] == 'error']
        if probs:
            raise EditError('Lua of your own, line %d: %s' % (max(1, probs[0]['line'] - 1), probs[0]['text']))
        out['code'] = code[:8000]
        out['brief'] = (d.get('brief') or '').strip()[:600]
    return out


def _clean(db, e):
    name = (e.get('name') or '').strip()
    if not name:
        raise EditError('Give the effect a name.')
    if len(name) > 31:
        raise EditError('Effect names can be at most 31 characters.')
    v = _vanilla(db)
    try:
        t = int(e.get('template'))
    except (TypeError, ValueError):
        raise EditError('Pick the game\'s effect it looks like.')
    if t not in v:
        raise EditError('Pick the game\'s effect it looks like.')
    eid = (e.get('id') or '').strip() or 'WS_' + _slug(name)
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]{1,30}$', eid):
        raise EditError('An effect\'s ID is letters, digits and underscores, starting with a letter (e.g. WS_StormCall).')
    if eid.lower().startswith('t_'):
        raise EditError('IDs starting with T_ are Tamriel Data\'s: start yours another way (e.g. WS_).')
    if re.sub(r'[^a-z]', '', eid.lower()) in {x['key'] for x in v.values()}:
        raise EditError('That ID is one of the game\'s own effects.')
    cost = _num(e.get('cost'), 'The base cost', v[t]['cost'])
    does = [s for s in (_step(db, d) for d in e.get('does') or []) if s]
    return {'id': eid, 'name': name, 'template': t, 'cost': round(cost, 3), 'icon': (e.get('icon') or '').strip() or v[t]['icon'],
            'description': (e.get('description') or '').strip()[:600],
            'magnitude': bool(e.get('magnitude', v[t]['magnitude'])), 'duration': bool(e.get('duration', v[t]['duration'])),
            'does': does}


def save(db, e, old_id=None):
    """Make or change one of the mod's effects (old_id: the one being changed). Writes the scripts. One step."""
    _require_project(db)
    if not db.project.lua_allowed():
        raise EditError('Your own magic effects are made by OpenMW Lua scripts, which a plain .esp can\'t carry: use Save as… '
                        'on My mod to make the mod an .omwaddon first.')
    lst = effects_raw(db)
    old = (old_id or '').lower()
    rest = [x for x in lst if x['id'].lower() != old]
    clean = _clean(db, e)
    if any(x['id'].lower() == clean['id'].lower() for x in rest):
        raise EditError('Another of your effects already has the ID %s.' % clean['id'])
    pos = next((n for n, x in enumerate(lst) if x['id'].lower() == old), len(rest))
    rest.insert(min(pos, len(rest)), clean)
    if old and old != clean['id'].lower():
        _rename_uses(db, old_id, clean['id'])
    _write(db, rest)
    commit(db, '%s the magic effect "%s" (%s)' % ('Changed' if old else 'Made', clean['name'], clean['id']))
    return {'effect': clean, 'effects': rest}


def delete(db, eid):
    _require_project(db)
    lst = effects_raw(db)
    gone = [x for x in lst if x['id'].lower() == (eid or '').lower()]
    if not gone:
        raise EditError('There is no effect of yours called %s.' % eid)
    import tdeffects
    users = [k for k, (rid, rows) in tdeffects.wanted(db).items() if any(r['id'].lower() == eid.lower() for r in rows.values())]
    if users:
        raise EditError('%s is still used by %s. Take it out of %s first.' % (
            gone[0]['name'], ', '.join(u[1] for u in users[:4]), 'them' if len(users) > 1 else 'it'))
    _write(db, [x for x in lst if x['id'].lower() != eid.lower()])
    commit(db, 'Removed the magic effect "%s"' % gone[0]['name'])
    return {'effects': effects_raw(db)}


def _rename_uses(db, old, new):
    import tdeffects
    table = tdeffects.wanted(db)
    for k, (rid, rows) in table.items():
        for r in rows.values():
            if r['id'].lower() == old.lower():
                r['id'] = new
    tdeffects._write(db, table)


# ------------------------------------------------------------------ the scripts
def _lua(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return '%g' % v
    if isinstance(v, (list, tuple)):
        return '{ %s }' % ', '.join(_lua(x) for x in v)
    if isinstance(v, dict):
        return '{ %s }' % ', '.join('[%s] = %s' % (_lua(str(k)), _lua(x)) for k, x in v.items())
    return json.dumps(str(v))


def _put(db, name, kind, text, first=False):
    p = db.project
    s = _script(db, name)
    if text is None:
        if s is not None:
            p.lua.remove(s)
        return
    if s is None:
        s = {'name': name, 'kind': kind, 'attach': []}
        # (made before the record fixes: "td_effects" puts these effects into spells as the game loads, after this)
        if first:
            p.lua.insert(0, s)
        else:
            p.lua.append(s)
    s['kind'], s['text'] = kind, text


def _row(d, fn_name=None):
    """A step as a Lua table for the actor script (lua steps name their function)."""
    keys = [k for k in d if k not in ('code', 'brief')]
    cells = ['%s = %s' % (k, _lua(d[k])) for k in keys]
    if fn_name:
        cells.append('fn = %s' % fn_name)
    return '{ %s }' % ', '.join(cells)


def _write(db, lst):
    if not lst:
        for n in (SCRIPT, ACTOR, GLOBAL, PLAYER):
            _put(db, n, None, None)
        return
    v = _vanilla(db)
    defs = []
    for e in lst:
        t = v[e['template']]
        defs.append('  { id = %s, template = %s, name = %s, baseCost = %s, icon = %s, description = %s, hasMagnitude = %s, hasDuration = %s },'
                    % (_lua(e['id']), _lua(t['key']), _lua(e['name']), _lua(e['cost']), _lua(e['icon'].replace('\\', '/')),
                       _lua(e['description']), _lua(e['magnitude']), _lua(e['duration'])))
    load = ('-- Made by Morrowind Workshop: your own magic effects (Create > New magic effect).\n'
            '-- Each is made as the game loads, from one of the game\'s effects for its looks; what it does is in %s.lua.\n'
            '-- Needs OpenMW 0.50 or newer.\n%s\n%s\n%s\n\n'
            'local content = require(\'openmw.content\')\n\nlocal EFFECTS = {\n%s\n}\n\n'
            'return {\n  engineHandlers = {\n    onContentFilesLoaded = function()\n'
            '      local records = content.magicEffects.records\n'
            '      for _, e in ipairs(EFFECTS) do\n'
            '        local ok, err = pcall(function()\n'
            '          records[e.id] = { template = records[e.template], name = e.name, baseCost = e.baseCost, icon = e.icon,\n'
            '                            description = e.description, hasMagnitude = e.hasMagnitude, hasDuration = e.hasDuration,\n'
            '                            allowsSpellmaking = true, allowsEnchanting = true }\n'
            '        end)\n'
            '        if not ok then print(\'[Workshop] magic effect \' .. e.id .. \': \' .. tostring(err)) end\n'
            '      end\n    end,\n  },\n}\n') % (ACTOR, BEGIN, json.dumps(lst, indent=1).replace(']]', ']\\u005d'), END, '\n'.join(defs))
    _put(db, SCRIPT, 'LOAD', load, first=True)
    # what each effect does, by its id (OpenMW gives effects' ids in lower case)
    rows, fns, msgs = [], [], False
    for e in lst:
        steps = []
        for n, d in enumerate(e['does']):
            fn = None
            if d['kind'] == 'lua':
                fn = 'user_%s_%d' % (re.sub(r'[^a-z0-9]', '_', e['id'].lower()), n)
                fns.append('-- %s: %s\nlocal function %s(ctx)\n%s\nend\n' % (e['name'], d.get('brief') or 'Lua of your own', fn, d['code']))
            steps.append('    ' + _row(d, fn) + ',')
            if d['kind'] == 'message':
                msgs = True
        if steps:
            rows.append('  [%s] = {\n%s\n  },' % (_lua(e['id'].lower()), '\n'.join(steps)))
    _put(db, ACTOR, 'NPC, CREATURE, PLAYER', (ACTOR_LUA % ('\n'.join(fns), '\n'.join(rows))) if rows else None)
    _put(db, GLOBAL, 'GLOBAL', GLOBAL_LUA if rows else None)
    _put(db, PLAYER, 'PLAYER', PLAYER_LUA if (rows and (msgs or any(d['kind'] in ('lua', 'transmute') for e in lst for d in e['does']))) else None)


# The actor script: on every actor near the player, it reads the spells working on it each frame (as Tamriel
# Data's actor_magic.lua does), runs the steps as an effect lands, each second while it lasts and as it ends,
# and asks the global script for what only the world can do.
ACTOR_LUA = '''-- Made by Morrowind Workshop: what your own magic effects do (Create > New magic effect).
-- Runs on every actor near the player: reads the spells working on it, as Tamriel Data's own effects do.
local core = require('openmw.core')
local nearby = require('openmw.nearby')
local self = require('openmw.self')
local types = require('openmw.types')
local util = require('openmw.util')

local FT = ''' + str(FT) + '''
local Actor = types.Actor

%s
local DOES = {
%s
}

local active = {}          -- spell:index -> { d = steps, mag, caster, tick, fight }

local function change(stat, amount)
  local s = Actor.stats.dynamic[stat](self)
  local top = s.base + s.modifier
  local v = s.current + amount
  if amount > 0 and v > top then v = math.max(s.current, top) end
  s.current = v
end

local function isKind(only)
  if only == nil or only == 'any' then return true end
  local player = types.Player.objectIsInstance(self)
  if only == 'player' then return player end
  if only == 'notplayer' then return not player end
  if only == 'npc' then return types.NPC.objectIsInstance(self) end
  if not types.Creature.objectIsInstance(self) then return false end
  if only == 'creature' then return true end
  local t = types.Creature.record(self).type
  if only == 'undead' then return t == types.Creature.TYPE.Undead end
  if only == 'daedra' then return t == types.Creature.TYPE.Daedra end
  return true
end

local function world(kind, data)
  local out = {}
  for k, v in pairs(data or {}) do if k ~= 'fn' then out[k] = v end end      -- (a copy: the steps' own tables stay as they are)
  out.kind = kind
  out.actor = self.object
  core.sendGlobalEvent('WS_MyEffectWorld', out)
end

-- moved a little each frame by the global script, to the furthest point short of a wall
local function moveBy(dir, dist, up, time)
  local from = self.position + util.vector3(0, 0, 40)
  local to = from + dir * dist
  local hit = nearby.castRay(from, to, { ignore = self.object, collisionType = nearby.COLLISION_TYPE.World + nearby.COLLISION_TYPE.Door + nearby.COLLISION_TYPE.Actor })
  if hit.hit and hit.hitPos then
    local back = (hit.hitPos - from):length() - 40
    to = from + dir * math.max(0, back)
  end
  world('move', { to = to - util.vector3(0, 0, 40), arc = up or 0, time = time or 0.35 })
end

local function flatDir(a, b)
  local v = b - a
  v = util.vector3(v.x, v.y, 0)
  if v:length() < 1 then
    local yaw = self.rotation:getYaw()
    return util.vector3(math.sin(yaw), math.cos(yaw), 0)
  end
  return v:normalize()
end

local function feet(d, mag)
  return ((d.feet and d.feet > 0) and d.feet or mag) * FT
end

local function ctxFor(st, dt, phase)
  local ctx = { self = self, caster = st.caster, magnitude = st.mag, dt = dt, phase = phase,
                core = core, types = types, util = util, nearby = nearby, state = st.user }
  ctx.change = change
  ctx.world = world
  ctx.message = function(text) world('message', { text = text }) end
  ctx.push = function(ft) local c = st.caster and st.caster:isValid() and st.caster.position or self.position; moveBy(flatDir(c, self.position), (ft or st.mag) * FT, 40) end
  ctx.pull = function(ft) if st.caster and st.caster:isValid() then local d = math.max(0, math.min((ft or st.mag) * FT, (st.caster.position - self.position):length() - 90)); moveBy(flatDir(self.position, st.caster.position), d, 20) end end
  ctx.launch = function(ft) moveBy(util.vector3(0, 0, 1), (ft or st.mag) * FT, 0, 0.3) end
  ctx.dash = function(ft) local yaw = self.rotation:getYaw(); moveBy(util.vector3(math.sin(yaw), math.cos(yaw), 0), (ft or st.mag) * FT, 0, 0.25) end
  ctx.scale = function(f) world('scale', { factor = f }) end
  ctx.weather = function(name) world('weather', { weather = name }) end
  ctx.cast = function(id) world('cast', { id = id, caster = st.caster }) end
  return ctx
end

local function run(d, st, dt, phase)
  if not isKind(d.only) then return end
  if d.chance and d.chance < 100 and math.random() * 100 >= d.chance then return end
  local k, mag = d.kind, st.mag
  if k == 'health' or k == 'magicka' or k == 'fatigue' then
    change(k, d.sign * mag * (phase == 'second' and dt or 1))
  elseif k == 'push' then
    local c = st.caster and st.caster:isValid() and st.caster.position or self.position
    moveBy(flatDir(c, self.position), feet(d, mag), 40)
  elseif k == 'pull' then
    if st.caster and st.caster:isValid() then
      local d2 = math.max(0, math.min(feet(d, mag), (st.caster.position - self.position):length() - 90))
      moveBy(flatDir(self.position, st.caster.position), d2, 20)
    end
  elseif k == 'launch' then
    moveBy(util.vector3(0, 0, 1), feet(d, mag), 0, 0.3)
  elseif k == 'dash' then
    local yaw = self.rotation:getYaw()
    moveBy(util.vector3(math.sin(yaw), math.cos(yaw), 0), feet(d, mag), 0, 0.25)
  elseif k == 'calm' or k == 'frenzy' then
    local f = Actor.stats.ai.fight(self)
    if st.fight == nil then st.fight = f.base end
    f.base = (k == 'calm') and 0 or 100
  elseif k == 'aura' then
    for _, other in ipairs(nearby.actors) do
      if other ~= self.object and other ~= st.caster and (other.position - self.position):length() <= d.feet * FT then
        other:sendEvent('WS_MyEffectStat', { stat = d.stat, amount = d.sign * mag })
      end
    end
  elseif k == 'leech' then
    change(d.stat, -mag)
    if st.caster and st.caster:isValid() and st.caster ~= self.object then
      st.caster:sendEvent('WS_MyEffectStat', { stat = d.stat, amount = mag })
    end
  elseif k == 'cast' then
    world('cast', { id = d.id, caster = st.caster })
  elseif k == 'scale' then
    world('scale', { factor = d.factor })
    st.scaled = true
  elseif k == 'swap' then
    if st.caster and st.caster:isValid() and st.caster ~= self.object then world('swap', { other = st.caster }) end
  elseif k == 'lua' then
    if d.fn then
      local ok, err = pcall(d.fn, ctxFor(st, dt, phase))
      if not ok then print('[Workshop] ' .. tostring(st.id) .. ' (your Lua): ' .. tostring(err)) end
    end
  else
    world(k, d)          -- teleport, spawn, global, message, weather: the world's
  end
end

local function each(st, phase, dt)
  for _, d in ipairs(st.d) do
    local w = d.when or 'land'
    if w == phase or (phase == 'second' and w == 'second' and (d.kind == 'health' or d.kind == 'magicka' or d.kind == 'fatigue')) then
      run(d, st, dt, phase)
    end
  end
end

local function finish(st)
  each(st, 'end', 0)
  if st.fight ~= nil then Actor.stats.ai.fight(self).base = st.fight end
  if st.scaled then world('unscale', {}) end
end

return {
  engineHandlers = {
    onUpdate = function(dt)
      if dt <= 0 then return end
      local now = {}
      for _, spell in pairs(Actor.activeSpells(self)) do
        for _, effect in pairs(spell.effects) do
          local d = DOES[effect.id]
          if d then
            local key = tostring(spell.activeSpellId) .. ':' .. tostring(effect.index)
            now[key] = true
            local st = active[key]
            local mag = effect.magnitudeThisFrame or effect.magnitude or 0
            if not st then
              st = { d = d, mag = mag, caster = spell.caster, tick = 0, id = effect.id, user = {} }
              active[key] = st
              each(st, 'land', dt)
            end
            st.mag = mag
            -- each second while it lasts: the stats smoothly, the rest once a second
            for _, s in ipairs(d) do
              if (s.when == 'second') and (s.kind == 'health' or s.kind == 'magicka' or s.kind == 'fatigue') then run(s, st, dt, 'second') end
            end
            st.tick = st.tick + dt
            if st.tick >= 1 then
              st.tick = st.tick - 1
              for _, s in ipairs(d) do
                if s.when == 'second' and not (s.kind == 'health' or s.kind == 'magicka' or s.kind == 'fatigue') then run(s, st, 1, 'second') end
              end
            end
          end
        end
      end
      for key, st in pairs(active) do
        if not now[key] then
          finish(st)
          active[key] = nil
        end
      end
    end,
  },
  eventHandlers = {
    WS_MyEffectStat = function(data) change(data.stat, data.amount) end,
  },
}
'''

GLOBAL_LUA = '''-- Made by Morrowind Workshop: what your own magic effects do in the world (Create > New magic effect).
local core = require('openmw.core')
local types = require('openmw.types')
local util = require('openmw.util')
local world = require('openmw.world')

local moving = {}          -- actor id -> { actor, from, to, arc, t, time }
local scaled = {}          -- actor id -> the scale it had

local function player() return world.players[1] end

local function weatherRecord(name)
  local ok, rec = pcall(function() return core.weather.records[name] end)
  if ok and rec then return rec end
  for _, r in pairs(core.weather.records) do
    local id = tostring(r.recordId or r.id or r.name or ''):lower():gsub('[^a-z]', '')
    if id == name then return r end
  end
  return nil
end

local DO = {
  move = function(a, d) moving[a.id] = { actor = a, from = a.position, to = d.to, arc = d.arc or 0, t = 0, time = d.time or 0.35 } end,
  teleport = function(a, d) a:teleport(d.cell, util.vector3(d.x, d.y, d.z)) end,
  spawn = function(a, d)
    local yaw = a.rotation:getYaw()
    world.createObject(d.id, 1):teleport(a.cell, a.position + util.vector3(math.sin(yaw) * 90, math.cos(yaw) * 90, 0))
  end,
  global = function(a, d) world.mwscript.getGlobalVariables(player())[d.name] = d.value end,
  message = function(a, d) player():sendEvent('WS_MyEffectMessage', { text = d.text }) end,
  scale = function(a, d)
    if scaled[a.id] == nil then scaled[a.id] = a.scale end
    a:setScale(scaled[a.id] * d.factor)
  end,
  unscale = function(a, d) if scaled[a.id] ~= nil then a:setScale(scaled[a.id]); scaled[a.id] = nil end end,
  weather = function(a, d)
    local region = a.cell and a.cell.region
    local rec = weatherRecord(d.weather)
    if region and rec then core.weather.changeWeather(region, rec) end
  end,
  swap = function(a, d)
    local o = d.other
    if not (o and o:isValid()) then return end
    local pa, pb, ca, cb = a.position, o.position, a.cell, o.cell
    a:teleport(cb, pb)
    o:teleport(ca, pa)
  end,
  transmute = function(a, d)
    local inv = types.Actor.inventory(a)
    for _, p in ipairs(d.pairs or {}) do
      local item = inv:find(p.from)
      if item and item.count > 0 then
        local n = math.min(d.count or 1, item.count)
        item:remove(n)
        world.createObject(p.to, n):moveInto(inv)
        if types.Player.objectIsInstance(a) then a:sendEvent('WS_MyEffectMessage', { text = 'Transmuted.' }) end
        return
      end
    end
  end,
  cast = function(a, d)
    local rec = core.magic.spells.records[d.id]
    if not rec then return end
    local idx = {}
    for i = 1, #rec.effects do idx[i] = i - 1 end
    types.Actor.activeSpells(a):add({ id = d.id, effects = idx, caster = d.caster or a })
  end,
}

return {
  engineHandlers = {
    onUpdate = function(dt)
      for id, m in pairs(moving) do
        if not m.actor:isValid() then
          moving[id] = nil
        else
          m.t = math.min(m.time, m.t + dt)
          local f = m.t / m.time
          local p = m.from + (m.to - m.from) * f + util.vector3(0, 0, math.sin(f * math.pi) * m.arc)
          local ok = pcall(function() m.actor:teleport(m.actor.cell, p) end)
          if not ok or m.t >= m.time then moving[id] = nil end
        end
      end
    end,
    onSave = function() return { scaled = scaled } end,
    onLoad = function(data) if data and data.scaled then scaled = data.scaled end end,
  },
  eventHandlers = {
    WS_MyEffectWorld = function(data)
      local a = data.actor
      local f = DO[data.kind]
      if not (f and a and a:isValid()) then return end
      local ok, err = pcall(f, a, data)
      if not ok then print('[Workshop] magic effect ' .. tostring(data.kind) .. ': ' .. tostring(err)) end
    end,
  },
}
'''

PLAYER_LUA = '''-- Made by Morrowind Workshop: the messages your own magic effects show (Create > New magic effect).
local ui = require('openmw.ui')

return {
  eventHandlers = {
    WS_MyEffectMessage = function(data)
      ui.showMessage(data.text)
    end,
  },
}
'''
