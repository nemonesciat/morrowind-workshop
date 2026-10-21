"""How the game's own, hand-made interiors are furnished: what a room of each kind holds (a bedroom: a
bed, a chest, a stool, seldom a table), where things stand (against a wall, in a corner, in the
middle), and how furniture stands relative to other furniture (a chair pulled up to a table, a chest
at the foot of a bed, a candle on the table). Auto-furnish goes by it instead of hand-written recipes.

A room's kind is told from what's in it (the game names places, not rooms): a bed makes a bedroom, a
counter a shop, bookshelves a study, cooking a kitchen, many seats round tables a tavern."""
import math
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata

_cache = {}
# furniture that stands on the floor, by family (see furnish.FAMILIES), and the small things on it
FLOOR_KINDS = ('bed', 'table', 'chair', 'bench', 'bookshelf', 'shelf', 'cupboard', 'chest', 'crate', 'barrel',
               'sack', 'urn', 'rug', 'counter', 'shrine', 'bedroll', 'fire')
TOP_KINDS = ('dish', 'bottle', 'book', 'food', 'candle')
# which pairs to measure: (thing, what it stands by)
THEMES = {'tavern': ('tavern', 'inn', 'cornerclub', 'corner club', 'club', 'tradehouse', 'bar'),
          'shop': ('trader', 'shop', 'smith', 'outfitter', 'apothecary', 'alchemist', 'bookseller', 'clothier',
                   'armorer', 'pawnbroker', 'general', 'store'),
          'temple': ('temple', 'shrine', 'chapel', 'monastery'),
          'guild': ('guild', 'legion', 'fort', 'barracks', 'council', 'manor hall'),
          'manor': ('manor', 'estate', 'plantation', 'palace')}
PAIRS = (('chair', 'table'), ('bench', 'table'), ('chest', 'bed'), ('cupboard', 'bed'), ('candle', 'table'),
         ('table', 'bed'), ('chair', 'bed'), ('urn', 'shrine'), ('bench', 'shrine'), ('chest', 'counter'),
         ('crate', 'barrel'), ('sack', 'crate'))
# floor clutter that the game stands in groups (a heap of crates and sacks in a corner)
CLUTTER = ('crate', 'barrel', 'sack', 'urn')
LINK = 160               # two pieces of clutter this close (origin to origin) are in one group
HEARTH_EXAMPLES = 30     # hearth dressings kept per fireplace model
LIMIT = 200              # places walked (was 400: the whole queue of surveys has to finish in minutes)
# furniture people stand at (the trader behind the counter, the publican by the bar, the owner at the table)
PEOPLE_BY = ('counter', 'table', 'bed', 'shrine', 'bookshelf', 'shelf', 'chair', 'bench', 'fire', 'chest', 'cupboard', 'barrel', 'crate')
_theme_re = {}


def theme_of(name):
    """The kind of place a cell name says it is (a tavern, a shop, a temple, a guild, a manor), else
    'house'. Whole words only: "bar" is not "barracks", "store" is not "storeroom"."""
    if not _theme_re:
        for t, words in THEMES.items():
            _theme_re[t] = re.compile(r'(^|[^a-z])(%s)([^a-z]|$)' % '|'.join(re.escape(w) for w in words))
    low = (name or '').lower()
    for t in THEMES:
        if _theme_re[t].search(low):
            return t
    return 'house'


_classes = {}


def class_of(db, rid):
    """An NPC's class (the ID in its record), or ''."""
    low = rid.lower()
    if low in _classes and _classes[low][0] is db.recs:
        return _classes[low][1]
    cls = ''
    ri = db.resolve_id(rid)
    if ri is not None and db.recs[ri][0] == 'NPC_':
        from esm import iter_subrecords, zstr
        try:
            _t, _f, data = db.files[db.recs[ri][3]].record_at(db.recs[ri][4])
            cls = next((zstr(sd) for st, sd in iter_subrecords(data) if st == 'CNAM'), '')
        except Exception:
            cls = ''
    _classes[low] = (db.recs, cls)
    return cls


def family_of(db, rid, tag):
    low = rid.lower()
    for k, (words, types) in furnish.FAMILIES.items():
        if tag not in types or not furnish._named(low, words):
            continue
        if any(w in low for w in furnish.NOT.get(k, ())) or 'marker' in low:
            continue
        return k
    return None


def room_kind(counts):
    """The kind of room, from what's in it."""
    c = counts
    if c['bed'] or c['bedroll'] >= 2:
        return 'bedroom'
    if c['counter'] and c['table'] >= 2 and c['chair'] + c['bench'] >= 4:
        return 'tavern'                 # (a bar with tables and seats round it)
    if c['counter']:
        return 'shop'
    if c['shrine']:
        return 'shrine'
    if c['bookshelf'] >= 2 or (c['bookshelf'] and c['table']):
        return 'study'
    # (a hearth with stores by it is a kitchen; a hearth alone warms a living room or a bedroom)
    if (c['fire'] and c['barrel'] + c['sack'] + c['crate'] + c['urn'] >= 2) or (c['barrel'] + c['sack'] >= 3 and c['table']):
        return 'kitchen'
    if c['table'] >= 2 and c['chair'] + c['bench'] >= 4:
        return 'tavern'
    if c['crate'] + c['barrel'] + c['sack'] + c['urn'] >= 3 and not c['table'] and not c['chair']:
        return 'storage'
    if sum(c.values()) == 0:
        return 'empty'
    return 'living'


def _local(dx, dy, rz):
    c, s = math.cos(rz), math.sin(rz)
    return dx * c - dy * s, dx * s + dy * c


def _disk(db, limit):
    """Where a finished survey is kept between runs (it takes a few minutes): the Workshop's cache folder,
    one file per load order (and per taste set: taste.py)."""
    import taste
    return taste.cache_file('roomsurvey_%s_%d_v6' % (taste.sig(db), limit))


def _load(path):
    import json
    with open(path, encoding='utf-8') as f:
        saved = json.load(f)
    saved['pairs'] = {tuple(k.split('|')): v for k, v in saved['pairs'].items()}
    saved['tops'] = {tuple(k.split('|')): v for k, v in saved['tops'].items()}
    saved['containers'] = {tuple(k.split('|')): v for k, v in saved.get('containers', {}).items()}
    return saved


_thread = {}


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); otherwise None, with the survey started in
    the background so it's there next time (it takes a few minutes the first time). While a survey for
    a changed taste set runs, the newest earlier one stands in."""
    import os
    import threading
    import taste
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
        _thread['t'] = background.start('what the game puts in each kind of room', lambda: survey(db, limit), task=('roomsurvey', 'survey', [limit]))
    return taste.stale(_cache, key, db.recs, _disk(db, limit), _load)


def survey(db, limit=LIMIT):
    """Walk the game's interiors built from kit pieces, room by room (kept on disk once done)."""
    import json
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db, limit)
        saved = _load(path)
        _cache[key] = (db.recs, saved)
        return saved
    except Exception:
        pass
    out = _survey(db, limit)
    _cache[key] = (db.recs, out)
    if path:
        try:
            flat = dict(out, pairs={'|'.join(k): v for k, v in out['pairs'].items()}, tops={'|'.join(k): v for k, v in out['tops'].items()},
                        containers={'|'.join(k): v for k, v in out['containers'].items()})
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(flat, f)
        except Exception:
            pass
    return out


def one(db, cell_key):
    """The survey of a single place (for "Furnish likeâ€¦": its rooms as the model), the same shape as the
    whole survey's; its 'kinds' hold only the kinds of room the place has."""
    return _survey(db, 1, cells=[cell_key])


def _fp_area(r):
    b, s = r['b'], r.get('s') or 1.0
    return (b[3] - b[0]) * (b[4] - b[1]) * s * s


def _survey(db, limit, cells=None):
    import arrangesurvey
    import taste
    kinds = defaultdict(lambda: {'rooms': 0, 'tiles': [], 'have': Counter(), 'count': Counter(), 'where': defaultdict(Counter),
                                 'lights': Counter(), 'light_n': [], 'light_ids': Counter(), 'tile_sum': 0, 'cover': [],
                                 'extra': Counter(), 'all_n': []})
    pairs = defaultdict(list)
    tops = defaultdict(Counter)          # what stands on a table/counter/shelf by family
    # the layout: how many rooms a place has, how big a room of each kind is, which kinds touch, and
    # where in a shared wall the doorway sits
    layout = {'rooms_per_cell': [], 'size': defaultdict(list), 'touch': Counter(), 'doors_per_room': defaultdict(list),
              'door_along': [], 'themes': defaultdict(list)}
    # floor clutter in groups: nearest-neighbour distances, group sizes, where groups stand
    cl = {'nn': defaultdict(list), 'nn_any': [], 'sizes': Counter(), 'mixed': 0, 'n': 0, 'where': Counter(), 'combos': Counter(),
          'per_room': [], 'rooms': 0}
    # which container models stand in rooms of each kind, in places of each theme (by family)
    conts = defaultdict(Counter)
    # what the game stands at its hearths (a cooking pot, a kettle, firewood, a bellows, a bucket): per
    # fireplace model, dressings of the small things within reach of it, in the hearth's own frame
    hearths = defaultdict(list)
    # where people stand: (room kind, theme, class, by what furniture, offset in its frame, turn, by a door)
    people = []
    seen = 0
    given = cells is not None
    if cells is None:
        cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                       and lst[-1] not in db.dead and kits.game_made(db, k))
        cells = taste.order(cells)             # (the exemplary places first, each counted several times over)
    for ck in cells:
        if seen >= limit:
            break
        try:
            info = furnish.rooms(db, ck, trace=given)
        except Exception:
            continue
        # (a place named as the model ("Furnish like") is read even when its floor had to be traced in
        # finer tiles; its tile counts are scaled to the kit's 256-unit tiles below)
        if not info['rooms'] or info['tile'] not in ((256, furnish.FLOOR_T) if given else (256,)):
            continue
        seen += 1
        T = info['tile']
        tk = (T / 256.0) ** 2
        for rm in info['rooms']:
            rm['tiles'] = max(1, int(round(rm['tiles'] * tk))) if tk != 1 else rm['tiles']
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in refs:
            r['_fam'] = family_of(db, r['id'], r['type'])
            # (the set pieces' other kinds too: lamps, planters, baskets, pillows... the whole count of
            # what stands in a room, for the density Auto-furnish aims at)
            r['_xfam'] = arrangesurvey.family(db, r['id'], r['type']) or r['_fam']
        layout['rooms_per_cell'].append(len(info['rooms']))
        # the kind of place, from its name (a tavern, a shop, a temple, a guild): which rooms it has
        theme = theme_of(ck)
        layout['themes'][theme].append(None)
        doors = [r for r in info['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()]
        npcs = [r for r in info['refs'] if r['type'] == 'NPC_']
        room_kinds = {}
        for rm in info['rooms']:
            H = 300
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and rm['floor'] - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= rm['floor'] + H]
            floor = [r for r in inside if r['_fam'] in FLOOR_KINDS]
            counts = Counter(r['_fam'] for r in floor)
            kind = room_kind(counts)
            room_kinds[rm['id']] = kind
            K = kinds[kind]
            K['rooms'] += 1
            K['tiles'].append(rm['tiles'])
            K['tile_sum'] += rm['tiles']
            # how full the room is: the floor furniture's footprints over the floor (rugs out), and
            # how many things of every kind stand on it, per nine tiles
            K['cover'].append(sum(_fp_area(r) for r in floor if r['_fam'] != 'rug') / float(rm['tiles'] * 256 * 256))
            xs = [r for r in inside if r.get('_xfam') and r['_fam'] not in FLOOR_KINDS and r['_fam'] not in TOP_KINDS]
            K['all_n'].append((len(floor) + len(xs), rm['tiles']))
            for r in xs:
                K['extra'][r['_xfam']] += 1
            layout['size'][kind].append((rm['w'], rm['h'], rm['tiles']))
            # doorways on this room's edge: how many, and how far along the wall (0 = a corner, 0.5 = the middle)
            mine = []
            for d in doors:
                if not (rm['floor'] - 60 <= d['p'][2] <= rm['floor'] + 200):
                    continue
                x, y = d['p'][0], d['p'][1]
                on_x = min(abs(x - rm['x_min']), abs(x - rm['x_max'])) < 40 and rm['y_min'] - 20 <= y <= rm['y_max'] + 20
                on_y = min(abs(y - rm['y_min']), abs(y - rm['y_max'])) < 40 and rm['x_min'] - 20 <= x <= rm['x_max'] + 20
                if on_x or on_y:
                    mine.append(d)
                    span = (rm['y_max'] - rm['y_min']) if on_x else (rm['x_max'] - rm['x_min'])
                    along = ((y - rm['y_min']) if on_x else (x - rm['x_min'])) / span if span else 0.5
                    if span >= T * 2:
                        layout['door_along'].append(round(min(along, 1 - along), 2))
            layout['doors_per_room'][kind].append(len({(round(d['p'][0] / 64), round(d['p'][1] / 64)) for d in mine}))
            for fam, n in counts.items():
                K['have'][fam] += 1
                K['count'][fam] += n
            # where each thing stands: by a wall, in a corner, or out in the room
            for r in floor:
                dx = min(r['p'][0] - rm['x_min'], rm['x_max'] - r['p'][0])
                dy = min(r['p'][1] - rm['y_min'], rm['y_max'] - r['p'][1])
                near = sum(1 for d in (dx, dy) if d < T * 0.35)
                K['where'][r['_fam']]['corner' if near == 2 else 'wall' if near == 1 else 'middle'] += 1
            # pairs: a thing and the nearest of what it stands by, in that one's own frame
            for a_kind, b_kind in PAIRS:
                bs = [r for r in floor if r['_fam'] == b_kind]
                if not bs:
                    continue
                for a in (r for r in floor if r['_fam'] == a_kind):
                    b = min(bs, key=lambda r: math.hypot(r['p'][0] - a['p'][0], r['p'][1] - a['p'][1]))
                    d = math.hypot(b['p'][0] - a['p'][0], b['p'][1] - a['p'][1])
                    if d > 400:
                        continue
                    lx, ly = _local(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1], b['p'][5])
                    dq = int(round(((a['p'][5] - b['p'][5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                    pairs[(a_kind, b_kind)].append((round(lx), round(ly), round(a['p'][2] - b['p'][2]), dq, a['id'], b['id']))
            # lights: how many a room has for its size, and where they are (on the floor, on furniture,
            # up on a wall or the ceiling)
            lights = [r for r in inside if r['type'] == 'LIGH']
            K['light_n'].append((len(lights), rm['tiles']))
            for r in lights:
                up = r['p'][2] + r['b'][2] * (r.get('s') or 1) - rm['floor']
                K['lights'][('floor' if up < 20 else 'furniture' if up < 130 else 'wall' if up < 230 else 'ceiling')] += 1
                K['light_ids'][r['id']] += 1
            # what sits on tables and counters, by room kind
            for r in inside:
                if r['_fam'] in TOP_KINDS or (r['type'] in mapdata.ITEM_TYPES and r['_fam'] is None):
                    under = [f for f in floor if f['_fam'] in ('table', 'counter', 'shelf', 'bookshelf', 'cupboard')
                             and abs(f['p'][0] - r['p'][0]) < 120 and abs(f['p'][1] - r['p'][1]) < 120 and 0 < r['p'][2] - f['p'][2] < 200]
                    if under:
                        tops[(kind, under[0]['_fam'])][r['_fam'] or r['type']] += 1
            # the containers the game stands here (their contents are the record's: see containersurvey.py)
            for r in floor:
                if r['type'] == 'CONT':
                    conts[(r['_fam'], kind, theme)][r['id']] += 1
            # the hearths: what stands within reach of each (not furniture, not another hearth)
            for f in floor:
                if f['_fam'] != 'fire' or len(hearths[f['id'].lower()]) >= HEARTH_EXAMPLES:
                    continue
                fs = f.get('s') or 1.0
                items = []
                for o in inside:
                    if o is f or o['_fam'] in FLOOR_KINDS or o['type'] in ('LIGH',) and 'fire' in o['id'].lower():
                        continue
                    ob = o['b']
                    if max(ob[3] - ob[0], ob[4] - ob[1]) * (o.get('s') or 1) > 110:
                        continue
                    dx, dy = o['p'][0] - f['p'][0], o['p'][1] - f['p'][1]
                    if math.hypot(dx, dy) > 170 or not (-30 <= o['p'][2] - f['p'][2] <= 140):
                        continue
                    lx, ly = _local(dx, dy, f['p'][5])
                    items.append([o['id'], round(lx / fs, 1), round(ly / fs, 1), round((o['p'][2] - f['p'][2]) / fs, 1),
                                  round((o['p'][5] - f['p'][5]) % (2 * math.pi), 3), round(o.get('s') or 1.0, 3), o['type']])
                hearths[f['id'].lower()].append({'cell': ck, 'kind': kind, 'items': items})
            # floor clutter in groups: how far apart, how many to a group, in a corner or along a wall
            clut = [r for r in floor if r['_fam'] in CLUTTER]
            if clut:
                cl['rooms'] += 1
                cl['per_room'].append(len(clut))
                _groups(clut, rm, T, cl)
            # people: by what furniture each stands, and where in its frame
            for n_ in npcs:
                if not (rm['x_min'] <= n_['p'][0] <= rm['x_max'] and rm['y_min'] <= n_['p'][1] <= rm['y_max']
                        and rm['floor'] - 60 <= n_['p'][2] <= rm['floor'] + 200):
                    continue
                by = [f for f in floor if f['_fam'] in PEOPLE_BY]
                b = min(by, key=lambda f: math.hypot(f['p'][0] - n_['p'][0], f['p'][1] - n_['p'][1])) if by else None
                d = math.hypot(b['p'][0] - n_['p'][0], b['p'][1] - n_['p'][1]) if b else None
                door_d = min((math.hypot(dr['p'][0] - n_['p'][0], dr['p'][1] - n_['p'][1]) for dr in doors), default=None)
                if b and d <= 300:
                    lx, ly = _local(n_['p'][0] - b['p'][0], n_['p'][1] - b['p'][1], b['p'][5])
                    dq = int(round(((n_['p'][5] - b['p'][5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                    people.append([kind, theme, class_of(db, n_['id']), b['_fam'], round(lx), round(ly), dq, round(d), b['id'],
                                   round(door_d) if door_d is not None else None])
                else:
                    people.append([kind, theme, class_of(db, n_['id']), None, None, None, None, None, None,
                                   round(door_d) if door_d is not None else None])
        layout['themes'][theme][-1] = Counter(room_kinds.values())
        # which kinds of room touch (share an edge)
        rl = info['rooms']
        for i, a in enumerate(rl):
            for b in rl[i + 1:]:
                if abs(a['floor'] - b['floor']) > 64:
                    continue
                gap_x = max(a['x_min'], b['x_min']) - min(a['x_max'], b['x_max'])
                gap_y = max(a['y_min'], b['y_min']) - min(a['y_max'], b['y_max'])
                if (abs(gap_x) < 8 and gap_y < -T * 0.5) or (abs(gap_y) < 8 and gap_x < -T * 0.5):
                    layout['touch'][tuple(sorted((room_kinds[a['id']], room_kinds[b['id']])))] += 1
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    n_groups = max(1, cl['n'])
    clusters = {'link': LINK, 'rooms_with': cl['rooms'], 'per_room': med(cl['per_room']),
                'nn': {f: med(v) for f, v in cl['nn'].items() if len(v) >= 5}, 'nn_any': med(cl['nn_any']),
                'sizes': [[s, round(n / n_groups, 2)] for s, n in sorted(cl['sizes'].items())],
                'mixed': round(cl['mixed'] / n_groups, 2),
                'where': {w: round(n / n_groups, 2) for w, n in cl['where'].items()},
                'combos': [['+'.join(k), n] for k, n in cl['combos'].most_common(10)], 'groups': cl['n']}
    out = {'cells': seen, 'kinds': {}, 'pairs': {}, 'tops': {k: v.most_common(8) for k, v in tops.items()},
           'clusters': clusters, 'containers': {k: v.most_common(12) for k, v in conts.items()}, 'people': people,
           'hearths': dict(hearths),
           'layout': {'rooms_per_cell': med(layout['rooms_per_cell']),
                      'rooms_per_cell_dist': Counter(min(n, 8) for n in layout['rooms_per_cell']).most_common(),
                      'size': {k: {'w': med([s[0] for s in v]), 'h': med([s[1] for s in v]), 'tiles': med([s[2] for s in v]),
                                   'one_wide': round(sum(1 for s in v if min(s[0], s[1]) == 1) / len(v), 2)}
                               for k, v in layout['size'].items() if v},
                      'touch': layout['touch'].most_common(12),
                      'doors_per_room': {k: round(sum(v) / len(v), 2) for k, v in layout['doors_per_room'].items() if v},
                      'door_along': Counter(round(a * 4) / 4 for a in layout['door_along']).most_common()}}
    out['layout']['touch'] = [['|'.join(k), n] for k, n in out['layout']['touch']]
    # themes: how many places of each kind, and the share of them with each kind of room, with the
    # typical count in the places that have one
    themes = {}
    for theme, lst in layout['themes'].items():
        lst = [c for c in lst if c is not None]
        n = len(lst)
        if not n:
            continue
        have = Counter()
        count = Counter()
        for c in lst:
            for k, v in c.items():
                have[k] += 1
                count[k] += v
        themes[theme] = {'places': n, 'rooms_per_place': round(sum(sum(c.values()) for c in lst) / n, 1),
                         'rooms': {k: [round(have[k] / n, 2), round(count[k] / have[k], 1)] for k in have if have[k] >= 3}}
    out['layout']['themes'] = themes
    for kind, K in kinds.items():
        n = K['rooms']
        tiles = sorted(K['tiles'])
        ts = float(K['tile_sum'] or 1)
        cov = sorted(K['cover'])
        out['kinds'][kind] = {
            'rooms': n, 'tiles': tiles[len(tiles) // 2] if tiles else 0, 'tile_sum': K['tile_sum'],
            'have': {f: round(K['have'][f] / n, 2) for f in K['have']},
            'per_room': {f: round(K['count'][f] / n, 2) for f in K['count']},
            # per nine tiles (a 3 x 3 room), over every tile of every room of the kind: what Auto-furnish
            # aims at, scaled by a room's own size
            'per_9': {f: round(K['count'][f] / ts * 9, 3) for f in K['count']},
            'extra_per_9': {f: round(K['extra'][f] / ts * 9, 3) for f in K['extra']},
            'cover': round(cov[len(cov) // 2], 3) if cov else 0,
            'all_per_9': round(sum(a for a, _t in K['all_n']) / ts * 9, 2),
            'where': {f: dict(w) for f, w in K['where'].items()},
            # lights per 9 tiles (a 3 x 3 room), where they are, and the ones used most
            'lights_per_9': round(sum(ln for ln, _t in K['light_n']) / max(1, sum(t for _l, t in K['light_n'])) * 9, 2),
            'lights_where': dict(K['lights']), 'light_ids': K['light_ids'].most_common(6)}
    for pk, lst in pairs.items():
        if len(lst) < 5:
            continue
        xs = sorted(abs(p[0]) for p in lst)
        ys = sorted(abs(p[1]) for p in lst)
        dists = sorted(math.hypot(p[0], p[1]) for p in lst)
        sides = Counter('x' if abs(p[0]) >= abs(p[1]) else 'y' for p in lst)
        turns = Counter(p[3] for p in lst)
        out['pairs'][pk] = {'n': len(lst), 'dist': dists[len(dists) // 2], 'along_x': round(sides['x'] / len(lst), 2),
                            'dx': xs[len(xs) // 2], 'dy': ys[len(ys) // 2], 'turn': turns.most_common(2),
                            'facing': round(sum(1 for p in lst if p[3] in (0, 2)) / len(lst), 2)}
    return out


def _groups(clut, rm, T, cl):
    """Group this room's floor clutter (crates, barrels, sacks, urns): pieces within LINK of each other
    are one group. Adds to cl: nearest-neighbour distances (same family, any family), group sizes, how
    many groups mix families, where each group stands."""
    n = len(clut)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        a = clut[i]
        best_same, best_any = None, None
        for j in range(n):
            if i == j:
                continue
            b = clut[j]
            d = math.hypot(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1])
            if d <= LINK:
                parent[find(i)] = find(j)
            best_any = d if best_any is None else min(best_any, d)
            if a['_fam'] == b['_fam']:
                best_same = d if best_same is None else min(best_same, d)
        if best_same is not None:
            cl['nn'][a['_fam']].append(round(best_same))
        if best_any is not None:
            cl['nn_any'].append(round(best_any))
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(clut[i])
    for g in groups.values():
        cl['n'] += 1
        cl['sizes'][min(len(g), 8)] += 1
        fams = Counter(r['_fam'] for r in g)
        if len(fams) > 1:
            cl['mixed'] += 1
        cl['combos'][tuple(sorted(fams))] += 1
        near = []
        for r in g:
            dx = min(r['p'][0] - rm['x_min'], rm['x_max'] - r['p'][0])
            dy = min(r['p'][1] - rm['y_min'], rm['y_max'] - r['p'][1])
            near.append(sum(1 for d in (dx, dy) if d < T * 0.35))
        cl['where']['corner' if max(near) == 2 else 'wall' if max(near) == 1 else 'middle'] += 1


def hearth_dressing(db, rid, rng, kind=None):
    """One of the game's own dressings of this hearth model (what stands within reach of it: a cooking
    pot, a kettle, firewood, a bucket, a bellows), in the hearth's own frame: [[id, x, y, z, rz, s,
    type], ...]; a dressing from a room of this kind when the game has three or more; any hearth's when
    the model was never seen with anything. None until the survey is done or when the game stands
    nothing at its hearths."""
    s = ready(db)
    H = (s or {}).get('hearths')
    if not H:
        return None
    pool = [d for d in H.get(rid.lower(), []) if d['items']]
    if len(pool) < 2:
        pool = [d for lst in H.values() for d in lst if d['items']]
    if not pool:
        return None
    if kind:
        own = [d for d in pool if d['kind'] == kind]
        if len(own) >= 3:
            pool = own
    a, b = rng.choice(pool), rng.choice(pool)
    return (max(a, b, key=lambda d: len(d['items'])) if rng.random() < 0.6 else a)['items']


def themes_report(db):
    """For people: what a tavern, a shop, a temple, a guild and a manor contain, in words."""
    s = survey(db)
    out = []
    for theme, d in sorted(s['layout'].get('themes', {}).items(), key=lambda kv: -kv[1]['places']):
        rooms = ', '.join('%s %d%% (x%.1f)' % (k, round(v[0] * 100), v[1]) for k, v in sorted(d['rooms'].items(), key=lambda kv: -kv[1][0]))
        out.append('%s: %d places, %.1f rooms each: %s' % (theme, d['places'], d['rooms_per_place'], rooms))
    return out


def recipe(db, kind):
    """What a room of this kind gets, from the game: [(family, how many per room, where)] for the
    families found in at least 1 room in 4, most common first."""
    s = survey(db)
    K = s['kinds'].get(kind)
    if not K:
        return []
    out = []
    for fam, share in sorted(K['have'].items(), key=lambda kv: -kv[1]):
        if share < 0.25 or fam not in FLOOR_KINDS:
            continue
        w = K['where'].get(fam, {})
        where = max(w, key=w.get) if w else 'wall'
        out.append((fam, max(1, round(K['per_room'][fam])), where, share))
    return out
