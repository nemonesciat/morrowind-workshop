"""Build an interior from a building: right-click a building on the map (one of the game's shells, or a
house put together from exterior pieces), and the Workshop checks it is closed and sound, plans an
interior inside its outline in the matching style, builds it, links its door both ways and turns the
northmarker. Then it lays the new interior over the building the way Project Tamriel's reviewers do
and says what sticks out.

The building and its outline come from shellsurvey.py (the pieces joined to the clicked one, cut by
horizontal planes just over the door's sill); the style, how many floors a building that tall has and
how far the game's own interiors stick out of their buildings come from that survey's pairs.

The plan, in the door's frame (+y inward, +x to the right going in, the door at the origin on the south
edge of tile (0, 0)): a tile is kept where at least COVER of it lies inside the outline, joined to the
door's tile; an upper floor is laid where the outline a storey up is closed, over the tiles below it
(the stepped town houses keep their steps); rooms are cut from each floor's tiles at most ROOM_MAX tiles
each; the builder then puts the stairs and doorways in as it does for any plan. The interior is built
with its way out at the door's tile on the south side, so the frame's +y is north inside and the
northmarker says where north is outside."""
import math
import random
import zlib
import re
import struct

import builder
import doors
import editing
import kits
import mapdata
import outside
import shellsurvey as ss
from editing import EditError
from project import zs

COVER = 0.5                   # share of a tile inside the outline for it to be laid
ROOM_MAX = 9                  # tiles in one room at most before it is cut in two
# (every family's storeys at once, when the layout survey isn't to hand: measured 2026-10-30, lab jrooms1)
# (Hlaalu's: rooms of a storey by its tiles in fours, their sizes, the biggest room's share of the storey)
ROOMS_FALLBACK = {'p': {2: 0.19, 3: 0.14, 4: 0.17, 5: 0.09, 6: 0.15, 7: 0.05, 8: 0.06, 9: 0.04, 10: 0.02, 11: 0.02, 12: 0.02,
                        14: 0.01, 15: 0.01, 16: 0.01, 20: 0.01}, 'rooms_at': {0: [1], 1: [1], 2: [2], 3: [3], 4: [2, 3], 5: [3],
                        6: [3, 4], 7: [3], 8: [4], 9: [4]}, 'biggest': 0.6, 'one_wide': 0.25, 'n': 0}
UP_MIN = 0.3                  # an upper outline smaller than this share of the ground's is no storey
ROOF_SAMPLE = 3               # every n-th outline cell is looked up from for the roof
# (a building right-clicked may be bigger than the survey reads in the game's towns: a prefab of three houses)
BIG_PIECES = 90
BIG_EXTENT = 4600
ROOF_OPEN = 0.30              # open to the sky over more of the floor than 9 in 10 of the game's buildings
# Measured on 3,417 of the game's buildings, 2026-10-27 (prefab stage 2): per style, the share of its buildings whose
# walls don't close round at the ground (Velothi cantons' arches, Dunmer and Redoran shells with open fronts) and the
# share of the floor open to the sky at the style's 90th percentile (Hlaalu's terraces and flat roofs read 60% open).
# Open walls outdoors are a warning, worded by how usual they are (OPEN_FAULT: past it, "usual"); the roof is a
# warning past the style's own p90. Styles not listed use 'ALL'.
STYLE_OPEN = {'Velothi': 0.481, 'Dunmer': 0.230, 'Hlaalu': 0.023, 'Imperial': 0.049, '(none)': 0.216, 'Telvanni': 0.009,
              'Cave': 0.010, 'Reach': 0.050, 'Nordic': 0.031, 'Mournhold': 0.017, 'Redoran': 0.130, 'Ashlander': 0.0,
              'Stronghold': 0.121, 'Common': 0.039, 'Indoril': 0.0, 'Daedric': 0.0, 'Dwemer': 0.0, 'Redguard': 0.0, 'ALL': 0.143}
STYLE_ROOF_P90 = {'Velothi': 0.333, 'Dunmer': 0.422, 'Hlaalu': 0.603, 'Imperial': 0.185, '(none)': 0.534, 'Telvanni': 0.181,
                  'Cave': 0.419, 'Reach': 0.263, 'Nordic': 0.308, 'Mournhold': 0.341, 'Redoran': 0.356, 'Ashlander': 0.357,
                  'Stronghold': 0.321, 'Common': 1.0, 'Indoril': 0.184, 'Daedric': 0.125, 'Dwemer': 0.926, 'Redguard': 1.0, 'ALL': 0.422}
OPEN_FAULT = 0.06
FLOAT_MIN = 16                # a piece's bottom this far over the ground and over everything under it: standing on nothing
                              # (the game's buildings: 0.3% have one)
# (checklab on 888 of the game's buildings, 2026-10-27, with the faces rule, MOUNTED and NO_HOLD: none hung touching
# nothing; 3.2% had a piece with nothing under it leaning on a neighbour, Telvanni's most at 10%. Pieces moved 300 up and
# 400 out (liftout lab, 139): 23 hang touching nothing, 33 lean; the rest landed on the ground, a rock or another
# building (61), or went past the building's reach (21). Lifted straight up, a piece is still most often held by a
# ledge or floor of its neighbours in reach: a known limit)
RATE_AIR = 'none in 888 of them'
RATE_LEAN = 'in 1 in 30'
# what hangs on a wall rather than standing on something (the game's windows were most of "standing on nothing" else)
MOUNTED = re.compile(r'window|_win|winround|winplain|slit|decal|overhang|_ban_|banner|tapestry|dormer|railing|_rail|sign|'
                     r'shutter|awning|lamp|lantern|ivy|vine|flag|brace|bracket|sconce|_trim|rope|pelt|clothes|marker', re.I)
# what holds nothing up: plants and trees, and loose things laid on the ground or hung
NO_HOLD = re.compile(r'flora|tree|palm|parasol|grass|bush|shrub|kelp|fern|ivy|vine|_plant|mushroom|'
                     r'rug|rope|banner|basket|lightpost|lamp|lantern|_sign|guarskin|pelt', re.I)


# ---------------------------------------------------------------- the building

def _door_inward(it, centre):
    """A door's inward direction: its thin axis (doors stand in the wall), the way towards the
    building's middle."""
    b, rz = it['b'], it['p'][5]
    thin_x = (b[3] - b[0]) < (b[4] - b[1])
    lx, ly = (1.0, 0.0) if thin_x else (0.0, 1.0)
    ux, uy = outside._world(lx, ly, rz)
    dx, dy = centre[0] - it['p'][0], centre[1] - it['p'][1]
    if ux * dx + uy * dy < 0:
        ux, uy = -ux, -uy
    return ux, uy


def building_at(db, cell_key, ref_key, door_key=None):
    """The building a placed exterior piece (or door) belongs to: {'group', 'door', 'doors', 'frame',
    'cell'}; raises EditError when there is none."""
    # (outdoors, or in a place that behaves like outdoors: Mournhold's districts are interiors, and their buildings
    # are buildings, the Winged Guar's in Godsreach, 2026-10-27)
    like_ext = bool(cell_key) and not cell_key.startswith('#') and bool((mapdata.cell_info(db, cell_key) or {}).get('like_exterior'))
    if not cell_key or not (cell_key.startswith('#') or like_ext):
        raise EditError('Pick a building outdoors: this works on exterior pieces.')
    m = mapdata.cellmap(db, cell_key)
    ref = next((r for r in m.get('refs', []) if r['k'] == ref_key), None)
    if ref is None:
        raise EditError('That piece is no longer there.')
    items = ss._cell_items(db, cell_key, {}, {}) if like_ext else ss.near_items(db, ref['p'][0], ref['p'][1])
    it = next((i for i in items if i['k'] == ref_key and i['cell'] == cell_key), None)
    if it is None:
        raise EditError('That piece has no model the Workshop can read.')
    all_doors = [i for i in items if i['tag'] == 'DOOR' and 'marker' not in i['low']]
    if it['tag'] == 'DOOR':
        seed_door = it
        group = ss.structure(items, it['box'], [d for d in all_doors if d is not it and d['to'] and d['to']['cell']], None, BIG_PIECES, BIG_EXTENT)
    else:
        seed_door = None
        mine = [d for d in all_doors if outside._touch(d['box'], it['box'], 8)]
        others = [d for d in all_doors if d['to'] and d['to']['cell'] and d not in mine]
        if not ss.is_building_piece(it):
            raise EditError('"%s" is not a building piece (a wall, a house, a tower).' % it['id'])
        group = ss.structure(items, None, others, seed=it, max_pieces=BIG_PIECES, max_extent=BIG_EXTENT)
    if not group:
        raise EditError('No building found here: the pieces run on into the rest of the town (more than %d pieces or %d units '
                        'across). Right-click the building\'s own door instead.' % (BIG_PIECES, BIG_EXTENT))
    touching = [d for d in all_doors if any(outside._touch(d['box'], g['box'], 8) for g in group)]
    door = seed_door
    if door_key:
        door = next((d for d in touching if d['k'] == door_key), door)
    if door is None and touching:
        # the door near the ground first (an upstairs door up outside stairs is the second way in), then
        # one that leads nowhere yet
        door = min(touching, key=lambda d: (d['box'][4] - min(g['box'][4] for g in group) > 200, bool(d['to'] and d['to']['cell']),
                                            -d['box'][5]))
    x0 = min(g['box'][0] for g in group)
    y0 = min(g['box'][1] for g in group)
    x1 = max(g['box'][2] for g in group)
    y1 = max(g['box'][3] for g in group)
    centre = ((x0 + x1) / 2, (y0 + y1) / 2)
    frame = None
    if door is not None:
        ux, uy = _door_inward(door, centre)
        sill = door['p'][2] + door['b'][2] * door['s']
        frame = ss.Frame(door['p'][0], door['p'][1], sill, ux, uy)
    return {'group': group, 'door': door, 'doors': touching, 'frame': frame, 'cell': cell_key, 'items': items,
            'centre': centre, 'doubled': list(getattr(ss.structure, 'doubled', []))}


# ---------------------------------------------------------------- closed and sound

def _gap_spots(wall, frame, max_grow=3):
    """Where an outline is open: grow the walls a cell at a time until they close; the cells the
    growing filled between inside and out are the gaps. [(world x, y, width)] or None (never closes)."""
    grown = set(wall)
    for k in range(1, max_grow + 1):
        ring = set()
        for (x, y) in grown:
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in grown:
                    ring.add((nx, ny))
        grown |= ring
        inside = ss.enclosed(grown)
        if inside:
            added = [c for c in grown - wall if c in inside and any(n not in inside for n in
                     ((c[0] + k + 1, c[1]), (c[0] - k - 1, c[1]), (c[0], c[1] + k + 1), (c[0], c[1] - k - 1)))]
            spots = _clusters(added)
            out = []
            for cl in spots:
                cx = (sum(c[0] for c in cl) / float(len(cl)) + 0.5) * ss.GRID
                cy = (sum(c[1] for c in cl) / float(len(cl)) + 0.5) * ss.GRID
                wx, wy = frame.back(cx, cy)
                out.append((round(wx), round(wy), (2 * k) * ss.GRID))
            return out
    return None


def _clusters(cells):
    cells = set(cells)
    out = []
    while cells:
        c = cells.pop()
        cl, todo = [c], [c]
        while todo:
            x, y = todo.pop()
            for n in ((x + dx, y + dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)):
                if n in cells:
                    cells.discard(n)
                    cl.append(n)
                    todo.append(n)
        if len(cl) >= 2:
            out.append(cl)
    return out


def _roof(db, group, frame, cells):
    """The share of the outline with nothing overhead (looked up from a man's height over the sill)."""
    import seethrough
    sc = seethrough.Scene()
    for it in group:
        if it.get('ri') is None:
            continue
        sc.add_model(seethrough.model_tris(db, db.recs[it['ri']][5]), it['p'], it['s'])
    cells = sorted(cells)[::ROOF_SAMPLE]
    if not cells:
        return 0.0, []
    open_ = []
    for (ix, iy) in cells:
        wx, wy = frame.back((ix + 0.5) * ss.GRID, (iy + 0.5) * ss.GRID)
        # (from inside, a roof is seen from behind: an exterior's faces look outward)
        if sc.nearest_any((wx, wy, frame.z + 170), (0.0, 0.0, 1.0), 4000) is None:
            open_.append((round(wx), round(wy)))
    return len(open_) / float(len(cells)), open_


def _held(db, it, supp):
    """Does something else's surface hold this piece up: a flat-ish face of another piece's mesh under the piece's
    footprint, from FLOAT_MIN below its bottom to a little over it (sunk in: TR's Velothi walls go 230 down through
    their platforms, Telvanni braces through theirs; Vivec's waistworks gap pieces sit level with their neighbours).
    Boxes alone held nearly anything up (a lifted wall by a tower's or a palm tree's box: 1 in 157 caught,
    2026-10-27), so it is the faces. A neighbour with no mesh read counts by its box top."""
    bx = it['box']
    bottom, T = bx[4], FLOAT_MIN
    x0, y0, x1, y1 = bx[0] - T, bx[1] - T, bx[2] + T, bx[3] + T
    # (nothing is held by a tree, a plant, a rug or a rope: a palm's box reached a window moved off its wall)
    supp = [s for s in supp if s is not it and not NO_HOLD.search(s['id'])]
    if MOUNTED.search(it['id']) or min(bx[2] - bx[0], bx[3] - bx[1]) < 40:
        # (windows, arrow slits, decals, overhangs, banners: on a wall by design; held if they touch something
        # made, its mesh and not only its box: a house's box took in a window moved 400 off it)
        from placecheck import _tri_in_box
        c = ((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2, (bx[4] + bx[5]) / 2)
        h = ((bx[2] - bx[0]) / 2 + T, (bx[3] - bx[1]) / 2 + T, (bx[5] - bx[4]) / 2 + T)
        for s in supp:
            sb = s['box']
            if not (sb[0] <= x1 and sb[2] >= x0 and sb[1] <= y1 and sb[3] >= y0 and sb[4] <= bx[5] + T and sb[5] >= bottom - T):
                continue
            tris = ss.world_tris(db, s)
            if not tris:
                return True
            for t in tris:
                if _tri_in_box(*[(p[0] - c[0], p[1] - c[1], p[2] - c[2]) for p in t], h):
                    return True
        return False
    reach = bottom + max(2 * T, min((bx[5] - bottom) / 2, 250))
    # (and a window or an awning holds up nothing standing: a house moved onto its neighbour's windows)
    supp = [s for s in supp if not MOUNTED.search(s['id'])]
    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
    pts = [(cx, cy), (bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3]),
           (cx, bx[1]), (cx, bx[3]), (bx[0], cy), (bx[2], cy)]
    for s in supp:
        sb = s['box']
        if s is it or sb[0] > x1 or sb[2] < x0 or sb[1] > y1 or sb[3] < y0 or sb[5] < bottom - T or sb[4] > reach:
            continue
        tris = ss.world_tris(db, s)
        if not tris:
            if bottom - T <= sb[5] <= reach:
                return True
            continue
        for t in tris:
            (ax, ay, az), (bx_, by, bz), (qx, qy, qz) = t
            if max(az, bz, qz) < bottom - T or min(az, bz, qz) > reach:
                continue
            # (flat-ish: a floor, a top, a ledge; not the side of a wall)
            ux, uy, uz, vx, vy, vz = bx_ - ax, by - ay, bz - az, qx - ax, qy - ay, qz - az
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            if nz * nz < 0.25 * (nx * nx + ny * ny + nz * nz):
                # (the side of a wall holds by its top edge, a piece set right on it: the game's Imperial tower
                # sections are four walls with no top, and the tower's crown rests on them; not sunk in)
                hz = max(az, bz, qz)
                if bottom - T <= hz <= bottom + 2 * T and any(
                        z == hz and x0 <= x <= x1 and y0 <= y <= y1 for x, y, z in t):
                    return True
                continue
            for x, y, z in t:
                if x0 <= x <= x1 and y0 <= y <= y1 and bottom - T <= z <= reach:
                    return True
            d = ux * vy - uy * vx
            if abs(d) < 1e-9:
                continue
            for x, y in pts:
                # (the face's height over a point of the footprint inside it)
                l1 = ((x - ax) * vy - (y - ay) * vx) / d
                l2 = ((y - ay) * ux - (x - ax) * uy) / d
                if l1 >= 0 and l2 >= 0 and l1 + l2 <= 1 and bottom - T <= az + l1 * uz + l2 * vz <= reach:
                    return True
    return False


def floating(db, group, items, ground=None):
    """The pieces of a building standing on nothing: their bottom over the ground (centre and corners) and over every
    made thing under them by more than FLOAT_MIN. [(item, gap, touching)]: touching, it leans on something beside it
    (a wall it was lifted along, or the game's own odd one); not touching, it hangs in the air on its own."""
    supp = [it for it in items if it['tag'] in ('STAT', 'ACTI') and it.get('b')]
    T = FLOAT_MIN
    out = []
    for it in group:
        if 'marker' in it['id'].lower():
            continue                     # (not seen in the game)
        bx = it['box']
        bottom = bx[4]
        pts = [((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2), (bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3])]
        gz = [z for z in ((ground or (lambda x_, y_: mapdata.terrain_z(db, x_, y_)))(x, y) for x, y in pts) if z is not None]
        if gz and bottom <= max(gz) + FLOAT_MIN:
            continue
        # (afloat: a boat's bottom at the sea, which outdoors is at 0; the game's longboats and harbour cutters)
        if gz and max(gz) < 0 and bottom <= FLOAT_MIN * 4:
            continue
        if _held(db, it, supp):
            continue
        over = [s for s in supp if s is not it and s['box'][0] < bx[2] and bx[0] < s['box'][2] and s['box'][1] < bx[3] and bx[1] < s['box'][3]]
        top = max([s['box'][5] for s in over if s['box'][5] < bottom] + (gz or [bottom - 9999]))
        touching = any(s is not it and s['box'][0] <= bx[2] + T and s['box'][2] >= bx[0] - T and s['box'][1] <= bx[3] + T
                       and s['box'][3] >= bx[1] - T and s['box'][4] <= bx[5] + T and s['box'][5] >= bottom - T for s in supp)
        out.append((it, round(bottom - top), touching))
    return out


def outdoor_check(db, cell_key, ref_key):
    """The building check for one put together outdoors (by hand, or Plan a prefab's): check() with the rules as the
    game's own buildings set them for its style."""
    b = building_at(db, cell_key, ref_key)
    ch = check(db, b, outdoor=True)
    return {'ok': ch['ok'], 'lines': ch['lines'], 'style': ss.style_of_group(b['group']) or None,
            'pieces': [g['k'] for g in b['group']]}


def check(db, b, outdoor=False, ground=None):
    """Is the building closed and sound? {'ok', 'lines': [{'sev': 'ok'|'warning'|'error', 'text', 'at'?}],
    'outline', 'ups'}. outdoor: as a building outdoors, by the game's rules for its style (open walls are a fault
    only where the style's own buildings almost never have them); else as the shell of an interior to be built,
    where the walls must close round."""
    lines = []
    group, frame, door = b['group'], b['frame'], b['door']
    style = ss.style_of_group(group) or '(none)'
    near = []
    if outdoor and b.get('items'):
        # (and made pieces beside it that touch nothing: a piece lifted off a building is no longer part of it, and
        # hangs in the air beside it; a balcony 300 up went unseen, 2026-10-27)
        import exteriorsurvey as es
        x0, y0 = min(g['box'][0] for g in group) - 256, min(g['box'][1] for g in group) - 256
        x1, y1 = max(g['box'][2] for g in group) + 256, max(g['box'][3] for g in group) + 256
        ids = {id(g) for g in group}
        # (building pieces only: a sign, a lantern or a banner hangs by design)
        near = [it for it in b['items'] if id(it) not in ids and ss.is_building_piece(it, big=True) and it['box'][0] < x1 and it['box'][2] > x0
                and it['box'][1] < y1 and it['box'][3] > y0]
    # (ground: the ground's height at a point; the prefab workbench's is flat, at 0, bench.py)
    fl = floating(db, group + near, b.get('items') or group, ground)
    floats = []
    # (in the air touching nothing: an error outdoors. Nothing under it but leaning on a neighbour: only a warning, as
    # the game's own buildings have it too (RATE_LEAN), and a lifted piece most often still leans on its wall)
    for lean in (False, True):
        fl1 = [f for f in fl if f[2] == lean]
        if not fl1:
            continue
        one = len(fl1) == 1
        if lean:
            what = ('1 piece has nothing under it, only a neighbour beside it' if one else
                    '%d pieces have nothing under them, only a neighbour beside them' % len(fl1))
            rate = 'Fine for something hung on a wall; the game\'s own buildings have one like it %s.' % RATE_LEAN
        else:
            what = '1 piece hangs in the air, touching nothing' if one else '%d pieces hang in the air, touching nothing' % len(fl1)
            rate = 'The game\'s own buildings almost never do this (%s).' % RATE_AIR
        floats.append({'sev': 'warning' if lean or not outdoor else 'error',
                       'text': '%s (%s): set %s down (End in 3D), or put something under %s. %s' % (
                           what, ', '.join('%s %d up' % (it['id'], g) for it, g, _t in fl1[:4]),
                           'it' if one else 'them', 'it' if one else 'them', rate),
                       'at': [[round(it['p'][0]), round(it['p'][1]), round(it['p'][2])] for it, _g, _t in fl1[:6]]})
    lines.append({'sev': 'ok', 'text': '%d piece%s, all joined (%s)' % (len(group), '' if len(group) == 1 else 's',
                                                                      ', '.join(sorted({g['id'] for g in group})[:6]) + ('…' if len(group) > 6 else ''))})
    if b.get('doubled'):
        lines.append({'sev': 'warning', 'text': '%d piece%s stand%s twice in the same spot (%s): delete the copy' % (
            len(b['doubled']), '' if len(b['doubled']) == 1 else 's', 's' if len(b['doubled']) == 1 else '',
            ', '.join(sorted({d['id'] for d in b['doubled']})[:4])),
            'at': [[round(d['p'][0]), round(d['p'][1]), round(d['p'][2])] for d in b['doubled'][:6]]})
    lines += floats or [{'sev': 'ok', 'text': 'Every piece stands on the ground or on another'}]
    if door is None or frame is None:
        if outdoor:
            lines.append({'sev': 'ok', 'text': 'No door into it: the walls and roof are only checked from a door (one is not needed '
                                               'outdoors: a tower, a wall or a ruin may have none)'})
            return {'ok': not any(l['sev'] == 'error' for l in lines), 'lines': lines, 'outline': None, 'ups': []}
        lines.append({'sev': 'error', 'text': 'No door: put a door in one of its walls (Place, then a load door of the style), '
                                              'then right-click the door.'})
        return {'ok': False, 'lines': lines, 'outline': None, 'ups': []}
    if door['to'] and door['to']['cell']:
        lines.append({'sev': 'ok' if outdoor else 'warning', 'text': ('Door: %s, into %s' % (door['id'], door['to']['cell'])) if outdoor else
                      'Door: %s. It leads to %s now; the new interior takes it over (Undo gives it back).' % (door['id'], door['to']['cell'])})
    else:
        lines.append({'sev': 'ok', 'text': 'Door: %s' % door['id'] + (' (it leads nowhere yet)' if outdoor else '')})
    g0 = ss.outline(db, group, frame, b['doors'], 0)
    open_share = STYLE_OPEN.get(style, STYLE_OPEN['ALL'])
    if g0['closed']:
        lines.append({'sev': 'ok', 'text': 'Walls round: closed at the ground floor (%d m² inside the walls)' % round(g0['area'] / 4900.0)})
    else:
        gaps = _gap_spots(g0['wall'], frame)
        # (outdoors only a warning: even the styles that close round leave 5 to 11% of the game's buildings open
        # (checklab, 2026-10-27: Reach, Imperial, Common), and it only matters for an interior. How usual it is says the rest)
        sev = 'warning' if outdoor else 'error'
        usual = ('' if not outdoor else
                 ' %d%% of the game\'s %s buildings are open at the ground too (arches, open fronts)' % (round(open_share * 100), style)
                 if open_share >= OPEN_FAULT else
                 ' The game\'s %s buildings are nearly always closed (%s open); an interior needs the walls round' % (
                     style, ('%d%%' % round(open_share * 100)) if open_share >= 0.01 else 'under 1%'))
        if gaps:
            lines.append({'sev': sev, 'text': 'The walls are open at the ground floor: %d gap%s (%s).%s' % (
                len(gaps), '' if len(gaps) == 1 else 's', ', '.join('%d units wide at %d, %d' % (g[2], g[0], g[1]) for g in gaps[:4]), usual),
                'at': [[g[0], g[1], round(frame.z + 100)] for g in gaps]})
        else:
            lines.append({'sev': sev, 'text': ('The walls don\'t go round.%s' % usual) if outdoor else
                          'The walls don\'t go round: there is no inside to build in (a wall is missing, or this is not a building).'})
        g0b = ss.box_outline(group, frame)
        return {'ok': not any(l['sev'] == 'error' for l in lines), 'lines': lines, 'outline': g0b, 'ups': []}
    share, open_ = _roof(db, group, frame, g0['cells'])
    # (measured on 260 of the game's buildings, 2026-10-24: open to the sky over 3% of the floor at the median, 30% at p90;
    # and per style on 3,417, 2026-10-27: Hlaalu's p90 is 60% (terraces, flat roofs), Telvanni's 18%. So only a warning,
    # past the style's own p90)
    lim = STYLE_ROOF_P90.get(style, STYLE_ROOF_P90['ALL'])
    if share > lim and lim < 1.0:
        lines.append({'sev': 'warning', 'text': 'Open to the sky over %d%% of the floor (9 in 10 of the game\'s %s buildings: under %d%%); '
                                                'fine for a tower with a walk on top' % (round(share * 100), style, round(lim * 100)),
                      'at': [[x, y, round(frame.z + 300)] for x, y in open_[:6]]})
    else:
        lines.append({'sev': 'ok', 'text': 'Roofed over' if share < 0.05 else 'Roofed over, but for %d%% (as the game\'s %s buildings are)' % (round(share * 100), style)})
    ups = []
    for k in (1, 2):
        u = ss.outline(db, group, frame, b['doors'], k)
        ups.append(u)
    n_up = sum(1 for u in ups if u['closed'] and u['area'] >= UP_MIN * g0['area'])
    lines.append({'sev': 'ok', 'text': 'About %d m tall over the door\'s sill; walls closed %s' % (
        round(max(g['box'][5] for g in group) - frame.z) // 70,
        'on %d storey%s above the ground' % (n_up, '' if n_up == 1 else 's') if n_up else 'at the ground floor only')})
    ok = not any(l['sev'] == 'error' for l in lines)
    return {'ok': ok, 'lines': lines, 'outline': g0, 'ups': ups}


# ---------------------------------------------------------------- the plan

def _learnt(db):
    s = ss.ready(db)
    return s['learnt'] if s else None


def _buildable(db, kit):
    return bool(kit) and kit in kits.kits(db) and bool((kits.kit_pieces(db, kit) or {}).get('pieces'))


def pick_style(db, b):
    """The kit to build in, what it was learnt from, and the prediction."""
    L = _learnt(db)
    bld = {'main': max(b['group'], key=lambda it: (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1]) *
                       (it['box'][5] - it['box'][4]))['id'].lower(),
           'style': ss.style_of_group(b['group']), 'height': max(g['box'][5] for g in b['group']) - (b['frame'].z if b['frame'] else 0)}
    pr = ss.predict(L, bld) if L else None
    kit = pr['kit'] if pr else None
    if not _buildable(db, kit):
        # the kit the game most often builds this style's interiors in, that the builder knows
        want = (pr or {}).get('style') or bld['style']
        cands = [k for k in kits.kits(db) if _buildable(db, k) and mapdata.style_of(k + '_x') == want]
        cands.sort(key=lambda k: -sum(p.get('uses', 0) for p in kits.kit_pieces(db, k)['pieces'][:20]))
        kit = cands[0] if cands else None
    if not _buildable(db, kit):
        kit = 'in_c_plain' if _buildable(db, 'in_c_plain') else None
    return kit, bld, pr


def _cover(cells, cx, cy, T):
    n = got = 0
    half = T / 2.0
    for ix in range(int(math.floor((cx - half) / ss.GRID)), int(math.ceil((cx + half) / ss.GRID))):
        for iy in range(int(math.floor((cy - half) / ss.GRID)), int(math.ceil((cy + half) / ss.GRID))):
            n += 1
            got += (ix, iy) in cells
    return got / float(n or 1)


def _tiles_in(cells, T, keep_door=True, cover=COVER):
    """The tiles (i, j) whose centre (i*T, (j+0.5)*T) lies over the outline by at least cover, joined to
    the door's tile (0, 0)."""
    if not cells:
        return set()
    xs = [c[0] * ss.GRID for c in cells]
    ys = [c[1] * ss.GRID for c in cells]
    i0, i1 = int(math.floor(min(xs) / T)) - 1, int(math.ceil(max(xs) / T)) + 1
    j0, j1 = int(math.floor(min(ys) / T)) - 1, int(math.ceil(max(ys) / T)) + 1
    tiles = {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1) if _cover(cells, i * T, (j + 0.5) * T, T) >= cover}
    if keep_door:
        tiles.add((0, 0))
    # (only what joins the door's tile)
    seen, todo = set(), [(0, 0)] if (0, 0) in tiles else []
    while todo:
        t = todo.pop()
        if t in seen:
            continue
        seen.add(t)
        todo += [n for n in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1)) if n in tiles]
    return seen


def _split(tiles, parts=None, always=False, room_max=None, rng=None, sizes=None):
    """A floor's tiles cut into rooms: first where the building's parts meet (parts: tile -> part; always
    for a prefab of the game's buildings, a room or more per building; for a building only when the floor
    must be cut anyway: the game's rooms change across a wall inside the outline 1.5 times as often as
    within one enclosure, 159 buildings, exterior-interior-mapping.md), then by size."""
    if parts:
        groups = {}
        for t in tiles:
            groups.setdefault(parts.get(t), set()).add(t)
        if len(groups) > 1 and (always or len(tiles) > (room_max or ROOM_MAX)):
            out = []
            for g in groups.values():
                for comp in _components(g):
                    out += _split_size(comp, room_max, rng, sizes)
            return _merge_scraps(out)
    return _split_size(tiles, room_max, rng, sizes)


def _split_size(tiles, room_max=None, rng=None, sizes=None):
    """A floor's tiles cut into rooms of at most ROOM_MAX tiles: across the longer side, through the
    middle, again and again. [set of tiles] (each joined). With a dealer (rng), the game's way instead
    (_split_organic)."""
    if rng is not None:
        return _split_organic(tiles, rng, sizes or room_sizes(None), room_max)
    def parts(ts):
        ts = set(ts)
        if len(ts) <= (room_max or ROOM_MAX):
            return [ts]
        xs, ys = [t[0] for t in ts], [t[1] for t in ts]
        if max(xs) - min(xs) >= max(ys) - min(ys):
            cut = (min(xs) + max(xs) + 1) // 2
            a, b = {t for t in ts if t[0] < cut}, {t for t in ts if t[0] >= cut}
        else:
            cut = (min(ys) + max(ys) + 1) // 2
            a, b = {t for t in ts if t[1] < cut}, {t for t in ts if t[1] >= cut}
        if not a or not b:
            return [ts]
        out = []
        for half in (a, b):
            for comp in _components(half):
                out += parts(comp)
        return out
    return _merge_scraps(parts(tiles))


def _merge_scraps(rooms):
    """(a one-tile scrap goes back into the room beside it)"""
    merged = True
    while merged:
        merged = False
        for r in rooms:
            if len(r) == 1 and len(rooms) > 1:
                t = next(iter(r))
                nb = next((o for o in rooms if o is not r and any(n in o for n in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1)))), None)
                if nb is not None:
                    nb |= r
                    rooms.remove(r)
                    merged = True
                    break
    return rooms


# The game's own storeys, cut into rooms (layoutsurvey's rooms, by style family): how big its rooms are, how many
# tiles a storey gives each room, how often a room is one tile wide. Halving a floor through the middle until every
# room is small gave rows of equal 2x2 and 3x3 rooms (the user's "too cookie cutter, lots of little 2x2s instead of
# an organic house", 2026-10-30); the game's storeys have a big room and smaller ones round it.
ORGANIC_TRIES = 48
_SIZES = {}


def room_sizes(db, fam=None):
    """{'p': {tiles: share}, 'per_room': tiles a room (median, by storey), 'one_wide': share, 'n'} for the family, else
    every family's; from the game's own storeys when the layout survey is to hand, else a fallback measured once."""
    rooms = None
    if db is not None:
        try:
            import layoutsurvey
            s = layoutsurvey.ready(db)
            rooms = s and s.get('rooms')
        except Exception:
            rooms = None
    if not rooms:
        return dict(ROOMS_FALLBACK)
    key = (id(rooms), fam)
    if key in _SIZES:
        return _SIZES[key]
    pick = [r for r in rooms if r.get('family') == fam] if fam else []
    if len(pick) < 40:
        pick = rooms
    from collections import Counter, defaultdict
    # (a one-tile space is a nook or an alcove off a room, which the builder doesn't make: left out of the counts)
    real = [r for r in pick if int(r.get('tiles') or 0) >= 2]
    hist = Counter(min(int(r['tiles']), 40) for r in real)
    tot = float(sum(hist.values())) or 1.0
    lv = defaultdict(list)
    for r in real:
        lv[(r['cell'], r['level'])].append(int(r['tiles']))
    rooms_at, big = defaultdict(list), []
    for v in lv.values():
        rooms_at[min(sum(v) // 4, 9)].append(len(v))
        if len(v) >= 2:
            big.append(max(v) / float(sum(v)))
    by = {}
    for band_ in range(10):
        v = sorted(rooms_at.get(band_) or [])
        if len(v) >= 5:
            by[band_] = v
    big.sort()
    out = {'p': {k: v / tot for k, v in hist.items()}, 'rooms_at': by, 'biggest': big[len(big) // 2] if big else ROOMS_FALLBACK['biggest'],
           'one_wide': sum(1 for r in real if r.get('short') == 1 and not r.get('corridor')) / max(1.0, len(real)), 'n': len(real)}
    _SIZES[key] = out
    return out


def _split_organic(tiles, rng, sizes, room_max=None):
    """A storey's tiles cut into rooms the game's way: as many rooms as the game gives a storey this size, made by
    straight cuts at any line (not only the middle); of ORGANIC_TRIES such cuttings, the one whose room sizes the
    game makes most often, few one-wide rooms, none longer than three times its width. [set of tiles]."""
    tiles = set(tiles)
    n_t = len(tiles)
    if n_t <= 3:
        return [tiles]
    big = room_max or ROOM_MAX
    # (as many rooms as one of the game's storeys this size, picked at random from them: a small floor most often
    # stays one room)
    ra = sizes.get('rooms_at') or ROOMS_FALLBACK['rooms_at']
    band_ = min(n_t // 4, 9)
    while band_ not in ra and band_ > 0:
        band_ -= 1
    want = rng.choice(ra.get(band_) or [1])
    if n_t > 39:
        want = int(round(want * n_t / 38.0))       # (past the survey's bands: as many again for each band's worth)
    want = max(want, int(math.ceil(n_t / float(big * 3))))
    if want <= 1:
        return [tiles]
    p = sizes['p']
    floor_p = 0.2 / (len(p) + 40)

    def cut(ts):
        xs, ys = [t[0] for t in ts], [t[1] for t in ts]
        w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        axis = 0 if (w > h if rng.random() < 0.8 else w <= h) else 1
        lo, span = (min(xs), w) if axis == 0 else (min(ys), h)
        if span < 2:
            axis, (lo, span) = 1 - axis, ((min(xs), w) if axis == 1 else (min(ys), h))
            if span < 2:
                return None
        # (any line, two in from each side where it can be)
        edge = 2 if span >= 4 else 1
        at = lo + rng.randint(edge, span - edge)
        a = {t for t in ts if t[axis] < at}
        b_ = ts - a
        return (a, b_) if a and b_ else None

    def one():
        rooms = [tiles]
        guard = 0
        while len(rooms) < want and guard < want * 6:
            guard += 1
            # (the bigger rooms cut more often; a room under four tiles never)
            cand = [r for r in rooms if len(r) >= 4]
            if not cand:
                break
            r = rng.choices(cand, weights=[len(x) ** 1.5 for x in cand])[0]
            c = cut(r)
            if not c:
                continue
            rooms.remove(r)
            for half in c:
                rooms += _components(half)
        return _merge_scraps(rooms)

    def score(rooms):
        sc = 0.0
        for r in rooms:
            xs, ys = [t[0] for t in r], [t[1] for t in r]
            w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            sc += math.log(p.get(min(len(r), 40), 0.0) + floor_p)
            if min(w, h) == 1 and len(r) > 1:
                sc += math.log(max(sizes['one_wide'], 0.01))
            if max(w, h) > 3 * min(w, h) and len(r) > 3:
                sc -= 2.0
            if len(r) > big * 2:
                sc -= 3.0
        sc /= len(rooms)
        # (the biggest room's share of the storey, against the game's typical one; the way in most often the biggest
        # room, 7 in 10 of the game's; the door's tile is (0, 0))
        ls = [len(r) for r in rooms]
        if len(ls) >= 2:
            sc -= 3.0 * abs(max(ls) / float(sum(ls)) - sizes.get('biggest', 0.6))
            door = next((r for r in rooms if (0, 0) in r), None)
            if door is not None:
                sc += math.log(0.7 if len(door) == max(ls) else 0.3)
        return sc - abs(len(rooms) - want) * 0.5

    best, best_sc = None, None
    for _ in range(ORGANIC_TRIES):
        rooms = one()
        s_ = score(rooms)
        if best_sc is None or s_ > best_sc:
            best, best_sc = rooms, s_
    return best


def _components(ts):
    ts = set(ts)
    out = []
    while ts:
        t = ts.pop()
        comp, todo = {t}, [t]
        while todo:
            x, y = todo.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in ts:
                    ts.discard(n)
                    comp.add(n)
                    todo.append(n)
        out.append(comp)
    return out


ROOM_NAMES = {0: ['Hall', 'Room', 'Back Room', 'Side Room', 'Store'], 1: ['Upstairs', 'Bedroom', 'Study', 'Back Bedroom'],
              2: ['Top Floor', 'Attic Room', 'Loft']}


FLOORS_MAX = 4                   # the most floors asked for by number (the builder's stairs climb that far)


def _family(kit):
    import layoutsurvey
    try:
        return layoutsurvey.family(kits.split_style(kit)[0])
    except Exception:
        return None


def _dealer(b, floor):
    """The rooms' dealer for a building's floor: the same rooms each time for the same building, others for 🎲 (b['seed'])."""
    return random.Random(zlib.crc32(('%s|%s|%d' % (b['cell'], (b['door'] or {}).get('k'), floor)).encode('utf-8')) + 7919 * int(b.get('seed') or 0))


def tall_floors(b):
    """How many storeys a building is tall over its door's sill (1 at least, FLOORS_MAX at most): the most floors
    worth asking for."""
    if not b.get('frame') or not b.get('group'):
        return 1
    # (a storey a STOREY, about 100 of roof over the top one: a one-storey Hlaalu house is ~350 over its sill)
    h = max(g['box'][5] for g in b['group']) - b['frame'].z
    return max(1, min(FLOORS_MAX, int(round((h - 100) / float(ss.STOREY)))))


def _plan(db, b, kit=None, cover=COVER, floors=None, ch=None, tiles=None, force=False):
    """The interior for a building at one cover and floor count: {'style', 'tile', 'rooms', 'doors', 'exit', 'tiles', 'floors', 'notes',
    'prediction', 'ratio'} in the builder's terms."""
    if b['door'] is None:
        raise EditError('The building has no door: put one in a wall first.')
    ch = ch or check(db, b)
    if not ch['outline'] or not ch['outline'].get('cells'):
        raise EditError('The building has no inside to build in: %s' % '; '.join(l['text'] for l in ch['lines'] if l['sev'] == 'error'))
    kit0, bld, pr = pick_style(db, b)
    kit = kit or kit0
    notes = []
    if pr is None:
        notes.append('The Workshop is still learning how the game\'s interiors fit their buildings (about five minutes, once, '
                     'in the background): the style and the number of floors are a first guess until then.')
    if not _buildable(db, kit):
        raise EditError('No building style to build this in.')
    kp = kits.kit_pieces(db, kit)
    T = kp['tile']
    g_cells = set(map(tuple, ch['outline']['cells']))
    ground = _tiles_in(g_cells, T, cover=cover)
    per = {0: ground}
    want = floors if floors is not None else ((pr or {}).get('floors') or 1)
    if tiles:
        # (a prefab planned as a volume: its tiles, in the door's frame, are the interior's, storey by storey;
        # an upper storey only over the one below, the door's tile always in)
        per = {}
        for t in tiles:
            i, j, k = t[0], t[1], t[2]
            if 0 <= int(k) <= 2:
                per.setdefault(int(k), set()).add((int(i), int(j)))
        per.setdefault(0, set()).add((0, 0))
        for k in (1, 2):
            if k in per:
                per[k] &= per[k - 1]
                if len(per[k]) < 2:
                    del per[k]
            if k not in per:
                for k2 in [x for x in per if x > k]:
                    del per[k2]
        ground = per[0]
    st_ = (kits.stairs(db, kit) or {}).get('storey') or kp.get('height') or ss.STOREY
    for k, u in enumerate([] if tiles else ch['ups'], start=1):
        if k >= want or k > 2:
            break
        if not (u['closed'] and u['area'] >= UP_MIN * ch['outline']['area']):
            if force:
                break                            # (laid over the floor below, after this loop)
            notes.append('Floor %d left out: the walls %d storey%s up don\'t close round.' % (k + 1, k, '' if k == 1 else 's'))
            break
        up = _tiles_in(set(map(tuple, u['cells'])), T, keep_door=False, cover=cover) & per[k - 1]
        if len(up) < 2:
            break
        per[k] = up
    # (floors asked for by number, the user's "the exterior looks like 3 stories" 2026-10-28: those the walls up there
    # don't give are laid over the floor below, up to as many storeys as the building is tall over the door's sill)
    if force and not tiles:
        for k in range(1, min(want, FLOORS_MAX)):
            if k not in per:
                per[k] = set(per[k - 1])
                notes.append('Floor %d laid over the floor below (the walls up there don\'t say where).' % (k + 1))
    # a door up high outside means a floor up there (the game's: 119 of 119), reaching the tile behind the door
    for k, t_up in _upper_tiles(b, per.get(0, set()), T, st_):
        for kk in range(1, k + 1):
            if kk not in per:
                per[kk] = set(per[kk - 1])
                notes.append('Floor %d: a door up outside leads into it, so it is there though the walls up there don\'t close round.' % (kk + 1))
        if t_up in per[k - 1]:
            per[k].add(t_up)
    # which part of the building each tile is in: for a prefab, which of the game's buildings stands over it
    # (a room or more for each); for a building, the enclosures its outline's inner walls part (the cut lines
    # when a floor must be cut)
    tile_parts, always = {}, False
    if tiles and any(len(t) > 3 for t in tiles):
        tile_parts = {(int(t[0]), int(t[1])): t[3] for t in tiles if len(t) > 3}
        always = True
    else:
        pc = (ch['outline'] or {}).get('parts') or {}
        for (i, j) in per.get(0, ()):
            cx, cy = int(math.floor(i * T / ss.GRID)), int(math.floor((j + 0.5) * T / ss.GRID))
            e = pc.get((cx, cy))
            if e is None:
                near = [pc[(cx + dx, cy + dy)] for dx in range(-3, 4) for dy in range(-3, 4) if (cx + dx, cy + dy) in pc]
                e = max(set(near), key=near.count) if near else None
            if e is not None:
                tile_parts[(i, j)] = e
    # (a shop's sign at the door: the ground floor's front room is the shop, and big)
    trade = shop_trade(b)
    sizes = room_sizes(db, _family(kit))
    rooms, where = [], {}
    for f, ts in sorted(per.items()):
        rng = _dealer(b, f)
        for n, comp in enumerate(_split(ts, tile_parts, always, SHOP_ROOM_MAX if trade else None, rng, sizes) if f == 0 else
                                 [c for comp in _components(ts) for c in _split(comp, tile_parts, always, None, rng, sizes)]):
            names = ROOM_NAMES.get(f, ['Room'])
            nm = names[min(n, len(names) - 1)]
            if n >= len(names) - 1 and n > 0:
                nm = '%s %d' % (names[-1], n - len(names) + 2)
            xs, ys = [t[0] for t in comp], [t[1] for t in comp]
            x0, y0 = min(xs), min(ys)
            w, h = max(xs) - x0 + 1, max(ys) - y0 + 1
            cut = [[x, y] for x in range(x0, x0 + w) for y in range(y0, y0 + h) if (x, y) not in comp]
            r = {'name': nm, 'x': x0, 'y': y0, 'w': w, 'h': h, 'floor': f}
            if cut:
                r['cut'] = cut
            for t in comp:
                where[(t[0], t[1], f)] = len(rooms)
            rooms.append(r)
    # what the building's features outside mean inside: a chimney's hearth, its windows (exterior-interior-mapping.md)
    notes += map_features(db, b, rooms, where, T, st_)
    # the door's room first in its name ("Hall"), and doorways between rooms side by side on a floor
    exit_room = where[(0, 0, 0)]
    if trade:
        rooms[exit_room]['name'] = TRADE_ROOM[trade[0]]
        notes.append('A %s\'s sign at the door (%s): the room behind the door is the %s.' % (
            trade[0] if trade[0] != 'shop' else 'trader', trade[1], TRADE_ROOM[trade[0]].lower()))
    dl = set()
    for (x, y, f), a in where.items():
        for n in ((x + 1, y, f), (x, y + 1, f)):
            bb = where.get(n)
            if bb is not None and bb != a:
                dl.add(tuple(sorted((a, bb))))
    # (room names must be unique)
    seen = {}
    for r in rooms:
        if r['name'].lower() in seen:
            seen[r['name'].lower()] += 1
            r['name'] = '%s %d' % (r['name'], seen[r['name'].lower()])
        seen[r['name'].lower()] = seen.get(r['name'].lower(), 1)
    door_list = []
    for a, c in sorted(dl):
        door_list.append({'rooms': [rooms[a]['name'], rooms[c]['name']]})
    exit_ = {'room': rooms[exit_room]['name'], 'side': 'S', 'x': 0, 'y': 0}
    area = len(ground) * T * T
    ratio = area / float(ch['outline']['area'])
    # (the share of the ground floor outside the walls: what the fit check will measure, from the tiles' cover)
    out_share = sum(1 - _cover(g_cells, t[0] * T, (t[1] + 0.5) * T, T) for t in ground) / float(len(ground) or 1)
    band = (pr or {}).get('ratio')
    if band:
        notes.append('Ground floor %d tiles: %.2f of the area inside the walls (the game\'s own %s interiors: %.2f to %.2f, '
                     'from %d pairs by %s).' % (len(ground), ratio, (pr or {}).get('style') or '', band[1], band[3], pr['n'],
                                                'this building model' if pr['from'] == 'model' else 'style'))
    tiles = [[t[0], t[1], f] for f, ts in sorted(per.items()) for t in sorted(ts)]
    return {'style': kit, 'style_name': kits.friendly(kit), 'tile': T, 'rooms': rooms, 'doors': door_list, 'exit': exit_,
            'tiles': tiles, 'floors': sorted(per), 'notes': notes, 'prediction': pr, 'ratio': round(ratio, 3),
            'out': round(out_share, 3), 'check': ch['lines'], 'ok': ch['ok']}


# the tiles' cover tried: tighter than half (the game's own often keep inside the walls) to any tile touching inside
COVERS = (0.8, 0.65, COVER, 0.35, 0.2, 0.02)


def plan(db, b, kit=None, floors=None, tiles=None, tolerance='usual'):
    """The interior for a building, sized the way the game sizes its own for this building (model, else
    family, else style; shellsurvey.py): every floor the building's height and closed outlines allow, the
    share of the ground floor outside the walls within what the game's own interiors take (p75), and the
    area nearest the game's typical one for it (median); the first of those the builder can put stairs
    in. Raises EditError when nothing builds."""
    ch = check(db, b)
    if tiles:
        pl = _plan(db, b, kit=kit, floors=floors, ch=ch, tiles=tiles)
        try:
            builder.plan(db, pl['style'], pl['rooms'], None, 'auto', pl['doors'])
            pl['notes'].append('The rooms follow the volume the building was planned from.')
            return pl
        except EditError as e:
            print('prefab tiles: %s; planning from the outline' % e)
    force = floors is not None
    pl0 = _plan(db, b, kit=kit, cover=COVER, floors=floors, ch=ch, force=force)
    pr = pl0.get('prediction') or {}
    band, share = pr.get('ratio'), pr.get('share')
    want = len(pl0['floors']) if floors is None else floors
    med = band[2] if band else 1.0
    # (the tolerance, Plan a prefab's Close / Usual / Loose: how far the interior may stand out of its building:
    # the game's median for the building, its p75, or as far as Bethesda's own interiors stand out of theirs)
    lim = share[3] if share else 0.3
    grow = band[4] if band else None
    if tolerance == 'close' and share:
        lim = share[2]
    elif tolerance == 'loose':
        beth = (ss.source_bands(db) or {}).get('bethesda')
        lim = max(lim, beth['share'] if beth else lim)
        grow = grow * 1.5 if grow else None
    cands, seen = [], set()
    for n in range(max(1, want), 0, -1):
        for cover in COVERS:
            pl = pl0 if (cover == COVER and n == want) else _plan(db, b, kit=kit, cover=cover, floors=n, ch=ch, force=force)
            sig = tuple(map(tuple, pl['tiles']))
            if sig in seen or not pl['tiles']:
                continue
            seen.add(sig)
            if grow and cover < COVER and pl['ratio'] > grow:
                continue                         # (bigger than the game ever makes them for this building)
            cands.append(((want - len(pl['floors']), pl['out'] > lim + 0.02, abs(math.log(max(pl['ratio'], 0.05) / max(med, 0.05)))),
                          cover, pl))
    cands.sort(key=lambda c: c[0])
    why = None
    for _key, cover, pl in cands:
        try:
            builder.plan(db, pl['style'], pl['rooms'], None, 'auto', pl['doors'])
        except EditError as e:
            why = str(e)
            continue
        if pl['out'] > lim + 0.02:
            pl['notes'].append('About %d%% of the ground floor lies outside the walls, more than the game\'s own interiors for this '
                               'building take (up to %d%%): the stairs need the room.' % (round(pl['out'] * 100), round(lim * 100)))
        elif cover < COVER:
            pl['notes'].append('Laid a little over the walls, as the game\'s own interiors for this building are (about %d%% of the '
                               'ground floor outside them; the game\'s: up to %d%%).' % (round(pl['out'] * 100), round(lim * 100)))
        if len(pl['floors']) < want:
            pl['notes'].append('%d floor%s instead of %d: the stairs don\'t fit in a building this size.' % (
                len(pl['floors']), '' if len(pl['floors']) == 1 else 's', want))
        return pl
    pl0['problem'] = why
    return pl0

# The game's cellars, measured on 472 of its interiors behind buildings (scratchpad cellarlab.py, 2026-10-27): the
# share of a style's houses with a floor below the one their door is on, and that floor's size against the ground
# floor's (median, p90). They are bigger than the house more often than not, and run out past its walls: under the
# ground nothing shows (the user's Council Club, Balmora: a plain Hlaalu shell over long cellar halls).
CELLARS = {'Hlaalu': (0.57, 1.4, 3.0), 'Velothi': (0.36, 1.2, 4.1), 'Imperial': (0.49, 1.17, 3.0), 'Common': (0.32, 0.87, 1.0),
           'Mournhold': (0.47, 1.07, 1.57), 'Indoril': (0.62, 1.4, 1.83), 'Dunmer': (0.5, 1.13, 1.5), 'ALL': (0.5, 1.3, 3.0)}
ROOM_NAMES[-1] = ['Cellar', 'Storeroom', 'Wine Cellar', 'Cellar Room']


def cellar_band(style):
    s = CELLARS.get(style or '', CELLARS['ALL'])
    return {'style': style if style in CELLARS else None, 'share': s[0], 'usual': s[1], 'big': s[2]}


def _with_cellar(db, b, pl, size):
    """The plan with a cellar under it (size 'usual' or 'big': the game's median or p90 for the style, against the ground
    floor): under the house, and where the game's ratio wants more, a wing out past the walls to one side. Rooms on
    floor -1 (the builder's cellar), doorways between them. A new plan; the given one is left as it was."""
    import copy
    pl = copy.deepcopy(pl)
    ground = {(t[0], t[1]) for t in pl['tiles'] if t[2] == 0}
    if not ground:
        return pl
    band = cellar_band(((pl.get('prediction') or {}).get('style')) or ss.style_of_group(b['group']))
    want = max(2, int(round(len(ground) * (band['big'] if size == 'big' else band['usual']))))
    if size == 'small':
        want = min(want, len(ground))           # (the fallback: under the house alone)
    xs, ys = [t[0] for t in ground], [t[1] for t in ground]
    if want <= len(ground):
        # (smaller than the house: the back of it, joined up from the back-most tile)
        start = max(ground, key=lambda t: (t[1], -abs(t[0])))
        cel, todo = {start}, [start]
        while todo and len(cel) < want:
            x, y = todo.pop(0)
            for n in ((x, y - 1), (x + 1, y), (x - 1, y), (x, y + 1)):
                if n in ground and n not in cel and len(cel) < want:
                    cel.add(n)
                    todo.append(n)
    else:
        # (under the house, then out past its walls all round, leaning to one side and the back: a tile at a time,
        # the one with most of the cellar beside it, so it grows as a block. It was a wing two or three tiles
        # wide out to one side, as long as the rest took: the user's "a very long cellar 2 tiles wide")
        cel = set(ground)
        rng = random.Random(zlib.crc32(('%s|%s' % (b['cell'], (b['door'] or {}).get('k'))).encode('utf-8')) + 7919 * int(b.get('seed') or 0))
        lean = (rng.choice((-1, 1)), 1)
        mx, my = sum(xs) / float(len(xs)), sum(ys) / float(len(ys))
        while len(cel) < want:
            front = {n for (x, y) in cel for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if n not in cel and n[1] >= 0}
            if not front:
                break
            def key(t):
                nb = sum(1 for n in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1)) if n in cel)
                return (-nb, math.hypot(t[0] - mx - lean[0] * 1.5, t[1] - my - lean[1] * 1.5), rng.random())
            cel.add(min(front, key=key))
    rooms = pl['rooms']
    where = {}
    first = len(rooms)
    sizes = room_sizes(db, _family(pl.get('style') or ''))
    rng_c = _dealer(b, -1)
    for n, comp in enumerate(c for comp in _components(cel) for c in _split(comp, rng=rng_c, sizes=sizes)):
        names = ROOM_NAMES[-1]
        nm = names[min(n, len(names) - 1)] if n < len(names) else '%s %d' % (names[-1], n - len(names) + 2)
        cx_, cy_ = [t[0] for t in comp], [t[1] for t in comp]
        x0, y0 = min(cx_), min(cy_)
        w, h = max(cx_) - x0 + 1, max(cy_) - y0 + 1
        r = {'name': nm, 'x': x0, 'y': y0, 'w': w, 'h': h, 'floor': -1}
        cut = [[xx, yy] for xx in range(x0, x0 + w) for yy in range(y0, y0 + h) if (xx, yy) not in comp]
        if cut:
            r['cut'] = cut
        for t in comp:
            where[t] = len(rooms)
        rooms.append(r)
    names_ = {r['name'].lower() for r in rooms[:first]}
    for r in rooms[first:]:
        while r['name'].lower() in names_:
            r['name'] += ' Below'
        names_.add(r['name'].lower())
    for (x, y), a in where.items():
        for nb in ((x + 1, y), (x, y + 1)):
            c = where.get(nb)
            if c is not None and c != a:
                pair = [rooms[a]['name'], rooms[c]['name']]
                if not any(sorted(d['rooms']) == sorted(pair) for d in pl['doors']):
                    pl['doors'].append({'rooms': pair})
    pl['tiles'] = [t for t in pl['tiles'] if t[2] != -1] + [[t[0], t[1], -1] for t in sorted(cel)]
    pl['floors'] = sorted(set(pl['floors']) | {-1})
    out_ = len(cel - ground)
    pl['notes'].append('A cellar of %d tiles, %.1f times the ground floor (the game\'s %s houses: %d%% have one, %.1f times the ground '
                       'floor at the median, %.1f for the big ones)%s.' % (
                           len(cel), len(cel) / float(len(ground)), band['style'] or 'own', round(band['share'] * 100), band['usual'], band['big'],
                           ', %d of them out past the walls, under the ground' % out_ if out_ else ', under the house'))
    return pl


def plan_with_cellar(db, b, pl, cellar):
    """The plan with the cellar asked for, if the builder can put the way down in: the wing first, then a cellar
    under the house alone; else the plan as it was, with a note why."""
    if cellar not in ('usual', 'big'):
        return pl
    why = 'no room for it'
    for size in (cellar, 'small'):
        try:
            p2 = _with_cellar(db, b, pl, size)
        except Exception as e:
            print('cellar: %s' % e)
            continue
        try:
            builder.plan(db, p2['style'], p2['rooms'], None, 'auto', p2['doors'])
            return p2
        except EditError as e:
            why = str(e)
            continue
    pl = dict(pl, notes=pl['notes'] + ['No cellar: the way down doesn\'t fit (%s).' % why])
    return pl


def preview(db, cell_key, ref_key, door_key=None, tolerance='usual', cellar=None, floors=None, seed=0):
    """For the map: the building's check, the plan, and the planned tiles' corners in the world (to
    draw over the exterior), without building anything."""
    b = building_at(db, cell_key, ref_key, door_key)
    b['seed'] = int(seed or 0)                  # (🎲 Other rooms: another cut of the same space)
    out = {'pieces': [g['k'] for g in b['group']], 'doors': [{'k': d['k'], 'id': d['id'], 'p': d['p'][:3]} for d in b['doors']],
           'door': b['door']['k'] if b['door'] else None}
    import podtwins
    pods = podtwins.pods_of(db, b)
    if pods:
        # (Telvanni: a place per pod with a door, its interior twin; no tile plan)
        ch = check(db, b)
        with_door = sum(1 for pod, _t in pods if any(podtwins.reaches(d, pod) for d in b['doors']))
        out.update({'ok': with_door > 0, 'check': ch['lines'] + [{'sev': 'ok' if with_door else 'error',
                    'text': '%d piece%s the game makes a ready-made interior for (%s), %d with a door outside: each becomes a place of its own, that interior '
                            'fitted out as one of the game\'s own' % (len(pods), '' if len(pods) == 1 else 's', ', '.join(sorted({t for _p, t in pods})), with_door)}],
                    'plan': {'style': 'pods', 'style_name': 'Ready-made interiors', 'tile': None, 'rooms': [], 'doors': [], 'exit': None,
                             'floors': [0], 'notes': ['The game builds these as one ready-made piece each (a Telvanni pod, a shack, a hut, '
                                                      'a tent): a place each; bridges between pods are walkways outdoors.'], 'ratio': None},
                    'tiles': [], 'sill': round(b['frame'].z) if b['frame'] else 0, 'name': _suggest_name(db, b)})
        return out
    try:
        pl = plan_with_cellar(db, b, plan(db, b, floors=floors, tolerance=tolerance), cellar)
    except EditError as e:
        ch = check(db, b)
        out.update({'ok': False, 'check': ch['lines'], 'error': str(e)})
        return out
    # (the floors above ground: as many as asked, else the game's way for this building; up to its height in storeys)
    out['floors_up'] = len([f for f in pl['floors'] if f >= 0])
    out['floors_max'] = max(tall_floors(b), out['floors_up'])
    out['floors_chosen'] = floors
    out['cellar'] = dict(cellar_band(((pl.get('prediction') or {}).get('style')) or ss.style_of_group(b['group'])), chosen=cellar or None)
    T, fr = pl['tile'], b['frame']
    polys = []
    for i, j, f in pl['tiles']:
        cs = []
        for dx, dy in ((-0.5, 0), (0.5, 0), (0.5, 1), (-0.5, 1)):
            wx, wy = fr.back((i + dx) * T, (j + dy) * T)
            cs.append([round(wx), round(wy)])
        polys.append({'f': f, 'c': cs})
    out.update({'ok': pl['ok'], 'check': pl['check'], 'plan': {k: pl[k] for k in ('style', 'style_name', 'tile', 'rooms', 'doors', 'exit', 'floors', 'notes', 'ratio')},
                'tiles': polys, 'sill': round(fr.z), 'name': _suggest_name(db, b)})
    try:
        out['plan']['dry'] = builder.plan(db, pl['style'], pl['rooms'], None, 'auto', pl['doors']).get('notes', [])
    except EditError as e:
        out['plan']['problem'] = str(e)
    return out


def _suggest_name(db, b):
    info = mapdata.cell_info(db, b['cell']) or {}
    town = info.get('name') or info.get('region') or 'Outside'
    base = '%s, New House' % town
    n, name = 1, base
    while mapdata.cell_info(db, name.lower()) or name.lower() in db.project.cells:
        n += 1
        name = '%s %d' % (base, n)
    return name


# ---------------------------------------------------------------- what the building's features mean inside
# (packaging/nexus/exterior-interior-mapping.md, measured on the game's 678 pairs, 2026-10-24: a door up high
# outside lands above the ground floor 119 times in 119; a building with a chimney has a hearth inside in 80%,
# within 384 of it in 55%; a building with window pieces has a window or a light shaft inside in 97%, within
# 256 of one in 62%)

CHIMNEY_RE = re.compile(r'chimney|chimny|flue')
WINDOW_RE = re.compile(r'window|_win_|shutter')
KITCHEN_RE = re.compile(r'kitchen', re.I)
UP_DOOR = 150                 # a door this much higher than the front door's sill is a way into an upper floor
# a shop's sign at its door (not a signpost or a bare sign base) naming its trade: the room behind the door is that
# trade's shop, as big as the game's are (measured on the game's 958 pairs, 2026-10-24: a place with a trade sign
# at its door is that trade in 14 of 30, another trade's shop in 2, the rest guilds and banks; a shop's counter is in
# the room at the door in 48 of 67, and that room is 78% of its ground floor)
SHOP_SIGN = re.compile(r'sign(?!post|base)')
SIGN_REACH = 300
SIGN_TRADES = (('smith', 'smithy'), ('arms', 'smithy'), ('weapon', 'smithy'), ('armor', 'smithy'), ('armour', 'smithy'),
               ('alchem', 'alchemist'), ('apothec', 'alchemist'), ('potion', 'alchemist'), ('enchant', 'enchanter'),
               ('magic', 'enchanter'), ('book', 'bookseller'), ('cloth', 'clothier'), ('tailor', 'clothier'), ('outfit', 'clothier'),
               ('pawn', 'pawnbroker'), ('trader', 'shop'), ('goods', 'shop'), ('general', 'shop'), ('merchant', 'shop'))
TRADE_ROOM = {'smithy': 'Smithy', 'alchemist': "Alchemist's Shop", 'enchanter': "Enchanter's Shop", 'bookseller': 'Bookshop',
              'clothier': "Clothier's Shop", 'pawnbroker': 'Pawnshop', 'shop': 'Shop'}
SHOP_ROOM_MAX = 16            # the shop room may be this big before it is cut (the game's: most of the ground floor)



def shop_trade(b):
    """The trade a shop sign at the building's front door names, or None: (trade, sign id)."""
    d = b.get('door')
    if not d:
        return None
    for it in b.get('items') or ():
        if it is d or not SHOP_SIGN.search(it['low']):
            continue
        if math.hypot(it['p'][0] - d['p'][0], it['p'][1] - d['p'][1]) > SIGN_REACH or abs(it['p'][2] - d['p'][2]) > 400:
            continue
        for w, t in SIGN_TRADES:
            if w in it['low']:
                return t, it['id']
    return None
WINDOW_REACH = 1.2            # a window outside belongs to a tile's wall within this many tiles of it


def features(b):
    """The building's chimneys and window pieces in the door's frame: {'chimneys': [(x, y)], 'windows':
    [(x, y, height over the sill)]}."""
    fr = b['frame']
    out = {'chimneys': [], 'windows': []}
    for it in b['group']:
        cx, cy = (it['box'][0] + it['box'][2]) / 2, (it['box'][1] + it['box'][3]) / 2
        lx, ly = fr.to(cx, cy)
        if CHIMNEY_RE.search(it['low']):
            out['chimneys'].append((lx, ly))
        elif WINDOW_RE.search(it['low']):
            out['windows'].append((lx, ly, (it['box'][4] + it['box'][5]) / 2 - fr.z))
    return out


def map_features(db, b, rooms, where, T, storey):
    """Rooms told what stands outside them: the room under a chimney becomes the kitchen, its hearth on the
    wall nearest the chimney (builder's hearth_near); a wall with a window outside asks for a window inside
    (builder's windows). Returns notes."""
    if not b.get('frame'):
        return []
    f = features(b)
    notes = []
    ground = [(x, y) for (x, y, k) in where if k == 0]
    for lx, ly in f['chimneys']:
        px, py = lx / float(T), ly / float(T) - 0.5
        t = min(ground, key=lambda t: math.hypot(t[0] - px, t[1] - py), default=None)
        if t is None or math.hypot(t[0] - px, t[1] - py) > 3:
            continue                                  # (a chimney over no part of the plan)
        r = rooms[where[(t[0], t[1], 0)]]
        if r.get('hearth_near'):
            continue
        r['hearth_near'] = [round(px, 2), round(py, 2)]
        if not KITCHEN_RE.search(r['name']):
            was = r['name']
            r['name'] = 'Kitchen' if not any(x['name'] == 'Kitchen' for x in rooms) else 'Kitchen %d' % (1 + sum(1 for x in rooms if KITCHEN_RE.search(x['name'])))
            notes.append('A chimney outside: the %s under it is the kitchen, its hearth on the wall nearest the chimney.' % was.lower())
        else:
            notes.append('A chimney outside: the hearth inside goes on the wall nearest it.')
    n_win = 0
    for lx, ly, z in f['windows']:
        k = max(0, int(round((z - 140) / float(storey))))
        tiles = [(x, y) for (x, y, kk) in where if kk == k] or ground
        if not tiles:
            continue
        k = k if any(kk == k for (_x, _y, kk) in where) else 0
        px, py = lx / float(T), ly / float(T) - 0.5
        t = min(tiles, key=lambda t: math.hypot(t[0] - px, t[1] - py))
        dx, dy = px - t[0], py - t[1]
        if math.hypot(dx, dy) > WINDOW_REACH:
            continue
        side = ('E' if dx > 0 else 'W') if abs(dx) > abs(dy) else ('N' if dy > 0 else 'S')
        r = rooms[where[(t[0], t[1], k)]]
        r.setdefault('windows', []).append([t[0], t[1], side])
        n_win += 1
    if n_win:
        notes.append('%d window%s outside: a window inside on the same wall%s, where this style has window pieces.' % (
            n_win, '' if n_win == 1 else 's', '' if n_win == 1 else 's'))
    return notes


def _upper_doors(b):
    """The building's doors more than UP_DOOR over the front door's sill: [(door, sill)]."""
    fr = b.get('frame')
    if not fr or not b.get('door'):
        return []
    out = []
    for d in b['doors']:
        if d['k'] == b['door']['k'] or 'marker' in d['low']:
            continue
        sill = d['p'][2] + d['b'][2] * d['s']
        if sill - fr.z > UP_DOOR:
            out.append((d, sill))
    return out


def _upper_tiles(b, ground, T, storey):
    """For each door up high: (the floor it leads to, 1 or 2; the ground tile behind it, coming in from the
    door), for the plan to lay that floor out to it."""
    fr = b.get('frame')
    out = []
    for d, sill in _upper_doors(b):
        k = min(2, max(1, int(round((sill - fr.z) / float(storey)))))
        lx, ly = fr.to(d['p'][0], d['p'][1])
        ux, uy = _door_inward(d, b['centre'])
        fx, fy = fr.to(fr.ox + ux, fr.oy + uy)
        px, py = lx / float(T), ly / float(T) - 0.5
        t = None
        for s_ in range(0, 13):
            q = (int(round(px + fx * s_ * 0.25)), int(round(py + fy * s_ * 0.25)))
            if q in ground:
                t = q
                break
        if t is not None:
            out.append((k, t))
    return out


def _rect_hit(rooms, x, y, z, tol=100):
    return next((r for r in rooms if abs(r['floor'] - z) < tol and r['x_min'] <= x <= r['x_max'] and r['y_min'] <= y <= r['y_max']), None)


def upper_ways(db, b, out, idoor):
    """Each door of the building more than UP_DOOR over the front door's sill (up the outside stairs, onto
    a balcony) gets a door inside on the floor behind it, standing to its room's wall as the front door
    stands to the hall's, and the two lead to each other. Returns notes."""
    import fixit
    import furnish
    fr = b['frame']
    ups = _upper_doors(b)
    if not ups:
        return []
    notes = []
    key0 = out['key']
    cells = out.get('cells') or [{'key': key0, 'floor': 0}]
    by_floor = {c['floor']: c['key'] for c in cells}
    # the interior's frame as link_both laid it: straight in from the front door
    im = mapdata.cellmap(db, key0)
    near = [r['p'] for r in im['refs'] if r['k'] != idoor['k'] and r.get('arch')] or [idoor['p']]
    iu = _door_inward(idoor, (sum(p[0] for p in near) / len(near), sum(p[1] for p in near) / len(near)))
    isill = idoor['p'][2] + (idoor.get('b') or [0, 0, 0])[2] * (idoor.get('s') or 1.0)
    ifr = ss.Frame(idoor['p'][0], idoor['p'][1], isill, iu[0], iu[1])
    rooms0 = furnish.rooms(db, key0, trace=False)['rooms']
    front = min(rooms0, key=lambda r: abs(r['floor'] - isill))
    # how far the front door stands out from its room's edge, and up from its floor
    e = 0.0
    while e < 400 and _rect_hit([front], idoor['p'][0] + iu[0] * e, idoor['p'][1] + iu[1] * e, front['floor']) is None:
        e += 8
    dz_door = idoor['p'][2] - front['floor']
    floors0 = sorted({round(r['floor']) for r in rooms0})
    storey = (floors0[1] - floors0[0]) if len(floors0) > 1 else ss.STOREY
    c_ext = {}
    for d, sill in ups:
        k = max(1, int(round((sill - fr.z) / float(storey))))
        key = by_floor.get(k) or (key0 if len(cells) == 1 else None)
        if key is None:
            notes.append('The door %d up outside (%s) has no floor %d inside to lead to.' % (round(sill - fr.z), d['id'], k + 1))
            continue
        rooms_k = rooms0 if key == key0 else furnish.rooms(db, key, trace=False)['rooms']
        want_z = front['floor'] + k * storey if key == key0 else min(r['floor'] for r in rooms_k)
        lx, ly = fr.to(d['p'][0], d['p'][1])
        ux, uy = _door_inward(d, b['centre'])
        fdx, fdy = fr.to(fr.ox + ux, fr.oy + uy)
        px, py = ifr.back(lx, ly)
        bx, by = ifr.back(fdx, fdy)
        Dx, Dy = bx - ifr.ox, by - ifr.oy
        hit, s_ = None, -256.0
        while s_ < 3 * 256 and hit is None:
            hit = _rect_hit(rooms_k, px + Dx * s_, py + Dy * s_, want_z)
            s_ += 8
        if hit is None:
            notes.append('The door %d up outside (%s) has no room behind it upstairs: draw the upper floor out to it.' % (round(sill - fr.z), d['id']))
            continue
        ex, ey = px + Dx * (s_ - 8), py + Dy * (s_ - 8)          # (the room's edge, coming in from the door)
        nx, ny = ex - Dx * e, ey - Dy * e
        nz = hit['floor'] + dz_door
        rz = (idoor['p'][5] + math.atan2(Dx, Dy) - math.atan2(iu[0], iu[1])) % (2 * math.pi)
        r = fixit.apply(db, key, [{'op': 'place', 'id': idoor['id'], 'p': [round(nx, 2), round(ny, 2), round(nz, 2), 0, 0, round(rz, 5)],
                                   's': idoor.get('s') or 1.0}], commit=False)
        nk = r['changed'][0]
        in_pos = [nx + Dx * 110, ny + Dy * 110, hit['floor'] + 12, 0.0, 0.0, math.atan2(Dx, Dy) % (2 * math.pi)]
        out_pos = [d['p'][0] - ux * 110, d['p'][1] - uy * 110, sill + 12, 0.0, 0.0, math.atan2(-ux, -uy) % (2 * math.pi)]
        info = mapdata.cell_info(db, key)
        c, refs = editing._cell(db, d['cell'])
        ref = refs.get(d['k'])
        if ref is None:
            continue
        editing._store(c, d['k'], ref['origin'], ref['idx'], doors._set_link(ref['subs'], info['name'], in_pos))
        c2, refs2 = editing._cell(db, key)
        r2 = refs2[nk]
        editing._store(c2, nk, r2['origin'], r2['idx'], doors._set_link(r2['subs'], '', out_pos))
        c_ext[d['k']] = key
        notes.append('The door %d up outside (%s) leads into the %s on floor %d, and back.' % (round(sill - fr.z), d['id'], hit['name'], k + 1))
    if c_ext:
        editing.commit(db, 'Linked %d door%s up outside with the floors above in %s' % (len(c_ext), '' if len(c_ext) == 1 else 's',
                                                                                   editing.cell_label(db, key0)))
    return notes


# ---------------------------------------------------------------- building it

def build(db, cell_key, ref_key, name, door_key=None, kit=None, floors=None, tiles=None, tolerance='usual', cellar=None,
          seed=0, lighting='normal', lights=True):
    """Plan, build, link the doors both ways and put the northmarker in."""
    import release
    b = building_at(db, cell_key, ref_key, door_key)
    b['seed'] = int(seed or 0)
    if not tiles and not kit:
        # (a shell the game makes a ready-made interior for, a Telvanni pod, a shack, a hut, a tent: a place per\n        # shell, that piece turned to the door and fitted out as one of the game's own; podtwins.py)
        import podtwins
        if podtwins.pods_of(db, b):
            out = podtwins.build(db, b, name)
            out['plan'] = {'style_name': 'Ready-made interiors', 'tile': None, 'floors': [0], 'ratio': None,
                           'notes': ['%s: %s, the game\'s interior for %s, fitted out as its own %s (the most typical of %d).' % (
                               m['name'], m['twin'], m['pod'], m['from'], m.get('examples') or 0) for m in out['cells']] + out['notes']}
            out['northmarker'] = all(m.get('northmarker') for m in out['cells'])
            out['fits'] = {'ok': True, 'share': 0.0, 'jut': 0, 'text': 'Each interior is the piece the game makes for that shell: '
                                                                       'it fits as the game\'s own do.'}
            return out
    pl = plan_with_cellar(db, b, plan(db, b, kit=kit, floors=floors, tiles=tiles, tolerance=tolerance), cellar)
    if not pl['ok']:
        raise EditError('The building isn\'t closed and sound: %s' % '; '.join(l['text'] for l in pl['check'] if l['sev'] == 'error'))
    out = None
    for ex_ in (pl['exit'], {'room': pl['exit']['room'], 'side': 'S'}, {'room': pl['exit']['room'], 'side': 'E'},
                {'room': pl['exit']['room'], 'side': 'W'}):
        try:
            out = builder.build_house(db, name, pl['style'], pl['rooms'], pl['doors'], ex_, None, lighting or 'normal', lights is not False)
        except EditError as e:
            if 'way out' not in str(e):
                raise
            continue
        if ex_ is not pl['exit']:
            # (the kit has no door piece for that wall of the door's tile: the builder picks the spot on the
            # front wall, else a side wall, of the same room)
            pl['notes'].append('The way in moved %s: the %s pieces have no door for the tile behind the building\'s door.' % (
                'along the front wall' if ex_['side'] == 'S' else 'to a side wall', pl['style_name']))
        break
    if out is None:
        raise EditError('The %s pieces have no way out on any outside wall of the %s.' % (pl['style_name'], pl['exit']['room']))
    key = out['key']
    m = mapdata.cellmap(db, key)
    ex = out.get('exit') or {}
    idoor = min((r for r in m['refs'] if r['type'] == 'DOOR' and not r.get('to')),
                key=lambda r: math.hypot(r['p'][0] - ex.get('x', 0), r['p'][1] - ex.get('y', 0)), default=None)
    if idoor is None:
        raise EditError('Built "%s", but found no door in it to link outside.' % name)
    in_pos = link_both(db, b, key, idoor)
    north = False
    try:
        # (a step further in than you arrive, on the floor, so you don't land on it)
        north = release.place_northmarker(db, key, idoor['k'], at=[in_pos[0] + (in_pos[0] - idoor['p'][0]) * 0.4, in_pos[1] + (in_pos[1] - idoor['p'][1]) * 0.4, in_pos[2] - 12])
    except Exception as e:
        print('northmarker:', e)
    try:
        pl['notes'] += upper_ways(db, b, out, idoor)
    except Exception as e:
        print('upper doors:', e)
        pl['notes'].append('The doors up high outside were not linked: %s' % e)
    out['plan'] = {k: pl[k] for k in ('style_name', 'tile', 'floors', 'notes', 'ratio')}
    out['northmarker'] = north
    out['fits'] = fits(db, key)
    return out


def link_both(db, b, int_key, idoor):
    """The building's door leads in (arriving in front of the interior's door) and the interior's door
    leads out (arriving a step outside the building's door, facing away from it)."""
    d, fr = b['door'], b['frame']
    im = mapdata.cellmap(db, int_key)
    # (straight in from the door, not towards the middle of the room: the fit check lays the interior over
    # the building along this line, and a room off to one side of its door would come out turned)
    near = [r['p'] for r in im['refs'] if r is not idoor and r.get('arch')] or [idoor['p']]
    iu = _door_inward(idoor, (sum(p[0] for p in near) / len(near), sum(p[1] for p in near) / len(near)))
    sill = idoor['p'][2] + (idoor.get('b') or [0, 0, 0])[2] * (idoor.get('s') or 1.0)
    in_pos = [idoor['p'][0] + iu[0] * 110, idoor['p'][1] + iu[1] * 110, sill + 12, 0.0, 0.0, math.atan2(iu[0], iu[1]) % (2 * math.pi)]
    out_pos = [fr.ox - fr.ux * 110, fr.oy - fr.uy * 110, fr.z + 12, 0.0, 0.0, (fr.yaw() + math.pi) % (2 * math.pi)]
    info = mapdata.cell_info(db, int_key)
    c, refs = editing._cell(db, b['cell'] if d['cell'] == b['cell'] else d['cell'])
    ref = refs.get(d['k'])
    if ref is None:
        raise EditError('The building\'s door is no longer there.')
    editing._store(c, d['k'], ref['origin'], ref['idx'], doors._set_link(ref['subs'], info['name'], in_pos))
    c2, refs2 = editing._cell(db, int_key)
    r2 = refs2[idoor['k']]
    editing._store(c2, idoor['k'], r2['origin'], r2['idx'], doors._set_link(r2['subs'], '', out_pos))
    editing.commit(db, 'Linked %s both ways with its building outside (%s)' % (editing.cell_label(db, int_key), d['id']))
    return in_pos


# ---------------------------------------------------------------- the game's own interiors for the same shell

def game_interiors(db, cell_key, ref_key, door_key=None):
    """The game's interiors behind buildings made of the same shell as this one: each is a valid interior for it
    (the user, 2026-10-27: a Mournhold bar shell has the Emerald Haven Inn behind it, and the Miners Club, the
    Laughing Goblin, Dreynim Spa and the Toiling Guar behind its other copies; 369 shells stand at the door of two
    or more of the game's interiors, 3,310 of its 3,551 pairs). {'shell', 'interiors': [{key, name, style, floors,
    area, same}]}: same, built round the same main piece; the closest in size first."""
    b = building_at(db, cell_key, ref_key, door_key)
    models = {g['low'] for g in b['group']}
    shell = max(b['group'], key=lambda g: (g['box'][2] - g['box'][0]) * (g['box'][3] - g['box'][1]))
    own = (b['door'] or {}).get('to') or {}
    own_key = (own.get('cell') or '').lower()
    pairs = ss.survey(db)['pairs'] + _like_ext_pairs(db)
    mine = next((p for p in pairs if p['key'] == own_key), None)
    area = (mine or {}).get('max_area') or None
    rows, seen = [], set()
    for p in pairs:
        main = (p['building'].get('main') or '').lower()
        same = _same_shell(db, shell, main)
        if not (same or main in models) or p['key'] in seen or not db.by_key.get(('CELL', p['key'])):
            continue
        seen.add(p['key'])
        info = mapdata.cell_info(db, p['key'])
        fl = p.get('floors')
        rows.append({'key': p['key'], 'name': (info or {}).get('name') or p['name'], 'style': p.get('style'),
                     'floors': len(fl) if isinstance(fl, (list, tuple)) else (fl or 1),
                     'area': round((p.get('max_area') or 0) / 4900.0), 'same': same, 'own': p['key'] == own_key})
    rows.sort(key=lambda r: (not r['same'], r['own'], abs((r['area'] or 0) - (area or 0) / 4900.0) if area else 0, r['name'].lower()))
    return {'shell': shell['id'], 'interiors': rows[:60]}


# ---------------------------------------------------------------- an outside for an interior (the other way round)

# How much bigger the game's interiors are than their buildings, across the door and along it (scratchpad
# anvilshape.py, 2026-10-27, door on door): Anvil 1.23 x 1.24 (52), the other Imperial 1.22 x 1.25 (82), Hlaalu
# 0.91 x 0.85 (253: a little inside the walls); the rest taken as 1. The user: Anvil's "should conform at least".
INSIDE_RATIO = {'Imperial': (1.23, 1.24), 'Hlaalu': (0.91, 0.85)}


def _interior_door(m):
    """An interior's way out: a door leading outdoors or nowhere yet, a load door first."""
    ds = [r for r in m['refs'] if r['type'] == 'DOOR' and (not r.get('to') or not r['to'].get('cell'))]
    return min(ds, key=lambda r: ('load' not in r['id'].lower(), bool(r.get('to')))) if ds else None


def outsides_for(db, int_key, limit=8):
    """The game's buildings to give an interior an outside, the best fit first: each one's footprint, grown by how
    much bigger the game makes its interiors than its buildings of that style (INSIDE_RATIO), against the interior's
    ground floor laid door on door, its storeys against the interior's floors above the door's. {'style', 'interior':
    {w, d, floors}, 'buildings': [{key, name, uses, w, d, floors, fit, text}]}"""
    m = mapdata.cellmap(db, int_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('Open an interior first: this gives a place indoors a building outside.')
    inside = ss.interior_of(db, int_key)
    d = _interior_door(m)
    if not inside or d is None:
        raise EditError('The Workshop can\'t read this place\'s rooms and way out (it reads places built from a style\'s pieces).')
    ifr = ss._interior_frame(m, d, None)
    T = inside['tile']
    floors = sorted(inside['per_floor'])
    g = min(floors, key=lambda f: abs(f - ifr.z))
    pts = [ifr.to(x, y) for (x, y) in inside['per_floor'][g]]
    ix0, ix1 = min(p[0] for p in pts) - T / 2, max(p[0] for p in pts) + T / 2
    iy0, iy1 = min(p[1] for p in pts), max(p[1] for p in pts) + T
    ups = sum(1 for f in floors if f > g + 64)
    style = inside.get('style') or 'Imperial'
    ra, rb = INSIDE_RATIO.get(style, (1.0, 1.0))
    import exteriorsurvey as es
    s = es.ready(db)
    if s is None:
        raise EditError('The Workshop is still learning how the game puts its buildings together (a few minutes, once). Try again shortly.')
    import housemodules as hm
    best = {}
    for mo in s['modules']:
        if hm.look(mo) != style or not mo.get('ftiles') or not mo.get('fpieces') or not hm.homely(mo):
            continue
        Tm = mo['tile']
        xs, ys = [t[0] for t in mo['ftiles']], [t[1] for t in mo['ftiles']]
        bx0, bx1, by0, by1 = (min(xs) - 0.5) * Tm, (max(xs) + 0.5) * Tm, min(ys) * Tm, (max(ys) + 1) * Tm
        w_i, d_i, w_b, d_b = ix1 - ix0, iy1 - iy0, bx1 - bx0, by1 - by0
        # (sizes against the grown footprint, the door's place along the front, the storeys: too few is a misfit, one
        # more over a one-floor interior only an attic; weighed alike, a narrow house with one storey beat a wide one with
        # two for one floor of rooms 1.8 times its width)
        fu = len(mo.get('fup') or ())
        fit = abs(math.log(w_i / (ra * w_b))) + abs(math.log(d_i / (rb * d_b))) + \
            abs((ix0 + ix1) / 2 - ra * (bx0 + bx1) / 2) / max(w_i, 1) + 0.3 * max(0, ups - fu) + 0.05 * max(0, fu - ups)
        if mo['main'] not in best or fit < best[mo['main']][0]:
            best[mo['main']] = (fit, mo, w_b, d_b)
    rows = []
    for fit, mo, w_b, d_b in sorted(best.values(), key=lambda r: (r[0], -r[1]['uses']))[:limit]:
        rows.append({'key': mo['main'], 'name': hm._label(mo), 'uses': mo['uses'], 'w': round(w_b), 'd': round(d_b),
                     'floors': 1 + len(mo.get('fup') or ()), 'fit': round(fit, 3),
                     'text': 'the rooms %.2f times as wide, %.2f as deep (the game\'s %s: %.2f, %.2f)' % (
                         (ix1 - ix0) / w_b, (iy1 - iy0) / d_b, style, ra, rb)})
    return {'style': style, 'interior': {'w': round(ix1 - ix0), 'd': round(iy1 - iy0), 'floors': 1 + ups}, 'buildings': rows}


def _outside_items(db, key):
    """A learnt building's pieces as a group to place: offsets from its door's frame (the door at 0, 0, inward +y,
    its ground at dz 0), the pieces standing on the ground marked foot (prefabplan.pfGroundZ), the door's index."""
    import exteriorsurvey as es
    import housemodules as hm
    s = es.ready(db) or {}
    ms = [mo for mo in s.get('modules') or () if mo['main'] == key and mo.get('fpieces')]
    if not ms:
        raise EditError('The Workshop does not know that building.')
    mo = max(ms, key=lambda mo: mo['uses'])
    g = mo.get('fground', -40.0)
    items, door = [], None
    for p in mo['fpieces']:
        ri = db.resolve_id(p['id'])
        if ri is None:
            continue
        b = mapdata.object_bounds(db, ri) or [0, 0, 0, 0, 0, 0]
        s_ = p.get('s') or 1.0
        bot, top = p['z'] - g + b[2] * s_, p['z'] - g + b[5] * s_
        if p.get('door') and door is None:
            door = len(items)
        items.append({'id': db.recs[ri][1], 'type': db.recs[ri][0], 'dx': round(p['x'], 2), 'dy': round(p['y'], 2), 'dz': round(p['z'] - g, 2),
                      'rx': p.get('rx', 0.0), 'ry': p.get('ry', 0.0), 'rz': p['rz'], 's': s_, 'foot': bot <= 40 and top > 0, 'footUp': 0})
    return items, door, hm._label(mo)


def give_outside(db, int_key, key, cell_hint, x, y, z, yaw):
    """One of the game's buildings set down outdoors as the interior's outside (groups.place), and its front door and
    the interior's way out linked both ways: one change. {'placed', 'cells', 'door'}"""
    import groups
    m = mapdata.cellmap(db, int_key)
    idoor = _interior_door(m) if m.get('exists') else None
    if idoor is None:
        raise EditError('The interior has no way out to link.')
    items, di, label = _outside_items(db, key)
    if di is None:
        raise EditError('That building has no front door the Workshop knows.')
    r = groups.place(db, cell_hint, items, x, y, z, yaw, '%s, outside %s' % (label, m.get('name') or int_key))
    c_, s_ = math.cos(yaw), math.sin(yaw)
    wx, wy = x + items[di]['dx'] * c_ + items[di]['dy'] * s_, y - items[di]['dx'] * s_ + items[di]['dy'] * c_
    best = None
    for pl in r['placed']:
        ref = next((q for q in mapdata.cellmap(db, pl['cell'])['refs'] if q['k'] == pl['ref']), None)
        if ref and ref['type'] == 'DOOR':
            dist = math.hypot(ref['p'][0] - wx, ref['p'][1] - wy)
            if best is None or dist < best[0]:
                best = (dist, pl)
    if best is None:
        raise EditError('Placed the building, but found no door in it to link (Undo takes it back).')
    b = building_at(db, best[1]['cell'], best[1]['ref'])
    link_both(db, b, int_key, idoor)
    editing.fold(db, 2, 'Gave %s an outside: %s (%d pieces), its door linked both ways' % (m.get('name') or int_key, label, len(r['placed'])))
    return {'placed': r['placed'], 'cells': r['cells'], 'door': best[1]}


def _same_shell(db, shell, main):
    """Is the building round `main` made of the same shell as this one: the same piece, the same mesh, or one of the
    same footprint and height (Tamriel Rebuilt's T_De_SetMH_X_B_Bar_01 is Tribunal's EX_MH_bar_01 to the unit, its
    own mesh with a foundation 385 deeper: the bottom is let go)."""
    if not main:
        return False
    if main == shell['low']:
        return True
    ri = db.resolve_id(main)
    if ri is None:
        return False
    if str(db.recs[ri][5] or '').lower() == str(db.recs[shell['ri']][5] or '').lower():
        return True
    a, b2 = shell['b'], mapdata.object_bounds(db, ri)
    if not b2:
        return False
    span = max(a[3] - a[0], a[4] - a[1], 1)
    tol = max(24.0, 0.03 * span)
    return all(abs(a[k] - b2[k]) <= tol for k in (0, 1, 3, 4, 5))


_like_ext = {}


def _like_ext_pairs(db):
    """The buildings in places that behave like outdoors (Mournhold's districts) and the interiors behind their
    doors, as shellsurvey's pairs ({'key', 'name', 'building': {'main'}, ...}); the shell survey reads only the
    exterior cells, and the Winged Guar's in Godsreach went unseen. Kept a load order."""
    if _like_ext.get('recs') is db.recs:
        return _like_ext['pairs']
    out = []
    for (tag, key) in list(db.by_key):
        if tag != 'CELL' or key.startswith('#') or not (mapdata.cell_info(db, key) or {}).get('like_exterior'):
            continue
        items = ss._cell_items(db, key, {}, {})
        doors_ = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'] and not it['to']['cell'].startswith('#')]
        for d in doors_:
            others = [o for o in doors_ if o is not d]
            try:
                group = ss.structure(items, d['box'], others, None, BIG_PIECES, BIG_EXTENT)
            except Exception:
                continue
            if not group:
                continue
            main = max(group, key=lambda g: (g['box'][2] - g['box'][0]) * (g['box'][3] - g['box'][1]))
            to = d['to']['cell'].lower()
            if db.by_key.get(('CELL', to)):
                out.append({'key': to, 'name': d['to']['cell'], 'style': mapdata.style_of(main['id']), 'floors': 1, 'max_area': 0,
                            'building': {'main': main['id']}})
    _like_ext.update({'recs': db.recs, 'pairs': out})
    return out


def copy_game_interior(db, cell_key, ref_key, template, name, contents='furnished', door_key=None):
    """One of the game's interiors for this building's shell (game_interiors), copied whole under a new name
    (create.create_interior: people and creatures left out) and its front door linked with the building's both
    ways, as one change. {'key', 'name'}"""
    import create
    b = building_at(db, cell_key, ref_key, door_key)
    if b['door'] is None:
        raise EditError('The building has no door to link the interior to: put a door in one of its walls first.')
    # (the original's front door: the load door that leads outside; its copy stands where it stood)
    tm = mapdata.cellmap(db, template)
    front = next((r for r in tm.get('refs', []) if r['type'] == 'DOOR' and r.get('to') and (r['to'].get('cell') or '').startswith('#')), None) \
        or next((r for r in tm.get('refs', []) if r['type'] == 'DOOR' and r.get('to')), None)
    key = create.create_interior(db, template, name, contents, None)
    m = mapdata.cellmap(db, key)
    ds = [r for r in m['refs'] if r['type'] == 'DOOR']
    if not ds:
        raise EditError('Copied "%s", but found no door in it to link outside.' % name)
    idoor = min(ds, key=lambda r: math.dist(r['p'][:3], front['p'][:3])) if front else ds[0]
    link_both(db, b, key, idoor)
    editing.fold(db, 2, 'Copied %s for the building at %s, its door linked both ways' % (name, editing.cell_label(db, cell_key)))
    return {'key': key, 'name': name}


# ---------------------------------------------------------------- does it fit?

def fits(db, int_key):
    """The reviewers' test: the interior laid over its building door on door, floor by floor. {'share',
    'jut', 'floors': [{'floor', 'share', 'jut'}], 'band': the game's p75 share/jut, 'ok', 'text'} or None
    (no door out to a building)."""
    m = mapdata.cellmap(db, int_key)
    if not m.get('exists') or not m.get('interior'):
        return None
    outs = [r for r in m['refs'] if r['type'] == 'DOOR' and r.get('to') and not r['to']['cell']]
    if not outs:
        return None
    inside = ss.interior_of(db, int_key)
    if not inside:
        return None
    for d in outs:
        to = d['to']
        items = ss.near_items(db, to['x'], to['y'])
        back = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'].lower() == int_key and
                math.hypot(it['p'][0] - to['x'], it['p'][1] - to['y']) < 600]
        if not back:
            continue
        back.sort(key=lambda it: math.hypot(it['p'][0] - to['x'], it['p'][1] - to['y']))
        ed = back[0]
        group = ss.structure(items, ed['box'], [it for it in items if it['tag'] == 'DOOR' and it is not ed and it['to'] and it['to']['cell']
                                                and it['to']['cell'].lower() != int_key], None, BIG_PIECES, BIG_EXTENT)
        if not group:
            return None
        # (inward: from where you arrive outside towards the door, as the survey measured the game's)
        efr = ss.Frame(ed['p'][0], ed['p'][1], ed['p'][2] + ed['b'][2] * ed['s'], ed['p'][0] - to['x'], ed['p'][1] - to['y'])
        same = [it for it in items if it['tag'] == 'DOOR' and any(outside._touch(it['box'], g['box'], 8) for g in group)]
        ifr = ss._interior_frame(m, d, (ed['to']['x'], ed['to']['y']))
        T = inside['tile']
        rows = []
        floors = sorted(inside['per_floor'])
        g_floor = min(floors, key=lambda f: abs(f - ifr.z))
        storey = ((kits.stairs(db, inside['kit']) or {}).get('storey') if inside['kit'] else None) or ss.STOREY
        for f in floors:
            k = int(round((f - g_floor) / float(storey)))
            if k < 0:
                continue                           # (a cellar is under the ground: nothing to jut out of)
            ol = ss.outline(db, group, efr, same, k) if k <= 2 else {'cells': set()}
            if k > 0 and not ol['cells']:
                ol = ss.outline(db, group, efr, same, 0)
            ov = ss.overlay(set(ol['cells']), inside['per_floor'][f], T, ifr)
            if ov:
                rows.append({'floor': k, 'share': ov['share'], 'jut': ov['jut']})
        if not rows:
            return None
        L = _learnt(db)
        band = None
        if L:
            bld = {'main': max(group, key=lambda it: (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1]))['id'].lower(),
                   'style': ss.style_of_group(group), 'height': max(g['box'][5] for g in group) - efr.z}
            pr = ss.predict(L, bld)
            if pr.get('jut') and pr.get('share'):
                band = {'share': pr['share'][3], 'jut': pr['jut'][3], 'n': pr['n'], 'from': pr['from']}
        g = rows[0]
        worst = max(rows, key=lambda r: r['share'])
        lim_share = band['share'] if band else 0.25
        lim_jut = band['jut'] if band else 192
        within = lambda sh_, j_: all(r['share'] <= sh_ + 0.02 and r['jut'] <= j_ + 16 for r in rows)
        # (close is good: Bethesda's own interiors line up with their buildings about half as well as Tamriel Rebuilt's;
        # within Bethesda's spread an interior passes, and the closer figure is said)
        sb = ss.source_bands(db) or {}
        beth = sb.get('bethesda')
        close = within(lim_share, lim_jut)
        loose = bool(beth) and within(max(lim_share, beth['share']), max(lim_jut, beth['jut']))
        ok = close or loose
        what = ': %d%% of the ground floor outside the walls, at most %d units out%s' % (
            round(g['share'] * 100), g['jut'], '' if len(rows) == 1 else '; worst floor %d: %d%%' % (worst['floor'] + 1, round(worst['share'] * 100)))
        if close:
            text = 'Fits its building as closely as the game\'s own interiors for it' + what + ' (the game\'s: up to %d%%, %d units)' % (round(lim_share * 100), lim_jut)
        elif loose:
            text = 'Fits its building about as loosely as the original game\'s interiors fit theirs' + what + \
                ' (the original game\'s: up to %d%%, %d units; the closer ones for this building: up to %d%%, %d units)' % (
                    round(beth['share'] * 100), beth['jut'], round(lim_share * 100), lim_jut)
        else:
            text = 'Sticks out of its building more than the game\'s own interiors do, the original game\'s too' + what + \
                ' (the game\'s for this building: up to %d%%, %d units%s)' % (
                    round(lim_share * 100), lim_jut, '; the original game\'s: up to %d%%, %d units' % (round(beth['share'] * 100), beth['jut']) if beth else '')
        return {'share': g['share'], 'jut': g['jut'], 'floors': rows, 'band': band, 'ok': ok, 'close': close, 'text': text,
                'building': ed['cell'], 'door': ed['id']}
    return None
