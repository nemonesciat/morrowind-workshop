"""What grows in the water (2026-11-09): the lily pads on a swamp's pools, the kelp on the sea bed, the reeds in the
shallows, as each region's own water has them.

The user, 2026-11-09: "I saw almost none of the normal things you'd see in a swamp region like so many in the game."
The land's growth (landdecor) leaves kelp, lilies, coral and seaweed out by name, so nothing grew in the water: the
Bitter Coast's lily pads are a quarter of all it grows (0.65 a million square units), its kelp 0.18; ours had none.

learn(db, region): the region's game cells cut into SQUARE patches of water by their depth (BANDS), each with what
grows in it (on the surface, or on the bed, with its height over the one or the other), empty patches kept too so the
density holds and the plants keep the game's clumps. grow(): each of the marked cells' water patches given one of the
region's patches of the same depth, turned by a quarter turn or not; an item only where our water is there for it.
Kept in memory for the session."""
import hashlib
import math
import random
import re
from collections import defaultdict

import mapdata

SQUARE = 512.0
WATER_PLANT = re.compile(r'lily|lilypad|kelp|seaweed|coral|_reed|reeds|cattail|bulrush|bc_knee')
BANDS = ((-120.0, 'edge'), (-450.0, 'shallow'), (-1300.0, 'mid'), (-1e9, 'deep'))
SURFACE = 70.0              # (a plant within this of the water's top floats on it)
LOOK = 160                  # (the region's cells looked at, at most)
KEEP = 700                  # (patches kept a band)
_mem = {}


def band_of(mean, low):
    if low >= 0:
        return None                             # (no water in the patch)
    if mean >= 40:
        return 'edge' if low < -20 else None
    for lim, name in BANDS:
        if mean >= lim:
            return name
    return 'deep'


def _patch(hat, x0, y0):
    hs = []
    for j in range(5):
        for i in range(5):
            h = hat(x0 + i * SQUARE / 4.0, y0 + j * SQUARE / 4.0)
            if h is not None:
                hs.append(h)
    if not hs:
        return None
    return band_of(sum(hs) / len(hs), min(hs))


def learn(db, region):
    key = (id(db.recs), region)
    if key in _mem:
        return _mem[key]
    import landdecor
    import regions
    rmap = regions.region_map(db)
    proj = db.project.cells if db.project else {}
    cells = sorted((k for k, r in rmap.items() if r == region and ('#' + k) not in proj), key=lambda k: hashlib.md5(k.encode()).hexdigest())[:LOOK]
    patches = defaultdict(list)
    found = 0
    for ck in cells:
        gx, gy = (int(v) for v in ck.split(','))
        L = mapdata.land(db, gx, gy)
        if not L.get('exists'):
            continue
        hat = landdecor._cell_hat(L['h'], gx, gy)
        per = int(8192 // SQUARE)
        sq = {}
        for i in range(per):
            for j in range(per):
                b = _patch(hat, gx * 8192.0 + i * SQUARE, gy * 8192.0 + j * SQUARE)
                if b:
                    sq[(i, j)] = (b, [])
        if not sq:
            continue
        for r in mapdata.cellmap(db, '#' + ck, original=True).get('refs') or ():
            low = r['id'].lower()
            if not WATER_PLANT.search(low) or r['type'] not in ('STAT', 'ACTI', 'CONT'):
                continue
            i, j = int((r['p'][0] - gx * 8192.0) // SQUARE), int((r['p'][1] - gy * 8192.0) // SQUARE)
            if (i, j) not in sq:
                continue
            g = hat(r['p'][0], r['p'][1])
            if g is None:
                continue
            surf = abs(r['p'][2]) <= SURFACE and g < -10
            sq[(i, j)][1].append([r['id'], round(r['p'][0] - gx * 8192.0 - i * SQUARE, 1), round(r['p'][1] - gy * 8192.0 - j * SQUARE, 1),
                                  'surf' if surf else 'bed', round(r['p'][2] if surf else r['p'][2] - g, 1),
                                  round(r['p'][3], 3), round(r['p'][4], 3), round(r['p'][5], 3), round(r.get('s') or 1.0, 2)])
            found += 1
        for (_i, _j), (b, items) in sq.items():
            if len(patches[b]) < KEEP:
                patches[b].append(items)
    out = {'patches': dict(patches), 'found': found}
    _mem[key] = out
    return out


def grow(db, keys, region_for, seed=1, hat=None):
    """The marked cells' water patches grown as their regions' are: [{'id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's'}]
    for cliffrocks.place. keys: (gx, gy); region_for(gx, gy): the region whose water it takes after; hat(x, y): the
    ground's height (the land as it stands when None)."""
    hat = hat or (lambda x, y: mapdata.terrain_z(db, x, y))
    rng = random.Random(seed * 31 + 7)
    out = []
    for gx, gy in keys:
        reg = region_for(gx, gy)
        if not reg:
            continue
        L = learn(db, reg)
        if not L['found']:
            continue
        per = int(8192 // SQUARE)
        for i in range(per):
            for j in range(per):
                x0, y0 = gx * 8192.0 + i * SQUARE, gy * 8192.0 + j * SQUARE
                b = _patch(hat, x0, y0)
                P = L['patches'].get(b) if b else None
                if not P:
                    continue
                items = rng.choice(P)
                if not items:
                    continue
                q = rng.randrange(4)                # (a quarter turn or none: the same patch never twice alike)
                c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][q]
                for rid, dx, dy, mode, off, rx, ry, rz, sc in items:
                    ux, uy = dx - SQUARE / 2, dy - SQUARE / 2
                    x, y = x0 + SQUARE / 2 + ux * c - uy * s, y0 + SQUARE / 2 + ux * s + uy * c
                    g = hat(x, y)
                    if g is None:
                        continue
                    if mode == 'surf':
                        if g > -20:
                            continue                # (a lily needs water under it)
                        z = off
                    else:
                        if g > 10:
                            continue                # (kelp and reeds stand in the water)
                        z = g + off
                    out.append({'id': rid, 'x': x, 'y': y, 'z': z, 'rx': rx, 'ry': ry, 'rz': (rz + q * math.pi / 2) % (2 * math.pi), 's': sc})
    return out
