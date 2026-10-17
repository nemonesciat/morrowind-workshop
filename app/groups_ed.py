"""Factions, classes, races and birthsigns: read into plain fields and write back.

FACT  FNAM name, RNAM x10 rank names, FADT (2 favoured attributes, 10 rank requirements, 7 skills, hidden),
      ANAM/INTV pairs: how the faction feels about another one.
CLAS  FNAM, CLDT (2 attributes, specialization, 5 minor/major skill pairs, playable, services), DESC.
RACE  FNAM, RADT (7 skill bonuses, attributes male/female, height and weight, flags), NPCS powers, DESC.
BSGN  FNAM, TNAM constellation picture, DESC, NPCS spells and abilities."""
import struct

import gmst_help

from database import ATTRIBUTES, SKILLS
from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

TAGS = {'faction': 'FACT', 'class': 'CLAS', 'race': 'RACE', 'birthsign': 'BSGN'}
SPECS = ['Combat', 'Magic', 'Stealth']


def _id32(s):
    return (s or '').encode(ENC, 'replace')[:31].ljust(32, b'\0')


def _find(db, tag, rid):
    lst = [v for v in db.by_key.get((tag, (rid or '').lower()), []) if v not in db.dead]
    return lst[-1] if lst else None


def _subs(db, ri):
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    return [(t, bytes(d)) for t, d in iter_subrecords(data)], flags


def _spell_rows(db, ids):
    out = []
    for s in ids:
        si = db.resolve_id(s)
        out.append({'id': s, 'name': db.recs[si][2] if si is not None else '', 'missing': si is None})
    return out


def read(db, kind, rid):
    tag = TAGS.get(kind)
    if not tag:
        raise EditError('Unknown kind.')
    ri = _find(db, tag, rid)
    if ri is None:
        raise EditError('There is no %s called "%s".' % (kind, rid))
    r = db.recs[ri]
    subs, _f = _subs(db, ri)
    o = {'kind': kind, 'id': r[1], 'i': ri, 'name': '', 'desc': '', 'src': db.plugins[r[3]]['name'],
         'mine': bool(db.project and (tag + '|' + r[7]) in db.project.records),
         'created': bool(db.project and db.project.records.get(tag + '|' + r[7], {}).get('created'))}
    if kind == 'faction':
        o.update({'ranks': [], 'attributes': [0, 1], 'skills': [], 'hidden': False, 'reactions': []})
        req = []
        cur = None
        for t, d in subs:
            if t == 'FNAM':
                o['name'] = zstr(d)
            elif t == 'RNAM':
                o['ranks'].append(zstr(d))
            elif t == 'FADT' and len(d) >= 240:
                v = struct.unpack_from('<2i50i7ii', d)
                o['attributes'] = list(v[0:2])
                req = [list(v[2 + n * 5: 7 + n * 5]) for n in range(10)]
                o['skills'] = [s for s in v[52:59] if s >= 0]
                o['hidden'] = bool(v[59])
            elif t == 'ANAM':
                cur = {'faction': zstr(d), 'value': 0}
                o['reactions'].append(cur)
            elif t == 'INTV' and cur is not None and len(d) >= 4:
                cur['value'] = struct.unpack_from('<i', d)[0]
                cur = None
        o['rank_req'] = [{'attr1': q[0], 'attr2': q[1], 'skill1': q[2], 'skill2': q[3], 'rep': q[4]} for q in req] or \
            [{'attr1': 0, 'attr2': 0, 'skill1': 0, 'skill2': 0, 'rep': 0} for _ in range(10)]
        o['members'] = _members(db, r[1])
    elif kind == 'class':
        o.update({'spec': 0, 'attributes': [0, 1], 'major': [], 'minor': [], 'playable': True, 'services': 0})
        for t, d in subs:
            if t == 'FNAM':
                o['name'] = zstr(d)
            elif t == 'DESC':
                o['desc'] = bytes(d).decode(ENC, 'replace').rstrip('\0')
            elif t == 'CLDT' and len(d) >= 60:
                v = struct.unpack_from('<15i', d)
                o['attributes'] = list(v[0:2])
                o['spec'] = v[2]
                o['minor'] = [v[3 + n * 2] for n in range(5)]
                o['major'] = [v[4 + n * 2] for n in range(5)]
                o['playable'] = bool(v[13])
                o['services'] = v[14]
    elif kind == 'race':
        o.update({'bonuses': [], 'male': [40] * 8, 'female': [40] * 8, 'height': [1.0, 1.0], 'weight': [1.0, 1.0],
                  'playable': True, 'beast': False, 'spells': []})
        for t, d in subs:
            if t == 'FNAM':
                o['name'] = zstr(d)
            elif t == 'DESC':
                o['desc'] = bytes(d).decode(ENC, 'replace').rstrip('\0')
            elif t == 'RADT' and len(d) >= 140:
                v = struct.unpack_from('<14i16i4fi', d)
                o['bonuses'] = [{'skill': v[n * 2], 'bonus': v[n * 2 + 1]} for n in range(7) if v[n * 2] >= 0]
                o['male'] = [v[14 + n * 2] for n in range(8)]
                o['female'] = [v[15 + n * 2] for n in range(8)]
                o['height'] = [round(v[30], 3), round(v[31], 3)]
                o['weight'] = [round(v[32], 3), round(v[33], 3)]
                o['playable'] = bool(v[34] & 1)
                o['beast'] = bool(v[34] & 2)
            elif t == 'NPCS':
                o['spells'].append(zstr(d))
        o['spells'] = _spell_rows(db, o['spells'])
    elif kind == 'birthsign':
        o.update({'picture': '', 'spells': []})
        for t, d in subs:
            if t == 'FNAM':
                o['name'] = zstr(d)
            elif t == 'DESC':
                o['desc'] = bytes(d).decode(ENC, 'replace').rstrip('\0')
            elif t == 'TNAM':
                o['picture'] = zstr(d)
            elif t == 'NPCS':
                o['spells'].append(zstr(d))
        o['spells'] = _spell_rows(db, o['spells'])
    return o


def _members(db, fid):
    """NPCs in this faction (by their own record), at most 60."""
    low = fid.lower().encode(ENC, 'replace')
    out = []
    for k, lst in db.by_key.items():
        if k[0] != 'NPC_' or not lst or lst[-1] in db.dead:
            continue
        r = db.recs[lst[-1]]
        data = db.files[r[3]].record_at(r[4])[2]
        p = data.find(b'ANAM')
        if p < 0:
            continue
        size = struct.unpack_from('<I', data, p + 4)[0]
        if bytes(data[p + 8:p + 8 + size]).rstrip(b'\0').lower() == low:
            out.append({'id': r[1], 'name': r[2]})
            if len(out) >= 60:
                break
    return out


def _n(v, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def save(db, kind, rid, o, create=False):
    _require_project(db)
    tag = TAGS.get(kind)
    if not tag:
        raise EditError('Unknown kind.')
    rid = (rid or '').strip()
    if not rid:
        raise EditError('Give it an ID.')
    if len(rid.encode(ENC, 'replace')) > 31:
        raise EditError('IDs can be at most 31 characters.')
    ri = _find(db, tag, rid)
    if create and ri is not None:
        raise EditError('A %s called "%s" already exists.' % (kind, rid))
    if not create and ri is None:
        raise EditError('There is no %s called "%s".' % (kind, rid))
    old, flags = (_subs(db, ri) if ri is not None else ([], 0))
    if ri is not None:
        rid = db.recs[ri][1]
    name = (o.get('name') or '').strip()
    if not name:
        raise EditError('Give it a name.')
    new = {}
    if kind == 'faction':
        ranks = [(x or '').strip() for x in (o.get('ranks') or [])][:10]
        ranks = [x for x in ranks if x]
        if not ranks:
            raise EditError('A faction needs at least one rank.')
        req = (o.get('rank_req') or [])[:10]
        req += [{}] * (10 - len(req))
        skills = [_n(s, 0, 26) for s in (o.get('skills') or [])][:7]
        skills += [-1] * (7 - len(skills))
        at = [_n(a, 0, 7) for a in (o.get('attributes') or [0, 1])][:2]
        vals = at + [x for q in req for x in (_n(q.get('attr1'), 0, 1000), _n(q.get('attr2'), 0, 1000),
                                               _n(q.get('skill1'), 0, 1000), _n(q.get('skill2'), 0, 1000),
                                               _n(q.get('rep'), -1000, 100000))] + skills + [1 if o.get('hidden') else 0]
        new['FNAM'] = [zs(name)]
        new['RNAM'] = [_id32(x) for x in ranks]
        new['FADT'] = [struct.pack('<2i50i7ii', *vals)]
        reac = []
        for rc in o.get('reactions') or []:
            f = (rc.get('faction') or '').strip()
            if not f:
                continue
            fi = _find(db, 'FACT', f)
            if fi is None and f.lower() != rid.lower():
                raise EditError('There is no faction called "%s".' % f)
            reac.append((db.recs[fi][1] if fi is not None else rid, _n(rc.get('value'), -10000, 10000)))
        order = ['NAME', 'FNAM', 'RNAM', 'FADT']
        out = _merge(old, rid, new, order, drop={'ANAM', 'INTV'})
        # some factions store these names without the closing zero byte; keep each record's own style
        olds = [d for t, d in old if t == 'ANAM']
        bare = bool(olds) and not any(d.endswith(b'\0') for d in olds)
        for f, v in reac:
            out += [('ANAM', f.encode(ENC, 'replace') if bare else zs(f)), ('INTV', struct.pack('<i', v))]
    elif kind == 'class':
        major = [_n(s, 0, 26) for s in (o.get('major') or [])][:5]
        minor = [_n(s, 0, 26) for s in (o.get('minor') or [])][:5]
        if len(major) != 5 or len(minor) != 5 or len(set(major + minor)) != 10:
            raise EditError('A class needs 5 major and 5 minor skills, all different.')
        at = [_n(a, 0, 7) for a in (o.get('attributes') or [0, 1])][:2]
        if len(at) != 2 or at[0] == at[1]:
            raise EditError('Pick two different favoured attributes.')
        pairs = [v for n in range(5) for v in (minor[n], major[n])]
        new['FNAM'] = [zs(name)]
        new['CLDT'] = [struct.pack('<15i', at[0], at[1], _n(o.get('spec'), 0, 2), *pairs, 1 if o.get('playable') else 0,
                                   _n(o.get('services'), 0, 2 ** 31 - 1))]
        new['DESC'] = [(o.get('desc') or '').encode(ENC, 'replace')] if (o.get('desc') or '').strip() else []
        out = _merge(old, rid, new, ['NAME', 'FNAM', 'CLDT', 'DESC'])
    elif kind == 'race':
        bon = []
        for b in (o.get('bonuses') or [])[:7]:
            if b.get('skill') is None or b.get('skill') == '':
                continue
            bon += [_n(b.get('skill'), 0, 26), _n(b.get('bonus'), -100, 100)]
        bon += [-1, 0] * (7 - len(bon) // 2)
        male = [_n(v, 0, 1000) for v in (o.get('male') or [])][:8]
        female = [_n(v, 0, 1000) for v in (o.get('female') or [])][:8]
        if len(male) != 8 or len(female) != 8:
            raise EditError('A race needs all 8 attributes for men and women.')
        att = [v for n in range(8) for v in (male[n], female[n])]
        hw = [max(0.5, min(2.0, float(x))) for x in list(o.get('height') or [1, 1])[:2] + list(o.get('weight') or [1, 1])[:2]]
        fl = (1 if o.get('playable') else 0) | (2 if o.get('beast') else 0)
        new['FNAM'] = [zs(name)]
        new['RADT'] = [struct.pack('<14i16i4fi', *bon, *att, *hw, fl)]
        new['NPCS'] = [_id32(_spell(db, s)) for s in (o.get('spells') or []) if _spell(db, s)]
        new['DESC'] = [(o.get('desc') or '').encode(ENC, 'replace')] if (o.get('desc') or '').strip() else []
        out = _merge(old, rid, new, ['NAME', 'FNAM', 'RADT', 'NPCS', 'DESC'])
    else:
        new['FNAM'] = [zs(name)]
        pic = (o.get('picture') or '').strip()
        new['TNAM'] = [zs(pic)] if pic else []
        new['DESC'] = [zs((o.get('desc') or '').strip())] if (o.get('desc') or '').strip() else []
        new['NPCS'] = [_id32(_spell(db, s)) for s in (o.get('spells') or []) if _spell(db, s)]
        out = _merge(old, rid, new, ['NAME', 'FNAM', 'TNAM', 'DESC', 'NPCS'])
    key = rid.lower()
    was_created = bool(db.project.records.get(tag + '|' + key, {}).get('created'))
    db.project.set_record(tag, key, flags & ~0x20, join_subs(out), created=create or was_created)
    commit(db, '%s %s "%s"' % ('Created' if create else 'Edited', kind, name))
    return read(db, kind, rid)


def _spell(db, s):
    sid = ((s.get('id') if isinstance(s, dict) else s) or '').strip()
    if not sid:
        return ''
    si = db.resolve_id(sid)
    if si is None or db.recs[si][0] != 'SPEL':
        raise EditError('There is no spell or ability called "%s".' % sid)
    return db.recs[si][1]


def _merge(old, rid, new, order, drop=()):
    """NAME first, then the fields in order (replacing old ones), then anything else the record had."""
    out = [('NAME', zs(rid))]
    for t in order[1:]:
        for d in new.get(t, []):
            out.append((t, d))
    known = set(order) | set(drop)
    out += [(t, d) for t, d in old if t not in known]
    return out


# ------------------------------------------------------------------ global variables and game settings
GLOB_TYPES = {'s': 'Whole number (short)', 'l': 'Whole number (long)', 'f': 'Decimal number (float)'}


def read_global(db, gid):
    ri = _find(db, 'GLOB', gid)
    if ri is None:
        raise EditError('There is no global variable called "%s".' % gid)
    r = db.recs[ri]
    subs, _f = _subs(db, ri)
    o = {'id': r[1], 'i': ri, 'type': 'f', 'value': 0.0, 'src': db.plugins[r[3]]['name'],
         'mine': bool(db.project and ('GLOB|' + r[7]) in db.project.records)}
    for t, d in subs:
        if t == 'FNAM' and d:
            o['type'] = chr(d[0]).lower()
        elif t == 'FLTV' and len(d) >= 4:
            o['value'] = struct.unpack_from('<f', d)[0]
    if o['type'] in ('s', 'l'):
        o['value'] = int(round(o['value']))
    o['used_by'] = _glob_users(db, r[1])
    return o


def _glob_users(db, gid):
    """Scripts and dialogue that mention the global (by name)."""
    import re
    pat = re.compile(rb'(?<![\w])' + re.escape(gid.lower().encode(ENC, 'replace')) + rb'(?![\w])')
    out = []
    for k, lst in db.by_key.items():
        if k[0] not in ('SCPT', 'INFO') or not lst or lst[-1] in db.dead:
            continue
        r = db.recs[lst[-1]]
        if pat.search(bytes(db.files[r[3]].record_at(r[4])[2]).lower()):
            if k[0] == 'SCPT':
                out.append({'kind': 'script', 'id': r[1]})
            else:
                d = db.info_dial.get(lst[-1])
                out.append({'kind': 'dialogue', 'id': db.recs[d][1] if d is not None else '?', 'i': lst[-1]})
            if len(out) >= 40:
                break
    return out


def save_global(db, gid, o, create=False):
    _require_project(db)
    gid = (gid or '').strip()
    if not gid or len(gid.encode(ENC, 'replace')) > 31:
        raise EditError('Give the variable an ID of at most 31 characters, e.g. "MyMod_GateOpen".')
    ri = _find(db, 'GLOB', gid)
    if create and (ri is not None or db.resolve_id(gid) is not None):
        raise EditError('Something called "%s" already exists.' % gid)
    if not create and ri is None:
        raise EditError('There is no global variable called "%s".' % gid)
    if ri is not None:
        gid = db.recs[ri][1]
    typ = (o.get('type') or 'f')[0].lower()
    if typ not in GLOB_TYPES:
        raise EditError('Unknown kind of number.')
    try:
        val = float(o.get('value') or 0)
    except ValueError:
        raise EditError('The value must be a number.')
    if typ in ('s', 'l'):
        val = float(int(round(val)))
        if typ == 's' and not -32768 <= val <= 32767:
            raise EditError('A short holds -32768 to 32767; use long for bigger numbers.')
    key = gid.lower()
    was = bool(db.project.records.get('GLOB|' + key, {}).get('created'))
    flags = db.recs[ri][6] & ~0x20 if ri is not None else 0
    db.project.set_record('GLOB', key, flags, join_subs([('NAME', zs(gid)), ('FNAM', typ.encode()), ('FLTV', struct.pack('<f', val))]),
                          created=create or was)
    commit(db, '%s global "%s" = %s' % ('Created' if create else 'Set', gid, ('%g' % val)))
    return read_global(db, gid)


def gmst_list(db, q='', limit=200, offset=0):
    """Game settings, a page at a time (limit 0: all of them)."""
    q = (q or '').lower().strip()
    out = []
    for k, lst in db.by_key.items():
        if k[0] != 'GMST':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        help_, sure = gmst_help.explain(k[1])
        if q and q not in k[1] and q not in help_.lower():
            continue
        # the ones people change most first, then the other numbers, then the game's words
        out.append((0 if sure else 2 if k[1].startswith('s') else 1, k[1], live[-1]))
    out.sort()
    offset = max(0, min(offset, len(out)))
    page = out[offset:offset + limit] if limit else out[offset:]
    rows = [_gmst_row(db, v) for _p, key, v in page]
    return {'rows': rows, 'total': len(out), 'offset': offset}


def _gmst_row(db, v, help_=None):
    r = db.recs[v]
    val, typ = None, r[1][:1].lower()
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'STRV':
            val, typ = bytes(d).decode(ENC, 'replace').rstrip('\0'), 's'
        elif t == 'INTV' and len(d) >= 4:
            val, typ = struct.unpack_from('<i', d)[0], 'i'
        elif t == 'FLTV' and len(d) >= 4:
            val, typ = round(struct.unpack_from('<f', d)[0], 5), 'f'
    if val is None:
        val = '' if typ == 's' else 0
    base = [x for x in db.by_key.get(('GMST', r[7]), []) if x not in db.dead and db.recs[x][3] != db.proj_pidx]
    text, sure = gmst_help.explain(r[7])
    return {'id': r[1], 'value': val, 'type': typ, 'help': text if help_ is None else help_, 'sure': sure,
            'src': db.plugins[r[3]]['name'], 'mine': bool(db.project and ('GMST|' + r[7]) in db.project.records),
            'original': _gmst_row(db, base[-1], '')['value'] if base and base[-1] != v else None}


def save_gmst(db, gid, value):
    _require_project(db)
    ri = _find(db, 'GMST', gid)
    if ri is None:
        raise EditError('There is no game setting called "%s".' % gid)
    r = db.recs[ri]
    row = _gmst_row(db, ri, '')
    typ = row['type']
    if typ == 's':
        data = ('STRV', (str(value)).encode(ENC, 'replace'))
    elif typ == 'i':
        try:
            data = ('INTV', struct.pack('<i', int(round(float(value)))))
        except ValueError:
            raise EditError('This setting takes a whole number.')
    else:
        try:
            data = ('FLTV', struct.pack('<f', float(value)))
        except ValueError:
            raise EditError('This setting takes a number.')
    db.project.set_record('GMST', r[7], r[6] & ~0x20, join_subs([('NAME', zs(r[1])), data]))
    commit(db, 'Changed game setting %s to %s' % (r[1], value))
    return _gmst_row(db, _find(db, 'GMST', gid))


def options(db):
    def lst(tag):
        out = []
        for k, v in db.by_key.items():
            if k[0] == tag:
                live = [x for x in v if x not in db.dead]
                if live:
                    r = db.recs[live[-1]]
                    out.append({'id': r[1], 'name': r[2] or r[1]})
        return sorted(out, key=lambda x: x['name'].lower())
    return {'skills': SKILLS, 'attributes': ATTRIBUTES, 'specs': SPECS,
            'factions': lst('FACT'), 'classes': lst('CLAS'), 'races': lst('RACE'), 'birthsigns': lst('BSGN')}
