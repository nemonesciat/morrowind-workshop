"""How the game's own places furnish the four kinds of room Auto-furnish does badly: bathing rooms,
halls and passages (corridors, entrance halls, landings with doors), storerooms and cellars, and
kitchens. For every room of a kind in the game's kit-built interiors: what stands in it by family (the
furniture families and the set-piece kinds, plus the kinds that mark these rooms: a tub or a basin, a
cooking pot or a kettle, hanging meat and fish, towels and washing things, buckets and water), at what
rate per nine tiles; how many rooms have a hearth, a cooking thing, a tub; whether the hearth is built
into the wall (a kit piece) or stands free; what rides on what (the crate tops, the counters, the tables);
how much stands against a wall, in a corner or out on the floor; the lights and the rugs; the game's
scenes there (the arrangement survey's groupings); and a per-culture breakdown. A room's kind is told
from what stands in it (roomsurvey.room_kind, plus the kinds this survey adds) and from its shape and
doors (a passage one tile wide, a room with the front door or three doorways), with the place's name as
a hint (a "bathhouse", a "cellar", a "warehouse"). Kept in the cache folder once done (taste.cache_file,
by load order); ready() runs it in the background the first time. Read-only: the furnish owner draws its
rules from the write-up (packaging/nexus/room-kinds-survey.md)."""
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

LIMIT = 300
LINK = 200                 # two pieces this close (origin to origin) are in one scene (arrangesurvey.LINK)
EXAMPLES = 60              # rooms kept per kind, for the write-up and spot checks
KINDS = ('bath', 'hall', 'storage', 'kitchen', 'guard')
GUARD_SUBS = ('barracks', 'armoury', 'training', 'mess', 'guardroom')
# the kinds of thing this survey adds to the furniture families and the set-piece kinds: matched on the
# object's id and its name together (lower case), whole-word or stem as given
MARKS = {
    'bath': (re.compile(r'bath|(^|[^a-z])tub([^a-z]|$)|basin|washstand|wash_stand|washbowl'), ('STAT', 'ACTI', 'CONT', 'MISC')),
    'cook': (re.compile(r'cook|kettle|cauldron|(^|[^a-z])spit|skillet|(^|[^a-z])pan([^a-z]|$)|frying|teapot|silverwarepot|iron_pot|metal_pot|cookpot|stewpot'), ('MISC', 'STAT', 'ACTI', 'CONT')),
    'hang': (re.compile(r'hang|dried|smoked|carcass|jerky|sausage|cured|rack_meat|meat_rack|_hook'), ('STAT', 'MISC', 'INGR', 'ACTI', 'CONT')),
    'wash': (re.compile(r'towel|soap|sponge|(^|[^a-z])comb|mirror|linen|washcloth|razor|perfume'), ('MISC', 'STAT', 'CLOT')),
    'water': (re.compile(r'bucket|pail|waterskin|ewer'), ('MISC', 'STAT', 'ACTI', 'CONT')),
    'firewood': (re.compile(r'firewood|_log|woodpile|wood_pile|kindling'), ('MISC', 'STAT')),
    'target': (re.compile(r'target|dummy|practice|training|pell([^a-z]|$)'), ('STAT', 'ACTI', 'CONT')),
    'dice': (re.compile(r'dice|cards|game_|gameboard|board_game'), ('MISC',)),
}
# guard settings: a place whose name says it houses guards or soldiers (a fort, a garrison, a guard tower,
# a barracks, an Ordinator or Fighters Guild hall), or one built from Tamriel Data's Legion set
GUARD_WORDS = (('legion', ('legion', 'fort ', 'fort,', 'garrison', 'moonmoth', 'command post', 'outpost', 'castle', ' keep', 'keep,')),
               ('guard tower', ('guard tower', 'guardtower', 'watchtower', 'watch tower', 'gatehouse', 'gate house', 'guardhouse', 'guard house', 'guard post', 'tower')),
               ('barracks', ('barracks', 'guard quarters', 'guards\' quarters', 'guard\'s quarters', 'soldiers')),
               ('ordinator', ('ordinator', 'temple guard', 'armigers', 'armiger')),
               ('fighters guild', ('fighters guild', 'fighter\'s guild', 'fighters\' guild')),
               ('guard', ('guard', 'armory', 'armoury', 'watch post', 'the watch')))      # (not "watch": Firewatch is a town)
TIERS = ('iron', 'steel', 'silver', 'chitin', 'bonemold', 'netch', 'imperial', 'nordic', 'dwemer', 'dwarven', 'orcish', 'glass', 'ebony',
         'daedric', 'adamantium', 'indoril', 'templar', 'dreugh', 'wooden', 'leather', 'fur', 'chain', 'colovian', 'redoran', 'hlaalu', 'legion')
HEARTH_WALL = re.compile(r'fireplace|hearth|chimney|oven|stove|kitchen')      # a kit's built-in hearth or kitchen wall
STORE_WORDS = ('cellar', 'storeroom', 'store room', 'storage', 'warehouse', 'stockroom', 'vault', 'pantry', 'larder')
HALL_WORDS = ('hall', 'corridor', 'entry', 'entrance', 'passage', 'foyer', 'vestibule', 'landing')
NOT_HALL = ('guildhall', 'guild hall', 'manor hall', 'great hall', 'council hall', 'hall of')
SMALL_TYPES = ('MISC', 'INGR', 'ALCH', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'APPA', 'LIGH', 'PROB', 'REPA', 'LOCK')
SURFACES = ('crate', 'barrel', 'chest', 'table', 'counter', 'shelf', 'bookshelf', 'cupboard', 'bench', 'sack', 'urn', 'bath')
_cache = {}
_thread = {}


def culture_of(info):
    """Whose building a place is, from its architecture: 'Gold Coast' for Tamriel Data's Gold Coast set,
    else the style label (Hlaalu, Redoran, Velothi, Imperial, Common, Indoril, Mournhold...), or '?'."""
    arch = [r for r in info['refs'] if r.get('arch') and r.get('b')]
    prefixes = Counter(kits.kit_prefix(r['id']) for r in arch if kits.kit_prefix(r['id']))
    prefix = prefixes.most_common(1)[0][0] if prefixes else ''
    if prefix.startswith('t_imp_setgc'):
        return 'Gold Coast', prefix
    labels = Counter(mapdata.style_of(r['id']) for r in arch if mapdata.style_of(r['id']))
    return (labels.most_common(1)[0][0] if labels else '?'), prefix


def mark_of(r):
    """Which of this survey's own kinds a thing is ('bath', 'cook', 'hang', 'wash', 'water', 'firewood'), or None."""
    low = (r['id'] + ' ' + (r.get('name') or '')).lower()
    if 'marker' in low:
        return None
    for k, (rx, types) in MARKS.items():
        if r['type'] in types and rx.search(low):
            if k == 'cook' and ('flower' in low or 'plant' in low or 'chamber' in low):
                continue
            if k == 'bath' and 'tube' in low:
                continue
            if k == 'hang' and ('wall' in low and 'hang' in low and 'meat' not in low and 'fish' not in low):
                continue              # (a wall hanging is a tapestry: the decor survey's)
            if k == 'target' and ('targeting' in low or 'train' in low and 'training' not in low):
                continue
            return k
    return None


def guard_setting(cell_name, prefix):
    """Which kind of guard place a cell is ('legion', 'guard tower', 'barracks', 'ordinator', 'fighters
    guild', 'guard'), or None for an ordinary place."""
    low = (cell_name or '').lower()
    if prefix.startswith('t_imp_legion'):
        return 'legion'
    for name, words in GUARD_WORDS:
        if any(w in low for w in words):
            return name
    return None


def tier_of(rid):
    """The make of a weapon or a piece of armour from its id ('iron', 'steel', 'glass'...), or 'other'."""
    low = rid.lower()
    for t in TIERS:
        if t in low:
            return t
    return 'other'


def guard_sub(c, gear, seats):
    """A guard place's room by what stands there: 'barracks' (two or more bunks or bedrolls), 'training'
    (a target or a dummy), 'armoury' (racks, or loose weapons and armour by the heap), 'mess' (a table
    with seats, food and drink), 'guardroom' (a chair, a chest, a lantern: a post), or None when it's
    one of the other kinds (a kitchen with its hearth, a store, a bath) or just a room."""
    beds = c['bed'] + c['bedroll']
    if beds >= 2:
        return 'barracks'
    if c['target']:
        return 'training'
    if c['rack'] >= 2 or (c['rack'] and gear >= 4) or gear >= 8:
        return 'armoury' if not beds else 'barracks'
    if beds:
        return None                    # (one bed: a bedroom, the room survey's)
    if c['table'] and seats >= 2 and not c['counter']:
        return 'mess'
    if c['bath'] or c['fire'] or c['cook'] or c['crate'] + c['barrel'] + c['sack'] + c['urn'] >= 3:
        return None
    if c['chair'] or c['chest'] or c['bench'] or c['rack']:
        return 'guardroom'
    return None


def family_of(r):
    """furnish.FAMILIES by the thing's id and its name together (roomsurvey.family_of reads the id alone,
    which misses Tamriel Data's T_MwCom_Var_Cr1.../Sk1.../Bl1... crates, sacks and barrels, named only
    "Crate", "Sack", "Barrel" in their records), or None."""
    low = (r['id'] + ' ' + (r.get('name') or '')).lower()
    if 'marker' in low or furnish.BARE_STONE.search(r['id'].lower()):
        return None
    for k, (words, types) in furnish.FAMILIES.items():
        if r['type'] not in types or not furnish._named(low, words):
            continue
        if any(w in low for w in furnish.NOT.get(k, ())):
            continue
        return k
    return None


def _fam(db, r):
    """A thing's family: the furniture families first, then the set-piece kinds, then this survey's marks."""
    import arrangesurvey
    f = family_of(r)
    m = mark_of(r)
    if m == 'bath':
        return 'bath'                 # (a tub or a basin before 'urn' or 'chest': it says what the room is)
    if f:
        if f == 'fire' and m == 'cook':
            return 'fire'
        return f
    x = arrangesurvey.family(db, r['id'], r['type'])
    if x and x not in ('apparatus',):
        return x
    return m


def _disk(db, limit):
    import taste
    return taste.cache_file('roomkindsurvey_%s_%d_v5' % (taste.sig(db), limit))


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
            _thread['t'] = background.start('how the game furnishes baths, halls, stores and kitchens', lambda: survey(db, limit),
                                            task=('roomkindsurvey', 'survey', [limit]))
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
    import fixit
    return fixit._world_box(r)


def kind_of(counts, rm, n_doors, front_door, cell_name):
    """The kind of room this survey files it under ('bath', 'kitchen', 'storage', 'hall'), or None for the
    kinds it doesn't cover. counts: families of what stands on its floor (this survey's _fam)."""
    c = counts
    low = (cell_name or '').lower()
    base = roomsurvey.room_kind(Counter({k: v for k, v in c.items() if k in roomsurvey.FLOOR_KINDS}))
    stores = c['crate'] + c['barrel'] + c['sack'] + c['urn']
    # a bathing room: two or more tubs or basins, or one with no bed and no stores round it (a single
    # washtub among the barrels of a one-room farmhouse is the kitchen's)
    if not c['counter'] and (c['bath'] >= 2 or (c['bath'] and not c['bed'] and stores + c['hang'] < 3 and 'bath' in low)
                             or (c['bath'] and not c['bed'] and stores + c['hang'] < 3 and not c['fire'] and not c['cook'])):
        return 'bath'
    if base in ('bedroom', 'shop', 'tavern', 'shrine', 'study'):
        return None
    if base == 'kitchen' or (c['fire'] + c['cook'] and not c['bed'] and (stores + c['cook'] + c['hang'] >= 2 or 'kitchen' in low)):
        return 'kitchen'
    if base == 'storage' or (any(w in low for w in STORE_WORDS) and stores >= 2 and not c['table']):
        return 'storage'
    narrow = min(rm['w'], rm['h']) == 1 and max(rm['w'], rm['h']) >= 3
    if narrow or (front_door and rm['tiles'] <= 4 and not c['table'] and not c['bed']) \
            or (n_doors >= 3 and rm['tiles'] <= 6 and not c['table'] and c['chair'] <= 2):
        return 'hall'
    if any(w in low for w in HALL_WORDS) and not any(w in low for w in NOT_HALL) and base in ('empty', 'living') and rm['tiles'] <= 6 and not c['table']:
        return 'hall'
    return None


def _survey(db, limit):
    import taste
    rows = []                              # one row per room of a covered kind
    seen = 0
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    cells = taste.spread(cells, limit)
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
        culture, prefix = culture_of(info)
        theme = roomsurvey.theme_of(ck)
        arch = [r for r in info['refs'] if r.get('arch') and r.get('b')]
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'LEVC', 'DOOR')]
        doors = [r for r in info['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()]
        for r in refs:
            r['_fam'] = _fam(db, r)
        for rm in info['rooms']:
            fl = rm['floor']
            # (up to 240 above the floor: a storey is 256, and the room upstairs shares this footprint)
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and fl - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 240]
            floor = [r for r in inside if r['_fam'] and r['_fam'] not in roomsurvey.TOP_KINDS and r['type'] not in SMALL_TYPES
                     and r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 160]
            counts = Counter(r['_fam'] for r in floor)
            marks = Counter(r['_fam'] for r in inside if r['_fam'] in MARKS)
            for k, v in marks.items():
                if k not in counts:
                    counts[k] = v
            # the doorways on this room's edge, and whether one is the front door
            mine = []
            front = False
            for d in doors:
                if not (fl - 60 <= d['p'][2] <= fl + 200):
                    continue
                x, y = d['p'][0], d['p'][1]
                on_x = min(abs(x - rm['x_min']), abs(x - rm['x_max'])) < 40 and rm['y_min'] - 20 <= y <= rm['y_max'] + 20
                on_y = min(abs(y - rm['y_min']), abs(y - rm['y_max'])) < 40 and rm['x_min'] - 20 <= x <= rm['x_max'] + 20
                if on_x or on_y:
                    mine.append(d)
                    if d['type'] == 'DOOR' and d.get('to') and not d['to'].get('cell'):
                        front = True
            n_doors = len({(round(d['p'][0] / 64), round(d['p'][1] / 64)) for d in mine})
            gear_items = [o for o in inside if o['type'] in ('WEAP', 'ARMO')]
            setting = guard_setting(ck, prefix)
            kind = sub = None
            if setting:
                sub = guard_sub(counts, len(gear_items), counts['chair'] + counts['bench'])
                if sub:
                    kind = 'guard'
            if not kind:
                kind = kind_of(counts, rm, n_doors, front, ck)
            if not kind:
                continue
            if kind == 'hall':
                sub = 'corridor' if min(rm['w'], rm['h']) == 1 and max(rm['w'], rm['h']) >= 3 else 'entry' if front else 'landing'
            elif kind == 'bath':
                sub = 'bathhouse' if counts['bath'] >= 2 else 'washroom' if not counts['bed'] and not counts['table'] else 'basin in a room'
            # the guard rooms' own measures: the bunks' spacing and whether they lie parallel, chests at
            # their feet, the weapons' and armour's make, shields hung up on the walls
            beds = [r for r in floor if r['_fam'] in ('bed', 'bedroll')]
            bed_nn = []
            parallel = 0
            for a in beds:
                others = [b for b in beds if b is not a]
                if not others:
                    continue
                b = min(others, key=lambda b: math.hypot(b['p'][0] - a['p'][0], b['p'][1] - a['p'][1]))
                bed_nn.append(round(math.hypot(b['p'][0] - a['p'][0], b['p'][1] - a['p'][1])))
                if abs(((a['p'][5] - b['p'][5]) % math.pi)) < 0.2 or abs(((a['p'][5] - b['p'][5]) % math.pi) - math.pi) < 0.2:
                    parallel += 1
            chest_by_bed = sum(1 for c_ in floor if c_['_fam'] == 'chest' and beds
                               and min(math.hypot(b['p'][0] - c_['p'][0], b['p'][1] - c_['p'][1]) for b in beds) < 200)
            tiers = Counter(tier_of(o['id']) for o in gear_items)
            gear_kinds = Counter('shield' if 'shield' in o['id'].lower() else o['type'] for o in gear_items)
            shields_up = sum(1 for o in gear_items if 'shield' in o['id'].lower() and o['p'][2] + o['b'][2] * (o.get('s') or 1) - fl > 100)
            # the built-in hearth: a kit wall piece named for it, on this room's edge
            built_in = [a for a in arch if HEARTH_WALL.search(a['id'].lower()) and rm['x_min'] - 40 <= a['p'][0] <= rm['x_max'] + 40
                        and rm['y_min'] - 40 <= a['p'][1] <= rm['y_max'] + 40 and fl - 60 <= a['p'][2] <= fl + 200]
            # where each floor piece stands
            where = Counter()
            where_f = defaultdict(Counter)
            for r in floor:
                dx = min(r['p'][0] - rm['x_min'], rm['x_max'] - r['p'][0])
                dy = min(r['p'][1] - rm['y_min'], rm['y_max'] - r['p'][1])
                near = sum(1 for d in (dx, dy) if d < T * 0.35)
                w = 'corner' if near == 2 else 'wall' if near == 1 else 'middle'
                where[w] += 1
                where_f[r['_fam']][w] += 1
            # what rides on what: small things (and small containers) over a surface piece's box
            boxes = [(r, _box(r)) for r in floor if r['_fam'] in SURFACES]
            tops = defaultdict(Counter)
            topped = Counter()               # surfaces with something on them, by family
            top_ids = defaultdict(Counter)
            stacked = Counter()              # crates/barrels/sacks with another of the family on top
            for o in inside:
                small = o['type'] in SMALL_TYPES or (o['type'] == 'CONT' and o['_fam'] in ('basket', 'sack', 'urn', 'chest', 'crate') and
                                                     max(o['b'][3] - o['b'][0], o['b'][4] - o['b'][1]) * (o.get('s') or 1) < 90)
                ob = o['p'][2] + o['b'][2] * (o.get('s') or 1)
                hit = None
                for r, b in boxes:
                    if r is o or not b:
                        continue
                    if b[0] - 6 <= o['p'][0] <= b[3] + 6 and b[1] - 6 <= o['p'][1] <= b[4] + 6 and b[5] - 24 <= ob <= b[5] + 40:
                        if hit is None or b[5] > hit[1][5]:
                            hit = (r, b)
                if hit is None:
                    continue
                uf = hit[0]['_fam']
                if small:
                    tops[uf][o['_fam'] or o['type']] += 1
                    top_ids[uf][o['id'].lower()] += 1
                    topped[hit[0]['k']] += 1
                elif o['_fam'] == uf and uf in ('crate', 'barrel', 'sack', 'urn', 'basket'):
                    stacked[uf] += 1
            surf_n = Counter(r['_fam'] for r, b in boxes)
            surf_topped = Counter(r['_fam'] for r, b in boxes if topped[r['k']])
            # lights and rugs
            lights = [r for r in inside if r['type'] == 'LIGH']
            lw = Counter()
            for r in lights:
                up = r['p'][2] + r['b'][2] * (r.get('s') or 1) - fl
                lw['floor' if up < 20 else 'furniture' if up < 130 else 'wall' if up < 230 else 'ceiling'] += 1
            # scenes: pieces within LINK of one another, signed by their families (anchor first)
            sigs = Counter()
            left = list(range(len(floor)))
            lone = Counter()
            while left:
                grp = [left.pop(0)]
                i = 0
                while i < len(grp):
                    a = floor[grp[i]]
                    for j in list(left):
                        b = floor[j]
                        if math.hypot(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1]) <= LINK:
                            grp.append(j)
                            left.remove(j)
                    i += 1
                if len(grp) < 2:
                    lone[floor[grp[0]]['_fam']] += 1
                    continue
                if len(grp) > 12:
                    continue
                sigs[_sig([floor[i_]['_fam'] for i_ in grp])] += 1
            # things by a doorway (within a tile of one): what the game stands beside its doors
            by_door = Counter()
            for r in floor:
                if any(math.hypot(d['p'][0] - r['p'][0], d['p'][1] - r['p'][1]) < T * 0.9 for d in mine):
                    by_door[r['_fam']] += 1
            small_n = sum(1 for o in inside if o['type'] in SMALL_TYPES)
            rows.append({'cell': ck, 'room': rm['id'], 'kind': kind, 'sub': sub, 'culture': culture, 'prefix': prefix, 'theme': theme, 'setting': setting,
                         'beds': len(beds), 'bed_nn': bed_nn, 'bed_parallel': parallel, 'chest_by_bed': chest_by_bed,
                         'gear_n': len(gear_items), 'tiers': dict(tiers), 'gear_kinds': dict(gear_kinds), 'shields_up': shields_up,
                         'rack_ids': sorted({r['id'].lower() for r in floor if r['_fam'] == 'rack'})[:4],
                         'target_ids': sorted({r['id'].lower() for r in inside if r['_fam'] == 'target'})[:4],
                         'tiles': rm['tiles'], 'w': rm['w'], 'h': rm['h'], 'doors': n_doors, 'front': front,
                         'counts': dict(counts), 'floor_n': len(floor), 'small_n': small_n, 'all_n': len(inside),
                         'cover': round(sum(roomsurvey._fp_area(r) for r in floor if r['_fam'] != 'rug') / float(rm['tiles'] * T * T), 3),
                         'hearth': int(bool(counts['fire'])), 'built_in': len({a['id'].lower() for a in built_in}), 'built_in_ids': sorted({a['id'].lower() for a in built_in})[:3],
                         'fire_ids': sorted({r['id'].lower() for r in floor if r['_fam'] == 'fire'}),
                         'bath_ids': sorted({r['id'].lower() for r in inside if r['_fam'] == 'bath'}),
                         'cook_ids': sorted({r['id'].lower() for r in inside if r['_fam'] == 'cook'})[:6],
                         'hang_ids': sorted({r['id'].lower() for r in inside if r['_fam'] == 'hang'})[:6],
                         'where': dict(where), 'where_f': {f: dict(w) for f, w in where_f.items()},
                         'tops': {f: dict(c) for f, c in tops.items()}, 'top_ids': {f: c.most_common(6) for f, c in top_ids.items()},
                         'surf_n': dict(surf_n), 'surf_topped': dict(surf_topped), 'stacked': dict(stacked),
                         'lights': len(lights), 'lights_where': dict(lw), 'light_ids': Counter(r['id'].lower() for r in lights).most_common(3),
                         'rugs': counts['rug'], 'rug_ids': sorted({r['id'].lower() for r in floor if r['_fam'] == 'rug'})[:3],
                         'sigs': dict(sigs), 'lone': dict(lone), 'by_door': dict(by_door),
                         'ids': Counter(r['id'].lower() for r in floor).most_common(8)})
    return _fold(seen, rows)


def _sig(fams):
    import arrangesurvey
    return arrangesurvey._signature(fams)


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _stats(rs):
    """The figures for a set of room rows: rates per nine tiles, shares of rooms with each thing, where
    things stand, what rides on what, lights, rugs, scenes."""
    n = len(rs)
    ts = float(sum(r['tiles'] for r in rs) or 1)
    count = Counter()
    have = Counter()
    for r in rs:
        for f, v in r['counts'].items():
            count[f] += v
            have[f] += 1
    where = sum((Counter(r['where']) for r in rs), Counter())
    wn = float(sum(where.values()) or 1)
    where_f = defaultdict(Counter)
    for r in rs:
        for f, w in r['where_f'].items():
            where_f[f].update(w)
    tops = defaultdict(Counter)
    top_ids = defaultdict(Counter)
    surf_n = Counter()
    surf_topped = Counter()
    stacked = Counter()
    sigs = Counter()
    lone = Counter()
    by_door = Counter()
    lw = Counter()
    light_ids = Counter()
    rug_ids = Counter()
    fire_ids = Counter()
    bath_ids = Counter()
    cook_ids = Counter()
    hang_ids = Counter()
    built_ids = Counter()
    ids = Counter()
    tiers = Counter()
    gear_kinds = Counter()
    rack_ids = Counter()
    target_ids = Counter()
    bed_nn = []
    for r in rs:
        tiers.update(r['tiers'])
        gear_kinds.update(r['gear_kinds'])
        rack_ids.update(r['rack_ids'])
        target_ids.update(r['target_ids'])
        bed_nn += r['bed_nn']
        for f, c in r['tops'].items():
            tops[f].update(c)
        for f, c in r['top_ids'].items():
            top_ids[f].update(dict(c))
        surf_n.update(r['surf_n'])
        surf_topped.update(r['surf_topped'])
        stacked.update(r['stacked'])
        sigs.update(r['sigs'])
        lone.update(r['lone'])
        by_door.update(r['by_door'])
        lw.update(r['lights_where'])
        light_ids.update(dict(r['light_ids']))
        rug_ids.update(r['rug_ids'])
        fire_ids.update(r['fire_ids'])
        bath_ids.update(r['bath_ids'])
        cook_ids.update(r['cook_ids'])
        hang_ids.update(r['hang_ids'])
        built_ids.update(r['built_in_ids'])
        ids.update(dict(r['ids']))
    return {
        'rooms': n, 'tiles_med': _med([r['tiles'] for r in rs]), 'tile_sum': int(ts),
        'subs': dict(Counter(r['sub'] for r in rs if r['sub'])), 'themes': dict(Counter(r['theme'] for r in rs).most_common()),
        'settings': dict(Counter(r['setting'] for r in rs if r['setting']).most_common()),
        'cells': Counter(r['cell'] for r in rs).most_common(16),
        'beds_per_room': round(sum(r['beds'] for r in rs) / float(n), 2), 'bed_nn': _med(bed_nn),
        'bed_parallel': round(sum(r['bed_parallel'] for r in rs) / float(max(1, len(bed_nn))), 2),
        'chest_by_bed': round(sum(r['chest_by_bed'] for r in rs) / float(max(1, sum(r['beds'] for r in rs))), 2),
        'gear_per_9': round(sum(r['gear_n'] for r in rs) / ts * 9, 2), 'gear_kinds': dict(gear_kinds.most_common()),
        'tiers': dict(tiers.most_common(10)), 'shields_up': sum(r['shields_up'] for r in rs),
        'rack_ids': rack_ids.most_common(8), 'target_ids': target_ids.most_common(6),
        'doors_mean': round(sum(r['doors'] for r in rs) / float(n), 2), 'front_door': round(sum(1 for r in rs if r['front']) / float(n), 2),
        'per_9': {f: round(count[f] / ts * 9, 2) for f, _v in count.most_common()},
        'have': {f: round(have[f] / float(n), 2) for f, _v in have.most_common()},
        'floor_per_9': round(sum(r['floor_n'] for r in rs) / ts * 9, 1), 'small_per_9': round(sum(r['small_n'] for r in rs) / ts * 9, 1),
        'all_per_9': round(sum(r['all_n'] for r in rs) / ts * 9, 1), 'cover': _med([r['cover'] for r in rs]),
        'hearth': round(sum(r['hearth'] for r in rs) / float(n), 2), 'built_in': round(sum(1 for r in rs if r['built_in']) / float(n), 2),
        'cook': round(have['cook'] / float(n), 2), 'bath': round(have['bath'] / float(n), 2), 'hang': round(have['hang'] / float(n), 2),
        'water': round(have['water'] / float(n), 2), 'wash': round(have['wash'] / float(n), 2),
        'where': {w: round(v / wn, 2) for w, v in where.items()},
        'where_f': {f: {w: round(v / float(sum(c.values())), 2) for w, v in c.items()} for f, c in where_f.items() if sum(c.values()) >= 5},
        'tops': {f: c.most_common(8) for f, c in tops.items()}, 'top_ids': {f: c.most_common(8) for f, c in top_ids.items()},
        'topped': {f: round(surf_topped[f] / float(surf_n[f]), 2) for f in surf_n if surf_n[f] >= 5},
        'stacked': {f: round(stacked[f] / float(count[f]), 2) for f in stacked if count[f] >= 5},
        'lights_per_9': round(sum(r['lights'] for r in rs) / ts * 9, 2), 'lights_where': dict(lw), 'light_ids': light_ids.most_common(6),
        'rugs_per_9': round(count['rug'] / ts * 9, 2), 'rug_rooms': round(have['rug'] / float(n), 2), 'rug_ids': rug_ids.most_common(5),
        'fire_ids': fire_ids.most_common(8), 'built_in_ids': built_ids.most_common(6), 'bath_ids': bath_ids.most_common(8),
        'cook_ids': cook_ids.most_common(10), 'hang_ids': hang_ids.most_common(8),
        'scenes': sigs.most_common(14), 'lone': lone.most_common(8), 'by_door': {f: round(v / float(n), 2) for f, v in by_door.most_common(8)},
        'ids': ids.most_common(16)}


def _fold(seen, rows):
    out = {'cells': seen, 'rooms': len(rows), 'kinds': {}, 'examples': {}}
    for kind in KINDS:
        rs = [r for r in rows if r['kind'] == kind]
        if not rs:
            continue
        K = {'*': _stats(rs)}
        for cu in sorted({r['culture'] for r in rs}):
            own = [r for r in rs if r['culture'] == cu]
            if len(own) >= 3:
                K[cu] = _stats(own)
        # the rooms by what they are (a barracks, an armoury; a corridor, an entry, a landing; a
        # bathhouse, a washroom) and, for the guard rooms, by their setting
        for sub in sorted({r['sub'] for r in rs if r['sub']}):
            own = [r for r in rs if r['sub'] == sub]
            if len(own) >= 2:
                K['sub:' + sub] = _stats(own)
        if kind == 'guard':
            for st in sorted({r['setting'] for r in rs if r['setting']}):
                own = [r for r in rs if r['setting'] == st]
                if len(own) >= 2:
                    K['setting:' + st] = _stats(own)
        out['kinds'][kind] = K
        # the examples: the fullest rooms of the kind, spread over the cultures
        ex = sorted(rs, key=lambda r: -r['all_n'])
        keep, per = [], Counter()
        for r in ex:
            if per[r['culture']] >= max(6, EXAMPLES // 6) and len(keep) >= EXAMPLES // 2:
                continue
            per[r['culture']] += 1
            keep.append({k: r[k] for k in ('cell', 'room', 'sub', 'setting', 'culture', 'theme', 'tiles', 'w', 'h', 'doors', 'front', 'all_n', 'floor_n',
                                            'counts', 'ids', 'fire_ids', 'built_in_ids', 'bath_ids', 'cook_ids', 'hang_ids', 'sigs', 'lights', 'rugs',
                                            'beds', 'bed_nn', 'gear_n', 'tiers', 'rack_ids', 'target_ids')})
            if len(keep) >= EXAMPLES:
                break
        out['examples'][kind] = keep
    return out


def report(db, limit=LIMIT, cultures=('Hlaalu', 'Redoran', 'Velothi', 'Imperial', 'Common', 'Gold Coast')):
    """The figures in words, kind by kind, every culture then the named ones with three rooms or more."""
    s = survey(db, limit)
    lines = ['%d places walked, %d rooms of the four kinds' % (s['cells'], s['rooms'])]
    for kind in KINDS:
        K = s['kinds'].get(kind)
        if not K:
            lines.append('== %s: none' % kind)
            continue
        keys = ('*',) + tuple(c for c in cultures if c in K) + tuple(k for k in K if ':' in k)
        for cu in keys:
            S = K[cu]
            lines.append('== %s / %s: %d rooms (median %s tiles; %s; themes %s; settings %s); doors %s per room, front door %s' % (
                kind, cu, S['rooms'], S['tiles_med'], S['subs'], S['themes'], S['settings'], S['doors_mean'], S['front_door']))
            if kind == 'guard':
                lines.append('   places: %s' % S['cells'][:12])
                lines.append('   beds %s per room (nearest bunk median %s apart, parallel %s; a chest within 200 of a bunk %s per bunk); gear %s per 9 (%s; makes %s; shields hung up %d); racks %s; targets %s' % (
                    S['beds_per_room'], S['bed_nn'], S['bed_parallel'], S['chest_by_bed'], S['gear_per_9'], S['gear_kinds'], S['tiers'], S['shields_up'], S['rack_ids'][:5], S['target_ids'][:4]))
            lines.append('   per 9 tiles: floor %s, small things %s, all %s; cover %s; %s' % (
                S['floor_per_9'], S['small_per_9'], S['all_per_9'], S['cover'], ', '.join('%s %s' % kv for kv in list(S['per_9'].items())[:16])))
            lines.append('   rooms with: %s' % ', '.join('%s %s' % kv for kv in list(S['have'].items())[:16]))
            lines.append('   hearth %s (built in %s: %s; free %s), cooking %s (%s), tub/basin %s (%s), hanging %s (%s), water %s, washing %s' % (
                S['hearth'], S['built_in'], S['built_in_ids'][:3], S['fire_ids'][:4], S['cook'], S['cook_ids'][:5], S['bath'], S['bath_ids'][:4],
                S['hang'], S['hang_ids'][:4], S['water'], S['wash']))
            lines.append('   where: %s; by family: %s' % (S['where'], {f: w for f, w in list(S['where_f'].items())[:8]}))
            lines.append('   on top: %s; topped %s; stacked %s' % ({f: c[:5] for f, c in S['tops'].items()}, S['topped'], S['stacked']))
            lines.append('   lights %s per 9 (%s; %s); rugs %s per 9, in %s of rooms (%s)' % (
                S['lights_per_9'], S['lights_where'], S['light_ids'][:3], S['rugs_per_9'], S['rug_rooms'], S['rug_ids'][:3]))
            lines.append('   scenes: %s; alone: %s; by a door: %s' % (S['scenes'][:10], S['lone'][:5], S['by_door']))
            lines.append('   models: %s' % S['ids'][:12])
        lines.append('   examples: %s' % ', '.join('%s#%d (%s, %d things)' % (e['cell'], e['room'], e['culture'], e['all_n']) for e in s['examples'][kind][:12]))
    return '\n'.join(lines)
