"""How the game furnishes the rooms people trade in: the smith's, the alchemist's, the enchanter's, the
bookseller's, the clothier's, the general trader's, the pawnbroker's and the publican's. A trade is read off
the class of the people who work there (roomsurvey.class_of: "Smith", "Apothecary Service"...), and its room
is the room that person stands in (the same floor round them where the place has no kit rooms). For each
trade: which of the trade's own pieces stand there and in what share of places (the forge, the anvil and
the grindstone; the alchemy table and its apparatus; the counter), how far the smith's tools stand from the
fire that heats them, and which everyday pieces (a writing set, scales, an easel) the trade's rooms never
hold. Auto-furnish lays a trade room from its own anchor set by these (furnish.py: lay_trade), and the
health check's 'smithfire' kind flags a smith's tool with no fire within reach (placecheck.py).

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import kits
import mapdata
import roomsurvey

V = 'v1'
# the trades, by the words in their people's class (first match wins: a "Smith Service" is a smith, a
# "Trader Service" a trader)
TRADES = (('smith', re.compile(r'smith|armou?rer')),
          ('alchemist', re.compile(r'alchemist|apothecar')),
          ('enchanter', re.compile(r'enchanter')),
          ('bookseller', re.compile(r'bookseller')),
          ('clothier', re.compile(r'clothier|outfitter|tailor')),
          ('pawnbroker', re.compile(r'pawnbroker')),
          ('trader', re.compile(r'trader|merchant|general')),
          ('publican', re.compile(r'publican')))
# the pieces a trade's room is read for, by their IDs (and record types)
PIECES = {
    # the smith's
    'forge': (re.compile(r'forge(_|\d|$)|_forge|furnace|smithshed|smith_shed'), ('STAT', 'ACTI', 'LIGH')),
    'coals': (re.compile(r'coals_hot|coalpile|light_coals|_coals'), ('STAT', 'ACTI', 'LIGH', 'CONT')),
    'anvil': (re.compile(r'furn_anvil|anvil0|_anvil_\d|var_anvil'), ('STAT', 'ACTI')),
    'grindstone': (re.compile(r'grindstone|whetstone'), ('STAT', 'ACTI')),
    'bellows': (re.compile(r'bellows'), ('STAT', 'ACTI', 'MISC')),
    'smithtool': (re.compile(r'hammer|tongs|prongs'), ('REPA', 'MISC')),
    'smithstock': (re.compile(r'smith'), ('CONT',)),          # (Tamriel Data's armourer's and weaponsmith's crates)
    'rack': (re.compile(r'weaponrack|weapon_rack|armorrack|armourrack|armorstand|armourstand|mannequin'), ('STAT', 'ACTI', 'CONT')),
    # the alchemist's and the enchanter's
    'apparatus': (re.compile(r''), ('APPA',)),
    'soulgem': (re.compile(r'soulgem|soul_gem'), ('MISC', 'CONT')),
    'ingredient': (re.compile(r''), ('INGR',)),
    'potion': (re.compile(r''), ('ALCH',)),
    # the clothier's
    'clothbolt': (re.compile(r'clothbolt|cloth_bolt'), ('MISC', 'STAT')),
    'loom': (re.compile(r'(^|_)loom|spinning'), ('STAT', 'ACTI')),      # (not a bloom)
    'clothes': (re.compile(r''), ('CLOT',)),
    # the bookseller's
    'book': (re.compile(r''), ('BOOK',)),
    # the shop's
    'scales': (re.compile(r'scales'), ('MISC', 'ACTI', 'STAT')),
    'writing': (re.compile(r'inkwell|ink_well|inkpot|quill'), ('MISC', 'STAT')),
    'weapon': (re.compile(r''), ('WEAP',)),
    'armour': (re.compile(r''), ('ARMO',)),
    'easel': (re.compile(r'easel'), ('STAT', 'ACTI', 'MISC')),
}
NOT_PIECE = re.compile(r'marker|sign|banner|painting|window|throne|key|book|_uni_|forget|tapestr|scroll')
SMITH_TOOLS = ('anvil', 'grindstone', 'bellows')         # what a smith keeps by the fire that heats the metal
HEAT = ('forge', 'coals')                                 # (and a hearth: hearthsurvey.is_bearer)
FIRE_LIGHT = re.compile(r'light_fire|fire_nosmoke|logpile|_coals|flame|brazier|orange_fire')
# how near the fire the game stands each smith's tool, in its smiths' rooms (box to origin, 600 places,
# 2026-10-23): 27 of 30 anvils within 166 of their forge or fire (the other three with none on their floor),
# every standing bellows within 10; a grindstone anywhere in the forge's room (28 to 680)
REACH = {'anvil': 200, 'bellows': 60, 'grindstone': None}
SET_REACH = 260                                           # a forge's set: what stands this near its box
EXAMPLES = 30
NOT_MEMBER = re.compile(r'tapestr|banner|rug|carpet|marker|_nf$|collision|invisible|rope|hook|door|jamb|sign')
LIMIT = 600
_cache = {}
_thread = {}


def trade_of_class(cls):
    low = (cls or '').lower()
    for t, rx in TRADES:
        if rx.search(low):
            return t
    return None


def piece_of(rid, tag):
    """Which of PIECES a thing is, or None."""
    low = rid.lower()
    if NOT_PIECE.search(low) and tag not in ('BOOK', 'APPA'):
        return None
    for k, (rx, types) in PIECES.items():
        if tag in types and rx.search(low):
            if k == 'book' and tag != 'BOOK':
                continue
            return k
    return None


def _disk(db, limit):
    import taste
    return taste.cache_file('tradesurvey_%s_%d_%s' % (taste.sig(db), limit, V))


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
            _thread['t'] = background.start('how the game furnishes its smithies, apothecaries and shops', lambda: survey(db, limit),
                                            task=('tradesurvey', 'survey', [limit]))
        except Exception:
            import threading
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


def _cells_of(db, rids):
    """The game-made interiors that use any of these records."""
    keys = set()
    for rid in rids:
        for ci in db.used_in.get(rid.lower(), ()):
            if db.recs[ci][0] == 'CELL':
                keys.add(db.recs[ci][7])
    out = []
    for k in keys:
        if not k or k.startswith('#') or not kits.game_made(db, k):
            continue
        ci = mapdata.cell_info(db, k)
        if ci and ci.get('interior'):
            out.append(k)
    return sorted(out)


def _traders(db):
    """{npc id: trade} for every NPC record whose class is a trade's."""
    out = {}
    for r in db.recs:
        if r[0] != 'NPC_':
            continue
        t = trade_of_class(roomsurvey.class_of(db, r[1]))
        if t:
            out[r[1].lower()] = t
    return out


def _box(r):
    import fixit
    return fixit._world_box(r)


def _named_hearth(db, rid):
    """A hearth by its name and size (hearthsurvey's test without its survey: a survey never waits on, or
    starts, another one)."""
    import hearthsurvey
    if not hearthsurvey.named_bearer(rid.lower()):
        return False
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    return bool(b) and max(b[3] - b[0], b[4] - b[1]) >= 60 and (b[5] - b[2]) >= 30


def _dist(o, h):
    """How far o's origin stands outside h's box in the floor plan (0 inside it)."""
    hb = h['_box']
    return math.hypot(max(hb[0] - o['p'][0], 0, o['p'][0] - hb[3]), max(hb[1] - o['p'][1], 0, o['p'][1] - hb[4]))


def _survey(db, limit):
    import furnish
    traders = _traders(db)
    smith_ids = [r[1] for r in db.recs if r[0] in ('STAT', 'ACTI') and piece_of(r[1], r[0]) in SMITH_TOOLS + ('forge',)]
    import taste
    # (every place with a forge or a smith's tool first, then the traders' places)
    first = taste.order(_cells_of(db, smith_ids))
    first_ = set(first)
    cells = first + [c for c in taste.order(_cells_of(db, list(traders))) if c not in first_][:limit * 3]
    forges = {}                    # forge model: {n, kits, size, sets}
    rooms_out = []                 # one row per trade room
    tools = []                     # one row per smith's tool anywhere: (cell, piece, id, distance to heat or None, the room's trade)
    seen = 0
    for ck in cells:
        if seen >= limit:
            break
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        npcs = [r for r in m['refs'] if r['type'] == 'NPC_' and r['id'].lower() in traders]
        if not npcs and not any(r['type'] in ('STAT', 'ACTI') and piece_of(r['id'], r['type']) in SMITH_TOOLS + ('forge',) for r in m['refs']):
            continue
        refs = []
        for r in m['refs']:
            if not r.get('b') or r['type'] in ('CREA', 'DOOR', 'LEVC', 'LEVI', 'NPC_'):
                continue
            r['_piece'] = piece_of(r['id'], r['type'])
            if r.get('arch') and not r['_piece']:
                continue                     # (the building; but a forge over 200 across is "architecture" to the map reader)
            r['_box'] = _box(r)
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
            refs.append(r)
        # (the fire may be a building piece to the map reader: a forge or a kit fireplace over 200 across is
        # "architecture"; and a fire light burning in a forge or a hearth counts as its fire)
        heat = []
        for r in m['refs']:
            if not r.get('b') or r['type'] not in ('STAT', 'ACTI', 'LIGH', 'CONT'):
                continue
            if '_box' not in r:
                r['_box'] = _box(r)
                r['_piece'] = piece_of(r['id'], r['type'])
            low = r['id'].lower()
            if r['_box'] and (r['_piece'] in HEAT or (r['type'] in ('STAT', 'ACTI') and _named_hearth(db, r['id']))
                              or (r['type'] == 'LIGH' and FIRE_LIGHT.search(low))):
                r['_heat'] = r['_piece'] if r['_piece'] in HEAT else 'firelight' if r['type'] == 'LIGH' else 'hearth'
                heat.append(r)
        has_tool = any(r['_piece'] in SMITH_TOOLS for r in refs)
        if not npcs and not has_tool:
            continue
        seen += 1
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            info = {'rooms': []}
        name = (mapdata.cell_info(db, ck) or {}).get('name') or ck
        theme = roomsurvey.theme_of(name)
        styles = Counter(kits.kit_prefix(r['id']) for r in m['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
        style = styles.most_common(1)[0][0] if styles else ''

        def room_at(p):
            for rm in info['rooms']:
                if rm['x_min'] - 20 <= p[0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= p[1] <= rm['y_max'] + 20 and -60 <= p[2] - rm['floor'] <= 250:
                    return rm
            return None

        def around(p, rm):
            if rm is not None:
                return [r for r in refs if rm['x_min'] - 20 <= r['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= r['p'][1] <= rm['y_max'] + 20
                        and rm['floor'] - 60 <= r['p'][2] <= rm['floor'] + 260]
            return [r for r in refs if math.hypot(r['p'][0] - p[0], r['p'][1] - p[1]) < 900 and -150 <= r['p'][2] - p[2] <= 260]
        # the trade rooms: one per trade per room (two smiths at one forge are one smithy)
        done = set()
        trade_here = {}
        for n in npcs:
            t = traders[n['id'].lower()]
            rm = room_at(n['p'])
            k = (t, rm['id'] if rm else (round(n['p'][0] / 512), round(n['p'][1] / 512), round(n['p'][2] / 256)))
            if k in done:
                continue
            done.add(k)
            inside = around(n['p'], rm)
            floor_level = [r for r in refs if -150 <= r['p'][2] - n['p'][2] <= 260]
            counts = Counter(r['_piece'] for r in inside if r['_piece'])
            place_counts = Counter(r['_piece'] for r in floor_level if r['_piece'])
            fams = Counter(r['_fam'] for r in inside if r['_fam'])
            ids = Counter(r['id'].lower() for r in inside if r['_piece'] in ('forge', 'coals', 'anvil', 'grindstone', 'bellows', 'scales', 'writing', 'rack', 'loom'))
            row = {'cell': ck, 'name': name, 'theme': theme, 'style': style, 'trade': t, 'room': rm['name'] if rm else None,
                   'tiles': rm['tiles'] if rm else None, 'pieces': dict(counts), 'place': dict(place_counts), 'fams': dict(fams), 'ids': dict(ids),
                   'heat_in_room': sum(1 for r in inside if r in heat)}
            # the everyday pieces' distance from the trade's own: the writing set and the scales from the anvil
            anv = [r for r in inside if r['_piece'] in SMITH_TOOLS and r['_box']]
            if anv:
                row['writing_to_tool'] = [round(min(_dist(r, a) for a in anv)) for r in inside if r['_piece'] in ('writing', 'scales')]
            rooms_out.append(row)
            if rm is not None:
                trade_here[rm['id']] = t
        # every smith's tool here, and how far the nearest fire is
        for r in refs:
            if r['_piece'] not in SMITH_TOOLS or r['type'] not in ('STAT', 'ACTI'):
                continue
            rm = room_at(r['p'])
            hs = [h for h in heat if h is not r and -150 <= h['_box'][2] - r['_box'][2] <= 150]
            d = min((_dist(r, h) for h in hs), default=None)
            near_kind = None
            if hs:
                h0 = min(hs, key=lambda h: _dist(r, h))
                near_kind = h0['_heat']
            tools.append({'cell': ck, 'piece': r['_piece'], 'id': r['id'].lower(), 'd': None if d is None else round(d),
                          'heat': near_kind, 'trade': trade_here.get(rm['id']) if rm else None, 'theme': theme, 'style': style,
                          'same_room': bool(rm) and any(room_at(h['p']) is rm for h in hs)})
        # every forge here with its set: what stands within SET_REACH of its box on its floor, in its frame
        for f in refs:
            if f['_piece'] != 'forge' or f['type'] not in ('STAT', 'ACTI') or not f['_box']:
                continue
            low = f['id'].lower()
            F = forges.setdefault(low, {'n': 0, 'kits': Counter(), 'size': None, 'sets': []})
            F['n'] += 1
            F['kits'][style] += 1
            fb = f['_box']
            F['size'] = [round(fb[3] - fb[0]), round(fb[4] - fb[1]), round(fb[5] - fb[2])]
            c_, s_ = math.cos(f['p'][5]), math.sin(f['p'][5])
            fs = f.get('s') or 1.0
            mem = []
            for o in refs:
                if o is f or not o['_box'] or not (-60 <= o['_box'][2] - fb[2] <= 200) or _dist(o, f) > SET_REACH:
                    continue
                if o['type'] not in ('STAT', 'ACTI', 'CONT', 'MISC', 'REPA', 'LIGH', 'WEAP', 'ARMO') or NOT_MEMBER.search(o['id'].lower()):
                    continue
                dx, dy = o['p'][0] - f['p'][0], o['p'][1] - f['p'][1]
                mem.append({'id': o['id'], 'type': o['type'], 'piece': o['_piece'], 'fam': o['_fam'],
                            'x': round((dx * c_ - dy * s_) / fs, 1), 'y': round((dx * s_ + dy * c_) / fs, 1),
                            'z': round((o['p'][2] - f['p'][2]) / fs, 1), 'rz': round((o['p'][5] - f['p'][5]) % (2 * math.pi), 3),
                            'rx': round(o['p'][3], 3), 'ry': round(o['p'][4], 3), 's': round(o.get('s') or 1.0, 3),
                            'in': fb[0] - 4 <= o['p'][0] <= fb[3] + 4 and fb[1] - 4 <= o['p'][1] <= fb[4] + 4,
                            'd': round(_dist(o, f))})
            F['sets'].append({'cell': ck, 'kit': style, 'theme': theme, 'smith': any(t == 'smith' for t in trade_here.values()),
                              'members': mem})
    for F in forges.values():
        F['kits'] = dict(F['kits'])
        F['sets'].sort(key=lambda d: -sum(1 for m in d['members'] if m['piece'] in SMITH_TOOLS))
        F['sets'] = F['sets'][:EXAMPLES]
    return {'cells': seen, 'rooms': rooms_out, 'tools': tools, 'forges': forges, 'stats': _stats(rooms_out, tools)}


def _q(v, f):
    v = sorted(v)
    return v[min(len(v) - 1, int(f * len(v)))] if v else None


def _stats(rooms_out, tools):
    """Per trade: rooms, the share holding each piece, the median count where held; the smith's tools'
    distances to their fire."""
    by = defaultdict(list)
    for r in rooms_out:
        by[r['trade']].append(r)
    out = {}
    for t, rs in by.items():
        n = len(rs)
        share = {}
        for k in PIECES:
            have = [r['pieces'].get(k, 0) for r in rs if r['pieces'].get(k)]
            share[k] = {'share': round(len(have) / float(n), 3), 'median': _q(have, 0.5) or 0,
                        'place': round(sum(1 for r in rs if r['place'].get(k)) / float(n), 3)}
        fams = Counter()
        for r in rs:
            fams.update({f: 1 for f in r['fams']})
        ids = Counter()
        for r in rs:
            ids.update(r['ids'])
        out[t] = {'rooms': n, 'pieces': share, 'fams': {f: round(c / float(n), 3) for f, c in fams.most_common()},
                  'ids': dict(ids.most_common(25)), 'themes': dict(Counter(r['theme'] for r in rs)),
                  'heat_in_room': round(sum(1 for r in rs if r['heat_in_room']) / float(n), 3)}
    ds = [x['d'] for x in tools if x['d'] is not None]
    out['_tools'] = {'n': len(tools), 'no_heat': sum(1 for x in tools if x['d'] is None),
                     'heat': dict(Counter(x['heat'] for x in tools)), 'cells': len({x['cell'] for x in tools}),
                     'd': {q: _q(ds, q) for q in (0.5, 0.75, 0.9, 0.95)},
                     'within': {str(R): round(sum(1 for d in ds if d <= R) / float(len(tools) or 1), 3) for R in (150, 250, 400, 600, 900)},
                     'by_piece': {p: {'n': sum(1 for x in tools if x['piece'] == p), 'no_heat': sum(1 for x in tools if x['piece'] == p and x['d'] is None),
                                      'd50': _q([x['d'] for x in tools if x['piece'] == p and x['d'] is not None], 0.5),
                                      'd90': _q([x['d'] for x in tools if x['piece'] == p and x['d'] is not None], 0.9)} for p in SMITH_TOOLS}}
    return out


# ---------------------------------------------------------------- what Auto-furnish and the check go by

def tool_of(rid, tag):
    """'anvil', 'bellows' or 'grindstone' for a smith's tool that stands, else None (not the loose bellows one can
    pick up: the game leaves those lying anywhere, a woodworker's, a fighters' guild's; 3 of 100 game places)."""
    p = piece_of(rid, tag)
    if p in SMITH_TOOLS and tag in ('STAT', 'ACTI'):
        return p
    return None


def heat_of(db, rid, tag):
    """'forge', 'coals', 'hearth' or 'firelight' for something a smith could heat metal at, else None."""
    p = piece_of(rid, tag)
    if p in HEAT:
        return p
    low = rid.lower()
    if tag == 'LIGH' and FIRE_LIGHT.search(low):
        return 'firelight'
    if tag in ('STAT', 'ACTI'):
        import hearthsurvey
        if hearthsurvey.is_bearer(db, rid):
            return 'hearth'
    return None


ANCHOR = 0.3          # a piece another trade is known by: in 30% of its rooms or more
FOREIGN = 0.12        # and this trade's rooms hold it in fewer than one in eight
# (the figures of the first survey, 600 places, 2026-10-23, for when the survey is not to hand)
FOREIGN_FALLBACK = {
    'smith': ('apparatus', 'soulgem', 'clothbolt', 'loom', 'scales', 'writing'),
    'alchemist': ('forge', 'anvil', 'soulgem', 'clothbolt', 'loom'),
    'enchanter': ('forge', 'anvil', 'clothbolt', 'loom', 'scales'),
    'bookseller': ('forge', 'anvil', 'apparatus', 'soulgem', 'clothbolt', 'loom'),
    'clothier': ('forge', 'anvil', 'apparatus', 'soulgem'),
    'pawnbroker': ('forge', 'anvil', 'loom'),
    'trader': ('forge', 'anvil', 'soulgem', 'loom'),
}
CHECKED = ('forge', 'anvil', 'bellows', 'apparatus', 'soulgem', 'clothbolt', 'loom', 'scales', 'writing')
PIECE_NAMES = {'forge': 'a forge', 'anvil': 'an anvil', 'bellows': 'a smith\'s bellows', 'apparatus': 'an alchemist\'s apparatus',
               'soulgem': 'a soul gem', 'clothbolt': 'a bolt of cloth', 'loom': 'a loom or spinning wheel', 'scales': 'a merchant\'s scales',
               'writing': 'a writing set'}


def foreign(db, trade):
    """The pieces a trade's rooms never hold: those another trade is known by (in ANCHOR of its rooms) that
    this trade's hold in fewer than FOREIGN of theirs (a smithy's writing set and scales, an apothecary's
    soul gems, anyone's anvil but a smith's). A set of PIECES names."""
    s = ready(db)
    st = (s or {}).get('stats') or {}
    if trade not in st or st[trade]['rooms'] < 10:
        return set(FOREIGN_FALLBACK.get(trade, ()))
    out = set()
    for k in CHECKED:
        own = st[trade]['pieces'].get(k, {}).get('share', 0)
        if own >= FOREIGN:
            continue
        if any(t != trade and not t.startswith('_') and S['rooms'] >= 10 and S['pieces'].get(k, {}).get('share', 0) >= ANCHOR
               for t, S in st.items()):
            out.add(k)
    return out


SCENE_PIECE = {'scribe': 'writing', 'alchemist': 'apparatus', 'smith': 'anvil', 'painter': 'easel'}
FORGE_KEEP = re.compile(r'anvil|bellows|coals|coalpile|light_fire|logpile|grindstone|hammer|prongs|tongs|repair_|bucket|barrelwater|'
                        r'quench|metalpiece|metalblank|ingot|(^|_)log_|stool|shovel|smith')


def forge_choices(db, kit, height=None):
    """The forges a smithy in a house of this kit takes, best first: [(id, figures)], or None until surveyed.
    The kit's own (Gold Coast's t_imp_setgc_i_forge_01, Hlaalu's t_de_sethla_f_forge_01), then those the
    game's places of its culture stand, then of its broad culture (hearthsurvey's), then the commonest;
    never a Legion fort's floor pit outside a fort's kit, never a forge three storeys tall."""
    import furnish
    import hearthsurvey
    import wealthsurvey
    s = ready(db)
    if not s:
        return None
    cult = hearthsurvey.culture_of_kit(kit)
    broad = hearthsurvey.BROAD.get(cult)
    fam = hearthsurvey._family(kit)
    out = []
    for k, F in (s.get('forges') or {}).items():
        if db.resolve_id(k) is None or not F.get('size'):
            continue
        if wealthsurvey.culture_of(k) in furnish.CULTURE_FORBIDS.get(broad, ()):
            continue                  # (Project Tamriel's rule, as furnish.put keeps it: no Dunmer forge in an Imperial house)
        if F['size'][2] > max(hearthsurvey.TALL, 3 * (height or 0)):
            continue
        if 'legion' in k and 'legion' not in (kit or '').lower():
            continue                  # (a fort's forge pit, 62 tall: the Legion's kit's own)
        kp = hearthsurvey.KIT_PIECE.match(k)
        mine = bool(fam) and k.startswith(fam)
        if kp and not mine and not k.startswith('t_com_'):
            continue                  # (another kit's built forge: a Reach forge is not a Gold Coast house's)
        cults = Counter()
        for kit2, n in F['kits'].items():
            cults[hearthsurvey.culture_of_kit(kit2)] += n
        own = cults.get(cult, 0)
        same = sum(n for c, n in cults.items() if broad and hearthsurvey.BROAD.get(c) == broad)
        # (Tamriel Data's common make, t_com_, before a borrowed culture's: the Gold Coast smiths' own)
        rank = 0 if mine else 1 if own else 1.5 if k.startswith('t_com_') else 2 if same else 3
        out.append((rank, -F['n'], k, F))
    out.sort(key=lambda t: t[:2])
    return [(k, F) for _r, _n, k, F in out]


def forge_set(db, rid, rng):
    """One of the game's sets round this forge model, the smith's pieces only (the anvil, the bellows, the
    coals and the fire in it, the grindstone, the tools, the quench bucket, the logs and the stool): [member
    dicts in the forge's frame]. Sets with an anvil within reach first. None when the survey has none."""
    s = ready(db)
    F = ((s or {}).get('forges') or {}).get(rid.lower())
    if not F or not F['sets']:
        return None
    pool = []
    for d in F['sets']:
        mem = [m for m in d['members'] if FORGE_KEEP.search(m['id'].lower()) and (m['type'] not in ('WEAP', 'ARMO'))
               and not re.search(r'^t_[a-z]+_set[a-z]*_|^(in|ex)_|_dng', m['id'].lower())]
        if mem:
            pool.append(dict(d, members=mem))
    if not pool:
        return None
    with_anvil = [d for d in pool if any(m['piece'] == 'anvil' and m['d'] <= REACH['anvil'] for m in d['members'])]
    return rng.choice(with_anvil or pool)


def report(db, limit=LIMIT):
    s = survey(db, limit)
    out = ['%d places walked; %d trade rooms' % (s['cells'], len(s['rooms']))]
    for t, S in sorted(s['stats'].items()):
        if t == '_tools':
            continue
        pcs = ', '.join('%s %.0f%%%s' % (k, v['share'] * 100, (' x%d' % v['median']) if v['median'] > 1 else '')
                        for k, v in sorted(S['pieces'].items(), key=lambda kv: -kv[1]['share']) if v['share'] >= 0.05)
        out.append('%s: %d rooms (themes %s), fire in the room %.0f%%' % (t, S['rooms'], S['themes'], S['heat_in_room'] * 100))
        out.append('   pieces: %s' % pcs)
        out.append('   furniture: %s' % ', '.join('%s %.0f%%' % (f, v * 100) for f, v in list(S['fams'].items())[:16]))
        out.append('   models: %s' % list(S['ids'].items())[:14])
    out.append('smith tools: %s' % s['stats']['_tools'])
    return out
