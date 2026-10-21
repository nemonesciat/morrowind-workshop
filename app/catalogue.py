"""The catalogue rules: the habits the user's screenshot catalogue of good design shows, each measured
over the game's own kit-built interiors (never the mod's; an exemplary place counts several times over,
taste.py) and kept as a rate per building style rather than a hard-coded count:

1. A light at every stair foot: a sconce, a candle stand or a lantern within a tile of the flight, at
   its foot more than its head.
2. Round rugs centred in Redoran and Indoril halls, rectangular rugs under the tables elsewhere.
3. Plants in planters, at walls and at the feet of columns, never loose mid-floor.
4. Benches (and planters, urns) up on the wall ledges of Redoran and Indoril rooms.
5. Banners hung from the arches into two-storey voids.
6. Shelves of pots and jars standing out from the walls as room dividers in Hlaalu.

Auto-furnish asks for each rule by the place's style (the kit its walls are built from) and follows
it at the game's rate (catalogue.rule). Kept in the cache folder once done (a few minutes); ready()
runs it in the background the first time."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey

LIMIT = 200
LIGHT_KIND = (('sconce', re.compile(r'sconce')), ('candle', re.compile(r'candle')), ('lantern', re.compile(r'lantern')),
              ('lamp', re.compile(r'lamp|torch')), ('brazier', re.compile(r'brazier|fire')))
BANNER = re.compile(r'banner|flag|pennant|tapestr')
PLANT = re.compile(r'flora_|_plant|fern|shrub|bush|tree|vine|mushroom|flower|ivy')
PLANTER = re.compile(r'planter|flowerbox|plantpot|plant_pot')
POTS = re.compile(r'pot_|_pot|urn|jar|jug|bowl|vase|misc_com_bottle|pitcher|basket')
COLUMN = re.compile(r'pillar|column|post|colum')
LEDGE_KINDS = ('bench', 'planter', 'urn', 'basket', 'chest', 'crate')
LEDGE_UP = (24, 140)          # a thing whose bottom is this far above the room's floor stands on a ledge
_cache = {}
_thread = {}


def _disk(db, limit):
    import taste
    return taste.cache_file('catalogue_%s_%d_v1' % (taste.sig(db), limit))


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background
    (while a survey for a changed taste set runs, the newest earlier one stands in)."""
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
        import background
        _thread['t'] = background.start('the catalogue rules (stair lights, rugs, planters, ledges)', lambda: survey(db, limit), task=('catalogue', 'survey', [limit]))
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


def _kind(low, table):
    for k, pat in table:
        if pat.search(low):
            return k
    return None


def _box(r):
    import fixit
    return fixit._world_box(r)


ROUND = re.compile(r'round|circ|oval|octagon')
ROUND_IDS = {'furn_de_rug_01'}        # the game's small round rug with the fringe (furn_rug_01.nif, a textured square: the mesh can't tell)
_round = {}


def is_round(db, rid):
    """A round (or oval) rug: named so, one of the game's known round ones, or a rug whose mesh is an
    ellipse (its farthest vertex from the middle is no farther than its half-width; a rectangle's reaches
    the half-diagonal). furn_de_rug_02 and Tamriel Data's small rugs are textured squares: rectangular."""
    low = rid.lower()
    if low in _round:
        return _round[low]
    out = bool(ROUND.search(low)) or low in ROUND_IDS
    if not out:
        try:
            ri = db.resolve_id(rid)
            shapes = kits._model(db, ri) if ri is not None else None
            b = mapdata.object_bounds(db, ri) if ri is not None else None
            if shapes and b:
                w, d = b[3] - b[0], b[4] - b[1]
                cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
                far = 0.0
                n = 0
                for sh in shapes:
                    p = sh['p']
                    for k in range(0, len(p) - 2, 3):
                        n += 1
                        far = max(far, math.hypot(p[k] - cx, p[k + 1] - cy))
                out = n >= 16 and far <= 1.12 * max(w, d) / 2 and max(w, d) / min(w, d) < 1.6
        except Exception:
            out = False
    _round[low] = out
    return out


HOUSE_LABELS = ('Redoran', 'Indoril', 'Hlaalu', 'Velothi', 'Imperial', 'Common', 'Mournhold', 'Dres', 'Telvanni', 'Nordic',
                'Breton', 'Cyrodiilic', 'Redguard', 'High Elf', 'Stronghold')
NOT_A_HOUSE = re.compile(r'cave|tomb|sewer|dwrv|dwemer|daed|ruin|_ex_|rock|mine|grotto|cavern|_tx_|shipwreck|_ship')


def style_keys(db, info):
    """Under which names a place's figures are kept: ['*', its kit prefix (in_hlaalu), its style label
    (Hlaalu)], the last two when known; and whether the place counts at all: a place laid in 256-unit
    tiles always, a traced floor (the Redoran manors' rooms, which the kit reader doesn't tile) only
    when its walls are a house style's and not a cave's or a tomb's."""
    arch = [r for r in info['refs'] if r.get('arch') and r.get('b')]
    prefixes = Counter(kits.kit_prefix(r['id']) for r in arch if kits.kit_prefix(r['id']))
    labels = Counter(mapdata.style_of(r['id']) for r in arch if mapdata.style_of(r['id']))
    prefix = prefixes.most_common(1)[0][0] if prefixes else None
    label = labels.most_common(1)[0][0] if labels else None
    keys = ['*'] + [k for k in (prefix, label) if k]
    if info['tile'] == 256:
        return True, keys
    if label not in HOUSE_LABELS or not arch:
        return False, keys
    if sum(1 for r in arch if NOT_A_HOUSE.search(r['id'].lower())) > len(arch) * 0.3:
        return False, keys
    return True, keys


def _new():
    return {'cells': 0,
            'stairs': {'n': 0, 'lit': 0, 'foot': 0, 'head': 0, 'kinds': Counter(), 'dist': []},
            'rugs': {'n': 0, 'round': 0, 'round_centred': 0, 'round_under_table': 0, 'rect': 0, 'rect_under_table': 0, 'rect_by_bed': 0,
                     'rect_centred': 0, 'rooms': 0, 'rooms_with': 0, 'per_room': Counter()},
            'plants': {'n': 0, 'in_planter': 0, 'at_wall': 0, 'at_column': 0, 'loose_mid': 0, 'col_rooms': 0, 'col_plants': 0},
            'planters': {'n': 0, 'at_wall': 0, 'at_column': 0, 'mid': 0, 'with_plant': 0, 'col_rooms': 0, 'col_n': 0},
            'ledge': {'n': 0, 'up': 0, 'ups': [], 'kinds': Counter(), 'kinds_up': Counter(), 'rooms': 0, 'rooms_with': 0},
            'void': {'rooms': 0, 'with_banner': 0, 'banners': 0, 'ups': []},
            'dividers': {'n': 0, 'mid': 0, 'pots': 0, 'rooms': 0, 'rooms_with': 0}}


def _survey(db, limit):
    import taste
    S = defaultdict(_new)
    seen = 0
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    # (a spread over the whole list, so Redoran's Ald-ruhn and Indoril's places are seen: the rules
    # are by style, and the first few hundred places by name are nearly all one mod's)
    cells = taste.spread(cells, limit)
    for ck in cells:
        if seen >= limit:
            break
        try:
            # (a floor is traced only where it would count: a house style's walls, not a cave's)
            info = furnish.rooms(db, ck, trace=lambda refs: style_keys(db, {'refs': refs, 'tile': None})[0])
        except Exception:
            continue
        # (the Redoran manors' rooms are not laid as 256-unit tiles: their floors are traced, in 128-unit
        # tiles; the rules read as well from those, when the walls are a house's: style_keys)
        if not info['rooms'] or info['tile'] not in (256, furnish.FLOOR_T):
            continue
        ok, keys = style_keys(db, info)
        if not ok:
            continue
        seen += 1
        T = info['tile']
        arch = [r for r in info['refs'] if r.get('b') and r.get('arch')]
        style = next((k for k in keys[1:] if k in kits.kits(db)), keys[1] if len(keys) > 1 else '?')
        accs = [S[k] for k in keys]
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in refs:
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
        for acc in accs:
            acc['cells'] += 1
        # ---- 1. stairs: the lights within a tile and a half, and at which end
        si = kits.stairs(db, style) if style in kits.kits(db) else None
        for st in arch:
            low = st['id'].lower()
            if not re.search(r'stair|ramp', low):
                continue
            sp = next((p for p in si['pieces'] if p['id'].lower() == low), None) if si else None
            foot = None
            if sp:
                q = st['p'][5]
                dx, dy = furnish.STEP[sp['low']]
                # (the low side in the piece's own frame, turned as it stands; the game turns clockwise)
                c, s_ = math.cos(q), math.sin(q)
                fx, fy = dx * c + dy * s_, -dx * s_ + dy * c
                foot = (st['p'][0] + fx * T * 0.5, st['p'][1] + fy * T * 0.5)
                head = (st['p'][0] - fx * T * 0.5, st['p'][1] - fy * T * 0.5)
            near = [r for r in refs if r['type'] == 'LIGH' and math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) < T * 1.5
                    and st['p'][2] - 100 <= r['p'][2] <= st['p'][2] + 450]
            for acc in accs:
                A = acc['stairs']
                A['n'] += 1
                if near:
                    A['lit'] += 1
                    A['kinds'].update(_kind(r['id'].lower(), LIGHT_KIND) or 'other' for r in near)
                    A['dist'].append(round(min(math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) for r in near)))
                    if foot:
                        for r in near:
                            df = math.hypot(r['p'][0] - foot[0], r['p'][1] - foot[1])
                            dh = math.hypot(r['p'][0] - head[0], r['p'][1] - head[1])
                            A['foot' if df <= dh else 'head'] += 1
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and fl - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 400]
            floor = [r for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 160]
            kind = roomsurvey.room_kind(Counter(r['_fam'] for r in floor))
            cx, cy = (rm['x_min'] + rm['x_max']) / 2, (rm['y_min'] + rm['y_max']) / 2
            walls = []
            for t in rm['_tiles']:
                for s, (dx, dy) in furnish.STEP.items():
                    if t['pat'][s] != 'wall':
                        continue
                    off = t['pat']['offset'].get(s, T / 2 - 16)
                    walls.append((s, (t['y'] + dy * off) if s in ('N', 'S') else (t['x'] + dx * off), (t['x'] if s in ('N', 'S') else t['y'])))

            def d_wall(bx):
                best = None
                for s, face, mid in walls:
                    if s in ('N', 'S'):
                        if bx[3] < mid - T / 2 - 20 or bx[0] > mid + T / 2 + 20:
                            continue
                        d = (face - bx[4]) if s == 'N' else (bx[1] - face)
                    else:
                        if bx[4] < mid - T / 2 - 20 or bx[1] > mid + T / 2 + 20:
                            continue
                        d = (face - bx[3]) if s == 'E' else (bx[0] - face)
                    if best is None or d < best:
                        best = d
                return best if best is not None else 999
            cols = []
            for a in arch:
                low = a['id'].lower()
                if COLUMN.search(low) and fl - 60 <= a['p'][2] <= fl + 200 and rm['x_min'] + T * 0.3 <= a['p'][0] <= rm['x_max'] - T * 0.3 \
                        and rm['y_min'] + T * 0.3 <= a['p'][1] <= rm['y_max'] - T * 0.3:
                    bx = _box(a)
                    if bx and max(bx[3] - bx[0], bx[4] - bx[1]) <= T * 0.6:
                        cols.append(bx)

            def at_col(bx):
                return any(max(c[0] - bx[3], bx[0] - c[3], c[1] - bx[4], bx[1] - c[4], 0) < 60 for c in cols)
            tables = [_box(r) for r in floor if r['_fam'] in ('table', 'counter')]
            beds = [_box(r) for r in floor if r['_fam'] == 'bed']
            # ---- 2. rugs: round or rectangular, centred, under a table, by a bed
            rugs = [r for r in floor if r['_fam'] == 'rug']
            for acc in accs:
                R = acc['rugs']
                R['rooms'] += 1
                if rugs:
                    R['rooms_with'] += 1
                    R['per_room'][min(len(rugs), 4)] += 1
            for r in rugs:
                rnd = is_round(db, r['id'])
                bx = _box(r)
                mx, my = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
                centred = math.hypot(mx - cx, my - cy) < T * 0.5
                under = any(tb and min(tb[3], bx[3]) - max(tb[0], bx[0]) > 0.5 * (tb[3] - tb[0]) and min(tb[4], bx[4]) - max(tb[1], bx[1]) > 0.5 * (tb[4] - tb[1]) for tb in tables)
                by_bed = any(bb and max(bb[0] - bx[3], bx[0] - bb[3], bb[1] - bx[4], bx[1] - bb[4]) < 40 for bb in beds)
                for acc in accs:
                    R = acc['rugs']
                    R['n'] += 1
                    if rnd:
                        R['round'] += 1
                        R['round_centred'] += 1 if centred else 0
                        R['round_under_table'] += 1 if under else 0
                    else:
                        R['rect'] += 1
                        R['rect_under_table'] += 1 if under else 0
                        R['rect_by_bed'] += 1 if by_bed else 0
                        R['rect_centred'] += 1 if centred else 0
            # ---- 3. plants and planters
            planters = [r for r in inside if PLANTER.search(r['id'].lower())]
            pboxes = [_box(p) for p in planters]
            plants = [r for r in inside if PLANT.search(r['id'].lower()) and not PLANTER.search(r['id'].lower())
                      and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 200]
            for r in plants:
                bx = _box(r)
                if not bx:
                    continue
                in_pl = any(pb and pb[0] - 30 <= r['p'][0] <= pb[3] + 30 and pb[1] - 30 <= r['p'][1] <= pb[4] + 30 for pb in pboxes)
                dw = d_wall(bx)
                for acc in accs:
                    P = acc['plants']
                    P['n'] += 1
                    P['in_planter'] += 1 if in_pl else 0
                    P['at_wall'] += 1 if dw <= 60 else 0
                    if cols:
                        P['col_plants'] += 1
                        P['at_column'] += 1 if at_col(bx) else 0
                    P['loose_mid'] += 1 if (not in_pl and dw > 110 and not at_col(bx)) else 0
            for r in planters:
                bx = _box(r)
                if not bx:
                    continue
                dw = d_wall(bx)
                has = any(bx[0] - 30 <= p['p'][0] <= bx[3] + 30 and bx[1] - 30 <= p['p'][1] <= bx[4] + 30 for p in plants)
                for acc in accs:
                    P = acc['planters']
                    P['n'] += 1
                    P['at_wall'] += 1 if dw <= 60 else 0
                    P['with_plant'] += 1 if has else 0
                    if cols:
                        P['col_n'] += 1
                        P['at_column'] += 1 if at_col(bx) else 0
                    P['mid'] += 1 if (dw > 110 and not at_col(bx)) else 0
            # ---- 4. the wall ledges: benches, planters, urns standing up on them
            got_up = False
            for r in inside:
                fam = r['_fam'] or ('planter' if PLANTER.search(r['id'].lower()) else None)
                if fam not in LEDGE_KINDS:
                    continue
                bx = _box(r)
                if not bx or d_wall(bx) > 80:
                    continue
                up = r['p'][2] + r['b'][2] * (r.get('s') or 1) - fl
                on_ledge = LEDGE_UP[0] <= up <= LEDGE_UP[1]
                # (up on another piece of furniture is not a ledge)
                if on_ledge and any(f is not r and f['_fam'] in ('table', 'chest', 'crate', 'barrel', 'counter', 'shelf', 'cupboard')
                                    and abs(f['p'][0] - r['p'][0]) < 80 and abs(f['p'][1] - r['p'][1]) < 80 for f in floor):
                    on_ledge = False
                for acc in accs:
                    Lg = acc['ledge']
                    Lg['n'] += 1
                    Lg['kinds'][fam] += 1
                    if on_ledge:
                        Lg['up'] += 1
                        Lg['ups'].append(round(up))
                        Lg['kinds_up'][fam] += 1
                got_up = got_up or on_ledge
            for acc in accs:
                acc['ledge']['rooms'] += 1
                acc['ledge']['rooms_with'] += 1 if got_up else 0
            # ---- 5. two-storey voids: a tile with no ceiling over it, and the banners hung high in such rooms
            open_above = False
            for t in rm['_tiles']:
                over = [a for a in arch if a['p'][2] + a['b'][2] * (a.get('s') or 1) > fl + 200 and a['p'][2] + a['b'][2] * (a.get('s') or 1) < fl + 900
                        and mapdata._rotated_contains(a, t['x'], t['y'])]
                if not over:
                    open_above = True
                    break
            if open_above:
                high = [r for r in inside if BANNER.search(r['id'].lower()) and r['p'][2] + r['b'][2] * (r.get('s') or 1) > fl + 250]
                for acc in accs:
                    V = acc['void']
                    V['rooms'] += 1
                    V['with_banner'] += 1 if high else 0
                    V['banners'] += len(high)
                    V['ups'] += [round(r['p'][2] + r['b'][2] * (r.get('s') or 1) - fl) for r in high]
            # ---- 6. shelves out from the walls as dividers, and what stands on them
            shelves = [r for r in floor if r['_fam'] in ('shelf', 'bookshelf')]
            got_div = False
            for r in shelves:
                bx = _box(r)
                if not bx:
                    continue
                mid = d_wall(bx) > 110
                pots = sum(1 for o in inside if o is not r and POTS.search(o['id'].lower()) and bx[0] - 10 <= o['p'][0] <= bx[3] + 10
                           and bx[1] - 10 <= o['p'][1] <= bx[4] + 10 and bx[2] <= o['p'][2] <= bx[5] + 20)
                for acc in accs:
                    Dv = acc['dividers']
                    Dv['n'] += 1
                    Dv['mid'] += 1 if mid else 0
                    Dv['pots'] += 1 if (mid and pots >= 3) else 0
                got_div = got_div or mid
            for acc in accs:
                acc['dividers']['rooms'] += 1
                acc['dividers']['rooms_with'] += 1 if got_div else 0
    return {'cells': seen, 'styles': {st: _fold(acc) for st, acc in S.items()}}


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _share(a, b):
    return round(a / float(b), 3) if b else None


def _fold(acc):
    A, R, P, Q, Lg, V, Dv = acc['stairs'], acc['rugs'], acc['plants'], acc['planters'], acc['ledge'], acc['void'], acc['dividers']
    kinds_n = float(sum(A['kinds'].values()) or 1)
    return {'cells': acc['cells'],
            'stair_light': {'n': A['n'], 'lit': _share(A['lit'], A['n']), 'foot': _share(A['foot'], A['foot'] + A['head']),
                            'kinds': {k: round(v / kinds_n, 3) for k, v in A['kinds'].items()}, 'dist': _med(A['dist'])},
            'rugs': {'n': R['n'], 'round_share': _share(R['round'], R['n']), 'round_centred': _share(R['round_centred'], R['round']),
                     'round_under_table': _share(R['round_under_table'], R['round']), 'rect_under_table': _share(R['rect_under_table'], R['rect']),
                     'rect_by_bed': _share(R['rect_by_bed'], R['rect']), 'rect_centred': _share(R['rect_centred'], R['rect']),
                     'rooms_with': _share(R['rooms_with'], R['rooms']), 'per_room': dict(R['per_room'])},
            'plants': {'n': P['n'], 'in_planter': _share(P['in_planter'], P['n']), 'at_wall': _share(P['at_wall'], P['n']),
                       'at_column': _share(P['at_column'], P['col_plants']), 'col_seen': P['col_plants'], 'loose_mid': _share(P['loose_mid'], P['n'])},
            'planters': {'n': Q['n'], 'at_wall': _share(Q['at_wall'], Q['n']), 'at_column': _share(Q['at_column'], Q['col_n']), 'col_seen': Q['col_n'],
                         'mid': _share(Q['mid'], Q['n']), 'with_plant': _share(Q['with_plant'], Q['n'])},
            'ledge': {'n': Lg['n'], 'share': _share(Lg['up'], Lg['n']), 'height': _med(Lg['ups']), 'rooms_with': _share(Lg['rooms_with'], Lg['rooms']),
                      'kinds': {k: _share(Lg['kinds_up'][k], v) for k, v in Lg['kinds'].items() if v >= 5}},
            'void': {'rooms': V['rooms'], 'with_banner': _share(V['with_banner'], V['rooms']), 'per_room': _share(V['banners'], V['rooms']), 'height': _med(V['ups'])},
            'dividers': {'n': Dv['n'], 'share': _share(Dv['mid'], Dv['n']), 'pots': _share(Dv['pots'], max(1, Dv['mid'])),
                         'rooms_with': _share(Dv['rooms_with'], Dv['rooms'])}}


MIN = {'stair_light': 8, 'rugs': 15, 'plants': 15, 'planters': 10, 'ledge': 15, 'void': 6, 'dividers': 15}


def rule(db, which, style):
    """One catalogue rule for a style (a kit prefix like in_hlaalu, or a style label like Redoran): its
    own figures when the game has enough places in the style (MIN pieces), else the style label's (every
    Redoran kit together), else every style's; None until surveyed."""
    s = ready(db)
    if not s:
        return None
    label = mapdata.style_of((style or '') + '_room') if style and style != '*' else None
    for key in (style, label):
        own = s['styles'].get(key or '', {}).get(which) if key else None
        n = (own or {}).get('n', (own or {}).get('rooms', 0)) if own else 0
        if own and n >= MIN[which]:
            return dict(own, style=key, own=True)
    allr = s['styles'].get('*', {}).get(which)
    return dict(allr, style='*', own=False) if allr else None


def report(db):
    """For people: every rule, per style, with its rate."""
    s = survey(db)
    lines = ['%d places walked' % s['cells']]
    for st, D in sorted(s['styles'].items(), key=lambda kv: -kv[1]['cells']):
        if D['cells'] < 5 and st != '*':
            continue
        lines.append('== %s (%d places)' % (st, D['cells']))
        A = D['stair_light']
        lines.append('   stair light: %d flights, lit %s, at the foot %s, kinds %s, nearest %s' % (A['n'], A['lit'], A['foot'], A['kinds'], A['dist']))
        R = D['rugs']
        lines.append('   rugs: %d, round %s (centred %s, under a table %s); rectangular under a table %s, by a bed %s, centred %s; rooms with %s' % (
            R['n'], R['round_share'], R['round_centred'], R['round_under_table'], R['rect_under_table'], R['rect_by_bed'], R['rect_centred'], R['rooms_with']))
        P, Q = D['plants'], D['planters']
        lines.append('   plants: %d, in a planter %s, at a wall %s, at a column %s (of %d), loose mid-floor %s; planters %d: at a wall %s, at a column %s, mid %s, with a plant %s' % (
            P['n'], P['in_planter'], P['at_wall'], P['at_column'], P['col_seen'], P['loose_mid'], Q['n'], Q['at_wall'], Q['at_column'], Q['mid'], Q['with_plant']))
        Lg = D['ledge']
        lines.append('   ledges: %d wall pieces, up on a ledge %s (height %s), rooms with %s, by kind %s' % (Lg['n'], Lg['share'], Lg['height'], Lg['rooms_with'], Lg['kinds']))
        V = D['void']
        lines.append('   voids: %d rooms open above, with a high banner %s, banners per such room %s, height %s' % (V['rooms'], V['with_banner'], V['per_room'], V['height']))
        Dv = D['dividers']
        lines.append('   dividers: %d shelves, out from the walls %s (of those, with pots and jars %s), rooms with %s' % (Dv['n'], Dv['share'], Dv['pots'], Dv['rooms_with']))
    return '\n'.join(lines)
