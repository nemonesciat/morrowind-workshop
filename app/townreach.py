"""Every door of a made town can be walked to from its streets.

The town's makers each keep a door's own way clear (a strip in front of it), and none of them looks at the whole
walk from the street to the door. A house whose door opened into the court behind it, between its neighbours, was
shut in by the yard's fence, its barrels and its plants: the game found no way from that door to anywhere (the
first walk of a made town by machine, Walkford, 2026-11-15: one house door in eighteen).

So, once everything of the town stands: a walking grid of its ground. What is in a walker's way is read off the
models themselves, every face that stands in a walker's height over the land, grown by a walker's half-width; ground
steeper than the game's walkers climb is no way either. The grid is flooded from the streets. A door whose front the
flood does not reach gets a way opened: the cheapest walk from it to walkable ground through the dressing alone
(never through a building, a wall or a rock), and the dressing on that walk is taken out again, with what stood on
it. A door shut in by more than the dressing is reported and left.

Checked against the game: on Walkford this grid and the game's own path finder agree on all eighteen house doors
(seventeen reached, the same one cut off).
"""
import collections
import heapq
import math
import re

import mapdata
import seethrough

STEP = 12.0                    # the grid's cell
GROW = 4                       # cells a standing thing is grown by: 48. The game's path finder keeps its walkers
                               # (half-width 29) off everything by some 40 once its own grid has rounded up, so a gap
                               # under 85 to 95 is no way for it: the court at Walkford, 68 to 90 wide beside a round
                               # cage, was shut to the game and open here at a cell of 24 grown by one and at 12 grown
                               # by three. Grown by four a gap wants 96 to 108: a little more than the game asks
LOW, HIGH = 4.0, 126.0         # a walker's body over the ground: a face in this band is in the way,
CLIMB = 34.0                   # where the face itself rises over what a walker steps up (a stair's riser, a sill and
                               # a kerb do not; a cage's wall does from its foot: read from 28 up, a round cage was
                               # narrower than it is and a 68-wide gap beside it passed that the game's walkers cannot)
SLOPE = 49.0                   # degrees: steeper ground between two cells is no way (the game's walkers' own limit)
SAMPLE = 12.0                  # a face is read every this far along it
LOOSE_COST = 60                # a cell of dressing against a free one, for the way that is opened
DOOR_HIGH = 150.0              # a door whose front stands this far over the land is a wall-walk's or a balcony's:
                               # reached through its tower, not from the street
RIDER_NEAR, RIDER_UP = 70.0, (8.0, 220.0)     # what stands on a thing taken out goes with it
NOT_IN_WAY = re.compile(r'grass|ivy|vine|lichen|moss|shelffungus|marker|light_|awning|cloth|banner|flag|sign', re.I)
STAYS = re.compile(r'rock|boulder|terrain_', re.I)
OPEN_CELLS = 6000              # this many cells walked on from a door's front without a wall closing them in: outdoors
FRONT = 110.0                  # a door's front: this far out of it (where the game sets a walker down, doors.outside_spot)
STRAIGHT = 360.0               # how far straight out of a door its way may run between grown walls
MOST_TRIES = 4
LAST = {}


def _faces(db, r):
    """The model's faces in the world: (corner, edge, edge), floors and roofs left out."""
    mdl = db.recs[r['ri']][5]
    if not mdl or 'marker' in mdl.lower():
        return
    try:
        tris = seethrough.model_tris(db, mdl)
    except Exception:
        return
    p = r['p']
    (a, b, c), (d, e, f), (g, h, i) = seethrough._matrix(p[3], p[4], p[5])
    s = r.get('s') or 1.0
    for t in tris:
        w = []
        for k in (0, 3, 6):
            x, y, z = t[k] * s, t[k + 1] * s, t[k + 2] * s
            w.append((p[0] + a * x + b * y + c * z, p[1] + d * x + e * y + f * z, p[2] + g * x + h * y + i * z))
        u = (w[1][0] - w[0][0], w[1][1] - w[0][1], w[1][2] - w[0][2])
        v = (w[2][0] - w[0][0], w[2][1] - w[0][1], w[2][2] - w[0][2])
        nz = u[0] * v[1] - u[1] * v[0]
        ln = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2 + nz * nz)
        if ln < 1e-6 or abs(nz) / ln > 0.7:
            continue                        # (a floor, a stair's tread, a roof: stood on or over the head)
        yield w[0], u, v


DISC = [(di, dj) for di in range(-GROW, GROW + 1) for dj in range(-GROW, GROW + 1) if di * di + dj * dj <= GROW * GROW + 1]


class Grid(object):
    def __init__(self, db, box):
        self.db = db
        self.x0, self.y0, x1, y1 = box
        self.nx, self.ny = int((x1 - self.x0) / STEP) + 1, int((y1 - self.y0) / STEP) + 1
        self.g = [[None] * self.nx for _ in range(self.ny)]
        self.fixed = [[False] * self.nx for _ in range(self.ny)]
        self.loose = {}                     # (i, j) -> set of ref keys of the dressing in the way there
        self.rise = STEP * math.tan(math.radians(SLOPE))
        self.bf = None
        self.bl = None

    def cell(self, x, y):
        return int((x - self.x0) / STEP), int((y - self.y0) / STEP)

    def inside(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny

    def ground(self, i, j):
        v = self.g[j][i]
        if v is None:
            v = self.g[j][i] = mapdata.terrain_z(self.db, self.x0 + (i + 0.5) * STEP, self.y0 + (j + 0.5) * STEP) or 0.0
        return v

    def stand(self, r, key=None):
        """A thing's faces onto the grid: fixed, or dressing under its key."""
        g0 = mapdata.terrain_z(self.db, r['p'][0], r['p'][1])
        for o, u, v in _faces(self.db, r):
            zs = (o[2], o[2] + u[2], o[2] + v[2])
            top = max(zs)
            if g0 is not None and (min(zs) > g0 + HIGH + 500.0 or top < g0 + LOW - 500.0):
                continue
            nu = max(1, int(math.sqrt(u[0] * u[0] + u[1] * u[1] + u[2] * u[2]) / SAMPLE))
            nv = max(1, int(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) / SAMPLE))
            for a in range(nu + 1):
                fa = a / float(nu)
                for b in range(nv + 1):
                    fb = b / float(nv)
                    if fa + fb > 1.0001:
                        break
                    i, j = self.cell(o[0] + u[0] * fa + v[0] * fb, o[1] + u[1] * fa + v[1] * fb)
                    if not self.inside(i, j):
                        continue
                    gz = self.ground(i, j)
                    if top > gz + CLIMB and gz + LOW < o[2] + u[2] * fa + v[2] * fb < gz + HIGH:
                        if key is None:
                            self.fixed[j][i] = True
                        else:
                            self.loose.setdefault((i, j), set()).add(key)

    def grow(self):
        """What is in the way grown by a walker's half-width."""
        nx, ny = self.nx, self.ny
        bf = [[False] * nx for _ in range(ny)]
        for j in range(ny):
            row = self.fixed[j]
            for i in range(nx):
                if row[i]:
                    for di, dj in DISC:
                        if 0 <= j + dj < ny and 0 <= i + di < nx:
                            bf[j + dj][i + di] = True
        bl = [[False] * nx for _ in range(ny)]
        for (i, j), keys in self.loose.items():
            if keys:
                for di, dj in DISC:
                    if 0 <= j + dj < ny and 0 <= i + di < nx:
                        bl[j + dj][i + di] = True
        self.bf, self.bl = bf, bl

    def free_near(self, i, j, rad=10, loose_ok=False):
        best = None
        for dj in range(-rad, rad + 1):
            for di in range(-rad, rad + 1):
                a, b = i + di, j + dj
                if self.inside(a, b) and not self.bf[b][a] and (loose_ok or not self.bl[b][a]):
                    d = di * di + dj * dj
                    if best is None or d < best[0]:
                        best = (d, a, b)
        return (best[1], best[2]) if best else None

    def flood(self, starts):
        seen = [[False] * self.nx for _ in range(self.ny)]
        q = collections.deque()
        for i, j in starts:
            if self.inside(i, j) and not seen[j][i]:
                seen[j][i] = True
                q.append((i, j))
        bf, bl, rise = self.bf, self.bl, self.rise
        while q:
            i, j = q.popleft()
            g = self.ground(i, j)
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < self.nx and 0 <= b < self.ny and not seen[b][a] and not bf[b][a] and not bl[b][a] and abs(self.ground(a, b) - g) <= rise:
                    seen[b][a] = True
                    q.append((a, b))
        return seen

    def town(self, starts):
        """The walkable ground of the town: the largest part the street points flood, not all they flood. A side
        street planned up to a door in a court is a street point inside the court: flooded from it, the court shut in
        by its dressing was "reached" (the hook's first run on Walkford found nothing where the check after it found
        the door)."""
        best, n_best = None, -1
        done = [[False] * self.nx for _ in range(self.ny)]
        for st in starts:
            if done[st[1]][st[0]]:
                continue
            seen = self.flood([st])
            n = 0
            for j in range(self.ny):
                row, drow = seen[j], done[j]
                for i in range(self.nx):
                    if row[i]:
                        n += 1
                        drow[i] = True
            if n > n_best:
                best, n_best = seen, n
        return best if best is not None else [[False] * self.nx for _ in range(self.ny)]

    def way_out(self, start, seen):
        """The cheapest walk from start to walkable ground, through dressing where it must: its cells, or None."""
        bf, bl, rise = self.bf, self.bl, self.rise
        dist = {start: 0}
        back = {}
        heap = [(0, start)]
        while heap:
            d, (i, j) = heapq.heappop(heap)
            if d > dist.get((i, j), 1e18):
                continue
            if seen[j][i]:
                out = [(i, j)]
                while out[-1] in back:
                    out.append(back[out[-1]])
                return out
            g = self.ground(i, j)
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if not (0 <= a < self.nx and 0 <= b < self.ny) or bf[b][a] or abs(self.ground(a, b) - g) > rise:
                    continue
                nd = d + 1 + (LOOSE_COST if bl[b][a] else 0)
                if nd < dist.get((a, b), 1e18):
                    dist[(a, b)] = nd
                    back[(a, b)] = (i, j)
                    heapq.heappush(heap, (nd, (a, b)))
        return None


UNDER = 8.0                    # a thing whose top is this far under the land is buried


def under_land(db, cells, loose, say=None):
    """The dressing that lies under the land, taken out again: [(cell key, ref key, id)]. A plant of a Hlaalu town's
    yard stood 163 under the ground the town had since raised to its wall; the game walk by machine, 2026-11-15.
    (By the thing's own box, upright: a tilted thing is judged as if it stood.)"""
    import editing
    gone = []
    for ck in cells:
        try:
            c, _refs = editing._cell(db, ck)
        except Exception:
            continue
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            k = r.get('k')
            if k not in loose or not r.get('b') or r['type'] in ('NPC_', 'CREA', 'LEVC'):
                continue
            g = mapdata.terrain_z(db, r['p'][0], r['p'][1])
            if g is not None and r['p'][2] + r['b'][5] * (r.get('s') or 1.0) < g - UNDER:
                c['refs'].pop(k, None)
                gone.append((ck, k, r['id']))
    if gone:
        db.sync_project()
        if say:
            say('town: %d things of the dressing lay under the land and were taken out (%s)' % (len(gone), ', '.join(sorted({g_[2] for g_ in gone})[:6])))
    return gone


def open_ways(db, cells, doors, streets, loose, fix=True, say=None):
    """cells: the town's outdoor cell keys. doors: [(cell key, ref key)] of its buildings' doors. streets: [(x, y)]
    points on its streets. loose: the ref keys of its dressing (what may be taken out again).
    {'doors': checked, 'cut': [door descriptions shut in], 'opened': doors given a way, 'removed': [(cell key, ref key,
    id)], 'left': [descriptions still shut in, by more than the dressing], 'unsure': [doors on steps or a platform, not
    judged]}. With fix False nothing is taken out."""
    import doors as doors_
    import editing
    out = {'doors': 0, 'cut': [], 'opened': 0, 'removed': [], 'left': [], 'unsure': []}
    LAST.clear()
    LAST.update(out)
    refs = {}
    for ck in cells:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r.get('ri') is not None and r.get('k'):
                refs[r['k']] = (ck, r)
    # (a door's two fronts, a step out of it either way: which of them is outdoors is not asked. The guess at it
    # (doors.outside_spot) chose the inside of the shell for twelve of an Anvil port's 29 doors, and they were called
    # shut in; the inside of a shell is never walked to from a street, so the side that is, is the front)
    import doorfronts
    fronts = []
    for ck, rk in doors:
        got = refs.get(rk)
        if not got or got[1]['type'] != 'DOOR' or not got[1].get('b'):
            continue
        d = got[1]
        mx, my = doors_.middle(d)
        g = mapdata.terrain_z(db, mx, my)
        up = (d['p'][2] + d['b'][2] * (d.get('s') or 1.0) - g) if g is not None else 0.0
        if up > DOOR_HIGH:
            continue                        # (a wall-walk's door, a balcony's)
        ux, uy = doorfronts.thin_axis(d)
        # (and how far its own stair may run to the ground: a Hlaalu house's door 100 up stands at the head of a
        # stair some 300 long)
        far = int((150.0 + 2.0 * max(0.0, up)) / STEP)
        fronts.append((rk, d, [(mx + ux * FRONT, my + uy * FRONT, ux, uy, far, up), (mx - ux * FRONT, my - uy * FRONT, -ux, -uy, far, up)]))
    pts = [(c[0], c[1]) for _k, _r, cs in fronts for c in cs] + [(p[0], p[1]) for p in streets]
    if not fronts or not streets:
        return out
    pad = 480.0
    box = (min(p[0] for p in pts) - pad, min(p[1] for p in pts) - pad, max(p[0] for p in pts) + pad, max(p[1] for p in pts) + pad)
    G = Grid(db, box)
    loose = set(loose)
    for k, (ck, r) in refs.items():
        if r['type'] in ('NPC_', 'CREA', 'LEVC') or NOT_IN_WAY.search(r['id']):
            continue
        if not (box[0] - 700 < r['p'][0] < box[2] + 700 and box[1] - 700 < r['p'][1] < box[3] + 700):
            continue
        G.stand(r, k if (k in loose and r['type'] != 'DOOR' and not STAYS.search(r['id'])) else None)
    G.grow()
    seeds = [c for c in (G.free_near(*G.cell(x, y)) for x, y in streets) if c]
    seen = G.town(seeds)
    out['doors'] = len(fronts)

    def raw_walk(i, j, most, stop_loose, cap=OPEN_CELLS):
        """From (i, j) over the cells nothing itself stands in (the walls' growth does not count), most steps deep:
        (cells walked, walkable ground met)."""
        if not G.inside(i, j) or G.fixed[j][i]:
            return 0, False
        q = collections.deque([(i, j, 0)])
        got = {(i, j)}
        n = 0
        while q:
            a_, b_, d_ = q.popleft()
            n += 1
            if seen[b_][a_]:
                return n, True
            if n >= cap:
                return n, False
            if d_ >= most:
                continue
            for c_ in ((a_ + 1, b_), (a_ - 1, b_), (a_, b_ + 1), (a_, b_ - 1)):
                if c_ not in got and G.inside(c_[0], c_[1]) and not G.fixed[c_[1]][c_[0]] and not (stop_loose and G.loose.get(c_)):
                    got.add(c_)
                    q.append((c_[0], c_[1], d_ + 1))
        return n, False

    def outdoors(c):
        """Whether this front of the door is its outdoor one: open ground goes on from it, where the inside of a
        shell is shut in by its own walls. (The dressing does not shut a place in: a fenced court is outdoors.)"""
        n, met = raw_walk(*G.cell(c[0], c[1]), most=10 ** 9, stop_loose=False)
        return met or n >= OPEN_CELLS

    def side(c):
        """True: walkable ground is reached from this front; None: it stands on something built, not judged."""
        i, j = G.cell(c[0], c[1])
        if not G.inside(i, j):
            return True
        if G.bf[j][i]:
            # (on the door's own steps, a porch, a quay, a wall's stair: the grid walks the land, not what is built
            # on it. Walkable ground met within the stair's length, over cells nothing itself stands in, is its
            # foot; by the distance alone the street behind a house was "near" the inside of its door)
            n, met = raw_walk(i, j, most=c[4] * 2, stop_loose=True)
            return True if met else None
        n = G.free_near(i, j, rad=4)
        if n and seen[n[1]][n[0]]:
            return True
        # (straight on out of the door: a door set back in a porch or under an arch stands in a slot narrower than
        # the grown walls leave, and a walker goes through it all the same. The cells on the line out of the door,
        # STRAIGHT far, with nothing itself standing in them (grown walls beside them do not count))
        for m in range(1, int(STRAIGHT / STEP) + 1):
            a_, b_ = G.cell(c[0] + c[2] * m * STEP, c[1] + c[3] * m * STEP)
            if not G.inside(a_, b_) or G.fixed[b_][a_] or G.loose.get((a_, b_)):
                break
            if seen[b_][a_]:
                return True
        return False

    def reached(cands):
        # (the door's outdoor front, or fronts: a gate has two. With neither told, the door is not judged)
        outs = [c for c in cands if outdoors(c)]
        if not outs:
            return None
        got = [side(c) for c in outs]
        if True in got:
            return True
        # (a door more than a step over the land is come to by something built, its own stair or a ramp, which this
        # grid does not walk: not judged. A Hlaalu guard tower's door, 75 up at the head of the tower's stair, was
        # called shut in)
        return None if (None in got or cands[0][5] > CLIMB) else False

    for rk, door, cands in fronts:
        got = reached(cands)
        if got:
            continue
        what = '%s at %d, %d' % (door['id'], round(door['p'][0]), round(door['p'][1]))
        if got is None:
            out['unsure'].append(what)
            continue
        out['cut'].append(what)
        if not fix:
            continue
        ok = False
        for _try in range(MOST_TRIES):
            way = None
            for c in [c for c in cands if outdoors(c)]:
                start = G.free_near(*G.cell(c[0], c[1]), rad=8, loose_ok=True)
                w = G.way_out(start, seen) if start else None
                if w and (way is None or len(w) < len(way)):
                    way = w
            if not way:
                break
            keys = set()
            for i, j in way:
                if G.bl[j][i]:
                    for di, dj in DISC:
                        keys |= G.loose.get((i + di, j + dj), set())
            if not keys:
                break
            # (and what stands on them: a pot on a barrel, a sack on a crate)
            for k in list(keys):
                p = refs[k][1]['p']
                for k2, (_ck2, r2) in refs.items():
                    if k2 in loose and k2 not in keys and RIDER_UP[0] < r2['p'][2] - p[2] < RIDER_UP[1]                             and math.hypot(r2['p'][0] - p[0], r2['p'][1] - p[1]) < RIDER_NEAR:
                        keys.add(k2)
            for k in keys:
                ck, r = refs[k]
                try:
                    c, _refs = editing._cell(db, ck)
                    c['refs'].pop(k, None)
                except Exception:
                    continue
                out['removed'].append((ck, k, r['id']))
                loose.discard(k)
            for ij in list(G.loose):
                G.loose[ij] -= keys
            G.grow()
            seen = G.town(seeds)
            if reached(cands):
                ok = True
                break
        if ok:
            out['opened'] += 1
        else:
            out['left'].append(what)
    if out['removed']:
        db.sync_project()
    if say and not out['cut']:
        say('town: %d of %d doors can be walked to from the streets%s' % (out['doors'] - len(out['unsure']), out['doors'],
            (' (%d stand on steps or a platform this check cannot judge)' % len(out['unsure'])) if out['unsure'] else ''))
    if say and (out['cut'] or out['removed']):
        say('town: %d of %d doors could not be walked to from the streets; a way opened to %d (%d things of the dressing taken out)%s' % (
            len(out['cut']), out['doors'], out['opened'], len(out['removed']),
            ('; still shut in: ' + '; '.join(out['left'])) if out['left'] else ''))
    LAST.update(out)
    return out
