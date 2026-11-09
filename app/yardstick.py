"""A yardstick for a first pass (docs/worldbuilding-next-2026-11.md, proposal 8): the marked cells as they stand now,
layer by layer, against the hand-made region they take after, a score for each and for the whole, and the five
cells that fall furthest short, each with what is wrong there.

Both sides are read the same way: the marked cells with the mod, the region's own game cells without it (up to SAMPLE
of its land cells, none of a game town's). The ground's figures (roughness 128, 512 and 2,048 apart, the steep
ground's share) come from the land itself; trees, plants and rocks as landdecor and cliffrocks tell them; the places
(doors outside the towns, those within 1,024 one place), the small things (smallthings' anchors), the people and the
creatures outside the towns; the road (the share of the ground in a road texture).

A layer's score is the smaller of the two figures over the larger (1 when they agree, 0.5 when one is twice the
other); the whole's, their mean. A cell's shortfall is the sum, over the ground's roughness, its trees, plants,
rocks and creatures, of how many times over or under the region's median cell it is (in logs); the five worst are
named with the figure that is furthest off."""
import math
import random
import re

import mapdata

SAMPLE = 160                     # (the region's land cells read at most)
N = 65
ROAD = re.compile(r'road|cobble|path|street|pave|brick|flagstone|walkway|plaza', re.I)
LAGS = (1, 4, 16)                # (points of 128: 128, 512, 2,048 apart)
PLACE_LINK = 1024.0
# (each layer's figure taken this much higher on both sides before the ratio: the rare things (a place, a person a
# cell) come in few to a cell, and 60 of a region's own cells scored 0.73 against 83 others of it before, lab j_yard2)
EPS = {'trees': 1.0, 'plants': 1.0, 'rocks': 1.0, 'creatures': 0.3, 'people': 0.15, 'places': 0.15, 'small': 0.15, 'road': 0.005}
LABELS = [('rough128', 'Roughness close up'), ('rough512', 'Roughness 512 apart'), ('rough2048', 'Hills and hollows'),
          ('steep30', 'Ground over 30°'), ('steep45', 'Cliffs (over 45°)'), ('trees', 'Trees a cell'), ('plants', 'Plants a cell'),
          ('rocks', 'Rocks a cell'), ('road', 'Road (share of the ground)'), ('places', 'Places a cell'), ('small', 'Small things a cell'),
          ('people', 'People a cell'), ('creatures', 'Creatures a cell')]
_REF = {}


def _cell_figs(db, gx, gy, original=False):
    """One cell's figures, or None where it has no land above the water: {'land', 'r': {lag: [sum of squares, n]},
    'steep': [over 30, over 45, n], 'trees', 'plants', 'rocks', 'road': [patches, land patches], 'doors': [(x, y)],
    'small', 'people', 'creatures'}."""
    import cliffrocks
    import landdecor
    import smallthings
    L = mapdata.land(db, gx, gy, with_textures=True)
    if not L.get('exists'):
        return None
    h = L['h']
    land = sum(1 for z in h if z > 0) / float(N * N)
    if land < 0.5:
        return None
    r = {}
    for lag in LAGS:
        acc, n = 0.0, 0
        for y in range(0, N, 4):
            for x in range(0, N - lag, 2):
                a, b = h[y * N + x], h[y * N + x + lag]
                if a > 0 and b > 0:
                    acc += (b - a) ** 2
                    n += 1
        r[lag] = [acc, n]
    s30 = s45 = sn = 0
    for y in range(1, 64, 2):
        for x in range(1, 64, 2):
            v = y * N + x
            if h[v] <= 0:
                continue
            sl = math.degrees(math.atan(math.hypot((h[v + 1] - h[v - 1]) / 256.0, (h[v + N] - h[v - N]) / 256.0)))
            sn += 1
            s30 += sl > 30
            s45 += sl > 45
    tex = L.get('tex') or []
    rd = sum(1 for i in L.get('t') or [] if i < len(tex) and ROAD.search(tex[i] or ''))
    m = mapdata.cellmap(db, '#%d,%d' % (gx, gy), original=original)
    trees = plants = rocks = people = creatures = 0
    doors, small = [], set()
    for ref in m.get('refs') or []:
        low = (ref.get('id') or '').lower()
        tag = ref.get('type')
        if tag == 'NPC_':
            people += 1
        elif tag in ('CREA', 'LEVC'):
            creatures += 1
        elif tag == 'DOOR':
            doors.append((ref['p'][0], ref['p'][1]))
        elif cliffrocks.is_rock(low):
            rocks += 1
        else:
            k = landdecor.kind_of(low)
            if k == 'trees':
                trees += 1
            elif k == 'plants':
                plants += 1
            sk = smallthings.kind_of(low)
            if sk:
                small.add((sk, round(ref['p'][0] / 400), round(ref['p'][1] / 400)))
    return {'land': land, 'r': r, 'steep': [s30, s45, sn], 'trees': trees, 'plants': plants, 'rocks': rocks,
            'road': [rd, 256 * land], 'doors': doors, 'small': len(small), 'people': people, 'creatures': creatures}


def _places(doors):
    """Doors within PLACE_LINK of each other one place: how many places."""
    n, seen = 0, set()
    for i in range(len(doors)):
        if i in seen:
            continue
        n += 1
        st = [i]
        seen.add(i)
        while st:
            a = st.pop()
            for j in range(len(doors)):
                if j not in seen and math.hypot(doors[a][0] - doors[j][0], doors[a][1] - doors[j][1]) < PLACE_LINK:
                    seen.add(j)
                    st.append(j)
    return n


def _fold(figs, town=frozenset()):
    """The cells' figures together: each layer a land cell (the town cells left out of the places, people and
    creatures), the roughness and steep shares over all."""
    if not figs:
        return {}
    acc = {lag: [0.0, 0] for lag in LAGS}
    s30 = s45 = sn = 0
    out = {k: 0.0 for k in ('trees', 'plants', 'rocks', 'small', 'people', 'creatures')}
    rd = [0.0, 0.0]
    doors, wild = [], 0
    for key, f in figs.items():
        for lag in LAGS:
            acc[lag][0] += f['r'][lag][0]
            acc[lag][1] += f['r'][lag][1]
        s30 += f['steep'][0]
        s45 += f['steep'][1]
        sn += f['steep'][2]
        rd[0] += f['road'][0]
        rd[1] += f['road'][1]
        for k in ('trees', 'plants', 'rocks'):
            out[k] += f[k]
        if key not in town:
            wild += 1
            for k in ('small', 'people', 'creatures'):
                out[k] += f[k]
            doors += f['doors']
    n = float(len(figs))
    res = {'rough%d' % (lag * 128): math.sqrt(a[0] / a[1]) if a[1] else 0.0 for lag, a in acc.items()}
    res['steep30'] = s30 / max(1, sn)
    res['steep45'] = s45 / max(1, sn)
    res['road'] = rd[0] / max(1.0, rd[1])
    for k in ('trees', 'plants', 'rocks'):
        res[k] = out[k] / n
    for k in ('small', 'people', 'creatures'):
        res[k] = out[k] / max(1, wild)
    res['places'] = _places(doors) / max(1, wild)
    res['cells'] = len(figs)
    return res


def reference(db, region):
    """The region's own figures, as _fold gives them, from up to SAMPLE of its game land cells (none of a town's),
    and its cells' medians for the cell checks. Kept for the session."""
    import landsurvey
    import townsurvey
    key = (id(db.recs), region)
    if key in _REF:
        return _REF[key]
    S = landsurvey.ready(db) or {}
    town = set()
    for t in townsurvey.survey(db)['towns']:
        town.update(tuple(c) for c in t['cells'])
    cells = [k for k, c in (S.get('cells') or {}).items() if (c.get('region') or '') == region and c.get('k') == 'land']
    rng = random.Random(region)
    rng.shuffle(cells)
    figs = {}
    for k in cells:
        if len(figs) >= SAMPLE:
            break
        gx, gy = (int(v) for v in k.split(','))
        if (gx, gy) in town:
            continue
        f = _cell_figs(db, gx, gy, original=True)
        if f:
            figs[(gx, gy)] = f
    R = _fold(figs)
    R['median'] = _medians(figs)
    _REF[key] = R
    return R


def _rough(f, lag):
    a = f['r'][lag]
    return math.sqrt(a[0] / a[1]) if a[1] else 0.0


def _medians(figs):
    def med(v):
        v = sorted(v)
        return v[len(v) // 2] if v else 0.0
    vals = list(figs.values())
    return {'rough512': med([_rough(f, 4) for f in vals]), 'trees': med([f['trees'] for f in vals]), 'plants': med([f['plants'] for f in vals]),
            'rocks': med([f['rocks'] for f in vals]), 'creatures': med([f['creatures'] for f in vals])}


def _score(a, b, eps):
    a, b = max(0.0, a) + eps, max(0.0, b) + eps
    return min(a, b) / max(a, b)


def report(db, cells, like='', towns=(), say=None):
    """{'region', 'like', 'cells', 'layers': [{key, label, ours, game, score}], 'score', 'worst': [{cell, why, off}]}
    for the marked cells. like: the region they take after (else landregion.like_for of their commonest region);
    towns: the settlements' outlines (their cells left out of the places, people and creatures)."""
    import landrange
    import landregion
    from collections import Counter
    keys = sorted({landrange._key(k) for k in cells or []})
    figs = {}
    regs = Counter()
    for n, (gx, gy) in enumerate(keys):
        if say and n % 20 == 0:
            say('Measuring the cells', n / max(1, len(keys)))
        f = _cell_figs(db, gx, gy)
        if f:
            figs[(gx, gy)] = f
            regs[landrange._region_of(db, gx, gy)] += 1
    if not figs:
        return {'cells': 0, 'layers': [], 'score': None, 'worst': [], 'region': '', 'like': ''}
    region = regs.most_common(1)[0][0]
    want = landregion.like_for(db, region, (like or '').lower())
    town = set()
    for pts in towns or ():
        if len(pts) >= 3:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            for gx in range(math.floor(min(xs) / 8192.0), math.floor(max(xs) / 8192.0) + 1):
                for gy in range(math.floor(min(ys) / 8192.0), math.floor(max(ys) / 8192.0) + 1):
                    town.add((gx, gy))
    ours = _fold(figs, frozenset(town))
    if say:
        say('Reading %s' % want, 0.8)
    ref = reference(db, want)
    layers, tot = [], []
    for k, lab in LABELS:
        o, g = ours.get(k, 0.0), ref.get(k, 0.0)
        e = EPS.get(k, max(1e-3, 0.05 * g))
        sc = _score(o, g, e)
        layers.append({'key': k, 'label': lab, 'ours': round(o, 4 if k in ('steep30', 'steep45', 'road') else 2), 'game': round(g, 4 if k in ('steep30', 'steep45', 'road') else 2),
                       'score': round(sc, 2)})
        tot.append(sc)
    # the cells that fall furthest short of the region's median cell
    M = ref.get('median') or {}
    worst = []
    WHY = {'rough512': ('smoother', 'rougher'), 'trees': ('fewer trees', 'more trees'), 'plants': ('fewer plants', 'more plants'),
           'rocks': ('fewer rocks', 'more rocks'), 'creatures': ('fewer creatures', 'more creatures')}
    for c, f in figs.items():
        vals = {'rough512': _rough(f, 4), 'trees': f['trees'], 'plants': f['plants'], 'rocks': f['rocks'], 'creatures': f['creatures']}
        if c in town:
            vals.pop('creatures')
        offs = {}
        for k, v in vals.items():
            e = 2.0 if k == 'rough512' else 1.0
            offs[k] = math.log((v + e) / (M.get(k, 0.0) + e))
        total = sum(abs(v) for v in offs.values())
        k = max(offs, key=lambda q: abs(offs[q]))
        times = math.exp(abs(offs[k]))
        why = '%s: %s (region %s)' % (WHY[k][0 if offs[k] < 0 else 1], round(vals[k]), round(M.get(k, 0.0)))
        worst.append({'cell': '%d,%d' % c, 'why': why, 'off': round(total, 2), 'times': round(times, 1)})
    worst.sort(key=lambda w: -w['off'])
    # (five apart: the next worst not beside one named already, so they show five places to look, not one stretch)
    picked = []
    for w in worst:
        gx, gy = (int(v) for v in w['cell'].split(','))
        if any(max(abs(gx - a), abs(gy - b)) <= 1 for a, b in ((int(v) for v in q['cell'].split(',')) for q in picked)):
            continue
        picked.append(w)
        if len(picked) >= 5:
            break
    return {'region': region, 'like': want, 'cells': len(figs), 'ref_cells': ref.get('cells', 0), 'layers': layers,
            'score': round(100 * sum(tot) / len(tot)), 'worst': picked}
