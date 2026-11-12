"""Rocks and trees keeping company (2026-11-09): in the game's land a sizeable rock has a tree near it, a tree a rock,
far more often than chance; the Workshop's Dress laid its trees first and kept every rock clear of them, so its land
read as rocks here and trees there, spread evenly.

Measured on the user's province against its own regions' untouched game cells (lab landlook, practice2): rocks a
million square units matched the game's, but trees were half the game's or fewer; 16-23% of the game's rocks had a tree
within 400, 3-8% of ours; its trees and rocks gather (Clark-Evans R 1.2), ours spread (1.6-2.4).

learn(db, region): from the region's game cells (their own refs, as the game made them), for rocks 256 across or more:
the share with a tree within REACH, the distances from rock to that tree, the trees standing there, how deep the game
sinks each tree model's origin; and the region's trees a million square units. pair(): after a Dress, for each of the
dressed cells' rocks with no tree within REACH, a tree at one of the game's distances from it, as often as the game's
rocks have one, never past the region's tree count. Kept in memory for the session."""
import math
import random
from collections import Counter, defaultdict

import mapdata

REACH = 400.0
MIN_ROCK = 256.0
SAMPLE = 80
STEEP_MAX = 38.0            # (no tree set on ground steeper than this by a rock)
FOOT_UP = 32.0              # (a set tree's lowest point is never more than this over the ground,
FOOT_DOWN = 0.35            #  nor deeper under it than this share of the tree's height: p34, trees stood 4,000 up)
_mem = {}


def _size(r):
    b = r.get('b')
    if not b:
        return 0.0
    return max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0)


def _slope(db, x, y):
    a, b = mapdata.terrain_z(db, x + 64, y), mapdata.terrain_z(db, x - 64, y)
    c, d = mapdata.terrain_z(db, x, y + 64), mapdata.terrain_z(db, x, y - 64)
    if None in (a, b, c, d):
        return 90.0
    return math.degrees(math.atan(math.hypot((a - b) / 128.0, (c - d) / 128.0)))


def learn(db, region):
    key = (id(db.recs), region)
    if key in _mem:
        return _mem[key]
    import cliffrocks
    import landdecor
    import landsurvey
    S = landsurvey.ready(db) or {}
    proj = db.project.cells if db.project else {}
    cells = [k for k, c in (S.get('cells') or {}).items() if (c.get('region') or '') == region and c.get('k') == 'land']
    rng = random.Random(region)
    rng.shuffle(cells)
    rocks_n = with_tree = 0
    dist, near_trees, sink = [], Counter(), defaultdict(list)
    trees_n, area = 0, 0.0
    for k in cells[:SAMPLE]:
        m = mapdata.cellmap(db, '#' + k, original=True)
        refs = m.get('refs') or ()
        trees = [r for r in refs if landdecor.kind_of(r['id'].lower()) == 'trees']
        rocks = [r for r in refs if cliffrocks.is_rock(r['id'].lower()) and _size(r) >= MIN_ROCK]
        trees_n += len(trees)
        area += (8192.0 * 8192.0) / 1e6
        if ('#' + k) not in proj:
            for t in trees:
                # (over the ground of the plugin that set it there: mapdata.own_heights)
                g = mapdata.own_ground(db, str(t.get('k') or '').split('|')[0], t['p'][0], t['p'][1])
                if g is not None:
                    sink[t['id'].lower()].append(t['p'][2] - g)
        for r in rocks:
            rocks_n += 1
            best = None
            for t in trees:
                d = math.hypot(t['p'][0] - r['p'][0], t['p'][1] - r['p'][1])
                if d <= REACH and (best is None or d < best[0]):
                    best = (d, t)
            if best:
                with_tree += 1
                dist.append(best[0] / max(1.0, _size(r) / 2.0))     # (in rock half-widths: a big rock's tree stands farther off)
                near_trees[best[1]['id']] += 1
    out = {'rocks': rocks_n, 'share': with_tree / float(rocks_n or 1), 'dist': sorted(dist), 'trees': near_trees.most_common(12),
           'sink': {k: sorted(v)[len(v) // 2] for k, v in sink.items() if v}, 'tree_density': trees_n / max(1.0, area)}
    _mem[key] = out
    return out


def pair(db, cells, region_of, seed=1, hold=None, amount=1.0):
    """For the dressed cells ('gx,gy' or (gx, gy)), trees by their bare rocks at the game's share and distances; placed,
    in the cells' own regions' trees. The number of trees set."""
    import cliffrocks
    import editing
    import landdecor
    from project import set_ref_pos, zs
    rng = random.Random(seed * 17 + 3)
    keys = sorted({tuple(c) if isinstance(c, (tuple, list)) else tuple(int(v) for v in str(c).lstrip('#').split(',')) for c in cells})
    by_reg = defaultdict(list)
    for gx, gy in keys:
        reg = (region_of((gx + 0.5) * 8192.0, (gy + 0.5) * 8192.0) or [''])[0]
        by_reg[reg].append((gx, gy))
    mine = db.project.plugin.lower()
    laid = 0
    for reg, ks in by_reg.items():
        if not reg:
            continue
        L = learn(db, reg)
        if L['rocks'] < 20 or not L['trees'] or not L['dist']:
            continue
        rocks, trees, area, built = [], [], 0.0, []
        for gx, gy in ks:
            refs = mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()
            area += (8192.0 * 8192.0) / 1e6
            for r in refs:
                low = r['id'].lower()
                if cliffrocks.is_rock(low) and _size(r) >= MIN_ROCK:
                    rocks.append(r)
                elif landdecor.kind_of(low) == 'trees':
                    trees.append((r['p'][0], r['p'][1]))
                elif r['type'] in ('DOOR', 'NPC_') or (r.get('b') and r['type'] in ('STAT', 'ACTI') and mapdata.is_architecture(r['type'], r['id'], r['b'])):
                    built.append((r['p'][0], r['p'][1], max(200.0, _size(r) / 2.0 + 150.0)))     # (a building, a door, a road piece: no tree at it)
        room = max(0, int(L['tree_density'] * area * amount) - len(trees))     # (never past the region's trees, times the Trees slider)
        bare = [r for r in rocks if not any(math.hypot(r['p'][0] - x, r['p'][1] - y) <= REACH for x, y in trees)]
        have = len(rocks) - len(bare)
        want = int(L['share'] * len(rocks) * max(1.0, amount)) - have
        rng.shuffle(bare)
        ids = [i for i, _n in L['trees']]
        wts = [n for _i, n in L['trees']]
        for r in bare:
            if want <= 0 or room <= 0:
                break
            half = _size(r) / 2.0
            for _try in range(8):
                d = max(half * 0.9, min(REACH, rng.choice(L['dist']) * half))
                a = rng.uniform(0, 2 * math.pi)
                x, y = r['p'][0] + d * math.cos(a), r['p'][1] + d * math.sin(a)
                g = mapdata.terrain_z(db, x, y)
                if g is None or g < 40 or _slope(db, x, y) > STEEP_MAX:
                    continue
                if any(math.hypot(x - tx, y - ty) < 120 for tx, ty in trees):
                    continue
                if any(math.hypot(x - bx, y - by) < br for bx, by, br in built):
                    continue
                if any(math.hypot(x - o['p'][0], y - o['p'][1]) < max(60.0, _size(o) / 2.0) for o in rocks if o is not r):
                    continue
                tid = rng.choices(ids, wts)[0]
                ri = db.resolve_id(tid)
                if ri is None:
                    break
                key = '#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0))
                try:
                    c_, _r = editing._cell(db, key)
                except editing.EditError:
                    break
                z = g + L['sink'].get(tid.lower(), -8.0)
                sc = rng.uniform(0.85, 1.15)
                tb = mapdata.object_bounds(db, ri)
                if tb:
                    foot, tall = z + tb[2] * sc, (tb[5] - tb[2]) * sc
                    if foot > g + FOOT_UP or foot < g - FOOT_DOWN * tall:
                        z = g - tb[2] * sc - 16.0          # (its foot a little in the ground, whatever was learnt)
                rk = db.project.new_ref_key()
                editing._store(c_, rk, mine, int(rk.rsplit('|', 1)[1]),
                               set_ref_pos([('NAME', zs(db.recs[ri][1]))], (x, y, z, 0.0, 0.0, rng.uniform(0, 2 * math.pi)), sc))
                trees.append((x, y))
                laid += 1
                want -= 1
                room -= 1
                break
    if laid:
        db.sync_project()
    return laid
