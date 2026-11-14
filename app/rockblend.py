"""Rock blending: the culture's rocks set into a made town's steep ground the way the game's towns have them (the user,
2026-11-08, on Akamora, Teyn and Narsis: "observe how the cliff and rock palette allows us to achieve a rugged and lofty
appearance"; "for cliff and rock pieces, the naked edges on the bottom are never exposed. They are always sufficiently
buried into the dirt, from all vantage points"). Terrain alone reads as smooth dirt; the game's hill towns get their
character from rocks that hide the banks and seams the ground work leaves, carry the perched floors, and never show a
cut-off bottom.

What is learnt (learn, cached like the other surveys): over the game's towns (townsurvey), every rock static 256+
across: by culture, which rocks its towns stand and how many a building (towns with 300+ relief); by the slope under
the rock (flat, gentle, steep, cliff), how big, how deep sunk at the middle (ground - box bottom), how far tilted and
how high its top stands over the land; round each building, how many rocks stand within 600 of its footprint, on
which side of it (behind the door line, beside, in front), how far off, and their tops against its floor.

What is placed (blend, from townbuild.make after the ground work): at the culture's rate a building, in the game's
shares behind, beside and in front, rocks round each house on its terrace's banks; under the downhill edge of a floor
standing over the land, a rock whose top meets the floor; along the cut banks of the footpaths and stair streets;
at the feet of the wall's towers and along the bank filled under the wall; and, where the town's ground is a knoll,
a crown outcrop of big rocks packed into one mass with small rocks at their feet (the Lan Orethan hilltop the user
pointed to: "this hill looks like a mountain because of clever rock placement"). Each rock lies with its long axis
down the slope more often than along it, tilted toward the slope's fall within the game's spread, sunk to the game's
depth for its slope; never on a street, a plot, a footpath's tread, a door's front or the wall's line, and never
in the way of a door or a stair.

The burial rule (check_burial): a rock's bottom rim is read from its mesh (edges.rim: the open edges of its shell,
the way edges.py reads a building piece's ends); every rim point is put in the world at the rock's pose and must lie
under the ground there. A rock whose rim shows is sunk further, up to a share of its height, else dropped: no rock
with a naked bottom edge is placed. (The box's perimeter is no guide: it hangs over the slope where the mesh does not,
and called 20-40% of the game's rocks exposed.)"""
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

import mapdata

VERSION = 1
BINS = ('flat', 'gentle', 'steep', 'cliff')
ROCK = re.compile(r'rock|cliff|terrain_|boulder|stone(?!wall)|crag|ledge', re.I)
NOT = re.compile(r'door|wall_|railing|stair|step|bridge|platform|sign|lamp|flora|tree|barrel|crate|fence|gate|menhir|_x_|cave|entr|ruin|shrine|pillar|statue|well|dock|pier|mtpeak|terredge|cliffs', re.I)
MIN_ACROSS = 256               # a rock piece is at least this across (smaller ones are the dressing's business)
MIN_RELIEF = 300               # a town with less rise between its buildings than this teaches no rates (a flat town's rocks are its
                               # land's, not its hill's)
NEAR = 600                     # a rock within this of a building's footprint is one of its rocks (the survey's reach)
FEW = 40                       # a culture with fewer rocks than this in its hill towns borrows a kin's figures
RATE_CAP = 16.0                # rocks a building at most (the camps read 29-31 a "building": tents among boulders)
SURROUND = (0.4, 1.6)          # the land round the town scales the rate within this (surroundings)
KIN = {'Imperial Legion': 'Imperial', 'Imperial': 'Gold Coast', 'Common': 'Imperial', 'Nordic': 'Reach', 'Reach': 'Nordic',
       'Stronghold': 'Dunmer', 'Ashlander': 'Velothi', 'Mine': 'Redoran', 'Mournhold': 'Dunmer', 'Indoril': 'Dunmer'}
MARGIN = 6.0                   # a rim point lies at least this far under the ground
SINK_SHARE = 0.8               # a rock is sunk at most this share of its height to bury its rim, else dropped
TOP_MIN = 48.0                 # ... and must still stand this far over the ground at its middle
SCALE = (0.6, 1.8)             # a rock's scale is kept in this range
SPREAD = 0.6                   # two rocks' centres at least this share of their mean size apart (an outcrop's OVERLAP less)
OVERLAP = 0.4
FLOOR_OVER = 160.0             # a floor standing this far over the land at an edge gets a rock under it
FLOOR_P = 0.8                  # ... with this chance (times the rate factor), one a building
OVERSAMPLE = 1.3               # rocks tried a building over the count drawn: about a third find no spot (streets, plots, the wall)
ALIGN = 0.3                    # the share of rocks laid with their long axis down the slope (the game's lie nearly any way
                               # to it: |cos| p50 0.70, random's 0.71)
FLOOR_GAP = (16.0, 100.0)      # ... whose top stands this far under the floor
PATH_EVERY = 420.0             # a footpath's cut bank gets a rock about every this far, at the culture's rate
PATH_P = 0.55
BANK = 64.0                    # a bank is a rise of this much over the tread's edge
WALL_EVERY = 560.0             # the filled bank under a wall gets a rock about every this far
WALL_P = 0.6
TOWER_P = 0.8                  # a tower's outer foot gets a rock with this chance (times the culture's rate factor)
KNOLL_REACH = 1200.0           # a knoll: the ground falls KNOLL_DROP within this every way from its top
KNOLL_DROP = 200.0
CROWN_R = 1400.0               # the crown outcrop reaches this far from the top
CROWN_N = 21                   # big rocks on a hill of CROWN_RELIEF, at rate factor 1 (Lan Orethan's)
CROWN_RELIEF = 516.0
CROWN_SIZE = [420, 480, 570, 700, 920]        # (its rocks' sizes, p10 to p90)
CROWN_SINK = [100, 150, 217, 300, 420]
CROWN_H = [140, 170, 210, 420, 1090]          # (its rocks' heights)
BANK_STEEP = 0.7               # a land vertex is bank when a facet through it is this steep (one in 0.7: 35 degrees)
BANK_REACH = 1200.0            # ... and stands within this of a building or a street
BANK_COVER = 0.85              # the bank pass stops when this share of the town's steep vertices is covered (the game's
#                                hill towns p50 0.90, rocks most of it: 0.04 of their land bare without them, 0.008 with)
BANK_SHOULDER = 640.0          # a bank within this of a street's edge is the street's shoulder: shored up first
BANK_MAX = 260                 # rocks the pass lays at most
BODY = 0.85                    # a rock's body reaches this share of its half-size from its middle
DOOR_CLEAR = 256.0             # and stays this far off every door
BANK_STREET_KEEP = 0.5         # a bank rock's middle stands at least this share of its half-size off a street's edge
BANK_TRIES = 7                 # tries a bank vertex: smaller after a spot refused for room, taller after a rim that shows
BANK_OFFS = (0.15, -0.2, 0.35, 0.0, -0.4, 0.25, 0.5)   # (the middle's offset down the fall, a share of the half-size)
MASS_MIN = 8                   # a bare bank of this many steep vertices under one rock takes a big rock first (the game's towns:
                               # a quarter of their rocks 700+ across, 8-13 steep vertices a rock where rocks do the covering;
                               # ours were p50 350, p90 650, 3-4 vertices a rock and 5-14 rocks a building, lab 2026-11-10)
MASS_SIZES = (1800.0, 1300.0, 900.0, 650.0)   # (the sizes tried, biggest first)
MASS_OFFS = ((0.0, 0.0),) + tuple((r * math.cos(k * math.pi / 4), r * math.sin(k * math.pi / 4)) for r in (0.35, 0.7) for k in range(8))
MASS_PLOT = 0.7                # (a big rock's body off the plots: it laps one by under a third of its half width)
MASS_TRIES = 25                # (the spots tried a size a round, the barest first)
BANK_BACK = 160.0              # (a bank's rock is stood back from a street at most this far from its bank's spot)
ROAD_NEAR = 700.0              # (a paved patch this near a street is that street's: its bank may take rocks)
STONE_CLUMPS = 0.18            # clumps of rock a building on the town's gentle open ground by its streets: the user set 12 rocks by
                               # hand in their town of about two dozen houses, in clumps (88 to 465 apart) at the streets' edges,
                               # 535 and more from the houses, their feet 52 to 383 under the ground
STONE_SLOPE = 0.35             # (on ground no steeper than this: the banks are the bank pass's)
STONE_HOUSE = 400.0            # (this far from a building at least)
STONE_STREET = 640.0           # (within this of a street's edge)
STONE_APART = 1200.0           # (one clump this far from the next)
STONE_SIZE = (420.0, 900.0)    # (its big rock across)
BANK_SMALLEST = 200.0          # (the smallest bank rock across; banks rocks lap each other at OVERLAP, packed. 150, more tries
                               # and a lean back against the bank were tried 2026-11-11: no rock more, the rim rule drops them)
LEAN_MAX = 38.0
STREET_SIDE = 220.0            # (a bank's rock this near a street is one of the street's side)
TOP_SHARE = 0.2                # one model is at most this share of a town's rocks (the game's hill towns: the commonest
                               # 0.21 of a town's rocks, the three commonest 0.47; ours 0.26 to 0.36 and 0.58, lab 2026-11-10)
CLONE_TURN = 0.5               # two touching rocks of one model turned within this of each other (radians) and within
CLONE_SCALE = 1.25             # ... this of each other's size read as copies: 0.00 to 0.02 of the game's touching pairs,
                               # 0.05 to 0.09 of ours (bank rocks all lie along their bank). The second is turned end for end,
                               # else another model is drawn
_mem = {}
_rims = {}


# ------------------------------------------------------------------------------------------------- the survey
def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'rockblend_%s_v%d.json' % (_sig(db), VERSION))


def ready(db):
    """The survey if learnt (in memory or on disk); else None, and the survey process learns it meanwhile."""
    if id(db.recs) in _mem or os.path.isfile(_disk(db)):
        try:
            return learn(db)
        except Exception:
            return None
    import background
    background.start("the game's rocks round its towns", lambda: learn(db), task=('rockblend', 'learn', []))
    return None


def slope_bin(s):
    return 'flat' if s < 0.1 else 'gentle' if s < 0.25 else 'steep' if s < 0.5 else 'cliff'


def _pcts(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    return [round(v[min(len(v) - 1, int(len(v) * p))], 1) for p in (0.1, 0.25, 0.5, 0.75, 0.9)]


def is_rock(rid):
    low = rid.lower()
    return bool(ROCK.search(low)) and not NOT.search(low)


def _grad(db, x, y, d=128.0):
    gxp, gxm = mapdata.terrain_z(db, x + d, y), mapdata.terrain_z(db, x - d, y)
    gyp, gym = mapdata.terrain_z(db, x, y + d), mapdata.terrain_z(db, x, y - d)
    if None in (gxp, gxm, gyp, gym):
        return None
    return (gxp - gxm) / (2 * d), (gyp - gym) / (2 * d)


def learn(db):
    """{'cultures': {culture: {'buildings', 'rocks', 'rate', 'ids': {id: n}, 'scale': {id: median scale}, 'near': {bin: [counts]}}},
    'bins': {bin: {'size', 'sink', 'tilt', 'top', 'h': [p10, p25, p50, p75, p90]}}, 'sides': {bin: {'back', 'beside', 'front'}},
    'dist': {bin: pcts}, 'top_vs_floor': {bin: pcts}, 'near_all': {bin: [counts]}, 'rate_all', 'boxes': {id: box}} (on disk)."""
    key = id(db.recs)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            _mem[key] = json.load(f)
            return _mem[key]
    except (OSError, ValueError):
        pass
    import townsurvey
    towns = townsurvey.survey(db)['towns']
    by_bin = defaultdict(list)
    sides = {k: Counter() for k in BINS}
    dist, tvf, near_all = defaultdict(list), defaultdict(list), defaultdict(list)
    cult = defaultdict(lambda: {'b': 0, 'r': 0, 'ids': Counter(), 'scales': defaultdict(list), 'near': defaultdict(list)})
    boxes = {}
    for t in towns:
        rocks = []
        for gx, gy in t['cells']:
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                if r['type'] != 'STAT' or not r.get('b') or not is_rock(r['id']):
                    continue
                b = r['b']
                s = r.get('s') or 1.0
                w, d, h = (b[3] - b[0]) * s, (b[4] - b[1]) * s, (b[5] - b[2]) * s
                if max(w, d) < MIN_ACROSS:
                    continue
                x, y, z = r['p'][0], r['p'][1], r['p'][2]
                g = mapdata.terrain_z(db, x, y)
                gr = _grad(db, x, y)
                if g is None or gr is None:
                    continue
                boxes.setdefault(r['id'].lower(), [round(v, 1) for v in b])
                rocks.append({'id': r['id'], 'x': x, 'y': y, 'size': max(w, d), 'h': h, 'top': z + b[5] * s, 'g': g,
                              'slope': math.hypot(*gr), 'sink': g - (z + b[2] * s), 's': s,
                              'tilt': math.degrees(min(abs(r['p'][3]) % (2 * math.pi), 2 * math.pi - abs(r['p'][3]) % (2 * math.pi),
                                                       abs(r['p'][4]) % (2 * math.pi), 2 * math.pi - abs(r['p'][4]) % (2 * math.pi)))})
        bl = t['buildings']
        relief = (max(b['z'] for b in bl) - min(b['z'] for b in bl)) if bl else 0
        hilly = relief >= MIN_RELIEF
        for rk in rocks:
            k = slope_bin(rk['slope'])
            by_bin[k].append(rk)
            if hilly:
                c = cult[t['culture']]
                c['ids'][rk['id'].lower()] += 1
                c['scales'][rk['id'].lower()].append(rk['s'])
        if hilly:
            cult[t['culture']]['b'] += len(bl)
            cult[t['culture']]['r'] += len(rocks)
        for bd in bl:
            ox, oy = math.sin(bd['face']), math.cos(bd['face'])          # (out of the door)
            box = bd.get('box') or [bd['x'] - 300, bd['y'] - 300, bd['x'] + 300, bd['y'] + 300]
            cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            half = max(box[2] - box[0], box[3] - box[1]) / 2.0
            gr = _grad(db, cx, cy, 256.0)
            if gr is None:
                continue
            k = slope_bin(math.hypot(*gr))
            n = 0
            for rk in rocks:
                dx, dy = rk['x'] - cx, rk['y'] - cy
                dd = max(0.0, math.hypot(dx, dy) - half - rk['size'] / 2.0)
                if dd > NEAR:
                    continue
                n += 1
                fwd = dx * ox + dy * oy
                sides[k]['front' if fwd > half * 0.5 else 'back' if fwd < -half * 0.5 else 'beside'] += 1
                dist[k].append(dd)
                tvf[k].append(rk['top'] - bd['z'])
            near_all[k].append(n)
            if hilly:
                cult[t['culture']]['near'][k].append(n)
    ncell = sum(len(t['cells']) for t in towns) or 1
    # (the land round the game's hill towns: its rocks a cell in the ring two cells out, the surroundings' yardstick)
    rings = []
    for t in towns:
        bl = t['buildings']
        if not bl or (max(b['z'] for b in bl) - min(b['z'] for b in bl)) < MIN_RELIEF:
            continue
        own = {tuple(c) for c in t['cells']}
        ring = {(gx + dx, gy + dy) for gx, gy in own for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)} - own
        n = 0
        for gx, gy in ring:
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                if r['type'] == 'STAT' and r.get('b') and is_rock(r['id']) and max(r['b'][3] - r['b'][0], r['b'][4] - r['b'][1]) * (r.get('s') or 1.0) >= MIN_ACROSS:
                    n += 1
        rings.append(n / float(len(ring) or 1))
    rings.sort()
    out = {'v': VERSION, 'towns': len(towns), 'rocks': sum(len(v) for v in by_bin.values()), 'boxes': boxes,
           'rocks_per_cell': round(sum(len(v) for v in by_bin.values()) / float(ncell), 2),
           'ring_per_cell': round(rings[len(rings) // 2], 2) if rings else 20.0,
           'bins': {}, 'sides': {}, 'dist': {}, 'top_vs_floor': {}, 'near_all': {}, 'cultures': {}}
    for k in BINS:
        R = by_bin[k]
        out['bins'][k] = {'n': len(R), 'size': _pcts([r['size'] for r in R]), 'h': _pcts([r['h'] for r in R]),
                          'sink': _pcts([r['sink'] for r in R if -200 < r['sink'] < 2500]), 'tilt': _pcts([r['tilt'] for r in R if r['tilt'] <= 60]),
                          'top': _pcts([r['top'] - r['g'] for r in R if -200 < r['top'] - r['g'] < 3000])}
        tot = float(sum(sides[k].values()) or 1)
        out['sides'][k] = {s: round(sides[k][s] / tot, 3) for s in ('back', 'beside', 'front')}
        out['dist'][k] = _pcts(dist[k])
        out['top_vs_floor'][k] = _pcts([v for v in tvf[k] if -1200 < v < 1500])
        out['near_all'][k] = sorted(min(20, n) for n in near_all[k])
    tb = sum(c['b'] for c in cult.values())
    out['rate_all'] = round(sum(c['r'] for c in cult.values()) / float(tb), 3) if tb else 5.0
    for name, c in cult.items():
        if not c['b'] or not name:
            continue
        out['cultures'][name] = {'buildings': c['b'], 'rocks': c['r'], 'rate': round(min(RATE_CAP, c['r'] / float(c['b'])), 3),
                                 'ids': dict(c['ids'].most_common(40)),
                                 'scale': {i: round(sorted(v)[len(v) // 2], 2) for i, v in c['scales'].items() if i in dict(c['ids'].most_common(40))},
                                 'near': {k: sorted(min(20, n) for n in v) for k, v in c['near'].items()}}
    _mem[key] = out
    try:
        tmp = '%s.%d.tmp' % (path, os.getpid())
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(out, f)
        os.replace(tmp, path)
    except OSError:
        pass
    return out


ROCK_FAMILY = re.compile(r'[_ ]*\d+[a-z]?$')
FORT_FRONT = 700.0             # (no rock this near a castle's gate or keep: the way up to it)
ROAD_HALF = 160.0              # (nor this near a road drawn on the land plan)


def rock_family(rid):
    """The set a rock model is of: its name less its number (terrain_rock_ac_12: terrain_rock_ac)."""
    return ROCK_FAMILY.sub('', (rid or '').lower())


def _one_family(db, ids, region):
    """The culture's rocks kept to one set: a culture's towns stand in many regions, each with its own rock, and a
    town drawn from them all stood 10 rocks of 6 sets, red sandstone beside ash rock beside mossy boulders (the
    Headland run, 2026-11-11). The set the land's own fitting region stands (landregion.rock_region: weather, the
    map, the ground's colour) first; else the culture's commonest."""
    fams = {}
    for i, n in ids.items():
        fams.setdefault(rock_family(i), {})[i] = n
    if len(fams) <= 1:
        return ids
    fit = set()
    try:
        import cliffrocks
        import landregion
        if region:
            R = cliffrocks.learn(db, landregion.rock_region(db, region.lower())) or {}
            for b in R.get('bands') or ():
                for it in b.get('items') or ():
                    fit.add(rock_family(it.get('id')))
    except Exception as e:
        print('rocks: the region\'s set:', e)
    best = max(fams.items(), key=lambda t: (t[0] in fit, sum(t[1].values()), t[0]))
    return best[1]


def figures(db, P, culture, region=''):
    """The culture's figures (its own, or a kin's when its hill towns stood too few rocks), with only the rocks this
    load order has: {'rate', 'ids': {id: n}, 'scale', 'near', 'factor', 'from'}."""
    seen = []
    name = culture
    C = None
    while name and name not in seen:
        seen.append(name)
        c = P['cultures'].get(name)
        if c and c['rocks'] >= FEW and any(db.resolve_id(i) is not None for i in c['ids']):
            C = c
            break
        name = KIN.get(name)
    if C is None:
        # (nothing of its own: the whole game's rocks, those this load order has)
        ids = Counter()
        scale = {}
        for c in P['cultures'].values():
            for i, n in c['ids'].items():
                ids[i] += n
                scale.setdefault(i, c['scale'].get(i, 1.0))
        C = {'rate': P['rate_all'], 'ids': dict(ids.most_common(60)), 'scale': scale, 'near': {}}
        name = ''
    import landregion
    # (a home region's rocks only at home: Narsis's red sandstone in a Hlaalu town elsewhere, HOME_ROCKS)
    ids = {i: n for i, n in C['ids'].items() if db.resolve_id(i) is not None and landregion.home_rock_ok(i, region)}
    ids = _one_family(db, ids, region)
    return {'rate': C['rate'], 'ids': ids, 'scale': C.get('scale') or {}, 'near': C.get('near') or {},
            'factor': max(0.25, min(3.0, C['rate'] / float(P['rate_all'] or 5.0))), 'from': name}


def surroundings(db, plan, P, cells=()):
    """How rocky the land round the town is against the game's towns: the game's rock pieces (256+ across, not the mod's
    own) a cell in the ring of cells round the town's, over the survey's rocks a town cell, as a factor on the rate,
    sqrt-damped and kept in SURROUND; the yardstick is the same ring round the game's own hill towns. (The user, 2026-11-08: Red Mountain's slopes stand far fewer rocks than a
    Mephalan gorge; the culture's rate alone would rock them alike.)"""
    own = set()
    for ck in cells:
        try:
            own.add(tuple(int(v) for v in ck.strip('#').split(',')))
        except ValueError:
            pass
    if not own:
        return 1.0, 0
    ring = {(gx + dx, gy + dy) for gx, gy in own for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)} - own
    n = 0
    for gx, gy in ring:
        for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
            if r['type'] != 'STAT' or not r.get('b') or not is_rock(r['id']) or r.get('mine'):
                continue
            b = r['b']
            s = r.get('s') or 1.0
            if max(b[3] - b[0], b[4] - b[1]) * s >= MIN_ACROSS:
                n += 1
    per = n / float(len(ring) or 1)
    typical = float(P.get('ring_per_cell') or P.get('rocks_per_cell') or 20.0)
    return max(SURROUND[0], min(SURROUND[1], math.sqrt(per / typical))) if typical else 1.0, n


# ------------------------------------------------------------------------------------------------- the rim and the pose
def rim(db, rid):
    """The bottom rim of a rock's mesh in its own coordinates: the vertices of its open edges (one face on them) in
    the lower half of the model, or, for a closed shell, the vertices in its lowest eighth; with its box. Read once a
    model (edges.rim). None when the mesh can't be read."""
    low = rid.lower()
    if low in _rims:
        return _rims[low]
    out = None
    try:
        import edges
        ri = db.resolve_id(rid)
        model = db.recs[ri][5] if ri is not None else None
        out = edges.rim(db, model) if model else None
    except Exception:
        out = None
    _rims[low] = out
    return out


def _matrix(rx, ry, rz):
    """The game's turn (Z then Y then X, each clockwise): seethrough._matrix."""
    import seethrough
    return seethrough._matrix(rx, ry, rz)


def to_world(pos, s, v, M=None):
    M = M or _matrix(pos[3], pos[4], pos[5])
    return [pos[k] + s * (M[k][0] * v[0] + M[k][1] * v[1] + M[k][2] * v[2]) for k in range(3)]


def check_burial(db, rid, pos, s, rm=None, memo=None, others=()):
    """How far the rock's rim shows: the most any rim point stands over the ground under it (negative: buried that
    deep everywhere), and the rim points read. A point inside one of `others` (rocks standing already: (x, y, z, rz,
    s, box)) is covered by it, as a rock on a rock is in the game. None when the mesh or the ground can't be read."""
    rm = rm or rim(db, rid)
    if not rm or not rm.get('pts'):
        return None
    M = _matrix(pos[3], pos[4], pos[5])
    worst = None
    n = 0
    for v in rm['pts']:
        w = to_world(pos, s, v, M)
        g = _ground(db, w[0], w[1], memo)
        if g is None:
            continue
        n += 1
        over = w[2] - g
        if over > -MARGIN and others and _in_others(w, others):
            over = -MARGIN
        if worst is None or over > worst:
            worst = over
    return None if not n else (worst, n)


def _in_others(w, others):
    for x, y, z, rz, s, b in others:
        dx, dy = w[0] - x, w[1] - y
        if abs(dx) > 1600 or abs(dy) > 1600:
            continue
        c, sn = math.cos(rz), math.sin(rz)
        lx, ly = c * dx - sn * dy, sn * dx + c * dy
        if b[0] * s * 0.9 <= lx <= b[3] * s * 0.9 and b[1] * s * 0.9 <= ly <= b[4] * s * 0.9 and z + b[2] * s <= w[2] <= z + b[5] * s * 0.85:
            return True
    return False


def _ground(db, x, y, memo=None):
    if memo is None:
        return mapdata.terrain_z(db, x, y)
    k = (round(x / 4.0), round(y / 4.0))
    if k not in memo:
        memo[k] = mapdata.terrain_z(db, x, y)
    return memo[k]


def pose(rng, b, s, x, y, gr, bin_, P, tilt_scale=1.0, align=0.5, along=False, sway=40.0, lean=0.0):
    """A rock's turn at a spot: its long axis down the slope (with chance `align`, within 30 degrees; else any way,
    the game's rocks lie nearly any way to their slope, cos p50 0.7), its top tipped the way the ground falls by the
    game's tilt for the slope's bin. (rx, ry, rz)."""
    w, d = (b[3] - b[0]) * s, (b[4] - b[1]) * s
    long_local = 0.0 if w >= d else math.pi / 2
    slope = math.hypot(*gr) if gr else 0.0
    if gr and slope > 0.03 and along:
        # (its long axis along the bank, across the fall: a bank's rocks shore it up the length of it)
        down = math.atan2(-gr[1], -gr[0])
        rz = (-(down + math.pi / 2 - long_local) + (rng.random() - 0.5) * math.radians(sway)) % (2 * math.pi)
    elif gr and slope > 0.03 and rng.random() < align:
        down = math.atan2(-gr[1], -gr[0])          # (the world angle of the way downhill)
        # (local +X points along the world angle -rz: rz = -(angle wanted for +X))
        rz = (-(down - long_local) + (rng.random() - 0.5) * math.radians(60)) % (2 * math.pi)
    else:
        rz = rng.random() * 2 * math.pi
    t = 0.0
    if gr and slope > 0.03:
        pct = (P['bins'].get(bin_) or {}).get('tilt') or [2, 4, 8, 14, 22]
        t = math.radians(min(28.0, max(0.0, _draw(rng, pct) * tilt_scale)))
        if lean:
            # (laid back against its bank: by this share of the slope's own angle at least, LEAN_MAX at most, as the
            # land's cliff pieces lean, rockface.LEAN_K; level on a slope of one in one its downhill rim stood a rock's
            # width in the air and it was dropped, 60 of a town's bank rocks, lab 2026-11-11)
            t = max(t, min(math.radians(LEAN_MAX), math.atan(slope) * lean))
        c, sn = math.cos(rz), math.sin(rz)
        dx, dy = -gr[0] / slope, -gr[1] / slope      # (the way downhill)
        lx, ly = dx * c - dy * sn, dx * sn + dy * c    # (in the rock's own frame: Pose.local)
        rx, ry = t * ly, -t * lx                      # (+rx tips the top toward local +Y, +ry toward local -X)
    else:
        rx = ry = 0.0
    return rx % (2 * math.pi), ry % (2 * math.pi), rz


def _draw(rng, pct, lo=0.1, hi=0.9, u=None):
    """A value drawn from a percentile sketch [p10, p25, p50, p75, p90] between the lo and hi marks (straight between;
    u: the mark itself, for two sketches drawn together)."""
    if not pct:
        return 0.0
    marks = [0.1, 0.25, 0.5, 0.75, 0.9]
    if u is None:
        u = lo + rng.random() * (hi - lo)
    for k in range(4):
        if u <= marks[k + 1]:
            f = (u - marks[k]) / (marks[k + 1] - marks[k])
            return pct[k] + (pct[k + 1] - pct[k]) * f
    return pct[-1]


# ------------------------------------------------------------------------------------------------- placing
class _Space:
    """Where no rock goes: the plots and their door ways, the door fronts, the streets and roads, the footpaths'
    treads, the wall's pieces, what stands there already; and the rocks laid so far."""

    def __init__(self, db, plan, W, new_refs, cells, outline=None):
        import townbuild
        import townplan
        self.db = db
        self.plan = plan
        self.outline = [tuple(p_) for p_ in (outline or plan.get('outline') or ())]
        self.pad = townbuild.REMOVE_PAD - 100          # (no rock further out than Remove the town reaches: one stood 1,625 out and stayed)
        self.rects = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
        self.ways = [[tuple(p_) for p_ in q['way']] for q in plan['plots'] if q.get('b') and q.get('way')]
        self.treads = townbuild._tread_guard(plan)
        self.roads = {tuple(r) for r in (plan.get('roads') or ())} | {tuple(r) for r in (plan.get('paint_extra') or ())}   # (paved patches)
        self.square = plan.get('square')
        self.wall = []
        self.outline_w = (W or {}).get('outline') or []
        for p_ in (W or {}).get('pieces') or ():
            cs = p_.get('corners')
            if cs and len(cs) >= 4:
                self.wall.append(townbuild._grown([tuple(c) for c in cs[:4]], 32.0))
        # (and the retaining walls along the streets' sheer sides, laid before the rocks: retain.py)
        for q_ in plan.get('_retain') or ():
            self.wall.append([tuple(c_) for c_ in q_])
        # door fronts: every door the town set (its buildings' front and back doors), a clear circle round each
        self.doors = []
        self.things = []
        for ck in cells:
            for r in mapdata.cellmap(db, ck).get('refs') or ():
                if r['k'] in new_refs:
                    if r['type'] == 'DOOR' and not re.search(r'trap|hatch|marker', r['id'], re.I):
                        self.doors.append((r['p'][0], r['p'][1]))
                    continue
                b = r.get('b')
                if not b or r['type'] in ('NPC_', 'CREA', 'LEVC'):
                    continue
                s = r.get('s') or 1.0
                size = max(b[3] - b[0], b[4] - b[1]) * s
                if 48 <= size <= 1600:
                    self.things.append((r['p'][0], r['p'][1], size / 2.0))
        # (another make's castle by the town: nothing in its yard, nothing before its gate or keep; and the roads drawn
        # on the land plan: a boulder stood on the ramp to a fort's gate, the Headland run 2026-11-11)
        self.forts = []
        self.lines = []
        try:
            for ft in townbuild._forts_for(db, self.outline or [], {}):
                self.forts.append(([tuple(q_[:2]) for q_ in ft['ring']], [tuple(b_) for b_ in ft.get('blocks') or ()]))
            land = getattr(getattr(db, 'project', None), 'land', None) or {}
            for L_ in (land.get('plan') or {}).get('layers') or ():
                if L_.get('kind') == 'road' and L_.get('on') is not False and len(L_.get('pts') or ()) >= 2:
                    self.lines.append([tuple(q_[:2]) for q_ in L_['pts']])
        except Exception as e:
            print('rocks: castles and roads:', e)
        self.rocks = []                            # (x, y, half size, loose)
        self.refused = Counter()                   # (why spots were refused, for the lab)
        self.PATCH = townplan.PATCH
        self._in_rect = townbuild._in_rect
        self._street_dist = townbuild._street_dist

    def free(self, x, y, half, loose=False, wall_ok=False, bank=False, cross=None):
        """May a rock of this half-size stand at (x, y)? loose: an outcrop's, which may lap its neighbours. bank: a
        bank's rock, which may stand in a street's paved patch, off the street itself."""
        why = self._why(x, y, half, loose, wall_ok, bank, cross)
        if why:
            self.refused[why] += 1
        return not why

    def _why(self, x, y, half, loose, wall_ok, bank=False, cross=None):
        r = half * 0.7
        # (a bank's rock lies along its bank, its long side along the street or the house wall at the bank's foot or
        # top: towards them it reaches its short side, cross. By its long side every spot on a bank 300 wide between a
        # street and a house was refused, 278 for the street and 160 for the plot in one town, lab 2026-11-11)
        cr = min(half, cross) if (bank and cross) else half
        if len(self.outline) >= 3 and not _inside_poly(self.outline, x, y) and _edge_dist(self.outline, x, y) > self.pad:
            return 'far'
        for ring, blocks in self.forts:
            if _inside_poly(ring, x, y) or _edge_dist(ring, x, y) < half * 0.5:
                return 'fort'
            for b_ in blocks:
                if math.hypot(x - b_[0], y - b_[1]) < (b_[2] if len(b_) > 2 else 0.0) + FORT_FRONT + half * BODY:
                    return 'fort'
        for ln in self.lines:
            for k_ in range(len(ln) - 1):
                if _seg_dist(ln[k_], ln[k_ + 1], x, y) < ROAD_HALF + half * BODY:
                    return 'road'
        for q in self.rects:
            if self._in_rect(q, x, y) or _rect_dist(q, x, y) < cr * 0.7 * 0.5:
                return 'plot'
        for q in self.ways:
            if self._in_rect(q, x, y) or _rect_dist(q, x, y) < r * 0.5:
                return 'way'
        for q in self.treads:
            if self._in_rect(q, x, y) or _rect_dist(q, x, y) < r * 0.6:
                return 'tread'
        if not wall_ok:
            for q in self.wall:
                if self._in_rect(q, x, y) or _rect_dist(q, x, y) < r * 0.6:
                    return 'wall'
        # (the rock's whole body off the door and off the street: a boulder stood in a door's way in the user's
        # Senchal, 2026-11-09; 6 of 231 rocks within 160 of a door and 27 lapping a street there before)
        for dx, dy in self.doors:
            if math.hypot(x - dx, y - dy) < DOOR_CLEAR + half * BODY:
                return 'door'
        sd = self._street_dist(self.plan, x, y)
        # (a paved patch is a square of 512: the bank beside a street lies in its street's patches, and every rock for
        # it was refused as on the road, the user's Senchal, 2026-11-11, "why did this get two rocks?". Where a street
        # runs by, its own edge is the rule; a patch with no street near, a gate's road or the square, stays clear)
        if (int(math.floor(x / self.PATCH)), int(math.floor(y / self.PATCH))) in self.roads and (not bank or sd is None or sd > ROAD_NEAR):
            return 'road'
        if sd is not None and sd < cr * BODY:
            return 'street'
        if self.square and math.hypot(x - self.square[0], y - self.square[1]) < self.square[2] + r:
            return 'square'
        for tx, ty, th in self.things:
            if math.hypot(x - tx, y - ty) < (th + half) * 0.7:
                return 'thing'
        for rx, ry, rh, rl in self.rocks:
            share = OVERLAP if (loose and rl) else SPREAD
            if math.hypot(x - rx, y - ry) < (rh + half) * share:
                return 'rock'
        return ''

    def take(self, x, y, half, loose=False):
        self.rocks.append((x, y, half, loose))


def _rect_dist(r, x, y):
    """How far a point stands outside a convex quad (0 inside)."""
    best = None
    for i in range(len(r)):
        (x1, y1), (x2, y2) = r[i], r[(i + 1) % len(r)]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        d = math.hypot(x - x1 - dx * t, y - y1 - dy * t)
        if best is None or d < best:
            best = d
    return best or 0.0


class _Picker:
    """The culture's rocks: one drawn by how often its towns stand it, with its box and natural scale."""

    def __init__(self, db, F, P):
        self.db = db
        self.ids = [(i, n) for i, n in F['ids'].items() if n > 0]
        self.tot = float(sum(n for _i, n in self.ids) or 1)
        self.boxes = P.get('boxes') or {}
        self.scale = F.get('scale') or {}
        self.memo = {}
        self.used = Counter()                  # (rocks laid by model)
        self.shun = None                       # (a model not to draw next: its copy stands at the spot)

    def box(self, rid):
        low = rid.lower()
        if low not in self.memo:
            b = self.boxes.get(low)
            if not b:
                ri = self.db.resolve_id(rid)
                b = mapdata.object_bounds(self.db, ri) if ri is not None else None
            self.memo[low] = b
        return self.memo[low]

    def _one(self, rng, pool):
        tot = sum(self.used.values())
        cap = max(TOP_SHARE, 1.5 / len(pool)) * (tot + 1)
        ok = [(i, n) for i, n in pool if i.lower() != self.shun and (tot < 8 or self.used[i.lower()] < cap)]
        pool = ok or pool
        u = rng.random() * float(sum(n for _i, n in pool))
        for i, n in pool:
            u -= n
            if u <= 0:
                return i
        return pool[-1][0]

    def pick(self, rng, size=None, tall=None, small=False, tries=5):
        """A rock id, its box and its scale: of `tries` drawn by use, the one whose shape (height over width) comes
        nearest the shape wanted (tall over size: the game stands taller rocks on steeper ground, h/size 0.53 on the
        flat and 0.78 on cliffs), scaled to about `size` across and `tall` high (the mean of the two, within SCALE);
        with `tall` alone, at least that high. small: the culture's smaller rocks (under 400 across naturally)."""
        if not self.ids:
            return None
        pool = self.ids
        if small:
            sm = [(i, n) for i, n in self.ids if (self.box(i) or [0] * 6) and max(self.box(i)[3] - self.box(i)[0], self.box(i)[4] - self.box(i)[1]) * self.scale.get(i, 1.0) < 400]
            pool = sm or self.ids
        best = None
        for _try in range(tries if (size and tall) else 8):
            rid = self._one(rng, pool)
            b = self.box(rid)
            if not b:
                continue
            nat = max(b[3] - b[0], b[4] - b[1]) or 1.0
            h = (b[5] - b[2]) or 1.0
            s0 = self.scale.get(rid, 1.0)
            if size and tall:
                s = math.sqrt((size / nat) * (tall / h))
                err = abs(math.log((h / nat) / (tall / size)))
            elif tall is not None:
                s = tall / h
                err = 0.0
            elif size is not None:
                s = size / nat
                err = 0.0
            else:
                s, err = s0, 0.0
            s = max(SCALE[0], min(SCALE[1], s))
            if tall is not None and not size and h * s < tall * 0.85:
                continue                           # (not tall enough at any scale it may take: another)
            if best is None or err < best[0]:
                best = (err, rid, b, round(s, 2))
            if not (size and tall):
                break
        self.shun = None
        return None if best is None else best[1:]

    def pick_big(self, rng, size):
        """A rock about `size` across from the culture's big pieces, by use, near its natural size."""
        pool = []
        for i, n in self.ids:
            b = self.box(i)
            if not b:
                continue
            nat = max(b[3] - b[0], b[4] - b[1]) or 1.0
            if size / 1.35 <= nat <= size * 1.35:
                pool.append((i, n))
        if not pool:
            return None
        rid = self._one(rng, pool)
        self.shun = None
        b = self.box(rid)
        nat = max(b[3] - b[0], b[4] - b[1]) or 1.0
        return rid, b, round(max(SCALE[0], min(SCALE[1], size / nat * (0.9 + rng.random() * 0.2))), 2)


def _finish(db, rid, b, s, x, y, z, rot, memo, out, kind, drops, others=()):
    """The rock at its pose sunk until its rim is buried everywhere (within SINK_SHARE of its height, still TOP_MIN
    over the ground), else dropped. Appends to out; returns True when placed."""
    g = _ground(db, x, y, memo)
    if g is None:
        drops['noground'] += 1
        return False
    h = (b[5] - b[2]) * s
    pos = [x, y, z, rot[0], rot[1], rot[2]]
    res = check_burial(db, rid, pos, s, memo=memo, others=others)
    if res is None:
        # (a mesh that can't be read: the box's bottom corners stand in for its rim)
        rm = {'pts': [(cx, cy, b[2]) for cx in (b[0], b[3]) for cy in (b[1], b[4])]}
        res = check_burial(db, rid, pos, s, rm=rm, memo=memo, others=others)
        if res is None:
            drops['noground'] += 1
            return False
    over = res[0]
    if over > -MARGIN:
        pos[2] -= over + MARGIN
        res2 = check_burial(db, rid, pos, s, memo=memo, others=others)
        if res2 is None or res2[0] > -MARGIN * 0.5:
            pos[2] -= MARGIN                       # (the ground falls steeply between the samples: once more)
    sunk = g - (pos[2] + b[2] * s)
    top = pos[2] + b[5] * s - g
    if sunk > SINK_SHARE * h or top < TOP_MIN:
        drops['buried'] += 1
        return False
    out.append({'id': rid, 'x': round(pos[0], 1), 'y': round(pos[1], 1), 'z': round(pos[2], 1), 'rx': round(pos[3], 4), 'ry': round(pos[4], 4),
                'rz': round(pos[5], 4), 's': s, 'kind': kind, 'sunk': round(sunk), 'top': round(top), 'size': round(max(b[3] - b[0], b[4] - b[1]) * s)})
    return True


def _sample_count(rng, F, P, bin_, scale=1.0):
    """How many rocks a building of this slope bin gets: drawn from the culture's own counts where it has them (20 or
    more buildings in the bin), else from every culture's scaled by the culture's rate factor; times scale (the
    surroundings' factor)."""
    own = F['near'].get(bin_) or []
    if len(own) >= 20:
        n = own[rng.randrange(len(own))] * scale
    else:
        alls = P['near_all'].get(bin_) or [1]
        n = alls[rng.randrange(len(alls))] * F['factor'] * scale
    return int(n) + (1 if rng.random() < n - int(n) else 0)


def blend(db, plan, culture, seed=1, W=None, new_refs=(), cells=(), amount=1.0, outline=None):
    """The town's rocks laid (see the module's head): {'placed': n, 'dropped': n, 'kinds': {kind: n}, 'rocks': [...],
    'factor', 'from'}. Nothing is placed when the survey is not to hand (ready)."""
    import townbuild
    P = ready(db)
    if P is None:
        return {'placed': 0, 'dropped': 0, 'kinds': {}, 'rocks': [], 'factor': 0, 'from': ''}
    region = ''
    try:
        import landrange
        c0 = sorted(cells)[0] if cells else None
        if c0 is not None:
            gx, gy = (c0 if isinstance(c0, tuple) else tuple(int(v) for v in str(c0).strip('#').split(',')))
            region = landrange._region_of(db, gx, gy) or ''
    except Exception:
        region = ''
    F = figures(db, P, culture, region)
    if not F['ids']:
        return {'placed': 0, 'dropped': 0, 'kinds': {}, 'rocks': [], 'factor': F['factor'], 'from': F['from']}
    rng = random.Random(seed * 104729 + 7)
    S = _Space(db, plan, W, set(new_refs), cells, outline)
    K = _Picker(db, F, P)
    memo = {}
    out = []
    drops = Counter()
    sf, n_round = surroundings(db, plan, P, cells)
    f = F['factor'] * sf * amount
    kinds = Counter()

    boxes = []                                 # (the rocks standing so far, for the rim rule's cover)
    laid_ = []                                 # (... with their models: x, y, half, id, turn, scale)

    def copy_(low, x, y, half, rz, s):
        for x2, y2, h2, id2, rz2, s2 in laid_:
            if id2 == low and math.hypot(x - x2, y - y2) < half + h2 + 100                     and abs((rz - rz2 + math.pi) % (2 * math.pi) - math.pi) < CLONE_TURN and 1 / CLONE_SCALE < s / s2 < CLONE_SCALE:
                return True
        return False

    def put(rid, b, s, x, y, z, rot, kind, loose=False):
        half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
        low = rid.lower()
        if copy_(low, x, y, half, rot[2], s):
            # (end for end: its long axis lies as it did, its tilt the same way in the world)
            rot = ((-rot[0]) % (2 * math.pi), (-rot[1]) % (2 * math.pi), (rot[2] + math.pi) % (2 * math.pi))
            if copy_(low, x, y, half, rot[2], s):
                K.shun = low
                drops['copy'] += 1
                return False
        if _finish(db, rid, b, s, x, y, z, rot, memo, out, kind, drops, others=boxes if loose else ()):
            S.take(x, y, half, loose)
            kinds[kind] += 1
            r_ = out[-1]
            boxes.append((r_['x'], r_['y'], r_['z'], r_['rz'], s, b))
            laid_.append((r_['x'], r_['y'], half, low, r_['rz'], s))
            K.used[low] += 1
            return True
        return False

    # 1. round each building: its rocks by the game's count for its slope, on the game's sides, at the game's distance
    for q in plan['plots']:
        if not q.get('b') or not q.get('rect') or q.get('door_z') is None:
            continue
        rect = [tuple(p_) for p_ in q['rect']]
        cx, cy = sum(p_[0] for p_ in rect) / 4.0, sum(p_[1] for p_ in rect) / 4.0
        c, sn, _yaw = townbuild._frame(q['face'])
        ox, oy = townbuild._world(0.0, 0.0, c, sn, 0.0, -1.0)              # (out of the door, from the frame's origin)
        sx, sy = townbuild._world(0.0, 0.0, c, sn, 1.0, 0.0)
        # (the plot's reach along the out and side axes)
        ho = max(abs((p_[0] - cx) * ox + (p_[1] - cy) * oy) for p_ in rect)
        hs = max(abs((p_[0] - cx) * sx + (p_[1] - cy) * sy) for p_ in rect)
        gr = _grad(db, cx, cy, 256.0)
        if gr is None:
            continue
        bslope = math.hypot(*gr)
        bin_ = slope_bin(bslope)
        n = _sample_count(rng, F, P, bin_, sf * amount * OVERSAMPLE)
        shares = P['sides'].get(bin_) or {'back': 0.5, 'beside': 0.2, 'front': 0.3}
        for _k in range(n):
            u = rng.random()
            side = 'back' if u < shares['back'] else 'beside' if u < shares['back'] + shares['beside'] else 'front'
            placed = False
            taller = 1.0
            for _try in range(8):
                u = 0.1 + rng.random() * 0.75
                size = _draw(rng, P['bins'][bin_]['size'] or [300, 400, 520, 700, 1200], u=u)
                tall = _draw(rng, P['bins'][bin_]['h'] or [150, 190, 300, 540, 1000], u=min(0.9, u + 0.1)) * taller
                pk = K.pick(rng, size=size, tall=tall)
                if not pk:
                    break
                rid, b, s = pk
                half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
                dd = _draw(rng, P['dist'].get(bin_) or [10, 60, 150, 300, 500], 0.1, 0.8)
                dd = min(320.0, dd) + half
                along = (rng.random() * 2 - 1)
                if side == 'back':
                    x, y = cx - ox * (ho + dd) + sx * along * hs, cy - oy * (ho + dd) + sy * along * hs
                elif side == 'front':
                    # (in front, off the door's way: at the plot's front corners, out to the side of it; or across the
                    # street, where most of the game's "front" rocks stand)
                    along = math.copysign(1.0, along)
                    if _try % 2 == 0:
                        x, y = (cx + ox * (ho * (0.55 + 0.45 * rng.random()) + dd * 0.3) + sx * along * (hs + dd * 0.7),
                                cy + oy * (ho * (0.55 + 0.45 * rng.random()) + dd * 0.3) + sy * along * (hs + dd * 0.7))
                    else:
                        far = ho + dd + 480 + rng.random() * 200
                        x, y = cx + ox * far + sx * along * hs * rng.random(), cy + oy * far + sy * along * hs * rng.random()
                else:
                    sg = 1 if rng.random() < 0.5 else -1
                    x, y = cx + sx * sg * (hs + dd) + ox * along * ho, cy + sy * sg * (hs + dd) + oy * along * ho
                if not S.free(x, y, half):
                    continue
                g = _ground(db, x, y, memo)
                gr2 = _grad(db, x, y)
                if g is None or g < 0 or gr2 is None:
                    continue
                kb = slope_bin(math.hypot(*gr2))
                rot = pose(rng, b, s, x, y, gr2, kb, P, align=ALIGN)
                sink = _draw(rng, P['bins'][kb]['sink'] or [20, 50, 100, 200, 400], 0.25, 0.75)
                z = g - sink - b[2] * s
                if put(rid, b, s, x, y, z, rot, side):
                    placed = True
                    break
                taller *= 1.3                      # (its rim would not bury on this bank: a taller rock next)
            if not placed:
                drops['nospot'] += 1
        # 2. under the downhill edge of a floor standing over the land: a rock whose top meets the floor
        fz = q['door_z']
        edges_ = []
        for i in range(4):
            (x1, y1), (x2, y2) = rect[i], rect[(i + 1) % 4]
            for t in (0.25, 0.5, 0.75):
                edges_.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
        rng.shuffle(edges_)
        under = 0
        if rng.random() > FLOOR_P * min(1.5, f):
            edges_ = []
        for ex, ey in edges_:
            if under >= 1:
                break
            g = _ground(db, ex, ey, memo)
            if g is None or fz - g < FLOOR_OVER:
                continue
            # (the edge's outward way: from the plot's middle)
            L = math.hypot(ex - cx, ey - cy) or 1.0
            nx, ny = (ex - cx) / L, (ey - cy) / L
            fwd = nx * ox + ny * oy
            if fwd > 0.7:
                continue                           # (never the door's edge)
            for _try in range(4):
                gap = FLOOR_GAP[0] + rng.random() * (FLOOR_GAP[1] - FLOOR_GAP[0])
                want_top = fz - gap
                pk = K.pick(rng, tall=(want_top - g) + 48 + rng.random() * 120)
                if not pk:
                    break
                rid, b, s = pk
                half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
                x, y = ex + nx * half * 0.55, ey + ny * half * 0.55
                if not S.free(x, y, half):
                    continue
                gr2 = _grad(db, x, y) or (0.0, 0.0)
                rot = pose(rng, b, s, x, y, gr2, slope_bin(math.hypot(*gr2)), P, tilt_scale=0.3)
                z = want_top - b[5] * s
                if put(rid, b, s, x, y, z, rot, 'floor'):
                    under += 1
                    break
    # 3. along the footpaths' and stair streets' cut banks
    lines = [(p_['pts'], p_['w'] / 2.0) for p_ in plan.get('paths') or () if p_.get('pts')]
    lines += [(st['pts'], (st.get('w') or 512) / 2.0) for st in plan.get('streets') or () if st.get('stair') and st.get('pts')]
    for pts, hw in lines:
        run = rng.random() * PATH_EVERY
        for k in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            L = math.hypot(bx - ax, by - ay)
            if L < 1:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            while run < L:
                x0, y0 = ax + ux * run, ay + uy * run
                run += PATH_EVERY * (0.7 + rng.random() * 0.6)
                if rng.random() > PATH_P * min(1.5, f):
                    continue
                g0 = _ground(db, x0, y0, memo)
                if g0 is None:
                    continue
                # (the uphill side: the higher ground a bank's width off the tread)
                gl = _ground(db, x0 - uy * (hw + 160), y0 + ux * (hw + 160), memo)
                gr_ = _ground(db, x0 + uy * (hw + 160), y0 - ux * (hw + 160), memo)
                if gl is None or gr_ is None:
                    continue
                sg = 1.0 if gl >= gr_ else -1.0
                if max(gl, gr_) - g0 < BANK:
                    continue                       # (no bank here: the tread lies at the land)
                for _try in range(3):
                    u = 0.1 + rng.random() * 0.6
                    pk = K.pick(rng, size=_draw(rng, P['bins']['gentle']['size'] or [280, 350, 450, 600, 900], u=u),
                                tall=_draw(rng, P['bins']['steep']['h'] or [150, 190, 310, 550, 1040], u=u))
                    if not pk:
                        break
                    rid, b, s = pk
                    half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
                    x, y = x0 - sg * uy * (hw + 48 + half * 0.6), y0 + sg * ux * (hw + 48 + half * 0.6)
                    if not S.free(x, y, half):
                        continue
                    g = _ground(db, x, y, memo)
                    gr2 = _grad(db, x, y)
                    if g is None or gr2 is None:
                        continue
                    kb = slope_bin(math.hypot(*gr2))
                    rot = pose(rng, b, s, x, y, gr2, kb, P, align=ALIGN + 0.2)
                    sink = _draw(rng, P['bins'][kb]['sink'] or [20, 50, 100, 200, 400], 0.3, 0.8)
                    if put(rid, b, s, x, y, g - sink - b[2] * s, rot, 'path'):
                        break
    # 4. the wall: its towers' outer feet, and the bank filled under it
    if W and W.get('outline'):
        import townwalls
        outline = [tuple(p_) for p_ in W['outline']]
        cxw = sum(p_[0] for p_ in outline) / len(outline)
        cyw = sum(p_[1] for p_ in outline) / len(outline)
        gates = [(p_['pose'].x, p_['pose'].y) for p_ in W.get('pieces') or () if p_.get('kind') in ('gate', 'end')]
        for p_ in W.get('pieces') or ():
            if p_.get('kind') not in ('tower', 'corner', 'bigtower', 'keep') or rng.random() > TOWER_P * min(1.5, f):
                continue
            cs = p_.get('corners')
            if not cs:
                continue
            mx, my = sum(c_[0] for c_ in cs) / float(len(cs)), sum(c_[1] for c_ in cs) / float(len(cs))
            half_t = max(math.hypot(c_[0] - mx, c_[1] - my) for c_ in cs)
            L = math.hypot(mx - cxw, my - cyw) or 1.0
            nx, ny = (mx - cxw) / L, (my - cyw) / L
            for _try in range(4):
                a = math.atan2(ny, nx) + (rng.random() - 0.5) * math.radians(110)
                u = 0.1 + rng.random() * 0.7
                pk = K.pick(rng, size=_draw(rng, P['bins']['gentle']['size'] or [280, 350, 450, 600, 900], u=u),
                            tall=_draw(rng, P['bins']['gentle']['h'] or [150, 190, 300, 540, 1000], u=u))
                if not pk:
                    break
                rid, b, s = pk
                half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
                dd = half_t + half * 0.8 + 40 + rng.random() * 160
                x, y = mx + math.cos(a) * dd, my + math.sin(a) * dd
                if townwalls._inside(outline, (x, y)) or not S.free(x, y, half) or any(math.hypot(x - gx, y - gy) < 500 for gx, gy in gates):
                    continue
                g = _ground(db, x, y, memo)
                gr2 = _grad(db, x, y)
                if g is None or gr2 is None:
                    continue
                kb = slope_bin(math.hypot(*gr2))
                rot = pose(rng, b, s, x, y, gr2, kb, P)
                sink = _draw(rng, P['bins'][kb]['sink'] or [20, 50, 100, 200, 400], 0.3, 0.8)
                if put(rid, b, s, x, y, g - sink - b[2] * s, rot, 'tower'):
                    break
        for a_, b_, zf in W.get('_fill_lines') or ():
            if zf is None or zf < -1e8:
                continue                           # (a cliff piece's hold line: no bank raised there)
            L = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
            if L < 64:
                continue
            ux, uy = (b_[0] - a_[0]) / L, (b_[1] - a_[1]) / L
            mx, my = (a_[0] + b_[0]) / 2.0, (a_[1] + b_[1]) / 2.0
            nx, ny = -uy, ux
            if (mx - cxw) * nx + (my - cyw) * ny < 0:
                nx, ny = -nx, -ny                  # (outward)
            if rng.random() > WALL_P * min(1.5, f) * min(1.0, L / WALL_EVERY):
                continue
            g_in = _ground(db, mx + nx * 96, my + ny * 96, memo)
            g_out = _ground(db, mx + nx * 420, my + ny * 420, memo)
            if g_in is None or g_out is None or g_in - g_out < 96:
                continue                           # (no bank outside: the wall's foot meets the land)
            for _try in range(3):
                u = 0.1 + rng.random() * 0.7
                pk = K.pick(rng, size=_draw(rng, P['bins']['steep']['size'] or [300, 400, 520, 700, 1200], u=u),
                            tall=_draw(rng, P['bins']['steep']['h'] or [150, 190, 310, 550, 1040], u=u))
                if not pk:
                    break
                rid, b, s = pk
                half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
                t = (rng.random() - 0.5) * L * 0.8
                dd = 150 + half * 0.6 + rng.random() * 160
                x, y = mx + ux * t + nx * dd, my + uy * t + ny * dd
                if townwalls._inside(outline, (x, y)) or not S.free(x, y, half) or any(math.hypot(x - gx, y - gy) < 600 for gx, gy in gates):
                    continue
                g = _ground(db, x, y, memo)
                gr2 = _grad(db, x, y)
                if g is None or gr2 is None:
                    continue
                kb = slope_bin(math.hypot(*gr2))
                rot = pose(rng, b, s, x, y, gr2, kb, P, align=ALIGN + 0.2)
                sink = _draw(rng, P['bins'][kb]['sink'] or [20, 50, 100, 200, 400], 0.3, 0.8)
                if put(rid, b, s, x, y, g - sink - b[2] * s, rot, 'wall'):
                    break
    # 5. the crown: a knoll in the town's ground gets its outcrop
    kn = knoll(db, outline or plan.get('outline') or [], memo)
    if kn:
        kx, ky, relief = kn
        n_big = int(round(CROWN_N * min(1.3, relief / CROWN_RELIEF) * min(1.5, f)))
        n_big = max(5, min(28, n_big))
        got = []
        why = Counter()
        gtop = _ground(db, kx, ky, memo) or 0
        for _try in range(n_big * 8):
            if len(got) >= n_big:
                break
            r = CROWN_R * (rng.random() ** 0.8)
            a = rng.random() * 2 * math.pi
            x, y = kx + math.cos(a) * r, ky + math.sin(a) * r
            g = _ground(db, x, y, memo)
            if g is None or g < 0 or g < gtop - relief * 0.75:
                why['low'] += 1
                continue
            u = 0.1 + rng.random() * 0.8
            pk = K.pick(rng, size=_draw(rng, CROWN_SIZE, u=u), tall=_draw(rng, CROWN_H, u=u))
            if not pk:
                break
            rid, b, s = pk
            half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
            if not S.free(x, y, half, loose=True):
                why['refused'] += 1
                continue
            gr2 = _grad(db, x, y) or (0.0, 0.0)
            kb = slope_bin(math.hypot(*gr2))
            rot = pose(rng, b, s, x, y, gr2, kb, P, align=ALIGN)
            sink = _draw(rng, CROWN_SINK, 0.15, 0.85)
            if put(rid, b, s, x, y, g - sink - b[2] * s, rot, 'crown', loose=True):
                got.append((x, y, half))
            else:
                why['buried'] += 1
        if os.environ.get('TOWN_ROCK_DEBUG'):
            print('  crown: %d of %d big rocks round %d,%d (relief %d): %s' % (len(got), n_big, kx, ky, relief, dict(why)))
        # (small rocks at the big rocks' feet, downhill of them)
        for x0, y0, h0 in got:
            if rng.random() > 0.3:
                continue
            gr0 = _grad(db, x0, y0)
            if not gr0 or math.hypot(*gr0) < 0.03:
                a = rng.random() * 2 * math.pi
            else:
                a = math.atan2(-gr0[1], -gr0[0]) + (rng.random() - 0.5) * 1.2
            pk = K.pick(rng, size=_draw(rng, [160, 200, 260, 330, 400], 0.1, 0.9), small=True)
            if not pk:
                break
            rid, b, s = pk
            half = max(b[3] - b[0], b[4] - b[1]) * s / 2.0
            x, y = x0 + math.cos(a) * (h0 + half * 0.5 + 20), y0 + math.sin(a) * (h0 + half * 0.5 + 20)
            if not S.free(x, y, half, loose=True):
                continue
            g = _ground(db, x, y, memo)
            gr2 = _grad(db, x, y)
            if g is None or gr2 is None:
                continue
            rot = pose(rng, b, s, x, y, gr2, slope_bin(math.hypot(*gr2)), P)
            put(rid, b, s, x, y, g - _draw(rng, [20, 40, 70, 110, 160], 0.1, 0.9) - b[2] * s, rot, 'foot', loose=True)
    # 6. the banks left bare: the steep ground the passes above left showing, the streets' shoulders first (the user,
    # 2026-11-08: "use stones etc to reinforce the sides of raised street profiles like this, as you might need to in
    # real life to shore up similar landscaping"; ours covered 24-38% of their steep ground before this pass)
    bank = _banks(db, plan, S, K, P, rng, memo, put, boxes, outline or plan.get('outline') or [], amount)
    try:
        bank['stones'] = _stones(db, plan, S, K, P, rng, memo, put, outline or plan.get('outline') or [], amount)
    except Exception as e:
        print('rocks, stones:', e)
    if os.environ.get('TOWN_ROCK_DEBUG'):
        print('  rocks: refused spots %s; drops %s; banks %s' % (dict(S.refused), dict(drops), bank))
    return {'placed': len(out), 'dropped': drops['buried'], 'drops': dict(drops), 'kinds': dict(kinds), 'rocks': out, 'refused': dict(S.refused),
            'factor': round(f / max(1e-6, amount), 2), 'culture_factor': round(F['factor'], 2), 'surround': round(sf, 2), 'round': n_round,
            'from': F['from'], 'knoll': kn, 'banks': bank}


def _stones(db, plan, S, K, P, rng, memo, put, outline, amount=1.0):
    """Clumps of the town's rock on its gentle open ground by the streets, for the look of it: a big rock and one to
    three smaller lapping it, sunk as the game sinks its rocks, STONE_HOUSE from the houses, off the streets and the
    door ways. STONE_CLUMPS a building, times the town's own amount. What the user set by hand in a made town
    (2026-11-13: "Same with decorative stones"). {'clumps', 'stones', 'spots'}."""
    import townbuild
    built = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    want = int(len(built) * STONE_CLUMPS * max(0.0, min(2.0, amount)) + rng.random())
    if want <= 0 or len(outline) < 3:
        return {'clumps': 0, 'stones': 0, 'spots': 0}
    outline = [tuple(p_[:2]) for p_ in outline]
    xs, ys = [p_[0] for p_ in outline], [p_[1] for p_ in outline]
    cand = []
    for i in range(int(math.floor(min(xs) / 128.0)), int(math.ceil(max(xs) / 128.0)) + 1):
        for j in range(int(math.floor(min(ys) / 128.0)), int(math.ceil(max(ys) / 128.0)) + 1):
            x, y = i * 128.0, j * 128.0
            if not _inside_poly(outline, x, y) or _edge_dist(outline, x, y) < 192.0:
                continue
            sd = townbuild._street_dist(plan, x, y)
            if sd is None or sd > STONE_STREET:
                continue
            g = _ground(db, x, y, memo)
            gr = _grad(db, x, y)
            if g is None or g < 16 or gr is None or math.hypot(*gr) > STONE_SLOPE:
                continue
            if any(townbuild._in_rect(q, x, y) or _rect_dist(q, x, y) < STONE_HOUSE for q in built):
                continue
            if S._why(x, y, 260.0, True, False, True):
                continue
            cand.append((x, y))
    rng.shuffle(cand)
    centres, laid = [], 0
    why = Counter()
    for x, y in cand:
        if len(centres) >= want:
            break
        if any(math.hypot(x - cx, y - cy) < STONE_APART for cx, cy in centres):
            continue
        size = rng.uniform(*STONE_SIZE)
        members = [(0.0, size)] + [(1.0, size * rng.uniform(0.4, 0.7)) for _k in range(rng.randint(1, 3))]
        got = 0
        for far, sz in members:
            for _try in range(6 if far else 4):
                # (a smaller rock on whichever side of the big one has room: a fresh side each try)
                a_ = rng.random() * 2 * math.pi
                d_ = far * (size + sz) / 2.0 * rng.uniform(0.55, 0.85)
                px, py = x + math.cos(a_) * d_, y + math.sin(a_) * d_
                pk = K.pick(rng, size=sz, tall=sz * rng.uniform(0.5, 0.85) * (1.3 ** _try))
                if not pk:
                    why['no rock that size'] += 1
                    break
                rid, b, sc = pk
                half = max(b[3] - b[0], b[4] - b[1]) * sc / 2.0
                w_ = S._why(px, py, half, True, False, True)
                if w_:
                    why[w_] += 1
                    if far:
                        continue
                    break
                g = _ground(db, px, py, memo)
                gr2 = _grad(db, px, py)
                if g is None or g < 0 or gr2 is None or math.hypot(*gr2) > 2 * STONE_SLOPE:
                    why['ground'] += 1
                    if far:
                        continue
                    break
                kb = slope_bin(math.hypot(*gr2))
                rot = pose(rng, b, sc, px, py, gr2, kb, P, align=ALIGN)
                sink = _draw(rng, P['bins'][kb]['sink'] or [20, 50, 100, 200, 400], 0.25, 0.75)
                if put(rid, b, sc, px, py, g - sink - b[2] * sc, rot, 'stone', loose=True):
                    got += 1
                    break
                why['rim shows'] += 1
            if not got:
                break                              # (no big rock, no clump)
        if got:
            centres.append((x, y))
            laid += got
    return {'clumps': len(centres), 'stones': laid, 'spots': len(cand), 'refused': dict(why)}


def _banks(db, plan, S, K, P, rng, memo, put, boxes, outline, amount=1.0):
    """The town's bare banks shored up with rocks: every land vertex within BANK_REACH of a building or a street,
    inside the town's reach, whose steepest facet is BANK_STEEP or more and which nothing covers (a building's plot,
    the wall, a thing standing there, a rock laid); the streets' shoulders first, then the highest banks; each rock
    sized to its bank's rise, laid along it, sunk until its rim is buried, the vertices under it covered; until
    BANK_COVER of the steep vertices are covered (times amount) or BANK_MAX rocks. {'steep', 'covered_before',
    'covered_after', 'laid', 'tried'}."""
    import townbuild
    cen = []
    for q in plan.get('plots') or ():
        if q.get('b') and q.get('rect'):
            cen.append((sum(p_[0] for p_ in q['rect']) / 4.0, sum(p_[1] for p_ in q['rect']) / 4.0))
    for st in plan.get('streets') or ():
        pts = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            for k in range(int(L // 600) + 1):
                t = k * 600.0 / L if L else 0.0
                cen.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    if not cen:
        return {}
    H = {}

    def vz(i, j):
        if (i, j) not in H:
            H[(i, j)] = _ground(db, i * 128.0, j * 128.0, memo)
        return H[(i, j)]

    rr = int(BANK_REACH // 128) + 1
    verts = set()
    for cx, cy in cen:
        ci, cj = int(round(cx / 128.0)), int(round(cy / 128.0))
        for i in range(ci - rr, ci + rr + 1):
            for j in range(cj - rr, cj + rr + 1):
                if (i * 128.0 - cx) ** 2 + (j * 128.0 - cy) ** 2 <= BANK_REACH * BANK_REACH:
                    verts.add((i, j))
    steep = {}
    for i, j in verts:
        z = vz(i, j)
        if z is None or z < 0:
            continue
        worst = 0.0
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            z2 = vz(i + di, j + dj)
            if z2 is not None:
                worst = max(worst, abs(z2 - z) / 128.0)
        if worst < BANK_STEEP:
            continue
        x, y = i * 128.0, j * 128.0
        if len(S.outline) >= 3 and not _inside_poly(S.outline, x, y) and _edge_dist(S.outline, x, y) > S.pad:
            continue
        steep[(i, j)] = worst
    if not steep:
        return {'steep': 0}

    def under(x, y):
        for q in S.rects:
            if S._in_rect(q, x, y):
                return True
        for q in S.wall:
            if S._in_rect(q, x, y):
                return True
        for tx, ty, th in S.things:
            if math.hypot(x - tx, y - ty) < th * 0.8:
                return True
        return False

    def footprint(x, y, rz, s_, b):
        """The lattice vertices under a rock's box (0.9 of it)."""
        c, sn = math.cos(rz), math.sin(rz)
        R = max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) * s_
        got = []
        for i in range(int(math.floor((x - R) / 128.0)), int(math.ceil((x + R) / 128.0)) + 1):
            for j in range(int(math.floor((y - R) / 128.0)), int(math.ceil((y + R) / 128.0)) + 1):
                dx, dy = i * 128.0 - x, j * 128.0 - y
                lx, ly = (dx * c - dy * sn) / s_, (dx * sn + dy * c) / s_
                if b[0] * 0.9 <= lx <= b[3] * 0.9 and b[1] * 0.9 <= ly <= b[4] * 0.9:
                    got.append((i, j))
        return got

    covered = {v for v in steep if under(v[0] * 128.0, v[1] * 128.0)}
    for x_, y_, _z, rz_, s_, b_ in boxes:
        covered.update(v for v in footprint(x_, y_, rz_, s_, b_) if v in steep)
    before = len(covered) / float(len(steep))
    # (down to nothing with the amount: it was held at 0.3 of the cover at least, and a town asked for a tenth of its
    # rocks still shored a quarter of its banks)
    target = min(0.95, BANK_COVER * max(0.0, min(1.15, amount)))
    # (a vertex on a street, a road patch, the square or a footpath's tread is the walk itself: never a bank's rock)
    order = []
    skip = Counter()
    ref0 = Counter(S.refused)
    for (i, j), worst in steep.items():
        if (i, j) in covered:
            continue
        x, y = i * 128.0, j * 128.0
        sd = S._street_dist(plan, x, y)
        if sd is not None and sd <= 0:
            skip['street'] += 1
            continue
        if (int(math.floor(x / S.PATCH)), int(math.floor(y / S.PATCH))) in S.roads and (sd is None or sd > ROAD_NEAR):
            skip['road'] += 1
            continue
        lo = min(v for v in (vz(i + 2, j), vz(i - 2, j), vz(i, j + 2), vz(i, j - 2), vz(i, j)) if v is not None)
        hi = max(v for v in (vz(i + 2, j), vz(i - 2, j), vz(i, j + 2), vz(i, j - 2), vz(i, j)) if v is not None)
        shoulder = sd is not None and sd < BANK_SHOULDER
        order.append((0 if shoulder else 1, -(hi - lo), rng.random(), i, j, hi - lo, sd))
    order.sort()
    laid = tried = 0
    # (masses first: a big bare bank takes one big rock, the small ones fill in after)
    masses = 0
    left = {(o[3], o[4]) for o in order}
    discs = {sz: [(di, dj) for di in range(-int(sz * 0.5 // 128), int(sz * 0.5 // 128) + 1) for dj in range(-int(sz * 0.5 // 128), int(sz * 0.5 // 128) + 1)
                  if di * di + dj * dj <= int(sz * 0.5 // 128) ** 2] for sz in MASS_SIZES}
    dead = set()
    mwhy = Counter()
    while len(left) >= MASS_MIN and laid < BANK_MAX and len(covered) < target * len(steep):
        done = False
        for size in MASS_SIZES:
            disc = discs[size]
            cand = []
            for (i, j) in left:
                if (size, i, j) in dead:
                    continue
                n_ = sum(1 for di, dj in disc if (i + di, j + dj) in left)
                if n_ >= MASS_MIN:
                    cand.append((-n_, i, j))
            cand.sort()
            for _n, i, j in cand[:MASS_TRIES]:
                near = [(i + di, j + dj) for di, dj in disc if (i + di, j + dj) in left]
                x0 = sum(v[0] for v in near) * 128.0 / len(near)
                y0 = sum(v[1] for v in near) * 128.0 / len(near)
                pk = K.pick_big(rng, size)
                if not pk:
                    break
                rid, b, s_ = pk
                half = max(b[3] - b[0], b[4] - b[1]) * s_ / 2.0
                why = ''
                for ox, oy in MASS_OFFS:           # (the middle of the bare ground first, then a little off it: out of a yard, off a street)
                    x, y = x0 + ox * half, y0 + oy * half
                    if (ox or oy) and sum(1 for di, dj in disc if (int(round(x / 128.0)) + di, int(round(y / 128.0)) + dj) in left) < MASS_MIN:
                        continue
                    sd2 = S._street_dist(plan, x, y)
                    g = _ground(db, x, y, memo)
                    gr2 = _grad(db, x, y, 256.0)
                    w_ = S._why(x, y, half, True, False, True) or ('keep' if (sd2 is not None and sd2 < half * BANK_STREET_KEEP) else '')                         or ('plot' if any(_rect_dist(q, x, y) < half * MASS_PLOT for q in S.rects) else '')                         or ('ground' if (g is None or g < 0 or gr2 is None) else '')
                    if not w_:
                        why = ''
                        break
                    why = why or w_
                if why:
                    mwhy[(int(size), why)] += 1
                    dead.add((size, i, j))
                    continue
                zs = [vz(*v) for v in near]
                rise = max(zs) - min(zs)
                kb = slope_bin(math.hypot(*gr2))
                rot = pose(rng, b, s_, x, y, gr2, kb, P, tilt_scale=0.5, align=0.0, along=True)
                top = max(160.0, min(700.0, rise * 0.6 + 140.0), 0.24 * (b[5] - b[2]) * s_)
                if put(rid, b, s_, x, y, g + top - b[5] * s_, rot, 'bank', loose=True):
                    laid += 1
                    masses += 1
                    x_, y_, _z, rz_, s3, b3 = boxes[-1]
                    got = footprint(x_, y_, rz_, s3, b3)
                    covered.update(v for v in got if v in steep)
                    left.difference_update(got)
                    left.discard((i, j))
                    done = True
                    break
                dead.add((size, i, j))
            if done:
                break
        if not done:
            break
    for _sh, _neg, _r, i, j, rise, sd in order:
        if len(covered) >= target * len(steep) or laid >= BANK_MAX:
            break
        if (i, j) in covered:
            continue
        if not any((i + di, j + dj) in steep and (i + di, j + dj) not in covered for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            skip['lone'] += 1
            continue                               # (a lone bare vertex is no bank: no rock of its own)
        tried += 1
        x0, y0 = i * 128.0, j * 128.0
        gr = _grad(db, x0, y0)
        if gr is None:
            continue
        slope = math.hypot(*gr)
        dx_, dy_ = (-gr[0] / slope, -gr[1] / slope) if slope > 1e-6 else (0.0, 0.0)
        taller = smaller = 1.0
        for _try in range(BANK_TRIES):
            tall = max(160.0, min(1000.0, rise * 0.75 + 120.0)) * taller
            size = max(BANK_SMALLEST, min(1100.0, rise * 1.3 + 260.0) * smaller * (0.8 + rng.random() * 0.45))
            pk = K.pick(rng, size=size, tall=tall, small=smaller < 0.6)
            if not pk:
                break
            rid, b, s_ = pk
            half = max(b[3] - b[0], b[4] - b[1]) * s_ / 2.0
            # (its middle a little down or up the bank from the vertex, so it sits into the rise; jittered along it.
            # A spot refused for room: a smaller rock, and the other way along the fall)
            off = BANK_OFFS[_try % len(BANK_OFFS)] * half
            jit = (rng.random() - 0.5) * 96.0
            x, y = x0 + dx_ * off - dy_ * jit, y0 + dy_ * off + dx_ * jit
            cross = min(b[3] - b[0], b[4] - b[1]) * s_ / 2.0
            if S._why(x, y, half, True, False, True, cross) == 'street':
                # (a hand's breadth too near the street: stood back from it up or down its bank, before a smaller rock is
                # tried; 181 of a town's bank spots went for the street alone, lab 2026-11-11)
                sd0 = S._street_dist(plan, x, y)
                gx_ = (S._street_dist(plan, x + 32.0, y) or 0.0) - (S._street_dist(plan, x - 32.0, y) or 0.0)
                gy_ = (S._street_dist(plan, x, y + 32.0) or 0.0) - (S._street_dist(plan, x, y - 32.0) or 0.0)
                gl_ = math.hypot(gx_, gy_)
                need_ = cross * BODY - (sd0 or 0.0) + 12.0
                if gl_ > 1e-6 and 0 < need_ <= BANK_BACK:
                    x, y = x + gx_ / gl_ * need_, y + gy_ / gl_ * need_
            if not S.free(x, y, half, loose=True, bank=True, cross=cross):
                smaller *= 0.75
                continue
            sd2 = S._street_dist(plan, x, y)
            if sd2 is not None and sd2 < cross * BODY:
                S.refused['shoulder'] += 1
                smaller *= 0.75
                continue
            g = _ground(db, x, y, memo)
            gr2 = _grad(db, x, y)
            if g is None or g < 0 or gr2 is None:
                continue
            kb = slope_bin(math.hypot(*gr2))
            # (by a street it lies true along its bank: swayed 20 degrees either way, its corners swung onto the paving)
            rot = pose(rng, b, s_, x, y, gr2, kb, P, align=0.0, along=True, sway=10.0 if (sd2 is not None and sd2 < STREET_SIDE) else 40.0)
            # (and as it lies, no corner of its body on the street: by its short side alone 15 of 35 lapped one)
            c_, sn_ = math.cos(rot[2]), math.sin(rot[2])
            if any(S._street_dist(plan, x + (lx_ * c_ + ly_ * sn_) * s_ * BODY, y + (-lx_ * sn_ + ly_ * c_) * s_ * BODY) == 0
                   for lx_ in (b[0], b[3]) for ly_ in (b[1], b[4])):
                S.refused['street corner'] += 1
                smaller *= 0.75
                continue
            sink = _draw(rng, P['bins'][kb]['sink'] or [20, 50, 100, 200, 400], 0.2, 0.6)
            if put(rid, b, s_, x, y, g - sink - b[2] * s_, rot, 'bank', loose=True):
                laid += 1
                x_, y_, _z, rz_, s3, b3 = boxes[-1]
                covered.update(v for v in footprint(x_, y_, rz_, s3, b3) if v in steep)
                break
            taller *= 1.3
    return {'steep': len(steep), 'covered_before': round(before, 3), 'covered_after': round(len(covered) / float(len(steep)), 3),
            'laid': laid, 'masses': masses, 'tried': tried, 'mass_refused': {'%d %s' % k: v for k, v in sorted(mwhy.items())},
            'skipped': dict(skip), 'refused': dict(S.refused - ref0),
            'left': [(v[0] * 128.0, v[1] * 128.0) for v in steep if v not in covered]}


CLAD_STREET = 96.0             # the cladding keeps this far off a street's edge
CLAD_PLOT = 48.0               # ... and off a building's box
CLAD_TALL = 260.0              # (a town bank's piece may always stand this tall: the land's gorges take 420)


def clad_banks(db, plan, W, new_refs, cells, seed=1, outline=None, amount=1.0):
    """The sheer ground a town cut for itself clad as the land's own steep ground is (rockface.clad: the region's
    cliff pieces as faces and foot boulders, each settled by the rim rule), after the bank pass's rocks: inside the
    town's reach, off its streets, plots, door fronts, ways, treads and wall. The land's steep ground was clad when
    the land was made; the banks the town's terraces and streets cut after it had only the bank pass, whose rocks
    are dropped where a rim would show, 45 in a town (the user's Senchal, 2026-11-11: "we spent hours on decorating
    sheer cliffs and steep ground with rocks. So why did this get two rocks?"). The pieces join the town's own
    (new_refs). rockface's answer, with 'refs'."""
    import rockface
    import landregion
    import regions
    S = _Space(db, plan, W, new_refs, cells, outline)
    plan_ = plan

    def keep(x, y):
        sd = S._street_dist(plan_, x, y)
        if sd is not None and sd < CLAD_STREET:
            return True
        if (int(math.floor(x / S.PATCH)), int(math.floor(y / S.PATCH))) in S.roads and (sd is None or sd > ROAD_NEAR):
            return True
        for q in S.rects:
            if S._in_rect(q, x, y) or _rect_dist(q, x, y) < CLAD_PLOT:
                return True
        for qs in (S.ways, S.treads, S.wall):
            for q in qs:
                if S._in_rect(q, x, y) or _rect_dist(q, x, y) < 32.0:
                    return True
        for dx, dy in S.doors:
            if math.hypot(x - dx, y - dy) < DOOR_CLEAR:
                return True
        if S.square and math.hypot(x - S.square[0], y - S.square[1]) < S.square[2] + 64.0:
            return True
        return False

    def mask(x, y):
        return len(S.outline) < 3 or _inside_poly(S.outline, x, y) or _edge_dist(S.outline, x, y) <= S.pad

    keys = sorted({(int(k.lstrip('#').split(',')[0]), int(k.lstrip('#').split(',')[1])) for k in cells})
    rm = regions.region_map(db)
    rr = {k: landregion.rock_region(db, rm.get('%d,%d' % k) or '', '') for k in keys}
    before = set()
    for gx, gy in keys:
        before.update(r['k'] for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ())
    tall0 = rockface.TOWER_MIN
    rockface.TOWER_MIN = CLAD_TALL
    try:
        rf = rockface.clad(db, keys, mask=mask, keep=keep, amount=float(amount), seed=seed, parts=('face', 'foot'),
                           region_of=lambda x, y: rr.get((int(math.floor(x / 8192.0)), int(math.floor(y / 8192.0))), ''))
    finally:
        rockface.TOWER_MIN = tall0
    refs = []
    if rf.get('rocks'):
        for gx, gy in keys:
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                if r['k'] not in before:
                    refs.append(r['k'])
        new_refs.update(refs)
    return dict({k: v for k, v in rf.items() if k not in ('zones',)}, refs=refs)


def knoll(db, outline, memo=None):
    """The town's knoll, if its ground has one: the highest spot inside its outline (400 in from the edge) from which
    the ground falls KNOLL_DROP or more within KNOLL_REACH every way. (x, y, relief) or None."""
    outline = [tuple(p_) for p_ in outline or ()]
    if len(outline) < 3:
        return None
    xs, ys = [p_[0] for p_ in outline], [p_[1] for p_ in outline]
    best = None
    x = min(xs)
    while x <= max(xs):
        y = min(ys)
        while y <= max(ys):
            if _inside_poly(outline, x, y) and _edge_dist(outline, x, y) >= 400:
                g = _ground(db, x, y, memo)
                if g is not None and (best is None or g > best[2]):
                    best = (x, y, g)
            y += 256
        x += 256
    if best is None:
        if os.environ.get('TOWN_ROCK_DEBUG'):
            print('  knoll? no spot 400 in from the outline')
        return None
    x, y, g = best
    drops = []
    for k in range(8):
        a = k * math.pi / 4
        gs = [_ground(db, x + math.cos(a) * d, y + math.sin(a) * d, memo) for d in (KNOLL_REACH * 0.5, KNOLL_REACH)]
        gs = [v for v in gs if v is not None]
        if not gs:
            return None
        drops.append(g - min(gs))
    if os.environ.get('TOWN_ROCK_DEBUG'):
        print('  knoll? top %d,%d at %.0f; drops within %d: %s' % (x, y, g, KNOLL_REACH, [round(v) for v in drops]))
    if min(drops) < KNOLL_DROP:
        return None
    return (x, y, round(sum(drops) / len(drops)))


def _edge_dist(poly, x, y):
    return _rect_dist(poly, x, y) if not _inside_poly(poly, x, y) else min(
        _seg_dist(poly[i], poly[(i + 1) % len(poly)], x, y) for i in range(len(poly)))


def _inside_poly(poly, x, y):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _seg_dist(a, b, x, y):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if not L2 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
    return math.hypot(x - a[0] - dx * t, y - a[1] - dy * t)


def place(db, rocks, new_refs=None, cells=None):
    """The rocks into the mod's cells (no Undo step of their own: the town's make is one). The count; the keys into
    new_refs and the cell keys into cells when given."""
    import editing
    from project import set_ref_pos, zs
    mine = db.project.plugin.lower()
    made = 0
    rmemo = {}
    for r in rocks:
        low = r['id'].lower()
        if low not in rmemo:
            rmemo[low] = db.resolve_id(r['id'])
        ri = rmemo[low]
        if ri is None:
            continue
        key = '#%d,%d' % (math.floor(r['x'] / 8192.0), math.floor(r['y'] / 8192.0))
        try:
            c, _refs = editing._cell(db, key)
        except editing.EditError:
            continue
        rk = db.project.new_ref_key()
        pos = (r['x'], r['y'], r['z'], r['rx'], r['ry'], r['rz'])
        editing._store(c, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], pos, r['s']))
        r['key'] = rk
        db.project.town_parts[rk] = rk              # (a part of the town: Remove the town takes it away; its own group)
        made += 1
        if new_refs is not None:
            new_refs.add(rk)
        if cells is not None:
            cells.add(key)
    return made
