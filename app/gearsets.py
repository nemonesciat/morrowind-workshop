"""A whole set of weapons and armour in one go (the Forge's Set tab; packaging/nexus/weapons-armour-plan.md, stage 2).

A set takes its look from one of the game's materials (each slot's piece nearest that material's median, as the
Forge's single pieces do), its numbers from a material or from a new one between two (gearsurvey.propose), and a
name: each piece is named as its look is, with the material swapped for yours ("Steel Cuirass" for a "Sunsteel"
set: "Sunsteel Cuirass"). Every piece is one record made by items.create_item, and the whole set is one Undo."""
import re

import gearsurvey

ARMOR_ORDER = ['Helmet', 'Cuirass', 'LPauldron', 'RPauldron', 'LGauntlet', 'RGauntlet', 'LBracer', 'RBracer', 'Greaves', 'Boots', 'Shield']
MIN_SLOTS = 4          # (a material offered as a set's look when the game has this many of its armour slots)


def options(db):
    """The materials a set can look like, with the armour slots and weapon types the game has of each:
    {'looks': [{'material', 'armor': [slot], 'weapons': [type]}], 'all_materials': [...]}."""
    s = gearsurvey.survey(db)
    by = {}
    for (kind, ty, mat), g in s['groups'].items():
        e = by.setdefault(mat, {'material': mat, 'armor': [], 'weapons': []})
        (e['armor'] if kind == 'armor' else e['weapons']).append(ty)
    looks = []
    for mat, e in by.items():
        if len(e['armor']) < MIN_SLOTS:
            continue
        e['armor'] = [t for t in ARMOR_ORDER if t in e['armor']]
        e['weapons'] = [t for t, _l in gearsurvey.WEAPON_TYPES if t in e['weapons']]
        e['pair'] = _pair(db, s, mat, e['armor'])
        looks.append(e)
    looks.sort(key=lambda e: s['tiers'].get(e['material'], 0))
    labels = dict(gearsurvey.WEAPON_TYPES + gearsurvey.ARMOR_SLOTS)
    return {'looks': looks, 'labels': labels, 'all_materials': sorted(s['tiers'], key=lambda m: s['tiers'][m])}


def _name_like(look_name, look_mat, stem, ty):
    """The look's own name with its material swapped for the set's ("Steel Cuirass" → "Sunsteel Cuirass"); a look
    whose name doesn't say its material: the set's name and the slot."""
    pat = re.compile(re.escape(look_mat) if look_mat != 'dwemer' else r'dwemer|dwarven', re.I)
    if look_name and pat.search(look_name):
        return pat.sub(stem, look_name, count=1)[:31]
    return ('%s %s' % (stem, gearsurvey.LABEL.get(ty, ty).split(',')[0].split(' (')[0]))[:31]


BASE = ('morrowind.esm', 'tribunal.esm', 'bloodmoon.esm')


def _look_for(db, g, mat):
    """A set's piece for one slot: the plainest of the game's pieces of the material, so the pieces belong
    together: one named for the material first ("Steel Helm", not "Imperial Steel Helmet"), from the base
    game before a mod's, then the nearest the material's median (the Forge's own order)."""
    # (the material named anywhere in it: the game's own "Left Glass Bracer")
    pat = re.compile(r'\b(%s)\b' % ('dwemer|dwarven' if mat == 'dwemer' else re.escape(mat)), re.I)
    # (one named for the material first, then the base game's, then the plainest name: "Steel Cuirass" before
    # "Ancient Steel Cuirass", "Dwemer Left Pauldron" before Tamriel Data's "Dwemer Scrap Left Pauldron")
    def rank(n_i):
        n, i = n_i
        r = db.recs[i]
        return (0 if pat.search(r[2] or '') else 1, 0 if _base(db, i) else 1, len(r[2] or r[1]), n)
    # (every piece of the material, not only the Forge's looks nearest its median: the plain ones can be far off it)
    return min(enumerate(g.get('members') or g['looks']), key=rank)[1]


def _base(db, i):
    """Made by the base game (Morrowind, Tribunal, Bloodmoon), whatever later mod changes it."""
    r = db.recs[i]
    return any(db.plugins[db.recs[v][3]]['name'].lower() in BASE for v in db.by_key.get((r[0], r[7]), []))


def _pair(db, s, mat, slots):
    """Gauntlets or bracers for a set of this look, as one is worn or the other: the pair the base game has both
    of (its glass and orcish have bracers, its steel gauntlets), else the pair the load order has both of."""
    def both(a, b, base_only):
        return all(t in slots and (not base_only or any(_base(db, i) for i in (s['groups'][('armor', t, mat)].get('members') or s['groups'][('armor', t, mat)]['looks']))) for t in (a, b))
    for base_only in (True, False):
        if both('LGauntlet', 'RGauntlet', base_only):
            return 'gauntlet'
        if both('LBracer', 'RBracer', base_only):
            return 'bracer'
    return None


def preview(db, look, mat=None, between=None, stem='', armor=(), weapons=()):
    """What the set would be, piece by piece: [{'kind', 'type', 'label', 'look': {i, id, name}, 'name', 'stats',
    'weight_class'}]."""
    s = gearsurvey.survey(db)
    out = []
    for kind, types in (('armor', armor), ('weapon', weapons)):
        for ty in types:
            g = s['groups'].get((kind, ty, look))
            if not g or not g['looks']:
                continue
            li = _look_for(db, g, look)
            r = db.recs[li]
            p = gearsurvey.propose(db, kind, ty, None if between else (mat or look), between)
            row = {'kind': kind, 'type': ty, 'label': gearsurvey.LABEL.get(ty, ty), 'look': {'i': li, 'id': r[1], 'name': r[2] or r[1]},
                   'name': _name_like(r[2] or '', look, stem or 'New', ty), 'stats': p['stats']}
            if kind == 'armor':
                row['weight_class'] = p.get('weight_class')
            out.append(row)
    return out


def make(db, look, mat=None, between=None, stem='', armor=(), weapons=(), names=None):
    """Make the set: one record a piece, the whole set one Undo. names: {type: name} the user changed.
    Returns {'made': [{'type', 'id', 'i', 'name'}]}."""
    import create
    import editing
    import items
    if not (stem or '').strip():
        raise ValueError('Give the set a name, like "Sunsteel".')
    rows = preview(db, look, mat, between, stem.strip(), armor, weapons)
    if not rows:
        raise ValueError('Pick at least one piece for the set.')
    made = []
    prefix = create._prefix(db)
    for row in rows:
        name = ((names or {}).get(row['type']) or row['name']).strip()[:31]
        rid = create.suggest_id(db, prefix, name)
        r = items.create_item(db, {'template': row['look']['i'], 'id': rid, 'name': name, 'stats': row['stats']})
        made.append({'type': row['type'], 'kind': row['kind'], 'id': r.get('id', rid), 'i': r.get('i'), 'name': name})
    if len(made) > 1:
        editing.fold(db, len(made), 'Forged the %s set (%d pieces)' % (stem.strip(), len(made)))
    return {'made': made}
