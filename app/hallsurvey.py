"""How the game's own places dress their halls: the kits' hall pieces (a Hlaalu hall's straight run, its
corners, its three- and four-way joins, its ends; Velothi, Imperial, Gold Coast, Common, Telvanni, Indoril
and Mournhold hall pieces; Redoran's ready-made halls; the Dwemer corridors; the Nord barrows' halls) and the
one-tile-wide corridors the room pieces make. For every such hall tile in the game-made interiors: what stands
in it (banners and tapestries, sconces and lanterns, benches, chests, urns and planters, statues, shrines,
rugs and runners, tables with a lamp, weapon racks, the stores), how often (per hall tile, and the share of
halls that have one), where across the hall (against a side wall, against the wall at a hall's end, out in
the walking line), how far apart along the hall (nearest neighbour), how close to a doorway, whether in pairs
across the hall, and what keeps the walking line clear (the free half-width from the hall's middle line to
the nearest thing). Halls are grouped into runs (hall tiles that touch); a run's set of things is its
arrangement, counted per culture. Kept in the cache folder once done (taste.cache_file, by load order);
ready() runs it in the background the first time. Read by furnish.hall_round; the write-up is
packaging/nexus/hallways-survey.md."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import kits
import mapdata

LIMIT = 900                 # places read (the ones with a hall piece or a corridor)
VERSION = 1
HALL_ID = re.compile(r'hall|corr|passage')
NOT_HALL_ID = re.compile(r'wall|ceiling|pillar|pllr|rail|jamb|plug|shaft|bridge|lvldown|hallt_|council|temple_hall|_exp$|_bk$|'
                         r'tunnel|middle|guildhall|halls_|hallmiddle|stair|ramp|clrhall')
STAIR_ID = re.compile(r'stair|ramp')
# whose hall a piece is, by the start of its id (the game's own kits and Tamriel Data's sets)
CULTURES = (('in_hlaalu', 'Hlaalu'), ('t_de_sethla', 'Hlaalu'), ('in_redoran', 'Redoran'), ('in_r_', 'Redoran'), ('t_de_setred', 'Redoran'),
            ('in_velothi', 'Velothi'), ('in_v_', 'Velothi'), ('t_de_setveloth', 'Velothi'), ('in_impsmall', 'Imperial'),
            ('in_imp', 'Imperial'), ('t_imp_setgc', 'Gold Coast'), ('t_imp_legion', 'Legion'), ('t_imp_set', 'Imperial'),
            ('in_c_', 'Common'), ('t_com_set', 'Common'), ('in_t_', 'Telvanni'), ('t_de_settel', 'Telvanni'), ('in_mh', 'Mournhold'),
            ('t_de_setind', 'Indoril'), ('t_de_setom', 'Indoril'), ('in_stronghold', 'Stronghold'), ('in_dwrv', 'Dwemer'),
            ('in_dwe', 'Dwemer'), ('t_dwe_', 'Dwemer'), ('in_nord', 'Nord'), ('t_nor_', 'Nord'), ('t_sky_', 'Nord'))
SMALL_TYPES = ('MISC', 'INGR', 'ALCH', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'APPA', 'PROB', 'REPA', 'LOCK')
LIGHT_KIND = (('sconce', re.compile(r'sconce')), ('candle', re.compile(r'candle')), ('lantern', re.compile(r'lantern')),
              ('brazier', re.compile(r'brazier|fire')), ('torch', re.compile(r'torch')), ('lamp', re.compile(r'lamp')),
              ('chandelier', re.compile(r'chandelier')))
STATUE = re.compile(r'statue|bust|idol|figurine|sculpt|_stat_|sotha_sil_|almalexia_|vivec_|dwrv_.*(centurion|construct)_.*static')
BANNER = re.compile(r'banner|flag|pennant')
TAPESTRY = re.compile(r'tapestr')
PAINTING = re.compile(r'painting|picture|portrait')
RACK = re.compile(r'weaponrack|weapon_rack|armorrack|armourrack|armor_rack|armour_rack')
PLANT = re.compile(r'flora_|_plant|fern|shrub|bush|vine|flower|ivy')
DEBRIS = re.compile(r'debris|rubble|_rock|rocks|_bone|bones|skeleton|cobweb|web_|blood|dirt|pile|scrap|_junk|broken')
FLOOR_KINDS = ('bench', 'chair', 'chest', 'crate', 'barrel', 'sack', 'basket', 'urn', 'planter', 'plant', 'statue', 'shrine', 'rug',
               'table', 'rack', 'shelf', 'bookshelf', 'cupboard', 'screen', 'bed', 'light', 'debris', 'other')
DUNGEONS = ('Dwemer', 'Nord', 'Stronghold')     # (ruins, barrows and strongholds: not in the whole game's figures for houses)
WALL_REACH = 96             # a thing's middle this close to a wall's face stands against it
_cache = {}
_thread = {}


def culture_of(rid):
    low = rid.lower()
    for p, c in CULTURES:
        if low.startswith(p):
            return c
    return None


def kind_of(db, r):
    """What a thing in a hall is, in this survey's words: 'banner', 'tapestry', 'painting', 'light:<kind>',
    'statue', 'rack', a furniture family (furnish.FAMILIES by id and name: 'bench', 'chest', 'urn', 'rug'...),
    'plant', 'debris', 'small' (a thing that can be picked up), or 'other'."""
    import roomkindsurvey
    low = r['id'].lower()
    name = (r.get('name') or '').lower()
    if 'marker' in low or r['type'] in ('NPC_', 'CREA', 'LEVC', 'LEVI', 'DOOR', 'SNDG', 'SOUN'):
        return None
    if r['type'] == 'LIGH':
        for k, rx in LIGHT_KIND:
            if rx.search(low):
                return 'light:' + k
        return 'light:other'
    if TAPESTRY.search(low):
        return 'tapestry'
    if BANNER.search(low):
        return 'banner'
    if PAINTING.search(low):
        return 'painting'
    if RACK.search(low):
        return 'rack'
    if r['type'] in SMALL_TYPES:
        return 'small'
    if STATUE.search(low) or (r['type'] in ('STAT', 'ACTI') and 'statue' in name):
        return 'statue'
    if low.startswith('flora_') or (PLANT.search(low) and not re.search(r'planter|pot', low)):
        return 'plant'
    if re.search(r'rug|carpet', low) and r['type'] == 'STAT':
        return 'rug'                     # (Tamriel Data's RugSmall and RugLong: one word to the rug family)
    if re.search(r'_vs\d|vase', low):
        return 'urn'
    f = roomkindsurvey.family_of(r)
    if f in ('dish', 'bottle', 'book', 'food', 'candle'):
        return 'small'
    if f:
        return f
    if PLANT.search(low):
        return 'plant'
    if DEBRIS.search(low):
        return 'debris'
    return 'other'


def _disk(db, limit):
    import taste
    return taste.cache_file('hallsurvey_%s_%d_v%d' % (taste.sig(db), limit, VERSION))


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    import taste
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db, limit)):
            return survey(db, limit)
    except Exception:
        return None
    t = _thread.get('t')
    if t is None or not t.is_alive():
        try:
            import background
            _thread['t'] = background.start('how the game dresses its halls', lambda: survey(db, limit),
                                            task=('hallsurvey', 'survey', [limit]))
        except Exception:
            t = threading.Thread(target=lambda: survey(db, limit), daemon=True)
            _thread['t'] = t
            t.start()
    return taste.stale(_cache, key, db.recs, _disk(db, limit))


def survey(db, limit=LIMIT):
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
    out = _survey(db, limit)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def _box(r):
    """A placed thing's box in the world (turned about Z), (x0, y0, z0, x1, y1, z1), or None."""
    b = r.get('b')
    if not b:
        return None
    s = r.get('s') or 1.0
    c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
    xs, ys = [], []
    for lx in (b[0], b[3]):
        for ly in (b[1], b[4]):
            xs.append(r['p'][0] + (lx * c + ly * sn) * s)
            ys.append(r['p'][1] + (-lx * sn + ly * c) * s)
    return (min(xs), min(ys), r['p'][2] + b[2] * s, max(xs), max(ys), r['p'][2] + b[5] * s)


def _pattern(db, r):
    """A kit piece's sides as it stands ({'N': 'wall'|'open'|'door', ..., 'offset': {...}}), or None."""
    prefix = kits.kit_prefix(r['id'])
    if not prefix or prefix not in kits.kits(db):
        return None
    kp = kits.kit_pieces(db, prefix)
    piece = next((p for p in (kp or {}).get('pieces', []) if p['id'].lower() == r['id'].lower()), None)
    if not piece:
        return None
    q = int(round(r['p'][5] / (math.pi / 2))) % 4
    return kits.rotate(piece['pattern'], q)


def shape_of(pat, box):
    """A hall tile's shape: 'straight' (walls on two facing sides), 'end' (three walls), 'corner' (two
    walls that meet), 'junction' (one wall or none), and the axis the walking line runs along ('x', 'y'
    or None)."""
    if pat:
        w = [s for s in 'NESW' if pat.get(s) == 'wall']
        if len(w) >= 3:
            op = next((s for s in 'NESW' if s not in w), None)
            return 'end', ('y' if op in ('N', 'S') else 'x') if op else None
        if sorted(w) == ['N', 'S']:
            return 'straight', 'x'
        if sorted(w) == ['E', 'W']:
            return 'straight', 'y'
        if len(w) == 2:
            return 'corner', None
        return 'junction', None
    wx, wy = box[3] - box[0], box[4] - box[1]
    if min(wx, wy) <= 160:
        # (a half-length piece, a Hlaalu hall_128, a Velothi halfhall: as wide as a hall, half as long; the
        # walking line runs along its short side)
        return 'straight', ('x' if wx < wy else 'y')
    if wx >= wy * 1.25:
        return 'straight', 'x'
    if wy >= wx * 1.25:
        return 'straight', 'y'
    return 'junction', None


def _units(db, ck, m):
    """The hall tiles of a place: [{x0, y0, x1, y1, floor, shape, axis, pat, culture, id, room}]."""
    import furnish
    out = []
    seen = set()
    for r in m['refs']:
        low = r['id'].lower()
        if not (r.get('arch') and r.get('b')) or not HALL_ID.search(low) or NOT_HALL_ID.search(low):
            continue
        c = culture_of(low)
        if not c:
            continue
        b = _box(r)
        w, h = b[3] - b[0], b[4] - b[1]
        if min(w, h) < 100 or min(w, h) > 600 or max(w, h) > 800:
            continue                     # (a sliver of a piece, or a great hall: not a passage)
        pat = _pattern(db, r)
        shape, axis = shape_of(pat, b)
        key = (round(r['p'][0] / 32), round(r['p'][1] / 32), round(b[2] / 32))
        if key in seen:
            continue
        seen.add(key)
        out.append({'x0': b[0], 'y0': b[1], 'x1': b[3], 'y1': b[4], 'floor': b[2], 'shape': shape, 'axis': axis, 'pat': pat,
                    'culture': c, 'id': low, 'room': None})
    # the corridors the room pieces make (a room one tile wide and three or more long), where no hall
    # piece already stands
    try:
        info = furnish.rooms(db, ck, trace=False)
    except Exception:
        info = None
    if info and info.get('tile') == 256:
        T = 256
        for rm in info['rooms']:
            if not (min(rm['w'], rm['h']) == 1 and max(rm['w'], rm['h']) >= 3):
                continue
            for t in rm['_tiles']:
                key = (round(t['x'] / 32), round(t['y'] / 32), round(t['floor'] / 32))
                if key in seen:
                    continue
                seen.add(key)
                ids = [r['id'].lower() for r in m['refs'] if r.get('arch') and abs(r['p'][0] - t['x']) < 8 and abs(r['p'][1] - t['y']) < 8]
                c = next((culture_of(i) for i in ids if culture_of(i)), None)
                if not c:
                    continue
                box = (t['x'] - T / 2, t['y'] - T / 2, t['floor'], t['x'] + T / 2, t['y'] + T / 2)
                shape, axis = shape_of(t['pat'], box)
                out.append({'x0': box[0], 'y0': box[1], 'x1': box[3], 'y1': box[4], 'floor': t['floor'], 'shape': shape, 'axis': axis,
                            'pat': t['pat'], 'culture': c, 'id': ids[0] if ids else '', 'room': rm['id']})
    return open_floor_out(out)


def open_floor_out(units):
    """The hall tiles that are passages, not the floor of a room: a tile that is one of four making a
    square (the Hlaalu kit builds its small rooms of hall corners and three-ways) is a room's."""
    grid = {}
    for i, u in enumerate(units):
        w, h = u['x1'] - u['x0'], u['y1'] - u['y0']
        if 200 <= w <= 300 and 200 <= h <= 300:
            grid[(round((u['x0'] + u['x1']) / 512.0), round((u['y0'] + u['y1']) / 512.0), round(u['floor'] / 64.0))] = i
    room_like = set()
    for (gx, gy, gz), i in grid.items():
        for dx in (-1, 1):
            for dy in (-1, 1):
                block = [(gx + dx, gy, gz), (gx, gy + dy, gz), (gx + dx, gy + dy, gz)]
                if all(b in grid for b in block):
                    room_like.add(i)
                    room_like.update(grid[b] for b in block)
    return [u for i, u in enumerate(units) if i not in room_like]


def _runs(units):
    """Hall tiles that touch, on one floor: lists of unit indexes."""
    left = list(range(len(units)))
    runs = []
    while left:
        grp = [left.pop(0)]
        i = 0
        while i < len(grp):
            a = units[grp[i]]
            for j in list(left):
                b = units[j]
                if abs(a['floor'] - b['floor']) < 64 and a['x0'] - 24 <= b['x1'] and b['x0'] - 24 <= a['x1'] \
                        and a['y0'] - 24 <= b['y1'] and b['y0'] - 24 <= a['y1']:
                    grp.append(j)
                    left.remove(j)
            i += 1
        runs.append(grp)
    return runs


def _wall_faces(u):
    """The unit's walls as (side, face coordinate): the inside face, from the kit's pattern offset."""
    faces = []
    pat = u['pat']
    cx, cy = (u['x0'] + u['x1']) / 2, (u['y0'] + u['y1']) / 2
    if pat:
        for s in 'NESW':
            if pat.get(s) != 'wall':
                continue
            off = (pat.get('offset') or {}).get(s, 112)
            faces.append((s, cy + off if s == 'N' else cy - off if s == 'S' else cx + off if s == 'E' else cx - off))
    elif u['axis'] == 'x':
        half = min(u['y1'] - u['y0'], 256) / 2 - 12
        faces = [('N', cy + half), ('S', cy - half)]
    elif u['axis'] == 'y':
        half = min(u['x1'] - u['x0'], 256) / 2 - 12
        faces = [('E', cx + half), ('W', cx - half)]
    return faces


def walk_lines(u):
    """The walking line through a hall tile: segments from the middle of each side one walks in or out by
    (open or a doorway) to the tile's middle; along the axis for a ready-made piece; [] when none is known."""
    cx, cy = (u['x0'] + u['x1']) / 2, (u['y0'] + u['y1']) / 2
    pat = u['pat']
    ends = []
    if pat:
        for s in 'NESW':
            if pat.get(s) in ('open', 'door'):
                ends.append((cx, u['y1']) if s == 'N' else (cx, u['y0']) if s == 'S' else (u['x1'], cy) if s == 'E' else (u['x0'], cy))
    elif u['axis'] == 'x':
        ends = [(u['x0'], cy), (u['x1'], cy)]
    elif u['axis'] == 'y':
        ends = [(cx, u['y0']), (cx, u['y1'])]
    return [((ex, ey), (cx, cy)) for ex, ey in ends]


def clear_of(box, lines, centre):
    """How far a footprint (x0, y0, ..., x1, y1) keeps from the walking line: the nearest distance from
    its edge to any segment of it (to the tile's middle when there are none)."""
    def d_pt(px, py):
        return math.hypot(max(box[0] - px, 0, px - box[3]), max(box[1] - py, 0, py - box[4]))
    if not lines:
        return d_pt(*centre)
    best = None
    for (ax, ay), (bx, by) in lines:
        n = max(1, int(math.hypot(bx - ax, by - ay) / 8))
        for i in range(n + 1):
            d = d_pt(ax + (bx - ax) * i / n, ay + (by - ay) * i / n)
            if best is None or d < best:
                best = d
    return best


BODY = 20                    # half the width one walks by (the player's capsule and a hand to spare)
STEP_G = 16                  # the grid a tile is walked on


def blocked(tile, T, boxes):
    """Whether one can still walk through a hall tile: from every way into it (an open side or a doorway
    in its pattern) to every other, round what stands on its floor (boxes: (x0, y0, x1, y1) footprints,
    widened by BODY), on a STEP_G grid over the tile and a little past its open sides. Returns the ways
    that can't be reached from the first ([] when all can, or the tile has fewer than two)."""
    pat = tile['pat']
    ways = [s for s in 'NESW' if pat.get(s) in ('open', 'door')]
    if len(ways) < 2:
        return []
    x0, y0 = tile['x'] - T / 2, tile['y'] - T / 2
    n = int(T // STEP_G)
    walls = {s: (pat.get('offset') or {}).get(s, T / 2 - 16) for s in 'NESW' if pat.get(s) == 'wall'}

    def free(i, j):
        px, py = x0 + (i + 0.5) * STEP_G, y0 + (j + 0.5) * STEP_G
        dx, dy = px - tile['x'], py - tile['y']
        if ('E' in walls and dx > walls['E'] - BODY) or ('W' in walls and -dx > walls['W'] - BODY) \
                or ('N' in walls and dy > walls['N'] - BODY) or ('S' in walls and -dy > walls['S'] - BODY):
            return False
        for b in boxes:
            if b[0] - BODY <= px <= b[2] + BODY and b[1] - BODY <= py <= b[3] + BODY:
                return False
        return True
    grid = [[free(i, j) for j in range(n)] for i in range(n)]

    def edge_cells(s):
        if s == 'N':
            return [(i, n - 1) for i in range(n)]
        if s == 'S':
            return [(i, 0) for i in range(n)]
        if s == 'E':
            return [(n - 1, j) for j in range(n)]
        return [(0, j) for j in range(n)]
    start = [c for c in edge_cells(ways[0]) if grid[c[0]][c[1]]]
    seen = set(start)
    todo = list(start)
    while todo:
        i, j = todo.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < n and 0 <= b < n and (a, b) not in seen and grid[a][b]:
                seen.add((a, b))
                todo.append((a, b))
    if not start:
        return ways[1:] if any(any(grid[c[0]][c[1]] for c in edge_cells(s)) for s in ways[1:]) else []
    return [s for s in ways[1:] if not any(c in seen for c in edge_cells(s)) and any(grid[c[0]][c[1]] for c in edge_cells(s))]


def obstacles(things, fl):
    """The floor footprints one walks round: furniture on this floor standing above ankle height (not a rug,
    not a thing that can be picked up, not a light hung up), as (x0, y0, x1, y1, ref)."""
    out = []
    for x in things:
        bx = x.get('_box') or _box(x)
        if not bx or x['type'] not in ('STAT', 'CONT', 'ACTI', 'LIGH'):
            continue
        low = x['id'].lower()
        # (a gallery's railing is the building's edge, not a thing in the way: Anvil's Thimistrel Manor)
        if re.search(r'rug|carpet|mat_|_mat|marker|web|blood|scum|flora_.*(grass|moss)|rail|balust', low):
            continue
        if not (fl - 30 <= bx[2] <= fl + 40) or bx[5] < fl + 30:
            continue
        out.append((bx[0], bx[1], bx[3], bx[4], x))
    return out


def _survey(db, limit):
    import taste
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    rows = []                     # one per hall run
    things = []                   # one per thing in a hall tile
    seen = 0
    for ck in taste.spread(cells, len(cells)):
        if seen >= limit:
            break
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        if not m.get('interior') or not m.get('exists', True):
            continue
        if not any(r.get('arch') and HALL_ID.search(r['id'].lower()) for r in m['refs']) \
                and not any(r.get('arch') and kits.kit_prefix(r['id']) for r in m['refs']):
            continue
        units = _units(db, ck, m)
        if not units:
            continue
        seen += 1
        name = ((mapdata.cell_info(db, ck) or {}).get('name') or ck)
        doors = [r for r in m['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower() or 'doorway' in r['id'].lower()]
        refs = [r for r in m['refs'] if r.get('b') and (not r.get('arch') or re.search(r'rug|carpet|planter|statue|banner|tapestr|flora|plant', r['id'].lower()))]
        mine = defaultdict(list)          # unit index -> [(ref, kind, box)]
        for r in refs:
            k = kind_of(db, r)
            if not k:
                continue
            bx = _box(r)
            if not bx:
                continue
            for i, u in enumerate(units):
                if u['x0'] <= r['p'][0] <= u['x1'] and u['y0'] <= r['p'][1] <= u['y1'] and u['floor'] - 30 <= bx[2] <= u['floor'] + 260:
                    mine[i].append((r, k, bx))
                    break
        for grp in _runs(units):
            culture = Counter(units[i]['culture'] for i in grp).most_common(1)[0][0]
            n_tiles = sum((units[i]['x1'] - units[i]['x0']) * (units[i]['y1'] - units[i]['y0']) for i in grp) / (256.0 * 256.0)
            kinds = Counter()
            run_things = []
            for i in grp:
                u = units[i]
                cx, cy = (u['x0'] + u['x1']) / 2, (u['y0'] + u['y1']) / 2
                faces = _wall_faces(u)
                lines = walk_lines(u)
                for r, k, bx in mine.get(i, []):
                    up = bx[2] - u['floor']
                    tall = bx[5] - bx[2]
                    x, y = r['p'][0], r['p'][1]
                    # against which wall (the nearest face within reach), or out in the hall
                    best = None
                    for s, f in faces:
                        d = abs((y if s in 'NS' else x) - f)
                        if best is None or d < best[1]:
                            best = (s, d)
                    at_wall = best is not None and best[1] <= WALL_REACH
                    side = None
                    if at_wall and u['axis']:
                        side = 'side' if (u['axis'] == 'x') == (best[0] in 'NS') else 'end'
                    elif at_wall:
                        side = 'wall'
                    # the walking line (from each way in or out to the tile's middle) to the nearest edge
                    # of the thing's footprint
                    clear = clear_of(bx, lines, (cx, cy))
                    along = x if u['axis'] == 'x' else y if u['axis'] == 'y' else None
                    door_d = min((math.hypot(d['p'][0] - x, d['p'][1] - y) for d in doors if abs(d['p'][2] - u['floor']) < 200), default=None)
                    if k in ('banner', 'tapestry', 'painting'):
                        place = 'wall' if at_wall else 'hanging'
                    elif k.startswith('light:'):
                        place = 'floor' if up < 20 else 'wall' if at_wall and up >= 100 else 'furniture' if up < 120 else 'hanging'
                    else:
                        place = 'floor' if up < 30 else 'raised'
                    floor_thing = place == 'floor' and k not in ('small',) and not k.startswith('light:') or (k.startswith('light:') and place == 'floor')
                    row = {'cell': ck, 'unit': i, 'shape': u['shape'], 'culture': culture, 'kind': k, 'id': r['id'].lower(), 'place': place,
                           'side': side, 'wall_d': round(best[1]) if best else None, 'clear': round(clear), 'door_d': round(door_d) if door_d is not None else None,
                           'up': round(up), 'tall': round(tall), 'w': round(max(bx[3] - bx[0], bx[4] - bx[1])), 'depth': round(min(bx[3] - bx[0], bx[4] - bx[1])),
                           'x': round(x), 'y': round(y), 'axis': u['axis'], 'along': round(along) if along is not None else None, 'floor_thing': floor_thing}
                    things.append(row)
                    run_things.append(row)
                    if floor_thing or k in ('banner', 'tapestry', 'painting') or k.startswith('light:'):
                        kinds[k] += 1
            # nearest-neighbour spacing of the floor things along the run, and pairs across it
            fl_ = [t for t in run_things if t['floor_thing'] and t['kind'] not in ('rug', 'debris', 'other')]
            nn, nn_same, pairs = [], [], 0
            for a in fl_:
                ds = [math.hypot(a['x'] - b['x'], a['y'] - b['y']) for b in fl_ if b is not a]
                if ds:
                    nn.append(round(min(ds)))
                ds2 = [math.hypot(a['x'] - b['x'], a['y'] - b['y']) for b in fl_ if b is not a and b['kind'] == a['kind']]
                if ds2:
                    nn_same.append(round(min(ds2)))
                for b in fl_:
                    if b is a or b['kind'] != a['kind'] or a['axis'] is None or a['axis'] != b['axis'] or a['side'] != 'side' or b['side'] != 'side':
                        continue
                    if abs(a['along'] - b['along']) <= 64 and math.hypot(a['x'] - b['x'], a['y'] - b['y']) > 120:
                        pairs += 1
            shapes = Counter(units[i]['shape'] for i in grp)
            rows.append({'cell': ck, 'name': name, 'culture': culture, 'units': len(grp), 'tiles': round(n_tiles, 2), 'shapes': dict(shapes),
                         'kinds': dict(kinds), 'floor_n': len(fl_), 'nn': nn, 'nn_same': nn_same, 'pairs': pairs // 2,
                         'clear': min((t['clear'] for t in fl_), default=None),
                         'ids': sorted({t['id'] for t in run_things if t['floor_thing'] or t['kind'] in ('banner', 'tapestry')})[:12]})
    _cache['rows'] = (rows, things)          # (for the write-up and spot checks; not kept on disk)
    return _fold(seen, rows, things)


def _q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))] if v else None


def arrangement(kinds):
    """A run's arrangement: its floor kinds (and hung cloths), the stores and debris left out, as a sorted
    signature 'bench+chest+urn'."""
    keep = [k for k in kinds if k in ('bench', 'chair', 'chest', 'urn', 'planter', 'plant', 'statue', 'shrine', 'rug', 'table', 'rack',
                                       'shelf', 'bookshelf', 'cupboard', 'screen', 'banner', 'tapestry', 'basket', 'crate', 'barrel', 'sack')]
    stores = sum(1 for k in keep if k in ('crate', 'barrel', 'sack', 'basket'))
    keep = sorted({k if k not in ('crate', 'barrel', 'sack', 'basket') else 'stores' for k in keep})
    return '+'.join(keep) if keep else ('bare' if not stores else 'stores')


def _fold(seen, rows, things):
    out = {'places': seen, 'runs': len(rows), 'cultures': {}}
    by_c = defaultdict(list)
    for r in rows:
        by_c[r['culture']].append(r)
        if r['culture'] not in DUNGEONS:
            by_c['*'].append(r)
    th_c = defaultdict(list)
    for t in things:
        th_c[t['culture']].append(t)
        if t['culture'] not in DUNGEONS:
            th_c['*'].append(t)
    for c, rs in by_c.items():
        tiles = sum(r['tiles'] for r in rs) or 1.0
        ts = th_c.get(c, [])
        kinds = {}
        for k in sorted({t['kind'] for t in ts}):
            kt = [t for t in ts if t['kind'] == k]
            runs_with = sum(1 for r in rs if any(kk == k or kk == k.split(':')[0] for kk in r['kinds']))
            kinds[k] = {'n': len(kt), 'per_tile': round(len(kt) / tiles, 3), 'runs_with': round(runs_with / float(len(rs)), 3),
                        'place': dict(Counter(t['place'] for t in kt)), 'side': dict(Counter(t['side'] or 'middle' for t in kt)),
                        'shape': dict(Counter(t['shape'] for t in kt)),
                        'clear_med': _q([t['clear'] for t in kt], 0.5), 'clear_p10': _q([t['clear'] for t in kt], 0.1),
                        'wall_d_med': _q([t['wall_d'] for t in kt if t['wall_d'] is not None], 0.5),
                        'door_d_p10': _q([t['door_d'] for t in kt if t['door_d'] is not None], 0.1),
                        'by_door': round(sum(1 for t in kt if t['door_d'] is not None and t['door_d'] < 160) / float(len(kt)), 3),
                        'up_med': _q([t['up'] for t in kt], 0.5), 'depth_med': _q([t['depth'] for t in kt], 0.5),
                        'ids': Counter(t['id'] for t in kt).most_common(10)}
        arr = Counter(arrangement(r['kinds']) for r in rs)
        ex = defaultdict(list)
        for r in rs:
            a = arrangement(r['kinds'])
            if len(ex[a]) < 4:
                ex[a].append(r['name'])
        fl_runs = [r for r in rs if r['floor_n']]
        out['cultures'][c] = {
            'runs': len(rs), 'tiles': round(tiles, 1), 'places': len({r['cell'] for r in rs}),
            'bare_share': round(sum(1 for r in rs if not r['floor_n']) / float(len(rs)), 3),
            'lit_share': round(sum(1 for r in rs if any(k.startswith('light') or k in ('sconce', 'lantern', 'candle', 'lamp', 'torch', 'brazier', 'chandelier') for k in r['kinds'])) / float(len(rs)), 3),
            'floor_per_tile': round(sum(r['floor_n'] for r in rs) / tiles, 3),
            'run_tiles_med': _q([r['tiles'] for r in rs], 0.5),
            'nn_med': _q([d for r in rs for d in r['nn']], 0.5), 'nn_p10': _q([d for r in rs for d in r['nn']], 0.1),
            'nn_same_med': _q([d for r in rs for d in r['nn_same']], 0.5),
            'pairs': sum(r['pairs'] for r in rs), 'pair_runs': round(sum(1 for r in fl_runs if r['pairs']) / float(len(fl_runs) or 1), 3),
            'clear_p10': _q([r['clear'] for r in fl_runs if r['clear'] is not None], 0.1),
            'clear_med': _q([r['clear'] for r in fl_runs if r['clear'] is not None], 0.5),
            'kinds': kinds, 'arrangements': arr.most_common(16), 'examples': {a: ex[a] for a, n in arr.most_common(16)}}
    return out


def rule(db, culture):
    """The hall rule for a culture (a key of the survey's 'cultures', or a furnish style label), with the
    whole game's figures where a culture has too few runs: None until the survey is ready."""
    s = ready(db)
    if not s:
        return None
    cs = s['cultures']
    c = cs.get(culture)
    if not c or c['runs'] < 12:
        return cs.get('*')
    return c


def report(db, limit=LIMIT, cultures=('*', 'Hlaalu', 'Redoran', 'Velothi', 'Imperial', 'Gold Coast', 'Common', 'Telvanni', 'Indoril',
                                       'Mournhold', 'Dwemer', 'Nord', 'Stronghold', 'Legion')):
    s = survey(db, limit)
    print('hall survey: %d places, %d runs' % (s['places'], s['runs']))
    for c in cultures:
        x = s['cultures'].get(c)
        if not x:
            print('\n== %s: none' % c)
            continue
        print('\n== %s: %d runs (%d places, %.0f tiles); bare %.0f%%, lit %.0f%%; floor things %.2f per tile; run median %.1f tiles'
              % (c, x['runs'], x['places'], x['tiles'], 100 * x['bare_share'], 100 * x['lit_share'], x['floor_per_tile'], x['run_tiles_med'] or 0))
        print('   spacing: nearest %s (p10 %s), same kind %s; pairs across %d (%.0f%% of furnished runs); walking line clear p10 %s, median %s'
              % (x['nn_med'], x['nn_p10'], x['nn_same_med'], x['pairs'], 100 * x['pair_runs'], x['clear_p10'], x['clear_med']))
        for k, v in sorted(x['kinds'].items(), key=lambda kv: -kv[1]['n']):
            if v['n'] < 2:
                continue
            print('   %-16s n %4d  /tile %.3f  runs %4.0f%%  place %s  side %s  clear %s/%s  wall %s  door p10 %s (by door %.0f%%)  depth %s'
                  % (k, v['n'], v['per_tile'], 100 * v['runs_with'], v['place'], v['side'], v['clear_p10'], v['clear_med'], v['wall_d_med'],
                     v['door_d_p10'], 100 * v['by_door'], v['depth_med']))
            print('       ' + ', '.join('%s %d' % (i, n) for i, n in v['ids'][:6]))
        print('   arrangements: ' + '; '.join('%s %d' % (a, n) for a, n in x['arrangements']))
