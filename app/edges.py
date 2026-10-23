"""Naked edges: the continuity of a building, piece by piece, without any kit's tables.

The idea (the user's): a good interior has no naked edge. Every edge of a building piece is met by
another piece's edge, or capped by a closer (a pillar at a wall's end, an addon over a seam), and the
two materials across a met edge are ones the game puts together. The joint and adjacency surveys know
this kit by kit; this knows it for any piece whose mesh can be read, which is what lets a structure the
kit tables never saw be judged (and, later, composed).

The segments of a model (segments): the game's meshes are open shells by design (a floor is one sheet,
a wall two faces with nothing between), so "every open mesh edge" is nearly every edge. The filter that
is kept, settled on the Hlaalu, Gold Coast, Redoran and Velothi pieces in packaging/nexus/naked-edges.md:

  1. an edge with exactly one face on it (vertices welded at WELD);
  2. whose two ends both lie on one of the piece's footprint planes: the six planes of its box, and,
     for a kit's tile piece, the four tile planes at half a tile from its origin (the box of a piece with
     a ledge or a buttress stands proud of its tile) - within PLANE_TOL;
  3. whose face is cut by that plane rather than lying in it (|face normal . plane normal| < IN_PLANE):
     the floor sheet, the inner wall face and the ceiling sheet end at the tile plane, and those ends
     are the edges another piece must continue; a face lying in a footprint plane is the piece's skin
     (the back of a wall) or a flat loose wall with its door hole, and its edges are not ends;
  4. merged into straight runs (same plane, same face normal, same texture, collinear and touching) and
     kept when MIN_LEN or longer (the rest is bevel and trim).

Each segment carries the texture of its face, the face's normal and the edge's outward direction (the
way the face would continue: along the plane's normal for an end). A model's segments are kept in the
Workshop's cache folder (edges_models_v<n>.json, keyed by model path and file size) and read once.

The check of a place (check): every segment of every building piece, in the world, is
  matched   another piece's segment on the same plane and line (MATCH_TOL), its face turned the same
            way, its outward direction opposite: the two faces continue each other (a floor into the
            next floor, a wall face into the next wall face);
  capped    inside a closer's box (pillars, posts, columns, caps, addons, jambs, beams, any narrow tall
            or thin loose piece: fixit's patch pieces), inflated by CAP_PAD; or hidden up to CAP_DEPTH
            behind a one-sided face of another piece (a wall end behind the pillar built into the next
            piece, as the Common sets' 3-way and corner pieces have them);
  seated    lying on another piece's face (SEAT_TOL): a wall's foot on the floor sheet, its top under
            the ceiling, a hall's end profile against a room's wall, an addon on its wall: met by a
            surface rather than an edge (the T-joint every kit is built on);
  below     under the piece's own floor level (the slab's underside, the footings);
  above     over its ceiling level (the roof side);
  outside   unseen: a back face (turned away from the piece's own middle), or standing outside every
            other piece's box with a face of another piece in front of it within VOID_DEPTH (a window
            recess's back behind its wall, the arm of a hall closed by a wall inside the tile plane);
  naked     none of these: an end nothing meets, caps or seats, where a player can see it (an end in
            the void with nothing in front of it looks onto nothing: a hole, and naked).
A segment is met when MET_SHARE of its length is matched, capped or seated. Across every matched pair
the two textures are recorded: the "blends" the game puts across a met edge.

The survey (survey, ready): the check over the game's interiors the convert gate passes, kept under
the load order's signature: per kit and over all, how many segments fall in each class, the naked share
(naked over naked + met), and the blends table with counts. The naked share is what the Continuity term
of the room score (roomscore.py) and the place check's "naked" kind go by: a place is only faulted for
what is worse than the game's own places of its kit.

Nothing here edits a place."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import kits
import mapdata
import nif

VERSION = 1
PLANE_TOL = 3.0        # a vertex this close to a footprint plane lies on it
WELD = 0.05            # vertices this close are one (positions come rounded to 0.01 from the reader)
MIN_LEN = 8.0          # shorter runs are bevel and trim
ISSUE_MIN_LEN = 32.0   # a naked edge shorter than this is counted but gets no marker in the place check
IN_PLANE = 0.7         # |n . plane normal| at or above this: the face lies in the plane, not cut by it
MATCH_TOL = 4.0        # two segments on one plane and line within this meet
MIN_OVERLAP = 6.0      # ... overlapping along the line by at least this
MET_SHARE = 0.6        # a segment is met when this share of its length is matched or capped
CAP_PAD = 6.0          # a closer's box inflated by this caps what lies in it
SEAT_TOL = 2.5         # a point this close to another piece's face lies on it (seated)
SEAT_PAD = 8.0         # ... or this close to the face's edge, on its plane (a floor edge under a wall's foot)
CAP_DEPTH = 48.0       # a point up to this far behind another piece's one-sided face is hidden by it (capped: a wall
                       # end behind the pillar built into the next piece, a floor sheet's edge under a thick wall)
VOID_DEPTH = 160.0     # an end in the void beyond every other piece's box is outside (unseen) only when a face of
                       # another piece stands in front of it within this (the wall closing a hall's arm)
SAMPLES = 5            # points along a segment tested against boxes and faces
CLOSER = re.compile(r'pillar|column|post|endcap|_end(_|\d|$)|cap|arch|jamb|addon|trim|beam|frame|skirt|rail|lintel|buttress|support|corbel|partition')
NOT_PIECE = re.compile(r'^(furn_|flora_|ex_|light_|act_|a_|misc_|com_)|marker|blacksquare|black_square|rug|banner|tapestr|light|fireplace|hearth|forge|counter|shelf|bench|pew|table|chair|bed_')
# (stairs and ramps are laid into a hole in the floor above and rest on the floor below: their ends are
# the stair survey's and the gap finder's business, not edges to be met)
NOT_SUBJECT = re.compile(r'stair|ramp')
MIN_PIECE = 96         # a building piece is at least this across
CLASSES = ('matched', 'capped', 'seated', 'naked', 'below', 'above', 'outside')
MET = ('matched', 'capped', 'seated')
PLACES_LIMIT = 1200    # the survey looks at this many gated places at most

_models = {}           # (cache state) 'path', 'data': {rel: {...}}, 'dirty', 'loaded'
_lock = threading.RLock()
_survey = {}           # 'recs', 'all'
_started = [None]
_running = [False]


# ------------------------------------------------------------------ the segments of one model
def _planes(b, T=None):
    """The footprint planes of a model: [(axis, value, outward sign)] from its box and, for a tile piece,
    its tile's four side planes."""
    out = [(0, b[0], -1), (0, b[3], 1), (1, b[1], -1), (1, b[4], 1), (2, b[2], -1), (2, b[5], 1)]
    if T:
        for ax in (0, 1):
            for sgn in (-1, 1):
                v = sgn * T / 2.0
                if not any(a == ax and abs(val - v) <= PLANE_TOL for a, val, _s in out):
                    out.append((ax, v, sgn))
    return out


def _tex(name):
    if not name:
        return ''
    n = name.replace('\\', '/').lower()
    n = n.rsplit('/', 1)[-1]
    return n.rsplit('.', 1)[0] if '.' in n else n


def segments_from_shapes(shapes, T=None):
    """The boundary segments of a model from its shapes (nif.mesh_from_nif): {'b': box, 'floor_z',
    'ceil_z', 'segs': [{'p': [x0,y0,z0,x1,y1,z1], 'n': [nx,ny,nz], 'o': [ox,oy,oz], 'pl': plane index,
    'tex': name, 'L': length}], 'planes': [(axis, value, sign)]}, or None for an empty model."""
    lo = [1e18] * 3
    hi = [-1e18] * 3
    tris = []                    # (a, b, c, tex) with welded vertex keys and positions
    area_up, area_down = Counter(), Counter()
    for sh in shapes or ():
        p, idx, tex = sh['p'], sh['i'], _tex(sh.get('tex'))
        for k in range(0, len(idx) - 2, 3):
            pts = []
            for j in (idx[k], idx[k + 1], idx[k + 2]):
                v = (p[j * 3], p[j * 3 + 1], p[j * 3 + 2])
                pts.append(v)
                for a in range(3):
                    if v[a] < lo[a]:
                        lo[a] = v[a]
                    if v[a] > hi[a]:
                        hi[a] = v[a]
            a, b, c = pts
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            L = math.sqrt(nx * nx + ny * ny + nz * nz)
            if L < 1e-6:
                continue
            n = (nx / L, ny / L, nz / L)
            if n[2] > 0.9:
                area_up[round(a[2] + 0.0)] += L / 2
            elif n[2] < -0.9:
                area_down[round(a[2] + 0.0)] += L / 2
            tris.append((a, b, c, n, tex))
    if lo[0] > hi[0] or not tris:
        return None
    b = [round(v, 2) for v in lo + hi]
    planes = _planes(b, T)
    # the open edges: one face on them
    key = lambda v: (round(v[0] / WELD), round(v[1] / WELD), round(v[2] / WELD))
    count = Counter()
    for a, b_, c, n, tex in tris:
        ka, kb, kc = key(a), key(b_), key(c)
        for e in ((ka, kb), (kb, kc), (kc, ka)):
            count[frozenset(e)] += 1
    raw = []
    for a, b_, c, n, tex in tris:
        for p0, p1 in ((a, b_), (b_, c), (c, a)):
            if count[frozenset((key(p0), key(p1)))] != 1:
                continue
            # on which footprint plane do both ends lie, with the face cut by it? (an edge on a box corner
            # lies on two planes: the wall face at the piece's outer plane lies IN that one (its skin) and
            # is cut by the tile's side plane (its end); the end is what counts)
            pl = None
            for i, (ax, val, sgn) in enumerate(planes):
                if abs(p0[ax] - val) <= PLANE_TOL and abs(p1[ax] - val) <= PLANE_TOL and abs(n[ax]) < IN_PLANE:
                    pl = i
                    break
            if pl is None:
                continue
            dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            L = math.sqrt(dx * dx + dy * dy + dz * dz)
            if L < 1e-3:
                continue
            d = (dx / L, dy / L, dz / L)
            # outward along the face, away from its inside: d x n
            o = (d[1] * n[2] - d[2] * n[1], d[2] * n[0] - d[0] * n[2], d[0] * n[1] - d[1] * n[0])
            raw.append((pl, tex, n, d, o, p0, p1, L))
    segs = _merge(raw)
    out = {'b': b, 'planes': [list(p) for p in planes], 'segs': segs,
           'floor_z': (max(area_up, key=area_up.get) if area_up else None),
           'ceil_z': (max(area_down, key=area_down.get) if area_down else None)}
    return out


def _merge(raw):
    """Collinear, touching edges on one plane with one face normal and texture, chained into runs."""
    groups = defaultdict(list)
    for r in raw:
        pl, tex, n, d, o, p0, p1, L = r
        # a run's key: plane, texture, the face normal and the line's direction (sign-free)
        dd = d if (d[0], d[1], d[2]) >= (-d[0], -d[1], -d[2]) else (-d[0], -d[1], -d[2])
        nk = (round(n[0], 1), round(n[1], 1), round(n[2], 1))
        dk = (round(dd[0], 2), round(dd[1], 2), round(dd[2], 2))
        # the line: a point's offset perpendicular to the direction (rounded)
        p = p0
        t = p[0] * dd[0] + p[1] * dd[1] + p[2] * dd[2]
        foot = (round(p[0] - t * dd[0], 0), round(p[1] - t * dd[1], 0), round(p[2] - t * dd[2], 0))
        groups[(pl, tex, nk, dk, foot)].append((dd, p0, p1, n, o))
    segs = []
    for (pl, tex, nk, dk, foot), lst in groups.items():
        dd = lst[0][0]
        # project every edge onto the line, as an interval [t0, t1]
        ivs = []
        for _dd, p0, p1, n, o in lst:
            t0 = p0[0] * dd[0] + p0[1] * dd[1] + p0[2] * dd[2]
            t1 = p1[0] * dd[0] + p1[1] * dd[1] + p1[2] * dd[2]
            ivs.append((min(t0, t1), max(t0, t1), n, o, p0))
        ivs.sort(key=lambda x: x[0])
        cur = None
        for t0, t1, n, o, p0 in ivs:
            if cur and t0 <= cur[1] + WELD * 4:
                cur[1] = max(cur[1], t1)
                continue
            if cur:
                segs.append(_seg(cur, dd, pl, tex))
            cur = [t0, t1, n, o, p0]
        if cur:
            segs.append(_seg(cur, dd, pl, tex))
    return [s for s in segs if s['L'] >= MIN_LEN]


def _seg(cur, dd, pl, tex):
    t0, t1, n, o, p0 = cur
    # the base point of the line: p0 moved back along dd to t=0
    tp = p0[0] * dd[0] + p0[1] * dd[1] + p0[2] * dd[2]
    base = (p0[0] - tp * dd[0], p0[1] - tp * dd[1], p0[2] - tp * dd[2])
    a = [round(base[k] + t0 * dd[k], 1) for k in range(3)]
    b = [round(base[k] + t1 * dd[k], 1) for k in range(3)]
    return {'p': a + b, 'n': [round(v, 2) for v in n], 'o': [round(v, 2) for v in o], 'pl': pl, 'tex': tex, 'L': round(t1 - t0, 1)}


# ------------------------------------------------------------------ the model cache
def _cache_path():
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'edges_models_v%d.json' % VERSION)


def _load_models():
    with _lock:
        if _models.get('loaded'):
            return _models
        path = _cache_path()
        data = {}
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            if d.get('v') == VERSION and isinstance(d.get('models'), dict):
                data = d['models']
        except (OSError, ValueError, AttributeError):
            pass
        _models.update(path=path, data=data, dirty=0, loaded=True)
        return _models


def save():
    """Write the model cache when it grew (the same tmp-and-replace dance as the mesh sizes: the survey
    processes and the Workshop share the file)."""
    with _lock:
        m = _models
        if not m.get('loaded') or not m.get('dirty'):
            return
        try:
            try:
                with open(m['path'], encoding='utf-8') as f:
                    d = json.load(f)
                if d.get('v') == VERSION and isinstance(d.get('models'), dict):
                    for k, v in d['models'].items():
                        m['data'].setdefault(k, v)
            except Exception:
                pass
            tmp = '%s.%d.tmp' % (m['path'], os.getpid())
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(json.dumps({'v': VERSION, 'models': m['data']}, separators=(',', ':'), check_circular=False))
            os.replace(tmp, m['path'])
            m['dirty'] = 0
        except OSError:
            try:
                os.remove(tmp)
            except Exception:
                pass


def _size_of(db, rel):
    mi = db.meshes
    try:
        if rel in mi.loose:
            return os.path.getsize(mi.loose[rel])
        if rel in mi.packed:
            return mi.packed[rel][2]
    except Exception:
        pass
    return None


def model_segments(db, model, T=None):
    """The segments of a model (cached): see segments_from_shapes; None when the mesh can't be read."""
    if not model:
        return None
    rel = 'meshes/' + model.lower().replace('\\', '/')
    m = _load_models()
    size = _size_of(db, rel)
    key = '%s|%s|%s' % (rel, size, T or 0)
    with _lock:
        hit = m['data'].get(key)
    if hit is not None:
        return hit or None
    res = None
    try:
        data = db.meshes.read(rel)
        shapes = nif.mesh_from_nif(data, max_verts=60000) if data else None
        res = segments_from_shapes(shapes, T) if shapes else None
    except Exception:
        res = None
    with _lock:
        m['data'][key] = res or {}
        m['dirty'] += 1
        if m['dirty'] >= 50:
            save()
    return res


# ------------------------------------------------------------------ a place
def _tile_of(db, rid):
    """(kit prefix, tile size) when this is a kit's tile piece (an ordinary or a tall one), else (prefix or None, None)."""
    pre = kits.kit_prefix(rid)
    if not pre or pre not in kits.kits(db):
        return pre, None
    kp = kits.kit_pieces(db, pre)
    if not kp or kp.get('sheet_kit'):
        return pre, None
    low = rid.lower()
    if any(p['id'].lower() == low for p in kp['pieces']) or any(p['id'].lower() == low for p in kp.get('tall') or []):
        return pre, kp['tile']
    return pre, None


def _role(db, r):
    """'piece' (segments are read and checked), 'closer' (caps what lies in its box), both ('wall': a thin
    loose piece), or None for anything else placed in the cell."""
    if r['type'] not in ('STAT', 'ACTI') or r.get('ri') is None or not r.get('b'):
        return None
    if abs(r['p'][3]) > 0.05 or abs(r['p'][4]) > 0.05:
        return None                                        # (tilted: not a building piece as the game lays them)
    low = r['id'].lower()
    if NOT_PIECE.search(low):
        return None
    b = r['b']
    w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
    pre, T = _tile_of(db, r['id'])
    if NOT_SUBJECT.search(low):
        return None
    if T:
        return 'piece'
    narrow = (w <= 160 and d <= 160 and h >= 64)
    if CLOSER.search(low) or narrow:
        if max(w, d) >= MIN_PIECE * 2 and not CLOSER.search(low):
            return 'wall'
        return 'closer'
    if not r.get('arch') or max(w, d) < MIN_PIECE:
        return None
    if min(w, d) <= 64 and h >= 64:
        return 'wall'                                      # (a thin loose piece: a wall, a screen; checked and capping)
    return 'piece'


def _world_box(r, pad=0.0):
    b, s = r['b'], r.get('s') or 1.0
    c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
    xs, ys = [], []
    for lx in (b[0] * s, b[3] * s):
        for ly in (b[1] * s, b[4] * s):
            xs.append(r['p'][0] + lx * c + ly * sn)
            ys.append(r['p'][1] - lx * sn + ly * c)
    return (min(xs) - pad, min(ys) - pad, r['p'][2] + b[2] * s - pad, max(xs) + pad, max(ys) + pad, r['p'][2] + b[5] * s + pad)


def _to_world(r, v, vec=False):
    s = 1.0 if vec else (r.get('s') or 1.0)
    c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
    x, y, z = v[0] * s, v[1] * s, v[2] * s
    wx, wy = x * c + y * sn, -x * sn + y * c
    if vec:
        return (wx, wy, z)
    return (r['p'][0] + wx, r['p'][1] + wy, r['p'][2] + z)


def place_segments(db, m):
    """Every building piece of a cell map with its segments in the world: [{'r': ref, 'role', 'segs':
    [{'a', 'b', 'n', 'o', 'tex', 'L', 'ax': the line's axis or None, 'mid'}], 'box', 'floor', 'ceil', 'centre'}]
    and the closers' padded boxes [(box, ref)]."""
    pieces, closers = [], []
    for r in m['refs']:
        role = _role(db, r)
        if not role:
            continue
        if role in ('closer', 'wall'):
            closers.append((_world_box(r, CAP_PAD), r))
        if role == 'closer':
            continue
        pre, T = _tile_of(db, r['id'])
        ms = model_segments(db, db.recs[r['ri']][5], T)
        if not ms:
            continue
        s = r.get('s') or 1.0
        segs = []
        for sg in ms['segs']:
            a = _to_world(r, sg['p'][:3])
            b = _to_world(r, sg['p'][3:])
            n = _to_world(r, sg['n'], vec=True)
            o = _to_world(r, sg['o'], vec=True)
            d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            ax = next((k for k in range(3) if abs(d[k]) >= 0.99 * sg['L'] * s), None)
            w = {'a': a, 'b': b, 'n': n, 'o': o, 'tex': sg['tex'], 'L': sg['L'] * s, 'ax': ax,
                 'mid': ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)}
            w['line'] = _line(w)
            segs.append(w)
        bw = _world_box(r)
        pieces.append({'r': r, 'role': role, 'segs': segs, 'box': bw, 'kit': pre, 'T': T,
                       'floor': (r['p'][2] + ms['floor_z'] * s) if ms.get('floor_z') is not None else None,
                       'ceil': (r['p'][2] + ms['ceil_z'] * s) if ms.get('ceil_z') is not None else None,
                       'centre': ((bw[0] + bw[3]) / 2, (bw[1] + bw[4]) / 2, (bw[2] + bw[5]) / 2)})
    return pieces, closers


GRID = 256.0           # the coarse grid boxes are sorted into for the point tests


def _gkey(p):
    return (int(math.floor(p[0] / GRID)), int(math.floor(p[1] / GRID)))


def _grid_put(grid, box, item):
    for ix in range(int(math.floor(box[0] / GRID)), int(math.floor(box[3] / GRID)) + 1):
        for iy in range(int(math.floor(box[1] / GRID)), int(math.floor(box[4] / GRID)) + 1):
            grid[(ix, iy)].append((box, item))


def _inside(p, box, depth=0.0):
    return (box[0] + depth <= p[0] <= box[3] - depth and box[1] + depth <= p[1] <= box[4] - depth
            and box[2] + depth <= p[2] <= box[5] - depth)


def _samples(sg):
    a, b = sg['a'], sg['b']
    return [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
            for t in [(k + 0.5) / SAMPLES for k in range(SAMPLES)]]


def _line(sg):
    """A segment's line: (unit direction with its sign fixed, the foot of the perpendicular from the
    origin). Collinear segments share both, whichever way they run."""
    a, b = sg['a'], sg['b']
    d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) or 1.0
    d = (d[0] / L, d[1] / L, d[2] / L)
    if d < (-d[0], -d[1], -d[2]):
        d = (-d[0], -d[1], -d[2])
    t = a[0] * d[0] + a[1] * d[1] + a[2] * d[2]
    foot = (a[0] - t * d[0], a[1] - t * d[1], a[2] - t * d[2])
    return d, foot


def _line_key(sg):
    """The bucket a segment's line falls in (its foot, in MATCH_TOL * 2 boxes; a match may sit in a
    neighbouring box)."""
    d, foot = sg['line']
    B = MATCH_TOL * 2
    return (int(math.floor(foot[0] / B)), int(math.floor(foot[1] / B)), int(math.floor(foot[2] / B)))


def _overlap(sa, sb):
    """How much of segment sa lies along sb (the same line, within MATCH_TOL), as an interval of sa's
    parameter t in [0, L], or None."""
    da, fa = sa['line']
    db_, fb = sb['line']
    if abs(da[0] * db_[0] + da[1] * db_[1] + da[2] * db_[2]) < 0.98:
        return None
    if abs(fa[0] - fb[0]) > MATCH_TOL or abs(fa[1] - fb[1]) > MATCH_TOL or abs(fa[2] - fb[2]) > MATCH_TOL:
        return None
    pa = lambda p: p[0] * da[0] + p[1] * da[1] + p[2] * da[2]
    a0, a1 = sorted((pa(sa['a']), pa(sa['b'])))
    b0, b1 = sorted((pa(sb['a']), pa(sb['b'])))
    lo, hi = max(a0, b0), min(a1, b1)
    if hi - lo < MIN_OVERLAP:
        return None
    return (lo - a0, hi - a0)


def _covered(ivs, L):
    """The length covered by a union of intervals in [0, L]."""
    if not ivs:
        return 0.0
    ivs = sorted(ivs)
    tot, cur = 0.0, list(ivs[0])
    for a, b in ivs[1:]:
        if a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            tot += cur[1] - cur[0]
            cur = [a, b]
    tot += cur[1] - cur[0]
    return min(L, tot)


def _dot(u, v):
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


class _Faces:
    """The building's faces, for the seated test: a point on a face of another piece. Built on
    seethrough's scene (its triangles sorted into boxes)."""

    def __init__(self, db, m):
        import seethrough
        self.G = seethrough.G
        self.sc = seethrough.place_scene(db, m)
        self.owner = {}
        for k, (a, b) in self.sc.of_ref.items():
            for n in range(a, b):
                self.owner[n] = k

    def on_face(self, p, own, nseg, depth=None):
        """2 when p lies within SEAT_TOL of a face (seated): another piece's, or this piece's own apart
        from the one the edge belongs to (a face in the edge's own plane: a beam's top under its own
        ceiling sheet, a post's chamfer on its own floor, the T-joints the game's open-shell pieces are
        modelled with); 1 when p stands behind a one-sided face of another piece by up to depth
        (CAP_DEPTH: hidden, a wall end behind the pillar built into the next piece); else 0."""
        G = self.G
        depth = CAP_DEPTH if depth is None else depth
        tris, grid, two = self.sc.tris, self.sc.grid, self.sc.two
        # every box the window round p touches (the point's own box among them: a face that holds p is
        # sorted into that box, whichever way the window's corners fall)
        lo = [int(math.floor((p[k] - depth) / G)) for k in range(3)]
        hi = [int(math.floor((p[k] + depth) / G)) for k in range(3)]
        cells = [(ix, iy, iz) for ix in range(lo[0], hi[0] + 1) for iy in range(lo[1], hi[1] + 1) for iz in range(lo[2], hi[2] + 1)]
        seen = set()
        behind = 0
        for c in cells:
            for n in grid.get(c, ()):
                if n in seen:
                    continue
                seen.add(n)
                x0, y0, z0, ax, ay, az, bx, by, bz = tris[n]
                nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
                L2 = nx * nx + ny * ny + nz * nz
                if L2 < 1e-9:
                    continue
                Ln = math.sqrt(L2)
                sx, sy, sz = p[0] - x0, p[1] - y0, p[2] - z0
                dist = (sx * nx + sy * ny + sz * nz) / Ln
                if dist > SEAT_TOL or dist < -depth:
                    continue
                mine = self.owner.get(n) == own
                if dist < -SEAT_TOL and (mine or two[n]):
                    continue                          # (behind: only another piece's one-sided face hides)
                if mine and abs(nx * nseg[0] + ny * nseg[1] + nz * nseg[2]) / Ln > 0.95:
                    continue                          # (the edge's own face, or another in its plane)
                # barycentric: s = u a + v b (+ w n)
                aa, ab, bb = ax * ax + ay * ay + az * az, ax * bx + ay * by + az * bz, bx * bx + by * by + bz * bz
                sa, sb = sx * ax + sy * ay + sz * az, sx * bx + sy * by + sz * bz
                den = aa * bb - ab * ab
                if abs(den) < 1e-9:
                    continue
                u = (bb * sa - ab * sb) / den
                v = (aa * sb - ab * sa) / den
                inside = u >= -0.02 and v >= -0.02 and u + v <= 1.02
                if not inside:
                    # past the face's edge: still on it (or behind it) when the nearest point of the face,
                    # measured in the face's plane, is within SEAT_PAD (a floor sheet's edge at the foot of
                    # a wall whose face starts a few units up: the Mournhold set's inset walls)
                    cu, cv = max(0.0, u), max(0.0, v)
                    if cu + cv > 1.0:
                        s_ = cu + cv
                        cu, cv = cu / s_, cv / s_
                    qx, qy, qz = x0 + cu * ax + cv * bx, y0 + cu * ay + cv * by, z0 + cu * az + cv * bz
                    d2 = (p[0] - qx) ** 2 + (p[1] - qy) ** 2 + (p[2] - qz) ** 2 - dist * dist
                    inside = d2 <= SEAT_PAD * SEAT_PAD
                if inside:
                    if dist >= -SEAT_TOL:
                        return 2
                    behind = 1
        return behind


_checks = {}           # (cell key, refs hash) -> check result


def _ref_hash(db, cell_key):
    import hashlib
    h = hashlib.blake2b(digest_size=16)
    try:
        refs, _hdr = db.cell_refs(cell_key)
    except Exception:
        return None
    for k in sorted(refs):
        h.update(k.encode('utf-8', 'replace'))
        h.update(refs[k]['subs'] if isinstance(refs[k]['subs'], (bytes, bytearray)) else repr(refs[k]['subs']).encode())
    return h.hexdigest()


def forget(cell_key=None):
    """Drop the kept check results (of one place, or all)."""
    for k in list(_checks):
        if cell_key is None or k[0] == cell_key.lower():
            _checks.pop(k, None)


def check(db, cell_key, m=None, cache=True):
    """Every segment of every building piece in a place, classified: {'pieces': n, 'segments': n,
    'counts': {class: n}, 'lengths': {class: units}, 'naked': [{ref, id, x, y, z, L, tex, n_naked}] per
    piece with a naked edge (the longest's spot), 'blends': {'texA|texB': n}, 'kit': the place's main kit,
    'share': naked / (naked + met) or None, 'per_piece': {ref: {class: n}}, 'items':
    [(class, piece index, segment)] for pictures (a matched segment carries 'mate', the texture across
    it), 'at': [(ref, id, p)] per piece index, 'secs'}. Kept by the place's references' bytes, so an
    unchanged place costs nothing the second time (m given: not kept)."""
    import time
    t0 = time.time()
    key = None
    if cache and m is None:
        hsh = _ref_hash(db, cell_key)
        key = (cell_key.lower(), hsh) if hsh else None
        hit = _checks.get(key) if key else None
        if hit and hit[0] is db.recs:
            return hit[1]
    if m is None:
        m = mapdata.cellmap(db, cell_key)
    out = _check(db, m)
    out['secs'] = round(time.time() - t0, 3)
    if key is not None:
        _checks[key] = (db.recs, out)
        if len(_checks) > 48:
            for k in list(_checks)[:12]:
                _checks.pop(k, None)
    return out


def _check(db, m):
    pieces, closers = place_segments(db, m)
    faces = _Faces(db, m) if pieces else None
    counts, lengths = Counter(), Counter()
    blends = Counter()
    per_piece = {}
    naked = []
    items = []
    # an index of every segment by line, for matching
    index = defaultdict(list)
    for pi, P in enumerate(pieces):
        for sg in P['segs']:
            index[_line_key(sg)].append((pi, sg))
    # the place's kit: the one most of its tile pieces belong to; a sheet kit's place (the Imperial chapel's
    # loose walls on floor sheets) by its pieces' names
    kit_votes = Counter(P['kit'] for P in pieces if P['kit'] and P['T'])
    if not kit_votes:
        known = kits.kits(db)
        kit_votes = Counter(P['kit'] for P in pieces if P['kit'] in known)
    # the building's volume, roughly: every piece's box, a little inflated (a point outside them all is
    # in the void behind the walls, where nobody sees an edge); the closers' boxes; both on a coarse grid
    volume_grid = defaultdict(list)
    for pi, P in enumerate(pieces):
        b = P['box']
        _grid_put(volume_grid, (b[0] - 4, b[1] - 4, b[2] - 4, b[3] + 4, b[4] + 4, b[5] + 4), pi)
    closer_grid = defaultdict(list)
    for box, r in closers:
        _grid_put(closer_grid, box, r)
    for pi, P in enumerate(pieces):
        own = P['r']['k']
        mine = Counter()
        worst = None
        for sg in P['segs']:
            L = sg['L']
            cls = None
            # matched: segments of other pieces on the same line, facing the same way, running the other way
            ivs = []
            mates = []
            kx, ky, kz = _line_key(sg)
            for du in (-1, 0, 1):
                for dv in (-1, 0, 1):
                    for dw in (-1, 0, 1):
                        for pj, sb in index.get((kx + du, ky + dv, kz + dw), ()):
                            if pj == pi:
                                continue
                            if _dot(sg['n'], sb['n']) < 0.5 or _dot(sg['o'], sb['o']) > -0.5:
                                continue
                            ov = _overlap(sg, sb)
                            if ov:
                                ivs.append(ov)
                                mates.append((pj, sb, ov[1] - ov[0]))
            matched = _covered(ivs, L)
            # capped: sample points inside a closer's padded box, or hidden behind another piece's face;
            # seated: on another face
            pts = _samples(sg)
            capped_pts = seated_pts = 0
            if matched < MET_SHARE * L:
                for p in pts:
                    if any(_inside(p, box) for box, _r in closer_grid.get(_gkey(p), ())):
                        capped_pts += 1
                    elif faces is not None:
                        f = faces.on_face(p, own, sg['n'])
                        if f == 2:
                            seated_pts += 1
                        elif f == 1:
                            capped_pts += 1
            capped = L * capped_pts / float(SAMPLES)
            seated = L * seated_pts / float(SAMPLES)
            if matched + capped + seated >= MET_SHARE * L:
                cls = 'matched' if matched >= max(capped, seated) else 'capped' if capped >= seated else 'seated'
                if mates and matched >= MIN_OVERLAP:
                    best = max(mates, key=lambda x: x[2])
                    sg['mate'] = best[1]['tex']
                    pair = sorted((sg['tex'], best[1]['tex']))
                    blends['%s|%s' % (pair[0], pair[1])] += 1
            elif P['floor'] is not None and max(sg['a'][2], sg['b'][2]) <= P['floor'] - 1.0:
                cls = 'below'
            elif P['ceil'] is not None and min(sg['a'][2], sg['b'][2]) >= P['ceil'] + 1.0:
                cls = 'above'
            else:
                c = P['centre']
                away = (sg['mid'][0] - c[0]) * sg['n'][0] + (sg['mid'][1] - c[1]) * sg['n'][1]
                horiz = math.hypot(sg['n'][0], sg['n'][1])
                if horiz > 0.7 and away > 8.0:
                    cls = 'outside'
                else:
                    # in the void beyond every other piece's box, AND hidden behind a face of another piece
                    # (the wall that closes an Imperial 4-way's arm 57 units inside the tile plane, the wall a
                    # window recess is set in): nobody sees it. In the void with nothing in front of it, the
                    # end looks onto nothing: a hole, and naked (a wall piece taken out of a room bares its
                    # neighbours' ends this way)
                    # (the piece's own box always holds its own ends: the others' boxes are the volume beyond)
                    void = sum(1 for p in pts if not any(pj != pi and _inside(p, box) for box, pj in volume_grid.get(_gkey(p), ())))
                    cls = 'naked'
                    if void >= SAMPLES * MET_SHARE and faces is not None:
                        hidden = sum(1 for p in pts if faces.on_face(p, own, sg['n'], VOID_DEPTH) == 1)
                        if hidden >= SAMPLES * MET_SHARE:
                            cls = 'outside'
            counts[cls] += 1
            lengths[cls] += L
            mine[cls] += 1
            items.append((cls, pi, sg))
            if cls == 'naked' and (worst is None or L > worst['L']):
                worst = sg
        per_piece[P['r']['k']] = dict(mine)
        if worst is not None:
            r = P['r']
            naked.append({'ref': r['k'], 'id': r['id'], 'x': round(worst['mid'][0], 1), 'y': round(worst['mid'][1], 1),
                          'z': round(worst['mid'][2], 1), 'L': round(worst['L'], 1), 'tex': worst['tex'], 'n_naked': mine['naked'],
                          'p': r['p']})
    met = sum(counts[c] for c in MET)
    share = (counts['naked'] / float(counts['naked'] + met)) if (counts['naked'] + met) else None
    return {'pieces': len(pieces), 'segments': sum(counts.values()), 'counts': dict(counts),
            'lengths': {k: round(v, 1) for k, v in lengths.items()}, 'naked': naked, 'blends': dict(blends),
            'kit': kit_votes.most_common(1)[0][0] if kit_votes else None, 'share': share, 'per_piece': per_piece,
            'items': items, 'closers': len(closers),
            'at': [(P['r']['k'], P['r']['id'], P['r']['p']) for P in pieces]}


# ------------------------------------------------------------------ the survey of the game's places
def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'edges_survey_%s_v%d.json' % (taste.sig(db), VERSION))


def _game_places(db):
    """The game's interiors the convert gate passes (its own order), without the mod's own cells."""
    import planfrom
    g = planfrom.gated(db)
    mine = set((db.project.cells or {}).keys()) if getattr(db, 'project', None) else set()
    out = []
    for p in g['places']:
        k = p['key']
        if k in mine or k.startswith('#'):
            continue
        try:
            if not kits.game_made(db, k):
                continue
        except Exception:
            continue
        out.append(k)
    return out, g.get('ready')


def survey(db, limit=PLACES_LIMIT):
    """The check over the game's gated interiors: {'places', 'kits': {prefix: {'places', 'pieces',
    'segments', 'counts', 'lengths', 'share', 'blends', 'naked_models': {id: n}}}, 'all': {...}, 'secs'}.
    Kept on disk under the load order's signature."""
    import time
    if _survey.get('recs') is db.recs and _survey.get('all'):
        return _survey['all']
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _survey.update(recs=db.recs, all=saved)
        return saved
    except Exception:
        pass
    t0 = time.time()
    _running[0] = True
    try:
        keys, _ready = _game_places(db)
        per = {}
        allc = {'places': 0, 'pieces': 0, 'segments': 0, 'counts': Counter(), 'lengths': Counter(), 'blends': Counter(), 'naked_models': Counter(), 'cells': []}
        for ck in keys[:limit]:
            try:
                res = check(db, ck)
            except Exception as e:
                print('edge survey, %s: %s' % (ck, e))
                continue
            if not res['pieces']:
                continue
            # (a place of no known kit, Ebonheart's Imperial big halls say, still counts over all)
            buckets = [allc]
            if res['kit']:
                buckets.append(per.setdefault(res['kit'], {'places': 0, 'pieces': 0, 'segments': 0, 'counts': Counter(), 'lengths': Counter(), 'blends': Counter(), 'naked_models': Counter(), 'cells': []}))
            for bucket in buckets:
                bucket['places'] += 1
                bucket['pieces'] += res['pieces']
                bucket['segments'] += res['segments']
                bucket['counts'].update(res['counts'])
                bucket['lengths'].update(res['lengths'])
                bucket['blends'].update(res['blends'])
                for nk in res['naked']:
                    bucket['naked_models'][nk['id'].lower()] += nk['n_naked']
                bucket['cells'].append([ck, res['pieces'], res['counts'].get('naked', 0), sum(res['counts'].get(x, 0) for x in MET)])
        def fin(bk):
            c = bk['counts']
            met = sum(c.get(x, 0) for x in MET)
            nk = c.get('naked', 0)
            return {'places': bk['places'], 'pieces': bk['pieces'], 'segments': bk['segments'], 'counts': dict(c),
                    'lengths': {k: round(v, 1) for k, v in bk['lengths'].items()},
                    'share': round(nk / float(nk + met), 4) if nk + met else None,
                    'per_piece': round(nk / float(bk['pieces']), 3) if bk['pieces'] else None,
                    'blends': dict(bk['blends'].most_common(400)), 'naked_models': dict(bk['naked_models'].most_common(40)),
                    'cells': bk['cells']}
        out = {'places': allc['places'], 'kits': {k: fin(v) for k, v in per.items()}, 'all': fin(allc), 'secs': round(time.time() - t0, 1), 'v': VERSION}
        save()
    finally:
        _running[0] = False
    _survey.update(recs=db.recs, all=out)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


def ready(db):
    """The survey when it's to hand (in memory or on disk), else None with it started in the survey
    process. (Not in learning._SURVEYS yet: see packaging/nexus/naked-edges.md for what adding it costs.)"""
    if _survey.get('recs') is db.recs and _survey.get('all'):
        return _survey['all']
    if _running[0]:
        return None
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    t = _started[0]
    if t is None or not t.is_alive():
        import background
        _started[0] = background.start('which edges the game leaves naked', lambda: survey(db), task=('edges', 'survey', []))
    return None


def game_share(db, prefix):
    """The game's naked share for this kit (every kit's when the kit was seen in under 3 places), or
    None until surveyed."""
    sv = ready(db)
    if not sv:
        return None
    rec = sv['kits'].get(prefix) if prefix else None
    if rec and rec['places'] >= 3 and rec['share'] is not None:
        return rec['share']
    return sv['all'].get('share')


def game_blends(db, prefix):
    """{texA|texB: n} the game puts across met edges in this kit (every kit's when the kit was seen in
    under 3 places), or None until surveyed."""
    sv = ready(db)
    if not sv:
        return None
    rec = sv['kits'].get(prefix) if prefix else None
    if rec and rec['places'] >= 3 and rec['blends']:
        return rec['blends']
    return sv['all'].get('blends')


def issues(db, cell_key, m=None, res=None):
    """The place check's 'naked' findings: one per piece with a naked edge ISSUE_MIN_LEN or longer, at its
    longest naked edge, only when the place's naked share is over twice the game's own places of its kit
    and over half a percent (over 5% when the game's rate for the kit is not known yet). (issues, hidden:
    how many pieces were left out as no worse than the game's, or as slivers)."""
    if res is None:
        res = check(db, cell_key, m)
    out = []
    share = res.get('share')
    if not res['naked'] or share is None:
        return out, 0
    typical = game_share(db, res.get('kit'))
    if typical is None:
        gate = 0.05
    else:
        # (twice the game's share, and never under half a percent: Hlaalu's places read 0.09 %, and a
        # built Hlaalu house with six bare wall ends 250 tall reads 1.1 %)
        gate = max(0.005, 2.0 * typical)
    if share <= gate:
        return out, len(res['naked'])
    hidden = 0
    for nk in res['naked']:
        if nk['L'] < ISSUE_MIN_LEN:
            hidden += 1                               # (a sliver: in the rate, not worth a marker)
            continue
        text = ('%d naked edges of %s: the longest %d long (%s), with nothing meeting or capping it.' % (nk['n_naked'], nk['id'], round(nk['L']), nk['tex'])
                if nk['n_naked'] > 1 else 'A naked edge of %s, %d long (%s): nothing meets or caps it.' % (nk['id'], round(nk['L']), nk['tex']))
        out.append({'kind': 'naked', 'text': text, 'id': nk['id'], 'name': '', 'ref': nk['ref'], 'room': '',
                    'x': nk['x'], 'y': nk['y'], 'z': nk['z'], 'fixes': []})
    return out, hidden


# ------------------------------------------------------------------ for the write-up
def sketch(ms, width=48, plane_axis=None):
    """A model's segments as a text plan (looking down: x across, y up; the z-runs drawn as '|' marks at
    their spot), for the write-up."""
    if not ms or not ms['segs']:
        return '(no segments)'
    b = ms['b']
    sx = (width - 1) / max(1.0, b[3] - b[0])
    h = max(8, int(round((b[4] - b[1]) * sx / 2.0)) + 1)
    grid = [[' '] * width for _ in range(h)]
    def put(x, y, ch):
        i = int(round((x - b[0]) * sx))
        j = int(round((b[4] - y) * sx / 2.0))
        if 0 <= i < width and 0 <= j < h and grid[j][i] in (' ', ch, '.'):
            grid[j][i] = ch
    for sg in ms['segs']:
        p = sg['p']
        if abs(p[3] - p[0]) < 0.5 and abs(p[4] - p[1]) < 0.5:
            put(p[0], p[1], '|')                      # an upright run (a wall end)
            continue
        n = max(2, int(sg['L'] * sx) + 1)
        ch = '-' if abs(p[4] - p[1]) < 0.5 else ':' if abs(p[3] - p[0]) < 0.5 else '/'
        for k in range(n):
            t = k / float(n - 1)
            put(p[0] + (p[3] - p[0]) * t, p[1] + (p[4] - p[1]) * t, ch)
    return '\n'.join(''.join(row).rstrip() for row in grid)


def describe(ms):
    """A model's segments in words, plane by plane, for the write-up."""
    if not ms:
        return 'no mesh'
    names = {(0, -1): 'W (x min)', (0, 1): 'E (x max)', (1, -1): 'S (y min)', (1, 1): 'N (y max)', (2, -1): 'bottom', (2, 1): 'top'}
    by = defaultdict(list)
    for sg in ms['segs']:
        by[sg['pl']].append(sg)
    lines = ['box %s, floor z %s, ceiling z %s, %d segments' % (ms['b'], ms.get('floor_z'), ms.get('ceil_z'), len(ms['segs']))]
    for pl, lst in sorted(by.items()):
        ax, val, sgn = ms['planes'][pl]
        lines.append('  plane %s = %g: %d' % (names.get((ax, sgn), '?'), val, len(lst)))
        for sg in sorted(lst, key=lambda s: -s['L'])[:8]:
            p = sg['p']
            lines.append('    %6.1f long  (%g,%g,%g)-(%g,%g,%g)  n=%s  out=%s  %s' % (sg['L'], p[0], p[1], p[2], p[3], p[4], p[5], sg['n'], sg['o'], sg['tex']))
        if len(lst) > 8:
            lines.append('    ... and %d more' % (len(lst) - 8))
    return '\n'.join(lines)
