"""Check my mod: the record-by-record checks the Construction Set's "verify" makes, in plain words.

Only your mod's own records and placed objects are checked (the game's own files have their quirks and
nothing can be done about them here). Each finding says what is wrong and opens the record. Things
that point to IDs that don't exist, scripts that won't compile and missing files are checked by
release.py already; this adds what the CS verifier looks at inside each record."""
import re
import struct

from esm import ENC, iter_subrecords, zstr
from project import ref_info, unb64

NAMED = {'ACTI', 'ALCH', 'APPA', 'ARMO', 'BOOK', 'CLOT', 'CONT', 'CREA', 'DOOR', 'INGR', 'LOCK', 'MISC', 'NPC_',
         'PROB', 'REPA', 'WEAP', 'CLAS', 'FACT', 'RACE', 'BSGN', 'REGN', 'SPEL'}


def _mute_panel(key, s):
    """A sliding panel another object pulls (mechanism.make_slide): it has no script of its own and no
    name on purpose, so it is not a button in the game's crosshair."""
    import re
    return bool(re.search(r'_slide(_\d+)?$', key)) and not zstr(s.get('SCRI', b''))


PICKABLE = {'MISC', 'BOOK', 'INGR', 'ALCH', 'WEAP', 'ARMO', 'CLOT', 'APPA', 'LOCK', 'PROB', 'REPA'}


def _carried(db, ri):
    """A light the player can carry (its Carry flag)."""
    try:
        _t, _f, data = db.files[db.recs[ri][3]].record_at(db.recs[ri][4])
        for t, d in iter_subrecords(data):
            if t == 'LHDT' and len(d) >= 24:
                return bool(struct.unpack_from('<i', d, 20)[0] & 2)
    except Exception:
        pass
    return False


MODELLED = {'ACTI', 'ALCH', 'APPA', 'ARMO', 'BOOK', 'CLOT', 'CONT', 'CREA', 'DOOR', 'INGR', 'LOCK', 'MISC', 'PROB',
            'REPA', 'STAT', 'WEAP', 'BODY'}
ICONED = {'ALCH', 'APPA', 'ARMO', 'BOOK', 'CLOT', 'INGR', 'LOCK', 'MISC', 'PROB', 'REPA', 'WEAP'}
# weight and value live at the start of each item's stats block
STATS = {'WEAP': ('WPDT', '<fi'), 'ARMO': ('AODT', '<xxxxfi'), 'CLOT': ('CTDT', '<xxxxfh'), 'MISC': ('MCDT', '<fi'),
         'BOOK': ('BKDT', '<fi'), 'ALCH': ('ALDT', '<fi'), 'APPA': ('AADT', '<xxxxffi'), 'LOCK': ('LKDT', '<fi'),
         'PROB': ('PBDT', '<fi'), 'REPA': ('RIDT', '<fi'), 'LIGH': ('LHDT', '<fi'), 'INGR': ('IRDT', '<fi')}
KIND = {'ACTI': 'activator', 'ALCH': 'potion', 'APPA': 'apparatus', 'ARMO': 'armour', 'BOOK': 'book', 'BSGN': 'birthsign',
        'CLAS': 'class', 'CLOT': 'clothing', 'CONT': 'container', 'CREA': 'creature', 'DOOR': 'door', 'ENCH': 'enchantment',
        'FACT': 'faction', 'GLOB': 'global variable', 'INGR': 'ingredient', 'LEVC': 'creature list', 'LEVI': 'item list',
        'LIGH': 'light', 'LOCK': 'lockpick', 'MISC': 'item', 'NPC_': 'person', 'PROB': 'probe', 'RACE': 'race',
        'REGN': 'region', 'REPA': 'repair tool', 'SOUN': 'sound', 'SPEL': 'spell', 'STAT': 'static', 'WEAP': 'weapon',
        'BODY': 'body part', 'SNDG': 'creature sound', 'SKIL': 'skill', 'MGEF': 'magic effect', 'DIAL': 'topic',
        'INFO': 'dialogue line', 'SCPT': 'script'}


def _label(db, tag, key, subs):
    name = next((zstr(d) for t, d in subs if t == 'FNAM'), '') if tag != 'INFO' else ''
    rid = next((zstr(d) for t, d in subs if t == 'NAME'), key) if tag not in ('SCPT', 'INFO') else key
    return '%s "%s"' % (KIND.get(tag, tag), name or rid)


def findings(db):
    """[{sev: error|warning|info, tag, key, i, text}] for everything in the mod."""
    p = db.project
    if not p:
        return []
    out = []

    def add(sev, tag, key, text, i=None, cell=None):
        f = {'sev': sev, 'tag': tag, 'key': key, 'text': text}
        if i is None and tag != 'CELL':
            i = db.overlay.get((tag, key))
        if i is not None:
            f['i'] = i
        if cell:
            f['cell'] = cell
        out.append(f)

    for rec in p.records.values():
        tag, key = rec['tag'], rec['key']
        if rec['flags'] & 0x20:
            continue
        subs = [(t, bytes(d)) for t, d in iter_subrecords(unb64(rec['data']))]
        s = {}
        for t, d in subs:
            s.setdefault(t, d)
        label = _label(db, tag, key, subs)
        name = zstr(s.get('FNAM', b''))
        if tag in NAMED and not name and not (tag == 'ACTI' and _mute_panel(key, s)):
            add('warning' if tag in ('ACTI', 'CONT', 'DOOR', 'STAT') else 'error', tag, key,
                '%s has no name: it shows up blank in the game.' % label)
        if tag in MODELLED and not zstr(s.get('MODL', b'')):
            add('error', tag, key, '%s has no model, so the game can\'t show it (a yellow "missing" sign at best).' % label)
        if tag in ICONED and not zstr(s.get('ITEX', b'')):
            add('warning', tag, key, '%s has no icon: it shows as a blank square in the inventory.' % label)
        st = STATS.get(tag)
        if st and st[0] in s and len(s[st[0]]) >= struct.calcsize(st[1]):
            vals = struct.unpack_from(st[1], s[st[0]])
            w, v = (vals[-2], vals[-1]) if tag != 'APPA' else (vals[1], vals[2])
            if w < 0:
                add('error', tag, key, '%s weighs less than nothing (%g).' % (label, w))
            if v < 0:
                add('error', tag, key, '%s is worth less than nothing (%d).' % (label, v))
        if tag in ('SPEL', 'ENCH', 'ALCH'):
            effs = [d for t, d in subs if t == 'ENAM']
            if not effs:
                add('error', tag, key, '%s has no effects: it does nothing.' % label)
            for d in effs:
                if len(d) >= 24:
                    eff, skill, attr, rng, area, dur, mn, mx = struct.unpack_from('<hbbiiiii', d)
                    if eff < 0 or eff not in db.effect_names:
                        add('error', tag, key, '%s uses magic effect number %d, which doesn\'t exist.' % (label, eff))
                    if mn > mx:
                        add('warning', tag, key, '%s has an effect whose least strength (%d) is more than its most (%d).' % (label, mn, mx))
                    if mn < 0 or dur < 0 or area < 0:
                        add('error', tag, key, '%s has an effect with a negative strength, duration or area.' % label)
            if tag == 'SPEL' and 'SPDT' in s and len(s['SPDT']) >= 12:
                typ, cost, fl = struct.unpack_from('<iii', s['SPDT'])
                if typ == 0 and not (fl & 1) and cost <= 0:
                    add('warning', tag, key, '%s costs no magicka and its cost isn\'t worked out automatically.' % label)
            if tag == 'ENCH' and 'ENDT' in s and len(s['ENDT']) >= 16:
                typ, cost, charge, fl = struct.unpack_from('<iiii', s['ENDT'])
                if typ != 3 and charge > 0 and cost > charge:
                    add('warning', tag, key, '%s costs %d a use but only holds %d: it can never be used.' % (label, cost, charge))
                if typ == 3 and any(struct.unpack_from('<hbbi', d)[3] != 0 for d in effs if len(d) >= 24):
                    add('warning', tag, key, '%s is a constant effect but not every effect is on Self.' % label)
        if tag == 'CLAS' and 'CLDT' in s and len(s['CLDT']) >= 60:
            v = struct.unpack_from('<15i', s['CLDT'])
            if v[0] == v[1]:
                add('error', tag, key, '%s has the same favoured attribute twice.' % label)
            sk = list(v[3:13])
            if len(set(sk)) != 10:
                add('error', tag, key, '%s has a skill listed twice among its major and minor skills.' % label)
            if not zstr(s.get('DESC', b'')) and v[13]:
                add('info', tag, key, '%s has no description for the character screen.' % label)
        if tag == 'FACT':
            if not any(t == 'RNAM' for t, _d in subs):
                add('error', tag, key, '%s has no ranks.' % label)
            if 'FADT' in s and len(s['FADT']) >= 240:
                v = struct.unpack_from('<2i50i7ii', s['FADT'])
                if v[0] == v[1]:
                    add('warning', tag, key, '%s has the same favoured attribute twice.' % label)
                if all(x < 0 for x in v[52:59]):
                    add('warning', tag, key, '%s cares about no skills, so nobody can ever be promoted.' % label)
        if tag == 'RACE' and 'RADT' in s and len(s['RADT']) >= 140:
            v = struct.unpack_from('<14i16i4fi', s['RADT'])
            if any(x <= 0 for x in v[30:34]):
                add('error', tag, key, '%s has a height or build of 0: its people would be invisible.' % label)
            if not zstr(s.get('DESC', b'')) and v[34] & 1:
                add('info', tag, key, '%s can be played but has no description.' % label)
        if tag == 'BSGN':
            if not zstr(s.get('TNAM', b'')):
                add('warning', tag, key, '%s has no constellation picture.' % label)
            if not any(t == 'NPCS' for t, _d in subs):
                add('info', tag, key, '%s gives no spells or abilities.' % label)
        if tag == 'REGN' and 'WEAT' in s:
            tot = sum(s['WEAT'][:10])
            if tot != 100:
                add('error', tag, key, '%s: the weather chances add up to %d%%, not 100%%.' % (label, tot))
        if tag == 'SOUN':
            f = zstr(s.get('FNAM', b''))
            if not f:
                add('error', tag, key, '%s plays no file.' % label)
            elif ('sound/' + f.replace('\\', '/').lower()) not in db.assets:
                add('error', tag, key, '%s plays Sound\\%s, which isn\'t installed.' % (label, f))
            if 'DATA' in s and len(s['DATA']) >= 3 and s['DATA'][0] == 0:
                add('warning', tag, key, '%s has its volume at 0.' % label)
        if tag in ('LEVI', 'LEVC'):
            n = sum(1 for t, _d in subs if t == ('INAM' if tag == 'LEVI' else 'CNAM'))
            if not n:
                add('warning', tag, key, '%s is empty.' % label)
            if 'NNAM' in s and s['NNAM'] and s['NNAM'][0] >= 100:
                add('warning', tag, key, '%s has a 100%% chance of nothing, so it never gives anything.' % label)
        if tag == 'CONT' and 'CNDT' in s and len(s['CNDT']) >= 4 and struct.unpack_from('<f', s['CNDT'])[0] <= 0:
            add('warning', tag, key, '%s can hold nothing (its capacity is 0).' % label)
        if tag == 'CREA' and 'NPDT' in s and len(s['NPDT']) >= 96:
            v = struct.unpack_from('<24i', s['NPDT'])
            if v[1] <= 0:
                add('warning', tag, key, '%s is level 0.' % label)
            if v[10] <= 0:
                add('warning', tag, key, '%s has no health: it dies at once.' % label)
        if tag == 'NPC_':
            for field, what in (('RNAM', 'race'), ('CNAM', 'class'), ('BNAM', 'head'), ('KNAM', 'hair')):
                if not zstr(s.get(field, b'')):
                    add('error', tag, key, '%s has no %s%s.' % (label, what, ': the game can\'t show them' if field in ('BNAM', 'KNAM') else ''))
            if 'NPDT' in s and len(s['NPDT']) >= 12 and struct.unpack_from('<h', s['NPDT'])[0] <= 0:
                add('warning', tag, key, '%s is level 0.' % label)
        if tag == 'BOOK' and not zstr(s.get('TEXT', b'')).strip():
            add('info', tag, key, '%s has no text.' % label)
        if tag == 'LIGH' and 'LHDT' in s and len(s['LHDT']) >= 24:
            w, v, dur, rad, r_, g_, b_, _x, fl = struct.unpack_from('<fiiiBBBBi', s['LHDT'])
            if rad <= 0 and not zstr(s.get('SNAM', b'')):
                add('info', tag, key, '%s gives no light (its radius is 0) and plays no sound.' % label)
            if (fl & 2) and dur == 0:
                add('warning', tag, key, '%s can be carried but burns for 0 seconds.' % label)
        if tag == 'INFO':
            if not zstr(s.get('NAME', b'')).strip() and not zstr(s.get('BNAM', b'')).strip() and not zstr(s.get('SNAM', b'')):
                add('warning', tag, key, 'A dialogue line in "%s" says nothing and does nothing.' % key.split('|', 1)[0])
        if tag == 'GMST' and key.startswith('s') and 'STRV' in s and not zstr(s['STRV']):
            add('warning', tag, key, 'Game setting %s is an empty text.' % key)
        if tag == 'SKIL' and 'SKDT' in s and len(s['SKDT']) >= 24:
            v = struct.unpack_from('<ii4f', s['SKDT'])
            if all(x <= 0 for x in v[2:6]):
                add('warning', tag, key, '%s rises from nothing: all its use values are 0.' % label)
        if tag == 'MGEF' and 'MEDT' in s and len(s['MEDT']) >= 8 and struct.unpack_from('<if', s['MEDT'])[1] < 0:
            add('error', tag, key, '%s has a negative base cost.' % label)
        if tag == 'BODY':
            if not zstr(s.get('FNAM', b'')):
                add('warning', tag, key, '%s belongs to no race.' % label)
        if tag == 'SNDG' and not zstr(s.get('SNAM', b'')):
            add('error', tag, key, '%s plays no sound.' % label)

    # placed objects
    import mapdata
    for ck, c in list(p.cells.items()):
        for rk, r in list(c['refs'].items()):
            if r.get('deleted'):
                continue
            subs = [(t, unb64(d)) for t, d in r['subs']]
            rid, pos, scale, _del = ref_info(subs)
            s = dict(subs)
            where = mapdata.cell_info(db, ck)
            where = (where['name'] or where['region'] or ck) if where else ck
            if not 0.5 <= scale <= 2.0:
                add('warning', 'CELL', ck, '"%s" in %s is scaled by %g: the game only allows 0.5 to 2.' % (rid, where, scale), cell=ck)
            elif abs(scale - 1.0) > 0.001:
                # Project Tamriel's scaling rules (packaging/nexus/pt-interior-guidelines.md)
                ri = db.resolve_id(rid)
                rtag = db.recs[ri][0] if ri is not None else ''
                low = rid.lower()
                if rtag in PICKABLE or (rtag == 'LIGH' and _carried(db, ri)):
                    add('warning', 'CELL', ck, '"%s" in %s is scaled by %g, but can be picked up: the game sets it back to 1 when it is put down.' % (rid, where, scale), cell=ck)
                elif re.search(r'crate|barrel|vase|chest', low) and rtag in ('CONT', 'STAT', 'ACTI'):
                    add('info', 'CELL', ck, '"%s" in %s is scaled by %g: crates, barrels, vases and chests come in one size.' % (rid, where, scale), cell=ck)
                elif 'sack' in low and scale < 0.75:
                    add('info', 'CELL', ck, '"%s" in %s is scaled by %g: a sack no smaller than 0.75 (there are small sacks).' % (rid, where, scale), cell=ck)
                elif re.search(r'basket|urn', low) and not 0.9 <= scale <= 1.1 and not (abs(scale - 0.5) < 0.01 and 'urn' in low):
                    add('info', 'CELL', ck, '"%s" in %s is scaled by %g: baskets and urns between 0.9 and 1.1 (an urn on a tomb altar 0.5).' % (rid, where, scale), cell=ck)
                elif 'furn' in low and scale < 0.9 and not re.search(r'rug|carpet|planter|plant|flora|tree', low):
                    add('info', 'CELL', ck, '"%s" in %s is scaled by %g: furniture no smaller than 0.9.' % (rid, where, scale), cell=ck)
            if 'FLTV' in s and len(s['FLTV']) >= 4 and struct.unpack_from('<i', s['FLTV'])[0] > 100:
                add('warning', 'CELL', ck, '"%s" in %s has a lock over 100, which no lockpick or spell can open.' % (rid, where), cell=ck)
            if 'INDX' in s and 'CNAM' not in s:
                add('warning', 'CELL', ck, '"%s" in %s has a faction rank but no faction.' % (rid, where), cell=ck)
            if 'ANAM' in s and 'CNAM' in s:
                add('warning', 'CELL', ck, '"%s" in %s has both a person and a faction as owner; the game keeps the person.' % (rid, where), cell=ck)
            if 'DODT' in s and len(s['DODT']) >= 24 and 'DNAM' not in s and not ck.startswith('#'):
                x, y = struct.unpack_from('<2f', s['DODT'])
                if abs(x) > 8192 * 100 or abs(y) > 8192 * 100:
                    add('warning', 'CELL', ck, 'A door in %s leads outdoors to a spot far outside the world.' % where, cell=ck)
    # weapons and armour: a new piece nobody hands out, a list level far from the game's for its worth, half a
    # pair in a set (gearcheck.py)
    try:
        import gearcheck
        for sev, tag, key, text in gearcheck.findings(db):
            add(sev, tag, key, text)
            out[-1]['gear'] = True
    except Exception as e:                  # (a check must never stop the list)
        print('gear checks:', e)
    order = {'error': 0, 'warning': 1, 'info': 2}
    out.sort(key=lambda f: (order[f['sev']], f['tag'], f['key']))
    return out


def summary(db):
    f = findings(db)
    n = {'error': 0, 'warning': 0, 'info': 0}
    for x in f:
        n[x['sev']] += 1
    return {'findings': f, 'counts': n}
