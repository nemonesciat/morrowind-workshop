"""Extend a built place: point at one of its walls, and add a room through it.

The place's own plan (the one Build from pieces keeps on the cell) grows by one room and one doorway; the
builder lays the grown plan in a scratch place, and only the new room's pieces and the doorway tile come
over into the real place, so nothing else in the house moves; the new room is then furnished on its own.
Before anything is laid, the room is shown as a ghost: the kit's own pieces, picked the way the builder
picks them, where they would stand.

    POST /api/extend/options {cell, ref, at: [x, y, z], w, h, shift, name}
         -> {room, side, from, ghost, limits, tile, note}
    POST /api/extend/apply   {cell, ref, at, w, h, shift, name, furnish, level}
         -> {ok, room, placed, note, ...}"""
import copy
import math
import random

import builder
import editing
import fixhere
import fixit
import furnish
import joints
import kits
import mapdata
import plans
from editing import EditError

SIDES = ('N', 'E', 'S', 'W')
STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
MAX = 6


def _names(pl):
    """The planner's room names as the page gives them to the builder: duplicates numbered."""
    out, seen = {}, {}
    for r in pl['rooms']:
        n = (r.get('name') or 'Room').strip()
        k = n.lower()
        seen[k] = seen.get(k, 0) + 1
        out[r['id']] = n if seen[k] == 1 else '%s %d' % (n, seen[k])
    return out


def _layout(pl):
    """A planner plan as the builder takes it (bLayout in planner.js)."""
    N = _names(pl)
    rooms = []
    for r in pl['rooms']:
        d = {'name': N[r['id']], 'x': int(r['x']), 'y': int(r['y']), 'w': int(r['w']), 'h': int(r['h']), 'floor': int(r.get('floor') or 0)}
        if r.get('tall'):
            d['tall'] = True
        if r.get('cut') or r.get('add'):
            d['add'] = [[r['x'] + t[0], r['y'] + t[1]] for t in (r.get('add') or [])]
            d['cut'] = [[r['x'] + t[0], r['y'] + t[1]] for t in (r.get('cut') or [])]
        rooms.append(d)
    doors = []
    for d in pl.get('doors') or []:
        if d.get('a') not in N or d.get('b') not in N:
            continue
        if d.get('kind') == 'open':
            doors.append({'rooms': [N[d['a']], N[d['b']]], 'kind': 'open'})
        else:
            doors.append({'rooms': [N[d['a']], N[d['b']]], 'at': {'x': d['x'], 'y': d['y'], 'side': d['side']}})
    ex = pl.get('exit')
    first = next((r for r in pl['rooms'] if int(r.get('floor') or 0) == 0), pl['rooms'][0])
    exit_ = {'room': N[ex['room']], 'side': ex['side'], 'x': ex['x'], 'y': ex['y']} if ex and ex.get('room') in N else {'room': N[first['id']], 'side': 'S'}
    stairs = []
    for s in pl.get('stairs') or []:
        if s.get('lo') in N and s.get('hi') in N:
            stairs.append({'rooms': [N[s['lo']], N[s['hi']]]})
    return rooms, doors, exit_, stairs, N


def _plan_of(db, cell_key):
    c = (db.project.cells if db.project else {}).get(cell_key)
    plan = (c or {}).get('plan') or {}
    if not plan.get('rooms'):
        raise EditError('Only a place built with "Build from pieces" can be extended this way: it has no room plan.')
    pl = plan.get('planner')
    if not (pl and pl.get('rooms')):
        pl = plans.plan_of_cell(db, cell_key)['plan']
    return plan, pl


def _room_tiles(r):
    cut = {(int(t[0]), int(t[1])) for t in r.get('cut') or []}
    tiles = {(int(r['x']) + i, int(r['y']) + j) for i in range(int(r['w'])) for j in range(int(r['h']))}
    tiles = {(r['x'] + t[0], r['y'] + t[1]) for t in r.get('add') or []} | {t for t in tiles if (t[0] - int(r['x']), t[1] - int(r['y'])) not in cut}
    return tiles


def _spot(db, cell_key, ref, at):
    """The wall pointed at: the tile, the side, the planner room it belongs to, and what is beyond."""
    plan, pl = _plan_of(db, cell_key)
    m = mapdata.cellmap(db, cell_key)
    place = joints.read_place(db, cell_key, m)
    if not place['tiles']:
        raise EditError('This place isn\'t built from a style\'s room pieces.')
    T = place['tiles'][0]['T']
    edges = fixhere._edges_for_ref(place, ref) if ref else fixhere._edge_at(place, *at) if at else []
    if not edges:
        raise EditError('Point at a wall of the place.')
    # the outer walls among the sides pointed at: a wall with no tile beyond it
    cands = []
    for t, s in edges:
        if t['spot'][s] != 'wall':
            continue
        dx, dy = STEP[s]
        if joints.tile_at(place['tiles'], t['x'] + dx * T, t['y'] + dy * T, t['floor']) is not None:
            continue
        ex, ey, ax, ay, ddx, ddy = joints.edge_frame(t, s)
        dist = math.hypot(at[0] - ex, at[1] - ey) if at else 0
        cands.append((dist, t, s))
    if not cands:
        raise EditError('That is not an outer wall: a room can only be added through a wall with nothing behind it.')
    cands.sort(key=lambda c: c[0])
    _d, t, s = cands[0]
    tx, ty = int(round(t['x'] / T)), int(round(t['y'] / T))
    # which planner room holds this tile (the plan's rooms and the planner's are in the same order)
    floor = None
    for n, pr in enumerate(plan['rooms']):
        if any(abs(pt[0] - t['x']) < 24 and abs(pt[1] - t['y']) < 24 and (len(pt) < 3 or abs(pt[2] - t['floor']) < 64) for pt in pr['tiles']):
            if n < len(pl['rooms']):
                floor = int(pl['rooms'][n].get('floor') or 0)
                room = pl['rooms'][n]
            break
    else:
        raise EditError('That wall belongs to no room of the plan.')
    if floor is None:
        raise EditError('That wall belongs to no room of the plan.')
    zf = t['floor']
    return {'plan': plan, 'pl': pl, 'place': place, 'T': T, 'tile': t, 'side': s, 'tx': tx, 'ty': ty, 'room': room, 'floor': floor, 'zf': zf, 'H': t['H']}


def _rect(sp, w, h, shift):
    """The new room's rectangle in planner tiles beyond the wall: x, y, w, h (w along the wall)."""
    s, tx, ty = sp['side'], sp['tx'], sp['ty']
    w, h = max(1, min(MAX, int(w or 3))), max(1, min(MAX, int(h or 3)))
    shift = int(shift or 0)
    if s in ('N', 'S'):
        x0 = tx - (w // 2) + shift
        y0 = ty + 1 if s == 'N' else ty - h
        return x0, y0, w, h
    y0 = ty - (w // 2) + shift
    x0 = tx + 1 if s == 'E' else tx - h
    return x0, y0, h, w


def _clear(pl, floor, rect, exclude=None):
    """Whether the rectangle is free of the plan's rooms on that floor."""
    x0, y0, w, h = rect
    mine = {(x0 + i, y0 + j) for i in range(w) for j in range(h)}
    for r in pl['rooms']:
        if int(r.get('floor') or 0) != floor or r is exclude:
            continue
        if mine & _room_tiles(r):
            return False
    return True


def _ghost(db, sp, rect, name):
    """The kit's pieces where the new room would stand, picked as the builder picks them: [{id, p}]."""
    kp = sp['tile']['kp']
    T, zf = sp['T'], sp['zf']
    x0, y0, w, h = rect
    tiles = {(x0 + i, y0 + j) for i in range(w) for j in range(h)}
    s_in = OPP[sp['side']]                                # the new room's side that faces the old room
    door_tile = (sp['tx'] + STEP[sp['side']][0], sp['ty'] + STEP[sp['side']][1])
    out = []
    for (gx, gy) in sorted(tiles):
        need = {}
        for s in SIDES:
            nb = (gx + STEP[s][0], gy + STEP[s][1])
            need[s] = 'open' if nb in tiles else 'wall'
        if (gx, gy) == door_tile:
            need[s_in] = 'door'
        need['_top'] = False
        piece, q, missing, pat = builder._pick(kp, need)
        if not piece:
            continue
        out.append({'id': piece['id'], 'p': [gx * T, gy * T, zf - piece['zmin'], 0, 0, q * math.pi / 2]})
    # the old room's tile gets a doorway on the shared side
    t = sp['tile']
    need = {s: t['spot'][s] for s in SIDES}
    need[sp['side']] = 'door'
    need['_top'] = False
    piece, q, missing, pat = builder._pick(kp, need)
    if piece:
        out.append({'id': piece['id'], 'p': [t['x'], t['y'], zf - piece['zmin'], 0, 0, q * math.pi / 2], 'swap': t['ref']})
    return out


def options(db, cell_key, ref=None, at=None, w=3, h=3, shift=0, name=None):
    sp = _spot(db, cell_key, ref, at)
    rect = _rect(sp, w, h, shift)
    fits = _clear(sp['pl'], sp['floor'], rect)
    # (a rectangle that runs into another room: shrink its depth until it is clear, so the first offer fits)
    tried = rect
    depth_key = 3 if sp['side'] in ('N', 'S') else 2
    while not fits and tried[depth_key] > 1:
        tried = list(tried)
        if sp['side'] == 'S':
            tried[1] += 1
        if sp['side'] == 'W':
            tried[0] += 1
        tried[depth_key] -= 1
        tried = tuple(tried)
        fits = _clear(sp['pl'], sp['floor'], tried)
    if fits and tried != rect:
        rect = tried
    name = (name or '').strip() or 'New room'
    ghost = _ghost(db, sp, rect, name) if fits else []
    x0, y0, rw, rh = rect
    return {'room': {'x': x0, 'y': y0, 'w': rw, 'h': rh, 'floor': sp['floor'], 'name': name},
            'side': sp['side'], 'from': sp['room'].get('name') or 'the room', 'tile': [sp['tx'], sp['ty']],
            'T': sp['T'], 'zf': sp['zf'], 'fits': fits, 'ghost': ghost, 'style': kits.friendly(sp['plan'].get('style') or ''),
            'note': None if fits else 'There is another room in the way beyond this wall.'}


def apply(db, cell_key, ref=None, at=None, w=3, h=3, shift=0, name=None, furnish_it=True, level=None, purpose=None):
    """Grow the plan, lay the new room and its doorway, furnish it: {'ok', 'room', 'placed', 'furnished'}."""
    editing._require_project(db)
    p = db.project
    sp = _spot(db, cell_key, ref, at)
    o = options(db, cell_key, ref, at, w, h, shift, name)
    if not o['fits']:
        raise EditError(o['note'])
    rect = (o['room']['x'], o['room']['y'], o['room']['w'], o['room']['h'])
    name = o['room']['name']
    plan, pl = sp['plan'], copy.deepcopy(sp['pl'])
    if any((r.get('name') or '').strip().lower() == name.lower() for r in pl['rooms']):
        name = '%s %d' % (name, sum(1 for r in pl['rooms'] if (r.get('name') or '').strip().lower().startswith(name.lower())) + 1)
    new_id = 'x%d' % random.randrange(1 << 24)
    pl['rooms'].append({'id': new_id, 'name': name, 'x': rect[0], 'y': rect[1], 'w': rect[2], 'h': rect[3], 'floor': sp['floor']})
    pl.setdefault('doors', []).append({'a': sp['room']['id'], 'b': new_id, 'kind': 'door', 'x': sp['tx'], 'y': sp['ty'], 'side': sp['side']})
    rooms, doors, exit_, stairs, N = _layout(pl)
    style = plan.get('style')
    if plan.get('dressing'):
        style = '%s@%s' % (style, plan['dressing'])
    # the grown plan laid in a scratch place (no lights: the house keeps its own)
    base = (mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key
    tmp = '%s (extending %d)' % (base[:40], random.randrange(1 << 20))
    tmp_key = tmp.lower()
    p.cells.pop(tmp_key, None)
    out = builder.build_interior(db, tmp, style, rooms, doors, exit_, None, 'normal', False, None, stairs, commit=False, planner=pl)
    tmp_key = out['key']
    tc = p.cells.get(tmp_key)
    if not tc:
        raise EditError('The builder laid nothing.')
    T, zf, H = sp['T'], sp['zf'], sp['H']
    x0, y0, rw, rh = rect
    new_tiles = {((x0 + i) * T, (y0 + j) * T) for i in range(rw) for j in range(rh)}
    seam = (sp['tx'] * T, sp['ty'] * T)
    take = new_tiles | {seam}

    def on_tiles(x, y, z):
        if not (zf - 40 <= z <= zf + H * 1.6):
            return False
        return any(abs(x - cx) <= T / 2 + 1 and abs(y - cy) <= T / 2 + 1 for cx, cy in take)
    from project import ref_info, unb64
    ops = []
    for rk, r in tc['refs'].items():
        if r.get('deleted'):
            continue
        rid, pos, scale, dead = ref_info([(t_, unb64(d_)) for t_, d_ in r['subs']])
        if dead or not on_tiles(pos[0], pos[1], pos[2]):
            continue
        op = {'op': 'place', 'id': rid, 'p': [round(v, 3) for v in pos[:6]]}
        if abs(scale - 1) > 0.001:
            op['s'] = scale
        ops.append(op)
    # the old pieces on the seam tile go (the wall becomes the doorway piece); furniture there stays
    m = mapdata.cellmap(db, cell_key)
    for r in m['refs']:
        if not r.get('arch'):
            continue
        x, y, z = r['p'][0], r['p'][1], r['p'][2]
        if abs(x - seam[0]) <= T / 2 + 1 and abs(y - seam[1]) <= T / 2 + 1 and zf - 40 <= z <= zf + H * 1.6:
            ops.append({'op': 'delete', 'ref': r['k']})
    new_plan_room = next((pr for pr in (tc.get('plan') or {}).get('rooms', []) if pr.get('name') == N[new_id]), None)
    p.cells.pop(tmp_key, None)
    for k_ in [k_ for k_ in p.cells if '(extending ' in k_]:
        p.cells.pop(k_, None)                     # (a scratch place left by an earlier try)
    if not any(op['op'] == 'place' for op in ops):
        raise EditError('The builder laid nothing for the new room.')
    fixit.apply(db, cell_key, ops, None, commit=False)
    # the place's plan grows: the room with its tiles for Auto-furnish, the planner's plan to start from again
    if new_plan_room:
        plan['rooms'].append(new_plan_room)
    else:
        plan['rooms'].append({'name': N[new_id], 'purpose': furnish.purpose_for(N[new_id], rw * rh, rw, rh),
                              'tiles': [[cx, cy, zf] for cx, cy in sorted(new_tiles)]})
    plan['planner'] = pl
    n_pieces = sum(1 for op in ops if op['op'] == 'place')
    editing.commit(db, 'Added the %s through the %s\'s %s wall (%d pieces)' % (
        N[new_id], sp['room'].get('name') or 'room', {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}[sp['side']], n_pieces))
    result = {'ok': True, 'room': N[new_id], 'pieces': n_pieces, 'placed': 0, 'furnished': False}
    if furnish_it:
        try:
            fr = furnish.furnish(db, cell_key, room=len(plan['rooms']) - 1, purpose=purpose or None, level=level or None,
                                 replace=False, seed=random.randrange(1 << 30))
            result['placed'] = fr.get('placed', 0)
            result['furnished'] = True
        except EditError as e:
            result['note'] = 'Built, but could not furnish it: %s' % e
    return result
