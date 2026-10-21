"""How the game's own, hand-made interiors (Bethesda's and Tamriel Rebuilt's) are laid out and built,
style by style: the shapes and sizes of rooms of each kind, how many rooms a storey has and which kinds
sit next to each other, where the way in is; which pieces the game runs along one wall (one variant or
a mix), where it puts window pieces, endcaps and the three- and four-way hall pieces, and the columns
standing free inside big rooms; which rooms are open to the storey above; how many doorways a room
has, with a door, open or curtained, on the long or the short wall; and the commonest whole-house
layouts per style. Read-only: a report (packaging/nexus/layout-survey.md) for deciding how "Build from
pieces" plans and builds, and numbers the planner and builder can look up (see summary()).

Only places the game made and built from a kit's tiles count (kits.game_made, furnish.rooms); a room's
kind is told from what stands in it the way roomsurvey does. A room here is a space: tiles joined by
open archways (a doorway side of a piece with no door, curtain or frame in it) are one room, as a
Mournhold hall with arched bays is; a door, a curtain or a door frame ends a room."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey

_cache = {}
STOREY = 256
YAW = {'N': 0.0, 'E': math.pi / 2, 'S': math.pi, 'W': 3 * math.pi / 2}   # (the game turns clockwise from north)
WIN_RE = re.compile(r'win(dow)?(_|$)|_win|cwin|swin')
RAIL_RE = re.compile(r'rail|balustrade|banister')
NOFLOOR_RE = re.compile(r'nofloor|_nf(_|$)|no_floor')
CURTAIN_RE = re.compile(r'curtain|drape|cloth_door|hanging')
COLUMN_RE = re.compile(r'post|pillar|column')
STAIR_RE = re.compile(r'stair|ramp|ladder')
ROLE_WORDS = (('endcap', re.compile(r'endcap|_end(_|$)|_cap(_|$)')), ('4way', re.compile(r'4way|4_way|cross')),
              ('3way', re.compile(r'3way|3_way|_t(_|$)|tee')), ('window', WIN_RE), ('stair', re.compile(r'stair|ramp')),
              ('hall', re.compile(r'hall')), ('corner', re.compile(r'corner|cornr|_cnr|corin|corout')),
              ('side', re.compile(r'side|wall')), ('centre', re.compile(r'center|centre|floor|_mid')))


def is_window(low):
    """A window piece or prop by its id (not a wine rack, not a window's light)."""
    return bool(WIN_RE.search(low)) and 'wine' not in low and 'light' not in low


def family(prefix):
    """The style family a kit belongs to ('in_c' for the Common sets, 't_imp_setgc' for Gold Coast)."""
    parts = prefix.lower().split('_')
    return '_'.join(parts[:-1]) if len(parts) >= 3 else prefix.lower()


def role(pid):
    """What kind of piece an id names: endcap, 4way, 3way, window, hall, corner, side, centre, other."""
    low = pid.lower()
    for name, rx in ROLE_WORDS:
        if rx.search(low):
            return name
    return 'other'


def _canon(pattern):
    return min(''.join(kits.rotate(pattern, q)[s][0].upper() for s in kits.SIDES) for q in range(4))


def _disk(db, limit):
    import hashlib
    import project
    sig = hashlib.md5('|'.join(sorted(p['name'].lower() for p in (db.plugins or []))).encode('utf-8')).hexdigest()[:12]
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'layoutsurvey_%s_%d_v3.json' % (sig, limit))


LIMIT = 6000                 # (every place the game has: about a minute)
_thread = {}


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); otherwise None, with the survey started in
    the background so it's there next time (about a minute the first time)."""
    import threading
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db, limit)):
            return survey(db, limit)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('the game\'s room shapes, columns and windows', lambda: survey(db, limit), task=('layoutsurvey', 'survey', [limit]))
    return None


def survey(db, limit=LIMIT, progress=None):
    """One record per room and one per place, over the game's places built from kit tiles (kept on
    disk once done): {'cells': n, 'rooms': [room records], 'places': [place records]}."""
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db, limit)
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache[key] = (db.recs, saved)
        return saved
    except Exception:
        pass
    out = _survey(db, limit, progress)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def _kit_tiles(db, m):
    """The kit tiles of a place: T, {(gx, gy, lv): {id, q, pat, canon, prefix, x, y, floor, height, role}}."""
    found, T = [], None
    kp_of = {}
    for r in m['refs']:
        prefix = kits.kit_prefix(r['id'])
        if not prefix or prefix not in kits.kits(db):
            continue
        if prefix not in kp_of:
            kp_of[prefix] = kits.kit_pieces(db, prefix)
        kp = kp_of[prefix]
        if not kp:
            continue
        piece = next((p for p in kp['pieces'] if p['id'].lower() == r['id'].lower()), None)
        if not piece or abs((r['s'] or 1) - 1) > 0.05:
            continue
        T = T or kp['tile']
        if kp['tile'] != T:
            continue
        found.append((r, prefix, piece))
    if not found:
        return T, {}, (0, 0)
    # the grid's origin: where the tiles stand (some places stand on half-tile offsets)
    res = Counter((int(round(r['p'][0] % T / 16)) * 16 % T, int(round(r['p'][1] % T / 16)) * 16 % T) for r, _p, _pc in found)
    ox, oy = res.most_common(1)[0][0]
    tiles = {}
    for r, prefix, piece in found:
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        pat = kits.rotate(piece['pattern'], q)
        floor = r['p'][2] + piece['zmin']
        k = (int(round((r['p'][0] - ox) / T)), int(round((r['p'][1] - oy) / T)), int(round(floor / 64)))
        tiles[k] = {'id': r['id'].lower(), 'q': q, 'pat': pat, 'canon': _canon(piece['pattern']), 'prefix': prefix,
                    'x': r['p'][0], 'y': r['p'][1], 'floor': floor, 'height': piece['height'], 'role': role(r['id'])}
    return T, tiles, (ox, oy)


def tiles_ids(tiles):
    return {t['id'] for t in tiles.values()}


def _fill_gaps(tiles, T):
    """A tile missing between two tiles of a storey whose sides towards it are open (a style's
    two-tile-long wall piece, which the kit doesn't count as a tile; Velothi has them) is taken as an
    open tile, so the room isn't cut in two."""
    for (gx, gy, lv), t in list(tiles.items()):
        for s, (dx, dy) in (('E', (1, 0)), ('N', (0, 1))):
            mid, far = (gx + dx, gy + dy, lv), (gx + 2 * dx, gy + 2 * dy, lv)
            if mid in tiles or far not in tiles:
                continue
            if t['pat'][s] == 'wall' or tiles[far]['pat'][furnish.OPP[s]] == 'wall':
                continue
            pat = {k: 'open' for k in kits.SIDES}
            pat.update(cover={}, offset={})
            tiles[mid] = {'id': '(gap)', 'q': 0, 'pat': pat, 'canon': 'OOOO', 'prefix': t['prefix'], 'x': t['x'] + dx * T,
                          'y': t['y'] + dy * T, 'floor': t['floor'], 'height': t['height'], 'role': 'gap'}


def _spaces(tiles, T, frames):
    """Tiles side by side and open towards each other make one space, unless a door frame stands
    between them (as furnish.rooms groups them)."""
    def framed(a, b):
        mx, my = (a['x'] + b['x']) / 2, (a['y'] + b['y']) / 2
        return any(abs(fx - mx) < 40 and abs(fy - my) < 40 and abs(fz - a['floor']) < 200 for fx, fy, fz in frames)
    seen, out = set(), []
    for k in sorted(tiles):
        if k in seen:
            continue
        group, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            group.append(c)
            for s, (dx, dy) in furnish.STEP.items():
                nk = (c[0] + dx, c[1] + dy, c[2])
                if nk in tiles and nk not in seen and tiles[c]['pat'][s] == 'open' and tiles[nk]['pat'][furnish.OPP[s]] == 'open' \
                        and not framed(tiles[c], tiles[nk]):
                    seen.add(nk)
                    todo.append(nk)
        out.append(group)
    out.sort(key=lambda g: (-len(g), g[0]))
    return out


def _survey(db, limit, progress=None):
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    # (a spread over the whole list, so every style gets its share: the names run A to Z)
    step = max(1, len(cells) // (limit * 2))
    cells = cells[::step]
    rooms_out, places_out = [], []
    props = defaultdict(list)
    seen = 0
    for ck in cells:
        if seen >= limit:
            break
        try:
            m = mapdata.cellmap(db, ck)
            if not m.get('exists') or not m.get('interior'):
                continue
            T, tiles, origin = _kit_tiles(db, m)
        except Exception:
            continue
        if len(tiles) < 3:
            continue
        seen += 1
        if progress:
            progress(seen, ck)
        try:
            _place(db, ck, m, T, tiles, origin, rooms_out, places_out, props)
        except Exception as e:          # (one odd place must not lose the survey)
            places_out.append({'cell': ck, 'error': '%s: %s' % (type(e).__name__, e)})
    # the window props per family: how the game stands each against a wall (medians), and in which rooms
    out_props = defaultdict(dict)
    for (fam, low), lst in props.items():
        if len(lst) < 4:
            continue
        turns = Counter(p[3] for p in lst)
        out_props[fam][low] = {'n': len(lst), 'out': _med([p[0] for p in lst]), 'along': _med([p[1] for p in lst]),
                               'z': _med([p[2] for p in lst]), 'turn': turns.most_common(1)[0][0],
                               'turn_share': round(turns.most_common(1)[0][1] / float(len(lst)), 2),
                               'walled': round(sum(1 for p in lst if p[4]) / float(len(lst)), 2),
                               'kinds': dict(Counter(p[5] for p in lst))}
    return {'cells': seen, 'rooms': rooms_out, 'places': places_out, 'props': dict(out_props)}


def _near(items, x, y, z, d=110, dz=200):
    return any(math.hypot(r['p'][0] - x, r['p'][1] - y) < d and abs(r['p'][2] - z) < dz for r in items)


def _place(db, ck, m, T, tiles, origin, rooms_out, places_out, props=None):
    ox, oy = origin
    cell_of = lambda x, y: (int(round((x - ox) / T)), int(round((y - oy) / T)))
    style = Counter(t['prefix'] for t in tiles.values()).most_common(1)[0][0]
    fam = family(style)
    theme = roomsurvey.theme_of(ck)
    refs = m['refs']
    kp_ids = {p['id'].lower() for p in (kits.kit_pieces(db, style) or {}).get('pieces', [])}
    for r in refs:
        r['_fam'] = roomsurvey.family_of(db, r['id'], r['type']) if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC') else None
    doors = [r for r in refs if r['type'] == 'DOOR']
    load = [r for r in doors if r.get('to')]
    way_out = [r for r in load if not r['to'].get('cell')] or load
    jambs = [r for r in refs if r['type'] == 'STAT' and 'jamb' in r['id'].lower()]
    curtains = [r for r in refs if r['type'] in ('STAT', 'ACTI') and CURTAIN_RE.search(r['id'].lower())]
    stairs = [r for r in refs if r['type'] == 'STAT' and STAIR_RE.search(r['id'].lower())]
    columns = [r for r in refs if r['type'] == 'STAT' and COLUMN_RE.search(r['id'].lower()) and r.get('b') and r['id'].lower() not in kp_ids]
    rails = [r for r in refs if r['type'] == 'STAT' and RAIL_RE.search(r['id'].lower())]
    # window pieces: the style's own (a bay, a window wall, a windowed side: most aren't full tiles, so
    # they aren't in the kit's tiles), placed by the tile they stand in or against
    windows = [r for r in refs if r['type'] == 'STAT' and is_window(r['id'].lower()) and r.get('b') and r['id'].lower() not in tiles_ids(tiles)]
    _fill_gaps(tiles, T)
    frames = [(j['p'][0], j['p'][1], j['p'][2]) for j in jambs] + [(d['p'][0], d['p'][1], d['p'][2]) for d in doors]
    spaces = []
    for group in _spaces(tiles, T, frames):
        xs = [tiles[k]['x'] for k in group]
        ys = [tiles[k]['y'] for k in group]
        spaces.append({'keys': group, 'rm': {'floor': min(tiles[k]['floor'] for k in group), 'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2,
                                             'y_min': min(ys) - T / 2, 'y_max': max(ys) + T / 2}})
    if not spaces:
        return
    # storeys: by height from the entrance's floor (else the lowest), a storey every 256 units
    ent_floor = None
    for d in way_out:
        for sp in spaces:
            rm = sp['rm']
            if rm['x_min'] - 8 <= d['p'][0] <= rm['x_max'] + 8 and rm['y_min'] - 8 <= d['p'][1] <= rm['y_max'] + 8 and rm['floor'] - 100 <= d['p'][2] <= rm['floor'] + 300:
                ent_floor = rm['floor']
                break
        if ent_floor is not None:
            break
    base = ent_floor if ent_floor is not None else min(sp['rm']['floor'] for sp in spaces)
    lv_of = lambda z: int(round((z - base) / STOREY))
    space_of = {}                       # (gx, gy, storey) -> space index
    for n, sp in enumerate(spaces):
        sp['lv'] = lv_of(sp['rm']['floor'])
        for k in sp['keys']:
            space_of[(k[0], k[1], sp['lv'])] = n
    # spaces joined by an open archway (a doorway side with no door, curtain or frame in it) are one room
    parent = list(range(len(spaces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for n, sp in enumerate(spaces):
        for k in sp['keys']:
            t = tiles[k]
            for s, (dx, dy) in furnish.STEP.items():
                if t['pat'][s] != 'door':
                    continue
                other = space_of.get((k[0] + dx, k[1] + dy, sp['lv']))
                if other is None or other == n:
                    continue
                mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
                if not (_near(doors, mx, my, t['floor']) or _near(curtains, mx, my, t['floor']) or _near(jambs, mx, my, t['floor'], 60)):
                    parent[find(n)] = find(other)
    merged = defaultdict(list)
    for n in range(len(spaces)):
        merged[find(n)].append(n)
    rooms = []
    for members in merged.values():
        keys = [k for n in members for k in spaces[n]['keys']]
        xs = [tiles[k]['x'] for k in keys]
        ys = [tiles[k]['y'] for k in keys]
        rooms.append({'keys': keys, 'cells': {k[:2] for k in keys}, 'lv': spaces[members[0]]['lv'],
                      'floor': min(tiles[k]['floor'] for k in keys), 'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2,
                      'y_min': min(ys) - T / 2, 'y_max': max(ys) + T / 2, 'spaces': len(members)})
    room_of = {}
    for n, rm in enumerate(rooms):
        for k in rm['keys']:
            room_of[(k[0], k[1], rm['lv'])] = n
    levels = sorted({rm['lv'] for rm in rooms})

    def in_room(rm, x, y, z, up=300):
        return cell_of(x, y) in rm['cells'] and rm['floor'] - 100 <= z <= rm['floor'] + up
    entrance = None
    for d in way_out:
        entrance = next((n for n, rm in enumerate(rooms) if in_room(rm, d['p'][0], d['p'][1], d['p'][2])), None)
        if entrance is None:
            # (a door standing just past the room's edge, in a frame piece: the nearest tile at its height)
            near_ = [(math.hypot(t['x'] - d['p'][0], t['y'] - d['p'][1]), k) for k, t in tiles.items()
                     if abs(t['floor'] - d['p'][2]) < 300 and math.hypot(t['x'] - d['p'][0], t['y'] - d['p'][1]) < T * 1.2]
            if near_:
                k = min(near_)[1]
                entrance = room_of.get((k[0], k[1], lv_of(tiles[k]['floor'])))
        if entrance is not None:
            break
    kinds = {}
    recs = {}
    for n, rm in enumerate(rooms):
        keys, cells_, lv = rm['keys'], rm['cells'], rm['lv']
        inside = [r for r in refs if r['_fam'] and in_room(rm, r['p'][0], r['p'][1], r['p'][2] + r['b'][2] * (r.get('s') or 1))]
        counts = Counter(r['_fam'] for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS)
        kind = roomsurvey.room_kind(counts)
        kinds[n] = kind
        w = int(round((rm['x_max'] - rm['x_min']) / T))
        h = int(round((rm['y_max'] - rm['y_min']) / T))
        fill = len(cells_) / float(w * h)
        corridor = max(w, h) >= 3 and not any({(x + 1, y), (x, y + 1), (x + 1, y + 1)} <= cells_ for x, y in cells_)
        # the shape: a rectangle, a rectangle less a tile or two (a nook), an L, or something more cut up
        if fill >= 0.999:
            shape = 'rect'
        elif w * h - len(cells_) <= 2:
            shape = 'nook'
        elif _is_L(cells_):
            shape = 'L'
        else:
            shape = 'other'
        # each tile's walled sides face the outside (no tile beyond on this storey) or another room;
        # its doorway sides are doorways out of the room, or arches inside it
        outside = inside_w = arches = 0
        win_out = win_in = 0
        door_spots = {}
        for k in keys:
            t = tiles[k]
            gx, gy = k[:2]
            for s, (dx, dy) in furnish.STEP.items():
                beyond = room_of.get((gx + dx, gy + dy, lv))
                if t['pat'][s] == 'wall':
                    if beyond is None:
                        outside += 1
                    elif beyond != n:
                        inside_w += 1
                    # (a door hung in a wall piece's own opening: Velothi's walls have doorways the
                    # measurement doesn't see; a door right on the wall line is one)
                    mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
                    if _near(doors, mx, my, t['floor'], T * 0.55):
                        door_spots[(int(round(mx / 32)), int(round(my / 32)))] = (mx, my, s, beyond)
                elif t['role'] == 'gap' and beyond != n:
                    # (a tile the kit doesn't know, with a door on its edge: a doorway)
                    mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
                    if _near(doors, mx, my, t['floor'], T * 0.55):
                        door_spots[(int(round(mx / 32)), int(round(my / 32)))] = (mx, my, s, beyond)
                elif t['pat'][s] == 'door':
                    if beyond == n:
                        arches += 1
                        continue
                    mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
                    door_spots[(int(round(mx / 32)), int(round(my / 32)))] = (mx, my, s, beyond)
        # the window pieces standing in or against this room's tiles: on an outside wall, or one
        # towards another room
        for wr in windows:
            wx, wy, wz = wr['p'][0], wr['p'][1], wr['p'][2] + wr['b'][2] * (wr.get('s') or 1)
            if not (rm['floor'] - 100 <= wz <= rm['floor'] + 200):
                continue
            k = min(keys, key=lambda k_: math.hypot(tiles[k_]['x'] - wx, tiles[k_]['y'] - wy))
            t = tiles[k]
            dx, dy = wx - t['x'], wy - t['y']
            if max(abs(dx), abs(dy)) > T * 0.75:
                continue
            if max(abs(dx), abs(dy)) < T * 0.3:
                sides = [s for s in kits.SIDES if t['pat'][s] == 'wall']
            else:
                sides = [('E' if dx > 0 else 'W') if abs(dx) > abs(dy) else ('N' if dy > 0 else 'S')]
            if any(room_of.get((k[0] + furnish.STEP[s][0], k[1] + furnish.STEP[s][1], lv)) is None for s in sides):
                win_out += 1
            else:
                win_in += 1
            # how the game stands this prop against the tile: how far out from the tile's centre towards
            # the wall, how far along it, how high its origin is over the floor, and its turn relative to
            # the side it faces (for the builder: window_props())
            if len(sides) == 1 and props is not None:
                s = sides[0]
                out = abs(dx) if s in 'EW' else abs(dy)
                along = dy if s in 'EW' else dx
                rel = (wr['p'][5] - YAW[s]) % (2 * math.pi)
                props[(fam, wr['id'].lower())].append((round(out), round(abs(along)), round(wr['p'][2] - t['floor']),
                                                       int(round(rel / (math.pi / 2))) % 4, t['pat'][s] == 'wall', kind))
        # door frames standing on the room's edge
        for j in jambs:
            if not (rm['floor'] - 60 <= j['p'][2] <= rm['floor'] + 200):
                continue
            x, y = j['p'][0], j['p'][1]
            # (a frame stands on the line between two tiles: half a tile from both centres)
            hit = None
            for s, (dx, dy) in furnish.STEP.items():
                cx, cy = x - dx * T / 2, y - dy * T / 2
                c = cell_of(cx, cy)
                if abs(cx - ox - c[0] * T) < 40 and abs(cy - oy - c[1] * T) < 40 and c in cells_ and room_of.get((c[0], c[1], lv)) == n:
                    hit = (s, c)
                    break
            if not hit:
                continue
            s, c = hit
            dx, dy = furnish.STEP[s]
            beyond = room_of.get((c[0] + dx, c[1] + dy, lv))
            if beyond == n:
                continue
            door_spots[(int(round(x / 32)), int(round(y / 32)))] = (x, y, s, beyond)
        # each doorway: with a door, a curtain, or open; on the long wall or the short end; to another
        # room, to the way out, to stairs, or to nothing on this storey
        dk, dwall, dto = Counter(), Counter(), Counter()
        exits = 0
        for (mx, my, s, beyond) in door_spots.values():
            z = rm['floor']
            dk['door' if _near(doors, mx, my, z) else 'curtain' if _near(curtains, mx, my, z) else 'open'] += 1
            if w != h:
                dwall['long' if (s in 'NS') == (w > h) else 'short'] += 1
            if _near(load, mx, my, z):
                exits += 1
                dto['out'] += 1
            elif beyond is not None:
                dto['room'] += 1
            elif _near(stairs, mx + furnish.STEP[s][0] * T / 2, my + furnish.STEP[s][1] * T / 2, z, T * 0.8, 400):
                dto['stairs'] += 1
            else:
                dto['nothing'] += 1
        # the pieces along each outside wall, in runs of two or more tiles whose walled side faces the
        # same way; among the pieces of one shape in a run (the sides, say, not the corners at its
        # ends): one variant, alternating, or mixed
        runs = []
        for s, (dx, dy) in furnish.STEP.items():
            along = sorted((k for k in keys if tiles[k]['pat'][s] == 'wall' and room_of.get((k[0] + dx, k[1] + dy, lv)) is None),
                           key=lambda k: (k[0], k[1]) if s in 'EW' else (k[1], k[0]))
            run = []
            for k in along:
                if run and ((s in 'EW' and k[0] == run[-1][0] and k[1] == run[-1][1] + 1) or (s in 'NS' and k[1] == run[-1][1] and k[0] == run[-1][0] + 1)):
                    run.append(k)
                else:
                    if len(run) >= 2:
                        runs.append(run)
                    run = [k]
            if len(run) >= 2:
                runs.append(run)
        run_kinds = Counter()
        run_len = []
        for run in runs:
            run_len.append(len(run))
            by_shape = defaultdict(list)
            for k in run:
                by_shape[tiles[k]['canon']].append(tiles[k]['id'])
            for ids in by_shape.values():
                if len(ids) < 2:
                    continue
                if len(set(ids)) == 1:
                    run_kinds['one'] += 1
                elif len(set(ids)) == 2 and len(ids) >= 3 and all(ids[i] == ids[i % 2] for i in range(len(ids))):
                    run_kinds['alternating'] += 1
                else:
                    run_kinds['mixed'] += 1
        # columns standing free inside the room (a third of a tile or more from its walls), and whether
        # they stand on the tile grid (at a tile's centre, on an edge, or at a corner between tiles)
        cols = []
        for c in columns:
            # (by the body of the column, not its origin: a half pillar's origin is a tile from its body)
            sc = c.get('s') or 1
            bx, by = (c['b'][0] + c['b'][3]) / 2 * sc, (c['b'][1] + c['b'][4]) / 2 * sc
            th = c['p'][5]
            x = c['p'][0] + bx * math.cos(th) + by * math.sin(th)
            y = c['p'][1] - bx * math.sin(th) + by * math.cos(th)
            z = c['p'][2] + c['b'][2] * sc
            if not in_room(rm, x, y, z, 100):
                continue
            # the distance to the nearest outside wall of the room's own tiles
            dist = T
            for (tx, ty) in cells_:
                for s, (dx, dy) in furnish.STEP.items():
                    if (tx + dx, ty + dy) in cells_:
                        continue
                    ex, ey = ox + (tx + dx * 0.5) * T, oy + (ty + dy * 0.5) * T
                    if s in 'NS' and abs(x - ox - tx * T) <= T / 2:
                        dist = min(dist, abs(y - ey))
                    elif s in 'EW' and abs(y - oy - ty * T) <= T / 2:
                        dist = min(dist, abs(x - ex))
            if dist < T * 0.3:
                continue
            fx, fy = ((x - ox) / T) % 1, ((y - oy) / T) % 1
            nx, ny = min(fx, 1 - fx), min(fy, 1 - fy)             # distance from a tile centre line, in tiles
            at = 'centre' if max(nx, ny) < 0.15 else 'corner' if min(nx, ny) > 0.35 else 'edge' if max(nx, ny) > 0.35 else 'off'
            cols.append((c['id'].lower(), at, round(dist), x, y))
        col_nn = []
        for i, a in enumerate(cols):
            ds = [math.hypot(a[3] - b[3], a[4] - b[4]) for j, b in enumerate(cols) if j != i]
            if ds:
                col_nn.append(round(min(ds)))
        # open to the storey above: tiles of this room with no tile over them although the storey above
        # has tiles beside that spot (a gallery, a stairwell, a double-height hall); railings and
        # no-floor pieces
        open_above = 0
        if any(lv2 == lv + 1 for lv2 in levels):
            for (gx, gy) in cells_:
                if (gx, gy, lv + 1) in room_of:
                    continue
                if sum(1 for dx, dy in furnish.STEP.values() if (gx + dx, gy + dy, lv + 1) in room_of) >= 2:
                    open_above += 1
        rails_here = sum(1 for r in rails if rm['x_min'] - 40 <= r['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= r['p'][1] <= rm['y_max'] + 40
                         and rm['floor'] - 40 <= r['p'][2] <= rm['floor'] + 200)
        nofloor = sum(1 for k in keys if NOFLOOR_RE.search(tiles[k]['id']))
        ceiling_h = sorted(tiles[k]['height'] for k in keys)[len(keys) // 2]
        rec = {'cell': ck, 'style': style, 'family': family(style), 'theme': theme, 'level': lv, 'kind': kind,
               'tiles': len(cells_), 'w': w, 'h': h, 'long': max(w, h), 'short': min(w, h), 'fill': round(fill, 2), 'shape': shape,
               'corridor': corridor, 'spaces': rm['spaces'], 'arches': arches // 2, 'entrance': n == entrance, 'doors': len(door_spots),
               'door_kinds': dict(dk), 'door_walls': dict(dwall), 'door_to': dict(dto), 'exits': exits,
               'outside_walls': outside, 'inside_walls': inside_w, 'win_out': win_out, 'win_in': win_in,
               'roles': dict(Counter(tiles[k]['role'] for k in keys)), 'runs': dict(run_kinds), 'run_len': run_len,
               'columns': len(cols), 'col_at': dict(Counter(c_[1] for c_ in cols)), 'col_ids': dict(Counter(c_[0] for c_ in cols)),
               'col_dist': [c_[2] for c_ in cols], 'col_nn': col_nn, 'open_above': open_above, 'rails': rails_here, 'nofloor': nofloor, 'height': ceiling_h,
               'gaps': sum(1 for k in keys if tiles[k]['role'] == 'gap')}
        recs[n] = rec
        rooms_out.append(rec)
    # the place: rooms per storey, their kinds, which touch and whether a doorway joins them
    per_level = defaultdict(list)
    for n, rec in recs.items():
        per_level[rec['level']].append(('*' if rec['entrance'] else '') + rec['kind'])
    adj = []
    for i, a in enumerate(rooms):
        for j in range(i + 1, len(rooms)):
            b = rooms[j]
            if a['lv'] != b['lv']:
                continue
            touch = joined = False
            for k in a['keys']:
                for s, (dx, dy) in furnish.STEP.items():
                    if room_of.get((k[0] + dx, k[1] + dy, a['lv'])) == j:
                        touch = True
                        t = tiles[k]
                        other = tiles.get(next((kk for kk in b['keys'] if kk[:2] == (k[0] + dx, k[1] + dy)), None))
                        if t['pat'][s] == 'door' or (other and other['pat'][furnish.OPP[s]] == 'door'):
                            joined = True
                        mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
                        if _near(jambs, mx, my, t['floor'], 60) or _near(doors, mx, my, t['floor'], T * 0.55):
                            joined = True
            if touch:
                adj.append([kinds[i], kinds[j], joined])
    grammar = ' | '.join('%+d: %s' % (lv, ','.join(sorted(ks))) for lv, ks in sorted(per_level.items()))
    places_out.append({'cell': ck, 'style': style, 'family': family(style), 'theme': theme, 'levels': len(levels),
                       'rooms': len(recs), 'per_level': {str(lv): len(ks) for lv, ks in per_level.items()},
                       'kinds_per_level': {str(lv): sorted(ks) for lv, ks in per_level.items()},
                       'entrance_kind': kinds.get(entrance), 'entrance_tiles': recs[entrance]['tiles'] if entrance in recs else None,
                       'way_out': len(way_out), 'adj': adj, 'grammar': grammar, 'tiles': len(tiles),
                       'columns': len(columns), 'rails': len(rails), 'stairs': len(stairs)})


def _is_L(cells_):
    """Two rectangles sharing a corner: the bounding box less one rectangular corner."""
    xs, ys = [c[0] for c in cells_], [c[1] for c in cells_]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    missing = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)} - cells_
    if not missing:
        return False
    mx, my = [c[0] for c in missing], [c[1] for c in missing]
    if len(missing) != (max(mx) - min(mx) + 1) * (max(my) - min(my) + 1):
        return False
    return (min(mx) == x0 or max(mx) == x1) and (min(my) == y0 or max(my) == y1)


# ------------------------------------------------------------------ the numbers, per style
def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _pct(n, d):
    return round(100.0 * n / d) if d else None


def summary(db, by='family', min_rooms=12, limit=LIMIT):
    """The findings as numbers, per style family (or per kit with by='style'): {name: {...}}."""
    key = ('summary', by, min_rooms, limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    out = _summary(db, by, min_rooms, limit)
    _cache[key] = (db.recs, out)
    return out


def _summary(db, by, min_rooms, limit):
    s = survey(db, limit)
    groups = defaultdict(list)
    for r in s['rooms']:
        groups[r[by]].append(r)
    pgroups = defaultdict(list)
    for p in s['places']:
        if 'error' not in p:
            pgroups[p[by]].append(p)
    out = {}
    for name, rooms in groups.items():
        if len(rooms) < min_rooms:
            continue
        places = pgroups.get(name, [])
        n = len(rooms)
        kinds = {}
        for kind in sorted({r['kind'] for r in rooms}):
            rk = [r for r in rooms if r['kind'] == kind]
            if len(rk) < 4:
                continue
            kinds[kind] = {'n': len(rk), 'tiles': _med([r['tiles'] for r in rk]), 'long': _med([r['long'] for r in rk]),
                           'short': _med([r['short'] for r in rk]), 'square': _pct(sum(1 for r in rk if r['w'] == r['h']), len(rk)),
                           'rect': _pct(sum(1 for r in rk if r['shape'] == 'rect'), len(rk)),
                           'doors': round(sum(r['doors'] for r in rk) / float(len(rk)), 1),
                           'win': _pct(sum(1 for r in rk if r['win_out'] + r['win_in']), len(rk)),
                           'columns': _pct(sum(1 for r in rk if r['columns']), len(rk)),
                           'entrance': _pct(sum(1 for r in rk if r['entrance']), len(rk)),
                           'sizes': dict(Counter('%dx%d' % (r['long'], r['short']) for r in rk).most_common(5))}
        corr = [r for r in rooms if r['corridor']]
        dk, dw, dto, runs = Counter(), Counter(), Counter(), Counter()
        for r in rooms:
            dk.update(r['door_kinds'])
            dw.update(r['door_walls'])
            dto.update(r['door_to'])
            runs.update(r['runs'])
        win_rooms = [r for r in rooms if r['win_out'] + r['win_in']]
        col_rooms = [r for r in rooms if r['columns']]
        col_at = Counter()
        col_ids = Counter()
        for r in col_rooms:
            col_at.update(r['col_at'])
            col_ids.update(r['col_ids'])
        big = [r for r in rooms if r['tiles'] >= 9]
        roles = Counter()
        for r in rooms:
            roles.update(r['roles'])
        tiles_total = sum(r['tiles'] for r in rooms)
        adj = Counter()
        adj_door = Counter()
        for p in places:
            for a, b, joined in p['adj']:
                k = '|'.join(sorted((a, b)))
                adj[k] += 1
                if joined:
                    adj_door[k] += 1
        grammars = Counter(p['grammar'] for p in places)
        by_theme = defaultdict(Counter)
        for p in places:
            by_theme[p['theme']][p['grammar']] += 1
        ent = Counter(p['entrance_kind'] for p in places if p['entrance_kind'])
        out[name] = {
            'rooms': n, 'places': len(places),
            'rooms_per_place': _med([p['rooms'] for p in places]), 'levels': dict(Counter(p['levels'] for p in places)),
            'rooms_per_level': _med([v for p in places for v in p['per_level'].values()]),
            'tiles_per_place': _med([p['tiles'] for p in places]), 'tiles_per_room': _med([r['tiles'] for r in rooms]),
            'shape': {k: _pct(sum(1 for r in rooms if r['shape'] == k), n) for k in ('rect', 'nook', 'L', 'other')},
            'corridors': {'share': _pct(len(corr), n), 'width': dict(Counter(r['short'] for r in corr)),
                          'length': _med([r['long'] for r in corr]), 'kinds': dict(Counter(r['kind'] for r in corr).most_common(4))},
            'kinds': kinds,
            'entrance': dict(ent.most_common(5)), 'entrance_tiles': _med([p['entrance_tiles'] for p in places if p['entrance_tiles']]),
            'doors_per_room': round(sum(r['doors'] for r in rooms) / float(n), 2),
            'arches_per_room': round(sum(r['arches'] for r in rooms) / float(n), 2),
            'door_kinds': {k: _pct(v, sum(dk.values())) for k, v in dk.items()},
            'door_walls': {k: _pct(v, sum(dw.values())) for k, v in dw.items()},
            'door_to': {k: _pct(v, sum(dto.values())) for k, v in dto.items()},
            'runs': {k: _pct(v, sum(runs.values())) for k, v in runs.items()}, 'runs_n': sum(runs.values()),
            'windows': {'rooms': _pct(len(win_rooms), n), 'per_room': round(sum(r['win_out'] + r['win_in'] for r in win_rooms) / float(len(win_rooms)), 1) if win_rooms else 0,
                        'outside': _pct(sum(r['win_out'] for r in rooms), sum(r['win_out'] + r['win_in'] for r in rooms)),
                        'per_outside_wall': round(sum(r['win_out'] for r in rooms) / float(max(1, sum(r['outside_walls'] for r in rooms))), 3),
                        'kinds': dict(Counter(r['kind'] for r in win_rooms).most_common(4))},
            'roles': {k: round(v / float(tiles_total), 3) for k, v in roles.most_common()},
            'columns': {'rooms': _pct(len(col_rooms), n), 'big_rooms': _pct(sum(1 for r in big if r['columns']), len(big)) if big else None,
                        'per_9_tiles': round(9.0 * sum(r['columns'] for r in col_rooms) / float(max(1, sum(r['tiles'] for r in col_rooms))), 2) if col_rooms else 0,
                        'at': {k: _pct(v, sum(col_at.values())) for k, v in col_at.items()}, 'ids': dict(col_ids.most_common(4)),
                        'dist': _med([d for r in col_rooms for d in r['col_dist']]), 'spacing': _med([d for r in col_rooms for d in r['col_nn']])},
            'open_above': {'rooms': _pct(sum(1 for r in rooms if r['open_above']), n), 'rails_rooms': _pct(sum(1 for r in rooms if r['rails']), n),
                           'nofloor_rooms': _pct(sum(1 for r in rooms if r['nofloor']), n)},
            'height': _med([r['height'] for r in rooms]),
            'adjacent': [[k, v, _pct(adj_door[k], v)] for k, v in adj.most_common(10)],
            'grammar': [[g, c] for g, c in grammars.most_common(8)],
            'grammar_by_theme': {th: [[g, c] for g, c in cnt.most_common(4)] for th, cnt in by_theme.items() if sum(cnt.values()) >= 3},
            'themes': dict(Counter(p['theme'] for p in places)),
            'props': s.get('props', {}).get(name if by == 'family' else family(name), {}),
        }
    return out


def report(db, by='family', limit=LIMIT):
    """The findings in words, style by style."""
    s = summary(db, by, limit=limit)
    lines = []
    for name, d in sorted(s.items(), key=lambda kv: -kv[1]['rooms']):
        lines.append('== %s: %d places, %d rooms; %s rooms a place (median), %s a storey, %s tiles a place, %s a room; storeys %s' % (
            name, d['places'], d['rooms'], d['rooms_per_place'], d['rooms_per_level'], d['tiles_per_place'], d['tiles_per_room'], d['levels']))
        lines.append('   shapes: rect %s%%, nook %s%%, L %s%%, other %s%%; corridors %s%% of rooms (width %s, length %s, %s)' % (
            d['shape']['rect'], d['shape']['nook'], d['shape']['L'], d['shape']['other'], d['corridors']['share'],
            d['corridors']['width'], d['corridors']['length'], d['corridors']['kinds']))
        for kind, k in sorted(d['kinds'].items(), key=lambda kv: -kv[1]['n']):
            lines.append('   %-8s n %3d: %s tiles (%sx%s) %s, square %s%%, rect %s%%, doors %s, windows %s%%, columns %s%%, is the entrance %s%%' % (
                kind, k['n'], k['tiles'], k['long'], k['short'], k['sizes'], k['square'], k['rect'], k['doors'], k['win'], k['columns'], k['entrance']))
        lines.append('   entrance room: %s (%s tiles); doorways per room %s (open arches inside a room %s); %s; on the %s; to %s' % (
            d['entrance'], d['entrance_tiles'], d['doors_per_room'], d['arches_per_room'], d['door_kinds'], d['door_walls'], d['door_to']))
        lines.append('   wall runs (%d): %s; windows: %s' % (d['runs_n'], d['runs'], d['windows']))
        lines.append('   piece roles per tile: %s' % d['roles'])
        lines.append('   columns: %s; open above: %s; height %s' % (d['columns'], d['open_above'], d['height']))
        lines.append('   adjacent (pairs, with a doorway %%): %s' % d['adjacent'])
        for g, c in d['grammar']:
            lines.append('   layout x%d: %s' % (c, g))
        for th, lst in sorted(d['grammar_by_theme'].items(), key=lambda kv: -d['themes'].get(kv[0], 0)):
            lines.append('   %s (%d places): %s' % (th, d['themes'].get(th, 0), '; '.join('x%d %s' % (c, g) for g, c in lst)))
        for low, p in sorted(d.get('props', {}).items(), key=lambda kv: -kv[1]['n']):
            lines.append('   window prop %s: n %d, out %s, along %s, z %s, turn q%d (%s), on a walled side %s' % (
                low, p['n'], p['out'], p['along'], p['z'], p['turn'], p['turn_share'], p['walled']))
    return '\n'.join(lines)


# ------------------------------------------------------------------ for the builder
# how much more often the game windows a room of each kind (storerooms, halls and landings get none)
WINDOW_KINDS = {'bedroom': 1.0, 'study': 1.0, 'shop': 1.0, 'tavern': 1.0, 'kitchen': 0.8, 'living': 0.5, 'shrine': 0.5}
COLUMN_MIN_SHARE = 50        # columns only where at least half the game's big rooms of the style have them (%)


def _fam(db, style):
    """This style's family numbers, when the survey is to hand (else None; it starts in the background)."""
    if ready(db) is None:
        return None
    return summary(db, 'family').get(family(style))


def window_rate(db, style):
    """How often the game puts a window on an outside wall side of this style's family (props per outside
    wall side of a tile), and the share of rooms of each kind with one: (rate, {kind: share})."""
    d = _fam(db, style)
    if not d:
        return 0.0, {}
    return d['windows']['per_outside_wall'], {k: (v['win'] or 0) / 100.0 for k, v in d['kinds'].items()}


def window_props(db, style):
    """The window props the game hangs on walls in this style's family, as the builder lays them:
    [{'id', 'n', 'out' (from the tile's centre towards the wall), 'along', 'z' (origin over the floor),
    'turn' (quarter turns past the side's own yaw), 'turn_share'}], most used first. Only props the game
    stands against a walled side (six times in ten at least), seen four times at least, near the wall."""
    s = ready(db)
    kp = kits.kit_pieces(db, style)
    if not s or not kp:
        return []
    T = kp['tile']
    out = []
    for low, p in s.get('props', {}).get(family(style), {}).items():
        if p['walled'] < 0.6 or p['n'] < 4 or p['out'] < T * 0.3 or p['along'] > T * 0.2:
            continue
        ri = db.resolve_id(low)
        if ri is None:
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or min(b[3] - b[0], b[4] - b[1]) > T * 0.3:
            continue                          # (a bay or a wall section, not a prop hung on a wall)
        out.append(dict(p, id=db.recs[ri][1], b=b))
    return sorted(out, key=lambda p: -p['n'])


def window_walls(db, style):
    """Window pieces that are wall sections (a tile wide, thin, a storey tall: Indoril's Room_Window,
    Gold Coast's WallWindow), to stand in for a loose wall on an outside side: [{'id', 'ri', 'n', 'thick',
    'thin_x', 'zmin', 'width'}], most used first."""
    s = ready(db)
    kp = kits.kit_pieces(db, style)
    if not s or not kp:
        return []
    T, H = kp['tile'], kp['height']
    fam = family(style)
    seen = {}
    for low, p in s.get('props', {}).get(fam, {}).items():
        seen[low] = p['n']
    for w in kp['walls']:
        if is_window(w['id'].lower()):
            seen.setdefault(w['id'].lower(), w['uses'])
    out = []
    for low, n in seen.items():
        ri = db.resolve_id(low)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        thin, long_ = min(w, d), max(w, d)
        if not (T * 0.8 <= long_ <= T * 1.15 and thin <= T * 0.35 and H * 0.6 <= h <= H * 1.2):
            continue
        out.append({'id': db.recs[ri][1], 'ri': ri, 'n': n, 'thick': thin, 'thin_x': w < d, 'zmin': b[2], 'width': long_})
    return sorted(out, key=lambda x: -x['n'])


def columns(db, style):
    """Where the game stands columns free in its big rooms of this style's family (at least half of them):
    (piece id, 'corner' | 'centre' of the tile grid, columns per 9 tiles), else None."""
    d = _fam(db, style)
    kp = kits.kit_pieces(db, style)
    if not d or not kp or (d['columns'].get('big_rooms') or 0) < COLUMN_MIN_SHARE:
        return None
    T = kp['tile']
    at = d['columns'].get('at', {})
    where = 'centre' if at.get('centre', 0) > at.get('corner', 0) else 'corner'
    fam = family(style)
    # (the family's own pillar before another set's, when the game uses both: the Common wood pillar
    # before Tamriel Data's Morrowind-set one)
    for low, _n in sorted(d['columns']['ids'].items(), key=lambda kv: (not kv[0].startswith(fam + '_'), -kv[1])):
        ri = db.resolve_id(low)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        w, dd = b[3] - b[0], b[4] - b[1]
        # a free-standing column: a square footprint at most half a tile across (not a wall with a
        # column on it, not a block); the builder stands it by its body, wherever its origin is
        if max(w, dd) <= T * 0.55 and abs(w - dd) < T * 0.15:
            return db.recs[ri][1], where, d['columns']['per_9_tiles']
    return None
