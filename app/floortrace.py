"""The floors, walls, doorways and rooms of any interior, read from its own geometry: the game's hand-made
places, places built from whole statics (a Nord house shell, a cave, a tomb), and places that mix those with
room pieces. Auto-furnish and the room tools work on tiles (furnish.rooms); this gives them tiles for a place
that has no piece layout, so the survey-learnt furnishing works there too.

How: the building's triangles are laid on a grid of columns G apart. A level face is a floor where a person
could stand (nothing solid from knee to head height above it: other floors, walls, sloping roofs, rock); the
standing floor reached from the doors, the walking paths and what already stands on a floor is the place's
floor (a roof's top or the void behind a wall is never reached). Columns are gathered into tiles of T, one
per storey; each side of a tile is open where the floor runs on at about the same height, else a wall, its
face measured by rays. Rooms are the parts of the floor wider than a doorway, cut at doors and door frames;
the narrow runs between them are halls, a step through a wall a doorway (left out of every room)."""
import math
import re

import mapdata
import seethrough

G = 32                    # (the column grid)
T = 128                   # (a tile: furnish.FLOOR_T)
KNEE, HEAD = 35, 150      # (standing room above a floor: nothing solid between these heights)
STEP_UP = 40              # (the most the floor rises from one column to the next and is still walked on)
LEVEL = 0.7               # (a face this flat or flatter is a floor: a cave's rough floor is not quite level)
COVER = 0.45              # (a tile needs this share of its columns standing floor)
MERGE = 40                # (level faces this close above each other are one floor: its top and its underside)
DOORISH = re.compile(r'jamb|doorway|doorf|_door_frame|doorframe|archway')
STAIRS = re.compile(r'stair|ramp|_steps')
_cache = {}


def _tris_world(db, m):
    """The building's triangles in the world: [(ax, ay, az, bx, by, bz, cx, cy, cz)] (architecture only: what
    stands in a room is furniture, doors are walked through)."""
    out = []
    for r in m['refs']:
        if not r.get('arch') or r['type'] in ('DOOR', 'LIGH') or r.get('ri') is None:
            continue
        model = db.recs[r['ri']][5]
        if not model or 'marker' in model.lower():
            continue
        tris = seethrough.model_tris(db, model)
        if not tris:
            continue
        R = seethrough._matrix(r['p'][3], r['p'][4], r['p'][5])
        (a, b, c), (d, e, f), (g, h, i) = R
        px, py, pz = r['p'][0], r['p'][1], r['p'][2]
        s = r.get('s') or 1.0
        stair = bool(STAIRS.search(r['id'].lower()))
        for t in tris:
            w = []
            for k in (0, 3, 6):
                x, y, z = t[k] * s, t[k + 1] * s, t[k + 2] * s
                w += [px + a * x + b * y + c * z, py + d * x + e * y + f * z, pz + g * x + h * y + i * z]
            out.append((w, stair))
    return out


def _raster(tris):
    """Level faces and solid spans per column: (levels {col: [z]}, solid {col: [(lo, hi)]})."""
    levels, solid = {}, {}
    for w, stair in tris:
        ax, ay, az, bx, by, bz, cx, cy, cz = w
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        area = math.sqrt(nx * nx + ny * ny + nz * nz)
        if area < 1:
            continue
        flat = abs(nz) / area
        i0, i1 = int(math.floor(min(ax, bx, cx) / G)), int(math.floor(max(ax, bx, cx) / G))
        j0, j1 = int(math.floor(min(ay, by, cy) / G)), int(math.floor(max(ay, by, cy) / G))
        if (i1 - i0 + 1) * (j1 - j0 + 1) > 60000:
            continue                                   # (a ground plane, a sky)
        d = ux * vy - uy * vx
        if flat > 0.12 and abs(d) > 1e-6:
            # a face that has a height at each column it covers: sample the column's middle and its corners
            # (a thin sliver between two samples still covers the column it crosses)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    zs = []
                    for qx, qy in (((i + 0.5) * G, (j + 0.5) * G), (i * G + 2, j * G + 2), ((i + 1) * G - 2, j * G + 2),
                                   (i * G + 2, (j + 1) * G - 2), ((i + 1) * G - 2, (j + 1) * G - 2)):
                        px_, py_ = qx - ax, qy - ay
                        l1, l2 = (px_ * vy - py_ * vx) / d, (ux * py_ - uy * px_) / d
                        if l1 < -0.02 or l2 < -0.02 or l1 + l2 > 1.02:
                            continue
                        zs.append(az + l1 * uz + l2 * vz)
                    if not zs:
                        continue
                    if flat >= LEVEL and not stair:
                        levels.setdefault((i, j), []).append(sum(zs) / len(zs))
                    if stair and flat >= LEVEL:
                        levels.setdefault((i, j), []).append(sum(zs) / len(zs))
                        continue
                    lo, hi = min(zs), max(zs)
                    solid.setdefault((i, j), []).append((lo - 2, hi + 2))
        else:
            # an upright face: solid along its foot, from its lowest to its highest point there
            pts = ((ax, ay, az), (bx, by, bz), (cx, cy, cz))
            for p, q in ((0, 1), (1, 2), (0, 2)):
                L = math.hypot(pts[q][0] - pts[p][0], pts[q][1] - pts[p][1])
                n = max(1, int(L / (G / 3)))
                for k in range(n + 1):
                    x = pts[p][0] + (pts[q][0] - pts[p][0]) * k / n
                    y = pts[p][1] + (pts[q][1] - pts[p][1]) * k / n
                    solid.setdefault((int(math.floor(x / G)), int(math.floor(y / G))), []).append(
                        (min(az, bz, cz), max(az, bz, cz)))
    return levels, solid


def _standing(levels, solid):
    """The floors a person can stand on in each column: {col: [z, ...]} (lowest first)."""
    out = {}
    for c, zs in levels.items():
        zs = sorted(zs)
        tops = []
        for z in zs:                                    # (a slab's top and underside are one floor: its top)
            if tops and z - tops[-1] < MERGE:
                tops[-1] = z
            else:
                tops.append(z)
        sp = solid.get(c, ())
        good = []
        for z in tops:
            if any(z + KNEE < z2 < z + HEAD for z2 in tops):
                continue
            if any(lo < z + HEAD and hi > z + KNEE for lo, hi in sp):
                continue
            # (indoors a floor has something over it; a roof's top or a shell's outside has the sky)
            if not any(z2 > z + HEAD for z2 in zs) and not any(hi > z + HEAD for lo, hi in sp):
                continue
            good.append(z)
        if good:
            out[c] = good
    return out


def _seeds(db, m, stand, key):
    """Columns known to be inside, with a height: in front of and behind each door, the walking paths, and
    what already stands on a floor (furniture, people)."""
    pts = []
    for r in m['refs']:
        if r['type'] == 'DOOR':
            s = r.get('s') or 1.0
            bottom = r['p'][2] + ((r.get('b') or [0, 0, 0])[2]) * s
            for dx, dy in ((80, 0), (-80, 0), (0, 80), (0, -80), (120, 0), (-120, 0), (0, 120), (0, -120)):
                pts.append((r['p'][0] + dx, r['p'][1] + dy, bottom + 20))
        elif not r.get('arch') and r.get('b') and r['type'] not in ('LIGH',):
            s = r.get('s') or 1.0
            pts.append((r['p'][0], r['p'][1], r['p'][2] + r['b'][2] * s + 10))
    try:
        import pathgrid
        for p in (pathgrid.read(db, key) or {}).get('pts', []) if key else ():
            pts.append((p[0], p[1], p[2] + 10))
    except Exception:
        pass
    out = []
    for x, y, z in pts:
        c = (int(math.floor(x / G)), int(math.floor(y / G)))
        zs = [f for f in stand.get(c, ()) if z - 80 <= f <= z + 20]
        if zs:
            out.append((c, max(zs)))
    return out


def _reach(stand, seeds):
    """The standing floor walked to from the seeds: {(col, z)}, four ways round, a step at a time."""
    seen = set()
    todo = []
    for c, z in seeds:
        if (c, z) not in seen:
            seen.add((c, z))
            todo.append((c, z))
    while todo:
        (i, j), z = todo.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c2 = (i + di, j + dj)
            for z2 in stand.get(c2, ()):
                if abs(z2 - z) <= STEP_UP and (c2, z2) not in seen:
                    seen.add((c2, z2))
                    todo.append((c2, z2))
    return seen


def trace(db, m, key=None):
    """The walkable floor of a place as tiles of T: {(x, y, level): {'pat', 'x', 'y', 'floor'}} (the shape of a
    kit-built place's tiles, each wall side's face measured), or None. Cached per place and its building."""
    key = key or m.get('key')
    sig = tuple(sorted((r['k'], r['id'].lower(), tuple(round(v, 1) for v in r['p']), r.get('s')) for r in m['refs']
                       if r.get('arch') or r['type'] == 'DOOR'))
    if key and key in _cache and _cache[key][0] == sig:
        return _cache[key][1]
    tris = _tris_world(db, m)
    if not tris:
        return None
    levels, solid = _raster(tris)
    stand = _standing(levels, solid)
    if not stand:
        return None
    seeds = _seeds(db, m, stand, key)
    floor = _reach(stand, seeds) if seeds else set()
    if len(floor) < 16:
        floor = {(c, z) for c, zs in stand.items() for z in zs}      # (no way in found: every standing floor)
    n = T // G
    # columns into tiles, one per storey a tile has
    by_tile = {}
    for (i, j), z in floor:
        by_tile.setdefault((i // n, j // n), []).append(((i, j), z))
    tiles = {}
    for (ti, tj), cols in by_tile.items():
        cols.sort(key=lambda cz: cz[1])
        groups, cur = [], [cols[0]]
        for cz in cols[1:]:
            if cz[1] - cur[-1][1] > 64:
                groups.append(cur)
                cur = [cz]
            else:
                cur.append(cz)
        groups.append(cur)
        for g in groups:
            if len(g) < n * n * COVER:
                continue
            zs = sorted(z for _c, z in g)
            fz = zs[len(zs) // 2]
            tiles[(ti, tj, round(fz / 64))] = {'cols': {c: z for c, z in g}, 'floor': fz, 'ti': ti, 'tj': tj}
    if not tiles:
        _cache[key] = (sig, None)
        return None
    floor_at = {}
    for (c, z) in floor:
        floor_at.setdefault(c, []).append(z)
    sc = None
    out = {}
    STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
    for tk, t in tiles.items():
        ti, tj, fz = t['ti'], t['tj'], t['floor']
        x, y = (ti + 0.5) * T, (tj + 0.5) * T
        pat = {'cover': {}, 'offset': {}}
        for s, (dx, dy) in STEP.items():
            # open where the floor runs on over the tile's edge at about this height
            crossings = 0
            for k in range(n):
                if dx:
                    a = (ti * n + (n - 1 if dx > 0 else 0), tj * n + k)
                else:
                    a = (ti * n + k, tj * n + (n - 1 if dy > 0 else 0))
                b = (a[0] + dx, a[1] + dy)
                za = t['cols'].get(a)
                if za is None:
                    continue
                if any(abs(zb - za) <= STEP_UP for zb in floor_at.get(b, ())):
                    crossings += 1
            nb = next((tiles[k2] for k2 in ((ti + dx, tj + dy, tk[2]), (ti + dx, tj + dy, tk[2] - 1), (ti + dx, tj + dy, tk[2] + 1))
                       if k2 in tiles and abs(tiles[k2]['floor'] - fz) < 48), None)
            pat[s] = 'open' if crossings >= 2 and nb is not None else 'wall'
            pat['cover'][s] = 0.0
            if pat[s] == 'wall':
                # the wall's face: as far as the floor reaches that way in this tile, then by rays at the
                # heights furniture stands against (the nearest of three across the side)
                reach_ = max(((c[0] - ti * n + 0.5 if dx else c[1] - tj * n + 0.5) * G - T / 2) * (dx + dy) + G / 2
                             for c in t['cols']) if t['cols'] else T / 2
                if sc is None:
                    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['type'] != 'DOOR']))
                best = None
                for lat in (-T / 4, 0, T / 4):
                    ox, oy = x + (lat if dy else 0), y + (lat if dx else 0)
                    for hz in (40, 100):
                        h = sc.nearest_any((ox, oy, fz + hz), (float(dx), float(dy), 0.0), T)
                        if h is not None and (best is None or h[0] < best):
                            best = h[0]
                off = min(reach_, best) if best is not None else reach_
                pat['offset'][s] = max(8.0, min(T / 2 + 24, off - 2))
            else:
                pat['offset'][s] = T / 2 - 4
        out[(x, y, tk[2])] = {'pat': pat, 'x': x, 'y': y, 'floor': fz}
    if key:
        _cache[key] = (sig, out)
    return out


def join(kit_tiles, kit_T, traced):
    """A place laid partly in room pieces and partly by hand, as one set of tiles of T: each piece's tile cut
    into T-sized parts that keep its walls (and where their faces are), and the traced floor the pieces
    don't cover."""
    out = {}
    n = max(1, int(round(kit_T / T)))
    STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
    for kt in kit_tiles.values():
        for a in range(n):
            for b in range(n):
                dx_, dy_ = (a + 0.5) * T - kit_T / 2, (b + 0.5) * T - kit_T / 2
                pat = {'cover': {}, 'offset': {}}
                for s, (sx, sy) in STEP.items():
                    edge = (sx > 0 and a == n - 1) or (sx < 0 and a == 0) or (sy > 0 and b == n - 1) or (sy < 0 and b == 0)
                    if edge:
                        pat[s] = kt['pat'][s]
                        pat['offset'][s] = max(8.0, kt['pat'].get('offset', {}).get(s, kit_T / 2 - 16) - (dx_ * sx + dy_ * sy))
                        pat['cover'][s] = kt['pat'].get('cover', {}).get(s, 0.0)
                    else:
                        pat[s] = 'open'
                        pat['offset'][s] = T / 2 - 4
                        pat['cover'][s] = 0.0
                x, y = kt['x'] + dx_, kt['y'] + dy_
                out[(x, y, round(kt['floor'] / 64))] = {'pat': pat, 'x': x, 'y': y, 'floor': kt['floor']}
    for k, t in traced.items():
        if any(abs(t['x'] - kt['x']) < kit_T / 2 and abs(t['y'] - kt['y']) < kit_T / 2 and abs(t['floor'] - kt['floor']) < 64
               for kt in kit_tiles.values()):
            continue
        out[k] = t
    return out


def segment(tiles, m, unit=None):
    """The tiles of a traced place cut into rooms: [[tile key, ...], ...], biggest first, and the doorway tiles
    left out of every room. A room is a part of the floor at least three tiles across (shrunk by a tile and
    grown back), cut at doors and door frames; what is narrower between them makes halls; a short narrow
    step from one room to the next (a doorway through a thick wall) is in no room."""
    unit = unit or T
    STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
    OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    # (doors and door frames standing up in a wall: a trapdoor lies in the floor and parts no rooms)
    door_pts = [(r['p'][0], r['p'][1], r['p'][2]) for r in m['refs']
                if (r['type'] == 'DOOR' or (r.get('arch') and DOORISH.search(r['id'].lower())))
                and 'trap' not in r['id'].lower() and not (r.get('b') and (r['b'][5] - r['b'][2]) * (r.get('s') or 1) < 60)]
    # (by the cell a tile's middle is in: its middle is half a tile off the grid, where round() would send a
    # tile and its neighbour to one key)
    near = {}
    for k in tiles:
        near.setdefault((math.floor(k[0] / unit), math.floor(k[1] / unit)), []).append(k)

    def nb(k, s):
        tx, ty = k[0] + STEP[s][0] * unit, k[1] + STEP[s][1] * unit
        best = None
        for k2 in near.get((math.floor(tx / unit), math.floor(ty / unit)), ()):
            if abs(k2[0] - tx) < unit / 4 and abs(k2[1] - ty) < unit / 4 and abs(tiles[k2]['floor'] - tiles[k]['floor']) < 48 \
                    and (best is None or abs(tiles[k2]['floor'] - tiles[k]['floor']) < abs(tiles[best]['floor'] - tiles[k]['floor'])):
                best = k2
        return best

    def framed(a, b):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        fz = min(tiles[a]['floor'], tiles[b]['floor'])
        return any(abs(px - mx) < unit * 0.45 and abs(py - my) < unit * 0.45 and -40 < pz - fz < 260 for px, py, pz in door_pts)
    links = {k: set() for k in tiles}
    for k in tiles:
        for s in STEP:
            if tiles[k]['pat'][s] != 'open':
                continue
            k2 = nb(k, s)
            if k2 is None or tiles[k2]['pat'][OPP[s]] != 'open' or framed(k, k2):
                continue
            links[k].add(k2)
            links[k2].add(k)

    def full(k):
        """A tile with floor all round it, the corners too (inside a part at least three tiles across)."""
        if len(links[k]) < 4:
            return False
        for s1, s2 in (('N', 'E'), ('E', 'S'), ('S', 'W'), ('W', 'N')):
            a, b = nb(k, s1), nb(k, s2)
            if a is None or b is None:
                return False
            if not (links[a] & links[b] - {k}):
                return False
        return True
    core = {k for k in tiles if full(k)}
    # the cores in pieces (linked core tiles), then each grown by the tiles linked to it
    owner = {}
    pieces = []
    for k in sorted(core):
        if k in owner:
            continue
        n = len(pieces)
        grp, todo = [], [k]
        owner[k] = n
        while todo:
            c = todo.pop()
            grp.append(c)
            for c2 in links[c]:
                if c2 in core and c2 not in owner:
                    owner[c2] = n
                    todo.append(c2)
        pieces.append(grp)
    for n, grp in enumerate(pieces):
        for c in list(grp):
            for c2 in links[c]:
                if c2 not in owner:
                    owner[c2] = n
                    grp.append(c2)
    # the rest: halls and small rooms (linked runs of tiles in no room)
    rest = [k for k in tiles if k not in owner]
    seen = set()
    for k in sorted(rest):
        if k in seen:
            continue
        grp, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            grp.append(c)
            for c2 in links[c]:
                if c2 not in owner and c2 not in seen:
                    seen.add(c2)
                    todo.append(c2)
        rooms_by = {owner[c2] for c in grp for c2 in links[c] if c2 in owner}
        if len(grp) <= 2 and len(rooms_by) >= 2:
            continue                    # (a doorway through a wall, between two rooms: in neither)
        if len(grp) <= 6 and len(rooms_by) == 1:
            pieces[rooms_by.pop()].extend(grp)       # (a nook or an alcove off one room: part of it)
            continue
        pieces.append(grp)
    pieces = [p for p in pieces if p]
    pieces.sort(key=lambda g: (-len(g), sorted(g)[0]))
    return pieces
