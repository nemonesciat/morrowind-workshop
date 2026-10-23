"""New items and spells: start from an existing item, change what you want (name, stats, magic
effects, an enchantment), or write a new spell from scratch. Each is one change you can undo."""
import struct

import editing
from database import ATTRIBUTES, SKILLS
from editing import EditError, apply_changes, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

KINDS = {   # what the Create form offers: kind -> (label, record types)
    'weapon': ('Weapon', ('WEAP',)),
    'armor': ('Armor', ('ARMO',)),
    'clothing': ('Clothing & jewelry', ('CLOT',)),
    'potion': ('Potion', ('ALCH',)),
    'ingredient': ('Ingredient', ('INGR',)),
    'misc': ('Misc item or key', ('MISC',)),
    'light': ('Light, torch or candle', ('LIGH',)),
    'tool': ('Tool (lockpick, probe, repair, apparatus)', ('LOCK', 'PROB', 'REPA', 'APPA')),
    'book': ('Book or scroll', ('BOOK',)),
}
# the fields worth showing for each kind of record (labels as the record viewer names them)
STAT_FIELDS = {
    'WEAP': ['Weapon Type', 'Weight', 'Value', 'Condition', 'Speed', 'Reach', 'Enchant Points', 'Chop Min', 'Chop Max',
             'Slash Min', 'Slash Max', 'Thrust Min', 'Thrust Max'],
    'ARMO': ['Armor Type', 'Weight', 'Value', 'Condition', 'Enchant Points', 'Armor Rating'],
    'CLOT': ['Clothing Type', 'Weight', 'Value', 'Enchant Points'],
    'ALCH': ['Weight', 'Value'],
    'INGR': ['Weight', 'Value'],
    'MISC': ['Weight', 'Value'],
    'LIGH': ['Weight', 'Value', 'Duration', 'Radius', 'Red', 'Green', 'Blue'],
    'LOCK': ['Weight', 'Value', 'Quality', 'Uses'],
    'PROB': ['Weight', 'Value', 'Quality', 'Uses'],
    'REPA': ['Weight', 'Value', 'Uses', 'Quality'],
    'APPA': ['Apparatus Type', 'Quality', 'Weight', 'Value'],
    'BOOK': ['Weight', 'Value', 'Enchant Points'],
}
SPELL_TYPES = ['Spell', 'Ability', 'Blight disease', 'Disease', 'Curse', 'Power']
ENCH_TYPES = ['Cast once', 'Cast when strikes', 'Cast when used', 'Constant effect']
RANGES = ['Self', 'Touch', 'Target']
EFFECT_SUB = {'ALCH': 'ENAM', 'SPEL': 'ENAM', 'ENCH': 'ENAM'}
NO_MAG = ('Summon', 'Bound', 'Cure', 'Mark', 'Recall', 'Divine Intervention', 'Almsivi Intervention', 'Water Breathing',
          'Water Walking', 'Invisibility', 'Paralyze', 'Silence', 'Vampirism', 'Corprus', 'Remove Curse', 'Turn Undead')
NO_DUR = ('Cure', 'Dispel', 'Mark', 'Recall', 'Divine Intervention', 'Almsivi Intervention', 'Open', 'Lock', 'Remove Curse')


# ------------------------------------------------------------------ magic effects
_effects = None


def effects(db, vanilla_only=False):
    """Every magic effect: [{index, name, school, cost, skill, attribute, magnitude, duration}]; with Tamriel
    Data in the load order its own effects too (index "T_...", td True: see tdeffects.py)."""
    if not vanilla_only:
        try:
            import tdeffects
            td = tdeffects.effects(db)
        except Exception as e:
            print('Tamriel Data effects:', e)
            td = []
        if td:
            return sorted(effects(db, True) + td, key=lambda e: (e['school'], e['name']))
    global _effects
    if _effects is not None and _effects[0] is db.recs:
        return _effects[1]
    out = []
    for (tag, key), lst in db.by_key.items():
        if tag != 'MGEF' or not lst or lst[-1] in db.dead or not key.lstrip('-').isdigit():
            continue
        r = db.recs[lst[-1]]
        _t, _f, data = db.files[r[3]].record_at(r[4])
        school, cost = 0, 1.0
        for st, sd in iter_subrecords(data):
            if st == 'MEDT' and len(sd) >= 8:
                school, cost = struct.unpack_from('<if', sd)
        idx = int(key)
        name = db.effect_names.get(idx, 'Effect %d' % idx)
        out.append({'index': idx, 'name': name, 'school': ['Alteration', 'Conjuration', 'Destruction', 'Illusion',
                                                            'Mysticism', 'Restoration'][school] if 0 <= school < 6 else '',
                    'cost': round(cost, 2), 'skill': 'Skill' in name, 'attribute': 'Attribute' in name,
                    'magnitude': not name.startswith(NO_MAG), 'duration': not name.startswith(NO_DUR)})
    out.sort(key=lambda e: (e['school'], e['name']))
    _effects = (db.recs, out)
    return out


def _named(v):
    """An effect named by its id (Tamriel Data's "T_...", or the mod's own: tdeffects.py), not the engine's number."""
    return isinstance(v, str) and not v.strip().lstrip('-').isdigit()


def _pack_effects(db, effs):
    known = {e['index']: e for e in effects(db)}
    if not effs:
        raise EditError('Add at least one magic effect.')
    if len(effs) > 8:
        raise EditError('At most 8 effects.')
    out = []
    for e in effs:
        idx = e['effect'] if _named(e['effect']) else int(e['effect'])
        info = known.get(idx)
        if not info:
            raise EditError('Unknown magic effect %s.' % idx)
        if info.get('td'):
            # (Tamriel Data's effect: the record carries its template's, and the mod's load script puts the
            # real one in as the game loads: tdeffects.remember, called by whoever writes the record)
            if db.project and not db.project.lua_allowed():
                raise EditError('%s is put in by an OpenMW script as the game loads, and a plain .esp like %s can\'t carry '
                                'scripts, so the game would show its stand-in (%s) instead. Use Save as… on My mod to make the '
                                'mod an .omwaddon (it keeps everything), or pick one of the game\'s own effects.' % (
                                    info['name'], db.project.plugin, known.get(info['template'], {}).get('name', 'another effect')))
            idx = info['template']
        skill = int(e.get('skill', -1)) if info['skill'] else -1
        attr = int(e.get('attribute', -1)) if info['attribute'] else -1
        if info['skill'] and skill < 0:
            raise EditError('"%s" needs a skill.' % info['name'])
        if info['attribute'] and attr < 0:
            raise EditError('"%s" needs an attribute.' % info['name'])
        lo, hi = int(e.get('min', 1) or 0), int(e.get('max', e.get('min', 1)) or 0)
        out.append(struct.pack('<hbbiiiii', idx, skill, attr, int(e.get('range', 0)), int(e.get('area', 0) or 0),
                               int(e.get('duration', 0) or 0), min(lo, hi), max(lo, hi)))
    return out


def unpack_effects(data, sub):
    out = []
    for st, sd in iter_subrecords(data):
        if st == sub and len(sd) >= 24:
            idx, skill, attr, rng, area, dur, lo, hi = struct.unpack_from('<hbbiiiii', sd)
            out.append({'effect': idx, 'skill': skill, 'attribute': attr, 'range': rng, 'area': area, 'duration': dur,
                        'min': lo, 'max': hi})
    return out


def _gmst_f(db, name, default):
    lst = [v for v in db.by_key.get(('GMST', name.lower()), []) if v not in db.dead]
    if lst:
        r = db.recs[lst[-1]]
        for st, sd in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
            if st == 'FLTV' and len(sd) >= 4:
                return struct.unpack_from('<f', sd)[0]
    return default


def spell_cost(db, effs, constant=False):
    """Magicka cost (or enchantment cost) the way OpenMW works it out: for each effect,
    average magnitude x 0.1 x the effect's base cost x (1 + duration), plus 0.05 x area x base
    cost, all times fEffectCostMult; half as much again for effects cast on a target. Constant
    effects count as lasting fEnchantmentConstantDurationMult (100) seconds."""
    known = {e['index']: e for e in effects(db)}
    mult = _gmst_f(db, 'fEffectCostMult', 0.5)
    const_dur = _gmst_f(db, 'fEnchantmentConstantDurationMult', 100.0)
    total = 0.0
    for e in effs:
        v = e['effect']
        info = known.get(v if _named(v) else int(v))
        if not info:
            continue
        lo = max(1, int(e.get('min', 1) or 1)) if info['magnitude'] else 1
        hi = max(1, int(e.get('max', lo) or lo)) if info['magnitude'] else 1
        dur = (const_dur if constant else max(1, int(e.get('duration', 1) or 1))) if info['duration'] else 1
        x = 0.5 * (lo + hi) * 0.1 * info['cost'] * (1 + dur) + 0.05 * max(1, int(e.get('area', 0) or 0)) * info['cost']
        x *= mult
        if int(e.get('range', 0)) == 2:
            x *= 1.5
        total += x
    return max(1, int(round(total)))


# ------------------------------------------------------------------ helpers
def _check_new_id(db, tag, new_id):
    new_id = (new_id or '').strip()
    if not new_id:
        raise EditError('Give it an ID.')
    if len(new_id.encode(ENC, 'replace')) > 31:
        raise EditError('IDs can be at most 31 characters.')
    if db.resolve_id(new_id) is not None or db.by_key.get((tag, new_id.lower())):
        raise EditError('Something with the ID "%s" already exists.' % new_id)
    return new_id


def _replace(subs, tag, values, after=('NAME', 'FNAM', 'MODL')):
    """Subrecords with every `tag` replaced by the new values (put back where the first one was,
    or after the given tags)."""
    out, put = [], False
    pos = next((n for n, (t, _d) in enumerate(subs) if t == tag), None)
    for n, (t, d) in enumerate(subs):
        if t == tag:
            if not put:
                out += [(tag, v) for v in values]
                put = True
            continue
        out.append((t, d))
    if not put and values:
        at = max([n + 1 for n, (t, _d) in enumerate(out) if t in after] or [len(out)])
        out[at:at] = [(tag, v) for v in values]
    return out


def options(db):
    return {'kinds': [{'id': k, 'label': v[0], 'types': list(v[1])} for k, v in KINDS.items()],
            'effects': effects(db), 'skills': SKILLS, 'attributes': ATTRIBUTES, 'ranges': RANGES,
            'spell_types': SPELL_TYPES, 'ench_types': ENCH_TYPES, 'stat_fields': STAT_FIELDS}


def template_info(db, i):
    """What a template item has: its editable stats, name and magic, for the form."""
    r = db.recs[int(i)]
    tag = r[0]
    d = db.record(int(i))
    wanted = STAT_FIELDS.get(tag, [])
    stats = []
    for f in d['fields']:
        if f['label'] in wanted and f.get('edit') and f['edit'].get('k') == 'num':
            stats.append({'label': f['label'], 'value': f['edit'].get('raw', f['value']), 'opts': f['edit'].get('opts')})
        elif f['label'] in wanted and f.get('edit') and f['edit'].get('opts'):
            stats.append({'label': f['label'], 'value': f['edit'].get('raw', 0), 'opts': f['edit']['opts']})
    _t, _f, data = db.files[r[3]].record_at(r[4])
    import tdeffects
    out = {'tag': tag, 'id': r[1], 'name': r[2], 'stats': stats, 'can_enchant': tag in ('WEAP', 'ARMO', 'CLOT', 'BOOK'),
           'effects': tdeffects.overlay(db, 'ALCH', r[1], unpack_effects(data, 'ENAM')) if tag == 'ALCH' else []}
    ench = next((zstr(sd) for st, sd in iter_subrecords(data) if st == 'ENAM' and tag != 'ALCH'), '')
    if ench:
        ei = db.resolve_id(ench)
        if ei is not None and db.recs[ei][0] == 'ENCH':
            er = db.recs[ei]
            _t2, _f2, ed = db.files[er[3]].record_at(er[4])
            et = next((struct.unpack_from('<iiii', sd) for st, sd in iter_subrecords(ed) if st == 'ENDT' and len(sd) >= 16), None)
            out['enchant'] = {'id': er[1], 'type': et[0] if et else 1, 'charge': et[2] if et else 100,
                              'effects': tdeffects.overlay(db, 'ENCH', er[1], unpack_effects(ed, 'ENAM'))}
    return out


# ------------------------------------------------------------------ creating
def create_item(db, d):
    """d: {template (record index), id, name, stats: {label: value}, effects: [...] (potions),
    enchant: {type, charge, effects} or None, keep_script: bool, give_to: NPC/container id}."""
    _require_project(db)
    ti = int(d['template'])
    tr = db.recs[ti]
    tag = tr[0]
    if tag not in STAT_FIELDS:
        raise EditError('That kind of record can\'t be used as an item template here.')
    new_id = _check_new_id(db, tag, d.get('id'))
    name = (d.get('name') or '').strip()
    if not name:
        raise EditError('Give it a name.')
    _t, flags, data = db.files[tr[3]].record_at(tr[4])
    # stats: edit the template's own fields (same layout), then make the copy
    rec = db.record(ti)
    edits = []
    for label, value in (d.get('stats') or {}).items():
        f = next((f for f in rec['fields'] if f['label'] == label and f.get('edit')), None)
        if f is None or value in (None, ''):
            continue
        e = dict(f['edit'])
        if e.get('opts') and not str(value).lstrip('-').isdigit():
            low = [o.lower() for o in e['opts']]
            value = low.index(str(value).lower()) if str(value).lower() in low else value
        edits.append(dict(e, value=value))
    if edits:
        data = apply_changes(data, edits)
    subs = [(t, bytes(v)) for t, v in iter_subrecords(data)]
    subs = [(t, zs(new_id) if t == 'NAME' else v) for t, v in subs]
    subs = _replace(subs, 'FNAM', [zs(name[:31])])
    if not d.get('keep_script'):
        subs = [(t, v) for t, v in subs if t != 'SCRI']
    import tdeffects
    if tag == 'ALCH' and d.get('effects') is not None:
        subs = _replace(subs, 'ENAM', _pack_effects(db, d['effects']), after=('NAME', 'FNAM', 'MODL', 'TEXT', 'SCRI', 'ALDT'))
        tdeffects.remember(db, 'ALCH', new_id, d['effects'])
    made = [new_id]
    ench = d.get('enchant')
    if ench and tag in ('WEAP', 'ARMO', 'CLOT', 'BOOK'):
        if ench.get('effects'):
            eid = (new_id[:27] + '_en')
            n = 2
            while db.resolve_id(eid) is not None:
                eid = '%s_en%d' % (new_id[:25], n)
                n += 1
            et = int(ench.get('type', 1))
            packed = _pack_effects(db, ench['effects'])
            cost = spell_cost(db, ench['effects'], constant=(et == 3))
            charge = int(ench.get('charge') or (0 if et == 3 else max(cost * 5, 50)))
            edata = join_subs([('NAME', zs(eid)), ('ENDT', struct.pack('<iiii', et, cost, charge, 0))] +
                              [('ENAM', p) for p in packed])
            db.project.set_record('ENCH', eid.lower(), 0, edata, created=True)
            tdeffects.remember(db, 'ENCH', eid, ench['effects'])
            subs = _replace(subs, 'ENAM', [zs(eid)], after=('NAME', 'MODL', 'FNAM', 'SCRI', 'ITEX'))
            made.append(eid)
        else:
            subs = [(t, v) for t, v in subs if t != 'ENAM']
    db.project.set_record(tag, new_id.lower(), flags & ~0x20, join_subs(subs), created=True)
    gave = _give(db, d.get('give_to'), new_id, 'item')
    commit(db, 'Created %s "%s" (%s) from "%s"%s' % (tag, name, new_id, tr[1], (' and gave it to ' + gave) if gave else ''))
    return {'id': new_id, 'i': db.overlay[(tag, new_id.lower())], 'made': made, 'given': gave}


def create_spell(db, d):
    """d: {id, name, type (0-5), effects: [...], cost (None = work it out), always_succeeds, player_starts,
    give_to: NPC id}."""
    _require_project(db)
    new_id = _check_new_id(db, 'SPEL', d.get('id'))
    name = (d.get('name') or '').strip()
    if not name:
        raise EditError('Give the spell a name.')
    effs = d.get('effects') or []
    packed = _pack_effects(db, effs)
    stype = int(d.get('type', 0))
    cost = int(d['cost']) if d.get('cost') not in (None, '') else spell_cost(db, effs)
    flg = (0 if d.get('cost') not in (None, '') else 1) | (2 if d.get('player_starts') else 0) | (4 if d.get('always_succeeds') else 0)
    data = join_subs([('NAME', zs(new_id)), ('FNAM', zs(name[:31])), ('SPDT', struct.pack('<iii', stype, cost, flg))] +
                     [('ENAM', p) for p in packed])
    db.project.set_record('SPEL', new_id.lower(), 0, data, created=True)
    import tdeffects
    tdeffects.remember(db, 'SPEL', new_id, effs)
    gave = _give(db, d.get('give_to'), new_id, 'spell')
    commit(db, 'Created %s "%s" (%s, %d magicka)%s' % (SPELL_TYPES[stype].lower() if 0 <= stype < 6 else 'spell', name,
                                                       new_id, cost, (' and gave it to ' + gave) if gave else ''))
    return {'id': new_id, 'i': db.overlay[('SPEL', new_id.lower())], 'cost': cost, 'given': gave}


def _give(db, who, thing, kind):
    """Add an item to an NPC's or container's inventory, or a spell to an NPC's spells. Returns their name."""
    who = (who or '').strip()
    if not who:
        return ''
    ri = db.resolve_id(who)
    if ri is None:
        raise EditError('No character or container called "%s".' % who)
    r = db.recs[ri]
    if kind == 'spell' and r[0] not in ('NPC_', 'CREA'):
        raise EditError('Spells can only be given to characters and creatures.')
    if kind == 'item' and r[0] not in ('NPC_', 'CREA', 'CONT'):
        raise EditError('Items can be given to characters, creatures and containers.')
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs = [(t, bytes(v)) for t, v in iter_subrecords(data)]
    if kind == 'spell':
        new = ('NPCS', thing.encode(ENC, 'replace')[:31].ljust(32, b'\0'))
        idx = max([n + 1 for n, (t, _v) in enumerate(subs) if t in ('NPCS', 'NPCO')] or
                  [n + 1 for n, (t, _v) in enumerate(subs) if t in ('NPDT', 'FLAG', 'AIDT')] or [len(subs)])
    else:
        new = ('NPCO', struct.pack('<i', 1) + thing.encode(ENC, 'replace')[:31].ljust(32, b'\0'))
        idx = max([n + 1 for n, (t, _v) in enumerate(subs) if t == 'NPCO'] or
                  [n + 1 for n, (t, _v) in enumerate(subs) if t in ('NPDT', 'FLAG', 'CNDT', 'FLAG')] or [len(subs)])
    subs.insert(idx, new)
    db.project.set_record(r[0], r[7], flags & ~0x20, join_subs(subs),
                          created=bool((db.project.records.get(r[0] + '|' + r[7]) or {}).get('created')))
    return r[2] or r[1]
