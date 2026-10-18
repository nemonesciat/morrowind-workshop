"""What grows and lies around outdoors in a region, for the scatter brush: grass, flowers and
plants, rocks, bushes and trees, with how often each one appears, the sizes the game uses and how
deep each is sunk into the ground. All learnt from the cells of the same region."""
import json
import os
import uuid

import mapdata
import regions
from project import APP_DIR, ref_info

SETS = [  # (key, label, words in the id, words that rule it out)
    ('grass', 'Grass', ('grass', 'kelp', 'reed', 'fern', 'heather', 'bracken', 'weed'), ('tree', 'rock')),
    ('plants', 'Flowers & plants', ('flora_', 'flower', 'plant', 'bush', 'shrub', 'ivy', 'mushroom', 'fung', 'lichen', 'marsh'),
     ('tree', 'grass', 'rock', 'log', 'stump', 'root', 'kelp')),
    ('rocks', 'Rocks & stones', ('rock', 'stone', 'boulder', 'pebble'), ('road', 'wall', 'bridge', 'arch', 'cave', 'entr', 'cliff', 'menhir')),
    ('trees', 'Trees', ('tree',), ('treehouse', 'root')),
    ('logs', 'Logs & stumps', ('log', 'stump', 'driftwood', 'deadwood'), ('logo',)),
]
_cache = {}


def _kind(low):
    for key, _label, words, nots in SETS:
        if any(w in low for w in words) and not any(w in low for w in nots):
            return key
    return None


def sets(db, cell_key, sample=36):
    """{'region', 'sets': [{key, label, items: [{id, name, n, smin, smax, sink, size}]}]} for the
    region an outdoor cell is in (or the cells around it, when it has none)."""
    if not cell_key.startswith('#'):
        return {'region': '', 'sets': custom_sets(db)}
    gx, gy = (int(v) for v in cell_key[1:].split(','))
    rmap = regions.region_map(db)
    reg = rmap.get('%d,%d' % (gx, gy), '')
    stamp = (reg or cell_key, id(db.recs), len(db.recs))
    if stamp in _cache:
        return dict(_cache[stamp], sets=_cache[stamp]['sets'] + custom_sets(db))
    # cells of the same region, nearest first (or simply the nearest cells)
    cand = [tuple(int(v) for v in k.split(',')) for k, r in rmap.items() if r == reg] if reg else []
    if not cand:
        cand = [(gx + dx, gy + dy) for dx in range(-3, 4) for dy in range(-3, 4)]
    cand.sort(key=lambda c: (c[0] - gx) ** 2 + (c[1] - gy) ** 2)
    stats, bmemo = {}, {}
    for cx, cy in cand[:sample]:
        key = '#%d,%d' % (cx, cy)
        if not db.by_key.get(('CELL', key)):
            continue
        refs, _h = db.cell_refs(key)
        for ref in refs.values():
            rid, pos, s, dead = ref_info(ref['subs'])
            if dead:
                continue
            low = rid.lower()
            k = _kind(low)
            if not k or any(w in low for w in ('kelp', 'lily', 'coral', 'seaweed', 'cave_')):
                continue                          # water plants float, cave plants belong in caves
            if low not in bmemo:
                ri = db.resolve_id(rid)
                bmemo[low] = (mapdata.object_bounds(db, ri), db.recs[ri][0], db.recs[ri][1], db.recs[ri][2]) if ri is not None else None
            info = bmemo[low]
            if not info or not info[0] or info[1] not in ('STAT', 'CONT', 'ACTI'):
                continue
            b = info[0]
            st = stats.setdefault(low, {'id': info[2], 'name': info[3] or '', 'kind': k, 'n': 0, 'scales': [], 'sinks': [], 'zmin': b[2],
                                        'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])]})
            st['n'] += 1
            s = s or 1.0
            if len(st['scales']) < 40:
                st['scales'].append(s)
                g = mapdata.terrain_z(db, pos[0], pos[1])
                if g is not None:
                    st['sinks'].append((g - (pos[2] + b[2] * s)) / s)      # how far its bottom is below the ground
    out = []
    for key, label, _w, _n in SETS:
        rows = [v for v in stats.values() if v['kind'] == key and v['n'] >= 2]
        rows.sort(key=lambda v: -v['n'])
        items = []
        for v in rows[:14]:
            sc = sorted(v['scales'])
            sk = sorted(v['sinks'])
            items.append({'id': v['id'], 'name': v['name'], 'n': v['n'], 'smin': round(sc[len(sc) // 10], 2),
                          'smax': round(sc[min(len(sc) - 1, len(sc) * 9 // 10)], 2),
                          # never sunk deeper than most of its height, nor floating
                          'sink': round(max(0.0, min(sk[len(sk) // 2], v['size'][2] * 0.6)), 1) if sk else 0.0,
                          'size': v['size'], 'zmin': round(v['zmin'], 1)})
        if items:
            out.append({'key': key, 'label': label, 'items': items})
    res = {'region': reg, 'sets': out}
    _cache[stamp] = res
    return dict(res, sets=out + custom_sets(db))


# ------------------------------------------------------------------ your own brushes
# Brushes you make yourself: any objects (from mods too), each with how often it comes up and its sizes.
# Kept beside the Workshop's settings so they work in every mod, and can be shared as a small file.
BRUSH_FILE = os.path.join(APP_DIR, 'brushes.json')
_item_cache = {}


def load_brushes():
    try:
        with open(BRUSH_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return [b for b in data.get('brushes', []) if isinstance(b, dict) and b.get('id')]
    except (OSError, ValueError):
        return []


def _save_brushes(brushes):
    tmp = BRUSH_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'brushes': brushes}, f, indent=1)
    os.replace(tmp, BRUSH_FILE)


def _clean(db, b):
    """A brush as given by the page (or a shared file), checked: known objects only, sane numbers."""
    name = str(b.get('name') or 'My brush').strip()[:40] or 'My brush'
    items, seen = [], set()
    for it in b.get('items') or []:
        rid = str(it.get('id') or '').strip()
        if not rid or rid.lower() in seen:
            continue
        ri = db.resolve_id(rid)
        if ri is None or db.recs[ri][0] not in ('STAT', 'ACTI', 'CONT', 'LIGH', 'MISC', 'INGR', 'ALCH', 'APPA', 'BOOK', 'CLOT', 'ARMO', 'WEAP'):
            continue
        seen.add(rid.lower())
        d = item_defaults(db, rid)
        num = lambda k, lo, hi, dflt: max(lo, min(hi, float(it[k]))) if isinstance(it.get(k), (int, float)) else dflt
        smin = num('smin', 0.5, 2.0, d['smin'])
        smax = max(smin, num('smax', 0.5, 2.0, d['smax']))
        items.append(dict(d, id=db.recs[ri][1], weight=num('weight', 0.1, 10, 1.0), smin=round(smin, 2), smax=round(smax, 2),
                          sink=round(num('sink', 0, 500, d['sink']), 1)))
    return {'id': str(b.get('id') or uuid.uuid4().hex[:8])[:16], 'name': name, 'items': items}


def item_defaults(db, rid):
    """Starting values for an object on a brush, from how the game itself uses it outdoors: its usual
    sizes and how deep its bottom is sunk into the ground. Plain values when it is never used outdoors."""
    low = rid.lower()
    if low in _item_cache and _item_cache[low][0] is db.recs:
        return dict(_item_cache[low][1])
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    b = b or [-20, -20, 0, 20, 20, 40]
    scales, sinks = [], []
    for ci in list(db.used_in.get(low, ()))[:40]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not r[7].startswith('#'):
            continue
        refs, _h = db.cell_refs(r[7])
        for ref in refs.values():
            rid2, pos, s, dead = ref_info(ref['subs'])
            if dead or rid2.lower() != low:
                continue
            s = s or 1.0
            scales.append(s)
            g = mapdata.terrain_z(db, pos[0], pos[1])
            if g is not None:
                sinks.append((g - (pos[2] + b[2] * s)) / s)
            if len(scales) >= 60:
                break
    scales.sort()
    sinks.sort()
    out = {'name': db.recs[ri][2] if ri is not None else '', 'n': len(scales),
           'smin': round(scales[len(scales) // 10], 2) if scales else 0.9,
           'smax': round(scales[min(len(scales) - 1, len(scales) * 9 // 10)], 2) if scales else 1.1,
           'sink': round(max(0.0, min(sinks[len(sinks) // 2], (b[5] - b[2]) * 0.6)), 1) if sinks else 0.0,
           'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])], 'zmin': round(b[2], 1)}
    _item_cache[low] = (db.recs, out)
    return dict(out)


def custom_sets(db):
    """Your brushes, in the same shape as the region's sets (key 'my:<id>')."""
    out = []
    for b in load_brushes():
        b = _clean(db, b)
        items = [dict(it, n=max(1, round(it['weight'] * 10))) for it in b['items']]
        out.append({'key': 'my:' + b['id'], 'label': b['name'], 'mine': True, 'items': items,
                    # (how far apart things go: by their size)
                    'gap': round(max(120, min(700, sum(max(i['size'][0], i['size'][1]) for i in items) / max(1, len(items)) * 3)))})
    return out


def save_brush(db, brush):
    """Add or change one of your brushes. Returns it as saved."""
    b = _clean(db, brush)
    have = load_brushes()
    old = next((i for i, x in enumerate(have) if x['id'] == b['id']), None)
    lst = [x for x in have if x['id'] != b['id']]
    lst.insert(old if old is not None else len(lst), b)
    _save_brushes(lst)
    return b


def delete_brush(brush_id):
    _save_brushes([x for x in load_brushes() if x['id'] != brush_id])


def import_brushes(db, data):
    """Brushes from a shared file: added beside yours (renamed if a name is taken). Objects your load
    order doesn't have are left out. Returns (brushes added, objects left out)."""
    have = load_brushes()
    names = {x['name'].lower() for x in have}
    added = skipped = 0
    for b in (data or {}).get('brushes', []):
        before = len(b.get('items') or [])
        c = _clean(db, dict(b, id=uuid.uuid4().hex[:8]))
        skipped += before - len(c['items'])
        if not c['items']:
            continue
        base, n = c['name'], 2
        while c['name'].lower() in names:
            c['name'] = '%s (%d)' % (base, n)
            n += 1
        names.add(c['name'].lower())
        have.append(c)
        added += 1
    _save_brushes(have)
    return added, skipped
