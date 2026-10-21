"""Build a new interior from scratch out of a kit's modular pieces.

Rooms are rectangles on a grid of the kit's tile size (usually 256 units). Every tile gets
the floor piece whose walls match where the room ends; doorways between rooms get the kit's
door frame; the way out gets a load door, linked to a door outside if you give a spot."""
import math
import os
import re
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
        if prefix in NOT_A_HOUSE_KIT:
            continue
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
        # the same kit dressed the way the game dresses it in a good share of its places (thin panels over
        # the walls, pilasters, floor sheets: Anvil's ashlar and grey-stone halls are the Gold Coast timber
        # kit under WallRichAddon / WallStoneAddon panels), each a style of its own right after the kit
        import dressingsurvey
        if dressingsurvey.has_panels(db, prefix):
            for n_, (d, places, _share) in enumerate(dressingsurvey.dressings(db, prefix)):
                sid = '%s@%s' % (prefix, d)
                out.append(dict(out[-1 - n_], id=sid, name=kits.friendly(sid), uses=k['uses'] - 0.5 - n_ * 0.01,
                                base=prefix, dressing=d, dressed_places=places))
    out.sort(key=lambda s: -s['uses'])
    _styles.update({'recs': db.recs, 'out': out})
    return out


_styles = {}
# Sets the game never builds a house from, so there is nothing to learn its rooms from: Vivec (large)
# is a single-hall accent in ancestral tombs and canalworks (185 places, never more than six tiles,
# no door piece, no piece with walls on three sides), and came out as one stepped bare hall.
NOT_A_HOUSE_KIT = {'in_v_l_int'}
_debug = None       # a function given build_interior's needs and choices per tile (the lab uses it)
CLOSURE = True       # lay what the game stands round a stair, from closuresurvey.py
STAIR_OPEN_LOW = False  # the room beside a stair's open side: open downstairs too (True), never (False), or by the piece's height (None).
#                         Measured (lab, two-floor test houses): walled downstairs, the see-through holes round a Common tall
#                         stairwell fall from 8 to 1, Gold Coast 4 to 3, Hlaalu 8 to 7; never worse
COLUMN_WORDS_RE = re.compile(r'post|pillar|column')
COLUMNS = True       # columns standing free in big rooms, where the game's own places of the style have them (layoutsurvey.py)
WINDOWS = True       # window props on outside walls, as often as the game's own places of the style have them (layoutsurvey.py)
ALCOVES = True       # stairs with the game's own pieces round them (the stair block), where the style's places show how
STAIR_VOID = True    # ... and the stairwell's void where the game has no floor (over the lower landing, under the upper)


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


def _stub_columns(db, kp, grid, need, choice, centre, zf, z0, T, doorway_sides, keep_clear, refs):
    """A piece taken for its wall that has a doorway on a side where the room simply carries on (the
    Common 3way next to a room's open tiles, when a door stands beside a wall) leaves its jambs' half
    pilasters standing in the middle of the floor: a half column with nothing behind it. The game's own
    places cover two such corners in three with the style's pillar (95 of 144 jamb corners in 75 Common
    stone and Gold Coast places); here every one that stands in open floor gets the style's most used
    pillar, so no half column stands free. A corner where a wall ends or a real doorway stands is left
    to its wall end or jambs (and to the gap fixes); one with a column already is left alone."""
    import fixit
    narrow = fixit._narrow_pieces(db, kp)
    if not narrow:
        return
    rid, ri, b = narrow[0]
    done = set()
    for t, (piece, _q, _missing, pat) in choice.items():
        if piece is None or t in keep_clear:
            continue
        for s in kits.SIDES:
            if pat[s] != 'door' or need[t][s] != 'open' or (t, s) in doorway_sides:
                continue
            dx, dy = STEP[s]
            for k in (-1, 1):
                ox, oy = dx * 0.5 + k * dy * 0.5, dy * 0.5 + k * dx * 0.5      # the corner, in tiles from the middle
                sx, sy = (1 if ox > 0 else -1), (1 if oy > 0 else -1)
                around = [(t[0] + ax, t[1] + ay, t[2]) for ax in (0, sx) for ay in (0, sy)]
                if any(a not in grid or a in keep_clear or a not in choice or choice[a][0] is None for a in around):
                    continue                                 # (the building's edge, or a stairwell: not open floor)
                clear = True
                for a in around:
                    apat = choice[a][3]
                    for s2 in kits.SIDES:
                        # the two sides of this tile that touch the corner (the corner is half a tile
                        # from the tile's middle, on the side towards it)
                        ddx, ddy = STEP[s2]
                        if ((ddx and (ddx > 0) == (a[0] < t[0] + ox)) or (ddy and (ddy > 0) == (a[1] < t[1] + oy))) and \
                                (apat[s2] == 'wall' or (apat[s2] == 'door' and (need[a][s2] == 'door' or (a, s2) in doorway_sides))):
                            clear = False
                if not clear:
                    continue
                cx, cy = centre(t)
                wx, wy = cx + ox * T, cy + oy * T
                spot = (int(round(wx / 8)), int(round(wy / 8)), t[2])
                if spot in done:
                    continue
                done.add(spot)
                # (one on this floor: a storey is 236 or more, so one 100 up or down is the floor above or below)
                if any(COLUMN_WORDS_RE.search(r_[0].lower()) and math.hypot(r_[1][0] - wx, r_[1][1] - wy) < 60 and
                       abs(r_[1][2] - (z0 + zf(t))) < 100 for r_ in refs):
                    continue
                px, py = _centred(db, ri, wx, wy, 0)
                refs.append((rid, (px, py, z0 + zf(t) + piece['zmin'] - b[2], 0, 0, 0), []))


def _stair_edge_columns(db, kp, grid, choice, stair_list, centre, zf, z0, T, refs):
    """A pillar where a room's wall ends at the edge of the stairwell: on the floor the stairs come out
    on, the tiles the stairwell takes have no room piece, so the wall of the piece beside them stops
    with a naked end face, and up by the ceiling the piece's rim meets nothing (the user's Common stone
    house: a bare wall edge beside the stairs upstairs, and a slit at that corner's ceiling). The style's
    pillar stands on that corner, as the game stands posts where its stairs meet a room's walls. Only
    corners on the stairwell's edge (one or two tiles missing round the corner, one of them the stairs'):
    the stairs' outer corner against the void is the stair piece's own."""
    import fixit
    narrow = fixit._narrow_pieces(db, kp)
    # (only in styles whose own places stand posts at a fair share of their corners, the Common and Gold
    # Coast sets; in the others the stair pieces close their own edges, and a pillar would be one the game
    # never has there)
    if not narrow or not stair_list or not fixit.uses_posts(db, kp.get('prefix')):
        return
    rid, ri, b = narrow[0]
    well = set()
    feet = set()             # the two corners at the foot of each flight: the stair piece's own side walls end there
    for x in stair_list:
        for s in x['tiles']:
            well.add((s[0], s[1], s[2]))
            well.add((s[0], s[1], s[2] + 1))
        s0 = x['tiles'][0]
        ddx, ddy = STEP[OPPOSITE[x['up']]]
        for k in (-1, 1):
            feet.add((int(round((s0[0] + ddx * 0.5 + k * ddy * 0.5) * 2)), int(round((s0[1] + ddy * 0.5 + k * ddx * 0.5) * 2)), s0[2]))
    done = set()
    for (sx, sy, lv) in sorted(well):
        for cx_, cy_ in ((sx - 0.5, sy - 0.5), (sx + 0.5, sy - 0.5), (sx - 0.5, sy + 0.5), (sx + 0.5, sy + 0.5)):
            key = (int(round(cx_ * 2)), int(round(cy_ * 2)), lv)
            if key in done:
                continue
            done.add(key)
            around = [(int(math.floor(cx_ + 0.5 + ddx)), int(math.floor(cy_ + 0.5 + ddy))) for ddx, ddy in ((0, 0), (-1, 0), (0, -1), (-1, -1))]
            have = [(ax, ay, lv) for (ax, ay) in around if (ax, ay, lv) in grid and choice.get((ax, ay, lv), (None,))[0] is not None]
            missing = [(ax, ay) for (ax, ay) in around if (ax, ay, lv) not in grid]
            # (three missing: the stairs' outer corner, where the room's wall ends against the stair
            # piece's side; the user's "another missing half column" by a Gold Coast flight was one)
            if not have or not 1 <= len(missing) <= 3 or not any((ax, ay, lv) in well for (ax, ay) in missing):
                continue
            # the wall lines ending at this corner, from the pieces round it (a wall seen from both of
            # two tiles is one line)
            lines = set()
            for a in have:
                pat = choice[a][3]
                for s2 in kits.SIDES:
                    ddx, ddy = STEP[s2]
                    touches = (ddx and (ddx > 0) == (a[0] < cx_)) or (ddy and (ddy > 0) == (a[1] < cy_))
                    if touches and pat[s2] in ('wall', 'door'):
                        lines.add(('v', a[0] + ddx * 0.5, 'n' if a[1] > cy_ else 's') if ddx else ('h', a[1] + ddy * 0.5, 'e' if a[0] > cx_ else 'w'))
            # (one wall ending here; or none, at the foot of the flight, where the stair piece's own side
            # wall stops in open floor with nothing to meet it: the user's "missing column again" at a
            # Common tall stair's foot. Two or more: walls meeting, a corner of their own)
            if key not in feet and len(lines) != 1:
                continue
            t = have[0]
            cx, cy = centre(t)
            wx, wy = cx + (cx_ - t[0]) * T, cy + (cy_ - t[1]) * T
            zt = z0 + zf(t)
            if any(COLUMN_WORDS_RE.search(r_[0].lower()) and math.hypot(r_[1][0] - wx, r_[1][1] - wy) < 60 and abs(r_[1][2] - zt) < 100 for r_ in refs):
                continue
            px, py = _centred(db, ri, wx, wy, 0)
            refs.append((rid, (px, py, zt + choice[t][0]['zmin'] - b[2], 0, 0, 0), []))


def _columns_and_windows(db, style, kp, grid, rooms, need, keep_clear, doorway_sides, rail_edges, floors_all, centre, zf, rng, refs, has_walls=False):
    """Columns standing free in rooms of nine tiles or more, where the game stands them in at least half
    its big rooms of this style (Gold Coast, Common, Velothi): at the inner corners of the tile grid a
    whole tile in from the outside walls, one tile apart (Velothi: at the centre of the tiles along the
    walls), as many per nine tiles as the game has. And the game's window props on true outside walls
    (nothing beyond on any floor), in the kinds of room the game windows (bedrooms, studies, shops,
    taverns; halls and storerooms never), as often per wall side as the game's places have them, standing
    out from the wall and up from the floor as the game stands them. Never on a doorway side, a railing,
    a stair tile or an alcove tile; one window to a tile. Measured in the lab (two-storey test houses in
    six styles): no see-through holes added in any style."""
    import furnish
    import layoutsurvey
    import variantsurvey
    T = kp['tile']
    purposes = [furnish.purpose_for(r.get('name') or '', int(r.get('w', 1)) * int(r.get('h', 1)), int(r.get('w', 1)), int(r.get('h', 1)))
                for r in rooms]
    if COLUMNS:
        col = layoutsurvey.columns(db, style)
        cb = mapdata.object_bounds(db, db.resolve_id(col[0])) if col else None
        if col and cb:
            cid, where, per9 = col
            # (by the column's body, not its origin: some have their origin at a corner of the base)
            obx, oby = (cb[0] + cb[3]) / 2.0, (cb[1] + cb[4]) / 2.0
            for n, _r in enumerate(rooms):
                tiles = {t for t, ra in grid.items() if ra == n}
                if len(tiles) < 9 or purposes[n] in ('hall',):
                    continue
                cells_ = {(t[0], t[1]) for t in tiles}
                lv = min(t[2] for t in tiles)
                clear = lambda t: t not in keep_clear and all((t, s) not in doorway_sides for s in STEP)
                spots = []
                if where == 'corner':
                    # the grid's inner corners: all four tiles round the corner in the room; nearest the
                    # outside walls first (the game's columns stand a tile in from the walls)
                    for (x, y) in cells_:
                        four = [(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)]
                        if all(c in cells_ and clear((c[0], c[1], lv)) for c in four):
                            ring = min(1 if any((c[0] + dx, c[1] + dy) not in cells_ for dx, dy in STEP.values()) else 2 for c in four)
                            spots.append((ring, x, y, ((x + 0.5) * T, (y + 0.5) * T, (x, y, lv))))
                else:
                    # the centre of the tiles along the walls (not the corner tiles, not doorway tiles)
                    for (x, y) in cells_:
                        t = (x, y, lv)
                        walls = [s for s in STEP if need[t][s] == 'wall']
                        if len(walls) == 1 and clear(t):
                            spots.append((1, x, y, (x * T, y * T, t)))
                spots.sort()
                cap = max(1, int(round(per9 * len(tiles) / 9.0)))
                if len(spots) > cap:
                    spots = [spots[(k * len(spots)) // cap] for k in range(cap)]
                for _ring, _x, _y, (sx, sy, t) in spots:
                    refs.append((cid, (sx - obx, sy - oby, -cb[2] + zf(t), 0, 0, 0), []))
    if WINDOWS:
        rate, by_kind = layoutsurvey.window_rate(db, style)
        props = layoutsurvey.window_props(db, style)
        # (not a prop the extras already hang from this style's pieces, as Mournhold's window is)
        hung = {oid.lower() for d in variantsurvey.hangings(db, style).values() for oid, _s, _o in d['with']}
        all_n = float(sum(p['n'] for p in props)) + float(sum(w['n'] for w in (layoutsurvey.window_walls(db, style) if has_walls else [])))
        props = [p for p in props if p['id'].lower() not in hung]
        if rate and props:
            import seethrough
            total = float(sum(p['n'] for p in props))
            rate *= total / max(1.0, all_n)       # (the share of the game's windows that are these props)
            for t, ra in sorted(grid.items()):
                factor = layoutsurvey.WINDOW_KINDS.get(purposes[ra], 0)
                if not factor or t in keep_clear:
                    continue
                for s in kits.SIDES:
                    if need[t][s] != 'wall' or (t, s) in doorway_sides or (t, s) in rail_edges:
                        continue
                    bx, by = t[0] + STEP[s][0], t[1] + STEP[s][1]
                    if any((bx, by, f) in grid for f in floors_all):
                        continue                       # (a wall with another room beyond, on some floor)
                    if rng.random() > min(0.5, rate * factor):
                        continue
                    pick = rng.random() * total
                    prop = props[-1]
                    for p in props:
                        pick -= p['n']
                        if pick <= 0:
                            prop = p
                            break
                    cx, cy = centre(t)
                    wx, wy = cx + STEP[s][0] * prop['out'], cy + STEP[s][1] * prop['out']
                    th = YAW[s]
                    rot = (th + prop['turn'] * math.pi / 2) % (2 * math.pi)
                    if prop['turn_share'] < 0.5:
                        # (the game turns it every which way: its finished side into the room)
                        rot = seethrough.facing(db, db.resolve_id(prop['id']), (-STEP[s][0], -STEP[s][1]), rot)
                    refs.append((prop['id'], (wx, wy, zf(t) + prop['z'], 0, 0, rot), []))
                    break


def _kit_record(db, kp, want):
    """The kit's most used record of a kind (dressingsurvey.kind_of: 'sheet', 'ceiling'...), skipping
    ids with any of the words in want[1]: (id, ri, box) or None."""
    import dressingsurvey
    T, H = kp['tile'], kp['height']
    best = None
    for ri in kp['ris']:
        low = db.recs[ri][1].lower()
        if any(w in low for w in want[1]):
            continue
        b = mapdata.object_bounds(db, ri)
        if b and dressingsurvey.kind_of(low, b, T, H) == want[0]:
            u = kits.game_uses(db, low)
            if best is None or u > best[3]:
                best = (db.recs[ri][1], ri, b, u)
    return best[:3] if best else None


def _tall_wall(db, kp):
    """The style's loose wall two storeys tall (Gold Coast's Wall_04, 30 of the game's places: the outer
    side of a two-storey hall), as a wall item like those in kp['walls'], or None."""
    T, H = kp['tile'], kp['height']
    best = None
    for ri in kp['ris']:
        low = db.recs[ri][1].lower()
        if 'wall' not in low or any(w in low for w in ('addon', 'window', 'door', 'shf', 'alc')):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        thin, long_ = min(w, d), max(w, d)
        if thin <= T * 0.35 and T * 0.85 <= long_ <= T * 1.15 and 1.8 * H <= h <= 2.25 * H:
            item = {'id': db.recs[ri][1], 'ri': ri, 'uses': kits.game_uses(db, low), 'thin_x': w < d, 'thick': thin,
                    'zmin': b[2], 'width': long_}
            if best is None or item['uses'] > best['uses']:
                best = item
    return best


def _loose_wall_ref(db, wall, cx, cy, s, floor_z, T):
    """A loose wall on side s of the tile centred (cx, cy), its finished side into the room: the same
    placing as build_interior's loose walls."""
    import seethrough
    off = T / 2 - wall['thick'] / 2 - 2
    wx, wy = cx + STEP[s][0] * off, cy + STEP[s][1] * off
    rot = 0 if (s in 'EW') == wall['thin_x'] else math.pi / 2
    rot = seethrough.facing(db, wall['ri'], (-STEP[s][0], -STEP[s][1]), rot)
    wx, wy = _centred(db, wall['ri'], wx, wy, rot)
    return (wall['id'], (wx, wy, -wall['zmin'] + floor_z, 0, 0, rot), [])


def _void_corners(wells, voids):
    """The corner points of a hall's opening on both storeys ((i, j, floor): the point at ((i - .5) T,
    (j - .5) T)), those on the opening's edge only (not points with the opening all round them)."""
    cols = {(t[0], t[1]) for t in wells} | {(v[0], v[1]) for v in voids}
    levels = sorted({t[2] for t in wells} | {v[2] for v in voids})
    pts = set()
    for (x, y) in cols:
        for cx_ in (0, 1):
            for cy_ in (0, 1):
                around = [(x + cx_ - 1 + dx, y + cy_ - 1 + dy) for dx in (0, 1) for dy in (0, 1)]
                if not all(a in cols for a in around):
                    for lv in levels:
                        pts.add((x + cx_, y + cy_, lv))
    return pts


def _has_column(refs, wx, wy, zt):
    return any(COLUMN_WORDS_RE.search(str(r_[0]).lower()) and math.hypot(r_[1][0] - wx, r_[1][1] - wy) < 60 and abs(r_[1][2] - zt) < 100
               for r_ in refs)


def _lay_wells(db, style, dressing, kp, grid, need, wells, voids, gallery_edges, stair_list, centre, zf, z0, T, H, refs, loose_at):
    """A two-storey hall the way the game's Gold Coast halls are built (dressingsurvey.py, 61 wells in its
    places): under the opening a floor sheet and no tile (the well), over it the kit's ceiling slab at
    the top of the upper storey (the void), loose walls on the sides that face nothing (the kit's
    two-storey wall where both storeys do), the kit's pillar at every corner of the opening on both
    storeys (the arcade of Anvil's guild of mages), and along the gallery's edge upstairs the railing
    pieces the game stands there (a fascia at the floor's edge and the balustrade on it)."""
    import dressingsurvey
    sheet = _kit_record(db, kp, ('sheet', ('tiles',))) or _kit_record(db, kp, ('sheet', ()))
    ceiling = _kit_record(db, kp, ('ceiling', ()))
    tall = _tall_wall(db, kp)
    wall = plain_wall(kp, db) if kp['walls'] else None
    # the hall's parts from this dressing's rules, else from any dressing of the kit that shows them
    rule_sets = [r for r in (dressingsurvey.rules(db, style, d) for d in ([dressing] if dressing else []) + [d_ for d_ in dressingsurvey.survey(db, style) if d_ != dressing]) if r]
    rails = max((r['rails'] for r in rule_sets), key=len, default=[])
    pillar = next((r['pillar']['well_id'] or r['pillar']['id'] for r in rule_sets if r['pillar']['well_id'] or r['pillar']['id']), None)
    if not pillar:
        import layoutsurvey
        col = layoutsurvey.columns(db, style)
        pillar = col[0] if col else None
    for t in sorted(wells):
        cx, cy = centre(t)
        fz = z0 + zf(t)
        if sheet:
            refs.append((sheet[0], (cx, cy, fz - sheet[2][2], 0, 0, 0), []))
        v = (t[0], t[1], t[2] + 1)
        for s in STEP:
            below_wall = need[t][s] == 'wall' and not _across_stairs(stair_list, t, s)
            above = nb(v, s)
            above_nothing = v in voids and above not in grid and above not in voids and not _across_stairs(stair_list, v, s)
            if not wall:
                continue
            if below_wall and above_nothing and tall:
                refs.append(_loose_wall_ref(db, tall, cx, cy, s, fz, T))
                loose_at.append((t, s, zf(t), 2, tall))
            elif below_wall:
                refs.append(_loose_wall_ref(db, wall, cx, cy, s, fz, T))
                loose_at.append((t, s, zf(t), 1, wall))
                if above_nothing:
                    refs.append(_loose_wall_ref(db, wall, cx, cy, s, fz + H, T))
                    loose_at.append((v, s, zf(v), 1, wall))
            elif above_nothing:
                refs.append(_loose_wall_ref(db, wall, cx, cy, s, fz + H, T))
                loose_at.append((v, s, zf(v), 1, wall))
    for v in sorted(voids):
        cx, cy = centre(v)
        if ceiling:
            refs.append((ceiling[0], (cx, cy, z0 + zf(v), 0, 0, 0), []))
        if (v[0], v[1], v[2] - 1) not in wells:
            # (an opening over a stair's tile, or a room's tile that the stairs took: the sides that face
            # nothing still want a wall on this storey)
            for s in STEP:
                above = nb(v, s)
                if wall and above not in grid and above not in voids and not _across_stairs(stair_list, v, s):
                    refs.append(_loose_wall_ref(db, wall, cx, cy, s, z0 + zf(v), T))
                    loose_at.append((v, s, zf(v), 1, wall))
    if pillar:
        pri = db.resolve_id(pillar)
        cb = mapdata.object_bounds(db, pri) if pri is not None else None
        if cb:
            obx, oby = (cb[0] + cb[3]) / 2.0, (cb[1] + cb[4]) / 2.0
            for (i, j, lv) in sorted(_void_corners(wells, voids)):
                wx, wy = (i - 0.5) * T, (j - 0.5) * T
                zt = z0 + lv * H
                if _has_column(refs, wx, wy, zt):
                    continue
                refs.append((pillar, (wx - obx, wy - oby, zt - cb[2], 0, 0, 0), []))
    for (t, s) in gallery_edges:
        cx, cy = centre(t)
        for rid, _share, canon in rails:
            refs.append((rid, dressingsurvey.place(canon, cx, cy, z0 + zf(t), s), []))


def _dress(db, style, dressing, kp, grid, need, choice, tile_piece, refs, centre, zf, z0, T, H, loose_at, doorway_sides,
           windowed, stair_tiles, wells, voids, rooms, rng):
    """Lay the dressing over a built house, as the game's dressed places have it (dressingsurvey.rules):
    a panel over every wall of the tiles' own (the game: 80% of walled sides in its ashlar places, 54% in
    the grey stone ones, the variants in the game's shares; every wall here, a bare timber wall among
    ashlar looking like a mistake), the same panels over the loose walls, pushed in to the wall's face;
    arches across the open joins between two tiles of a room at the game's share; the beam at the ceiling
    across joins and doorways at its shares; the floor sheet over whole rooms at its share of tiles; the
    pilaster at the corner points where walls meet (two walls: 78% in the ashlar places, 62% stone; a wall
    ending: 81% / 74%), never where a column stands already, nor at the stairs' or the hall opening's
    corners (those have their own); and the kit's rich door frames and jambs in place of the plain ones."""
    import dressingsurvey
    from collections import Counter
    rules = dressingsurvey.rules(db, style, dressing)
    if not rules:
        return
    place = dressingsurvey.place
    boxes = {}

    def box(pid):
        if pid not in boxes:
            ri = db.resolve_id(pid)
            boxes[pid] = mapdata.object_bounds(db, ri) if ri is not None else None
        return boxes[pid]

    def pick(lst):
        total = sum(x[1] for x in lst)
        r = rng.random() * total
        for x in lst:
            r -= x[1]
            if r <= 0:
                return x
        return lst[-1]
    panels = rules['panels']
    if panels:
        for t, (piece, q) in sorted(tile_piece.items()):
            if t in wells:
                continue
            pat = kits.rotate(piece['pattern'], q)
            cx, cy = centre(t)
            fz = z0 + zf(t)
            for s in kits.SIDES:
                if pat[s] == 'wall' and (t, s) not in windowed:
                    pid, _sh, canon = pick(panels)
                    refs.append((pid, place(canon, cx, cy, fz, s), []))
        lst = rules['loose_panels'] or panels
        for (t, s, fz_, storeys, wall) in loose_at:
            cx, cy = centre(t)
            for k in range(storeys):
                pid, _sh, canon = pick(lst)
                b = box(pid)
                if not b:
                    continue
                # (the panel's plane, from its origin; the wall's face into the room; the panel a hair inside the wall)
                plane = max(abs(b[0]), abs(b[3])) if (b[3] - b[0]) < (b[4] - b[1]) else max(abs(b[1]), abs(b[4]))
                face = T / 2 - wall['thick'] - 2
                c2 = dict(canon, x=canon['x'] + max(0.0, plane - (face - 1)))
                refs.append((pid, place(c2, cx, cy, z0 + fz_ + k * H, s), []))
    arches, beam = rules['arches'], rules['beam']
    for t in sorted(grid):
        if t in wells or t in stair_tiles:
            continue
        cx, cy = centre(t)
        fz = z0 + zf(t)
        for s in ('N', 'E'):
            n_ = nb(t, s)
            if n_ not in grid or n_ in wells or grid[n_] != grid[t] or need[t][s] != 'open' or need[n_][OPPOSITE[s]] != 'open':
                continue
            for pid, sh_open, _sh_door, canon in arches:
                if rng.random() < sh_open:
                    refs.append((pid, place(canon, cx, cy, fz, s), []))
                    break
            if beam and rng.random() < beam[1]:
                refs.append((beam[0], place(beam[3], cx, cy, fz, s), []))
    if beam:
        for (t, s) in sorted(doorway_sides):
            n_ = nb(t, s)
            if t not in grid or (t, s) in windowed or t in wells or ((n_, OPPOSITE[s]) in doorway_sides and (n_, OPPOSITE[s]) < (t, s)):
                continue
            if rng.random() < beam[2]:
                cx, cy = centre(t)
                refs.append((beam[0], place(beam[3], cx, cy, z0 + zf(t), s), []))
    if rules['floor']:
        fid, share = rules['floor']
        for n_, _r in enumerate(rooms):
            if rng.random() >= share:
                continue
            for t, ra in sorted(grid.items()):
                if ra == n_:
                    cx, cy = centre(t)
                    refs.append((fid, (cx, cy, z0 + zf(t) + (0.5 if t in wells else 0.2), 0, 0, 0), []))
    pil = rules['pillar']
    if pil['id'] and (pil['corner1'] or pil['corner2'] or pil['inner']):
        cb = box(pil['id'])
        if cb:
            obx, oby = (cb[0] + cb[3]) / 2.0, (cb[1] + cb[4]) / 2.0
            corner = Counter()
            for t in grid:
                x, y, f = t
                for s in STEP:
                    if need[t][s] not in ('wall', 'door'):
                        continue
                    pts = {'N': ((x, y + 1), (x + 1, y + 1)), 'S': ((x, y), (x + 1, y)), 'E': ((x + 1, y), (x + 1, y + 1)), 'W': ((x, y), (x, y + 1))}[s]
                    for (i, j) in pts:
                        corner[(i, j, f)] += 1
            # the points inside a room with all four tiles round them: free columns in rows, where the
            # game's places have them (the chapel's halls), grouped as the game groups them there
            inner = {}
            if pil['inner']:
                for t in grid:
                    x, y, f = t
                    for cx_ in (0, 1):
                        for cy_ in (0, 1):
                            pt = (x + cx_, y + cy_, f)
                            around = [(x + cx_ - 1 + dx, y + cy_ - 1 + dy, f) for dx in (0, 1) for dy in (0, 1)]
                            if pt not in corner and pt not in inner and all(a in grid and grid[a] == grid[t] and a not in wells for a in around):
                                inner[pt] = True
            skip = _void_corners(wells, voids)
            for st in stair_tiles:
                for lv in (st[2], st[2] + 1):
                    for cx_ in (0, 1):
                        for cy_ in (0, 1):
                            skip.add((st[0] + cx_, st[1] + cy_, lv))
            group = pil.get('inner_group') or [(pil['id'], 0)]
            for (i, j, f), n_ in sorted(list(corner.items()) + [(pt, 0) for pt in inner]):
                if (i, j, f) in skip:
                    continue
                if rng.random() >= (pil['inner'] if n_ == 0 else pil['corner2'] if n_ >= 2 else pil['corner1']):
                    continue
                wx, wy = (i - 0.5) * T, (j - 0.5) * T
                zt = z0 + f * H
                if _has_column(refs, wx, wy, zt):
                    continue
                if n_ == 0:
                    for gid, gq in group:
                        gb = box(gid)
                        if not gb:
                            continue
                        # (each of the group by its own body, turned as the game turns it, round the point)
                        bx_, by_ = (gb[0] + gb[3]) / 2.0, (gb[1] + gb[4]) / 2.0
                        rz = gq * math.pi / 2
                        ox_, oy_ = bx_ * math.cos(rz) + by_ * math.sin(rz), -bx_ * math.sin(rz) + by_ * math.cos(rz)
                        refs.append((gid, (wx - ox_, wy - oy_, zt - gb[2], 0, 0, rz), []))
                else:
                    refs.append((pil['id'], (wx - obx, wy - oby, zt - cb[2], 0, 0, 0), []))
    swaps = rules['jambs']
    if swaps:
        for i, r_ in enumerate(refs):
            low = str(r_[0]).lower()
            if low in swaps:
                refs[i] = (swaps[low],) + tuple(r_[1:])


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


def _alcove_shape(kp, piece, tpl, void=()):
    """How the game stands a one-tile stair of this style: the pieces at the tiles round it on the floor
    it climbs from (level 0) and the floor it comes out on (level 1), from its template by floors
    (stairtemplate.floors). Indoril's Room_Stair_H_01 has a Hall_Corner at either end, turned to face
    each other, and a Room_Side walled towards it; Hlaalu's hall_stairsl stands in a two-by-three
    stairwell of hall_corner_01 pieces, two beside its foot downstairs and two beside its head
    upstairs, their walls outward. In the piece's own frame: {'tiles': {(ix, iy, level): (pattern
    turned as the game turns it, piece id)}, 'ends': [low end offset, high end offset], 'void': the
    spots over or under those pieces where the game mostly has no floor at all (stairtemplate.voids:
    the stairwell the stair climbs through)}, or None when the template shows nothing next to the
    stair (styles with no template, or whose stairs stand free)."""
    by_id = {p['id'].lower(): p for p in kp['pieces']}
    tiles = {}
    for (ix, iy, lv), (pid, dq) in tpl.items():
        p = by_id.get(pid.lower())
        if p and (ix, iy) != (0, 0) and lv in (0, 1) and max(abs(ix), abs(iy)) <= 2:
            tiles[(ix, iy, lv)] = (kits.rotate(p['pattern'], dq), p['id'])
    if len(tiles) < 2 or not any(abs(k[0]) + abs(k[1]) == 1 for k in tiles):
        return None
    lo = STEP[piece['low']]
    return {'tiles': tiles, 'ends': [(lo[0], lo[1], 0), (-lo[0], -lo[1], 1)],
            'void': {k for k in void if (k[0], k[1], 1 - k[2]) in tiles} if STAIR_VOID else set()}


def _turn(k, q):
    """A template offset (ix, iy, level) turned q quarter turns, in whole tiles (what
    stairtemplate.world_tile does with a tile of 1, without the trigonometry)."""
    ix, iy = k[0], k[1]
    dx, dy = ((ix, iy), (iy, -ix), (-ix, -iy), (-iy, ix))[q % 4]
    return (dx, dy, k[2])


def _alcove(grid, used, piece, shape, s0, up, f, g):
    """A one-tile stair placed the way the game places it (see _alcove_shape): the tiles round it on
    its two floors get the needs the game's own pieces there have, walls, arches and all: the stair
    block. A tile the game's pieces close off from the room (walls every side that faces the room) is
    taken out of the room for the checks (the room must stay in one piece); the tile at the foot and
    the one at the head are floor (the room's, or a landing joined to the room beside). A block
    piece's wall through the room (the room goes on past the stairwell) is a cut. Returns None, or
    {'carve', 'land', 'lo', 'hi', 'needs': {tile: {side: need}}, 'vcarve' (the tiles out of the room's
    floor for the checks), 'cuts', 'open' (the stair's open sides, world), 'block' (its tiles)}."""
    down = OPPOSITE[up]
    q = (kits.SIDES.index(down) - kits.SIDES.index(piece['low'])) % 4
    sxy = (s0[0], s0[1])
    if sxy in used:
        return None
    # (the shape turned as the stair is turned, worked out once per quarter turn: this is asked for
    # at every spot on the plan, for every piece and way up)
    turned = shape.setdefault('_turned', {}).get(q)
    if turned is None:
        turned = shape['_turned'][q] = {
            'tiles': {_turn(k, q): (kits.rotate(pat, q), pid) for k, (pat, pid) in shape['tiles'].items()},
            'ends': [_turn(k, q) for k in shape['ends']], 'void': [_turn(k, q) for k in shape['void']]}
    world = lambda k: (sxy[0] + k[0], sxy[1] + k[1], f + k[2])
    lo, hi = world(turned['ends'][0]), world(turned['ends'][1])
    # (the game's pieces need floor to stand on: two of the block's tiles at least, the rooms' or the
    # two landings; most spots on the plan fail this and are done with here)
    if sum(1 for k in turned['tiles'] if world(k) in grid) + sum(1 for t in (lo, hi) if t not in grid and any(nb(t, s) in grid for s in STEP)) < 2:
        return None
    block = {world(k): v for k, v in turned['tiles'].items()}
    if any(t[:2] in used for t in list(block) + [lo, hi]):
        return None
    carve = [(sxy[0], sxy[1], lv) for lv in (f, g) if (sxy[0], sxy[1], lv) in grid]
    # (the stairwell's void: over the lower landing, under the upper one, where the game has no floor)
    carve += [t for t in (world(k) for k in turned['void']) if t in grid and t not in (lo, hi)]
    # the foot and the head: floor to step from and onto (a landing joined to the room beside it)
    land = []
    for t in (lo, hi):
        if t in grid:
            continue
        beside = [nb(t, s) for s in STEP if nb(t, s) in grid and nb(t, s) not in carve and nb(t, s)[:2] != sxy]
        if not beside:
            return None
        land.append((t, grid[beside[0]]))
    landing = {t: r for t, r in land}
    # (the game's pieces only where there is floor to lay them on: the rooms', or those landings)
    block = {t: v for t, v in block.items() if (t in grid and t not in carve) or t in landing}
    if len(block) < 2:
        return None
    room_of = lambda t: landing.get(t) if t in landing else grid.get(t) if t not in carve else None
    # the stair's open sides: floor beside them on both floors, else closed by what the game stands
    # over the stairwell (kits._stair_cap), when the style has that
    rot_open = []
    for o in piece['open']:
        ws = kits.SIDES[(kits.SIDES.index(o) + q) % 4]
        if all(room_of(nb((sxy[0], sxy[1], lv), ws)) is not None for lv in (f, g)):
            rot_open.append(ws)
        elif not piece.get('cap'):
            return None
    needs, cuts, walled = {}, 0, []

    def setn(t, s, v):
        needs.setdefault(t, {})[s] = v
    for t, (pat, _pid) in block.items():
        R = room_of(t)
        off = True
        for s in STEP:
            n_ = nb(t, s)
            if n_[:2] == sxy:
                setn(t, s, 'wall' if pat[s] == 'wall' else 'open')
                continue
            if n_ in block:
                setn(t, s, pat[s] if pat[s] in ('wall', 'door') else 'open')
                continue
            same = room_of(n_) == R and n_ in grid and n_ not in carve
            if pat[s] == 'wall':
                setn(t, s, 'wall')
                if same:
                    setn(n_, OPPOSITE[s], 'wall')
                    cuts += 1
            elif same:
                off = False
                if pat[s] == 'door':
                    setn(t, s, 'door')
                    setn(n_, OPPOSITE[s], 'door')
        if off and t in grid:
            walled.append(t)
    return {'carve': carve, 'land': land, 'lo': lo, 'hi': hi, 'needs': needs, 'vcarve': carve + walled,
            'cuts': cuts, 'open': rot_open, 'block': set(block)}


def _carve_ctx(grid, doors_):
    """What _carve_check looks up again and again while the stairs' spots are weighed (the grid
    doesn't change meanwhile): each room's tiles, and for each pair of rooms that want a doorway the
    edges they share."""
    rooms = {}
    for t, r in grid.items():
        rooms.setdefault(r, set()).add(t)
    pairs, keep_tiles = doors_
    edges = {}
    for a_, b_ in pairs:
        edges[(a_, b_)] = [(t_, nb(t_, s_)) for t_ in rooms.get(a_, ()) for s_ in STEP if grid.get(nb(t_, s_)) == b_]
    return {'rooms': rooms, 'edges': edges, 'keep': set(keep_tiles)}


def _carve_check(grid, carve, doors_, ends=(), ctx=None):
    """Whether these tiles can be taken out of their rooms for stairs: never all of a room, the room
    must stay in one piece, and not the last of the wall two rooms share that want a doorway in it (or
    a doorway's own tiles, when the plan puts it in an exact spot). Returns how many nooks it leaves
    (tiles of the room walled on three sides: the game's own places almost never have one beside their
    stairs, see stairsurvey.py; the tiles at the stair's foot and head, `ends`, open onto it), or None
    when it can't be done. ctx: _carve_ctx(grid, doors_), when the same grid is asked about often."""
    if ctx is None:
        ctx = _carve_ctx(grid, doors_)
    cset = set(carve)
    conn = ctx.setdefault('conn', {})
    for room in {grid[c] for c in carve}:
        # (many spots carve the same tiles from a room: whether it stays in one piece is remembered)
        k = (room, frozenset(cset & ctx['rooms'][room]))
        ok = conn.get(k)
        if ok is None:
            left = ctx['rooms'][room] - cset
            ok = conn[k] = len(left) >= 2 and _connected(left)
        if not ok:
            return None
    if cset & ctx['keep']:
        return None
    touched = {grid[c] for c in carve}
    for (a_, b_), edges in ctx['edges'].items():
        if a_ not in touched and b_ not in touched:
            continue
        if not any(t_ not in cset and n_ not in cset for t_, n_ in edges):
            return None
    nooks = 0
    for c in carve:
        for s_ in STEP:
            t_ = nb(c, s_)
            if t_ in grid and t_ not in carve and grid[t_] == grid[c]:
                joined = sum(1 for s2 in STEP if nb(t_, s2) in grid and nb(t_, s2) not in carve
                             and grid[nb(t_, s2)] == grid[t_]) + (t_ in ends)
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


def _pin_of(want):
    """Where the stairs were put by hand, as (x, y, up), or None."""
    at = want.get('at')
    if not at:
        return None
    aup = str(at.get('up') or 'N').upper()
    return int(at['x']), int(at['y']), aup if aup in kits.SIDES else 'N'


def _stair_candidates(db, style, kp, info, grid, used, f, want, doors_, at=None, below=None):
    """Every way the stairs from floor f up to f + 1 could stand in this plan, cheapest first, and the
    cheapest one whose surroundings the style's pieces can build (None when there is none). Each is
    (cost, n, piece, up, tiles, lo, hi, carve, land, open sides, alcove or None, pair): `pair` when it
    is two short flights in line where the style has a stair that climbs the storey on its own (the
    last resort, see the note in the loop). at: (x, y, up), the bottom step's tile and the side it
    climbs to, when the stairs were put there by hand (only that spot is tried). below: the flight of
    the floor below when these are to stand over it in one stairwell (`stack`). used: the (x, y) the
    other floors' stairs hold. Nothing here changes the grid: _place_stairs carves it afterwards."""
    g = f + 1
    H = info['storey']
    xs = [t[0] for t in grid]
    ys = [t[1] for t in grid]
    stack = below is not None
    if at:
        ax, ay, aup = at
    starts, allow = [], set()
    if stack:
        bt = below['tiles']
        starts = [(OPPOSITE[below['up']], (bt[-1][0], bt[-1][1])), (below['up'], (bt[0][0], bt[0][1]))]
        allow = {(s[0], s[1]) for s in bt} | {below['lo'][:2], below['hi'][:2]}
    cands = []
    whole = [p for p in info['pieces'] if abs(p['rise'] - H) < 8 and p.get('len', 1) == 1]
    ctx = _carve_ctx(grid, doors_)
    # (a stairwell of the game's pieces stands within two tiles of the rooms it is carved from)
    near = {(t[0] + dx, t[1] + dy) for t in grid if t[2] in (f, g) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)}
    for piece in info['pieces']:
        n = int(round(H / piece['rise']))
        if n < 1 or n > 2 or (piece['open'] and n > 1):
            continue
        # two half-storey flights in line: the lower one's walls stop short of the next floor's
        # ceiling when the piece is a sloped stair hall no taller than that (Common plain's
        # stair_short is 364 tall: a storey and a half of 492 would be needed), and the tile over
        # it, given up for the stairwell, has nothing to close its outer side: a strip of void. A
        # piece that climbs the storey on its own (the tall stairwell) is used instead, wherever
        # it fits; the pair stays as a last resort (a pin where nothing else fits), and a style
        # with only short flights keeps them
        wedge = 150 if n == 2 and whole and piece.get('height', 1e9) < H + kp['height'] - 16 else 0
        # a piece several tiles long climbs the whole storey on its own
        L = piece.get('len', 1)
        if L > 1 and n != 1:
            continue
        span = max(n, L)
        # (how the game stands this stair, floor by floor, when its places show it)
        shape = _alcove_shape(kp, piece, stairtemplate.floors(db, style, piece['id'], piece['z_low'], piece['rise']),
                              stairtemplate.voids(db, style, piece['id'], piece['z_low'], piece['rise'])) \
            if ALCOVES and n == 1 and L == 1 and 'cx' not in piece and not stack else None
        for up in ([s for s, _xy in starts] if stack else [aup] if at else kits.SIDES):
            down = OPPOSITE[up]
            sx0 = dict(starts).get(up) if stack else None
            for bx in ([sx0[0]] if stack else [ax] if at else range(min(xs) - span - 2, max(xs) + span + 3)):
                for by in ([sx0[1]] if stack else [ay] if at else range(min(ys) - span - 2, max(ys) + span + 3)):
                    st = [nb((bx, by, f), up, i) for i in range(span)]
                    cost = 0
                    carve = []
                    ok = True
                    for s in st:
                        if (s[0], s[1]) in used and (s[0], s[1]) not in allow:
                            ok = False
                            break
                        for lv in (f, g):
                            tt = (s[0], s[1], lv)
                            if tt in grid:
                                carve.append(tt)
                    if not ok:
                        continue
                    lo, hi = nb(st[0], down), nb((st[-1][0], st[-1][1], g), up)
                    if ((lo[0], lo[1]) in used and (lo[0], lo[1]) not in allow) or \
                            ((hi[0], hi[1]) in used and (hi[0], hi[1]) not in allow):
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
                        landing = {t_ for t_, _r in land}        # (a landing is floor too)
                        for o in piece['open']:
                            ws = kits.SIDES[(kits.SIDES.index(o) + q) % 4]
                            for lv in (f, g):
                                t = nb((st[0][0], st[0][1], lv), ws)
                                if (t not in grid or t in carve) and t not in landing:
                                    ok = False
                            rot_open.append(ws)
                    if not ok:
                        continue
                    nooks = _carve_check(grid, carve, doors_, (lo, hi), ctx)
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
                    cost = len(carve) * 2 + len(land) * 6 + ((3 if piece['post'] else 10) if piece['open'] else 0) + nooks * 25 + side_n * 1.5 + wedge
                    cost += _stair_cost(info, piece, want, len(carve), len(land), rooms_lo, rooms_hi, bx, by, xs, ys)
                    if stack and up == starts[1][0]:
                        cost += 4                   # (the same way up: round the stairwell to the next flight)
                    cands.append((cost, len(cands), piece, up, st, lo, hi, carve, land, rot_open, None, wedge > 0))
                # the same spot, but the stair with the game's own pieces round it (see _alcove):
                # Indoril's closed-in corners at its ends, Hlaalu's stairwell of hall corners.
                # Preferred when it costs about the same
                if shape:
                    for bx in ([ax] if at else range(min(xs) - 3, max(xs) + 4)):
                        for by in ([ay] if at else range(min(ys) - 3, max(ys) + 4)):
                            if (bx, by) not in near:
                                continue
                            s0 = (bx, by, f)
                            alc = _alcove(grid, used, piece, shape, s0, up, f, g)
                            if not alc:
                                continue
                            carve, land, lo, hi = alc['carve'], alc['land'], alc['lo'], alc['hi']
                            # (no nook cost: the dead ends the block leaves are the game's own, Hlaalu's
                            # closet under the upper landing is a hall_end piece; the rooms must still
                            # hold together)
                            nooks = _carve_check(grid, alc['vcarve'], doors_, (lo, hi), ctx)
                            if nooks is None:
                                continue
                            rooms_lo = grid[lo] if lo in grid else land[0][1]
                            rooms_hi = grid[hi] if hi in grid and hi not in carve else land[-1][1]
                            side_n = sum(1 for lv in (f, g) for sd in (LEFT_OF[up], OPPOSITE[LEFT_OF[up]])
                                         if nb((bx, by, lv), sd) in grid and nb((bx, by, lv), sd) not in carve)
                            cost = len(carve) * 2 + len(land) * 6 + side_n * 1.5 + alc['cuts'] * 3 - 3
                            cost += _stair_cost(info, piece, want, len(carve), len(land), rooms_lo, rooms_hi, bx, by, xs, ys)
                            cands.append((cost, len(cands), piece, up, [s0], lo, hi, carve, land, alc['open'], alc, False))
    # the cheapest spot where the floor round the stairs can still be built from the style's pieces
    for c in sorted(cands)[:400]:
        if _stairs_fit(kp, grid, c[4], c[5], c[6], c[3], c[7], c[8], c[10]['needs'] if c[10] else None):
            return (c[0],) + c[2:], cands
    return None, cands


def stair_spots(db, style, rooms, stairs=None, doors=None, budget=2.5):
    """For the planner: where the stairs between each pair of floors could stand in this plan, by the
    bottom step's tile and the side they climb to, the same spots _place_stairs weighs (stairs put by
    hand are left out of the reckoning: these are the spots to move them to). {'pairs': [{'floor': f,
    'spots': [{x, y, up, pair (two short flights in line: the style's tall stairwell doesn't fit
    there), cost}], 'stacked' (the flight stands over the one below: nothing to choose)}]}."""
    import time
    style = kits.split_style(style)[0]
    kp = kits.kit_pieces(db, style)
    if not kp or not kp['pieces']:
        raise EditError('Unknown building style "%s".' % style)
    info = kits.stairs(db, style)
    if not info:
        return {'pairs': []}
    grid, names = _grid(rooms)
    wanted = _wanted_stairs(rooms, names, stairs)
    doors_ = _door_pairs(rooms, names, doors)
    floors = sorted({t[2] for t in grid})
    # where the other floors' stairs stand (a spot they hold isn't offered); none when the plan can't
    # place them as it is, and nothing to ask with only two floors
    placed = []
    if len(floors) > 2:
        try:
            placed, _n = _place_stairs(db, style, kp, dict(grid), rooms, wanted, doors_)
        except EditError:
            placed = []
    out = []
    for f in floors[:-1]:
        if f + 1 not in floors:
            continue
        t0 = time.time()
        want = dict(wanted.get(f) or {})
        want.pop('at', None)
        if want.get('stack') and any(x['floor'] == f - 1 for x in placed):
            out.append({'floor': f, 'spots': [], 'stacked': True})
            continue
        used = {(s[0], s[1]) for x in placed if x['floor'] != f for s in x['tiles']} | \
            {x[k][:2] for x in placed if x['floor'] != f for k in ('lo', 'hi')}
        _best, cands = _stair_candidates(db, style, kp, info, grid, used, f, want, doors_, None, None)
        by = {}
        for c in sorted(cands):
            k = (c[4][0][0], c[4][0][1], c[3])
            if len(by.setdefault(k, [])) < 3:
                by[k].append(c)
        spots, partial = [], False
        for k, cs in by.items():
            if time.time() - t0 > budget:
                partial = True
                break
            for c in cs:
                if _stairs_fit(kp, grid, c[4], c[5], c[6], c[3], c[7], c[8], c[10]['needs'] if c[10] else None):
                    spots.append({'x': k[0], 'y': k[1], 'up': k[2], 'pair': bool(c[11]), 'cost': round(c[0], 1)})
                    break
        out.append({'floor': f, 'spots': spots, 'partial': partial})
    return {'pairs': out}


def stair_seed(db, style, foot=('Hall', 2, 3), head=('Bedroom', 3, 2)):
    """A plan to grow a house out from: the style's stairwell on the ground floor with one room at
    its foot and one upstairs at its head, where the stairs stand best (the whole-storey piece, no
    landings, the game's pieces round it where the style has them). The planner pins the stairs
    there. Returns {'rooms': [foot room, head room], 'pin': {x, y, up}, 'stairs': plan()'s stairs}."""
    style = kits.split_style(style)[0]
    kp = kits.kit_pieces(db, style)
    if not kp or not kp['pieces']:
        raise EditError('Unknown building style "%s".' % style)
    info = kits.stairs(db, style)
    if not info:
        raise EditError('The %s style has no stair pieces, so there is no stairwell to start from. Try Hlaalu.' % kits.friendly(style))
    # the two rooms over each other, the upper one over the lower, or a tile along from it, either
    # way round; the Workshop stands the stairs where they cost least in each (the game's stairwells
    # stand inside the house's outline, the rooms on both sides of them, so the stair is carved from
    # the two rooms rather than stuck on outside them), and the cheapest arrangement is the seed
    best = None
    # (a style whose stairs want more room round them, Mournhold's: the rooms a size up, then two)
    for grow in (0, 1, 2):
        fw, fh, hw, hh = foot[1] + grow, foot[2] + grow, head[1] + grow, head[2] + grow
        for turn_a in (0, 1):
            wa, ha = (fw, fh) if turn_a == 0 else (fh, fw)
            A = {'name': foot[0], 'x': 0, 'y': 0, 'w': wa, 'h': ha, 'floor': 0}
            for turn_b in (0, 1):
                wb, hb = (hw, hh) if turn_b == 0 else (hh, hw)
                offs = {(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (wa - wb, 0), (0, ha - hb), (wa - wb, ha - hb)}
                for ox, oy in sorted(offs):
                    B = {'name': head[0], 'x': ox, 'y': oy, 'w': wb, 'h': hb, 'floor': 1}
                    try:
                        res = plan(db, style, [A, B], floors_as='stairs')
                    except EditError:
                        continue
                    if res.get('linked') or not res['stairs']:
                        continue
                    s = res['stairs'][0]
                    score = s['cost'] + len(s['land']) * 20 + (150 if s.get('pair') else 0) + (abs(ox) + abs(oy)) * 0.5 + (0.1 if turn_a else 0)
                    if best is None or score < best[0]:
                        best = (score, [A, B], {'x': s['tiles'][0][0], 'y': s['tiles'][0][1], 'up': s['up']}, res)
        if best:
            break
    if not best:
        raise EditError('Could not stand the %s stairs between a %s and a %s. Try another style.' % (
            kits.friendly(style), foot[0].lower(), head[0].lower()))
    _score, rooms, pin, res = best
    return {'rooms': rooms, 'pin': pin, 'stairs': res['stairs'], 'notes': res.get('notes', [])}


def _rooms_touch(rooms, a, b):
    """Whether two rooms (numbers) share a wall on the same floor."""
    if int(rooms[a].get('floor') or 0) != int(rooms[b].get('floor') or 0):
        return False
    ga, _n = _grid([rooms[a]])
    gb, _n = _grid([rooms[b]])
    return any(nb(t, s) in gb for t in ga for s in STEP)


def fit_together(db, style, rooms, stairs=None, doors=None, floors_as='auto', budget=4.5, scan_tiles=0):
    """Shuffle the plan a little so the stairs sit better: each room nudged a tile each way, the
    stairs turned, moved a tile or handed back to the Workshop, one change at a time, each judged by
    what the stairs would cost there (two short flights in line, landings, dead ends, floor given up:
    the same reckoning _place_stairs makes), and for a small plan the best few are built in a scratch
    place and looked through for see-through holes (the place is thrown away, nothing is committed).
    Returns {'changed': bool, 'rooms': [{'i': room number, 'x', 'y'}] (the rooms that moved), 'pins':
    {floor: {x, y, up}}, 'unpin': [floors], 'note': what changed, 'tried': how many, 'score':
    [before, after], 'holes': [before, after] or None}."""
    import copy
    import time
    t0 = time.time()
    style = kits.split_style(style)[0]
    doors = doors or []
    stairs = copy.deepcopy(stairs or [])
    pairs = [[r.get('rooms')[0], r.get('rooms')[1]] for r in doors if r.get('rooms')]
    names = [(r.get('name') or 'Room %d' % (n + 1)).strip().lower() for n, r in enumerate(rooms)]
    pair_idx = []
    for a, b in pairs:
        try:
            pair_idx.append((names.index(str(a).strip().lower()), names.index(str(b).strip().lower())))
        except ValueError:
            pass
    # (doorways in an exact spot are left to the planner to put back on the wall: only the pairs count)
    door_pairs = [{'rooms': [a, b]} for a, b in pairs]

    def evaluate(rs, sts):
        try:
            res = plan(db, style, rs, sts, floors_as, door_pairs)
        except EditError:
            return None, None
        if res.get('linked'):
            return None, res
        return sum(s['cost'] for s in res['stairs']), res
    base_score, base = evaluate(rooms, stairs)
    if base is None:
        # (the stairs have nowhere to go as the plan is, a pin where they can't stand usually: any
        # variation that builds is better than that)
        base_score, base = float('inf'), {'stairs': []}
    elif base_score is None:
        raise EditError('Fit together works out where the stairs sit best: it needs rooms on two floors joined by stairs.')
    floors = sorted({int(r.get('floor') or 0) for r in rooms})
    by_floor = {int(s.get('floor')): s for s in stairs if s.get('floor') is not None}
    for s in stairs:
        if s.get('rooms') and s.get('floor') is None:
            try:
                f = int(rooms[names.index(str(s['rooms'][0]).strip().lower())].get('floor') or 0)
                by_floor.setdefault(f, s)
            except ValueError:
                pass
    # ---- the variations, one change each
    tries = []                                   # (what changed, rooms, stairs)
    for i, r in enumerate(rooms):
        for dx, dy in STEP.values():
            rs = copy.deepcopy(rooms)
            rs[i]['x'] = int(rs[i].get('x', 0)) + dx
            rs[i]['y'] = int(rs[i].get('y', 0)) + dy
            for k in ('add', 'cut'):
                if rs[i].get(k):
                    rs[i][k] = [[int(t[0]) + dx, int(t[1]) + dy] for t in rs[i][k]]
            if any(not _rooms_touch(rs, a, b) for a, b in pair_idx if i in (a, b)):
                continue
            tries.append(({'room': i, 'x': rs[i]['x'], 'y': rs[i]['y'], 'what': '%s moved a tile %s' % (
                rooms[i].get('name') or 'Room %d' % (i + 1), {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}[
                    next(k for k, v in STEP.items() if v == (dx, dy))])}, rs, stairs))
    for f in floors[:-1]:
        if f + 1 not in floors:
            continue
        s = by_floor.get(f)
        stacked = bool(s and s.get('stack')) and f != min(ff for ff in floors if ff + 1 in floors)
        if stacked:
            continue                       # (one stairwell: the flights above go by the lowest pin)
        at = (s or {}).get('at')
        if not at:
            got = next((x for x in base['stairs'] if x['floor'] == f), None)
            if not got:
                continue
            at = {'x': got['tiles'][0][0], 'y': got['tiles'][0][1], 'up': got['up']}
        else:
            # pinned: handed back to the Workshop is a variation too
            sts = copy.deepcopy(stairs)
            for x in sts:
                if int(x.get('floor', -99)) == f:
                    x.pop('at', None)
            tries.append(({'unpin': f, 'what': 'the stairs from the %s put where they fit best' % FLOOR_NAMES.get(f, 'floor %d' % f)}, rooms, sts))
        turns = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}
        moves = [('turned a quarter turn', {'x': at['x'], 'y': at['y'], 'up': turns[at['up']]}),
                 ('turned round', {'x': at['x'], 'y': at['y'], 'up': turns[turns[at['up']]]}),
                 ('turned back a quarter turn', {'x': at['x'], 'y': at['y'], 'up': turns[turns[turns[at['up']]]]})]
        for dx, dy in STEP.values():
            moves.append(('moved a tile %s' % {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}[
                next(k for k, v in STEP.items() if v == (dx, dy))], {'x': at['x'] + dx, 'y': at['y'] + dy, 'up': at['up']}))
        for what, pin in moves:
            sts = copy.deepcopy(stairs)
            mine = [x for x in sts if int(x.get('floor', -99)) == f]
            if mine:
                mine[0]['at'] = pin
            else:
                sts.append({'floor': f, 'at': pin})
            tries.append(({'pin': f, 'at': pin, 'what': 'the stairs from the %s %s' % (FLOOR_NAMES.get(f, 'floor %d' % f), what)}, rooms, sts))
    # ---- the cheap pass: what the stairs would cost in each (the stairs' own variations first, then
    # the rooms nearest the stairs: the search stops when the time is up)
    stair_xy = [(s['tiles'][0][0], s['tiles'][0][1]) for s in base['stairs']]

    def nearness(t):
        change = t[0]
        if 'room' not in change:
            return -1
        r = rooms[change['room']]
        cx, cy = int(r.get('x', 0)) + int(r.get('w', 1)) / 2.0, int(r.get('y', 0)) + int(r.get('h', 1)) / 2.0
        return min((abs(cx - x) + abs(cy - y) for x, y in stair_xy), default=0)
    tries.sort(key=nearness)
    scored = []
    cheap_budget = budget * (0.55 if len(_grid(rooms)[0]) <= scan_tiles else 1.0)
    tried = 0
    for change, rs, sts in tries:
        if time.time() - t0 > cheap_budget:
            break
        tried += 1
        sc, res = evaluate(rs, sts)
        if sc is None:
            continue
        scored.append((sc, len(scored), change, rs, sts, res))
    scored.sort(key=lambda x: (x[0], x[1]))
    better = [x for x in scored if x[0] < base_score - 0.5]
    holes = None
    best = better[0] if better else None
    # ---- the real thing, for a small plan: built and looked through, the plan with the fewest holes wins
    ntiles = len(_grid(rooms)[0])
    if ntiles <= scan_tiles and time.time() - t0 < budget * 0.6:
        exit_ = next(({'room': rooms[n].get('name') or 'Room %d' % (n + 1), 'side': 'S'}
                      for n in range(len(rooms)) if int(rooms[n].get('floor') or 0) == 0), None)
        try:
            h0 = _scratch_holes(db, style, rooms, door_pairs, exit_, stairs)
        except Exception as e:
            print('fit together, scratch build:', e)
            h0 = None
        if h0 is not None:
            holes = [h0, h0]
            ranked = []
            for x in better[:3]:
                if time.time() - t0 > budget:
                    break
                try:
                    h = _scratch_holes(db, style, x[3], door_pairs, exit_, x[4])
                except Exception as e:
                    print('fit together, scratch build:', e)
                    continue
                ranked.append((h, x[0], x))
            ranked.sort(key=lambda r: (r[0], r[1]))
            if ranked and (ranked[0][0] < h0 or (ranked[0][0] == h0 and ranked[0][1] < base_score - 0.5)):
                best = ranked[0][2]
                holes = [h0, ranked[0][0]]
            elif ranked:
                best = None if ranked[0][0] > h0 else best
    out = {'changed': bool(best), 'tried': tried, 'score': [None if base_score == float('inf') else round(base_score, 1),
                                                           round(best[0], 1) if best else None if base_score == float('inf') else round(base_score, 1)],
           'holes': holes, 'rooms': [], 'pins': {}, 'unpin': []}
    if not best:
        out['note'] = ('Nothing fits better: the plan stays as it is (%d variations tried).' if base_score != float('inf') else
                       'The stairs have nowhere to go as the plan is, and none of the %d variations tried mends that. Move or unpin them.') % tried
        return out
    change = best[2]
    if 'room' in change:
        out['rooms'].append({'i': change['room'], 'x': change['x'], 'y': change['y']})
    if 'pin' in change:
        out['pins'][str(change['pin'])] = change['at']
    if 'unpin' in change:
        out['unpin'].append(change['unpin'])
    what = change['what']
    s0, s1 = base['stairs'], best[5]['stairs']
    was_pair = any(s.get('pair') for s in s0)
    now_pair = any(s.get('pair') for s in s1)
    gain = []
    if not s0:
        gain.append('the stairs had nowhere to go before')
    if was_pair and not now_pair:
        gain.append('the tall stairwell fits now instead of two short flights')
    if sum(len(s['land']) for s in s0) > sum(len(s['land']) for s in s1):
        gain.append('fewer landings')
    if holes and holes[1] < holes[0]:
        gain.append('%d see-through hole%s fewer' % (holes[0] - holes[1], '' if holes[0] - holes[1] == 1 else 's'))
    out['note'] = 'Fit together: %s%s. Undo puts it back.' % (what[0].upper() + what[1:], (' (' + ', '.join(gain) + ')') if gain else '')
    return out


_scratch_n = [0]


def _scratch_holes(db, style, rooms, doors, exit_, stairs):
    """Build the plan in a scratch place, count its see-through holes (fixit.scan with everything
    shown), and throw the place away again: nothing is committed, so Undo never sees it."""
    import fixit
    editing._require_project(db)
    p = db.project
    _scratch_n[0] += 1
    name = 'Workshop fit scratch %d' % _scratch_n[0]
    key = name.lower()
    had_pgrd = 'PGRD|' + key in p.records
    try:
        build_interior(db, name, style, rooms, doors, exit_, None, 'normal', False, None, stairs, commit=False)
        sc = fixit.scan(db, key, everything=True)
        return sum(1 for i in sc['issues'] if i['kind'] == 'hole')
    finally:
        p.cells.pop(key, None)
        if not had_pgrd:
            p.remove_record('PGRD', key)
        db.sync_project()


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
        # put there by hand: only that spot and that way up (the bottom step's tile, and the side it climbs to)
        at = _pin_of(want)
        if at:
            ax, ay, aup = at
        # one stairwell: this flight over the one below, turned back on it (a tower's switchback: up
        # one flight, round the landing, up the next over the first), or failing that climbing the same
        # way; the flight below's own tiles may be used again. A pin on this floor stands aside. When
        # nothing fits over the flight below, these stairs go wherever they fit, as usual
        stack_wanted = bool(want.get('stack')) and bool(placed) and placed[-1]['floor'] == f - 1
        whole_pieces = [p for p in info['pieces'] if abs(p['rise'] - H) < 8 and p.get('len', 1) == 1]
        stack = stack_wanted
        best, cands = _stair_candidates(db, style, kp, info, grid, used, f, want, doors_, at, placed[-1] if stack else None)
        if not best and stack:
            notes.append('The stairs from the %s could not stand over the ones below (no room for them to come '
                         'out on the %s there), so they were put where they fit.' % (FLOOR_NAMES.get(f), FLOOR_NAMES.get(g)))
            stack = False
            best, cands = _stair_candidates(db, style, kp, info, grid, used, f, want, doors_, at, None)
        if not best and at:
            raise EditError(_pin_problem(info, kits.friendly(style), grid, used, f, ax, ay, aup, bool(cands)))
        if not best:
            raise EditError('Could not find room for stairs between the %s and the %s. Make the rooms on both '
                            'floors a little bigger (3 tiles deep is enough).' % (FLOOR_NAMES.get(f), FLOOR_NAMES.get(g)))
        cost, piece, up, st, lo, hi, carve, land, rot_open, alc, pair = best
        moved = False
        if pair and at:
            # two short flights in line leave a strip of void beside the lower one and under the upper
            # (the user's "missing walls with staircases"): rather than build that, the stairs go to the
            # nearest spot where the set's tall stairwell fits, and the note says where they went
            _b, cands2 = _stair_candidates(db, style, kp, info, grid, used, f, want, doors_, None, None)
            # (the nearest spot first, among those that need no landing: a landing's open sides upstairs
            # show as black gaps in a style with no wall piece for them)
            near_ = sorted((abs(c[4][0][0] - ax) + abs(c[4][0][1] - ay) + (0 if c[3] == aup else 1) + (3 if c[8] else 0), c[0], c[1], c)
                           for c in cands2 if not c[11] and len(c[4]) == 1)
            for dist, _cost, _n, c in near_:
                if dist > 7:
                    break
                if _stairs_fit(kp, grid, c[4], c[5], c[6], c[3], c[7], c[8], c[10]['needs'] if c[10] else None):
                    cost, piece, up, st, lo, hi, carve, land, rot_open, alc, pair = (c[0],) + c[2:]
                    dx_, dy_ = st[0][0] - ax, st[0][1] - ay
                    how = ', '.join(p for p in ('%d %s' % (abs(dx_), 'east' if dx_ > 0 else 'west') if dx_ else '',
                                                '%d %s' % (abs(dy_), 'north' if dy_ > 0 else 'south') if dy_ else '') if p)
                    notes.append('Where you put the stairs from the %s only two short flights in line would fit, and the %s '
                                 'style has nothing to close the wall beside the lower flight or under the upper one (a strip of '
                                 'void). They were moved %s%s, where the set\'s tall stairwell (%s) fits.' % (
                                     FLOOR_NAMES.get(f), kits.friendly(style), (how + ' from there') if how else 'nowhere',
                                     (', going %s' % {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}[up]) if up != aup else '',
                                     whole_pieces[0]['id']))
                    moved = True
                    break
        if pair:
            notes.append('The stairs from the %s had to be two short flights in line (the only stairs that fit %s), and the '
                         '%s style has nothing to close the wall beside the lower flight or under the upper one: expect a '
                         'strip of void there. The set\'s tall stairwell (%s) needs a room beside its open side on both '
                         'floors.%s' % (FLOOR_NAMES.get(f), 'anywhere near where you put them' if at else 'anywhere', kits.friendly(style),
                                        whole_pieces[0]['id'], ' Try the stairs a tile along, or turn them (R).'))
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
                       'open': rot_open, 'storey': H, 'pinned': bool(at) or stack, 'land': [t for t, _r in land],
                       'stacked': stack, 'cost': cost, 'pair': bool(pair), 'moved': moved,
                       # an alcove: the needs of the tiles round the stair, and its side open only upstairs
                       'alcove': alc['needs'] if alc else None, 'block': alc['block'] if alc else set(),
                       # (a stairwell piece taller than a storey and a half is a closed hall below and open
                       # over a railing only upstairs: the room beside it keeps its wall downstairs)
                       'open_low': [] if alc or (STAIR_OPEN_LOW is False) or
                       (STAIR_OPEN_LOW is None and piece.get('height', 0) > H * 1.5) else rot_open})
        if land:
            notes.append('The stairs from the %s needed %s.' % (FLOOR_NAMES.get(f), 'a small landing' if len(land) == 1 else
                                                                 'two small landings' if len(land) == 2 else 'small landings'))
    return placed, notes


def _across_stairs(stair_list, t, s):
    """Whether a wall on this side of a tile would stand across a staircase: at the foot of a flight
    (the tile it climbs from, towards it) or at its head (the tile it comes out on, back towards it)."""
    for x in stair_list:
        if (t == x['lo'] and s == x['up']) or (t == x['hi'] and s == OPPOSITE[x['up']]):
            return True
    return False


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
        if s.get('stack'):
            w['stack'] = True             # (one stairwell: over the stairs of the floor below)
        wanted.setdefault(fa, {}).update(w)
    return wanted


def plan(db, style, rooms, stairs=None, floors_as='auto', doors=None):
    """Where everything would go, without building it: tiles per floor and the stairs."""
    style = kits.split_style(style)[0]
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
                        'stacked': bool(x.get('stacked')), 'land': [[t[0], t[1], t[2]] for t in x['land']],
                        # (what this placement cost the builder's reckoning, and whether it is two short flights
                        # in line where the style's tall stairwell would do: for Fit together)
                        'cost': round(x.get('cost', 0), 2), 'pair': bool(x.get('pair')),
                        # (put by hand where only the void-leaving pair fits: moved to the nearest spot for the tall stairwell)
                        'moved': bool(x.get('moved'))} for x in stairs],
            'notes': notes}


def build_interior(db, name, style, rooms, doors=None, exit=None, entrance=None, lighting='normal',
                   lights=True, outside_door=None, stairs=None, commit=True, exit_door=None, planner=None, dressing=None):
    """rooms: [{'name', 'x', 'y', 'w', 'h', 'floor'[, 'tall']}] in tiles (x east, y north, floor 0 = ground,
    1 = upstairs, -1 = cellar; 'tall': a two-storey hall, open to the floor above wherever no room is
    drawn over it, see wells below). doors: [{'rooms': [a, b]}] on the same floor. stairs: optional
    [{'rooms': [lower room, upper room]}]; floors are joined by stairs anyway.
    exit: {'room': a, 'side': 'N'|'E'|'S'|'W'}. entrance: {cell, x, y, z, rz} outside, or None.
    dressing: the game's panels, pilasters and floor sheets laid over the kit (dressingsurvey.py), or the
    style may name it, "kit@dressing"."""
    editing._require_project(db)
    p = db.project
    style, d_ = kits.split_style(style)
    dressing = dressing or d_
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
    # (a sheet kit, floor sheets with walls stood on them, is always dressed with its own arches, columns
    # and beams the way the game's places of it are: the Imperial chapel's arcades)
    if kp.get('sheet_kit') and not dressing:
        dressing = 'plain'
    # ---- the grid
    grid, names = _grid(rooms)
    # ---- two-storey halls: a room marked 'tall' is open to the storey above wherever no room is drawn
    # over it. The game builds such a hall (Anvil's guild of mages, the conservatory of Saint Laeca, the
    # bazaar) as a column with no tile on either storey: a floor sheet at the bottom (the 'well'), a
    # ceiling slab at the top (the 'void'), the upstairs rooms round it open towards it over a railing,
    # and pillars at its corners (dressingsurvey.py measured 61 such wells in the Gold Coast places)
    wells, voids = set(), set()
    for n_, r_ in enumerate(rooms):
        if not r_.get('tall'):
            continue
        for t_, ra_ in grid.items():
            if ra_ == n_ and (t_[0], t_[1], t_[2] + 1) not in grid:
                wells.add(t_)
                voids.add((t_[0], t_[1], t_[2] + 1))

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
    # (the rooms upstairs round a hall's opening look down into it: open on that side, over a railing)
    wells = {t for t in wells if t in grid}
    voids = {v for v in voids if v not in grid}
    gallery_edges = []
    for v in voids:
        for s in STEP:
            n_ = nb(v, s)
            if n_ in need:
                need[n_][OPPOSITE[s]] = 'open'
                gallery_edges.append((n_, OPPOSITE[s]))
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
    # (a kit with full-width door frames but none named for a load door, the chapel's TileDoorW and the
    # Redguard and Kvaurb wall-with-doorway pieces: the one frame it has makes the way out too, rather
    # than a door panel stood against a solid wall with no opening behind it)
    if load_jamb is None and full_jamb is not None and kp['frame_doors']:
        load_jamb = full_jamb
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
        # (nor through a two-storey hall's open middle, which has no wall piece to put a doorway in)
        e2 = [(t, s) for t, s in e if t not in wells and nb(t, s) not in wells]
        if not e2 and d.get('kind') != 'open':
            raise EditError('The doorway between "%s" and "%s" would open under the two-storey hall\'s opening, where there is '
                            'no wall piece to put it in. Draw an upstairs room over that part of the hall, or move the door.' % (
                                rooms[a].get('name'), rooms[b].get('name')))
        e = e2 or e
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
    free = lambda t, s: nb(t, s) not in grid and nb(t, s)[:2] not in stair_xy and need[t][s] == 'wall' and t not in wells
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
            # not downstairs where the side is walled, stairs in an alcove; and not where the game's
            # own piece beside the stair stands with its wall there)
            if sp['post'] and x['open']:
                for ws in x['open']:
                    ax, ay = STEP[ws]
                    bx, by = STEP[x['up']]
                    for along in (-1, 1):
                        for lv in ([s[2]] if ws in x.get('open_low', x['open']) else []) + [s[2] + 1]:
                            if (s[0] + bx * along, s[1] + by * along, lv) in x.get('block', ()) or \
                                    (s[0] + ax + bx * along, s[1] + ay + by * along, lv) in x.get('block', ()):
                                continue
                            refs.append((sp['post'], (sx_ + (ax + bx * along) * T / 2, sy_ + (ay + by * along) * T / 2,
                                                      z0 + lv * H, 0, 0, 0), []))
    # ---- what the game stands over and beside these stairs, at the heights its own places show
    # (closuresurvey.py: Gold Coast's loose walls over the stairwell, the Common corner behind the foot,
    # Indoril's no-floor piece over the stair), where the spot is no room tile, no stair and not filled
    # already. Half levels (±128) are the styles' own stair logic (Hlaalu, Telvanni)
    closure_refs = []        # (laid after the room tiles, so one never doubles a tile: see below)
    if CLOSURE:
        import closuresurvey
        fam_ = '_'.join(style.lower().split('_')[:-1]) if len(style.split('_')) >= 3 else style.lower()
        for x in stair_list:
            sp = x['piece']
            try:
                col = closuresurvey.column(db, style, sp['id'])
            except Exception:
                col = {}
            s0 = x['tiles'][0]
            sx0, sy0 = centre(s0)
            base_z = z0 + zf(s0) - sp['z_low']
            for (ix, iy, dz), (pid, dq) in sorted(col.items()):
                if dz % int(H) or 'stair' in pid or 'ramp' in pid or not pid.startswith(fam_ + '_') or COLUMN_WORDS_RE.search(pid):
                    continue
                ri_ = db.resolve_id(pid)
                if ri_ is None:
                    continue
                wx, wy = stairtemplate.world_tile((sx0, sy0), x['q'], ix, iy, T)
                t = (int(round(wx / T)), int(round(wy / T)), s0[2] + int(round(dz / H)))
                if t in grid or t in stair_tiles or (t[0], t[1], t[2]) in {(s[0], s[1], s[2]) for s in x['tiles']}:
                    continue
                # (only on the two floors the stair joins: the survey also sees the floor above those in
                # the game's taller houses, Common's room pieces two storeys over its tall stair, and
                # those would stand in the open over a house that has no such floor)
                if not x['floor'] <= t[2] <= x['floor'] + 1:
                    continue
                pz = base_z + dz
                if any(abs(r_[1][0] - wx) < T * 0.3 and abs(r_[1][1] - wy) < T * 0.3 and abs(r_[1][2] - pz) < H * 0.5
                       and str(r_[0]).lower().startswith(fam_ + '_') for r_ in refs):
                    continue                                   # (something of the family stands there already)
                closure_refs.append((db.recs[ri_][1], (wx, wy, pz, 0, 0, ((x['q'] + dq) % 4) * math.pi / 2), []))
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
        # (by the floor each piece stands on: a style's stair may have its origin half way up)
        for (ix, iy, lv), (pid, dq) in stairtemplate.floors(db, style, sp['id'], sp['z_low'], sp['rise']).items():
            wx, wy = stairtemplate.world_tile(centre(s0), x['q'], ix, iy, T)
            t = (int(round(wx / T)), int(round(wy / T)), s0[2] + lv)
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
    # the tiles beside a stair block's pieces take that family (a hall_3way beside Hlaalu's stairwell
    # of hall corners, as the game has it): a room piece against a hall piece leaves slits where their
    # rims differ
    beside_fam = {}
    for x in stair_list:
        for b in x.get('block', ()):
            if b in forced:
                fam = _family(forced[b][0]['id'])
                for s in STEP:
                    n_ = nb(b, s)
                    if grid.get(n_) == grid.get(b) and n_ not in x['block'] and (n_ not in beside_fam or fam == 'hall'):
                        beside_fam[n_] = fam
    import extras
    erng = extras.seeded(name)
    # windows that are wall sections (Indoril's Room_Window, Gold Coast's WallWindow): one stands in for a
    # loose wall on a true outside side of a room the game windows, as often as the game has them
    # (layoutsurvey.py; the props hung on walls come later, see _columns_and_windows)
    import furnish
    import layoutsurvey
    purposes = [furnish.purpose_for(r.get('name') or '', int(r.get('w', 1)) * int(r.get('h', 1)), int(r.get('w', 1)), int(r.get('h', 1)))
                for r in rooms]
    floors_all = {t_[2] for t_ in grid}
    win_walls = layoutsurvey.window_walls(db, style) if WINDOWS else []
    win_wall_rate = 0.0
    if win_walls:
        walls_n = float(sum(w['n'] for w in win_walls))
        props_n = float(sum(p['n'] for p in layoutsurvey.window_props(db, style)))
        win_wall_rate = layoutsurvey.window_rate(db, style)[0] * walls_n / max(1.0, walls_n + props_n)
    windowed = set()                       # (tile, side) that got a window wall
    wrng = extras.seeded(name + ' windows')  # (its own draws: the extras come out the same with or without windows)
    choice = {}
    for t, ra in sorted(grid.items()):
        if t in forced:
            choice[t] = forced[t]
            continue
        if t in wells:
            choice[t] = (None, 0, [], None)       # (no piece: a floor sheet and loose walls, see below)
            continue
        piece, q, missing, pat = _pick(kp, need[t], beside_fam.get(t) if has_halls else None)
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
    loose_at = []                          # (tile, side, floor z, storeys) where a loose wall stands: the dressing panels it
    for t, ra in sorted(grid.items()):
        piece, q, missing, pat = choice[t]
        if t in wells:
            continue                       # (laid with the voids, below)
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
        # walls the piece doesn't have (never across the foot or the head of a staircase)
        for s in missing:
            if _across_stairs(stair_list, t, s):
                continue
            wall = plain_wall(kp, db)
            factor = layoutsurvey.WINDOW_KINDS.get(purposes[ra], 0)
            if win_walls and factor and t not in stair_tiles and t not in alcove_tiles and (t, s) not in rail_edges \
                    and not any((t[0] + STEP[s][0], t[1] + STEP[s][1], f_) in grid for f_ in floors_all) \
                    and wrng.random() <= min(0.5, win_wall_rate * factor):
                pick = wrng.random() * sum(w_['n'] for w_ in win_walls)
                for w_ in win_walls:
                    pick -= w_['n']
                    wall = w_
                    if pick <= 0:
                        break
                windowed.add((t, s))
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
            if (t, s) not in windowed:
                loose_at.append((t, s, zf(t), 1, wall))
    # ---- a sheet kit's ceilings: the slab over every tile, at the top of the storey (the floor sheets have none)
    if kp.get('ceiling'):
        for t in sorted(grid):
            if t in wells or tile_piece.get(t, (None,))[0] is None:
                continue
            cx, cy = centre(t)
            refs.append((kp['ceiling']['id'], (cx, cy, z0 + zf(t), 0, 0, 0), []))
    # ---- two-storey halls: the floor sheet under the opening, the ceiling slab over it, loose walls on
    # the sides that face nothing (two storeys tall where both storeys do), pillars at the opening's
    # corners on both storeys, and the railing along the gallery's edge, all as the game's halls have them
    if wells or voids:
        _lay_wells(db, style, dressing, kp, grid, need, wells, voids, gallery_edges, stair_list, centre, zf, z0, T, H, refs, loose_at)
    # ---- the closure pieces, now that every room tile stands: never one on a tile's own spot (the
    # Gold Coast survey's Floor_01 slabs landed under room pieces at the same height and the floor
    # flickered; the room tiles weren't in the list when the closure pieces were checked)
    for c_ in closure_refs:
        if any(abs(r_[1][0] - c_[1][0]) < T * 0.3 and abs(r_[1][1] - c_[1][1]) < T * 0.3 and abs(r_[1][2] - c_[1][2]) < kp['height'] * 0.5
               for r_ in refs):
            continue
        refs.append(c_)
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
    # ---- columns standing free in big rooms, and windows on outside walls, the way the game's own
    # places of this style have them (layoutsurvey.py: a survey of all of them; nothing until it has run)
    # (a doorway: a side that was asked for one, a frame, a learned edge, the way out; not every arched
    # side of a hall piece standing where the room simply carries on)
    doorway_sides = {(t, s) for (t, s) in door_at if need[t][s] == 'door'} | set(frames) | {(t, s) for t, s, _w in learned_edges} \
        | {(exit_tile, exit_side)} | windowed
    _columns_and_windows(db, style, kp, grid, rooms, need, stair_tiles | alcove_tiles | wells, doorway_sides, set(rail_edges) | set(gallery_edges),
                         floors_all, centre, zf, wrng, refs, bool(win_walls))
    # ---- a whole column over a doorway jamb left standing in open floor (see _stub_columns)
    _stub_columns(db, kp, grid, need, choice, centre, zf, z0, T, doorway_sides, stair_tiles | alcove_tiles | wells, refs)
    _stair_edge_columns(db, kp, grid, choice, stair_list, centre, zf, z0, T, refs)
    # ---- the dressing: the game's panels over the walls, pilasters where walls meet, arches and beams over
    # the joins, floor sheets, its rich door frames (dressingsurvey.py), as often as its dressed places have them
    if dressing:
        _dress(db, style, dressing, kp, grid, need, choice, tile_piece, refs, centre, zf, z0, T, H, loose_at, doorway_sides,
               windowed, stair_tiles, wells, voids, rooms, extras.seeded(name + ' dressing'))
    # ---- some light to see by
    if lights:
        # a hanging lantern of the kind used in places like this, from the ceiling
        # (not sconces: those belong on a wall, and Auto-furnish puts them there)
        hanging = _co_used(db, kp, 'LIGH', lambda k: any(w in k for w in ('lantern', 'chandelier', 'hang')) and 'sconce' not in k)
        lamp = hanging[0] if hanging else None
        lb = mapdata.object_bounds(db, db.resolve_id(lamp)) if lamp else None
        if lamp and lb:
            for n, r in enumerate(rooms):
                tiles = sorted(t for t, ra in grid.items() if ra == n and t not in wells) or sorted(t for t, ra in grid.items() if ra == n)
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
                        # the room plan, so auto-furnish knows which tiles make which room (and the
                        # planner's own plan, when it was built from the planner, to start from again)
                        'plan': {'tile': T, 'style': style, 'dressing': dressing,
                                 'rooms': [{'name': (r.get('name') or 'Room %d' % (n + 1)),
                                            'tiles': [[t[0] * T, t[1] * T, zf(t)] for t, ra in sorted(grid.items()) if ra == n]}
                                           for n, r in enumerate(rooms)]}}
    if isinstance(planner, dict) and planner.get('rooms'):
        c['plan']['planner'] = planner
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
            kits.friendly(style + ('@' + dressing if dressing else '')), name, len(rooms), len(grid),
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
    return {'key': key, 'name': name, 'style': kits.friendly(style + ('@' + dressing if dressing else '')), 'tile': T, 'rooms': summary,
            'exit': {'x': round(dx), 'y': round(dy), 'side': exit_side, 'how': exit_how}, 'door': door_id,
            'entrance': out_spot[0] if out_spot else None,
            'building': {'like': shell_spot[1]['like'], 'pieces': len(shell_spot[2]), 'cell': shell_spot[0]} if shell_spot else None,
            'floors': sorted({t[2] for t in grid}), 'stairs': [x['piece']['id'] for x in stair_list],
            'notes': ['No proper doorway piece fitted between "%s" and "%s", so they join through an open gap.' % g for g in gaps] + stair_notes,
            '_grid': grid, '_exit_tile': (exit_tile, exit_side)}


FLOOR_TITLES = {-2: 'Lower Cellar', -1: 'Cellar', 1: 'Upstairs', 2: 'Top Floor'}


def build_house(db, name, style, rooms, doors=None, exit=None, entrance=None, lighting='normal',
                lights=True, outside_door=None, stairs=None, floors_as='auto', planner=None):
    """Build from pieces, on one floor or several. Styles with stair pieces get real stairs inside one
    place; in the others every floor is a place of its own ("Name: Upstairs", "Name: Cellar"), joined
    the way the game often does it: a door in a wall going up, a trapdoor in the floor going down to a
    cellar. Everything goes in as one change. Returns build_interior's result for the ground floor,
    plus 'cells': every place built, in order."""
    floors = sorted({int(r.get('floor') or 0) for r in rooms})
    # (a dressed style, "kit@dressing": the kit is read by its prefix, the dressing laid over it at the end)
    style, dressing = kits.split_style(style)
    # floors_as: 'stairs' (real stairs inside one place), 'linked' (a place per floor, joined by doors)
    # or 'auto' (stairs when the style has them)
    if floors_as == 'stairs' and len(floors) > 1 and not kits.stairs(db, style):
        raise EditError('The %s style has no stair pieces. Choose "Separate floors, joined by doors" for it.' % kits.friendly(style))
    st_info = kits.stairs(db, style)
    use_stairs = bool(st_info) and (floors_as == 'stairs' or (floors_as == 'auto' and st_info.get('proper', True)))
    if len(floors) < 2 or use_stairs:
        out = build_interior(db, name, style, rooms, doors, exit, entrance, lighting, lights, outside_door, stairs,
                             planner=planner, dressing=dressing)
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
        # (a two-storey hall needs its gallery in the same place: with the floors as places of their own,
        # the hall is an ordinary room)
        rs = [dict(rooms[n], floor=0, tall=False) for n in keep]
        ds = [d for d in (doors or []) if all(floor_of[idx(r)] == f for r in d['rooms'])]
        return keep, rs, ds
    built = {}
    title = lambda f: name if f == 0 else '%s: %s' % (name, FLOOR_TITLES.get(f, 'Floor %d' % f))
    for f in [0] + [f for f in floors if f > 0] + sorted((f for f in floors if f < 0), reverse=True):
        keep, rs, ds = floor_rooms(f)
        if len(title(f).encode(ENC, 'replace')) > 63:
            raise EditError('"%s" is too long for a place name (63 characters at most): shorten the name.' % title(f))
        if f == 0:
            out = build_interior(db, name, style, rs, ds, exit, entrance, lighting, lights, outside_door, commit=False,
                                 planner=planner, dressing=dressing)
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
                                 exit_door=ladder if f < 0 else None, dressing=dressing)
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
