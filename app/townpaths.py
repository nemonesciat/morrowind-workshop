"""A built town's walking paths outdoors (townbuild.make): the path grid its people walk by, along its streets and
square and out of every door, cell by cell as the game keeps them. Without one a town's people stood where they were
put or walked into walls (the user, 2026-11-02: "level walking paths that people can use").

As the game lays its own towns' (survey of 236 town cells, lab p23): a point every 384 or so along the ways (its links
387 long, p10 214, p90 711), 62 points a cell, a point in front of every door (the nearest 262 from it), links no
steeper than its own (p99 0.7 rise a unit), none through a building, wall or tree. The paths the land already had
in the town's cells stay outside the town and go inside it."""
import math
import re
from collections import Counter

import mapdata

STEP = 384                     # (a point this far along a street from the last)
JOIN = 2 * STEP                # (points of two streets this near are joined: a crossing)
DOOR_OUT = 110                 # (the door's point: this far out in front of it, where the ground was fitted)
DOOR_FOOT = (1, 2, 3, 4.5, 6)  # (and further out, by these many, when that is under a stair)
DOOR_REACH = 900               # (a door's point is joined to a street's this near it at most)
STEEP = 0.7                    # (a link climbing more than this a unit is no way: the game's p99)
PAD = 28                       # (a link keeps this far clear of anything standing)
ROUTE = 128                    # (a walk round things is found on a lattice this fine)
ROUTE_MAX = 3000               # (and only to a web this near)
WEB_REACH = 6000               # (a web of its own is walked to the main one from this far)
ROUTE_NODES = 14000            # (the lattice walked at most)
LINK_MAX = 640                 # (no link longer: the game's p90 711)
SQUARE_STEP = 448              # (a square is walked on a lattice this fine)
OPEN = re.compile(r'gate|_arch|wallent|entrance|awning|canopy|overhang|_sign', re.I)
LAST = {}                      # (how the last lay went: for the lab)
SOFT = re.compile(r'grass|flora_.*(fern|bush|plant)|kelp|reed|_weed|lily|shrub_small|_moss', re.I)


def _boxes(db, keys, skip=(), scene=None):
    """What stands in the way, cell by cell: [(x, y, c, s, x0, y0, x1, y1, z0, z1)] in each thing's own frame (and
    its mesh into scene, a seethrough.Scene, when given)."""
    import seethrough
    out = []
    tri = {}
    for ck in keys:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            b = r.get('b')
            if not b or r['type'] in ('NPC_', 'CREA', 'LEVC', 'DOOR') or r['type'] in mapdata.ITEM_TYPES or r['k'] in skip:
                continue
            s = r.get('s') or 1.0
            if (b[5] - b[2]) * s < 60 or max(b[3] - b[0], b[4] - b[1]) * s < 40 or SOFT.search(r['id']) or OPEN.search(r['id']):
                continue                    # (grass and small plants: walked through; a gate or an arch: walked under)
            out.append((r['p'][0], r['p'][1], math.cos(r['p'][5]), math.sin(r['p'][5]), b[0] * s, b[1] * s, b[3] * s, b[4] * s,
                        r['p'][2] + b[2] * s, r['p'][2] + b[5] * s))
            if scene is not None:
                ri = r.get('ri') if r.get('ri') is not None else db.resolve_id(r['id'])
                model = db.recs[ri][5] if ri is not None else None
                if model and 'marker' not in model.lower():
                    if model not in tri:
                        tri[model] = seethrough.model_tris(db, model)
                    scene.add_model(tri[model], tuple(r['p'][:6]), s)
    return out


KNEE, HEAD = 40, 110            # (a link is walked if nothing meets these heights over its line: the boxes of rocks and
                               # porches are far bigger than they are; by box, 45% of the game's own town links ran
                               # through something, by mesh 'through' below)


class _Space:
    def __init__(self, boxes, scene=None):
        self.boxes = boxes
        self.scene = scene
        self.grid = {}
        for k, b in enumerate(boxes):
            R = math.hypot(max(abs(b[4]), abs(b[6])), max(abs(b[5]), abs(b[7]))) + PAD
            for gx in range(int((b[0] - R) // 512), int((b[0] + R) // 512) + 1):
                for gy in range(int((b[1] - R) // 512), int((b[1] + R) // 512) + 1):
                    self.grid.setdefault((gx, gy), []).append(k)

    def blocked(self, x, y, z=None, pad=PAD):
        for k in self.grid.get((int(x // 512), int(y // 512)), ()):
            bx, by, c, s, x0, y0, x1, y1, z0, z1 = self.boxes[k]
            if z is not None and (z1 < z + 24 or z0 > z + 120):
                continue                    # (under foot, a step or a rug; or overhead, a bridge or an awning)
            dx, dy = x - bx, y - by
            lx, ly = dx * c - dy * s, dx * s + dy * c        # (into its frame: turned back, as the game turns clockwise)
            if x0 - pad < lx < x1 + pad and y0 - pad < ly < y1 + pad:
                return True
        return False

    def clear(self, a, b, pad=PAD):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if self.scene is not None:
            if d < 1:
                return True
            u = ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
            for h in (KNEE, HEAD):
                for side in (-1, 0, 1) if pad > 8 else (0,):
                    ox, oy = a[0] - u[1] * side * pad, a[1] + u[0] * side * pad
                    L = math.hypot(d, b[2] - a[2])
                    dz = (b[2] - a[2]) / L
                    if self.scene.nearest_any((ox, oy, a[2] + h), (u[0] * d / L, u[1] * d / L, dz), L) is not None:
                        return False
            return True
        n = max(1, int(d / 24))
        return not any(self.blocked(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n,
                                    a[2] + (b[2] - a[2]) * t / n, pad) for t in range(1, n))


def _along(pts, step):
    """Points every `step` along a polyline, its ends included."""
    out = [tuple(pts[0])]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(round(L / step)))
        out += [(x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n) for t in range(1, n + 1)]
    return out


def lay(db, plan, cells, doors, skip=()):
    """The town's paths: (points [[x, y, z]], links {(a, b)}, door points [index]). doors: [(x, y, out x, out y)] each
    built door and the way out of it."""
    import seethrough
    sc = seethrough.Scene()
    sp = _Space(_boxes(db, cells, skip, sc), sc)
    P, links, chains = [], set(), []
    LAST.clear()
    LAST.update(tried=0, water=0, blocked=0, links=0, refused=Counter(), doors=0, door_linked=0)

    def point(x, y, soft=False):
        LAST['tried'] += 1
        z = mapdata.terrain_z(db, x, y)
        if z is None or z < 16:
            LAST['water'] += 1
            return None
        if sp.blocked(x, y, z):
            # (a little to one side, round the corner of what stands there)
            for dx, dy in ((48, 0), (-48, 0), (0, 48), (0, -48), (96, 0), (-96, 0), (0, 96), (0, -96)):
                z2 = mapdata.terrain_z(db, x + dx, y + dy)
                if z2 is not None and z2 >= 16 and not sp.blocked(x + dx, y + dy, z2):
                    x, y, z = x + dx, y + dy, z2
                    break
            else:
                LAST['blocked'] += 1
                return None
        P.append([x, y, z])
        return len(P) - 1

    def link(a, b):
        if a is None or b is None or a == b:
            return False
        pa, pb = P[a], P[b]
        d = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if d < 1:
            return False
        if abs(pb[2] - pa[2]) > STEEP * d:
            LAST['refused']['steep'] += 1
            return False
        if not sp.clear(pa, pb):
            LAST['refused']['through'] += 1
            return False
        links.add((min(a, b), max(a, b)))
        return True
    # (the streets, main first: a chain of points along each, joined end to end)
    for st in sorted(plan.get('streets') or (), key=lambda s: not s.get('main')):
        pts = [tuple(p[:2]) for p in st.get('pts') or ()]
        if len(pts) < 2:
            continue
        ch = [i for i in (point(x, y) for x, y in _along(pts, STEP)) if i is not None]
        # (each point to the next it can walk to, past one that couldn't be set or a link that couldn't be walked:
        # by its neighbour only, a lamp post or a cart in the street cut it in two)
        for k, a in enumerate(ch):
            for b in ch[k + 1:k + 4]:
                if math.hypot(P[b][0] - P[a][0], P[b][1] - P[a][1]) > LINK_MAX * 1.6:
                    break
                if link(a, b):
                    break
        chains.append(ch)
    sq = plan.get('square')
    if sq:
        x0, y0, r = sq
        lat = {}
        n = int(r // SQUARE_STEP)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x, y = x0 + i * SQUARE_STEP, y0 + j * SQUARE_STEP
                if math.hypot(x - x0, y - y0) <= r:
                    lat[(i, j)] = point(x, y)
        for (i, j), a in lat.items():
            for di, dj in ((1, 0), (0, 1)):
                link(a, lat.get((i + di, j + dj)))
        chains.append([a for a in lat.values() if a is not None])
    # (crossings: a street's points joined to the nearest of every other street's, when near)
    street = [i for ch in chains for i in ch]
    for k, ch in enumerate(chains):
        others = [i for c2 in chains[k + 1:] for i in c2]
        for c2 in chains[k + 1:]:
            # (each pair of streets joined where they come nearest, by the nearest pair that can be walked)
            pairs = sorted(((math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1]), a, b) for a in ch for b in c2), key=lambda t: t[0])
            for d, a, b in pairs[:8]:
                if d > JOIN:
                    break
                if link(a, b):
                    break
    # (a town without streets, its houses about open ground: its ways start from its middle, the square or the doors')
    street = [i for ch in chains for i in ch]
    if not street and doors:
        cx = sum(d[0] for d in doors) / len(doors)
        cy = sum(d[1] for d in doors) / len(doors)
        for r_ in (0, 192, 384, 768):
            h = next((k for k in (point(cx + r_ * math.cos(t * math.pi / 4), cy + r_ * math.sin(t * math.pi / 4)) for t in range(8 if r_ else 1))
                      if k is not None), None)
            if h is not None:
                street.append(h)
                break

    def route(a, web=None, reach=ROUTE_MAX):
        """A walk from point a to the nearest point of the web (street), round what stands between: the shortest way
        on a ROUTE lattice, then pulled straight where it can be walked straight. The points it adds, or None."""
        import heapq
        web = street if web is None else web
        if not web:
            return None
        pa = P[a]
        tgt = min(web, key=lambda b: math.hypot(P[b][0] - pa[0], P[b][1] - pa[1]))
        span = math.hypot(P[tgt][0] - pa[0], P[tgt][1] - pa[1])
        if span > reach:
            return None
        m_ = ROUTE * (4 if reach <= ROUTE_MAX else 14)        # (room to go round: a web of its own may lie past a ravine)
        lo_x, lo_y = min(pa[0], P[tgt][0]) - m_, min(pa[1], P[tgt][1]) - m_
        node = {}

        def at(i, j):
            if (i, j) not in node:
                x, y = lo_x + i * ROUTE, lo_y + j * ROUTE
                z = mapdata.terrain_z(db, x, y)
                node[(i, j)] = None if z is None or z < 16 or sp.blocked(x, y, z, pad=20) else (x, y, z)
            return node[(i, j)]
        nx_, ny_ = int((max(pa[0], P[tgt][0]) + m_ - lo_x) / ROUTE) + 1, int((max(pa[1], P[tgt][1]) + m_ - lo_y) / ROUTE) + 1
        if nx_ * ny_ > ROUTE_NODES:
            return None
        goal = {}
        for b in web:
            pb = P[b]
            if lo_x <= pb[0] <= lo_x + nx_ * ROUTE and lo_y <= pb[1] <= lo_y + ny_ * ROUTE:
                goal[(int(round((pb[0] - lo_x) / ROUTE)), int(round((pb[1] - lo_y) / ROUTE)))] = b
        s0 = (int(round((pa[0] - lo_x) / ROUTE)), int(round((pa[1] - lo_y) / ROUTE)))
        h = lambda k: math.hypot((k[0] * ROUTE + lo_x) - P[tgt][0], (k[1] * ROUTE + lo_y) - P[tgt][1])
        best, came, todo, end = {s0: 0.0}, {}, [(h(s0), s0)], None
        while todo:
            _f, k = heapq.heappop(todo)
            if k in goal and k != s0:
                end = k
                break
            here = at(*k) if k != s0 else pa
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                n_ = (k[0] + di, k[1] + dj)
                if not (0 <= n_[0] <= nx_ and 0 <= n_[1] <= ny_):
                    continue
                q = at(*n_)
                if q is None:
                    continue
                d = ROUTE * (1.4142 if di and dj else 1.0)
                if abs(q[2] - here[2]) > STEEP * d or not sp.clear(here, q, pad=12):
                    continue
                c = best[k] + d + abs(q[2] - here[2]) * 2      # (the level way round before the climb)
                if c < best.get(n_, 1e18):
                    best[n_] = c
                    came[n_] = k
                    heapq.heappush(todo, (c + h(n_), n_))
        if end is None:
            return None
        path = [end]
        while path[-1] != s0:
            path.append(came[path[-1]])
        path.reverse()
        pts = [pa] + [at(*k) for k in path[1:-1]] + [P[goal[end]]]
        # (pulled straight: from each kept point the farthest one it walks to in a line, at most LINK_MAX on)
        out, i = [a], 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1 and (math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]) > LINK_MAX or abs(pts[j][2] - pts[i][2]) >
                                 STEEP * math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]) or not sp.clear(pts[i], pts[j])):
                j -= 1
            if j == len(pts) - 1:
                nxt = goal[end]
            else:
                P.append(list(pts[j]))
                nxt = len(P) - 1
            links.add((min(out[-1], nxt), max(out[-1], nxt)))
            out.append(nxt)
            i = j
        return out[1:]
    # (every door: a point in front of it, joined to the nearest point of the web it can walk to in a line, else by a
    # walk round what stands between; each walk joins the web, so the next door's may end on it)
    door_pts = []
    order = sorted(doors, key=lambda d: min((math.hypot(P[b][0] - d[0], P[b][1] - d[1]) for b in street), default=0.0))
    for x, y, ux, uy in order:
        # (a door up its stairs or stalk: its point at their foot, out along the way they lead down)
        a = next((k for k in (point(x + ux * DOOR_OUT * t, y + uy * DOOR_OUT * t) for t in DOOR_FOOT) if k is not None), None)
        if a is None:
            continue
        door_pts.append(a)
        LAST['doors'] += 1
        near = sorted((b for b in street if math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1]) <= DOOR_REACH),
                      key=lambda b: math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1]))
        if any(link(a, b) for b in near[:6]):
            LAST['door_linked'] += 1
            street.append(a)
            continue
        added = route(a)
        if added:
            LAST['door_linked'] += 1
            LAST['routed'] = LAST.get('routed', 0) + 1
            street += [a] + added[:-1]
        elif not street:
            street.append(a)                # (the first door of an open town: the others' walks lead to it)
    # (every web joined to the biggest: a street ending short of another, or one whose crossing couldn't be walked,
    # stood as a web of its own, a quarter of a hillside city's points, the city round of 2026-11-02)
    for _round in range(3):
        webs = _webs(len(P), links)
        if len(webs) < 2:
            break
        main = set(webs[0])
        joined = False
        for w in webs[1:]:
            if len(w) < 2:
                continue
            a = min(w, key=lambda i: min(math.hypot(P[i][0] - P[j][0], P[i][1] - P[j][1]) for j in main))
            near = sorted(main, key=lambda j: math.hypot(P[a][0] - P[j][0], P[a][1] - P[j][1]))[:6]
            if any(math.hypot(P[a][0] - P[j][0], P[a][1] - P[j][1]) <= JOIN * 2 and link(a, j) for j in near) or route(a, sorted(main), WEB_REACH):
                LAST['webs_joined'] = LAST.get('webs_joined', 0) + 1
                joined = True
        if not joined:
            break
    # (none left alone: a point nobody can walk to or from is no use)
    used = {i for e in links for i in e}
    keep = [i for i in range(len(P)) if i in used]
    ren = {o: n for n, o in enumerate(keep)}
    return [P[i] for i in keep], {(ren[a], ren[b]) for a, b in links}, [ren[a] for a in door_pts if a in ren]


def _webs(n, links):
    """The linked points as webs (union-find), biggest first: [[index]]."""
    root = list(range(n))

    def f(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for a, b in links:
        root[f(a)] = f(b)
    used = {i for e in links for i in e}
    by = {}
    for i in used:
        by.setdefault(f(i), []).append(i)
    return sorted(by.values(), key=len, reverse=True)


def write(db, P, links, outline=None):
    """The paths into each cell's path grid; the land's own points outside the town kept. No Undo step. {cell: points}"""
    import pathgrid
    import townplan
    cell = lambda p: (math.floor(p[0] / 8192.0), math.floor(p[1] / 8192.0))
    # (a link from one cell into the next: each cell keeps its own grid, so each side runs on to the border, a point
    # just inside it; cut there, its ends stood alone)
    P = [list(p) for p in P]
    links = set(links)
    for a, b in sorted(links):
        ca, cb = cell(P[a]), cell(P[b])
        if ca == cb:
            continue
        links.discard((a, b))
        for me, other, c in ((a, b, ca), (b, a, cb)):
            p, q = P[me], P[other]
            ts = []
            for k, lo in ((0, c[0] * 8192.0), (1, c[1] * 8192.0)):
                dv = q[k] - p[k]
                if dv:
                    for edge in (lo, lo + 8192.0):
                        t = (edge - p[k]) / dv
                        if 0 < t <= 1:
                            ts.append(t)
            t = min(ts, default=1.0)
            L = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
            t = max(0.0, t - 8.0 / L)
            if t * L < 16:
                continue
            x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
            z = mapdata.terrain_z(db, x, y)
            P.append([x, y, z if z is not None else p[2] + (q[2] - p[2]) * t])
            links.add((me, len(P) - 1))
    used = {i for e in links for i in e}
    by = {}
    for i, p in enumerate(P):
        if i not in used:
            continue
        by.setdefault('#%d,%d' % (math.floor(p[0] / 8192.0), math.floor(p[1] / 8192.0)), []).append(i)
    out = {}
    for ck, idx in by.items():
        own = {o: n for n, o in enumerate(idx)}
        pts = [P[i] for i in idx]
        es = [(own[a], own[b]) for a, b in links if a in own and b in own]
        had = pathgrid.read(db, ck)
        if had and had.get('pts'):
            gx, gy = (int(v) for v in ck[1:].split(','))
            old = [[p[0] + gx * 8192, p[1] + gy * 8192, p[2]] for p in had['pts']]
            stay = [k for k, p in enumerate(old) if not (outline and (townplan._inside(outline, p[0], p[1]) or townplan._edge_dist(outline, p[0], p[1]) < 600))]
            re_ = {o: len(pts) + n for n, o in enumerate(stay)}
            pts = pts + [old[k] for k in stay]
            es += [(re_[a], re_[b]) for a, b in had.get('edges') or () if a in re_ and b in re_]
        if len(pts) < 2:
            continue
        pathgrid.save(db, ck, pts, [list(e) for e in es], commit=False)
        out[ck] = len(pts)
    return out


def check(db, cells):
    """The town's paths as walked: {'points', 'links', 'steep', 'through', 'alone'}: links climbing more than STEEP a
    unit, links through something standing, points with no link (the game's own: lab p23)."""
    import pathgrid
    import seethrough
    sc = seethrough.Scene()
    sp = _Space(_boxes(db, cells, (), sc), sc)
    F = {'points': 0, 'links': 0, 'steep': 0, 'through': 0, 'alone': 0}
    allp, alle = [], []
    for ck in cells:
        g = pathgrid.read(db, ck)
        if not g or not g.get('pts'):
            continue
        gx, gy = (int(v) for v in ck[1:].split(','))
        P = [[p[0] + gx * 8192, p[1] + gy * 8192, p[2]] for p in g['pts']]
        F['points'] += len(P)
        base = len(allp)
        allp += P
        alle += [(a + base, b + base) for a, b in g.get('edges') or ()]
        used = set()
        for a, b in g.get('edges') or ():
            used |= {a, b}
            F['links'] += 1
            d = math.hypot(P[b][0] - P[a][0], P[b][1] - P[a][1])
            if d > 1 and abs(P[b][2] - P[a][2]) > STEEP * d:
                F['steep'] += 1
            if not sp.clear(P[a], P[b], pad=4):
                F['through'] += 1
        F['alone'] += len(P) - len(used)
        # (and the points cut off from the cell's main web: a door's point that leads to no street)
        root = list(range(len(P)))
        def find(i):
            while root[i] != i:
                root[i] = root[root[i]]
                i = root[i]
            return i
        for a, b in g.get('edges') or ():
            root[find(a)] = find(b)
        sizes = {}
        for i in used:
            sizes[find(i)] = sizes.get(find(i), 0) + 1
        F['cut off'] = F.get('cut off', 0) + (len(used) - max(sizes.values()) if sizes else 0)
    # (the whole town's: a cell's points by its border joined to the next cell's there, as people walk on across)
    cellk = lambda p: (math.floor(p[0] / 8192.0), math.floor(p[1] / 8192.0))
    edge = [i for i, p in enumerate(allp) if min(p[0] % 8192, 8192 - p[0] % 8192, p[1] % 8192, 8192 - p[1] % 8192) < 64]
    for x, i in enumerate(edge):
        for j in edge[x + 1:]:
            if abs(allp[i][0] - allp[j][0]) < 48 and abs(allp[i][1] - allp[j][1]) < 48 and cellk(allp[i]) != cellk(allp[j]):
                alle.append((i, j))
    W = _webs(len(allp), alle)
    F['town cut off'] = sum(len(w) for w in W[1:])
    return F
