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


def preview(db, look, mat=None, between=None, stem='', armor=(), weapons=(), looks=None):
    """What the set would be, piece by piece: [{'kind', 'type', 'label', 'look': {i, id, name}, 'name', 'stats',
    'weight_class'}]. looks {type: record index}: a slot's look picked by hand ("Looks like", forgelooks.py), from
    any piece of that slot in the load order."""
    s = gearsurvey.survey(db)
    out = []
    for kind, types in (('armor', armor), ('weapon', weapons)):
        for ty in types:
            g = s['groups'].get((kind, ty, look))
            pick = (looks or {}).get(ty)
            if pick is not None and 0 <= int(pick) < len(db.recs) and db.recs[int(pick)] and db.recs[int(pick)][0] in ('WEAP', 'ARMO'):
                li = int(pick)
            elif not g or not g['looks']:
                continue
            else:
                li = _look_for(db, g, look)
            r = db.recs[li]
            p = gearsurvey.propose(db, kind, ty, None if between else (mat or look), between)
            row = {'kind': kind, 'type': ty, 'label': gearsurvey.LABEL.get(ty, ty), 'look': {'i': li, 'id': r[1], 'name': r[2] or r[1]},
                   'name': _name_like(r[2] or '', look, stem or 'New', ty), 'stats': p['stats']}
            if kind == 'armor':
                row['weight_class'] = p.get('weight_class')
            out.append(row)
    return out


def make(db, look, mat=None, between=None, stem='', armor=(), weapons=(), names=None, looks=None, style=None):
    """Make the set: one record a piece, the whole set one Undo. names: {type: name} the user changed; looks
    {type: record index} picked by hand; style {'own': {type: Library model}, 'worn': {type: {part: Library
    model}}, 'skin': {texture: new texture}} (forgelooks.restyle; the skin goes over every piece).
    Returns {'made': [{'type', 'id', 'i', 'name'}]}."""
    import create
    import editing
    import forgelooks
    import items
    if not (stem or '').strip():
        raise ValueError('Give the set a name, like "Sunsteel".')
    rows = preview(db, look, mat, between, stem.strip(), armor, weapons, looks)
    if not rows:
        raise ValueError('Pick at least one piece for the set.')
    made = []
    prefix = create._prefix(db)
    st = style or {}
    steps = 0
    for row in rows:
        name = ((names or {}).get(row['type']) or row['name']).strip()[:31]
        rid = create.suggest_id(db, prefix, name)
        # (an enchanted look gives its look only: its enchantment is left behind)
        r = items.create_item(db, {'template': row['look']['i'], 'id': rid, 'name': name, 'stats': row['stats'], 'enchant': {'effects': []}})
        steps += 1
        own, worn = (st.get('own') or {}).get(row['type']), (st.get('worn') or {}).get(row['type'])
        if own or worn or st.get('skin'):
            forgelooks.restyle(db, r.get('id', rid), own=own, worn_own=worn, skin=st.get('skin'))
            editing.commit(db, 'Gave %s its look' % name)
            steps += 1
            r['i'] = db.resolve_id(r.get('id', rid))
        made.append({'type': row['type'], 'kind': row['kind'], 'id': r.get('id', rid), 'i': r.get('i'), 'name': name})
        remember(db, r.get('id', rid), None if between else (mat or look), between)
    if steps > 1:
        editing.fold(db, steps, 'Forged the %s set (%d pieces)' % (stem.strip(), len(made)))
    return {'made': made}


def remember(db, rid, mat=None, between=None):
    """What a piece was forged as, kept with the mod (project.forged), for Into the world opened later: its name
    can say another material ("Duskglass Helm" read as glass)."""
    if not db.project or not rid or not (mat or between):
        return
    db.project.forged[rid.lower()] = {'between': [between[0], between[1], float(between[2])]} if between else {'mat': mat}
    db.project.save()


def forged_as(db, rid):
    """(mat, between) a piece was forged as, or (None, None)."""
    e = (getattr(db.project, 'forged', None) or {}).get((rid or '').lower()) if db.project else None
    if not e:
        return None, None
    return e.get('mat'), (tuple(e['between']) if e.get('between') else None)


def make_one(db, d):
    """One Forge piece: items.create_item with its look's enchantment left behind, then its own model, worn
    models or skin (d['style'], as make's), one Undo."""
    import editing
    import forgelooks
    import items
    r = items.create_item(db, dict(d, enchant={'effects': []}))
    remember(db, r['id'], d.get('mat'), d.get('between'))
    st = d.get('style') or {}
    if st.get('own') or st.get('worn') or st.get('skin'):
        forgelooks.restyle(db, r['id'], own=st.get('own'), worn_own=st.get('worn'), skin=st.get('skin'))
        editing.commit(db, 'Gave %s its look' % d.get('name', r['id']))
        editing.fold(db, 2, 'Forged %s' % d.get('name', r['id']))
        r['i'] = db.resolve_id(r['id'])
    return r
