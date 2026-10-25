"""What the game's own weapons and armour are like, by type and material: the Forge proposes a new piece's
numbers from them and says when yours go beyond anything the game does (packaging/nexus/weapons-armour-plan.md).

Every weapon and armour piece in the load order (the mod being made left out) is read: its type or slot,
its material (read from its name, ID or model: about 70% have one; the rest are hats, canes and one-offs),
and its numbers. Enchanted pieces are left out of the figures (their value is the enchantment's). For each
type and material: how many, the median and the range of each number, and the game's pieces of it to take
the look from. Materials are put in tiers by the median value of their pieces over every type.

Measured (2026-10-25): left out in turn, 92% of the game's own plain pieces fall inside the others' range
of their type and material widened by 15%, so beyond that is worth a word ("fits the game"), not a nag.

Armour's weight class is the game's own rule: light up to fLightMaxMod (0.6) of the slot's base weight
(iHelmWeight...), medium up to fMedMaxMod (0.9), heavy above."""
import struct
from collections import Counter, defaultdict

from esm import iter_subrecords, zstr

WEAPON_TYPES = [('ShortBlade1H', 'Short blade'), ('LongBlade1H', 'Long blade, one-handed'), ('LongBlade2H', 'Long blade, two-handed'),
                ('Blunt1H', 'Blunt, one-handed (mace, club)'), ('Blunt2Close', 'Blunt, two-handed (warhammer)'),
                ('Blunt2Wide', 'Blunt, two-handed (staff)'), ('Spear2Wide', 'Spear'), ('Axe1H', 'Axe, one-handed'),
                ('Axe2H', 'Axe, two-handed'), ('Bow', 'Bow'), ('Crossbow', 'Crossbow'), ('Thrown', 'Thrown weapon'),
                ('Arrow', 'Arrow'), ('Bolt', 'Bolt')]
ARMOR_SLOTS = [('Helmet', 'Helmet'), ('Cuirass', 'Cuirass'), ('LPauldron', 'Left pauldron'), ('RPauldron', 'Right pauldron'),
               ('Greaves', 'Greaves'), ('Boots', 'Boots'), ('LGauntlet', 'Left gauntlet'), ('RGauntlet', 'Right gauntlet'),
               ('Shield', 'Shield'), ('LBracer', 'Left bracer'), ('RBracer', 'Right bracer')]
# the slot's base weight for its weight class (the GMST and its default)
SLOT_BASE = {'Helmet': ('iHelmWeight', 5), 'Cuirass': ('iCuirassWeight', 30), 'LPauldron': ('iPauldronWeight', 10),
             'RPauldron': ('iPauldronWeight', 10), 'Greaves': ('iGreavesWeight', 15), 'Boots': ('iBootsWeight', 20),
             'LGauntlet': ('iGauntletWeight', 5), 'RGauntlet': ('iGauntletWeight', 5), 'Shield': ('iShieldWeight', 15),
             'LBracer': ('iGauntletWeight', 5), 'RBracer': ('iGauntletWeight', 5)}
# materials in the order they're looked for in a name (a "dwarven" piece is dwemer; "bonemold" before "bone")
MATERIALS = ['daedric', 'ebony', 'glass', 'dwemer', 'dwarven', 'adamantium', 'orcish', 'silver', 'steel', 'iron', 'chitin',
             'bonemold', 'netch', 'fur', 'leather', 'nordic', 'imperial', 'dreugh', 'indoril', 'stalhrim', 'ice', 'templar',
             'dragonbone', 'bone', 'wood', 'elven', 'mithril', 'redoran', 'telvanni', 'royal', 'colovian', 'newtscale',
             'chain', 'goblin', 'trollbone']
ALIAS = {'dwarven': 'dwemer'}
LEEWAY = 0.15
FRACTIONAL = {'Weight', 'Speed', 'Reach'}
LABEL = dict(WEAPON_TYPES + ARMOR_SLOTS)
# the numbers of each kind, as the item form names them (items.STAT_FIELDS), and where they are in the record
W_STATS = ['Weight', 'Value', 'Condition', 'Speed', 'Reach', 'Enchant Points', 'Chop Min', 'Chop Max', 'Slash Min', 'Slash Max',
           'Thrust Min', 'Thrust Max']
A_STATS = ['Weight', 'Value', 'Condition', 'Enchant Points', 'Armor Rating']
_cache = {}


def material_of(*texts):
    s = ' '.join((t or '').lower() for t in texts)
    for m in MATERIALS:
        if m in s:
            return ALIAS.get(m, m)
    return None


def _gmst(db, name, default):
    lst = [v for v in db.by_key.get(('GMST', name.lower()), []) if v not in db.dead]
    if not lst:
        return default
    r = db.recs[lst[-1]]
    d = {t: bytes(v) for t, v in iter_subrecords(db.files[r[3]].record_at(r[4])[2])}
    if 'FLTV' in d:
        return struct.unpack('<f', d['FLTV'][:4])[0]
    if 'INTV' in d:
        return struct.unpack('<i', d['INTV'][:4])[0]
    return default


def weight_class(db, slot, weight):
    """'light', 'medium' or 'heavy' for an armour piece of this slot and weight, by the game's rule."""
    gm, dflt = SLOT_BASE.get(slot, ('iCuirassWeight', 30))
    base = float(_gmst(db, gm, dflt))
    if weight <= base * float(_gmst(db, 'fLightMaxMod', 0.6)) + 1e-6:
        return 'light'
    if weight <= base * float(_gmst(db, 'fMedMaxMod', 0.9)) + 1e-6:
        return 'medium'
    return 'heavy'


def _read(db, ri):
    r = db.recs[ri]
    d = {}
    for t, v in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        d.setdefault(t, bytes(v))
    name, model = zstr(d.get('FNAM', b'')), zstr(d.get('MODL', b''))
    out = {'i': ri, 'id': r[1], 'name': name, 'model': model, 'mat': material_of(r[1], name, model), 'enchanted': 'ENAM' in d}
    if r[0] == 'WEAP' and len(d.get('WPDT', b'')) >= 28:
        wt, val, ty, hp, spd, reach, ench = struct.unpack_from('<fiHHffH', d['WPDT'])
        dmg = struct.unpack_from('<6B', d['WPDT'], 22)
        if ty >= len(WEAPON_TYPES):
            return None
        out.update(kind='weapon', type=WEAPON_TYPES[ty][0],
                   stats=dict(zip(W_STATS, [round(wt, 2), val, hp, round(spd, 2), round(reach, 2), ench] + list(dmg))))
    elif r[0] == 'ARMO' and len(d.get('AODT', b'')) >= 24:
        ty, wt, val, hp, ench, ar = struct.unpack_from('<ifiiii', d['AODT'])
        if not 0 <= ty < len(ARMOR_SLOTS):
            return None
        out.update(kind='armor', type=ARMOR_SLOTS[ty][0], stats=dict(zip(A_STATS, [round(wt, 2), val, hp, ench, ar])))
    else:
        return None
    return out


def _q(v, f):
    v = sorted(v)
    return v[min(len(v) - 1, int(f * (len(v) - 1) + 0.5))] if v else None


def survey(db):
    """{'groups': {(kind, type, material): {'n', 'stats': {label: {'med', 'lo', 'hi', 'p10', 'p90'}}, 'looks':
    [record index, closest to the median first]}}, 'tiers': {material: rank 0 (cheapest) ...}, 'materials':
    {kind: {type: [materials with plain pieces, cheapest first]}}}."""
    if _cache.get('recs') is db.recs:
        return _cache['out']
    proj = getattr(db, 'proj_pidx', None)
    pieces = defaultdict(list)
    for (tag, _k), lst in db.by_key.items():
        if tag not in ('WEAP', 'ARMO'):
            continue
        live = [v for v in lst if v not in db.dead]
        # (the game's own: the last version from a file other than the mod being made)
        live = [v for v in live if proj is None or db.recs[v][3] != proj]
        if not live:
            continue
        it = _read(db, live[-1])
        if it and it['mat'] and not it['enchanted']:
            pieces[(it['kind'], it['type'], it['mat'])].append(it)
    groups = {}
    for key, lst in pieces.items():
        labels = W_STATS if key[0] == 'weapon' else A_STATS
        st = {}
        for lab in labels:
            vals = [p['stats'][lab] for p in lst]
            st[lab] = {'med': _q(vals, 0.5), 'lo': min(vals), 'hi': max(vals), 'p10': _q(vals, 0.1), 'p90': _q(vals, 0.9)}
        main = 'Armor Rating' if key[0] == 'armor' else None

        def off(p):
            # (the look: the piece nearest the median, by its main numbers)
            if main:
                return abs(p['stats'][main] - st[main]['med']) + abs(p['stats']['Value'] - st['Value']['med']) / max(1.0, st['Value']['med'])
            best = max(p['stats'][k] for k in ('Chop Max', 'Slash Max', 'Thrust Max'))
            mb = max(st[k]['med'] for k in ('Chop Max', 'Slash Max', 'Thrust Max'))
            return abs(best - mb) + abs(p['stats']['Value'] - st['Value']['med']) / max(1.0, st['Value']['med'])
        looks = sorted(lst, key=off)
        groups[key] = {'n': len(lst), 'stats': st, 'looks': [p['i'] for p in looks[:24]]}
    # tiers: each material's typical value against the other materials of the same types, over all types
    rank = defaultdict(list)
    by_type = defaultdict(list)
    for (kind, ty, m), g in groups.items():
        by_type[(kind, ty)].append((g['stats']['Value']['med'], m))
    for key, lst in by_type.items():
        lst.sort()
        for n, (_v, m) in enumerate(lst):
            rank[m].append(n / float(max(1, len(lst) - 1)))
    tiers = {m: round(sum(v) / len(v), 3) for m, v in rank.items()}
    materials = defaultdict(dict)
    for (kind, ty), lst in by_type.items():
        materials[kind][ty] = [m for _v, m in sorted(lst)]
    out = {'groups': groups, 'tiers': tiers, 'materials': {k: dict(v) for k, v in materials.items()}}
    _cache.update(recs=db.recs, out=out)
    return out


def options(db):
    """For the Forge's form: the kinds, types and the materials the game has for each, cheapest first."""
    s = survey(db)
    def rows(kind, lst):
        return [{'id': t, 'label': lab, 'materials': [{'id': m, 'n': s['groups'][(kind, t, m)]['n']} for m in s['materials'].get(kind, {}).get(t, [])]}
                for t, lab in lst if s['materials'].get(kind, {}).get(t)]
    return {'weapon': rows('weapon', WEAPON_TYPES), 'armor': rows('armor', ARMOR_SLOTS),
            'all_materials': sorted(s['tiers'], key=lambda m: s['tiers'][m])}


def _near(db, kind, ty, mat):
    """The group for this type and material; a material with no piece of this type borrows the curve of its
    tier: the type's materials either side of it in tier, mixed by where it lies between them."""
    s = survey(db)
    g = s['groups'].get((kind, ty, mat))
    if g:
        return g, None
    have = s['materials'].get(kind, {}).get(ty, [])
    if not have or mat not in s['tiers']:
        return None, None
    t = s['tiers'][mat]
    lower = [m for m in have if s['tiers'][m] <= t]
    upper = [m for m in have if s['tiers'][m] > t]
    a = max(lower, key=lambda m: s['tiers'][m]) if lower else None
    b = min(upper, key=lambda m: s['tiers'][m]) if upper else None
    if a and b:
        f = (t - s['tiers'][a]) / max(1e-6, s['tiers'][b] - s['tiers'][a])
        return mix(s['groups'][(kind, ty, a)], s['groups'][(kind, ty, b)], f), (a, b, round(f, 2))
    one = a or b
    return s['groups'][(kind, ty, one)], (one, one, 0.0)


def mix(ga, gb, f):
    """Two groups' figures mixed, f of the way from a to b (values on a log scale: tiers multiply value)."""
    import math
    st = {}
    for lab, a in ga['stats'].items():
        b = gb['stats'][lab]
        out = {}
        for k in ('med', 'lo', 'hi', 'p10', 'p90'):
            x, y = float(a[k]), float(b[k])
            if lab == 'Value' and x > 0 and y > 0:
                out[k] = round(math.exp(math.log(x) + (math.log(y) - math.log(x)) * f))
            elif lab in FRACTIONAL:
                out[k] = round(x + (y - x) * f, 2)
            else:
                out[k] = int(round(x + (y - x) * f))         # (whole numbers, as the game keeps them)
        st[lab] = out
    return {'n': 0, 'stats': st, 'looks': (ga['looks'][:12] + gb['looks'][:12])}


def propose(db, kind, ty, mat, between=None):
    """The numbers the game gives a piece of this type and material (its medians), their ranges, and the
    game's pieces to take the look from. between: (material a, material b, f) for a new material f of the way
    from a to b."""
    if between:
        a, b, f = between
        ga, _ = _near(db, kind, ty, a)
        gb, _ = _near(db, kind, ty, b)
        if not ga or not gb:
            raise ValueError('The game has no %s of %s or %s to go by.' % (ty, a, b))
        g, how = mix(ga, gb, float(f)), (a, b, float(f))
    else:
        g, how = _near(db, kind, ty, mat)
        if not g:
            raise ValueError('The game has no %s of any material to go by.' % ty)
    stats = {lab: v['med'] for lab, v in g['stats'].items()}
    out = {'kind': kind, 'type': ty, 'material': mat, 'n': g['n'], 'stats': stats, 'ranges': g['stats'], 'borrowed': how,
           'looks': [{'i': i, 'id': db.recs[i][1], 'name': db.recs[i][2] or db.recs[i][1]} for i in g['looks']]}
    if kind == 'armor':
        out['weight_class'] = weight_class(db, ty, stats['Weight'])
    return out


def check(db, kind, ty, mat, stats, between=None):
    """Each number against the game's range for this type and material, with the leeway: {label: 'ok' |
    'high' | 'low'}, and a sentence for the ones beyond."""
    p = propose(db, kind, ty, mat, between)
    out, notes = {}, []
    for lab, r in p['ranges'].items():
        if lab not in stats or stats[lab] in (None, ''):
            continue
        v = float(stats[lab])
        lo, hi = float(r['lo']) * (1 - LEEWAY), float(r['hi']) * (1 + LEEWAY)
        if lab == 'Weight' and kind == 'armor':
            continue                            # (any weight is fine: it decides the class, said apart)
        state = 'high' if v > hi + 1e-6 else 'low' if v < lo - 1e-6 else 'ok'
        out[lab] = state
        if state != 'ok':
            what = mat or (between and '%s-%s' % (between[0], between[1])) or 'this'
            kind_word = LABEL.get(ty, ty).split(' (')[0].lower()
            notes.append('%s is %s than on any %s %s in the game (%s to %s).' % (lab, 'higher' if state == 'high' else 'lower', what,
                                                                                    kind_word, r['lo'], r['hi']))
    res = {'states': out, 'notes': notes}
    if kind == 'armor' and stats.get('Weight') not in (None, ''):
        res['weight_class'] = weight_class(db, ty, float(stats['Weight']))
    return res
