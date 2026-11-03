"""Groups of objects: move, delete or place several at once (one change each), and prefabs:
groups saved to reuse anywhere ("market stall", "alchemist's corner"...)."""
import json
import math
import os
import re
import time

import editing
import mapdata
from editing import EditError, PLACEABLE, _cell, _store, commit, cell_label
from project import APP_DIR, ref_info, set_ref_pos, zs

PREFAB_DIR = os.path.join(APP_DIR, 'prefabs')
CELL = 8192


def _place_key(db, hint, x, y):
    """The cell an object at (x, y) belongs in: outdoors by position, else the place given."""
    if hint and hint.startswith('#'):
        return '#%d,%d' % (math.floor(x / CELL), math.floor(y / CELL))
    return hint


JOIN_GAP = 12                  # (two pieces this close every way are joined, for a building the Workshop has no record of)
JOIN_REACH = 2500              # (and never further than this from the piece clicked)


def building(db, cell_key, refkey):
    """The whole building a piece belongs to: [{cell, ref}] and how it was found. A town's building by the record its
    Make it kept (project.town_parts); any other, the building pieces and doors joined to it through pieces touching
    one another, within JOIN_REACH. Moving a town's building took the user 130 single moves in a morning, 2026-11-01:
    "I seem to be unable to grab every single piece"."""
    parts = getattr(db.project, 'town_parts', None) or {}
    gid = parts.get(refkey)
    if gid:
        out = []
        for ck, c in db.project.cells.items():
            for rk, ref in (c.get('refs') or {}).items():
                if parts.get(rk) == gid and not ref.get('deleted'):
                    out.append({'cell': ck, 'ref': rk})
        if out:
            return {'refs': out, 'how': 'built'}
    m = mapdata.cellmap(db, cell_key)
    r0 = next((r for r in m.get('refs') or () if r['k'] == refkey), None)
    if r0 is None:
        raise EditError('That piece is no longer there.')
    keys = [cell_key]
    if cell_key.startswith('#'):
        gx, gy = (int(v) for v in cell_key[1:].split(','))
        keys = ['#%d,%d' % (gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    cand = []
    for ck in keys:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r.get('b') and (r.get('arch') or r['type'] == 'DOOR') and math.hypot(r['p'][0] - r0['p'][0], r['p'][1] - r0['p'][1]) <= JOIN_REACH:
                cand.append((ck, r, _box3(r)))
    i0 = next((i for i, c_ in enumerate(cand) if c_[1]['k'] == refkey and c_[0] == cell_key), None)
    if i0 is None:
        return {'refs': [{'cell': cell_key, 'ref': refkey}], 'how': 'alone'}
    near = lambda a, b: all(a[i] - JOIN_GAP <= b[i + 3] and b[i] - JOIN_GAP <= a[i + 3] for i in range(3))
    seen, todo = {i0}, [i0]
    while todo:
        k = todo.pop()
        for j, c_ in enumerate(cand):
            if j not in seen and near(cand[k][2], c_[2]):
                seen.add(j)
                todo.append(j)
    return {'refs': [{'cell': cand[j][0], 'ref': cand[j][1]['k']} for j in sorted(seen)], 'how': 'joined'}


def _box3(r):
    b, s = r['b'], r['s'] or 1.0
    c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
    xs = [r['p'][0] + (bx * c + by * sn) * s for bx in (b[0], b[3]) for by in (b[1], b[4])]
    ys = [r['p'][1] + (-bx * sn + by * c) * s for bx in (b[0], b[3]) for by in (b[1], b[4])]
    return (min(xs), min(ys), r['p'][2] + b[2] * s, max(xs), max(ys), r['p'][2] + b[5] * s)


def move(db, moves):
    """moves: [{cell, ref, p: [x, y, z, rx, ry, rz], s?}]. A moved outdoor door's interior way out follows it
    (doors.follow), in the same step."""
    editing._require_project(db)
    if not moves:
        raise EditError('Nothing to move.')
    import doors
    was = doors.door_spots(db, [(mv['cell'], mv['ref']) for mv in moves])
    cells = set()
    for mv in moves:
        c, refs = _cell(db, mv['cell'])
        ref = refs.get(mv['ref'])
        if not ref:
            continue
        p = [float(v) for v in mv['p'][:6]]
        _store(c, mv['ref'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], tuple(p), mv.get('s')))
        cells.add(mv['cell'])
    note = 'Moved %d objects in %s' % (len(moves), ', '.join(sorted(cell_label(db, k) for k in cells)))
    commit(db, note)
    if was and doors.follow(db, was):
        editing.fold(db, 2, note)
    return {'cells': sorted(cells)}


def delete(db, refs):
    """refs: [{cell, ref}]."""
    editing._require_project(db)
    cells, n = set(), 0
    for item in refs:
        c, all_refs = _cell(db, item['cell'])
        ref = all_refs.get(item['ref'])
        if not ref:
            continue
        if ref['origin'] == db.project.plugin.lower():
            c['refs'].pop(item['ref'], None)
        else:
            _store(c, item['ref'], ref['origin'], ref['idx'], ref['subs'], deleted=True)
        cells.add(item['cell'])
        n += 1
    for k in cells:
        editing._drop_empty(db, k)
    if not n:
        raise EditError('Nothing to remove.')
    commit(db, 'Removed %d objects from %s' % (n, ', '.join(sorted(cell_label(db, k) for k in cells))))
    return {'cells': sorted(cells)}


def swap(db, refs, new_id):
    """Replace several placed objects with another one (search and replace), in one change.
    refs: [{cell, ref}]. Each keeps its spot, turn, scale (and where a door leads)."""
    editing._require_project(db)
    ri = db.resolve_id(new_id or '')
    if ri is None:
        raise EditError('No object called "%s".' % new_id)
    if db.recs[ri][0] not in PLACEABLE:
        raise EditError('"%s" can\'t be placed in the world.' % new_id)
    cells, n, olds = set(), 0, set()
    for item in refs:
        c, all_refs = _cell(db, item['cell'])
        ref = all_refs.get(item['ref'])
        if not ref:
            continue
        olds.add(ref_info(ref['subs'])[0])
        subs = [(t, zs(db.recs[ri][1]) if t == 'NAME' else d) for t, d in ref['subs']]
        if db.recs[ri][0] != 'DOOR':
            subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
        _store(c, item['ref'], ref['origin'], ref['idx'], subs)
        cells.add(item['cell'])
        n += 1
    if not n:
        raise EditError('Nothing to replace.')
    commit(db, 'Replaced %d object%s (%s) with "%s" in %s' % (n, '' if n == 1 else 's', ', '.join(sorted(olds))[:80],
                                                              db.recs[ri][1], ', '.join(sorted(cell_label(db, k) for k in cells))))
    return {'cells': sorted(cells), 'n': n}


def restore(db, refs):
    """Bring several objects back as they were before your mod (moved back, or not removed after all)."""
    editing._require_project(db)
    cells = set()
    for item in refs:
        c = db.project.cells.get(item['cell'])
        if c and c['refs'].pop(item['ref'], None) is not None:
            cells.add(item['cell'])
    for k in cells:
        editing._drop_empty(db, k)
    if not cells:
        raise EditError('Nothing to bring back.')
    commit(db, 'Brought back %d object%s in %s' % (len(refs), '' if len(refs) == 1 else 's',
                                                   ', '.join(sorted(cell_label(db, k) for k in cells))))
    return {'cells': sorted(cells)}


def place(db, cell_hint, items, x, y, z=None, yaw=0.0, label=None, scattered=False):
    """Put a group down with its middle at (x, y). items: [{id, dx, dy, dz, rx, ry, rz, s}] relative to the
    group's middle and its lowest point. z None: set the group down on the floor or ground there.
    yaw turns the whole group (clockwise, like the game). scattered: the Scatter brush's, marked so its Remove
    takes out only what it placed."""
    editing._require_project(db)
    if not items:
        raise EditError('The group is empty.')
    x, y = float(x), float(y)
    if z is None:
        key0 = _place_key(db, cell_hint, x, y)
        m = mapdata.cellmap(db, key0)
        if not m.get('exists'):
            raise EditError('There is no place there to put it.')
        z = mapdata.surface_z(db, m['refs'], m['interior'], x, y, None, 1.0, 'STAT', None)
    z = float(z)
    c_, s_ = math.cos(yaw), math.sin(yaw)
    placed, cells = [], set()
    mine = db.project.plugin.lower()
    import library
    for it in items:
        # (your own Library models: their record is made in this mod when it doesn't have one yet)
        rid = library.resolve(db, it['id'], it.get('lib'), it.get('type'))
        ri = db.resolve_id(rid) if rid else None
        if ri is None or db.recs[ri][0] not in PLACEABLE:
            continue
        dx, dy = float(it.get('dx', 0)), float(it.get('dy', 0))
        wx, wy = x + dx * c_ + dy * s_, y - dx * s_ + dy * c_          # the game turns things clockwise
        key = _place_key(db, cell_hint, wx, wy)
        c, _refs = _cell(db, key)
        rk = db.project.new_ref_key()
        pos = (wx, wy, z + float(it.get('dz', 0)), float(it.get('rx', 0)), float(it.get('ry', 0)),
               (float(it.get('rz', 0)) + yaw) % (2 * math.pi))
        _store(c, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], pos, float(it.get('s', 1.0) or 1.0)))
        placed.append({'cell': key, 'ref': rk})
        cells.add(key)
    if not placed:
        raise EditError('None of these objects exist in your load order.')
    if scattered:
        db.project.scattered.update(p['ref'] for p in placed)
    commit(db, 'Placed %s (%d objects) in %s' % (('"%s"' % label) if label else 'a group', len(placed),
                                                  ', '.join(sorted(cell_label(db, k) for k in cells))))
    return {'placed': placed, 'cells': sorted(cells)}


def from_refs(db, refs):
    """A group (prefab form) from objects in the world: [{cell, ref}] -> items relative to their middle."""
    rows = []
    for item in refs:
        m = mapdata.cellmap(db, item['cell'])
        r = next((x for x in m['refs'] if x['k'] == item['ref']), None)
        if r:
            rows.append(r)
    if not rows:
        raise EditError('Nothing selected.')
    xs = [r['p'][0] for r in rows]
    ys = [r['p'][1] for r in rows]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    bottoms = [r['p'][2] + ((r['b'] or [0, 0, 0])[2]) * (r['s'] or 1) for r in rows]
    cz = min(bottoms)
    import library
    out = []
    for r in rows:
        it = {'id': r['id'], 'name': r['name'], 'type': r['type'], 'dx': round(r['p'][0] - cx, 2), 'dy': round(r['p'][1] - cy, 2),
              'dz': round(r['p'][2] - cz, 2), 'rx': r['p'][3], 'ry': r['p'][4], 'rz': r['p'][5], 's': r['s'] or 1.0, 'b': r['b']}
        e = library.entry_for_record(r['id'], db)
        if e:
            it['lib'] = e['id']                 # (one of your own models: it travels with the prefab)
        out.append(it)
    return out


# ------------------------------------------------------------------ prefabs
def _safe(name):
    return re.sub(r'[^A-Za-z0-9 _\-]', '', name).strip()[:60]


def prefabs():
    os.makedirs(PREFAB_DIR, exist_ok=True)
    out = []
    for fn in sorted(os.listdir(PREFAB_DIR)):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(PREFAB_DIR, fn), encoding='utf-8') as f:
                d = json.load(f)
            out.append({'name': d.get('name') or fn[:-5], 'file': fn[:-5], 'items': d.get('items', []),
                        'saved': d.get('saved', ''), 'from': d.get('from', '')})
        except (OSError, ValueError):
            continue
    return out


def save_prefab(db, name, items, source=''):
    name = (name or '').strip()
    if not _safe(name):
        raise EditError('Give the prefab a name.')
    if not items:
        raise EditError('Select some objects first.')
    os.makedirs(PREFAB_DIR, exist_ok=True)
    path = os.path.join(PREFAB_DIR, _safe(name) + '.json')
    keep = [{k: it[k] for k in ('id', 'name', 'type', 'dx', 'dy', 'dz', 'rx', 'ry', 'rz', 's', 'b', 'lib') if k in it} for it in items]
    from project import write_json
    write_json(path, {'name': name, 'items': keep, 'saved': time.strftime('%Y-%m-%d %H:%M'), 'from': source}, indent=1)
    return {'ok': True, 'file': _safe(name)}


def delete_prefab(name):
    path = os.path.join(PREFAB_DIR, _safe(name) + '.json')
    if os.path.isfile(path):
        os.remove(path)
    return {'ok': True}
