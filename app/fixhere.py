"""Fix here: point at a building piece or at an open tile edge in a place, and the Workshop reads the
situation at that joint (joints.py), says what the game stands there, most often first, and lays the
one you pick as one change. "Fix every spot like this one" lays the same answer at every edge of the
place in the same situation.

    POST /api/fixhere/options {cell, ref} or {cell, at: [x, y, z]}
    POST /api/fixhere/apply   {cell, ops, label} or {cell, key, ans, label, everywhere: true}"""
import math

import fixit
import joints
import mapdata
from editing import EditError

SIDES = joints.SIDES


def _edges_for_ref(place, ref):
    """The edges a placed piece stands on: a tile's four sides; a loose piece's edge(s) (a post at a
    corner lies at the end of up to four); [(tile, side)]."""
    t = next((x for x in place['tiles'] if x['ref'] == ref), None)
    if t:
        return [(t, s) for s in SIDES]
    L = next((x for x in place['loose'] if x['ref'] == ref), None)
    out = []
    if L:
        for t in place['tiles']:
            if L['z1'] < t['floor'] + 16 or L['z0'] > t['floor'] + t['H'] - 16:
                continue
            for s in SIDES:
                ex, ey, ax, ay, dx, dy = joints.edge_frame(t, s)
                u = (L['cx'] - ex) * ax + (L['cy'] - ey) * ay
                d = (L['cx'] - ex) * dx + (L['cy'] - ey) * dy
                if abs(d) <= t['T'] * 0.3 and abs(u) <= t['T'] * 0.55:
                    out.append((t, s, abs(d) + (abs(u) if abs(u) > t['T'] * 0.4 else 0)))
        out.sort(key=lambda x: x[2])
        # (a post at a corner lies at the end of up to four edges: the two it is nearest to)
        return [(t, s) for t, s, _d in out[:2]]
    st = next((x for x in place['stairs'] if x.get('ref') == ref), None)
    return []


def _edge_at(place, x, y, z):
    """The nearest tile edge to a point (on the floor the point is on): [(tile, side)] or []."""
    best = None
    for t in place['tiles']:
        if z is not None and not (t['floor'] - 40 <= z <= t['floor'] + t['H'] + 40):
            continue
        h = t['T'] / 2.0
        if abs(x - t['x']) > h + t['T'] * 0.6 or abs(y - t['y']) > h + t['T'] * 0.6:
            continue
        inside = abs(x - t['x']) <= h + 2 and abs(y - t['y']) <= h + 2
        for s in SIDES:
            ex, ey, ax, ay, dx, dy = joints.edge_frame(t, s)
            u = (x - ex) * ax + (y - ey) * ay
            d = (x - ex) * dx + (y - ey) * dy
            if abs(u) > h + 8:
                continue
            score = (0 if inside else 1, abs(d))
            if best is None or score < best[0]:
                best = (score, t, s)
    return [(best[1], best[2])] if best else []


def options(db, cell_key, ref=None, at=None):
    """What the game stands at the joint(s) pointed at: {'prefix', 'spots': [{tile ref, side, x, y, z, situation,
    now, n, key, options: [{label, n, share, ans, ops, ghost, current, possible}]}], 'note'}."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('Fix here works in interiors built from room pieces.')
    place = joints.read_place(db, cell_key, m)
    if not place['tiles']:
        raise EditError('This place isn\'t built from a style\'s room pieces.')
    from collections import Counter
    prefix = Counter(t['kit'] for t in place['tiles']).most_common(1)[0][0]
    edges = _edges_for_ref(place, ref) if ref else _edge_at(place, *at) if at else []
    if not edges:
        return {'prefix': prefix, 'spots': [], 'note': 'Point at a floor piece, a wall, a post or an edge of a tile.' if ref or at else 'Nothing pointed at.'}
    learnt = joints.ready(db)
    spots = []
    seen = set()
    for t, s in edges:
        if (t['ref'], s) in seen:
            continue
        seen.add((t['ref'], s))
        o = joints.options(db, place, t, s, prefix)
        ex, ey, ax, ay, dx, dy = joints.edge_frame(t, s)
        spots.append(dict(o, tile=t['ref'], tile_id=t['id'], side=s, x=ex, y=ey, z=t['floor'] + 110))
    out = {'prefix': prefix, 'style': __import__('kits').friendly(prefix), 'spots': spots}
    if not learnt:
        out['note'] = 'The Workshop is still learning what the game stands at each kind of joint (once, a minute or so): try again shortly.'
    elif not any(sp['options'] for sp in spots):
        out['note'] = 'The game\'s own %s places show no joint quite like this one.' % out['style']
    return out


def _dedupe(ops):
    out = []
    for op in ops:
        if op['op'] in ('swap', 'delete', 'move') and any(o['op'] == op['op'] and o.get('ref') == op['ref'] for o in out):
            continue
        if op['op'] == 'place' and any(o['op'] == 'place' and o['id'].lower() == op['id'].lower() and
                                       math.hypot(o['p'][0] - op['p'][0], o['p'][1] - op['p'][1]) < 24 and abs(o['p'][2] - op['p'][2]) < 24
                                       and abs(o['p'][5] - op['p'][5]) < 0.05 for o in out):
            continue
        out.append(op)
    return out


def everywhere(db, cell_key, key, ans, label=None):
    """Lay one answer at every edge of the place in the same situation (the key as the options gave it)
    where something else stands now, as one change: {'changed', 'spots'}."""
    m = mapdata.cellmap(db, cell_key)
    place = joints.read_place(db, cell_key, m)
    from collections import Counter
    prefix = Counter(t['kit'] for t in place['tiles']).most_common(1)[0][0]
    fam = joints.family(prefix)
    want_core = joints.core(ans)
    ops, spots = [], 0
    seen = set()
    for t in place['tiles']:
        if t['ref'] in seen or t['kit'] != prefix:
            continue
        seen.update(t['mates'])
        for s in SIDES:
            sit = joints.situation(place, t, s)
            used, rec = joints.answers(db, prefix, sit)
            if not rec or joints.key_str(used) != key:
                continue
            ident, _d = joints.answer_of(place, t, s, fam)
            if joints.core(joints.ans_str(ident)) == want_core:
                continue
            info = rec['ans'].get(ans)
            if not info:
                continue
            o = joints.ops_for(db, place, t, s, ans, info, prefix)
            if o:
                ops += o['ops']
                spots += 1
    ops = _dedupe(ops)
    if not ops:
        return {'changed': [], 'spots': 0}
    r = fixit.apply(db, cell_key, ops, label or 'Fixed %d spot%s the game\'s way' % (spots, '' if spots == 1 else 's'))
    return {'changed': r['changed'], 'spots': spots}
