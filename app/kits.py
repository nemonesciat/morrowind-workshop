"""Interior building kits: the modular room pieces Morrowind's interiors are built from
(floor tiles with walls on some sides, corners, doorways, hall pieces).

Each piece's 3D model is measured to find which of its four sides are solid walls, which
have a doorway, and which are open, so rooms can be laid out from scratch on a grid."""
import math
import re

import mapdata
from nif import mesh_from_nif

SIDES = ('N', 'E', 'S', 'W')          # +Y, +X, -Y, -X
_cache = {}


def _model(db, ri):
    r = db.recs[ri]
    raw = db.meshes.read('meshes/' + (r[5] or '').lower().replace('\\', '/')) if r[5] else None
    return mesh_from_nif(raw) if raw else None


def game_made(db, cell_key):
    """A place the game (or another mod) made, not one the mod being made added: only those are
    examples to learn from (else the Workshop's own buildings would teach it its own habits)."""
    lst = [v for v in db.by_key.get(('CELL', cell_key), []) if v not in db.dead]
    if not lst or getattr(db, 'proj_pidx', None) is None:
        return True
    return any(db.recs[v][3] != db.proj_pidx for v in lst)


def game_uses(db, low):
    """How many places use this object, not counting the ones the mod being made added."""
    return sum(1 for ci in db.used_in.get(low, ()) if not (db.recs[ci][0] == 'CELL' and not game_made(db, db.recs[ci][7])))


def measure(db, ri, tile):
    """Wall pattern of a piece: {'N': 'wall'|'door'|'open', ...}, plus floor/ceiling, or None."""
    key = (db.recs[ri][1].lower(), tile)
    if key in _cache:
        return _cache[key]
    shapes = _model(db, ri)
    b = mapdata.object_bounds(db, ri)
    if not shapes or not b:
        _cache[key] = None
        return None
    half = tile / 2.0
    zlo, zhi = b[2], b[5]
    height = zhi - zlo
    # coverage grids of vertical faces near each side: [u (along the side), z]
    G = 16
    grids = {s: [[0] * G for _ in range(G)] for s in SIDES}
    where = {s: [0.0, 0.0] for s in SIDES}       # how far out each side's wall stands (area-weighted)
    floor = ceiling = 0.0
    for s in shapes:
        p, idx = s['p'], s['i']
        for t in range(0, len(idx) - 2, 3):
            a, bb, c = idx[t] * 3, idx[t + 1] * 3, idx[t + 2] * 3
            ax, ay, az = p[a], p[a + 1], p[a + 2]
            bx, by, bz = p[bb], p[bb + 1], p[bb + 2]
            cx, cy, cz = p[c], p[c + 1], p[c + 2]
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx - ax, cy - ay, cz - az
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            area = math.sqrt(nx * nx + ny * ny + nz * nz)
            if area < 1e-6:
                continue
            nz_ = abs(nz) / area
            mx, my, mz = (ax + bx + cx) / 3, (ay + by + cy) / 3, (az + bz + cz) / 3
            if nz_ > 0.8:              # horizontal: floor or ceiling
                if mz < zlo + height * 0.2:
                    floor += area / 2
                elif mz > zlo + height * 0.8:
                    ceiling += area / 2
                continue
            if nz_ > 0.5:
                continue
            # a vertical face: which side is it on? (it must also face along that side's direction)
            facing_y = abs(ny) > abs(nx) * 1.5
            facing_x = abs(nx) > abs(ny) * 1.5
            for side, (coord, sign) in (('N', (my, 1)), ('S', (my, -1)), ('E', (mx, 1)), ('W', (mx, -1))):
                if coord * sign < half * 0.55:
                    continue
                if (side in 'NS' and not facing_y) or (side in 'EW' and not facing_x):
                    continue
                u_of = (lambda x, y: x) if side in 'NS' else (lambda x, y: y)
                us = [u_of(ax, ay), u_of(bx, by), u_of(cx, cy)]
                zs = [az, bz, cz]
                u0, u1 = max(-half, min(us)), min(half, max(us))
                z0, z1 = max(zlo, min(zs)), min(zhi, max(zs))
                if u1 <= u0 or z1 <= z0:
                    continue
                where[side][0] += coord * sign * area
                where[side][1] += area
                g = grids[side]
                for i in range(int((u0 + half) / tile * G), min(G, int(math.ceil((u1 + half) / tile * G)))):
                    for j in range(int((z0 - zlo) / height * G), min(G, int(math.ceil((z1 - zlo) / height * G)))):
                        g[i][j] = 1
    out = {'cover': {}, 'offset': {}}
    for side in SIDES:
        g = grids[side]
        low = range(1, G // 2)                       # the lower half: where you'd walk through
        cover = sum(g[i][j] for i in range(G) for j in low) / float(G * len(low))
        middle = sum(g[i][j] for i in range(G // 2 - 2, G // 2 + 2) for j in low) / float(4 * len(low))
        out['cover'][side] = round(cover, 2)
        out['offset'][side] = round(where[side][0] / where[side][1], 1) if where[side][1] else half - 16
        out.setdefault('middle', {})[side] = round(middle, 2)
        if cover >= 0.7 or (cover >= 0.55 and middle >= 0.8):
            out[side] = 'wall'                      # (rounded corners leave the ends of a wall open)
        elif cover >= 0.25 and middle < 0.2:
            out[side] = 'door'                      # a wall with a doorway cut into it
        else:
            out[side] = 'open'
    out['floor'] = floor > tile * tile * 0.3
    out['ceiling'] = ceiling > tile * tile * 0.3
    _cache[key] = out
    return out


def _hole(db, ri, axis, band=None, G=40):
    """The walk-through hole in a wall-like model, seen along an axis ('x': faces looking along X,
    'y': along Y). band = (lo, hi) limits which faces count by their position on that axis.
    Returns (width, height of the hole's top above the floor, middle of the hole) or None."""
    shapes = _model(db, ri)
    b = mapdata.object_bounds(db, ri)
    if not shapes or not b:
        return None
    ui = 1 if axis == 'x' else 0                 # the other horizontal axis runs along the wall
    ai = 0 if axis == 'x' else 1
    u0, u1, z0, z1 = b[ui], b[ui + 3], b[2], b[5]
    if u1 - u0 < 1 or z1 - z0 < 1:
        return None
    g = [[0] * G for _ in range(G)]
    for s in shapes:
        p, idx = s['p'], s['i']
        for t in range(0, len(idx) - 2, 3):
            vs = [p[idx[t + k] * 3:idx[t + k] * 3 + 3] for k in range(3)]
            ux, uy, uz = (vs[1][k] - vs[0][k] for k in range(3))
            vx, vy, vz = (vs[2][k] - vs[0][k] for k in range(3))
            n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            if abs(n[ai]) < max(abs(n[ui]), abs(n[2])) * 1.2:
                continue                             # not facing along the axis
            if band and not all(band[0] <= v[ai] <= band[1] for v in vs):
                continue
            us = [v[ui] for v in vs]
            zs = [v[2] for v in vs]
            for i in range(max(0, int((min(us) - u0) / (u1 - u0) * G)), min(G, int(math.ceil((max(us) - u0) / (u1 - u0) * G)))):
                for j in range(max(0, int((min(zs) - z0) / (z1 - z0) * G)), min(G, int(math.ceil((max(zs) - z0) / (z1 - z0) * G)))):
                    g[i][j] = 1
    cu, cw, ch = (u1 - u0) / G, None, (z1 - z0) / G
    mid = G // 2
    if g[mid][1] or g[mid][2]:
        return None                                  # no hole at the middle bottom
    left = mid
    while left > 0 and not g[left - 1][2]:
        left -= 1
    right = mid
    while right < G - 1 and not g[right + 1][2]:
        right += 1
    top = 1
    while top < G and not g[mid][top]:
        top += 1
    return ((right - left + 1) * cu, top * ch, u0 + (left + right + 1) / 2.0 * cu)


_holes = {}


def doorway(db, ri, side, tile):
    """The doorway in one side of a floor piece (in the piece's own coordinates): (width, height,
    middle along the side) or None."""
    key = ('side', ri, side, tile)
    if key not in _holes:
        half = tile / 2.0
        axis = 'y' if side in 'NS' else 'x'
        sign = 1 if side in 'NE' else -1
        band = (half * 0.45, half * 1.05) if sign > 0 else (-half * 1.05, -half * 0.45)
        _holes[key] = _hole(db, ri, axis, band)
    return _holes[key]


def frame_hole(db, ri):
    """A door frame's outside size and the hole in it: (outer width, outer height, hole width,
    hole height) or None."""
    key = ('frame', ri)
    if key not in _holes:
        b = mapdata.object_bounds(db, ri)
        out = None
        if b:
            axis = 'y' if (b[4] - b[1]) < (b[3] - b[0]) else 'x'
            h = _hole(db, ri, axis)
            ow = max(b[3] - b[0], b[4] - b[1])
            if h:
                out = (ow, b[5] - b[2], h[0], h[1])
        _holes[key] = out
    return _holes[key]


def _curved(pat, rid):
    """Styles with curved walls (Telvanni) bow the walls into the tile, away from its edge, so they
    measure as only partly there. A piece named as a corner or a side whose walls are clearly where
    its name says gets them counted as walls."""
    c = pat.get('cover', {})
    if not c:
        return pat
    # how many walls the name says it has, and how they stand: corners two side by side, halls two
    # facing each other, end caps three, a three-way one
    if re.search(r'4way|center|centre', rid):
        return pat
    if re.search(r'endcap|_end|_cap', rid):
        want, shape = 3, 'any'
    elif re.search(r'corner|cornr|_cnr', rid):
        want, shape = 2, 'adjacent'
    elif re.search(r'3way', rid):
        want, shape = 1, 'any'
    elif re.search(r'hall', rid):
        want, shape = 2, 'opposite'
    elif re.search(r'side|wall', rid):
        want, shape = 1, 'any'
    else:
        return pat
    if sum(1 for s in SIDES if pat[s] == 'wall') >= want:
        return pat
    # (the doorways of a hall piece are its ends, not walls)
    order = sorted((s for s in SIDES if pat[s] != 'door'), key=lambda s: -c.get(s, 0))
    if len(order) < want:
        return pat
    top, rest = order[:want], order[want:]
    if shape == 'adjacent' and (SIDES.index(top[1]) - SIDES.index(top[0])) % 2 != 1:
        return pat
    if shape == 'opposite' and (SIDES.index(top[1]) - SIDES.index(top[0])) % 2 != 0:
        return pat
    low_rest = max((c.get(s, 0) for s in rest), default=0)
    if min(c.get(s, 0) for s in top) >= 0.3 and low_rest <= min(c.get(s, 0) for s in top) * 0.75:
        pat = dict(pat)
        for s in top:
            pat[s] = 'wall'
    return pat


def rotate(pattern, quarter):
    """The pattern after turning the piece clockwise by quarter * 90 degrees."""
    out = dict(pattern)
    cover, offset = {}, {}
    for n, s in enumerate(SIDES):
        t = SIDES[(n + quarter) % 4]
        out[t] = pattern[s]
        cover[t] = pattern.get('cover', {}).get(s, 0)
        offset[t] = pattern.get('offset', {}).get(s, 0)
    out['cover'], out['offset'] = cover, offset
    return out


# ------------------------------------------------------------------ finding kits
STYLE_KITS = {}
# words that name a kind of piece; a kit's name is everything before the first of them
PIECE_WORDS = {'room', 'roomt', 'hall', 'hallt', 'hallway', 'wall', 'corner', 'center', 'centre', 'side', 'door',
               'doorway', 'entry', 'jamb', 'doorjamb', 'end', '3way', '4way', 'post', 'rail', 'stair', 'stairs', 'stairsl',
               'stairsr', 'ramp', 'floor', 'ceiling', 'pillar', 'column', 'arch'}


def kit_prefix(rid):
    parts = rid.lower().split('_')
    for n, w in enumerate(parts):
        # (Tamriel Data's Hlaalu manor set names its room pieces LedgeWallSide, LedgeWallCorIn, NoFloor_Side...)
        if n >= 2 and (w in PIECE_WORDS or re.match(r'^(room|hall|corner|wall|door|center|side|ledgewall|nofloor)', w)):
            return '_'.join(parts[:n])
    return None


def kits(db):
    """Building kits found in the load order: prefix -> {tile, pieces: [{id, pattern, uses, size}]}."""
    if STYLE_KITS.get('_recs') is db.recs:
        return STYLE_KITS['kits']
    groups = {}
    for (tag, key), lst in db.by_key.items():
        if tag != 'STAT' or not lst or lst[-1] in db.dead:
            continue
        if not (key.startswith('in_') or re.match(r'^t_[a-z]+_set', key)):
            continue
        prefix = kit_prefix(key)
        if prefix:
            groups.setdefault(prefix, []).append(lst[-1])
    out = {}
    for prefix, ris in groups.items():
        if len(ris) < 6:
            continue
        sizes = []
        for ri in ris:
            b = mapdata.object_bounds(db, ri)
            if b:
                w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
                if h > 150 and abs(w - d) < 40 and w > 200:
                    sizes.append(round(max(w, d) / 64.0) * 64)
        if not sizes:
            continue
        tile = max(set(sizes), key=sizes.count)
        out[prefix] = {'prefix': prefix, 'tile': tile, 'ris': ris,
                       'uses': sum(game_uses(db, db.recs[ri][1].lower()) for ri in ris)}
    STYLE_KITS.update({'_recs': db.recs, 'kits': out})
    return out


def kit_pieces(db, prefix):
    k = kits(db).get(prefix)
    if not k:
        return None
    if 'pieces' in k:
        return k
    tile = k['tile']
    pieces, halves = [], []
    # a set whose floor is a flat slab of its own under wall-and-ceiling pieces (Tamriel Data's Hlaalu
    # manor: Floor_01 under LedgeWallSide_01): the slab, so the floorless pieces count, with it under them
    slab = None
    for ri in k['ris']:
        b = mapdata.object_bounds(db, ri)
        low = db.recs[ri][1].lower()
        if b and 'floor' in low and 'nofloor' not in low and b[5] - b[2] <= 8 and abs(b[3] - b[0] - tile) < tile * 0.12 \
                and abs(b[4] - b[1] - tile) < tile * 0.12 and abs(b[0] + b[3]) < tile * 0.12 and abs(b[1] + b[4]) < tile * 0.12:
            u = game_uses(db, low)
            if slab is None or u > slab['uses']:
                slab = {'id': db.recs[ri][1], 'ri': ri, 'zmin': b[2], 'uses': u}
    for ri in k['ris']:
        b = mapdata.object_bounds(db, ri)
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        rid = db.recs[ri][1]
        low = rid.lower()
        if 'stair' in low or 'ramp' in low or h > tile * 1.5:
            continue
        # a full tile, centred on its origin
        if not (abs(w - tile) < tile * 0.12 or abs(d - tile) < tile * 0.12) or max(w, d) > tile * 1.15:
            continue
        if abs((b[0] + b[3]) / 2) > tile * 0.12 or abs((b[1] + b[4]) / 2) > tile * 0.12:
            continue
        pat = measure(db, ri, tile)
        if not pat:
            continue
        # (only one that stands on the slab: not the set's "NoFloor" pieces for a storey above, whose
        # bottom is a floor's thickness up)
        floorless = not pat['floor']
        if floorless and not (slab and b[2] <= slab['zmin'] + 16 and (pat.get('ceiling') or any(pat[s] == 'wall' for s in SIDES))):
            continue
        pat = _curved(pat, low)
        item = {'id': rid, 'ri': ri, 'pattern': pat, 'uses': game_uses(db, low), 'zmin': b[2], 'height': h,
                'floorless': floorless}
        # a half-length piece (a hall piece 128 long): open at both short ends, it fills only half a
        # tile, so it isn't one (two of them end to end are)
        short = 'x' if w < tile * 0.7 else 'y' if d < tile * 0.7 else None
        if short and all(pat[s] != 'wall' for s in (('E', 'W') if short == 'x' else ('N', 'S'))):
            item.update(axis=short, length=w if short == 'x' else d)
            halves.append(item)
            continue
        pieces.append(item)
    # door frames that sit in a doorway between two tiles, and plain wall sections
    jambs, walls, door_walls = [], [], []
    heights = sorted(p['height'] for p in pieces) or [tile]
    full_h = heights[len(heights) // 2]
    pieces = [p for p in pieces if p['height'] >= full_h * 0.5]      # (not a ceiling slab on its own)
    for ri in k['ris']:
        low = db.recs[ri][1].lower()
        b = mapdata.object_bounds(db, ri)
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        thin, long_ = min(w, d), max(w, d)
        named_jamb = 'jamb' in low and thin <= tile * 0.35 and tile * 0.25 <= long_ <= tile * 1.15 and full_h * 0.45 <= h <= full_h * 1.2
        if not named_jamb and (thin > tile * 0.35 or long_ < tile * 0.6 or long_ > tile * 1.15 or h < full_h * 0.8 or h > full_h * 1.2):
            continue
        if 'jamb' not in low and long_ < tile * 0.8:
            continue
        item = {'id': db.recs[ri][1], 'ri': ri, 'uses': game_uses(db, low), 'thin_x': w < d,
                'thick': thin, 'zmin': b[2], 'width': long_}
        if 'jamb' in low or 'doorway' in low or ('door' in low and 'load' not in low and 'jamb' in low):
            item['load'] = 'load' in low
            jambs.append(item)
        elif 'wall' in low and 'door' not in low and thin >= 3 and 'addon' not in low:
            walls.append(item)          # (not the paper-thin panels laid over walls for decoration)
        elif 'door' in low and 'load' not in low and 'trap' not in low and long_ >= tile * 0.9:
            # a wall section with a doorway through it (Tamriel Data's Redguard "Wall_Door"): the
            # same thing as a Hlaalu door frame, by another name, if there's a hole to walk through
            fh = frame_hole(db, ri)
            if fh and fh[2] >= 64 and fh[3] >= full_h * 0.6:
                item['load'] = False
                door_walls.append(item)
    entry = any(p['pattern'][s] == 'door' for p in pieces for s in SIDES)
    if not jambs and not entry:
        jambs = door_walls              # (only for a style with no other way of making a doorway)
    # (a floorless piece only where no piece with a floor has that shape: a set's "no floor" variants of
    # its ordinary pieces are for storeys above, not the ground)
    # (unless the game plainly prefers it: the Hlaalu manor's square ledge corner over its round one)
    canon = lambda pat: min(''.join(rotate(pat, q)[s][0] for s in SIDES) for q in range(4))
    floored = {}
    for p in pieces:
        if not p['floorless']:
            floored[canon(p['pattern'])] = max(floored.get(canon(p['pattern']), 0), p['uses'])
    pieces = [p for p in pieces if not p['floorless'] or p['uses'] > 1.5 * floored.get(canon(p['pattern']), -1)]
    k['pieces'] = sorted(pieces, key=lambda p: -p['uses'])
    k['slab'] = slab if any(p['floorless'] for p in pieces) else None
    k['halves'] = sorted(halves, key=lambda p: -p['uses'])
    k['jambs'] = sorted(jambs, key=lambda p: -p['uses'])
    k['walls'] = sorted(walls, key=lambda p: -p['uses'])
    # how this style makes doorways: a full-width frame between two open tiles (Hlaalu), or
    # a doorway built into a floor piece's wall (most others)
    k['frame_doors'] = any(j['width'] >= tile * 0.9 for j in jambs)
    k['entry_doors'] = entry
    zs = sorted(p['zmin'] for p in pieces) or [0]
    k['zmin'] = zs[len(zs) // 2]
    k['height'] = full_h
    return k


_fits = {}


def door_fits(db, prefix):
    """How the original game fills the doorways of this kit's floor pieces: {(piece id, side in
    the piece's own frame): {'door', 'scale', 'x', 'y', 'z', 'rz' (all relative to the piece),
    'extra': [(id, x, y, z, rz, scale)] (frames and the like around it, relative to the piece),
    'load': it is a load door}}, picked from the commonest way each doorway is used."""
    k = kit_pieces(db, prefix)
    if not k:
        return {}
    if prefix in _fits and _fits[prefix][0] is db.recs:
        return _fits[prefix][1]
    from mapdata import ref_info
    T = k['tile']
    tag_of = {}

    def tag(rid):
        if rid not in tag_of:
            ri = db.resolve_id(rid)
            tag_of[rid] = db.recs[ri][0] if ri is not None else None
        return tag_of[rid]
    floor_ids = {p['id'].lower() for p in k['pieces']}
    counts = {}
    for p in k['pieces']:
        sides = [s for s in SIDES if p['pattern'][s] == 'door']
        if not sides:
            continue
        low = p['id'].lower()
        for ci in list(db.used_in.get(low, ()))[:40]:
            r = db.recs[ci]
            if r[0] != 'CELL' or not game_made(db, r[7]):
                continue
            refs, _h = db.cell_refs(r[7])
            items = []
            for ref in refs.values():
                rid, pos, sc, dead = ref_info(ref['subs'])
                if not dead:
                    items.append((rid, pos, sc or 1.0, any(t == 'DODT' for t, _d in ref['subs'])))
            for rid, pos, sc, _l in items:
                if rid.lower() != low or abs(sc - 1) > 0.01:
                    continue
                rz = pos[5]
                for s in sides:
                    vx, vy = _VEC[s]
                    best = None
                    for did, dpos, dsc, dload in items:
                        if tag(did.lower()) != 'DOOR':
                            continue
                        dx, dy = dpos[0] - pos[0], dpos[1] - pos[1]
                        lx, ly = dx * math.cos(rz) - dy * math.sin(rz), dx * math.sin(rz) + dy * math.cos(rz)
                        along, out = (lx, ly) if s in 'NS' else (ly, lx)
                        out *= (vy if s in 'NS' else vx)
                        if not (T * 0.25 < out < T * 0.62 and abs(along) < T * 0.4 and abs(dpos[2] - pos[2]) < T):
                            continue
                        dd = abs(out - T / 2) + abs(along)
                        if best is None or dd < best[0]:
                            best = (dd, did, dpos, dsc, dload, lx, ly)
                    if not best:
                        continue
                    _dd, did, dpos, dsc, dload, lx, ly = best
                    # what stands right around the door: frames, jambs, a step
                    extra = []
                    for oid, opos, osc, _ol in items:
                        olow = oid.lower()
                        if olow in floor_ids or tag(olow) not in ('STAT',) or (oid, tuple(opos)) == (did, tuple(dpos)):
                            continue
                        # (a door's origin is often its hinge, so the frame round it can be a way off)
                        framey = any(w in olow for w in ('jamb', 'frame', 'door', 'arch', 'trim')) or kit_prefix(olow) == prefix
                        if framey and math.hypot(opos[0] - dpos[0], opos[1] - dpos[1]) < 150 and abs(opos[2] - dpos[2]) < 160:
                            ex, ey = opos[0] - pos[0], opos[1] - pos[1]
                            elx, ely = ex * math.cos(rz) - ey * math.sin(rz), ex * math.sin(rz) + ey * math.cos(rz)
                            eout = (ely * vy) if s in 'NS' else (elx * vx)
                            if not T * 0.3 < eout < T * 0.62:
                                continue                    # it belongs to another side of the piece
                            extra.append((oid, round(elx, 1), round(ely, 1), round(opos[2] - pos[2], 1),
                                          round((opos[5] - rz) % (2 * math.pi), 3), round(osc, 3)))
                    key = (p['id'], s, did.lower(), round(dsc, 2), round(lx / 6), round(ly / 6), round((dpos[2] - pos[2]) / 6),
                           round(((dpos[5] - rz) % (2 * math.pi)) / (math.pi / 2)) % 4, tuple(sorted(e[0].lower() for e in extra)))
                    c = counts.setdefault(key, {'n': 0, 'load': 0, 'sample': None})
                    c['n'] += 1
                    c['load'] += 1 if dload else 0
                    if c['sample'] is None:
                        c['sample'] = {'door': did, 'scale': dsc, 'x': lx, 'y': ly, 'z': dpos[2] - pos[2],
                                       'rz': (dpos[5] - rz) % (2 * math.pi), 'extra': extra}
    out = {}
    for key, c in counts.items():
        pk = (key[0], key[1])
        # ordinary doors (not a jail door, a trapdoor or a secret one), load doors (it is the way out),
        # then the commonest
        plain = not any(w in key[2] for w in ('jail', 'trap', 'cell', 'cage', 'secret', 'hidden', 'vault'))
        score = (plain, c['load'] > 0, c['n'])
        if pk not in out or score > out[pk][0]:
            out[pk] = (score, dict(c['sample'], load=c['load'] > 0, uses=c['n'], plain=plain))
    res = {pk: v[1] for pk, v in out.items()}
    _fits[prefix] = (db.recs, res)
    return res


_stairs = {}
MEASURED_STAIRS = True           # (stairs measured from their models, where the game's own use can't teach them)


def stairs(db, prefix):
    """The kit's stair pieces and how the original game joins them to floors, learnt from the
    places that use them: {'storey': height between floors, 'pieces': [{id, ri, low (side the low
    end opens to, in the piece's own frame), z_low (a lower floor piece's origin height relative to
    the stair's), rise, open (other sides that open into a room), uses}]}, or None."""
    k = kit_pieces(db, prefix)
    if not k:
        return None
    if prefix in _stairs and _stairs[prefix][0] is db.recs:
        return _stairs[prefix][1]
    from mapdata import ref_info
    T = k['tile']
    floor_ids = {p['id'].lower(): p for p in k['pieces']}
    is_stair = lambda rid: any(w in rid for w in ('stair', 'ramp'))
    out = []
    for ri in _stair_ris(db, k):
        sid = db.recs[ri][1].lower()
        if not is_stair(sid):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or max(b[3] - b[0], b[4] - b[1]) > T * 1.15:
            continue                                  # only stairs one tile across
        seen = 0
        near = {}                                      # (dx, dy) in tiles -> {dz: count}
        opening = {}                                   # (dx, dy) -> floors beside it that are open towards it
        posts = {}                                     # posts standing at its corners -> count
        for ci in list(db.used_in.get(sid, ()))[:40]:
            r = db.recs[ci]
            if r[0] != 'CELL' or not game_made(db, r[7]):
                continue
            refs, _h = db.cell_refs(r[7])
            items = []
            for ref in refs.values():
                rid, pos, _s, dead = ref_info(ref['subs'])
                if not dead:
                    items.append((rid.lower(), pos))
            for rid, pos in items:
                if rid != sid:
                    continue
                seen += 1
                rz = pos[5]
                for rid2, p2 in items:
                    if any(w in rid2 for w in ('post', 'pillar', 'column')):
                        dx, dy = p2[0] - pos[0], p2[1] - pos[1]
                        lx, ly = dx * math.cos(rz) - dy * math.sin(rz), dx * math.sin(rz) + dy * math.cos(rz)
                        if abs(abs(lx) - T / 2) < 30 and abs(abs(ly) - T / 2) < 30:
                            posts[rid2] = posts.get(rid2, 0) + 1
                        continue
                    if rid2 not in floor_ids and not is_stair(rid2):
                        continue
                    dx, dy, dz = p2[0] - pos[0], p2[1] - pos[1], p2[2] - pos[2]
                    if abs(math.hypot(dx, dy) - T) > T * 0.12:
                        continue
                    lx, ly = dx * math.cos(rz) - dy * math.sin(rz), dx * math.sin(rz) + dy * math.cos(rz)
                    key = (int(round(lx / T)), int(round(ly / T)))
                    if abs(key[0]) + abs(key[1]) != 1:
                        continue
                    dzr = int(round(dz / 16.0) * 16)
                    near.setdefault(key, {}).setdefault(dzr, 0)
                    near[key][dzr] += 1
                    fp = floor_ids.get(rid2)
                    if fp:
                        # the side of that floor piece that faces the stair, in its own frame
                        wx, wy = -dx, -dy
                        r2 = p2[5]
                        fx, fy = wx * math.cos(r2) - wy * math.sin(r2), wx * math.sin(r2) + wy * math.cos(r2)
                        fs = next(s for s, v in _VEC.items() if v == (int(round(fx / T)), int(round(fy / T)))) \
                            if abs(round(fx / T)) + abs(round(fy / T)) == 1 else None
                        if fs and fp['pattern'][fs] != 'wall':
                            opening[key] = opening.get(key, 0) + 1
        if seen < 3:
            continue
        # the low end and the high end: opposite sides, each joined to a floor in most places
        best = None
        for s in SIDES:
            o = SIDES[(SIDES.index(s) + 2) % 4]
            a, c = near.get(_VEC[s], {}), near.get(_VEC[o], {})
            if not a or not c:
                continue
            za, na = max(a.items(), key=lambda kv: kv[1])
            zc, nc = max(c.items(), key=lambda kv: kv[1])
            if zc - za < T * 0.4 or min(na, nc) < seen * 0.5:
                continue
            score = min(na, nc)
            if best is None or score > best[0]:
                best = (score, s, za, zc - za)
        if not best:
            continue
        _sc, low, z_low, rise = best
        high = SIDES[(SIDES.index(low) + 2) % 4]
        open_ = [s for s in SIDES if s not in (low, high) and opening.get(_VEC[s], 0) > seen * 0.3]
        post = max(posts, key=posts.get) if posts else None
        post_ri = db.resolve_id(post) if post and posts[post] >= max(3, seen * 0.2) else None
        out.append({'id': db.recs[ri][1], 'ri': ri, 'low': low, 'z_low': z_low, 'rise': rise, 'open': open_,
                    'uses': game_uses(db, sid), 'height': b[5] - b[2],
                    # what covers the joins where an open side meets the walls beside it
                    'post': db.recs[post_ri][1] if post_ri is not None else None,
                    # what closes in the stairwell: [(id, height over the stairs, quarter turns)]
                    'cap': _stair_cap(db, prefix, sid, T)})
    res = None
    if not out and MEASURED_STAIRS:
        # the game never puts these stairs beside the kit's own floor tiles where they could be learnt
        # from: measure them instead
        z0 = -k['zmin']
        for ri in _stair_ris(db, k):
            sid = db.recs[ri][1].lower()
            if is_stair(sid):
                g = stair_shape(db, ri, T, k['height'])
                if g:
                    # (2 lower than flush: the game sets about one staircase in eight that way, and a stair
                    # exactly level with the floor can leave a hairline crack where they meet)
                    out.append(dict(g, id=db.recs[ri][1], ri=ri, z_low=z0 + g['bottom'] + 2, open=[], post=None,
                                    cap=_stair_cap(db, prefix, sid, T),
                                    uses=game_uses(db, sid)))
    if out:
        # the height between floors: what most stairs climb (or two short flights do), a little more
        # than a room is tall
        cands = [r for p in out for r in (p['rise'], p['rise'] * 2) if k['height'] * 0.95 <= r <= k['height'] * 1.45]
        storey = max(set(cands), key=lambda r: (cands.count(r), -r)) if cands else 0
        if storey:
            pieces = [p for p in out if any(abs(p['rise'] * n - storey) < 8 for n in (1, 2))]
            # closed-in stairs first (nothing to patch around them), then the ones used most
            pieces.sort(key=lambda p: (len(p['open']), -p['uses']))
            if pieces:
                # a proper staircase that climbs a whole floor (not only ramps meant for halls): the
                # style looks right with stairs, so they are the default
                proper = any(abs(p['rise'] - storey) < 8 and 'ramp' not in p['id'].lower() for p in pieces)
                res = {'storey': storey, 'pieces': pieces, 'proper': proper}
    _stairs[prefix] = (db.recs, res)
    return res


_VEC = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}


def _stair_ris(db, k):
    """The records that may be this kit's stairs: its own, and the stairs its family keeps under the
    family's name with the kit's own word after "stair" (the Common sets: in_c_stair_plain_tall_01
    for in_c_plain, in_c_stair_rich_tall_01 for in_c_rich), which file under "in_c" otherwise."""
    out = list(k['ris'])
    pre = (k.get('prefix') or '').lower()
    parts = pre.split('_')
    if len(parts) >= 3:
        family, word = '_'.join(parts[:-1]), parts[-1]
        # (the family's other kits' words: a stair named for one of them is theirs; one named for none
        # is the family's, shared: in_impsmall_stairs_01 for in_impsmall_r)
        others = {p.split('_')[-1] for p in kits(db) if p.startswith(family + '_') and p != pre}
        seen = set(out)
        for (tag, key), lst in db.by_key.items():
            if tag != 'STAT' or not key.startswith(family + '_') or not ('stair' in key or 'ramp' in key):
                continue
            kparts = set(key.split('_'))
            if not (word in kparts or not (kparts & others)):
                continue
            if lst and lst[-1] not in db.dead and lst[-1] not in seen and kit_prefix(key) != pre:
                seen.add(lst[-1])
                out.append(lst[-1])
    return out


def _stair_cap(db, prefix, sid, T):
    """The pieces the game stands in the same spot as these stairs, to close in the stairwell: a room
    piece with no floor on top and a wall beside it (Indoril), or a room piece the stairs stand inside
    (Redoran): [(id, height over the stairs' origin, quarter turns from the stairs')], the common ones
    (in a quarter of the places or more), most common first; [] when there are none."""
    from mapdata import ref_info
    caps, seen = {}, 0
    for ci in list(db.used_in.get(sid, ()))[:40]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not game_made(db, r[7]):
            continue
        refs, _h = db.cell_refs(r[7])
        items = [(rid.lower(), pos) for rid, pos, _s, dead in (ref_info(x['subs']) for x in refs.values()) if not dead]
        for rid, pos in items:
            if rid != sid:
                continue
            seen += 1
            for rid2, p2 in items:
                if rid2 == sid or 'stair' in rid2 or 'ramp' in rid2 or not rid2.startswith(prefix.lower()):
                    continue
                if math.hypot(p2[0] - pos[0], p2[1] - pos[1]) < 24 and -T * 0.6 < p2[2] - pos[2] < T * 2.2:
                    dq = int(round(((p2[5] - pos[5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                    k = (rid2, int(round((p2[2] - pos[2]) / 16) * 16), dq)
                    caps[k] = caps.get(k, 0) + 1
    # (the game closes a stairwell several ways, a wall on this side or that, a floorless room piece
    # with its ceiling: all the fairly common ones, the builder takes those whose walls fit; of two
    # as common, the one that puts a ceiling over the stairwell first)
    out = []
    for (cid, dz, dq), n in caps.items():
        ri = db.resolve_id(cid)
        if ri is None or n < max(2, seen * 0.15):
            continue
        pat = measure(db, ri, T)
        out.append((-n, not (pat and pat.get('ceiling')), db.recs[ri][1], dz, dq))
    return [(cid, dz, dq) for _n, _c, cid, dz, dq in sorted(out)]


def stair_shape(db, ri, T, room_h):
    """A stair piece measured from its model: which side its low end is on ('low', in its own frame),
    how high its bottom and top steps are ('bottom', 'rise'), how many tiles long it is ('len'), and
    where the middle of the model is ('cx', 'cy'). None if it doesn't look like one tile-wide flight
    that climbs about one storey."""
    shapes = _model(db, ri)
    b = mapdata.object_bounds(db, ri)
    if not shapes or not b:
        return None
    ups = []                                         # (x, y, z, area) of faces you could stand on
    for s in shapes:
        p, idx = s['p'], s['i']
        for t in range(0, len(idx) - 2, 3):
            A, B, C = (p[idx[t + k] * 3:idx[t + k] * 3 + 3] for k in range(3))
            ux, uy, uz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
            vx, vy, vz = C[0] - A[0], C[1] - A[1], C[2] - A[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            area = math.sqrt(nx * nx + ny * ny + nz * nz)
            if area > 1 and nz / area > 0.9:
                ups.append(((A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3, (A[2] + B[2] + C[2]) / 3, area))
    if len(ups) < 4:
        return None
    best = None
    for axis, (lo, hi) in (('x', (b[0], b[3])), ('y', (b[1], b[4]))):
        ai = 0 if axis == 'x' else 1
        L = hi - lo
        if L < T * 0.8:
            continue
        width = (b[4] - b[1]) if axis == 'x' else (b[3] - b[0])
        ci = 1 - ai
        mid = (b[ci] + b[ci + 3]) / 2
        # the walking line up the middle: in slices along this axis, the heights you could stand at
        # (near the middle across, so the tops of side walls don't count), then the longest run of
        # them that only climbs, a step at a time
        N = 16
        bins = [{} for _ in range(N)]
        for u in ups:
            if abs(u[ci] - mid) > width * 0.3:
                continue
            k = min(N - 1, max(0, int((u[ai] - lo) / L * N)))
            z = round(u[2] / 4) * 4
            bins[k][z] = bins[k].get(z, 0) + u[3]
        res_axis = None
        for direction in (1, -1):
            order = bins if direction == 1 else bins[::-1]
            # paths[z] = (covered slices, area, first z) for paths ending at height z
            paths = {}
            for sl in order:
                nxt = dict(paths)
                for z, a in sl.items():
                    cand = (1, a, z)
                    for pz, (n, pa, z0) in paths.items():
                        if -6 <= z - pz <= room_h * 0.3 and (n + 1, pa + a) > cand[:2]:
                            cand = (n + 1, pa + a, z0)
                    if z not in nxt or cand[:2] > nxt[z][:2]:
                        nxt[z] = cand
                paths = nxt
            if not paths:
                continue
            ztop, (n, _a, zbot) = max(paths.items(), key=lambda kv: (kv[1][0], kv[0] - kv[1][2]))
            if n >= N * 0.5 and ztop - zbot >= room_h * 0.8 and (res_axis is None or ztop - zbot > res_axis[1] - res_axis[0]):
                res_axis = (zbot, ztop, direction)
        if not res_axis:
            continue
        za, zc, direction = res_axis
        # the treads stop a step short of a floor at one end or the other: one step's height, from
        # the heights the treads stand at
        levels = sorted({z for sl in bins for z in sl if za - 2 <= z <= zc + 2})
        diffs = sorted(d for d in (b_ - a_ for a_, b_ in zip(levels, levels[1:])) if d >= 8)
        step = diffs[len(diffs) // 2] if diffs else 0
        if step and 2 < za - b[2] <= step * 1.5:
            za = b[2]                                 # the first tread is a step up from the floor below
        # and floors stand on the game's 64-unit grid: the climb is a whole number of those
        rise = max(64, round((zc - za) / 64.0) * 64)
        low = ('W' if axis == 'x' else 'S') if direction == 1 else ('E' if axis == 'x' else 'N')
        if width > T * 1.2:
            continue                                 # (wider than a tile: a stairwell of its own)
        n = max(1, int(round(L / T)))
        if n > 3:
            continue
        score = rise
        if best is None or score > best[0]:
            best = (score, {'low': low, 'bottom': za, 'rise': rise, 'len': n, 'cx': (b[0] + b[3]) / 2,
                            'cy': (b[1] + b[4]) / 2, 'height': b[5] - b[2]})
    return best[1] if best else None


_YAW = {'N': 0.0, 'E': math.pi / 2, 'S': math.pi, 'W': 3 * math.pi / 2}
_edges = {}
NOT_PART = ('furn', 'light', 'rug', 'active', 'flora', 'misc', 'contain', 'com_', 'book', 'banner', 'tapestr')


def edge_doors(db, prefix):
    """How the original game makes doorways on the edge between two of this kit's floor tiles (or
    between a tile and the outside), learnt from the places built with it. Many styles have no floor
    piece with a doorway in it: they leave the tile's side open and stand a separate door frame,
    a door and maybe a short wall or pillar on the edge instead.
    Returns [{'a': the tile's side ('open'|'door'|'wall'), 'b': the other tile's side, or 'out' when
    nothing is beyond, 'load': the door leads somewhere else, 'door': the door's id or None,
    'parts': [(id, along, across, z, rz, scale)], 'uses'}], commonest first. Positions are relative
    to the middle of the edge at the tile's floor piece, 'across' pointing out of the tile and
    'along' to its right; rz is relative to the side's direction (clockwise, like the game)."""
    k = kit_pieces(db, prefix)
    if not k:
        return []
    if prefix in _edges and _edges[prefix][0] is db.recs:
        return _edges[prefix][1]
    from mapdata import ref_info
    T = k['tile']
    floor_ids = {p['id'].lower(): p for p in k['pieces']}
    family = '_'.join(prefix.split('_')[:3]) if prefix.startswith('t_') else '_'.join(prefix.split('_')[:2])
    tag_of = {}

    def tag(rid):
        if rid not in tag_of:
            ri = db.resolve_id(rid)
            tag_of[rid] = db.recs[ri][0] if ri is not None else None
        return tag_of[rid]

    def part_like(rid):
        if rid in floor_ids or any(w in rid for w in NOT_PART):
            return False
        if any(w in rid for w in ('trap', 'hatch', 'jail', 'cage', 'secret', 'hidden')):
            return False                         # (not the doors and frames of an ordinary doorway)
        return rid.startswith(family) or any(w in rid for w in ('jamb', 'frame', 'arch', 'door', 'pillar', 'post', 'column'))

    bottoms = {}

    def bottom(rid, z, sc):
        """How high the bottom of an object stands, from where its origin is."""
        if rid not in bottoms:
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            bottoms[rid] = b[2] if b else 0.0
        return z + bottoms[rid] * sc
    stand = T * 0.2          # how far off the floor a door or frame may stand and still belong to it
    widths = {}

    def widest(rid):
        if rid not in widths:
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            widths[rid] = max(b[3] - b[0], b[4] - b[1]) if b else 0.0
        return widths[rid]

    def covered(parts):
        """How much of the edge (along it) the parts stand across."""
        spans = sorted((max(-T / 2, p[1] - widest(p[0]) * p[5] / 2), min(T / 2, p[1] + widest(p[0]) * p[5] / 2)) for p in parts)
        total, end = 0.0, -T / 2
        for lo, hi in spans:
            lo = max(lo, end)
            if hi > lo:
                total += hi - lo
                end = hi
        return total

    cells = {}
    for pid in floor_ids:
        for ci in db.used_in.get(pid, ()):
            cells[ci] = cells.get(ci, 0) + 1
    counts = {}
    for ci in sorted(cells, key=lambda c: -cells[c])[:120]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not game_made(db, r[7]):
            continue
        refs, _h = db.cell_refs(r[7])
        floors, others = [], []
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead:
                continue
            low = rid.lower()
            sc = sc or 1.0
            if low in floor_ids and abs(sc - 1) < 0.01:
                floors.append((low, pos))
            elif tag(low) in ('STAT', 'DOOR') and part_like(low):
                others.append((low, pos, sc, any(t == 'DODT' for t, _d in ref['subs'])))
        if not floors:
            continue
        at = {}
        for low, pos in floors:
            at[(round(pos[0] / 8), round(pos[1] / 8), round(pos[2] / 8))] = (low, pos)

        def tile_near(x, y, z):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        got = at.get((round(x / 8) + dx, round(y / 8) + dy, round(z / 8) + dz))
                        if got:
                            return got
            return None

        # each edge with a door or a door frame on it, from the tiles on both sides
        seen_edges = set()
        for oid, opos, osc, oload in others:
            if tag(oid) != 'DOOR' and not any(w in oid for w in ('jamb', 'frame', 'doorway', 'arch')):
                continue
            for low, pos in floors:
                floor_z = pos[2] + floor_ids[low]['zmin']
                if abs(bottom(oid, opos[2], osc) - floor_z) > stand:
                    continue                     # (on another floor: places like Vivec stack them close)
                dx, dy = opos[0] - pos[0], opos[1] - pos[1]
                if abs(dx) > T or abs(dy) > T:
                    continue
                for s, (vx, vy) in _VEC.items():
                    out = dx * vx + dy * vy
                    along = dx * vy - dy * vx
                    if not (T * 0.3 < out < T * 0.66 and abs(along) < T * 0.3):
                        continue
                    ek = (round(pos[0] + vx * T / 2), round(pos[1] + vy * T / 2), round(pos[2]), s in 'NS')
                    if (ek, low, round(pos[0]), round(pos[1])) in seen_edges:
                        continue
                    seen_edges.add((ek, low, round(pos[0]), round(pos[1])))
                    q = round(((pos[5] % (2 * math.pi)) / (math.pi / 2))) % 4
                    a = rotate(floor_ids[low]['pattern'], q)[s]
                    nbt = tile_near(pos[0] + vx * T, pos[1] + vy * T, pos[2])
                    if nbt:
                        q2 = round(((nbt[1][5] % (2 * math.pi)) / (math.pi / 2))) % 4
                        b = rotate(floor_ids[nbt[0]]['pattern'], q2)[SIDES[(SIDES.index(s) + 2) % 4]]
                    else:
                        b = 'out'
                    # everything standing on this edge, in the edge's own frame
                    th = _YAW[s]
                    ox, oy = pos[0] + vx * T / 2, pos[1] + vy * T / 2
                    parts, door, load = [], None, False
                    for pid, ppos, psc, pload in others:
                        pb = bottom(pid, ppos[2], psc)
                        if pb < floor_z - stand or pb > floor_z + floor_ids[low]['height'] * 0.8 or \
                                (tag(pid) == 'DOOR' and abs(pb - floor_z) > stand):
                            continue
                        ex, ey = ppos[0] - ox, ppos[1] - oy
                        lx, ly = ex * math.cos(th) - ey * math.sin(th), ex * math.sin(th) + ey * math.cos(th)
                        if abs(ly) > T * 0.22 or abs(lx) > T * 0.56:
                            continue
                        if tag(pid) == 'DOOR':
                            if door is not None:
                                continue
                            door, load = pid, pload
                        parts.append((pid, round(lx, 1), round(ly, 1), round(ppos[2] - pos[2], 1),
                                      round((ppos[5] - th) % (2 * math.pi), 3), round(psc, 3)))
                    if not parts:
                        continue
                    framey = [p for p in parts if any(w in p[0] for w in ('jamb', 'frame', 'arch', 'doorway')) or
                              re.search(r'_dj(_|\d|$)', p[0])]
                    if any(abs(p[1]) > T * 0.25 for p in framey):
                        continue                 # a doorway on the corner between two tiles: not one edge's
                    if a == 'open' and b == 'out' and covered(parts) < T * 0.85:
                        continue                 # something else filled the rest of that edge in the game
                    key = (a, b, load, tuple(sorted((p[0], round(p[1] / 8), round(p[2] / 8), round(p[3] / 8),
                                                     round(p[4] / (math.pi / 2)) % 4) for p in parts)))
                    c = counts.setdefault(key, {'n': 0, 'sample': None, 'under': {}})
                    c['n'] += 1
                    if c['sample'] is None:
                        c['sample'] = {'a': a, 'b': b, 'load': load, 'door': door, 'parts': parts}
                    # the floor piece the game puts under it (often one made for the doorway), by its own side
                    own = SIDES[(SIDES.index(s) - q) % 4]
                    c['under'][(low, own)] = c['under'].get((low, own), 0) + 1
    res = []
    for _k, c in sorted(counts.items(), key=lambda kv: -kv[1]['n']):
        if c['n'] < 2:
            continue
        (pid, own), n = max(c['under'].items(), key=lambda kv: kv[1])
        res.append(dict(c['sample'], uses=c['n'], piece=floor_ids[pid]['id'], piece_side=own, piece_uses=n))
    _edges[prefix] = (db.recs, res)
    return res


def friendly(prefix):
    """A readable name for a kit, e.g. in_hlaalu -> Hlaalu, t_de_setind_i -> Indoril (TR)."""
    fixed = {'in_t_s': 'Telvanni (small)', 'in_t_l': 'Telvanni (large)', 'in_t_s_plain': 'Telvanni (small, plain)',
             'in_r_s_int': 'Redoran (small)', 'in_r_l_int': 'Redoran (large)', 'in_v_s_int': 'Vivec (small)',
             'in_v_l_int': 'Vivec (large)', 'in_mh_int': 'Mournhold', 'in_m_sewer': 'Mournhold sewer'}
    if prefix in fixed:
        return fixed[prefix]
    words =[w for w in prefix.split('_') if w not in ('in', 't', 'i', 'set', 'int')]
    names = {'hlaalu': 'Hlaalu', 'velothismall': 'Velothi (small)', 'velothilarge': 'Velothi (large)', 'dae': 'Daedric ruin',
             'impsmall': 'Imperial (small)', 'c': 'Common', 'plain': 'plain', 'rich': 'rich', 'stone': 'stone',
             'mh': 'Mournhold', 'dwrv': 'Dwemer', 'strong': 'Stronghold', 'stronghold': 'Stronghold', 'om': 'Old Mournhold',
             'v': 'Vivec', 's': 'small', 'l': 'large', 'redoran': 'Redoran', 'r': 'rich', 'ashl': 'Ashlander',
             'moldcave': 'Mold cave', 't': 'Telvanni', 'de': 'Dunmer', 'imp': 'Imperial', 'gc': 'Gold Coast',
             'ind': 'Indoril', 'cha': 'chapel', 'hla': 'Hlaalu', 'veloth': 'Velothi', 'necrom': 'Necrom',
             'nor': 'Nordic', 'rga': 'Redguard', 'reach': 'Reach', 'com': 'Common', 'mine': 'mine',
             'sewer': 'sewer', 'sewerl': 'sewer (large)', 'nord': 'Nordic', 'bre': 'Breton', 'cyr': 'Cyrodiilic',
             'he': 'High Elf', 'sky': 'Skyrim', 'dwrv': 'Dwemer', 'dwe': 'Dwemer', 'tel': 'Telvanni', 'red': 'Redoran'}
    tr = prefix.startswith('t_')
    out = []
    for w in words:
        w2 = w[3:] if w.startswith('set') else w
        out.append(names.get(w2, w2.capitalize()))
    return ' '.join(out) + (' (Tamriel Data)' if tr else '')
