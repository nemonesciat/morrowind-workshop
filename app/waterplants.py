"""What grows and lies in the water (2026-11-09; the sea bed's own things 2026-11-14): the lily pads on a swamp's
pools, the kelp on the sea bed, the reeds in the shallows, and the bed's rocks, barnacles, kollops, coral, starfish,
urchins and shells, as each region's own water has them.

The user, 2026-11-09: "I saw almost none of the normal things you'd see in a swamp region like so many in the game."
The land's growth (landdecor) leaves kelp, lilies, coral and seaweed out by name, so nothing grew in the water: the
Bitter Coast's lily pads are a quarter of all it grows (0.65 a million square units), its kelp 0.18; ours had none.

The user, 2026-11-14: "right now sea floor looks uninteresting ... rocks, sea shells, seaweed, coral, that sort of
thing." Counted that day (lab sea1): the game sets 0.7 to 3.2 things a million square units of bed in its dressed
seas; six in ten are kelp and rocks (no rock was ever laid under the water: cliffrocks and rockface keep to dry
land), then the cave plant it uses as weed, barnacles (half of them on a rock), kollops, coral, urchins, starfish.
Ours had 0.06, kelp alone, and none at all where the cell's own region has bare water (a heightmap's lake).

learn(db, region): the region's game cells cut into SQUARE patches of water by their depth (BANDS) and whether the
bed slopes, each with what stands in it (on the surface, or on the bed, with its height over the one or the other; a
thing set on a rock keeps its place on that rock), empty patches kept too so the density holds and the things keep
the game's clumps. grow(): each of the marked cells' water patches given one of the region's patches of the same
depth, turned by a quarter turn or not; an item only where our water is there for it. A region with bare water takes
after the nearest dressed water (seafloor.dressed_like); a lake gets none of the sea's animals (seafloor.open_water);
water the game dressed itself is left as it is. Kept in memory for the session."""
import hashlib
import math
import random
import re
from collections import defaultdict

import mapdata

SQUARE = 512.0
WATER_PLANT = re.compile(r'lily|lilypad|kelp|seaweed|coral|_reed|reeds|cattail|bulrush|bc_knee')
SEA_LIFE = re.compile(r'barnacle|kollop|seaurch|starf|eyestar|fauna_clam|oyst|fauna_shell|seabiscuit|seacup|bulbshroom|smearalgae|'
                      r'fishsch|active_bubbles|in_cave_plant|driftwood')
# (the sea's own, never in a lake)
SALT = re.compile(r'coral|barnacle|kollop|seaurch|starf|eyestar|fauna_clam|oyst|fauna_shell|seabiscuit|seacup|fishsch')
# (what sits on a rock or the bed and never hangs in the water by itself)
SITS = re.compile(r'coral|barnacle|kollop|seaurch|starf|eyestar|fauna_clam|oyst|fauna_shell|seabiscuit|seacup|bulbshroom|smearalgae')
BANDS = ((-120.0, 'edge'), (-450.0, 'shallow'), (-1300.0, 'mid'), (-1e9, 'deep'))
SURFACE = 70.0              # (a plant within this of the water's top floats on it)
LOOK = 160                  # (the region's cells looked at, at most)
KEEP = 500                  # (patches kept a band and slope)
SLOPED = 160.0              # (a patch whose bed rises this much across it is a sloping one)
ON_PAD = 24.0               # (a thing within this of a rock's box sits on that rock)
FLOAT = 80.0                # (a sitting thing this far over the bed with no rock under it is left out)
ENOUGH = 40                 # (things a region's sampled water must hold to be its own look)
DRESSED = 0.25              # (things a million square units of a cell's bed for the game's own dressing to stand)
_mem = {}


def sea_rock(low):
    import cliffrocks
    return cliffrocks.is_rock(low) or 'menhir_l' in low or ('terrrock' in low and 'menhir' in low)


def takes(low, typ):
    """Whether a thing is the water's own: a water plant, one of the bed's animals, a rock (which the caller takes
    only under the water)."""
    if typ in ('STAT', 'ACTI', 'CONT'):
        return bool(WATER_PLANT.search(low) or SEA_LIFE.search(low)) or sea_rock(low)
    return typ == 'LIGH' and 'bulbshroom' in low


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
    b = band_of(sum(hs) / len(hs), min(hs))
    if not b:
        return None
    k = 0
    if len(hs) == 25:
        # (which way the bed falls, to a quarter turn: east 0, north 1, west 2, south 3)
        sx = sum(hs[j * 5 + 4] - hs[j * 5] for j in range(5))
        sy = sum(hs[20 + i] - hs[i] for i in range(5))
        k = int(round(math.atan2(-sy, -sx) / (math.pi / 2))) % 4
    return b + ('/s' if max(hs) - min(hs) >= SLOPED else '/f'), k


def _in_box(h, p, pad):
    b, s = h.get('b'), h.get('s') or 1.0
    if not b:
        return None
    dx, dy = p[0] - h['p'][0], p[1] - h['p'][1]
    c, sn = math.cos(h['p'][5]), math.sin(h['p'][5])
    lx, ly, lz = (dx * c - dy * sn) / s, (dx * sn + dy * c) / s, (p[2] - h['p'][2]) / s
    if b[0] - pad <= lx <= b[3] + pad and b[1] - pad <= ly <= b[4] + pad and b[2] - pad <= lz <= b[5] + pad:
        return (b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2]) * s ** 3
    return None


def learn(db, region):
    """{'patches': {'band/slope': [(the way its bed falls, [item])]}, 'found'}; an item: [id, dx, dy, mode, off, rx,
    ry, rz, scale, host]:
    mode 'surf' (off: its height), 'bed' (off: over the bed) or 'on' (off: over the origin of the patch's item host)."""
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
    per = int(8192 // SQUARE)
    for ck in cells:
        gx, gy = (int(v) for v in ck.split(','))
        L = mapdata.land(db, gx, gy)
        if not L.get('exists'):
            continue
        # (a dead flat cell is sea nobody worked, no example of a flat bed: a third of the Telvanni Isles' sea cells,
        # and with them a made bed's gentler patches drew from nothing but empty ones, half the game's count)
        srt = sorted(L['h'])
        if srt[int(0.95 * len(srt))] - srt[int(0.05 * len(srt))] < 40:
            continue
        hat = landdecor._cell_hat(L['h'], gx, gy)
        sq = {}
        for i in range(per):
            for j in range(per):
                b = _patch(hat, gx * 8192.0 + i * SQUARE, gy * 8192.0 + j * SQUARE)
                if b:
                    sq[(i, j)] = (b[0], [], b[1])
        if not sq:
            continue
        rocks, rest = [], []
        for r in mapdata.cellmap(db, '#' + ck, original=True).get('refs') or ():
            low = r['id'].lower()
            if not takes(low, r['type']):
                continue
            g = hat(r['p'][0], r['p'][1])
            if g is None:
                continue
            if sea_rock(low):
                if g < -20:
                    rocks.append((r, g))
            elif g < 10:
                rest.append((r, g, low))
        at = {}

        def put(r, g, i, j, host=-1, hz=0.0):
            surf = host < 0 and abs(r['p'][2]) <= SURFACE and g < -10
            sq[(i, j)][1].append([r['id'], round(r['p'][0] - gx * 8192.0 - i * SQUARE, 1), round(r['p'][1] - gy * 8192.0 - j * SQUARE, 1),
                                  'on' if host >= 0 else 'surf' if surf else 'bed',
                                  round(r['p'][2] - hz if host >= 0 else r['p'][2] if surf else r['p'][2] - g, 1),
                                  round(r['p'][3], 3), round(r['p'][4], 3), round(r['p'][5], 3), round(r.get('s') or 1.0, 2), host])
            return len(sq[(i, j)][1]) - 1
        for r, g in rocks:
            i, j = int((r['p'][0] - gx * 8192.0) // SQUARE), int((r['p'][1] - gy * 8192.0) // SQUARE)
            if (i, j) in sq:
                at[r['k']] = (i, j, put(r, g, i, j))
                found += 1
        for r, g, low in rest:
            i, j = int((r['p'][0] - gx * 8192.0) // SQUARE), int((r['p'][1] - gy * 8192.0) // SQUARE)
            host = None
            if SITS.search(low):
                for h, _hg in rocks:
                    if h['k'] not in at or abs(h['p'][0] - r['p'][0]) > 2000 or abs(h['p'][1] - r['p'][1]) > 2000:
                        continue
                    v = _in_box(h, r['p'], ON_PAD)
                    if v is not None and (host is None or v < host[0]):
                        host = (v, h)
                if host is None and r['p'][2] - g > FLOAT:
                    continue                    # (set on something that isn't the bed's: a wreck, a pier, a rock of the next cell)
            if host is not None:
                hi, hj, hn = at[host[1]['k']]
                put(r, g, hi, hj, hn, host[1]['p'][2])
                found += 1
            elif (i, j) in sq:
                put(r, g, i, j)
                found += 1
        for (_i, _j), (b, items, k) in sq.items():
            if len(patches[b]) < KEEP:
                patches[b].append((k, items))
    out = {'patches': dict(patches), 'found': found}
    _mem[key] = out
    return out


def _pool(L, key):
    """The region's patches for a depth and slope: its own when there are a few, else the same depth's other slope."""
    P = L['patches'].get(key) or []
    if len(P) >= 8:
        return P
    other = key[:-1] + ('f' if key.endswith('s') else 's')
    return P + (L['patches'].get(other) or [])


def _game_dressed(db, gx, gy):
    """Whether the game dressed this cell's bed itself (its own things on it, the mod's left out)."""
    L = mapdata.land(db, gx, gy)
    if not L.get('exists'):
        return False
    H = L['h']
    bed = sum(1 for h in H if h < -20) * 128.0 * 128.0
    if bed < 2e6:
        return False
    n = 0
    for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy), original=True).get('refs') or ():
        if r['p'][2] <= -15 and takes(r['id'].lower(), r['type']):
            n += 1
    return n / (bed / 1e6) >= DRESSED


def _palette(db, region, memo):
    """The rocks a region's land wears, as the cliff survey learnt them: [(id, how wide, its lowest point)]; [] when
    it isn't learnt yet or the region has under six."""
    if region in memo:
        return memo[region]
    out = []
    try:
        import cliffsurvey
        S = cliffsurvey.ready(db)
        R = ((S or {}).get('regions') or {}).get(region) or {}
        seen = {}
        for part in list(R.get('bands') or []) + list((R.get('zones') or {}).values()):
            for it in part.get('items') or ():
                low = it['id'].lower()
                if low not in seen and sea_rock(low) and it.get('size'):
                    seen[low] = (it['id'], float(max(it['size'][0], it['size'][1], 1.0)), float(it.get('zmin') or 0.0))
        if len(seen) >= 6:
            out = sorted(seen.values())
    except Exception as e:
        print("water, the land's rocks:", e)
    memo[region] = out
    return out


def _seat(db, rid, x, y, z, rz, sc, hat, memo):
    """A bed rock's height with its foot in the ground: no lower corner of its box over the bed (a rock the game
    leant on a slope, set on a bed that falls another way, hung clear of it, the 3D view 2026-11-14). None when that
    would bury three quarters of it."""
    low = rid.lower()
    if low not in memo:
        ri = db.resolve_id(rid)
        memo[low] = mapdata.object_bounds(db, ri) if ri is not None else None
    b = memo[low]
    if not b:
        return z
    c, sn = math.cos(rz), math.sin(rz)
    lowest = None
    for lx, ly in ((b[0], b[1]), (b[3], b[1]), (b[0], b[4]), (b[3], b[4]), (0.0, 0.0)):
        lx, ly = lx * 0.7 * sc, ly * 0.7 * sc
        g = hat(x + lx * c + ly * sn, y - lx * sn + ly * c)
        if g is not None and (lowest is None or g < lowest):
            lowest = g
    if lowest is None:
        return z
    over = z + b[2] * sc - (lowest - 8.0)
    if over <= 0:
        return z
    if over > 0.75 * (b[5] - b[2]) * sc:
        return None
    return z - over


def _swap(db, rid, pal, memo):
    """A bed rock of borrowed water as one of the land's own rocks of its size: (id, how far its origin is moved up
    so its foot stays where the other's was, a unit of scale)."""
    low = rid.lower()
    if low not in memo:
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            memo[low] = (rid, 0.0)
        else:
            d = max(b[3] - b[0], b[4] - b[1], 1.0)
            near = sorted(pal, key=lambda it: (abs(math.log(it[1] / d)), it[0]))[:3]
            pick = near[int(hashlib.md5(low.encode()).hexdigest(), 16) % len(near)]
            memo[low] = (pick[0], b[2] - pick[2])
    return memo[low]


def grow(db, keys, region_for, seed=1, hat=None, free=None, amount=1.0, rocks=1.0, like='', rock_from=None):
    """The marked cells' water patches dressed as their regions' are: [{'id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's'}]
    for cliffrocks.place. keys: (gx, gy); region_for(gx, gy): the region whose water it takes after; hat(x, y): the
    ground's height (the land as it stands when None); free(x, y): False where nothing may be set (held ground);
    amount, rocks: how much of the game's share of plants and animals, and of rocks, is laid (0 to 2);
    rock_from(gx, gy): the region whose rocks the land there wears: a bed dressed after another region's water gets
    its rocks from that one, size for size (but a rock with barnacles or coral set on it stays the rock it was)."""
    hat = hat or (lambda x, y: mapdata.terrain_z(db, x, y))
    rng = random.Random(seed * 31 + 7)
    keys = list(keys)
    try:
        import seafloor
        salt = seafloor.open_water(db, keys)
    except Exception as e:
        print('water, sea or lake:', e)
        seafloor, salt = None, {}
    out = []
    libs = {}
    pals, swaps, boxes = {}, {}, {}
    per = int(8192 // SQUARE)
    for gx, gy in keys:
        reg = region_for(gx, gy) or ''
        lk = (reg, gx // 3, gy // 3)
        if lk not in libs:
            L = learn(db, reg) if reg else None
            used = reg
            if (not L or L['found'] < ENOUGH) and seafloor:
                # (bare water of its own: the nearest dressed water's)
                try:
                    for r2 in seafloor.dressed_like(db, reg, gx, gy, like):
                        L2 = learn(db, r2)
                        if L2['found'] >= ENOUGH:
                            L, used = L2, r2
                            break
                except Exception as e:
                    print('water, whose to take after:', e)
            libs[lk] = (L, used)
        L, used = libs[lk]
        if not L or not L['found']:
            continue
        pal = []
        if rock_from and used != reg:
            rr = rock_from(gx, gy) or ''
            if rr and rr != used:
                pal = _palette(db, rr, pals)
        if _game_dressed(db, gx, gy):
            continue
        sea = salt.get((gx, gy), True)
        for i in range(per):
            for j in range(per):
                x0, y0 = gx * 8192.0 + i * SQUARE, gy * 8192.0 + j * SQUARE
                b = _patch(hat, x0, y0)
                P = _pool(L, b[0]) if b else None
                if not P:
                    continue
                for _again in range(2 if max(amount, rocks) > 1.0 else 1):
                    fell, items = rng.choice(P)
                    if not items:
                        continue
                    # (a sloping patch turned so its bed falls the way ours does: its rocks lean on the slope they
                    # were set on; a level one by a quarter turn or none, the same patch never twice alike)
                    q = (fell - b[1]) % 4 if b[0].endswith('s') else rng.randrange(4)
                    c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][q]
                    set_z = {}
                    sat_on = {it[9] for it in items if it[3] == 'on'} if pal else ()
                    for n, (rid, dx, dy, mode, off, rx, ry, rz, sc, host) in enumerate(items):
                        low = rid.lower()
                        rock = mode != 'on' and sea_rock(low)
                        k = rocks if rock else amount
                        k = k - 1.0 if _again else min(1.0, k)
                        if mode == 'on':
                            if host not in set_z:
                                continue                # (its rock wasn't set)
                        elif rng.random() >= k:
                            continue
                        if not sea and SALT.search(low):
                            continue
                        ux, uy = dx - SQUARE / 2, dy - SQUARE / 2
                        # (turned the way a thing's own turn goes, clockwise from above, so what sits on a rock stays on it)
                        x, y = x0 + SQUARE / 2 + ux * c + uy * s, y0 + SQUARE / 2 - ux * s + uy * c
                        if free and not free(x, y):
                            continue
                        g = hat(x, y)
                        if g is None:
                            continue
                        if mode == 'on':
                            z = set_z[host] + off
                        elif mode == 'surf':
                            if g > -20:
                                continue                # (a lily needs water under it)
                            z = off
                        else:
                            if g > (-20 if rock else 10):
                                continue                # (kelp and reeds stand in the water, the bed's rocks under it)
                            z = g + off
                        turn = (rz + q * math.pi / 2) % (2 * math.pi)
                        if rock:
                            if pal and n not in sat_on:
                                rid, up = _swap(db, rid, pal, swaps.setdefault(id(pal), {}))
                                z += up * sc
                            z = _seat(db, rid, x, y, z, turn, sc, hat, boxes)
                            if z is None:
                                continue
                        set_z[n] = z
                        out.append({'id': rid, 'x': x, 'y': y, 'z': z, 'rx': rx, 'ry': ry, 'rz': turn, 's': sc})
    return out
