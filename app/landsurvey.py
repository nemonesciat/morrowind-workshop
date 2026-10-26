"""The land survey: how the game's own outdoor land is shaped, textured and shaded, and how much is built on
each cell, for shaping land over many cells at once (packaging/terrain-shaping-proposal.md, stage 0).

Read from every landscape in the load order (the mod being made is left out):

  cells     for each exterior cell: whether it is sea, shore or land, its lowest and highest ground, its
            region and name, the plugin whose land it is, how rough it is close up, how many textures and
            whether it has vertex colours, and what stands on it (objects, building pieces, doors into
            interiors, people and creatures). What the map's "where can I shape" overlay is read from.
  regions   for each region: heights, slopes, roughness at each distance (the noise to match), which texture
            the game lays at each slope and height, its shore profile (the ground's height going inland and
            out to sea from the waterline), and whether the game's shading darkens hollows and lightens crests.
  water     the inland water (ground under sea level not joined to the open sea, at every 4th point), and the
            water heights exterior cells carry.
  extent    the grid each plugin's land covers, for finding room for new land.

Kept in the cache folder under the signature of the plugins holding land. Nothing here edits a place."""
import hashlib
import json
import math
import os
import struct
from array import array
from collections import Counter, defaultdict

from esm import iter_subrecords, zstr
from project import ref_info

VERSION = 1
N = 65
SLOPES = (10, 20, 30, 45)                 # slope bands, degrees: under 10, 10-20, 20-30, 30-45, 45 and over
HEIGHTS = (0, 500, 1500, 4000)            # height bands: under the sea, shore, low, hills, mountains
LAGS = (1, 2, 4, 8, 16, 32, 64)           # roughness at these distances, in points (128 units each)
PROFILE = 64                              # shore profile: this many points inland and out to sea
_cache = {}


def sig(db):
    """The plugins whose land the survey reads, with their sizes (the mod being made left out)."""
    plugins = db.plugins or []
    holders = {r[3] for r in db.recs if r is not None and r[0] == 'LAND'}
    parts = sorted('%s:%s' % (plugins[i]['name'].lower(), plugins[i].get('size') or 0)
                   for i in holders if i != db.proj_pidx and i < len(plugins))
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'landsurvey_%s_v%d.json' % (sig(db), VERSION))


def ready(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    import background
    background.start('how the game shapes its land', lambda: survey(db), task=('landsurvey', 'survey', []))
    return None


def survey(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache['survey'] = (db.recs, saved)
        return saved
    except Exception:
        pass
    out = _survey(db)
    _cache['survey'] = (db.recs, out)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


# ---------- reading one landscape ----------

def _game_land(db, gx, gy):
    """The last landscape for a cell that isn't the mod's own, or None."""
    lst = [v for v in db.by_key.get(('LAND', '%d,%d' % (gx, gy)), []) if v not in db.dead and db.recs[v][3] != db.proj_pidx]
    return lst[-1] if lst else None


def _decode(db, ri):
    """(heights as array('i') of 65*65, texture file per patch [256], vertex colours bytes or None)."""
    import landshade
    r = db.recs[ri]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    h = None
    for st, sd in iter_subrecords(data):
        if st == 'VHGT' and len(sd) >= 4 + N * N:
            base = struct.unpack_from('<f', sd)[0]
            dl = struct.unpack_from('<4225b', sd, 4)
            h = array('i', bytes(4 * N * N))
            row = base
            for y in range(N):
                row += dl[y * N]
                col = row
                h[y * N] = int(col * 8)
                for x in range(1, N):
                    col += dl[y * N + x]
                    h[y * N + x] = int(col * 8)
    if h is None:
        return None
    grid, col = landshade._land_of(db, ri)
    return h, grid, col


def _band(v, cuts):
    for n, c in enumerate(cuts):
        if v < c:
            return n
    return len(cuts)


def _pct(vals, ps):
    if not vals:
        return {}
    s = sorted(vals)
    return {str(p): round(s[min(len(s) - 1, int(len(s) * p / 100.0))], 1) for p in ps}


# ---------- what stands on a cell ----------

_BUILD = ('ex_', 't_de_setind_x', 't_de_setveloth_x', 't_imp_set', 't_com_set', 't_nor_set', 't_de_set')


def _built(db, key, tags):
    """{refs, build, doors, actors} for an exterior cell (doors: leading into an interior)."""
    import doors
    refs, _hdr = db.cell_refs(key, without_project=True)
    n = Counter()
    for ref in refs.values():
        rid, _pos, _s, deleted = ref_info(ref['subs'])
        if deleted:
            continue
        low = rid.lower()
        if low not in tags:
            ti = db.resolve_id(rid)
            tags[low] = db.recs[ti][0] if ti is not None else ''
        tag = tags[low]
        n['refs'] += 1
        if tag in ('NPC_', 'CREA', 'LEVC'):
            n['actors'] += 1
        elif tag == 'DOOR':
            to = doors.link_of(ref['subs'])
            if to and to.get('cell'):
                n['doors'] += 1
        elif tag == 'STAT' and (low.startswith(_BUILD) or '_x_' in low or '_ex_' in low):
            n['build'] += 1
    return n


# ---------- the survey ----------

def _survey(db):
    cells, lands = {}, {}
    tags = {}
    names, wh = {}, Counter()
    # exterior cells: name, region, water height
    for (tag, key), lst in list(db.by_key.items()):
        if tag != 'CELL' or not key.startswith('#'):
            continue
        lst = [v for v in lst if v not in db.dead and db.recs[v][3] != db.proj_pidx]
        if not lst:
            continue
        r = db.recs[lst[-1]]
        _t, _f, data = db.files[r[3]].record_at(r[4])
        name, region, water = '', '', None
        for st, sd in iter_subrecords(data):
            if st == 'NAME':
                name = zstr(sd)
            elif st == 'RGNN':
                region = zstr(sd).lower()
            elif st == 'WHGT' and len(sd) >= 4:
                water = struct.unpack_from('<f', sd)[0]
            elif st in ('FRMR', 'MVRF'):
                break
        names[key] = (name, region)
        if water is not None:
            wh[round(water)] += 1
    reg = defaultdict(lambda: {'pts': 0, 'h': [], 'slope': [], 'lag': [[0.0, 0] for _ in LAGS],
                               'tex': defaultdict(Counter), 'shade': defaultdict(lambda: [0.0, 0]),
                               'shore': [[0.0, 0] for _ in range(2 * PROFILE + 1)], 'cells': 0})
    extent = defaultdict(lambda: [10 ** 6, 10 ** 6, -10 ** 6, -10 ** 6, 0])
    for (tag, key), lst in list(db.by_key.items()):
        if tag != 'LAND':
            continue
        try:
            gx, gy = (int(v) for v in key.split(','))
        except ValueError:
            continue
        ri = _game_land(db, gx, gy)
        if ri is None:
            continue
        d = _decode(db, ri)
        if d is None:
            continue
        h, grid, col = d
        lands[(gx, gy)] = h
        ck = '#%d,%d' % (gx, gy)
        name, region = names.get(ck, ('', ''))
        R = reg[region or '(none)']
        R['cells'] += 1
        plug = db.plugins[db.recs[ri][3]]['name']
        e = extent[plug]
        e[0], e[1], e[2], e[3] = min(e[0], gx), min(e[1], gy), max(e[2], gx), max(e[3], gy)
        e[4] += 1
        lo, hi = min(h), max(h)
        # roughness close up: the typical height step from one point to the next along the rows
        r1 = math.sqrt(sum((h[y * N + x + 1] - h[y * N + x]) ** 2 for y in range(0, N, 4) for x in range(64)) / (17 * 64))
        built = _built(db, ck, tags)
        cells['%d,%d' % (gx, gy)] = {
            'k': 'sea' if hi < 0 else 'shore' if lo < 0 else 'land', 'lo': lo, 'hi': hi, 'r1': round(r1, 1),
            'tex': len(set(grid)), 'vclr': col is not None, 'region': region, 'name': name, 'plugin': plug,
            'refs': built['refs'], 'build': built['build'], 'doors': built['doors'], 'actors': built['actors']}
        if hi < 0:
            continue                                     # (the sea bed teaches nothing about land)
        # heights, slopes and textures at every other point; the shading against its hollows and crests
        cl = {}
        if col:
            # each texture's own colour in this cell, where it lies alone
            sums = defaultdict(lambda: [0, 0])
            for y in range(2, 63, 2):
                for x in range(2, 63, 2):
                    t = _alone(grid, x, y)
                    if t is not None:
                        o = (y * N + x) * 3
                        s = sums[t]
                        s[0] += col[o] + col[o + 1] + col[o + 2]
                        s[1] += 1
            cl = {t: s[0] / s[1] for t, s in sums.items() if s[1] >= 8}
        for y in range(1, 64, 2):
            for x in range(1, 64, 2):
                v = y * N + x
                z = h[v]
                if z < -64:
                    continue
                gxs = (h[v + 1] - h[v - 1]) / 256.0
                gys = (h[v + N] - h[v - N]) / 256.0
                sl = math.degrees(math.atan(math.hypot(gxs, gys)))
                R['pts'] += 1
                if (x + y) % 4 == 2:
                    R['h'].append(z)
                    R['slope'].append(round(sl, 1))
                px, py = min(15, x // 4), min(15, y // 4)
                R['tex']['%d,%d' % (_band(sl, SLOPES), _band(z, HEIGHTS))][grid[py * 16 + px]] += 1
                if cl:
                    t = _alone(grid, x, y)
                    if t in cl:
                        o = v * 3
                        lap = (h[v - 1] + h[v + 1] + h[v - N] + h[v + N] - 4 * z) / 4.0      # >0: a hollow, <0: a crest
                        b = (col[o] + col[o + 1] + col[o + 2]) / max(1.0, cl[t])
                        s = R['shade']['%d' % max(-4, min(4, int(round(lap / 32.0))))]
                        s[0] += b
                        s[1] += 1
        for n, lag in enumerate(LAGS):
            acc = R['lag'][n]
            for y in range(0, N, 8):
                for x in range(0, N - lag, 2):
                    dz = h[y * N + x + lag] - h[y * N + x]
                    acc[0] += dz * dz
                    acc[1] += 1
    # shore profiles: along every row and column through a shore cell, the ground either side of each waterline
    def H(gx, gy, x, y):
        gx += x // 64
        gy += y // 64
        x, y = x % 64, y % 64
        a = lands.get((gx, gy))
        return a[y * N + x] if a is not None else -2048
    for key, c in cells.items():
        if c['k'] != 'shore':
            continue
        gx, gy = (int(v) for v in key.split(','))
        R = reg[c['region'] or '(none)']
        for horiz in (True, False):
            for j in range(0, 64, 8):
                for i in range(64):
                    a = H(gx, gy, i, j) if horiz else H(gx, gy, j, i)
                    b = H(gx, gy, i + 1, j) if horiz else H(gx, gy, j, i + 1)
                    if (a < 0) == (b < 0):
                        continue
                    up = 1 if b >= 0 else -1             # which way is inland
                    at = i if up == 1 else i + 1
                    for k in range(-PROFILE, PROFILE + 1):
                        p = at + up * k
                        z = H(gx, gy, p, j) if horiz else H(gx, gy, j, p)
                        s = R['shore'][k + PROFILE]
                        s[0] += z
                        s[1] += 1
    # inland water: points under the sea (every 4th) not joined to the open sea, which is any cell with no land
    water = _inland_water(lands, cells)
    regions = {}
    for name, R in reg.items():
        if R['pts'] < 200:
            continue
        tex = {}
        for band, c in R['tex'].items():
            tot = sum(c.values())
            tex[band] = {'n': tot, 'top': [[t or 'default', round(n / tot, 3)] for t, n in c.most_common(6)]}
        regions[name] = {
            'cells': R['cells'], 'points': R['pts'],
            'height': _pct(R['h'], (5, 25, 50, 75, 95, 99)),
            'slope': _pct(R['slope'], (25, 50, 75, 90, 95, 99, 99.9)),
            'steep': {str(d): round(sum(1 for s in R['slope'] if s > d) / max(1, len(R['slope'])), 4) for d in (30, 45, 60, 70)},
            'rough': {str(lag * 128): round(math.sqrt(a[0] / a[1])) for lag, a in zip(LAGS, R['lag']) if a[1]},
            'textures': tex,
            'shade': {k: [round(s[0] / s[1], 3), s[1]] for k, s in sorted(R['shade'].items(), key=lambda kv: int(kv[0])) if s[1] >= 30},
            'shore': [round(s[0] / s[1]) if s[1] else None for s in R['shore']], 'shore_n': R['shore'][PROFILE][1]}
        lr = [(math.log(lag), math.log(math.sqrt(a[0] / a[1]))) for lag, a in zip(LAGS, R['lag']) if a[1] and a[0] > 0]
        if len(lr) > 2:
            mx, my = sum(p[0] for p in lr) / len(lr), sum(p[1] for p in lr) / len(lr)
            regions[name]['hurst'] = round(sum((p[0] - mx) * (p[1] - my) for p in lr) / sum((p[0] - mx) ** 2 for p in lr), 2)
    return {'version': VERSION, 'cells': cells, 'regions': regions, 'water': water,
            'water_heights': {str(k): n for k, n in wh.most_common(12)},
            'extent': {p: {'x0': e[0], 'y0': e[1], 'x1': e[2], 'y1': e[3], 'cells': e[4]} for p, e in extent.items()}}


def _alone(grid, x, y):
    """The texture at point (x, y) when the four patches around it are all the same one, else None."""
    a = grid[min(15, max(0, (y - 2) // 4)) * 16 + min(15, max(0, (x - 2) // 4))]
    for dx, dy in ((2, -2), (-2, 2), (2, 2)):
        if grid[min(15, max(0, (y + dy) // 4)) * 16 + min(15, max(0, (x + dx) // 4))] != a:
            return None
    return a


def _inland_water(lands, cells):
    """[{cells, points, lowest, middle cell, name}] of each body of water not joined to the open sea."""
    wet = set()
    for (gx, gy), h in lands.items():
        for y in range(0, 64, 4):
            for x in range(0, 64, 4):
                if h[y * N + x] < 0:
                    wet.add((gx * 16 + x // 4, gy * 16 + y // 4))
    seen, out = set(), []
    for start in wet:
        if start in seen:
            continue
        comp, stack, sea, low = [], [start], False, 0
        seen.add(start)
        while stack:
            p = stack.pop()
            comp.append(p)
            for q in ((p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)):
                if q in seen:
                    continue
                if (q[0] // 16, q[1] // 16) not in lands:
                    sea = True                           # (off the land's edge: the open sea)
                    continue
                if q in wet:
                    seen.add(q)
                    stack.append(q)
        if sea or len(comp) < 3:
            continue
        cs = Counter((p[0] // 16, p[1] // 16) for p in comp)
        (mx, my), _n = cs.most_common(1)[0]
        c = cells.get('%d,%d' % (mx, my), {})
        lowest = min(lands[(p[0] // 16, p[1] // 16)][(p[1] % 16) * 4 * N + (p[0] % 16) * 4] for p in comp)
        out.append({'cells': len(cs), 'points': len(comp), 'lowest': lowest, 'at': '%d,%d' % (mx, my),
                    'name': c.get('name') or '', 'region': c.get('region') or ''})
    out.sort(key=lambda w: -w['points'])
    return out[:200]
