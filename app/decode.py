"""Turns a raw record into friendly, labelled fields for the detail panel."""
import struct
from collections import Counter

from esm import iter_subrecords, zstr
from database import (ARMOR_PART_LABELS, ATTRIBUTES, CELL_PREFIXES, ENUMS, INFO_LABELS, LABELS, SKILLS, STRUCTS,
                      TYPE_NAMES)

RANGES = ['Self', 'Touch', 'Target']
SCVR_TYPES = {'1': 'Function', '2': 'Global', '3': 'Local', '4': 'Journal', '5': 'Has item', '6': 'Dead count',
              '7': 'Not ID', '8': 'Not faction', '9': 'Not class', 'A': 'Not race', 'B': 'Not cell',
              'C': 'Not local'}
FLAG_NAMES = {
    ('NPC_', 'FLAG'): [(1, 'Female'), (2, 'Essential'), (4, 'Respawns'), (16, 'Auto-calculated stats'),
                       (1024, 'Skeleton blood'), (2048, 'Metal sparks blood')],
    ('WEAP', 'WPDT'): [(1, 'Ignores normal weapon resistance'), (2, 'Silver')],
    ('LIGH', 'LHDT'): [(1, 'Dynamic'), (2, 'Can be carried'), (4, 'Negative'), (8, 'Flicker'), (16, 'Fire'),
                       (32, 'Off by default'), (64, 'Flicker slow'), (128, 'Pulse'), (256, 'Pulse slow')],
    ('CONT', 'FLAG'): [(1, 'Organic (harvestable)'), (2, 'Respawns')],
    ('LEVI', 'DATA'): [(1, 'Level up to PC'), (2, 'Calculate for each item')],
    ('LEVC', 'DATA'): [(1, 'Level up to PC')],
    ('SPEL', 'SPDT'): [(1, 'Auto-calculated cost'), (2, 'PC start spell'), (4, 'Always succeeds')],
    ('BODY', 'BYDT'): [(1, 'For women'), (2, 'Not playable')],
    ('MGEF', 'MEDT'): [(0x200, 'Allow spellmaking'), (0x400, 'Allow enchanting'), (0x800, 'Negative light')],
}
ENTRY_LABEL = {'LEVI': ('INAM', 'Item'), 'LEVC': ('CNAM', 'Creature')}


def _fmt(v):
    if isinstance(v, float):
        return ('%.3f' % v).rstrip('0').rstrip('.') if v == v else 'NaN'
    if isinstance(v, bytes):
        return zstr(v)
    return str(v)


def _looks_text(b):
    if not b:
        return True
    # fixed-size string fields are padded with junk after the first NUL
    nul = b.find(b'\0')
    body = b if nul < 0 else b[:nul]
    if nul == 0 and any(b):
        return False
    if nul > 0 and len(body) < 2 and len(b) <= 8:
        return False   # probably a small number, not text
    return all(c >= 32 or c in (9, 10, 13) for c in body)


class Ctx:
    def __init__(self, db, tag):
        self.db, self.tag = db, tag
        self.fields = []

    def link(self, value):
        """Return the record index a string value refers to, if it names a known record."""
        lst = self.db.by_id.get(value.lower()) if value else None
        if not lst:
            return None
        # prefer the winning version of a non-INFO record
        for i in reversed(lst):
            if self.db.winner[i] and self.db.recs[i][0] != 'INFO':
                return i
        return lst[-1]

    def add(self, label, value, link=False, kind=None, edit=None):
        f = {'label': label, 'value': value}
        if edit:
            f['edit'] = edit
        if link and isinstance(value, str):
            li = self.link(value)
            if li is not None:
                f['link'] = li
        if kind:
            f['kind'] = kind
        self.fields.append(f)


def effect_text(db, sd):
    eff, skill, attr, rng, area, dur, mn, mx = struct.unpack_from('<hbbiiiii', sd)
    name = db.effect_names.get(eff, 'Effect #%d' % eff)
    if skill >= 0 and skill < len(SKILLS) and ('Skill' in name or eff in (21, 26, 78, 83, 89)):
        name += ' (%s)' % SKILLS[skill]
    if 0 <= attr < len(ATTRIBUTES) and ('Attribute' in name or eff in (17, 22, 74, 79, 85)):
        name += ' (%s)' % ATTRIBUTES[attr]
    parts = [name]
    if mx or mn:
        parts.append('%d pts' % mn if mn == mx else '%d-%d pts' % (mn, mx))
    if dur:
        parts.append('for %ds' % dur)
    if area:
        parts.append('in %d ft' % area)
    parts.append('on ' + (RANGES[rng] if 0 <= rng < 3 else str(rng)))
    return ' '.join(parts)


def decode_record(db, i):
    r = db.recs[i]
    tag, rid, name, pidx, offset, extra, flags = r[:7]
    pf = db.files[pidx]
    _t, _f, data = pf.record_at(offset)
    ctx = Ctx(db, tag)
    labels = dict(LABELS)
    if tag == 'INFO':
        labels.update(INFO_LABELS)
    if tag == 'DOOR':
        labels.update({'SNAM': 'Open Sound', 'ANAM': 'Close Sound'})
    if tag == 'SNDG':
        labels.update({'CNAM': 'Creature', 'SNAM': 'Sound'})
    if tag == 'BODY':
        labels.update({'FNAM': 'Race'})
    if tag in ('ARMO', 'CLOT'):
        labels_after_indx = ARMOR_PART_LABELS
    else:
        labels_after_indx = None
    seen_indx = False
    script_text = None
    cell_refs = None
    level_entries = []
    pending_entry = None

    script_edit = None
    for n, (st, sd) in enumerate(iter_subrecords(data)):
        ed = {'s': n, 't': st, 'k': 'str'}
        if tag == 'CELL' and st in CELL_PREFIXES:
            break
        key = (tag, st)
        if tag in ('LEVI', 'LEVC') and st == ENTRY_LABEL[tag][0]:
            pending_entry = zstr(sd)
            continue
        if tag in ('LEVI', 'LEVC') and st == 'INTV' and pending_entry is not None:
            lvl = struct.unpack_from('<h', sd)[0]
            level_entries.append((lvl, pending_entry))
            pending_entry = None
            continue
        if st == 'SCTX':
            script_text = sd.decode('cp1252', 'replace').replace('\r\n', '\n')
            script_edit = ed
            continue
        if st == 'SCDT' or st == 'SCVR' and tag == 'SCPT':
            continue
        if st == 'BNAM' and tag == 'INFO':
            ctx.add('Result Script', zstr(sd), kind='code', edit=ed)
            continue
        if st == 'NAME' and tag == 'INFO':
            ctx.add('Response', zstr(sd), kind='text', edit=ed)
            continue
        if st in ('TEXT', 'DESC') and tag in ('BOOK', 'BSGN', 'RACE', 'CLAS', 'SKIL', 'MGEF'):
            txt = zstr(sd)
            ctx.add('Text' if tag == 'BOOK' else 'Description', txt, kind='html' if tag == 'BOOK' else 'text', edit=ed)
            continue
        if st == 'ENAM' and tag in ('SPEL', 'ALCH', 'ENCH') and len(sd) >= 24:
            ctx.add('Effect', effect_text(db, sd))
            continue
        if st == 'NPCO' and len(sd) >= 36:
            cnt = struct.unpack_from('<i', sd)[0]
            item = zstr(sd[4:36])
            ctx.add('Carries', item, link=True)
            ctx.fields[-1]['count'] = cnt
            continue
        if st == 'SCVR' and tag == 'INFO' and len(sd) >= 5:
            kind = SCVR_TYPES.get(chr(sd[1]), 'Condition')
            subject = zstr(sd[5:]) if kind != 'Function' else 'function %s' % sd[2:4].decode('ascii', 'replace')
            ctx.add('Condition', '%s %s %s' % (kind, subject, _scvr_op(sd)))
            continue
        if st in ('INTV', 'FLTV') and tag == 'INFO':
            if ctx.fields and ctx.fields[-1]['label'] == 'Condition' and len(sd) >= 4:
                v = struct.unpack_from('<i' if st == 'INTV' else '<f', sd)[0]
                ctx.fields[-1]['value'] += ' ' + _fmt(v)
            continue
        if st == 'DODT' and len(sd) >= 24:
            x, y, z = struct.unpack_from('<3f', sd)
            ctx.add('Travel Destination', 'position %.0f, %.0f, %.0f' % (x, y, z))
            continue
        if st == 'INDX' and labels_after_indx:
            seen_indx = True
            ctx.add('Body Slot', str(sd[0]) if sd else '')
            continue
        if seen_indx and labels_after_indx and st in ('BNAM', 'CNAM'):
            ctx.add(labels_after_indx[st], zstr(sd), link=True)
            continue
        if tag == 'CELL' and st == 'DATA' and len(sd) >= 12:
            cf, gx, gy = struct.unpack_from('<iii', sd)
            ctx.add('Kind', 'Interior' if cf & 1 else 'Exterior (grid %d, %d)' % (gx, gy))
            names_on = [n for bit, n in ((2, 'Has water'), (4, 'Sleeping is illegal'), (128, 'Behaves like exterior'))
                        if cf & bit]
            if names_on:
                ctx.add('Flags', ', '.join(names_on))
            continue
        if tag == 'CELL' and st == 'AMBI' and len(sd) >= 16:
            for lab, o in (('Ambient light', 0), ('Sunlight', 4), ('Fog colour', 8)):
                ctx.add(lab, 'rgb(%d, %d, %d)' % tuple(sd[o:o + 3]), kind='color')
            ctx.add('Fog density', _fmt(struct.unpack_from('<f', sd, 12)[0]))
            continue
        if tag == 'NPC_' and st == 'NPDT':
            _decode_npdt(ctx, sd, n)
            continue
        if key in STRUCTS:
            fmt, names = STRUCTS[key]
            try:
                vals = struct.unpack_from(fmt, sd)
            except struct.error:
                ctx.add(st, sd.hex(' ')[:200], kind='raw')
                continue
            layout = struct_layout(fmt)
            for lab, v, (code, off, _sz) in zip(names, vals, layout):
                if lab is None:
                    continue
                enum = ENUMS.get((tag, lab))
                fed = {'s': n, 't': st, 'k': 'num', 'c': code, 'o': off, 'raw': v}
                if enum:
                    fed['opts'] = enum
                if lab == 'Governing Attribute':
                    fed['opts'] = ATTRIBUTES
                if lab == 'Flags' and (tag, st) in FLAG_NAMES:
                    fed['bits'] = FLAG_NAMES[(tag, st)]
                if code == 's':
                    fed = None
                if lab.startswith('Effect ') and tag == 'INGR':
                    if v < 0:
                        continue
                    v = db.effect_names.get(v, 'Effect #%d' % v)
                elif lab.startswith(('Skill ', 'Attribute ')) and tag == 'INGR':
                    continue
                elif lab == 'Governing Attribute' and 0 <= v < 8:
                    v = ATTRIBUTES[v]
                elif enum and isinstance(v, int) and 0 <= v < len(enum):
                    v = enum[v]
                elif enum and isinstance(v, int) and v < 0:
                    v = 'None'
                elif lab == 'Flags' and (tag, st) in FLAG_NAMES:
                    names_on = [n for bit, n in FLAG_NAMES[(tag, st)] if v & bit]
                    v = ', '.join(names_on) if names_on else 'None'
                ctx.add(lab, _fmt(v), edit=None if tag == 'INGR' and lab.startswith('Effect') else fed)
            continue
        label = labels.get(st, st)
        if _looks_text(sd):
            v = zstr(sd)
            ctx.add(label, v, link=st not in ('NAME', 'FNAM', 'MODL', 'ITEX', 'TEXT', 'DESC', 'STRV', 'PTEX'),
                    kind='path' if st in ('MODL', 'ITEX', 'PTEX') else None,
                    edit=None if st == 'NAME' and tag != 'INFO' else ed)
        elif len(sd) == 4:
            iv = struct.unpack_from('<i', sd)[0]
            fv = struct.unpack_from('<f', sd)[0]
            isf = abs(iv) > 1 << 24 and 1e-6 < abs(fv) < 1e9
            ctx.add(label, _fmt(fv) if isf else str(iv), edit={'s': n, 't': st, 'k': 'num', 'c': 'f' if isf else 'i', 'o': 0})
        else:
            ctx.add(label, sd[:64].hex(' ') + (' ...' if len(sd) > 64 else ''), kind='raw')

    out = {
        'i': i, 'type': tag, 'type_label': TYPE_NAMES.get(tag, tag), 'id': rid, 'name': name,
        'plugin': db.plugins[pidx]['name'], 'deleted': bool(flags & 0x20), 'persistent': bool(flags & 0x400),
        'blocked': bool(flags & 0x2000), 'fields': ctx.fields,
        'mine': pidx == db.proj_pidx, 'winner': bool(db.winner[i]), 'key': r[7],
        'can_edit': tag not in ('CELL', 'LAND', 'PGRD'),
        'can_copy': tag not in ('CELL', 'INFO', 'DIAL', 'LAND', 'PGRD', 'GMST', 'SKIL', 'MGEF', 'LTEX'),
    }
    if pidx == db.proj_pidx and db.project:
        rec = db.project.records.get(tag + '|' + r[7])
        out['created'] = bool(rec and rec.get('created'))
    if script_text is not None:
        out['script'] = script_text
        out['script_edit'] = script_edit
    if level_entries:
        out['level_list'] = [{'level': l, 'id': e, 'link': ctx.link(e)} for l, e in level_entries]
    if tag == 'CELL':
        out['contents'] = _cell_contents(db, ctx, i)
    if tag == 'DIAL':
        out['responses'] = [{'i': ii, 'text': db.recs[ii][2], 'speaker': db.recs[ii][5].split(' ', 1)[1]
                             if ' ' in db.recs[ii][5] else '', 'plugin': db.plugins[db.recs[ii][3]]['name']}
                            for ii in _dial_responses(db, i)][:500]
    if tag == 'INFO' and i in db.info_dial:
        d = db.info_dial[i]
        out['topic'] = {'i': d, 'id': db.recs[d][1]}
    # Versions across plugins
    vers = db.versions(i)
    out['versions'] = [{'i': v, 'plugin': db.plugins[db.recs[v][3]]['name'], 'winner': bool(db.winner[v])}
                       for v in vers]
    # Where used
    used = db.used_in.get(rid.lower(), ()) if tag not in ('CELL', 'INFO', 'DIAL') else ()
    seen, used_rows = set(), []
    for u in sorted(used):
        ur = db.recs[u]
        if (ur[0], ur[7]) in seen:
            continue
        seen.add((ur[0], ur[7]))
        u = db.versions(u)[-1]   # link to the version that is active in game
        ur = db.recs[u]
        used_rows.append({'i': u, 'type': ur[0], 'type_label': TYPE_NAMES.get(ur[0], ur[0]), 'id': ur[1],
                          'name': ur[2]})
    out['used_in'] = used_rows[:300]
    out['used_in_total'] = len(used_rows)
    return out


def _dial_responses(db, d):
    """All INFO lines for a topic across every plugin, winning versions only."""
    did = db.recs[d][1].lower()
    res = []
    for v in db.by_key.get(('DIAL', did), [d]):
        for ii in db.dial_infos.get(v, []):
            if db.winner[ii] and not db.recs[ii][6] & 0x20:
                res.append(ii)
    return res


def _scvr_op(sd):
    ops = {'0': '=', '1': '!=', '2': '>', '3': '>=', '4': '<', '5': '<='}
    try:
        return ops.get(chr(sd[4]), '?')
    except Exception:
        return '?'


def struct_layout(fmt):
    """[(code, offset, size)] for every value a struct format unpacks to."""
    out, off, i = [], 0, 1 if fmt[0] in '<>=!@' else 0
    while i < len(fmt):
        num = ''
        while fmt[i].isdigit():
            num += fmt[i]
            i += 1
        c = fmt[i]
        i += 1
        cnt = int(num) if num else 1
        if c == 's':
            out.append((c, off, cnt))
            off += cnt
            continue
        size = struct.calcsize('<' + c)
        for _ in range(cnt):
            out.append((c, off, size))
            off += size
    return out


def _decode_npdt(ctx, sd, n):
    def num(label, layout, idx, vals, kind=None):
        code, off, _s = layout[idx]
        ctx.add(label, str(vals[idx]), kind=kind, edit={'s': n, 't': 'NPDT', 'k': 'num', 'c': code, 'o': off})

    if len(sd) >= 52:
        fmt = '<h8B27BBhhhBBBBi'
        vals, lay = struct.unpack_from(fmt, sd), struct_layout(fmt)
        num('Level', lay, 0, vals)
        for k, a in enumerate(ATTRIBUTES):
            num(a, lay, 1 + k, vals, 'stat')
        for k, s in enumerate(SKILLS):
            num(s, lay, 9 + k, vals, 'skill')
        for label, idx in (('Health', 37), ('Magicka', 38), ('Fatigue', 39), ('Disposition', 40),
                           ('Reputation', 41), ('Rank', 42), ('Gold', 44)):
            num(label, lay, idx, vals)
    elif len(sd) >= 12:
        fmt = '<hBBBBBBi'
        vals, lay = struct.unpack_from(fmt, sd), struct_layout(fmt)
        num('Level', lay, 0, vals)
        ctx.add('Stats', 'Auto-calculated from class and level')
        for label, idx in (('Disposition', 1), ('Reputation', 2), ('Rank', 3), ('Gold', 7)):
            num(label, lay, idx, vals)


def _cell_contents(db, ctx, i):
    """Objects placed in a cell, merged across every plugin that edits it."""
    from database import CELL_REF_RE
    seen = set()
    counts = Counter()
    for v in db.versions(i):
        r = db.recs[v]
        _t, _f, data = db.files[r[3]].record_at(r[4])
        for m in CELL_REF_RE.finditer(data):
            size = struct.unpack('<I', m.group(1))[0]
            obj = zstr(data[m.end():m.end() + size])
            refnum = data[m.start() + 8:m.start() + 12]
            k = (refnum, obj.lower())
            if k in seen:
                continue
            seen.add(k)
            counts[obj] += 1
    rows = []
    for obj, n in counts.most_common():
        li = ctx.link(obj)
        rr = db.recs[li] if li is not None else None
        rows.append({'id': obj, 'count': n, 'link': li, 'type': rr[0] if rr else '',
                     'type_label': TYPE_NAMES.get(rr[0], '') if rr else '', 'name': rr[2] if rr else ''})
    return rows
