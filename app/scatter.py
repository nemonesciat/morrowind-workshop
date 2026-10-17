"""What grows and lies around outdoors in a region, for the scatter brush: grass, flowers and
plants, rocks, bushes and trees, with how often each one appears, the sizes the game uses and how
deep each is sunk into the ground. All learnt from the cells of the same region."""
import mapdata
import regions
from project import ref_info

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
        return {'region': '', 'sets': []}
    gx, gy = (int(v) for v in cell_key[1:].split(','))
    rmap = regions.region_map(db)
    reg = rmap.get('%d,%d' % (gx, gy), '')
    stamp = (reg or cell_key, id(db.recs), len(db.recs))
    if stamp in _cache:
        return _cache[stamp]
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
    return res
