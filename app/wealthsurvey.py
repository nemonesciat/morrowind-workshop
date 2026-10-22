"""How well off the game's own homes are, and what that looks like: which furniture sets a poor house
and a rich one are furnished with (the Dunmer and Common sets come in poor, middle and rich makes:
furn_de_p_, furn_de_rm_, furn_de_r_), how full the rooms are, how many hangings and lights, what the
loose things lying about are worth, what the chests and barrels hold, and who lives there (the owner's
class and faction, from the NPCs standing in the place). Auto-furnish's "Furnish as" choice (poor,
modest, comfortable, rich, exquisite, or by a trade or a faction) goes by it: the band's furniture sets
first, its density, its hangings, its value cap on the things on the shelves, its containers.

The survey walks the game's kit-built interiors (furnish.rooms, like roomsurvey.py), one row per place,
kept on disk under the Workshop's cache folder; the bands are drawn from the rows afterwards."""
import math
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey
import shelfsurvey

V = 'v5'                 # (v5: which hanging and rug models each place has, for the rich and poor tiers)
LIMIT = 250
BANDS = ('poor', 'modest', 'comfortable', 'rich', 'exquisite')
# the makes of the game's furniture sets, by the token after "furn" (and the culture) in the ID:
# furn_de_p_table_01 (poor), furn_de_rm_bookshelf_01 (middle), furn_de_r_chair_01 (rich), furn_com_rm_...
TIER_TOKEN = {'p': 'poor', 'rm': 'middle', 'm': 'middle', 'r': 'rich'}
# what gives a trade's home its character, beyond the everyday furniture (arrangesurvey's extra kinds)
CHARACTER = ('forge', 'loom', 'rack', 'apparatus', 'shrine', 'planter', 'bath', 'well', 'cage', 'counter', 'bookshelf')
# what a trade's home has when the survey has seen too few of them to say (words in the class, faction or
# trade typed; the first match wins)
TRADE_HINTS = (
    (r'smith|armorer|armourer|weaponsmith', {'band': 'modest', 'extras': ('forge', 'rack'), 'theme': 'shop'}),
    (r'apothecar|alchem|healer|herbal', {'band': 'comfortable', 'extras': ('apparatus',), 'theme': 'shop'}),
    (r'mage|wizard|sorcer|enchant|battlemage|spellsword|witch|guild of mages|mages guild', {'band': 'comfortable', 'extras': ('apparatus', 'bookshelf'), 'theme': 'guild'}),
    (r'temple|priest|monk|acolyte|ordinator|cleric|pilgrim', {'band': 'modest', 'extras': ('shrine',), 'theme': 'temple'}),
    (r'fighter|guard|warrior|legion|soldier|knight|mercenar|champion|redoran', {'band': 'modest', 'extras': ('rack',), 'theme': 'guild'}),
    (r'thie|thieves|rogue|agent|assassin|morag|camonna|smuggler', {'band': 'modest', 'extras': (), 'theme': 'house'}),
    (r'noble|lord|lady|councilor|councillor|hlaalu|telvanni|king|duke|patrician', {'band': 'exquisite', 'extras': ('bookshelf',), 'theme': 'manor'}),
    (r'scholar|scribe|bookseller|savant|archivist|librarian', {'band': 'comfortable', 'extras': ('bookshelf',), 'theme': 'house'}),
    (r'trader|merchant|pawn|clothier|outfitter|publican|innkeep|shopkeep|caravan', {'band': 'comfortable', 'extras': ('counter',), 'theme': 'shop'}),
    (r'farmer|miner|labou?rer|fisher|hunter|herder|slave|pauper|beggar|commoner|servant|drillmaster|shipmaster|sailor', {'band': 'poor', 'extras': (), 'theme': 'house'}),
    (r'ashland|wise woman|gulakhan|nomad', {'band': 'poor', 'extras': ('shrine',), 'theme': 'house'}),
)
_cache = {}
_thread = {}
_factions = {}
_list_value = {}


def set_tier(rid):
    """The make of a furniture set piece, from its ID: 'poor', 'middle', 'rich', or None (a piece that
    comes in one make only, like a bed or a barrel)."""
    low = rid.lower()
    if 'furn' not in low:
        return None
    tokens = low.split('_')
    try:
        i = tokens.index('furn')
    except ValueError:
        i = next((n for n, t in enumerate(tokens) if t.startswith('furn')), None)
        if i is None:
            return None
    for t in tokens[i + 1:i + 4]:
        if t in TIER_TOKEN:
            return TIER_TOKEN[t]
    return None


def set_name(rid):
    """The family of a furniture set, e.g. 'furn_de_p', 't_de_furn_r', 'furn_com_rm'; or '' for a piece
    that belongs to no make."""
    low = rid.lower()
    tokens = low.split('_')
    for n, t in enumerate(tokens):
        if t in TIER_TOKEN and n >= 1 and any(x.startswith('furn') for x in tokens[:n]):
            return '_'.join(tokens[:n + 1])
    return ''


def faction_of(db, rid):
    """An NPC's faction (the ID in its record), or ''."""
    low = rid.lower()
    if low in _factions and _factions[low][0] is db.recs:
        return _factions[low][1]
    fac = ''
    ri = db.resolve_id(rid)
    if ri is not None and db.recs[ri][0] == 'NPC_':
        from esm import iter_subrecords, zstr
        try:
            _t, _f, data = db.files[db.recs[ri][3]].record_at(db.recs[ri][4])
            fac = next((zstr(sd) for st, sd in iter_subrecords(data) if st == 'ANAM'), '')
        except Exception:
            fac = ''
    _factions[low] = (db.recs, fac)
    return fac


def list_value(db, lid, depth=0):
    """What one draw from a leveled list is worth, about: the mean value of its entries (a list in the
    list counts as its own mean), ignoring the player's level and the chance of nothing."""
    low = (lid or '').lower()
    if low in _list_value and _list_value[low][0] is db.recs:
        return _list_value[low][1]
    out = 0.0
    if depth < 4:
        try:
            import levlists
            o = levlists.read(db, low)
            vals = []
            for e in o['entries']:
                if e['type'] == 'LEVI':
                    vals.append(list_value(db, e['id'], depth + 1))
                elif e['type']:
                    vals.append(shelfsurvey.value_of(db, e['id'])[1])
            out = sum(vals) / len(vals) if vals else 0.0
        except Exception:
            out = 0.0
    _list_value[low] = (db.recs, out)
    return out


def container_value(db, rid):
    """What a container record's contents are worth, about (count x value; a leveled list by its mean
    draw); 0 for an empty one, None for something that isn't a container."""
    import containersurvey
    c = containersurvey.contents(db, rid)
    if c is None:
        return None
    total = 0.0
    for it in c['items']:
        n = abs(it['count']) or 1
        if it['type'] == 'LEVI':
            total += n * list_value(db, it['id'])
        elif it['type']:
            total += n * shelfsurvey.value_of(db, it['id'])[1]
    return total


def _disk(db, limit):
    import taste
    return taste.cache_file('wealthsurvey_%s_%d_%s' % (taste.sig(db), limit, V))


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); otherwise None, with the survey started in
    the background so it's there next time (several minutes the first time; while a survey for a
    changed taste set runs, the newest earlier one stands in)."""
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
        _thread['t'] = background.start('how well off the game\'s households are', lambda: survey(db, limit), task=('wealthsurvey', 'survey', [limit]))
    return taste.stale(_cache, key, db.recs, _disk(db, limit))


def survey(db, limit=LIMIT):
    """One row per game-made kit interior (kept on disk once done): see _survey."""
    import json
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


def _clip_area(fp, rm):
    x0, y0 = max(fp[0], rm['x_min']), max(fp[1], rm['y_min'])
    x1, y1 = min(fp[2], rm['x_max']), min(fp[3], rm['y_max'])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _survey(db, limit):
    import arrangesurvey
    import wallsurvey2
    rows = []
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    # (a spread over the whole list, not its first names: the first six hundred interiors by name are
    # nearly all Tamriel Rebuilt's, and Bethesda's Balmora and Vivec would never be seen; about one
    # interior in four is a kit-built one with rooms, so the stride is set to pass four and a half times
    # the limit)
    step = max(1.0, len(cells) / float(limit * 4.5))
    seen = 0
    # (the exemplary places first, each counted several times over: taste.py; then the spread)
    import taste
    first = taste.order([c for c in cells if taste.is_marked(c)])
    for n in range(len(first) + int(len(cells) / step)):
        if seen >= limit:
            break
        ck = first[n] if n < len(first) else cells[int((n - len(first)) * step)]
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        if not info['rooms'] or info['tile'] != 256:
            continue
        seen += 1
        T = info['tile']
        name = (mapdata.cell_info(db, ck) or {}).get('name') or ck
        theme = roomsurvey.theme_of(name)
        styles = Counter(kits.kit_prefix(r['id']) for r in info['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
        style = styles.most_common(1)[0][0] if styles else ''
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in refs:
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
        tiers = Counter()
        sets = Counter()
        cover = []
        pieces = []
        kinds = Counter()
        for rm in info['rooms']:
            H = 300
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and rm['floor'] - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= rm['floor'] + H]
            floor = [r for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS]
            counts = Counter(r['_fam'] for r in floor)
            kinds[roomsurvey.room_kind(counts)] += 1
            area = (rm['x_max'] - rm['x_min']) * (rm['y_max'] - rm['y_min']) or 1.0
            cov = 0.0
            for r in floor:
                if r['_fam'] == 'rug':
                    continue
                s = r.get('s') or 1.0
                fp = furnish._footprint([v * s for v in r['b']], r['p'][5], r['p'][0], r['p'][1])
                cov += _clip_area(fp, rm)
            cover.append((min(1.0, cov / area), rm['tiles']))
            pieces.append((len([r for r in floor if r['_fam'] != 'rug']), rm['tiles']))
            for r in floor:
                t = set_tier(r['id'])
                if t:
                    tiers[t] += 1
                    sets[set_name(r['id'])] += 1
        n_tiles = sum(t for _c, t in cover) or 1
        # hangings, rugs and lights in the whole place
        hangings = rugs = lights = candles = 0
        hang_ids = Counter()         # (which hanging and rug models: the rich tier the game hangs in its rich homes)
        rug_ids = Counter()
        for r in refs:
            low = r['id'].lower()
            if r['_fam'] == 'rug':
                rugs += 1
                rug_ids[low] += 1
            elif r['type'] == 'LIGH':
                lights += 1
                if 'candle' in low:
                    candles += 1
            elif r['type'] in ('STAT', 'ACTI', 'MISC') and wallsurvey2.HANG.search(low) and not wallsurvey2.NOT_HANG.search(low) \
                    and 'sconce' not in low and r['p'][2] + r['b'][2] * (r.get('s') or 1) > min(rm['floor'] for rm in info['rooms']) + 40:
                hangings += 1
                hang_ids[low] += 1
        # the loose things lying about, and what they're worth
        vals = []
        interesting = 0
        gold = 0
        for r in refs:
            if r['type'] not in mapdata.ITEM_TYPES:
                continue
            low = r['id'].lower()
            tag, v, _ex = shelfsurvey.value_of(db, low)
            if re.search(r'gold_\d|^gold', low) and tag == 'MISC':
                gold += max(1, int(r.get('n') or r.get('count') or 1)) * max(1, v)
                continue
            vals.append(v)
            if shelfsurvey.interesting(db, low):
                interesting += 1
        vals.sort()
        p90 = vals[min(len(vals) - 1, int(0.9 * len(vals)))] if vals else 0
        # the containers and what they hold
        conts = []
        cont_ids = Counter()
        for r in refs:
            if r['type'] != 'CONT' or r['_fam'] not in furnish.CONTAINER_KINDS:
                continue
            cv = container_value(db, r['id'])
            if cv is None:
                continue
            conts.append(round(cv))
            cont_ids[r['id'].lower()] += 1
        conts.sort()
        # what gives the place character: a forge, a loom, a shrine, an apparatus, a rack
        character = Counter()
        for r in refs:
            f = arrangesurvey.family(db, r['id'], r['type'])
            if f in CHARACTER:
                character[f] += 1
        # who lives here
        npcs = [r for r in info['refs'] if r['type'] == 'NPC_']
        classes = Counter(roomsurvey.class_of(db, n['id']).lower() for n in npcs)
        factions = Counter(faction_of(db, n['id']).lower() for n in npcs)
        classes.pop('', None)
        factions.pop('', None)
        rows.append({
            'key': ck, 'name': name, 'theme': theme, 'style': style, 'rooms': len(info['rooms']), 'tiles': n_tiles,
            'kinds': dict(kinds), 'tiers': dict(tiers), 'sets': dict(sets.most_common(6)),
            'cover': round(sum(c * t for c, t in cover) / n_tiles, 3),
            'per9': round(sum(p for p, _t in pieces) / n_tiles * 9, 2),
            'hangings': hangings, 'rugs': rugs, 'lights': lights, 'candles': candles,
            'hang_ids': dict(hang_ids), 'rug_ids': dict(rug_ids),
            'loose': {'n': len(vals), 'total': round(sum(vals)), 'max': vals[-1] if vals else 0, 'p90': p90,
                      'interesting': interesting, 'gold': gold},
            'cont': {'n': len(conts), 'total': round(sum(conts)), 'max': conts[-1] if conts else 0,
                     'median': conts[len(conts) // 2] if conts else 0, 'ids': dict(cont_ids.most_common(8))},
            'character': dict(character), 'classes': dict(classes), 'factions': dict(factions)})
    return {'cells': seen, 'rows': rows}


# ------------------------------------------------------------------ the bands
HOME_THEMES = ('house', 'manor', 'shop', 'tavern', 'guild', 'temple')


def band_of(row):
    """Which band a surveyed place falls in, from the make of its furniture first (poor, middle, rich
    sets), and then from what lies about: a rich house whose loose things run dear is exquisite, a poor
    one with a few good things modest."""
    t = row['tiers']
    n = sum(t.values())
    p90 = row['loose']['p90']
    if n >= 3:
        score = (t.get('rich', 0) - t.get('poor', 0)) / float(n)
        if score <= -0.5:
            return 'modest' if p90 >= 60 else 'poor'
        if score < -0.1:
            return 'modest'
        if score <= 0.4:
            return 'rich' if p90 >= 150 else 'comfortable'
        return 'exquisite' if (p90 >= 120 or row['theme'] == 'manor') else 'rich'
    # no set furniture to go by (a style with one make, or hardly any furniture): by what lies about
    if p90 <= 10:
        return 'poor'
    if p90 <= 30:
        return 'modest'
    if p90 <= 80:
        return 'comfortable'
    if p90 <= 200:
        return 'rich'
    return 'exquisite'


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0


def _p(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0


def bands(db, limit=LIMIT):
    """The bands, measured: {band: {'places', 'themes', 'tiers', 'sets', 'cover', 'per9', 'hangings' (per
    room), 'rugs', 'lights', 'loose_p90', 'loose_max', 'interesting' (per place), 'cont_median',
    'cont_p90', 'cont_ids', 'classes', 'factions', 'character'}}; None while the survey runs."""
    s = ready(db, limit)
    if not s:
        return None
    key = ('bands', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    rows = [r for r in s['rows'] if r['theme'] in HOME_THEMES and r['rooms'] >= 1 and r['per9'] > 0]
    out = {}
    for b in BANDS:
        R = [r for r in rows if band_of(r) == b]
        if not R:
            out[b] = None
            continue
        sets = Counter()
        tiers = Counter()
        conts = Counter()
        classes = Counter()
        factions = Counter()
        character = Counter()
        for r in R:
            sets.update(r['sets'])
            tiers.update(r['tiers'])
            conts.update(r['cont']['ids'])
            classes.update(r['classes'])
            factions.update(r['factions'])
            character.update(r['character'])
        n_t = sum(tiers.values()) or 1
        out[b] = {
            'places': len(R), 'themes': dict(Counter(r['theme'] for r in R)),
            'tiers': {k: round(v / n_t, 2) for k, v in tiers.items()}, 'sets': sets.most_common(8),
            # (medians: a warehouse with its floor seven tenths under crates would pull a mean)
            'cover': round(_med([r['cover'] for r in R]), 3), 'per9': round(_med([r['per9'] for r in R]), 2),
            'cover_mean': round(sum(r['cover'] for r in R) / len(R), 3),
            'hangings': round(sum(r['hangings'] for r in R) / float(sum(r['rooms'] for r in R)), 2),
            'rugs': round(sum(r['rugs'] for r in R) / float(sum(r['rooms'] for r in R)), 2),
            'lights': round(sum(r['lights'] for r in R) / float(sum(r['rooms'] for r in R)), 2),
            'rooms': round(sum(r['rooms'] for r in R) / float(len(R)), 1),
            'tiles_per_room': round(sum(r['tiles'] for r in R) / float(sum(r['rooms'] for r in R)), 1),
            'loose_p90': _med([r['loose']['p90'] for r in R]), 'loose_max': _med([r['loose']['max'] for r in R]),
            'loose_max_hi': _p([r['loose']['max'] for r in R], 0.75),
            'loose_total': _med([r['loose']['total'] for r in R]),
            'interesting': round(sum(r['loose']['interesting'] for r in R) / float(len(R)), 1),
            'interest_rate': round(sum(r['loose']['interesting'] for r in R) / float(sum(r['loose']['n'] for r in R) or 1), 3),
            'cont_median': _med([r['cont']['median'] for r in R if r['cont']['n']]),
            'cont_p90': _p([r['cont']['max'] for r in R if r['cont']['n']], 0.9),
            'cont_ids': conts.most_common(10), 'classes': classes.most_common(12), 'factions': factions.most_common(8),
            'character': {k: round(v / float(len(R)), 2) for k, v in character.items()}}
    _cache[key] = (db.recs, out)
    return out


_tiers = {}


def decor_tiers(db, limit=LIMIT):
    """Which hanging and rug models the game's rich homes use and which its poor ones: {'hang': {id:
    'rich'|'poor'}, 'rug': {...}, 'shares': {band: {'hang_rich', 'hang_poor', 'rug_rich', 'rug_poor'}}}.
    A model is of the rich tier when its share of the hangings (rugs) in rich and exquisite homes is twice
    its share in poor and modest ones, seen three times or more there; of the poor tier the other way
    round. The shares say how much of each band's hangings and rugs are of each tier, the figure to measure
    a furnished house against. None while the survey runs. The user: "for rich and exquisitely decorated
    homes, remember to incorporate wall paintings, fancy rugs, fancy tapestries"."""
    s = ready(db, limit)
    if not s:
        return None
    key = ('tiers', limit)
    if key in _tiers and _tiers[key][0] is db.recs:
        return _tiers[key][1]
    rows = [r for r in s['rows'] if r['theme'] in HOME_THEMES and r['rooms'] >= 1 and r['per9'] > 0 and 'hang_ids' in r]
    out = {'hang': {}, 'rug': {}, 'shares': {}}
    for what in ('hang', 'rug'):
        rich, poor = Counter(), Counter()
        for r in rows:
            b = band_of(r)
            if b in ('rich', 'exquisite'):
                rich.update(r[what + '_ids'])
            elif b in ('poor', 'modest'):
                poor.update(r[what + '_ids'])
        nr, np_ = float(sum(rich.values()) or 1), float(sum(poor.values()) or 1)
        for i in set(rich) | set(poor):
            sr, sp = rich[i] / nr, poor[i] / np_
            if rich[i] >= 3 and sr >= 2 * sp:
                out[what][i] = 'rich'
            elif poor[i] >= 3 and sp >= 2 * sr:
                out[what][i] = 'poor'
    for b in BANDS:
        R = [r for r in rows if band_of(r) == b]
        sh = {}
        for what in ('hang', 'rug'):
            c = Counter()
            for r in R:
                c.update(r[what + '_ids'])
            n = float(sum(c.values()) or 1)
            sh[what + '_rich'] = round(sum(v for i, v in c.items() if out[what].get(i) == 'rich') / n, 3)
            sh[what + '_poor'] = round(sum(v for i, v in c.items() if out[what].get(i) == 'poor') / n, 3)
            sh[what + '_n'] = int(n) if c else 0
        out['shares'][b] = sh
    _tiers[key] = (db.recs, out)
    return out


def decor_tier(db, rid, what='hang'):
    """'rich', 'poor' or None for a hanging ('hang') or rug ('rug') model."""
    t = decor_tiers(db)
    return (t or {}).get(what, {}).get(rid.lower()) if t else None


def trades(db, limit=LIMIT):
    """Every class and faction seen living in a surveyed home, with its usual band and the character
    pieces its homes have more than most: {name: {'kind': 'class'|'faction', 'n', 'band', 'bands':
    {...}, 'extras': [...]}}; None while the survey runs."""
    s = ready(db, limit)
    if not s:
        return None
    key = ('trades', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    rows = [r for r in s['rows'] if r['theme'] in HOME_THEMES]
    all_char = Counter()
    for r in rows:
        all_char.update(r['character'])
    base = {k: v / float(len(rows) or 1) for k, v in all_char.items()}
    out = {}
    for kind, field in (('class', 'classes'), ('faction', 'factions')):
        by = defaultdict(list)
        for r in rows:
            for name in r[field]:
                by[name].append(r)
        for name, R in by.items():
            bc = Counter(band_of(r) for r in R)
            ch = Counter()
            for r in R:
                ch.update(r['character'])
            extras = [k for k, v in ch.items() if k in CHARACTER and v / float(len(R)) >= max(0.25, 2.5 * base.get(k, 0))]
            # the band in the middle of this trade's homes (not the commonest: a trade seen in a poor house
            # and a rich one is modest or comfortable)
            order = [b for b in BANDS for _ in range(bc.get(b, 0))]
            out[name] = {'kind': kind, 'n': len(R), 'band': order[len(order) // 2] if order else 'comfortable',
                         'bands': dict(bc), 'extras': sorted(extras, key=lambda k: -ch[k])}
    _cache[key] = (db.recs, out)
    return out


def _names(db):
    """{'class': {id: name}, 'faction': {id: name}} from the records."""
    key = ('names',)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    out = {'class': {}, 'faction': {}}
    for (tag, k), lst in db.by_key.items():
        if tag in ('CLAS', 'FACT') and lst and lst[-1] not in db.dead:
            r = db.recs[lst[-1]]
            out['class' if tag == 'CLAS' else 'faction'][k.lower()] = r[2] or r[1]
    _cache[key] = (db.recs, out)
    return out


def trade_options(db):
    """For the "By trade or faction" box: [{'id', 'name', 'kind', 'band', 'n'}] the trades the survey
    has seen living somewhere, then every other class and faction (band by the hints)."""
    T = trades(db) or {}
    names = _names(db)
    out = []
    seen = set()
    for tid, t in sorted(T.items(), key=lambda kv: -kv[1]['n']):
        nm = names[t['kind']].get(tid, tid)
        if nm.lower() in seen or nm.startswith('<'):
            continue
        out.append({'id': tid, 'name': nm, 'kind': t['kind'], 'band': t['band'], 'n': t['n'], 'extras': t['extras']})
        seen.add(nm.lower())
    for kind in ('class', 'faction'):
        for tid, nm in sorted(names[kind].items(), key=lambda kv: kv[1]):
            # (one entry per name: the game has a class and a "service" class of the same name; nothing deprecated)
            if nm.lower() in seen or nm.startswith('<') or 'deprecated' in nm.lower():
                continue
            seen.add(nm.lower())
            h = _hint(nm) or _hint(tid) or {}
            out.append({'id': tid, 'name': nm, 'kind': kind, 'band': h.get('band', 'comfortable'), 'n': 0, 'extras': list(h.get('extras', ()))})
    return out


def _hint(text):
    low = (text or '').lower()
    for pat, h in TRADE_HINTS:
        if re.search(pat, low):
            return h
    return None


def trade(db, text):
    """What furnishing a home 'by trade or faction' means for this text (a class, a faction, a trade
    word): {'band', 'extras': the character pieces to lay (a smith's forge), 'theme', 'match': what it
    was read as, 'n': homes seen}. The survey's own classes and factions first (by id or name, whole
    or part), then the hints."""
    low = (text or '').strip().lower()
    if not low:
        return None
    T = trades(db) or {}
    names = _names(db)
    best = None
    for tid, t in T.items():
        nm = names[t['kind']].get(tid, tid).lower()
        exact = low in (tid, nm)
        part = low in nm or low in tid or nm in low
        if exact or part:
            score = (2 if exact else 1, t['n'])
            if best is None or score > best[0]:
                best = (score, tid, nm, t)
    h = _hint(low)
    if best and (best[3]['n'] >= 3 or not h):
        tid, nm, t = best[1], best[2], best[3]
        # (what the survey saw in their homes, and what the trade's name says: a Temple priest's shrine)
        extras = list(t['extras']) + [e for e in (h or {}).get('extras', ()) if e not in t['extras']]
        return {'band': t['band'], 'extras': extras, 'theme': (h or {}).get('theme'), 'match': nm, 'kind': t['kind'], 'n': t['n']}
    if h:
        return {'band': h['band'], 'extras': list(h['extras']), 'theme': h.get('theme'), 'match': low, 'kind': 'hint', 'n': 0}
    for kind in ('class', 'faction'):
        for tid, nm in names[kind].items():
            if low in (tid, nm.lower()) or low in nm.lower():
                return {'band': 'comfortable', 'extras': [], 'theme': None, 'match': nm, 'kind': kind, 'n': 0}
    return {'band': 'comfortable', 'extras': [], 'theme': None, 'match': low, 'kind': 'none', 'n': 0}


# ------------------------------------------------------------------ what Auto-furnish does with a band
# how a band furnishes, relative to 'comfortable' (today's behaviour): fallbacks until the survey has run
# and for what it can't measure. tiers: the makes of furniture preferred, first choice first.
DEFAULTS = {
    'poor':        {'tiers': ('poor', 'middle', None, 'rich'), 'keep': 1, 'density': 0.75, 'hang': 0.5, 'lights': 0.7, 'cap': 40, 'rate': 0.4},
    'modest':      {'tiers': ('poor', 'middle', None, 'rich'), 'keep': 2, 'density': 0.9, 'hang': 0.75, 'lights': 0.85, 'cap': 120, 'rate': 0.7},
    'comfortable': {'tiers': (None,), 'keep': 1, 'density': 1.0, 'hang': 1.0, 'lights': 1.0, 'cap': None, 'rate': 1.0},
    'rich':        {'tiers': ('rich', 'middle', None, 'poor'), 'keep': 1, 'density': 1.15, 'hang': 1.3, 'lights': 1.2, 'cap': 500, 'rate': 1.3},
    'exquisite':   {'tiers': ('rich', 'middle', None, 'poor'), 'keep': 1, 'density': 1.3, 'hang': 1.6, 'lights': 1.4, 'cap': 1500, 'rate': 1.6},
}


def rule(db, band):
    """How Auto-furnish furnishes at this band: {'band', 'tiers', 'density' (x today's counts), 'hang'
    (x today's hangings), 'lights' (x today's hung lanterns), 'cap' (value cap on the things on shelves;
    None = the theme's own), 'rate' (x the game's rate of interesting things), 'cont_max' (what a
    container may hold, about)}. The multipliers are the surveyed band's measure over the comfortable
    band's, when the survey has run."""
    band = band if band in BANDS else 'comfortable'
    out = dict(DEFAULTS[band], band=band, cont_max=None)
    if band == 'comfortable':
        return out
    B = bands(db)
    mid = (B or {}).get('comfortable')
    me = (B or {}).get(band)
    if me and mid and me['places'] >= 8 and mid['places'] >= 8:
        # (density by the share of the floor under furniture, which is what the eye sees; the count of
        # pieces runs the other way in big-roomed manors, whose pieces are bigger)
        out['density'] = max(0.5, min(1.5, me['cover'] / float(mid['cover'] or 1)))
        out['hang'] = max(0.3, min(2.0, me['hangings'] / float(mid['hangings'] or 1)))
        out['lights'] = max(0.4, min(1.8, me['lights'] / float(mid['lights'] or 1)))
        out['rate'] = max(0.25, min(2.5, me['interest_rate'] / float(mid['interest_rate'] or 1)))
        # the cap on what stands on the shelves: a poor house twice what nine in ten of its things are
        # worth (so nothing interesting at all, mostly); a rich one what the dearest thing in three
        # rich houses in four stays under
        out['cap'] = max(35, me['loose_p90'] * 2) if band in ('poor', 'modest') else max(100, me['loose_max_hi'])
        # containers: a poor house's hold nothing dearer than nine in ten of the game's poor houses' do
        out['cont_max'] = (me['cont_p90'] or None) if band in ('poor', 'modest') else None
    return out


def containers_of(db, band):
    """The container records the game stands in places of this band, with sightings; {} while surveying."""
    B = bands(db)
    me = (B or {}).get(band)
    return dict(me['cont_ids']) if me else {}


def order_by_tier(ids, tiers, keep=1):
    """A palette list reordered so the preferred makes come first (the order within a make kept); and
    when the list holds any of the first make, only the first `keep` makes and the pieces of no make
    stay (a poor house that has the poor Dunmer chair gets no rich one, nor a middling one; a modest
    house keeps the poor and the middling; a rich house the rich)."""
    rank = {t: n for n, t in enumerate(tiers)}
    fallback = len(tiers)
    if len(tiers) > 1 and any(set_tier(rid) == tiers[0] for rid in ids):
        allowed = set(tiers[:keep]) | {None}
        ids = [rid for rid in ids if set_tier(rid) in allowed]
    return sorted(ids, key=lambda rid: rank.get(set_tier(rid), rank.get(None, fallback)))


def level(db, choice):
    """Auto-furnish's "Furnish as" choice, resolved: None for today's behaviour, else {'band', 'tiers',
    'density', 'hang', 'cap', 'rate', 'cont_max', 'max_value' (nothing dearer anywhere, or None),
    'extras', 'theme', 'label'}. choice: a band name, 'worthless', 'trade:<text>', or a dict {'band',
    'trade', 'max_value'}."""
    if not choice:
        return None
    if isinstance(choice, str):
        c = {'band': choice}
        if choice.startswith('trade:'):
            c = {'band': 'trade', 'trade': choice[6:]}
    else:
        c = dict(choice)
    band = (c.get('band') or 'comfortable').lower()
    extras = []
    theme = None
    label = band
    if band == 'trade':
        t = trade(db, c.get('trade') or '')
        if not t:
            return None
        band, extras, theme = t['band'], t['extras'], t.get('theme')
        label = 'by trade: %s (%s)' % (t['match'], band)
    max_value = None
    if band == 'worthless':
        try:
            max_value = max(0, int(c.get('max_value') if c.get('max_value') is not None else 15))
        except (TypeError, ValueError):
            max_value = 15
        band = 'modest'
        label = 'loot worthless (nothing over %d gold)' % max_value
    if band == 'comfortable' and not extras and max_value is None:
        return None
    out = rule(db, band)
    if max_value is not None:
        out['cap'] = max_value
        out['rate'] = 0.0 if max_value < shelfsurvey.INTEREST_MIN_VALUE else out['rate']
        out['cont_max'] = max_value
    out.update(max_value=max_value, extras=extras, theme=theme, label=label)
    return out


# ------------------------------------------------------------------ for people
def report(db, limit=LIMIT):
    s = survey(db, limit)
    B = bands(db, limit)
    names = _names(db)
    lines = ['%d places surveyed, %d in home themes' % (s['cells'], sum(1 for r in s['rows'] if r['theme'] in HOME_THEMES))]
    lines.append('bands by furniture make and loose values: ' + ', '.join('%s %d' % (b, (B[b] or {}).get('places', 0)) for b in BANDS))
    for b in BANDS:
        d = B.get(b)
        if not d:
            continue
        lines.append('== %s: %d places %s' % (b, d['places'], d['themes']))
        lines.append('   makes %s; sets %s' % (d['tiers'], d['sets'][:5]))
        lines.append('   floor cover %.0f%% (mean %.0f%%), %.1f pieces per 9 tiles, hangings %.2f per room, rugs %.2f, lights %.2f; %.1f rooms of %.1f tiles'
                     % (d['cover'] * 100, d['cover_mean'] * 100, d['per9'], d['hangings'], d['rugs'], d['lights'], d['rooms'], d['tiles_per_room']))
        lines.append('   loose things: p90 value %d, dearest %d, total %d (medians per place), %.1f interesting per place (rate %.3f)'
                     % (d['loose_p90'], d['loose_max'], d['loose_total'], d['interesting'], d['interest_rate']))
        lines.append('   containers: median value %d, p90 of the dearest %d; %s' % (d['cont_median'], d['cont_p90'], d['cont_ids'][:5]))
        lines.append('   classes %s' % [(names['class'].get(k, k), n) for k, n in d['classes'][:8]])
        lines.append('   factions %s' % [(names['faction'].get(k, k), n) for k, n in d['factions'][:6]])
        lines.append('   character %s' % d['character'])
        r = rule(db, b)
        lines.append('   rule: density x%.2f, hangings x%.2f, cap %s, rate x%.2f, container max %s' % (r['density'], r['hang'], r['cap'], r['rate'], r['cont_max']))
    T = trades(db, limit) or {}
    lines.append('== trades (n >= 3)')
    for tid, t in sorted(T.items(), key=lambda kv: -kv[1]['n']):
        if t['n'] < 3:
            continue
        lines.append('   %-28s %-8s n %3d  %-12s %s extras %s' % (names[t['kind']].get(tid, tid)[:28], t['kind'], t['n'], t['band'], t['bands'], t['extras']))
    return lines
