"""Give spells to everyone who fits: every Telvanni mage in Sadrith Mora, every healer in the Ascadian Isles,
everyone who already knows Fireball, everyone with Destruction 50 or more.

People are picked by what they are (race, class, faction, a spell they know, a skill, selling spells) and by
where they stand (regions, towns), from their records and their placements in the game. Each person's
stats are their own where the record has them, or what the game works out for auto-calculated people.

Two ways of giving:
- "records": each person's record gets the spells in your mod. Simple, and the Construction Set shows it,
  but every one of them becomes an override, which can clash with another mod that changes the same people.
- "script": a small OpenMW Lua script gives the spells as each person comes near. No overrides, so it works
  beside any mod; the rules are kept in the script and can be changed or taken out. Needs an .omwaddon.
"""
import json
import struct

from editing import EditError, commit, _require_project
from esm import iter_subrecords, zstr
from project import join_subs
from database import SKILLS

SCRIPT = 'spell_gifts'
BEGIN = '--[[ WORKSHOP SPELL GIFTS (kept by the Workshop: Give spells to people writes this)'
END = 'WORKSHOP SPELL GIFTS END ]]'
SELLS_SPELLS = 0x800
FLAG_FEMALE, FLAG_AUTO = 0x1, 0x10
_cache = {}


def _data(db, i):
    r = db.recs[i]
    return db.files[r[3]].record_at(r[4])


def _winner(db, tag, key):
    lst = [v for v in db.by_key.get((tag, key), []) if v not in db.dead]
    return lst[-1] if lst else None


# ----------------------------------------------------------------- where each place is
def _places(db):
    """cell record index -> (town, region id lower), from the cells' own names and regions."""
    if _cache.get('places_for') is db.recs and _cache.get('places_n') == len(db.recs):
        return _cache['places']
    import poplines
    town_region, out = {}, {}
    ext = []
    for (tag, key), lst in db.by_key.items():
        if tag != 'CELL':
            continue
        for ci in lst:
            r = db.recs[ci]
            if r is None or ci in db.dead:
                continue
            if key.startswith('#'):
                region = r[5][len('exterior '):].strip().lower() if r[5].startswith('exterior') else ''
                name = r[1].rsplit(' (', 1)[0]
                town = '' if name.lower() in (region, 'wilderness') else poplines.town_of(name)
                ext.append((ci, town, region))
                if town and region:
                    town_region.setdefault(town.lower(), {})
                    town_region[town.lower()][region] = town_region[town.lower()].get(region, 0) + 1
            else:
                out[ci] = (poplines.town_of(r[1]), None)
    best = {t: max(c.items(), key=lambda kv: kv[1])[0] for t, c in town_region.items()}
    for ci, town, region in ext:
        out[ci] = (town, region)
    # (an interior is in its town's region: "Balmora, Guild of Mages" is in the West Gash)
    for ci, (town, region) in list(out.items()):
        if region is None:
            out[ci] = (town, best.get(town.lower(), ''))
    _cache.update(places=out, places_for=db.recs, places_n=len(db.recs))
    return out


# ----------------------------------------------------------------- who there is
def people(db):
    """[person]: id, name, race, cls, faction, level, skills (27), spells (lower ids), sells (spells),
    places [(town, region)]. Every character in the load order, as it stands."""
    if _cache.get('people_for') is db.recs and _cache.get('people_n') == len(db.recs):
        return _cache['people']
    import npc
    places = _places(db)
    calc = {}
    out = []
    for (tag, key), lst in db.by_key.items():
        if tag != 'NPC_':
            continue
        ri = _winner(db, tag, key)
        if ri is None:
            continue
        r = db.recs[ri]
        o = {'id': r[1], 'i': ri, 'name': '', 'race': '', 'cls': '', 'faction': '', 'level': 1, 'skills': None,
             'spells': set(), 'sells': False, 'female': False}
        flags = 0
        for t, d in iter_subrecords(_data(db, ri)[2]):
            if t == 'FNAM':
                o['name'] = zstr(d)
            elif t == 'RNAM':
                o['race'] = zstr(d)
            elif t == 'CNAM':
                o['cls'] = zstr(d)
            elif t == 'ANAM':
                o['faction'] = zstr(d)
            elif t == 'NPDT' and len(d) >= 52:
                v = struct.unpack_from('<h8B27B', d)
                o['level'], o['skills'] = v[0], list(v[9:36])
            elif t == 'NPDT' and len(d) >= 12:
                o['level'] = struct.unpack_from('<h', d)[0]
            elif t == 'FLAG' and len(d) >= 4:
                flags = struct.unpack_from('<i', d)[0]
            elif t == 'NPCS':
                o['spells'].add(zstr(d).lower())
            elif t == 'AIDT' and len(d) >= 12:
                o['sells'] = bool(struct.unpack_from('<i', d, 8)[0] & SELLS_SPELLS)
        o['female'] = bool(flags & FLAG_FEMALE)
        if o['skills'] is None or flags & FLAG_AUTO:
            # (auto-calculated: the skills the game works out from race, class and level)
            ck = (o['race'].lower(), o['cls'].lower(), o['level'], o['female'])
            if ck not in calc:
                c = npc.autocalc(db, o['race'], o['cls'], o['level'], o['female'])
                calc[ck] = c['skills'] if c else [0] * 27
            o['skills'] = calc[ck]
        seen = set()
        for ci in db.used_in.get(key, ()):
            p = places.get(ci)
            if p and p not in seen:
                seen.add(p)
        o['places'] = sorted(seen)
        out.append(o)
    _cache.update(people=out, people_for=db.recs, people_n=len(db.recs))
    return out


def options(db):
    """What the filters can pick from, with how many people each has."""
    ps = people(db)
    count = lambda key: sorted(((k, n) for k, n in _tally(p[key] for p in ps if p[key]).items()), key=lambda kv: (-kv[1], kv[0].lower()))
    towns, regions = {}, {}
    for p in ps:
        for town, region in p['places']:
            if town:
                towns[town] = towns.get(town, 0) + 1
            if region:
                regions[region] = regions.get(region, 0) + 1
    import regions as regmod
    rnames = {g['id'].lower(): g['name'] for g in regmod.all_regions(db)}
    return {'races': count('race'), 'classes': count('cls'), 'factions': count('faction'), 'skills': SKILLS,
            'towns': sorted(towns.items(), key=lambda kv: (-kv[1], kv[0].lower())),
            'regions': sorted(([k, rnames.get(k, k), n] for k, n in regions.items()), key=lambda x: x[1].lower()),
            'people': len(ps), 'rules': rules(db)}


def _tally(it):
    out = {}
    for v in it:
        out[v] = out.get(v, 0) + 1
    return out


def _low(lst):
    return {(x or '').strip().lower() for x in (lst or []) if (x or '').strip()}


def match(db, f):
    """Everyone who fits the filters f: races, classes, factions, knows (any of), skill {i, min}, sellers,
    regions, towns (standing in any of those regions or towns), placed (only people placed somewhere)."""
    races, classes, factions, knows = _low(f.get('races')), _low(f.get('classes')), _low(f.get('factions')), _low(f.get('knows'))
    regions, towns = _low(f.get('regions')), _low(f.get('towns'))
    sk = f.get('skill') or {}
    try:
        si, smin = int(sk.get('i')), int(sk.get('min') or 0)
    except (TypeError, ValueError):
        si, smin = None, 0
    out = []
    for p in people(db):
        if races and p['race'].lower() not in races:
            continue
        if classes and p['cls'].lower() not in classes:
            continue
        if factions and p['faction'].lower() not in factions:
            continue
        if knows and not (knows & p['spells']):
            continue
        if f.get('sellers') and not p['sells']:
            continue
        if si is not None and 0 <= si < 27 and p['skills'][si] < smin:
            continue
        if regions or towns:
            if not any((t.lower() in towns) or (g in regions) for t, g in p['places']):
                continue
        elif f.get('placed', True) and not p['places']:
            continue
        out.append(p)
    return out


def _spells(db, ids):
    out = []
    for s in ids or []:
        s = (s or '').strip()
        if not s:
            continue
        ri = db.resolve_id(s)
        if ri is None or db.recs[ri][0] != 'SPEL':
            raise EditError('There is no spell called "%s".' % s)
        if db.recs[ri][1] not in out:
            out.append(db.recs[ri][1])
    if not out:
        raise EditError('Pick the spells to give.')
    return out


def preview(db, spells, f):
    """Who would get what, before anything is changed."""
    sp = _spells(db, spells)
    ms = match(db, f)
    low = [s.lower() for s in sp]
    rows = [{'id': p['id'], 'i': p['i'], 'name': p['name'], 'race': p['race'], 'cls': p['cls'], 'faction': p['faction'],
             'where': ', '.join(sorted({t for t, _g in p['places'] if t}))[:80],
             'new': [s for s, l in zip(sp, low) if l not in p['spells']]} for p in ms]
    rows.sort(key=lambda x: (not x['new'], x['name'].lower()))
    return {'spells': sp, 'n': len(rows), 'getting': sum(1 for x in rows if x['new']), 'rows': rows[:400]}


# ----------------------------------------------------------------- giving
def give(db, spells, f, mode='records', label=''):
    _require_project(db)
    sp = _spells(db, spells)
    if mode == 'script':
        if not db.project.lua_allowed():
            raise EditError('Giving by script needs OpenMW Lua, which a plain .esp can\'t carry: use Save as… on My mod to make '
                            'the mod an .omwaddon first, or give them in the records instead.')
        lst = rules(db)
        lst.append({'spells': sp, 'filters': _clean_filters(f), 'label': (label or '').strip()[:80]})
        n = _write(db, lst)
        commit(db, 'Gave %s by script to %d people' % (', '.join(sp), n['last']))
        return {'given': n['last'], 'rules': rules(db)}
    ms = match(db, f)
    given = 0
    for p in ms:
        add = [s for s in sp if s.lower() not in p['spells']]
        if add:
            _add_to_record(db, p['i'], add)
            given += 1
    if not given:
        raise EditError('Everyone who fits already knows %s.' % ('it' if len(sp) == 1 else 'them'))
    commit(db, 'Gave %s to %d people' % (', '.join(sp), given))
    return {'given': given}


def _add_to_record(db, ri, add):
    """The spells added to one person's record (their NPCS list), everything else kept as it was."""
    from npc import _id32
    r = db.recs[ri]
    _t, rflags, data = _data(db, ri)
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    # (after the spells they know; or after what they carry; or before their AI)
    at = next((n + 1 for n in range(len(subs) - 1, -1, -1) if subs[n][0] == 'NPCS'), None)
    if at is None:
        at = next((n + 1 for n in range(len(subs) - 1, -1, -1) if subs[n][0] == 'NPCO'), None)
    if at is None:
        at = next((n for n, (t, _d) in enumerate(subs) if t == 'AIDT'), len(subs))
    subs[at:at] = [('NPCS', _id32(s)) for s in add]
    db.project.set_record('NPC_', r[7], rflags & ~0x20, join_subs(subs),
                          created=bool(db.project.records.get('NPC_|' + r[7], {}).get('created')))


def _clean_filters(f):
    out = {k: sorted(_low(f.get(k))) for k in ('races', 'classes', 'factions', 'knows', 'regions', 'towns') if f.get(k)}
    sk = f.get('skill') or {}
    if sk.get('i') not in (None, ''):
        out['skill'] = {'i': int(sk['i']), 'min': int(sk.get('min') or 0)}
    if f.get('sellers'):
        out['sellers'] = True
    return out


# ----------------------------------------------------------------- the script's rules
def _script(db):
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == SCRIPT), None)


def rules(db):
    s = _script(db)
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


def remove_rule(db, n):
    _require_project(db)
    lst = rules(db)
    if not 0 <= n < len(lst):
        raise EditError('There is no such rule.')
    gone = lst.pop(n)
    _write(db, lst)
    commit(db, 'Stopped giving %s by script' % ', '.join(gone['spells']))
    return {'rules': rules(db)}


def refresh(db):
    """The rules matched again against the people as they are now (after adding mods or people)."""
    _require_project(db)
    lst = rules(db)
    n = _write(db, lst)
    commit(db, 'Matched the spell gifts again')
    return {'rules': rules(db), 'people': n['all']}


def _write(db, lst):
    from myeffects import _put, _lua
    give_to = {}
    last = 0
    for rule in lst:
        ms = match(db, rule['filters'])
        rule['n'] = len(ms)
        last = 0
        for p in ms:
            want = give_to.setdefault(p['id'].lower(), [])
            for s in rule['spells']:
                if s.lower() not in p['spells'] and s.lower() not in want:
                    want.append(s.lower())
            last += 1
    give_to = {k: v for k, v in give_to.items() if v}
    if not lst:
        _put(db, SCRIPT, None, None)
        return {'last': 0, 'all': 0}
    rows = '\n'.join('  [%s] = %s,' % (_lua(k), _lua(v)) for k, v in sorted(give_to.items()))
    text = LUA % (BEGIN, json.dumps(lst, indent=1).replace(']]', ']\\u005d'), END, rows)
    _put(db, SCRIPT, 'NPC', text)
    return {'last': last, 'all': len(give_to)}


LUA = '''-- Made by Morrowind Workshop: spells given to everyone who fits (Give spells to people…).
-- Each person on the list learns these spells the first time they come near, if they don't know them already.
%s
%s
%s

local self = require('openmw.self')
local types = require('openmw.types')

local GIVE = {
%s
}

local function give()
  local list = GIVE[self.recordId]
  if not list then return end
  local spells = types.Actor.spells(self)
  for _, id in ipairs(list) do
    local ok, has = pcall(function() return spells[id] end)
    if not (ok and has) then
      local added, err = pcall(function() spells:add(id) end)
      if not added then print('[Workshop] spell gift ' .. id .. ' for ' .. self.recordId .. ': ' .. tostring(err)) end
    end
  end
end

return {
  engineHandlers = {
    onActive = give,
  },
}
'''
