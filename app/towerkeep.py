"""A small tower keep on a hilltop, the Cyrodiil way: a square keep with round towers at its corners and a walled yard
before its door.

The game's own is Duskwatch Keep on Stirk (docs/cyrodiil-study-2026-11.md; the user, 2026-11-13: "Nice small keep for
the cyrodilic style"), measured in the keep's own frame, its door looking down its -y:
  the keep t_imp_legioncyr_x_keep_01 (848 square); its door frame at (7, -483, -227) and its door at (6, -420, -220),
  the threshold 24 over the ground before it, which lies 345 under the keep's origin;
  a small round tower at each front corner (415 either side, 502 out), a big one at a back corner (432, 442): stacks
  of a dark foot, a base 96 to 128 over it, a middle at +256, light storeys every 256 from +512, and a top (the small
  one's 256 over its last storey, the big one's roof 128 over its);
  the yard: the Legion wall on a grid of 512, a corner piece on each corner node turned as the side that leaves it, one
  side wall running from the keep's front tower, the far side's wall closing on the keep's flank; an arch
  (wallarch_01) in the side that faces down the hill with a buttressed length (walltower_01) beside it; the walls'
  origin 483 under the keep's; the yard's ground 175 to 220 under the door's; a well in the yard;
  the hill falls about 25 degrees from the keep, boulders all round it.

Built anew, never Duskwatch copied: the yard's size, which side it lies to, where its arch stands, how tall the towers
are and where the well stands are the seed's. make() levels the hilltop for the keep and a terrace for the yard, clears
what grew there, stands the pieces, and builds the keep's rooms with the keep maker's own layouts (keepmaker.py),
the door linked both ways."""
import math
import random

import mapdata
from editing import EditError

KEEP = 't_imp_legioncyr_x_keep_01'
FRAME = ('t_imp_legioncyr_x_kdoorframe_01', 7.0, -483.0, -227.0)
DOOR = ('ex_imp_loaddoor_03', 6.0, -420.0, -220.0)
WALL = 't_imp_legioncyr_x_wall_01'
CORNER = 't_imp_legioncyr_x_wallcorner_01'
ARCH = 't_imp_legioncyr_x_wallarch_01'
BUTTRESS = 't_imp_legioncyr_x_walltower_01'
WELL = ('t_imp_legioncyr_x_well_02', 106.0)                     # (its origin over the yard's ground, the game's)
SMALL = {'dark': 't_imp_legioncyr_x_towersdark_01', 'base': 't_imp_legioncyr_x_towersbase_01', 'med': 't_imp_legioncyr_x_towersmed_01',
         'ligt': 't_imp_legioncyr_x_towersligt_01', 'top': 't_imp_legioncyr_x_towerstop_01', 'base_dz': 106.0, 'top_dz': 256.0, 'foot': -508.0}
BIG = {'dark': 't_imp_legioncyr_x_towerbdark_01', 'base': 't_imp_legioncyr_x_towerbbase_01', 'med': 't_imp_legioncyr_x_towerbmed_01',
       'ligt': 't_imp_legioncyr_x_towerbligt_01', 'top': 't_imp_legioncyr_x_towerbrfp_01', 'base_dz': 96.0, 'top_dz': 128.0, 'foot': -265.0}
U = 512.0
DOOR_GROUND = 345.0            # the ground before the door lies this far under the keep's origin
WALL_DZ = -483.0               # the yard's walls: their origin against the keep's
YARD_DROP = 190.0              # the yard's ground under the door's (the game's 175 to 220)
FRONT_Y = -252.0               # the yard's near side, on the keep's flank (the game's wall there at -226 to -275)
SIDE_X = 408.0                 # the side wall that runs from the front tower: this far off the keep's middle
TOWER_FRONT = (415.0, -502.0)
TOWER_BACK = (432.0, 442.0)
CUT, RAISE = 700.0, 700.0      # how far the hill may be cut and filled for the keep's ground and its terrace
RAMP = (-560.0, -1130.0)       # the bank from the door's ground down to the yard's, in the keep's frame (about 18 degrees)
ROCKS = ('t_cyr_terrrockgc_rock_01', 't_cyr_terrrockgc_rock_02', 't_cyr_terrrockgc_rock_03', 't_cyr_terrrockgc_rock_04', 't_cyr_terrrockgc_rock_05')
LAST = {}


def ready(db):
    return all(db.resolve_id(i) is not None for i in (KEEP, FRAME[0], DOOR[0], WALL, CORNER, ARCH, SMALL['ligt'], BIG['ligt']))


def _frame(x, y, face):
    """The keep's frame for a door that looks along the unit vector face: (rz, to_world(lx, ly))."""
    rz = math.atan2(-face[0], -face[1]) % (2 * math.pi)
    c, s = math.cos(rz), math.sin(rz)
    return rz, (lambda lx, ly: (x + lx * c + ly * s, y - lx * s + ly * c))


def downhill(db, x, y, reach=1400.0):
    """The way the ground falls from a spot: the unit vector toward the lowest of sixteen points reach out, among those
    that stay land and fall no more than a terrace can take; None on flat or drowned ground."""
    g0 = mapdata.terrain_z(db, x, y)
    best = None
    for k in range(16):
        a = k * math.pi / 8
        zs = [mapdata.terrain_z(db, x + math.cos(a) * d, y + math.sin(a) * d) for d in (reach * 0.5, reach, reach * 1.4)]
        if g0 is None or any(z is None or z < 24 for z in zs):
            continue
        fall = g0 - zs[1]
        # (a fall of 150 to 650 over the yard's depth suits it best: the game's falls 400)
        cost = abs(fall - 400.0) + (2.0 * max(0.0, fall - 700.0))
        if best is None or cost < best[0]:
            best = (cost, a)
    return (math.cos(best[1]), math.sin(best[1])) if best else None


def plan(db, x, y, face=None, seed=1, top=None):
    """The keep's pieces and ground for a hilltop at (x, y): {'pieces': [{'id', 'p', 's', 'kind'}], 'levels': [(a, b,
    level)] ground lines, 'door': {...}, 'outline', 'k': the keep's origin height, 'face'}. face: the way its door looks
    (a unit vector); the way the ground falls when none is given."""
    if not ready(db):
        raise EditError('This load order has no Cyrodiil fort pieces (Tamriel Data) to build the keep of.')
    rng = random.Random('%s|tower keep' % seed)
    face = face or downhill(db, x, y) or (0.0, -1.0)
    h = math.hypot(face[0], face[1]) or 1.0
    face = (face[0] / h, face[1] / h)
    rz, W = _frame(x, y, face)
    # the top's level: what most of the ground under the keep already stands at, a little cut off the crown
    gs = sorted(g for g in (mapdata.terrain_z(db, *W(lx, ly)) for lx in (-400, -200, 0, 200, 400) for ly in (-600, -400, -200, 0, 200, 400)) if g is not None)
    if not gs:
        raise EditError('There is no land there.')
    A = gs[int(len(gs) * 0.35)] if top is None else float(top)      # (top: a level made for it, a rock raised from the sea)
    K = A + DOOR_GROUND
    side = rng.choice((1.0, -1.0))               # (the yard lies to the keep's left or right of its door)
    nx, ny = rng.choice((2, 2, 3)), rng.choice((2, 2, 3))
    ya = FRONT_Y
    yb = -764.0 - U * (ny - 1) - U               # (so the side wall's last length ends in the front tower)
    if side > 0:
        xa = -SIDE_X
        xb = xa + (nx + 1) * U
    else:
        xb = SIDE_X
        xa = xb - (nx + 1) * U
    T = lambda deg: (rz + math.radians(deg)) % (2 * math.pi)
    pieces = []

    def put(rid, lx, ly, dz, deg=0.0, kind='wall', s=1.0):
        wx, wy = W(lx, ly)
        pieces.append({'id': rid, 'p': [round(wx, 2), round(wy, 2), round(K + dz, 2), 0.0, 0.0, round(T(deg), 5)], 's': s, 'kind': kind, 'l': (lx, ly)})
    put(KEEP, 0.0, 0.0, 0.0, 0.0, 'keep')
    put(FRAME[0], FRAME[1], FRAME[2], FRAME[3], 0.0, 'frame')
    put(DOOR[0], DOOR[1], DOOR[2], DOOR[3], 0.0, 'door')
    # the round towers: one at each front corner, the big one at the back corner away from the yard
    def stack(S, lx, ly, storeys):
        b = S['foot']
        put(S['dark'], lx, ly, b, 0.0, 'tower')
        put(S['base'], lx, ly, b + S['base_dz'], 0.0, 'tower')
        put(S['med'], lx, ly, b + 256.0, 0.0, 'tower')
        for i in range(storeys):
            put(S['ligt'], lx, ly, b + 512.0 + 256.0 * i, 0.0, 'tower')
        put(S['top'], lx, ly, b + 512.0 + 256.0 * (storeys - 1) + S['top_dz'], rng.choice((0.0, 90.0, 180.0, 270.0)), 'tower')
    n_small = rng.choice((2, 2, 3))
    stack(SMALL, TOWER_FRONT[0], TOWER_FRONT[1], n_small)
    stack(SMALL, -TOWER_FRONT[0], TOWER_FRONT[1], n_small)
    stack(BIG, -side * TOWER_BACK[0], TOWER_BACK[1], rng.choice((2, 3, 3)))
    # the yard, walked clockwise (north, east, south, west sides turn 0, 90, 180, 270; a corner piece on a node turned
    # as the side that leaves it)
    gate_k = min(range(1, nx + 1), key=lambda k: abs(xb - U * k - DOOR[1]) + rng.random() * 300.0)
    butt_k = next((k for k in rng.sample(range(1, nx + 1), nx) if k != gate_k), None)
    for k in range(1, nx + 1):                                      # the far side, where the arch is
        rid = ARCH if k == gate_k else (BUTTRESS if k == butt_k else WALL)
        put(rid, xb - U * k, yb, WALL_DZ, 180.0, 'gate' if rid == ARCH else 'wall')
    put(CORNER, xb, yb, WALL_DZ, 180.0, 'corner')
    put(CORNER, xa, yb, WALL_DZ, 270.0, 'corner')
    if side > 0:
        put(CORNER, xb, ya, WALL_DZ, 90.0, 'corner')
        for k in range(1, ny + 1):
            put(WALL, xb, ya - U * k, WALL_DZ, 90.0)                 # the outer side
            put(WALL, xa, yb + U * k, WALL_DZ, 270.0)                # the side that ends in the front tower
        k = 1
        while True:                                                 # the near side, closing on the keep's flank
            cx_ = xb - U * k
            put(WALL, cx_, ya, WALL_DZ, 0.0)
            if cx_ - U / 2.0 <= 424.0 or k > 6:
                break
            k += 1
    else:
        put(CORNER, xa, ya, WALL_DZ, 0.0, 'corner')
        for k in range(1, ny + 1):
            put(WALL, xa, yb + U * k, WALL_DZ, 270.0)
            put(WALL, xb, yb + U * k, WALL_DZ, 90.0)
        k = 1
        while True:
            cx_ = xa + U * k
            put(WALL, cx_, ya, WALL_DZ, 0.0)
            if cx_ + U / 2.0 >= -424.0 or k > 6:
                break
            k += 1
    # the well, in the yard's half away from the door's way
    Y = A - YARD_DROP
    if db.resolve_id(WELL[0]) is not None:
        wx_ = (xa + xb) / 2.0 + side * rng.uniform(0.15, 0.3) * (xb - xa)
        wy_ = yb + rng.uniform(0.35, 0.6) * (ya - yb - 300.0)
        wxw, wyw = W(wx_, wy_)
        pieces.append({'id': WELL[0], 'p': [round(wxw, 2), round(wyw, 2), round(Y + WELL[1], 2), 0.0, 0.0, round(T(rng.choice((0.0, 90.0))), 5)], 's': 1.0, 'kind': 'well', 'l': (wx_, wy_)})
    # the ground: the keep's top at the door's level, the yard a terrace under it, the walls' feet in the ground
    levels = []
    for ly in (-480.0, -300.0, 0.0, 300.0, 520.0):
        levels.append((W(-560.0, ly), W(560.0, ly), A))
    # (the way down from the door to the yard: one even bank, a line every 90 at its own height. With only the two
    # levels given the ground between them fell as a 54 degree step, the first keep)
    y_ = RAMP[0]
    while y_ > RAMP[1]:
        t_ = (RAMP[0] - y_) / (RAMP[0] - RAMP[1])
        levels.append((W(xa + 150.0, y_), W(xb - 150.0, y_), A - (A - Y) * t_))
        y_ -= 90.0
    y_ = yb + 200.0
    while y_ <= RAMP[1]:
        levels.append((W(xa + 150.0, y_), W(xb - 150.0, y_), Y))
        y_ += 200.0
    for a_, b_ in (((xa, yb), (xb, yb)), ((xa, yb), (xa, -900.0)), ((xb, yb), (xb, -900.0))):
        levels.append((W(*a_), W(*b_), Y))
    outline = [W(min(xa, -560.0) - 200.0, 640.0), W(max(xb, 560.0) + 200.0, 640.0), W(max(xb, 560.0) + 200.0, yb - 250.0), W(min(xa, -560.0) - 200.0, yb - 250.0)]
    dx, dy = W(DOOR[1], DOOR[2])
    out_x, out_y = W(DOOR[1], DOOR[2] - 150.0)
    return {'pieces': pieces, 'levels': levels, 'outline': [list(p) for p in outline], 'k': K, 'top': A, 'yard': Y, 'face': face, 'rz': rz, 'side': side,
            'yard_box': [xa, yb, xb, ya], 'nx': nx, 'ny': ny,
            'door': {'p': [dx, dy, K + DOOR[3]], 'out': [round(out_x, 1), round(out_y, 1), round(A + 8.0, 1), 0.0, 0.0, round(math.atan2(face[0], face[1]) % (2 * math.pi), 5)]},
            'gate': next(p for p in pieces if p['kind'] == 'gate')['p'][:2]}


def _clear(db, P):
    """What grew or lay loose on the keep's ground taken off it, as a town's ground is cleared (gateway._clearable)."""
    import editing
    import gateway
    poly = P['outline']
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    mine = db.project.plugin.lower()

    def inside(x, y):
        c = False
        for i in range(4):
            a, b = poly[i], poly[(i + 1) % 4]
            if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                c = not c
        return c
    n = 0
    for gx in range(int(math.floor(min(xs) / 8192.0)), int(math.floor(max(xs) / 8192.0)) + 1):
        for gy in range(int(math.floor(min(ys) / 8192.0)), int(math.floor(max(ys) / 8192.0)) + 1):
            key = '#%d,%d' % (gx, gy)
            hits = [r for r in mapdata.cellmap(db, key).get('refs') or () if gateway._clearable(r) and inside(r['p'][0], r['p'][1])]
            if not hits:
                continue
            c, all_refs = editing._cell(db, key)
            for r in hits:
                ref = all_refs.get(r['k'])
                if not ref:
                    continue
                if ref['origin'] == mine:
                    c['refs'].pop(r['k'], None)
                else:
                    editing._store(c, r['k'], ref['origin'], ref['idx'], ref['subs'], deleted=True)
                n += 1
    if n:
        db.sync_project()
    return n


def _rocks(db, P, rng):
    """Boulders at the foot of the yard's walls on the falling side and under the keep's back, as Duskwatch stands among
    its own (49 within 2,200): where the made ground drops away outside a wall, a rock set deep against it."""
    ids = [i for i in ROCKS if db.resolve_id(i) is not None]
    if not ids:
        return []
    rz, W = _frame(*P['at'], P['face'])
    xa, yb, xb, ya = P['yard_box']
    spots = []
    for t in range(int(xa), int(xb) + 1, 420):
        spots.append((t, yb - 330.0))
    for t in range(int(yb), -500, 420):
        spots.append((xa - 330.0, t))
        spots.append((xb + 330.0, t))
    for t in (-420.0, 0.0, 420.0):
        spots.append((t, 760.0))
    out = []
    for lx, ly in spots:
        lx += rng.uniform(-120.0, 120.0)
        ly += rng.uniform(-90.0, 90.0)
        x, y = W(lx, ly)
        g = mapdata.terrain_z(db, x, y)
        g_in = mapdata.terrain_z(db, *W(max(xa + 100, min(xb - 100, lx)), max(yb + 100, min(500.0, ly))))
        if g is None or g_in is None or g < 16 or g_in - g < 40.0 or rng.random() < 0.2:
            continue                              # (only where the ground does fall away outside)
        rid = rng.choice(ids)
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) or [0, 0, -100, 0, 0, 100]
        s = rng.uniform(0.7, 1.25)
        # (set deep: a third of it in the ground, never a bottom edge showing)
        z = g - b[2] * s - 0.38 * (b[5] - b[2]) * s
        out.append({'id': rid, 'p': [round(x, 1), round(y, 1), round(z, 1), 0.0, 0.0, round(rng.uniform(0, 2 * math.pi), 4)], 's': round(s, 2), 'kind': 'rock'})
    return out


def make(db, x, y, face=None, seed=1, name='', people=False, rooms=True, top=None):
    """The keep made at (x, y): its ground shaped, its pieces stood, its rooms built and its door linked both ways; one
    Undo takes it back. {'name', 'pieces', 'rocks', 'cleared', 'interiors', 'links', 'cells', 'door'}."""
    import editing
    import ledger
    import townwalls
    from project import set_ref_pos, zs
    editing._require_project(db)
    P = plan(db, x, y, face, seed, top)
    P['at'] = (x, y)
    rng = random.Random('%s|tower keep made' % seed)
    if not name:
        import towninside
        try:
            name = '%s Keep' % towninside.town_name(db, 'Imperial', seed)
        except Exception:
            name = 'Hill Keep %d' % seed
    p = db.project
    stack = getattr(p, 'undo_stack', [])
    n0 = len(stack)
    mine = p.plugin.lower()
    out = {'name': name, 'pieces': 0, 'rocks': 0, 'cleared': 0, 'interiors': 0, 'links': 0, 'cells': [], 'faults': []}
    with ledger.open(db, 'castle', name, P['outline'], seed, {'style': 'Tower keep'}):
        out['cleared'] = _clear(db, P)
        # (cut first, then filled: the two tolerances apart, as the walls' own ground passes do)
        townwalls._KEEP_SEA[0] = False
        townwalls._shape_ground(db, P['levels'], set(), CUT, RAISE)
        cells = set()
        door_ref = None

        def put(t):
            ri = db.resolve_id(t['id'])
            if ri is None:
                return None
            key = '#%d,%d' % (math.floor(t['p'][0] / 8192.0), math.floor(t['p'][1] / 8192.0))
            cell, _refs = editing._cell(db, key)
            rk = p.new_ref_key()
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], tuple(t['p']), t.get('s') or 1.0))
            cells.add(key)
            return key, rk
        for t in P['pieces']:
            got = put(t)
            if got:
                out['pieces'] += 1
                if t['kind'] == 'door':
                    door_ref = got
        db.sync_project()
        for t in _rocks(db, P, rng):
            if put(t):
                out['rocks'] += 1
        db.sync_project()
        editing.commit(db, 'Stood %s' % name)
        out['cells'] = sorted(cells)
        out['door'] = P['door']
        if rooms and door_ref:
            try:
                import keepmaker
                R = keepmaker.make(db, name, 'small', seed=seed, outs=1, people=people, commit=False)
                if R.get('learning'):
                    out['faults'].append('The Workshop is still learning the game\'s forts: the keep has no rooms yet.')
                else:
                    out['interiors'] = len(R['interiors'])
                    outs = sorted([o for o in R['outs'] if o.get('kind') != 'trap'], key=lambda o: (o.get('role') != 'hall', o.get('kind') != 'front', o['z']))
                    if outs:
                        o = outs[0]
                        if keepmaker._link(db, door_ref[0], door_ref[1], o['name'], o['arrive']):
                            out['links'] += 1
                        if keepmaker._link(db, o['cell'], o['k'], '', P['door']['out']):
                            out['links'] += 1
                        # (a way in more than the keep has doors: out by the same door's spot, never a door to nowhere)
                        for o2 in R['outs']:
                            if o2 is not o and o2.get('kind') != 'trap':
                                if keepmaker._link(db, o2['cell'], o2['k'], '', P['door']['out']):
                                    out['links'] += 1
                    else:
                        out['faults'].append('The keep\'s rooms kept no door for the outside.')
                    db.sync_project()
                    editing.commit(db, 'Built the rooms of %s' % name)
            except Exception as e:
                out['faults'].append('rooms: %s' % e)
    steps = len(getattr(p, 'undo_stack', [])) - n0
    if steps > 1:
        try:
            editing.fold(db, steps, 'Made %s: a tower keep, %d pieces, %d rooms' % (name, out['pieces'], out['interiors']))
        except Exception as e:
            out['faults'].append('fold: %s' % e)
    LAST.clear()
    LAST.update(plan=P, out=out)
    return out
