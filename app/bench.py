"""The prefab workbench (web/bench.js): an empty space to put a building together from the game's own pieces, kept
between sessions, then set down in the world in one go.

The user's own words for it (2026-10-27): "a builder view where you snap pieces together, and then can lift that
built structure, which benefits from tools like snapping matching pieces together and filling in windows and
doors, and previewing it whole on the land before you place it in one go". Plan a prefab, which laid whole game
buildings over a drawn floor plan, "doesn't look anything like what I drew".

On the bench the ground is flat, at height 0, and a piece's pose is the game's [x, y, z, rx, ry, rz]. What it knows
comes from the exterior survey: the pieces of a style (the shelf), how the game joins them (snapping,
housemodules.snaps_among), which doors and windows it sets into each piece (filling the openings, learnt from the
game's buildings), and the outdoor building check (frombuilding.check, on flat ground)."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import adjacency
import exteriorsurvey as es
import housemodules as hm
import mapdata
import outside
import shellsurvey as ss
from editing import EditError
from project import APP_DIR

BENCH_DIR = os.path.join(APP_DIR, 'bench')
# the shelf's kinds, in its order; a piece is the first kind its name (or a door's record) says
KINDS = [('door', 'Doors', r'door|jamb|doorway|_entr|entrance'),
         ('window', 'Windows', r'window|_win|shutter|slit|dormer'),
         ('stairs', 'Stairs and steps', r'stair|step|ramp|ladder'),
         ('roof', 'Roofs', r'roof|dome|cupola|spire'),
         ('corner', 'Corners and towers', r'corner|cnr|turret|tower|_post|pillar|column|buttress'),
         ('floor', 'Floors, platforms and foundations', r'floor|plat|deck|landing|base|found|terrace|bridge|walkway|pier'),
         ('wall', 'Walls and building bodies', r'wall|_w_|_b_|house|building|block|hut|manor|pod|shack|_x_|stem|shell|_fb_')]
TRIM = ('trim', 'Trim and the rest')
FILL_RATE = 0.1                 # a door or window the game sets into a piece in at least this share of its buildings,
FILL_MIN = 2                    # and in this many at least: a hole in the piece's mesh is a hole either way (a house
                                # body's window spots are filled in 29% of its buildings each, its door in 43%)
SHELF_MAX = 90                  # pieces a kind on the shelf, the most used first


# ---------------------------------------------------------------- kept between sessions

def _path(name):
    return os.path.join(BENCH_DIR, re.sub(r'[^A-Za-z0-9 _\-]', '', name or 'bench').strip()[:60] or 'bench') + '.json'


def load(name='bench'):
    try:
        with open(_path(name), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'style': None, 'pieces': []}


def save(name, data):
    os.makedirs(BENCH_DIR, exist_ok=True)
    keep = {'style': data.get('style'), 'pieces': [{k: p[k] for k in ('k', 'id', 'type', 'p', 's') if k in p} for p in data.get('pieces') or []]}
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump(keep, f)
    return {'ok': True, 'n': len(keep['pieces'])}


# ---------------------------------------------------------------- the bench's pieces as the surveys' items

def items_of(db, pieces):
    """The bench's pieces as shellsurvey's items ({id, low, p, s, b, tag, ri, k, box, to}); those with no model the
    Workshop can read are left out."""
    out = []
    for p in pieces or ():
        ri = db.resolve_id(p['id'])
        if ri is None:
            continue
        b = mapdata.object_bounds(db, ri)
        if not b:
            continue
        pos = [float(v) for v in (list(p['p']) + [0] * 6)[:6]]
        s = float(p.get('s') or 1.0)
        out.append({'id': db.recs[ri][1], 'low': db.recs[ri][1].lower(), 'p': pos, 's': s, 'b': b, 'tag': db.recs[ri][0], 'ri': ri,
                    'k': str(p.get('k')), 'cell': '@bench', 'box': outside._box(b, pos, s), 'to': None})
    return out


def _survey(db):
    s = es.ready(db)
    if s is None:
        raise EditError('The Workshop is still learning how the game puts its buildings together (a few minutes, once, '
                        'in the background). The bench fills in when it is done.')
    return s


def _kind(low, tag):
    if tag == 'DOOR':
        return 'door'
    for k, _label, rx in KINDS:
        if re.search(rx, low):
            return k
    return TRIM[0]


# ---------------------------------------------------------------- the shelf

def styles(db):
    """{style: pieces of it the shelf has}, the styles the game's buildings are made in."""
    return {st: sum(len(k['pieces']) for k in shelf(db, st)['kinds']) for st in hm.styles(db)}


_shelf = {}


def shelf(db, style):
    """Every building piece of a style, by kind, the most used first: {'style', 'kinds': [{kind, label, pieces:
    [{id, n, tag}]}]}. From the game's buildings of that look (their pieces, doors and trim) and every outdoor piece
    whose name says the style."""
    s = _survey(db)
    key = (id(db.recs), style)
    if key in _shelf:
        return _shelf[key]
    placed = (s.get('outdoor') or {}).get('placed') or {}
    seen = Counter()
    names = {}
    for m in s['modules']:
        if hm.look(m) != style:
            continue
        for p in m.get('fpieces') or ():
            low = p['id'].lower()
            seen[low] += 1
            names[low] = p['id']
    for low, n in placed.items():
        if low not in seen and mapdata.style_of(low) == style:
            seen[low] += n
    kinds = defaultdict(list)
    for low, n in seen.items():
        ri = db.resolve_id(names.get(low, low))
        if ri is None or db.recs[ri][0] not in ('STAT', 'DOOR', 'ACTI'):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or 'marker' in low or 'collision' in low:
            continue
        tag = db.recs[ri][0]
        kinds[_kind(low, tag)].append({'id': db.recs[ri][1], 'n': max(n, placed.get(low, 0)), 'tag': tag})
    out = []
    for k, label, _rx in KINDS + [TRIM + ('',)]:
        if kinds.get(k):
            out.append({'kind': k, 'label': label, 'pieces': sorted(kinds[k], key=lambda x: (-x['n'], x['id'].lower()))[:SHELF_MAX]})
    _shelf[key] = {'style': style, 'kinds': out}
    return _shelf[key]


# ---------------------------------------------------------------- snapping

def snaps(db, pieces, rid, x, y, z, skip=None):
    """Where the game joins this model to the bench's pieces near (x, y, z), the best backed first (as the 3D view's
    snaps outdoors, housemodules.snaps)."""
    return {'snaps': hm.snaps_among(db, _survey(db), rid, x, y, items_of(db, pieces), skip)}


# ---------------------------------------------------------------- filling the openings

_fills = {}


def _fill_table(db):
    """{host model: [(fill id, lx, ly, lz, turn degrees, rate, n)]}: the doors and windows the game sets into each
    building piece and where, in the piece's own frame, learnt from the game's buildings (the exterior survey's
    modules, their doors and trim); rate: the share of the buildings with that piece that have it there."""
    s = _survey(db)
    if id(s) in _fills:
        return _fills[id(s)]
    hosts = Counter()
    seen = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])
    names = {}
    for m in s['modules']:
        ps = m.get('fpieces') or ()
        stat = [p for p in ps if not p.get('trim') and not p.get('door') and _kind(p['id'].lower(), '') != 'door']
        fills = [p for p in ps if p.get('door') or _kind(p['id'].lower(), '') in ('door', 'window')]
        for h in {p['id'].lower() for p in stat}:
            hosts[h] += m.get('uses', 1)
        for f in fills:
            fb_ = adjacency._box(db, f['id'])[1]
            if not fb_:
                continue
            fbox = outside._box(fb_, [f['x'], f['y'], f['z'], 0, 0, f['rz']], f.get('s') or 1.0)
            for h in stat:
                hb = adjacency._box(db, h['id'])[1]
                if not hb or not outside._touch(fbox, outside._box(hb, [h['x'], h['y'], h['z'], 0, 0, h['rz']], h.get('s') or 1.0), 8):
                    continue
                A = {'x': h['x'], 'y': h['y'], 'z': h['z'], 'rz': h['rz']}
                lx, ly = adjacency.to_local(A, f['x'], f['y'])
                turn = math.degrees((f['rz'] - h['rz']) % (2 * math.pi))
                q = int(round(turn / 15)) % 24
                key = (h['id'].lower(), f['id'].lower(), int(round(lx / 8)), int(round(ly / 8)), int(round((f['z'] - h['z']) / 8)), q)
                # (sums for the mean pose, by use; the turn as its step off the 15-degree key, so 359 and 1 agree)
                w = m.get('uses', 1)
                e = seen[key]
                e[0] += w
                e[1] += lx * w; e[2] += ly * w; e[3] += (f['z'] - h['z']) * w; e[4] += ((turn - q * 15 + 180) % 360 - 180) * w
                names[f['id'].lower()] = f['id']
    tab = defaultdict(list)
    for (host, fid, _x, _y, _z, q), (n, sx, sy, sz, st) in seen.items():
        tab[host].append((names[fid], sx / n, sy / n, sz / n, q * 15 + st / n, n / float(max(1, hosts[host])), n))
    for rows in tab.values():
        rows.sort(key=lambda r: -r[5])
    _fills[id(s)] = dict(tab)
    return _fills[id(s)]


def fill(db, pieces):
    """The doors and windows the game sets into the bench's pieces, where it sets them, that are not there yet:
    {'add': [{id, type, p, s, why}]}. A spot is filled once, with what the game sets there most."""
    tab = _fill_table(db)
    items = items_of(db, pieces)
    have = [(it['low'], it['p']) for it in items]
    add = []
    for it in items:
        if it['tag'] not in ('STAT', 'ACTI'):
            continue
        A = {'x': it['p'][0], 'y': it['p'][1], 'z': it['p'][2], 'rz': it['p'][5] % (2 * math.pi)}
        for fid, lx, ly, lz, turn, rate, n in tab.get(it['low'], ()):
            if rate < FILL_RATE or n < FILL_MIN:
                continue
            wx, wy = adjacency.to_world(A, lx, ly)
            p = [round(wx, 2), round(wy, 2), round(A['z'] + lz, 2), 0.0, 0.0, round((A['rz'] + math.radians(turn)) % (2 * math.pi), 5)]
            # (a spot that has a door or window already, this one or another, is filled)
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 40 and abs(p[2] - q[2]) < 60 and _kind(low, '') in ('door', 'window')
                   for low, q in have) or any(math.hypot(p[0] - a['p'][0], p[1] - a['p'][1]) < 40 and abs(p[2] - a['p'][2]) < 60 for a in add):
                continue
            ri = db.resolve_id(fid)
            if ri is None:
                continue
            add.append({'id': db.recs[ri][1], 'type': db.recs[ri][0], 'p': p, 's': 1.0,
                        'why': '%s in %d%% of the game\'s buildings with %s' % (fid, round(rate * 100), it['id'])})
            have.append((fid.lower(), p))
    return {'add': add}


# ---------------------------------------------------------------- the check

def check(db, pieces):
    """The outdoor building check (frombuilding.check) on the bench's pieces, the ground flat at 0: {ok, lines}."""
    import frombuilding as fb
    items = items_of(db, pieces)
    group = [it for it in items if it['tag'] in ('STAT', 'ACTI')]
    if not group:
        raise EditError('Put some pieces on the bench first.')
    doors = [it for it in items if it['tag'] == 'DOOR']
    door = min(doors, key=lambda d: d['box'][4]) if doors else None
    x0, y0 = min(g['box'][0] for g in group), min(g['box'][1] for g in group)
    x1, y1 = max(g['box'][2] for g in group), max(g['box'][3] for g in group)
    centre = ((x0 + x1) / 2, (y0 + y1) / 2)
    frame = None
    if door is not None:
        ux, uy = fb._door_inward(door, centre)
        frame = ss.Frame(door['p'][0], door['p'][1], door['p'][2] + door['b'][2] * door['s'], ux, uy)
    doubled = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if a['low'] == b['low'] and math.dist(a['p'][:3], b['p'][:3]) < 2:
                doubled.append(b)
    bld = {'group': group, 'door': door, 'doors': doors, 'frame': frame, 'cell': '@bench', 'items': items,
           'centre': centre, 'doubled': doubled}
    r = fb.check(db, bld, outdoor=True, ground=lambda x, y: 0.0)
    return {'ok': r['ok'], 'lines': r['lines'], 'style': ss.style_of_group(group) or None}


# ---------------------------------------------------------------- starting from one of the game's buildings

def buildings(db, style):
    """The game's buildings of a style, to start from: [{key, name, uses, pieces}], the most built first."""
    s = _survey(db)
    best = {}
    for m in s['modules']:
        if hm.look(m) != style or not m.get('fpieces'):
            continue
        if m['main'] not in best or m['uses'] > best[m['main']]['uses']:
            best[m['main']] = m
    return [{'key': m['main'], 'name': hm._label(m), 'uses': m['uses'], 'pieces': len(m['fpieces']), 'home': hm.homely(m)}
            for m in sorted(best.values(), key=lambda m: (-m['uses'], m['main']))]


def building(db, key):
    """One of the game's buildings as bench pieces, its door at the middle facing -y, standing on the bench's ground:
    {'pieces': [{id, type, p, s}]}."""
    s = _survey(db)
    ms = [m for m in s['modules'] if m['main'] == key and m.get('fpieces')]
    if not ms:
        raise EditError('The Workshop does not know that building.')
    m = max(ms, key=lambda m: m['uses'])
    g = m.get('fground', -40.0)
    out = []
    for p in m['fpieces']:
        ri = db.resolve_id(p['id'])
        if ri is None:
            continue
        out.append({'id': db.recs[ri][1], 'type': db.recs[ri][0], 's': p.get('s') or 1.0,
                    'p': [round(p['x'], 2), round(p['y'], 2), round(p['z'] - g, 2), p.get('rx', 0.0), p.get('ry', 0.0), p['rz']]})
    return {'pieces': out, 'name': hm._label(m)}
