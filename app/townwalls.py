"""Town walls the way the game builds its own: one family's pieces laid as a continuous run, each set on the last by a
join the game itself uses (exteriorsurvey's outdoor joins, their exact poses), so the pieces line up and meet as the
game's do. Never pieces scattered where a wall should be (the user, 2026-10-30: "the walls line up, the pieces snap
together, and it looks like a real wall").

  kits(db)    for every family with a wall the game runs piece after piece: its straight piece and step, its
              corners (a corner piece, a tower, or the straight turned on itself) for a turn either way, the pieces it
              sets in line (gates, towers, arches) and how often, and the cultures whose towns have it
  lay(db, plan, family=None)   the wall for a town plan: an outline square to the town, laid corner unit by corner
              unit with straights between, gates where streets leave, towers as often as the game's; checked (every
              piece joined to the next by a game join, nothing left open) and set on the ground
"""
import math
import re
from collections import Counter, defaultdict

import exteriorsurvey as es
import mapdata
import townsurvey

WALLISH = re.compile(r'wall|gate|tower|rampart|parapet|battlement|palisade|_ent_|wallent|arch')
NOT_WALL = re.compile(r'house|ruin|decal|fence|collision|property|farm|dngruin|_wallb_|stair|ladder')
GATEISH = re.compile(r'gate|wallent|_ent_|arch')
TOWERISH = re.compile(r'tower')
MIN_STEPS = 4                  # the game runs the straight on itself at least this often
STEP_MIN = 192                 # (a straight's step: shorter is a post or a trim)
SNAP = 12                      # units a join's pose may miss its line and still count as in line
MARGIN = 640                   # the wall stands this far outside the plots
OVERLAP_MAX = 0.5              # of a step: the last straight of a side may overlap its neighbour this much, when the
                               # game itself sets that straight on itself at a shorter step (Hlaalu at 128 of 256)


def _ang(deg):
    """A turn in degrees folded to (-180, 180]."""
    return (deg + 180.0) % 360.0 - 180.0


class Pose:
    __slots__ = ('x', 'y', 'z', 'rz', 'id')

    def __init__(self, x, y, z, rz, id_=None):
        self.x, self.y, self.z, self.rz, self.id = x, y, z, rz % (2 * math.pi), id_

    def then(self, e, id_=None):
        """The pose a join's exact [lx, ly, dz, turn deg] puts the next piece at (adjacency.to_world's turn)."""
        c, s = math.cos(self.rz), math.sin(self.rz)
        return Pose(self.x + e[0] * c + e[1] * s, self.y - e[0] * s + e[1] * c, self.z + e[2], self.rz + math.radians(e[3]), id_)

    def local(self, wx, wy):
        dx, dy = wx - self.x, wy - self.y
        c, s = math.cos(self.rz), math.sin(self.rz)
        return dx * c - dy * s, dx * s + dy * c

    def dir(self, v):
        """A local direction in the world."""
        c, s = math.cos(self.rz), math.sin(self.rz)
        return v[0] * c + v[1] * s, -v[0] * s + v[1] * c


_kits = {}


def _joins(db):
    S = es.survey(db)['outdoor']
    J, EX = S['joins'], S['exact']
    out = defaultdict(list)                  # model: [(target, n, exact)]
    for m, sides in EX.items():
        for s_, rels in sides.items():
            if s_ in ('U', 'D', 'in'):
                continue
            for rs, e in rels.items():
                out[m].append((rs.split('@')[0], J[m][s_][rs], e))
    return out, S['placed']


def kits(db):
    k = id(db.recs)
    if k in _kits:
        return _kits[k]
    import townbuild
    JN, placed = _joins(db)
    fams = defaultdict(list)
    for m, n in placed.items():
        if WALLISH.search(m) and not NOT_WALL.search(m):
            fams[townbuild.family(m)].append(m)
    out = {}
    for fam, ms in fams.items():
        kit = _kit(fam, set(ms), JN, placed)
        if kit:
            out[fam] = kit
    # (the cultures whose game towns stand their walls: wall pieces within a town's cells)
    for t in townsurvey.survey(db)['towns']:
        c = Counter()
        for gx, gy in t['cells']:
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                f = townbuild.family(r['id'].lower())
                if f in out and r['id'].lower() in out[f]['models']:
                    c[f] += 1
        for f, n in c.items():
            if n >= 6:
                cu = out[f].setdefault('cultures', {})
                cu[t['culture']] = cu.get(t['culture'], 0) + 1
                out[f].setdefault('towns', []).append(t['name'])
    _kits[k] = out
    return out


def _kit(fam, ms, JN, placed):
    """A family's wall kit, or None when the game never runs it piece after piece."""
    best = None
    for m in ms:
        steps = Counter()
        short = 0
        for t, n, e in JN.get(m, ()):
            if t != m or abs(_ang(e[3])) > 2 or abs(e[2]) > 4:
                continue
            for ax in (0, 1):
                a, lat = e[ax], e[1 - ax]
                if abs(lat) <= SNAP and abs(a) >= STEP_MIN:
                    steps[(ax, int(round(abs(a) / 8.0)) * 8)] += n
                elif abs(lat) <= SNAP and 64 <= abs(a) < STEP_MIN:
                    short += n
        if not steps:
            continue
        (ax, L), n = steps.most_common(1)[0]
        if n < MIN_STEPS:
            continue
        # (overlap allowed: the game also sets it on itself at a shorter step along the same axis)
        shorter = sum(v for (a2, l2), v in steps.items() if a2 == ax and l2 < L) + short
        if best is None or n > best['n']:
            best = {'straight': m, 'axis': ax, 'L': float(L), 'n': n, 'overlap': shorter >= 2}
    if not best:
        return None
    S, ax, L = best['straight'], best['axis'], best['L']
    run = (1.0, 0.0) if ax == 0 else (0.0, 1.0)
    # in line: S -> X along +run, X -> S on along +run, both with no turn
    inline = {}
    corners = {}
    p0 = Pose(0, 0, 0, 0)
    for t, n1, e1 in JN.get(S, ()):
        if t not in ms and t != S:
            continue
        X = p0.then(e1, t)
        # (corner direct: the straight turned on itself, a quarter either way, beyond the end)
        for t2, n2, e2 in JN.get(t, ()):
            if t2 != S:
                continue
            S1 = X.then(e2, S)
            turn = _ang(math.degrees(S1.rz))
            if t == S:
                continue
            if abs(turn) <= 2:
                # (in line: on along the run, on the same line)
                a1 = e1[0] * run[0] + e1[1] * run[1]
                lat1 = e1[1] * run[0] - e1[0] * run[1]
                lx, ly = S1.x, S1.y
                a2 = lx * run[0] + ly * run[1]
                lat2 = ly * run[0] - lx * run[1]
                if a1 > 0 and a2 > a1 and abs(lat1) <= SNAP and abs(lat2) <= SNAP and abs(S1.z) <= 4:
                    w = min(n1, n2)
                    if w >= 2 and (t not in inline or w > inline[t]['n']):
                        inline[t] = {'a': a1, 'span': a2, 'e1': e1, 'e2': e2, 'n': w,
                                     'kind': 'gate' if GATEISH.search(t) else 'tower' if TOWERISH.search(t) else 'piece'}
            elif abs(abs(turn) - 90) <= 3:
                w = min(n1, n2)
                _corner(corners, S, run, [(t, e1), (S, e2)], turn, w)
    # the straight turned on itself directly
    for t, n1, e1 in JN.get(S, ()):
        if t == S and abs(abs(_ang(e1[3])) - 90) <= 3:
            _corner(corners, S, run, [(S, e1)], _ang(e1[3]), n1)
    # (a corner the game turned once may be two pieces that only happen to touch: Reach's fort wall)
    corners = {k_: v for k_, v in corners.items() if v['n'] >= 2}
    if not corners:
        return None
    # its ends: a piece that finishes the run, after the last straight (fwd) or before the first (back), on its line
    ends = {}
    for t, n1, e1 in JN.get(S, ()):
        if t == S or t not in ms or not re.search(r'end|post|cap', t):
            continue
        a1 = e1[0] * run[0] + e1[1] * run[1]
        lat1 = e1[1] * run[0] - e1[0] * run[1]
        if abs(lat1) > SNAP or abs(e1[2]) > 4 or abs(a1) < 32:
            continue
        k_ = 'fwd' if a1 > 0 else 'back'
        if n1 >= 2 and (k_ not in ends or n1 > ends[k_]['n']):
            ends[k_] = {'id': t, 'e': e1, 'n': n1}
    # the towers the game stands right beside a corner, in the place of the straight there (Imperial: wall_tower_01 a step
    # on from corner_01, 12 of its 71 town corners, lab jcorner2): {corner id: [(tower id, exact join from the corner)]}
    ctow = {}
    for v in corners.values():
        C = v['chain'][0][0] if v['chain'] and v['chain'][0][0] != S else None
        if not C or C in ctow:
            continue
        for t, n1, e1 in JN.get(C, ()):
            if t in ms and TOWERISH.search(t) and n1 >= 2 and abs(e1[2]) <= 4:
                ctow.setdefault(C, []).append((t, e1))
    # (how often each in-line piece stands among the straights: one in every so many)
    for t, v in inline.items():
        v['every'] = max(2.0, placed.get(S, 1) / float(max(1, placed.get(t, 1))))
    return {'family': fam, 'straight': S, 'axis': ax, 'L': L, 'overlap': best['overlap'], 'runs': best['n'],
            'inline': inline, 'corners': corners, 'ends': ends, 'corner_towers': ctow, 'models': sorted(ms), 'placed': sum(placed.get(m, 0) for m in ms)}


def _corner(corners, S, run, chain, turn, w):
    """A corner unit: from a straight S0 at the origin, the pieces after it to the straight S1 turned a quarter. Its
    vertex (where S0's line meets S1's) in S0's frame, and how far S1 stands past it, on its own line."""
    p = Pose(0, 0, 0, 0)
    poses = []
    for t, e in chain:
        p = p.then(e, t)
        poses.append(p)
    S1 = poses[-1]
    if abs(S1.z) > 4:
        return
    d1 = S1.dir(run)
    # S0's line: lat = l0 (y = 0 when run is x); S1's line passes S1 along d1. Their meeting point:
    # (on S0's line every point is t*run; on S1's, S1 + u*d1)
    det = run[0] * (-d1[1]) - run[1] * (-d1[0])
    if abs(det) < 1e-6:
        return
    bx, by = S1.x, S1.y
    tt = (bx * (-d1[1]) - by * (-d1[0])) / det
    uu = (run[0] * by - run[1] * bx) / det
    if tt <= 0 or uu >= 0:
        # (the vertex must lie ahead of S0 and behind S1, else it is not a turn of the run but a branch)
        return
    side = 1 if turn > 0 else -1
    have = corners.get(side)
    if have is None or w > have['n']:
        corners[side] = {'chain': [[t, list(e)] for t, e in chain], 'p': tt, 'q': -uu, 'n': w}


# ------------------------------------------------------------------------------------------------ laying a wall
def _town_pts(plan):
    pts = []
    for q in plan['plots']:
        pts.extend(q.get('rect') or [(q['x'], q['y'])])
    return pts


def _town_frame(plan):
    """The town's own square: the turn whose box round its plots is smallest, so the wall hugs the town and runs with
    its streets (a wall square to the compass round a town laid corner-wise was all steps, lab 2026-10-30)."""
    pts = _town_pts(plan)
    best = (None, 0.0)
    for deg in range(0, 90, 3):
        th = math.radians(deg)
        c, s = math.cos(th), math.sin(th)
        us = [x * c + y * s for x, y in pts]
        vs = [-x * s + y * c for x, y in pts]
        a = (max(us) - min(us) + 2 * MARGIN) * (max(vs) - min(vs) + 2 * MARGIN) if pts else 0
        if best[0] is None or a < best[0]:
            best = (a, th)
    # (square to the way most buildings face when that is nearly as tight: a grid town walled a few degrees off its
    # streets looked careless, lab 2026-10-30)
    hs = Counter(int(round((math.degrees(q['face']) % 90.0) / 3.0)) * 3 % 90 for q in plan['plots'])
    if hs:
        th = math.radians(hs.most_common(1)[0][0])
        c, s = math.cos(th), math.sin(th)
        us = [x * c + y * s for x, y in pts]
        vs = [-x * s + y * c for x, y in pts]
        if (max(us) - min(us) + 2 * MARGIN) * (max(vs) - min(vs) + 2 * MARGIN) <= best[0] * 1.12:
            return th
    return best[1]


MAX_CORNERS = 8
FILL = 0.85                    # the town fills this share of its box: walled square round it (at 0.6 an L-shaped town was
                               # walled as a box, a third of it empty ground, the Tamriel practice 2026-10-31)


DRY = 48                       # a wall square's ground stands at least this far over the water everywhere
STEEP = 520                    # and rises or falls no more than this across it (a cliff's edge is no place for a wall)


def outline(plan, cell=1024.0, db=None, step=1.0):
    """An outline square to the town round its plots and MARGIN beyond, its sides whole cells: the town's box when
    the town fills it well, else grid squares of the town's frame with rows and columns filled (no holes, no notches
    into it); [(x, y)] counter-clockwise, and its frame angle."""
    th = _town_frame(plan)
    c, s = math.cos(th), math.sin(th)
    pts = [(x * c + y * s, -x * s + y * c) for x, y in _town_pts(plan)]
    if not pts:
        return [], th
    x0 = min(p[0] for p in pts) - MARGIN
    y0 = min(p[1] for p in pts) - MARGIN
    # (squares sized to the town each way, whole squares to its ends: rounded up to whole cells, the wall stood up to a
    # cell beyond the town on two sides, half its ground empty against a fifth inside the game's, lab jhug 2026-10-31)
    ex, ey = max(p[0] for p in pts) + MARGIN - x0, max(p[1] for p in pts) + MARGIN - y0

    def fit(e):
        # (whole straights a square, so a side's straights fill it; the count of squares leaving least to spare)
        best = None
        for n in range(max(1, int(e // cell)), int(math.ceil(e / cell)) + 2):
            cs = step * math.ceil(e / n / step - 1e-6)
            if cs < 0.6 * cell and n > 1:
                continue
            if best is None or n * cs - e < best[0] * best[1] - e:
                best = (n, cs)
        return best
    nx, cu = fit(ex)
    ny, cv = fit(ey)
    x0 -= (nx * cu - ex) / 2            # (what is to spare, half each side)
    y0 -= (ny * cv - ey) / 2
    on = set()
    for q in plan['plots']:
        r = [(x * c + y * s, -x * s + y * c) for x, y in (q.get('rect') or [(q['x'], q['y'])])]
        ax0 = int((min(p[0] for p in r) - MARGIN - x0) // cu)
        ax1 = int((max(p[0] for p in r) + MARGIN - x0 - 1) // cu)
        ay0 = int((min(p[1] for p in r) - MARGIN - y0) // cv)
        ay1 = int((max(p[1] for p in r) + MARGIN - y0 - 1) // cv)
        for i in range(max(0, ax0), min(nx - 1, ax1) + 1):
            for j in range(max(0, ay0), min(ny - 1, ay1) + 1):
                on.add((i, j))
    plots_on = set(on)
    # (rows and columns filled between their ends: no holes, no notches; the result is orthogonally convex)
    for _ in range(3):
        rows = defaultdict(list)
        for i, j in on:
            rows[j].append(i)
        for j, l in rows.items():
            for i in range(min(l), max(l) + 1):
                on.add((i, j))
        cols = defaultdict(list)
        for i, j in on:
            cols[i].append(j)
        for i, l in cols.items():
            for j in range(min(l), max(l) + 1):
                on.add((i, j))
    # (an L or a notch where the town leaves a corner of its box empty, but never a staircase of jogs: the game's walls
    # run long straight sides, and 12 to 14 corners round a town was the user's "fever dream" again)
    if len(on) >= FILL * nx * ny or len(_trace(on)) > MAX_CORNERS:
        on = {(i, j) for i in range(nx) for j in range(ny)}
    if db is not None:
        on = _on_land(db, on, x0, y0, (cu, cv), c, s, plots_on)
    poly = _trace(on)
    out = []
    for i, j in poly:
        u, v = x0 + i * cu, y0 + j * cv
        out.append((u * c - v * s, u * s + v * c))
    return out, th


def _on_land(db, on, x0, y0, cell, c, s, plots_on=()):
    """(cell: the squares' size each way.) The wall's squares kept to dry, walkable ground: a square over the water, or across a cliff's edge, is left out,
    so the wall follows the land inside its shore and above its cliffs instead of running a straight box out over the sea
    (the user's island town, test3: sides off the land, hanging over the drop). Then the piece with the most of the town
    in it, its holes filled (a wall closes round them)."""
    def ok(i, j):
        steep_ok = (i, j) in plots_on         # (a plot's square stays in, steep or not: the wall never cuts a building)
        zs = []
        for fu in (0.0, 0.5, 1.0):
            for fv in (0.0, 0.5, 1.0):
                u, v = x0 + (i + fu) * cell[0], y0 + (j + fv) * cell[1]
                z = mapdata.terrain_z(db, u * c - v * s, u * s + v * c)
                if z is None or z < DRY:
                    return False
                zs.append(z)
        return steep_ok or max(zs) - min(zs) <= STEEP
    keep = {t for t in on if ok(*t)}
    if not keep:
        return on
    # (notches filled with any dry, walkable square: traced square by square the wall came out jogging in and out a
    # square at a time, a corner and a tower at every jog, 12 corners and 14 towers round a small town, the user's
    # "fever dream"; the game's walls run long straight sides, turning only where the land makes them)
    memo_ok = {}
    def ok2(t):
        if t not in memo_ok:
            memo_ok[t] = ok(*t)
        return memo_ok[t]
    for _ in range(3):
        rows, cols = defaultdict(list), defaultdict(list)
        for i, j in keep:
            rows[j].append(i)
            cols[i].append(j)
        add = {(i, j) for j, l in rows.items() for i in range(min(l), max(l) + 1)} |             {(i, j) for i, l in cols.items() for j in range(min(l), max(l) + 1)}
        add = {t for t in add - keep if ok2(t)}
        if not add:
            break
        keep |= add
    # (a square standing out on its own, joined by one side only: dropped, a jog of its own)
    for _ in range(2):
        lone = {t for t in keep if sum((t[0] + dx, t[1] + dy) in keep for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) <= 1
                and t not in plots_on}
        if not lone:
            break
        keep -= lone
    # (the largest 4-connected piece)
    best, seen = set(), set()
    for t in keep:
        if t in seen:
            continue
        comp, stack = set(), [t]
        while stack:
            u = stack.pop()
            if u in seen or u not in keep:
                continue
            seen.add(u)
            comp.add(u)
            stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
        if len(comp) > len(best):
            best = comp
    # (holes filled: squares the outside can't reach)
    xs = [t[0] for t in best]
    ys = [t[1] for t in best]
    box = {(i, j) for i in range(min(xs) - 1, max(xs) + 2) for j in range(min(ys) - 1, max(ys) + 2)}
    out_, stack = set(), [(min(xs) - 1, min(ys) - 1)]
    while stack:
        u = stack.pop()
        if u in out_ or u not in box or u in best:
            continue
        out_.add(u)
        stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
    return {t for t in box if t not in out_}


def _trace(on):
    """The boundary of a 4-connected set of grid squares as its corners, counter-clockwise."""
    edges = {}
    for i, j in on:
        if (i, j - 1) not in on:
            edges[(i, j)] = (i + 1, j)
        if (i + 1, j) not in on:
            edges[(i + 1, j)] = (i + 1, j + 1)
        if (i, j + 1) not in on:
            edges[(i + 1, j + 1)] = (i, j + 1)
        if (i - 1, j) not in on:
            edges[(i, j + 1)] = (i, j)
    if not edges:
        return []
    start = min(edges)
    pts, p = [start], edges[start]
    while p != start and len(pts) < 10000:
        pts.append(p)
        p = edges[p]
    # (the corners only)
    out = []
    n = len(pts)
    for k in range(n):
        a, b, c_ = pts[k - 1], pts[k], pts[(k + 1) % n]
        if (b[0] - a[0], b[1] - a[1]) != (c_[0] - b[0], c_[1] - b[1]):
            out.append(b)
    return out


def _rz_for(kit, d):
    """The straight's turn whose run points along world direction d (to_world turns clockwise)."""
    run = (1.0, 0.0) if kit['axis'] == 0 else (0.0, 1.0)
    return math.atan2(run[1], run[0]) - math.atan2(d[1], d[0])


def lay(db, plan, family=None, cell=None):
    """The wall round a town plan: {'family', 'pieces': [{'id', 'p': [x, y, z, 0, 0, rz], 'kind'}], 'outline',
    'gates', 'faults': [...]}. Pieces chain by the game's joins; a side's last straight may overlap the one before it
    when the game sets that straight on itself at a shorter step, else the side is lengthened to whole steps."""
    K = kits(db)
    fam = family if family in K else pick_family(db, plan)
    if not fam:
        return {'family': None, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No wall for this culture']}
    kit = K[fam]
    L = kit['L']
    # (an outline whose squares are whole steps, so a side's straights fill it)
    G = cell or L * max(1, round(1024.0 / L))
    # (a town planned inside its wall keeps that wall: traced again round its new plots, at their own slant, the box came
    # out a row wider all round, townbuild.planned)
    poly, th = ([tuple(p) for p in plan['wall_outline']], 0.0) if plan.get('wall_outline') else outline(plan, G, db, L)
    if len(poly) < 4:
        return {'family': fam, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No plots to wall']}
    # (counter-clockwise: turns at outer corners are to the left, +90 in the game's clockwise rz... measured per kit)
    n = len(poly)
    turns = []
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        cr = (b[0] - a[0]) * (c_[1] - b[1]) - (b[1] - a[1]) * (c_[0] - b[0])
        turns.append(1 if cr > 0 else -1)          # (1: a left turn seen from above)
    # the kit's corner for a left turn: its rz turn is clockwise, so a left turn is a negative rz turn
    need = {1: -1, -1: 1}
    # (the way round the game walks its own walls: its commonest corner is the convex one, outer corners being most of a
    # town wall's, so the town lies on that corner's inner side and the straights' buttresses face out. Walked the other
    # way the wall stood inside out, buttresses to the town, the user's first town, 2026-10-31)
    dom = max(kit['corners'], key=lambda h: kit['corners'][h]['n'])
    maj = 1 if sum(turns) >= 0 else -1
    if need[maj] != dom and all(need[-t] in kit['corners'] for t in turns):
        poly = poly[::-1]
        turns = [-t for t in turns[::-1]]
    if any(need[t] not in kit['corners'] for t in turns):
        # (walk the other way round: a kit with only one corner hand fits a convex outline walked either way)
        poly = poly[::-1]
        turns = [-t for t in turns[::-1]]
        if any(need[t] not in kit['corners'] for t in turns):
            return {'family': fam, 'pieces': [], 'outline': poly, 'gates': 0, 'faults': ['This wall turns only one way']}
    pieces, faults = [], []
    # every corner: S0 (in), its chain, S1 (out)
    units = []
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        din = _unit(b[0] - a[0], b[1] - a[1])
        co = kit['corners'][need[turns[k]]]
        rz = _rz_for(kit, din)
        # S0 stands co['p'] before the vertex on the incoming line
        S0 = Pose(b[0] - din[0] * co['p'], b[1] - din[1] * co['p'], 0.0, rz, kit['straight'])
        chain = [S0]
        p = S0
        for t, e in co['chain']:
            p = p.then(e, t)
            chain.append(p)
        units.append(chain)
    streets, roads = _street_crossings(plan, poly)
    gates = 0
    for k in range(n):
        out_ = units[k][-1]
        in_ = units[(k + 1) % n][0]
        b, c_ = poly[k], poly[(k + 1) % n]
        d = _unit(c_[0] - b[0], c_[1] - b[1])
        D = (in_.x - out_.x) * d[0] + (in_.y - out_.y) * d[1]
        lat = -(in_.x - out_.x) * d[1] + (in_.y - out_.y) * d[0]
        if abs(lat) > SNAP:
            faults.append('side %d: corners %.0f units off one line' % (k, lat))
        off = (out_.x - b[0]) * d[0] + (out_.y - b[1]) * d[1]
        side, g = _side(kit, out_, D, d, [c0 - off for c0 in streets.get(k) or []], faults, k)
        gates += g
        for q in side:
            q['run'] = k
        pieces.extend(side)
    for k, chain in enumerate(units):
        # (a tower beside each corner where the game stands one, in the place of the straight there: the sections of the
        # wall meet at towers, the user, 2026-10-31; Imperial corner_01's wall_tower_01 a step along)
        C = next((q for q in chain if q.id != kit['straight']), None)
        # (outer corners only: a tower in an inner corner stood into the town, "too many towers within the borders of the
        # wall", the user's island town)
        outer = need[turns[k]] == dom
        for t, e in ((kit.get('corner_towers') or {}).get(C.id) or ()) if C and outer else ():
            T = C.then(e, t)
            for q in chain:
                if q.id == kit['straight'] and math.hypot(q.x - T.x, q.y - T.y) <= 24 and                         abs(((q.rz - T.rz + math.pi) % (2 * math.pi)) - math.pi) <= math.radians(3):
                    q.id = t
                    break
            else:
                continue
            break
        for q in chain:
            # (the corner at vertex k stands between side k - 1's run and side k's)
            pieces.append({'id': q.id, 'pose': q, 'kind': 'corner' if q.id != kit['straight'] else 'wall', 'corner': k})
    pieces += _big_towers(db, fam, kit, poly, [need[t] == dom for t in turns], pieces)
    return {'family': fam, 'kit': kit, 'pieces': pieces, 'outline': poly, 'gates': gates, 'faults': faults,
            'roads': roads if gates else []}


# the towers that rise over a wall, standing in its line with its lengths running into them, and the keep among them:
# Imperial walls' guardtower_02 at corners and between lengths, 192 under the wall's level (its own 1,863 tall, 870 over
# the wall), and a keep at the wall's level (keep_02, 820 over it), lab jtow1/jtow2. wall_tower_01 alone is the wall's
# own height and didn't read as a tower: "no towers or keeps at all ... and it should have them", the user's
# Chillmorrow, test4
BIG = {'ex_imp': {'tower': 'ex_imp_guardtower_02', 'tower_dz': -192, 'keep': 'ex_imp_keep_02', 'keep_dz': 0, 'every': 6}}
BIG_CLEAR = 900                # (no tower this near a gate or an opening)


def _big_towers(db, fam, kit, poly, outer, pieces):
    """[{'id', 'pose', 'kind': 'bigtower'|'keep', 'dz'}]: a tower on each outer corner and every few lengths along a
    side, the keep on the outer corner on the highest ground."""
    B = BIG.get(fam)
    if not B or not poly:
        return []
    L = kit['L']
    gates = [(p['pose'].x, p['pose'].y) for p in pieces if p.get('kind') in ('gate', 'end')]
    spots = []
    for k, v in enumerate(poly):
        if outer[k]:
            spots.append((v[0], v[1], 'corner', k))
    n = len(poly)
    for k in range(n):
        side = [p for p in pieces if p.get('run') == k and p['id'] == kit['straight']]
        a, b = poly[k], poly[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        side.sort(key=lambda p: (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1])
        every = B['every']
        for i in range(every // 2, len(side) - 2, every):
            q = side[i]['pose']
            spots.append((q.x + d[0] * L / 2.0, q.y + d[1] * L / 2.0, 'side', k))
    spots = [s for s in spots if all(math.hypot(s[0] - g[0], s[1] - g[1]) > BIG_CLEAR for g in gates)]
    keep_at = None
    if db is not None:
        hz = [(mapdata.terrain_z(db, s[0], s[1]) or -9e9, i) for i, s in enumerate(spots) if s[2] == 'corner']
        if hz:
            keep_at = max(hz)[1]
    out = []
    for i, (x, y, _w, k) in enumerate(spots):
        kp = i == keep_at
        t = B['keep'] if kp else B['tower']
        # (turned square to the side it stands on)
        a, b = poly[k], poly[(k + 1) % n]
        rz = _rz_for(kit, _unit(b[0] - a[0], b[1] - a[1]))
        out.append({'id': t, 'pose': Pose(x, y, 0.0, rz, t), 'kind': 'keep' if kp else 'bigtower',
                    'dz': B['keep_dz'] if kp else B['tower_dz']})
    return out


def _unit(x, y):
    h = math.hypot(x, y) or 1.0
    return x / h, y / h


REACH = 3500                   # a street's end is carried on to the wall this far, for a gate


def _street_crossings(plan, poly):
    """({side: [distance along it]} where the plan's streets cross the outline, or would if carried on from their
    ends; [(from, to)] the stretches carried on, to pave). The main street both ways at least, as the game's walled
    towns are entered along their main street."""
    out = defaultdict(list)
    roads = []
    n = len(poly)
    ringed = any(st.get('ring') for st in plan.get('streets') or ())
    for si, st in enumerate(plan.get('streets') or ()):
        if st.get('ring') or st.get('court') or st.get('len'):
            continue                 # (the lane round inside the wall and the courts' lanes lead nowhere out: a gate where
                                     # one happened to end stood behind a row of houses, 7 of 15 gates, lab jgate)
        pts = [tuple(p) for p in st['pts']]
        segs = list(zip(pts, pts[1:]))
        for a, b in segs:
            for k in range(n):
                hit = _cross(a, b, poly[k], poly[(k + 1) % n])
                if hit is not None:
                    out[k].append(hit)
        if len(pts) < 2:
            continue
        for a, b in ((pts[1], pts[0]), (pts[-2], pts[-1])):
            if not _inside(poly, b):
                continue
            d = _unit(b[0] - a[0], b[1] - a[1])
            far = (b[0] + d[0] * REACH, b[1] + d[1] * REACH)
            best = None
            for k in range(n):
                hit = _cross(b, far, poly[k], poly[(k + 1) % n])
                if hit is not None:
                    w = poly[k]
                    e = _unit(poly[(k + 1) % n][0] - w[0], poly[(k + 1) % n][1] - w[1])
                    q = (w[0] + e[0] * hit, w[1] + e[1] * hit)
                    dist = math.hypot(q[0] - b[0], q[1] - b[1])
                    if best is None or dist < best[0]:
                        best = (dist, k, hit, q)
            # (a branch whose end is far from the wall is a lane that stops in town; the main street goes out)
            # (in a town with a lane round inside its wall, the branches end at that lane and only the main street goes out:
            # carried on, a branch's gate opened behind the row of houses along the wall, lab jgate)
            if best and (si == 0 or (best[0] <= REACH / 3 and not ringed)):
                out[best[1]].append(best[2])
                roads.append((b, best[3], st.get('w') or 256))
    return out, roads


def _inside(poly, p):
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _cross(p1, p2, a, b):
    """Where segment p1p2 crosses ab, as the distance from a along ab; else None."""
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    qx, qy = a[0] - p1[0], a[1] - p1[1]
    t = (qx * sy - qy * sx) / den
    u = (qx * ry - qy * rx) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return u * math.hypot(sx, sy)
    return None


TOWER_EVERY = 3


def _side(kit, S0, D, d, crossings, faults, k):
    """The pieces between a corner's out-straight S0 and the next corner's in-straight, D along d: straights at the
    step, a gate where a street crosses, towers as often as the game's. ([pieces], gates)."""
    L = kit['L']
    gate = _best(kit, 'gate')
    tower = _best(kit, 'tower')
    out = []
    # (distances from S0 along the side where a gate should stand: the crossing, less what the corner took)
    want_gate = sorted(set(round(c / L) for c in crossings))
    pos, p, g = 0.0, S0, 0
    since_tower = 0
    # (a tower every few straights, at most TOWER_EVERY: the game's Imperial walls stand 0.45 towers a straight, its
    # wall_tower_01 and its towerb stacks together, lab jwallgame; by wall_tower_01 alone, one in six, they looked bare)
    every = min(int(round(tower[1]['every'])), TOWER_EVERY) if tower else 0
    while True:
        left = D - pos
        nxt = None
        # a gate when this stretch reaches the street (and it fits before the next corner)
        if gate and want_gate and pos + gate[1]['span'] <= D - L * 0.5 and abs((pos + gate[1]['span'] / 2.0) / L - want_gate[0]) <= 1.0:
            nxt = gate
            want_gate.pop(0)
        elif tower and every and since_tower >= every and pos + tower[1]['span'] <= D - L:
            nxt = tower
        if nxt:
            t, v = nxt
            X = p.then(v['e1'], t)
            S1 = X.then(v['e2'], kit['straight'])
            out.append({'id': t, 'pose': X, 'kind': v['kind']})
            if v['kind'] == 'gate':
                g += 1
            since_tower = 0 if v['kind'] == 'tower' else since_tower + 1
            pos += v['span']
            if pos >= D - 1:
                # (the in-line piece brought its own straight where the next corner's stands)
                if abs(pos - D) > 2:
                    faults.append('side %d: ends %.0f units off' % (k, pos - D))
                return out, g
            out.append({'id': kit['straight'], 'pose': S1, 'kind': 'wall'})
            p = S1
            continue
        if not gate and want_gate and abs((pos + L * 1.5) / L - want_gate[0]) <= 0.5 and pos + L * 4 <= D - L:
            # (an opening: the game's wall runs stop with their end pieces; two steps open, the street through it)
            want_gate.pop(0)
            E = kit['ends'].get('fwd')
            if E:
                out.append({'id': E['id'], 'pose': p.then(E['e'], E['id']), 'kind': 'end'})
            p = Pose(p.x + d[0] * L * 3, p.y + d[1] * L * 3, 0.0, p.rz, kit['straight'])
            pos += L * 3
            out.append({'id': kit['straight'], 'pose': p, 'kind': 'wall'})
            E = kit['ends'].get('back')
            if E:
                out.append({'id': E['id'], 'pose': p.then(E['e'], E['id']), 'kind': 'end'})
            g += 1
            since_tower += 1
            continue
        while want_gate and want_gate[0] * L < pos - L:
            want_gate.pop(0)                         # (passed: a gate did not fit there)
        if left <= 2:
            return out, g
        if left >= L - 1:
            p = Pose(p.x + d[0] * L, p.y + d[1] * L, 0.0, p.rz, kit['straight'])
            pos += L
            if pos >= D - 1:
                return out, g                     # (that place is the next corner's own straight)
            out.append({'id': kit['straight'], 'pose': p, 'kind': 'wall'})
            since_tower += 1
            continue
        # less than a step left: the last straight overlaps the one before it, if the game does that
        if kit['overlap'] and left >= L * (1 - OVERLAP_MAX):
            return out, g                          # (the next corner's in-straight overlaps this one: nothing to add)
        faults.append('side %d: %.0f units the wall cannot close' % (k, left))
        return out, g


def _best(kit, kind):
    c = [(t, v) for t, v in kit['inline'].items() if v['kind'] == kind and v['span'] >= kit['L']]
    return max(c, key=lambda tv: tv[1]['n']) if c else None


def pick_family(db, plan):
    """The wall family for the town's culture: the one the culture's game towns stand most often, else the one whose
    family leads the town's buildings, else none."""
    K = kits(db)
    cult = plan.get('culture')
    # (Anvil's and the Gold Coast's towns, out of Imperial, have the Imperial wall when they have none counted of their own)
    for c_ in (cult, 'Imperial') if cult in ('Anvil', 'Gold Coast') else (cult,):
        best = max(K.items(), key=lambda kv: (kv[1].get('cultures') or {}).get(c_, 0), default=None)
        if best and (best[1].get('cultures') or {}).get(c_, 0) >= 2:
            return best[0]
    fam = plan.get('family')
    if fam in K:
        return fam
    return None


SINK = 24                      # a wall piece's foot stands this far under the lowest ground beneath it


def _box(db, pid, pose, memo):
    """A piece's corners in the world and its bounds [x0, y0, z0, x1, y1, z1] (or None)."""
    if pid not in memo:
        ri = db.resolve_id(pid)
        memo[pid] = mapdata.object_bounds(db, ri) if ri is not None else None
    b = memo[pid]
    if not b:
        return None, None
    c, s = math.cos(pose.rz), math.sin(pose.rz)
    return [(pose.x + bx * c + by * s, pose.y - bx * s + by * c) for bx, by in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4]))], b


LEVEL_TOL = 192                # the ground under a wall run is moved towards the run's level by at most this
CUT_TOL = 640                  # (towards the ring's one level: cut down this much at most, raised this much at most)
RAISE_TOL = 512
LEVEL_R = 320                  # (full change within this of the run's line, fading to nothing over LEVEL_BLEND beyond)
LEVEL_BLEND = 384


def level_ground(db, W, skip=(), tol=LEVEL_TOL):
    """The ground along each straight run of the wall evened out towards the run's middle height, by at most tol, fading
    back into the land round it, before the wall is set on it: so a run stays one level, as the game's own do, rather
    than being cut into steps on a lumpy slope (the user, 2026-10-31: "allow the city planner to reshape land to
    accommodate walls ... within tolerance"). What stands on that ground follows it (skip: the town's own new refs).
    Returns the cells changed."""
    import landscape
    runs = defaultdict(list)
    for p in W['pieces']:
        if 'run' in p:
            runs[p['run']].append(p['pose'])
    segs, tz = [], {}
    # (one level for the whole ring: the ground under every run evened towards the middle height of all of it, so the
    # wall goes round at one height as far as the land allows; per run, the user's Chillmorrow stood at 19 levels, and
    # they set it all at one, flattening the ground to it, test4)
    every = sorted(z for ps in runs.values() for z in (mapdata.terrain_z(db, q.x, q.y) for q in ps) if z is not None and z >= 0)
    ring = every[len(every) // 2] if every else None
    for k, ps in runs.items():
        zs = sorted(z for z in (mapdata.terrain_z(db, q.x, q.y) for q in ps) if z is not None)
        if not zs or zs[len(zs) // 2] < 0:
            continue                      # (a run at the water: left as it is)
        segs.append(((ps[0].x, ps[0].y), (ps[-1].x, ps[-1].y), ring))
        tz[k] = ring
    # (the corners too, towards the runs either side: a corner on a cliff's edge stood buried on its high side)
    nk = max(list(runs) + [-1]) + 1
    for p in W['pieces']:
        if 'corner' in p:
            near = [tz[k] for k in ((p['corner'] - 1) % max(1, nk), p['corner']) if k in tz]
            if near:
                q = p['pose']
                segs.append(((q.x, q.y), (q.x, q.y), sum(near) / len(near)))
    if not segs:
        return 0
    reach = LEVEL_R + LEVEL_BLEND
    xs = [c[0] for s_ in segs for c in s_[:2]]
    ys = [c[1] for s_ in segs for c in s_[:2]]
    G = landscape.CELL
    step = G / (landscape.N - 1.0)

    def dist(px, py, a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + dx * t), py - (ay + dy * t))
    new_h, before = {}, {}
    for gx in range(int(math.floor((min(xs) - reach) / G)), int(math.floor((max(xs) + reach) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - reach) / G)), int(math.floor((max(ys) + reach) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(landscape.N):
                for i in range(landscape.N):
                    x, y = gx * G + i * step, gy * G + j * step
                    best = None
                    for a, b, t in segs:
                        d = dist(x, y, a, b)
                        if d >= reach:
                            continue
                        w = 1.0 if d <= LEVEL_R else 0.5 + 0.5 * math.cos(math.pi * (d - LEVEL_R) / LEVEL_BLEND)
                        if best is None or w > best[0]:
                            best = (w, t)
                    if not best:
                        continue
                    n = j * landscape.N + i
                    z = h[n]
                    want = max(z - CUT_TOL, min(z + RAISE_TOL, best[1]))
                    nz = z + best[0] * (want - z)
                    if abs(nz - z) >= 1:
                        h[n] = nz
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return len(new_h)


SHOW = 200                     # a wall stands at least this much of its height out of the highest ground along its run
SHOW_SHARE = 0.5               # and at least this share of it: the game's straights stand 180-460 over the ground (0.64-0.94
                               # of ex_imp_wall_01 out); at SHOW alone a run down a slope was buried to 200 at its high end,
                               # "far too short ... a lot of sunken wall", the user's Chillmorrow, test4
def grounded(db, W):
    """The wall set on the ground the game's way: every straight run between corners one level, as the game's own town walls
    stand (120 of 120 neighbouring Imperial straights level, lab jwallz2), sunk so its foot is SINK under the lowest
    ground along it and at least SHOW of it stands out of the highest; a run on ground too steep for one level is cut
    into level stretches. Corners take the level of the runs either side when that buries their foot. Pieces over open
    water or on no land are left out, as faults. W changed. (Each piece set on the ground under it alone made a jagged
    wall at a dozen heights, the user's first town, 2026-10-31.)"""
    memo = {}
    keep, wet = [], 0
    for p in W['pieces']:
        cs, b = _box(db, p['id'], p['pose'], memo)
        if not cs:
            continue
        pts = cs + [((cs[i][0] + cs[(i + 1) % 4][0]) / 2, (cs[i][1] + cs[(i + 1) % 4][1]) / 2) for i in range(4)]
        pts.append((p['pose'].x, p['pose'].y))
        zs = [z for z in (mapdata.terrain_z(db, x, y) for x, y in pts) if z is not None]
        if not zs or max(zs) < 0:
            wet += 1
            continue
        # (its low ground the third lowest of its nine: a corner over a cliff's edge or the shore no longer drags the
        # whole run down to the sea floor, its foot showing a little there as the user set their own, Chillmorrow test4)
        zs.sort()
        p['corners'], p['_g'], p['_b'] = cs, (zs[min(2, len(zs) - 1)], zs[-1]), b
        keep.append(p)
    def span(ps):
        # (the levels that bury every foot and show enough of every top: origin z in [lo, hi])
        lo = max(p['_g'][1] + max(SHOW, SHOW_SHARE * (p['_b'][5] - p['_b'][2])) - p['_b'][5] for p in ps)
        hi = min(p['_g'][0] - SINK - p['_b'][2] for p in ps)
        return lo, hi
    def level(ps):
        lo, hi = span(ps)
        z = max(lo, min(hi, sum(p['_g'][0] + p['_g'][1] for p in ps) / (2.0 * len(ps)) + 208))
        for p in ps:
            p['pose'].z = min(z, p['_g'][0] - SINK - p['_b'][2])
    tower_id = next((t for v in ((W.get('kit') or {}).get('corner_towers') or {}).values() for t, _e in v), None)
    # the levels set round the whole wall in order, corner by side by corner: each stretch as long as one level can serve
    # it, the next stretch starting at a tower so the step hides in it. (A level per side and each corner set to suit one
    # side left a step at every corner between sides at different heights, 36 joins up to 889 units apart on the user's
    # island, lab jjoins)
    straight = (W.get('kit') or {}).get('straight')
    n = max([p.get('corner', -1) for p in keep] + [p.get('run', -1) for p in keep] + [-1]) + 1
    order = []
    for k in range(n):
        order += [p for p in keep if p.get('corner') == k]
        order += [p for p in keep if p.get('run') == k]
    order += [p for p in keep if 'corner' not in p and 'run' not in p and 'dz' not in p]
    big = [p for p in keep if 'dz' in p]

    def towered(i):
        # (the step between order[i - 1] and order[i]: whichever of the two is a straight becomes the tower, so it
        # stands at the change; a corner or a gate arch can't be one)
        for p in [order[i]] + ([order[i - 1]] if i > 0 else [order[-1]]):
            if 'tower' in p['id'].lower():
                return
            if tower_id and p['id'] == straight:
                p['id'] = p['pose'].id = tower_id
                p['kind'] = 'tower'
                nb_ = _box(db, tower_id, p['pose'], memo)[1]
                if nb_:
                    p['_b'] = nb_
                return
    seg, starts = [], []
    for i, p in enumerate(order):
        if seg:
            lo, hi = span(seg + [p])
            if lo > hi:
                level(seg)
                seg = []
                starts.append(i)
        seg.append(p)
    if seg:
        level(seg)
    for i in starts:
        towered(i)
    # (round the loop: where the last stretch meets the first at another level, a tower there too)
    if order and starts and abs(order[-1]['pose'].z - order[0]['pose'].z) > 48:
        towered(0)
    # (the towers and the keep at the level of the wall running into them, the highest where two levels meet so the
    # step hides in the tower; sunk further where the ground under them lies lower)
    for p in big:
        q = p['pose']
        near = sorted(order, key=lambda o: math.hypot(o['pose'].x - q.x, o['pose'].y - q.y))[:2]
        wz = max(o['pose'].z for o in near) if near else p['_g'][0] + 208
        gc = mapdata.terrain_z(db, q.x, q.y)
        q.z = wz + p['dz'] if gc is None else min(wz + p['dz'], gc - SINK - p['_b'][2])
    for p in keep:
        for k_ in ('_g', '_b'):
            p.pop(k_, None)
    W['pieces'] = keep
    if wet:
        W['faults'].append('%d pieces over water left out' % wet)
    return W


def preview(db, plan, family=None):
    """The wall for the map: {'family', 'outline', 'pieces': [[kind, [[x, y] x4]]], 'gates', 'faults', 'roads'}."""
    W = lay(db, plan, family)
    memo = {}
    ps = []
    for p in W['pieces']:
        cs, _b = _box(db, p['id'], p['pose'], memo)
        if cs:
            ps.append([p['kind'], [[round(x), round(y)] for x, y in cs]])
    return {'family': W['family'], 'outline': [[round(x), round(y)] for x, y in W['outline']], 'pieces': ps,
            'gates': W['gates'], 'faults': W['faults'][:6], 'roads': [[list(a), list(b), w] for a, b, w in W.get('roads') or []]}


def choices(db):
    """[{'id', 'piece', 'towns', 'cultures'}]: the walls the game runs, the most used first."""
    out = []
    for f, k in kits(db).items():
        out.append({'id': f, 'piece': k['straight'], 'towns': (k.get('towns') or [])[:4], 'cultures': k.get('cultures') or {},
                    'placed': k['placed'], 'gate': any(v['kind'] == 'gate' for v in k['inline'].values())})
    return sorted(out, key=lambda o: -o['placed'])


def road_patches(roads):
    """The land patches (512 across) a wall's gate roads cross, their width either side."""
    out = set()
    for a, b, w in roads:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / 128))
        for i in range(n + 1):
            x = a[0] + (b[0] - a[0]) * i / n
            y = a[1] + (b[1] - a[1]) * i / n
            r = w / 2.0
            for dx in (-r, 0, r):
                for dy in (-r, 0, r):
                    out.add((int((x + dx) // 512), int((y + dy) // 512)))
    return out
