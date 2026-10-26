"""Shapes drawn on the land map (packaging/terrain-shaping-proposal.md, stage 2): coastlines, ridgelines, rivers,
valleys, plateaus, lakes and stamps, as layers of a plan over the marked cells. The plan is kept in the project
(project.land['plan']); preview() works it out at every 4th point for the map, apply() at every point and writes
it as one Undo step.

Each layer acts on the ground as the layers before it left it (the land as it is, or the sea bed where there is
none), in order:
  coast    an outline: inside rises to its height over the coast width, outside sinks to the sea bed (-2048, where
           the game's open sea lies); the waterline wanders as the raise does (landrange)
  plateau  an outline: a level top at its height, reached over the cliff width, in steps if it has terraces
  ridge    a line: a range along it, its crest at the height (tapering at the ends), its foot the width out,
           sharp or rounded, with spurs (the width wanders along it)
  river    a line: a bed under the sea along all of it (the game's one water level: its rivers are dug under 0,
           landsurvey: the Odai's bed at Balmora -400), banks rising to the ground over the bank width; a canyon
           keeps them steep
  valley   a line: a trough the depth below the ground, U- or V-shaped
  lake     an outline: a basin under the water line, its shore eased down to it
  stamp    a point: a cone, volcano, caldera, crater, dome or mesa of its radius and height, or a piece of the game's
           own land (cells of it, their shape over their own surroundings) set down at that size and turn
Then rolling ground as rough as the region's on all of the plan's land, the fade at the edge of the marked cells
(nothing changes on an edge shared with a cell not marked), and for apply: steps too steep for the record eased,
textures by the region, things and paths following the ground."""
import math
from collections import Counter

import landrange
import landscape
import mapdata
from editing import EditError, commit, _require_project

KINDS = ('coast', 'plateau', 'ridge', 'river', 'valley', 'lake', 'stamp')
DEFAULTS = {
    'coast': {'height': 600, 'width': 6144, 'wander': 1.0},
    'plateau': {'height': 2000, 'width': 768, 'terraces': 0},
    'ridge': {'height': 3500, 'width': 8192, 'sharp': 0.5, 'spurs': 1.0},
    'river': {'depth': 256, 'width': 256, 'banks': 2048, 'canyon': 0},
    'valley': {'depth': 900, 'width': 4096, 'round': 0.6},
    'lake': {'depth': 400, 'width': 1536},
    'stamp': {'shape': 'volcano', 'radius': 8192, 'height': 4000, 'turn': 0, 'src': None},
}
SHAPES = ('cone', 'volcano', 'caldera', 'crater', 'dome', 'mesa', 'game')
SEA_BED = -2048.0
FLOOR = -2560.0
WATER = ('river', 'lake')


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def plan_of(db):
    p = db.project
    return dict((getattr(p, 'land', None) or {}).get('plan') or {}) if p else {}


def save_plan(db, plan):
    """Keep the plan (layers and settings) in the project: like the marks, a plan rather than a change to the mod."""
    _require_project(db)
    p = db.project
    clean = {'layers': [_clean(L) for L in (plan.get('layers') or [])][:60],
             'rough': max(0.0, min(2.0, float(plan.get('rough', 1.0)))),
             'fade': max(256.0, min(8192.0, float(plan.get('fade', 1024)))),
             'paint': plan.get('paint', True) is not False, 'seed': int(plan.get('seed') or 1),
             'passes': _clean_opts(plan.get('passes'), PASSES), 'dress': _clean_opts(plan.get('dress'), DRESS),
             'protect': _clean_opts(plan.get('protect'), PROTECT)}
    p.land = dict(p.land or {}, plan=clean)
    p.save()
    return clean


# stage 3 and 4 settings (landpasses, landdress), with their defaults
PASSES = {'detail': True, 'detail_k': 1.0, 'settle': True, 'angle': 0.0, 'gullies': 0.0, 'terraces': False, 'tstep': 256.0,
          'tsharp': 0.6, 'tslope': 20.0}
DRESS = {'variety': -1.0, 'tints': True, 'seams': True, 'hollows': True, 'shade': 1.0, 'region': '', 'assign': False}


def _clean_opts(d, base):
    out = dict(base)
    for k, v in (d or {}).items():
        if k not in base:
            continue
        if isinstance(base[k], bool):
            out[k] = bool(v)
        elif isinstance(base[k], float):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
        else:
            out[k] = str(v or '')[:64]
    return out


def _clean(L):
    kind = L.get('kind')
    if kind not in KINDS:
        raise EditError('Unknown shape "%s".' % kind)
    pts = [[float(a), float(b)] for a, b in (L.get('pts') or [])][:400]
    need = 1 if kind == 'stamp' else 3 if kind in ('coast', 'plateau', 'lake') else 2
    if len(pts) < need:
        raise EditError('A %s needs at least %d point%s.' % (kind, need, '' if need == 1 else 's'))
    prm = dict(DEFAULTS[kind])
    for k, v in (L.get('p') or {}).items():
        if k in prm:
            prm[k] = v
    return {'id': str(L.get('id') or ''), 'kind': kind, 'name': str(L.get('name') or '')[:60], 'on': L.get('on', True) is not False,
            'pts': pts, 'p': prm}


# ---------- the working grid: every s-th point of the stitched cells ----------

class Field:
    def __init__(self, G, s):
        self.G, self.s = G, s
        self.w, self.h = (G.w - 1) // s + 1, (G.h - 1) // s + 1
        self.z = [G.z[(y * s) * G.w + x * s] for y in range(self.h) for x in range(self.w)]
        self.ox, self.oy = G.x0 * 64 * 128.0, G.y0 * 64 * 128.0
        self.step = 128.0 * s

    def world(self, i):
        return self.ox + (i % self.w) * self.step, self.oy + (i // self.w) * self.step

    def near(self, x0, y0, x1, y1):
        """Indices of the points within a world box."""
        ix0 = max(0, int(math.floor((x0 - self.ox) / self.step)))
        ix1 = min(self.w - 1, int(math.ceil((x1 - self.ox) / self.step)))
        iy0 = max(0, int(math.floor((y0 - self.oy) / self.step)))
        iy1 = min(self.h - 1, int(math.ceil((y1 - self.oy) / self.step)))
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                yield iy * self.w + ix


def _line_dist(F, pts, reach, closed=False):
    """{point: (distance to the line, distance along it)} for points within reach of a polyline."""
    out = {}
    segs = list(zip(pts, pts[1:] + ([pts[0]] if closed else [])))
    along = 0.0
    for (ax, ay), (bx, by) in segs:
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        L = math.sqrt(L2)
        for i in F.near(min(ax, bx) - reach, min(ay, by) - reach, max(ax, bx) + reach, max(ay, by) + reach):
            x, y = F.world(i)
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
            if d <= reach and (i not in out or d < out[i][0]):
                out[i] = (d, along + t * L)
        along += L
    return out, along


def _inside(F, pts):
    """Set of points inside a closed outline (even-odd)."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    out = set()
    n = len(pts)
    for i in F.near(min(xs), min(ys), max(xs), max(ys)):
        x, y = F.world(i)
        c = False
        for k in range(n):
            (ax, ay), (bx, by) = pts[k], pts[(k + 1) % n]
            if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                c = not c
        if c:
            out.add(i)
    return out


def _outline(F, L, reach):
    """(inside set, {point: signed distance to the outline, + inside}) within reach of it, and the inside beyond."""
    ins = _inside(F, L['pts'])
    near, _ = _line_dist(F, L['pts'], reach, closed=True)
    sd = {i: (d if i in ins else -d) for i, (d, _a) in near.items()}
    for i in ins:
        if i not in sd:
            sd[i] = reach
    return ins, sd


# ---------- the layers ----------

def _coast(F, L, seed):
    P = L['p']
    width, height, wander = float(P['width']), float(P['height']), float(P['wander'])
    ins, sd = _outline(F, L, width * 1.6)
    for i, d in sd.items():
        x, y = F.world(i)
        e = d + (landrange.noise(x, y, seed + 7, width * 0.45 * wander) * min(1.0, abs(d) / 1024.0) if wander else 0.0)
        # (the waterline at the outline, full height a coast width in, the sea bed a coast width out to sea)
        if e >= 0:
            F.z[i] = max(F.z[i], -64 + (height + 64) * _smooth(e / width))
        else:
            # (the shelf out to sea is the coast's own: no wall where the old sea bed met the shore)
            F.z[i] = -64 + (SEA_BED + 64) * _smooth(-e / width)
    # (the rest of the plan's area, out beyond the coast: the sea bed)
    for i in range(len(F.z)):
        if i not in sd and i not in ins:
            F.z[i] = min(F.z[i], SEA_BED)


def _plateau(F, L, seed):
    P = L['p']
    top, cliff, T = float(P['height']), max(128.0, float(P['width'])), int(P['terraces'] or 0)
    ins, sd = _outline(F, L, cliff)
    for i, d in sd.items():
        if d <= 0:
            continue
        s = min(1.0, d / cliff)
        if T > 0:
            t = s * T
            s = (math.floor(t) + _smooth(min(1.0, (t - math.floor(t)) * 3))) / T
        else:
            s = _smooth(s)
        old = F.z[i]
        if top > old:
            F.z[i] = old + (top - old) * s


def _ridge(F, L, seed):
    P = L['p']
    peak, W, sharp, spurs = float(P['height']), max(512.0, float(P['width'])), float(P['sharp']), float(P['spurs'])
    near, total = _line_dist(F, L['pts'], W * 1.5)
    for i, (d, a) in near.items():
        x, y = F.world(i)
        w = W * (1 + 0.45 * spurs * landrange.noise(x, y, seed + 31, 1.0)) if spurs else W
        if d >= w:
            continue
        lin = 1 - d / w
        p = sharp * lin ** 1.6 + (1 - sharp) * _smooth(lin)      # (sharp: a knife-edge crest; 0: rounded)
        taper = _smooth(min(a, total - a) / max(1.0, W)) if total > 2 * W else _smooth(min(a, total - a) / max(1.0, total / 2))
        crest = peak * (0.35 + 0.65 * taper)
        old = F.z[i]
        if crest > old:
            F.z[i] = old + (crest - old) * p


def _river(F, L, seed):
    P = L['p']
    bed, bw, banks, canyon = -abs(float(P['depth'])), float(P['width']), max(256.0, float(P['banks'])), bool(P['canyon'])
    near, _ = _line_dist(F, L['pts'], bw + banks)
    for i, (d, _a) in near.items():
        old = F.z[i]
        if d <= bw:
            F.z[i] = min(old, bed)
            continue
        t = min(1.0, (d - bw) / banks)
        # (the banks climb out of the water quickly and ease off towards the valley sides: a river's water a few
        # hundred units wide, as the Odai's; a canyon's walls steeper still)
        s = t ** 0.3 if canyon else 1 - (1 - t) ** 2.2
        F.z[i] = min(old, bed + (old - bed) * s)


def _valley(F, L, seed):
    P = L['p']
    depth, W, rnd = float(P['depth']), max(512.0, float(P['width'])), float(P['round'])
    near, _ = _line_dist(F, L['pts'], W)
    for i, (d, _a) in near.items():
        t = d / W
        u = 1 - _smooth(t)                       # (U: flat-bottomed and rounded)
        v = 1 - t                                # (V: straight sides)
        old = F.z[i]
        # (a valley stays dry: its floor keeps a third of the ground's height over the water at least, unless the
        # ground was under it already; a valley at sea level is a flooded marsh, which a river or lake makes)
        floor = min(old, 48.0 + 0.3 * max(0.0, old - 48.0))
        F.z[i] = max(old - depth * (rnd * u + (1 - rnd) * v), floor)


def _lake(F, L, seed):
    P = L['p']
    depth, shore = abs(float(P['depth'])), max(256.0, float(P['width']))
    _ins, sd = _outline(F, L, shore)
    for i, d in sd.items():
        old = F.z[i]
        if d >= 0:
            F.z[i] = min(old, -24 - depth * _smooth(d / shore))
        else:
            t = -d / shore
            if old > -24:
                F.z[i] = min(old, -24 + (old + 24) * _smooth(t))


def _stamp_shape(shape, r):
    """Height 0..1 (a crater below 0) at r = distance over radius."""
    if r >= 1:
        return 0.0
    if shape == 'cone':
        return (1 - r) ** 1.3
    if shape == 'volcano':
        cone = (1 - r) ** 1.4
        return cone if r > 0.12 else cone - 0.35 * (1 - r / 0.12) ** 2
    if shape == 'caldera':
        rim = math.exp(-((r - 0.55) / 0.22) ** 2)
        return max(rim * 0.9 + (1 - r) * 0.1, 0.32 if r < 0.55 else 0.0) * (1 - _smooth((r - 0.85) / 0.15) if r > 0.85 else 1)
    if shape == 'crater':
        return -(1 - (r / 0.7) ** 2) if r < 0.7 else 0.25 * math.exp(-((r - 0.78) / 0.1) ** 2)
    if shape == 'dome':
        return math.sqrt(max(0.0, 1 - r * r)) * (1 - _smooth((r - 0.8) / 0.2) if r > 0.8 else 1)
    if shape == 'mesa':
        return 1.0 if r < 0.65 else _smooth((1 - r) / 0.35)
    return 0.0


def _game_stamp(db, src, cache={}):
    """(grid of heights over their own surroundings, n points across) of game cells [x0, y0, x1, y1]."""
    key = (id(db.recs), tuple(src))
    if key in cache:
        return cache[key]
    x0, y0, x1, y1 = (int(v) for v in src)
    x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 36:
        raise EditError('A stamp of the game\'s land is at most 6 x 6 cells.')
    G = landrange.Grid(db, x0, y0, x1, y1)
    # (its shape over its own surroundings: the ring round its edge is the ground it stands on)
    ring = [G.z[i] for i in range(G.w)] + [G.z[(G.h - 1) * G.w + i] for i in range(G.w)] + \
           [G.z[j * G.w] for j in range(G.h)] + [G.z[j * G.w + G.w - 1] for j in range(G.h)]
    base = sorted(ring)[len(ring) // 2]
    out = ([v - base for v in G.z], G.w, G.h)
    cache[key] = out
    return out


def _stamp(F, L, seed, db):
    P = L['p']
    (cx, cy), R, H, turn = L['pts'][0], max(512.0, float(P['radius'])), float(P['height']), math.radians(float(P['turn'] or 0))
    shape = P['shape'] if P['shape'] in SHAPES else 'cone'
    if shape == 'game':
        if not P.get('src'):
            raise EditError('Pick the game\'s cells this stamp copies.')
        S, sw, sh = _game_stamp(db, P['src'])
        top = max(abs(v) for v in S) or 1.0
        k = H / top if H else 1.0
        c, s_ = math.cos(turn), math.sin(turn)
        half = max(sw, sh) / 2.0
        for i in F.near(cx - R, cy - R, cx + R, cy + R):
            x, y = F.world(i)
            dx, dy = x - cx, y - cy
            r = math.hypot(dx, dy) / R
            if r >= 1:
                continue
            # (into the stamp's own points: turned back, scaled so its wider side spans the radius)
            lx, ly = (dx * c + dy * s_) / R * half + (sw - 1) / 2.0, (-dx * s_ + dy * c) / R * half + (sh - 1) / 2.0
            if not (0 <= lx <= sw - 1 and 0 <= ly <= sh - 1):
                continue
            ix, iy = min(sw - 2, int(lx)), min(sh - 2, int(ly))
            fx, fy = lx - ix, ly - iy
            v = ((S[iy * sw + ix] * (1 - fx) + S[iy * sw + ix + 1] * fx) * (1 - fy)
                 + (S[(iy + 1) * sw + ix] * (1 - fx) + S[(iy + 1) * sw + ix + 1] * fx) * fy)
            F.z[i] += v * k * (1 - _smooth((r - 0.8) / 0.2))
        return
    for i in F.near(cx - R, cy - R, cx + R, cy + R):
        x, y = F.world(i)
        dx, dy = x - cx, y - cy
        # (an oval when turned would need a stretch; the parametric ones are round)
        F.z[i] += H * _stamp_shape(shape, math.hypot(dx, dy) / R)


# ---------- the whole plan ----------

def _work(db, cells, plan, s):
    keys = sorted({landrange._key(k) for k in cells or []})
    if not keys:
        raise EditError('Mark the cells to shape on the land map first.')
    if len(keys) > landrange.MAX_CELLS:
        raise EditError('That is %d cells; shape at most %d at once.' % (len(keys), landrange.MAX_CELLS))
    layers = [_clean(L) for L in (plan.get('layers') or []) if L.get('on', True) is not False]
    # (rivers and lakes are carved last, through whatever the other shapes raised: a volcano stamped after a river
    # was drawn would otherwise dam it; among themselves, and the others among themselves, the order stands)
    layers = [L for L in layers if L['kind'] not in WATER] + [L for L in layers if L['kind'] in WATER]
    xs, ys = [k[0] for k in keys], [k[1] for k in keys]
    G = landrange.Grid(db, min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
    F = Field(G, s)
    before = list(F.z)
    seed = int(plan.get('seed') or 1)
    for L in layers:
        fn = {'coast': _coast, 'plateau': _plateau, 'ridge': _ridge, 'river': _river, 'valley': _valley, 'lake': _lake}.get(L['kind'])
        if fn:
            fn(F, L, seed)
        else:
            _stamp(F, L, seed, db)
    # (nothing much under the game's own lowest ground, -2448 in TR: a crater stamped into the sea stops there)
    for i in range(len(F.z)):
        if F.z[i] < FLOOR:
            F.z[i] = min(before[i], FLOOR)
    # rolling ground on the plan's land, as rough as the region's (none under the sea: the bed stays smooth)
    rough = float(plan.get('rough', 1.0))
    dress = _clean_opts(plan.get('dress'), DRESS)
    reg = {k: (dress['region'] or landrange._region_of(db, k[0], k[1])).lower() for k in keys}
    if rough > 0 and layers:
        amp = rough * landrange._roughness(db, sorted(set(reg.values()))) / 1.8 * 0.6
        for i in range(len(F.z)):
            z = F.z[i]
            if z > 0 and z != before[i]:
                x, y = F.world(i)
                # (fainter near the water, and never dipping dry land under it: half its height over 32 at most)
                F.z[i] = max(z + landrange.noise(x, y, seed, amp) * min(1.0, z / 1500.0), 32 + 0.5 * (z - 32) if z > 32 else z)
    # the marked cells' own points (an edge shared with a cell that isn't marked is not theirs)
    marked = set(keys)
    inside = bytearray(F.w * F.h)
    per = 64 // s
    for y in range(F.h):
        cys = {G.y0 + (y - 1) // per, G.y0 + y // per} if y % per == 0 else {G.y0 + y // per}
        for x in range(F.w):
            cxs = {G.x0 + (x - 1) // per, G.x0 + x // per} if x % per == 0 else {G.x0 + x // per}
            if all((cx, cy) in marked for cx in cxs for cy in cys):
                inside[y * F.w + x] = 1
    # the natural passes (landpasses): terraces, rain gullies, then settling the steepest slopes to the region's
    F.info = {}
    P = _clean_opts(plan.get('passes'), PASSES)
    if layers or P['gullies'] > 0 or P['terraces']:
        import landpasses
        if P['detail'] and layers:
            changed = bytearray(1 if F.z[i] != before[i] else 0 for i in range(len(F.z)))
            rs = sorted(set(reg.values()))
            want = region_figure(db, rs, 'rough', '1024', 430.0) * P['detail_k']
            want128 = region_figure(db, rs, 'rough', '128', 62.0) * P['detail_k']
            F.info['detail'] = round(landpasses.match_roughness(F, inside, changed, want, seed, target128=want128))
        if P['terraces']:
            F.info['terraced'] = landpasses.terraces(F, inside, P['tstep'], P['tsharp'], P['tslope'])
        if P['gullies'] > 0:
            F.info['drops'] = landpasses.gullies(F, inside, P['gullies'], seed)
        if P['settle']:
            ang = P['angle'] or region_figure(db, sorted(set(reg.values())), 'slope', '99', 62.0)
            F.info['settle_angle'] = round(ang, 1)
            F.info['too_steep'] = landpasses.settle(F, inside, ang)
    # the ground held under what is built on it: buildings, ruins, doors (the loose things move with the ground)
    prot = _clean_opts(plan.get('protect'), PROTECT)
    F.hold, F.held = None, []
    if prot['hold']:
        F.hold, F.held = _holds(db, F, keys, prot['margin'])
        if F.hold is not None:
            for i in range(len(F.z)):
                k = F.hold[i]
                if k:
                    F.z[i] = F.z[i] + (before[i] - F.z[i]) * k
        F.info['held'] = len(F.held)
    # the fade at the edge of the marked cells: nothing moves on an edge shared with a cell that isn't marked
    dist = landrange._distance(inside, F.w, F.h)
    fade = float(plan.get('fade', 1024))
    for i in range(len(F.z)):
        t = _smooth(dist[i] * F.step / fade) if inside[i] else 0.0
        F.z[i] = before[i] + (F.z[i] - before[i]) * t
    return keys, G, F, inside, reg


PROTECT = {'hold': True, 'margin': 512.0}


def held_kind(r):
    """'hold' for what the ground must stay put under (a building or a piece of one, a ruin's walls, a door), else
    None (a loose thing: a rock, a plant, a crate, a person, which moves with the ground: landscape._follow_ground)."""
    if r.get('type') == 'DOOR':
        return 'hold'
    if r.get('arch') and not landscape.NATURAL.search(r['id'].lower()):
        return 'hold'
    return None


def _holds(db, F, keys, margin):
    """(weights 0-1 a point, the held pieces [[id, 4 corners]]): 1 under each held piece's footprint (its model's
    box, scaled and turned as it stands), fading to 0 over the margin round it."""
    margin = max(64.0, float(margin))
    hold = None
    held = []
    for gx, gy in keys:
        if landscape._winner(db, gx, gy) is None:
            continue
        m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
        for r in m.get('refs') or []:
            if held_kind(r) != 'hold' or not r.get('b'):
                continue
            b, s = r['b'], r.get('s') or 1.0
            x0, y0, x1, y1 = b[0] * s, b[1] * s, b[3] * s, b[4] * s
            px, py, rz = r['p'][0], r['p'][1], r['p'][5]
            c, sn = math.cos(rz), math.sin(rz)
            # (the box's corners in the world: the game turns a thing by -rz round the up axis, mapdata._rotated_contains)
            corners = [[px + lx * c + ly * sn, py - lx * sn + ly * c] for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            held.append([r['id'], [[round(v) for v in p] for p in corners], r['k']])
            if hold is None:
                hold = [0.0] * len(F.z)
            xs, ys = [p[0] for p in corners], [p[1] for p in corners]
            for i in F.near(min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin):
                wx, wy = F.world(i)
                dx, dy = wx - px, wy - py
                lx, ly = dx * c - dy * sn, dx * sn + dy * c
                ox = max(x0 - lx, 0.0, lx - x1)
                oy = max(y0 - ly, 0.0, ly - y1)
                d = math.hypot(ox, oy)
                if d >= margin:
                    continue
                k = 1.0 if d <= 0 else 1.0 - _smooth(d / margin)
                if k > hold[i]:
                    hold[i] = k
    return hold, held


def region_figure(db, regions, table, key, default):
    """The regions' figure from the land survey (e.g. 'slope', '99': the slope 99% of their ground is under)."""
    import landsurvey
    s = landsurvey.ready(db)
    vals = [((s or {}).get('regions', {}).get(r) or {}).get(table, {}).get(key) for r in regions]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else default


def measure(F, keys):
    """The plan's land against the game's figures: slopes (degrees, percentiles), the share over 45, and the
    roughness 128, 1024 and 8192 apart along the rows, over the marked cells' points above the water."""
    G = F.G
    per = 64 // F.s
    sl, lag = [], {1: [0.0, 0], 8: [0.0, 0], 64: [0.0, 0]}
    for gx, gy in keys:
        ox, oy = (gx - G.x0) * per, (gy - G.y0) * per
        for y in range(oy + 1, oy + per):
            for x in range(ox + 1, ox + per):
                i = y * F.w + x
                z = F.z[i]
                if z < 0:
                    continue
                gxs = (F.z[i + 1] - F.z[i - 1]) / (2 * F.step)
                gys = (F.z[i + F.w] - F.z[i - F.w]) / (2 * F.step)
                sl.append(math.degrees(math.atan(math.hypot(gxs, gys))))
                for L, acc in lag.items():
                    k = L // F.s
                    if k >= 1 and x + k < F.w and F.z[i + k] >= 0:
                        d = F.z[i + k] - z
                        acc[0] += d * d
                        acc[1] += 1
    sl.sort()
    pc = {str(p): round(sl[min(len(sl) - 1, int(len(sl) * p / 100))], 1) for p in (50, 90, 99)} if sl else {}
    return {'slope': pc, 'over45': round(sum(1 for v in sl if v > 45) / max(1, len(sl)), 4),
            'rough': {str(L * 128): round(math.sqrt(a[0] / a[1])) for L, a in lag.items() if a[1]}, 'points': len(sl)}


def preview(db, cells, plan):
    """{'cells': {'gx,gy': {'n': 17, 'h': [...], 't': [256 texture files]}}, 'textures': {file: count}, 'info'}: the
    plan's land at every 4th point, for the map, with the textures it would lay; nothing written."""
    keys, G, F, _ins, reg = _work(db, cells, plan, 4)
    out = {}
    files = {}
    if plan.get('paint', True) is not False:
        import landdress
        dress = _clean_opts(plan.get('dress'), DRESS)
        _ids, files = landdress.textures(db, F, keys, reg, dress['variety'], int(plan.get('seed') or 1))
    used = {}
    for gx, gy in keys:
        ox, oy = (gx - G.x0) * 16, (gy - G.y0) * 16
        c = {'n': 17, 'h': [int(round(F.z[(oy + y) * F.w + ox + x])) for y in range(17) for x in range(17)]}
        t = files.get((gx, gy))
        if t:
            c['t'] = t
            for f in set(t):
                used[f] = used.get(f, 0) + 1
        out['%d,%d' % (gx, gy)] = c
    return {'cells': out, 'textures': used, 'info': F.info, 'regions': sorted(set(reg.values())),
            'held': [h[1] for h in (F.held or [])[:3000]]}


def apply(db, cells, plan):
    """The plan written into the marked cells at every point. One Undo step."""
    _require_project(db)
    keys0 = sorted({landrange._key(k) for k in cells or []})
    made = 0
    for gx, gy in keys0:
        if landscape.new_land(db, gx, gy, landrange._region_of(db, gx, gy), sync=False):
            made += 1
    if made:
        db.sync_project()                               # (once for all the new cells, not once each)
    keys, G, F, inside, reg = _work(db, cells, plan, 1)
    before = {k: G.cell(*k) for k in keys}
    G.z = __import__('array').array('d', F.z)
    free = inside if F.hold is None else bytearray(0 if F.hold[i] >= 1 else inside[i] for i in range(len(inside)))
    eased = landrange.ease_cliffs(G, free)          # (held ground stays as it is)
    F.z = list(G.z)
    new_h = {k: G.cell(*k) for k in keys}
    moved = paths = 0
    dress = _clean_opts(plan.get('dress'), DRESS)
    ids, files = {}, {}
    paint = plan.get('paint', True) is not False
    if paint:
        import landdress
        ids, files = landdress.textures(db, F, keys, reg, dress['variety'], int(plan.get('seed') or 1))
    # the region's shading (landshade), worked out here for each cell and written with its heights and textures in
    # one go: its tints, then its seams, then its darker hollows, each on what the one before made (as shade() would
    # read them back), on the heights as the record keeps them (to 8 units). One write a cell, not four.
    import landshade
    modes = [m for m, k in (('texture', 'tints'), ('seams', 'seams'), ('hollows', 'hollows')) if dress[k]] \
        if (paint or dress['hollows']) else []
    rmain = Counter(reg.values()).most_common(1)[0][0] if reg else ''
    held_keys = {h[2] for h in (F.held or [])}
    q_h = {k: landscape._encode_heights([float(v) for v in new_h[k]])[1] for k in keys} if modes else {}
    shaded = set()
    for gx, gy in keys:
        k = (gx, gy)
        cols = None
        if modes:
            grid, col = landshade._land_of(db, landscape._winner(db, gx, gy))
            if files.get(k):
                grid = [f.lower() for f in files[k]]
            mix = landshade.mixes(grid) if ('texture' in modes or 'seams' in modes) else None
            for mode in modes:
                new, _n = landshade.colours(db, gx, gy, mode, max(0.0, min(1.0, float(dress['shade']))), rmain, grid, col,
                                            H=q_h[k], around=landscape.around_of(db, gx, gy, q_h), mix=mix)
                if new is not None:
                    col = new
                    shaded.add(mode)
            cols = col
        after = landscape.write(db, gx, gy, new_h[k], ids.get(k), cols, around=landscape.around_of(db, gx, gy, new_h))
        # (what the ground is held under stays where it stands: its origin can lie outside its box, where the
        # ground did move)
        moved += landscape._follow_ground(db, gx, gy, before[k], after, skip=held_keys)
        paths += landscape._follow_paths(db, gx, gy, before[k], after)
    db.sync_project()
    shaded = [m for m in ('texture', 'seams', 'hollows') if m in shaded]
    cl = ['%d,%d' % k for k in keys]
    # the cells into the region, so its weather, sounds and creatures go with the land
    assigned = 0
    if dress['assign'] and dress['region']:
        import regions
        try:
            assigned = regions.assign(db, dress['region'], cl, note=False)['changed']
        except EditError:
            pass
    db.sync_project()
    m = measure(F, keys)
    n = len([L for L in plan.get('layers') or [] if L.get('on', True) is not False])
    commit(db, 'Shaped %d cell%s with %d shape%s%s' % (len(keys), '' if len(keys) == 1 else 's', n, '' if n == 1 else 's',
                                                       (' (%d new)' % made) if made else ''))
    texn = sorted(len(set(v)) for v in ids.values())
    return {'cells': len(keys), 'new': made, 'eased': eased, 'moved': moved, 'paths': paths, 'info': F.info,
            'shaded': shaded, 'assigned': assigned, 'measured': m,
            'textures_a_cell': texn[len(texn) // 2] if texn else 0,
            'region_figures': _figures(db, sorted(set(reg.values())))}


def _figures(db, regions):
    """The game's own figures for the regions, beside the plan's measure(), for the note after apply."""
    import landsurvey
    s = landsurvey.ready(db)
    out = {}
    for r in regions:
        R = ((s or {}).get('regions') or {}).get(r)
        if R:
            out[r] = {'slope': {k: R['slope'].get(k) for k in ('50', '90', '99')}, 'over45': R['steep'].get('45'),
                      'rough': {k: R['rough'].get(k) for k in ('128', '1024', '8192')},
                      'tex_per_cell': (R.get('tex_per_cell') or {}).get('50')}
    return out
