"""A cliff along a drawn line: the region's cliff rocks chained end to end along it, each in a pose the game set
such a rock in (cliffrocks' learning), turned so its face looks out over the drop, with loose boulders at the foot
and crest pieces behind. The user (2026-11-04) had been picking terrain_rock pieces from the palette one by one to
make a coast like the game's: a line is what that work is.

lay(db, pts, ...): pts the line [[x, y], ...]; side 0 picks the drop side itself (the lower ground, or the water),
+1 the left of the line as drawn, -1 the right; height roughly how tall the face stands (the rocks are scaled to it
within the sizes the game uses them at); like a region's look, else the line's own; pieces: rock ids to use instead
of the region's (the user's own picks, chained the same way); raise: lift the ground behind the line to the face's
top so the land meets it. One Undo."""
import math
import random

import cliffrocks
import mapdata

OVERLAP = 0.55                  # the next face piece starts this far along the last one's extent (the game's cliffs
                                # overlap, piece into piece; end to end they showed every seam)
OUT = 0.3                       # the face's middle this share of its width out over the drop
FOOT_EVERY = 0.55               # a boulder at the foot for about this share of the face pieces
CREST_EVERY = 0.4               # a crest piece behind for about this share
SIDE_PROBE = 480                # how far either side the ground is read to pick the drop side
RAISE_IN = 420                  # the ground raised along a line this far behind the face
BIG = 220                       # a face piece is at least this wide (its smaller footprint side) and tall
SMALL = 260                     # a foot boulder is at most this wide
MAX_PIECES = 400
CLAD_REACH = 1024               # the steep ground this far from the line is clad round the chain (rockface.py)
LAST = {}


def _poly(pts):
    """Segments with their lengths and the running length at each start."""
    segs = []
    t = 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1:
            continue
        segs.append((a, b, L, t))
        t += L
    return segs, t


def _at(segs, t):
    """The point and unit direction at running length t."""
    for a, b, L, t0 in segs:
        if t <= t0 + L or (a, b, L, t0) is segs[-1]:
            u = max(0.0, min(1.0, (t - t0) / L))
            d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u), d
    a, b, L, t0 = segs[-1]
    return (b[0], b[1]), ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _drop_side(db, segs, total):
    """+1 when the left of the line (as drawn) is the lower side or the water, else -1."""
    lo = [0.0, 0.0]
    n = 0
    for k in range(5):
        p, d = _at(segs, total * (k + 0.5) / 5.0)
        nrm = (-d[1], d[0])
        for s, i in ((1, 0), (-1, 1)):
            z = mapdata.terrain_z(db, p[0] + nrm[0] * s * SIDE_PROBE, p[1] + nrm[1] * s * SIDE_PROBE)
            lo[i] += -4000.0 if z is None else z
        n += 1
    return 1 if lo[0] <= lo[1] else -1


def _region(db, like, x, y):
    import landrange
    reg = (like or '').lower() or landrange._region_of(db, int(math.floor(x / 8192.0)), int(math.floor(y / 8192.0)))
    if not like and cliffrocks._rocky(db, reg) < cliffrocks.ENOUGH:
        reg = cliffrocks._nearest_rocky(db, int(math.floor(x / 8192.0)), int(math.floor(y / 8192.0))) or reg
    return reg


def _items(db, region, pieces):
    """(faces, feet, crests): the rocks to chain, weighted by how often the region uses them on steep ground; or the
    user's own pieces as faces."""
    if pieces:
        out = []
        for pid in pieces:
            ri = db.resolve_id(pid)
            b = mapdata.object_bounds(db, ri) if ri is not None else None
            if not b:
                continue
            out.append({'id': db.recs[ri][1] if ri is not None else pid, 'n': 1, 'size': [b[3] - b[0], b[4] - b[1], b[5] - b[2]],
                        'zmin': b[2], 'smin': 0.8, 'smax': 1.4, 'sink': max(0.0, -b[2]) if b[2] < 0 else 0.0, 'poses': [], 'at': [0, 1, 0], 'b': b})
        return out, [], []
    F = cliffrocks.learn(db, region)
    seen = {}
    for k, band in enumerate(F['bands']):
        w = 1.0 if k >= cliffrocks.STEEP_BAND else 0.4 if k == cliffrocks.STEEP_BAND - 1 else 0.15
        for it in band['items']:
            low = it['id'].lower()
            e = seen.setdefault(low, dict(it, w=0.0, poses=[]))
            e['w'] += it['n'] * w
            e['poses'] = (e['poses'] + list(it.get('poses') or []))[:cliffrocks.POSES]
    items = list(seen.values())
    for it in items:
        ri = db.resolve_id(it['id'])
        it['b'] = mapdata.object_bounds(db, ri) if ri is not None else None
    items = [it for it in items if it['b']]
    faces = [it for it in items if min(it['size'][0], it['size'][1]) >= BIG and it['size'][2] >= BIG]
    feet = [it for it in items if max(it['size'][0], it['size'][1]) <= SMALL]
    crests = [it for it in faces if it['at'][cliffrocks.CREST] >= max(2, it['n'] * 0.2)] or faces
    return faces or items, feet, crests


def _pick(rng, items):
    tot = sum(it.get('w', it['n']) for it in items)
    r = rng.random() * tot
    for it in items:
        r -= it.get('w', it['n'])
        if r <= 0:
            return it
    return items[-1]


def _rotate(x, y, rz):
    """A local offset into the world for a thing turned by rz (local x -> (cos, -sin), y -> (sin, cos))."""
    c, s = math.cos(rz), math.sin(rz)
    return x * c + y * s, -x * s + y * c


def _extent(b, s, rz, d):
    """How far the turned, scaled box reaches along d and across it, and its middle's world offset from the origin."""
    xs = [b[0], b[3]]
    ys = [b[1], b[4]]
    along, across = [], []
    nrm = (-d[1], d[0])
    for x in xs:
        for y in ys:
            wx, wy = _rotate(x * s, y * s, rz)
            along.append(wx * d[0] + wy * d[1])
            across.append(wx * nrm[0] + wy * nrm[1])
    mx, my = _rotate((b[0] + b[3]) / 2.0 * s, (b[1] + b[4]) / 2.0 * s, rz)
    return max(along) - min(along), max(across) - min(across), (mx, my)


def _pose(rng, it, d, drop, place, height):
    """rx, ry, rz, dz (origin over the ground), s for a rock on the line: a learnt pose at that place on the slope when
    the region has one, turned so its downhill is the drop; else its long side along the line."""
    poses = [p for p in (it.get('poses') or []) if p[5] == place] or (it.get('poses') or [])
    sz = it['size'][2] or 1.0
    s_h = height / sz
    if poses:
        rx, ry, turn, dz, s0, _p = poses[rng.randrange(len(poses))]
        s = max(it['smin'], min(it['smax'], s_h)) if it.get('smax') else s0
        s = max(0.5, min(2.5, s * (0.94 + rng.random() * 0.12)))
        if turn is not None:
            rz = (cliffrocks._downhill(-drop[0], -drop[1]) + turn + (rng.random() - 0.5) * 0.25) % (2 * math.pi)
        else:
            rz = _along(it, d, rng)
        return rx, ry, rz, dz * s / (s0 or 1.0), s
    s = max(0.5, min(2.5, max(it['smin'], min(it['smax'], s_h)) * (0.94 + rng.random() * 0.12)))
    return 0.0, 0.0, _along(it, d, rng), -it.get('sink', 0.0) * s - (it['zmin'] * s if it['zmin'] > 0 else 0.0), s


def _along(it, d, rng):
    """The turn that lays the rock's longer footprint side along d."""
    if it['size'][0] >= it['size'][1]:
        rz = math.atan2(-d[1], d[0])
    else:
        rz = math.atan2(d[0], d[1])
    if rng.random() < 0.5:
        rz += math.pi
    return (rz + (rng.random() - 0.5) * 0.3) % (2 * math.pi)


def plan(db, pts, side=0, height=600, like='', seed=None, pieces=None, amount=1.0):
    """The rocks for the line: [{id, x, y, z, rx, ry, rz, s, part}], and {'side', 'region', 'length'}."""
    pts = [(float(p[0]), float(p[1])) for p in pts]
    segs, total = _poly(pts)
    if not segs:
        return [], {}
    rng = random.Random(int(seed) if seed is not None else random.randrange(1, 1 << 30))
    side = int(side) if side else _drop_side(db, segs, total)
    mid, _d = _at(segs, total / 2.0)
    region = _region(db, like, mid[0], mid[1])
    faces, feet, crests = _items(db, region, pieces)
    if not faces:
        return [], {'side': side, 'region': region, 'length': total, 'why': 'no rocks learnt for ' + region}
    out = []
    t = 0.0
    k = 0
    while t < total and len(out) < MAX_PIECES:
        p, d = _at(segs, t)
        drop = (-d[1] * side, d[0] * side)
        it = _pick(rng, faces)
        rx, ry, rz, dz, s = _pose(rng, it, d, drop, cliffrocks.FACE, height)
        along, across, (mx, my) = _extent(it['b'], s, rz, d)
        # (the face's middle a little out over the drop, its origin set back from there)
        cx = p[0] + drop[0] * across * OUT + d[0] * along / 2.0
        cy = p[1] + drop[1] * across * OUT + d[1] * along / 2.0
        ox, oy = cx - mx, cy - my
        # (its foot at the lower of the ground under it and the line's: a rock set up a steep bank from a line at the
        # water stood 900 over the next, lab cliff2)
        g = [v for v in (mapdata.terrain_z(db, ox, oy), mapdata.terrain_z(db, p[0], p[1])) if v is not None]
        z = (min(g) if g else 0.0) + dz
        out.append({'id': it['id'], 'x': ox, 'y': oy, 'z': z, 'rx': rx, 'ry': ry, 'rz': rz, 's': round(s, 2), 'part': 'face'})
        # a boulder at the foot, out past the face
        if feet and rng.random() < FOOT_EVERY * amount:
            fi = _pick(rng, feet)
            frx, fry, frz, fdz, fs = _pose(rng, fi, d, drop, cliffrocks.FOOT, fi['size'][2])
            off = across * (0.5 + OUT) + rng.uniform(60, 260)
            fx = cx + drop[0] * off + d[0] * rng.uniform(-along * 0.3, along * 0.3)
            fy = cy + drop[1] * off + d[1] * rng.uniform(-along * 0.3, along * 0.3)
            fg = mapdata.terrain_z(db, fx, fy)
            out.append({'id': fi['id'], 'x': fx, 'y': fy, 'z': (fg if fg is not None else 0.0) + fdz, 'rx': frx, 'ry': fry, 'rz': frz, 's': round(fs, 2), 'part': 'foot'})
        # a crest piece behind, on the land
        if crests and rng.random() < CREST_EVERY * amount:
            ci = _pick(rng, crests)
            crx, cry, crz, cdz, cs = _pose(rng, ci, d, drop, cliffrocks.CREST, height * 0.6)
            calong, cacross, (cmx, cmy) = _extent(ci['b'], cs, crz, d)
            off = across * (0.5 - OUT) + cacross * 0.35
            ccx = cx - drop[0] * off + d[0] * rng.uniform(-along * 0.25, along * 0.25)
            ccy = cy - drop[1] * off + d[1] * rng.uniform(-along * 0.25, along * 0.25)
            cox, coy = ccx - cmx, ccy - cmy
            cg = mapdata.terrain_z(db, cox, coy)
            out.append({'id': ci['id'], 'x': cox, 'y': coy, 'z': (cg if cg is not None else 0.0) + cdz, 'rx': crx, 'ry': cry, 'rz': crz, 's': round(cs, 2), 'part': 'crest'})
        t += max(64.0, along * OVERLAP) * (0.9 + rng.random() * 0.2)
        k += 1
    return out, {'side': side, 'region': region, 'length': total}


def _raise(db, pts, side, height):
    """The ground behind the line lifted to the face's top, fading back into the land (townwalls._shape_ground)."""
    import townwalls
    segs, total = _poly([(float(p[0]), float(p[1])) for p in pts])
    runs = []
    for a, b, L, t0 in segs:
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        back = (d[1] * side, -d[0] * side)                 # (away from the drop)
        g = [mapdata.terrain_z(db, *q) for q in (a, b, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0))]
        g = [v for v in g if v is not None]
        level = (sum(g) / len(g) if g else 0.0) + height * 0.85
        runs.append(((a[0] + back[0] * RAISE_IN, a[1] + back[1] * RAISE_IN), (b[0] + back[0] * RAISE_IN, b[1] + back[1] * RAISE_IN), level))
    return townwalls._shape_ground(db, runs, (), 0.0, height * 1.2)


def _dist(segs, x, y):
    """The distance from a point to the line."""
    best = None
    for a, b, L, _t in segs:
        dx, dy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        u = max(0.0, min(L, (x - a[0]) * dx + (y - a[1]) * dy))
        d = math.hypot(x - (a[0] + dx * u), y - (a[1] + dy * u))
        if best is None or d < best:
            best = d
    return best if best is not None else 1e9


def lay(db, pts, side=0, height=600, like='', seed=None, pieces=None, raise_ground=False, amount=1.0, commit=True, clad=True):
    import editing
    seed = int(seed) if seed is not None else random.randrange(1, 1 << 30)
    info = {}
    cells = 0
    if raise_ground:
        segs, total = _poly([(float(p[0]), float(p[1])) for p in pts])
        s_ = int(side) if side else (_drop_side(db, segs, total) if segs else 1)
        cells = _raise(db, pts, s_, float(height))
        side = s_
    rocks, info = plan(db, pts, side, float(height), like, seed, pieces, float(amount))
    made = cliffrocks.place(db, rocks) if rocks else 0
    db.sync_project()
    # (the steep ground within CLAD_REACH of the line clad by the rock-face pass, rockface.py: the slopes the chain
    # stands on and the lip and foot round it come out as the game's gorges do, the chain's pieces leant on)
    cladn = 0
    if clad and made:
        import rockface
        segs_, _total = _poly([(float(p[0]), float(p[1])) for p in pts])
        near_cells = sorted({(int(math.floor(r['x'] / 8192.0)), int(math.floor(r['y'] / 8192.0))) for r in rocks})
        try:
            cladn = rockface.clad(db, near_cells, mask=lambda x, y: _dist(segs_, x, y) <= CLAD_REACH, like=like, amount=float(amount),
                                  seed=seed, parts=('face', 'lip', 'foot'))['rocks']
        except editing.EditError:
            cladn = 0
    if (made or cells) and commit:
        editing.commit(db, 'Laid a cliff of %d rock%s' % (made + cladn, '' if made + cladn == 1 else 's'))
    LAST.clear()
    LAST.update(info, rocks=made, parts={p: sum(1 for r in rocks if r['part'] == p) for p in ('face', 'foot', 'crest')}, raised=cells, clad=cladn)
    return {'rocks': made + cladn, 'side': info.get('side'), 'region': info.get('region'), 'seed': seed, 'raised': cells,
            'parts': LAST['parts'], 'clad': cladn, 'why': info.get('why', '')}
