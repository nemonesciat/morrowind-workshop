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


def _modules(S, style, which='keep'):
    d = STYLES[style]
    rx = re.compile(d['keep'] if which == 'keep' else d.get('more') or '$^', re.I)
    out = [m for m in S['modules'] if m['style'] == style and rx.search(m['main']) and m['doors']]
    if which == 'keep':
        # (the keep holds the halls: a module whose rooms are only a prison or a chapel stands beside it, not for it)
        out = [m for m in out if 'keep' in m['roles'] or which != 'keep']
    # (a keep whose doors all lead into rooms the castle won't have is no use: a doorless shell)
    # (and one with a door on every side, Pelagiad's thirteen, is a fort's whole yard, not a keep)
    return [m for m in out if any(not re.search(r'trap|hatch', dd['id'], re.I) for dd in m['doors']) and len(m['doors']) <= 6]


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
def plan(db, outline, style='Imperial', size='medium', seed=1, name=''):
    """The castle laid out (nothing placed): {'style', 'name', 'frame', 'outline', 'W' (the wall), 'towers', 'modules',
    'preview', 'rooms', 'fig', 'faults'}. The same outline, style, size and seed give the same castle."""
    if style not in STYLES:
        raise EditError('No such style: %s' % style)
    pts = [(float(p[0]), float(p[1])) for p in outline or ()]
    if len(pts) < 3:
        raise EditError("Draw the castle's outline first.")
    S = cs.survey(db)
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
    best = None
    for k in range(4):
        a = F['a'] + k * math.pi / 2
        G = dict(F, a=a)
        gx, gy = _to_world(G, 0, -2500)
        z = _ground(db, gx, gy)
        if best is None or z < best[0] - 32:
            best = (z, a)
    F['a'] = best[1]
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
        km = rng.choice(ok) if ok else max(fits, key=lambda t: t[1])[2]
        eu, ev = _turned_extent(km, F)
        g_side, g_back, g_front = d.get('gaps') or (SIDE_GAP, MARGIN, 1200)
        Wd = max(Wd, eu + 2 * g_side)
        Dp = max(Dp, ev + g_back + g_front)
        n_w, n_d = max(4, int(round(Wd / L))), max(4, int(round(Dp / L)))
        if n_w % 2:
            n_w += 1                     # (an even count: the gate stands in the middle of its side)
        Wd, Dp = n_w * L, n_d * L
        poly = [_to_world(F, -Wd / 2, -Dp / 2), _to_world(F, Wd / 2, -Dp / 2), _to_world(F, Wd / 2, Dp / 2), _to_world(F, -Wd / 2, Dp / 2)]
        # (the way in: out, through the front, out again, so the gate is asked for there alone)
        way = [list(_to_world(F, -16, -Dp / 2 - 1500)), list(_to_world(F, 0, -Dp / 2 + 200)), list(_to_world(F, 16, -Dp / 2 - 1500))]
        W = _lay(db, d['wall'], kit, {'plots': [], 'streets': [{'pts': way}], 'wall_outline': poly})
        faults += W.get('faults') or []
        W['pieces'] = [p for p in W['pieces'] if p.get('kind') not in ('bigtower', 'keep')]
        out['W'] = W
        out['size_wd'] = [Wd, Dp]
        # the keep at the back, its door to the gate
        out['modules'].append(_set_module(km, F, 0.0, Dp / 2 - (d.get('gaps') or (0, MARGIN))[1], back=True))
        if size == 'large' and style == 'Imperial':
            # (a second hall, a chapel or an armoury, as Frostmoth's and Umbermoth's)
            sec = [m for m in keeps if m is not km and set(m['roles']) & {'chapel', 'armoury', 'barracks'}]
            if sec:
                m = rng.choice(sorted(sec, key=lambda m: m['fort']))
                hw = max(m['box'][2] - m['box'][0], m['box'][3] - m['box'][1]) / 2.0
                out['modules'].append(_set_module(m, F, -Wd / 2 + SIDE_GAP + hw, 0.0, face=(0.0, 0.0)))
        if d.get('towers'):
            out['towers'] = _towers(W, kit, F)
    out['name'] = (name or '').strip() or castle_name(db, style, seed)
    out['preview'] = _preview(db, out)
    out['rooms'] = _rooms(db, S, out)
    out['fig'] = _figures(out)
    out['game'] = _game_figures(S, style)
    return out


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


def _set_module(m, F, u, v, back=False, face=None):
    """A module placed in the castle frame at (u, v): turned so its way in faces the gate (or face: the point in the
    castle frame it faces), its back edge at v when back."""
    front = next((dd for dd in m['doors'] if not re.search(r'trap|hatch', dd['id'], re.I) and dd['p'][2] < 200), None) or m['doors'][0]
    phi = math.atan2(front['p'][1], front['p'][0])
    tu, tv = (face if face is not None else (u, v - 1.0))
    tx, ty = _to_world(F, tu, tv)
    x, y = _to_world(F, u, v)
    target = math.atan2(ty - y, tx - x) if face is not None else F['a'] - math.pi / 2
    rz = (phi - target) % (2 * math.pi)
    if back:
        # (its far edge at v: how far the module reaches behind its origin, turned)
        P = (0.0, 0.0, 0.0, rz)
        kb = m['box']
        reach = 0.0
        for lx in (kb[0], kb[2]):
            for ly in (kb[1], kb[3]):
                wx, wy = _place(P, lx, ly)
                # (along the castle's v: the world direction F['a'] + 90°)
                reach = max(reach, wx * -math.sin(F['a']) + wy * math.cos(F['a']))
        x, y = _to_world(F, u, v - reach)
    return {'m': m, 'x': x, 'y': y, 'rz': rz}


def _towers(W, kit, F):
    """Where the round towers stand: each corner of the wall, the lengths either side of the gate, and a length every
    TOWER_EVERY along longer sides. [{'x', 'y', 'rz', 'dirs': [(dx, dy) the ways the wall runs out of it], 'kind'}]."""
    poly = W['outline']
    n = len(poly)
    out = []
    for k in range(n):
        a, b, c_ = poly[k - 1], poly[k], poly[(k + 1) % n]
        din = tw._unit(a[0] - b[0], a[1] - b[1])
        dout = tw._unit(c_[0] - b[0], c_[1] - b[1])
        out.append({'x': b[0], 'y': b[1], 'rz': tw._rz_for(kit, (-din[0], -din[1])), 'dirs': [din, dout], 'kind': 'corner', 'run': k})
    gates = [p for p in W['pieces'] if p.get('kind') in ('gate', 'end')]
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        d = tw._unit(b[0] - a[0], b[1] - a[1])
        side = sorted([p for p in W['pieces'] if p.get('run') == k and p.get('kind') == 'wall'],
                      key=lambda p: (p['pose'].x - a[0]) * d[0] + (p['pose'].y - a[1]) * d[1])
        picks = []
        g = [q for q in gates if q.get('run') == k]
        if g:
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


def make(db, outline, style='Imperial', size='medium', seed=1, name='', people=True, rooms='furnished'):
    """The castle built (plan() laid out), its rooms as ROOMS says. One Undo."""
    PROGRESS.update(on=True, what='Planning', frac=0.0)
    try:
        return _make(db, outline, style, size, seed, name, people, rooms if rooms in ROOMS else 'furnished')
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


def _make(db, outline, style, size, seed, name, people, rooms='furnished'):
    import editing
    import create
    import doors
    editing._require_project(db)
    P = plan(db, outline, style, size, seed, name)
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
    skip = set()
    if W is not None:
        try:
            tw.level_ground(db, W, skip)
        except Exception as e:
            print('castle wall ground:', e)
    pads = []
    for M in P['modules']:
        kb = M['m']['box']
        Pz = (M['x'], M['y'], 0.0, M['rz'])
        corners = [_place(Pz, lx, ly) for lx, ly in ((kb[0], kb[1]), (kb[2], kb[1]), (kb[2], kb[3]), (kb[0], kb[3]))]
        zs_ = sorted(_ground(db, *_place(Pz, (kb[0] + kb[2]) * f / 2, (kb[1] + kb[3]) * g / 2)) for f in (0, 1, 2) for g in (0, 1, 2))
        M['ground'] = zs_[len(zs_) // 2] if style != 'Stronghold' else zs_[len(zs_) // 3]
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
        W = tw.grounded(db, W)
        for p in W['pieces']:
            q = p['pose']
            wr.put(p['id'], (q.x, q.y, q.z, 0.0, 0.0, q.rz))
    tdoors = []                                  # [(tower index, kind, (cell, rk, pos), arrive outside)]
    if P['towers'] and W is not None:
        _say('Raising the towers', 0.3)
        lv = [(p['pose'].x, p['pose'].y, p['pose'].z) for p in W['pieces'] if p.get('kind') in ('wall', 'corner')]
        for i, t in enumerate(P['towers']):
            near = sorted(lv, key=lambda q: math.hypot(q[0] - t['x'], q[1] - t['y']))[:2]
            wz = max(q[2] for q in near) if near else _ground(db, t['x'], t['y']) - 200
            tdoors += _tower(db, wr, t, wz, i)
    mdoors = []                                  # [(module index, door entry, (cell, rk, pos))]
    _say('Raising the keep', 0.4)
    for mi, M in enumerate(P['modules']):
        m = M['m']
        Z = M['ground'] + m['over']
        Pz = (M['x'], M['y'], Z, M['rz'])
        M['pose'] = Pz
        for pc in m['pieces']:
            x, y = _place(Pz, pc[1], pc[2])
            wr.put(pc[0], (x, y, Z + pc[3], pc[5], pc[6], M['rz'] + pc[4]), pc[7])
        for dd in m['doors']:
            x, y = _place(Pz, dd['p'][0], dd['p'][1])
            got = wr.put(dd['id'], (x, y, Z + dd['p'][2], 0.0, 0.0, M['rz'] + dd['p'][3]), dd.get('s') or 1.0)
            if got:
                mdoors.append((mi, dd, got))
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
                        links.append(here + ('', _out_of(db, M['pose'], dd, ext)))
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
            links.append((ck, rk, '', _out_of(db, P['modules'][mi]['pose'], dd, got)))
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


def _out_of(db, Pz, dd, got):
    """Where an inside door out of a keep sets you down: where the game's did, in front of its door, carried to ours."""
    o = dd.get('out')
    if o:
        x, y = _place(Pz, o[0], o[1])
        z = Pz[2] + o[2]
        g = mapdata.terrain_z(db, x, y)
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


def wall_keeps(db, refs, outline, town, taken, rng, rooms='furnished'):
    """Ways into a town wall's keep and big towers, each with a stair room behind them (see WALL_KEEP). refs: the wall's
    placed pieces [(cell key, ref key, id, pose)], changed: the pieces given rooms are taken out (so
    towninside.wall_rooms doesn't give them another); outline: the wall's. The rooms' names."""
    import editing
    lib = [r for r in cs.survey(db)['tower_rooms'] if r['style'] == 'Imperial']
    if not lib:
        return []
    poly = [tuple(p) for p in outline]
    cx, cy = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
    lv = [(w[3][0], w[3][1], w[3][2]) for w in refs if re.search(r'_wall_0|_wall_corner', w[2], re.I)]
    cand = [w for w in refs if w[2].lower() in WALL_KEEP]
    cand.sort(key=lambda w: (0 if 'keep' in w[2].lower() else 1, rng.random()))
    nd_ = lambda r: sum(1 for d in r['doors'] if not d['trap'])
    cost = lambda r, need: nd_(r) - need + (1 if any(d['trap'] for d in r['doors']) else 0)
    wr = _Writer(db)
    names, links, done, src = [], [], set(), {}
    for ck, rk, wid, pose in cand:
        if len(names) >= WALL_KEEPS:
            break
        what, half = WALL_KEEP[wid.lower()]
        x, y = pose[0], pose[1]
        runs = _runs_at(poly, x, y)
        near = sorted(lv, key=lambda q: math.hypot(q[0] - x, q[1] - y))[:2]
        if not near:
            continue
        wz = max(q[2] for q in near)
        # the spot for the ground door: on one of the piece's four faces, in its middle or to one side of it, where the
        # ground in front of it lies furthest into the town and clear of the wall (a keep at a corner looks into the
        # town only past the ends of the lengths running into it)
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
                spots.append((clear - abs(off) * 0.1, n, off))
        if not spots:
            continue
        _c, n, off = max(spots)
        t_ = (n[1], -n[0])
        # a stair room with a door for the ground and one for each way along the walk
        need = 1 + len(runs)
        fit = [r for r in lib if nd_(r) >= need]
        if not fit:
            continue
        lo = min(cost(r, need) for r in fit)
        R = rng.choice(sorted([r for r in fit if cost(r, need) == lo], key=lambda r: (r['key'], r['box'])))
        # the ground door, its sill on the ground in front of it
        gx, gy = x + n[0] * (half + 120) + t_[0] * off, y + n[1] * (half + 120) + t_[1] * off
        gz = _ground(db, gx, gy)
        ri = db.resolve_id(GROUND['door'])
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        drz = math.atan2(-n[0], -n[1]) % (2 * math.pi)          # (its face, local +y, into the piece)
        dx, dy = x + n[0] * (half - 12) + t_[0] * off, y + n[1] * (half - 12) + t_[1] * off
        dzz = gz + 6 - b[2]
        if gz > wz + WALK_OVER:
            continue                                            # (the ground there stands over the wall walk itself)
        wr.put(GROUND['frame'], (dx + n[0] * GROUND['in'], dy + n[1] * GROUND['in'], dzz, 0.0, 0.0, drz))
        gd = wr.put(GROUND['door'], (dx, dy, dzz, 0.0, 0.0, drz))
        outs = [(gd, [gx + n[0] * 60, gy + n[1] * 60, gz + 8, 0.0, 0.0, _facing(*n)])]
        # the walk doors: an arch on the face where each length runs in
        T = TOWER
        for d in runs:
            ax, ay = x + d[0] * (half - 3), y + d[1] * (half - 3)
            arz = math.atan2(d[1], -d[0])
            az = wz + WALK_OVER + T['arch_dz']
            wr.put(T['arch'], (ax, ay, az, 0.0, 0.0, arz))
            c, s = math.cos(arz), math.sin(arz)
            lx, ly, lz = T['door_in']
            px, py = ax + lx * c + ly * s, ay - lx * s + ly * c
            got = wr.put(T['door'], (px, py, az + lz, 0.0, 0.0, arz + math.pi / 2))
            outs.append((got, [px + d[0] * 110, py + d[1] * 110, az + lz - 88, 0.0, 0.0, _facing(*d)]))
        if any(g is None for g, _o in outs):
            continue
        name = _free_name(db, '%s, %s' % (town, what), taken)
        key, cell = _new_place(db, name, R['key'])
        if R['key'] not in src:
            src[R['key']] = db.cell_refs(R['key'])[0]
        copied = _copy_room(db, cell, R, 0.0, 0.0, src[R['key']])
        inner = sorted([d for d in R['doors'] if not d['trap'] and d['k'] in copied], key=lambda d: d['dz'])
        # (the lowest door to the ground, the highest ones to the walk: the stair between them)
        pairs = [(outs[0], inner[0])] + list(zip(outs[1:], inner[::-1][:len(outs) - 1]))
        used = {d['k'] for _o, d in pairs}
        for (got, arr), dd in pairs:
            links.append((got[0], got[1], name, ('in', key, copied[dd['k']])))
            links.append((key, copied[dd['k']], '', arr))
        # (a door more, or a trap door: out by the ground door, never leading nowhere)
        for dd in R['doors']:
            if dd['k'] not in used and dd['k'] in copied:
                links.append((key, copied[dd['k']], '', outs[0][1]))
        names.append(name)
        done.add(rk)
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


def furnish_shell(db, key, src_key, shift=(0.0, 0.0, 0.0), seed=1):
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
        plan.append({'id': rm['id'], 'purpose': kind or rm.get('purpose')})
    if not plan:
        return 0
    try:
        out = furnish.furnish(db, key, plan, seed=seed, commit=False)
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
