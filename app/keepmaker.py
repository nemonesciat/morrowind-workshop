"""A keep of several linked interiors, the way the game's big Imperial keeps are put together (docs/keep-study-2026-11.md,
2026-11-05: Old Ebonheart's Ebon Tower, Firewatch's Ember Keep, Anvil, read whole).

A game keep is not one room behind one door. Ember Keep is eleven interiors off its Great Hall (barracks, high halls,
kitchens, servants' quarters, offices, a treasure chamber, the chapel and its undercroft under it); the Ebon Tower's
palace is twenty-three, in chains and two rings, with the sewers tying the prison, the undercroft and the treasure
chamber together underneath, and spiral-stair towers hanging off the halls. Each interior opens on the others door to
door, every door paired both ways, and on the walls outside at several arches.

plan() lays out such a set for a keep of a size: which interiors (a great hall, chambers, a garrison, a prison, a tower
or two, an undercroft), how they link (a chain with a ring or two through it) and which of them open to the outside.
make() builds each with the Imperial fort kind (dwemer.build(kind='fort'), with the doorways out it needs, its spiral
towers and big halls) and links them door to door; the doors kept for the outside come back for castle.py to pair with
the castle's own arches, tower crowns and keep doors. Nothing is copied from a game interior: every layout is grown,
dressed and lived in by the Workshop's own layers."""
import math
import random
import re
from collections import defaultdict

import mapdata
from editing import EditError

# the interiors a keep may hold: how each is grown (dwemer.build's size, levels, way) and what it asks for (keep:
# big halls' share, spiral towers and their turns, trap doors to the roof)
ROLES = {
    # (the halls climb from their doors: a keep's rooms rise into the mass that stands outside; only the dungeons and
    # the undercroft go down. Grown the generator's own way, down, "all the rooms sprawl downwards, there's no sense of
    # going up into the rest of the castle from the ground floor": the user, 2026-11-06)
    # (hall_first: the hall is the room behind the door, the user 2026-11-11, dwemer._generate)
    'hall': {'label': 'Great Hall', 'size': 'medium', 'levels': 'steep', 'big': 0.6, 'way': 'up', 'hall_first': True},
    'chambers': {'label': 'High Chambers', 'size': 'medium', 'levels': 'steep', 'big': 0.35, 'way': 'up'},
    'household': {'label': 'Household', 'size': 'medium', 'levels': 'steep', 'big': 0.2, 'way': 'up'},
    'library': {'label': 'Library', 'size': 'small', 'levels': 'some', 'big': 1.0, 'way': 'up'},
    'chapel': {'label': 'Chapel', 'size': 'small', 'levels': 'some', 'big': 1.0, 'way': 'up'},
    'garrison': {'label': 'Barracks', 'size': 'medium', 'levels': 'some', 'big': 0.15, 'way': 'up'},
    'prison': {'label': 'Dungeons', 'size': 'small', 'levels': 'some', 'big': 0.0, 'way': 'down'},
    'treasury': {'label': 'Treasure Chamber', 'size': 'small', 'levels': 'flat', 'big': 0.5, 'way': 'up'},
    'undercroft': {'label': 'Undercroft', 'size': 'medium', 'levels': 'some', 'big': 0.2, 'way': 'down'},
    'tower': {'label': '%s Tower', 'size': 'small', 'levels': 'some', 'way': 'up', 'big': 0.0, 'spirals': 1, 'turns': (3, 5), 'traps': True},
    # (one interior for a run of wall towers: passages and spiral stairs inside the wall with a door out at every arch,
    # Firewatch's Wall Towers, 13 doors over 7,197)
    'walls': {'label': 'Wall Towers', 'size': 'large', 'levels': 'some', 'way': 'up', 'big': 0.0, 'spirals': 2, 'turns': (2, 3), 'traps': True},
}
TOWER_NAMES = ('North Tower', 'South Tower', 'East Tower', 'West Tower', 'Old Tower', 'High Tower')
# the sets by size: the interiors (role names, a tower more than once) and the links between them by index; every
# plan has a ring (the Palace's Ducal Chambers - Library - Great Hall - Household ring, the sewer loop under the
# Treasure Chamber) and the undercroft under the halls, the prison and the garrison, as the game's sewers tie them
PLANS = {
    'small': {'roles': ['hall', 'garrison', 'tower', 'undercroft'],
              'links': [(0, 1), (0, 2), (0, 3), (1, 3)]},
    'medium': {'roles': ['hall', 'chambers', 'garrison', 'prison', 'tower', 'tower', 'undercroft'],
               'links': [(0, 1), (0, 2), (2, 3), (3, 6), (6, 0), (1, 4), (2, 5), (1, 6)]},
    'large': {'roles': ['hall', 'chambers', 'household', 'library', 'garrison', 'prison', 'treasury', 'tower', 'tower', 'tower', 'undercroft', 'chapel'],
              'links': [(0, 1), (1, 3), (3, 0), (0, 2), (2, 1), (0, 4), (4, 5), (5, 10), (10, 6), (6, 2), (10, 4), (1, 7), (2, 8), (4, 9), (3, 11), (11, 10)]},
}
# which interiors open to the outside, and how many doors each at most (castle.py hands the keep its doors: the ground
# door under the keep, the arches where the walk runs in, the roof door, the tower crowns): the halls first
# (a tower opens to the outside by the hatch at its top alone, as the game's crowns do: its front door is its foot)
OUTS = {'hall': 3, 'garrison': 2, 'chambers': 2, 'household': 1, 'walls': 16, 'prison': 1, 'undercroft': 1}
OUT_ORDER = ('hall', 'garrison', 'chambers', 'household', 'prison', 'undercroft')


def plan(size='medium', seed=1, outs=None, box=None, masses=None):
    """The set for a keep of this size: {'interiors': [{'i', 'role', 'label', 'size', 'levels', 'way', 'keep'}], 'links':
    [(i, j)], 'outs': {i: n}} with each interior's keep asks worked out from the doors it needs (one way out for each
    link, each door to the outside, and the front door counting as one). outs: how many doors to the outside the keep
    has to take ({role: n} or a number spread over the halls first), None for the plan's own. box: [half width, depth]
    of the keep's mass outside, from its door in; each hall keeps within it (the towers and the walls' passages stand
    where their own pieces do)."""
    P = PLANS.get((size or 'medium').partition('+')[0], PLANS['medium'])
    rng = random.Random('keep|%s|%s' % (size, seed))
    roles = list(P['roles'])
    links = [tuple(l) for l in P['links']]
    deg = defaultdict(int)
    for a, b in links:
        deg[a] += 1
        deg[b] += 1
    # the doors to the outside: as asked, else the plan's own (the great hall's ground door and a walk door, a tower's crown)
    want_out = {}
    if isinstance(outs, dict):
        for role, n in outs.items():
            for i, r in enumerate(roles):
                if r == role and n > 0:
                    take = min(n, OUTS.get(role, 1))
                    want_out[i] = take
                    n -= take
    elif isinstance(outs, int):
        n = outs
        # (in the keep's own blocks, with chambers over the hall: the hall keeps its front door, the doors at the walks
        # go to what lies up there, where the walks are)
        over = bool(masses) and any(r in UPPER for r in roles)
        cap_ = dict(OUTS, hall=1) if over else OUTS
        for role in (('hall', 'chambers', 'household', 'garrison', 'prison', 'undercroft') if over else OUT_ORDER):
            for i, r in enumerate(roles):
                if r == role and n > 0:
                    take = min(n, cap_.get(role, 1))
                    want_out[i] = take
                    n -= take
    else:
        want_out = {0: 2}
    towers = 0
    out = []
    for i, role in enumerate(roles):
        R = ROLES[role]
        label = R['label']
        if '%s' in label:
            label = TOWER_NAMES[towers % len(TOWER_NAMES)]
            towers += 1
        doors = deg[i] + want_out.get(i, 0)
        keep = {'exits': max(0, doors - 1), 'big': R.get('big', 0.0), 'spirals': R.get('spirals', 0), 'traps': bool(R.get('traps')),
                'nostories': True, 'role': role}
        if R.get('turns'):
            keep['turns'] = list(R['turns'])
        if R.get('hall_first'):
            keep['hall_first'] = True
        # (its rooms, set before any piece is laid: dwemer._grow_plan. A library's and a chapel's hall stands first)
        import dwemer as _dw
        if PLANNED and role in _dw.PLAN_ROOMS:
            keep['rooms'] = [list(r_) for r_ in _dw.PLAN_ROOMS[role]]
            if role in ('library', 'chapel'):
                keep['hall_first'] = True
        if masses and role == 'hall':
            # (the Great Hall is the room behind the keep's own door: inside the keep's own blocks, dwemer _Layout.fits)
            keep['mass'] = roomy(masses)
        elif masses and role not in ('tower', 'walls') and R.get('way') != 'down':
            # (the keep's other halls open off it by doors of their own: no bigger than the keep itself)
            wide = max(b[4] for b in masses) - min(b[1] for b in masses)
            deep = max(b[3] for b in masses) - min(b[0] for b in masses)
            keep['box'] = [max(wide, deep) / 2.0, max(wide, deep)]
        elif box and role not in ('tower', 'walls') and R.get('way') != 'down':   # (underground may spread past the mass)
            keep['box'] = [float(box[0]), float(box[1])]
        out.append({'i': i, 'role': role, 'label': label, 'size': R['size'], 'levels': R['levels'], 'way': R.get('way', 'down'),
                    'keep': keep, 'seed': rng.getrandbits(31), 'doors': doors})
    return {'size': size, 'seed': seed, 'interiors': out, 'links': links, 'outs': want_out}


MASS_NOT = re.compile(r'wall|gate|bridge|stair|battlement|arch|door|rail|ramp|plat|roof|window|slit|banner|flag', re.I)
MASS_ROOFED = re.compile(r'keep_02', re.I)       # (a block under its own pyramid roof: its rooms end under the roof)
MASS_BODY = 0.72               # (ex_imp_keep_02 is keep_01's body, 1,177 high, under a roof to 1,652)
MASS_TOWER = 700.0             # (a block narrower than this both ways is a tower)


def masses(db, cell, door, out, reach=4200.0):
    """The keep's outer blocks behind a door of it, read off the outside as built: [[a0, c0, z0, a1, c1, z1]] in the
    door's own frame (a: the way in from the door; c: across it to the right as you go in; z: up from the door's sill),
    every big piece that stands touching the one behind the door (the keep's blocks one on another, the towers against
    them), each up to its usable top. cell: the exterior cell's key; door: the door's place; out: a spot outside before
    it. [] when nothing is found behind the door."""
    try:
        gx, gy = [int(v) for v in str(cell)[1:].split(',')]
    except Exception:
        return []
    dx, dy = door[0] - out[0], door[1] - out[1]
    ln = math.hypot(dx, dy)
    if ln < 1:
        return []
    dx, dy = dx / ln, dy / ln
    refs = []
    for x in range(gx - 1, gx + 2):
        for y in range(gy - 1, gy + 2):
            try:
                refs += [r for r in mapdata.cellmap(db, '#%d,%d' % (x, y)).get('refs') or () if r.get('b') and r['type'] == 'STAT']
            except Exception:
                pass
    big = []
    for r in refs:
        b, s = r['b'], r.get('s') or 1.0
        # (a tower stands in sections a storey high: each counts)
        if (b[5] - b[2]) * s < (150 if 'tower' in r['id'].lower() else 400) or max(b[3] - b[0], b[4] - b[1]) * s < 300 or MASS_NOT.search(r['id']) \
                or math.hypot(r['p'][0] - door[0], r['p'][1] - door[1]) > reach:
            continue
        c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
        cs = [(r['p'][0] + (lx * c + ly * sn) * s, r['p'][1] + (-lx * sn + ly * c) * s) for lx in (b[0], b[3]) for ly in (b[1], b[4])]
        z0, z1 = r['p'][2] + b[2] * s, r['p'][2] + b[5] * s
        if MASS_ROOFED.search(r['id']):
            z1 = z0 + (z1 - z0) * MASS_BODY
        big.append({'w': (min(p[0] for p in cs), min(p[1] for p in cs), z0, max(p[0] for p in cs), max(p[1] for p in cs), z1), 'cs': cs})
    if not big:
        return []
    px, py = door[0] + dx * 220, door[1] + dy * 220
    holds = [m for m in big if m['w'][0] - 96 <= px <= m['w'][3] + 96 and m['w'][1] - 96 <= py <= m['w'][4] + 96 and m['w'][2] <= door[2] + 200 and m['w'][5] >= door[2] + 100]
    if not holds:
        return []
    got = [min(holds, key=lambda m: m['w'][2])]
    grew = True
    while grew:
        grew = False
        for m in big:
            if any(m is g for g in got):
                continue
            if any(m['w'][0] <= g['w'][3] + 48 and g['w'][0] <= m['w'][3] + 48 and m['w'][1] <= g['w'][4] + 48 and g['w'][1] <= m['w'][4] + 48
                   and m['w'][2] <= g['w'][5] + 96 and g['w'][2] <= m['w'][5] + 96 for g in got):
                got.append(m)
                grew = True
    out_ = []
    for m in got:
        ac = [((x - door[0]) * dx + (y - door[1]) * dy, (x - door[0]) * dy - (y - door[1]) * dx) for x, y in m['cs']]
        out_.append([round(min(p[0] for p in ac)), round(min(p[1] for p in ac)), round(m['w'][2] - door[2]),
                     round(max(p[0] for p in ac)), round(max(p[1] for p in ac)), round(m['w'][5] - door[2])])
    return out_


# ---- one plan of the keep for all its interiors (the brief of 2026-11-12, part 1)
# The keep's blocks are one space, measured from its front door (a the way in, c across to the right, z up from the
# sill). The Great Hall is the ground of it behind the door; the chambers, household, library and chapel lie over the
# hall, from the door they hang from upward; the barracks beside it on the lower floors; each tower interior is a tower
# with the stretch of the keep from its door to the tower's foot. An interior begins where the door it hangs from
# stands, going the way that door leads, so walking through a door you are where the outside says you are. Below
# ground (prison, undercroft, treasury) may spread.
UPPER = ('chambers', 'household', 'library', 'chapel')
# (the keep planner, dwemer._grow_plan: each interior's rooms drawn on a grid of the kit's own cells, storey by storey,
# before any piece is laid, then laid to the drawing. On since the round of 2026-11-12, lab kr_grid: five castles, 138
# rooms with a purpose where the grown keeps of 2.7.2-test6 had 59. KEEP_PLANNED=0 in the environment turns it off: a
# keep is then grown and its rooms given their purposes by where they lie, as in test6, piece for piece)
PLANNED = __import__('os').environ.get('KEEP_PLANNED', '1') != '0'
HALL_CAP = 900.0               # (the hall's own interior this high over the sill at most, when chambers lie over it)
BARRACKS_UP = 760.0            # (the barracks: this far up from its door at most)
REACH_UNDER = 150.0            # (an interior may go this far under the door it hangs from)


def _narrow(b):
    return b[3] - b[0] < MASS_TOWER and b[4] - b[1] < MASS_TOWER


def columns(blocks):
    """The towers among a keep's blocks, tallest first: [{'a', 'c', 'top', 'boxes'}]."""
    cols = {}
    for b in blocks or ():
        if _narrow(b):
            k = (round((b[0] + b[3]) / 400.0), round((b[1] + b[4]) / 400.0))
            cols.setdefault(k, []).append(list(b))
    out = [{'a': sum(b[0] + b[3] for b in bs) / (2.0 * len(bs)), 'c': sum(b[1] + b[4] for b in bs) / (2.0 * len(bs)), 'top': max(b[5] for b in bs), 'boxes': bs}
           for bs in cols.values()]
    return sorted([t for t in out if t['top'] > 700], key=lambda t: -t['top'])


def _clip(boxes, lo=None, hi=None):
    out = []
    for b in boxes:
        z0, z1 = b[2] if lo is None else max(b[2], lo), b[5] if hi is None else min(b[5], hi)
        if z1 - z0 >= 200:
            out.append([b[0], b[1], z0, b[3], b[4], z1])
    return out


def _in_frame(boxes, o, d):
    """Boxes of the keep's own space, in the frame of a door at o = (a, c, z) that leads the way d = (da, dc)."""
    out = []
    for b in boxes:
        pts = [((a - o[0]) * d[0] + (c - o[1]) * d[1], -(a - o[0]) * d[1] + (c - o[1]) * d[0]) for a in (b[0], b[3]) for c in (b[1], b[4])]
        out.append([round(min(q[0] for q in pts)), round(min(q[1] for q in pts)), round(b[2] - o[2]),
                    round(max(q[0] for q in pts)), round(max(q[1] for q in pts)), round(b[5] - o[2])])
    return out


def keep_pos(F, x, y, z):
    """A spot of an interior (its own coordinates) in the keep's space. F: {'o', 'd', 'e', 'in'}."""
    al = (x - F['e'][0]) * F['in'][0] + (y - F['e'][1]) * F['in'][1]
    cl = (x - F['e'][0]) * F['in'][1] - (y - F['e'][1]) * F['in'][0]
    return (F['o'][0] + al * F['d'][0] - cl * F['d'][1], F['o'][1] + al * F['d'][1] + cl * F['d'][0], F['o'][2] + (z - F['e'][2]))


def _door_out(F, d):
    """Where one of an interior's doors stands in the keep's space and which way it leads out: ((a, c, z), (da, dc))."""
    vx, vy = d['pos'][0] - d['arrive'][0], d['pos'][1] - d['arrive'][1]
    sx, sy = ((1 if vx > 0 else -1), 0) if abs(vx) >= abs(vy) else (0, (1 if vy > 0 else -1))
    al = sx * F['in'][0] + sy * F['in'][1]
    cl = sx * F['in'][1] - sy * F['in'][0]
    return keep_pos(F, d['pos'][0], d['pos'][1], d['pos'][2]), (int(round(al * F['d'][0] - cl * F['d'][1])), int(round(al * F['d'][1] + cl * F['d'][0])))


def _anchor(role, body, col, hall_box, took):
    """Where an interior of this role begins in the keep's space and which way it goes from there: ((a, c, z), (da, dc)),
    with a storey's height, the block ahead of it and its first two pieces clear of the Great Hall's own space; None
    when the keep has no such place. The chambers and the like a storey or two up in the tallest block not taken yet
    (took: the blocks given already); the barracks on the ground beside the hall, over it where the hall takes the
    ground; a tower's in the block nearest the tower, heading for it."""
    def clear(o, d):
        if not hall_box:
            return True
        for ahead in (128.0, 384.0):
            x, y = o[0] + d[0] * ahead, o[1] + d[1] * ahead
            if hall_box[0] - 150 <= x <= hall_box[3] + 150 and hall_box[1] - 150 <= y <= hall_box[4] + 150 and o[2] - 128 < hall_box[5] and o[2] + 128 > hall_box[2]:
                return False
        return True

    def ways(b, z):
        ma, mc = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
        out = [((b[0] + 150.0, mc, z), (1, 0)), ((ma, b[1] + 150.0, z), (0, 1)), ((b[3] - 150.0, mc, z), (-1, 0)), ((ma, b[4] - 150.0, z), (0, -1))]
        if b[3] - b[0] < b[4] - b[1]:
            out = [out[1], out[0], out[3], out[2]]
        # (and room ahead in the block itself: two pieces)
        return [(o, d) for o, d in out if clear(o, d) and (b[3] - b[0] if d[0] else b[4] - b[1]) >= 700]
    if not body:
        return None
    # (planned: a wall-sized tower, 326 across inside, holds no spiral stair, 474 across: the interior begun at it
    # was its door and one piece, lab kr_grid4. Begun beside the hall instead, as a keep with no tower's)
    if role == 'tower' and col and PLANNED and min(min(c_[3] - c_[0], c_[4] - c_[1]) for c_ in col['boxes']) < 500.0:
        col = None
    if role == 'tower' and col:
        b = min(body, key=lambda b: math.hypot((b[0] + b[3]) / 2.0 - col['a'], (b[1] + b[4]) / 2.0 - col['c']) + (0 if b[2] <= 64 else 2000))
        ma, mc = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
        da, dc = col['a'] - ma, col['c'] - mc
        d = ((1 if da > 0 else -1), 0) if abs(da) >= abs(dc) else (0, (1 if dc > 0 else -1))
        # (beside the tower, heading into it: begun in the middle of its block, the way to the tower ran through the
        # Great Hall's own space and the interior stood two pieces long, lab pl2)
        half = max(c_[3] - c_[0] for c_ in col['boxes']) / 2.0 if d[0] else max(c_[4] - c_[1] for c_ in col['boxes']) / 2.0
        if not PLANNED:
            # (as in 2.7.2-test6: from the middle of the block; the place beside the tower is the planner's, not measured
            # on grown layouts)
            for z in (max(0.0, b[2]), 384.0, 512.0):
                o = (ma - d[0] * 120.0, mc - d[1] * 120.0, z)
                if b[5] - z >= 310 and clear(o, d):
                    return o, d
            return None
        # (so far from the tower's middle that the stair at the door's own opening stands whole in the tower: its cap
        # 320 from the door, its foot 684, both within the tower's narrowest section; at half its widest and 330 the cap
        # stood 17 out of the tower's near face and the tower had no stair, lab gp4)
        half = min((c_[3] - c_[0] if d[0] else c_[4] - c_[1]) for c_ in col['boxes']) / 2.0
        for z in (max(0.0, b[2]), 384.0, 512.0):
            for back in (half + 200.0, half + 300.0):
                o = (col['a'] - d[0] * back, col['c'] - d[1] * back, z)
                if b[5] - z >= 310 and clear(o, d):
                    return o, d
        return None
    if role == 'tower' and PLANNED:
        # (a keep with no tower outside for it: on the ground beside the hall, where a spiral stair has the keep's whole
        # height over it and its foot under the floor; begun over the hall the stair's foot, 384 under its lowest
        # doorway, stood in the hall's own space and the tower had no stair, lab kr_grid1)
        hc = ((hall_box[0] + hall_box[3]) / 2.0, (hall_box[1] + hall_box[4]) / 2.0) if hall_box else (0.0, 0.0)
        ground = [b for b in body if b[2] <= 64 and b[5] >= 600]
        for b in sorted(ground, key=lambda b: (sum(1 for t in took if t is b), -math.hypot((b[0] + b[3]) / 2.0 - hc[0], (b[1] + b[4]) / 2.0 - hc[1]))):
            w = ways(b, 0.0)
            if w:
                took.append(b)
                return w[0]
    if role in UPPER or role == 'tower':
        for b in sorted(body, key=lambda b: (sum(1 for t in took if t is b), -b[5])):
            for z in (512.0, 384.0):
                if b[2] <= z and b[5] - z >= 310:
                    w = ways(b, z)
                    if w:
                        took.append(b)
                        return w[0]
        return None
    if role == 'garrison':
        ground = [b for b in body if b[2] <= 64 and b[5] >= 310]
        hc = ((hall_box[0] + hall_box[3]) / 2.0, (hall_box[1] + hall_box[4]) / 2.0) if hall_box else (0.0, 0.0)
        for z in (0.0, 384.0, 512.0):
            for b in sorted(ground, key=lambda b: -math.hypot((b[0] + b[3]) / 2.0 - hc[0], (b[1] + b[4]) / 2.0 - hc[1])):
                # (planned: on the ground only in a block with room for a stair beside a room, 4.5 cells one way; one
                # keep block is 3.6 across, a barracks of one room in it and no way up, lab gp2. Over the hall else)
                if PLANNED and z == 0.0 and max(b[3] - b[0], b[4] - b[1]) < 1150.0:
                    continue
                if b[5] - z >= 310:
                    w = ways(b, z)
                    if w:
                        return w[0]
        return None
    return None


LEAD_IN = 470.0                # (a door leads on into the keep when the keep stands this far beyond it)
PLACED_LEAST = 12              # (an interior stays in its part of the keep when that gives it this many pieces and a real room)


def _leads_in(body, kp, kd):
    x, y = kp[0] + LEAD_IN * kd[0], kp[1] + LEAD_IN * kd[1]
    # (and stands a storey high there: a door under a block's very top leads to nothing that fits)
    return any(b[0] <= x <= b[3] and b[1] <= y <= b[4] and b[2] - 300 <= kp[2] <= b[5] - 310 for b in body)


def _frame_of(lay, o, d):
    import dwemer
    e = lay.get('entrance') or {}
    if e.get('side') not in dwemer.SIDES:
        return None
    return {'o': [float(v) for v in o], 'd': [int(d[0]), int(d[1])], 'e': [float(e['x']), float(e['y']), float(e.get('z', 0.0))],
            'in': list(dwemer.SIDES[dwemer.OPP[e['side']]])}


def _part_for(role, body, col, zp):
    """The part of the keep an interior of this role takes, hung from a door at height zp: boxes in the keep's space,
    or None for one that may spread (below ground)."""
    lo = zp - REACH_UNDER
    if role == 'tower':
        # (planned: the keep beside the tower to its top, for the rooms at the stair's landings)
        return (col['boxes'] + _clip(body, lo, None if PLANNED else zp + 320.0)) if col else _clip(body, lo)
    if role in UPPER:
        return _clip(body, lo)
    if role == 'garrison':
        return _clip(body, lo, zp + BARRACKS_UP)
    return None


MASS_ROOM = 1408.0             # (a hall of four tiles behind the door and a passage beside it)
MASS_GROW = 1.65               # (a small keep's blocks taken this much bigger inside at most)


def roomy(blocks):
    """The blocks as the inside takes them: a small keep's, whose block behind the door holds no hall and a passage
    (one keep block is 851 across; made in them a Great Hall came to nine pieces, lab castle_made), grown about the door
    until they do, by MASS_GROW at most, their heights and sides as they stand. A keep is roomier inside than out, as
    the game's own buildings are; a big keep's blocks stay as they are."""
    # (by the hall itself, not by a block's size: the smallest of a few steps at which a hall of four tiles stands behind
    # the door on the keep's ground, on the door's line or to one side of it. By the first block's size Fort Urasek's
    # keep, five blocks on the ground, was taken 1.63 times bigger; by all its ground blocks' size a great keep whose
    # hall fits no single block got none)
    def scaled(s):
        out = []
        for b in blocks:
            if _narrow(b) and s > 1.0:
                ma, mc, ha, hc = (b[0] + b[3]) / 2.0 * s, (b[1] + b[4]) / 2.0 * s, (b[3] - b[0]) / 2.0, (b[4] - b[1]) / 2.0
                out.append([ma - ha, mc - hc, b[2], ma + ha, mc + hc, b[5]])      # (a tower stays a tower: moved out with the keep, its own width kept)
            else:
                out.append([b[0] * s, b[1] * s, b[2], b[3] * s, b[4] * s, b[5]])
        return out

    def hall_fits(bs):
        ground = [b for b in bs if not _narrow(b) and b[2] <= 64 and b[5] >= 300]
        inside = lambda a, c: any(b[0] - 8 <= a <= b[3] + 8 and b[1] - 8 <= c <= b[4] + 8 for b in ground)
        # (as the hall is laid: its first tile on the door's line, 384 in, the second row 512 on, the other column 512 to
        # one side; each tile's middle with the layout's own margin. A test of any square that size passed for a hall
        # between two columns, which cannot be laid, and a great keep's Great Hall had no hall, lab kr_final)
        # (planned: the tiles where they are laid, their middles 512 and 1024 in from the sill, the way in's own piece
        # and the doorway before them. Tested at 384 and 896, a great keep whose block behind the door is 1,022 square
        # passed and no hall of four tiles stood in it: its Great Hall was a room of fourteen pieces with one door, lab
        # kr_grid4, gp11. The unplanned keep keeps the old test, to stay as 2.7.2-test6 lays it)
        r1, r2, far = (512, 1024, 1408) if PLANNED else (384, 896, 1280)
        return any(all(inside(a + da, c * sg + dc) for a in (r1, r2) for c in (0, 512) for da in (-72, 72) for dc in (-72, 72)) and inside(128, 0)
                   and all(inside(far, c * sg) for c in (0, 512)) for sg in (1, -1))
    for s in (1.0, 1.2, 1.4, MASS_GROW):
        out = scaled(s)
        if hall_fits(out):
            break
    return out


def towers_of(blocks):
    """The towers among a keep's blocks: [(a, c, top)] the middle of each column of narrow blocks and how high it stands."""
    cols = {}
    for b in blocks or ():
        if b[3] - b[0] < MASS_TOWER and b[4] - b[1] < MASS_TOWER:
            k = (round((b[0] + b[3]) / 2 / 200.0), round((b[1] + b[4]) / 2 / 200.0))
            cols[k] = ((b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, max(b[5], cols.get(k, (0, 0, -1e9))[2]))
    return sorted(cols.values(), key=lambda t: -t[2])


def _free_name(db, nm):
    base, k = nm, 2
    low = nm.lower()
    while any(v not in db.dead for v in db.by_key.get(('CELL', low), [])) or low in db.project.cells:
        nm = '%s %d' % (base, k)
        low = nm.lower()
        k += 1
    return nm


def _layout_with_doors(db, I, tries=8):
    """A seed whose layout gives the interior the doorways it needs (dwemer.generate with its keep asks): the plan's
    seed, else the next few drawn from it. (seed, layout)."""
    import dwemer
    rng = random.Random(I['seed'])
    best = None
    # (a planned interior: three seeds. Its doors are the plan's, and eight plans in the same blocks came to the same
    # count eight times, a Great Hall's layout 7 s where one took 0.9, lab gp6)
    for t in range(min(tries, 3) if I['keep'].get('rooms') else tries):
        seed = I['seed'] if t == 0 else rng.getrandbits(31)
        try:
            lay = dwemer.generate(db, I['size'], I['levels'], 'branching', seed=seed, kind='fort', way=I['way'], keep=I['keep'])
        except EditError:
            continue
        got = 1 + len(lay.get('exits') or [])
        # (a real room in it: an interior of corridor only is a fault, "not a hallway", the user 2026-11-12)
        roomy_ = any(pc.get('hall') is not None and not pc.get('gone') for pc in lay['pieces'])
        if got >= I['doors'] and roomy_:
            return seed, lay
        if best is None or (roomy_, got) > best[0]:
            best = ((roomy_, got), seed, lay)
    if best is None:
        raise EditError('No layout for the keep\'s %s keeps the rules.' % I['label'].lower())
    return best[1], best[2]


def make(db, name, *a, **k):
    """_make, written into the places ledger (ledger.py): a keep's interiors, its castle's when one is being made."""
    import ledger
    with ledger.open(db, 'interior', name, seed=k.get('seed')):
        return _make(db, name, *a, **k)


def _make(db, name, size='medium', seed=1, outs=None, people=True, commit=True, progress=None, box=None, masses=None):
    """The keep's interiors built and linked. name: the keep's ("Fort Vanvuld": its interiors are "Fort Vanvuld, Great
    Hall" and so on). outs: the doors to the outside wanted, as plan(). Returns {'name', 'cells': [keys], 'interiors':
    [{role, label, key, name, doors: [...]}], 'links': n, 'outs': [{cell, k, name, arrive, role, z}] (the doors kept for
    the outside, highest first within each interior), 'rings'}; with commit, one Undo takes the whole keep back."""
    import editing
    import dwemer
    editing._require_project(db)
    p = db.project
    name = (name or '').strip()
    if not name:
        raise EditError('Give the keep a name.')
    S = dwemer.ready(db, 'fort')
    if S is None:
        import learning
        return {'learning': learning.ruin_pending(db, 'fort')}
    PL = plan(size, seed, outs, box, masses)
    stack = getattr(p, 'undo_stack', [])
    n0 = len(stack)
    say = progress or (lambda what, frac: None)
    made = []
    # ---- the order: the hall first, then each interior from one already standing that it links to (the door it
    # hangs from is known then, and with it where in the keep it begins)
    MB = roomy(masses) if masses else None
    body = [b for b in MB if not _narrow(b)] if MB else []
    cols = columns(MB) if MB else []
    n_tow = sum(1 for I in PL['interiors'] if I['role'] == 'tower')
    tow_free = list(cols[:n_tow])
    order, seen = [(0, None)], {0}
    grew = True
    while grew and MB:
        grew = False
        for a, b in PL['links']:
            for x, y in ((a, b), (b, a)):
                if x in seen and y not in seen:
                    order.append((y, x))
                    seen.add(y)
                    grew = True
    order += [(I['i'], None) for I in PL['interiors'] if I['i'] not in seen and I['i'] != 0]
    by_plan = {I['i']: I for I in PL['interiors']}
    frames, hung, used, hall_box, took = {}, [], set(), None, []
    for n_, (i_, par) in enumerate(order):
        I = dict(by_plan[i_])
        I['keep'] = dict(I['keep'])
        say('Building the %s' % I['label'].lower(), 0.1 + 0.6 * n_ / max(1, len(PL['interiors'])))
        nm = _free_name(db, '%s, %s' % (name, I['label']))
        o_, d_, da_ = None, None, None
        if MB and I['role'] == 'hall':
            # (the ground of the keep behind its door; the towers no tower interior takes; no higher than HALL_CAP
            # where chambers lie over it)
            over = any(J['role'] in UPPER for J in PL['interiors'])
            I['keep']['mass'] = _clip(body, None, HALL_CAP if over else None) + [b for t in cols[n_tow:] for b in t['boxes']]
            o_, d_ = (0.0, 0.0, 0.0), (1, 0)
        elif MB and I['way'] != 'down' and I['role'] != 'walls':
            # (its own part of the keep, begun at a set place in it: over the hall, beside it, at a tower's foot; and
            # the door it hangs from, the nearest free one of the interior it links to. Hung from wherever a door of
            # the hall happened to stand, 3 of 19 interiors of two castles found a door that led anywhere)
            col = tow_free[0] if (I['role'] == 'tower' and tow_free) else None
            anc = _anchor(I['role'], body, col, hall_box, took)
            part = _part_for(I['role'], body, col, anc[0][2]) if anc else None
            if anc and part:
                o_, d_ = anc
                if col is not None:
                    tow_free.remove(col)
                I['keep']['mass'] = _in_frame(part, o_, d_) + [[-40, -160, -REACH_UNDER, 340, 160, 300]]
                if hall_box:
                    I['keep']['avoid'] = _in_frame([hall_box], o_, d_)
                I['keep'].pop('box', None)
                if par in frames:
                    A = next(m for m in made if m['i'] == par)
                    free_ = [d for d in A['doors'] if d['kind'] == 'exit' and d['k'] not in used]
                    if free_:
                        near_ = lambda d: (lambda kp: math.hypot(kp[0] - o_[0], kp[1] - o_[1]) + 2.0 * abs(kp[2] - o_[2]))(_door_out(frames[par], d)[0])
                        da_ = min(free_, key=near_)
        try:
            seed_, lay = _layout_with_doors(db, I)
            if I['keep'].get('mass') and I['role'] != 'hall':
                live_ = [pc for pc in lay['pieces'] if not pc.get('gone') and pc.get('id')]
                if len(live_) < PLACED_LEAST or not any(pc.get('hall') is not None for pc in live_):
                    raise EditError('too little fits its part')     # (six pieces of corridor in a tower's part, lab kr_try)
                # (planned: a tower with no stair is no tower: a row of rooms on one floor over the hall, lab kr_grid4)
                if PLANNED and I['role'] == 'tower' and sum(1 for pc in live_ if 'spiral_01' in str(pc.get('id', '')).lower()) < 2:
                    raise EditError('no stair stands in its part')
        except EditError:
            if not I['keep'].get('mass') or I['role'] == 'hall':
                raise
            # (no layout fits its part: made the old way, by its size alone, and counted as not placed)
            for k_ in ('mass', 'avoid'):
                I['keep'].pop(k_, None)
            o_, d_, da_ = None, None, None
            seed_, lay = _layout_with_doors(db, I)
        r = dwemer.build(db, nm, I['size'], I['levels'], 'branching', seed=seed_, kind='fort', way=I['way'], keep=I['keep'],
                         occupants='none', commit=True)
        if r.get('learning'):
            return r
        doors = [d for d in r.get('doors') or []]
        F = _frame_of(lay, o_, d_) if o_ is not None else None
        if F:
            frames[i_] = F
            try:
                p.cells[r['key']]['ruin']['at'] = {'o': [round(v, 1) for v in F['o']], 'd': F['d']}
            except Exception:
                pass
            if I['role'] == 'hall':
                tl = [pc['box'] for pc in lay['pieces'] if not pc.get('gone') and pc.get('hall') == 0 and str(pc.get('id', '')).lower() == 'in_impbig_4way_01' and pc.get('box')]
                if tl:
                    cs = [keep_pos(F, x, y, z) for b in tl for x in (b[0], b[3]) for y in (b[1], b[4]) for z in (b[2], b[5])]
                    hall_box = [min(q[0] for q in cs) + 40, min(q[1] for q in cs) + 40, min(q[2] for q in cs), max(q[0] for q in cs) - 40, max(q[1] for q in cs) - 40, max(q[2] for q in cs) - 40]
            if da_ is not None:
                front = next((d for d in doors if d['kind'] == 'front'), None)
                if front is not None:
                    used.update((da_['k'], front['k']))
                    hung.append((par, da_, i_, front))
        made.append({'i': I['i'], 'role': I['role'], 'label': I['label'], 'key': r['key'], 'name': nm, 'doors': doors, 'seed': seed_, 'entrance': lay.get('entrance'),
                     'tunnels': r.get('tunnels'), 'halls': r.get('halls'), 'rings': r.get('rings', 0), 'spirals': r.get('spirals', 0), 'placed': F is not None,
                     'floors': len({round(dwemer_floor(S, pc) / 128) for pc in lay['pieces'] if not pc.get('gone') and pc.get('id') and pc.get('of') is None})})
    made.sort(key=lambda m: m['i'])
    # ---- the doors: each link takes a door at either end; the front door is kept for the outside where the outside
    # is wanted, else it is a link's; a tower's front door is its foot, the way in from the hall it hangs off
    say('Linking the doors', 0.75)
    by_i = {m['i']: m for m in made}
    spare = {}
    for m in made:
        ds = [d for d in m['doors'] if d['k'] not in used]
        front = [d for d in ds if d['kind'] == 'front']
        rest = [d for d in ds if d['kind'] == 'exit']
        traps = [d for d in ds if d['kind'] == 'trap']
        n_out = PL['outs'].get(m['i'], 0)
        # (the doors for the outside: the front door first, then the highest exits; a tower's crown trap door is for
        # the outside too, when a crown is there to take it)
        # (and of the exits, those in the keep's outer face before those that lead on into it)
        if m['i'] in frames and body:
            rest = sorted(rest, key=lambda d: (_leads_in(body, *_door_out(frames[m['i']], d)), -d['pos'][2]))
            keep_out = (front + rest)[:n_out] if n_out else []
        else:
            keep_out = (front + sorted(rest, key=lambda d: -d['pos'][2]))[:n_out] if n_out else []
        m['out'] = keep_out + traps
        spare[m['i']] = [d for d in front + sorted(rest, key=lambda d: -d['pos'][2]) if d not in keep_out]
    links_done = []
    unmet = []
    spots = towers_of(masses) if not hung else []
    # (the interiors hung from a door first: that door and their own front door are the link)
    for a, da, b, front in hung:
        _link(db, by_i[a]['key'], da['k'], by_i[b]['name'], front['arrive'])
        _link(db, by_i[b]['key'], front['k'], by_i[a]['name'], da['arrive'])
        links_done.append((a, b))
    for a, b in PL['links']:
        if (a, b) in links_done or (b, a) in links_done:
            continue
        if a not in by_i or b not in by_i or not spare.get(a) or not spare.get(b):
            unmet.append((a, b))
            continue
        A, B = by_i[a], by_i[b]
        da = None
        if spots and A['role'] == 'hall' and B['role'] == 'tower' and isinstance(A.get('entrance'), dict) and A['entrance'].get('side'):
            # (the door to a tower: the hall's door nearest where a tower stands outside, the tallest tower first)
            import dwemer
            e_ = A['entrance']
            ix, iy = dwemer.SIDES[dwemer.OPP[e_['side']]]
            ta, tc, _top = spots.pop(0)
            da = min(spare[a], key=lambda d: math.hypot((d['pos'][0] - e_['x']) * ix + (d['pos'][1] - e_['y']) * iy - ta,
                                                        (d['pos'][0] - e_['x']) * iy - (d['pos'][1] - e_['y']) * ix - tc))
            spare[a].remove(da)
        da, db_ = da or spare[a].pop(0), spare[b].pop(0)
        _link(db, A['key'], da['k'], B['name'], db_['arrive'])
        _link(db, B['key'], db_['k'], A['name'], da['arrive'])
        links_done.append((a, b))
    # (a door more than its links and outside doors need: paired with another such, the farthest interior first, so
    # no door leads nowhere; an odd one left is given to the outside)
    extra = [(i, d) for i, ds in spare.items() for d in ds]
    while len(extra) >= 2:
        i, d = extra.pop(0)
        j_, d2 = next(((j, e) for j, e in extra if j != i), extra[0])
        extra.remove((j_, d2))
        _link(db, by_i[i]['key'], d['k'], by_i[j_]['name'], d2['arrive'])
        _link(db, by_i[j_]['key'], d2['k'], by_i[i]['name'], d['arrive'])
        links_done.append((i, j_))
    for i, d in extra:
        by_i[i]['out'].insert(0, d)
    db.sync_project()
    cells = [m['key'] for m in made]
    editing.commit(db, 'Linked the doors of %s' % name)
    try:
        import doors as doors_
        doors_.face_arrivals(db, cells, follow=False)
    except Exception as e:
        print('keep arrivals:', e)
    # ---- people: a garrison in the halls, as the game's keeps of the kind are peopled (populate.cast reads a keep's
    # setting off its name and furniture)
    folks = 0
    if people:
        say('Placing the people', 0.9)
        folks = _people(db, made, seed)
    outs_ = []
    for m in made:
        for d in m['out']:
            outs_.append({'cell': m['key'], 'k': d['k'], 'name': m['name'], 'arrive': d['arrive'], 'role': m['role'], 'kind': d['kind'],
                          'z': d['pos'][2], 'label': m['label'],
                          # (where it stands in the keep's own space, for the castle to pair it with the door outside it)
                          'kp': [round(v, 1) for v in keep_pos(frames[m['i']], d['pos'][0], d['pos'][1], d['pos'][2])] if m['i'] in frames else None})
    grow_ = 1.0
    if masses and MB:
        wide0 = max((b[3] - b[0] for b in masses if not _narrow(b)), default=0.0)
        wide1 = max((b[3] - b[0] for b in MB if not _narrow(b)), default=0.0)
        grow_ = wide1 / wide0 if wide0 > 0 else 1.0
    out = {'name': name, 'cells': cells, 'interiors': made, 'links': len(links_done), 'link_list': links_done, 'unmet': unmet, 'outs': outs_, 'grow': grow_,
           'rings': _cycle_rank(len(made), links_done), 'people': folks, 'plan': PL}
    if commit:
        steps = len(getattr(p, 'undo_stack', [])) - n0
        if steps > 1:
            editing.fold(db, steps, 'Made the keep of %s: %d interiors, %d links%s' % (name, len(made), len(links_done), (', %d people' % folks) if folks else ''))
    return out


def dwemer_floor(S, pc):
    import dgrules
    return dgrules.floor_of(S, pc)


def _cycle_rank(n, links):
    """How many independent rings the interiors' link graph has (joins - nodes + parts)."""
    par = list(range(n))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for a, b in links:
        par[f(a)] = f(b)
    parts = len({f(i) for i in range(n)})
    return len(links) - n + parts


def _link(db, cell, rk, dest, pos):
    import doors
    import editing
    c, refs = editing._cell(db, cell)
    ref = refs.get(rk)
    if ref is None:
        return False
    editing._store(c, rk, ref['origin'], ref['idx'], doors._set_link(ref['subs'], dest, [float(v) for v in pos[:6]]))
    return True


def _people(db, made, seed):
    """The keep's people: each interior cast as the game casts a place of its setting (populate.cast: a keep's name and
    furniture read as a garrison's or a guild's), placed in its rooms; the prison and the undercroft get nobody."""
    import zlib
    try:
        import castsurvey
        if castsurvey.ready(db) is None:
            return 0
        import populate
    except Exception:
        return 0
    n, said = 0, []
    for m in made:
        if m['role'] in ('prison', 'undercroft', 'treasury'):
            continue
        try:
            cast_ = populate.cast(db, m['key'], {'density': 'few'} if m['role'] in ('tower', 'library', 'chapel') else {},
                                  seed=zlib.crc32(('%s|%s' % (seed, m['name'])).encode()))
            ppl = (cast_ or {}).get('people') or []
            if ppl:
                pl = populate.place(db, m['key'], ppl, own=True, lines=False)
                said += pl.get('people') or []
                n += len(ppl)
        except Exception as e:
            print('keep people:', m['name'], e)
    if said:
        import editing
        try:
            if populate.write_lines(db, said):
                editing.commit(db, 'Lines for the people of the keep')
        except Exception as e:
            print('keep lines:', e)
    return n


# ------------------------------------------------------------------------------------------------ reading a made keep
LOAD_DOOR = re.compile(r'loaddoor|trap|hatch', re.I)


def doors_of(db, cells):
    """Every door that leads somewhere, or should, in these places (the load doors and hatches; a door that only swings
    in its frame is left out): [{cell, k, id, to (cell key or None), pos}]."""
    out = []
    for ck in cells:
        m = mapdata.cellmap(db, ck)
        for r in m.get('refs') or ():
            if r['type'] == 'DOOR' and (LOAD_DOOR.search(r['id']) or r.get('to')):
                to = (r.get('to') or {}).get('key') if r.get('to') else None
                if r.get('to') and not to:
                    to = ((r['to'].get('cell') or '').lower()) or '#'
                out.append({'cell': ck, 'k': r['k'], 'id': r['id'], 'to': to, 'pos': r['p'][:3]})
    return out


def pairing(db, cells):
    """How the doors of a keep pair: {'doors': n, 'paired': doors leading to another of these places that has a door
    leading back, 'out': doors leading outside them, 'unpaired': doors leading nowhere, 'oneway': doors whose other
    end leads elsewhere}."""
    cells = set(cells)
    ds = doors_of(db, cells)
    leads = defaultdict(set)
    for d in ds:
        if d['to'] and d['to'] in cells:
            leads[(d['cell'], d['to'])].add(d['k'])
    paired = oneway = out = unp = 0
    for d in ds:
        if not d['to']:
            unp += 1
        elif d['to'] not in cells:
            out += 1
        elif leads.get((d['to'], d['cell'])):
            paired += 1
        else:
            oneway += 1
    return {'doors': len(ds), 'paired': paired, 'out': out, 'unpaired': unp, 'oneway': oneway}
