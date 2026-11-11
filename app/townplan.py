"""Planning a town in a culture's way: its streets and its plots, from an outline drawn on the land (the user,
2026-10-30: "learn to plan and build towns with previews, at least as nice as the dungeon generator").

Everything is the culture's own, from its towns (townsurvey.py): how wide its streets are and how much of a town is
street, how far back its buildings stand from the street and how far apart, how often they are joined in a row, how
big they are across their front and deep, how many are houses, shops, taverns and the rest, whether it has squares.

  a street culture (Hlaalu, Imperial, Dunmer, Redoran, Reach, Nord ...): a main street along the town's length with a
    gentle bend, streets branching off it a block apart, a square where the culture has them; buildings front every
    street, door to the street, at its setback, in rows as the culture joins them
  a camp (Ashlander): its yurts in a ring, doors to the middle
  an open town (Telvanni, a stronghold): its buildings spread over open ground, apart as the culture's are, facing in

plan() gives streets (as lines with a width), the road patches they paint, a square, and plots (where a building
stands, which way its door opens, how wide and deep, what kind): nothing is placed. The preview draws it; the builder
puts the culture's buildings on the plots."""
import math
import random
import re
from collections import Counter

import mapdata
import townsurvey

PATCH = 512
_BANK = {}                      # (a town of level bands, while its plots are placed: its ground and band streets, _bank_room)
_OBST = {}                      # (what stands in the outline already, while a plan is made: plan() sets it)
MARGIN = 256                    # streets and plots keep this far inside the outline
LANES = 0.5                     # the chance two neighbouring branches are joined by a back lane
WATER_CLEAR = 16                # a building's ground stands this far over the water at least
NO_STREETS = {'Telvanni': 'open', 'Ashlander': 'ring', 'Stronghold': 'open', 'Mine': 'open', 'Cave': 'open'}
_fig = {}


def figures(db):
    """{culture: figures} from the game's towns: width (a street's, units), road (share), setback, joined, gaps, sizes
    [(across, deep)], kinds, squares, layout ('streets', 'ring', 'open')."""
    key = id(db.recs)
    if key in _fig:
        return _fig[key]
    T = townsurvey.survey(db)['towns']
    st = townsurvey.stats(db)
    out = {}
    by = {}
    DL = {}
    for t in T:
        by.setdefault(t['culture'] or '?', []).append(t)
    for c, towns in by.items():
        sizes, setbacks, gaps, dens, roadh, widths = [], [], [], [], [], []
        relief, krad, ksize, order = [], {}, {}, []
        for t in towns:
            roads = {tuple(int(v) for v in k.split(',')) for k in t['roads']}
            bl = t['buildings']
            if len(bl) >= 8:
                order.append(_order([b['face'] for b in bl]))
            if len(bl) >= 5:
                mx = sum(b['x'] for b in bl) / len(bl)
                my = sum(b['y'] for b in bl) / len(bl)
                R = max(math.hypot(b['x'] - mx, b['y'] - my) for b in bl) or 1.0
                for b in bl:
                    krad.setdefault(b['kind'], []).append(math.hypot(b['x'] - mx, b['y'] - my) / R)
                    if b.get('fw') and b.get('fd'):
                        ksize.setdefault(b['kind'], []).append(b['fw'] * b['fd'])
                        fx, fy = math.sin(b['face']), math.cos(b['face'])
                        rect = _rect(b['x'] - fx * b['fd'] / 2, b['y'] - fy * b['fd'] / 2, b['face'], b['fw'], b['fd'])
                        zs = [mapdata.terrain_z(db, x, y) for x, y in rect]
                        if None not in zs:
                            relief.append(max(zs) - min(zs))
            if len(roads) >= 8:
                ws = sorted(townsurvey._widths(t['roads']))
                widths.append(ws[len(ws) // 2])
            if len(t['buildings']) >= 5:
                # (buildings on the town's own ground: its buildings' outline, HULL_PAD out. By the cells they stand in,
                # a plan had a third of the game's buildings: a town fills only part of its cells, lab jtplan2)
                hp = _grow(_hull([(b['x'], b['y']) for b in t['buildings']]), HULL_PAD)
                if len(hp) >= 3:
                    dens.append(len(t['buildings']) / _area(hp) * 1e6)
                    DL.setdefault(c, []).append((math.log(_area(hp) / 1e6), math.log(len(t['buildings']))))
                    roadh.append(_road_share(hp, roads))
            boxes = [b['box'] for b in t['buildings']]
            for i, a in enumerate(boxes):
                best = None
                for j, o in enumerate(boxes):
                    if i != j:
                        d = math.hypot(max(0, max(a[0], o[0]) - min(a[2], o[2])), max(0, max(a[1], o[1]) - min(a[3], o[3])))
                        best = d if best is None or d < best else best
                if best is not None and best >= 8:
                    gaps.append(best)
            for b in t['buildings']:
                if b.get('fw') and b.get('fd') and 150 < b['fw'] < 3000 and 150 < b['fd'] < 3000:
                    sizes.append((b['fw'], b['fd']))
                fx, fy = math.sin(b['face']), math.cos(b['face'])
                for d in range(64, 1025, 64):
                    if (int((b['x'] + fx * d) // PATCH), int((b['y'] + fy * d) // PATCH)) in roads:
                        setbacks.append(d)
                        break
        S = st.get(c) or {}
        g = sorted(gaps)[:int(len(gaps) * 0.9)] or [200.0]
        out[c] = {'width': max(512.0, sum(widths) / len(widths) * PATCH) if widths else 1024.0,
                  'road': S.get('road') or 0.0, 'setback': sorted(setbacks)[len(setbacks) // 2] if setbacks else 192,
                  'joined': S.get('joined') or 0.0, 'gap': g, 'sizes': sizes or [(700, 700)],
                  'dens': sorted(dens)[len(dens) // 2] if dens else 0.3, 'onroad': S.get('door_road') or 0.6,
                  'grid': S.get('square_to_grid') or 0.3, 'roadh': sorted(roadh)[len(roadh) // 2] if roadh else 0.2,
                  # (how uneven the ground under its buildings may be: nine in ten of the culture's stand on less)
                  'relief': min(800.0, max(96.0, sorted(relief)[int(len(relief) * 0.9)] if relief else 256.0)),
                  'krad': {k: sorted(v)[len(v) // 2] for k, v in krad.items() if len(v) >= 3},
                  # (how planned its towns are: Indoril and Reach 0.7, Hlaalu and Imperial 0.55-0.6, Redoran 0.39,
                  # Telvanni 0.36; the user: "Imperial cities tend to be more planned ... Dunmer cities (especially
                  # Telvanni) more fluid and conforming to geography")
                  'order': sorted(order)[len(order) // 2] if order else 0.5,
                  'ksize': {k: sorted(v)[len(v) // 2] for k, v in ksize.items() if len(v) >= 3},
                  'kinds': S.get('kinds') or {'house': 1}, 'square': S.get('square') or 0.0,
                  'layout': NO_STREETS.get(c, 'streets' if (S.get('road') or 0) >= 0.05 else 'open'),
                  'per_cell': S.get('per_cell') or 8.0}
    # (buildings grow slower than their ground: over the game's towns as n = e^k * area^0.58, a small town's own
    # ground mostly the HULL_PAD round it. By one density a culture's small towns came out half the game's (Maar Gan
    # 6 of 15, Vos 2 of 8) and its big ones twice (Anvil's Port Quarter 209 of 110). Each culture takes the curve or
    # the plain density, whichever misses its own towns less: Hlaalu and Redoran keep the density, lab jfit)
    P = [q for v in DL.values() for q in v]
    if len(P) >= 8:
        mx = sum(q[0] for q in P) / len(P)
        my = sum(q[1] for q in P) / len(P)
        sxx = sum((q[0] - mx) ** 2 for q in P)
        sl = min(1.0, max(0.3, sum((q[0] - mx) * (q[1] - my) for q in P) / sxx)) if sxx else 1.0
        for c, v in DL.items():
            if c not in out:
                continue
            k = sorted(q[1] - sl * q[0] for q in v)[len(v) // 2]
            k1 = math.log(out[c]['dens'])
            miss = sorted(abs(q[1] - k - sl * q[0]) for q in v)[len(v) // 2]
            miss1 = sorted(abs(q[1] - k1 - q[0]) for q in v)[len(v) // 2]
            out[c]['dcurve'] = [sl, k] if miss < miss1 else [1.0, k1]
    # (a look whose own towns are forts takes its kin's figures whole: its street share and layout come from the
    # culture's stats, and from its forts alone the classic Imperial town came out open, without a street)
    for c, kin in townsurvey.KIN.items():
        if c in out and kin and kin[0] in out:
            out[c] = dict(out[kin[0]])
    _fig[key] = out
    return out


HULL_PAD = 900                  # a town's own ground: its buildings' outline this far out (as a drawn outline would be)


# ---------------------------------------------------------------- geometry
def _order(faces, tol=math.radians(6)):
    """The share of buildings whose doors face along one grid, at its best angle."""
    best = 0
    for k in range(90):
        a = math.radians(k)
        best = max(best, sum(1 for f in faces if abs(((f - a + math.pi / 4) % (math.pi / 2)) - math.pi / 4) < tol))
    return best / float(max(1, len(faces)))


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for q in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return lo[:-1] + up[:-1]


def _road_share(poly, roads):
    """The share of the outline's patches that are road."""
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    n = r = 0
    for px in range(int(min(xs) // PATCH), int(max(xs) // PATCH) + 1):
        for py in range(int(min(ys) // PATCH), int(max(ys) // PATCH) + 1):
            if _inside(poly, (px + 0.5) * PATCH, (py + 0.5) * PATCH):
                n += 1
                r += (px, py) in roads
    return r / float(n) if n else 0.0


def _grow(poly, d):
    if not poly:
        return poly
    cx = sum(q[0] for q in poly) / len(poly)
    cy = sum(q[1] for q in poly) / len(poly)
    return [(x + (x - cx) / (math.hypot(x - cx, y - cy) or 1) * d, y + (y - cy) / (math.hypot(x - cx, y - cy) or 1) * d) for x, y in poly]


def _inside(poly, x, y):
    c = False
    n = len(poly)
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax:
            c = not c
    return c


def _edge_dist(poly, x, y):
    best = None
    n = len(poly)
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        d = math.hypot(x - ax - t * dx, y - ay - t * dy)
        best = d if best is None or d < best else best
    return best or 0.0


def _in(poly, x, y, margin=MARGIN):
    return _inside(poly, x, y) and _edge_dist(poly, x, y) >= margin


def _axis(poly):
    """The outline's middle and its long axis (a unit vector)."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    sxx = sum((p[0] - cx) ** 2 for p in poly)
    syy = sum((p[1] - cy) ** 2 for p in poly)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in poly)
    a = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return (cx, cy), (math.cos(a), math.sin(a))


# (a Nord village is one road through it, its hall at the heart and the houses along both sides facing it, yards and
# woodpiles between: the game's Skaal Village and Karthgad, and the village rules the user pointed to, 2026-11-01. With
# its branch streets a dozen log houses stood scattered round a smear of cobbles, the user's "Blood Pallage")
VILLAGE_ROAD = {'Nordic'}
VILLAGE_MAX = 20               # (a town of fewer buildings than this is a village: one road)
VILLAGE_WIDTH = 768            # (and a narrow one: a track, not an avenue)
RING_GRID = True               # a walled town's streets on its wall's grid
SPINE_SLOPE = 0.1              # an organic town whose ground rises this much a unit has its main street up the slope
SPINE_RUN = 3000               # ...when the outline runs this far up it
SPINE_ALONG = 0.4              # ...and its buildings are kept nearest the stair street, up and down it counting for this


RING_GRID_RELIEF = 900         # (a town on ground rising more than this inside its outline is no strict grid: a walled one
                               # leaves its wall's grid and a planned one's streets bend along the hill, as hill towns'
                               # do; straight, a walled hilltop city's streets ran down the slopes, a quarter of them
                               # steeper than 0.25, the city round of 2026-11-02)


def _relief(poly, g):
    """How far the ground rises inside the outline (its 90th height over its 10th), or 0 with no ground to ask."""
    if not g:
        return 0.0
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    step = max(256.0, max(max(xs) - min(xs), max(ys) - min(ys)) / 16.0)
    zs = []
    x = min(xs)
    while x <= max(xs):
        y = min(ys)
        while y <= max(ys):
            if _inside(poly, x, y):
                z = g(x, y)
                if z is not None and z > -64:
                    zs.append(z)
            y += step
        x += step
    if len(zs) < 8:
        return 0.0
    zs.sort()
    return zs[int(len(zs) * 0.9)] - zs[int(len(zs) * 0.1)]


def _slope_of(poly, g):
    """The outline's ground as a plane: (uphill x, uphill y, rise a unit), or None with no ground to ask."""
    if not g:
        return None
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    P = []
    step = max(256.0, max(max(xs) - min(xs), max(ys) - min(ys)) / 24.0)
    x = min(xs)
    while x <= max(xs):
        y = min(ys)
        while y <= max(ys):
            if _inside(poly, x, y):
                z = g(x, y)
                if z is not None and z > -64:
                    P.append((x, y, z))
            y += step
        x += step
    if len(P) < 8:
        return None
    n = float(len(P))
    mx, my, mz = sum(p[0] for p in P) / n, sum(p[1] for p in P) / n, sum(p[2] for p in P) / n
    sxx = sum((p[0] - mx) ** 2 for p in P)
    syy = sum((p[1] - my) ** 2 for p in P)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in P)
    sxz = sum((p[0] - mx) * (p[2] - mz) for p in P)
    syz = sum((p[1] - my) * (p[2] - mz) for p in P)
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-6:
        return None
    gx, gy = (sxz * syy - syz * sxy) / det, (syz * sxx - sxz * sxy) / det
    r = math.hypot(gx, gy)
    return (gx / r, gy / r, r) if r > 1e-6 else None


def _run(poly, x, y, ux, uy, step=128, limit=60000):
    """How far from (x, y) along (ux, uy) the outline's inside (with its margin) reaches."""
    d = 0.0
    while d < limit and _in(poly, x + ux * (d + step), y + uy * (d + step)):
        d += step
    return d


def _rect(cx, cy, face, w, d):
    """The four corners of a building w across its front and d deep, its middle at (cx, cy), its door's way face."""
    fx, fy = math.sin(face), math.cos(face)          # (out of the door)
    rx, ry = fy, -fx                                  # (to the right, facing out)
    return [(cx + rx * sx * w / 2 + fx * sy * d / 2, cy + ry * sx * w / 2 + fy * sy * d / 2) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _overlap(a, b):
    """Two convex quads overlap (separating axes)."""
    for poly in (a, b):
        for k in range(4):
            (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % 4]
            nx, ny = y2 - y1, x1 - x2
            pa = [nx * p[0] + ny * p[1] for p in a]
            pb = [nx * p[0] + ny * p[1] for p in b]
            if max(pa) <= min(pb) + 1e-6 or max(pb) <= min(pa) + 1e-6:
                return False
    return True


# ---------------------------------------------------------------- streets
STREET_GRADE = 0.15            # (a street steers along the slope where its line would climb more than this a unit)
STREET_TURN = math.radians(50) # (at most this far off its line)
STREETS_STEER = True


def _steered(poly, x0, y0, ux, uy, length, ground):
    """A street from (x0, y0) along (ux, uy), length long, that keeps under STREET_GRADE where it can: at each PATCH the
    heading nearest its line that climbs no more, as the game's hill towns run their lanes along the hillside and
    the land's own way; straight up, a hillside city's streets were a quarter of them steeper than 0.25 (the game's
    9%), the city round of 2026-11-02. Its points every PATCH."""
    base = math.atan2(uy, ux)
    h, x, y = base, x0, y0
    z = ground(x, y)
    pts = [(round(x, 1), round(y, 1))]
    walked = 0.0
    while walked < length - 1:
        best = None
        for dd in (0, 10, -10, 20, -20, 30, -30, 40, -40, 50, -50):
            t = h + math.radians(dd)
            off = (t - base + math.pi) % (2 * math.pi) - math.pi
            if abs(off) > STREET_TURN:
                continue
            nx_, ny_ = x + math.cos(t) * PATCH, y + math.sin(t) * PATCH
            z2 = ground(nx_, ny_) if z is not None else None
            g = abs(z2 - z) / PATCH if z2 is not None else 0.0
            # (over the grade costs most; then being off its line, then turning)
            c = max(0.0, g - STREET_GRADE) * 40 + abs(off) * 0.6 + abs(math.radians(dd)) * 0.3
            if best is None or c < best[0]:
                best = (c, t, nx_, ny_, z2)
        _c, h, x, y, z2 = best
        z = z2 if z2 is not None else z
        if not _inside(poly, x, y):
            break
        pts.append((round(x, 1), round(y, 1)))
        # (as far along its line as it went: a street turned along the slope goes on until it has gone its length)
        walked += PATCH * max(0.3, math.cos(h - base))
    return pts


def _street(poly, x0, y0, ux, uy, length, bend, rng, ground=None, steer=False):
    """A street from (x0, y0) along (ux, uy), length long, bending gently: its points every PATCH. steer: along the
    slope where the ground is steep (_steered)."""
    if steer and ground and STREETS_STEER:
        return _steered(poly, x0, y0, ux, uy, length, ground)
    nx, ny = -uy, ux
    ph, amp = rng.random() * 6.28, bend * length
    pts = []
    n = max(2, int(length // PATCH) + 1)
    for i in range(n):
        t = i / float(n - 1)
        off = amp * math.sin(ph + t * math.pi * 1.2) - amp * math.sin(ph)
        x, y = x0 + ux * t * length + nx * off, y0 + uy * t * length + ny * off
        if not _inside(poly, x, y):
            break
        # (on across water: a river through the town is bridged, and only the dry patches are painted road; stopped at
        # the water, Balmora's streets ended at the Odai and Seyda Neen's in the sea, lab jtground)
        pts.append((round(x, 1), round(y, 1)))
    return pts


def _until_near(pts, w, streets, room):
    """A branch's points up to where it comes within room of another street (past its own junction): bending with the
    ground, Velothi branches ran into and along one another, a tangle of road with houses stood every which way between
    (lab jpl5, Almas Thirr's outline). It ends there, joined to that street."""
    lead = int(math.ceil(w / PATCH)) + 1
    for i in range(lead, len(pts)):
        x, y = pts[i]
        for o in streets:
            near = (w + o['w']) / 2.0 + room
            if any(abs(qx - x) < near and abs(qy - y) < near and math.hypot(qx - x, qy - y) < near for qx, qy in o['pts']):
                return pts[:i]
    return pts


def _paint(streets, poly, ground=None):
    """The road patches the streets paint, each street its width wide: {(px, py)}."""
    out = set()
    for s in streets:
        w = s['w']
        pts = s['pts']
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay) or 1.0
            for k in range(int(L // 64) + 1):
                t = k * 64 / L
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                r = w / 2.0
                for px in range(int((x - r) // PATCH), int((x + r) // PATCH) + 1):
                    for py in range(int((y - r) // PATCH), int((y + r) // PATCH) + 1):
                        cx, cy = (px + 0.5) * PATCH, (py + 0.5) * PATCH
                        if math.hypot(cx - x, cy - y) <= r and _inside(poly, cx, cy) and not (ground and (ground(cx, cy) or 0) < 0):
                            out.add((px, py))
    return out


def _obstacles(db, poly):
    """What already stands inside the outline and must be kept clear: buildings, doors, walls and other big made
    things, as rects (trees, plants and rocks are left: a town is built among them). The first town laid on the game's
    own world went down over its buildings and statics, 2026-10-30."""
    import cliffrocks
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    out = []
    for gx in range(int(min(xs) // 8192), int(max(xs) // 8192) + 1):
        for gy in range(int(min(ys) // 8192), int(max(ys) // 8192) + 1):
            m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
            for r in m.get('refs') or ():
                b = r.get('b')
                if not b or r['type'] in ('NPC_', 'CREA', 'LEVC'):
                    continue
                low = r['id'].lower()
                if cliffrocks.is_rock(low) or re.search(r'flora|tree|plant|grass|bush|kelp|terrain_', low):
                    continue
                # (what the town clears from its plots anyway, townbuild._clear_ground: Tamriel.esm's boulders blocked
                # most plots of a town on open ground, 8 buildings on one street, the town practice of 2026-10-31)
                import townbuild
                if townbuild.CLEARABLE.search(low) and not townbuild.NOT_CLEARABLE.search(low):
                    continue
                sc = r['s'] or 1.0
                w, d = (b[3] - b[0]) * sc, (b[4] - b[1]) * sc
                if not (r['type'] == 'DOOR' or r.get('arch') or max(w, d) >= 300):
                    continue
                x, y = r['p'][0], r['p'][1]
                if not _inside(poly, x, y) and _edge_dist(poly, x, y) > max(w, d):
                    continue
                c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
                pts = []
                for bx, by in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4])):
                    pts.append((x + bx * sc * c + by * sc * sn, y - bx * sc * sn + by * sc * c))
                out.append(pts)
    return out


# (a walled town stands about twice as close as the culture's open ones: the game's walled towns have 0.5 to 1.3
# buildings a million square units inside their walls, Imperial towns 0.5 in the open; at the open figure half the
# ground inside our walls was empty against a fifth of the game's, lab jhug 2026-10-31)
WALLED_DENS = 2.0
RING_MAIN = 768                # a walled town's main street at most this wide


def plan(db, outline, culture, seed=1, F=None, ground=True, walled=False, ring=False, opts=None):
    """plan_once, and where a seed's streets left no room for a single plot (one street along a narrow island, the
    user's Imperial town of test3), the next few street layouts tried quietly; the same seed still gives the same town.
    walled: the town is to have a wall, so it stands closer. ring: the outline is the inside of its wall, and a street
    runs round just inside it (townbuild.planned). opts: what the user chose (see plan_once)."""
    global CONTOURS
    best = None
    for k in range(6):
        p = plan_once(db, outline, culture, seed + 7919 * k, F, ground, walled, ring, opts)
        if best is None or len(p.get('plots') or ()) > len(best.get('plots') or ()):
            best = p
        if len(best.get('plots') or ()) >= 3:
            break
    # (a hillside's band streets hold fewer houses than a plain plan where the ground is a bowl or a crest of short
    # contours: where they would halve the town, the plain plan stands, steep streets and all; lab hills 2026-11-08,
    # a valley town of 15 came out with 7 on bands)
    if best.get('bands') and CONTOURS:
        try:
            CONTOURS = False
            plain = plan_once(db, outline, culture, seed, F, ground, walled, ring, opts)
        finally:
            CONTOURS = True
        if len(plain.get('plots') or ()) * (BAND_KEEP_STEEP if _BANK.get('S', 0.0) >= BAND_STEEP else BAND_KEEP) > len(best.get('plots') or ()):
            plain['bands_dropped'] = best.get('bands')
            return plain
    return best


def plan_once(db, outline, culture, seed=1, F=None, ground=True, walled=False, ring=False, opts=None):
    """A town for the outline (world points) in the culture's way: {'culture', 'layout', 'streets': [{'pts', 'w'}],
    'roads': [[px, py]], 'square': [x, y, r] or None, 'plots': [{'x', 'y', 'face', 'w', 'd', 'kind', 'door': [x, y]}],
    'figures': {...}}. opts (PIN2's asks, 2026-11-01): 'density' the share of the culture's buildings (1); 'streets' '' the culture's width, 'narrow' or 'lanes'; 'roads'
    [[x, y], ...] lines drawn as its streets, in place of its own; 'zones' [{'kind', 'pts'}] residential, business or
    noble; 'counts' {kind: n} how many of each special building."""
    F = F or figures(db)
    fig = dict(F.get(culture) or F.get('Hlaalu') or next(iter(F.values())))
    fig['_culture'] = culture
    O = opts or {}
    fig['_opts'] = O
    # ("the roads tend to be a bit too big for the kind of towns I'm going for", PIN2: a street is painted in whole
    # land texture squares, 512 across, so a lane is one square)
    if O.get('streets') == 'narrow':
        fig['width'] = max(float(PATCH), fig['width'] * 0.6)
    elif O.get('streets') == 'lanes':
        fig['width'] = float(PATCH)
    drawn = [[(float(x), float(y)) for x, y in r] for r in O.get('roads') or () if len(r) >= 2]
    if drawn:
        fig['_drawn'] = drawn
        fig['layout'] = 'streets'
    if walled:
        fig['dens'] = fig['dens'] * WALLED_DENS
        fig['dcurve'] = None                # (walled towns were measured by the plain density, doubled)
    fig['_ring'] = ring
    if ring:
        # (inside a wall the streets are narrower: Hlaalu's 1,250-wide main street and its ring painted almost all the
        # ground inside the wall road, no room for a house between them, the Tamriel practice; Firewatch's are two patches)
        fig['width'] = min(fig['width'], RING_MAIN)
    if ground is not False:
        memo = {}

        def ground_at(x, y):
            k = (int(x // 64), int(y // 64))
            if k not in memo:
                memo[k] = mapdata.terrain_z(db, x, y)
            return memo[k]
        fig['ground'] = ground_at
    fig['_obst'] = _obstacles(db, [(float(q[0]), float(q[1])) for q in outline]) if ground is not False else []
    _OBST['now'] = fig['_obst']
    _BANK['now'] = None
    # (the seed mixed with the culture: Python's first draw for seeds 1, 3, 4 and 8 is under 0.24, and towns of those
    # seeds all came out square to the compass, lab jtsq)
    rng = random.Random('%d|%s' % (int(seed), culture))
    poly = [(float(p[0]), float(p[1])) for p in outline]
    layout = fig['layout']
    streets, roads, square, plots = [], set(), None, []
    if layout == 'streets':
        # (as much of the town street as the culture's towns have, the town finished: blocks closer or further apart,
        # the nearest kept; Hlaalu's came out with two thirds of Balmora's streets, Mournhold's with half as much again)
        state = rng.getstate()
        target = fig.get('roadh', 0.2)
        best = None
        for spread in (1.0, 0.75, 1.35, 0.55, 1.8):
            rng.setstate(state)
            got = _street_town(poly, fig, rng, spread)
            err = abs(_road_share(poly, {tuple(r) for r in got[1]}) - target) / max(0.02, target)
            if best is None or err < best[0]:
                best = (err, got)
            if err < 0.2 or drawn:
                break
        streets, roads, square, plots = best[1]
        _kinds(plots, fig, poly, square, rng)
        out = {'culture': culture, 'layout': layout, 'streets': streets, 'roads': sorted([list(p) for p in roads]), 'square': square,
               'plots': plots, 'figures': {k: fig[k] for k in ('width', 'setback', 'joined', 'square', 'layout', 'per_cell')},
               'obstacles': [[[round(v, 1) for v in q] for q in o] for o in fig['_obst']]}
        if fig.get('_bands'):
            out['districts'] = _districts(streets, plots, fig)
            out['bands'] = fig['_bands']
        return out
    if False:
        if square:
            sx, sy, sr = square
            for px in range(int((sx - sr) // PATCH), int((sx + sr) // PATCH) + 1):
                for py in range(int((sy - sr) // PATCH), int((sy + sr) // PATCH) + 1):
                    if math.hypot((px + 0.5) * PATCH - sx, (py + 0.5) * PATCH - sy) <= sr and _inside(poly, (px + 0.5) * PATCH, (py + 0.5) * PATCH):
                        roads.add((px, py))
        plots = _front_plots(poly, streets, roads, fig, rng)
        plots += _back_plots(poly, roads, plots, fig, rng)
    elif layout == 'ring':
        plots = _ring_plots(poly, fig, rng)
    else:
        plots = _open_plots(poly, fig, rng)
    plots = _how_many(plots, poly, fig, square, rng)
    if layout == 'streets':
        streets = _trim(streets, plots)
        roads = _paint(streets, poly, fig.get('ground')) | {tuple(r) for r in roads if square and math.hypot((r[0] + 0.5) * PATCH - square[0], (r[1] + 0.5) * PATCH - square[1]) <= square[2]}
    _kinds(plots, fig, poly, square, rng)
    return {'culture': culture, 'layout': layout, 'streets': streets, 'roads': sorted([list(p) for p in roads]), 'square': square,
            'plots': plots, 'figures': {k: fig[k] for k in ('width', 'setback', 'joined', 'square', 'layout', 'per_cell')},
                'obstacles': [[[round(v, 1) for v in q] for q in o] for o in fig['_obst']]}


def _contour_turn(fig, x, y, nx, ny, tx, ty, rng):
    """For an organic town: the turn off square (within 50 degrees) that keeps a branch street most level over its
    first 1500 units, as the game's Dunmer towns run along their hillsides; random on flat ground."""
    g = fig.get('ground')
    if not g:
        return math.radians(rng.uniform(-35, 35))
    z0 = g(x, y)
    if z0 is None:
        return math.radians(rng.uniform(-35, 35))
    best = None
    for deg in range(-50, 51, 10):
        a = math.radians(deg)
        ux, uy = nx * math.cos(a) + tx * math.sin(a), ny * math.cos(a) + ty * math.sin(a)
        rise = 0.0
        for d in (500, 1000, 1500):
            z = g(x + ux * d, y + uy * d)
            rise += abs((z if z is not None else z0) - z0)
        c = rise + rng.random() * 60
        if best is None or c < best[0]:
            best = (c, a)
    flat = best[0] < 120
    return math.radians(rng.uniform(-35, 35)) if flat else best[1]


QUAY_NEAR = 448                # land with water this near is the shore
QUAY_MIN = 2500                # a shore this long inside the outline gets a street along it
QUAY_BEND = 0.3                # ...when it bends no more than this (spread across it for its length)


def _quay(poly, fig):
    """A street along the shore, its houses on the land side facing out over the water and the water side open: the game's
    shore houses stand a median 256-768 from the water and a plan's stood 768-1,024 back, its streets laid across the
    town regardless (Ebonheart, Narsis, Bal Foyen; Hallstatt's lakefront; lab jwet). None where the shore is short or
    winds (an island's round coast)."""
    g = fig['ground']
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    step = 256
    pts = []
    x = min(xs)
    while x <= max(xs):
        y = min(ys)
        while y <= max(ys):
            if _in(poly, x, y):
                z = g(x, y)
                if z is not None and z >= WATER_CLEAR + 48:
                    for dx, dy in ((QUAY_NEAR, 0), (-QUAY_NEAR, 0), (0, QUAY_NEAR), (0, -QUAY_NEAR)):
                        zw = g(x + dx, y + dy)
                        if zw is not None and zw < -32:
                            pts.append((x, y))
                            break
            y += step
        x += step
    if len(pts) < QUAY_MIN / step:
        return None
    n = float(len(pts))
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    a = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ux, uy = math.cos(a), math.sin(a)
    al = [((p[0] - mx) * ux + (p[1] - my) * uy, (p[0] - mx) * -uy + (p[1] - my) * ux) for p in pts]
    lo, hi = min(v[0] for v in al), max(v[0] for v in al)
    if hi - lo < QUAY_MIN:
        return None
    across = math.sqrt(sum(v[1] ** 2 for v in al) / n)
    if across > QUAY_BEND * (hi - lo):
        return None
    # (the shore's line, a point every 384 along it, the longest unbroken run)
    B = {}
    for t, c in al:
        B.setdefault(int((t - lo) // 384), []).append(c)
    runs, cur = [], []
    for k in range(int((hi - lo) // 384) + 1):
        if k in B:
            cur.append(k)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    run = max(runs, key=len)
    if len(run) * 384 < QUAY_MIN:
        return None
    line = []
    for k in run:
        t = lo + (k + 0.5) * 384
        c = sum(B[k]) / len(B[k])
        line.append((mx + ux * t - uy * c, my + uy * t + ux * c))
    return {'pts': line, 'w': max(512.0, fig['width'] * 0.75), 'quay': True}


def _districts(streets, plots, fig):
    """The town's districts on a hillside: each plot belongs to the band (contour street) its door is nearest in height
    and place; [{'level', 'plots', 'x', 'y'}], and each plot's 'band'."""
    bands = [(k, s_) for k, s_ in enumerate(streets) if s_.get('contour')]
    if not bands:
        return []
    g = fig.get('ground')
    out = {}
    for q in plots:
        if not q.get('door'):
            continue
        best = None
        for k, s_ in bands:
            d, _p = _nearest_on(s_['pts'], q['door'][0], q['door'][1])
            dz = abs((g(q['door'][0], q['door'][1]) or s_['level']) - s_['level']) if g else 0.0
            c = d + 3.0 * dz
            if best is None or c < best[0]:
                best = (c, s_['level'])
        q['band'] = best[1]
        o = out.setdefault(best[1], {'level': best[1], 'plots': 0, 'x': 0.0, 'y': 0.0})
        o['plots'] += 1
        o['x'] += q['x']
        o['y'] += q['y']
    for o in out.values():
        o['x'], o['y'] = round(o['x'] / o['plots']), round(o['y'] / o['plots'])
    return [out[k] for k in sorted(out)]


def _street_town(poly, fig, rng, spread):
    """A street town with blocks spread so far apart: (streets, roads, square, plots), finished and trimmed."""
    streets, square = _drawn_streets(poly, fig) if fig.get('_drawn') else _streets(poly, fig, rng, spread)
    if fig.get('_ring'):
        rs = _ring_street(poly, fig)
        if rs:
            streets.extend(rs)
    elif fig.get('ground'):
        qs = _quay(poly, fig)
        if qs:
            streets.append(qs)
    roads = _paint(streets, poly, fig.get('ground'))
    courts = [] if fig.get('_village') else _courts(poly, streets, roads, fig, rng)
    if courts:
        streets += courts
        roads = _paint(streets, poly, fig.get('ground'))
    sq = set()
    if square:
        sx, sy, sr = square
        for px in range(int((sx - sr) // PATCH), int((sx + sr) // PATCH) + 1):
            for py in range(int((sy - sr) // PATCH), int((sy + sr) // PATCH) + 1):
                if math.hypot((px + 0.5) * PATCH - sx, (py + 0.5) * PATCH - sy) <= sr and _inside(poly, (px + 0.5) * PATCH, (py + 0.5) * PATCH):
                    sq.add((px, py))
    roads |= sq
    _BANK['now'] = None
    if fig.get('ground') and BANK_SLOPE <= _BANK.get('S', 0.4) < BAND_STEEP and any(s_.get('level') is not None and len(s_['pts']) > 1 for s_ in streets):
        _BANK['now'] = (fig['ground'], [s_ for s_ in streets if s_.get('level') is not None and len(s_['pts']) > 1])
    plots = _front_plots(poly, streets, roads, fig, rng)
    plots += _back_plots(poly, roads, plots, fig, rng)
    want = int(math.ceil(_want(fig, poly) * 1.15))
    if len(plots) < want:
        plots += _fill_plots(poly, roads, plots, fig, rng, want)
    plots = _how_many(plots, poly, fig, square, rng)
    streets = _trim(streets, plots)
    roads = _paint(streets, poly, fig.get('ground')) | sq
    return streets, roads, square, plots


def _drawn_streets(poly, fig):
    """The streets the user drew (fig['_drawn']), in place of the town's own: each cut where it leaves the outline,
    its points every PATCH as a planned street's are; the longest is the main street, its middle the square where the
    culture has one. (PIN2, 2026-11-01: "draw the roads in the town ... rather than the towns trying to generate its own")"""
    w = fig['width']
    runs = []
    for line in fig['_drawn']:
        run = []
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            L = math.hypot(bx - ax, by - ay) or 1.0
            n = max(1, int(L // PATCH))
            for k in range(n + 1):
                if k == 0 and run:
                    continue
                x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
                if _inside(poly, x, y):
                    run.append((round(x, 1), round(y, 1)))
                elif run:
                    runs.append(run)
                    run = []
        if run:
            runs.append(run)
    runs = [r for r in runs if len(r) >= 2]
    length = lambda r: sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(r, r[1:]))
    runs.sort(key=length, reverse=True)
    fig['_planned'] = False
    streets = [{'pts': r, 'w': w if i == 0 else max(float(PATCH), w * 0.75), 'main': i == 0, 'drawn': True}
               for i, r in enumerate(runs)]
    square = None
    if runs and fig['square'] >= 0.1 and length(runs[0]) > 6000:
        mid = runs[0][len(runs[0]) // 2]
        square = [round(mid[0], 1), round(mid[1], 1), round(max(PATCH * 1.5, w * 0.75), 1)]
    return streets, square


CONTOURS = True
BAND_MIN = 192                 # (a hillside town's streets run in level bands this far apart in height at least...)
BANK_GRADE = 1.2               # (the bank between two bands is given the run to fall no steeper than this: on a 0.42 slope a
                               # band's rise of 576 came every 1,370, the street and a row of houses level across 1,100 of it, and
                               # the 576 fell in the 270 left, sheer banks 570 tall behind the houses, lab gchill 2026-11-10)
BANK_BY = 320                  # (a plot this near a band street stands at its level)
BAND_MAX = 960                 # (...and this much at most: a row's rise on the slope between, so a row of houses stands between
                               # two bands, as the game's hill towns stand: Vos, Akamora, Ald Velothi, Hla Oad; the game's hill
                               # towns' road lies in 3 bands at the median, 404 of rise a band)
BAND_RELIEF = 2 * BAND_MIN     # (an outline whose ground rises this much, 10th to 90th, is a hillside town)
CONTOUR_MIN = 1400             # (a contour street at least this long)
CLIMB_STEP = 128               # (the climbing street is found on a lattice this fine)
CLIMB_GRADE = 0.12             # (it climbs this much a unit by preference...)
CLIMB_MAX = 0.25               # (...and never more: a ramp a walker takes, the game's gate roads at 8-15 degrees)
CLIMB_SLOPE = 0.16             # (a hill this steep is climbed by the found street: steered within 50 degrees, a street on a
                               # 0.4 slope still climbed at 0.26 and more)
RAMP_FAR = 2.5                 # (a band longer than this many blocks past the main street gets a ramp of its own at its far end)
BAND_KEEP = 0.5                # (a band plan is kept while it holds this share of the plain plan's houses at least)
BAND_KEEP_STEEP = 0.4          # (...and this share on ground of BAND_STEEP and more, where the plain plan buries its houses:
BAND_STEEP = 0.5               # on a 0.55 slope it stood 22 for the bands' 14, the land 1,090 over their floors, lab redoran)
BANK_SLOPE = 0.3               # (ground under this median slope has no banks to give room to: its bands are spaced and its
BAND_MAX_GENTLE = 576          # plots stood as before the bank rules, which took a town on a 0.18 slope from 40 houses to
                               # 17, lab gcflat 2026-11-10)
STAIR_HOP = 700                # (two bands this near across are joined by a straight stair street, no ramp sought)
STAIR_WANDER = 2.0             # (a ramp longer than this times the straight way between the bands gives way to a stair street)


def _grid_z(poly, ground, step):
    """{(i, j): z} on a step lattice over the outline (inside it), and the lattice's origin."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    x0, y0 = math.floor(min(xs) / step) * step, math.floor(min(ys) / step) * step
    nx, ny = int((max(xs) - x0) // step) + 2, int((max(ys) - y0) // step) + 2
    Z = {}
    for i in range(nx):
        for j in range(ny):
            x, y = x0 + i * step, y0 + j * step
            if _inside(poly, x, y):
                z = ground(x, y)
                if z is not None and z > -64:
                    Z[(i, j)] = z
    return Z, x0, y0, nx, ny


def _band_slope(poly, ground):
    """The median slope of the ground inside the outline (rise a unit), on a 256 lattice."""
    Z, x0, y0, nx, ny = _grid_z(poly, ground, 256.0)
    slopes = []
    for (i, j), z in Z.items():
        a, b = Z.get((i + 1, j)), Z.get((i, j + 1))
        if a is not None and b is not None:
            slopes.append(math.hypot(a - z, b - z) / 256.0)
    slopes.sort()
    return slopes[len(slopes) // 2] if slopes else 0.0


def _band_levels(poly, ground, block):
    """The heights of a hillside town's level bands: a block's rise on the median slope apart (within BAND_MIN..BAND_MAX),
    from the ground's 10th height up to its 90th. [] on ground too even for bands."""
    Z, x0, y0, nx, ny = _grid_z(poly, ground, 256.0)
    if len(Z) < 16:
        return [], 0.0
    zs = sorted(Z.values())
    lo, hi = zs[int(len(zs) * 0.1)], zs[int(len(zs) * 0.9)]
    if hi - lo < BAND_RELIEF:
        return [], 0.0
    slopes = []
    for (i, j), z in Z.items():
        a, b = Z.get((i + 1, j)), Z.get((i, j + 1))
        if a is not None and b is not None:
            slopes.append(math.hypot(a - z, b - z) / 256.0)
    slopes.sort()
    S = slopes[len(slopes) // 2] if slopes else 0.0
    _BANK['S'] = S
    if S < BANK_SLOPE or S >= BAND_STEEP:
        # (nor has ground of BAND_STEEP and more the room: a town on a 0.55 slope went from 7 houses to 3, lab redoran)
        H = max(BAND_MIN, min(BAND_MAX_GENTLE, block * S))
    else:
        H = max(BAND_MIN, min(BAND_MAX, block * S / (1.0 - min(0.6, S / BANK_GRADE))))
    levels = []
    z = lo + H * 0.5
    while z < hi:
        levels.append(z)
        z += H
    return levels, H


def _contours(poly, ground, level, step=128.0):
    """The level's contour lines inside the outline (marching squares on a step lattice), chained, simplified and
    eased: [[(x, y), ...]] each at least CONTOUR_MIN long, points about PATCH apart."""
    Z, x0, y0, nx, ny = _grid_z(poly, ground, step)
    segs = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            c = [Z.get((i, j)), Z.get((i + 1, j)), Z.get((i + 1, j + 1)), Z.get((i, j + 1))]
            if any(v is None for v in c):
                continue
            P4 = [(x0 + i * step, y0 + j * step), (x0 + (i + 1) * step, y0 + j * step), (x0 + (i + 1) * step, y0 + (j + 1) * step), (x0 + i * step, y0 + (j + 1) * step)]
            cross = []
            for k in range(4):
                a, b = c[k], c[(k + 1) % 4]
                if (a < level) != (b < level):
                    t = (level - a) / (b - a)
                    ax, ay = P4[k]
                    bx, by = P4[(k + 1) % 4]
                    cross.append((round(ax + (bx - ax) * t, 1), round(ay + (by - ay) * t, 1)))
            if len(cross) == 2:
                segs.append((cross[0], cross[1]))
            elif len(cross) == 4:
                segs.append((cross[0], cross[1]))
                segs.append((cross[2], cross[3]))
    # (chain the segments end to end)
    ends = {}
    for n_, (a, b) in enumerate(segs):
        ends.setdefault(a, []).append(n_)
        ends.setdefault(b, []).append(n_)
    used = [False] * len(segs)
    lines = []
    for n_ in range(len(segs)):
        if used[n_]:
            continue
        used[n_] = True
        line = [segs[n_][0], segs[n_][1]]
        for side in (1, -1):
            while True:
                tip = line[-1] if side == 1 else line[0]
                nxt = [m for m in ends.get(tip, ()) if not used[m]]
                if not nxt:
                    break
                m = nxt[0]
                used[m] = True
                a, b = segs[m]
                p = b if a == tip else a
                if side == 1:
                    line.append(p)
                else:
                    line.insert(0, p)
        lines.append(line)
    out = []
    for line in lines:
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:]))
        if L < CONTOUR_MIN:
            continue
        out.append(_resample(_ease(_simplify(_average(line, 2), 64.0), 1), PATCH))
    out.sort(key=lambda l: -len(l))
    return out


def _average(pts, k):
    """A polyline's points each averaged with the k either side (its ends kept): the lattice's wobble taken out."""
    n = len(pts)
    if n < 3:
        return pts
    out = []
    for i in range(n):
        lo, hi = max(0, i - k), min(n - 1, i + k)
        m = hi - lo + 1
        out.append((sum(p[0] for p in pts[lo:hi + 1]) / m, sum(p[1] for p in pts[lo:hi + 1]) / m))
    out[0], out[-1] = pts[0], pts[-1]
    return out


def _simplify(pts, tol):
    """Douglas-Peucker: the polyline with the points within tol of the lines between the rest left out."""
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    L = math.hypot(bx - ax, by - ay)
    worst, wi = -1.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / L if L > 1e-6 else math.hypot(x - ax, y - ay)
        if d > worst:
            worst, wi = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[:wi + 1], tol)[:-1] + _simplify(pts[wi:], tol)


def _ease(pts, rounds=2):
    """A polyline rounded (Chaikin), its ends kept."""
    for _ in range(rounds):
        if len(pts) < 3:
            return pts
        q = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            q.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            q.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        q.append(pts[-1])
        pts = q
    return pts


def _resample(pts, step):
    """The polyline's points every step along it (its ends kept)."""
    if len(pts) < 2:
        return [(round(x, 1), round(y, 1)) for x, y in pts]
    out = [pts[0]]
    carry = 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        d = step - carry
        while d <= L:
            out.append((a[0] + (b[0] - a[0]) * d / L, a[1] + (b[1] - a[1]) * d / L))
            d += step
        carry = L - (d - step)
    if math.hypot(out[-1][0] - pts[-1][0], out[-1][1] - pts[-1][1]) > step * 0.4:
        out.append(pts[-1])
    else:
        out[-1] = pts[-1]
    return [(round(x, 1), round(y, 1)) for x, y in out]


def _climb(poly, ground, x0, y0, x1, y1, step=CLIMB_STEP):
    """A street from (x0, y0) to near (x1, y1) that climbs at most CLIMB_MAX a unit and by preference CLIMB_GRADE, found
    on a lattice inside the outline with moves up to two steps long (a switchback where the hill is steep); eased and
    its points every PATCH. None when there is none."""
    import heapq
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    ox, oy = math.floor(min(xs) / step) * step, math.floor(min(ys) / step) * step
    nx, ny = int((max(xs) - ox) // step) + 2, int((max(ys) - oy) // step) + 2
    si, sj = int(round((x0 - ox) / step)), int(round((y0 - oy) / step))
    ti, tj = int(round((x1 - ox) / step)), int(round((y1 - oy) / step))
    zs, ins = {}, {}

    def at(i, j):
        if (i, j) not in zs:
            x, y = ox + i * step, oy + j * step
            ok = 0 <= i < nx and 0 <= j < ny and (_inside(poly, x, y) or (abs(i - si) + abs(j - sj) <= 1) or (abs(i - ti) + abs(j - tj) <= 1))
            z = ground(x, y) if ok else None
            zs[(i, j)] = z if (z is not None and z > -64) else None
        return zs[(i, j)]
    # (moves up to four steps long: a traverse across the slope at an angle; two-step moves alone could not climb a
    # 0.5 slope under the grade)
    moves = [(a * sa, b * sb) for a, b in ((1, 0), (0, 1), (1, 1), (1, 2), (2, 1), (1, 3), (3, 1), (1, 4), (4, 1), (2, 3), (3, 2))
             for sa in (1, -1) for sb in (1, -1) if not ((a == 0 and sa < 0) or (b == 0 and sb < 0))]
    dist = {(si, sj): 0.0}
    prev = {}
    heap = [(0.0, si, sj)]
    seen = 0
    while heap:
        c, i, j = heapq.heappop(heap)
        if c > dist.get((i, j), 1e18):
            continue
        if abs(i - ti) <= 1 and abs(j - tj) <= 1:
            way, k = [], (i, j)
            while k in prev:
                way.append((ox + k[0] * step, oy + k[1] * step))
                k = prev[k]
            way.append((x0, y0))
            way = way[::-1]
            way[-1] = (x1, y1)
            return _resample(_ease(_simplify(_average(way, 1), 48.0), 2), PATCH)
        seen += 1
        if seen > 80000:
            return None
        zi = at(i, j)
        if zi is None:
            continue
        for da, db_ in moves:
            a, b = i + da, j + db_
            zb = at(a, b)
            if zb is None:
                continue
            ln = step * math.hypot(da, db_)
            g = abs(zb - zi) / ln
            m = max(abs(da), abs(db_))
            bad = False
            for t in range(1, m):
                u = t / float(m)
                xi, yi = ox + (i + da * u) * step, oy + (j + db_ * u) * step
                zm = ground(xi, yi)
                if zm is None or not _inside(poly, xi, yi) or abs(zm - (zi + (zb - zi) * u)) > 256:
                    bad = True
                    break
            if bad:
                continue
            if g > CLIMB_MAX:
                continue
            nc = c + ln * (1.0 + 8.0 * max(0.0, g - CLIMB_GRADE) / CLIMB_GRADE)
            if nc < dist.get((a, b), 1e18):
                dist[(a, b)] = nc
                prev[(a, b)] = (i, j)
                heapq.heappush(heap, (nc, a, b))
    return None


def _band_ramps(poly, ground, bands, block, w):
    """Ramps between neighbouring bands: from points along each band (its middle, then its ends and quarters) up to the
    nearest point of the band above within 3 blocks, found at a walkable grade (_climb); one at least a pair of levels
    where there is one, a second where the band runs on past RAMP_FAR blocks from the first. [{'pts', 'w', 'ramp'}]"""
    by_level = {}
    for b_ in bands:
        by_level.setdefault(b_['level'], []).append(b_)
    lv = sorted(by_level)
    out = []
    for lo_, hi_ in zip(lv, lv[1:]):
        up = [p_ for u_ in by_level[hi_] for p_ in u_['pts']]
        if not up:
            continue
        done = []
        for b_ in by_level[lo_]:
            pts_ = b_['pts']
            if len(pts_) < 2:
                continue
            starts = [pts_[len(pts_) // 2], pts_[0], pts_[-1]] + pts_[len(pts_) // 4:len(pts_) // 4 + 1] + pts_[3 * len(pts_) // 4:3 * len(pts_) // 4 + 1]
            for s_ in starts:
                if done and min(math.hypot(s_[0] - d_[0], s_[1] - d_[1]) for d_ in done) < RAMP_FAR * block:
                    continue
                tgt = min(up, key=lambda p_: math.hypot(p_[0] - s_[0], p_[1] - s_[1]))
                if math.hypot(tgt[0] - s_[0], tgt[1] - s_[1]) > 3 * block:
                    continue
                d_ = math.hypot(tgt[0] - s_[0], tgt[1] - s_[1])
                ramp = _climb(poly, ground, s_[0], s_[1], tgt[0], tgt[1]) if d_ > STAIR_HOP else None
                # (a ramp that must wander more than STAIR_WANDER times the straight way for its grade, or a short hop,
                # is a stair street instead: straight up between the bands, as Vivec's and Tel Mora's steps go; the
                # found ramps zigzagged 3,000 units across a 0.4 slope, lab hills 2026-11-08)
                if ramp and sum(math.hypot(b2[0] - a2[0], b2[1] - a2[1]) for a2, b2 in zip(ramp, ramp[1:])) > STAIR_WANDER * d_ + 256:
                    ramp = None
                if ramp and len(ramp) >= 2:
                    out.append({'pts': ramp, 'w': float(PATCH), 'main': False, 'ramp': True})
                else:
                    out.append({'pts': _resample([s_, tgt], PATCH), 'w': float(PATCH), 'main': False, 'ramp': True, 'stair': True})
                done.append(s_)
                if len(done) >= 2:
                    break
    return out


def _grades(pts, ground):
    """The rise a unit between a polyline's points, as the ground has it."""
    out = []
    for a, b in zip(pts, pts[1:]):
        za, zb = ground(a[0], a[1]), ground(b[0], b[1])
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if za is not None and zb is not None and L > 1:
            out.append(abs(zb - za) / L)
    return out


def _nearest_on(pts, x, y):
    """The point of a polyline nearest (x, y) and its distance."""
    best = None
    for p in pts:
        d = math.hypot(p[0] - x, p[1] - y)
        if best is None or d < best[0]:
            best = (d, p)
    return best


def _streets(poly, fig, rng, spread=1.0):
    """The main street along the town's length, branches a block apart off both sides, a square where the culture has
    them."""
    (cx, cy), (ax, ay) = _axis(poly)
    w = fig['width']
    # (some of a culture's towns are laid square to the compass, straight streets crossing square, as often as its
    # buildings stand square: half the game's do, a plan's one in eight, lab jtplan2)
    # (planned, one grid, straight streets crossing square, as often as the culture's towns are; else organic, its
    # streets bending with the ground. A planned town is squared to the compass when its outline lies near it (squared
    # in a diagonal outline, Caldera's plan got a short main street and a dozen buildings), else to its own length)
    # (a planned town's buildings nearly all share its grid, an organic one's about a third by chance: planned as often
    # as brings the town's share to the culture's. Planned at the culture's share itself, Common came out 0.89 on one
    # grid against the game's 0.49, lab jtplan3)
    planned = rng.random() < min(0.95, max(0.02, (fig.get('order', 0.5) - 0.35) / 0.6))
    fig['_planned'] = planned
    a = math.atan2(ay, ax)
    grid = planned
    if planned and abs(a - round(a / (math.pi / 2)) * (math.pi / 2)) < math.radians(25):
        a = round(a / (math.pi / 2)) * (math.pi / 2)
    elif not planned:
        # (off the compass: the game's own outlines mostly lie north-south, and a free plan in them came out square
        # all the same, seven in ten buildings against the game's half, lab jtplan2)
        q = round(a / (math.pi / 2)) * (math.pi / 2)
        if abs(a - q) < math.radians(12):
            a = q + rng.choice((-1, 1)) * math.radians(rng.uniform(12, 35))
    # (on a hillside the main street climbs it, a stair street, and the branches run off it along the slope, each with
    # its row above it looking down over the roofs below: Oia's, Hallstatt's and Akamora's way; along the outline's
    # length, the main street ran straight down the hill and its houses faced sideways, lab jvert1. A planned town too:
    # its grid turned up the slope is terraces, its cross streets level, as Hlaalu's hill towns are)
    sp = _slope_of(poly, fig.get('ground'))
    if sp and sp[2] >= SPINE_SLOPE and _run(poly, cx, cy, sp[0], sp[1]) + _run(poly, cx, cy, -sp[0], -sp[1]) >= SPINE_RUN:
        a = math.atan2(sp[1], sp[0]) + (0.0 if planned else math.radians(rng.uniform(-10, 10)))
        fig['_spine'] = (sp[0], sp[1])
    steep = _relief(poly, fig.get('ground')) >= RING_GRID_RELIEF
    if fig.get('_ring') and RING_GRID and not steep:
        # (inside a wall one grid, the wall's: its streets along and square to its sides, so the inner blocks line up with
        # the rows backing the wall. Off at the culture's branch angles, a walled Imperial town's middle was a jumble of
        # guild halls and temples at odd turns, "more random than real cities", the user's Tessellated Shores, 2026-11-01)
        n_ = len(poly)
        e = max(range(n_), key=lambda k: math.hypot(poly[(k + 1) % n_][0] - poly[k][0], poly[(k + 1) % n_][1] - poly[k][1]))
        ea = math.atan2(poly[(e + 1) % n_][1] - poly[e][1], poly[(e + 1) % n_][0] - poly[e][0])
        a = min((ea + k * math.pi / 2 for k in range(4)), key=lambda t: abs((t - a + math.pi) % (2 * math.pi) - math.pi))
        planned = grid = True
        fig['_planned'] = True
    village = fig.get('_culture') in VILLAGE_ROAD and not fig.get('_ring') and _want(fig, poly) < VILLAGE_MAX
    fig['_village'] = village
    if village:
        w = fig['width'] = min(fig['width'], VILLAGE_WIDTH)
    ax, ay = math.cos(a), math.sin(a)
    back = _run(poly, cx, cy, -ax, -ay)
    fwd = _run(poly, cx, cy, ax, ay)
    x0, y0 = cx - ax * back, cy - ay * back
    main = _street(poly, x0, y0, ax, ay, back + fwd, 0.0 if grid else 0.05 + rng.random() * 0.05, rng, fig.get('ground'),
                   steer=(not grid or steep) and not fig.get('_spine'))
    # (a hillside town: its streets in level bands along the slope, a block apart up it, and the main street climbing
    # through them at a walkable grade, switching back where the hill is steep; the rows along each band are its
    # districts. Straight up the slope a town's streets were a quarter of them over 0.25 and its doors hung over the
    # drop; the user, 2026-11-07: "lay down streets over elevation so the homes are accessible and cluster together")
    sizes = fig['sizes']
    deep = sorted(d for _w, d in sizes)[len(sizes) // 2]
    across = sorted(w_ for w_, _d in sizes)[len(sizes) // 2]
    block = max(4 * across, 2 * (deep + fig['setback']) + w + 256) * spread
    bands = []
    if CONTOURS and fig.get('ground') and not fig.get('_drawn') and not village:
        # (a band's rise: a row of houses each side of the street between two bands, no more)
        levels, H = _band_levels(poly, fig['ground'], (2 * (deep + fig['setback']) + max(512, w * 0.75) + 128) * spread)
        if levels:
            # (lanes: a hill town's streets along its slope are narrow, Vos's and Hla Oad's one patch wide; wider, their
            # painted road took the rows' ground and the band streets came out bare, lab hills 2026-11-08)
            for lv in levels:
                for line in _contours(poly, fig['ground'], lv):
                    bands.append({'pts': line, 'w': float(PATCH), 'main': False, 'contour': True, 'level': round(lv)})
            # (a town that wants more houses than its bands' rows hold packs its bands a single row apart, the houses
            # stepped up the slope as Tel Mora's and Vos's are: two rows apart, a walled town on a 0.4 slope came out
            # with 17 buildings where its density asked 44, lab hills 2026-11-08)
            room = sum(sum(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) for a_, b_ in zip(l_['pts'], l_['pts'][1:])) for l_ in bands) * 2.0 / (across + 200.0)
            if bands and _want(fig, poly) > 0.9 * room:
                levels2, H2 = _band_levels(poly, fig['ground'], (deep + fig['setback'] + PATCH + 128) * spread)
                if len(levels2) > len(levels):
                    levels, H = levels2, H2
                    bands = []
                    for lv in levels:
                        for line in _contours(poly, fig['ground'], lv):
                            bands.append({'pts': line, 'w': float(PATCH), 'main': False, 'contour': True, 'level': round(lv)})
            # (the main street is the longest band nearest the middle level, at the main street's width: a street up
            # the slope was the town's steepest, and one found climbing wandered in an arc for its grade; the bands
            # are joined by short ramps, _band_ramps)
            if bands:
                mid = levels[len(levels) // 2]
                best = min(bands, key=lambda b_: (abs(b_['level'] - round(mid)), -len(b_['pts'])))
                bands.remove(best)
                main = best['pts']
                # (no wider than half the ground between two bands: at its culture's full width on a 0.45 slope, a
                # Gold Coast main street 1,638 across took the band beside it and 730 of rise, lab hills 2026-11-08)
                spacing = H / max(0.02, _band_slope(poly, fig['ground']))
                w = fig['_main_w'] = max(float(PATCH), min(w, spacing * 0.5))
                best.update({'w': w, 'main': True})
                bands.insert(0, best)
            fig['_bands'] = {'levels': [round(v) for v in levels], 'rise': round(H), 'streets': len(bands)}
    streets = [{'pts': main, 'w': w, 'main': True}] if not bands else []
    # (a block: a building's depth and its setback each side of a street, twice over, and the street: the branch
    # streets run this far apart, so a row of buildings faces each)
    nx, ny = -ay, ax
    L = math.hypot(main[-1][0] - main[0][0], main[-1][1] - main[0][1]) if len(main) > 1 else 0
    k = 0
    d = block * (0.6 + 0.3 * rng.random())
    if bands:
        # (the bands are the streets; each joined to the band above by a ramp at a walkable grade, two where it is
        # long: at its middle and at the end farthest from the first)
        streets.extend(bands)
        d = L
        streets.extend(_band_ramps(poly, fig['ground'], bands, block, w))
    while d < L - block * 0.4 and len(main) > 2 and not village:
        i = min(len(main) - 2, int(d // PATCH))
        bx, by = main[i]
        tx, ty = main[i + 1][0] - bx, main[i + 1][1] - by
        tl = math.hypot(tx, ty) or 1.0
        px_, py_ = -ty / tl, tx / tl
        sides = (1, -1) if rng.random() < 0.6 else ((1,) if k % 2 == 0 else (-1,))
        for sd in sides:
            # (off at an angle, not square: the game's branch streets leave its main street every which way)
            a = 0.0 if grid else _contour_turn(fig, bx, by, px_ * sd, py_ * sd, tx / tl, ty / tl, rng)
            ux = px_ * sd * math.cos(a) + tx / tl * math.sin(a)
            uy = py_ * sd * math.cos(a) + ty / tl * math.sin(a)
            reach = _run(poly, bx + ux * w, by + uy * w, ux, uy)
            if reach < deep * 1.5:
                continue
            ln = reach * (0.65 + 0.35 * rng.random())
            br = _street(poly, bx, by, ux, uy, ln + w / 2, 0.0 if grid else 0.03 * rng.random(), rng, fig.get('ground'), steer=not grid or steep)
            bw_ = max(512, w * (0.75 if w > 512 else 1))
            br = _until_near(br, bw_, [o for o in streets if not o.get('main')], deep + fig['setback'])
            if len(br) >= 3:
                streets.append({'pts': br, 'w': max(512, w * (0.75 if w > 512 else 1)), 'main': False, 'side': sd})
        k += 1
        d += block * (0.85 + 0.3 * rng.random())
    # (back lanes: two neighbouring branches on one side joined near their far ends now and then, making blocks and
    # loops; a main street with dead-end branches read as a comb beside the game's towns)
    br = [s for s in streets if not s.get('main') and not s.get('contour') and not s.get('ramp')]
    for side in (1, -1):
        mine = [s for s in br if s.get('side') == side]
        for a_, b_ in zip(mine, mine[1:]):
            if rng.random() > LANES:
                continue
            n = min(len(a_['pts']), len(b_['pts']))
            i = max(1, int(n * rng.uniform(0.55, 0.9)) - 1)
            pa, pb = a_['pts'][min(i, len(a_['pts']) - 1)], b_['pts'][min(i, len(b_['pts']) - 1)]
            dl = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            if dl < block * 0.5 or dl > block * 1.8 or not _inside(poly, (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2):
                continue
            lane = _street(poly, pa[0], pa[1], (pb[0] - pa[0]) / dl, (pb[1] - pa[1]) / dl, dl, 0.0, rng)
            if len(lane) >= 2:
                streets.append({'pts': lane, 'w': max(512, w * 0.75), 'main': False, 'lane': True})
    square = None
    if fig['square'] >= 0.1 and L > 6000:
        mid = main[len(main) // 2]
        # (a square the street's width across and a half: at 1.2 times its width each way Hlaalu's was a bare dirt field
        # 3,000 across with the houses far round its edge, the practice renders u_hla)
        square = [round(mid[0], 1), round(mid[1], 1), round(max(PATCH * 1.5, w * 0.75), 1)]
    return streets, square


def inset(poly, d):
    """A polygon of square corners moved in by d on every side."""
    n = len(poly)
    area = sum(poly[k][0] * poly[(k + 1) % n][1] - poly[(k + 1) % n][0] * poly[k][1] for k in range(n))
    sg = 1.0 if area > 0 else -1.0                # (counter-clockwise: the inside is to the left of each side)

    def nrm(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        h = math.hypot(dx, dy) or 1.0
        return -dy / h * sg, dx / h * sg
    out = []
    for k in range(n):
        n1 = nrm(poly[k - 1], poly[k])
        n2 = nrm(poly[k], poly[(k + 1) % n])
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        f = d / (1.0 + dot) if dot > -0.9 else d
        out.append((poly[k][0] + (n1[0] + n2[0]) * f, poly[k][1] + (n1[1] + n2[1]) * f))
    return out


def _ring_street(poly, fig):
    """The street round the inside of a town wall (poly: the ground inside it), a row's depth in from it, so a row of
    buildings stands between it and the wall, backs to the wall and doors to the street, as walled towns are built. Planned
    without it, a walled town's streets ran down its middle only and its buildings stood in a blob, the wall round them
    two fifths empty, and the doors off the streets opened onto each other's walls (the Tamriel practice, 2026-11-01;
    the user: "entrances tend to line up along streets, common access coves"). A list."""
    sizes = fig['sizes']
    deep = sorted(d for _w, d in sizes)[len(sizes) // 2]
    w = 512.0
    r = inset(poly, deep + fig['setback'] + w / 2 + 64)
    if len(r) < 3 or _area(r) < 0.2 * _area(poly):
        return None
    # (a list, though one: on a hillside its steep stretches were tried left out, and the town's streets came out steeper
    # still, a fifth of its road over 0.25 against 7% with the lane whole, lab r20)
    return [{'pts': [(round(x, 1), round(y, 1)) for x, y in r + [r[0]]], 'w': w, 'main': False, 'ring': True}]


COURT = 640                    # a court's half width: a small yard shared by the doors round it
COURT_FAR = 1700               # opened where the ground lies this far from any street
COURT_APART = 3200


def _courts(poly, streets, roads, fig, rng):
    """Courts: where a block is too deep for its streets' rows to reach, a small yard in it, joined to the nearest
    street by a short lane, for the houses round it to face (the user, the practice night: "entrances tend to line up
    along streets, common access coves ... the feeling of being 'lived in'"). Streets [{'pts', 'w', 'court'|'lane'}]."""
    if not roads:
        return []
    main = next((s_ for s_ in streets if s_.get('main')), None)
    if main and len(main['pts']) > 1:
        a = math.atan2(main['pts'][-1][1] - main['pts'][0][1], main['pts'][-1][0] - main['pts'][0][0])
    else:
        a = 0.0
    ux, uy = math.cos(a), math.sin(a)
    R = [((px + 0.5) * PATCH, (py + 0.5) * PATCH) for px, py in roads]
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    cand = []
    for gx in range(int(min(xs)), int(max(xs)), PATCH):
        for gy in range(int(min(ys)), int(max(ys)), PATCH):
            if not _in(poly, gx, gy, COURT + 900):
                continue
            d = min(math.hypot(gx - rx, gy - ry) for rx, ry in R)
            if d >= COURT_FAR:
                cand.append((d + rng.random() * 200, gx, gy))
    cand.sort(reverse=True)
    out, at = [], []
    for d, gx, gy in cand:
        if any(math.hypot(gx - x_, gy - y_) < COURT_APART for x_, y_ in at):
            continue
        corners = [(gx + ux * sx * COURT - uy * sy * COURT, gy + uy * sx * COURT + ux * sy * COURT) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        if not all(_in(poly, x_, y_, 256) for x_, y_ in corners):
            continue
        rx, ry = min(R, key=lambda r: math.hypot(r[0] - gx, r[1] - gy))
        L = math.hypot(rx - gx, ry - gy)
        out.append({'pts': [(round(x_, 1), round(y_, 1)) for x_, y_ in corners + [corners[0]]], 'w': 512.0, 'main': False, 'court': True})
        out.append({'pts': [(round(gx, 1), round(gy, 1)), (round(rx, 1), round(ry, 1))], 'w': 512.0, 'main': False, 'lane': True,
                    'len': L})
        at.append((gx, gy))
    return out


def _sizes(fig, rng):
    w, d = fig['sizes'][rng.randrange(len(fig['sizes']))]
    return float(w), float(d)


DOOR_REACH = 1536              # a back building's door turns to a street this near it


def _door_turn(x, y, face, bd, roads, g=None):
    """Of the four ways a building off the street may face, the one whose door meets a street soonest (its own way
    first on a tie), None where no street lies within DOOR_REACH: the game's back rows open onto lanes and yards that
    lead out, and turned at random a plan's opened onto the backs of the street row (the user: entrances line up along
    streets and shared coves)."""
    best = None
    up = _uphill(g, x, y)
    for k, t in enumerate((0.0, math.pi / 2, -math.pi / 2, math.pi)):
        f = face + t
        fx, fy = math.sin(f), math.cos(f)
        for d in range(int(bd / 2), int(bd / 2) + DOOR_REACH, 64):
            if (int((x + fx * d) // PATCH), int((y + fy * d) // PATCH)) in roads:
                c = d + (0 if k == 0 else 96) + (UPHILL_COST * max(0.0, fx * up[0] + fy * up[1]) if up else 0.0)
                if best is None or c < best[0]:
                    best = (c, f % (2 * math.pi))
                break
    return best[1] if best else None


def _uphill(g, x, y):
    """The way up the slope at a point (unit x, y), or None on level ground (rise under 0.12) or with no ground to ask."""
    if not g:
        return None
    zs = [g(x + a, y + b) for a, b in ((384, 0), (-384, 0), (0, 384), (0, -384))]
    if None in zs:
        return None
    gx, gy = (zs[0] - zs[1]) / 768.0, (zs[2] - zs[3]) / 768.0
    r = math.hypot(gx, gy)
    return (gx / r, gy / r) if r >= 0.12 else None


TERRACE_TOL = 256              # the ground under a plot is moved at most this far (townbuild._terrace)


def _level(fig, rect):
    """The ground under a building's footprint is dry and no more uneven than under the culture's own (fig['ground']:
    the land's height at a point, or none to ask)."""
    g = fig.get('ground')
    if not g:
        return True
    cx = sum(q[0] for q in rect) / 4
    cy = sum(q[1] for q in rect) / 4
    zs = [g(x, y) for x, y in rect]
    zc = g(cx, cy)
    # (its middle on dry ground, its corners at most a little under the water, as the game's shore houses stand; and
    # the ground no more uneven than under the culture's own, with a quarter to spare)
    if zc is None or zc < WATER_CLEAR or any(z is None or z < -96 for z in zs):
        return False
    # (and up to two terrace tolerances more: the town terraces each plot before its building goes down,
    # townbuild._terrace; refused on a hillside, a town of 30 plots came out with 2 to 6 buildings far apart)
    if max(zs + [zc]) - min(zs + [zc]) > fig['relief'] * 1.25 + 2 * TERRACE_TOL:
        return False
    return _door_front(g, rect)


DOOR_DROP = 128                # the ground out of a door may fall this far below its step within DOOR_OUT
DOOR_CLIMB = 192               # ...or rise this far over it (a door into a bank)
DOOR_OUT = 320


def _door_front(g, rect):
    """The ground out of the door (the middle of the rect's front edge, out along its face) walkable: no drop off a
    cliff, no water, no bank rising against it. The game's hill towns open 3.2% of their doors off a drop and 0.2% into
    a bank; a plan's opened 6.2% and 2.0%, houses crowded to a headland's cliff edge (the user: "we don't want doors
    opening off bare cliffs", lab jdrop)."""
    fx0, fy0 = (rect[2][0] + rect[3][0]) / 2.0, (rect[2][1] + rect[3][1]) / 2.0
    cx, cy = sum(q[0] for q in rect) / 4.0, sum(q[1] for q in rect) / 4.0
    L = math.hypot(fx0 - cx, fy0 - cy) or 1.0
    ux, uy = (fx0 - cx) / L, (fy0 - cy) / L
    z0 = g(fx0 + ux * 64, fy0 + uy * 64)
    if z0 is None:
        return False
    for d in range(128, DOOR_OUT + 1, 64):
        z = g(fx0 + ux * d, fy0 + uy * d)
        if z is None or (z < -16 <= z0) or z0 - z > DOOR_DROP or z - z0 > DOOR_CLIMB:
            return False
    return True


def _free(rect, plots, roads, poly, road_rect=None):
    """Inside the outline, off the road (road_rect: the part that must be, a building's front may meet the road's
    edge as the game's do) and clear of the other plots."""
    if not all(_in(poly, x, y, 64) for x, y in rect):
        return False
    rr = road_rect or rect
    cx = sum(p[0] for p in rr) / 4
    cy = sum(p[1] for p in rr) / 4
    for x, y in rr + [(cx, cy)] + [((rr[i][0] + rr[(i + 1) % 4][0]) / 2, (rr[i][1] + rr[(i + 1) % 4][1]) / 2) for i in range(4)]:
        if (int(x // PATCH), int(y // PATCH)) in roads:
            return False
    if any(_overlap(rect, p['rect']) for p in plots) or any(_overlap(rect, o) for o in _OBST.get('now') or ()):
        return False
    return not _BANK.get('now') or _bank_room(rect, plots)


def _pt_line(pts, x, y):
    """How far (x, y) is from a polyline."""
    best = 9e9
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
        best = min(best, math.hypot(x - ax - dx * t, y - ay - dy * t))
    return best


def _bank_lv(rect):
    """The level a plot will stand at in a town of level bands: its band street's where it stands by one, else its
    own ground's; and the points of its edge."""
    g, streets = _BANK['now']
    pts = list(rect) + [((rect[i][0] + rect[(i + 1) % 4][0]) / 2, (rect[i][1] + rect[(i + 1) % 4][1]) / 2) for i in range(4)]
    near = [(min(_pt_line(o['pts'], x, y) for x, y in pts) - o['w'] / 2, o['level']) for o in streets]
    d, lv = min(near)
    if d > BANK_BY:
        lv = g(sum(p[0] for p in rect) / 4, sum(p[1] for p in rect) / 4)
    return lv, pts, near


def _bank_room(rect, plots):
    """A plot in a town of level bands leaves the bank its run: the streets and plots of another level stand as far
    off as the height between them at BANK_GRADE."""
    lv, pts, near = _bank_lv(rect)
    if lv is None:
        return True
    if any(d < abs(o - lv) / BANK_GRADE for d, o in near):
        return False
    for p in plots:
        if 'lv' not in p:
            p['lv'] = _bank_lv(p['rect'])[0]
        if p['lv'] is None:
            continue
        need = abs(p['lv'] - lv) / BANK_GRADE
        if need > 64 and any(abs(x - p['x']) < need + 900 and abs(y - p['y']) < need + 900 and math.hypot(x - u, y - v) < need
                             for x, y in pts for u, v in p['rect']):
            return False
    return True


def _front_plots(poly, streets, roads, fig, rng):
    """Buildings along both sides of every street, door to it, at the culture's setback; joined in rows as often as the
    culture joins them, else apart by one of its gaps."""
    plots = []
    gaps = fig['gap'] or [120.0]
    # (the main street's rows first, then the waterfront's: last, the branches had taken the shore and a quay got 2 to 8
    # buildings of a town's 17 to 125, lab jquay)
    for si, s in sorted(enumerate(streets), key=lambda e: 0 if e[1].get('main') else 1 if e[1].get('quay') else 2):
        pts, w = s['pts'], s['w']
        if len(pts) < 2:
            continue
        sides = (1, -1)
        if s.get('court'):
            # (round a court only its outside, doors in to the yard: a house set in the yard closed it)
            ar = sum(pts[k][0] * pts[k + 1][1] - pts[k + 1][0] * pts[k][1] for k in range(len(pts) - 1))
            sides = (-1,) if ar > 0 else (1,)
        for side in sides:
            dist = rng.random() * 300
            seg_len = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
            total = sum(seg_len)
            while dist < total:
                bw, bd = _sizes(fig, rng)
                at = dist + bw / 2
                if at > total:
                    break
                i, acc = 0, 0.0
                while i < len(seg_len) - 1 and acc + seg_len[i] < at:
                    acc += seg_len[i]
                    i += 1
                t = (at - acc) / (seg_len[i] or 1.0)
                (ax, ay), (bx, by) = pts[i], pts[i + 1]
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                tx, ty = (bx - ax) / (seg_len[i] or 1.0), (by - ay) / (seg_len[i] or 1.0)
                nx, ny = -ty * side, tx * side
                setback = fig['setback'] * (0.8 + 0.4 * rng.random())
                doorx, doory = x + nx * (w / 2 + setback - 64), y + ny * (w / 2 + setback - 64)
                cxx, cyy = x + nx * (w / 2 + setback + bd / 2), y + ny * (w / 2 + setback + bd / 2)
                face = math.atan2(-nx, -ny)
                if not fig.get('_planned', True):
                    # (a few degrees off: the street's bends turn an organic town's rows. Thirty off, Balmora's plan came
                    # out 0.36 on one grid against the game's 0.88, its doors no longer in a line, lab jun1)
                    face += math.radians(rng.uniform(-FACE_JIT, FACE_JIT))
                g = fig.get('ground')
                upface = False
                if g and not s.get('court'):
                    # (on a hillside, the row above the street: the game's doors face downhill twice as often as by chance
                    # and uphill half as often, each row looking out over the street and the roofs below it; a plan
                    # lining both sides faced uphill as often as down, lab jvert1. The row below is kept but taken last,
                    # _how_many: left out, a big town lost street plots the fill could not replace, Anvil's Port Quarter
                    # 84 of the game's 110, jpq)
                    z0, z1 = g(x, y), g(cxx, cyy)
                    upface = z0 is not None and z1 is not None and z0 - z1 > HILL_RISE * math.hypot(cxx - x, cyy - y)
                rect = _rect(cxx, cyy, face, bw, bd)
                # (off the road but for its front: the patch grid paints a street up to most of a patch wider than it is)
                slack = min(bd * 0.5, PATCH * 0.7)
                inner = _rect(cxx + nx * slack / 2, cyy + ny * slack / 2, face, bw * 0.85, bd - slack)
                if _free(rect, plots, roads, poly, inner) and _level(fig, rect):
                    plots.append({'x': round(cxx, 1), 'y': round(cyy, 1), 'face': round(face, 4), 'w': round(bw), 'd': round(bd),
                                  'door': [round(doorx, 1), round(doory, 1)], 'rect': rect, 'street': True, 'si': si, 'at': at, 'sd': side})
                    if upface:
                        plots[-1]['upface'] = True
                    gap = 0.0 if rng.random() < _pair_rate(fig) else gaps[rng.randrange(len(gaps))] * GAP_SCALE * (0.7 + 0.6 * rng.random())
                    dist += bw + gap
                else:
                    dist += 192
    return plots


# (the nearest of all a building's neighbours is the gap the game's figures give: spaced by them along a street alone,
# buildings came out half as far apart as the game's, lab jtplan2)
GAP_SCALE = 1.6
FACE_JIT = 6                    # (degrees an organic town's street building may stand off its street)
HILL_RISE = 0.1                 # a street-side plot whose middle stands this far under the street a unit out is the downhill row
HILL_SKIP = 0.85                # a fill facing up a slope is left out so often (game towns on slopes: doors down 0.46, up 0.13)
UPFACE_LAST = 3.0              # the downhill row's plots count this much further from the middle when a town is cut to size
OPEN_DOWN = 0.75                # an open town's building on a slope faces down it this often, else the middle
UPHILL_COST = 640               # a back building turned to face uphill counts as its door this much further from a street


def _pair_rate(fig):
    """The chance a building is joined to the one beside it, so the share joined to any comes out as the culture's:
    a building has about two such neighbours."""
    j = min(0.95, max(0.0, fig.get('joined', 0.0)))
    return 1.0 - math.sqrt(1.0 - j)


def _then(first, grows):
    """Every item of first, then those added to grows while first was gone through."""
    for q in first:
        yield q
    for q in list(grows):
        yield q


def _back_plots(poly, roads, front, fig, rng):
    """The second row: buildings behind the street ones and in the yards between, door to the nearest street but
    not onto it (a third of the game's doors open onto no road; every plan door did, lab jtplan2)."""
    gaps = fig['gap'] or [200.0]
    plots = list(front)
    out = []
    R = list(roads)
    # (behind the street row, then a third row behind the second)
    second = sorted(front, key=lambda _q: rng.random())
    for f in _then(second, out):
        fx, fy = math.sin(f['face']), math.cos(f['face'])
        for _t in range(6):
            bw, bd = _sizes(fig, rng)
            gap = 0.0 if rng.random() < _pair_rate(fig) else gaps[rng.randrange(len(gaps))] * GAP_SCALE * (0.8 + 0.4 * rng.random())
            back = f['d'] / 2 + gap + bd / 2
            side = (rng.random() - 0.5) * f['w']
            x, y = f['x'] - fx * back + fy * side, f['y'] - fy * back - fx * side
            face = f['face'] if rng.random() < 0.6 else f['face'] + rng.choice((math.pi / 2, -math.pi / 2, math.pi))
            turn = _door_turn(x, y, face, bd, roads, fig.get('ground'))
            face = face if turn is None else turn
            rect = _rect(x, y, face, bw, bd)
            pad = 0.0 if gap == 0.0 else gaps[rng.randrange(len(gaps))]
            roomy = _rect(x, y, face, bw + 2 * pad, bd + 2 * pad) if pad else rect
            if _free(rect, plots, roads, poly) and (not pad or not any(_overlap(roomy, o['rect']) for o in plots if o is not f)) and _level(fig, rect):
                gx, gy = math.sin(face), math.cos(face)
                q = {'x': round(x, 1), 'y': round(y, 1), 'face': round(face % (2 * math.pi), 4), 'w': round(bw), 'd': round(bd),
                     'door': [round(x + gx * bd / 2, 1), round(y + gy * bd / 2, 1)], 'rect': rect, 'back': True}
                plots.append(q)
                out.append(q)
                break
    return out


FILL_TRIES = 1500


def _fill_plots(poly, roads, plots, fig, rng, want):
    """Buildings beside the ones laid, their fronts in line and facing the same way, until the town has as many as the
    culture's stand on so much ground: two streets of big Hlaalu houses, a row behind each, came to 11 of the 17 the
    game's Hlaalu towns stand on such ground, far apart on open grass (the Tamriel practice, 2026-10-31)."""
    gaps = fig['gap'] or [200.0]
    plots = list(plots)
    out = []
    for _t in range(FILL_TRIES):
        if len(plots) >= want or not plots:
            break
        f = plots[rng.randrange(len(plots))]
        fx, fy = math.sin(f['face']), math.cos(f['face'])
        bw, bd = _sizes(fig, rng)
        gap = 0.0 if rng.random() < _pair_rate(fig) else gaps[rng.randrange(len(gaps))] * GAP_SCALE * (0.8 + 0.4 * rng.random())
        behind = rng.random() < 0.4
        if behind:
            # (or behind it, backs together, as the game's blocks fill between their streets)
            side = (rng.random() - 0.5) * max(0.0, f['w'] - bw)
            fwd = -(f['d'] / 2 + gap + bd / 2)
        else:
            side = rng.choice((1.0, -1.0)) * (f['w'] / 2 + gap + bw / 2)
            fwd = (f['d'] - bd) / 2                  # (fronts in line)
        x, y = f['x'] + fy * side + fx * fwd, f['y'] - fx * side + fy * fwd
        # (behind: backs together, its door the other way; facing the same way it opened onto the first one's back wall,
        # one door in seven shut, lab jdoor0)
        face = (f['face'] + math.pi) % (2 * math.pi) if behind else f['face']
        if behind:
            turn = _door_turn(x, y, face, bd, roads, fig.get('ground'))
            face = face if turn is None else turn
        up = _uphill(fig.get('ground'), x, y)
        if up and math.sin(face) * up[0] + math.cos(face) * up[1] > 0.707 and rng.random() < HILL_SKIP:
            continue                    # (facing up the hill: the hillside's rows look down it, _front_plots)
        rect = _rect(x, y, face, bw, bd)
        inner = None
        if f.get('street') and not behind:
            slack = min(bd * 0.5, PATCH * 0.7)
            inner = _rect(x - fx * slack / 2, y - fy * slack / 2, f['face'], bw * 0.85, bd - slack)
        pad = 0.0 if gap == 0.0 else gaps[rng.randrange(len(gaps))]
        roomy = _rect(x, y, f['face'], bw + 2 * pad, bd + 2 * pad) if pad else rect
        if _free(rect, plots, roads, poly, inner) and (not pad or not any(_overlap(roomy, o['rect']) for o in plots if o is not f)) \
                and _level(fig, rect):
            ux, uy = math.sin(face), math.cos(face)
            q = {'x': round(x, 1), 'y': round(y, 1), 'face': round(face, 4), 'w': round(bw), 'd': round(bd),
                 'door': [round(x + ux * bd / 2, 1), round(y + uy * bd / 2, 1)], 'rect': rect}
            if f.get('street') and not behind:
                # (its place along the street: aside along the building is back along the street on its right-hand side)
                q.update(street=True, si=f['si'], at=f['at'] - f.get('sd', 1) * side, sd=f.get('sd', 1))
            else:
                q['back'] = True
            plots.append(q)
            out.append(q)
    return out


def _ring_plots(poly, fig, rng):
    """A camp: its buildings round the middle, door to it, in one ring (two for a big outline)."""
    (cx, cy), _a = _axis(poly)
    plots = []
    reach = min(_run(poly, cx, cy, math.cos(a), math.sin(a)) for a in [k * math.pi / 4 for k in range(8)])
    # (four rings: the game's camps are tight clusters; spaced a yurt's depth and a gap apart, a camp lost half its yurts
    # and almost none touched, against two in three of the game's, lab jtplan2)
    for r in (reach * 0.25, reach * 0.45, reach * 0.65, reach * 0.85):
        if r < 400:
            continue
        a0 = a = rng.random() * 2 * math.pi
        while a < a0 + 2 * math.pi - 0.2 and len(plots) < 60:
            bw, bd = _sizes(fig, rng)
            x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
            face = math.atan2(cx - x, cy - y)
            rect = _rect(x, y, face, bw, bd)
            if _free(rect, plots, set(), poly) and _level(fig, rect):
                fx, fy = math.sin(face), math.cos(face)
                plots.append({'x': round(x, 1), 'y': round(y, 1), 'face': round(face, 4), 'w': round(bw), 'd': round(bd),
                              'door': [round(x + fx * bd / 2, 1), round(y + fy * bd / 2, 1)], 'rect': rect})
            g = 0.0 if rng.random() < _pair_rate(fig) else (fig['gap'] or [300.0])[rng.randrange(len(fig['gap'] or [300.0]))]
            a += (bw + g * (0.7 + 0.6 * rng.random())) / r
    return plots


def _open_plots(poly, fig, rng):
    """An open town: buildings spread over the ground as far apart as the culture's, each facing the middle."""
    (cx, cy), _a = _axis(poly)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    gaps = fig['gap'] or [300.0]
    plots = []
    for _t in range(1500):
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if not _in(poly, x, y):
            continue
        bw, bd = _sizes(fig, rng)
        face = math.atan2(cx - x, cy - y) + (rng.random() - 0.5) * 0.8
        up = _uphill(fig.get('ground'), x, y)
        if up and rng.random() < OPEN_DOWN:
            # (on a slope out over it: Telvanni towns' doors face downhill 0.6 of the time; facing the middle, a hilltop
            # town's faced up the hill four times in five, lab jvert2)
            face = math.atan2(-up[0], -up[1]) + (rng.random() - 0.5) * 0.8
        # (a full gap clear all round: Sadrith Mora's towers stand 430 apart, a plan's stood 150)
        g = gaps[rng.randrange(len(gaps))]
        rect = _rect(x, y, face, bw + 2 * g, bd + 2 * g)
        if _free(rect, plots, set(), poly) and _level(fig, _rect(x, y, face, bw, bd)):
            fx, fy = math.sin(face), math.cos(face)
            plots.append({'x': round(x, 1), 'y': round(y, 1), 'face': round(face, 4), 'w': round(bw), 'd': round(bd),
                          'door': [round(x + fx * bd / 2, 1), round(y + fy * bd / 2, 1)], 'rect': rect})
    return plots


def _area(poly):
    return abs(sum(poly[k][0] * poly[(k + 1) % len(poly)][1] - poly[(k + 1) % len(poly)][0] * poly[k][1] for k in range(len(poly)))) / 2.0


def _want(fig, poly):
    """How many buildings the culture's towns stand on so much ground (figures' dcurve, else its density)."""
    a = _area(poly) / 1e6
    sl, k = fig.get('dcurve') or (1.0, math.log(max(1e-6, fig['dens'])))
    return math.exp(k) * a ** sl


def _how_many(plots, poly, fig, square, rng):
    """As many buildings as the culture's towns stand on so much ground (its buildings a cell), the ones nearest the
    middle (the square, else the outline's middle) and on the main street first: the game's towns gather round their
    middle and leave open ground, and a plan filling the whole outline had three times Dreynim's buildings."""
    # (Density: the user's own share of the culture's figure, 0.3 to 4; a big Dunmer outline drawn as a city stood a
    # village's cluster in open country, the user 2026-11-03)
    dens = max(0.3, min(4.0, float((fig.get('_opts') or {}).get('density') or 1.0)))
    want = max(3, int(round(_want(fig, poly) * dens * rng.uniform(0.85, 1.15))))
    if fig.get('_ring'):
        if dens >= 1.0:
            return list(plots)              # (a walled town fills its wall: every plot its streets have room for)
        want = max(3, int(round(len(plots) * dens)))   # (thinner than its wall's room: the nearest the middle)
    if fig['layout'] != 'streets':
        # (an open town or a camp spreads over its ground: nearest the middle first crowded Sadrith Mora's towers into
        # a ring round its centre)
        plots = list(plots)
        rng.shuffle(plots)
        return plots[:want]
    (cx, cy), _a = _axis(poly)
    if square:
        cx, cy = square[0], square[1]
    near = lambda p: math.hypot(p['x'] - cx, p['y'] - cy) * (0.75 if p.get('si') == 0 else 1.0)
    if fig.get('_spine'):
        # (a hill town climbs its stair street: up and down the slope counts for less, and Hla Oad's 37 plots spanning
        # 2,360 of height kept the 21 round the middle, 710 of it, against the game's 2,080, lab jvert4)
        ux, uy = fig['_spine']

        def near(p):
            dx, dy = p['x'] - cx, p['y'] - cy
            al = dx * ux + dy * uy
            return math.hypot(al * SPINE_ALONG, dx * -uy + dy * ux) * (0.75 if p.get('si') == 0 else 1.0)
    near0 = near
    near = lambda p: near0(p) * (UPFACE_LAST if p.get('upface') else 1.0)
    front = sorted((p for p in plots if not p.get('back')), key=near)
    back = sorted((p for p in plots if p.get('back')), key=near)
    nf = int(round(want * fig.get('onroad', 0.6)))
    got = front[:nf]
    got += back[:want - len(got)]
    if len(got) < want:
        got += front[nf:nf + want - len(got)]
    # (a back building whose street building was left out stands alone in a yard: fine, the game has those too)
    return got


def _trim(streets, plots):
    """Each street to its last building (and a little on); a branch with none goes. The main street runs on to the
    outline: the road out of town."""
    out = []
    for si, s in enumerate(streets):
        if s.get('main') or s.get('ring') or s.get('court') or s.get('len') or s.get('drawn') or s.get('ramp'):
            out.append(s)                    # (a court and its lane whole: cut short, a court was left with no way in;
            continue                         # a ramp between two bands whole: it has no rows of its own)
        ats = [p['at'] for p in plots if p.get('si') == si]
        if s.get('contour'):
            # (a band street whole, along its contour to the outline, where it has a row at all: the road out of town)
            if ats:
                out.append(s)
            continue
        if not ats:
            continue
        end, n = max(ats) + 600, 1
        acc = 0.0
        pts = s['pts']
        while n < len(pts) and acc < end:
            acc += math.hypot(pts[n][0] - pts[n - 1][0], pts[n][1] - pts[n - 1][1])
            n += 1
        out.append(dict(s, pts=pts[:n]))
    return out


SKIP_CULTURES = ('?', 'Cave', 'Mine', 'Skyrim')


def cultures(db):
    """[{'id', 'towns', 'layout', 'examples'}]: the cultures with towns enough to plan by, the most towns first."""
    st = townsurvey.stats(db)
    F = figures(db)
    out = [{'id': c, 'towns': len(S['towns']), 'layout': F[c]['layout'], 'examples': [t for t in S['towns'] if t and t != '?'][:4]}
           for c, S in st.items() if c not in SKIP_CULTURES and len(S['towns']) >= 3]
    return sorted(out, key=lambda o: -o['towns'])


def nearest_culture(db, outline):
    """The culture of the game's town nearest the outline's middle."""
    cx = sum(p[0] for p in outline) / len(outline)
    cy = sum(p[1] for p in outline) / len(outline)
    best = None
    ok = {c['id'] for c in cultures(db)}
    for t in townsurvey.survey(db)['towns']:
        if t['culture'] not in ok or not t['buildings']:
            continue
        x = sum(b['x'] for b in t['buildings']) / len(t['buildings'])
        y = sum(b['y'] for b in t['buildings']) / len(t['buildings'])
        d = math.hypot(x - cx, y - cy)
        if best is None or d < best[0]:
            best = (d, t['culture'])
    return best[1] if best else 'Hlaalu'


SPECIAL = ('tavern', 'temple', 'guild', 'shop', 'manor', 'guard')
# what goes in each zone drawn in a town (PIN2: "residential, business, noble")
ZONE_KINDS = {'residential': (), 'business': ('shop', 'tavern', 'guild'), 'noble': ('manor', 'temple')}
ZONE_COST = 6.0


def _kinds(plots, fig, poly, square, rng):
    """What each building is, in the culture's mix: the special ones (a tavern, a temple, a guild hall, shops, a manor,
    a guard post) nearest the square or the middle and on the main street, houses the rest."""
    import towntrade
    kinds = {k: v for k, v in fig['kinds'].items() if k != 'other'}
    tot = float(sum(kinds.values()) or 1)
    n = len(plots)
    O = fig.get('_opts') or {}
    # (what the town lives by leans its mix as the game's towns of that trade lean: a farm town's fewer shops and guard
    # posts, a mine town's more shops, taverns and guild halls; towntrade.KIND_LIFT)
    lift = towntrade.kind_lift(O.get('trade'))
    want = Counter()
    for k in SPECIAL:
        share = kinds.get(k, 0) / tot * lift.get(k, 1.0)
        c = share * n
        want[k] = int(c) + (1 if rng.random() < c - int(c) else 0)
    if n >= 8 and kinds.get('tavern'):
        want['tavern'] = max(1, want['tavern'])
    counts = O.get('counts') or {}
    for k in SPECIAL:
        # (as many as the user asked for, where they did: PIN2's "specify if it's gonna have guildhalls, chapels ...
        # how many shops")
        if counts.get(k) is not None:
            want[k] = max(0, min(n, int(counts[k])))
    zones = [(z['kind'], [(float(x), float(y)) for x, y in z['pts']]) for z in O.get('zones') or ()
             if z.get('kind') in ZONE_KINDS and len(z.get('pts') or ()) >= 3]
    for p in plots:
        p.pop('zone', None)
        for zk, zp in zones:
            if _inside(zp, p['x'], p['y']):
                p['zone'] = zk
                break
    drawn_for = {k for zk, _zp in zones for k in ZONE_KINDS[zk]}
    # (each kind where the culture's stand, as far out from the town's middle as theirs (a guard post at the edge, a
    # tavern near the middle), and on a plot about their size: given out nearest-first, a temple could be the smallest
    # building in town)
    if not n:
        return
    mx = sum(p['x'] for p in plots) / n
    my = sum(p['y'] for p in plots) / n
    R = max(math.hypot(p['x'] - mx, p['y'] - my) for p in plots) or 1.0
    free = set(range(n))
    for k in ('temple', 'manor', 'guild', 'tavern', 'guard', 'shop'):
        kr = (fig.get('krad') or {}).get(k, 0.35)
        ks = (fig.get('ksize') or {}).get(k)
        for _j in range(want[k]):
            if not free:
                break
            def cost(i):
                p = plots[i]
                c = 2.0 * abs(math.hypot(p['x'] - mx, p['y'] - my) / R - kr)
                if ks:
                    c += abs(math.log(max(1.0, p['w'] * p['d']) / ks))
                # (zones: a kind goes in its own zone where one is drawn, and never into another's)
                z = p.get('zone')
                if z and k not in ZONE_KINDS[z]:
                    c += ZONE_COST
                elif k in drawn_for and z is None:
                    c += ZONE_COST / 2
                return c + rng.random() * 0.15
            best = min(free, key=cost)
            plots[best]['kind'] = k
            free.discard(best)
    for p in plots:
        p.setdefault('kind', 'house')
        # (the rest of a noble quarter are manors, of a business quarter every other one a shop, unless how many
        # manors or shops was set)
        if p['kind'] == 'house':
            if p.get('zone') == 'noble' and counts.get('manor') is None:
                p['kind'] = 'manor'
            elif p.get('zone') == 'business' and counts.get('shop') is None and rng.random() < 0.5:
                p['kind'] = 'shop'
        p['rect'] = [[round(x, 1), round(y, 1)] for x, y in p['rect']]
