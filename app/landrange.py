"""Land over many cells at once (packaging/terrain-shaping-proposal.md, stage 1): the cells marked on the land map
stitched into one height grid (a point every 128 units, the cells' shared edges one row of points), worked on as
one piece, and split back into cells with their edges exactly equal.

raise_land() is the first shape: the marked cells raised into land, the way an island or a new stretch of coast
stands out of the sea. The ground rises from the edge of the marked area (where it meets the cells left as they
are, so nothing outside changes) to the height asked for, over the coast width, with noise on top whose
roughness falls off with scale as the game's land does (landsurvey: 0.72-0.86 everywhere; 0.78 here). Ground
already higher stays. Then:
  - steps too steep for the land record along a row (127 x 8 a point, east-west, and north-south down each
    cell's first column; landscape._encode_heights would soften them unevenly) are eased out, and counted;
  - each 512-unit patch gets the texture the game most often lays at its slope and height in the region
    (landsurvey's table, roads left out);
  - cells with no land yet get it first (landscape.new_land: the sea bed at -2048, a new unnamed cell);
  - normals over the joined grid, the world map's WNAM, things and walking paths follow the ground;
  - all of it one Undo step."""
import math
from array import array

import landscape
import mapdata
from editing import EditError, commit, _require_project

N = 65
CELL = 8192
STEP_MAX = 127 * 8           # (the steepest step the land record holds from one point to the next along a row)
MAX_CELLS = 400
HURST = 0.78


def _key(k):
    gx, gy = (int(v) for v in (k.split(',') if isinstance(k, str) else k))
    return gx, gy


class Grid:
    """Heights of the cells x0..x1, y0..y1 as one grid; cells with no land stand at the sea bed (-2048)."""

    def __init__(self, db, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.w, self.h = 64 * (x1 - x0 + 1) + 1, 64 * (y1 - y0 + 1) + 1
        self.z = array('d', [-2048.0]) * (self.w * self.h)
        self.land = set()
        for gy in range(y0, y1 + 1):
            for gx in range(x0, x1 + 1):
                L = mapdata.land(db, gx, gy)
                if not L.get('exists') or not L.get('h'):
                    continue
                self.land.add((gx, gy))
                H, ox, oy = L['h'], (gx - x0) * 64, (gy - y0) * 64
                for y in range(N):
                    row = (oy + y) * self.w + ox
                    self.z[row:row + N] = array('d', H[y * N:(y + 1) * N])

    def cell(self, gx, gy):
        ox, oy = (gx - self.x0) * 64, (gy - self.y0) * 64
        out = []
        for y in range(N):
            row = (oy + y) * self.w + ox
            out.extend(self.z[row:row + N])
        return out


def _hash(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1.0


# (the lattice values, remembered: a plan of 100 cells asked for the same few thousand 23 million times, 2026-10-26)
_LAT = {}


def _h(ix, iy, seed):
    k = (ix, iy, seed)
    v = _LAT.get(k)
    if v is None:
        if len(_LAT) > 3000000:
            _LAT.clear()
        v = _LAT[k] = _hash(ix, iy, seed)
    return v


def _value(x, y, seed):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _h(ix, iy, seed), _h(ix + 1, iy, seed)
    c, d = _h(ix, iy + 1, seed), _h(ix + 1, iy + 1, seed)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy


_OCT = [(lam, (lam / 8192.0) ** 0.78) for lam in (8192.0, 4096.0, 2048.0, 1024.0, 512.0)]


def noise(wx, wy, seed, amp):
    """Rolling ground at a world point: layers 8192 down to 512 across, each smaller one fainter by the game's
    roughness exponent (half the size, 0.58 of the height). (_value inlined, the same sums in the same order.)"""
    out = 0.0
    floor, get = math.floor, _LAT.get
    for lam, fall in _OCT:
        s = seed + int(lam)
        x, y = wx / lam, wy / lam
        ix, iy = floor(x), floor(y)
        fx, fy = x - ix, y - iy
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a = get((ix, iy, s))
        if a is None:
            a = _h(ix, iy, s)
        b = get((ix + 1, iy, s))
        if b is None:
            b = _h(ix + 1, iy, s)
        c = get((ix, iy + 1, s))
        if c is None:
            c = _h(ix, iy + 1, s)
        d = get((ix + 1, iy + 1, s))
        if d is None:
            d = _h(ix + 1, iy + 1, s)
        out += ((a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy) * amp * fall
    return out


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _distance(inside, w, h):
    """Distance in points from each point inside to the nearest one outside (chamfer 3-4, two passes)."""
    big = 10 ** 9
    d = array('l', [big if v else 0 for v in inside])
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not d[i]:
                continue
            v = d[i]
            if x > 0: v = min(v, d[i - 1] + 3)
            if y > 0:
                v = min(v, d[i - w] + 3)
                if x > 0: v = min(v, d[i - w - 1] + 4)
                if x < w - 1: v = min(v, d[i - w + 1] + 4)
            d[i] = v
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            i = y * w + x
            if not d[i]:
                continue
            v = d[i]
            if x < w - 1: v = min(v, d[i + 1] + 3)
            if y < h - 1:
                v = min(v, d[i + w] + 3)
                if x < w - 1: v = min(v, d[i + w + 1] + 4)
                if x > 0: v = min(v, d[i + w - 1] + 4)
            d[i] = v
    return [v / 3.0 for v in d]


def ease_cliffs(G, inside):
    """Steps too steep for the record (STEP_MAX from one point to the next along a row; down each cell's first
    column too) spread over the points either side, where both are free to move. The number of steps there were."""
    w, h, z = G.w, G.h, G.z
    pairs = []
    for y in range(h):
        for x in range(w - 1):
            pairs.append((y * w + x, y * w + x + 1))
    for x in range(0, w, 64):
        for y in range(h - 1):
            pairs.append((y * w + x, (y + 1) * w + x))
    pairs = [(a, b) for a, b in pairs if inside[a] or inside[b]]
    found = sum(1 for a, b in pairs if abs(z[b] - z[a]) > STEP_MAX)
    for _ in range(60):
        worst = 0
        for a, b in pairs:
            d = z[b] - z[a]
            over = abs(d) - (STEP_MAX - 8)
            if over <= 0:
                continue
            worst = max(worst, over)
            s = 1 if d > 0 else -1
            if inside[a] and inside[b]:
                z[a] += s * over / 2
                z[b] -= s * over / 2
            elif inside[a]:
                z[a] += s * over
            elif inside[b]:
                z[b] -= s * over
        if worst <= 0:
            break
    return found


def _region_of(db, gx, gy, want=''):
    """The region whose land a cell takes after: the one asked for, its own, or the nearest cell's."""
    if want:
        return want.lower()
    for r in range(0, 6):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                i = mapdata.cell_info(db, '#%d,%d' % (gx + dx, gy + dy))
                if i and i.get('region'):
                    return i['region'].lower()
    # (out in the open sea: the region of the nearest land the survey knows)
    import landsurvey
    s = landsurvey.ready(db)
    best = None
    for k, c in ((s or {}).get('cells') or {}).items():
        if c['region'] and c['k'] != 'sea':
            x, y = (int(v) for v in k.split(','))
            d = (x - gx) ** 2 + (y - gy) ** 2
            if best is None or d < best[0]:
                best = (d, c['region'])
    return best[1] if best else ''


def _roughness(db, regions):
    """The regions' height difference 8192 units apart (landsurvey), averaged; the game's usual 1,300 if unknown."""
    import landsurvey
    s = landsurvey.ready(db)
    vals = [s['regions'][r]['rough'].get('8192') for r in regions if s and r in s['regions']]
    vals = [v for v in vals if v]
    return sum(vals) / len(vals) if vals else 1300.0


def _texture_table(db, region):
    """{(slope band, height band): LTEX id} from the land survey's table for the region; {} if not learnt."""
    import landsurvey
    s = landsurvey.ready(db)
    if not s:
        return {}
    R = s['regions'].get(region)
    if not R:
        return {}
    by_file = {}
    for (_f, _i), (rid, tex) in landscape._ltex_all(db).items():
        by_file.setdefault(tex.lower(), rid)
    out = {}
    for band, t in R['textures'].items():
        for name, _share in t['top']:
            if name == 'default' or 'road' in name:
                continue
            rid = by_file.get(name)
            if rid:
                sb, hb = (int(v) for v in band.split(','))
                out[(sb, hb)] = rid
                break
    return out


def _paint(G, gx, gy, table):
    """16 x 16 LTEX ids for a cell from its patches' slope and height."""
    import landsurvey
    if not table:
        return None
    ox, oy = (gx - G.x0) * 64, (gy - G.y0) * 64
    out = []
    for py in range(16):
        for px in range(16):
            zs, sl = [], []
            for y in range(oy + py * 4, oy + py * 4 + 5):
                for x in range(ox + px * 4, ox + px * 4 + 5):
                    zs.append(G.z[y * G.w + x])
                    if 0 < x < G.w - 1 and 0 < y < G.h - 1:
                        gx_ = (G.z[y * G.w + x + 1] - G.z[y * G.w + x - 1]) / 256.0
                        gy_ = (G.z[(y + 1) * G.w + x] - G.z[(y - 1) * G.w + x]) / 256.0
                        sl.append(math.degrees(math.atan(math.hypot(gx_, gy_))))
            sb = landsurvey._band(sum(sl) / len(sl) if sl else 0, landsurvey.SLOPES)
            hb = landsurvey._band(sum(zs) / len(zs), landsurvey.HEIGHTS)
            t = table.get((sb, hb))
            if t is None:
                # (a slope the region has no example of at this height: the nearest slope band that it has)
                near = sorted((abs(s - sb), s) for (s, b) in table if b == hb)
                t = table.get((near[0][1], hb)) if near else next(iter(table.values()))
            out.append(t)
    return out


def raise_land(db, cells, height=512.0, coast=6144.0, rough=1.0, paint=True, region='', seed=None):
    """The marked cells (['gx,gy']) raised into land. height: the land's height away from its edge; coast: how
    far in from the edge it reaches it (units); rough: 0 smooth to 2 twice the usual noise. One Undo step."""
    _require_project(db)
    keys = sorted({_key(k) for k in cells or []})
    if not keys:
        raise EditError('Mark some cells on the land map first.')
    if len(keys) > MAX_CELLS:
        raise EditError('That is %d cells; raise at most %d at once.' % (len(keys), MAX_CELLS))
    height, coast, rough = float(height), max(512.0, float(coast)), max(0.0, min(3.0, float(rough)))
    seed = int(seed) if seed is not None else 1
    reg = {k: _region_of(db, k[0], k[1], region) for k in keys}
    made = 0
    for gx, gy in keys:
        if landscape.new_land(db, gx, gy, reg[(gx, gy)]):
            made += 1
    xs, ys = [k[0] for k in keys], [k[1] for k in keys]
    G = Grid(db, min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
    marked = set(keys)
    before = {k: G.cell(*k) for k in keys}
    # a point is free to change when every cell it belongs to is marked: the edges shared with other cells stay
    inside = bytearray(G.w * G.h)
    for y in range(G.h):
        cys = {G.y0 + (y - 1) // 64, G.y0 + y // 64} if y % 64 == 0 else {G.y0 + y // 64}
        for x in range(G.w):
            cxs = {G.x0 + (x - 1) // 64, G.x0 + x // 64} if x % 64 == 0 else {G.x0 + x // 64}
            if all((cx, cy) in marked for cx in cxs for cy in cys):
                inside[y * G.w + x] = 1
    dist = _distance(inside, G.w, G.h)
    # (how rolling the ground is: the region's own height difference 8192 apart, landsurvey's 'rough' table, about
    # 1,300 in most regions, 2,600 in the highlands; the layers' noise gives about 1.8 times its amplitude there)
    amp = rough * _roughness(db, sorted(set(reg.values()))) / 1.8
    for y in range(G.h):
        wy = (G.y0 * 64 + y) * 128
        for x in range(G.w):
            i = y * G.w + x
            if not inside[i]:
                continue
            wx = (G.x0 * 64 + x) * 128
            # (the shore wanders, bays and headlands up to half the coast's width either way: the waterline
            # follows broad noise, not the square edge of the marked cells; at the edge itself nothing moves)
            e = dist[i] * 128.0
            wobble = noise(wx, wy, seed + 7, coast * 0.9) * min(1.0, e / 1024.0) if rough else 0.0
            s = _smooth((e + wobble) / coast)
            if s <= 0:
                continue
            want = height + (noise(wx, wy, seed, amp) if amp else 0.0)
            if want < 48 <= height:
                want = 48 + (want - 48) * 0.15         # (hollows inland stay just above the water: not ponds)
            old = G.z[i]
            G.z[i] = max(old, old + (want - old) * s)
    eased = ease_cliffs(G, inside)
    new_h = {k: G.cell(*k) for k in keys}
    moved = paths = 0
    painted = set()
    tables = {}
    # (painted as Shape them paints, landdress: the region's textures at each slope, height and shore, in its own
    # number a cell and its own broken patches; one texture a band, the land came out in blocks of one or two,
    # lab jtex1, 2026-10-29)
    dressed = {}
    if paint:
        try:
            import landdress
            import landshapes
            dressed, _files = landdress.textures(db, landshapes.Field(G, 1), list(keys), {k: reg[k] for k in keys}, -1.0, int(seed or 1))
        except Exception:
            dressed = {}
    for gx, gy in keys:
        tex = None
        if paint:
            r = reg[(gx, gy)]
            if r not in tables:
                tables[r] = _texture_table(db, r)
            tex = dressed.get((gx, gy)) or _paint(G, gx, gy, tables[r])
            if tex:
                painted.add(r)
        after = landscape.write(db, gx, gy, new_h[(gx, gy)], tex, None, around=landscape.around_of(db, gx, gy, new_h))
        moved += landscape._follow_ground(db, gx, gy, before[(gx, gy)], after)
        paths += landscape._follow_paths(db, gx, gy, before[(gx, gy)], after)
    db.sync_project()
    commit(db, 'Raised %d cell%s into land%s%s' % (len(keys), '' if len(keys) == 1 else 's',
                                                   (' (%d new)' % made) if made else '',
                                                   (', %d objects followed it' % moved) if moved else ''))
    return {'cells': len(keys), 'new': made, 'eased': eased, 'moved': moved, 'paths': paths, 'painted_as': sorted(painted)}
