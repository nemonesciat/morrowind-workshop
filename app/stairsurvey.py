"""How the game's own, hand-made interiors put stairs between floors: a survey of every staircase in
places built from a style's room pieces, and what stands round it. The pieces are counted by the part
they play (open floor, a side, a corner, a hall, a dead end), so what one style does can be carried
over to a style the game never builds with (Tamriel Data's Redguard sets, say).

For each staircase: the floor piece at its foot and at its head, whether those are part of a room or a
landing of their own, the pieces beside it on both floors and whether they are walled towards it, what
stands over it upstairs (nothing, a floor piece, a room piece with no floor), and the posts and railings
at its edges."""
import math

import kits
import mapdata
from mapdata import ref_info

SIDES = kits.SIDES
VEC = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
LEFT = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
RIGHT = {v: k for k, v in LEFT.items()}

_cache = {}


def role(pat):
    """The part a floor piece plays, from its walls: centre, side, corner, hall, end, closed."""
    w = [s for s in SIDES if pat[s] == 'wall']
    if not w:
        return 'centre'
    if len(w) == 1:
        return 'side'
    if len(w) == 2:
        return 'hall' if OPP[w[0]] == w[1] else 'corner'
    return 'end' if len(w) == 3 else 'closed'


def _turn(side, q):
    return SIDES[(SIDES.index(side) + q) % 4]


def _cell_pieces(db, cell_key):
    """Floor pieces (of any style) and other things in a place: ([{x, y, floor, pat, id, T}], [(id, pos)])."""
    refs, _h = db.cell_refs(cell_key)
    tiles, other = [], []
    for ref in refs.values():
        rid, pos, scale, dead = ref_info(ref['subs'])
        if dead:
            continue
        pre = kits.kit_prefix(rid)
        kp = kits.kit_pieces(db, pre) if pre and pre in kits.kits(db) else None
        piece = next((p for p in kp['pieces'] if p['id'].lower() == rid.lower()), None) if kp else None
        q = int(round(pos[5] / (math.pi / 2))) % 4
        if piece and abs((scale or 1) - 1) < 0.02 and abs(pos[5] - q * math.pi / 2) % (2 * math.pi) < 0.1:
            tiles.append({'id': rid, 'x': pos[0], 'y': pos[1], 'floor': pos[2] + piece['zmin'], 'z': pos[2],
                          'pat': kits.rotate(piece['pattern'], q), 'T': kp['tile'], 'kit': pre})
        else:
            other.append((rid.lower(), pos))
    return tiles, other


def _at(tiles, x, y, lo, hi):
    """The floor piece at a spot, its floor between lo and hi (the highest such)."""
    best = None
    for t in tiles:
        if abs(t['x'] - x) < 40 and abs(t['y'] - y) < 40 and lo <= t['floor'] <= hi:
            if best is None or t['floor'] > best['floor']:
                best = t
    return best


def _room_size(tiles, t, cap=8):
    """How many floor tiles join this one through open sides, on its floor (up to cap)."""
    T = t['T']
    seen, todo = {(round(t['x']), round(t['y']))}, [t]
    while todo and len(seen) < cap:
        a = todo.pop()
        for s in SIDES:
            if a['pat'][s] == 'wall':
                continue
            b = _at(tiles, a['x'] + VEC[s][0] * T, a['y'] + VEC[s][1] * T, a['floor'] - 40, a['floor'] + 40)
            if b and b['pat'][OPP[s]] != 'wall' and (round(b['x']), round(b['y'])) not in seen:
                seen.add((round(b['x']), round(b['y'])))
                todo.append(b)
    return len(seen)


def survey(db, prefix, limit=60):
    """Every staircase of this style in the game's places (up to `limit` places per stair piece):
    [{stair, foot: {...}, head: {...}, sides_low, sides_high, over, posts, rails}]."""
    key = (prefix, limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    info = kits.stairs(db, prefix)
    out = []
    for sp in (info or {}).get('pieces', []):
        sid = sp['id'].lower()
        cells = [db.recs[ci][7] for ci in db.used_in.get(sid, ()) if db.recs[ci][0] == 'CELL' and not db.recs[ci][7].startswith('#')
                 and kits.game_made(db, db.recs[ci][7])]
        for ck in sorted(set(cells))[:limit]:
            tiles, other = _cell_pieces(db, ck)
            if not tiles:
                continue
            T = tiles[0]['T']
            for rid, pos in other:
                if rid != sid:
                    continue
                q = int(round(pos[5] / (math.pi / 2))) % 4
                low = _turn(sp['low'], q)
                high = OPP[low]
                x, y = pos[0], pos[1]
                z_lo = pos[2] + sp['z_low']                 # the lower floor piece's origin, from what's learnt
                foot = _at(tiles, x + VEC[low][0] * T, y + VEC[low][1] * T, z_lo - 200, z_lo + 200)
                if not foot:
                    continue
                lo_floor = foot['floor']
                hi_floor = lo_floor + sp['rise'] * (1 if sp.get('len', 1) <= 1 else 1)
                span = sp.get('len', 1)
                hx, hy = x + VEC[high][0] * T * span, y + VEC[high][1] * T * span
                head = _at(tiles, hx, hy, hi_floor - 80, hi_floor + 80)
                # (or more stairs: a flight that climbs half a floor and turns into the next one)
                more = not head and any(('stair' in r2 or 'ramp' in r2) and r2 != '' and math.hypot(p2[0] - hx, p2[1] - hy) < T * 0.8
                                        and abs(p2[2] - pos[2] - sp['rise']) < T * 0.6 for r2, p2 in other) or \
                    (not head and any(('stair' in r2 or 'ramp' in r2) and math.hypot(p2[0] - x, p2[1] - y) < T * 1.6 and p2 != pos and
                                      abs(p2[2] - pos[2]) > 40 for r2, p2 in other))
                rec = {'stair': sp['id'], 'cell': ck,
                       'foot': {'role': role(foot['pat']), 'open': foot['pat'][high] != 'wall', 'room': _room_size(tiles, foot), 'id': foot['id']},
                       'head': ({'role': role(head['pat']), 'open': head['pat'][low] != 'wall', 'room': _room_size(tiles, head), 'id': head['id']}
                                if head else {'role': 'stairs', 'room': 0, 'open': True} if more else None)}
                # beside it, on both floors: a floor piece walled towards the stairs, open to them, or nothing
                for name, fl in (('sides_low', lo_floor), ('sides_high', head['floor'] if head else hi_floor)):
                    got = []
                    for side in (LEFT[high], RIGHT[high]):
                        t = _at(tiles, x + VEC[side][0] * T, y + VEC[side][1] * T, fl - 60, fl + 60)
                        got.append('none' if not t else ('wall' if t['pat'][OPP[side]] == 'wall' else 'open') + ':' + role(t['pat']))
                    rec[name] = got
                # over it, upstairs
                up = _at(tiles, x, y, (head['floor'] if head else hi_floor) - 60, (head['floor'] if head else hi_floor) + 300)
                rec['over'] = role(up['pat']) + ':' + up['id'] if up else 'nothing'
                # posts, columns and railings round it
                posts, rails = [], []
                for rid2, p2 in other:
                    dx, dy = p2[0] - x, p2[1] - y
                    if abs(dx) > T * 0.8 or abs(dy) > T * 0.8 or not (lo_floor - 40 <= p2[2] <= lo_floor + sp['rise'] * 2 + 60):
                        continue
                    if any(w in rid2 for w in ('post', 'pillar', 'column')):
                        posts.append(rid2)
                    elif 'rail' in rid2 or 'banister' in rid2:
                        rails.append(rid2)
                rec['posts'], rec['rails'] = posts, rails
                # how the bottom of the stairs sits against the floor at its foot (below it: negative)
                sb = mapdata.object_bounds(db, sp['ri'])
                if sb:
                    rec['sink'] = round(pos[2] + sb[2] - foot['floor'], 1)
                out.append(rec)
    _cache[key] = (db.recs, out)
    return out


def summary(db, prefixes=None):
    """What the game does round its stairs, style by style and over all of them: counts of each
    situation, most common first."""
    from collections import Counter
    styles = prefixes or [p for p in kits.kits(db) if kits.stairs(db, p)]
    per, allc = {}, {k: Counter() for k in ('foot', 'head', 'sides_low', 'sides_high', 'over', 'posts', 'rails', 'sink')}
    for pre in styles:
        recs = survey(db, pre)
        if not recs:
            continue
        c = {k: Counter() for k in allc if k != 'sink'}
        for r in recs:
            c['foot'][(r['foot']['role'], 'room' if r['foot']['room'] >= 3 else 'landing')] += 1
            c['head'][('more stairs',) if r['head'] and r['head']['role'] == 'stairs' else
                      (r['head']['role'], 'room' if r['head']['room'] >= 3 else 'landing') if r['head'] else ('none',)] += 1
            c['sides_low'][tuple(sorted(r['sides_low']))] += 1
            c['sides_high'][tuple(sorted(r['sides_high']))] += 1
            c['over'][r['over'].split(':')[0]] += 1
            c['posts'][len(r['posts'])] += 1
            c['rails'][len(r['rails'])] += 1
            if 'sink' in r:
                c.setdefault('sink', Counter())[int(round(r['sink'] / 2.0) * 2)] += 1
        c.setdefault('sink', Counter())
        for k in c:
            allc[k].update(c[k])
        per[pre] = {'n': len(recs), **{k: [(str(a), b) for a, b in c[k].most_common(6)] for k in c}}
    return {'styles': per, 'all': {k: [(str(a), b) for a, b in v.most_common(8)] for k, v in allc.items()},
            'n': sum(p['n'] for p in per.values())}
