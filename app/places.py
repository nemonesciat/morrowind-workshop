"""A place's own settings: lighting (ambient, sunlight, fog), water, and how it behaves.

Interiors keep these in the cell header: AMBI holds ambient, sunlight and fog colours plus fog
density, WHGT the water height, and DATA the flags (has water, no sleeping, behaves like outdoors)."""
import struct

import editing
from editing import EditError, commit, _require_project
from esm import iter_subrecords, zstr
from project import b64, unb64

F_INTERIOR, F_WATER, F_NOSLEEP, F_LIKE_EXT = 0x01, 0x02, 0x04, 0x80

# moods to start from: ambient, sunlight, fog colours and fog density
PRESETS = [
    ('Cosy house', [92, 74, 52], [214, 168, 112], [60, 48, 36], 0.6),
    ('Shop or guild hall', [110, 100, 86], [235, 215, 170], [90, 80, 66], 0.4),
    ('Tavern at night', [70, 52, 36], [200, 140, 80], [40, 30, 22], 0.7),
    ('Cave', [38, 34, 30], [80, 72, 64], [18, 16, 14], 0.85),
    ('Ancestral tomb', [40, 36, 46], [96, 88, 120], [22, 20, 28], 0.9),
    ('Dwemer ruin', [70, 56, 40], [190, 140, 80], [56, 40, 26], 0.75),
    ('Daedric shrine', [62, 28, 24], [170, 60, 40], [40, 12, 10], 0.85),
    ('Mine (glowing ebony)', [36, 40, 44], [90, 120, 140], [16, 20, 24], 0.85),
    ('Sewers', [40, 46, 36], [90, 110, 80], [22, 28, 20], 0.9),
    ('Telvanni tower', [70, 66, 78], [170, 160, 200], [44, 40, 52], 0.6),
    ('Bright and plain', [140, 140, 140], [255, 255, 255], [120, 120, 120], 0.2),
]


def _header(db, key):
    """(header subrecords, flags of the record, which of them are the project's) for a cell."""
    p = db.project
    if p and key in p.cells:
        c = p.cells[key]
        return [(t, unb64(d)) for t, d in c['header']], c.get('flags', 0)
    lst = [v for v in db.by_key.get(('CELL', key), []) if v not in db.dead]
    if not lst:
        raise EditError('That place does not exist.')
    from project import split_cell
    r = db.recs[lst[-1]]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    hdr, _refs = split_cell(data)
    return hdr, flags


def read(db, key):
    hdr, _flags = _header(db, key)
    o = {'key': key, 'name': '', 'interior': not key.startswith('#'), 'ambient': [80, 80, 80], 'sun': [160, 160, 160],
         'fog': [60, 60, 60], 'density': 0.5, 'has_lighting': False, 'water': False, 'water_height': 0.0,
         'no_sleep': False, 'like_exterior': False, 'region': ''}
    for t, d in hdr:
        if t == 'NAME':
            o['name'] = zstr(d)
        elif t == 'DATA' and len(d) >= 4:
            f = struct.unpack_from('<i', d)[0]
            o['water'] = bool(f & F_WATER)
            o['no_sleep'] = bool(f & F_NOSLEEP)
            o['like_exterior'] = bool(f & F_LIKE_EXT)
        elif t == 'AMBI' and len(d) >= 16:
            o['ambient'] = list(d[0:3])
            o['sun'] = list(d[4:7])
            o['fog'] = list(d[8:11])
            o['density'] = round(struct.unpack_from('<f', d, 12)[0], 3)
            o['has_lighting'] = True
        elif t == 'WHGT' and len(d) >= 4:
            o['water_height'] = round(struct.unpack_from('<f', d)[0], 1)
        elif t == 'INTV' and len(d) >= 4 and key and not key.startswith('#'):
            o['water_height'] = float(struct.unpack_from('<i', d)[0])
        elif t == 'RGNN':
            o['region'] = zstr(d)
    o['mine'] = bool(db.project and key in db.project.cells and db.project.cells[key].get('props'))
    return o


def _col(v):
    v = list(v or [0, 0, 0])[:3]
    return bytes(max(0, min(255, int(round(float(x))))) for x in v) + b'\0'


def save(db, key, o):
    _require_project(db)
    if key.startswith('#'):
        raise EditError('Outdoor places get their light from the weather and time of day. (Regions and weather come later.)')
    c, _refs = editing._cell(db, key)
    hdr = [(t, unb64(d)) for t, d in c['header']]
    out, seen = [], set()
    dens = max(0.0, min(1.0, float(o.get('density', 0.5))))
    ambi = _col(o.get('ambient')) + _col(o.get('sun')) + _col(o.get('fog')) + struct.pack('<f', dens)
    for t, d in hdr:
        if t == 'DATA' and len(d) >= 4:
            f = struct.unpack_from('<i', d)[0] | F_INTERIOR
            f = (f & ~(F_WATER | F_NOSLEEP | F_LIKE_EXT)) | (F_WATER if o.get('water') else 0) | \
                (F_NOSLEEP if o.get('no_sleep') else 0) | (F_LIKE_EXT if o.get('like_exterior') else 0)
            d = struct.pack('<i', f) + bytes(d[4:])
        elif t == 'AMBI':
            d = ambi
        elif t == 'WHGT':
            d = struct.pack('<f', float(o.get('water_height') or 0))
        elif t == 'INTV':
            continue                         # old-style water height: replaced by WHGT below
        out.append((t, d))
        seen.add(t)
    if 'AMBI' not in seen:
        # AMBI goes after DATA (and WHGT)
        at = next((n + 1 for n, (t, _d) in enumerate(out) if t == 'DATA'), len(out))
        out.insert(at, ('AMBI', ambi))
    if 'WHGT' not in seen and o.get('water'):
        at = next((n + 1 for n, (t, _d) in enumerate(out) if t == 'DATA'), len(out))
        out.insert(at, ('WHGT', struct.pack('<f', float(o.get('water_height') or 0))))
    c['header'] = [[t, b64(d)] for t, d in out]
    c['props'] = True
    db.sync_project()
    commit(db, 'Changed the lighting and settings of "%s"' % (read(db, key)['name'] or key))
    return read(db, key)


def presets():
    return [{'name': n, 'ambient': a, 'sun': s, 'fog': f, 'density': d} for n, a, s, f, d in PRESETS]


# ----- lights, for the 3D view
_light_cache = {}


def light_of(db, rid):
    """[r, g, b, radius, flags] of a light (LIGH), or None."""
    low = rid.lower()
    lst = [v for v in db.by_key.get(('LIGH', low), []) if v not in db.dead]
    if not lst:
        return None
    v = lst[-1]
    hit = _light_cache.get(low)
    if hit and hit[0] == v:
        return hit[1]
    r = db.recs[v]
    out = None
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'LHDT' and len(d) >= 24:
            _w, _val, _time, radius = struct.unpack_from('<fiii', d)
            col = list(d[16:19])
            flags = struct.unpack_from('<i', d, 20)[0]
            out = col + [radius, flags]
    _light_cache[low] = (v, out)
    return out
