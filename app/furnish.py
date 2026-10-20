"""Auto-furnish: fill the rooms of an interior with fitting furniture and clutter.

Rooms are found from the place's floor pieces (the same kit measurements the builder uses).
What goes in them comes from similar places in your load order, so a Hlaalu house gets Hlaalu
furniture. Which way each piece of furniture faces is learnt from where it stands in real
interiors (it faces into the room), so beds and shelves end up with their backs to the wall."""
import math
import random
import re
import struct

import editing
import kits
import mapdata
from editing import EditError
from esm import zstr
from project import ref_info, set_ref_pos, split_cell, zs

STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

# what a kind of furniture is called, by words in its ID or name (and the record types it can be)
FAMILIES = {
    'bed': (('bed',), ('STAT', 'ACTI')),
    'table': (('table',), ('STAT', 'ACTI')),
    'chair': (('chair', 'stool'), ('STAT', 'ACTI')),
    'bench': (('bench',), ('STAT', 'ACTI')),
    'bookshelf': (('bookshelf', 'bookcase'), ('STAT', 'ACTI', 'CONT')),
    'shelf': (('shelf',), ('STAT', 'ACTI', 'CONT')),
    'cupboard': (('cupboard', 'closet', 'dresser', 'wardrobe', 'armoire', 'drawers'), ('CONT', 'STAT')),
    'chest': (('chest',), ('CONT',)),
    'crate': (('crate',), ('CONT', 'STAT')),
    'barrel': (('barrel',), ('CONT', 'STAT')),
    'sack': (('sack',), ('CONT', 'STAT')),
    'urn': (('urn', '_pot'), ('CONT', 'STAT')),
    'rug': (('rug', 'carpet'), ('STAT',)),
    'counter': (('counter', 'bar'), ('STAT', 'ACTI')),      # (the game's counters are its "bar" pieces)
    'shrine': (('shrine', 'altar'), ('ACTI', 'STAT')),
    'dish': (('plate', 'bowl', 'cup', 'goblet', 'mug', 'pitcher', 'tankard', 'flask', 'jug'), ('MISC',)),
    'bottle': (('bottle',), ('MISC', 'ALCH')),
    'book': (('',), ('BOOK',)),
    'food': (('',), ('INGR',)),
    'candle': (('candle',), ('LIGH',)),
    'bedroll': (('bedroll', 'bedding', 'hammock'), ('STAT', 'ACTI')),
    'fire': (('firepit', 'fire_pit', 'campfire', 'fireplace_ashl', 'cookingfire'), ('STAT', 'ACTI', 'LIGH')),
}
NOT = {'table': ('tablet',), 'bed': ('bedroll',), 'shelf': ('bookshelf', 'bookcase'), 'chest': ('chestnut',),
       'counter': ('door', 'barrel')}
HANGING_KINDS = ('shelf',)      # the only furniture put up on a wall (at the height the game hangs it)
DRESSED_KINDS = ('bookshelf', 'shelf', 'table', 'counter')     # set out the way the game dresses the model (shelfsurvey.py)
CONTAINER_KINDS = ('chest', 'crate', 'barrel', 'sack', 'urn', 'cupboard')   # the game's own filled ones, by room (containersurvey.py)
last_placed = []                # what the last Auto-furnish put where (for tests)
last_clutter = []               # how the clutter groups went (for tests)

# what goes in a kind of room: (kind of thing, how many, where). Rugs go where the game puts them: under
# the table, beside the bed, in front of a shrine or counter (where people stand); a long one down a hall;
# a small mat inside the front door (see furnish())
RECIPES = {
    'bedroom': [('bed', 1, 'wall'), ('rug', 1, 'by_bed'), ('chest', 1, 'wall'), ('cupboard', 1, 'wall'),
                ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('candle', 1, 'on_table'), ('book', 1, 'on_table'),
                ('dish', 1, 'on_table')],
    'living': [('table', 1, 'centre'), ('rug', 1, 'under_table'), ('chair', 3, 'by_table'), ('bench', 1, 'wall'),
               ('shelf', 1, 'wall'), ('cupboard', 1, 'wall'), ('urn', 1, 'corner'), ('dish', 3, 'on_table'),
               ('bottle', 2, 'on_table'), ('food', 2, 'on_table')],
    'kitchen': [('table', 1, 'centre'), ('chair', 2, 'by_table'), ('barrel', 2, 'corner'), ('sack', 2, 'wall'),
                ('crate', 1, 'wall'), ('shelf', 1, 'wall'), ('food', 4, 'on_table'), ('dish', 3, 'on_table')],
    'storage': [('crate', 3, 'wall'), ('barrel', 3, 'corner'), ('sack', 3, 'wall'), ('chest', 1, 'wall'),
                ('urn', 2, 'corner')],
    'study': [('bookshelf', 2, 'wall'), ('table', 1, 'centre'), ('rug', 1, 'under_table'), ('chair', 1, 'by_table'),
              ('book', 3, 'on_table'), ('candle', 1, 'on_table'), ('cupboard', 1, 'wall')],
    'shop': [('counter', 1, 'centre'), ('rug', 1, 'before'), ('shelf', 2, 'wall'), ('chest', 1, 'wall'), ('crate', 2, 'wall'),
             ('barrel', 1, 'corner'), ('bottle', 2, 'on_table'), ('dish', 2, 'on_table')],
    'shrine': [('shrine', 1, 'wall'), ('rug', 1, 'before'), ('bench', 2, 'wall'), ('urn', 2, 'corner'),
               ('candle', 2, 'on_table')],
    'hall': [('rug', 1, 'runner'), ('bench', 1, 'wall'), ('urn', 2, 'corner')],
    # caves, mines and camps: people sleep rough here; ruins: what's left lying about
    'camp': [('bedroll', 2, 'wall'), ('fire', 1, 'centre'), ('crate', 2, 'wall'), ('barrel', 2, 'corner'), ('sack', 2, 'wall'),
             ('chest', 1, 'wall'), ('urn', 1, 'corner')],
    'ruin': [('crate', 2, 'wall'), ('barrel', 2, 'corner'), ('urn', 2, 'corner'), ('chest', 1, 'wall'), ('sack', 1, 'wall')],
    'tavern': [('counter', 1, 'wall'), ('table', 2, 'centre'), ('chair', 5, 'by_table'), ('barrel', 3, 'corner'),
               ('bench', 1, 'wall'), ('bottle', 4, 'on_table'), ('dish', 4, 'on_table'), ('food', 2, 'on_table')],
}
PURPOSE_WORDS = {'bed': 'bedroom', 'sleep': 'bedroom', 'kitchen': 'kitchen', 'cook': 'kitchen', 'pantry': 'kitchen',
                 'store': 'storage', 'cellar': 'storage', 'storage': 'storage', 'study': 'study', 'library': 'study',
                 'office': 'study', 'shop': 'shop', 'store front': 'shop', 'trader': 'shop', 'shrine': 'shrine',
                 'chapel': 'shrine', 'temple': 'shrine', 'hall': 'hall', 'corridor': 'hall', 'tavern': 'tavern',
                 'inn': 'tavern', 'club': 'tavern', 'bar': 'tavern', 'living': 'living', 'main': 'living',
                 'common': 'living', 'dining': 'living', 'parlor': 'living', 'parlour': 'living',
                 'camp': 'camp', 'cave': 'camp', 'mine': 'camp', 'den': 'camp', 'ruin': 'ruin', 'vault': 'ruin'}


def purpose_for(name, tiles, w, h):
    low = (name or '').lower()
    for word, p in PURPOSE_WORDS.items():
        if word in low:
            return p
    if min(w, h) == 1:
        return 'hall'
    if tiles <= 4:
        return 'bedroom'
    return 'living'


# ------------------------------------------------------------------ rooms
FLOOR_T = 128            # the grid traced floors are cut into
_geo = {}


def _turned(rx, ry, rz):
    """The game's rotation of an object as a matrix (turned by -x, -y, -z in Z-Y-X order, like the 3D view)."""
    a, b, c = -rx, -ry, -rz
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    X = ((1, 0, 0), (0, ca, -sa), (0, sa, ca))
    Y = ((cb, 0, sb), (0, 1, 0), (-sb, 0, cb))
    Z = ((cc, -sc, 0), (sc, cc, 0), (0, 0, 1))
    mul = lambda A, B: tuple(tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(Z, mul(Y, X))


def _floor_tiles(db, m, G=32):
    """The walkable floor of a place, traced from its own walls and floors: level surfaces are floor,
    steep ones at head height are walls. Cut into tiles of FLOOR_T, with a wall on each side where the
    floor ends or a step is too high. Same shape as the tiles of a kit-built place, or None."""
    T = FLOOR_T
    floor, walls = {}, {}
    for r in m['refs']:
        if not r.get('arch') or r['type'] != 'STAT':
            continue
        key = r['id'].lower()
        if key not in _geo:
            ri = db.resolve_id(r['id'])
            _geo[key] = kits._model(db, ri) if ri is not None else None
        shapes = _geo[key]
        if not shapes:
            continue
        s = r['s'] or 1.0
        px, py, pz, rx, ry, rz = r['p']
        R = _turned(rx, ry, rz)
        for sh in shapes:
            p, idx = sh['p'], sh['i']
            V = []
            for k in range(0, len(p) - 2, 3):
                x, y, z = p[k] * s, p[k + 1] * s, p[k + 2] * s
                V.append((px + R[0][0] * x + R[0][1] * y + R[0][2] * z, py + R[1][0] * x + R[1][1] * y + R[1][2] * z,
                          pz + R[2][0] * x + R[2][1] * y + R[2][2] * z))
            for t in range(0, len(idx) - 2, 3):
                A, B, C = V[idx[t]], V[idx[t + 1]], V[idx[t + 2]]
                ux, uy, uz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
                vx, vy, vz = C[0] - A[0], C[1] - A[1], C[2] - A[2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                area = math.sqrt(nx * nx + ny * ny + nz * nz)
                if area < 1:
                    continue
                if abs(nz) / area > 0.8:
                    # level: floor at every grid point inside it (the lowest one, if there are several)
                    i0, i1 = int(math.floor(min(A[0], B[0], C[0]) / G)), int(math.ceil(max(A[0], B[0], C[0]) / G))
                    j0, j1 = int(math.floor(min(A[1], B[1], C[1]) / G)), int(math.ceil(max(A[1], B[1], C[1]) / G))
                    if (i1 - i0) * (j1 - j0) > 40000:
                        continue
                    d = ux * vy - uy * vx
                    if abs(d) < 1e-6:
                        continue
                    for i in range(i0, i1 + 1):
                        for j in range(j0, j1 + 1):
                            qx, qy = (i + 0.5) * G - A[0], (j + 0.5) * G - A[1]
                            l1, l2 = (qx * vy - qy * vx) / d, (ux * qy - uy * qx) / d
                            if l1 < 0 or l2 < 0 or l1 + l2 > 1:
                                continue
                            zz = A[2] + l1 * uz + l2 * vz
                            if (i, j) not in floor or zz < floor[(i, j)]:
                                floor[(i, j)] = zz
                elif abs(nz) / area < 0.5:
                    # steep: a wall in each grid square along it, from its bottom to its top
                    zlo, zhi = min(A[2], B[2], C[2]), max(A[2], B[2], C[2])
                    pts = (A, B, C)
                    L = max(math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]) for a, b in ((0, 1), (1, 2), (0, 2)))
                    n = max(1, int(L / (G / 2)))
                    for a, b in ((0, 1), (1, 2), (0, 2)):
                        for k in range(n + 1):
                            x = pts[a][0] + (pts[b][0] - pts[a][0]) * k / n
                            y = pts[a][1] + (pts[b][1] - pts[a][1]) * k / n
                            walls.setdefault((int(math.floor(x / G)), int(math.floor(y / G))), []).append((zlo, zhi))
    if not floor:
        return None
    # standing room: nothing solid from knee to head height above the floor
    ok = {c: z for c, z in floor.items() if not any(lo < z + 150 and hi > z + 35 for lo, hi in walls.get(c, ()))}
    n = T // G
    tiles = {}
    for (i, j) in {(c[0] // n, c[1] // n) for c in ok}:
        zs = [ok[(i * n + a, j * n + b)] for a in range(n) for b in range(n) if (i * n + a, j * n + b) in ok]
        if len(zs) < n * n * 0.7:
            continue
        zs.sort()
        tiles[(i, j)] = zs[len(zs) // 2]
    out = {}
    for (i, j), z in tiles.items():
        pat = {'cover': {}, 'offset': {}}
        for s, (dx, dy) in STEP.items():
            o = tiles.get((i + dx, j + dy))
            pat[s] = 'open' if o is not None and abs(o - z) < 40 else 'wall'
            pat['offset'][s] = T / 2 - 4
            pat['cover'][s] = 0.0
        x, y = (i + 0.5) * T, (j + 0.5) * T
        out[(x, y, round(z / 64))] = {'pat': pat, 'x': x, 'y': y, 'floor': z}
    return out or None


def _overlap_area(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _is_floor_piece(db, rid):
    """A kit's floor tile, wall, door frame or stairs (the building itself), not something standing in it."""
    prefix = kits.kit_prefix(rid)
    kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
    low = rid.lower()
    if kp and any(p['id'].lower() == low for p in kp['pieces'] + kp['jambs'] + kp['walls']):
        return True
    return any(w in low for w in ('wall', 'floor', 'ceiling', 'stair', 'ramp', 'jamb', 'door', 'room', 'hall', 'corner',
                                  'side', 'center', 'centre', 'entry', 'end', 'cap', 'shell', 'cave', 'arch'))


def rooms(db, cell_key, names=None):
    """The rooms of a place, from its kit floor pieces: [{id, name, purpose, tiles, x_min, ...}]."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('Auto-furnish works in interiors.')
    tiles = {}
    T = None
    for r in m['refs']:
        prefix = kits.kit_prefix(r['id'])
        kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
        if not kp:
            continue
        piece = next((p for p in kp['pieces'] if p['id'].lower() == r['id'].lower()), None)
        if not piece or abs((r['s'] or 1) - 1) > 0.05:
            continue
        T = T or kp['tile']
        if kp['tile'] != T:
            continue
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        pat = kits.rotate(piece['pattern'], q)
        floor = r['p'][2] + piece['zmin']
        tiles[(r['p'][0], r['p'][1], round(floor / 64))] = {'pat': pat, 'x': r['p'][0], 'y': r['p'][1], 'floor': floor}
    # places not (only) built from tiles: yurts, caves, Dwemer halls, Velothi's ready-made rooms
    premade = any(r.get('arch') and r.get('b') and (r['b'][3] - r['b'][0]) * (r['b'][4] - r['b'][1]) * (r['s'] or 1) ** 2 > 2.5 * 256 * 256
                  and not (kits.kit_prefix(r['id']) and any(p['id'].lower() == r['id'].lower() for p in
                           (kits.kit_pieces(db, kits.kit_prefix(r['id'])) or {}).get('pieces', [])))
                  for r in m['refs'])
    if not tiles or premade:
        traced = _floor_tiles(db, m)
        if traced:
            tiles, T = traced, FLOOR_T
    if not tiles:
        return {'tile': None, 'rooms': [], 'refs': m['refs']}
    # a place made with "Build from pieces" remembers its rooms
    plan = (db.project.cells.get(cell_key) or {}).get('plan') if db.project else None
    if plan and plan.get('rooms'):
        result = []
        for n, pr in enumerate(plan['rooms']):
            # tiles are [x, y] or, in buildings with more than one floor, [x, y, floor height]
            g = [k for k in tiles if any(abs(k[0] - pt[0]) < 24 and abs(k[1] - pt[1]) < 24 and
                                         (len(pt) < 3 or abs(tiles[k]['floor'] - pt[2]) < 64) for pt in pr['tiles'])]
            if not g:
                continue
            xs = [tiles[k]['x'] for k in g]
            ys = [tiles[k]['y'] for k in g]
            w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
            result.append({'id': n, 'name': pr['name'], 'tiles': len(g), 'w': w, 'h': h,
                           'purpose': purpose_for(pr['name'], len(g), w, h),
                           'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2,
                           'y_max': max(ys) + T / 2, 'floor': min(tiles[k]['floor'] for k in g),
                           '_tiles': [tiles[k] for k in g]})
        return {'tile': T, 'rooms': result, 'refs': m['refs']}
    # otherwise: tiles side by side and open towards each other make one room, unless a door frame
    # stands between them
    frames = [(r['p'][0], r['p'][1]) for r in m['refs'] if 'jamb' in r['id'].lower() or r['type'] == 'DOOR']

    def framed(a, b):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        return any(abs(fx - mx) < 40 and abs(fy - my) < 40 for fx, fy in frames)

    near = {}
    for kk in tiles:
        near.setdefault((round(kk[0] / 32), round(kk[1] / 32), kk[2]), []).append(kk)

    def nb(k, s):
        x, y, lv = k
        tx, ty = x + STEP[s][0] * T, y + STEP[s][1] * T
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for kk in near.get((round(tx / 32) + dx, round(ty / 32) + dy, lv), ()):
                    if abs(kk[0] - tx) < 24 and abs(kk[1] - ty) < 24:
                        return kk
        return None
    seen, out = set(), []
    for k in sorted(tiles):
        if k in seen:
            continue
        group, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            group.append(c)
            for s in STEP:
                n = nb(c, s)
                if n and n not in seen and tiles[c]['pat'][s] == 'open' and tiles[n]['pat'][OPP[s]] == 'open' \
                        and not framed(c, n):
                    seen.add(n)
                    todo.append(n)
        out.append(group)
    out.sort(key=lambda g: (-len(g), g[0]))
    result = []
    for n, g in enumerate(out):
        xs = [tiles[k]['x'] for k in g]
        ys = [tiles[k]['y'] for k in g]
        w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
        name = (names or {}).get(n) or 'Room %d' % (n + 1)
        result.append({'id': n, 'name': name, 'tiles': len(g), 'w': w, 'h': h,
                       'purpose': purpose_for(name, len(g), w, h),
                       'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2, 'y_max': max(ys) + T / 2,
                       'floor': min(tiles[k]['floor'] for k in g), '_tiles': [tiles[k] for k in g]})
    return {'tile': T, 'rooms': result, 'refs': m['refs']}


# ------------------------------------------------------------------ which way things face
_facing = {}


def front_of(db, rid):
    """The direction an object's front points in its own coordinates, learnt from real interiors
    (furniture faces into the room). (x, y) unit vector, or None if it can't be told."""
    low = rid.lower()
    if low in _facing:
        return _facing[low]
    sx = sy = 0.0
    n = 0
    for ci in list(db.used_in.get(low, ()))[:14]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not kits.game_made(db, r[7]):
            continue
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
            _hdr, crefs = split_cell(data)
        except Exception:
            continue
        pts, mine = [], []
        for cr in crefs:
            cid, pos, _s, dele = ref_info(cr['subs'])
            if dele:
                continue
            pts.append(pos)
            if cid.lower() == low:
                mine.append(pos)
        for pos in mine[:4]:
            near = [p for p in pts if 30 < math.hypot(p[0] - pos[0], p[1] - pos[1]) < 700 and abs(p[2] - pos[2]) < 300]
            if len(near) < 4:
                continue
            cx = sum(p[0] for p in near) / len(near) - pos[0]
            cy = sum(p[1] for p in near) / len(near) - pos[1]
            d = math.hypot(cx, cy)
            if d < 1:
                continue
            th = pos[5]
            # into the object's own frame (the game turns things clockwise)
            lx, ly = (cx * math.cos(th) - cy * math.sin(th)) / d, (cx * math.sin(th) + cy * math.cos(th)) / d
            sx += lx
            sy += ly
            n += 1
    out = None
    if n >= 2:
        sx, sy = sx / n, sy / n
        if max(abs(sx), abs(sy)) > 0.25:
            out = (1.0 if sx > 0 else -1.0, 0.0) if abs(sx) > abs(sy) else (0.0, 1.0 if sy > 0 else -1.0)
    _facing[low] = out
    return out


_heights = {}


def hang_height(db, rid):
    """How far above the floor an object's bottom usually is in real interiors (wall shelves,
    sconces, banners hang; most things stand on the floor). 0 for things that stand."""
    low = rid.lower()
    if low in _heights:
        return _heights[low]
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    out = 0.0
    if b:
        bounds_of = {}

        def bnd(cid):
            k = cid.lower()
            if k not in bounds_of:
                cri = db.resolve_id(cid)
                bounds_of[k] = (mapdata.object_bounds(db, cri), db.recs[cri][0]) if cri is not None else (None, '')
            return bounds_of[k]
        found = []
        for ci in list(db.used_in.get(low, ()))[:10]:
            r = db.recs[ci]
            if r[0] != 'CELL' or not kits.game_made(db, r[7]):
                continue
            try:
                _t, _f, data = db.files[r[3]].record_at(r[4])
                _hdr, crefs = split_cell(data)
            except Exception:
                continue
            all_refs = []
            for cr in crefs:
                cid, pos, sc, dele = ref_info(cr['subs'])
                if not dele:
                    all_refs.append((cid, pos, sc or 1.0))
            for cid, pos, sc in all_refs:
                if cid.lower() != low or len(found) >= 12:
                    continue
                bottom = pos[2] + b[2] * sc
                # the floor under it: the top of the room pieces (architecture) right below it
                floors = []
                resting = False
                for oid, op, osc in all_refs:
                    if abs(op[0] - pos[0]) > 200 or abs(op[1] - pos[1]) > 200:
                        continue
                    ob, otag = bnd(oid)
                    if not ob:
                        continue
                    if not mapdata.is_architecture(otag, oid, ob):
                        # standing on a crate, a barrel or a table here, not hanging on the wall
                        if op is not pos and abs(op[0] - pos[0]) < 60 and abs(op[1] - pos[1]) < 60 and \
                                abs(op[2] + ob[5] * osc - bottom) < 8:
                            resting = True
                        continue
                    fz = op[2] + ob[2] * osc
                    if fz <= bottom + 4 and bottom - fz < 400:
                        floors.append(fz)
                if floors and not resting:
                    found.append(bottom - max(floors))
        if len(found) >= 2:
            found.sort()
            med = found[len(found) // 2]
            _mount[low] = med             # (for things on walls that reach nearly to the floor)
            if med > 40:                  # it hangs: remember how high
                out = med
    _heights[low] = out
    return out


_mount = {}


def mount_height(db, rid):
    """How far above the floor the bottom of an object usually is, even when that is only a little
    (a long tapestry); None if the game doesn't use it in enough places to tell."""
    hang_height(db, rid)
    return _mount.get(rid.lower())


def _turn_to_face(front, direction):
    """Turn (radians, multiple of 90 degrees) so the local front points along the world direction."""
    f = front or (0.0, -1.0)
    best, bd = 0.0, -9
    for q in range(4):
        th = q * math.pi / 2
        wx, wy = f[0] * math.cos(th) + f[1] * math.sin(th), -f[0] * math.sin(th) + f[1] * math.cos(th)
        d = wx * direction[0] + wy * direction[1]
        if d > bd:
            best, bd = th, d
    return best


def _footprint(b, rot, x, y):
    """Axis-aligned box (x0, y0, x1, y1) of a model turned by a multiple of 90 degrees at (x, y)."""
    corners = [(b[0], b[1]), (b[3], b[1]), (b[0], b[4]), (b[3], b[4])]
    c, s = math.cos(rot), math.sin(rot)
    pts = [(x + px * c + py * s, y - px * s + py * c) for px, py in corners]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _overlaps(a, b, pad=4):
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


# ------------------------------------------------------------------ choosing things
CORE_KINDS = ('bed', 'table', 'chair', 'bench', 'chest', 'cupboard', 'shelf')
_related = {}


def related_cells(db, culture, limit=40):
    """Interiors built from pieces of the same culture (e.g. every Dunmer house kit), most built-up first."""
    key = (culture, limit)
    if _related.get('recs') is not db.recs:
        _related.clear()
        _related['recs'] = db.recs
    if key in _related:
        return _related[key]
    counts = {}
    for oid, cells in db.used_in.items():
        if not kits.kit_prefix(oid):
            continue                                  # only building pieces say what a place is
        label = mapdata.style_of(oid)
        if not label or STYLE_SET.get(label, 'imperial') != culture:
            continue
        for ci in cells:
            r = db.recs[ci]
            if r is not None and r[0] == 'CELL' and not r[7].startswith('#') and ci not in db.dead:
                counts[r[7]] = counts.get(r[7], 0) + 1
    out = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:limit])
    _related[key] = out
    return out


def _named(low, words):
    """Is one of these words in the name? Short words only as a word of their own ("urn", not the
    "urn" in "furn_de_rope"; "bed", not "bedroll"), longer ones anywhere ("chair" in "armchair")."""
    tokens = None
    for w in words:
        w = w.strip('_')
        if not w:
            return True
        if len(w) > 3:
            if w in low:
                return True
            continue
        if tokens is None:
            tokens = re.split(r'[^a-z0-9]+', low)
        if any(t == w or re.fullmatch(w + r'\d*[a-z]?', t) for t in tokens):
            return True
    return False


def _sort_into(fam, groups):
    for g in groups:
        for it in g['items']:
            low = (it['id'] + ' ' + (it['name'] or '')).lower()
            for k, (words, types) in FAMILIES.items():
                if it['type'] not in types:
                    continue
                if not _named(low, words):
                    continue
                if any(w in low for w in NOT.get(k, ())):
                    continue
                if 'marker' in low or 'unique' in low:
                    continue
                if it['id'] not in fam[k]:
                    fam[k].append(it['id'])
                break


def candidates(db, cell_key):
    """Things used in places like this one, sorted into kinds of furniture (most used first).
    When few places are built from the same pieces (a style only a mod or two uses), it also
    learns from other places of the same culture: other Dunmer houses for a Dres one, and plain
    common furniture for a style with no relatives."""
    pal = mapdata.palette(db, cell_key, limit=80)
    fam = {k: [] for k in FAMILIES}
    _sort_into(fam, pal.get('groups', []))
    style = pal.get('style', '')
    have = sum(1 for k in CORE_KINDS if fam[k])
    if pal.get('similar', 0) < 8 or have < 4:
        culture = STYLE_SET.get(style, 'imperial')
        cells = {k: v for k, v in related_cells(db, culture).items() if k != cell_key}
        if cells:
            # (after this place's own things; a long list, so rarer pieces like beds make it in)
            _sort_into(fam, mapdata.palette_from(db, cells, limit=400))
        fam['_borrowed'] = culture
    return fam, style


DECOR_WORDS = ('tapestry', 'banner', 'painting', 'picture', 'portrait', 'sconce', 'weaponrack', 'weapon_rack', 'rack',
               'trophy', 'plaque', 'map', 'mask', 'shield', 'flag', 'herbs', 'hanging', 'wall')
NOT_DECOR = ('door', 'window', 'marker', 'unique', 'gate', 'light_de_lantern', 'chandelier', 'rug', 'carpet', 'curtain',
             'rope', 'web', 'ivy', 'flora', 'railing', 'rail_', 'pole', 'post', 'burial', 'shutter', 'chain', 'beam',
             'pillar', 'column', 'stair', 'ladder', 'cage', 'bone', 'skull', 'blood', 'cobweb', 'moss', 'screen')
# which pieces suit which kind of place, by the start of their IDs
DECOR_SETS = {'dunmer': ('furn_de_', 't_de_', 'light_de_', 'furn_banner', 'furn_tapestry'),
              'imperial': ('furn_com_', 'furn_imp', 't_imp_', 't_com_', 'light_com_', 'furn_c_'),
              'nordic': ('furn_nord', 't_nor_', 't_sky_', 'furn_com_', 'light_com_')}
STYLE_SET = {'Hlaalu': 'dunmer', 'Redoran': 'dunmer', 'Telvanni': 'dunmer', 'Velothi': 'dunmer', 'Dunmer': 'dunmer',
             'Daedric': 'dunmer', 'Common': 'imperial', 'Imperial': 'imperial', 'Breton': 'imperial', 'Cyrodiilic': 'imperial',
             'Nordic': 'nordic', 'Skyrim': 'nordic', 'Ashlander': 'dunmer', 'Redguard': 'imperial',
             'High Elf': 'imperial', 'Stronghold': 'imperial', 'Mournhold': 'dunmer', 'Indoril': 'dunmer', 'Dres': 'dunmer',
             'Dwemer': 'dunmer', 'Cave': 'dunmer', 'Reach': 'nordic'}
CULTURE_NAMES = {'dunmer': 'other Dunmer places', 'imperial': 'common and Imperial places', 'nordic': 'other Nordic places'}
_decor_global = {}


def wall_decor(db, cell_key):
    """Things that hang on the walls in places like this one (tapestries, banners, paintings, wall
    shelves, sconces, racks), learnt from where the game itself puts them: well up off the floor,
    and flat against a wall. [(id, how high it hangs, kind)] most used first."""
    pal = mapdata.palette(db, cell_key, limit=120)
    out, seen = [], set()
    items = [it for g in pal.get('groups', []) for it in g['items']]
    # and the game's own tapestries, banners, paintings and sconces of the same make, used anywhere
    dset = DECOR_SETS.get(STYLE_SET.get(pal.get('style', ''), ''), ())
    if dset:
        key = (dset, id(db.recs))
        if key not in _decor_global:
            found = []
            for (tag, k), lst in db.by_key.items():
                if tag not in ('STAT', 'LIGH') or not k.startswith(dset) or not any(w in k for w in ('tapestry', 'banner', 'painting', 'sconce')):
                    continue
                if not lst or lst[-1] in db.dead:
                    continue
                n = len(db.used_in.get(k, ()))
                if n >= 3:
                    found.append((n, {'id': db.recs[lst[-1]][1], 'name': db.recs[lst[-1]][2], 'type': tag}))
            found.sort(key=lambda x: -x[0])
            _decor_global[key] = [f[1] for f in found[:40]]
        items += _decor_global[key]
    for it in items:
        if True:
            rid, low = it['id'], (it['id'] + ' ' + (it.get('name') or '')).lower()
            if rid.lower() in seen or it['type'] not in ('STAT', 'ACTI', 'LIGH', 'MISC'):
                continue
            seen.add(rid.lower())
            if any(w in low for w in NOT_DECOR):
                continue
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            if not b:
                continue
            w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
            thin, wide = min(w, d), max(w, d)
            named = any(w_ in low for w_ in DECOR_WORDS)
            flat = thin <= (44 if named else 32) and wide >= 40 and h >= 30     # (a tapestry's rod adds depth)
            if it['type'] == 'LIGH' and 'sconce' not in low and 'wall' not in low:
                continue                       # free-standing candles and lamps are not wall things
            if not (flat or named) or wide > 420 or h > 400:
                continue
            hang = hang_height(db, rid)
            if hang < 50:
                # a long tapestry or banner can reach nearly to the floor: still a wall thing if it's flat
                m = mount_height(db, rid)
                if not (named and flat and m is not None and m >= 0):
                    continue                   # the game keeps it on the floor or a table
                hang = max(4.0, m)
            kind = next((k for k in ('tapestry', 'banner', 'painting', 'sconce', 'rack', 'shelf', 'trophy', 'herbs')
                         if k in low), 'light' if it['type'] == 'LIGH' else 'decor')
            out.append((rid, hang, kind))
    return out


DECOR_PER_PURPOSE = {'storage': 0.15, 'kitchen': 0.25, 'hall': 0.3, 'camp': 0.1}       # share of free wall spots used (default 0.4)
DECOR_KINDS = {'shrine': ('banner', 'tapestry', 'sconce'), 'storage': ('rack', 'herbs', 'decor', 'sconce'),
               'kitchen': ('herbs', 'decor', 'sconce', 'tapestry'), 'camp': ('herbs', 'sconce', 'light')}


def house_hangings(db, decor, rng):
    """The wall things for one house: the game's own houses keep to a couple of kinds of tapestry or
    banner (half of them use one or two), so the house gets two, picked from the most used, and up to two
    of each other kind (racks, herbs...). Also, as wallsurvey.py found: a hanger or banner post that is
    almost never without its banner isn't hung on its own (a banner goes up with what it hangs from)."""
    import wallsurvey
    decor = [d for d in decor if wallsurvey.hangs_alone(db, d[0]) or wallsurvey.partner(db, d[0])]
    # (and no torn hangings from ruins and dungeons in a lived-in place; nothing is hung in a ruin)
    decor = [d for d in decor if not re.search(r'dngruin|_ruin|ruins_|dng_|dngcryp|crypt', d[0].lower())]
    out, count = [], {}
    cloth = [d for d in decor if d[2] in ('tapestry', 'banner', 'painting')]
    top = cloth[:4]
    rng.shuffle(top)
    keep = {d[0] for d in top[:2]}
    for d in decor:
        if d[2] in ('tapestry', 'banner', 'painting'):
            if d[0] in keep:
                out.append(d)
        elif count.get(d[2], 0) < 2:
            count[d[2]] = count.get(d[2], 0) + 1
            out.append(d)
    return out


def _decorate(db, room, purpose, T, decor, refs, placed, put, rng, hung):
    """Hang things on the free walls of one room: flat against the wall, facing in, at the height the
    game hangs them, never over a doorway or into furniture that stands that high. hung: what hangs in
    the house so far, [(x, y, floor, direction it faces)]."""
    if not decor:
        return []
    import wallsurvey
    floor = room['floor']
    # what already stands here, with its height (so a tapestry can hang above a low chest, not a shelf)
    solid = []
    for r in list(refs) + list(placed):
        b = r.get('b')
        if not b or r.get('arch') or r['type'] in ('NPC_', 'CREA'):
            continue
        s = r.get('s') or 1.0
        solid.append((_footprint([v * s for v in b], r['p'][5], r['p'][0], r['p'][1]), r['p'][2] + b[2] * s, r['p'][2] + b[5] * s,
                      r['type'] == 'DOOR'))
    spots = []
    for t in room['_tiles']:
        walls_here = [s for s in STEP if t['pat'][s] == 'wall']
        for s in walls_here:
            off = t['pat']['offset'].get(s, T / 2 - 16) - 3              # the wall's inside face
            spots.append({'x': t['x'] + STEP[s][0] * off, 'y': t['y'] + STEP[s][1] * off, 'in': (-STEP[s][0], -STEP[s][1]),
                          'corner': len(walls_here) >= 2})
    rng.shuffle(spots)
    spots.sort(key=lambda sp: sp['corner'])                              # the middle of a wall first
    # not two things side by side, on the same wall, round a corner or through an opening into the next
    # room: a good stretch of wall between (back to back on the two sides of one wall is fine)
    gap = max(384, T * 1.5)

    def crowded(sp):
        for hx, hy, hf, hin in hung:
            if abs(hf - floor) > 100 or math.hypot(hx - sp['x'], hy - sp['y']) > gap:
                continue
            if hin == (-sp['in'][0], -sp['in'][1]) and (abs(hx - sp['x']) < 40 if hin[0] == 0 else abs(hy - sp['y']) < 40):
                continue
            return True
        return False
    spots = [sp for sp in spots if not crowded(sp)]
    # a few per room, by its floor area (in standard 256-unit tiles; traced floors are cut finer): about one
    # for every four tiles, fewer in stores and kitchens, never more than three
    area = room['tiles'] * (T / 256.0) ** 2
    want = max(1, min(3, int(round(area * 0.25 * DECOR_PER_PURPOSE.get(purpose, 0.4) / 0.4))))
    kinds = DECOR_KINDS.get(purpose)
    pool = [d for d in decor if not kinds or d[2] in kinds] or decor
    lights = [d for d in pool if d[2] in ('sconce', 'light')]
    others = [d for d in pool if d[2] not in ('sconce', 'light')]
    # one kind of hanging for the room, repeated (as in the game's own houses, where the hangings side by
    # side are mostly the same one), and a sconce or two for light
    plan = []
    if others:
        main = rng.choice(others[:2])
        plan += [main] * max(1, want - (1 if lights else 0))
    if lights:
        plan += [lights[0]] * min(2, max(1, want // 3))
    got = []
    for rid, hang, kind in plan:
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        front = front_of(db, rid)
        z0, z1 = floor + hang, floor + hang + (b[5] - b[2])
        for sp in list(spots):
            rot = _turn_to_face(front, sp['in'])
            box0 = _footprint(b, rot, 0, 0)
            back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sp['in']]
            x, y = sp['x'] + sp['in'][0] * (back + 1), sp['y'] + sp['in'][1] * (back + 1)
            box = _footprint(b, rot, x, y)
            # clear of doors (any height) and of whatever stands as high as it hangs, with a little room around
            pad = (box[0] - 24, box[1] - 24, box[2] + 24, box[3] + 24)
            if any(_overlaps(pad if door else box, fb, 0) and (door or (zb < z1 + 4 and zt > z0 - 4))
                   for fb, zb, zt, door in solid):
                continue
            rec = put(rid, x, y, rot, hang_from=z0, room=room['name'])
            if rec is None:
                break
            solid.append((box, z0, z1, False))
            # what it hangs from, where the game puts it (a hanger above a banner, a banner post...)
            pt = wallsurvey.partner(db, rid)
            if pt and wallsurvey.HANGY.search(pt['id']):
                pri = db.resolve_id(pt['id'])
                pb = mapdata.object_bounds(db, pri) if pri is not None else None
                if pb:
                    lx, ly, dz = pt['offset']
                    c_, s_ = math.cos(rot), math.sin(rot)
                    px, py = x + lx * c_ + ly * s_, y - lx * s_ + ly * c_
                    put(pt['id'], px, py, (rot + pt['dq'] * math.pi / 2) % (2 * math.pi), hang_from=rec['p'][2] + dz + pb[2],
                        room=room['name'])
            spots.remove(sp)
            hung.append((sp['x'], sp['y'], floor, sp['in']))
            spots[:] = [o for o in spots if not crowded(o)]
            got.append(rid)
            break
    return got


def furnish(db, cell_key, plan=None, seed=None, walls=True, walls_only=False):
    """Fill rooms with furniture. plan: [{'id': room id, 'purpose': ...}] (all rooms, by their
    guessed purpose, if None). Everything goes in as one change. Returns what was placed."""
    editing._require_project(db)
    info = rooms(db, cell_key)
    if not info['rooms']:
        raise EditError('No rooms found here. Auto-furnish works in places built from modular room pieces '
                        '(like the ones "Build from pieces" makes, and most town interiors).')
    T = info['tile']
    fam, style = candidates(db, cell_key)
    # caves, camps and ruins aren't homes: rough sleeping and stores there, unless a room was named
    ROUGH = {'Cave': 'camp', 'Ashlander': 'camp', 'Mine': 'camp', 'Dwemer': 'ruin', 'Daedric': 'ruin', 'Ruin': 'ruin'}
    rough = ROUGH.get(style)
    if not rough:
        # the walls say it better than the furniture: a yurt full of Dunmer things is still a tent
        shell = {}
        for r in mapdata.cellmap(db, cell_key).get('refs', []):
            low = r['id'].lower()
            if low.startswith(('in_', 'ex_')) or kits.kit_prefix(low):
                st = mapdata.style_of(low)
                if st:
                    shell[st] = shell.get(st, 0) + 1
        if shell:
            top = max(shell, key=shell.get)
            rough = ROUGH.get(top)
    if rough:
        for rm in info['rooms']:
            if re.match(r'^room \d+$', (rm['name'] or '').lower()) or not rm['name']:
                rm['purpose'] = rough
    rng = random.Random(seed if seed is not None else cell_key)
    decor = house_hangings(db, wall_decor(db, cell_key), rng) if (walls or walls_only) else []
    # the kind of place its name says it is (a tavern, a shop, a temple): what the game keeps in the
    # containers there goes by it
    import roomsurvey
    theme = roomsurvey.theme_of((mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key)
    wanted = {p['id']: p.get('purpose') for p in (plan or [])}
    # everything already standing here takes up room: (box, bottom, top), so that a room only minds
    # what stands on its own floor, not the furniture of the room above or below it
    refs = info['refs']
    taken = []

    def span(r):
        b, s = r.get('b'), r.get('s') or 1.0
        return (r['p'][2] + b[2] * s, r['p'][2] + b[5] * s) if b else (r['p'][2] - 20, r['p'][2] + 200)
    for r in refs:
        if r.get('b') and not r.get('arch') and r['type'] not in ('LIGH',):
            taken.append((_footprint([v * (r['s'] or 1.0) for v in r['b']], r['p'][5], r['p'][0], r['p'][1]),) + span(r) + (False,))
        elif r.get('b') and r.get('arch') and info['tile'] != FLOOR_T and (r['b'][5] - r['b'][2]) * (r['s'] or 1) > 30 \
                and not _is_floor_piece(db, r['id']):
            # (traced floors already leave out what stands in the way; rugs are flat)
            # big things standing in a room that aren't its floor and walls: a tree, a pillar, a statue
            s = r['s'] or 1.0
            fp = _footprint([v * s for v in r['b']], r['p'][5], r['p'][0], r['p'][1])
            # (one that covers most of a room is the building itself, like a hut's shell)
            area = (fp[2] - fp[0]) * (fp[3] - fp[1])
            shell = any(_overlap_area(fp, (rm['x_min'], rm['y_min'], rm['x_max'], rm['y_max'])) >
                        0.4 * (rm['x_max'] - rm['x_min']) * (rm['y_max'] - rm['y_min']) for rm in info['rooms'])
            if area < 700 * 700 and not shell:
                taken.append((fp,) + span(r) + (False,))
    # keep doorways clear: doors and door frames, with room to walk through on both sides (a door's
    # own point is often at its hinge, so the clear space reaches well past it), and room sides that
    # open into other rooms
    clear = max(150, (info['tile'] or 256) * 0.6)
    openings = []
    for r in refs:
        low = r['id'].lower()
        if r['type'] == 'DOOR' or 'jamb' in low or 'doorway' in low:
            zb, zt = span(r)
            taken.append(((r['p'][0] - clear, r['p'][1] - clear, r['p'][0] + clear, r['p'][1] + clear), zb, zt, True))
            openings.append(r)
        # and the landings at both ends of a staircase
        if r['type'] == 'STAT' and ('stair' in low or 'ramp' in low) and info['tile']:
            T = info['tile']
            along_x = abs(math.sin(r['p'][5])) < 0.5          # which way the stairs run, before turning
            prefix = kits.kit_prefix(r['id'])
            si = kits.stairs(db, prefix) if prefix and prefix in kits.kits(db) else None
            sp = next((p for p in si['pieces'] if p['id'].lower() == low), None) if si else None
            if sp:
                along_x = (sp['low'] in 'EW') == along_x
            ax, ay = (T * 1.5, T * 0.5) if along_x else (T * 0.5, T * 1.5)
            zb, zt = span(r)
            taken.append(((r['p'][0] - ax, r['p'][1] - ay, r['p'][0] + ax, r['p'][1] + ay), zb - 40, zt + 40, True))
    T = info['tile']
    surf = [dict(r) for r in refs]           # for finding floor and table heights as things are added
    placed = []
    # the rugs here (box, floor height): rugs don't lie next to or over each other
    rugs = [(_footprint([v * (r['s'] or 1.0) for v in r['b']], r['p'][5], r['p'][0], r['p'][1]), r['p'][2])
            for r in refs if r.get('b') and _named(r['id'].lower(), FAMILIES['rug'][0])]
    # and what already hangs on the walls (on the floor of the room it's in)
    levels = sorted(set(rm['floor'] for rm in info['rooms']))
    hung = [(r['p'][0], r['p'][1], max([f for f in levels if f <= r['p'][2] + 10], default=r['p'][2]), (0, 0))
            for r in refs if re.search(r'tapestr|banner|painting', r['id'].lower())]
    c, _r = editing._cell(db, cell_key)
    mine = db.project.plugin.lower()
    global last_placed, last_clutter
    last_placed = placed                     # (for tests: what went where)
    last_clutter = []

    def put(rid, x, y, rot, on_top=False, hang_from=None, floor=None, flat=False, room=None, at_z=None, tilt=(0, 0), scale=1.0):
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri)
        if not b:
            return None
        tag = db.recs[ri][0]
        if at_z is not None:
            z = at_z                             # exactly where a game dressing puts it on its shelf
        elif hang_from is not None:
            z = hang_from - b[2]                 # hung on the wall at its usual height
        else:
            # on this room's own floor (not up on the floor of a room above it), or on a table in it; a
            # rug always on the floor
            under = [r for r in surf if r.get('arch')] if flat else surf
            z = mapdata.surface_z(db, under, True, x, y, b, 1.0, 'MISC' if on_top else tag,
                                  None if floor is None else floor + 64)
            if floor is not None and z + b[2] < floor - 40:
                return None                      # no floor under it here (a stairwell): leave it out
        nk = db.project.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                       set_ref_pos([('NAME', zs(rid))], (x, y, z, tilt[0], tilt[1], rot), scale))
        rec = {'id': rid, 'p': [x, y, z, tilt[0], tilt[1], rot], 's': scale, 'b': b, 'type': tag,
               'arch': False, 'room': room}
        surf.append(rec)
        placed.append(rec)
        return rec

    def dress(rec, purpose):
        """Set a new bookshelf, shelf, table or counter out the way the game dresses that model (see
        shelfsurvey.py): the things of one of its real dressings, at the same spots on the same shelves,
        with a book or two swapped and the odd end piece changed. None when the game never dresses it."""
        import shelfsurvey
        d = shelfsurvey.dressing(db, rec['id'], purpose, rng, books=fam.get('book') or [])
        if d is None:
            return None
        px, py, pz, rz = rec['p'][0], rec['p'][1], rec['p'][2], rec['p'][5]
        for o in d:
            wx, wy = shelfsurvey.to_world(o['x'], o['y'], rz)
            put(o['id'], px + wx, py + wy, (rz + o['rz']) % (2 * math.pi), at_z=pz + o['z'], tilt=(o['rx'], o['ry']),
                scale=o['s'], room=rec.get('room'))
        return d

    def rug_sizes():
        out = []
        for rid in fam.get('rug') or []:
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            if b:
                out.append((rid, b, max(b[3] - b[0], b[4] - b[1]), min(b[3] - b[0], b[4] - b[1])))
        return out
    all_rugs = rug_sizes()
    mats = [r for r in all_rugs if r[2] <= 200]                 # door mats: the small ones
    big_rugs = [r for r in all_rugs if r[2] > 200] or all_rugs

    def rug_free(box, fl):
        """Not on or right next to another rug (a hand's width apart at least)."""
        return not any(abs(f - fl) < 60 and _overlaps(box, (o[0] - 40, o[1] - 40, o[2] + 40, o[3] + 40), 0) for o, f in rugs)

    report = []
    groups = []                              # the sizes of the clutter groups made
    for room in info['rooms']:
        purpose = wanted.get(room['id'], room['purpose']) if plan is not None else room['purpose']
        if plan is not None and room['id'] not in wanted:
            continue
        if not purpose or purpose == 'none' or purpose not in RECIPES:
            continue
        tl = room['_tiles']
        # inside the room (wall spots already stand off the measured wall face)
        inner = (room['x_min'] + 8, room['y_min'] + 8, room['x_max'] - 8, room['y_max'] - 8)
        fl = room['floor']
        # open sides of this room (to other rooms, doorways) stay clear
        for t in tl:
            for s, (dx, dy) in STEP.items():
                if t['pat'][s] == 'door' or (t['pat'][s] == 'open' and not any(
                        abs(u['x'] - (t['x'] + dx * T)) < 24 and abs(u['y'] - (t['y'] + dy * T)) < 24 for u in tl)):
                    mx, my = t['x'] + dx * T * 0.45, t['y'] + dy * T * 0.45
                    taken.append(((mx - 100, my - 100, mx + 100, my + 100), fl, fl + 200, True))
        # spots along the walls: (x, y on the wall's inside face, direction into the room, is it a corner)
        slots = []
        for t in tl:
            walls_here = [s for s in STEP if t['pat'][s] == 'wall']
            for s in walls_here:
                off = t['pat']['offset'].get(s, T / 2 - 16) - 14
                wx, wy = t['x'] + STEP[s][0] * off, t['y'] + STEP[s][1] * off
                inward = (-STEP[s][0], -STEP[s][1])
                slots.append({'x': wx, 'y': wy, 'in': inward, 'corner': len(walls_here) >= 2, 'side': s})
        rng.shuffle(slots)
        cx, cy = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
        # how big the room is, in standard 256-unit tiles (traced floors are cut finer); a huge hall
        # doesn't get endless furniture
        area_k = max(1.0, min(3.0, room['tiles'] * (T / 256.0) ** 2 / 9.0))
        tables = []
        fronts = []         # what people stand in front of: a bed's side, a shrine, a counter ({box, in})
        got = []

        def pick(kind):
            lst = fam.get(kind) or []
            if not lst:
                return None
            if kind in CONTAINER_KINDS:
                # the container the game stands in rooms like this, in places like this, with its
                # contents (a kitchen barrel's saltrice, a bedroom chest's clothes and coins)
                import containersurvey
                rid = containersurvey.pick(db, kind, purpose, theme, rng, palette=lst)
                if rid:
                    return rid
            return lst[min(len(lst) - 1, int(rng.random() ** 2 * min(4, len(lst))))]

        def inside(box):
            return box[0] >= inner[0] and box[1] >= inner[1] and box[2] <= inner[2] and box[3] <= inner[3]

        def fits(box, clearings=True):
            """Inside the room and clear of what stands on this floor (and of doorways, unless clearings
            is False: a door mat may lie in one)."""
            if not inside(box):
                return False
            return not any(_overlaps(box, o[0]) for o in taken
                           if o[1] < fl + 150 and o[2] > fl + 4 and (clearings or not o[3]))

        def wall_spot(b, front, where):
            """A free spot for this thing with its back to a wall (a corner first when where is
            'corner'): ((x, y, rot, box), direction into the room), or (None, None). The slot is used up."""
            order = sorted(slots, key=lambda s: (not s['corner']) if where == 'corner' else s['corner'])
            for sl in order:
                rot = _turn_to_face(front, sl['in'])
                box0 = _footprint(b, rot, 0, 0)
                # back against the wall: move out by the part of the box behind the origin
                depth_back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sl['in']]
                x = sl['x'] + sl['in'][0] * (depth_back + 2)
                y = sl['y'] + sl['in'][1] * (depth_back + 2)
                box = _footprint(b, rot, x, y)
                if fits(box):
                    slots.remove(sl)
                    return (x, y, rot, box), sl['in']
            return None, None

        def place_clutter(items, cs):
            """Crates, barrels, sacks and urns in groups the way the game stands them (roomsurvey
            clusters): a group starts at a corner or by a wall as often as the game's do, is as big as the
            game's groups are, and each further piece stands next to one already in the group, about as
            far off as the game keeps its own kind. items: the kinds to place, in order; returns the
            group sizes made."""
            sizes = [(s, w) for s, w in cs['sizes'] if w > 0] or [(1, 1.0)]
            w_corner = cs['where'].get('corner', 0.5)
            w_wall = cs['where'].get('wall', 0.4)
            groups = []
            guard = 0
            while items and guard < 40:
                guard += 1
                # how big this group is to be
                x_ = rng.random() * sum(w for _s, w in sizes)
                target = sizes[-1][0]
                for s_, w in sizes:
                    x_ -= w
                    if x_ <= 0:
                        target = s_
                        break
                target = min(target, len(items))
                # where it starts: in a corner or along a wall
                kind = items[0]
                rid = pick(kind)
                if not rid:
                    items[:] = [k for k in items if k != kind]
                    continue
                b = mapdata.object_bounds(db, db.resolve_id(rid))
                if not b:
                    items.pop(0)
                    continue
                front = front_of(db, rid)
                where = 'corner' if rng.random() * (w_corner + w_wall) < w_corner else 'wall'
                done, face = wall_spot(b, front, where)
                if not done:
                    done, face = wall_spot(b, front, 'wall' if where == 'corner' else 'corner')
                if not done:
                    # (the wall slots all taken by furniture: a little way out from a wall, or out on the
                    # floor, as a fifth of the game's groups are)
                    for _try in range(14):
                        side = rng.choice(list(STEP))
                        sx, sy = STEP[side]
                        rot = _turn_to_face(front, (-sx, -sy))
                        box0 = _footprint(b, rot, 0, 0)
                        depth = rng.uniform(0, T * 0.5) if rng.random() < 0.75 else rng.uniform(T * 0.5, T * 1.5)
                        x, y = rng.uniform(inner[0] + 60, inner[2] - 60), rng.uniform(inner[1] + 60, inner[3] - 60)
                        if sx:
                            x = (inner[2] - box0[2] - depth) if sx > 0 else (inner[0] - box0[0] + depth)
                        else:
                            y = (inner[3] - box0[3] - depth) if sy > 0 else (inner[1] - box0[1] + depth)
                        box = _footprint(b, rot, x, y)
                        if fits(box):
                            done, face = (x, y, rot, box), (-sx, -sy)
                            break
                if not done:
                    last_clutter.append((room['name'], kind, 'no spot for a group', len(items)))
                    break
                rec = put(rid, done[0], done[1], done[2], floor=fl, room=room['name'])
                if rec is None:
                    items.pop(0)
                    continue
                taken.append((done[3], fl, fl + 200, False))
                got.append(rid)
                items.pop(0)
                group = [(done[0], done[1], done[2], rec)]
                # the rest of the group, each beside one already standing
                while items and len(group) < target:
                    kind = items[0]
                    rid = pick(kind)
                    if not rid:
                        items.pop(0)
                        continue
                    b = mapdata.object_bounds(db, db.resolve_id(rid))
                    if not b:
                        items.pop(0)
                        continue
                    # beside one of the group: along the wall first, then out into the room, close enough
                    # to touch (the game's own stand about a crate's width apart, origin to origin)
                    near = cs['nn'].get(kind) or cs.get('nn_any') or 60
                    spot = None
                    dirs = [(face[1], -face[0]), (-face[1], face[0]), face, (face[0] + face[1], face[1] - face[0]), (face[0] - face[1], face[1] + face[0])]
                    for _try in range(16):
                        bx, by, brot, br = rng.choice(group)
                        ux, uy = dirs[min(len(dirs) - 1, int(rng.random() ** 2 * len(dirs)))]
                        rot = (brot + rng.choice((0, 0, 0, math.pi / 2, -math.pi / 2)) + rng.uniform(-0.12, 0.12)) % (2 * math.pi)
                        # the two boxes side by side along that way, plus a hand's width now and then
                        fa, fb = _footprint([v * (br['s'] or 1.0) for v in br['b']], brot, 0, 0), _footprint(b, rot, 0, 0)
                        ext = lambda f, u: abs(u[0]) * (f[2] - f[0]) / 2 + abs(u[1]) * (f[3] - f[1]) / 2
                        d = max(near * 0.6, ext(fa, (ux, uy)) + ext(fb, (ux, uy)) + rng.uniform(2, 18)) / math.hypot(ux, uy)
                        x, y = bx + d * ux, by + d * uy
                        box = _footprint(b, rot, x, y)
                        if fits(box):
                            spot = (x, y, rot, box)
                            break
                    if not spot:
                        last_clutter.append((room['name'], kind, 'no spot beside', len(group), target))
                        break                    # (no room beside this group: the next piece starts another)
                    rec = put(rid, spot[0], spot[1], spot[2], floor=fl, room=room['name'])
                    items.pop(0)
                    if rec is None:
                        continue
                    taken.append((spot[3], fl, fl + 200, False))
                    got.append(rid)
                    group.append((spot[0], spot[1], spot[2], rec))
                for _x, _y, _r, rec in group:
                    rec['group'] = len(groups)
                groups.append(len(group))
                last_clutter.append((room['name'], 'group', len(group), target, len(items)))
            return groups

        def rug_at(rug, x, y, along_x, clearings=True, furniture=True):
            """A rug lying at (x, y), its long side along x or y: (x, y, rot, box) if it's free there."""
            rid, rb = rug[0], rug[1]
            long_x = (rb[3] - rb[0]) >= (rb[4] - rb[1])
            rot = 0.0 if long_x == along_x else math.pi / 2
            box = _footprint(rb, rot, x, y)
            # (where the model's middle isn't its origin, put the middle there)
            x, y = x - ((box[0] + box[2]) / 2 - x), y - ((box[1] + box[3]) / 2 - y)
            box = _footprint(rb, rot, x, y)
            if not inside(box) or not rug_free(box, fl):
                return None
            if furniture and not fits(box, clearings):
                return None
            return (x, y, rot, box)

        def place_rug(where, rug_list):
            if where == 'under_table' and tables:
                tb = tables[-1]['box']
                tw, td = tb[2] - tb[0], tb[3] - tb[1]
                # the smallest rug that is bigger than the table all round, or failing that the biggest
                fit = sorted([r for r in rug_list if r[2] >= max(tw, td) + 40 and r[3] >= min(tw, td) + 20], key=lambda r: r[2])
                for rug in (fit or sorted(rug_list, key=lambda r: -r[2]))[:4]:
                    s = rug_at(rug, (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2, tw >= td, furniture=False)
                    if s:
                        return rug, s
            elif where in ('by_bed', 'before') and fronts:
                f = fronts[-1]
                fb, (ix, iy) = f['box'], f['in']
                for rug in sorted(rug_list, key=lambda r: abs(r[2] - 200))[:4]:
                    half_l, half_s = rug[2] / 2, rug[3] / 2
                    if where == 'before':
                        # in front of it, lying across its front
                        mx, my = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
                        reach = (fb[2] - fb[0]) / 2 if ix else (fb[3] - fb[1]) / 2
                        spots = [(mx + ix * (reach + half_s + 8), my + iy * (reach + half_s + 8), iy != 0)]
                    else:
                        # beside the bed, along its long side, where one gets out of it
                        if (fb[2] - fb[0]) >= (fb[3] - fb[1]):
                            spots = [((fb[0] + fb[2]) / 2, fb[3] + half_s + 6, True), ((fb[0] + fb[2]) / 2, fb[1] - half_s - 6, True)]
                        else:
                            spots = [(fb[2] + half_s + 6, (fb[1] + fb[3]) / 2, False), (fb[0] - half_s - 6, (fb[1] + fb[3]) / 2, False)]
                        rng.shuffle(spots)
                    for x, y, ax in spots:
                        s = rug_at(rug, x, y, ax)
                        if s:
                            return rug, s
            elif where == 'runner':
                # a long, narrow rug down the middle of a hall
                along_x = (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min'])
                for rug in sorted([r for r in rug_list if r[2] >= 1.6 * r[3]], key=lambda r: -r[2]):
                    s = rug_at(rug, cx, cy, along_x, clearings=False, furniture=False)
                    if s:
                        return rug, s
            return None

        # what goes in a room like this: the game's own rooms of the kind, once surveyed (roomrules.py),
        # the hand-written recipe until then; the standing lamps the game lights such rooms with
        import roomrules
        fam['lamp'] = roomrules.floor_lamps(db, purpose)
        # (floor clutter goes in groups after the furniture, the way the game stands it, once surveyed)
        cs = roomrules.clusters(db)
        clutter = []
        for kind, count, where in ([] if walls_only else roomrules.recipe(db, purpose, RECIPES[purpose])):
            # (a big room gets more of most things, not more beds, shrines or counters)
            n = count if where in ('centre', 'on_table') or kind in ('rug', 'bed', 'shrine', 'counter', 'chest') else max(1, int(round(count * area_k)))
            if cs and kind in roomsurvey.CLUTTER and where in ('wall', 'corner'):
                clutter += [kind] * n
                continue
            for _ in range(n):
                if kind == 'rug':
                    got_rug = place_rug(where, big_rugs if where != 'by_bed' else all_rugs)
                    if got_rug:
                        rug, (x, y, rot, box) = got_rug
                        if put(rug[0], x, y, rot, floor=fl, flat=True, room=room['name']):
                            rugs.append((box, fl))
                            got.append(rug[0])
                    continue
                rid = pick(kind)
                if not rid:
                    break
                ri = db.resolve_id(rid)
                b = mapdata.object_bounds(db, ri)
                if not b:
                    continue
                front = front_of(db, rid)
                done = None
                face = None
                if where == 'by_bed':
                    # at the foot of the bed (or its side), as far off as the game stands it (roomsurvey pairs);
                    # failing that, by a wall like anything else
                    beds = [f for f in fronts if f.get('kind') == 'bed']
                    pair = roomrules.beside(db, kind, 'bed')
                    if beds and pair:
                        fb = beds[-1]['box']
                        bw, bh = fb[2] - fb[0], fb[3] - fb[1]
                        bx0, by0 = _footprint(b, 0, 0, 0)[2] - _footprint(b, 0, 0, 0)[0], _footprint(b, 0, 0, 0)[3] - _footprint(b, 0, 0, 0)[1]
                        mx, my = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
                        long_x = bw >= bh
                        gap = 12
                        spots = ([(fb[2] + bx0 / 2 + gap, my), (fb[0] - bx0 / 2 - gap, my)] if long_x else
                                 [(mx, fb[3] + by0 / 2 + gap), (mx, fb[1] - by0 / 2 - gap)])
                        if pair['along_x'] < 0.5:            # the game keeps it beside the bed more than at its foot
                            spots = ([(mx, fb[3] + by0 / 2 + gap), (mx, fb[1] - by0 / 2 - gap)] if long_x else
                                     [(fb[2] + bx0 / 2 + gap, my), (fb[0] - bx0 / 2 - gap, my)]) + spots
                        for x, y in spots:
                            rot = 0.0 if long_x else math.pi / 2
                            box = _footprint(b, rot, x, y)
                            if fits(box):
                                done = (x, y, rot, box)
                                break
                    if not done:
                        where = 'wall'
                if where in ('wall', 'corner'):
                    done, face = wall_spot(b, front, where)
                elif where == 'centre':
                    rot = 0.0 if (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min']) else math.pi / 2
                    rot = _turn_to_face(front, (0, -1)) if front else rot
                    face = (0, -1)
                    for dx, dy in ((0, 0), (64, 0), (-64, 0), (0, 64), (0, -64), (128, 128), (-128, -128)):
                        box = _footprint(b, rot, cx + dx, cy + dy)
                        if fits(box):
                            done = (cx + dx, cy + dy, rot, box)
                            break
                elif where == 'by_table' and tables:
                    t = tables[len(got) % len(tables)]
                    tb = t['box']
                    sides = [((tb[0] + tb[2]) / 2, tb[3] + 30, (0, -1)), ((tb[0] + tb[2]) / 2, tb[1] - 30, (0, 1)),
                             (tb[2] + 30, (tb[1] + tb[3]) / 2, (-1, 0)), (tb[0] - 30, (tb[1] + tb[3]) / 2, (1, 0))]
                    rng.shuffle(sides)
                    for x, y, face in sides:
                        rot = _turn_to_face(front, face)
                        box = _footprint(b, rot, x + (-face[0]) * 10, y + (-face[1]) * 10)
                        if fits(box):
                            done = (x + (-face[0]) * 10, y + (-face[1]) * 10, rot, box)
                            break
                elif where == 'on_table' and tables:
                    # (a table set out the game's way is laid already; the scatter is for the others)
                    bare = [t for t in tables if not t.get('dressed')]
                    if not bare:
                        continue
                    t = rng.choice(bare)
                    tb = t['box']
                    for _try in range(8):
                        x = rng.uniform(tb[0] + 15, tb[2] - 15)
                        y = rng.uniform(tb[1] + 15, tb[3] - 15)
                        box = _footprint(b, 0, x, y)
                        if not any(_overlaps(box, o, 0) for o in t['items']):
                            done = (x, y, rng.uniform(0, 2 * math.pi), None)
                            t['items'].append(box)
                            break
                if not done:
                    continue
                # (only wall shelves hang on the wall: a chest or a crate the game keeps up on a shelf or a
                # table stands on the floor here)
                hang = hang_height(db, rid) if where in ('wall', 'corner') and kind in HANGING_KINDS else 0.0
                rec = put(rid, done[0], done[1], done[2], on_top=(where == 'on_table'),
                          hang_from=(fl + hang) if hang > 0 else None, floor=fl, room=room['name'])
                if rec is None:
                    continue
                if done[3] is not None:
                    taken.append((done[3], fl, fl + 200, False))
                got.append(rid)
                # what stands on it, the way the game sets out this very model (books packed along a
                # bookshelf, dishes and a candle on a table, wares on a counter)
                laid = dress(rec, purpose) if kind in DRESSED_KINDS else None
                if kind in ('table', 'counter'):
                    tables.append({'box': done[3], 'items': [], 'dressed': bool(laid)})
                if kind in ('bed', 'shrine', 'counter') and done[3] is not None and face:
                    fronts.append({'box': done[3], 'in': face, 'kind': kind})
        if clutter:
            rng.shuffle(clutter)
            # (mostly one kind to a group, as the game's are: like kinds together)
            if rng.random() > cs.get('mixed', 0.3):
                clutter.sort()
            groups += place_clutter(clutter, cs)
        # a small mat just inside the front door, where people stand as they come in
        if not walls_only and mats and purpose not in ('ruin', 'camp'):
            for o in openings:
                low = o['id'].lower()
                if not (o['type'] == 'DOOR' and (o.get('to') or 'load' in low)) and 'jamb_load' not in low:
                    continue
                ox, oy = o['p'][0], o['p'][1]
                if not (room['x_min'] - 40 <= ox <= room['x_max'] + 40 and room['y_min'] - 40 <= oy <= room['y_max'] + 40) \
                        or abs(span(o)[0] - fl) > 60:
                    continue
                # (the frame marks the doorway's middle; a door's own point is often at its hinge)
                jb = [j for j in openings if 'jamb' in j['id'].lower() and math.hypot(j['p'][0] - ox, j['p'][1] - oy) < 140]
                if jb:
                    ox, oy = jb[0]['p'][0], jb[0]['p'][1]
                edges = {(1, 0): ox - room['x_min'], (-1, 0): room['x_max'] - ox, (0, 1): oy - room['y_min'], (0, -1): room['y_max'] - oy}
                ix, iy = min(edges, key=lambda k: abs(edges[k]))
                ex = room['x_min'] if ix == 1 else room['x_max'] if ix == -1 else ox
                ey = room['y_min'] if iy == 1 else room['y_max'] if iy == -1 else oy
                for rug in sorted(mats, key=lambda r: -r[2]):
                    s = rug_at(rug, ex + ix * (rug[3] / 2 + 30), ey + iy * (rug[3] / 2 + 30), iy != 0, clearings=False)
                    if s and put(rug[0], s[0], s[1], s[2], floor=fl, flat=True, room=room['name']):
                        rugs.append((s[3], fl))
                        got.append(rug[0])
                        break
        if (walls or walls_only) and purpose != 'ruin':      # (nobody hangs tapestries in a ruin)
            got += _decorate(db, room, purpose, T, decor, refs, placed, put, rng, hung)
        report.append({'room': room['name'], 'purpose': purpose, 'placed': len(got)})
    if not placed:
        if walls_only:
            raise EditError('Found no free wall to hang things on, or nothing that hangs on walls in places like this.')
        raise EditError('Could not find fitting furniture for these rooms (nothing similar in the load order?).')
    # walking paths around the new furniture (only where the mod made the paths, or there were none)
    db.sync_project()
    if not any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), [])):
        try:
            import pathgrid
            pathgrid.generate(db, cell_key, note=False)
        except EditError:
            pass
    editing.commit(db, 'Auto-furnished %s (%d things in %d rooms)' % (editing.cell_label(db, cell_key), len(placed),
                                                                      len([r for r in report if r['placed']])))
    # how many of the containers stood here hold something (the game's own filled ones)
    import containersurvey
    filled = sum(1 for r in placed if r['type'] == 'CONT' and (containersurvey.contents(db, r['id']) or {}).get('items'))
    return {'placed': len(placed), 'rooms': report, 'style': style, 'groups': groups, 'filled': filled,
            'containers': sum(1 for r in placed if r['type'] == 'CONT'),
            'borrowed': CULTURE_NAMES.get(fam.get('_borrowed')) if fam.get('_borrowed') else None}
