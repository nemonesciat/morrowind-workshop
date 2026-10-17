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


def move(db, moves):
    """moves: [{cell, ref, p: [x, y, z, rx, ry, rz], s?}]."""
    editing._require_project(db)
    if not moves:
        raise EditError('Nothing to move.')
    cells = set()
    for mv in moves:
        c, refs = _cell(db, mv['cell'])
        ref = refs.get(mv['ref'])
        if not ref:
            continue
        p = [float(v) for v in mv['p'][:6]]
        _store(c, mv['ref'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], tuple(p), mv.get('s')))
        cells.add(mv['cell'])
    commit(db, 'Moved %d objects in %s' % (len(moves), ', '.join(sorted(cell_label(db, k) for k in cells))))
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


def place(db, cell_hint, items, x, y, z=None, yaw=0.0, label=None):
    """Put a group down with its middle at (x, y). items: [{id, dx, dy, dz, rx, ry, rz, s}] relative to the
    group's middle and its lowest point. z None: set the group down on the floor or ground there.
    yaw turns the whole group (clockwise, like the game)."""
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
    for it in items:
        ri = db.resolve_id(it['id'])
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
    return [{'id': r['id'], 'name': r['name'], 'type': r['type'], 'dx': round(r['p'][0] - cx, 2), 'dy': round(r['p'][1] - cy, 2),
             'dz': round(r['p'][2] - cz, 2), 'rx': r['p'][3], 'ry': r['p'][4], 'rz': r['p'][5], 's': r['s'] or 1.0,
             'b': r['b']} for r in rows]


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
    keep = [{k: it[k] for k in ('id', 'name', 'type', 'dx', 'dy', 'dz', 'rx', 'ry', 'rz', 's', 'b') if k in it} for it in items]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'items': keep, 'saved': time.strftime('%Y-%m-%d %H:%M'), 'from': source}, f, indent=1)
    return {'ok': True, 'file': _safe(name)}


def delete_prefab(name):
    path = os.path.join(PREFAB_DIR, _safe(name) + '.json')
    if os.path.isfile(path):
        os.remove(path)
    return {'ok': True}
