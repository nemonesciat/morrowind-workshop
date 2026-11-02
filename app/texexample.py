"""Ground textures by example: new land painted with the layout of the region's own land, patch by patch.

landdress picks each 512-unit patch's texture from the region's odds at its slope, height and shore, so the counts
come out like the game's but not which textures meet (the user, 2026-10-30: "the auto paint doesn't look great").
Here every patch of the region's land is an example: its texture, slope, height, shore distance and whether it sits on
a crest or in a hollow. New land is painted in rows; each patch takes the example whose ground is most like its own
and whose neighbours carry the textures already laid round it, and the example that carries on from a neighbour's
own example is always tried, so whole stretches of the game's layout come across: its transitions, its blob shapes,
its rock on the crests. (Texture synthesis by neighbourhood matching with coherence, Efros-Leung / Ashikhmin.)"""
import hashlib
import math
import random
from collections import defaultdict, deque

import landsurvey

CURVS = (-60, -15, 15, 60)       # a patch against the four round it, units: hollow, dip, even, rise, crest
SAMPLE = 400                     # region cells read at most
MIN_PATCHES = 3000               # fewer land patches than this: the region is too small to copy from
MIN_BUCKET = 40                  # examples a ground needs before it is copied from (rarer: the nearest ground's)
HOLDOUT = set()                  # cells never taken as examples (the lab repaints them to compare with the game's)
RANDOM_TRIES = 24                # examples tried from the patch's own ground, besides the ones carrying on
OFFS = ((-1, 0), (0, -1), (-1, -1), (1, -1), (-2, 0), (0, -2))   # the neighbours already painted, read in rows
# (held-out repaints of 8 blocks of the game's own land in 4 regions, lab jex3/jex4 2026-10-30: the textures that
# meet off the game's by 0.41 (total variation) against the odds' 0.47, crests and hollows 0.31 against 0.33, and
# 36% of patches the game's very texture against 26%. Heavier neighbour weights broke the land into more textures)
NEIGHBOUR_W = 0.5                # a neighbour whose texture the example's own neighbour doesn't have
COHERE_W = 0.5                   # off an example that carries on from a neighbour's (copying stretches whole)
NEWTEX_W = 1.5                   # a texture new to the cell once it has the region's number of them
_idx = {}


def _bands(slope, z, curv, shore):
    return (landsurvey._band(slope, landsurvey.SLOPES), landsurvey._band(z, landsurvey.HEIGHTS),
            landsurvey._band(curv, CURVS), landsurvey.shore_band(shore))


def _curv(Z, x, y):
    z = Z.get((x, y))
    nb = [Z[p] for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if p in Z]
    return (z - sum(nb) / len(nb)) if nb and z is not None else 0.0


def _shore(Z, reach):
    """{patch: patches to the nearest one under water, at most reach}."""
    dist, q = {}, deque()
    for p, z in Z.items():
        if z < 0:
            dist[p] = 0
            q.append(p)
    while q:
        p = q.popleft()
        if dist[p] >= reach:
            continue
        for nb in ((p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)):
            if nb in Z and nb not in dist:
                dist[nb] = dist[p] + 1
                q.append(nb)
    return dist


def _cell_patches(L):
    """[(slope degrees, mean height)] for a land record's 256 patches (65 x 65 heights, 128 apart)."""
    h, out = L['h'], []
    for py in range(16):
        for px in range(16):
            x0, y0 = px * 4, py * 4
            a, b = h[y0 * 65 + x0], h[y0 * 65 + x0 + 4]
            c, d = h[(y0 + 4) * 65 + x0], h[(y0 + 4) * 65 + x0 + 4]
            gx, gy = ((b - a) + (d - c)) / (2 * 512.0), ((c - a) + (d - b)) / (2 * 512.0)
            z = sum(h[(y0 + j) * 65 + x0 + i] for j in range(5) for i in range(5)) / 25.0
            out.append((math.degrees(math.atan(math.hypot(gx, gy))), z))
    return out


def index(db, region, cells=None):
    """The region's examples: {'tex': {patch: LTEX id}, 'band': {patch: bands}, 'by': {bands: [patches]}, 'n'}, None
    when it has too little land. cells: only these "gx,gy" (the lab's held-out halves)."""
    import landscape
    import regions as regions_
    key = (id(db.recs), region, tuple(sorted(cells)) if cells else None, tuple(sorted(HOLDOUT)))
    if key in _idx:
        return _idx[key]
    if cells is None:
        cells = [k for k, r in regions_.region_map(db).items() if r == region and k not in HOLDOUT]
        cells = sorted(cells, key=lambda k: hashlib.md5(k.encode()).hexdigest())[:SAMPLE]
    T, Z, S = {}, {}, {}
    for k in cells:
        gx, gy = (int(v) for v in k.split(','))
        L = landscape.read(db, gx, gy)
        if not L.get('exists') or not L.get('t') or not L.get('h'):
            continue
        for n, (sl, z) in enumerate(_cell_patches(L)):
            p = (gx * 16 + n % 16, gy * 16 + n // 16)
            T[p], Z[p], S[p] = L['t'][n], z, sl
    dist = _shore(Z, landsurvey.SHORE_BANDS[-1])
    band, by = {}, defaultdict(list)
    for p, z in Z.items():
        b = band[p] = _bands(S[p], z, _curv(Z, *p), dist.get(p, landsurvey.SHORE_BANDS[-1]))
        if usable(T[p]):
            by[b].append(p)
    land = sum(1 for z in Z.values() if z > 0)
    out = {'tex': T, 'band': band, 'by': dict(by), 'n': land} if land >= MIN_PATCHES else None
    _idx[key] = out
    return out


def usable(t):
    """A texture an example may give: not the default ground, nor a road (laid on purpose, not by the ground)."""
    return bool(t) and 'road' not in t.lower()


def _near_bands(b):
    """The patch's own ground first, then ground a step off: shore, then curvature, then slope and height."""
    sb, hb, cb, shb = b
    yield b
    for d in (1, 2, 3):
        for s2 in (shb - d, shb + d):
            yield (sb, hb, cb, s2)
    for dc in (1, -1, 2, -2):
        yield (sb, hb, cb + dc, shb)
    for ds, dh in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1), (2, 0), (-2, 0)):
        for dc in (0, 1, -1):
            yield (sb + ds, hb + dh, cb + dc, shb)


def _dist(a, b):
    return abs(a[0] - b[0]) * 1.0 + abs(a[1] - b[1]) * 1.0 + abs(a[2] - b[2]) * 0.7 + abs(a[3] - b[3]) * 0.5


def paint(db, F, keys, regions, seed=1, pre=None):
    """{(gx, gy): [256 LTEX ids, None where no example fits]} for the cells whose region has enough land to copy
    from (the rest left out, for landdress's odds to paint). pre: landdress._prepare's (stats, shore distances, memo)."""
    import landdress
    from landshapes import _check_stop      # (a land preview stopped from the busy chip gives up here too: most of its time)
    stats, sdist, _m = pre or landdress._prepare(F, keys)
    reach = landsurvey.SHORE_BANDS[-1]
    Z = {}
    for (gx, gy), st in stats.items():
        for n, (_s, z, _w) in enumerate(st):
            Z[(gx * 16 + n % 16, gy * 16 + n // 16)] = z
    rng = random.Random(seed * 7919 + 17)
    out, got = {}, {}
    src = {}                       # (painted patch: the example it took)
    todo = []
    for (gx, gy) in keys:
        _check_stop()
        I = index(db, regions.get((gx, gy), ''))
        if not I:
            continue
        for n, (sl, z, _w) in enumerate(stats[(gx, gy)]):
            p = (gx * 16 + n % 16, gy * 16 + n // 16)
            todo.append((p[1], p[0], (gx, gy), n, I, _bands(sl, z, _curv(Z, *p), sdist.get(p, reach))))
    todo.sort(key=lambda r: (r[0], r[1]))
    want = {}                      # (the region's textures a cell, its median: landdress.pattern)
    in_cell = defaultdict(set)
    for k_, (py, px, cell, n, I, b) in enumerate(todo):
        if not k_ & 511:
            _check_stop()
        p = (px, py)
        T, B = I['tex'], I['band']
        r = regions.get(cell, '')
        if r not in want:
            pt = landdress.pattern(db, r)
            want[r] = pt['n'] if pt else 99
        cands, coherent = set(), set()
        # (the examples that carry on from what's painted round it: copying whole stretches)
        for dx, dy in OFFS:
            s = src.get((px + dx, py + dy))
            if s:
                c = (s[0] - dx, s[1] - dy)
                if c in B and usable(T.get(c)):
                    cands.add(c)
                    coherent.add(c)
        tried = 0
        for nb in _near_bands(b):
            pool = I['by'].get(nb)
            if not pool or len(pool) < MIN_BUCKET:
                continue
            for _ in range(min(RANDOM_TRIES - tried, len(pool))):
                cands.add(pool[rng.randrange(len(pool))])
            tried = len(cands)
            if tried >= RANDOM_TRIES:
                break
        best = None
        have = in_cell[cell]
        for c in cands:
            sc = _dist(b, B[c])
            if c not in coherent:
                sc += COHERE_W
            if T[c] not in have and len(have) >= want[r]:
                sc += NEWTEX_W
            for dx, dy in OFFS:
                mine = got.get((px + dx, py + dy))
                if mine is None:
                    continue
                theirs = T.get((c[0] + dx, c[1] + dy))
                if theirs is not None and theirs != mine:
                    sc += NEIGHBOUR_W
            sc += rng.random() * 0.01
            if best is None or sc < best[0]:
                best = (sc, c)
        if best is None:
            continue
        got[p] = T[best[1]]
        src[p] = best[1]
        have.add(T[best[1]])
        out.setdefault(cell, [None] * 256)[n] = T[best[1]]
    # (a patch with no example near its ground, deep under the water, say, is None: the odds paint it)
    return out
