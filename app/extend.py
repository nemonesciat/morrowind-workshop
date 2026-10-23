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
from collections import Counter

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
    # the two ends of the doorway: the seam tile's corners on the seam edge, where the game stands a post
    # over the join of the door jamb and the wall (fixit.missing_posts, 'frame')
    ex_, ey_, ax_, ay_, _dx, _dy = joints.edge_frame(sp['tile'], sp['side'])
    jamb_ends = [(ex_ + ax_ * k * T / 2.0, ey_ + ay_ * k * T / 2.0) for k in (-1, 1)]
    posty = joints.POSTY

    # (one storey only: the band reached up to the storey above before, and took its piece on the seam tile
    # with it, 2026-10-22)
    def on_tiles(x, y, z):
        if not (zf - 40 <= z < zf + H - 40):
            return False
        return any(abs(x - cx) <= T / 2 + 1 and abs(y - cy) <= T / 2 + 1 for cx, cy in take)

    def at_jamb_end(x, y, z):
        return zf - 40 <= z < zf + H - 40 and any(math.hypot(x - jx, y - jy) < 60 for jx, jy in jamb_ends)
    from project import ref_info, unb64
    m = mapdata.cellmap(db, cell_key)
    # the loose pieces on the seam edge itself go with the wall (the old outer wall's loose wall, its addon),
    # but not the posts at its two ends: those are the doorway's own, the game's post over each jamb end
    # (taking them out and then skipping the scratch build's as "there already" left both ends bare on the
    # user's Gold Coast shop, 2026-10-22: the "missing beams on both sides of the doorway")
    t0 = sp['tile']
    seam_dels = [L['ref'] for L, u, d, dz, dq, label in joints.loose_on(sp['place'], t0, sp['side'], joints.family(t0['kit']))
                 if not posty.search(L['id'])]
    ops = []
    for rk, r in tc['refs'].items():
        if r.get('deleted'):
            continue
        rid, pos, scale, dead = ref_info([(t_, unb64(d_)) for t_, d_ in r['subs']])
        if dead:
            continue
        # (a post at a jamb end counts whichever tile its point falls on: the corner is shared with the
        # tile beside the doorway)
        if not on_tiles(pos[0], pos[1], pos[2]) and not (posty.search(rid.lower()) and at_jamb_end(pos[0], pos[1], pos[2])):
            continue
        # (a post the scratch build stands where the house has one already, and that one stays: the house's)
        if any(x['id'].lower() == rid.lower() and x['k'] not in seam_dels and abs(x['p'][0] - pos[0]) < 24 and abs(x['p'][1] - pos[1]) < 24
               and abs(x['p'][2] - pos[2]) < 24 and abs(x['p'][5] - pos[5]) < 0.05 for x in m['refs']):
            continue
        op = {'op': 'place', 'id': rid, 'p': [round(v, 3) for v in pos[:6]]}
        if abs(scale - 1) > 0.001:
            op['s'] = scale
        ops.append(op)
    # the old tile piece on the seam tile becomes the doorway piece (a swap, so the piece keeps its key and
    # "Remove this room" gives the house back as it was), with the loose pieces on the seam edge itself
    # taken out; the posts at the tile's corners, and the furniture, stay
    tile_ids = {x['id'].lower() for x in t0['kp']['pieces']} | {x['id'].lower() for x in t0['kp'].get('tall') or []}
    swapped = False
    for op in ops:
        if op['op'] == 'place' and op['id'].lower() in tile_ids and abs(op['p'][0] - seam[0]) < 24 and abs(op['p'][1] - seam[1]) < 24 and not swapped:
            op.update({'op': 'swap', 'ref': t0['ref'], 'rz': op['p'][5]})
            swapped = True
    for rk in ([] if swapped else [t0['ref']]) + list(t0.get('mates') or []):
        ops.append({'op': 'delete', 'ref': rk})
    for rk in seam_dels:
        ops.append({'op': 'delete', 'ref': rk})
    new_plan_room = next((pr for pr in (tc.get('plan') or {}).get('rooms', []) if pr.get('name') == N[new_id]), None)
    p.cells.pop(tmp_key, None)
    for k_ in [k_ for k_ in p.cells if '(extending ' in k_]:
        p.cells.pop(k_, None)                     # (a scratch place left by an earlier try)
    if not any(op['op'] == 'place' for op in ops):
        raise EditError('The builder laid nothing for the new room.')
    fixit.apply(db, cell_key, ops, None, commit=False)
    # the doorway's closure, the same the builder gives a planned door: the style's post over each bare jamb
    # end (and any see-through slit the join left), looked for at the seam only, as a round or two of the
    # builder's own closing pieces
    try:
        n_closed = 0
        for _round in range(2):
            got = [(pid, ppos, psc, pkind) for pid, ppos, psc, pkind in fixit.closing_pieces(db, cell_key)
                   if at_jamb_end(ppos[0], ppos[1], ppos[2]) or (pkind == 'hole' and on_tiles(ppos[0], ppos[1], ppos[2]))]
            if not got:
                break
            cops = [dict({'op': 'place', 'id': pid, 'p': list(ppos)}, **({'s': psc} if abs(psc - 1) > 0.001 else {})) for pid, ppos, psc, pkind in got]
            fixit.apply(db, cell_key, cops, None, commit=False)
            ops += cops
            n_closed += len(cops)
    except Exception as e:
        print('extend: closing the doorway:', e)
    # the place's plan grows: the room with its tiles for Auto-furnish, the planner's plan to start from again
    if new_plan_room:
        plan['rooms'].append(new_plan_room)
    else:
        plan['rooms'].append({'name': N[new_id], 'purpose': furnish.purpose_for(N[new_id], rw * rh, rw, rh),
                              'tiles': [[cx, cy, zf] for cx, cy in sorted(new_tiles)]})
    plan['planner'] = pl
    n_pieces = sum(1 for op in ops if op['op'] == 'place')
    note = 'Added the %s through the %s\'s %s wall (%d pieces)' % (
        N[new_id], sp['room'].get('name') or 'room', {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}[sp['side']], n_pieces)
    editing.commit(db, note)
    result = {'ok': True, 'room': N[new_id], 'pieces': n_pieces, 'placed': 0, 'furnished': False}
    if furnish_it:
        depth = editing.undo_depth(db)
        try:
            fr = furnish.furnish(db, cell_key, room=len(plan['rooms']) - 1, purpose=purpose or None, level=level or None,
                                 replace=False, seed=random.randrange(1 << 30))
            result['placed'] = fr.get('placed', 0)
            result['furnished'] = True
        except EditError as e:
            result['note'] = 'Built, but could not furnish it: %s' % e
        # (the pieces, the furnishing and the plan's new room are one step: one Undo takes the room back whole)
        steps = editing.undo_depth(db) - depth
        if steps > 0:
            editing.fold(db, steps + 1, 'Added the %s (%d pieces, %d things)' % (N[new_id], n_pieces, result['placed']))
    return result


# ------------------------------------------------------------------ remove a room
def _room_index(db, cell_key, room):
    """The plan's room by index (the id furnish.rooms gives a planned place's rooms) or by name."""
    plan, pl = _plan_of(db, cell_key)
    if isinstance(room, int) or (isinstance(room, str) and room.isdigit()):
        n = int(room)
        if 0 <= n < len(plan['rooms']):
            return plan, pl, n
    for n, r in enumerate(plan['rooms']):
        if (r.get('name') or '').lower() == str(room).lower():
            return plan, pl, n
    raise EditError('No such room in this place\'s plan.')


def _planner_room(pl, plan, n):
    """The planner's room for the plan's nth room (same order; by name when the orders differ)."""
    N = _names(pl)
    name = plan['rooms'][n].get('name')
    if n < len(pl['rooms']) and N.get(pl['rooms'][n]['id']) == name:
        return pl['rooms'][n]
    return next((r for r in pl['rooms'] if N.get(r['id']) == name), None)


def removable(db, cell_key, room):
    """Whether the room can be taken out, and why not: {'ok', 'why', 'name', 'doors'}."""
    plan, pl, n = _room_index(db, cell_key, room)
    pr = plan['rooms'][n]
    name = pr.get('name') or 'the room'
    if len(plan['rooms']) < 2:
        return {'ok': False, 'why': 'it is the only room', 'name': name}
    rr = _planner_room(pl, plan, n)
    if rr:
        ex = pl.get('exit') or {}
        if ex.get('room') == rr['id']:
            return {'ok': False, 'why': 'the way out is in it', 'name': name}
        if any(s.get('lo') == rr['id'] or s.get('hi') == rr['id'] for s in pl.get('stairs') or []):
            return {'ok': False, 'why': 'its stair joins two floors', 'name': name}
        # the other rooms must hang together as well without it as with it (a cellar the plan joins to the
        # house by no door of its own is already apart: that is not this room's doing)
        def components(ids):
            links = {}
            for d in pl.get('doors') or []:
                if d.get('a') in ids and d.get('b') in ids:
                    links.setdefault(d['a'], set()).add(d['b'])
                    links.setdefault(d['b'], set()).add(d['a'])
            for s in pl.get('stairs') or []:
                if s.get('lo') in ids and s.get('hi') in ids:
                    links.setdefault(s['lo'], set()).add(s['hi'])
                    links.setdefault(s['hi'], set()).add(s['lo'])
            seen, comps = set(), []
            for start in ids:
                if start in seen:
                    continue
                comp, todo = set(), [start]
                while todo:
                    x = todo.pop()
                    if x in comp:
                        continue
                    comp.add(x)
                    todo += [y for y in links.get(x, ()) if y not in comp]
                seen |= comp
                comps.append(comp)
            return comps
        others = {r['id'] for r in pl['rooms'] if r is not rr}
        with_it = [c for c in components(others | {rr['id']}) if c & others]
        if len(components(others)) > len(with_it):
            return {'ok': False, 'why': 'other rooms are reached through it', 'name': name}
    if pr.get('tall'):
        return {'ok': False, 'why': 'it is a two-storey hall', 'name': name}
    return {'ok': True, 'why': None, 'name': name}


def remove(db, cell_key, room):
    """Take a room out of a built place: its pieces and everything in it go, the wall closes again where
    its doorway was (the joint survey's answer for a wall with nothing beyond), and the plan loses the
    room and its doors; one change. {'ok', 'name', 'pieces', 'things', 'closed'}."""
    editing._require_project(db)
    chk = removable(db, cell_key, room)
    if not chk['ok']:
        raise EditError('The %s can\'t be taken out: %s.' % (chk['name'], chk['why']))
    plan, pl, n = _room_index(db, cell_key, room)
    pr = plan['rooms'][n]
    name = chk['name']
    m = mapdata.cellmap(db, cell_key)
    place = joints.read_place(db, cell_key, m)
    if not place['tiles']:
        raise EditError('This place isn\'t built from a style\'s room pieces.')
    T, H = place['tiles'][0]['T'], place['tiles'][0]['H']
    tiles = [(pt[0], pt[1], pt[2] if len(pt) > 2 else place['tiles'][0]['floor']) for pt in pr['tiles']]

    def on_room(x, y, z, arch=True):
        # (a building piece within the storey; a thing up to the ceiling line, where the hanging lamps are)
        top = H - 40 if arch else H - 4
        return any(abs(x - cx) <= T / 2 + 1 and abs(y - cy) <= T / 2 + 1 and cz - 40 <= z < cz + top for cx, cy, cz in tiles)
    ops, n_pieces, n_things = [], 0, 0
    for r in m['refs']:
        if on_room(r['p'][0], r['p'][1], r['p'][2], bool(r.get('arch'))):
            ops.append({'op': 'delete', 'ref': r['k']})
            if r.get('arch'):
                n_pieces += 1
            else:
                n_things += 1
    # the seam: every remaining tile side that faced the room (a doorway, or open) closes with a wall
    seams = []
    for t in place['tiles']:
        if on_room(t['x'], t['y'], t['floor']):
            continue
        for s in SIDES:
            dx, dy = STEP[s]
            if any(abs(t['x'] + dx * T - cx) < 24 and abs(t['y'] + dy * T - cy) < 24 and abs(t['floor'] - cz) < 64 for cx, cy, cz in tiles):
                seams.append((t['ref'], s))
                # (the door hung in the doorway, and anything else standing in the seam line, goes with the room)
                ex, ey, ax, ay, ddx, ddy = joints.edge_frame(t, s)
                for r in m['refs']:
                    if r.get('arch') or any(op.get('ref') == r['k'] for op in ops):
                        continue
                    u = (r['p'][0] - ex) * ax + (r['p'][1] - ey) * ay
                    d = (r['p'][0] - ex) * ddx + (r['p'][1] - ey) * ddy
                    if abs(d) <= 40 and abs(u) <= T * 0.5 and t['floor'] - 40 <= r['p'][2] <= t['floor'] + H:
                        ops.append({'op': 'delete', 'ref': r['k']})
                        n_things += 1
    if not ops:
        raise EditError('Nothing of the %s is standing here.' % name)
    fixit.apply(db, cell_key, ops, None, commit=False)
    closed = 0
    if seams:
        m2 = mapdata.cellmap(db, cell_key)
        place2 = joints.read_place(db, cell_key, m2)
        prefix = place['tiles'][0]['kit']
        fam = joints.family(prefix)
        ops2 = []
        for ref, s in seams:
            t = next((x for x in place2['tiles'] if x['ref'] == ref), None)
            if not t:
                continue
            # the jamb across the old doorway goes, and the doorway's posts (the game's answer for the wall
            # stands posts again where it has them)
            for L, u, d, dz, dq, label in joints.loose_on(place2, t, s, fam):
                if joints.class_of(L['id']) in ('jamb', 'wall', 'addon', 'post'):
                    ops2.append({'op': 'delete', 'ref': L['ref']})
            if t['spot'][s] == 'wall':
                continue
            o = None
            sit = joints.situation(place2, t, s)
            key, rec = joints.answers(db, prefix, sit)
            if rec:
                for c, n_, share, (a, info) in joints.ranked_cores(rec):
                    if c.partition(';')[0] == 'wall':
                        o = joints.ops_for(db, place2, t, s, a, info, prefix)
                        break
            if not o:
                want = {k: t['spot'][k] for k in SIDES}
                want[s] = 'wall'
                want['_top'] = False
                piece, q, missing, pat = builder._pick(t['kp'], want)
                if piece and not missing:
                    rz = q * math.pi / 2
                    o = {'ops': [{'op': 'swap', 'ref': t['ref'], 'id': piece['id'], 'rz': rz}] + [{'op': 'delete', 'ref': mr} for mr in t.get('mates', [])]}
            if o:
                ops2 += o['ops']
                closed += 1
        ops2 = fixhere._dedupe(ops2)
        if ops2:
            fixit.apply(db, cell_key, ops2, None, commit=False)
    # the plan: the room and its doors go
    rr = _planner_room(pl, plan, n)
    plan['rooms'].pop(n)
    if rr:
        pl['rooms'] = [r for r in pl['rooms'] if r is not rr]
        pl['doors'] = [d for d in pl.get('doors') or [] if rr['id'] not in (d.get('a'), d.get('b'))]
        pl['stairs'] = [s for s in pl.get('stairs') or [] if rr['id'] not in (s.get('lo'), s.get('hi'))]
    plan['planner'] = pl
    editing.commit(db, 'Removed the %s (%d pieces, %d things; the wall closed again)' % (name, n_pieces, n_things))
    return {'ok': True, 'name': name, 'pieces': n_pieces, 'things': n_things, 'closed': closed}


# ------------------------------------------------------------------ the furniture sketch
BIG = 100                                              # a thing's footprint this long (units) is a big piece of the sketch


def sketch(db, cell_key, ref=None, at=None, w=3, h=3, shift=0, name=None, kind=None, level=None):
    """What the furnish would lay in the ghost room, big pieces only (bed, table, shelves, rug, chest): the
    room's recipe run once on the ghost's tiles in a scratch place that is thrown away; [{id, p, s}].
    A sketch, not a promise: the real furnish rolls its own draw."""
    editing._require_project(db)
    p = db.project
    sp = _spot(db, cell_key, ref, at)
    o = options(db, cell_key, ref, at, w, h, shift, name)
    if not o['fits'] or not o['ghost']:
        return {'furniture': [], 'note': o.get('note')}
    T, zf = sp['T'], sp['zf']
    x0, y0, rw, rh = o['room']['x'], o['room']['y'], o['room']['w'], o['room']['h']
    real = p.cells.get(cell_key) or {}
    base = (mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key
    tmp = '%s (sketch %d)' % (base[:40], random.randrange(1 << 20))
    tmp_key = tmp.lower()
    for k_ in [k_ for k_ in p.cells if '(sketch ' in k_]:
        p.cells.pop(k_, None)
    header = real.get('header')
    if not header:
        from project import b64, zs
        import struct
        header = [['NAME', b64(zs(tmp))], ['DATA', b64(struct.pack('<Iii', 1, 0, 0))]]
    else:
        from project import b64, zs
        header = [[t_, (b64(zs(tmp)) if t_ == 'NAME' else d_)] for t_, d_ in header]
    purpose = furnish.purpose_for(kind or o['room']['name'], rw * rh, rw, rh)
    p.cells[tmp_key] = {'flags': real.get('flags', 0), 'header': header, 'refs': {},
                        'plan': {'tile': T, 'style': sp['plan'].get('style'), 'dressing': sp['plan'].get('dressing'),
                                 'rooms': [{'name': kind or o['room']['name'], 'purpose': purpose,
                                            'tiles': [[(x0 + i) * T, (y0 + j) * T, zf] for i in range(rw) for j in range(rh)]}]}}
    db.sync_project()
    out = []
    depth, nlog, last = editing.undo_depth(db), len(p.log), p.last_state
    try:
        ops = [{'op': 'place', 'id': g['id'], 'p': g['p']} for g in o['ghost'] if not g.get('swap')]
        fixit.apply(db, tmp_key, ops, None, commit=False)
        try:
            furnish.furnish(db, tmp_key, room=0, purpose=purpose, level=level or None, replace=False,
                            seed=random.randrange(1 << 30), commit=False, **({'sketch': True} if 'sketch' in furnish.furnish.__code__.co_varnames else {}))
        except EditError as e:
            return {'furniture': [], 'note': str(e)}
        for r in furnish.last_placed or []:
            b = r.get('b')
            if not b or r.get('on') or r.get('type') not in ('STAT', 'ACTI', 'CONT'):
                continue
            s = r.get('s') or 1.0
            if max(b[3] - b[0], b[4] - b[1]) * s < BIG:
                continue
            out.append({'id': r['id'], 'p': [round(v, 2) for v in r['p'][:6]], 's': s})
    finally:
        # (whatever the furnish committed on the scratch place is rolled off: nothing of it stays)
        stack = getattr(p, 'undo_stack', [])
        while editing.undo_depth(db) > depth:
            stack.pop()
        del p.log[nlog:]
        p.last_state = last
        p.cells.pop(tmp_key, None)
        db.sync_project()
    return {'furniture': out, 'purpose': purpose, 'note': None}


# ------------------------------------------------------------------ Extend mode: piece by piece
import adjacency

OPEN_SHARE = 0.1                                       # a face the game fills this seldom is no open edge (a Redoran
#                                                        manor's outer corner face: 18%, and that is where it grows)
RED_SHARE = 0.7                                        # ... and one it fills this often shows the void when open
TOP_SHARE = 0.5                                        # a top face is open only where the game mostly builds on it
THIN = 80                                              # a closing piece (a loose wall, a cap, a railing) is this thin or less


def _pieces(db, cell_key, m=None):
    m = m or mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('Extend works in interiors built from building pieces.')
    pieces = adjacency.read_pieces(db, cell_key, m)
    if not pieces:
        raise EditError('No building pieces here to extend from.')
    prefix = adjacency.kit_of(db, pieces)
    return m, pieces, prefix


def _void_test(db, m):
    """A function (A, side) -> whether a ray out through that face of A finds nothing beyond (the finder's
    see-through test), built once per place."""
    try:
        import seethrough
        sc = seethrough.place_scene(db, m)
    except Exception:
        return lambda A, side: False

    def test(A, side):
        b, s = A['b'], A['s']
        cx, cy = (b[0] + b[3]) / 2.0 * s, (b[1] + b[4]) / 2.0 * s
        zmid = A['z'] + (b[2] + b[5]) / 2.0 * s
        if side in ('E', 'W', 'N', 'S'):
            seg = adjacency.face_segment(A, side)
            fx, fy = (seg[0] + seg[2]) / 2.0, (seg[1] + seg[3]) / 2.0
            nx, ny = seg[5], seg[6]
            o = (fx - nx * 12, fy - ny * 12, zmid)
            d = (nx, ny, 0.0)
        else:
            wx, wy = adjacency.to_world(A, cx, cy)
            o = (wx, wy, A['z'] + (b[5] if side == 'U' else b[2]) * s + (-12 if side == 'U' else 12))
            d = (0.0, 0.0, 1.0 if side == 'U' else -1.0)
        # (the ray starts inside the piece and goes out through the face: the piece's own wall or ceiling
        # stops it, so a walled outer face is not a void; an open face with nothing beyond is)
        try:
            return not sc.blocked(o, d, 1500)
        except Exception:
            return False
    return test


def _open_faces(db, prefix, pieces, A, extra=(), voids=None, spots=None):
    """The faces of A with nothing against them that the game usually fills, or that the piece itself
    leaves open (a floor tile's open or doorway side: spots, from the joint survey's reading of the
    place): [(side, share, void)]."""
    rec = adjacency.record(db, prefix, A['id'])
    have = {s_ for s_, B in adjacency.neighbours(list(pieces) + list(extra), A)}
    spot = (spots or {}).get(A['ref'])
    out = []
    for side in ('E', 'W', 'N', 'S', 'U'):
        if side in have:
            continue
        share = adjacency.join_share(rec, side)
        # (a tile's own open or doorway side with nothing beyond is an open edge whatever the game's share)
        own_open = False
        if spot and side != 'U':
            q = int(round(A['rz'] / (math.pi / 2))) % 4
            world_side = SIDES[(SIDES.index(side) + q) % 4]
            own_open = spot.get(world_side) in ('open', 'door')
        # (a top face counts only where the game usually builds a storey on it: every roof piece of a
        # house would glow otherwise, 2026-10-22)
        if share < (TOP_SHARE if side == 'U' else OPEN_SHARE) and not own_open:
            continue
        void = voids(A, side) if voids else share >= RED_SHARE
        out.append((side, share, void))
    return out


def _strip(A, side, **kw):
    seg = adjacency.face_segment(A, side)
    d = {'ref': A['ref'], 'id': A['id'], 'side': side, 'a': [seg[0], seg[1], seg[4]], 'b': [seg[2], seg[3], seg[4]], 'out': [seg[5], seg[6]]}
    if side == 'U':
        # (the rim of the top face: its four corners in the world, for a square strip)
        b, s = A['b'], A['s']
        d['rim'] = [list(adjacency.to_world(A, lx, ly)) + [seg[4]] for lx, ly in ((b[0] * s, b[1] * s), (b[3] * s, b[1] * s), (b[3] * s, b[4] * s), (b[0] * s, b[4] * s))]
    d.update(kw)
    return d


def edges(db, cell_key):
    """Every open face of every building piece of the place: {'prefix', 'style', 'edges': [{ref, id, side, a, b,
    out, void, share, words}], 'open', 'note'}."""
    m, pieces, prefix = _pieces(db, cell_key)
    sv = adjacency.ready(db)
    out = {'prefix': prefix, 'style': kits.friendly(prefix) if prefix else '', 'pieces': len(pieces), 'edges': [], 'open': 0}
    if not sv:
        out['note'] = 'The Workshop is still learning which piece the game joins to which (once, a minute or so): try again shortly.'
        return out
    voids = _void_test(db, m)
    try:
        spots = {t['ref']: t['spot'] for t in joints.read_place(db, cell_key, m)['tiles']}
    except Exception:
        spots = {}
    for A in pieces:
        for side, share, void in _open_faces(db, prefix, pieces, A, voids=voids, spots=spots):
            words = '%s side of a %s; the game joins something here %d times in 10%s' % (
                adjacency.SIDE_WORDS[side], joints.nice(A['id'], prefix), round(share * 10), ', nothing beyond' if void else '')
            out['edges'].append(_strip(A, side, void=bool(void), share=round(share, 2), words=words))
    out['open'] = len(out['edges'])
    return out


def _piece_at(db, item):
    ri, b = adjacency._box(db, item['id'])
    if ri is None or not b:
        return None
    p = item['p']
    return {'ref': item.get('ref') or ('new|%s' % id(item)), 'id': item['id'].lower(), 'x': p[0], 'y': p[1], 'z': p[2], 'rz': p[5] % (2 * math.pi),
            's': item.get('s') or 1.0, 'b': b, 'ri': ri}


def candidates(db, cell_key, ref, side, limit=12):
    """What the game joins to this face of this piece, most often first, each with its ghost and the faces it
    would leave open; and the patterns that start from it (a run, a piece with its ring)."""
    m, pieces, prefix = _pieces(db, cell_key)
    A = next((x for x in pieces if x['ref'] == ref), None)
    if not A:
        raise EditError('That piece is no longer here.')
    rec = adjacency.record(db, prefix, A['id'])
    out = {'prefix': prefix, 'id': A['id'], 'label': joints.nice(A['id'], prefix), 'side': side, 'candidates': [], 'patterns': [],
           'n': (rec or {}).get('adj', {}).get(side, {}).get('n', 0)}
    if not rec:
        out['note'] = 'The game\'s places never show this piece, so there is nothing to offer here.'
        return out
    cands = adjacency.candidates(rec, side, limit)
    if not cands:
        out['note'] = 'The game never joins anything to this side of a %s.' % out['label']
        return out
    for rel, n, share in cands:
        item = adjacency.placed(A, rel)
        B = _piece_at(db, item)
        if not B:
            continue
        blocked = any(adjacency.overlaps(B, X) for X in pieces)
        leaves = [_strip(B, s2, share=round(sh, 2), void=bool(v)) for s2, sh, v in _open_faces(db, prefix, pieces, B)]
        out['candidates'].append({'id': item['id'], 'p': item['p'], 'n': n, 'share': round(share, 2), 'blocked': blocked,
                                  'label': joints.nice(item['id'], prefix), 'turn': rel[4], 'leaves': leaves,
                                  'ghost': [{'id': item['id'], 'p': item['p'], 's': 1.0}]})
    out['patterns'] = patterns(db, prefix, pieces, A, side, rec, out['candidates'])
    return out


def _run_ghost(A, rel, n):
    """n copies of the piece stepping away from A by the relation."""
    items, cur = [], A
    for k in range(n):
        it = adjacency.placed(cur, rel)
        items.append({'id': it['id'], 'p': it['p'], 's': 1.0})
        nxt = dict(cur, x=it['p'][0], y=it['p'][1], z=it['p'][2], rz=it['p'][5])
        cur = nxt
    return items


def patterns(db, prefix, pieces, A, side, rec, cands):
    """The assemblies the game's places repeat from this edge: a run of the same piece (with how many the
    game lays), and a candidate with its ring of neighbours; [{kind, label, n, min, max, ghost, share}]."""
    out = []
    # a run: the piece itself again on this side (turned the same way or about), as the game chains them
    runs = (rec or {}).get('runs', {}).get(side)
    same = next((c for c in cands if c['id'].lower() == A['id'] and c['turn'] in (0, 180)), None)
    if same and not same['blocked']:
        rel = (A['id'], 0, 0, 0, 0)
        lx, ly = adjacency.to_local(A, same['p'][0], same['p'][1])
        rel = (A['id'], int(round(lx / 8.0)) * 8, int(round(ly / 8.0)) * 8, int(round((same['p'][2] - A['z']) / 8.0)) * 8, same['turn'])
        lengths = {int(k): v for k, v in (runs or {}).get('lengths', {}).items()}
        n = max(lengths, key=lambda k: (lengths[k], k)) if lengths else 3
        n = max(2, min(8, n))
        out.append({'kind': 'run', 'id': A['id'], 'label': 'A run of %s' % joints.nice(A['id'], prefix), 'n': n, 'min': 1, 'max': 10,
                    'rel': list(rel), 'ghost': _run_ghost(A, rel, n), 'share': same['share'],
                    'words': ('the game lays runs of %s' % ', '.join(str(k) for k, v in sorted(lengths.items(), key=lambda kv: -kv[1])[:3])) if lengths else ''})
    # a ring: a candidate the game surrounds with the same neighbours again and again
    for c in cands[:6]:
        if c['blocked']:
            continue
        crec = adjacency.record(db, prefix, c['id'].lower())
        if not crec:
            continue
        root = _piece_at(db, c)
        for g in (crec.get('rings') or [])[:3]:
            members = []
            for ms in g['members']:
                rel = adjacency.parse_rel(ms)
                it = adjacency.placed(root, rel)
                Bm = _piece_at(db, it)
                if not Bm or any(adjacency.overlaps(Bm, X) for X in pieces) or adjacency.overlaps(Bm, root):
                    continue
                members.append({'id': it['id'], 'p': it['p'], 's': 1.0})
            if len(members) < 2:
                continue
            kinds = Counter(joints.nice(mm['id'], prefix) for mm in members)
            out.append({'kind': 'ring', 'id': c['id'], 'label': '%s with its %s' % (joints.nice(c['id'], prefix), ' and '.join('%d %s' % (v, k) if v > 1 else k for k, v in kinds.most_common(3))),
                        'n': g['n'], 'ghost': [{'id': c['id'], 'p': c['p'], 's': 1.0}] + members, 'share': c['share'],
                        'words': 'the game lays this set round a %s %d times' % (joints.nice(c['id'], prefix), g['n'])})
            if len(out) >= 5:
                return out
    return out


def run_ghost(db, cell_key, ref, rel, n):
    """The run pattern's ghost for a chosen length."""
    m, pieces, prefix = _pieces(db, cell_key)
    A = next((x for x in pieces if x['ref'] == ref), None)
    if not A:
        raise EditError('That piece is no longer here.')
    items = _run_ghost(A, tuple(rel), max(1, min(10, int(n))))
    # (a copy that runs into the house stops the run there)
    out = []
    for it in items:
        B = _piece_at(db, it)
        if B and any(adjacency.overlaps(B, X) for X in pieces):
            break
        out.append(it)
    return {'ghost': out}


def lay(db, cell_key, items, label=None):
    """Lay pieces as one undo step: {'changed': [refs]}."""
    ops = [{'op': 'place', 'id': it['id'], 'p': [float(v) for v in it['p'][:6]], **({'s': it['s']} if it.get('s') and abs(it['s'] - 1) > 0.001 else {})} for it in items]
    if not ops:
        raise EditError('Nothing to lay.')
    r = fixit.apply(db, cell_key, ops, label or ('Laid %s' % (ops[0]['id'] if len(ops) == 1 else '%d pieces' % len(ops))))
    return {'changed': r['changed']}


def fold(db, n, note):
    e = editing.fold(db, n, note)
    return {'ok': True, 'depth': editing.undo_depth(db), 'note': e['text'] if e else None}


def close(db, cell_key, refs, preview=True):
    """The joint survey's closing round on the new pieces only: the loose walls, posts, caps and swaps the
    builder's closing rounds would add round them, as a ghost (preview) or laid as one step."""
    m, pieces, prefix = _pieces(db, cell_key)
    new = [x for x in pieces if x['ref'] in set(refs or ())]
    if not new:
        raise EditError('None of the new pieces is standing here.')

    def near(x, y, z):
        # (beside a new piece, on its storey: a hole fix in the cellar under a new hall is not its closing)
        return any(abs(x - A['x']) <= 420 and abs(y - A['y']) <= 420 and -60 <= z - A['z'] <= 200 for A in new)
    refset = {x['ref'] for x in new}
    ops = []
    # the game's own closers from the adjacency survey: on each open face of a new piece, the thin piece
    # (a loose wall, a cap, a railing) the game stands there most often
    for A in new:
        for side, share, void in _open_faces(db, prefix, pieces, A):
            rec = adjacency.record(db, prefix, A['id'])
            for rel, n, sh in adjacency.candidates(rec, side, 8):
                if sh < 0.1:
                    break
                it = adjacency.placed(A, rel)
                B = _piece_at(db, it)
                if not B:
                    continue
                b, s = B['b'], B['s']
                thin = min(b[3] - b[0], b[4] - b[1]) * s <= THIN or (side == 'U' and (b[5] - b[2]) * s <= THIN)
                if not thin or any(adjacency.overlaps(B, X) for X in pieces):
                    continue
                ops.append({'op': 'place', 'id': it['id'], 'p': it['p']})
                break
    try:
        for op in fixit.joint_ops(db, cell_key):
            if op['op'] == 'place' and near(*op['p'][:3]) or op.get('ref') in refset:
                ops.append(op)
    except Exception as e:
        print('close: joint round:', e)
    try:
        for rid, pos, sc, kind in fixit.closing_pieces(db, cell_key):
            if near(pos[0], pos[1], pos[2]):
                ops.append({'op': 'place', 'id': rid, 'p': list(pos), 's': sc})
    except Exception as e:
        print('close: closing pieces:', e)
    ops = fixhere._dedupe(ops)
    ghost = [{'id': op['id'], 'p': op['p'], 's': op.get('s', 1.0)} for op in ops if op['op'] == 'place']
    if preview or not ops:
        return {'ops': ops, 'ghost': ghost, 'count': len(ops)}
    r = fixit.apply(db, cell_key, ops, 'Closed the new pieces the game\'s way (%d pieces)' % len(ops))
    return {'ops': ops, 'ghost': ghost, 'count': len(ops), 'changed': r['changed']}
