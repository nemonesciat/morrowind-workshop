"""Who the game's people are, place by place (2026-10-23): the survey Populate learns from.

For every game-made place with people in it (indoors and out, caves and ruins too), what kind of place it is
(its setting: a house, tavern, shop, temple, guild or manor of a culture, a cave, a mine, a Dwemer or Daedric
ruin, a tomb, a stronghold, an Ashlander camp, a stretch of a region outdoors) and, for each person placed
there, their race, sex, class, faction and rank, level, what they wear slot by slot and what else they carry,
their spells, services and barter gold, their AI (hello, fight, flee, alarm, wander), head and hair; and the
creatures and creature lists placed there.

Folded into what Populate asks for:
- casts: by setting, who is there (class shares with their race, sex, faction and level), how many people
  per place, and which roles turn up together (a publican with servers and patrons; a smuggler boss with
  smugglers);
- outfits: by class and wealth, the clothes and armour per slot, and the other things carried;
- names: by race and sex, first and family names, and the titles the game names generic people by
  ("Ordinator", "Imperial Guard");
- faces: heads and hairs by race and sex, as the game's people wear them;
- the spells, AI, services and barter gold of each class; the creatures of each setting.

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import os
import re
import struct
from collections import Counter, defaultdict

from esm import iter_subrecords, zstr

V = 'v7'           # (v5: 'tower', a place with a Velothi tower's pit: its mages, not a house's people; v6: 'crowd', creatures a
#                   place; v7: 'bands', the dungeons' bands by kind)
TOP = 24                    # (most common entries kept per list)
CLOT_SLOTS = ['pants', 'shoes', 'shirt', 'belt', 'robe', 'glove_r', 'glove_l', 'skirt', 'ring', 'amulet']
ARMO_SLOTS = ['helmet', 'cuirass', 'pauldron_l', 'pauldron_r', 'greaves', 'boots', 'gauntlet_l', 'gauntlet_r', 'shield',
              'bracer_l', 'bracer_r']
# places named for what they are, before the building pieces say
NAME_SETTINGS = (('tomb', ('tomb', 'barrow', 'crypt', 'catacomb', 'burial', 'ossuary', 'ancestral vault')),
                 ('cave', ('cave', 'grotto', 'cavern')), ('mine', ('mine', 'egg mine')),
                 ('stronghold', ('stronghold',)), ('ruin', ('ruin',)), ('camp', ('camp', 'yurt')),
                 ('sewer', ('sewer', 'underworks', 'canalworks')))
# what the room survey's themes miss (they'd be "house"): checked after them, words whole
MORE_THEMES = (('guard', ('guard tower', 'guardtower', 'watchtower', 'guardhouse', 'gatehouse', 'prison', 'jail', 'gaol', 'keep',
                          'garrison', 'outpost', 'armory', 'armoury', 'dungeon')),
               ('temple', ('fane', 'sanctum', 'sanctuary', 'cathedral', 'cloister', 'abbey', 'priory', 'chantry', 'oratory')),
               ('tavern', ('alehouse', 'meadhall', 'mead hall', 'taproom', 'brewhouse', 'tradehouse')),
               ('shop', ('herbalist', 'merchant', 'weapon', 'armor', 'goods', 'supplies', 'bazaar', 'market', 'emporium',
                         'provisioner', 'provisions', 'tailor', 'jeweler', 'jeweller', 'dealer', 'book', 'curio', 'pawn',
                         'smithy', 'enchanter', 'enchantress', 'fletcher', 'bowyer', 'scribe')),
               ('guild', ('office', 'court', 'judgement', 'judgment', 'arena', 'academy', 'college', 'library', 'archive',
                          'hall of', 'consulate', 'treasury', 'bank', 'company', 'society', 'tollhouse', 'clerk', 'counting house')),
               ('plaza', ('plaza', 'canton', 'waistworks', 'waist', 'square', 'market hall')))
STYLE_SETTINGS = {'Cave': 'cave', 'Mine': 'mine', 'Sewer': 'sewer', 'Dwemer': 'dwemer', 'Daedric': 'daedric',
                  'Ruin': 'ruin', 'Stronghold': 'stronghold', 'Ashlander': 'camp'}
GENERIC_WORDS = re.compile(r'\b(guard|ordinator|legion|soldier|watchman|buoyant|sharpshooter|archer|knight|warrior|'
                           r'smuggler|bandit|thief|slave|pilgrim|dreamer|worshipper|cultist|necromancer|witch|'
                           r'hunter|miner|farmer|commoner|noble|priest|monk|acolyte|sailor|fisherman)\b', re.I)
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('castsurvey_%s_%s' % (taste.sig(db), V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception as e:
        print("who the game's people are: couldn't read the survey:", repr(e))
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start("who the game's people are", lambda: survey(db), task=('castsurvey', 'survey', []))
    return None


def survey(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache['survey'] = (db.recs, out)
            return out
    except Exception:
        pass
    out = fold(db, read_places(db))
    _cache['survey'] = (db.recs, out)
    if path:
        # (written beside it and swapped in whole: the server asks for it while the survey process writes it)
        try:
            with open(path + '.part', 'w', encoding='utf-8') as f:
                json.dump(out, f)
            os.replace(path + '.part', path)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- records
def _winner(db, tag, rid):
    lst = [v for v in db.by_key.get((tag, (rid or '').lower()), []) if v not in db.dead]
    return lst[-1] if lst else None


def _subs(db, ri):
    r = db.recs[ri]
    return [(t, bytes(d)) for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2])]


_items = {}


def item(db, rid):
    """(type, slot or '', value) of an item, a leveled list's ('LEVI', '', 0), or None."""
    low = (rid or '').lower()
    hit = _items.get(low)
    if hit is not None and hit[0] is db.recs:
        return hit[1]
    out = None
    ri = db.resolve_id(rid) if rid else None
    if ri is not None:
        tag = db.recs[ri][0]
        slot, value = '', 0
        try:
            for t, d in _subs(db, ri):
                if tag == 'CLOT' and t == 'CTDT' and len(d) >= 10:
                    ty, _w, value = struct.unpack_from('<ifh', d)
                    slot = CLOT_SLOTS[ty] if 0 <= ty < len(CLOT_SLOTS) else ''
                elif tag == 'ARMO' and t == 'AODT' and len(d) >= 12:
                    ty, _w, value = struct.unpack_from('<ifi', d)
                    slot = ARMO_SLOTS[ty] if 0 <= ty < len(ARMO_SLOTS) else ''
                elif tag == 'WEAP' and t == 'WPDT' and len(d) >= 10:
                    _w, value, ty = struct.unpack_from('<fih', d)
                    # (arrows and bolts go with a bow, not in the hand; a bow or crossbow is a slot of its own)
                    slot = 'arrow' if ty == 12 else 'bolt' if ty == 13 else 'bow' if ty == 9 else 'crossbow' if ty == 10 \
                        else 'thrown' if ty == 11 else 'weapon'
                elif tag in ('MISC', 'BOOK', 'ALCH', 'INGR', 'LIGH', 'APPA', 'LOCK', 'PROB', 'REPA') and \
                        t in ('MCDT', 'BKDT', 'ALDT', 'IRDT', 'LHDT', 'AADT', 'LKDT', 'PBDT', 'RIDT') and len(d) >= 8:
                    value = struct.unpack_from('<i', d, 4)[0]
        except Exception:
            pass
        out = (tag, slot, int(value or 0))
    _items[low] = (db.recs, out)
    return out


def person(db, ri):
    """What the game knows of one of its NPCs, for the survey."""
    o = {'id': db.recs[ri][1], 'name': '', 'race': '', 'cls': '', 'faction': '', 'rank': 0, 'level': 1, 'female': False,
         'auto': False, 'disp': 50, 'gold': 0, 'head': '', 'hair': '', 'script': '', 'hello': 30, 'fight': 30,
         'flee': 30, 'alarm': 0, 'services': 0, 'items': [], 'spells': [], 'wander': None, 'travel': 0, 'ai': ''}
    for t, d in _subs(db, ri):
        if t == 'FNAM':
            o['name'] = zstr(d)
        elif t in ('RNAM', 'CNAM', 'ANAM', 'BNAM', 'KNAM', 'SCRI'):
            o[{'RNAM': 'race', 'CNAM': 'cls', 'ANAM': 'faction', 'BNAM': 'head', 'KNAM': 'hair', 'SCRI': 'script'}[t]] = zstr(d)
        elif t == 'NPDT' and len(d) >= 52:
            v = struct.unpack_from('<h8B27Bx3HBBBxi', d)
            o['level'], o['disp'], o['rank'], o['gold'] = v[0], v[39], v[41], v[42]
        elif t == 'NPDT' and len(d) >= 12:
            o['level'], o['disp'], _rep, o['rank'], o['gold'] = struct.unpack_from('<hBBBxxxi', d)
        elif t == 'FLAG' and len(d) >= 4:
            f = struct.unpack_from('<i', d)[0]
            o['female'], o['auto'] = bool(f & 0x01), bool(f & 0x10)
        elif t == 'NPCO' and len(d) >= 36:
            o['items'].append((zstr(d[4:36]), abs(struct.unpack_from('<i', d)[0])))
        elif t == 'NPCS':
            o['spells'].append(zstr(d))
        elif t == 'AIDT' and len(d) >= 12:
            o['hello'], _u, o['fight'], o['flee'], o['alarm'] = struct.unpack_from('<BBBBB', d)
            o['services'] = struct.unpack_from('<i', d, 8)[0]
        elif t == 'DODT':
            o['travel'] += 1
        elif t == 'AI_W' and len(d) >= 14 and o['wander'] is None:
            dist, dur, _tod = struct.unpack_from('<hhB', d)
            o['wander'] = [dist, dur, list(d[5:13])]
            o['ai'] = o['ai'] or 'wander'
        elif t in ('AI_T', 'AI_F', 'AI_E', 'AI_A'):
            o['ai'] = o['ai'] or {'AI_T': 'travel', 'AI_F': 'follow', 'AI_E': 'escort', 'AI_A': 'activate'}[t]
    return o


# ---------------------------------------------------------------- places
def setting_of(db, name, ids, exterior=False, region=''):
    """(setting, theme, culture) of a place: its setting ('house', 'tavern', 'shop', 'temple', 'guild', 'manor'
    for a settlement's places, else 'cave', 'mine', 'sewer', 'dwemer', 'daedric', 'ruin', 'tomb', 'stronghold',
    'camp', or 'outdoors'), the theme its name says, and the culture its building pieces say."""
    import mapdata
    import roomsurvey
    styles = Counter(s for s in (mapdata.style_of(i) for i in ids) if s)
    if exterior:
        return 'outdoors', 'outdoors', region or '?'
    low = (name or '').lower()
    # (a Velothi tower: the pit, its two-storey room, is in no house; the game's 70 are the mages' and cultists')
    # (not the monasteries' pits, nor a fort's: their monks, guards and Armigers aren't a tower's)
    if any(i.lower().startswith(('in_velothismall_pit_01', 'in_velothismall_pit_02')) for i in ids) \
            and not re.search(r'tomb|monastery|abbey|infirmary|ghostgate|guard', low):
        return 'tower', 'tower', _culture(styles)
    for setting, words in NAME_SETTINGS:
        if any(re.search(r'(^|[^a-z])%s' % re.escape(w), low) for w in words):
            return setting, setting, _culture(styles)
    dungeon = Counter({STYLE_SETTINGS[s]: n for s, n in styles.items() if s in STYLE_SETTINGS})
    total = sum(styles.values())
    if dungeon and total and sum(dungeon.values()) >= 0.3 * total:
        s = dungeon.most_common(1)[0][0]
        return s, s, _culture(styles)
    theme = roomsurvey.theme_of(name)
    culture = _culture(styles)
    if theme == 'house':
        for setting, words in MORE_THEMES:
            if any(re.search(r'(^|[^a-z])%s(e?s)?([^a-z]|$)' % re.escape(w), low) for w in words):
                return setting, setting, culture
        # a place with a name of its own and no town before it (Kunashpat, Aharnat): somewhere out in the
        # wilds; a Velothi building out there is an old tower or shrine
        if ',' not in low and ' ' not in low.strip():
            return ('ruin' if culture == 'Velothi' else 'hideout'), 'hideout', culture
    return theme, theme, culture


def _culture(styles):
    cul = Counter({s: n for s, n in styles.items() if s not in STYLE_SETTINGS})
    return cul.most_common(1)[0][0] if cul else '?'


def read_places(db):
    """Every game-made place's people and creatures: [{'key', 'name', 'setting', 'theme', 'culture',
    'npcs': [npc id], 'creatures': [id], 'pieces': n}]."""
    import kits
    from project import ref_info
    out = []
    for (tag, k), lst in list(db.by_key.items()):
        if tag != 'CELL' or not lst or lst[-1] in db.dead:
            continue
        ext = k.startswith('#')
        if not ext and not kits.game_made(db, k):
            continue
        try:
            refs, header = db.cell_refs(k, without_project=True)
        except Exception:
            continue
        ids, npcs, creas, conts = [], [], [], []
        for ref in refs.values():
            rid, _pos, _s, deleted = ref_info(ref['subs'])[:4]
            if deleted or not rid:
                continue
            ids.append(rid)
            ri = db.resolve_id(rid)
            if ri is None:
                continue
            t = db.recs[ri][0]
            if t == 'NPC_':
                npcs.append(db.recs[ri][1])
            elif t in ('CREA', 'LEVC'):
                creas.append(db.recs[ri][1])
            elif t == 'CONT' and not NOT_LOOT.search(rid.lower()):
                conts.append(db.recs[ri][1])
        if not npcs and not creas:
            continue
        name = db.recs[lst[-1]][2] or db.recs[lst[-1]][1]
        region = ''
        if ext and header:
            region = next((zstr(d) for t, d in header[0] if t == 'RGNN'), '')
            name = re.sub(r'\s*\(-?\d+,\s*-?\d+\)$', '', db.recs[lst[-1]][1])
        setting, theme, culture = setting_of(db, name, ids, ext, region)
        out.append({'key': k, 'name': name, 'setting': setting, 'theme': theme, 'culture': culture,
                    'npcs': npcs, 'creatures': creas, 'conts': conts, 'pieces': sum(1 for i in ids if i.lower().startswith(('in_', 'ex_', 't_')))})
    return out


# ---------------------------------------------------------------- the dungeons' bands
# (2026-10-30, Populate's dungeon groups: of 2,076 dungeons with people, 510 hold two or more who fight on sight, and
# their classes, factions and spells name seven kinds, each with its own leaders, creatures and loot)
DUNGEONS = ('cave', 'mine', 'tomb', 'dwemer', 'daedric', 'ruin', 'hideout', 'stronghold', 'sewer', 'camp', 'tower')
BAND_KINDS = ('bandits', 'smugglers', 'worshippers', 'cultists', 'necromancers', 'mages', 'vampires')
HOSTILE = 70                  # (fight at or over it: attacks on sight)
VAMP = re.compile(r'vampir|aundae|berne|quarra|volkihar|bloodlust')
MAGES = ('sorcer', 'mage', 'battlemage', 'healer', 'spellsword', 'nightblade')
# (a container that is no band's loot: a plant's harvest, an egg, a corpse)
NOT_LOOT = re.compile(r'flora|kollop|egg|corpse|dead|plant|ingred_|skeleton|^bm_|_dwe_|guild|_gg_|quest')


def band_kind(ps, setting):
    """The kind of a dungeon's band, from its people (castsurvey.person dicts)."""
    cls = Counter(o['cls'].lower() for o in ps)
    n = len(ps)
    if any(VAMP.search(o['faction'].lower()) or VAMP.search(' '.join(o['spells']).lower()) or 'vampire' in o['race'].lower() for o in ps):
        return 'vampires'
    if any('dreamer' in c for c in cls):
        return 'cultists'
    if any('necromancer' in c for c in cls):
        return 'necromancers'
    if sum(v for c, v in cls.items() if 'smuggler' in c) * 2 >= n:
        return 'smugglers'
    if setting == 'daedric' or any(w in c for c in cls for w in ('warlock', 'witch')):
        return 'worshippers'
    if sum(v for c, v in cls.items() if any(w in c for w in MAGES)) * 2 > n:
        return 'mages'
    return 'bandits'


def _bands(places, people):
    B = defaultdict(lambda: {'places': 0, 'size': [], 'lead': Counter(), 'classes': Counter(), 'races': Counter(), 'factions': Counter(),
                             'creatures': Counter(), 'conts': Counter(), 'nconts': [], 'settings': Counter(), 'examples': []})
    for p in places:
        if p['setting'] not in DUNGEONS or p['key'].startswith('#'):
            continue
        ps = [o for o in (people.get(n.lower()) for n in p['npcs']) if o and o['fight'] >= HOSTILE]
        if len(ps) < 2:
            continue
        D = B[band_kind(ps, p['setting'])]
        D['places'] += 1
        D['size'].append(len(ps))
        D['settings'][p['setting']] += 1
        D['lead'][max(ps, key=lambda o: o['level'])['cls']] += 1
        for o in ps:
            D['classes'][o['cls']] += 1
            D['races'][o['race']] += 1
            D['factions'][o['faction'] or '-'] += 1
        for c in p['creatures']:
            D['creatures'][c.lower()] += 1
        for c in p.get('conts') or []:
            D['conts'][c.lower()] += 1
        D['nconts'].append(len(p.get('conts') or []))
        if len(D['examples']) < 6:
            D['examples'].append(p['key'])
    return B


# ---------------------------------------------------------------- folding
def role_of(cls):
    import peoplesurvey
    return peoplesurvey.role_of(cls)


TITLE_WORDS = {'dead', 'hetman', 'lord', 'lady', 'king', 'queen', 'master', 'mistress', 'sir', 'dame', 'captain', 'old', 'young',
               'big', 'little', 'uncle', 'aunt', 'brother', 'sister', 'father', 'mother', 'ghost', 'corpse', 'grandmaster',
               'archmagister', 'magister', 'councilor', 'duke', 'count', 'countess', 'baron', 'ashkhan', 'gulakhan', 'wise',
               'high', 'mad', 'crazy', 'drunk', 'blind', 'poor', 'fat', 'the', 'boss', 'chief', 'elder', 'foreman', 'madam',
               'mister', 'sergeant', 'general', 'commander', 'prince', 'princess', 'warlord', 'doctor', 'sister', 'saint'}


def _split_name(name, race):
    """(first, family) of a name, or (name, '') for a one-part name. Titles in front ("Hetman", "Dead",
    "Lord") and nicknames in quotes are left out; a Nord's "the Crow" is his family part; an Argonian's
    name is one name however many words ("Hides His Eyes")."""
    parts = [p for p in (name or '').split() if not (p.startswith(("'", '"')) and p.endswith(("'", '"')))]
    # (a Khajiit's prefix written apart, "Ra' Virr": one word)
    i = 0
    while i < len(parts) - 1:
        if parts[i].endswith("'") and len(parts[i]) <= 4:
            parts[i:i + 2] = [parts[i] + parts[i + 1]]
        i += 1
    while len(parts) > 1 and parts[0].lower().strip('.,') in TITLE_WORDS:
        parts = parts[1:]
    if not parts:
        return '', ''
    if len(parts) < 2 or (race or '').lower() == 'argonian':
        return ' '.join(parts), ''
    low = [p.lower() for p in parts]
    if 'the' in low[1:]:
        i = low.index('the', 1)
        return ' '.join(parts[:i]), ' '.join(parts[i:])
    if len(parts) >= 3 and low[-2] in ('gro', 'gra', 'at', 'af', 'of', 'de', 'la', 'ap'):
        return ' '.join(parts[:-2]), ' '.join(parts[-2:])
    return ' '.join(parts[:-1]), parts[-1]


def _top(c, n=TOP):
    return [[k, v] for k, v in c.most_common(n)]


def fold(db, places):
    """The places folded into what Populate asks for (see the module's note)."""
    people = {}
    uses = Counter()
    for p in places:
        for nid in p['npcs']:
            low = nid.lower()
            uses[low] += 1
            if low not in people:
                ri = _winner(db, 'NPC_', nid)
                if ri is not None:
                    try:
                        people[low] = person(db, ri)
                    except Exception:
                        pass
    # the wealth an outfit says: what its clothes and armour are worth, banded by the game's own spread
    worth = {}
    for low, o in people.items():
        v = 0
        for iid, n in o['items']:
            it = item(db, iid)
            if it and it[0] in ('CLOT', 'ARMO'):
                v += it[2]
        worth[low] = v
    vals = sorted(worth.values())
    cut = [vals[int(q * (len(vals) - 1))] for q in (0.3, 0.7, 0.92)] if vals else [0, 0, 0]
    band = lambda v: 'poor' if v <= cut[0] else 'common' if v <= cut[1] else 'fine' if v <= cut[2] else 'rich'
    # casts by setting
    casts = defaultdict(lambda: {'places': 0, 'people': [], 'creatures': Counter(), 'classes': Counter(), 'roles': Counter(),
                                 'groups': Counter(), 'cultures': Counter(), 'families': 0, 'pieces': [], 'races': Counter(), 'crowd': [],
                                 'factions': Counter(), 'bands': Counter(), 'female': 0, 'n': 0,
                                 'two': 0, 'two_kin': 0, 'two_couple': 0, 'two_race': 0, 'two_mf_race': 0})
    by_class = defaultdict(lambda: {'n': 0, 'races': Counter(), 'female': 0, 'factions': Counter(), 'ranks': Counter(),
                                    'levels': [], 'bands': Counter(), 'spells': Counter(), 'auto': 0, 'services': Counter(),
                                    'gold': [], 'hello': [], 'fight': [], 'flee': [], 'alarm': [], 'ai': Counter(),
                                    'wander': [], 'idles': [0] * 8, 'travel': 0, 'settings': Counter(), 'titles': Counter(),
                                    'carry': Counter(), 'carry_n': []})
    outfits = defaultdict(lambda: defaultdict(Counter))          # (class|band) -> slot -> item
    outfit_n = Counter()                                          # (class|band) -> people (how often a slot is filled)
    names = defaultdict(lambda: {'first': Counter(), 'family': Counter(), 'single': Counter(), 'whole': Counter()})
    faces = defaultdict(lambda: {'head': Counter(), 'hair': Counter()})
    name_n = Counter(o['name'] for o in people.values())
    for p in places:
        # each place counts for its setting, and for its setting in its culture (or region, outdoors)
        for key in (p['setting'], p['setting'] + '|' + p['culture']):
            C = casts[key]
            C['places'] += 1
            C['cultures'][p['culture']] += 1
            C['pieces'].append(p['pieces'])
            C['people'].append(len(p['npcs']))
            for cid in p['creatures']:
                C['creatures'][cid.lower()] += 1
            C['crowd'].append(len(p['creatures']))
            roles, fams = [], Counter()
            for nid in p['npcs']:
                o = people.get(nid.lower())
                if not o:
                    continue
                cls = o['cls']
                C['classes'][cls] += 1
                C['races'][o['race']] += 1
                C['factions'][o['faction'] or '-'] += 1
                C['bands'][band(worth[nid.lower()])] += 1
                C['female'] += o['female']
                C['n'] += 1
                r = role_of(cls)
                roles.append(r)
                C['roles'][r] += 1
                fam = _split_name(o['name'], o['race'])[1]
                if fam and name_n[o['name']] == 1:
                    fams[fam.lower()] += 1
            C['families'] += sum(1 for v in fams.values() if v >= 2)
            # the homes of two (no guard among them): how often they are one family, a man and a wife,
            # of one race
            two = [people.get(nid.lower()) for nid in p['npcs']]
            if len(two) == 2 and all(two) and not any(role_of(o['cls']) == 'guard' for o in two):
                a, b = two
                C['two'] += 1
                same_fam = bool(fams) and max(fams.values()) >= 2
                C['two_kin'] += same_fam
                C['two_couple'] += same_fam and a['female'] != b['female']
                C['two_race'] += a['race'] == b['race']
                C['two_mf_race'] += a['race'] == b['race'] and a['female'] != b['female']
            if roles:
                C['groups'][' + '.join(sorted(set(roles)))] += 1
    for low, o in people.items():
        cls, race = o['cls'], o['race']
        B = by_class[cls]
        B['n'] += 1
        B['races'][race] += 1
        B['female'] += o['female']
        if o['faction']:
            B['factions'][o['faction']] += 1
            B['ranks'][o['rank']] += 1
        B['levels'].append(o['level'])
        b = band(worth[low])
        B['bands'][b] += 1
        B['spells'].update(s.lower() for s in o['spells'])
        B['auto'] += o['auto']
        for bit in range(18):
            if o['services'] & (1 << bit):
                B['services'][bit] += 1
        B['gold'].append(o['gold'])
        for k in ('hello', 'fight', 'flee', 'alarm'):
            B[k].append(o[k])
        B['ai'][o['ai'] or 'none'] += 1
        if o['wander']:
            B['wander'].append(o['wander'][0])
            for i, v in enumerate(o['wander'][2][:8]):
                B['idles'][i] += v
        B['travel'] += bool(o['travel'])
        # generic people the game names by what they are ("Ordinator", "Imperial Guard") rather than a name
        if name_n[o['name']] >= 3 or (GENERIC_WORDS.search(o['name']) and len(o['name'].split()) <= 3 and name_n[o['name']] >= 2):
            B['titles'][o['name']] += 1
        elif "'s " in o['name'] or not o['name'].strip():
            pass                             # (a description, "Akavorioc's Enthralled", is no one's name)
        else:
            first, family = _split_name(o['name'], race)
            N = names['%s|%s' % (race, 'f' if o['female'] else 'm')]
            N['whole'][o['name']] += 1
            if family:
                N['first'][first] += 1
                N['family'][family] += 1
                names['%s|any' % race]['family'][family] += 1
            else:
                N['single'][first] += 1
        F = faces['%s|%s' % (race, 'f' if o['female'] else 'm')]
        if o['head']:
            F['head'][o['head']] += 1
        if o['hair']:
            F['hair'][o['hair']] += 1
        carried = 0
        # (by wealth, and by faction too: a Hlaalu guard wears Hlaalu armour, a legionary the Legion's)
        okeys = ['%s|%s' % (cls, b)] + (['%s|@%s' % (cls, o['faction'])] if o['faction'] else [])
        for ok in okeys:
            outfit_n[ok] += 1
        for iid, n in o['items']:
            it = item(db, iid)
            if not it:
                continue
            if (it[0] in ('CLOT', 'ARMO') and it[1]) or it[0] == 'WEAP':
                for ok in okeys:
                    outfits[ok][it[1]][iid.lower()] += 1
            elif iid.lower() != 'gold_001':
                B['carry'][iid.lower()] += 1
                carried += 1
        B['carry_n'].append(carried)

    def med(v):
        v = sorted(v)
        return v[len(v) // 2] if v else None

    def spread(v):
        v = sorted(v)
        return [v[int(q * (len(v) - 1))] for q in (0.1, 0.5, 0.9)] if v else None
    out = {'version': V, 'places': len(places), 'people': len(people), 'wealth_cuts': cut, 'casts': {}, 'classes': {},
           'outfits': {}, 'names': {}, 'faces': {}}
    for k, D in _bands(places, people).items():
        out.setdefault('bands', {})[k] = {'places': D['places'], 'size': spread(D['size']), 'lead': _top(D['lead'], 8),
                                          'classes': _top(D['classes'], 16), 'races': _top(D['races'], 10), 'factions': _top(D['factions'], 6),
                                          'creatures': _top(D['creatures'], 30), 'conts': _top(D['conts'], 30), 'nconts': spread(D['nconts']),
                                          'settings': _top(D['settings'], 11), 'examples': D['examples']}
    for k, C in casts.items():
        out['casts'][k] = {'places': C['places'], 'cultures': _top(C['cultures'], 10), 'people': spread(C['people']),
                           'empty': round(sum(1 for x in C['people'] if not x) / max(1, C['places']), 2),
                           'pieces': spread(C['pieces']), 'crowd': spread(C['crowd']), 'classes': _top(C['classes'], 40), 'roles': _top(C['roles'], 12),
                           'groups': _top(C['groups'], 20), 'creatures': _top(C['creatures'], 30), 'families': C['families'],
                           'races': _top(C['races'], 12), 'factions': _top(C['factions'], 10), 'bands': _top(C['bands'], 4),
                           'female': round(C['female'] / max(1, C['n']), 2),
                           'two': {k: C[k] for k in ('two', 'two_kin', 'two_couple', 'two_race', 'two_mf_race')}}
    for cls, B in by_class.items():
        n = B['n']
        out['classes'][cls] = {'n': n, 'role': role_of(cls), 'races': _top(B['races'], 12), 'female': round(B['female'] / n, 2),
                               'factions': _top(B['factions'], 8), 'ranks': _top(B['ranks'], 6), 'levels': spread(B['levels']),
                               'bands': _top(B['bands'], 4), 'spells': _top(B['spells'], 16), 'auto': round(B['auto'] / n, 2),
                               'services': {str(k): round(v / n, 2) for k, v in B['services'].items()}, 'gold': spread(B['gold']),
                               'hello': med(B['hello']), 'fight': med(B['fight']), 'flee': med(B['flee']), 'alarm': med(B['alarm']),
                               'ai': _top(B['ai'], 5), 'wander': spread(B['wander']),
                               'idles': [round(x / max(1, len(B['wander']))) for x in B['idles']], 'travel': round(B['travel'] / n, 2),
                               'titles': _top(B['titles'], 6), 'carry': _top(B['carry'], 20), 'carry_n': spread(B['carry_n'])}
    for k, slots in outfits.items():
        # per slot: how often someone of this class and wealth wears something there, and what
        out['outfits'][k] = {'n': outfit_n[k], 'slots': {s: {'share': round(sum(c.values()) / max(1, outfit_n[k]), 2), 'items': _top(c, 12)}
                                                         for s, c in slots.items()}}
    for k, N in names.items():
        out['names'][k] = {f: _top(c, 400) for f, c in N.items() if c}
    for k, F in faces.items():
        out['faces'][k] = {'head': _top(F['head'], 40), 'hair': _top(F['hair'], 40)}
    return out
