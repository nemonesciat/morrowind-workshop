"""Water over a land plan (packaging/landscaping-plan.md, the water stage): where the rain runs, the valleys it
carves, and the way a river finds down from a spring.

All of it on a grid of every 512 units (the land record's own texture patch), whatever grid the plan is worked out
on: the preview (every 4th point) and apply (every point) see the same valleys, and the work stays small (a 10 x 10
cell plan is 25,600 points here against 410,000 at every point).

  fill     every hollow filled to its lip (a priority flood, with a hair's slope so flats drain): rain always finds
           a way out, to the water or off the plan's edge
  flow     each point's way down (the steepest drop on the filled ground) and how much ground drains through it
  valleys  the stream-power rule (cut = K * area^0.5 * slope, the usual one in landscape tools and geomorphology),
           solved implicitly from the outlets up (Braun and Willett 2013) so it is stable at any strength: big flows
           cut deep, small ones hardly, which gives the branching valleys of real land
  trace    the way down from a spring, to the water or the plan's edge"""
import heapq
import math

STEP = 512.0
SQ2 = math.sqrt(2.0)
NB = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, SQ2), (-1, 1, SQ2), (1, -1, SQ2), (-1, -1, SQ2))


class Coarse:
    """The plan's field at every 512 units: z, which points are the plan's own (inside) and the outlets."""
    def __init__(self, F, inside):
        self.F = F
        self.k = k = max(1, int(round(STEP / F.step)))
        self.w, self.h = (F.w - 1) // k + 1, (F.h - 1) // k + 1
        self.fi = [(y * k) * F.w + x * k for y in range(self.h) for x in range(self.w)]
        self.z = [F.z[i] for i in self.fi]
        self.inside = bytearray(1 if inside[i] else 0 for i in self.fi)

    def outlets(self):
        """Where the water leaves: the water itself (at or under 0), outside the marked cells, the grid's edge."""
        w, h, z = self.w, self.h, self.z
        out = bytearray(w * h)
        for i in range(w * h):
            x, y = i % w, i // w
            if z[i] <= 0 or not self.inside[i] or x == 0 or y == 0 or x == w - 1 or y == h - 1:
                out[i] = 1
        return out

    def world(self, i):
        return self.F.world(self.fi[i])


_NBRS = {}


def _nbrs(w, h):
    """Each point's neighbours on a w x h grid as (index, distance), in NB's order, with the rise over flats: worked
    out once a grid (valleys fills and flows the same grid 24 times; the bounds checks were a third of the time)."""
    key = (w, h)
    if key not in _NBRS:
        if len(_NBRS) > 8:
            _NBRS.clear()
        nb = []
        for i in range(w * h):
            x, y = i % w, i // w
            nb.append(tuple((ny * w + nx, d) for nx, ny, d in ((x + dx, y + dy, d) for dx, dy, d in NB)
                            if 0 <= nx < w and 0 <= ny < h))
        jit = [0.3 + ((j * 2654435761) % 1000) / 700.0 for j in range(w * h)]
        _NBRS[key] = (nb, jit)
    return _NBRS[key]


def fill(z, w, h, out, eps=0.05):
    """(filled heights, the order the points were reached in: lowest first, so each point's way down comes before
    it). Priority flood (Barnes et al. 2014) with a small rise over flats, a little different at each point: with
    one rise the water crossed every filled hollow in a dead straight line (lab 2026-10-28)."""
    n = w * h
    nbrs, jit0 = _nbrs(w, h)
    jit = [eps * v for v in jit0]
    f = list(z)
    seen = bytearray(n)
    heap = []
    for i in range(n):
        if out[i]:
            seen[i] = 1
            heap.append((z[i], i))
    heapq.heapify(heap)
    order = []
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        zi, i = pop(heap)
        order.append(i)
        for j, _d in nbrs[i]:
            if not seen[j]:
                seen[j] = 1
                if f[j] <= zi + jit[j]:
                    f[j] = zi + jit[j]
                push(heap, (f[j], j))
    return f, order


def flow(f, w, h, out):
    """(receiver of each point, its distance in steps, -1 at an outlet): the steepest drop on the filled ground."""
    n = w * h
    rec = [-1] * n
    dist = [1.0] * n
    nbrs = _nbrs(w, h)[0]
    for i in range(n):
        if out[i]:
            continue
        fi = f[i]
        best, bj, bd = 0.0, -1, 1.0
        for j, d in nbrs[i]:
            s = (fi - f[j]) / d
            if s > best:
                best, bj, bd = s, j, d
        rec[i], dist[i] = bj, bd
    return rec, dist


def area(rec, order):
    """How many points drain through each (itself too)."""
    A = [1.0] * len(rec)
    for i in reversed(order):
        r = rec[i]
        if r >= 0:
            A[r] += A[i]
    return A


def _wobble(C, seed, amp=40.0):
    """A gentle rolling offset for the water's way only (not the ground): on an even slope the steepest drop on a
    grid runs in straight lines along it, and the courses came out ruled (lab 2026-10-28)."""
    import landrange
    return [landrange.noise(*C.world(i), seed + 4099, amp) for i in range(C.w * C.h)]


def flow_map(F, inside, seed=1):
    """Where the rain runs on F as it is (no cutting): (the grid at every 512 units, how many of its points drain
    through each, each point's receiver). The land map's flow overlay and the dressing's stream beds read it."""
    C = Coarse(F, inside)
    out = C.outlets()
    f, order = fill([a + b for a, b in zip(C.z, _wobble(C, seed))], C.w, C.h, out)
    rec, _dist = flow(f, C.w, C.h, out)
    return C, area(rec, order), rec


def streams(C, A, rec, least=8.0):
    """The flow map as line pieces for drawing: [x0, y0, x1, y1, area] in world units, each point to its receiver,
    where at least `least` points (about 2 million square units) drain through it."""
    out = []
    for i, r in enumerate(rec):
        if r >= 0 and A[i] >= least:
            x0, y0 = C.world(i)
            x1, y1 = C.world(r)
            out.append([round(x0), round(y0), round(x1), round(y1), int(A[i])])
    return out


def patch_flow(C, A, G):
    """{(patch x, patch y) over the world: the most ground draining through one of its corners}, the 512-unit
    texture patches of the cells, from the flow map on a grid that starts at G's first cell."""
    out = {}
    for i, a in enumerate(A):
        cx, cy = i % C.w, i // C.w
        px, py = G.x0 * 16 + cx, G.y0 * 16 + cy
        # (a grid point is the corner of the four patches round it)
        for qx, qy in ((px, py), (px - 1, py), (px, py - 1), (px - 1, py - 1)):
            if out.get((qx, qy), 0) < a:
                out[(qx, qy)] = a
    return out


def valleys(F, inside, weight, strength=1.0, seed=1, hard=None, rounds=24, K=0.02):
    """The stream-power valleys on the plan's ground, laid on the field in proportion to weight (0-1 a point of F:
    how far the plan made that ground). Dry land stays dry, its floor at least 15% of its height over the water (a
    floor just over it was eased under by the passes after). Returns (the flow area at every 512 units for drawing,
    its grid width, the deepest cut). K: at strength 1 a big island's main valleys about 800 deep, as the game's
    West Gash and Ascadian valleys are 500 to 1,500 below their ridges. hard: the rock's hardness at each point of
    F (landrock), the water cutting hard rock at a quarter of the rate of soft."""
    C = Coarse(F, inside)
    w, h = C.w, C.h
    out = C.outlets()
    z0 = list(C.z)
    z = C.z
    floor = [min(v, 48.0 + 0.15 * max(0.0, v - 48.0)) for v in z0]
    wob = _wobble(C, seed)
    k = K * strength
    kf = [1.0 - 0.75 * hard[j] for j in C.fi] if hard is not None else None
    A = None
    for _ in range(rounds):
        f, order = fill([a + b for a, b in zip(z, wob)], w, h, out)
        rec, dist = flow(f, w, h, out)
        A = area(rec, order)
        # (from the outlets up: each point's receiver is already done, so the implicit step needs no smaller steps)
        for i in order:
            r = rec[i]
            if r < 0 or z[i] <= z[r]:
                continue
            Fk = k * math.sqrt(A[i]) / dist[i] * (kf[i] if kf else 1.0)
            v = (z[i] + Fk * z[r]) / (1 + Fk)
            # (never under the water: a valley reaching the sea ends in it, the river layers dig the beds)
            z[i] = max(v, floor[i])
    dz = [z[i] - z0[i] for i in range(w * h)]
    deepest = -min(dz) if dz else 0.0
    _lay(F, C, dz, weight)
    return A, w, deepest


def _lay(F, C, dz, weight):
    """The change at every 512 units laid on every point of F, bilinear, times the weight there."""
    k, w, h = C.k, C.w, C.h
    if k == 1:
        for i, d in enumerate(dz):
            if d:
                F.z[i] += d * weight[i]
        return
    for y in range(F.h):
        cy, ty = divmod(y, k)
        ty /= k
        cy1 = min(cy + 1, h - 1)
        for x in range(F.w):
            i = y * F.w + x
            if not weight[i]:
                continue
            cx, tx = divmod(x, k)
            tx /= k
            cx1 = min(cx + 1, w - 1)
            d = ((dz[cy * w + cx] * (1 - tx) + dz[cy * w + cx1] * tx) * (1 - ty)
                 + (dz[cy1 * w + cx] * (1 - tx) + dz[cy1 * w + cx1] * tx) * ty)
            if d:
                F.z[i] += d * weight[i]


def trace(F, inside, x, y):
    """The way down from (x, y) to the water or the plan's edge, as world points every 512 units; [] if the spring
    is off the plan's ground or already in the water."""
    C = Coarse(F, inside)
    w, h = C.w, C.h
    out = C.outlets()
    ix = int(round((x - F.ox) / STEP))
    iy = int(round((y - F.oy) / STEP))
    if not (0 <= ix < w and 0 <= iy < h):
        return []
    i = iy * w + ix
    if out[i]:
        return []
    f, _order = fill(C.z, w, h, out)
    rec, _dist = flow(f, w, h, out)
    path, seen = [i], {i}
    while rec[i] >= 0 and rec[i] not in seen:
        i = rec[i]
        seen.add(i)
        path.append(i)
    return [list(C.world(j)) + [C.z[j]] for j in path]


def wind(pts, wander=1.0, width=256.0, seed=1):
    """A traced way made a river's: smoothed (Chaikin), and winding where the land is flat, as rivers do on a plain
    and don't in a gorge. pts carry their height as a third value; returns [x, y] points."""
    if len(pts) < 3:
        return [p[:2] for p in pts]
    P = [p[:] for p in pts]
    for _ in range(2):
        Q = [P[0]]
        for a, b in zip(P, P[1:]):
            Q.append([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25, a[2] * 0.75 + b[2] * 0.25])
            Q.append([a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75, a[2] * 0.25 + b[2] * 0.75])
        Q.append(P[-1])
        P = Q
    if not wander:
        return [p[:2] for p in P]
    out, along = [], 0.0
    amp = wander * max(384.0, width * 2.5)
    wave = max(2048.0, width * 12.0)
    phase = (seed * 0.618) % 1.0 * 2 * math.pi
    n = len(P)
    for k in range(n):
        if k:
            along += math.hypot(P[k][0] - P[k - 1][0], P[k][1] - P[k - 1][1])
        a, b = P[max(0, k - 1)], P[min(n - 1, k + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        slope = abs(a[2] - b[2]) / L
        flat = max(0.0, 1.0 - slope / 0.12)
        # (no winding at the ends: the spring stays where it was put, the mouth where the water is)
        ends = min(1.0, along / wave, max(0.0, (n - 1 - k)) / 4.0)
        off = amp * flat * ends * math.sin(along / wave * 2 * math.pi + phase)
        out.append([P[k][0] - dy / L * off, P[k][1] + dx / L * off])
    return out
