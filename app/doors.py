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


def _in_front(m, door):
    """A spot a step away from a door, on the room side, facing away from it."""
    px, py = door['p'][0], door['p'][1]
    near = [r['p'] for r in m['refs'] if r is not door and 60 < math.hypot(r['p'][0] - px, r['p'][1] - py) < 900]
    if near:
        cx, cy = sum(p[0] for p in near) / len(near) - px, sum(p[1] for p in near) / len(near) - py
    else:
        cx, cy = math.sin(door['p'][5]), math.cos(door['p'][5])
    d = math.hypot(cx, cy) or 1.0
    ux, uy = cx / d, cy / d
    x, y = px + ux * 110, py + uy * 110
    bottom = door['p'][2] + ((door.get('b') or [0, 0, 0])[2]) * (door.get('s') or 1.0)
    yaw = math.atan2(ux, uy) % (2 * math.pi)           # the game measures turns clockwise from north
    return [round(x, 1), round(y, 1), round(bottom + 12, 1), 0.0, 0.0, round(yaw, 4)]


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
    if source_key:
        back = [r for r in doors if _leads_to(db, r.get('to'), source_key)]
        if back:
            if near:
                back.sort(key=lambda r: math.hypot(r['p'][0] - near[0], r['p'][1] - near[1]))
            return _in_front(m, back[0]), back[0]
    if near:
        x, y = float(near[0]), float(near[1])
        z = near[2] if len(near) > 2 and near[2] is not None else mapdata.surface_z(db, m['refs'], m['interior'], x, y, None, 1.0, 'NPC_', None) + 10
        return [x, y, z, 0, 0, float(near[3]) if len(near) > 3 and near[3] is not None else 0.0], None
    linked = [r for r in doors if r.get('to')]
    if linked:
        return _in_front(m, linked[0]), None
    if m['interior'] and doors:
        # no way out yet: just inside its door
        load_like = [r for r in doors if 'load' in r['id'].lower()] or doors
        return _in_front(m, load_like[0]), load_like[0]
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
    if target == cell_key:
        raise EditError('A door can\'t lead into the place it stands in. Pick another place.')
    here = next((r for r in mapdata.cellmap(db, cell_key)['refs'] if r['k'] == refkey), None)
    near = None
    if at:
        near = [float(at[0]), float(at[1]), None if len(at) < 3 or at[2] is None else float(at[2]),
                float(at[3]) if len(at) > 3 and at[3] is not None else None]
    pos, back = arrival(db, target, cell_key, near)
    dest_name = info['name'] if info['interior'] else ''
    editing._store(c, refkey, ref['origin'], ref['idx'], _set_link(ref['subs'], dest_name, pos))
    note = 'Door "%s" in %s now leads to %s' % (rid, editing.cell_label(db, cell_key), info['name'] or info['id'])
    back_done = None
    if both_ways and here:
        # the door at the other end: the one that already leads here, or the closest door to where you arrive
        m2 = mapdata.cellmap(db, target)
        cand = back or min((r for r in m2['refs'] if r['type'] == 'DOOR'),
                           key=lambda r: math.hypot(r['p'][0] - pos[0], r['p'][1] - pos[1]), default=None)
        if cand and math.hypot(cand['p'][0] - pos[0], cand['p'][1] - pos[1]) < 600:
            c2, refs2 = editing._cell(db, target)
            r2 = refs2.get(cand['k'])
            if r2:
                src = mapdata.cell_info(db, cell_key)
                back_pos = _in_front(mapdata.cellmap(db, cell_key), here)
                editing._store(c2, cand['k'], r2['origin'], r2['idx'],
                               _set_link(r2['subs'], src['name'] if src['interior'] else '', back_pos))
                back_done = cand['id']
                note += ' (and back)'
    editing.commit(db, note)
    return {'ok': True, 'arrive': pos, 'back': back_done}
