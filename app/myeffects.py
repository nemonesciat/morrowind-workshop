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
  resurrect                    the dead near the one it lands on stand up again, with what was left on them
                               (made again where they lay: OpenMW's Lua has no Resurrect), as they were or
                               following the caster
  cast                         a spell of the game's (or yours) cast on them: chains and combos
  weather                      the region's weather changes (a storm, ash, blight, snow...)
  quake                        the ground shakes where it lands for so many seconds: the player's view shakes, the
                               game's rumble plays, people stagger (some fall) and small loose things hop and
                               settle a little apart (Settle's rules: never furniture or anything hung)
  teleport / spawn / global / message   as before
  lua                          your own code, with helpers (ctx.push, ctx.launch, ctx.scale, ctx.change...)

Kept in the mod's Lua scripts: "my_effects" (kind LOAD) holds the list as JSON between markers and makes the
effects; "my_effects_actor", "my_effects_global" and "my_effects_player" are written from it. The spell,
enchantment and potion editors offer the effects (tdeffects.effects lists them with Tamriel Data's), and a
record using one carries its template meanwhile, put right as the game loads by the "td_effects" script."""
import json
import re
import struct

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
    ('resurrect', 'Raise the dead', 'The dead within so many feet of the one it lands on (cast on Self: of you) stand up again, carrying '
                  'what was left on them: what was looted stays taken. As they were, or on your side, following you.'),
    ('cast', 'Cast a spell on them', 'Another spell (the game\'s, or one of yours) cast on them: for chains and combos.'),
    ('weather', 'Change the weather', 'The region\'s weather turns to a storm, ash, blight, snow, rain or clear skies.'),
    ('quake', 'Quake', 'The ground shakes where it lands, for so many seconds: the player\'s view shakes and the game\'s rumble plays, '
              'people and creatures stagger (some fall), and small loose things on tables and shelves hop about and settle a little '
              'apart. Furniture, building pieces and anything hung stay put.'),
    ('transmute', 'Transmute', 'One of the first item it finds in their inventory, of the pairs you list (iron ore into silver, silver into gold...), becomes the next.'),
    ('teleport', 'Teleport', 'Send the one it lands on to a place: a cell and a spot in it.'),
    ('summon', 'Summon', 'A creature or person (or one from a random creature list) appears beside the caster, follows and fights for them, '
               'and vanishes when the effect ends, when the caster dies, or when it is cast again, as the game\'s own summons do.'),
    ('spawn', 'Place something', 'Place an object or a creature beside the one it lands on, to stay.'),
    ('global', 'Set a global variable', 'Set one of the game\'s global variables, so an MWScript or a dialogue line can react.'),
    ('message', 'Show a message', 'Show a line of text to the player.'),
    ('lua', 'Lua of your own', 'Your own code, run when you choose, with helpers for the steps above. The Assistant can write it from a description.'),
]
# (where each kind is done: on the actor itself, or by the global script for what only the world can do)
WORLD = ('teleport', 'spawn', 'summon', 'global', 'message', 'scale', 'weather', 'swap', 'transmute', 'resurrect')
FT = 22.1                     # (game units to a foot, as Tamriel Data's Blink reckons it)
# (a quake's rumble: the first of the game's own the load order has, looped; the end game's Red Mountain rumble
# first. Falling stones now and then, from the regions' rock sounds)
RUMBLES = ('endrumble', 'volcano rumble', 'rumble1', 'rumble2', 'rumble3', 'rumble4')
ROCKS = tuple('rocks%d' % i for i in range(1, 9))


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
        if int(key) not in out:
            continue
        look = {}
        for st, sd in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
            sd = bytes(sd)
            if st == 'ITEX':
                out[int(key)]['icon'] = zstr(sd)
            elif st in LOOK_SUBS:
                look[LOOK_SUBS[st]] = zstr(sd)
            elif st == 'MEDT' and len(sd) >= 36:
                _school, _cost, _flags, red, green, blue, speed, _size, _cap = struct.unpack_from('<ifiiiifff', sd)
                look['color'] = [red, green, blue]
                look['speed'] = round(speed, 3)
        # (a sound left blank is its school's: "destruction cast", "destruction bolt"... as the game plays it)
        school = (out[int(key)].get('school') or '').lower()
        for k, part in (('castSound', 'cast'), ('boltSound', 'bolt'), ('hitSound', 'hit'), ('areaSound', 'area')):
            if not look.get(k) and school and db.resolve_id('%s %s' % (school, part)) is not None:
                look[k] = db.recs[db.resolve_id('%s %s' % (school, part))][1]
        out[int(key)]['look'] = look
    _vcache.update(recs=db.recs, out=out)
    return out


# the parts of an effect's look: its record's subrecord, and the field OpenMW's Lua gives it
LOOK_SUBS = {'CVFX': 'castStatic', 'BVFX': 'bolt', 'HVFX': 'hitStatic', 'AVFX': 'areaStatic', 'CSND': 'castSound', 'BSND': 'boltSound',
             'HSND': 'hitSound', 'ASND': 'areaSound', 'PTEX': 'particle'}
LOOK_STATICS = ('castStatic', 'bolt', 'hitStatic', 'areaStatic')
LOOK_SOUNDS = ('castSound', 'boltSound', 'hitSound', 'areaSound')


def templates(db):
    """The game's effects to start from, for the maker: [{index, name, school, cost, icon, magnitude, duration}]."""
    v = _vanilla(db)
    return sorted(({k: e.get(k, {} if k == 'look' else None) for k in ('index', 'name', 'school', 'cost', 'icon', 'magnitude', 'duration', 'look')}
                   for e in v.values()), key=lambda e: (e['school'], e['name']))


def _look(db, look):
    """An effect's own look (the parts that differ from the one it looks like): the game's visuals and
    sounds by their IDs, a particle texture, a colour, a bolt speed. Unknown visuals or sounds are refused."""
    out = {}
    for k in LOOK_STATICS + LOOK_SOUNDS:
        v = ((look or {}).get(k) or '').strip()
        if not v:
            continue
        ri = db.resolve_id(v)
        # (a bolt is a projectile, which the game keeps as a weapon record; the other visuals are statics)
        want = ('WEAP', 'STAT') if k == 'bolt' else ('STAT',) if k in LOOK_STATICS else ('SOUN',)
        if ri is None or db.recs[ri][0] not in want:
            raise EditError('There is no %s called "%s".' % ('sound' if want == ('SOUN',) else 'visual effect', v))
        out[k] = db.recs[ri][1]
    p = ((look or {}).get('particle') or '').strip()
    if p:
        out['particle'] = p[:200]
    c = (look or {}).get('color')
    if isinstance(c, (list, tuple)) and len(c) == 3:
        out['color'] = [max(0, min(255, int(x))) for x in c]
    s = (look or {}).get('speed')
    if s not in (None, ''):
        out['speed'] = max(0.0, min(10.0, float(s)))
    return out


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
    elif k == 'resurrect':
        # (the game's magic doesn't land on the dead, so it raises those near the one it lands on)
        out['feet'] = max(1.0, min(200.0, _num(d.get('feet'), label + ': the reach', 15.0)))
        out['which'] = 'all' if d.get('which') == 'all' else 'one'
        out['health'] = max(1.0, min(100.0, _num(d.get('health'), label + ': their health', 100.0)))
        out['side'] = 'ally' if d.get('side') == 'ally' else 'own'
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
    elif k == 'quake':
        # (2026-10-25, the user: "don't want all the furniture and whatnot flying off the shelves": only small
        # loose things move, a few units, and rest on what is under them)
        out['feet'] = max(5.0, min(300.0, _num(d.get('feet'), label + ': the radius', 30.0)))
        out['strength'] = max(1.0, min(10.0, _num(d.get('strength'), label + ': the strength', 5.0)))
        out['seconds'] = max(1.0, min(120.0, _num(d.get('seconds'), label + ': how long', 10.0)))
        out['sound'] = next((s for s in RUMBLES if db.resolve_id(s) is not None), '')
        out['rocks'] = [s for s in ROCKS if db.resolve_id(s) is not None]
        out['when'] = 'land'
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
    elif k == 'summon':
        sid = (d.get('id') or '').strip()
        ri = db.resolve_id(sid) if sid else None
        if ri is None or db.recs[ri][0] not in ('CREA', 'NPC_', 'LEVC'):
            raise EditError('Summon: there is no creature, person or random creature list called "%s".' % sid)
        out['id'] = db.recs[ri][1]
        out['list'] = db.recs[ri][0] == 'LEVC'
        out['count'] = max(1, min(5, int(_num(d.get('count'), 'Summon: how many', 1))))
        out['when'] = 'land'
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
            'look': _look(db, e.get('look')),
            # (which of the game's effects each part was taken from, for the maker's menus: several share a part)
            'look_from': {k: int(x) for k, x in (e.get('look_from') or {}).items() if str(x).lstrip('-').isdigit()},
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
        look = dict(e.get('look') or {})
        if look.get('particle'):
            look['particle'] = look['particle'].replace('\\', '/')
        defs.append('  { id = %s, template = %s, name = %s, baseCost = %s, icon = %s, description = %s, hasMagnitude = %s, hasDuration = %s, look = %s },'
                    % (_lua(e['id']), _lua(t['key']), _lua(e['name']), _lua(e['cost']), _lua(e['icon'].replace('\\', '/')),
                       _lua(e['description']), _lua(e['magnitude']), _lua(e['duration']), _lua(look)))
    load = ('-- Made by Morrowind Workshop: your own magic effects (Create > New magic effect).\n'
            '-- Each is made as the game loads, from one of the game\'s effects for its looks; what it does is in %s.lua.\n'
            '-- Needs OpenMW 0.50 or newer.\n%s\n%s\n%s\n\n'
            'local content = require(\'openmw.content\')\nlocal hasUtil, util = pcall(require, \'openmw.util\')\n\nlocal EFFECTS = {\n%s\n}\n\n'
            'return {\n  engineHandlers = {\n    onContentFilesLoaded = function()\n'
            '      local records = content.magicEffects.records\n'
            '      for _, e in ipairs(EFFECTS) do\n'
            '        local ok, err = pcall(function()\n'
            '          local params = { template = records[e.template], name = e.name, baseCost = e.baseCost, icon = e.icon,\n'
            '                           description = e.description, hasMagnitude = e.hasMagnitude, hasDuration = e.hasDuration,\n'
            '                           allowsSpellmaking = true, allowsEnchanting = true }\n'
            '          -- its own look, part by part (the rest is the template\'s): visuals and sounds by the game\'s IDs\n'
            '          for k, v in pairs(e.look or {}) do\n'
            '            if k == \'color\' then\n'
            '              if hasUtil then params.color = util.color.rgb(v[1] / 255, v[2] / 255, v[3] / 255) end\n'
            '            else\n'
            '              params[k] = v\n'
            '            end\n'
            '          end\n'
            '          records[e.id] = params\n'
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
            # (a summon knows its step, so two summons in one effect each call their own)
            steps.append('    ' + _row(dict(d, n=n) if d['kind'] == 'summon' else d, fn) + ',')
            if d['kind'] == 'message':
                msgs = True
        if steps:
            rows.append('  [%s] = {\n%s\n  },' % (_lua(e['id'].lower()), '\n'.join(steps)))
    _put(db, ACTOR, 'NPC, CREATURE, PLAYER', (ACTOR_LUA % ('\n'.join(fns), '\n'.join(rows))) if rows else None)
    quake = any(d['kind'] == 'quake' for e in lst for d in e['does'])
    _put(db, GLOBAL, 'GLOBAL', GLOBAL_LUA.replace('local HUNG = {}', 'local HUNG = %s' % _hung(db) if quake else 'local HUNG = {}') if rows else None)
    _put(db, PLAYER, 'PLAYER', PLAYER_LUA if (rows and (msgs or quake or any(d['kind'] in ('lua', 'transmute', 'resurrect') for e in lst for d in e['does']))) else None)


def _hung(db):
    """The models the game hangs (hangsurvey: clear of anything under them in most of its places), as a Lua set
    for a quake's loose things; those its name rules leave out anyway (furniture, building pieces, plants) are
    left out of the list. While the survey isn't done yet, the names alone (it starts in the background)."""
    import hangsurvey
    S = hangsurvey.ready(db)
    skip = re.compile(r'(^|/)(in_|ex_)|furn|flora|_in_|_ex_')
    hung = sorted(m for m, st in ((S or {}).get('models') or {}).items() if st.get('hung', 0) >= 0.6 and not skip.search(m))
    return '{\n%s\n}' % ''.join('  [%s] = true,\n' % _lua(m) for m in hung).rstrip('\n') if hung else '{}'


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
  elseif k == 'summon' then
    -- (keyed by this actor and the spell, so a game loaded while it lasts doesn't call a second one)
    local spell = tostring(self.id) .. ':' .. st.key
    world('summon', { id = d.id, list = d.list, count = d.count, spell = spell, key = spell .. ':' .. tostring(d.n or 0), eff = st.id, caster = st.caster or self.object })
    st.summoned = true
  elseif k == 'resurrect' then
    world('resurrect', { feet = d.feet, which = d.which, health = d.health, side = d.side, caster = st.caster or self.object })
  elseif k == 'quake' then
    -- (where it lands is the middle of it: on Self, the caster; the world finds the loose things, the player's script shakes them)
    world('quake', { feet = d.feet, strength = d.strength, seconds = d.seconds, sound = d.sound, rocks = d.rocks, caster = st.caster })
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
  if st.summoned then world('unsummon', { spell = tostring(self.id) .. ':' .. st.key }) end
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
              st = { d = d, mag = mag, caster = spell.caster, tick = 0, id = effect.id, key = key, user = {} }
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
    -- a quake under their feet, once a second: tired out (enough of it and they fall, as from a fatigue drain)
    -- and knocked a step or two any way, stopping at walls
    WS_MyEffectStagger = function(data)
      local s = data.strength or 5
      change('fatigue', -s * 8 * (0.5 + math.random()) * (data.fade or 1))
      if math.random() < 0.6 then
        local a = math.random() * 2 * math.pi
        moveBy(util.vector3(math.cos(a), math.sin(a), 0), s * (2 + math.random() * 6) * (data.fade or 1), 6, 0.25)
      end
    end,
    -- raised from the dead (the global script made this one where the corpse lay): back on their feet with
    -- what the corpse had on, at the health asked for, and on the caster's side if asked
    WS_MyEffectRaised = function(data)
      if data.equip and next(data.equip) then
        local inv, eq = Actor.inventory(self), {}
        for slot, rid in pairs(data.equip) do
          local item = inv:find(rid)
          if item then eq[slot] = item end
        end
        pcall(Actor.setEquipment, self, eq)
      end
      local h = Actor.stats.dynamic.health(self)
      h.current = math.max(1, (h.base + h.modifier) * (data.health or 100) / 100)
      if data.side == 'ally' and data.caster and data.caster:isValid() then
        Actor.stats.ai.fight(self).base = 0
        local ok, I = pcall(require, 'openmw.interfaces')
        if ok and I.AI then
          I.AI.removePackages('Combat')
          I.AI.startPackage({ type = 'Follow', target = data.caster })
        end
      end
    end,
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
local summoned = {}        -- actor:spell key -> { caster, eff, objects, told }
local hopping = {}         -- thing id -> { obj, from, to, rot, yaw, arc, t, time }: a quake's loose things
local quakes = {}          -- { pos, cell, reach, at }: an area spell landing on five people starts one quake

local function player() return world.players[1] end

-- what a quake may shake loose, as Settle reckons it (settle.loose): an item, a candle or small lamp standing on
-- something, a small container or bit of clutter; never furniture, a building piece, a plant, a door, a person,
-- or a model the game hangs (hangsurvey, written in by the Workshop) or whose name says it hangs
local HUNG = {}
local HANG_WORDS = { 'anchor', 'hanging', 'hang_', '_hang', 'chain', 'cage', 'chandelier', 'lantern', 'sconce' }
local PLANT_WORDS = { 'flora', 'plant', 'kelp', 'mushroom', 'shrub', 'grass', 'lilypad', 'moss', 'vine', 'ivy', 'root_', 'roots' }
local BUILT = { '_in_', '_ex_', '_i_', '_x_', 'furn' }
local LOOSE_TYPES = { types.Miscellaneous, types.Book, types.Potion, types.Ingredient, types.Apparatus, types.Weapon, types.Armor,
                      types.Clothing, types.Lockpick, types.Probe, types.Repair, types.Light, types.Container, types.Activator, types.Static }
local MAX_LOOSE = 50

local function has(s, words)
  for _, w in ipairs(words) do if s:find(w, 1, true) then return true end end
  return false
end

local function sizeOf(o)
  local ok, b = pcall(function() return o:getBoundingBox() end)
  if not ok or not b then return nil end
  return math.max(b.halfSize.x, b.halfSize.y, b.halfSize.z) * 2
end

local function looseThing(o, T)
  if o.count == 0 or o.enabled == false then return false end
  local id = tostring(o.recordId):lower()
  if has(id, PLANT_WORDS) then return false end
  local okR, rec = pcall(function() return T.record(o) end)
  if not (okR and rec) then return false end
  local model = string.lower(rec.model or ''):gsub('\\\\', '/'):gsub('^meshes/', '')
  if HUNG[model] or has(model .. ' ' .. id, HANG_WORDS) or (id:find('bell', 1, true) and not id:find('belly', 1, true)) then return false end
  if T == types.Light then
    local size = sizeOf(o)
    return rec.isCarriable == true and size ~= nil and size <= 40
  end
  if T == types.Ingredient then return not id:find('flor', 1, true) end
  if T == types.Container or T == types.Activator or T == types.Static then
    if id:sub(1, 3) == 'in_' or id:sub(1, 3) == 'ex_' or has(id, BUILT) then return false end
    local size = sizeOf(o)
    return size ~= nil and size <= 140
  end
  return true
end

-- the game's own summoning flash, where it has one
local function flash(id, pos)
  pcall(function()
    local rec = types.Static.record(id)
    if rec and rec.model then world.vfx.spawn(rec.model, pos) end
  end)
end

-- a summon's time is up: what it called goes, in the game's flash
local function dismiss(key)
  local s = summoned[key]
  summoned[key] = nil
  if not s then return end
  for _, o in ipairs(s.objects or {}) do
    if o:isValid() and o.count > 0 then
      flash('VFX_Summon_End', o.position)
      o:remove()
    end
  end
end

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
  summon = function(a, d)
    local c = (d.caster and d.caster:isValid()) and d.caster or a
    if summoned[d.key] then return end
    -- (cast again: the ones called before go, as the game's own summons do)
    for key, s in pairs(summoned) do
      if s.caster == c and s.eff == d.eff and s.spell ~= d.spell then dismiss(key) end
    end
    local n, objs = d.count or 1, {}
    for i = 1, n do
      local rid = d.id
      if d.list then
        local ok, r = pcall(function() return types.LevelledCreature.record(d.id):getRandomId(types.Actor.stats.level(c).current) end)
        rid = ok and r or nil
      end
      if rid and rid ~= '' then
        -- (in front of the caster, side by side when there are several)
        local yaw = c.rotation:getYaw() + (i - 1 - (n - 1) / 2) * 0.6
        local pos = c.position + util.vector3(math.sin(yaw) * 110, math.cos(yaw) * 110, 0)
        local o = world.createObject(rid, 1)
        o:teleport(c.cell, pos, c.rotation)
        flash('VFX_Summon_Start', pos)
        objs[#objs + 1] = o
      end
    end
    summoned[d.key] = { caster = c, eff = d.eff, spell = d.spell, objects = objs, told = false }
  end,
  unsummon = function(a, d)
    for key, s in pairs(summoned) do
      if s.spell == d.spell then dismiss(key) end
    end
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
  -- raise the dead near the one it landed on. The engine's own Resurrect isn't open to Lua, so the same
  -- character is made again where the corpse lies, the corpse's own things moved onto them (what was
  -- looted stays taken, what they still wore is put back on) and the corpse taken away
  resurrect = function(a, d)
    local reach = (d.feet or 15) * ''' + str(FT) + '''
    local dead = {}
    for _, T in ipairs({ types.NPC, types.Creature }) do
      for _, c in ipairs(a.cell:getAll(T)) do
        if c ~= a and c.count > 0 and not types.Player.objectIsInstance(c) and types.Actor.isDead(c) then
          local dist = (c.position - a.position):length()
          if dist <= reach then dead[#dead + 1] = { c = c, dist = dist } end
        end
      end
    end
    table.sort(dead, function(x, y) return x.dist < y.dist end)
    if #dead == 0 then
      if types.Player.objectIsInstance(a) then a:sendEvent('WS_MyEffectMessage', { text = 'No one lies dead near enough.' }) end
      return
    end
    for i, e in ipairs(dead) do
      if d.which ~= 'all' and i > 1 then break end
      local c = e.c
      local cinv = types.Actor.inventory(c)
      pcall(function() cinv:resolve() end)
      local equip = {}
      local okE, eq = pcall(types.Actor.getEquipment, c)
      if okE and eq then for slot, item in pairs(eq) do equip[slot] = item.recordId end end
      local n = world.createObject(c.recordId, 1)
      n:teleport(c.cell, c.position, c.rotation)
      -- (what their record gives them taken away first: only the corpse's things come back with them)
      local ninv = types.Actor.inventory(n)
      pcall(function() ninv:resolve() end)
      for _, item in ipairs(ninv:getAll()) do item:remove() end
      for _, item in ipairs(cinv:getAll()) do item:moveInto(ninv) end
      c:remove()
      n:sendEvent('WS_MyEffectRaised', { equip = equip, health = d.health, side = d.side, caster = d.caster })
    end
  end,
  -- a quake where it landed: the loose things within reach (the nearest MAX_LOOSE) handed to the player's
  -- script, which shakes the view, plays the rumble, staggers people and hops the things (it can cast rays)
  quake = function(a, d)
    local now = core.getSimulationTime()
    local reach = (d.feet or 30) * ''' + str(FT) + '''
    for i = #quakes, 1, -1 do
      local q = quakes[i]
      if now - q.at > 2 then table.remove(quakes, i)
      elseif q.cell == a.cell and (q.pos - a.position):length() < q.reach then return end
    end
    quakes[#quakes + 1] = { pos = a.position, cell = a.cell, reach = reach, at = now }
    local cells = { a.cell }
    if a.cell.isExterior then
      pcall(function() local all = {}; for _, c in ipairs(world.activeCells) do all[#all + 1] = c end; if #all > 0 then cells = all end end)
    end
    local near = {}
    for _, c in ipairs(cells) do
      for _, T in ipairs(LOOSE_TYPES) do
        for _, o in ipairs(c:getAll(T)) do
          local dist = (o.position - a.position):length()
          if dist <= reach and looseThing(o, T) then near[#near + 1] = { o = o, dist = dist } end
        end
      end
    end
    table.sort(near, function(x, y) return x.dist < y.dist end)
    local things = {}
    for i = 1, math.min(MAX_LOOSE, #near) do things[i] = near[i].o end
    player():sendEvent('WS_MyEffectQuake', { pos = a.position, ext = a.cell.isExterior, cellName = a.cell.name, reach = reach,
                                             strength = d.strength or 5, seconds = d.seconds or 10, sound = d.sound, rocks = d.rocks,
                                             things = things, caster = d.caster })
  end,
  -- one of a quake's loose things hops a few units and lands where the player's script found a surface
  hop = function(a, d)
    if a.cell == nil then return end
    hopping[a.id] = { obj = a, from = a.position, to = d.to, rot = a.rotation, yaw = d.yaw or 0, arc = d.arc or 0, t = 0, time = d.time or 0.12 }
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
      for id, h in pairs(hopping) do
        if not h.obj:isValid() or h.obj.count == 0 or h.obj.cell == nil then
          hopping[id] = nil          -- (picked up mid-hop)
        else
          h.t = math.min(h.time, h.t + dt)
          local f = h.t / h.time
          local p = h.from + (h.to - h.from) * f + util.vector3(0, 0, math.sin(f * math.pi) * h.arc)
          local ok = pcall(function() h.obj:teleport(h.obj.cell, p, util.transform.rotateZ(h.yaw * f) * h.rot) end)
          if not ok or h.t >= h.time then hopping[id] = nil end
        end
      end
      for key, s in pairs(summoned) do
        if not (s.caster and s.caster:isValid()) or types.Actor.isDead(s.caster) then
          dismiss(key)          -- (the caster died: their summons go with them)
        elseif not s.told then
          -- (a frame after they were made, once their own scripts run: on the caster's side, following)
          s.told = true
          for _, o in ipairs(s.objects) do
            if o:isValid() then o:sendEvent('WS_MyEffectRaised', { health = 100, side = 'ally', caster = s.caster }) end
          end
        end
      end
    end,
    onSave = function() return { scaled = scaled, summoned = summoned } end,
    onLoad = function(data)
      if data and data.scaled then scaled = data.scaled end
      if data and data.summoned then summoned = data.summoned end
    end,
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

PLAYER_LUA = '''-- Made by Morrowind Workshop: the messages your own magic effects show, and their quakes (Create > New magic effect).
local ambient = require('openmw.ambient')
local camera = require('openmw.camera')
local core = require('openmw.core')
local nearby = require('openmw.nearby')
local self = require('openmw.self')
local types = require('openmw.types')
local ui = require('openmw.ui')
local util = require('openmw.util')

local quakes = {}          -- the quakes going on: { pos, reach, s, T, t, things, ... }
local shake = { p = 0, y = 0, r = 0 }          -- (the view's jitter now: added to what other mods set, and taken off again)
local RAY = nearby.COLLISION_TYPE.World + nearby.COLLISION_TYPE.HeightMap

local function setShake(p, y, r)
  pcall(function() camera.setExtraPitch(camera.getExtraPitch() - shake.p + p) end)
  pcall(function() camera.setExtraYaw(camera.getExtraYaw() - shake.y + y) end)
  pcall(function() camera.setExtraRoll(camera.getExtraRoll() - shake.r + r) end)
  shake.p, shake.y, shake.r = p, y, r
end

-- the surface under a point (a table top, a shelf's board, the floor), the thing itself left out
local function surfaceUnder(p, obj)
  local hit = nearby.castRay(p + util.vector3(0, 0, 2), p - util.vector3(0, 0, 40), { ignore = obj, collisionType = RAY })
  if hit.hit and hit.hitPos then return hit.hitPos.z end
  return nil
end

local function here(q)
  if q.ext then return self.cell.isExterior end
  return self.cell.name == q.cellName
end

local function start(d)
  local q = { pos = d.pos, ext = d.ext, cellName = d.cellName, reach = d.reach, s = d.strength or 5, T = d.seconds or 10, t = 0,
              caster = d.caster, sound = d.sound, rocks = d.rocks or {}, things = {}, beat = 0, moment = 0, stones = 2, jt = 0,
              aim = { p = 0, y = 0, r = 0 }, cur = { p = 0, y = 0, r = 0 } }
  -- each thing as it lies: where, and how far its middle is above what holds it (kept, so it lands as it lay)
  for _, o in ipairs(d.things or {}) do
    if o:isValid() and o.count > 0 then
      local z = surfaceUnder(o.position, o)
      if z then q.things[#q.things + 1] = { obj = o, home = o.position, z0 = z, off = o.position.z - z } end
    end
  end
  local dist = (self.position - q.pos):length()
  if q.sound and q.sound ~= '' and here(q) and dist <= q.reach * 2 then
    q.playing = pcall(ambient.playSound, q.sound, { loop = true, volume = math.min(1, 0.4 + q.s * 0.06) })
  end
  quakes[#quakes + 1] = q
end

local function stop(q)
  if q.playing then pcall(ambient.stopSound, q.sound) end
end

-- each moment, about a third of the loose things hop: a few units at most from where they lay, onto the same
-- surface (one with an edge or a step under the new spot hops straight up instead), turned a hair
local function jostle(q, fade)
  local j = 0.5 * q.s
  for _, th in ipairs(q.things) do
    local o = th.obj
    if o:isValid() and o.count > 0 and o.cell ~= nil and math.random() < 0.35 then
      local x = th.home.x + (math.random() * 2 - 1) * j * 1.5
      local y = th.home.y + (math.random() * 2 - 1) * j * 1.5
      local z = surfaceUnder(util.vector3(x, y, o.position.z), o)
      if not z or math.abs(z - th.z0) > 3 then x, y, z = o.position.x, o.position.y, th.z0 end
      core.sendGlobalEvent('WS_MyEffectWorld', { kind = 'hop', actor = o, to = util.vector3(x, y, z + th.off),
                                                 yaw = (math.random() * 2 - 1) * q.s * 0.006, arc = (0.5 + q.s * 0.35) * fade, time = 0.12 })
    end
  end
end

local function stagger(q, fade)
  for _, a in ipairs(nearby.actors) do
    if a ~= q.caster and (a.position - q.pos):length() <= q.reach and not types.Actor.isDead(a) then
      a:sendEvent('WS_MyEffectStagger', { strength = q.s, fade = fade })
    end
  end
end

return {
  engineHandlers = {
    onUpdate = function(dt)
      if dt <= 0 or #quakes == 0 then return end
      local p, y, r = 0, 0, 0
      for i = #quakes, 1, -1 do
        local q = quakes[i]
        q.t = q.t + dt
        if q.t >= q.T then
          stop(q)
          table.remove(quakes, i)
        else
          -- (up to full in half a second, full until six tenths through, then dying away)
          local fade = math.min(1, q.t / 0.5) * math.min(1, (q.T - q.t) / (q.T * 0.4))
          q.beat = q.beat + dt
          if q.beat >= 1 then q.beat = q.beat - 1; stagger(q, fade) end
          q.moment = q.moment + dt
          if q.moment >= 0.15 then q.moment = 0; jostle(q, fade) end
          local dist = (self.position - q.pos):length()
          if here(q) and dist <= q.reach * 1.5 then
            -- the view: a new aim every few hundredths of a second, eased into, smaller further from the middle
            local amp = q.s * 0.0025 * fade * (1 - dist / (q.reach * 1.5))
            q.jt = q.jt - dt
            if q.jt <= 0 then
              q.jt = 0.04
              q.aim = { p = (math.random() * 2 - 1) * amp, y = (math.random() * 2 - 1) * amp, r = (math.random() * 2 - 1) * amp * 0.6 }
            end
            local k = math.min(1, dt * 25)
            for _, n in ipairs({ 'p', 'y', 'r' }) do q.cur[n] = q.cur[n] + (q.aim[n] - q.cur[n]) * k end
            p, y, r = p + q.cur.p, y + q.cur.y, r + q.cur.r
            -- now and then stones falling somewhere
            q.stones = q.stones - dt
            if q.stones <= 0 and #q.rocks > 0 then
              q.stones = 2 + math.random() * 3
              pcall(ambient.playSound, q.rocks[math.random(#q.rocks)], { volume = 0.5 * fade + 0.2 })
            end
          end
        end
      end
      setShake(p, y, r)
    end,
  },
  eventHandlers = {
    WS_MyEffectMessage = function(data)
      ui.showMessage(data.text)
    end,
    WS_MyEffectQuake = function(data) start(data) end,
  },
}
'''
