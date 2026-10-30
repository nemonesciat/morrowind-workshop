"""The rules a made dungeon keeps (dwemer.py), checked on its layout before anything is written.

The user: "the game should prioritize making consistent and valid dungeons over total player control". So a
layout is only made when:

1. the way in is its highest point: no floor above the front door's, as in about three quarters of the game's
   own dungeons (the rest have a stair up somewhere, 5-15% of their pieces; the user wants it never);
2. every piece is joined to the rest by a real passage: reached from the way in, and no opening that leads
   nowhere or into a wall;
3. no leaks: from either side of every join, eye-height rays see no void through it;
4. pieces never run into each other where they don't join, and every join has room to walk through.

check() says what's wrong and where, in plain words; dwemer.generate keeps only layouts that pass and says
what it changed to get there. Measured against the game's own places in the lab (scratch rkm.py, j_game.py)."""
import math
from collections import defaultdict, deque

import mapdata

SIDES = {'E': (1, 0), 'W': (-1, 0), 'N': (0, 1), 'S': (0, -1)}
OPP = {'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N'}
RISE = 32               # a floor this much over the way in's is above it (cave floors are uneven by about this)
CAVE_RISE = 64
# how deep a made place may go below its way in, by kind: the game's own deepest tenth (the drop from the
# front door to the lowest floor, 51-123 places a kind, 2026-10-26)
DEEP = {'dwemer': 1560, 'cave': 1792, 'tomb': 1024, 'daedric': 2560, 'tower': 1024}
HEADROOM = 100          # a join a player walks through: this much over its floor (the player is about 90 tall)
WIDTH = 64              # and this wide at waist height
SLACK = 40              # boxes may overlap this much at their trims (dwemer.SLACK)


def _rot(x, y, rz):
    c, s = math.cos(rz), math.sin(rz)
    return x * c + y * s, -x * s + y * c


def _dir_of(vx, vy):
    return min(SIDES, key=lambda k: (SIDES[k][0] - vx) ** 2 + (SIDES[k][1] - vy) ** 2)


# Some of the game's own climb from the way in instead (the way in their lowest point, nothing under it): a
# few of each kind, 2026-10-26 (scratch climbs.py on j_game.py's rows): Dwemer 1 of 65 (Nchazdrumn, Halls of
# Rest), caves 16 of 370, tombs 12 of 123, Daedric 1 of 71 (Ald Balaal). How high they go: the highest of them.
# (the user: "some dungeons are going to be ascents rather than descents ... climbing up a Dwemer tower")
CLIMB = {'dwemer': 1152, 'cave': 1152, 'tomb': 1024, 'daedric': 768, 'tower': 1536}     # (towers: Ald Virak's, Nim's 1536)
CLIMBERS = {'dwemer': (1, 65), 'cave_mold': (4, 121), 'cave_mud': (7, 101), 'cave_py': (1, 97), 'cave_lava': (4, 51),
            'tomb': (12, 123), 'daedric': (1, 71), 'tower': (51, 64)}       # (towers: the pit's floor over the front door's)


def deep_cap(K):
    k = K.get('kind', 'dwemer')
    return DEEP['cave'] if k.startswith('cave') else DEEP.get(k, 1560)


def climb_cap(K):
    k = K.get('kind', 'dwemer')
    return CLIMB['cave'] if k.startswith('cave') else CLIMB.get(k, 1152)


def rise_cap(K):
    return CAVE_RISE if K.get('kind', '').startswith('cave') else RISE


def floor_of(S, p):
    """A piece's floor: its lowest join's height (a cave piece's box runs far down into the rock), or its own
    height for a room tile, which has no joins."""
    ps = S['ports'].get(p['id']) or []
    return p['p'][2] + min(q[2] for q in ps) if ps else p['p'][2]


def entrance_z(lay, S):
    e = lay.get('entrance') or {}
    if 'piece' in e:
        return floor_of(S, lay['pieces'][e['piece']])
    return e.get('z', 0.0)


def _nodes(lay):
    """Each live piece's node: a hall's tiles are one place, a companion goes with its piece."""
    P = lay['pieces']
    node = {}
    for k, p in enumerate(P):
        if p.get('gone') or not p.get('id'):
            continue
        if p.get('of') is not None:
            node[k] = ('h', P[p['of']]['hall']) if P[p['of']].get('hall') is not None else p['of']
        elif p.get('hall') is not None:
            node[k] = ('h', p['hall'])
        else:
            node[k] = k
    return node


def where(lay, k):
    """Where a piece is, in words for the plan: its kind and its height against the way in."""
    p = lay['pieces'][k]
    role = 'a hall' if p.get('hall') is not None else 'a %s' % (p.get('role') or 'piece')
    return '%s (piece %d)' % (role, k)


def top_of(S, p):
    """A piece's highest join (a climbing ramp's top end), or its own height for a room tile."""
    ps = S['ports'].get(p['id']) or []
    return p['p'][2] + max(q[2] for q in ps) if ps else p['p'][2]


def climbs(lay):
    """Whether the layout climbs up from its way in (the way in its lowest point) instead of going down."""
    return lay.get('way') == 'up'


def heights(lay, S, K):
    """Pieces on the wrong side of the way in (over it, or under it for a place that climbs), and ones further
    from it than the game's own go: ([(k, floor - way in)], [(k, floor - way in)])."""
    ez = entrance_z(lay, S)
    up, deep = [], []
    cap = rise_cap(K)
    for k, p in enumerate(lay['pieces']):
        if p.get('gone') or not p.get('id') or p.get('of') is not None:
            continue
        f = floor_of(S, p)
        if climbs(lay):
            if f < ez - cap:
                up.append((k, round(f - ez)))
            elif top_of(S, p) > ez + climb_cap(K):
                deep.append((k, round(top_of(S, p) - ez)))
        elif f > ez + cap:
            up.append((k, round(f - ez)))
        elif f < ez - deep_cap(K):
            deep.append((k, round(f - ez)))
    return up, deep


def joined(lay):
    """Pieces not reached from the way in by the layout's joins: [k]."""
    node = _nodes(lay)
    nb = defaultdict(set)
    for s in lay['seams']:
        a, b = node.get(s[4]), node.get(s[5])
        if a is not None and b is not None:
            nb[a].add(b)
            nb[b].add(a)
    e = lay.get('entrance') or {}
    start = node.get(e['piece'] if 'piece' in e else e.get('owner', 0))
    if start is None:
        return sorted(node)
    seen, todo = {start}, deque([start])
    while todo:
        u = todo.popleft()
        for v in nb[u]:
            if v not in seen:
                seen.add(v)
                todo.append(v)
    return [k for k, u in node.items() if u not in seen]


def _in_box(b, x, y, z, pad=8):
    return b[0] + pad < x < b[3] - pad and b[1] + pad < y < b[4] - pad and b[2] < z < b[5]


def openings(lay, S, K):
    """Openings that lead nowhere or into a wall: [(k, x, y, z, 'void'|'wall')]. An opening is used when another
    piece's opening meets it (the way in counts), or the space beyond it is the owner's own hall; a hall's
    exit piece only counts its corridor end."""
    P = lay['pieces']
    pts = []
    for k, p in enumerate(P):
        if p.get('gone') or not p.get('id'):
            continue
        for px, py, pz, ps in S['ports'].get(p['id']) or []:
            if p.get('hall') is not None and K.get('halls') == 'dwemer' and not (ps == 'N' and pz == 0):
                continue
            wx, wy = _rot(px, py, p['p'][5])
            side = _dir_of(*_rot(*SIDES[ps], p['p'][5]))
            pts.append((k, p['p'][0] + wx, p['p'][1] + wy, p['p'][2] + pz, side))
    e = lay.get('entrance') or {}
    out = []
    for k, x, y, z, side in pts:
        if 'x' in e and abs(e['x'] - x) < 24 and abs(e['y'] - y) < 24 and abs(e['z'] - z) < 24:
            continue
        if any(j != k and abs(x2 - x) < 24 and abs(y2 - y) < 24 and abs(z2 - z) < 24 and s2 == OPP[side] for j, x2, y2, z2, s2 in pts):
            continue
        dx, dy = SIDES[side]
        bx, by, bz = x + dx * 64, y + dy * 64, z + 40
        own = P[k].get('hall')
        inside = [j for j, q in enumerate(P) if j != k and not q.get('gone') and q.get('box') and _in_box(q['box'], bx, by, bz)]
        if own is not None and any(P[j].get('hall') == own for j in inside):
            continue
        # (a room's entry piece opens into its own tiles, which have no openings of their own)
        if any(P[j].get('hall') is not None and P[j].get('hall') == P[k].get('hall') for j in inside):
            continue
        if any(P[j].get('hall') is not None and P[k].get('hall') is not None for j in inside) and K.get('halls') != 'dwemer':
            continue
        out.append((k, round(x), round(y), round(z), 'wall' if inside else 'void'))
    return out


def clashes(lay):
    """Pieces whose boxes run into each other by more than their trims where they don't join: [(a, b)]."""
    P = lay['pieces']
    node = _nodes(lay)
    nb = defaultdict(set)
    for s in lay['seams']:
        a, b = node.get(s[4]), node.get(s[5])
        if a is not None and b is not None:
            nb[a].add(b)
            nb[b].add(a)
    live = sorted(node)
    out = []
    for i, a in enumerate(live):
        A = P[a]['box']
        for b in live[i + 1:]:
            if node[a] == node[b] or node[b] in nb[node[a]]:
                continue
            B = P[b]['box']
            if min(A[3], B[3]) - max(A[0], B[0]) > SLACK and min(A[4], B[4]) - max(A[1], B[1]) > SLACK and \
                    min(A[5], B[5]) - max(A[2], B[2]) > SLACK:
                out.append((a, b))
    return out


# ------------------------------------------------------------------ rays: leaks and room to walk
DIRS = []
for _k in range(16):
    _a = _k * math.pi / 8
    for _el in (-0.3, 0.0, 0.35):
        DIRS.append((math.cos(_a) * math.cos(_el), math.sin(_a) * math.cos(_el), math.sin(_el)))
# a ray that meets nothing this far out has seen the void (4000 before: a keep's straight corridor runs further, and
# every join along one of 6000 counted as open onto the void, 2026-10-29)
REACH = 20000


def scene(db, lay):
    import seethrough
    sc = seethrough.Scene()
    for p in lay['pieces']:
        if p.get('gone') or not p.get('id'):
            continue
        ri = db.resolve_id(p['id'])
        mo = db.recs[ri][5] if ri is not None else None
        if mo:
            sc.add_model(seethrough.model_tris(db, mo), p['p'], 1.0)
    # (and the frame a keep's short passage has in its middle, as the place is written: dwemer.build)
    K = lay.get('K') or {}
    if K.get('framed') and db.resolve_id(K['jamb']) is not None:
        jt = seethrough.model_tris(db, db.recs[db.resolve_id(K['jamb'])][5])
        for p in lay['pieces']:
            if p.get('id') in K['framed'] and not p.get('gone'):
                sc.add_model(jt, (p['p'][0], p['p'][1], p['p'][2], 0, 0, p['p'][5]), 1.0)
    # (the front door closes the way in: a wall across it, as the door and its frame stand there)
    e = lay.get('entrance') or {}
    if 'side' in e:
        dx, dy = SIDES[e['side']]
        cx, cy, z0, z1, w = e['x'] + dx * 8, e['y'] + dy * 8, e['z'] - 300, e['z'] + 600, 400
        a = (cx - dy * w, cy + dx * w)
        b = (cx + dy * w, cy - dx * w)
        sc.add([a[0], a[1], z0, b[0], b[1], z0, b[0], b[1], z1])
        sc.add([a[0], a[1], z0, b[0], b[1], z1, a[0], a[1], z1])
    return sc


def _probe(sc, x, y, z):
    """From over the floor near (x, y, z): (eye point, headroom) or None where there is no floor and roof."""
    dn = sc.nearest_any((x, y, z + 60), (0.0, 0.0, -1.0), 260)
    if dn is None:
        return None
    fz = z + 60 - dn[0]
    up = sc.nearest_any((x, y, fz + 4), (0.0, 0.0, 1.0), 1200)
    room = up[0] + 4 if up else None
    return (x, y, fz + min(70.0, (room or 140) / 2)), room, fz


_BASE = {}


def base(kind):
    """The game's own places of the kind (dgbase.json): {'pairs': {'a|b': [spots, spots seeing the void, joins,
    joins too tight]}, 'ids': {piece: [spots a step in from its joins, spots seeing the void]}}."""
    kind = {'tower': 'tomb'}.get(kind, kind)          # (a Velothi tower is the tombs' small pieces: their figures)
    if not _BASE:
        import json, os
        try:
            _BASE.update(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dgbase.json'))))
        except (OSError, ValueError):
            _BASE['_'] = ''
    return _BASE.get(kind) or {}


GAME_SHARE = 0.1        # a join the game's own show the void through (or squeeze) this often is as the game makes it


def _as_game(B, a, b, k, n):
    """Whether a fault at the join of pieces a and b is one the game's own joins of them have as often: k is
    the record's count of faults, n the count looked at."""
    g = (B.get('pairs') or {}).get('|'.join(sorted((a, b))))
    return bool(g) and g[n] >= 3 and g[k] / g[n] >= GAME_SHARE


def _leaky_piece(B, pid):
    """A piece the game's own places see the void from as often (a cave's dead end, 66-88% of its spots: open
    rock the game closes with nothing)."""
    g = (B.get('ids') or {}).get(pid)
    return bool(g) and g[0] >= 6 and g[1] / g[0] >= GAME_SHARE


def _drawn(sc, o, d):
    """Whether the first face a ray meets is met from its drawn side (the inside of a cave's shell)."""
    h = sc.nearest_any(o, d, 2000)
    return bool(h) and not sc.back_of(h[1], d)


def inside(sc, box, step=128):
    """Eye spots over the floor inside a piece's box (a grid, step apart) and how many of them see the void:
    (spots, seeing). A cave chamber's rock is open where the game closes it with big rock formations."""
    spots = seen = 0
    x = box[0] + step / 2
    while x < box[3]:
        y = box[1] + step / 2
        while y < box[4]:
            g = _probe(sc, x, y, box[2] + (box[5] - box[2]) * 0.6)
            # (only a spot inside the cave: the floor under it and the roof over it seen from their drawn
            # side. A spot on the rock's outside, over another piece's roof, sees the void and no one stands
            # there; such spots made most of a made chamber's count, the user's Bucci, 2026-10-26)
            if g and g[1] and g[1] > 90 and g[2] > box[2] and _drawn(sc, g[0], (0.0, 0.0, -1.0)) and _drawn(sc, g[0], (0.0, 0.0, 1.0)):
                spots += 1
                if any(sc.nearest_any(g[0], d, REACH) is None for d in DIRS):
                    seen += 1
            y += step
        x += step
    return spots, seen


def inside_share(kind, pid):
    """The share of eye spots inside the game's own pieces of this id that see the void (dgbase 'inside'), or
    None when the game shows too few."""
    g = (base(kind).get('inside') or {}).get(pid)
    return g[1] / g[0] if g and g[0] >= 10 else None


def seams_check(db, lay, sc=None, leaks=True, kind=None):
    """At each join: the void seen through it ([(k, x, y, z, rays out)]), and joins too low or narrow to walk
    ([(k, x, y, z, 'low'|'narrow', size)]); both where the game's own joins of the same two pieces don't do it
    as often (cave rock and tomb ramps let rays out in the game's own places too)."""
    sc = sc or scene(db, lay)
    P = lay['pieces']
    B = base(kind or (lay.get('K') or {}).get('kind') or 'dwemer')
    leak, tight = [], []
    # (a cave's way in is a piece of its own whose mouth the front door closes: not looked through)
    mouth = (lay.get('entrance') or {}).get('piece')
    for sx, sy, sz, side, a, b in lay['seams']:
        if P[a].get('gone') or P[b].get('gone'):
            continue
        if mouth is not None and mouth in (a, b):
            leaks_here = False
        else:
            leaks_here = leaks
        dx, dy = SIDES[side]
        ida, idb = P[a]['id'], P[b]['id']
        squeezed = _as_game(B, ida, idb, 3, 2)
        got = _probe(sc, sx, sy, sz)
        if got is None:
            if not squeezed:
                tight.append((b, round(sx), round(sy), round(sz), 'floor', 0))
            continue
        eye, room, fz = got
        if room is not None and room < HEADROOM and not squeezed:
            tight.append((b, round(sx), round(sy), round(sz), 'low', round(room)))
        # (across the way at waist height)
        wl = sc.nearest_any((sx, sy, fz + 50), (-dy, dx, 0.0), 600)
        wr = sc.nearest_any((sx, sy, fz + 50), (dy, -dx, 0.0), 600)
        if wl and wr and wl[0] + wr[0] < WIDTH and not squeezed:
            tight.append((b, round(sx), round(sy), round(sz), 'narrow', round(wl[0] + wr[0])))
        if not leaks_here or _as_game(B, ida, idb, 1, 0):
            continue
        # (and not by a piece the game's own see the void from: seen through from next door just the same)
        if _leaky_piece(B, ida) or _leaky_piece(B, idb):
            continue
        for off in (-48, 48):
            # (not behind a piece too thin to stand in: a keep closes a corridor's end with a wall 48 thick, and the
            # eye a step past the join stood behind it in the void)
            bx = P[b if off > 0 else a].get('box')
            if bx and (bx[3] - bx[0] if dx else bx[4] - bx[1]) < 100:
                continue
            g2 = _probe(sc, sx + dx * off, sy + dy * off, sz)
            if g2 is None:
                continue
            n = sum(1 for d in DIRS if sc.nearest_any(g2[0], d, REACH) is None)
            if n:
                leak.append((b if off > 0 else a, round(sx), round(sy), round(sz), n))
    return leak, tight


def check(db, lay, S, K, rays=True):
    """Every rule at once: {'up', 'deep', 'cut', 'open', 'clash', 'leak', 'tight'} lists (empty: fine)."""
    up, deep = heights(lay, S, K)
    out = {'up': up, 'deep': deep, 'cut': joined(lay), 'open': openings(lay, S, K), 'clash': clashes(lay)}
    if rays:
        out['leak'], out['tight'] = seams_check(db, lay, kind=K.get('kind'))
    else:
        out['leak'], out['tight'] = [], []
    return out


def ok(res):
    return not any(res.values())


def say(lay, res):
    """The first thing wrong, in one plain line saying where."""
    if res.get('up'):
        k, dz = res['up'][0]
        if climbs(lay):
            return '%s stands %d under the way in: in a place that climbs, the way in must be the lowest point.' % (where(lay, k).capitalize(), -dz)
        return '%s stands %d over the way in: the way in must be the highest point.' % (where(lay, k).capitalize(), dz)
    if res.get('deep'):
        k, dz = res['deep'][0]
        if climbs(lay):
            return '%s climbs %d over the way in, higher than the game\'s own of the kind.' % (where(lay, k).capitalize(), dz)
        return '%s goes %d below the way in, deeper than the game\'s own of the kind.' % (where(lay, k).capitalize(), -dz)
    if res.get('cut'):
        return '%s is not joined to the rest.' % where(lay, res['cut'][0]).capitalize()
    if res.get('open'):
        k, x, y, z, what = res['open'][0]
        return '%s has an opening %s at (%d, %d).' % (where(lay, k).capitalize(), 'into a wall' if what == 'wall' else 'onto nothing', x, y)
    if res.get('clash'):
        a, b = res['clash'][0]
        return '%s runs into %s.' % (where(lay, a).capitalize(), where(lay, b))
    if res.get('leak'):
        k, x, y, z, n = res['leak'][0]
        return 'The join by %s at (%d, %d) shows the void.' % (where(lay, k), x, y)
    if res.get('tight'):
        k, x, y, z, what, size = res['tight'][0]
        return 'The join by %s at (%d, %d) is too %s to walk through.' % (where(lay, k), x, y, {'low': 'low', 'narrow': 'narrow'}.get(what, 'broken'))
    return ''
