"""Populate: people for a place, as the game would have them (2026-10-23).

cast() proposes a cast for a place and changes nothing: who would be there (a group the game's own places
of this kind have: a publican with servers and patrons, a household with its servants, smugglers in a cave),
each a person of their own (race, sex, name in the manner of their race, face, class, faction and rank,
level, an outfit slot by slot, what they carry, a few spells, how they greet, fight and wander, what they
sell) and where they stand (by the furniture the game stands their kind at: the trader behind the counter,
the publican by the bar; else on open floor). All of it from the people survey (castsurvey.py) and where the
game stands people (peoplesurvey.py); the page's parameters (races, faction, occupations, wealth, how busy)
lean it their way.

place() makes the cast real as one change: a new NPC record for each person, placed where the cast says,
and (for a household or a shop) the place's beds and containers owned by its head, so taking from them
is stealing, as in the game's own houses."""
import math
import random
import struct
from collections import Counter

import castsurvey
from editing import EditError, commit, _require_project
from esm import ENC
from project import join_subs, zs

DENSITY = {'quiet': 0.55, 'usual': 1.0, 'busy': 1.7}
MAX_PEOPLE = 30
HOUSEHOLDS = ('house', 'manor', 'shop', 'tavern', 'camp')        # (places whose people are a household: one family name, owned beds)
OWNED = ('bed', 'chest', 'cupboard', 'barrel', 'crate', 'sack', 'drawer', 'dresser', 'desk', 'closet', 'wardrobe', 'urn')
MATERIALS = ('daedric', 'ebony', 'glass', 'dwemer', 'dwarven', 'orcish', 'adamantium', 'indoril', 'her_hand', 'bonemold', 'chitin',
             'netch', 'imperial', 'steel', 'iron', 'silver', 'nordic', 'fur', 'leather', 'dreugh', 'riverwatch', 'redoran', 'hlaalu',
             'telvanni', 'templar', 'colovian', 'ringmail', 'chain', 'kagouti', 'molecrab', 'newtscale', 'goblin', 'bear', 'wolf')
ARMOR = ('helmet', 'cuirass', 'pauldron_l', 'pauldron_r', 'greaves', 'boots', 'gauntlet_l', 'gauntlet_r', 'shield', 'bracer_l', 'bracer_r')
PAIRS = (('pauldron_l', 'pauldron_r'), ('gauntlet_l', 'gauntlet_r'), ('bracer_l', 'bracer_r'), ('glove_l', 'glove_r'))
SINGLE_NAMED = ('argonian', 'khajiit')
CLEAR = 46              # (how far a person stands from another, at least)
# a shop's trade, by a word of its name: the words in the classes that keep such a shop
TRADES = (('smith', ('smith', 'armorer')), ('armor', ('smith', 'armorer')), ('weapon', ('smith',)), ('forge', ('smith',)),
          ('outfit', ('clothier', 'trader')), ('cloth', ('clothier',)), ('tailor', ('clothier',)), ('alchem', ('apothecary', 'alchemist')),
          ('apothec', ('apothecary',)), ('herbal', ('apothecary',)), ('book', ('bookseller',)), ('pawn', ('pawnbroker',)),
          ('enchant', ('enchanter',)), ('mage', ('enchanter', 'mage')), ('trader', ('trader',)), ('general', ('trader',)),
          ('merchant', ('trader',)), ('supplies', ('trader',)), ('goods', ('trader',)))
NOT_HEADS = ('slave', 'servant', 'guard', 'ordinator', 'sharpshooter')


# ---------------------------------------------------------------- picking
def _w(rng, pairs):
    """A weighted pick from [[thing, weight]...], or None."""
    pairs = [p for p in pairs if p[1] > 0]
    if not pairs:
        return None
    t = sum(p[1] for p in pairs) * rng.random()
    for k, v in pairs:
        t -= v
        if t <= 0:
            return k
    return pairs[-1][0]


def _spread(rng, s, lo=1):
    """A value in a survey's [p10, p50, p90]."""
    if not s:
        return lo
    a, m, b = s
    return int(round(m + (rng.random() - 0.5) * (b - a))) if b > a else m


def _material(rid):
    low = rid.lower()
    return next((m for m in MATERIALS if m in low), None)


# ---------------------------------------------------------------- the place
def place_info(db, cell_key):
    """What Populate needs to know of a place: its setting and culture (as the survey reads the game's),
    its furniture, its rooms' floors, and the people already in it."""
    import mapdata
    import roomsurvey
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists'):
        raise EditError('There is no place called "%s".' % cell_key)
    if not m.get('interior'):
        raise EditError('Populate works indoors for now (outdoors is to come).')
    ids = [r['id'] for r in m['refs']]
    setting, theme, culture = castsurvey.setting_of(db, m.get('name') or cell_key, ids)
    furniture = []
    for r in m['refs']:
        if r['type'] in ('NPC_', 'CREA', 'DOOR') or r.get('arch') or not r.get('b'):
            continue
        fam = roomsurvey.family_of(db, r['id'], r['type'])
        if fam:
            furniture.append(dict(r, fam=fam))
    rooms = []
    try:
        import furnish
        rooms = furnish.rooms(db, cell_key)['rooms']
    except Exception:
        rooms = []
    people = [r for r in m['refs'] if r['type'] in ('NPC_', 'CREA')]
    pieces = sum(1 for i in ids if i.lower().startswith(('in_', 'ex_', 't_')))
    return {'key': cell_key, 'name': m.get('name') or cell_key, 'setting': setting, 'culture': culture, 'refs': m['refs'],
            'furniture': furniture, 'rooms': rooms, 'people': people, 'pieces': pieces}


def _cast_of(S, setting, culture):
    return S['casts'].get('%s|%s' % (setting, culture)) if (S['casts'].get('%s|%s' % (setting, culture)) or {}).get('places', 0) >= 4 \
        else S['casts'].get(setting) or S['casts'].get('house')


def how_many(S, info, density='usual'):
    """How many people a place like this has: the game's own median for its setting, scaled by its size."""
    C = _cast_of(S, info['setting'], info['culture'])
    if isinstance(density, (int, float)) or (isinstance(density, str) and density.isdigit()):
        return max(1, min(MAX_PEOPLE, int(density)))
    p50 = (C.get('people') or [1, 2, 4])[1] or 1
    size = (C.get('pieces') or [0, 0, 0])[1] or 0
    scale = (info['pieces'] / size) ** 0.6 if size and info['pieces'] else 1.0
    n = p50 * max(0.5, min(3.0, scale)) * DENSITY.get(density, 1.0)
    return max(1, min(MAX_PEOPLE, int(round(n))))


# ---------------------------------------------------------------- one person
def _name(db, S, rng, race, female, family=None, taken=()):
    N = S['names'].get('%s|%s' % (race, 'f' if female else 'm')) or {}
    if race.lower() in SINGLE_NAMED or not N.get('family'):
        pool = N.get('single') or N.get('first') or [['Nameless', 1]]
        for _t in range(30):
            nm = _w(rng, pool)
            if nm and nm.lower() not in taken:
                return nm
        return _w(rng, pool)
    fam = family or _w(rng, N.get('family') or S['names'].get('%s|any' % race, {}).get('family') or [['', 1]])
    for _t in range(40):
        first = _w(rng, N.get('first') or [['Nameless', 1]])
        nm = ('%s %s' % (first, fam)).strip()
        if nm.lower() not in taken:
            return nm
    return nm


def _outfit(db, S, rng, cls, band, faction=''):
    """[[item id, count]]: clothes and armour slot by slot as the game dresses people of this class and
    wealth (each slot as often as they wear something there), or of this class in this faction where the
    game has enough of them (a Hlaalu guard in Hlaalu armour); armour of one make where it can be, a
    weapon, and a bow with arrows or a crossbow with bolts."""
    F = S['outfits'].get('%s|@%s' % (cls, faction)) if faction else None
    O = F if F and F['n'] >= 5 else S['outfits'].get('%s|%s' % (cls, band)) or S['outfits'].get('%s|common' % cls) or \
        S['outfits'].get('Commoner|%s' % band) or S['outfits'].get('Commoner|poor') or {'slots': {}}
    slots = O['slots']
    out, chosen = [], {}
    worn_armor = rng.random() < max((slots.get(s, {}).get('share', 0) for s in ('cuirass', 'greaves', 'boots')), default=0)
    make = None
    for slot in ('cuirass', 'greaves', 'boots', 'helmet', 'pauldron_l', 'pauldron_r', 'gauntlet_l', 'gauntlet_r', 'bracer_l',
                 'bracer_r', 'shield', 'shirt', 'pants', 'skirt', 'robe', 'shoes', 'belt', 'glove_l', 'glove_r', 'ring', 'amulet',
                 'weapon', 'bow', 'crossbow', 'thrown'):
        s = slots.get(slot)
        if not s:
            continue
        if slot == 'crossbow' and 'bow' in chosen:
            continue
        if slot in ARMOR and not worn_armor:
            continue
        if slot == 'shoes' and 'boots' in chosen:
            continue
        twin = next((a for a, b in PAIRS if b == slot), None)
        if twin is not None:
            if twin not in chosen:
                continue                       # (the right one goes with the left, as a pair)
        elif slot not in ('cuirass',) and rng.random() >= s['share'] * (1.15 if slot in ARMOR else 1.0):
            continue
        items = s['items']
        if slot in ARMOR and make:
            same = [it for it in items if _material(it[0]) == make]
            items = same or items
        if twin is not None:
            # the other of a pair: the same make, the other hand (left_ / right_, _l / _r in its ID)
            mate = chosen[twin]
            alt = [it for it in items if _material(it[0]) == _material(mate)] or items
            pick = _w(rng, alt)
        else:
            pick = _w(rng, items)
        if not pick or db.resolve_id(pick) is None:
            continue
        chosen[slot] = pick
        if slot == 'cuirass':
            make = _material(pick)
        out.append([pick, 1])
    for launcher, shot in (('bow', 'arrow'), ('crossbow', 'bolt')):
        ammo = slots.get(shot)
        if launcher in chosen and ammo:
            a = _w(rng, ammo['items'])
            if a and db.resolve_id(a) is not None:
                out.append([a, rng.choice((15, 20, 25, 30))])
    if 'shirt' not in chosen and 'robe' not in chosen and 'cuirass' not in chosen and db.resolve_id('common_shirt_01'):
        out.append(['common_shirt_01', 1])
    if 'pants' not in chosen and 'skirt' not in chosen and 'robe' not in chosen and 'greaves' not in chosen and db.resolve_id('common_pants_01'):
        out.append(['common_pants_01', 1])
    return out


def person(db, S, rng, cls, setting_cast, params, family=None, taken=(), role=None, race=None, female=None):
    """One person of a class, for a place whose cast is setting_cast (race and female: as given, for a
    head's wife or husband)."""
    B = S['classes'].get(cls) or S['classes'].get('Commoner')
    allowed = [r.lower() for r in params.get('races') or []]
    races = Counter({r: n for r, n in B['races']})
    place_races = dict(setting_cast.get('races') or [])
    if place_races:
        tot = sum(place_races.values())
        races = Counter({r: n * (0.2 + place_races.get(r, 0) / tot) for r, n in races.items()})
    if allowed:
        races = Counter({r: n for r, n in races.items() if r.lower() in allowed}) or Counter({r: 1 for r in params['races']})
    race = race or _w(rng, races.most_common()) or 'Dark Elf'
    female = (rng.random() < B.get('female', 0.4)) if female is None else female
    # faction: the page's, else the class's in this kind of place (a Hlaalu guard in a Hlaalu house)
    faction, rank = params.get('faction') or '', 0
    if not faction:
        pf = dict(setting_cast.get('factions') or [])
        share = sum(n for f, n in B['factions']) / max(1, B['n'])
        if rng.random() < share:
            cands = [[f, n * (1 + 3 * pf.get(f, 0) / max(1, sum(pf.values())))] for f, n in B['factions']]
            faction = _w(rng, cands) or ''
    if faction:
        rank = int(_w(rng, [[r, n] for r, n in B.get('ranks') or [[0, 1]]]) or 0) if not params.get('faction') else rng.randint(0, 3)
    level = max(1, _spread(rng, B.get('levels')))
    band = params.get('wealth') if params.get('wealth') in ('poor', 'common', 'fine', 'rich') else \
        _w(rng, [[b, n * (1 + 2 * dict(setting_cast.get('bands') or []).get(b, 0) / max(1, setting_cast.get('n', 1)))] for b, n in B['bands']]) or 'common'
    face = S['faces'].get('%s|%s' % (race, 'f' if female else 'm')) or {}
    head = _w(rng, face.get('head') or [])
    hair = _w(rng, face.get('hair') or [])
    # a person the game names by what they are ("Hlaalu Guard") gets such a name; else a name of their own
    titles = B.get('titles') or []
    if titles and sum(n for _t, n in titles) >= 0.5 * B['n']:
        name = _w(rng, titles)
    else:
        name = _name(db, S, rng, race, female, family, taken)
    items = _outfit(db, S, rng, cls, band, faction)
    sells = any(int(bit) in range(0, 14) and share >= 0.5 for bit, share in B['services'].items())
    for _k in range(max(0, _spread(rng, B.get('carry_n'), 0))):
        it = _w(rng, B.get('carry') or [])
        if it and db.resolve_id(it) is not None and not any(x[0] == it for x in items):
            items.append([it, -rng.randint(2, 6) if sells else 1])     # (a trader's stock comes back after they sell it)
    spells = [s for s, n in (B.get('spells') or []) if n >= max(2, 0.15 * B['n']) and rng.random() < 0.6][:3]
    services = 0
    for bit, share in B['services'].items():
        if share >= 0.5:
            services |= 1 << int(bit)
    wander = B.get('wander') or [0, 0, 0]
    return {'key': '%08x' % rng.getrandbits(32), 'name': name or 'Nameless', 'race': race, 'female': female, 'cls': cls,
            'role': role or castsurvey.role_of(cls), 'faction': faction, 'rank': rank, 'level': level, 'band': band,
            'head': head or '', 'hair': hair or '', 'items': items, 'spells': [s for s in spells if db.resolve_id(s) is not None],
            'hello': B.get('hello') if B.get('hello') is not None else 30, 'fight': B.get('fight') if B.get('fight') is not None else 30,
            'flee': B.get('flee') if B.get('flee') is not None else 30, 'alarm': B.get('alarm') if B.get('alarm') is not None else 0,
            'services': services,
            'gold': max(_spread(rng, B.get('gold'), 0), int((B.get('gold') or [0, 0, 0])[1] * 0.6)) if services else 0,
            'wander': wander[1] if wander else 0, 'idles': B.get('idles') or [0] * 8, 'spot': None, 'relation': ''}


# ---------------------------------------------------------------- where they stand
def _world(lx, ly, rz):
    """A furniture's own-frame offset in the world (the inverse of roomsurvey._local)."""
    c, s = math.cos(rz), math.sin(rz)
    return lx * c + ly * s, -lx * s + ly * c


def _room_of(info, x, y):
    for rm in info['rooms']:
        if rm['x_min'] - 8 <= x <= rm['x_max'] + 8 and rm['y_min'] - 8 <= y <= rm['y_max'] + 8:
            return rm
    return None


def _clear(info, taken, x, y):
    if any(math.hypot(x - a, y - b) < CLEAR for a, b in taken):
        return False
    for r in info['refs']:
        if r['type'] in ('NPC_', 'CREA'):
            if math.hypot(x - r['p'][0], y - r['p'][1]) < CLEAR:
                return False
            continue
        b = r.get('b')
        if not b or r.get('arch') or r['type'] in ('LIGH',) or (b[5] - b[2]) * (r.get('s') or 1) < 25:
            continue
        s = r.get('s') or 1.0
        lx, ly = (x - r['p'][0]), (y - r['p'][1])
        c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
        ox, oy = lx * c - ly * sn, lx * sn + ly * c
        if b[0] * s - 18 <= ox <= b[3] * s + 18 and b[1] * s - 18 <= oy <= b[4] * s + 18:
            return False
    return True


def spot(db, info, p, rng, taken, used):
    """Where a person stands: by a piece of furniture the game stands their role at, at the game's own
    offset in its frame and facing; else somewhere clear on a room's floor. (x, y, z, rz, by)."""
    import furnish
    import peoplesurvey
    PS = peoplesurvey.survey(db)
    stands = (PS or {}).get('stands') or {}
    cands = []
    for f in info['furniture']:
        if f['k'] in used:
            continue
        st = stands.get((p['role'], f['fam']))
        if st and st['n'] >= 3:
            cands.append((st['n'], f, st))
    rng.shuffle(cands)
    cands.sort(key=lambda c: -c[0] * (0.5 + rng.random()))
    for _n, f, st in cands[:12]:
        fr = furnish.front_of(db, f['id']) or (0.0, -1.0)
        side = -1 if st.get('behind', 0) > 0.5 else 1
        d = st.get('dist') or 70
        lat = (rng.random() - 0.5) * min(60, st.get('dx') or 30)
        lx, ly = fr[0] * d * side - fr[1] * lat, fr[1] * d * side + fr[0] * lat
        wx, wy = _world(lx, ly, f['p'][5])
        x, y = f['p'][0] + wx, f['p'][1] + wy
        if not _clear(info, taken, x, y):
            continue
        rm = _room_of(info, x, y)
        z = (rm['floor'] if rm else f['p'][2]) + 4
        rz = (f['p'][5] + (st.get('turn') or 0) * math.pi / 2) % (2 * math.pi)
        used.add(f['k'])
        return [round(x, 1), round(y, 1), round(z, 1), round(rz, 4), f['fam']]
    # open floor: a clear spot in one of the rooms
    rooms = list(info['rooms'])
    rng.shuffle(rooms)
    for rm in rooms:
        for _t in range(25):
            x = rng.uniform(rm['x_min'] + 40, rm['x_max'] - 40) if rm['x_max'] - rm['x_min'] > 90 else (rm['x_min'] + rm['x_max']) / 2
            y = rng.uniform(rm['y_min'] + 40, rm['y_max'] - 40) if rm['y_max'] - rm['y_min'] > 90 else (rm['y_min'] + rm['y_max']) / 2
            if _clear(info, taken, x, y):
                return [round(x, 1), round(y, 1), round(rm['floor'] + 4, 1), round(rng.uniform(0, 2 * math.pi), 4), '']
    return None


# ---------------------------------------------------------------- the cast
def _two_rates(S, setting, culture):
    """How the game's homes of two of this kind (in this culture, when it has ten of them) are made up:
    {'couple': a man and a woman of one race, 'race': of one race otherwise}, as shares of all of them."""
    T = None
    for k in (setting + '|' + culture, setting):
        t = (S['casts'].get(k) or {}).get('two') or {}
        if t.get('two', 0) >= 10:
            T = t
            break
    if T is None:
        return {'couple': 0.40, 'race': 0.19}         # (the game's houses: 70 and 33 of 176)
    n = float(T['two'])
    return {'couple': T['two_mf_race'] / n, 'race': (T['two_race'] - T['two_mf_race']) / n}


def cast(db, cell_key, params=None, keep=None, seed=None):
    """A proposed cast for a place (nothing changes): {'place', 'setting', 'culture', 'count', 'people',
    'notes'}. keep: people from an earlier cast to keep as they are (the locked ones, or everyone but the
    one being made again)."""
    S = castsurvey.ready(db)
    if S is None:
        import learning
        return {'learning': learning.populate_pending(db) or ["the game's people"]}
    params = dict(params or {})
    rng = random.Random(seed if seed is not None else random.getrandbits(40))
    info = place_info(db, cell_key)
    setting = params.get('setting') or info['setting']
    C = _cast_of(S, setting, info['culture']) or {}
    count = params.get('count') or how_many(S, info, params.get('density') or 'usual')
    keep = list(keep or [])
    count = max(count, len(keep))
    notes = []
    if info['people'] and not keep:
        notes.append('%d already live here; these are on top of them.' % len(info['people']))
    # who: one of the groups the game's places of this kind have, then the place's classes in their shares
    classes = [[c, n] for c, n in (C.get('classes') or []) if c in S['classes']]
    occ = [o for o in params.get('occupations') or [] if o in S['classes']]
    only = params.get('only') and occ
    want = []
    if occ:
        want += occ
    elif not keep and setting == 'shop':
        # a shop's keeper is of its trade, as its name says (an outfitter's a clothier or a trader, a
        # smithy's a smith); the rest of its people as the game's shops have them
        low = info['name'].lower()
        words = next((ws for k, ws in TRADES if k in low), ('trader',))
        tc = [[c, B['n']] for c, B in S['classes'].items() if any(w in c.lower() for w in words) and B['n'] >= 3]
        cls = _w(rng, tc)
        if cls:
            want.append(cls)
    elif not keep:
        group = _w(rng, C.get('groups') or [])
        for role in (group or '').split(' + '):
            if role:
                cls = _w(rng, [[c, n] for c, n in classes if castsurvey.role_of(c) == role])
                if cls:
                    want.append(cls)
    pool = [[c, n] for c, n in classes if c in occ] if only else classes
    if setting == 'shop' and not only:
        # (the others in a shop are its customers, guards and helpers, not the keepers of other trades)
        trade = want[0] if want else None
        pool = [[c, n] for c, n in pool if c == trade or not any(int(b) < 14 and s >= 0.5 for b, s in S['classes'][c]['services'].items())]
    pool = pool or [['Commoner', 1]]
    taken = {p['name'].lower() for p in keep}
    family = None
    if setting in HOUSEHOLDS and C.get('families', 0) > 0 and rng.random() < 0.7:
        fams = [p for p in keep if p.get('relation') in ('head', 'family')]
        family = castsurvey._split_name(fams[0]['name'], fams[0]['race'])[1] if fams else None
    people = list(keep)
    spots_taken = [(p['spot'][0], p['spot'][1]) for p in keep if p.get('spot')]
    used = set(p['spot_by'] for p in keep if p.get('spot_by'))
    # a home of two: as often as the game's homes of two of this kind and culture, the head's wife or husband
    # (a man and a woman of one race: 40% of the game's houses of two, 70 of 176), else as often someone of
    # the head's race (59% are of one race), not two strangers picked apart
    two = _two_rates(S, setting, info['culture']) if setting in ('house', 'manor') and count == 2 and not occ else None
    while len(people) < count:
        cls = want.pop(0) if want else _w(rng, pool)
        head_ = people[0] if two and len(people) == 1 and people[0].get('relation') == 'head' else None
        if head_ is not None and not params.get('races'):
            roll = rng.random()
            if roll < two['couple']:
                for _t in range(8):         # (a commoner, a farmer, a smith: never a guard or a slave for a wife)
                    if not any(w in cls.lower() for w in NOT_HEADS + ('slave', 'servant')):
                        break
                    cls = _w(rng, pool)
                p = person(db, S, rng, cls, C, params, None, taken, race=head_['race'], female=not head_['female'])
                p['relation'], p['spouse'], head_['spouse'] = 'family', head_['key'], p['key']
                if family and p['race'].lower() not in SINGLE_NAMED:
                    p['name'] = _name(db, S, rng, p['race'], p['female'], family, taken)
                taken.add(p['name'].lower())
                sp = spot(db, info, p, rng, spots_taken, used)
                if sp:
                    p['spot'], p['spot_by'] = sp[:4], sp[4] or ''
                    spots_taken.append((sp[0], sp[1]))
                else:
                    notes.append('No clear spot for %s: they are left for you to place.' % p['name'])
                people.append(p)
                continue
            p = person(db, S, rng, cls, C, params, None, taken, race=head_['race'] if roll < two['couple'] + two['race'] else None)
        else:
            p = person(db, S, rng, cls, C, params, None, taken)
        # a household: the first is its head, the family shares the head's family name; servants and
        # lodgers keep their own
        if setting in HOUSEHOLDS:
            head = next((x for x in people if x.get('relation') == 'head'), None)
            # (a commoner, farmer or miner is the head of their own house; a slave or a servant never is)
            servant = any(w in p['cls'].lower() for w in ('slave', 'servant'))
            if head is None and not servant and not any(w in p['cls'].lower() for w in NOT_HEADS):
                p['relation'] = 'head'
                if p['race'].lower() not in SINGLE_NAMED:
                    family = family or castsurvey._split_name(p['name'], p['race'])[1]
            elif servant:
                p['relation'] = 'servant'
            elif any(w in p['cls'].lower() for w in NOT_HEADS):
                p['relation'] = 'guard'
            elif head is not None and p['race'] == head['race'] and family and rng.random() < 0.55 and p['race'].lower() not in SINGLE_NAMED:
                p['relation'] = 'family'
                p['name'] = _name(db, S, rng, p['race'], p['female'], family, taken)
            else:
                p['relation'] = 'lodger' if setting in ('house', 'manor') else 'patron' if setting == 'tavern' else ''
        taken.add(p['name'].lower())
        sp = spot(db, info, p, rng, spots_taken, used)
        if sp:
            p['spot'], p['spot_by'] = sp[:4], sp[4] or ''
            spots_taken.append((sp[0], sp[1]))
        else:
            notes.append('No clear spot for %s: they are left for you to place.' % p['name'])
        people.append(p)
    # their own words (poplines.py): made afresh with the cast, as its people refer to each other; lines
    # someone changed by hand are kept
    if params.get('lines', True) is not False:
        import poplines
        made = poplines.lines_for(people, info['name'], setting, rng)
        for p in people:
            if not p.get('lines_edited'):
                p['lines'] = made.get(p['key'], [])
    return {'place': info['name'], 'key': cell_key, 'setting': setting, 'culture': info['culture'], 'count': count,
            'people': people, 'notes': notes, 'already': len(info['people']),
            'options': {'settings': sorted(k for k in S['casts'] if '|' not in k),
                        'classes': [c for c, _n in classes[:30]], 'races': sorted({r for c in S['classes'].values() for r, _n in c['races'][:4]})}}


# ---------------------------------------------------------------- making it real
def _npc_record(db, nid, p):
    flags = 0x10 | 0x8 | (1 if p.get('female') else 0)          # autocalculated, as most of the game's generic people
    subs = [('NAME', zs(nid)), ('FNAM', zs(p['name'])), ('RNAM', zs(p['race'])), ('CNAM', zs(p['cls'])),
            ('ANAM', zs(p.get('faction') or '')), ('BNAM', zs(p.get('head') or '')), ('KNAM', zs(p.get('hair') or '')),
            ('NPDT', struct.pack('<hBBBxxxi', max(1, min(100, int(p.get('level') or 1))), 50, 0,
                                 max(0, min(9, int(p.get('rank') or 0))) if p.get('faction') else 0, max(0, int(p.get('gold') or 0)))),
            ('FLAG', struct.pack('<i', flags))]
    for it, n in (p.get('items') or [])[:60]:
        subs.append(('NPCO', struct.pack('<i', int(n)) + it.encode(ENC, 'replace')[:31].ljust(32, b'\0')))
    for s in (p.get('spells') or [])[:20]:
        subs.append(('NPCS', s.encode(ENC, 'replace')[:31].ljust(32, b'\0')))
    clamp = lambda v, d: max(0, min(100, int(v if v is not None else d)))
    subs.append(('AIDT', struct.pack('<BBBBBBBBi', clamp(p.get('hello'), 30), 0, clamp(p.get('fight'), 30), clamp(p.get('flee'), 30),
                                     clamp(p.get('alarm'), 0), 0, 0, 0, int(p.get('services') or 0))))
    idles = [max(0, min(100, int(v))) for v in (p.get('idles') or [0] * 8)][:8] + [0] * (8 - len((p.get('idles') or [])[:8]))
    subs.append(('AI_W', struct.pack('<hhB8BB', max(0, min(2000, int(p.get('wander') or 0))), 5, 0, *idles, 1)))
    return join_subs(subs)


def place(db, cell_key, people, own=True):
    """Make a cast real: each person a new NPC record placed where the cast says, the household's head
    owning the place's beds and containers (those nobody owns yet). One change, one Undo."""
    _require_project(db)
    import create
    from editing import _cell, _store, set_ref_pos
    from project import ref_info
    if not people:
        raise EditError('There is nobody to place.')
    info = place_info(db, cell_key)
    made = []
    for p in people:
        if not p.get('name') or not p.get('race') or not p.get('cls'):
            raise EditError('Everyone needs a name, a race and a class.')
        for f, tag in (('race', 'RACE'), ('cls', 'CLAS'), ('faction', 'FACT')):
            if p.get(f) and (db.resolve_id(p[f]) is None or db.recs[db.resolve_id(p[f])][0] != tag):
                raise EditError('%s: there is no %s called "%s".' % (p['name'], {'race': 'race', 'cls': 'class', 'faction': 'faction'}[f], p[f]))
        nid = create.suggest_id(db, create._prefix(db), p['name'])
        while any(m[0].lower() == nid.lower() for m in made):
            nid = create.suggest_id(db, create._prefix(db), p['name'] + ' %d' % len(made))
        db.project.set_record('NPC_', nid.lower(), 0, _npc_record(db, nid, p), created=True)
        made.append((nid, p))
    db.sync_project()
    c, refs = _cell(db, cell_key)
    placed = 0
    for nid, p in made:
        sp = p.get('spot')
        if not sp:
            continue
        rk = db.project.new_ref_key()
        origin, idx = rk.rsplit('|', 1)
        _store(c, rk, origin, int(idx), set_ref_pos([('NAME', zs(nid))], tuple(sp[:3]) + (0.0, 0.0, float(sp[3])), 1.0))
        placed += 1
    owned = 0
    head = next((nid for nid, p in made if p.get('relation') == 'head'), None)
    if own and head and info['setting'] in HOUSEHOLDS:
        for rk, ref in refs.items():
            rid, _pos, _s, deleted = ref_info(ref['subs'])
            ri = db.resolve_id(rid)
            low = rid.lower()
            # (only what can be taken from or slept in: containers, and beds, which are activators in the game)
            if deleted or ri is None or 'marker' in low or not (db.recs[ri][0] == 'CONT' or (db.recs[ri][0] == 'ACTI' and 'bed' in low)):
                continue
            if db.recs[ri][0] == 'CONT' and not any(w in low for w in OWNED):
                continue                       # (a corpse, a plant's harvest, a guild chest: not the household's)
            subs = list(ref['subs'])
            if any(t in ('ANAM', 'CNAM', 'BNAM') for t, _d in subs):
                continue                       # (already someone's, or a faction's, or rented)
            at = next((n for n, (t, _d) in enumerate(subs) if t in ('DODT', 'DNAM', 'UNAM', 'DATA')), len(subs))
            subs[at:at] = [('ANAM', zs(head))]
            _store(c, rk, ref['origin'], ref['idx'], subs)
            owned += 1
    said = write_lines(db, made)
    what = '%d %s' % (len(made), 'person' if len(made) == 1 else 'people')
    commit(db, 'Populated %s with %s%s%s' % (info['name'], what, (', who own its %d beds and containers' % owned) if owned else '',
                                            (' and have %d lines of their own' % said) if said else ''))
    return {'made': [nid for nid, _p in made], 'placed': placed, 'owned': owned, 'lines': said}


GREETING_TOPIC = 'greeting 5'      # (where the game's own people keep their own greetings, before the everyday ones)


def write_lines(db, made):
    """Each person's lines (p['lines']) as lines of the topics they belong to, theirs alone (the speaker is
    them), above the topic's other lines: a greeting on a first meeting (Talked to player before = 0) and
    one for later, a secret only to someone they like (disposition 60). The count written."""
    import dialogue
    talked = dialogue.FUNCTIONS.index('Talked to player before')
    by_topic = {}
    for nid, p in made:
        for ln in p.get('lines') or []:
            text = (ln.get('text') or '').strip()
            if not text:
                continue
            key = GREETING_TOPIC if ln.get('topic') == 'greeting' else (ln.get('topic') or '').lower()
            if not dialogue._dial_versions(db, key):
                continue                        # (a topic this load order doesn't have)
            # (topic lines need a disposition of 30, as Project Tamriel's dialogue guide asks of "almost all NPC
            # dialogue" and as the game's own topics do: its little secrets 541 of 1,076 at 30 and only 23 at 60;
            # greetings carry none, 1,949 of 17,993 in the game; 2026-10-24)
            conds, disp = [], 0 if key == GREETING_TOPIC else 30
            if ln.get('when') == 'first':
                conds.append({'kind': 'function', 'func': talked, 'op': '=', 'value': 0})
            elif ln.get('when') == 'again':
                conds.append({'kind': 'function', 'func': talked, 'op': '=', 'value': 1})
            by_topic.setdefault(key, []).append((nid, text[:1000], conds, disp))
    n = 0
    for key, lines in by_topic.items():
        dialogue._ensure_dial(db, key)
        t = dialogue._dial_type(db, dialogue._dial_versions(db, key)[-1])
        new = []
        for nid, text, conds, disp in lines:
            d = dict(dialogue.parse_info(b''))
            d.update(type=t, inam=dialogue._new_inam(db, key), actor=nid, text=text, conds=conds, disp=disp)
            dialogue._put(db, key, d, True)
            new.append(d['inam'])
            n += 1
        db.sync_project()
        rest = [x['inam'] for _ii, x in dialogue.ordered_lines(db, key) if x['inam'] not in set(new)]
        dialogue._relink(db, key, new + rest)
    return n
