"""Keeps and castles, made the way each culture builds its own (the user, 2026-11-01: "better keep and castle generation,
with rooms inside towers, keeps and curtain walls").

Everything is the game's own, read by castlesurvey.py:

  Imperial    a curtain wall of the Legion's pieces (townwalls' ex_imp kit, its gate where the way in comes), a round
              tower at each corner and beside the gate, each tower as the game stands its own in a wall (the crown at
              the wall walk, 384 over the wall's origin, an entrance arch where each length runs in, a door in it, a trap
              door to the roof), and a Legion keep standing inside at the back with the pieces round it. Behind the keep's
              doors the game keep's own rooms and those they lead on to (its prison, its upper storey) as shells, every
              door paired as the game paired it, furnished by the Workshop (ROOMS); behind the towers' doors one
              "Towers" place holding a spiral-stair room for each tower, as the game's forts keep theirs (Hawkmoth's
              six, Firewatch's seven), joined to the keep.
  Stronghold  a Dunmer stronghold stands whole: the game repeats one keep on its stepped platform, piece for piece
              (Hlormaren, Marandus, Falasmaryon; Andasreth and Berandas without the platform), with its four ways in:
              the upper and lower levels, the dome, the propylon chamber. Stood whole, its rooms behind it as shells.
  Redoran     a house stronghold: the ex_r_pcfort wall (corners, gate) round its manor, its services and its tower,
              each with the shells of the rooms the game put behind them.

plan(db, outline, style, size, seed) lays it out for the map (nothing changes); make(...) builds it as one Undo.
Doors face through to the world: each outside door leads in where the game's led, arriving in front of the inside
door, and out again a step in front of the outside one, facing away."""
import math
import random
import re
import zlib
from collections import Counter

import castlesurvey as cs
import mapdata
import townwalls as tw
from editing import EditError

STYLES = {
    'Imperial': {'label': 'Imperial fort', 'wall': 'ex_imp', 'keep': r'^ex_imp_keep_01$', 'towers': True, 'name': 'Fort %s',
                 'gaps': (500, 700, 1200)},
    'Stronghold': {'label': 'Dunmer stronghold', 'wall': None, 'keep': r'^ex_stronghold_fort00$', 'name': '%s'},
    # (Indarys's wall hugs its buildings: 4,018 by 2,994 round a group 3,300 across)
    'Redoran': {'label': 'Redoran stronghold', 'wall': 'ex_r_pcfort', 'keep': r'^ex_r_pcfort_01$', 'gaps': (200, 250, 400),
                'name': '%s Manor'},
}
NAME_CULTURE = {'Imperial': 'Imperial', 'Stronghold': 'Dunmer', 'Redoran': 'Redoran'}
SIZES = {'small': 0.8, 'medium': 1.0, 'large': 1.3}
MARGIN = 700                   # a keep stands this far in from the wall behind it (the wall's own depth and a lane)
TOWN_NEAR = 6000               # (a town's wall this near turns the castle's gate towards the town)
SIDE_GAP = 500                 # (and from the walls at its sides)
# the Legion's round tower in a wall, as the game stands its own (lab c8, 46 towers_top in game walls): the crown at the
# walk (wall origin + 384), lights below it every 256, a med section, the base, dark foundation sections to the ground;
# an entrance arch (ex_imp_wallent_02) at 176 out on each side a length runs in, 72 under the crown, its door 13 in
# and 74 up, turned a quarter; a trap door in the crown to the roof
TOWER = {'top': 'ex_imp_towers_top_01', 'light': 'ex_imp_towers_light_01', 'med': 'ex_imp_towers_med_01',
         'base': 'ex_imp_towers_base_01', 'dark': 'ex_imp_towers_dark_01', 'arch': 'ex_imp_wallent_02',
         'door': 'Ex_imp_loaddoor_02', 'trap': 'in_com_traptop_01', 'over_wall': 384, 'arch_r': 176, 'arch_dz': -72,
         'door_in': (13.0, 0.0, 74.0), 'trap_at': (-59.0, 6.0, 154.0, 90.0)}
TOWER_EVERY = 6                # a tower along a side every so many lengths besides those at the corners and the gate
TOWER_CLEAR = 300              # (a wall_tower_01 this near a round tower goes: two towers in one spot)
# a Legion gatehouse (Tamriel Data), as Firewatch's gates stand (five of them, lab g8): the wall arch in the wall line at
# the wall's level, the gate passage on its outer side with its door on the ground, a square guard tower either side.
# In the arch's frame (+y out of the castle): the passage 65 out turned about, the door in the passage's frame, the
# towers at +-565 and 44 out, a quarter turned as the game's (doorways along the walk), 1.12 big: the tower's body is
# solid only 200 out (its 303 box is its crown), so the arch's edge and the wall's end both stand 20 inside it, lab tprof
GATEHOUSE = {'arch': 't_imp_legionmw_x_wallarch_04', 'dent': 't_imp_legionmw_x_gatedent_01', 'door': 't_imp_legion_gatedoor_01',
             'tower': 'ex_imp_guardtower_02', 'dent_at': (0.0, 65.0), 'door_at': (-138.0, -23.0, -326.0),
             'tower_at': (565.0, 44.0), 'tower_s': 1.12, 'tower_dz': -80.0, 'dent_over': 330.0, 'tower_foot': 436.0}
WALL_FOOT, WALL_TOP = 488.0, 409.0  # (ex_imp_wall_01's foot under and top over its origin, the foot a little in the ground)
KEEP_COVER_Z = (150.0, 350.0, 550.0, 750.0, 850.0)  # (heights over the keep's ground its walls must stand at to be the wall)
KEEP_OVER_WALL = 200.0         # (a keep in the wall line rises this far over the wall's top at least)
TOWER_KEEP_CLEAR = 700.0       # (a round tower's middle this far from a keep's box at least)
KEEP_NOT = re.compile(r'guardtower', re.I)  # (pieces of a game keep that stood on its fort's wall, not the keep)
DOOR_ON = 50.0                 # (a keep's front door this near its own walls; the game's 7-28, Ancylis' 117)
PAD_SHOW = 300.0               # (a walled-in keep's pad this far under the wall's top at most)
TOWER_UNDER = 260              # (a corner piece or length with its middle this near a round tower's is inside it)
TOWER_BESIDE = 800             # (a buttressed length this near one is a plain length)
KEEP_CUT = 60                  # (a wall length this deep in the keep's footprint is left out: the keep is the wall there)
INNER_LANE = 2                 # (a large castle's inner ward: this many lengths of lane between its wall and the outer)
INNER_FRONT = 1000             # (and this much yard before the keep inside it)
INNER_RUN = 100                # (its runs numbered from here, so the grounding levels them as runs of their own)
KEEP_UP = 64                   # the keep's origin this far over the wall's beside it (the game's 0 to 128)
CASTLE_LEVEL_TOL = 384         # (the ground under a castle's wall is moved further than a town's: fewer levels)
PAD_R = 256                    # the ground under a keep is evened out this far round it
PAD_BLEND = 512
PAD_CUT = 1024
_cache = {}


# ------------------------------------------------------------------------------------------------ what can be made
def choices(db):
    """The styles there are game examples of, for the panel: [{'id', 'label', 'examples', 'modules'}]."""
    S = cs.survey(db)
    out = []
    for st, d in STYLES.items():
        mods = _modules(S, st)
        if not mods:
            continue
        out.append({'id': st, 'label': d['label'], 'modules': len(mods),
                    'examples': sorted({f['name'].split(',')[0].title() for f in S['forts'] if f['style'] == st})[:6]})
    return out


_DB = [None]
_ATT = {}


def _door_attached(db, m):
    """Whether a module's front door stands on its own walls (a wall within DOOR_ON of it, round it at its height)."""
    k = (m['fort'], m['main'])
    if k not in _ATT:
        import seethrough
        sc = seethrough.Scene()
        memo = {}
        for pc in m['pieces']:
            ri = db.resolve_id(pc[0])
            model = db.recs[ri][5] if ri is not None else None
            if not model:
                continue
            if model not in memo:
                memo[model] = seethrough.model_tris(db, model)
            sc.add_model(memo[model], (pc[1], pc[2], pc[3], pc[5], pc[6], pc[4]), pc[7])
        x, y, z = _front_door(m)['p'][:3]
        best = None
        for i in range(16):
            a = i * math.pi / 8
            for dz in (-60.0, 20.0, 100.0):
                h = sc.nearest_any((x, y, z + dz), (math.cos(a), math.sin(a), 0.0), 600.0)
                if h is not None and (best is None or h[0] < best):
                    best = h[0]
        _ATT[k] = best is not None and best <= DOOR_ON
    return _ATT[k]


def _modules(S, style, which='keep'):
    d = STYLES[style]
    rx = re.compile(d['keep'] if which == 'keep' else d.get('more') or '$^', re.I)
    out = [m for m in S['modules'] if m['style'] == style and rx.search(m['main']) and m['doors']]
    if which == 'keep':
        # (the keep holds the halls: a module whose rooms are only a prison or a chapel stands beside it, not for it)
        out = [m for m in out if 'keep' in m['roles'] or which != 'keep']
    # (a keep whose doors all lead into rooms the castle won't have is no use: a doorless shell)
    # (and one with a door on every side, Pelagiad's thirteen, is a fort's whole yard, not a keep)
    out = [m for m in out if any(not re.search(r'trap|hatch', dd['id'], re.I) for dd in m['doors']) and len(m['doors']) <= 6]
    # (the game fort's own wall-walk pieces left out: Moonmoth's keep carries the two sentry towers that stand on
    # Moonmoth's wall beside it, and without that wall they hung off the keep's side, the user 2026-11-03)
    out = [dict(m, pieces=[pc for pc in m['pieces'] if not KEEP_NOT.search(pc[0])]) if any(KEEP_NOT.search(pc[0]) for pc in m['pieces']) else m
           for m in out]
    # (its front door on its own walls: Ancylis' keep's door is a round tower's, 117 out from the plain keep it came
    # with, and it stood loose before it, the user 2026-11-03 "the same detached door flaw")
    if _DB[0] is not None:
        out = [m for m in out if _door_attached(_DB[0], m)] or out
    return out


def _kit(db, fam):
    K = tw.kits(db)
    if fam in K:
        return K[fam]
    return cs.survey(db)['wall_kits'].get(fam)


def _typical(S, style):
    """The style's game forts' walled ground: (short, long) sides, the medians."""
    sz = [sorted(f['wall_size']) for f in S['forts'] if f['style'] == style and f.get('wall_size') and f.get('wall', {}).get('pieces', 0) >= 12]
    if not sz:
        return 3000.0, 3800.0
    a = sorted(s[0] for s in sz)
    b = sorted(s[1] for s in sz)
    return float(a[len(a) // 2]), float(b[len(b) // 2])


# ------------------------------------------------------------------------------------------------ frames
def _to_world(F, u, v):
    """Castle frame (u across, v from the gate to the back) to the world."""
    c, s = math.cos(F['a']), math.sin(F['a'])
    return F['x'] + u * c - v * s, F['y'] + u * s + v * c


def _place(P, lx, ly):
    """A point in a placed module's frame (x, y, z, rz: the main piece's pose) in the world (to_world turns clockwise)."""
    c, s = math.cos(P[3]), math.sin(P[3])
    return P[0] + lx * c + ly * s, P[1] - lx * s + ly * c


def _axis(pts):
    """The drawn outline's main way: its longest side."""
    best = (0, 0.0)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > best[0]:
            best = (L, math.atan2(b[1] - a[1], b[0] - a[0]))
    return best[1]


def _extent(pts, F):
    c, s = math.cos(F['a']), math.sin(F['a'])
    us = [(p[0] - F['x']) * c + (p[1] - F['y']) * s for p in pts]
    vs = [-(p[0] - F['x']) * s + (p[1] - F['y']) * c for p in pts]
    return max(us) - min(us), max(vs) - min(vs)


def _ground(db, x, y):
    z = mapdata.terrain_z(db, x, y)
    return z if z is not None else 0.0


# ------------------------------------------------------------------------------------------------ planning
def plan(db, outline, style='Imperial', size='medium', seed=1, name='', gate=None):
    """The castle laid out (nothing placed): {'style', 'name', 'frame', 'outline', 'W' (the wall), 'towers', 'modules',
    'preview', 'rooms', 'fig', 'faults'}. The same outline, style, size and seed give the same castle."""
    if style not in STYLES:
        raise EditError('No such style: %s' % style)
    pts = [(float(p[0]), float(p[1])) for p in outline or ()]
    if len(pts) < 3:
        raise EditError("Draw the castle's outline first.")
    S = cs.survey(db)
    _DB[0] = db
    d = STYLES[style]
    rng = random.Random('%s|%s|%s|castle' % (style, size, seed))
    F = {'x': sum(p[0] for p in pts) / len(pts), 'y': sum(p[1] for p in pts) / len(pts), 'a': _axis(pts)}
    faults = []
    keeps = _modules(S, style)
    if not keeps:
        raise EditError('The game has no %s keeps to learn from in this load order.' % d['label'])
    if style == 'Stronghold':
        # (small: a keep with no platform, Andasreth's or Berandas's; else one on its platform)
        big = [m for m in keeps if len(m['pieces']) >= 30]
        small = [m for m in keeps if len(m['pieces']) < 30]
        pool = (small or big) if size == 'small' else (big or small)
        km = rng.choice(sorted(pool, key=lambda m: m['fort']))
    else:
        km = rng.choice(sorted(keeps, key=lambda m: (m['fort'], m['main'])))
    out = {'style': style, 'size': size, 'seed': seed, 'faults': faults, 'frame': F, 'towers': [], 'modules': [], 'W': None}
    # the way in: the side whose ground outside is lowest (a fort is come at from below), the drawn way first on a tie
    # (beside or inside a town with a wall, the gate opens towards the town: its streets lead to it, and the town's wall
    # meets the castle's rather than running past its back)
    town = tw.standing_walls(db, [(F['x'], F['y'])], TOWN_NEAR)
    tx = ty = None
    if len(town) >= 6:
        tx = sum(c[0] for q in town for c in q[0]) / (4.0 * len(town))
        ty = sum(c[1] for q in town for c in q[0]) / (4.0 * len(town))
        if math.hypot(tx - F['x'], ty - F['y']) < 600:
            tx = ty = None                   # (the castle in the very middle of its town: by the ground, as alone)
    # (never out onto the sea or over a cliff: a castle on an island or a headland had its gate at the water, the lowest
    # ground, and the user had to steer every one, 2026-11-03. gate: the way the user picked, an angle, kept to)
    half = 0.5 * (max(_extent(pts, F)) if size == 'drawn' else max(_typical(S, style)) * SIZES.get(size, 1.0))
    z0 = mapdata.terrain_z(db, F['x'], F['y'])
    best = None
    for k in range(4):
        a = F['a'] + k * math.pi / 2
        G = dict(F, a=a)
        if gate is not None:
            d_ = abs((a - math.pi / 2 - gate + math.pi) % (2 * math.pi) - math.pi)
            key = (d_,)
        else:
            ox, oy = _to_world(G, 0, -1.0)
            wet, steep = tw.gate_blocked(db, F['x'], F['y'], ox - F['x'], oy - F['y'], z0, half)
            gx, gy = _to_world(G, 0, -2500)
            z = _ground(db, gx, gy) if tx is None else math.hypot(gx - tx, gy - ty)
            key = (wet, steep, z)
        if best is None or key[:-1] < best[0][:-1] or (key[:-1] == best[0][:-1] and key[-1] < best[0][-1] - (0 if gate is not None else 32)):
            best = (key, a)
    F['a'] = best[1]
    out['gate'] = F['a'] - math.pi / 2
    if style == 'Stronghold':
        out['modules'].append(_set_module(km, F, 0.0, 0.0))
    else:
        kit = _kit(db, d['wall'])
        if not kit:
            raise EditError('The game has no %s wall pieces in this load order.' % d['label'])
        L = kit['L']
        a0, b0 = _typical(S, style)
        f = SIZES.get(size, 1.0)
        if size == 'drawn':
            Wd, Dp = _extent(pts, F)
        else:
            Wd, Dp = a0 * f, b0 * f
        # (room for the keep and what stands with it, turned with its door to the gate, and a yard before it)
        # (a keep that fits the size asked for, else the smallest)
        fits = []
        for m in sorted(keeps, key=lambda m: (m['fort'], m['main'])):
            eu, ev = _turned_extent(m, F)
            g_side, g_back, g_front = d.get('gaps') or (SIDE_GAP, MARGIN, 1200)
            fits.append((eu + 2 * g_side <= Wd * 1.1 and ev + g_back + g_front <= Dp * 1.1, -(eu * ev), m))
        ok = [t[2] for t in fits if t[0]]
        # (a keep in the wall line stands as high as the wall: Umbermoth's keep is 450 high, the wall 900, and in the
        # wall line it left a low gap the wall could not fill, the user 2026-11-03)
        if not d.get('keep_apart'):
            ok = [m for m in ok if _mesh_tall(db, m)] or ok
        km = rng.choice(ok) if ok else max(fits, key=lambda t: t[1])[2]
        eu, ev = _turned_extent(km, F)
        g_side, g_back, g_front = d.get('gaps') or (SIDE_GAP, MARGIN, 1200)
        Wd = max(Wd, eu + 2 * g_side)
        Dp = max(Dp, ev + g_back + g_front)
        # (whole lengths round it, never fewer than its keep needs: rounded down, a compound stood into the wall)
        n_w, n_d = max(4, int(math.ceil(Wd / L - 0.1))), max(4, int(math.ceil(Dp / L - 0.1)))
        if n_w % 2:
            n_w += 1                     # (an even count: the gate stands in the middle of its side)
        inner = size == 'large' and bool(d.get('towers')) and not d.get('keep_apart')
        if inner:
            # (the inner ward round the keep: whole lengths, a lane of INNER_LANE lengths between the two walls)
            n_w2 = max(4, int(math.ceil((eu + 2 * g_side) / L - 0.1)))
            if n_w2 % 2:
                n_w2 += 1
            n_d2 = max(3, int(math.ceil((ev + INNER_FRONT) / L - 0.1)))
            n_w = max(n_w, n_w2 + 2 * INNER_LANE)
            n_d = max(n_d, n_d2 + 2 * INNER_LANE + 2)
        Wd, Dp = n_w * L, n_d * L
        poly = [_to_world(F, -Wd / 2, -Dp / 2), _to_world(F, Wd / 2, -Dp / 2), _to_world(F, Wd / 2, Dp / 2), _to_world(F, -Wd / 2, Dp / 2)]
        # (the way in: out, through the front, out again, so the gate is asked for there alone)
        way = [list(_to_world(F, -16, -Dp / 2 - 1500)), list(_to_world(F, 0, -Dp / 2 + 200)), list(_to_world(F, 16, -Dp / 2 - 1500))]
        W = _lay(db, d['wall'], kit, {'plots': [], 'streets': [{'pts': way}], 'wall_outline': poly})
        faults += W.get('faults') or []
        W['pieces'] = [p for p in W['pieces'] if p.get('kind') not in ('bigtower', 'keep')]
        _outlines(db, W)
        if style == 'Imperial':
            _gatehouse_plan(db, W, F, L)
        out['W'] = W
        out['size_wd'] = [Wd, Dp]
        W2 = None
        if inner:
            vb = Dp / 2 - INNER_LANE * L
            vf = vb - n_d2 * L
            poly2 = [_to_world(F, -n_w2 * L / 2, vf), _to_world(F, n_w2 * L / 2, vf), _to_world(F, n_w2 * L / 2, vb), _to_world(F, -n_w2 * L / 2, vb)]
            way2 = [list(_to_world(F, -16, vf - 1500)), list(_to_world(F, 0, vf + 200)), list(_to_world(F, 16, vf - 1500))]
            W2 = _lay(db, d['wall'], kit, {'plots': [], 'streets': [{'pts': way2}], 'wall_outline': poly2})
            W2['pieces'] = [p for p in W2['pieces'] if p.get('kind') not in ('bigtower', 'keep')]
            _outlines(db, W2)
            if style == 'Imperial':
                _gatehouse_plan(db, W2, F, L)
            out['inner'] = poly2
        # the keep at the back, its door to the gate: in the wall line, as the game's keeps stand (Old Ebonheart's,
        # Moonmoth's, Ebonheart's: their wall lengths run into the keep's sides, lab r01; the user, 2026-11-02: "the keep
        # should actually attach to the walls"). Its back face at the wall's outer face; the lengths it covers go
        # (a big keep with its own platform and stairs too: its doors came out 248 under the pad until the pad was set
        # by its door, _rise; the user, 2026-11-03: the keep still stood apart)
        if d.get('keep_apart'):
            out['modules'].append(_set_module(km, F, 0.0, Dp / 2 - (d.get('gaps') or (0, MARGIN))[1], back=True))
        else:
            Wk = W2 if W2 is not None else W
            v_back = (Dp / 2 - INNER_LANE * L) if W2 is not None else Dp / 2
            v_out = v_back
            for p in Wk['pieces']:
                if p.get('kind') == 'wall' and p.get('corners'):
                    for cx_, cy_ in p['corners']:
                        v_ = -(cx_ - F['x']) * math.sin(F['a']) + (cy_ - F['y']) * math.cos(F['a'])
                        if v_ > v_back - L and v_ > v_out:
                            v_out = v_
            M = _set_module(km, F, 0.0, v_out, back=True)
            # (its walls' back at the wall's outer face, not its box's: Ancylis' keep's box reaches past its walls, and set
            # by the box it stood short of the wall line with the lengths behind it gone, the user 2026-11-03)
            vx, vy = -math.sin(F['a']), math.cos(F['a'])
            kb_ = km['box']
            box_reach = max(_place((0.0, 0.0, 0.0, M['rz']), lx, ly)[0] * vx + _place((0.0, 0.0, 0.0, M['rz']), lx, ly)[1] * vy
                            for lx in (kb_[0], kb_[2]) for ly in (kb_[1], kb_[3]))
            mr = _mesh_reach(db, km, M['rz'], vx, vy)
            if mr is not None:
                M['x'] += vx * (box_reach - mr)
                M['y'] += vy * (box_reach - mr)
            M['in_wall'] = True
            out['modules'].append(M)
            kb = km['box']
            Pz = (M['x'], M['y'], 0.0, M['rz'])
            kpts = [_place(Pz, lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))]
            Wk['pieces'] = _cut_by_module(db, Wk, M, kpts)
        if size == 'large' and style == 'Imperial':
            # (a second hall, a chapel or an armoury, as Frostmoth's and Umbermoth's)
            sec = [m for m in keeps if m is not km and set(m['roles']) & {'chapel', 'armoury', 'barracks'}]
            if sec:
                m = rng.choice(sorted(sec, key=lambda m: m['fort']))
                # (in the side wall's line, its back the wall there and its door to the yard, as the keep stands in the
                # back wall: set free in the yard and turned to the gate it stood askew and apart, the user 2026-11-03)
                Mh = _in_side_wall(db, m, F, W, Wd, Dp, L, poly2 if W2 is not None else None)
                if Mh is not None:
                    out['modules'].append(Mh)
        if d.get('towers'):
            out['towers'] = _towers(W, kit, F, corners=size == 'large')
            if W2 is not None:
                out['towers'] += _towers(W2, kit, F, corners=True)
            # (no round tower against a keep or hall: one stood on the length by a keep's side, half in the keep and
            # hanging off it, the user 2026-11-03 "a floating tower dangling on the side")
            out['towers'] = [t for t in out['towers'] if not any(_near_module(M, t['x'], t['y'], TOWER_KEEP_CLEAR) for M in out['modules'])]
        if W2 is not None:
            # (one wall for the rest of the making: the inner runs numbered on from the outer's)
            for p in W2['pieces']:
                for k_ in ('run', 'corner'):
                    if p.get(k_) is not None:
                        p[k_] += INNER_RUN
            W['pieces'] += W2['pieces']
            W['extra_preview'] = (W.get('extra_preview') or []) + (W2.get('extra_preview') or [])
            faults += W2.get('faults') or []
        # (stairs up to the walk from the bailey, as the game's forts have theirs; clear of the towers and the keep)
        away = [(t['x'], t['y']) for t in out['towers']]
        for M in out['modules']:
            kb = M['m']['box']
            away += [_place((M['x'], M['y'], 0.0, M['rz']), lx, ly) for lx in (kb[0], kb[2]) for ly in (kb[1], kb[3])]
        W['pieces'] += tw.wall_stairs(W, avoid=away, most=3 if W2 is not None else 2, db=db)
    out['name'] = (name or '').strip() or castle_name(db, style, seed)
    out['preview'] = _preview(db, out)
    out['rooms'] = _rooms(db, S, out)
    out['fig'] = _figures(out)
    out['game'] = _game_figures(S, style)
    return out


def _outlines(db, W):
    """Each length's corners on the ground, for the keeps set in the wall line: the wall's own are only worked out when
    it is grounded, after the plan, so the lengths a keep stands in were never left out and the keep was set by the
    wall's middle line, not its outer face (lab k2, 2026-11-03)."""
    memo = {}
    for p in W['pieces']:
        if not p.get('corners'):
            cs_ = tw._box(db, p['id'], p['pose'], memo)[0]
            if cs_:
                p['corners'] = cs_


def _gatehouse_ok(db):
    return all(db.resolve_id(GATEHOUSE[k]) is not None for k in ('arch', 'dent', 'door', 'tower'))


def _gatehouse_plan(db, W, F, L):
    """The wall's gate made a Legion gatehouse: the gate arch and the length after it out, the gatehouse's wall arch in
    the middle of the gap, marked for make() to stand its passage, door and towers by. Its towers and passage go in the
    plan's preview too, at no height yet."""
    if not _gatehouse_ok(db):
        return
    memo = {}

    def mid(p):
        cs_ = tw._box(db, p['id'], p['pose'], memo)[0]
        return (sum(q[0] for q in cs_) / 4.0, sum(q[1] for q in cs_) / 4.0) if cs_ else None
    for g in [p for p in W['pieces'] if p.get('kind') == 'gate']:
        c = mid(g)
        if not c:
            continue
        dx, dy = math.cos(g['pose'].rz), -math.sin(g['pose'].rz)
        # (three lengths in a row with the gate among them, the gate in the middle where it can be: the gap three
        # lengths, the two towers meeting the lengths beyond. A gate by a corner takes the two after it)
        at = {}
        for p in W['pieces']:
            if p.get('kind') not in ('wall', 'tower') or p.get('run') != g.get('run'):
                continue
            m = mid(p)
            if not m or abs((m[0] - c[0]) * dy - (m[1] - c[1]) * dx) > L / 4:
                continue
            k = round(((m[0] - c[0]) * dx + (m[1] - c[1]) * dy) / L)
            if k and abs((m[0] - c[0]) * dx + (m[1] - c[1]) * dy - k * L) < L / 4:
                at[k] = p
        side = None
        for ks, off in (((-1, 1), 0), ((1, 2), 1), ((-2, -1), -1)):
            if all(k in at for k in ks):
                side, shift = [at[k] for k in ks], off
                break
        if side is None:
            continue
        gx, gy = c[0] + dx * shift * L, c[1] + dy * shift * L
        nx, ny = -dy, dx
        if nx * (gx - F['x']) + ny * (gy - F['y']) < 0:
            nx, ny = -nx, -ny
        rz = math.atan2(nx, ny)                  # (its +y out of the castle: the passage stands outside the wall line)
        A = tw.Pose(gx, gy, g['pose'].z, rz, GATEHOUSE['arch'])
        W['pieces'] = [p for p in W['pieces'] if p is not g and not any(p is q for q in side)]
        W['pieces'].append({'id': GATEHOUSE['arch'], 'pose': A, 'kind': 'gate', 'run': g.get('run'), 'gatehouse': True})
        for sx in (-1, 1):
            tx, ty = A.dir((sx * GATEHOUSE['tower_at'][0], GATEHOUSE['tower_at'][1]))
            W.setdefault('extra_preview', []).append((GATEHOUSE['tower'], tw.Pose(gx + tx, gy + ty, 0.0, rz + math.pi / 2, GATEHOUSE['tower'])))
        ox, oy = A.dir(GATEHOUSE['dent_at'])
        W.setdefault('extra_preview', []).append((GATEHOUSE['dent'], tw.Pose(gx + ox, gy + oy, 0.0, rz + math.pi, GATEHOUSE['dent'])))


def _gatehouse_make(db, W):
    """[(id, (x, y, z, rx, ry, rz))] for each gatehouse arch now on the ground: its passage with the door's foot on the
    ground before it, the gate door, and the two guard towers, their feet in the ground."""
    out = []
    for p in W['pieces']:
        if not p.get('gatehouse'):
            continue
        A = p['pose']
        ox, oy = A.dir(GATEHOUSE['dent_at'])
        D = tw.Pose(A.x + ox, A.y + oy, 0.0, A.rz + math.pi)
        fx, fy = D.dir(GATEHOUSE['door_at'][:2])
        D.z = _ground(db, D.x + fx, D.y + fy) + GATEHOUSE['dent_over']
        out.append((GATEHOUSE['dent'], (D.x, D.y, D.z, 0.0, 0.0, D.rz), 1.0))
        out.append((GATEHOUSE['door'], (D.x + fx, D.y + fy, D.z + GATEHOUSE['door_at'][2], 0.0, 0.0, D.rz), 1.0))
        for sx in (-1, 1):
            tx, ty = A.dir((sx * GATEHOUSE['tower_at'][0], GATEHOUSE['tower_at'][1]))
            x, y = A.x + tx, A.y + ty
            # (its foot under the ground there too, on a slope)
            z = min(D.z + GATEHOUSE['tower_dz'], _ground(db, x, y) + GATEHOUSE['tower_foot'] - 40)
            out.append((GATEHOUSE['tower'], (x, y, z, 0.0, 0.0, A.rz + math.pi / 2), GATEHOUSE['tower_s']))
    return out


def _cut_by_module(db, W, M, kpts):
    """W's pieces with the lengths a keep stands in left out: only a length the keep's own walls cover from end to end
    as high as the wall (rays across the wall line at its two ends and its middle meet the keep at every height up to
    the wall's top: Ancylis' keep is a platform 450 high, and the wall over it went, the user 2026-11-03). Left out by the
    keep's box alone, a length
    went where the box reached but the keep's walls did not, and the wall stopped short of the keep, a slot 96-128
    wide either side (lab gaps, 2026-11-03)."""
    import seethrough
    sc = seethrough.Scene()
    memo = {}
    rise = _rise(M['m'])
    Pz = (M['x'], M['y'], 0.0, M['rz'])
    for pc in M['m']['pieces']:
        ri = db.resolve_id(pc[0])
        model = db.recs[ri][5] if ri is not None else None
        if not model:
            continue
        if model not in memo:
            memo[model] = seethrough.model_tris(db, model)
        x, y = _place(Pz, pc[1], pc[2])
        sc.add_model(memo[model], (x, y, pc[3], pc[5], pc[6], M['rz'] + pc[4]), pc[7])
    keep = []
    for p in W['pieces']:
        if p.get('kind') != 'wall' or not p.get('corners') or _sat_depth(kpts, p['corners']) <= KEEP_CUT:
            keep.append(p)
            continue
        q = p['pose']
        ax, ay = q.dir((1.0, 0.0))
        nx, ny = -ay, ax
        cx, cy = sum(c[0] for c in p['corners']) / 4.0, sum(c[1] for c in p['corners']) / 4.0
        covered = True
        for t in (-0.45 * 512, 0.0, 0.45 * 512):
            x, y = cx + ax * t, cy + ay * t
            if not all(sc.nearest_any((x - nx * 600, y - ny * 600, -rise + z), (nx, ny, 0.0), 1200) is not None for z in KEEP_COVER_Z):
                covered = False
                break
        if not covered:
            keep.append(p)
    return keep


def _lay(db, fam, kit, plan_):
    """townwalls.lay with a kit townwalls doesn't know (a house's fort wall): lent to its kit table for the one call."""
    K = tw.kits(db)
    lent = fam not in K
    if lent:
        K[fam] = kit
    try:
        return tw.lay(db, plan_, fam)
    finally:
        if lent:
            K.pop(fam, None)


def _turned_extent(m, F):
    """A keep's reach across and along the castle once turned to face the gate."""
    M = _set_module(m, F, 0.0, 0.0)
    P = (0.0, 0.0, 0.0, M['rz'])
    kb = m['box']
    us, vs = [], []
    for lx in (kb[0], kb[2]):
        for ly in (kb[1], kb[3]):
            wx, wy = _place(P, lx, ly)
            us.append(wx * math.cos(F['a']) + wy * math.sin(F['a']))
            vs.append(-wx * math.sin(F['a']) + wy * math.cos(F['a']))
    return max(us) - min(us), max(vs) - min(vs)


def _front_door(m):
    """The module's way in: its lowest ordinary door (never a trap door: Buckmoth's keep, whose door stands 310 up
    its own piece, was faced and grounded by its roof hatch, the door 213 under the pad, lab c11)."""
    plain = [dd for dd in m['doors'] if not re.search(r'trap|hatch', dd['id'], re.I)]
    return min(plain, key=lambda dd: dd['p'][2]) if plain else m['doors'][0]


DOOR_OVER = (100, 160)         # a keep's front door (its middle) this far over the pad: at the yard, up its own step


def _rise(m):
    """How far the module's origin stands over its pad: so that its front door stands a step over the pad, as the
    game's keep doors stand over their own ground (Moonmoth's 137), wherever the game's keep had its ground (the main
    piece's lay 248 lower across Moonmoth's slope, and the doors came out that far under the pad, lab c03; Umbermoth's
    door is 764 over the ground, on its wall, and carried so it was dropped as a way out into the air, lab c07). The
    survey's older figure when the door's height isn't known."""
    dd = _front_door(m)
    if dd.get('over') is None:
        return m['over']
    return max(DOOR_OVER[0], min(DOOR_OVER[1], dd['over'])) - dd['p'][2]


def _front_axis(m):
    """The way out of the keep's front face, in its own frame (0, 90, 180 or 270 degrees): the side of its box its front
    door stands nearest, as a share of the box's half-widths."""
    front = _front_door(m)
    kb = m['box']
    cx, cy = (kb[0] + kb[2]) / 2.0, (kb[1] + kb[3]) / 2.0
    hx, hy = max(1.0, (kb[2] - kb[0]) / 2.0), max(1.0, (kb[3] - kb[1]) / 2.0)
    dx, dy = (front['p'][0] - cx) / hx, (front['p'][1] - cy) / hy
    if abs(dx) >= abs(dy):
        return 0.0 if dx >= 0 else math.pi
    return math.pi / 2 if dy >= 0 else -math.pi / 2


_TALL = {}


def _mesh_tall(db, m):
    """Whether a keep's own walls rise over a curtain wall's top (KEEP_COVER_Z's top) by KEEP_OVER_WALL: the game's keeps
    stand 1100-1800 over their pads, the wall 890 (the user, 2026-11-03: "usually keeps rise above the walls")."""
    k = (m['fort'], m['main'])
    if k not in _TALL:
        import seethrough
        sc = seethrough.Scene()
        memo = {}
        for pc in m['pieces']:
            ri = db.resolve_id(pc[0])
            model = db.recs[ri][5] if ri is not None else None
            if not model:
                continue
            if model not in memo:
                memo[model] = seethrough.model_tris(db, model)
            sc.add_model(memo[model], (pc[1], pc[2], pc[3], pc[5], pc[6], pc[4]), pc[7])
        kb = m['box']
        z = -_rise(m) + KEEP_COVER_Z[-1] + KEEP_OVER_WALL
        hits = 0
        for ly in range(int(kb[1]), int(kb[3]) + 1, 64):
            if sc.nearest_any((kb[0] - 500.0, float(ly), z), (1.0, 0.0, 0.0), kb[2] - kb[0] + 1000.0) is not None:
                hits += 1
        _TALL[k] = hits >= 3
    return _TALL[k]


def _near_module(M, x, y, clear):
    """Whether (x, y) lies within clear of a placed module's box."""
    kb = M['m']['box']
    c, s_ = math.cos(M['rz']), math.sin(M['rz'])
    dx, dy = x - M['x'], y - M['y']
    lx, ly = dx * c - dy * s_, dx * s_ + dy * c
    return kb[0] - clear <= lx <= kb[2] + clear and kb[1] - clear <= ly <= kb[3] + clear


def _mesh_reach(db, m, rz, dx, dy):
    """How far a module's own walls reach along (dx, dy) from its origin, turned rz: rays at its body's heights from far
    out back towards it, across its width. None when its pieces have no meshes."""
    import seethrough
    sc = seethrough.Scene()
    memo = {}
    rise = _rise(m)
    Pz = (0.0, 0.0, 0.0, rz)
    n = 0
    for pc in m['pieces']:
        ri = db.resolve_id(pc[0])
        model = db.recs[ri][5] if ri is not None else None
        if not model:
            continue
        if model not in memo:
            memo[model] = seethrough.model_tris(db, model)
        x, y = _place(Pz, pc[1], pc[2])
        sc.add_model(memo[model], (x, y, pc[3], pc[5], pc[6], rz + pc[4]), pc[7])
        n += 1
    if not n:
        return None
    kb = m['box']
    span = max(kb[2] - kb[0], kb[3] - kb[1])
    px, py = -dy, dx
    R = 4000.0
    best = None
    t = -span
    while t <= span:
        for z in (150.0, 300.0, 450.0):
            o = (px * t + dx * R, py * t + dy * R, -rise + z)
            h = sc.nearest_any(o, (-dx, -dy, 0.0), 2 * R)
            if h is not None:
                v = R - h[0]
                if best is None or v > best:
                    best = v
        t += 48.0
    return best


def _set_module(m, F, u, v, back=False, face=None):
    """A module placed in the castle frame at (u, v): turned so its way in faces the gate (or face: the point in the
    castle frame it faces), its back edge at v when back."""
    phi = _front_axis(m)
    tu, tv = (face if face is not None else (u, v - 1.0))
    tx, ty = _to_world(F, tu, tv)
    x, y = _to_world(F, u, v)
    target = math.atan2(ty - y, tx - x) if face is not None else F['a'] - math.pi / 2
    # (square to the walls: the keep's own sides along the castle's. Turned so the line from its main piece to its door
    # pointed at the gate, a door off the middle of its face set the whole keep askew of the walls and its back corner
    # clear of the wall line, Fort Estmoth's two keeps 30° out, the user 2026-11-03)
    target = F['a'] + round((target - F['a']) / (math.pi / 2)) * (math.pi / 2)
    rz = (phi - target) % (2 * math.pi)
    if back:
        # (its far edge at v: how far the module reaches behind its origin, turned; and its middle across at u, not its
        # main piece: Indarys's manor stands to one side of its compound, and set by the manor the compound's far
        # building stood through the castle's wall, lab r07)
        P = (0.0, 0.0, 0.0, rz)
        kb = m['box']
        reach = 0.0
        us = []
        for lx in (kb[0], kb[2]):
            for ly in (kb[1], kb[3]):
                wx, wy = _place(P, lx, ly)
                # (along the castle's v: the world direction F['a'] + 90°)
                reach = max(reach, wx * -math.sin(F['a']) + wy * math.cos(F['a']))
                us.append(wx * math.cos(F['a']) + wy * math.sin(F['a']))
        x, y = _to_world(F, u - (min(us) + max(us)) / 2.0, v - reach)
    return {'m': m, 'x': x, 'y': y, 'rz': rz}


def _in_side_wall(db, m, F, W, Wd, Dp, L, inner=None):
    """A second hall standing in the left side wall's line, facing across the yard; the lengths it covers left out.
    In the outer ward's front half when there is an inner ward, clear of it; None when it can't fit."""
    M = _set_module(m, F, 0.0, 0.0, face=(1.0e6, 0.0))
    kb = m['box']
    Pz = (0.0, 0.0, 0.0, M['rz'])
    c, s_ = math.cos(F['a']), math.sin(F['a'])
    rel = [_place(Pz, lx, ly) for lx in (kb[0], kb[2]) for ly in (kb[1], kb[3])]
    us = [x * c + y * s_ for x, y in rel]
    vs = [-x * s_ + y * c for x, y in rel]
    # (the left wall's outer face: the farthest out its lengths reach on that side)
    u_out = -Wd / 2
    for p in W['pieces']:
        if p.get('kind') == 'wall' and p.get('corners'):
            for cx_, cy_ in p['corners']:
                u_ = (cx_ - F['x']) * c + (cy_ - F['y']) * s_
                if u_ < -Wd / 2 + L and u_ < u_out:
                    u_out = u_
    if not _mesh_tall(db, m):
        # (a hall lower than the wall stands against the wall's inner face, the wall whole behind it)
        u_out = max([(cx_ - F['x']) * c + (cy_ - F['y']) * s_ for p in W['pieces'] if p.get('kind') == 'wall' and p.get('corners')
                     for cx_, cy_ in p['corners'] if (cx_ - F['x']) * c + (cy_ - F['y']) * s_ < -Wd / 2 + L / 2] or [u_out])
    mr = _mesh_reach(db, m, M['rz'], -c, -s_)
    u0 = u_out - (min(us) if mr is None else -mr)
    half_v = (max(vs) - min(vs)) / 2.0
    mid_v = (max(vs) + min(vs)) / 2.0
    # (its middle along the wall: the front half, a length clear of the front corner; nearer the middle while clear of
    # the inner ward)
    lo, hi = -Dp / 2 + L + half_v, Dp / 2 - L - half_v
    if lo > hi:
        return None
    vc = max(lo, min(hi, -Dp / 4 if inner is not None else 0.0))
    for _ in range(40):
        x, y = _to_world(F, u0, vc - mid_v)
        Pw = (x, y, 0.0, M['rz'])
        pts = [_place(Pw, lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))]
        if inner is None or _sat_depth(pts, [tuple(q) for q in inner]) <= 0:
            break
        vc -= L / 4
        if vc < lo:
            return None
    M.update(x=x, y=y)
    M['in_wall'] = True
    W['pieces'] = _cut_by_module(db, W, M, pts)
    return M


def _towers(W, kit, F, corners=False):
    """Where the round towers stand: each corner of the wall, the lengths either side of the gate, and a length every
    TOWER_EVERY along longer sides. [{'x', 'y', 'rz', 'dirs': [(dx, dy) the ways the wall runs out of it], 'kind'}]."""
    poly = W['outline']
    n = len(poly)
    out = []
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        din = tw._unit(a[0] - b[0], a[1] - b[1])
        dout = tw._unit(c_[0] - b[0], c_[1] - b[1])
        # (the game's fort corners are its corner piece alone, 26 of 30; a round tower at a corner, as Pelagiad's and
        # Windmoth's, only at a large castle's back corners)
        if not corners or -(b[0] - F['x']) * math.sin(F['a']) + (b[1] - F['y']) * math.cos(F['a']) <= 0:
            continue
        out.append({'x': b[0], 'y': b[1], 'rz': tw._rz_for(kit, (-din[0], -din[1])), 'dirs': [din, dout], 'kind': 'corner', 'run': k})
    gates = [p for p in W['pieces'] if p.get('kind') in ('gate', 'end')]
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        d = tw._unit(b[0] - a[0], b[1] - a[1])
        side = sorted([p for p in W['pieces'] if p.get('run') == k and p.get('kind') == 'wall'],
                      key=lambda p: (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1])
        picks = []
        g = [q for q in gates if q.get('run') == k]
        if g and g[0].get('gatehouse'):
            pass                                 # (the gatehouse has its own towers)
        elif g:
            G = g[0]['pose']
            ga = (G.x - a[0]) * d[0] + (G.y - a[1]) * d[1]
            # (the lengths nearest the gate on either side of it: a tower flanking the gate each side)
            before = [p for p in side if (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1] < ga]
            after = [p for p in side if (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1] > ga]
            if before:
                picks.append(before[-1])
            if after:
                picks.append(after[0])
        else:
            for i in range(TOWER_EVERY // 2, len(side) - 2, TOWER_EVERY):
                if len(side) >= TOWER_EVERY + 2:
                    picks.append(side[i])
        for p in picks:
            q = p['pose']
            if any(math.hypot(q.x - t['x'], q.y - t['y']) < 900 for t in out):
                continue
            out.append({'x': q.x, 'y': q.y, 'rz': q.rz, 'dirs': [d, (-d[0], -d[1])], 'kind': 'gate' if g else 'side', 'run': k, 'on': id(p)})
    # (a wall_tower_01 in the round tower's place goes)
    W['pieces'] = [p for p in W['pieces'] if not (p.get('kind') == 'tower' and any(math.hypot(p['pose'].x - t['x'], p['pose'].y - t['y']) < TOWER_CLEAR for t in out))]
    # (the round tower is the corner and the length it stands on: the wall's own corner piece and the length were left
    # in it, and the buttressed lengths of the game's corner beside it stood as a second tower at every corner, the user
    # 2026-11-03. A buttressed length beside a round tower is a plain one; it has the same ends)
    keep = []
    for p in W['pieces']:
        dd = min((math.hypot(p['pose'].x - t['x'], p['pose'].y - t['y']) for t in out), default=1e9)
        if p.get('kind') in ('corner', 'tower') and dd < TOWER_BESIDE and kit.get('straight') and 'tower' in p['id'].lower():
            q = p['pose']
            p = dict(p, id=kit['straight'], kind='wall', pose=tw.Pose(q.x, q.y, q.z, q.rz, kit['straight']))
            p.pop('corners', None)
        keep.append(p)
    W['pieces'] = keep
    return out


def castle_name(db, style, seed=1):
    import towninside
    pat = STYLES[style]['name']
    for k in range(20):
        stem = towninside.town_name(db, NAME_CULTURE.get(style, 'Imperial'), seed + 7919 * k)
        if re.search(r'fort|legion|keep|castle|manor|garrison', stem, re.I):
            continue                     # (the game's fort names in the mix: "Fort Egion Fort")
        nm = pat % stem
        low = nm.lower()
        if not any(t == 'CELL' and (key == low or key.startswith(low + ',')) for t, key in db.by_key):
            return nm
    return pat % ('New %s' % style)


# ------------------------------------------------------------------------------------------------ what it will hold
def _tail(db, key):
    nm = (mapdata.cell_info(db, key) or {}).get('name') or key
    return nm.split(',', 1)[1].strip() if ',' in nm else ''


def room_name(db, name, gkey, role, second=False):
    t = _tail(db, gkey)
    if not t or t.lower() in ('interior', 'keep', 'main keep') or second and role == 'keep':
        t = 'Hall' if second else {'keep': 'Keep', 'prison': 'Prison'}.get(role, 'Keep')
    return ('%s, %s' % (name, t))[:63]


def _rooms(db, S, P):
    out = []
    for mi, M in enumerate(P['modules']):
        for g in M['m']['network']:
            out.append({'name': room_name(db, P['name'], g, cs.role_of(g), mi > 0), 'role': cs.role_of(g), 'from': g})
    if P['towers']:
        out.append({'name': '%s, Towers' % P['name'], 'role': 'towers', 'from': '%d tower rooms' % len(P['towers'])})
    return out


def _figures(P):
    """The castle's own figures, to set beside the game's."""
    W = P.get('W') or {}
    ps = W.get('pieces') or []
    f = {'wall_size': [round(v) for v in P.get('size_wd') or ()], 'wall_pieces': len(ps),
         'gates': sum(1 for p in ps if p.get('kind') in ('gate', 'end')), 'towers': len(P['towers']) + sum(1 for p in ps if p.get('kind') == 'tower'),
         'keeps': len(P['modules']), 'interiors': sum(len(M['m']['network']) for M in P['modules']) + (1 if P['towers'] else 0),
         'doors_out': sum(len(M['m']['doors']) for M in P['modules']) + sum(len(t['dirs']) + 1 for t in P['towers'])}
    return f


def _game_figures(S, style):
    fs = [f for f in S['forts'] if f['style'] == style]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    return {'forts': len(fs), 'interiors': med([f['interiors'] for f in fs]), 'doors_out': med([f['doors_out'] for f in fs]),
            'links': med([f['links'] for f in fs]), 'npcs': med([f['npcs'] for f in fs]),
            'wall_size': [med([min(f['wall_size']) for f in fs if f.get('wall_size') and f['wall']['pieces'] >= 12]),
                          med([max(f['wall_size']) for f in fs if f.get('wall_size') and f['wall']['pieces'] >= 12])],
            'towers': med([f['wall']['towers'] for f in fs if f.get('wall')]), 'examples': [f['name'] for f in fs][:8]}


def _preview(db, P):
    """For the map: [[kind, [[x, y] x4]]] for every piece outside, the doors as points."""
    memo = {}
    out = []
    for p in (P.get('W') or {}).get('pieces') or ():
        cs_, _b = tw._box(db, p['id'], p['pose'], memo)
        if cs_:
            out.append([p['kind'], [[round(x), round(y)] for x, y in cs_]])
    for rid, q in (P.get('W') or {}).get('extra_preview') or ():
        cs_, _b = tw._box(db, rid, q, memo)
        if cs_:
            out.append(['gate', [[round(x), round(y)] for x, y in cs_]])
    for t in P['towers']:
        r = 180
        out.append(['bigtower', [[round(t['x'] + r * math.cos(k * math.pi / 2 + math.pi / 4) * 1.41), round(t['y'] + r * math.sin(k * math.pi / 2 + math.pi / 4) * 1.41)] for k in range(4)]])
    doors = []
    for M in P['modules']:
        Pz = (M['x'], M['y'], 0.0, M['rz'])
        for pc in M['m']['pieces']:
            cs_, _b = tw._box(db, pc[0], tw.Pose(*_place(Pz, pc[1], pc[2]), 0.0, M['rz'] + pc[4]), memo)
            if cs_:
                out.append(['keep', [[round(x), round(y)] for x, y in cs_]])
        for dd in M['m']['doors']:
            doors.append([round(v) for v in _place(Pz, dd['p'][0], dd['p'][1])])
    for t in P['towers']:
        for dx, dy in t['dirs']:
            doors.append([round(t['x'] + dx * TOWER['arch_r']), round(t['y'] + dy * TOWER['arch_r'])])
    poly = (P.get('W') or {}).get('outline') or []
    if not poly and out:
        # (a stronghold has no wall round it: its outline is the box its pieces stand in)
        xs = [p[0] for _k, cs_ in out for p in cs_]
        ys = [p[1] for _k, cs_ in out for p in cs_]
        poly = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
    return {'pieces': out, 'doors': doors, 'outline': [[round(x), round(y)] for x, y in poly]}


# ------------------------------------------------------------------------------------------------ building
PROGRESS = {'on': False, 'what': '', 'frac': 0.0}


def progress():
    return dict(PROGRESS)


def make(db, outline, style='Imperial', size='medium', seed=1, name='', people=True, rooms='furnished', gate=None):
    """The castle built (plan() laid out), its rooms as ROOMS says. One Undo."""
    PROGRESS.update(on=True, what='Planning', frac=0.0)
    try:
        return _make(db, outline, style, size, seed, name, people, rooms if rooms in ROOMS else 'furnished', gate)
    finally:
        PROGRESS.update(on=False, what='', frac=0.0)


def _say(what, frac):
    PROGRESS.update(what=what, frac=frac)


class _Writer:
    """New refs outside, each in the cell under it, as one change; doors kept by a name to link them after."""

    def __init__(self, db):
        self.db = db
        self.mine = db.project.plugin.lower()
        self.ri = {}
        self.refs = []
        self.cells = set()
        self.gid = None

    def put(self, rid, pos, s=1.0, cell=None):
        import editing
        from project import set_ref_pos, zs
        low = rid.lower()
        if low not in self.ri:
            self.ri[low] = self.db.resolve_id(rid)
        ri = self.ri[low]
        if ri is None:
            return None
        key = cell or '#%d,%d' % (math.floor(pos[0] / 8192.0), math.floor(pos[1] / 8192.0))
        try:
            c, _r = editing._cell(self.db, key)
        except EditError:
            return None
        rk = self.db.project.new_ref_key()
        pos = tuple(float(v) for v in pos[:3]) + (float(pos[3]) if len(pos) > 3 else 0.0, float(pos[4]) if len(pos) > 4 else 0.0, float(pos[-1]) % (2 * math.pi))
        editing._store(c, rk, self.mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(self.db.recs[ri][1]))], pos, s))
        if key.startswith('#'):
            self.gid = self.gid or rk
            self.db.project.town_parts[rk] = self.gid
        self.refs.append((key, rk))
        self.cells.add(key)
        return key, rk, pos


def _link(db, cell, rk, dest, pos):
    import doors
    import editing
    c, refs = editing._cell(db, cell)
    ref = refs.get(rk)
    if ref is None:
        return False
    editing._store(c, rk, ref['origin'], ref['idx'], doors._set_link(ref['subs'], dest, [float(v) for v in pos[:6]]))
    return True


def _facing(dx, dy):
    """An actor's turn to face world direction (dx, dy)."""
    return math.atan2(dx, dy) % (2 * math.pi)


def _make(db, outline, style, size, seed, name, people, rooms='furnished', gate=None):
    import editing
    import create
    import doors
    editing._require_project(db)
    P = plan(db, outline, style, size, seed, name, gate)
    name = P['name']
    S = cs.survey(db)
    stack = getattr(db.project, 'undo_stack', [])
    n0 = len(stack)
    rng = random.Random('%s|%s|make' % (style, seed))
    tname = None
    # names: free of the game's places and of each other
    taken = set()

    def free(nm):
        base, k = nm, 2
        while nm.lower() in taken or any(v not in db.dead for v in db.by_key.get(('CELL', nm.lower()), [])) or nm.lower() in db.project.cells:
            nm = '%s %d' % (base, k)
            k += 1
        taken.add(nm.lower())
        return nm
    # ---- the ground: even under the wall, a pad under each keep and tower
    _say('Levelling the ground', 0.08)
    W = P['W']
    # (drawn inside a town of the mod's own: its buildings there make way)
    if W is not None and W.get('outline'):
        site = W['outline']
    else:
        site = []
        for M in P['modules']:
            kb = M['m']['box']
            site += [_place((M['x'], M['y'], 0.0, M['rz']), lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))]
        site = site[:4]
    try:
        _clear_town(db, site)
    except Exception as e:
        print('castle in a town:', e)
    # (the yard one level, the walls and keeps set on it: the ground inside rose to a hall in a mound, the user
    # 2026-11-03 "usually the inside of the keep is pretty flat")
    yard = None
    if W is not None and W.get('outline') and style != 'Stronghold':
        yard = _yard_level(db, W['outline'])
        try:
            _pad(db, [(W['outline'], yard)])
        except Exception as e:
            print('castle yard:', e)
    skip = set()
    if W is not None:
        try:
            tw.level_ground(db, W, skip, tol=CASTLE_LEVEL_TOL)
        except Exception as e:
            print('castle wall ground:', e)
        # (the wall's levels known before the keep's pad: a keep in the wall line stands at the wall's level)
        db.sync_project()
        W = tw.grounded(db, W)
    pads = []
    for M in P['modules']:
        kb = M['m']['box']
        Pz = (M['x'], M['y'], 0.0, M['rz'])
        corners = [_place(Pz, lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))]
        zs_ = sorted(_ground(db, *_place(Pz, (kb[0] + kb[2]) * f / 2, (kb[1] + kb[3]) * g / 2)) for f in (0, 1, 2) for g in (0, 1, 2))
        M['ground'] = zs_[len(zs_) // 2] if style != 'Stronghold' else zs_[len(zs_) // 3]
        if M.get('in_wall') and W is not None:
            near = sorted((p for p in W['pieces'] if p.get('kind') in ('wall', 'corner')), key=lambda p: math.hypot(p['pose'].x - M['x'], p['pose'].y - M['y']))[:2]
            if near:
                M['ground'] = max(p['pose'].z for p in near) + KEEP_UP - _rise(M['m'])
                # (its pad never over the wall's top nor under its foot: Umbermoth's hall (its rise -220) set its pad over
                # the wall's top, the ground round it buried the lengths either side, a slot in the wall line, lab gaps)
                wz = min(p['pose'].z for p in near)
                M['ground'] = max(wz - WALL_FOOT, min(wz + WALL_TOP - PAD_SHOW, M['ground']))
        if yard is not None:
            M['ground'] = yard
        pads.append((corners, M['ground']))
    for t in P['towers']:
        pass                                     # (towers stand on the wall's evened line)
    try:
        _pad(db, pads)
    except Exception as e:
        print('castle pads:', e)
    db.sync_project()
    try:
        import townbuild
        yard = [list(W['outline'])] if W is not None and W.get('outline') else []
        townbuild._clear_ground(db, {'plots': [{'rect': c, 'b': True} for c in yard + [c for c, _z in pads]], 'streets': [], 'roads': []}, W)
    except Exception as e:
        print('castle clearing:', e)
    # ---- outside: the wall, the towers, the keeps
    _say('Setting the wall', 0.2)
    wr = _Writer(db)
    if W is not None:
        db.sync_project()
        _cut_town_wall(db, W['outline'])
        tw.drop_doubled(db, W)               # (where a town's wall already stands, it is the castle's too)
        for p in W['pieces']:
            q = p['pose']
            wr.put(p['id'], (q.x, q.y, q.z, 0.0, 0.0, q.rz))
        for rid, pos, s_ in _gatehouse_make(db, W):
            wr.put(rid, pos, s_)
    tdoors = []                                  # [(tower index, kind, (cell, rk, pos), arrive outside)]
    if P['towers'] and W is not None:
        _say('Raising the towers', 0.3)
        lv = [(p['pose'].x, p['pose'].y, p['pose'].z) for p in W['pieces'] if p.get('kind') in ('wall', 'corner')]
        for i, t in enumerate(P['towers']):
            near = sorted(lv, key=lambda q: math.hypot(q[0] - t['x'], q[1] - t['y']))[:2]
            wz = max(q[2] for q in near) if near else _ground(db, t['x'], t['y']) - 200
            tdoors += _tower(db, wr, t, wz, i)
    mdoors = []                                  # [(module index, door entry, (cell, rk, pos))]
    walk_cand = {}                               # {module index: [its upper doors that open onto no walk of ours]}
    _say('Raising the keep', 0.4)
    for mi, M in enumerate(P['modules']):
        m = M['m']
        Z = M['ground'] + _rise(m)
        Pz = (M['x'], M['y'], Z, M['rz'])
        M['pose'] = Pz
        for pc in m['pieces']:
            x, y = _place(Pz, pc[1], pc[2])
            wr.put(pc[0], (x, y, Z + pc[3], pc[5], pc[6], M['rz'] + pc[4]), pc[7])
        for dd in m['doors']:
            x, y = _place(Pz, dd['p'][0], dd['p'][1])
            if not _stood_on(db, M, Pz, dd, W):
                if dd.get('back') and dd.get('to') in m['network'] and not re.search(r'trap|hatch', dd['id'], re.I):
                    walk_cand.setdefault(mi, []).append(dd)
                continue                         # (a door out onto the game fort's walk or bridge, not here: its room
                                                 # leads out by the keep's front door instead)
            if rooms != 'none' and dd.get('to') and (dd['to'] not in m['network'] or not db.by_key.get(('CELL', dd['to']))):
                continue                         # (a door into a room the castle hasn't: it led nowhere, an
                                                 # ex_nord_door_01 on a Redoran manor, lab c01)
            got = wr.put(dd['id'], (x, y, Z + dd['p'][2], 0.0, 0.0, M['rz'] + dd['p'][3]), dd.get('s') or 1.0)
            if got:
                mdoors.append((mi, dd, got))
    if W is not None:
        mdoors += _walk_doors(db, wr, P, W, walk_cand)
    if W is not None:
        _say('Setting out the bailey', 0.45)
        try:
            for rid, pos, s_ in _bailey(db, P, W, rng):
                wr.put(rid, pos, s_)
        except Exception as e:
            print('castle bailey:', e)
    editing.commit(db, 'Built %s outside: %d pieces' % (name, len(wr.refs)))
    # ---- inside
    _say('Copying the rooms', 0.5)
    links = []                                   # (cell, rk, destination name, position)
    names = {}
    keys = {}
    to_towers = []                               # (cell, rk) inside doors the game led to its towers
    loose = []                                   # inside doors that led out where this castle has no door
    for mi, M in enumerate(P['modules']) if rooms != 'none' else ():
        m = M['m']
        net = [g for g in m['network'] if db.by_key.get(('CELL', g))]
        for g in net:
            nm = free(room_name(db, name, g, cs.role_of(g), mi > 0))
            try:
                # (the game room's shell and doors only: its furnishing and decor are never copied)
                keys[(mi, g)] = create.create_interior(db, g, nm, 'empty', None)
                _strip(db, keys[(mi, g)])
                names[(mi, g)] = nm
            except EditError as e:
                print('castle room:', g, e)
        mine = [(dd, got) for j, dd, got in mdoors if j == mi]
        for g in net:
            if (mi, g) not in keys:
                continue
            tm, cm = mapdata.cellmap(db, g), mapdata.cellmap(db, keys[(mi, g)])
            copies = [r for r in cm['refs'] if r['type'] == 'DOOR']
            for r in tm['refs']:
                if r['type'] != 'DOOR' or not r.get('to'):
                    continue
                cr = min(copies, key=lambda o: math.dist(o['p'][:3], r['p'][:3]), default=None)
                if cr is None or math.dist(cr['p'][:3], r['p'][:3]) > 2:
                    continue
                to = r['to']
                tc = (to.get('cell') or '').lower()
                here = (keys[(mi, g)], cr['k'])
                if tc and (mi, tc) in names:
                    links.append(here + (names[(mi, tc)], [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']]))
                elif tc and cs.role_of(tc) == 'towers':
                    to_towers.append(here)
                elif tc:
                    links.append(here + (to['cell'], [to['x'], to['y'], to['z'], 0.0, 0.0, to['rz']]))      # (on into the game's own)
                else:
                    ext = next((got for dd, got in mine if dd['to'] == g and dd.get('back') == r['k']), None)
                    dd = next((dd for dd, got in mine if dd['to'] == g and dd.get('back') == r['k']), None)
                    if ext is not None:
                        links.append(here + ('', dd['walk_out'] if dd.get('walk_out') else _out_of(db, M['pose'], dd, ext, M)))
                    else:
                        loose.append(here + (g,))
        for dd, got in mine:
            if (mi, dd['to']) in names and dd.get('arrive'):
                a = dd['arrive']
                links.append((got[0], got[1], names[(mi, dd['to'])], [a[0], a[1], a[2], 0.0, 0.0, a[3]]))
    # (an inside door that led out by a door this castle hasn't: out by the keep's own front door)
    for ck, rk, g in loose:
        mi = next(j for (j, gg) in keys if keys[(j, gg)] == ck)
        ext = [(dd, got) for j, dd, got in mdoors if j == mi and dd['to'] == g] or [(dd, got) for j, dd, got in mdoors if j == mi]
        if ext:
            dd, got = ext[0]
            links.append((ck, rk, '', _out_of(db, P['modules'][mi]['pose'], dd, got, P['modules'][mi])))
    # ---- the towers: a spiral-stair room for each, in one place
    tower_key = None
    if P['towers'] and tdoors and rooms != 'none':
        _say('Making the tower rooms', 0.7)
        tname = free('%s, Towers' % name)
        tower_key, tl = _tower_rooms(db, S, P, tname, tdoors, to_towers, names, keys, rng)
        links += tl
    editing.commit(db, 'Copied the rooms of %s' % name)
    # ---- every door linked
    _say('Linking the doors', 0.85)
    for ck, rk, dest, pos in links:
        if callable(pos):
            pos = pos()
        if pos:
            _link(db, ck, rk, dest, pos)
    editing.commit(db, 'Linked the doors of %s' % name)
    try:
        import doors as doors_
        doors_.face_arrivals(db, sorted(wr.cells))      # (every arrival at the face of the door it pairs with)
    except Exception as e:
        print('door arrivals:', e)
    # ---- furnished by the Workshop's own furnisher, each room by its kind
    placed = 0
    if rooms == 'furnished':
        _say('Furnishing the rooms', 0.88)
        for (mi, g), k in sorted(keys.items()):
            placed += furnish_shell(db, k, g, seed=zlib.crc32(('%s|%s' % (seed, k)).encode()))
        if tower_key:
            placed += furnish_shell(db, tower_key, None, seed=seed)
        editing.commit(db, 'Furnished the rooms of %s' % name)
    # ---- people
    folks = 0
    if people and rooms == 'furnished':
        _say('Placing the people', 0.9)
        folks = _people(db, keys, names, seed)
    n_in = len(keys) + (1 if tower_key else 0)
    if len(stack) > n0:
        editing.fold(db, len(stack) - n0, 'Built %s, a %s: %d pieces outside, %d interiors%s' % (
            name, STYLES[style]['label'], len(wr.refs), n_in, (', %d people' % folks) if folks else ''))
    return {'name': name, 'pieces': len(wr.refs), 'cells': sorted(wr.cells), 'interiors': n_in, 'people': folks, 'furnished': placed,
            'sources': [[k, g] for (mi, g), k in sorted(keys.items())],
            'rooms': sorted(set(names.values())) + ([tname] if tower_key else []), 'links': len(links), 'fig': P['fig'], 'game': P['game'],
            'faults': P['faults'][:6]}


# ------------------------------------------------------------------------------------------------ the bailey
# What the game's forts keep inside their walls besides the keep (lab j04, 14 Legion forts): stores of crates, barrels
# and sacks, training dummies and targets, a cart, a well, benches and tables, an anvil and bellows, flagpoles, lamps,
# an awning; 30-60 things in a yard of 6-10 Mu². A made fort's bailey stood bare. Learnt as the groups the game set
# together, each kept whole in its own frame (the wall it backs onto, or the open yard) and laid in this castle's own
# spots, never where the game had it.
BAILEY = re.compile(r'crate|barrel|sack|keg|basket|chest|cart|wagon|target|dummy|practice|anvil|forge|bellows|grindstone|bench|'
                    r'table|stool|chair|well|trough|flagpole|flag_|banner|signbase|lantern|torch|brazier|awning|canopy|_rack|hay|'
                    r'stocks|cage|firepit|campfire|woodpile|bucket', re.I)
NOT_BAILEY = re.compile(r'hook|hang|wall|window|door|marker|collision|ruin|rubble|broken|_brk|constr|scaffold', re.I)
BAILEY_GROUP = 260             # (things this near each other are one set)
BAILEY_UP = 160                # (standing on the ground or on a set's own crates: no higher)
BAILEY_BACK = 900              # (a set this near a wall backs onto it)
BAILEY_ROAD = 520              # (the way from the gate to the keep kept this clear either side)
BAILEY_THING = 48              # (a thing's own room on the ground, for the free ground test)
_bsets = {}


def _bailey_sets(db, style):
    """The game forts' bailey sets for a style and their density: ([{'things': [(id, lx, ly, dz, rz, s)], 'back': d or
    None, 'r'}], things per square unit)."""
    S = cs.survey(db)
    key = (id(db.recs), style)
    if key in _bsets:
        return _bsets[key]
    K = tw.kits(db)
    wallm = set()
    for k in K.values():
        wallm |= set(k['models'])
    sets, n_all, area = [], 0, 0.0
    for f in S['forts']:
        wb = f.get('wall_box')
        if f['style'] != style or not wb or (f.get('wall') or {}).get('pieces', 0) < 12:
            continue
        x0, y0, x1, y1 = wb[0] + 300, wb[1] + 300, wb[2] - 300, wb[3] - 300
        if x1 - x0 < 1000 or y1 - y0 < 1000 or (x1 - x0) * (y1 - y0) > 16e6:
            continue                     # (a walled town, not a fort's yard: Firewatch, Hawkmoth)
        area += (x1 - x0) * (y1 - y0)
        got = []
        cells = {'#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0)) for x in (x0, x1) for y in (y0, y1)}
        for ck in cells:
            for r in mapdata.cellmap(db, ck).get('refs') or ():
                x, y = r['p'][0], r['p'][1]
                low = r['id'].lower()
                if not (x0 < x < x1 and y0 < y < y1) or low in wallm or r['type'] in ('NPC_', 'CREA', 'LEVC', 'DOOR'):
                    continue
                if r['type'] in mapdata.ITEM_TYPES or not BAILEY.search(low) or NOT_BAILEY.search(low):
                    continue
                g = mapdata.terrain_z(db, x, y)
                if g is None or not -40 <= r['p'][2] - g <= BAILEY_UP:
                    continue
                got.append((r, r['p'][2] - g))
        n_all += len(got)
        # (one set: things joined within BAILEY_GROUP of each other)
        left = list(got)
        while left:
            grp = [left.pop()]
            i = 0
            while i < len(grp):
                a = grp[i][0]['p']
                near = [t for t in left if math.hypot(t[0]['p'][0] - a[0], t[0]['p'][1] - a[1]) <= BAILEY_GROUP]
                for t in near:
                    left.remove(t)
                grp += near
                i += 1
            cx = sum(t[0]['p'][0] for t in grp) / len(grp)
            cy = sum(t[0]['p'][1] for t in grp) / len(grp)
            # (its frame: +y into the yard from the wall side nearest it)
            sides = [(cx - x0, (1.0, 0.0)), (x1 - cx, (-1.0, 0.0)), (cy - y0, (0.0, 1.0)), (y1 - cy, (0.0, -1.0))]
            d, n = min(sides)
            d += 300
            a = math.atan2(n[0], n[1])
            c, s = math.cos(a), math.sin(a)
            th = []
            for r, dz in grp:
                dx, dy = r['p'][0] - cx, r['p'][1] - cy
                # (into the set's frame: turned back by a, the game's clockwise turn)
                th.append((r['id'], dx * c - dy * s, dx * s + dy * c, dz, (r['p'][5] - a) % (2 * math.pi), r.get('s') or 1.0))
            rad = max([math.hypot(t[1], t[2]) for t in th] + [0.0]) + 80
            if rad > 700:
                continue                 # (a long row strung along a wall: not one set)
            sets.append({'things': th, 'back': d if d <= BAILEY_BACK else None, 'r': rad})
    out = (sets, n_all / area if area else 0.0)
    _bsets[key] = out
    return out


def _bailey(db, P, W, rng):
    """Sets for the bailey: [(id, (x, y, z, 0, 0, rz), s)], laid on free ground inside the wall."""
    sets, dens = _bailey_sets(db, P['style'])
    poly = (W or {}).get('outline') or []
    if not sets or not dens or len(poly) < 3:
        return []
    F = P['frame']
    Wd, Dp = P.get('size_wd') or (0.0, 0.0)
    # (what is taken: the wall's pieces, the keep and what stands with it, the towers, the gate's way to the keep)
    taken = []
    memo = {}
    for p in W['pieces']:
        c_, _b = tw._box(db, p['id'], p['pose'], memo)
        if c_:
            taken.append(('quad', c_, 60.0))
    for M in P['modules']:
        kb = M['m']['box']
        taken.append(('quad', [_place((M['x'], M['y'], 0.0, M['rz']), lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))], 260.0))
    for t in P['towers']:
        taken.append(('disc', (t['x'], t['y']), 420.0))
    gx, gy = _to_world(F, 0.0, -Dp / 2.0)
    kx, ky = (P['modules'][0]['x'], P['modules'][0]['y']) if P['modules'] else (F['x'], F['y'])
    road = (gx, gy, kx, ky)
    area = Wd * Dp
    for M in P['modules']:
        kb = M['m']['box']
        area -= (kb[2] - kb[0]) * (kb[3] - kb[1])
    want = int(dens * max(0.0, area))

    def seg_d(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - ax - dx * t, py - ay - dy * t)

    def free(x, y, r):
        if not tw._inside(poly, (x, y)) or seg_d(x, y, *road) < BAILEY_ROAD + r:
            return False
        for kind, v, pad in taken:
            if kind == 'disc':
                if math.hypot(x - v[0], y - v[1]) < pad + r:
                    return False
            else:
                cx_ = sum(q[0] for q in v) / 4.0
                cy_ = sum(q[1] for q in v) / 4.0
                R = max(math.hypot(q[0] - cx_, q[1] - cy_) for q in v)
                if math.hypot(x - cx_, y - cy_) < R + pad + r and _in_quad(v, x, y, pad + r):
                    return False
        return True
    # spots: along each side, a set's own distance in from the wall, facing the yard; and in the open yard
    n = len(poly)
    cx0, cy0 = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    out, laid = [], 0
    order = list(range(len(sets)))
    rng.shuffle(order)
    tries = 0
    used = {}
    while laid < want and tries < 1500:
        tries += 1
        S_ = sets[order[tries % len(order)]]
        if used.get(id(S_), 0) >= 3:
            continue                     # (the same set at most three times)
        if S_['back'] is not None:
            k = rng.randrange(n)
            a, b = poly[k], poly[(k + 1) % n]
            d = tw._unit(b[0] - a[0], b[1] - a[1])
            nrm = (-d[1], d[0])
            if (cx0 - a[0]) * nrm[0] + (cy0 - a[1]) * nrm[1] < 0:
                nrm = (-nrm[0], -nrm[1])
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            t = rng.uniform(0.15, 0.85) * L
            x, y = a[0] + d[0] * t + nrm[0] * S_['back'], a[1] + d[1] * t + nrm[1] * S_['back']
            ang = math.atan2(nrm[0], nrm[1])
        else:
            x, y = cx0 + rng.uniform(-Wd / 2, Wd / 2) * 0.8, cy0 + rng.uniform(-Dp / 2, Dp / 2) * 0.8
            ang = rng.uniform(0, 2 * math.pi)
        c, s = math.cos(ang), math.sin(ang)
        placed = []
        # (each thing of the set on free ground, not the set's whole round: tested as one disc, a set backing onto a
        # wall always met it, and a fort's bailey held a third of the game's, lab r05)
        for rid, lx, ly, dz, rz, sc in S_['things']:
            wx, wy = x + lx * c + ly * s, y - lx * s + ly * c
            g = mapdata.terrain_z(db, wx, wy)
            if g is None or not free(wx, wy, BAILEY_THING):
                placed = None
                break
            placed.append((rid, (wx, wy, g + dz, 0.0, 0.0, (rz + ang) % (2 * math.pi)), sc))
        if not placed:
            continue
        # (on ground too steep for it: no)
        zs = [mapdata.terrain_z(db, x + S_['r'] * math.sin(k * math.pi / 2), y + S_['r'] * math.cos(k * math.pi / 2)) for k in range(4)]
        zs = [z for z in zs if z is not None]
        if zs and max(zs) - min(zs) > 0.35 * 2 * S_['r']:
            continue
        out += placed
        laid += len(placed)
        used[id(S_)] = used.get(id(S_), 0) + 1
        taken.append(('disc', (x, y), S_['r']))
    return out


def _sat_depth(A, B):
    # (how deep two convex footprints cut into each other; negative: apart by that much)
    best = 1e9
    for P in (A, B):
        n = len(P)
        for i in range(n):
            ex, ey = P[(i + 1) % n][0] - P[i][0], P[(i + 1) % n][1] - P[i][1]
            h = math.hypot(ex, ey) or 1.0
            nx, ny = -ey / h, ex / h
            pa = [x * nx + y * ny for x, y in A]
            pb = [x * nx + y * ny for x, y in B]
            best = min(best, min(max(pa), max(pb)) - max(min(pa), min(pb)))
    return best


def _in_quad(q, x, y, pad):
    """Whether (x, y) lies within pad of a convex quad."""
    inside = True
    for i in range(4):
        (x1, y1), (x2, y2) = q[i], q[(i + 1) % 4]
        ex, ey = x2 - x1, y2 - y1
        L = math.hypot(ex, ey) or 1.0
        # (signed distance outward, whichever way round the quad runs)
        dist = ((x - x1) * ey - (y - y1) * ex) / L
        sgn = 1.0 if ((q[(i + 2) % 4][0] - x1) * ey - (q[(i + 2) % 4][1] - y1) * ex) < 0 else -1.0
        if dist * sgn > pad:
            inside = False
            break
    return inside


CLEAR_OUT = 300                # (a made town's buildings this near the castle's wall, or inside it, make way for it)


def _clear_town(db, poly, keep=()):
    """A castle drawn inside a town of the mod's own: the town's buildings it stands on are taken away, with what
    stands with them and the rooms behind their doors, as the castle takes their ground (drawn in a town's middle,
    the castle went up through its houses, lab b03). keep: ref keys of the castle's own. (buildings, rooms) taken."""
    import townplan
    if len(poly) < 3:
        return 0, 0
    outer = townplan.inset([tuple(p) for p in poly], -CLEAR_OUT)
    p = db.project
    xs, ys = [q[0] for q in outer], [q[1] for q in outer]
    groups = {}
    for gx in range(int(min(xs) // 8192) - 1, int(max(xs) // 8192) + 2):
        for gy in range(int(min(ys) // 8192) - 1, int(max(ys) // 8192) + 2):
            ck = '#%d,%d' % (gx, gy)
            if ck not in p.cells:
                continue
            for r in mapdata.cellmap(db, ck).get('refs') or ():
                g = p.town_parts.get(r['k'])
                if g and r.get('new') and r['k'] not in keep:
                    groups.setdefault(g, []).append((ck, r))
    M = tw.wall_models(db)
    ways = {GROUND['frame'].lower(), GROUND['door'].lower(), TOWER['arch'].lower(), TOWER['door'].lower()}
    # (a building, not the town wall's keep doors, which _cut_town_wall sees to: a group of only those; a building's
    # own door is often the same model, and a keep house carries a wallent or two)
    gone = [g for g, rs in groups.items() if any(tw._inside(outer, (r['p'][0], r['p'][1])) for _ck, r in rs)
            and not all(r['id'].lower() in M or r['id'].lower() in ways for _ck, r in rs)]
    if not gone:
        return 0, 0
    rooms = set()
    for g in gone:
        for ck, r in groups[g]:
            to = r.get('to') or {}
            if r['type'] == 'DOOR' and to.get('cell') and to['key'] in p.cells:
                rooms.add(to['key'])
            c = p.cells.get(ck)
            if c and r['k'] in (c.get('refs') or {}):
                c['refs'].pop(r['k'])
                p.town_parts.pop(r['k'], None)
    # (a room behind a taken building goes with it, and the rooms only it led to)
    for k in list(rooms):
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)
    db.sync_project()
    return len(gone), len(rooms)


CUT_IN = 200                   # (a made town wall's pieces this far inside a castle's wall are the castle's ground now)


def _cut_town_wall(db, poly):
    """A town wall of the mod's own running into a castle's bailey stops at the castle's wall: its pieces inside are
    taken out, and the doors set in them (a castle drawn across a made town's wall ran the town's wall on through its
    yard, two walls crossing, lab r06). The count."""
    import townplan
    if len(poly) < 3:
        return 0
    inner = townplan.inset([tuple(p) for p in poly], CUT_IN)
    if len(inner) < 3:
        return 0
    M = tw.wall_models(db)
    ways = {GROUND['frame'].lower(), GROUND['door'].lower(), TOWER['arch'].lower(), TOWER['door'].lower()}
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    p = db.project
    n = 0
    for gx in range(int(min(xs) // 8192), int(max(xs) // 8192) + 1):
        for gy in range(int(min(ys) // 8192), int(max(ys) // 8192) + 1):
            ck = '#%d,%d' % (gx, gy)
            c = p.cells.get(ck)
            if not c:
                continue
            for r in mapdata.cellmap(db, ck).get('refs') or ():
                low = r['id'].lower()
                if not r.get('new') or not (low in M or low in ways) or not tw._inside(inner, (r['p'][0], r['p'][1])):
                    continue
                if r['k'] in (c.get('refs') or {}):
                    c['refs'].pop(r['k'])
                    p.town_parts.pop(r['k'], None)
                    n += 1
    if n:
        db.sync_project()
    return n


WALK_REACH = 600.0             # (a length's end this near a keep's box: its walk may run on into the keep's face)
WALK_DOOR_OUT = 8.0            # (a walk door this far out of the keep's face)
WALK_DROP = 120                # (a keep door's way out this far over a wall walk at most: it opens onto the walk)
AIR = 200                      # (a door's way out this far over the ground needs something of the keep's under it)


def _keep_scene(db, M):
    import seethrough
    if 'scene' not in M:
        Pz = M['pose']
        sc = seethrough.Scene()
        memo = {}
        for pc in M['m']['pieces']:
            ri = db.resolve_id(pc[0])
            model = db.recs[ri][5] if ri is not None else None
            if not model:
                continue
            if model not in memo:
                memo[model] = seethrough.model_tris(db, model)
            px, py = _place(Pz, pc[1], pc[2])
            sc.add_model(memo[model], (px, py, Pz[2] + pc[3], pc[5], pc[6], Pz[3] + pc[4]), pc[7])
        M['scene'] = sc
    return M['scene']


def _walk_doors(db, wr, P, W, cand):
    """Where the wall walk runs into a keep: an arch and a door in the keep's face at the walk, as the round towers have
    theirs, leading into the room the keep's own upper door led to (the game's keep doors opened onto its fort's walk on
    other sides; the user 2026-11-03: "the wall tops have doors leading into towers and keeps"). [(module index, door
    entry with walk_out, (cell, rk, pos))]."""
    T = TOWER
    out = []
    for mi, M in enumerate(P['modules']):
        if not M.get('in_wall') or 'pose' not in M:
            continue
        # (only into the room its own upper door led to, on the walk's floor: never a door that doesn't match its
        # inside, the user 2026-11-03)
        into = list(cand.get(mi) or [])
        if not into:
            continue
        sc = _keep_scene(db, M)
        joints = []
        for p in W['pieces']:
            if p.get('kind') not in ('wall', 'corner'):
                continue
            q = p['pose']
            if _near_module(M, q.x, q.y, 0.0):
                continue
            ax, ay = q.dir((1.0, 0.0))
            for sg in (1, -1):
                ex, ey = q.x + sg * ax * 256, q.y + sg * ay * 256
                if not _near_module(M, ex, ey, WALK_REACH):
                    continue
                # (along the walk from this length's middle until the keep's own face, at the walk's height)
                d = (sg * ax, sg * ay)
                az = q.z + T['over_wall'] + T['arch_dz']
                h = sc.nearest_any((q.x, q.y, az + 100), (d[0], d[1], 0.0), 256 + 2 * WALK_REACH)
                if h is None:
                    continue
                fx, fy = q.x + d[0] * h[0], q.y + d[1] * h[0]
                if any(math.hypot(fx - j[0], fy - j[1]) < 300 for j in joints):
                    continue
                joints.append((fx, fy, az, d))
        for (fx, fy, az, d), dd in zip(joints, into):
            arz = math.atan2(-d[1], d[0])
            wr.put(T['arch'], (fx, fy, az, 0.0, 0.0, arz))
            # (a flat door at the keep's face, just out of it: set 13 in, as in a tower's shell, it stood in the masonry)
            lz = T['door_in'][2]
            dx_, dy_ = fx - d[0] * WALK_DOOR_OUT, fy - d[1] * WALK_DOOR_OUT
            got = wr.put(T['door'], (dx_, dy_, az + lz, 0.0, 0.0, arz + math.pi / 2))
            if got:
                walk_out = [dx_ - d[0] * 110, dy_ - d[1] * 110, az + lz - 88, 0.0, 0.0, _facing(-d[0], -d[1])]
                out.append((mi, dict(dd, walk_out=walk_out), got))
    return out


def _stood_on(db, M, Pz, dd, W=None):
    """Whether the game's way out of a keep's door lands on the ground or on the keep's own pieces here. A Legion keep's
    upper doors led out onto the fort's wall walk or a bridge, which the keep alone hasn't: copied, they opened 530-760
    up in the air (2 in each made Imperial fort, lab c01)."""
    import seethrough
    o = dd.get('out')
    if not o:
        return True
    x, y = _place(Pz, o[0], o[1])
    z = Pz[2] + o[2]
    g = mapdata.terrain_z(db, x, y)
    if g is not None and z - g <= AIR:
        return True
    if 'scene' not in M:
        sc = seethrough.Scene()
        memo = {}
        for pc in M['m']['pieces']:
            ri = db.resolve_id(pc[0])
            model = db.recs[ri][5] if ri is not None else None
            if not model:
                continue
            if model not in memo:
                memo[model] = seethrough.model_tris(db, model)
            px, py = _place(Pz, pc[1], pc[2])
            sc.add_model(memo[model], (px, py, Pz[2] + pc[3], pc[5], pc[6], Pz[3] + pc[4]), pc[7])
        M['scene'] = sc
    hit = M['scene'].nearest_any((x, y, z + 80), (0.0, 0.0, -1.0), 80 + AIR)
    if hit is not None:
        return True
    # (or onto the castle's own wall walk: a keep in the wall line keeps its doors out onto the walk, as the game's keeps
    # have them, the user 2026-11-03 "the wall tops have doors leading into towers and keeps")
    if W is not None:
        if 'walkscene' not in W:
            sc = seethrough.Scene()
            memo = {}
            for p in W['pieces']:
                if p.get('kind') not in ('wall', 'corner', 'tower', 'gate'):
                    continue
                ri = db.resolve_id(p['id'])
                model = db.recs[ri][5] if ri is not None else None
                if not model:
                    continue
                if model not in memo:
                    memo[model] = seethrough.model_tris(db, model)
                q = p['pose']
                sc.add_model(memo[model], (q.x, q.y, q.z, 0.0, 0.0, q.rz), 1.0)
            W['walkscene'] = sc
        h = W['walkscene'].nearest_any((x, y, z + 80), (0.0, 0.0, -1.0), 80 + WALK_DROP)
        if h is not None:
            return True
    return False


def _out_of(db, Pz, dd, got, M=None):
    """Where an inside door out of a keep sets you down: where the game's did, in front of its door, carried to ours;
    a step out of our door at the ground when that spot is off the pad with nothing of the keep's under it (the pad
    is set by the door now, _rise: Moonmoth's spot came out 169 up in the air and Buckmoth's 231 under, lab c08)."""
    o = dd.get('out')
    if o:
        x, y = _place(Pz, o[0], o[1])
        z = Pz[2] + o[2]
        g = mapdata.terrain_z(db, x, y)
        if g is not None and abs(z - g) > 48:
            sc = (M or {}).get('scene')
            under = sc.nearest_any((x, y, z + 80), (0.0, 0.0, -1.0), 80 + 48) if sc is not None else None
            if under is None:
                return lambda: _front_spot(db, got)
        if g is not None and z < g + 4:
            z = g + 8
        return [x, y, z, 0.0, 0.0, (Pz[3] + o[3]) % (2 * math.pi)]
    return lambda: _front_spot(db, got)


def _front_spot(db, got):
    import doors
    cell, rk, pos = got
    ref = next((r for r in mapdata.cellmap(db, cell).get('refs') or () if r['k'] == rk), None)
    spot = doors.outside_spot(db, ref) if ref else None
    if spot:
        return spot
    return [pos[0], pos[1], pos[2], 0.0, 0.0, pos[5]]


def _tower(db, wr, t, wz, i):
    """One round tower in the wall: the stack from the crown at the walk down into the ground, an arch and a door where
    each length runs in, a trap door to the roof. [(i, kind, (cell, rk, pos), arrive outside)]."""
    T = TOWER
    top = wz + T['over_wall']
    x, y, rz = t['x'], t['y'], t['rz']
    gz = min(_ground(db, x + 160 * math.cos(k * math.pi / 4), y + 160 * math.sin(k * math.pi / 4)) for k in range(8))
    wr.put(T['top'], (x, y, top, 0.0, 0.0, rz))
    z = top - 256
    while z - 128 - 352 > gz:                    # (lights while a med and the base would still stand clear of the ground)
        wr.put(T['light'], (x, y, z, 0.0, 0.0, rz))
        z -= 256
    wr.put(T['med'], (x, y, z, 0.0, 0.0, rz))
    zb = z - 96
    wr.put(T['base'], (x, y, zb, 0.0, 0.0, rz))
    bottom = zb - 256
    while bottom > gz - 48:
        wr.put(T['dark'], (x, y, bottom - 128, 0.0, 0.0, rz))
        bottom -= 256
    out = []
    for dx, dy in t['dirs']:
        ax, ay = x + dx * T['arch_r'], y + dy * T['arch_r']
        arz = math.atan2(dy, -dx)
        az = top + T['arch_dz']
        wr.put(T['arch'], (ax, ay, az, 0.0, 0.0, arz))
        c, s = math.cos(arz), math.sin(arz)
        lx, ly, lz = T['door_in']
        dx_, dy_ = ax + lx * c + ly * s, ay - lx * s + ly * c
        got = wr.put(T['door'], (dx_, dy_, az + lz, 0.0, 0.0, arz + math.pi / 2))
        if got:
            # (out on the walk, a step from the door, facing along the wall away from the tower)
            out.append((i, 'walk', got, [dx_ + dx * 110, dy_ + dy * 110, az + lz - 88, 0.0, 0.0, _facing(dx, dy)]))
    lx, ly, lz, tq = T['trap_at']
    c, s = math.cos(rz), math.sin(rz)
    got = wr.put(T['trap'], (x + lx * c + ly * s, y - lx * s + ly * c, top + lz, 0.0, 0.0, rz + math.radians(tq)))
    if got:
        out.append((i, 'trap', got, [x, y, top + lz + 8, 0.0, 0.0, rz]))
    t['ground'] = gz
    t['top'] = top
    return out


def _tower_rooms(db, S, P, tname, tdoors, to_towers, names, keys, rng):
    """One place holding a spiral-stair room for each tower, copied from the game's tower rooms; their doors linked to
    the tower's walk doors and trap door, the rest joining room to room and to the keep. (key, links)."""
    import editing
    import create
    from project import b64, ref_info, set_ref_pos, zs
    lib = [r for r in S['tower_rooms'] if r['style'] == 'Imperial']
    if not lib:
        return None, []
    p = db.project
    nT = len(P['towers'])
    want = {}
    for i, kind, got, arr in tdoors:
        want.setdefault(i, {'walk': [], 'trap': []})[kind].append((got, arr))
    # the place itself, lit as the game's towers are
    tm_key = lib[0]['key']
    _refs, header = db.cell_refs(tm_key)
    hdr = []
    for tg, dd in header[0]:
        if tg == 'NAME':
            dd = zs(tname)
        elif tg == 'RGNN':
            continue
        hdr.append([tg, b64(dd)])
    key = tname.lower()
    c = p.cells[key] = {'flags': 0, 'header': hdr, 'refs': {}}
    mine = p.plugin.lower()
    links, extras, made = [], [], []
    tref = {}
    # (the keep's doors to its towers go to the towers nearest it, a spare door in each of their rooms)
    kx, ky = (P['modules'][0]['x'], P['modules'][0]['y']) if P['modules'] else (P['frame']['x'], P['frame']['y'])
    order = sorted(range(nT), key=lambda i: math.hypot(P['towers'][i]['x'] - kx, P['towers'][i]['y'] - ky))
    spare = {i: 0 for i in range(nT)}
    for j in range(len(to_towers)):
        if nT:
            spare[order[j % nT]] += 1
    keep_ways = {i: [] for i in range(nT)}
    for j, here in enumerate(to_towers):
        if nT:
            keep_ways[order[j % nT]].append(here)
    nd_ = lambda r: sum(1 for d in r['doors'] if not d['trap'])
    nt_ = lambda r: sum(1 for d in r['doors'] if d['trap'])
    for i in range(nT):
        w = want.get(i, {'walk': [], 'trap': []})
        nw = len(w['walk'])
        need = nw + spare[i]
        fit = [r for r in lib if nd_(r) >= need] or [max(lib, key=nd_)]
        cost = lambda r: (nd_(r) - need) + (0 if (nt_(r) > 0) == bool(w['trap']) else 3) + max(0, nt_(r) - 1)
        lo = min(cost(r) for r in fit)
        R = rng.choice(sorted([r for r in fit if cost(r) == lo], key=lambda r: (r['key'], r['box'])))
        if R['key'] not in tref:
            tref[R['key']] = db.cell_refs(R['key'])[0]
        src = tref[R['key']]
        ox, oy = i * 2048.0, 0.0
        bx = R['box']
        copied = {}
        for rk in R['refs'] + [d['k'] for d in R['doors']]:
            ref = src.get(rk)
            if ref is None:
                continue
            rid, pos, scale, deleted = ref_info(ref['subs'])
            if deleted or not is_shell(db, rid):
                continue
            subs = [(tg, dd) for tg, dd in ref['subs'] if tg not in create.OWNER_TAGS and tg not in create.DOOR_TAGS]
            npos = (pos[0] - bx[0] + ox, pos[1] - bx[1] + oy, pos[2] - bx[2], pos[3], pos[4], pos[5])
            nk = p.new_ref_key()
            editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), set_ref_pos(subs, npos))
            copied[rk] = nk
        ds = [d for d in R['doors'] if d['k'] in copied]
        walk = sorted([d for d in ds if not d['trap']], key=lambda d: -d['dz'])
        traps = [d for d in ds if d['trap']]
        for (got, arr), d in zip(w['walk'], walk):
            links.append((got[0], got[1], tname, ('in', copied[d['k']])))
            links.append((key, copied[d['k']], '', arr))
        rest = walk[len(w['walk']):]
        if w['trap']:
            got, arr = w['trap'][0]
            if traps:
                links.append((got[0], got[1], tname, ('in', copied[traps[0]['k']])))
                links.append((key, copied[traps[0]['k']], '', arr))
                traps = traps[1:]
            elif walk:
                # (a room with no trap door of its own: the roof's leads down to its top door)
                links.append((got[0], got[1], tname, ('in', copied[walk[0]['k']])))
        # (the keep's ways in first, from the lowest spare door: the keep stands on the ground)
        rest.sort(key=lambda d: d['dz'])
        for here in keep_ways[i]:
            if rest:
                d = rest.pop(0)
                links.append((here[0], here[1], tname, ('in', copied[d['k']])))
                links.append((key, copied[d['k']], _name_of(db, here[0], names, keys, tname), ('in', here[1], here[0])))
            else:
                extras.append(None)
        for d in rest + traps:
            extras.append((i, copied[d['k']], d))
        made.append(R['key'])
    extras = [e for e in extras if e]
    # the rest: room to room, round the wall
    pairs = []
    while len(extras) >= 2:
        a_, b_ = extras.pop(0), extras.pop(0)
        pairs.append(((key, a_[1]), (key, b_[1])))
    for e in extras:
        # (one left: out by its tower's own walk door)
        w = want.get(e[0], {}).get('walk') or []
        if w:
            got, arr = w[0]
            links.append((key, e[1], '', arr))
    for a_, b_ in pairs:
        links.append((a_[0], a_[1], tname, ('in', b_[1], b_[0])))
        links.append((b_[0], b_[1], tname, ('in', a_[1], a_[0])))
    # the arrivals inside: in front of each door, worked out once the place is written
    editing.commit(db, 'Made %s: %d tower rooms' % (tname, nT))
    out = []
    for ck, rk, dest, pos in links:
        if isinstance(pos, tuple) and pos[0] == 'in':
            cell = pos[2] if len(pos) > 2 else key
            out.append((ck, rk, dest, (lambda cell=cell, k=pos[1]: _in_front(db, cell, k))))
        else:
            out.append((ck, rk, dest, pos))
    return key, out


def _name_of(db, ck, names, keys, tname):
    if ck == tname.lower():
        return tname
    for k, v in keys.items():
        if v == ck:
            return names[k]
    return mapdata.cell_info(db, ck)['name']


def _in_front(db, cell, rk):
    import doors
    m = mapdata.cellmap(db, cell)
    d = next((r for r in m['refs'] if r['k'] == rk), None)
    if d is None:
        return None
    return doors._in_front(m, d, db)


def _yard_level(db, poly):
    """The height a castle's yard is evened to: the middle of the ground inside its wall."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    zs = []
    for gx in range(int(min(xs)), int(max(xs)) + 1, 256):
        for gy in range(int(min(ys)), int(max(ys)) + 1, 256):
            if tw._inside(poly, (gx, gy)):
                z = mapdata.terrain_z(db, gx, gy)
                if z is not None:
                    zs.append(z)
    zs.sort()
    return zs[len(zs) // 2] if zs else 0.0


def _pad(db, pads):
    """The ground under each keep evened to its height: full within PAD_R of its outline, fading out over PAD_BLEND,
    cut or raised PAD_CUT at most. What stands on the ground follows it."""
    import landscape
    if not pads:
        return 0
    G = landscape.CELL
    step = G / (landscape.N - 1.0)
    reach = PAD_R + PAD_BLEND
    xs = [x for c, _z in pads for x, _y in c]
    ys = [y for c, _z in pads for _x, y in c]

    def dist(px, py, poly):
        if tw._inside(poly, (px, py)):
            return 0.0
        best = 9e9
        for i in range(len(poly)):
            (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1.0
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            best = min(best, math.hypot(px - ax - dx * t, py - ay - dy * t))
        return best
    new_h, before = {}, {}
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
                    for poly, tz in pads:
                        d = dist(x, y, poly)
                        if d >= reach:
                            continue
                        w = 1.0 if d <= PAD_R else 0.5 + 0.5 * math.cos(math.pi * (d - PAD_R) / PAD_BLEND)
                        if best is None or w > best[0]:
                            best = (w, tz)
                    if not best:
                        continue
                    n = j * landscape.N + i
                    z = h[n]
                    want = max(z - PAD_CUT, min(z + PAD_CUT, best[1]))
                    nz = z + best[0] * (want - z)
                    if abs(nz - z) >= 1:
                        h[n] = nz
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, set())
    if new_h:
        db.sync_project()
    return len(new_h)


def _people(db, keys, names, seed):
    """Each copied room's people, cast as the game's own room had them (populate.cast on the original)."""
    import zlib
    try:
        import castsurvey
        if castsurvey.ready(db) is None:
            return 0
        import populate
    except Exception:
        return 0
    said, n = [], 0
    for (mi, g), k in keys.items():
        try:
            cast_ = populate.cast(db, g, {}, seed=zlib.crc32(('%s|%s' % (seed, names[(mi, g)])).encode()))
            ppl = (cast_ or {}).get('people') or []
            if ppl:
                pl = populate.place(db, k, ppl, own=True, lines=False)
                said += pl['people']
                n += len(ppl)
        except Exception as e:
            print('castle people:', g, e)
    if said:
        import editing
        if populate.write_lines(db, said):
            editing.commit(db, 'Lines for the people of the castle')
    return n


REMOVE_PAD = 1500              # (a castle's pieces stand this far outside its outline at most)


def remove(db, outline, look=False):
    """Everything a castle's Make it built round its outline, taken away as one step: every piece outside it made as
    one castle (project.town_parts, one group for all its outside pieces) and the rooms its doors lead into, named
    "<castle>, ...". What you added later, and the ground, stay. look: only count. {'things', 'interiors', 'name'}.
    (The town's remove cuts at its first door, and a castle lays its wall long before: Redoran's lost 11 pieces.)"""
    import editing
    from collections import defaultdict
    editing._require_project(db)
    p = db.project
    poly = [(float(a), float(b)) for a, b in outline or ()]
    if len(poly) < 3:
        raise EditError("Draw the castle's outline first.")
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]

    def near(x, y):
        if tw._inside(poly, (x, y)):
            return True
        return min(math.hypot(x - min(max(x, min(xs)), max(xs)), y - min(max(y, min(ys)), max(ys))), 9e9) <= REMOVE_PAD
    groups, by = Counter(), defaultdict(list)
    for gx in range(int((min(xs) - REMOVE_PAD) // 8192), int((max(xs) + REMOVE_PAD) // 8192) + 1):
        for gy in range(int((min(ys) - REMOVE_PAD) // 8192), int((max(ys) + REMOVE_PAD) // 8192) + 1):
            ck = '#%d,%d' % (gx, gy)
            for r in mapdata.cellmap(db, ck).get('refs') or ():
                if r.get('new') and r.get('tb'):
                    by[r['tb']].append((ck, r))
                    if near(r['p'][0], r['p'][1]):
                        groups[r['tb']] += 1
    if not groups:
        raise EditError('No castle built here.')
    gid = groups.most_common(1)[0][0]
    out = by[gid]
    targets = {r['to']['key'] for _ck, r in out if r['type'] == 'DOOR' and r.get('to') and r['to'].get('cell') and r['to']['key'] in p.cells}
    pre = Counter(k.split(', ', 1)[0] for k in targets if ', ' in k).most_common(1)
    inside = [k for k in p.cells if pre and k.startswith(pre[0][0] + ', ')]
    name = ((mapdata.cell_info(db, inside[0]) or {}).get('name') or pre[0][0]).split(',')[0] if inside else 'the castle'
    if look:
        return {'things': len(out), 'interiors': len(inside), 'name': name}
    for ck, r in out:
        c = p.cells.get(ck)
        if c and r['k'] in (c.get('refs') or {}):
            c['refs'].pop(r['k'])
            p.town_parts.pop(r['k'], None)
    for k in inside:
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)
    editing.commit(db, 'Removed the castle %s: %d things and %d rooms' % (name, len(out), len(inside)))
    return {'things': len(out), 'interiors': len(inside), 'name': name}



# ------------------------------------------------------------------------------------------------ a town wall's keeps
# A walled town's keep and big guard towers (townwalls.BIG: ex_imp_keep_02 at a corner, ex_imp_guardtower_02 at the
# others and along the sides) stood doorless (the user's Griffbarrow, 2026-11-02: "entry ways at the ground and on the
# walls into this keep, with an interior and staircase to link them"). Each gets the game's ways in: a door at the
# ground on the town side, set in the Legion keep's own door frame as Moonmoth's keep has it (ex_imp_kdoorframe_01, the
# door 64 in from it), and an arched door on the wall walk where each length runs in, as the game's round towers have
# theirs (TOWER: the arch 72 under the walk's crown height, the door 13 in and 74 up); behind them one of the game's
# spiral-stair tower rooms, its lowest door to the ground and its upper doors to the walk, so the stair joins them.
WALL_KEEP = {'ex_imp_keep_02': ('Keep', 464.0), 'ex_imp_guardtower_02': ('Guard Tower', 303.0)}
# (the piece's face at the walk, where its walk doors stand: guardtower_02's shell is 223-226 from its middle there
# and the game's own door stands 231 out; set at its foot's 303 they stood out in the air, lab w02. The door is
# TOWER['door_in'] (13) in from the arch, so the arch stands at this less 3: at 233 the door came 217 from the middle,
# inside the shell — "towers still get empty doorways", the user's Nargorewatch, 2026-11-03)
WALK_FACE = {'ex_imp_keep_02': 464.0, 'ex_imp_guardtower_02': 247.0}
GROUND = {'frame': 'ex_imp_kdoorframe_01', 'door': 'ex_imp_loaddoor_03', 'in': 64.0}
WALK_OVER = 384                # (the walk's crown height over a wall length's origin: TOWER['over_wall'])
WALL_KEEPS = 8                 # a town's wall gets ways into this many of its keeps and towers at most


def _runs_at(poly, x, y):
    """The ways the wall runs out of a piece standing on it: to the neighbouring corners at a corner, both ways along
    the side on a side."""
    n = len(poly)
    k = min(range(n), key=lambda i: math.hypot(poly[i][0] - x, poly[i][1] - y))
    if math.hypot(poly[k][0] - x, poly[k][1] - y) < 400:
        a, c_ = poly[k - 1], poly[(k + 1) % n]
        return [tw._unit(a[0] - x, a[1] - y), tw._unit(c_[0] - x, c_[1] - y)]
    best = None
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
        d = math.hypot(x - a[0] - dx * t, y - a[1] - dy * t)
        if best is None or d < best[0]:
            best = (d, tw._unit(dx, dy))
    d = best[1]
    return [d, (-d[0], -d[1])]


def _copy_room(db, c, R, ox, oy, src):
    """A tower room's pieces and doors copied into place c (a project cell) with its box's low corner at (ox, oy, 0):
    {its ref key in the game place: the new ref key}."""
    import editing
    import create
    from project import ref_info, set_ref_pos
    p = db.project
    mine = p.plugin.lower()
    bx = R['box']
    copied = {}
    for rk in R['refs'] + [d['k'] for d in R['doors']]:
        ref = src.get(rk)
        if ref is None:
            continue
        rid, pos, scale, deleted = ref_info(ref['subs'])
        if deleted or not is_shell(db, rid):
            continue
        subs = [(tg, dd) for tg, dd in ref['subs'] if tg not in create.OWNER_TAGS and tg not in create.DOOR_TAGS]
        nk = p.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                       set_ref_pos(subs, (pos[0] - bx[0] + ox, pos[1] - bx[1] + oy, pos[2] - bx[2], pos[3], pos[4], pos[5])))
        copied[rk] = nk
    return copied


def _new_place(db, name, like):
    """A new interior lit as the game place `like` is: (key, cell)."""
    from project import b64, zs
    _refs, header = db.cell_refs(like)
    hdr = []
    for tg, dd in header[0]:
        if tg == 'NAME':
            dd = zs(name)
        elif tg == 'RGNN':
            continue
        hdr.append([tg, b64(dd)])
    key = name.lower()
    c = db.project.cells[key] = {'flags': 0, 'header': hdr, 'refs': {}}
    return key, c


def _seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
    return math.hypot(px - a[0] - dx * t, py - a[1] - dy * t)


def _free_name(db, nm, taken):
    base, k = nm, 2
    while nm.lower() in taken or any(v not in db.dead for v in db.by_key.get(('CELL', nm.lower()), [])) or nm.lower() in db.project.cells:
        nm = '%s %d' % (base, k)
        k += 1
    taken.add(nm.lower())
    return nm[:63]


WALL_TOWERS = 'Wall Towers'    # (the place a town wall's tower rooms share, as Anvil's "City Walls" and the forts' "Towers")
DOOR_CLEAR = 200               # (a wall door's way out this far clear at knee and head height, or it is not set there)
GROUND_CLEAR = 420             # (and a ground door's, into the town: a house 300 out stood in its way, lab w01)


def _scene_near(db, pts, R=1600):
    """What stands within R of any of pts, as a seethrough.Scene (doors, people and loose things left out)."""
    import seethrough
    sc = seethrough.Scene()
    memo = {}
    cells = {'#%d,%d' % (math.floor((x + dx) / 8192.0), math.floor((y + dy) / 8192.0)) for x, y in pts for dx in (-R, R) for dy in (-R, R)}
    for ck in cells:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r['type'] in ('NPC_', 'CREA', 'LEVC', 'DOOR') or r['type'] in mapdata.ITEM_TYPES or not r.get('b'):
                continue
            if not any(abs(r['p'][0] - x) < R and abs(r['p'][1] - y) < R for x, y in pts):
                continue
            ri = r.get('ri') if r.get('ri') is not None else db.resolve_id(r['id'])
            model = db.recs[ri][5] if ri is not None else None
            if not model or 'marker' in model.lower():
                continue
            if model not in memo:
                try:
                    memo[model] = seethrough.model_tris(db, model)
                except Exception:
                    memo[model] = []
            sc.add_model(memo[model], tuple(r['p'][:6]), r.get('s') or 1.0)
    return sc


def _way_clear(sc, x, y, z, n, dist=DOOR_CLEAR):
    """Nothing at knee or head height for dist along n from a step out of a door at (x, y), its sill at z."""
    for h in (50, 110):
        if sc.nearest_any((x + n[0] * 24, y + n[1] * 24, z + h), (n[0], n[1], 0.0), dist) is not None:
            return False
    return True


def wall_keeps(db, refs, outline, town, taken, rng, rooms='furnished'):
    """Ways into a town wall's keep and big towers, each with a stair room behind them (see WALL_KEEP): a door at the
    ground on the town side and an arched door on the walk where each length runs in, set only where the way out of
    each is clear (a ground door against a house or a walk door into the next tower opened into a wall, 3 of 18 in a
    made Imperial town against the game's 2.7%, lab b01). The keep's room is a place of its own; the towers' rooms
    share one place, "<town>, Wall Towers", joined room to room round the wall as the game's walls join theirs
    (Anvil's City Walls, Hawkmoth's and the Legion forts' Towers; Pelagiad's North Wall one passage), the keep's to
    the towers either side of it. refs: the wall's placed pieces [(cell key, ref key, id, pose)], changed: the
    pieces given rooms are taken out (so towninside.wall_rooms doesn't give them another); outline: the wall's.
    The places' names."""
    import editing
    lib = [r for r in cs.survey(db)['tower_rooms'] if r['style'] == 'Imperial']
    if not lib:
        return []
    poly = [tuple(p) for p in outline]
    cx, cy = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
    lv = [(w[3][0], w[3][1], w[3][2]) for w in refs if re.search(r'_wall_0|_wall_corner', w[2], re.I)]
    cand = [w for w in refs if w[2].lower() in WALL_KEEP]
    cand.sort(key=lambda w: (0 if 'keep' in w[2].lower() else 1, rng.random()))
    cand = cand[:WALL_KEEPS]
    if not cand:
        return []
    nd_ = lambda r: sum(1 for d in r['doors'] if not d['trap'])
    sc = _scene_near(db, [(w[3][0], w[3][1]) for w in cand], 1400)
    ri = db.resolve_id(GROUND['door'])
    gb = mapdata.object_bounds(db, ri) if ri is not None else None
    T = TOWER
    plans = []
    for ck, rk, wid, pose in cand:
        what, half = WALL_KEEP[wid.lower()]
        x, y = pose[0], pose[1]
        near = sorted(lv, key=lambda q: math.hypot(q[0] - x, q[1] - y))[:2]
        if not near or not gb:
            continue
        wz = max(q[2] for q in near)
        # the ground door: on one of the piece's four faces, in its middle or to one side of it, where the ground in
        # front of it lies furthest into the town, clear of the wall and of whatever stands there (a house, a stair)
        spots = []
        for k in range(4):
            a = pose[5] + k * math.pi / 2
            n = (math.sin(a), math.cos(a))
            t_ = (n[1], -n[0])
            for off in (0.0, half - 100, -(half - 100)):
                fx, fy = x + n[0] * (half + 300) + t_[0] * off, y + n[1] * (half + 300) + t_[1] * off
                if not tw._inside(poly, (fx, fy)):
                    continue
                clear = min(_seg_dist(fx, fy, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))
                if clear < 300:              # (the wall's own depth inside its line is ~170, a step more)
                    continue
                gx, gy = x + n[0] * (half + 120) + t_[0] * off, y + n[1] * (half + 120) + t_[1] * off
                gz = _ground(db, gx, gy)
                if gz > wz + WALK_OVER:
                    continue                 # (the ground there stands over the wall walk itself)
                dx, dy = x + n[0] * (half - 12) + t_[0] * off, y + n[1] * (half - 12) + t_[1] * off
                if not _way_clear(sc, dx, dy, gz, n, GROUND_CLEAR):
                    continue
                spots.append((clear - abs(off) * 0.1, n, off, gx, gy, gz, dx, dy))
        ground = max(spots) if spots else None
        # the walk doors: an arch on the face where each length runs in, its way along the walk clear and on it
        walks = []
        wf = WALK_FACE.get(wid.lower(), half)
        for d in _runs_at(poly, x, y):
            ax, ay = x + d[0] * (wf - 3), y + d[1] * (wf - 3)
            arz = math.atan2(d[1], -d[0])
            az = wz + WALK_OVER + T['arch_dz']
            c, s = math.cos(arz), math.sin(arz)
            lx, ly, lz = T['door_in']
            px, py = ax + lx * c + ly * s, ay - lx * s + ly * c
            arr = [px + d[0] * 110, py + d[1] * 110, az + lz - 88]
            if not _way_clear(sc, px, py, arr[2], d, 240):
                continue
            under = sc.nearest_any((arr[0], arr[1], arr[2] + 80), (0.0, 0.0, -1.0), 260)
            if under is None:
                continue                     # (no walk there: the length runs on past a gap)
            walks.append((d, ax, ay, arz, az, px, py, lz, arr))
        if ground is None and not walks:
            continue
        plans.append({'w': (ck, rk, wid, pose), 'what': what, 'ground': ground, 'walks': walks, 'wz': wz})
    if not plans:
        return []
    wr = _Writer(db)
    for P_ in plans:
        outs = []
        g = P_['ground']
        if g is not None:
            _c, n, off, gx, gy, gz, dx, dy = g
            drz = math.atan2(-n[0], -n[1]) % (2 * math.pi)          # (its face, local +y, into the piece)
            dzz = gz + 6 - gb[2]
            wr.put(GROUND['frame'], (dx + n[0] * GROUND['in'], dy + n[1] * GROUND['in'], dzz, 0.0, 0.0, drz))
            got = wr.put(GROUND['door'], (dx, dy, dzz, 0.0, 0.0, drz))
            if got:
                outs.append((got, [gx + n[0] * 60, gy + n[1] * 60, gz + 8, 0.0, 0.0, _facing(*n)]))
        for d, ax, ay, arz, az, px, py, lz, arr in P_['walks']:
            wr.put(T['arch'], (ax, ay, az, 0.0, 0.0, arz))
            got = wr.put(T['door'], (px, py, az + lz, 0.0, 0.0, arz + math.pi / 2))
            if got:
                outs.append((got, arr + [0.0, 0.0, _facing(*d)]))
        P_['outs'] = outs
        P_['ang'] = math.atan2(P_['w'][3][1] - cy, P_['w'][3][0] - cx)
    plans = [P_ for P_ in plans if P_['outs']]
    # the rooms: one with a door for each way in and, in the towers' place, a spare or two to join the next rooms
    joined = sorted([P_ for P_ in plans if P_['what'] != 'Keep'], key=lambda P_: P_['ang'])
    for P_ in plans:
        need = len(P_['outs'])
        want = need + (2 if P_['what'] != 'Keep' and len(joined) > 1 else 1)
        fit = [r for r in lib if nd_(r) >= need]
        if not fit:
            P_['R'] = None
            continue
        cost = lambda r: abs(nd_(r) - want) + (1 if any(d['trap'] for d in r['doors']) else 0)
        lo = min(cost(r) for r in fit)
        P_['R'] = rng.choice(sorted([r for r in fit if cost(r) == lo], key=lambda r: (r['key'], r['box'])))
    plans = [P_ for P_ in plans if P_['R']]
    joined = [P_ for P_ in joined if P_ in plans]
    names, links, done, src = [], [], set(), {}
    shared = None
    for j, P_ in enumerate(sorted(plans, key=lambda P_: (P_['what'] != 'Keep', P_['ang']))):
        R = P_['R']
        if P_['what'] == 'Keep' or len(joined) < 2:
            name = _free_name(db, '%s, %s' % (town, P_['what']), taken)
            key, cell = _new_place(db, name, R['key'])
            names.append(name)
            ox = 0.0
        else:
            if shared is None:
                name = _free_name(db, '%s, %s' % (town, WALL_TOWERS), taken)
                shared = (name,) + _new_place(db, name, R['key'])
                names.append(name)
                shared += ([0],)
            name, key, cell, nxt = shared
            ox = nxt[0] * 2048.0
            nxt[0] += 1
        if R['key'] not in src:
            src[R['key']] = db.cell_refs(R['key'])[0]
        copied = _copy_room(db, cell, R, ox, 0.0, src[R['key']])
        inner = sorted([d for d in R['doors'] if not d['trap'] and d['k'] in copied], key=lambda d: d['dz'])
        outs = P_['outs']
        # (the ground door to the lowest door inside, the walk doors to the highest: the stair between them)
        has_ground = P_['ground'] is not None and outs and outs[0][1][2] < P_['wz']
        if has_ground:
            pairs = [(outs[0], inner[0])] + list(zip(outs[1:], inner[::-1][:len(outs) - 1]))
        else:
            pairs = list(zip(outs, inner[::-1][:len(outs)]))
        used = {d['k'] for _o, d in pairs}
        for (got, arr), dd in pairs:
            links.append((got[0], got[1], name, ('in', key, copied[dd['k']])))
            links.append((key, copied[dd['k']], '', arr))
        P_['place'] = (name, key)
        P_['spare'] = [copied[d['k']] for d in R['doors'] if d['k'] not in used and d['k'] in copied]
        done.add(P_['w'][1])
    # joined round the wall: each tower's room to the next one's, the last back to the first; the keep's room to the
    # tower rooms nearest it either side
    ring = [P_ for P_ in joined if P_.get('place')]

    def join(A, B):
        if not A['spare'] or not B['spare']:
            return False
        a, b = A['spare'].pop(0), B['spare'].pop(0)
        links.append((A['place'][1], a, B['place'][0], ('in', B['place'][1], b)))
        links.append((B['place'][1], b, A['place'][0], ('in', A['place'][1], a)))
        return True
    if len(ring) >= 2:
        for i in range(len(ring) if len(ring) >= 3 else 1):
            join(ring[i], ring[(i + 1) % len(ring)])
    for K_ in [P_ for P_ in plans if P_['what'] == 'Keep' and P_.get('place')]:
        for T_ in sorted(ring, key=lambda P_: abs(((P_['ang'] - K_['ang'] + math.pi) % (2 * math.pi)) - math.pi))[:2]:
            join(K_, T_)
    # (a door more, or a trap door: out by its own first way in, never leading nowhere)
    for P_ in plans:
        if not P_.get('place'):
            continue
        for k_ in P_['spare']:
            links.append((P_['place'][1], k_, '', P_['outs'][0][1]))
    if not names:
        return []
    editing.commit(db, 'Ways into the wall of %s: %s' % (town, ', '.join(names)))
    for ck, rk, dest, pos in links:
        if isinstance(pos, tuple):
            pos = _in_front(db, pos[1], pos[2])
        if pos:
            _link(db, ck, rk, dest, pos)
    editing.commit(db, 'Linked the doors into the wall of %s' % town)
    if rooms == 'furnished':
        for nm in names:
            furnish_shell(db, nm.lower(), None, seed=zlib.crc32(nm.encode()))
        editing.commit(db, 'Furnished the rooms in the wall of %s' % town)
    refs[:] = [w for w in refs if w[1] not in done]
    return names


# ------------------------------------------------------------------------------------------------ shells, not copies
# The rooms behind a castle's doors keep the game room's architecture and its door links, never its furnishing or decor
# (the user, 2026-11-02: "We can learn as much as we want from other interiors about design and architecture, but we
# can't just copy them wholesale ... the interior decor and furnishing at least has to be unique"). ROOMS: None (no
# rooms), shells (the architecture and doors only, for furnishing by hand) or furnished (the same shells, furnished by
# the Workshop's own furnisher by each room's kind; the source's choices steer only the kind, never where things go).
ROOMS = ('none', 'shells', 'furnished')
# (a building piece that is furnishing all the same: kit tables and beds, rugs, banners, altars, racks)
NOT_SHELL = re.compile(r'rug|carpet|banner|tapestry|table|chair|bench|stool|_bed|bed_|bunk|hammock|shelf|bookcase|crate|barrel|'
                       r'sack|basket|rack|mannequin|statue|altar|shrine|planter|flora|tree|cushion|pillow|painting|candle|lantern|'
                       r'sconce|torch|chandelier|cauldron|anvil|forge|bottle|book|scroll|skull|bones|corpse|drape|curtain|screen', re.I)
_SHELL = {}


def is_shell(db, rid):
    """Whether a placed thing is a room's architecture (kept in a shell): a door, or a building piece that isn't
    furniture or decor. Lights, containers, things and people are never."""
    low = rid.lower()
    if low in _SHELL and _SHELL[low][0] is db.recs:
        return _SHELL[low][1]
    ri = db.resolve_id(rid)
    tag = db.recs[ri][0] if ri is not None else ''
    if tag == 'DOOR':
        ok = True
    elif tag not in ('STAT', 'ACTI'):
        ok = False
    else:
        b = mapdata.object_bounds(db, ri)
        ok = bool(mapdata.is_architecture(tag, rid, b)) and not NOT_SHELL.search(low) and not low.startswith(('furn_', 'light_', 'misc_'))
    _SHELL[low] = (db.recs, ok)
    return ok


def _strip(db, key):
    """A copied place's furnishing and decor taken out: its architecture and doors stay. The count taken."""
    c = db.project.cells.get(key)
    if not c:
        return 0
    from project import ref_info
    gone = []
    for rk, ref in list(c['refs'].items()):
        rid = ref_info(_subs(ref))[0]
        if not is_shell(db, rid):
            gone.append(rk)
    for rk in gone:
        c['refs'].pop(rk, None)
    return len(gone)


def _subs(ref):
    import base64
    return [(t, base64.b64decode(d) if isinstance(d, str) else d) for t, d in ref['subs']]


def _kind_of(counts, n_tiles):
    """A room's kind for the furnisher, from what its source room held (cs.KINDS counts), or None for its own guess."""
    g = counts.get
    if g('bed', 0) >= 3:
        return 'barracks'
    if g('weapons', 0) + g('armour', 0) >= 2:
        return 'armoury'
    if g('shrine', 0):
        return 'shrine'
    if g('prison', 0):
        return 'guardroom'
    if g('bed', 0):
        return 'bedroom'
    if g('books', 0) >= 3:
        return 'study'
    if g('cook', 0) and g('table', 0):
        return 'kitchen'
    if g('table', 0) >= 2:
        return 'mess'
    if g('store', 0) >= 3:
        return 'storage'
    return 'hall' if n_tiles >= 4 else None


def furnish_shell(db, key, src_key, shift=(0.0, 0.0, 0.0), seed=1, kinds=None, level=None):
    """A shell furnished by the Workshop's own furnisher, each room as the kind its source room was (counted from the
    source's things within the room's floor, shift carrying the source's spots to ours), never their spots. The
    number of things placed (0 when the place has no rooms the furnisher can read)."""
    import furnish
    try:
        info = furnish.rooms(db, key)
    except Exception as e:
        print('castle rooms of', key, e)
        return 0
    T = info.get('tile') or 256
    src = [r for r in mapdata.cellmap(db, src_key).get('refs') or () if not r.get('arch') and r['type'] != 'DOOR'] if src_key else []
    plan = []
    for rm in info.get('rooms') or ():
        tl = rm.get('_tiles') or []
        cnt = Counter()
        for r in src:
            x, y, z = r['p'][0] + shift[0], r['p'][1] + shift[1], r['p'][2] + shift[2]
            if not any(abs(x - t['x']) <= T / 2 and abs(y - t['y']) <= T / 2 for t in tl):
                continue
            if rm.get('floor') is not None and not (-80 <= z - rm['floor'] <= 400):
                continue
            for k, rx in cs.KR:
                if rx.search(r['id']):
                    cnt[k] += 1
                    break
        kind = _kind_of(cnt, len(tl))
        if kinds:
            kind = kinds(rm, kind, cnt) or kind
        plan.append({'id': rm['id'], 'purpose': kind or rm.get('purpose')})
    if not plan:
        return 0
    try:
        out = furnish.furnish(db, key, plan, seed=seed, commit=False, level=level)
    except Exception as e:
        print('castle furnish', key, e)
        return 0
    n = (out or {}).get('placed') if isinstance(out, dict) else 0
    return n if isinstance(n, int) else len(n or ())


def source_share(db, key, src_key, shift=(0.0, 0.0, 0.0)):
    """The share of a made place's things (not architecture) standing where the source place had the same model (within
    30 units): near 0 when its furnishing is its own."""
    src = {}
    for r in mapdata.cellmap(db, src_key).get('refs') or ():
        if not r.get('arch') and r['type'] != 'DOOR':
            src.setdefault(r['id'].lower(), []).append(r['p'][:3])
    mine = [r for r in mapdata.cellmap(db, key).get('refs') or () if not r.get('arch') and r['type'] not in ('DOOR', 'NPC_', 'CREA')]
    if not mine:
        return 0.0, 0
    same = 0
    for r in mine:
        x, y, z = r['p'][0] - shift[0], r['p'][1] - shift[1], r['p'][2] - shift[2]
        if any(math.dist((x, y, z), q) <= 30 for q in src.get(r['id'].lower(), ())):
            same += 1
    return same / float(len(mine)), len(mine)
