"""Walking paths (path grids): the invisible network of points NPCs and creatures walk along.

For places built from room pieces, a point goes into each walkable tile (moved aside if furniture
stands there), joined to its neighbours where you can walk through: open floor, archways and door
frames. Points by the way out let people reach the door."""
import math
import struct

import editing
import furnish
import mapdata
from editing import EditError
from esm import iter_subrecords, zstr
from project import join_subs, zs

STEP = furnish.STEP
OPP = furnish.OPP


def read(db, cell_key):
    """The walking paths a place has now: {'pts': [[x, y, z]], 'edges': [[a, b]]} or None."""
    lst = [v for v in db.by_key.get(('PGRD', cell_key), []) if v not in db.dead]
    if not lst:
        return None
    r = db.recs[lst[-1]]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    pts, conns, counts = [], [], []
    for st, sd in iter_subrecords(data):
        if st == 'PGRP':
            for o in range(0, len(sd) - 15, 16):
                x, y, z, _auto, n, _u = struct.unpack_from('<iiiBBH', sd, o)
                pts.append([x, y, z])
                counts.append(n)
        elif st == 'PGRC':
            conns = list(struct.unpack_from('<%dI' % (len(sd) // 4), sd))
    edges, k = set(), 0
    for i, n in enumerate(counts):
        for j in conns[k:k + n]:
            if j < len(pts) and i != j:
                edges.add((min(i, j), max(i, j)))
        k += n
    return {'pts': pts, 'edges': sorted(edges)}


def save(db, cell_key, pts, edges):
    """Walking paths edited by hand: points [[x, y, z]] (outdoors in world positions, like read() gives
    them through the map) and links [[a, b]]. Saved into the mod as one change."""
    editing._require_project(db)
    info = mapdata.cell_info(db, cell_key)
    if not info:
        raise EditError('That place does not exist.')
    pts = [[float(v) for v in p[:3]] for p in pts]
    if len(pts) > 30000:
        raise EditError('That is too many points for one place.')
    links = {i: set() for i in range(len(pts))}
    for e in edges:
        a, b = int(e[0]), int(e[1])
        if a != b and 0 <= a < len(pts) and 0 <= b < len(pts):
            links[a].add(b)
            links[b].add(a)
    links = {i: sorted(v)[:255] for i, v in links.items()}     # (the game keeps up to 255 links a point)
    outdoors = cell_key.startswith('#')
    ox, oy = (info['gx'] * 8192, info['gy'] * 8192) if outdoors else (0, 0)
    if outdoors:
        for p in pts:
            if not (ox - 64 <= p[0] <= ox + 8256 and oy - 64 <= p[1] <= oy + 8256):
                raise EditError('A point lies outside this cell. Each outdoor cell keeps its own paths.')
    pgrp = b''.join(struct.pack('<iiiBBH', int(round(p[0] - ox)), int(round(p[1] - oy)), int(round(p[2])), 0, len(links[i]), 0)
                    for i, p in enumerate(pts))
    pgrc = b''.join(struct.pack('<%dI' % len(links[i]), *links[i]) for i in range(len(pts)) if links[i])
    name = info.get('name') or ('' if not outdoors else info.get('region') or '')
    head = struct.pack('<iiHH', info['gx'] if outdoors else 0, info['gy'] if outdoors else 0, 1024 if outdoors else 256, len(pts))
    subs = [('DATA', head), ('NAME', zs(name))]
    if pts:
        subs += [('PGRP', pgrp)] + ([('PGRC', pgrc)] if pgrc else [])
    had = any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), []))
    if not pts and not had:
        db.project.remove_record('PGRD', cell_key)        # nothing left, and nobody else had paths here
    else:
        db.project.set_record('PGRD', cell_key, 0, join_subs(subs), created=not had)
    n = sum(len(v) for v in links.values()) // 2
    editing.commit(db, 'Edited the walking paths in %s (%d points, %d links)' % (editing.cell_label(db, cell_key), len(pts), n))
    return {'points': len(pts), 'links': n}


def _blocked(boxes, x, y, pad=18):
    return any(b[0] - pad < x < b[2] + pad and b[1] - pad < y < b[3] + pad for b in boxes)


def _clear(boxes, a, b, pad=14):
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d / 16))
    return not any(_blocked(boxes, a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n, pad) for t in range(1, n))


def generate_exterior(db, cell_key, note=True, spacing=512):
    """Walking paths for an outdoor cell: a point every `spacing` units of dry, walkable ground (not
    inside a building, rock or tree), joined to its neighbours where the slope is gentle enough and
    nothing stands in the way. Points are stored relative to the cell's corner, like the game's."""
    editing._require_project(db)
    gx, gy = (int(v) for v in cell_key[1:].split(','))
    if mapdata.terrain_z(db, gx * 8192 + 4096, gy * 8192 + 4096) is None:
        raise EditError('This cell has no ground (it is open water), so there is nowhere to walk.')
    m = mapdata.cellmap(db, cell_key)
    boxes = []
    for r in m.get('refs', []):
        b = r.get('b')
        if not b or r['type'] in ('NPC_', 'CREA', 'LEVC', 'LIGH', 'DOOR') or r['type'] in mapdata.ITEM_TYPES:
            continue
        s = r['s'] or 1.0
        if (b[5] - b[2]) * s < 60 or max(b[3] - b[0], b[4] - b[1]) * s < 40:
            continue                                  # grass, small plants: you walk through them
        boxes.append(furnish._footprint([v * s for v in b], r['p'][5], r['p'][0], r['p'][1]))
    ox, oy = gx * 8192, gy * 8192
    n = int(8192 // spacing)
    grid, pts = {}, []
    for j in range(n):
        for i in range(n):
            x, y = ox + (i + 0.5) * spacing, oy + (j + 0.5) * spacing
            z = mapdata.terrain_z(db, x, y)
            if z is None or z < 16:
                continue                              # under water
            if _blocked(boxes, x, y, pad=40):
                # try a little to the side before giving up on this spot
                moved = next(((x + dx, y + dy) for dx, dy in ((spacing * 0.3, 0), (-spacing * 0.3, 0), (0, spacing * 0.3), (0, -spacing * 0.3))
                              if not _blocked(boxes, x + dx, y + dy, pad=40)), None)
                if not moved:
                    continue
                x, y = moved
                z = mapdata.terrain_z(db, x, y)
                if z is None or z < 16:
                    continue
            grid[(i, j)] = len(pts)
            pts.append([x, y, z])
    edges = set()
    for (i, j), a in grid.items():
        for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
            b = grid.get((i + di, j + dj))
            if b is None:
                continue
            pa, pb = pts[a], pts[b]
            d = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            if abs(pb[2] - pa[2]) > d * 0.75:
                continue                              # too steep to walk
            mid = mapdata.terrain_z(db, (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            if mid is None or mid < 16 or abs(mid - (pa[2] + pb[2]) / 2) > d * 0.4:
                continue                              # water, a ditch or a ridge in between
            if not _clear(boxes, pa, pb, pad=30):
                continue
            edges.add((a, b))
    # points nobody can reach from anywhere are no use
    linked = {i for e in edges for i in e}
    keep = [i for i in range(len(pts)) if i in linked]
    if len(keep) < 2:
        raise EditError('There is too little open, walkable ground here for walking paths.')
    renum = {old: new for new, old in enumerate(keep)}
    pts = [pts[i] for i in keep]
    edges = {(renum[a], renum[b]) for a, b in edges}
    links = {i: [] for i in range(len(pts))}
    for a, b in sorted(edges):
        links[a].append(b)
        links[b].append(a)
    pgrp = b''.join(struct.pack('<iiiBBH', int(round(p[0] - ox)), int(round(p[1] - oy)), int(round(p[2])), 1, len(links[i]), 0)
                    for i, p in enumerate(pts))
    pgrc = b''.join(struct.pack('<%dI' % len(links[i]), *links[i]) for i in range(len(pts)) if links[i])
    info = mapdata.cell_info(db, cell_key) or {}
    name = info.get('name') or info.get('region') or ''
    data = join_subs([('DATA', struct.pack('<iiHH', gx, gy, 1024, len(pts))), ('NAME', zs(name)), ('PGRP', pgrp), ('PGRC', pgrc)])
    had = any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), []))
    db.project.set_record('PGRD', cell_key, 0, data, created=not had)
    if note:
        editing.commit(db, 'Made walking paths outdoors in %s (%d points)' % (editing.cell_label(db, cell_key), len(pts)))
    return {'points': len(pts), 'links': len(edges), 'replaced': had}


def generate(db, cell_key, note=True):
    """Make walking paths for an interior built from room pieces (or an outdoor cell). Saves them into the mod."""
    if cell_key.startswith('#'):
        return generate_exterior(db, cell_key, note)
    editing._require_project(db)
    info = furnish.rooms(db, cell_key)
    if not info['rooms']:
        raise EditError('No rooms found here. Walking paths can be made for places built from modular room '
                        'pieces (like the ones "Build from pieces" makes, and most town interiors).')
    T = info['tile']
    cinfo = mapdata.cell_info(db, cell_key)
    refs = info['refs']
    # furniture and other things standing on the floor are in the way (rugs, lights and small items aren't)
    boxes = []
    for r in refs:
        b = r.get('b')
        if not b or r.get('arch') or r['type'] in ('LIGH', 'DOOR', 'NPC_', 'CREA', 'LEVC') or r['type'] in mapdata.ITEM_TYPES:
            continue
        if (b[5] - b[2]) * (r['s'] or 1) < 20:
            continue                                   # flat: a rug, a mat
        boxes.append(furnish._footprint(b, r['p'][5], r['p'][0], r['p'][1]))
    # four points in each walkable tile (a half-tile grid), so paths can weave around furniture
    tiles = [(room['id'], t) for room in info['rooms'] for t in room['_tiles']]
    lv = lambda z: int(round(z / 64.0))                 # which floor (buildings can have several)
    tile_at = {(round(t['x']), round(t['y']), lv(t['floor'])): (rid, t) for rid, t in tiles}
    pts, at = [], {}
    q = T / 4
    for rid, t in tiles:
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = t['x'] + sx * q, t['y'] + sy * q
                if not _blocked(boxes, x, y):
                    at[(round(x), round(y), lv(t['floor']))] = len(pts)
                    pts.append([x, y, t['floor'], rid, t])
    edges = set()

    def link(i, j):
        if i is not None and j is not None and i != j and _clear(boxes, pts[i], pts[j]):
            edges.add((min(i, j), max(i, j)))

    for i, (x, y, z, rid, t) in enumerate(pts):
        # neighbours half a tile away (and diagonally), inside the tile or across open floor in the same room
        for dx, dy in ((2, 0), (0, 2), (2, 2), (2, -2)):
            nx, ny = x + dx * q, y + dy * q
            j = at.get((round(nx), round(ny), lv(z)))
            if j is None:
                continue
            u = pts[j][4]
            if u is t:
                link(i, j)
                continue
            # crossing into another tile: only over open floor of the same room
            sides = [s for s, (ux, uy) in STEP.items() if abs(u['x'] - (t['x'] + ux * T)) < 2 and abs(u['y'] - (t['y'] + uy * T)) < 2]
            if sides and pts[j][3] == rid and t['pat'][sides[0]] == 'open' and u['pat'][OPP[sides[0]]] == 'open':
                link(i, j)
            elif not sides and pts[j][3] == rid and dx and dy:
                # diagonal into a corner tile: both tiles beside it must be open floor of this room too
                a = tile_at.get((round(t['x'] + (T if dx > 0 else -T)), round(t['y']), lv(z)))
                b = tile_at.get((round(t['x']), round(t['y'] + (T if dy > 0 else -T)), lv(z)))
                if a and b and a[0] == rid and b[0] == rid:
                    link(i, j)
    # doorways, archways and door frames between rooms: one point in the middle of the opening,
    # joined to the nearest points on both sides
    for rid, t in tiles:
        for s, (dx, dy) in STEP.items():
            other = tile_at.get((round(t['x'] + dx * T), round(t['y'] + dy * T), lv(t['floor'])))
            if not other or (t['x'], t['y']) > (other[1]['x'], other[1]['y']):
                continue
            u = other[1]
            if t['pat'][s] == 'wall' or u['pat'][OPP[s]] == 'wall':
                continue
            if other[0] == rid and t['pat'][s] == 'open' and u['pat'][OPP[s]] == 'open':
                continue                               # open floor: already joined above
            mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
            k = len(pts)
            pts.append([mx, my, min(t['floor'], u['floor']), None, None])
            for side_tile in (t, u):
                near = sorted((j for j in range(k) if pts[j][4] is side_tile),
                              key=lambda j: math.hypot(pts[j][0] - mx, pts[j][1] - my))[:2]
                for j in near:
                    link(k, j)
    # up and down stairs: a point at each end of every stair piece, joined to the floor beside it
    import kits
    m = mapdata.cellmap(db, cell_key)
    ends = []
    for r in m['refs']:
        prefix = kits.kit_prefix(r['id'])
        si = kits.stairs(db, prefix) if prefix and prefix in kits.kits(db) else None
        sp = next((p for p in si['pieces'] if p['id'].lower() == r['id'].lower()), None) if si else None
        if not sp:
            continue
        kp = kits.kit_pieces(db, prefix)
        rz = r['p'][5]
        lx, ly = STEP[sp['low']]
        wx, wy = lx * math.cos(rz) + ly * math.sin(rz), -lx * math.sin(rz) + ly * math.cos(rz)   # the low end, in the world
        z_lo = r['p'][2] + sp['z_low'] + kp['zmin']
        a = len(pts)
        pts.append([r['p'][0] + wx * T * 0.45, r['p'][1] + wy * T * 0.45, z_lo, None, None])
        pts.append([r['p'][0] - wx * T * 0.45, r['p'][1] - wy * T * 0.45, z_lo + sp['rise'], None, None])
        edges.add((a, a + 1))
        ends += [(a, (wx, wy), a + 1), (a + 1, (-wx, -wy), a)]
    for k, (ox, oy), partner in ends:
        # only out of the open end (never through the stair's side walls into a room beside it)
        near = sorted((j for j in range(len(pts)) if j not in (k, partner) and abs(pts[j][2] - pts[k][2]) < 40 and
                       (pts[j][0] - pts[k][0]) * ox + (pts[j][1] - pts[k][1]) * oy > 0),
                      key=lambda j: math.hypot(pts[j][0] - pts[k][0], pts[j][1] - pts[k][1]))[:2]
        for j in near:
            if math.hypot(pts[j][0] - pts[k][0], pts[j][1] - pts[k][1]) < T * 0.6:
                edges.add((min(k, j), max(k, j)))
    # by the doors that lead out, so people can reach them
    import doors as doormod
    for r in m['refs']:
        if r['type'] != 'DOOR' or not r.get('to'):
            continue
        spot = doormod._in_front(m, r)
        near = sorted(range(len(pts)), key=lambda k: math.hypot(pts[k][0] - spot[0], pts[k][1] - spot[1]))
        if not near or math.hypot(pts[near[0]][0] - spot[0], pts[near[0]][1] - spot[1]) < 40:
            continue
        k = len(pts)
        pts.append([spot[0], spot[1], pts[near[0]][2], None, None])
        for j in near[:2]:
            if math.hypot(pts[j][0] - spot[0], pts[j][1] - spot[1]) < T * 1.2 and _clear(boxes, pts[k], pts[j]):
                edges.add((min(k, j), max(k, j)))
    if len(pts) < 2:
        raise EditError('There is too little free floor here for walking paths.')
    # the record: a header, the points, then each point's connections in turn
    links = {i: [] for i in range(len(pts))}
    for a, b in sorted(edges):
        links[a].append(b)
        links[b].append(a)
    pgrp = b''.join(struct.pack('<iiiBBH', int(round(p[0])), int(round(p[1])), int(round(p[2])), 1, len(links[i]), 0)
                    for i, p in enumerate(pts))
    pgrc = b''.join(struct.pack('<%dI' % len(links[i]), *links[i]) for i in range(len(pts)) if links[i])
    data = join_subs([('DATA', struct.pack('<iiHH', 0, 0, 256, len(pts))), ('NAME', zs(cinfo['name'])),
                      ('PGRP', pgrp), ('PGRC', pgrc)])
    had = any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), []))
    db.project.set_record('PGRD', cell_key, 0, data, created=not had)
    if note:
        editing.commit(db, 'Made walking paths for %s (%d points)' % (cinfo['name'], len(pts)))
    return {'points': len(pts), 'links': len(edges)}
