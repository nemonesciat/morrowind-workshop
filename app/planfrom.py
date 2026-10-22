"""A floor plan from one of the game's own places, read back into the room planner's plan (rooms with
names and purposes, doorways between them, the way out, cellar and upstairs floors, and the stairs
pinned where the game stands them, in the place's own style), so a house, shop or tavern the game's
builders laid out can be studied on the plan and built from. Read-only: nothing here changes the mod.

An approximation that keeps the building's shape: every floor-bearing building piece (the kit's own
tiles, and the set's other pieces: a tall hall, a double-size room, a platform, a stair) marks the
grid cells its footprint covers, on the storey nearest its floor (a half-level folds to the nearest
storey; a piece two storeys tall marks both). Cells side by side on a storey make a room unless a kit
tile shows a wall between them, or a doorway with a door, a curtain or a frame in it; a cell with no
kit pattern joins its neighbours. Rooms are named by what stands in them (roomsurvey.room_kind) and
keep their shape as a rectangle with tiles cut out. The note says how many pieces the plan was
approximated from and how many of them are of a kind the kit doesn't build with."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import furnish
import kits
import layoutsurvey
import mapdata
import roomsurvey
from editing import EditError

# the planner's room names for what the survey sees in a room
KIND_NAMES = {'bedroom': 'Bedroom', 'tavern': 'Tavern', 'shop': 'Shop', 'shrine': 'Shrine', 'study': 'Study',
              'kitchen': 'Kitchen', 'storage': 'Storeroom', 'living': 'Living room'}
FLOOR_WORDS = {-2: 'the lower cellar', -1: 'the cellar', 0: 'the ground floor', 1: 'upstairs', 2: 'the top floor'}
# pieces of a set that carry no floor: not read as building, whatever their size
NOT_FLOOR_RE = re.compile(r'jamb|post|rail|wall|pillar|column|arch(?!way)|ceil|roof|window|_win|light|lamp|trim|cap(_|$)|'
                          r'beam|banister|balustrade|door(?!way)|shutter|curtain|rug|carpet|drape|hearth|fire|chimney|'
                          r'^furn_|^ex_|_ex_|_x_')
STAIR_RE = layoutsurvey.STAIR_RE


def _box(r):
    """A piece's footprint in the world, from its model's bounds turned and moved as the piece is:
    (x0, y0, x1, y1), and its floor height (the bottom of the box)."""
    b = r.get('b')
    if not b:
        return None
    sc = r.get('s') or 1
    th = r['p'][5]
    c, s = math.cos(th), math.sin(th)
    xs, ys = [], []
    for bx, by in ((b[0], b[1]), (b[0], b[4]), (b[3], b[1]), (b[3], b[4])):
        bx, by = bx * sc, by * sc
        xs.append(r['p'][0] + bx * c + by * s)
        ys.append(r['p'][1] - bx * s + by * c)
    return (min(xs), min(ys), max(xs), max(ys)), r['p'][2] + b[2] * sc, (b[5] - b[2]) * sc


def _building(db, m):
    """The pieces of the place that carry floor: (T, kit prefix most used, [(ref, box, floor z, height,
    kit piece or None)], the grid origin)."""
    pieces, kp_of, others = [], {}, []
    known = kits.kits(db)
    for r in m['refs']:
        if r['type'] != 'STAT':
            continue
        low = r['id'].lower()
        prefix = kits.kit_prefix(low)
        if not prefix or prefix not in known:
            # (a building piece of no kit: the set's big round rooms, a cave's floor: its footprint
            # counts once the kit is known)
            if r.get('arch') and not NOT_FLOOR_RE.search(low):
                others.append(r)
            continue
        if prefix not in kp_of:
            kp_of[prefix] = kits.kit_pieces(db, prefix)
        kp = kp_of[prefix]
        if not kp:
            continue
        rest = low[len(prefix):]
        piece = next((p for p in kp['pieces'] if p['id'].lower() == low), None)
        if piece is None and NOT_FLOOR_RE.search(rest):
            continue
        bb = _box(r)
        if not bb:
            continue
        box, z, h = bb
        T = kp['tile']
        # (a thin piece is a wall or a rail, not a floor; a flat slab wider than a tile is a floor, a
        # stair or ramp is floor too)
        if min(box[2] - box[0], box[3] - box[1]) < T * 0.5:
            continue
        if piece is None and h < 24 and not STAIR_RE.search(rest):
            continue                                        # (a ceiling slab, a rug-thin board)
        pieces.append((r, box, z, h, piece, prefix, T))
    if not pieces:
        return None, None, [], (0, 0)
    style = Counter(p[5] for p in pieces).most_common(1)[0][0]
    T = kp_of[style]['tile']
    pieces = [p for p in pieces if p[6] == T]
    for r in others:
        bb = _box(r)
        if not bb:
            continue
        box, z, h = bb
        if min(box[2] - box[0], box[3] - box[1]) < T * 0.5 or (h < 24 and not STAIR_RE.search(r['id'].lower())):
            continue
        pieces.append((r, box, z, h, None, style, T))
    # the grid's origin: where the kit's own tiles stand (else where the pieces' centres fall)
    tiles = [p for p in pieces if p[4] is not None]
    src = tiles or pieces
    res = Counter((int(round(p[0]['p'][0] % T / 16)) * 16 % T, int(round(p[0]['p'][1] % T / 16)) * 16 % T) for p in src)
    ox, oy = res.most_common(1)[0][0]
    return T, style, pieces, (ox, oy)


def _covered(box, ox, oy, T, share=0.4):
    """The grid cells a footprint covers by at least `share` of a cell."""
    x0, y0, x1, y1 = box
    out = []
    for gx in range(int(math.floor((x0 - ox) / T - 0.5)), int(math.ceil((x1 - ox) / T + 0.5)) + 1):
        cx0, cx1 = ox + (gx - 0.5) * T, ox + (gx + 0.5) * T
        w = min(x1, cx1) - max(x0, cx0)
        if w <= 0:
            continue
        for gy in range(int(math.floor((y0 - oy) / T - 0.5)), int(math.ceil((y1 - oy) / T + 0.5)) + 1):
            cy0, cy1 = oy + (gy - 0.5) * T, oy + (gy + 0.5) * T
            d = min(y1, cy1) - max(y0, cy0)
            if d > 0 and w * d >= share * T * T:
                out.append((gx, gy))
    return out


_places = {}


def places(db):
    """Every interior the game made that is built from a kit's floor tiles (so it can be read as a
    plan), with its style and size: [{key, name, style, objects, tiles}], by style then name."""
    if _places.get('recs') is db.recs:
        return _places['out']
    import create
    from esm import zstr
    from project import split_cell
    known = kits.kits(db)
    out = []
    for k, lst in db.by_key.items():
        if k[0] != 'CELL' or k[1].startswith('#'):
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        data = create._data(db, live[-1])
        n = data.count(b'FRMR')
        if n < 3:
            continue
        votes, kit = {}, Counter()
        _hdr, refs = split_cell(data)
        for ref in refs:
            rid = ''
            for t, d in ref['subs']:
                if t == 'NAME':
                    rid = zstr(d).lower()
                    break
            if not rid:
                continue
            prefix = kits.kit_prefix(rid)
            if prefix and prefix in known:
                kit[prefix] += 1
            if rid.startswith('in_') or '_in_' in rid or '_i_' in rid:
                label = mapdata.style_of(rid)
                if label:
                    votes[label] = votes.get(label, 0) + 1
        if sum(kit.values()) < 3:
            continue
        out.append({'key': k[1], 'name': db.recs[live[-1]][1], 'objects': n, 'tiles': sum(kit.values()),
                    'kit': kit.most_common(1)[0][0], 'style': max(votes, key=votes.get) if votes else 'Other'})
    out.sort(key=lambda t: (t['style'], t['name'].lower()))
    _places.update({'recs': db.recs, 'out': out})
    return out


def _words(n, what, plural=None):
    return '%d %s' % (n, what if n == 1 else (plural or what + 's'))


def _nearest(z, base, storey):
    return int(math.floor((z - base) / float(storey) + 0.5))


def plan_from_cell(db, key):
    """The planner's plan for one of the game's places: {'plan': {rooms, doors, walls, exit, stairs,
    stairPins}, 'style': kit prefix, 'name': the place's name, 'note': what was read and what was
    left out, in words, 'counts': {...}}."""
    m = mapdata.cellmap(db, key)
    if not m.get('exists'):
        raise EditError('There is no place called "%s".' % key)
    if not m.get('interior'):
        raise EditError('"%s" is outdoors: only an interior can be turned into a plan.' % (m.get('name') or key))
    name = m.get('name') or key
    T, style, pieces, (ox, oy) = _building(db, m)
    if len(pieces) < 2:
        raise EditError('%s isn\'t built from a building kit\'s pieces (a cave, a tomb or a ruin, or a set the Workshop '
                        'can\'t build with), so there is no plan to read from it.' % name)
    refs = m['refs']
    doors = [r for r in refs if r['type'] == 'DOOR']
    load = [r for r in doors if r.get('to')]
    way_out = [r for r in load if not r['to'].get('cell')] or load
    jambs = [r for r in refs if r['type'] == 'STAT' and 'jamb' in r['id'].lower()]
    curtains = [r for r in refs if r['type'] in ('STAT', 'ACTI') and layoutsurvey.CURTAIN_RE.search(r['id'].lower())]
    near = layoutsurvey._near
    st_info = kits.stairs(db, style)
    kp = kits.kit_pieces(db, style)
    storey = (st_info or {}).get('storey') or kp['height'] or 256
    cell_of = lambda x, y: (int(round((x - ox) / T)), int(round((y - oy) / T)))
    stair_pieces = {p['id'].lower(): p for p in (st_info or {}).get('pieces', [])}
    # the floor the way in is on: the lowest piece under the door to outside
    base = None
    for d in way_out:
        under = [(abs(z - d['p'][2]), z) for r, box, z, h, piece, _pre, _T in pieces
                 if box[0] - T * 0.6 <= d['p'][0] <= box[2] + T * 0.6 and box[1] - T * 0.6 <= d['p'][1] <= box[3] + T * 0.6
                 and -60 <= d['p'][2] - z <= 400]
        if under:
            base = min(under)[1]
            break
    if base is None:
        base = min(z for _r, _b, z, _h, _p, _pre, _T in pieces)
    # (the way in on the ground floor, unless the floors above it won't fit in the planner's two: then
    # the whole house slides down a floor or two, as far as the cellars allow)
    pieces = [p + (_covered(p[1], ox, oy, T),) for p in pieces]
    pieces = [p for p in pieces if p[7]]                    # (a piece covering no cell by half: nothing to mark)
    if len(pieces) < 2:
        raise EditError('%s has too little floor on the grid to read a plan from.' % name)
    raw_levels = [_nearest(z, base, storey) for _r, _b, z, _h, _p, _pre, _T, _c in pieces]
    hi, lo = max(raw_levels), min(raw_levels)
    shift = min(max(0, hi - 2), max(0, 2 + lo)) if hi > 2 else 0
    lv_of = lambda z: _nearest(z, base, storey) - shift
    is_stair_id = lambda low: STAIR_RE.search(low[len(style):] if low.startswith(style) else low) is not None
    # (the storeys that have floor of their own: a tall piece reaches up into the next storey only
    # where the building has a floor there, as a Hlaalu manor's tall hall meets its upper rooms)
    plain_levels = {lv_of(z) for r, _b, z, h, _p, _pre, _T, _c in pieces if h < storey * 1.5 and not is_stair_id(r['id'].lower())}
    # every piece marks the cells it covers on its storey (a tall piece on the storey above too); the
    # kit's own tiles bring their wall/door pattern, the others are open all round. A stair or ramp
    # marks no floor: it is pinned as stairs (when the kit has the piece) and the Workshop builds its own
    cells = {}                       # (gx, gy, lv) -> {'pat': pattern or None, 'x', 'y', 'floor', 'id', 'tile': bool}
    other_n = kit_n = dropped = 0
    stairs_seen = []
    for r, box, z, h, piece, _pre, _T, covered in pieces:
        lv = lv_of(z)
        low = r['id'].lower()
        if piece is not None:
            kit_n += 1
        else:
            other_n += 1
        if is_stair_id(low):
            stairs_seen.append((r, box, z, lv))
            continue
        levels = [lv]
        if h >= storey * 1.5 and lv + 1 in plain_levels:
            levels.append(lv + 1)
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        pat = kits.rotate(piece['pattern'], q) if piece is not None else None
        for gx, gy in covered:
            for l in levels:
                if not -2 <= l <= 2:
                    dropped += 1
                    continue
                k = (gx, gy, l)
                here = cells.get(k)
                if here and (here['tile'] or pat is None):
                    continue                                   # (a kit tile's pattern wins; the first piece otherwise)
                cells[k] = {'pat': pat if (piece is not None and len(covered) == 1) else None, 'x': ox + gx * T, 'y': oy + gy * T,
                            'floor': base + (l + shift) * storey, 'id': low, 'tile': piece is not None and len(covered) == 1}
    if not cells:
        raise EditError('%s has no rooms the planner can hold (its floors are too far apart).' % name)

    def side_of(k, s):
        """What a cell shows on a side: 'wall', 'door' or 'open'."""
        c = cells[k]
        if c['pat'] is None:
            return 'open'
        return c['pat'][s]

    def wall_between(k, s):
        dx, dy = furnish.STEP[s]
        nk = (k[0] + dx, k[1] + dy, k[2])
        if nk not in cells:
            return None
        a, b = side_of(k, s), side_of(nk, furnish.OPP[s])
        c = cells[k]
        mx, my = c['x'] + dx * T / 2, c['y'] + dy * T / 2
        has_door = near(doors, mx, my, c['floor'], T * 0.55)
        if a == 'wall' or b == 'wall':
            # (a door hung in a wall piece's own opening: Velothi's and Redoran's walls have them)
            return 'door' if has_door else 'wall'
        if a == 'door' or b == 'door' or near(jambs, mx, my, c['floor'], 60):
            # a doorway: with a door, a curtain or a frame in it, it ends a room; a bare arch joins
            if has_door or near(curtains, mx, my, c['floor']) or near(jambs, mx, my, c['floor'], 60):
                return 'door'
            return 'open'
        return 'open'
    # rooms: cells side by side on a storey, split where a wall or a doorway stands between them
    rooms, room_of = [], {}
    for k in sorted(cells):
        if k in room_of:
            continue
        group, todo = [], [k]
        room_of[k] = len(rooms)
        while todo:
            c = todo.pop()
            group.append(c)
            for s in kits.SIDES:
                dx, dy = furnish.STEP[s]
                nk = (c[0] + dx, c[1] + dy, c[2])
                if nk in cells and nk not in room_of and wall_between(c, s) == 'open':
                    room_of[nk] = len(rooms)
                    todo.append(nk)
        rooms.append({'keys': group, 'lv': k[2], 'floor': cells[k]['floor']})
    # an approximated cell sticking out of its room on its own (a round piece's rim, a nub the kits can't
    # close: the builder has no piece with walls on three sides in the Redoran and Velothi sets) is
    # trimmed off; a kit tile stays whatever its neighbours
    trimmed = 0
    # (a kit with no piece walled on three sides and no loose walls can't build a one-tile nub at all,
    # whatever stands there in the game: those are trimmed even where a kit tile stands)
    small_rooms = bool(kp.get('walls')) or any(sum(1 for s in kits.SIDES if p['pattern'][s] == 'wall') >= 3 for p in kp['pieces'])
    for rm in rooms:
        if len(rm['keys']) < 4:
            continue
        keep = set(rm['keys'])
        while True:
            nubs = [k for k in keep if (cells[k]['pat'] is None or not small_rooms)
                    and sum(1 for dx, dy in furnish.STEP.values() if (k[0] + dx, k[1] + dy, k[2]) in keep) <= 1]
            if not nubs or len(keep) - len(nubs) < 2:
                break
            for k in nubs:
                keep.discard(k)
                del cells[k]
                del room_of[k]
                trimmed += 1
        rm['keys'] = [k for k in rm['keys'] if k in keep]
    # (a cell or two walled off on their own with no kit pattern: a stair's foot, a ramp, a landing
    # that the builder makes for itself: not a room)
    lone = [rm for rm in rooms if len(rm['keys']) <= 2 and (not small_rooms or all(cells[k]['pat'] is None for k in rm['keys']))]
    if lone and len(lone) < len(rooms):
        # (not when that would leave a floor with no rooms between two that have some: the builder
        # needs every floor in between)
        kept = [rm for rm in rooms if rm not in lone]
        lvs = {rm['lv'] for rm in kept}
        for rm in lone:
            if min(lvs) < rm['lv'] < max(lvs) and rm['lv'] not in lvs:
                kept.append(rm)
                lvs.add(rm['lv'])
        lone = [rm for rm in lone if rm not in kept]
        rooms = [rm for rm in rooms if rm in kept]
    else:
        lone = []                       # (a place of nothing but small rooms keeps them)
    landings = sum(len(rm['keys']) for rm in lone) + trimmed
    if lone:
        for rm in lone:
            for k in rm['keys']:
                del cells[k]
        room_of = {k: n for n, rm in enumerate(rooms) for k in rm['keys']}
    # what stands in each room says what kind it is
    for r in refs:
        r['_fam'] = roomsurvey.family_of(db, r['id'], r['type']) if r.get('b') and not r.get('arch') \
            and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC') else None
    for n, rm in enumerate(rooms):
        cells_ = {k[:2] for k in rm['keys']}
        inside = [r for r in refs if r['_fam'] and cell_of(r['p'][0], r['p'][1]) in cells_
                  and rm['floor'] - 100 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= rm['floor'] + storey + 40]
        counts = Counter(r['_fam'] for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS)
        rm['kind'] = roomsurvey.room_kind(counts)
        rm['cells'] = cells_
    # the grid moved so the plan starts at 0, 0
    x_min = min(k[0] for k in cells)
    y_min = min(k[1] for k in cells)
    out_rooms = []
    for n, rm in enumerate(rooms):
        xs = [k[0] - x_min for k in rm['keys']]
        ys = [k[1] - y_min for k in rm['keys']]
        x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        have = set(zip(xs, ys))
        cut = [[x - x0, y - y0] for x in range(x0, x0 + w) for y in range(y0, y0 + h) if (x, y) not in have]
        corridor = min(w, h) == 1 and max(w, h) >= 3
        rname = KIND_NAMES.get(rm['kind']) or ('Hallway' if corridor else 'Hall')
        if rm['kind'] in ('empty', 'living') and corridor:
            rname = 'Hallway'
        room = {'id': 'g%d' % (n + 1), 'name': rname, 'x': x0, 'y': y0, 'w': w, 'h': h, 'floor': rm['lv']}
        if cut:
            room['cut'] = cut
        rm['id'] = room['id']
        out_rooms.append(room)
    # doorways between rooms where the game has them (the one with a door in it when a pair has several);
    # the rooms that touch with nothing but wall between them keep their wall
    out_doors, walls, seen_pairs = [], [], {}
    for n, rm in enumerate(rooms):
        for k in rm['keys']:
            for s, (dx, dy) in furnish.STEP.items():
                other = room_of.get((k[0] + dx, k[1] + dy, k[2]))
                if other is None or other == n:
                    continue
                pair = (min(n, other), max(n, other))
                kind = wall_between(k, s)
                if kind != 'door':
                    seen_pairs.setdefault(pair, None)
                    continue
                c = cells[k]
                has_door = near(doors, c['x'] + dx * T / 2, c['y'] + dy * T / 2, c['floor'], T * 0.55)
                d = {'a': rm['id'], 'b': rooms[other]['id'], 'kind': 'door', 'x': k[0] - x_min, 'y': k[1] - y_min, 'side': s}
                if seen_pairs.get(pair) is None or (has_door and not seen_pairs[pair][1]):
                    seen_pairs[pair] = (d, bool(has_door))
    for pair, v in seen_pairs.items():
        if v is None:
            walls.append([rooms[pair[0]]['id'], rooms[pair[1]]['id']])
        else:
            out_doors.append(v[0])
    # the way out: the door to outside, on an outside side of the cell it stands at
    exit_ = None
    for d in way_out:
        # (the cell nearest the door, on the floor it stands on before any other)
        cand = [(abs(c['floor'] - d['p'][2]) > storey * 0.5, math.hypot(c['x'] - d['p'][0], c['y'] - d['p'][1]), k) for k, c in cells.items()
                if abs(c['floor'] - d['p'][2]) < storey * 1.2 and math.hypot(c['x'] - d['p'][0], c['y'] - d['p'][1]) < T * 1.2]
        if not cand:
            continue
        k = min(cand)[2]
        c = cells[k]
        dx, dy = d['p'][0] - c['x'], d['p'][1] - c['y']
        side = ('E' if dx > 0 else 'W') if abs(dx) > abs(dy) else ('N' if dy > 0 else 'S')
        for s in [side] + [x for x in kits.SIDES if x != side]:
            sx, sy = furnish.STEP[s]
            if (k[0] + sx, k[1] + sy, k[2]) not in cells:
                exit_ = {'room': rooms[room_of[k]]['id'], 'x': k[0] - x_min, 'y': k[1] - y_min, 'side': s}
                break
        if exit_:
            break
    # the stairs: the kit's own stair pieces, each pinned where it stands (the bottom step's tile and the
    # side it climbs to) on the storey of its foot; other stairs and ramps only mark floor
    pins, stairs_out, unknown, extra = {}, [], 0, 0
    cands = []
    for r, box, z, lv in stairs_seen:
        p = stair_pieces.get(r['id'].lower())
        if not p:
            unknown += 1
            continue
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        low = kits.SIDES[(kits.SIDES.index(p['low']) + q) % 4]
        up = furnish.OPP[low]
        gx, gy = cell_of(r['p'][0], r['p'][1])
        cands.append((lv, r['p'][2], gx, gy, up, p))
    for lv, z, gx, gy, up, p in sorted(cands):
        if not (-2 <= lv <= 1) or not any(rm['lv'] == lv for rm in rooms) or not any(rm['lv'] == lv + 1 for rm in rooms):
            unknown += 1
            continue
        if lv in pins:
            # (the second of two short flights in line, over the first: the first is the pin)
            if abs(p['rise'] * 2 - storey) < 8 and (gx, gy) == (pins[lv]['x'] + x_min + furnish.STEP[up][0], pins[lv]['y'] + y_min + furnish.STEP[up][1]):
                continue
            extra += 1
            continue
        pins[lv] = {'x': gx - x_min, 'y': gy - y_min, 'up': up}
        foot = room_of.get((gx - furnish.STEP[up][0], gy - furnish.STEP[up][1], lv)) if (gx, gy, lv) not in room_of else room_of[(gx, gy, lv)]
        head = room_of.get((gx + furnish.STEP[up][0], gy + furnish.STEP[up][1], lv + 1))
        if foot is None:
            foot = next((room_of.get((gx + dx, gy + dy, lv)) for dx, dy in furnish.STEP.values() if (gx + dx, gy + dy, lv) in room_of), None)
        if head is None:
            head = next((room_of.get((gx + dx, gy + dy, lv + 1)) for dx, dy in furnish.STEP.values() if (gx + dx, gy + dy, lv + 1) in room_of), None)
        if foot is not None and head is not None and foot != head:
            stairs_out.append({'lo': rooms[foot]['id'], 'hi': rooms[head]['id']})
    plan = {'rooms': out_rooms, 'doors': out_doors, 'walls': walls, 'exit': exit_, 'stairs': stairs_out, 'stairPins': pins}
    levels = sorted({rm['lv'] for rm in rooms})
    unpinned, problem = _check(db, style, plan)
    # what was read, and what was left out, in words
    got = [_words(len(out_rooms), 'room'), _words(len(out_doors), 'doorway')]
    if len(levels) > 1:
        got.append(_words(len(levels), 'floor'))
    if pins:
        got.append('stairs from ' + ' and '.join(FLOOR_WORDS.get(f, 'floor %d' % f) for f in sorted(pins)))
    if exit_:
        got.append('the way out')
    note = 'Read %s: %s; approximated from %s%s.' % (
        name, ', '.join(got), _words(kit_n + other_n, 'building piece'),
        (', %d of them of a kind the %s kit doesn\'t build with (their footprint is kept, their walls are not)' % (other_n, kits.friendly(style))) if other_n else '')
    missed = []
    if dropped:
        missed.append(_words(dropped, 'tile', 'tiles') + ' on a floor the planner can\'t hold (more than two storeys from the way in)')
    if landings:
        missed.append(_words(landings, 'walled-off tile', 'walled-off tiles') + ' of pieces the kit doesn\'t build with')
    if unknown:
        missed.append(_words(unknown, 'stair or ramp', 'stairs or ramps') + ' the kit has no stair piece for (only its floor is kept)')
    if extra:
        missed.append(_words(extra, 'extra flight of stairs', 'extra flights of stairs') + ' (one a floor is pinned)')
    if missed:
        note += ' Left out: %s.' % '; '.join(missed)
    if unpinned:
        note += ' The Workshop can\'t stand the stairs from %s where the game has them (its own stair rules differ there), ' \
                'so it puts them where they fit.' % ' and '.join(FLOOR_WORDS.get(f, 'floor %d' % f) for f in unpinned)
    if problem:
        note += ' As it is, it can\'t be built: %s' % problem
    return {'plan': plan, 'style': style, 'name': name, 'note': note,
            'counts': {'rooms': len(out_rooms), 'doors': len(out_doors), 'floors': len(levels), 'stairs': len(pins),
                       'pieces': kit_n + other_n, 'other': other_n, 'dropped': dropped, 'unknown_stairs': unknown,
                       'extra_stairs': extra, 'stair_refs': len(stairs_seen), 'cells': len(cells), 'unpinned': unpinned,
                       'problem': problem or None}}


# ------------------------------------------------------------------ which places are worth listing
# the game's places that read back as a plan the Workshop can build: tombs, caves, sewers and the like
# are out by name and style, so are sets with no stair pieces; the rest are scored by how much of their
# floor is the kit's own tiles, whether their stairs are the kit's, and a dry run of the builder's
# planning, in a background pass kept on disk (a few minutes the first time)
EXCLUDE_NAME_RE = re.compile(r'tomb|cave|cavern|grotto|\bmine\b|\bmines\b|ruin|daedric|dwemer|sewer|depths|barrow|crypt|catacomb|'
                             r'smuggler|bandit|lair|den\b|nest|burrow|pit\b|hollow|vault\b|sanctum|shrine of|ancestral', re.I)
EXCLUDE_STYLES = {'Cave', 'Daedric', 'Dwemer', 'Sewer', 'Stronghold', 'Other'}
_gate = {}


def _gate_disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'planfrom_%s_v3.json' % taste.sig(db))


def candidates(db):
    """The places worth a dry run: not a tomb or a cave by name or style, in a style the Workshop
    builds with that has stair pieces."""
    import builder
    styles = {s['id'] for s in builder.styles(db)}
    out = []
    for p in places(db):
        if p['style'] in EXCLUDE_STYLES or EXCLUDE_NAME_RE.search(p['name']) or p['kit'] not in styles:
            continue
        if not kits.stairs(db, p['kit']):
            continue
        out.append(p)
    return out


def score(db, p):
    """One place's fitness: {'builds', 'share' (kit tiles among its floor-bearing pieces), 'approx',
    'stairs': 'own' | 'placed' | 'none' | None (one floor), 'word'}, or None when it can't be read or
    built as it is."""
    try:
        r = plan_from_cell(db, p['key'])
    except Exception:
        return None
    c = r['counts']
    if c['problem'] or not c['pieces']:
        return None
    share = (c['pieces'] - c['other']) / float(c['pieces'])
    if share < 0.1:
        return None                     # (next to nothing of it is the kit's: a Redoran hut of round pieces)
    if c['floors'] < 2:
        st = None
    elif c['stairs'] and not c['unpinned']:
        st = 'own'
    elif c['stairs']:
        st = 'mixed'                    # (some flights where the game has them, the rest placed)
    elif c['stair_refs']:
        st = 'placed'
    else:
        st = 'none'
    bits = []
    rough = share < 0.5
    if c['other']:
        bits.append(('%d of %d pieces' % (c['other'], c['pieces']) if rough else _words(c['other'], 'piece')) + ' approximated')
    if st == 'placed':
        bits.append('stairs placed by the Workshop')
    elif st == 'mixed':
        bits.append('some stairs placed by the Workshop')
    elif st == 'none':
        bits.append('no stairs in the game, the Workshop adds them')
    word = 'builds as it is' if not bits else ('rough: ' if rough else 'close: ') + ', '.join(bits)
    return {'builds': True, 'share': round(share, 2), 'approx': c['other'], 'rough': rough, 'stairs': st, 'word': word,
            'rooms': c['rooms'], 'floors': c['floors']}


def _gate_run(db, cands, path):
    done = _gate['done']
    n = 0
    for p in cands:
        if _gate.get('recs') is not db.recs:
            return
        if p['key'] in done:
            continue
        try:
            done[p['key']] = score(db, p)
        except Exception:
            done[p['key']] = None
        n += 1
        if n % 25 == 0:
            _gate_save(path)
    _gate_save(path)
    _gate['finished'] = True


def _gate_save(path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(_gate['done'], f)
    except Exception:
        pass


def gated(db):
    """The places that pass the gate, best first, with the pass's progress: {'ready', 'done', 'total',
    'places': [place + score]}. Starts the pass in the background the first time."""
    import threading
    path = _gate_disk(db)
    if _gate.get('recs') is not db.recs:
        done = {}
        try:
            with open(path, encoding='utf-8') as f:
                done = json.load(f)
        except Exception:
            pass
        _gate.clear()
        _gate.update({'recs': db.recs, 'done': done, 'finished': False, 'cands': candidates(db)})
    cands = _gate['cands']
    done = _gate['done']
    if not _gate['finished'] and all(p['key'] in done for p in cands):
        _gate['finished'] = True
    if not _gate['finished'] and (_gate.get('thread') is None or not _gate['thread'].is_alive()):
        import background
        _gate['thread'] = background.start('which of the game\'s places can be read back as plans', lambda: _gate_run(db, cands, path))
    out = []
    for p in cands:
        s = done.get(p['key'])
        if s:
            out.append(dict(p, **s))
    out.sort(key=lambda x: (x.get('rough', False), x['approx'] > 0, x['stairs'] in ('placed', 'mixed'), -x['share'], -x['rooms'], x['name'].lower()))
    return {'ready': _gate['finished'], 'done': sum(1 for p in cands if p['key'] in done), 'total': len(cands), 'places': out}


def builder_args(plan):
    """A planner plan as the builder takes it (what the planner's bLayout sends): (rooms, doors, exit,
    stairs), with the room names made unique the way the planner does."""
    rooms, N, seen = [], {}, {}
    for n, r in enumerate(plan['rooms']):
        name = (r.get('name') or '').strip() or 'Room %d' % (n + 1)
        k = name.lower()
        if k in seen:
            seen[k] += 1
            name += ' %d' % seen[k]
        else:
            seen[k] = 1
        N[r['id']] = name
        o = {'name': name, 'x': r['x'], 'y': r['y'], 'w': r['w'], 'h': r['h'], 'floor': r['floor']}
        if r.get('cut') or r.get('add'):
            o['cut'] = [[r['x'] + t[0], r['y'] + t[1]] for t in r.get('cut') or []]
            o['add'] = [[r['x'] + t[0], r['y'] + t[1]] for t in r.get('add') or []]
        rooms.append(o)
    doors = [{'rooms': [N[d['a']], N[d['b']]], 'kind': 'open'} if d.get('kind') == 'open' else
             {'rooms': [N[d['a']], N[d['b']]], 'at': {'x': d['x'], 'y': d['y'], 'side': d['side']}} for d in plan.get('doors') or []]
    ex = plan.get('exit')
    exit_ = {'room': N[ex['room']], 'side': ex['side'], 'x': ex['x'], 'y': ex['y']} if ex and ex.get('room') in N else None
    floor_of = {r['id']: r['floor'] for r in plan['rooms']}
    by = {}
    for s in plan.get('stairs') or []:
        if s['lo'] in floor_of and s['hi'] in floor_of:
            by[floor_of[s['lo']]] = {'floor': floor_of[s['lo']], 'rooms': [N[s['lo']], N[s['hi']]]}
    for f, p in (plan.get('stairPins') or {}).items():
        by.setdefault(int(f), {'floor': int(f)})['at'] = {'x': p['x'], 'y': p['y'], 'up': p['up']}
    return rooms, doors, exit_, list(by.values())


def _check(db, style, plan):
    """Whether the builder can plan this (its stairs above all): a pinned stair the builder can't stand
    where the game has it (its foot or head on a piece the kit doesn't build with, a loose wall where the
    builder wants floor) is unpinned, so the Workshop places those stairs itself. Returns (the floors
    unpinned, the builder's complaint when it still can't plan it, else None)."""
    import builder
    unpinned = []
    for _ in range(len(plan['stairPins']) + 1):
        rooms, doors, _exit, stairs = builder_args(plan)
        try:
            builder.plan(db, style, rooms, stairs, 'auto', doors)
            return unpinned, None
        except Exception as e:                  # (EditError mostly; an odd place must not lose the plan)
            msg = str(e)
            if not plan['stairPins']:
                return unpinned, msg
            f = next((f for f in sorted(plan['stairPins']) if 'from the %s ' % builder.FLOOR_NAMES.get(f, '?') in msg), None)
            if f is None:
                f = min(plan['stairPins'])
            del plan['stairPins'][f]
            unpinned.append(f)
    return unpinned, None
