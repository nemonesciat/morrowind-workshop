"""How the game's own, hand-made interiors compose their walls and their lighting. Three questions, asked
of 400 of the game's places (never the mod's own), room by room (furnish.rooms, as roomsurvey.py does):

1. Wall hangings (tapestries, banners, paintings, shields, trophies, racks, wall shelves, sconces): how
   many per wall length and per room, where along a wall (the middle of the wall, beside a doorway, over
   a bed or a table), how high, whether one model repeats in a room, which walls get nothing (the wall a
   bed stands against? behind a bookshelf?), how far from the nearest doorway and corner, and pairs (two
   of a kind flanking a doorway or set either side of a wall's middle).
2. Lighting: per room kind the mix of hung lanterns, sconces, standing lamps, candles on furniture,
   chandeliers and braziers; where each is (over a table, beside a door, at a bed), how high; how
   corridors and stairs are lit; each style's light models with their radius and colour.
3. Finishing touches at floor level along the walls: rugs by walls, planters, firewood by a hearth,
   barrels under a wall shelf, hooks and ropes with what hangs from them.

Kept in the cache folder once done (a few minutes); ready() runs it in the background the first time.
Auto-furnish (furnish._decorate, the hung-lights block, roomrules.lights) goes by it."""
import json
import math
import os
import re
import struct
import threading
from collections import Counter, defaultdict

import furnish
import kits
import mapdata

LIMIT = 200
HANG = re.compile(r'tapestr|banner|painting|picture|portrait|sconce|rack|trophy|plaque|shield|mask|flag|pennant|herb|hanging|antler|skull')
NOT_HANG = re.compile(r'door|window|marker|gate|rug|carpet|curtain|web|ivy|flora|railing|rail_|pole|post|burial|shutter|chain|beam|pillar|column|stair|ladder|cage|bone|blood|cobweb|moss|screen|chandelier|lantern')
HANG_KIND = (('tapestry', re.compile(r'tapestr')), ('banner', re.compile(r'banner|flag|pennant')), ('painting', re.compile(r'painting|picture|portrait')),
             ('sconce', re.compile(r'sconce')), ('rack', re.compile(r'rack')), ('shelf', re.compile(r'shelf')),
             ('trophy', re.compile(r'trophy|antler|skull|mask|plaque|shield')), ('herbs', re.compile(r'herb')))
LIGHT_KIND = (('sconce', re.compile(r'sconce')), ('chandelier', re.compile(r'chandelier')), ('lantern', re.compile(r'lantern')),
              ('brazier', re.compile(r'brazier|firepit|fire_pit|campfire|fire')), ('candle', re.compile(r'candle')),
              ('torch', re.compile(r'torch')), ('lamp', re.compile(r'lamp')))
TOUCH = (('rug', re.compile(r'rug|carpet')), ('planter', re.compile(r'planter|plant_|_plant|flora|bush|fern|_pot_|pot_0')),
         ('firewood', re.compile(r'firewood|woodpile|wood_pile|logs|_log')), ('hook', re.compile(r'hook')), ('rope', re.compile(r'rope')),
         ('barrel', re.compile(r'barrel')), ('crate', re.compile(r'crate')), ('sack', re.compile(r'sack')), ('urn', re.compile(r'urn_|_urn')),
         ('basket', re.compile(r'basket')), ('chest', re.compile(r'chest')), ('bench', re.compile(r'bench')), ('stool', re.compile(r'stool|chair')))
AT_WALL = 70                # an origin this close to a wall's inside face is at the wall
WINDOW = re.compile(r'win(dow)?(_|$|\d)')     # the kits' window props (placesurvey.WINDOW)
_cache = {}
_thread = {}
_light_recs = {}


def _kind(low, table):
    for k, pat in table:
        if pat.search(low):
            return k
    return None


def light_record(db, rid):
    """A light's radius, colour (r, g, b) and flags from its record; None when it has none."""
    low = rid.lower()
    if low in _light_recs and _light_recs[low][0] is db.recs:
        return _light_recs[low][1]
    out = None
    ri = db.resolve_id(rid)
    if ri is not None and db.recs[ri][0] == 'LIGH':
        from esm import iter_subrecords
        try:
            _t, _f, data = db.files[db.recs[ri][3]].record_at(db.recs[ri][4])
            for st, sd in iter_subrecords(data):
                if st == 'LHDT' and len(sd) >= 24:
                    _w, _v, _d, rad, r_, g_, b_, _a, fl = struct.unpack_from('<fiiiBBBBi', sd)
                    out = {'radius': rad, 'colour': (r_, g_, b_), 'flags': fl}
                    break
        except Exception:
            out = None
    _light_recs[low] = (db.recs, out)
    return out


def _disk(db, limit):
    import taste
    return taste.cache_file('wallsurvey2_%s_%d_v6' % (taste.sig(db), limit))     # (v3: hangings and posts by the stairs, planters under windows; v4: hangings over windows; v5: how planters stand together; v6: a post's foot by its box)


POST_REACH = 60


def at_post(a, px, py, reach=POST_REACH):
    """Whether a point stands at the foot of this column piece: within reach of its box, not of its origin
    (a Common wood pillar's box is 133 wide, so a planter at its face stands 102 from the origin)."""
    import fixit
    b = fixit._world_box(a)
    if not b:
        return math.hypot(a['p'][0] - px, a['p'][1] - py) < reach + 30
    dx = max(b[0] - px, 0.0, px - b[3])
    dy = max(b[1] - py, 0.0, py - b[4])
    return math.hypot(dx, dy) < reach


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); otherwise None, with the survey started in
    the background so it's there next time (while a survey for a changed taste set runs, the newest
    earlier one stands in)."""
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
        _thread['t'] = background.start('how the game hangs and lights its walls', lambda: survey(db, limit), task=('wallsurvey2', 'survey', [limit]))
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


def _lines(rm, T):
    """The room's wall lines: {(side, line coordinate): {'along': {tile along-coordinate: 'wall'|'door'|'open'},
    'off': the wall face's coordinate}}. The side is which way the wall is from the tile; the line
    coordinate is the wall face's x (E/W walls) or y (N/S walls)."""
    lines = {}
    here = {(round(t['x'] / 32), round(t['y'] / 32)) for t in rm['_tiles']}
    for t in rm['_tiles']:
        for s, (dx, dy) in furnish.STEP.items():
            kind = t['pat'][s]
            if kind == 'open':
                # an open side towards another of this room's own tiles is no wall line at all
                if (round((t['x'] + dx * T) / 32), round((t['y'] + dy * T) / 32)) in here:
                    continue
            off = t['pat']['offset'].get(s, T / 2 - 16)
            if s in ('N', 'S'):
                lc, along = t['y'] + dy * off, t['x']
            else:
                lc, along = t['x'] + dx * off, t['y']
            L = lines.setdefault((s, round(lc)), {'along': {}, 'off': lc})
            L['along'][round(along)] = kind
    return lines


def _runs(L, T):
    """The unbroken stretches of wall on a line: [(start, end)] in along-coordinates (tile edges), and the
    doorways on it: [along] (tile centres of door/open sides)."""
    cells = sorted(L['along'].items())
    runs, doors = [], []
    cur = None
    for a, kind in cells:
        if kind == 'wall':
            if cur and abs(a - T / 2 - cur[1]) < 8:
                cur[1] = a + T / 2
            else:
                cur = [a - T / 2, a + T / 2]
                runs.append(cur)
        else:
            doors.append(a)
            cur = None
    return [tuple(r) for r in runs], doors


def _survey(db, limit):
    import decorsurvey
    import roomsurvey
    H = defaultdict(lambda: {'rooms': 0, 'wall_tiles': 0, 'runs': 0, 'n': 0, 'rooms_with': 0, 'ups': defaultdict(list),
                             'centre': 0, 'tile_centre': 0, 'door_d': [], 'corner_d': [], 'over': Counter(), 'over_opening': 0,
                             'kinds': Counter(), 'models': Counter(), 'repeat_rooms': 0, 'multi_rooms': 0, 'distinct': [],
                             'pairs': Counter(), 'row_gap': [], 'walls': defaultdict(lambda: [0, 0]), 'run_len': defaultdict(lambda: [0, 0]),
                             'per_room': Counter(), 'at_door_side': 0, 'wall_share': Counter(), 'bed_wall': [0, 0],
                             'door_tile': 0, 'door_off': []})
    LT = defaultdict(lambda: {'rooms': 0, 'tiles': 0, 'n': Counter(), 'rooms_with': Counter(), 'on': defaultdict(Counter),
                              'ups': defaultdict(list), 'rel': defaultdict(Counter), 'door_d': defaultdict(list), 'per_room': defaultdict(Counter),
                              'at_wall': Counter()})
    ST = defaultdict(lambda: {'cells': 0, 'hang': Counter(), 'light': defaultdict(Counter), 'radius': defaultdict(list), 'colour': defaultdict(list)})
    CO = {'rooms': 0, 'tiles': 0, 'lights': Counter(), 'spacing': [], 'per_room': [], 'at_wall': 0, 'n': 0, 'hang': Counter(), 'hang_n': 0}
    SW = {'n': 0, 'with': 0, 'kinds': Counter(), 'dist': [],
          # (the flat hangings by a flight, within a tile and a half of it: tapestries flanking a stair;
          # a pair when one hangs either side of the flight's line; the posts standing by it)
          'hang': 0, 'hang_pair': 0, 'hang_n': [], 'hang_dist': [], 'hang_kinds': Counter(), 'posts': 0, 'post_ids': Counter()}
    WI = {'rooms': 0, 'windows': 0, 'under': Counter(), 'with_any': 0, 'rooms_with': 0, 'planters': 0, 'planters_under': 0, 'baskets': 0, 'baskets_under': 0,
          'hung_over': 0}       # (windows with a hanging on their own tile's wall: the game's rate of tapestries over windows)
    # how the game stands its planters and potted plants, per room kind: in groups of how many (within 160 of
    # one another), at what spot (a window, a post's foot, beside a doorway, by a stair, by a bench or a
    # table, a plain wall, out in the room), with what beside (a vase or urn, a lamp, loose flora), and the
    # loose flora (plants with no planter) a room holds. The user: "single potted plants in the middle of the
    # floor by the wall look garish; placed with each other, in a nook or by a window"
    PL = defaultdict(lambda: {'rooms': 0, 'tiles': 0, 'rooms_with': 0, 'n': 0, 'groups': Counter(), 'spots': Counter(), 'beside': Counter(),
                              'lone_plain': 0, 'g': 0, 'flora': 0, 'flora_groups': Counter(), 'flora_rooms': 0})
    TO = defaultdict(lambda: {'rooms': 0, 'wall_floor': Counter(), 'rooms_with': Counter(), 'under_shelf': Counter(), 'hooks': Counter(),
                              'hook_n': 0, 'hook_alone': 0, 'by_fire': Counter(), 'fires': 0, 'rug_wall': [0, 0]})
    import taste
    seen = 0
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    cells = taste.order(cells)             # (the exemplary places first, each counted several times over)
    for ck in cells:
        if seen >= limit:
            break
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        if not info['rooms'] or info['tile'] != 256:
            continue
        seen += 1
        T = info['tile']
        theme = roomsurvey.theme_of(ck)
        arch = [r for r in info['refs'] if r.get('b') and r.get('arch')]
        style = Counter(kits.kit_prefix(r['id']) for r in arch if kits.kit_prefix(r['id'])).most_common(1)
        style = style[0][0] if style else '?'
        ST[style]['cells'] += 1
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'LEVC')]
        for r in refs:
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type']) if r['type'] != 'DOOR' else None
        doors = [r for r in info['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()]
        stairs = [r for r in arch if re.search(r'stair|ramp', r['id'].lower())]
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in refs if r['type'] != 'DOOR' and rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and fl - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 400]
            floor = [r for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 40]
            kind = roomsurvey.room_kind(Counter(r['_fam'] for r in floor))
            corridor = min(rm['w'], rm['h']) == 1 and rm['tiles'] >= 3
            lines = _lines(rm, T)
            # door refs refine the doorways on each line
            runs_of, doors_of = {}, {}
            wall_tiles = 0
            for lk, L in lines.items():
                runs, dws = _runs(L, T)
                s = lk[0]
                for d in doors:
                    if not (fl - 60 <= d['p'][2] <= fl + 200):
                        continue
                    nd = (d['p'][1] if s in ('N', 'S') else d['p'][0]) - L['off']
                    al = d['p'][0] if s in ('N', 'S') else d['p'][1]
                    if abs(nd) < 48 and min(L['along']) - T / 2 <= al <= max(L['along']) + T / 2:
                        dws.append(al)
                runs_of[lk], doors_of[lk] = runs, dws
                wall_tiles += sum(1 for k in L['along'].values() if k == 'wall')

            def at_line(r):
                """The wall line this thing is at, its along-coordinate and distance from the face."""
                best = None
                for lk, L in lines.items():
                    s = lk[0]
                    nd = abs((r['p'][1] if s in ('N', 'S') else r['p'][0]) - L['off'])
                    al = r['p'][0] if s in ('N', 'S') else r['p'][1]
                    if nd < AT_WALL and min(L['along']) - T / 2 - 8 <= al <= max(L['along']) + T / 2 + 8 and (best is None or nd < best[2]):
                        best = (lk, al, nd)
                return best

            def fp(r):
                s = r.get('s') or 1.0
                return furnish._footprint([v * s for v in r['b']], r['p'][5], r['p'][0], r['p'][1])
            # ---- wall hangings
            K = H[kind]
            K['rooms'] += 1
            K['wall_tiles'] += wall_tiles
            K['runs'] += sum(len(v) for v in runs_of.values())
            # which furniture stands against each run (its origin at the wall, within the run)
            against = defaultdict(set)
            for f in floor:
                a = at_line(f)
                if not a or f['_fam'] not in ('bed', 'bookshelf', 'shelf', 'cupboard', 'table', 'chest', 'counter', 'shrine', 'bench'):
                    continue
                lk, al, _nd = a
                for run in runs_of[lk]:
                    if run[0] <= al <= run[1]:
                        against[(lk, run)].add(f['_fam'])
            hangs = []
            for r in inside:
                low = r['id'].lower()
                if r['type'] not in ('STAT', 'LIGH', 'ACTI', 'MISC') or not HANG.search(low) or NOT_HANG.search(low):
                    continue
                hk = _kind(low, HANG_KIND) or 'decor'
                b, s = r['b'], r.get('s') or 1.0
                up = r['p'][2] + b[2] * s - fl
                if hk == 'shelf' and up < 40:
                    continue                       # a shelf standing on the floor is furniture
                a = at_line(r)
                if not a:
                    continue
                lk, al, _nd = a
                run = next((ru for ru in runs_of[lk] if ru[0] - 8 <= al <= ru[1] + 8), None)
                if run is None:
                    # on a tile whose wall has a doorway cut in it (or an open side): beside the opening,
                    # on the wall either side of it
                    cell = min(lines[lk]['along'], key=lambda a_: abs(a_ - al))
                    ck_ = lines[lk]['along'][cell]
                    if ck_ == 'door':
                        K['door_tile'] += 1
                        K['door_off'].append(round(al - cell))
                        run = ('door', cell)
                    else:
                        K['over_opening'] += 1
                        continue
                hangs.append((lk, run, al, low, hk, up, r))
            if hangs:
                K['rooms_with'] += 1
            K['n'] += len(hangs)
            K['per_room'][min(len(hangs), 8)] += 1
            ST[style]['hang'].update(h[3] for h in hangs)
            if corridor:
                CO['hang'].update(h[4] for h in hangs)
                CO['hang_n'] += len(hangs)
            runs_with = Counter((h[0], h[1]) for h in hangs)
            for lk, runs in runs_of.items():
                for run in runs:
                    n_tiles = int(round((run[1] - run[0]) / T))
                    fams = against.get((lk, run), set())
                    label = 'bare' if not fams else '+'.join(sorted(fams))
                    K['walls'][label][0] += 1
                    K['walls'][label][1] += 1 if runs_with.get((lk, run)) else 0
                    K['run_len'][min(n_tiles, 6)][0] += 1
                    K['run_len'][min(n_tiles, 6)][1] += runs_with.get((lk, run), 0)
                    if 'bed' in fams:
                        K['bed_wall'][0] += 1
                        K['bed_wall'][1] += 1 if runs_with.get((lk, run)) else 0
            for lk, run, al, low, hk, up, r in hangs:
                K['kinds'][hk] += 1
                K['models'][low] += 1
                K['ups'][hk].append(round(up))
                if run[0] == 'door':
                    continue
                mid = (run[0] + run[1]) / 2
                if abs(al - mid) < 40:
                    K['centre'] += 1
                if min(abs(al - a_) for a_ in lines[lk]['along']) < 24:
                    K['tile_centre'] += 1
                dd = min((abs(al - d) for d in doors_of[lk]), default=None)
                if dd is not None:
                    K['door_d'].append(round(dd))
                    if dd < 200:
                        K['at_door_side'] += 1
                K['corner_d'].append(round(min(al - run[0], run[1] - al)))
                under = [f for f in floor if f is not r]
                over = None
                for f in under:
                    fb = fp(f)
                    if fb[0] - 16 <= r['p'][0] <= fb[2] + 16 and fb[1] - 16 <= r['p'][1] <= fb[3] + 16:
                        over = f['_fam']
                        break
                K['over'][over or 'free'] += 1
            if len(hangs) >= 2:
                K['multi_rooms'] += 1
                models = Counter(h[3] for h in hangs)
                K['distinct'].append(len(models))
                if len(models) == 1:
                    K['repeat_rooms'] += 1
                # pairs: two of one model on one line
                by_line = defaultdict(list)
                for h in hangs:
                    by_line[(h[0], h[3])].append(h)
                for (lk, low), lst in by_line.items():
                    lst.sort(key=lambda h: h[2])
                    for i in range(len(lst) - 1):
                        a1, a2 = lst[i][2], lst[i + 1][2]
                        r1, r2 = lst[i][1], lst[i + 1][1]
                        between = [d for d in doors_of[lk] if a1 < d < a2]
                        if r1[0] == 'door' and r1 == r2 and abs((r1[1] - a1) - (a2 - r1[1])) < 48:
                            K['pairs']['flank_door'] += 1          # (either side of the doorway in its own tile)
                        elif r1[0] == 'door' or r2[0] == 'door':
                            K['pairs']['door_and_wall'] += 1
                        elif between and abs((between[0] - a1) - (a2 - between[0])) < 48:
                            K['pairs']['flank_door'] += 1
                        elif lst[i][1] == lst[i + 1][1] and abs((a1 + a2) / 2 - (lst[i][1][0] + lst[i][1][1]) / 2) < 48:
                            K['pairs']['about_centre'] += 1
                        else:
                            K['pairs']['row'] += 1
                            K['row_gap'].append(round(a2 - a1))
            # ---- lighting
            LK = LT[kind]
            LK['rooms'] += 1
            LK['tiles'] += rm['tiles']
            lights = [r for r in inside if r['type'] == 'LIGH']
            room_kinds = Counter()
            shell = [r for r in arch if rm['x_min'] - 64 <= r['p'][0] <= rm['x_max'] + 64 and rm['y_min'] - 64 <= r['p'][1] <= rm['y_max'] + 64
                     and fl - 64 <= r['p'][2] <= fl + 700]
            placed = []
            for r in lights:
                low = r['id'].lower()
                lk_ = _kind(low, LIGHT_KIND) or 'other'
                p = decorsurvey.placing(db, r, rm, inside, T, all_refs=shell)
                if lk_ == 'lamp' and p['on'] == 'hung':
                    lk_ = 'hanging lamp'
                elif lk_ == 'lamp' and p['on'] != 'floor':
                    lk_ = 'lamp on furniture'
                room_kinds[lk_] += 1
                LK['n'][lk_] += 1
                LK['on'][lk_][p['on']] += 1
                LK['ups'][lk_].append(p['up'])
                a = at_line(r)
                LK['at_wall'][lk_] += 1 if a else 0
                dd = min((math.hypot(d['p'][0] - r['p'][0], d['p'][1] - r['p'][1]) for d in doors if abs(d['p'][2] - fl) < 200), default=None)
                if dd is not None:
                    LK['door_d'][lk_].append(round(dd))
                # what it is over or beside
                rel = 'free'
                for f in floor:
                    fb = fp(f)
                    if fb[0] - 12 <= r['p'][0] <= fb[2] + 12 and fb[1] - 12 <= r['p'][1] <= fb[3] + 12 and f['_fam'] in ('table', 'counter', 'bed', 'shrine', 'bookshelf', 'shelf', 'cupboard', 'chest', 'fire'):
                        rel = 'over ' + f['_fam'] if p['on'] in ('hung', 'floor') else 'on ' + f['_fam']
                        break
                if rel == 'free':
                    near = None
                    for f in floor:
                        if f['_fam'] in ('table', 'bed', 'counter', 'shrine', 'bookshelf', 'fire', 'chair', 'bench'):
                            fb = fp(f)
                            d = max(fb[0] - r['p'][0], r['p'][0] - fb[2], fb[1] - r['p'][1], r['p'][1] - fb[3], 0)
                            if d < 100 and (near is None or d < near[1]):
                                near = (f['_fam'], d)
                    if near:
                        rel = 'by ' + near[0]
                    elif dd is not None and dd < 200:
                        rel = 'by door'
                    elif a:
                        rel = 'at wall'
                LK['rel'][lk_][rel] += 1
                placed.append((r, lk_, a))
                lr = light_record(db, r['id'])
                ST[style]['light'][lk_][low] += 1
                if lr:
                    ST[style]['radius'][lk_].append(lr['radius'])
                    ST[style]['colour'][lk_].append(lr['colour'])
            for lk_, n in room_kinds.items():
                LK['rooms_with'][lk_] += 1
                LK['per_room'][lk_][min(n, 6)] += 1
            if corridor:
                CO['rooms'] += 1
                CO['tiles'] += rm['tiles']
                CO['n'] += len(lights)
                CO['per_room'].append(len(lights))
                CO['lights'].update(lk_ for _r, lk_, _a in placed)
                CO['at_wall'] += sum(1 for _r, _lk, a in placed if a)
                long_x = rm['w'] >= rm['h']
                pos = sorted(r['p'][0] if long_x else r['p'][1] for r, _lk, _a in placed)
                CO['spacing'] += [round(pos[i + 1] - pos[i]) for i in range(len(pos) - 1) if pos[i + 1] - pos[i] > 30]
            # ---- finishing touches at the walls' feet
            TK = TO[kind]
            TK['rooms'] += 1
            got = set()
            hung_shelves = [h[6] for h in hangs if h[4] == 'shelf']
            for r in inside:
                low = r['id'].lower()
                s = r.get('s') or 1.0
                up = r['p'][2] + r['b'][2] * s - fl
                tk = _kind(low, TOUCH)
                if tk in ('hook', 'rope'):
                    TK['hook_n'] += 1
                    below = [o for o in inside if o is not r and abs(o['p'][0] - r['p'][0]) < 48 and abs(o['p'][1] - r['p'][1]) < 48
                             and o['p'][2] + o['b'][5] * (o.get('s') or 1) <= r['p'][2] + r['b'][2] * s + 40 and o['p'][2] > r['p'][2] - 200]
                    if below:
                        TK['hooks'][_kind(below[0]['id'].lower(), LIGHT_KIND) or _kind(below[0]['id'].lower(), HANG_KIND) or below[0]['id'].lower()] += 1
                    else:
                        TK['hook_alone'] += 1
                    continue
                if up > 40 or not tk:
                    continue
                a = at_line(r)
                if a:
                    TK['wall_floor'][tk] += 1
                    got.add(tk)
                if tk == 'rug':
                    TK['rug_wall'][0] += 1
                    TK['rug_wall'][1] += 1 if a else 0
                for sh in hung_shelves:
                    sb = fp(sh)
                    if sb[0] - 20 <= r['p'][0] <= sb[2] + 20 and sb[1] - 20 <= r['p'][1] <= sb[3] + 20:
                        TK['under_shelf'][tk] += 1
                        break
            for tk in got:
                TK['rooms_with'][tk] += 1
            # ---- the windows: what stands at their feet (planters and baskets under the windows)
            wins = [a for a in arch if WINDOW.search(a['id'].lower()) and fl - 60 <= a['p'][2] <= fl + 300
                    and rm['x_min'] - 40 <= a['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= a['p'][1] <= rm['y_max'] + 40]
            if wins:
                WI['rooms'] += 1
                WI['windows'] += len(wins)
                any_ = False
                for w in wins:
                    under = [r for r in inside if r['_fam'] in ('planter', 'basket', 'urn', 'chest', 'bench', 'table', 'crate', 'barrel', 'sack')
                             and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 40
                             and math.hypot(r['p'][0] - w['p'][0], r['p'][1] - w['p'][1]) < T * 0.55]
                    for r in under:
                        WI['under'][r['_fam']] += 1
                    if under:
                        WI['with_any'] += 1
                        any_ = True
                    if any(abs(h[6]['p'][0] - w['p'][0]) < T * 0.45 and abs(h[6]['p'][1] - w['p'][1]) < T * 0.45 for h in hangs):
                        WI['hung_over'] += 1
                WI['rooms_with'] += 1 if any_ else 0
                for r in inside:
                    if r['_fam'] in ('planter', 'basket') and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 40:
                        WI[r['_fam'] + 's'] += 1
                        if any(math.hypot(r['p'][0] - w['p'][0], r['p'][1] - w['p'][1]) < T * 0.55 for w in wins):
                            WI[r['_fam'] + 's_under'] += 1
            # ---- planters and potted plants: how they stand together, and where
            PK = PL[kind]
            PK['rooms'] += 1
            PK['tiles'] += rm['tiles']
            planters_ = [r for r in inside if r['_fam'] == 'planter' and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 60]
            import catalogue as _cat
            cols_ = [a for a in arch if _cat.COLUMN.search(a['id'].lower()) and fl - 60 <= a['p'][2] <= fl + 200
                     and rm['x_min'] - 40 <= a['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= a['p'][1] <= rm['y_max'] + 40]
            room_doors_ = [d for d in doors if fl - 60 <= d['p'][2] <= fl + 200 and rm['x_min'] - 60 <= d['p'][0] <= rm['x_max'] + 60 and rm['y_min'] - 60 <= d['p'][1] <= rm['y_max'] + 60]
            room_stairs_ = [s for s in stairs if abs(s['p'][2] - fl) < 100 and rm['x_min'] - T <= s['p'][0] <= rm['x_max'] + T and rm['y_min'] - T <= s['p'][1] <= rm['y_max'] + T]
            wins_ = [a for a in arch if WINDOW.search(a['id'].lower()) and fl - 60 <= a['p'][2] <= fl + 300
                     and rm['x_min'] - 40 <= a['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= a['p'][1] <= rm['y_max'] + 40]
            if planters_:
                PK['rooms_with'] += 1
                PK['n'] += len(planters_)
                left_ = list(planters_)
                groups_ = []
                while left_:
                    grp_ = [left_.pop(0)]
                    i_ = 0
                    while i_ < len(grp_):
                        a_ = grp_[i_]
                        for b_ in list(left_):
                            if math.hypot(a_['p'][0] - b_['p'][0], a_['p'][1] - b_['p'][1]) <= 160:
                                grp_.append(b_)
                                left_.remove(b_)
                        i_ += 1
                    groups_.append(grp_)
                for grp_ in groups_:
                    PK['g'] += 1
                    PK['groups'][min(len(grp_), 4)] += 1
                    near_ = lambda lst, reach: any(math.hypot(a_['p'][0] - m_['p'][0], a_['p'][1] - m_['p'][1]) < reach for m_ in grp_ for a_ in lst)
                    at_w = any(at_line(m_) for m_ in grp_)
                    if near_(wins_, T * 0.55):
                        spot = 'window'
                    elif any(at_post(a_, m_['p'][0], m_['p'][1]) for m_ in grp_ for a_ in cols_):
                        spot = 'post'
                    elif near_(room_doors_, 200):
                        spot = 'door'
                    elif near_(room_stairs_, T * 1.2):
                        spot = 'stair'
                    elif near_([f for f in floor if f['_fam'] in ('bench', 'table', 'chair')], 110):
                        spot = 'seat'
                    elif at_w:
                        spot = 'plain wall'
                    else:
                        spot = 'open'
                    PK['spots'][spot] += 1
                    if len(grp_) == 1 and spot in ('plain wall', 'open'):
                        PK['lone_plain'] += 1
                    for o in inside:
                        if o in grp_ or not any(math.hypot(o['p'][0] - m_['p'][0], o['p'][1] - m_['p'][1]) < 100 for m_ in grp_):
                            continue
                        ol = o['id'].lower()
                        if o['_fam'] == 'urn' or re.search(r'vase|jug|pitcher', ol):
                            PK['beside']['vase'] += 1
                        elif o['type'] == 'LIGH' and (_kind(ol, LIGHT_KIND) in ('lamp', 'candle')) and o['p'][2] + o['b'][2] * (o.get('s') or 1) < fl + 40:
                            PK['beside']['lamp'] += 1
                        elif o['_fam'] in ('bench', 'chair', 'table', 'chest', 'basket', 'screen'):
                            PK['beside'][o['_fam']] += 1
            # loose flora: plants standing in the room with no planter under them
            flora_ = [r for r in inside if re.search(r'flora_|_plant|fern|shrub|bush|tree|ivy|flower', r['id'].lower()) and r['_fam'] != 'planter'
                      and r['type'] in ('STAT', 'ACTI') and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 60
                      and not any(abs(r['p'][0] - p_['p'][0]) < 60 and abs(r['p'][1] - p_['p'][1]) < 60 for p_ in planters_)]
            if flora_:
                PK['flora_rooms'] += 1
                PK['flora'] += len(flora_)
                left_ = list(flora_)
                while left_:
                    grp_ = [left_.pop(0)]
                    i_ = 0
                    while i_ < len(grp_):
                        a_ = grp_[i_]
                        for b_ in list(left_):
                            if math.hypot(a_['p'][0] - b_['p'][0], a_['p'][1] - b_['p'][1]) <= 160:
                                grp_.append(b_)
                                left_.remove(b_)
                        i_ += 1
                    PK['flora_groups'][min(len(grp_), 6)] += 1
            for f in floor:
                if f['_fam'] != 'fire':
                    continue
                TK['fires'] += 1
                for o in inside:
                    if o is f or math.hypot(o['p'][0] - f['p'][0], o['p'][1] - f['p'][1]) > 200:
                        continue
                    ol = o['id'].lower()
                    TK['by_fire'][o['_fam'] or _kind(ol, TOUCH) or _kind(ol, LIGHT_KIND) or ol] += 1
        # ---- stairs: the lights within a tile and a half of each flight
        for st in stairs:
            SW['n'] += 1
            near = [r for r in refs if r['type'] == 'LIGH' and math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) < T * 1.5
                    and st['p'][2] - 100 <= r['p'][2] <= st['p'][2] + 450]
            if near:
                SW['with'] += 1
                SW['kinds'].update(_kind(r['id'].lower(), LIGHT_KIND) or 'other' for r in near)
                SW['dist'].append(round(min(math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) for r in near)))
            # the flat hangings within a tile and a half of the flight, on its own level, and whether
            # they flank it (one either side of its line); the posts standing by it
            flat = [r for r in refs if r['type'] in ('STAT', 'ACTI') and _kind(r['id'].lower(), HANG_KIND) in ('tapestry', 'banner', 'painting')
                    and not NOT_HANG.search(r['id'].lower())
                    and math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) < T * 1.6 and st['p'][2] - 100 <= r['p'][2] <= st['p'][2] + 450]
            if flat:
                SW['hang'] += 1
                SW['hang_n'].append(len(flat))
                SW['hang_dist'].append(round(min(math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) for r in flat)))
                SW['hang_kinds'].update(_kind(r['id'].lower(), HANG_KIND) for r in flat)
                along_x = abs(math.sin(st['p'][5])) < 0.5
                sides = set((1 if ((r['p'][1] if along_x else r['p'][0]) > (st['p'][1] if along_x else st['p'][0])) else -1) for r in flat)
                if len(sides) == 2:
                    SW['hang_pair'] += 1
            posts = [r for r in refs if r['type'] == 'STAT' and re.search(r'post|pillar|column', r['id'].lower()) and not re.search(r'banner|rope|sign', r['id'].lower())
                     and math.hypot(r['p'][0] - st['p'][0], r['p'][1] - st['p'][1]) < T * 1.6 and st['p'][2] - 100 <= r['p'][2] <= st['p'][2] + 450]
            if len(posts) >= 2:
                SW['posts'] += 1
                SW['post_ids'].update(r['id'].lower() for r in posts)
    return _fold(seen, H, LT, ST, CO, SW, TO, WI, PL)


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _fold(seen, H, LT, ST, CO, SW, TO, WI=None, PL=None):
    out = {'cells': seen, 'hangings': {}, 'lights': {}, 'styles': {}, 'corridors': {}, 'stairs': {}, 'touches': {}, 'windows': {}, 'plants': {}}
    for kind, PK in (PL or {}).items():
        g = float(PK['g'] or 1)
        out['plants'][kind] = {'rooms': PK['rooms'], 'rooms_with': round(PK['rooms_with'] / float(PK['rooms'] or 1), 3), 'n': PK['n'], 'groups': PK['g'],
                               'groups_per_9': round(9.0 * PK['g'] / float(PK['tiles'] or 1), 3),
                               'size': {int(k): round(v / g, 3) for k, v in PK['groups'].items()}, 'spots': {k: round(v / g, 3) for k, v in PK['spots'].items()},
                               'beside': {k: round(v / g, 3) for k, v in PK['beside'].items()}, 'lone_plain': round(PK['lone_plain'] / g, 3),
                               'flora': PK['flora'], 'flora_rooms': round(PK['flora_rooms'] / float(PK['rooms'] or 1), 3),
                               'flora_groups': {int(k): v for k, v in PK['flora_groups'].items()}}
    for kind, K in H.items():
        n = float(K['n'] or 1)
        out['hangings'][kind] = {
            'rooms': K['rooms'], 'n': K['n'], 'rooms_with': round(K['rooms_with'] / max(1, K['rooms']), 2),
            'per_room': round(K['n'] / max(1, K['rooms']), 2), 'per_wall_tile': round(K['n'] / max(1, K['wall_tiles']), 3),
            'per_run': round(K['n'] / max(1, K['runs']), 2), 'count_dist': dict(sorted(K['per_room'].items())),
            'height': {hk: _med(v) for hk, v in K['ups'].items()}, 'kinds': dict(K['kinds'].most_common()),
            'models': K['models'].most_common(12),
            'centre': round(K['centre'] / n, 2), 'tile_centre': round(K['tile_centre'] / n, 2),
            'door_d': _med(K['door_d']), 'door_d_dist': dict(Counter(min(int(d // 128), 6) for d in K['door_d'])),
            'beside_door': round(K['at_door_side'] / n, 2),
            'corner_d': _med(K['corner_d']), 'corner_d_dist': dict(Counter(min(int(d // 64), 8) for d in K['corner_d'])),
            'over': dict(K['over'].most_common()), 'over_opening': K['over_opening'],
            'door_tile': K['door_tile'], 'door_off': _med([abs(o) for o in K['door_off']]),
            'door_off_dist': dict(Counter(min(int(abs(o) // 32), 5) for o in K['door_off'])),
            'repeat': round(K['repeat_rooms'] / max(1, K['multi_rooms']), 2), 'multi_rooms': K['multi_rooms'],
            'distinct': _med(K['distinct']), 'pairs': dict(K['pairs']), 'row_gap': _med(K['row_gap']),
            'walls': {lab: [v[0], round(v[1] / v[0], 2)] for lab, v in sorted(K['walls'].items(), key=lambda kv: -kv[1][0]) if v[0] >= 5},
            'bed_wall': K['bed_wall'],
            'run_len': {ln: [v[0], round(v[1] / v[0], 2)] for ln, v in sorted(K['run_len'].items())}}
    for kind, LK in LT.items():
        rooms = float(LK['rooms'] or 1)
        tiles = float(LK['tiles'] or 1)
        out['lights'][kind] = {
            'rooms': LK['rooms'], 'tiles': LK['tiles'], 'n': dict(LK['n'].most_common()),
            'per_9': {k: round(v / tiles * 9, 2) for k, v in LK['n'].items()},
            'rooms_with': {k: round(v / rooms, 2) for k, v in LK['rooms_with'].items()},
            'per_room_when': {k: round(sum(c * m for c, m in d.items()) / float(sum(d.values()) or 1), 2) for k, d in LK['per_room'].items()},
            'on': {k: dict(c.most_common()) for k, c in LK['on'].items()},
            'height': {k: _med(v) for k, v in LK['ups'].items()},
            'rel': {k: dict(c.most_common(8)) for k, c in LK['rel'].items()},
            'door_d': {k: _med(v) for k, v in LK['door_d'].items()},
            'at_wall': {k: round(LK['at_wall'][k] / float(LK['n'][k] or 1), 2) for k in LK['n']}}
    for style, S in ST.items():
        cols = {}
        for k, lst in S['colour'].items():
            if lst:
                cols[k] = [round(sum(c[i] for c in lst) / len(lst)) for i in range(3)]
        out['styles'][style] = {'cells': S['cells'], 'hang': S['hang'].most_common(10),
                                'light': {k: c.most_common(5) for k, c in S['light'].items()},
                                'radius': {k: _med(v) for k, v in S['radius'].items()}, 'colour': cols}
    out['corridors'] = {'rooms': CO['rooms'], 'tiles': CO['tiles'], 'lights': dict(CO['lights'].most_common()),
                        'per_tile': round(CO['n'] / float(CO['tiles'] or 1), 3), 'per_room': _med(CO['per_room']),
                        'rooms_lit': round(sum(1 for n in CO['per_room'] if n) / float(CO['rooms'] or 1), 2),
                        'spacing': _med(CO['spacing']), 'spacing_dist': dict(Counter(min(int(round(s / 256.0)), 6) for s in CO['spacing'])),
                        'at_wall': round(CO['at_wall'] / float(CO['n'] or 1), 2),
                        'hangings_per_tile': round(CO['hang_n'] / float(CO['tiles'] or 1), 3), 'hang_kinds': dict(CO['hang'].most_common())}
    out['stairs'] = {'n': SW['n'], 'lit': round(SW['with'] / float(SW['n'] or 1), 2), 'kinds': dict(SW['kinds'].most_common()), 'dist': _med(SW['dist']),
                     # (flights with a flat hanging within a tile and a half, how many then, a pair flanking, posts)
                     'hang': round(SW.get('hang', 0) / float(SW['n'] or 1), 2), 'hang_n': _med(SW.get('hang_n', [])), 'hang_dist': _med(SW.get('hang_dist', [])),
                     'hang_pair': round(SW.get('hang_pair', 0) / float(SW.get('hang', 0) or 1), 2), 'hang_kinds': dict(SW.get('hang_kinds', Counter()).most_common()),
                     'posts': round(SW.get('posts', 0) / float(SW['n'] or 1), 2), 'post_ids': SW.get('post_ids', Counter()).most_common(8)}
    if WI:
        out['windows'] = {'rooms': WI['rooms'], 'windows': WI['windows'], 'with_any': round(WI['with_any'] / float(WI['windows'] or 1), 2),
                          'rooms_with': round(WI['rooms_with'] / float(WI['rooms'] or 1), 2), 'under': dict(WI['under'].most_common()),
                          'planters': WI['planters'], 'planters_under': round(WI['planters_under'] / float(WI['planters'] or 1), 2),
                          'baskets': WI['baskets'], 'baskets_under': round(WI['baskets_under'] / float(WI['baskets'] or 1), 2),
                          'hung_over': round(WI['hung_over'] / float(WI['windows'] or 1), 2)}
    for kind, TK in TO.items():
        rooms = float(TK['rooms'] or 1)
        out['touches'][kind] = {'rooms': TK['rooms'], 'wall_floor': dict(TK['wall_floor'].most_common()),
                                'rooms_with': {k: round(v / rooms, 2) for k, v in TK['rooms_with'].most_common()},
                                'under_shelf': dict(TK['under_shelf'].most_common(8)),
                                'hooks': TK['hook_n'], 'hook_alone': TK['hook_alone'], 'on_hooks': TK['hooks'].most_common(10),
                                'fires': TK['fires'], 'by_fire': TK['by_fire'].most_common(10),
                                'rug_at_wall': [TK['rug_wall'][0], round(TK['rug_wall'][1] / float(TK['rug_wall'][0] or 1), 2)]}
    return out


# ------------------------------------------------------------------ what Auto-furnish asks
MIN_ROOMS = 12
HOME_KINDS = ('bedroom', 'living', 'study', 'kitchen', 'storage', 'shop', 'tavern', 'shrine', 'empty')


def _merged(s, table, purpose):
    """The entry for this room kind, or the merged home kinds when the game has too few rooms of it."""
    K = s[table].get(purpose)
    if K and K['rooms'] >= MIN_ROOMS:
        return K
    return s[table].get('living')


def hang_rule(db, purpose):
    """How the game hangs things in rooms of this kind: {'per_room', 'per_wall_tile', 'rooms_with', 'height':
    {kind: bottom above the floor}, 'centre': share at a wall's middle, 'beside_door': share within 200 of
    a doorway, 'min_door_d', 'min_corner_d', 'repeat': share of rooms with more than one whose hangings are
    one model, 'pairs': {'flank_door', 'about_centre', 'row'}, 'avoid': {furniture: how much less often the
    wall over it has a hanging than a bare wall}, 'p90': the count nine rooms in ten stay under, 'kinds':
    shares}; None while the survey runs."""
    s = ready(db)
    if not s:
        return None
    K = _merged(s, 'hangings', purpose)
    if not K:
        return None
    bare = K['walls'].get('bare', [0, 0.3])[1] or 0.3
    # {furniture: how much less often the wall over it carries a hanging than a bare wall} (the bed's
    # wall two times in five, a cupboard's one in two, a shrine's seven in ten)
    avoid = {}
    for lab, (n, share) in K['walls'].items():
        if lab == 'bare' or '+' in lab or n < 8:
            continue
        if share < 0.8 * bare:
            avoid[lab] = round(1 - share / bare, 2)
    n = float(K['n'] or 1)
    # the count nine rooms in ten stay under (a living room 5, a bedroom 7, a study 8)
    acc, p90 = 0, 8
    for c, m in sorted((int(c), m) for c, m in K['count_dist'].items()):
        acc += m
        if acc >= 0.9 * K['rooms']:
            p90 = c
            break
    return {'per_room': K['per_room'], 'per_wall_tile': K['per_wall_tile'], 'rooms_with': K['rooms_with'], 'count_dist': K['count_dist'], 'p90': p90,
            'height': K['height'], 'centre': K['centre'], 'beside_door': K['beside_door'],
            'min_door_d': 128 if (K['door_d_dist'].get(0, 0) / n) < 0.1 else 64,
            'min_corner_d': 64 if (K['corner_d_dist'].get(0, 0) / n) < 0.1 else 32,
            'repeat': K['repeat'], 'pairs': K['pairs'], 'avoid': avoid, 'kinds': {k: round(v / n, 2) for k, v in K['kinds'].items()},
            'door_share': round(K['door_tile'] / n, 2), 'door_off': K['door_off'] if K['door_tile'] >= 10 else None,
            'over': {k: round(v / n, 2) for k, v in K['over'].items()}, 'rooms': K['rooms']}


def light_rule(db, purpose):
    """How the game lights rooms of this kind: {'per_9': {kind: per 3 x 3 tiles}, 'rooms_with': {kind: share},
    'per_room_when': {kind: how many when any}, 'height': {kind: bottom up}, 'rel': {kind: {where: share}},
    'at_wall': {kind: share}}; None while the survey runs."""
    s = ready(db)
    if not s:
        return None
    K = _merged(s, 'lights', purpose)
    if not K:
        return None
    rel = {}
    for k, c in K['rel'].items():
        t = float(sum(c.values()) or 1)
        rel[k] = {w: round(v / t, 2) for w, v in c.items()}
    return {'per_9': K['per_9'], 'rooms_with': K['rooms_with'], 'per_room_when': K['per_room_when'], 'height': K['height'],
            'rel': rel, 'at_wall': K['at_wall'], 'door_d': K['door_d'], 'rooms': K['rooms']}


def corridor_rule(db):
    """How the game lights its corridors (rooms one tile wide): {'per_tile', 'spacing' (units along the
    corridor), 'kinds': shares, 'rooms_lit'}; None while the survey runs or when few were seen."""
    s = ready(db)
    if not s or s['corridors'].get('rooms', 0) < MIN_ROOMS:
        return None
    C = s['corridors']
    t = float(sum(C['lights'].values()) or 1)
    return {'per_tile': C['per_tile'], 'spacing': C['spacing'], 'kinds': {k: round(v / t, 2) for k, v in C['lights'].items()},
            'rooms_lit': C['rooms_lit'], 'at_wall': C['at_wall'], 'hangings_per_tile': C['hangings_per_tile']}


def plant_rule(db, purpose):
    """How the game stands planters in rooms of this kind (the merged home kinds when it has too few):
    {'groups_per_9', 'rooms_with', 'size': {1: share, 2:, 3:, 4:}, 'spots': {'window', 'post', 'door',
    'stair', 'seat', 'plain wall', 'open'}, 'beside': {'vase', 'lamp', 'bench', ...: per group}, 'lone_plain':
    share of groups that are one planter at a plain wall or in the open, 'flora_rooms', 'flora_groups'};
    None while the survey runs."""
    s = ready(db)
    if not s or not s.get('plants'):
        return None
    K = s['plants'].get(purpose)
    if not K or K['rooms'] < MIN_ROOMS or K['groups'] < 10:
        K = s['plants'].get('living')
    return K


def style_lights(db, prefix):
    """The light models a style's places use, by kind, with radius and colour; None when the style was
    not seen."""
    s = ready(db)
    if not s:
        return None
    return s['styles'].get(prefix)


def report(db):
    """For people: the survey in words."""
    s = survey(db)
    out = ['%d places walked' % s['cells']]
    for kind, K in sorted(s['hangings'].items(), key=lambda kv: -kv[1]['rooms']):
        out.append('hangings, %s (%d rooms): %d; in %d%% of rooms, %.2f per room, %.3f per wall tile; kinds %s; heights %s; at a wall middle %d%%, '
                   'at a tile middle %d%%, beside a door %d%%, door distance %s, corner distance %s; over %s; on a door tile %d (off the doorway %s, %s); '
                   'over an open side %d; one model %d%% of %d rooms with 2+ (distinct %s); count %s; pairs %s, row gap %s; walls %s; run length %s'
                   % (kind, K['rooms'], K['n'], K['rooms_with'] * 100, K['per_room'], K['per_wall_tile'], K['kinds'], K['height'], K['centre'] * 100,
                      K['tile_centre'] * 100, K['beside_door'] * 100, K['door_d'], K['corner_d'], K['over'], K['door_tile'], K['door_off'], K['door_off_dist'],
                      K['over_opening'], K['repeat'] * 100, K['multi_rooms'], K['distinct'], K['count_dist'], K['pairs'], K['row_gap'], K['walls'], K['run_len']))
    for kind, L in sorted(s['lights'].items(), key=lambda kv: -kv[1]['rooms']):
        out.append('lights, %s (%d rooms, %d tiles): %s; per 9 tiles %s; rooms with %s; when any %s; on %s; heights %s; relative %s; at wall %s; door %s'
                   % (kind, L['rooms'], L['tiles'], L['n'], L['per_9'], L['rooms_with'], L['per_room_when'], L['on'], L['height'], L['rel'], L['at_wall'], L['door_d']))
    out.append('corridors: %s' % s['corridors'])
    out.append('stairs: %s' % s['stairs'])
    out.append('windows: %s' % s.get('windows'))
    for kind, P in sorted((s.get('plants') or {}).items(), key=lambda kv: -kv[1]['rooms']):
        out.append('plants, %s: %s' % (kind, P))
    for kind, Tk in sorted(s['touches'].items(), key=lambda kv: -kv[1]['rooms']):
        out.append('touches, %s: %s' % (kind, Tk))
    for st, S in sorted(s['styles'].items(), key=lambda kv: -kv[1]['cells']):
        out.append('style %s (%d places): hangings %s; lights %s; radius %s; colour %s' % (st, S['cells'], S['hang'], S['light'], S['radius'], S['colour']))
    return out
