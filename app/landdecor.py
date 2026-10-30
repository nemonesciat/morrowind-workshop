"""Dressing land the way the game dresses its own: trees, plants, grass and logs from the region's own land, as
Auto-furnish dresses a table from the game's examples. The user (2026-10-29): "a way to mark out an area ... that
can attempt to dress landmass the way the game does", like the land around it in the region.

The region's land is cut into SQUARE-unit squares, each kept whole with what grows on it (each thing's spot in the
square, its height over the ground, its turn and size), and filed by its ground: how steep (landsurvey.SLOPES),
how high (landsurvey.HEIGHTS) and whether the water is near. Squares with buildings, roads' furniture or people are
left out: those are settled, not grown. Land is then dressed square by square with one of the game's squares of the
same ground, so groves, lone trees, undergrowth round trunks and bare scree come out as the game lays them, because
they are its own. Rocks are laid apart (cliffrocks: turned to their slopes)."""
import hashlib
import json
import math
import os
import random

import landsurvey
import mapdata
from project import ref_info

VERSION = 2
SQUARE = 1024                   # units a square side: 8 a cell
SAMPLE = 90                     # wild cells a region read, spread over it
LOOK = 260                      # cells looked at for them
KEEP = 300                      # squares kept a kind of ground
ENOUGH = 40                     # squares with something on them a region needs to be its own look
BROAD = 600                     # squares of land a region needs to stand in for another's missing ground
FALLBACKS = 3                   # regions with land tried after a cell's own, the nearest first
SETTLED = 300                   # a non-growing thing this wide (or a door, a person) makes a square settled
_mem = {}


def _kinds():
    import scatter
    return scatter


def kind_of(low):
    """'trees', 'plants', 'grass', 'logs' or None (rocks are cliffrocks')."""
    import cliffrocks
    if cliffrocks.is_rock(low) or low.startswith(('sound', 'marker')) or any(w in low for w in ('kelp', 'lily', 'coral', 'seaweed', 'cave_')):
        return None
    k = _kinds()._kind(low)
    return k if k in ('trees', 'plants', 'grass', 'logs') else None


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'landdecor_%s_v%d.json' % (_sig(db), VERSION))


def ground_key(slope, height, wet):
    return '%d,%d,%d' % (landsurvey._band(slope, landsurvey.SLOPES), landsurvey._band(height, landsurvey.HEIGHTS), 1 if wet else 0)


def _square_ground(hat, x0, y0):
    """(mean steepness, mean height, water near) of a square, from hat(x, y) (the height at a world point)."""
    hs, sl = [], []
    for j in range(5):
        for i in range(5):
            x, y = x0 + i * SQUARE / 4.0, y0 + j * SQUARE / 4.0
            h = hat(x, y)
            if h is None:
                continue
            hs.append(h)
            a, b, c, d = hat(x + 128, y), hat(x - 128, y), hat(x, y + 128), hat(x, y - 128)
            if None not in (a, b, c, d):
                sl.append(math.degrees(math.atan(math.hypot((a - b) / 256.0, (c - d) / 256.0))))
    if not hs:
        return None
    wet = min(hs) <= 0 or any((hat(x0 + dx, y0 + dy) or 1) <= 0 for dx in (-512, SQUARE + 512) for dy in (-512, SQUARE + 512))
    return (sum(sl) / len(sl) if sl else 0.0), sum(hs) / len(hs), wet


def _cell_hat(H, gx, gy):
    ox, oy = gx * 8192.0, gy * 8192.0

    def hat(x, y):
        fx, fy = (x - ox) / 128.0, (y - oy) / 128.0
        if not (0 <= fx <= 64 and 0 <= fy <= 64):
            return None
        x0, y0 = min(63, int(fx)), min(63, int(fy))
        tx, ty = fx - x0, fy - y0
        return ((H[y0 * 65 + x0] * (1 - tx) + H[y0 * 65 + x0 + 1] * tx) * (1 - ty) +
                (H[(y0 + 1) * 65 + x0] * (1 - tx) + H[(y0 + 1) * 65 + x0 + 1] * tx) * ty)
    return hat


def _tag(db, rid, memo):
    low = rid.lower()
    if low not in memo:
        ri = db.resolve_id(rid)
        memo[low] = (db.recs[ri][0], db.recs[ri][1], mapdata.object_bounds(db, ri)) if ri is not None else None
    return memo[low][0] if memo[low] else None


def learn(db, region):
    """{'squares': {ground key: [[item, ...], ...]}, 'grown': squares with something, 'cells'}: the region's own
    squares by their ground (item: [id, dx, dy, over the ground, rx, ry, rz, scale]). Cached by the load order."""
    region = (region or '').lower()
    key = (id(db.recs), region)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    disk = {}
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                disk = json.load(f)
    except (OSError, ValueError):
        disk = {}
    if region in disk:
        _mem[key] = disk[region]
        return disk[region]
    import regions
    rmap = regions.region_map(db)
    cells = sorted((k for k, r in rmap.items() if r == region), key=lambda k: hashlib.md5(k.encode()).hexdigest())[:LOOK]
    squares, memo, used, grown = {}, {}, 0, 0
    for ck in cells:
        if used >= SAMPLE:
            break
        gx, gy = (int(v) for v in ck.split(','))
        L = mapdata.land(db, gx, gy)
        if not L.get('exists') or sum(1 for v in L['h'] if v > 0) < 600:
            continue
        hat = _cell_hat(L['h'], gx, gy)
        used += 1
        per = int(8192 // SQUARE)
        sq = {(i, j): [] for i in range(per) for j in range(per)}
        settled = set()
        refs, _h = db.cell_refs('#' + ck)
        # (wild cells only: a town's or a farm's cell is half as green, and the land being dressed is wild; learnt
        # from every cell, West Gash came out at 8 trees a cell against the wild land's 16, lab jdec1 2026-10-29)
        if any(not ref_info(r['subs'])[3] and _tag(db, ref_info(r['subs'])[0], memo) in ('DOOR', 'NPC_') for r in refs.values()):
            used -= 1
            continue
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead:
                continue
            low = rid.lower()
            i, j = int((pos[0] - gx * 8192.0) // SQUARE), int((pos[1] - gy * 8192.0) // SQUARE)
            if (i, j) not in sq:
                continue
            if low not in memo:
                ri = db.resolve_id(rid)
                memo[low] = (db.recs[ri][0], db.recs[ri][1], mapdata.object_bounds(db, ri)) if ri is not None else None
            info = memo[low]
            if not info:
                continue
            tag, real, b = info
            k = kind_of(low)
            if k and tag in ('STAT', 'ACTI', 'CONT'):
                g = hat(pos[0], pos[1])
                if g is None:
                    continue
                sq[(i, j)].append([real, round(pos[0] - gx * 8192.0 - i * SQUARE, 1), round(pos[1] - gy * 8192.0 - j * SQUARE, 1),
                                   round(pos[2] - g, 1), round(pos[3], 3), round(pos[4], 3), round(pos[5], 3), round(sc or 1.0, 2)])
                continue
            import cliffrocks
            if cliffrocks.is_rock(low) or tag in ('LIGH', 'MISC', 'INGR', 'ALCH', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'LEVI'):
                continue
            # (a building, a door, a person, a big thing that doesn't grow: the square is settled)
            big = b and max(b[3] - b[0], b[4] - b[1]) * (sc or 1.0) >= SETTLED
            if tag in ('DOOR', 'NPC_', 'CREA', 'LEVC') or big:
                settled.add((i, j))
        for (i, j), items in sq.items():
            if (i, j) in settled:
                continue
            gr = _square_ground(hat, gx * 8192.0 + i * SQUARE, gy * 8192.0 + j * SQUARE)
            if not gr or gr[1] <= 0:
                continue
            lst = squares.setdefault(ground_key(*gr), [])
            if len(lst) < KEEP:
                lst.append(items)
                grown += bool(items)
    out = {'squares': squares, 'grown': grown, 'cells': used}
    _mem[key] = out
    disk[region] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(disk, f)
    except OSError:
        pass
    return out


def _nearby_keys(key):
    """Ground keys to try for a square with no example: the same, then a slope band off, then a height band off,
    then the water the other way."""
    s, h, w = (int(v) for v in key.split(','))
    out = [key]
    for ds, dh, dw in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (1, 1, 0), (-1, -1, 0), (0, 0, 1), (2, 0, 0), (-2, 0, 0), (0, 2, 0), (0, -2, 0)):
        out.append('%d,%d,%d' % (s + ds, h + dh, w ^ dw))
    return out


def plan_growth(db, F, inside, hold, region_of, amount=1.0, seed=1, used=None):
    """What grows over the field's land: [{id, x, y, z, rx, ry, rz, s}], square by square one of the game's own
    squares of the same ground in the region region_of(x, y) gives."""
    import cliffrocks
    rng = random.Random(seed * 104729 + 7)
    libs = {}
    out = []
    hat = lambda x, y: cliffrocks._height(F, x, y)
    x0 = math.floor(F.ox / SQUARE) * SQUARE
    y0 = math.floor(F.oy / SQUARE) * SQUARE
    x1, y1 = F.ox + (F.w - 1) * F.step, F.oy + (F.h - 1) * F.step

    def ok(x, y):
        fx, fy = int(round((x - F.ox) / F.step)), int(round((y - F.oy) / F.step))
        if not (0 <= fx < F.w and 0 <= fy < F.h):
            return False
        i = fy * F.w + fx
        return inside[i] and not (hold and hold[i])
    y = y0
    while y < y1:
        x = x0
        while x < x1:
            if ok(x + SQUARE / 2, y + SQUARE / 2) or ok(x, y) or ok(x + SQUARE, y + SQUARE):
                regs = region_of(x + SQUARE / 2, y + SQUARE / 2)
                gr = _square_ground(hat, x, y)
                pool = None
                if gr and gr[1] > 0:
                    # (the cell's look first; where it has no ground like this square's, the next region's: the Sea of
                    # Ghosts' land is low islets, and a raised island's high slopes found nothing, lab 2026-10-29)
                    for reg in ([regs] if isinstance(regs, str) else regs):
                        if reg not in libs:
                            libs[reg] = learn(db, reg)['squares']
                        lib = libs[reg]
                        pool = next((lib[k] for k in _nearby_keys(ground_key(*gr)) if lib.get(k)), None)
                        if pool:
                            if used is not None:
                                used[reg] = used.get(reg, 0) + 1
                            break
                if pool:
                    if True:
                        picks = [rng.choice(pool)]
                        if amount > 1 and rng.random() < amount - 1:
                            picks.append(rng.choice(pool))
                        turn = rng.randrange(4) * math.pi / 2       # (a square turned a quarter, or not: more variety)
                        c, sn = math.cos(turn), math.sin(turn)
                        for items in picks:
                            for it in items:
                                if amount < 1 and rng.random() > amount:
                                    continue
                                rid, dx, dy, dz, rx, ry, rz, s = it
                                cx, cy = dx - SQUARE / 2, dy - SQUARE / 2
                                wx, wy = x + SQUARE / 2 + cx * c - cy * sn, y + SQUARE / 2 + cx * sn + cy * c
                                if not ok(wx, wy):
                                    continue
                                g = hat(wx, wy)
                                if g is None or g <= 8:
                                    continue
                                out.append({'id': rid, 'x': round(wx, 1), 'y': round(wy, 1), 'z': round(g + dz, 1), 'rx': rx, 'ry': ry,
                                            'rz': round((rz + turn) % (2 * math.pi), 3), 's': s})
            x += SQUARE
        y += SQUARE
    return out


def _grows(db, region):
    return learn(db, region)['grown']


def _broad(db, region):
    return sum(len(v) for v in learn(db, region)['squares'].values()) >= BROAD


def nearest_lands(db, gx, gy, ok, n, reach=20):
    """Up to n regions passing ok(region), by their nearest cell to (gx, gy) within reach, the nearest first."""
    import regions
    best = {}
    for k, reg in regions.region_map(db).items():
        if not reg:
            continue
        x, y = (int(v) for v in k.split(','))
        d = (x - gx) ** 2 + (y - gy) ** 2
        if d <= reach * reach and (reg not in best or d < best[reg]):
            best[reg] = d
    out = []
    for reg in sorted(best, key=best.get):
        if ok(reg):
            out.append(reg)
            if len(out) >= n:
                break
    return out


def nearest_land(db, gx, gy, ok, reach=14):
    """The region of the nearest cell (within reach) whose region passes ok(region)."""
    import regions
    rmap = regions.region_map(db)
    seen, best = {}, None
    for k, reg in rmap.items():
        if not reg:
            continue
        x, y = (int(v) for v in k.split(','))
        d = (x - gx) ** 2 + (y - gy) ** 2
        if d > reach * reach or (best and d >= best[0]):
            continue
        if reg not in seen:
            seen[reg] = ok(reg)
        if seen[reg]:
            best = (d, reg)
    return best[1] if best else ''


def _in_outline(F, inside, outline):
    """inside, kept only within a closed outline of world points (even-odd)."""
    if not outline or len(outline) < 3:
        return inside
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    out = bytearray(len(inside))
    n = len(outline)
    for i in F.near(min(xs), min(ys), max(xs), max(ys)):
        if not inside[i]:
            continue
        x, y = F.world(i)
        c = False
        for k in range(n):
            (ax, ay), (bx, by) = outline[k], outline[(k + 1) % n]
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax:
                c = not c
        if c:
            out[i] = 1
    return out


def dress_all(db, cells, like='', parts=None, seed=None, outline=None):
    """The marked cells' land (or the part within outline) dressed as the game dresses the region's: rocks and
    cliffs (cliffrocks) and what grows (plan_growth), each part {'rocks': amount, 'growth': amount} (0: not), as
    one Undo step. like: a region for all; '' takes each cell's own region, or, where it has little land of its own
    (the open sea), the nearest land's."""
    import cliffrocks
    import editing
    import landrange
    parts = parts or {'rocks': 1.0, 'growth': 1.0}
    want, F, inside, hold = cliffrocks.area(db, cells)
    inside = _in_outline(F, inside, outline)
    if not any(inside):
        raise editing.EditError('No marked land inside that outline.')
    seed = int(seed) if seed is not None else random.randrange(1, 1 << 30)
    looks, chains = {}, {}
    for gx, gy in want:
        if like:
            looks[(gx, gy)] = like.lower()
            chains[(gx, gy)] = [like.lower()] + nearest_lands(db, gx, gy, lambda r: _broad(db, r), FALLBACKS)
            continue
        # (a region with little land of its own, the open sea's, isn't the look: the nearest with land is. The Sea of
        # Ghosts' islets are bare, and a raised island took 14 things from them, lab 2026-10-29)
        reg = landrange._region_of(db, gx, gy)
        if _grows(db, reg) < ENOUGH or not _broad(db, reg):
            reg = (nearest_lands(db, gx, gy, lambda r: _broad(db, r) and _grows(db, r) >= ENOUGH, 1) or [reg])[0]
        looks[(gx, gy)] = reg
        chains[(gx, gy)] = [reg] + [r for r in nearest_lands(db, gx, gy, lambda r: _broad(db, r), FALLBACKS + 1) if r != reg][:FALLBACKS]
    region_of = lambda x, y: chains.get((math.floor(x / 8192.0), math.floor(y / 8192.0)), [''])
    rocks = grown = 0
    if float(parts.get('growth') or 0) > 0:
        from_ = {}
        items = plan_growth(db, F, inside, hold, region_of, float(parts['growth']), seed, from_)
        # (the looks the squares came from, the most used first)
        for reg in sorted(from_, key=lambda r: -from_[r]):
            if reg not in looks.values():
                looks[('from', reg)] = reg
        grown = cliffrocks.place(db, items)
        # (nothing new where a tree now stands: the rocks keep clear of it)
        for it in items:
            for i in F.near(it['x'] - 96, it['y'] - 96, it['x'] + 96, it['y'] + 96):
                hold[i] = 1
    if float(parts.get('rocks') or 0) > 0:
        r = cliffrocks.dress(db, cells, '', float(parts['rocks']), seed, commit=False, prepared=(want, F, inside, hold), looks_of=looks)
        rocks = r['rocks']
    db.sync_project()
    if rocks or grown:
        what = ' and '.join(w for w in ('%d rocks' % rocks if rocks else '', '%d trees and plants' % grown if grown else '') if w)
        editing.commit(db, 'Dressed %d cell%s with %s' % (len(want), '' if len(want) == 1 else 's', what))
    names = []
    for reg in sorted(set(looks.values())):
        ri = db.resolve_id(reg)
        names.append((db.recs[ri][2] or db.recs[ri][1]) if ri is not None else reg)
    return {'rocks': rocks, 'growth': grown, 'cells': len(want), 'looks': names, 'seed': seed}
