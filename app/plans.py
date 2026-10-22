"""Floor plans for "Build from pieces": the planner's plan (rooms, shapes, names, floors, doorways, the
way out, stairs and their pins, the style and the build options) saved under a name as a JSON file in
settings/plans under the Workshop home, like prefabs, so a layout can be loaded again, changed and
built once more; and the plan a built place remembers, to start from one of those."""
import json
import os
import re
import time

from editing import EditError
from project import APP_DIR

PLAN_DIR = os.path.join(APP_DIR, 'settings', 'plans')
KEEP = ('rooms', 'doors', 'exit', 'stairs', 'stairPins', 'stairOut', 'stairwell', 'walls', 'join')


def _safe(name):
    return re.sub(r'[^A-Za-z0-9 _\-\',.()]', '', str(name or '')).strip()[:60]


def _path(name):
    return os.path.join(PLAN_DIR, _safe(name) + '.json')


def _summary(plan):
    rooms = plan.get('rooms') or []
    floors = sorted({int(r.get('floor') or 0) for r in rooms})
    tiles = 0
    for r in rooms:
        w, h = int(r.get('w') or 1), int(r.get('h') or 1)
        tiles += w * h - len(r.get('cut') or []) + len(r.get('add') or [])
    return {'rooms': len(rooms), 'floors': len(floors), 'tiles': tiles,
            'names': [str(r.get('name') or '') for r in rooms][:6]}


def list_plans():
    """The saved plans, newest first: [{name, file, saved, style, rooms, floors, tiles, names}]."""
    os.makedirs(PLAN_DIR, exist_ok=True)
    out = []
    for fn in os.listdir(PLAN_DIR):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(PLAN_DIR, fn), encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        plan = d.get('plan') or {}
        if not plan.get('rooms'):
            continue
        out.append(dict(_summary(plan), name=d.get('name') or fn[:-5], file=fn[:-5], saved=d.get('saved', ''),
                        style=d.get('style') or '', options=d.get('options') or {}))
    out.sort(key=lambda p: p['saved'], reverse=True)
    return out


def load_plan(name):
    """A saved plan: {name, saved, style, options, plan}."""
    path = _path(name)
    if not os.path.isfile(path):
        raise EditError('There is no saved plan called "%s".' % name)
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    if not (d.get('plan') or {}).get('rooms'):
        raise EditError('The saved plan "%s" has no rooms in it.' % name)
    return d


def save_plan(name, plan, style=None, options=None):
    """Keep a plan under a name (a plan of that name is replaced)."""
    name = (name or '').strip()
    if not _safe(name):
        raise EditError('Give the plan a name.')
    if not isinstance(plan, dict) or not plan.get('rooms'):
        raise EditError('There is nothing to save: the plan has no rooms.')
    keep = {k: plan[k] for k in KEEP if k in plan}
    os.makedirs(PLAN_DIR, exist_ok=True)
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'plan': keep, 'style': style or '', 'options': options or {},
                   'saved': time.strftime('%Y-%m-%d %H:%M')}, f, indent=1)
    return {'ok': True, 'file': _safe(name)}


def delete_plan(name):
    path = _path(name)
    if os.path.isfile(path):
        os.remove(path)
    return {'ok': True}


def _tz(t):
    """A tile's floor height; plans from before 2.2 (and places merged in from such mods) have only x, y."""
    return t[2] if len(t) > 2 else 0


def built_places(db):
    """Places in your mod built from pieces, newest first: [{key, name, style, rooms, floors, tiles}]."""
    import editing
    if not db.project:
        return []
    out = []
    for key, c in db.project.cells.items():
        plan = c.get('plan') or {}
        if not plan.get('rooms'):
            continue
        rooms = plan['rooms']
        zs = sorted({_tz(t) for r in rooms for t in r.get('tiles', [])})
        out.append({'key': key, 'name': editing.cell_label(db, key), 'style': plan.get('style') or '',
                    'rooms': len(rooms), 'floors': len(zs), 'tiles': sum(len(r.get('tiles', [])) for r in rooms),
                    'names': [r.get('name', '') for r in rooms][:6]})
    return out


def plan_of_cell(db, key):
    """The planner's plan for a built place: the one it was built from, when it remembers it (places
    built since 2.2.7), else its rooms worked out again from the tiles each room has (a rectangle with
    the tiles it lacks taken away; doorways and the way out are then put back by the planner)."""
    c = (db.project.cells if db.project else {}).get(key) or {}
    plan = c.get('plan') or {}
    if not plan.get('rooms'):
        raise EditError('That place wasn\'t built from pieces, so there is no plan to start from.')
    if plan.get('planner') and (plan['planner'].get('rooms') or []):
        return {'plan': plan['planner'], 'style': plan.get('style') or '', 'remembered': True}
    T = float(plan.get('tile') or 256)
    zs = sorted({_tz(t) for r in plan['rooms'] for t in r.get('tiles', [])})
    H = min((b - a for a, b in zip(zs, zs[1:])), default=256.0) or 256.0
    rooms = []
    for n, r in enumerate(plan['rooms']):
        tiles = {(int(round(t[0] / T)), int(round(t[1] / T))) for t in r.get('tiles', [])}
        if not tiles:
            continue
        f = int(round(_tz(r['tiles'][0]) / H))
        xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
        x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        cut = [[x - x0, y - y0] for x in range(x0, x0 + w) for y in range(y0, y0 + h) if (x, y) not in tiles]
        rooms.append({'id': 'p%d' % (n + 1), 'name': r.get('name') or 'Room %d' % (n + 1), 'x': x0, 'y': y0, 'w': w, 'h': h,
                      'floor': max(-2, min(2, f)), 'cut': cut})
    if not rooms:
        raise EditError('That place\'s plan has no rooms left in it.')
    return {'plan': {'rooms': rooms, 'doors': [], 'exit': None, 'stairs': []}, 'style': plan.get('style') or '', 'remembered': False}
