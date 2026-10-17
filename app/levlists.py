"""Leveled lists: random loot (LEVI) and random creature spawns (LEVC).

A list holds entries, each with the player level it unlocks at. When the game needs one thing from the
list it first rolls "chance none" (nothing at all), then picks at random among the entries the player's
level allows: only the highest-level ones, unless "use all levels" is ticked. Lists can hold other lists."""
import struct

from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

# loot lists: 1 = roll each one separately, 2 = all levels; creature lists: 1 = all levels
def _bits(tag):
    return (0x2, 0x1) if tag == 'LEVI' else (0x1, 0)


def _find(db, lid):
    for tag in ('LEVI', 'LEVC'):
        lst = [v for v in db.by_key.get((tag, (lid or '').lower()), []) if v not in db.dead]
        if lst:
            return lst[-1]
    return None


def read(db, lid):
    ri = _find(db, lid)
    if ri is None:
        raise EditError('There is no leveled list called "%s".' % lid)
    r = db.recs[ri]
    tag = r[0]
    o = {'id': r[1], 'i': ri, 'kind': 'items' if tag == 'LEVI' else 'creatures', 'chance_none': 0,
         'all_levels': False, 'each': False, 'entries': [], 'src': db.plugins[r[3]]['name'],
         'mine': bool(db.project and (tag + '|' + r[7]) in db.project.records),
         'created': bool(db.project and db.project.records.get(tag + '|' + r[7], {}).get('created'))}
    cur = None
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'DATA' and len(d) >= 4:
            f = struct.unpack_from('<i', d)[0]
            b_all, b_each = _bits(tag)
            o['all_levels'] = bool(f & b_all)
            o['each'] = bool(f & b_each)
        elif t == 'NNAM' and len(d) >= 1:
            o['chance_none'] = d[0]
        elif t in ('INAM', 'CNAM'):
            cur = {'id': zstr(d), 'level': 1}
            o['entries'].append(cur)
        elif t == 'INTV' and cur is not None and len(d) >= 2:
            cur['level'] = struct.unpack_from('<h', d)[0]
            cur = None
    for e in o['entries']:
        ei = db.resolve_id(e['id'])
        e['name'] = db.recs[ei][2] if ei is not None else ''
        e['type'] = db.recs[ei][0] if ei is not None else ''
        e['missing'] = ei is None
    o['used_by'] = used_by(db, r[1])
    return o


def used_by(db, lid):
    out = []
    for ri in sorted(db.used_in.get(lid.lower(), ()))[:60]:
        r = db.recs[ri]
        if r is None or ri in db.dead:
            continue
        if r[0] == 'CELL':
            out.append({'kind': 'place', 'key': r[7], 'label': r[1] if r[7].startswith('#') else (r[2] or r[1])})
        else:
            out.append({'kind': r[0], 'i': ri, 'id': r[1], 'label': r[2] or r[1]})
    return out


def save(db, lid, o, create=False):
    _require_project(db)
    lid = (lid or '').strip()
    if not lid:
        raise EditError('Give the list an ID, e.g. "mymod_lev_bandit_loot".')
    if len(lid.encode(ENC, 'replace')) > 31:
        raise EditError('IDs can be at most 31 characters.')
    ri = _find(db, lid)
    if create:
        if ri is not None or db.resolve_id(lid) is not None:
            raise EditError('Something with the ID "%s" already exists.' % lid)
        tag = 'LEVI' if o.get('kind') != 'creatures' else 'LEVC'
        key, flags, created = lid.lower(), 0, True
    else:
        if ri is None:
            raise EditError('There is no leveled list called "%s".' % lid)
        r = db.recs[ri]
        tag, key, flags = r[0], r[7], r[6] & ~0x20
        lid = r[1]
        created = bool(db.project.records.get(tag + '|' + key, {}).get('created'))
    want = ('CREA', 'LEVC', 'NPC_') if tag == 'LEVC' else None
    entries = []
    for e in o.get('entries') or []:
        eid = (e.get('id') or '').strip()
        if not eid:
            continue
        ei = db.resolve_id(eid)
        if ei is None:
            raise EditError('There is nothing called "%s".' % eid)
        if want and db.recs[ei][0] not in want:
            raise EditError('"%s" is not a creature or creature list.' % eid)
        if not want and db.recs[ei][0] in ('CREA', 'NPC_', 'LEVC'):
            raise EditError('"%s" is a creature; put it in a creature list instead.' % eid)
        if db.recs[ei][1].lower() == lid.lower():
            raise EditError('A list can\'t contain itself.')
        lv = max(1, min(1000, int(e.get('level') or 1)))
        entries.append((lv, db.recs[ei][1]))
    b_all, b_each = _bits(tag)
    f = (b_all if o.get('all_levels') else 0) | (b_each if o.get('each') else 0)
    subs = [('NAME', zs(lid)), ('DATA', struct.pack('<i', f)),
            ('NNAM', bytes([max(0, min(100, int(o.get('chance_none') or 0)))])),
            ('INDX', struct.pack('<i', len(entries)))]
    et = 'INAM' if tag == 'LEVI' else 'CNAM'
    for lv, eid in entries:
        subs += [(et, zs(eid)), ('INTV', struct.pack('<h', lv))]
    db.project.set_record(tag, key, flags, join_subs(subs), created=created)
    commit(db, ('Created %s list "%s"' if create else 'Edited %s list "%s"') % ('loot' if tag == 'LEVI' else 'creature', lid))
    return read(db, lid)
