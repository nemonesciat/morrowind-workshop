"""A keep on its own rock off the shore, joined to the land by a bridge: the great keep the Cyrodiil way.

The game's own is Goldstone, Anvil's castle (docs/cyrodiil-study-2026-11.md; the user, 2026-11-13: "a good example of
the 'great keep' style, especially for Imperial"): a rock island standing out of the sea, its sides clad in boulders
(70 within 1,500 of the fort's box), the fort's pieces on top, and a bridge of eight 512 lengths (t_imp_legioncyr_x_
bridge_01a, a bridge_02a at each end with its stepped end to the land), its deck 272 over the pieces' origin, standing
on piers (bridgebot_01, 896 under the bridge, at the joints over the water) and foundation blocks under those where the
sea is deep.

Built anew here: make() raises a rock where it is asked for (land raised only, steep sides with an uneven edge, never
a game rock copied), stands the tower keep on it (towerkeep.py) with its door and yard toward the shore, runs the
bridge level from the yard's arch to the land with a landing and an even way down at its far end, and sets boulders
into the rock's sides."""
import math
import random

import mapdata
from editing import EditError

BRIDGE = 't_imp_legioncyr_x_bridge_01a'
BRIDGE_END = 't_imp_legioncyr_x_bridge_02a'
PIER = ('t_imp_legioncyr_x_bridgebot_01', -896.0)
BLOCK = ('t_imp_legioncyr_x_foundation_01', -1589.0, 1.47)
DECK = 272.0                   # the deck over the bridge pieces' origin
END_STEP = 216.0               # the ground at a bridge's end: this far over its origin (the end piece's own step)
END_OUT = 336.0                # an end piece reaches this far past its middle toward the land
U = 512.0
DECK_MIN = 440.0               # the deck over the water at least (Goldstone's stands 550 over it)
DECK_OVER_SHORE = 200.0        # and about this far over the shore it lands on, the land raised to meet it
DECK_MOST = 820.0
LANDING = 300.0                # level ground between the yard's arch and the bridge
SLOPE = math.tan(math.radians(60.0))     # the rock's sides
EDGE = 260.0                   # the rock's top reaches this far past the keep's ground all round
WAY_DOWN = math.tan(math.radians(13.0))  # the way down from the bridge's far end to the land as it lies
MOST = 18                      # bridge lengths at most
BIG_ROCKS = ('t_cyr_terrrockgc_rock_15', 't_cyr_terrrockgc_rock_19', 't_cyr_terrrockgc_rock_21', 't_cyr_terrrockgc_rock_24', 't_cyr_terrrockgc_rock_25',
             't_cyr_terrrockgc_rock_29', 't_cyr_terrrockgc_rock_23', 't_cyr_terrrockgc_rock_31', 't_cyr_terrrockgc_rock_32', 't_cyr_terrrockgc_rock_18')
MID_ROCKS = ('t_cyr_terrrockgc_rock_08', 't_cyr_terrrockgc_rock_10', 't_cyr_terrrockgc_rock_12', 't_cyr_terrrockgc_rock_13', 't_cyr_terrrockgc_rock_14',
             't_cyr_terrrockgc_rock_17', 't_cyr_terrrockgc_rock_22', 't_cyr_terrrockgc_rock_27', 't_cyr_terrrockgc_rock_28')
LAST = {}


def _unit(x, y):
    h = math.hypot(x, y) or 1.0
    return x / h, y / h


def _raise(db, box_of, A, seed, skip=()):
    """The rock: every land point brought up to the height the rock has there (never down). box_of(x, y): how far a
    point lies outside the rock's top (0 on it). Its edge runs in and out by the bearing, so no two rocks are one
    shape. The cells changed."""
    import landscape
    rng = random.Random('%s|rock' % seed)
    ph = [rng.uniform(0, 2 * math.pi) for _ in range(4)]
    cx, cy, reach = box_of(None, None)
    G = landscape.CELL
    step = G / (landscape.N - 1.0)
    new_h, before = {}, {}
    far = reach + A / SLOPE + 900.0 + 2500.0 / SLOPE
    for gx in range(int(math.floor((cx - far) / G)), int(math.floor((cx + far) / G)) + 1):
        for gy in range(int(math.floor((cy - far) / G)), int(math.floor((cy + far) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(landscape.N):
                for i in range(landscape.N):
                    x, y = gx * G + i * step, gy * G + j * step
                    if abs(x - cx) > far or abs(y - cy) > far:
                        continue
                    d = box_of(x, y)
                    th = math.atan2(y - cy, x - cx)
                    d_eff = d - (150.0 * math.sin(3 * th + ph[0]) + 110.0 * math.sin(5 * th + ph[1]) + 70.0 * math.sin(9 * th + ph[2]))
                    if d <= 0.0:
                        t = A
                    else:
                        # (a shoulder, then the fall: steeper low down, as a sea rock's foot is)
                        t = A - max(0.0, d_eff) * SLOPE * (1.0 + 0.25 * math.sin(7 * th + ph[3]))
                    n = j * landscape.N + i
                    if t > h[n] + 1:
                        h[n] = t
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return len(new_h)


def _mound(db, height, cx, cy, reach, skip=()):
    """Land raised to height(x, y) wherever it lies under it, within reach of (cx, cy); never lowered. The cells changed."""
    import landscape
    G = landscape.CELL
    step = G / (landscape.N - 1.0)
    new_h, before = {}, {}
    for gx in range(int(math.floor((cx - reach) / G)), int(math.floor((cx + reach) / G)) + 1):
        for gy in range(int(math.floor((cy - reach) / G)), int(math.floor((cy + reach) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(landscape.N):
                for i in range(landscape.N):
                    x, y = gx * G + i * step, gy * G + j * step
                    if abs(x - cx) > reach or abs(y - cy) > reach:
                        continue
                    t = height(x, y)
                    n = j * landscape.N + i
                    if t is not None and t > h[n] + 1:
                        h[n] = t
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return len(new_h)


def make(db, x, y, toward, seed=1, name='', people=False, rooms=True):
    """The keep on its rock at (x, y), its bridge running toward the shore point `toward` (x, y). One Undo takes it all
    back. {'name', 'top', 'deck', 'bridge': lengths, 'piers', 'rocks', 'keep': towerkeep's own result, 'faults'}."""
    import editing
    import ledger
    import towerkeep
    import townwalls
    from project import set_ref_pos, zs
    editing._require_project(db)
    if any(db.resolve_id(i) is None for i in (BRIDGE, BRIDGE_END)) or not towerkeep.ready(db):
        raise EditError('This load order has no Cyrodiil fort pieces (Tamriel Data) to build the keep and its bridge of.')
    u = _unit(toward[0] - x, toward[1] - y)
    rng = random.Random('%s|rock keep' % seed)
    # the keep as it will stand, to know its ground and where its arch is (the same seed gives the same keep after)
    P0 = towerkeep.plan(db, x, y, u, seed, top=1000.0)
    rz, W = towerkeep._frame(x, y, u)
    xa, yb, xb, ya = P0['yard_box']
    lo_x, hi_x = min(xa, -560.0) - EDGE, max(xb, 560.0) + EDGE
    lo_y, hi_y = yb - 250.0 - LANDING - 120.0, 640.0 + EDGE
    c, s = math.cos(rz), math.sin(rz)

    def to_local(wx, wy):
        dx, dy = wx - x, wy - y
        return dx * c - dy * s, dx * s + dy * c

    def box_of(wx, wy):
        if wx is None:
            mx, my = W((lo_x + hi_x) / 2.0, (lo_y + hi_y) / 2.0)
            return mx, my, 0.5 * math.hypot(hi_x - lo_x, hi_y - lo_y)
        lx, ly = to_local(wx, wy)
        ox = max(lo_x - lx, 0.0, lx - hi_x)
        oy = max(lo_y - ly, 0.0, ly - hi_y)
        return math.hypot(ox, oy)
    # the arch and the bridge's line out of it
    gx_, gy_ = P0['gate']
    start = (gx_ + u[0] * (168.0 + LANDING + END_OUT), gy_ + u[1] * (168.0 + LANDING + END_OUT))
    n = None
    for k in range(2, MOST + 1):
        ex, ey = start[0] + u[0] * (U * k + END_OUT + 150.0), start[1] + u[1] * (U * k + END_OUT + 150.0)
        g = mapdata.terrain_z(db, ex, ey)
        # (past the rock's own foot, and on land that stays land a little further on)
        g2 = mapdata.terrain_z(db, ex + u[0] * 400.0, ey + u[1] * 400.0)
        if g is not None and g2 is not None and g >= 40.0 and g2 >= 40.0 and U * k > 1000.0 / SLOPE + 900.0:
            n = k
            shore = g
            break
    if n is None:
        raise EditError('No shore within %d bridge lengths that way: set the rock nearer the land.' % MOST)
    D = max(DECK_MIN, min(DECK_MOST, shore + DECK_OVER_SHORE))
    origin = D - DECK
    Y = origin + END_STEP                    # the yard and the landing: the bridge's end at grade
    A = Y + towerkeep.YARD_DROP
    name = (name or '').strip()
    if not name:
        import towninside
        try:
            name = '%s Rock' % towninside.town_name(db, 'Imperial', seed)
        except Exception:
            name = 'Keep Rock %d' % seed
    p = db.project
    stack = getattr(p, 'undo_stack', [])
    n0 = len(stack)
    mine = p.plugin.lower()
    out = {'name': name, 'top': round(A), 'deck': round(D), 'bridge': n + 1, 'piers': 0, 'blocks': 0, 'rocks': 0, 'faults': []}
    outline = [W(lo_x, hi_y), W(hi_x, hi_y), W(hi_x, lo_y), W(lo_x, lo_y)]
    with ledger.open(db, 'castle', name, outline, seed, {'style': 'Keep on a rock'}):
        out['cells_raised'] = _raise(db, box_of, A, seed)
        editing.commit(db, 'Raised the rock of %s' % name)
        K = towerkeep.make(db, x, y, u, seed, name=name, people=people, rooms=rooms, top=A)
        out['keep'] = {k_: v for k_, v in K.items() if k_ != 'door'}
        out['faults'] += K.get('faults') or []
        # the landing before the arch, and the far end's landing and way down
        segs = []
        for d_ in range(0, int(LANDING + END_OUT) + 1, 110):
            mx, my = gx_ + u[0] * (168.0 + d_), gy_ + u[1] * (168.0 + d_)
            segs.append(((mx + u[1] * 330.0, my - u[0] * 330.0), (mx - u[1] * 330.0, my + u[0] * 330.0), Y))
        far = (start[0] + u[0] * (U * n + END_OUT), start[1] + u[1] * (U * n + END_OUT))
        townwalls._KEEP_SEA[0] = False
        townwalls._shape_ground(db, segs, set(), 400.0, 900.0)
        # (the far end: an abutment no wider than the bridge needs, level for a landing and then an even way down to
        # the land as it lies; its sides and its face to the water fall steeply. Shaped as the walls' ground is, with
        # their wide fade, the first one raised the whole shore and left no water under the bridge)

        def abutment(wx, wy):
            al = (wx - far[0]) * u[0] + (wy - far[1]) * u[1]
            ac = abs(-(wx - far[0]) * u[1] + (wy - far[1]) * u[0])
            top = Y if al <= 300.0 else Y - (al - 300.0) * WAY_DOWN
            if al < -40.0:
                top = Y - (-40.0 - al) * SLOPE          # (its face under the bridge's end)
            return top - max(0.0, ac - 300.0) * 1.2
        out['cells_raised'] += _mound(db, abutment, far[0], far[1], 3200.0)
        cells = set()

        def put(rid, px, py, pz, prz, sc=1.0):
            ri = db.resolve_id(rid)
            if ri is None:
                return False
            key = '#%d,%d' % (math.floor(px / 8192.0), math.floor(py / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                return False
            rk = p.new_ref_key()
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], (px, py, pz, 0.0, 0.0, prz % (2 * math.pi)), sc))
            cells.add(key)
            return True
        rzb = math.atan2(-u[1], u[0])            # (a bridge piece's x along the way to the shore)
        for k in range(n + 1):
            bx, by = start[0] + u[0] * U * k, start[1] + u[1] * U * k
            if k == 0:
                put(BRIDGE_END, bx, by, origin, rzb)
            elif k == n:
                put(BRIDGE_END, bx, by, origin, rzb + math.pi)
            else:
                put(BRIDGE, bx, by, origin, rzb)
        for k in range(n):
            jx, jy = start[0] + u[0] * (U * k + U / 2.0), start[1] + u[1] * (U * k + U / 2.0)
            g = mapdata.terrain_z(db, jx, jy)
            if g is None or g > origin - 420.0:
                continue                         # (the joint stands over the rock or the shore: no pier)
            if db.resolve_id(PIER[0]) is not None and put(PIER[0], jx, jy, origin + PIER[1], rzb):
                out['piers'] += 1
                if g < origin + PIER[1] - 384.0 and db.resolve_id(BLOCK[0]) is not None and put(BLOCK[0], jx, jy, origin + BLOCK[1], rzb, BLOCK[2]):
                    out['blocks'] += 1
        db.sync_project()
        # boulders set into the rock's sides, in three bands down the fall, none on the bridge's line
        big = [i for i in BIG_ROCKS if db.resolve_id(i) is not None]
        mid = [i for i in MID_ROCKS if db.resolve_id(i) is not None]
        per = 2.0 * ((hi_x - lo_x) + (hi_y - lo_y))
        for band, (off, pool, gap, sc_) in enumerate(((90.0, mid or big, 420.0, (0.9, 1.5)), (330.0, big or mid, 620.0, (0.9, 1.5)), (640.0, big or mid, 760.0, (1.0, 1.7)))):
            if not pool:
                continue
            t = rng.uniform(0, gap)
            while t < per:
                # (a point on the top's edge by the distance round it, then `off` outward)
                w_, h_ = hi_x - lo_x, hi_y - lo_y
                q = t
                if q < w_:
                    lx, ly, ox, oy = lo_x + q, hi_y, 0.0, 1.0
                elif q < w_ + h_:
                    lx, ly, ox, oy = hi_x, hi_y - (q - w_), 1.0, 0.0
                elif q < 2 * w_ + h_:
                    lx, ly, ox, oy = hi_x - (q - w_ - h_), lo_y, 0.0, -1.0
                else:
                    lx, ly, ox, oy = lo_x, lo_y + (q - 2 * w_ - h_), -1.0, 0.0
                t += gap * rng.uniform(0.7, 1.3)
                lx, ly = lx + ox * off + rng.uniform(-90, 90), ly + oy * off + rng.uniform(-90, 90)
                wx, wy = W(lx, ly)
                # (off the bridge's line and the landing)
                along = (wx - gx_) * u[0] + (wy - gy_) * u[1]
                across = abs(-(wx - gx_) * u[1] + (wy - gy_) * u[0])
                if along > -100.0 and across < 520.0:
                    continue
                g = mapdata.terrain_z(db, wx, wy)
                if g is None:
                    continue
                rid = rng.choice(pool)
                b = mapdata.object_bounds(db, db.resolve_id(rid))
                if not b:
                    continue
                sc = rng.uniform(*sc_)
                # (set deep into the slope: its middle about at the ground, no bottom edge to see)
                z = g - (b[2] + b[5]) / 2.0 * sc - 0.12 * (b[5] - b[2]) * sc
                if put(rid, wx, wy, z, rng.uniform(0, 2 * math.pi), round(sc, 2)):
                    out['rocks'] += 1
        db.sync_project()
        editing.commit(db, 'Built the bridge of %s' % name)
        out['cells'] = sorted(set(cells) | set(K.get('cells') or ()))
    steps = len(getattr(p, 'undo_stack', [])) - n0
    if steps > 1:
        try:
            editing.fold(db, steps, 'Made %s: a keep on a rock, a bridge of %d lengths' % (name, n + 1))
        except Exception as e:
            out['faults'].append('fold: %s' % e)
    LAST.clear()
    LAST.update(out=out, start=start, u=u, n=n, origin=origin, yard=Y, top=A, gate=(gx_, gy_), far=far)
    return out
