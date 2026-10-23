"""Where and how the game grows things indoors: every planter in its interiors (the convert gate's places
and every place that stands one), read as the game's own planting manual.

For each planter MODEL: its size (width, depth, height), where it stands (on the floor, on a table or a
shelf, hung from the ceiling) and so its class (a floor bed 150 wide or more, a big urn, a mid pot, a
tabletop pot, a hanging planter), what grows in it and how densely, the whole gardens the game lays in it
(kept as examples to copy), and which plants fit it (plant width and height against the pot's).
For each ROOM KIND and STYLE: how many floor planters a room holds (per nine tiles, and the count by room
size), where they stand (a corner, flanking a door, under a window, at a post's foot, at a stair's foot,
by a seat, a plain wall, out in the open), how they group (singles, pairs, rows; the pair of matching urns
either side of a door, the row under a window), what the tabletop pots stand on, and how high the hanging
ones hang.

Auto-furnish's planting path draws its rates, spots, models and gardens from here (furnish.py: plant_room);
"Planters half empty" in Check this place learns each model's usual count here (placecheck.py).

The game's big planters are "architecture" to the map reader (any static over 200 x 200), so this survey
admits them by name, as redoransurvey does. Kept in the cache folder once done (taste.cache_file, by load
order); ready() runs it in the background the first time."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey
import arrangesurvey
import fixit
import shelfsurvey

V = 'v3'                # (v3: size classes, stands, spots, groups, fit, surfaces, hanging heights; every planter cell's rooms)
LIMIT = 1200            # places whose rooms are read (the models are read from every place)
EXAMPLES = 30           # dressings kept per planter model
PLANTER = re.compile(r'planter|flowerbox|plantpot|plant_pot|gardenbed|garden_bed')
PLANT = re.compile(r'flora_|_plant|fern|shrub|bush|tree|vine|mushroom|shroom|flower|ivy|grass|moss|kanet|anther|lichen|kelp|reed|weed|rock_|_rock|stone_0')
WINDOW = re.compile(r'win(dow)?(_|$|\d)')
COLUMN = re.compile(r'pillar|column|post|colum')
BEAM = re.compile(r'beam|rafter|joist')
BED_W = 150             # a planter this wide is a bed, not a pot
URN_W = 90              # a floor planter this wide is a big urn; narrower, a mid pot
GROUP_D = 200           # planters this close stand together (a pair, a row)
SURFACE_KINDS = ('table', 'shelf', 'bookshelf', 'counter', 'cupboard', 'chest', 'crate', 'barrel', 'bench', 'urn', 'planter')
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('gardensurvey_%s_%d_%s' % (taste.sig(db), LIMIT, V))


def ready(db):
    import taste
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('the game\'s gardens', lambda: survey(db), task=('gardensurvey', 'survey', []))
    return taste.stale(_cache, key, db.recs, _disk(db))


def survey(db):
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def is_planter(r):
    low = r['id'].lower()
    return r['type'] in ('STAT', 'ACTI', 'CONT') and bool(PLANTER.search(low)) and 'marker' not in low


def is_plant(r):
    low = r['id'].lower()
    if r['type'] not in ('STAT', 'ACTI', 'CONT') or 'marker' in low or PLANTER.search(low):
        return False
    if low.startswith(('in_', 'ex_')) or kits.kit_prefix(low):
        return False
    return bool(PLANT.search(low))


def _planter_cells(db):
    """Every game-made interior that stands a planter, by the records' use lists (no walk of all places),
    and the convert gate's places when the gate has run (its cache file; no gate run is started here)."""
    keys = set()
    for ri, r in enumerate(db.recs):
        if r[0] not in ('STAT', 'ACTI', 'CONT') or not PLANTER.search(r[1].lower()):
            continue
        for ci in db.used_in.get(r[1].lower(), ()):
            if db.recs[ci][0] == 'CELL':
                keys.add(db.recs[ci][7])
    try:
        import planfrom
        gp = planfrom._gate_disk(db)
        if os.path.isfile(gp):
            with open(gp, encoding='utf-8') as f:
                keys |= set(json.load(f).keys())
    except Exception:
        pass
    mine = set((db.project.cells or {}).keys()) if getattr(db, 'project', None) else set()
    out = []
    for k in keys:
        if not k or k.startswith('#') or k in mine or not kits.game_made(db, k):
            continue
        ci = mapdata.cell_info(db, k)
        if ci and ci.get('interior'):
            out.append(k)
    return sorted(out)


def _pcts(v):
    v = sorted(v)
    if not v:
        return None
    return [round(v[int(len(v) * q)] if int(len(v) * q) < len(v) else v[-1], 2) for q in (0.1, 0.25, 0.5, 0.75, 0.9)]


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _bucket(tiles9):
    return 'small' if tiles9 <= 6 else 'mid' if tiles9 <= 12 else 'large'


def _survey(db):
    import taste
    import catalogue
    cells = taste.order(_planter_cells(db))
    models = defaultdict(lambda: {'n': 0, 'with': 0, 'counts': [], 'kinds': Counter(), 'w': None, 'd': None, 'h': None, 'examples': [], 'styles': Counter(),
                                  'benches': 0, 'lights': 0, 'stands': Counter(), 'on': Counter(), 'spots': Counter(), 'fit_w': [], 'fit_h': []})
    kinds = defaultdict(lambda: {'rooms': 0, 'tiles': 0.0, 'beds': 0, 'pots': 0, 'rooms_with_bed': 0, 'spots': Counter(), 'island': 0, 'flora_groups': 0,
                                 'flora_near': 0, 'flora_sizes': [], 'flora_kinds': Counter(), 'flora_ids': Counter(), 'rocks': 0, 'bed_w': [],
                                 'floor': Counter(), 'rooms_with_floor': 0, 'per_room': defaultdict(Counter), 'cls_spots': defaultdict(Counter),
                                 'groups': Counter(), 'pair_door': 0, 'pairs': 0, 'pair_same': 0, 'rows': 0, 'row_window': 0, 'row_same': 0,
                                 'surface': 0, 'surfaces': Counter(), 'hung': 0, 'rooms_with_surface': 0, 'on_furniture': 0})
    styles = defaultdict(lambda: {'rooms': 0, 'tiles': 0.0, 'classes': Counter(), 'models': defaultdict(Counter), 'spots': defaultdict(Counter), 'groups': Counter(),
                                  'surface_models': Counter(), 'hanging_models': Counter(), 'rooms_with_floor': 0, 'scales': defaultdict(lambda: defaultdict(list))})
    style_beds = defaultdict(Counter)
    fit = {'w': [], 'h': [], 'rim': [], 'by_w': defaultdict(lambda: {'w': [], 'h': []})}
    hanging = {'height': [], 'beam': 0, 'n': 0, 'models': Counter(), 'under_ceiling': []}
    pairs = {'n': 0, 'same': 0, 'door': 0, 'spacing': [], 'examples': []}
    rows = {'n': 0, 'same': 0, 'window': 0, 'wall': 0, 'gap': [], 'len': Counter(), 'examples': []}
    seen = rooms_read = 0
    for ck in cells:
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        refs = [r for r in m['refs'] if r.get('b') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        planters = [r for r in refs if is_planter(r)]
        flora = [r for r in refs if is_plant(r)]
        if not planters:
            continue
        seen += 1
        for r in planters + flora:
            r['_box'] = fixit._world_box(r)
        arch = [r for r in m['refs'] if r.get('arch') and r.get('b') and (r['id'].lower().startswith(('in_', 'ex_')) or kits.kit_prefix(r['id']))]
        prefixes = Counter(kits.kit_prefix(a['id']) for a in arch if kits.kit_prefix(a['id']))
        prefix = prefixes.most_common(1)[0][0] if prefixes else ''
        label = catalogue.style_keys(db, {'refs': m['refs'], 'tile': 256})[1][-1] if arch else ''
        st_key = label or prefix or '?'
        benches = [r for r in refs if arrangesurvey.family(db, r['id'], r['type']) == 'bench']
        lights = [r for r in refs if r['type'] == 'LIGH']
        in_any = set()
        contents = {}
        for p in planters:
            b = p['_box']
            if not b:
                continue
            low = p['id'].lower()
            M = models[low]
            M['n'] += 1
            # (the model's own size, unturned: a square pot turned 45 degrees has a world box 1.4 times as
            # wide, and that made small pots "urns"; its size as placed is the model's times its scale)
            ob = mapdata.object_bounds(db, db.resolve_id(p['id'])) if db.resolve_id(p['id']) is not None else None
            if not ob:
                ob = b
            ps_ = p.get('s') or 1.0
            M['w'] = round(max(ob[3] - ob[0], ob[4] - ob[1]))
            M['d'] = round(min(ob[3] - ob[0], ob[4] - ob[1]))
            M['h'] = round(ob[5] - ob[2])
            M['styles'][st_key] += 1
            w = M['w'] * ps_
            p['_w'] = w
            cont = [o for o in flora if b[0] - 16 <= o['p'][0] <= b[3] + 16 and b[1] - 16 <= o['p'][1] <= b[4] + 16 and o['_box'] and b[2] - 30 <= o['_box'][2] <= b[5] + 160]
            contents[id(p)] = cont
            for o in cont:
                in_any.add(id(o))
                M['kinds'][re.sub(r'_\d+$', '', o['id'].lower())] += 1
                ob_ = mapdata.object_bounds(db, db.resolve_id(o['id'])) if db.resolve_id(o['id']) is not None else None
                os_ = o.get('s') or 1.0
                tw_ = (max(ob_[3] - ob_[0], ob_[4] - ob_[1]) if ob_ else max(o['_box'][3] - o['_box'][0], o['_box'][4] - o['_box'][1])) * (os_ if ob_ else 1.0)
                th_ = ((ob_[5] - ob_[2]) if ob_ else (o['_box'][5] - o['_box'][2])) * (os_ if ob_ else 1.0)
                pw_, ph_ = w, max(1.0, (ob[5] - ob[2]) * ps_)
                rw_ = round(tw_ / pw_, 2)
                rh_ = round(th_ / ph_, 2)
                rim_ = round(o['_box'][2] - b[5])
                M['fit_w'].append(rw_); M['fit_h'].append(rh_)
                fit['w'].append(rw_); fit['h'].append(rh_); fit['rim'].append(rim_)
                wb_ = 'bed' if pw_ >= BED_W else 'urn' if pw_ >= URN_W else 'pot' if pw_ >= 40 else 'tabletop'
                fit['by_w'][wb_]['w'].append(round(tw_)); fit['by_w'][wb_]['h'].append(round(th_))
            bn = [o for o in benches if math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < w / 2 + 220]
            rim = [o for o in lights if b[0] - 30 <= o['p'][0] <= b[3] + 30 and b[1] - 30 <= o['p'][1] <= b[4] + 30 and fixit._world_box(o) and b[5] - 60 <= fixit._world_box(o)[2] <= b[5] + 80]
            M['benches'] += 1 if len(bn) >= 2 else 0
            M['lights'] += 1 if rim else 0
            if w >= BED_W:
                style_beds[st_key][low] += 1
            if cont:
                M['with'] += 1
                M['counts'].append(len(cont))
                c_, s_ = math.cos(p['p'][5]), math.sin(p['p'][5])
                things = []
                for o in cont:
                    dx, dy = o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]
                    things.append({'id': o['id'], 'type': o['type'], 'x': round(dx * c_ - dy * s_, 1), 'y': round(dx * s_ + dy * c_, 1), 'z': round(o['p'][2] - p['p'][2], 1),
                                   'rz': round((o['p'][5] - p['p'][5]) % (2 * math.pi), 3), 'rx': round(o['p'][3], 3), 'ry': round(o['p'][4], 3),
                                   's': round(o.get('s') or 1.0, 3), 'top': round(o['_box'][5] - b[5]), 'bottom': round(o['_box'][2] - b[5])})
                ex = {'cell': ck, 'n': len(cont), 'things': things, 'ps': round(p.get('s') or 1.0, 3)}   # (ps: the planter's own scale, the offsets are at it)
                # (the fullest dressings are the ones worth copying: keep EXAMPLES, dropping the thinnest)
                M['examples'].append(ex)
                if len(M['examples']) > EXAMPLES:
                    M['examples'].sort(key=lambda e: -e['n'])
                    M['examples'] = M['examples'][:EXAMPLES]
        # ---- the rooms: where every planter stands, by room kind and style
        if rooms_read >= LIMIT:
            continue
        try:
            info = furnish.rooms(db, ck, trace=lambda rr: catalogue.style_keys(db, {'refs': rr, 'tile': None})[0])
        except Exception:
            info = None
        if not info or not info['rooms']:
            continue
        rooms_read += 1
        T = info['tile']
        all_refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in all_refs:
            r['_fam'] = arrangesurvey.family(db, r['id'], r['type'])
        wins = [a for a in info['refs'] if a.get('arch') and WINDOW.search(a['id'].lower())]
        cols = [a for a in info['refs'] if a.get('arch') and a.get('b') and COLUMN.search(a['id'].lower())]
        beams = [a for a in info['refs'] if a.get('arch') and a.get('b') and BEAM.search(a['id'].lower())]
        doors = [r for r in m['refs'] if r['type'] == 'DOOR' or (r.get('b') and 'jamb' in r['id'].lower())]
        stairs = [a for a in info['refs'] if a.get('arch') and re.search(r'stair|ramp', a['id'].lower())]
        S = styles[st_key]
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in all_refs if rm['x_min'] - 20 <= r['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= r['p'][1] <= rm['y_max'] + 20 and fl - 40 <= r['p'][2] <= fl + 300]
            counts = Counter(r['_fam'] for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS)
            kind = roomsurvey.room_kind(counts)
            tiles9 = rm['tiles'] * (T / 256.0) ** 2
            # (a planter of this room: on its floor, on its furniture or its ledge, under 150 up; higher than
            # that only a hanging planter by name, else it is the storey above's, standing on that floor)
            pl = [p for p in planters if p['_box'] and rm['x_min'] - 20 <= p['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= p['p'][1] <= rm['y_max'] + 20
                  and fl - 40 <= p['_box'][2] <= (fl + 400 if 'hang' in p['id'].lower() else fl + 150)]
            K = kinds[kind]
            K['rooms'] += 1; K['tiles'] += tiles9
            S['rooms'] += 1; S['tiles'] += tiles9
            r_wins = [a for a in wins if abs(a['p'][2] - fl) < 300 and rm['x_min'] - 40 <= a['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= a['p'][1] <= rm['y_max'] + 40]
            r_cols = []
            for a in cols:
                if not (fl - 60 <= a['p'][2] <= fl + 200 and rm['x_min'] - 40 <= a['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= a['p'][1] <= rm['y_max'] + 40):
                    continue
                bx = fixit._world_box(a)
                if bx and max(bx[3] - bx[0], bx[4] - bx[1]) <= T * 0.6:
                    r_cols.append(bx)
            r_doors = [d for d in doors if fl - 60 <= d['p'][2] <= fl + 200 and rm['x_min'] - 60 <= d['p'][0] <= rm['x_max'] + 60 and rm['y_min'] - 60 <= d['p'][1] <= rm['y_max'] + 60]
            r_stairs = [s for s in stairs if abs(s['p'][2] - fl) < 100 and rm['x_min'] - T <= s['p'][0] <= rm['x_max'] + T and rm['y_min'] - T <= s['p'][1] <= rm['y_max'] + T]
            seats = [r for r in inside if r['_fam'] in ('bench', 'table', 'chair') and r['p'][2] < fl + 60]
            furn = [r for r in inside if r['_fam'] in SURFACE_KINDS and not is_planter(r)]
            floor_pl, surf_pl, hung_pl = [], [], []
            for p in pl:
                b = p['_box']
                bottom = b[2] - fl
                low = p['id'].lower()
                M = models[low]
                if 'hang' in low:
                    hung_pl.append(p)
                    M['stands']['hung'] += 1
                    hanging['n'] += 1; hanging['models'][low] += 1; hanging['height'].append(round(bottom))
                    if any(math.hypot(min(max(p['p'][0], a['p'][0] + a['b'][0]), a['p'][0] + a['b'][3]) - p['p'][0], min(max(p['p'][1], a['p'][1] + a['b'][1]), a['p'][1] + a['b'][4]) - p['p'][1]) < 120
                           and fl + 100 < a['p'][2] + a['b'][2] < fl + 900 for a in beams):
                        hanging['beam'] += 1
                    S['hanging_models'][low] += 1
                    continue
                if bottom < 40:
                    floor_pl.append(p)
                    M['stands']['floor'] += 1
                    continue
                # on something: the piece whose footprint holds it and whose top meets its bottom
                host = None
                for f_ in furn:
                    fb = fixit._world_box(f_)
                    if not fb:
                        continue
                    if fb[0] - 12 <= p['p'][0] <= fb[3] + 12 and fb[1] - 12 <= p['p'][1] <= fb[4] + 12 and fb[5] - 30 <= b[2] <= fb[5] + 40:
                        host = f_['_fam'] or 'other'
                        break
                    if fb[0] - 12 <= p['p'][0] <= fb[3] + 12 and fb[1] - 12 <= p['p'][1] <= fb[4] + 12 and fb[2] <= b[2] <= fb[5] + 40 and f_['_fam'] in ('shelf', 'bookshelf', 'cupboard'):
                        host = f_['_fam']           # (a shelf's board inside its box)
                        break
                if host is None:
                    # (nothing of the furniture under it: a window sill, or a kit's wall ledge, a dais or a
                    # raised part of the floor; not a tabletop pot's place for Auto-furnish)
                    near_w = any(math.hypot(a['p'][0] - p['p'][0], a['p'][1] - p['p'][1]) < T * 0.55 for a in r_wins)
                    host = 'sill' if near_w else 'ledge'
                surf_pl.append((p, host))
                M['stands']['surface'] += 1
                M['on'][host] += 1
                S['surface_models'][low] += 1
            # the floor planters: class, spot, groups
            if floor_pl:
                K['rooms_with_floor'] += 1
                S['rooms_with_floor'] += 1
            for p in floor_pl:
                b = p['_box']
                w = p.get('_w') or max(b[3] - b[0], b[4] - b[1])
                cls = 'bed' if w >= BED_W else 'urn' if w >= URN_W else 'pot'
                K['floor'][cls] += 1
                S['classes'][cls] += 1
                S['models'][cls][p['id'].lower()] += 1
                S['scales'][cls][p['id'].lower()].append(round(p.get('s') or 1.0, 2))   # (the game's big Hlaalu urns are its small pot scaled up)
                wall_d = {'W': p['p'][0] - rm['x_min'], 'E': rm['x_max'] - p['p'][0], 'S': p['p'][1] - rm['y_min'], 'N': rm['y_max'] - p['p'][1]}
                tl = min(rm['_tiles'], key=lambda t: abs(t['x'] - p['p'][0]) + abs(t['y'] - p['p'][1]))
                tw = {s: tl['pat'][s] == 'wall' for s in furnish.STEP}
                # (the walls of the planter's own tile, how far off each)
                td = {'W': p['p'][0] - (tl['x'] - T / 2), 'E': (tl['x'] + T / 2) - p['p'][0], 'S': p['p'][1] - (tl['y'] - T / 2), 'N': (tl['y'] + T / 2) - p['p'][1]}
                at_walls = [s for s in tw if tw[s] and td[s] < 140]
                near_win = any(math.hypot(a['p'][0] - p['p'][0], a['p'][1] - p['p'][1]) < T * 0.55 for a in r_wins)
                at_post = any(bx[0] - 60 <= p['p'][0] <= bx[3] + 60 and bx[1] - 60 <= p['p'][1] <= bx[4] + 60 for bx in r_cols)
                near_door = any(math.hypot(d['p'][0] - p['p'][0], d['p'][1] - p['p'][1]) < 200 for d in r_doors)
                near_stair = any(math.hypot(s['p'][0] - p['p'][0], s['p'][1] - p['p'][1]) < T * 1.2 for s in r_stairs)
                near_seat = any(math.hypot(s['p'][0] - p['p'][0], s['p'][1] - p['p'][1]) < 110 for s in seats)
                corner = len(at_walls) >= 2 and any(a in 'NS' for a in at_walls) and any(a in 'EW' for a in at_walls)
                if at_post:
                    spot = 'post'
                elif near_win and at_walls:
                    spot = 'window'
                elif near_door:
                    spot = 'door'
                elif near_stair:
                    spot = 'stair'
                elif corner:
                    spot = 'corner'
                elif near_seat:
                    spot = 'seat'
                elif at_walls or min(wall_d.values()) < 140:
                    spot = 'plain wall'
                else:
                    spot = 'open'
                p['_spot'] = spot
                p['_cls'] = cls
                K['cls_spots'][cls][spot] += 1
                S['spots'][cls][spot] += 1
                models[p['id'].lower()]['spots'][spot] += 1
                if cls == 'bed':
                    K['beds'] += 1
                    K['bed_w'].append(round(w))
                    K['spots']['nook' if corner else 'window' if near_win else 'wall' if min(wall_d.values()) < 140 else 'middle'] += 1
                    if sum(1 for o in inside if o['_fam'] == 'bench' and math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < w / 2 + 220) >= 2:
                        K['island'] += 1
                else:
                    K['pots'] += 1
            if floor_pl:
                K['rooms_with_bed'] += 1 if any(p['_cls'] == 'bed' for p in floor_pl) else 0
            K['per_room'][_bucket(tiles9)][min(len(floor_pl), 6)] += 1
            # groups of floor planters: singles, pairs, rows
            left = list(floor_pl)
            while left:
                grp = [left.pop(0)]
                i = 0
                while i < len(grp):
                    a = grp[i]
                    for b2 in list(left):
                        if math.hypot(a['p'][0] - b2['p'][0], a['p'][1] - b2['p'][1]) <= GROUP_D:
                            grp.append(b2); left.remove(b2)
                    i += 1
                same = len({g['id'].lower() for g in grp}) == 1
                if len(grp) == 1:
                    pat = 'single'
                elif len(grp) == 2:
                    pat = 'pair'
                    a, b2 = grp
                    d_ = math.hypot(a['p'][0] - b2['p'][0], a['p'][1] - b2['p'][1])
                    pairs['n'] += 1; pairs['same'] += 1 if same else 0; pairs['spacing'].append(round(d_))
                    K['pairs'] += 1; K['pair_same'] += 1 if same else 0
                    # (flanking a door: the door's middle between them, each within 200 of it)
                    flank = False
                    for d in r_doors:
                        da, db_ = math.hypot(d['p'][0] - a['p'][0], d['p'][1] - a['p'][1]), math.hypot(d['p'][0] - b2['p'][0], d['p'][1] - b2['p'][1])
                        if da < 200 and db_ < 200 and (d['p'][0] - a['p'][0]) * (d['p'][0] - b2['p'][0]) + (d['p'][1] - a['p'][1]) * (d['p'][1] - b2['p'][1]) < 0:
                            flank = True
                            break
                    if flank:
                        pairs['door'] += 1; K['pair_door'] += 1
                        if len(pairs['examples']) < 40:
                            pairs['examples'].append({'cell': ck, 'ids': [a['id'], b2['id']], 'd': round(d_), 'kind': kind, 'style': st_key})
                else:
                    # a row: the points nearly on one line, evenly spaced
                    xs = [g['p'][0] for g in grp]; ys = [g['p'][1] for g in grp]
                    along_x = (max(xs) - min(xs)) >= (max(ys) - min(ys))
                    dev = (max(ys) - min(ys)) if along_x else (max(xs) - min(xs))
                    ordd = sorted(grp, key=lambda g: g['p'][0] if along_x else g['p'][1])
                    gaps = [math.hypot(ordd[i + 1]['p'][0] - ordd[i]['p'][0], ordd[i + 1]['p'][1] - ordd[i]['p'][1]) for i in range(len(ordd) - 1)]
                    even = gaps and (max(gaps) - min(gaps)) <= 0.35 * (sum(gaps) / len(gaps))
                    if dev <= 40 and even:
                        pat = 'row'
                        rows['n'] += 1; rows['same'] += 1 if same else 0; rows['gap'].extend(round(g) for g in gaps); rows['len'][min(len(grp), 6)] += 1
                        K['rows'] += 1; K['row_same'] += 1 if same else 0
                        if any(g['_spot'] == 'window' for g in grp):
                            rows['window'] += 1; K['row_window'] += 1
                        if all(g['_spot'] in ('window', 'plain wall', 'corner', 'door') for g in grp):
                            rows['wall'] += 1
                        if len(rows['examples']) < 40:
                            rows['examples'].append({'cell': ck, 'ids': [g['id'] for g in ordd], 'gap': round(sum(gaps) / len(gaps)), 'kind': kind, 'style': st_key, 'spot': grp[0]['_spot']})
                    else:
                        pat = 'cluster'
                K['groups'][pat] += 1
                S['groups'][pat] += 1
            # the tabletop pots and the hanging ones, per room kind
            if surf_pl:
                K['rooms_with_surface'] += 1
            for p, host in surf_pl:
                K['surface'] += 1
                K['surfaces'][host] += 1
                if host not in ('ledge', 'sill'):
                    K['on_furniture'] += 1
            K['hung'] += len(hung_pl)
            # loose flora (plants standing in the room with no planter under them)
            lf = [o for o in flora if id(o) not in in_any and o['_box'] and rm['x_min'] - 20 <= o['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= o['p'][1] <= rm['y_max'] + 20 and fl - 40 <= o['_box'][2] <= fl + 100]
            left = list(lf)
            while left:
                grp = [left.pop(0)]
                i = 0
                while i < len(grp):
                    a = grp[i]
                    for b2 in list(left):
                        if math.hypot(a['p'][0] - b2['p'][0], a['p'][1] - b2['p'][1]) <= 160:
                            grp.append(b2); left.remove(b2)
                    i += 1
                K['flora_groups'] += 1
                K['flora_sizes'].append(min(len(grp), 8))
                K['flora_kinds'].update(re.sub(r'_\d+$', '', o['id'].lower()) for o in grp)
                K['flora_ids'].update(o['id'] for o in grp if o['type'] == 'STAT')
                K['rocks'] += sum(1 for o in grp if re.search(r'rock|stone', o['id'].lower()))
                if any(math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < 260 for o in grp for p in pl):
                    K['flora_near'] += 1
    out = {'cells': seen, 'rooms_read': rooms_read, 'models': {}, 'kinds': {}, 'style_beds': {}, 'styles': {}, 'fit': {}, 'hanging': {}, 'pairs': {}, 'rows': {}}
    for low, M in models.items():
        cs = sorted(M['counts'])
        st = M['stands']
        tot = float(sum(st.values()) or 1)
        # (a hanging planter by its name; a tabletop pot by the game's use of it, seen ten times or more
        # and on tables and shelves more often than on the floor; else by its width)
        if 'hang' in low:
            cls = 'hanging'
        elif tot >= 10 and st['surface'] / tot > 0.5:
            cls = 'tabletop'
        elif tot < 10 and (M['w'] or 0) < 40:
            cls = 'tabletop'
        elif (M['w'] or 0) >= BED_W:
            cls = 'bed'
        elif (M['w'] or 0) >= URN_W:
            cls = 'urn'
        else:
            cls = 'pot'
        out['models'][low] = {'n': M['n'], 'with': M['with'], 'median': cs[len(cs) // 2] if cs else 0, 'max': cs[-1] if cs else 0, 'w': M['w'], 'd': M['d'], 'h': M['h'],
                              'kinds': dict(M['kinds'].most_common(12)), 'styles': dict(M['styles'].most_common(6)), 'examples': M['examples'],
                              'benches': round(M['benches'] / float(M['n'] or 1), 3), 'lights': round(M['lights'] / float(M['n'] or 1), 3),
                              'stands': dict(st), 'on': dict(M['on'].most_common(6)), 'class': cls, 'spots': dict(M['spots']),
                              'fit_w': _pcts(M['fit_w']), 'fit_h': _pcts(M['fit_h'])}
    for kind, K in kinds.items():
        n = float(K['rooms'] or 1)
        g = float(K['flora_groups'] or 1)
        t9 = float(K['tiles'] or 1)
        nf = float(sum(K['floor'].values()) or 1)
        ng = float(sum(K['groups'].values()) or 1)
        out['kinds'][kind] = {'rooms': K['rooms'], 'tiles9': round(K['tiles'] / n, 1), 'beds_per_9': round(9.0 * K['beds'] / t9, 3),
                              'pots_per_9': round(9.0 * K['pots'] / t9, 3), 'rooms_with_bed': round(K['rooms_with_bed'] / n, 3),
                              'spots': {k: round(v / float(K['beds'] or 1), 3) for k, v in K['spots'].items()}, 'island': round(K['island'] / float(K['beds'] or 1), 3),
                              'flora_groups_per_9': round(9.0 * K['flora_groups'] / t9, 3), 'flora_near_planter': round(K['flora_near'] / g, 3),
                              'flora_size': _med(K['flora_sizes']), 'flora_kinds': dict(K['flora_kinds'].most_common(10)), 'rocks_per_group': round(K['rocks'] / g, 2),
                              'flora_ids': dict(K['flora_ids'].most_common(16)),
                              'bed_w': _med(K['bed_w']),
                              # v3
                              'floor_per_9': round(9.0 * sum(K['floor'].values()) / t9, 3), 'rooms_with_floor': round(K['rooms_with_floor'] / n, 3),
                              'class_per_9': {c: round(9.0 * v / t9, 3) for c, v in K['floor'].items()}, 'class_share': {c: round(v / nf, 3) for c, v in K['floor'].items()},
                              'per_room': {bk: dict(sorted(C.items())) for bk, C in K['per_room'].items()},
                              'cls_spots': {c: {s: round(v / float(sum(C.values()) or 1), 3) for s, v in C.items()} for c, C in K['cls_spots'].items()},
                              'groups': {p: round(v / ng, 3) for p, v in K['groups'].items()},
                              'pair_door': round(K['pair_door'] / float(K['pairs'] or 1), 3), 'pair_same': round(K['pair_same'] / float(K['pairs'] or 1), 3),
                              'row_window': round(K['row_window'] / float(K['rows'] or 1), 3), 'row_same': round(K['row_same'] / float(K['rows'] or 1), 3),
                              'surface_per_9': round(9.0 * K['surface'] / t9, 3), 'furniture_pots_per_9': round(9.0 * K['on_furniture'] / t9, 3),
                              'rooms_with_surface': round(K['rooms_with_surface'] / n, 3),
                              'surfaces': {s: round(v / float(K['surface'] or 1), 3) for s, v in K['surfaces'].most_common(8)},
                              'hung_per_9': round(9.0 * K['hung'] / t9, 3)}
    for st, C in style_beds.items():
        out['style_beds'][st] = dict(C.most_common(6))
    for st, S in styles.items():
        t9 = float(S['tiles'] or 1)
        ncl = float(sum(S['classes'].values()) or 1)
        out['styles'][st] = {'rooms': S['rooms'], 'floor_per_9': round(9.0 * sum(S['classes'].values()) / t9, 3), 'rooms_with_floor': round(S['rooms_with_floor'] / float(S['rooms'] or 1), 3),
                             'classes': {c: round(v / ncl, 3) for c, v in S['classes'].items()},
                             'models': {c: dict(C.most_common(6)) for c, C in S['models'].items()},
                             'scales': {c: {i: _med(v) for i, v in D.items()} for c, D in S['scales'].items()},
                             'spots': {c: {s: round(v / float(sum(C.values()) or 1), 3) for s, v in C.items()} for c, C in S['spots'].items()},
                             'groups': {p: round(v / float(sum(S['groups'].values()) or 1), 3) for p, v in S['groups'].items()},
                             'surface_models': dict(S['surface_models'].most_common(6)), 'hanging_models': dict(S['hanging_models'].most_common(4))}
    out['fit'] = {'n': len(fit['w']), 'w_ratio': _pcts(fit['w']), 'h_ratio': _pcts(fit['h']), 'over_rim': _pcts(fit['rim']),
                  'by_pot': {k: {'n': len(v['w']), 'plant_w': _pcts(v['w']), 'plant_h': _pcts(v['h'])} for k, v in fit['by_w'].items()}}
    out['hanging'] = {'n': hanging['n'], 'height': _pcts(hanging['height']), 'beam_near': round(hanging['beam'] / float(hanging['n'] or 1), 3), 'models': dict(hanging['models'].most_common(8))}
    out['pairs'] = {'n': pairs['n'], 'same_model': round(pairs['same'] / float(pairs['n'] or 1), 3), 'flank_door': round(pairs['door'] / float(pairs['n'] or 1), 3),
                    'spacing': _pcts(pairs['spacing']), 'examples': pairs['examples']}
    out['rows'] = {'n': rows['n'], 'same_model': round(rows['same'] / float(rows['n'] or 1), 3), 'under_window': round(rows['window'] / float(rows['n'] or 1), 3),
                   'at_wall': round(rows['wall'] / float(rows['n'] or 1), 3), 'gap': _pcts(rows['gap']), 'len': dict(rows['len']), 'examples': rows['examples']}
    return out


# ---- what Auto-furnish and the checks ask

def rule(db, purpose):
    """How rooms of this kind hold garden beds and floor planters: the v2 keys ('beds_per_9', 'rooms_with_bed',
    'spots': {'middle', 'wall', 'nook', 'window'}, 'island', 'flora_groups_per_9', 'flora_near_planter',
    'flora_size', 'rocks_per_group') and the v3 ones ('floor_per_9', 'class_per_9', 'class_share', 'per_room',
    'cls_spots', 'groups', 'pair_door', 'row_window', 'surface_per_9', 'surfaces', 'hung_per_9'); a hall's,
    an entrance's or a bath's read the game's living and empty rooms. None until surveyed."""
    s = ready(db)
    if not s:
        return None
    kinds = {'hall': ('living', 'empty'), 'entry': ('living', 'empty'), 'landing': ('empty',), 'corridor': ('empty',), 'bath': ('living',),
             'dining': ('living',), 'mess': ('tavern',)}.get(purpose, (purpose,))
    K = None
    for kd in kinds:
        K = s['kinds'].get(kd)
        if K and K['rooms'] >= 8:
            break
    return K


def style_rule(db, style_label=None, prefix=None):
    """How places of this style stand their floor planters: {'floor_per_9', 'classes': {bed, urn, pot: share},
    'models': {class: {id: n}}, 'spots': {class: {spot: share}}, 'groups'}; the label's figures, else the kit
    prefix's, else None."""
    s = ready(db)
    if not s:
        return None
    for st in (style_label, prefix):
        S = s['styles'].get(st) if st else None
        if S and S['rooms'] >= 8:
            return S
    return None


def classify(db, rid):
    """This planter model's class by the game's use of it: 'bed', 'urn', 'pot' (a floor planter), 'tabletop'
    (stands on tables and shelves), 'hanging'; by its size and name when the game never stood it."""
    s = ready(db)
    M = (s or {}).get('models', {}).get(rid.lower())
    if M:
        return M['class']
    low = rid.lower()
    if 'hang' in low:
        return 'hanging'
    b = mapdata.object_bounds(db, db.resolve_id(rid)) if db.resolve_id(rid) is not None else None
    w = max(b[3] - b[0], b[4] - b[1]) if b else 0
    return 'bed' if w >= BED_W else 'urn' if w >= URN_W else 'pot' if w >= 40 else 'tabletop'


def floor_models(db, cls, style_label=None, prefix=None):
    """The floor planter models of this class ('bed', 'urn', 'pot'; 'tabletop', 'hanging') the game stands in
    places of this style, most used first, that exist here (the style's own as the game stood them, scaled
    or not: a Hlaalu big urn is furn_planter_02 scaled up, see scale_for); every style's of the class when
    the style has none."""
    s = ready(db)
    if not s:
        return []
    own = []
    for st in (style_label, prefix):
        S = s['styles'].get(st) if st else None
        if S and S['models'].get(cls):
            own = [i for i, _n in sorted(S['models'][cls].items(), key=lambda kv: -kv[1]) if db.resolve_id(i) is not None
                   and s['models'].get(i, {}).get('class') not in ('hanging', 'tabletop')]
            if own:
                return own
    pool = [i for i, M in sorted(s['models'].items(), key=lambda kv: -kv[1]['n']) if M['class'] == cls]
    return [i for i in pool if db.resolve_id(i) is not None]


def scale_for(db, cls, rid, style_label=None, prefix=None):
    """The scale the game stands this planter model at as a floor planter of this class in places of this
    style (the median), 1.0 when unknown; a pot made a big urn by scaling comes out as big."""
    s = ready(db)
    if not s:
        return 1.0
    for st in (style_label, prefix):
        S = s['styles'].get(st) if st else None
        v = ((S or {}).get('scales') or {}).get(cls, {}).get(rid.lower())
        if v:
            return max(0.9, min(2.5, float(v)))
    return 1.0


def models_for(db, style_label=None, prefix=None, min_w=BED_W):
    """The bed models (planters at least min_w wide) the game stands in places of this style, most used
    first, that exist here; every style's when the style has none."""
    s = ready(db)
    if not s:
        return []
    own = []
    for st in (style_label, prefix):
        if st and s['style_beds'].get(st):
            own = [i for i, _n in sorted(s['style_beds'][st].items(), key=lambda kv: -kv[1])]
            break
    pool = own or [i for i, M in sorted(s['models'].items(), key=lambda kv: -kv[1]['n']) if (M['w'] or 0) >= min_w]
    return [i for i in pool if db.resolve_id(i) is not None and (s['models'].get(i, {}).get('w') or 0) >= min_w]


def dressing(db, rid, rng, min_n=None, scale=1.0):
    """One of the game's own gardens of this planter model, whole: [{'id', 'x', 'y', 'z', 'rz', 'rx', 'ry',
    's', 'bottom', 'top'}] in the planter's frame (offsets from its origin, z from its origin), drawn by chance
    among the model's fullest examples (min_n: at least this many things); None when the model was never seen
    planted. scale: the planter's scale here; an example of a planter at another scale has its offsets scaled
    to match (the soil is where the mesh puts it), the game's own scale preferred."""
    s = ready(db)
    if not s:
        return None
    M = s['models'].get(rid.lower())
    if not M or not M['examples']:
        return None
    exs = [e for e in M['examples'] if all(db.resolve_id(t['id']) is not None for t in e['things'])]
    if min_n:
        exs = [e for e in exs if e['n'] >= min_n] or exs
    if not exs:
        return None
    same = [e for e in exs if abs((e.get('ps') or 1.0) - scale) < 0.08]
    e = rng.choice(same or exs)
    k = scale / (e.get('ps') or 1.0)
    out = []
    for t in e['things']:
        t = dict(t)
        if abs(k - 1.0) > 0.01:
            t['x'], t['y'], t['z'] = t['x'] * k, t['y'] * k, t['z'] * k
        out.append(t)
    return out


def usual(db, rid):
    """How many things the game usually grows in this planter model (the median over its planted ones), when
    it was seen planted five times or more and the median is two or more; else None."""
    s = ready(db)
    if not s:
        return None
    M = s['models'].get(rid.lower())
    if not M or M['with'] < 5 or M['median'] < 2:
        return None
    return M['median']


def fits(db, plant_id, pot_id):
    """Whether this plant is one the game grows in pots of this size: its width and height against the
    pot's within the game's 90th percentile for the pot's width class (fit.by_pot); True when unsurveyed."""
    s = ready(db)
    if not s or not s.get('fit'):
        return True
    pb = mapdata.object_bounds(db, db.resolve_id(pot_id)) if db.resolve_id(pot_id) is not None else None
    tb = mapdata.object_bounds(db, db.resolve_id(plant_id)) if db.resolve_id(plant_id) is not None else None
    if not pb or not tb:
        return True
    pw = max(pb[3] - pb[0], pb[4] - pb[1])
    cls = 'bed' if pw >= BED_W else 'urn' if pw >= URN_W else 'pot' if pw >= 40 else 'tabletop'
    F = s['fit']['by_pot'].get(cls)
    if not F or F['n'] < 20:
        return True
    return max(tb[3] - tb[0], tb[4] - tb[1]) <= F['plant_w'][4] * 1.1 and (tb[5] - tb[2]) <= F['plant_h'][4] * 1.1


def report(db):
    s = survey(db)
    out = ['%d places with planters, %d with their rooms read' % (s['cells'], s['rooms_read'])]
    for low, M in sorted(s['models'].items(), key=lambda kv: -kv[1]['n'])[:40]:
        out.append('%-34s %-8s n %4d planted %4d median %2d max %2d size %sx%sx%s stands %s on %s spots %s fit w %s h %s kinds %s styles %s'
                   % (low, M['class'], M['n'], M['with'], M['median'], M['max'], M['w'], M['d'], M['h'], M['stands'], M['on'], M['spots'], M['fit_w'], M['fit_h'],
                      list(M['kinds'].items())[:4], list(M['styles'].items())[:3]))
    for kind, K in sorted(s['kinds'].items(), key=lambda kv: -kv[1]['rooms']):
        out.append('%-9s rooms %4d (%.1f tiles): floor/9 %.3f (%s) in %.0f%% of rooms; per room %s; spots %s; groups %s pair at door %.0f%% row under window %.0f%%; '
                   'surface pots/9 %.2f (on furniture %.2f) in %.0f%% of rooms on %s; hung/9 %.2f; beds/9 %.3f width %s island %.0f%%; loose flora groups/9 %.2f size %s rocks %.2f'
                   % (kind, K['rooms'], K['tiles9'], K['floor_per_9'], K['class_per_9'], 100 * K['rooms_with_floor'], K['per_room'], K['cls_spots'], K['groups'],
                      100 * K['pair_door'], 100 * K['row_window'], K['surface_per_9'], K['furniture_pots_per_9'], 100 * K['rooms_with_surface'], K['surfaces'], K['hung_per_9'],
                      K['beds_per_9'], K['bed_w'], 100 * K['island'], K['flora_groups_per_9'], K['flora_size'], K['rocks_per_group']))
    for st, S in sorted(s['styles'].items(), key=lambda kv: -kv[1]['rooms']):
        out.append('style %-12s rooms %4d floor/9 %.3f in %.0f%% of rooms classes %s models %s spots %s groups %s surface %s hanging %s'
                   % (st, S['rooms'], S['floor_per_9'], 100 * S['rooms_with_floor'], S['classes'], S['models'], S['spots'], S['groups'], S['surface_models'], S['hanging_models']))
    F = s['fit']
    out.append('fit: %d plants in planters; width ratio %s height ratio %s over rim %s; by pot %s' % (F['n'], F['w_ratio'], F['h_ratio'], F['over_rim'], F['by_pot']))
    H = s['hanging']
    out.append('hanging: %d, bottom height %s, beam near %.0f%%, models %s' % (H['n'], H['height'], 100 * H['beam_near'], H['models']))
    P = s['pairs']
    out.append('pairs: %d, same model %.0f%%, flanking a door %.0f%%, spacing %s' % (P['n'], 100 * P['same_model'], 100 * P['flank_door'], P['spacing']))
    R = s['rows']
    out.append('rows: %d, same model %.0f%%, under a window %.0f%%, at a wall %.0f%%, gap %s, lengths %s' % (R['n'], 100 * R['same_model'], 100 * R['under_window'], 100 * R['at_wall'], R['gap'], R['len']))
    for st, C in sorted(s['style_beds'].items(), key=lambda kv: -sum(kv[1].values())):
        out.append('style %-14s beds %s' % (st, C))
    return out
