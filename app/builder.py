"""Build a new interior from scratch out of a kit's modular pieces.

Rooms are rectangles on a grid of the kit's tile size (usually 256 units). Every tile gets
the floor piece whose walls match where the room ends; doorways between rooms get the kit's
door frame; the way out gets a load door, linked to a door outside if you give a spot."""
import math
import struct

import editing
import kits
import mapdata
from editing import EditError
from esm import ENC, iter_subrecords, zstr
from project import b64, join_subs, set_ref_pos, zs

STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
YAW = {'N': 0.0, 'E': math.pi / 2, 'S': math.pi, 'W': 3 * math.pi / 2}   # clockwise from north
LIGHTING = {   # ambient, sunlight, fog colour
    'dark': ((25, 22, 20), (40, 36, 30), (0, 0, 0)),
    'dim': ((45, 40, 35), (70, 62, 52), (0, 0, 0)),
    'normal': ((70, 64, 55), (105, 95, 80), (0, 0, 0)),
    'bright': ((110, 104, 95), (150, 140, 125), (0, 0, 0)),
}


def styles(db):
    """Kits you can build with, most used first."""
    if _styles.get('recs') is db.recs:
        return _styles['out']
    out = []
    for prefix, k in kits.kits(db).items():
        kp = kits.kit_pieces(db, prefix)
        if not kp or len(kp['pieces']) < 3:
            continue
        pats = {''.join(kits.rotate(p['pattern'], q)[s][0].upper() for s in kits.SIDES) for p in kp['pieces'] for q in range(4)}
        # it must at least do a plain floor, a side and a corner
        if not ({'OOOO'} <= pats and any(p.count('W') == 1 for p in pats) and any(p in pats for p in ('WWOO', 'OWWO', 'OOWW', 'WOOW'))):
            continue
        small = bool(kp['walls']) or any(p.count('W') >= 3 for p in pats)
        st = kits.stairs(db, prefix)
        out.append({'id': prefix, 'name': kits.friendly(prefix), 'tile': kp['tile'], 'pieces': len(kp['pieces']),
                    'doorways': bool(kp['jambs']), 'small_rooms': small, 'uses': k['uses'], 'floors': bool(st)})
    out.sort(key=lambda s: -s['uses'])
    _styles.update({'recs': db.recs, 'out': out})
    return out


_styles = {}


def _pick(kp, need):
    """Best piece and turn for a tile: (piece, quarter turns, sides still needing a wall)."""
    best = None
    for p in kp['pieces']:
        for q in range(4):
            pat = kits.rotate(p['pattern'], q)
            # passable where people walk through (an archway will do, a plain opening is better), a doorway
            # exactly where one is wanted, and never a hole in a wall
            if any((need[s] == 'open' and pat[s] == 'wall') or (need[s] == 'door' and pat[s] != 'door') or
                   (need[s] == 'wall' and pat[s] == 'door') for s in kits.SIDES):
                continue
            missing = [s for s in kits.SIDES if need[s] == 'wall' and pat[s] != 'wall']
            clutter = sum(pat['cover'].get(s, 0) + (1 if pat[s] == 'door' else 0) for s in kits.SIDES if need[s] == 'open')
            # pieces no real interior uses are often unfinished or special: only as a last resort
            score = (len(missing), p['uses'] == 0, round(clutter, 1), -p['uses'])
            if best is None or score < best[0]:
                best = (score, p, q, missing, pat)
    if best is None:
        return None, 0, list(kits.SIDES), None
    return best[1], best[2], best[3], best[4]


def _pick_fit(kp, need, side, fits):
    """Like _pick, but only pieces whose doorway on `side` the game itself fills with a door (so the
    door that goes there is known to fit). None if there is no such piece for this spot."""
    best = None
    for p in kp['pieces']:
        for q in range(4):
            pat = kits.rotate(p['pattern'], q)
            if any((need[s] == 'open' and pat[s] == 'wall') or (need[s] == 'door' and pat[s] != 'door') or
                   (need[s] == 'wall' and pat[s] == 'door') for s in kits.SIDES):
                continue
            local = kits.SIDES[(kits.SIDES.index(side) - q) % 4]
            fit = fits.get((p['id'], local))
            if not fit or not fit.get('plain', True):
                continue
            missing = [s for s in kits.SIDES if need[s] == 'wall' and pat[s] != 'wall']
            score = (len(missing), not fit.get('plain', True), not fit['load'], -fit['uses'], -p['uses'])
            if best is None or score < best[0]:
                best = (score, p, q, missing, pat, fit)
    return best[1:] if best else None


def _front(db, ri):
    """Which way a flat model (a door panel, a frame) faces, in its own coordinates: (x, y) or None
    when it looks the same from both sides."""
    shapes = kits._model(db, ri)
    if not shapes:
        return None
    sx = sy = total = 0.0
    for s in shapes:
        p, idx = s['p'], s['i']
        if s.get('double'):
            return None
        for t in range(0, len(idx) - 2, 3):
            a, b, c = idx[t] * 3, idx[t + 1] * 3, idx[t + 2] * 3
            ux, uy, uz = p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2]
            vx, vy, vz = p[c] - p[a], p[c + 1] - p[a + 1], p[c + 2] - p[a + 2]
            nx, ny = uy * vz - uz * vy, uz * vx - ux * vz
            sx += nx
            sy += ny
            total += math.hypot(nx, ny)
    if total <= 0 or math.hypot(sx, sy) < total * 0.35:
        return None
    return (sx, sy)


def _facing(db, ri, inward, default):
    """A turn (radians) that makes a flat model face the given direction, or the default."""
    f = _front(db, ri)
    if not f:
        return default
    best, bd = default, -2
    for q in range(4):
        th = q * math.pi / 2                      # the game turns clockwise
        wx, wy = f[0] * math.cos(th) + f[1] * math.sin(th), -f[0] * math.sin(th) + f[1] * math.cos(th)
        d = (wx * inward[0] + wy * inward[1]) / (math.hypot(wx, wy) or 1)
        if d > bd:
            best, bd = th, d
    return best


def _centred(db, ri, x, y, rot, scale=1.0):
    """Where to put a model's origin so the middle of the model (not its origin, which for many
    doors is the hinge or somewhere else entirely) lands on (x, y) after turning it by rot."""
    b = mapdata.object_bounds(db, ri)
    if not b:
        return x, y
    cx, cy = (b[0] + b[3]) / 2 * scale, (b[1] + b[4]) / 2 * scale
    wx, wy = cx * math.cos(rot) + cy * math.sin(rot), -cx * math.sin(rot) + cy * math.cos(rot)
    return x - wx, y - wy


def _co_used(db, kp, tag, want=None):
    """Objects of a type that are used most in the same places as this kit."""
    cells = set()
    for p in kp['pieces'][:6]:
        cells |= set(db.used_in.get(p['id'].lower(), ()))
    counts = {}
    for (t, key), lst in db.by_key.items():
        if t != tag or not lst or lst[-1] in db.dead:
            continue
        if want and not want(key):
            continue
        n = len(cells & set(db.used_in.get(key, ())))
        if n:
            counts[db.recs[lst[-1]][1]] = n
    return sorted(counts, key=lambda k: -counts[k])


FLOOR_NAMES = {-2: 'lower cellar', -1: 'cellar', 0: 'ground floor', 1: 'upstairs', 2: 'top floor'}


def nb(t, s, k=1):
    """The tile k steps from t towards side s, on the same floor."""
    return (t[0] + STEP[s][0] * k, t[1] + STEP[s][1] * k, t[2])


def side_of(dx, dy):
    return next(s for s, v in STEP.items() if v == (dx, dy))


def _grid(rooms):
    """Tiles (x, y, floor) -> room number, and the rooms' names (lower case)."""
    grid, names = {}, []
    for n, r in enumerate(rooms):
        rn = (r.get('name') or 'room %d' % (n + 1)).strip()
        names.append(rn.lower())
        w, h, f = int(r.get('w', 1)), int(r.get('h', 1)), int(r.get('floor') or 0)
        if w < 1 or h < 1 or w * h > 200:
            raise EditError('Room "%s" has a strange size (%s x %s tiles).' % (rn, w, h))
        if not -2 <= f <= 2:
            raise EditError('Room "%s" is on floor %d; buildings can go two floors up and two down.' % (rn, f))
        for tx in range(int(r.get('x', 0)), int(r.get('x', 0)) + w):
            for ty in range(int(r.get('y', 0)), int(r.get('y', 0)) + h):
                if (tx, ty, f) in grid:
                    raise EditError('Rooms "%s" and "%s" overlap.' % (rooms[grid[(tx, ty, f)]].get('name'), rn))
                grid[(tx, ty, f)] = n
    if len(grid) > 400:
        raise EditError('That is too big for one go (over 400 tiles).')
    return grid, names


def _connected(tiles):
    tiles = set(tiles)
    if not tiles:
        return False
    todo, seen = [next(iter(tiles))], set()
    while todo:
        t = todo.pop()
        if t in seen:
            continue
        seen.add(t)
        todo += [nb(t, s) for s in STEP if nb(t, s) in tiles]
    return seen == tiles


def _place_stairs(db, style, kp, grid, rooms, wanted=None):
    """Join each floor to the one above with a staircase from the style's own stair pieces.
    Changes grid in place (a landing tile may be added to a room, or a tile given up for the
    stairwell). Returns [{'piece', 'tiles': [(x, y, floor)], 'up': side, 'q', 'z'...}] and notes."""
    floors = sorted({t[2] for t in grid})
    if len(floors) < 2:
        return [], []
    info = kits.stairs(db, style)
    if not info:
        raise EditError('The %s style has no stair pieces, so it can only make one floor. Try Hlaalu, or put '
                        'every room on the same floor.' % kits.friendly(style))
    H = info['storey']
    for f in range(floors[0], floors[-1]):
        if f not in floors or f + 1 not in floors:
            raise EditError('There is a floor with no rooms between the %s and the %s.' % (
                FLOOR_NAMES.get(floors[0]), FLOOR_NAMES.get(floors[-1])))
    placed, notes, used = [], [], set()
    for f in floors[:-1]:
        g = f + 1
        want = (wanted or {}).get(f) or {}
        xs = [t[0] for t in grid]
        ys = [t[1] for t in grid]
        best = None
        for piece in info['pieces']:
            n = int(round(H / piece['rise']))
            if n < 1 or n > 2 or (piece['open'] and n > 1):
                continue
            for up in kits.SIDES:
                down = OPPOSITE[up]
                for bx in range(min(xs) - n - 2, max(xs) + n + 3):
                    for by in range(min(ys) - n - 2, max(ys) + n + 3):
                        st = [nb((bx, by, f), up, i) for i in range(n)]
                        cost = 0
                        carve = []
                        ok = True
                        for s in st:
                            if (s[0], s[1]) in used:
                                ok = False
                                break
                            for lv in (f, g):
                                tt = (s[0], s[1], lv)
                                if tt in grid:
                                    carve.append(tt)
                        if not ok:
                            continue
                        lo, hi = nb(st[0], down), nb((st[-1][0], st[-1][1], g), up)
                        if (lo[0], lo[1]) in used or (hi[0], hi[1]) in used:
                            continue
                        land = []
                        for t, lv in ((lo, f), (hi, g)):
                            if t in grid and t not in carve:
                                continue
                            # a landing tile joined to a room beside it
                            beside = [nb(t, s) for s in STEP if nb(t, s) in grid and nb(t, s) not in carve and
                                      (nb(t, s)[0], nb(t, s)[1]) not in {(x[0], x[1]) for x in st}]
                            if not beside:
                                ok = False
                                break
                            land.append((t, grid[beside[0]]))
                        if not ok:
                            continue
                        # sides of the stair that open into the room beside it need that room on both floors
                        rot_open = []
                        if piece['open']:
                            q = (kits.SIDES.index(down) - kits.SIDES.index(piece['low'])) % 4
                            for o in piece['open']:
                                ws = kits.SIDES[(kits.SIDES.index(o) + q) % 4]
                                for lv in (f, g):
                                    t = nb((st[0][0], st[0][1], lv), ws)
                                    if t not in grid or t in carve:
                                        ok = False
                                rot_open.append(ws)
                        if not ok:
                            continue
                        # giving up tiles: never all of a room, and the room must stay in one piece
                        for c in carve:
                            left = [t for t, r in grid.items() if r == grid[c] and t not in carve]
                            if len(left) < 2 or not _connected(left):
                                ok = False
                                break
                        if not ok:
                            continue
                        rooms_lo = grid[lo] if lo in grid and lo not in carve else land[0][1]
                        rooms_hi = grid[hi] if hi in grid and hi not in carve else land[-1][1]
                        # stairs open on one side leave a gap where they meet the next wall: a last resort
                        cost = len(carve) * 3 + len(land) * 2 + ((3 if piece['post'] else 10) if piece['open'] else 0)
                        if want.get('from') is not None and rooms_lo != want['from']:
                            cost += 6
                        if want.get('to') is not None and rooms_hi != want['to']:
                            cost += 6
                        # near the middle of the building rather than off in a corner
                        cost += 0.01 * (abs(bx - (min(xs) + max(xs)) / 2) + abs(by - (min(ys) + max(ys)) / 2))
                        cost += info['pieces'].index(piece) * 0.2
                        if best is None or cost < best[0]:
                            best = (cost, piece, up, st, lo, hi, carve, land, rot_open)
        if not best:
            raise EditError('Could not find room for stairs between the %s and the %s. Make the rooms on both '
                            'floors a little bigger (3 tiles deep is enough).' % (FLOOR_NAMES.get(f), FLOOR_NAMES.get(g)))
        cost, piece, up, st, lo, hi, carve, land, rot_open = best
        for c in carve:
            del grid[c]
        for t, r in land:
            grid[t] = r
        q = (kits.SIDES.index(OPPOSITE[up]) - kits.SIDES.index(piece['low'])) % 4
        for s in st:
            used.add((s[0], s[1]))
        used.add((lo[0], lo[1]))
        used.add((hi[0], hi[1]))
        placed.append({'piece': piece, 'tiles': st, 'up': up, 'q': q, 'floor': f, 'lo': lo, 'hi': hi,
                       'open': rot_open, 'storey': H})
        if land:
            notes.append('The stairs from the %s needed %s.' % (FLOOR_NAMES.get(f), 'a small landing' if len(land) == 1 else 'two small landings'))
    return placed, notes


def plan(db, style, rooms):
    """Where everything would go, without building it: tiles per floor and the stairs."""
    kp = kits.kit_pieces(db, style)
    if not kp or not kp['pieces']:
        raise EditError('Unknown building style "%s".' % style)
    grid, _names = _grid(rooms)
    stairs, notes = _place_stairs(db, style, kp, grid, rooms)
    return {'tiles': [[t[0], t[1], t[2], r] for t, r in sorted(grid.items())],
            'stairs': [{'tiles': [[s[0], s[1], s[2]] for s in x['tiles']], 'up': x['up'], 'floor': x['floor']} for x in stairs],
            'notes': notes}


def build_interior(db, name, style, rooms, doors=None, exit=None, entrance=None, lighting='normal',
                   lights=True, outside_door=None, stairs=None):
    """rooms: [{'name', 'x', 'y', 'w', 'h', 'floor'}] in tiles (x east, y north, floor 0 = ground,
    1 = upstairs, -1 = cellar). doors: [{'rooms': [a, b]}] on the same floor. stairs: optional
    [{'rooms': [lower room, upper room]}]; floors are joined by stairs anyway.
    exit: {'room': a, 'side': 'N'|'E'|'S'|'W'}. entrance: {cell, x, y, z, rz} outside, or None."""
    editing._require_project(db)
    p = db.project
    name = (name or '').strip()
    if not name:
        raise EditError('Give the new place a name, e.g. "Balmora, Fenas\' House".')
    if len(name.encode(ENC, 'replace')) > 63:
        raise EditError('Place names can be at most 63 characters.')
    key = name.lower()
    if any(v not in db.dead for v in db.by_key.get(('CELL', key), [])) or key in p.cells:
        raise EditError('There is already a place called "%s".' % name)
    kp = kits.kit_pieces(db, style)
    if not kp or not kp['pieces']:
        raise EditError('Unknown building style "%s". Pick one from the list of styles.' % style)
    T = kp['tile']
    if not rooms:
        raise EditError('Describe at least one room.')
    # ---- the grid
    grid, names = _grid(rooms)

    def room_index(ref):
        if isinstance(ref, int):
            return ref
        s = str(ref).strip().lower()
        if s in names:
            return names.index(s)
        raise EditError('There is no room called "%s".' % ref)

    wanted = {}
    for s in stairs or []:
        a, b = room_index(s['rooms'][0]), room_index(s['rooms'][1])
        fa, fb = int(rooms[a].get('floor') or 0), int(rooms[b].get('floor') or 0)
        if abs(fa - fb) != 1:
            raise EditError('Stairs join a room to one on the floor just above or below it.')
        if fa > fb:
            a, b, fa = b, a, fb
        wanted[fa] = {'from': a, 'to': b}
    stair_list, stair_notes = _place_stairs(db, style, kp, grid, rooms, wanted)
    H = stair_list[0]['storey'] if stair_list else 256

    def boundary(a, b):
        """Edges between two rooms: [(tile, side)] with the tile in room a."""
        return [(t, s) for t, ra in grid.items() if ra == a for s in STEP if grid.get(nb(t, s)) == b]

    # ---- what each tile needs on each side: open within a room, a wall at its edge
    need = {}
    for t, ra in grid.items():
        need[t] = {s: 'open' if grid.get(nb(t, s)) == ra else 'wall' for s in STEP}
    # ... and open towards the ends of a staircase (and its open sides)
    for x in stair_list:
        need[x['lo']][x['up']] = 'open'
        need[x['hi']][OPPOSITE[x['up']]] = 'open'
        for ws in x['open']:
            for lv in (x['floor'], x['floor'] + 1):
                need[nb((x['tiles'][0][0], x['tiles'][0][1], lv), ws)][OPPOSITE[ws]] = 'open'

    def fits(t):
        return _pick(kp, need[t])[0] is not None

    load_jamb = next((j for j in kp['jambs'] if j.get('load') and j['width'] >= T * 0.9), None)
    full_jamb = next((j for j in kp['jambs'] if not j.get('load') and j['width'] >= T * 0.9), None) or load_jamb
    small_jamb = next((j for j in kp['jambs'] if j['width'] < T * 0.9), None)
    frame_style = kp['frame_doors'] or not kp['entry_doors']
    frames = []          # (tile, side) where a full-width door frame goes between two tiles
    gaps = []            # doorways that could only be left as open gaps
    # ---- doorways between rooms
    for d in doors or []:
        a, b = room_index(d['rooms'][0]), room_index(d['rooms'][1])
        e = boundary(a, b)
        if not e:
            raise EditError('Rooms "%s" and "%s" don\'t touch, so there is no wall to put a door in.' % (rooms[a].get('name'), rooms[b].get('name')))
        # try the middle of the shared wall first, then spots around it
        e = sorted(e)
        order = sorted(range(len(e)), key=lambda i: abs(i - len(e) // 2))
        done = False
        for i in order:
            t, s = e[i]
            n2 = nb(t, s)
            o = OPPOSITE[s]
            saved = (need[t][s], need[n2][o])
            if frame_style:
                # Hlaalu-like: both tiles open, a full-width frame between them
                need[t][s], need[n2][o] = 'open', 'open'
                if fits(t) and fits(n2):
                    frames.append((t, s))
                    done = True
            else:
                # these styles build every wall twice, back to back (one inside each tile), so a doorway
                # needs an opening in both walls to line up; failing that, one opening and an open side
                for a_need, b_need in (('door', 'door'), ('door', 'open'), ('open', 'door')):
                    need[t][s], need[n2][o] = a_need, b_need
                    if fits(t) and fits(n2):
                        done = True
                        break
                    need[t][s], need[n2][o] = saved
            if done:
                break
            need[t][s], need[n2][o] = saved
        if not done:
            t, s = e[len(e) // 2]
            n2 = nb(t, s)
            need[t][s], need[n2][OPPOSITE[s]] = 'open', 'open'
            gaps.append((rooms[a].get('name'), rooms[b].get('name')))
    # ---- the way out
    ex = exit or {}
    er = room_index(ex.get('room', 0))
    eside = (ex.get('side') or 'S').upper()[:1]
    stair_xy = {(s[0], s[1]) for x in stair_list for s in x['tiles']}
    free = lambda t, s: nb(t, s) not in grid and nb(t, s)[:2] not in stair_xy and need[t][s] == 'wall'
    outer = sorted((t, eside) for t, ra in grid.items() if ra == er and free(t, eside))
    if not outer:
        outer = sorted((t, s) for t, ra in grid.items() if ra == er for s in kits.SIDES if free(t, s))
    if not outer:
        raise EditError('Room "%s" has no outside wall left for the way out.' % rooms[er].get('name'))
    exit_how = 'wall'            # 'frame' (full frame + door), 'entry' (door in a doorway piece), 'wall' (door on a wall)
    exit_tile, exit_side = outer[len(outer) // 2]
    for i in sorted(range(len(outer)), key=lambda i: abs(i - len(outer) // 2)):
        t, s = outer[i]
        if frame_style and load_jamb:
            need[t][s] = 'open'
            if fits(t):
                exit_tile, exit_side, exit_how = t, s, 'frame'
                break
        elif kp['entry_doors']:
            need[t][s] = 'door'
            if fits(t):
                exit_tile, exit_side, exit_how = t, s, 'entry'
                break
        need[t][s] = 'wall'
        if not (frame_style and load_jamb) and not kp['entry_doors']:
            break
    plain_jamb = full_jamb

    refs = []        # (id, (x, y, z, rx, ry, rz), extra subrecords[, scale])
    z0 = -kp['zmin']         # floors at height 0
    door_at = {}             # (tile, side) -> how far from the tile's centre that side's doorway stands
    tile_piece = {}          # tile -> (piece, quarter turns)

    def centre(t):
        return t[0] * T, t[1] * T

    def zf(t):
        return t[2] * H                          # how high this tile's floor is

    # ---- stairs between floors
    for x in stair_list:
        sp = x['piece']
        for i, s in enumerate(x['tiles']):
            sx_, sy_ = centre(s)
            sz = z0 + zf(s) - sp['z_low'] + i * sp['rise']
            refs.append((sp['id'], (sx_, sy_, sz, 0, 0, x['q'] * math.pi / 2), []))
            # posts where an open side meets the walls beside it, on both floors (as the game does)
            if sp['post'] and x['open']:
                for ws in x['open']:
                    ax, ay = STEP[ws]
                    bx, by = STEP[x['up']]
                    for along in (-1, 1):
                        for lv in (s[2], s[2] + 1):
                            refs.append((sp['post'], (sx_ + (ax + bx * along) * T / 2, sy_ + (ay + by * along) * T / 2,
                                                      z0 + lv * H, 0, 0, 0), []))
    # ---- floor tiles
    exit_fit = None
    for t, ra in sorted(grid.items()):
        piece, q, missing, pat = _pick(kp, need[t])
        if t == exit_tile and exit_how == 'entry':
            # the way out: a doorway piece the game itself puts a door in, and that same door
            got = _pick_fit(kp, need[t], exit_side, kits.door_fits(db, style))
            if got and (len(got[2]) <= len(missing) or kp['walls']):
                piece, q, missing, pat, exit_fit = got
        tile_piece[t] = (piece, q)
        if piece is None:
            raise EditError('The %s style has no floor piece that fits a spot in room "%s". Try a different style, '
                            'or simpler room shapes.' % (kits.friendly(style), rooms[ra].get('name') or ra + 1))
        for s in kits.SIDES:
            if pat[s] == 'door':
                door_at[(t, s)] = pat['offset'].get(s, T / 2 - 16)
        cx, cy = centre(t)
        if missing and not kp['walls']:
            raise EditError('The %s style has no piece for a spot with walls on %d sides (in room "%s"), and no loose '
                            'wall pieces to close it off. In this style, make rooms and corridors at least 2 tiles '
                            'wide, and let corridors end in a room.' % (kits.friendly(style), list(need[t].values()).count('wall'),
                                                                         rooms[ra].get('name') or ra + 1))
        refs.append((piece['id'], (cx, cy, z0 + zf(t), 0, 0, q * math.pi / 2), []))
        # walls the piece doesn't have
        for s in missing:
            wall = kp['walls'][0]
            off = T / 2 - wall['thick'] / 2 - 2
            wx, wy = cx + STEP[s][0] * off, cy + STEP[s][1] * off
            along_y = s in 'EW'                       # an east/west wall runs north-south
            rot = 0 if along_y == wall['thin_x'] else math.pi / 2
            refs.append((wall['id'], (wx, wy, -wall['zmin'] + zf(t), 0, 0, rot), []))
    # ---- full-width door frames between rooms (styles that build doorways that way)
    for t, s in frames:
        if not plain_jamb:
            continue
        cx, cy = centre(t)
        mx, my = cx + STEP[s][0] * T / 2, cy + STEP[s][1] * T / 2
        along_y = s in 'EW'
        rot = 0 if along_y == plain_jamb['thin_x'] else math.pi / 2
        mx, my = _centred(db, plain_jamb['ri'], mx, my, rot)
        refs.append((plain_jamb['id'], (mx, my, -plain_jamb['zmin'] + zf(t), 0, 0, rot), []))
    # ---- the way out: a door frame and a door, or a door against the wall
    cx, cy = centre(exit_tile)
    sx, sy = STEP[exit_side]
    door_id = None
    doors_here = _co_used(db, kp, 'DOOR', lambda k: 'load' in k or 'door' in k)
    door_id = doors_here[0] if doors_here else 'in_hlaalu_loaddoor_01'
    db_door = db.resolve_id(door_id)
    if db_door is None:
        raise EditError('Could not find a door to use for the way out.')
    db_door_b = mapdata.object_bounds(db, db_door) or [-5, -64, -100, 5, 64, 100]
    door_thin_x = (db_door_b[3] - db_door_b[0]) < (db_door_b[4] - db_door_b[1])
    along_y = exit_side in 'EW'
    jamb_scale = door_scale = 1.0
    if exit_how == 'frame':
        jx, jy = cx + sx * T / 2, cy + sy * T / 2
        rot = 0 if along_y == load_jamb['thin_x'] else math.pi / 2
        px, py = _centred(db, load_jamb['ri'], jx, jy, rot)
        refs.append((load_jamb['id'], (px, py, -load_jamb['zmin'] + zf(exit_tile), 0, 0, rot), []))
        dx, dy = jx, jy
    elif exit_how == 'entry' and exit_fit:
        # exactly as the game does it in this doorway: the same door, size and frame
        piece, q = tile_piece[exit_tile]
        prz = q * math.pi / 2
        pz = z0 + zf(exit_tile)
        wxy = lambda lx, ly: (cx + lx * math.cos(prz) + ly * math.sin(prz), cy - lx * math.sin(prz) + ly * math.cos(prz))
        for eid, ex_, ey_, ez_, erz, esc in exit_fit['extra']:
            px, py = wxy(ex_, ey_)
            refs.append((eid, (px, py, pz + ez_, 0, 0, (prz + erz) % (2 * math.pi)), [], esc))
        door_id = exit_fit['door']
        db_door = db.resolve_id(door_id)
        dx, dy = wxy(exit_fit['x'], exit_fit['y'])
        door_scale = exit_fit['scale']
    elif exit_how == 'entry':
        # the door goes into the doorway of the floor piece's own wall, with a frame if the style has one
        off = door_at.get((exit_tile, exit_side), T / 2 - 16)
        dx, dy = cx + sx * off, cy + sy * off
        if small_jamb:
            rot = 0 if along_y == small_jamb['thin_x'] else math.pi / 2
            rot = _facing(db, small_jamb['ri'], (-sx, -sy), rot)      # its finished side into the room
            # make the frame cover the whole opening (arched openings are often taller than the frame)
            piece, q = tile_piece[exit_tile]
            local = kits.SIDES[(kits.SIDES.index(exit_side) - q) % 4]
            opening = kits.doorway(db, piece['ri'], local, T)
            frame = kits.frame_hole(db, small_jamb['ri'])
            if opening and frame:
                jamb_scale = max(1.0, min(1.35, max(opening[0] / frame[0], opening[1] / frame[1]) * 1.03))
                # and the door fills the frame's hole
                hole_w, hole_h = frame[2] * jamb_scale, frame[3] * jamb_scale
                dwid = max(db_door_b[3] - db_door_b[0], db_door_b[4] - db_door_b[1])
                dhei = db_door_b[5] - db_door_b[2]
                if dwid > 1 and dhei > 1:
                    door_scale = max(0.8, min(1.5, min(hole_w / dwid, hole_h / dhei) * 1.02))
            px, py = _centred(db, small_jamb['ri'], dx, dy, rot, jamb_scale)
            refs.append((small_jamb['id'], (px, py, -small_jamb['zmin'] * jamb_scale + zf(exit_tile), 0, 0, rot), [], jamb_scale))
    else:
        wall_in = T / 2 - 34
        dx, dy = cx + sx * wall_in, cy + sy * wall_in
    if exit_how == 'entry' and exit_fit:
        drot = (q * math.pi / 2 + exit_fit['rz']) % (2 * math.pi)
        dz = z0 + zf(exit_tile) + exit_fit['z']
    else:
        drot = 0 if along_y == door_thin_x else math.pi / 2
        drot = _facing(db, db_door, (-sx, -sy), drot)        # a one-sided door panel must face into the room
        dz = -db_door_b[2] * door_scale + zf(exit_tile)  # the door's bottom on the floor
    # where the player appears when coming in: a step inside, facing into the room
    arrive = (dx - sx * 110, dy - sy * 110, 20.0 + zf(exit_tile), 0, 0, (YAW[exit_side] + math.pi) % (2 * math.pi))
    door_extra = []
    out_spot = None
    shell_spot = None
    if entrance and entrance.get('cell') and entrance.get('building'):
        # a whole outside building in the style, standing on the spot, with its own front door
        import outside
        sh = next((s for s in outside.shells(db, style) if s['id'].lower() == str(entrance['building']).lower()), None)
        if not sh:
            raise EditError('"%s" is not one of the outside buildings for the %s style.' % (entrance['building'], kits.friendly(style)))
        spieces, sdoor, dpose, dscale, out_arrival, sdoors = outside.place(
            db, sh, entrance['cell'], float(entrance['x']), float(entrance['y']), float(entrance.get('facing') or 0))
        door_extra = [('DODT', struct.pack('<6f', *out_arrival))]
        cell_of = lambda x_, y_: '#%d,%d' % (math.floor(x_ / 8192), math.floor(y_ / 8192))
        out_spot = (cell_of(dpose[0], dpose[1]), sdoor, dpose, dscale)
        shell_spot = (out_spot[0], sh, [(cell_of(pp[0], pp[1]), pid, pp, ps) for pid, pp, ps in spieces],
                      [(cell_of(pp[0], pp[1]), pid, pp, ps) for pid, pp, ps in sdoors])
    elif entrance and entrance.get('cell'):
        import create
        ex_, ey_ = float(entrance['x']), float(entrance['y'])
        if entrance.get('z') is None:
            em = mapdata.cellmap(db, entrance['cell'])
            if not em.get('exists'):
                raise EditError('There is no place at the chosen entrance spot.')
            ez_ = mapdata.surface_z(db, em['refs'], em['interior'], ex_, ey_, None, 1.0, 'DOOR')
        else:
            ez_ = float(entrance['z'])
        erz = float(entrance.get('rz') or 0)
        if not outside_door:
            choices = create.outside_doors(db, None, None)
            outside_door = choices[0]['id'] if choices else 'ex_common_door_01'
        if db.resolve_id(outside_door) is None:
            raise EditError('"%s" is not a door.' % outside_door)
        ox, oy = create._rot2(0, -128, erz)
        out_arrival = (ex_ + ox, ey_ + oy, ez_ + 16, 0, 0, (erz + math.pi) % (2 * math.pi))
        info = mapdata.cell_info(db, entrance['cell'])
        door_extra = [('DODT', struct.pack('<6f', *out_arrival))]
        if info and info['interior']:
            door_extra.append(('DNAM', zs(info['name'])))
        out_spot = (entrance['cell'], outside_door, (ex_, ey_, ez_, 0, 0, erz))
    if exit_how == 'entry' and exit_fit:
        pdx, pdy = dx, dy                                            # where the game puts it, exactly
    else:
        pdx, pdy = _centred(db, db_door, dx, dy, drot, door_scale)  # the door panel itself in the opening
    refs.append((door_id, (pdx, pdy, dz, 0, 0, drot), door_extra, door_scale))
    # ---- some light to see by
    if lights:
        # a hanging lantern of the kind used in places like this, from the ceiling
        # (not sconces: those belong on a wall, and Auto-furnish puts them there)
        hanging = _co_used(db, kp, 'LIGH', lambda k: any(w in k for w in ('lantern', 'chandelier', 'hang')) and 'sconce' not in k)
        lamp = hanging[0] if hanging else None
        lb = mapdata.object_bounds(db, db.resolve_id(lamp)) if lamp else None
        if lamp and lb:
            for n, r in enumerate(rooms):
                tiles = sorted(t for t, ra in grid.items() if ra == n)
                count = max(1, round(len(tiles) / 6.0))
                for k in range(count):
                    t = tiles[(k * len(tiles)) // count + len(tiles) // (2 * count)]
                    cxx, cyy = centre(t)
                    hz = kp['height'] - lb[5] - 6 + zf(t)    # its top just under the ceiling
                    refs.append((lamp, (cxx, cyy, hz, 0, 0, 0), []))
    # ---- write the new place
    amb, sun, fog = LIGHTING.get(lighting, LIGHTING['normal'])
    rgb = lambda c: c[0] | (c[1] << 8) | (c[2] << 16)
    header = [['NAME', b64(zs(name))], ['DATA', b64(struct.pack('<Iii', 1, 0, 0))],
              ['AMBI', b64(struct.pack('<IIIf', rgb(amb), rgb(sun), rgb(fog), 1.0))]]
    c = p.cells[key] = {'flags': 0, 'header': header, 'refs': {},
                        # the room plan, so auto-furnish knows which tiles make which room
                        'plan': {'tile': T, 'rooms': [{'name': (r.get('name') or 'Room %d' % (n + 1)),
                                                       'tiles': [[t[0] * T, t[1] * T, zf(t)] for t, ra in sorted(grid.items()) if ra == n]}
                                                      for n, r in enumerate(rooms)]}}
    mine = p.plugin.lower()
    for item in refs:
        rid, pos, extra = item[:3]
        scale = item[3] if len(item) > 3 else 1.0
        subs = set_ref_pos([('NAME', zs(rid))], pos, round(scale, 3) if abs(scale - 1.0) > 0.005 else 1.0)
        if extra:
            out, put = [], False
            for t_, d_ in subs:
                if t_ == 'DATA' and not put:
                    out += extra
                    put = True
                out.append((t_, d_))
            subs = out
        nk = p.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), subs)
    if shell_spot:
        for pcell, pid, ppose, pscale in shell_spot[2]:
            sc_, _r = editing._cell(db, pcell)
            nk = p.new_ref_key()
            editing._store(sc_, nk, mine, int(nk.rsplit('|', 1)[1]),
                           set_ref_pos([('NAME', zs(pid))], ppose, round(pscale, 3) if abs(pscale - 1.0) > 0.005 else 1.0))
    # the front door outside, and any other doors in the building: all lead in here
    for dcell, did, dpose, dsc in ([out_spot[:2] + (out_spot[2], out_spot[3] if len(out_spot) > 3 else 1.0)] if out_spot else []) + \
            (shell_spot[3] if shell_spot else []):
        oc, _r = editing._cell(db, dcell)
        dsubs = set_ref_pos([('NAME', zs(did))], dpose, round(dsc, 3) if abs(dsc - 1.0) > 0.005 else 1.0)
        out, put = [], False
        for t_, d_ in dsubs:
            if t_ == 'DATA' and not put:
                out += [('DODT', struct.pack('<6f', *arrive)), ('DNAM', zs(name))]
                put = True
            out.append((t_, d_))
        nk = p.new_ref_key()
        editing._store(oc, nk, mine, int(nk.rsplit('|', 1)[1]), out)
    # walking paths for the new place, in the same change
    db.sync_project()
    try:
        import pathgrid
        pathgrid.generate(db, key, note=False)
    except EditError:
        pass
    editing.commit(db, 'Built a new %s interior "%s" (%d rooms, %d tiles)%s' % (
        kits.friendly(style), name, len(rooms), len(grid),
        (' with %s outside in %s' % ('a %s building' % kits.friendly(style) if shell_spot else 'its entrance',
                                     editing.cell_label(db, out_spot[0]))) if out_spot else ''))
    # where everything ended up, for furnishing
    summary = []
    for n, r in enumerate(rooms):
        tiles = [t for t, ra in grid.items() if ra == n]
        xs = [t[0] for t in tiles]
        ys = [t[1] for t in tiles]
        margin = T / 2 - 40
        summary.append({'name': r.get('name') or 'room %d' % (n + 1),
                        'x_min': min(xs) * T - margin, 'x_max': max(xs) * T + margin,
                        'y_min': min(ys) * T - margin, 'y_max': max(ys) * T + margin,
                        'floor_z': zf(tiles[0]), 'floor': tiles[0][2]})
    return {'key': key, 'name': name, 'style': kits.friendly(style), 'tile': T, 'rooms': summary,
            'exit': {'x': round(dx), 'y': round(dy), 'side': exit_side, 'how': exit_how}, 'door': door_id,
            'entrance': out_spot[0] if out_spot else None,
            'building': {'like': shell_spot[1]['like'], 'pieces': len(shell_spot[2]), 'cell': shell_spot[0]} if shell_spot else None,
            'floors': sorted({t[2] for t in grid}), 'stairs': [x['piece']['id'] for x in stair_list],
            'notes': ['No proper doorway piece fitted between "%s" and "%s", so they join through an open gap.' % g for g in gaps] + stair_notes}
