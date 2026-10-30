"""The exterior survey: how the game's own buildings are put together from exterior pieces, and which
of them make good prefabs for a home that is easily built inside.

Read from the buildings the shell survey found (every game interior's building, shellsurvey.py: the
pieces joined to the piece its door is set into, stopping at a neighbour's door):

  joins     for every two pieces of a building whose boxes touch, B in A's frame as adjacency.py
            records it (B's id, its origin in A's frame to 8 units, its turn to 15 degrees) on the face
            of A it stands against, or 'in' when B stands inside A's box (a window, an entrance porch, a
            chimney set into a wall piece): per model, what the game joins to it, where, how often.
            From it come the checks of a building put together by hand (a piece joined the way the game
            never joins it) and the candidates for the next piece.
  sets      which families are mixed in one building (Common walls with Imperial windows, a Hlaalu
            house with Common stairs), counted.
  modules   each distinct building (its sorted pieces) once, with its pieces relative to its door
            (outside.py's frame), its outline and storeys, and its size in interior tiles of the kit the
            game builds its interiors in: the tiles that lie at least half inside its walls, and how
            much of the outline they fill ('fill': tiles' area over the outline's). A module whose
            walls run on the kit's tile lines fills close to 1 and builds as an interior without
            leeway; the catalogue is ordered by that, then by how often the game uses it.

Kept in the cache folder under the load order's signature. Nothing here edits a place."""
import json
import math
import re
import os
from collections import Counter, defaultdict

import adjacency
import kits
import outside
import shellsurvey as ss

VERSION = 12                  # (5: buildings behind one-piece interiors too, and 'outdoor': joins from every cell;
                               # 6: row houses, one-piece buildings and lighthouses, shellsurvey v5; 7: shellsurvey v6;
                               # 8: outdoor joins kept up to 60 a face; 9: and their exact poses; 10: modules keep
                               # their own trim; 11: and their other doors; 12: doors among the outdoor joins, and twins
                               # for the pieces no place has)
KEEP = 200                     # outdoor joins kept a face, the most used first
# what is no building's trim: plants, rocks, loose things, lights, and a shop's or a guild's sign (not for a new house)
NOT_TRIM = re.compile(r'flora|tree|grass|rock|terrain|kelp|bush|shrub|mushroom|misc_|light_|contain|crate|barrel|sack|basket|'
                      r'sign|marker|_bed|chair|bench|table|furn_(?!.*(overhang|awning|banner|shade|canopy))|'
                      r'canal|dock|piling|icicle|_x_house_?\d|_hut_?\d|_wall_gate|collision')
CLIMB = re.compile(r'stair|step|ramp|ladder|platform|walkway|landing')
_cache = {}


def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'exteriorsurvey_%s_v%d.json' % (taste.sig(db) + _outdoor_sig(db), VERSION))


_osig = {}


def _outdoor_sig(db):
    """The plugins with outdoor places but no interiors, each with its size, for the cache's name: taste.sig keys
    the surveys on the interior plugins only, and this survey learns from every exterior cell too, so a mod of
    outdoor buildings alone must make it learn again (promised the user, 2026-10-27). '' when there are none, so
    the caches of a load order without such plugins keep their names."""
    if _osig.get('recs') is db.recs:
        return _osig['sig']
    import hashlib
    plugins = db.plugins or []
    proj = getattr(db, 'proj_pidx', None)
    inside, outside_ = set(), set()
    for r in db.recs:
        if r[0] == 'CELL':
            (inside if r[5] == 'interior' else outside_).add(r[3])
    parts = sorted('%s:%s' % (plugins[i]['name'].lower(), plugins[i].get('size') or 0)
                   for i in outside_ - inside if i != proj and i < len(plugins))
    s = ('x' + hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:8]) if parts else ''
    _osig.update({'recs': db.recs, 'sig': s})
    return s


def _piece(it):
    """An item as adjacency.py's piece."""
    return {'ref': it['k'], 'id': it['low'], 'x': it['p'][0], 'y': it['p'][1], 'z': it['p'][2], 'rz': it['p'][5] % (2 * math.pi),
            's': it['s'] or 1.0, 'b': it['b']}


def joins_of(group):
    """[(A id, side or 'in', relation)] for every touching pair of the building's pieces."""
    ps = [_piece(it) for it in group]
    out = []
    for A in ps:
        for B in ps:
            if A is B:
                continue
            s_ = adjacency.side_of(A, B)
            if s_ is None:
                a = adjacency.own_box(A)
                L = adjacency.local_box(A, B)
                # (B wholly or mostly within A's box: set into it)
                inside = all(L[k] >= a[k] - 24 for k in range(3)) and all(L[k] <= a[k] + 24 for k in range(3, 6))
                if not inside:
                    continue
                s_ = 'in'
            out.append((A['id'], s_, adjacency.relation(A, B)))
    return out


def is_big(it):
    """A piece a building is made of rather than trimmed with: 384 across and 256 tall or more."""
    b, s = it['b'], it['s'] or 1.0
    return max(b[3] - b[0], b[4] - b[1]) * s >= 384 and (b[5] - b[2]) * s >= 256


def rel_str(rel):
    return '%s@%d,%d,%d/%d' % rel


def _kit_tile(db, kit):
    kp = kits.kit_pieces(db, kit) if kit else None
    return kp['tile'] if kp else 256


DOORS = True                   # doors are outdoor pieces too (v12): a door in its frame is a join like any other


def is_outdoor_piece(it):
    """A made thing standing outdoors that buildings are put together from or dressed with: walls, towers, wings,
    porches, stairs, fences, awnings, foundations, bridges, docks, and their doors. Not the land's rocks and plants,
    not clutter. (Doors since v12: the game stands 6,190 outdoors, and none was learnt, so a door never snapped into its
    frame, the user's Reach double doors, 2026-10-29.)"""
    import landscape
    if it['tag'] not in (('STAT', 'DOOR') if DOORS else ('STAT',)) or landscape.NATURAL.search(it['low']):
        return False
    b, s = it['b'], it['s'] or 1.0
    w, d, h = (b[3] - b[0]) * s, (b[4] - b[1]) * s, (b[5] - b[2]) * s
    return max(w, d) >= 64 and h >= 24 and max(w, d) < 6000


def outdoor_joins(db, stage=(0, 1), cells=None):
    """How the game joins its made pieces anywhere outdoors, in a building with a door or not (a town wall, a
    tower, a bridge, a dock, a stair up to a door): {'joins': {model: {side: {rel: n}}}, 'placed': {model: n}}.
    Every two touching pieces in every exterior cell, each in the other's frame as adjacency.py records it.
    Measured 2026-10-27: the buildings with a door into a kit interior had only ~8% of the game's outdoor
    building pieces in them; this is what gives the rest a place in the builder. cells: only these (a lab's half of
    them, to test on the other half); else every exterior cell, and the twins of the pieces placed nowhere."""
    joins = defaultdict(lambda: defaultdict(Counter))
    # (each join's exact pose too, summed: the key is on the kits' grid (8 units, 15 degrees), and outdoors the game
    # turns its pieces any way, so a pose rebuilt from the key alone fell units off the real one, 2026-10-27)
    exact = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    placed = Counter()
    memo, bmemo = {}, {}
    every = cells is None
    cells = sorted(key for (tag, key) in db.by_key if tag == 'CELL' and key.startswith('#')) if every else cells
    import background
    for n, ek in enumerate(cells):
        background.progress(n, len(cells), 'outdoor places', stage)
        items = [it for it in ss._cell_items(db, ek, memo, bmemo) if is_outdoor_piece(it)]
        memo.clear()
        for it in items:
            placed[it['low']] += 1
        items.sort(key=lambda it: it['box'][0])
        ps = [_piece(it) for it in items]
        for i, A in enumerate(items):
            for j in range(i + 1, len(items)):
                B = items[j]
                if B['box'][0] > A['box'][2] + 8:
                    break                        # (sorted by west edge: nothing further east can touch)
                if not outside._touch(A['box'], B['box'], 8):
                    continue
                for P, Q in ((ps[i], ps[j]), (ps[j], ps[i])):
                    s_ = adjacency.side_of(P, Q)
                    if s_ is None:
                        a = adjacency.own_box(P)
                        L = adjacency.local_box(P, Q)
                        if not (all(L[k] >= a[k] - 24 for k in range(3)) and all(L[k] <= a[k] + 24 for k in range(3, 6))):
                            continue
                        s_ = 'in'
                    rel = adjacency.relation(P, Q)
                    rs = rel_str(rel)
                    joins[P['id']][s_][rs] += 1
                    lx, ly = adjacency.to_local(P, Q['x'], Q['y'])
                    turn = (math.degrees((Q['rz'] - P['rz']) % (2 * math.pi)) - rel[4] + 180) % 360 - 180
                    e = exact[(P['id'], s_, rs)]
                    e[0] += lx; e[1] += ly; e[2] += Q['z'] - P['z']; e[3] += turn
    # (up to KEEP per face: a house has canal pieces, neighbours and its own balcony against one face, and with 12 the
    # balcony's own join was lost; snapping offers what the game did, the rarer joins too)
    kept = {k: {s_: dict(c.most_common(KEEP)) for s_, c in v.items()} for k, v in joins.items()}
    ex = {}
    for k, v in kept.items():
        for s_, rels in v.items():
            for rs, n in rels.items():
                e = exact[(k, s_, rs)]
                ex.setdefault(k, {}).setdefault(s_, {})[rs] = [round(e[0] / n, 2), round(e[1] / n, 2), round(e[2] / n, 2),
                                                                round(int(rs.rsplit('/', 1)[1]) + e[3] / n, 3)]
    return {'joins': kept, 'exact': ex, 'placed': dict(placed), 'twins': twins(db, kept) if every else {}}


# a piece's name without its variant: "_01", "_01a", "_02b" at the end (the kits' siblings of one size)
_STEM = re.compile(r'_?\d+[a-z]?$')
TWIN_FIT = 4                   # a twin is the same size as the piece to this many units each way


def twins(db, joins):
    """{model: twin}: for the made pieces no place in the load order has, a placed sibling of the same name but for its
    variant number and the same size, whose joins it takes (snaps_among): the kits make their variants to one grid,
    a door frame 01a as its 01 (the user's Reach door frames, 2026-10-29). The most joined sibling when several fit."""
    import mapdata
    has = set(joins)
    for sides in joins.values():
        for rels in sides.values():
            for rs in rels:
                has.add(rs.split('@')[0])
    by_stem = defaultdict(list)
    for low in has:
        by_stem[_STEM.sub('', low)].append(low)
    use = Counter({k: sum(sum(r.values()) for r in v.values()) for k, v in joins.items()})
    bounds = {}

    def size(low):
        if low not in bounds:
            ri = db.resolve_id(low)
            b = mapdata.object_bounds(db, ri) if ri is not None else None
            bounds[low] = (b[3] - b[0], b[4] - b[1], b[5] - b[2]) if b else None
        return bounds[low]
    out = {}
    for r in db.recs:
        if r[0] not in ('STAT', 'DOOR'):
            continue
        low = r[1].lower()
        if low in has or low in out:
            continue
        sib = by_stem.get(_STEM.sub('', low))
        if not sib:
            continue
        me = size(low)
        if not me:
            continue
        fits = [o for o in sib if size(o) and all(abs(a - b) <= TWIN_FIT for a, b in zip(me, size(o)))]
        if fits:
            out[low] = max(fits, key=lambda o: (use[o], o))
    return out


def survey(db):
    """{'joins': {model: {'n': buildings, 'sides': {side: {rel: n}}}}, 'sets': {families: n},
    'modules': [...], 'outdoor': outdoor_joins()} (kept on disk)."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache['survey'] = (db.recs, saved)
        return saved
    except Exception:
        pass
    # (three stages for the Learning bar: the places with an interior, unless learnt already; the buildings outside
    # their doors; every outdoor place's joins)
    import background
    shells = ss.survey(db, stage=(0, 3))
    learnt = shells['learnt']
    memo, bmemo = {}, {}
    joins = defaultdict(lambda: {'n': 0, 'sides': defaultdict(Counter)})
    bigj = defaultdict(lambda: defaultdict(Counter))
    counted = set()
    sets = Counter()
    modules = {}
    for n_p, p in enumerate(shells['pairs']):
        background.progress(n_p, len(shells['pairs']), 'buildings', (1, 3))
        ef = p['eframe']
        items = ss.near_items(db, ef['x'], ef['y'], memo, bmemo)
        if len(memo) > 600:
            memo.clear()
        d = next((it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'].lower() == p['key']
                  and math.hypot(it['p'][0] - ef['x'], it['p'][1] - ef['y']) < 5), None)
        if d is None:
            continue
        others = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'] and it['to']['cell'].lower() != p['key']]
        group = ss.structure(items, d['box'], others)
        if not group:
            continue
        # (one building reached from two interiors, a house and its upstairs flat, counts once)
        where = tuple(sorted((it['low'], round(it['p'][0]), round(it['p'][1])) for it in group))
        if where in counted:
            continue
        counted.add(where)
        seen_models = set()
        for a, s_, rel in joins_of(group):
            if a not in seen_models:
                joins[a]['n'] += 1
                seen_models.add(a)
            joins[a]['sides'][s_][rel_str(rel)] += 1
        # (the big pieces among them, a wing, a tower, a storey, a wall run, and how the game joins them: the
        # candidates for joining a module to another, housemodules.py)
        for a, s_, rel in joins_of([it for it in group if is_big(it)]):
            bigj[a][s_][rel_str(rel)] += 1
        sets[' + '.join(sorted({outside._family(it['id']) for it in group}))] += 1
        sig = ' '.join(sorted(it['low'] for it in group))
        if sig in modules:
            modules[sig]['uses'] += 1
            modules[sig]['examples'].append(p['key'])
            continue
        frame = ss.Frame(**{'ox': ef['x'], 'oy': ef['y'], 'sill': ef['z'], 'ux': ef['ux'], 'uy': ef['uy']})
        same = [it for it in items if it['tag'] == 'DOOR' and any(outside._touch(it['box'], g['box'], 8) for g in group)]
        g0 = ss.outline(db, group, frame, same, 0)
        if not g0['closed']:
            continue
        pr = ss.predict(learnt, p['building'])
        T = _kit_tile(db, pr['kit'])
        import frombuilding
        tiles = frombuilding._tiles_in(set(g0['cells']), T)
        fill = len(tiles) * T * T / float(g0['area'])
        dp = d['p']
        pieces = []
        for g in group:
            lx, ly = outside._local(g['p'][0] - dp[0], g['p'][1] - dp[1], dp[5])
            pieces.append({'id': g['id'], 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(g['p'][2] - dp[2], 1),
                           'rx': g['p'][3], 'ry': g['p'][4], 'rz': round((g['p'][5] - dp[5]) % (2 * math.pi), 4), 's': g['s']})
        xs = [t[0] for t in tiles]
        ys = [t[1] for t in tiles]
        # (the ground in front of the door, under it: a module is set down on the ground the way the game's stands)
        import mapdata
        gz = mapdata.terrain_z(db, ef['x'] - ef['ux'] * 120, ef['y'] - ef['uy'] * 120)
        ground = round(gz - dp[2], 1) if gz is not None and -400 < gz - ef['z'] < 60 else round(ef['z'] - dp[2] - 40, 1)
        # (and the same in the door's frame, shellsurvey.Frame: +y inward, the door at the origin, the tiles laid as the
        # interior planner lays them, centres at (i T, (j + 1/2) T), and those of the storeys above where the walls close
        # round: what the prefab planner fits to a volume, housemodules.fit_volume)
        th = frame.yaw()
        fpieces = []
        # (and the stairs, steps, ramps and platforms that touch it: a high door's way up; the building reader
        # leaves them out of the building itself, and a prefab without them had a door no one could reach)
        climb = [it for it in items if CLIMB.search(it['low']) and it['tag'] == 'STAT' and it not in group
                 and any(outside._touch(it['box'], g['box'], 24) for g in group)]
        # (and its trim, as the game dressed this building: windows, awnings, chimneys, patios, foundations, a Reach
        # house's roof and beams. The building reader keeps to the big pieces, and a prefab came out barer than the
        # game's own: Hlaalu's windows 1.5 a building beside it, 0.1 in it; Reach's roofs and beams 11, measured
        # 2026-10-27. Its own: touching it, its middle over it)
        x0, y0 = min(g['box'][0] for g in group) - 64, min(g['box'][1] for g in group) - 64
        x1, y1 = max(g['box'][2] for g in group) + 64, max(g['box'][3] for g in group) + 64
        taken = {id(g) for g in group + climb} | {id(d)}
        # (a big building piece only when it lies over the building, nearly all of it: a Reach house's roof is its own;
        # a canal, a town wall or a dock running past is the town's)
        def over(it):
            b = it['box']
            a = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
            return max(0, min(b[2], x1) - max(b[0], x0)) * max(0, min(b[3], y1) - max(b[1], y0)) / a >= 0.8
        trim = [it for it in items if id(it) not in taken and it['tag'] in ('STAT', 'ACTI') and it.get('b') and not NOT_TRIM.search(it['low'])
                and (not ss.is_building_piece(it, big=True) or over(it))
                and x0 <= (it['box'][0] + it['box'][2]) / 2 <= x1 and y0 <= (it['box'][1] + it['box'][3]) / 2 <= y1
                and any(outside._touch(it['box'], g['box'], 24) for g in group)]
        trim_ids = {id(it) for it in trim}
        # (and its other doors, to its other interiors or an upper floor: without them a prefab had a door-sized hole
        # in its wall where the game's has a door, "walls open, 1 gap 128 wide", 2026-10-27. Placed, they are plain
        # doors; a load door's way is the placed reference's, not the model's)
        doors2 = [it for it in same if it is not d and id(it) not in taken]
        for g in group + climb + [d] + doors2 + trim:
            lx, ly = frame.to(g['p'][0], g['p'][1])
            fpieces.append({'id': g['id'], 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(g['p'][2] - frame.z, 1), 'rx': g['p'][3],
                            'ry': g['p'][4], 'rz': round((g['p'][5] - th) % (2 * math.pi), 4), 's': g['s'], 'door': g is d})
            if id(g) in trim_ids:
                fpieces[-1]['trim'] = True
        fup = []
        below = set(tiles)
        for k in (1, 2):
            u = ss.outline(db, group, frame, same, k)
            if not (u['closed'] and u['area'] >= frombuilding.UP_MIN * g0['area']):
                break
            below = frombuilding._tiles_in(set(u['cells']), T, keep_door=False) & below
            if len(below) < 2:
                break
            fup.append(sorted(below))
        modules[sig] = {'main': p['building']['main'], 'style': pr['style'], 'kit': pr['kit'], 'tile': T, 'pieces': pieces,
                        'fpieces': fpieces, 'ftiles': sorted(tiles), 'fup': fup,
                        'fground': round(gz - frame.z, 1) if gz is not None and -400 < gz - ef['z'] < 60 else -40.0,
                        'door_scale': d['s'], 'ground': ground, 'door_rz': round(dp[5], 4),
                        'door': d['id'], 'area': g0['area'], 'height': p['building']['height'], 'floors': pr['floors'],
                        'tiles': len(tiles), 'tiles_wd': [max(xs) - min(xs) + 1, max(ys) - min(ys) + 1] if tiles else None,
                        'fill': round(fill, 3), 'uses': 1, 'examples': [p['key']], 'game_fit': p.get('overlay')}
    mods = sorted(modules.values(), key=lambda m: (-round(1 - abs(1 - m['fill']), 1), -m['uses']))
    for m in mods:
        m['examples'] = m['examples'][:5]
    out = {'version': VERSION, 'buildings': sum(m['uses'] for m in mods),
           'joins': {k: {'n': v['n'], 'sides': {s_: dict(c.most_common(12)) for s_, c in v['sides'].items()}} for k, v in joins.items()},
           'big': {k: {s_: dict(c) for s_, c in v.items()} for k, v in bigj.items()},
           'sets': dict(sets.most_common(60)), 'modules': mods, 'outdoor': outdoor_joins(db, (2, 3))}
    _cache['survey'] = (db.recs, out)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


def ready(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    import background
    background.start('how the game puts its buildings together', lambda: survey(db), task=('exteriorsurvey', 'survey', []))
    return None


def odd_joins(db, group, min_n=3):
    """For a building put together by hand: the touching pairs the game never joins that way, though
    it has the model often enough to know (at least min_n buildings): [(A id, side, B id, words)]."""
    s = ready(db)
    if not s:
        return None
    out = []
    for a, s_, rel in joins_of(group):
        j = s['joins'].get(a)
        if not j or j['n'] < min_n:
            continue
        bid = rel[0]
        here = j['sides'].get(s_, {})
        if any(k.split('@')[0] == bid for k in here):
            continue
        # (the game joins B to A, only on another face or turned otherwise: say where it does)
        elsewhere = [(k, n) for sd, c in j['sides'].items() for k, n in c.items() if k.split('@')[0] == bid]
        if elsewhere:
            words = 'the game joins %s to %s, but not on this side' % (bid, a)
        else:
            words = 'the game never joins %s to %s' % (bid, a)
        out.append((a, s_, bid, words))
    return out


def modules(db, style=None, limit=40):
    """The catalogue: whole buildings the game uses, the best fitting first (optionally of one style)."""
    s = ready(db)
    if not s:
        return None
    lst = [m for m in s['modules'] if style is None or m['style'] == style]
    return lst[:limit]
