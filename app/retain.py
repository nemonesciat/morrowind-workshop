"""Revetments for a made town: the sheer sides of its streets regraded into a clean step and held by thick rock.

A hill town's streets and house terraces leave sheer strips of ground beside the streets. The bank pass could not dress
them (rockblend._banks: on the street a rock may not stand, and sunk into a bank that steep its bottom rim shows, so it
is dropped; 32 rocks a town, 137 steep spots left bare, lab 2026-11-11). The user, of their Senchal: "we spent hours on
decorating sheer cliffs and steep ground with rocks. So why did this get two rocks?"

The user's rules for what holds such a side, from their own hand-set example (a slab of rock, a dry-stone wall, a
boulder, side by side in a sheer notch by a street): it must HIDE the sheared ground, all of it ("anything less and it
looks like a failed wall whose retained soil has started to erode"); it must stand as tall as the soil it holds ("so
they don't merely look like slap-on decorations"); and no piece may show a naked end.

The land's points are 128 apart, so sheer ground is a slope 128 deep at the least. A wall 50 thick cannot hide that:
part of the slope shows before it or the soil falls away behind it (the first lab try, 2026-11-11: single lengths of
dry-stone wall, stubs with naked ends). Thick rock can: its body swallows the slope. So, for each sheer side:

  1. the ground is regraded into a clean step: the street's own level out to STEP_AT beyond its width, the level behind
     from there on, so the whole slope lies in one strip just outside the street;
  2. the land's own rocks (the culture's palette, rockblend._Picker) stand along that strip, each turned along the
     street, deep enough to cover the slope where it stands and tall enough to top the soil by OVER_MIN, lapping the
     next, its foot on the level ground before it and its bottom rim buried there (rockblend's rim rule, on flat ground
     an easy one);
  3. before the bank pass, whose rocks keep off them (plan['_retain']).

A side whose drop no rock of the palette can top, or where a house, a door, a way or another street leaves no room, is
left as it is. Dry-stone walls between two rocks, their ends buried in them, are not built yet.
"""
import math
import random
from collections import Counter

import mapdata

RISE_MIN = 80.0                # a drop under this is no revetment's business
RISE_TAIL = 48.0               # ... but a run that has one goes on while the drop is this much: a bank's shoulders are held with it
RISE_MAX = 380.0               # ... and over this no rock of a town's palette tops it
SHEER = 0.8                    # this share of the drop stands within SHEER_IN of the street's level edge: a sheer side, not a slope
SHEER_IN = 150.0
EDGE = 64.0                    # (the street's level margin beyond its width: townbuild.STREET_EDGE)
STEP_AT = 128.0                # the regraded step stands this far beyond the street's width
BACK = 230.0                   # the ground behind the step is brought level this far back
READ = 128.0                   # the street's side is read this often along it
MIN_RUN = 2                    # a sheer side shorter than this many readings is left
OVER_MIN = 48.0                # a rock's top at least this far over the upper ground
OVER_AIM = (60.0, 115.0)       # ... and set about this far over it: sunk until it is. A hold, not a standing stone (the
                               # first try stood them on their feet, 203 over the soil)
OVER_MAX = 230.0               # (a rock that would stand taller than this even so is not used)
FOOT_IN = 28.0                 # its foot starts this far in the lower ground (the rim rule sinks it further if it must)
COVER_PAD = 14.0               # it covers the slope and this much either side of it
SHOULDER = 200.0               # the rocks run on this far past a sheer side's ends, while the ground still drops SHOULDER_MIN:
SHOULDER_MIN = 30.0            # the bank's shoulders held with it (the second try stopped dead, the bank bare beside the last rock)
LAP = 0.22                     # each laps the next by this share of its length
LONG_MAX = 760.0               # no rock longer than this along the street
DOOR_CLEAR = 256.0


def _segments(plan):
    """Every street segment: (street index, segment index, ax, ay, ux, uy, length, half width)."""
    out = []
    for si, st in enumerate(plan.get('streets') or ()):
        hw = (st.get('w') or 512) / 2.0
        pts = st.get('pts') or []
        for gi, ((ax, ay), (bx, by)) in enumerate(zip(pts, pts[1:])):
            L = math.hypot(bx - ax, by - ay)
            if L >= 1:
                out.append((si, gi, ax, ay, (bx - ax) / L, (by - ay) / L, L, hw))
    return out


def _on_segment(seg, x, y):
    """(along, across, side) of a point in a segment's frame: across from its middle line, side +1 to its left."""
    _si, _gi, ax, ay, ux, uy, _L, _hw = seg
    dx, dy = x - ax, y - ay
    cr = ux * dy - uy * dx
    return dx * ux + dy * uy, abs(cr), (1 if cr >= 0 else -1)


def _at(seg, along, across, side):
    _si, _gi, ax, ay, ux, uy, _L, _hw = seg
    return ax + ux * along - uy * across * side, ay + uy * along + ux * across * side


def _other_street(plan, own, px, py, pad):
    """Does the point lie within another street's width (and pad)?"""
    for si, st in enumerate(plan.get('streets') or ()):
        if si == own:
            continue
        hw = (st.get('w') or 512) / 2.0
        ps = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(ps, ps[1:]):
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            if math.hypot(px - ax - dx * t, py - ay - dy * t) < hw + pad:
                return True
    return False


def _blocked(S, plan, rockblend, pts, own_street, pad=24.0, plot_pts=None):
    """Why nothing may stand over these points ('' when it may). plot_pts: how many of the first points are kept out
    of the buildings' boxes (all of them when None): a rock's middle stays out of a house's box, its back may lean in."""
    for n_, (px, py) in enumerate(pts):
        if (plot_pts is None or n_ < plot_pts) and any(S._in_rect(q, px, py) or rockblend._rect_dist(q, px, py) < pad for q in S.rects):
            return 'plot'
        if any(S._in_rect(q, px, py) for qs in (S.ways, S.treads, S.wall) for q in qs):
            return 'way'
        if any(math.hypot(px - dx, py - dy) < DOOR_CLEAR for dx, dy in S.doors):
            return 'door'
        if S.square and math.hypot(px - S.square[0], py - S.square[1]) < S.square[2] + 32.0:
            return 'square'
        if _other_street(plan, own_street, px, py, EDGE * 0.6):
            return 'street'
    return ''


def sheer_runs(db, plan, S):
    """The sheer sides of the streets: ([(segment, side, [(along, street level, the level behind)], down)], why not)
    for every stretch where the ground behind the street's level edge stands RISE_MIN to RISE_MAX over or under the
    street, most of it within SHEER_IN of the edge, and something may stand there."""
    import rockblend
    tz = lambda x, y: mapdata.terrain_z(db, x, y)
    why = Counter()
    out = []
    for seg in _segments(plan):
        si, _gi, _ax, _ay, ux, uy, L, hw = seg
        for side in (1, -1):
            run = []

            def close():
                if len(run) >= MIN_RUN and max(abs(r_[2] - r_[1]) for r_ in run) >= RISE_MIN:
                    out.append((seg, side, list(run), run[0][3]))
                elif run:
                    why['short' if len(run) < MIN_RUN else 'low'] += 1
                del run[:]
            a = READ / 2.0
            while a <= L - READ / 2.0 + 1:
                zs = tz(*_at(seg, a, hw + EDGE * 0.5, side))
                near = tz(*_at(seg, a, hw + EDGE + SHEER_IN, side))
                far = [tz(*_at(seg, a, hw + EDGE + d_, side)) for d_ in (SHEER_IN, SHEER_IN + 60.0, SHEER_IN + 120.0)]
                ok = zs is not None and near is not None and None not in far and zs >= 8 and min(far) >= 8
                zb = drop = 0.0
                if ok:
                    zb = sorted(far)[1]
                    drop = zb - zs
                    if abs(drop) < RISE_TAIL or abs(near - zs) < SHEER * abs(drop) or (near - zs) * drop <= 0:
                        why['no sheer side'] += 1
                        ok = False
                    elif abs(drop) > RISE_MAX:
                        why['too tall'] += 1
                        ok = False
                if ok and len(S.outline) >= 3:
                    x, y = _at(seg, a, hw + STEP_AT, side)
                    if not rockblend._inside_poly(S.outline, x, y) and rockblend._edge_dist(S.outline, x, y) > S.pad:
                        why['far'] += 1
                        ok = False
                if ok:
                    # (the step's own line clear: a house's box may begin just behind it, the rock leans on its foot)
                    x, y = _at(seg, a, hw + STEP_AT + 30.0, side)
                    w_ = _blocked(S, plan, rockblend, [(x, y), (x + ux * READ * 0.45, y + uy * READ * 0.45), (x - ux * READ * 0.45, y - uy * READ * 0.45)], si, pad=0.0)
                    if w_:
                        why[w_] += 1
                        ok = False
                if ok and run and (run[-1][3] != (drop < 0) or abs(run[-1][2] - zb) > 120):
                    close()                      # (the other way, or another terrace behind: another run)
                if ok:
                    run.append((a, zs, zb, drop < 0))
                else:
                    close()
                a += READ
            close()
    return out, why


def _regrade(db, plan, S, runs, new_refs):
    """The runs' ground as a clean step: the street's level out to STEP_AT beyond its width, the level behind from
    there to BACK (never inside a plot's box, a door's way, a tread or under the town's wall). The points moved."""
    import landscape
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    new_h, before, moved = {}, {}, 0
    for seg, side, run, down in runs:
        hw = seg[7]
        a0, a1 = run[0][0] - READ / 2.0, run[-1][0] + READ / 2.0
        xs, ys = [], []
        for a_ in (a0, a1):
            for c_ in (hw, hw + STEP_AT + BACK):
                px, py = _at(seg, a_, c_, side)
                xs.append(px); ys.append(py)
        for gx in range(int(math.floor((min(xs) - step) / G)), int(math.floor((max(xs) + step) / G)) + 1):
            for gy in range(int(math.floor((min(ys) - step) / G)), int(math.floor((max(ys) + step) / G)) + 1):
                h = new_h.get((gx, gy))
                if h is None:
                    Ld = mapdata.land(db, gx, gy)
                    if not Ld or not Ld.get('h'):
                        continue
                    h = list(Ld['h'])
                    before[(gx, gy)] = list(Ld['h'])
                    new_h[(gx, gy)] = h
                for j in range(N):
                    y = gy * G + j * step
                    if y < min(ys) - step or y > max(ys) + step:
                        continue
                    for i in range(N):
                        x = gx * G + i * step
                        if x < min(xs) - step or x > max(xs) + step:
                            continue
                        along, across, sd_ = _on_segment(seg, x, y)
                        if sd_ != side or along < a0 - 1 or along > a1 + 1 or across <= hw + EDGE or across > hw + STEP_AT + BACK:
                            continue
                        _a, street_z, back_z, _d = min(run, key=lambda r_: abs(r_[0] - along))
                        want = street_z if across < hw + STEP_AT else back_z
                        nidx = j * N + i
                        if abs(h[nidx] - want) <= 2:
                            continue
                        if any(S._in_rect(r_, x, y) for qs in (S.rects, S.ways, S.treads, S.wall) for r_ in qs):
                            continue
                        if _other_street(plan, seg[0], x, y, EDGE):
                            continue                 # (another street's own level stays)
                        h[nidx] = want
                        moved += 1
    changed = {k: h for k, h in new_h.items() if h != before[k]}
    for (gx, gy), h in changed.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, changed))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, new_refs)
    if changed:
        db.sync_project()
    return moved


def _slope_span(db, seg, side, along, street_z, back_z):
    """Where the step's slope lies across the street's side at this spot: (from, to) from the street's middle line,
    read every 16 between the street's width and STEP_AT + 160; None when there is no step there."""
    hw = seg[7]
    lo = hi = None
    tol = max(10.0, abs(back_z - street_z) * 0.08)
    c = hw
    while c <= hw + STEP_AT + 160.0:
        z = mapdata.terrain_z(db, *_at(seg, along, c, side))
        if z is None:
            return None
        if lo is None and abs(z - street_z) > tol:
            lo = c - 16.0
        if lo is not None and abs(z - back_z) <= tol:
            hi = c
            break
        c += 16.0
    return None if lo is None or hi is None else (max(hw, lo), hi)


def _fam(rid):
    """A rock's make: its id without its number (terrain_rock_ac_07 -> terrain_rock_ac)."""
    import re
    return re.sub(r'_?\d+[a-z]?$', '', rid.lower())


def _fit_rock(K, rng, depth, top, drop, fam=None):
    """A rock of the palette that is `depth` through and tops the soil when turned along the street: (id, box, scale),
    drawn by the towns' use among those that fit within the scales a rock may take, the lower ones first (those that
    need not be sunk past their middle to come down to OVER_AIM); None when none does."""
    import rockblend
    pool = []
    low_pool = []
    for rid, n in K.ids:
        b = K.box(rid)
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        thin, long_ = min(w, d), max(w, d)
        if thin <= 0 or h <= 0:
            continue
        s = max(depth / thin, top / h)
        if s < rockblend.SCALE[0]:
            s = rockblend.SCALE[0]
        if s > rockblend.SCALE[1] or long_ * s > LONG_MAX or h * s > drop + FOOT_IN + OVER_MAX + 60.0:
            continue
        pool.append((rid, n, round(s, 2)))
        if h * s <= 2.0 * (drop + FOOT_IN + OVER_AIM[1]):
            low_pool.append(pool[-1])
    # (one make of rock a side: a brown rock and a grey one side by side read as two piles, the second try)
    if fam:
        low_pool = [p_ for p_ in low_pool if _fam(p_[0]) == fam] or low_pool
        pool = [p_ for p_ in pool if _fam(p_[0]) == fam] or pool
        if any(_fam(p_[0]) == fam for p_ in pool) and not any(_fam(p_[0]) == fam for p_ in low_pool):
            low_pool = []
    pool = low_pool or pool
    if not pool:
        return None
    rid = K._one(rng, [(i, n) for i, n, _s in pool])
    K.shun = None
    s = next(s_ for i, _n, s_ in pool if i == rid)
    return rid, K.box(rid), s


def revet(db, plan, W, new_refs, cells, culture, seed=1, outline=None):
    """The sheer sides of the town's streets regraded and held by rock (see the module's head). The rocks join the
    town's own (new_refs, cells); their boxes are kept in plan['_retain'] for the bank pass. {'runs', 'rocks',
    'ground': points moved, 'refused': {why: n}, 'bare': runs left with a gap, 'placed': [...]}."""
    import rockblend
    P = rockblend.ready(db)
    if P is None:
        return {'runs': 0, 'rocks': 0, 'ground': 0, 'refused': {'learning': 1}, 'bare': 0, 'placed': []}
    region = ''
    try:
        import landrange
        c0 = sorted(cells)[0] if cells else None
        if c0 is not None:
            gx, gy = (c0 if isinstance(c0, tuple) else tuple(int(v) for v in str(c0).strip('#').split(',')))
            region = landrange._region_of(db, gx, gy) or ''
    except Exception:
        region = ''
    F = rockblend.figures(db, P, culture, region)
    if not F['ids']:
        return {'runs': 0, 'rocks': 0, 'ground': 0, 'refused': {'no rocks of the culture': 1}, 'bare': 0, 'placed': []}
    K = rockblend._Picker(db, F, P)
    rng = random.Random(seed * 7919 + 31)
    S = rockblend._Space(db, plan, W, set(new_refs), cells, outline or plan.get('outline'))
    runs, refused = sheer_runs(db, plan, S)
    if not runs:
        return {'runs': 0, 'rocks': 0, 'ground': 0, 'refused': dict(refused), 'bare': 0, 'placed': []}
    moved = _regrade(db, plan, S, runs, new_refs)
    memo, out, drops, boxes = {}, [], Counter(), []
    bare = 0
    for seg, side, run, down in runs:
        si, _gi, _ax, _ay, ux, uy, _L, hw = seg
        a0, a1 = run[0][0] - READ / 2.0, run[-1][0] + READ / 2.0
        b0, b1 = max(0.0, a0 - SHOULDER), min(_L, a1 + SHOULDER)       # (with the bank's shoulders)
        theta = math.atan2(uy, ux)
        along = b0
        gap = False
        fam = None
        while along < b1 - 24.0:
            # (the rock that starts here: read where the slope lies over the stretch a rock of middling length covers)
            placed = False
            for _try in range(5):
                guess = 300.0 * (1.0 - 0.12 * _try)
                mid = min(b1 - 20.0, along + guess / 2.0)
                if a0 <= mid <= a1:
                    _a, street_z, back_z, _d = min(run, key=lambda r_: abs(r_[0] - mid))
                else:
                    # (a shoulder: the ground as it lies there, the same way as the run's)
                    street_z = mapdata.terrain_z(db, *_at(seg, mid, hw + EDGE * 0.5, side))
                    back_z = mapdata.terrain_z(db, *_at(seg, mid, hw + STEP_AT + 100.0, side))
                    if street_z is None or back_z is None or abs(back_z - street_z) < SHOULDER_MIN or (back_z < street_z) != down:
                        break
                spans = [_slope_span(db, seg, side, max(b0, min(b1, mid + f_ * guess / 2.0)), street_z, back_z) for f_ in (-0.8, 0.0, 0.8)]
                spans = [sp for sp in spans if sp]
                if not spans:
                    drops['no step'] += 1
                    break
                c0_, c1_ = max(hw + 8.0, min(sp[0] for sp in spans) - COVER_PAD), max(sp[1] for sp in spans) + COVER_PAD
                low, high = min(street_z, back_z), max(street_z, back_z)
                pk = _fit_rock(K, rng, c1_ - c0_, (high - low) + FOOT_IN + OVER_MIN, high - low, fam)
                if not pk:
                    drops['no rock fits'] += 1
                    break
                rid, b, s = pk
                long_x = (b[3] - b[0]) >= (b[4] - b[1])
                length = max(b[3] - b[0], b[4] - b[1]) * s
                thick = min(b[3] - b[0], b[4] - b[1]) * s
                mid = min(b1 + length * 0.15, along + length / 2.0)
                # (its middle over the slope's middle; its front never on the street's width)
                across0 = max((c0_ + c1_) / 2.0, hw + 8.0 + thick / 2.0)
                # (its box's middle is not its origin: set by the box's middle)
                bx, by = (b[0] + b[3]) / 2.0 * s, (b[1] + b[4]) / 2.0 * s
                rz = (-(theta - (0.0 if long_x else math.pi / 2.0)) + (math.pi if rng.random() < 0.5 else 0.0)) % (2 * math.pi)
                c_, sn_ = math.cos(rz), math.sin(rz)
                import townbuild
                w_ = ''
                # (stood a little back, or a little forward, before it is given up: a gap in the middle of a held side
                # is the bank showing through it)
                for shift in (0.0, 28.0, 56.0, -24.0):
                    across = max(across0 + shift, hw + 8.0 + thick / 2.0)
                    mx, my = _at(seg, mid, across, side)
                    x, y = mx - (bx * c_ + by * sn_), my - (-bx * sn_ + by * c_)
                    corners = [(mx + (lx_ * c_ + ly_ * sn_) * 0.5, my + (-lx_ * sn_ + ly_ * c_) * 0.5)
                               for lx_ in (-(b[3] - b[0]) * s, (b[3] - b[0]) * s) for ly_ in (-(b[4] - b[1]) * s, (b[4] - b[1]) * s)]
                    w_ = _blocked(S, plan, rockblend, [(mx, my)] + [((cx_ + mx) / 2.0, (cy_ + my) / 2.0) for cx_, cy_ in corners], si, pad=8.0, plot_pts=1)
                    # (and no corner of its body on any street's width, its own least of all: 5 of 21 touched one)
                    if not w_ and any(townbuild._street_dist(plan, mx + (cx_ - mx) * 0.9, my + (cy_ - my) * 0.9) == 0 for cx_, cy_ in corners):
                        w_ = 'street corner'
                    if not w_:
                        break
                if w_:
                    drops[w_] += 1
                    continue
                # (set by its top: OVER_AIM over the soil it holds, its foot FOOT_IN in the lower ground at the least;
                # then sunk on while its rim shows, and no lower than OVER_MIN over the soil)
                aim = max(OVER_AIM[0], min(OVER_AIM[1], (high - low) * 0.6))
                z = min(high + aim - b[5] * s, low - FOOT_IN - b[2] * s)
                pos = [x, y, z, 0.0, 0.0, rz]
                okr = False
                for _sink in range(6):
                    res = rockblend.check_burial(db, rid, pos, s, memo=memo, others=boxes)
                    if res is None:
                        break
                    if res[0] <= -rockblend.MARGIN * 0.5:
                        okr = True
                        break
                    pos[2] -= res[0] + rockblend.MARGIN
                top_over = pos[2] + b[5] * s - high
                if not okr or top_over < OVER_MIN - 4.0:
                    drops['rim shows' if not okr else 'too low'] += 1
                    continue
                if True:
                    out.append({'id': rid, 'x': round(pos[0], 1), 'y': round(pos[1], 1), 'z': round(pos[2], 1), 'rx': 0.0, 'ry': 0.0, 'rz': round(rz, 4),
                                's': s, 'kind': 'revet', 'sunk': round(low - (pos[2] + b[2] * s)), 'top': round(pos[2] + b[5] * s - low),
                                'size': round(max(b[3] - b[0], b[4] - b[1]) * s)})
                    r_ = out[-1]
                    r_.update(length=round(length), thick=round(thick), drop=round(high - low), over=round(top_over), down=down,
                              quad=[(cx_, cy_) for cx_, cy_ in (corners[0], corners[1], corners[3], corners[2])])
                    boxes.append((r_['x'], r_['y'], r_['z'], r_['rz'], s, b))
                    K.used[rid.lower()] += 1
                    fam = fam or _fam(rid)
                    along = mid + length / 2.0 - length * LAP
                    placed = True
                    break
            if not placed:
                gap = gap or (a0 <= along <= a1)
                along += 128.0
        if gap:
            bare += 1
    made = rockblend.place(db, out, new_refs, cells) if out else 0
    plan['_retain'] = [[tuple(c_) for c_ in r_['quad']] for r_ in out]
    if made:
        db.sync_project()
    return {'runs': len(runs), 'rocks': made, 'ground': moved, 'refused': dict(refused), 'drops': dict(drops), 'bare': bare,
            'placed': [{k: v for k, v in r_.items() if k != 'quad'} for r_ in out]}
