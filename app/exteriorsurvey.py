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

VERSION = 4
CLIMB = re.compile(r'stair|step|ramp|ladder|platform|walkway|landing')
_cache = {}


def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'exteriorsurvey_%s_v%d.json' % (taste.sig(db), VERSION))


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


def survey(db):
    """{'joins': {model: {'n': buildings, 'sides': {side: {rel: n}}}}, 'sets': {families: n},
    'modules': [...]} (kept on disk)."""
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
    shells = ss.survey(db)
    learnt = shells['learnt']
    memo, bmemo = {}, {}
    joins = defaultdict(lambda: {'n': 0, 'sides': defaultdict(Counter)})
    bigj = defaultdict(lambda: defaultdict(Counter))
    counted = set()
    sets = Counter()
    modules = {}
    for p in shells['pairs']:
        ef = p['eframe']
        items = ss.near_items(db, ef['x'], ef['y'], memo, bmemo)
        if len(memo) > 60:
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
        for g in group + climb + [d]:
            lx, ly = frame.to(g['p'][0], g['p'][1])
            fpieces.append({'id': g['id'], 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(g['p'][2] - frame.z, 1), 'rx': g['p'][3],
                            'ry': g['p'][4], 'rz': round((g['p'][5] - th) % (2 * math.pi), 4), 's': g['s'], 'door': g is d})
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
           'sets': dict(sets.most_common(60)), 'modules': mods}
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
