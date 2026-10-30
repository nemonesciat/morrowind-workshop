"""Rocks on a land plan's slopes and cliffs, the way the game sets them (packaging/landscaping-plan.md, the rock
stage). The game's land is heights on a 128-unit grid: it can't overhang, and its textures stretch on steep
ground, so the game covers its cliffs with rock models. What this learns, a region at a time, from the game's own
cells:

  how thickly rocks stand on ground of each steepness (rocks over the area of land in 0-15, 15-30, 30-45, 45-60
  and over 60 degrees: the steeper, the more), which rocks (by how often each is used on such ground), their
  sizes, how deep they are sunk and how far they lean

A rock's ground is the steepness at its middle. Then plan_rocks() sets rocks over the plan's own ground by those
figures, point by point (every 128 units), so they gather on the faces as the game's do.

Since v3 (the user, 2026-10-29: the game's rocks and cliffs give land its character and make the overhangs; land
dressed at random looks barren) each rock is also learnt whole, as the game set it against its slope: its turn
from the way downhill, its tilt, how high its origin stands over the ground and its size, and where on the slope
it stands (the foot, the face or the crest, by its height among the ground around it). A rock is laid in one of
those poses turned to its own slope, so a cliff piece faces out over the drop, and the crest's pieces hang over
it, the way the game's do."""
import hashlib
import json
import math
import os
import random

import mapdata

VERSION = 3
BANDS = (0.0, 15.0, 30.0, 45.0, 60.0, 91.0)
WORDS = ('rock', 'stone', 'boulder', 'cliff', 'crag')
NOT = ('road', 'wall', 'bridge', 'arch', 'cave', 'entr', 'menhir', 'door', 'sign', 'ruin', 'shrine', 'pillar', 'stair',
       'gate', 'tower', 'house', 'kelp', 'coral', 'lily', 'stoneflower', 'flora', 'plant', 'grave', 'tomb', 'dock',
       'pier', 'fence', 'well', 'statue', 'altar', 'table', 'chair', 'shelf', 'pebble')
_mem = {}


def _band(deg):
    for k in range(len(BANDS) - 1):
        if deg < BANDS[k + 1]:
            return k
    return len(BANDS) - 2


def is_rock(low):
    return any(w in low for w in WORDS) and not any(w in low for w in NOT)


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'cliffrocks_%s_v%d.json' % (_sig(db), VERSION))


def _slopes(H):
    """Slope in degrees at each inner point of a 65 x 65 height grid (None at the edge)."""
    out = [None] * (65 * 65)
    for y in range(1, 64):
        for x in range(1, 64):
            i = y * 65 + x
            gx = (H[i + 1] - H[i - 1]) / 256.0
            gy = (H[i + 65] - H[i - 65]) / 256.0
            out[i] = math.degrees(math.atan(math.hypot(gx, gy)))
    return out


# where on its slope a spot stands, by its height among the ground within REACH: the lowest third the foot, the
# highest the crest (a spot with less than FLAT of rise round it is the face of nothing: 'face')
FOOT, FACE, CREST = 0, 1, 2
REACH = 4                       # points (128 each) every way: 512 units
FLAT = 48.0
ASPECT_MIN = 8.0                # degrees: flatter ground has no way downhill to turn a rock by
POSES = 40                      # poses kept a rock and steepness


def _place_of(g, lo, hi):
    if hi - lo < FLAT:
        return FACE
    r = (g - lo) / (hi - lo)
    return FOOT if r < 1 / 3.0 else CREST if r > 2 / 3.0 else FACE


def _places(H):
    """Where on its slope each inner point of a 65 x 65 grid stands (FOOT, FACE, CREST; None at the edge)."""
    out = [None] * (65 * 65)
    for y in range(1, 64):
        for x in range(1, 64):
            ys, xs = range(max(0, y - REACH), min(64, y + REACH) + 1), range(max(0, x - REACH), min(64, x + REACH) + 1)
            win = [H[yy * 65 + xx] for yy in ys for xx in xs]
            out[y * 65 + x] = _place_of(H[y * 65 + x], min(win), max(win))
    return out


def _downhill(gx, gy):
    """The turn (rz) that points a thing's own +Y the way downhill, for the gradient (gx, gy): a thing turned by
    rz has its +Y along (sin rz, cos rz), as adjacency.to_world has it."""
    return math.atan2(-gx, -gy)


def _tilt(pos):
    a = max(abs(math.degrees(pos[3])) % 360, abs(math.degrees(pos[4])) % 360)
    return min(a, 360 - a)


def learn(db, region, sample=90):
    """The region's figures: {'bands': [{area, n, per_mu (rocks a million square units), items: [...]}], 'cells'}.
    Read from up to `sample` of its cells (spread over it), cached on disk by the load order."""
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
    from project import ref_info
    rmap = regions.region_map(db)
    cells = sorted((k for k, r in rmap.items() if r == region), key=lambda k: hashlib.md5(k.encode()).hexdigest())[:sample]
    area = [0.0] * (len(BANDS) - 1)
    stats = [dict() for _ in area]
    nb = [0] * len(area)
    parea = [[0.0, 0.0, 0.0] for _ in area]          # (by steepness and place on the slope)
    pnb = [[0, 0, 0] for _ in area]
    bmemo = {}
    used = 0
    for ck in cells:
        gx, gy = (int(v) for v in ck.split(','))
        L = mapdata.land(db, gx, gy)
        if not L.get('exists'):
            continue
        H = L['h']
        sl = _slopes(H)
        pl = _places(H)
        used += 1
        for i, s in enumerate(sl):
            if s is not None and H[i] > 0:
                area[_band(s)] += 128.0 * 128.0
                parea[_band(s)][pl[i]] += 128.0 * 128.0
        refs, _h = db.cell_refs('#' + ck)
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead:
                continue
            low = rid.lower()
            if not is_rock(low):
                continue
            if low not in bmemo:
                ri = db.resolve_id(rid)
                bmemo[low] = (mapdata.object_bounds(db, ri), db.recs[ri][0], db.recs[ri][1], db.recs[ri][2]) if ri is not None else None
            info = bmemo[low]
            if not info or not info[0] or info[1] != 'STAT':
                continue
            b = info[0]
            sc = sc or 1.0
            fx, fy = (pos[0] - gx * 8192.0) / 128.0, (pos[1] - gy * 8192.0) / 128.0
            if not (1 <= fx < 63 and 1 <= fy < 63):
                continue
            # (the steepness at its middle, as place() reads the plan's ground: filed by the steepest ground under
            # its whole width, the figures didn't add up when laid point by point, lab 2026-10-28)
            x0_, y0_ = int(fx), int(fy)
            tx, ty = fx - x0_, fy - y0_
            j = y0_ * 65 + x0_
            g = (H[j] * (1 - tx) + H[j + 1] * tx) * (1 - ty) + (H[j + 65] * (1 - tx) + H[j + 66] * tx) * ty
            if g <= 0 or None in (sl[j], sl[j + 1], sl[j + 65], sl[j + 66]):
                continue
            steep = (sl[j] * (1 - tx) + sl[j + 1] * tx) * (1 - ty) + (sl[j + 65] * (1 - tx) + sl[j + 66] * tx) * ty
            if g <= 0:
                continue
            k = _band(steep)
            nb[k] += 1
            # (where on the slope, and the way downhill, at the nearest point)
            jn = int(round(fy)) * 65 + int(round(fx))
            plc = pl[jn] if pl[jn] is not None else FACE
            pnb[k][plc] += 1
            st = stats[k].setdefault(low, {'id': info[2], 'name': info[3] or '', 'n': 0, 'scales': [], 'sinks': [], 'tilts': [],
                                           'zmin': round(b[2], 1), 'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])],
                                           'poses': [], 'at': [0, 0, 0]})
            st['n'] += 1
            st['at'][plc] += 1
            if len(st['scales']) < 60:
                st['scales'].append(sc)
                st['sinks'].append((g - (pos[2] + b[2] * sc)) / sc)
                st['tilts'].append(_tilt(pos))
            if len(st['poses']) < POSES:
                ggx, ggy = (H[jn + 1] - H[jn - 1]) / 256.0, (H[jn + 65] - H[jn - 65]) / 256.0
                turn = None
                if math.degrees(math.atan(math.hypot(ggx, ggy))) >= ASPECT_MIN:
                    turn = round(((pos[5] - _downhill(ggx, ggy)) + math.pi) % (2 * math.pi) - math.pi, 3)
                # [rx, ry, turn from downhill (None: any), origin over the ground, scale, place]
                st['poses'].append([round(pos[3], 3), round(pos[4], 3), turn, round(pos[2] - g, 1), round(sc, 2), plc])
    bands = []
    for k in range(len(area)):
        items = []
        for v in sorted(stats[k].values(), key=lambda v: -v['n'])[:16]:
            if v['n'] < 2:
                continue
            sc, sk, tl = sorted(v['scales']), sorted(v['sinks']), sorted(v['tilts'])
            lean = [t for t in tl if 1.0 <= t <= 60]
            items.append({'id': v['id'], 'name': v['name'], 'n': v['n'], 'size': v['size'], 'zmin': v['zmin'],
                          'smin': round(sc[len(sc) // 10], 2), 'smax': round(sc[min(len(sc) - 1, len(sc) * 9 // 10)], 2),
                          # (sunk as the game sinks it, its median; never more than most of its height)
                          'sink': round(max(0.0, min(sk[len(sk) // 2], v['size'][2] * 0.7)), 1),
                          'tilt': round(lean[min(len(lean) - 1, len(lean) * 8 // 10)], 1) if lean else 0.0,
                          'tilt_share': round(len(lean) / len(tl), 2) if tl else 0.0,
                          'at': v['at'], 'poses': v['poses']})
        bands.append({'from': BANDS[k], 'to': BANDS[k + 1], 'area': round(area[k]), 'n': nb[k],
                      'per_mu': round(nb[k] / area[k] * 1e6, 3) if area[k] > 0 else 0.0, 'items': items,
                      # (rocks a million square units at the foot, on the face and at the crest of such ground)
                      'per_place': [round(pnb[k][p] / parea[k][p] * 1e6, 3) if parea[k][p] > 0 else 0.0 for p in range(3)]})
    out = {'region': region, 'cells': used, 'bands': bands}
    _mem[key] = out
    disk[region] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(disk, f)
    except OSError:
        pass
    return out


def _height(F, x, y):
    fx, fy = (x - F.ox) / F.step, (y - F.oy) / F.step
    ix, iy = int(fx), int(fy)
    if not (0 <= ix < F.w - 1 and 0 <= iy < F.h - 1):
        return None
    tx, ty = fx - ix, fy - iy
    i = iy * F.w + ix
    z = F.z
    return (z[i] * (1 - tx) + z[i + 1] * tx) * (1 - ty) + (z[i + F.w] * (1 - tx) + z[i + F.w + 1] * tx) * ty


def _slope_at(F, x, y):
    d = F.step
    a, b, c, e = _height(F, x + d, y), _height(F, x - d, y), _height(F, x, y + d), _height(F, x, y - d)
    if None in (a, b, c, e):
        return None
    return math.degrees(math.atan(math.hypot((a - b) / (2 * d), (c - e) / (2 * d))))


def _grad_at(F, x, y):
    d = F.step
    a, b, c, e = _height(F, x + d, y), _height(F, x - d, y), _height(F, x, y + d), _height(F, x, y - d)
    if None in (a, b, c, e):
        return None
    return (a - b) / (2 * d), (c - e) / (2 * d)


def _place_at(F, x, y):
    """Where on its slope a spot of the field stands (as _places reads the game's: its height among the ground
    within 512 units)."""
    g = _height(F, x, y)
    if g is None:
        return FACE
    hs = [g]
    for dx in (-512, -256, 0, 256, 512):
        for dy in (-512, -256, 0, 256, 512):
            h = _height(F, x + dx, y + dy)
            if h is not None:
                hs.append(h)
    return _place_of(g, min(hs), max(hs))


BAND_MIN = 8                    # rocks a steepness needs in the region's land to be its own


def _band_for(R, k):
    """The region's figures for steepness band k, or, where it set fewer than BAND_MIN rocks on such ground (the Sea
    of Ghosts has none over 60 degrees, and an island's cliff stayed bare), the nearest steepness it did, the
    steeper first among equals."""
    bands = R['bands']
    if bands[k]['n'] >= BAND_MIN:
        return bands[k]
    for d in range(1, len(bands)):
        for j in (k - d, k + d):
            if 0 <= j < len(bands) and bands[j]['n'] >= BAND_MIN:
                return bands[j]
    return bands[k]


FLOAT_MAX = 32                  # a laid rock's lowest corner may stand this far over the ground under it, no more
SETTLE_SINK = 16                # (and one let down onto the ground sinks this far into it)


def _lowest(F, r, b):
    """The ground under a laid rock's lowest corner (its box turned as it's turned), minus that corner's height:
    over 0 it floats there."""
    s = r['s']
    cx, sx, cy, sy, cz, sz = (math.cos(-r['rx']), math.sin(-r['rx']), math.cos(-r['ry']), math.sin(-r['ry']),
                              math.cos(-r['rz']), math.sin(-r['rz']))
    best = None
    for x in (b[0], b[3]):
        for y in (b[1], b[4]):
            for z in (b[2], b[5]):
                y1, z1 = y * s * cx - z * s * sx, y * s * sx + z * s * cx
                x2, z2 = x * s * cy + z1 * sy, -x * s * sy + z1 * cy
                wx, wy = r['x'] + x2 * cz - y1 * sz, r['y'] + x2 * sz + y1 * cz
                if best is None or r['z'] + z2 < best[2]:
                    best = (wx, wy, r['z'] + z2)
    g = _height(F, best[0], best[1])
    return None if g is None else best[2] - g


def _posed(F, it, x, y, g, plc, rng):
    """A rock laid as the game laid one of it on such ground: one of its poses (one at this place on the slope if
    it has any), turned to this spot's own way downhill. {rx, ry, rz, z, s}, or None for a rock learnt with none."""
    poses = it.get('poses') or []
    if not poses:
        return None
    here = [p for p in poses if p[5] == plc] or poses
    rx, ry, turn, dz, s0, _plc = here[rng.randrange(len(here))]
    gr = _grad_at(F, x, y)
    if turn is None or gr is None or math.degrees(math.atan(math.hypot(*gr))) < ASPECT_MIN:
        rz = rng.random() * 2 * math.pi
    else:
        rz = (_downhill(*gr) + turn + (rng.random() - 0.5) * 0.3) % (2 * math.pi)
    s = max(0.5, min(2.0, s0 * (0.92 + rng.random() * 0.16)))
    return {'rx': rx, 'ry': ry, 'rz': rz, 'z': g + dz * s / s0, 's': round(s, 2)}


def plan_rocks(db, F, inside, weight, region_of, amount=1.0, seed=1, hold=None):
    """The rocks for the plan's ground: [{id, x, y, z, rx, ry, rz, s}]. Over every 512-unit patch of the plan's own
    ground (weight 0.5 or more: the plan made it), above the water and not where ground is held under a building:
    the region's rocks for that steepness, as thickly as the game sets them (times amount), each on the steepest
    of three spots tried in the patch, none on top of another. region_of(x, y): the region whose rocks go there."""
    rng = random.Random(seed * 7919 + 13)
    k = max(1, int(round(512.0 / F.step)))
    figs = {}
    out, taken = [], {}
    bounds = {}
    for py in range(0, F.h - k, k):
        for px in range(0, F.w - k, k):
            i = (py + k // 2) * F.w + px + k // 2
            if not inside[i] or weight[i] < 0.5 or F.z[i] <= 16 or (hold and hold[i]):
                continue
            x0, y0 = F.world(py * F.w + px)
            reg = region_of(x0 + 256, y0 + 256)
            if reg not in figs:
                figs[reg] = learn(db, reg)
            R = figs[reg]
            # (the patch's 16 spots every 128 units, each as thick with rocks as the game's ground of its steepness:
            # by the middle's steepness alone, the plan came out a half short on its cliffs, lab 2026-10-28)
            spots = []
            for sy in range(4):
                for sx in range(4):
                    x, y = x0 + 64 + sx * 128, y0 + 64 + sy * 128
                    sl = _slope_at(F, x, y)
                    if sl is None:
                        continue
                    band = _band_for(R, _band(sl))
                    # (as thick as the game's rocks at that place on such a slope: the foot, the face or the crest)
                    plc = _place_at(F, x, y)
                    dens = band['per_place'][plc] if band.get('per_place') else band['per_mu']
                    if band['items'] and dens > 0:
                        spots.append((dens * 128.0 * 128.0 / 1e6 * amount, x, y, band, plc))
            want = sum(sp[0] for sp in spots)
            if not want:
                continue
            n = int(want) + (1 if rng.random() < want - int(want) else 0)
            for _ in range(n):
                pick = rng.random() * want
                sp = spots[-1]
                for c in spots:
                    pick -= c[0]
                    if pick <= 0:
                        sp = c
                        break
                _w, x, y, band, plc = sp
                x, y = x + (rng.random() - 0.5) * 128, y + (rng.random() - 0.5) * 128
                # (the rocks the game sets at that place on such a slope, the more it sets there the likelier)
                wt = [(c['at'][plc] + 0.25) if c.get('at') else c['n'] for c in band['items']]
                pick = rng.random() * sum(wt)
                it = band['items'][0]
                for c, w_ in zip(band['items'], wt):
                    pick -= w_
                    if pick <= 0:
                        it = c
                        break
                s = it['smin'] + rng.random() * max(0.0, it['smax'] - it['smin'])
                # (only not one in another's middle: the game overlaps its cliff rocks to cover the face, and kept a
                # third of their width apart the plan's cliffs had half the game's rocks, lab 2026-10-28)
                r = max(it['size'][0], it['size'][1]) * s * 0.12
                cx, cy = int(x // 512), int(y // 512)
                if any(math.hypot(x - ox, y - oy) < r + orr for gx_ in (cx - 1, cx, cx + 1) for gy_ in (cy - 1, cy, cy + 1)
                       for ox, oy, orr in taken.get((gx_, gy_), ())):
                    continue
                g = _height(F, x, y)
                if g is None or g <= 16:
                    continue
                ps = _posed(F, it, x, y, g, plc, rng)
                if ps:
                    r_ = dict(ps, id=it['id'], x=x, y=y)
                    # (a pose the game used for a rock on another rock floats on bare ground: let down onto it.
                    # Druadach's p90 lowest corner stood 491 over the ground, the game's 91, lab 2026-10-29)
                    low = it['id'].lower()
                    if low not in bounds:
                        bounds[low] = mapdata.object_bounds(db, db.resolve_id(it['id']))
                    if bounds[low]:
                        gap = _lowest(F, r_, bounds[low])
                        if gap is not None and gap > FLOAT_MAX:
                            r_['z'] -= gap + SETTLE_SINK
                    out.append(r_)
                else:
                    lean = math.radians(it['tilt']) if it['tilt'] and rng.random() < it['tilt_share'] else 0.0
                    out.append({'id': it['id'], 'x': x, 'y': y, 'z': g - it['sink'] * s - it['zmin'] * s,
                                'rx': (rng.random() * 2 - 1) * lean, 'ry': (rng.random() * 2 - 1) * lean,
                                'rz': rng.random() * 2 * math.pi, 's': round(s, 2)})
                taken.setdefault((cx, cy), []).append((x, y, r))
    return out


def place(db, rocks):
    """The rocks into the mod's cells (no Undo step of their own: the land plan's apply makes one for all)."""
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
            continue                              # (a cell with no record: open sea the plan left as sea)
        rk = db.project.new_ref_key()
        pos = (r['x'], r['y'], r['z'], r['rx'], r['ry'], r['rz'])
        editing._store(c, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], pos, r['s']))
        made += 1
    return made


# ---------------------------------------------------------------- dressing land that's there already

ENOUGH = 30                     # rocks a region's sampled cells must have to be its own look; fewer, and the nearest
                                # region with more stands in (the Sea of Ghosts has hardly any land of its own)
HOLD_PAD = 96                   # units round a thing already standing where no rock goes


def _rocky(db, region):
    R = learn(db, region)
    return sum(b['n'] for b in R['bands'])


def area(db, cells):
    """The marked cells' land as a field: (cells with land, F, inside, hold). hold: the points where something stands
    already (a building, a tree, a rock: nothing new goes there)."""
    import editing
    import landrange
    import landshapes
    from project import ref_info
    editing._require_project(db)
    keys = sorted({tuple(int(v) for v in str(c).split(',')) for c in cells or []})
    if not keys:
        raise editing.EditError('Mark the cells to dress first.')
    if len(keys) > 64:
        raise editing.EditError('That is a lot of land at once: dress up to 64 cells a time.')
    x0, y0 = min(k[0] for k in keys), min(k[1] for k in keys)
    x1, y1 = max(k[0] for k in keys), max(k[1] for k in keys)
    G = landrange.Grid(db, x0, y0, x1, y1)
    F = landshapes.Field(G, 1)
    want = set(keys) & G.land
    if not want:
        raise editing.EditError('There is no land in those cells.')
    n = F.w * F.h
    inside = bytearray(n)
    for i in range(n):
        x, y = F.world(i)
        if (math.floor(x / 8192.0), math.floor(y / 8192.0)) in want:
            inside[i] = 1
    hold = bytearray(n)
    for gx, gy in want:
        refs, _h = db.cell_refs('#%d,%d' % (gx, gy))
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead:
                continue
            ri = db.resolve_id(rid)
            b = mapdata.object_bounds(db, ri) if ri is not None else None
            if not b:
                continue
            r = max(b[3] - b[0], b[4] - b[1]) * (sc or 1.0) / 2.0 + HOLD_PAD
            for i in F.near(pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r):
                hold[i] = 1
    return want, F, inside, hold


def dress(db, cells, like='', amount=1.0, seed=None, commit=True, prepared=None, looks_of=None):
    """Rocks and cliffs over land as it is now (land shaped by hand, an island raised from the sea): the game's rocks
    of the region (or the one asked for, like) at each steepness and place on the slope, turned to the slope as the
    game turns them, in one Undo step. cells: ['gx,gy']. Not on water, or where something stands already (a
    building, a tree, another rock). prepared: area()'s, when the caller has it; looks_of: {cell: region}."""
    import editing
    import landrange
    want, F, inside, hold = prepared or area(db, cells)
    weight = [1.0] * (F.w * F.h)
    # (the look: the one asked for, else each cell's own region, else the nearest rocky one)
    looks = {}
    for gx, gy in want:
        reg = (looks_of or {}).get((gx, gy)) or (like or '').lower() or landrange._region_of(db, gx, gy)
        if not like and _rocky(db, reg) < ENOUGH:
            reg = _nearest_rocky(db, gx, gy) or reg
        looks[(gx, gy)] = reg
    region_of = lambda x, y: looks.get((math.floor(x / 8192.0), math.floor(y / 8192.0)), '')
    rng_seed = int(seed) if seed is not None else random.randrange(1, 1 << 30)
    rocks = plan_rocks(db, F, inside, weight, region_of, float(amount), rng_seed, hold)
    made = place(db, rocks)
    db.sync_project()
    used = sorted(set(looks.values()))
    if made and commit:
        editing.commit(db, 'Dressed %d cell%s with %d rocks' % (len(want), '' if len(want) == 1 else 's', made))
    return {'rocks': made, 'cells': len(want), 'looks': used, 'seed': rng_seed, 'placed': rocks}


def _nearest_rocky(db, gx, gy):
    """The region of the nearest cell (within 12) whose region the game dresses with rocks."""
    import regions
    rmap = regions.region_map(db)
    seen = {}
    best = None
    for k, reg in rmap.items():
        if not reg:
            continue
        x, y = (int(v) for v in k.split(','))
        d = (x - gx) ** 2 + (y - gy) ** 2
        if d > 144 or (best and d >= best[0]):
            continue
        if reg not in seen:
            seen[reg] = _rocky(db, reg) >= ENOUGH
        if seen[reg]:
            best = (d, reg)
    return best[1] if best else ''


def looks(db):
    """The regions for the Like list: [{region, name, cells}], the largest first. Nothing is learnt here (the first
    time over every region took three minutes): a region's rocks are learnt when it's first dressed with."""
    import regions
    n = {}
    for reg in regions.region_map(db).values():
        if reg:
            n[reg] = n.get(reg, 0) + 1
    out = []
    for reg, c in n.items():
        if c < 4:
            continue
        ri = db.resolve_id(reg)
        out.append({'region': reg, 'name': (db.recs[ri][2] or db.recs[ri][1]) if ri is not None else reg, 'cells': c})
    return sorted(out, key=lambda o: o['name'].lower())
