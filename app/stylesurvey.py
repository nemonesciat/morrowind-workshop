"""The Style palette's learning: which building pieces, furniture, decor and sets go with each building
style (theme) of the game's places, so someone who has never built can pick a theme and see what goes
together: the Hlaalu walls and the furniture the game puts in Hlaalu houses, the lights it hangs there,
its tables with their chairs.

A place's theme is told from its building pieces (each kit's names: in_hlaalu_..., t_de_setveloth_...,
t_imp_setgc_...). Each of the game's own places is then a greenlist of the things found in it (the
user's idea): an object belongs to a theme when it concentrates in that theme's places compared with
everywhere (its lift, share there over share anywhere) and is no extraordinary one-off there (a few
places and a few per cent of the theme's places at least). What many themes use alike (crates, sacks,
bread, common clutter) is listed once, as "Used everywhere".

A second, geometric pass over a sample of each theme's places reads what the game stands next to each
thing and puts on it ("goes with") and the sets it puts together (a table with its chairs, a bed with
its chest); the hearth and scene surveys' whole sets are added by theme when they are to hand. The
joins between building pieces come from the adjacency survey.

Learnt only from places the game (or another mod) made; kept in the cache folder by load order once
done (taste.cache_file), run in the survey process by ready(). Cold: about 10 s (2026-10-25)."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import kits
import mapdata

V = 'v5'                   # v2: rugs, hearths, beds and nomad furniture by name first; no shackles as plants; v3: planters, trees, cushions, hearth tools
# (name, the kit families that build it, a line for people). A family is an id's first parts: in_hlaalu,
# ex_hlaalu, t_de_sethla (t_<culture>_<set>); a place's theme is the one most of its pieces belong to.
THEMES = [
    ('Hlaalu', ('in_hlaalu', 'ex_hlaalu', 't_de_sethla'), 'House Hlaalu: plaster and timber, the West Gash and the Ascadian Isles'),
    ('Redoran', ('in_redoran', 'in_r', 'ex_redoran', 't_de_setred'), 'House Redoran: shell-shaped halls of the Ashlands'),
    ('Telvanni', ('in_t', 'ex_t', 't_de_settel', 't_de_settelv'), 'House Telvanni: grown mushroom towers'),
    ('Velothi', ('in_velothismall', 'in_velothilarge', 'in_velothi', 'in_v', 'in_vs', 'in_vsl', 'ex_velothi', 'ex_vivec', 'ex_v',
                 't_de_setveloth'), 'Velothi stone: temples, tombs, Vivec and the plain Dunmer houses'),
    ('Indoril', ('t_de_setind',), 'House Indoril (Tamriel Rebuilt)'),
    ('Mournhold', ('in_mh', 'in_om', 'in_m', 'ex_mh', 't_de_setmh', 't_de_setom', 't_de_setomc'), 'Mournhold and Old Mournhold'),
    ('Necrom', ('t_de_setnecrom',), 'Necrom, the city of the dead (Tamriel Rebuilt)'),
    ('Dunmer common', ('in_de', 'ex_de', 't_de_set'), 'Plain Dunmer shacks, huts and ships'),
    ('Dunmer stronghold', ('in_strong', 'in_stronghold', 'in_strongruin', 'in_strongruin2', 'ex_stronghold', 'ex_strongruin',
                           'ex_strongholdruin'), 'The old Dunmer strongholds'),
    ('Imperial', ('in_c', 'in_common', 'ex_common', 't_imp_setmw', 't_imp_set'), 'Imperial colonists\' houses, shops and offices'),
    ('Imperial Legion', ('in_impsmall', 'in_impbig', 'ex_imp', 't_imp_legion', 't_imp_legionmw', 't_imp_legioncyr'),
     'The Legion\'s forts, keeps and castles'),
    ('Imperial chapel', ('t_imp_setchapel', 't_imp_setchapelmw'), 'The Imperial Cult\'s chapels'),
    ('Gold Coast', ('t_imp_setgc', 't_imp_setgcpoor', 't_imp_setgcrich'), 'Cyrodiil\'s Gold Coast (Project Cyrodiil)'),
    ('Anvil', ('t_imp_setanv', 't_imp_setstr'), 'Anvil\'s pale ashlar (Project Cyrodiil)'),
    ('Farm', ('t_com_setfarm', 't_imp_setfarm', 't_nor_setfarm'), 'Farmhouses and barns'),
    ('Ship & harbour', ('t_com_setharbor', 't_imp_setharbor', 't_nor_setharbor', 't_he_setharbor', 't_rga_setharbor',
                        't_we_setharbor', 't_de_setharbor', 't_imp_setairship'), 'Ships\' holds, cabins and harbour houses'),
    ('Nord', ('in_nord', 'ex_nord', 'in_s', 'ex_s', 'in_greathall', 'in_thirsk', 'in_bm', 't_nor_set', 't_nor_setlogcabin',
              't_nor_setpalisade', 't_nor_setmarkarth', 't_imp_setnord', 't_imp_setsky'), 'Nords: log halls, Skaal huts, barrows'),
    ('Reach', ('t_rga_setreach', 't_rea_set', 't_bre_setostf'), 'The Reach (Project Tamriel)'),
    ('Ashlander', ('in_ashl', 'ex_ashl'), 'The Ashlanders\' yurts'),
    ('Orc', ('t_orc_setnomad',), 'Orc camps and strongholds'),
    ('Dwemer', ('in_dwrv', 'in_dwe', 'ex_dwrv'), 'Dwemer ruins'),
    ('Daedric', ('in_dae', 'ex_dae'), 'Daedric shrines'),
    ('Cave', ('in_cave', 'ex_cave', 'in_cavern', 'in_mold', 'in_moldcave', 'in_moldcave2', 'in_mud', 'in_mudcave', 'in_mudcave2',
              'in_py', 'in_pycave', 'in_pycave2', 'in_pycave4', 'in_lava', 'in_lavacave', 'in_lavacave2', 'in_lavacave4', 'in_bonecave',
              'in_bonecave2', 'in_bone', 'in_ar', 'in_icesheet', 'in_glacier'), 'Caves, grottoes and lava tubes'),
    ('Mine', ('t_com_setmine',), 'Mines with their timber props'),
    ('Sewer', ('in_sewer',), 'Sewers and underworks'),
]
THEME_OF_FAMILY = {f: name for name, fams, _l in THEMES for f in fams}
# the themes' cultures: "Used everywhere" is what the game stands alike in most of them (a Dunmer chair is in
# every Dunmer theme's places and none of the others': it is Dunmer, not everywhere)
CULTURE = {'Hlaalu': 'Dunmer', 'Redoran': 'Dunmer', 'Telvanni': 'Dunmer', 'Velothi': 'Dunmer', 'Indoril': 'Dunmer', 'Mournhold': 'Dunmer',
           'Necrom': 'Dunmer', 'Dunmer common': 'Dunmer', 'Dunmer stronghold': 'Dunmer', 'Ashlander': 'Dunmer',
           'Imperial': 'Imperial', 'Imperial Legion': 'Imperial', 'Imperial chapel': 'Imperial', 'Gold Coast': 'Imperial',
           'Anvil': 'Imperial', 'Farm': 'Imperial', 'Ship & harbour': 'Imperial',
           'Nord': 'Northern', 'Reach': 'Northern', 'Orc': 'Northern',
           'Dwemer': 'Ruins', 'Daedric': 'Ruins', 'Cave': 'Ruins', 'Mine': 'Ruins', 'Sewer': 'Ruins'}
EVERY_CULTURES = 3
ORDER = [t[0] for t in THEMES]
MIN_PLACES = 8               # a theme with fewer of the game's places isn't listed
SECTIONS = ('Shell', 'Furniture', 'Decor')
# learning: an object goes with a theme when its share of the theme's places is LIFT times its share of
# all places or more, it stands in MIN_N of the theme's places and in MIN_SHARE of them (no one-offs)
LIFT = 1.8
MIN_N = 3
MIN_SHARE = 0.03
# "Used everywhere": in EVERY_SHARE of the places of EVERY_CULTURES cultures (CULTURE) or more, listed
# there once and in no theme
EVERY_SHARE = 0.03
PER_GROUP = 60               # pieces kept per group of a theme's section
SAMPLE = 45                  # places per theme read for "goes with" and sets
NEAR = 130                   # two things this close (origin to origin, flat) stand together
SKIP_TYPES = {'NPC_', 'CREA', 'LEVC', 'LEVI', 'WEAP', 'ARMO', 'CLOT', 'LOCK', 'PROB', 'REPA', 'BODY', 'SPEL'}
NOT_PIECE = re.compile(r'marker|collision|invisible|blocker|_nolor|^xx|^t_glb_|editor|_sound|sound_|_fx_|^fx_|^ab_|^tr_m\d_|^tr_i\d_|light_fire|smoke|'
                       r'^furn_de_ex_|^active_|_trigger|trigger_|^terrain_|_water|water_')
_cache = {}
_thread = {}


def family(low):
    """An id's kit family: in_hlaalu, ex_de, t_de_sethla, t_imp_legionmw (None for anything else)."""
    p = low.split('_')
    if p[0] in ('in', 'ex') and len(p) > 2:
        return p[0] + '_' + p[1]
    if p[0] == 't' and len(p) > 3 and (p[2].startswith('set') or p[2].startswith('legion')):
        return 't_' + p[1] + '_' + p[2]
    return None


def piece_theme(low):
    """The theme a building piece's name puts it in, or None."""
    f = family(low)
    return THEME_OF_FAMILY.get(f) if f else None


def place_theme(db, ids):
    """A place's theme from the building pieces it holds (a set of lower-case ids): the theme most of its
    themed pieces belong to, with three of them at least and two in five of the themed ones; else None."""
    c = Counter()
    for low in ids:
        t = piece_theme(low)
        if t and ('STAT', low) in db.by_key:
            c[t] += 1
    if not c:
        return None
    t, n = c.most_common(1)[0]
    if n < 3 or n < 0.4 * sum(c.values()):
        return None
    return t


def theme_here(db, cell_key):
    """The open place's theme (for "Only what fits here"), by the same rule as the game's places."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists'):
        return None
    return place_theme(db, {r['id'].lower() for r in m['refs']})


def _greenlists(db):
    """Every game-made interior's things: {cell key: set of lower-case ids} (from the records' use lists,
    no place read)."""
    cells = defaultdict(set)
    for low, cis in db.used_in.items():
        for ci in cis:
            r = db.recs[ci]
            if r[0] == 'CELL' and r[7] and not r[7].startswith('#'):
                cells[r[7]].add(low)
    return {k: v for k, v in cells.items() if kits.game_made(db, k)}


# ------------------------------------------------------------------ what a thing is, for the palette
ROCK = re.compile(r'rock|boulder|stalag|rubble|cave|crystal|_vein|lavavent|lava_vent|terrrock|icicle')
_WORDS = [
    ('Shell', 'Stairs', re.compile(r'stair|step|ramp|ladder')),
    ('Shell', 'Doorways & doors', re.compile(r'door|entr|jamb|gate|portcullis|arch(?!ive)')),
    ('Shell', 'Columns & posts', re.compile(r'column|pillar|post|pole|beam|support|strut|buttress')),
    ('Shell', 'Floors & ceilings', re.compile(r'floor|ceil|roof|platform|plat_|dome|cap')),
    ('Shell', 'Windows', re.compile(r'window')),
    ('Shell', 'Rooms & walls', re.compile(r'wall|corner|side|room|hall|center|centre|cent|end|connector|tunnel|corr|cor_|_cor|ledge|rail|'
                                          r'tile|house|tent|yurt|hut|shack')),
    ('Shell', 'Rocks & rubble', ROCK),
]
_FURN_GROUP = {'bed': 'Beds', 'bedroll': 'Beds', 'table': 'Tables', 'chair': 'Seats', 'bench': 'Seats',
               'chest': 'Storage', 'cupboard': 'Storage', 'crate': 'Storage', 'barrel': 'Storage', 'sack': 'Storage', 'urn': 'Storage',
               'basket': 'Storage', 'counter': 'Counters & shelves', 'shelf': 'Counters & shelves', 'bookshelf': 'Counters & shelves',
               'winerack': 'Counters & shelves', 'rack': 'Counters & shelves', 'fire': 'Hearths & ovens', 'shrine': 'Shrines & altars',
               'screen': 'Other furniture', 'bath': 'Other furniture', 'target': 'Other furniture'}
_DECOR_FAM = {'rug': 'Rugs & mats', 'planter': 'Plants', 'dish': 'Tableware & food', 'bottle': 'Tableware & food',
              'food': 'Tableware & food', 'book': 'Books & papers', 'candle': 'Lights'}
GROUPS = {'Shell': ['Rooms & walls', 'Floors & ceilings', 'Doorways & doors', 'Windows', 'Stairs', 'Columns & posts', 'Rocks & rubble', 'Outside',
                    'Other pieces'],
          'Furniture': ['Beds', 'Tables', 'Seats', 'Storage', 'Counters & shelves', 'Hearths & ovens', 'Shrines & altars', 'Other furniture'],
          'Decor': ['Lights', 'Rugs & mats', 'Wall hangings', 'Plants', 'Tableware & food', 'Books & papers', 'Clutter']}


# what a name says before its size does: a big rug or a kit's fireplace is no building piece, and a bed is a
# bed whatever its family (the Telvanni bed, the Orcs' nomad bed); a kit's own furniture ("_f_") by its word
_NAME_FIRST = [
    (re.compile(r'shackle|manacle|shovel|poker|tongs|broom|fireplacehook|fireplacestand'), ('Decor', 'Clutter')),   # (not Telvanni's ex_t_hook)
    (re.compile(r'rug|carpet|pelt|bearskin|wolfskin|cushion'), ('Decor', 'Rugs & mats')),
    (re.compile(r'fireplace|hearth|(^|_)oven|kiln|stove|firepit'), ('Furniture', 'Hearths & ovens')),
    (re.compile(r'planter|(^|_)flora_|_tree_|(^|_)tree\d'), ('Decor', 'Plants')),
]
_KIT_FURN = [
    (re.compile(r'bed|bunk|hammock'), 'Beds'), (re.compile(r'table|desk'), 'Tables'),
    (re.compile(r'stool|chair|bench|seat'), 'Seats'), (re.compile(r'chest|crate|barrel|sack|basket|cupboard|closet'), 'Storage'),
    (re.compile(r'rack|shelf|counter'), 'Counters & shelves'),
]


def _by_name(low, tag):
    for rx, where in _NAME_FIRST:
        if rx.search(low):
            return where
    # (furniture by its name: furn_..., a kit's _f_ pieces, T_..._Furn_...; never a building piece such as a mine
    # cart's bed or a bunk-house wall)
    if 'furn' in low or '_f_' in low:
        for rx, grp in _KIT_FURN:
            if rx.search(low):
                return ('Furniture', grp)
    # (a sack or a basket of something is a store, though the something is a plant: hackle-lo leaves)
    if tag == 'CONT' and re.search(r'sack|(^|_)sk\d|basket|(^|_)bs\d|crate|barrel', low):
        return ('Furniture', 'Storage')
    return None


def classify(db, low):
    """(section, group, record) for a thing, or None when it isn't for the palette."""
    ri = db.resolve_id(low)
    if ri is None:
        return None
    r = db.recs[ri]
    tag = r[0]
    if tag in SKIP_TYPES or NOT_PIECE.search(low):
        return None
    if tag == 'DOOR':
        return ('Shell', 'Doorways & doors', r)
    if tag not in ('STAT', 'ACTI', 'CONT', 'LIGH', 'MISC', 'BOOK', 'ALCH', 'INGR', 'APPA'):
        return None
    if tag != 'LIGH':
        named = _by_name(low, tag)
        if named:
            return named + (r,)
    b = mapdata.object_bounds(db, ri)
    if tag in ('STAT', 'ACTI') and re.search(r'(^|_)web\d|cobweb', low):
        return ('Decor', 'Clutter', r)
    if tag in ('STAT', 'ACTI') and low.startswith('furn_c_t_'):
        return ('Furniture', 'Shrines & altars', r)     # (the Imperial Cult's shrines: furn_c_t_akatosh_01...)
    if tag == 'STAT' and ROCK.search(low) and not family(low):
        return ('Shell', 'Rocks & rubble', r)
    if tag in ('STAT', 'ACTI') and (family(low) or mapdata.is_architecture(tag, r[1], b)):
        import roomsurvey
        fam = roomsurvey.family_of(db, r[1], tag)
        if fam in _FURN_GROUP and not family(low):
            return ('Furniture', _FURN_GROUP[fam], r)     # (a big piece of furniture: a Redoran kiln, a long bar)
        if low.startswith('ex_') or '_x_' in low or '_ex_' in low:
            for sec, grp, rx in _WORDS[:3]:
                if rx.search(low):
                    return (sec, grp, r)
            return ('Shell', 'Outside', r)
        for sec, grp, rx in _WORDS:
            if rx.search(low):
                return (sec, grp, r)
        return ('Shell', 'Other pieces', r)
    if tag == 'LIGH':
        return ('Decor', 'Lights', r)
    import roomsurvey
    fam = roomsurvey.family_of(db, r[1], tag)
    if tag in ('STAT', 'ACTI', 'CONT') and fam in _FURN_GROUP:
        return ('Furniture', _FURN_GROUP[fam], r)
    if fam in _DECOR_FAM:
        return ('Decor', _DECOR_FAM[fam], r)
    if tag in ('STAT', 'ACTI', 'CONT', 'MISC', 'INGR') and mapdata._PLANT_RE.search(r[1]):
        return ('Decor', 'Plants', r)
    if tag in ('STAT', 'ACTI'):
        k = mapdata._palette_kind(r[1], b)
        if k == 'Wall hangings':
            return ('Decor', 'Wall hangings', r)
        if k == 'Rugs & mats':
            return ('Decor', 'Rugs & mats', r)
        if b and (b[5] - b[2]) >= 60 and max(b[3] - b[0], b[4] - b[1]) >= 60:
            return ('Furniture', 'Other furniture', r)
        return ('Decor', 'Clutter', r)
    if tag == 'CONT':
        return ('Furniture', 'Storage', r)
    if tag == 'BOOK':
        return ('Decor', 'Books & papers', r)
    return ('Decor', 'Clutter', r)


# ------------------------------------------------------------------ the survey
def _disk(db):
    import taste
    return taste.cache_file('stylesurvey_%s_%s' % (taste.sig(db), V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the survey process."""
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
        _thread['t'] = background.start("the game's styles and what goes with them", lambda: survey(db), task=('stylesurvey', 'survey', []))
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
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(out, f)
            os.replace(tmp, path)
        except Exception:
            pass
    return out


def learn(green, theme_of, keep=None):
    """The greenlist learning on its own (also for the held-out check): green {cell: ids}, theme_of {cell:
    theme}; keep: the cells to learn from (all when None). {'n': {theme: places}, 'count': {id: {theme:
    places}}, 'total': {id: places}, 'all': places}."""
    n = Counter()
    count = defaultdict(Counter)
    total = Counter()
    for ck, ids in green.items():
        t = theme_of.get(ck)
        if not t or (keep is not None and ck not in keep):
            continue
        n[t] += 1
        for low in ids:
            count[low][t] += 1
            total[low] += 1
    return {'n': n, 'count': count, 'total': total, 'all': sum(n.values())}


def assign(L, low, themes=None):
    """The themes an object goes with by the learning L: [(theme, places, share, lift)], best lift first;
    and whether it is "used everywhere". (themes: only these.) The lift is against the mean of every
    theme's share, each theme counting once: two places in three are Dunmer, and against the pooled share
    a Dunmer chair would concentrate nowhere."""
    c = L['count'].get(low)
    if not c or not L['all']:
        return [], False
    names = [t for t in L['n'] if L['n'][t] >= MIN_PLACES and (themes is None or t in themes)]
    if not names:
        return [], False
    shares = {t: c.get(t, 0) / float(L['n'][t]) for t in names}
    base = sum(shares.values()) / len(names)
    out = []
    by_culture = defaultdict(list)
    for t in names:
        by_culture[CULTURE.get(t, t)].append(shares[t])
        k = c.get(t, 0)
        share = shares[t]
        lift = share / base if base else 0.0
        if lift >= LIFT and k >= MIN_N and share >= MIN_SHARE:
            out.append((t, k, share, lift))
    out.sort(key=lambda x: -x[3])
    # (everywhere: a staple of most cultures, by each culture's mean share)
    wide = sum(1 for v in by_culture.values() if sum(v) / len(v) >= EVERY_SHARE)
    return out, wide >= EVERY_CULTURES and L['total'][low] >= 20


def _survey(db):
    import time
    t0 = time.time()
    green = _greenlists(db)
    theme_of = {}
    for ck, ids in green.items():
        t = place_theme(db, ids)
        if t:
            theme_of[ck] = t
    L = learn(green, theme_of)
    themes = [t for t in ORDER if L['n'][t] >= MIN_PLACES]
    examples = defaultdict(list)          # theme -> places, most varied first (for "Show me in the game")
    for ck in sorted(theme_of):
        examples[theme_of[ck]].append(ck)
    items = {}
    per = {t: {s: defaultdict(list) for s in SECTIONS} for t in themes}
    every = defaultdict(list)
    cls_memo = {}
    for low, total in L['total'].items():
        if low not in cls_memo:
            cls_memo[low] = classify(db, low)
        cl = cls_memo[low]
        if not cl:
            continue
        sec, grp, r = cl
        got, everywhere = assign(L, low, set(themes))
        if everywhere and sec != 'Shell':
            got = []                      # (listed once, under "Used everywhere", not in every theme)
        own = piece_theme(low) if sec == 'Shell' else None
        if own in themes and own not in [g[0] for g in got]:
            # (a kit's own piece is its theme's, however few places stand it)
            k = L['count'][low].get(own, 0)
            got.append((own, k, k / float(L['n'][own]), 0.0))
        if not got and not everywhere:
            continue
        it ={'id': r[1], 'name': r[2], 'type': r[0], 'sec': sec, 'grp': grp, 'n': total, 'mesh': (r[5] or '').lower(),
              'th': {t: [k, round(sh, 3), round(lf, 2)] for t, k, sh, lf in got}}
        items[low] = it
        for t, k, sh, lf in got:
            per[t][sec][grp].append((sh, low))
        if everywhere:
            it['every'] = round(total / float(L['all']), 3)
            every[(sec, grp)].append((total, low))
    # where each one stands in the game, a few places per theme (for "Show me in the game")
    want = {low: {t: [] for t in it['th']} for low, it in items.items()}
    for ck in sorted(green):
        t = theme_of.get(ck)
        if not t:
            continue
        for low in green[ck]:
            w = want.get(low)
            if w is not None and t in w and len(w[t]) < 3:
                w[t].append(ck)
    for low, w in want.items():
        items[low]['at'] = w
        if 'every' in items[low]:
            items[low]['at_any'] = next((ck for ck in green if low in green[ck] and ck in theme_of), None)
    lists = {}
    for t in themes:
        lists[t] = {}
        for sec in SECTIONS:
            lists[t][sec] = {g: [low for _s, low in sorted(per[t][sec][g], key=lambda x: -x[0])[:PER_GROUP]] for g in GROUPS[sec] if per[t][sec][g]}
    everywhere = {}
    for (sec, grp), lst in every.items():
        everywhere.setdefault(sec, {})[grp] = [low for _n, low in sorted(lst, key=lambda x: -x[0])[:PER_GROUP]]
    t1 = time.time()
    goes, sets = _geometry(db, theme_of, themes, examples, items)
    _add_joins(db, items, goes)
    _add_survey_sets(db, sets, theme_of, themes)
    out = {'v': V, 'themes': {t: {'places': L['n'][t], 'line': next(x[2] for x in THEMES if x[0] == t),
                                  'examples': examples[t][:6]} for t in themes},
           'order': themes, 'items': items, 'lists': lists, 'everywhere': everywhere, 'goes': goes, 'sets': sets,
           'places': len(theme_of), 'unthemed': len(green) - len(theme_of),
           'secs': {'learn': round(t1 - t0, 1), 'geometry': round(time.time() - t1, 1)}}
    return out


# ------------------------------------------------------------------ goes with, and sets
def _spread(lst, n):
    if len(lst) <= n:
        return list(lst)
    step = len(lst) / float(n)
    return [lst[int(k * step)] for k in range(n)]


def _geometry(db, theme_of, themes, examples, items):
    """What the game stands next to each thing and puts on it, and its sets, from SAMPLE places a theme:
    ({id: [[other, n, 'next'|'on'|'under']]}, {theme: [set]})."""
    import roomsurvey
    from project import ref_info
    pairs = defaultdict(Counter)
    found = {t: defaultdict(list) for t in themes}
    fam_memo, box_memo = {}, {}

    def fam(low, tag):
        if low not in fam_memo:
            fam_memo[low] = roomsurvey.family_of(db, low, tag)
        return fam_memo[low]

    def box(low):
        if low not in box_memo:
            ri = db.resolve_id(low)
            box_memo[low] = (mapdata.object_bounds(db, ri), db.recs[ri][0]) if ri is not None else (None, None)
        return box_memo[low]

    for t in themes:
        for ck in _spread(examples[t], SAMPLE):
            try:
                refs, _h = db.cell_refs(ck)
            except Exception:
                continue
            things = []
            for _rk, ref in refs.items():
                rid, pos, scale, dead = ref_info(ref['subs'])
                low = rid.lower()
                if dead or low not in items or items[low]['sec'] == 'Shell':
                    continue
                b, tag = box(low)
                if not b:
                    continue
                s = scale or 1.0
                things.append({'low': low, 'id': items[low]['id'], 'type': tag, 'p': pos, 's': s, 'b': b, 'fam': fam(low, tag),
                               'top': pos[2] + b[5] * s, 'bot': pos[2] + b[2] * s})
            for a in things:
                for o in things:
                    if o is a or o['low'] == a['low']:
                        continue
                    dx, dy = o['p'][0] - a['p'][0], o['p'][1] - a['p'][1]
                    if abs(dx) > 260 or abs(dy) > 260:
                        continue
                    # on it: its foot inside the box and at the top
                    c, sn = math.cos(a['p'][5]), math.sin(a['p'][5])
                    lx, ly = (dx * c - dy * sn) / a['s'], (dx * sn + dy * c) / a['s']
                    b = a['b']
                    if b[0] <= lx <= b[3] and b[1] <= ly <= b[4] and -6 <= o['bot'] - a['top'] <= 30 and a['top'] - a['bot'] > 20:
                        pairs[a['low']][(o['low'], 'on')] += 1
                        pairs[o['low']][(a['low'], 'under')] += 1
                    elif math.hypot(dx, dy) < NEAR and abs(o['bot'] - a['bot']) < 40:
                        pairs[a['low']][(o['low'], 'next')] += 1
            _find_sets(things, found[t], ck)
    goes = {}
    for low, c in pairs.items():
        top = [[o, n, how] for (o, how), n in c.most_common(10) if n >= 2]
        if top:
            goes[low] = top[:8]
    sets = {}
    for t in themes:
        lst = []
        for (kind, sig), exs in found[t].items():
            if len(exs) < 2:
                continue                  # (seen once: an odd one, not what the theme does)
            exs.sort(key=lambda e: e['spread'])
            ex = exs[len(exs) // 2]
            lst.append({'kind': kind, 'label': ex['label'], 'n': len(exs), 'cell': ex['cell'], 'items': ex['items'],
                        'cells': sorted({e['cell'] for e in exs})[:4]})
        lst.sort(key=lambda s: -s['n'])
        # (a few of each kind: the commonest two tables with chairs, not twenty of them, so the theme's other
        # sets show)
        keep, per_kind = [], Counter()
        for s in lst:
            if per_kind[s['kind']] < (2 if s['kind'] == 'table' else 4):
                keep.append(s)
                per_kind[s['kind']] += 1
        sets[t] = keep
    return goes, sets


SEATS = ('chair', 'bench')
STORE = ('chest', 'cupboard')


def _item(o, ref):
    """A member of a set in the anchor's frame (the group placer's form; dz from the anchor's foot)."""
    dx, dy = o['p'][0] - ref['p'][0], o['p'][1] - ref['p'][1]
    c, s = math.cos(ref['p'][5]), math.sin(ref['p'][5])
    return {'id': o['id'], 'type': o['type'], 'dx': round(dx * c - dy * s, 1), 'dy': round(dx * s + dy * c, 1),
            'dz': round(o['p'][2] - ref['bot'], 1), 'rx': round(o['p'][3], 4), 'ry': round(o['p'][4], 4),
            'rz': round((o['p'][5] - ref['p'][5]) % (2 * math.pi), 4), 's': round(o['s'], 3)}


def _find_sets(things, found, ck):
    """The sets in one place: a table with its seats (and what is on it), a bed with its chest or cupboard."""
    used = set()
    for a in things:
        if a['fam'] not in ('table', 'bed'):
            continue
        near = []
        for o in things:
            if o is a or id(o) in used:
                continue
            d = math.hypot(o['p'][0] - a['p'][0], o['p'][1] - a['p'][1])
            reach = max(a['b'][3] - a['b'][0], a['b'][4] - a['b'][1]) * a['s'] / 2.0 + 80
            if d > reach or abs(o['bot'] - a['bot']) > 40:
                continue
            if a['fam'] == 'table' and o['fam'] in SEATS:
                near.append(o)
            elif a['fam'] == 'bed' and o['fam'] in STORE + ('table',):
                near.append(o)
        if a['fam'] == 'table':
            seats = [o for o in near if o['fam'] in SEATS]
            if len(seats) < 2:
                continue
            members = seats[:6]
            kind, label = 'table', 'Table and %d %s' % (len(members), 'seats' if any(o['fam'] == 'bench' for o in members) else 'chairs')
        else:
            stores = [o for o in near if o['fam'] in STORE]
            if not stores:
                continue
            members = stores[:1] + [o for o in near if o['fam'] == 'table'][:1]
            kind, label = 'bed', 'Bed with a %s%s' % (stores[0]['fam'], ' and a side table' if len(members) > 1 else '')
        used.add(id(a))
        used.update(id(o) for o in members)
        ref = a
        its = [_item(a, ref)] + [_item(o, ref) for o in members]
        sig = (kind, a['low'], tuple(sorted(o['low'] for o in members)))
        spread = sum(abs(i['dx']) + abs(i['dy']) for i in its)
        found[(kind, sig)].append({'cell': ck, 'label': label, 'items': its, 'spread': spread})


def _add_joins(db, items, goes):
    """Building pieces: what the game joins to each one (the adjacency survey's faces), as 'joins'."""
    try:
        import adjacency
        sv = adjacency.ready(db)
    except Exception:
        sv = None
    if not sv:
        return
    joins = defaultdict(Counter)
    for pre, rec in sv.items():
        for aid, sides in (rec.get('adj') or {}).items():
            low = aid.lower()
            if low not in items:
                continue
            for side in sides.values():
                for k, n in (side.get('c') or {}).items():
                    o = k.split('|')[0].lower()
                    if o != low:
                        joins[low][o] += n
    for low, c in joins.items():
        top = [[o, n, 'joins'] for o, n in c.most_common(8) if n >= 2]
        if top:
            goes[low] = top + (goes.get(low) or [])[:4]


def _add_survey_sets(db, sets, theme_of, themes):
    """The hearth and scene surveys' whole sets, by the theme of the place each example came from."""
    try:
        import hearthsurvey
        h = hearthsurvey.ready(db)
    except Exception:
        h = None
    for k, F in ((h or {}).get('models') or {}).items():
        if F.get('pit'):
            continue
        by = defaultdict(list)
        for d in F.get('sets') or []:
            t = theme_of.get(d.get('cell'))
            if t in sets and 2 <= len(d['members']) <= 14:
                by[t].append(d)
        ri = db.resolve_id(k)
        if ri is None:
            continue
        b = mapdata.object_bounds(db, ri)
        for t, lst in by.items():
            if len(lst) < 2:
                continue
            lst.sort(key=lambda d: len(d['members']))
            d = lst[len(lst) // 2]
            bot = (b[2] if b else 0) * (d.get('s') or 1.0)
            its = [{'id': db.recs[ri][1], 'type': db.recs[ri][0], 'dx': 0.0, 'dy': 0.0, 'dz': round(-bot, 1), 'rx': 0, 'ry': 0, 'rz': 0, 's': d.get('s') or 1.0}]
            for m in d['members']:
                its.append({'id': m['id'], 'type': m.get('type', 'STAT'), 'dx': m['x'], 'dy': m['y'], 'dz': round(m['z'] - bot, 1), 'rx': 0, 'ry': 0,
                            'rz': m.get('rz', 0), 's': m.get('s', 1.0)})
            # (named for what it is, not its id: the picture tells one fireplace from another)
            low = db.recs[ri][1].lower()
            what = next((w for k, w in (('fireplace', 'Fireplace'), ('stove', 'Stove'), ('oven', 'Oven'), ('kiln', 'Kiln'), ('firepit', 'Fire pit'))
                         if k in low), 'Hearth')
            sets[t].append({'kind': 'hearth', 'label': db.recs[ri][2] or '%s with its things' % what, 'n': len(lst),
                            'cell': d['cell'], 'items': its, 'cells': sorted({x['cell'] for x in lst})[:4]})
    # (the two hearths a theme has most often, not six fireplaces)
    for t in sets:
        hs = sorted((x for x in sets[t] if x['kind'] == 'hearth'), key=lambda x: -x['n'])[2:]
        sets[t] = [x for x in sets[t] if not any(x is y for y in hs)]
    try:
        import scenesurvey
        s = scenesurvey.ready(db)
    except Exception:
        s = None
    names = {'painter': "Painter's corner", 'alchemist': "Alchemist's bench", 'smith': "Smith's corner", 'scribe': "Scribe's desk"}
    for sk, S in ((s or {}).get('scenes') or {}).items():
        by = defaultdict(list)
        for e in S.get('examples') or []:
            t = theme_of.get(e.get('cell'))
            if t in sets and 3 <= e['n'] <= 16:
                by[t].append(e)
        for t, lst in by.items():
            lst.sort(key=lambda e: e['n'])
            e = lst[len(lst) // 2]
            its = []
            if e.get('base'):
                ri = db.resolve_id(e['base']['id'])
                if ri is None:
                    continue
                its.append({'id': db.recs[ri][1], 'type': db.recs[ri][0], 'dx': 0.0, 'dy': 0.0, 'dz': 0.0, 'rx': 0, 'ry': 0, 'rz': 0, 's': 1.0})
            for m in e['members']:
                its.append({'id': m['id'], 'type': m['type'], 'dx': m['x'], 'dy': m['y'], 'dz': m['zo'], 'rx': m.get('rx', 0), 'ry': m.get('ry', 0),
                            'rz': m['rz'], 's': m.get('s', 1.0)})
            sets[t].append({'kind': sk, 'label': names.get(sk, sk), 'n': len(lst), 'cell': e['cell'], 'items': its,
                            'cells': sorted({x['cell'] for x in lst})[:4]})


# ------------------------------------------------------------------ for the page
def themes(db):
    """The list of themes for the window's tabs: {'ready', 'themes': [{name, places, line}], 'waiting'}."""
    s = ready(db)
    if not s:
        import learning
        return {'ready': False, 'waiting': learning._names() or ["the game's styles"]}
    return {'ready': True, 'themes': [{'name': t, 'places': s['themes'][t]['places'], 'line': s['themes'][t]['line']} for t in s['order']],
            'everywhere': True, 'places': s['places']}


def _place_name(db, ck):
    info = mapdata.cell_info(db, ck)
    return (info or {}).get('name') or ck


def _name_of(db, s, low):
    """(id, name, type) for a "goes with" entry."""
    it = s['items'].get(low)
    if it:
        return it['id'], it['name'], it['type']
    ri = db.resolve_id(low)
    return (db.recs[ri][1], db.recs[ri][2], db.recs[ri][0]) if ri is not None else (low, '', '')


def _row(db, s, low, theme):
    it = s['items'][low]
    if db.resolve_id(low) is None:
        return None
    th = it['th'].get(theme)
    at = (it.get('at') or {}).get(theme) or ([it['at_any']] if it.get('at_any') else [])
    row = {'id': it['id'], 'name': it['name'], 'type': it['type'], 'mesh': it['mesh'], 'grp': it['grp'],
           'share': th[1] if th else it.get('every', 0), 'places': th[0] if th else it['n'], 'lift': th[2] if th else None,
           'at': [[ck, _place_name(db, ck)] for ck in at], 'also': [t for t in it['th'] if t != theme][:4]}
    g = s['goes'].get(low)
    if g:
        row['goes'] = [list(_name_of(db, s, o)) + [n, how] for o, n, how in g]
    return row


def theme(db, name):
    """One theme's palette: {'name', 'places', 'line', 'sections': {Shell|Furniture|Decor: [{group, items}]},
    'sets': [...], 'examples'}; name '*' is "Used everywhere"."""
    s = ready(db)
    if not s:
        return None
    if name == '*':
        secs = s['everywhere']
        out = {'name': 'Used everywhere', 'places': s['places'], 'line': 'What the game stands in places of every style alike: '
               'crates, sacks, bread and the common clutter', 'sets': [], 'examples': []}
    else:
        if name not in s['themes']:
            return None
        secs = s['lists'][name]
        out = {'name': name, 'places': s['themes'][name]['places'], 'line': s['themes'][name]['line'],
               'sets': [st for st in s['sets'].get(name, []) if all(db.resolve_id(i['id']) is not None for i in st['items'])],
               'examples': s['themes'][name]['examples']}
    out['sections'] = {}
    for sec in SECTIONS:
        groups = []
        for g in GROUPS[sec]:
            rows = [r for r in (_row(db, s, low, name) for low in (secs.get(sec) or {}).get(g, [])) if r]
            if rows:
                groups.append({'group': g, 'items': rows})
        out['sections'][sec] = groups
    for st in out['sets']:
        _set_feet(db, st)
        st['places'] = [[ck, _place_name(db, ck)] for ck in st.get('cells') or []]
        st['place'] = _place_name(db, st['cell'])
    out['examples'] = [[ck, _place_name(db, ck)] for ck in out['examples']]
    return out


def _set_feet(db, st):
    """A set's items as the group placer wants them: dz from the set's lowest point."""
    if st.get('_feet'):
        return
    lows = []
    for i in st['items']:
        ri = db.resolve_id(i['id'])
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        lows.append(i['dz'] + ((b[2] if b else 0) * (i.get('s') or 1.0)))
    m = min(lows) if lows else 0
    for i in st['items']:
        i['dz'] = round(i['dz'] - m, 1)
    st['_feet'] = True


# ------------------------------------------------------------------ measuring it
def holdout(db, folds=5):
    """How well the learning holds on places it never saw: the places split in `folds`, each part's
    places checked against the learning from the others. For each held-out place: of its things the
    learning puts in some theme, the share whose themes include the place's own (precision), against the
    share expected by chance; and whether the theme its things vote for most is its own (accuracy)."""
    green = _greenlists(db)
    theme_of = {ck: t for ck, t in ((ck, place_theme(db, ids)) for ck, ids in green.items()) if t}
    keys = sorted(theme_of)
    by_theme = defaultdict(lambda: {'places': 0, 'hit': 0, 'judged': 0, 'right': 0, 'voted': 0, 'culture': 0})
    cls = {}
    for f in range(folds):
        test = set(keys[f::folds])
        L = learn(green, theme_of, keep=set(keys) - test)
        names = {t for t in ORDER if L['n'][t] >= MIN_PLACES}
        for ck in test:
            t = theme_of[ck]
            if t not in names:
                continue
            B = by_theme[t]
            B['places'] += 1
            votes = Counter()
            for low in green[ck]:
                if family(low):
                    continue                  # (the building pieces told the theme: not a test of the learning)
                if low not in cls:
                    cls[low] = classify(db, low)
                if not cls[low]:
                    continue
                got, _e = assign(L, low, names)
                if not got:
                    continue
                B['judged'] += 1
                if t in [g[0] for g in got]:
                    B['hit'] += 1
                for g in got:
                    votes[g[0]] += math.log(g[3])
            if votes:
                B['voted'] += 1
                best = votes.most_common(1)[0][0]
                if best == t:
                    B['right'] += 1
                if CULTURE.get(best) == CULTURE.get(t):
                    B['culture'] += 1
    out = {}
    allp = sum(B['places'] for B in by_theme.values())
    for t, B in by_theme.items():
        out[t] = {'places': B['places'], 'precision': round(B['hit'] / float(B['judged'] or 1), 3),
                  'chance': round(B['places'] / float(allp or 1), 3), 'accuracy': round(B['right'] / float(B['voted'] or 1), 3),
                  'culture': round(B['culture'] / float(B['voted'] or 1), 3), 'voted': B['voted']}
    return out


def report(db, top=12):
    s = survey(db)
    out = ['%d themed places (%d without a theme), learnt in %s s' % (s['places'], s['unthemed'], s['secs'])]
    for t in s['order']:
        out.append('== %s: %d places' % (t, s['themes'][t]['places']))
        for sec in SECTIONS:
            for g, lst in s['lists'][t][sec].items():
                out.append('   %s / %s (%d): %s' % (sec, g, len(lst), ', '.join('%s %.0f%%' % (s['items'][l]['id'], 100 * s['items'][l]['th'][t][1]) for l in lst[:top])))
        out.append('   sets: %s' % '; '.join('%s x%d' % (x['label'], x['n']) for x in s['sets'].get(t, [])))
    out.append('== Used everywhere')
    for sec, gs in s['everywhere'].items():
        for g, lst in gs.items():
            out.append('   %s / %s (%d): %s' % (sec, g, len(lst), ', '.join(s['items'][l]['id'] for l in lst[:top])))
    return out
