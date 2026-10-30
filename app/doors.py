"""Where doors lead: read, change or remove a door's destination, pick a sensible place to
arrive, and optionally point the door at the other end back here."""
import math
import struct

import editing
import mapdata
from editing import EditError
from esm import zstr
from project import ref_info, zs

CELL = 8192


def link_of(subs):
    """{'cell': name or '', 'x', 'y', 'z', 'rz'} for a door that leads somewhere, else None."""
    d = dict((t, bytes(v)) for t, v in subs)
    if 'DODT' not in d or len(d['DODT']) < 24:
        return None
    x, y, z, _rx, _ry, rz = struct.unpack_from('<6f', d['DODT'])
    out = {'cell': zstr(d['DNAM']) if 'DNAM' in d else '', 'x': round(x, 1), 'y': round(y, 1), 'z': round(z, 1),
           'rz': round(rz, 4)}
    out['key'] = target_key(out)
    return out


def target_key(link):
    """The cell key a link points at ('' = outdoors, by position)."""
    if link['cell']:
        return link['cell'].lower()
    return '#%d,%d' % (math.floor(link['x'] / CELL), math.floor(link['y'] / CELL))


_scenes = {}


def _floor_at(db, m, x, y, bottom):
    """The floor under (x, y) near a door's foot in a place's own walls and floors (seethrough), or None: nothing to
    stand on there, or no room to stand."""
    import seethrough
    key = (id(db.recs), m.get('key'), len(m['refs']))
    if key not in _scenes:
        _scenes.clear()
        _scenes[key] = seethrough.place_scene(db, m)
    sc = _scenes[key]
    hit = sc.nearest_any((x, y, bottom + 90.0), (0.0, 0.0, -1.0), 260.0)
    if hit is None:
        return None
    z = bottom + 90.0 - hit[0]
    if abs(z - bottom) > 110:
        return None
    up = sc.nearest_any((x, y, z + 20.0), (0.0, 0.0, 1.0), 400.0)
    if up is not None and up[0] < 100:
        return None                                    # (under a ledge or in a wall: no room)
    return z


def _in_front(m, door, db=None):
    """A spot a step away from a door, on the room side, facing away from it. With db, in a place with walls and
    floors: the side with floor to stand on, tried both ways (the middle of the things near a door was the guess, and
    in a cave or ruin it lay behind the door: you arrived outside the walls, in the void, the user 2026-10-30)."""
    px, py = door['p'][0], door['p'][1]
    near = [r['p'] for r in m['refs'] if r is not door and 60 < math.hypot(r['p'][0] - px, r['p'][1] - py) < 900]
    if near:
        cx, cy = sum(p[0] for p in near) / len(near) - px, sum(p[1] for p in near) / len(near) - py
    else:
        cx, cy = math.sin(door['p'][5]), math.cos(door['p'][5])
    d = math.hypot(cx, cy) or 1.0
    ux, uy = cx / d, cy / d
    bottom = door['p'][2] + ((door.get('b') or [0, 0, 0])[2]) * (door.get('s') or 1.0)
    z = bottom + 12
    if db is not None and m.get('interior'):
        fx, fy = math.sin(door['p'][5]), math.cos(door['p'][5])
        tries = [(ux, uy), (-ux, -uy), (fx, fy), (-fx, -fy), (fy, -fx), (-fy, fx)]
        # (the first side with floor, the middle of the things near it first: tried against 150 of the game's door
        # pairs, its spots fell on the wrong side of the door 6% of the time, the guess alone 10%; choosing the side
        # with more room when both had floor made it 12%)
        for tx, ty in tries:
            for dist in (110, 160, 220):
                try:
                    fz = _floor_at(db, m, px + tx * dist, py + ty * dist, bottom)
                except Exception:
                    fz = None
                if fz is not None:
                    ux, uy, z = tx, ty, fz + 12
                    x, y = px + ux * dist, py + uy * dist
                    yaw = math.atan2(ux, uy) % (2 * math.pi)
                    return [round(x, 1), round(y, 1), round(z, 1), 0.0, 0.0, round(yaw, 4)]
    x, y = px + ux * 110, py + uy * 110
    yaw = math.atan2(ux, uy) % (2 * math.pi)           # the game measures turns clockwise from north
    return [round(x, 1), round(y, 1), round(z, 1), 0.0, 0.0, round(yaw, 4)]


def _leads_to(db, link, source_key):
    if not link:
        return False
    if source_key.startswith('#'):
        if link['cell']:
            return False
        gx, gy = (int(v) for v in source_key[1:].split(','))
        return abs(math.floor(link['x'] / CELL) - gx) <= 1 and abs(math.floor(link['y'] / CELL) - gy) <= 1
    return link['cell'].lower() == source_key


def arrival(db, target, source_key=None, near=None):
    """Where to arrive in a place: in front of its door back to where you came from, else in front of
    any door that leads out, else in the middle of things. Returns (pos6, back door ref or None)."""
    m = mapdata.cellmap(db, target)
    if not m.get('exists'):
        raise EditError('That place does not exist.')
    doors = [r for r in m['refs'] if r['type'] == 'DOOR']
    back = None
    if source_key:
        backs = [r for r in doors if _leads_to(db, r.get('to'), source_key)]
        if backs:
            if near:
                backs.sort(key=lambda r: math.hypot(r['p'][0] - near[0], r['p'][1] - near[1]))
            back = backs[0]
            if not near:
                return _in_front(m, back, db), back
    if near:
        # (a spot that was clicked is where you arrive, even with a door back there: that door still leads back)
        x, y = float(near[0]), float(near[1])
        z = near[2] if len(near) > 2 and near[2] is not None else mapdata.surface_z(db, m['refs'], m['interior'], x, y, None, 1.0, 'NPC_', None) + 10
        return [x, y, z, 0, 0, float(near[3]) if len(near) > 3 and near[3] is not None else 0.0], back
    linked = [r for r in doors if r.get('to')]
    if linked:
        return _in_front(m, linked[0], db), None
    if m['interior'] and doors:
        # no way out yet: just inside its door
        load_like = [r for r in doors if 'load' in r['id'].lower()] or doors
        return _in_front(m, load_like[0], db), load_like[0]
    if m['interior']:
        refs = m['refs'] or [{'p': [0, 0, 0]}]
        x = sorted(r['p'][0] for r in refs)[len(refs) // 2]
        y = sorted(r['p'][1] for r in refs)[len(refs) // 2]
    else:
        x, y = (m['gx'] + 0.5) * CELL, (m['gy'] + 0.5) * CELL
    z = mapdata.surface_z(db, m['refs'], m['interior'], x, y, None, 1.0, 'NPC_', None) + 10
    return [x, y, z, 0, 0, 0.0], None


def _set_link(subs, dest_name, pos):
    """Door subrecords with the destination replaced (or removed when pos is None)."""
    subs = [(t, bytes(d)) for t, d in subs if t not in ('DODT', 'DNAM')]
    if pos is None:
        return subs
    extra = [('DODT', struct.pack('<6f', *[float(v) for v in pos[:6]]))]
    if dest_name:
        extra.append(('DNAM', zs(dest_name)))
    out, put = [], False
    for t, d in subs:
        if t == 'DATA' and not put:
            out += extra
            put = True
        out.append((t, d))
    if not put:
        out += extra
    return out


def link_pair(db, cell_a, ref_a, cell_b, ref_b):
    """Two picked doors lead to each other, each arriving in front of the other (one picked in each of two
    windows, web/twowin.js), as one change."""
    editing._require_project(db)
    if cell_a == cell_b and ref_a == ref_b:
        raise EditError('Pick two different doors.')
    ends = []
    for ck, rk in ((cell_a, ref_a), (cell_b, ref_b)):
        c, refs = editing._cell(db, ck)
        ref = refs.get(rk)
        if not ref:
            raise EditError('That door is no longer here.')
        rid = ref_info(ref['subs'])[0]
        ri = db.resolve_id(rid)
        if ri is None or db.recs[ri][0] != 'DOOR':
            raise EditError('"%s" is not a door.' % rid)
        m = mapdata.cellmap(db, ck)
        here = next((r for r in m['refs'] if r['k'] == rk), None)
        if not here:
            raise EditError('That door is no longer here.')
        ends.append({'cell': ck, 'k': rk, 'c': c, 'ref': ref, 'id': rid, 'here': here, 'map': m,
                     'info': mapdata.cell_info(db, ck)})
    for me, other in ((ends[0], ends[1]), (ends[1], ends[0])):
        pos = _in_front(other['map'], other['here'], db)
        name = other['info']['name'] if other['info']['interior'] else ''
        ref = me['ref']
        editing._store(me['c'], me['k'], ref['origin'], ref['idx'], _set_link(ref['subs'], name, pos))
    a, b = ends
    editing.commit(db, 'Doors "%s" in %s and "%s" in %s now lead to each other' % (
        a['id'], editing.cell_label(db, a['cell']), b['id'], editing.cell_label(db, b['cell'])))
    return {'ok': True, 'cells': sorted({a['cell'], b['cell']})}


def relink(db, cell_key, refkey, target=None, at=None, both_ways=False):
    """Make a door lead to `target` (a cell key), arriving at `at` ([x, y, z, rz] or None to choose).
    target None removes the link. both_ways also points the door at the other end back here."""
    editing._require_project(db)
    c, refs = editing._cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That door is no longer here.')
    rid = ref_info(ref['subs'])[0]
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] != 'DOOR':
        raise EditError('Only doors can lead somewhere.')
    if not target:
        editing._store(c, refkey, ref['origin'], ref['idx'], _set_link(ref['subs'], None, None))
        editing.commit(db, 'Door "%s" in %s no longer leads anywhere' % (rid, editing.cell_label(db, cell_key)))
        return {'ok': True}
    info = mapdata.cell_info(db, target)
    if not info:
        raise EditError('There is no place called "%s".' % target)
    # (a door to elsewhere in its own place, as the game's towers, manors and tombs have: the spot is picked)
    same = target == cell_key
    if same and not at:
        raise EditError('Pick where you arrive in this place: click the spot.')
    here = next((r for r in mapdata.cellmap(db, cell_key)['refs'] if r['k'] == refkey), None)
    near = None
    if at:
        near = [float(at[0]), float(at[1]), None if len(at) < 3 or at[2] is None else float(at[2]),
                float(at[3]) if len(at) > 3 and at[3] is not None else None]
    pos, back = arrival(db, target, None if same else cell_key, near)
    dest_name = info['name'] if info['interior'] else ''
    editing._store(c, refkey, ref['origin'], ref['idx'], _set_link(ref['subs'], dest_name, pos))
    note = 'Door "%s" in %s now leads to %s' % (rid, editing.cell_label(db, cell_key), info['name'] or info['id'])
    back_done = None
    if both_ways and here:
        # the door at the other end: the one that already leads here, or the closest door to where you arrive
        m2 = mapdata.cellmap(db, target)
        cand = back or min((r for r in m2['refs'] if r['type'] == 'DOOR' and not (same and r['k'] == refkey)),
                           key=lambda r: math.hypot(r['p'][0] - pos[0], r['p'][1] - pos[1]), default=None)
        if cand and math.hypot(cand['p'][0] - pos[0], cand['p'][1] - pos[1]) < 600:
            c2, refs2 = editing._cell(db, target)
            r2 = refs2.get(cand['k'])
            if r2:
                src = mapdata.cell_info(db, cell_key)
                back_pos = _in_front(mapdata.cellmap(db, cell_key), here, db)
                editing._store(c2, cand['k'], r2['origin'], r2['idx'],
                               _set_link(r2['subs'], src['name'] if src['interior'] else '', back_pos))
                back_done = cand['id']
                note += ' (and back)'
    editing.commit(db, note)
    return {'ok': True, 'arrive': pos, 'back': back_done}
