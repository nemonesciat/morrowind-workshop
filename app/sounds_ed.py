"""Sounds and creature sounds.

SOUN  NAME id, FNAM the file under Sound\\, DATA volume (0-255), min range, max range (one byte each).
SNDG  NAME id, DATA the moment (0 left foot, 1 right foot, 2 swim left, 3 swim right, 4 moan,
      5 roar, 6 scream, 7 land), CNAM the creature (none: every creature without one of its own),
      SNAM the sound."""
import re
import struct

import editing
from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

MOMENTS = ['Left footstep', 'Right footstep', 'Swimming (left)', 'Swimming (right)', 'Moan', 'Roar', 'Scream', 'Landing']
SOUND_EXT = ('.wav', '.mp3', '.ogg', '.flac')


def _find(db, tag, rid):
    lst = [v for v in db.by_key.get((tag, (rid or '').lower()), []) if v not in db.dead]
    return lst[-1] if lst else None


def _subs(db, ri):
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    return [(t, bytes(d)) for t, d in iter_subrecords(data)], flags


def _row(db, ri):
    r = db.recs[ri]
    o = {'id': r[1], 'i': ri, 'file': '', 'volume': 255, 'min': 0, 'max': 0, 'src': db.plugins[r[3]]['name'],
         'mine': bool(db.project and ('SOUN|' + r[7]) in db.project.records),
         'created': bool(db.project and db.project.records.get('SOUN|' + r[7], {}).get('created'))}
    for t, d in _subs(db, ri)[0]:
        if t == 'FNAM':
            o['file'] = zstr(d)
        elif t == 'DATA' and len(d) >= 3:
            o['volume'], o['min'], o['max'] = d[0], d[1], d[2]
    o['exists'] = bool(o['file']) and file_exists(db, o['file'])
    return o


def file_exists(db, name):
    return ('sound/' + name.replace('\\', '/').lower()) in db.assets


def all_sounds(db):
    out = []
    for (tag, _k), lst in db.by_key.items():
        if tag != 'SOUN':
            continue
        live = [v for v in lst if v not in db.dead]
        if live:
            out.append(_row(db, live[-1]))
    out.sort(key=lambda s: s['id'].lower())
    return out


def read(db, rid):
    ri = _find(db, 'SOUN', rid)
    if ri is None:
        raise EditError('There is no sound called "%s".' % rid)
    o = _row(db, ri)
    o['used_by'] = used_by(db, o['id'])
    return o


def used_by(db, sid, limit=40):
    """Regions, doors, lights, creature sounds and magic effects that play this sound, and scripts that name it."""
    low = sid.lower()
    raw = low.encode(ENC, 'replace')
    pat = re.compile(rb'(?<![\w])' + re.escape(raw) + rb'(?![\w])')
    out = []
    for k, lst in db.by_key.items():
        if k[0] not in ('REGN', 'DOOR', 'LIGH', 'SNDG', 'MGEF', 'SCPT', 'ACTI', 'CONT', 'WEAP', 'ARMO', 'MISC', 'INFO') or not lst or lst[-1] in db.dead:
            continue
        ri = lst[-1]
        r = db.recs[ri]
        data = db.files[r[3]].record_at(r[4])[2]
        hit = False
        if k[0] in ('SCPT', 'INFO'):
            hit = bool(pat.search(bytes(data).lower()))
        else:
            for t, d in iter_subrecords(data):
                if t in ('SNAM', 'ANAM', 'BSND', 'CSND', 'HSND', 'ASND') and zstr(d[:32]).lower() == low:
                    hit = True
                    break
        if hit:
            label = r[2] or r[1]
            if k[0] == 'SNDG':
                cre = next((zstr(d) for t, d in iter_subrecords(data) if t == 'CNAM'), '')
                label = '%s: %s' % (cre or 'every creature', MOMENTS[_sndg_type(data)] if 0 <= _sndg_type(data) < 8 else '?')
            elif k[0] == 'INFO':
                d = db.info_dial.get(ri)
                label = 'a line in "%s"' % (db.recs[d][1] if d is not None else '?')
            out.append({'tag': k[0], 'i': ri, 'id': r[1], 'label': label})
            if len(out) >= limit:
                break
    return out


def files(db, q='', limit=80):
    """Sound files in the game's folders and archives (and the Library's) that match the words."""
    words = [w for w in (q or '').lower().replace('\\', '/').split() if w]
    out = []
    for a in db.assets:
        if not a.startswith('sound/') or not a.endswith(SOUND_EXT):
            continue
        if all(w in a for w in words):
            out.append(a[6:])
    out.sort()
    return {'files': out[:limit], 'total': len(out)}


def save(db, rid, o, create=False):
    _require_project(db)
    rid = (rid or '').strip()
    if not rid or len(rid.encode(ENC, 'replace')) > 31:
        raise EditError('Give the sound an ID of at most 31 characters, e.g. "MyMod_Waterfall".')
    ri = _find(db, 'SOUN', rid)
    if create and (ri is not None or db.resolve_id(rid) is not None):
        raise EditError('Something called "%s" already exists.' % rid)
    if not create and ri is None:
        raise EditError('There is no sound called "%s".' % rid)
    if ri is not None:
        rid = db.recs[ri][1]
    f = (o.get('file') or '').strip().replace('/', '\\')
    if f.lower().startswith('sound\\'):
        f = f[6:]
    if not f:
        raise EditError('Pick the sound file it plays.')
    if len(f.encode(ENC, 'replace')) > 31:
        raise EditError('The game keeps sound file names to 31 characters (counting the folders under Sound\\): "%s" is too long. Rename the file, or put it in a shorter folder.' % f)
    vol = _n(o.get('volume', 255), 0, 255, 'Volume')
    lo = _n(o.get('min', 0), 0, 255, 'The near distance')
    hi = _n(o.get('max', 0), 0, 255, 'The far distance')
    if hi and lo > hi:
        raise EditError('The near distance can\'t be further than the far one.')
    old, flags = _subs(db, ri) if ri is not None else ([], 0)
    subs = [('NAME', zs(rid)), ('FNAM', zs(f)), ('DATA', bytes([vol, lo, hi]))]
    subs += [(t, d) for t, d in old if t not in ('NAME', 'FNAM', 'DATA')]
    key = rid.lower()
    was = bool(db.project.records.get('SOUN|' + key, {}).get('created'))
    db.project.set_record('SOUN', key, flags & ~0x20, join_subs(subs), created=create or was)
    db.sync_project()
    commit(db, '%s sound "%s" (%s)' % ('Created' if create else 'Changed', rid, f))
    out = read(db, rid)
    if not out['exists']:
        out['note'] = 'No file called Sound\\%s is installed, so the game will play nothing. Drop it into your Library, or pick another.' % f
    return out


def _n(v, lo, hi, what):
    try:
        return max(lo, min(hi, int(round(float(v if v not in (None, '') else 0)))))
    except (TypeError, ValueError):
        raise EditError('%s must be a number.' % what)


# ------------------------------------------------------------------ creature sounds
def _sndg_type(data):
    for t, d in iter_subrecords(data):
        if t == 'DATA' and len(d) >= 4:
            return struct.unpack_from('<i', d)[0]
    return -1


def _sndg_all(db):
    """(creature id lower or '', moment) -> (record index, SNDG id, sound id)."""
    out = {}
    for (tag, _k), lst in db.by_key.items():
        if tag != 'SNDG':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        ri = live[-1]
        r = db.recs[ri]
        data = db.files[r[3]].record_at(r[4])[2]
        cre, snd, typ = '', '', -1
        for t, d in iter_subrecords(data):
            if t == 'CNAM':
                cre = zstr(d).lower()
            elif t == 'SNAM':
                snd = zstr(d)
            elif t == 'DATA' and len(d) >= 4:
                typ = struct.unpack_from('<i', d)[0]
        if 0 <= typ < 8:
            out[(cre, typ)] = (ri, r[1], snd)
    return out


def creature_sounds(db, cid):
    """The sound a creature makes at each moment: its own, or the default every creature shares."""
    ci = db.resolve_id(cid) if cid else None
    if cid and (ci is None or db.recs[ci][0] != 'CREA'):
        raise EditError('There is no creature called "%s".' % cid)
    cre = db.recs[ci][1] if ci is not None else ''
    allg = _sndg_all(db)
    rows = []
    for n, label in enumerate(MOMENTS):
        own = allg.get((cre.lower(), n))
        dflt = allg.get(('', n))
        rows.append({'moment': n, 'label': label, 'sound': own[2] if own else '', 'default': dflt[2] if dflt else '',
                     'mine': bool(own and db.project and ('SNDG|' + db.recs[own[0]][7]) in db.project.records)})
    return {'creature': cre, 'name': db.recs[ci][2] if ci is not None else 'Every creature', 'rows': rows}


def creatures_with_sounds(db):
    """Creatures that have sounds of their own, for the list."""
    seen = {}
    for (cre, _n), (ri, _id, _snd) in _sndg_all(db).items():
        if cre:
            seen[cre] = seen.get(cre, 0) + 1
    out = []
    for cre, n in seen.items():
        ci = db.resolve_id(cre)
        out.append({'id': db.recs[ci][1] if ci is not None else cre, 'name': db.recs[ci][2] if ci is not None else cre, 'n': n,
                    'missing': ci is None})
    out.sort(key=lambda x: x['name'].lower())
    return out


def save_creature_sounds(db, cid, rows):
    """rows: [{moment, sound}] — an empty sound takes that moment's entry out (back to the default)."""
    _require_project(db)
    ci = db.resolve_id(cid) if cid else None
    if cid and (ci is None or db.recs[ci][0] != 'CREA'):
        raise EditError('There is no creature called "%s".' % cid)
    cre = db.recs[ci][1] if ci is not None else ''
    allg = _sndg_all(db)
    p = db.project
    changed = []
    for row in rows or []:
        n = int(row.get('moment', -1))
        if not 0 <= n < 8:
            continue
        snd = (row.get('sound') or '').strip()
        have = allg.get((cre.lower(), n))
        if snd:
            si = db.resolve_id(snd)
            if si is None or db.recs[si][0] != 'SOUN':
                raise EditError('"%s" is not a sound.' % snd)
            snd = db.recs[si][1]
        if have and have[2].lower() == snd.lower():
            continue
        if not snd:
            if not have:
                continue
            key = db.recs[have[0]][7]
            if p.records.get('SNDG|' + key, {}).get('created'):
                p.remove_record('SNDG', key)
            else:
                # one of the game's: mark it deleted, so the default plays again
                _subs_, flags = _subs(db, have[0])
                p.set_record('SNDG', key, flags | 0x20, join_subs(_subs_))
            changed.append('%s: back to the usual' % MOMENTS[n].lower())
            continue
        if have:
            old, flags = _subs(db, have[0])
            subs = [(t, d) for t, d in old if t != 'SNAM'] + [('SNAM', zs(snd))]
            key = db.recs[have[0]][7]
            p.set_record('SNDG', key, flags & ~0x20, join_subs(subs),
                         created=bool(p.records.get('SNDG|' + key, {}).get('created')))
        else:
            base = re.sub(r'[^A-Za-z0-9]+', '_', (cre or 'all') + ' ' + MOMENTS[n].split()[0]).strip('_')[:28]
            sid, k = base, 2
            while db.resolve_id(sid) is not None or db.by_key.get(('SNDG', sid.lower())):
                sid = '%s%d' % (base[:28 - len(str(k))], k)
                k += 1
            subs = [('NAME', zs(sid)), ('DATA', struct.pack('<i', n))]
            if cre:
                subs.append(('CNAM', zs(cre)))
            subs.append(('SNAM', zs(snd)))
            p.set_record('SNDG', sid.lower(), 0, join_subs(subs), created=True)
        changed.append('%s: %s' % (MOMENTS[n].lower(), snd))
    if changed:
        db.sync_project()
        commit(db, 'Sounds of %s: %s' % (db.recs[ci][2] or cre if ci is not None else 'every creature', '; '.join(changed)))
    return creature_sounds(db, cre)
