"""Walking paths (path grids): the invisible network of points NPCs and creatures walk along.

For places built from room pieces, a point goes into each walkable tile (moved aside if furniture
stands there), joined to its neighbours where you can walk through: open floor, archways and door
frames. Points by the way out let people reach the door."""
import math
import re
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


def save(db, cell_key, pts, edges, note=None):
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
    editing.commit(db, (note or 'Edited the walking paths in %s (%d points, %d links)') % (editing.cell_label(db, cell_key), len(pts), n))
    return {'points': len(pts), 'links': n}


# ------------------------------------------------------------------ redraw, anywhere
# Project Tamriel's "Path Grids Explained", as rules: less is more (a point a tile, the game's own median 1.0 a
# floor tile over 100 interiors); links only where you can walk straight from one to the other; no redundant
# links (the game's points have two links, its p90 three); points on both sides of furniture, not through it;
# a point in front of every door; none left without a link. Measured 2026-10-24.
WALK = 256            # (a tile: the game's links are 171 / 234 / 278 long, p10 / p50 / p90)
LAT = 128             # (the floor is found on a lattice half a tile apart, to get through door frames and narrow tunnels)
RISE = 200            # (the most a link may climb: a Dwemer ramp rises 192 over a tile)
HEAD = 100            # (room overhead for a person to pass)
COVER = 300          # (a kept point stands for the floor this near it that it can see)
LINK = 620           # (the longest link: the game's longest, median 411, p90 about 600)
ROOMS_FIRST = True    # (a place of room tiles by its tiles; the lab turns it off to compare)


WHY = [None]         # (why the last link test said no: for the checks)
STAIRS = re.compile(r'stair|ramp|_steps')
STEP_UP = 50         # (the most the floor may rise or drop from one step of a walked link to the next, 32 on)
ROCK = re.compile(r'cave|_rock|terrrock|boulder|_mine|grotto|cavern')


def walk_grid(db, cell_key, starts=(), roof=True, raw=False):
    """Points and links for any interior, worked out from its real floors and walls (the same triangles the
    gap finder looks at): from the doors and the old points, step a tile at a time over every floor a person
    can walk to, round furniture, up and down ramps and stairs. (pts [[x, y, z]], edges [[a, b]])."""
    import doors as doormod
    import seethrough
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists'):
        raise EditError('That place does not exist.')
    # (doors left out of what is in the way: the game's own paths run through them, as people open them)
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['type'] != 'DOOR']))
    boxes = []
    for r in m['refs']:
        b = r.get('b')
        if not b or r.get('arch') or r['type'] in ('LIGH', 'DOOR', 'NPC_', 'CREA', 'LEVC') or r['type'] in mapdata.ITEM_TYPES:
            continue
        s = r.get('s') or 1
        if (b[5] - b[2]) * s < 40:
            continue                                   # (a rug, a low step)
        boxes.append((furnish._footprint([v * s for v in b], r['p'][5], r['p'][0], r['p'][1]), r['p'][2] + b[2] * s, r['p'][2] + b[5] * s))

    def furniture(x, y, z):
        return any(f[0] - 16 < x < f[2] + 16 and f[1] - 16 < y < f[3] + 16 and zb - 40 < z + 40 < zt for f, zb, zt in boxes)

    roofed = [roof]

    def floor(x, y, z):
        """The floor under (x, y) near height z, with room overhead, or None."""
        for up in (60, 150, RISE + 40):
            h = sc.nearest_any((x, y, z + up), (0.0, 0.0, -1.0), up + 260)
            if h is None:
                continue
            fz = z + up - h[0]
            if abs(fz - z) > RISE + 20:
                continue
            top = sc.nearest_any((x, y, fz + 8), (0.0, 0.0, 1.0), HEAD + 40)
            if top is not None and top[0] < HEAD:
                continue
            # (indoors, a floor has a ceiling somewhere above it: the top of a cave's rock shell, seen from
            # the void outside it, has none; a cave door's front can lie out there)
            if roofed[0] and top is None and sc.nearest_any((x, y, fz + 8), (0.0, 0.0, 1.0), 4000) is None:
                continue
            fid = ids_by_k.get(sc.owner(h[1]), '')
            on_stair[0] = bool(STAIRS.search(fid))
            on_rock[0] = bool(ROCK.search(fid))
            return fz
        return None

    # (stairs and ramps: their steps are walked up, though a riser stands at waist height a step ahead and
    # the floor steps away from a straight line; in the lab Daedric and Velothi stairs cut whole places off)
    ids_by_k = {r['k']: r['id'].lower() for r in m['refs']}
    on_stair = [False]
    on_rock = [False]

    def clear(a, b):
        """A person can walk straight from a to b: step by step along the floor (never more than 60 off the
        straight line between the ends: no hollow or hump spanned), and nothing in the way at shin, waist or
        head height from each step to the next, no furniture. (Straight rays from end to end, with a level
        one from the higher end when the sloping one hit, let links over humps and through rock past: the
        user saw them in a made cave, and Redraw on the game's caves had 6.7% through rock, 2026-10-24.)"""
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 1:
            return False
        n = max(1, int(d / 32))
        px, py, pz = a[0], a[1], a[2]
        on_stair[0] = on_rock[0] = False
        for k in range(1, n + 1):
            was = on_stair[0]
            t = k / n
            x, y = a[0] + dx * t, a[1] + dy * t
            zi = a[2] + (b[2] - a[2]) * t
            if k < n:
                if furniture(x, y, zi):
                    WHY[0] = 'furniture'
                    return False
                fz = floor(x, y, zi)
                if fz is None or abs(fz - zi) > (160 if on_stair[0] else 90):     # (stepped floors stray from the line)
                    WHY[0] = 'no floor' if fz is None else 'floor off the line'
                    return False
            else:
                fz = b[2]
            # (a step up or down no person takes, the last one too: the game climbs about 46 at a step;
            # Daedric corners have a ledge 90 high that links ran up onto, 2026-10-24)
            # (scaled to the step's length: the last one runs up to twice as far; a cave's rock floor is rough)
            if abs(fz - pz) > (90 if (on_stair[0] or was) else 75 if on_rock[0] else min(75, max(STEP_UP, STEP_UP * math.hypot(x - px, y - py) / 32))):
                WHY[0] = 'step too high'
                return False
            sx, sy, sz = x - px, y - py, fz - pz
            L = math.sqrt(sx * sx + sy * sy + sz * sz)
            if L > 1:
                for hgt in (50, 80, 100):                     # (above a stair's riser and a door frame's sill, waist, chin: a
                                                              # sloping cave tunnel's roof is low)
                    h = sc.nearest_any((px, py, pz + hgt), (sx / L, sy / L, sz / L), L)
                    if h is not None and h[0] < L - 2:
                        if (was or on_stair[0] or hgt < 100) and STAIRS.search(ids_by_k.get(sc.owner(h[1]), '')):
                            continue                  # (a stair's own steps and sloping roof, walked on it)
                        WHY[0] = ('hit', hgt, sc.owner(h[1]))
                        return False
            px, py, pz = x, y, fz
        return True
    # where to start: in front of each door, and the old points
    seeds, door_pts = [], []
    for r in m['refs']:
        if r['type'] == 'DOOR':
            try:
                sx, sy = doormod._in_front(m, r)[:2]
            except Exception:
                continue
            fz = floor(sx, sy, r['p'][2])
            if fz is not None:
                seeds.append((sx, sy, fz))
                door_pts.append((sx, sy, fz))
    # (spots known to be inside, e.g. where a made dungeon's front door sets you down: a door's front is
    # worked out from the door alone, and a cave's door can face the rock)
    for p in starts:
        fz = floor(p[0], p[1], p[2])
        if fz is not None:
            seeds.append((p[0], p[1], fz))
            door_pts.append((p[0], p[1], fz))
    old = read(db, cell_key)
    for p in (old or {}).get('pts', [])[:200]:
        fz = floor(p[0], p[1], p[2])
        if fz is not None:
            seeds.append((p[0], p[1], fz))
    if not seeds:
        arch = [r for r in m['refs'] if r.get('arch')]
        if arch:
            c = arch[len(arch) // 2]
            fz = floor(c['p'][0], c['p'][1], c['p'][2])
            if fz is not None:
                seeds.append((c['p'][0], c['p'][1], fz))
    if not seeds and roof:
        # (a place open to the sky, which "behaves like outdoors": floors with no ceiling over them count)
        return walk_grid(db, cell_key, starts, roof=False, raw=raw)
    if not seeds:
        raise EditError('Found no floor to walk on here.')
    # a lattice a tile apart from the first seed; each lattice spot may be a little off its mark to clear furniture
    ox, oy = seeds[0][0], seeds[0][1]
    key_of = lambda x, y, z: (int(round((x - ox) / LAT)), int(round((y - oy) / LAT)), int(round(z / 160.0)))
    pts, at, edges = [], {}, set()

    def place(x, y, z):
        i, j, lv = key_of(x, y, z)
        for nb in ((i, j, lv), (i, j, lv - 1), (i, j, lv + 1)):
            if nb in at:
                return at[nb], False
        cx, cy = ox + i * LAT, oy + j * LAT
        for dx, dy in ((0, 0), (32, 0), (-32, 0), (0, 32), (0, -32), (48, 48), (-48, 48), (48, -48), (-48, -48)):
            fz = floor(cx + dx, cy + dy, z)
            if fz is not None and not furniture(cx + dx, cy + dy, fz):
                at[(i, j, lv)] = len(pts)
                pts.append([cx + dx, cy + dy, fz])
                return len(pts) - 1, True
        return None, False
    queue = []
    for s in seeds:
        k, new = place(*s)
        if new:
            queue.append(k)
    while queue and len(pts) < 12000:
        k = queue.pop(0)
        x, y, z = pts[k]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            tx, ty = x + dx * LAT, y + dy * LAT
            fz = floor(tx, ty, z)
            if fz is None or abs(fz - z) > RISE:
                continue
            j, new = place(tx, ty, fz)
            if j is None or j == k:
                continue
            if clear(pts[k], pts[j]):
                edges.add((min(k, j), max(k, j)))
                if new:
                    queue.append(j)
            elif new:
                queue.append(j)
    if raw == 'clear':
        return pts, edges, door_pts, clear
    if raw:
        return pts, edges, door_pts
    return _sparse(pts, edges, at, key_of, door_pts, clear)


def _sparse(pts, edges, at, key_of, door_pts, clear):
    """From the fine lattice (a point a tile wherever there is floor) to a grid like the game's: the floor
    joined to the doors only; enough points that all of it is in sight of one; joined where they see each
    other, with no link that has a shorter way round; mended back into one piece through the lattice."""
    # the door points, joined into the lattice
    for d in door_pts:
        near = sorted(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - d[0], pts[i][1] - d[1]))
        if near and math.hypot(pts[near[0]][0] - d[0], pts[near[0]][1] - d[1]) > 60:
            k = len(pts)
            pts.append([d[0], d[1], d[2]])
            for j in near[:4]:
                if math.hypot(pts[j][0] - d[0], pts[j][1] - d[1]) < WALK * 1.4 and clear(pts[k], pts[j]):
                    edges.add((min(k, j), max(k, j)))
    nb = {i: set() for i in range(len(pts))}
    for a, b in edges:
        nb[a].add(b)
        nb[b].add(a)
    doors_i = [min(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - d[0], pts[i][1] - d[1]) + abs(pts[i][2] - d[2])) for d in door_pts] if pts else []
    # 1. only the floor a person can walk to from a door (else the biggest piece): no islands
    seen, comps = set(), []
    for s in range(len(pts)):
        if s in seen:
            continue
        comp, q = [], [s]
        seen.add(s)
        while q:
            u = q.pop()
            comp.append(u)
            for v in nb[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        comps.append(comp)
    # (the biggest piece of floor, and every piece with a door or of some size, bridged to it by the nearest
    # clear line: a door in a pocket of its own, the lattice stepping past a ledge)
    comps.sort(key=len, reverse=True)
    live = set(comps[0]) if comps else set()
    for c in comps[1:]:
        if not (any(d in c for d in doors_i) or len(c) >= 3):
            continue
        best = None
        for a in c:
            for b in live:
                d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                if d < LINK * 1.2 and abs(pts[a][2] - pts[b][2]) < RISE * max(1.0, d / WALK) and (best is None or d < best[0]):
                    best = (d, a, b)
        tries = sorted(((math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]), a, b) for a in c for b in live
                        if math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]) < LINK * 1.2))[:12] if best else []
        for d, a, b in tries:
            if clear(pts[a], pts[b]):
                nb[a].add(b)
                nb[b].add(a)
                live |= set(c)
                break
        else:
            if any(d in c for d in doors_i):
                live |= set(c)                # (a door's own pocket, even unjoined: its people still walk there)
    if not live:
        return [], []                        # (no floor joined up anywhere: nothing to draw)
    # 2. enough points: in order from the doors outwards, a point is kept unless a kept one within COVER sees it
    order, q, dist = [], list(dict.fromkeys(d for d in doors_i if d in live)) or [next(iter(live))], {}
    for s in q:
        dist[s] = 0
    while q:
        u = q.pop(0)
        order.append(u)
        for v in sorted(nb[u]):
            if v in live and v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    order += [u for u in live if u not in dist]
    kept, owner = [], {}
    for u in order:
        hit = None
        for k in kept:
            if math.hypot(pts[k][0] - pts[u][0], pts[k][1] - pts[u][1]) < COVER and abs(pts[k][2] - pts[u][2]) < 80 and clear(pts[k], pts[u]):
                hit = k
                break
        if hit is None or u in doors_i:
            kept.append(u)
            owner[u] = u
        else:
            owner[u] = hit
    # 3. joined where they see each other, within LINK; a link goes when a third point is nearer both ends
    ks = set(kept)
    cand = []
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
            if d < LINK and abs(pts[a][2] - pts[b][2]) < RISE * max(1.0, d / WALK):
                cand.append((d, a, b))
    out = set()
    for d, a, b in sorted(cand):
        if any(c not in (a, b) and math.hypot(pts[a][0] - pts[c][0], pts[a][1] - pts[c][1]) < d and
               math.hypot(pts[b][0] - pts[c][0], pts[b][1] - pts[c][1]) < d for c in kept):
            continue                       # (a shorter way round, by c: the relative neighbourhood graph)
        if clear(pts[a], pts[b]):
            out.add((min(a, b), max(a, b)))
    # 4. one piece: where two neighbours on the lattice belong to kept points not yet joined, join their owners
    # (or, failing a clear line between those, bring the two lattice points in as points of their own)
    def pieces():
        par = {k: k for k in ks}

        def f(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for a, b in out:
            par[f(a)] = f(b)
        return f
    for _round in range(6):
        f = pieces()
        added = False
        for u in live:
            for v in nb[u]:
                if v not in live or u > v:
                    continue
                ou, ov = owner[u], owner[v]
                if f(ou) == f(ov):
                    continue
                if clear(pts[ou], pts[ov]) and math.hypot(pts[ou][0] - pts[ov][0], pts[ou][1] - pts[ov][1]) < LINK * 1.4:
                    out.add((min(ou, ov), max(ou, ov)))
                else:
                    for w in (u, v):
                        if w not in ks:
                            ks.add(w)
                            owner[w] = w
                    out.add((min(u, v), max(u, v)))
                    if ou != u and clear(pts[ou], pts[u]):
                        out.add((min(ou, u), max(ou, u)))
                    if ov != v and clear(pts[ov], pts[v]):
                        out.add((min(ov, v), max(ov, v)))
                added = True
                f = pieces()
        if not added:
            break
    # 5. less is more, once more: a point with two links goes when its two neighbours see each other (within
    # LINK), a dead end when its neighbour covers its floor; never a door's point
    dset = set(doors_i)
    adj = {}
    for a, b in out:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    changed = True
    while changed:
        changed = False
        for k in sorted(adj, key=lambda i: len(adj[i])):
            if k in dset or k not in adj:
                continue
            s = adj[k]
            if len(s) == 1:
                (a,) = s
                if math.hypot(pts[a][0] - pts[k][0], pts[a][1] - pts[k][1]) < COVER * 0.8 and len(adj[a]) > 1:
                    adj[a].discard(k)
                    del adj[k]
                    changed = True
            elif len(s) == 2:
                a, b = sorted(s)
                if b in adj[a]:
                    continue
                d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                if d < LINK and clear(pts[a], pts[b]):
                    adj[a].discard(k)
                    adj[b].discard(k)
                    adj[a].add(b)
                    adj[b].add(a)
                    del adj[k]
                    changed = True
    out = {(min(a, b), max(a, b)) for a, s in adj.items() for b in s}
    used = sorted({i for e in out for i in e})
    new = {o: n for n, o in enumerate(used)}
    return [[round(pts[o][0]), round(pts[o][1]), round(pts[o][2])] for o in used], sorted([new[a], new[b]] for a, b in out)


def redraw(db, cell_key, starts=()):
    """Walking paths made afresh by Project Tamriel's rules, for any place: outdoors as before, a place built
    from room pieces by its tiles, anything else (caves, ruins, the game's own odd shapes) from its real
    floors. Replaces what it has (the game's own paths too, in your mod). One change."""
    if cell_key.startswith('#'):
        return generate_exterior(db, cell_key)
    try:
        info = furnish.rooms(db, cell_key)
    except Exception:
        info = {'rooms': []}
    # (by the tiles only where the plan of them is the Workshop's own, Build from pieces: in the game's places
    # the room reader finds tiles in caves and halls too, and the floors are the truer guide)
    built = bool(((db.project.cells.get(cell_key) or {}).get('plan') or {}).get('rooms')) if db.project else False
    if built and info.get('rooms') and _tile_ok(info) and not info.get('traced') and ROOMS_FIRST:
        try:
            return dict(generate(db, cell_key), how='rooms')
        except EditError:
            pass
    pts, edges = walk_grid(db, cell_key, starts)
    r = save(db, cell_key, pts, edges, note='Redrew the walking paths in %s (%d points, %d links)')
    return dict(r, how='floors')


def _tile_ok(info):
    """A place whose rooms are made of the kit's floor tiles all through (Build from pieces, town houses)."""
    return bool(info.get('tile')) and all(r.get('_tiles') for r in info['rooms'])


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
    # a point in the middle of each walkable tile, as the game's own grids have it (one point a floor tile,
    # links of about a tile, two links a point: 100 game interiors measured 2026-10-24, and Project Tamriel's
    # "less is more": one node in the middle of a tile reaches all of it); where furniture stands on the
    # middle, the tile's free quarter points instead, so the paths go round it
    tiles = [(room['id'], t) for room in info['rooms'] for t in room['_tiles']]
    lv = lambda z: int(round(z / 64.0))                 # which floor (buildings can have several)
    tile_at = {(round(t['x']), round(t['y']), lv(t['floor'])): (rid, t) for rid, t in tiles}
    pts, of_tile = [], {}
    q = T / 4
    for rid, t in tiles:
        if not _blocked(boxes, t['x'], t['y']):
            spots = [(t['x'], t['y'])]
        else:
            spots = [(t['x'] + sx * q, t['y'] + sy * q) for sx in (-1, 1) for sy in (-1, 1) if not _blocked(boxes, t['x'] + sx * q, t['y'] + sy * q)]
        of_tile[id(t)] = []
        for x, y in spots:
            of_tile[id(t)].append(len(pts))
            pts.append([x, y, t['floor'], rid, t])
    edges = set()

    def link(i, j):
        if i is not None and j is not None and i != j and _clear(boxes, pts[i], pts[j]):
            edges.add((min(i, j), max(i, j)))
            return True
        return False

    def nearest_pair(a, b):
        """The closest clear pair of points between two tiles' points, joined; True when one was."""
        pairs = sorted(((math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]), i, j) for i in of_tile[id(a)] for j in of_tile[id(b)]))
        return any(link(i, j) for _d, i, j in pairs[:3] if _clear(boxes, pts[i], pts[j]))

    # (the quarter points of one tile, joined round whatever stands in its middle)
    for rid, t in tiles:
        own = of_tile[id(t)]
        for a_ in range(len(own)):
            for b_ in range(a_ + 1, len(own)):
                if math.hypot(pts[own[a_]][0] - pts[own[b_]][0], pts[own[a_]][1] - pts[own[b_]][1]) < T * 0.6:
                    link(own[a_], own[b_])
    for rid, t in tiles:
        z = t['floor']
        joined = {}
        # the tile beside it across open floor of the same room
        for s, (ux, uy) in STEP.items():
            o = tile_at.get((round(t['x'] + ux * T), round(t['y'] + uy * T), lv(z)))
            if o and o[0] == rid and t['pat'][s] == 'open' and o[1]['pat'][OPP[s]] == 'open' and (t['x'], t['y']) < (o[1]['x'], o[1]['y']):
                joined[s] = nearest_pair(t, o[1])
            elif o and o[0] == rid and t['pat'][s] == 'open' and o[1]['pat'][OPP[s]] == 'open':
                joined[s] = True                      # (joined from the other side)
        # diagonally only where a straight way round is missing (a table on the tile beside: the game's
        # grids keep to two links a point, and the guide's redundant links are its worst grids)
        for dx, dy, s1, s2 in ((1, 1, 'E', 'N'), (1, -1, 'E', 'S')):
            o = tile_at.get((round(t['x'] + dx * T), round(t['y'] + dy * T), lv(z)))
            a = tile_at.get((round(t['x'] + dx * T), round(t['y']), lv(z)))
            b = tile_at.get((round(t['x']), round(t['y'] + dy * T), lv(z)))
            if not (o and a and b and o[0] == rid and a[0] == rid and b[0] == rid):
                continue
            if joined.get(s1) and joined.get(s2):
                continue
            nearest_pair(t, o[1])
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
                              key=lambda j: math.hypot(pts[j][0] - mx, pts[j][1] - my))[:1]
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
    # (a point with no link is no use to anyone: Project Tamriel's rule 9, and none of 100 game grids has one)
    used = sorted({i for e in edges for i in e})
    if len(used) < len(pts):
        new = {o: n for n, o in enumerate(used)}
        pts = [pts[o] for o in used]
        edges = {(new[a], new[b]) for a, b in edges}
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
