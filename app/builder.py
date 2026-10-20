"""Build a new interior from scratch out of a kit's modular pieces.

Rooms are rectangles on a grid of the kit's tile size (usually 256 units). Every tile gets
the floor piece whose walls match where the room ends; doorways between rooms get the kit's
door frame; the way out gets a load door, linked to a door outside if you give a spot."""
import math
import os
import struct

import editing
import kits
import mapdata
import stairtemplate
from editing import EditError
from esm import ENC, iter_subrecords, zstr
from project import b64, join_subs, set_ref_pos, zs

STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
LEFT_OF = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
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
        # it must at least do a plain floor, a side and a corner; loose wall pieces can stand in for
        # the walls (some styles build every wall that way), and a corner may have doorways on its other
        # sides (styles built from halls)
        loose = bool(kp['walls'])
        side = loose or any(p.count('W') == 1 and 'D' not in p for p in pats)
        corner = loose or any(p[i] == 'W' and p[(i + 1) % 4] == 'W' and p.count('W') == 2 for p in pats for i in range(4))
        if not ('OOOO' in pats and side and corner):
            continue
        small = bool(kp['walls']) or any(p.count('W') >= 3 for p in pats)
        st = kits.stairs(db, prefix)
        out.append({'id': prefix, 'name': kits.friendly(prefix), 'tile': kp['tile'], 'pieces': len(kp['pieces']),
                    'doorways': bool(kp['jambs']), 'small_rooms': small, 'uses': k['uses'], 'floors': bool(st),
                    'stairs_default': bool(st) and st.get('proper', True)})
    out.sort(key=lambda s: -s['uses'])
    _styles.update({'recs': db.recs, 'out': out})
    return out


_styles = {}
_debug = None        # a function given build_interior's needs and choices per tile (the lab uses it)
ALCOVES = True       # stairs in an alcove the way the game has them, where the style's template shows one


def _family(pid):
    """'hall' for a style's corridor pieces, 'room' for the rest."""
    return 'hall' if 'hall' in pid.lower() else 'room'


def _pick(kp, need, family=None):
    """Best piece and turn for a tile: (piece, quarter turns, sides still needing a wall). family:
    'hall' in a corridor, 'room' in a room: of pieces that fit as well, one of that family (the game
    runs its hall pieces along a corridor: a room piece among them brings the room's wall trim, and the
    ledges step up and down along the corridor)."""
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
            # a doorway where the room should just carry on leaves bits of wall and posts standing in it
            stubs = sum(1 for s in kits.SIDES if need[s] == 'open' and pat[s] == 'door')
            clutter = sum(pat['cover'].get(s, 0) for s in kits.SIDES if need[s] == 'open')
            # pieces no real interior uses are often unfinished or special: only as a last resort
            # (a missing wall can be closed with a loose wall piece, when the style has them)
            # (and a piece with its own ceiling over one without: some styles have both)
            score = ((stubs, len(missing)) if kp['walls'] else (len(missing), stubs)) + \
                (p['uses'] == 0, bool(family) and _family(p['id']) != family, not pat.get('ceiling'), round(clutter, 1), -p['uses'])
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


def plain_wall(kp, db=None):
    """The style's loose wall for closing a side: a plain one (not an alcove or a thick decorated one)
    when it has one, else the one used most. With db: of those, one that covers the whole side, seen
    from the room (some have arched or carved tops that leave the void showing above them)."""
    walls = kp['walls']
    # (not a see-through or decorative one either: Indoril's metal screens, grilles, railings, windows.
    # Closing a room with those looks nothing like its other walls)
    decor = ('metal', 'screen', 'grate', 'grill', 'lattice', 'rail', 'iron', 'glass', 'window', 'alc', 'niche')
    looks = [w for w in walls if not any(x in w['id'].lower() for x in decor)]
    plain = [w for w in looks if w['thick'] <= 48] or [w for w in looks if w['thick'] <= kp.get('tile', 256) * 0.25]
    pool = plain or looks or walls
    if db is not None and len(walls) > 1:
        import seethrough
        # made of the same stuff as the style's own room pieces (some sets mix in walls from another
        # set: Tamriel Data's Indoril has Tribunal's Mournhold walls beside its own)
        own = _textures(db, [p['ri'] for p in kp['pieces'][:6]])
        same = lambda w: len(_textures(db, [w['ri']]) & own) * 2 >= max(1, len(_textures(db, [w['ri']])))
        matching = [w for w in (looks or walls) if same(w)] or (looks or walls)
        base = next((w for w in pool if w in matching), matching[0])
        best = max(matching, key=lambda w: (round(seethrough.wall_cover(db, w['ri'], kp['height']), 1), w in pool, w['uses']))
        if seethrough.wall_cover(db, best['ri'], kp['height']) > seethrough.wall_cover(db, base['ri'], kp['height']) + 0.05:
            return best
        return base
    return pool[0]


_TEX = {}


def _textures(db, ris):
    """The textures some models are painted with (file names, lower case, no folder or ending)."""
    out = set()
    for ri in ris:
        if ri not in _TEX:
            shapes = kits._model(db, ri) or []
            _TEX[ri] = {os.path.splitext(os.path.basename(str(s.get('tex') or '').replace('\\', '/')))[0].lower()
                        for s in shapes if s.get('tex')}
        out |= _TEX[ri]
    return out


def _centred(db, ri, x, y, rot, scale=1.0):
    """Where to put a model's origin so the middle of the model (not its origin, which for many
    doors is the hinge or somewhere else entirely) lands on (x, y) after turning it by rot."""
    b = mapdata.object_bounds(db, ri)
    if not b:
        return x, y
    cx, cy = (b[0] + b[3]) / 2 * scale, (b[1] + b[4]) / 2 * scale
    wx, wy = cx * math.cos(rot) + cy * math.sin(rot), -cx * math.sin(rot) + cy * math.cos(rot)
    return x - wx, y - wy


def _pick_under(kp, want, side, way):
    """The floor piece the game puts under this doorway (way: from kits.edge_doors), turned so its
    doorway side faces this side, when it fits the spot: (piece, q, missing walls, pattern) or None."""
    pid, own = way.get('piece'), way.get('piece_side')
    p = next((x for x in kp['pieces'] if pid and x['id'].lower() == pid.lower()), None)
    if not p or way.get('piece_uses', 0) < 3:          # (seen enough to be how the style does it)
        return None
    q = (kits.SIDES.index(side) - kits.SIDES.index(own)) % 4
    pat = kits.rotate(p['pattern'], q)
    missing = []
    for s in kits.SIDES:
        if want[s] == 'wall':
            if pat[s] != 'wall':
                missing.append(s)
        elif pat[s] != want[s]:
            return None                  # (a wall or doorway where the room carries on)
    return p, q, missing, pat


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
        # a rectangle, less the tiles taken away ('cut') and with tiles added on ('add'): [[x, y]], on its floor
        x0, y0 = int(r.get('x', 0)), int(r.get('y', 0))
        cut = {(int(t[0]), int(t[1])) for t in r.get('cut') or []}
        tiles = [(tx, ty) for tx in range(x0, x0 + w) for ty in range(y0, y0 + h) if (tx, ty) not in cut]
        tiles += [t for t in dict.fromkeys((int(t[0]), int(t[1])) for t in r.get('add') or []) if t not in tiles]
        if not tiles:
            raise EditError('Room "%s" has no tiles left.' % rn)
        if len(tiles) > 1 and not _connected([(t[0], t[1], f) for t in tiles]):
            raise EditError('Room "%s" is in two pieces. Join them up, or make two rooms.' % rn)
        for tx, ty in tiles:
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


def _door_pairs(rooms, names, doors):
    """The pairs of rooms (numbers) that want a doorway between them, and the tiles of the doorways put
    in an exact spot on the plan (stairs mustn't take those): (pairs, tiles)."""
    out, keep = set(), set()
    for d in doors or []:
        try:
            a, b = [names.index(str(x).strip().lower()) if not isinstance(x, int) else x for x in d['rooms'][:2]]
        except (ValueError, KeyError, TypeError):
            continue
        out.add((a, b))
        at = d.get('at')
        if at and str(at.get('side') or '').upper()[:1] in STEP:
            t_ = (int(at['x']), int(at['y']), int(rooms[a].get('floor') or 0))
            keep |= {t_, nb(t_, str(at['side']).upper()[:1])}
    return out, keep


def _alcove_shape(kp, piece, tpl):
    """How the game stands a one-tile stair of this style in an alcove, from its template
    (stairtemplate.template): the two tiles at its ends and the room's tile along one flank are in the
    template, and the end pieces are open (an arch) towards that flank: that is the room's side; the
    ends are closed at the back. In the piece's own frame: {'ends': [low end offset, high end offset],
    'flank': offset of the room's tile beside the stair, 'pats': {offset: pattern}}, or None when the
    template doesn't show that arrangement (styles with no template, or whose stairs stand free)."""
    by_id = {p['id'].lower(): p for p in kp['pieces']}
    lo = STEP[piece['low']]
    ends = [(lo[0], lo[1], 0), (-lo[0], -lo[1], 0)]
    pats = {}
    for k in ends:
        if k not in tpl or tpl[k][0].lower() not in by_id:
            return None
        pats[k] = kits.rotate(by_id[tpl[k][0].lower()]['pattern'], tpl[k][1])
    flank = None
    for fk in ((lo[1], lo[0], 0), (-lo[1], -lo[0], 0)):
        if fk not in tpl or tpl[fk][0].lower() not in by_id:
            continue
        s = side_of(fk[0], fk[1])
        if all(pats[e][s] != 'wall' for e in ends):
            if flank:
                return None                      # (open to both sides: no alcove)
            flank = fk
    if not flank:
        return None
    pats[flank] = kits.rotate(by_id[tpl[flank][0].lower()]['pattern'], tpl[flank][1])
    return {'ends': ends, 'flank': flank, 'pats': pats}


def _alcove(grid, used, piece, shape, s0, up, f, g):
    """A one-tile stair placed the way the game places it (see _alcove_shape): in a 3-wide alcove on
    the edge of a room, the tiles at its two ends closed in (walls at the back and the outer side, an
    arch into the room and towards the stair), the room's tile beside it walled towards it on the lower
    floor and open on the upper one, where the room looks down into the stairwell. The end tiles are
    taken out of the room (or added beside it) and get the needs the game's pieces there have.
    Returns None, or {'carve', 'land', 'lo', 'hi', 'needs': {tile: {side: need}}, 'vcarve' (the tiles
    out of the room's floor for the checks), 'cuts' (walls put through a room), 'flank': world side}."""
    down = OPPOSITE[up]
    q = (kits.SIDES.index(down) - kits.SIDES.index(piece['low'])) % 4
    sxy = (s0[0], s0[1])

    def world(k, lv):
        wx, wy = stairtemplate.world_tile(sxy, q, k[0], k[1], 1)
        return (int(round(wx)), int(round(wy)), lv)
    e0, e1 = [world(k, f) for k in shape['ends']]
    if (e0[0], e0[1]) != nb(s0, down)[:2] or (e1[0], e1[1]) != nb(s0, up)[:2]:
        return None
    near = world(shape['flank'], f)
    fside = side_of(near[0] - s0[0], near[1] - s0[1])
    if any(t[:2] in used for t in (e0, e1, s0)):
        return None
    carve = [(s0[0], s0[1], lv) for lv in (f, g) if (s0[0], s0[1], lv) in grid]
    if near not in grid:
        return None
    R = grid[near]
    # the room's tiles under the arches at the ends: the way into the alcove and up the stairs
    if any(grid.get(nb(e, fside)) != R for e in (e0, e1)):
        return None
    land = []
    for e in (e0, e1):
        if e in grid:
            if grid[e] != R:
                return None
        else:
            land.append((e, R))
    hi = (e1[0], e1[1], g)
    if hi not in grid:
        beside = [nb(hi, s) for s in STEP if nb(hi, s) in grid and nb(hi, s) not in carve and nb(hi, s)[:2] != sxy]
        if not beside:
            return None
        land.append((hi, grid[beside[0]]))
    vcarve = carve + [e for e in (e0, e1) if e in grid]
    # the needs the game's pieces have: walls closing the ends in (through the room where it goes on
    # past the alcove: a cut), arches into the room, open towards the stair (its arch), the room's
    # tile beside the stair walled towards it (or whatever the game has there)
    needs, cuts = {}, 0

    def setn(t, s, v):
        needs.setdefault(t, {})[s] = v
    pats = {e0: kits.rotate(shape['pats'][shape['ends'][0]], q), e1: kits.rotate(shape['pats'][shape['ends'][1]], q),
            near: kits.rotate(shape['pats'][shape['flank']], q)}
    for t, pat in pats.items():
        for s in STEP:
            n_ = nb(t, s)
            if n_[:2] == sxy:
                setn(t, s, pat[s] if t == near else 'open')
                continue
            same = n_ in grid and n_ not in vcarve and grid[n_] == R
            if pat[s] == 'wall':
                setn(t, s, 'wall')
                if same:
                    setn(n_, OPPOSITE[s], 'wall')
                    cuts += 1
            elif pat[s] == 'door' and same:
                setn(t, s, 'door')
                setn(n_, OPPOSITE[s], 'door')
    return {'carve': carve, 'land': land, 'lo': e0, 'hi': hi, 'needs': needs, 'vcarve': vcarve, 'cuts': cuts, 'flank': fside}


def _carve_check(grid, carve, doors_):
    """Whether these tiles can be taken out of their rooms for stairs: never all of a room, the room
    must stay in one piece, and not the last of the wall two rooms share that want a doorway in it (or
    a doorway's own tiles, when the plan puts it in an exact spot). Returns how many nooks it leaves
    (tiles of the room walled on three sides: the game's own places almost never have one beside their
    stairs, see stairsurvey.py), or None when it can't be done."""
    for c in carve:
        left = [t for t, r in grid.items() if r == grid[c] and t not in carve]
        if len(left) < 2 or not _connected(left):
            return None
    pairs, keep_tiles = doors_
    cset = set(carve)
    if cset & set(keep_tiles):
        return None
    for a_, b_ in pairs:
        if not any(grid.get(c) in (a_, b_) for c in carve):
            continue
        if not any(r_ == a_ and t_ not in cset and nb(t_, s_) not in cset and grid.get(nb(t_, s_)) == b_
                   for t_, r_ in grid.items() for s_ in STEP):
            return None
    nooks = 0
    for c in carve:
        for s_ in STEP:
            t_ = nb(c, s_)
            if t_ in grid and t_ not in carve and grid[t_] == grid[c]:
                joined = sum(1 for s2 in STEP if nb(t_, s2) in grid and nb(t_, s2) not in carve
                             and grid[nb(t_, s2)] == grid[t_])
                if joined <= 1:
                    nooks += 1
    return nooks


def _stair_cost(info, piece, want, n_carve, n_land, rooms_lo, rooms_hi, bx, by, xs, ys):
    """The parts of a stair placement's cost that don't depend on how it sits in the room: the piece
    the game itself builds with over one it hardly uses (the pieces round it are known then, see
    stairtemplate.py), what was asked for (outside the rooms, joining given rooms), and a spot near
    the middle of the building rather than off in a corner."""
    cost = 4 * (1 - min(1, piece.get('uses', 0) / 20.0))
    if want.get('outside'):
        # beside the rooms, in a stairwell of their own: taking floor from a room costs far more than
        # a landing joined to the room next to them
        cost += n_carve * 10 - n_land * 4
    if want.get('from') is not None and rooms_lo != want['from']:
        cost += 6
    if want.get('to') is not None and rooms_hi != want['to']:
        cost += 6
    cost += 0.01 * (abs(bx - (min(xs) + max(xs)) / 2) + abs(by - (min(ys) + max(ys)) / 2))
    cost += info['pieces'].index(piece) * 0.2
    return cost


def _place_stairs(db, style, kp, grid, rooms, wanted=None, doors_=((), ())):
    """Join each floor to the one above with a staircase from the style's own stair pieces.
    Changes grid in place (a landing tile may be added to a room, or a tile given up for the
    stairwell). Where the style's stair survey shows how the game stands the stair in an alcove (see
    _alcove), that arrangement is weighed against the plain spots and preferred when it costs about the
    same. Returns [{'piece', 'tiles': [(x, y, floor)], 'up': side, 'q', 'z'..., 'alcove': {tile: {side:
    need}} or None, 'open_low': the open sides downstairs}] and notes."""
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
        # put there by hand: only that spot and that way up (the bottom step's tile, and the side it climbs to)
        at = want.get('at')
        if at:
            ax, ay, aup = int(at['x']), int(at['y']), str(at.get('up') or 'N').upper()
            if aup not in kits.SIDES:
                aup = 'N'
        cands = []
        for piece in info['pieces']:
            n = int(round(H / piece['rise']))
            if n < 1 or n > 2 or (piece['open'] and n > 1):
                continue
            # a piece several tiles long climbs the whole storey on its own
            L = piece.get('len', 1)
            if L > 1 and n != 1:
                continue
            span = max(n, L)
            # (how the game stands this stair in an alcove, when its template shows one)
            shape = _alcove_shape(kp, piece, stairtemplate.template(db, style, piece['id'])) \
                if ALCOVES and n == 1 and L == 1 and 'cx' not in piece else None
            for up in ([aup] if at else kits.SIDES):
                down = OPPOSITE[up]
                for bx in ([ax] if at else range(min(xs) - span - 2, max(xs) + span + 3)):
                    for by in ([ay] if at else range(min(ys) - span - 2, max(ys) + span + 3)):
                        st = [nb((bx, by, f), up, i) for i in range(span)]
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
                        nooks = _carve_check(grid, carve, doors_)
                        if nooks is None:
                            continue
                        rooms_lo = grid[lo] if lo in grid and lo not in carve else land[0][1]
                        rooms_hi = grid[hi] if hi in grid and hi not in carve else land[-1][1]
                        # stairs open on one side leave a gap where they meet the next wall: a last resort
                        # (inside the rooms rather than landings sticking out of the building)
                        # floor beside the stairs, on either floor: the game mostly stands stairs along an
                        # outside wall or in a stairwell of their own, not through the middle of a room
                        side_n = sum(1 for s in st for lv in (f, g) for sd in (LEFT_OF[up], OPPOSITE[LEFT_OF[up]])
                                     if nb((s[0], s[1], lv), sd) in grid and nb((s[0], s[1], lv), sd) not in carve)
                        cost = len(carve) * 2 + len(land) * 6 + ((3 if piece['post'] else 10) if piece['open'] else 0) + nooks * 25 + side_n * 1.5
                        cost += _stair_cost(info, piece, want, len(carve), len(land), rooms_lo, rooms_hi, bx, by, xs, ys)
                        cands.append((cost, len(cands), piece, up, st, lo, hi, carve, land, rot_open, None))
                    # the same spot, but the stair in an alcove the way the game's own places have it
                    # (see _alcove): the room's tile beside it walled towards it, closed-in corners at
                    # its ends. Preferred when it costs about the same
                    if shape:
                        for bx in ([ax] if at else range(min(xs) - 3, max(xs) + 4)):
                            for by in ([ay] if at else range(min(ys) - 3, max(ys) + 4)):
                                s0 = (bx, by, f)
                                alc = _alcove(grid, used, piece, shape, s0, up, f, g)
                                if not alc:
                                    continue
                                carve, land, lo, hi = alc['carve'], alc['land'], alc['lo'], alc['hi']
                                nooks = _carve_check(grid, alc['vcarve'], doors_)
                                if nooks is None:
                                    continue
                                rooms_lo = grid[lo] if lo in grid else land[0][1]
                                rooms_hi = grid[hi] if hi in grid and hi not in carve else land[-1][1]
                                side_n = sum(1 for lv in (f, g) for sd in (LEFT_OF[up], OPPOSITE[LEFT_OF[up]])
                                             if nb((bx, by, lv), sd) in grid and nb((bx, by, lv), sd) not in carve)
                                cost = len(carve) * 2 + len(land) * 6 + nooks * 25 + side_n * 1.5 + alc['cuts'] * 3 - 3
                                cost += _stair_cost(info, piece, want, len(carve), len(land), rooms_lo, rooms_hi, bx, by, xs, ys)
                                cands.append((cost, len(cands), piece, up, [s0], lo, hi, carve, land, [alc['flank']], alc))
        # the cheapest spot where the floor round the stairs can still be built from the style's pieces
        best = None
        for c in sorted(cands)[:400]:
            if _stairs_fit(kp, grid, c[4], c[5], c[6], c[3], c[7], c[8], c[10]['needs'] if c[10] else None):
                best = (c[0],) + c[2:]
                break
        if not best and at:
            raise EditError(_pin_problem(info, kits.friendly(style), grid, used, f, ax, ay, aup, bool(cands)))
        if not best:
            raise EditError('Could not find room for stairs between the %s and the %s. Make the rooms on both '
                            'floors a little bigger (3 tiles deep is enough).' % (FLOOR_NAMES.get(f), FLOOR_NAMES.get(g)))
        cost, piece, up, st, lo, hi, carve, land, rot_open, alc = best
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
                       'open': rot_open, 'storey': H, 'pinned': bool(at), 'land': [t for t, _r in land],
                       # an alcove: the needs of the tiles round the stair, and its side open only upstairs
                       'alcove': alc['needs'] if alc else None, 'open_low': [] if alc else rot_open})
        if land:
            notes.append('The stairs from the %s needed %s.' % (FLOOR_NAMES.get(f), 'a small landing' if len(land) == 1 else
                                                                 'two small landings' if len(land) == 2 else 'small landings'))
    return placed, notes


def _pin_problem(info, style_name, grid, used, f, x, y, up, any_spot):
    """Why stairs put somewhere by hand can't go there, in words (for the planner)."""
    g, down = f + 1, OPPOSITE[up]
    where = 'The stairs you put from the %s up' % FLOOR_NAMES.get(f)
    lens = sorted({max(int(round(info['storey'] / p['rise'])), p.get('len', 1)) for p in info['pieces'] if p['rise']})
    span = lens[0] if lens else 1
    st = [nb((x, y, f), up, i) for i in range(span)]
    if any((s[0], s[1]) in used for s in st):
        return where + ' run into the other stairs. Move them apart.'
    lo, hi = nb(st[0], down), nb((st[-1][0], st[-1][1], g), up)
    near = lambda t: t in grid or any(nb(t, s) in grid for s in STEP)
    if not near(lo):
        return where + ' start where there is no room on the %s to step onto them from. Put the bottom end (the arrow\'s tail) in or next to a room.' % FLOOR_NAMES.get(f)
    if not near(hi):
        return where + ' come out where there is no room on the %s to step off into. Put a room there, or turn the stairs (R).' % FLOOR_NAMES.get(g)
    if any_spot:
        return where + ' fit, but the %s style has no wall or floor pieces for the rooms round them just there. Try a tile further along, or turn them (R).' % style_name
    return where + ' don\'t fit there: they would leave a room in two pieces, or take all of it, or need floor on both sides. Try a tile further along, or turn them (R).'


def _stairs_fit(kp, grid, st, lo, hi, up, carve, land, extra=None):
    """Whether the tiles round a staircase put here can all still get a floor piece of the style (some
    styles have no piece for a strip with walls on both sides, for instance). extra: {tile: {side:
    need}} for stairs in an alcove (see _alcove)."""
    g = {t: r for t, r in grid.items() if t not in carve}
    for t, r in land:
        g[t] = r
    stair_xy = {(s[0], s[1]) for s in st}
    near = {t for t in g if any(abs(t[0] - s[0]) <= 1 and abs(t[1] - s[1]) <= 1 for s in stair_xy)} | {lo, hi}
    for t in near:
        if t not in g:
            continue
        need = {s: 'open' if g.get(nb(t, s)) == g[t] else 'wall' for s in STEP}
        if t == lo:
            need[up] = 'open'
        if t == hi:
            need[OPPOSITE[up]] = 'open'
        need.update((extra or {}).get(t, {}))
        # (sides facing the stairs may stay open: stairs standing free, a railing round the stairwell)
        facing = [s for s in STEP if (nb(t, s)[0], nb(t, s)[1]) in stair_xy and need[s] == 'wall']
        if _stair_need(kp, need, facing) is None:
            return False
    return True


def _stair_need(kp, need, facing):
    """A tile next to stairs: walls towards them if the style has a piece for that, else those sides
    open. Changes need; returns the sides left open, or None if neither fits."""
    piece, _q, missing, _p = _pick(kp, need)
    if piece is not None and not (missing and not kp['walls']):
        return []
    for s in facing:
        need[s] = 'open'
    piece, _q, missing, _p = _pick(kp, need)
    if piece is not None and not (missing and not kp['walls']):
        return list(facing)
    return None


def _wanted_stairs(rooms, names, stairs):
    """{lower floor: {'from': room, 'to': room}} from [{'rooms': [a, b]}] (names or numbers)."""
    def idx(ref):
        if isinstance(ref, int):
            return ref
        s = str(ref).strip().lower()
        if s in names:
            return names.index(s)
        raise EditError('There is no room called "%s".' % ref)
    wanted = {}
    for s in stairs or []:
        # {'rooms': [a, b]} which rooms they join; {'floor': f, 'at': {x, y, up}} put by hand;
        # 'outside': rather beside the rooms than in one (any of these, for the stairs from floor f up)
        w = {}
        if s.get('rooms'):
            a, b = idx(s['rooms'][0]), idx(s['rooms'][1])
            fa, fb = int(rooms[a].get('floor') or 0), int(rooms[b].get('floor') or 0)
            if abs(fa - fb) != 1:
                raise EditError('Stairs join a room to one on the floor just above or below it.')
            if fa > fb:
                a, b, fa = b, a, fb
            w = {'from': a, 'to': b}
        elif s.get('floor') is not None:
            fa = int(s['floor'])
        else:
            continue
        if s.get('at'):
            w['at'] = s['at']
        if s.get('outside'):
            w['outside'] = True
        wanted.setdefault(fa, {}).update(w)
    return wanted


def plan(db, style, rooms, stairs=None, floors_as='auto', doors=None):
    """Where everything would go, without building it: tiles per floor and the stairs."""
    kp = kits.kit_pieces(db, style)
    if not kp or not kp['pieces']:
        raise EditError('Unknown building style "%s".' % style)
    grid, names = _grid(rooms)
    st_info = kits.stairs(db, style)
    use_stairs = bool(st_info) and (floors_as == 'stairs' or (floors_as == 'auto' and st_info.get('proper', True)))
    if len({t[2] for t in grid}) > 1 and not use_stairs:
        # (each floor will be a place of its own, joined by doors: nothing to work out here)
        return {'tiles': [[t[0], t[1], t[2], r] for t, r in sorted(grid.items())], 'stairs': [], 'linked': True,
                'can_stairs': bool(st_info),
                'notes': [('Each floor becomes a place of its own' if kits.stairs(db, style) else
                           'This style has no stair pieces, so each floor becomes a place of its own') +
                          ', joined by a door (a trapdoor down to a cellar).']}
    stairs, notes = _place_stairs(db, style, kp, grid, rooms, _wanted_stairs(rooms, names, stairs), _door_pairs(rooms, names, doors))
    return {'tiles': [[t[0], t[1], t[2], r] for t, r in sorted(grid.items())],
            'stairs': [{'tiles': [[s[0], s[1], s[2]] for s in x['tiles']], 'up': x['up'], 'floor': x['floor'], 'pinned': x['pinned'],
                        'land': [[t[0], t[1], t[2]] for t in x['land']]} for x in stairs],
            'notes': notes}


def build_interior(db, name, style, rooms, doors=None, exit=None, entrance=None, lighting='normal',
                   lights=True, outside_door=None, stairs=None, commit=True, exit_door=None):
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

    stair_list, stair_notes = _place_stairs(db, style, kp, grid, rooms, _wanted_stairs(rooms, names, stairs),
                                            _door_pairs(rooms, names, doors))
    H = stair_list[0]['storey'] if stair_list else 256

    def boundary(a, b):
        """Edges between two rooms: [(tile, side)] with the tile in room a."""
        return [(t, s) for t, ra in grid.items() if ra == a for s in STEP if grid.get(nb(t, s)) == b]

    # ---- what each tile needs on each side: open within a room, a wall at its edge
    need = {}
    for t, ra in grid.items():
        need[t] = {s: 'open' if grid.get(nb(t, s)) == ra else 'wall' for s in STEP}
    # ... and open towards the ends of a staircase (and its open sides)
    alcove_tiles = set()
    for x in stair_list:
        need[x['lo']][x['up']] = 'open'
        need[x['hi']][OPPOSITE[x['up']]] = 'open'
        for ws in x['open']:
            for lv in (x['floor'], x['floor'] + 1):
                # (stairs in an alcove: walled on the lower floor, open only where the room above
                # looks down into the stairwell)
                if lv == x['floor'] and ws not in x.get('open_low', x['open']):
                    continue
                t = nb((x['tiles'][0][0], x['tiles'][0][1], lv), ws)
                if t in need:
                    need[t][OPPOSITE[ws]] = 'open'
        # stairs in an alcove the way the game has them (see _alcove): the tiles round them need what
        # the game's pieces there have, walls, arches and all
        for t, sides in (x.get('alcove') or {}).items():
            if t in need:
                need[t].update(sides)
                alcove_tiles.add(t)
    # tiles beside the stairs that have no piece walling them off: open towards the stairs, and on
    # the floor above a railing along the edge of the stairwell
    rail_edges = []                     # (tile, side) on an upper floor
    for x in stair_list:
        sxy = {(s[0], s[1]) for s in x['tiles']}
        for t in list(need):
            if t[2] not in (x['floor'], x['floor'] + 1):
                continue
            facing = [s for s in STEP if (nb(t, s)[0], nb(t, s)[1]) in sxy and need[t][s] == 'wall']
            if not facing:
                continue
            opened = _stair_need(kp, need[t], facing)
            if opened and t[2] == x['floor'] + 1:
                rail_edges += [(t, s) for s in opened]
        # (stairs in an alcove: the room above looks down into the stairwell over a railing, as in the
        # game's own places)
        if x.get('alcove'):
            for ws in x['open']:
                t = nb((x['tiles'][0][0], x['tiles'][0][1], x['floor'] + 1), ws)
                if t in need and need[t][OPPOSITE[ws]] == 'open' and (t, OPPOSITE[ws]) not in rail_edges:
                    rail_edges.append((t, OPPOSITE[ws]))

    def fits(t):
        return _pick(kp, need[t])[0] is not None

    def badness(tiles):
        """(bits of doorway left standing in rooms, walls the pieces can't close) for these tiles."""
        stubs = missing = 0
        for t in tiles:
            piece, _q, miss, pat = _pick(kp, need[t])
            if piece is None:
                return None
            stubs += sum(1 for s in kits.SIDES if need[t][s] == 'open' and pat[s] == 'door')
            missing += len(miss)
        if missing and not kp['walls']:
            return None
        return stubs, missing

    # how the game itself makes doorways in this style: a frame (and a door) standing on the edge
    learned = kits.edge_doors(db, style)
    inner_ways = [e for e in learned if e['b'] != 'out' and 'wall' not in (e['a'], e['b'])][:10]
    if not inner_ways:
        # none seen in the game: borrow from the style its own door frames come from (Tamriel Data's
        # Hlaalu houses use the original Hlaalu frames, for instance)
        for other in dict.fromkeys(kits.kit_prefix(p[0]) for e in learned for p in e['parts']):
            if other and other != style and kits.kit_pieces(db, other) and kits.kit_pieces(db, other)['tile'] == kp['tile']:
                inner_ways = [e for e in kits.edge_doors(db, other) if e['b'] != 'out' and 'wall' not in (e['a'], e['b'])][:10]
                if inner_ways:
                    break
    # (any door will do for the way out: it gets its own link outside; the game's front doors first)
    exit_ways = sorted((e for e in learned if e['b'] == 'out' and e['door']), key=lambda e: (not e['load'], -e['uses']))[:10]
    if exit_door:
        exit_ways = []                   # (a given way out, e.g. a ladder: it stands against the wall)
    learned_edges = []   # (tile, side, way): doorways to build from what the game does

    load_jamb = next((j for j in kp['jambs'] if j.get('load') and j['width'] >= T * 0.9), None)
    full_jamb = next((j for j in kp['jambs'] if not j.get('load') and j['width'] >= T * 0.9), None) or load_jamb
    small_jamb = next((j for j in kp['jambs'] if j['width'] < T * 0.9), None)
    frame_style = kp['frame_doors'] or not kp['entry_doors']
    frames = []          # (tile, side) where a full-width door frame goes between two tiles
    gaps = []            # doorways that could only be left as open gaps
    # ---- doorways between rooms (rooms joined with no wall at all first: doorways go around them)
    for d in sorted(doors or [], key=lambda d: d.get('kind') != 'open'):
        a, b = room_index(d['rooms'][0]), room_index(d['rooms'][1])
        e = boundary(a, b)
        if not e:
            raise EditError('Rooms "%s" and "%s" don\'t touch, so there is no wall to put a door in.' % (rooms[a].get('name'), rooms[b].get('name')))
        # (not through the closed-in corners of a stair's alcove, when there is wall elsewhere)
        e = [(t, s) for t, s in e if t not in alcove_tiles and nb(t, s) not in alcove_tiles] or e
        if d.get('kind') == 'open':
            # one space: no wall between them anywhere (an L-shaped room, a hall with an alcove)
            for t, s in e:
                need[t][s] = need[nb(t, s)][OPPOSITE[s]] = 'open'
            continue
        at = d.get('at')
        if at:
            # exactly where it was put on the plan (given from either room's side of the wall)
            s_ = str(at.get('side') or '').upper()[:1]
            if s_ not in STEP:
                raise EditError('A doorway between "%s" and "%s" has no side.' % (rooms[a].get('name'), rooms[b].get('name')))
            t_ = (int(at['x']), int(at['y']), int(rooms[a].get('floor') or 0))
            spot = (t_, s_) if (t_, s_) in e else (nb(t_, s_), OPPOSITE[s_]) if (nb(t_, s_), OPPOSITE[s_]) in e else None
            if spot is None:
                raise EditError('The doorway between "%s" and "%s" isn\'t on the wall they share. Put it back on that wall.' % (
                    rooms[a].get('name'), rooms[b].get('name')))
            e = [spot]
        # try the middle of the shared wall first, then spots around it
        e = sorted(e)
        order = sorted(range(len(e)), key=lambda i: abs(i - len(e) // 2))
        done = False
        # first the ways the game makes doorways in this style, where they leave no bits of wall in a room
        best = None
        for rank, i in enumerate(order):
            t, s = e[i]
            n2, o = nb(t, s), OPPOSITE[s]
            saved = (need[t][s], need[n2][o])
            for wn, way in enumerate(inner_ways):
                need[t][s], need[n2][o] = way['a'], way['b']
                bad = badness([t, n2])
                if bad is not None and bad[0] == 0:
                    # (where the game's own floor piece for this doorway fits first: elsewhere an
                    # ordinary piece beside the frame can leave a gap)
                    score = (bad[1], _pick_under(kp, need[t], s, way) is None, rank, wn)
                    if best is None or score < best[0]:
                        best = (score, t, s, way)
            need[t][s], need[n2][o] = saved
        if best:
            _sc, t, s, way = best
            need[t][s], need[nb(t, s)][OPPOSITE[s]] = way['a'], way['b']
            learned_edges.append((t, s, way))
            continue
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
    outer = [o for o in outer if o[0] not in alcove_tiles] or outer
    if ex.get('x') is not None:
        # exactly where it was put on the plan
        spot = ((int(ex['x']), int(ex['y']), int(rooms[er].get('floor') or 0)), eside)
        if grid.get(spot[0]) != er or not free(*spot):
            raise EditError('The way out isn\'t on an outside wall of "%s" (or stairs are in the way). Put it on an outside wall.' % rooms[er].get('name'))
        outer = [spot]
    if not outer:
        outer = sorted((t, s) for t, ra in grid.items() if ra == er for s in kits.SIDES if free(t, s))
    if not outer:
        raise EditError('Room "%s" has no outside wall left for the way out.' % rooms[er].get('name'))
    exit_how = 'wall'            # 'frame' (full frame + door), 'entry' (door in a doorway piece), 'wall' (door on a wall),
                                 # 'learned' (built the way the game builds front doors in this style)
    exit_tile, exit_side = outer[len(outer) // 2]
    exit_way = None
    best = None
    for rank, i in enumerate(sorted(range(len(outer)), key=lambda i: abs(i - len(outer) // 2))):
        t, s = outer[i]
        for wn, way in enumerate(exit_ways):
            need[t][s] = way['a']
            bad = badness([t])
            if bad is not None and bad[0] == 0:
                score = (bad[1], _pick_under(kp, need[t], s, way) is None, rank, wn)
                if best is None or score < best[0]:
                    best = (score, t, s, way)
        need[t][s] = 'wall'
    if best:
        _sc, exit_tile, exit_side, exit_way = best
        need[exit_tile][exit_side] = exit_way['a']
        exit_how = 'learned'
    for i in sorted(range(len(outer)), key=lambda i: abs(i - len(outer) // 2)) if not exit_way and not exit_door else []:
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
    stair_tiles = {s for x_ in stair_list for s in x_['tiles']}

    def put_cap(x, sp, ox_, oy_, oz_, rot):
        """What the game stands in the same spot as these stairs to close in the stairwell (a room piece
        with walls and a ceiling but no floor on top, a wall beside it, or a piece the stairs stand
        inside), where no room of that floor is, its walls never across a room (nor across the way
        off the top of the stairs), and one wall to a side."""
        closed = set()                                   # (level, side) walled already
        for cap in sp.get('cap') or []:
            cri = db.resolve_id(cap[0])
            cb = mapdata.object_bounds(db, cri) if cri is not None else None
            if not cb:
                continue
            cz = oz_ + cap[1]
            level = int(round((cz + cb[2]) / H))
            home = min(x['tiles'], key=lambda s_: math.hypot(centre(s_)[0] - ox_, centre(s_)[1] - oy_))
            spot = (home[0], home[1], level)
            if spot in grid or (spot in stair_tiles and spot not in x['tiles']):
                continue
            crot = (rot + cap[2] * math.pi / 2) % (2 * math.pi)
            cpat = kits.measure(db, cri, T)
            cq = int(round(crot / (math.pi / 2))) % 4
            if not cpat:
                continue
            wpat = kits.rotate(cpat, cq)
            walls_ = [d for d in kits.SIDES if wpat[d] == 'wall']
            if not walls_ or any(nb(spot, d) in grid or (spot[2] == x['floor'] + 1 and d == x['up']) or (level, d) in closed
                                 for d in walls_):
                continue
            closed |= {(level, d) for d in walls_}
            refs.append((cap[0], (ox_, oy_, cz, 0, 0, crot), []))

    for x in stair_list:
        sp = x['piece']
        rot = x['q'] * math.pi / 2
        if sp.get('len', 1) > 1 or 'cx' in sp:
            # one piece over its whole run, the middle of its model in the middle of the tiles
            a, c = centre(x['tiles'][0]), centre(x['tiles'][-1])
            mx, my = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
            ox, oy = sp.get('cx', 0.0), sp.get('cy', 0.0)
            wx, wy = ox * math.cos(rot) + oy * math.sin(rot), -ox * math.sin(rot) + oy * math.cos(rot)
            oz = z0 + zf(x['tiles'][0]) - sp['z_low']
            refs.append((sp['id'], (mx - wx, my - wy, oz, 0, 0, rot), []))
            put_cap(x, sp, mx - wx, my - wy, oz, rot)
        whole = sp.get('len', 1) > 1 or 'cx' in sp
        for i, s in enumerate(x['tiles']):
            sx_, sy_ = centre(s)
            if not whole:                      # a piece per tile, each a step higher
                sz = z0 + zf(s) - sp['z_low'] + i * sp['rise']
                refs.append((sp['id'], (sx_, sy_, sz, 0, 0, rot), []))
                put_cap(x, sp, sx_, sy_, sz, rot)
            # posts where an open side meets the walls beside it, on both floors (as the game does;
            # not downstairs where the side is walled, stairs in an alcove)
            if sp['post'] and x['open']:
                for ws in x['open']:
                    ax, ay = STEP[ws]
                    bx, by = STEP[x['up']]
                    for along in (-1, 1):
                        for lv in ([s[2]] if ws in x.get('open_low', x['open']) else []) + [s[2] + 1]:
                            refs.append((sp['post'], (sx_ + (ax + bx * along) * T / 2, sy_ + (ay + by * along) * T / 2,
                                                      z0 + lv * H, 0, 0, 0), []))
    # ---- railings round the stairwell, from the style's own railing pieces
    rail = None
    for ri_ in kp['ris']:
        rid_ = db.recs[ri_][1]
        rb = mapdata.object_bounds(db, ri_) if 'rail' in rid_.lower() else None
        if rb and T * 0.75 <= max(rb[3] - rb[0], rb[4] - rb[1]) <= T * 1.15 and min(rb[3] - rb[0], rb[4] - rb[1]) < T * 0.3 \
                and rb[5] - rb[2] < 160:
            uses = kits.game_uses(db, rid_.lower())
            if rail is None or uses > rail[2]:
                rail = (rid_, rb, uses, ri_)
    for t, s in rail_edges if rail else []:
        rid_, rb, _u, ri_ = rail
        cx, cy = centre(t)
        thick = min(rb[3] - rb[0], rb[4] - rb[1])
        ex_, ey_ = cx + STEP[s][0] * (T / 2 - thick / 2), cy + STEP[s][1] * (T / 2 - thick / 2)
        rot = 0 if (s in 'EW') == ((rb[3] - rb[0]) < (rb[4] - rb[1])) else math.pi / 2
        px, py = _centred(db, ri_, ex_, ey_, rot)
        refs.append((rid_, (px, py, -rb[2] + zf(t), 0, 0, rot), []))
    # ---- floor tiles
    exit_fit = None
    # doorways learnt from the game: the floor piece the game itself puts under each (often one made for
    # it, whose walls meet the door frame: an ordinary piece there leaves a gap beside the frame)
    under = {}
    for t, s, way in learned_edges + ([(exit_tile, exit_side, exit_way)] if exit_how == 'learned' else []):
        under.setdefault(t, []).append((s, way))
    # corridors: rooms with no two-by-two block of tiles anywhere in them
    tiles_of = {}
    for t, ra in grid.items():
        tiles_of.setdefault(ra, set()).add(t)
    corridor = {ra for ra, ts in tiles_of.items()
                if not any({(x + 1, y, f), (x, y + 1, f), (x + 1, y + 1, f)} <= ts for x, y, f in ts)}
    has_halls = any(_family(p['id']) == 'hall' for p in kp['pieces']) and any(_family(p['id']) == 'room' for p in kp['pieces'])
    # the pieces the game itself stands round this style's stairs, and how it turns them (a Hall_Corner
    # on either side of an Indoril stair, facing each other): laid the same way here, where the tile
    # needs allow it (see stairtemplate.py)
    forced = {}
    by_id = {p['id'].lower(): p for p in kp['pieces']}
    for x in stair_list:
        sp = x['piece']
        if sp.get('len', 1) > 1 or 'cx' in sp:
            continue
        s0 = x['tiles'][0]
        own = {(s[0], s[1], lv) for s in x['tiles'] for lv in (s[2], s[2] + 1)}
        for (ix, iy, iz), (pid, dq) in stairtemplate.template(db, style, sp['id']).items():
            wx, wy = stairtemplate.world_tile(centre(s0), x['q'], ix, iy, T)
            t = (int(round(wx / T)), int(round(wy / T)), s0[2] + iz)
            piece = by_id.get(pid.lower())
            if t not in grid or t in own or not piece or t in forced:
                continue
            q = (x['q'] + dq) % 4
            pat = kits.rotate(piece['pattern'], q)
            if any((need[t][s] == 'open' and pat[s] == 'wall') or (need[t][s] == 'door' and pat[s] != 'door') or
                   (need[t][s] == 'wall' and pat[s] == 'door') for s in kits.SIDES):
                continue
            missing = [s for s in kits.SIDES if need[t][s] == 'wall' and pat[s] != 'wall']
            if missing and (not kp['walls'] or len(_pick(kp, need[t])[2]) < len(missing)):
                continue                  # (a piece of the style's own closes more of its walls)
            forced[t] = (piece, q, missing, pat)
    import extras
    erng = extras.seeded(name)
    choice = {}
    for t, ra in sorted(grid.items()):
        if t in forced:
            choice[t] = forced[t]
            continue
        piece, q, missing, pat = _pick(kp, need[t])
        for s, way in under.get(t, ()):
            got = _pick_under(kp, need[t], s, way)
            if got and (not got[2] or kp['walls']):
                piece, q, missing, pat = got
                break
        choice[t] = (piece, q, missing, pat)
    # a room piece in a corridor, between two of the style's hall pieces (beside a side door, say): the
    # hall piece that fits as well. The game runs its hall pieces along a corridor; a room piece among
    # them brings the room's wall trim, and the ledges step up and down along it
    for t, ra in sorted(grid.items()) if has_halls else ():
        piece = choice[t][0]
        if ra not in corridor or not piece or _family(piece['id']) == 'hall' or t in forced:
            continue
        along = [nb(t, s) for s in STEP if need[t][s] == 'open' and grid.get(nb(t, s)) == ra]
        if len(along) >= 2 and all(choice[n][0] and _family(choice[n][0]['id']) == 'hall' for n in along):
            alt = _pick(kp, need[t], 'hall')
            if alt[0] is not None and _family(alt[0]['id']) == 'hall' and len(alt[2]) <= len(choice[t][2]):
                choice[t] = alt
    if _debug is not None:                 # (for the lab: what each tile needs and gets)
        _debug({'need': need, 'choice': choice, 'stairs': stair_list, 'grid': grid, 'forced': forced})
    for t, ra in sorted(grid.items()):
        piece, q, missing, pat = choice[t]
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
        # the small things the game hangs from or stands against this piece (a rope and lantern under a
        # Hlaalu side piece, a skirting along a Gold Coast wall), as often and where it does (extras.py)
        for eid, epos in extras.for_piece(db, style, piece['id'], q, cx, cy, z0 + zf(t) + piece['zmin'], erng):
            refs.append((eid, epos, []))
        if piece.get('floorless') and kp.get('slab'):
            # (a wall-and-ceiling piece with no floor of its own: the set's floor slab under it)
            refs.append((kp['slab']['id'], (cx, cy, z0 + zf(t) + kp['zmin'] - kp['slab']['zmin'], 0, 0, 0), []))
        # walls the piece doesn't have
        for s in missing:
            wall = plain_wall(kp, db)
            off = T / 2 - wall['thick'] / 2 - 2
            wx, wy = cx + STEP[s][0] * off, cy + STEP[s][1] * off
            along_y = s in 'EW'                       # an east/west wall runs north-south
            rot = 0 if along_y == wall['thin_x'] else math.pi / 2
            # its finished side into the room (many are one-sided: turned the other way, it can't be seen)
            import seethrough
            rot = seethrough.facing(db, wall['ri'], (-STEP[s][0], -STEP[s][1]), rot)
            # (the middle of the wall on the edge: some walls' models don't have their origin in the middle)
            wx, wy = _centred(db, wall['ri'], wx, wy, rot)
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
    # ---- doorways built the way the game builds them in this style: frame, door, posts on the edge

    def edge_parts(t, s, way, skip_door=False):
        th = YAW[s]
        ox, oy = centre(t)
        ox, oy = ox + STEP[s][0] * T / 2, oy + STEP[s][1] * T / 2
        pz = z0 + zf(t)
        out = []
        for pid, lx, ly, lz, lrz, psc in way['parts']:
            if skip_door and pid == way['door']:
                continue
            wx, wy = ox + lx * math.cos(th) + ly * math.sin(th), oy - lx * math.sin(th) + ly * math.cos(th)
            out.append((pid, (wx, wy, pz + lz, 0, 0, (th + lrz) % (2 * math.pi)), [], psc))
        return out

    for t, s, way in learned_edges:
        refs.extend(edge_parts(t, s, way))
    # ---- the way out: a door frame and a door, or a door against the wall
    cx, cy = centre(exit_tile)
    sx, sy = STEP[exit_side]
    door_id = None
    doors_here = _co_used(db, kp, 'DOOR', lambda k: 'load' in k or 'door' in k)
    door_id = doors_here[0] if doors_here else 'in_hlaalu_loaddoor_01'
    if exit_door:
        door_id = exit_door
    db_door = db.resolve_id(door_id)
    if db_door is None:
        raise EditError('Could not find a door to use for the way out.')
    db_door_b = mapdata.object_bounds(db, db_door) or [-5, -64, -100, 5, 64, 100]
    door_thin_x = (db_door_b[3] - db_door_b[0]) < (db_door_b[4] - db_door_b[1])
    along_y = exit_side in 'EW'
    jamb_scale = door_scale = 1.0
    learned_door = None
    if exit_how == 'learned':
        # the frame and the door exactly as the game puts them on a front door's edge in this style
        refs.extend(edge_parts(exit_tile, exit_side, exit_way, skip_door=True))
        learned_door = next(p for p in edge_parts(exit_tile, exit_side, exit_way) if p[0] == exit_way['door'])
        door_id = exit_way['door']
        db_door = db.resolve_id(door_id)
        if db_door is None:
            raise EditError('Could not find a door to use for the way out.')
        dx, dy = cx + sx * T / 2, cy + sy * T / 2
        door_scale = learned_door[3]
    elif exit_how == 'frame':
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
                # (and at least the floor piece's own doorway: a frame's hole measures small when columns
                # or carving stand in it, and a door that size leaves the doorway showing beside it)
                hole_w, hole_h = max(hole_w, opening[0] * 1.04), max(hole_h, opening[1] * 0.95)

                def fill(b):
                    """How much bigger a door must be to fill the hole (0 when it can't be measured)."""
                    dwid, dhei = max(b[3] - b[0], b[4] - b[1]), b[5] - b[2]
                    return max(hole_w / dwid, hole_h / dhei) if dwid > 1 and dhei > 1 else 0
                if not exit_door:
                    # of the doors used with this style, the one that fills the hole best when sized to it
                    # (a big arch with a small door left the void showing round it)
                    best_d = None
                    for cand in doors_here[:15]:
                        if any(w in cand.lower() for w in ('trap', 'hatch', 'cage', 'jail', 'secret', 'hidden', 'gate')):
                            continue                 # (not an ordinary standing door)
                        cri = db.resolve_id(cand)
                        cb = mapdata.object_bounds(db, cri) if cri is not None else None
                        f = fill(cb) if cb else 0
                        if f <= 0:
                            continue
                        dw, dh = max(cb[3] - cb[0], cb[4] - cb[1]), cb[5] - cb[2]
                        # (sized to cover, how far past the hole it reaches: a close fit first, and one that
                        # needs no more than the game's largest size)
                        over = max(dw * min(f, 2.0) / hole_w, dh * min(f, 2.0) / hole_h)
                        score = (f > 2.0, abs(math.log(over)) if over > 0 else 9)
                        if best_d is None or score < best_d[0]:
                            best_d = (score, cand, cri, cb)
                    if best_d:
                        door_id, db_door, db_door_b = best_d[1], best_d[2], best_d[3]
                        door_thin_x = (db_door_b[3] - db_door_b[0]) < (db_door_b[4] - db_door_b[1])
                f = fill(db_door_b)
                if f > 0:
                    door_scale = max(0.8, min(2.0, f * 1.02))
            px, py = _centred(db, small_jamb['ri'], dx, dy, rot, jamb_scale)
            refs.append((small_jamb['id'], (px, py, -small_jamb['zmin'] * jamb_scale + zf(exit_tile), 0, 0, rot), [], jamb_scale))
    else:
        # against the inside of the wall: where the floor piece's own wall stands (curved and large
        # styles have it well inside the tile's edge), or the edge where a loose wall goes
        wall_in = T / 2 - 34
        piece, q = tile_piece[exit_tile]
        pat = kits.rotate(piece['pattern'], q)
        if pat[exit_side] == 'wall' and pat.get('offset', {}).get(exit_side):
            wall_in = min(wall_in, pat['offset'][exit_side] - 26)
        dx, dy = cx + sx * wall_in, cy + sy * wall_in
    if learned_door:
        drot, dz = learned_door[1][5], learned_door[1][2]
    elif exit_how == 'entry' and exit_fit:
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
        if entrance.get('arrive'):
            out_arrival = tuple(float(v) for v in entrance['arrive'])     # (worked out by the caller)
        info = mapdata.cell_info(db, entrance['cell'])
        door_extra = [('DODT', struct.pack('<6f', *out_arrival))]
        if info and info['interior']:
            door_extra.append(('DNAM', zs(info['name'])))
        out_spot = (entrance['cell'], outside_door, (ex_, ey_, ez_, 0, 0, erz))
    if learned_door:
        pdx, pdy = learned_door[1][0], learned_door[1][1]
    elif exit_how == 'entry' and exit_fit:
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
    # the style's posts where its door frames meet walls, and posts or walls over anything the player
    # could see through where pieces don't quite meet (a round or two: a post can leave a slit beside it)
    db.sync_project()
    try:
        import fixit
        closers = set()
        # (more rounds than most places need: round a stairwell each post can leave the next slit
        # showing, and the backing walls wait until the posts are done)
        for _round in range(9):
            got = fixit.closing_pieces(db, key)
            if not got:
                break
            for pid, ppos, psc in got:
                nk = p.new_ref_key()
                editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(pid))], ppos, psc))
                if fixit.COLUMN_WORDS.search(pid.lower()):
                    closers.add(nk)
            db.sync_project()
        # each round closes what it sees, so a corner can end up with a column from each side and one
        # more over the middle: the ones that, taken away, leave nothing showing through, go again
        if closers:
            _trim_columns(db, key, c, closers)
    except Exception as e:
        print('closing the gaps:', e)
    # walking paths for the new place, in the same change
    db.sync_project()
    try:
        import pathgrid
        pathgrid.generate(db, key, note=False)
    except EditError:
        pass
    if commit:
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
            'notes': ['No proper doorway piece fitted between "%s" and "%s", so they join through an open gap.' % g for g in gaps] + stair_notes,
            '_grid': grid, '_exit_tile': (exit_tile, exit_side)}


FLOOR_TITLES = {-2: 'Lower Cellar', -1: 'Cellar', 1: 'Upstairs', 2: 'Top Floor'}


def build_house(db, name, style, rooms, doors=None, exit=None, entrance=None, lighting='normal',
                lights=True, outside_door=None, stairs=None, floors_as='auto'):
    """Build from pieces, on one floor or several. Styles with stair pieces get real stairs inside one
    place; in the others every floor is a place of its own ("Name: Upstairs", "Name: Cellar"), joined
    the way the game often does it: a door in a wall going up, a trapdoor in the floor going down to a
    cellar. Everything goes in as one change. Returns build_interior's result for the ground floor,
    plus 'cells': every place built, in order."""
    floors = sorted({int(r.get('floor') or 0) for r in rooms})
    # floors_as: 'stairs' (real stairs inside one place), 'linked' (a place per floor, joined by doors)
    # or 'auto' (stairs when the style has them)
    if floors_as == 'stairs' and len(floors) > 1 and not kits.stairs(db, style):
        raise EditError('The %s style has no stair pieces. Choose "Separate floors, joined by doors" for it.' % kits.friendly(style))
    st_info = kits.stairs(db, style)
    use_stairs = bool(st_info) and (floors_as == 'stairs' or (floors_as == 'auto' and st_info.get('proper', True)))
    if len(floors) < 2 or use_stairs:
        out = build_interior(db, name, style, rooms, doors, exit, entrance, lighting, lights, outside_door, stairs)
        out['cells'] = [{'key': out['key'], 'name': out['name'], 'floor': 0}]
        return _public(out)
    editing._require_project(db)
    if 0 not in floors:
        raise EditError('Put at least one room on the ground floor: that is where the way in is.')
    for f in range(floors[0], floors[-1]):
        if f not in floors:
            raise EditError('There is a floor with no rooms in it between the %s and the %s.' % (
                FLOOR_NAMES.get(floors[0]), FLOOR_NAMES.get(floors[-1])))
    kp = kits.kit_pieces(db, style)
    if not kp:
        raise EditError('Unknown building style "%s". Pick one from the list of styles.' % style)
    T = kp['tile']
    names = [(r.get('name') or 'Room %d' % (n + 1)).strip() for n, r in enumerate(rooms)]
    low = [n.lower() for n in names]
    floor_of = [int(r.get('floor') or 0) for r in rooms]

    def idx(ref):
        if isinstance(ref, int):
            return ref
        s = str(ref).strip().lower()
        if s not in low:
            raise EditError('There is no room called "%s".' % ref)
        return low.index(s)
    # which rooms the way between two floors joins: the one asked for, or the biggest on each floor
    wanted = {}
    for s in stairs or []:
        if not s.get('rooms'):
            continue                                   # (stairs put by hand: none here, floors are joined by doors)
        a, b = idx(s['rooms'][0]), idx(s['rooms'][1])
        if floor_of[a] > floor_of[b]:
            a, b = b, a
        wanted[floor_of[a]] = (a, b)
    biggest = lambda f: max((n for n in range(len(rooms)) if floor_of[n] == f),
                            key=lambda n: int(rooms[n].get('w', 1)) * int(rooms[n].get('h', 1)))
    # a door for going up, a trapdoor for going down, of the kinds used with this style
    learned = kits.edge_doors(db, style)
    inner = next((e['door'] for e in learned if e['door'] and e['b'] != 'out'), None) or \
        next((e['door'] for e in learned if e['door']), None)
    up_door = inner if inner and db.resolve_id(inner) is not None else 'in_hlaalu_door'
    # the way up out of a cellar: a ladder, as in the game's own cellars (a door if there's none)
    ladder = next((l for l in ('t_de_set_ladderload_03', 'ex_mh_pav_ladder_01', 'in_mh_pav_ladder', 't_imp_setkva_ladder_01')
                   if db.resolve_id(l) is not None), None)
    traps = _co_used(db, kp, 'DOOR', lambda k: 'trapdoor' in k)
    trap = traps[0] if traps else 'in_h_trapdoor_01'
    if db.resolve_id(up_door) is None or db.resolve_id(trap) is None:
        raise EditError('Could not find a door to join the floors with.')

    def floor_rooms(f):
        keep = [n for n in range(len(rooms)) if floor_of[n] == f]
        rs = [dict(rooms[n], floor=0) for n in keep]
        ds = [d for d in (doors or []) if all(floor_of[idx(r)] == f for r in d['rooms'])]
        return keep, rs, ds
    built = {}
    title = lambda f: name if f == 0 else '%s: %s' % (name, FLOOR_TITLES.get(f, 'Floor %d' % f))
    for f in [0] + [f for f in floors if f > 0] + sorted((f for f in floors if f < 0), reverse=True):
        keep, rs, ds = floor_rooms(f)
        if len(title(f).encode(ENC, 'replace')) > 63:
            raise EditError('"%s" is too long for a place name (63 characters at most): shorten the name.' % title(f))
        if f == 0:
            out = build_interior(db, name, style, rs, ds, exit, entrance, lighting, lights, outside_door, commit=False)
        else:
            parent = f - 1 if f > 0 else f + 1
            lo_f = min(f, parent)
            a, b = wanted.get(lo_f) or (biggest(lo_f), biggest(lo_f + 1))
            here, there = (b, a) if f > 0 else (a, b)
            spot = _link_spot(db, built[parent], rooms[there], T, going_down=f < 0, door=up_door if f > 0 else trap)
            out = build_interior(db, title(f), style, rs, ds, {'room': keep.index(here)},
                                 {'cell': built[parent]['key'], 'x': spot['x'], 'y': spot['y'], 'z': spot['z'],
                                  'rz': spot['rz'], 'arrive': spot['arrive']},
                                 lighting, lights, up_door if f > 0 else trap, commit=False,
                                 exit_door=ladder if f < 0 else None)
            built[parent].setdefault('_links', []).append(spot['tile'])
        out['_rooms_in'] = rs
        built[f] = out
    total = sum(len(b['_grid']) for b in built.values())
    editing.commit(db, 'Built a new %s house "%s" on %d floors (%d rooms, %d tiles)' % (
        kits.friendly(style), name, len(floors), len(rooms), total))
    out = dict(built[0])
    out['cells'] = [{'key': built[f]['key'], 'name': built[f]['name'], 'floor': f} for f in sorted(built)]
    out['floors'] = floors
    out['notes'] = out.get('notes', []) + ['Each floor is a place of its own, joined by doors%s.' % (' and a trapdoor' if floors[0] < 0 else '')]
    return _public(out)


def _trim_columns(db, key, c, closers=None, slow=5):
    """Take out again the posts and columns put in to close gaps that turn out to close nothing: first
    the ones that look spare from close by, then the whole place is looked at as it is without them,
    and any by something new that shows through (a view from across the room, up by the ceiling) go
    back, until nothing new does. (In a style whose places take longer than `slow` seconds to look
    through, they all stay.) closers: the refs to consider; None: every post or column the mod put in
    this place. Returns how many came out."""
    import time
    import fixit
    fixit.LAST_TRACE = False
    if closers is None:
        closers = {r['k'] for r in mapdata.cellmap(db, key)['refs']
                   if r.get('new') and r['k'] in c['refs'] and fixit.COLUMN_WORDS.search(r['id'].lower())}
        if not closers:
            return 0
    t0 = time.time()
    before = fixit.wall_holes(db, key)
    if time.time() - t0 > slow:
        return 0                                    # (too slow to look through again and again)
    spare = fixit.spare_columns(db, key, closers, trace=fixit.LAST_TRACE)
    if not spare:
        return 0
    boxes = {r['k']: fixit.column_box(r) for r in mapdata.cellmap(db, key)['refs'] if r['k'] in spare}
    kept = {k: c['refs'].pop(k) for k in spare if k in c['refs']}
    db.sync_project()
    same = lambda h, o: math.hypot(h[0] - o[0], h[1] - o[1]) < 12 and abs(h[2] - o[2]) < 16
    for _round in range(4):
        new = [h for h in fixit.wall_holes(db, key) if not any(same(h, o) for o in before)]
        back = set()
        for h in new:
            near = [(math.hypot((b[0] + b[3]) / 2 - h[0], (b[1] + b[4]) / 2 - h[1]), k) for k, b in boxes.items()
                    if k in kept and b and b[2] - 16 <= h[2] <= b[5] + 16]
            near = [x for x in near if x[0] < 160]
            if near:
                back.add(min(near)[1])
        if fixit.LAST_TRACE is not False:
            fixit.LAST_TRACE.append('as built, round %d: %d new holes %s, %d back, %d out' % (
                _round + 1, len(new), [tuple(round(v) for v in h) for h in new], len(back), len(kept) - len(back)))
        if not back:
            if new:
                for k in list(kept):                # (something shows that no column of these explains: all back)
                    c['refs'][k] = kept.pop(k)
                db.sync_project()
            break
        for k in back:
            c['refs'][k] = kept.pop(k)
        db.sync_project()
    return len(kept)


def _public(out):
    return {k: v for k, v in out.items() if not k.startswith('_')}


def _link_spot(db, below, room, T, going_down, door):
    """Where the door to another floor goes in a place already built: against an outside wall of the
    room for a door, on the floor in the middle of the room for a trapdoor, away from the way out and
    from other such doors. {x, y, z, rz, arrive, tile}."""
    grid = below['_grid']
    rn = next(n for n, r in enumerate(below['_rooms_in']) if r is room or (r.get('name'), r.get('x'), r.get('y')) ==
              (room.get('name'), room.get('x'), room.get('y')))
    tiles = sorted(t for t, ra in grid.items() if ra == rn)
    ex_t, ex_s = below['_exit_tile']
    taken = [ex_t] + below.get('_links', [])
    far = lambda t: min(abs(t[0] - o[0]) + abs(t[1] - o[1]) for o in taken)
    ri = db.resolve_id(door)
    b = mapdata.object_bounds(db, ri) or [-5, -64, -100, 5, 64, 100]
    if going_down:
        # a tile with room all round it if there is one, else any; as far from the way out as can be
        inside = [t for t in tiles if all(nb(t, s) in grid for s in STEP)] or tiles
        t = max(inside, key=lambda t: (far(t), -abs(t[0] - sum(x[0] for x in tiles) / len(tiles))))
        cx, cy = t[0] * T, t[1] * T
        return {'x': cx, 'y': cy, 'z': -b[2], 'rz': 0.0, 'tile': t,
                'arrive': (cx, cy - T * 0.45, 20.0, 0, 0, 0.0)}
    walls = [(t, s) for t in tiles for s in STEP if nb(t, s) not in grid and (t, s) != (ex_t, ex_s)]
    if not walls:
        raise EditError('Room "%s" has no free wall for the door upstairs. Make it a little bigger, or pick '
                        'another room for the way up.' % room.get('name'))
    t, s = max(walls, key=lambda w: (far(w[0]), -abs(w[0][0] - sum(x[0] for x in tiles) / len(tiles))))
    sx, sy = STEP[s]
    off = T / 2 - 34
    dx, dy = t[0] * T + sx * off, t[1] * T + sy * off
    thin_x = (b[3] - b[0]) < (b[4] - b[1])
    rot = 0 if (s in 'EW') == thin_x else math.pi / 2
    rot = _facing(db, ri, (-sx, -sy), rot)
    px, py = _centred(db, ri, dx, dy, rot)
    return {'x': px, 'y': py, 'z': -b[2], 'rz': rot, 'tile': t,
            'arrive': (dx - sx * 110, dy - sy * 110, 20.0, 0, 0, (YAW[s] + math.pi) % (2 * math.pi))}
