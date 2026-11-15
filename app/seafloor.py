"""The sea floor (2026-11-14). The user: "right now sea floor looks uninteresting where it falls into marked tiles, it
would be nice to have a way to automatically add variety to the sea floor in terms of hills or valleys, rocks, sea
shells, seaweed, coral, that sort of thing."

Measured that day (lab sea1, sea2): the game's hand-made sea beds are far from flat. Of a cell wholly under water the
middle nine tenths of the bed span 1,000 to 1,900 units; the ground differs by 28-50 units 128 apart (RMS), 105-185
at 512, 300-570 at 2,048 (West Gash, Azura's Coast, Ascadian Isles, Gold Coast, Stirk, the Abecean). A coast drawn in
the Workshop left its sea bed dead flat at -2,048 (0, 0, 0), and a heightmap's lake bed (the Heartlands) had 18, 68,
193, both untouched by the region pass, which works dry land only. And the bed is dressed: 0.7 to 3.2 things a
million square units (kelp, rocks, barnacles, kollops, coral, starfish, urchins, shells), where ours had 0.06, kelp.

learn(db): every region's water from the game's own land, kept on disk: how rough its sea cells are, how deep, how
much stands on its bed, where its water is. shape(): the region pass's sea stage, rolling ground laid on the bed under
the water in the layers that make its roughness the nearest hand-made sea's (landregion's layers, with two wider ones
for the banks and troughs), less where the bed is rough already, fading out towards the shore, never through the
water. dressed_like(): whose water a cell's bed is dressed after when its own region's is bare. open_water(): which
of the cells' water is the sea's (salt: coral, starfish, barnacles) and which a lake's.

The dressing itself is waterplants.py."""
import hashlib
import json
import math
import os
import random
import threading

import mapdata

VERSION = 1
N = 65
WET = -20.0                     # (ground under this is under the water)
SEA_CELL = 0.85                 # (a sea cell: this share of it under the water)
WET_CELL = 0.3                  # (a cell with this much water counts as one of its region's waters)
LAGS = (128, 512, 2048, 4096)
# (no layer wider than 8,192: nothing measured asks for one (the widest lag read is 4,096), and at the power law's
# height it sank a whole block of marked sea 800 under the cells round it, lab 2026-11-14)
OCTAVES = (8192.0, 4096.0, 2048.0, 1024.0, 512.0, 256.0)
LOOK_RELIEF = 150               # (sea cells a region measured, at most)
LOOK_THINGS = 24                # (wet cells a region whose beds are looked over for what stands on them)
LOOK_LANDS = 500                # (a region's cells read, at most)
HAND_128 = 24.0                 # (a sea this rough 128 apart was shaped by hand: heightmaps 13-22, the game's own 26-58;
HAND_SURE = 32.0                #  between this and HAND_SURE only if its water is dressed too: a few heightmap regions reach 25-27)
HAND_CELLS = 6
SEA_SHARE = 0.6                 # (a region this much sea cells is the open sea)
SEA_REACH = 12                  # (cells: water joined to the open sea within this is the sea's own)
DRESSED = 0.35                  # (things a million square units of bed for a region's water to be one to dress after)
DRESSED_CELLS = 6
FADE = (80.0, 700.0)            # (the relief fades in from this depth to this: the shore keeps its shape)
CEILING = 0.3                   # (the bed never rises past this share of its depth, nor past 96 under the water)
FLOOR = -3400.0
_lock = threading.RLock()
_mem = {}
_probe = {}


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'seafloor_%s_v%d.json' % (_sig(db), VERSION))


def _game_heights(db, gx, gy):
    """The game's own land of a cell (never the mod's), as mapdata.land reads it, or None."""
    import landsurvey
    ri = landsurvey._game_land(db, gx, gy)
    if ri is None:
        return None
    d = landsurvey._decode(db, ri)
    return d[0] if d else None


def ready(db):
    """Whether the game's seas have been read already (in memory or on disk): nothing to wait for."""
    return _sig(db) in _mem or os.path.exists(_disk(db))


def warm(db):
    """The game's seas read in a survey process if they haven't been (the land map asks when it opens)."""
    if ready(db):
        return
    import background
    background.start("the game's sea floors", lambda: learn(db), task=('seafloor', 'learn', []))


def sea_thing(low, typ):
    """Whether a thing is the sea bed's own: its plants, its animals that stay put, its rocks."""
    import waterplants
    return waterplants.takes(low, typ)


def learn(db, say=None):
    """{'regions': {region: {'wet', 'sea', 'rms' {lag: RMS difference}, 'depth' [p10, p50, p90], 'things' (a million
    square units of bed), 'at' [[gx, gy]] (some of its water), 'seashare'}}}: from disk, or read off the game now
    (half a minute to a minute, once for a load order)."""
    with _lock:
        sig = _sig(db)
        if sig in _mem:
            return _mem[sig]
        path = _disk(db)
        try:
            with open(path, encoding='utf-8') as f:
                got = json.load(f)
            if got.get('version') == VERSION:
                _mem[sig] = got
                return got
        except (OSError, ValueError):
            pass
        got = _learn(db, say)
        try:
            tmp = path + '.part'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(got, f)
            os.replace(tmp, path)
        except OSError as e:
            print('sea floor: not saved,', e)
        _mem[sig] = got
        return got


def _learn(db, say):
    import regions
    rmap = regions.region_map(db)
    proj = db.project.cells if db.project else {}
    by = {}
    for (tag, k) in db.by_key:
        if tag == 'LAND':
            by.setdefault(rmap.get(k) or '', []).append(k)
    out = {}
    done = 0
    for reg, keys in sorted(by.items()):
        done += 1
        if say and not done % 8:
            say("Reading the game's sea floors", 0.1 + 0.05 * done / max(1, len(by)))
        keys = sorted(keys, key=lambda k: hashlib.md5(k.encode()).hexdigest())[:LOOK_LANDS]
        sq = {lag: [0.0, 0] for lag in LAGS}
        depth, at = [], []
        wet = sea = measured = looked = things = 0
        bed = 0.0
        for k in keys:
            try:
                gx, gy = (int(v) for v in k.split(','))
            except ValueError:
                continue
            H = _game_heights(db, gx, gy)
            if H is None:
                continue
            under = sum(1 for h in H if h < WET)
            if under < WET_CELL * len(H):
                continue
            wet += 1
            if len(at) < 60:
                at.append([gx, gy])
            if under >= SEA_CELL * len(H):
                sea += 1
                srt = sorted(H)
                if srt[int(0.95 * len(srt))] - srt[int(0.05 * len(srt))] >= 40 and measured < LOOK_RELIEF:
                    measured += 1
                    for y in range(0, 64, 2):
                        row = y * N
                        for x in range(0, 64, 2):
                            h = H[row + x]
                            if h >= WET:
                                continue
                            if not (x + y) % 8:
                                depth.append(h)
                            for lag in LAGS:
                                n = lag // 128
                                if x + n <= 64:
                                    q = H[row + x + n]
                                    if q < WET:
                                        s = sq[lag]
                                        s[0] += (q - h) * (q - h)
                                        s[1] += 1
            if looked < LOOK_THINGS and ('#' + k) not in proj and reg:
                looked += 1
                bed += under * 128.0 * 128.0
                for r in mapdata.cellmap(db, '#' + k, original=True).get('refs') or ():
                    if r['p'][2] > -15 or not sea_thing(r['id'].lower(), r['type']):
                        continue
                    ix = min(64, max(0, int(round((r['p'][0] - gx * 8192.0) / 128.0))))
                    iy = min(64, max(0, int(round((r['p'][1] - gy * 8192.0) / 128.0))))
                    if H[iy * N + ix] < WET:
                        things += 1
        if not wet:
            continue
        depth.sort()
        out[reg] = {'wet': wet, 'sea': sea, 'cells': len(keys), 'measured': measured,
                    'rms': {str(lag): round(math.sqrt(s[0] / s[1]), 1) if s[1] else 0.0 for lag, s in sq.items()},
                    'depth': [depth[int(p * (len(depth) - 1))] for p in (0.1, 0.5, 0.9)] if depth else [],
                    'things': round(things / (bed / 1e6), 3) if bed else 0.0, 'at': at,
                    'seashare': round(sea / max(1, len(keys)), 3)}
    return {'version': VERSION, 'regions': out}


def handmade(db, say=None):
    """The regions whose sea beds were shaped by hand, the ones a bed is made after."""
    R = learn(db, say)['regions']
    return {r: v for r, v in R.items() if r and v['measured'] >= HAND_CELLS
            and (float(v['rms'].get('128') or 0) >= HAND_SURE or (float(v['rms'].get('128') or 0) >= HAND_128 and v['things'] >= 0.2))}


def dressed(db, say=None):
    """The regions whose water is dressed, the ones a bed is dressed after."""
    R = learn(db, say)['regions']
    return {r: v for r, v in R.items() if r and v['wet'] >= DRESSED_CELLS and v['things'] >= DRESSED}


def _nearest(pool, gx, gy, n=6):
    rows = []
    for r, v in pool.items():
        d = min((math.hypot(a - gx, b - gy) for a, b in v['at']), default=1e9)
        rows.append((d, r))
    return [r for _d, r in sorted(rows)[:n]]


def relief_like(db, region, gx, gy, want='', say=None):
    """The hand-made sea a region's bed at (gx, gy) is made after: the one asked for if its sea is hand-made, its
    own, else the nearest on the map."""
    hm = handmade(db, say)
    if want and want in hm:
        return want
    if region in hm:
        return region
    near = _nearest(hm, gx, gy, 1)
    return near[0] if near else ''


def dressed_like(db, region, gx, gy, want=''):
    """The regions whose water a cell's bed is dressed after, the first choice first."""
    dr = dressed(db)
    out = []
    for r in (want, region):
        if r and r in dr and r not in out:
            out.append(r)
    return out + [r for r in _nearest(dr, gx, gy) if r not in out]


# ---------- the layers ----------

def _probes():
    """The mean squared difference a unit layer makes at each lag, sampled once."""
    if _probe:
        return _probe
    import landregion
    rnd = random.Random(4711)
    pts = [(rnd.uniform(-4e5, 4e5), rnd.uniform(-4e5, 4e5)) for _ in range(1600)]
    for lam in OCTAVES:
        base = [landregion._octave(x, y, lam, 1, 0.0) for x, y in pts]
        for lag in LAGS:
            a = 0.0
            for (x, y), b in zip(pts, base):
                q = landregion._octave(x + lag, y, lam, 1, 0.0) - b
                a += q * q
            _probe[(lam, lag)] = a / len(pts)
    return _probe


def layer_amps(want):
    """Each layer's height (OCTAVES) for a flat bed to become as rough as want ({lag: RMS}) at LAGS: a power law over
    the layers (A x (size / 4,096)^b), fitted as landregion.layer_amps fits the land's."""
    P = _probes()
    need = {lag: float(want.get(str(lag)) or 0) ** 2 for lag in LAGS}
    if max(need.values()) < 64.0:
        return [0.0] * len(OCTAVES)
    best = None
    for k in range(0, 29):
        b = 0.2 + 0.05 * k
        S = {lag: sum((lam / 4096.0) ** (2 * b) * P[(lam, lag)] for lam in OCTAVES) for lag in LAGS}
        wts = {lag: 1.0 / max(1.0, need[lag]) ** 2 for lag in LAGS}
        num = sum(S[lag] * need[lag] * wts[lag] for lag in LAGS)
        den = sum(S[lag] * S[lag] * wts[lag] for lag in LAGS)
        A2 = max(0.0, num / den) if den else 0.0
        err = sum(((A2 * S[lag] - need[lag]) ** 2) * wts[lag] for lag in LAGS)
        if best is None or err < best[0]:
            best = (err, b, A2)
    _e, b, A2 = best
    A = math.sqrt(A2)
    return [A * (lam / 4096.0) ** b for lam in OCTAVES]


def _wet_rough(z, w, h, lag=4, r=4):
    """RMS difference `lag` coarse points apart (2,048 at 512) of the ground under the water, averaged over a
    (2r+1) square round each point; 0 where no water is near."""
    sq = [0.0] * (w * h)
    n = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if z[i] >= WET:
                continue
            for j, ok in ((i + lag, x + lag < w), (i + lag * w, y + lag < h)):
                if ok and z[j] < WET:
                    d = z[j] - z[i]
                    sq[i] += d * d
                    n[i] += 1
    out = [0.0] * (w * h)
    for y in range(h):
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        for x in range(w):
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            s = c = 0
            for yy in range(y0, y1):
                row = yy * w
                s += sum(sq[row + x0:row + x1])
                c += sum(n[row + x0:row + x1])
            out[y * w + x] = math.sqrt(s / c) if c else 0.0
    return out


def shape(db, F, pts, here, seed, amount=1.0, want='', say=None):
    """Rolling ground on the bed under the water at F's points pts, in place. here: {region: weight a point}.
    Returns {'points', 'like' {region: the sea it is made after}, 'layers' {like: heights}}."""
    import landregion
    wet = [i for i in pts if F.z[i] < WET]
    info = {'points': len(wet), 'like': {}, 'layers': {}}
    if not wet or amount <= 0:
        return info
    cx = sum(F.world(i)[0] for i in wet[::37] or wet) / len(wet[::37] or wet) / 8192.0
    cy = sum(F.world(i)[1] for i in wet[::37] or wet) / len(wet[::37] or wet) / 8192.0
    R = learn(db, say)['regions']
    amps, w2048 = {}, {}
    for r in here:
        lk = relief_like(db, r, cx, cy, want)
        if not lk:
            continue
        info['like'][r] = lk
        if lk not in info['layers']:
            a = layer_amps(R[lk]['rms'])
            info['layers'][lk] = [round(v) for v in a]
        amps[r] = layer_amps(R[lk]['rms'])
        w2048[r] = max(1.0, float(R[lk]['rms'].get('2048') or 1.0))
    if not amps:
        return info
    if say:
        say('Shaping the sea floor', 0.19)
    k, w, h, cz = landregion._coarse(F)
    lr = _wet_rough(cz, w, h)
    step = F.step
    on = [lam >= 2.0 * step for lam in OCTAVES]
    wts = [(r, here[r]) for r in amps]
    z = F.z
    oct_ = landregion._octave
    sd = int(seed) * 13 + 5003
    for i in wet:
        z0 = z[i]
        fade = landregion._smooth((-z0 - FADE[0]) / (FADE[1] - FADE[0]))
        if not fade:
            continue
        a = [0.0] * len(OCTAVES)
        ref = tot = 0.0
        for r, wr in wts:
            v = wr[i]
            if not v:
                continue
            tot += v
            ref += v * w2048[r]
            ar = amps[r]
            for o in range(len(OCTAVES)):
                a[o] += v * ar[o]
        if not tot:
            continue
        # (variances add: a bed already f of the way there in roughness takes the square root of what is left)
        f = landregion._up(F, k, w, h, lr, i) / (ref / tot)
        left = math.sqrt(max(0.0, 1.0 - f * f))
        if not left:
            continue
        x, y = F.world(i)
        s = 0.0
        for o, lam in enumerate(OCTAVES):
            if on[o] and a[o]:
                s += a[o] * oct_(x, y, lam, sd, 0.0)
        add = amount * s * left * fade / tot
        # (never through the water, never bottomless: eased towards a ceiling and a floor)
        if add > 0:
            room = max(1.0, -z0 - max(96.0, CEILING * -z0))
        else:
            room = max(1.0, z0 - FLOOR)
        z[i] = z0 + room * math.tanh(add / room)
    return info


# ---------- the sea's water and a lake's ----------

def open_water(db, keys, cap=90000):
    """{(gx, gy): True where the cell's water is the sea's}: joined under the water (every fourth point), within
    SEA_REACH cells, to a cell with no land or to a region that is mostly sea. A lake, or a river far from its mouth,
    is not. (A cell of no region is no proof either way: Tamriel.esm's lakes have such cells in their middles.)"""
    R = learn(db)['regions']
    import regions
    rmap = regions.region_map(db)
    lands, sea_cell = {}, {}

    def land(c):
        if c not in lands:
            L = mapdata.land(db, c[0], c[1])
            lands[c] = L['h'] if L.get('exists') and L.get('h') else None
        return lands[c]

    def is_sea(c):
        if c not in sea_cell:
            reg = rmap.get('%d,%d' % c)
            sea_cell[c] = land(c) is None or (bool(reg) and float((R.get(reg) or {}).get('seashare') or 0) >= SEA_SHARE)
        return sea_cell[c]

    def wet(p):
        H = land((p[0] // 16, p[1] // 16))
        return H is not None and H[(p[1] % 16) * 4 * N + (p[0] % 16) * 4] < 0
    out, known = {}, {}
    for key in keys:
        if is_sea(key):
            out[key] = True
            continue
        H = land(key)
        starts = [(key[0] * 16 + x, key[1] * 16 + y) for y in range(16) for x in range(16) if H[y * 4 * N + x * 4] < 0]
        res = False
        seen = set()
        for st in starts:
            if st in known:
                res = res or known[st]
                continue
            if st in seen:
                continue
            comp, stack, found = [], [st], False
            seen.add(st)
            while stack and not found and len(seen) < cap:
                p = stack.pop()
                comp.append(p)
                for q in ((p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)):
                    if q in seen:
                        continue
                    c = (q[0] // 16, q[1] // 16)
                    if abs(c[0] - key[0]) > SEA_REACH or abs(c[1] - key[1]) > SEA_REACH:
                        continue
                    if q in known:
                        found = found or known[q]
                        continue
                    if is_sea(c):
                        if land(c) is None or wet(q):
                            found = True
                            break
                        continue
                    if wet(q):
                        seen.add(q)
                        stack.append(q)
            for p in comp:
                known[p] = found
            for p in stack:
                known[p] = found
            res = res or found
            if res:
                break
        out[key] = res
    return out
