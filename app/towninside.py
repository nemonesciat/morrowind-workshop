"""A built town's insides (townbuild.make, interiors=True): behind each building's door one of the game's own interiors
for that very building, copied whole (frombuilding.copy_game_interior: its furniture and what lies about, people and
owners left out), its door linked both ways; and with people=True its household, cast as the game's places of its kind
have them (populate.cast), placed and owning its beds and chests.

Every building on a plot is a game building that stands outside one or more of the game's interiors (the exterior
survey's examples), so each has interiors made for it: the one of the plot's kind is taken (a smithy's for a smithy),
never a tomb's, a cave's or a mine's, and a whole place before an upper floor or a wing.

The interiors are named as the game names its own (survey of the interiors behind the game's town buildings, lab
jtint0, 2026-10-31): "<Town>, <Name>'s House" (323), "<Name>: Trader" and the other trades (100+), "<Family>
Tradehouse"; a temple, a guild or a guard tower by what it is. The name is the household's head's: the cast is made
on the game's original first (the copy keeps every position, so its spots hold), then the copy is named after its head.
A tavern with a name of its own gets one made from the words of that culture's tavern names ("The Ruby Crab Inn")."""
import random
import re
import zlib

import math
import mapdata
import townsurvey
from editing import EditError

# (the doors of the game's tombs, barrows, caves and mines are in its towns too, Velothi's ancestral tombs most; a
# plot takes none of them, and no interior is copied from one)
NOT_TOWN = re.compile(r'tomb|barrow|crypt|cave\b|cavern|grotto|\bmine\b|mine entrance|ruin|propylon|daedric|catacomb|sewer|'
                      r'\babyss\b|dungeon|\blair\b|egg mine|stronghold|shrine of|underground|ancestral', re.I)
# (part of a place, not a place: "Gateway Inn: North Wing", "Red Palace: Upper Floor")
PART = re.compile(r':\s*(upper|lower|top|ground|second|third|north|south|east|west)?\s*(floor|level|wing|basement|cellar|'
                  r'quarters|tower|hall|antechamber|auditorium|kitchen|storage|attic|vault|spire|rooms?)\b', re.I)
TRADE = re.compile(r"^([A-Z][\w'-]*(?: [A-Z][\w'-]*){0,3}): ([A-Z][\w ]+)$")
OWNED = re.compile(r"^([A-Z][\w'-]*(?: (?:the |gro-|gra-)?[A-Z][\w'-]*){0,3})'s? ([A-Z][\w ]+)$")
FAMILY = re.compile(r"^([A-Z][\w'-]+) (Tradehouse|Manor|House|Household|Residence|Farmhouse|Cornerclub|Hall)$")
NOT_PERSON = re.compile(r'\b(of|the|temple|hall|inn|tower|manor|guild|chapel|shrine|office|market|club|palace|house|tavern)\b', re.I)
TAVERN_WORDS = re.compile(r'\b(the|inn|tavern|tradehouse|hostel|club|cornerclub|entrance|of|and|house|wing|north|south|east|west)\b', re.I)


def town_ok(name):
    """Is the game interior behind a building one a town's plot can stand for (not a tomb's, a cave's, a mine's)?"""
    return not NOT_TOWN.search(name or '')


def _name_of(db, key):
    return (mapdata.cell_info(db, key) or {}).get('name') or key


def _tail(name):
    """The place's own part of a game interior's name: "Ald-ruhn, Dandera Selaro: Smith" → "Dandera Selaro: Smith"."""
    return name.split(',', 1)[1].strip() if ',' in name else name.strip()


def template(db, m, kind, rng, used=None):
    """The game interior to copy for a building (its exterior module m) on a plot of this kind, or None: the plot's kind
    first, a whole place before a part, one not copied yet in this town before one that was."""
    used = used if used is not None else {}
    rows = []
    for e in m.get('examples') or ():
        if not db.by_key.get(('CELL', e)):
            continue
        nm = _name_of(db, e)
        if not town_ok(nm):
            continue
        rows.append((townsurvey.kind_of(e) != kind, _dead_doors(db, e) > 0, bool(PART.search(nm)), used.get(e, 0), rng.random(), e))
    return min(rows)[-1] if rows else None


def _dead_doors(db, e):
    """How many doors of e and the places copied with it would lead nowhere in a copy (to a crypt, a sewer, a place
    past CLOSURE_MAX): such an interior is taken last. (19 such doors in a walled town of 61 interiors, lab jd5)"""
    cells = _closure(db, [e])
    n = 0
    for c in cells:
        for r in mapdata.cellmap(db, c).get('refs') or ():
            if r['type'] == 'DOOR' and r.get('to') and r['to'].get('cell') and r['to']['cell'].lower() not in cells:
                n += 1
    return n


# ---------------------------------------------------------------- names

def town_name(db, culture, seed=1):
    """A town name made from the culture's own town names: the start of one and the end of another
    ("Gni" + "ruhn"), never one the game has."""
    towns = townsurvey.survey(db)['towns']
    names = [t['name'] for t in towns if t.get('name') and t.get('culture') == culture] or [t['name'] for t in towns if t.get('name')]
    have = {n.lower() for n in names}
    rng = random.Random('%s|%s|town' % (seed, culture))
    chunks = lambda s: re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy]+$)?", s.lower())
    for _t in range(200):
        a, b = rng.choice(names), rng.choice(names)
        a_, b_ = chunks(a.split(',')[0]), chunks(b.split(',')[0])
        if len(a_) < 1 or len(b_) < 2:
            continue
        nm = ''.join(a_[:rng.randint(1, max(1, len(a_) - 1))] + b_[-rng.randint(1, max(1, len(b_) - 1)):])
        nm = re.sub(r'([ -])(\w)', lambda g: g.group(1) + g.group(2).upper(), nm).strip(' -')
        nm = nm[:1].upper() + nm[1:]
        if 4 <= len(nm.replace(' ', '')) <= 12 and nm.lower() not in have and not re.search(r'(.)\1\1|[ -]{2}', nm):
            return nm
    return 'New ' + culture


def _possessive(name):
    return name + ("'" if name.endswith('s') else "'s")


def _tavern(db, culture, rng):
    """A tavern name from the words of the culture's game tavern names: "The <word> <word> Inn"."""
    names = []
    for t in townsurvey.survey(db)['towns']:
        if t.get('culture') != culture:
            continue
        for b in t.get('buildings') or ():
            if b.get('kind') == 'tavern' and b.get('name'):
                names.append(_tail(b['name']))
    words = [w for n in names for w in re.findall(r"[A-Z][a-z']+", TAVERN_WORDS.sub(' ', n)) if not w.endswith("'s")]
    ends = [m.group(1) for n in names for m in [re.search(r'\b(Inn|Tavern|Tradehouse|Hostel|Cornerclub|Club)\b', n)] if m] or ['Inn']
    if len(set(words)) < 2:
        return None
    a = rng.choice(words)
    b = rng.choice([w for w in words if w != a])          # ("The Iron Iron Tavern", lab jd3)
    return 'The %s %s %s' % (a, b, rng.choice(ends))


DWELLING = re.compile(r'(House|Shack|Hut|Lodge|Farmhouse|Cabin|Yurt|Tent|Manor|Hall|Apartment|Residence|Household|Tower|Farm)')


def interior_name(db, town, tmpl_name, kind, head, family, culture, rng):
    """The copy's name, after its head where the game's own is after a person, and always for a home (a house plot in a
    farm's storage or a slave shack is somebody's: "Slave Shack Two" six times over, lab jtint1)."""
    tail = PART.sub('', _tail(tmpl_name)).strip(' :') or _tail(tmpl_name)
    # ("Guar Farm: Erdlan Galelan's Shack": the person's part)
    if ': ' in tail and OWNED.match(tail.split(': ', 1)[1]):
        tail = tail.split(': ', 1)[1]
    m = TRADE.match(tail)
    if m and head and not NOT_PERSON.search(m.group(1)):
        tail = '%s: %s' % (head, m.group(2))
    else:
        m = OWNED.match(tail)
        if m and head and not NOT_PERSON.search(m.group(1)):
            tail = '%s %s' % (_possessive(head), m.group(2))
        else:
            m = FAMILY.match(tail)
            if m and (family or head):
                tail = '%s %s' % (family or head.split()[-1], m.group(2))
            elif kind == 'tavern':
                tail = _tavern(db, culture, rng) or tail
            elif kind not in ('temple', 'guild', 'guard', 'tavern') and head:
                w = DWELLING.findall(tail)
                tail = '%s %s' % (_possessive(head), w[-1] if w else 'House')
    # (a game fort's "Interior" or "Entrance" names nothing: "Fibonheart, Interior" and "Interior: Prison Towers", lab i01)
    if GENERIC.match(tail):
        tail = GENERIC_KIND.get(kind) or ('%s House' % _possessive(head) if head else 'Hall')
    return '%s, %s' % (town, tail)


GENERIC = re.compile(r'^(interior|entrance|main|ground floor|upper floor|lower floor|hall|building)$', re.I)
GENERIC_KIND = {'guard': 'Garrison', 'temple': 'Chapel', 'guild': 'Guild Hall', 'tavern': 'Tavern', 'manor': 'Manor', 'shop': 'Shop'}


def _unique(db, name, taken):
    base, n = name[:60], 2
    while name.lower() in taken or (db.by_key.get(('CELL', name.lower())) and
                                    any(v not in db.dead for v in db.by_key[('CELL', name.lower())])):
        name = '%s %d' % (base[:58], n)
        n += 1
    taken.add(name.lower())
    return name


# ---------------------------------------------------------------- the insides

def _building(db, q, dr):
    """The building at a plot as frombuilding knows one, from what the town knows: its door, and its frame from the plot's
    facing (+y inward). (building_at gave up on a joined Dunmer row, "the pieces run on into the rest of the town", and
    read the pieces round every door again)"""
    import shellsurvey as ss
    import townbuild
    m = mapdata.cellmap(db, dr[0])
    d = next((r for r in m.get('refs', []) if r['k'] == dr[1]), None)
    if d is None:
        raise EditError("The building's door is no longer there.")
    c, sn, _yaw = townbuild._frame(q['face'])
    ux, uy = sn, c
    sill = d['p'][2] + (d.get('b') or [0, 0, 0])[2] * (d.get('s') or 1.0)
    return {'door': {'k': d['k'], 'cell': dr[0], 'id': d['id'], 'p': d['p']}, 'frame': ss.Frame(d['p'][0], d['p'][1], sill, ux, uy),
            'cell': dr[0]}


def _link_more_doors(db, q, done=()):
    """A building's other doors (a Nordic house's back door) lead into its interior too, as its front door does: left
    unlinked they opened onto nothing, five in a town of 26 (the town audit, 2026-11-01)."""
    import doors
    import editing
    dr = q.get('door_ref')
    if not dr or not q.get('more_doors'):
        return
    m = mapdata.cellmap(db, dr[0])
    front = next((r for r in m.get('refs') or () if r['k'] == dr[1]), None)
    to = front and front.get('to')
    if not to or not to.get('cell'):
        return
    n = 0
    for key, rk in q['more_doors']:
        if rk in done:
            continue                    # (linked as the game's led: copy_building)
        try:
            c, refs = editing._cell(db, key)
        except EditError:
            continue
        ref = refs.get(rk)
        if ref is None:
            continue
        editing._store(c, rk, ref['origin'], ref['idx'], doors._set_link(ref['subs'], to['cell'], on_floor(db, to['cell'], [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']])))
        n += 1
    if n:
        editing.commit(db, 'Linked the other door%s of %s' % ('' if n == 1 else 's', to['cell']))


# ---------------------------------------------------------------- the doors as the game led them

# (a building's interior and the parts its doors lead on to, an upper level, a cellar, a turret, copied together; the
# game's town templates: 985 of 1,106 are one place, 103 two to six, 48 run on into sewers or further, lab jd2)
CLOSURE_MAX = 6
DOOR_MATCH = 48                     # (a placed door is the game's door that stood within this of its spot, same model)
_PAIRS = {}


def _pair(db, key):
    import shellsurvey as ss
    if _PAIRS.get('recs') is not db.recs:
        _PAIRS.clear()
        _PAIRS['recs'] = db.recs
        _PAIRS['by'] = {p['key']: p for p in ss.survey(db)['pairs']}
    return _PAIRS['by'].get(key)


def game_doors(db, t):
    """The game's building outside interior t: (its door frame, the doors of it that lead somewhere, each
    {'low', 'x', 'y', 'z' in the frame, 'to', 'p'}), or (None, [])."""
    import math
    import shellsurvey as ss
    p = _pair(db, t)
    if not p:
        return None, []
    ef = p['eframe']
    fr = ss.Frame(ef['x'], ef['y'], ef['z'], ef['ux'], ef['uy'])
    out = []
    for it in ss.near_items(db, ef['x'], ef['y']):
        if it['tag'] != 'DOOR' or not it.get('to'):
            continue
        lx, ly = fr.to(it['p'][0], it['p'][1])
        if math.hypot(lx, ly) < 3000:
            out.append({'low': it['low'], 'x': lx, 'y': ly, 'z': it['p'][2] - fr.z, 'to': it['to'], 'p': it['p']})
    return fr, out


def _match_doors(pieces, gdoors):
    """{placed door's ref key: the game door that stood at its spot in the building}."""
    out = {}
    for dp in pieces or ():
        d2 = lambda g: (g['x'] - dp['x']) ** 2 + (g['y'] - dp['y']) ** 2 + (g['z'] - dp['z']) ** 2
        g = min((g for g in gdoors if g['low'] == dp['id'].lower()), key=d2, default=None)
        if g is not None and d2(g) <= DOOR_MATCH ** 2:
            out[dp['rk']] = g
    return out


def _closure(db, seeds):
    """The places to copy for a building: its interior and those its inside doors lead on to (town places only)."""
    cells, todo = [], list(seeds)
    while todo and len(cells) < CLOSURE_MAX:
        k = todo.pop(0)
        if k in cells or not db.by_key.get(('CELL', k)) or not town_ok(_name_of(db, k)):
            continue
        cells.append(k)
        for r in mapdata.cellmap(db, k).get('refs') or ():
            if r['type'] == 'DOOR' and r.get('to') and r['to'].get('cell'):
                todo.append(r['to']['cell'].lower())
    return cells


def _sub_name(db, name, t, c):
    """A copied part's name: the main copy's and the part's own ("Anvil, Hasi Manor: Upper Level" behind
    "Anvil, Hasi Manor" → "<name>: Upper Level")."""
    tt, ct = _tail(_name_of(db, t)), _tail(_name_of(db, c))
    if ct.lower().startswith(tt.lower()) and len(ct) > len(tt):
        suffix = ct[len(tt):].lstrip(' :,-')
    elif ':' in ct:
        suffix = ct.split(':', 1)[1].strip()
    else:
        suffix = ct
    suffix = (suffix or 'Back')[:30]
    return name[:max(10, 60 - len(suffix) - 2)].rstrip(' ,:') + ': ' + suffix


ARRIVE_LIFT = 12                # (an arrival this far over the floor or ground under it: the game's own stand 80 over it,
                               # p10 80, p90 86, lab a01, and you drop a step at every door, the user's Griffbarrow)
ARRIVE_REACH = 160             # (only onto a floor this near under the game's spot, or this near over it)


def on_floor(db, dest, pos, memo=None):
    """pos (an arrival in dest, '' outside) set on the floor or ground under it, ARRIVE_LIFT over it."""
    import math
    import seethrough
    memo = {} if memo is None else memo
    x, y, z = pos[0], pos[1], pos[2]
    key = dest.lower() if dest else '#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0))
    if key not in memo:
        try:
            refs = [r for r in mapdata.cellmap(db, key).get('refs') or () if r['type'] not in ('NPC_', 'CREA', 'DOOR')]
            if not dest:
                refs = [r for r in refs if r.get('arch')]
            memo[key] = seethrough.place_scene(db, {'refs': refs})
        except Exception:
            memo[key] = None
    sc, fl = memo[key], None
    if sc is not None:
        h = sc.nearest_any((x, y, z + ARRIVE_REACH), (0.0, 0.0, -1.0), 2 * ARRIVE_REACH)
        fl = z + ARRIVE_REACH - h[0] if h else None
    if not dest:
        g = mapdata.terrain_z(db, x, y)
        if g is not None and (fl is None or fl < g) and abs(g - z) <= 2 * ARRIVE_REACH:
            fl = g
    return list(pos) if fl is None else [x, y, fl + ARRIVE_LIFT] + list(pos[3:])


def _carry(to, gp, xp):
    """The game's arrival outside its door gp, carried to our door xp: the same spot and turn in the door's frame."""
    import math
    import create
    lx, ly = create._rot2(to['x'] - gp[0], to['y'] - gp[1], -gp[5])
    wx, wy = create._rot2(lx, ly, xp[5])
    return [xp[0] + wx, xp[1] + wy, xp[2] + (to['z'] - gp[2]), 0.0, 0.0, (to['rz'] - gp[5] + xp[5]) % (2 * math.pi)]


OWN_LAYOUTS = True              # (town interiors planned from their buildings, never a game interior copied)


def _own_building(db, dr, name, seed, n):
    """The plot's building given an interior of the Workshop's own (frombuilding.build): planned from its footprint
    in its own style, its doors linked both ways. {'key', 'name'}, or None when the builder has no plan for it."""
    import frombuilding
    import zlib
    out = frombuilding.build(db, dr[0], dr[1], name, door_key=dr[1], seed=zlib.crc32(('%s|%s|%d' % (seed, name, n)).encode()) % 100000)
    if not out or not out.get('key'):
        return None
    return {'key': out['key'], 'name': name, 'own_layout': True}


def copy_building(db, q, t, name, taken):
    """The game's interior t copied for the plot's building with the places its doors lead on to, and every door
    linked as the game's led: the building's outside doors to the copies of the inside doors the game paired them
    with, arriving where the game's arrive; the inside doors out to those, a step in front of them, facing away; trap
    doors and ladders between the copied storeys as the game joined them. None when the game's building can't be
    read (the caller copies the old way). {'key', 'name', 'linked', 'dead'}"""
    import math
    import create
    import doors
    import editing
    fr, G = game_doors(db, t)
    M = _match_doors(q.get('door_pieces'), G)
    dr = q.get('door_ref')
    if not G or not dr or dr[1] not in M or (M[dr[1]]['to'].get('cell') or '').lower() != t:
        return None
    seeds = [t] + [(g['to'].get('cell') or '').lower() for g in M.values() if g['to'].get('cell')]
    cells = _closure(db, seeds)
    if t not in cells:
        return None
    names = {t: name}
    for c in cells[1:]:
        names[c] = _unique(db, _sub_name(db, name, t, c), taken)
    n0 = len(getattr(db.project, 'undo_stack', []))
    keys = {c: create.create_interior(db, c, names[c], 'furnished', None) for c in cells}
    placed = {}
    for dp in q.get('door_pieces') or ():
        r = next((r for r in mapdata.cellmap(db, dp['key']).get('refs') or () if r['k'] == dp['rk']), None)
        if r is not None:
            placed[dp['rk']] = (dp['key'], r)
    by_game = {id(g): rk for rk, g in M.items()}
    links = []                          # (cell key, ref key, destination name, position)
    dead = 0
    for c in cells:
        tm, cm = mapdata.cellmap(db, c), mapdata.cellmap(db, keys[c])
        copies = [r for r in cm['refs'] if r['type'] == 'DOOR']
        for r in tm['refs']:
            if r['type'] != 'DOOR' or not r.get('to'):
                continue
            cr = min(copies, key=lambda o: math.dist(o['p'][:3], r['p'][:3]), default=None)
            if cr is None or cr['id'].lower() != r['id'].lower() or math.dist(cr['p'][:3], r['p'][:3]) > 2:
                continue
            to = r['to']
            tc = (to.get('cell') or '').lower()
            if tc in names:
                links.append((keys[c], cr['k'], names[tc], [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']]))
                continue
            if not tc:
                # (out: the building's door the game's arrival stands in front of, among those that lead into this place)
                g = min((g for g in G if (g['to'].get('cell') or '').lower() == c), default=None,
                        key=lambda g: math.hypot(g['p'][0] - to['x'], g['p'][1] - to['y']))
                rk = by_game.get(id(g)) if g is not None and math.hypot(g['p'][0] - to['x'], g['p'][1] - to['y']) < 400 else None
                if rk in placed:
                    xp = placed[rk][1]['p']
                    out = _carry(to, g['p'], xp)
                    gz = mapdata.terrain_z(db, out[0], out[1])
                    if gz is not None and out[2] < gz + 4:
                        out[2] = gz + 8
                    links.append((keys[c], cr['k'], '', out))
                    continue
            dead += 1                   # (it led on past what was copied: left a plain door)
    for rk, g in M.items():
        tc = (g['to'].get('cell') or '').lower()
        if tc in names and rk in placed:
            to = g['to']
            links.append((placed[rk][0], rk, names[tc], [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']]))
    db.sync_project()
    floors = {}
    for ck, rk, dest, pos in links:
        c_, refs = editing._cell(db, ck)
        ref = refs.get(rk)
        if ref is not None:
            editing._store(c_, rk, ref['origin'], ref['idx'], doors._set_link(ref['subs'], dest, on_floor(db, dest, pos, floors)))
    editing.commit(db, 'Linked the doors of %s as the game\'s led' % name)
    # (then every arrival at the face of the door it pairs with, once for the whole town when it is done, townbuild:
    # the game's own copied arrivals put the user upstairs behind a locked door, 236 over the entry door's floor,
    # 2026-11-02)
    editing.fold(db, len(getattr(db.project, 'undo_stack', [])) - n0, 'Copied %s for the building, its doors linked as the game\'s' % name)
    linked = {rk for ck, rk, dest, pos in links}
    return {'key': keys[t], 'name': name, 'parts': [names[c] for c in cells[1:]], 'linked': len(links), 'dead': dead,
            'placed_linked': linked & set(placed), 'from': [(keys[c], c) for c in cells]}


# ---------------------------------------------------------------- the Workshop's own furnishing

# (the user, 2026-11-02: "we can learn as much as we want from other interiors about design and architecture, but we
# can't just copy them wholesale ... the interior decor and furnishing at least has to be unique". A town's interior
# keeps the game building's architecture, doors and door graph; its furnishing is the Workshop's own (castle.furnish_shell:
# each room's kind read from what the source room held, never its spots), or none for a modder to furnish)
ROOMS = ('none', 'shells', 'furnished')
FIXTURE = re.compile(r'sconce|chandelier|wall_?torch|torch_?wall|torchholder|_brazier', re.I)
PLAIN_LIGHT_UP = 170            # (a room's own plain light: this far over its floor)
_PLAIN = {}


def _kept_light(db, rid):
    """A light of the architecture: one with no model (a glow the builder set) or a fixture on the wall that can't be
    carried. Lamps, candles and lanterns are furnishing."""
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] != 'LIGH':
        return False
    if not db.recs[ri][5]:
        return True
    if not FIXTURE.search(rid):
        return False
    import builder
    return builder._light_carried(db, rid) is False


def _plain_light(db):
    """The game's most used warm light with no model, of a room's reach (256-768): an id, or None."""
    k = id(db.recs)
    if k in _PLAIN:
        return _PLAIN[k]
    import struct
    from esm import iter_subrecords
    best = None
    for (tag, low), lst in db.by_key.items():
        if tag != 'LIGH' or not lst:
            continue
        r = db.recs[lst[-1]]
        if r[5]:
            continue
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
        except Exception:
            continue
        for st, sd in iter_subrecords(data):
            if st == 'LHDT' and len(sd) >= 24:
                _w, _v, _d, rad, cr, cg, cb, _a, fl = struct.unpack_from('<fiiiBBBBi', sd, 0)
                if 256 <= rad <= 768 and not fl & 4 and cr >= 150 and cr >= cg >= cb:
                    n = len(db.used_in.get(low, ()))
                    if best is None or n > best[0]:
                        best = (n, r[1])
    _PLAIN[k] = best[1] if best else None
    return _PLAIN[k]


# (the user, 2026-11-02, on the first towns furnished anew: "they look very bland now ... the interiors should still be
# worth exploring, should still tell a story of the new town". A house's rooms were kinds read off the game's room: an
# armoury for a house that had two weapons on its wall, six racks and no bed. Now a home's rooms are a home's, by storey
# and size; a shop's its trade's, from the head's class; a tavern's a tavern's; the furnishing to the household's wealth
# (the head's class, wealthsurvey.trade); and the lived-in layer after, as any place can have it)
HOME_KINDS = {'armoury': 'living', 'barracks': 'bedroom', 'mess': 'living', 'guardroom': 'storage', 'shrine': 'study',
              'hall': 'living', 'training': 'living'}
TRADE_KIND = (('smith|armorer|armourer|weaponsmith', 'smithy'), ('alchem|apothec', 'alchemist'), ('enchant', 'enchanter'),
              ('bookseller|scribe', 'bookseller'), ('clothier|tailor|outfitter', 'clothier'), ('pawn', 'pawnbroker'),
              ('publican|innkeeper|barkeep', 'tavern'), ('priest|monk|healer', 'shrine'))
STOREY = 200                    # (a room's floor this far over the front door's is an upper storey: bedrooms)


def household_kinds(db, key, kind, head_cls, n_rooms_hint=None):
    """A function (room, kind read off the source, counts) -> the kind to furnish it as, for a town building of the
    plot kind with a head of that class; or None to keep the source's reading."""
    import re as _re
    m = mapdata.cellmap(db, key)
    fronts = [r for r in m.get('refs') or () if r['type'] == 'DOOR' and r.get('to') and not r['to'].get('cell')]
    z0 = min((r['p'][2] for r in fronts), default=None)
    trade = None
    for rx, k in TRADE_KIND:
        if head_cls and _re.search(rx, head_cls, _re.I):
            trade = k
            break
    state = {'shop': False, 'living': False, 'bed': 0, 'seen': 0}
    # (how many rooms the place has: a household gets a bedroom by its last room at the latest. The Workshop's own
    # layouts read no kind off the game's rooms, and a two-room house came out living + kitchen with no bed, lab own)
    try:
        import furnish
        n_rooms = n_rooms_hint or len(furnish.rooms(db, key, trace=False)['rooms'])
    except Exception:
        n_rooms = n_rooms_hint or 0

    def kinds(rm, k, cnt):
        state['seen'] += 1
        out = kinds0(rm, k, cnt)
        if out == 'bedroom':
            state['bed'] += 1
        elif kind in ('house', 'manor', 'farm', 'shack') and state['bed'] == 0 and n_rooms and state['seen'] >= n_rooms:
            out = 'bedroom'                  # (the last room of a bedless household sleeps its people)
            state['bed'] += 1
        return out

    def kinds0(rm, k, cnt):
        fl = rm.get('floor')
        tl = rm.get('_tiles') or ()
        upper = z0 is not None and fl is not None and fl > z0 + STOREY
        cellar = z0 is not None and fl is not None and fl < z0 - STOREY
        big = len(tl) >= 6
        if kind == 'tavern' or trade == 'tavern':
            if not upper and big and not state['shop']:
                state['shop'] = True
                return 'tavern'
            return 'bedroom' if upper else ('storage' if cellar else 'kitchen')
        if kind == 'temple' or trade == 'shrine':
            if not upper and big and not state['shop']:
                state['shop'] = True
                return 'shrine'
            return 'bedroom' if upper else 'study'
        if kind in ('shop', 'guild') or trade:
            if not upper and not cellar and big and not state['shop']:
                state['shop'] = True
                return trade if trade and trade not in ('tavern', 'shrine') else 'shop'
            if cellar:
                return 'storage'
            if upper:
                state['bed'] += 1
                return 'bedroom' if state['bed'] <= 2 else 'living'
            return 'storage' if not big else 'living'
        if kind == 'guard':
            return {'hall': 'guardroom'}.get(k, k if k in ('barracks', 'armoury', 'mess', 'guardroom', 'training') else 'barracks' if upper else 'guardroom')
        # a home, a manor
        if cellar:
            return 'storage'
        if upper:
            state['bed'] += 1
            return 'bedroom' if state['bed'] <= 2 else 'study'
        if big and not state['living']:
            state['living'] = True
            return 'dining' if kind == 'manor' else 'living'
        if k in ('kitchen', 'study', 'bedroom', 'storage', 'living', 'dining', 'entry', 'corridor', 'landing', 'bath'):
            return k
        return HOME_KINDS.get(k) or ('kitchen' if big else 'bedroom' if state['bed'] == 0 else 'storage')
    return kinds


def household_level(db, head_cls):
    """Auto-furnish's wealth choice for a household headed by that class: by trade when the survey knows it."""
    if not head_cls:
        return None
    try:
        import wealthsurvey
        return 'trade:%s' % head_cls if wealthsurvey.trade(db, head_cls) else None
    except Exception:
        return None


def make_own(db, key, src, rooms='furnished', seed=1, kind=None, head_cls=None):
    """A copied place made the Workshop's own: everything but its architecture, doors and built-in lights taken out;
    then furnished by the Workshop's own furnisher (rooms 'furnished'), or left empty with a plain light in every room
    that has none ('shells'). One step of its own. {'taken', 'placed', 'lights'}"""
    import castle
    import editing
    from project import ref_info
    c = db.project.cells.get(key)
    if not c:
        return {'taken': 0, 'placed': 0, 'lights': 0}
    gone = []
    for rk, ref in list(c['refs'].items()):
        rid = ref_info(castle._subs(ref))[0]
        if not (castle.is_shell(db, rid) or _kept_light(db, rid)):
            gone.append(rk)
    for rk in gone:
        c['refs'].pop(rk, None)
    db.sync_project()
    placed = 0
    if rooms == 'furnished':
        kinds = household_kinds(db, key, kind or 'house', head_cls) if (kind or head_cls) else None
        placed = castle.furnish_shell(db, key, src, (0.0, 0.0, 0.0), seed, kinds=kinds, level=household_level(db, head_cls))
        if placed:
            try:
                import livedin
                db.sync_project()
                livedin.apply(db, key, '', 1.0, seed, None, None, commit=False, camps=False, stories=False)
            except Exception as e:
                print('lived in:', key, e)
    lit = _light_rooms(db, key) if rooms == 'shells' else 0
    editing.commit(db, '%s %s' % ('Furnished' if rooms == 'furnished' else 'Emptied', (mapdata.cell_info(db, key) or {}).get('name') or key))
    return {'taken': len(gone), 'placed': placed, 'lights': lit}


def _light_rooms(db, key):
    """A plain light in every room of the place with no light in it. The number added."""
    import furnish
    import fixit
    lid = _plain_light(db)
    if not lid:
        return 0
    try:
        info = furnish.rooms(db, key)
    except Exception as e:
        print('shell rooms of', key, e)
        return 0
    T = info.get('tile') or 256
    lights = [r['p'] for r in mapdata.cellmap(db, key).get('refs') or () if r['type'] == 'LIGH']
    ops = []
    for rm in info.get('rooms') or ():
        tl = rm.get('_tiles') or []
        if not tl:
            continue
        fz = rm.get('floor') if rm.get('floor') is not None else min(t.get('z', 0.0) for t in tl)
        if any(any(abs(p[0] - t['x']) <= T / 2 and abs(p[1] - t['y']) <= T / 2 for t in tl) and -40 <= p[2] - fz <= 500 for p in lights):
            continue
        mx, my = sum(t['x'] for t in tl) / len(tl), sum(t['y'] for t in tl) / len(tl)
        t0 = min(tl, key=lambda t: (t['x'] - mx) ** 2 + (t['y'] - my) ** 2)
        ops.append({'op': 'place', 'id': lid, 'p': [t0['x'], t0['y'], fz + PLAIN_LIGHT_UP, 0.0, 0.0, 0.0]})
    if ops:
        fixit.apply(db, key, ops, commit=False)
    return len(ops)


TOWN_FIGHT = 30                 # (a town's people fight no more readily than this)
STAND_REACH = 200               # (a person with no floor this far under their feet is moved onto a room's floor)


def stand_people(db, key):
    """Every person placed in the place stood on a floor the place has: where nothing of its architecture lies within
    STAND_REACH under their feet (14 of 63 in a lab town stood over nothing and fell 230–2,070 in the game, the in-game
    harness, 2026-11-02), they are moved to the nearest room tile that has floor under it. The number moved."""
    import seethrough
    import furnish
    import editing
    from project import set_ref_pos
    m = mapdata.cellmap(db, key)
    ppl = [r for r in m.get('refs') or () if r['type'] == 'NPC_' and r.get('new')]
    if not ppl:
        return 0
    arch = [r for r in m['refs'] if r.get('arch') and r['type'] in ('STAT', 'ACTI')]
    sc = seethrough.place_scene(db, {'refs': arch})

    def under(x, y, z, reach=STAND_REACH):
        h = sc.nearest_any((x, y, z + 60.0), (0.0, 0.0, -1.0), reach + 60.0)
        return None if h is None else z + 60.0 - h[0]
    tiles = None
    moved = 0
    for p in ppl:
        x, y, z = p['p'][0], p['p'][1], p['p'][2]
        fz = under(x, y, z)
        if fz is not None:
            continue
        if tiles is None:
            try:
                info = furnish.rooms(db, key)
                tiles = [(t['x'], t['y'], t.get('floor', rm.get('floor')) if t.get('floor') is not None else rm.get('floor')) for rm in info.get('rooms') or () for t in rm.get('_tiles') or ()]
            except Exception:
                tiles = []
        best = None
        for tx, ty, tz in tiles:
            if tz is None:
                continue
            d = math.hypot(tx - x, ty - y) + abs(tz - z) * 0.5
            if best is not None and d >= best[0]:
                continue
            got = under(tx, ty, tz + 8.0, 120)
            if got is None:
                continue
            best = (d, tx, ty, got)
        if best is None:
            continue
        _d, tx, ty, tz = best
        c_, refs = editing._cell(db, key)
        ref = refs.get(p['k'])
        if ref is None:
            continue
        editing._store(c_, p['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (tx, ty, tz + 4.0, p['p'][3], p['p'][4], p['p'][5]), p.get('s') or 1.0))
        moved += 1
    if moved:
        db.sync_project()
    return moved


# ---------------------------------------------------------------- rooms in the wall

# (the game's own wall pieces with an interior behind a door of theirs: keeps, guard towers, curtain-wall towers, the
# Imperial forts' and Firewatch's, Old Ebonheart's; a made town's towers stood doorless, the user's walk of 2026-11-01)
WALL_ROOM = re.compile(r'keep|guardtower|wall_tower', re.I)
WALL_ROOMS = 6                     # a town's wall holds at most this many rooms
WALL_ROOM_WAYS = 4                 # (and copies only a game room with at most this many ways out)
DOOR_GROUND = 64                   # (a wall door's sill this near the ground in front of it, or it is not used there)
_WALLX = {}


def _wall_examples(db):
    """{wall model: [{'t', 'door', 'off': (x, y, z, turn) of the door from the piece, 's', 'to', 'gd'}]}: where the game
    sets a door on that piece and the interior behind it."""
    import math
    import create
    import shellsurvey as ss
    if _WALLX.get('recs') is db.recs:
        return _WALLX['out']
    out = {}
    for p in ss.survey(db)['pairs']:
        main = (p['building'].get('main') or '').lower()
        if not WALL_ROOM.search(main) or not town_ok(p.get('name') or '') or not db.by_key.get(('CELL', p['key'])):
            continue
        ef = p['eframe']
        items = ss.near_items(db, ef['x'], ef['y'])
        d = next((it for it in items if it['tag'] == 'DOOR' and it['to'] and (it['to'].get('cell') or '').lower() == p['key']
                  and math.hypot(it['p'][0] - ef['x'], it['p'][1] - ef['y']) < 5), None)
        if d is None:
            continue
        ms = [it for it in items if it['low'] == main]
        if not ms:
            continue
        m = min(ms, key=lambda it: math.hypot(it['p'][0] - d['p'][0], it['p'][1] - d['p'][1]))
        if math.hypot(m['p'][0] - d['p'][0], m['p'][1] - d['p'][1]) > 1500 or abs((m['s'] or 1.0) - 1.0) > 0.01:
            continue
        lx, ly = create._rot2(d['p'][0] - m['p'][0], d['p'][1] - m['p'][1], -m['p'][5])
        out.setdefault(main, []).append({'t': p['key'], 'door': d['id'], 's': d['s'] or 1.0, 'to': d['to'], 'gd': d['p'],
                                         'off': (lx, ly, d['p'][2] - m['p'][2], (d['p'][5] - m['p'][5]) % (2 * math.pi))})
    _WALLX.update(recs=db.recs, out=out)
    return out


def _ways_out(db, key):
    """How many of a place's doors lead somewhere."""
    try:
        return sum(1 for r in mapdata.cellmap(db, key)['refs'] if r['type'] == 'DOOR' and r.get('to'))
    except Exception:
        return 0


def wall_rooms(db, pieces, outline, town, taken, rng, rooms='furnished'):
    """Doors into the wall's own towers and keep, each with the game's interior for that piece behind it: the door where
    the game sets it on the piece, kept only where it opens into the town at the ground; linked both ways as the game's
    are. pieces: [(cell key, ref key, id, pose [x, y, z, rx, ry, rz])]. The interiors' names."""
    import math
    import create
    import doors
    import editing
    import townwalls
    from project import set_ref_pos, zs
    X = _wall_examples(db)
    cand = [w for w in pieces if w[2].lower() in X]
    # (the keep and the big towers first, then the wall towers, spread round the wall)
    cand.sort(key=lambda w: (0 if re.search('keep', w[2], re.I) else 1 if re.search('guardtower', w[2], re.I) else 2, rng.random()))
    names, used = [], set()
    mine = db.project.plugin.lower()
    for ck, rk, wid, pose in cand:
        if len(names) >= WALL_ROOMS:
            break
        # (a tower's own room, never a whole curtain wall's place with a dozen ways out: copied for one tower, its other
        # doors all led out by that tower's, the way out behind the wall there counted once for each, lab w02)
        exs = sorted([e for e in X[wid.lower()] if _ways_out(db, e['t']) <= WALL_ROOM_WAYS],
                     key=lambda e: (_dead_doors(db, e['t']) > 0, e['t'] in used, rng.random()))
        for e in exs:
            lx, ly, dz, drz = e['off']
            wx, wy = create._rot2(lx, ly, pose[5])
            dp = [pose[0] + wx, pose[1] + wy, pose[2] + dz, 0.0, 0.0, (pose[5] + drz) % (2 * math.pi)]
            # (where you come out: the game's arrival, carried to this door; in the town, on the ground)
            tm = mapdata.cellmap(db, e['t'])
            back = [r for r in tm['refs'] if r['type'] == 'DOOR' and r.get('to') and not r['to'].get('cell')]
            if not back:
                continue
            ib = min(back, key=lambda r: math.hypot(r['to']['x'] - e['gd'][0], r['to']['y'] - e['gd'][1]))
            out = _carry(ib['to'], e['gd'], dp)
            if not townwalls._inside(outline, (out[0], out[1])):
                continue                    # (it opens outside the town)
            gz = mapdata.terrain_z(db, out[0], out[1])
            if gz is None or abs(out[2] - 12 - gz) > DOOR_GROUND + 60:
                continue                    # (its sill in the air or in the ground here)
            try:
                import castle
                d_ = math.hypot(out[0] - dp[0], out[1] - dp[1]) or 1.0
                n_ = ((out[0] - dp[0]) / d_, (out[1] - dp[1]) / d_)
                if not castle._way_clear(castle._scene_near(db, [(dp[0], dp[1])], 900), dp[0] + n_[0] * 30, dp[1] + n_[1] * 30, gz, n_, castle.GROUND_CLEAR):
                    continue                # (something stands in its way out: a yard wall, a house)
            except Exception as e_:
                print('wall room way out:', e_)
            ri = db.resolve_id(e['door'])
            if ri is None:
                continue
            # (named by the piece: the game's own names were "Interior", "Towers", "Prison")
            name = _unique(db, '%s, %s' % (town, 'Keep' if re.search('keep', wid, re.I) else 'Guard Tower' if re.search('guardtower', wid, re.I) else 'Wall Tower'), taken)
            key = create.create_interior(db, e['t'], name, 'furnished', None)
            cm = mapdata.cellmap(db, key)
            cb = min((r for r in cm['refs'] if r['type'] == 'DOOR'), key=lambda r: math.dist(r['p'][:3], ib['p'][:3]), default=None)
            if cb is None:
                continue
            dk = '#%d,%d' % (math.floor(dp[0] / 8192.0), math.floor(dp[1] / 8192.0))
            cell, _refs = editing._cell(db, dk)
            nk = db.project.new_ref_key()
            to = e['to']
            subs = doors._set_link(set_ref_pos([('NAME', zs(db.recs[ri][1]))], tuple(dp), e['s']), name, on_floor(db, name, [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']]))
            editing._store(cell, nk, mine, int(nk.rsplit('|', 1)[1]), subs)
            c2, refs2 = editing._cell(db, key)
            r2 = refs2[cb['k']]
            editing._store(c2, cb['k'], r2['origin'], r2['idx'], doors._set_link(r2['subs'], '', on_floor(db, '', out)))
            # (the game place's other ways out, to its fort and along its wall, out by this door too: a curtain wall's
            # place copied for one tower kept its eleven other doors leading nowhere, 48 in a walled hill town, lab b01)
            for r in tm['refs']:
                if r['type'] != 'DOOR' or not r.get('to') or r['k'] == ib['k']:
                    continue
                o = min((c_ for c_ in cm['refs'] if c_['type'] == 'DOOR' and c_['k'] != cb['k']), key=lambda c_: math.dist(c_['p'][:3], r['p'][:3]), default=None)
                if o is None or math.dist(o['p'][:3], r['p'][:3]) > 2 or o['k'] not in refs2:
                    continue
                r3 = refs2[o['k']]
                editing._store(c2, o['k'], r3['origin'], r3['idx'], doors._set_link(r3['subs'], '', on_floor(db, '', out)))
            editing.commit(db, 'A room in the wall of %s: %s' % (town, name))
            try:
                make_own(db, key, e['t'], rooms, rng.randrange(1, 1 << 30))
            except EditError as e_:
                print('wall room made its own:', name, e_)
            used.add(e['t'])
            names.append(name)
            break
    return names


def furnish(db, plan, town, culture, seed=1, people=True, catalog=None, say=None, rooms='furnished'):
    """An interior behind every built plot's door (q['door_ref']), and its people. Each step its own change; the caller
    folds them with the town into one. say(done share): told as each plot is gone through (townbuild's progress bar).
    {'interiors', 'people', 'names', 'skipped'}"""
    import frombuilding
    import townbuild
    C = townbuild.by_uid(catalog or ())
    # (a cast for every interior when the people survey is learnt, people or not: a home is named after its head, and
    # without one nine homes were "Farmhands' Lodge" 1 to 3; only placing them is slow)
    import castsurvey
    S = castsurvey.ready(db)
    rng = random.Random('%s|%s|inside' % (seed, culture))
    taken, names, used = set(), [], {}
    said = []
    made = folks = skipped = 0
    tried = set()                    # (every place this run made or began: the ones no door leads to go at the end)
    for k, q in enumerate(plan['plots']):
        if say:
            say(k / float(len(plan['plots']) or 1))
        dr = q.get('door_ref')
        b = q.get('b') and townbuild.built(C, q['b'])
        if not dr or not b:
            continue
        kind = q.get('kind') or b['kind']
        t = template(db, b['m'], kind, rng, used)
        if t is None:
            skipped += 1
            continue
        used[t] = used.get(t, 0) + 1
        tname = _name_of(db, t)
        cast_ = None
        head = family = head_cls = None
        if S is not None:
            import populate
            import castsurvey
            try:
                # (the plot in the seed: by the template alone, six copies of one shack had one Drathyn Sarothril, lab jtint2)
                # (cast for what the plot is, named as the building will be: a template read as a house by its name cast
                # no keeper for a Bonesmith, the in-game walk 2026-11-03)
                ask = {'setting': kind} if kind in ('shop', 'tavern', 'temple', 'guild', 'manor') else {}
                if tname:
                    ask['name'] = tname
                cast_ = populate.cast(db, t, ask, seed=zlib.crc32(('%s|%s|%s|%d' % (seed, town, t, made + skipped)).encode()))
            except Exception as e:
                print('town cast:', t, e)
                cast_ = None
            ppl = (cast_ or {}).get('people') or []
            if ppl:
                h = next((p for p in ppl if p.get('relation') in ('head', 'leader')), ppl[0])
                if h.get('relation') not in ('head', 'leader') and kind in ('house', 'manor', 'farm', 'shack'):
                    # (a household cast with nobody who may head it, a manor's lone guard: the one the place is named
                    # after heads it and owns its beds and chests, else they stood free for anyone, lab own 2026-11-03)
                    h['relation'] = 'head'
                head = h['name']
                head_cls = h.get('cls')
                family = castsurvey._split_name(h['name'], h.get('race') or '')[1] or None
        name = _unique(db, interior_name(db, town, tname, townsurvey.kind_of(tname), head, family, culture, rng), taken)
        tried.add(name.lower())
        try:
            out = None
            if OWN_LAYOUTS:
                # (the Workshop's own layout from the building's footprint, frombuilding.build: the user, 2026-11-03,
                # "to see a perfect copy of some interior in Balmora or Ebonheart on a brand new continent would feel
                # jarring"; rooms, shelves and decor may resemble the game's, the plan is its own. The game's copy is
                # the fallback when the building can't be planned)
                try:
                    out = _own_building(db, dr, name, seed, made + skipped)
                except Exception as e:
                    print('town own layout:', name, e)
            if out is None:
                out = copy_building(db, q, t, name, taken)
            if out is None:
                out = frombuilding.copy_game_interior(db, dr[0], dr[1], t, name, 'furnished', door_key=dr[1], b=_building(db, q, dr))
        except EditError as e:
            print('town interior:', name, e)
            skipped += 1
            continue
        made += 1
        names.append(out['name'])
        tried.update(k_.lower() for k_, _s in out.get('from') or [(out['key'], t)])
        for k_, src_ in out.get('from') or [(out['key'], t)]:
            try:
                make_own(db, k_, src_, rooms, zlib.crc32(('%s|%s|own' % (seed, k_)).encode()), kind, head_cls)
            except EditError as e:
                print('town interior made its own:', name, e)
        q['inside_kind'] = kind
        q['interior'] = out['key']
        q['interior_from'] = out.get('from') or [(out['key'], t)]
        _link_more_doors(db, q, out.get('placed_linked') or ())
        ppl = (cast_ or {}).get('people') or [] if people and rooms == 'furnished' else []
        if ppl:
            import populate
            # (a householder never fights on sight: a jailor and a trader cast with fight 90 attacked the player at
            # the door, the in-game harness, 2026-11-02; the game's townsfolk stand at 30)
            for p_ in ppl:
                if p_.get('fight') is not None and p_['fight'] > TOWN_FIGHT:
                    p_['fight'] = TOWN_FIGHT
            try:
                if out.get('own_layout'):
                    # (cast on the game's template for their names and trades, they stand where its furniture was: in a
                    # layout of the Workshop's own those spots are nowhere, nobody was placed, and with no head placed
                    # nothing was owned (1,005 free containers in Hlervuld, the in-game walk 2026-11-03). Spotted again
                    # in the new place)
                    import random as _random
                    info_ = populate.place_info(db, out['key'])
                    rng_ = _random.Random('%s|%s|spots' % (seed, out['key']))
                    taken_, used_ = [], set()
                    for p_ in ppl:
                        sp_ = populate.spot(db, info_, p_, rng_, taken_, used_)
                        p_['spot'] = sp_[:4] if sp_ else None
                        p_['spot_by'] = (sp_[4] or '') if sp_ and len(sp_) > 4 else ''
                        if sp_:
                            taken_.append((sp_[0], sp_[1]))
                            if len(sp_) > 4 and sp_[4]:
                                used_.add(sp_[4])
                pl = populate.place(db, out['key'], ppl, own=True, lines=False)
                said += pl['people']
                folks += len(ppl)
                for k_ in {out['key']} | {k2 for k2, _s in out.get('from') or ()}:
                    try:
                        stand_people(db, k_)
                    except Exception as e_:
                        print('town people on the floor:', k_, e_)
            except EditError as e:
                print('town people:', name, e)
    if said:
        import populate
        import editing
        if populate.write_lines(db, said):
            editing.commit(db, 'Lines for the people of %s' % town)
    _drop_unled(db, tried)
    return {'interiors': made, 'people': folks, 'names': names, 'skipped': skipped}


def _drop_unled(db, keys):
    """The places of this run no door leads to, taken out: a pod copied without a door of its own outside, and the
    cell an own layout began before its builder gave up (a bakery of 18 things and three "pod 2"s no one could reach,
    the user's Estmorevale, 2026-11-03)."""
    import mapdata
    p = db.project
    mine = {k for k in p.cells if k.lower() in keys and not k.startswith('#')}
    if not mine:
        return 0
    led = set()
    for ck in list(p.cells):
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r['type'] == 'DOOR' and (r.get('to') or {}).get('key'):
                led.add(r['to']['key'].lower())
    gone = [k for k in mine if k.lower() not in led]
    for k in gone:
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)
    if gone:
        print('town: %d place(s) no door led to, taken out: %s' % (len(gone), gone[:6]))
        db.sync_project()
    return len(gone)
