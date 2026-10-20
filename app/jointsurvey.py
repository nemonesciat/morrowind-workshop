"""Where the game's own, hand-made interiors stand posts and columns, and how their doorways meet the
walls: a survey of every corner where floor pieces meet, in places built from a style's room pieces.

A corner is described the same whichever way it is turned: which of the four tiles round it are there,
and what runs off from it along each of the four edges between them (a wall, a doorway, a door frame,
open floor, or nothing: the outside). For each kind of corner, how often the game stands a post or
column on it, which one, and which way round. Counted for each style and for all of them together, so
a style the game never builds with goes by what every style does at a corner like that."""
import math
import re
from collections import Counter

import kits
import stairsurvey

SIDES = kits.SIDES
POSTY = re.compile(r'post|pillar|column')
FRAMEY = re.compile(r'jamb|doorframe|doorway|wall_?door|walldoor')
_cache = {}

# a corner's four tiles: NE, NW, SW, SE of it; its four edges run N, W, S, E from it
QUAD = {'NE': (1, 1), 'NW': (-1, 1), 'SW': (-1, -1), 'SE': (1, -1)}


def _corner_key(quads, edges):
    """The same for a corner whichever way it's turned: (tiles there, edges) at the turn that sorts first.
    quads: [NE, NW, SW, SE] True/False; edges: [N, W, S, E] kinds."""
    best = None
    for k in range(4):
        q = tuple(quads[(i + k) % 4] for i in range(4))
        e = tuple(edges[(i + k) % 4] for i in range(4))
        if best is None or (q, e) < best:
            best = (q, e)
    return best


def corners(tiles, frames=()):
    """Every corner where floor tiles meet: [{x, y, floor, key, quads, edges}]. frames: [(x0, y0, x1, y1, z)]
    boxes of door frames standing on edges."""
    if not tiles:
        return []
    T = tiles[0]['T']
    at = {}
    for t in tiles:
        at[(round(t['x'] / 8), round(t['y'] / 8), round(t['floor'] / 32))] = t
    get = lambda x, y, f: at.get((round(x / 8), round(y / 8), round(f / 32)))
    seen, out = set(), []
    for t in tiles:
        for cx, cy in QUAD.values():
            vx, vy = t['x'] + cx * T / 2, t['y'] + cy * T / 2
            k = (round(vx / 8), round(vy / 8), round(t['floor'] / 32))
            if k in seen:
                continue
            seen.add(k)
            q = {n: get(vx + dx * T / 2, vy + dy * T / 2, t['floor']) for n, (dx, dy) in QUAD.items()}

            def edge(a, b, side_a, side_b, ex, ey):
                """The edge between quadrant tiles a and b (side_a of a faces b), from the corner along (ex, ey)."""
                ta, tb = q[a], q[b]
                if not ta and not tb:
                    return 'none'
                mx, my = vx + ex * T / 2, vy + ey * T / 2
                if any(f[0] - 24 <= mx <= f[2] + 24 and f[1] - 24 <= my <= f[3] + 24 and abs(f[4] - t['floor']) < 160 for f in frames):
                    return 'frame'
                pa = ta['pat'][side_a] if ta else None
                pb = tb['pat'][side_b] if tb else None
                if 'wall' in (pa, pb) or not ta or not tb:
                    return 'wall' if 'wall' in (pa, pb) else 'edge'
                return 'door' if 'door' in (pa, pb) else 'open'
            edges = [edge('NW', 'NE', 'E', 'W', 0, 1), edge('SW', 'NW', 'N', 'S', -1, 0),
                     edge('SE', 'SW', 'W', 'E', 0, -1), edge('NE', 'SE', 'S', 'N', 1, 0)]
            quads = [bool(q['NE']), bool(q['NW']), bool(q['SW']), bool(q['SE'])]
            out.append({'x': vx, 'y': vy, 'floor': t['floor'], 'quads': quads, 'edges': edges,
                        'key': _corner_key(quads, edges), 'kit': t['kit']})
    return out


def survey(db, prefix, limit=60):
    """Corners in the game's places of this style: {key: {'n', 'with', 'ids': Counter}} and a count of
    places looked at."""
    if (prefix, limit) in _cache and _cache[(prefix, limit)][0] is db.recs:
        return _cache[(prefix, limit)][1]
    kp = kits.kit_pieces(db, prefix)
    cells = set()
    for p in (kp or {}).get('pieces', [])[:8]:
        cells |= {db.recs[ci][7] for ci in db.used_in.get(p['id'].lower(), ()) if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7])
                  and not db.recs[ci][7].startswith('#')}
    stats, places = {}, 0
    for ck in sorted(cells)[:limit]:
        tiles, other = stairsurvey._cell_pieces(db, ck)
        tiles = [t for t in tiles if t['kit'] == prefix]
        if len(tiles) < 4:
            continue
        places += 1
        T = tiles[0]['T']
        frames, posts = [], []
        for rid, pos in other:
            if FRAMEY.search(rid):
                b = None
                ri = db.resolve_id(rid)
                if ri is not None:
                    import mapdata
                    b = mapdata.object_bounds(db, ri)
                if b and max(b[3] - b[0], b[4] - b[1]) >= T * 0.8:
                    w = max(b[3] - b[0], b[4] - b[1]) / 2
                    along_x = abs(math.cos(pos[5])) > 0.7 if (b[3] - b[0]) > (b[4] - b[1]) else abs(math.sin(pos[5])) > 0.7
                    frames.append((pos[0] - (w if along_x else 20), pos[1] - (20 if along_x else w),
                                   pos[0] + (w if along_x else 20), pos[1] + (20 if along_x else w), pos[2] + b[2]))
            elif POSTY.search(rid):
                posts.append((rid, pos))
        for c in corners(tiles, frames):
            st = stats.setdefault(c['key'], {'n': 0, 'with': 0, 'ids': Counter()})
            st['n'] += 1
            near = [rid for rid, p in posts if abs(p[0] - c['x']) < 40 and abs(p[1] - c['y']) < 40 and
                    c['floor'] - 64 <= p[2] <= c['floor'] + 400]
            if near:
                st['with'] += 1
                st['ids'][near[0]] += 1
    res = (stats, places)
    _cache[(prefix, limit)] = (db.recs, res)
    return res


def describe(key):
    """A corner in words: 'walls: 2, doorways: 1, frames: 0, open: 1, tiles 3'."""
    quads, edges = key
    c = Counter(edges)
    return 'tiles %d; %s' % (sum(quads), ', '.join('%s %d' % (k, c[k]) for k in ('wall', 'frame', 'door', 'open', 'edge', 'none') if c[k]))


def rules(db, styles=None):
    """{'styles': {prefix: {key: share with a post, n, id}}, 'all': {key: share, n}} for the corners seen
    at least a few times."""
    styles = styles or list(kits.kits(db))
    per, allc = {}, {}
    for pre in styles:
        stats, places = survey(db, pre)
        if not places:
            continue
        per[pre] = {k: {'share': round(v['with'] / v['n'], 2), 'n': v['n'],
                        'id': v['ids'].most_common(1)[0][0] if v['ids'] else None} for k, v in stats.items() if v['n'] >= 3}
        for k, v in stats.items():
            a = allc.setdefault(k, {'n': 0, 'with': 0})
            a['n'] += v['n']
            a['with'] += v['with']
    return {'styles': per, 'all': {k: {'share': round(v['with'] / v['n'], 2), 'n': v['n']} for k, v in allc.items() if v['n'] >= 5}}


def summary(db, styles=None):
    """For people: the kinds of corner most often seen, how often each has a post, style by style and
    over all."""
    r = rules(db, styles)
    out = {'all': sorted(([describe(k), v['n'], v['share']] for k, v in r['all'].items()), key=lambda x: -x[1])[:25],
           'styles': {pre: sorted(([describe(k), v['n'], v['share'], v['id']] for k, v in d.items()), key=lambda x: -x[1])[:12]
                      for pre, d in r['styles'].items()}}
    return out
