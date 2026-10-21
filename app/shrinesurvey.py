"""How the game composes a shrine: each altar or shrine base model with what stands on it (the saint's
or the god's statue, the candles, the offerings: flowers, coins, food, a book) at the game's own offsets
in the base's frame, in which kinds of room and place, how far from the wall behind it. Auto-furnish lays
a shrine only as one of these whole compositions (furnish.dress_shrine), and a base the game gives a
statue in half its places or more is never laid bare: the user's "blank monoliths". Kept in the cache
folder once done; ready() runs it in the background the first time."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import furnish
import kits

LIMIT = 300
SHRINE = re.compile(r'shrine|altar')
STATUE = re.compile(r'statue|saint|tribunal|divine|idol|bust|figure|relief|icon|almsivi|vivec|almalexia|sotha|azura|mephala|boethiah|'
                    r'akatosh|arkay|dibella|julianos|kynareth|mara_|stendarr|talos|zenithar|nine|ninedivines|triolith|ancestor')
OFFER_TYPES = ('MISC', 'INGR', 'ALCH', 'BOOK', 'CLOT', 'ARMO', 'WEAP')
_cache = {}
_thread = {}


def _disk(db, limit):
    import taste
    return taste.cache_file('shrinesurvey_%s_%d_v2' % (taste.sig(db), limit))


def ready(db, limit=LIMIT):
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
            _thread['t'] = background.start('how the game composes its shrines', lambda: survey(db, limit),
                                            task=('shrinesurvey', 'survey', [limit]))
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


def is_base(rid, tag):
    low = rid.lower()
    return tag in ('STAT', 'ACTI') and bool(SHRINE.search(low)) and not re.search(r'marker|in_|ex_|sound|light_', low)


def _survey(db, limit):
    import fixit
    import roomsurvey
    import taste
    per = defaultdict(lambda: {'n': 0, 'statue': 0, 'candles': 0, 'offer': 0, 'statues': Counter(), 'kinds': Counter(), 'themes': Counter(),
                               'gaps': [], 'examples': []})
    seen = 0
    # (every place of the game's that holds a shrine or altar model: found by the object index, not by
    # walking a spread of places, since shrines stand in one place in thirty)
    shrine_ids = [db.recs[ri][1].lower() for (tag, k), lst in db.by_key.items() if tag in ('STAT', 'ACTI') and lst
                  for ri in lst[-1:] if ri not in db.dead and is_base(db.recs[ri][1], tag)]
    cells = set()
    for low in shrine_ids:
        for ci in db.used_in.get(low, ()):
            if db.recs[ci][0] == 'CELL':
                ck = db.recs[ci][7]
                if ck and not ck.startswith('#') and kits.game_made(db, ck):
                    cells.add(ck)
    cells = taste.order(sorted(cells))
    for ck in cells:
        if seen >= limit:
            break
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'LEVC', 'DOOR')]
        bases = [r for r in refs if is_base(r['id'], r['type'])]
        if not bases:
            continue
        seen += 1
        theme = roomsurvey.theme_of(ck)
        for r in refs:
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
        for bs in bases:
            bb = fixit._world_box(bs)
            if not bb:
                continue
            rm = next((m for m in info['rooms'] if m['x_min'] <= bs['p'][0] <= m['x_max'] and m['y_min'] <= bs['p'][1] <= m['y_max']
                       and abs(m['floor'] - bb[2]) < 80), None)
            if rm is None:
                # (a place not laid in kit tiles, a temple's hall: the shrine's own surroundings)
                fl = bb[2]
                rm = {'x_min': bs['p'][0] - 512, 'x_max': bs['p'][0] + 512, 'y_min': bs['p'][1] - 512, 'y_max': bs['p'][1] + 512, 'floor': fl, 'loose': True}
            fl = rm['floor']
            inside = [o for o in refs if rm['x_min'] <= o['p'][0] <= rm['x_max'] and rm['y_min'] <= o['p'][1] <= rm['y_max']
                      and fl - 30 <= o['p'][2] + o['b'][2] * (o.get('s') or 1) <= fl + 400]
            kind = roomsurvey.room_kind(Counter(o['_fam'] for o in inside if o['_fam'] in roomsurvey.FLOOR_KINDS)) if not rm.get('loose') else 'untiled'
            rz = bs['p'][5]
            c, s = math.cos(-rz), math.sin(-rz)
            ex = {'statue': None, 'candles': [], 'offer': [], 'cell': ck, 'kind': kind}
            for o in inside:
                if o is bs or o['type'] in ('LEVC',):
                    continue
                ob = fixit._world_box(o)
                if not ob:
                    continue
                low = o['id'].lower()
                on = (bb[0] - 20 <= o['p'][0] <= bb[3] + 20 and bb[1] - 20 <= o['p'][1] <= bb[4] + 20 and bb[5] - 40 <= ob[2] <= bb[5] + 300)
                if not on:
                    continue
                dx, dy = o['p'][0] - bs['p'][0], o['p'][1] - bs['p'][1]
                off = [round(dx * c + dy * s, 1), round(-dx * s + dy * c, 1), round(o['p'][2] - bs['p'][2], 1),
                       round((o['p'][5] - rz) % (2 * math.pi), 3), o.get('s') or 1.0]
                if o['type'] in ('STAT', 'ACTI') and STATUE.search(low) and not SHRINE.search(low) and (ob[5] - ob[2]) >= 30 \
                        and not re.search(r'tapestr|banner|rug|carpet', low):
                    if ex['statue'] is None or (ob[5] - ob[2]) > ex['statue'][5]:
                        ex['statue'] = [o['id'].lower()] + off + [round(ob[5] - ob[2])]
                elif o['type'] == 'LIGH' and 'candle' in low:
                    ex['candles'].append([o['id'].lower()] + off)
                elif o['type'] in OFFER_TYPES:
                    ex['offer'].append([o['id'].lower()] + off)
            # (a statue that is itself the shrine: a shrine model with a statue's name stands alone)
            P = per[bs['id'].lower()]
            P['n'] += 1
            P['statue'] += 1 if ex['statue'] else 0
            P['candles'] += 1 if ex['candles'] else 0
            P['offer'] += 1 if ex['offer'] else 0
            if ex['statue']:
                P['statues'][ex['statue'][0]] += 1
            P['kinds'][kind] += 1
            P['themes'][theme] += 1
            if not rm.get('loose'):
                d_ = min(bs['p'][0] - rm['x_min'], rm['x_max'] - bs['p'][0], bs['p'][1] - rm['y_min'], rm['y_max'] - bs['p'][1])
                P['gaps'].append(round(d_))
            if len(P['examples']) < 16:
                P['examples'].append(ex)
    out = {'cells': seen, 'models': {}}
    for m, P in per.items():
        g = sorted(P['gaps'])
        out['models'][m] = {'n': P['n'], 'with_statue': round(P['statue'] / float(P['n']), 2), 'with_candles': round(P['candles'] / float(P['n']), 2),
                            'with_offerings': round(P['offer'] / float(P['n']), 2), 'statues': P['statues'].most_common(6),
                            'kinds': dict(P['kinds'].most_common()), 'themes': dict(P['themes'].most_common()),
                            'wall_gap': g[len(g) // 2] if g else None, 'examples': P['examples'],
                            'tall': bool(STATUE.search(m))}
    return out


def rule(db, rid):
    s = ready(db)
    if not s:
        return None
    return s['models'].get(rid.lower())


CHAPEL = re.compile(r'setchapel|chapel_|_chapel')
DUNMER = ('furn_shrine', 't_de_', 'furn_velothi', 'furn_de_', 't_dreu')
IMPERIAL = ('furn_imp', 't_imp_', 'furn_c_', 'furn_com', 't_com', 't_nor', 't_bre', 't_cyr')


def allowed(db, rid, theme='house', culture=None):
    """May this shrine model stand in a place of this theme and culture: the game stands it in homes
    (its places include houses or manors) when the place is a home, never a chapel's altar in a house,
    and the house's own culture's make: a Tribunal saint in a Dunmer house, an Imperial saint or altar in
    an Imperial or Common one (the user's "Imperial chapel's tall saint shrine in the middle of a Common
    stone cellar"). True when not surveyed yet; a model the game never stands anywhere is never allowed."""
    import mapdata
    low = rid.lower()
    r = rule(db, rid)
    if ready(db) is None:
        return True
    if not r:
        return False
    if theme != 'temple':
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        tall = bool(b) and (b[5] - b[2]) > LOW_ALTAR
        # (a chapel's tall saint pillar never in a home; its low altar table is the user's own choice for
        # one: "a good choice for homes, often decorated with various items found in the world")
        if CHAPEL.search(low) and tall:
            return False
        if re.search(r'dng|dungeon|barrow|tomb|crypt', low):
            return False                  # (a dungeon's altar, a Breton cellar's or a Nord barrow's)
        if re.match(r'^(pc_m|tr_m|tr_q|ac_|sky_m)', low):
            return False                  # (a quest's own shrine, made for one place)
        if not (r['themes'].get('house', 0) + r['themes'].get('manor', 0) + r['themes'].get('shop', 0) + r['themes'].get('tavern', 0)):
            return False
    if culture == 'dunmer' and low.startswith(IMPERIAL) and not low.startswith(DUNMER):
        return False
    if culture == 'imperial' and low.startswith(DUNMER):
        return False
    return True


def house_models(db, theme='house', culture=None):
    """The shrine models the game stands in places of this theme and culture, most used first (the
    Tribunal saints' shrines for a Dunmer house, the Imperial saints and the Imperial altar for an
    Imperial or Common one): for a house whose palette has no shrine of its own. [] until surveyed."""
    s = ready(db)
    if not s:
        return []
    import mapdata
    out = []
    for m, M in s['models'].items():
        ri = db.resolve_id(m)
        if ri is None or not allowed(db, m, theme, culture):
            continue
        n = M['themes'].get('house', 0) + M['themes'].get('manor', 0) if theme != 'temple' else M['n']
        b = mapdata.object_bounds(db, ri)
        low = bool(b) and (b[5] - b[2]) <= LOW_ALTAR
        # (in a home the low altar table first, "a good choice for homes, often decorated with various
        # items found in the world": the user; the tall saints' pillars clip the ceilings anyway. The
        # Imperial home's default is the Nine Divines altar table and the Imperial altar; the Dunmer
        # home's the Velothi altar)
        pref = HOME_FIRST.index(m) if m in HOME_FIRST else len(HOME_FIRST)
        out.append((0 if (low or theme == 'temple') else 1, pref, -n, m))
    out.sort()
    return [m for lo, p, n, m in out if n < 0]


HOME_FIRST = ('t_imp_setchapel_altarcure_02', 'furn_imp_altar_01', 't_imp_setchapel_altarcure_01', 'furn_imp_altar_cure_01',
              'furn_velothi_altar_01', 'furn_shrine_tribunal_cure_01')


LOW_ALTAR = 120            # a shrine no taller than this is an altar table, not a pillar
# the offerings the user names for a home's altar table, laid on it where the game's own dressings of
# the model are few: "gems, coins, cups, scrolls, books, that sort of thing"
OFFERINGS = {'gem': ('ingred_diamond_01', 'ingred_emerald_01', 'ingred_ruby_01', 'ingred_pearl_01'),
             'coin': ('gold_010', 'gold_025', 'gold_005', 'gold_001'),
             'cup': ('misc_com_goblet_01', 'misc_imp_silverware_cup', 'misc_com_metal_goblet_01', 'misc_com_silverware_cup', 'misc_de_goblet_01'),
             'scroll': ('sc_paper plain', 'sc_paper_plain', 'misc_de_paper_roll', 'text_paper_roll_01', 'text_paper_roll_02'),
             'candle': ('light_com_candle_07_64', 'light_com_candle_05_64', 'light_com_candle_03_64', 'light_de_candle_07_64')}


def offering_set(db, rng, books=()):
    """The user's offering set for a home's altar table, as ids that exist here: a gem or two, a coin
    pile, a cup, a scroll, a book, a candle (four to seven things), in a random order."""
    out = []
    for kind, n in (('gem', rng.choice((1, 2))), ('coin', 1), ('cup', 1), ('scroll', 1), ('candle', rng.choice((1, 2)))):
        ids = [i for i in OFFERINGS[kind] if db.resolve_id(i) is not None]
        for _ in range(n):
            if ids and rng.random() < 0.8:
                out.append(rng.choice(ids))
    if books and rng.random() < 0.7:
        out.append(rng.choice(list(books)))
    rng.shuffle(out)
    return out[:7]


def needs_statue(db, rid):
    """Is this base laid bare never: the game gives it a statue in half its places or more. None until surveyed."""
    r = rule(db, rid)
    if r is None:
        return None
    return r['with_statue'] >= 0.5


def composition(db, rid, rng, max_top=None):
    """One of the game's own dressings of this base: {'statue': [id, dx, dy, dz, drz, s, h] or None, 'candles':
    [...], 'offer': [...]} in the base's frame; the ones with a statue first when the model wants one;
    with max_top, only those whose statue's top stays under it (over the base's origin): the shorter
    saint under a low ceiling. None when the game never dresses it (or until surveyed), or when nothing
    fits under max_top."""
    r = rule(db, rid)
    if not r or not r['examples']:
        return None
    exs = r['examples']
    if max_top is not None:
        exs = [e for e in exs if not e['statue'] or e['statue'][3] + e['statue'][6] * (e['statue'][5] or 1.0) <= max_top]
        if not exs:
            return None
    if r['with_statue'] >= 0.5:
        exs = [e for e in exs if e['statue']] or exs
    return rng.choice(exs)


def report(db):
    s = survey(db)
    lines = ['%d places with shrines walked, %d base models' % (s['cells'], len(s['models']))]
    for m, M in sorted(s['models'].items(), key=lambda kv: -kv[1]['n'])[:40]:
        lines.append('   %-40s n %3d statue %.0f%% candles %.0f%% offerings %.0f%% wall gap %s rooms %s places %s statues %s' % (
            m, M['n'], 100 * M['with_statue'], 100 * M['with_candles'], 100 * M['with_offerings'], M['wall_gap'], M['kinds'], M['themes'], M['statues'][:3]))
    return '\n'.join(lines)
