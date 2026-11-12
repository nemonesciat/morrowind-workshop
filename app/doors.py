"""Where doors lead: read, change or remove a door's destination, pick a sensible place to
arrive, and optionally point the door at the other end back here."""
import math
import re
import struct

import editing
import mapdata
from editing import EditError
from esm import zstr
from project import ref_info, zs

CELL = 8192


def link_of(subs):
    """{'cell': name or '', 'x', 'y', 'z', 'rz'} for a door that leads somewhere, else None."""
    d = dict((t, bytes(v)) for t, v in subs)
    if 'DODT' not in d or len(d['DODT']) < 24:
        return None
    x, y, z, _rx, _ry, rz = struct.unpack_from('<6f', d['DODT'])
    out = {'cell': zstr(d['DNAM']) if 'DNAM' in d else '', 'x': round(x, 1), 'y': round(y, 1), 'z': round(z, 1),
           'rz': round(rz, 4)}
    out['key'] = target_key(out)
    return out


def target_key(link):
    """The cell key a link points at ('' = outdoors, by position)."""
    if link['cell']:
        return link['cell'].lower()
    return '#%d,%d' % (math.floor(link['x'] / CELL), math.floor(link['y'] / CELL))


_scenes = {}


def _floor_at(db, m, x, y, bottom):
    """The floor under (x, y) near a door's foot in a place's own walls and floors (seethrough), or None: nothing to
    stand on there, or no room to stand."""
    import seethrough
    key = (id(db.recs), m.get('key'), len(m['refs']))
    if key not in _scenes:
        _scenes.clear()
        _scenes[key] = seethrough.place_scene(db, m)
    sc = _scenes[key]
    hit = sc.nearest_any((x, y, bottom + 90.0), (0.0, 0.0, -1.0), 260.0)
    if hit is None:
        return None
    z = bottom + 90.0 - hit[0]
    if abs(z - bottom) > 110:
        return None
    up = sc.nearest_any((x, y, z + 20.0), (0.0, 0.0, 1.0), 400.0)
    if up is not None and up[0] < 100:
        return None                                    # (under a ledge or in a wall: no room)
    return z


ROOF_REACH = 1500.0            # (something over a floor within this: indoors; nothing: the top of the place's shell)


def _roofed(db, m, x, y, z):
    """Whether a floor spot in a place has anything over it: the top of a room's ceiling, outside the walls, has not."""
    import seethrough
    key = (id(db.recs), m.get('key'), len(m['refs']))
    if key not in _scenes:
        _scenes.clear()
        _scenes[key] = seethrough.place_scene(db, m)
    return _scenes[key].nearest_any((x, y, z + 20.0), (0.0, 0.0, 1.0), ROOF_REACH) is not None


def stand_spot(db, m, x, y, top, rz=None):
    """Where the player stands at a spot picked for a door's arrival: [x, y, z, rz] and whether it was moved off a
    wall, or None (nothing to stand on). The floor is the first one down from `top` with room to stand (a click on
    the map has no height: top is a step above the nearest door's foot, so roofs, upper storeys and tables over the
    spot are not it); the spot is pushed out of the walls round it, and a facing not given is away from the nearest
    door, into the place. Picked arrivals took the top of whatever stood there and faced north: "pressing on where
    I want to land seems to have random effects" (StingDR, 2026-11-02)."""
    import seethrough
    if m['interior']:
        key = (id(db.recs), m.get('key'), len(m['refs']))
        if key not in _scenes:
            _scenes.clear()
            _scenes[key] = seethrough.place_scene(db, m)
        sc, land = _scenes[key], None
    else:
        sc, land = _local_scene(db, {'p': [x, y, 0.0]}), mapdata.terrain_z(db, x, y)
    z = None
    for _ in range(4):
        hit = sc.nearest_any((x, y, top), (0.0, 0.0, -1.0), 2000.0)
        f = top - hit[0] if hit else None
        if land is not None and land <= top and (f is None or land > f):
            f = land
        if f is None:
            break
        up = sc.nearest_any((x, y, f + 20.0), (0.0, 0.0, 1.0), 400.0)
        if up is None or up[0] >= 100:
            z = f
            break
        top = f - 5.0                                  # (under a ledge or a table top: the floor beneath)
    if z is None:
        return None
    moved = False
    for _ in range(2):
        px = py = 0.0
        for i in range(8):
            dx, dy = math.sin(i * math.pi / 4), math.cos(i * math.pi / 4)
            h = sc.nearest_any((x, y, z + 50.0), (dx, dy, 0.0), 40.0)
            if h:
                px -= dx * (40.0 - h[0])
                py -= dy * (40.0 - h[0])
        if math.hypot(px, py) < 2:
            break
        x, y, moved = x + px, y + py, True
    if rz is None:
        ds = [r for r in m['refs'] if r['type'] == 'DOOR' and math.hypot(r['p'][0] - x, r['p'][1] - y) < 600]
        d = min(ds, key=lambda r: math.hypot(r['p'][0] - x, r['p'][1] - y), default=None)
        rz = math.atan2(x - d['p'][0], y - d['p'][1]) if d else 0.0
    return [x, y, z + 10.0, rz], moved


OUT_NEAR = 1500                # (the buildings round an outdoor door, for its open side)
FRONT_SHUT = 7                 # (a door model's learnt front is taken unless it is this shut in: walls all round and a roof)


def _local_scene(db, door):
    """The walls, roofs and floors round an outdoor door: its cell's and OUT_NEAR round it, as a ray scene (kept until
    the next change)."""
    import seethrough
    px, py = door['p'][0], door['p'][1]
    gx, gy = math.floor(px / CELL), math.floor(py / CELL)
    refs = []
    x0, y0 = gx * CELL - OUT_NEAR, gy * CELL - OUT_NEAR
    x1, y1 = (gx + 1) * CELL + OUT_NEAR, (gy + 1) * CELL + OUT_NEAR
    for cx in (gx - 1, gx, gx + 1):
        for cy in (gy - 1, gy, gy + 1):
            for r in mapdata.cellmap(db, '#%d,%d' % (cx, cy)).get('refs') or ():
                if x0 < r['p'][0] < x1 and y0 < r['p'][1] < y1 and (r.get('arch') or r['type'] == 'DOOR'):
                    refs.append(r)
    # (kept while the same pieces stand where they stood: a town links forty doors, a change each, and by the change
    # count it built the scene again for every one, 1.5 s a door)
    key = ('out', id(db.recs), gx, gy, hash(tuple((r['k'], tuple(r['p'])) for r in refs)))
    if key in _scenes:
        return _scenes[key]
    if len(_scenes) > 8:
        _scenes.clear()
    _scenes[key] = seethrough.place_scene(db, {'refs': refs})
    return _scenes[key]


def middle(door):
    """A door's middle on the ground plan (x, y): many door models stand on their hinge edge (in_c_door_wood_square's
    box runs 0 to 132 across), and a step out from the origin put you beside the door, not in front of it."""
    b = door.get('b')
    if not b:
        return door['p'][0], door['p'][1]
    s = door.get('s') or 1.0
    mx, my = (b[0] + b[3]) / 2 * s, (b[1] + b[4]) / 2 * s
    c, sn = math.cos(door['p'][5]), math.sin(door['p'][5])
    return door['p'][0] + mx * c + my * sn, door['p'][1] - mx * sn + my * c


def outside_spot(db, door, prefer=None):
    """Where to arrive in front of an outdoor door: a step out on its open side, on the ground or its porch, facing
    away from it; None when neither side has room. The door's two faces are tried (prefer's first), each a step
    and further out, and the one less shut in by walls round it and a roof over it wins: the middle of the things near
    the door, the guess before, lay inside the house next to it, and the user and PIN2 came out of their interiors in
    the walls or behind them (2026-11-01, "it sends me out of bounds and i have to set the locations manually")."""
    import doorfronts
    b = door.get('b')
    if not b:
        return None
    s = door.get('s') or 1.0
    px, py = middle(door)
    ux, uy = doorfronts.thin_axis(door)
    sides = [(ux, uy), (-ux, -uy)]
    if prefer:
        sides.sort(key=lambda t: -(t[0] * prefer[0] + t[1] * prefer[1]))
    # (the side the game's own doors of this model put you on, where it has room and isn't shut in: doorfronts)
    f = doorfronts.front(db, door)
    if f:
        sides.sort(key=lambda t: -(t[0] * f * ux + t[1] * f * uy))
    bottom = door['p'][2] + b[2] * s
    sc = _local_scene(db, door)
    best = None
    for k, (tx, ty) in enumerate(sides):
        for dist in (110, 160, 220, 300):
            x, y = px + tx * dist, py + ty * dist
            g = mapdata.terrain_z(db, x, y)
            hit = sc.nearest_any((x, y, bottom + 90.0), (0.0, 0.0, -1.0), 260.0)
            z = bottom + 90.0 - hit[0] if hit is not None else None
            if g is not None and (z is None or z < g):
                z = g
            if z is None or abs(z - bottom) > 160:
                continue
            if sc.nearest_any((x, y, z + 20.0), (0.0, 0.0, 1.0), 100.0) is not None:
                continue                                      # (in a wall or under a ledge)
            # (a floor, not a railing's or a post's top: the ground round it is at its height; an arrival stood 383 over
            # the ground, the in-game walk 2026-11-03)
            if not _floor_about(sc, g, x, y, z):
                continue
            # (something between it and the door: behind a wall, 2 of 26 in a town; but a porch post or railing too,
            # so only a last choice: refused outright, 91% of the game's doors against 93%)
            blocked = dist > 100 and sc.nearest_any((x, y, z + 60.0), (-tx, -ty, 0.0), dist - 60.0) is not None
            shut = sum(1 for a in range(8) if sc.nearest_any((x, y, z + 70.0), (math.cos(a * math.pi / 4), math.sin(a * math.pi / 4), 0.0), 500.0) is not None)
            if sc.nearest_any((x, y, z + 20.0), (0.0, 0.0, 1.0), 1200.0) is not None:
                shut += 3                                     # (a roof over it: inside a building)
            cand = (blocked, shut, k, x, y, z, tx, ty)
            if blocked and dist < 300:
                if best is None or cand[:3] < best[:3]:
                    best = cand
                continue                                      # (further out may see past it)
            if f and k == 0 and shut <= FRONT_SHUT:
                best = cand
                break
            if best is None or cand[:3] < best[:3]:
                best = cand
            break
        if f and best and best[2] == 0 and not best[0] and best[1] <= FRONT_SHUT:
            break
    if best is None:
        return None
    _bl, _sh, _k, x, y, z, tx, ty = best
    return [round(x, 1), round(y, 1), round(z + 12, 1), 0.0, 0.0, round(math.atan2(tx, ty) % (2 * math.pi), 4)]


def _floor_about(sc, g, x, y, z):
    """Whether the floor at (x, y, z) goes on round it: three of its four neighbours 40 out stand within 60 of z."""
    ok = 0
    for dx, dy in ((40.0, 0.0), (-40.0, 0.0), (0.0, 40.0), (0.0, -40.0)):
        hit = sc.nearest_any((x + dx, y + dy, z + 90.0), (0.0, 0.0, -1.0), 260.0)
        f = z + 90.0 - hit[0] if hit is not None else None
        if g is not None and (f is None or f < g):
            f = g
        if f is not None and abs(f - z) <= 60:
            ok += 1
    return ok >= 3


def door_spots(db, refs):
    """Of these [(cell, ref)], the outdoor doors that lead into an interior, with where they stood: for follow."""
    out = []
    by = {}
    for ck, rk in refs:
        if not ck.startswith('#'):
            continue
        if ck not in by:
            by[ck] = {r['k']: r for r in mapdata.cellmap(db, ck).get('refs') or ()}
        r = by[ck].get(rk)
        if r and r['type'] == 'DOOR' and (r.get('to') or {}).get('cell'):
            out.append((ck, rk, r['p'][:2], r['to']['key']))
    return out


FOLLOW_NEAR = 700              # (an interior's way out this close to where its door stood leads to that door)


def follow(db, was):
    """Each moved door's interior way out set again in front of the door where it stands now (outside_spot): moved
    with its building, a house's door left its interior letting you out where the house had been, the user's town,
    2026-11-01 ("the interiors don't point to the right exits"). The number changed; committed as one step."""
    n = 0
    for ck, rk, old, ik in was:
        d = next((r for r in mapdata.cellmap(db, ck).get('refs') or () if r['k'] == rk), None)
        if d is None or math.hypot(d['p'][0] - old[0], d['p'][1] - old[1]) < 1:
            continue
        spot = outside_spot(db, d) or _in_front(mapdata.cellmap(db, ck), d, None)
        im = mapdata.cellmap(db, ik)
        for b in im.get('refs') or ():
            to = b.get('to') if b['type'] == 'DOOR' else None
            if not to or to.get('cell') or math.hypot(to['x'] - old[0], to['y'] - old[1]) > FOLLOW_NEAR:
                continue
            c, refs = editing._cell(db, ik)
            ref = refs.get(b['k'])
            if ref is None:
                continue
            editing._store(c, b['k'], ref['origin'], ref['idx'], _set_link(ref['subs'], '', spot))
            n += 1
    if n:
        editing.commit(db, 'Moved the way out of %d interior%s with its door' % (n, '' if n == 1 else 's'))
    return n


def _in_front(m, door, db=None):
    """A spot a step away from a door, on the room side, facing away from it. With db, in a place with walls and
    floors: the side with floor to stand on, tried both ways (the middle of the things near a door was the guess, and
    in a cave or ruin it lay behind the door: you arrived outside the walls, in the void, the user 2026-10-30)."""
    px, py = middle(door)
    near = [r['p'] for r in m['refs'] if r is not door and 60 < math.hypot(r['p'][0] - px, r['p'][1] - py) < 900]
    if near:
        cx, cy = sum(p[0] for p in near) / len(near) - px, sum(p[1] for p in near) / len(near) - py
    else:
        cx, cy = math.sin(door['p'][5]), math.cos(door['p'][5])
    d = math.hypot(cx, cy) or 1.0
    ux, uy = cx / d, cy / d
    bottom = door['p'][2] + ((door.get('b') or [0, 0, 0])[2]) * (door.get('s') or 1.0)
    z = bottom + 12
    if db is not None and (not m.get('interior') or m.get('like_exterior')):
        try:
            spot = outside_spot(db, door, (ux, uy))
        except Exception as e:
            print('outside spot:', e)
            spot = None
        if spot:
            return spot
    if db is not None and m.get('interior'):
        fx, fy = math.sin(door['p'][5]), math.cos(door['p'][5])
        # (straight out of the door's face first, on the side of the things near it: the things' middle alone put
        # you off to one side of the door, at a slant, 2026-11-02)
        try:
            import doorfronts
            nx, ny = doorfronts.thin_axis(door) if door.get('b') else (fx, fy)
        except Exception:
            nx, ny = fx, fy
        if nx * ux + ny * uy < 0:
            nx, ny = -nx, -ny
        tries = [(nx, ny), (-nx, -ny), (ux, uy), (-ux, -uy), (fy, -fx), (-fy, fx)]
        # (the first side with floor, the middle of the things near it first: tried against 150 of the game's door
        # pairs, its spots fell on the wrong side of the door 6% of the time, the guess alone 10%; choosing the side
        # with more room when both had floor made it 12%)
        # (and a floor with a roof over it before one under the open void: a door on an upper storey, the room
        # below reaching out past it, had "floor" on both sides, the far one the top of that room's ceiling: the
        # user's Tharen Rise tavern, 2026-11-11, "door sets you on top of the ceiling")
        for roofed in (True, False):
            for tx, ty in tries:
                for dist in (110, 160, 220):
                    try:
                        fz = _floor_at(db, m, px + tx * dist, py + ty * dist, bottom)
                        if fz is not None and roofed and not _roofed(db, m, px + tx * dist, py + ty * dist, fz):
                            fz = None
                    except Exception:
                        fz = None
                    if fz is not None:
                        ux, uy, z = tx, ty, fz + 12
                        x, y = px + ux * dist, py + uy * dist
                        yaw = math.atan2(ux, uy) % (2 * math.pi)
                        return [round(x, 1), round(y, 1), round(z, 1), 0.0, 0.0, round(yaw, 4)]
    x, y = px + ux * 110, py + uy * 110
    yaw = math.atan2(ux, uy) % (2 * math.pi)           # the game measures turns clockwise from north
    return [round(x, 1), round(y, 1), round(z, 1), 0.0, 0.0, round(yaw, 4)]


def _leads_to(db, link, source_key):
    if not link:
        return False
    if source_key.startswith('#'):
        if link['cell']:
            return False
        gx, gy = (int(v) for v in source_key[1:].split(','))
        return abs(math.floor(link['x'] / CELL) - gx) <= 1 and abs(math.floor(link['y'] / CELL) - gy) <= 1
    return link['cell'].lower() == source_key


def arrival(db, target, source_key=None, near=None):
    """Where to arrive in a place: in front of its door back to where you came from, else in front of
    any door that leads out, else in the middle of things. Returns (pos6, back door ref or None)."""
    m = mapdata.cellmap(db, target)
    if not m.get('exists'):
        raise EditError('That place does not exist.')
    doors = [r for r in m['refs'] if r['type'] == 'DOOR']
    back = None
    if source_key:
        backs = [r for r in doors if _leads_to(db, r.get('to'), source_key)]
        if backs:
            if near:
                backs.sort(key=lambda r: math.hypot(r['p'][0] - near[0], r['p'][1] - near[1]))
            back = backs[0]
            if not near:
                return _in_front(m, back, db), back
    if near:
        # (a spot that was clicked is where you arrive, even with a door back there: that door still leads back)
        x, y = float(near[0]), float(near[1])
        rz = near[3] if len(near) > 3 else None
        if len(near) > 4 and near[4] and near[2] is not None:
            # (typed, or where the player stands in game: exactly that, nothing moved)
            arrival.moved = False
            return [x, y, float(near[2]), 0, 0, float(rz or 0.0)], back
        if len(near) > 2 and near[2] is not None:
            top = near[2] + 60.0                       # (clicked in 3D: the floor there)
        else:
            d = min(doors, key=lambda r: math.hypot(r['p'][0] - x, r['p'][1] - y), default=None)
            top = d['p'][2] + 150.0 if d else None     # (on the map: the floor of the nearest door's storey)
        got = stand_spot(db, m, x, y, top, rz) if top is not None else None
        if got:
            (x, y, z, rz), moved = got
        else:
            z = near[2] if len(near) > 2 and near[2] is not None else mapdata.surface_z(db, m['refs'], m['interior'], x, y, None, 1.0, 'NPC_', None) + 10
            rz, moved = rz or 0.0, False
        arrival.moved = moved
        return [x, y, z, 0, 0, float(rz)], back
    linked = [r for r in doors if r.get('to')]
    if linked:
        return _in_front(m, linked[0], db), None
    if m['interior'] and doors:
        # no way out yet: just inside its door
        load_like = [r for r in doors if 'load' in r['id'].lower()] or doors
        return _in_front(m, load_like[0], db), load_like[0]
    if m['interior']:
        refs = m['refs'] or [{'p': [0, 0, 0]}]
        x = sorted(r['p'][0] for r in refs)[len(refs) // 2]
        y = sorted(r['p'][1] for r in refs)[len(refs) // 2]
    else:
        x, y = (m['gx'] + 0.5) * CELL, (m['gy'] + 0.5) * CELL
    z = mapdata.surface_z(db, m['refs'], m['interior'], x, y, None, 1.0, 'NPC_', None) + 10
    return [x, y, z, 0, 0, 0.0], None


def _set_link(subs, dest_name, pos):
    """Door subrecords with the destination replaced (or removed when pos is None)."""
    subs = [(t, bytes(d)) for t, d in subs if t not in ('DODT', 'DNAM')]
    if pos is None:
        return subs
    extra = [('DODT', struct.pack('<6f', *[float(v) for v in pos[:6]]))]
    if dest_name:
        extra.append(('DNAM', zs(dest_name)))
    out, put = [], False
    for t, d in subs:
        if t == 'DATA' and not put:
            out += extra
            put = True
        out.append((t, d))
    if not put:
        out += extra
    return out


# (the user, 2026-11-02, after a town door landed them upstairs behind a locked door, "ive requested this many times":
# a door puts you right at the face of the door it pairs with, and that one puts you at the face of this one; never
# a spot the game's copied house had, never the middle of a place)
FACE_OFF = 128                 # (an arrival further than this from the face of the door that leads back is not at it)
FACE_DROP = 64                 # (or this far over or under it: another storey)
NOT_FACED = re.compile(r'trap|ladder|hatch|grate', re.I)    # (joined storey to storey as the game joins them)


def partner(db, ck, door):
    """The door at the other end of a door's link: the one in the place it leads to that leads back here, nearest to
    where this door stands. (cell key, ref) or None."""
    to = door.get('to')
    if not to:
        return None
    if to.get('cell'):
        keys = [to['key']]
    else:
        gx, gy = math.floor(to['x'] / CELL), math.floor(to['y'] / CELL)
        keys = ['#%d,%d' % (gx + i, gy + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]
    best = None
    for k in keys:
        try:
            refs = mapdata.cellmap(db, k).get('refs') or ()
        except Exception:
            continue
        for r in refs:
            if r['type'] != 'DOOR' or r is door or not _leads_to(db, r.get('to'), ck):
                continue
            # (both ways: its arrival by this door and this one's by it; two doors of one tower room out onto the walk
            # took each other's partner by the first alone)
            d = math.hypot(r['to']['x'] - door['p'][0], r['to']['y'] - door['p'][1])
            d2 = math.hypot(to['x'] - r['p'][0], to['y'] - r['p'][1]) + abs(to['z'] - r['p'][2]) * 0.5
            if d < 800 and (best is None or d + d2 < best[0]):
                d += d2
                best = (d, k, r)
    return (best[1], best[2]) if best else None


def misplaced_arrivals(db, cells=None, made_only=True):
    """The doors (the mod's own, in these cells or all) whose arrival isn't at the face of the door that leads back:
    [(cell key, ref key, door id, destination name, arrival now, arrival at the face)]."""
    out = []
    for ck in (cells if cells is not None else list(db.project.cells)):
        try:
            refs = mapdata.cellmap(db, ck).get('refs') or ()
        except Exception:
            continue
        for r in refs:
            if r['type'] != 'DOOR' or not r.get('to') or (made_only and not r.get('new')) or NOT_FACED.search(r['id']):
                continue
            if r['to']['key'] == ck:
                continue                     # (a door into its own place: storeys joined as the game joined them)
            pr = partner(db, ck, r)
            if pr is None or NOT_FACED.search(pr[1]['id']):
                continue
            pk, pd = pr
            back = partner(db, pk, pd)
            if back is None or back[1]['k'] != r['k'] or back[0] != ck:
                continue                     # (not each other's: two doors onto one spot, left for a person to pick)
            want = _in_front(mapdata.cellmap(db, pk), pd, db)
            to = r['to']
            if math.hypot(want[0] - to['x'], want[1] - to['y']) > FACE_OFF or abs(want[2] - to['z']) > FACE_DROP:
                out.append((ck, r['k'], r['id'], to.get('cell') or '', [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']], want))
    return out


def face_arrivals(db, cells=None, commit=True, follow=True):
    """Every misplaced arrival (misplaced_arrivals) set at the face of its door's partner, facing away from it. With
    follow, the places these cells' doors lead into are gone through too (a town's interiors and the rooms past
    them). The number set."""
    if cells is not None and follow:
        seen, todo = set(), list(cells)
        while todo:
            ck = todo.pop()
            if ck in seen:
                continue
            seen.add(ck)
            try:
                refs = mapdata.cellmap(db, ck).get('refs') or ()
            except Exception:
                continue
            for r in refs:
                if r['type'] == 'DOOR' and r.get('new') and (r.get('to') or {}).get('cell') and len(seen) < 400:
                    todo.append(r['to']['key'])
        cells = sorted(seen)
    fix = misplaced_arrivals(db, cells)
    for ck, rk, _id, dest, _now, want in fix:
        c_, refs = editing._cell(db, ck)
        ref = refs.get(rk)
        if ref is not None:
            editing._store(c_, rk, ref['origin'], ref['idx'], _set_link(ref['subs'], dest, want))
    if fix and commit:
        editing.commit(db, 'Set %d door arrivals at the face of their doors' % len(fix))
    elif fix:
        db.sync_project()
    return len(fix)


def link_pair(db, cell_a, ref_a, cell_b, ref_b):
    """Two picked doors lead to each other, each arriving in front of the other (one picked in each of two
    windows, web/twowin.js), as one change."""
    editing._require_project(db)
    if cell_a == cell_b and ref_a == ref_b:
        raise EditError('Pick two different doors.')
    ends = []
    for ck, rk in ((cell_a, ref_a), (cell_b, ref_b)):
        c, refs = editing._cell(db, ck)
        ref = refs.get(rk)
        if not ref:
            raise EditError('That door is no longer here.')
        rid = ref_info(ref['subs'])[0]
        ri = db.resolve_id(rid)
        if ri is None or db.recs[ri][0] != 'DOOR':
            raise EditError('"%s" is not a door.' % rid)
        m = mapdata.cellmap(db, ck)
        here = next((r for r in m['refs'] if r['k'] == rk), None)
        if not here:
            raise EditError('That door is no longer here.')
        ends.append({'cell': ck, 'k': rk, 'c': c, 'ref': ref, 'id': rid, 'here': here, 'map': m,
                     'info': mapdata.cell_info(db, ck)})
    for me, other in ((ends[0], ends[1]), (ends[1], ends[0])):
        pos = _in_front(other['map'], other['here'], db)
        name = other['info']['name'] if other['info']['interior'] else ''
        ref = me['ref']
        editing._store(me['c'], me['k'], ref['origin'], ref['idx'], _set_link(ref['subs'], name, pos))
    a, b = ends
    editing.commit(db, 'Doors "%s" in %s and "%s" in %s now lead to each other' % (
        a['id'], editing.cell_label(db, a['cell']), b['id'], editing.cell_label(db, b['cell'])))
    return {'ok': True, 'cells': sorted({a['cell'], b['cell']})}


def relink(db, cell_key, refkey, target=None, at=None, both_ways=False):
    """Make a door lead to `target` (a cell key), arriving at `at` ([x, y, z, rz] or None to choose).
    target None removes the link. both_ways also points the door at the other end back here."""
    editing._require_project(db)
    c, refs = editing._cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That door is no longer here.')
    rid = ref_info(ref['subs'])[0]
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] != 'DOOR':
        raise EditError('Only doors can lead somewhere.')
    if not target:
        editing._store(c, refkey, ref['origin'], ref['idx'], _set_link(ref['subs'], None, None))
        editing.commit(db, 'Door "%s" in %s no longer leads anywhere' % (rid, editing.cell_label(db, cell_key)))
        return {'ok': True}
    info = mapdata.cell_info(db, target)
    if not info:
        raise EditError('There is no place called "%s".' % target)
    # (a door to elsewhere in its own place, as the game's towers, manors and tombs have: the spot is picked)
    same = target == cell_key
    if same and not at:
        raise EditError('Pick where you arrive in this place: click the spot.')
    here = next((r for r in mapdata.cellmap(db, cell_key)['refs'] if r['k'] == refkey), None)
    near = None
    if at:
        near = [float(at[0]), float(at[1]), None if len(at) < 3 or at[2] is None else float(at[2]),
                float(at[3]) if len(at) > 3 and at[3] is not None else None, bool(len(at) > 4 and at[4])]
    arrival.moved = False
    pos, back = arrival(db, target, None if same else cell_key, near)
    dest_name = info['name'] if info['interior'] else ''
    editing._store(c, refkey, ref['origin'], ref['idx'], _set_link(ref['subs'], dest_name, pos))
    note = 'Door "%s" in %s now leads to %s' % (rid, editing.cell_label(db, cell_key), info['name'] or info['id'])
    back_done = None
    if both_ways and here and not back:
        # the door at the other end: the closest door to where you arrive that leads nowhere yet. (A door that
        # already leads here keeps its own arrival: picking this door's spot reset the one picked for that door
        # a minute before, and the other way, and people's arrivals seemed to come out at random, 2026-11-02.)
        m2 = mapdata.cellmap(db, target)
        cand = min((r for r in m2['refs'] if r['type'] == 'DOOR' and not r.get('to') and not (same and r['k'] == refkey)),
                   key=lambda r: math.hypot(r['p'][0] - pos[0], r['p'][1] - pos[1]), default=None)
        if cand and math.hypot(cand['p'][0] - pos[0], cand['p'][1] - pos[1]) < 600:
            c2, refs2 = editing._cell(db, target)
            r2 = refs2.get(cand['k'])
            if r2:
                src = mapdata.cell_info(db, cell_key)
                back_pos = _in_front(mapdata.cellmap(db, cell_key), here, db)
                editing._store(c2, cand['k'], r2['origin'], r2['idx'],
                               _set_link(r2['subs'], src['name'] if src['interior'] else '', back_pos))
                back_done = cand['id']
                note += ' (and back)'
    editing.commit(db, note)
    return {'ok': True, 'arrive': pos, 'back': back_done, 'moved': arrival.moved}
