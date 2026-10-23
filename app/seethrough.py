"""Looking through a place the way the player does, to find the holes the room pieces leave: slits where
two walls don't quite meet, corners that let the void show, a door frame standing off the wall, a hole
in a ceiling. Rays go from inside each floor piece out through its sides and ceiling, against the real
triangles of the building's models; a ray that gets through to nothing (or, through a slit too thin to
be a way through, into the next room) marks a hole. Pieces of the style that might close a hole are
tried the same way, and the ones that do are offered."""
import math
import os
import re

import mapdata
import nif

G = 64.0                      # size of the boxes triangles are sorted into
FRONT = 1                     # which way round a face's corners go, seen from its front (as in the 3D view)
_MODEL_TRIS = {}
SKIP_TYPES = ('NPC_', 'CREA', 'LEVC', 'LEVI', 'BOOK', 'MISC', 'INGR', 'ALCH', 'APPA', 'LOCK', 'PROB', 'REPA',
              'WEAP', 'ARMO', 'CLOT', 'SNDG', 'SOUN')


def model_tris(db, model):
    """A model's triangles in its own coordinates: [(ax, ay, az, bx, by, bz, cx, cy, cz, two-sided)]
    (cached). Like the game, a face is seen from its front only, unless its model makes it two-sided."""
    if not model:
        return []
    key = model.lower().replace('\\', '/')
    if key in _MODEL_TRIS:
        return _MODEL_TRIS[key]
    tris = []
    try:
        data = db.meshes.read('meshes/' + key)
        shapes = nif.mesh_from_nif(data, max_verts=40000) if data else None
    except Exception:
        shapes = None
    for sh in shapes or ():
        p, idx = sh['p'], sh['i']
        two = bool(sh.get('double') or sh.get('alpha'))
        for k in range(0, len(idx) - 2, 3):
            a, b, c = idx[k] * 3, idx[k + 1] * 3, idx[k + 2] * 3
            tris.append((p[a], p[a + 1], p[a + 2], p[b], p[b + 1], p[b + 2], p[c], p[c + 1], p[c + 2], two))
    if len(_MODEL_TRIS) > 3000:
        _MODEL_TRIS.clear()
    _MODEL_TRIS[key] = tris
    return tris


def _matrix(rx, ry, rz):
    """The game's turn of an object (clockwise about each axis, Z then Y then X)."""
    def rot(axis, a):
        c, s = math.cos(a), math.sin(a)
        if axis == 'x':
            return [[1, 0, 0], [0, c, -s], [0, s, c]]
        if axis == 'y':
            return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
        return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

    def mul(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(mul(rot('z', -rz), rot('y', -ry)), rot('x', -rx))


class Scene:
    """Triangles of a place in the world, sorted into boxes for quick ray tests."""

    def __init__(self):
        self.tris = []
        self.two = []                # two-sided (seen from behind too)
        self.grid = {}
        self.of_ref = {}             # placed object -> (first, last + 1) of its triangles

    def add_model(self, tris, pos, scale=1.0):
        R = _matrix(pos[3], pos[4], pos[5])
        px, py, pz = pos[0], pos[1], pos[2]
        (a, b, c), (d, e, f), (g, h, i) = R
        s = scale or 1.0
        for t in tris:
            w = []
            for k in (0, 3, 6):
                x, y, z = t[k] * s, t[k + 1] * s, t[k + 2] * s
                w += [px + a * x + b * y + c * z, py + d * x + e * y + f * z, pz + g * x + h * y + i * z]
            self.add(w, t[9] if len(t) > 9 else True)

    def add(self, w, two=True):
        x0, y0, z0 = w[0], w[1], w[2]
        e1 = (w[3] - x0, w[4] - y0, w[5] - z0)
        e2 = (w[6] - x0, w[7] - y0, w[8] - z0)
        n = len(self.tris)
        self.tris.append((x0, y0, z0) + e1 + e2)
        self.two.append(two)
        lo = [int(math.floor(min(w[k], w[k + 3], w[k + 6]) / G)) for k in range(3)]
        hi = [int(math.floor(max(w[k], w[k + 3], w[k + 6]) / G)) for k in range(3)]
        if (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1) > 4000:
            return                                    # (a huge triangle: a ground plane or a sky, not a wall)
        grid = self.grid
        for ix in range(lo[0], hi[0] + 1):
            for iy in range(lo[1], hi[1] + 1):
                for iz in range(lo[2], hi[2] + 1):
                    grid.setdefault((ix, iy, iz), []).append(n)

    def _cells(self, o, d, tmax):
        """Every box the ray passes through, in order: (key, distance where it enters)."""
        cell = [int(math.floor(o[k] / G)) for k in range(3)]
        step, tnext, tdelta = [0, 0, 0], [math.inf] * 3, [math.inf] * 3
        for k in range(3):
            if d[k] > 1e-12:
                step[k] = 1
                tnext[k] = ((cell[k] + 1) * G - o[k]) / d[k]
                tdelta[k] = G / d[k]
            elif d[k] < -1e-12:
                step[k] = -1
                tnext[k] = (cell[k] * G - o[k]) / d[k]
                tdelta[k] = -G / d[k]
        t = 0.0
        while t <= tmax:
            yield (cell[0], cell[1], cell[2]), t
            k = 0 if tnext[0] <= tnext[1] and tnext[0] <= tnext[2] else 1 if tnext[1] <= tnext[2] else 2
            t = tnext[k]
            cell[k] += step[k]
            tnext[k] += tdelta[k]

    def _hits(self, o, d, tmax, seen, nearest, both=False):
        grid, tris = self.grid, self.tris
        ox, oy, oz = o
        dx, dy, dz = d
        best = None
        for key, tin in self._cells(o, d, tmax):
            if best and tin > best[0]:
                break
            for n in grid.get(key, ()):
                if n in seen:
                    continue
                seen.add(n)
                x0, y0, z0, ax, ay, az, bx, by, bz = tris[n]
                px, py, pz = dy * bz - dz * by, dz * bx - dx * bz, dx * by - dy * bx
                det = ax * px + ay * py + az * pz
                if -1e-7 < det < 1e-7:
                    continue                         # (edge on)
                if det * FRONT < 0 and not self.two[n] and not both:
                    continue                         # (its back: not drawn from behind)
                inv = 1.0 / det
                sx, sy, sz = ox - x0, oy - y0, oz - z0
                u = (sx * px + sy * py + sz * pz) * inv
                if u < -1e-4 or u > 1.0001:
                    continue
                qx, qy, qz = sy * az - sz * ay, sz * ax - sx * az, sx * ay - sy * ax
                v = (dx * qx + dy * qy + dz * qz) * inv
                if v < -1e-4 or u + v > 1.0001:
                    continue
                th = (bx * qx + by * qy + bz * qz) * inv
                if 0.5 < th < tmax:
                    if not nearest:
                        return (th, n)
                    if best is None or th < best[0]:
                        best = (th, n)
        return best

    def blocked(self, o, d, tmax, skip=None):
        """Does the ray from o along unit d hit anything before tmax? (skip: (first, last) triangles
        to leave out, of a piece about to be swapped; or a set of triangles)"""
        seen = set(skip) if isinstance(skip, (set, frozenset)) else set(range(*skip)) if skip else set()
        return self._hits(o, d, tmax, seen, False) is not None

    def nearest(self, o, d, tmax):
        """The nearest hit of a ray: (distance, triangle) or None (for pictures and checks)."""
        return self._hits(o, d, tmax, set(), True)

    def back_of(self, n, d):
        """Whether a ray along d meets triangle n from behind (a face the game doesn't draw from there)."""
        if self.two[n]:
            return False
        x0, y0, z0, ax, ay, az, bx, by, bz = self.tris[n]
        dx, dy, dz = d
        px, py, pz = dy * bz - dz * by, dz * bx - dx * bz, dx * by - dy * bx
        return (ax * px + ay * py + az * pz) * FRONT < 0

    def nearest_any(self, o, d, tmax):
        """The nearest triangle a ray meets, from the front or from behind: (distance, triangle) or None."""
        return self._hits(o, d, tmax, set(), True, both=True)

    def owner(self, n):
        """The placed object a triangle belongs to (its key), or None."""
        if not hasattr(self, '_own'):
            self._own = sorted((a, b, k) for k, (a, b) in self.of_ref.items())
        import bisect
        i = bisect.bisect_right(self._own, (n, float('inf'), '')) - 1
        if i >= 0 and self._own[i][0] <= n < self._own[i][1]:
            return self._own[i][2]
        return None


def place_scene(db, m):
    """The building of a place (its architecture and doors) as a Scene."""
    sc = Scene()
    for r in m['refs']:
        if r['type'] in SKIP_TYPES or r.get('ri') is None:
            continue
        if not (r.get('arch') or r['type'] == 'DOOR'):
            continue
        model = db.recs[r['ri']][5]
        low = (model or '').lower()
        if not low or 'marker' in low:
            continue
        first = len(sc.tris)
        sc.add_model(model_tris(db, model), r['p'], r['s'])
        sc.of_ref[r['k']] = (first, len(sc.tris))
    return sc


def overlay(db, ops):
    """The pieces some fix would add, as a Scene of their own (for trying the fix)."""
    sc = Scene()
    for op in ops:
        if op.get('op') != 'place':
            continue
        ri = next((i for i in db.by_id.get(op['id'].lower(), ()) if db.recs[i][0] in ('STAT', 'ACTI', 'DOOR')), None)
        if ri is not None:
            sc.add_model(model_tris(db, db.recs[ri][5]), op['p'], op.get('s', 1.0))
    return sc


def _ray(o, target, over):
    dx, dy, dz = target[0] - o[0], target[1] - o[1], target[2] - o[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    return (dx / L, dy / L, dz / L), L + over


def _free_column(r, tiles, walled):
    """A post or column standing out in a room: on some tile's floor, and no walled side (a wall, a
    doorway, a door frame) of any tile round it within a third of a tile of its body."""
    b, sc_ = r.get('b'), r.get('s') or 1.0
    if not b:
        return False
    th = r['p'][5]
    bx, by = (b[0] + b[3]) / 2.0 * sc_, (b[1] + b[4]) / 2.0 * sc_
    cx = r['p'][0] + bx * math.cos(th) + by * math.sin(th)
    cy = r['p'][1] - bx * math.sin(th) + by * math.cos(th)
    cz = r['p'][2] + b[2] * sc_ + 10
    near = [t for t in tiles if abs(t['x'] - cx) <= t['T'] * 0.85 and abs(t['y'] - cy) <= t['T'] * 0.85
            and t['floor'] - 32 <= cz <= t['floor'] + t['H']]
    if not any(abs(t['x'] - cx) <= t['T'] / 2 + 1 and abs(t['y'] - cy) <= t['T'] / 2 + 1 for t in near):
        return False
    for t in near:
        h = t['T'] / 2.0
        for s, (nx, ny) in (('N', (0, 1)), ('S', (0, -1)), ('E', (1, 0)), ('W', (-1, 0))):
            ax, ay = abs(ny), abs(nx)
            to_line = abs((cx - t['x']) * nx + (cy - t['y']) * ny - h)
            along = abs((cx - t['x']) * ax + (cy - t['y']) * ay)
            if to_line < t['T'] * 0.35 and along <= h + 8 and (walled is None or walled(t, s)):
                return False
    return True


def holes(db, m, tiles, neighbour, above, extra=(), walled=None, solid=(), only=None):
    """Holes in the walls and ceilings of a place: [{kind ('wall' | 'ceiling'), tile, side, void (True
    when it shows nothing), x, y, z (the middle of the hole), u0, u1 (along the side, from its
    middle), z0, z1, rays: [(origin, dir, tmax)]}], and the Scene.

    neighbour(t, side) says what carries on past a side; above(t) whether a floor stands on top;
    extra: pieces about to be added anyway ([(id, pos)]), counted as there; walled(t, side) whether a
    wall, doorway or door frame stands on a side (slits into the next room are looked for only there:
    across open floor, a narrow view past a post or a stair rail is no gap). only: look out from
    just these tiles (refs), the rest still there for following where a view goes."""
    sc = place_scene(db, m)
    for rid, pos in extra:
        ri = next((i for i in db.by_id.get(rid.lower(), ()) if db.recs[i][0] in ('STAT', 'ACTI')), None)
        if ri is not None:
            sc.add_model(model_tris(db, db.recs[ri][5]), pos, 1.0)
    # posts and columns standing free in a room: across open floor the view past one is no slit (a
    # column on the line between two tiles of one room would leave narrow "escaping" runs beside it),
    # so the rays across open sides are cast as if they weren't there
    # (only columns standing free: a post at a wall, a doorway or a join stays what it is to the scan)
    tile_refs = {t['ref'] for t in tiles}
    col_tris = set()
    for r in m['refs']:
        if r['k'] in sc.of_ref and r['k'] not in tile_refs and r['type'] == 'STAT' and re.search(r'post|pillar|column', r['id'].lower()) \
                and _free_column(r, tiles, walled):
            col_tris.update(range(*sc.of_ref[r['k']]))
    col_tris = frozenset(col_tris)
    out = []
    done_edges = set()
    # where the building is: for following a ray that gets through to where it leaves it
    T0 = tiles[0]['T'] if tiles else 256.0
    ox, oy = (tiles[0]['x'] % T0, tiles[0]['y'] % T0) if tiles else (0.0, 0.0)
    at = {}
    for t in tiles:
        at.setdefault((round((t['x'] - ox) / T0), round((t['y'] - oy) / T0)), []).append(t)

    def tile_at(p):
        for t in at.get((round((p[0] - ox) / T0), round((p[1] - oy) / T0)), ()):
            if abs(p[0] - t['x']) <= t['T'] / 2 + 1 and abs(p[1] - t['y']) <= t['T'] / 2 + 1 and \
                    t['floor'] - 8 <= p[2] <= t['floor'] + t['H'] + 8:
                return t
        return None

    def in_solid(p):
        return any(b[0] <= p[0] <= b[3] and b[1] <= p[1] <= b[4] and b[2] - 8 <= p[2] <= b[5] + 8 for b in solid)

    def leaves(o, d):
        """Where a ray leaves the building: (the tile it was last in, the side it goes out by, or 'top'
        or 'bottom', the point), or None. (Through other pieces of the building with a floor, a
        half-length hall piece say, it hasn't left: what's wrong there is theirs, not a tile's side.)"""
        last, via_solid = None, False
        for k in range(1, 300):
            p = (o[0] + d[0] * 8 * k, o[1] + d[1] * 8 * k, o[2] + d[2] * 8 * k)
            t_ = tile_at(p)
            if t_ is not None:
                last, via_solid = t_, False
                continue
            if in_solid(p):
                via_solid = True
                continue
            if last is None:
                return None
            if via_solid:
                # out by way of stairs or a hall piece that isn't a whole tile: the tile nearest where it
                # got out, and its side facing that way (where a post or a wall would go)
                near_t = min(tiles, key=lambda q: math.hypot(q['x'] - p[0], q['y'] - p[1]) + abs(q['floor'] - p[2]) * 0.5)
                if math.hypot(near_t['x'] - p[0], near_t['y'] - p[1]) > near_t['T'] * 1.2:
                    return None
                last = near_t
                dx, dy = p[0] - last['x'], p[1] - last['y']
                return last, (('E' if dx > 0 else 'W') if abs(dx) >= abs(dy) else ('N' if dy > 0 else 'S')), p
            if p[2] > last['floor'] + last['H'] + 8:
                return last, 'top', p
            if p[2] < last['floor'] - 8:
                return last, 'bottom', p
            dx, dy = p[0] - last['x'], p[1] - last['y']
            return last, (('E' if dx > 0 else 'W') if abs(dx) >= abs(dy) else ('N' if dy > 0 else 'S')), p
        return None
    far = {}             # (tile ref, side) -> [(tile, point, ray)]: rays across open floor that got out of the building
    for t in tiles:
        if only is not None and t['ref'] not in only:
            continue
        T, H = t['T'], t['H']
        h = T / 2.0
        eye = (t['x'], t['y'], t['floor'] + min(H * 0.45, 128))      # (about where a player's eyes are)
        for side, (ax, ay, nx, ny) in (('N', (1, 0, 0, 1)), ('S', (1, 0, 0, -1)), ('E', (0, 1, 1, 0)), ('W', (0, 1, -1, 0))):
            ex, ey = t['x'] + nx * h, t['y'] + ny * h
            ekey = (round(ex / 8), round(ey / 8), round(t['floor'] / 64))
            if ekey in done_edges:
                continue
            done_edges.add(ekey)
            nb = neighbour(t, side)
            # across open floor only what shows the void counts (followed on as far as it goes): a
            # narrow view past a post or a stair rail into the room is no gap
            far_only = bool(nb and walled and not walled(t, side))
            us = [-h + 4 + 4 * k for k in range(10)] + [-h + 48 + 12 * k for k in range(int((T - 96) / 12) + 1)] + \
                 [h - 4 - 4 * k for k in range(10)]
            us = sorted(set(round(u, 1) for u in us if -h < u < h))
            # (up to where the wall meets the ceiling: a wall that stops short of it leaves a band there)
            zs = [t['floor'] + 20 + 24 * k for k in range(int((H - 40) / 24) + 1)] + [t['floor'] + H - 8, t['floor'] + H + 8]
            rows = []
            # from the middle of the tile, and on big tiles also from closer to this side (standing in
            # front of a door: a sliver beside it shows from there, not from far back)
            back = min(h * 0.6, 160)
            eyes = [eye] + ([(ex - nx * back + ax * k * h * 0.4, ey - ny * back + ay * k * h * 0.4, eye[2]) for k in (-1, 0, 1)]
                            if T > 300 else [])
            for e_ in eyes:
                for z in zs:
                    row = []
                    for u in us:
                        tgt = (ex + ax * u, ey + ay * u, z)
                        d, tmax = _ray(e_, tgt, 64)
                        esc = not sc.blocked(e_, d, tmax, col_tris if far_only and col_tris else None)
                        if far_only:
                            # (it shows the void somewhere further on: the hole is where it leaves the building)
                            if esc and not sc.blocked(e_, d, 4000):
                                got = leaves(e_, d)
                                if got:
                                    far.setdefault((got[0]['ref'], got[1]), []).append((got[0], got[2], (e_, d, 4000)))
                            # (but a seam at the very end of the side, where the room's wall meets the stairs or
                            # a hall beside it, counts: see below. Only one that shows the void: a ray past a
                            # pillar standing at the corner that goes on to a wall of the next tile is a view
                            # into the room, not a slit)
                            esc = esc and abs(u) > h - 40 and not sc.blocked(e_, d, 4000)
                        row.append((u, esc, (e_, d, tmax)))
                    rows.append((z, row))
            # what counts: anything getting through to nothing; into the next room, only slits (a run of
            # rays narrower than a way through)
            hits = []
            for z, row in rows:
                run = []
                for k, (u, esc, ray) in enumerate(row + [(None, False, None)]):
                    if esc:
                        run.append((u, ray))
                        continue
                    if run:
                        width = run[-1][0] - run[0][0]
                        if not nb or width <= (24 if far_only else 40):
                            hits += [(u_, z, r_) for u_, r_ in run]
                        run = []
            if len(hits) < (2 if not nb else 3):
                continue
            # group into holes along the side
            hits.sort(key=lambda x: x[0])
            groups = [[hits[0]]]
            for hh in hits[1:]:
                if hh[0] - groups[-1][-1][0] > 24:
                    groups.append([hh])
                else:
                    groups[-1].append(hh)
            for g in groups:
                zs_g = {x[1] for x in g}
                if len(zs_g) < (5 if far_only else 3) or len(g) < 4:
                    continue                    # (a slit shows over some height: a pinprick is a crack in a model;
                                                # a seam at the end of an open side, over most of it)
                u0, u1 = min(x[0] for x in g), max(x[0] for x in g)
                z0, z1 = min(zs_g), max(zs_g)
                uc = (u0 + u1) / 2
                out.append({'kind': 'wall', 'tile': t, 'side': side, 'void': not nb or far_only, 'inside': far_only,
                            'nb': nb if isinstance(nb, dict) else None,
                            'u0': u0, 'u1': u1, 'z0': z0, 'z1': z1,
                            'x': ex + ax * uc, 'y': ey + ay * uc, 'z': (z0 + z1) / 2, 'edge': (ex, ey, ax, ay),
                            'rays': [x[2] for x in g]})
        # the floor, where nothing is built underneath (no stairwell down)
        if not any(o is not t and abs(o['x'] - t['x']) < T * 0.6 and abs(o['y'] - t['y']) < T * 0.6 and
                   64 < t['floor'] - o['floor'] < H * 1.6 for o in tiles):
            rays = []
            for i in range(-3, 4):
                for j in range(-3, 4):
                    tgt = (t['x'] + i * h / 3.6, t['y'] + j * h / 3.6, t['floor'])
                    d, tmax = _ray(eye, tgt, 64)
                    if not sc.blocked(eye, d, tmax):
                        rays.append((eye, d, tmax))
            if len(rays) >= 6:
                out.append({'kind': 'floor', 'tile': t, 'side': None, 'void': True, 'x': t['x'], 'y': t['y'],
                            'z': t['floor'] + 10, 'rays': rays, 'n': len(rays)})
        # the ceiling, where no floor stands on top
        if above(t):
            continue
        top = t['floor'] + H
        rays = []
        for i in range(-3, 4):
            for j in range(-3, 4):
                tgt = (t['x'] + i * h / 3.6, t['y'] + j * h / 3.6, top)
                d, tmax = _ray(eye, tgt, 96)
                if not sc.blocked(eye, d, tmax):
                    rays.append((eye, d, tmax))
        if len(rays) >= 6:
            out.append({'kind': 'ceiling', 'tile': t, 'side': None, 'void': True, 'x': t['x'], 'y': t['y'], 'z': top - 20,
                        'rays': rays, 'n': len(rays)})
    # looking all round from the middle of each tile, as someone standing there would: what reaches
    # the void through gaps no side of that tile has (seen through a doorway, past the stairs...)
    for t in tiles:
        if only is not None and t['ref'] not in only:
            continue
        eye = (t['x'], t['y'], t['floor'] + min(t['H'] * 0.45, 128))
        for a in range(0, 360, 10):
            for e in (-30, -15, 0, 15, 30, 45, 60, 75):
                th, ph = math.radians(a), math.radians(e)
                d = (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph))
                if sc.blocked(eye, d, 4000):
                    continue
                got = leaves(eye, d)
                if got:
                    far.setdefault((got[0]['ref'], got[1]), []).append((got[0], got[2], (eye, d, 4000), 'round'))
    # what got out of the building from across open floor: a hole where it left
    for (_ref, side), got in far.items():
        from_round = sum(1 for g in got if len(g) > 3)
        if len(got) < 4 and from_round < 2:
            continue
        t = got[0][0]
        rays = [g[2] for g in got]
        if os.environ.get('SEETHROUGH_DEBUG'):
            print('far', t['id'], side, [(round(g[1][0]), round(g[1][1]), round(g[1][2])) for g in got][:10],
                  'from', [round(v) for v in got[0][2][0]])
        if side in ('top', 'bottom'):
            out.append({'kind': 'ceiling' if side == 'top' else 'floor', 'tile': t, 'side': None, 'void': True,
                        'x': t['x'], 'y': t['y'], 'z': t['floor'] + (t['H'] - 20 if side == 'top' else 10), 'rays': rays, 'n': len(rays)})
            continue
        if len({round(g[1][2] / 24) for g in got}) < 2 and from_round < 2:
            continue                                # (a pinprick)
        h = t['T'] / 2.0
        nx, ny = {'N': (0, 1), 'S': (0, -1), 'E': (1, 0), 'W': (-1, 0)}[side]
        ax, ay = abs(ny), abs(nx)
        ex, ey = t['x'] + nx * h, t['y'] + ny * h
        us = [max(-h, min(h, (g[1][0] - ex) * ax + (g[1][1] - ey) * ay)) for g in got]
        zs_g = [g[1][2] for g in got]
        u0, u1 = min(us), max(us)
        uc = (u0 + u1) / 2
        nb = neighbour(t, side)
        out.append({'kind': 'wall', 'tile': t, 'side': side, 'void': True, 'inside': False,
                    'nb': nb if isinstance(nb, dict) else None, 'u0': u0, 'u1': u1, 'z0': min(zs_g), 'z1': max(zs_g),
                    'x': ex + ax * uc, 'y': ey + ay * uc, 'z': (min(zs_g) + max(zs_g)) / 2, 'edge': (ex, ey, ax, ay),
                    'rays': rays})
    return out, sc


def backs(db, sc, tiles, walled, share=0.35):
    """Walls seen from behind (2026-10-23): a side of a tile that is meant to be walled, where what the
    player looks at from the tile is the back of a one-sided wall, which the game doesn't draw, so the view
    goes on into the room beyond (the user's Gold Coast "Big Ass Fail": "I can't ever find the right wall
    piece to cover these up from the back"). The game stands its one-sided walls back to back, a face for
    each room. [{tile, side, owner (the key of the piece whose back shows), x, y, z, share}] where at least
    `share` of the rays to the side meet a back face near the side's line and go on past it."""
    out = []
    done = set()
    for t in tiles:
        T, H = t['T'], t['H']
        h = T / 2.0
        eye = (t['x'], t['y'], t['floor'] + min(H * 0.45, 128))
        for side, (ax, ay, nx, ny) in (('N', (1, 0, 0, 1)), ('S', (1, 0, 0, -1)), ('E', (0, 1, 1, 0)), ('W', (0, 1, -1, 0))):
            # (every side: a loose wall stood by hand on a side the tile leaves open shows its back too)
            ex, ey = t['x'] + nx * h, t['y'] + ny * h
            key = (round(ex / 8), round(ey / 8), round(t['floor'] / 64), side)
            if key in done:
                continue
            done.add(key)
            us = [-h + 32 + k * (T - 64) / 6.0 for k in range(7)]
            zs = [t['floor'] + 40 + k * (H - 80) / 4.0 for k in range(5)]
            n_all, owners = 0, {}
            for u in us:
                for z in zs:
                    d, tmax = _ray(eye, (ex + ax * u, ey + ay * u, z), 48)
                    n_all += 1
                    got = sc.nearest_any(eye, d, tmax)
                    if got is None or not sc.back_of(got[1], d):
                        continue
                    # (the back face stands at the side's line, not somewhere across the tile or beyond)
                    if got[0] < tmax - 48 - 40:
                        continue
                    front = sc.nearest(eye, d, tmax + 400)
                    if front is not None and front[0] <= got[0] + 4:
                        continue                 # (something drawn from here covers it after all)
                    k = sc.owner(got[1])
                    if k is not None:
                        owners[k] = owners.get(k, 0) + 1
            if not owners or sum(owners.values()) < share * n_all:
                continue
            k = max(owners, key=owners.get)
            out.append({'tile': t, 'side': side, 'owner': k, 'x': ex, 'y': ey, 'z': t['floor'] + H / 2.0,
                        'share': round(sum(owners.values()) / float(n_all), 2)})
    return out


_side_open = {}


def side_open(db, ri, side, z0, z1, T):
    """How much of one side of a piece is open between heights z0 and z1 (in the piece's own frame,
    0..1): rays from inside the piece's tile, across its middle, out through that side. A Common tall
    stairwell's low end is open below (the way in) and walled above; its sides are walled where the
    measure says so."""
    key = (ri, side, round(z0), round(z1), round(T))
    if key in _side_open and _side_open[key][0] is db.recs:
        return _side_open[key][1]
    tris = model_tris(db, db.recs[ri][5])
    if not tris:
        return 1.0
    sc = Scene()
    sc.add_model(tris, (0, 0, 0, 0, 0, 0))
    nx, ny = {'N': (0, 1), 'S': (0, -1), 'E': (1, 0), 'W': (-1, 0)}[side]
    ax, ay = abs(ny), abs(nx)
    free = total = 0
    for k in range(-4, 5):
        u = k * T * 0.1
        for j in range(8):
            z = z0 + (z1 - z0) * (j + 0.5) / 8.0
            o = (ax * u, ay * u, z)
            total += 1
            if not sc.blocked(o, (float(nx), float(ny), 0.0), T):
                free += 1
    res = free / float(total)
    _side_open[key] = (db.recs, res)
    return res


def facing(db, ri, inward, default):
    """The turn (of the four) that shows the most of a wall piece to someone looking at it from the
    side inward points to (from the room): many are seen from one side only, and some are open or
    arched on their other side."""
    b = mapdata.object_bounds(db, ri)
    tris = model_tris(db, db.recs[ri][5]) if b else []
    if not tris:
        return default
    best = None
    span = max(b[3] - b[0], b[4] - b[1])
    for q in range(4):
        th = q * math.pi / 2
        sc = Scene()
        sc.add_model(tris, (0, 0, 0, 0, 0, th))
        # its middle once turned (the game turns clockwise)
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        mx, my = cx * math.cos(th) + cy * math.sin(th), -cx * math.sin(th) + cy * math.cos(th)
        ax, ay = -inward[1], inward[0]
        seen = 0
        for i in range(-4, 5):
            for j in range(1, 10):
                o = (mx + inward[0] * 400 + ax * i * span / 9, my + inward[1] * 400 + ay * i * span / 9, b[2] + (b[5] - b[2]) * j / 10)
                if sc.blocked(o, (-inward[0], -inward[1], 0.0), 800):
                    seen += 1
        if best is None or seen > best[0] or (seen == best[0] and abs(th - default) < 1e-6):
            best = (seen, th)
    return best[1] if best and best[0] else default


_cover = {}


def wall_cover(db, ri, height):
    """How much of a storey-high side a wall piece covers, seen from its best side (0..1): a wall
    with an arched or carved top leaves the void showing above it."""
    key = (ri, round(height))
    if key in _cover and _cover[key][0] is db.recs:
        return _cover[key][1]
    b = mapdata.object_bounds(db, ri)
    tris = model_tris(db, db.recs[ri][5]) if b else []
    best = 0.0
    if tris:
        sc = Scene()
        sc.add_model(tris, (0, 0, 0, 0, 0, 0))
        along_x = (b[3] - b[0]) >= (b[4] - b[1])
        span = max(b[3] - b[0], b[4] - b[1])
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        for sgn in (1, -1):
            inward = (0, sgn) if along_x else (sgn, 0)
            ax, ay = -inward[1], inward[0]
            seen = 0
            for i in range(-4, 5):
                for j in range(1, 10):
                    o = (cx + inward[0] * 400 + ax * i * span / 10, cy + inward[1] * 400 + ay * i * span / 10, b[2] + height * j / 10)
                    seen += sc.blocked(o, (-inward[0], -inward[1], 0.0), 800)
            best = max(best, seen / 81.0)
    _cover[key] = (db.recs, best)
    return best


def closes(db, sc, hole, ops, swap=None):
    """How many of a hole's rays a fix stops (0..1). swap: (ref, id, pos) of a piece swapped for
    another: the old one's triangles leave, the new one's come."""
    ov = overlay(db, ops + ([{'op': 'place', 'id': swap[1], 'p': swap[2], 's': swap[3] if len(swap) > 3 else 1.0}] if swap else []))
    if not ov.tris:
        return 0.0
    skip = sc.of_ref.get(swap[0]) if swap else None
    n = sum(1 for o, d, tmax in hole['rays'] if ov.blocked(o, d, tmax) or (skip and sc.blocked(o, d, tmax, skip)))
    return n / float(len(hole['rays']))
