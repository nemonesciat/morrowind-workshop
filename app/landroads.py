"""Roads between settlements, the way the game's run (docs/terrain-tools-research-2026-11.md, P11): proposed as 'road'
layers of the land plan (a line each), laid by Shape the ground: the bed cut level across and eased along, the
culture's road texture painted on it.

The game's roads between towns (lab a12, 2026-11-08: Vvardenfell and TR outside the towns' cells, the 512 patches of
a road texture): 4.4% of the land, about 5,800 units of road a land cell; climbing 4 degrees at the median along the
way (16 at 90%, 33 at 99%, measured over 1,024), 8 across; on ground half as steep as the land round it (median 11
against 21 degrees); winding 1.4-2.3 times the straight line between the towns they join (median 1.7); 88 of 115
towns with a road within three cells.

  route    the settlements (the plan's town layers and the game's own towns near the marked cells) joined as road
           networks join them, each pair no third settlement lies nearer both of (the relative neighbourhood graph:
           the shortest ways and the ones that go round, none that cuts across another town); each way the least
           cost path on a 256 lattice in the corridor between its ends, up to four steps a move (a traverse
           across a slope at an angle), costing more the steeper past GRADE, never steeper than GRADE_MAX
           (switchbacks come of it), never through the water or a building; straightened (Chaikin) and its ends
           cut back to the towns' outlines (the streets inside are the town's)
  bed      the ground under the road level across it (HALF either side of its line, feathered over FEATHER) and
           eased along it (a running mean, its steepest steps spread), never under a held building
  paint    the 512 patches whose middle is within PAINT of the line, in the road texture of the culture's nearest
           towns (townbuild.road_texture)"""
import heapq
import math

STEP = 256.0
GRADE = 0.08                    # (tan of 4.6 degrees: the game's median; past it a step costs more)
GRADE_MAX = 0.36                # (tan of 20 degrees: none steeper, measured over a 256 step)
WATER = 24.0                    # (ground this low is water: no bridges yet)
ROAD_MAX = 60000.0              # (settlements further apart than this get no road of their own)
CORRIDOR = 0.5                  # (the search keeps within this share of the way's length of the straight line, at least 4,096)
HALF = 160.0                    # (the bed level across within this of the line ...)
FEATHER = 256.0                 # (... easing back to the ground over this)
PAINT = 256.0
EASE = 4                        # (points of 64 either side in the bed's running mean along the way)
VISITS = 250000
# bridges: a straight jump over water from bank to bank, up to BRIDGE_STEPS lattice steps, costing BRIDGE_COST times
# its length and BRIDGE_FIXED besides (a road goes round a pond, over a river)
BRIDGE_STEPS = 8                # (2,048 at 256)
BRIDGE_COST = 4.0
BRIDGE_FIXED = 3000.0
BANK = 256.0                    # (the bridge reaches this far onto each bank)
RAMP = 1024.0                   # (the road rises to the deck over this, each end)
RAMP_GRADE = 0.15               # (... longer where the deck stands high: no steeper than this at the middle of it)
RAMP_MAX = 3072.0
TIP_PAD = 96.0                  # (the ground at the deck's height this far past an end piece's outer tip)
# the game's bridges as kits (lab a13, 2026-11-08: every piece a family chains along its own x, all at one level, the
# deck level with the banks and at least `clear` over the water; ends turned outward): end piece (reaching `out` past
# its origin outward and `in` inward), middle piece `step` long, the deck's top `top` over a piece's origin, a pier
# every other middle `pier_dz` under it
BRIDGES = {
    'highway': {'end': 't_imp_highway_bridgeramp_01', 'out': 491.0, 'in': 0.0, 'mid': 't_imp_highway_bridge_01', 'step': 512.0, 'top': 296.0,
                'pier': 't_imp_highway_bridgebot_01', 'pier_dz': -736.0, 'clear': 508.0},
    'anvil': {'end': 't_imp_setanv_x_bridge_01', 'out': 128.0, 'in': 128.0, 'mid': 't_imp_setanv_x_bridge_02', 'step': 512.0, 'top': 394.0,
              'pier': None, 'pier_dz': 0.0, 'clear': 466.0},
    'hlaalu': {'end': 'ex_hlaalu_bridge_04', 'out': 176.0, 'in': 128.0, 'mid': 'ex_hlaalu_bridge_01', 'step': 256.0, 'top': 266.0,
               'pier': None, 'pier_dz': 0.0, 'clear': 251.0},
    'imperial': {'end': 'ex_imp_bridge_02', 'out': 350.0, 'in': 256.0, 'mid': 'ex_imp_bridge_01', 'step': 512.0, 'top': 409.0,
                 'pier': None, 'pier_dz': 0.0, 'clear': 585.0},
}
BRIDGE_OF = {'Gold Coast': 'anvil', 'Imperial': 'imperial', 'Nordic': 'highway', 'Reach': 'highway'}     # (the rest, Dunmer: hlaalu)


def _towns(db, keys, layers):
    """[(x, y, r, culture, name, outline)]: the plan's town layers (their middles, their furthest point, their
    outlines) and the game's towns within two cells of the marked ones (no outline: a circle of r)."""
    import townsurvey
    out = []
    for L in layers or []:
        if L.get('kind') != 'town' or L.get('on', True) is False or len(L.get('pts') or []) < 3:
            continue
        xs, ys = [p[0] for p in L['pts']], [p[1] for p in L['pts']]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        r = max(math.hypot(x - cx, y - cy) for x, y in zip(xs, ys))
        out.append((cx, cy, r, (L.get('p') or {}).get('culture') or '', L.get('name') or (L.get('p') or {}).get('name') or (L.get('p') or {}).get('place') or '',
                    [tuple(p) for p in L['pts']]))
    if keys:
        gx0, gx1 = min(k[0] for k in keys) - 2, max(k[0] for k in keys) + 2
        gy0, gy1 = min(k[1] for k in keys) - 2, max(k[1] for k in keys) + 2
        for t in townsurvey.survey(db)['towns']:
            b = t.get('buildings') or []
            if len(b) < 3:
                continue
            cx, cy = sum(q['x'] for q in b) / len(b), sum(q['y'] for q in b) / len(b)
            if not (gx0 * 8192 <= cx < (gx1 + 1) * 8192 and gy0 * 8192 <= cy < (gy1 + 1) * 8192):
                continue
            if any(math.hypot(cx - o[0], cy - o[1]) < o[2] + 1024 for o in out):
                continue
            r = sorted(math.hypot(q['x'] - cx, q['y'] - cy) for q in b)[int(0.9 * (len(b) - 1))]
            out.append((cx, cy, r, t.get('culture') or '', t.get('name') or '', None))
    return out


def _pairs(towns):
    """The relative neighbourhood graph's edges no longer than ROAD_MAX: (a, b) with no third town nearer both."""
    out = []
    n = len(towns)
    for a in range(n):
        for b in range(a + 1, n):
            d = math.hypot(towns[a][0] - towns[b][0], towns[a][1] - towns[b][1])
            if d > ROAD_MAX:
                continue
            if any(max(math.hypot(towns[c][0] - towns[a][0], towns[c][1] - towns[a][1]),
                       math.hypot(towns[c][0] - towns[b][0], towns[c][1] - towns[b][1])) < d for c in range(n) if c not in (a, b)):
                continue
            out.append((a, b, d))
    return out


class Ground:
    """The land's heights at every 128 (the cells' own grid), read once a cell, and the ground held under buildings."""

    def __init__(self, db):
        import mapdata
        self.db, self.cells = db, {}
        self.mapdata = mapdata
        self.boxes = {}

    def z(self, x, y):
        gx, gy = math.floor(x / 8192.0), math.floor(y / 8192.0)
        c = self.cells.get((gx, gy))
        if c is None:
            L = self.mapdata.land(self.db, gx, gy)
            c = self.cells[(gx, gy)] = L['h'] if L.get('exists') else False
        if c is False:
            return None
        fx, fy = (x - gx * 8192.0) / 128.0, (y - gy * 8192.0) / 128.0
        i, j = min(63, int(fx)), min(63, int(fy))
        tx, ty = fx - i, fy - j
        return ((c[j * 65 + i] * (1 - tx) + c[j * 65 + i + 1] * tx) * (1 - ty)
                + (c[(j + 1) * 65 + i] * (1 - tx) + c[(j + 1) * 65 + i + 1] * tx) * ty)

    def built(self, x, y):
        """Whether a building (a held piece, landshapes.held_kind) stands within 128 of the point."""
        import landshapes
        gx, gy = math.floor(x / 8192.0), math.floor(y / 8192.0)
        if (gx, gy) not in self.boxes:
            lst = []
            m = self.mapdata.cellmap(self.db, '#%d,%d' % (gx, gy))
            for r in m.get('refs') or []:
                if landshapes.held_kind(r) == 'hold' and r.get('b'):
                    b, s = r['b'], r.get('s') or 1.0
                    rad = max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) * s + 128
                    lst.append((r['p'][0], r['p'][1], rad))
            self.boxes[(gx, gy)] = lst
        return any((x - bx) ** 2 + (y - by) ** 2 < rr * rr for bx, by, rr in self.boxes[(gx, gy)])


MOVES = [(a * sa, b * sb) for a, b in ((1, 0), (0, 1), (1, 1), (1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2))
         for sa in (1, -1) for sb in (1, -1) if not ((a == 0 and sa < 0) or (b == 0 and sb < 0))]


def path(G, x0, y0, x1, y1, free=()):
    """The least cost way from (x0, y0) to (x1, y1) on a STEP lattice: ([(x, y)], [bridges: ((x, y), (x, y))]) or
    None. free: (x, y, r) round the ends where buildings don't bar the way (the towns themselves)."""
    L = math.hypot(x1 - x0, y1 - y0)
    pad = max(4096.0, CORRIDOR * L)
    ox, oy = math.floor((min(x0, x1) - pad) / STEP) * STEP, math.floor((min(y0, y1) - pad) / STEP) * STEP
    nx, ny = int((max(x0, x1) + pad - ox) // STEP) + 1, int((max(y0, y1) + pad - oy) // STEP) + 1
    si, sj = int(round((x0 - ox) / STEP)), int(round((y0 - oy) / STEP))
    ti, tj = int(round((x1 - ox) / STEP)), int(round((y1 - oy) / STEP))
    zs = {}

    def at(i, j):
        k = (i, j)
        if k not in zs:
            x, y = ox + i * STEP, oy + j * STEP
            z = G.z(x, y) if 0 <= i < nx and 0 <= j < ny else None
            if z is not None and (z < WATER or (G.built(x, y) and not any((x - fx) ** 2 + (y - fy) ** 2 < fr * fr for fx, fy, fr in free))):
                z = None
            zs[k] = z
        return zs[k]
    h = lambda i, j: math.hypot(i - ti, j - tj) * STEP           # (A*: the straight way's length, never more than the cost)
    dist = {(si, sj): 0.0}
    prev = {}
    jump = set()
    heap = [(h(si, sj), 0.0, si, sj)]
    seen = 0
    while heap:
        _f, c, i, j = heapq.heappop(heap)
        if c > dist.get((i, j), 1e18):
            continue
        if (i, j) == (ti, tj):
            way, k, br = [], (i, j), []
            while k in prev:
                way.append((ox + k[0] * STEP, oy + k[1] * STEP))
                if k in jump:
                    br.append(((ox + prev[k][0] * STEP, oy + prev[k][1] * STEP), (ox + k[0] * STEP, oy + k[1] * STEP)))
                k = prev[k]
            way.append((x0, y0))
            way = way[::-1]
            way[-1] = (x1, y1)
            return way, br[::-1]
        seen += 1
        if seen > VISITS:
            return None
        zi = at(i, j)
        if zi is None and (i, j) != (si, sj):
            continue
        if zi is None:
            zi = G.z(x0, y0) or 0.0
        for da, db_ in MOVES:
            a, b = i + da, j + db_
            zb = at(a, b) if (a, b) != (ti, tj) else (at(a, b) if at(a, b) is not None else G.z(x1, y1))
            if zb is None:
                continue
            ln = STEP * math.hypot(da, db_)
            g = abs(zb - zi) / ln
            if g > GRADE_MAX:
                continue
            m = max(abs(da), abs(db_))
            bad = False
            for t in range(1, m):
                u = t / float(m)
                zm = at(i + int(round(da * u)), j + int(round(db_ * u)))
                if zm is None or abs(zm - (zi + (zb - zi) * u)) > 160:
                    bad = True
                    break
            if bad:
                continue
            nc = c + ln * (1.0 + 6.0 * max(0.0, g - GRADE) / GRADE)
            if nc < dist.get((a, b), 1e18):
                dist[(a, b)] = nc
                prev[(a, b)] = (i, j)
                jump.discard((a, b))
                heapq.heappush(heap, (nc + h(a, b), nc, a, b))
        # a bridge: from this bank straight over the water to the first dry ground the other side, near its level
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            z1 = G.z(ox + (i + dx) * STEP, oy + (j + dy) * STEP)
            if z1 is None or z1 >= WATER:
                continue
            for n in range(2, BRIDGE_STEPS + 1):
                a, b = i + dx * n, j + dy * n
                zr = G.z(ox + a * STEP, oy + b * STEP)
                if zr is None:
                    break
                if zr < WATER:
                    continue
                zb = at(a, b)
                if zb is not None and abs(zb - zi) <= 192:
                    ln = STEP * n * math.hypot(dx, dy)
                    nc = c + ln * BRIDGE_COST + BRIDGE_FIXED
                    if nc < dist.get((a, b), 1e18):
                        dist[(a, b)] = nc
                        prev[(a, b)] = (i, j)
                        jump.add((a, b))
                        heapq.heappush(heap, (nc + h(a, b), nc, a, b))
                break
    return None


def _chaikin(pts, n=2):
    P = [tuple(p) for p in pts]
    for _ in range(n):
        if len(P) < 3:
            break
        Q = [P[0]]
        for a, b in zip(P, P[1:]):
            Q.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            Q.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        Q.append(P[-1])
        P = Q
    return P


def _in_poly(poly, x, y):
    c = False
    n = len(poly)
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax:
            c = not c
    return c


def _clip(pts, towns):
    """The way with its ends inside the towns' outlines cut off (from its last point inside the first town, to its
    first point inside the second). A town's own outline where it has one: the circle round its furthest point took in
    a river crossing outside a long town, cut the road short of its bridge and left the bridge standing alone (the
    user, 2026-11-08: "The roads do not join either side of the bridge")."""
    def inside(p):
        for t in towns:
            poly = t[5] if len(t) > 5 else None
            if poly and len(poly) >= 3:
                if _in_poly(poly, p[0], p[1]):
                    return True
            elif math.hypot(p[0] - t[0], p[1] - t[1]) < t[2]:
                return True
        return False
    a, b = 0, len(pts) - 1
    while a < b and inside(pts[a]):
        a += 1
    while b > a and inside(pts[b]):
        b -= 1
    return pts[max(0, a - 1):b + 2]


def route(db, cells, layers=None, say=None):
    """The roads to propose for the marked cells: [{'pts', 'from', 'to', 'len', 'straight', 'grade90'}] and the
    settlements they join. say(what, frac): progress."""
    import landrange
    keys = sorted({landrange._key(k) for k in cells or []})
    towns = _towns(db, keys, layers)
    G = Ground(db)
    pairs = _pairs(towns)
    out = []
    for n, (a, b, d) in enumerate(sorted(pairs, key=lambda p: p[2])):
        if say:
            say('Way %d of %d' % (n + 1, len(pairs)), n / max(1, len(pairs)))
        A, B = towns[a], towns[b]
        got = path(G, A[0], A[1], B[0], B[1], free=[(A[0], A[1], A[2] + 256), (B[0], B[1], B[2] + 256)])
        if not got:
            continue
        way, br = got
        # (each stretch between bridges smoothed alone: a bridge stays the straight line it was found as)
        cut = {p for ab in br for p in ab}
        parts, cur = [], []
        for p in way:
            cur.append(p)
            if p in cut and len(cur) > 1:
                parts.append(cur)
                cur = [p]
        parts.append(cur)
        sm = []
        for k, part in enumerate(parts):
            q = list(_chaikin(part)) if len(part) > 2 else list(part)
            sm += q if not sm else q[1:]
        way = _clip(sm, [A, B])
        if len(way) < 2:
            continue
        ln = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(way, way[1:]))
        d = math.hypot(way[-1][0] - way[0][0], way[-1][1] - way[0][1])        # (its own ends: the winding, as a12 measures it)
        gs = []
        for p, q in zip(way, way[1:]):
            za, zb = G.z(*p), G.z(*q)
            L = math.hypot(q[0] - p[0], q[1] - p[1])
            if za is not None and zb is not None and L > 1:
                gs.append(math.degrees(math.atan(abs(zb - za) / L)))
        gs.sort()
        # (a bridge the kept way doesn't run over is no bridge of this road: inside a town, its streets' business)
        def on_way(p_):
            return any(_seg_d(u, v, p_) < 96 for u, v in zip(way, way[1:]))
        br = [(a_, b_) for a_, b_ in br if on_way(a_) and on_way(b_)]
        out.append({'pts': [[round(p[0]), round(p[1])] for p in way], 'from': A[4] or 'town', 'to': B[4] or 'town',
                    'bridges': [[round(a[0]), round(a[1]), round(b[0]), round(b[1])] for a, b in br],
                    'len': round(ln), 'straight': round(d), 'grade90': round(gs[int(0.9 * (len(gs) - 1))], 1) if gs else 0.0,
                    'culture': A[3] or B[3]})
    return {'roads': out, 'towns': len(towns), 'pairs': len(pairs)}


def _seg_d(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if not L2 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dy * t)


def _resample(pts, step):
    out = [tuple(pts[0])]
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(L // step))
        for t in range(1, k + 1):
            out.append((a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k))
    return out


def bed(F, inside, hold, roads):
    """The roads' beds into F (heights in place, inside only, never where hold): each road's line at every 64, its
    ground eased along (a running mean of EASE points either side), every point within HALF + FEATHER of the line
    brought to it (wholly within HALF). Returns a bytearray of the points under a road (for keeping rocks and plants
    off) and the points changed."""
    import cliffrocks
    under = bytearray(F.w * F.h)
    best = {}
    for R in roads:
        pts = _resample(R['pts'], 64.0)
        prof = [cliffrocks._height(F, x, y) for x, y in pts]
        if any(v is None for v in prof):
            # (a way running out of the field: only the part on it)
            keep = [k for k, v in enumerate(prof) if v is not None]
            if len(keep) < 2:
                continue
            pts = [pts[k] for k in keep]
            prof = [prof[k] for k in keep]
        eased = []
        for k in range(len(prof)):
            lo, hi = max(0, k - EASE), min(len(prof), k + EASE + 1)
            eased.append(sum(prof[lo:hi]) / (hi - lo))
        for B in R.get('bridges') or []:
            D = deck(B, lambda x, y: cliffrocks._height(F, x, y), R.get('kit') or 'highway')
            if D is None:
                continue
            # (the ground at the deck's height under the whole end piece, to its outer tip and TIP_PAD past it, then
            # eased down over RAMP: the bank points alone left the end pieces' outer halves over a drop, the deck a
            # step over the road, 2026-11-08)
            bl = math.hypot(B[2] - B[0], B[3] - B[1]) or 1.0
            bu = ((B[2] - B[0]) / bl, (B[3] - B[1]) / bl)
            reach_ = BANK + TIP_PAD
            ta = (B[0] - bu[0] * reach_, B[1] - bu[1] * reach_)
            tb = (B[2] + bu[0] * reach_, B[3] + bu[1] * reach_)
            # (the ramp long enough to climb at RAMP_GRADE from the lower of the ground at the tips)
            gts = [v for v in (cliffrocks._height(F, *ta), cliffrocks._height(F, *tb)) if v is not None]
            rl = max(RAMP, min(RAMP_MAX, (D - min(gts)) / RAMP_GRADE)) if gts else RAMP
            for k, (x, y) in enumerate(pts):
                e = _seg_d(ta, tb, (x, y))
                if e <= 0.5:
                    eased[k] = D
                    continue
                if e < rl:
                    t = 1.0 - e / rl
                    eased[k] += (D - eased[k]) * t * t * (3 - 2 * t)
        reach = HALF + FEATHER
        for (ax, ay), (bx, by), za, zb in zip(pts, pts[1:], eased, eased[1:]):
            L = math.hypot(bx - ax, by - ay) or 1.0
            ux, uy = (bx - ax) / L, (by - ay) / L
            for i in F.near(min(ax, bx) - reach, min(ay, by) - reach, max(ax, bx) + reach, max(ay, by) + reach):
                if not inside[i] or (hold is not None and hold[i] >= 0.5) or F.z[i] < WATER:
                    continue
                x, y = F.world(i)
                t = max(0.0, min(1.0, ((x - ax) * ux + (y - ay) * uy) / L))
                d = math.hypot(x - (ax + ux * L * t), y - (ay + uy * L * t))
                if d >= reach:
                    continue
                if i in best and best[i][0] <= d:
                    continue
                best[i] = (d, za + (zb - za) * t)
    for i, (d, zr) in best.items():
        k = 1.0 if d <= HALF else 1.0 - (d - HALF) / FEATHER
        k = k * k * (3 - 2 * k)
        F.z[i] += (zr - F.z[i]) * k
        if d <= HALF + 64:
            under[i] = 1
    return under, len(best)


def kit_for(db, culture):
    """The bridge kit for a culture, the first of its own and the others whose pieces the load order has."""
    want = BRIDGE_OF.get(culture, 'hlaalu')
    for k in [want] + [k for k in BRIDGES if k != want]:
        K = BRIDGES[k]
        if all(db.resolve_id(i) is not None for i in (K['end'], K['mid']) + ((K['pier'],) if K['pier'] else ())):
            return k
    return None


def deck(B, ground, kit):
    """The deck's height for a bridge [xa, ya, xb, yb]: level with its higher bank, and at least the kit's clearance
    over the water."""
    za, zb = ground(B[0], B[1]), ground(B[2], B[3])
    if za is None or zb is None:
        return None
    return max(za, zb, BRIDGES[kit]['clear'])


def bridge_pieces(B, D, kit):
    """The pieces of one bridge from bank to bank at deck height D, for cliffrocks.place: an end at each bank turned
    outward, middles between, piers under every other middle."""
    K = BRIDGES[kit]
    ax, ay, bx, by = B
    L = math.hypot(bx - ax, by - ay) or 1.0
    ux, uy = (bx - ax) / L, (by - ay) / L
    rz = (-math.atan2(uy, ux)) % (2 * math.pi)          # (a piece's +x heads (cos rz, -sin rz) in the world)
    z = D - K['top']
    span = L + 2 * BANK
    n = max(1, int(math.ceil((span - 2 * (K['out'] + K['in'])) / K['step'])))
    at = lambda t: (ax + ux * t, ay + uy * t)
    out = []
    t0 = -BANK + K['out']
    x, y = at(t0)
    out.append({'id': K['end'], 'x': x, 'y': y, 'z': z, 'rx': 0.0, 'ry': 0.0, 'rz': rz, 's': 1.0})
    t = t0 + K['in']
    for k in range(n):
        x, y = at(t + K['step'] / 2)
        out.append({'id': K['mid'], 'x': x, 'y': y, 'z': z, 'rx': 0.0, 'ry': 0.0, 'rz': rz, 's': 1.0})
        if K['pier'] and k % 2 == 1 and k < n - 1:
            out.append({'id': K['pier'], 'x': x, 'y': y, 'z': z + K['pier_dz'], 'rx': 0.0, 'ry': 0.0, 'rz': rz, 's': 1.0})
        t += K['step']
    x, y = at(t + K['in'])
    out.append({'id': K['end'], 'x': x, 'y': y, 'z': z, 'rx': 0.0, 'ry': 0.0, 'rz': (rz + math.pi) % (2 * math.pi), 's': 1.0})
    return out


def paint(db, keys, ids, roads, culture_of):
    """The 512 patches of the cells whose middle lies within PAINT of a road's line, in the road texture of the
    culture's nearest towns. ids: {(gx, gy): 256 LTEX ids} (the cells' own read in where missing). Returns the patches."""
    import landscape
    import townbuild
    n = 0
    keyset = set(keys)
    tex = {}
    for R in roads:
        pts = _resample(R['pts'], 128.0)
        cult = R.get('culture') or culture_of(pts[len(pts) // 2])
        mid = pts[len(pts) // 2]
        if cult not in tex:
            tex[cult] = townbuild.road_texture(db, cult, mid)
        tid = tex[cult]
        if not tid:
            continue
        done = set()
        # (every patch the line runs through, and where two of them meet only at a corner the one of the pair
        # between them whose middle is nearer the line: the run joined edge to edge. Patches by their middles alone
        # left a road crossing the grid aslant as blobs, the user, 2026-11-08: "The road ends up quite patchy")
        want = []
        last = None
        for x, y in pts:
            here = (math.floor(x / 512.0), math.floor(y / 512.0))
            if last is not None and here != last and abs(here[0] - last[0]) == 1 and abs(here[1] - last[1]) == 1:
                a, b = (here[0], last[1]), (last[0], here[1])
                da = math.hypot(a[0] * 512.0 + 256 - x, a[1] * 512.0 + 256 - y)
                db_ = math.hypot(b[0] * 512.0 + 256 - x, b[1] * 512.0 + 256 - y)
                want.append(a if da <= db_ else b)
            want.append(here)
            last = here
            px0, py0 = math.floor((x - PAINT) / 512.0), math.floor((y - PAINT) / 512.0)
            for px in range(px0, px0 + 3):
                for py in range(py0, py0 + 3):
                    if math.hypot(px * 512.0 + 256 - x, py * 512.0 + 256 - y) <= PAINT:
                        want.append((px, py))
        for px, py in want:
            if (px, py) in done:
                continue
            k = (math.floor(px / 16.0), math.floor(py / 16.0))
            if k not in keyset:
                continue
            done.add((px, py))
            T = ids.get(k)
            if T is None:
                T = ids[k] = list(landscape.read(db, k[0], k[1]).get('t') or [''] * 256)
            j = (py - k[1] * 16) * 16 + (px - k[0] * 16)
            if T[j] != tid:
                T[j] = tid
                n += 1
    return n
