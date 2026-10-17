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
        if cover >= 0.7:
            out[side] = 'wall'
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
               'doorway', 'entry', 'jamb', 'doorjamb', 'end', '3way', '4way', 'post', 'rail', 'stairs', 'stairsl',
               'stairsr', 'ramp', 'floor', 'ceiling', 'pillar', 'column', 'arch'}


def kit_prefix(rid):
    parts = rid.lower().split('_')
    for n, w in enumerate(parts):
        if n >= 2 and (w in PIECE_WORDS or re.match(r'^(room|hall|corner|wall|door|center|side)', w)):
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
                       'uses': sum(len(db.used_in.get(db.recs[ri][1].lower(), ())) for ri in ris)}
    STYLE_KITS.update({'_recs': db.recs, 'kits': out})
    return out


def kit_pieces(db, prefix):
    k = kits(db).get(prefix)
    if not k:
        return None
    if 'pieces' in k:
        return k
    tile = k['tile']
    pieces = []
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
        if not pat or not pat['floor']:
            continue
        pieces.append({'id': rid, 'ri': ri, 'pattern': pat, 'uses': len(db.used_in.get(low, ())),
                       'zmin': b[2], 'height': h})
    # door frames that sit in a doorway between two tiles, and plain wall sections
    jambs, walls = [], []
    heights = sorted(p['height'] for p in pieces) or [tile]
    full_h = heights[len(heights) // 2]
    for ri in k['ris']:
        low = db.recs[ri][1].lower()
        b = mapdata.object_bounds(db, ri)
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        thin, long_ = min(w, d), max(w, d)
        if thin > tile * 0.35 or long_ < tile * 0.6 or long_ > tile * 1.15 or h < full_h * 0.8 or h > full_h * 1.2:
            continue
        if 'jamb' not in low and long_ < tile * 0.8:
            continue
        item = {'id': db.recs[ri][1], 'ri': ri, 'uses': len(db.used_in.get(low, ())), 'thin_x': w < d,
                'thick': thin, 'zmin': b[2], 'width': long_}
        if 'jamb' in low or 'doorway' in low or ('door' in low and 'load' not in low and 'jamb' in low):
            item['load'] = 'load' in low
            jambs.append(item)
        elif 'wall' in low and 'door' not in low:
            walls.append(item)
    k['pieces'] = sorted(pieces, key=lambda p: -p['uses'])
    k['jambs'] = sorted(jambs, key=lambda p: -p['uses'])
    k['walls'] = sorted(walls, key=lambda p: -p['uses'])
    # how this style makes doorways: a full-width frame between two open tiles (Hlaalu), or
    # a doorway built into a floor piece's wall (most others)
    k['frame_doors'] = any(j['width'] >= tile * 0.9 for j in jambs)
    k['entry_doors'] = any(p['pattern'][s] == 'door' for p in pieces for s in SIDES)
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
            if r[0] != 'CELL':
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
    for ri in k['ris']:
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
            if r[0] != 'CELL':
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
                    'uses': len(db.used_in.get(sid, ())), 'height': b[5] - b[2],
                    # what covers the joins where an open side meets the walls beside it
                    'post': db.recs[post_ri][1] if post_ri is not None else None})
    res = None
    if out:
        top = max(p['rise'] for p in out)
        storey = top if top >= T * 0.75 else top * 2
        if k['height'] <= storey <= k['height'] * 1.4:
            pieces = [p for p in out if any(abs(p['rise'] * n - storey) < 8 for n in (1, 2))]
            # closed-in stairs first (nothing to patch around them), then the ones used most
            pieces.sort(key=lambda p: (len(p['open']), -p['uses']))
            if pieces:
                res = {'storey': storey, 'pieces': pieces}
    _stairs[prefix] = (db.recs, res)
    return res


_VEC = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}


def friendly(prefix):
    """A readable name for a kit, e.g. in_hlaalu -> Hlaalu, t_de_setind_i -> Indoril (TR)."""
    words = [w for w in prefix.split('_') if w not in ('in', 't', 'i', 'set', 'int')]
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
