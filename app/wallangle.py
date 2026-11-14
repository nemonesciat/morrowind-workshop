"""Town walls at any angle.

A wall kit turns square corners only, so a town drawn off the square, or beside a castle that stands at another angle,
got its sides in steps (the user, 2026-11-11: "why can't I just draw some walls ... What's so hard about building walls
like this when I draw two straight lines to the coast?"). The game's forts hide the joints of their walls in round
towers; so does this: each side of the outline as drawn is one straight run of whole wall lengths at its own angle, the
runs' ends inside a round tower stood over each corner (the idea is Watabou's city generator's: a wall is a polygon
with a tower at every vertex). A castle beside the town is in the ring: the town's wall ends at two of its corners and
the castle's own wall closes the ring between them.

outline(drawn, forts, L) gives the outline to lay, or None where the drawing cannot be built this way (a corner too
sharp, a side too short, too many corners): the caller then walls it the square way.
"""
import math

HIDE = 230.0                   # a run ends this far from its corner at most: inside the tower over it (radius 303)
ANGLE_LEAST = 65.0             # (degrees) a corner sharper than this crosses its two walls outside the tower
STRAIGHT_TURN = 9.0            # (degrees) a point of the drawing that turns less than this is no corner
SIDE_LEAST = 2                 # a side holds this many lengths at least
CORNERS_MOST = 24
GATE_SIDE = 5                  # one side at least holds this many lengths: room for a gate between its corners
BLUNT = 3.0                    # a corner too sharp is cut off this many lengths back along each of its sides, at most
FORT_BY = 1700.0               # a stretch of the drawing this near a castle's wall is the castle's (townwalls.FORT_GAP)
FORT_STEP = 64.0
FIT_ROUNDS = 80
FIT_TOL = 6.0


def _d(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if not l2 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _ring_dist(ring, p):
    return min(_seg_dist(p, ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))


def _inside(poly, p):
    c = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
    return c


def _area(poly):
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))) / 2.0


def _turn(a, b, c):
    """The turn at b going a, b, c, in degrees (0 straight on)."""
    u = math.atan2(b[1] - a[1], b[0] - a[0])
    v = math.atan2(c[1] - b[1], c[0] - b[0])
    return abs((math.degrees(v - u) + 180.0) % 360.0 - 180.0)


def simplify(P, L, pinned=(), least=None):
    """The outline with only its real corners: points that hardly turn taken out, and the corner between two sides of
    which one is shorter than a wall can be. pinned: points that stay (a castle's corners). least: the lengths a side
    holds at least (SIDE_LEAST; a wall of round towers holds one, townwalls.ROUND)."""
    least = SIDE_LEAST if least is None else least
    P = [tuple(p) for p in P]
    pin = {(round(p[0]), round(p[1])) for p in pinned}
    is_pin = lambda p: (round(p[0]), round(p[1])) in pin
    changed = True
    while changed and len(P) > 3:
        changed = False
        n = len(P)
        for k in range(n):
            a, b, c = P[k - 1], P[k], P[(k + 1) % n]
            if is_pin(b):
                continue
            if _d(a, b) < 1 or _turn(a, b, c) < STRAIGHT_TURN:
                P.pop(k)
                changed = True
                break
        if changed:
            continue
        # (the shortest side under the least: the end of it that turns less goes; a pinned end stays)
        short = sorted((_d(P[k], P[(k + 1) % n]), k) for k in range(n))
        for s, k in short:
            if s >= (least - 0.4) * L:      # (a little short is lengthened after: fit_lengths)
                break
            i, j = k, (k + 1) % n
            cand = [x for x in (i, j) if not is_pin(P[x])]
            if not cand:
                continue
            x = min(cand, key=lambda x: _turn(P[x - 1], P[x], P[(x + 1) % n]))
            P.pop(x)
            changed = True
            break
    return P


def gate_room(P, L, pinned=()):
    """The outline with a side long enough for a gate: a round drawing of many short sides stood a ring of towers
    with no way in. The corner that turns least is taken out until one side holds GATE_SIDE lengths."""
    P = [tuple(p) for p in P]
    pin = {(round(p[0]), round(p[1])) for p in pinned}
    while len(P) > 4:
        n = len(P)
        if max(_d(P[k], P[(k + 1) % n]) for k in range(n)) >= GATE_SIDE * L:
            break
        cand = [k for k in range(n) if (round(P[k][0]), round(P[k][1])) not in pin]
        if not cand:
            break
        P.pop(min(cand, key=lambda k: _turn(P[k - 1], P[k], P[(k + 1) % n])))
    return P


def blunt(P, L, pinned=()):
    """The outline with no corner sharper than ANGLE_LEAST: an outer one cut off across (two corners of half its
    turn each, a tower on both), an inner one filled in (its point taken out). A castle's corners stay."""
    P = [tuple(p) for p in P]
    pin = {(round(p[0]), round(p[1])) for p in pinned}
    for _ in range(4 * len(P) + 8):
        n = len(P)
        if n < 3:
            break
        sg = 1.0 if _area(P) > 0 else -1.0
        for k in range(n):
            a, b, c = P[k - 1], P[k], P[(k + 1) % n]
            if (round(b[0]), round(b[1])) in pin or 180.0 - _turn(a, b, c) >= ANGLE_LEAST:
                continue
            cr = ((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) * sg
            if cr < 0 and n > 3:
                P.pop(k)                         # (an inner corner: the notch filled)
            else:
                la, lc = _d(a, b), _d(b, c)
                # (far enough back that the cut across holds its two lengths)
                half = math.radians(max(4.0, 180.0 - _turn(a, b, c))) / 2.0
                t = min(max(BLUNT * L, 1.15 * L / math.sin(half)), la * 0.45, lc * 0.45)
                P[k:k + 1] = [(b[0] + (a[0] - b[0]) * t / la, b[1] + (a[1] - b[1]) * t / la),
                              (b[0] + (c[0] - b[0]) * t / lc, b[1] + (c[1] - b[1]) * t / lc)]
            break
        else:
            break
    return P


def window(S, L, hide=None, least=None):
    """(pieces, low, high): how many lengths a side S long holds and the lengths it may have with them."""
    n = max(SIDE_LEAST if least is None else least, int((S + 1e-6) // L))
    return n, n * L, n * L + 2.0 * (HIDE if hide is None else hide)


def fit_lengths(P, L, fort_sides=(), pinned=(), hide=None, least=None):
    """The corners moved a little so every side holds whole lengths with its ends inside the towers: a side between
    n and n lengths and two HIDEs long as it is; one longer, shortened to that or lengthened to n + 1, whichever is
    less; each end moved half the change along the side. (P, worst miss left)."""
    P = [list(p) for p in P]
    n = len(P)
    pin = {(round(p[0]), round(p[1])) for p in pinned}
    fixed = [(round(p[0]), round(p[1])) in pin for p in P]
    fs = set(fort_sides)
    worst = 0.0
    for _ in range(FIT_ROUNDS):
        worst = 0.0
        for k in range(n):
            if k in fs:
                continue
            i, j = k, (k + 1) % n
            S = _d(P[i], P[j])
            if S < 1:
                continue
            m, lo, hi = window(S, L, hide, least)
            if S < lo:
                dl = lo - S
            elif S > hi:
                dl = (hi - S) if (S - hi) <= ((m + 1) * L - S) else ((m + 1) * L - S)
            else:
                continue
            worst = max(worst, abs(dl))
            ux, uy = (P[j][0] - P[i][0]) / S, (P[j][1] - P[i][1]) / S
            wi = 0.0 if fixed[i] else (1.0 if fixed[j] else 0.5)
            wj = 0.0 if fixed[j] else (1.0 if fixed[i] else 0.5)
            P[i][0] -= ux * dl * wi
            P[i][1] -= uy * dl * wi
            P[j][0] += ux * dl * wj
            P[j][1] += uy * dl * wj
        if worst <= FIT_TOL:
            break
    return [tuple(p) for p in P], worst


def _fort_path(ring, c1, c2, kept):
    """The castle's corners from c1 round to c2 (indices into its ring), the way that leaves the castle outside the
    town: of the two ways round, the one that makes the smaller town."""
    m = len(ring)
    ways = []
    for step in (1, -1):
        path, i = [c1], c1
        while i != c2:
            i = (i + step) % m
            path.append(i)
        ways.append(path)
    if c1 == c2:
        return [c1]
    best = min(ways, key=lambda w: abs(_area(list(kept) + [ring[i] for i in w])))
    return best


def with_fort(D, fort, L):
    """The drawn outline with a castle in its ring: (points, fort side keys, the castle's corners in it), or None when
    the castle is nowhere near the drawing or swallows it. The stretch of the drawing by the castle (inside its ring
    or within FORT_BY of its wall) is the castle's: the town's wall ends at the castle's corners nearest where that
    stretch begins and ends, and the castle's own wall stands between them."""
    ring = [tuple(p[:2]) for p in fort['ring']]
    n = len(D)
    samples = []                               # (side k, point, by the castle)
    for k in range(n):
        a, b = D[k], D[(k + 1) % n]
        S = _d(a, b)
        steps = max(1, int(S // FORT_STEP))
        for s in range(steps):
            p = (a[0] + (b[0] - a[0]) * s / steps, a[1] + (b[1] - a[1]) * s / steps)
            samples.append((k, p, _inside(ring, p) or _ring_dist(ring, p) <= FORT_BY))
    m = len(samples)
    if not any(s[2] for s in samples):
        return None
    if all(s[2] for s in samples):
        return None
    # the longest run of samples by the castle, round the loop
    start = next(i for i in range(m) if samples[i][2] and not samples[i - 1][2])
    best = (0, start)
    i = start
    seen = 0
    while seen < m:
        if samples[i % m][2] and not samples[(i - 1) % m][2]:
            j = i
            while samples[j % m][2]:
                j += 1
            if j - i > best[0]:
                best = (j - i, i % m)
            seen += j - i
            i = j
        else:
            i += 1
            seen += 1
    length, s0 = best
    e1, e2 = samples[s0][1], samples[(s0 + length - 1) % m][1]
    k_in, k_out = samples[s0][0], samples[(s0 + length - 1) % m][0]
    # the drawing's corners clear of the castle, in order from where the stretch ends round to where it begins
    kept = []
    k = (k_out + 1) % n
    guard = 0
    while guard <= n:
        guard += 1
        p = D[k]
        if not (_inside(ring, p) or _ring_dist(ring, p) <= FORT_BY):
            kept.append(p)
        if k == k_in:
            break
        k = (k + 1) % n
    if not kept:
        return None
    c1 = min(range(len(ring)), key=lambda i: _d(ring[i], e1))
    c2 = min(range(len(ring)), key=lambda i: _d(ring[i], e2))
    path = _fort_path(ring, c1, c2, kept)
    pts = list(kept) + [ring[i] for i in path]
    keys = set()
    for a, b in zip(path, path[1:]):
        keys.add(_key(ring[a], ring[b]))
    return pts, keys, [ring[i] for i in path]


def _key(a, b):
    p, q = (int(round(a[0])), int(round(a[1]))), (int(round(b[0])), int(round(b[1])))
    return (p + q) if p <= q else (q + p)


def outline(drawn, forts, L):
    """The outline to wall at any angle: {'poly': [(x, y)], 'fort': [side keys], 'no_tower': [(x, y)]}, or None.
    fort: the sides that are a castle's own wall (no town wall there); no_tower: the castle's corners in the ring (it
    has its own piece there)."""
    D = simplify([tuple(p[:2]) for p in drawn], L)
    if len(D) < 3:
        return None
    keys, pins = set(), []
    for f in forts or ():
        if len(f.get('ring') or ()) < 3:
            continue
        got = with_fort(D, f, L)
        if got is None:
            continue
        D, k2, p2 = got
        keys |= k2
        pins += p2
        break                                  # (one castle a town's ring, as the square way has it)
    D = simplify(blunt(D, L, pins), L, pins)
    D = gate_room(D, L, pins)
    n = len(D)
    if n < 3 or n > CORNERS_MOST:
        return None
    fs = {k for k in range(n) if _key(D[k], D[(k + 1) % n]) in keys}
    D, miss = fit_lengths(D, L, fs, pins)
    if miss > 4 * FIT_TOL:
        return None
    for k in range(n):
        a, b, c = D[k - 1], D[k], D[(k + 1) % n]
        if 180.0 - _turn(a, b, c) < ANGLE_LEAST:
            return None
        if k not in fs and _d(b, c) < SIDE_LEAST * L - FIT_TOL:
            return None
    pin = {(round(p[0]), round(p[1])) for p in pins}
    fort_keys = [list(_key(D[k], D[(k + 1) % n])) for k in range(n) if k in fs]
    return {'poly': [(round(p[0], 2), round(p[1], 2)) for p in D], 'fort': fort_keys,
            'no_tower': [[round(p[0]), round(p[1])] for p in D if (round(p[0]), round(p[1])) in pin]}


def fort_sides(poly, info):
    """The indices of an outline's sides that are a castle's wall, however the outline is walked."""
    keys = {tuple(k) for k in (info or {}).get('fort') or ()}
    n = len(poly)
    return {k for k in range(n) if _key(poly[k], poly[(k + 1) % n]) in keys}


def run_of(a, b, L):
    """A side's run: (pieces, how far its first length's middle stands from a)."""
    S = _d(a, b)
    n = max(1, int((S + FIT_TOL) // L))
    return n, (S - n * L) / 2.0 + L / 2.0
