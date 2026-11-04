"""The story layer of a made town's dressing: the ground between its houses given owners. Each house plot's back and
sides are its yard, fenced in the culture's own fence; the yard gets one kind of life (a kitchen yard, a garden, a
workshop yard, a pen) as a set of the Workshop's own, laid against the house's back; a planter or two by the door.

The survey dressing (towndress, townlife) lays what the game lays at the game's rates: scenes before doors, groups along
streets, stalls and storage. It never decides what a patch of ground is FOR, so the ground between houses read as a
lawn (the user, 2026-11-03: "fill the empty space in between homes and roads with more things, namely planters,
stalls, trees, more crates and boxes"; the brainstorm: "fences that divide the grass into yards, then one yard kind per
house"). Sets here are hand-written in a frame: x across the house's back (right-handed, facing the back fence),
y into the yard from the house's back wall, z over the ground. Things that would stand in something are left out.
"""
import math
import random

import mapdata

# the culture's fence: straights by length (longest first) and a post for the ends; the long axis is the piece's x
FENCES = {
    'Imperial': {'runs': [('t_imp_set_fence_03', 264), ('t_imp_set_fence_01', 134)], 'post': 't_imp_set_fence_02'},
    'Common': {'runs': [('t_imp_set_fence_03', 264), ('t_imp_set_fence_01', 134)], 'post': 't_imp_set_fence_02'},
    'Gold Coast': {'runs': [('t_imp_set_fence_03', 264), ('t_imp_set_fence_01', 134)], 'post': 't_imp_set_fence_02'},
    'Nord': {'runs': [('t_nor_setfarm_x_fencelent_01', 380), ('t_nor_setfarm_x_fencelent_02', 380)], 'post': 't_nor_setfarm_x_fencepost_01'},
    'Breton': {'runs': [('t_bre_setfarm_x_fencelent_01', 380), ('t_bre_setfarm_x_fencelent_02', 380)], 'post': 't_bre_setfarm_x_fencepost_01'},
    'Redguard': {'runs': [('t_rga_setrihad_x_fencestr_01', 390)], 'post': 't_rga_setrihad_x_fencepost_01'},
    'Orc': {'runs': [('t_orc_setnomad_x_fence_01', 288), ('t_orc_setnomad_x_fence_02', 295)], 'post': None},
    'Hlaalu': {'runs': [('t_de_set_x_woodfence_01', 257), ('t_de_set_x_woodfence_01_128', 128)], 'post': None},
    'Velothi': {'runs': [('t_de_set_x_woodfence_01', 257), ('t_de_set_x_woodfence_01_128', 128)], 'post': None},
    'Redoran': {'runs': [('t_de_set_x_woodfence_02', 257), ('t_de_set_x_woodfence_02_128', 128)], 'post': None},
    'Dunmer common': {'runs': [('t_de_set_x_woodfence_01', 257), ('t_de_set_x_woodfence_01_128', 128)], 'post': None},
}
FENCE_KIN = {'Anvil': 'Imperial', 'Imperial Legion': 'Imperial', 'Indoril': 'Velothi', 'Mournhold': 'Velothi'}
FENCE_IN = 24                  # a fence stands this far inside the plot's edge (two plots' fences never meet)
FENCE_GAP = 6                  # (and pieces this far apart along the run)
FENCE_SHARE = 0.8              # (a run is laid when this share of its pieces fit, else none of it: no stray stakes)
YARD_D = 440                   # a yard reaches this far behind the house's back wall (the plot cut for a house is
                               # smaller than the house, so the plot's own back is no guide)
YARD_MIN = 320                 # a yard with less than this behind the house gets no set, only its fence
THING = 44                     # a set thing's own room on the ground (half a side)
PLANTERS = ['furn_planter_01', 'furn_planter_02', 'furn_planter_03', 'furn_com_planter']

# the yard kinds: [(id, x, y, dz, rz)] in the yard frame, y from the house's back wall; alternatives by id prefix are
# tried in order and the first the load order has is used
KINDS = {
    'kitchen': [('barrel_01', -150, 60, 0, 0.0), ('barrel_02', -95, 60, 0, 0.4), ('com_sack_01', 40, 50, 0, 1.1), ('com_sack_02', 80, 55, 0, 2.0),
                ('com_basket_01', 130, 70, 0, 0.3), ('misc_com_bucket_01', 170, 60, 0, 0.0), ('t_com_var_cagechicken_01', -40, 170, 0, 1.6),
                ('crate_01', 150, 200, 0, 0.2)],
    'garden': [('com_basket_02', -170, 60, 0, 0.0), ('misc_com_bucket_01', 160, 50, 0, 0.0)],
    'workshop': [('crate_01', -140, 70, 0, 0.0), ('crate_02', -140, 70, 64, 0.5), ('crate_01', -70, 70, 0, 0.1), ('barrel_01', 60, 60, 0, 0.0),
                 ('barrel_01', 120, 60, 0, 0.9), ('t_com_furn_wheelbarrow_01', 10, 210, 0, 1.3), ('com_sack_02', 180, 70, 0, 0.0)],
    'pen': [('t_com_setfarm_haybale_01', -120, 200, 0, 0.3), ('t_com_setfarm_haybale_01', -40, 220, 0, 1.2), ('t_imp_setfarm_foodtrough_01', 100, 120, 0, 1.571),
            ('t_com_setfarm_haypile_01', 150, 260, 0, 0.0)],
}
# a garden's rows: the culture's own crops, three rows of them, three to a row
CROPS = {'Dunmer': ['flora_saltrice_01', 'flora_marshmerrow_01', 'flora_comberry_01'],
         'Imperial': ['flora_wickwheat_01', 'flora_comberry_01', 'flora_green_lichen_01'],
         'Nord': ['flora_wickwheat_01', 'flora_heather_01', 'flora_comberry_01'],
         'Breton': ['flora_wickwheat_01', 'flora_comberry_01', 'flora_heather_01'],
         'Redguard': ['flora_wickwheat_01', 'flora_comberry_01', 'flora_ash_yam_01']}
KIND_BY = {'house': ['kitchen', 'garden', 'kitchen', 'pen'], 'manor': ['garden', 'kitchen'], 'shop': ['workshop', 'kitchen'],
           'tavern': ['kitchen', 'workshop'], 'farm': ['pen', 'garden'], 'shack': ['kitchen', 'garden']}
LAST = {}                      # (the last town's figures, for the checks)


def _unit(x, y):
    h = math.hypot(x, y) or 1.0
    return x / h, y / h


def _rect(cx, cy, dx, dy, half_x, half_y):
    """The corners of a box half_x along (dx, dy) and half_y across it, at (cx, cy)."""
    nx, ny = -dy, dx
    return [(cx + dx * sx * half_x + nx * sy * half_y, cy + dy * sx * half_x + ny * sy * half_y) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _inside(poly, x, y):
    c = False
    n = len(poly)
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax:
            c = not c
    return c


def _overlap(a, b):
    import townplan
    return townplan._overlap(a, b)


class _Space:
    def __init__(self, polys):
        self.polys = [list(p) for p in polys]

    def free(self, pts):
        return not any(_overlap(pts, p) for p in self.polys)

    def take(self, pts):
        self.polys.append(pts)


def _bounds(db, memo, rid):
    low = rid.lower()
    if low not in memo:
        ri = db.resolve_id(rid)
        memo[low] = mapdata.object_bounds(db, ri) if ri is not None else None
    return memo[low]


def _first(db, *ids):
    for i in ids:
        if i and db.resolve_id(i) is not None:
            return i
    return None


def _ground_z(db, b, x, y):
    g = mapdata.terrain_z(db, x, y)
    if g is None:
        return None
    # (the piece's foot on the ground: most statics stand at their origin; one with its mesh starting over it is sunk)
    return g - (b[2] if b and b[2] > 0 else 0.0)


def _fence_run(db, space, memo, F, a, b, inward):
    """A fence from a to b along a plot's edge, FENCE_IN inside it (inward: the unit normal into the plot): pieces of
    the culture's lengths, longest first, a post at each end. [(id, (x, y, z, 0, 0, rz), 1.0)] or [] when the run
    could not be laid mostly whole."""
    dx, dy = _unit(b[0] - a[0], b[1] - a[1])
    ax, ay = a[0] + inward[0] * FENCE_IN, a[1] + inward[1] * FENCE_IN
    bx, by = b[0] + inward[0] * FENCE_IN, b[1] + inward[1] * FENCE_IN
    L = math.hypot(bx - ax, by - ay)
    runs = [(i, n) for i, n in F['runs'] if db.resolve_id(i) is not None]
    if not runs or L < runs[-1][1]:
        return []
    rz = math.atan2(-dy, dx) % (2 * math.pi)     # (the piece's x along the run)
    out, t, want, got = [], 0.0, 0, 0
    while True:
        piece = next(((i, n) for i, n in runs if t + n <= L + 1), None)
        if piece is None:
            break
        rid, n = piece
        bb = _bounds(db, memo, rid)
        if not bb:
            break
        mx, my = ax + dx * (t + n / 2.0), ay + dy * (t + n / 2.0)
        # (the piece's bounds centre on the run's middle: its origin may sit at an end)
        cx_, cy_ = (bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0
        ox = mx - (cx_ * dx + cy_ * (-dy) * 0) - 0  # placeholder, replaced below
        c, s = math.cos(rz), math.sin(rz)
        # world offset of the local bounds centre under the turn (local x along (dx, dy), local y along inward-ish)
        wx = cx_ * dx - cy_ * dy
        wy = cx_ * dy + cy_ * dx
        px, py = mx - wx, my - wy
        want += 1
        rect = _rect(mx, my, dx, dy, n / 2.0 - 2, max(14.0, (bb[4] - bb[1]) / 2.0))
        z = _ground_z(db, bb, px, py)
        if z is not None and space.free(rect):
            out.append((rid, (px, py, z, 0.0, 0.0, rz), 1.0, rect))
            got += 1
        t += n + FENCE_GAP
    if not want or got < FENCE_SHARE * want:
        return []
    for _rid, _p, _s, rect in out:
        space.take(rect)
    laid = [(rid, p, s) for rid, p, s, _r in out]
    post = F.get('post')
    if post and db.resolve_id(post) is not None:
        pb = _bounds(db, memo, post)
        for ex, ey in ((ax, ay), (ax + dx * min(L, t), ay + dy * min(L, t))):
            z = _ground_z(db, pb, ex, ey)
            if z is not None:
                laid.append((post, (ex, ey, z, 0.0, 0.0, rz), 1.0))
    return laid


def _plot_frame(q):
    """(c, s): the unit vectors of the plot's x (across, to the right facing out of the door) and y (into the plot,
    away from the street), as townplan._rect lays them."""
    fx, fy = math.sin(q['face']), math.cos(q['face'])
    Y = (-fx, -fy)
    return (Y[1], -Y[0]), Y                           # (x as the placement turn lays a set's x: to the right facing in)


def _lay_set(db, space, memo, things, ox, oy, X, Y, kind):
    """A set's things in the yard frame at (ox, oy) with x along X and y along Y, each on free ground; the set is laid
    when most of it fits."""
    placed, rects = [], []
    rz0 = math.atan2(-Y[1] * 0 + X[0] * 0 + Y[0], Y[1]) if False else math.atan2(Y[0], Y[1])
    for rid, lx, ly, dz, rz in things:
        if db.resolve_id(rid) is None:
            continue
        bb = _bounds(db, memo, rid)
        if not bb:
            continue
        wx = ox + X[0] * lx + Y[0] * ly
        wy = oy + X[1] * lx + Y[1] * ly
        half = max(THING, (bb[3] - bb[0]) / 2.0, (bb[4] - bb[1]) / 2.0)
        rect = _rect(wx, wy, X[0], X[1], half, half)
        z = _ground_z(db, bb, wx, wy)
        if z is None or not space.free(rect):
            continue
        placed.append((rid, (wx, wy, z + dz, 0.0, 0.0, (rz + rz0) % (2 * math.pi)), 1.0))
        rects.append(rect)
    if len(placed) < 0.5 * max(1, sum(1 for t in things if db.resolve_id(t[0]) is not None)):
        return []
    for r in rects:
        space.take(r)
    return placed


def _garden_rows(db, space, memo, cult, ox, oy, X, Y, width, depth, rng):
    crops = CROPS.get(cult) or CROPS['Imperial']
    crop = _first(db, *rng.sample(crops, len(crops)))
    if not crop:
        return []
    bb = _bounds(db, memo, crop)
    out, rects = [], []
    rows = max(1, min(3, int(depth // 110)))
    per = max(2, min(5, int(width // 100)))
    for r in range(rows):
        ly = 70 + r * 100
        for k in range(per):
            lx = -width / 2.0 + 50 + k * (width - 100) / max(1, per - 1)
            wx, wy = ox + X[0] * lx + Y[0] * ly, oy + X[1] * lx + Y[1] * ly
            rect = _rect(wx, wy, X[0], X[1], 36, 36)
            z = _ground_z(db, bb, wx, wy)
            if z is None or not space.free(rect):
                continue
            out.append((crop, (wx, wy, z, 0.0, 0.0, rng.uniform(0, 2 * math.pi)), rng.uniform(0.85, 1.1)))
            rects.append(rect)
    for r in rects:
        space.take(r)
    return out


def yards(db, plan, seed=1, blocked=(), also=(), amount=1.0):
    """[{'id', 'p', 's', 'role'}]: fences, yard sets, garden rows and planters for a made town (plan as townbuild.fit
    left it). blocked: polygons kept clear (the wall); also: [(id, p)] things laid already (the dressing's), kept
    clear of."""
    import towndress
    cult = plan.get('culture') or 'Imperial'
    F = FENCES.get(cult) or FENCES.get(FENCE_KIN.get(cult, ''), None)
    rng = random.Random('%s|%s|story' % (seed, cult))
    memo = {}
    rects = [[tuple(p) for p in q['rect']] for q in plan['plots'] if q.get('rect') and q.get('b')]
    polys = list(blocked) + rects + [[tuple(p) for p in o] for o in plan.get('obstacles') or ()]
    for q in plan['plots']:
        if q.get('door') and q.get('b'):
            polys.append(towndress._door_clear(q['door'][0], q['door'][1], q['face']))
    polys += towndress._street_polys(plan, towndress.STREET_BLOCK_SHARE)
    for rid, p in also:
        bb = _bounds(db, memo, rid)
        half = max(24.0, (bb[3] - bb[0]) / 2.0 if bb else 24.0, (bb[4] - bb[1]) / 2.0 if bb else 24.0)
        polys.append(_rect(p[0], p[1], 1.0, 0.0, half, half))
    space = _Space(polys)
    out = []
    n = {'fences': 0, 'posts': 0, 'sets': 0, 'things': 0, 'crops': 0, 'planters': 0, 'yards': 0, 'no room': 0}
    crop_cult = 'Dunmer' if cult in ('Hlaalu', 'Velothi', 'Redoran', 'Dunmer common', 'Indoril', 'Mournhold', 'Telvanni') else cult
    for q in plan['plots']:
        if not q.get('b') or not q.get('rect') or rng.random() > amount:
            continue
        X, Y = _plot_frame(q)
        cx, cy = q['x'], q['y']
        # the house's back and sides in the plot frame, from its own footprint
        ys = [(p[0] - cx) * Y[0] + (p[1] - cy) * Y[1] for p in q['rect']]
        xs = [(p[0] - cx) * X[0] + (p[1] - cy) * X[1] for p in q['rect']]
        back, front, xl, xr = max(ys), min(ys), min(xs), max(xs)
        w = xr - xl
        depth = YARD_D
        n['yards'] += 1
        # the fence: the yard's back edge, YARD_D behind the house, and its two sides from the house's back corners
        if F:
            at = lambda lx, ly: (cx + X[0] * lx + Y[0] * ly, cy + X[1] * lx + Y[1] * ly)
            far = {-1: at(xl, back + depth), 1: at(xr, back + depth)}
            near_ = {-1: at(xl, back + 30), 1: at(xr, back + 30)}
            runs = [(far[-1], far[1], (-Y[0], -Y[1])), (near_[-1], far[-1], (X[0], X[1])), (far[1], near_[1], (-X[0], -X[1]))]
            for a, b, inward in runs:
                laid = _fence_run(db, space, memo, F, a, b, inward)
                for rid, p, s in laid:
                    out.append({'id': rid, 'p': [round(v, 2) for v in p], 's': s, 'role': 'fence'})
                    n['posts' if rid == F.get('post') else 'fences'] += 1
        # the yard's kind, laid against the house's back
        if depth >= YARD_MIN:
            kinds = KIND_BY.get(q.get('kind') or 'house') or KIND_BY['house']
            kind = rng.choice(kinds)
            laid = []
            # (against the middle of the back wall, else to one side: a porch or the dressing's own things may stand
            # in the middle)
            for off in (0.0, w / 4.0, -w / 4.0):
                ox, oy = cx + X[0] * ((xl + xr) / 2.0 + off) + Y[0] * back, cy + X[1] * ((xl + xr) / 2.0 + off) + Y[1] * back
                laid = _lay_set(db, space, memo, KINDS[kind], ox, oy, X, Y, kind)
                if laid:
                    break
            if kind == 'garden':
                laid += _garden_rows(db, space, memo, crop_cult, ox, oy, X, Y, min(w, 480.0), depth - 60, rng)
            if laid:
                n['sets'] += 1
                n['things'] += sum(1 for r, _p, _s in laid if not r.startswith('flora'))
                n['crops'] += sum(1 for r, _p, _s in laid if r.startswith('flora'))
                out += [{'id': rid, 'p': [round(v, 2) for v in p], 's': round(s, 3), 'role': 'yard', 'kind': kind} for rid, p, s in laid]
            else:
                n['no room'] += 1
        # a planter by the door, the way the game's towns stand them by Imperial and Hlaalu doors
        if q.get('door') and rng.random() < 0.45:
            pl = _first(db, *rng.sample(PLANTERS, len(PLANTERS)))
            if pl:
                bb = _bounds(db, memo, pl)
                # (beside the door, against the house's front line: the footprint reaches past the door, porch and all)
                dlx = (q['door'][0] - cx) * X[0] + (q['door'][1] - cy) * X[1]
                side = rng.choice((-1, 1))
                px = cx + X[0] * (dlx + side * 175) + Y[0] * (front - 55)
                py = cy + X[1] * (dlx + side * 175) + Y[1] * (front - 55)
                rect = _rect(px, py, X[0], X[1], 40, 40)
                z = _ground_z(db, bb, px, py)
                if z is not None and space.free(rect):
                    space.take(rect)
                    out.append({'id': pl, 'p': [round(px, 2), round(py, 2), round(z, 2), 0.0, 0.0, round(math.atan2(Y[0], Y[1]) % (2 * math.pi), 4)], 's': 1.0, 'role': 'planter'})
                    n['planters'] += 1
    LAST.clear()
    LAST.update(n)
    return out


# ------------------------------------------------------------------ the fort's yard
# roles for the wall's stretches and the yard's middle, as sets in a frame: x along the wall (or across the yard),
# y into the yard from the wall, z over the ground. Alternatives for a piece are tried in order (the first the load
# order has is used)
FORT_SETS = {
    'smithy': {'back': 460, 'things': [(('furn_s_forge', 'furn_de_forge_01'), 0, 60, 0, 0.0), (('furn_anvil00',), -140, 170, 0, 1.2),
                                       (('furn_de_bellows_01',), 110, 80, 0, 0.0), (('barrel_01',), -230, 50, 0, 0.3),
                                       (('t_imp_furnp_grindstone_01',), 230, 150, 0, 2.6), (('crate_01',), -300, 70, 0, 0.0),
                                       (('misc_com_bucket_01',), 60, 200, 0, 0.0)]},
    'stables': {'back': 430, 'things': [(('t_com_setfarm_haypile_01',), -260, 70, 0, 0.0), (('t_com_setfarm_haybale_01',), -110, 50, 0, 0.4),
                                        (('t_com_setfarm_haybale_01',), -40, 60, 64, 1.9), (('t_imp_setfarm_foodtrough_01',), 110, 90, 0, 1.5708),
                                        (('barrel_01',), 260, 50, 0, 0.0), (('com_sack_01',), 300, 90, 0, 0.7), (('misc_com_bucket_01',), 180, 170, 0, 0.0)]},
    'stores': {'back': 420, 'things': [(('crate_01',), -140, 50, 0, 0.0), (('crate_02',), -140, 50, 64, 0.4), (('crate_01',), -70, 55, 0, 0.1),
                                       (('crate_02',), 10, 50, 0, 0.0), (('barrel_01',), 90, 45, 0, 0.0), (('barrel_02',), 150, 50, 0, 0.9),
                                       (('com_sack_02',), 220, 60, 0, 0.0), (('com_basket_01',), -210, 70, 0, 0.0),
                                       (('t_com_furn_wheelbarrow_01',), -290, 180, 0, 0.6)]},
    'shrine': {'back': 400, 'things': [(('furn_imp_altar_01', 'furn_velothi_altar_01'), 0, 50, 0, 0.0),
                                       (('light_com_candle_01', 'light_com_candle_02', 'light_de_candle_01'), -90, 40, 0, 0.0),
                                       (('light_com_candle_01', 'light_com_candle_02', 'light_de_candle_01'), 90, 40, 0, 0.0)]},
    'drill': {'back': None, 'things': [(('furn_practice_dummy', 't_com_furn_practicedummy'), -160, 0, 0, 0.0),
                                       (('furn_practice_dummy', 't_com_furn_practicedummy'), 160, 40, 0, 0.5),
                                       (('t_com_furn_target_01', 't_de_furn_target_01'), 0, 330, 0, 3.1416),
                                       (('t_com_furn_target_02', 't_com_furn_target_01'), 120, 350, 0, 3.1416)]},
}
BRAZIERS = ('light_com_brazier_01', 'light_imp_brazier_01', 'light_brazier_01', 'light_com_brazier', 'light_de_brazier_01', 'light_dae_brazier00')
GATE_SET_OFF = 1000            # the smithy this far along the wall from the gate (clear of the gatehouse's towers)
CORNER_IN = 560                # a brazier this far in from a yard corner (clear of the corner tower and the wall's pads)
FORT_LAST = {}


def fort(db, poly, gate, keep, free, taken, rng, style='Imperial'):
    """Sets with a job for a fort's yard: the smithy by the gate, the stables on the longest blank stretch, the stores
    and a shrine on the others, a drill ring in the middle, braziers in the corners. poly: the wall's outline (the
    yard); gate, keep: (x, y); free(x, y, r): ground not taken; taken: the castle's list to add ('disc', (x, y), r)
    to. [(id, (x, y, z, 0, 0, rz), s)]."""
    n = len(poly)
    if n < 3:
        return []
    memo = {}
    cx0, cy0 = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n

    def seg_d(px, py, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        return math.hypot(px - a[0] - dx * t, py - a[1] - dy * t), t * math.sqrt(L2)
    edges = []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        nrm = (-d[1], d[0])
        if (cx0 - a[0]) * nrm[0] + (cy0 - a[1]) * nrm[1] < 0:
            nrm = (-nrm[0], -nrm[1])
        edges.append({'a': a, 'b': b, 'd': d, 'n': nrm, 'L': math.hypot(b[0] - a[0], b[1] - a[1]),
                      'gate': seg_d(gate[0], gate[1], a, b), 'keep': seg_d(keep[0], keep[1], a, b)})
    gate_e = min(edges, key=lambda e: e['gate'][0])
    keep_e = min(edges, key=lambda e: e['keep'][0])
    rest = sorted((e for e in edges if e is not gate_e and e is not keep_e), key=lambda e: -e['L'])
    plan = []
    # (the smithy along the gate's wall, a way in from the gate; the stables, stores and shrine on the other walls,
    # longest first)
    t_g = gate_e['gate'][1]
    for t_s in (t_g + GATE_SET_OFF, t_g - GATE_SET_OFF):
        if 300 < t_s < gate_e['L'] - 300:
            plan.append(('smithy', gate_e, t_s))
            break
    for role, e in zip(('stables', 'stores'), rest):
        plan.append((role, e, e['L'] * rng.uniform(0.35, 0.65)))
    # (the shrine beside the keep, on its wall: a four-sided yard has only two free walls)
    t_k = keep_e['keep'][1]
    for t_s in (t_k + 900, t_k - 900):
        if 300 < t_s < keep_e['L'] - 300:
            plan.append(('shrine', keep_e, t_s))
            break
    out = []
    laid_roles = []
    tries = {}

    def fit(role, ox, oy, X, Y):
        # (the set's things on free ground at this spot: what fits, of how many)
        S_ = FORT_SETS[role]
        placed, discs = [], []
        rz0 = math.atan2(Y[0], Y[1])
        want = 0
        for alts, lx, ly, dz, rz in S_['things']:
            rid = _first(db, *alts)
            if not rid:
                continue
            want += 1
            bb = _bounds(db, memo, rid)
            wx, wy = ox + X[0] * lx + Y[0] * ly, oy + X[1] * lx + Y[1] * ly
            r = max(THING, (bb[3] - bb[0]) / 2.0 if bb else THING, (bb[4] - bb[1]) / 2.0 if bb else THING)
            # (against each other by their own sizes, a little closer than touching: the set is laid out packed on
            # purpose, and a stacked thing (dz) sits on the one under it)
            own = 0.45 * min((bb[3] - bb[0]), (bb[4] - bb[1])) if bb else THING * 0.6
            g = _ground_z(db, bb, wx, wy)
            if g is None or not free(wx, wy, r) or (dz <= 0 and any(math.hypot(wx - q[0], wy - q[1]) < own + q[3] for q in discs)):
                continue
            placed.append((rid, (wx, wy, g + dz, 0.0, 0.0, (rz + rz0) % (2 * math.pi)), 1.0))
            discs.append((wx, wy, r, own))
        return placed, discs, want

    def commit(role, placed, discs):
        out.extend(placed)
        for wx, wy, r, _own in discs:
            taken.append(('disc', (wx, wy), r))
        laid_roles.append(role)

    def lay(role, ox, oy, X, Y):
        placed, discs, want = fit(role, ox, oy, X, Y)
        if not want or len(placed) < 0.5 * want:
            return False
        commit(role, placed, discs)
        return True

    for role, e, t in plan:
        S_ = FORT_SETS[role]
        Y = e['n']
        X = (Y[1], -Y[0])
        # (the spot along the wall nearest the one asked for where most of the set fits: the wall's towers stand every
        # few lengths, and a set tried at one spot usually straddled one)
        spots = sorted((t_ for t_ in range(300, int(e['L']) - 300, 200)), key=lambda t_: abs(t_ - t))
        best = None
        most = (0, 0)
        for t_ in spots[:14]:
            ox, oy = e['a'][0] + e['d'][0] * t_ + Y[0] * S_['back'], e['a'][1] + e['d'][1] * t_ + Y[1] * S_['back']
            placed, discs, want = fit(role, ox, oy, X, Y)
            most = max(most, (len(placed), want))
            if want and len(placed) >= 0.5 * want and (best is None or len(placed) > len(best[0])):
                best = (placed, discs)
                if len(placed) == want:
                    break
        tries[role] = '%d of %d at best' % most
        if best:
            commit(role, best[0], best[1])
    # the drill ring: in the yard's middle, to one side of the way from the gate to the keep
    gk = _unit(keep[0] - gate[0], keep[1] - gate[1])
    side = (-gk[1], gk[0])
    for s in (1, -1):
        ox, oy = cx0 + side[0] * s * 700, cy0 + side[1] * s * 700
        if lay('drill', ox, oy, (gk[1], -gk[0]), gk):
            break
    # braziers in the corners
    br = _first(db, *BRAZIERS)
    if br:
        bb = _bounds(db, memo, br)
        for k in range(n):
            p = poly[k]
            prev, nxt = poly[k - 1], poly[(k + 1) % n]
            u1 = _unit(prev[0] - p[0], prev[1] - p[1])
            u2 = _unit(nxt[0] - p[0], nxt[1] - p[1])
            bis = _unit(u1[0] + u2[0], u1[1] + u2[1])
            wx, wy = p[0] + bis[0] * CORNER_IN, p[1] + bis[1] * CORNER_IN
            g = _ground_z(db, bb, wx, wy)
            if g is not None and free(wx, wy, 60):
                out.append((br, (wx, wy, g, 0.0, 0.0, 0.0), 1.0))
                taken.append(('disc', (wx, wy), 60.0))
                laid_roles.append('brazier')
    FORT_LAST.clear()
    FORT_LAST['roles'] = laid_roles
    FORT_LAST['things'] = len(out)
    FORT_LAST['tries'] = tries
    return out
