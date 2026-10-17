"""The character editor: everything about an NPC in one place, in plain terms.

Reads an NPC record into a simple structure (who they are, stats, behaviour, services,
travel, what they carry and know) and writes it back, keeping anything it doesn't know about."""
import math
import struct

import editing
from database import ATTRIBUTES, SKILLS
from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

FLAG_FEMALE, FLAG_ESSENTIAL, FLAG_RESPAWN, FLAG_BASE, FLAG_AUTO = 0x1, 0x2, 0x4, 0x8, 0x10
BLOOD = [('Red', 0), ('Skeleton (white dust)', 0x400), ('Metal (golden sparks)', 0x800)]
SERVICE_BITS = [
    ('Weapons', 0x1), ('Armor', 0x2), ('Clothing', 0x4), ('Books', 0x8), ('Ingredients', 0x10),
    ('Lockpicks', 0x20), ('Probes', 0x40), ('Lights', 0x80), ('Apparatus', 0x100), ('Repair items', 0x200),
    ('Miscellaneous', 0x400), ('Potions', 0x2000), ('Magic items', 0x1000),
    ('Sells spells', 0x800), ('Training', 0x4000), ('Spellmaking', 0x8000), ('Enchanting', 0x10000), ('Repairs', 0x20000)]
IDLE_NAMES = ['Look around', 'Look behind', 'Scratch head', 'Shift clothes', 'Rub hands', 'Look at hands',
              'Shift weight', 'Fidget']
# subrecords this editor writes itself (everything else is kept as it was)
OWN = {'FNAM', 'RNAM', 'CNAM', 'ANAM', 'BNAM', 'KNAM', 'SCRI', 'NPDT', 'FLAG', 'NPCO', 'NPCS', 'AIDT',
       'DODT', 'DNAM', 'AI_W', 'AI_T', 'AI_F', 'AI_E', 'AI_A', 'CNDT', 'XSCL'}


def _id32(s):
    return (s or '').encode(ENC, 'replace')[:31].ljust(32, b'\0')


def _data(db, i):
    r = db.recs[i]
    return db.files[r[3]].record_at(r[4])


def _find(db, npc_id):
    for tag in ('NPC_', 'CREA'):
        lst = [v for v in db.by_key.get((tag, (npc_id or '').lower()), []) if v not in db.dead]
        if lst:
            return lst[-1]
    raise EditError('There is no character or creature with the ID "%s".' % npc_id)


# creatures
CREA_TYPES = ['Creature', 'Daedra', 'Undead', 'Humanoid']
CF_BIPED, CF_RESPAWN, CF_WEAPON, CF_BASE, CF_SWIMS, CF_FLIES, CF_WALKS, CF_ESSENTIAL = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80
SOULS = [('None', 0), ('Petty', 30), ('Lesser', 60), ('Common', 120), ('Greater', 180), ('Grand', 600)]


def _crea_sub(t, d, o):
    if t == 'CNAM':
        o['sound'] = zstr(d)
    elif t == 'NPDT' and len(d) >= 96:
        v = struct.unpack_from('<24i', d)
        o['ctype'], o['level'] = v[0], v[1]
        o['attributes'] = list(v[2:10])
        o['health'], o['magicka'], o['fatigue'], o['soul'] = v[10:14]
        o['combat'], o['magic'], o['stealth'] = v[14:17]
        o['attacks'] = [[v[17], v[18]], [v[19], v[20]], [v[21], v[22]]]
        o['gold'] = v[23]
    elif t == 'FLAG' and len(d) >= 4:
        f = struct.unpack_from('<i', d)[0]
        o['flags'] = f
        for k, bit in (('biped', CF_BIPED), ('respawn', CF_RESPAWN), ('weapons', CF_WEAPON), ('swims', CF_SWIMS),
                       ('flies', CF_FLIES), ('walks', CF_WALKS), ('essential', CF_ESSENTIAL)):
            o[k] = bool(f & bit)
        o['blood'] = f & 0xC00


def read(db, npc_id):
    ri = _find(db, npc_id)
    r = db.recs[ri]
    tag = r[0]
    _t, _flags, data = _data(db, ri)
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    o = {'id': r[1], 'i': ri, 'kind': 'creature' if tag == 'CREA' else 'npc', 'name': '', 'race': '', 'cls': '', 'faction': '', 'head': '', 'hair': '', 'script': '',
         'model': '', 'level': 1, 'disposition': 50, 'reputation': 0, 'rank': 0, 'gold': 0,
         'attributes': None, 'skills': None, 'health': None, 'magicka': None, 'fatigue': None,
         'female': False, 'essential': False, 'respawn': False, 'auto': True, 'blood': 0, 'scale': 1.0,
         'hello': 30, 'fight': 30, 'flee': 30, 'alarm': 0, 'services': 0,
         'items': [], 'spells': [], 'travel': [], 'ai': [],
         'mine': db.project is not None and (tag + '|' + r[7]) in db.project.records,
         'created': bool(db.project and db.project.records.get(tag + '|' + r[7], {}).get('created')),
         'src': db.plugins[r[3]]['name']}
    if tag == 'CREA':
        o.update({'sound': '', 'ctype': 0, 'soul': 0, 'combat': 0, 'magic': 0, 'stealth': 0, 'attacks': [[0, 0]] * 3,
                  'attributes': [0] * 8, 'health': 0, 'magicka': 0, 'fatigue': 0, 'auto': False, 'flags': CF_BASE | CF_WALKS,
                  'biped': False, 'weapons': False, 'swims': False, 'flies': False, 'walks': True})
    flags = 0
    last_ai = None
    for t, d in subs:
        if tag == 'CREA' and t in ('CNAM', 'NPDT', 'FLAG'):
            _crea_sub(t, d, o)
            continue
        if t == 'FNAM':
            o['name'] = zstr(d)
        elif t == 'MODL':
            o['model'] = zstr(d)
        elif t in ('RNAM', 'CNAM', 'ANAM', 'BNAM', 'KNAM', 'SCRI'):
            o[{'RNAM': 'race', 'CNAM': 'cls', 'ANAM': 'faction', 'BNAM': 'head', 'KNAM': 'hair', 'SCRI': 'script'}[t]] = zstr(d)
        elif t == 'NPDT' and len(d) >= 52:
            v = struct.unpack_from('<h8B27Bx3HBBBxi', d)
            o['level'] = v[0]
            o['attributes'] = list(v[1:9])
            o['skills'] = list(v[9:36])
            o['health'], o['magicka'], o['fatigue'] = v[36:39]
            o['disposition'], o['reputation'], o['rank'], o['gold'] = v[39:43]
        elif t == 'NPDT' and len(d) >= 12:
            o['level'], o['disposition'], o['reputation'], o['rank'], o['gold'] = struct.unpack_from('<hBBBxxxi', d)
        elif t == 'FLAG' and len(d) >= 4:
            flags = struct.unpack_from('<i', d)[0]
        elif t == 'NPCO' and len(d) >= 36:
            n = struct.unpack_from('<i', d)[0]
            o['items'].append({'id': zstr(d[4:36]), 'count': abs(n), 'restock': n < 0})
        elif t == 'NPCS':
            o['spells'].append(zstr(d))
        elif t == 'AIDT' and len(d) >= 12:
            o['hello'], _u, o['fight'], o['flee'], o['alarm'] = struct.unpack_from('<BBBBB', d)
            o['services'] = struct.unpack_from('<i', d, 8)[0]
        elif t == 'DODT' and len(d) >= 24:
            x, y, z, rx, ry, rz = struct.unpack_from('<6f', d)
            o['travel'].append({'p': [x, y, z, rx, ry, rz], 'cell': ''})
        elif t == 'DNAM' and o['travel']:
            o['travel'][-1]['cell'] = zstr(d)
        elif t == 'AI_W' and len(d) >= 14:
            dist, dur, tod = struct.unpack_from('<hhB', d)
            o['ai'].append({'kind': 'wander', 'distance': dist, 'duration': dur, 'idle': list(d[5:13]),
                            'repeat': bool(d[13])})
            last_ai = None
        elif t == 'AI_T' and len(d) >= 13:
            x, y, z = struct.unpack_from('<3f', d)
            o['ai'].append({'kind': 'travel', 'p': [x, y, z], 'repeat': bool(d[12])})
            last_ai = None
        elif t in ('AI_F', 'AI_E') and len(d) >= 47:
            x, y, z, dur = struct.unpack_from('<3fh', d)
            last_ai = {'kind': 'follow' if t == 'AI_F' else 'escort', 'p': [x, y, z], 'duration': dur,
                       'target': zstr(d[14:46]), 'repeat': bool(d[46]), 'cell': ''}
            o['ai'].append(last_ai)
        elif t == 'CNDT' and last_ai is not None:
            last_ai['cell'] = zstr(d)
        elif t == 'AI_A' and len(d) >= 32:
            o['ai'].append({'kind': 'activate', 'target': zstr(d[:32]), 'repeat': bool(d[32]) if len(d) > 32 else False})
            last_ai = None
        elif t == 'XSCL' and len(d) >= 4:
            o['scale'] = round(struct.unpack_from('<f', d)[0], 3)
    _finish_lists(db, o)
    o['placed'] = placements(db, r[1])
    if tag == 'CREA':
        o['calc'] = None
        return o
    o['female'] = bool(flags & FLAG_FEMALE)
    o['essential'] = bool(flags & FLAG_ESSENTIAL)
    o['respawn'] = bool(flags & FLAG_RESPAWN)
    o['auto'] = bool(flags & FLAG_AUTO) or o['attributes'] is None
    o['blood'] = flags & 0xC00
    o['flags'] = flags
    # what the auto-calculated stats come out at, to show (and to start from when switching off)
    o['calc'] = autocalc(db, o['race'], o['cls'], o['level'], o['female'])
    return o


def _finish_lists(db, o):
    for n in o['items']:
        ii = db.resolve_id(n['id'])
        n['name'] = db.recs[ii][2] if ii is not None else ''
        n['type'] = db.recs[ii][0] if ii is not None else ''
        n['missing'] = ii is None
    o['spells'] = [{'id': s, 'name': (db.recs[db.resolve_id(s)][2] if db.resolve_id(s) is not None else ''),
                    'missing': db.resolve_id(s) is None} for s in o['spells']]


def placements(db, npc_id):
    """The places this character stands in (cells that have them placed)."""
    out, seen = [], set()
    for ci in sorted(db.used_in.get(npc_id.lower(), ())):
        r = db.recs[ci]
        # any version of the cell counts (outdoors, a later mod's copy of the cell often lists only its own changes)
        if r is None or r[0] != 'CELL' or ci in db.dead or r[7] in seen:
            continue
        seen.add(r[7])
        name = r[1] if r[7].startswith('#') else (r[2] or r[1])     # (outdoors the ID already ends in the grid spot)
        out.append({'key': r[7], 'name': name or r[7]})
    return out[:30]


# ----------------------------------------------------------------- auto-calculated stats
def _rec_subs(db, tag, rid):
    lst = [v for v in db.by_key.get((tag, (rid or '').lower()), []) if v not in db.dead]
    if not lst:
        return None
    return {t: bytes(d) for t, d in iter_subrecords(_data(db, lst[-1])[2])}


_skill_cache = None


def _skill_info(db):
    """skill index -> (governing attribute, specialization)."""
    global _skill_cache
    if _skill_cache is not None and _skill_cache[0] is db.recs:
        return _skill_cache[1]
    out = {}
    for k, lst in db.by_key.items():
        if k[0] != 'SKIL':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        s = {t: bytes(d) for t, d in iter_subrecords(_data(db, live[-1])[2])}
        if 'INDX' in s and 'SKDT' in s:
            out[struct.unpack_from('<i', s['INDX'])[0]] = struct.unpack_from('<ii', s['SKDT'])
    _skill_cache = (db.recs, out)
    return out


def autocalc(db, race, cls, level, female):
    """The stats the game gives an NPC whose stats are auto-calculated (same formulas as OpenMW)."""
    rs, cs = _rec_subs(db, 'RACE', race), _rec_subs(db, 'CLAS', cls)
    if not rs or not cs or 'RADT' not in rs or 'CLDT' not in cs:
        return None
    radt, cldt = rs['RADT'], cs['CLDT']
    bonus = {}
    for n in range(7):
        sk, b = struct.unpack_from('<ii', radt, n * 8)
        if sk >= 0:
            bonus[sk] = b
    attrs = [struct.unpack_from('<ii', radt, 56 + n * 8)[1 if female else 0] for n in range(8)]
    a1, a2, spec = struct.unpack_from('<iii', cldt)
    pairs = [struct.unpack_from('<ii', cldt, 12 + n * 8) for n in range(5)]
    minor, major = {p[0] for p in pairs}, {p[1] for p in pairs}
    for a in (a1, a2):
        if 0 <= a < 8:
            attrs[a] += 10
    info = _skill_info(db)
    lv = max(1, level)
    # attributes grow with the skills they govern
    for a in range(8):
        mod = 0.0
        for sk, (gov, _sp) in info.items():
            if gov == a:
                mod += 1.0 if sk in major else 0.5 if sk in minor else 0.2
        attrs[a] = min(100, int(round(attrs[a] + (lv - 1) * mod)))
    skills = []
    for sk in range(27):
        base = 25 if sk in major else 10 if sk in minor else 0
        mult = 1.0 if sk in major else 0.5 if sk in minor else 0.1
        sp_mult, sp_bonus = (0.5, 5) if info.get(sk, (0, -1))[1] == spec else (0.0, 0)
        skills.append(min(100, int(round(base + 5 + bonus.get(sk, 0) + sp_bonus + (lv - 1) * (mult + sp_mult)))))
    st, intel, wil, agi, end = attrs[0], attrs[1], attrs[2], attrs[3], attrs[5]
    mult = 3 + (2 if spec == 0 else 1 if spec == 2 else 0) + (1 if 5 in (a1, a2) else 0)
    health = int(math.floor(0.5 * (st + end))) + mult * (lv - 1)
    return {'attributes': attrs, 'skills': skills, 'health': health, 'magicka': intel, 'fatigue': st + wil + agi + end}


# ----------------------------------------------------------------- choices for the editor
_opt_cache = None


def options(db):
    global _opt_cache
    if _opt_cache is not None and _opt_cache[0] is db.recs and _opt_cache[1] == len(db.recs):
        return _opt_cache[2]
    import create
    base = create.options(db)
    heads = []
    for k, lst in db.by_key.items():
        if k[0] != 'BODY':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        s = {t: bytes(d) for t, d in iter_subrecords(_data(db, live[-1])[2])}
        by = s.get('BYDT', b'')
        if len(by) < 4 or by[0] not in (0, 1) or by[3] != 0:
            continue
        heads.append({'id': db.recs[live[-1]][1], 'part': 'head' if by[0] == 0 else 'hair', 'race': zstr(s.get('FNAM', b'')),
                      'female': bool(by[2] & 1), 'vampire': bool(by[1])})
    heads.sort(key=lambda h: h['id'].lower())
    # every travel destination used in the game, so a new caravaner can offer the same trips
    dests = {}
    for k, lst in db.by_key.items():
        if k[0] != 'NPC_':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        data = _data(db, live[-1])[2]
        if b'DODT' not in data:
            continue
        cur = None
        for t, d in iter_subrecords(data):
            if t == 'DODT' and len(d) >= 24:
                cur = list(struct.unpack_from('<6f', d))
                dests.setdefault(('', round(cur[0]), round(cur[1])), {'p': cur, 'cell': '', 'by': db.recs[live[-1]][2]})
            elif t == 'DNAM' and cur is not None:
                dests.pop(('', round(cur[0]), round(cur[1])), None)
                dests.setdefault((zstr(d), round(cur[0]), round(cur[1])), {'p': cur, 'cell': zstr(d), 'by': db.recs[live[-1]][2]})
                cur = None
    out = dict(base)
    out.update({'heads': heads, 'skills': SKILLS, 'attributes': ATTRIBUTES, 'services': SERVICE_BITS,
                'idles': IDLE_NAMES, 'blood': BLOOD, 'ctypes': CREA_TYPES, 'souls': SOULS, 'destinations': sorted(dests.values(), key=lambda d: (d['cell'] or '~', d['by'] or ''))})
    _opt_cache = (db.recs, len(db.recs), out)
    return out


# ----------------------------------------------------------------- saving
def _num(v, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def _check_ref(db, rid, tags, what):
    if not rid:
        return ''
    ri = db.resolve_id(rid)
    if ri is None or (tags and db.recs[ri][0] not in tags):
        raise EditError('There is no %s called "%s".' % (what, rid))
    return db.recs[ri][1]


def save(db, npc_id, o):
    _require_project(db)
    ri = _find(db, npc_id)
    r = db.recs[ri]
    _t, rflags, data = _data(db, ri)
    old = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    name = (o.get('name') or '').strip()
    if not name:
        raise EditError('Give the character a name.')
    if r[0] == 'CREA':
        new = _crea_head(db, o, name)
    else:
        new = _npc_head(db, o, name)
    return _save_rest(db, ri, r, rflags, old, new, o, name)


def _crea_head(db, o, name):
    sound = _check_ref(db, (o.get('sound') or '').strip(), ('CREA',), 'creature (for sounds)')
    script = _check_ref(db, (o.get('script') or '').strip(), ('SCPT',), 'script')
    at = [_num(v, 0, 10000) for v in (o.get('attributes') or [0] * 8)][:8]
    at += [0] * (8 - len(at))
    atk = [[_num(a, 0, 10000) for a in pair][:2] for pair in (o.get('attacks') or [[0, 0]] * 3)][:3]
    atk += [[0, 0]] * (3 - len(atk))
    npdt = struct.pack('<24i', _num(o.get('ctype'), 0, 3), _num(o.get('level'), 0, 32767, 1), *at,
                       _num(o.get('health'), 0, 2 ** 31 - 1), _num(o.get('magicka'), 0, 2 ** 31 - 1),
                       _num(o.get('fatigue'), 0, 2 ** 31 - 1), _num(o.get('soul'), 0, 2 ** 31 - 1),
                       _num(o.get('combat'), 0, 255), _num(o.get('magic'), 0, 255), _num(o.get('stealth'), 0, 255),
                       *[v for pair in atk for v in pair], _num(o.get('gold'), 0, 2 ** 31 - 1))
    f = int(o.get('flags') or 0) & ~(0xFF | 0xC00)
    for k, bit in (('biped', CF_BIPED), ('respawn', CF_RESPAWN), ('weapons', CF_WEAPON), ('swims', CF_SWIMS),
                   ('flies', CF_FLIES), ('walks', CF_WALKS), ('essential', CF_ESSENTIAL)):
        if o.get(k):
            f |= bit
    f |= CF_BASE | (int(o.get('blood') or 0) & 0xC00)
    new = []
    if sound:
        new.append(('CNAM', zs(sound)))
    new.append(('FNAM', zs(name)))
    if script:
        new.append(('SCRI', zs(script)))
    return new + [('NPDT', npdt), ('FLAG', struct.pack('<i', f))]


def _npc_head(db, o, name):
    race = _check_ref(db, o.get('race'), ('RACE',), 'race')
    cls = _check_ref(db, o.get('cls'), ('CLAS',), 'class')
    faction = _check_ref(db, (o.get('faction') or '').strip(), ('FACT',), 'faction')
    head = _check_ref(db, o.get('head'), ('BODY',), 'head')
    hair = _check_ref(db, o.get('hair'), ('BODY',), 'hair style')
    script = _check_ref(db, (o.get('script') or '').strip(), ('SCPT',), 'script')
    level = _num(o.get('level'), 0, 32767, 1)
    disp, rep, rank = _num(o.get('disposition'), 0, 100, 50), _num(o.get('reputation'), 0, 255), _num(o.get('rank'), 0, 9)
    gold = _num(o.get('gold'), 0, 2 ** 31 - 1)
    auto = bool(o.get('auto'))
    flags = (int(o.get('flags') or 0) & ~(0x1F | 0xC00)) | FLAG_BASE
    flags |= (FLAG_FEMALE if o.get('female') else 0) | (FLAG_ESSENTIAL if o.get('essential') else 0) | \
        (FLAG_RESPAWN if o.get('respawn') else 0) | (FLAG_AUTO if auto else 0) | (int(o.get('blood') or 0) & 0xC00)
    if auto:
        npdt = struct.pack('<hBBBxxxi', level, disp, rep, rank, gold)
    else:
        at = [_num(v, 0, 255) for v in (o.get('attributes') or [])][:8]
        sk = [_num(v, 0, 255) for v in (o.get('skills') or [])][:27]
        if len(at) != 8 or len(sk) != 27:
            raise EditError('Stats need all 8 attributes and 27 skills.')
        npdt = struct.pack('<h8B27Bx3HBBBxi', level, *at, *sk, _num(o.get('health'), 0, 65535),
                           _num(o.get('magicka'), 0, 65535), _num(o.get('fatigue'), 0, 65535), disp, rep, rank, gold)
    new = [('FNAM', zs(name)), ('RNAM', zs(race)), ('CNAM', zs(cls)), ('ANAM', zs(faction)), ('BNAM', zs(head)),
           ('KNAM', zs(hair))]
    if script:
        new.append(('SCRI', zs(script)))
    return new + [('NPDT', npdt), ('FLAG', struct.pack('<i', flags))]


def _save_rest(db, ri, r, rflags, old, new, o, name):
    """Everything characters and creatures share: inventory, spells, behaviour, services, travel, AI, size."""
    new = list(new)
    for it in o.get('items') or []:
        iid = _check_ref(db, (it.get('id') or '').strip(), None, 'item')
        if not iid:
            continue
        n = _num(it.get('count'), 1, 2 ** 31 - 1, 1)
        new.append(('NPCO', struct.pack('<i', -n if it.get('restock') else n) + _id32(iid)))
    for s in o.get('spells') or []:
        sid = _check_ref(db, ((s.get('id') if isinstance(s, dict) else s) or '').strip(), ('SPEL',), 'spell')
        if sid:
            new.append(('NPCS', _id32(sid)))
    # keep the bytes and service bits this editor doesn't know about as they were
    oaidt = next((d for t, d in old if t == 'AIDT' and len(d) >= 12), bytes(12))
    known = 0
    services = 0
    for _label, bit in SERVICE_BITS:
        known |= bit
        if int(o.get('services') or 0) & bit:
            services |= bit
    services |= struct.unpack_from('<i', oaidt, 8)[0] & ~known
    new.append(('AIDT', bytes([_num(o.get('hello'), 0, 255), oaidt[1], _num(o.get('fight'), 0, 255),
                               _num(o.get('flee'), 0, 255), _num(o.get('alarm'), 0, 255)]) + bytes(oaidt[5:8]) +
                struct.pack('<i', services) + bytes(oaidt[12:])))
    for tr in o.get('travel') or []:
        p = [float(v) for v in (tr.get('p') or [])][:6]
        p += [0.0] * (6 - len(p))
        new.append(('DODT', struct.pack('<6f', *p)))
        if (tr.get('cell') or '').strip():
            new.append(('DNAM', zs(tr['cell'].strip())))
    for a in o.get('ai') or []:
        k, rep_ = a.get('kind'), 1 if a.get('repeat') else 0
        if k == 'wander':
            idle = [_num(v, 0, 100) for v in (a.get('idle') or [])][:8]
            idle += [0] * (8 - len(idle))
            new.append(('AI_W', struct.pack('<hhB8BB', _num(a.get('distance'), 0, 32767), _num(a.get('duration'), 0, 32767),
                                            0, *idle, rep_)))
        elif k == 'travel':
            p = [float(v) for v in (a.get('p') or [0, 0, 0])][:3]
            new.append(('AI_T', struct.pack('<3fB3x', *p, rep_)))
        elif k in ('follow', 'escort'):
            tgt = _check_ref(db, (a.get('target') or '').strip(), ('NPC_', 'CREA'), 'character') or 'player'
            p = [float(v) for v in (a.get('p') or [0, 0, 0])][:3]
            new.append(('AI_F' if k == 'follow' else 'AI_E', struct.pack('<3fh', *p, _num(a.get('duration'), 0, 32767)) +
                        _id32(tgt) + bytes([rep_, 0])))
            if (a.get('cell') or '').strip():
                new.append(('CNDT', zs(a['cell'].strip())))
        elif k == 'activate':
            tgt = _check_ref(db, (a.get('target') or '').strip(), None, 'object')
            if tgt:
                new.append(('AI_A', _id32(tgt) + bytes([rep_])))
    scale = float(o.get('scale') or 1)
    if abs(scale - 1) > 1e-4:
        new.append(('XSCL', struct.pack('<f', max(0.5, min(2.0, scale)))))
    # keep what came before (NAME, MODL, ...) and anything unknown, in their places
    head_subs = [(t, d) for t, d in old if t not in OWN]
    # NAME and MODL go first, then everything this editor writes, then the rest
    first = [(t, d) for t, d in head_subs if t in ('NAME', 'MODL')]
    rest = [(t, d) for t, d in head_subs if t not in ('NAME', 'MODL')]
    model = (o.get('model') or '').strip()
    if r[0] == 'CREA' and model:
        # a creature's look is its model (pick another creature's to change how it looks)
        first = [(t, d) for t, d in first if t != 'MODL']
        first.insert(1 if first and first[0][0] == 'NAME' else 0, ('MODL', zs(model)))
    tag = r[0]
    db.project.set_record(tag, r[7], rflags & ~0x20, join_subs(first + new + rest),
                          created=bool(db.project.records.get(tag + '|' + r[7], {}).get('created')))
    commit(db, 'Edited %s "%s"' % ('creature' if tag == 'CREA' else 'character', name))
    return read(db, r[1])
