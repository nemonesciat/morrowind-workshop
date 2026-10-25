"""The shell survey: the game's interiors against the buildings their doors lead out of.

Project Tamriel's reviewers lay an interior's shell over its exterior building and look for anything
that juts out; "you only have to fit the exterior as well as vanilla ints". This survey measures how
well the game's own interiors fit, so the Workshop can build one that fits as well, and say when one
doesn't.

For every game interior with a load door out to the open air, the building outside is found: the
outside door that leads back in, the exterior piece that door is set into, and the pieces touching it
(outside.py's way, stopping at a neighbour's door). Then, each in its own door frame (origin the door,
+y inward, from the door towards where you arrive inside, +x to the right going in):

  the building  its outline, read from its meshes: the triangles cut by three horizontal planes just
                above the door's sill (40, 100 and 160 up: a window open at one height is wall at
                another), drawn into a GRID raster, the doors' own boxes filled in, and everything the
                open air can't reach by a flood from outside is inside. Roof overhangs, awnings and
                outside stairs are not cut by those planes and are not counted; the box of a one-model
                shell like ex_hlaalu_b_05 would count them all. Its height (top over the sill), and the
                outline again a storey up and two (the stepped Dunmer town houses), the door's place
                along the front;
  the interior  its kit, style, tile, floors, the tiles of each floor (furnish.rooms), the tile at the
                door, the side of the footprint the door is on;
  the overlay   the interior's tiles laid over the outline door on door: the share of the ground floor
                outside it and how far the furthest tile sticks out, the reviewers' test as a number.

learn() turns the pairs into bands per exterior model (MIN_MODEL pairs or more) and per style: the area
ratio, floors by height, how much the game's interiors jut. Kept in the cache folder under the load
order's signature. Nothing here edits a place."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import doors
import kits
import mapdata
import outside
from project import ref_info

VERSION = 3
CELL = 8192
GRID = 32                     # the outline raster, in game units
SLICES = (40, 100, 160)       # heights over the sill the walls are read at
STOREY = 256                  # (a storey up, for the stepped outline: the kits' storeys are 256 to 384)
WALL_CELLS = 3                # two enclosures this many cells apart (a wall's thickness) or less share a wall...
JOIN_CONTACT = 4              # ...when they meet along this many cells (128 units): one building
MIN_MODEL = 3                 # pairs an exterior model needs to have bands of its own
MAX_PIECES = outside.MAX_PIECES
MAX_EXTENT = outside.MAX_EXTENT
# pieces that are never a house's walls
NOT_A_BUILDING = outside.NOT_A_BUILDING + ('fence', 'stair', 'step', 'awning', 'scaffold', 'gate', 'pole', 'ladder',
                                           'crate', 'barrel', 'cart', 'sack', 'stall', 'platform', 'flag')

_cache = {}
_tri_cache = {}


def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'shellsurvey_%s_v%d.json' % (taste.sig(db), VERSION))


# ---------------------------------------------------------------- the outside

def _cell_items(db, ek, memo, bmemo):
    """The things in an exterior cell with their boxes: [{id, low, p, s, b, tag, ri, box, to, k}]."""
    if ek in memo:
        return memo[ek]
    items = []
    try:
        refs, _h = db.cell_refs(ek)
    except Exception:
        refs = {}
    for rk, ref in refs.items():
        rid, pos, s, dead = ref_info(ref['subs'])
        if dead:
            continue
        low = rid.lower()
        if low not in bmemo:
            ri = db.resolve_id(rid)
            bmemo[low] = (mapdata.object_bounds(db, ri), db.recs[ri][0], ri) if ri is not None else (None, None, None)
        b, tag, ri = bmemo[low]
        if not b or tag not in ('STAT', 'DOOR', 'ACTI'):
            continue
        items.append({'id': rid, 'low': low, 'p': pos, 's': s or 1.0, 'b': b, 'tag': tag, 'ri': ri, 'k': rk, 'cell': ek,
                      'box': outside._box(b, pos, s or 1.0),
                      'to': doors.link_of(ref['subs']) if tag == 'DOOR' else None})
    memo[ek] = items
    return items


def near_items(db, x, y, memo=None, bmemo=None):
    """The things in the exterior cells round (x, y) (the cell and its eight neighbours)."""
    memo = {} if memo is None else memo
    bmemo = {} if bmemo is None else bmemo
    gx, gy = int(math.floor(x / CELL)), int(math.floor(y / CELL))
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            out += _cell_items(db, '#%d,%d' % (gx + dx, gy + dy), memo, bmemo)
    return out


def is_building_piece(it):
    low = it['low']
    if it['tag'] != 'STAT' or any(w in low for w in NOT_A_BUILDING):
        return False
    b, s = it['b'], it['s']
    w, d, h = (b[3] - b[0]) * s, (b[4] - b[1]) * s, (b[5] - b[2]) * s
    return max(w, d) < 2400 and h >= 96 and max(w, d) >= 96


def structure(items, seed_box, others=(), seed=None, max_pieces=MAX_PIECES, max_extent=MAX_EXTENT):
    """The building pieces joined to what touches seed_box (a door's box) or to seed (a piece): outside.py's
    grouping (touching boxes, never through a piece that holds another house's door). [] when it runs on
    into the rest of a town."""
    cand = [it for it in items if is_building_piece(it)]
    if seed is not None:
        roots = [seed]
    else:
        roots = [it for it in cand if outside._touch(it['box'], seed_box, 40)]
    if not roots:
        return []
    root = max(roots, key=lambda it: (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1]))
    group, todo = [root], [root]
    doubled = []
    while todo and len(group) < max_pieces:
        c = todo.pop()
        for it in cand:
            if it in group or not outside._touch(it['box'], c['box']):
                continue
            if any(g['low'] == it['low'] and all(abs(g['p'][n] - it['p'][n]) < 1 for n in range(3)) for g in group):
                doubled.append(it)
                continue                   # (the same piece twice in one spot: a copy left behind)
            if any(outside._touch(it['box'], o['box'], 4) for o in others):
                continue
            group.append(it)
            todo.append(it)
            if len(group) >= max_pieces:
                break
    x0 = min(g['box'][0] for g in group)
    y0 = min(g['box'][1] for g in group)
    x1 = max(g['box'][2] for g in group)
    y1 = max(g['box'][3] for g in group)
    if max(x1 - x0, y1 - y0) > max_extent or len(group) >= max_pieces:
        return []
    structure.doubled = doubled
    return group


class Frame:
    """A door's frame: origin at (ox, oy, sill), +y along (ux, uy) (inward), +x to the right going in."""

    def __init__(self, ox, oy, sill, ux, uy):
        d = math.hypot(ux, uy) or 1.0
        self.ox, self.oy, self.z, self.ux, self.uy = ox, oy, sill, ux / d, uy / d

    def to(self, x, y):
        dx, dy = x - self.ox, y - self.oy
        return dx * self.uy - dy * self.ux, dx * self.ux + dy * self.uy

    def back(self, lx, ly):
        return self.ox + lx * self.uy + ly * self.ux, self.oy - lx * self.ux + ly * self.uy

    def yaw(self):
        """The game's turn (clockwise from north) that faces +y."""
        return math.atan2(self.ux, self.uy) % (2 * math.pi)

    def as_dict(self):
        return {'x': round(self.ox, 1), 'y': round(self.oy, 1), 'z': round(self.z, 1), 'ux': round(self.ux, 4), 'uy': round(self.uy, 4)}


def _world_tris(db, it):
    import seethrough
    model = db.recs[it['ri']][5] if it.get('ri') is not None else None
    tris = seethrough.model_tris(db, model)
    R = seethrough._matrix(it['p'][3], it['p'][4], it['p'][5])
    (a, b, c), (d, e, f), (g, h, i) = R
    s = it['s'] or 1.0
    px, py, pz = it['p'][0], it['p'][1], it['p'][2]
    out = []
    for t in tris:
        w = []
        for k in (0, 3, 6):
            x, y, z = t[k] * s, t[k + 1] * s, t[k + 2] * s
            w.append((px + a * x + b * y + c * z, py + d * x + e * y + f * z, pz + g * x + h * y + i * z))
        out.append(w)
    return out


def _cut(tri, h):
    """The segment where a triangle meets the plane z = h, or None."""
    pts = []
    for n in range(3):
        p, q = tri[n], tri[(n + 1) % 3]
        if (p[2] - h) * (q[2] - h) < 0:
            t = (h - p[2]) / (q[2] - p[2])
            pts.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
        elif p[2] == h:
            pts.append((p[0], p[1]))
    return (pts[0], pts[1]) if len(pts) >= 2 else None


def walls_at(db, group, frame, heights, fill=()):
    """The raster cells (in the frame, GRID apart) a building's walls stand in at these heights over the
    sill, with the boxes in fill (doors) drawn in solid: a set of (ix, iy)."""
    wall = set()
    for it in group:
        key = (it['low'], tuple(round(v, 1) for v in it['p']), it['s'])
        tris = _tri_cache.get(key)
        if tris is None:
            tris = _world_tris(db, it)
            if len(_tri_cache) > 400:
                _tri_cache.clear()
            _tri_cache[key] = tris
        for tri in tris:
            zs = (tri[0][2], tri[1][2], tri[2][2])
            lo, hi = min(zs), max(zs)
            for hh in heights:
                h = frame.z + hh
                if not lo < h < hi:
                    continue
                sg = _cut(tri, h)
                if not sg:
                    continue
                (ax, ay), (bx, by) = frame.to(*sg[0]), frame.to(*sg[1])
                n = max(1, int(math.hypot(bx - ax, by - ay) / (GRID / 2.0)))
                for k in range(n + 1):
                    t = k / float(n)
                    wall.add((int(math.floor((ax + (bx - ax) * t) / GRID)), int(math.floor((ay + (by - ay) * t) / GRID))))
    for it in fill:
        b = it['b']
        s = it['s'] or 1.0
        pts = []
        for cx in (b[0], b[3]):
            for cy in (b[1], b[4]):
                wx, wy = outside._world(cx * s, cy * s, it['p'][5])
                pts.append(frame.to(it['p'][0] + wx, it['p'][1] + wy))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        for ix in range(int(math.floor(min(xs) / GRID)), int(math.floor(max(xs) / GRID)) + 1):
            for iy in range(int(math.floor(min(ys) / GRID)), int(math.floor(max(ys) / GRID)) + 1):
                wall.add((ix, iy))
    return wall


def enclosed(wall, pad=3):
    """The cells the open air can't reach from outside the walls' box (walls included): a set, empty
    when the walls leave a way through."""
    if not wall:
        return set()
    xs = [c[0] for c in wall]
    ys = [c[1] for c in wall]
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    seen = {(x0, y0)}
    todo = [(x0, y0)]
    while todo:
        x, y = todo.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if x0 <= nx <= x1 and y0 <= ny <= y1 and (nx, ny) not in seen and (nx, ny) not in wall:
                seen.add((nx, ny))
                todo.append((nx, ny))
    inside = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) not in seen}
    # (a wall's own cells count only round something enclosed: a lone garden wall encloses nothing)
    if not any(c not in wall for c in inside):
        return set()
    return inside


def behind_door(inside, wall, parts=None):
    """Of the enclosures, the one the door opens into (the cells just in from the door at the frame's
    origin), with the walls round it: a house with a second building or a tower behind it has three."""
    room = [c for c in inside if c not in wall]
    if not room:
        return set()
    room_set = set(room)
    seed = min(room, key=lambda c: (abs(c[0]) + abs(c[1] - 2), c[1] < 0))
    if abs(seed[0]) + abs(seed[1] - 2) > 8:
        return inside                          # (no enclosure near the door: keep them all)
    comps, left = [], set(room_set)
    while left:
        c0 = left.pop()
        cc, todo = {c0}, [c0]
        while todo:
            x, y = todo.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in left:
                    left.discard(n)
                    cc.add(n)
                    todo.append(n)
        comps.append(cc)
    comp = next(cc for cc in comps if seed in cc)
    if parts is not None:
        # (which enclosure each room cell is in: the building's parts, for rooms cut along the walls they meet at)
        for n_, cc in enumerate(comps):
            for c_ in cc:
                parts[c_] = n_
    # (and the enclosures it shares a wall with, along at least JOIN_CONTACT cells: the wing, the tower, the
    # next house of a row built as one; not a building standing apart behind it)
    grown = True
    while grown:
        grown = False
        near = {(x + dx, y + dy) for (x, y) in comp for dx in range(-WALL_CELLS, WALL_CELLS + 1) for dy in range(-WALL_CELLS, WALL_CELLS + 1)}
        for cc in comps:
            if cc is comp or cc <= comp:
                continue
            if len(cc & near) >= JOIN_CONTACT:
                comp = comp | cc
                grown = True
    ring = {(x + dx, y + dy) for (x, y) in comp for dx in (-1, 0, 1) for dy in (-1, 0, 1)} & wall
    # (and the walls' thickness: wall cells two deep from the room)
    ring |= {(x + dx, y + dy) for (x, y) in ring for dx in (-1, 0, 1) for dy in (-1, 0, 1)} & wall & inside
    return comp | ring


def outline(db, group, frame, door_items=(), up=0):
    """The building's enclosed outline `up` storeys over the sill: {'cells': set, 'area', 'box': [x0, y0,
    x1, y1] (frame units), 'closed': bool}."""
    hs = tuple(h + up * STOREY for h in SLICES)
    wall = walls_at(db, group, frame, hs, door_items)
    parts = {}
    inside = behind_door(enclosed(wall), wall, parts) if up == 0 else enclosed(wall)
    if not inside:
        return {'cells': set(), 'area': 0, 'box': None, 'closed': False, 'wall': wall}
    xs = [c[0] for c in inside]
    ys = [c[1] for c in inside]
    return {'cells': inside, 'area': len(inside) * GRID * GRID, 'closed': True, 'wall': wall, 'parts': parts,
            'box': [min(xs) * GRID, min(ys) * GRID, (max(xs) + 1) * GRID, (max(ys) + 1) * GRID]}


def box_outline(group, frame):
    """The outline from the pieces' turned boxes (when the meshes leave no closed outline)."""
    cells = set()
    for it in group:
        b, s = it['b'], it['s'] or 1.0
        if it['box'][4] > frame.z + 160 or it['box'][5] < frame.z + 40:
            continue                          # (a roof up above, a footing below)
        corners = []
        for cx, cy in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4])):
            wx, wy = outside._world(cx * s, cy * s, it['p'][5])
            corners.append(frame.to(it['p'][0] + wx, it['p'][1] + wy))
        xs, ys = [p[0] for p in corners], [p[1] for p in corners]
        for ix in range(int(math.floor(min(xs) / GRID)), int(math.floor(max(xs) / GRID)) + 1):
            for iy in range(int(math.floor(min(ys) / GRID)), int(math.floor(max(ys) / GRID)) + 1):
                if _in_poly((ix + 0.5) * GRID, (iy + 0.5) * GRID, corners):
                    cells.add((ix, iy))
    if not cells:
        return {'cells': set(), 'area': 0, 'box': None, 'closed': False}
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return {'cells': cells, 'area': len(cells) * GRID * GRID, 'closed': False,
            'box': [min(xs) * GRID, min(ys) * GRID, (max(xs) + 1) * GRID, (max(ys) + 1) * GRID]}


def _in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / ((by - ay) or 1e-9):
            inside = not inside
    return inside


def style_of_group(group):
    """The style the building's pieces name, weighed by their footprint."""
    c = Counter()
    for it in group:
        st = mapdata.style_of(it['id'])
        if st:
            c[st] += (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1])
    return c.most_common(1)[0][0] if c else None


def describe_building(db, group, frame, door_items=()):
    """What the survey records of a building: outline (ground, a storey up, two up), height, style."""
    g0 = outline(db, group, frame, door_items, 0)
    if not g0['closed']:
        g0 = box_outline(group, frame)
    ups = [outline(db, group, frame, door_items, k) for k in (1, 2)]
    top = max(it['box'][5] for it in group)
    main = max(group, key=lambda it: (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1]) * (it['box'][5] - it['box'][4]))
    return {'main': main['id'].lower(), 'pieces': sorted(it['id'].lower() for it in group), 'style': style_of_group(group),
            'closed': g0['closed'], 'area': g0['area'], 'box': g0['box'], 'height': round(top - frame.z),
            'up_area': [u['area'] for u in ups], 'cells': sorted(g0['cells'])}


# ---------------------------------------------------------------- the inside

def interior_of(db, key):
    """The interior's kit, style, floors and tiles (furnish.rooms on kit tiles only), or None."""
    import furnish
    try:
        info = furnish.rooms(db, key, trace=False)
    except Exception:
        return None
    if not info.get('rooms') or not info.get('tile'):
        return None
    T = info['tile']
    tiles = {}
    for r in info['rooms']:
        for t in r.get('_tiles') or ():
            tiles[(round(t['x'], 1), round(t['y'], 1))] = min(tiles.get((round(t['x'], 1), round(t['y'], 1)), 1e9), r['floor'])
    floors = sorted({round(r['floor'] / 64.0) * 64 for r in info['rooms']})
    per = defaultdict(list)
    for r in info['rooms']:
        f = round(r['floor'] / 64.0) * 64
        for t in r.get('_tiles') or ():
            per[f].append((round(t['x'], 1), round(t['y'], 1)))
    kp = Counter(kits.kit_prefix(r['id']) for r in info['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
    st = Counter(mapdata.style_of(r['id']) for r in info['refs'] if r.get('arch') and mapdata.style_of(r['id']))
    return {'tile': T, 'kit': kp.most_common(1)[0][0] if kp else None, 'style': st.most_common(1)[0][0] if st else None,
            'floors': floors, 'per_floor': {f: sorted(set(v)) for f, v in per.items()}, 'refs': info['refs']}


def _interior_frame(m, door, arrive):
    """The interior door's frame: inward towards where you arrive coming in (the outside door's
    destination), else towards the middle of the place."""
    px, py = door['p'][0], door['p'][1]
    sill = door['p'][2] + (door.get('b') or [0, 0, 0])[2] * (door.get('s') or 1.0)
    if arrive and math.hypot(arrive[0] - px, arrive[1] - py) > 20:
        return Frame(px, py, sill, arrive[0] - px, arrive[1] - py)
    near = [r['p'] for r in m['refs'] if r is not door and 60 < math.hypot(r['p'][0] - px, r['p'][1] - py) < 900]
    if near:
        return Frame(px, py, sill, sum(p[0] for p in near) / len(near) - px, sum(p[1] for p in near) / len(near) - py)
    return Frame(px, py, sill, math.sin(door['p'][5]), math.cos(door['p'][5]))


def overlay(cells, tiles, T, iframe, eframe=None):
    """The interior's ground-floor tiles (world centres in the interior) laid over the building's outline
    (cells in the exterior door's frame), door on door. {'share': share of the tile area outside,
    'jut': furthest any of it sticks out (units), 'cells_out': [frame cells outside]}."""
    if not cells or not tiles:
        return None
    out_cells = set()
    total = 0
    half = T / 2.0
    for (x, y) in tiles:
        cx, cy = iframe.to(x, y)
        for ix in range(int(math.floor((cx - half) / GRID)), int(math.ceil((cx + half) / GRID))):
            for iy in range(int(math.floor((cy - half) / GRID)), int(math.ceil((cy + half) / GRID))):
                total += 1
                if (ix, iy) not in cells:
                    out_cells.add((ix, iy))
    if not total:
        return None
    jut = 0.0
    if out_cells:
        edge = [c for c in cells if any(n not in cells for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)))]
        for c in out_cells:
            d = min(math.hypot(c[0] - e[0], c[1] - e[1]) for e in edge) if edge else 0
            jut = max(jut, d * GRID)
    return {'share': round(len(out_cells) / float(total), 3), 'jut': round(jut), 'cells_out': sorted(out_cells)}


def tiles_in_frame(tiles, frame):
    return [frame.to(x, y) for (x, y) in tiles]


def entrance_side(tiles, T, iframe):
    """Where the door stands on the interior's footprint, in its frame: 'front' (the edge it faces in
    from), 'left', 'right', 'back' or 'middle'."""
    pts = tiles_in_frame(tiles, iframe)
    if not pts:
        return None
    x0, x1 = min(p[0] for p in pts) - T / 2, max(p[0] for p in pts) + T / 2
    y0, y1 = min(p[1] for p in pts) - T / 2, max(p[1] for p in pts) + T / 2
    d = {'front': abs(y0), 'back': abs(y1), 'left': abs(x0), 'right': abs(x1)}
    side, dist = min(d.items(), key=lambda kv: kv[1])
    return side if dist <= T * 0.75 else 'middle'


# ---------------------------------------------------------------- the pairs

def _interiors(db):
    out = []
    for (tag, key), lst in db.by_key.items():
        if tag != 'CELL' or key.startswith('#'):
            continue
        if not kits.game_made(db, key):
            continue
        out.append(key)
    return sorted(out)


def pair(db, key, memo=None, bmemo=None):
    """One game interior against the building outside its door, or None (no door out, no building)."""
    memo = {} if memo is None else memo
    bmemo = {} if bmemo is None else bmemo
    m = mapdata.cellmap(db, key)
    if not m.get('exists') or not m.get('interior'):
        return None
    outs = [r for r in m['refs'] if r['type'] == 'DOOR' and r.get('to') and not r['to']['cell']]
    if not outs:
        return None
    inside = None
    for d in outs:
        to = d['to']
        items = near_items(db, to['x'], to['y'], memo, bmemo)
        back = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'].lower() == key and
                'marker' not in it['low'] and math.hypot(it['p'][0] - to['x'], it['p'][1] - to['y']) < 600]
        if not back:
            continue
        back.sort(key=lambda it: math.hypot(it['p'][0] - to['x'], it['p'][1] - to['y']))
        edoor = back[0]
        ep = edoor['p']
        others = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'] and it['to']['cell'].lower() != key
                  and math.hypot(it['p'][0] - ep[0], it['p'][1] - ep[1]) < MAX_EXTENT]
        group = structure(items, edoor['box'], others)
        if not group:
            continue
        esill = ep[2] + edoor['b'][2] * edoor['s']
        # inward outside: from where you arrive outside (in front of the door) towards the door
        eframe = Frame(ep[0], ep[1], esill, ep[0] - to['x'], ep[1] - to['y'])
        same = [it for it in items if it['tag'] == 'DOOR' and any(outside._touch(it['box'], g['box'], 8) for g in group)]
        bld = describe_building(db, group, eframe, same)
        if inside is None:
            inside = interior_of(db, key)
            if inside is None:
                return None
        arrive = (edoor['to']['x'], edoor['to']['y'])
        iframe = _interior_frame(m, d, arrive)
        g_floor = min(inside['per_floor'], key=lambda f: abs(f - iframe.z)) if inside['per_floor'] else None
        ground = inside['per_floor'].get(g_floor, [])
        T = inside['tile']
        ov = overlay(set(map(tuple, bld['cells'])), ground, T, iframe)
        pts = tiles_in_frame([t for f in inside['per_floor'].values() for t in f], iframe)
        ibox = [min(p[0] for p in pts) - T / 2, min(p[1] for p in pts) - T / 2, max(p[0] for p in pts) + T / 2,
                max(p[1] for p in pts) + T / 2] if pts else None
        areas = {str(f): len(v) * T * T for f, v in inside['per_floor'].items()}
        # how many places lead into this one building (an upstairs flat, a shop beside the house)
        into = {it['to']['cell'].lower() for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell']
                and any(outside._touch(it['box'], g['box'], 8) for g in group)}
        bc = bld.pop('cells')
        return {'key': key, 'name': m.get('name') or key, 'ext_cell': edoor['cell'], 'ext_door': edoor['id'],
                'building': bld, 'into': len(into), 'eframe': eframe.as_dict(), 'iframe': iframe.as_dict(),
                'door_x': round(-bld['box'][0] / float(max(1, bld['box'][2] - bld['box'][0])), 3) if bld['box'] else None,
                'kit': inside['kit'], 'style': inside['style'], 'tile': T, 'floors': len(inside['floors']),
                'floor_z': [round(f - iframe.z) for f in inside['floors']], 'areas': areas,
                'max_area': max(areas.values()) if areas else 0, 'ground_area': len(ground) * T * T,
                'ibox': [round(v) for v in ibox] if ibox else None,
                'entrance': entrance_side(ground or [t for f in inside['per_floor'].values() for t in f], T, iframe),
                'overlay': {'share': ov['share'], 'jut': ov['jut']} if ov else None,
                'outline_cells': len(bc)}
    return None


def survey(db, limit=None, keys=None):
    """{'pairs': [...], 'learnt': learn(pairs)} for the game's interiors (kept on disk)."""
    if keys is None and 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = None
    if keys is None:
        try:
            path = _disk(db)
            with open(path, encoding='utf-8') as f:
                saved = json.load(f)
            saved['learnt'] = learn(saved['pairs'])          # (cheap: the pairs are what is slow)
            _cache['survey'] = (db.recs, saved)
            return saved
        except Exception:
            pass
    memo, bmemo = {}, {}
    pairs = []
    for key in (keys or _interiors(db))[:limit]:
        try:
            p = pair(db, key, memo, bmemo)
        except Exception as e:
            print('shellsurvey %s: %s' % (key, e))
            continue
        if p:
            pairs.append(p)
        if len(memo) > 60:
            memo.clear()
    out = {'version': VERSION, 'pairs': pairs, 'learnt': learn(pairs)}
    if keys is None:
        _cache['survey'] = (db.recs, out)
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(out, f)
            except Exception:
                pass
    return out


def ready(db):
    """The survey when it's to hand; otherwise None, with it started in the background."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    import background
    background.start('how the game\'s interiors fit their buildings', lambda: survey(db), task=('shellsurvey', 'survey', []))
    return None


# ---------------------------------------------------------------- what is learnt

def _q(vals, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    v = sorted(vals)
    if not v:
        return None
    return [round(v[min(len(v) - 1, int(q * len(v)))], 3) for q in qs]


def usable(p):
    """A pair to learn from: one place into its building, a closed outline, a kit interior, and not a
    tomb, cave or ruin (those lie under the landscape, behind a door in a rock: nothing to fit)."""
    import planfrom
    return bool(p.get('into', 1) <= 1 and p['building']['area'] and p['max_area'] and p.get('style') and
                p['style'] not in planfrom.EXCLUDE_STYLES and not planfrom.EXCLUDE_NAME_RE.search(p.get('name') or p['key']))


def family(main):
    """An exterior model's set: ex_hlaalu_b_05 -> ex_hlaalu, t_de_setveloth_x_house_01 -> t_de_setveloth."""
    return outside._family(main)


def ratio(p):
    return p['max_area'] / float(p['building']['area'])


def learn(pairs, skip=None):
    """Bands from the pairs (all but `skip`, a key): per exterior model and per style {'n', 'ratio':
    [p10..p90], 'jut': [..], 'share': [..], 'front': share of doors on the front edge}, and the floors
    by height: [[height bin, typical floors, n]]."""
    use = [p for p in pairs if usable(p) and p['key'] != skip]
    by_model, by_family, by_style = defaultdict(list), defaultdict(list), defaultdict(list)
    for p in use:
        by_model[p['building']['main']].append(p)
        by_family[family(p['building']['main'])].append(p)
        if p['building']['style']:
            by_style[p['building']['style']].append(p)

    def band(lst):
        ov = [p['overlay'] for p in lst if p.get('overlay')]
        return {'n': len(lst), 'ratio': _q([ratio(p) for p in lst]),
                'jut': _q([o['jut'] for o in ov]), 'share': _q([o['share'] for o in ov]),
                'front': round(sum(1 for p in lst if p['entrance'] == 'front') / float(len(lst)), 3),
                'style': Counter(p['style'] for p in lst).most_common(1)[0][0],
                'kit': Counter(p['kit'] for p in lst if p['kit']).most_common(1)[0][0] if any(p['kit'] for p in lst) else None,
                'floors': Counter(p['floors'] for p in lst).most_common(1)[0][0]}
    heights = defaultdict(list)
    for p in use:
        heights[int(p['building']['height'] // 128) * 128].append(p['floors'])
    return {'models': {k: band(v) for k, v in by_model.items() if len(v) >= MIN_MODEL},
            'families': {k: band(v) for k, v in by_family.items() if len(v) >= MIN_MODEL},
            'styles': {k: band(v) for k, v in by_style.items() if len(v) >= 2},
            'all': band(use) if use else None,
            'height_floors': [[h, Counter(v).most_common(1)[0][0], len(v)] for h, v in sorted(heights.items())]}


def predict(learnt, building):
    """From a building alone: {'style', 'kit', 'ratio' band, 'floors', 'from': 'model'|'style'|'all'}."""
    b = learnt['models'].get(building['main'])
    src = 'model'
    if not b:
        b = learnt.get('families', {}).get(family(building['main']))
        src = 'family'
    if not b:
        b = learnt['styles'].get(building.get('style'))
        src = 'style'
    if not b:
        b, src = learnt['all'], 'all'
    floors = None
    hf = learnt['height_floors']
    if hf:
        h = building['height']
        near = min(hf, key=lambda r: (abs(r[0] + 64 - h), -r[2]))
        floors = near[1]
    if src == 'model':
        floors = b['floors'] if floors is None else floors
    return {'style': b['style'], 'kit': b['kit'], 'ratio': b['ratio'], 'floors': floors, 'from': src, 'n': b['n'],
            'jut': b['jut'], 'share': b['share'], 'front': b['front']}


def leave_one_out(pairs):
    """The prediction test: for each usable pair, the bands learnt from all the others. {'n', 'style',
    'area_in_band' (p25..p75), 'floors_within_one', 'front', 'rows'}."""
    use = [p for p in pairs if usable(p)]
    rows = []
    for p in use:
        L = learn(pairs, skip=p['key'])
        pr = predict(L, p['building'])
        r = ratio(p)
        rows.append({'key': p['key'], 'from': pr['from'], 'style_ok': pr['style'] == p['style'],
                     'band_ok': bool(pr['ratio'] and pr['ratio'][1] <= r <= pr['ratio'][3]),
                     'wide_ok': bool(pr['ratio'] and pr['ratio'][0] <= r <= pr['ratio'][4]),
                     'floors_ok': pr['floors'] is not None and abs(pr['floors'] - p['floors']) <= 1,
                     'front': p['entrance'] == 'front'})
    n = float(len(rows) or 1)
    return {'n': len(rows), 'style': round(sum(r['style_ok'] for r in rows) / n, 3),
            'area_in_band': round(sum(r['band_ok'] for r in rows) / n, 3),
            'area_in_wide_band': round(sum(r['wide_ok'] for r in rows) / n, 3),
            'floors_within_one': round(sum(r['floors_ok'] for r in rows) / n, 3),
            'front': round(sum(r['front'] for r in rows) / n, 3), 'rows': rows}


BETHESDA = ('morrowind.esm', 'tribunal.esm', 'bloodmoon.esm')
_src = {}


def source_bands(db):
    """How closely the game's interiors fit their buildings, by who made them: {'bethesda': {'share', 'jut', 'n'},
    'tr': {...}} (p75). Measured 2026-10-24: Bethesda's interiors stick out of their buildings by a median 43% of
    the ground floor (346 units at most), Tamriel Rebuilt's by 24% (192); Bethesda cared less about lining them up."""
    if 'b' in _src and _src['b'][0] is db.recs:
        return _src['b'][1]
    s = ready(db)
    if not s:
        return None
    by = {'bethesda': [], 'tr': []}
    for p in s['pairs']:
        if not usable(p) or not p.get('overlay'):
            continue
        lst = [v for v in db.by_key.get(('CELL', p['key']), []) if v not in db.dead]
        if not lst:
            continue
        src = db.plugins[db.recs[lst[0]][3]]['name'].lower()
        by['bethesda' if src in BETHESDA else 'tr'].append(p['overlay'])
    out = {}
    for k, ov in by.items():
        if ov:
            out[k] = {'share': _q([o['share'] for o in ov])[3], 'jut': _q([o['jut'] for o in ov])[3], 'n': len(ov)}
    _src['b'] = (db.recs, out)
    return out