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


def measure(db, ri, tile, band=None):
    """Wall pattern of a piece: {'N': 'wall'|'door'|'open', ...}, plus floor/ceiling, or None.
    band = (zlo, zhi), in the model's own heights: only that slice of the piece is measured (one storey
    of a two-storey hall piece, Redoran (large)'s in_r_l_int_lcorner_01 and its kin, 764 tall)."""
    key = (db.recs[ri][1].lower(), tile, band)
    if key in _cache:
        return _cache[key]
    shapes = _model(db, ri)
    b = mapdata.object_bounds(db, ri)
    if not shapes or not b:
        _cache[key] = None
        return None
    half = tile / 2.0
    zlo, zhi = b[2], b[5]
    if band:
        zlo, zhi = max(zlo, band[0]), min(zhi, band[1])
        if zhi - zlo < 16:
            _cache[key] = None
            return None
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
            if band and not (zlo - 2 <= mz <= zhi + 2):
                continue
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
        whole = sum(g[i][j] for i in range(G) for j in range(G)) / float(G * G)
        out['cover'][side] = round(cover, 2)
        out['offset'][side] = round(where[side][0] / where[side][1], 1) if where[side][1] else half - 16
        out.setdefault('middle', {})[side] = round(middle, 2)
        if cover >= 0.7 or (cover >= 0.55 and middle >= 0.8):
            out[side] = 'wall'                      # (rounded corners leave the ends of a wall open)
        elif cover >= 0.25 and middle < 0.2:
            out[side] = 'door'                      # a wall with a doorway cut into it
        elif band and whole >= 0.4 and middle < 0.2:
            out[side] = 'door'                      # (a storey of a tall piece: a wall with a wide archway through it)
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
               'stairsr', 'ramp', 'floor', 'ceiling', 'pillar', 'column', 'arch', 'entrance', 'entr', 'partition',
               # (the Common sets' endcap, in_c_plain_endcap / in_c_stone_endcap: three walls and a doorway, 51 and
               # 37 uses, the piece the game stands under a landing in front of its tall stair's underside and at
               # the end of a one-tile closet; without it the kits had no three-walled piece at all)
               'endcap'}
# kits whose "entrance" piece the builder must not build with (see kit_pieces), measured on the two-floor
# test house: Redoran (small)'s in_r_s_int_entrance_01 measures as a doorway (OODO, 24 uses) but the house
# then fails to build ("no piece for a spot with walls on 1 sides"), where without it it builds with 3
# holes; Vivec (small)'s in_v_s_int_entrance_01 (DOOO, 482 uses) is never built with (the game hangs its
# Velothi doors in a tile's open side, 18 places under that very piece's open W side against 0 in its
# measured doorway), but admitting it moved the upstairs link door from the middle of the south wall to a
# corner tile and a fresh gap survey then reported 12 and 10 holes for the two floors instead of 4 and 4
NO_ENTRANCE_KITS = {'in_r_s_int', 'in_v_s_int'}
# A roof kit: a set the game only ever stands as the top storey over another set of its family. Common
# thatch (in_c_thatch_room_p*, 364 tall pitched-roof pieces) is the attic of a Common house: in all 15 of
# the game's thatch places that have stairs the thatch floor stands exactly 256 above a plain, stone or
# rich floor (Caldera's Falanaamo, Dagon Fel's End of the World, Old Ebonheart's Katariah, Helnim's
# guild of fighters...), never over another thatch floor, and the stairs are the family's
# in_c_stair_plain_tall_01 (8 places) or the thatch set's own in_c_stair_thatch_pend_01/02 (9), all
# climbing 256. Built as a kit of its own with floors 512 apart it had no stairs the builder would use.
# So the kit builds its lower floors from the family's plain pieces (tagged 'lower') and only the top
# floor from its own (tagged 'top'), the storey being the plain set's.
ROOF_KITS = {'in_c_thatch': 'in_c_plain'}


def _named_entrance(low):
    return bool({'entrance', 'entr'} & set(low.split('_')))


def kit_prefix(rid):
    parts = rid.lower().split('_')
    for n, w in enumerate(parts):
        # (Tamriel Data's Hlaalu manor set names its room pieces LedgeWallSide, LedgeWallCorIn, NoFloor_Side...)
        # (and Tamriel Data's Imperial chapel set, whose parts are all named tile...: TileFloor, TileWall,
        # TileDoorW, TileCeil, TileCol, TileArch, TileStair, TileRail, TileStory)
        # (Redoran (large)'s two-storey hall pieces, in_r_l_int_lcorner_01 / lwall / lcenter / lentrance, 764
        # tall, the pieces its manors are built of; the Hlaalu manor set's ledge, ledge rail and ledge post pieces)
        if n >= 2 and (w in PIECE_WORDS or re.match(r'^(room|hall|corner|wall|door|center|side|ledge|nofloor)', w)
                       or re.match(r'^l(corner|wall|cent|entr|column|partition)', w)
                       or re.match(r'^tile(floor|wall|door|ceil|col|arch|stair|rail|story|corni)', w)):
            return '_'.join(parts[:n])
    return None


def kits(db):
    """Building kits found in the load order: prefix -> {tile, pieces: [{id, pattern, uses, size}]}."""
    if STYLE_KITS.get('_recs') is db.recs:
        return STYLE_KITS['kits']
    recs = db.recs            # (the list this walk is about: a reload swaps in a new one, and the walk then starts over)
    groups = {}
    for (tag, key), lst in db.by_key.items():
        if tag != 'STAT' or not lst or lst[-1] in db.dead:
            continue
        # (vanilla's in_ sets; Tamriel Data's t_<culture>_set<name>_i sets, and its few interior sets named
        # without "set": t_imp_legioncyr_i, the Cyrodiil Legion forts and Goldstone castle, the grey
        # stone halls with pointed arches and a spiral stair tower the user walked in Anvil)
        if not (key.startswith('in_') or re.match(r'^t_[a-z]+_set', key) or re.match(r'^t_[a-z]+_legion[a-z]*_i_', key)):
            continue
        prefix = kit_prefix(key)
        if prefix:
            groups.setdefault(prefix, []).append(lst[-1])
    out = {}
    for prefix, ris in groups.items():
        if len(ris) < 6:
            continue
        sizes, flat, n_flat = {}, {}, 0
        for ri in ris:
            b = mapdata.object_bounds(db, ri)
            low = db.recs[ri][1].lower()
            if b and not any(w_ in low for w_ in ('stair', 'ramp', 'rail')):
                w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
                # (the tile size is the one the game builds with most: each piece's vote weighs what the
                # game uses it, plus one. Counting pieces alone, Hlaalu's 19 tall-storey pieces (512) outvoted
                # its 16 ordinary ones (256) once the stairs stopped voting, and the kit lost its stairs)
                if h > 150 and abs(w - d) < 40 and w > 200:
                    sz = round(max(w, d) / 64.0) * 64
                    sizes[sz] = sizes.get(sz, 0) + 1 + game_uses(db, low)
                elif h <= 8 and abs(w - d) < 16 and 200 < w < 600 and 'floor' in low:
                    sz = round(max(w, d) / 64.0) * 64
                    flat[sz] = flat.get(sz, 0) + 1 + game_uses(db, low)
                    n_flat += 1
        # (a set with no room pieces at all, built from flat floor sheets with loose walls stood on them: the
        # Imperial chapel set, Anvil's pale ashlar halls; see kit_pieces)
        sheet_kit = not sizes and n_flat >= 2
        if not sizes and not sheet_kit:
            continue
        votes = sizes or flat
        tile = max(votes, key=lambda sz: (votes[sz], -sz))
        out[prefix] = {'prefix': prefix, 'tile': tile, 'ris': ris, 'sheet_kit': sheet_kit,
                       'uses': sum(game_uses(db, db.recs[ri][1].lower()) for ri in ris)}
    if db.recs is recs:
        # (not kept when the game data was reloaded during the walk: the record indices in it would be
        # the old list's; the next call walks the new one. The style warm-up thread met this as an
        # IndexError in _stairs_learn on a test server whose data reloaded under it)
        STYLE_KITS.update({'_recs': recs, 'kits': out})
    return out


def kit_pieces(db, prefix):
    k = kits(db).get(prefix)
    if not k:
        return None
    if 'pieces' in k:
        return k
    tile = k['tile']
    pieces, halves, uppers = [], [], []
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
        if 'stair' in low or 'ramp' in low or 'rail' in low or h > tile * 1.5:
            continue
        # a full tile, centred on its origin
        if not (abs(w - tile) < tile * 0.12 or abs(d - tile) < tile * 0.12) or max(w, d) > tile * 1.15:
            continue
        if abs((b[0] + b[3]) / 2) > tile * 0.12 or abs((b[1] + b[4]) / 2) > tile * 0.12:
            continue
        if k.get('sheet_kit'):
            # the floor sheets are the tiles: open on every side, a floor and nothing else; the walls, the
            # door walls and the ceiling slabs stand on them (the chapel set's TileFloor_01..05)
            if h > 8 or 'floor' not in low or abs(w - d) >= 16:
                continue
            pat = {s: 'open' for s in SIDES}
            pat.update(floor=True, ceiling=False, offset={s: tile / 2 - 16 for s in SIDES}, cover={s: 0.0 for s in SIDES})
        else:
            pat = measure(db, ri, tile)
        if not pat:
            continue
        # (only one that stands on the slab: not the set's "NoFloor" pieces for a storey above, whose
        # bottom is a floor's thickness up)
        floorless = not pat['floor']
        if floorless and not (slab and b[2] <= slab['zmin'] + 16 and (pat.get('ceiling') or any(pat[s] == 'wall' for s in SIDES))):
            # (kept apart as the kit's upper-storey pieces: the Hlaalu manor's NoFloor_Corner/Side/End/
            # Center_01, walls and a ceiling with no floor, which the game stands over a two-storey hall's
            # opening on the storey above, 128 under where a floored piece's origin would be; see 'floorless')
            if slab and (pat.get('ceiling') or any(pat[s] == 'wall' for s in SIDES)) and b[2] > slab['zmin'] + 16 and h >= tile * 0.6:
                uppers.append({'id': rid, 'ri': ri, 'pattern': _curved(pat, low), 'uses': game_uses(db, low), 'zmin': b[2],
                               'height': h, 'floorless': True})
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
    # two-storey hall pieces, a tile across and about twice as tall as the kit's ordinary pieces (Redoran
    # (large)'s in_r_l_int_lcorner_01 / lwall_01 / lcenter_01 / lentrance_01, 764 against 380: the pieces
    # its manors' halls are built of, 11, 8, 10 and 11 uses against the single-storey corner_01's 7), kept
    # apart as the kit's 'tall' pieces with a wall pattern per storey, never laid as an ordinary tile
    # (the ordinary height: the lowest cluster of heights among pieces at least half a tile tall; a flat
    # ceiling or floor slab a tile across, 16 or 40 tall, is no storey to measure the others against)
    base = sorted(p['height'] for p in pieces if p['height'] >= tile * 0.5)
    base_h = None
    if base:
        low_ = [h for h in base if h <= base[0] * 1.5]
        base_h = low_[len(low_) // 2]
    tall = [p for p in pieces if base_h and p['height'] >= base_h * 1.8]
    pieces = [p for p in pieces if p not in tall]
    # door frames that sit in a doorway between two tiles, and plain wall sections
    jambs, walls, door_walls = [], [], []
    # (the full height from the ordinarily named pieces: an "entrance" piece may be dropped below)
    heights = sorted(p['height'] for p in pieces if not _named_entrance(p['id'].lower())) or sorted(p['height'] for p in pieces) or [tile]
    full_h = heights[len(heights) // 2]
    for p in tall:
        # (each storey measured on its own slice of the model: a Redoran lentrance has an archway below
        # and a doorway above on the same side, an lcorner its two walls on both storeys)
        zl, zh = p['zmin'], p['zmin'] + p['height']
        mid = (zl + zh) / 2.0
        lower = measure(db, p['ri'], tile, band=(zl, mid))
        upper = measure(db, p['ri'], tile, band=(mid, zh))
        if not lower or not upper:
            continue
        lower, upper = _curved(lower, p['id'].lower()), _curved(upper, p['id'].lower())
        for s in SIDES:
            if lower[s] == 'door' and upper[s] == 'open':
                upper[s] = 'door'            # (the opening carries on up: the upper doorway of an entrance piece)
        p['lower'], p['upper'] = lower, upper
        p['pattern'] = lower
    tall = [p for p in tall if 'upper' in p]
    if k.get('sheet_kit'):
        # (the storey is as tall as the set's walls: the chapel's TileWall_01 is 364, its ceiling slab's top too)
        hs = []
        for ri in k['ris']:
            low = db.recs[ri][1].lower()
            b = mapdata.object_bounds(db, ri)
            if b and 'wall' in low and 'door' not in low:
                w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
                if min(w, d) <= tile * 0.35 and tile * 0.8 <= max(w, d) <= tile * 1.15 and h > 150:
                    hs.append(h)
        # (the shortest of the common wall heights: the set has walls a storey tall and walls two storeys
        # tall for its halls; the storey is the short one, 364)
        counts = {}
        for h in hs:
            counts[round(h / 16) * 16] = counts.get(round(h / 16) * 16, 0) + 1
        common = [h for h, n in counts.items() if n >= max(2, max(counts.values()) // 2)] or list(counts)
        full_h = min(common) if common else tile
        for p in pieces:
            p['height'] = full_h
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
        # (a loose wall must reach nearly to the ceiling: the Indoril chapel's Room_Wall_01/02 are 212
        # tall under a 255 storey, screens rather than walls, and every side closed with one leaked
        # under the ceiling: seven of the test house's eleven holes. Indoril's Room_Wall_03, 215 under
        # 236, stays)
        if 'jamb' not in low and h < full_h * 0.85:
            continue
        item = {'id': db.recs[ri][1], 'ri': ri, 'uses': game_uses(db, low), 'thin_x': w < d,
                'thick': thin, 'zmin': b[2], 'width': long_}
        if 'jamb' in low or 'doorway' in low or ('door' in low and 'load' not in low and 'jamb' in low):
            item['load'] = 'load' in low
            jambs.append(item)
        elif ('wall' in low or 'partition' in low) and 'door' not in low and thin >= 3 and 'addon' not in low:
            # (not the paper-thin panels laid over walls for decoration; Redoran (small)'s partition_01 is
            # its loose wall, 4 thick and a tile long, 27 uses: the game closes the sides of its
            # notches with it, and it is what lets a one-tile room close in that style)
            walls.append(item)
        elif 'door' in low and 'load' not in low and 'trap' not in low and long_ >= tile * 0.9:
            # a wall section with a doorway through it (Tamriel Data's Redguard "Wall_Door"): the
            # same thing as a Hlaalu door frame, by another name, if there's a hole to walk through
            fh = frame_hole(db, ri)
            if fh and fh[2] >= 64 and fh[3] >= full_h * 0.6:
                item['load'] = False
                door_walls.append(item)
    # the vanilla canton sets and Tamriel Data name their doorway tile "entrance" or "entr" (Mournhold's
    # in_MH_int_entrance_01, the Imperial small rich in_impsmall_r_entr_01..04). Such a piece is kept only
    # where it is the set's own way of making a doorway: it measures as one (a side of pattern 'door';
    # Redoran (large)'s entrance_01/_03 measure OOOO, open arches), the set has no door frames (Necrom and
    # the Stronghold set have jambs), and no doorway piece the game uses more (Gold Coast's Entrance_02,
    # 33 uses, against its Hall_01 with 79, so its tuned doorways stay as they were; Mournhold's
    # entrance_01, 122 uses, against its corner_04 with 20). Measured on the two-floor test house:
    # Mournhold gains entrance_01 with the game's In_MH_door_01 (3 doorway sides, 0 issues before and
    # after), Imperial (small) rich its four entr pieces with in_impsmall_door_01/loaddoor_01 (holes 6 -> 0),
    # Redoran (small) and (large) build the same house as before (3 and 11 holes); Hlaalu, Common, Indoril
    # and Telvanni have no such piece. Redoran (small) and Vivec (small) are kept out by name (NO_ENTRANCE_KITS).
    if any(_named_entrance(p['id'].lower()) for p in pieces):
        top = max((p['uses'] for p in pieces if not _named_entrance(p['id'].lower()) for s in SIDES if p['pattern'][s] == 'door'), default=-1)
        keep = not jambs and prefix.lower() not in NO_ENTRANCE_KITS
        pieces = [p for p in pieces if not _named_entrance(p['id'].lower()) or
                  (keep and p['uses'] > top and any(p['pattern'][s] == 'door' for s in SIDES))]
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
    k['tall'] = sorted(tall, key=lambda p: -p['uses'])
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
    # the upper-storey pieces (walls and a ceiling, no floor) with how much lower than an ordinary piece
    # each one's origin goes for its bottom to sit on the storey's floor ('zoff': the Hlaalu manor's
    # NoFloor pieces -128, their bottom 5 above their origin against the ordinary pieces' -123)
    for p in uppers:
        p['zoff'] = k['zmin'] - p['zmin']
    k['floorless'] = sorted(uppers, key=lambda p: -p['uses'])
    # a sheet kit's ceiling: the slab a tile across up at the top of the storey (TileCeil_01), laid over
    # every tile by the builder, since the floor sheets have none
    k['ceiling'] = None
    if k.get('sheet_kit'):
        best = None
        for ri in k['ris']:
            low = db.recs[ri][1].lower()
            b = mapdata.object_bounds(db, ri)
            if b and 'ceil' in low and abs(b[3] - b[0] - tile) < tile * 0.12 and abs(b[4] - b[1] - tile) < tile * 0.12 and b[2] >= full_h * 0.7:
                u = game_uses(db, low)
                if best is None or u > best[2]:
                    best = (db.recs[ri][1], ri, u, b)
        k['ceiling'] = best and {'id': best[0], 'ri': best[1], 'box': best[3]}
    # a roof kit (see ROOF_KITS): the family's base set builds the lower floors, this set the top one
    base = ROOF_KITS.get(prefix.lower())
    kb = kit_pieces(db, base) if base else None
    if kb and kb['tile'] == tile and kb['pieces']:
        for p in k['pieces']:
            p['storey'] = 'top'
        k['pieces'] = [dict(p, storey='lower') for p in kb['pieces']] + k['pieces']
        k['halves'] = [dict(p, storey='lower') for p in kb['halves']] + k['halves']
        k['jambs'] = kb['jambs'] or k['jambs']
        k['walls'] = kb['walls'] or k['walls']
        k['frame_doors'] = kb['frame_doors']
        k['entry_doors'] = kb['entry_doors'] or k['entry_doors']
        k['slab'] = kb['slab']
        k['zmin'] = kb['zmin']
        k['tall'] = []
        k['floorless'] = []
        k['roof_height'] = k['height']           # (the roof storey's own: thatch 364, for the stairs under it)
        k['height'] = kb['height']
        k['roof_kit'] = True
        k['roof_of'] = base
    return k


_family_walls = {}


def family_wall(db, prefix):
    """The loose wall a kit's family keeps under the family's name, when the kit itself has none: the
    Common sets close an open side with in_c_wall_plain / in_c_wall_stone / in_c_wall_rich (96, 50 uses),
    which file under "in_c", not under any kit. The one named with the kit's word first, else the most
    used; shaped like a kit_pieces wall item. None when there is no such wall."""
    k = kit_pieces(db, prefix)
    if not k:
        return None
    key = prefix.lower()
    if key in _family_walls and _family_walls[key][0] is db.recs:
        return _family_walls[key][1]
    tile, full_h = k['tile'], k['height']
    parts = key.split('_')
    fam, word = ('_'.join(parts[:-1]), parts[-1]) if len(parts) >= 3 else (key, '')
    best = None
    for (tag, key2), lst in db.by_key.items():
        if tag != 'STAT' or not key2.startswith(fam + '_wall') or not lst or lst[-1] in db.dead:
            continue
        ri = lst[-1]
        b = mapdata.object_bounds(db, ri)
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        thin, long_ = min(w, d), max(w, d)
        if thin > tile * 0.35 or not tile * 0.8 <= long_ <= tile * 1.15 or h < full_h * 0.85 or h > full_h * 1.2:
            continue
        if any(x in key2 for x in ('window', 'rail', 'screen', 'door')):
            continue
        item = {'id': db.recs[ri][1], 'ri': ri, 'uses': game_uses(db, key2), 'thin_x': w < d, 'thick': thin, 'zmin': b[2], 'width': long_}
        score = (word and word in key2.split('_'), item['uses'])
        if best is None or score > best[0]:
            best = (score, item)
    res = best[1] if best else None
    _family_walls[key] = (db.recs, res)
    return res


_wall_offsets = {}


def loose_wall_offset(db, prefix, wall, limit=60):
    """How far from a tile's middle the game stands this loose wall, along its thin axis: the distance
    its own places use most (to 8 units), with how many walls it was seen on, or None. Hlaalu's
    in_hlaalu_wall (62 thick) stands centred on the tile's edge, 128 out, in 52 of 83 (2026-10-23);
    the builder used to stand it 95 out, flush inside the tile, a 48-unit jog in from the faces of the
    room pieces' own walls, with the corner post left half inside it."""
    k = kit_pieces(db, prefix)
    if not k or not wall:
        return None
    key = (prefix.lower(), wall['id'].lower())
    if key in _wall_offsets and _wall_offsets[key][0] is db.recs:
        return _wall_offsets[key][1]
    import fixit
    T = k['tile']
    low = wall['id'].lower()
    cells = sorted({db.recs[ci][7] for ci in db.used_in.get(low, ()) if db.recs[ci][0] == 'CELL' and game_made(db, db.recs[ci][7])})
    offs = {}
    for ck in cells[:limit]:
        try:
            m = mapdata.cellmap(db, ck)
            tiles, _p = fixit._tiles(db, m)
        except Exception:
            continue
        for r in m['refs']:
            if r['id'].lower() != low or abs(r['p'][3]) > 0.05 or abs(r['p'][4]) > 0.05:
                continue
            q = int(round(r['p'][5] / (math.pi / 2))) % 4
            best = None
            for t in tiles:
                if abs(t['floor'] - (r['p'][2] + wall['zmin'])) > 40:
                    continue
                # (the wall's thin axis: x when its model is thin in x and it stands unturned)
                thin_x = wall['thin_x'] == (q % 2 == 0)
                d = (r['p'][0] - t['x']) if thin_x else (r['p'][1] - t['y'])
                o = (r['p'][1] - t['y']) if thin_x else (r['p'][0] - t['x'])
                if abs(o) < 40 and abs(d) <= T and (best is None or abs(d) < abs(best)):
                    best = d
            if best is not None:
                b = int(round(abs(best) / 8.0) * 8)
                offs[b] = offs.get(b, 0) + 1
    res = None
    if offs:
        off = max(offs, key=offs.get)
        res = (off, offs[off])
    _wall_offsets[key] = (db.recs, res)
    return res


_hearths = {}
HEARTH_RE = re.compile(r'fireplace|hearth|stove|oven')


def hearths(db, prefix):
    """The built-in hearths the game stands against this kit's walls, which Auto-furnish never places
    (statics named in_... or ex_... count as the building, not furniture): [{'id', 'n': how many stand
    against a wall side of the kit's (or its family's) tiles, 'out': how far out from the tile's centre
    towards that wall, 'along': how far along it, 'turn': quarter turns from facing out of the wall,
    'bottom': how far over the floor the model's bottom sits, 'above': share with a floor tile over it}],
    most used first. Measured 2026-10-22: the game's Common kitchens have no hearth piece of their own;
    they stand in_nord_fireplace_01 (36 against the walls of plain, stone and rich tiles, 104 out, turned
    a quarter, a room above it in 19 of 42) and in_imp_fireplace_grand (24, 80 out). Most kits have none."""
    k = kit_pieces(db, prefix)
    if not k:
        return []
    key = prefix.lower()
    if key in _hearths and _hearths[key][0] is db.recs:
        return _hearths[key][1]
    from mapdata import ref_info
    parts = key.split('_')
    family = '_'.join(parts[:-1]) + '_' if len(parts) >= 3 else None
    tiles_of = {}
    for pre in kits(db):
        if pre.lower() == key or (family and pre.lower().startswith(family)):
            kp2 = kit_pieces(db, pre)
            if kp2 and kp2['tile'] == k['tile']:
                for p in kp2['pieces']:
                    tiles_of.setdefault(p['id'].lower(), (p, kp2['tile'], kp2['height']))
    T = k['tile']
    found = {}
    for (tag, mid), lst in db.by_key.items():
        if tag != 'STAT' or not lst or lst[-1] in db.dead or not HEARTH_RE.search(mid) or not mid.startswith(('in_', 'ex_')):
            continue
        if game_uses(db, mid) < 3:
            continue
        fb = mapdata.object_bounds(db, lst[-1])
        if not fb or fb[5] - fb[2] < 100:
            continue
        rows = []
        for ci in list(db.used_in.get(mid, ()))[:60]:
            r = db.recs[ci]
            if r[0] != 'CELL' or not game_made(db, r[7]):
                continue
            try:
                refs, _h = db.cell_refs(r[7])
            except Exception:
                continue
            items = [(rid.lower(), pos) for rid, pos, _s, dead in (ref_info(x['subs']) for x in refs.values()) if not dead]
            tiles = [(rid, pos) for rid, pos in items if rid in tiles_of]
            if not tiles:
                continue
            for rid, pos in items:
                if rid != mid:
                    continue
                best = None
                for tid, tp in tiles:
                    p, _T, H = tiles_of[tid]
                    fl = tp[2] + p['zmin']
                    if abs(pos[0] - tp[0]) <= T * 0.75 and abs(pos[1] - tp[1]) <= T * 0.75 and -64 <= (pos[2] + fb[2]) - fl <= 200:
                        d = max(abs(pos[0] - tp[0]), abs(pos[1] - tp[1]))
                        if best is None or d < best[0]:
                            best = (d, tid, tp, p, H, fl)
                if not best:
                    continue
                _d, tid, tp, p, H, fl = best
                dx, dy = pos[0] - tp[0], pos[1] - tp[1]
                side = ('E' if dx > 0 else 'W') if abs(dx) >= abs(dy) else ('N' if dy > 0 else 'S')
                vx, vy = _VEC[side]
                q = int(round(tp[5] / (math.pi / 2))) % 4
                if rotate(p['pattern'], q)[side] != 'wall':
                    continue
                up = any(abs(t2[0] - tp[0]) < 24 and abs(t2[1] - tp[1]) < 24 and H * 0.8 < (t2[2] + tiles_of[r2][0]['zmin']) - fl < H * 2.5
                         for r2, t2 in tiles)
                turn = int(round(((pos[5] - _YAW[side]) % (2 * math.pi)) / (math.pi / 2))) % 4
                rows.append((dx * vx + dy * vy, dx * vy - dy * vx, turn, (pos[2] + fb[2]) - fl, up))
        if len(rows) >= 3:
            med = lambda i: sorted(r_[i] for r_ in rows)[len(rows) // 2]
            turns = {}
            for r_ in rows:
                turns[r_[2]] = turns.get(r_[2], 0) + 1
            found[mid] = {'id': db.recs[lst[-1]][1], 'n': len(rows), 'out': round(med(0)), 'along': round(med(1)),
                          'turn': max(turns, key=turns.get), 'bottom': round(med(3)),
                          'above': round(sum(1 for r_ in rows if r_[4]) / float(len(rows)), 2), 'height': round(fb[5] - fb[2])}
    res = sorted(found.values(), key=lambda h: -h['n'])
    _hearths[key] = (db.recs, res)
    return res


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
    # (kept on disk by load order: learning the stairs of all 77 kits took about 40 s on every start, and
    # the style picker, which asks for every kit's stairs, sat on "Loading styles…" meanwhile, with the
    # planner unable to place any stairs until it had)
    disk = _stairs_disk(db)
    # (a roof kit's stairs are learnt against its base set's storey: kept apart from what was learnt
    # before it was one)
    dkey = prefix.lower() + ('@roof' if k.get('roof_kit') else '')
    if dkey in disk:
        res = disk[dkey]
        if res:
            res = dict(res, pieces=[dict(p, ri=db.resolve_id(p['id'])) for p in res['pieces']])
            res['pieces'] = [p for p in res['pieces'] if p['ri'] is not None]
            if not res['pieces']:
                res = None
        _stairs[prefix] = (db.recs, res)
        return res
    res = _stairs_learn(db, prefix, k)
    _stairs[prefix] = (db.recs, res)
    disk[dkey] = res
    _stairs_save(db, disk)
    return res


def learn_stairs(db):
    """Every kit's stairs learnt and kept on disk in one go: the survey process does this when the
    Workshop starts (learning.prewarm), so the style list has them the first time it is opened."""
    disk = _stairs_disk(db)
    for prefix in kits(db):
        k = kit_pieces(db, prefix)
        dkey = prefix.lower() + ('@roof' if k and k.get('roof_kit') else '')
        if dkey in disk:
            continue
        disk[dkey] = _stairs_learn(db, prefix, k) if k else None
    _stairs_save(db, disk)
    return disk


def _stairs_path(db):
    import os
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    # (v2: the mesh reader now ignores a model's root transform as the game does, and the two-storey hall
    # pieces are kept apart from a kit's tiles: both change what a stair is learnt against, 2026-10-22)
    return os.path.join(folder, 'stairs_%s_v2.json' % taste.sig(db))


_stairs_disk_cache = {}


def _stairs_disk(db):
    """Every kit's learnt stairs for this load order, from disk: {prefix: res or None}. Read again when
    the file has changed since (the survey process writes it a minute after the Workshop starts: the
    style list opened before that used to keep an empty table and learn every kit itself, 30 s)."""
    import json
    import os
    path = _stairs_path(db)
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        stamp = None
    if _stairs_disk_cache.get('recs') is db.recs and (stamp is None or _stairs_disk_cache.get('stamp') == stamp):
        return _stairs_disk_cache['d']
    d = {}
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        d = {}
    _stairs_disk_cache.update({'recs': db.recs, 'd': d, 'stamp': stamp})
    return d


def stairs_known(db, prefix):
    """Whether this kit's stairs are learnt already (in memory or on disk), without learning them."""
    if prefix in _stairs and _stairs[prefix][0] is db.recs:
        return True
    k = kit_pieces(db, prefix)
    dkey = prefix.lower() + ('@roof' if k and k.get('roof_kit') else '')
    return dkey in _stairs_disk(db)


def _stairs_save(db, d):
    import json
    try:
        # (what another survey process wrote meanwhile is kept: the catalogue learns a kit's stairs
        # on the way while the stairs of every kit are learnt beside it)
        try:
            with open(_stairs_path(db), encoding='utf-8') as f:
                on_disk = json.load(f)
            for pre, res in on_disk.items():
                d.setdefault(pre, res)
        except Exception:
            pass
        out = {}
        for pre, res in d.items():
            out[pre] = None if not res else dict(res, pieces=[{k_: v for k_, v in p.items() if k_ != 'ri'} for p in res['pieces']])
        with open(_stairs_path(db), 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass


def _stairs_learn(db, prefix, k):
    from mapdata import ref_info
    T = k['tile']
    floor_ids = {p['id'].lower(): p for p in k['pieces']}
    # (a stair the family shares, like in_c_stair_plain_tall_01 in a Common stone house, is learnt from
    # how it joins any of the family's floor tiles, this kit's own places first)
    parts = prefix.lower().split('_')
    own_cells = set()
    if len(parts) >= 3:
        family = '_'.join(parts[:-1])
        for p in kits(db):
            if p.startswith(family + '_') and p != prefix:
                kp2 = kit_pieces(db, p)
                for piece in (kp2 or {}).get('pieces', []):
                    if piece['tile'] == T if 'tile' in piece else kp2['tile'] == T:
                        floor_ids.setdefault(piece['id'].lower(), piece)
        for ri in k['ris']:
            for ci in db.used_in.get(db.recs[ri][1].lower(), ()):
                if db.recs[ci][0] == 'CELL':
                    own_cells.add(ci)
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
        using = list(db.used_in.get(sid, ()))
        using = [ci for ci in using if ci in own_cells] + [ci for ci in using if ci not in own_cells]
        for ci in using[:40]:
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
        # (a post the game stands at a corner of the stair in half its places or more: fewer than that,
        # and the corners are the floor pieces' own, with nothing to cover)
        post_ri = db.resolve_id(post) if post and posts[post] >= max(3, seen * 0.5) else None
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
            # (a roof kit's own stairs before the family's: Common thatch's in_c_stair_thatch_pend_01/02
            # reach from the ground floor up to the roof's ridge, 620 tall, so nothing shows over them,
            # while the family's in_c_stair_plain_tall_01 stops 122 short of the thatch storey's top)
            word = prefix.lower().split('_')[-1] if k.get('roof_kit') else None
            pieces.sort(key=lambda p: (len(p['open']), bool(word) and word not in p['id'].lower().split('_'), -p['uses']))
            if pieces:
                # a proper staircase that climbs a whole floor (not only ramps meant for halls): the
                # style looks right with stairs, so they are the default
                proper = any(abs(p['rise'] - storey) < 8 and 'ramp' not in p['id'].lower() for p in pieces)
                res = {'storey': storey, 'pieces': pieces, 'proper': proper}
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
        # and the family's stairs the game itself stands in this kit's own places, whatever they are
        # named: the Common stone houses climb with in_c_stair_plain_tall_01 (16 of 35 with stairs)
        # more than with in_c_stone_stair_short (12), and the thatch ones too
        from mapdata import ref_info
        cells = set()
        for ri in k['ris']:
            for ci in db.used_in.get(db.recs[ri][1].lower(), ()):
                if db.recs[ci][0] == 'CELL' and game_made(db, db.recs[ci][7]):
                    cells.add(db.recs[ci][7])
        count = {}
        for ck in cells:
            try:
                refs, _h = db.cell_refs(ck)
            except Exception:
                continue
            for sid in {ref_info(r['subs'])[0].lower() for r in refs.values() if not ref_info(r['subs'])[3]}:
                if sid.startswith(family + '_') and ('stair' in sid or 'ramp' in sid):
                    count[sid] = count.get(sid, 0) + 1
        for sid, n in count.items():
            lst = db.by_key.get(('STAT', sid))
            if n >= 3 and lst and lst[-1] not in db.dead and lst[-1] not in seen and kit_prefix(sid) != pre:
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


# A style may be a kit dressed the way the game dresses it in some of its places (dressingsurvey.py): the
# id is "<kit prefix>@<dressing>", e.g. t_imp_setgc_i@wallrichaddon, the Gold Coast timber kit under the
# pale carved ashlar panels of Anvil's guild halls. Everything that reads the kit uses the prefix alone.
DRESSING_NAMES = {'wallrichaddon': 'pale ashlar, as in Anvil\'s guild halls',
                  'wallstoneaddon': 'grey stone, as in Anvil\'s halls and vaults'}


def split_style(style):
    """(kit prefix, dressing or None) of a style id."""
    s = str(style or '')
    if '@' in s:
        a, b = s.split('@', 1)
        return a, (b or None)
    return s, None


def dressing_name(dressing):
    if dressing in DRESSING_NAMES:
        return DRESSING_NAMES[dressing]
    return re.sub(r'^wall|addon$', '', dressing).strip('_') or dressing


def friendly(prefix):
    """A readable name for a kit, e.g. in_hlaalu -> Hlaalu, t_de_setind_i -> Indoril (TR)."""
    prefix, dressing = split_style(prefix)
    if dressing:
        base = friendly(prefix)
        tail = ' (Tamriel Data)' if base.endswith(' (Tamriel Data)') else ''
        return '%s: %s%s' % (base[:len(base) - len(tail)], dressing_name(dressing), tail)
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
             'he': 'High Elf', 'sky': 'Skyrim', 'dwrv': 'Dwemer', 'dwe': 'Dwemer', 'tel': 'Telvanni', 'red': 'Redoran',
             'legioncyr': 'Legion fort (Cyrodiil)', 'legionmw': 'Legion fort (Morrowind)', 'legionsky': 'Legion fort (Skyrim)',
             'chapel': 'chapel'}
    tr = prefix.startswith('t_')
    out = []
    for w in words:
        w2 = w[3:] if w.startswith('set') else w
        out.append(names.get(w2, w2.capitalize()))
    return ' '.join(out) + (' (Tamriel Data)' if tr else '')
