"""Steep ground clad in the region's rock and cliff pieces, the way the game's gorges, river banks and hilltops are
(cliffsurvey.py has the figures). The user (2026-11-08): with its rock statics a gorge is active and cliff-like; the
naked terrain under them looks like the terrains we generate; and a rock's naked bottom edge is never exposed from
any vantage point.

clad(db, cells, mask, keep, ...) lays, on the steep ground of the cells (slope STEEP or more, or the mask given):
  faces     the region's steep-band pieces at the game's density for that steepness, the big cliff pieces first and
            the smaller filling in, each in a pose the game set such a piece in (turned to its own way downhill), then
            more until the steep ground is as much under rock as the region's own (its cover);
  the lip   smaller pieces on the gentle ground just over the steep ground, at the game's lip density;
  the foot  boulders on the gentle ground just under it;
  banks     pieces along the water's edge at the game's bank density;
  outcrops  on a knoll (a hilltop of KNOLL_RELIEF within KNOLL_REACH) the hilltop recipe: big rocks packed into one
            mass round the top, sunk deep, small rocks at their feet (Lan Orethan's figures, or the region's own).
Every piece is settled by the rim rule: the open edge of its mesh (its naked bottom rim, read from the model and
kept in rockrims_v<n>.json) is sampled in the world, and each sample must lie under the ground or inside another
rock; the piece is sunk until it does, and dropped when that would sink it more than MAX_SINK of its height.
Nothing goes on roads (the land's road textures), where the ground is held under a building (hold), on what the
caller keeps (keep: plots, streets, treads), or under water.

The town builder calls clad(db, cells, mask=<outlines or points>, keep=<its plots and streets>) for the steep
ground inside its outline; the land tools call it after Shape them (Dressing: Rock the steep ground), from Dress
and from the Cliff line."""
import json
import math
import os
import random
import threading
from collections import Counter

import mapdata

VERSION = 2                     # (the rim cache: 2, bottom loops only)
STEEP = 30.0                    # degrees: ground this steep is clad
RIM_MAX = 64                    # rim points kept a model (the farthest apart)
RIM_LOOP = 0.15                 # an open-edge loop is bottom rim when its lowest point is in this lowest share of the height
RIM_PAD = 6.0                   # a settled rim point lies this far under the ground
INSET = 0.18                    # a point inside another rock's turned box, inset by this share of its width, is inside the rock
INSET_TOP = 0.06                # ... and under its top by this share of its height (a stacked piece's rim lies just there)
MAX_SINK = 0.6                  # a piece sunk more than this share of its height is dropped instead
MAX_SINK_SMALL = 0.8            # ... a boulder up to PATCH_SIZE across may go this deep (the game half-buries its feet)
PATCH_FROM = 0.25               # a face piece needing more sinking than this share of its height gets foot boulders first
PATCH_MAX = 420                 # ... at naked points up to this high over the ground
PATCH_TRIES = 3                 # ... at this many points at most
PATCH_SIZE = 700                # a foot boulder is at most this across
TRIES = 3                       # pieces tried at a spot before it is left bare
WALL_SETBACK = 0.3              # a piece that cannot be buried on a face of 40 degrees or more is moved into the slope by this share of its size and tried again
TOWER_MIN = 420                 # a piece may always stand this tall over the ground; taller only up to TOWER_K times the ground's relief within its size
TOWER_K = 1.2
LEAN_FROM = 45.0                # degrees: on ground this steep a share of the pieces lean back against the face
LEAN_SHARE = 0.7
LEAN_K = 0.6                    # ... by this share of the slope's angle, at most LEAN_MAX
LEAN_MAX = 38.0
ROWS_FROM = 45.0                # degrees: faces this steep are laid from the foot upward, each row resting on the one below
BOULDER_H = 1.3                 # a lip, foot or outcrop piece is at most this many times as tall as it is wide, and at most BOULDER_MAX tall
BOULDER_MAX = 1100
KNOLL_PROM = 150                # a knoll's top stands this far over the median of the ground within KNOLL_REACH
KNOLLS_A_CELL = 2
SPACING = {'face': 0.42, 'lip': 0.35, 'foot': 0.35, 'bank': 0.5, 'outcrop': 0.5}  # least centre distance, share of the smaller size
#                               (outcrop: of the mean; lip and foot rocks sit against the faces' edges, as the game's do)
BIG_FIRST = 0.6                 # share of a steep patch's pieces picked among the big ones first
LIP = 384                       # the lip and foot zones reach this far from steep ground
BANK = 384
BANK_SLOPE = 5.0
KNOLL_RELIEF = 300
KNOLL_REACH = 1536
ROAD_PAD = 64.0
ROAD = None                     # (set below: landshapes.KEEP_TEX and townsurvey.ROAD)
_rims = {'loaded': False}
_lock = threading.RLock()       # (reentrant: rim() saves the cache from inside its own hold of the lock)


# ---------------------------------------------------------------- the rim of a rock

def _rims_path():
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'rockrims_v%d.json' % VERSION)


def _load_rims():
    with _lock:
        if _rims['loaded']:
            return _rims
        data = {}
        try:
            with open(_rims_path(), encoding='utf-8') as f:
                d = json.load(f)
            if d.get('v') == VERSION and isinstance(d.get('models'), dict):
                data = d['models']
        except (OSError, ValueError, AttributeError):
            pass
        _rims.update(data=data, dirty=0, loaded=True)
        return _rims


def save_rims():
    with _lock:
        m = _rims
        if not m.get('loaded') or not m.get('dirty'):
            return
        path = _rims_path()
        try:
            try:
                with open(path, encoding='utf-8') as f:
                    d = json.load(f)
                if d.get('v') == VERSION and isinstance(d.get('models'), dict):
                    for k, v in d['models'].items():
                        m['data'].setdefault(k, v)
            except Exception:
                pass
            tmp = '%s.%d.tmp' % (path, os.getpid())
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(json.dumps({'v': VERSION, 'models': m['data']}, separators=(',', ':')))
            os.replace(tmp, path)
            m['dirty'] = 0
        except OSError:
            pass


def _thin(pts, n):
    """n of the points, the farthest apart (the first the lowest)."""
    if len(pts) <= n:
        return pts
    pts = sorted(pts, key=lambda p: p[2])
    keep = [pts[0]]
    d = [(p[0] - keep[0][0]) ** 2 + (p[1] - keep[0][1]) ** 2 + (p[2] - keep[0][2]) ** 2 for p in pts]
    while len(keep) < n:
        i = max(range(len(pts)), key=lambda k: d[k])
        q = pts[i]
        keep.append(q)
        for k, p in enumerate(pts):
            dd = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
            if dd < d[k]:
                d[k] = dd
    return keep


def rim_of_shapes(shapes):
    """The open edge of a mesh (nif.mesh_from_nif's shapes): the vertices of every edge with one face on it, in the
    model's own coordinates, thinned to RIM_MAX; a closed mesh gives the ring of its lowest vertices (the underside
    nobody should see). {'pts': [[x, y, z]...], 'b': box, 'closed': bool} or None."""
    key = lambda v: (round(v[0] / 0.05), round(v[1] / 0.05), round(v[2] / 0.05))
    count, verts = Counter(), {}
    lo, hi = [1e18] * 3, [-1e18] * 3
    for sh in shapes or ():
        p, idx = sh['p'], sh['i']
        for k in range(0, len(idx) - 2, 3):
            ks = []
            for j in (idx[k], idx[k + 1], idx[k + 2]):
                v = (p[j * 3], p[j * 3 + 1], p[j * 3 + 2])
                kk = key(v)
                verts[kk] = v
                ks.append(kk)
                for a in range(3):
                    if v[a] < lo[a]:
                        lo[a] = v[a]
                    if v[a] > hi[a]:
                        hi[a] = v[a]
            for e in ((ks[0], ks[1]), (ks[1], ks[2]), (ks[2], ks[0])):
                count[frozenset(e)] += 1
    if not verts:
        return None
    # the open edges, chained into loops; only the loops whose lowest point lies in the lowest RIM_LOOP of the model
    # are its bottom rim (a rock group's upper boulders have open rims of their own, standing on the lower ones:
    # settling those under the ground buried the whole group, 2026-11-08)
    h = hi[2] - lo[2]
    adj = {}
    for e, n in count.items():
        if n == 1:
            a, b = tuple(e)
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
    seen = set()
    pts = []
    for start in adj:
        if start in seen:
            continue
        comp = [start]
        seen.add(start)
        stack = [start]
        while stack:
            k = stack.pop()
            for nb in adj[k]:
                if nb not in seen:
                    seen.add(nb)
                    comp.append(nb)
                    stack.append(nb)
        if min(verts[k][2] for k in comp) <= lo[2] + RIM_LOOP * h:
            pts += [verts[k] for k in comp]
    closed = not adj
    if closed:
        pts = [v for v in verts.values() if v[2] <= lo[2] + 0.12 * h]
    pts = _thin([list(p) for p in pts], RIM_MAX)
    return {'pts': [[round(c, 1) for c in p] for p in pts], 'b': [round(v, 1) for v in lo + hi], 'closed': closed}


def rim(db, rid):
    """The rim of a placeable's model (cached on disk by model and file size), or None."""
    import nif
    ri = db.resolve_id(rid)
    if ri is None:
        return None
    model = db.recs[ri][5]
    if not model:
        return None
    rel = 'meshes/' + model.lower().replace('\\', '/')
    m = _load_rims()
    try:
        size = os.path.getsize(db.meshes.loose[rel]) if rel in db.meshes.loose else db.meshes.packed[rel][2] if rel in db.meshes.packed else None
    except Exception:
        size = None
    key = '%s|%s' % (rel, size)
    with _lock:
        hit = m['data'].get(key)
    if hit is not None:
        return hit or None
    res = None
    try:
        data = db.meshes.read(rel)
        shapes = nif.mesh_from_nif(data, max_verts=60000) if data else None
        res = rim_of_shapes(shapes) if shapes else None
    except Exception:
        res = None
    with _lock:
        m['data'][key] = res or {}
        m['dirty'] += 1
        full = m['dirty'] >= 40
    if full:
        save_rims()
    return res


# ---------------------------------------------------------------- pieces in the world

def to_world(r, v):
    """A model point in the world for a piece {x, y, z, rx, ry, rz, s} (the game's order, as cliffrocks._lowest)."""
    s = r['s']
    x, y, z = v[0] * s, v[1] * s, v[2] * s
    cx, sx, cy, sy, cz, sz = math.cos(-r['rx']), math.sin(-r['rx']), math.cos(-r['ry']), math.sin(-r['ry']), math.cos(-r['rz']), math.sin(-r['rz'])
    y1, z1 = y * cx - z * sx, y * sx + z * cx
    x2, z2 = x * cy + z1 * sy, -x * sy + z1 * cy
    return r['x'] + x2 * cz - y1 * sz, r['y'] + x2 * sz + y1 * cz, r['z'] + z2


def to_local(r, p):
    """The inverse: a world point in the piece's model frame (unscaled)."""
    dx, dy, dz = p[0] - r['x'], p[1] - r['y'], p[2] - r['z']
    cz, sz = math.cos(-r['rz']), math.sin(-r['rz'])
    x2, y1 = dx * cz + dy * sz, -dx * sz + dy * cz
    cy, sy = math.cos(-r['ry']), math.sin(-r['ry'])
    x, z1 = x2 * cy - dz * sy, x2 * sy + dz * cy
    cx, sx = math.cos(-r['rx']), math.sin(-r['rx'])
    y, z = y1 * cx + z1 * sx, -y1 * sx + z1 * cx
    s = r['s'] or 1.0
    return x / s, y / s, z / s


class Boxes:
    """Placed pieces by their turned boxes, to ask whether a point lies inside one (inset by INSET). Each is filed
    on the 512 grid by the world box of its eight turned corners (a sphere round a 4,000-unit cliff piece reached
    hundreds of grid cells, and the yardstick over a gorge took minutes)."""
    def __init__(self):
        self.grid = {}
        self.items = []
        self.centres = {}

    def add(self, r, b, tag=None):
        if 'rx' not in r:
            r = dict(r, rx=0.0, ry=0.0)
        xs, ys, zs = [], [], []
        for x in (b[0], b[3]):
            for y in (b[1], b[4]):
                for z in (b[2], b[5]):
                    wx, wy, wz = to_world(r, (x, y, z))
                    xs.append(wx)
                    ys.append(wy)
                    zs.append(wz)
        aabb = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        it = (r, b, aabb, tag if tag is not None else r)
        self.items.append(it)
        for gx in range(int(aabb[0] // 512), int(aabb[3] // 512) + 1):
            for gy in range(int(aabb[1] // 512), int(aabb[4] // 512) + 1):
                self.grid.setdefault((gx, gy), []).append(it)
        size = max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0)
        self.centres.setdefault((int(r['x'] // 1024), int(r['y'] // 1024)), []).append((r['x'], r['y'], size))

    def near(self, x, y):
        return self.grid.get((int(x // 512), int(y // 512)), ())

    def covers(self, p, skip=None):
        px, py, pz = p
        for r, b, aabb, tag in self.near(px, py):
            if tag is skip or not (aabb[0] <= px <= aabb[3] and aabb[1] <= py <= aabb[4] and aabb[2] <= pz <= aabb[5]):
                continue
            lx, ly, lz = to_local(r, p)
            w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
            if (b[0] + w * INSET <= lx <= b[3] - w * INSET and b[1] + d * INSET <= ly <= b[4] - d * INSET
                    and b[2] <= lz <= b[5] - h * INSET_TOP):
                return True
        return False

    def too_near(self, x, y, size, k, mean=False):
        """Another piece's centre within k of the smaller of the two sizes (centres within 2,048): a small rock may
        stand at a cliff piece's foot or lip, as the game's do. mean: of the mean of the two (an outcrop's spacing)."""
        cx, cy = int(x // 1024), int(y // 1024)
        for gx in (cx - 2, cx - 1, cx, cx + 1, cx + 2):
            for gy in (cy - 2, cy - 1, cy, cy + 1, cy + 2):
                for ox, oy, osz in self.centres.get((gx, gy), ()):
                    if math.hypot(x - ox, y - oy) < k * ((size + osz) / 2.0 if mean else min(size, osz)):
                        return True
        return False


def exposure(r, rim_, ground_at, boxes=None, skip=None):
    """The rim rule on a piece: {'n': rim points read, 'naked': those above the ground and inside no other piece,
    'max': the highest naked point's height over the ground}."""
    n = naked = 0
    worst = 0.0
    for v in rim_['pts']:
        wx, wy, wz = to_world(r, v)
        g = ground_at(wx, wy)
        if g is None:
            continue
        n += 1
        if wz <= g:
            continue
        if boxes is not None and boxes.covers((wx, wy, wz), skip):
            continue
        naked += 1
        if wz - g > worst:
            worst = wz - g
    return {'n': n, 'naked': naked, 'max': worst}


def naked_points(r, rim_, ground_at, boxes=None, skip=None):
    """The naked rim points of a piece in the world, the highest over the ground first: [(over, x, y, z)]."""
    out = []
    for v in rim_['pts']:
        wx, wy, wz = to_world(r, v)
        g = ground_at(wx, wy)
        if g is None or wz <= g:
            continue
        if boxes is not None and boxes.covers((wx, wy, wz), skip):
            continue
        out.append((wz - g, wx, wy, wz))
    out.sort(reverse=True)
    return out


def settle(r, rim_, ground_at, boxes, h, patch=None, max_sink=MAX_SINK):
    """The piece sunk until no rim point is naked (the ground or another rock over each), or None when that would
    sink it more than max_sink of its height. patch(point): a chance to hide a naked point under a smaller rock first
    (the game's foot boulders), called for the worst points when the sinking needed is more than PATCH_FROM of the
    height; it returns True when the point is hidden now. r is changed in place."""
    sunk = 0.0
    for round_ in range(4):
        nk = naked_points(r, rim_, ground_at, boxes)
        if not nk:
            return r if exposure(r, rim_, ground_at, boxes)['n'] else None
        need = nk[0][0] + RIM_PAD
        if patch is not None and round_ == 0 and need > PATCH_FROM * h:
            hidden = 0
            for over, px, py, pz in nk[:PATCH_TRIES]:
                if over <= PATCH_MAX and patch((px, py, pz)):
                    hidden += 1
            if hidden:
                continue
        if sunk + need > max_sink * h:
            return None
        r['z'] -= need
        sunk += need
    return r if not naked_points(r, rim_, ground_at, boxes) else None


# ---------------------------------------------------------------- the field

def _height(F, x, y):
    import cliffrocks
    return cliffrocks._height(F, x, y)


def _slopes(F):
    w, h, z, d = F.w, F.h, F.z, F.step
    out = [None] * (w * h)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            out[i] = math.degrees(math.atan(math.hypot((z[i + 1] - z[i - 1]) / (2 * d), (z[i + w] - z[i - w]) / (2 * d))))
    return out


def _as_points(F, what):
    """A bytearray over F from: None, a bytearray/list, a callable (x, y) -> bool, or outlines [[x, y], ...] (a list
    of them, or one)."""
    n = F.w * F.h
    if what is None:
        return None
    if isinstance(what, (bytearray, bytes)) or (isinstance(what, list) and what and not isinstance(what[0], (list, tuple))):
        return bytearray(1 if v else 0 for v in what) if len(what) == n else None
    out = bytearray(n)
    if callable(what):
        for i in range(n):
            x, y = F.world(i)
            if what(x, y):
                out[i] = 1
        return out
    polys = what if (what and isinstance(what[0][0], (list, tuple))) else [what]
    for poly in polys:
        if not poly or len(poly) < 3:
            continue
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        m = len(poly)
        for i in F.near(min(xs), min(ys), max(xs), max(ys)):
            x, y = F.world(i)
            c = False
            for k in range(m):
                (ax, ay), (bx, by) = poly[k][:2], poly[(k + 1) % m][:2]
                if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax:
                    c = not c
            if c:
                out[i] = 1
    return out


def _roads(db, F, keys):
    """The points on the cells' road patches (the land's road-like textures), padded by ROAD_PAD."""
    global ROAD
    if ROAD is None:
        import re
        import landshapes
        import townsurvey
        ROAD = re.compile(landshapes.KEEP_TEX.pattern + '|' + townsurvey.ROAD.pattern)
    import landscape
    out = bytearray(F.w * F.h)
    for gx, gy in keys:
        try:
            L = landscape.read(db, gx, gy)
        except Exception:
            continue
        if not L.get('exists') or not L.get('t'):
            continue
        tex = L.get('tex') or {}
        for n_, t in enumerate(L['t']):
            if t and ROAD.search((str(t) + ' ' + str(tex.get(t) or '')).lower()):
                px, py = gx * 8192.0 + (n_ % 16) * 512.0, gy * 8192.0 + (n_ // 16) * 512.0
                for i in F.near(px - ROAD_PAD, py - ROAD_PAD, px + 512 + ROAD_PAD, py + 512 + ROAD_PAD):
                    out[i] = 1
    return out


def _standing(db, F, keys, boxes, rockpad=48.0):
    """What stands in the cells already: rocks go into boxes (a new piece may lean on them); everything's footprint
    is returned as held points (nothing new centred there)."""
    from project import ref_info
    import cliffsurvey
    hold = bytearray(F.w * F.h)
    for gx, gy in keys:
        try:
            refs, _h = db.cell_refs('#%d,%d' % (gx, gy))
        except Exception:
            continue
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead or not rid:
                continue
            ri = db.resolve_id(rid)
            b = mapdata.object_bounds(db, ri) if ri is not None else None
            if not b:
                continue
            sc = sc or 1.0
            low = rid.lower()
            if cliffsurvey.is_piece(low) and db.recs[ri][0] == 'STAT':
                boxes.add({'x': pos[0], 'y': pos[1], 'z': pos[2], 'rx': pos[3], 'ry': pos[4], 'rz': pos[5], 's': sc}, b)
                r = rockpad
            else:
                r = max(b[3] - b[0], b[4] - b[1]) * sc / 2.0 + 96.0
            for i in F.near(pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r):
                hold[i] = 1
    return hold


def _downhill(gx, gy):
    return math.atan2(-gx, -gy)


def _grad(F, x, y):
    d = F.step
    a, b, c, e = _height(F, x + d, y), _height(F, x - d, y), _height(F, x, y + d), _height(F, x, y - d)
    if None in (a, b, c, e):
        return None
    return (a - b) / (2 * d), (c - e) / (2 * d)


def _pick(rng, items, weights):
    t = sum(weights)
    if t <= 0:
        return items[rng.randrange(len(items))]
    u = rng.random() * t
    for it, w in zip(items, weights):
        u -= w
        if u <= 0:
            return it
    return items[-1]


POSE_OFF = 0.5                  # (a learnt pose that would leave the piece's top this share of its height under the
                                #  ground, or its foot that far over it, is not used: the piece is sunk by its
                                #  band's figure instead. Poses learnt over land that lost its cell, p34b)


def _pose(F, it, x, y, g, place, rng, sunk=None):
    """A piece as the game set one of it on such ground: one of its learnt poses turned to this spot's own downhill
    (cliffrocks' way); without poses, its long axis down the slope, leaning with the ground up to its tilt, sunk
    by its band's figure. {rx, ry, rz, z, s}."""
    import cliffrocks
    poses = it.get('poses') or []
    gr = _grad(F, x, y)
    steep = gr is not None and math.degrees(math.atan(math.hypot(*gr))) >= cliffrocks.ASPECT_MIN
    slope = math.degrees(math.atan(math.hypot(*gr))) if gr is not None else 0.0
    if poses:
        here = [p for p in poses if p[5] == place] or poses
        rx, ry, turn, dz, s0, _plc = here[rng.randrange(len(here))]
        tall = it['size'][2] * s0
        foot = dz + it['zmin'] * s0
        if foot + tall < -POSE_OFF * tall or foot > POSE_OFF * tall:
            poses = []
    if poses:
        if turn is None or not steep:
            rz = rng.random() * 2 * math.pi
        else:
            rz = (_downhill(*gr) + turn + (rng.random() - 0.5) * 0.3) % (2 * math.pi)
        s = max(0.5, min(2.0, s0 * (0.9 + rng.random() * 0.2)))
        out = {'rx': rx, 'ry': ry, 'rz': rz, 'z': g + dz * s / s0, 's': round(s, 2)}
        # (on a wall, a share of the pieces lie against the face like a slab instead of standing level: the game's
        # 60-degree ground carries pieces tipped up to 33 degrees (p90), and a level piece there hangs its downhill
        # rim in the air by most of its width. The base follows the slope, so the top tips out over the drop: +rx
        # tips it toward local +Y, +ry toward -X, and downhill lies at -turn from local +Y, i.e. (-sin t, cos t))
        if slope >= LEAN_FROM and turn is not None and rng.random() < LEAN_SHARE:
            a = math.radians(min(LEAN_MAX, slope * LEAN_K))
            t = turn
            out['rx'], out['ry'] = a * math.cos(t), a * math.sin(t)
            out['z'] = g + min(dz, 0.0) * s / s0
        return out
    smin, smax = it.get('smin', 0.9), it.get('smax', 1.3)
    s = smin + rng.random() * max(0.0, smax - smin)
    w, d = it['size'][0], it['size'][1]
    if steep:
        rz = (_downhill(*gr) + (0.0 if d >= w else math.pi / 2) + (rng.random() - 0.5) * 0.5) % (2 * math.pi)
    else:
        rz = rng.random() * 2 * math.pi
    lean = math.radians(it.get('tilt') or 8.0) * rng.random()
    sk = (sunk if sunk is not None else it.get('sink') or 100.0) * s
    out = {'rx': (rng.random() * 2 - 1) * lean, 'ry': (rng.random() * 2 - 1) * lean, 'rz': rz, 'z': g - sk - it['zmin'] * s, 's': round(s, 2)}
    if steep and slope >= LEAN_FROM and rng.random() < LEAN_SHARE:
        a = math.radians(min(LEAN_MAX, slope * LEAN_K))
        t = rz - _downhill(*gr)
        out['rx'], out['ry'] = a * math.cos(t), a * math.sin(t)
    return out


def _boulder(it):
    """A piece that reads as a boulder rather than a wall pillar: no taller than BOULDER_H times its width, and under
    BOULDER_MAX tall (terrain_rock_wg_12 is 1,556 wide and 2,173 tall: a wall piece, and it stood as a tower on a lip)."""
    w, d, h = it['size']
    return h <= BOULDER_H * max(w, d) and h <= BOULDER_MAX


def _bounds(db, rid, memo):
    low = rid.lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(rid))
    return memo[low]


# ---------------------------------------------------------------- the pass

def clad(db, cells, mask=None, keep=None, like='', amount=1.0, seed=None, commit=False, field=None, region_of=None,
         say=None, parts=('face', 'lip', 'foot', 'bank', 'outcrop'), weight=None):
    """The region's rock and cliff pieces over the cells' steep ground (see the module's head). cells: ['gx,gy'] or
    (gx, gy) keys. mask: where to clad (None: all the steep ground; a bytearray over the field; outlines; a callable):
    the steep ground within it. keep: points left alone besides roads, buildings and water (a bytearray, outlines or
    a callable). like: a region whose pieces to use (else each cell's own). amount: 1 as the game. field: (F, inside,
    hold) from the shaping flow (the land as shaped, the plan's holds), else read from the cells as they are; weight:
    points the plan made (0..1), only those are clad when given. region_of(x, y): the region to take after at a spot.
    {'rocks', 'parts': {face, lip, foot, bank, outcrop}, 'dropped', 'steep_points', 'cover', 'naked', 'placed'}."""
    import cliffrocks
    import cliffsurvey
    import editing
    import landrange
    keys = sorted({landrange._key(k) if not isinstance(k, tuple) else k for k in cells or []})
    if not keys:
        return {'rocks': 0, 'parts': {}, 'dropped': 0, 'placed': [], 'zones': bytearray()}
    # (the survey learns in the survey process the first time: nothing is clad until it is to hand, and the caller
    # says so; the plain rock scatter still runs)
    if cliffsurvey.ready(db) is None:
        n0 = (field[0].w * field[0].h) if field else 0
        return {'rocks': 0, 'parts': {}, 'dropped': 0, 'placed': [], 'zones': bytearray(n0), 'why': 'learning'}
    rng = random.Random((int(seed) if seed is not None else random.randrange(1, 1 << 30)) * 6007 + 11)
    boxes = Boxes()
    if field:
        F, inside, hold = field[0], field[1], field[2]
        hold = bytearray(1 if (hold and hold[i] >= 0.5) else 0 for i in range(F.w * F.h)) if hold is not None else bytearray(F.w * F.h)
        stand = _standing(db, F, keys, boxes)
        for i in range(F.w * F.h):
            if stand[i]:
                hold[i] = 1
    else:
        want, F, inside, _hold = cliffrocks.area(db, cells if not isinstance(cells[0], tuple) else ['%d,%d' % k for k in keys])
        hold = _standing(db, F, keys, boxes)
    n = F.w * F.h
    if say:
        say('Reading the steep ground', 0.0)
    sl = _slopes(F)
    maskp = _as_points(F, mask)
    keepp = _as_points(F, keep)
    roads = _roads(db, F, keys)
    free = bytearray(n)
    for i in range(n):
        if not inside[i] or hold[i] or roads[i] or F.z[i] <= 16 or (keepp is not None and keepp[i]) or (weight is not None and weight[i] < 0.5):
            continue
        free[i] = 1
    # the zones: steep (within the mask), lip, foot, bank
    steep = bytearray(n)
    for i in range(n):
        if free[i] and sl[i] is not None and sl[i] >= STEEP and (maskp is None or maskp[i]):
            steep[i] = 1
    lip, foot, bank = bytearray(n), bytearray(n), bytearray(n)
    r = max(1, int(LIP // F.step))
    w = F.w
    for i in range(n):
        if not steep[i]:
            continue
        x0, y0 = i % w, i // w
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                xx, yy = x0 + dx, y0 + dy
                if not (0 <= xx < w and 0 <= yy < F.h) or dx * dx + dy * dy > r * r:
                    continue
                j = yy * w + xx
                if steep[j] or not free[j] or (sl[j] or 0) >= STEEP:
                    continue
                if F.z[j] > F.z[i] + 32:
                    lip[j] = 1
                elif F.z[j] < F.z[i] - 32 and not lip[j]:
                    foot[j] = 1
    if 'bank' in parts:
        rb = max(1, int(BANK // F.step))
        for i in range(n):
            if not free[i] or steep[i] or lip[i] or foot[i] or (sl[i] or 0) < BANK_SLOPE or (maskp is not None and not maskp[i]):
                continue
            x0, y0 = i % w, i // w
            for dy in range(-rb, rb + 1):
                for dx in range(-rb, rb + 1):
                    xx, yy = x0 + dx, y0 + dy
                    if 0 <= xx < w and 0 <= yy < F.h and dx * dx + dy * dy <= rb * rb and F.z[yy * w + xx] <= 0:
                        bank[i] = 1
                        break
                if bank[i]:
                    break
    # whose pieces
    looks = {}
    for gx, gy in keys:
        reg = (like or '').lower() or landrange._region_of(db, gx, gy)
        looks[(gx, gy)] = reg
    if region_of is None:
        region_of = lambda x, y: looks.get((math.floor(x / 8192.0), math.floor(y / 8192.0)), '')
    figs = {}

    def fig(x, y):
        reg = (region_of(x, y) or '').lower()
        if reg not in figs:
            figs[reg] = cliffsurvey.figures(db, reg)
        return figs[reg]
    def ground_at(x, y):
        g = _height(F, x, y)
        return g if g is not None else mapdata.terrain_z(db, x, y)
    bmemo = {}
    placed, dropped = [], [0]
    rejects = {p: Counter() for p in ('face', 'lip', 'foot', 'bank', 'outcrop')}
    taken = bytearray(n)        # points under a new piece's footprint (for the cover share)
    point_area = F.step * F.step

    def footprint(r_, b):
        """The points newly under the piece's footprint."""
        new = []
        rad = max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) * r_['s']
        c, sn = math.cos(r_['rz']), math.sin(r_['rz'])
        for i in F.near(r_['x'] - rad, r_['y'] - rad, r_['x'] + rad, r_['y'] + rad):
            if taken[i]:
                continue
            px, py = F.world(i)
            dx, dy = px - r_['x'], py - r_['y']
            lx, ly = c * dx - sn * dy, sn * dx + c * dy
            if b[0] * r_['s'] <= lx <= b[3] * r_['s'] and b[1] * r_['s'] <= ly <= b[4] * r_['s']:
                taken[i] = 1
                new.append(i)
        return new

    def lay(it, x, y, place, part, spacing, sunk=None, mean=False, feet=None):
        """One piece tried at a spot: posed, spaced, settled by the rim rule; the points it newly covers when it
        went in, else None. feet: the smaller pieces that may hide a naked point of this one (a face's boulders)."""
        b = _bounds(db, it['id'], bmemo)
        rm = rim(db, it['id'])
        g = ground_at(x, y)
        if not b or not rm or g is None or g <= 16:
            rejects[part]['model' if not (b and rm) else 'water'] += 1
            return None
        ps = _pose(F, it, x, y, g, place, rng, sunk)
        size = max(b[3] - b[0], b[4] - b[1]) * ps['s']
        if boxes.too_near(x, y, size, spacing, mean):
            rejects[part]['near'] += 1
            return None
        # (a piece stands no taller over the ground than the ground's own relief round it allows: a 2,000-tall cliff
        # piece is embedded in a gorge wall of that drop, and stood as a tower on a 30-degree valley side, 2026-11-08)
        if True:
            top = ps['z'] + b[5] * ps['s'] - g
            if top > TOWER_MIN:
                lo = hi = g
                for dx, dy in ((size, 0), (-size, 0), (0, size), (0, -size), (size * 0.7, size * 0.7), (-size * 0.7, -size * 0.7), (size * 0.7, -size * 0.7), (-size * 0.7, size * 0.7)):
                    gg = ground_at(x + dx, y + dy)
                    if gg is not None:
                        lo, hi = min(lo, gg), max(hi, gg)
                if top > max(TOWER_MIN, (hi - lo) * TOWER_K):
                    rejects[part]['tall'] += 1
                    return None
        r_ = dict(ps, id=it['id'], x=x, y=y, part=part)

        def patch(p):
            # (a boulder at the naked point, a little out from the piece's middle, settled itself; kept when its
            # body now hides the point)
            px, py, pz = p
            dx, dy = px - x, py - y
            d = math.hypot(dx, dy) or 1.0
            for _t in range(2):
                fi = _pick(rng, feet, [c['n'] for c in feet])
                fb = _bounds(db, fi['id'], bmemo)
                frm = rim(db, fi['id'])
                if not fb or not frm:
                    continue
                fsz = max(fb[3] - fb[0], fb[4] - fb[1])
                fx = px + dx / d * fsz * 0.15 + (rng.random() - 0.5) * 60
                fy = py + dy / d * fsz * 0.15 + (rng.random() - 0.5) * 60
                fg = ground_at(fx, fy)
                if fg is None or fg <= 16:
                    continue
                fp = _pose(F, dict(fi, poses=None), fx, fy, fg, place, rng)
                fr = dict(fp, id=fi['id'], x=fx, y=fy, part='foot')
                if settle(fr, frm, ground_at, boxes, (fb[5] - fb[2]) * fp['s'], max_sink=MAX_SINK_SMALL) is None:
                    continue
                boxes.add(fr, fb)
                if boxes.covers((px, py, pz)):
                    placed.append(fr)
                    footprint(fr, fb)
                    return True
                boxes.items.pop()                              # (it did not reach the point: taken out again)
                for lst in boxes.grid.values():
                    if lst and lst[-1][0] is fr:
                        lst.pop()
                for lst in boxes.centres.values():
                    if lst and lst[-1][0] == fx and lst[-1][1] == fy:
                        lst.pop()
            return False
        h_ = (b[5] - b[2]) * ps['s']
        ms = MAX_SINK_SMALL if size <= PATCH_SIZE else MAX_SINK
        if settle(r_, rm, ground_at, boxes, h_, patch if feet else None, max_sink=ms) is None:
            # (on a steep face: the piece moved into the slope by a share of its size and tried once more, so the
            # downhill rim meets the ground sooner; the game's wall pieces stand set back into the face)
            gr = _grad(F, x, y)
            moved = None
            if gr is not None and math.degrees(math.atan(math.hypot(*gr))) >= 40.0:
                gl = math.hypot(*gr)
                ux, uy = x - gr[0] / gl * size * WALL_SETBACK, y - gr[1] / gl * size * WALL_SETBACK
                ug = ground_at(ux, uy)
                if ug is not None and ug > 16 and not boxes.too_near(ux, uy, size, spacing, mean):
                    ps2 = _pose(F, it, ux, uy, ug, place, rng, sunk)
                    moved = dict(ps2, id=it['id'], x=ux, y=uy, part=part)
                    if settle(moved, rm, ground_at, boxes, h_, patch if feet else None, max_sink=ms) is None:
                        moved = None
            if moved is None:
                dropped[0] += 1
                rejects[part]['sink'] += 1
                return None
            r_ = moved
        boxes.add(r_, b)
        placed.append(r_)
        return footprint(r_, b)

    def weights(items, place):
        return [(c['at'][place] + 0.25) if c.get('at') else c['n'] for c in items]

    # 1. the faces: by 512 patches of steep ground, the band's density; big first
    pts_by = {}
    for i in range(n):
        if steep[i]:
            x, y = F.world(i)
            pts_by.setdefault((int(x // 512), int(y // 512)), []).append(i)
    order = sorted(pts_by)
    rng.shuffle(order)
    if 'face' in parts:
        if say:
            say('Cladding the faces', 0.1)
        for pk in order:
            idx = pts_by[pk]
            cands = []
            want = 0.0
            for i in idx:
                x, y = F.world(i)
                Fg = fig(x, y)
                band = Fg['bands'][cliffsurvey._band(sl[i])]
                dens = band['per_k'] * point_area / 1e6 * amount
                if band['items'] and dens > 0:
                    cands.append((dens, i, band))
                    want += dens
            if not cands:
                continue
            k = int(want) + (1 if rng.random() < want - int(want) else 0)
            picks = []
            for _ in range(k):
                dens, i, band = _pick(rng, cands, [c[0] for c in cands])
                x, y = F.world(i)
                x += (rng.random() - 0.5) * F.step
                y += (rng.random() - 0.5) * F.step
                place = cliffrocks._place_at(F, x, y)
                items = band['items']
                big = [c for c in items if max(c['size'][0], c['size'][1]) >= cliffsurvey.BIG]
                # (the band's big cliff pieces at their share, and laid first: the small fill in)
                pool = big if (big and rng.random() < min(0.9, band.get('big', 0.0))) else items
                it = _pick(rng, pool, weights(pool, place))
                picks.append((max(it['size'][0], it['size'][1]), it, x, y, place, band))
            # (a wall from the foot up, each row resting on the one below; a gentler face the big pieces first)
            if picks and picks[0][5]['from'] >= ROWS_FROM:
                picks.sort(key=lambda p: ground_at(p[2], p[3]) or 0.0)
            else:
                picks.sort(key=lambda p: -p[0])
            for _sz, it, x, y, place, band in picks:
                feet = [c for c in band['items'] if max(c['size'][0], c['size'][1]) <= PATCH_SIZE]
                for _t in range(TRIES):
                    if lay(it, x, y, place, 'face', SPACING['face'], feet=feet) is not None:
                        break
                    it = _pick(rng, band['items'], weights(band['items'], place))
        # the cover: more pieces at bare steep points until the band is as much under rock as the region's own
        if say:
            say('Covering the faces', 0.35)
        groups = {}
        for i in range(n):
            if steep[i]:
                x, y = F.world(i)
                groups.setdefault((region_of(x, y) or '', cliffsurvey._band(sl[i])), []).append(i)
        for (reg, bk), idx in groups.items():
            band = fig(F.world(idx[0])[0], F.world(idx[0])[1])['bands'][bk]
            target = min(0.95, float(band.get('cover') or 0.0) * amount)
            if not band['items'] or target <= 0:
                continue
            bare = [i for i in idx if not taken[i]]
            need = int(target * len(idx)) - (len(idx) - len(bare))
            own = set(idx)
            rng.shuffle(bare)
            for i in bare:
                if need <= 0:
                    break
                if taken[i]:
                    continue
                x, y = F.world(i)
                place = cliffrocks._place_at(F, x, y)
                feet = [c for c in band['items'] if max(c['size'][0], c['size'][1]) <= PATCH_SIZE]
                for _t in range(TRIES):
                    it = _pick(rng, band['items'], weights(band['items'], place))
                    new = lay(it, x, y, place, 'face', SPACING['face'] * 0.8, feet=feet)
                    if new is not None:
                        need -= sum(1 for j in new if j in own)
                        break
    # 2. the lip and the foot, 3. the banks: each zone at its own density, the zone's own pieces
    for zone, pts, place in (('lip', lip, cliffrocks.CREST), ('foot', foot, cliffrocks.FOOT), ('bank', bank, cliffrocks.FOOT)):
        if zone not in parts:
            continue
        if say:
            say('The %s' % zone, 0.55 if zone == 'lip' else 0.65 if zone == 'foot' else 0.75)
        # (lip and foot points under a face piece's box footprint still count: the box overstates the rock, and the
        # game's lip rocks sit on the cliff pieces' edges; the spacing and the rim rule keep them honest)
        idx = [i for i in range(n) if pts[i] and (zone != 'bank' or not taken[i])]
        rng.shuffle(idx)
        for i in idx:
            x, y = F.world(i)
            Z = fig(x, y)['zones'].get(zone)
            if not Z or not Z['items']:
                continue
            if rng.random() >= Z['per_k'] * point_area / 1e6 * amount:
                continue
            x += (rng.random() - 0.5) * F.step
            y += (rng.random() - 0.5) * F.step
            # (not in a learnt pose: a crest pose hangs over the drop, and on the lip's own gentle ground it hung in
            # the air and was dropped; its long axis down the slope, leaning a little, sunk as the zone's are)
            zitems = [c for c in Z['items'] if _boulder(c)] or Z['items']
            for _t in range(TRIES):
                it = _pick(rng, zitems, [c['n'] for c in zitems])
                if lay(dict(it, poses=None, tilt=Z.get('tilt') or 8.0), x, y, place, zone, SPACING[zone], sunk=(Z['sunk'] or [None, None])[1]) is not None:
                    break
    # 4. outcrops on the knolls
    if 'outcrop' in parts:
        if say:
            say('The outcrops', 0.85)
        rk = max(2, int(KNOLL_REACH // F.step))
        knolls = []
        for y0 in range(rk, F.h - rk, 2):
            for x0 in range(rk, F.w - rk, 2):
                i = y0 * w + x0
                if not free[i] or steep[i] or (maskp is not None and not maskp[i]) or (weight is not None and weight[i] < 0.5):
                    continue
                lo = hi = F.z[i]
                top = True
                win = []
                for dy in range(-rk, rk + 1):
                    row = (y0 + dy) * w
                    for dx in range(-rk, rk + 1):
                        v = F.z[row + x0 + dx]
                        if v > hi:
                            top = False
                            break
                        if v < lo:
                            lo = v
                        win.append(v)
                    if not top:
                        break
                # (a knoll rises over most of the ground round it: a plateau's flat top is not eighteen knolls)
                if top and hi - lo >= KNOLL_RELIEF and hi - sorted(win)[len(win) // 2] >= KNOLL_PROM \
                        and not any(abs(kx - x0) <= rk * 1.5 and abs(ky - y0) <= rk * 1.5 for kx, ky, _r in knolls):
                    knolls.append((x0, y0, hi - lo))
        if len(knolls) > KNOLLS_A_CELL * len(keys):
            knolls.sort(key=lambda k: -k[2])
            knolls = knolls[:KNOLLS_A_CELL * len(keys)]
        for kx, ky, relief in knolls:
            cx, cy = F.world(ky * w + kx)
            Fg = fig(cx, cy)
            K = Fg.get('knolls') or cliffsurvey.OUTCROP
            k_n = (K.get('pieces') or [0, 0, 0])[1] or cliffsurvey.OUTCROP['pieces'][1]
            k_rel = K.get('relief') or cliffsurvey.OUTCROP['relief']
            k_sp = K.get('spacing') or cliffsurvey.OUTCROP['spacing']
            k_sunk = K.get('sunk') or cliffsurvey.OUTCROP['sunk']
            k_r = K.get('radius') or cliffsurvey.OUTCROP['radius']
            scale = max(0.5, min(1.4, math.sqrt(relief / float(k_rel))))
            count = max(5, int(round(k_n * scale * amount)))
            radius = k_r * 0.5 * scale
            # (the region's bigger pieces: the steep bands' items, the biggest weighted up; small ones at the feet)
            items = []
            for band in Fg['bands'][cliffsurvey.STEEP_BAND - 1:]:
                items += band['items']
            seen = set()
            items = [it for it in items if not (it['id'].lower() in seen or seen.add(it['id'].lower()))]
            if not items:
                continue
            items = [it for it in items if _boulder(it)] or items
            bigs = [it for it in items if 400 <= max(it['size'][0], it['size'][1]) <= 1600] or items
            smalls = [it for it in items if max(it['size'][0], it['size'][1]) < 400]
            laid = 0
            for _ in range(count * 4):
                if laid >= count:
                    break
                # (a spot round the top, more on the top third)
                ang = rng.random() * 2 * math.pi
                rad = radius * (rng.random() ** (0.5 if rng.random() < 0.6 else 1.0))
                x, y = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad
                fx, fy = int(round((x - F.ox) / F.step)), int(round((y - F.oy) / F.step))
                if not (0 <= fx < w and 0 <= fy < F.h) or not free[fy * w + fx]:
                    continue
                it = _pick(rng, bigs, [c['n'] for c in bigs])
                if lay(dict(it, poses=None), x, y, cliffrocks.CREST, 'outcrop', SPACING['outcrop'], sunk=k_sunk, mean=True) is not None:
                    laid += 1
            if smalls and laid:
                feet_n = int(round(laid * (cliffsurvey.OUTCROP['small'] / float(cliffsurvey.OUTCROP['pieces'][1])) * 1.5))
                for _ in range(feet_n * 3):
                    if feet_n <= 0:
                        break
                    big = placed[-1 - rng.randrange(min(laid, len(placed)))]
                    b = _bounds(db, big['id'], bmemo)
                    rr = max(b[3] - b[0], b[4] - b[1]) * big['s'] / 2.0 + rng.uniform(40, 220)
                    ang = rng.random() * 2 * math.pi
                    x, y = big['x'] + math.cos(ang) * rr, big['y'] + math.sin(ang) * rr
                    it = _pick(rng, smalls, [c['n'] for c in smalls])
                    if lay(dict(it, poses=None), x, y, cliffrocks.FOOT, 'outcrop', 0.3) is not None:
                        feet_n -= 1
    # write
    made = cliffrocks.place(db, placed) if placed else 0
    if made:
        db.sync_project()
        if commit:
            editing.commit(db, 'Clad the steep ground with %d rock%s' % (made, '' if made == 1 else 's'))
    save_rims()
    steep_n = sum(steep)
    zones = bytearray(1 if (steep[i] or lip[i] or foot[i] or bank[i]) else 0 for i in range(n))
    return {'rocks': made, 'parts': dict(Counter(r_['part'] for r_ in placed)), 'dropped': dropped[0], 'steep_points': steep_n,
            'zone_points': {'lip': sum(lip), 'foot': sum(foot), 'bank': sum(bank)}, 'knolls': len(knolls) if 'outcrop' in parts else None,
            'rejects': {p: dict(c) for p, c in rejects.items() if c},
            'cover': round(sum(1 for i in range(n) if steep[i] and taken[i]) / steep_n, 3) if steep_n else None,
            'placed': placed, 'looks': sorted(set(figs)), 'zones': zones}
