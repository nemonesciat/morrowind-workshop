"""Walking room in a place: the ways a person walks between its doors and the feet and heads of its stairs, over the
floor tiles the room trace finds, and what stands in them.

The user, 2026-11-08: "tables in the way of walking space". The furnisher keeps a square clear round each door and each
stair's landing, but nothing kept the way between them: a table set mid-room stood across the line from the front door
to the stair. walk_lines() gives those ways on the bare floor (before anything is laid), for the furnisher to keep clear;
measure() scores a furnished place: how many of the ways are cut or made to wander, how much of the floor can't be
reached from the door, and which pieces stand in the bare floor's way.

The floor is the room trace's tiles (furnish.rooms), cut into cells GRID wide. A person crosses from one tile to the
next where neither tile's side between them is a wall and the floors are a step apart at most. A piece of furniture
blocks the cells within BODY of its footprint; rugs, mats and things up on tables or walls block nothing."""
import heapq
import math
import re

GRID = 32.0             # (the walking grid's cell)
BODY = 22.0             # (a person's half width: a cell this near a piece of furniture can't be stood in)
STEP = 48.0             # (the most a floor may rise from one tile to the next and still be walked)
WALL_NEAR = 40.0        # (cells this near a wall cost a little more, so the ways run through the room, not along its walls)
JOINS_MAX = 8           # (the most room-to-room openings a place's ways are laid through)
WAY = 36.0              # (half the width the furnisher keeps clear along a way: a way 72 wide plus the cell)
FLAT = re.compile(r'tapestr|banner|painting|sconce|rug|carpet|_mat_|mat_|doormat|pelt|bearskin|wolfskin|_skin_rug|cushion_floor|straw|hay_pile', re.I)
STAIR = re.compile(r'stair|steps|ramp|ladder', re.I)
SIDES = {'N': (0, 1), 'S': (0, -1), 'E': (1, 0), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}


def _fp(r):
    b = r['b']
    s = r.get('s') or 1.0
    rot = r['p'][5]
    c, sn = math.cos(rot), math.sin(rot)
    pts = [(r['p'][0] + px * s * c + py * s * sn, r['p'][1] - px * s * sn + py * s * c)
           for px, py in ((b[0], b[1]), (b[3], b[1]), (b[0], b[4]), (b[3], b[4]))]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts),
            r['p'][2] + b[2] * s, r['p'][2] + b[5] * s)


class Floor:
    """The walking grid over a place's room tiles."""

    def __init__(self, info):
        T = float(info.get('tile') or 256.0)
        self.T = T
        n = max(1, int(round(T / GRID)))
        self.n = n
        self.g = T / n
        self.tiles = {}             # (ix, iy, level) -> tile
        self.cells = {}             # node -> (x, y, z)
        self.wallish = set()
        self.room_of = {}
        levels = []
        for rm in info.get('rooms') or ():
            for t in rm.get('_tiles') or ():
                z = t.get('floor')
                if z is None:
                    z = rm.get('floor') or 0.0
                lv = next((l for l in levels if abs(l - z) <= STEP), None)
                if lv is None:
                    levels.append(z)
                    lv = z
                key = (int(round(t['x'] / T)), int(round(t['y'] / T)), levels.index(lv))
                if key in self.tiles:
                    continue
                self.tiles[key] = (t, z, rm.get('name'))
        self.levels = levels
        for key, (t, z, rn) in self.tiles.items():
            pat = t.get('pat') or {}
            x0, y0 = t['x'] - T / 2, t['y'] - T / 2
            for i in range(n):
                for j in range(n):
                    node = (key, i, j)
                    cx, cy = x0 + (i + 0.5) * self.g, y0 + (j + 0.5) * self.g
                    self.cells[node] = (cx, cy, z)
                    self.room_of[node] = rn
                    for sd, (dx, dy) in SIDES.items():
                        if pat.get(sd) == 'wall' and self._edge_dist(i, j, dx, dy) < WALL_NEAR:
                            self.wallish.add(node)

    def _edge_dist(self, i, j, dx, dy):
        n, g = self.n, self.g
        if dx == 1:
            return (n - i - 0.5) * g
        if dx == -1:
            return (i + 0.5) * g
        if dy == 1:
            return (n - j - 0.5) * g
        return (j + 0.5) * g

    def _side_open(self, key, sd):
        t = self.tiles.get(key)
        return t is not None and (t[0].get('pat') or {}).get(sd) != 'wall'

    def neighbours(self, node):
        key, i, j = node
        n = self.n
        out = []
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ni, nj = i + di, j + dj
            nk = key
            ok = True
            sides = []
            if ni >= n or ni < 0:
                sd = 'E' if ni >= n else 'W'
                sides.append(sd)
                ni %= n
            if nj >= n or nj < 0:
                sd = 'N' if nj >= n else 'S'
                sides.append(sd)
                nj %= n
            if sides:
                if len(sides) == 2:
                    continue                        # (never cut a tile's corner)
                sd = sides[0]
                dx, dy = SIDES[sd]
                nk = None
                for lv in range(len(self.levels)):
                    k2 = (key[0] + dx, key[1] + dy, lv)
                    if k2 in self.tiles and abs(self.tiles[k2][1] - self.tiles[key][1]) <= STEP:
                        nk = k2
                        break
                if nk is None or not self._side_open(key, sd) or not self._side_open(nk, OPP[sd]):
                    ok = False
            if ok:
                out.append(((nk, ni, nj), 1.4142 if di and dj else 1.0))
        return out

    def near(self, x, y, z, reach, zreach=70.0):
        """The cells within reach of a point, on a floor within zreach below or above it."""
        return [nd for nd, (cx, cy, cz) in self.cells.items()
                if abs(cx - x) <= reach and abs(cy - y) <= reach and -zreach <= z - cz <= zreach + 40]

    def path(self, starts, goals, blocked=frozenset()):
        """The cheapest way from any start cell to any goal cell, as a list of cells, or None."""
        goals = set(goals) - blocked
        if not goals:
            return None
        dist = {}
        prev = {}
        hq = []
        for s in starts:
            if s in blocked:
                continue
            dist[s] = 0.0
            heapq.heappush(hq, (0.0, s))
        while hq:
            d, u = heapq.heappop(hq)
            if d > dist.get(u, 1e18):
                continue
            if u in goals:
                out = [u]
                while out[-1] in prev:
                    out.append(prev[out[-1]])
                return out[::-1]
            for v, w in self.neighbours(u):
                if v in blocked:
                    continue
                nd = d + w * (1.6 if v in self.wallish else 1.0)
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(hq, (nd, v))
        return None

    def reach(self, starts, blocked=frozenset()):
        seen = set(s for s in starts if s not in blocked)
        todo = list(seen)
        while todo:
            u = todo.pop()
            for v, _w in self.neighbours(u):
                if v not in seen and v not in blocked:
                    seen.add(v)
                    todo.append(v)
        return seen

    def length(self, p):
        return sum(math.hypot(self.cells[a][0] - self.cells[b][0], self.cells[a][1] - self.cells[b][1]) for a, b in zip(p, p[1:]))


def openings(fl, refs):
    """Where people come into each floor: [(name, cells)] for each door (the cells by its point) and for the foot and
    the head of each stair (the floor cells along its footprint's edge at its bottom and its top)."""
    out = []
    n_st = 0
    for r in refs:
        if not r.get('b'):
            continue
        low = r['id'].lower()
        if r['type'] == 'DOOR':
            if 'trap' in low:
                continue
            cs = fl.near(r['p'][0], r['p'][1], r['p'][2], 96)
            if cs:
                c0 = min(cs, key=lambda nd: math.hypot(fl.cells[nd][0] - r['p'][0], fl.cells[nd][1] - r['p'][1]))
                out.append(('door ' + r['id'], [nd for nd in cs if math.hypot(fl.cells[nd][0] - fl.cells[c0][0], fl.cells[nd][1] - fl.cells[c0][1]) <= 48]))
        elif r['type'] in ('STAT', 'ACTI') and STAIR.search(low) and r.get('arch', True):
            f = _fp(r)
            if f[5] - f[4] < 100:
                continue
            # (the head is the floor the flight climbs to: the next floor over its foot under the top of its box; the
            # box's top is its rail's, not the floor's, and a flight climbs one storey)
            ups = [lv for lv in fl.levels if f[4] + 120 <= lv <= f[5] + 20]
            ends = [('foot', f[4])] + ([('head', min(ups))] if ups else [])
            for end, z in ends:
                cs = [nd for nd, (cx, cy, cz) in fl.cells.items()
                      if abs(cz - z) <= 60 and f[0] - 56 <= cx <= f[2] + 56 and f[1] - 56 <= cy <= f[3] + 56
                      and not (f[0] + 4 < cx < f[2] - 4 and f[1] + 4 < cy < f[3] - 4)]
                if cs:
                    out.append(('stair %s %s#%d' % (end, r['id'], n_st), cs))
            n_st += 1
    # and where one room opens into the next: the cells on both sides of a tile edge between two rooms' tiles that
    # neither side walls, one opening for each pair of rooms (a table set before the arch from the kitchen to the
    # hall stands in the way as much as one before a door)
    joins = {}
    size = {}
    for key, (t, z, rn) in fl.tiles.items():
        size[rn] = size.get(rn, 0) + 1
    for key, (t, z, rn) in fl.tiles.items():
        if size.get(rn, 0) < 2:
            continue                                # (a trace's one-tile scrap of floor is no room of its own)
        for sd, (dx, dy) in SIDES.items():
            for lv in range(len(fl.levels)):
                k2 = (key[0] + dx, key[1] + dy, lv)
                o = fl.tiles.get(k2)
                if o is None or o[2] == rn or abs(o[1] - z) > STEP or size.get(o[2], 0) < 2:
                    continue
                if not fl._side_open(key, sd) or not fl._side_open(k2, OPP[sd]):
                    continue
                pair = tuple(sorted((str(rn), str(o[2]))))
                n = fl.n
                for i in range(n):
                    for j in range(n):
                        if (dx == 1 and i == n - 1) or (dx == -1 and i == 0) or (dy == 1 and j == n - 1) or (dy == -1 and j == 0):
                            joins.setdefault(pair, []).append((key, i, j))
    for pair, cs in sorted(joins.items(), key=lambda kv: -len(kv[1]))[:JOINS_MAX]:
        out.append(('join %s|%s' % pair, cs))
    return out


def stair_cells(fl, refs):
    """The cells under a stair's run (its footprint, on the floor at its foot): no way crosses a stair sideways."""
    out = set()
    for r in refs:
        if r.get('b') and r['type'] in ('STAT', 'ACTI') and STAIR.search(r['id'].lower()):
            f = _fp(r)
            if f[5] - f[4] < 100:
                continue
            for nd, (cx, cy, cz) in fl.cells.items():
                if f[0] + 8 < cx < f[2] - 8 and f[1] + 8 < cy < f[3] - 8 and f[4] - 60 <= cz <= f[5] - 60:
                    out.add(nd)
    return out


def walk_lines(info, refs):
    """The ways on the bare floor between every two openings on one floor: [(a, b, [(x, y, z) ...])]."""
    fl = Floor(info)
    if not fl.cells:
        return []
    ops = openings(fl, refs)
    under = stair_cells(fl, refs)
    out = []
    for i in range(len(ops)):
        for j in range(i + 1, len(ops)):
            a, b = ops[i], ops[j]
            if a[0].split(' ', 2)[-1] == b[0].split(' ', 2)[-1] and a[0].startswith('stair'):
                continue                            # (a stair's own foot and head)
            p = fl.path(a[1], b[1], frozenset(under))
            if p:
                out.append((a[0], b[0], [fl.cells[nd] for nd in p]))
    return out


def clearings(info, refs):
    """Boxes (x0, y0, x1, y1, z) along every way, WAY each side: the floor the furnisher keeps clear."""
    out = []
    for _a, _b, pts in walk_lines(info, refs):
        for x, y, z in pts:
            out.append((x - WAY, y - WAY, x + WAY, y + WAY, z))
    return out


def blockers(fl, refs, arch=None):
    """What stands on the floor: [(ref, footprint)] for every piece of furniture that a person can't walk through."""
    out = []
    for r in refs:
        if not r.get('b') or r['type'] not in ('STAT', 'CONT', 'ACTI', 'LIGH', 'NPC_'):
            continue
        if r['type'] == 'NPC_':
            continue
        if (arch(r) if arch else r.get('arch')):
            continue
        if FLAT.search(r['id']) or STAIR.search(r['id']):
            continue
        f = _fp(r)
        if f[5] - f[4] < 18 or (f[2] - f[0]) * (f[3] - f[1]) < 16 * 16:
            continue
        out.append((r, f))
    return out


def measure(info, refs, arch=None):
    """A furnished place's walking room: {'ways', 'cut', 'wander', 'reach', 'in_way': [ids], 'pieces'}.
    ways: the openings' pairs that join on the bare floor; cut: those no way joins once furnished; wander: those
    whose way is half as long again and more; reach: the share of the bare floor (not under furniture) the front
    door reaches; in_way: the pieces standing on the bare floor's ways."""
    fl = Floor(info)
    if not fl.cells:
        return None
    ops = openings(fl, refs)
    under = frozenset(stair_cells(fl, refs))
    bl = blockers(fl, refs, arch)
    blocked = set()
    owner = {}
    for r, f in bl:
        for nd, (cx, cy, cz) in fl.cells.items():
            if cz - 40 <= f[4] <= cz + 30 and f[0] - BODY < cx < f[2] + BODY and f[1] - BODY < cy < f[3] + BODY:
                blocked.add(nd)
                owner.setdefault(nd, set()).add(r['id'])
    blocked_all = frozenset(blocked | under)
    ways = cut = wander = 0
    in_way = []
    for i in range(len(ops)):
        for j in range(i + 1, len(ops)):
            a, b = ops[i], ops[j]
            if a[0].split(' ', 2)[-1] == b[0].split(' ', 2)[-1] and a[0].startswith('stair'):
                continue
            p0 = fl.path(a[1], b[1], under)
            if not p0:
                continue
            ways += 1
            p1 = fl.path(a[1], b[1], blocked_all)
            if p1 is None:
                cut += 1
            elif fl.length(p1) > 1.5 * fl.length(p0) + 64:
                wander += 1
            hit = set()
            for nd in p0:
                hit |= owner.get(nd, set())
            in_way.extend(sorted(hit))
    doors = [o for o in ops if o[0].startswith('door')]
    reach = None
    if doors:
        bare = fl.reach(doors[0][1], under)
        free = [nd for nd in bare if nd not in blocked]
        got = fl.reach(doors[0][1], blocked_all)
        reach = len([nd for nd in free if nd in got]) / float(len(free) or 1)
    return {'ways': ways, 'cut': cut, 'wander': wander, 'reach': reach, 'in_way': in_way, 'pieces': len(bl),
            'cells': len(fl.cells)}
