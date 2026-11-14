"""Town walls the way the game builds its own: one family's pieces laid as a continuous run, each set on the last by a
join the game itself uses (exteriorsurvey's outdoor joins, their exact poses), so the pieces line up and meet as the
game's do. Never pieces scattered where a wall should be (the user, 2026-10-30: "the walls line up, the pieces snap
together, and it looks like a real wall").

  kits(db)    for every family with a wall the game runs piece after piece: its straight piece and step, its
              corners (a corner piece, a tower, or the straight turned on itself) for a turn either way, the pieces it
              sets in line (gates, towers, arches) and how often, and the cultures whose towns have it
  lay(db, plan, family=None)   the wall for a town plan: an outline square to the town, laid corner unit by corner
              unit with straights between, gates where streets leave, towers as often as the game's; checked (every
              piece joined to the next by a game join, nothing left open) and set on the ground
"""
import math
import re
from collections import Counter, defaultdict

import exteriorsurvey as es
import mapdata
import townsurvey

WALLISH = re.compile(r'wall|gate|tower|rampart|parapet|battlement|palisade|_ent_|wallent|arch')
NOT_WALL = re.compile(r'house|ruin|decal|fence|collision|property|farm|dngruin|_wallb_|stair|ladder')
GATEISH = re.compile(r'gate|wallent|_ent_|arch')
TOWERISH = re.compile(r'tower')
MIN_STEPS = 4                  # the game runs the straight on itself at least this often
STEP_MIN = 192                 # (a straight's step: shorter is a post or a trim)
SNAP = 12                      # units a join's pose may miss its line and still count as in line
MARGIN = 640                   # the wall stands this far outside the plots
OVERLAP_MAX = 0.5              # of a step: the last straight of a side may overlap its neighbour this much, when the
                               # game itself sets that straight on itself at a shorter step (Hlaalu at 128 of 256)


def _ang(deg):
    """A turn in degrees folded to (-180, 180]."""
    return (deg + 180.0) % 360.0 - 180.0


class Pose:
    __slots__ = ('x', 'y', 'z', 'rz', 'id', 's')

    def __init__(self, x, y, z, rz, id_=None):
        self.x, self.y, self.z, self.rz, self.id = x, y, z, rz % (2 * math.pi), id_
        self.s = 1.0                        # (its scale: Anvil's gate arch stands at 1.14, ROUND)

    def then(self, e, id_=None):
        """The pose a join's exact [lx, ly, dz, turn deg] puts the next piece at (adjacency.to_world's turn)."""
        c, s = math.cos(self.rz), math.sin(self.rz)
        return Pose(self.x + e[0] * c + e[1] * s, self.y - e[0] * s + e[1] * c, self.z + e[2], self.rz + math.radians(e[3]), id_)

    def local(self, wx, wy):
        dx, dy = wx - self.x, wy - self.y
        c, s = math.cos(self.rz), math.sin(self.rz)
        return dx * c - dy * s, dx * s + dy * c

    def dir(self, v):
        """A local direction in the world."""
        c, s = math.cos(self.rz), math.sin(self.rz)
        return v[0] * c + v[1] * s, -v[0] * s + v[1] * c


_kits = {}


def _joins(db):
    S = es.survey(db)['outdoor']
    J, EX = S['joins'], S['exact']
    out = defaultdict(list)                  # model: [(target, n, exact)]
    for m, sides in EX.items():
        for s_, rels in sides.items():
            if s_ in ('U', 'D', 'in'):
                continue
            for rs, e in rels.items():
                out[m].append((rs.split('@')[0], J[m][s_][rs], e))
    return out, S['placed']


def kits(db):
    k = id(db.recs)
    if k in _kits:
        return _kits[k]
    import townbuild
    JN, placed = _joins(db)
    fams = defaultdict(list)
    for m, n in placed.items():
        if WALLISH.search(m) and not NOT_WALL.search(m):
            fams[townbuild.family(m)].append(m)
    out = {}
    for fam, ms in fams.items():
        kit = _kit(fam, set(ms), JN, placed)
        if kit:
            out[fam] = kit
    # (the cultures whose game towns stand their walls: wall pieces within a town's cells)
    for t in townsurvey.survey(db)['towns']:
        c = Counter()
        for gx, gy in t['cells']:
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                f = townbuild.family(r['id'].lower())
                if f in out and r['id'].lower() in out[f]['models']:
                    c[f] += 1
        for f, n in c.items():
            if n >= 6:
                cu = out[f].setdefault('cultures', {})
                cu[t['culture']] = cu.get(t['culture'], 0) + 1
                out[f].setdefault('towns', []).append(t['name'])
    _round_kits(db, out)
    _kits[k] = out
    return out


def _kit(fam, ms, JN, placed):
    """A family's wall kit, or None when the game never runs it piece after piece."""
    best = None
    for m in ms:
        steps = Counter()
        short = 0
        for t, n, e in JN.get(m, ()):
            if t != m or abs(_ang(e[3])) > 2 or abs(e[2]) > 4:
                continue
            for ax in (0, 1):
                a, lat = e[ax], e[1 - ax]
                if abs(lat) <= SNAP and abs(a) >= STEP_MIN:
                    steps[(ax, int(round(abs(a) / 8.0)) * 8)] += n
                elif abs(lat) <= SNAP and 64 <= abs(a) < STEP_MIN:
                    short += n
        if not steps:
            continue
        (ax, L), n = steps.most_common(1)[0]
        if n < MIN_STEPS:
            continue
        # (overlap allowed: the game also sets it on itself at a shorter step along the same axis)
        shorter = sum(v for (a2, l2), v in steps.items() if a2 == ax and l2 < L) + short
        if best is None or n > best['n']:
            best = {'straight': m, 'axis': ax, 'L': float(L), 'n': n, 'overlap': shorter >= 2}
    if not best:
        return None
    S, ax, L = best['straight'], best['axis'], best['L']
    run = (1.0, 0.0) if ax == 0 else (0.0, 1.0)
    # in line: S -> X along +run, X -> S on along +run, both with no turn
    inline = {}
    corners = {}
    p0 = Pose(0, 0, 0, 0)
    for t, n1, e1 in JN.get(S, ()):
        if t not in ms and t != S:
            continue
        X = p0.then(e1, t)
        # (corner direct: the straight turned on itself, a quarter either way, beyond the end)
        for t2, n2, e2 in JN.get(t, ()):
            if t2 != S:
                continue
            S1 = X.then(e2, S)
            turn = _ang(math.degrees(S1.rz))
            if t == S:
                continue
            if abs(turn) <= 2:
                # (in line: on along the run, on the same line)
                a1 = e1[0] * run[0] + e1[1] * run[1]
                lat1 = e1[1] * run[0] - e1[0] * run[1]
                lx, ly = S1.x, S1.y
                a2 = lx * run[0] + ly * run[1]
                lat2 = ly * run[0] - lx * run[1]
                if a1 > 0 and a2 > a1 and abs(lat1) <= SNAP and abs(lat2) <= SNAP and abs(S1.z) <= 4:
                    w = min(n1, n2)
                    if w >= 2 and (t not in inline or w > inline[t]['n']):
                        inline[t] = {'a': a1, 'span': a2, 'e1': e1, 'e2': e2, 'n': w,
                                     'kind': 'gate' if GATEISH.search(t) else 'tower' if TOWERISH.search(t) else 'piece'}
            elif abs(abs(turn) - 90) <= 3:
                w = min(n1, n2)
                _corner(corners, S, run, [(t, e1), (S, e2)], turn, w)
    # the straight turned on itself directly
    for t, n1, e1 in JN.get(S, ()):
        if t == S and abs(abs(_ang(e1[3])) - 90) <= 3:
            _corner(corners, S, run, [(S, e1)], _ang(e1[3]), n1)
    # (a corner the game turned once may be two pieces that only happen to touch: Reach's fort wall)
    corners = {k_: v for k_, v in corners.items() if v['n'] >= 2}
    if not corners:
        return None
    # its ends: a piece that finishes the run, after the last straight (fwd) or before the first (back), on its line
    ends = {}
    for t, n1, e1 in JN.get(S, ()):
        if t == S or t not in ms or not re.search(r'end|post|cap', t):
            continue
        a1 = e1[0] * run[0] + e1[1] * run[1]
        lat1 = e1[1] * run[0] - e1[0] * run[1]
        if abs(lat1) > SNAP or abs(e1[2]) > 4 or abs(a1) < 32:
            continue
        k_ = 'fwd' if a1 > 0 else 'back'
        if n1 >= 2 and (k_ not in ends or n1 > ends[k_]['n']):
            ends[k_] = {'id': t, 'e': e1, 'n': n1}
    # the towers the game stands right beside a corner, in the place of the straight there (Imperial: wall_tower_01 a step
    # on from corner_01, 12 of its 71 town corners, lab jcorner2): {corner id: [(tower id, exact join from the corner)]}
    ctow = {}
    for v in corners.values():
        C = v['chain'][0][0] if v['chain'] and v['chain'][0][0] != S else None
        if not C or C in ctow:
            continue
        for t, n1, e1 in JN.get(C, ()):
            if t in ms and TOWERISH.search(t) and n1 >= 2 and abs(e1[2]) <= 4:
                ctow.setdefault(C, []).append((t, e1))
    # (how often each in-line piece stands among the straights: one in every so many)
    for t, v in inline.items():
        v['every'] = max(2.0, placed.get(S, 1) / float(max(1, placed.get(t, 1))))
    return {'family': fam, 'straight': S, 'axis': ax, 'L': L, 'overlap': best['overlap'], 'runs': best['n'],
            'inline': inline, 'corners': corners, 'ends': ends, 'corner_towers': ctow, 'models': sorted(ms), 'placed': sum(placed.get(m, 0) for m in ms)}


def _corner(corners, S, run, chain, turn, w):
    """A corner unit: from a straight S0 at the origin, the pieces after it to the straight S1 turned a quarter. Its
    vertex (where S0's line meets S1's) in S0's frame, and how far S1 stands past it, on its own line."""
    p = Pose(0, 0, 0, 0)
    poses = []
    for t, e in chain:
        p = p.then(e, t)
        poses.append(p)
    S1 = poses[-1]
    if abs(S1.z) > 4:
        return
    d1 = S1.dir(run)
    # S0's line: lat = l0 (y = 0 when run is x); S1's line passes S1 along d1. Their meeting point:
    # (on S0's line every point is t*run; on S1's, S1 + u*d1)
    det = run[0] * (-d1[1]) - run[1] * (-d1[0])
    if abs(det) < 1e-6:
        return
    bx, by = S1.x, S1.y
    tt = (bx * (-d1[1]) - by * (-d1[0])) / det
    uu = (run[0] * by - run[1] * bx) / det
    if tt <= 0 or uu >= 0:
        # (the vertex must lie ahead of S0 and behind S1, else it is not a turn of the run but a branch)
        return
    side = 1 if turn > 0 else -1
    have = corners.get(side)
    if have is None or w > have['n']:
        corners[side] = {'chain': [[t, list(e)] for t, e in chain], 'p': tt, 'q': -uu, 'n': w}


# ------------------------------------------------------------------------------------------ walls of round towers
# Anvil's city wall (docs/cyrodiil-study-2026-11.md): no corner piece and no grid. A round tower stands over every
# joint, at a corner and between two lengths in one line alike (28 towers to 41 lengths); each length runs from tower
# to tower at whatever angle, its ends hidden 180 to 320 inside them; the whole ring stands at one level, the ground
# made to fit; a way in is the low wall's great arch (citywall_03) raised and scaled between two of the taller towers.
# Laid so here: the outline's corners are towers, each side one length or one gate.
ROUND = {'t_imp_setanv': {
    'straight': 't_imp_setanv_x_citywall_01', 'L': 2240.0,
    # (tower to tower: the game's 2,380 to 2,880. Down to 2,000 here, a length's end then up to 120 past its tower's
    # middle and still inside it (the tower 517 in radius, the wall 350 either side of its line): with 2,400 the least no
    # side between 2,880 and 4,800 long could be walled, and a drawn town shrank by a third)
    'side': (2000.0, 2880.0),
    'tower': 't_imp_setanv_x_citywalltower_01', 'tall': 't_imp_setanv_x_citywalltower_02', 'tower_dz': 0.0, 'tower_r': 517.0,
    'gate': 't_imp_setanv_x_citywall_03', 'gate_scale': 1.14, 'gate_dz': 340.0,      # (the game's: 332 to 346 over the wall's)
    'arch': 't_imp_setanv_x_citywallent_01', 'arch_at': 465.0, 'arch_dz': 880.0,     # (on the walk, where it enters a tower)
    'low': 't_imp_setanv_x_citywall_02', 'low_L': 1755.0, 'low_dz': -40.0,           # (the harbour's wall, and its arch)
    'low_gate': 't_imp_setanv_x_citywall_03',
    'rise': 24.0,                          # (a length's origin over the ground under it: 24 at the game's median)
    'sea_z': 448.0,                        # (what stands in the sea: its origin this far over the water at most, Anvil's)
    # (how much of each piece's foot belongs in the ground: Anvil's lengths stand 300 deep, their towers 665, the
    # raised arch 570. Measured to their true bottoms they stood with 24 in the ground and the first street graded
    # past a gate left the wall's foot in the air, the practice of 2026-11-13)
    'foot': {'t_imp_setanv_x_citywall_01': 270.0, 't_imp_setanv_x_citywalltower_01': 600.0, 't_imp_setanv_x_citywalltower_02': 600.0,
             't_imp_setanv_x_citywall_03': 500.0, 't_imp_setanv_x_citywall_02': 700.0},
    'back': 520.0,                         # (the town planned this much further in: the wall is 700 deep, a tower 1,034)
    'cultures': {'Anvil': 2, 'Gold Coast': 2}, 'towns': ['Anvil']},
    # The balustrade wall round Charach's villas (docs/cyrodiil-study-2026-11.md): arcaded lengths 800 long, a round pier
    # between every two and on every corner (405 to 452 from a length's middle), an arched gate with a pier 486 to 495
    # either side of its middle, the gate scaled 1.3 to 1.42 and its piers 1.2. Low: it follows the ground, a piece at
    # a time (their origins 130 to 153 over it), and no ground is moved for it. Never chosen by itself: asked for.
    't_imp_setstr': {
        'low': True, 'straight': 't_imp_setstr_x_wall_01', 'L': 800.0, 'side': (812.0, 905.0),
        'tower': 't_imp_setstr_x_wallpillar_01', 'tall': 't_imp_setstr_x_wallpillar_01', 'tall_scale': 1.2, 'tower_dz': 0.0, 'tower_r': 88.0,
        'gate': 't_imp_setstr_x_gate_01', 'gate_half': 430.0, 'gate_dz': 0.0,
        'rise': 150.0, 'back': 0.0, 'cultures': {}, 'towns': ['Charach']}}
ROUND_SHARP = 60.0             # (degrees: two lengths meeting sharper than this cross outside their tower)
_FOOT = {k_.lower(): v_ for R_ in ROUND.values() for k_, v_ in (R_.get('foot') or {}).items()}


def _round_kits(db, out):
    """The walls of round towers the load order holds all the pieces of, as kits beside the learnt ones."""
    for fam, R in ROUND.items():
        ids = [R[k] for k in (('straight', 'tower', 'gate') if R.get('low') is True else ('straight', 'tower', 'tall', 'gate', 'arch', 'low'))]
        if any(db.resolve_id(i) is None for i in ids):
            continue
        out[fam] = {'family': fam, 'straight': R['straight'], 'axis': 0, 'L': R['L'], 'overlap': False, 'runs': 28,
                    'inline': {}, 'corners': {}, 'ends': {}, 'corner_towers': {}, 'models': sorted(set(i.lower() for i in ids)),
                    'placed': sum(len(db.used_in.get(i.lower(), ())) for i in ids) or 100, 'round': R,
                    'cultures': dict(R['cultures']), 'towns': list(R['towns'])}


def _poly_area(P):
    return sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P))) / 2.0


def _hull(pts):
    pts = sorted(set((round(p[0], 1), round(p[1], 1)) for p in pts))
    if len(pts) < 3:
        return pts
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def round_outline(plan, kit, drawn=None):
    """The tower spots of a wall of round towers for a town: the drawn outline (else the town's own hull, MARGIN out)
    with only its real corners, no corner too sharp, every side whole tower-to-tower lengths, a tower between every
    two lengths of a long side. [(x, y)], or [] where nothing can be walled."""
    import wallangle
    R = kit['round']
    lo, hi = R['side']
    D = [(float(p[0]), float(p[1])) for p in (drawn if drawn is not None else plan.get('drawn') or ()) if len(p) >= 2]
    if len(D) < 3:
        H = _hull(_town_pts(plan))
        if len(H) < 3:
            return []
        cx, cy = sum(p[0] for p in H) / len(H), sum(p[1] for p in H) / len(H)
        D = []
        for x, y in H:
            u = _unit(x - cx, y - cy)
            D.append((x + u[0] * (MARGIN + R['back']), y + u[1] * (MARGIN + R['back'])))
    old = wallangle.ANGLE_LEAST
    wallangle.ANGLE_LEAST = ROUND_SHARP
    try:
        D = wallangle.simplify(D, lo, least=1)
        D = wallangle.simplify(wallangle.blunt(D, lo), lo, least=1)
    finally:
        wallangle.ANGLE_LEAST = old
    if len(D) < 3:
        return []
    D, _miss = wallangle.fit_lengths(D, lo, hide=(hi - lo) / 2.0, least=1)
    out = []
    n = len(D)
    for k in range(n):
        a, b = D[k], D[(k + 1) % n]
        S = math.hypot(b[0] - a[0], b[1] - a[1])
        m = max(1, int(math.ceil(S / hi - 1e-6)))
        while m > 1 and S / m < lo - 8:
            m -= 1
        for i in range(m):
            out.append((round(a[0] + (b[0] - a[0]) * i / m, 2), round(a[1] + (b[1] - a[1]) * i / m, 2)))
    return out


def lay_round(db, plan, fam, kit):
    """A wall of round towers round a town plan, as lay() gives a wall: a tower on every corner of its outline, one
    length between each two, a gate (the great arch, raised between two taller towers) where a street leaves, the
    walk's arches where it enters a tower. Each side's piece is a 'run' of its own; the towers, the gates and the
    arches take their level from the lengths beside them (grounded)."""
    R = kit['round']
    plan['_fam'] = fam
    _KEEP_SEA[0] = False
    if plan.get('wall_outline'):
        poly = [(float(p[0]), float(p[1])) for p in plan['wall_outline']]
    else:
        poly = round_outline(plan, kit)
        plan['_led'] = True
    if len(poly) < 3:
        return {'family': fam, 'kit': kit, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No plots to wall']}
    # (walked clockwise: a length's outer face, the arcade, is its +y, to the left of the way it runs)
    if _poly_area(poly) > 0:
        poly = poly[::-1]
    n = len(poly)
    faults = []
    side = lambda k: (poly[k], poly[(k + 1) % n])
    low_kit = R.get('low') is True               # (a low wall of piers: it stops at the water, and follows the ground)
    open_ = bool(plan.get('open_sea')) or low_kit
    # the sides that stand in the sea: left out when the town is open to the water, their towers with them
    wet = set()
    if db is not None:
        for k in range(n):
            a, b = side(k)
            zs = sorted((-9999.0 if z is None else z) for z in (mapdata.terrain_z(db, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in (0.1, 0.3, 0.5, 0.7, 0.9)))
            # (most of it over the water: the harbour's low wall there, or nothing when the town is open to the sea)
            if zs[2] < ROUND_WET and zs[3] < 0:
                wet.add(k)
    # (the middle one of the longest run of sides in the water: the arch boats pass under)
    water_gate = None
    if wet and not open_:
        runs_, cur = [], []
        for k in list(range(n)) + list(range(n)):
            if k in wet:
                cur.append(k)
            else:
                if cur:
                    runs_.append(cur)
                cur = []
        runs_ = [r_[:n] for r_ in runs_ + ([cur] if cur else [])]
        if runs_:
            best_ = max(runs_, key=len)
            water_gate = best_[len(best_) // 2]
    ok_sides = set(range(n)) - wet
    _KEEP_SEA[0] = bool(wet) and not low_kit
    streets, roads = _street_crossings(plan, poly)
    if any(k not in ok_sides for k in streets):
        streets = defaultdict(list, {k: v for k, v in streets.items() if k in ok_sides})
    mine = user_gates(plan, poly, roads, 256.0, ok_sides or None)
    if mine:
        streets, roads = mine
    elif db is not None:
        streets, roads = _downhill_gates(db, poly, streets, roads)
    if not any(streets.values()) and not mine:
        streets, roads = _fallback_gate(db, plan, poly, roads, 256.0, ok_sides or None)
    gate_sides = {k for k, v in streets.items() if v and k in ok_sides}
    # (never two gates side by side: the one nearer its side's middle stays)
    for k in sorted(gate_sides):
        if (k + 1) % n in gate_sides and k in gate_sides and n > 3:
            a, b = side(k)
            c_, d_ = side((k + 1) % n)
            off = lambda kk, A, B: min(abs(h - math.hypot(B[0] - A[0], B[1] - A[1]) / 2.0) for h in streets[kk])
            gate_sides.discard(k if off(k, a, b) > off((k + 1) % n, c_, d_) else (k + 1) % n)
    pieces = []
    for k in range(n):
        if k in wet and open_:
            continue
        a, b = side(k)
        d = _unit(b[0] - a[0], b[1] - a[1])
        S = math.hypot(b[0] - a[0], b[1] - a[1])
        if k in wet:
            # (the harbour's wall: the low length, made longer as the game makes its arch, so its ends stand inside
            # the towers; at the towers' level less a little, as Anvil's; no ground is raised under it)
            lid = R['low_gate'] if k == water_gate else R['low']
            lp = Pose((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, 0.0, _rz_for(kit, d), lid)
            lp.s = round(min(1.3, max(1.0, (S / 2.0 - 250.0) / (R['low_L'] / 2.0))), 3)
            pieces.append({'id': lid, 'pose': lp, 'kind': 'seawall', 'dz': R['low_dz'], 'sea': True, 'nofill': True})
            continue
        if not (R['side'][0] - 160 <= S <= R['side'][1] + 60):
            faults.append('side %d: %.0f from tower to tower' % (k, S))
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        rz = _rz_for(kit, d)
        if k in gate_sides and low_kit:
            g = Pose(mx, my, 0.0, rz, R['gate'])
            # (the gate made as wide as its two piers stand apart, as the game scales it)
            g.s = round(max(1.0, min(1.5, (S / 2.0 + 60.0) / R['gate_half'])), 3)
            host = {'id': R['gate'], 'pose': g, 'kind': 'gate', 'run': k}
        elif k in gate_sides:
            g = Pose(mx, my, 0.0, rz, R['gate'])
            g.s = R['gate_scale']
            # (levelled as a length of the wall, 'lift' over it once the wall is set: grounded)
            host = {'id': R['gate'], 'pose': g, 'kind': 'gate', 'run': k, 'lift': R['gate_dz']}
        else:
            host = {'id': R['straight'], 'pose': Pose(mx, my, 0.0, rz, R['straight']), 'kind': 'wall', 'run': k}
        pieces.append(host)
        # (the walk's arch at each end, facing along the wall, where the walk meets the tower: 58 for Anvil's 28 towers)
        for sgn in (-1.0, 1.0) if R.get('arch') else ():
            t = S / 2.0 - R['arch_at']
            ap = Pose(mx + sgn * d[0] * t, my + sgn * d[1] * t, 0.0, rz + (0.0 if sgn > 0 else math.pi), R['arch'])
            pieces.append({'id': R['arch'], 'pose': ap, 'kind': 'arch', 'dz': R['arch_dz'], 'host': host['pose']})
    for k in range(n):
        if open_ and (k - 1) % n in wet and k in wet:
            continue
        v = poly[k]
        tall = (k in gate_sides) or ((k - 1) % n in gate_sides)
        if not open_ and (k in wet) != ((k - 1) % n in wet):
            tall = True                              # (where the land's wall meets the sea's: the step hides in the taller tower)
        tid = R['tall'] if tall else R['tower']
        d = _unit(poly[(k + 1) % n][0] - v[0], poly[(k + 1) % n][1] - v[1])
        tw_ = {'id': tid, 'pose': Pose(v[0], v[1], 0.0, _rz_for(kit, d), tid), 'kind': 'post' if low_kit else 'bigtower', 'dz': R['tower_dz'], 'vertex': k}
        if tall and R.get('tall_scale'):
            tw_['pose'].s = R['tall_scale']          # (a gate's piers stand bigger)
        gv_ = mapdata.terrain_z(db, v[0], v[1]) if db is not None else None
        if (gv_ is not None and gv_ < 0) or (k in wet and (k - 1) % n in wet):
            tw_.update(sea=True, nofill=True)        # (a tower in the water: Anvil's harbour towers)
        pieces.append(tw_)
    n_g = len([p for p in pieces if p['kind'] == 'gate'])
    W_ = {'family': fam, 'kit': kit, 'pieces': pieces, 'outline': poly, 'gates': n_g, 'faults': faults, 'joins': 0,
          'angled': {'poly': [list(p) for p in poly], 'fort': [], 'no_tower': [], 'round': True}, 'led': True, 'rise': R['rise'],
          'roads': _gate_roads(poly, roads, pieces, 2000.0) if n_g else []}
    if low_kit:
        W_['palisade'] = True                    # (set on the ground a piece at a time, no ground moved: _palisade_grounded)
    return W_


GATE_WAY_DEEP = 1300.0         # (a round wall's gateway: kept clear this far in and out of the arch)


def gate_ways(W):
    """[[(x, y) x4]]: the way through each gate of a wall of round towers or piers, GATE_WAY_DEEP in and out of it, as
    wide as its arch: ground nothing is set on (the town's rocks, its dressing, its trees)."""
    if not ((W or {}).get('kit') or {}).get('round'):
        return []
    out = []
    for p_ in W.get('pieces') or ():
        cs = p_.get('corners')
        if p_.get('kind') != 'gate' or not cs or len(cs) < 4:
            continue
        q_ = p_['pose']
        c_, s_ = math.cos(q_.rz), math.sin(q_.rz)
        hw_ = 0.33 * math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1]) + 60.0
        out.append([(q_.x + lx * c_ + ly * s_, q_.y - lx * s_ + ly * c_) for lx, ly in ((-hw_, -GATE_WAY_DEEP), (hw_, -GATE_WAY_DEEP), (hw_, GATE_WAY_DEEP), (-hw_, GATE_WAY_DEEP))])
    return out


FOOT_ROCKS = ('t_cyr_terrrockgc_rock_15', 't_cyr_terrrockgc_rock_19', 't_cyr_terrrockgc_rock_21', 't_cyr_terrrockgc_rock_24', 't_cyr_terrrockgc_rock_25',
              't_cyr_terrrockgc_rock_29', 't_cyr_terrrockgc_rock_17', 't_cyr_terrrockgc_rock_13')
FOOT_SHOWS = 24.0              # (a foot this far out of the ground or more wants a boulder)
FOOT_GAP = 520.0               # (boulders along a face about this far apart, none nearer another than 0.7 of it)


def foot_rocks(db, W, seed=1):
    """[{'id', 'p', 's', 'role': 'rock'}]: boulders under a round wall's feet where they show. A length's true foot is
    its model's bottom (321 under its origin, of which the ground takes 270 where it can); on a bank that falls to the
    water the land cannot be raised (the harbour's floor stays the sea's), so the foot hangs: a boulder there, its
    bottom under the ground or the water, its top over the foot. Nothing in a gate's way."""
    import random
    R = (W.get('kit') or {}).get('round') or {}
    if not R or R.get('low') is True or not W.get('pieces'):
        return []
    ids = [i for i in FOOT_ROCKS if db.resolve_id(i) is not None]
    if not ids:
        return []
    rng = random.Random('%s|foot rocks' % seed)
    gates = [p['pose'] for p in W['pieces'] if p.get('kind') == 'gate']
    out, at = [], []
    for p in W['pieces']:
        if p.get('kind') not in ('wall', 'bigtower') or p.get('sea'):
            continue
        q = p['pose']
        ri = db.resolve_id(p['id'])
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        s = getattr(q, 's', 1.0) or 1.0
        foot = q.z + b[2] * s
        c, sn = math.cos(q.rz), math.sin(q.rz)
        if p['kind'] == 'bigtower':
            r_ = 0.5 * (b[3] - b[0]) * s
            spots = [(r_ * math.cos(a_ * math.pi / 4), r_ * math.sin(a_ * math.pi / 4), math.cos(a_ * math.pi / 4), math.sin(a_ * math.pi / 4)) for a_ in range(8)]
        else:
            n_ = max(2, int((b[3] - b[0]) * s / FOOT_GAP))
            xs = [b[0] * s + (b[3] - b[0]) * s * (i + 0.5) / n_ for i in range(n_)]
            spots = [(x_, b[4] * s, 0.0, 1.0) for x_ in xs] + [(x_, b[1] * s, 0.0, -1.0) for x_ in xs]
        for lx, ly, ox, oy in spots:
            # (the ground just outside the face, where the eye meets the foot)
            px, py = lx + ox * 90.0, ly + oy * 90.0
            wx, wy = q.x + px * c + py * sn, q.y - px * sn + py * c
            g = mapdata.terrain_z(db, wx, wy)
            if g is None or g >= foot - FOOT_SHOWS:
                continue
            if any(abs((wx - g_.x) * math.cos(g_.rz) - (wy - g_.y) * math.sin(g_.rz)) < 700.0 and math.hypot(wx - g_.x, wy - g_.y) < 1500.0 for g_ in gates):
                continue
            if any(math.hypot(wx - a_[0], wy - a_[1]) < 0.7 * FOOT_GAP for a_ in at):
                continue
            rid = rng.choice(ids)
            rb = mapdata.object_bounds(db, db.resolve_id(rid))
            if not rb:
                continue
            low_ = max(g, -420.0) - 110.0                      # (its bottom well under the ground, or the water)
            need = (foot + 170.0) - low_
            sc = max(0.8, min(2.6, need / float(rb[5] - rb[2])))
            z = low_ - rb[2] * sc
            out.append({'id': rid, 'p': [round(wx, 1), round(wy, 1), round(z, 1), 0.0, 0.0, round(rng.uniform(0, 2 * math.pi), 4)], 's': round(sc, 2), 'role': 'rock'})
            at.append((wx, wy))
    return out


ROUND_WET = -160.0             # (a side whose ground lies under this all along stands in the sea)
SEA_KEEP = -24.0               # (ground under this is the harbour's floor: never raised by a wall that stands in the sea)
_KEEP_SEA = [False]


# ------------------------------------------------------------------------------------------------ laying a wall
def _town_pts(plan):
    pts = []
    for q in plan['plots']:
        pts.extend(q.get('rect') or [(q['x'], q['y'])])
    return pts


def _town_frame(plan):
    """The town's own square: the turn whose box round its plots is smallest, so the wall hugs the town and runs with
    its streets (a wall square to the compass round a town laid corner-wise was all steps, lab 2026-10-30)."""
    pts = _town_pts(plan)
    best = (None, 0.0)
    for deg in range(0, 90, 3):
        th = math.radians(deg)
        c, s = math.cos(th), math.sin(th)
        us = [x * c + y * s for x, y in pts]
        vs = [-x * s + y * c for x, y in pts]
        a = (max(us) - min(us) + 2 * MARGIN) * (max(vs) - min(vs) + 2 * MARGIN) if pts else 0
        if best[0] is None or a < best[0]:
            best = (a, th)
    # (square to the way most buildings face when that is nearly as tight: a grid town walled a few degrees off its
    # streets looked careless, lab 2026-10-30)
    hs = Counter(int(round((math.degrees(q['face']) % 90.0) / 3.0)) * 3 % 90 for q in plan['plots'])
    if hs:
        th = math.radians(hs.most_common(1)[0][0])
        c, s = math.cos(th), math.sin(th)
        us = [x * c + y * s for x, y in pts]
        vs = [-x * s + y * c for x, y in pts]
        if (max(us) - min(us) + 2 * MARGIN) * (max(vs) - min(vs) + 2 * MARGIN) <= best[0] * 1.12:
            return th
    return best[1]


MAX_CORNERS = 8
FILL = 0.85                    # the town fills this share of its box: walled square round it (at 0.6 an L-shaped town was
                               # walled as a box, a third of it empty ground, the Tamriel practice 2026-10-31)


DRY = 48                       # a wall square's ground stands at least this far over the water everywhere
STEEP = 520                    # and rises or falls no more than this across it (a cliff's edge is no place for a wall)


def outline(plan, cell=1024.0, db=None, step=1.0):
    """An outline square to the town round its plots and MARGIN beyond, its sides whole cells: the town's box when
    the town fills it well, else grid squares of the town's frame with rows and columns filled (no holes, no notches
    into it); [(x, y)] counter-clockwise, and its frame angle."""
    plan.pop('_led', None)
    plan.pop('_angled', None)
    drawn = [(float(p[0]), float(p[1])) for p in plan.get('drawn') or () if len(p) >= 2]
    if len(drawn) >= 3 and step >= 64 and plan.get('_fam') in BIG and not plan.get('square_walls') and not _square_drawn(plan, drawn):
        # (off the square, or beside a castle that stands at another angle: the drawing's own lines, straight runs at
        # any angle with a round tower over every corner, wallangle.py. Squared to one frame it came out in steps)
        import wallangle
        A = wallangle.outline(drawn, _forts_by(plan, drawn), step)
        if A:
            plan['_led'] = True
            plan['_angled'] = A
            return A['poly'], 0.0
    if len(drawn) >= 3:
        # (a palisade asks at a step of 1, its sections any length: a lattice of 256 then, not 76 million squares)
        led = _drawn_outline(plan, drawn, db, step if step >= 64 else 256.0)
        if led:
            plan['_led'] = True
            return led
    forts = _forts_near(plan)
    th = _fort_angle(forts[0]) if forts else _town_frame(plan)
    c, s = math.cos(th), math.sin(th)
    pts = [(x * c + y * s, -x * s + y * c) for x, y in _town_pts(plan)]
    if not pts:
        return [], th
    x0 = min(p[0] for p in pts) - MARGIN
    y0 = min(p[1] for p in pts) - MARGIN
    # (squares sized to the town each way, whole squares to its ends: rounded up to whole cells, the wall stood up to a
    # cell beyond the town on two sides, half its ground empty against a fifth inside the game's, lab jhug 2026-10-31)
    ex, ey = max(p[0] for p in pts) + MARGIN - x0, max(p[1] for p in pts) + MARGIN - y0

    def fit(e):
        # (whole straights a square, so a side's straights fill it; the count of squares leaving least to spare)
        best = None
        for n in range(max(1, int(e // cell)), int(math.ceil(e / cell)) + 2):
            cs = step * math.ceil(e / n / step - 1e-6)
            if cs < 0.6 * cell and n > 1:
                continue
            if best is None or n * cs - e < best[0] * best[1] - e:
                best = (n, cs)
        return best
    nx, cu = fit(ex)
    ny, cv = fit(ey)
    x0 -= (nx * cu - ex) / 2            # (what is to spare, half each side)
    y0 -= (ny * cv - ey) / 2
    # (a castle standing in the wall: the squares cut into wall lengths, a length's corner set on the castle's, so the
    # town's wall runs onto the castle's line by whole lengths)
    mu, mv = max(1, int(round(cu / max(step, 128.0)))), max(1, int(round(cv / max(step, 128.0))))
    pu, pv = cu / mu, cv / mv
    if forts:
        fx, fy = forts[0]['ring'][0]
        fu, fv = fx * c + fy * s, -fx * s + fy * c
        ru, rv = (fu - x0) % pu, (fv - y0) % pv
        x0 += ru if ru <= pu / 2 else ru - pu
        y0 += rv if rv <= pv / 2 else rv - pv
    on = set()
    for q in plan['plots']:
        r = [(x * c + y * s, -x * s + y * c) for x, y in (q.get('rect') or [(q['x'], q['y'])])]
        ax0 = int((min(p[0] for p in r) - MARGIN - x0) // cu)
        ax1 = int((max(p[0] for p in r) + MARGIN - x0 - 1) // cu)
        ay0 = int((min(p[1] for p in r) - MARGIN - y0) // cv)
        ay1 = int((max(p[1] for p in r) + MARGIN - y0 - 1) // cv)
        for i in range(max(0, ax0), min(nx - 1, ax1) + 1):
            for j in range(max(0, ay0), min(ny - 1, ay1) + 1):
                on.add((i, j))
    plots_on = set(on)
    # (rows and columns filled between their ends: no holes, no notches; the result is orthogonally convex)
    for _ in range(3):
        rows = defaultdict(list)
        for i, j in on:
            rows[j].append(i)
        for j, l in rows.items():
            for i in range(min(l), max(l) + 1):
                on.add((i, j))
        cols = defaultdict(list)
        for i, j in on:
            cols[i].append(j)
        for i, l in cols.items():
            for j in range(min(l), max(l) + 1):
                on.add((i, j))
    # (an L or a notch where the town leaves a corner of its box empty, but never a staircase of jogs: the game's walls
    # run long straight sides, and 12 to 14 corners round a town was the user's "fever dream" again)
    if len(on) >= FILL * nx * ny or len(_trace(on)) > MAX_CORNERS:
        on = {(i, j) for i in range(nx) for j in range(ny)}
    # (the game's own buildings and doors inside the drawn outline: their squares are left out at the edge, so the wall
    # skirts a settlement it is drawn over; what stands in the middle of the town is enclosed and said so. A cold-start
    # town over Dren Plantation walled in 140 of the game's objects, the in-game harness, 2026-11-02)
    blocked = set()
    for ob in plan.get('obstacles') or ():
        ox = sum(p[0] for p in ob) / len(ob)
        oy = sum(p[1] for p in ob) / len(ob)
        if any(_inside(g['ring'], (ox, oy)) or _ring_dist(g['ring'], ox, oy) <= 400 for g in forts):
            continue                         # (the castle's own: the meld below sets the wall to it)
        u, v = ox * c + oy * s, -ox * s + oy * c
        blocked.add((int((u - x0) // cu), int((v - y0) // cv)))
    if db is not None:
        on = _on_land(db, on, x0, y0, (cu, cv), c, s, plots_on, blocked)
    if forts:
        melded = _meld(plan, db, on, forts, x0, y0, pu, pv, mu, mv, c, s)
        if len(melded) >= 4:
            return melded, th
    poly = _trace(on)
    out = []
    for i, j in poly:
        u, v = x0 + i * cu, y0 + j * cv
        out.append((u * c - v * s, u * s + v * c))
    return out, th


# ------------------------------------------------------------------------------------------ the wall as the town is drawn
# The wall stands on the town's drawn outline: a side drawn nearly straight along the town's square is one straight side
# of wall, a slanting side a few big steps (the kits turn square corners only). It hugged the buildings on a grid of
# squares and was cut back square by square at the water, so it ran in staircases along a shore or a slanting side,
# wandered outside what was drawn and left whole sides out (the user, 2026-11-11: "why can't I just draw some walls and
# you figure out something that fits", "two straight lines to the coast").
AXIS_NEAR = math.radians(20)   # (a drawn side within this of the square's axes is one straight side)
DRIFT = 1536.0                 # (and drifts no more than this across: the wall then stands within 768 of the line
                               # drawn; a west side 15 degrees off over 9,300 stood 1,300 outside the drawing at one end,
                               # lab 2026-11-11. In units, not wall lengths: a kit of 256 pieces stepped a side an
                               # Imperial wall ran straight, and its one-handed corners could not turn the step)
STAIR = 2048.0                 # (a slanting side: a step for every this much it runs across)
STAIR_MOST = 3
JOG_LEAST = 768.0              # (two sides in a row this far apart or less are one; no jog shorter than this)
DRAWN_CORNERS = 16             # (more corners than this: a drawn blob, walled round its buildings as before)


SQUARE_NEAR = math.radians(5)  # (a drawn side this near its frame's square, drifting SQUARE_DRIFT at most, is square)
SQUARE_DRIFT = 256.0


def _forts_by(plan, drawn):
    """The castles that stand by a drawn outline (in it, or within FORT_NEAR of it)."""
    return [f for f in _forts(plan)
            if any(_inside(drawn, q) or _ring_dist(drawn, q[0], q[1]) <= FORT_NEAR for q in f['ring'])
            or any(_ring_dist(f['ring'], x, y) <= FORT_NEAR for x, y in drawn)]


def _square_drawn(plan, drawn):
    """Is the drawing square already: every side within SQUARE_NEAR of one frame's axes (the castle's beside it, else
    its own)? Then the kit's own corner pieces wall it best."""
    forts = _forts_by(plan, drawn)
    th = _fort_angle(forts[0]) if forts else _drawn_frame(drawn)
    c, s = math.cos(th), math.sin(th)
    P = [(x * c + y * s, -x * s + y * c) for x, y in drawn]
    n = len(P)
    for k in range(n):
        du, dv = abs(P[(k + 1) % n][0] - P[k][0]), abs(P[(k + 1) % n][1] - P[k][1])
        if du < 1 and dv < 1:
            continue
        a = math.atan2(dv, du)
        if not ((a <= SQUARE_NEAR and dv <= SQUARE_DRIFT) or (a >= math.pi / 2 - SQUARE_NEAR and du <= SQUARE_DRIFT)):
            return False
    return True


def _rectilinear(poly):
    """Does an outline turn square at every corner?"""
    n = len(poly)
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        u = math.atan2(b[1] - a[1], b[0] - a[0])
        v = math.atan2(c_[1] - b[1], c_[0] - b[0])
        t = abs((math.degrees(v - u) + 180.0) % 360.0 - 180.0)
        if abs(t - 90.0) > 3.0:
            return False
    return True


def angled_info(poly, forts):
    """wallangle's notes for an outline handed over without them (the wall's line as a preview showed it): the sides
    whose two ends are corners of one castle's ring are that castle's wall."""
    import wallangle
    keys, bare = [], []
    n = len(poly)
    for f in forts or ():
        at = [k for k in range(n) if any(math.hypot(poly[k][0] - q[0], poly[k][1] - q[1]) <= 4 for q in f['ring'])]
        for k in at:
            bare.append([int(round(poly[k][0])), int(round(poly[k][1]))])
            if (k + 1) % n in at:
                keys.append(list(wallangle._key(poly[k], poly[(k + 1) % n])))
    return {'poly': [tuple(p) for p in poly], 'fort': keys, 'no_tower': bare}


def _drawn_frame(pts):
    """The square a drawn outline runs along: the way of its sides that most of its length lies near."""
    n = len(pts)
    sides = [(math.atan2(pts[(k + 1) % n][1] - pts[k][1], pts[(k + 1) % n][0] - pts[k][0]),
              math.hypot(pts[(k + 1) % n][0] - pts[k][0], pts[(k + 1) % n][1] - pts[k][1])) for k in range(n)]
    best = (None, 0.0)
    for a, _l in sides:
        th = a % (math.pi / 2)
        sc = sum(l * max(0.0, math.cos(4.0 * (b - th))) for b, l in sides)
        if best[0] is None or sc > best[0] + 1e-6:
            best = (sc, th)
    return best[1]


def _straighten(P, step, ou, ov):
    """A drawn outline (points in the town's square, P) as one of square corners on the lattice of wall lengths set at
    (ou, ov): its corners as lattice points [(i, j)], or []. Near-straight sides each on one line through their middle,
    slanting sides in steps about their own line."""
    n = len(P)
    subs = []                                   # [way, the line it lies on, from, to, length]
    for k in range(n):
        a, b = P[k], P[(k + 1) % n]
        du, dv = b[0] - a[0], b[1] - a[1]
        if abs(du) < 1 and abs(dv) < 1:
            continue
        ang = math.atan2(abs(dv), abs(du))
        if ang <= AXIS_NEAR and abs(dv) <= DRIFT:
            subs.append(['U', (a[1] + b[1]) / 2.0, a[0], b[0], abs(du)])
        elif ang >= math.pi / 2 - AXIS_NEAR and abs(du) <= DRIFT:
            subs.append(['V', (a[0] + b[0]) / 2.0, a[1], b[1], abs(dv)])
        else:
            m = max(1, min(STAIR_MOST, int(round(min(abs(du), abs(dv)) / STAIR))))
            if abs(du) >= abs(dv):
                for j in range(m + 1):
                    u0, u1 = a[0] + du * max(0.0, j - 0.5) / m, a[0] + du * min(float(m), j + 0.5) / m
                    subs.append(['U', a[1] + dv * j / m, u0, u1, abs(u1 - u0)])
                    if j < m:
                        subs.append(['V', u1, a[1] + dv * j / m, a[1] + dv * (j + 1) / m, abs(dv) / m])
            else:
                for j in range(m + 1):
                    v0, v1 = a[1] + dv * max(0.0, j - 0.5) / m, a[1] + dv * min(float(m), j + 0.5) / m
                    subs.append(['V', a[0] + du * j / m, v0, v1, abs(v1 - v0)])
                    if j < m:
                        subs.append(['U', v1, a[0] + du * j / m, a[0] + du * (j + 1) / m, abs(du) / m])
    if len(subs) < 3:
        return []
    # (two in a row the same way: one side when their lines lie near, else a jog between them where they meet)
    for _ in range(4 * len(subs) + 8):
        m_ = len(subs)
        for k in range(m_):
            A, B = subs[k], subs[(k + 1) % m_]
            if A[0] != B[0] or m_ < 3:
                continue
            if abs(A[1] - B[1]) <= max(JOG_LEAST, 1.5 * step):
                w = (A[4] + B[4]) or 1.0
                A[1], A[3], A[4] = (A[1] * A[4] + B[1] * B[4]) / w, B[3], A[4] + B[4]
                subs.pop((k + 1) % m_)
            else:
                subs.insert(k + 1, ['V' if A[0] == 'U' else 'U', A[3], A[1], B[1], abs(B[1] - A[1])])
            break
        else:
            break
    m_ = len(subs)
    if m_ < 4 or m_ % 2:
        return []
    q = lambda v, o: int(round((v - o) / step))
    V = []
    for k in range(m_):
        A, B = subs[k], subs[(k + 1) % m_]
        V.append((q(B[1], ou), q(A[1], ov)) if A[0] == 'U' else (q(A[1], ou), q(B[1], ov)))

    def clean(V):
        changed = True
        while changed and len(V) >= 4:
            changed = False
            for k in range(len(V)):
                a_, b_, c_ = V[k - 1], V[k], V[(k + 1) % len(V)]
                if a_ == b_ or (a_[0] == b_[0] == c_[0]) or (a_[1] == b_[1] == c_[1]) or a_ == c_:
                    V.pop(k)
                    changed = True
                    break
        return V
    V = clean(V)
    # (a short jog between two sides running on the same way: the shorter side moved onto the longer's line)
    for _ in range(64):
        m_ = len(V)
        if m_ < 6:
            break
        for k in range(m_):
            p0, p1, p2, p3 = V[k - 1], V[k], V[(k + 1) % m_], V[(k + 2) % m_]
            jog = (p2[0] - p1[0], p2[1] - p1[1])
            if not 1 <= abs(jog[0]) + abs(jog[1]) <= max(1, int(JOG_LEAST // step)):
                continue
            d0, d1 = (p1[0] - p0[0], p1[1] - p0[1]), (p3[0] - p2[0], p3[1] - p2[1])
            if d0[0] * d1[0] + d0[1] * d1[1] <= 0:
                continue                         # (a bump, not a jog)
            if abs(d0[0]) + abs(d0[1]) >= abs(d1[0]) + abs(d1[1]):
                V[(k + 1) % m_] = p1
                V[(k + 2) % m_] = (p3[0] - jog[0], p3[1] - jog[1])
            else:
                V[k] = p2
                V[k - 1] = (p0[0] + jog[0], p0[1] + jog[1])
            break
        else:
            break
        V = clean(V)
    return V if len(V) >= 4 else []


def _lattice_cells(V):
    """The lattice squares inside an outline of lattice corners: its biggest piece, holes filled."""
    if len(V) < 4:
        return set()
    cells = {(i, j) for i in range(min(p[0] for p in V), max(p[0] for p in V)) for j in range(min(p[1] for p in V), max(p[1] for p in V))
             if _inside(V, (i + 0.5, j + 0.5))}
    best, seen = set(), set()
    for t in sorted(cells):
        if t in seen:
            continue
        comp, stack = set(), [t]
        while stack:
            u = stack.pop()
            if u in seen or u not in cells:
                continue
            seen.add(u)
            comp.add(u)
            stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
        if len(comp) > len(best):
            best = comp
    if not best:
        return set()
    i0, i1 = min(t[0] for t in best) - 1, max(t[0] for t in best) + 1
    j0, j1 = min(t[1] for t in best) - 1, max(t[1] for t in best) + 1
    out_, stack = set(), [(i0, j0)]
    while stack:
        u = stack.pop()
        if u in out_ or u in best or not (i0 <= u[0] <= i1 and j0 <= u[1] <= j1):
            continue
        out_.add(u)
        stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
    return {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1) if (i, j) not in out_}


def _drawn_outline(plan, drawn, db, step):
    """The wall's outline from the town as drawn, ([(x, y)], its square's turn), or None where the drawing gives none
    (a blob of many corners): outline()'s own way then."""
    forts = [f for f in _forts(plan)
             if any(_inside(drawn, q) or _ring_dist(drawn, q[0], q[1]) <= FORT_NEAR for q in f['ring'])
             or any(_ring_dist(f['ring'], x, y) <= FORT_NEAR for x, y in drawn)]
    th = _fort_angle(forts[0]) if forts else _drawn_frame(drawn)
    c, s = math.cos(th), math.sin(th)
    P = [(x * c + y * s, -x * s + y * c) for x, y in drawn]
    if forts:
        fx, fy = forts[0]['ring'][0]
        ou, ov = fx * c + fy * s, -fx * s + fy * c
    else:
        # (the lattice set on the longest side each way, so those stand where they were drawn)
        n = len(P)
        us = sorted(((abs(P[(k + 1) % n][1] - P[k][1]), (P[k][0] + P[(k + 1) % n][0]) / 2.0) for k in range(n)), reverse=True)
        vs = sorted(((abs(P[(k + 1) % n][0] - P[k][0]), (P[k][1] + P[(k + 1) % n][1]) / 2.0) for k in range(n)), reverse=True)
        ou, ov = us[0][1], vs[0][1]
    V = _straighten(P, step, ou, ov)
    cells = _lattice_cells(V)
    if not cells:
        return None
    if forts:
        out = _meld(plan, db, cells, forts, ou, ov, step, step, 1, 1, c, s, hug=False)
    else:
        out = []
        for i, j in _trace(cells):
            u, v = ou + i * step, ov + j * step
            out.append((u * c - v * s, u * s + v * c))
    if len(out) < 4 or len(out) > DRAWN_CORNERS:
        return None
    return out, th


# ---------------------------------------------------------------------------------------- a castle in the town's wall
# A castle beside a town, or inside its edge, stands in the town's wall: the town's wall runs to the castle's and stops,
# the castle's own wall closing the ring there. Two rings a lane apart, the town's wall run through the castle's, were
# what a castle drawn in a town's corner got (the user, 2026-11-11: "arent the walls supposed to meld"). The town is told
# of the castle (plan['forts'], townbuild._forts_for): planned or standing, the same.
FORT_NEAR = 2600               # (a castle whose wall comes this near the town's buildings stands in the town's wall)
FORT_GAP = 1700                # (town ground this near a castle's wall is carried on to it: no lane between two walls)
FORT_SLIVER = 1300             # (a strip of the town this thin between a castle's wall and the open goes: the castle's
                               # wall is the town's there)
FORT_TOL = 100                 # (a wall piece this near a castle's wall line stands in it)
FORT_TOWER = 420               # (a castle's own tower this near a join covers it)
FORT_BLOCK = 500               # (no tower set at a join this near the castle's keep or gate)
FORT_TO_CORNER = 4             # (a join this many lengths or fewer short of the castle's corner is carried on to the corner)
FORT_STUB = 2                  # (a town strip holding this few lengths of a castle's side, at its corner, is given up)
FORT_NOFILL = 1.6               # (the town's lengths within this many wall lengths of a castle's wall stand on the ground
                               # as it is: the castle's standing wall keeps the town's fill off its ground (wall_guard), and
                               # a wall floated at the ring's level there hung 100 to 300 over it, its ground 142 and 290
                               # where the fill wanted 440, the release check of 2.6.18, 2026-11-11)
FORT_NOTCH = 8                 # (carried on to the corner only when the ground taken in is this many squares of a length
                               # or fewer, a notch: a castle lapping a town's corner took in a block of 28, half a
                               # cell of ground outside the town as drawn, lab 2026-11-11)


def _forts(plan):
    """The castles the town's wall is to meet: [{'ring': [(x, y)], 'towers': [(x, y, r)], 'blocks': [(x, y, r)]}]."""
    out = []
    for f in plan.get('forts') or ():
        ring = f.get('ring') if isinstance(f, dict) else f
        ring = [(float(q[0]), float(q[1])) for q in ring or ()]
        if len(ring) < 4:
            continue
        g = f if isinstance(f, dict) else {}
        out.append({'ring': ring, 'towers': [tuple(float(v) for v in t[:3]) for t in g.get('towers') or ()],
                    'blocks': [tuple(float(v) for v in t[:3]) for t in g.get('blocks') or ()]})
    return out


def _seg_dist(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / l2))
    return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def _ring_dist(ring, x, y):
    return min(_seg_dist(x, y, ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))


def _on_fort(forts, x, y, tol=FORT_TOL):
    """The fort on whose wall line (x, y) stands, or None."""
    for f in forts:
        if _ring_dist(f['ring'], x, y) <= tol:
            return f
    return None


def _forts_near(plan):
    """The plan's castles near enough to its buildings to stand in its wall."""
    forts = _forts(plan)
    if not forts:
        return []
    pts = _town_pts(plan)
    return [f for f in forts if any(_ring_dist(f['ring'], x, y) <= FORT_NEAR or _inside(f['ring'], (x, y)) for x, y in pts)]


def _fort_angle(f):
    """The way a castle's wall runs, as a town frame's turn (0 to a quarter turn)."""
    r = f['ring']
    a, b = max(((r[i], r[(i + 1) % len(r)]) for i in range(len(r))), key=lambda e: math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]))
    return math.atan2(b[1] - a[1], b[0] - a[0]) % (math.pi / 2)


def _meld(plan, db, on, forts, x0, y0, pu, pv, mu, mv, c, s, hug=True):
    """The town's outline with its castles in it, [(x, y)]: on a lattice of wall lengths set on the castle's corner, the
    town's squares less the castle's ground; a lane between the two filled, the town carried on to the castle's wall; a
    thin strip of town between the castle and the open left out, the castle's wall the town's there. The outline runs
    along the castle's wall where they meet: lay() leaves those lengths to the castle."""
    town = {(i * mu + a, j * mv + b) for i, j in on for a in range(mu) for b in range(mv)}
    if not town:
        return []
    fr = lambda x, y: (x * c + y * s, -x * s + y * c)
    rings = [[fr(x, y) for x, y in f['ring']] for f in forts]
    mid = lambda t: (x0 + (t[0] + 0.5) * pu, y0 + (t[1] + 0.5) * pv)
    gu, gv = int(math.ceil(FORT_GAP / pu)), int(math.ceil(FORT_GAP / pv))
    i0 = min(min(t[0] for t in town), min(int((u - x0) // pu) for r in rings for u, _v in r)) - gu - 2
    i1 = max(max(t[0] for t in town), max(int((u - x0) // pu) for r in rings for u, _v in r)) + gu + 2
    j0 = min(min(t[1] for t in town), min(int((v - y0) // pv) for r in rings for _u, v in r)) - gv - 2
    j1 = max(max(t[1] for t in town), max(int((v - y0) // pv) for r in rings for _u, v in r)) + gv + 2
    fort = {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1) if any(_inside(r, mid((i, j))) for r in rings)}
    # (the buildings' own squares: never cut; a first plan's building on the castle's ground is no building)
    plots = set()
    # (hug False, the town as drawn: its ground is what was drawn, the buildings planned into the wall after)
    for q in plan['plots'] if hug else ():
        r = [fr(x, y) for x, y in (q.get('rect') or [(q['x'], q['y'])])]
        mx, my = sum(p_[0] for p_ in r) / len(r), sum(p_[1] for p_ in r) / len(r)
        if any(_inside(g, (mx, my)) for g in rings):
            continue
        for i in range(int((min(p_[0] for p_ in r) - x0) // pu), int((max(p_[0] for p_ in r) - x0) // pu) + 1):
            for j in range(int((min(p_[1] for p_ in r) - y0) // pv), int((max(p_[1] for p_ in r) - y0) // pv) + 1):
                plots.add((i, j))
    plots -= fort
    town -= fort
    town |= plots
    memo = {}

    def dry(t):
        if t not in memo:
            u, v = mid(t)
            z = mapdata.terrain_z(db, u * c - v * s, u * s + v * c) if db is not None else 0.0
            memo[t] = db is None or (z is not None and z >= DRY)
        return memo[t]
    su, sv = int(FORT_SLIVER // pu), int(FORT_SLIVER // pv)
    for _ in range(3):
        add, cut = set(), set()
        for i, j in fort:
            for di, dj, g, sl in ((1, 0, gu, su), (-1, 0, gu, su), (0, 1, gv, sv), (0, -1, gv, sv)):
                t = (i + di, j + dj)
                if t in fort:
                    continue                 # (outward from the castle's wall only)
                run, k = [], 1
                if t in town:
                    while t in town and k <= sl + 1:
                        run.append(t)
                        k += 1
                        t = (i + di * k, j + dj * k)
                    if t not in town and t not in fort and len(run) <= sl and not any(q in plots for q in run):
                        cut.update(run)
                else:
                    while t not in town and t not in fort and k <= g:
                        run.append(t)
                        k += 1
                        t = (i + di * k, j + dj * k)
                    # (wet or dry: no wall stands on the lane itself, the castle's wall closes it; a lane left open
                    # because its ground lay low put the town's wall end in the castle's gate)
                    if t in town and run:
                        add.update(run)
        add -= cut
        if not add and not cut:
            break
        town |= add
        town -= cut
    # (the town's wall leaves the castle at the castle's corners, where its own towers stand: a join a few lengths short
    # of a corner is carried on to it, the town's ground beside the castle run on as deep as it lies; a strip of town
    # that holds only a length or two of the castle's side at a corner is given up, the join at the corner the other
    # way. A join left a length from the corner stood two towers side by side, and one by the gate stood in the way in)
    def out_run(f, d):
        k, run = 1, []
        while (f[0] + d[0] * k, f[1] + d[1] * k) in town and k < 64:
            run.append((f[0] + d[0] * k, f[1] + d[1] * k))
            k += 1
        return run
    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        edge = sorted((f for f in fort if (f[0] + d[0], f[1] + d[1]) not in fort), key=lambda f: (f[0], f[1]) if d[0] else (f[1], f[0]))
        sides, cur = [], []
        for f in edge:
            # (one side: the cells in one line, one after another)
            if cur and ((d[0] and f[0] == cur[-1][0] and f[1] == cur[-1][1] + 1) or (d[1] and f[1] == cur[-1][1] and f[0] == cur[-1][0] + 1)):
                cur.append(f)
            else:
                if cur:
                    sides.append(cur)
                cur = [f]
        if cur:
            sides.append(cur)
        for side in sides:
            for run in (side, side[::-1]):
                cov = [(f[0] + d[0], f[1] + d[1]) in town for f in run]
                if not any(cov) or all(cov):
                    continue
                u = cov.index(True)
                if 0 < u <= FORT_TO_CORNER:
                    depth = len(out_run(run[u], d))
                    fill = [(f[0] + d[0] * k, f[1] + d[1] * k) for f in run[:u] for k in range(1, depth + 1)]
                    fill = [t for t in fill if t not in fort]
                    rim = [(f[0] + d[0] * k, f[1] + d[1] * k) for f in run[:1] for k in range(1, depth + 1)]
                    if fill and len([t for t in fill if t not in town]) <= FORT_NOTCH and sum(dry(t) for t in rim) >= 0.7 * len(rim):
                        town.update(fill)
                elif u == 0:
                    c_ = cov.index(False)
                    if c_ <= FORT_STUB and not any(cov[c_:]):
                        strip = [t for f in run[:c_] for t in out_run(f, d)]
                        if strip and not any(t in plots for t in strip):
                            town.difference_update(strip)
    # (a pocket of open ground the town and the castle close on three sides: the town's)
    for _ in range(2):
        more = set()
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                t = (i, j)
                if t in town or t in fort:
                    continue
                nb = [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
                if sum(q in town or q in fort for q in nb) >= 3 and any(q in town for q in nb):
                    more.add(t)
        if not more:
            break
        town |= more
    # (a square joined by one side alone, no building on it: a jog of its own)
    for _ in range(2):
        lone = {t for t in town if t not in plots and
                sum((t[0] + dx, t[1] + dy) in town for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) <= 1}
        if not lone:
            break
        town -= lone
    # (two squares touching by a corner alone: no wall turns there)
    for _ in range(4):
        fixed = False
        for i, j in sorted(town):
            for dj in (1, -1):
                a, b, o1, o2 = (i, j), (i + 1, j + dj), (i + 1, j), (i, j + dj)
                if b in town and o1 not in town and o2 not in town:
                    free = [o for o in (o1, o2) if o not in fort]
                    if free:
                        town.add(free[0])
                    else:
                        town.discard(b if b not in plots else a)
                    fixed = True
        if not fixed:
            break
    # (the piece with the most buildings on it)
    best, seen = set(), set()
    for t in sorted(town):
        if t in seen:
            continue
        comp, stack = set(), [t]
        while stack:
            u = stack.pop()
            if u in seen or u not in town:
                continue
            seen.add(u)
            comp.add(u)
            stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
        if (len(comp & plots), len(comp)) > (len(best & plots), len(best)):
            best = comp
    if not best:
        return []
    # (what the open can't reach is inside: a castle in the middle of its town is walled in with it)
    box = {(i, j) for i in range(i0 - 1, i1 + 2) for j in range(j0 - 1, j1 + 2)}
    out_, stack = set(), [(i0 - 1, j0 - 1)]
    while stack:
        u = stack.pop()
        if u in out_ or u not in box or u in best:
            continue
        out_.add(u)
        stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
    full = {t for t in box if t not in out_}
    out = []
    for i, j in _trace(full):
        u, v = x0 + i * pu, y0 + j * pv
        out.append((u * c - v * s, u * s + v * c))
    return out


def _side_share(forts, a, b):
    """The share of the side a-b that runs along a castle's wall."""
    n = 0
    for k in range(1, 10):
        t = k / 10.0
        if _on_fort(forts, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t):
            n += 1
    return n / 9.0


def _off_forts(forts, poly, streets, roads):
    """streets and roads (as _street_crossings gives them) less the ways that would cross a castle's wall: the way from
    town to castle is the castle's own gate."""
    n = len(poly)
    out = defaultdict(list)
    for k, hs in streets.items():
        a, b = poly[k], poly[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        keep = [h for h in hs if not _on_fort(forts, a[0] + d[0] * h, a[1] + d[1] * h, FORT_TOL + 300)]
        if keep:
            out[k] = keep
    return out, [r for r in roads if not _on_fort(forts, r[1][0], r[1][1], FORT_TOL + 300)]


LINE_KINDS = ('corner', 'tower')          # (pieces that can stand in a wall's line besides its plain lengths)


def _in_line(kit, p, d):
    """Whether a wall piece stands in the line of a run going the way d: a plain length, or a corner unit's or the run's
    tower piece turned along it."""
    if p['id'] == kit['straight']:
        return True
    return p.get('kind') in LINE_KINDS and abs(math.sin(_rz_for(kit, d) - p['pose'].rz)) <= 0.05


def _meet_forts(db, fam, kit, poly, pieces, forts):
    """The wall's pieces where it meets a castle's: (pieces, joins). The lengths on the castle's line are left to the
    castle; where the town's wall runs up to the castle's and stops, a length carried on into the castle's wall, so no
    gap stands between the two, and a guard tower over the join where the kit has one and the castle has none there
    (the sections of a wall meet at towers)."""
    n = len(poly)
    L = kit['L']
    on = [_on_fort(forts, v[0], v[1]) for v in poly]
    share = [_side_share(forts, poly[k], poly[(k + 1) % n]) for k in range(n)]
    drop_unit, joins = set(), []
    for k in range(n):
        if on[k] is None:
            continue
        s_in, s_out = share[k - 1] > 0.5, share[k] > 0.5      # (the side into the corner, the side out of it)
        if not s_in and not s_out:
            continue
        drop_unit.add(k)
        if s_in != s_out:
            a = poly[k - 1] if not s_in else poly[(k + 1) % n]
            joins.append((poly[k], _unit(poly[k][0] - a[0], poly[k][1] - a[1]), on[k], {'corner': k}))
    # (and where the town's wall runs straight on into a castle's corner, no turn of its own there: the same join)
    for f in forts:
        for c_ in f['ring']:
            for k in range(n):
                a, b = poly[k], poly[(k + 1) % n]
                if _seg_dist(c_[0], c_[1], a, b) > 24 or min(math.hypot(c_[0] - a[0], c_[1] - a[1]), math.hypot(c_[0] - b[0], c_[1] - b[1])) <= FORT_TOL:
                    continue
                e = _unit(b[0] - a[0], b[1] - a[1])
                free = [sg for sg in (1, -1) if not _on_fort(forts, c_[0] + sg * e[0] * L, c_[1] + sg * e[1] * L)]
                if len(free) == 1:
                    joins.append((c_, (-free[0] * e[0], -free[0] * e[1]), f, {'run': k}))
    keep = []
    for p in pieces:
        q = p['pose']
        if p.get('corner') in drop_unit or _on_fort(forts, q.x, q.y) or any(_inside(f['ring'], (q.x, q.y)) for f in forts):
            continue
        keep.append(p)
    B = BIG.get(fam)
    n_j = 0
    for v, d, f, tag in joins:
        # (the last whole length of the free side, and half a length on from it: into the castle's wall, to its middle)
        # (a plain length, or a piece of the wall's line that is none: the tower piece of the town's own corner a step
        # along, a wall tower in the run. Only plain lengths were looked for, and a wall whose corner stood two lengths
        # from the castle's was left open beside it: the user's 2618 at Blackrose, 2026-11-11)
        # (as far back as the town's own corner unit left out at the castle's corner reached, and a length and a half:
        # a kit of short lengths with a long rounded corner, the Hlaalu wall's three of 256, left its nearest length
        # 3.5 lengths off, past the 2.6 that suit the Legion's wall, and the ring stood open 770 wide either side of
        # the castle; practice 2, 2026-11-11)
        gone_ = [math.hypot(p['pose'].x - v[0], p['pose'].y - v[1]) for p in pieces if 'corner' in tag and p.get('corner') == tag['corner']]
        reach = max(2.6 * L, (max(gone_) + 1.6 * L) if gone_ else 0.0)
        side = [p for p in keep if _in_line(kit, p, d) and abs(-(p['pose'].x - v[0]) * d[1] + (p['pose'].y - v[1]) * d[0]) <= 24
                and -max(4 * L, reach + L) <= (p['pose'].x - v[0]) * d[0] + (p['pose'].y - v[1]) * d[1] < 0]
        side.sort(key=lambda p: math.hypot(p['pose'].x - v[0], p['pose'].y - v[1]))
        if not side or math.hypot(side[0]['pose'].x - v[0], side[0]['pose'].y - v[1]) > reach:
            continue                         # (no wall comes up to the castle here: a side open to the water)
        mine = {id(p) for p in side}
        far = side[-1]['pose']
        if len(side) < 3 and not any(id(p) not in mine and math.hypot(p['pose'].x - far.x, p['pose'].y - far.y) <= 1.3 * L for p in keep):
            # (a length or two left standing alone by the castle, nothing beyond them, the rest of their side open to
            # the water: they go too. A short leg that runs on to a corner of the wall is no such thing)
            gone = {id(p) for p in side}
            keep = [p for p in keep if id(p) not in gone]
            continue
        rz = side[0]['pose'].rz
        near = math.hypot(side[0]['pose'].x - v[0], side[0]['pose'].y - v[1])
        n_j += 1
        m = 0
        while near - (m + 1) * L >= L / 2.0 - 8 and m < max(4, int(reach / L) + 1):
            # (whole lengths first, where the corner's own pieces left more than one out)
            m += 1
            keep.append(dict({'id': kit['straight'], 'pose': Pose(v[0] - d[0] * (near - m * L), v[1] - d[1] * (near - m * L), 0.0, rz, kit['straight']),
                              'kind': 'wall', 'join': True}, **tag))
        if near - m * L > L / 2.0 + 8:
            keep.append(dict({'id': kit['straight'], 'pose': Pose(v[0] - d[0] * L / 2.0, v[1] - d[1] * L / 2.0, 0.0, rz, kit['straight']),
                              'kind': 'wall', 'join': True}, **tag))
        # (nor a length or so from the castle's own corner: two towers side by side)
        crn = min(math.hypot(q[0] - v[0], q[1] - v[1]) for q in f['ring'])
        # (nor where the town's own corner tower stands two lengths off, its tower piece between: three in a row)
        crowd = side[0]['id'] != kit['straight'] and any(o.get('kind') == 'bigtower' and math.hypot(o['pose'].x - v[0], o['pose'].y - v[1]) <= 2.2 * L
                                                         for o in keep)
        if B and not crowd and not FORT_TOL < crn < 1.6 * L and not any(math.hypot(t[0] - v[0], t[1] - v[1]) <= FORT_TOWER for t in f['towers']) and \
                not any(math.hypot(t[0] - v[0], t[1] - v[1]) <= FORT_BLOCK + (t[2] if len(t) > 2 else 0.0) for t in f['blocks']):
            keep.append({'id': B['tower'], 'pose': Pose(v[0], v[1], 0.0, rz, B['tower']), 'kind': 'bigtower', 'dz': B['tower_dz'], 'join': True})
    # (and a tower or a length left standing by itself beside the castle, the wall either side of it gone to the castle
    # or to the water: a lone guard tower stood a length off the keep's back, a gap between them, lab 2026-11-11)
    lone = [p for p in keep if not p.get('join') and any(_ring_dist(f['ring'], p['pose'].x, p['pose'].y) <= 2.2 * L for f in forts)
            and not any(q is not p and math.hypot(q['pose'].x - p['pose'].x, q['pose'].y - p['pose'].y) <= 1.3 * L for q in keep)]
    if lone:
        gone = {id(p) for p in lone}
        keep = [p for p in keep if id(p) not in gone]
    # (and no gap left anywhere: a length that ends short of a castle's wall on its own line, however it came to stand
    # there (a wall run on to the water past the castle's corner had its first length on the castle's line, left out,
    # and a gap of 100 beside the corner, lab 2026-11-11), is carried on into the castle's wall by half a length)
    for p in list(keep):
        if p.get('join') or not (p['id'] == kit['straight'] or p.get('kind') in LINE_KINDS):
            continue
        q0 = p['pose']
        for f in forts:
            r = f['ring']
            best = None
            for i in range(len(r)):
                a, b = r[i], r[(i + 1) % len(r)]
                dx, dy = b[0] - a[0], b[1] - a[1]
                t = max(0.0, min(1.0, ((q0.x - a[0]) * dx + (q0.y - a[1]) * dy) / ((dx * dx + dy * dy) or 1.0)))
                qx, qy = a[0] + t * dx, a[1] + t * dy
                dq = math.hypot(qx - q0.x, qy - q0.y)
                if best is None or dq < best[0]:
                    best = (dq, qx, qy)
            dq, qx, qy = best
            if not L / 2.0 + 8 < dq <= L + 24:
                continue
            d = _unit(qx - q0.x, qy - q0.y)
            if abs(math.sin(_rz_for(kit, d) - q0.rz)) > 0.05:
                continue                     # (it runs along the castle's wall, not at it)
            tx, ty = qx - d[0] * L / 2.0, qy - d[1] * L / 2.0
            if any(math.hypot(o['pose'].x - tx, o['pose'].y - ty) <= 64 for o in keep):
                continue
            keep.append(dict({k: p[k] for k in ('run', 'corner') if k in p}, id=kit['straight'], pose=Pose(tx, ty, 0.0, q0.rz, kit['straight']), kind='wall', join=True))
    # (the lengths by the castle stand on the ground as it is, no fill under them: grounded, _allow)
    for p in keep:
        if any(_ring_dist(f['ring'], p['pose'].x, p['pose'].y) <= FORT_NOFILL * L for f in forts):
            p['nofill'] = True
    return keep, n_j


def _on_land(db, on, x0, y0, cell, c, s, plots_on=(), blocked=()):
    """(cell: the squares' size each way.) The wall's squares kept to dry, walkable ground: a square over the water, or across a cliff's edge, is left out,
    so the wall follows the land inside its shore and above its cliffs instead of running a straight box out over the sea
    (the user's island town, test3: sides off the land, hanging over the drop). Then the piece with the most of the town
    in it, its holes filled (a wall closes round them)."""
    def ok(i, j):
        steep_ok = (i, j) in plots_on         # (a plot's square stays in, steep or not: the wall never cuts a building)
        if (i, j) in blocked and not steep_ok:
            return False                      # (one of the game's own buildings stands there)
        zs = []
        for fu in (0.0, 0.5, 1.0):
            for fv in (0.0, 0.5, 1.0):
                u, v = x0 + (i + fu) * cell[0], y0 + (j + fv) * cell[1]
                z = mapdata.terrain_z(db, u * c - v * s, u * s + v * c)
                if z is None or z < DRY:
                    return False
                zs.append(z)
        return steep_ok or max(zs) - min(zs) <= STEEP
    keep = {t for t in on if ok(*t)}
    if not keep:
        return on
    # (notches filled with any dry, walkable square: traced square by square the wall came out jogging in and out a
    # square at a time, a corner and a tower at every jog, 12 corners and 14 towers round a small town, the user's
    # "fever dream"; the game's walls run long straight sides, turning only where the land makes them)
    memo_ok = {}
    def ok2(t):
        if t not in memo_ok:
            memo_ok[t] = ok(*t)
        return memo_ok[t]
    for _ in range(3):
        rows, cols = defaultdict(list), defaultdict(list)
        for i, j in keep:
            rows[j].append(i)
            cols[i].append(j)
        add = {(i, j) for j, l in rows.items() for i in range(min(l), max(l) + 1)} |             {(i, j) for i, l in cols.items() for j in range(min(l), max(l) + 1)}
        add = {t for t in add - keep if ok2(t)}
        if not add:
            break
        keep |= add
    # (a square standing out on its own, joined by one side only: dropped, a jog of its own)
    for _ in range(2):
        lone = {t for t in keep if sum((t[0] + dx, t[1] + dy) in keep for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) <= 1
                and t not in plots_on}
        if not lone:
            break
        keep -= lone
    # (the largest 4-connected piece)
    best, seen = set(), set()
    for t in keep:
        if t in seen:
            continue
        comp, stack = set(), [t]
        while stack:
            u = stack.pop()
            if u in seen or u not in keep:
                continue
            seen.add(u)
            comp.add(u)
            stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
        if len(comp) > len(best):
            best = comp
    # (holes filled: squares the outside can't reach)
    xs = [t[0] for t in best]
    ys = [t[1] for t in best]
    box = {(i, j) for i in range(min(xs) - 1, max(xs) + 2) for j in range(min(ys) - 1, max(ys) + 2)}
    out_, stack = set(), [(min(xs) - 1, min(ys) - 1)]
    while stack:
        u = stack.pop()
        if u in out_ or u not in box or u in best:
            continue
        out_.add(u)
        stack.extend(((u[0] + 1, u[1]), (u[0] - 1, u[1]), (u[0], u[1] + 1), (u[0], u[1] - 1)))
    return {t for t in box if t not in out_}


def _trace(on):
    """The boundary of a 4-connected set of grid squares as its corners, counter-clockwise."""
    edges = {}
    for i, j in on:
        if (i, j - 1) not in on:
            edges[(i, j)] = (i + 1, j)
        if (i + 1, j) not in on:
            edges[(i + 1, j)] = (i + 1, j + 1)
        if (i, j + 1) not in on:
            edges[(i + 1, j + 1)] = (i, j + 1)
        if (i - 1, j) not in on:
            edges[(i, j + 1)] = (i, j)
    if not edges:
        return []
    start = min(edges)
    pts, p = [start], edges[start]
    while p != start and len(pts) < 10000:
        pts.append(p)
        p = edges[p]
    # (the corners only)
    out = []
    n = len(pts)
    for k in range(n):
        a, b, c_ = pts[k - 1], pts[k], pts[(k + 1) % n]
        if (b[0] - a[0], b[1] - a[1]) != (c_[0] - b[0], c_[1] - b[1]):
            out.append(b)
    return out


def _rz_for(kit, d):
    """The straight's turn whose run points along world direction d (to_world turns clockwise)."""
    run = (1.0, 0.0) if kit['axis'] == 0 else (0.0, 1.0)
    return math.atan2(run[1], run[0]) - math.atan2(d[1], d[0])


def lay(db, plan, family=None, cell=None):
    """The wall round a town plan: {'family', 'pieces': [{'id', 'p': [x, y, z, 0, 0, rz], 'kind'}], 'outline',
    'gates', 'faults': [...]}. Pieces chain by the game's joins; a side's last straight may overlap the one before it
    when the game sets that straight on itself at a shorter step, else the side is lengthened to whole steps."""
    K = kits(db)
    fam = family if family in K else pick_family(db, plan)
    if not fam or family == 'palisade':
        # (a village of a culture that rings itself with a palisade: the Nords')
        P = palisade_for(db, plan, family == 'palisade')
        if P:
            return lay_palisade(db, plan, P)
        return {'family': None, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No wall for this culture']}
    kit = K[fam]
    if kit.get('round'):
        return lay_round(db, plan, fam, kit)
    _KEEP_SEA[0] = False
    L = kit['L']
    # (an outline whose squares are whole steps, so a side's straights fill it)
    G = cell or L * max(1, round(1024.0 / L))
    # (a town planned inside its wall keeps that wall: traced again round its new plots, at their own slant, the box came
    # out a row wider all round, townbuild.planned)
    plan['_fam'] = fam
    poly, th = ([tuple(p) for p in plan['wall_outline']], 0.0) if plan.get('wall_outline') else outline(plan, G, db, L)
    if len(poly) < 3:
        return {'family': fam, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No plots to wall']}
    # (at any angle: wallangle.py)
    ang = (plan.get('wall_angled') if plan.get('wall_outline') else plan.get('_angled')) or None
    if ang is None and plan.get('wall_outline') and fam in BIG and not _rectilinear(poly):
        ang = angled_info(poly, _forts(plan))
    if fam not in BIG:
        ang = None
    if len(poly) < 4 and not ang:
        return {'family': fam, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No plots to wall']}
    # (counter-clockwise: turns at outer corners are to the left, +90 in the game's clockwise rz... measured per kit)
    n = len(poly)
    turns = []
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        cr = (b[0] - a[0]) * (c_[1] - b[1]) - (b[1] - a[1]) * (c_[0] - b[0])
        turns.append(1 if cr > 0 else -1)          # (1: a left turn seen from above)
    # the kit's corner for a left turn: its rz turn is clockwise, so a left turn is a negative rz turn
    need = {1: -1, -1: 1}
    # (the way round the game walks its own walls: its commonest corner is the convex one, outer corners being most of a
    # town wall's, so the town lies on that corner's inner side and the straights' buttresses face out. Walked the other
    # way the wall stood inside out, buttresses to the town, the user's first town, 2026-10-31)
    dom = max(kit['corners'], key=lambda h: kit['corners'][h]['n'])
    maj = 1 if sum(turns) >= 0 else -1
    fort_k, bare_v = set(), set()
    if ang:
        # (walked so its outer corners turn as the kit's commonest corner does: the straights' buttresses face out)
        import wallangle
        if need[maj] != dom:
            poly = poly[::-1]
        turns = []
        for k in range(n):
            a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
            turns.append(1 if (b[0] - a[0]) * (c_[1] - b[1]) - (b[1] - a[1]) * (c_[0] - b[0]) > 0 else -1)
        fort_k = wallangle.fort_sides(poly, ang)
        # (no tower of the town's on a castle's corner between two of the castle's own sides; where the town's wall
        # ends at a castle's corner, a tower over the join unless the castle stands one of its own there)
        ftw_ = [t for f in _forts(plan) for t in f['towers']]
        bare_v = set()
        for k in range(n):
            if (k - 1) % n in fort_k and k in fort_k:
                bare_v.add((int(round(poly[k][0])), int(round(poly[k][1]))))
            elif ((k - 1) % n in fort_k) != (k in fort_k) and any(math.hypot(t[0] - poly[k][0], t[1] - poly[k][1]) <= FORT_TOWER for t in ftw_):
                bare_v.add((int(round(poly[k][0])), int(round(poly[k][1]))))
    if not ang and need[maj] != dom and all(need[-t] in kit['corners'] for t in turns):
        poly = poly[::-1]
        turns = [-t for t in turns[::-1]]
    if not ang and any(need[t] not in kit['corners'] for t in turns):
        # (walk the other way round: a kit with only one corner hand fits a convex outline walked either way)
        poly = poly[::-1]
        turns = [-t for t in turns[::-1]]
        if any(need[t] not in kit['corners'] for t in turns):
            return {'family': fam, 'pieces': [], 'outline': poly, 'gates': 0, 'faults': ['This wall turns only one way']}
    pieces, faults = [], []
    forts_ = _forts(plan)
    inside_ = sum(1 for ob in plan.get('obstacles') or () if _inside(poly, (sum(p[0] for p in ob) / len(ob), sum(p[1] for p in ob) / len(ob)))
                  and not any(_inside(g['ring'], (sum(p[0] for p in ob) / len(ob), sum(p[1] for p in ob) / len(ob))) or
                              _ring_dist(g['ring'], sum(p[0] for p in ob) / len(ob), sum(p[1] for p in ob) / len(ob)) <= 400 for g in forts_))
    if inside_:
        faults.append("%d of the game's own buildings stand inside the wall" % inside_)
    # every corner: S0 (in), its chain, S1 (out)
    units = []
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        din = _unit(b[0] - a[0], b[1] - a[1])
        if ang:
            # (no corner piece: the last length of the side in and the first of the side out, each on its own line,
            # their ends inside the tower stood over the corner; none on a castle's own side)
            chain = []
            if (k - 1) % n not in fort_k:
                _m, off_ = wallangle.run_of(a, b, L)
                chain.append(Pose(b[0] - din[0] * off_, b[1] - din[1] * off_, 0.0, _rz_for(kit, din), kit['straight']))
            if k not in fort_k:
                dout = _unit(c_[0] - b[0], c_[1] - b[1])
                _m, off_ = wallangle.run_of(b, c_, L)
                chain.append(Pose(b[0] + dout[0] * off_, b[1] + dout[1] * off_, 0.0, _rz_for(kit, dout), kit['straight']))
            units.append(chain)
            continue
        co = kit['corners'][need[turns[k]]]
        rz = _rz_for(kit, din)
        # S0 stands co['p'] before the vertex on the incoming line
        S0 = Pose(b[0] - din[0] * co['p'], b[1] - din[1] * co['p'], 0.0, rz, kit['straight'])
        chain = [S0]
        p = S0
        for t, e in co['chain']:
            p = p.then(e, t)
            chain.append(p)
        units.append(chain)
    forts = _forts(plan)
    streets, roads = _street_crossings(plan, poly)
    if forts:
        streets, roads = _off_forts(forts, poly, streets, roads)
    # (a crossing on a side too short to hold a gate between its corners is no way in: the island town's one crossing
    # fell on a two-length jog of its outline and the wall closed with "0 ways in", the user 2026-11-06)
    gate_ = _best(kit, 'gate')
    span = gate_[1]['span'] if gate_ else 2 * kit['L']
    ok_sides = set()
    for k in range(n):
        if k in fort_k:
            continue
        out_, in_ = units[k][-1], units[(k + 1) % n][0]
        b, c_ = poly[k], poly[(k + 1) % n]
        d = _unit(c_[0] - b[0], c_[1] - b[1])
        if (in_.x - out_.x) * d[0] + (in_.y - out_.y) * d[1] >= span + 1.5 * kit['L']:
            ok_sides.add(k)
    if forts:
        # (nor on a side the castle's wall stands on: the way between them is the castle's gate)
        ok_sides = {k for k in ok_sides if _side_share(forts, poly[k], poly[(k + 1) % n]) <= 0.34} or ok_sides
    # (open to the sea: no gate on a side that faces the water, its wall is left out below)
    sea = bool(plan.get('open_sea')) and db is not None
    if sea:
        dry = ok_sides - _sea_sides(db, poly, kit['L'])
        ok_sides = dry or ok_sides
    mine = user_gates(plan, poly, roads, kit['L'], ok_sides or None)
    if mine:
        streets, roads = mine
    if any(k not in ok_sides for k in streets):
        kept = [(poly[k][0] + _unit(poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1])[0] * h,
                 poly[k][1] + _unit(poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1])[1] * h)
                for k, hs in streets.items() if k in ok_sides for h in hs]
        streets = defaultdict(list, {k: v for k, v in streets.items() if k in ok_sides})
        roads = [r for r in roads if any(math.hypot(r[1][0] - q[0], r[1][1] - q[1]) < 50 for q in kept)]
    # (the user's gates stand where they put them: not moved downhill, none added)
    if db is not None and not mine:
        streets, roads = _downhill_gates(db, poly, streets, roads)
        if forts:
            streets, roads = _off_forts(forts, poly, streets, roads)
    if not any(streets.values()) and not mine:
        # (no street reaches the wall line: on a big drawn outline the main street ended far inside it and the town had
        # "0 ways in", the user's island town of 2026-11-06. A gate all the same: at the main street's end carried on to
        # the nearest side however far, else in the middle of a side; the side chosen as gates are kept, dry, no cliff,
        # low; the road paved from the street's end to it)
        streets, roads = _fallback_gate(db, plan, poly, roads, kit['L'], ok_sides)
        if forts:
            streets, roads = _off_forts(forts, poly, streets, roads)
    # (and a wall that still comes out with no gate, its street's crossing too near a corner for one to stand, gets the
    # same one gate: one walled plan in six had none, a sealed town, the cold start of 2.6.17 and of 2.6.16 alike)
    gates = 0
    for _attempt in (0, 1):
        sides_, gates = [], 0
        for k in range(n):
            if k in fort_k:
                continue
            out_ = units[k][-1]
            in_ = units[(k + 1) % n][0]
            b, c_ = poly[k], poly[(k + 1) % n]
            d = _unit(c_[0] - b[0], c_[1] - b[1])
            D = (in_.x - out_.x) * d[0] + (in_.y - out_.y) * d[1]
            lat = -(in_.x - out_.x) * d[1] + (in_.y - out_.y) * d[0]
            if abs(lat) > SNAP and not _attempt:
                faults.append('side %d: corners %.0f units off one line' % (k, lat))
            off = (out_.x - b[0]) * d[0] + (out_.y - b[1]) * d[1]
            side, g = _side(kit, out_, D, d, [c0 - off for c0 in streets.get(k) or []], faults, k)
            gates += g
            for q in side:
                q['run'] = k
            sides_.extend(side)
        if gates or mine or _attempt:
            break
        streets, roads = _fallback_gate(db, plan, poly, roads, kit['L'], ok_sides)
        if forts:
            streets, roads = _off_forts(forts, poly, streets, roads)
    pieces.extend(sides_)
    for k, chain in enumerate(units):
        # (a tower beside each corner where the game stands one, in the place of the straight there: the sections of the
        # wall meet at towers, the user, 2026-10-31; Imperial corner_01's wall_tower_01 a step along)
        C = next((q for q in chain if q.id != kit['straight']), None)
        # (outer corners only: a tower in an inner corner stood into the town, "too many towers within the borders of the
        # wall", the user's island town)
        outer = need[turns[k]] == dom
        for t, e in ((kit.get('corner_towers') or {}).get(C.id) or ()) if C and outer else ():
            T = C.then(e, t)
            for q in chain:
                if q.id == kit['straight'] and math.hypot(q.x - T.x, q.y - T.y) <= 24 and                         abs(((q.rz - T.rz + math.pi) % (2 * math.pi)) - math.pi) <= math.radians(3):
                    q.id = t
                    break
            else:
                continue
            break
        for q in chain:
            # (the corner at vertex k stands between side k - 1's run and side k's)
            pieces.append({'id': q.id, 'pose': q, 'kind': 'corner' if q.id != kit['straight'] else 'wall', 'corner': k})
    if ang:
        # (a round tower over every corner, an inner one too: it is what closes the joint. No keep: it is square)
        tw_ = _big_towers(db, fam, kit, poly, [(int(round(v[0])), int(round(v[1]))) not in bare_v for v in poly], pieces)
        for p_ in tw_:
            if p_.get('kind') == 'keep':
                p_.update(id=BIG[fam]['tower'], kind='bigtower', dz=BIG[fam]['tower_dz'])
                p_['pose'].id = BIG[fam]['tower']
        # (and none left out for a gate near it: with no tower the corner stands open, two wall ends in the air)
        for k_, v_ in enumerate(poly):
            if (int(round(v_[0])), int(round(v_[1]))) in bare_v or any(p_.get('kind') == 'bigtower' and math.hypot(p_['pose'].x - v_[0], p_['pose'].y - v_[1]) <= 64 for p_ in tw_):
                continue
            d_ = _unit(poly[(k_ + 1) % n][0] - v_[0], poly[(k_ + 1) % n][1] - v_[1])
            tw_.append({'id': BIG[fam]['tower'], 'pose': Pose(v_[0], v_[1], 0.0, _rz_for(kit, d_), BIG[fam]['tower']), 'kind': 'bigtower', 'dz': BIG[fam]['tower_dz']})
        pieces += tw_
    else:
        pieces += _big_towers(db, fam, kit, poly, [need[t] == dom for t in turns], pieces)
    pieces = _once(pieces)
    if sea:
        # (a coastal town: the wall on the land side only, the lengths that face the water left out, the user 2026-11-09)
        n_g = sum(1 for p in pieces if p.get('kind') in ('gate', 'end'))
        order = []
        for k in range(n):
            d = _unit(poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1])
            order += [p for p in pieces if p.get('corner') == k]
            order += sorted([p for p in pieces if p.get('run') == k], key=lambda p: p['pose'].x * d[0] + p['pose'].y * d[1])
        nrm = _out_normals(poly)
        tower = next((t for v in (kit.get('corner_towers') or {}).values() for t, _e in v), None)
        pieces = _open_to_sea(db, pieces, order, lambda p: [nrm[p['run']]] if 'run' in p else [nrm[p['corner'] - 1], nrm[p['corner']]],
                              kit['straight'], tower, [_unit(poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1]) for k in range(n)], nrm, kit['L'],
                              (lambda B: {'id': B['tower'], 'dz': B['tower_dz']} if B else None)(BIG.get(fam)))
        if n_g:
            gates = int(round(gates * sum(1 for p in pieces if p.get('kind') in ('gate', 'end')) / float(n_g)))
    joins = 0
    if forts and not ang:
        # (after the sea's openings: a side left open to the water beside a castle needs no join, the town open there)
        pieces, joins = _meet_forts(db, fam, kit, poly, pieces, forts)
    elif ang:
        joins = 2 if fort_k or bare_v else 0
        # (by a castle: the tower over the join is no double of the castle's own corner piece (drop_doubled), and the
        # lengths beside the castle stand on the ground as it is, the castle's level, no bank of fill under them: _allow)
        ends_ = [poly[k] for k in range(n) if ((k - 1) % n in fort_k) != (k in fort_k)]
        for p_ in pieces:
            q_ = p_['pose']
            if p_.get('kind') == 'bigtower' and any(math.hypot(q_.x - v_[0], q_.y - v_[1]) <= 64 for v_ in ends_):
                p_['join'] = True
            elif any(_ring_dist(f['ring'], q_.x, q_.y) <= FORT_NOFILL * L for f in forts):
                p_['nofill'] = True
    return {'family': fam, 'kit': kit, 'pieces': pieces, 'outline': poly, 'gates': gates, 'faults': faults, 'joins': joins,
            'angled': dict(ang, poly=[list(p) for p in poly]) if ang else None,
            'led': bool(plan.get('_led')), 'roads': _gate_roads(poly, roads, pieces, L) if gates else []}


def _gate_roads(poly, roads, pieces, L):
    """The streets carried out to the wall, met to the gates: a gate stands up to a length aside from where its street
    crossed the wall (whole steps), and the street ran into the wall beside it, the gate's way unpaved (both gates of a
    walled Imperial town, 512 off, lab w01). Each carried stretch ends at its gate's middle."""
    gates = [p['pose'] for p in pieces if p.get('kind') in ('gate', 'end')]
    if not gates:
        return roads
    cx, cy = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
    out = []
    for b, q, w in roads:
        g = min(gates, key=lambda G: math.hypot(G.x - q[0], G.y - q[1]))
        if math.hypot(g.x - q[0], g.y - q[1]) > 1.5 * L + 64:
            out.append((b, q, w))
            continue
        # (an opening's two end pieces: its middle between them)
        pair = [G for G in gates if math.hypot(G.x - g.x, G.y - g.y) <= 4 * L and G is not g]
        gx, gy = g.x, g.y
        if pair and not any(p['pose'] is g and p.get('kind') == 'gate' for p in pieces):
            o = min(pair, key=lambda G: math.hypot(G.x - g.x, G.y - g.y))
            gx, gy = (g.x + o.x) / 2, (g.y + o.y) / 2
        u = _unit(gx - cx, gy - cy)
        out.append((b, (gx, gy), w))
        if GATE_OUT:
            out.append(((gx, gy), (gx + u[0] * GATE_OUT, gy + u[1] * GATE_OUT), w))
    return out


GATE_OUT = 0                   # (a gate's street run on this far outside it: on a hill, run 384 or 900 straight down the slope
                               # it made a hilltop town's road the steeper by a sixth to a quarter, lab r20; none)


# ------------------------------------------------------------------------------------------------ palisades
# Nord villages ring themselves with palisades: sections of posts ~300 long, each turned a few degrees from the last
# (joins of 296-315 at 0-20 degrees), a gatehouse where the way in passes, every section set on its own ground (the game's
# Karthgad, Blood Paw Lodge, Criaglorc: lab r01). No straight repeats, so the wall kits never had them and a Nordic town
# asked for a wall got none.
PALISADE = {'Nordic': {'posts': ('t_nor_setpalisade_posts_02', 't_nor_setpalisade_posts_01', 't_nor_setpalisade_posts_03'),
                       'gate': 't_nor_setpalisade_gatehouse_02', 'post': 't_nor_setpalisade_post_01', 'step': 300.0,
                       'gate_half': 330.0}}
PALISADE_ROUND = 3             # (the outline's corners rounded off this many times over: the game's palisades curve)


def palisade_for(db, plan, asked=False):
    """The culture's palisade where its game towns stand them and its pieces load (asked: the Nords' for any
    culture, chosen by name), else None."""
    P = PALISADE.get(plan.get('culture')) or (PALISADE['Nordic'] if asked else None)
    if not P or db is None or db.resolve_id(P['posts'][0]) is None or db.resolve_id(P['gate']) is None:
        return None
    return P


def lay_palisade(db, plan, P):
    """A palisade round a village: W as lay() gives it ({'family': 'palisade', 'pieces', 'outline', 'gates', 'roads',
    'faults', 'palisade': True}); grounded() sets each section on its own ground."""
    poly, _th = ([tuple(p) for p in plan['wall_outline']], 0.0) if plan.get('wall_outline') else outline(plan, 1024.0, db, 1.0)
    if len(poly) < 3:
        return {'family': None, 'pieces': [], 'outline': [], 'gates': 0, 'faults': ['No plots to wall']}
    # (rounded: each corner cut a quarter of the way along its sides, over and over)
    ring = list(poly)
    for _r in range(PALISADE_ROUND):
        nr = []
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            nr += [(a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25), (a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75)]
        ring = nr
    # (the ring walked in sections of a step each)
    step = P['step']
    per = sum(math.hypot(ring[(i + 1) % len(ring)][0] - ring[i][0], ring[(i + 1) % len(ring)][1] - ring[i][1]) for i in range(len(ring)))
    n = max(8, int(round(per / step)))
    step = per / n

    def at(t):
        t %= per
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if t <= L or i == len(ring) - 1:
                f = t / L if L else 0.0
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            t -= L
        return ring[0]
    pts = [at(k * step) for k in range(n)]
    # (the gates: where the streets cross the ring, as lay() finds them)
    sides, roads = _street_crossings(plan, pts)
    mine = user_gates(plan, pts, roads, step)
    if mine:
        sides, roads = mine
    else:
        sides, roads = _downhill_gates(db, pts, sides, roads)
    gates_at = []
    for k, ds in sides.items():
        a, b = pts[k], pts[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        for h in ds:
            gates_at.append((a[0] + d[0] * h, a[1] + d[1] * h, d))
    pieces = []
    rng_i = 0
    for k in range(n):
        a, b = pts[k], pts[(k + 1) % n]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if any(math.hypot(mx - g[0], my - g[1]) < P['gate_half'] + step / 2 for g in gates_at):
            continue
        d = _unit(b[0] - a[0], b[1] - a[1])
        pid = P['posts'][(k * 7 + rng_i) % len(P['posts'])]
        pieces.append({'id': pid, 'pose': Pose(mx, my, 0.0, math.atan2(-d[1], d[0]), pid), 'kind': 'wall', 'run': 0})
    for gx, gy, d in gates_at:
        pieces.append({'id': P['gate'], 'pose': Pose(gx, gy, 0.0, math.atan2(-d[1], d[0]), P['gate']), 'kind': 'gate', 'run': 0})
        for s_ in (-1, 1):
            x, y = gx + d[0] * s_ * (P['gate_half'] + 20), gy + d[1] * s_ * (P['gate_half'] + 20)
            pieces.append({'id': P['post'], 'pose': Pose(x, y, 0.0, math.atan2(-d[1], d[0]), P['post']), 'kind': 'end', 'run': 0})
    if plan.get('open_sea') and db is not None:
        cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
        order = sorted(pieces, key=lambda p: math.atan2(p['pose'].y - cy, p['pose'].x - cx))
        pieces = _open_to_sea(db, pieces, order, lambda p: [_unit(p['pose'].x - cx, p['pose'].y - cy)], L=step)
        gates_at = [g for g in gates_at if any(p.get('kind') == 'gate' and math.hypot(p['pose'].x - g[0], p['pose'].y - g[1]) < 1 for p in pieces)]
    return {'family': 'palisade', 'kit': {'L': step, 'straight': None}, 'pieces': pieces, 'outline': pts, 'gates': len(gates_at),
            'faults': [] if gates_at else ['No street crosses the palisade'], 'roads': roads if gates_at else [], 'palisade': True}


def _palisade_grounded(db, W):
    """Each section stood as the game stands that piece over its ground (its posts run deep into it)."""
    import townbuild
    keep, memo = [], {}
    for p in W['pieces']:
        q = p['pose']
        g = mapdata.terrain_z(db, q.x, q.y)
        if g is None or g < 0:
            continue
        o = townbuild._game_over_ground(db, p['id'].lower())
        if o is None:
            o = ((W.get('kit') or {}).get('round') or {}).get('rise')
        if _low_wall(W) and p.get('kind') in ('wall', 'gate'):
            # (the lowest ground along it: its foot in the ground from end to end)
            c_, s_ = math.cos(q.rz), math.sin(q.rz)
            h_ = 0.45 * ((W.get('kit') or {}).get('L') or 800.0) * (getattr(q, 's', 1.0) or 1.0)
            for t_ in (-1.0, -0.5, 0.5, 1.0):
                g2 = mapdata.terrain_z(db, q.x + c_ * h_ * t_, q.y - s_ * h_ * t_)
                if g2 is not None and g2 >= 0:
                    g = min(g, g2)
        q.z = g + (o if o is not None else 0.0)
        p['corners'] = _box(db, p['id'], q, memo)[0]
        keep.append(p)
    W['pieces'] = keep
    return W


SAME = 8                       # (two pieces of one model this close, facing the same way or back to back, are one)


def _once(pieces):
    """The pieces with none laid twice: a side's run and the corner chain it runs into could both lay the length where
    they meet, two of ex_imp_wall_01 in one spot four times round the user's Nargorewatch (2026-11-01, "lots of walls
    overlapping/double spawned"). A corner, gate or tower is kept over a plain length."""
    rank = lambda q: 0 if q.get('kind') == 'wall' else 1
    out = []
    for q in sorted(pieces, key=rank, reverse=True):
        P = q['pose']
        if any(o['id'] == q['id'] and math.hypot(o['pose'].x - P.x, o['pose'].y - P.y) <= SAME
               and abs(((o['pose'].rz - P.rz + math.pi / 2) % math.pi) - math.pi / 2) <= math.radians(3) for o in out):
            continue
        out.append(q)
    return sorted(out, key=lambda q: pieces.index(q))


# the towers that rise over a wall, standing in its line with its lengths running into them, and the keep among them:
# Imperial walls' guardtower_02 at corners and between lengths, 192 under the wall's level (its own 1,863 tall, 870 over
# the wall), and a keep at the wall's level (keep_02, 820 over it), lab jtow1/jtow2. wall_tower_01 alone is the wall's
# own height and didn't read as a tower: "no towers or keeps at all ... and it should have them", the user's
# Chillmorrow, test4
BIG = {'ex_imp': {'tower': 'ex_imp_guardtower_02', 'tower_dz': -192, 'keep': 'ex_imp_keep_02', 'keep_dz': 0, 'every': 6}}
BIG_CLEAR = 900                # (no tower this near a gate or an opening)


def _big_towers(db, fam, kit, poly, outer, pieces):
    """[{'id', 'pose', 'kind': 'bigtower'|'keep', 'dz'}]: a tower on each outer corner and every few lengths along a
    side, the keep on the outer corner on the highest ground."""
    B = BIG.get(fam)
    if not B or not poly:
        return []
    L = kit['L']
    gates = [(p['pose'].x, p['pose'].y) for p in pieces if p.get('kind') in ('gate', 'end')]
    spots = []
    for k, v in enumerate(poly):
        if outer[k]:
            spots.append((v[0], v[1], 'corner', k))
    n = len(poly)
    for k in range(n):
        side = [p for p in pieces if p.get('run') == k and p['id'] == kit['straight']]
        a, b = poly[k], poly[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        side.sort(key=lambda p: (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1])
        every = B['every']
        for i in range(every // 2, len(side) - 2, every):
            q = side[i]['pose']
            spots.append((q.x + d[0] * L / 2.0, q.y + d[1] * L / 2.0, 'side', k))
    spots = [s for s in spots if all(math.hypot(s[0] - g[0], s[1] - g[1]) > BIG_CLEAR for g in gates)]
    keep_at = None
    if db is not None:
        hz = [(mapdata.terrain_z(db, s[0], s[1]) or -9e9, i) for i, s in enumerate(spots) if s[2] == 'corner']
        if hz:
            keep_at = max(hz)[1]
    out = []
    for i, (x, y, _w, k) in enumerate(spots):
        kp = i == keep_at
        t = B['keep'] if kp else B['tower']
        # (turned square to the side it stands on)
        a, b = poly[k], poly[(k + 1) % n]
        rz = _rz_for(kit, _unit(b[0] - a[0], b[1] - a[1]))
        out.append({'id': t, 'pose': Pose(x, y, 0.0, rz, t), 'kind': 'keep' if kp else 'bigtower',
                    'dz': B['keep_dz'] if kp else B['tower_dz']})
    return out


# stairs up to the wall walk from inside, as the game's forts and walled towns have theirs (its forts keep 1-7 each,
# lab j04/j05): ex_imp_wall_stairs_03 against a straight's inner face, 320 out from its line and 256 under it, turned
# half round on the -y side (8 of 8 in the game). Without them a walk was reached only through a tower room, and a town
# or castle with none had a walk no one could climb to
STAIRS = {'ex_imp': {'id': 'ex_imp_wall_stairs_03', 'ly': 320.0, 'dz': -256.0}}
STAIRS_CLEAR = 900             # (no stair this near a corner, a gate, an opening or a tower)
STAIRS_EVERY = 14              # (one beside each gate, and one every so many lengths besides)
STAIRS_MAX = 4


def wall_stairs(W, avoid=(), most=STAIRS_MAX, free=None, db=None):
    """Stairs up to the walk for a laid wall W (its kit's own, STAIRS): [{'id', 'pose', 'kind': 'stairs', 'dz',
    'host'}], each against a plain length's inner face, one near each gate first, then spread round the wall.
    avoid: more [(x, y)] to keep clear of (a castle's round towers); free(stair): whether its ground is free."""
    S = STAIRS.get(W.get('family'))
    poly = W.get('outline') or []
    kit = W.get('kit') or {}
    if not S or len(poly) < 3:
        return []
    keep_off = [(p['pose'].x, p['pose'].y) for p in W['pieces'] if p['id'] != kit.get('straight') or p.get('kind') != 'wall']
    keep_off += list(avoid)
    cand = [p for p in W['pieces'] if p.get('kind') == 'wall' and p['id'] == kit.get('straight') and 'run' in p
            and all(math.hypot(p['pose'].x - x, p['pose'].y - y) > STAIRS_CLEAR for x, y in keep_off)]
    stair = {}
    for c in cand:
        st = _stair_at(c, S, poly, free, db)
        if st:
            stair[id(c)] = st
    cand = [c for c in cand if id(c) in stair]
    gates = [p['pose'] for p in W['pieces'] if p.get('kind') in ('gate', 'end')]
    picks = []
    for g in gates:
        near = sorted((c for c in cand if c not in picks), key=lambda c: math.hypot(c['pose'].x - g.x, c['pose'].y - g.y))
        if near and math.hypot(near[0]['pose'].x - g.x, near[0]['pose'].y - g.y) < STAIRS_CLEAR + 1200:
            picks.append(near[0])
    # (then round the wall, the length furthest from every stair so far, while the wall is long enough for one more)
    n_more = max(1 if not picks else 0, len(cand) // STAIRS_EVERY)
    for _i in range(n_more):
        rest = [c for c in cand if c not in picks]
        if not rest or len(picks) >= most:
            break
        far = max(rest, key=lambda c: min([math.hypot(c['pose'].x - o['pose'].x, c['pose'].y - o['pose'].y) for o in picks] or [1e9]))
        if picks and min(math.hypot(far['pose'].x - o['pose'].x, far['pose'].y - o['pose'].y) for o in picks) < kit.get('L', 512) * STAIRS_EVERY / 2:
            break
        picks.append(far)
    return [stair[id(c)] for c in picks[:most]]


def _stair_at(c, S, poly, free, db):
    """The stair against plain length c's inner face, or None (outside the outline, on something, or on no ground)."""
    q = c['pose']
    for side in (-1, 1):
        ly = side * S['ly']
        wx, wy = q.x + ly * math.sin(q.rz), q.y + ly * math.cos(q.rz)
        if _inside(poly, (wx, wy)):
            st = {'id': S['id'], 'pose': Pose(wx, wy, 0.0, q.rz + (math.pi if side < 0 else 0.0), S['id']),
                  'kind': 'stairs', 'dz': S['dz'], 'host': q}
            if (free is None or free(st)) and (db is None or _stair_ground(db, st, q)):
                return st
            return None
    return None


LEVEL_STAIR_CLEAR = 400        # (a level's own stair this far from a tower, gate or corner at least: a short stretch between
                               # two towers still gets one)


def stair_each_level(W, avoid=(), free=None, db=None):
    """A stair up to the walk for every level stretch of a grounded wall that has none (W['stretches']): where the wall
    changes level at a tower or a keep the walk is cut there, and a stretch without a stair of its own could not be
    climbed to (the user's Firuhn, 2026-11-07). After fill_ground, the ground under it being final. [stair pieces], at
    their height."""
    S = STAIRS.get(W.get('family'))
    poly = W.get('outline') or []
    kit = W.get('kit') or {}
    if not S or len(poly) < 3 or not W.get('stretches'):
        return []
    have = {id(p['host']) for p in W['pieces'] if p.get('kind') == 'stairs' and p.get('host') is not None}
    by_pose = {id(p['pose']): p for p in W['pieces']}
    keep_off = [(p['pose'].x, p['pose'].y) for p in W['pieces'] if p['id'] != kit.get('straight') or p.get('kind') != 'wall']
    keep_off += list(avoid)
    out = []
    for ids in W['stretches']:
        ps = [by_pose[i] for i in ids if i in by_pose]
        plain = [p for p in ps if p.get('kind') == 'wall' and p['id'] == kit.get('straight') and 'run' in p]
        if len(plain) < 2 or any(id(p['pose']) in have for p in ps):
            continue
        mid = len(plain) / 2.0
        for k, c in sorted(enumerate(plain), key=lambda kc: abs(kc[0] + 0.5 - mid)):
            if any(math.hypot(c['pose'].x - x, c['pose'].y - y) <= LEVEL_STAIR_CLEAR for x, y in keep_off):
                continue
            st = _stair_at(c, S, poly, free, db)
            if st:
                st['pose'].z = c['pose'].z + S['dz']
                out.append(st)
                keep_off.append((c['pose'].x, c['pose'].y))
                break
    return out


DOUBLED = 0.3                  # (a new wall piece over this share of whose footprint another wall already stands is left out)
DOUBLED_SIDE = 0.3             # (or this share within WALL_KEEP beside a standing wall running the same way: a town's north wall
                               # stood back to back with the castle's south wall, the outer hanging or buried; Sketh, 2026-11-07)
PARALLEL = 25                  # (degrees: two wall pieces running the same way, for the side-by-side test)


def _parallel(a, b):
    """Whether two pieces' quads run the same way (their long edges within PARALLEL degrees)."""
    def axis(q):
        e01 = (q[1][0] - q[0][0], q[1][1] - q[0][1])
        e12 = (q[2][0] - q[1][0], q[2][1] - q[1][1])
        e = e01 if math.hypot(*e01) >= math.hypot(*e12) else e12
        return math.degrees(math.atan2(e[1], e[0])) % 180.0
    d = abs(axis(a) - axis(b)) % 180.0
    return min(d, 180.0 - d) <= PARALLEL


def _widen(cs, d):
    """A piece's quad (corners as _box gives them) widened by d across its short axis."""
    e01 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e12 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    if math.hypot(*e01) <= math.hypot(*e12):
        u = _unit(*e01)
        return [(cs[0][0] - u[0] * d, cs[0][1] - u[1] * d), (cs[1][0] + u[0] * d, cs[1][1] + u[1] * d),
                (cs[2][0] + u[0] * d, cs[2][1] + u[1] * d), (cs[3][0] - u[0] * d, cs[3][1] - u[1] * d)]
    u = _unit(*e12)
    return [(cs[0][0] - u[0] * d, cs[0][1] - u[1] * d), (cs[1][0] - u[0] * d, cs[1][1] - u[1] * d),
            (cs[2][0] + u[0] * d, cs[2][1] + u[1] * d), (cs[3][0] + u[0] * d, cs[3][1] + u[1] * d)]


def wall_models(db):
    """Every wall kit's pieces (the towns' and the castle survey's house forts), lower case."""
    out = set()
    for k in kits(db).values():
        out |= set(k['models'])
    try:
        import castlesurvey
        for k in (castlesurvey.survey(db).get('wall_kits') or {}).values():
            out |= set(k.get('models') or ())
    except Exception:
        pass
    return out


def standing_walls(db, pts, R=1200, skip=()):
    """The wall pieces already standing near pts (a town's or a castle's, the game's or made): [(corners, z0, z1)]."""
    M = wall_models(db)
    # (every cell the box round each point reaches, not only its corners': a reach past half a cell skipped the cell in
    # the middle, and a castle beside a town found none of the town's wall there, 2026-11-09)
    cells = {'#%d,%d' % (gx, gy) for x, y in pts
             for gx in range(math.floor((x - R) / 8192.0), math.floor((x + R) / 8192.0) + 1)
             for gy in range(math.floor((y - R) / 8192.0), math.floor((y + R) / 8192.0) + 1)}
    out = []
    for ck in cells:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r['k'] in skip or r['id'].lower() not in M or not r.get('b'):
                continue
            b, s = r['b'], r.get('s') or 1.0
            c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
            cs = [(r['p'][0] + (bx * c + by * sn) * s, r['p'][1] + (-bx * sn + by * c) * s) for bx, by in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4]))]
            out.append((cs, r['p'][2] + b[2] * s, r['p'][2] + b[5] * s))
    return out


def _quad_area(q):
    return abs(sum(q[i][0] * q[(i + 1) % len(q)][1] - q[(i + 1) % len(q)][0] * q[i][1] for i in range(len(q)))) / 2.0


def _clip(subject, clip):
    """Convex polygon clipping (Sutherland-Hodgman): subject inside convex clip."""
    out = list(subject)
    n = len(clip)
    sgn = 1.0 if sum(clip[i][0] * clip[(i + 1) % n][1] - clip[(i + 1) % n][0] * clip[i][1] for i in range(n)) > 0 else -1.0
    for i in range(n):
        a, b = clip[i], clip[(i + 1) % n]
        inp, out = out, []
        if not inp:
            break
        side = lambda p: sgn * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) >= 0
        for j in range(len(inp)):
            P, Q = inp[j], inp[(j + 1) % len(inp)]
            if side(Q):
                if not side(P):
                    out.append(_isect(P, Q, a, b))
                out.append(Q)
            elif side(P):
                out.append(_isect(P, Q, a, b))
    return out


def _isect(P, Q, a, b):
    x1, y1, x2, y2 = P[0], P[1], Q[0], Q[1]
    x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return Q
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def drop_doubled(db, W, skip=()):
    """W's pieces with those left out that stand where a wall already does: a castle drawn against a town's wall, or a
    town walled round a castle, ran two walls through each other. Where they meet the wall standing there serves both.
    The count left out."""
    memo = {}
    have = standing_walls(db, [(p['pose'].x, p['pose'].y) for p in W['pieces']], 800, skip)
    if not have:
        return 0
    keep, n = [], 0
    for p in W['pieces']:
        cs, b = _box(db, p['id'], p['pose'], memo)
        # (nor a join: the length and the tower that carry the town's wall into a castle's stand in it by design)
        if cs and p.get('kind') not in ('stairs',) and not p.get('join'):
            A = _quad_area(cs) or 1.0
            if any(_quad_area(_clip(cs, h[0]) or []) >= DOUBLED * A or
                   (_parallel(cs, h[0]) and _quad_area(_clip(cs, _widen(h[0], WALL_KEEP)) or []) >= DOUBLED_SIDE * A)
                   for h in have if abs(h[0][0][0] - cs[0][0]) < 1500 and abs(h[0][0][1] - cs[0][1]) < 1500):
                n += 1
                continue
        keep.append(p)
    W['pieces'] = keep
    if n:
        W.setdefault('faults', []).append('%d pieces left out where a wall already stands' % n)
    return n


STAIRS_GROUND = 200            # (a stair's ground this near its wall's, or the stair would stand in a bank or in the air)


def _stair_ground(db, st, host):
    """Whether the ground under a stair lies as the ground under its length does: inside a wall at a hill's foot the
    land rises steeply, and a stair set there stood 939 deep in it, its top meeting no walk (lab w02)."""
    g0 = mapdata.terrain_z(db, host.x, host.y)
    if g0 is None:
        return False
    q = st['pose']
    pts = [(q.x, q.y)] + [(q.x + dx * math.cos(q.rz) + dy * math.sin(q.rz), q.y - dx * math.sin(q.rz) + dy * math.cos(q.rz))
                          for dx in (-440, 440) for dy in (-240, 240)]
    zs = [mapdata.terrain_z(db, x, y) for x, y in pts]
    return all(z is not None and abs(z - g0) <= STAIRS_GROUND for z in zs)


def _unit(x, y):
    h = math.hypot(x, y) or 1.0
    return x / h, y / h


REACH = 3500                   # a street's end is carried on to the wall this far, for a gate


def user_gates(plan, poly, roads, L, sides=None):
    """The gates where the user put them ("really need some flexibility with where these gates wind up", 2026-11-08):
    each drawn gate (plan['user_gates']) on the nearest side of poly, at the point nearest it, and its way in, the
    carried street that reaches the wall nearest it (within two lengths) or a new one from the nearest point of a
    street. Only the sides that can hold a gate (sides, when given): one put on a short jog of the wall goes to the
    nearest side that can. ({side: [distance along]}, roads), as _street_crossings gives them; None where the user drew
    none."""
    ug = plan.get('user_gates') or []
    if not ug:
        return None
    n = len(poly)
    out, rds = defaultdict(list), []
    spts = [tuple(p) for st in plan.get('streets') or () if not st.get('ring') for p in st.get('pts') or ()]
    for g in ug:
        best = None
        for k in range(n):
            if sides and k not in sides:
                continue
            a, b = poly[k], poly[(k + 1) % n]
            d = _unit(b[0] - a[0], b[1] - a[1])
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            t = max(0.0, min(ln, (g[0] - a[0]) * d[0] + (g[1] - a[1]) * d[1]))
            dist = math.hypot(g[0] - (a[0] + d[0] * t), g[1] - (a[1] + d[1] * t))
            # (clear of the corners, so a whole gate fits there: one moved to the nearest side that can hold it landed
            # at that side's corner and was never laid, lab j_gate)
            m = min(ln / 2.0, 3.0 * L)
            t = max(m, min(ln - m, t))
            q = (a[0] + d[0] * t, a[1] + d[1] * t)
            if best is None or dist < best[0]:
                best = (dist, k, t, q)
        _dd, k, t, q = best
        out[k].append(t)
        r = min(roads, key=lambda r_: math.hypot(r_[1][0] - q[0], r_[1][1] - q[1])) if roads else None
        if r is not None and math.hypot(r[1][0] - q[0], r[1][1] - q[1]) < 2 * L:
            rds.append((r[0], q, r[2]))
        elif spts:
            p = min(spts, key=lambda s_: math.hypot(s_[0] - q[0], s_[1] - q[1]))
            rds.append((p, q, 256))
    return out, rds




def _street_crossings(plan, poly):
    """({side: [distance along it]} where the plan's streets cross the outline, or would if carried on from their
    ends; [(from, to)] the stretches carried on, to pave). The main street both ways at least, as the game's walled
    towns are entered along their main street."""
    out = defaultdict(list)
    roads = []
    n = len(poly)
    ringed = any(st.get('ring') for st in plan.get('streets') or ())
    for si, st in enumerate(plan.get('streets') or ()):
        if st.get('ring') or st.get('court') or st.get('len'):
            continue                 # (the lane round inside the wall and the courts' lanes lead nowhere out: a gate where
                                     # one happened to end stood behind a row of houses, 7 of 15 gates, lab jgate)
        pts = [tuple(p) for p in st['pts']]
        segs = list(zip(pts, pts[1:]))
        for a, b in segs:
            for k in range(n):
                hit = _cross(a, b, poly[k], poly[(k + 1) % n])
                if hit is not None:
                    out[k].append(hit)
        if len(pts) < 2:
            continue
        for a, b in ((pts[1], pts[0]), (pts[-2], pts[-1])):
            if not _inside(poly, b):
                continue
            d = _unit(b[0] - a[0], b[1] - a[1])
            far = (b[0] + d[0] * REACH, b[1] + d[1] * REACH)
            best = None
            for k in range(n):
                hit = _cross(b, far, poly[k], poly[(k + 1) % n])
                if hit is not None:
                    w = poly[k]
                    e = _unit(poly[(k + 1) % n][0] - w[0], poly[(k + 1) % n][1] - w[1])
                    q = (w[0] + e[0] * hit, w[1] + e[1] * hit)
                    dist = math.hypot(q[0] - b[0], q[1] - b[1])
                    if best is None or dist < best[0]:
                        best = (dist, k, hit, q)
            # (a branch whose end is far from the wall is a lane that stops in town; the main street goes out)
            # (in a town with a lane round inside its wall, the branches end at that lane and only the main street goes out:
            # carried on, a branch's gate opened behind the row of houses along the wall, lab jgate)
            if best and (si == 0 or (best[0] <= REACH / 3 and not ringed)):
                out[best[1]].append(best[2])
                roads.append((b, best[3], st.get('w') or 256))
    return out, roads


# gates on the low side: the game's walled towns and forts are entered from below, 63% of their gates on the lowest third
# of their wall's ground and 15% on the highest (123 gates, lab j03); the main street carried out at both ends gave a
# gate at its top as often as at its foot
GATE_HIGH = 0.67               # (a gate on ground higher than this share of the wall's)
GATE_RISE = 192                # (and this much over the lowest gate's ground) is left out, while another gate remains


SEA_NEAR = 3000                # (a length with water within this of its outer face faces the water)
SEA_STEP = 400
SEA_MIN = 3                    # (fewer lengths in a row than this are not opened)
SEA_ALONE = 6                  # (fewer than this left standing between two openings go too)
SEA_BY = 1500                  # (a section with water this near all along it stands by the water)


def _faces_sea(db, x, y, nx, ny):
    for i in range(int(SEA_NEAR // SEA_STEP) + 1):
        z = mapdata.terrain_z(db, x + nx * SEA_STEP * i, y + ny * SEA_STEP * i)
        if z is None or z < GATE_WATER:
            return True
    return False


def _out_normals(poly):
    """Each side's unit normal pointing out of the outline."""
    n = len(poly)
    s = 1 if sum(poly[k][0] * poly[(k + 1) % n][1] - poly[(k + 1) % n][0] * poly[k][1] for k in range(n)) > 0 else -1
    out = []
    for k in range(n):
        d = _unit(poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1])
        out.append((d[1] * s, -d[0] * s))
    return out


def _sea_sides(db, poly, L):
    """The sides of an outline that face the water along half their length or more."""
    n, nrm, out = len(poly), _out_normals(poly), set()
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        m = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // L))
        wet = sum(1 for i in range(m) if _faces_sea(db, a[0] + (b[0] - a[0]) * (i + 0.5) / m, a[1] + (b[1] - a[1]) * (i + 0.5) / m, *nrm[k]))
        if 2 * wet >= m:
            out.add(k)
    return out


def _even(flags, v, least):
    """flags (round a ring) with every run of v shorter than least turned over."""
    N = len(flags)
    if all(f == v for f in flags) or not any(f == v for f in flags):
        return flags
    s = next(i for i in range(N) if flags[i] != v)
    out = list(flags)
    i = 0
    while i < N:
        if flags[(s + i) % N] != v:
            i += 1
            continue
        j = i
        while j < N and flags[(s + j) % N] == v:
            j += 1
        if j - i < least:
            for t in range(i, j):
                out[(s + t) % N] = not v
        i = j
    return out


def _by_water(db, x, y):
    """Water within SEA_BY of a spot, any way round."""
    for i in range(8):
        for r in (SEA_BY / 2.0, SEA_BY):
            z = mapdata.terrain_z(db, x + r * math.cos(i * math.pi / 4), y + r * math.sin(i * math.pi / 4))
            if z is None or z < GATE_WATER:
                return True
    return False


def _open_to_sea(db, pieces, order, normals, straight=None, tower=None, dirs=None, nrm=None, L=None, cap=None):
    """pieces without the wall that faces the water: order is the wall's pieces round the ring, normals(p) the ways out
    from a piece (a corner faces the water when both its sides do). The towers standing on a length left out go with it.
    The wall that stays runs on to the water at both its ends, straight on past the corner where the ring turns along
    the shore, so that nobody walks round it; a section standing wholly by the water, apart from the land side's wall,
    goes too (the user's Senchal, 2026-11-09). A wall's end is capped: the family's big tower (cap: {'id', 'dz'}) in
    the place of its last length, else the kit's wall tower."""
    N = len(order)
    if N < 2 * SEA_MIN:
        return pieces
    wet = [all(_faces_sea(db, p['pose'].x, p['pose'].y, nx, ny) for nx, ny in normals(p)) for p in order]
    wet = _even(_even(wet, True, SEA_MIN), False, SEA_ALONE)
    if not any(wet) or all(wet):
        return pieces
    # (the sections left standing; all but the longest go when they stand by the water all along)
    s0 = next(i for i in range(N) if wet[i])
    secs, cur = [], []
    for t in range(1, N + 1):
        i = (s0 + t) % N
        if not wet[i]:
            cur.append(i)
        elif cur:
            secs.append(cur)
            cur = []
    longest = max(secs, key=len)
    for sec in secs:
        if sec is not longest and all(_by_water(db, order[i]['pose'].x, order[i]['pose'].y) for i in sec):
            for i in sec:
                wet[i] = True
    at_water = lambda q: (lambda zz: zz is None or zz < GATE_WATER)(mapdata.terrain_z(db, q['pose'].x, q['pose'].y))
    wet0, added, ends = list(wet), [], []
    for i in range(N):
        for step in (1, -1):
            if wet0[i] or not wet0[(i + step) % N]:
                continue
            # (this end runs on along its side while the ground is dry)
            j, p, c = i, order[i], None
            if dirs is None:
                # (a palisade: straight on from its end, the way its last lengths ran, to the water)
                q = order[(i - 3 * step) % N]
                u = _unit(p['pose'].x - q['pose'].x, p['pose'].y - q['pose'].y)
                sp = L or math.hypot(p['pose'].x - q['pose'].x, p['pose'].y - q['pose'].y)
                wid = next((t['id'] for t in order if t.get('kind') == 'wall'), None)
                m, M = 1, int(SEA_NEAR // max(1.0, sp)) + 3
                dryz = lambda m_: (lambda zz: zz is not None and zz >= GATE_WATER)(mapdata.terrain_z(db, p['pose'].x + u[0] * sp * m_, p['pose'].y + u[1] * sp * m_))
                while m <= M and dryz(m):
                    m += 1
                if wid and sp > 1 and m <= M and not at_water(p):
                    for m_ in range(1, m + 1):
                        added.append({'id': wid, 'pose': Pose(p['pose'].x + u[0] * sp * m_, p['pose'].y + u[1] * sp * m_, 0.0, math.atan2(-u[1], u[0]), wid), 'kind': 'wall', 'run': 0})
                continue
            if 'corner' in p:
                c = p['corner']
            else:
                k, back = p.get('run'), []
                reach = int(SEA_NEAR // max(1.0, L or math.hypot(order[(i + step) % N]['pose'].x - p['pose'].x, order[(i + step) % N]['pose'].y - p['pose'].y))) + 2
                while not at_water(order[j]):
                    nj = (j + step) % N
                    if not wet0[nj]:
                        break
                    if dirs is not None and order[nj].get('run') != k:
                        c = order[nj].get('corner')
                        break
                    if dirs is None and len(back) >= reach:
                        # (a palisade with no water this near along its ring: as it was)
                        for t in back:
                            wet[t] = True
                        j = i
                        break
                    wet[nj] = False
                    back.append(nj)
                    j = nj
            end = order[j]
            if c is not None and dirs is not None and straight and L:
                # (the ring turns here: straight on to the water, the corner left out)
                n = len(dirs)
                u = dirs[(c - 1) % n] if step == 1 else (-dirs[c][0], -dirs[c][1])
                w = nrm[c] if step == 1 else nrm[(c - 1) % n]
                chain = [t for t in range(N) if order[t].get('corner') == c]
                A = order[chain[0] if step == 1 else chain[-1]] if chain else None
                if A is not None and u[0] * w[0] + u[1] * w[1] > 0.5:
                    m, M = 1, int(SEA_NEAR // L) + 3
                    spot = lambda m_: (A['pose'].x + u[0] * L * m_, A['pose'].y + u[1] * L * m_)
                    wetz = lambda xy: (lambda zz: zz is None or zz < GATE_WATER)(mapdata.terrain_z(db, xy[0], xy[1]))
                    while m <= M and not wetz(spot(m)):
                        m += 1
                    if m <= M:
                        for t in chain:
                            wet[t] = order[t] is not A
                        end = A
                        for m_ in range(1, m + 1):
                            x, y = spot(m_)
                            end = {'id': straight, 'pose': Pose(x, y, 0.0, A['pose'].rz, straight), 'kind': 'wall',
                                   'run': (c - 1) % n if step == 1 else c}
                            added.append(end)
            ends.append(end)
    gone = {id(p) for p, w in zip(order, wet) if w}
    ring = {id(p) for p in order}
    for p in pieces:
        if id(p) not in ring:
            q = min(order, key=lambda o: math.hypot(o['pose'].x - p['pose'].x, o['pose'].y - p['pose'].y))
            if id(q) in gone:
                gone.add(id(p))
    out = [p for p in pieces if id(p) not in gone] + added
    if cap and L:
        # (the wall's ends capped by the family's big tower, standing where the last length stood; the towers the wall
        # already had this near make way for it)
        caps = []
        for p in ends:
            if id(p) in gone or not any(p is q for q in out):
                continue
            caps.append({'id': cap['id'], 'pose': Pose(p['pose'].x, p['pose'].y, 0.0, p['pose'].rz, cap['id']), 'kind': 'bigtower', 'dz': cap['dz']})
        near = lambda q: any(math.hypot(q['pose'].x - c['pose'].x, q['pose'].y - c['pose'].y) < 2.5 * L for c in caps)
        ended = {id(p) for p in ends}
        out = [q for q in out if not (id(q) in ended and near(q)) and not (q.get('kind') in ('bigtower', 'tower') and near(q))] + caps
    elif tower and straight:
        for p in ends:
            if p['id'] == straight and id(p) not in gone:
                p['id'] = p['pose'].id = tower
                p['kind'] = 'tower'
    return out


GATE_WATER = 16                # (ground under this, by the water line, is no way in: the sea or the shore)
GATE_SLOPE = 0.7               # (a rise or drop steeper than this, about 35 degrees, before a gate: a cliff, not a way)


def gate_blocked(db, x, y, nx, ny, z0=None, near=0.0):
    """(wet, steep) for a way out at x, y going nx, ny: water or no land within 2.5k of it, or a cliff on the way."""
    zp = mapdata.terrain_z(db, x, y) if z0 is None else z0
    if zp is None:
        return True, False
    dp, steep = 0.0, False
    for dist in (near + 500, near + 1500, near + 2500):
        zz = mapdata.terrain_z(db, x + nx * dist, y + ny * dist)
        if zz is None or zz < GATE_WATER:
            return True, steep
        if abs(zp - zz) > GATE_SLOPE * (dist - dp):
            steep = True
        zp, dp = zz, dist
    return False, steep


def _fallback_gate(db, plan, poly, roads, L, sides=None):
    """One gate for a wall no street crosses: ({side: [distance along]}, roads) as _street_crossings gives them. The
    main street's end carried on to the side it faces (clear of the corners) when it has one, else a side's middle; among
    the spots the dry ones first, then those no cliff bars, then a street's end over a side's middle, the nearest such
    end, or the lowest middle."""
    n = len(poly)
    cx, cy = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    main = next((st for st in plan.get('streets') or () if not st.get('ring') and not st.get('court') and not st.get('len')
                 and len(st.get('pts') or ()) >= 2), None)
    ends = []
    if main:
        pts = [tuple(q) for q in main['pts']]
        ends = [(pts[1], pts[0]), (pts[-2], pts[-1])]
    cands = []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        Lk = math.hypot(b[0] - a[0], b[1] - a[1])
        if Lk < 3 * L or (sides is not None and k not in sides):
            continue
        d = _unit(b[0] - a[0], b[1] - a[1])
        nx, ny = -d[1], d[0]
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        if nx * (mx - cx) + ny * (my - cy) < 0:
            nx, ny = -nx, -ny
        spots = [(None, Lk / 2.0, 0.0)]
        for _a, e in ends:
            if not _inside(poly, e):
                continue
            h = (e[0] - a[0]) * d[0] + (e[1] - a[1]) * d[1]
            if 1.5 * L <= h <= Lk - 1.5 * L:
                spots.append((e, h, abs(-(e[0] - a[0]) * d[1] + (e[1] - a[1]) * d[0])))
        for e, h, dist in spots:
            x, y = a[0] + d[0] * h, a[1] + d[1] * h
            z = mapdata.terrain_z(db, x, y) if db is not None else None
            wet, steep = gate_blocked(db, x, y, nx, ny, z) if db is not None else (False, False)
            key = (wet, steep, 0 if e is not None else 1, dist if e is not None else (z if z is not None else 0.0))
            cands.append((key, k, h, (x, y), e))
    out = defaultdict(list)
    if not cands:
        return out, roads
    best = min(cands, key=lambda c: c[0])
    out[best[1]].append(best[2])
    if best[4] is not None:
        roads = list(roads) + [(best[4], best[3], (main.get('w') if main else None) or 256)]
    return out, roads


def _downhill_gates(db, poly, streets, roads):
    n = len(poly)
    ring = []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        for i in range(max(1, int(L / 256))):
            t = i / max(1, int(L / 256))
            z = mapdata.terrain_z(db, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if z is not None:
                ring.append(z)
    gs = []
    for k, ds in streets.items():
        a, b = poly[k], poly[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        for h in ds:
            x, y = a[0] + d[0] * h, a[1] + d[1] * h
            gs.append((mapdata.terrain_z(db, x, y), k, h, (x, y)))
    # (a crossing where the wall line has no land at all, past the island's edge, is the most blocked of ways, not one
    # to skip: skipped, three such gates stood on a cliff top over nothing, the user's Sketh 2026-11-06)
    if len(gs) < 2 or not ring:
        return streets, roads
    # (a gate out onto the sea or over a cliff goes first, whatever its height: a coast town's lowest gate faced the
    # water, the user, 2026-11-03; never the last gate, and of gates all blocked the least blocked stays)
    cx, cy = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    blocked = {}
    for g in gs:
        a, b = poly[g[1]], poly[(g[1] + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        nx, ny = -d[1], d[0]
        if nx * (g[3][0] - cx) + ny * (g[3][1] - cy) < 0:
            nx, ny = -nx, -ny
        blocked[id(g)] = (True, True) if g[0] is None else gate_blocked(db, g[3][0], g[3][1], nx, ny, g[0])
    zs_ = [g[0] for g in gs if g[0] is not None]
    low = min(g[0] for g in gs if g[0] is not None and not blocked[id(g)][0]) if any(g[0] is not None and not blocked[id(g)][0] for g in gs) else (min(zs_) if zs_ else 0.0)
    drop = []
    for g in sorted(gs, key=lambda g: (-blocked[id(g)][0], -blocked[id(g)][1], -(g[0] if g[0] is not None else 1e9))):
        if len(gs) - len(drop) <= 1:
            break
        if blocked[id(g)][0] or blocked[id(g)][1]:
            drop.append(g)
            continue
        if g[0] is None:
            continue
        rank = sum(1 for z in ring if z < g[0] - 32) / float(len(ring))
        if rank > GATE_HIGH and g[0] > low + GATE_RISE:
            drop.append(g)
    if not drop:
        return streets, roads
    out = defaultdict(list)
    for k, ds in streets.items():
        for h in ds:
            if not any(g[1] == k and abs(g[2] - h) < 1 for g in drop):
                out[k].append(h)
    roads = [r for r in roads if not any(math.hypot(r[1][0] - g[3][0], r[1][1] - g[3][1]) < 400 for g in drop)]
    return out, roads


def _inside(poly, p):
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _cross(p1, p2, a, b):
    """Where segment p1p2 crosses ab, as the distance from a along ab; else None."""
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    qx, qy = a[0] - p1[0], a[1] - p1[1]
    t = (qx * sy - qy * sx) / den
    u = (qx * ry - qy * rx) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return u * math.hypot(sx, sy)
    return None


TOWER_EVERY = 3


def _side(kit, S0, D, d, crossings, faults, k):
    """The pieces between a corner's out-straight S0 and the next corner's in-straight, D along d: straights at the
    step, a gate where a street crosses, towers as often as the game's. ([pieces], gates)."""
    L = kit['L']
    gate = _best(kit, 'gate')
    tower = _best(kit, 'tower')
    out = []
    # (distances from S0 along the side where a gate should stand: the crossing, less what the corner took)
    want_gate = sorted(set(round(c / L) for c in crossings))
    pos, p, g = 0.0, S0, 0
    since_tower = 0
    # (a tower every few straights, at most TOWER_EVERY: the game's Imperial walls stand 0.45 towers a straight, its
    # wall_tower_01 and its towerb stacks together, lab jwallgame; by wall_tower_01 alone, one in six, they looked bare)
    every = min(int(round(tower[1]['every'])), TOWER_EVERY) if tower else 0
    while True:
        left = D - pos
        nxt = None
        # a gate when this stretch reaches the street (and it fits before the next corner)
        if gate and want_gate and pos + gate[1]['span'] <= D - L * 0.5 and abs((pos + gate[1]['span'] / 2.0) / L - want_gate[0]) <= 1.0:
            nxt = gate
            want_gate.pop(0)
        elif tower and every and since_tower >= every and pos + tower[1]['span'] <= D - L:
            nxt = tower
        if nxt:
            t, v = nxt
            X = p.then(v['e1'], t)
            S1 = X.then(v['e2'], kit['straight'])
            out.append({'id': t, 'pose': X, 'kind': v['kind']})
            if v['kind'] == 'gate':
                g += 1
            since_tower = 0 if v['kind'] == 'tower' else since_tower + 1
            pos += v['span']
            if pos >= D - 1:
                # (the in-line piece brought its own straight where the next corner's stands)
                if abs(pos - D) > 2:
                    faults.append('side %d: ends %.0f units off' % (k, pos - D))
                return out, g
            out.append({'id': kit['straight'], 'pose': S1, 'kind': 'wall'})
            p = S1
            continue
        if not gate and want_gate and abs((pos + L * 1.5) / L - want_gate[0]) <= 0.5 and pos + L * 4 <= D - L:
            # (an opening: the game's wall runs stop with their end pieces; two steps open, the street through it)
            want_gate.pop(0)
            E = kit['ends'].get('fwd')
            if E:
                out.append({'id': E['id'], 'pose': p.then(E['e'], E['id']), 'kind': 'end'})
            p = Pose(p.x + d[0] * L * 3, p.y + d[1] * L * 3, 0.0, p.rz, kit['straight'])
            pos += L * 3
            out.append({'id': kit['straight'], 'pose': p, 'kind': 'wall'})
            E = kit['ends'].get('back')
            if E:
                out.append({'id': E['id'], 'pose': p.then(E['e'], E['id']), 'kind': 'end'})
            g += 1
            since_tower += 1
            continue
        while want_gate and want_gate[0] * L < pos - L:
            want_gate.pop(0)                         # (passed: a gate did not fit there)
        if left <= 2:
            return out, g
        if left >= L - 1:
            p = Pose(p.x + d[0] * L, p.y + d[1] * L, 0.0, p.rz, kit['straight'])
            pos += L
            if pos >= D - 1:
                return out, g                     # (that place is the next corner's own straight)
            out.append({'id': kit['straight'], 'pose': p, 'kind': 'wall'})
            since_tower += 1
            continue
        # less than a step left: the last straight overlaps the one before it, if the game does that
        if kit['overlap'] and left >= L * (1 - OVERLAP_MAX):
            return out, g                          # (the next corner's in-straight overlaps this one: nothing to add)
        faults.append('side %d: %.0f units the wall cannot close' % (k, left))
        return out, g


def _best(kit, kind):
    c = [(t, v) for t, v in kit['inline'].items() if v['kind'] == kind and v['span'] >= kit['L']]
    return max(c, key=lambda tv: tv[1]['n']) if c else None


WALL_KIN = {'Indoril': 't_de_setveloth'}


def pick_family(db, plan):
    """The wall family for the town's culture: the one the culture's game towns stand most often, else the one whose
    family leads the town's buildings, else none."""
    K = kits(db)
    cult = plan.get('culture')
    # (Anvil's and the Gold Coast's towns, out of Imperial, have the Imperial wall when they have none counted of their own)
    for c_ in (cult, 'Imperial') if cult in ('Anvil', 'Gold Coast') else (cult,):
        best = max(K.items(), key=lambda kv: (kv[1].get('cultures') or {}).get(c_, 0), default=None)
        if best and (best[1].get('cultures') or {}).get(c_, 0) >= 2:
            return best[0]
    fam = plan.get('family')
    if fam in K:
        return fam
    # (a culture whose own wall is not learnt takes the wall its game towns stand beside their own: the Indoril towns'
    # is built of wall lengths and posts in turn, which the wall learning does not read, and an Indoril town asked for
    # a wall got none; Nanaav stands 14 lengths of the Velothi wall in its own. The check of 2026-11-13)
    kin = WALL_KIN.get(cult)
    if kin in K:
        return kin
    return None


SINK = 24                      # a wall piece's foot stands this far under the lowest ground beneath it


def _box(db, pid, pose, memo):
    """A piece's corners in the world and its bounds [x0, y0, z0, x1, y1, z1] (or None)."""
    if pid not in memo:
        ri = db.resolve_id(pid)
        memo[pid] = mapdata.object_bounds(db, ri) if ri is not None else None
    b = memo[pid]
    if not b:
        return None, None
    k_ = getattr(pose, 's', 1.0) or 1.0
    if k_ != 1.0:
        b = [v * k_ for v in b]
    f_ = _FOOT.get(str(pid).lower())
    if f_:
        b = list(b)
        b[2] = min(b[2] + f_, -16.0)        # (a foot made for the ground or the water: the rest of it counts as its bottom)
    c, s = math.cos(pose.rz), math.sin(pose.rz)
    return [(pose.x + bx * c + by * s, pose.y - bx * s + by * c) for bx, by in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4]))], b


LEVEL_TOL = 192                # the ground under a wall run is moved towards the run's level by at most this
CUT_TOL = 640                  # (towards the ring's one level: cut down this much at most, raised this much at most)
RAISE_TOL = 512
LEVEL_R = 320                  # (full change within this of the run's line, fading to nothing over LEVEL_BLEND beyond)
LEVEL_BLEND = 384
LEVEL_FADE = 3.0               # (or this times the change, up to LEVEL_BLEND_MAX: a 640 cut faded over 384 left a bank of 59
LEVEL_BLEND_MAX = 1024         # degrees under the wall on a hill, the city round of 2026-11-01; 3x keeps it under 30)


def level_ground(db, W, skip=(), tol=LEVEL_TOL, keep=()):
    """The ground along each straight run of the wall evened out towards the run's middle height, by at most tol, fading
    back into the land round it, before the wall is set on it: so a run stays one level, as the game's own do, rather
    than being cut into steps on a lumpy slope (the user, 2026-10-31: "allow the city planner to reshape land to
    accommodate walls ... within tolerance"). What stands on that ground follows it (skip: the town's own new refs).
    Returns the cells changed."""
    import landscape
    if W.get('palisade'):
        return 0                          # (a palisade follows the land, section by section)
    runs = defaultdict(list)
    for p in W['pieces']:
        if 'run' in p:
            runs[p['run']].append(p['pose'])
    segs, tz = [], {}
    # (one level for the whole ring: the ground under every run evened towards the middle height of all of it, so the
    # wall goes round at one height as far as the land allows; per run, the user's Chillmorrow stood at 19 levels, and
    # they set it all at one, flattening the ground to it, test4)
    every = sorted(z for ps in runs.values() for z in (mapdata.terrain_z(db, q.x, q.y) for q in ps) if z is not None and z >= 0)
    ring = every[len(every) // 2] if every else None
    # (round a mountainside, HILL_RELIEF: a run under the ring's level towards its own middle height, and raised by tol
    # only. Towards the ring's one level the low side was raised 500 before any fill and stood on a bank 1,000 high,
    # the lab's Gold Coast hill town, 2026-11-10. The high side is cut as ever: left high, the wall stood 500 over the
    # houses inside it)
    hill = bool(every) and every[int(len(every) * 0.9)] - every[int(len(every) * 0.1)] > HILL_RELIEF
    for k, ps in runs.items():
        zs = sorted(z for z in (mapdata.terrain_z(db, q.x, q.y) for q in ps) if z is not None)
        if not zs or zs[len(zs) // 2] < 0:
            continue                      # (a run at the water: left as it is)
        tz[k] = min(ring, zs[len(zs) // 2]) if hill else ring
        segs.append(((ps[0].x, ps[0].y), (ps[-1].x, ps[-1].y), tz[k]))
    # (the corners too, towards the runs either side: a corner on a cliff's edge stood buried on its high side)
    nk = max(list(runs) + [-1]) + 1
    for p in W['pieces']:
        if 'corner' in p:
            near = [tz[k] for k in ((p['corner'] - 1) % max(1, nk), p['corner']) if k in tz]
            if near:
                q = p['pose']
                segs.append(((q.x, q.y), (q.x, q.y), sum(near) / len(near)))
    return _shape_ground(db, segs, skip, CUT_TOL, tol if hill else RAISE_TOL, keep)


HILL_RELIEF = 2048             # (a wall round a mountainside: its ground differs by more than this, a tenth of it left out
                               # at each end)
FILL_MAX = 1024                # (a stretch sunk this far under its neighbours is raised to them, the ground filled under it)
LEVEL_AT = 0.7                 # (the ring's level stands at this share of its stretches' ground: more fill, fewer steps up)
DIP_MIN = 48


def _low_wall(W):
    """A low wall of piers (ROUND, 'low': True): it follows the ground as it lies."""
    return ((W.get('kit') or {}).get('round') or {}).get('low') is True


def fill_ground(db, W, skip=(), keep=()):
    """The ground under the wall's raised stretches (grounded's W['fill']) filled up to their feet: a stretch whose ground
    had been cut to the ring's level stood lower than the walls either side, a dip in the walk with a trench under it
    (the user's Estmorevale, 2026-11-03: "a couple spots where the walls depress down"). The cells changed."""
    segs = W.pop('fill', None) or []
    return _shape_ground(db, segs, skip, 0.0, FILL_MAX, keep) if segs else 0


SHOWN_GIVE = 16                # (a length counts as sunk or hanging past this)


def show_ground(db, W, skip=(), keep=()):
    """Once the wall stands and the town's ground is fitted: no straight length sunk to its top, none hanging. The ground
    along a length that stands higher than the length may show (its top less SHOW, SHOW_SHARE of its height) is cut back
    to that, within CUT_TOL; the ground under a length whose foot is in the air is filled up to it, within FILL_MAX;
    both fading into the land round them and kept off the town's buildings (keep), as the wall's other ground work.
    On a steep site the wall's levels and the fills that follow them left lengths buried and lengths hanging: 12 runs of
    a Dunmer town's wall on a mountainside, up to 900 long, the check of 2026-11-13. (cells changed, lengths cut back,
    lengths filled under)."""
    if _low_wall(W):
        return 0, 0, 0
    cut, fill = [], []
    memo = {}
    for p in W.get('pieces') or ():
        q = p.get('pose')
        if q is None or p.get('kind') in ('gate', 'tower', 'stair', 'bigtower') or GATEISH.search(p['id']) or TOWERISH.search(p['id']):
            continue
        if p.get('nofill'):
            continue                                   # (by a castle's wall: the ground there is the castle's, FORT_NOFILL)
        cs, b = _box(db, p['id'], q, memo)             # (as it stands now: its box is not kept with the piece)
        if not cs or len(cs) < 4 or not b:
            continue
        e0 = math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e1 = math.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        mid = lambda u, v: ((u[0] + v[0]) / 2.0, (u[1] + v[1]) / 2.0)
        a, bb = (mid(cs[0], cs[3]), mid(cs[1], cs[2])) if e0 >= e1 else (mid(cs[0], cs[1]), mid(cs[3], cs[2]))
        zs = [mapdata.terrain_z(db, a[0] + (bb[0] - a[0]) * t, a[1] + (bb[1] - a[1]) * t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        if any(z is None for z in zs):
            continue
        h = b[5] - b[2]
        show = q.z + b[5] - max(SHOW, SHOW_SHARE * h)
        foot = q.z + b[2] + SINK
        if max(zs) > show + SHOWN_GIVE:
            cut.append((a, bb, show))
        if min(zs) < foot - SHOWN_GIVE and foot < show:
            fill.append((a, bb, foot))
    n = 0
    if cut:
        n += _shape_ground(db, cut, skip, CUT_TOL, 0.0, keep)
    if fill:
        n += _shape_ground(db, fill, skip, 0.0, FILL_MAX, keep)
    return n, len(cut), len(fill)


INNER_OFFS = (320.0, 800.0)    # (the ground inside the wall brought to each stretch's foot level: level in full this far in from
                               # the wall's line (LEVEL_R round each), fading inward beyond; raised within FILL_MAX, cut within
                               # LEVEL_TOL: a wall "built on a rampart of earth that could just be more level ground", the
                               # user's Firuhn 2026-11-07, its houses dug in below the band of fill under the wall)


def inner_ground(db, W, skip=(), keep=()):
    """The ground inside the wall levelled up to each stretch's foot: a band INNER_OFFS deep in from the wall's line at
    the foot's level (the ground under the piece's corners once the fill has brought it up), raised within FILL_MAX and
    cut within LEVEL_TOL, fading into the town's ground beyond; the buildings' and the streets' ground (keep) left to
    them. Gates and towers set no level. The cells changed."""
    outline = W.get('outline') or []
    if len(outline) < 3 or _low_wall(W):
        return 0
    cx = sum(p_[0] for p_ in outline) / len(outline)
    cy = sum(p_[1] for p_ in outline) / len(outline)
    segs = []
    for p in W.get('pieces') or ():
        cs = p.get('corners')
        if not cs or len(cs) < 4 or p.get('kind') in ('gate', 'tower', 'stair', 'step') or GATEISH.search(p['id']) or TOWERISH.search(p['id']):
            continue
        zs = [mapdata.terrain_z(db, x, y) for x, y in cs]
        if any(z is None for z in zs):
            continue
        zs.sort()
        level = (zs[1] + zs[2]) / 2.0
        e0 = math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e1 = math.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        if e0 >= e1:
            ux, uy, h = (cs[1][0] - cs[0][0]) / (e0 or 1.0), (cs[1][1] - cs[0][1]) / (e0 or 1.0), e0 / 2.0
        else:
            ux, uy, h = (cs[2][0] - cs[1][0]) / (e1 or 1.0), (cs[2][1] - cs[1][1]) / (e1 or 1.0), e1 / 2.0
        h = max(0.0, h - FILL_IN)
        mx, my = sum(c[0] for c in cs) / 4.0, sum(c[1] for c in cs) / 4.0
        nx, ny = -uy, ux
        if (cx - mx) * nx + (cy - my) * ny < 0:
            nx, ny = -nx, -ny
        for off in INNER_OFFS:
            segs.append(((mx - h * ux + nx * off, my - h * uy + ny * off), (mx + h * ux + nx * off, my + h * uy + ny * off), level))
    return _shape_ground(db, segs, skip, LEVEL_TOL, FILL_MAX, keep, grade=INNER_GRADE, mix=True) if segs else 0


GATE_GRADE = math.tan(math.radians(16))     # (the way through a gate climbs at most this steeply, the game's gate roads at 8-15)
GATE_RAMP = 1024                             # (graded this far in and out of the arch)
GATE_HALF = 288                              # (level across this much either side of the gate's axis)


def gate_ramps(db, W, skip=(), keep=()):
    """(Not called yet: on the lab's Sketh it cut a 34-degree dip into the south gate, whose way stood at 17 degrees
    before, the arch piece's foot read 480 too low; the two steep "gates" that asked for it were corners of the wall.
    To be given each gate piece's true foot before it is used, 2026-11-07.)
    The way through each gate graded: the ground along the gate's axis GATE_RAMP in and out, never steeper than
    GATE_GRADE from the wall's foot there, level across the opening and fading sideways; the ground under the wall's
    pieces and inside keep's footprints (building_guard) left as it is. The gates are where the wall's gate roads end
    (W['roads'], each run to its opening's middle: an Imperial opening is a gap between two towers, no piece of its own).
    (Inside a town's west gate the ground fell 440 over 500 at 37 to 59 degrees, and the checker slid down the banks by
    the wall; the lab's Sketh walked 2026-11-06.) The cells changed."""
    if not W or not W.get('pieces') or not W.get('roads'):
        return 0
    memo = {}
    gates = []
    for r in W['roads']:
        if len(r) < 2 or not r[0] or not r[1]:
            continue
        (bx, by), (gx, gy) = r[0], r[1]
        if any(math.hypot(gx - o[0], gy - o[1]) < 300 for o in gates):
            continue
        d = _unit(bx - gx, by - gy)                       # (the road runs from inside the town to the gate: in is towards it)
        if d == (0.0, 0.0):
            continue
        gates.append((gx, gy, d))
    segs = []
    for gx, gy, (nx, ny) in gates:
        feet = []
        for p in W['pieces']:
            q = p['pose']
            if math.hypot(q.x - gx, q.y - gy) > 900:
                continue
            _cs, b = _box(db, p['id'], q, memo)
            if b:
                feet.append(q.z + b[2] + SINK + 8)
        if not feet:
            continue
        foot = sum(feet) / len(feet)
        ax, ay = -ny, nx
        for s_ in range(-GATE_RAMP, GATE_RAMP + 1, 128):
            x, y = gx + nx * s_, gy + ny * s_
            z = mapdata.terrain_z(db, x, y)
            if z is None:
                continue
            lim = GATE_GRADE * abs(s_)
            t = foot + max(-lim, min(lim, z - foot))
            segs.append(((x - ax * GATE_HALF, y - ay * GATE_HALF), (x + ax * GATE_HALF, y + ay * GATE_HALF), t))
    if not segs:
        return 0
    # (the wall's pieces near a gate keep their ground: a ramp cut under a tower's foot would open the wall)
    guard = list(keep)
    for p in W['pieces']:
        q = p['pose']
        if not any(math.hypot(q.x - g[0], q.y - g[1]) < GATE_RAMP + GATE_HALF + LEVEL_R + LEVEL_BLEND_MAX for g in gates):
            continue
        cs_, _b = _box(db, p['id'], q, memo)
        if cs_:
            guard.append(cs_)
    return _shape_ground(db, segs, skip, FILL_MAX, FILL_MAX, guard)


WALL_KEEP = 160                # (a standing wall piece's footprint, this much wider, is kept from another make's ground work)


def wall_guard(db, outline, reach=2000.0, mine=()):
    """The footprints of the wall pieces already standing within reach of an outline's box (another make's: a castle's
    wall beside a town, a town's beside a castle), each WALL_KEEP wider, for level_ground and fill_ground to keep off.
    mine: ref keys of this make's own pieces, left out. (A town's level_ground raised the wall line it shared with the
    castle built before it by 416, and 14 of the castle's pieces lay 480-720 deep; the user's Sketh, lab w109,
    2026-11-07.) [[(x, y) x4]]"""
    if not outline:
        return []
    try:
        K = kits(db)
        models = {m.lower() for k in K.values() for m in k.get('models') or ()}
    except Exception:
        models = set()
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    out, memo = [], {}
    mine = set(mine or ())
    for gx in range(int(math.floor((min(xs) - reach) / 8192.0)), int(math.floor((max(xs) + reach) / 8192.0)) + 1):
        for gy in range(int(math.floor((min(ys) - reach) / 8192.0)), int(math.floor((max(ys) + reach) / 8192.0)) + 1):
            try:
                m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
            except Exception:
                continue
            for r in m.get('refs') or ():
                low = r['id'].lower()
                if r.get('k') in mine or r['type'] != 'STAT' or not (low in models or WALLISH.search(low)) or GATEISH.search(low):
                    continue
                p = r['p']
                if not (min(xs) - reach <= p[0] <= max(xs) + reach and min(ys) - reach <= p[1] <= max(ys) + reach):
                    continue
                cs_ = _box(db, r['id'], Pose(p[0], p[1], p[2], p[5], r['id']), memo)[0]
                if cs_:
                    cx, cy = sum(c[0] for c in cs_) / 4.0, sum(c[1] for c in cs_) / 4.0
                    out.append([(x + (x - cx) / (math.hypot(x - cx, y - cy) or 1) * WALL_KEEP, y + (y - cy) / (math.hypot(x - cx, y - cy) or 1) * WALL_KEEP) for x, y in cs_])
    return out


def building_guard(db, outline, reach=2000.0):
    """The footprints of the buildings a town built (project.town_parts) within reach of an outline's box, each a step
    wider: ground shaping round a castle keeps its hands off them. (The west castle's fill buried a town house's entrance
    327 deep beside its wall, the user's Sketh 2026-11-06.) [[(x, y) x4]]"""
    tp = getattr(db.project, 'town_parts', None) or {}
    if not tp or not outline:
        return []
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    out, memo = [], {}
    for gx in range(int(math.floor((min(xs) - reach) / 8192.0)), int(math.floor((max(xs) + reach) / 8192.0)) + 1):
        for gy in range(int(math.floor((min(ys) - reach) / 8192.0)), int(math.floor((max(ys) + reach) / 8192.0)) + 1):
            try:
                m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
            except Exception:
                continue
            for r in m.get('refs') or ():
                if r.get('k') not in tp or re.search(r'_win|window|chimney|awning|sign|banner|marker', r['id'], re.I):
                    continue
                p = r['p']
                if not (min(xs) - reach <= p[0] <= max(xs) + reach and min(ys) - reach <= p[1] <= max(ys) + reach):
                    continue
                if r['type'] == 'DOOR':
                    # (and the ground before each door: a door's front buried 493 under a town wall's fill, 2026-11-06)
                    out.append([(p[0] - 260, p[1] - 260), (p[0] + 260, p[1] - 260), (p[0] + 260, p[1] + 260), (p[0] - 260, p[1] + 260)])
                    continue
                cs_ = _box(db, r['id'], Pose(p[0], p[1], p[2], p[5], r['id']), memo)[0]
                if cs_:
                    cx, cy = sum(c[0] for c in cs_) / 4.0, sum(c[1] for c in cs_) / 4.0
                    out.append([(x + (x - cx) / (math.hypot(x - cx, y - cy) or 1) * 128, y + (y - cy) / (math.hypot(x - cx, y - cy) or 1) * 128) for x, y in cs_])
    return out


def _in_poly(r, x, y):
    sgn = None
    for i in range(len(r)):
        x1, y1 = r[i]
        x2, y2 = r[(i + 1) % len(r)]
        cr = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if abs(cr) < 1e-9:
            continue
        if sgn is None:
            sgn = cr > 0
        elif (cr > 0) != sgn:
            return False
    return True


KEEP_GRADE = 0.8               # (beside a kept footprint the ground is moved by this times the distance from it at most: the
                               # fill stopped dead at a house's plot and at a street's edge, a pit 576 deep round a tavern by
                               # the wall and a cliff along every street near it, the lab's Redoran hill town 2026-11-10)


def _keep_dist(k_, x, y, far):
    """How far (x, y) is outside the footprint k_ (far when farther than that)."""
    best = far
    n = len(k_)
    for i in range(n):
        ax, ay = k_[i][0], k_[i][1]
        bx, by = k_[(i + 1) % n][0], k_[(i + 1) % n][1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        d = math.hypot(x - (ax + dx * t), y - (ay + dy * t))
        if d < best:
            best = d
    return best


INNER_GRADE = 0.5              # (the ground inside the wall: gentler still beside the houses and streets, and where two stretches
                               # of the wall stand at different levels their levels run into each other: each stretch's own
                               # level 800 in made terraces with a cliff between them at every step of the wall)


def _shape_ground(db, segs, skip, cut_tol, raise_tol, keep=(), grade=KEEP_GRADE, mix=False):
    """The ground along each ((x0, y0), (x1, y1), level) evened towards its level, cut by at most cut_tol and raised by at
    most raise_tol, fading back into the land round it (LEVEL_R, LEVEL_BLEND); the ground inside keep's footprints
    (building_guard) left as it is. The cells changed."""
    import landscape
    if not segs:
        return 0
    reach = LEVEL_R + LEVEL_BLEND_MAX
    xs = [c[0] for s_ in segs for c in s_[:2]]
    ys = [c[1] for s_ in segs for c in s_[:2]]
    G = landscape.CELL
    step = G / (landscape.N - 1.0)

    def dist(px, py, a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + dx * t), py - (ay + dy * t))
    new_h, before = {}, {}
    kbox = [(min(c[0] for c in k_), min(c[1] for c in k_), max(c[0] for c in k_), max(c[1] for c in k_), k_) for k_ in keep if len(k_) >= 3]
    for gx in range(int(math.floor((min(xs) - reach) / G)), int(math.floor((max(xs) + reach) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - reach) / G)), int(math.floor((max(ys) + reach) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(landscape.N):
                for i in range(landscape.N):
                    x, y = gx * G + i * step, gy * G + j * step
                    best = None
                    n = j * landscape.N + i
                    z = h[n]
                    sw = st = 0.0
                    for a, b, t in segs:
                        d = dist(x, y, a, b)
                        if d >= reach:
                            continue
                        blend = max(LEVEL_BLEND, min(LEVEL_BLEND_MAX, LEVEL_FADE * abs(max(z - cut_tol, min(z + raise_tol, t)) - z)))
                        if d >= LEVEL_R + blend:
                            continue
                        w = 1.0 if d <= LEVEL_R else 0.5 + 0.5 * math.cos(math.pi * (d - LEVEL_R) / blend)
                        # (two in full at one point: the nearer one's level, not the first listed: under a wall's end,
                        # the neighbouring higher stretch's fill buried it, the lab's Firuhn 2026-11-07)
                        if best is None or (w, -d) > (best[0], -best[2]):
                            best = (w, t, d)
                        if mix:
                            m_ = 1.0 / (d + 64.0) ** 3
                            sw += m_
                            st += m_ * t
                    if not best:
                        continue
                    if mix:
                        best = (best[0], st / sw, best[2])
                    want = max(z - cut_tol, min(z + raise_tol, best[1]))
                    nz = z + best[0] * (want - z)
                    if _KEEP_SEA[0] and z < SEA_KEEP and nz > z:
                        continue                         # (the harbour's floor stays the sea's)
                    if abs(nz - z) >= 1:
                        if keep and any(_in_poly(k_, x, y) for k_ in keep):
                            continue                     # (a town building's own ground: left to it)
                        far = abs(nz - z) / grade
                        for kx0, ky0, kx1, ky1, k_ in kbox:
                            if kx0 - far < x < kx1 + far and ky0 - far < y < ky1 + far:
                                far = _keep_dist(k_, x, y, far)
                        if far * grade < abs(nz - z):
                            nz = z + math.copysign(far * grade, nz - z)
                            if abs(nz - z) < 1:
                                continue
                        h[n] = nz
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


SHOW = 200                     # a wall stands at least this much of its height out of the highest ground along its run
SHOW_SHARE = 0.64              # and at least this share of it: the game's straights stand 180-460 over the ground (0.64-0.94
                               # of ex_imp_wall_01 out); at SHOW alone a run down a slope was buried to 200 at its high end,
                               # "far too short ... a lot of sunken wall", the user's Chillmorrow, test4; at 0.5 a stretch on a
                               # hill stood buried to 460, showing half: the game's least, 0.64, 2026-11-07)
def grounded(db, W):
    """The wall set on the ground the game's way: every straight run between corners one level, as the game's own town walls
    stand (120 of 120 neighbouring Imperial straights level, lab jwallz2), sunk so its foot is SINK under the lowest
    ground along it and at least SHOW of it stands out of the highest; a run on ground too steep for one level is cut
    into level stretches. Corners take the level of the runs either side when that buries their foot. Pieces over open
    water or on no land are left out, as faults. W changed. (Each piece set on the ground under it alone made a jagged
    wall at a dozen heights, the user's first town, 2026-10-31.)"""
    if W.get('palisade'):
        return _palisade_grounded(db, W)
    memo = {}
    keep, wet = [], 0
    for p in W['pieces']:
        cs, b = _box(db, p['id'], p['pose'], memo)
        if not cs:
            continue
        pts = cs + [((cs[i][0] + cs[(i + 1) % 4][0]) / 2, (cs[i][1] + cs[(i + 1) % 4][1]) / 2) for i in range(4)]
        pts.append((p['pose'].x, p['pose'].y))
        gz = [mapdata.terrain_z(db, x, y) for x, y in pts]
        zs = [z for z in gz if z is not None]
        if not zs or (max(zs) < 0 and not p.get('sea')):
            wet += 1
            continue
        # (its low ground the third lowest of its nine: a corner over a cliff's edge or the shore no longer drags the
        # whole run down to the sea floor, its foot showing a little there as the user set their own, Chillmorrow test4)
        zs.sort()
        p['corners'], p['_g'], p['_b'] = cs, (zs[min(2, len(zs) - 1)], zs[-1]), b
        if p.get('lift'):
            # (a gate that stands higher than the lengths beside it, Anvil's raised arch: levelled as if its origin
            # were theirs, so the ring's level answers to the gate's ground too)
            p['_b'] = list(b[:2]) + [b[2] + p['lift']] + list(b[3:5]) + [b[5] + p['lift']]
        # (a piece along a cliff's edge or a steep bank, the ground under its own footprint differing by more than
        # CLIFF_SPREAD: its foot is measured along its crest, the middle and the two end midpoints, not at the corner
        # over the drop, and no bank of earth is raised under it (_fill_under): the cliff is the wall's foot. The
        # user's Firuhn, 2026-11-07: "integrate the cliffs themselves into the fortress structure, in order to keep
        # the walls level")
        if zs[-1] - zs[0] > CLIFF_SPREAD:
            ends = (5, 7) if (W.get('kit') or {}).get('axis', 0) == 0 else (4, 6)
            crest = [z for z in [gz[8]] + [gz[k] for k in ends] if z is not None]
            if crest:
                p['_cliff'] = True
                p['_g'] = (min(crest), zs[-1])
        keep.append(p)
    gs_ = sorted(p['_g'][0] for p in keep)
    _FILL[0] = HILL_FILL if gs_ and gs_[int(len(gs_) * 0.9)] - gs_[int(len(gs_) * 0.1)] > HILL_RELIEF else FILL_MAX
    def span(ps):
        # (the levels that bury every foot and show enough of every top: origin z in [lo, hi])
        lo = max(p['_g'][1] + max(SHOW, SHOW_SHARE * (p['_b'][5] - p['_b'][2])) - p['_b'][5] for p in ps)
        hi = min(p['_g'][0] - SINK - p['_b'][2] for p in ps)
        return lo, hi
    def level(ps):
        lo, hi = span(ps)
        z = max(lo, min(hi, sum(p['_g'][0] + p['_g'][1] for p in ps) / (2.0 * len(ps)) + (W.get('rise') if W.get('rise') is not None else 208)))
        for p in ps:
            p['pose'].z = min(z, p['_g'][0] - SINK - p['_b'][2])
    tower_id = next((t for v in ((W.get('kit') or {}).get('corner_towers') or {}).values() for t, _e in v), None)
    AN = ANCHOR.get(W.get('family')) if db is not None and all(db.resolve_id(v) is not None for v in (ANCHOR.get(W.get('family')) or {}).values() if isinstance(v, str)) else None
    stacks = []                                  # (the round towers stacked where the wall changes level by more than a wall tower hides)
    # the levels set round the whole wall in order, corner by side by corner: each stretch as long as one level can serve
    # it, the next stretch starting at a tower so the step hides in it. (A level per side and each corner set to suit one
    # side left a step at every corner between sides at different heights, 36 joins up to 889 units apart on the user's
    # island, lab jjoins)
    straight = (W.get('kit') or {}).get('straight')
    n = max([p.get('corner', -1) for p in keep] + [p.get('run', -1) for p in keep] + [-1]) + 1
    order = []
    for k in range(n):
        order += [p for p in keep if p.get('corner') == k]
        order += [p for p in keep if p.get('run') == k]
    order += [p for p in keep if 'corner' not in p and 'run' not in p and 'dz' not in p]
    big = [p for p in keep if 'dz' in p]

    def towered(i):
        # (the step between order[i - 1] and order[i]: the HIGHER of the two becomes the tower when it is a straight, so
        # the lower wall runs into the tower's side; the tower on the low side left the high wall's open end standing
        # over it, the user's Tessellated Shores, 2026-11-01. The game's Imperial walls step at towers, 28 of 33
        # towers level and the rest steps, never straight to straight (2 of 141), lab sj1/sj2. A corner or a gate
        # arch on the high side closes the step itself)
        a, b = order[i - 1] if i > 0 else order[-1], order[i]
        d_ = abs((a['pose'].z + a['_b'][5]) - (b['pose'].z + b['_b'][5]))
        if d_ < 16:
            return                                       # (no step left to hide: the stretches came out level)
        if AN and d_ > STEP_HIDE:
            # (more than a wall tower hides: a round tower stacked at the joint spans the whole change, the two
            # stretches running into its sides at their own heights, as the user set Firuhn's by hand, 2026-11-07)
            # (not where a guard tower or the keep already stands at the joint: set from the higher wall and sunk to
            # its ground, it spans the change itself)
            stacks.extend(_stack_anchor(db, a, b, AN, W, avoid=[(p['pose'].x, p['pose'].y) for p in big if p.get('host') is None]))
            return
        hp = max((a, b), key=lambda p: p['pose'].z + p['_b'][5])
        if any('tower' in p['id'].lower() and p['pose'].z + p['_b'][5] >= hp['pose'].z + hp['_b'][5] - 16 for p in (a, b)):
            return
        if W.get('evened') is not None:
            return                                       # (the stairs climbed it, _even_out: no length raised over its neighbour)
        if tower_id and hp['id'] == straight:
            top = hp['pose'].z + hp['_b'][5]
            hp['id'] = hp['pose'].id = tower_id
            hp['kind'] = 'tower'
            nb_ = _box(db, tower_id, hp['pose'], memo)[1]
            if nb_:
                hp['_b'] = nb_
                # (its top at least the wall's, its foot under its own ground)
                hp['pose'].z = min(max(hp['pose'].z, top - nb_[5]), hp['_g'][0] - SINK - nb_[2]) if nb_[5] - nb_[2] > 0 else hp['pose'].z
    if AN and tower_id:
        # (the hill rule: as few level stretches round the ring as the ground allows, each as long as it can be with
        # the ground filled under its low end, the change of level between two at an anchor: _plan_levels)
        segs, starts = _plan_levels(order, W, keep)
    else:
        seg, starts, segs = [], [], []
        for i, p in enumerate(order):
            if seg:
                lo, hi = span(seg + [p])
                if lo > hi:
                    level(seg)
                    segs.append(seg)
                    seg = []
                    starts.append(i)
            seg.append(p)
        if seg:
            level(seg)
            segs.append(seg)
        _one_level(segs, W, span, keep)
    _no_dips(segs, W)
    if not AN:
        _cap_steps(segs, W)
    W['stretches'] = [[id(p['pose']) for p in seg] for seg in segs]
    St = STEP_PIECES.get(W.get('family'))
    if St and straight:
        for k in range(1, len(segs)):
            _stepped(db, segs[k - 1], segs[k], St, straight, span, memo, fill=_FILL[0] if AN else 0.0)
    if St and straight and St.get('turn'):
        W['evened'] = _even_out(db, segs, St, straight, (W.get('kit') or {}).get('L') or 512.0,
                                [(p['pose'].x, p['pose'].y) for p in big if p.get('host') is None], memo, bool(AN))
        _stair_to_fort(db, segs, St, straight, memo)
    for i in starts:
        towered(i)
    # (the ground brought up to every stretch's foot across the wall's width, not only under the raised ones: a level
    # stretch sunk under the lowest ground along its line still hung over the slope falling away outside it, 60 of a
    # town's 199 pieces with a corner over nothing in the game, the lab's Sketh walked 2026-11-06. fill_ground raises
    # only, within FILL_MAX, and fades out. After the ramps: each piece at its own height; not under a cliff piece on
    # its crest)
    fill_all = W.setdefault('fill', [])
    for seg in segs:
        _fill_under(fill_all, seg, None, (W.get('kit') or {}).get('axis', 0))
    # (round the loop: where the last stretch meets the first at another level, a tower there too)
    if order and starts and abs(order[-1]['pose'].z - order[0]['pose'].z) > 48 and \
            abs((order[-1].get('run') if order[-1].get('run') is not None else order[-1].get('corner', 0)) - (order[0].get('run') if order[0].get('run') is not None else order[0].get('corner', 0))) < 100:
        towered(0)                                   # (not where a castle's inner wall follows its outer in the order)
    if W.get('evened') is not None:
        # (and whatever change of level is left with nothing spanning it: past STEP_HIDE the round tower stacked at
        # the joint, wherever in the wall it stands. The stacks above come only where one planned stretch follows
        # another in the order; a 986 step two lengths from a guard tower stood bare, the lab's mountain town.
        # A smaller one no stair could take is told as a fault)
        L_ = (W.get('kit') or {}).get('L') or 512.0
        have = [(p['pose'].x, p['pose'].y) for p in big if p.get('host') is None] + [(a_[0], a_[1]) for a_ in W.get('anchors') or ()]
        lens = [p for p in order if p.get('kind') != 'step']
        bare = 0
        for i_, a_ in enumerate(lens):
            for b_ in lens[i_ + 1:]:
                d_ = abs(a_['pose'].z - b_['pose'].z)
                if d_ < 16 or not _beside(a_, b_, L_, straight):
                    continue
                mx_, my_ = (a_['pose'].x + b_['pose'].x) / 2.0, (a_['pose'].y + b_['pose'].y) / 2.0
                if any(math.hypot(t_[0] - mx_, t_[1] - my_) <= EVEN_TOWER * L_ for t_ in have):
                    continue
                if AN and d_ > STEP_HIDE:
                    stacks.extend(_stack_anchor(db, a_, b_, AN, W))
                    have.append((mx_, my_))
                else:
                    bare += 1
        if bare:
            W['faults'].append('%d changes of level in the wall that no stair or tower could take' % bare)
    # (the towers and the keep at the level of the wall running into them, the highest where two levels meet so the
    # step hides in the tower; sunk further where the ground under them lies lower)
    hosts = {id(p['pose']) for p in keep if p.get('kind') != 'step'}
    for p in big:
        q = p['pose']
        if p.get('host') is not None:
            # (a stair against its length: at that length's level, gone with it when it was left out, or when the
            # length became a wall stair itself)
            if id(p['host']) not in hosts:
                p['_gone'] = True
                continue
            q.z = p['host'].z + p['dz']
            continue
        near = sorted(order, key=lambda o: math.hypot(o['pose'].x - q.x, o['pose'].y - q.y))[:2]
        wz = max(o['pose'].z for o in near) if near else p['_g'][0] + 208
        gc = mapdata.terrain_z(db, q.x, q.y)
        # (a wall of round towers: its towers and gates at the lengths' own level, as Anvil's all are)
        q.z = wz + p['dz'] if gc is None or (W.get('kit') or {}).get('round') else min(wz + p['dz'], gc - SINK - p['_b'][2])
        if p.get('sea') and (W.get('kit') or {}).get('round'):
            q.z = min(wz, W['kit']['round'].get('sea_z', wz)) + p['dz']
    for p in keep:
        if p.get('lift') and not p.get('_lifted'):
            p['pose'].z += p['lift']                     # (the raised gate at its own height, the wall's set)
            p['_lifted'] = True
    keep = [p for p in keep if not p.pop('_gone', False)]
    for p in keep:
        for k_ in ('_g', '_b', '_cliff'):
            p.pop(k_, None)
    W['pieces'] = keep + stacks
    if wet:
        W['faults'].append('%d pieces over water left out' % wet)
    return W


FILL_IN = 48                   # (a piece's fill line stops this short of its ends: the next piece's own fill takes over at the joint)
HOLD = -1e9                    # (a fill line's level that raises nothing: the ground under it kept from the neighbours' fill)


def _fill_under(fill, seg, z=None, axis=0):
    """The ground wanted under each piece of a stretch set at z (None: each piece's own height, after the ramps): its
    own foot, along a short line down the piece's own length (a line from the stretch's first piece to its last cut
    the corners, and the pieces round them stood in the air; a point at each piece's middle let the neighbour's fill
    win under the piece's ends). A cliff piece whose foot sits on its crest gets no bank raised under its drop: the
    cliff is its foot."""
    for p in seg:
        q = p['pose']
        zz = q.z if z is None else z
        b = p['_b']
        on_crest = p.get('_cliff') and p['_g'][0] + CLIFF_SIT >= zz + b[2]
        lo_, hi_ = (b[0], b[3]) if axis == 0 else (b[1], b[4])
        m, h = (lo_ + hi_) / 2.0, max(0.0, (hi_ - lo_) / 2.0 - FILL_IN)
        c, s_ = math.cos(q.rz), math.sin(q.rz)
        if axis == 0:
            a_, b_ = (q.x + (m - h) * c, q.y - (m - h) * s_), (q.x + (m + h) * c, q.y - (m + h) * s_)
        else:
            a_, b_ = (q.x + (m - h) * s_, q.y + (m - h) * c), (q.x + (m + h) * s_, q.y + (m + h) * c)
        # (a cliff piece on its crest: its line holds the ground as it is (a level nothing can be raised to), so the
        # neighbouring stretch's bank stops at the joint instead of burying it)
        fill.append((a_, b_, HOLD if on_crest else zz + b[2] + SINK + 8))


def _one_level(segs, W, span, keep):
    """Every level stretch at the ring's one level where it can be: a stretch whose ground lies under that level floats
    at it and gets its ground filled to its foot (W['fill'], up to FILL_MAX); one whose ground stands too high to show
    the wall steps up, as the game's walls step at a hill. Before, a stretch took its own ground's level, so a wall on
    a slope went down it in steps (the user's Fort Estmoth, 2026-11-03: "bring the terrain up to meet it")."""
    if not segs:
        return
    gs = sorted(p['_g'][0] for p in keep)
    want = gs[int(len(gs) * LEVEL_AT)] + 208               # (level()'s own figure, for the whole ring)
    fill = W.setdefault('fill', [])
    ax = (W.get('kit') or {}).get('axis', 0)
    rise = (STEP_PIECES.get(W.get('family')) or {}).get('rise') or HILL_STEP
    for seg in segs:
        lo, hi = span(seg)
        if want < lo:
            # (a hill: the wall must show over the ground. Its level a whole number of rises over the ring's, so the
            # climb goes in steps a tower hides and the ground is filled under the stretch's low end, not a notch
            # at every short stretch: a castle's north wall took 13 steps of 7-66 over ten pieces, the user's
            # Skethwall 2026-11-07, "they dip down when it looks easy to make them level")
            z = want + math.ceil((lo - want) / rise - 1e-6) * rise
            if z - hi > FILL_MAX:
                z = lo                                  # (too much fill under its low end: its own level)
        elif want <= hi:
            z = want
        elif want - hi <= FILL_MAX:
            z = want                                    # (ground under the level: filled up to the foot)
        else:
            continue                                    # (too deep to fill: its own level, as before)
        if abs(z - seg[0]['pose'].z) < 1:
            continue
        if z > hi and any(p.get('nofill') for p in seg):
            continue                                    # (by a castle's wall, no fill: its own level)
        for p in seg:
            p['pose'].z = z
        if z > hi:
            _fill_under(fill, seg, z, ax)


CLIFF_SPREAD = 512             # (the ground under one piece's footprint differing by more than this: a cliff piece, its foot
                               # measured along its crest; half the Imperial wall's 921 height)
CLIFF_SIT = 64                 # (a cliff piece's foot within this over its crest sits on it: no bank raised under it)
GATE_FILL = 256                # (the ground under a gate raised this much at most: a gate on a bank of fill had the road climb
                               # it and drop again inside, the lab's Firuhn gate 572 up, 2026-11-07; the game's gates stand at
                               # their ground on the low side)


HILL_FILL = 512                # (a wall round a mountainside, HILL_RELIEF: a stretch
                               # stands on this much fill at most. With the whole FILL_MAX the downhill side stood on a bank
                               # 700 to 1,017 high dropping 400 to 640 within 900 outside, the lab's Gold Coast hill town,
                               # 2026-11-10; the wall steps down at more towers and stairs instead)
_FILL = [FILL_MAX]


def _allow(p):
    """How much fill a wall piece may stand on."""
    if p.get('nofill'):
        return 0.0                               # (by a castle's wall: the ground there is the castle's, FORT_NOFILL)
    return GATE_FILL if p.get('kind') == 'gate' else _FILL[0]


def _plan_levels(order, W, keep):
    """The ring cut into as few level stretches as the ground allows, each as long as it can be: a stretch's one level
    must show every piece (SHOW, SHOW_SHARE) and bury every foot or have the ground filled up to it within FILL_MAX;
    between two stretches the level changes whole, at an anchor (towered: a wall tower, or a stacked round tower for
    more than STEP_HIDE), by preference where a tower, gate or corner already stands. The fewest stretches first, then
    the fewest changes in the open, then the least fill. Each stretch at the ring's level (LEVEL_AT) where its ground
    allows, a whole number of rises over it on a hill, its own level where the ring's lies too deep to fill. (The
    stretch-by-stretch rule cut a wall down a mountainside into a staircase: ex_imp_wall_01 at twelve heights, 838 to
    5375, a step of 256 every length or two, the user's Firuhn, 2026-11-07: "wall sections stay level along the
    crest; the whole change of level happens at a tower, a keep or a stair that spans it".) (segs, starts)."""
    n = len(order)
    if not n:
        return [], []
    gs = sorted(p['_g'][0] for p in keep)
    want = gs[int(len(gs) * LEVEL_AT)] + 208               # (level()'s own figure, for the whole ring)
    rise = (STEP_PIECES.get(W.get('family')) or {}).get('rise') or HILL_STEP
    straight = (W.get('kit') or {}).get('straight')
    LH = [(p['_g'][1] + max(SHOW, SHOW_SHARE * (p['_b'][5] - p['_b'][2])) - p['_b'][5], p['_g'][0] - SINK - p['_b'][2],
           p['_g'][0] - SINK - p['_b'][2] + _allow(p)) for p in order]        # (lo, hi, hi with its fill)
    anchorish = [p['id'] != straight for p in order]

    def level_for(lo, hi, cap, ps):
        if want < lo:
            z = want + math.ceil((lo - want) / rise - 1e-6) * rise
            return z if z <= cap else min(lo, cap)          # (a piece no level serves: buried, not floating)
        if want <= cap:
            return want
        # (ground too low to fill up to the ring's level: a whole number of rises under it where one serves, so
        # the change is one the stairs climb; a level of its own stood at any height and no stair fitted it, the
        # length beside it raised as a wall tower instead, the user's "uneven wall sections", 2026-11-13)
        z = want - math.ceil((want - cap) / rise - 1e-6) * rise
        if z >= lo - STEP_GIVE:
            return z
        return max(lo, min(hi, sum(p['_g'][0] + p['_g'][1] for p in ps) / (2.0 * len(ps)) + 208))
    NONE = (1 << 30, 0, 0.0)
    best = [NONE] * (n + 1)
    best[0] = (0, 0, 0.0)
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        lo_max, hi_min, cap_min = -1e18, 1e18, 1e18
        for i in range(j, 0, -1):
            lo, hi, cap = LH[i - 1]
            lo_max, hi_min, cap_min = max(lo_max, lo), min(hi_min, hi), min(cap_min, cap)
            if lo_max > cap_min and i < j:
                break                                   # (no one level serves these: nor any longer stretch)
            if best[i - 1][0] >= (1 << 30):
                continue
            pen = 0 if (i == 1 or anchorish[i - 2] or anchorish[i - 1]) else 1
            z = level_for(lo_max, hi_min, cap_min, order[i - 1:j])
            f = sum(max(0.0, min(FILL_MAX, z - h)) for _l, h, _c in LH[i - 1:j])
            cand = (best[i - 1][0] + 1, best[i - 1][1] + pen, best[i - 1][2] + f)
            if cand < best[j]:
                best[j] = cand
                back[j] = i - 1
    segs, j = [], n
    while j > 0:
        i = back[j]
        segs.append(order[i:j])
        j = i
    segs.reverse()
    starts, pos = [], 0
    for seg in segs:
        lo = max(LH[pos + k][0] for k in range(len(seg)))
        hi = min(LH[pos + k][1] for k in range(len(seg)))
        cap = min(LH[pos + k][2] for k in range(len(seg)))
        z = level_for(lo, hi, cap, seg)
        for p in seg:
            p['pose'].z = z
        if pos:
            starts.append(pos)
        pos += len(seg)
    return segs, starts


# the round tower stacked where a wall changes level by more than a wall tower hides (STEP_HIDE): the game's own wall
# tower stack (castle.TOWER), its crown 384 over the higher wall's origin, light sections every 256 down to the dirt,
# the darker section at the dirt, the flared base, dark foundations down to the low ground. The two stretches run into
# its sides at their own heights (the Ebon Tower's keeps and towers in the wall line; the user's Firuhn rebuilt by hand,
# 2026-11-07: "creatively use towers and stairs and keeps to make sure continuing sections of wall remain level")
ANCHOR = {'ex_imp': {'top': 'ex_imp_towers_top_01', 'light': 'ex_imp_towers_light_01', 'med': 'ex_imp_towers_med_01',
                     'base': 'ex_imp_towers_base_01', 'dark': 'ex_imp_towers_dark_01', 'over': 384.0, 'bury': 64.0}}
ANCHOR_R = 160.0               # (the ground sampled this far round the stack's middle)
ANCHOR_CLEAR = 240.0           # (no stack where a guard tower or keep stands this near the joint)


def _stack_anchor(db, a, b, AN, W, avoid=()):
    """The stack at the joint between wall pieces a and b: [{'id', 'pose', 'kind': 'stack'}], and (x, y, crown z) noted
    in W['anchors']. None where a tower of avoid's stands within ANCHOR_CLEAR of the joint."""
    qa, qb = a['pose'], b['pose']
    d = math.hypot(qb.x - qa.x, qb.y - qa.y)
    L = (W.get('kit') or {}).get('L') or 512.0
    if d <= 1.25 * L:
        x, y = (qa.x + qb.x) / 2.0, (qa.y + qb.y) / 2.0
    else:
        x, y = qa.x + (qb.x - qa.x) * (L / 2.0) / d, qa.y + (qb.y - qa.y) * (L / 2.0) / d
    if any(math.hypot(x - ax, y - ay) < ANCHOR_CLEAR for ax, ay in avoid):
        return []
    low_foot = min(qa.z + a['_b'][2], qb.z + b['_b'][2])
    gzs = [g for g in (mapdata.terrain_z(db, x + ANCHOR_R * math.cos(k * math.pi / 4), y + ANCHOR_R * math.sin(k * math.pi / 4)) for k in range(8)) if g is not None]
    gz = max(gzs) if gzs else low_foot
    gz_lo = min(gzs + [low_foot])
    top = max(qa.z, qb.z) + AN['over']
    rz = qa.rz
    out = [('top', top)]
    z = top - 256
    while z - 128 > gz + AN['bury']:
        out.append(('light', z))
        z -= 256
    out.append(('med', z))
    out.append(('base', z - 384))
    bottom = z - 640
    while bottom > gz_lo - 48:
        out.append(('dark', bottom - 128))
        bottom -= 256
    W.setdefault('anchors', []).append((x, y, top))
    return [{'id': AN[k], 'pose': Pose(x, y, zz, rz, AN[k]), 'kind': 'stack'} for k, zz in out]


HILL_STEP = 192                # (a wall with no stair piece of its own climbs a hill in steps of this; the Imperial wall's
                               # stair rises 256, Hlaalu's, Velothi's and Redoran's 128: STEP_PIECES)
STEP_HIDE = 640                # (a tower hides a step between two stretches of this much at most: a bigger one raises
                               # the lower stretch, the ground filled under it. A tower stood 1,072 over the corner beside
                               # it and 34 of 167 neighbouring pieces stepped over 256 on the user's island town, "uneven
                               # walls", 2026-11-06)


def _cap_steps(segs, W):
    """No step between neighbouring stretches taller than a tower hides (STEP_HIDE): the lower stretch is raised by the
    rest, up to FILL_MAX over where its ground put it, and the ground is noted for fill_ground to bring up to its foot.
    Round the ring until nothing moves, so a hill becomes a stair of steps a tower can hide."""
    n = len(segs)
    if n < 2:
        return
    fill = W.setdefault('fill', [])
    ax = (W.get('kit') or {}).get('axis', 0)
    base = {id(seg): seg[0]['pose'].z for seg in segs}

    def top(seg):
        return max(p['pose'].z + p['_b'][5] for p in seg)
    for _round in range(n * 2):
        changed = False
        for k in range(1, n):
            A, B = segs[k - 1], segs[k]
            d = top(B) - top(A)
            if abs(d) <= STEP_HIDE:
                continue
            low = A if d > 0 else B
            z = min(low[0]['pose'].z + abs(d) - STEP_HIDE, base[id(low)] + FILL_MAX)
            if z - low[0]['pose'].z < 1 or any(p.get('nofill') for p in low):
                continue
            for p in low:
                p['pose'].z = z
            _fill_under(fill, low, z, ax)
            changed = True
        if not changed:
            break


def _no_dips(segs, W):
    """A level stretch standing under both the stretches either side (DIP_MIN) is raised to the lower of them, when the
    rise is within FILL_MAX; the ground under it is noted in W['fill'] for fill_ground to bring up to its foot. (The
    ground under a stretch cut to the ring's level while its neighbours' stayed high left the stretch in a trench.)"""
    n = len(segs)
    if n < 3:
        return
    fill = W.setdefault('fill', [])
    ax = (W.get('kit') or {}).get('axis', 0)
    for _round in range(n):
        changed = False
        for k, seg in enumerate(segs):
            z = seg[0]['pose'].z
            zp, zn = segs[k - 1][0]['pose'].z, segs[(k + 1) % n][0]['pose'].z
            # (never further than FILL_MAX over its own ground: raised to a neighbour already standing on fill, a
            # stretch stood with its feet beyond what fill_ground brings up)
            target = min(zp, zn, min(p['_g'][0] - SINK - p['_b'][2] + _allow(p) for p in seg))
            if z >= target - DIP_MIN or target - z > _FILL[0]:
                continue
            for p in seg:
                p['pose'].z = target
            _fill_under(fill, seg, target, ax)
            changed = True
        if not changed:
            break


# the walls that climb on step pieces of their own where a run changes level (lab j09 joins): Hlaalu's wall_up_01, a
# length whose one end stands 128 higher (its neighbour at -x 128 up), Velothi's wall_05 (at +x 128 up); laid without
# them, a Hlaalu or Velothi run stepped with its end standing bare over the next; Redoran's wu_01 the same way
STEP_PIECES = {'ex_hlaalu': {'id': 'ex_hlaalu_wall_up_01', 'rise': 128.0, 'up': -1},
               # (the Imperial stair length: a 512 length turned 90° to the straight that climbs 256 along its own y,
               # stairs_02 toward +y, stairs_01 the other hand; Old Ebonheart joins its wall's many levels with them, the
               # user's "master class", 2026-11-02. The other hand is its own piece, never the first turned about: the
               # buttress side would come inside)
               # (and a stretch's level may give up to 'give' to land on a whole rise: the game's Imperial walls step by
               # 256 and nothing else, their ground made to fit)
               # (and one rise only: the game's walls climb one stair length, 256, between levels (10 of 10 changes at a
               # stair, lab gamewalls 2026-11-07); a bigger change hides in a tower)
               'ex_imp': {'id': 'ex_imp_wall_stairs_02', 'alt': 'ex_imp_wall_stairs_01', 'rise': 256.0, 'up': 1, 'turn': math.pi / 2, 'give': 200, 'most': 1,
                          # (and a change of two or three rises laid stair, wall, stair: a straight at each level between,
                          # each stair at the lower level of its own step; the user's Soulrest east wall, 2026-11-08, its
                          # two wall towers at a 512 change taken out for that by hand: "use stairs more when joining
                          # different levels of wall section", "stair - wall - stair insertion")
                          'chain': 3},
               't_de_setveloth': {'id': 't_de_setveloth_x_wall_05', 'rise': 128.0, 'up': 1},
               # (a Redoran house's fort wall, Indarys's wu_01: the castle maker's Redoran stronghold on a slope)
               'ex_r_pcfort': {'id': 'ex_r_pcfort_wu_01', 'rise': 128.0, 'up': -1}}
STEP_MOST = 3                  # (a step of more rises than this is left to the run's own ends)
STEP_GIVE = 48                 # (how far a stretch's level may leave what its ground asks, to climb on whole steps)


def _stepped(db, A, B, St, straight, span, memo, fill=0.0):
    """Where level stretch B follows A along the same side, B's level set a whole number of rises from A's (within
    what its ground allows, the ground filled under it up to fill) and the lengths between climbed on the step piece:
    the last of A's going down, the first of B's going up."""
    a, b = A[-1], B[0]
    chain = St.get('chain', 0)

    def in_run(p):
        # (a length of the run: a straight, or, for a chain, the wall tower the planner set the change at; the user took
        # Soulrest's two out and laid the stairs in their places, 2026-11-08)
        return p.get('run') is not None and p.get('run') == a.get('run') and (
            p['id'] == straight or (chain and p.get('kind') == 'tower' and 'corner' not in p and TOWERISH.search(p['id'])))
    if a.get('run') is None or not in_run(a) or not in_run(b):
        return False
    za, zb = a['pose'].z, b['pose'].z
    lo, hi = span(B)
    rise = St['rise']
    # (a stretch's level may give a little, its foot or top a hand's breadth off: else a whole number of rises seldom
    # fitted, the ground allowing a stretch 10 to 60 units of play, and no step piece was ever laid, lab r26)
    give = St.get('give', STEP_GIVE)
    most = St.get('most', STEP_MOST)
    # (and below only STEP_GIVE: 'give' under lo let a whole side drop 188 and show 0.47, the lab's castle 2026-11-07)
    ks = [k for k in range(-max(most, chain), max(most, chain) + 1) if lo - STEP_GIVE <= za + k * rise <= hi + (fill or give)]
    if not ks:
        return False
    # (the fewest rises, as before; a chain's rises only where B's own ground asks for them: never more than its level
    # needs, the lower stretch kept on its ground rather than raised on fill to save a rise)
    near = min(abs(za + k * rise - zb) for k in ks)
    k = min(ks, key=lambda k: (abs(k) > most and abs(za + k * rise - zb) > near, abs(k) if abs(k) <= most else 0, abs(za + k * rise - zb), abs(k)))
    if k == 0:
        for p in B:
            p['pose'].z = za                 # (one level after all: no step)
        return True
    # (more rises than the piece climbs in a row: a stair, a straight at the level it reaches, the next stair; the
    # straights between are pieces of the stretch the stairs are taken from)
    gap = abs(k) > most
    need = 2 * abs(k) - 1 if gap else abs(k)
    if not gap and (a['id'] != straight or b['id'] != straight):
        return False                         # (one rise at a tower: the tower hides it, as before)

    def fits(run):
        if len(run) < need or any(not in_run(p) if gap else (p['id'] != straight or p.get('run') != a.get('run')) for p in run):
            return False
        # (each straight between at its own level must still bury its foot and show its top: else the change is left
        # to the tower, as before)
        for m, p in enumerate(run):
            if gap and m % 2 == 1:
                lvl = za + ((m + 1) // 2) * rise * (1 if k > 0 else -1)
                plo, phi = span([p])
                if not (plo - STEP_GIVE <= lvl <= phi + (fill or give)):
                    return False
        return True
    # (the pieces from the side the step piece climbs into, as before; a chain may take the other side's when that run
    # ends short of its corner: the levels go by the order the wall runs in either way)
    run = B[:need] if k > 0 else A[-need:]
    if not fits(run):
        other = A[-need:] if k > 0 else B[:need]
        if not gap or not fits(other):
            return False
        run = other
    for p in B:
        p['pose'].z = za + k * rise
    # (each step piece turned so it climbs the way the wall does: from A towards B when B is higher)
    fwd = (b['pose'].x - a['pose'].x, b['pose'].y - a['pose'].y)
    for m, p in enumerate(run):
        q = p['pose']
        if gap:
            # (in the order the wall runs from A to B: stair, straight, stair, ...; the m-th piece the (m // 2)-th step)
            if m % 2 == 1:
                # (a straight between two stairs: at the level the stair before it reaches; a wall tower there
                # becomes a straight)
                q.z = za + ((m + 1) // 2) * rise * (1 if k > 0 else -1)
                if p['id'] != straight:
                    p['id'] = q.id = straight
                    p['kind'] = 'piece'
                    nb_ = _box(db, straight, q, memo)[1]
                    if nb_:
                        p['_b'] = nb_
                continue
            j = m // 2
        else:
            j = m
        lx = (math.cos(q.rz), -math.sin(q.rz))
        climb = St['up'] * (1 if lx[0] * fwd[0] + lx[1] * fwd[1] > 0 else -1)
        pid = St['id']
        if (climb > 0) != (k > 0):
            if St.get('alt'):
                pid = St['alt']
            else:
                q.rz = (q.rz + math.pi) % (2 * math.pi)
        if St.get('turn'):
            q.rz = (q.rz + St['turn']) % (2 * math.pi)
        p['id'] = q.id = pid
        p['kind'] = 'step'
        # (its low end at the level it climbs from)
        q.z = za + (j * rise if k > 0 else -(j + 1) * rise)
        nb_ = _box(db, St['id'], q, memo)[1]
        if nb_:
            p['_b'] = nb_
    return True


EVEN_UP = 64                    # (a length no fill may come under is raised this much at most to a whole rise: else down)
EVEN_TOWER = 0.6                # (a tower within this many lengths of a joint spans its change of level)


def _beside(a, b, L, straight):
    """Two wall pieces stand next to each other in line: one length apart, along the line of whichever is a length of
    a run (a corner piece is turned to one of its two sides), turned alike."""
    dx, dy = b['pose'].x - a['pose'].x, b['pose'].y - a['pose'].y
    if not 0.75 * L <= math.hypot(dx, dy) <= 1.25 * L:
        return False
    for u, v in ((a, b), (b, a)):
        if 'corner' in u and u['id'] != straight:
            continue
        ax_ = (math.cos(u['pose'].rz), -math.sin(u['pose'].rz))
        if abs(dx * ax_[1] - dy * ax_[0]) > 0.1 * L:
            return False
        if not ('corner' in v and v['id'] != straight) and abs(math.sin(u['pose'].rz - v['pose'].rz)) > 0.1:
            return False
        return True
    return False


def _even_out(db, segs, St, straight, L, towers, memo, anchors):
    """No uneven lengths. Once the levels are planned: every length's level is brought to a whole number of rises of
    the wall's stair from the level most lengths stand at (half a rise at most, up or down; a length by a castle or
    on a cliff's crest, which takes no fill, is not raised more than EVEN_UP), and wherever two lengths that stand
    next to each other in line still differ, the change is climbed on stairs: stair, wall, stair through the first
    lengths of the higher run where it has them, stairs one after another through both runs' ends where it has not.
    A change a tower spans is left to it: a guard tower or keep at the joint (towers), or, past STEP_HIDE, the round
    tower the kit stacks there (anchors). By where the lengths stand, not the order they were planned in: a length
    carried into a castle's wall belongs to the town's corner there, and its neighbour stands in the middle of a
    stretch. Before this a level could stand at any height, a stair fitted only where two happened to lie a whole
    rise apart, and the higher length was otherwise made a wall tower standing over its neighbour: "why are you
    unable to use stairs as a last resort to avoid the uneven wall sections", "uneven wall sections are forbidden",
    the user, 2026-11-13, who had taken such lengths out by hand for stairs on 2026-11-08 and again that day.
    (stairs laid, joints left uneven)."""
    rise = St['rise']
    most = max(St.get('most', STEP_MOST), St.get('chain', 0))
    ps = [p for seg in segs for p in seg if 'dz' not in p]
    plain = [p for p in ps if p['id'] == straight and p.get('kind') not in ('gate', 'step')]
    if not plain:
        return 0, 0
    from collections import Counter
    base = Counter(round(p['pose'].z, 1) for p in plain).most_common(1)[0][0]
    for p in ps:
        z = p['pose'].z
        t = base + round((z - base) / rise) * rise
        # (a gate too, half a rise at most: its road is graded to the arch afterwards. Left at its own height, a gate
        # 71 over the lattice stood with a stair either side of it and a lip at each, the lab's mountain town)
        if t > z + EVEN_UP and (p.get('nofill') or p.get('_cliff')):
            t -= rise
        p['pose'].z = t

    def can(p):
        # (a length a stair may take the place of: a plain one, or the run's own wall tower)
        return p.get('kind') not in ('gate', 'step') and (p['id'] == straight or (p.get('kind') == 'tower' and 'corner' not in p and TOWERISH.search(p['id'])))

    def beside(a, b):
        return _beside(a, b, L, straight)

    def stair(p, z, fwd):
        q = p['pose']
        if p['id'] != straight:
            # (a wall tower's place: turned as the straight it stands for, which is how it is laid)
            p['id'] = q.id = straight
        lx = (math.cos(q.rz), -math.sin(q.rz))
        climb = St['up'] * (1 if lx[0] * fwd[0] + lx[1] * fwd[1] > 0 else -1)
        pid = St['id'] if climb > 0 else St.get('alt')
        if not pid or db.resolve_id(pid) is None:
            return False
        q.rz = (q.rz + St['turn']) % (2 * math.pi)
        p['id'] = q.id = pid
        p['kind'] = 'step'
        q.z = z
        nb_ = _box(db, pid, q, memo)[1]
        if nb_:
            p['_b'] = nb_
        return True

    def flat(p, z):
        q = p['pose']
        q.z = z
        if p['id'] != straight:
            p['id'] = q.id = straight
            p['kind'] = 'piece'
            nb_ = _box(db, straight, q, memo)[1]
            if nb_:
                p['_b'] = nb_

    def chain(first, back, fwd, level, n_most):
        # (the lengths a stair may take from `first` on, each one length further the way fwd, at first's level)
        run, cur = [], first
        while cur is not None and len(run) < n_most and can(cur) and abs(cur['pose'].z - level) < 16:
            run.append(cur)
            cur = next((c for c in ps if c is not cur and c is not back and c not in run and beside(cur, c)
                        and (c['pose'].x - cur['pose'].x) * fwd[0] + (c['pose'].y - cur['pose'].y) * fwd[1] > 0), None)
        return run
    pairs = sorted(((abs(b['pose'].z - a['pose'].z), i, j) for i, a in enumerate(ps) for j, b in enumerate(ps) if i < j and beside(a, b)), reverse=True)
    laid = left = 0
    for _d, i, j in pairs:
        a, b = ps[i], ps[j]
        if a.get('kind') == 'step' or b.get('kind') == 'step':
            continue
        if a['pose'].z > b['pose'].z:
            a, b = b, a
        lo, hi = a['pose'].z, b['pose'].z
        d = hi - lo
        if d < 16:
            continue
        mx, my = (a['pose'].x + b['pose'].x) / 2.0, (a['pose'].y + b['pose'].y) / 2.0
        if (anchors and d > STEP_HIDE) or any(math.hypot(t[0] - mx, t[1] - my) <= EVEN_TOWER * L for t in towers):
            continue                             # (a tower spans it)
        k = max(1, int(round(d / rise)))
        if k > most:
            left += 1
            continue
        fwd = (b['pose'].x - a['pose'].x, b['pose'].y - a['pose'].y)
        H = chain(b, a, fwd, hi, 2 * k - 1)
        if len(H) >= 2 * k - 1:
            for m, p in enumerate(H):
                if m % 2 == 0:
                    laid += bool(stair(p, lo + (m // 2) * rise, fwd))
                else:
                    flat(p, lo + ((m + 1) // 2) * rise)
            continue
        Lw = chain(a, b, (-fwd[0], -fwd[1]), lo, k)
        h = min(len(H), k)
        if len(Lw) < k - h:
            left += 1
            continue
        # (stairs one after another: the lower run's last lengths, then the higher run's first)
        flight = list(reversed(Lw[:k - h])) + H[:h]
        for m, p in enumerate(flight):
            laid += bool(stair(p, lo + m * rise, fwd))
    return laid, left


FORT_STAIR = 0.4               # (the last length before a castle standing this share of a rise over its run, or more: a stair)


def _stair_to_fort(db, segs, St, straight, memo):
    """The town's last length before a castle's wall, where the castle's ground lifts it over the run it ends: a wall
    stair at the run's own level, climbing towards the castle. Such a length takes no fill (FORT_NOFILL), so the
    planner stood it alone on the castle's bank at a height of its own, between the town's wall and the castle's, and
    made a wall tower of it: a length a quarter sunk in the bank with a step either side. The user took both out of
    their town's joins with its fort and laid ex_imp_wall_stairs_01 and _02 in their places, turned to the wall, at
    the town wall's height (2026-11-13). How many were laid."""
    rise = St['rise']
    n = 0
    for k, B in enumerate(segs):
        if len(B) != 1 or not B[0].get('nofill') or B[0]['id'] != straight:
            continue
        b = B[0]
        L = b['_b'][3] - b['_b'][0]
        # (the run it ends: a plain length one length off on its own line, lower. Not by the order the wall was
        # planned in: a length carried into the castle's wall at the town's corner is that corner's, not the run's)
        a = None
        ax_ = (math.cos(b['pose'].rz), -math.sin(b['pose'].rz))
        for A in segs:
            for c in A:
                if c is b or c['id'] != straight:
                    continue
                dx, dy = c['pose'].x - b['pose'].x, c['pose'].y - b['pose'].y
                d = math.hypot(dx, dy)
                if not 0.75 * L <= d <= 1.25 * L or abs(dx * ax_[1] - dy * ax_[0]) > 0.1 * L:
                    continue
                if b['pose'].z - c['pose'].z >= FORT_STAIR * rise and (a is None or c['pose'].z > a['pose'].z):
                    a = c
        if a is None:
            continue
        q = b['pose']
        fwd = (q.x - a['pose'].x, q.y - a['pose'].y)
        lx = (math.cos(q.rz), -math.sin(q.rz))
        climb = St['up'] * (1 if lx[0] * fwd[0] + lx[1] * fwd[1] > 0 else -1)
        pid = St['id'] if climb > 0 else St.get('alt')
        if not pid or db.resolve_id(pid) is None:
            continue
        q.rz = (q.rz + St['turn']) % (2 * math.pi)
        b['id'] = q.id = pid
        b['kind'] = 'step'
        q.z = a['pose'].z                        # (its low end at the level it climbs from)
        nb_ = _box(db, pid, q, memo)[1]
        if nb_:
            b['_b'] = nb_
        n += 1
    return n


def square_up(pts, step):
    """A wall drawn on the map made one the kit can lay: its points on a grid of the pieces' step from its first point,
    turned as its first side runs, each side straight along the grid (a slanting side becomes a step), points on a
    straight line dropped. [(x, y)]."""
    pts = [(float(p[0]), float(p[1])) for p in pts]
    if len(pts) < 3 or step <= 0:
        return []
    x0, y0 = pts[0]
    a = math.atan2(pts[1][1] - y0, pts[1][0] - x0)
    c, s = math.cos(a), math.sin(a)
    g = [(round(((x - x0) * c + (y - y0) * s) / step), round((-(x - x0) * s + (y - y0) * c) / step)) for x, y in pts]
    sq = []
    for k, p in enumerate(g):
        q = g[(k + 1) % len(g)]
        sq.append(p)
        if p[0] != q[0] and p[1] != q[1]:
            sq.append((q[0], p[1]))
    out = []
    for p in sq:
        if not out or out[-1] != p:
            out.append(p)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    changed = True
    while changed and len(out) >= 4:
        changed = False
        for k in range(len(out)):
            a_, b_, c_ = out[k - 1], out[k], out[(k + 1) % len(out)]
            if (a_[0] == b_[0] == c_[0]) or (a_[1] == b_[1] == c_[1]) or a_ == c_:
                out.pop(k)
                changed = True
                break
    if len(out) < 4:
        return []
    return [(x0 + (u * c - v * s) * step, y0 + (u * s + v * c) * step) for u, v in out]


def preview(db, plan, family=None):
    """The wall for the map: {'family', 'outline', 'pieces': [[kind, [[x, y] x4]]], 'gates', 'faults', 'roads'}."""
    W = lay(db, plan, family)
    memo = {}
    ps = []
    for p in W['pieces']:
        cs, _b = _box(db, p['id'], p['pose'], memo)
        if cs:
            ps.append([p['kind'], [[round(x), round(y)] for x, y in cs]])
    return {'family': W['family'], 'step': (W.get('kit') or {}).get('L'), 'outline': [[round(x), round(y)] for x, y in W['outline']], 'pieces': ps,
            'gates': W['gates'], 'faults': W['faults'][:6], 'roads': [[list(a), list(b), w] for a, b, w in W.get('roads') or []]}


def choices(db):
    """[{'id', 'piece', 'towns', 'cultures'}]: the walls the game runs, the most used first."""
    out = []
    for f, k in kits(db).items():
        out.append({'id': f, 'piece': k['straight'], 'step': k['L'], 'towns': (k.get('towns') or [])[:4], 'cultures': k.get('cultures') or {},
                    'placed': k['placed'], 'gate': any(v['kind'] == 'gate' for v in k['inline'].values()) or bool((k.get('round') or {}).get('gate'))})
    P = PALISADE['Nordic']
    if db.resolve_id(P['posts'][0]) is not None and db.resolve_id(P['gate']) is not None:
        n = sum(len(db.used_in.get(m, ())) for m in P['posts'])
        out.append({'id': 'palisade', 'piece': P['posts'][0], 'step': P['step'], 'towns': ['Karthgad', 'Blood Paw Lodge', 'Criaglorc'],
                    'cultures': {'Nordic': 3}, 'placed': n, 'gate': True})
    return sorted(out, key=lambda o: -o['placed'])


def road_patches(roads):
    """The land patches (512 across) a wall's gate roads cross, their width either side."""
    out = set()
    for a, b, w in roads:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / 128))
        for i in range(n + 1):
            x = a[0] + (b[0] - a[0]) * i / n
            y = a[1] + (b[1] - a[1]) * i / n
            r = w / 2.0
            for dx in (-r, 0, r):
                for dy in (-r, 0, r):
                    out.add((int((x + dx) // 512), int((y + dy) // 512)))
    return out
