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
from collections import Counter, defaultdict

import castlesurvey as cs
import mapdata
import townwalls as tw
from editing import EditError

STYLES = {
    'Imperial': {'label': 'Imperial fort', 'wall': 'ex_imp', 'keep': r'^ex_imp_keep_01$', 'halls': r'^ex_imp_keep_0[12]$', 'towers': True,
                 'name': 'Fort %s', 'gaps': (500, 700, 1200)},
    'Stronghold': {'label': 'Dunmer stronghold', 'wall': None, 'keep': r'^ex_stronghold_fort00$', 'name': '%s'},
    # (Indarys's wall hugs its buildings: 4,018 by 2,994 round a group 3,300 across)
    'Redoran': {'label': 'Redoran stronghold', 'wall': 'ex_r_pcfort', 'keep': r'^ex_r_pcfort_01$', 'gaps': (200, 250, 400),
                'name': '%s Manor'},
}
NAME_CULTURE = {'Imperial': 'Imperial', 'Stronghold': 'Dunmer', 'Redoran': 'Redoran'}
SIZES = {'small': 0.8, 'medium': 1.0, 'large': 1.3}
KEEP_STOREY = 1037             # (a keep piece on a keep piece: the Ebon Tower's keep_01 over keep_01, lab w10 2026-11-05)
TOWER_UP = {'court': 3, 'junction': 2, 'corner': 2, 'gate': 1}   # (light storeys over the walk in a tall castle: the Ebon Tower's crowns stand 512-1920 over the wall, 2-7 storeys)
GREAT = 7168                   # (a great castle: a cell across, as the Ebon Tower's and Firewatch's walls, in wards with the keep's court)
MARGIN = 700                   # a keep stands this far in from the wall behind it (the wall's own depth and a lane)
TOWN_NEAR = 6000               # (a town's wall this near turns the castle's gate towards the town)
SIDE_GAP = 500                 # (and from the walls at its sides)
# the Legion's square tower in a wall, as the game stands its own (lab c8, 46 towers_top in game walls): the crown at the
# walk (wall origin + 384), lights below it every 256 to the ground (the game's med section and base show as a darker
# foot; ours are under the ground, _tower);
# an entrance arch (ex_imp_wallent_02) at 176 out on each side a length runs in, 72 under the crown, its door 13 in
# and 74 up, turned a quarter; a trap door in the crown to the roof
TOWER = {'top': 'ex_imp_towers_top_01', 'light': 'ex_imp_towers_light_01', 'med': 'ex_imp_towers_med_01',
         'base': 'ex_imp_towers_base_01', 'dark': 'ex_imp_towers_dark_01', 'arch': 'ex_imp_wallent_02',
         'door': 'Ex_imp_loaddoor_02', 'trap': 'in_com_traptop_01', 'over_wall': 384, 'arch_r': 176, 'arch_dz': -72,
         'door_in': (13.0, 0.0, 74.0), 'trap_at': (-59.0, 6.0, 154.0, 90.0)}
TOWER_EVERY = 6                # a tower along a side every so many lengths besides those at the corners and the gate
TOWER_CLEAR = 300              # (a wall_tower_01 this near a round tower goes: two towers in one spot)
TOWER_OUT = 16                 # (a wall tower stands this far out of the wall line: its faces clear of the lengths' (168 against 162))
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
_DEBUG = [False]                # (the hall fill's decisions printed, for the lab)


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
    """The game's keeps of a style ('keep'), or its halls ('hall': the buildings its forts stand in their walls besides
    the keep, a barracks, an armoury, a chapel, a prison: Frostmoth's three, Hawkmoth's barracks, Buckmoth's prison)."""
    d = STYLES[style]
    rx = re.compile(d['keep'] if which == 'keep' else d.get('halls') or '$^', re.I)
    out = [m for m in S['modules'] if m['style'] == style and rx.search(m['main']) and m['doors']]
    if which == 'keep':
        # (the keep holds the halls: a module whose rooms are only a prison or a chapel stands beside it, not for it)
        out = [m for m in out if 'keep' in m['roles'] or which != 'keep']
    else:
        kx = re.compile(d['keep'], re.I)
        out = [m for m in out if not (kx.search(m['main']) and 'keep' in m['roles'])]
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
    great = size == 'great'
    if size == 'great':
        # (a great castle: a square a cell across round the outline's middle, built as a drawn one is, in wards)
        pts = [_to_world(F, u, v) for u, v in ((-GREAT / 2, -GREAT / 2), (GREAT / 2, -GREAT / 2), (GREAT / 2, GREAT / 2), (-GREAT / 2, GREAT / 2))]
        size = 'drawn'
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
        g_side, g_back, g_front = d.get('gaps') or (SIDE_GAP, MARGIN, 1200)
        # (as drawn: the outline itself, any shape with square corners, squared to the wall's pieces; the game's own
        # sizes are a box. A drawn outline that comes to nothing, or whose front or back can't take a gate or the
        # keep, is a box of its size)
        polyf = _drawn_poly(pts, F, L) if size == 'drawn' and d.get('towers') else None
        front_f = back_f = None
        if polyf is not None:
            front_f, back_f = _side_facing(polyf, -1), _side_facing(polyf, 1)
            if front_f is None or back_f is None or abs(front_f[2][0] - front_f[1][0]) < 5 * L:
                polyf = None
        if polyf is not None:
            Wd, Dp = _extent_f(polyf)
            room_w = abs(back_f[2][0] - back_f[1][0])
        elif size == 'drawn':
            Wd, Dp = _extent(pts, F)
            room_w = Wd
        else:
            Wd, Dp = a0 * f, b0 * f
            room_w = Wd
        # (room for the keep and what stands with it, turned with its door to the gate, and a yard before it)
        # (a keep that fits the size asked for, else the smallest)
        fits = []
        for m in sorted(keeps, key=lambda m: (m['fort'], m['main'])):
            eu, ev = _turned_extent(m, F)
            fits.append((eu + 2 * g_side <= room_w * 1.1 and ev + g_back + g_front <= Dp * 1.1, -(eu * ev), m))
        ok = [t[2] for t in fits if t[0]]
        # (a keep in the wall line stands as high as the wall: Umbermoth's keep is 450 high, the wall 900, and in the
        # wall line it left a low gap the wall could not fill, the user 2026-11-03)
        if not d.get('keep_apart'):
            ok = [m for m in ok if _mesh_tall(db, m)] or ok
        km0 = rng.choice(ok) if ok else max(fits, key=lambda t: t[1])[2]
        # (the keep as one tiered mass of blocks in a drawn, great or large castle, as wide and as tall as the
        # outline's back and its court take; the plain keep when no mass fits. The user, 2026-11-05: a tiered
        # fortress rather than sprawling small keeps)
        tries = [None]
        if d.get('towers') and not d.get('keep_apart') and (polyf is not None or size == 'large'):
            # (the widest mass the outline's back takes: it stands for the halls too, no lone hall in the ward's walls)
            if size == 'large':
                tries = [(3, 2)] + tries
            else:
                # (the widest mass first, or the next by the seed: every great castle stood the same mass, the user
                # 2026-11-06, "just because I approved of one outcome doesn't mean they should all look the same")
                first = rng.choice([(7, 3), (7, 3), (5, 3)] if great else [(7, 3), (5, 3), (5, 3), (3, 3)])
                tries = [first] + [t for t in [(7, 3), (5, 3), (3, 3), (3, 2)] if t != first] + tries
        # (the keep off the back's middle by the seed, as far as the back takes it: a length or two either way)
        du_keep = rng.choice((-2, -1, 0, 0, 1, 2))
        polyf0, Wd0, Dp0 = polyf, Wd, Dp
        pool = _slit_pool(keeps)
        # (the widest mass that leaves the castle its court or its wards; failing that, the widest that fits at all)
        i_try, fallback = 0, None
        while i_try < len(tries):
            cand = tries[i_try]
            i_try += 1
            km = _tiered(db, km0, rng, *cand, pool=pool) if cand else km0
            if km is None:
                continue
            polyf, Wd, Dp = polyf0, Wd0, Dp0
            eu, ev = _turned_extent(km, F)
            if polyf is not None and room_w < eu + 2 * g_side + 2 * L:
                if cand:
                    continue                 # (a smaller mass, or the plain keep)
                polyf = None                 # (its back too short for a keep: a box of the outline's size)
                Wd, Dp = _extent(pts, F)
            cuts = []
            court = None                     # (the keep's court: (u middle, v back, n wide, n deep) in lengths)
            if polyf is None:
                Wd = max(Wd, eu + 2 * g_side)
                Dp = max(Dp, ev + g_back + g_front)
                # (whole lengths round it, never fewer than its keep needs: rounded down, a compound stood into the wall)
                n_w, n_d = max(4, int(math.ceil(Wd / L - 0.1))), max(4, int(math.ceil(Dp / L - 0.1)))
                if n_w % 2:
                    n_w += 1                 # (an even count: the gate stands in the middle of its side)
                if size == 'large' and bool(d.get('towers')) and not d.get('keep_apart'):
                    # (the inner ward round the keep: whole lengths, a lane of INNER_LANE lengths between the two walls)
                    n_w2 = max(4, int(math.ceil((eu + 2 * g_side) / L - 0.1)))
                    if n_w2 % 2:
                        n_w2 += 1
                    n_d2 = max(3, int(math.ceil((ev + INNER_FRONT) / L - 0.1)))
                    n_w = max(n_w, n_w2 + 2 * INNER_LANE)
                    n_d = max(n_d, n_d2 + 2 * INNER_LANE + 2)
                    court = (0.0, n_d * L / 2 - INNER_LANE * L, n_w2, n_d2)
                Wd, Dp = n_w * L, n_d * L
                polyf = [(-Wd / 2, -Dp / 2), (Wd / 2, -Dp / 2), (Wd / 2, Dp / 2), (-Wd / 2, Dp / 2)]
                u_gate = u_keep = 0.0
            else:
                u_gate = (front_f[1][0] + front_f[2][0]) / 2.0
                u_keep = (back_f[1][0] + back_f[2][0]) / 2.0
                # (and the corner towers stay: the keep's box clear of them, else the rule below drops the tower)
                lim = int(max(0.0, (room_w - eu) / 2.0 - max(g_side, TOWER_KEEP_CLEAR + 120)) // L)
                u_keep += max(-lim, min(lim, du_keep)) * L
                # (a big one in wards: cross walls with their gates, the keep's ward at the back; and in the keep's ward
                # its court, the keep's own walls round a yard with its wings and halls in them and towers at its corners,
                # as the game's big keeps stand (Ember Keep, the Ebon Tower). The user, 2026-11-05: larger and more
                # complicated keep sections, not a bubble with a keep at the back)
                cuts = _ward_cuts(polyf, L, ev, u_keep, u_gate, rng)
                court = _court(polyf, cuts, L, eu, ev, u_keep, g_side, rng)
            if cuts or court is not None:
                break
            if cand is not None:
                if fallback is None:
                    fallback = cand
                continue
            if fallback is not None:
                tries, i_try, fallback = [fallback], 0, None   # (no court for the plain keep either: the widest mass)
        v_min = min(p[1] for p in polyf)
        poly = [_to_world(F, u, v) for u, v in polyf]
        # (the way in: out, through the front, out again, so the gate is asked for there alone)
        way = [list(_to_world(F, u_gate - 16, v_min - 1500)), list(_to_world(F, u_gate, v_min + 200)), list(_to_world(F, u_gate + 16, v_min - 1500))]
        W = _lay(db, d['wall'], kit, {'plots': [], 'streets': [{'pts': way}], 'wall_outline': poly})
        faults += W.get('faults') or []
        W['pieces'] = [p for p in W['pieces'] if p.get('kind') not in ('bigtower', 'keep')]
        _outlines(db, W)
        if style == 'Imperial':
            _gatehouse_plan(db, W, F, L)
        for j, (vc, u0, u1, ug) in enumerate(cuts):
            W['pieces'] += _cross_wall(db, kit, F, L, u0, u1, vc, ug, INNER_RUN + j, faults)
        _outlines(db, W)
        out['W'] = W
        out['size_wd'] = [Wd, Dp]
        out['wards'] = _wards(polyf, cuts, F)
        out['cuts'] = cuts
        out['gate_at'] = _to_world(F, u_gate, v_min + 200)
        W2 = None
        poly2 = poly2f = None
        if court is not None:
            uc, vb, n_w2, n_d2 = court
            vf = vb - n_d2 * L
            poly2f = [(uc - n_w2 * L / 2, vf), (uc + n_w2 * L / 2, vf), (uc + n_w2 * L / 2, vb), (uc - n_w2 * L / 2, vb)]
            poly2 = [_to_world(F, u, v) for u, v in poly2f]
            way2 = [list(_to_world(F, uc - 16, vf - 1500)), list(_to_world(F, uc, vf + 200)), list(_to_world(F, uc + 16, vf - 1500))]
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
            if W2 is not None:
                Wk, ka, kb_ = W2, poly2[2], poly2[3]
                t_keep = math.hypot(kb_[0] - ka[0], kb_[1] - ka[1]) / 2.0
            else:
                Wk = W
                bk = back_f if back_f is not None else (2, polyf[2], polyf[3])
                ka, kb_ = _to_world(F, *bk[1]), _to_world(F, *bk[2])
                t_keep = abs(u_keep - bk[1][0])   # (where the seed set it along the back)
            M = _in_wall(db, km, F, Wk, ka, kb_, t_keep, L, tall=True)
            out['modules'].append(M)
        # (the halls the game's forts stand in their walls, at their rate: a second hall, a chapel or an armoury, as
        # Frostmoth's and Umbermoth's; the court's walls first, the keep's wings beside it, then the wards' walls)
        # (a tiered keep stands for the halls: a hall module in the wall near it looked thrown together, two Gold Coast
        # buildings in the yard didn't fit, a lone section of keep made no sense, the user 2026-11-05)
        if d.get('towers') and not d.get('keep_apart') and not km.get('tiered'):
            try:
                import townplan
                budget = int(round(abs(_area_f(polyf)) * _module_rate(S, style))) - 1
                if W2 is not None and size != 'large':
                    # (the court's walls take the castle's halls first: they cluster at the keep, as the game's)
                    got = _fill_walls(db, S, style, out, W2, F, L, poly2f, [], km, rng, HALL_GAP, keeps, want=budget)
                    out['modules'] += got
                    budget -= len(got)
                # (clear of the court's wall by half a length at least: a hall in the lane between the walls, jammed
                # against both, 2026-11-05)
                # (a large fort's inner ward is keep-sized, its second hall stands close before it)
                out['modules'] += _fill_walls(db, S, style, out, W, F, L, polyf, cuts, km, rng, HALL_GAP, keeps,
                                              avoid=townplan.inset(poly2, -(L / 4 if size == 'large' else L)) if poly2 is not None else None, most=budget,
                                              front_ok=bool(cuts) or (court is not None and size != 'large'))
            except Exception as e:
                print('castle halls:', e)
        if d.get('towers'):
            out['towers'] = _towers(W, kit, F, corners='all' if cuts or km.get('tiered') else size == 'large')
            if W2 is not None:
                for t in _towers(W2, kit, F, corners='all' if size != 'large' else True):
                    t['court'] = True
                    out['towers'].append(t)
            cross = _cross_towers(W, kit, F, L, cuts)
            # (no side tower beside a junction tower: two columns 256 or 512 apart stood at a cross wall's end)
            out['towers'] = [t for t in out['towers'] if t.get('kind') == 'corner' or not any(math.hypot(t['x'] - c['x'], t['y'] - c['y']) < 900 for c in cross)]
            out['towers'] += cross
            # (a tall castle, as the user sees the Ebon Tower: its towers rise storeys over the walk, the court's
            # highest, and its keep is two keep pieces high. The Legion's small forts stay as the game's own)
            out['tall'] = bool(cuts) or court is not None or bool(km.get('tiered'))
            if out['tall']:
                for t in out['towers']:
                    t['up'] = TOWER_UP.get('court' if t.get('court') else t.get('kind'), 0)
                    if t.get('kind') == 'side':
                        t['up'] = rng.choice((0, 1, 1, 2))
                    if size == 'large':
                        t['up'] = min(t['up'], 1)
            # (no round tower against a keep or hall: one stood on the length by a keep's side, half in the keep and
            # hanging off it, the user 2026-11-03 "a floating tower dangling on the side"; a junction tower stays, it
            # closes the cross wall)
            out['towers'] = [t for t in out['towers'] if t.get('kind') == 'junction' or not any(_near_module(M, t['x'], t['y'], TOWER_KEEP_CLEAR) for M in out['modules'])]
            _tower_pieces(W, kit, out['towers'])
            if W2 is not None:
                _tower_pieces(W2, kit, out['towers'])
        if W2 is not None:
            # (one wall for the rest of the making: the inner runs numbered on from the outer's)
            for p in W2['pieces']:
                for k_ in ('run', 'corner'):
                    if p.get(k_) is not None:
                        p[k_] += INNER_RUN + len(cuts)
            W['pieces'] += W2['pieces']
            W['extra_preview'] = (W.get('extra_preview') or []) + (W2.get('extra_preview') or [])
            faults += W2.get('faults') or []
        # (stairs up to the walk from the bailey, as the game's forts have theirs; clear of the towers and the keep)
        away = [(t['x'], t['y']) for t in out['towers']]
        for M in out['modules']:
            kb = M['m']['box']
            away += [_place((M['x'], M['y'], 0.0, M['rz']), lx, ly) for lx in (kb[0], kb[2]) for ly in (kb[1], kb[3])]
        W['pieces'] += tw.wall_stairs(W, avoid=away, most=(3 if W2 is not None else 2) + len(cuts), db=db)
        # (the lower wards are built as quarters of the castle's town, streets and houses, once the walls stand:
        # Firewatch and Old Ebonheart are towns inside their walls. The keep's ward keeps its yard)
        out['quarters'] = [w for w in out['wards'][:-1]] if cuts else []
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
        # (out of its own ring: by the castle's middle, a court's gate behind the middle stood its passage inside the
        # court and its towers' doorways across the wall, lab w5 2026-11-05)
        ring = W.get('outline') or []
        ox_, oy_ = (sum(q[0] for q in ring) / len(ring), sum(q[1] for q in ring) / len(ring)) if ring else (F['x'], F['y'])
        if nx * (gx - ox_) + ny * (gy - oy_) < 0:
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
        # (a buttressed length too: left inside a tiered keep, its buttress stood out of the keep's back, lab 2026-11-05)
        if p.get('kind') not in ('wall', 'tower') or not p.get('corners') or _sat_depth(kpts, p['corners']) <= KEEP_CUT:
            keep.append(p)
            continue
        q = p['pose']
        ax, ay = q.dir((1.0, 0.0))
        nx, ny = -ay, ax
        cx, cy = sum(c[0] for c in p['corners']) / 4.0, sum(c[1] for c in p['corners']) / 4.0
        covered = True
        # (at the ends themselves: at 0.45 a length whose end stood 26 out of the keep was cut, a 32 seam, lab 2026-11-05)
        for t in (-0.495 * 512, 0.0, 0.495 * 512):
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


# ------------------------------------------------------------------------------------------------ the tiered keep
# A castle's keep as one tiered mass of the kit's keep blocks rather than a keep with halls round it (the user,
# 2026-11-05: the keep pieces fit together too symmetrically, cookie-cutter; a tiered fortress is a better Great
# stronghold than sprawling small keeps). As the Ebon Tower stands (lab w11, w14): keep_01 blocks, a 768 body under a
# deck at 530 with a parapet to 664, side by side body to body and stacked at KEEP_STOREY; big round towers (towerb)
# rising out of their decks under pitched roofs or battlements; keep_02 (the same body under a pyramid roof) and the
# slender guard tower as crowns. The keep's own block, with its door, stands in front; the back row stands in the wall.
BLOCK = 768                    # keep_01's body across (its 848 box is the corner buttresses)
DECK = 530                     # its roof deck over its origin
TIER_ID = 'ex_imp_keep_01'
CROWN_ROOF = 'ex_imp_keep_02'  # (keep_01's body under a pyramid roof: the top of a column)
CROWN_SPIRE = 'ex_imp_guardtower_02'   # (the slender square tower with the pointed roof, 1,863 tall, its foot 389 under its origin)
TOWERB = {'base': 'ex_imp_towerb_base_01', 'med': 'ex_imp_towerb_med_01', 'light': 'ex_imp_towerb_light_01',
          'dark': 'ex_imp_towerb_dark_01', 'top': 'ex_imp_towerb_top_01', 'roof': 'ex_imp_towerb_roof_pitch'}
TOWERB_IN = 150                # (a corner tower's middle this far in from the block's corner along both faces: half in it)
TIER_FLANK = 0.6               # (a wing block before the back row's neighbour, each side, this often)
SLIT_ID = 'ex_imp_arrowslit_01'
SLIT_OUT = 400                 # (an arrow slit stands this far out from a block's middle: on its face)
TIER_DROPS = (0, 0, 128, 256)  # (a column sunk this much beside its neighbours: equal tops met in a clash of parapets)
TIER_ROOFED = 0.25             # (a column topped by the pyramid-roofed block this often)
PITCH_VARY = (-64, -32, 0, 32, 64)   # (a column's storeys this much over or under KEEP_STOREY: the bands between storeys no longer line up across the row)
TALL = 3                       # (a column this many storeys is tall: windows on every storey, no spire on it)
KEEP_SINK = 512                # (a keep piece on another sinks this far: its arcaded ground base (the model's lower 512, dark
                               # columns and wall) inside the piece under it, its pale wall rising out of that piece's parapet;
                               # stacked at the game's 1037 the base stood in the air as a dark band, the user 2026-11-06)
KEEP_INSET = 0.95              # (and a shade smaller, so its faces stand 19 inside the lower's, never in one plane with them)
GROUND_BURY = 64               # (a tower's dark section at the dirt goes this far into it: the darkening at a foot wants the
                               # ground it stands in, 'buried a bit', the user 2026-11-06)
DECK_TOWER = 0.5               # (a back column's top carries a round tower rising out of its deck near a corner this often)
DECK_TOWER_IN = 102            # (its middle this far from the block's middle each way: the column wholly within the block's body, no foot showing)
# (small round turrets hung on a tall column's top corners, as Pelagiad's keep carries two, were tried and taken out:
# Pelagiad's run to the ground, and hung off the column theirs ended in flat bottoms in the air, the user 2026-11-05)
SLIT_FACE = 0.65               # (a block's face takes a window pattern this often, else it stands bare)
SLIT_DOOR_CLEAR = 340          # (no window this near a door or a walk arch on the block's face: windows clipped into doors, the user 2026-11-05)


def _slit_pool(keeps):
    """The window patterns on the game keeps' blocks, one a face: [[(along, z)]] as they would stand on a block's -y
    face (the game's five keep_01s carry two or three slits a face in their own arrangements)."""
    pool = []
    for m in keeps:
        if not any(pc[0].lower() == TIER_ID and abs(pc[1]) < 1 and abs(pc[2]) < 1 for pc in m['pieces']):
            continue
        faces = {}
        for pc in m['pieces']:
            if not re.search(r'arrowslit', pc[0], re.I) or max(abs(pc[1]), abs(pc[2])) > 440:
                continue
            x, y = pc[1], pc[2]
            q = (0 if y < 0 else 2) if abs(y) >= abs(x) else (1 if x < 0 else 3)
            a = -q * math.pi / 2                 # (back to the -y face, turned as _place turns)
            faces.setdefault(q, []).append((round(x * math.cos(a) + y * math.sin(a)), round(pc[3])))
        for pts in faces.values():
            pts = sorted(pts)
            if pts not in pool:
                pool.append(pts)
    return pool


# the joins between keep pieces in the game's own keeps (lab w37, 2026-11-05: 19 clusters, the Ebon Tower's, Firewatch's,
# Firemoth's and the Legion forts'): (kind A, kind B, du, dv, dz) in A's frame, both ways as seen; the pieces are square,
# so a join holds turned a quarter
KEEP_JOINS = [
    ('k1', 'k1', -864, 0, 496),
    ('k1', 'k1', -680, -696, -384),
    ('k1', 'k1', -680, -696, 384),
    ('k1', 'k1', -680, 168, -880),
    ('k1', 'k1', -384, 576, 96),
    ('k1', 'k1', -168, -680, 880),
    ('k1', 'k1', -12, -21, 1037),
    ('k1', 'k1', 0, -864, -496),
    ('k1', 'k1', 12, 21, -1037),
    ('k1', 'k1', 384, -576, -96),
    ('k1', 'k2', -1134, -240, -256),
    ('k1', 'k2', -1104, 680, -600),
    ('k1', 'k2', -1056, 416, -8),
    ('k1', 'k2', -864, 608, -8),
    ('k1', 'k2', -824, -712, 992),
    ('k1', 'k2', -720, 104, -696),
    ('k1', 'k2', -517, -400, 38),
    ('k1', 'k2', -424, 8, 45),
    ('k1', 'k2', -152, -824, 1488),
    ('k1', 'k2', -18, -529, -51),
    ('k1', 'k2', -18, 495, -51),
    ('k1', 'k2', -7, -508, -1088),
    ('k1', 'k2', -7, 516, -1088),
    ('k1', 'k2', 8, 680, -832),
    ('k1', 'k2', 128, -800, 0),
    ('k1', 'k2', 144, 16, 608),
    ('k1', 'k2', 376, -1112, -392),
    ('k1', 'k2', 512, -688, 48),
    ('k1', 'k2', 824, 16, 128),
    ('k2', 'k1', -1056, 416, 8),
    ('k2', 'k1', -775, 862, 256),
    ('k2', 'k1', -712, 824, -992),
    ('k2', 'k1', -680, 8, 832),
    ('k2', 'k1', -512, 688, -48),
    ('k2', 'k1', -376, 1112, 392),
    ('k2', 'k1', -128, 800, 0),
    ('k2', 'k1', -16, 144, -608),
    ('k2', 'k1', 7, -516, 1088),
    ('k2', 'k1', 7, 508, 1088),
    ('k2', 'k1', 16, -824, -128),
    ('k2', 'k1', 18, -495, 51),
    ('k2', 'k1', 18, 529, 51),
    ('k2', 'k1', 104, 720, 696),
    ('k2', 'k1', 152, 824, -1488),
    ('k2', 'k1', 424, -8, -45),
    ('k2', 'k1', 517, 400, -38),
    ('k2', 'k1', 608, 864, 8),
    ('k2', 'k1', 680, 1104, 600),
    ('k2', 'k2', -1128, -232, -1000),
    ('k2', 'k2', -664, -816, -960),
    ('k2', 'k2', -664, -816, 960),
    ('k2', 'k2', -664, -136, 1440),
    ('k2', 'k2', -608, 0, -64),
    ('k2', 'k2', -232, 1128, 1000),
    ('k2', 'k2', -192, -192, 0),
    ('k2', 'k2', -192, 192, 0),
    ('k2', 'k2', 0, -1280, 0),
    ('k2', 'k2', 0, -1024, 0),
    ('k2', 'k2', 0, -680, -480),
    ('k2', 'k2', 0, -680, 480),
    ('k2', 'k2', 0, -512, 0),
    ('k2', 'k2', 0, -384, 0),
    ('k2', 'k2', 0, 384, 0),
    ('k2', 'k2', 0, 512, 0),
    ('k2', 'k2', 0, 608, 64),
    ('k2', 'k2', 0, 1024, 0),
    ('k2', 'k2', 0, 1280, 0),
    ('k2', 'k2', 92, 1288, 12),
    ('k2', 'k2', 192, -192, 0),
    ('k2', 'k2', 192, 192, 0),
    ('k2', 'k2', 448, 1128, 520),
    ('k2', 'k2', 664, 136, -1440),
    ('k2', 'k2', 1128, -448, -520),
    ('k2', 'k2', 1288, -92, -12),
]


# (and the plain join, body to body at 768, so blocks meet at a wall line: the game's joins are mostly merges or stand
# a quarter-length apart; the user, 2026-11-05: "it's a matter of hiding their seams well enough to make them look whole")
KEEP_JOINS += [(a, b, du, dv, 0) for a in ('k1', 'k2') for b in ('k1', 'k2') for du, dv in ((768, 0), (-768, 0), (0, 768), (0, -768))] * 2
# (and up: a storey bridging two blocks, set half a block across; a roofed keep as a block's top storey, as the Ebon
# Tower sets one 1,088 over a keep_01. The user, 2026-11-05: the stacked keep pieces look cookie cutter)
KEEP_JOINS += [('k1', 'k1', du, dv, KEEP_STOREY) for du, dv in ((384, 0), (-384, 0), (0, 384), (0, -384))] * 2
KEEP_JOINS += [('k1', 'k2', 12, 21, 1088)] * 3


def _towerb(x, y, rz, z_light0, z_over, crown):
    """A big round tower's stack at (x, y): lights from z_light0 (the first light's middle) every 256 until the crown
    stands z_over or higher (the crown's foot), then the crown: 'top' (battlements) or 'roof' (the pitched roof)."""
    out = []
    z = z_light0
    while True:
        out.append((TOWERB['light'], x, y, z, rz, 0.0, 0.0, 1.0))
        if z + 128 >= z_over:
            break
        z += 256
    if crown == 'roof':
        out.append((TOWERB['roof'], x, y, z + 128, rz, 0.0, 0.0, 1.0))
    else:
        out.append((TOWERB['top'], x, y, z + 256, rz, 0.0, 0.0, 1.0))
    return out


def _tiered(db, km, rng, n_c=3, T=3, pool=None):
    """km's keep block grown into one mass of the kit's keep pieces by the joins the game's own great keeps show (the
    Ebon Tower, Firewatch's, Firemoth's, the Legion forts; lab w37, 2026-11-05): a pyramid-roofed keep_02 beside
    another at 384, 512 or 1024, or 192 off a centre in a cross so their roofs run into one; a keep_02 on a keep_02
    680 over and 480 up; a keep_01 on a keep_01; a keep_01 beside a keep_02 at 424 or 512. Each new piece is set by
    one of those joins off a piece already standing and rests on the ground or on a piece under it; the mass stays
    flush at the back (the wall line) and within its width; the keep's own doored block keeps its front. Then round
    towers as the game sets them (at a keep_02's corners from the ground, out of the top keep_01's deck), windows
    on the faces left open, and doors from the walls onto the decks they meet. n_c: the width class (3, 5, 7); T: the
    pieces (2: a few). A module dict (pieces in km's frame, the box grown), or None when km's keep isn't the plain
    block at its origin. (The user, 2026-11-05: the game's keeps "flow together, they look like a solid structure",
    not "little keep sections stacked on top of each other like milk crates".)"""
    main = [pc for pc in km['pieces'] if pc[0].lower() == TIER_ID and abs(pc[1]) < 1 and abs(pc[2]) < 1 and abs(pc[3]) < 1]
    if not main or (km.get('main') or '').lower() != TIER_ID or db.resolve_id(CROWN_ROOF) is None:
        return None
    mp = main[0]
    f = _front_axis(km)
    fv = (math.cos(f), math.sin(f))
    av = (-fv[1], fv[0])
    G = BLOCK
    rise = _rise(km)
    fd = _front_door(km)
    pieces = [pc for pc in km['pieces'] if pc is mp or re.search(r'kdoorframe', pc[0], re.I) or (abs(pc[1]) <= 440 and abs(pc[2]) <= 440)]
    frames = [pc for pc in pieces if re.search(r'kdoorframe', pc[0], re.I)]
    frame = min(frames, key=lambda pc: math.hypot(pc[1] - fd['p'][0], pc[2] - fd['p'][1])) if frames else None
    half_w = {3: 1400, 5: 2000, 7: 2600}.get(n_c, 1400)
    budget = {3: 6, 5: 9, 7: 12}.get(n_c, 6) if T >= 3 else 4
    v_back = -(G + G / 2)                        # (the back faces on the wall line, a block behind the keep's own)

    def uv(x, y):
        return (x * av[0] + y * av[1], x * fv[0] + y * fv[1])
    KINDS = {'k1': TIER_ID, 'k2': CROWN_ROOF}
    TOP = {'k1': 665, 'k2': 923}
    body = [{'kind': 'k1', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'main': True}]

    def overlap(a, b):
        """The share of b's body under a's."""
        ox = max(0.0, min(a['x'], b['x']) + G / 2 - max(a['x'], b['x']) + G / 2)
        oy = max(0.0, min(a['y'], b['y']) + G / 2 - max(a['y'], b['y']) + G / 2)
        return ox * oy / (G * G)
    tries = 0
    while len(body) < budget and tries < 600:
        tries += 1
        A = rng.choice(body)
        js = [j for j in KEEP_JOINS if j[0] == A['kind']]
        if not js:
            continue
        # (a storey up more often than not where the piece has such a join: the joins are mostly sideways, and a keep
        # grown by chance alone lay flat)
        up = [j for j in js if j[4] > 600]
        kind, du, dv, dz = (rng.choice(up) if up and rng.random() < 0.55 else rng.choice(js))[1:]
        q = rng.randrange(4)
        cq, sq = math.cos(q * math.pi / 2), math.sin(q * math.pi / 2)
        du, dv = du * cq + dv * sq, -du * sq + dv * cq
        if dz > 600:
            dz -= KEEP_SINK                      # (a storey up sinks its base into the piece under it)
        elif dz < -600:
            dz += KEEP_SINK
        B = {'kind': kind, 'x': A['x'] + du, 'y': A['y'] + dv, 'z': A['z'] + dz}
        u, v = uv(B['x'], B['y'])
        if abs(u) > half_w - G / 2 or v > 0 or v - G / 2 < v_back - 60 or B['z'] < -150 or B['z'] > 2200:
            continue                             # (four sunk storeys at most)
        if v - G / 2 < v_back + 300:
            # (flush at the back: the wall line)
            d_ = (v_back + G / 2) - v
            B['x'] += fv[0] * d_
            B['y'] += fv[1] * d_
            u, v = uv(B['x'], B['y'])
        elif v - G / 2 < v_back + 650:
            continue                             # (neither flush nor clear of the wall: the lengths behind it were cut
                                                 # for a piece within 600 of the line, a slot in the wall, lab 2026-11-05)
        # (the keep's own block and its door stay as they are: nothing merged into it at its own height)
        if abs(u) < 600 and v > -700 and abs(B['z']) < 400:
            continue
        if any(math.hypot(P['x'] - B['x'], P['y'] - B['y']) < 160 and abs(P['z'] - B['z']) < 200 for P in body):
            continue
        foot = B['z'] - 512
        if foot > -rise + 40 or B['z'] > 200:
            # (on the ground only at the keep's own level: a block a storey up with its foot under a high pad stood on
            # the dirt showing its base beside blocks buried to their pale walls)
            # (not on the ground: resting on pieces under it whose parapets reach its foot, nine tenths of it carried,
            # so a storey bridging two blocks hangs nowhere; the pieces under it clearly lower, one beside it at
            # nearly the same height is no support; a piece that drifted up by small joins stood with its foot in the
            # air, a slit under it and a gap in the wall)
            carried = sum(overlap(P, B) for P in body if P is not B and P['z'] + 300 < B['z'] and -160 <= P['z'] + TOP[P['kind']] - foot <= 700)
            if carried < 0.9:
                continue
        # (no piece into a roofed keep's pyramid but a roofed neighbour at its own height, whose roof runs into it: a
        # keep standing up through a roof was clipping, the user 2026-11-05. The roof: the cornice up, 432 each way)
        clash = False
        for P in body:
            for R, O in ((P, B), (B, P)):
                # (the roof's body, not its cornice's overhang: a block abutting a roofed keep may carry a storey, as the
                # Ebon Tower's keep stack stands between its roofed keeps)
                if R['kind'] != 'k2' or abs(R['x'] - O['x']) >= 396 + G / 2 or abs(R['y'] - O['y']) >= 396 + G / 2:
                    continue
                if O['kind'] == 'k2' and abs(O['z'] - R['z']) < 40:
                    continue
                if O['z'] - 512 < R['z'] + 1227 and O['z'] + TOP[O['kind']] > R['z'] + 771:
                    clash = True
        # (and no two blocks run far into each other: side by side they nibble a third at most (a keep block into a
        # roofed one's taller wall, three fifths), and one over another sits on its parapet, never hangs mid-wall.
        # The user, 2026-11-05: "too many overlapping clipped keep sections")
        # (the game's clean cases only: two keep blocks at one height touch at a corner at most (their parapets ran
        # into each other); a keep block runs into a roofed keep's taller wall as an annex, its parapet under the
        # cornice; two roofed keeps merge at exactly one height, their roofs one; one block over another sits on
        # the lower's parapet, never hangs mid-wall; nothing at a height a little off another's)
        for P in body:
            ov = overlap(P, B)
            if ov <= 0.02:
                continue
            lo, hi = (P, B) if P['z'] <= B['z'] else (B, P)
            dz_ = hi['z'] - lo['z']
            if dz_ < 100:
                if P['kind'] == B['kind'] == 'k1':
                    if ov > 0.12:
                        clash = True
                elif P['kind'] == B['kind'] == 'k2':
                    B['z'] = P['z']              # (one roof)
                else:
                    k1 = P if P['kind'] == 'k1' else B
                    k2 = B if k1 is P else P
                    if k1['z'] > k2['z'] + 80 or ov > 0.5:
                        clash = True
                    # (and into one roofed keep only: a block sunk into roofed keeps on two sides was left a slot of
                    # deck between their walls and a proud front, a box between two roofs; the user 2026-11-06)
                    elif any(Q is not k2 and Q is not k1 and Q['kind'] == 'k2' and abs(Q['z'] - k1['z']) < 100 and overlap(Q, k1) > 0.12
                             for Q in body + [B]):
                        clash = True
            elif dz_ < 300:
                clash = True
            elif hi['z'] - 512 < lo['z'] - 40 or hi['z'] > lo['z'] + TOP[lo['kind']] - 80:
                clash = True                     # (the upper's base below the lower's floor, or its pale wall starting over
                                                 # the lower's parapet: the base would show as a band)
        if clash:
            continue
        # (no two faces in one plane: a piece set at another's x or y, or at its height, had its sides, its deck or its
        # roof slopes flickering against the other's; a nudge of 16 parts them)
        for P in body:
            if overlap(P, B) <= 0:
                continue
            for k_ in ('x', 'y'):
                if abs(P[k_] - B[k_]) < 24:
                    if B['z'] > 300 and P['z'] + 300 < B['z']:
                        B[k_] = P[k_]            # (a sunk block centred over its carrier: its base wholly inside)
                    else:
                        B[k_] += 16 if (P[k_] <= B[k_]) else -16
        body.append(B)
    # (a keep rises: where chance left it flat, a block or two stand on a keep block the roofs leave free, as the
    # Ebon Tower's keep stands on its keep)
    if not any(P['z'] > 400 for P in body):
        for base_ in sorted([P for P in body if P['kind'] == 'k1'], key=lambda P: (P.get('main', False), rng.random())):
            if any(Q['kind'] == 'k2' and abs(Q['x'] - base_['x']) < 396 + G / 2 and abs(Q['y'] - base_['y']) < 396 + G / 2 and Q['z'] + 1227 > base_['z'] + 525 for Q in body):
                continue
            n_up = 2 if T >= 3 else 1
            for lev in range(1, n_up + 1):
                roofed = lev == n_up and rng.random() < 0.5
                body.append({'kind': 'k2' if roofed else 'k1', 'x': base_['x'] + 12 * lev, 'y': base_['y'] + 21 * lev,
                             'z': base_['z'] + (KEEP_STOREY - KEEP_SINK) * lev + (51 if roofed else 0)})
            break
    # (the pieces: the keep's own block stands already)
    def sc(P):
        return KEEP_INSET if P['z'] > 300 else 1.0
    for B in body:
        if B.get('main'):
            continue
        pieces.append((KINDS[B['kind']], B['x'], B['y'], B['z'], mp[4], 0.0, 0.0, sc(B)))

    def inside_body(x, y, z, skip=None):
        for P in body:
            if P is skip:
                continue
            if abs(x - P['x']) <= G / 2 and abs(y - P['y']) <= G / 2 and P['z'] - 512 <= z <= P['z'] + TOP[P['kind']]:
                return True
        return False
    # ---- round towers as the game sets them: at a keep_02's corners from the ground (half in it), and one rising out
    # of the top keep_01's deck, as the Ebon Tower's
    z_pad = -rise
    n_tow = 0
    tops = sorted(body, key=lambda P: -P['z'])
    for P in tops:
        if P['kind'] != 'k2' or n_tow >= 3 or rng.random() > 0.55:
            continue
        for _try in range(4):
            sx, sy = rng.choice((1, -1)), rng.choice((1, -1))
            tx, ty = P['x'] + sx * 384, P['y'] + sy * 256
            if rng.random() < 0.5:
                tx, ty = P['x'] + sx * 256, P['y'] + sy * 384
            tu, tv = uv(tx, ty)
            if inside_body(tx, ty, P['z'] + 300, skip=P) or abs(tu) > half_w or tv - 262 < v_back - 40:
                continue
            if abs(tu) < 700 and tv > -700:
                continue                         # (not before the keep's door)
            # (its crown over every roof its column rises through: a pitched roof in a pyramid's side was a clash)
            need = max([Q['z'] + 1300 for Q in body if Q['kind'] == 'k2' and abs(tx - Q['x']) < 432 + 262 and abs(ty - Q['y']) < 432 + 262] + [0])
            crown_z = max(need, P['z'] + rng.choice((960, 1216, 1280, 1856)))
            # (the darker med section at the dirt, buried a little, the base and a dark section under it: the game's
            # feet; a pale section from the dirt was 'inexplicably light', the user 2026-11-06)
            zm = z_pad - GROUND_BURY + 128
            pieces.append((TOWERB['dark'], tx, ty, zm - 640, mp[4], 0.0, 0.0, 1.0))
            pieces.append((TOWERB['base'], tx, ty, zm - 384, mp[4], 0.0, 0.0, 1.0))
            pieces.append((TOWERB['med'], tx, ty, zm, mp[4], 0.0, 0.0, 1.0))
            pieces += _towerb(tx, ty, mp[4], zm + 256, crown_z, rng.choice(('top', 'roof', 'roof')))
            n_tow += 1
            break
    top_k1 = [P for P in body if P['kind'] == 'k1' and not any(Q is not P and Q['z'] > P['z'] and overlap(Q, P) > 0.2 for Q in body)]
    if top_k1 and rng.random() < 0.7:
        P = max(top_k1, key=lambda P: P['z'])
        tx, ty = P['x'] + 96, P['y'] - 64
        pieces.append((TOWERB['med'], tx, ty, P['z'] + 644, mp[4], 0.0, 0.0, 1.0))   # (the darker section at its foot: the deck under it, where water sits)
        pieces += _towerb(tx, ty, mp[4], P['z'] + 900, P['z'] + 1284 - 128, rng.choice(('top', 'roof', 'roof')))
    # ---- windows: each face left open takes one of the game keeps' patterns, or none
    slit = next((pc for pc in pieces if re.search(r'arrowslit', pc[0], re.I)), None)
    if slit is None and db.resolve_id(SLIT_ID) is not None:
        slit = (SLIT_ID, 0.0, -SLIT_OUT, 240.0, 0.0, 0.0, 0.0, 1.0)
    pool = [p for p in (pool or []) if p] or ([[(0, 240)]] if slit else [])
    DIRS = ((0, -1), (-1, 0), (0, 1), (1, 0))
    if slit:
        for P in body:
            if P.get('main'):
                continue
            for q, (dx, dy) in enumerate(DIRS):
                if inside_body(P['x'] + dx * (G / 2 + 60), P['y'] + dy * (G / 2 + 60), P['z'] + 300, skip=P):
                    continue
                if rng.random() > SLIT_FACE:
                    continue
                a = q * math.pi / 2
                ca, sa = math.cos(a), math.sin(a)
                dz_, flip = rng.choice((-96, -48, 0, 0, 48, 96)), rng.choice((1, -1))
                for t_, sz in rng.choice(pool):
                    t_ *= flip
                    out_ = (SLIT_OUT - G / 2) + G / 2 * sc(P)   # (as far out of the face as the game's)
                    px, py = t_ * ca + (-out_) * sa, -t_ * sa + (-out_) * ca
                    pieces.append((slit[0], P['x'] + px, P['y'] + py, P['z'] + sz + dz_, a, 0.0, 0.0, 1.0, 'slit'))
    # ---- doors: where a wall of a higher piece stands on a keep_01's deck, a door onto the deck, with its frame
    RZF = {(0, -1): 0.0, (-1, 0): math.pi / 2, (0, 1): math.pi, (1, 0): 1.5 * math.pi}
    fvi = (int(round(fv[0])), int(round(fv[1])))
    rz0 = fd['p'][3] - RZF.get(fvi, 0.0)         # (the keep's own door's turn less its face's: a door's turn on any face)
    over = fd['p'][2] + rise
    doors = []
    for P in body:
        if P['kind'] != 'k1':
            continue
        deck = P['z'] + DECK * sc(P)
        if any(Q is not P and overlap(Q, P) > 0.8 and Q['z'] > P['z'] for Q in body):
            continue                             # (another block on it: no deck)
        for Q in body:
            if Q is P or not (Q['z'] - 512 < deck < Q['z'] + 500):
                continue
            for dx, dy in DIRS:
                hq = G / 2 * sc(Q)
                ox, oy = Q['x'] + dx * (hq + 90), Q['y'] + dy * (hq + 90)
                if abs(ox - P['x']) > G / 2 - 80 or abs(oy - P['y']) > G / 2 - 80:
                    continue                     # (the spot before the face is not on P's deck)
                if inside_body(ox, oy, deck + 200):
                    continue
                if any(math.hypot(ox - d[0], oy - d[1]) < 300 for d in doors):
                    continue
                # (the door as the keep's own stands at its face, just out from it, its frame a little further out)
                drz = rz0 + RZF[(dx, dy)]
                dxq, dyq = Q['x'] + dx * (hq + 28), Q['y'] + dy * (hq + 28)
                fr = None
                if frame is not None:
                    fr = (frame[0], dxq + dx * 64, dyq + dy * 64, deck + over + (frame[3] - fd['p'][2]), drz + (frame[4] - fd['p'][3]), frame[5], frame[6], frame[7])
                doors.append((dxq, dyq, deck + over, drz, fr, deck))
                if len(doors) >= 4:
                    break
    memo = {}
    xs, ys = [], []
    for pc in pieces:
        cs_, b = tw._box(db, pc[0], tw.Pose(pc[1], pc[2], pc[3], pc[4], pc[0]), memo)
        if cs_:
            xs += [p[0] for p in cs_]
            ys += [p[1] for p in cs_]
    if not xs:
        return None
    m = dict(km, pieces=pieces, box=[round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
             tiered={'doors': doors, 'tiers': {'0,0': len(body)}, 'crown': 'grown', 'front': [fv[0], fv[1]], 'n': n_c, 'T': T,
                     'kinds': {'k1': sum(1 for P in body if P['kind'] == 'k1'), 'k2': sum(1 for P in body if P['kind'] == 'k2')}, 'towers': n_tow})
    return m


# ------------------------------------------------------------------------------------------------ any shape, and wards
# A castle drawn as any shape with square corners (an L, a T, a stepped side), and a big one split into wards by cross
# walls, each with its gate and a round tower where it meets the side walls, the keep's ward at the back; the walls
# lined with the game's own halls (a barracks, an armoury, a chapel, a prison) at the game forts' rate, beside the keep
# as its wings first. (The user, 2026-11-05: "As drawn" made one large bubble with too much empty space inside; it should
# plan nested walls or a large keep, and take non-rectangular outlines.)
MIN_SIDE = 3                   # (a wall side this many lengths at least: a corner unit each end)
MAX_SIDES = 14                 # (an outline with more sides than this is a box: the game's walls run long straight sides)
WARD_LANE = 6                  # (a lower bailey this many lengths deep at least, else one ward)
WARD_SPLIT = 16                # (a lower bailey deeper than this is split again)
WARD_GROW = 6                  # (the keep's ward grows this many lengths over what the keep needs at most)
HALL_RATE_FALLBACK = 0.18      # (keeps and halls per million square units of walled ground: the game's Legion forts)
HALL_CLEAR = 1.0               # (lengths clear of a corner for a hall in the wall: the corner piece and its tower)
HALL_GAP = 250                 # (between a hall and its neighbour in the wall: the game's stand close, Frostmoth's)
HALL_USES = 2                  # (one hall module stands in a castle this often at most)
HALL_AREA_MAX = 2.5e7          # (a fort's walled ground this big at most counts for the rate: Firewatch is a town)


def _uv(F, x, y):
    """A world point in the castle frame."""
    c, s = math.cos(F['a']), math.sin(F['a'])
    return (x - F['x']) * c + (y - F['y']) * s, -(x - F['x']) * s + (y - F['y']) * c


def _area_f(P):
    n = len(P)
    return 0.5 * sum(P[k][0] * P[(k + 1) % n][1] - P[(k + 1) % n][0] * P[k][1] for k in range(n))


def _simplify(P, tol):
    """Douglas-Peucker on a closed ring (its first point kept)."""
    def dp(pts):
        if len(pts) < 3:
            return pts
        a, b = pts[0], pts[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        h = math.hypot(dx, dy) or 1.0
        best, bi = -1.0, 0
        for i in range(1, len(pts) - 1):
            d = abs((pts[i][0] - a[0]) * dy - (pts[i][1] - a[1]) * dx) / h if h > 1 else math.hypot(pts[i][0] - a[0], pts[i][1] - a[1])
            if d > best:
                best, bi = d, i
        if best <= tol:
            return [a, b]
        return dp(pts[:bi + 1])[:-1] + dp(pts[bi:])
    ring = dp(list(P) + [P[0]])
    return ring[:-1]


def _clean_f(R):
    """Doubled points, points on a straight line and spikes dropped."""
    changed = True
    while changed and len(R) >= 3:
        changed = False
        for k in range(len(R)):
            a, b, c_ = R[k - 1], R[k], R[(k + 1) % len(R)]
            if b == a or b == c_ or a == c_ or (a[0] == b[0] == c_[0]) or (a[1] == b[1] == c_[1]):
                R.pop(k)
                changed = True
                break
    return R


def _simple_f(R):
    """Whether a rectilinear ring keeps clear of itself."""
    n = len(R)
    for i in range(n):
        a, b = R[i], R[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c_, d_ = R[j], R[(j + 1) % n]
            if tw._cross(a, b, c_, d_) is not None:
                return False
    return True


def _drawn_poly(pts, F, L):
    """The drawn outline made one the wall can be laid round, in the castle frame: its wobble smoothed, its points on the
    pieces' grid, a slanting side turned into a step (the corner inside what was drawn, so the wall keeps within it),
    sides shorter than MIN_SIDE lengths merged away. Counter-clockwise [(u, v)]; None when it comes to nothing (a box
    is laid then)."""
    P = [_uv(F, x, y) for x, y in pts]
    if len(P) < 3:
        return None
    if _area_f(P) < 0:
        P.reverse()
    # (from the longest side's start: the frame's own axis, a real corner)
    k0 = max(range(len(P)), key=lambda k: math.hypot(P[(k + 1) % len(P)][0] - P[k][0], P[(k + 1) % len(P)][1] - P[k][1]))
    P = P[k0:] + P[:k0]
    area0 = _area_f(P)
    for tol in (0.75 * L, 1.5 * L, 3.0 * L):
        Q = _simplify(P, tol)
        Q = [(round(u / L) * L, round(v / L) * L) for u, v in Q]
        R = []
        n = len(Q)
        for k in range(n):
            p, q = Q[k], Q[(k + 1) % n]
            R.append(p)
            if p[0] != q[0] and p[1] != q[1]:
                legs = [(p, q)]
                if max(abs(q[0] - p[0]), abs(q[1] - p[1])) >= 6 * L:
                    m = (round((p[0] + q[0]) / 2 / L) * L, round((p[1] + q[1]) / 2 / L) * L)
                    legs = [(p, m), (m, q)]
                for a_, b_ in legs:
                    if a_ != p:
                        R.append(a_)
                    if a_[0] != b_[0] and a_[1] != b_[1]:
                        j1, j2 = (b_[0], a_[1]), (a_[0], b_[1])
                        R.append(j1 if tw._inside(P, j1) else j2)
        R = _clean_f(R)
        # (short sides merged away: the shorter of the two sides either end moves onto the other's line)
        for _ in range(60):
            if len(R) < 4:
                break
            n = len(R)
            lens = [abs(R[(k + 1) % n][0] - R[k][0]) + abs(R[(k + 1) % n][1] - R[k][1]) for k in range(n)]
            k = min(range(n), key=lambda i: lens[i])
            if lens[k] >= MIN_SIDE * L - 1:
                break
            A, B = R[k], R[(k + 1) % n]
            za, bc = lens[k - 1], lens[(k + 1) % n]
            dv = (B[0] - A[0], B[1] - A[1])
            if za <= bc:
                Z = R[k - 1]
                R[k - 1] = (Z[0] + dv[0], Z[1] + dv[1])
                R[k] = B
            else:
                C = R[(k + 2) % n]
                R[(k + 2) % n] = (C[0] - dv[0], C[1] - dv[1])
                R[(k + 1) % n] = A
            R = _clean_f(R)
        if 4 <= len(R) <= MAX_SIDES and _simple_f(R) and abs(_area_f(R)) >= 0.5 * area0:
            if _area_f(R) < 0:
                R.reverse()
            return R
    return None


def _extent_f(P):
    us = [p[0] for p in P]
    vs = [p[1] for p in P]
    return max(us) - min(us), max(vs) - min(vs)


def _side_facing(P, way):
    """The longest side whose outside faces way along v (+1: the back, -1: the front): (k, a, b) or None."""
    n = len(P)
    best = None
    for k in range(n):
        a, b = P[k], P[(k + 1) % n]
        if a[1] != b[1]:
            continue
        # (counter-clockwise: the inside is to the left; a side run along +u has its inside at +v, its outside at -v)
        out_v = -1 if b[0] > a[0] else 1
        if out_v != way:
            continue
        if best is None or abs(b[0] - a[0]) > best[0]:
            best = (abs(b[0] - a[0]), k, a, b)
    return None if best is None else best[1:]


def _chords(P, v):
    """Where a line across the castle at v lies inside the outline: [(u0, u1)], by crossing its upright sides."""
    us = []
    n = len(P)
    for k in range(n):
        a, b = P[k], P[(k + 1) % n]
        if a[0] == b[0] and min(a[1], b[1]) < v < max(a[1], b[1]):
            us.append(a[0])
    us.sort()
    return [(us[i], us[i + 1]) for i in range(0, len(us) - 1, 2)]


def _chord_clear(P, v, u0, u1, L):
    """Whether a cross wall at v from u0 to u1 stands clear of the outline's corners: two lengths from every corner at
    its ends, and from any side running along it."""
    for u, vv in P:
        if abs(vv - v) < 2 * L - 1 and (abs(u - u0) < 1 or abs(u - u1) < 1 or u0 < u < u1):
            return False
    return True


COURT_HALL = 1100              # (a hall's depth off the court's wall: room for one each side of the keep's yard)
COURT_FRONT = 2                # (lengths of yard before the court's gate, inside its ward)
COURT_BACK = 1                 # (a lane this many lengths between the court's back wall and the ward's)


def _court(P, cuts, L, eu, ev, u_keep, gap, rng=None):
    """The keep's court in a drawn castle: a walled yard at the back of the keep's ward, the keep in its back wall
    with room for a hall either side of its yard, a lane of INNER_LANE lengths between its walls and the ward's.
    (u middle, v back, n wide, n deep), or None when the ward is too small for one (the keep stands in the ward's
    back wall then)."""
    vs = [p[1] for p in P]
    v_max = max(vs)
    v_cut = cuts[0][0] if cuts else min(vs)
    vb = v_max - COURT_BACK * L
    n_w_min = max(4, int(math.ceil((eu + 2 * gap) / L - 0.1)))
    n_w_min += n_w_min % 2
    n_d_min = max(3, int(math.ceil((ev + INNER_FRONT) / L - 0.1)))
    n_w_want = int(math.ceil((eu + 2 * gap + 2 * (COURT_HALL + gap)) / L - 0.1))
    n_w_want += n_w_want % 2
    n_d_want = n_d_min + 2
    if rng is not None and n_w_want - 2 >= n_w_min and rng.random() < 0.4:
        n_w_want -= 2                        # (a narrower court, by the seed)
    for n_w2 in range(n_w_want, n_w_min - 1, -2):
        for n_d2 in (n_d_want, n_d_min):
            vf = vb - n_d2 * L
            if vf - COURT_FRONT * L < v_cut + L:
                continue
            # (the ward's width at every length of the court's depth, the lane either side included)
            fits = True
            v = vf - INNER_LANE * L
            while v <= vb + L / 2:
                ch = [c for c in _chords(P, v) if c[0] < u_keep < c[1]]
                if not ch or ch[0][0] > u_keep - n_w2 * L / 2 - INNER_LANE * L or ch[0][1] < u_keep + n_w2 * L / 2 + INNER_LANE * L:
                    fits = False
                    break
                v += L
            if fits:
                return (u_keep, vb, n_w2, n_d2)
    return None


def _ward_cuts(P, L, ev, u_keep, u_gate, rng=None):
    """Where the cross walls run: [(v, u0, u1, u_gate)] from the back forward. The keep's ward at the back, as deep as
    the keep and its yard need and up to WARD_GROW lengths more as the outline allows; a lower bailey before it when
    WARD_LANE lengths or more are left, split again when WARD_SPLIT or more."""
    vs = [p[1] for p in P]
    v_min, v_max = min(vs), max(vs)
    n_depth = int(round((v_max - v_min) / L))
    n_in_min = max(3, int(math.ceil((ev + INNER_FRONT) / L - 0.1))) + 1
    if n_depth < n_in_min + WARD_LANE:
        return []
    grow = rng.randint(2, WARD_GROW) if rng is not None else WARD_GROW    # (the keep's ward deeper or shallower, by the seed)
    n_in = max(n_in_min, min(n_in_min + grow, int(round(0.45 * n_depth))))
    cuts = []
    v = v_max - n_in * L
    for dv in (0, -1, 1, -2, 2):
        vc = v + dv * L
        ch = [c for c in _chords(P, vc) if c[0] < u_keep < c[1]]
        if ch and _chord_clear(P, vc, ch[0][0], ch[0][1], L) and (vc - v_min) / L >= WARD_LANE:
            u0, u1 = ch[0]
            ug = u_keep if u0 + 2.5 * L <= u_keep <= u1 - 2.5 * L else (u0 + u1) / 2.0
            cuts.append((vc, u0, u1, ug))
            break
    if not cuts:
        return []
    rest = int(round((cuts[0][0] - v_min) / L))
    if rest >= WARD_SPLIT:
        v = cuts[0][0] - (int(round(rest / 2.0)) + (rng.choice((-1, 0, 0, 1)) if rng is not None else 0)) * L
        for dv in (0, -1, 1, -2, 2):
            vc = v + dv * L
            ch = [c for c in _chords(P, vc) if c[0] < u_gate < c[1]]
            if ch and _chord_clear(P, vc, ch[0][0], ch[0][1], L) and (vc - v_min) / L >= WARD_LANE and (cuts[0][0] - vc) / L >= WARD_LANE:
                u0, u1 = ch[0]
                ug = u_gate if u0 + 2.5 * L <= u_gate <= u1 - 2.5 * L else (u0 + u1) / 2.0
                cuts.append((vc, u0, u1, ug))
                break
    return cuts


def _wards(P, cuts, F):
    """The wards' outlines in the world, the gate's first, the keep's last: the outline clipped to the band between
    one cross wall and the next."""
    if not cuts:
        return [[_to_world(F, u, v) for u, v in P]]
    vs = [p[1] for p in P]
    bands = [min(vs)] + [c[0] for c in sorted(cuts)] + [max(vs)]
    out = []
    for i in range(len(bands) - 1):
        v_lo, v_hi = bands[i], bands[i + 1]
        pts = []
        for u, v in P:
            q = (u, max(v_lo, min(v_hi, v)))
            if not pts or pts[-1] != q:
                pts.append(q)
        pts = _clean_f(pts)
        if len(pts) >= 3:
            out.append([_to_world(F, u, v) for u, v in pts])
    return out


def _module_rate(S, style):
    """Keeps and halls per square unit of walled ground in the game's forts of this style."""
    n, area = 0, 0.0
    for f in S['forts']:
        ws = f.get('wall_size')
        if f['style'] != style or not ws or (f.get('wall') or {}).get('pieces', 0) < 12:
            continue
        a = ws[0] * ws[1]
        if a > HALL_AREA_MAX:
            continue
        n += f.get('keeps') or 0
        area += a
    return n / area if area else HALL_RATE_FALLBACK / 1e6


def _wall_extent(m, F, d):
    """A module's reach along a wall running d and out from it once turned to face in off that wall: (along, out, M)."""
    n_in = (-d[1], d[0])
    fu, fv = _uv(dict(F, x=0.0, y=0.0), n_in[0] * 1e6, n_in[1] * 1e6)
    M = _set_module(m, F, 0.0, 0.0, face=(fu, fv))
    kb = m['box']
    Pz = (0.0, 0.0, 0.0, M['rz'])
    rel = [_place(Pz, lx, ly) for lx in (kb[0], kb[2]) for ly in (kb[1], kb[3])]
    al = [x * d[0] + y * d[1] for x, y in rel]
    ou = [-(x * n_in[0] + y * n_in[1]) for x, y in rel]
    return max(al) - min(al), max(ou) - min(ou), M


def _in_wall(db, m, F, W, a, b, t, L, tall=None, cut=True):
    """A module standing in the wall line along the side a→b (walked with the inside on its left), its middle t along
    the side, its face to the yard: a tall one with its back at the wall's outer face and the lengths it covers left
    out (as the game's keeps stand, Old Ebonheart's, Moonmoth's); a low one against the wall's inner face, the wall
    whole behind it (Umbermoth's hall). The module dict."""
    d = tw._unit(b[0] - a[0], b[1] - a[1])
    n_in = (-d[1], d[0])
    n_out = (-n_in[0], -n_in[1])
    _al, _ou, M = _wall_extent(m, F, d)
    kb = m['box']
    Pz = (0.0, 0.0, 0.0, M['rz'])
    rel = [_place(Pz, lx, ly) for lx in (kb[0], kb[2]) for ly in (kb[1], kb[3])]
    al = [x * d[0] + y * d[1] for x, y in rel]
    outs = [x * n_out[0] + y * n_out[1] for x, y in rel]
    # (the wall's faces on this side: the corners of its lengths along the side, the farthest out and the least)
    span = math.hypot(b[0] - a[0], b[1] - a[1])
    face_out, face_in = 0.0, 0.0
    got = False
    for p in W['pieces']:
        if p.get('kind') != 'wall' or not p.get('corners'):
            continue
        q = p['pose']
        off = (q.x - a[0]) * n_out[0] + (q.y - a[1]) * n_out[1]
        along = (q.x - a[0]) * d[0] + (q.y - a[1]) * d[1]
        if abs(off) > L / 2 or along < -L or along > span + L:
            continue
        for cx_, cy_ in p['corners']:
            o = (cx_ - a[0]) * n_out[0] + (cy_ - a[1]) * n_out[1]
            if not got:
                face_out = face_in = o
                got = True
            face_out = max(face_out, o)
            face_in = min(face_in, o)
    if tall is None:
        tall = _mesh_tall(db, m)
    mr = _mesh_reach(db, m, M['rz'], n_out[0], n_out[1])
    reach = max(outs) if mr is None else mr
    target = face_out if tall else face_in
    x = a[0] + d[0] * (t - (min(al) + max(al)) / 2.0) + n_out[0] * (target - reach)
    y = a[1] + d[1] * (t - (min(al) + max(al)) / 2.0) + n_out[1] * (target - reach)
    M.update(x=x, y=y)
    M['in_wall'] = True
    M['side'] = (tuple(a), tuple(b))
    M['along'] = t
    kpts = [_place((x, y, 0.0, M['rz']), lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))]
    M['pts'] = kpts
    if cut:
        W['pieces'] = _cut_by_module(db, W, M, kpts)
    return M


def _fill_walls(db, S, style, P, W, F, L, polyf, cuts, km, rng, gap, keeps, avoid=None, most=None, want=None, front_ok=False):
    """Halls in the wall lines at the game forts' rate of keeps and halls to walled ground (Frostmoth's four, Fort
    Heath's four): beside the keep as its wings first, then round the keep's ward, then the lower wards, the longest
    free stretch of wall first; never on the gate's side, nor within HALL_CLEAR lengths of a corner, a cross wall's
    junction or a gatehouse. Each of the game's hall modules at most HALL_USES times. [modules]."""
    halls = _modules(S, style, 'hall') + [m for m in keeps if m is not km]
    if not halls or not polyf:
        return []
    area = abs(_area_f(polyf))
    if want is None:
        want = int(round(area * _module_rate(S, style))) - 1
    if most is not None:
        want = min(want, most)
    if _DEBUG[0]:
        print('  fill: area %.1f Mu2 want %d most %s halls %d' % (area / 1e6, want, most, len(halls)))
    if want <= 0:
        return []
    n = len(polyf)
    front = _side_facing(polyf, -1)
    back = _side_facing(polyf, 1)
    sides = []
    for k in range(n):
        if front and k == front[0] and not front_ok:
            continue
        a, b = polyf[k], polyf[(k + 1) % n]
        Ls = abs(b[0] - a[0]) + abs(b[1] - a[1])
        taken = [(-1e9, HALL_CLEAR * L), (Ls - HALL_CLEAR * L, 1e9)]
        aw, bw = _to_world(F, *a), _to_world(F, *b)
        dw = tw._unit(bw[0] - aw[0], bw[1] - aw[1])
        nw = (-dw[1], dw[0])
        # (gates and gatehouses on this side, by where they stand: the wall layer numbers its runs its own way round)
        for p in W['pieces']:
            if p.get('kind') in ('gate', 'end'):
                q = p['pose']
                t = (q.x - aw[0]) * dw[0] + (q.y - aw[1]) * dw[1]
                off = (q.x - aw[0]) * nw[0] + (q.y - aw[1]) * nw[1]
                if abs(off) > L / 2 or t < -L or t > Ls + L:
                    continue
                r = 2.5 * L if p.get('gatehouse') else 1.5 * L
                taken.append((t - r, t + r))
                if _DEBUG[0]:
                    print('  side %d: gate %s at %.0f' % (k, p['id'], t))
        for vc, u0, u1, ug in cuts:
            for u in (u0, u1):
                if abs(u - a[0]) < 1 and abs(u - b[0]) < 1 and min(a[1], b[1]) <= vc <= max(a[1], b[1]):
                    t = abs(vc - a[1])
                    taken.append((t - 2 * L, t + 2 * L))
        # (the keep and whatever stands in this wall already)
        for M in P['modules']:
            if M.get('side') == (tuple(aw), tuple(bw)):
                al, _o, _m = _wall_extent(M['m'], F, dw)
                taken.append((M['along'] - al / 2, M['along'] + al / 2))
                if _DEBUG[0]:
                    print('  side %d: module %s at %.0f al %.0f' % (k, M['m']['fort'][:10], M['along'], al))
        # (the inner ward's wall and lane, where they run along this side: nothing stands in the lane)
        if avoid is not None:
            n_in = (-dw[1], dw[0])
            ts = [(q[0] - aw[0]) * dw[0] + (q[1] - aw[1]) * dw[1] for q in avoid]
            ds = [(q[0] - aw[0]) * n_in[0] + (q[1] - aw[1]) * n_in[1] for q in avoid]
            if min(ds) < 2600 and max(ts) > 0 and min(ts) < Ls:
                taken.append((min(ts), max(ts)))
        # (which ward: the keep's is behind the first cut)
        mid_v = (a[1] + b[1]) / 2.0
        ward = 0 if not cuts else (2 if mid_v >= cuts[0][0] else 1)
        sides.append({'k': k, 'a': aw, 'b': bw, 'd': dw, 'L': Ls, 'taken': taken, 'back': bool(back and k == back[0]), 'ward': ward})
    used = Counter()
    out = []
    for rnd in range(HALL_USES):
        order = sorted(sides, key=lambda s: (0 if s['back'] else 1, -s['ward'], -s['L']))
        for s in order:
            while want > 0:
                # (the free stretches of this side, longest first; by the keep on the back wall)
                iv = sorted(s['taken'])
                free_ = []
                t0 = 0.0
                for lo, hi in iv:
                    if lo > t0:
                        free_.append((t0, lo))
                    t0 = max(t0, hi)
                if t0 < s['L']:
                    free_.append((t0, s['L']))
                free_ = [f for f in free_ if f[1] - f[0] >= 2 * gap + 800 and f[1] > f[0]]
                if _DEBUG[0]:
                    print('  fill side %d want %d (back %s ward %d L %.0f): taken %s free %s' % (s['k'], want, s['back'], s['ward'], s['L'], [(round(a_), round(b_)) for a_, b_ in iv], [(round(a_), round(b_)) for a_, b_ in free_]))
                if not free_:
                    break
                keep_t = s['L'] / 2.0
                if s['back']:
                    keep_t = next((M['along'] for M in P['modules'] if M.get('side') == (tuple(s['a']), tuple(s['b']))), s['L'] / 2.0)
                    free_.sort(key=lambda f: min(abs(f[0] - keep_t), abs(f[1] - keep_t)))
                else:
                    free_.sort(key=lambda f: -(f[1] - f[0]))
                lo, hi = free_[0]
                room = hi - lo - 2 * gap
                fit = []
                for m in halls:
                    key = (m['fort'], m['main'], tuple(m['box']))
                    if used[key] > rnd:
                        continue
                    al, ou, _m = _wall_extent(m, F, s['d'])
                    if al <= room:
                        fit.append((0 if _mesh_tall(db, m) else 1, -al * ou, rng.random(), m, al))
                if _DEBUG[0]:
                    print('    stretch %.0f..%.0f room %.0f fits %d' % (lo, hi, room, len(fit)))
                if not fit:
                    s['taken'].append((lo, hi))
                    continue
                fit.sort(key=lambda t: t[:3])
                M = None
                for _a, _b, _c, m, al in fit[:3]:
                    # (its spots along the stretch: a wing against the keep, else the middle, then either end)
                    if s['back']:
                        spots = [lo + gap + al / 2.0] if abs(lo - keep_t) < abs(hi - keep_t) else [hi - gap - al / 2.0]
                    else:
                        spots = [(lo + hi) / 2.0, lo + gap + al / 2.0, hi - gap - al / 2.0]
                    for t in spots:
                        M = _in_wall(db, m, F, W, s['a'], s['b'], t, L, cut=False)
                        bad = avoid is not None and _sat_depth(M['pts'], [tuple(q) for q in avoid]) > 0
                        bad2 = any(_sat_depth(M['pts'], O['pts']) > -gap / 2 for O in P['modules'] + out if O.get('pts'))
                        if _DEBUG[0]:
                            print('      %s %s at %.0f: avoid %s modules %s' % (m['fort'][:10], m['roles'], t, bad, bad2))
                        bad = bad or bad2
                        if not bad:
                            break
                        M = None
                    if M is not None:
                        break
                if M is None:
                    s['taken'].append((lo, hi))
                    continue
                W['pieces'] = _cut_by_module(db, W, M, M['pts'])
                out.append(M)
                used[(m['fort'], m['main'], tuple(m['box']))] += 1
                s['taken'].append((t - al / 2, t + al / 2))
                want -= 1
                break
            if want <= 0:
                break
        if want <= 0:
            break
    return out


def _cross_wall(db, kit, F, L, u0, u1, v, ug, run, faults):
    """A cross wall between two side walls at v, from u0 to u1, its gate at ug: straights at the step with the kit's
    gate where the way crosses, walked so its buttresses face the gate's side. [pieces], each tagged run."""
    a = _to_world(F, u0, v)
    b = _to_world(F, u1, v)
    d = tw._unit(b[0] - a[0], b[1] - a[1])
    rz = tw._rz_for(kit, d)
    S0 = tw.Pose(a[0] + d[0] * L / 2.0, a[1] + d[1] * L / 2.0, 0.0, rz, kit['straight'])
    D = (u1 - u0) - L
    side, _g = tw._side(kit, S0, D, d, [ug - u0 - L / 2.0], faults, run)
    pieces = [{'id': kit['straight'], 'pose': S0, 'kind': 'wall'}] + side
    last = tw.Pose(b[0] - d[0] * L / 2.0, b[1] - d[1] * L / 2.0, 0.0, rz, kit['straight'])
    if not any(math.hypot(p['pose'].x - last.x, p['pose'].y - last.y) < L / 2 for p in pieces):
        pieces.append({'id': kit['straight'], 'pose': last, 'kind': 'wall'})
    for p in pieces:
        p['run'] = run
        p['cross'] = True
    return pieces


def _cross_towers(W, kit, F, L, cuts):
    """Round towers where each cross wall meets the side walls (the walk runs three ways out of them) and flanking its
    gate, as the outer gate's. [{'x', 'y', 'rz', 'dirs', 'kind', 'run'}]."""
    out = []
    poly = W['outline']
    n = len(poly)
    cx, cy = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    for j, (vc, u0, u1, ug) in enumerate(cuts):
        a = _to_world(F, u0, vc)
        b = _to_world(F, u1, vc)
        d = tw._unit(b[0] - a[0], b[1] - a[1])
        for end, din in ((a, d), (b, (-d[0], -d[1]))):
            # (the side wall it stands in: the outline side nearest)
            k = min(range(n), key=lambda i: _seg_dist(end[0], end[1], poly[i], poly[(i + 1) % n]))
            e = tw._unit(poly[(k + 1) % n][0] - poly[k][0], poly[(k + 1) % n][1] - poly[k][1])
            # (16 out of the side wall's line, as the other towers: the length through it stood proud of its face)
            nrm = (e[1], -e[0])
            if (end[0] - cx) * nrm[0] + (end[1] - cy) * nrm[1] < 0:
                nrm = (-nrm[0], -nrm[1])
            out.append({'x': end[0] + nrm[0] * TOWER_OUT, 'y': end[1] + nrm[1] * TOWER_OUT, 'rz': tw._rz_for(kit, e), 'dirs': [e, (-e[0], -e[1]), din], 'kind': 'junction', 'run': k})
        run = INNER_RUN + j
        gates = [p for p in W['pieces'] if p.get('run') == run and p.get('kind') in ('gate', 'end')]
        if gates:
            G = gates[0]['pose']
            ga = (G.x - a[0]) * d[0] + (G.y - a[1]) * d[1]
            side = sorted([p for p in W['pieces'] if p.get('run') == run and p.get('kind') == 'wall'], key=lambda p: (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1])
            before = [p for p in side if (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1] < ga]
            after = [p for p in side if (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1] > ga]
            # (at the joint away from the gate, 16 off the wall line, as the outer walls' towers: _towers)
            for p, sgn in ([(before[-1], -1.0)] if before else []) + ([(after[0], 1.0)] if after else []):
                q = p['pose']
                x, y = q.x + d[0] * sgn * 256 + d[1] * TOWER_OUT, q.y + d[1] * sgn * 256 - d[0] * TOWER_OUT
                if any(math.hypot(x - t['x'], y - t['y']) < 900 for t in out):
                    continue
                out.append({'x': x, 'y': y, 'rz': q.rz, 'dirs': [d, (-d[0], -d[1])], 'kind': 'gate', 'run': run, 'on': id(p)})
    return out


def _tower_pieces(W, kit, towers):
    """The wall's pieces once the round towers stand: a wall_tower_01 in a round tower's place goes, and a buttressed
    length beside one is a plain length (the round tower is the corner and the length it stands on; the buttressed
    lengths of the game's corner beside it stood as a second tower at every corner, the user 2026-11-03)."""
    # (a wall_tower_01 under a junction tower is a plain length, not dropped: dropped, it left a hole beside the round
    # tower, which covers less than the length, lab w5 2026-11-05)
    keep = []
    for p in W['pieces']:
        dd = min((math.hypot(p['pose'].x - t['x'], p['pose'].y - t['y']) for t in towers), default=1e9)
        if p.get('kind') in ('corner', 'tower') and dd < TOWER_BESIDE and kit.get('straight') and 'tower' in p['id'].lower():
            q = p['pose']
            p = dict(p, id=kit['straight'], kind='wall', pose=tw.Pose(q.x, q.y, q.z, q.rz, kit['straight']))
            p.pop('corners', None)
        keep.append(p)
    W['pieces'] = keep


def _towers(W, kit, F, corners=False):
    """Where the round towers stand: each corner of the wall, the lengths either side of the gate, and a length every
    TOWER_EVERY along longer sides. [{'x', 'y', 'rz', 'dirs': [(dx, dy) the ways the wall runs out of it], 'kind'}]."""
    poly = W['outline']
    n = len(poly)
    out = []
    # (the wall is walked whichever way round its kit's corners ask: an outer corner turns the way the whole does)
    sg = 1.0 if _area_f(poly) > 0 else -1.0
    cx, cy = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        din = tw._unit(a[0] - b[0], a[1] - b[1])
        dout = tw._unit(c_[0] - b[0], c_[1] - b[1])
        # (the game's fort corners are its corner piece alone, 26 of 30; a round tower at a corner, as Pelagiad's and
        # Windmoth's, only at a large castle's back corners; a castle of wards has them at every outer corner, as
        # Firewatch's walls)
        if not corners or (corners != 'all' and -(b[0] - F['x']) * math.sin(F['a']) + (b[1] - F['y']) * math.cos(F['a']) <= 0):
            continue
        if (-din[0] * dout[1] + din[1] * dout[0]) * sg <= 0:
            continue                     # (an inside corner of an L or a notch: a tower there stood into the yard)
        # (16 out of the corner: the corner piece's faces stood 6 proud of the tower's, a sliver of wall on the tower)
        out.append({'x': b[0] - (din[0] + dout[0]) * TOWER_OUT, 'y': b[1] - (din[1] + dout[1]) * TOWER_OUT, 'rz': tw._rz_for(kit, (-din[0], -din[1])), 'dirs': [din, dout], 'kind': 'corner', 'run': k})
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
        # (the tower at a joint of two lengths, 16 out of the wall line, as the game's square towers stand (lab w59:
        # the lengths either side 384 off the tower, their ends 34 in it, none through it): a length through the tower
        # stood 6 proud of its outer face, a wall across the tower's foot. Beside a gate, the joint away from the gate)
        nrm = (d[1], -d[0])
        if (((a[0] + b[0]) / 2 - cx) * nrm[0] + ((a[1] + b[1]) / 2 - cy) * nrm[1]) < 0:
            nrm = (-nrm[0], -nrm[1])
        for p in picks:
            q = p['pose']
            along = (q.x - a[0]) * d[0] + (q.y - a[1]) * d[1]
            if g:
                G = g[0]['pose']
                sgn = -1.0 if along < (G.x - a[0]) * d[0] + (G.y - a[1]) * d[1] else 1.0
            else:
                sgn = 1.0
            x, y = q.x + d[0] * sgn * 256 + nrm[0] * TOWER_OUT, q.y + d[1] * sgn * 256 + nrm[1] * TOWER_OUT
            if any(math.hypot(x - t['x'], y - t['y']) < 900 for t in out):
                continue
            out.append({'x': x, 'y': y, 'rz': q.rz, 'dirs': [d, (-d[0], -d[1])], 'kind': 'gate' if g else 'side', 'run': k, 'on': id(p)})
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
         'keeps': len(P['modules']), 'tiers': max([((M['m'].get('tiered') or {}).get('T') or 1) for M in P['modules']] or [0]), 'wards': len(P.get('wards') or [[]]) + (1 if P.get('inner') else 0), 'interiors': sum(len(M['m']['network']) for M in P['modules']) + (1 if P['towers'] else 0),
         'doors_out': sum(len(M['m']['doors']) for M in P['modules']) + sum(len(t['dirs']) + 1 for t in P['towers'])}
    return f


def _game_figures(S, style):
    fs = [f for f in S['forts'] if f['style'] == style]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    return {'forts': len(fs), 'interiors': med([f['interiors'] for f in fs]), 'doors_out': med([f['doors_out'] for f in fs]),
            'links': med([f['links'] for f in fs]), 'npcs': med([f['npcs'] for f in fs]),
            'wall_size': [med([min(f['wall_size']) for f in fs if f.get('wall_size') and f['wall']['pieces'] >= 12]),
                          med([max(f['wall_size']) for f in fs if f.get('wall_size') and f['wall']['pieces'] >= 12])],
            'towers': med([f['wall']['towers'] for f in fs if f.get('wall')]), 'keeps': med([f.get('keeps') or 0 for f in fs if f.get('wall')]),
            'examples': [f['name'] for f in fs][:8]}


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
    out = dict(PROGRESS)
    try:
        import townbuild
        if out['on'] and townbuild.PROGRESS.get('on') and townbuild.PROGRESS.get('what'):
            out['what'] = '%s: %s' % (out['what'], townbuild.PROGRESS['what'])
    except Exception:
        pass
    return out


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


def _pair_dead(db, cells, links, load_only=()):
    """The doors of these rooms that lead nowhere (no link set, not a trap door) paired two by two, each to the
    other's room at the other's spot (face_arrivals then sets the arrival at the door's face); an odd one left
    leads out where the room's first way out does. The number of doors linked. load_only: cells whose doors that
    only swing in their frames are left alone (a made keep's in_impsmall_door_01 are not ways anywhere)."""
    import doors
    linked = {(ck, rk) for ck, rk, _d, _p in links}
    dead = []
    for ck in cells:
        m = mapdata.cellmap(db, ck)
        nm = (mapdata.cell_info(db, ck) or {}).get('name') or ck
        for r in m.get('refs') or ():
            if r['type'] == 'DOOR' and not r.get('to') and (ck, r['k']) not in linked and not re.search(r'trap|hatch', r['id'], re.I):
                if ck in load_only and not re.search(r'loaddoor', r['id'], re.I):
                    continue
                dead.append((ck, nm, r))
    if not dead:
        return 0
    # (pairs from different rooms first, the farthest apart: a passage, not a door to the room next door)
    n = 0
    while len(dead) >= 2:
        a = dead.pop(0)
        others = [d for d in dead if d[0] != a[0]] or dead
        b = max(others, key=lambda d: (d[0] != a[0], math.dist(d[2]['p'][:2], a[2]['p'][:2])))
        dead.remove(b)
        for x, y in ((a, b), (b, a)):
            _link(db, x[0], x[2]['k'], y[1], [y[2]['p'][0], y[2]['p'][1], y[2]['p'][2], 0.0, 0.0, (y[2]['p'][5] + math.pi) % (2 * math.pi)])
            n += 1
    for ck, nm, r in dead:
        out = next((p_ for c_, _r, d_, p_ in links if c_ == ck and d_ == '' and p_ and not callable(p_)), None)
        if out:
            _link(db, ck, r['k'], '', out)
            n += 1
    if n:
        db.sync_project()
    return n


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
    if rooms == 'furnished' and P['modules'] and P['modules'][0]['m'].get('tiered'):
        # (a tiered keep's rooms are made anew to its size, several storeys and the doors on its decks: the game
        # rooms it would copy are a small fort's. The user, 2026-11-05: interiors consistent in size and linkage)
        import dwemer
        if dwemer.ready(db, 'fort') is not None:
            rooms = 'made'
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
        # (the town's buildings round the castle keep their ground: its wall's fill buried a house's entrance, 2026-11-06)
        try:
            guard = tw.building_guard(db, W.get('outline') or []) + tw.wall_guard(db, W.get('outline') or [])
        except Exception as e:
            print('castle guard:', e)
            guard = []
        try:
            tw.level_ground(db, W, skip, tol=CASTLE_LEVEL_TOL, keep=guard)
        except Exception as e:
            print('castle wall ground:', e)
        # (the wall's levels known before the keep's pad: a keep in the wall line stands at the wall's level)
        db.sync_project()
        W = tw.grounded(db, W)
        try:
            tw.fill_ground(db, W, skip, keep=guard)         # (the ground up to the feet of the stretches raised out of a dip)
        except Exception as e:
            print('castle wall fill:', e)
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
    slits_later = []                             # [(module index, piece)]: the tiered keep's windows, set after its doors
    walk_cand = {}                               # {module index: [its upper doors that open onto no walk of ours]}
    _say('Raising the keep', 0.4)
    for mi, M in enumerate(P['modules']):
        m = M['m']
        Z = M['ground'] + _rise(m)
        Pz = (M['x'], M['y'], Z, M['rz'])
        M['pose'] = Pz
        for pc in m['pieces']:
            if len(pc) > 8 and pc[8] == 'slit':
                slits_later.append((mi, pc))     # (the mass's windows: after the doors, clear of them)
                continue
            x, y = _place(Pz, pc[1], pc[2])
            wr.put(pc[0], (x, y, Z + pc[3], pc[5], pc[6], M['rz'] + pc[4]), pc[7])
        upper = None
        if mi == 0 and m.get('tiered'):
            # (the tiered keep's doors from its back row's upper storeys onto the decks before them: they lead into
            # the keep as its front door does; its door frame with each)
            fd = _front_door(m)
            fv = m['tiered']['front']
            for lx, ly, lz, lrz, fr, deck in m['tiered']['doors']:
                if fr:
                    fx, fy = _place(Pz, fr[1], fr[2])
                    wr.put(fr[0], (fx, fy, Z + fr[3], fr[5], fr[6], M['rz'] + fr[4]), fr[7])
                ux, uy = _place(Pz, lx, ly)
                wx, wy = _place(Pz, lx + fv[0] * 110, ly + fv[1] * 110)
                got = wr.put(fd['id'], (ux, uy, Z + lz, 0.0, 0.0, M['rz'] + lrz), fd.get('s') or 1.0)
                if got:
                    mdoors.append((mi, dict(fd, p=[lx, ly, lz, lrz], walk=True, upper=True, walk_out=[wx, wy, Z + deck + 8, 0.0, 0.0, _facing(wx - ux, wy - uy)]), got))
        elif mi == 0 and P.get('tall') and re.search(r'^ex_imp_keep_01$', m['main'], re.I):
            # (a storey more: a keep piece on the keep piece, as the Ebon Tower stacks its own; the upper piece's door
            # opens onto the lower's roof walk and leads into the keep too)
            wr.put(m['main'], (M['x'], M['y'], Z + KEEP_STOREY, 0.0, 0.0, M['rz']))
            fd = _front_door(m)
            ux, uy = _place(Pz, fd['p'][0], fd['p'][1])
            uz = Z + fd['p'][2] + KEEP_STOREY
            ox, oy = tw._unit(ux - M['x'], uy - M['y'])
            got = wr.put(fd['id'], (ux, uy, uz, 0.0, 0.0, M['rz'] + fd['p'][3]), fd.get('s') or 1.0)
            if got:
                upper = dict(fd, p=[fd['p'][0], fd['p'][1], fd['p'][2] + KEEP_STOREY, fd['p'][3]], walk=True, upper=True,
                             walk_out=[ux + ox * 110, uy + oy * 110, uz - 88, 0.0, 0.0, _facing(ox, oy)])
                mdoors.append((mi, upper, got))
        for dd in m['doors']:
            x, y = _place(Pz, dd['p'][0], dd['p'][1])
            if not _stood_on(db, M, Pz, dd, W):
                if dd.get('back') and dd.get('to') in m['network'] and not re.search(r'trap|hatch', dd['id'], re.I):
                    walk_cand.setdefault(mi, []).append(dd)
                continue                         # (a door out onto the game fort's walk or bridge, not here: its room
                                                 # leads out by the keep's front door instead)
            if (rooms != 'none' and (rooms != 'made' or mi > 0)) and dd.get('to') and (dd['to'] not in m['network'] or not db.by_key.get(('CELL', dd['to']))):
                continue                         # (a door into a room the castle hasn't: it led nowhere, an
                                                 # ex_nord_door_01 on a Redoran manor, lab c01)
            got = wr.put(dd['id'], (x, y, Z + dd['p'][2], 0.0, 0.0, M['rz'] + dd['p'][3]), dd.get('s') or 1.0)
            if got:
                mdoors.append((mi, dd, got))
    if W is not None:
        mdoors += _walk_doors(db, wr, P, W, walk_cand, every=(rooms == 'made'))
    # (the tiered keep's windows now, none where a door or a walk arch stands on the face)
    near = [g[2][:3] for _mi, _dd, g in mdoors]
    for mi, pc in slits_later:
        M = P['modules'][mi]
        Pz = M['pose']
        x, y = _place(Pz, pc[1], pc[2])
        z = Pz[2] + pc[3]
        if any(math.hypot(x - nx, y - ny) < SLIT_DOOR_CLEAR and abs(z - nz) < 450 for nx, ny, nz in near):
            continue
        wr.put(pc[0], (x, y, z, pc[5], pc[6], M['rz'] + pc[4]), pc[7])
    editing.commit(db, 'Built %s outside: %d pieces' % (name, len(wr.refs)))
    # ---- the lower wards: quarters of streets and houses, planned round what stands (the walls, towers, halls and
    # gates are its obstacles now), as the game's big castles are towns inside their walls
    quarters = []
    for qi, wp in enumerate(P.get('quarters') or []):
        _say('Building the %s quarter' % ('lower', 'middle', 'upper')[min(qi, 2)], 0.46 + 0.02 * qi)
        try:
            import townbuild
            import townplan
            q_poly = townplan.inset([tuple(q) for q in wp], townbuild.WALL_BACK)
            # (its main street from the ward's gate to the next: the way through stays open)
            g_in = _ward_gate(P['frame'], P, qi) if qi else tuple(P['gate_at'])
            g_out = _ward_gate(P['frame'], P, qi + 1)
            opts = {'nokeep': True, 'roads': [[list(g_in), list(g_out)]], 'density': 1.0, 'streets': 'narrow'}
            qr = townbuild.make(db, q_poly, NAME_CULTURE.get(style, 'Imperial'), seed + qi, walls='', dress=True, interiors=rooms != 'none', people=people, name=name, opts=opts)
            quarters.append({'buildings': qr.get('buildings', 0), 'interiors': qr.get('interiors', 0), 'people': qr.get('people', 0)})
        except Exception as e:
            print('castle quarter:', e)
    # (the bailey's sets after the quarters, whose ground passes reach into the keep's ward: set out before them, 117
    # barrels, crates and baskets stood sunk in the raised ground of Fort Skethwest's yard, the in-game walk 2026-11-07)
    if W is not None:
        _say('Setting out the bailey', 0.49)
        n0 = len(wr.refs)
        try:
            for rid, pos, s_ in _bailey(db, P, W, rng):
                wr.put(rid, pos, s_)
        except Exception as e:
            print('castle bailey:', e)
        if len(wr.refs) > n0:
            editing.commit(db, 'Set out the bailey of %s: %d things' % (name, len(wr.refs) - n0))
    db.sync_project()
    # ---- inside
    _say('Copying the rooms', 0.5)
    links = []                                   # (cell, rk, destination name, position)
    names = {}
    keys = {}
    to_towers = []                               # (cell, rk) inside doors the game led to its towers
    loose = []                                   # inside doors that led out where this castle has no door
    made = None
    if rooms == 'made':
        # (the keep's interiors made anew, several of them linked door to door, and one interior for each run of wall
        # towers: keepmaker.py, the keep study of 2026-11-05)
        _say('Making the keep\'s interiors', 0.55)
        made = _made_inside(db, P, W, mdoors, tdoors, name, size, seed, people, free, lambda what, frac: _say(what, 0.55 + 0.3 * frac))
        links += made['links']
    # (rooms made anew: the keep's; its halls keep the game rooms' shells behind their doors, furnished by the Workshop)
    for mi, M in enumerate(P['modules']) if rooms != 'none' else ():
        if rooms == 'made' and mi == 0:
            continue
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
    if P['towers'] and tdoors and rooms not in ('none', 'made'):
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
    # (the copied rooms' doors into rooms this castle hasn't, left plain: 7 in a keep, 6 in a hall, the user's Fort
    # Estmoth. Paired across the castle's own rooms so each opens somewhere, the odd one out by the way in)
    try:
        n_dead = _pair_dead(db, [k for k in keys.values()] + ([tower_key] if tower_key else []) + (made['cells'] if made else []), links,
                            load_only=set(made['cells']) if made else ())
        if n_dead:
            print('castle: %d door(s) that led nowhere paired within %s' % (n_dead, name))
    except Exception as e:
        print('castle dead doors:', e)
    editing.commit(db, 'Linked the doors of %s' % name)
    try:
        import doors as doors_
        doors_.face_arrivals(db, sorted(wr.cells))      # (every arrival at the face of the door it pairs with)
    except Exception as e:
        print('door arrivals:', e)
    # ---- furnished by the Workshop's own furnisher, each room by its kind
    placed = 0
    if rooms in ('furnished', 'made') and keys:
        _say('Furnishing the rooms', 0.88)
        for (mi, g), k in sorted(keys.items()):
            placed += furnish_shell(db, k, g, seed=zlib.crc32(('%s|%s' % (seed, k)).encode()))
        if tower_key:
            # (the towers are the garrison's: guardroom, barracks, armoury by storey; with no source room to read a
            # kind off, 54 tower rooms held 48 things between them, the user's Fort Fostmoth, 2026-11-04)
            import towninside
            placed += furnish_shell(db, tower_key, None, seed=seed, kinds=towninside.household_kinds(db, tower_key, 'guard', None))
        editing.commit(db, 'Furnished the rooms of %s' % name)
    # ---- people
    folks = 0
    if people and rooms in ('furnished', 'made') and keys:
        _say('Placing the people', 0.9)
        folks = _people(db, keys, names, seed)
    n_in = len(keys) + (1 if tower_key else 0) + (len(made['cells']) if made else 0) + sum(q['interiors'] for q in quarters)
    folks += sum(q['people'] for q in quarters)
    if made:
        folks += made.get('people', 0)
    if len(stack) > n0:
        editing.fold(db, len(stack) - n0, 'Built %s, a %s: %d pieces outside, %d interiors%s' % (
            name, STYLES[style]['label'], len(wr.refs), n_in, (', %d people' % folks) if folks else ''))
    return {'name': name, 'pieces': len(wr.refs), 'cells': sorted(wr.cells), 'interiors': n_in, 'people': folks, 'furnished': placed,
            'quarters': quarters, 'buildings': sum(q['buildings'] for q in quarters),
            'sources': [[k, g] for (mi, g), k in sorted(keys.items())],
            'rooms': sorted(set(names.values())) + ([tname] if tower_key else []) + (made['names'] if made else []), 'links': len(links), 'fig': P['fig'], 'game': P['game'],
            'faults': P['faults'][:6], 'made': {k: v for k, v in made.items() if k in ('cells', 'names', 'keep', 'walls', 'unpaired')} if made else None}


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
    if P.get('quarters'):
        poly = (P.get('wards') or [poly])[-1]     # (the keep's ward alone: the quarters dress themselves)
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
    # the yard's jobs first: the smithy by the gate, stables, stores, a shrine, the drill ring, braziers in the corners
    # (storydress.fort; the user, 2026-11-03: a fort with no routine is a diorama). Then the game's own bailey sets in
    # what is left
    out, laid = [], 0
    try:
        import storydress
        wards = P.get('wards') or [poly]
        if P.get('quarters'):
            wards = wards[-1:]
        for wi, wp in enumerate(wards):
            wi += len(P.get('wards') or [poly]) - len(wards)
            # (each ward's jobs by its own gate and what it leads to: the next ward's gate, the keep's ward's keep)
            g_at = (gx, gy) if wi == 0 else _ward_gate(F, P, wi)
            k_at = (kx, ky) if wi == len(wards) - 1 else _ward_gate(F, P, wi + 1)
            roles = storydress.fort(db, [tuple(q) for q in wp], g_at, k_at, free, taken, rng, P.get('style') or 'Imperial')
            out += roles
            laid += len(roles)
    except Exception as e:
        print('castle yard roles:', e)
    # spots: along each side, a set's own distance in from the wall, facing the yard; and in the open yard
    n = len(poly)
    cx0, cy0 = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    order = list(range(len(sets)))
    rng.shuffle(order)
    tries = 0
    used = {}
    most_each = max(3, int(math.ceil(want / max(1, len(sets)))))
    while laid < want and tries < max(1500, 6 * want):
        tries += 1
        S_ = sets[order[tries % len(order)]]
        if used.get(id(S_), 0) >= most_each:
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


def _ward_gate(F, P, wi):
    """Where the cross wall into ward wi (counted from the gate's) has its gate, in the world."""
    cuts = sorted(P.get('cuts') or [])
    if not cuts or wi < 1 or wi > len(cuts):
        return (F['x'], F['y'])
    vc, u0, u1, ug = cuts[wi - 1]
    return _to_world(F, ug, vc)


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


def _walk_doors(db, wr, P, W, cand, every=False):
    """Where the wall walk runs into a keep: an arch and a door in the keep's face at the walk, as the round towers have
    theirs, leading into the room the keep's own upper door led to (the game's keep doors opened onto its fort's walk on
    other sides; the user 2026-11-03: "the wall tops have doors leading into towers and keeps"). [(module index, door
    entry with walk_out, (cell, rk, pos))]. every: a door wherever the walk runs in (a keep made anew has an interior
    behind each: the game's keeps open at every arch along their walls, the keep study of 2026-11-05)."""
    T = TOWER
    out = []
    for mi, M in enumerate(P['modules']):
        if not M.get('in_wall') or 'pose' not in M:
            continue
        # (only into the room its own upper door led to, on the walk's floor: never a door that doesn't match its
        # inside, the user 2026-11-03)
        into = list(cand.get(mi) or []) if not every else [{'id': T['door'], 'to': None, 'walk': True} for _k in range(12)]
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
    top = wz + T['over_wall'] + 256 * int(t.get('up') or 0)
    x, y, rz = t['x'], t['y'], t['rz']
    gzs = [_ground(db, x + 160 * math.cos(k * math.pi / 4), y + 160 * math.sin(k * math.pi / 4)) for k in range(8)]
    gz, gz_lo = max(gzs), min(gzs)               # (the med section goes into the dirt on the tower's high side; the
                                                 # foundations run down to its low side)
    wr.put(T['top'], (x, y, top, 0.0, 0.0, rz))
    # (pale sections from the crown down, the darker med section at the dirt (the game's: water sits at a foot), the
    # flared base and a dark section under the ground: the base stood proud as a second tower under the pale one
    # ("they do not stack vertically, the colour banding is too abrupt"), and all pale to the dirt was "inexplicably
    # light"; the user, 2026-11-06)
    z = top - 256
    while z - 128 > gz + GROUND_BURY:            # (lights down to the section at the dirt)
        wr.put(T['light'], (x, y, z, 0.0, 0.0, rz))
        z -= 256
    # (the darker section at the dirt: its foot up to 192 in the ground, or up to 64 over it on the base's lip; the
    # sections run on a 256 grid from the crown, so the foot can't always be 64 in)
    wr.put(T['med'], (x, y, z, 0.0, 0.0, rz))
    wr.put(T['base'], (x, y, z - 384, 0.0, 0.0, rz))
    bottom = z - 640
    while bottom > gz_lo - 48:
        wr.put(T['dark'], (x, y, bottom - 128, 0.0, 0.0, rz))
        bottom -= 256
    out = []
    for dx, dy in t['dirs']:
        ax, ay = x + dx * T['arch_r'], y + dy * T['arch_r']
        arz = math.atan2(dy, -dx)
        az = wz + T['over_wall'] + T['arch_dz']     # (at the walk, however high the crown)
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


def _tower_runs(P, W):
    """The castle's round towers grouped by the wall side they stand on, each run in order along it: [[tower index]].
    (A run of wall towers is one interior in the game: Firewatch's Wall Towers, Old Ebonheart's West Curtain Towers.)"""
    T = P.get('towers') or []
    if not T:
        return []
    poly = [tuple(q) for q in (W or {}).get('outline') or []]
    if len(poly) < 3:
        return [list(range(len(T)))]
    runs = defaultdict(list)
    for i, t in enumerate(T):
        k = min(range(len(poly)), key=lambda j: _seg_dist(t['x'], t['y'], poly[j], poly[(j + 1) % len(poly)]))
        a, b = poly[k], poly[(k + 1) % len(poly)]
        along = (t['x'] - a[0]) * (b[0] - a[0]) + (t['y'] - a[1]) * (b[1] - a[1])
        runs[k].append((along, i))
    return [[i for _a, i in sorted(v)] for k, v in sorted(runs.items())]


def _run_name(P, W, run, n_runs):
    """What a run of wall towers' interior is called: by its side of the castle when there are several."""
    if n_runs <= 1:
        return 'Wall Towers'
    T = P['towers']
    cx, cy = P['frame']['x'], P['frame']['y']
    mx = sum(T[i]['x'] for i in run) / len(run) - cx
    my = sum(T[i]['y'] for i in run) / len(run) - cy
    side = ('East', 'North', 'West', 'South')[int(((math.atan2(my, mx) + math.pi / 4) % (2 * math.pi)) // (math.pi / 2))]
    return '%s Wall Towers' % side


def _made_inside(db, P, W, mdoors, tdoors, name, size, seed, people, free, say):
    """The castle's interiors made anew rather than copied (ROOMS 'made'): the keep's set of linked interiors from
    keepmaker (a great hall, chambers, a garrison, a prison, towers, an undercroft, in chains and rings), its doors to the
    outside paired with the keep's own doors by height (the ground door to the lowest, the walk doors above, a roof door
    to a tower's hatch); and for each run of wall towers one interior of passages and spiral stairs with a door out at
    every arch on the walk and a hatch at each crown, as the game's big keeps have them (docs/keep-study-2026-11.md).
    {'cells', 'names', 'links': [(cell, rk, dest, pos)], 'people', 'keep', 'walls', 'unpaired'}."""
    import dwemer
    import keepmaker
    links, cells, names, unpaired = [], [], [], 0
    # ---- the keep's doors outside, lowest first; one high on the keep is its roof door
    kd = []
    for mi, dd, got in mdoors:
        if mi > 0:
            continue                         # (a hall's doors lead into its own copied rooms)
        M = P['modules'][mi]
        out = dd['walk_out'] if dd.get('walk_out') else _out_of(db, M['pose'], dd, got, M)
        if callable(out):
            out = out()
        if not out:
            continue
        kd.append((got[2][2], dd, got, [float(v) for v in out[:6]], mi))
    kd.sort(key=lambda t: t[0])
    roof = [t for t in kd if 'pose' in P['modules'][t[4]] and t[0] - P['modules'][t[4]]['pose'][2] > 400 and not t[1].get('walk')]
    keep_doors = [t for t in kd if t not in roof]
    ti = (P['modules'][0]['m'].get('tiered') or {}) if P['modules'] else {}
    if ti:
        # (a set to the mass's size: a dozen blocks and more take the large set, fewer the medium)
        size = 'large' if sum(ti['tiers'].values()) >= 10 else 'medium'
    # (the mass's footprint from its door in, for the halls to keep within: its width class's half width, and the depth
    # from the keep's front face to the wall line behind)
    box = [{3: 1400, 5: 2000, 7: 2600}.get(ti.get('n'), 1400), BLOCK * 2.5] if ti else None
    R = keepmaker.make(db, name, size, seed=seed, outs=max(1, len(keep_doors)), people=people, commit=False, progress=lambda w, f: say(w, 0.6 * f), box=box)
    if R.get('learning'):
        raise EditError('The Workshop is still learning the game\'s forts; try again in a minute.')
    cells += R['cells']
    names += [m['name'] for m in R['interiors']]
    kout = sorted([o for o in R['outs'] if o['kind'] != 'trap'], key=lambda o: o['z'])
    hatches = [o for o in R['outs'] if o['kind'] == 'trap']
    for (z, dd, got, out, mi), o in zip(keep_doors, kout):
        links.append((got[0], got[1], o['name'], o['arrive']))
        links.append((o['cell'], o['k'], '', out))
    for (z, dd, got, out, mi), o in zip(roof, hatches):
        links.append((got[0], got[1], o['name'], o['arrive']))
        links.append((o['cell'], o['k'], '', out))
    # (a keep door more than the set has ways in: into the great hall by its first door, one way; a way in more than the
    # keep has doors: out by the ground door's spot)
    spare_out = keep_doors[len(kout):] + roof[len(hatches):]
    spare_in = kout[len(keep_doors):] + hatches[len(roof):]
    for z, dd, got, out, mi in spare_out:
        if kout:
            links.append((got[0], got[1], kout[0]['name'], kout[0]['arrive']))
            unpaired += 1
    for o in spare_in:
        if keep_doors:
            links.append((o['cell'], o['k'], '', keep_doors[0][3]))
            unpaired += 1
    # ---- the wall towers: one interior a run, a door out at every arch, a hatch at each crown
    want = defaultdict(list)
    for i, kind, got, arr in tdoors:
        want[i].append((kind, got, arr))
    runs = _tower_runs(P, W)
    walls = []
    cx, cy = P['frame']['x'], P['frame']['y']
    for r_i, run in enumerate(runs):
        walks = [(i, got, arr) for i in run for kind, got, arr in want.get(i, []) if kind == 'walk']
        traps = [(i, got, arr) for i in run for kind, got, arr in want.get(i, []) if kind == 'trap']
        if not walks and not traps:
            continue
        say('Making the %s' % _run_name(P, W, run, len(runs)).lower(), 0.6 + 0.4 * r_i / max(1, len(runs)))
        nm = free('%s, %s' % (name, _run_name(P, W, run, len(runs))))
        n_doors = max(1, len(walks))
        I = {'label': nm, 'size': 'large' if n_doors > 5 else 'medium', 'levels': 'some', 'way': 'up', 'seed': zlib.crc32(('%s|%s|walls%d' % (name, seed, r_i)).encode()),
             'doors': n_doors, 'keep': {'exits': n_doors - 1, 'spirals': min(len(run), 3), 'turns': [2, 3], 'traps': True, 'big': 0.0, 'nostories': True}}
        try:
            seed_, _lay = keepmaker._layout_with_doors(db, I)
            rr = dwemer.build(db, nm, I['size'], I['levels'], 'branching', seed=seed_, kind='fort', way='up', keep=I['keep'], occupants='none', commit=True)
        except EditError as e:
            print('castle wall towers:', e)
            continue
        if rr.get('learning'):
            continue
        cells.append(rr['key'])
        names.append(nm)
        doors = rr.get('doors') or []
        ins = [d for d in doors if d['kind'] in ('front', 'exit')]
        # (the arches in their order round the castle, the doors inside in theirs across the place: neighbours stay
        # neighbours as far as they can)
        walks.sort(key=lambda w: math.atan2(w[2][1] - cy, w[2][0] - cx))
        ins.sort(key=lambda d: (d['pos'][0], d['pos'][1]))
        for (i, got, arr), d in zip(walks, ins):
            links.append((got[0], got[1], nm, d['arrive']))
            links.append((rr['key'], d['k'], '', arr))
        tr_in = [d for d in doors if d['kind'] == 'trap']
        for (i, got, arr), d in zip(traps, tr_in):
            links.append((got[0], got[1], nm, d['arrive']))
            links.append((rr['key'], d['k'], '', arr))
        # (an arch or a crown more than the place has doors: in by the first door, one way; a door more: out at the first arch)
        for i, got, arr in walks[len(ins):] + traps[len(tr_in):]:
            if ins:
                links.append((got[0], got[1], nm, ins[0]['arrive']))
                unpaired += 1
        for d in ins[len(walks):] + tr_in[len(traps):]:
            if walks:
                links.append((rr['key'], d['k'], '', walks[0][2]))
                unpaired += 1
        walls.append({'name': nm, 'key': rr['key'], 'towers': len(run), 'arches': len(walks), 'hatches': len(traps), 'doors': len(ins), 'rings': rr.get('rings', 0), 'spirals': rr.get('spirals', 0)})
    folks = R.get('people', 0)
    if people and walls:
        try:
            folks += keepmaker._people(db, [{'role': 'walls', 'key': w['key'], 'name': w['name']} for w in walls], seed)
        except Exception as e:
            print('castle wall people:', e)
    return {'cells': cells, 'names': names, 'links': links, 'people': folks, 'keep': R, 'walls': walls, 'unpaired': unpaired}


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
    # (the quarters built inside its walls: every made group standing wholly within the outline is the castle's)
    for g, rs in by.items():
        if g != gid and all(tw._inside(poly, (r['p'][0], r['p'][1])) for _ck, r in rs):
            out = out + rs
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
ROOMS = ('none', 'shells', 'furnished', 'made')
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


def furnish_shell(db, key, src_key, shift=(0.0, 0.0, 0.0), seed=1, kinds=None, level=None, like=None):
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
        out = furnish.furnish(db, key, plan, seed=seed, commit=False, level=level, like=like)
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
