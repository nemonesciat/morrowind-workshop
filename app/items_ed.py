"""Editing existing items, spells and enchantments, all of it: stats, name, looks, script, a
potion's or spell's effects, and an item's enchantment (its kind, charge, cost and effects).

Only what you change is changed: stats are edited in place in the record (the same way the record
viewer does it), and effect lists, the enchantment and the script are only rewritten when they
differ, so saving an item unchanged gives back the very same record."""
import struct

import editing
import items
from editing import EditError, apply_changes, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

ITEM_TAGS = ('WEAP', 'ARMO', 'CLOT', 'ALCH', 'INGR', 'MISC', 'LIGH', 'LOCK', 'PROB', 'REPA', 'APPA', 'BOOK')
EDIT_TAGS = ITEM_TAGS + ('SPEL', 'ENCH')
CAN_ENCHANT = ('WEAP', 'ARMO', 'CLOT', 'BOOK')
# fields the editor shows in sections of their own
SKIP_LABELS = ('ID', 'Effect', 'Enchantment', 'Script')


def _find(db, rid, tags=EDIT_TAGS):
    for t in tags:
        lst = [v for v in db.by_key.get((t, (rid or '').lower()), []) if v not in db.dead]
        if lst:
            return lst[-1]
    return None


def _data(db, ri):
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    return bytes(data), flags


def _ench(db, eid):
    """{id, i, type, cost, charge, auto, effects, src, used_by} of an enchantment, or None."""
    ei = _find(db, eid, ('ENCH',))
    if ei is None:
        return None
    er = db.recs[ei]
    ed, _f = _data(db, ei)
    et = next((struct.unpack_from('<iiii', sd) for st, sd in iter_subrecords(ed) if st == 'ENDT' and len(sd) >= 16), (1, 0, 0, 0))
    users = [{'id': rr[1], 'name': rr[2] or rr[1], 'tag': rr[0]} for rr in (db.recs[i] for i in _ench_users(db).get(er[1].lower(), ()))]
    return {'id': er[1], 'i': ei, 'type': et[0], 'cost': et[1], 'charge': et[2], 'auto': bool(et[3] & 1),
            'effects': items.unpack_effects(ed, 'ENAM'), 'src': db.plugins[er[3]]['name'], 'used_by': users}


_users = {}


def _ench_users(db):
    """enchantment id -> [record index of each item that uses it] (worked out once per load)."""
    stamp = (id(db.recs), len(db.recs), len(db.project.records) if db.project else 0)
    if _users.get('stamp') == stamp:
        return _users['map']
    out = {}
    for (tag, key), lst in db.by_key.items():
        if tag not in CAN_ENCHANT:
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        r = db.recs[live[-1]]
        for st, sd in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
            if st == 'ENAM':
                out.setdefault(zstr(sd).lower(), []).append(live[-1])
                break
    _users.update(stamp=stamp, map=out)
    return out


def read(db, rid):
    ri = _find(db, rid)
    if ri is None:
        raise EditError('There is no item, spell or enchantment called "%s".' % rid)
    r = db.recs[ri]
    tag = r[0]
    data, _flags = _data(db, ri)
    rec = db.record(ri)
    fields = []
    for n, f in enumerate(rec['fields']):
        e = f.get('edit')
        if not e or f['label'] in SKIP_LABELS or e.get('t') in ('SPDT', 'ENDT'):
            continue                       # (a spell's or enchantment's kind and cost have their own section)
        fields.append({'n': n, 'label': f['label'], 'kind': 'bits' if e.get('bits') else 'opts' if e.get('opts') else e['k'],
                       'value': e.get('raw', f['value']) if e['k'] == 'num' else str(f['value'] or ''),
                       'opts': e.get('opts'), 'bits': e.get('bits'), 'float': e.get('c') in ('f', 'd')})
    o = {'tag': tag, 'id': r[1], 'i': ri, 'name': r[2] or '', 'src': db.plugins[r[3]]['name'], 'fields': fields,
         'mine': bool(db.project and (tag + '|' + r[7]) in db.project.records),
         'created': bool(db.project and (db.project.records.get(tag + '|' + r[7]) or {}).get('created'))}
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    o['script'] = next((zstr(d) for t, d in subs if t == 'SCRI'), '')
    if tag in ('ALCH', 'SPEL', 'ENCH'):
        o['effects'] = items.unpack_effects(data, 'ENAM')
    if tag == 'BOOK':
        o['text'] = next((d.rstrip(b'\0').decode(ENC, 'replace') for t, d in subs if t == 'TEXT'), '')
    if tag in CAN_ENCHANT:
        o['can_enchant'] = True
        eid = next((zstr(d) for t, d in subs if t == 'ENAM'), '')
        o['enchant'] = _ench(db, eid) if eid else None
        if eid and not o['enchant']:
            o['enchant_missing'] = eid
    if tag == 'ENCH':
        e = _ench(db, r[1])
        o.update({k: e[k] for k in ('type', 'cost', 'charge', 'auto', 'used_by')})
    if tag == 'SPEL':
        sp = next((struct.unpack_from('<iii', d) for t, d in subs if t == 'SPDT' and len(d) >= 12), (0, 0, 0))
        o['spell'] = {'type': sp[0], 'cost': sp[1], 'auto': bool(sp[2] & 1)}
        o['cost_now'] = items.spell_cost(db, o['effects']) if o['effects'] else 0
    return o


def _set_sub(subs, tag, value, after):
    """Put, replace or (value None) remove a single subrecord."""
    return items._replace(subs, tag, [value] if value is not None else [], after=after)


def _effects_changed(old, new):
    keys = ('effect', 'skill', 'attribute', 'range', 'area', 'duration', 'min', 'max')
    norm = lambda l: [tuple(int(e.get(k, -1 if k in ('skill', 'attribute') else 0) or 0) for k in keys) for e in l]
    return norm(old) != norm(new)


def _save_ench(db, eid, ench, create):
    """Write an enchantment record (new, or changed in place). Returns its id."""
    et = int(ench.get('type', 1))
    if not 0 <= et <= 3:
        raise EditError('Unknown kind of enchantment.')
    effs = ench.get('effects') or []
    packed = items._pack_effects(db, effs)
    if et == 3 and any(int(e.get('range', 0)) != 0 for e in effs):
        raise EditError('Constant effects only work on the wearer: set every effect\'s range to Self.')
    auto = bool(ench.get('auto'))
    cost = items.spell_cost(db, effs, constant=(et == 3)) if auto or ench.get('cost') in (None, '') else int(ench['cost'])
    charge = int(ench.get('charge') or 0)
    if et != 3 and charge <= 0:
        charge = max(cost * 5, 50)
    key = eid.lower()
    if not create:
        # an automatic cost stays as it is unless the effects or the kind changed
        old = _ench(db, eid)
        if auto and old and old['auto'] and old['type'] == et and not _effects_changed(old['effects'], effs):
            cost = old['cost']
    if create:
        subs = [('NAME', zs(eid)), ('ENDT', struct.pack('<iiii', et, cost, charge, 1 if auto else 0))] + [('ENAM', p) for p in packed]
        db.project.set_record('ENCH', key, 0, join_subs(subs), created=True)
        return eid
    ei = _find(db, eid, ('ENCH',))
    data, flags = _data(db, ei)
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    old = next((d for t, d in subs if t == 'ENDT'), b'\0' * 16)
    endt = struct.pack('<iiii', et, cost, charge, (struct.unpack_from('<i', old, 12)[0] & ~1) | (1 if auto else 0)) + old[16:]
    new = _set_sub(subs, 'ENDT', endt, after=('NAME',))
    if _effects_changed(items.unpack_effects(data, 'ENAM'), effs):
        new = items._replace(new, 'ENAM', packed, after=('NAME', 'ENDT'))
    if new != subs:
        was = bool((db.project.records.get('ENCH|' + key) or {}).get('created'))
        db.project.set_record('ENCH', key, flags & ~0x20, join_subs(new), created=was)
    return db.recs[ei][1]


def _own_ench_id(db, item_id):
    eid = item_id[:27] + '_en'
    n = 2
    while db.resolve_id(eid) is not None or db.by_key.get(('ENCH', eid.lower())):
        eid = '%s_en%d' % (item_id[:25], n)
        n += 1
    return eid


def save(db, rid, o):
    """o: what read() gave, changed: fields[].value, script, effects, text, enchant (None removes it;
    {..., 'scope': 'all' | 'this'} where 'this' gives the item an enchantment of its own when others
    share it), spell {type, cost, auto}; for an enchantment: type, charge, cost, auto, effects."""
    _require_project(db)
    ri = _find(db, rid)
    if ri is None:
        raise EditError('There is no item, spell or enchantment called "%s".' % rid)
    r = db.recs[ri]
    tag, key = r[0], r[7]
    data, flags = _data(db, ri)
    cur = read(db, rid)
    rec = db.record(ri)
    notes = []
    # ---- stats, name, looks: only what changed
    edits = []
    byn = {f['n']: f for f in cur['fields']}
    for f in o.get('fields') or []:
        old = byn.get(f.get('n'))
        if old is None:
            continue
        nv = f.get('value')
        if old['kind'] == 'str':
            if str(nv or '') == old['value']:
                continue
            if old['label'] == 'Name' and len(str(nv).encode(ENC, 'replace')) > 31:
                raise EditError('Names can be at most 31 characters.')
        else:
            try:
                same = abs(float(nv) - float(old['value'])) < (1e-4 if old['float'] else 0.5)
            except (TypeError, ValueError):
                raise EditError('"%s" must be a number.' % old['label'])
            if same:
                continue
        edits.append(dict(rec['fields'][old['n']]['edit'], value=nv))
    if edits:
        data = apply_changes(data, edits)
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    # ---- script
    if 'script' in o and (o.get('script') or '') != cur['script']:
        sid = (o.get('script') or '').strip()
        if sid:
            si = db.resolve_id(sid)
            if si is None or db.recs[si][0] != 'SCPT':
                raise EditError('There is no script called "%s".' % sid)
            sid = db.recs[si][1]
        subs = _set_sub(subs, 'SCRI', zs(sid) if sid else None, after=('NAME', 'MODL', 'FNAM'))
    # ---- a book's text
    if tag == 'BOOK' and 'text' in o and (o.get('text') or '') != cur.get('text', ''):
        subs = _set_sub(subs, 'TEXT', (o.get('text') or '').encode(ENC, 'replace'), after=('NAME', 'MODL', 'FNAM', 'BKDT', 'ITEX', 'SCRI'))
    # ---- effects (potions, spells, enchantments)
    if tag in ('ALCH', 'SPEL', 'ENCH') and o.get('effects') is not None and _effects_changed(cur['effects'], o['effects']):
        after = {'ALCH': ('NAME', 'MODL', 'TEXT', 'FNAM', 'SCRI', 'ALDT'), 'SPEL': ('NAME', 'FNAM', 'SPDT'), 'ENCH': ('NAME', 'ENDT')}[tag]
        subs = items._replace(subs, 'ENAM', items._pack_effects(db, o['effects']), after=after)
    # ---- a spell's kind, cost and flags
    if tag == 'SPEL' and o.get('spell'):
        sp = o['spell']
        old = next((d for t, d in subs if t == 'SPDT'), b'\0' * 12)
        st, cost, fl = struct.unpack_from('<iii', old)
        auto = bool(sp.get('auto'))
        effs_changed = o.get('effects') is not None and _effects_changed(cur['effects'], o['effects'])
        # a worked-out cost is only worked out again when the effects change or it is newly switched on
        if auto and (effs_changed or not (fl & 1)):
            ncost = items.spell_cost(db, o.get('effects') or cur['effects'])
        elif auto:
            ncost = cost
        else:
            ncost = int(sp.get('cost') or 0)
        nfl = (fl & ~1) | (1 if auto else 0)
        nst = int(sp.get('type', st))
        if (nst, ncost, nfl) != (st, cost, fl):
            subs = _set_sub(subs, 'SPDT', struct.pack('<iii', nst, ncost, nfl) + old[12:], after=('NAME', 'FNAM'))
    # ---- an enchantment edited on its own
    if tag == 'ENCH':
        ench = {k: o.get(k, cur.get(k)) for k in ('type', 'cost', 'charge', 'auto')}
        ench['effects'] = o.get('effects') if o.get('effects') is not None else cur['effects']
        old = next((d for t, d in subs if t == 'ENDT'), b'\0' * 16)
        et, cost, charge, fl = struct.unpack_from('<iiii', old)
        auto = bool(ench['auto'])
        redo = _effects_changed(cur['effects'], ench['effects']) or not (fl & 1) or int(ench['type']) != et
        ncost = (items.spell_cost(db, ench['effects'], constant=(int(ench['type']) == 3)) if redo else cost) if auto \
            else int(ench['cost'] or 0)
        new = (int(ench['type']), ncost, int(ench['charge'] or 0), (fl & ~1) | (1 if auto else 0))
        if new != (et, cost, charge, fl):
            subs = _set_sub(subs, 'ENDT', struct.pack('<iiii', *new) + old[16:], after=('NAME',))
    # ---- an item's enchantment
    if tag in CAN_ENCHANT and 'enchant' in o:
        want, have = o.get('enchant'), cur.get('enchant')
        if not want:
            if have or cur.get('enchant_missing'):
                subs = _set_sub(subs, 'ENAM', None, after=())
                notes.append('took the enchantment off')
        else:
            changed = not have or _effects_changed(have['effects'], want.get('effects') or []) or \
                any(str(want.get(k)) != str(have.get(k)) for k in ('type', 'charge', 'auto')) or \
                (not want.get('auto') and str(want.get('cost')) != str(have.get('cost')))
            if changed:
                shared = have and any(u['id'].lower() != r[1].lower() for u in have['used_by'])
                if not have or (shared and want.get('scope') == 'this'):
                    eid = _save_ench(db, _own_ench_id(db, r[1]), want, create=True)
                    subs = _set_sub(subs, 'ENAM', zs(eid), after=('NAME', 'MODL', 'FNAM', 'SCRI', 'ITEX', 'WPDT', 'AODT', 'CTDT', 'BKDT'))
                    notes.append('gave it its own enchantment ' + eid)
                else:
                    _save_ench(db, have['id'], want, create=False)
                    if shared:
                        notes.append('changed the enchantment for every item that shares it')
    new_data = join_subs(subs)
    if new_data != _data(db, ri)[0]:
        db.project.set_record(tag, key, flags & ~0x20, new_data, created=cur['created'])
    db.sync_project()
    commit(db, 'Edited %s "%s"%s' % ({'SPEL': 'spell', 'ENCH': 'enchantment'}.get(tag, 'item'), cur['name'] or r[1],
                                     (' (' + '; '.join(notes) + ')') if notes else ''))
    out = read(db, r[1])
    out['notes'] = notes
    return out
