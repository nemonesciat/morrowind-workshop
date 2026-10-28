"""Rocks on a land plan's slopes and cliffs, the way the game sets them (packaging/landscaping-plan.md, the rock
stage). The game's land is heights on a 128-unit grid: it can't overhang, and its textures stretch on steep
ground, so the game covers its cliffs with rock models. What this learns, a region at a time, from the game's own
cells:

  how thickly rocks stand on ground of each steepness (rocks over the area of land in 0-15, 15-30, 30-45, 45-60
  and over 60 degrees: the steeper, the more), which rocks (by how often each is used on such ground), their
  sizes, how deep they are sunk and how far they lean

A rock's ground is the steepness at its middle. Then plan_rocks() sets rocks over the plan's own ground by those
figures, point by point (every 128 units), so they gather on the faces as the game's do."""
import hashlib
import json
import math
import os
import random

import mapdata

VERSION = 2
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
    bmemo = {}
    used = 0
    for ck in cells:
        gx, gy = (int(v) for v in ck.split(','))
        L = mapdata.land(db, gx, gy)
        if not L.get('exists'):
            continue
        H = L['h']
        sl = _slopes(H)
        used += 1
        for i, s in enumerate(sl):
            if s is not None and H[i] > 0:
                area[_band(s)] += 128.0 * 128.0
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
            st = stats[k].setdefault(low, {'id': info[2], 'name': info[3] or '', 'n': 0, 'scales': [], 'sinks': [], 'tilts': [],
                                           'zmin': round(b[2], 1), 'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])]})
            st['n'] += 1
            if len(st['scales']) < 60:
                st['scales'].append(sc)
                st['sinks'].append((g - (pos[2] + b[2] * sc)) / sc)
                st['tilts'].append(_tilt(pos))
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
                          'tilt_share': round(len(lean) / len(tl), 2) if tl else 0.0})
        bands.append({'from': BANDS[k], 'to': BANDS[k + 1], 'area': round(area[k]), 'n': nb[k],
                      'per_mu': round(nb[k] / area[k] * 1e6, 3) if area[k] > 0 else 0.0, 'items': items})
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


def plan_rocks(db, F, inside, weight, region_of, amount=1.0, seed=1, hold=None):
    """The rocks for the plan's ground: [{id, x, y, z, rx, ry, rz, s}]. Over every 512-unit patch of the plan's own
    ground (weight 0.5 or more: the plan made it), above the water and not where ground is held under a building:
    the region's rocks for that steepness, as thickly as the game sets them (times amount), each on the steepest
    of three spots tried in the patch, none on top of another. region_of(x, y): the region whose rocks go there."""
    rng = random.Random(seed * 7919 + 13)
    k = max(1, int(round(512.0 / F.step)))
    figs = {}
    out, taken = [], {}
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
                    band = R['bands'][_band(sl)]
                    if band['items'] and band['per_mu'] > 0:
                        spots.append((band['per_mu'] * 128.0 * 128.0 / 1e6 * amount, x, y, band))
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
                _w, x, y, band = sp
                x, y = x + (rng.random() - 0.5) * 128, y + (rng.random() - 0.5) * 128
                total = sum(it['n'] for it in band['items'])
                pick = rng.random() * total
                it = band['items'][0]
                for c in band['items']:
                    pick -= c['n']
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
