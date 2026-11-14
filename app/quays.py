"""Stone quays with ships for a town of the Anvil or Gold Coast styles that stands on the water.

Anvil's harbour, measured (docs/cyrodiil-study-2026-11.md): stone quays of t_imp_setgc_x_dockstown* pieces run out from
the shore as fingers, 512 a piece and 276 wide, their deck 200 over the water (the piece's origin at z 32, the deck 166
over it, the piece reaching 1,400 down), a post (dockstowncolmn_01) along their edges every 320; the big ships lie
between them at z 8 to 64, each 320 to 760 from the nearest dock piece, over water 340 to 700 deep.

Built anew here, never a game quay copied: for_town() finds the town's shore, runs a finger of whole pieces out from
it where the water deepens, closes it with an end piece, stands its posts, and moors a ship beside it where the water
is deep enough for one.
"""
import math
import random

import mapdata

CULTURES = ('Anvil', 'Gold Coast')
PIECE = 't_imp_setgc_x_dockstowncent_01'       # 512 long (its x), 276 wide
END = 't_imp_setgc_x_dockstownend_01'          # stands 256 on from the last piece's middle, the same way round
POST = 't_imp_setgc_x_dockstowncolmn_01'
SHIPS = (('t_imp_setharbor_tradeship_01', 760.0, 1500.0, 48.0), ('t_imp_setharbor_galleon_01', 600.0, 1900.0, 56.0),
         ('t_imp_setharbor_cutter_01', 300.0, 1300.0, 32.0))      # (id, half its beam, half its length, the z it floats at)
# (where no ship fits, a narrow inlet: the sailing longboat, 590 by 1,510, at z 80 over water 200 to 500 deep in the game)
SMALLER = (('t_com_setharbor_boatlong_01', 300.0, 760.0, 80.0),)
DEEP_SMALL = -150.0
BOAT = ('t_imp_setharbor_rowboat', 60.0, 183.0, 4.0)
DECK_Z = 32.0                  # the pieces' origin: the deck then stands 198 over the water
POST_DZ = 26.0                 # a post's origin over its piece's (the game's)
STEP = 512.0
MOST = 5                       # pieces a finger at most (Anvil's run 2 to 6)
LEAST = 2
ROOT_GROUND = (20.0, 150.0)    # the shore a finger starts from: dry, just over the water's edge
ROOT_BACK = (192.0, 12.0)      # (and the ground this far behind it this high at least: the land's own edge, not a bar)
ROOT_CLEAR = 460.0             # (nothing 200 across or more standing this near the finger's first pieces: a boulder, a tree)
MOST_BY = {'village': 3, 'town': 4, 'city': 5}
DEEP = -230.0                  # the sea floor under most of a ship: this far down at least (the game's ships: 340 to 700)
SHOAL = -48.0                  # (and nowhere under her higher than this: no part of her over a beach)
APART = 2300.0                 # two fingers no nearer than this
FINGERS = {'village': 1, 'town': 2, 'city': 3}
LAST = {}


def _g(db, x, y):
    return mapdata.terrain_z(db, x, y)


def _inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
    return c


def _seg_dist(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if not l2 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
    return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def _roots(db, poly, step=192.0):
    """Shore spots inside the town's outline (or within 600 of it) where the water lies one way: [(x, y, way out)]."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    out = []
    x = min(xs) - 600
    while x <= max(xs) + 600:
        y = min(ys) - 600
        while y <= max(ys) + 600:
            g = _g(db, x, y)
            if g is not None and ROOT_GROUND[0] <= g <= ROOT_GROUND[1] and \
                    (_inside(poly, x, y) or min(_seg_dist(x, y, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))) <= 600):
                best = None
                for a in range(0, 360, 15):
                    ar = math.radians(a)
                    zs = [_g(db, x + math.cos(ar) * d, y + math.sin(ar) * d) for d in (384.0, 768.0, 1152.0)]
                    if any(z is None for z in zs) or zs[0] > -24 or zs[1] > -96 or zs[2] > -128:
                        continue
                    zb = _g(db, x - math.cos(ar) * ROOT_BACK[0], y - math.sin(ar) * ROOT_BACK[0])
                    if zb is None or zb < ROOT_BACK[1]:
                        continue
                    depth = -sum(zs) / 3.0
                    if best is None or depth > best[0]:
                        best = (depth, ar)
                if best:
                    out.append((x, y, best[1], best[0]))
            y += step
        x += step
    return out


def _standing(db, poly):
    """Where the big things stand in the cells round an outline (rocks, trees, buildings): [(x, y)]."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    out = []
    for gx in range(int(math.floor((min(xs) - 1500) / 8192.0)), int(math.floor((max(xs) + 1500) / 8192.0)) + 1):
        for gy in range(int(math.floor((min(ys) - 1500) / 8192.0)), int(math.floor((max(ys) + 1500) / 8192.0)) + 1):
            try:
                refs = mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()
            except Exception:
                continue
            for r in refs:
                b = r.get('b')
                if b and r.get('type') in ('STAT', 'ACTI', 'CONT') and max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0) >= 200:
                    out.append((r['p'][0], r['p'][1]))
    return out


def _finger(db, x, y, a, bars, most=MOST):
    """The pieces of a finger from the shore spot out the way a: [(x, y)] middles, or [] where it would not stand."""
    ux, uy = math.cos(a), math.sin(a)
    mids = []
    for k in range(most):
        mx, my = x + ux * (STEP * (k + 0.5)), y + uy * (STEP * (k + 0.5))
        g = _g(db, mx, my)
        # (it stops where the water shoals again: a finger of five pieces bridged a 2,000 inlet to its far bank)
        if g is None or (k > 0 and g > -16) or g < -1300 or (k > 1 and g > -110):
            break
        if any(_seg_dist(mx, my, s0, s1) < 420 for s0, s1 in bars):
            break
        mids.append((mx, my))
    return mids if len(mids) >= LEAST else []


def _moor(db, x, y, a, L, bars, rng, ships, others):
    """A ship beside the finger that runs L out from (x, y) the way a: {'id', 'p', 's', 'role': 'ship'} or None. Her
    length along the finger, her middle by its outer end; deep water under most of her and none of it shoal (the first
    rule wanted the full depth under her whole length, the shoreward end too, and two ports got rowing boats only);
    clear of the sea wall and of the other ships."""
    ux, uy = math.cos(a), math.sin(a)
    small = [s for s in SMALLER if db.resolve_id(s[0]) is not None]
    order = (rng.sample(ships, len(ships)) if ships else []) + small
    for sid, beam, half, fz in order:
        DEEP_ = DEEP if half > 1000 else DEEP_SMALL
        for along in (max(L * 0.8, half * 0.9), L + half * 0.35, max(L * 0.55, half * 0.75)):
            for side in rng.sample((-1.0, 1.0), 2):
                off = 138.0 + beam + 90.0
                sx = x + ux * along - uy * side * off
                sy = y + uy * along + ux * side * off
                spots = [(sx + ux * t, sy + uy * t) for t in (-half, -half / 2, 0.0, half / 2, half)]
                spots.append((sx - uy * side * beam, sy + ux * side * beam))
                zs = [_g(db, qx, qy) for qx, qy in spots]
                # (deep under her middle and most of her length; her shoreward end may lie over the shallows)
                if any(z is None or z > SHOAL for z in zs) or zs[2] > DEEP_ or sum(1 for z in zs if z <= DEEP_) < 3:
                    continue
                if any(_seg_dist(qx, qy, s0, s1) < beam + 200 for qx, qy in spots for s0, s1 in bars):
                    continue
                if any(math.hypot(sx - o['p'][0], sy - o['p'][1]) < 2200 for o in others):
                    continue
                # (her length is her model's y: turned so it runs along the finger, bow out or in by the seed)
                srz = (math.atan2(ux, uy) + (math.pi if rng.random() < 0.5 else 0.0)) % (2 * math.pi)
                return {'id': sid, 'p': [round(sx, 1), round(sy, 1), fz, 0.0, 0.0, round(srz, 5)], 's': 1.0, 'role': 'ship'}
    # (a narrow channel: across the finger's head, her length along the channel)
    for sid, beam, half, fz in order:
        DEEP_ = DEEP if half > 1000 else DEEP_SMALL
        hx, hy = x + ux * (L + beam + 80.0), y + uy * (L + beam + 80.0)
        spots = [(hx - uy * t, hy + ux * t) for t in (-half, -half / 2, 0.0, half / 2, half)]
        spots.append((hx + ux * beam, hy + uy * beam))
        zs = [_g(db, qx, qy) for qx, qy in spots]
        if any(z is None or z > SHOAL for z in zs) or zs[2] > DEEP_ or sum(1 for z in zs if z <= DEEP_) < 3:
            continue
        if any(_seg_dist(qx, qy, s0, s1) < beam + 200 for qx, qy in spots for s0, s1 in bars):
            continue
        if any(math.hypot(hx - o['p'][0], hy - o['p'][1]) < 2200 for o in others):
            continue
        srz = (math.atan2(-uy, ux) + (math.pi if rng.random() < 0.5 else 0.0)) % (2 * math.pi)
        return {'id': sid, 'p': [round(hx, 1), round(hy, 1), fz, 0.0, 0.0, round(srz, 5)], 's': 1.0, 'role': 'ship'}
    return None


def ships_for(db, fingers, seed=1, bars=()):
    """Ships for fingers that stand already: fingers [(x, y, way out, length)]; [{'id', 'p', 's', 'role'}]."""
    rng = random.Random('%s|ships' % seed)
    ships = [s for s in SHIPS if db.resolve_id(s[0]) is not None]
    out = []
    for x, y, a, L in fingers:
        sh_ = _moor(db, x, y, a, L, list(bars), rng, ships, out)
        if sh_:
            out.append(sh_)
    return out


def for_town(db, plan, W=None, seed=1, avoid=()):
    """[{'id', 'p', 's', 'role': 'quay'}] for a made town: its fingers, their posts, a ship at each where the water takes
    one. Nothing for a town of another style, or one with no shore of its own. avoid: [(x, y, r)] kept clear of."""
    LAST.clear()
    cult = plan.get('culture') or ''
    if cult not in CULTURES or any(db.resolve_id(i) is None for i in (PIECE, END)):
        return []
    poly = [tuple(p[:2]) for p in (W or {}).get('outline') or plan.get('wall_outline') or plan.get('drawn') or ()]
    if len(poly) < 3:
        pts = [(q['x'], q['y']) for q in plan.get('plots') or ()]
        if len(pts) < 3:
            return []
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        r = max(math.hypot(p[0] - cx, p[1] - cy) for p in pts) + 900
        poly = [(cx + r * math.cos(i * math.pi / 4), cy + r * math.sin(i * math.pi / 4)) for i in range(8)]
    rng = random.Random('%s|%s|quays' % (seed, cult))
    roots = _roots(db, poly)
    LAST['roots'] = len(roots)
    if not roots:
        return []
    # (a wall's pieces in the water bar a finger: it stops short of the sea wall)
    bars = []
    for p in (W or {}).get('pieces') or ():
        if p.get('sea') and p.get('corners'):
            c = p['corners']
            bars.append((((c[0][0] + c[3][0]) / 2, (c[0][1] + c[3][1]) / 2), ((c[1][0] + c[2][0]) / 2, (c[1][1] + c[2][1]) / 2)))
    n_built = sum(1 for q in plan.get('plots') or () if q.get('b'))
    size = 'village' if n_built < 12 else 'town' if n_built < 25 else 'city'
    want = FINGERS[size]
    stand = _standing(db, poly)
    roots.sort(key=lambda r: -r[3])
    out, laid = [], []
    # (a village's quay takes a sailing boat, never a galleon: the game's big ships lie at Anvil's quays alone)
    ships = [] if size == 'village' else [s for s in SHIPS if db.resolve_id(s[0]) is not None]
    for x, y, a, _depth in roots:
        if len(laid) >= want:
            break
        if any(math.hypot(x - o[0], y - o[1]) < APART for o in laid):
            continue
        if any(math.hypot(x - v[0], y - v[1]) < v[2] + 300 for v in avoid):
            continue
        mids = _finger(db, x, y, a, bars, MOST_BY[size])
        if not mids:
            continue
        if any(math.hypot(sx_ - px_, sy_ - py_) < ROOT_CLEAR for sx_, sy_ in stand for px_, py_ in [(x, y)] + mids[:2]):
            continue
        ux, uy = math.cos(a), math.sin(a)
        rz = math.atan2(-uy, ux) % (2 * math.pi)        # (a piece's x along the way out)
        for mx, my in mids:
            out.append({'id': PIECE, 'p': [round(mx, 1), round(my, 1), DECK_Z, 0.0, 0.0, round(rz, 5)], 's': 1.0, 'role': 'quay'})
        ex, ey = mids[-1][0] + ux * STEP / 2.0, mids[-1][1] + uy * STEP / 2.0
        out.append({'id': END, 'p': [round(ex, 1), round(ey, 1), DECK_Z, 0.0, 0.0, round(rz, 5)], 's': 1.0, 'role': 'quay'})
        if db.resolve_id(POST) is not None:
            px, py = -uy, ux
            for k in range(len(mids) + 1):
                for side in (-1.0, 1.0):
                    qx = x + ux * STEP * k + px * side * 124.0
                    qy = y + uy * STEP * k + py * side * 124.0
                    if k == 0 and (_g(db, qx, qy) or 0) > 40:
                        continue                     # (no post standing on the bank)
                    out.append({'id': POST, 'p': [round(qx, 1), round(qy, 1), DECK_Z + POST_DZ, 0.0, 0.0, round(rz, 5)], 's': 1.0, 'role': 'quay'})
        laid.append((x, y, a, len(mids)))
        # the ship: beside the finger's outer half, its length along it, over deep water, clear of the wall
        L = STEP * len(mids)
        sh_ = _moor(db, x, y, a, L, bars, rng, ships, [o for o in out if o.get('role') == 'ship'])
        done = sh_ is not None
        if sh_:
            out.append(sh_)
        if not done and db.resolve_id(BOAT[0]) is not None:
            bx, by = x + ux * L * 0.6 + uy * 230.0, y + uy * L * 0.6 - ux * 230.0
            if (_g(db, bx, by) or 0) < -40:
                out.append({'id': BOAT[0], 'p': [round(bx, 1), round(by, 1), BOAT[3], 0.0, 0.0, round(math.atan2(ux, uy) % (2 * math.pi), 5)], 's': 1.0, 'role': 'boat'})
    LAST.update(fingers=len(laid), pieces=sum(f[3] for f in laid), ships=sum(1 for o in out if o['role'] == 'ship'), boats=sum(1 for o in out if o['role'] == 'boat'))
    return out
