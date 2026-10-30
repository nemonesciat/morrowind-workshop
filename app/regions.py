"""Regions: the weather chances, background sounds, sleep encounters and map colour of an area of
the outdoors, and which outdoor cells belong to it.

REGN: NAME id, FNAM name, WEAT chances (8 bytes in Morrowind, 10 with Bloodmoon's snow and
blizzard), BNAM the leveled creature list met when sleeping outdoors, CNAM the map colour (RGBA),
and SNAM per sound: 32 bytes of sound id and one byte of chance. Exterior cells name their region
in RGNN."""
import struct

import editing
import landscape
from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import b64, join_subs, unb64, zs

WEATHER = ['Clear', 'Cloudy', 'Foggy', 'Overcast', 'Rain', 'Thunderstorm', 'Ash storm', 'Blight', 'Snow', 'Blizzard']


def _find(db, rid):
    lst = [v for v in db.by_key.get(('REGN', (rid or '').lower()), []) if v not in db.dead]
    return lst[-1] if lst else None


def _subs(db, ri):
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    return [(t, bytes(d)) for t, d in iter_subrecords(data)], flags


def read(db, rid):
    ri = _find(db, rid)
    if ri is None:
        raise EditError('There is no region called "%s".' % rid)
    r = db.recs[ri]
    subs, _f = _subs(db, ri)
    o = {'id': r[1], 'i': ri, 'name': '', 'weather': [0] * 10, 'weather_len': 8, 'sleep': '', 'color': [128, 128, 128],
         'sounds': [], 'src': db.plugins[r[3]]['name'],
         'mine': bool(db.project and ('REGN|' + r[7]) in db.project.records)}
    for t, d in subs:
        if t == 'FNAM':
            o['name'] = zstr(d)
        elif t == 'WEAT':
            o['weather_len'] = len(d)
            for n in range(min(10, len(d))):
                o['weather'][n] = d[n]
        elif t == 'BNAM':
            o['sleep'] = zstr(d)
        elif t == 'CNAM' and len(d) >= 3:
            o['color'] = list(d[:3])
        elif t == 'SNAM' and len(d) >= 33:
            o['sounds'].append({'id': zstr(d[:32]), 'chance': d[32]})
    o['cells'] = cells_of(db, r[1])
    return o


def all_regions(db):
    """Every region with its name, colour and how many outdoor cells it has."""
    counts = {}
    for k, reg in region_map(db).items():
        counts[reg] = counts.get(reg, 0) + 1
    out = []
    for (tag, key), lst in db.by_key.items():
        if tag != 'REGN':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        r = db.recs[live[-1]]
        subs, _f = _subs(db, live[-1])
        name, col = r[1], [128, 128, 128]
        for t, d in subs:
            if t == 'FNAM':
                name = zstr(d) or r[1]
            elif t == 'CNAM' and len(d) >= 3:
                col = list(d[:3])
        out.append({'id': r[1], 'name': name, 'color': col, 'cells': counts.get(key, 0), 'src': db.plugins[r[3]]['name'],
                    'mine': bool(db.project and ('REGN|' + key) in db.project.records)})
    out.sort(key=lambda x: x['name'].lower())
    return out


def region_map(db):
    """'gx,gy' -> region id (lower case) for every outdoor cell that has one."""
    out = {}
    for (tag, key), lst in db.by_key.items():
        if tag != 'CELL' or not key.startswith('#'):
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        r = db.recs[live[-1]]
        data = db.files[r[3]].record_at(r[4])[2]
        for st, sd in iter_subrecords(data):
            if st == 'RGNN':
                out[key[1:]] = zstr(sd).lower()
                break
            if st in ('FRMR', 'MVRF', 'NAM0'):
                break
    return out


def cells_of(db, rid):
    low = (rid or '').lower()
    return sorted(([int(v) for v in k.split(',')] for k, reg in region_map(db).items() if reg == low))


def save(db, rid, o, create=False):
    _require_project(db)
    rid = (rid or '').strip()
    if not rid or len(rid.encode(ENC, 'replace')) > 31:
        raise EditError('Give the region an ID of at most 31 characters, e.g. "MyMod Ashen Vale Region".')
    ri = _find(db, rid)
    if create and ri is not None:
        raise EditError('There is already a region called "%s".' % rid)
    if not create and ri is None:
        raise EditError('There is no region called "%s".' % rid)
    old = _subs(db, ri)[0] if ri is not None else []
    flags = db.recs[ri][6] & ~0x20 if ri is not None else 0
    if ri is not None:
        rid = db.recs[ri][1]
    name = (o.get('name') or '').strip() or rid
    if len(name.encode(ENC, 'replace')) > 31:
        raise EditError('Region names can be at most 31 characters.')
    w = [max(0, min(100, int(round(float(v or 0))))) for v in (list(o.get('weather') or []) + [0] * 10)[:10]]
    if sum(w) != 100:
        raise EditError('The weather chances add up to %d%%; they must add up to 100%%.' % sum(w))
    # Morrowind's own regions keep 8 weathers; snow and blizzard need the longer (Bloodmoon) form
    old_len = next((len(d) for t, d in old if t == 'WEAT'), 10 if create else 8)
    wlen = 10 if (w[8] or w[9] or old_len >= 10) else 8
    subs = [('NAME', zs(rid)), ('FNAM', zs(name)), ('WEAT', bytes(w[:wlen]))]
    sleep = (o.get('sleep') or '').strip()
    if sleep:
        si = db.resolve_id(sleep)
        if si is None or db.recs[si][0] != 'LEVC':
            raise EditError('"%s" is not a leveled creature list. Sleep encounters come from one, e.g. ex_wild_all_sleep.' % sleep)
        subs.append(('BNAM', zs(db.recs[si][1])))
    col = [max(0, min(255, int(v or 0))) for v in (list(o.get('color') or [128, 128, 128]) + [0, 0, 0])[:3]]
    subs.append(('CNAM', bytes(col) + b'\0'))
    # sounds: keep each untouched one byte for byte (the game's files have leftovers after the name)
    old_snd = [d for t, d in old if t == 'SNAM' and len(d) >= 33]
    for s in o.get('sounds') or []:
        sid = (s.get('id') or '').strip()
        if not sid:
            continue
        chance = max(0, min(100, int(s.get('chance') or 0)))
        same = next((d for d in old_snd if zstr(d[:32]).lower() == sid.lower() and d[32] == chance), None)
        if same is not None:
            old_snd.remove(same)
            subs.append(('SNAM', same))
            continue
        si = db.resolve_id(sid)
        if si is None or db.recs[si][0] != 'SOUN':
            raise EditError('"%s" is not a sound.' % sid)
        rawid = db.recs[si][1].encode(ENC, 'replace')[:31]
        subs.append(('SNAM', rawid + b'\0' * (32 - len(rawid)) + bytes([chance])))
    if len([1 for t, _d in subs if t == 'SNAM']) > 32:
        raise EditError('A region can have at most 32 background sounds.')
    key = rid.lower()
    was = bool(db.project.records.get('REGN|' + key, {}).get('created'))
    db.project.set_record('REGN', key, flags, join_subs(subs), created=create or was)
    db.sync_project()
    commit(db, '%s region "%s"' % ('Created' if create else 'Changed', name))
    return read(db, rid)


def assign(db, rid, cells, note=True):
    """Put outdoor cells (['gx,gy' or (gx, gy)]) into a region ('' takes them out of any)."""
    _require_project(db)
    if rid:
        ri = _find(db, rid)
        if ri is None:
            raise EditError('There is no region called "%s".' % rid)
        rid = db.recs[ri][1]
    done = 0
    for c in cells:
        gx, gy = (int(v) for v in (c.split(',') if isinstance(c, str) else c))
        key = '#%d,%d' % (gx, gy)
        # (land with no cell, a land-only mod's sea floor shaped into an island: editing._cell makes the cell)
        if not db.by_key.get(('CELL', key)) and key not in db.project.cells and landscape._winner(db, gx, gy) is None:
            continue                      # no land there: nothing to put in a region
        cell, _r = editing._cell(db, key)
        hdr = [(t, unb64(d)) for t, d in cell['header']]
        out, put = [], False
        for t, d in hdr:
            if t == 'RGNN':
                if rid and not put:
                    out.append(('RGNN', zs(rid)))
                    put = True
                continue
            out.append((t, d))
        if rid and not put:
            at = next((n + 1 for n, (t, _d) in enumerate(out) if t == 'DATA'), len(out))
            out.insert(at, ('RGNN', zs(rid)))
        if out != hdr:
            cell['header'] = [[t, b64(d)] for t, d in out]
            cell['props'] = True
            done += 1
            # back as the game has it, with nothing else changed here: no need to keep it in the mod
            base = [v for v in db.by_key.get(('CELL', key), []) if v not in db.dead and db.recs[v][3] != db.proj_pidx]
            if base and not cell.get('refs'):
                from project import split_cell
                r = db.recs[base[-1]]
                bh, _br = split_cell(db.files[r[3]].record_at(r[4])[2])
                if [(t, bytes(d)) for t, d in bh] == out:
                    del db.project.cells[key]
    db.sync_project()
    if note:
        commit(db, ('Put %d outdoor cell%s into %s' % (done, '' if done == 1 else 's', rid)) if rid
               else 'Took %d outdoor cell%s out of their region' % (done, '' if done == 1 else 's'))
    return {'changed': done}
