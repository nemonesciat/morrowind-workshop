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
UP_MIN = 0.3                  # an upper outline smaller than this share of the ground's is no storey
ROOF_SAMPLE = 3               # every n-th outline cell is looked up from for the roof
# (a building right-clicked may be bigger than the survey reads in the game's towns: a prefab of three houses)
BIG_PIECES = 90
BIG_EXTENT = 4600
ROOF_OPEN = 0.30              # open to the sky over more of the floor than 9 in 10 of the game's buildings


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
    if not cell_key or not cell_key.startswith('#'):
        raise EditError('Pick a building outdoors: this works on exterior pieces.')
    m = mapdata.cellmap(db, cell_key)
    ref = next((r for r in m.get('refs', []) if r['k'] == ref_key), None)
    if ref is None:
        raise EditError('That piece is no longer there.')
    items = ss.near_items(db, ref['p'][0], ref['p'][1])
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


def check(db, b):
    """Is the building closed and sound? {'ok', 'lines': [{'sev': 'ok'|'warning'|'error', 'text', 'at'?}],
    'outline', 'ups'}."""
    lines = []
    group, frame, door = b['group'], b['frame'], b['door']
    lines.append({'sev': 'ok', 'text': '%d piece%s, all joined (%s)' % (len(group), '' if len(group) == 1 else 's',
                                                                      ', '.join(sorted({g['id'] for g in group})[:6]) + ('…' if len(group) > 6 else ''))})
    if b.get('doubled'):
        lines.append({'sev': 'warning', 'text': '%d piece%s stand%s twice in the same spot (%s): delete the copy' % (
            len(b['doubled']), '' if len(b['doubled']) == 1 else 's', 's' if len(b['doubled']) == 1 else '',
            ', '.join(sorted({d['id'] for d in b['doubled']})[:4])),
            'at': [[round(d['p'][0]), round(d['p'][1]), round(d['p'][2])] for d in b['doubled'][:6]]})
    if door is None or frame is None:
        lines.append({'sev': 'error', 'text': 'No door: put a door in one of its walls (Place, then a load door of the style), '
                                              'then right-click the door.'})
        return {'ok': False, 'lines': lines, 'outline': None, 'ups': []}
    if door['to'] and door['to']['cell']:
        lines.append({'sev': 'warning', 'text': 'Door: %s. It leads to %s now; the new interior takes it over (Undo gives it back).' % (door['id'], door['to']['cell'])})
    else:
        lines.append({'sev': 'ok', 'text': 'Door: %s' % door['id']})
    g0 = ss.outline(db, group, frame, b['doors'], 0)
    if g0['closed']:
        lines.append({'sev': 'ok', 'text': 'Walls round: closed at the ground floor (%d m² inside the walls)' % round(g0['area'] / 4900.0)})
    else:
        gaps = _gap_spots(g0['wall'], frame)
        if gaps:
            lines.append({'sev': 'error', 'text': 'The walls are open at the ground floor: %d gap%s (%s)' % (
                len(gaps), '' if len(gaps) == 1 else 's', ', '.join('%d units wide at %d, %d' % (g[2], g[0], g[1]) for g in gaps[:4])),
                'at': [[g[0], g[1], round(frame.z + 100)] for g in gaps]})
        else:
            lines.append({'sev': 'error', 'text': 'The walls don\'t go round: there is no inside to build in (a wall is missing, or this '
                                                  'is not a building).'})
        g0b = ss.box_outline(group, frame)
        return {'ok': False, 'lines': lines, 'outline': g0b, 'ups': []}
    share, open_ = _roof(db, group, frame, g0['cells'])
    # (measured on 260 of the game's buildings, 2026-10-24: open to the sky over 3% of the floor at the median,
    # 30% at p90; towers with a walk on top read all open. So only a warning, past the game's p90)
    if share > ROOF_OPEN:
        lines.append({'sev': 'warning', 'text': 'Open to the sky over %d%% of the floor (9 in 10 of the game\'s buildings: under %d%%); '
                                                'fine for a tower with a walk on top' % (round(share * 100), round(ROOF_OPEN * 100)),
                      'at': [[x, y, round(frame.z + 300)] for x, y in open_[:6]]})
    else:
        lines.append({'sev': 'ok', 'text': 'Roofed over'})
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


def _split(tiles, parts=None, always=False, room_max=None):
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
                    out += _split_size(comp, room_max)
            return _merge_scraps(out)
    return _split_size(tiles, room_max)


def _split_size(tiles, room_max=None):
    """A floor's tiles cut into rooms of at most ROOM_MAX tiles: across the longer side, through the
    middle, again and again. [set of tiles] (each joined)."""
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


def _plan(db, b, kit=None, cover=COVER, floors=None, ch=None, tiles=None):
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
    for k, u in enumerate([] if tiles else ch['ups'], start=1):
        if k >= want or k > 2:
            break
        if not (u['closed'] and u['area'] >= UP_MIN * ch['outline']['area']):
            notes.append('Floor %d left out: the walls %d storey%s up don\'t close round.' % (k + 1, k, '' if k == 1 else 's'))
            break
        up = _tiles_in(set(map(tuple, u['cells'])), T, keep_door=False, cover=cover) & per[k - 1]
        if len(up) < 2:
            break
        per[k] = up
    # a door up high outside means a floor up there (the game's: 119 of 119), reaching the tile behind the door
    st_ = (kits.stairs(db, kit) or {}).get('storey') or kp.get('height') or ss.STOREY
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
    rooms, where = [], {}
    for f, ts in sorted(per.items()):
        for n, comp in enumerate(_split(ts, tile_parts, always, SHOP_ROOM_MAX if trade else None) if f == 0 else
                                 [c for comp in _components(ts) for c in _split(comp, tile_parts, always)]):
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
    pl0 = _plan(db, b, kit=kit, cover=COVER, floors=floors, ch=ch)
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
            pl = pl0 if (cover == COVER and n == want) else _plan(db, b, kit=kit, cover=cover, floors=n, ch=ch)
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

def preview(db, cell_key, ref_key, door_key=None, tolerance='usual'):
    """For the map: the building's check, the plan, and the planned tiles' corners in the world (to
    draw over the exterior), without building anything."""
    b = building_at(db, cell_key, ref_key, door_key)
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
        pl = plan(db, b, tolerance=tolerance)
    except EditError as e:
        ch = check(db, b)
        out.update({'ok': False, 'check': ch['lines'], 'error': str(e)})
        return out
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

def build(db, cell_key, ref_key, name, door_key=None, kit=None, floors=None, tiles=None, tolerance='usual'):
    """Plan, build, link the doors both ways and put the northmarker in."""
    import release
    b = building_at(db, cell_key, ref_key, door_key)
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
    pl = plan(db, b, kit=kit, floors=floors, tiles=tiles, tolerance=tolerance)
    if not pl['ok']:
        raise EditError('The building isn\'t closed and sound: %s' % '; '.join(l['text'] for l in pl['check'] if l['sev'] == 'error'))
    out = None
    for ex_ in (pl['exit'], {'room': pl['exit']['room'], 'side': 'S'}, {'room': pl['exit']['room'], 'side': 'E'},
                {'room': pl['exit']['room'], 'side': 'W'}):
        try:
            out = builder.build_house(db, name, pl['style'], pl['rooms'], pl['doors'], ex_, None)
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
            text = 'Fits its building about as loosely as Bethesda\'s own interiors fit theirs' + what + \
                ' (Bethesda\'s: up to %d%%, %d units; the closer ones for this building: up to %d%%, %d units)' % (
                    round(beth['share'] * 100), beth['jut'], round(lim_share * 100), lim_jut)
        else:
            text = 'Sticks out of its building more than the game\'s own interiors do, Bethesda\'s too' + what + \
                ' (the game\'s for this building: up to %d%%, %d units%s)' % (
                    round(lim_share * 100), lim_jut, '; Bethesda\'s: up to %d%%, %d units' % (round(beth['share'] * 100), beth['jut']) if beth else '')
        return {'share': g['share'], 'jut': g['jut'], 'floors': rows, 'band': band, 'ok': ok, 'close': close, 'text': text,
                'building': ed['cell'], 'door': ed['id']}
    return None
