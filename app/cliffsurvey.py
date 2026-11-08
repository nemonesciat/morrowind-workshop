"""How the game clads its steep ground in rock: the survey behind the rock-face pass (rockface.py).

The user's lesson (2026-11-08, a gorge in the Mephalan Vales with its rock statics shown and then hidden): the naked
terrain under them "looks like many of the terrains we generate"; the rocks are what make it a gorge. And a rock's
naked bottom edge is never exposed from any vantage point: it is under the dirt, or inside another rock.

Read from up to SAMPLE exterior cells of each region (spread over it, cached by the load order like the other
surveys), for every rock or cliff piece MIN_SIZE or more across:

  by the steepness of the ground under it (the bands of cliffrocks: 0-15, 15-30, 30-45, 45-60, 60+ degrees):
    how many a million square units of such ground (per_k), which pieces (with the poses the game set them in,
    as cliffrocks learns them: turn from downhill, tilt, origin over the ground, scale, place on the slope), their
    size, how deep they are sunk at the centre, how far they lean, how their long axis lies to the slope, how
    many stand on another rock, how many overlap a neighbour, how much of the steep ground they cover, and how
    many of their rim points are naked (above the ground and inside no other rock: the rule);
  the zones round steep ground: the LIP (gentle ground within LIP of steep ground that falls away below it)
    and the FOOT (gentle ground just under it), each with its own density and pieces;
  the BANKS: land within BANK of the water, its density and pieces;
  the KNOLLS: hilltops of KNOLL_RELIEF or more within KNOLL_REACH, and the outcrop on each (pieces, their size,
    spacing, sink, the small rocks at their feet), the Lan Orethan recipe the user pointed at (OUTCROP) kept as
    the fallback where a region has no knolls of its own.

figures(db, region) gives a region's figures with thin bands borrowed from the nearest steepness (and a region
with under ENOUGH pieces takes the whole world's), and measure_cells() reads any cells the same way, so a made
valley is measured against the game's own gorge by one yardstick."""
import hashlib
import json
import math
import os
import re
from collections import Counter

import mapdata

VERSION = 1
SAMPLE = 70                     # cells a region read
MIN_SIZE = 200                  # a piece is at least this across (smaller rocks are 'small': the groups at the feet)
BIG = 1500                      # a cliff piece: this across or more
BANDS = (0.0, 15.0, 30.0, 45.0, 60.0, 91.0)
STEEP = 30.0                    # degrees: ground this steep is "steep ground" (the pass clads it)
STEEP_BAND = 2
LIP = 384                       # the lip and foot zones reach this far from the steep ground
BANK = 384                      # the bank: land within this of the water
KNOLL_RELIEF = 300              # a hilltop stands at least this over the ground within KNOLL_REACH
KNOLL_REACH = 1536
KNOLL_R = 1000                  # the outcrop: pieces within this of the top
POSES = 24                      # poses kept a piece and band
ENOUGH = 30                     # pieces a region needs to be its own look (fewer: the world's figures)
BAND_MIN = 8                    # pieces a band needs to be its own (fewer: the nearest band's)
WORDS = re.compile(r'rock|cliff|terrain_|terrrock|boulder|crag|stone(?!wall|_?floor)|ledge', re.I)
NOT = re.compile(r'road|wall_|railing|stair|step|bridge|platform|sign|lamp|flora|tree|barrel|crate|fence|gate|door|'
                 r'cave|entr|menhir|ruin|shrine|pillar|tower|house|kelp|coral|lily|stoneflower|plant|grave|tomb|dock|'
                 r'pier|well|statue|altar|table|chair|shelf|pebble|arch|column|bench|brazier', re.I)
# (the hilltop the user pointed at, Lan Orethan 34,-30, read 2026-11-08: the fallback outcrop recipe)
OUTCROP = {'relief': 516, 'pieces': [12, 21, 30], 'size': [450, 570, 920], 'height': [150, 210, 1090], 'spacing': 325,
           'overlap': 0.57, 'sunk': 217, 'top': [77, 375], 'small': 5, 'trees': 8, 'radius': 2000, 'top_third': 0.4}
_mem = {}


def is_piece(low):
    return bool(WORDS.search(low)) and not NOT.search(low)


def _band(deg):
    for k in range(len(BANDS) - 1):
        if deg < BANDS[k + 1]:
            return k
    return len(BANDS) - 2


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'cliffsurvey_%s_v%d.json' % (_sig(db), VERSION))


def family(rid):
    return re.sub(r'_\d+[a-z]?$', '', (rid or '').lower())


def pct(v, p):
    v = sorted(x for x in v if x is not None)
    return None if not v else v[min(len(v) - 1, int(len(v) * p))]


def _p3(v, nd=0):
    out = [pct(v, .1), pct(v, .5), pct(v, .9)]
    return [None if x is None else round(x, nd) for x in out]


# ---------------------------------------------------------------- a cell read

def _slopes(H):
    out = [None] * (65 * 65)
    for y in range(1, 64):
        for x in range(1, 64):
            i = y * 65 + x
            out[i] = math.degrees(math.atan(math.hypot((H[i + 1] - H[i - 1]) / 256.0, (H[i + 65] - H[i - 65]) / 256.0)))
    return out


def _bilinear(H, fx, fy):
    x0, y0 = min(63, max(0, int(fx))), min(63, max(0, int(fy)))
    tx, ty = fx - x0, fy - y0
    j = y0 * 65 + x0
    return (H[j] * (1 - tx) + H[j + 1] * tx) * (1 - ty) + (H[j + 65] * (1 - tx) + H[j + 66] * tx) * ty


def _zones(H, sl):
    """Each inner point's zone: 'steep', 'lip' (gentle, within LIP of steep ground lower than it), 'foot' (gentle,
    within LIP of steep ground higher than it), 'bank' (within BANK of the water), else '' ; and the knolls
    [(x, y, relief)] in grid points."""
    n = 65 * 65
    zone = [''] * n
    steep = [i for i in range(n) if sl[i] is not None and sl[i] >= STEEP and H[i] > 0]
    for i in steep:
        zone[i] = 'steep'
    r = int(LIP // 128)
    for i in steep:
        x, y = i % 65, i // 65
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                xx, yy = x + dx, y + dy
                if not (1 <= xx < 64 and 1 <= yy < 64) or dx * dx + dy * dy > r * r:
                    continue
                j = yy * 65 + xx
                if zone[j] == 'steep' or H[j] <= 0:
                    continue
                if H[j] > H[i] + 32:
                    zone[j] = 'lip'
                elif H[j] < H[i] - 32 and zone[j] != 'lip':
                    zone[j] = 'foot'
    rb = int(BANK // 128)
    for y in range(1, 64):
        for x in range(1, 64):
            i = y * 65 + x
            if H[i] <= 0 or zone[i] == 'steep':
                continue
            for dy in range(-rb, rb + 1):
                for dx in range(-rb, rb + 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < 65 and 0 <= yy < 65 and dx * dx + dy * dy <= rb * rb and H[yy * 65 + xx] <= 0:
                        zone[i] = 'bank'
                        break
                if zone[i] == 'bank':
                    break
    knolls = []
    rk = int(KNOLL_REACH // 128)
    for y in range(rk, 65 - rk, 3):
        for x in range(rk, 65 - rk, 3):
            i = y * 65 + x
            if H[i] <= 0 or (sl[i] or 0) >= STEEP:
                continue
            lo = hi = H[i]
            top = True
            for dy in range(-rk, rk + 1):
                row = (y + dy) * 65
                for dx in range(-rk, rk + 1):
                    v = H[row + x + dx]
                    if v > hi:
                        top = False
                        break
                    if v < lo:
                        lo = v
                if not top:
                    break
            if top and hi - lo >= KNOLL_RELIEF:
                if not any(abs(kx - x) <= rk and abs(ky - y) <= rk for kx, ky, _r in knolls):
                    knolls.append((x, y, hi - lo))
    return zone, knolls


def _downhill(gx, gy):
    return math.atan2(-gx, -gy)


def _tilt(pos):
    a = max(abs(math.degrees(pos[3])) % 360, abs(math.degrees(pos[4])) % 360)
    return min(a, 360 - a)


def _read_cell(db, gx, gy, bmemo):
    """(H, slopes, zone, knolls, pieces, small) of a cell; pieces: [{id, x, y, z, pos, s, b, size, h, bottom, top,
    g, slope, band, place, sunk, tilt, along, zone}]."""
    from project import ref_info
    import cliffrocks
    L = mapdata.land(db, gx, gy)
    if not L.get('exists') or L.get('flat'):
        return None
    H = L['h']
    sl = _slopes(H)
    pl = cliffrocks._places(H)
    zone, knolls = _zones(H, sl)
    refs, _h = db.cell_refs('#%d,%d' % (gx, gy))
    pieces, small = [], []
    for ref in refs.values():
        rid, pos, sc, dead = ref_info(ref['subs'])
        if dead or not rid:
            continue
        low = rid.lower()
        if not is_piece(low):
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
        size = max(b[3] - b[0], b[4] - b[1]) * sc
        h = (b[5] - b[2]) * sc
        g = _bilinear(H, fx, fy)
        if g <= 0:
            continue
        jn = int(round(fy)) * 65 + int(round(fx))
        if size < MIN_SIZE:
            small.append({'id': info[2], 'x': pos[0], 'y': pos[1], 'size': size, 'g': g, 'zone': zone[jn]})
            continue
        steep = sl[jn] if sl[jn] is not None else 0.0
        ggx, ggy = (H[jn + 1] - H[jn - 1]) / 256.0, (H[jn + 65] - H[jn - 65]) / 256.0
        long_local = 0.0 if (b[3] - b[0]) >= (b[4] - b[1]) else math.pi / 2
        along = abs(math.cos(long_local + pos[5] - _downhill(ggx, ggy))) if steep >= 8 else None
        turn = round(((pos[5] - _downhill(ggx, ggy)) + math.pi) % (2 * math.pi) - math.pi, 3) if steep >= 8 else None
        pieces.append({'id': info[2], 'name': info[3] or '', 'x': pos[0], 'y': pos[1], 'z': pos[2], 'pos': pos, 's': sc, 'b': b,
                       'size': size, 'h': h, 'bottom': pos[2] + b[2] * sc, 'top': pos[2] + b[5] * sc, 'g': g,
                       'slope': steep, 'band': _band(steep), 'place': pl[jn] if pl[jn] is not None else 1,
                       'sunk': g - (pos[2] + b[2] * sc), 'tilt': _tilt(pos), 'along': along, 'turn': turn,
                       'dz': pos[2] - g, 'zone': zone[jn]})
    # stacking and overlap among the cell's pieces
    for p in pieces:
        p['on_rock'] = any(o is not p and abs(o['top'] - p['bottom']) < 96 and math.hypot(o['x'] - p['x'], o['y'] - p['y']) < o['size'] / 2.0 for o in pieces)
        near = [math.hypot(o['x'] - p['x'], o['y'] - p['y']) / max(1.0, (o['size'] + p['size']) / 2.0) for o in pieces if o is not p]
        p['overlap'] = bool(near) and min(near) < 0.6
    return H, sl, zone, knolls, pieces, small


# ---------------------------------------------------------------- the survey

class _Acc:
    """What one region (or the world) gathers."""
    def __init__(self):
        self.cells = 0
        self.area = [0.0] * (len(BANDS) - 1)
        self.zone_area = Counter()
        self.pieces = [[] for _ in self.area]
        self.zone_pieces = {'lip': [], 'foot': [], 'bank': []}
        self.cover = [[0, 0] for _ in self.area]
        self.knolls = []
        self.items = [dict() for _ in self.area]
        self.zone_items = {'lip': {}, 'foot': {}, 'bank': {}}
        self.naked = [[0, 0] for _ in self.area]

    def add_cell(self, read, db):
        import cliffrocks
        import rockface
        H, sl, zone, knolls, pieces, small = read
        self.cells += 1
        for i in range(65 * 65):
            if sl[i] is None or H[i] <= 0:
                continue
            self.area[_band(sl[i])] += 128.0 * 128.0
            if zone[i]:
                self.zone_area[zone[i]] += 128.0 * 128.0
        feet = cliffrocks._Feet()
        boxes = rockface.Boxes()
        for p in pieces:
            feet.add(p['x'], p['y'], p['pos'][5], p['s'], p['b'])
            boxes.add({'x': p['x'], 'y': p['y'], 'z': p['z'], 'rx': p['pos'][3], 'ry': p['pos'][4], 'rz': p['pos'][5], 's': p['s']}, p['b'], tag=p)
        # (cover, the share of each steep band's points under a piece's footprint, is counted in add_cover)
        for p in pieces:
            k = p['band']
            self.pieces[k].append(p)
            it = self.items[k].setdefault(p['id'].lower(), {'id': p['id'], 'name': p['name'], 'n': 0, 'size': [round(p['b'][3] - p['b'][0]), round(p['b'][4] - p['b'][1]), round(p['b'][5] - p['b'][2])],
                                                            'zmin': round(p['b'][2], 1), 'scales': [], 'sinks': [], 'tilts': [], 'at': [0, 0, 0], 'poses': []})
            it['n'] += 1
            it['at'][p['place']] += 1
            if len(it['scales']) < 60:
                it['scales'].append(p['s'])
                it['sinks'].append(p['sunk'] / p['s'])
                it['tilts'].append(p['tilt'])
            if len(it['poses']) < POSES:
                it['poses'].append([round(p['pos'][3], 3), round(p['pos'][4], 3), p['turn'], round(p['dz'], 1), round(p['s'], 2), p['place']])
            if p['zone'] in self.zone_pieces:
                self.zone_pieces[p['zone']].append(p)
                zi = self.zone_items[p['zone']].setdefault(p['id'].lower(), {'id': p['id'], 'n': 0, 'size': it['size'], 'zmin': it['zmin'], 'poses': []})
                zi['n'] += 1
                if len(zi['poses']) < POSES:
                    zi['poses'].append(it['poses'][-1])
            # the rim rule: naked points above the ground and inside no other piece
            rim = rockface.rim(db, p['id'])
            if rim:
                ex = rockface.exposure({'x': p['x'], 'y': p['y'], 'z': p['z'], 'rx': p['pos'][3], 'ry': p['pos'][4], 'rz': p['pos'][5], 's': p['s']},
                                       rim, lambda x, y: _ground(db, x, y), boxes, skip=p)
                self.naked[k][0] += ex['naked']
                self.naked[k][1] += ex['n']
        # (knolls: the pieces within KNOLL_R of each top)
        for kx, ky, relief in knolls:
            wx, wy = self._wx + kx * 128.0, self._wy + ky * 128.0
            on = [p for p in pieces if math.hypot(p['x'] - wx, p['y'] - wy) <= KNOLL_R]
            sm = [s for s in small if math.hypot(s['x'] - wx, s['y'] - wy) <= KNOLL_R]
            big = [p for p in on if p['size'] >= 400]
            near = [min(math.hypot(a['x'] - b['x'], a['y'] - b['y']) for b in big if b is not a) for a in big] if len(big) > 1 else []
            self.knolls.append({'relief': relief, 'n': len(on), 'big': len(big), 'small': len(sm),
                                'size': pct([p['size'] for p in big], .5), 'h': pct([p['h'] for p in big], .5),
                                'sunk': pct([p['sunk'] for p in big], .5), 'spacing': pct(near, .5),
                                'feet': sum(1 for s in sm if any(math.hypot(s['x'] - b['x'], s['y'] - b['y']) < b['size'] / 2.0 + 300 for b in big)),
                                'top': [p['top'] - p['g'] for p in big]})

    def add_cover(self, read):
        import cliffrocks
        H, sl, zone, knolls, pieces, small = read
        feet = cliffrocks._Feet()
        for p in pieces:
            feet.add(p['x'], p['y'], p['pos'][5], p['s'], p['b'])
        for i in range(65 * 65):
            if sl[i] is None or H[i] <= 0 or _band(sl[i]) < STEEP_BAND:
                continue
            c = self.cover[_band(sl[i])]
            c[1] += 1
            c[0] += 1 if feet.under(self._wx + (i % 65) * 128.0, self._wy + (i // 65) * 128.0) else 0

    def figures(self):
        bands = []
        for k in range(len(self.area)):
            P = self.pieces[k]
            items = []
            for v in sorted(self.items[k].values(), key=lambda v: -v['n'])[:14]:
                if v['n'] < 2:
                    continue
                sc, sk, tl = sorted(v['scales']), sorted(v['sinks']), sorted(v['tilts'])
                lean = [t for t in tl if 1.0 <= t <= 60]
                items.append({'id': v['id'], 'name': v['name'], 'n': v['n'], 'size': v['size'], 'zmin': v['zmin'],
                              'smin': round(sc[len(sc) // 10], 2), 'smax': round(sc[min(len(sc) - 1, len(sc) * 9 // 10)], 2),
                              'sink': round(max(0.0, min(sk[len(sk) // 2], v['size'][2] * 0.7)), 1),
                              'tilt': round(lean[min(len(lean) - 1, len(lean) * 8 // 10)], 1) if lean else 0.0,
                              'tilt_share': round(len(lean) / len(tl), 2) if tl else 0.0, 'at': v['at'], 'poses': v['poses']})
            per_place = [0, 0, 0]
            for p in P:
                per_place[p['place']] += 1
            bands.append({'from': BANDS[k], 'to': BANDS[k + 1], 'area': round(self.area[k]), 'n': len(P),
                          'per_k': round(len(P) / self.area[k] * 1e6, 3) if self.area[k] > 0 else 0.0,
                          'place_share': [round(c / len(P), 3) for c in per_place] if P else [0.2, 0.6, 0.2],
                          'size': _p3([p['size'] for p in P]), 'height': _p3([p['h'] for p in P]), 'sunk': _p3([p['sunk'] for p in P]),
                          'tilt': [round(pct([p['tilt'] for p in P], .5) or 0, 1), round(pct([p['tilt'] for p in P], .9) or 0, 1)],
                          'along': round(pct([p['along'] for p in P], .5) or 0, 2),
                          'stacked': round(sum(1 for p in P if p['on_rock']) / len(P), 3) if P else 0.0,
                          'overlap': round(sum(1 for p in P if p['overlap']) / len(P), 3) if P else 0.0,
                          'big': round(sum(1 for p in P if p['size'] >= BIG) / len(P), 3) if P else 0.0,
                          'cover': round(self.cover[k][0] / self.cover[k][1], 3) if self.cover[k][1] else 0.0, 'cover_n': self.cover[k][1],
                          'naked': round(self.naked[k][0] / self.naked[k][1], 4) if self.naked[k][1] else None, 'rim_n': self.naked[k][1],
                          'items': items})
        zones = {}
        for z in ('lip', 'foot', 'bank'):
            P = self.zone_pieces[z]
            a = self.zone_area.get(z, 0.0)
            zones[z] = {'area': round(a), 'n': len(P), 'per_k': round(len(P) / a * 1e6, 3) if a > 0 else 0.0,
                        'size': _p3([p['size'] for p in P]), 'height': _p3([p['h'] for p in P]), 'sunk': _p3([p['sunk'] for p in P]),
                        'tilt': round(pct([p['tilt'] for p in P], .5) or 0, 1), 'big': round(sum(1 for p in P if p['size'] >= BIG) / len(P), 3) if P else 0.0,
                        'items': [{'id': v['id'], 'n': v['n'], 'size': v['size'], 'zmin': v['zmin'], 'poses': v['poses']}
                                  for v in sorted(self.zone_items[z].values(), key=lambda v: -v['n'])[:12] if v['n'] >= 2]}
        K = [k for k in self.knolls if k['n'] >= 3]
        knolls = {'n': len(self.knolls), 'with_rocks': len(K),
                  'pieces': _p3([k['n'] for k in K]), 'big': _p3([k['big'] for k in K]), 'small': _p3([k['small'] for k in K]),
                  'relief': round(pct([k['relief'] for k in K], .5) or 0), 'size': round(pct([k['size'] for k in K], .5) or 0),
                  'height': round(pct([k['h'] for k in K], .5) or 0), 'sunk': round(pct([k['sunk'] for k in K], .5) or 0),
                  'spacing': round(pct([k['spacing'] for k in K], .5) or 0),
                  'feet': round(sum(k['feet'] for k in K) / max(1, sum(k['small'] for k in K)), 2),
                  'top': _p3([t for k in K for t in k['top']])}
        return {'cells': self.cells, 'bands': bands, 'zones': zones, 'knolls': knolls, 'n': sum(len(P) for P in self.pieces)}


def _ground(db, x, y):
    return mapdata.terrain_z(db, x, y)


def survey(db, sample=SAMPLE, progress=None):
    """{'regions': {region: figures}, 'all': the world's, 'cells': n, 'secs'} (on disk by the load order)."""
    import time
    key = id(db.recs)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            if d.get('version') == VERSION:
                _mem[key] = d
                return d
    except (OSError, ValueError):
        pass
    import regions
    import rockface
    t0 = time.time()
    rmap = regions.region_map(db)
    by = {}
    for k, r in rmap.items():
        if r:
            by.setdefault(r, []).append(k)
    accs = {}
    world = _Acc()
    bmemo = {}
    n_cells = 0
    names = sorted(by)
    for n_, reg in enumerate(names):
        if progress:
            progress('Reading the rocks of %s' % reg, n_ / max(1, len(names)))
        cells = sorted(by[reg], key=lambda k: hashlib.md5(k.encode()).hexdigest())[:sample]
        acc = accs.setdefault(reg, _Acc())
        for ck in cells:
            gx, gy = (int(v) for v in ck.split(','))
            read = _read_cell(db, gx, gy, bmemo)
            if not read:
                continue
            n_cells += 1
            for a in (acc, world):
                a._wx, a._wy = gx * 8192.0, gy * 8192.0
                a.add_cell(read, db)
                a.add_cover(read)
    out = {'version': VERSION, 'cells': n_cells, 'regions': {reg: acc.figures() for reg, acc in accs.items()},
           'all': world.figures(), 'secs': round(time.time() - t0, 1)}
    rockface.save_rims()
    _mem[key] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except OSError:
        pass
    return out


def ready(db):
    """The survey if learnt (in memory or on disk); else None, and the survey process learns it meanwhile."""
    if id(db.recs) in _mem or os.path.isfile(_disk(db)):
        try:
            return survey(db)
        except Exception:
            return None
    import background
    background.start("how the game clads its cliffs", lambda: survey(db), task=('cliffsurvey', 'survey', []))
    return None


def figures(db, region):
    """A region's figures for the pass, each band and zone its own where it has BAND_MIN pieces, else the nearest
    band's (the steeper first), and the world's when the region set under ENOUGH pieces in all. {'region', 'bands',
    'zones', 'knolls', 'borrowed'}."""
    S = survey(db)
    region = (region or '').lower()
    R = S['regions'].get(region)
    borrowed = ''
    if not R or R['n'] < ENOUGH:
        R, borrowed = S['all'], 'all'
    W = S['all']
    bands = []
    for k, b in enumerate(R['bands']):
        if b['n'] >= BAND_MIN and b['items']:
            bands.append(b)
            continue
        pick = None
        for d in range(1, len(R['bands'])):
            for j in (k + d, k - d):
                if 0 <= j < len(R['bands']) and R['bands'][j]['n'] >= BAND_MIN and R['bands'][j]['items']:
                    pick = R['bands'][j]
                    break
            if pick:
                break
        if pick is None:
            pick = W['bands'][k] if W['bands'][k]['items'] else next((x for x in W['bands'] if x['items']), b)
        # (the band's own density where it has any ground, the borrowed band's pieces)
        bands.append(dict(pick, per_k=b['per_k'] if b['area'] > 1e6 and b['n'] else pick['per_k'], area=b['area']))
    zones = {}
    for z, v in R['zones'].items():
        if v['n'] >= BAND_MIN and v['items']:
            zones[z] = v
        else:
            wz = W['zones'].get(z) or v
            zones[z] = dict(wz, per_k=v['per_k'] if v['area'] > 2e6 and v['n'] else wz['per_k'], area=v['area'])
    knolls = R['knolls'] if R['knolls'].get('with_rocks', 0) >= 3 else (W['knolls'] if W['knolls'].get('with_rocks', 0) >= 3 else None)
    return {'region': region, 'bands': bands, 'zones': zones, 'knolls': knolls, 'borrowed': borrowed, 'n': R['n']}


def measure_cells(db, keys, ground_at=None):
    """The yardstick over any cells (the game's gorge, or a made valley): {'steep_area', 'pieces', 'per_k' (pieces a
    million square units of steep ground), 'size', 'height', 'sunk', 'tilt', 'stacked', 'overlap', 'big', 'cover',
    'naked' (naked rim points over all), 'naked_pieces' (pieces with any), 'bands': [...], 'zones', 'families'}.
    The pieces of every cell lean on each other across the cells' borders here."""
    import cliffrocks
    import rockface
    bmemo = {}
    reads = {}
    for gx, gy in keys:
        r = _read_cell(db, gx, gy, bmemo)
        if r:
            reads[(gx, gy)] = r
    allp = [p for r in reads.values() for p in r[4]]
    boxes = rockface.Boxes()
    for p in allp:
        boxes.add({'x': p['x'], 'y': p['y'], 'z': p['z'], 'rx': p['pos'][3], 'ry': p['pos'][4], 'rz': p['pos'][5], 's': p['s']}, p['b'], tag=p)
    g_at = ground_at or (lambda x, y: mapdata.terrain_z(db, x, y))
    naked = tot = withn = 0
    worst = []
    for p in allp:
        rim = rockface.rim(db, p['id'])
        if not rim:
            continue
        ex = rockface.exposure({'x': p['x'], 'y': p['y'], 'z': p['z'], 'rx': p['pos'][3], 'ry': p['pos'][4], 'rz': p['pos'][5], 's': p['s']}, rim, g_at, boxes, skip=p)
        naked += ex['naked']
        tot += ex['n']
        if ex['naked']:
            withn += 1
            worst.append((ex['max'], p['id'], round(p['x']), round(p['y'])))
    area = Counter()
    cover = [0, 0]
    for (gx, gy), (H, sl, zone, knolls, pieces, small) in reads.items():
        feet = cliffrocks._Feet()
        for p in pieces:
            feet.add(p['x'], p['y'], p['pos'][5], p['s'], p['b'])
        for i in range(65 * 65):
            if sl[i] is None or H[i] <= 0:
                continue
            area[_band(sl[i])] += 128.0 * 128.0
            if _band(sl[i]) >= STEEP_BAND:
                cover[1] += 1
                cover[0] += 1 if feet.under(gx * 8192.0 + (i % 65) * 128.0, gy * 8192.0 + (i // 65) * 128.0) else 0
    steep_area = sum(a for k, a in area.items() if k >= STEEP_BAND)
    steep_p = [p for p in allp if p['band'] >= STEEP_BAND]
    bands = []
    for k in range(len(BANDS) - 1):
        P = [p for p in allp if p['band'] == k]
        bands.append({'from': BANDS[k], 'n': len(P), 'area': round(area[k]), 'per_k': round(len(P) / area[k] * 1e6, 2) if area[k] else 0.0,
                      'size': _p3([p['size'] for p in P]), 'sunk': _p3([p['sunk'] for p in P])})
    worst.sort(reverse=True)
    return {'cells': len(reads), 'steep_area': round(steep_area), 'pieces': len(allp), 'steep_pieces': len(steep_p),
            'per_k': round(len(steep_p) / steep_area * 1e6, 2) if steep_area else None,
            'size': _p3([p['size'] for p in steep_p]), 'height': _p3([p['h'] for p in steep_p]), 'sunk': _p3([p['sunk'] for p in steep_p]),
            'tilt': [round(pct([p['tilt'] for p in steep_p], .5) or 0, 1), round(pct([p['tilt'] for p in steep_p], .9) or 0, 1)],
            'along': round(pct([p['along'] for p in steep_p], .5) or 0, 2),
            'stacked': round(sum(1 for p in allp if p['on_rock']) / len(allp), 3) if allp else 0.0,
            'overlap': round(sum(1 for p in allp if p['overlap']) / len(allp), 3) if allp else 0.0,
            'big': round(sum(1 for p in steep_p if p['size'] >= BIG) / len(steep_p), 3) if steep_p else 0.0,
            'cover': round(cover[0] / cover[1], 3) if cover[1] else None,
            'naked': round(naked / tot, 4) if tot else None, 'rim_points': tot, 'naked_pieces': withn,
            'worst': worst[:8], 'bands': bands,
            'zones': {z: sum(1 for p in allp if p['zone'] == z) for z in ('steep', 'lip', 'foot', 'bank')},
            'families': Counter(family(p['id']) for p in allp).most_common(8)}
