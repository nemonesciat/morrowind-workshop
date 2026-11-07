"""Building a planned town (townplan.py): the culture's own buildings on its plots, then (later stages) the ground under
them, the streets' road, and the dressing.

The buildings are the game's own, whole, from the exterior survey (exteriorsurvey modules: every building outside a
game interior's door, its pieces in its door's frame, door at the origin, +y inward, the ground in front of the door
at fground). Each is catalogued with its culture (townsurvey.town_style of its main piece), its kind (from the
interiors it serves) and its footprint (its pieces' boxes, turned, in its door's frame). A plot takes a building of the
town's culture and the plot's kind about its size, set down with its middle on the plot's and its door facing the
plot's way."""
import json
import os
import math
import random
import re
from collections import Counter, defaultdict

import mapdata
import strays
import townsurvey

_cat = {}
WALLISH = re.compile(r'wall|gate|rampart|parapet|battlement|palisade|fence', re.I)
MAX_ACROSS = 3200               # a building wider or deeper than this is a compound or a town wall, not a plot's
NEAR_CULTURES = {'Common': ('Imperial', 'Nordic'), 'Imperial': ('Common',), 'Nordic': ('Common',), 'Dunmer': ('Velothi', 'Redoran'),
                 'Velothi': ('Dunmer', 'Indoril'), 'Indoril': ('Velothi', 'Dunmer'), 'Redoran': ('Dunmer', 'Velothi'),
                 'Mournhold': ('Indoril', 'Velothi'), 'Reach': ('Nordic', 'Common'), 'Hlaalu': ('Dunmer',), 'Telvanni': ('Dunmer',),
                 'Ashlander': (), 'Stronghold': ('Velothi',),
                 # (only when a look has fewer than 12 buildings of its own: Anvil's and the Gold Coast's never mix otherwise)
                 'Anvil': ('Gold Coast',), 'Gold Coast': ('Anvil',)}


def family(key):
    """A building's family by its main piece's name: ex_imp, ex_common, t_imp_setgc, t_de_setnecrom ..."""
    p = re.sub(r'[_ ]?\d+[a-z]?$', '', key.lower()).split('_')
    return '_'.join(p[:3] if p[0] == 't' else p[:2]) if len(p) > 1 else p[0]


_co = {}
_mix = {}


def family_mix(db):
    """{lead family: {'towns': game towns it leads, 'cultures': {culture: n}, 'mix': {family: share of their buildings}}}:
    in the game's towns where a family has the most buildings, what share of all their buildings each family has
    (Pelagiad-like ex_imp towns: their houses ex_common and ex_nord, their fort ex_imp)."""
    k = id(db.recs)
    if k not in _mix:
        out = {}
        for t in townsurvey.survey(db)['towns']:
            fs = {}
            for b in t['buildings']:
                if b.get('main'):
                    f = family(b['main'])
                    fs[f] = fs.get(f, 0) + 1
            if not fs:
                continue
            lead = max(fs, key=fs.get)
            o = out.setdefault(lead, {'towns': 0, 'cultures': {}, 'n': {}})
            o['towns'] += 1
            o['cultures'][t['culture']] = o['cultures'].get(t['culture'], 0) + 1
            for f, n in fs.items():
                o['n'][f] = o['n'].get(f, 0) + n
        for o in out.values():
            tot = float(sum(o['n'].values()) or 1)
            o['mix'] = {f: n / tot for f, n in o.pop('n').items()}
        _mix[k] = out
    return _mix[k]


def families_together(db):
    """{family: {family: game towns with both}}: which families the game's own towns mix."""
    k = id(db.recs)
    if k not in _co:
        co = {}
        for t in townsurvey.survey(db)['towns']:
            fs = {family(b['main']) for b in t['buildings'] if b.get('main')}
            for a in fs:
                for b in fs:
                    co.setdefault(a, {})
                    co[a][b] = co[a].get(b, 0) + 1
        _co[k] = co
    return _co[k]


YARD_NEAR = 64                 # a yard's wall or fence this near the building itself is its own, and stays


def _pbox(db, p, memo):
    """A module piece's box in the module's frame: [x0, y0, x1, y1], or None."""
    low = p['id'].lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
    b = memo[low]
    if not b:
        return None
    s = p.get('s') or 1.0
    c, sn = math.cos(p['rz']), math.sin(p['rz'])
    xs, ys = [], []
    for bx in (b[0] * s, b[3] * s):
        for by in (b[1] * s, b[4] * s):
            xs.append(p['x'] + bx * c + by * sn)
            ys.append(p['y'] - bx * sn + by * c)
    return [min(xs), min(ys), max(xs), max(ys)]


TIPPED = re.compile(r'plat|plank|(?<!cup)board')
TIPPED_UP = 250                # (only those standing on the ground: higher up, planks on edge are shutters and trim)


def _trim_yard(db, m, memo):
    """The module without the walls, palisades, fences and platforms standing clear of the building itself, and what
    stands on them: in the game they join the neighbours' into a street wall or a harbour stage, and set down alone
    they stood loose about the town, a Nordic log house's seven palisade lengths in front of it and an Anvil house's
    platform stage, bollards and planks on the square (the unwalled practice, 2026-11-01). A wall a town wall's height
    goes even against the house: Solstheim's palisade posts, 1,100 tall, hid the log houses they stood against. A piece
    a door stands on
    stays, and a house's own walls (the Reach's houses are built of HouseWall lengths) and a keep's."""
    if KEEP.search(m['main']):
        return m
    main = next((p for p in m['fpieces'] if p['id'].lower() == m['main'].lower()), None)
    mb = main and _pbox(db, main, memo)
    if not mb:
        return m
    mb = [mb[0] - YARD_NEAR, mb[1] - YARD_NEAR, mb[2] + YARD_NEAR, mb[3] + YARD_NEAR]
    doors = [(p['x'], p['y']) for p in m['fpieces'] if p.get('door')]
    apart = lambda a, b: a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]
    holds = lambda a: any(a[0] - 32 <= x <= a[2] + 32 and a[1] - 32 <= y <= a[3] + 32 for x, y in doors)
    drop, boxes = set(), []
    for k, p in enumerate(m['fpieces']):
        low = p['id'].lower()
        # (a plank or platform tipped up on edge on the ground: Firewatch leans half-size ones against its houses, and set down alone
        # one read as a board stuck to a wall, the user's town twice, 2026-11-01)
        if p is not main and not p.get('door') and TIPPED.search(low) and p['z'] < TIPPED_UP and max(abs(math.sin(p.get('rx') or 0.0)), abs(math.sin(p.get('ry') or 0.0))) > 0.7:
            drop.add(k)
            continue
        if p is main or p.get('door') or 'door' in low or 'housewall' in low or not (WALLISH.search(low) or 'platform' in low):
            continue
        b = _pbox(db, p, memo)
        tall = WALLISH.search(low) and 'gateway' not in low and _height(db, low, memo) >= FORT_HEIGHT
        if b and (apart(b, mb) or tall) and not holds(b):
            drop.add(k)
            boxes.append(b)
    if drop:
        for k, p in enumerate(m['fpieces']):
            if k not in drop and p is not main and not p.get('door') and 'door' not in p['id'].lower():
                b = _pbox(db, p, memo)
                if b and apart(b, mb) and not holds(b) and any(o[0] <= (b[0] + b[2]) / 2 <= o[2] and o[1] <= (b[1] + b[3]) / 2 <= o[3] for o in boxes):
                    drop.add(k)
    # (and a yard wall left with an open end, its run cut where the rest stood clear of the house: dropped, and so on
    # down the run, until every yard wall left runs into the house, a post or another wall. A dry-stone run stopped
    # open and three pieces stood alone between houses, the user's Tessellated Shores, 2026-11-01; 25 open ends in 8
    # walled towns, lab sw1)
    while True:
        kept = [(k, p) for k, p in enumerate(m['fpieces']) if k not in drop]
        opens = [o for _j, o in kept if OPENING.search(o['id'])]
        more = [k for k, p in kept if _yard_wall(db, p, memo) and not holds(_pbox(db, p, memo) or [0, 0, -1, -1])
                and not any(_end_met(db, (o['x'], o['y'], o['z']), [p], memo, 100) for o in opens)
                and any(not _end_met(db, e, [o for j, o in kept if j != k], memo) for e in _ends_of(db, p, memo))]
        if not more:
            break
        drop |= set(more)
    if not drop:
        return m
    return dict(m, fpieces=[p for k, p in enumerate(m['fpieces']) if k not in drop])


def _yard_wall(db, p, memo):
    """A yard's wall or fence length (not a house's own wall, a gateway or a door)."""
    low = p['id'].lower()
    return bool(WALLISH.search(low)) and not re.search(r'door|housewall|gateway|gate|post|end|tower|corner', low) and not p.get('door') \
        and _height(db, low, memo) < FORT_HEIGHT


def _local_box(db, p, memo):
    low = p['id'].lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
    return memo[low]


def _ends_of(db, p, memo):
    """A wall length's two ends, a little past them, in the module's frame: [(x, y, z)]. None for a piece no longer
    than wide."""
    b = _local_box(db, p, memo)
    if not b:
        return []
    s = p.get('s') or 1.0
    c, sn = math.cos(p['rz']), math.sin(p['rz'])
    if b[3] - b[0] >= b[4] - b[1]:
        if b[3] - b[0] < 1.5 * (b[4] - b[1]):
            return []
        loc = [(b[0] - 16 / s, (b[1] + b[4]) / 2), (b[3] + 16 / s, (b[1] + b[4]) / 2)]
    else:
        if b[4] - b[1] < 1.5 * (b[3] - b[0]):
            return []
        loc = [((b[0] + b[3]) / 2, b[1] - 16 / s), ((b[0] + b[3]) / 2, b[4] + 16 / s)]
    zm = p['z'] + (b[2] + b[5]) / 2 * s
    return [(p['x'] + lx * s * c + ly * s * sn, p['y'] - lx * s * sn + ly * s * c, zm) for lx, ly in loc]


def _end_met(db, e, others, memo, pad=20):
    """Does something of the module stand at this end point (inside its box, a little grown)?"""
    for o in others:
        b = _local_box(db, o, memo)
        if not b:
            continue
        s = o.get('s') or 1.0
        c, sn = math.cos(o['rz']), math.sin(o['rz'])
        dx, dy = e[0] - o['x'], e[1] - o['y']
        lx, ly = (dx * c - dy * sn) / s, (dx * sn + dy * c) / s
        if b[0] - pad <= lx <= b[3] + pad and b[1] - pad <= ly <= b[4] + pad and o['z'] + b[2] * s - 40 - pad <= e[2] <= o['z'] + b[5] * s + 40 + pad:
            return True
    return False


APART = 128                    # a module's piece this far clear of every other piece of it is a neighbour's, not its own


def _drop_apart(db, m, memo):
    """The module without pieces standing clear of the rest of its building: a log house brought the chimney and the
    wheelbarrow of the game house next to it, set 760-915 off on the snow (the user's Nordic village, 2026-11-01).
    Doors stay (a door is its building's)."""
    boxes = [(p, _pbox(db, p, memo)) for p in m['fpieces']]
    gap = lambda a, b: math.hypot(max(0.0, a[0] - b[2], b[0] - a[2]), max(0.0, a[1] - b[3], b[1] - a[3]))
    keep = [p for p, b in boxes if p.get('door') or b is None or len(boxes) < 3
            or any(o is not p and ob is not None and gap(b, ob) <= APART for o, ob in boxes)]
    return m if len(keep) == len(m['fpieces']) else dict(m, fpieces=keep)


PORCH = re.compile(r'entrance|porch|stoop', re.I)
WINDOWISH = re.compile(r'_win|window|chimney', re.I)
PORCH_DOOR = 72                # (a porch holds a door: the door's spot within this of the porch's box)
OFF_SHELL = 96                 # (a window or a chimney this far outside every shell of the building is nobody's)


def _explained(db, m, memo):
    """The module with only the pieces the building explains: a porch or an entrance holds one of the building's own
    doors; a window or a chimney sits on one of its shells (the pieces that are neither trim, doors, porches nor
    windows). The reader took a building as every piece whose box touched the door's piece outward, so a neighbour's
    porch pressed against the wall in the game example came with every copy: an entrance standing alone by a well,
    440 from the hostel it came with, the user's Skethwall; 32 of the catalogue's 2,096 modules carried one
    (2026-11-07)."""
    fp = m['fpieces']
    doors = [p for p in fp if p.get('door') or _rec_type(db, p['id']) == 'DOOR']
    shells = [_pbox(db, p, memo) for p in fp if not p.get('trim') and not p.get('door') and not PORCH.search(p['id'])
              and not WINDOWISH.search(p['id']) and _rec_type(db, p['id']) == 'STAT']
    shells = [b for b in shells if b is not None]
    if not shells:
        return m

    def near(x, y, b, pad):
        return b[0] - pad <= x <= b[2] + pad and b[1] - pad <= y <= b[3] + pad
    keep = []
    for p in fp:
        if p.get('door'):
            keep.append(p)
            continue
        if PORCH.search(p['id']):
            b = _pbox(db, p, memo)
            if b is not None and not any(near(d['x'], d['y'], b, PORCH_DOOR) for d in doors):
                continue
        elif WINDOWISH.search(p['id']):
            if not any(near(p['x'], p['y'], b, OFF_SHELL) for b in shells):
                continue
        keep.append(p)
    return m if len(keep) == len(fp) else dict(m, fpieces=keep)


def _rec_type(db, rid):
    ri = db.resolve_id(rid)
    return db.recs[ri][0] if ri is not None else None


REPEAT_NEAR = 8                # (one model this near itself, the same way up, is the same piece twice)


def _no_repeats(m):
    """The module without a piece set twice in one spot: the game has a few (an ex_common_window_03 twice on one wall),
    and a town built them twice, the town audit of 2026-11-01."""
    out = []
    for p in m['fpieces']:
        if any(o['id'].lower() == p['id'].lower() and abs(o['x'] - p['x']) <= REPEAT_NEAR and abs(o['y'] - p['y']) <= REPEAT_NEAR
               and abs(o['z'] - p['z']) <= REPEAT_NEAR and o.get('door') == p.get('door') for o in out):
            continue
        out.append(p)
    return m if len(out) == len(m['fpieces']) else dict(m, fpieces=out)


SHELL_AREA = 250000            # (a piece this big across and SHELL_HEIGHT tall is a building's own shell)
SHELL_HEIGHT = 400
SHELL_GAP = 48                 # (two shells this close, every way, are one building's)


def _two_buildings(db, m, memo):
    """Does the module hold another building with a door of its own? Learnt from the game's rows, a Common guard house
    kept the tavern 810 along from it, door and all, and set down whole it stood over its neighbours, a house's door
    opening inside the tavern four times in a town (the user's audit, 2026-11-01; PIN2's "multiple building pieces in
    one"). True when a building shell stands apart from the front door's, joined to it by no chain of touching shells."""
    boxes = []
    for p in m['fpieces']:
        low = p['id'].lower()
        if low not in memo:
            ri = db.resolve_id(p['id'])
            memo[low] = mapdata.object_bounds(db, ri) if ri is not None else None
        b = memo[low]
        if not b:
            boxes.append(None)
            continue
        sc, c, sn = p.get('s') or 1.0, math.cos(p.get('rz') or 0.0), math.sin(p.get('rz') or 0.0)
        xs = [p['x'] + (bx * c + by * sn) * sc for bx in (b[0], b[3]) for by in (b[1], b[4])]
        ys = [p['y'] + (-bx * sn + by * c) * sc for bx in (b[0], b[3]) for by in (b[1], b[4])]
        boxes.append((min(xs), min(ys), p['z'] + b[2] * sc, max(xs), max(ys), p['z'] + b[5] * sc))
    shells = [k for k, (p, b) in enumerate(zip(m['fpieces'], boxes)) if b and (b[3] - b[0]) * (b[4] - b[1]) >= SHELL_AREA
              and b[5] - b[2] >= SHELL_HEIGHT and not OPENING.search(p['id']) and not WALLISH.search(p['id'].lower())]
    if len(shells) < 2:
        return False
    gap = lambda a, b: max(0.0, max(a[0], b[0]) - min(a[3], b[3]), max(a[1], b[1]) - min(a[4], b[4]), max(a[2], b[2]) - min(a[5], b[5]))
    pt = lambda b, x, y: math.hypot(max(b[0] - x, 0.0, x - b[3]), max(b[1] - y, 0.0, y - b[4]))
    near = lambda x, y: min(shells, key=lambda k: pt(boxes[k], x, y))
    # (the front door's shell and the shells joined to it, touching one another; any other is another building's,
    # with its own door or without: a tavern with no door standing over the next house is as much a phantom)
    front = near(0.0, 0.0)
    joined, todo = {front}, [front]
    while todo:
        k = todo.pop()
        for j in shells:
            if j not in joined and gap(boxes[k], boxes[j]) <= SHELL_GAP:
                joined.add(j)
                todo.append(j)
    return len(joined) < len(shells)


SUPPORTS = re.compile(r'stair|steps|ramp|stem|stalk')
STAIRS = re.compile(r'stair|steps|ramp')
_over_ground = {}


def _game_over_ground(db, low):
    """How high the game stands a model's origin over its ground outdoors (median of its placements), or None."""
    if low in _over_ground and _over_ground[low][0] is db.recs:
        return _over_ground[low][1]
    from project import ref_info
    v = []
    for ci in list(db.used_in.get(low, ()))[:40]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not r[7].startswith('#') or r[3] == db.proj_pidx:
            continue
        refs, _h = db.cell_refs(r[7])
        for ref in refs.values():
            rid, pos, _s, dead = ref_info(ref['subs'])
            if dead or rid.lower() != low:
                continue
            g = mapdata.terrain_z(db, pos[0], pos[1])
            if g is not None:
                v.append(pos[2] - g)
    v.sort()
    out = v[len(v) // 2] if len(v) >= 5 else None
    _over_ground[low] = (db.recs, out)
    return out


DOOR_TO_WALL = 220             # (a building's other door this near the town wall, looking at it, keeps the building unbuilt)


def _door_to_wall(db, m, q, dx, dy, c, sn, wall_boxes, rmemo):
    """Whether one of the building's doors other than its front would open against the town wall: the way out of it,
    from the building's middle through the door, meets a wall piece within DOOR_TO_WALL."""
    import townplan
    rect = q.get('rect')
    if not rect:
        return False
    mx, my = sum(p_[0] for p_ in rect) / len(rect), sum(p_[1] for p_ in rect) / len(rect)
    front = min((p_ for p_ in m['fpieces'] if p_.get('door')), key=lambda p_: p_['x'] ** 2 + p_['y'] ** 2 + (p_['z'] * 3) ** 2, default=None)
    for p_ in m['fpieces']:
        if p_ is front or not (p_.get('door') or re.search(r'door', p_['id'], re.I)) or re.search(r'trap|hatch|marker|frame', p_['id'], re.I):
            continue
        low = p_['id'].lower()
        if low not in rmemo:
            rmemo[low] = db.resolve_id(p_['id'])
        ri = rmemo[low]
        if ri is None or db.recs[ri][0] != 'DOOR':
            continue
        wx, wy = _world(dx, dy, c, sn, p_['x'], p_['y'])
        ux, uy = wx - mx, wy - my
        h = math.hypot(ux, uy)
        if h < 1:
            continue
        px, py = wx + ux / h * DOOR_TO_WALL, wy + uy / h * DOOR_TO_WALL
        probe = [(px - 24, py - 24), (px + 24, py - 24), (px + 24, py + 24), (px - 24, py + 24)]
        if any(townplan._overlap(probe, w_) for w_ in wall_boxes):
            return True
    return False


# the roots a Telvanni pod hangs lanterns from dangle in the air under it (ex_t_root_hook: 448 of 452 of the game's with
# their foot off the ground, median 803 up; lab r04); set where the pod stands lower than the game's, their feet went into
# the ground, lanterns and all (the user, 2026-11-02)
HUNG = re.compile(r'root_hook|^ex_t_hook$', re.I)
HUNG_CLEAR = 40                # (a hanging piece's foot at least this far over the ground, or it is left out)


def _hung_into_ground(db, m, dx, dy, c, sn, z0, rmemo):
    """{id(piece)}: the module's hanging pieces that would reach the ground here, and the lights they hold."""
    out, held = set(), []
    for p_ in m['fpieces']:
        if not HUNG.search(p_['id']):
            continue
        low = p_['id'].lower()
        if low not in rmemo:
            rmemo[low] = db.resolve_id(p_['id'])
        ri = rmemo[low]
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        wx, wy = _world(dx, dy, c, sn, p_['x'], p_['y'])
        g = mapdata.terrain_z(db, wx, wy)
        s = p_.get('s') or 1.0
        foot = z0 + p_['z'] + b[2] * s
        if g is not None and foot < g + HUNG_CLEAR:
            out.add(id(p_))
            held.append((p_['x'], p_['y'], p_['z'] + b[2] * s - 64, p_['z'] + b[5] * s + 64, max(b[3] - b[0], b[4] - b[1]) * s / 2 + 48))
    if held:
        for p_ in m['fpieces']:
            if id(p_) in out or not re.search(r'^light_|lantern', p_['id'], re.I):
                continue
            if any(math.hypot(p_['x'] - x, p_['y'] - y) <= r and z_lo <= p_['z'] <= z_hi for x, y, z_lo, z_hi, r in held):
                out.add(id(p_))
    return out


def _fground(db, m, rmemo):
    """The ground under a building's door, from its door (frame z 0). The survey keeps the game's own only for a door
    up to 400 over its ground, else -40; a Telvanni pod's door is up its stalk or spiral stair, so every pod house
    stood 200-600 too low, stalks and stairs in the ground (the user's Uvidrith, 2026-11-02). There its stalks and
    stairs stand as high over the ground as the game stands them (ex_t_housestem_01: 315, ex_t_stair_spiral: -2)."""
    g = m.get('fground')
    # (a building with stairs up to its door stands its stairs on the ground, the way up from the street, whatever the
    # survey made of its door: the user, "the stairs are supposed to carry the player off the ground level")
    stairs = [p_ for p_ in m['fpieces'] if STAIRS.search(p_['id'].lower())]
    if g is not None and g != -40.0 and not stairs:
        return g
    want = []
    for p_ in stairs or m['fpieces']:
        low = p_['id'].lower()
        if SUPPORTS.search(low):
            o = _game_over_ground(db, low)
            if o is not None:
                want.append(p_['z'] - o)
    if want:
        want.sort()
        f = want[len(want) // 2]
        if g is not None and g != -40.0:
            # (raised only, and only where its stairs would stand well in the ground: never lowered, as stairs to an
            # upper floor or a roof would have it; lab 2026-11-02, Hlaalu and Redoran huts went 200-700 down)
            return f if f < g - 150 else g
        if f < -120:                        # (only a door well up its supports: the others stand as they did)
            return f
    return g if g is not None else -40.0


def _footprint(db, m, memo):
    """The module's footprint in its door's frame: [x0, y0, x1, y1] (+y inward, the door at the origin)."""
    xs, ys = [], []
    for p in m['fpieces']:
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if not b:
            continue
        s = p.get('s') or 1.0
        c, sn = math.cos(p['rz']), math.sin(p['rz'])
        for bx in (b[0] * s, b[3] * s):
            for by in (b[1] * s, b[4] * s):
                # (turned clockwise, as the game turns: groups.place)
                xs.append(p['x'] + bx * c + by * sn)
                ys.append(p['y'] - bx * sn + by * c)
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


OWN = '\u2605'                  # (a style of your own as a town's culture: '★name')


def _prefab_module(db, pf, memo):
    """A prefab of yours as a building module: its pieces in the frame of its outer door (the door farthest from its
    middle) at the origin, the building inward (+y), as the survey's modules are; None without a door."""
    its = [it for it in pf.get('items') or () if db.resolve_id(it.get('id') or '') is not None]
    tag = lambda it: it.get('type') or db.recs[db.resolve_id(it['id'])][0]
    doors = [it for it in its if tag(it) == 'DOOR']
    if not doors or len(its) < 2:
        return None
    cx = sum(float(it.get('dx', 0)) for it in its) / len(its)
    cy = sum(float(it.get('dy', 0)) for it in its) / len(its)
    door = max(doors, key=lambda it: math.hypot(float(it.get('dx', 0)) - cx, float(it.get('dy', 0)) - cy))
    ux, uy = cx - float(door.get('dx', 0)), cy - float(door.get('dy', 0))
    if math.hypot(ux, uy) < 1:
        return None
    # (inward square to the door, out of the wall it stands in, as the game's modules are framed; towards the
    # prefab's middle, the frame came out turned, a game house saved as a prefab 1,119 by 1,462 against its own
    # 1,223 by 1,045, lab jown)
    db_ = mapdata.object_bounds(db, db.resolve_id(door['id']))
    if db_:
        import doorfronts
        tx, ty = doorfronts.thin_axis({'b': db_, 'p': [0, 0, 0, 0, 0, float(door.get('rz', 0))]})
        ux, uy = (tx, ty) if tx * ux + ty * uy >= 0 else (-tx, -ty)
    L = math.hypot(ux, uy)
    sn, c = ux / L, uy / L
    th = math.atan2(ux, uy)
    out = []
    for it in its:
        px, py = float(it.get('dx', 0)) - float(door.get('dx', 0)), float(it.get('dy', 0)) - float(door.get('dy', 0))
        out.append({'id': it['id'], 'x': px * c - py * sn, 'y': px * sn + py * c, 'z': float(it.get('dz', 0)) - float(door.get('dz', 0)),
                    'rx': float(it.get('rx', 0)), 'ry': float(it.get('ry', 0)), 'rz': (float(it.get('rz', 0)) - th) % (2 * math.pi),
                    's': float(it.get('s', 1.0) or 1.0), 'door': tag(it) == 'DOOR'})
    low = door['id'].lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(door['id']))
    b = memo[low]
    main = max(out, key=lambda p: 0 if p['door'] else 1)['id']
    return {'main': main, 'fpieces': out, 'uses': 1, 'examples': [],
            'fground': (b[2] * float(door.get('s', 1.0) or 1.0)) if b else 0.0}


_own_cat = {}


def own_catalog(db, game=None):
    """Your prefabs as buildings of your own styles (stylesurvey.own_styles): [catalog entries], culture '★name', each
    kind as you set it; behind its door, the interior of a game building of that kind (its look's 'like' culture's)."""
    import groups
    import stylesurvey
    st = stylesurvey.own_styles()
    pfs = {p['name']: p for p in groups.prefabs()}
    sig = (id(db.recs), json.dumps(st, sort_keys=True), tuple(sorted((n, p.get('saved')) for n, p in pfs.items())))
    if _own_cat.get('sig') == sig:
        return _own_cat['out']
    memo, out = {}, []
    for name, o in st.items():
        like = o.get('like') or ''
        for pn, kind in (o.get('prefabs') or {}).items():
            pf = pfs.get(pn)
            m = _prefab_module(db, pf, memo) if pf else None
            fp = _footprint(db, m, memo) if m else None
            if not fp:
                continue
            w, d = fp[2] - fp[0], fp[3] - fp[1]
            # (an interior to copy: a game building's of the kind and about the size, of the look it is like)
            gl = [c for c in game or () if c['m'].get('examples') and (not like or c['culture'] == like)]
            pick = sorted(gl, key=lambda c: (c['kind'] != kind, abs(math.log(max(1.0, c['w'] * c['d']) / max(1.0, w * d)))))
            if pick:
                m['examples'] = list(pick[0]['m']['examples'])
            out.append({'key': 'prefab:' + pn, 'culture': OWN + name, 'kind': kind, 'w': round(w), 'd': round(d),
                        'fp': [round(v) for v in fp], 'uses': 1, 'm': m, 'fort': False, 'keep': False, 'own': True,
                        'uid': 'prefab:%s@%s' % (pn, name)})
    _own_cat.update(sig=sig, out=out)
    return out


def catalog(db):
    """The game's buildings (game_catalog) and your own prefab ones (own_catalog), each with its own 'uid'."""
    g = game_catalog(db)
    return g + own_catalog(db, g) if g else g


def by_uid(C):
    """{uid: entry}. Many of the game's buildings share their main piece (three taverns are ex_common_tavern_01, each
    with its own pieces and footprint): looked up by that, the town built another of them than the plan had fitted,
    bigger, into its neighbours, the user's "two buildings completely spawned into one another" (2026-11-01)."""
    return {c['uid']: c for c in C}


def built(C, b):
    """The catalogue entry a plot's 'b' names (by its uid; by key for a plan made before uids)."""
    if not b:
        return None
    return C.get(b.get('uid')) or next((c for c in C.values() if c['key'] == b.get('key') and c['w'] == b.get('w') and c['d'] == b.get('d')), None)


def game_catalog(db):
    """[{'key': main piece, 'culture', 'kind', 'w', 'd', 'fp', 'uses', 'm': module}] for every whole building the game
    has outside a door."""
    key = id(db.recs)
    # (built again once, when the strays arrive from the survey process: built before, it kept them for the session)
    st = strays.ready(db) is not None
    if key in _cat and (_cat[key][1] or not st):
        return _cat[key][0]
    import exteriorsurvey as es
    s = es.ready(db)
    if s is None:
        return []                  # (not learnt yet: nothing kept, so the next ask finds the catalogue whole)
    memo, tri = {}, {}
    out = []
    try:
        import townwalls
        K = townwalls.kits(db)
        runs = {k['straight'].lower() for k in K.values()}
        fortish = {x.lower() for k in K.values() for x in k['models']}
    except Exception as e:
        print('wall kits:', e)
        runs, fortish = set(), set()
    for m in s.get('modules') or ():
        if not m.get('fpieces') or not any(p.get('door') for p in m['fpieces']):
            continue
        # (a building that brings lengths of town wall with it, two or more of a wall kit's straights or a curved wall:
        # set down alone, its walls stood about the town as strays, a guard tower's three straights seven times over in
        # an Imperial town and Hlaalu's curved yard wall snaking between houses, the Tamriel practice 2026-10-31)
        if sum(1 for p in m['fpieces'] if p['id'].lower() in runs or 'wall_curve' in p['id'].lower()) >= 2:
            continue
        cult = townsurvey.town_style(m['main'])
        if not cult:
            continue
        # (no piece of a town wall, gate or rampart as a building: dropped on a plot it was a stray length of wall; the
        # user: "for a walled city, the walls line up, the pieces snap together, and it looks like a real wall". Walls
        # are laid whole, by the game's joins, in a stage of their own)
        if WALLISH.search(m['main']) or sum(1 for p in m['fpieces'] if WALLISH.search(p['id'])) > 0.5 * len(m['fpieces']):
            continue
        m = strays.without(db, m)            # (windows learnt with it from the house next door: strays.py)
        m = _trim_yard(db, m, memo)
        m = _no_repeats(m)
        m = _drop_apart(db, m, memo)
        m = _explained(db, m, memo)          # (a porch holds a door of its own building; a window sits on its shell)
        m = _without_lone_doors(db, m, memo, tri)
        if m is None:
            continue
        if _two_buildings(db, m, memo):
            continue
        fp = _footprint(db, m, memo)
        if not fp:
            continue
        if _floating(db, m, memo):
            continue
        if _open_walkway(db, m, memo):
            continue
        if _roof_door(db, m, memo):
            continue
        # (the top of a tower stack, learnt as a building for the door on its platform: set on the ground it stood
        # sunk to its roof, the user's island town, test3. A stack part whose module holds no base piece)
        if STACK_PART.search(m['main']) and not any(BASE_PART.search(p_['id']) for p_ in m['fpieces']):
            continue
        # (and the bottom of one with nothing on it: a tower's base and middle without its top or roof stood as an open
        # stump, four round an Imperial keep, the Tamriel practice 2026-10-31)
        if re.search(r'tower', m['main'], re.I) and BASE_PART.search(m['main']) and                 not any(re.search(r'top|roof', p_['id'], re.I) for p_ in m['fpieces']):
            continue
        # (a waterfront's wall, a dock or a pier is no house: Hlaalu's wfcurve stood inland as one, the town practice)
        if WATERFRONT.search(m['main']):
            continue
        w, d = fp[2] - fp[0], fp[3] - fp[1]
        if not (150 < w < MAX_ACROSS and 150 < d < MAX_ACROSS):
            continue
        # (a tomb's, a barrow's, a cave's or a mine's door stands in the game's towns too: no plot takes one)
        import towninside
        ex = [e for e in m.get('examples') or () if towninside.town_ok((mapdata.cell_info(db, e) or {}).get('name') or e)]
        if m.get('examples') and not ex:
            continue
        kinds = [townsurvey.kind_of(e) for e in ex]
        # (a tie the first of them by name: over a set, the kind of a building with one manor and one plain interior
        # changed with each run's string hashes, and a walled town of the same seed stood 56 buildings or 68, lab jdet)
        kind = max(sorted(set(kinds)), key=kinds.count) if kinds else 'other'
        # (a ruin's piece: a broken keep stood among new houses)
        if any(RUIN.search(p['id']) for p in m['fpieces']):
            continue
        # (a fort's part: a keep is whole, a tower or a stretch of fort wall stands only against a neighbour, fit)
        keep = bool(KEEP.search(m['main']))
        # (the building is itself a tower or a fort wall's piece; or a guard tower of any set: the legion's stood three
        # together among the houses on an Imperial town's guard plots, now the wall has towers of its own, test4 practice)
        fort = keep or m['main'].lower() in fortish or bool(re.search(r'guardtower', m['main'], re.I))
        # (a tower that brings a piece of its fort's wall with it, an arch or a length: it trailed off into the open)
        if fort and not keep and any(p['id'].lower() != m['main'].lower() and p['id'].lower() in fortish and 'wall' in p['id'].lower()
                                     and 'wallent' not in p['id'].lower() for p in m['fpieces']):
            continue
        if not keep and any('bridge' in p['id'].lower() or WATERFRONT.search(p['id']) for p in m['fpieces']):
            continue                     # (any building with a bridge to its neighbour, a mooring or a lighthouse: a stub of
                                         # a waterfront or a fort; four legion lighthouses and their bridges stood inland
                                         # on an Imperial town's guard plots, test4 practice)
        # (any house that brings a town wall's length, corner, arch or tower with it, a wall's height: set down inside the
        # town, it stood as a stray stretch of wall among the houses, Common's guard house and tavern built against Old
        # Ebonheart's wall, the user's Chillmorrow, test4. A yard's low wall stays: it is the house's own)
        if not keep and any(p['id'].lower() != m['main'].lower() and p['id'].lower() in fortish and 'wallent' not in p['id'].lower()
                            and _height(db, p['id'], memo) >= FORT_HEIGHT for p in m['fpieces']):
            continue
        if keep and not _keep_whole(db, m, fortish, memo):
            continue
        # (a well is no house: Solstheim's, with its trapdoor, stood on ten house plots of a Nordic-led town)
        if NOT_BUILDING.search(m['main']):
            continue
        # (a data file's one-of-a-kind landmark, made for one city (Tamriel Data's "_x_" sets: a chapel of Old Ebonheart's
        # stood as a lone keep tower among a Common town's houses, the user 2026-11-06): not a town's building)
        if re.search(r'_x_', m['main'], re.I):
            continue
        out.append({'key': m['main'], 'culture': cult, 'kind': kind, 'w': round(w), 'd': round(d), 'fp': [round(v) for v in fp],
                    'uses': m.get('uses', 1), 'm': m, 'fort': fort, 'keep': keep,
                    # (by the game building it was learnt from, not its place in the list: the list changes when the
                    # strays arrive, and a plan made before would have built other buildings than it showed)
                    'uid': '%s#%s' % (m['main'].lower(), ((m.get('examples') or [''])[0] or str(len(out))).lower())})
    seen = set()
    for c in out:
        if c['uid'] in seen:
            c['uid'] += '#%d' % len(seen)
        seen.add(c['uid'])
    _cat[key] = (out, st)
    _lone_save()
    return out


RUIN = re.compile(r'ruin|broken|collapsed|rubble', re.I)
KEEP = re.compile(r'keep', re.I)
# (Nordic windows are ex_nord_win_01/02 and Tamriel's chapel ones _X_WinKynaret...: by "window" alone they counted as
# walls, and a Common guard house's Nordic window hung in the air beside it four times in the user's Nargorewatch,
# 2026-11-01. An entrance too: a Firewatch row's furnisher entrance and sign were learnt with the house next door,
# 500 off, and stood alone in the user's town)
OPENING = re.compile(r'window|_win(_|\d|$)|_x_win(?!d)|triwin|door|entrance|shutter|awning|sign|banner', re.I)
STACK_PART = re.compile(r'_top|top_|roof|_med_|_light_|_dark_|upper', re.I)
BASE_PART = re.compile(r'base|_bottom|foundation', re.I)
WATERFRONT = re.compile(r'_wf|waterfront|dock|pier|quay|jetty|mooring|_ship|boat|cutter|shipwreck|shipwrk|wreck|lighthouse', re.I)
# (and a stair, a deck, a plank or a chimney taken for a building: a log cabin's stairs alone lay flat on the snow as a
# "house", the user's Nordic village, 2026-11-01)
NOT_BUILDING = re.compile(r'well|stairs?\b|stairs?_|steps|_deck|plank|platform|truss|chimney|terrace', re.I)
OPEN_REACH = 100               # a window's or door's middle stands at most this far from one of its building's walls
FORT_HEIGHT = 600              # a wall kit's piece this tall is a town wall's, not a yard's (ex_imp_wall_01 921)
KEEP_DROP = 480                # a keep whose pieces reach further than this under its door stood down a hill or a cliff


def _height(db, pid, memo):
    low = pid.lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(pid))
    b = memo[low]
    return (b[5] - b[2]) if b else 0.0


ROOF_DOOR = 200                # a building rising less than this over its door is entered from its roof


def _roof_door(db, m, memo):
    """Is the door on the building's roof? Balmora's houses by the Odai are entered from the upper street, the door on
    top and the walls going down to the river: set on level ground they stood sunk to their parapets, empty stone basins
    among the houses (the town practice, u2_hla). They rise 60-90 over the door; every other culture's 265 and more."""
    doors = [p for p in m['fpieces'] if p.get('door')]
    if not doors:
        return False
    dz = min(p['z'] for p in doors)
    top = None
    for p in m['fpieces']:
        if p.get('door'):
            continue
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if b:
            t = p['z'] + b[5] * (p.get('s') or 1.0)
            top = t if top is None else max(top, t)
    return top is not None and top - dz < ROOF_DOOR


def _keep_whole(db, m, fortish, memo):
    """Can this keep stand on its own on level ground, whole? Most of the game's are a part of a bigger fort, their door
    up on a platform or a hillside: their towers reached 2,000 under the door and stood buried, and the lengths of fort
    wall, arches and wall towers they carry stood loose about the town, its towers' bases without their tops as stumps
    (the user's Chillmorrow, test4: "a randomly thrown together sprawl"). Keeps that reach no further than KEEP_DROP
    under the door, carry no length of wall and have a top on every tower."""
    lowest = 0.0
    bases = tops = 0
    for p in m['fpieces']:
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if b:
            lowest = min(lowest, p['z'] + b[2] * (p.get('s') or 1.0))
        if low != m['main'].lower() and low in fortish and 'wall' in low and 'wallent' not in low:
            return False
        if 'tower' in low and BASE_PART.search(low):
            bases += 1
        if 'tower' in low and re.search(r'top|roof', low):
            tops += 1
    return lowest >= -KEEP_DROP and tops >= bases


def _floating(db, m, memo):
    """Is a window or door of this building touching none of its walls? The survey cut some buildings short, a window
    or door kept and the wall it stood in left out (28 of 290 Imperial, Anvil and Gold Coast ones, lab jfloat): set down
    whole on a plot, they stood as an incomplete building with windows and doors in the air, the user's first town."""
    boxes = []
    for p in m['fpieces']:
        if p['id'] not in memo:
            ri = db.resolve_id(p['id'])
            memo[p['id']] = mapdata.object_bounds(db, ri) if ri is not None else None
        b = memo[p['id']]
        if not b:
            continue
        sc, c, sn = p.get('s') or 1.0, math.cos(p.get('rz') or 0.0), math.sin(p.get('rz') or 0.0)
        xs = [p['x'] + (bx * c + by * sn) * sc for bx in (b[0], b[3]) for by in (b[1], b[4])]
        ys = [p['y'] + (-bx * sn + by * c) * sc for bx in (b[0], b[3]) for by in (b[1], b[4])]
        boxes.append((bool(OPENING.search(p['id'])), (min(xs), min(ys), p['z'] + b[2] * sc, max(xs), max(ys), p['z'] + b[5] * sc)))
    solid = [b for o, b in boxes if not o]
    touch = lambda a, b: all(a[i] - 24 <= b[i + 3] and b[i] - 24 <= a[i + 3] for i in range(3))
    # (and its middle within OPEN_REACH of a wall: one that only grazes a corner hangs beside the building, its frame
    # standing out from no wall; frames stand 50-90 out of their own walls, lab jwin3. The user, test4: "be careful with
    # windows and doorways, don't add them unless they go on a building")
    def near(b):
        c = [(b[i] + b[i + 3]) / 2.0 for i in range(3)]
        return any(sum(max(s_[i] - c[i], 0.0, c[i] - s_[i + 3]) ** 2 for i in range(3)) <= OPEN_REACH ** 2 for s_ in solid)
    return any(o and (not any(touch(b, s_) for s_ in solid) or not near(b)) for o, b in boxes)


WALKWAY = re.compile(r'bridge|skywalk|walkway|catwalk|gangway', re.I)
WALKWAY_PAD = 48               # (a walkway's end meets a building piece this near it)


def _open_walkway(db, m, memo):
    """Does a walkway of the module end in the air: a covered bridge or skywalk out from the house to a neighbour that
    isn't there (the user's Griffbarrow, test3: "building bridge with nothing attached to other side")? True when one of
    its ends meets no other piece of the module."""
    for p in m['fpieces']:
        if not WALKWAY.search(p['id']):
            continue
        others = [o for o in m['fpieces'] if o is not p and not o.get('door')]
        ends = _ends_of(db, p, memo)
        if ends and not all(_end_met(db, e, others, memo, pad=WALKWAY_PAD) for e in ends):
            return True
    return False


DOOR_SIDE = 220                # (along a door's own wall, past its frame: its building's wall stands there, one side or both)
DOOR_OFFS = (0, 30, -30)       # (in its wall's plane and a little out or in: deeper in, a ray ran inside the house it
                               # stood off; 1 of the user's 5 found at 45)
DOOR_EDGE = 0.75               # (its frame's edge: a wall met nearer the door's middle than this of its half width)
DOOR_BEHIND = 800              # (straight out of the door and into it)
LONE_WITH = 160                # (a lone door's step, frame, awning, sign or window over it: this near, they go with it)
NOT_A_WAY_IN = re.compile(r'trap|hatch|grate|gate|marker', re.I)


def _lone_doors(db, m, memo, tri=None):
    """The module's doors with no wall of it beside them: a Common row's house kept its neighbour's door, step and
    window, the neighbour's walls left out, and the door stood alone in the street, an interior and a household behind
    it (the user's Griffbarrow, test3: "phantom doors"). Their boxes grazed the house's corner, so _floating kept them;
    rays along the door's own wall, out past its frame, find a wall or nothing."""
    import seethrough
    tri = {} if tri is None else tri
    sc = None
    out = []
    for p in m['fpieces']:
        if not p.get('door') and not (db.resolve_id(p['id']) is not None and db.recs[db.resolve_id(p['id'])][0] == 'DOOR'):
            continue
        if NOT_A_WAY_IN.search(p['id']):
            continue
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if not b:
            continue
        if sc is None:
            sc = seethrough.Scene()
            for o in m['fpieces']:
                if OPENING.search(o['id']):
                    continue
                ri = db.resolve_id(o['id'])
                model = db.recs[ri][5] if ri is not None else None
                if not model or 'marker' in model.lower() or db.recs[ri][0] == 'DOOR':
                    continue
                if model not in tri:
                    tri[model] = seethrough.model_tris(db, model)
                sc.add_model(tri[model], (o['x'], o['y'], o['z'], o.get('rx', 0.0), o.get('ry', 0.0), o['rz']), o.get('s') or 1.0)
        s = p.get('s') or 1.0
        c, sn = math.cos(p['rz']), math.sin(p['rz'])
        w = lambda ax, ay: (ax * c + ay * sn, -ax * sn + ay * c)
        thinx = (b[3] - b[0]) < (b[4] - b[1])
        n, t = (w(1, 0), w(0, 1)) if thinx else (w(0, 1), w(1, 0))
        ox, oy = w((b[0] + b[3]) / 2 * s, (b[1] + b[4]) / 2 * s)
        ox, oy = p['x'] + ox, p['y'] + oy
        hl = ((b[4] - b[1]) if thinx else (b[3] - b[0])) / 2 * s
        zs_ = [p['z'] + (b[2] + (b[5] - b[2]) * zf) * s for zf in (0.3, 0.6, 0.9)]
        # (nothing along its wall, a little out of it or in; and nothing straight in front of it or behind it: a door in
        # a curved or set-back wall has its building there. 14 of 923 game buildings, 5 doors of the user's town. A wall
        # met inside the door's own width cuts through it: the end of the house it stood off, at the corner)
        # (a wall along the door's plane is met at different distances a little out of and into the plane, or not at
        # all from inside it; a wall END across the door, the house's corner the user's door stood off, is met at one
        # distance from all three, just past the door's edge: that is not the door's wall, Tessellated Shores, 2026-11-02)
        # (a recessed door, a Hlaalu one, meets a wall end on BOTH sides: that is its own entrance. Only a wall end on
        # one side with nothing at all on the other is the corner case)
        def beside_at(z_, d):
            hs = [(sc.nearest_any((ox + n[0] * off, oy + n[1] * off, z_), (t[0] * d, t[1] * d, 0.0), hl + DOOR_SIDE) or (None,))[0] for off in DOOR_OFFS]
            got = [h for h in hs if h is not None and h >= DOOR_EDGE * hl]
            if not got:
                return 'none'
            if len(got) == len(hs) and max(got) - min(got) < DOOR_END_FLAT and min(got) < hl + DOOR_END:
                return 'end'
            return 'wall'
        beside = False
        for z_ in zs_:
            a_, b_ = beside_at(z_, 1), beside_at(z_, -1)
            if 'wall' in (a_, b_) or (a_ == 'end' and b_ == 'end'):
                beside = True
                break
        # (rays from the door's two edges instead of its middle were tried and taken back: a door in a curved wall, a
        # Velothi temple's or a Telvanni tunnel's, met it at two distances and was called lone, 90 modules for 14)
        if not beside and not any(sc.nearest_any((ox, oy, z_), (n[0] * d, n[1] * d, 0.0), DOOR_BEHIND) is not None
                                  for z_ in zs_ for d in (1, -1)):
            out.append(p)
    return out


DOOR_END = 60                  # (a face met across the door's plane within this of its edge, at one distance from every offset, is a wall end)
DOOR_END_FLAT = 6
DOOR_BEHIND_FLAT = 80          # (and must meet a wall at distances this alike: one flat wall, not a roof's inside)


_LONE = {'sig': None, 'd': {}, 'dirty': False}      # (lone doors found, by the module's pieces: on disk, cache/lonedoors_*)


def _lone_memo(db):
    """The lone doors found before, keyed by a module's pieces: finding them casts rays through every game building's
    model, 80 s of each town plan on the audit machine (and twice a session, once the strays arrive), while the answer
    depends on the pieces alone. Kept on disk by the game's signature."""
    import taste
    sig = taste.sig(db)
    if _LONE['sig'] != sig:
        _LONE.update(sig=sig, d={}, dirty=False)
        try:
            with open(_lone_path(sig), encoding='utf-8') as f:
                _LONE['d'] = json.load(f)
        except (OSError, ValueError):
            pass
    return _LONE['d']


def _lone_path(sig):
    folder = os.path.join(os.environ.get('WORKSHOP_HOME') or os.path.dirname(os.path.abspath(__file__)), 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'lonedoors_%s_v5.json' % sig)


def _lone_save():
    if not _LONE['dirty'] or not _LONE['sig']:
        return
    try:
        path = _lone_path(_LONE['sig'])
        tmp = '%s.%d.tmp' % (path, os.getpid())
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(json.dumps(_LONE['d']))
        os.replace(tmp, path)
        _LONE['dirty'] = False
    except OSError:
        pass


def _without_lone_doors(db, m, memo, tri=None):
    """The module without its lone doors and their steps, frames and signs; None when its way in is one of them."""
    import hashlib
    pieces = [(p['id'].lower(), round(p['x'], 1), round(p['y'], 1), round(p['z'], 1), round(p.get('rx', 0.0), 3),
               round(p.get('ry', 0.0), 3), round(p['rz'], 3), round(p.get('s') or 1.0, 3), bool(p.get('door'))) for p in m['fpieces']]
    key = hashlib.sha1(json.dumps(sorted(pieces)).encode()).hexdigest()[:20]
    known = _lone_memo(db)
    if key in known:
        at = set(known[key])
        lone = [p for n, p in enumerate(m['fpieces']) if n in at]
    else:
        lone = _lone_doors(db, m, memo, tri)
        known[key] = [n for n, p in enumerate(m['fpieces']) if any(p is q for q in lone)]
        _LONE['dirty'] = True
    if not lone:
        return m
    front = min((p for p in m['fpieces'] if p.get('door')), key=lambda p: p['x'] ** 2 + p['y'] ** 2 + (p['z'] * 3) ** 2, default=None)
    if front is None or any(p is front for p in lone):
        return None
    drop = {id(p) for p in lone}
    for p in m['fpieces']:
        if OPENING.search(p['id']) and any(math.hypot(p['x'] - d['x'], p['y'] - d['y']) <= LONE_WITH for d in lone):
            drop.add(id(p))
    return dict(m, fpieces=[p for p in m['fpieces'] if id(p) not in drop])


def _frame(face):
    """(c, s) of the turn a building's door frame takes for a plot whose door opens the face way: groups.place's own
    turn, so its +y (inward) runs from the door into the plot."""
    yaw = face + math.pi
    return math.cos(yaw), math.sin(yaw), yaw


def _world(x, y, c, s, dx, dy):
    return x + dx * c + dy * s, y - dx * s + dy * c


SPECIAL = ('temple', 'guild', 'guard', 'tavern')
NUDGES = ((0, 0), (-160, 0), (160, 0), (0, 160), (-320, 0), (320, 0), (0, 320), (-160, 160), (160, 160))
KIND_NEAR = {('house', 'other'): 0.0, ('other', 'house'): 0.0, ('manor', 'house'): 0.5, ('shop', 'house'): 0.6, ('tavern', 'shop'): 0.6}


def fit(db, plan, seed=1):
    """A building for each plot of the plan: the town's culture's own (or the nearest culture's, when it has few),
    the plot's kind first, about the plot's size, not the same one over and over. Each plot gets 'b': {key, culture,
    kind, w, d}, its rect becomes the building's own outline and its door the building's door. The plan, changed."""
    C = catalog(db)
    cult = plan.get('own') or plan['culture']
    pool = [c for c in C if c['culture'] == cult]
    for near in NEAR_CULTURES.get(cult, ()):
        if len(pool) >= 12:
            break
        pool += [c for c in C if c['culture'] == near]
    if not pool:
        return plan
    rng = random.Random('%d|%s|b' % (int(seed), cult))
    # (one leading family, and the families the game's own towns mix with it: "Imperial" alone mixed Gold Coast towers,
    # Reach timber houses and fort walls in one town, lab 2026-10-30. The lead is drawn by how many of the culture's
    # buildings are of it)
    M = family_mix(db)
    # (the lead: a family that leads the culture's own towns in the game, as often as it does; else by its buildings)
    # (only families the culture's own buildings are of: Common's game towns include Old Ebonheart and Dagon Fel, and
    # ex_vivec led a Common town of Dunmer shacks, a Telvanni stem house and Imperial towers, not one ex_common
    # building, the user's island town, test3)
    own = {family(c_['key']) for c_ in pool if c_['culture'] == cult}
    fams = {f: o['cultures'].get(cult, 0) for f, o in M.items() if o['cultures'].get(cult) and f in own}
    if not fams:
        for c_ in pool:
            if c_['culture'] == cult:
                f = family(c_['key'])
                fams[f] = fams.get(f, 0) + 1
    lead = plan.get('family') if plan.get('family') in fams else None
    if lead is None and fams:
        pick = rng.random() * sum(fams.values())
        for f, n in sorted(fams.items()):
            pick -= n
            if pick <= 0:
                lead = f
                break
    share = {}
    if lead:
        # (the families its game towns mix, by their share of the buildings, from the whole catalogue: an Imperial town
        # of ex_imp alone was all fort sections; let in as equals, a Redoran town came out mostly Hlaalu)
        share = {f: v for f, v in (M.get(lead, {}).get('mix') or {lead: 1.0}).items() if v >= 0.03}
        share.setdefault(lead, 0.5)
        # (from the look's own buildings: taken from the whole catalogue, the families the game mixes with a lead brought
        # in other looks' buildings; a kind the look lacks is lent from its near culture below, as the game mixes them)
        narrow = [c_ for c_ in pool if family(c_['key']) in share]
        if len(narrow) >= 8:
            pool = narrow
    plan['family'] = lead
    # (a kind of building the look has too few of, its near culture's of that kind: the classic Imperial look's game towns
    # are forts, with hardly a shop, tavern or plain house, and the game stands Common ones among Imperial in Pelagiad and
    # Old Ebonheart; the user, 2026-10-31: "appropriate to mix and match between these styles when certain types of pieces
    # are missing")
    have = Counter(c['kind'] for c in pool)
    lend = {}
    for near in NEAR_CULTURES.get(cult, ())[:1]:
        for c in C:
            if c['culture'] == near and have[c['kind']] < 3:
                lend.setdefault(c['kind'], []).append(c)
    # (the buildings it would choose from, each to leave out by unticking: PIN2 2026-11-01, "give you a selection of
    # buildings that would be used in the generation ... remove lets say certain chapels")
    skip = {str(k).lower() for k in plan.get('skip') or ()}
    ch = {}
    for c_ in pool + [x for v in lend.values() for x in v]:
        e = ch.setdefault(c_['key'].lower(), {'key': c_['key'], 'kind': c_['kind'], 'culture': c_['culture'], 'w': c_['w'], 'd': c_['d'],
                                              'off': c_['key'].lower() in skip, 'n': 0})
    pool = [c_ for c_ in pool if c_['key'].lower() not in skip]
    lend = {k_: [c_ for c_ in v if c_['key'].lower() not in skip] for k_, v in lend.items()}
    used = {}
    import townplan
    placed = [[tuple(p_) for p_ in r] for r in plan.get('obstacles') or ()]
    roads = {tuple(r) for r in plan.get('roads') or ()}
    # (and the streets' own middle lines, every 64: a building whose corners missed the road squares still stood
    # across a street, the in-game walk 2026-11-03)
    street_pts = _street_points(plan)
    keep = []
    keeps = []
    ways = []                            # (the ground straight out of each fitted building's door, kept clear)
    # (the special buildings first, then the biggest plots: the ones hardest to fit)
    for q in sorted(plan['plots'], key=lambda q: (q['kind'] == 'house', -q['w'] * q['d'])):
        pw, pd = max(150.0, q['w']), max(150.0, q['d'])

        def cost(c):
            k = 0.0 if c['kind'] == q['kind'] else KIND_NEAR.get((q['kind'], c['kind']), 1.2)
            if q['kind'] in ('house', 'other') and c['kind'] in SPECIAL:
                k = 4.0                  # (a house plot in a chapel or a guard tower: its interior is a chapel's, lab jtint1; 2.5
                                         # still left 4 chapels on 46 Imperial house plots, lab jchap)
            if c['kind'] == 'guard' and q['kind'] != 'guard':
                k = 8.0                  # (a fort's tower on a shop, tavern or house plot: one Imperial town stood seven)
            sw, sd = c['w'] / pw, c['d'] / pd
            size = abs(math.log(sw)) + abs(math.log(sd)) + (2.0 * (max(sw, sd) - 1.15) if max(sw, sd) > 1.15 else 0.0)
            fam = 0.6 * -math.log(max(0.02, share.get(family(c['key']), 0.02))) if share else 0.0
            # (a building whose game interiors are all copied already in this town: the next would repeat one, the same
            # chapel three times in a town, lab jchap)
            u = used.get(c['key'], 0)
            again = 2.0 if u and u >= len(c.get('examples') or ()) else 0.0
            return k + size + fam + 0.35 * u + again - 0.05 * math.log(1 + c['uses']) + rng.random() * 0.25
        # (the best that stands clear of the buildings already fitted: a game building bigger than its plot ran into its
        # neighbour, 2 to 22 pairs a town, lab jtbuild1)
        c, sn, _yaw = _frame(q['face'])
        b = None
        # (the first 80: of the first 30, a plot in five of a walled Hlaalu town found none clear of its neighbours)
        for cand in sorted(pool + lend.get(q['kind'], []), key=cost)[:80]:
            if cand.get('fort') and not cand.get('keep'):
                continue                         # (a fort's loose part: _lone_forts)
            if cand.get('keep') and (keeps or plan.get('nokeep')):
                continue                         # (one keep a town, whole; seven stood in for guard towers)
            fp = cand['fp']
            cfx, cfy = (fp[0] + fp[2]) / 2.0, (fp[1] + fp[3]) / 2.0
            ox, oy = _world(0, 0, c, sn, cfx, cfy)
            for nx_, ny_ in NUDGES:
                # (where it runs into a neighbour on its plot, a little aside or back from the street: the game's buildings
                # are bigger than the plots cut for them, and a walled Hlaalu town built 16 of its 25)
                mx, my = _world(0, 0, c, sn, nx_, ny_)
                dx, dy = q['x'] - ox + mx, q['y'] - oy + my      # (the door, so the building's middle is the plot's)
                rect = [_world(dx, dy, c, sn, fx, fy) for fx, fy in ((fp[0] + 8, fp[1] + 8), (fp[2] - 8, fp[1] + 8), (fp[2] - 8, fp[3] - 8), (fp[0] + 8, fp[3] - 8))]
                if any(townplan._overlap(rect, o) for o in placed):
                    continue
                # (its door with a way out, and no other building's door shut by it)
                way = _doorway(dx, dy, c, sn)
                if any(townplan._overlap(rect, w_) for w_ in ways) or any(townplan._overlap(way, o) for o in placed):
                    continue
                if (nx_ or ny_) and any((int(x_ // townplan.PATCH), int(y_ // townplan.PATCH)) in roads for x_, y_ in rect[2:4] + [
                        ((rect[0][0] + rect[2][0]) / 2, (rect[0][1] + rect[2][1]) / 2)]):
                    continue                             # (nudged onto a street: its far corners and middle stay off them)
                if _over_street(rect, street_pts):
                    continue                             # (never over a street's middle line: five buildings stood on
                                                         # street points, the in-game walk 2026-11-03)
                b = cand
                break
            if b is not None:
                break
        if b is None:
            continue
        placed.append(rect)
        ways.append(way)
        keep.append(q)
        used[b['key']] = used.get(b['key'], 0) + 1
        if b.get('keep'):
            keeps.append(q)
        q['b'] = {'key': b['key'], 'culture': b['culture'], 'kind': b['kind'], 'w': b['w'], 'd': b['d'], 'uid': b['uid']}
        q['door'] = [round(dx, 1), round(dy, 1)]
        if mx or my:
            q['x'], q['y'] = round(q['x'] + mx, 1), round(q['y'] + my, 1)      # (where it was nudged)
        q['rect'] = [[round(v, 1) for v in _world(dx, dy, c, sn, fx, fy)] for fx, fy in ((fp[0], fp[1]), (fp[2], fp[1]), (fp[2], fp[3]), (fp[0], fp[3]))]
        q['way'] = [[round(v, 1) for v in p_] for p_ in way]
    plan['plots'] = [q for q in plan['plots'] if q in keep]
    _off_streets(plan, street_pts, 'fitted')
    _close_rows(plan, rng)
    _off_streets(plan, street_pts, 'closed up')
    _lone_forts(plan, by_uid(C))
    _shut_doors(plan)
    for q in plan['plots']:
        e = ch.get(((q.get('b') or {}).get('key') or '').lower())
        if e:
            e['n'] += 1
    plan['choices'] = sorted(ch.values(), key=lambda e: (e['kind'] == 'house', e['kind'], -e['n'], e['key'].lower()))
    return plan


WALL_BACK = 320                # a walled town's buildings stand back to its wall this close (its own depth ~250)


def planned(db, outline, culture, seed=1, walls='', opts=None):
    """The town planned and its buildings fitted (townplan.plan, fit). Walled: planned twice, the second time inside the
    wall the first plan's buildings call for, so its streets and buildings fill the wall corner to corner as the game's
    walled towns do: planned once, the town's streets made a long blob and the wall's box round it left its corners
    bare, two fifths of the ground inside empty against a fifth or less in Firewatch and Ebonheart (the Tamriel
    practice, 2026-11-01). opts: the user's choices (townplan.plan_once); opts['wall'], a wall drawn on the map, is
    the wall, squared to its pieces' steps (townwalls.square_up), and the town fills it."""
    import townplan
    opts = opts or {}
    # (the bar's planning share: a walled town is planned twice, its two plans the most of it)
    P = PLAN_END
    pl = townplan.plan(db, outline, culture, seed, walled=bool(walls), opts=opts)
    if opts.get('own'):
        pl['own'] = opts['own']             # (built of your own style's prefabs, planned like `culture`'s towns)
    pl['skip'] = list(opts.get('skip') or ())
    pl['nokeep'] = bool(opts.get('nokeep'))     # (a castle's quarter: no keep building in it)
    _say('Choosing the buildings', P * (0.3 if walls else 0.8))
    plan = fit(db, pl, seed)
    if not walls:
        return plan
    import townwalls
    _say('Planning inside the wall', P * 0.4)
    drawn = opts.get('wall') or []
    if len(drawn) >= 3:
        # (drawn by the user, "like ridges that lock into a grid once you put down your first point", PIN2)
        K = townwalls.kits(db)
        fam = walls if walls in K else townwalls.pick_family(db, plan)
        poly = townwalls.square_up(drawn, K[fam]['L']) if fam else []
    else:
        try:
            W = townwalls.lay(db, plan, None if walls == 'auto' else walls)
        except Exception as e:
            print('town wall:', e)
            return plan
        poly = W.get('outline') or []
    if len(poly) < 4:
        return plan
    inner = townplan.inset(poly, WALL_BACK)
    pl = townplan.plan(db, inner, culture, seed, walled=True, ring=True, opts=opts)
    if opts.get('own'):
        pl['own'] = opts['own']
    pl['skip'] = list(opts.get('skip') or ())
    pl['nokeep'] = bool(opts.get('nokeep'))     # (a castle's quarter: no keep building in it)
    _say('Choosing the buildings', P * 0.85)
    again = fit(db, pl, seed)
    built = lambda p_: sum(1 for q in p_['plots'] if q.get('b'))
    if built(again) < 0.75 * built(plan) and len(drawn) < 3:
        return plan
    again['wall_outline'] = [list(p_) for p_ in poly]
    return again


GATE_CLEAR = 1200              # the ground inside a gate kept free of buildings, this deep
DOOR_CLEAR = 320               # the ground straight out of a door kept free of buildings, this deep
DOOR_WAY = 224                 # and this wide


def _off_streets(plan, street_pts, when):
    """Buildings standing over a street's middle line left out (none should: a last guard, said when it fires)."""
    import townplan
    gone = [q for q in plan['plots'] if q.get('b') and q.get('rect') and _over_street(q['rect'], street_pts)]
    if gone:
        print('town: %d building(s) over a street after %s: %s' % (len(gone), when, [(q['b']['key'], round(q['x']), round(q['y'])) for q in gone]))
        plan['plots'] = [q for q in plan['plots'] if q not in gone]


STREET_KEEP = 96               # a building's faces stay this far off a street's middle line (half a lane, less its own setback)


def _over_street(rect, street_pts):
    """Whether a street's middle line comes within STREET_KEEP of this rect (a ring lane ran along a house's back wall,
    half of it under the house)."""
    import townplan
    grown = _shrink_rect(rect, -STREET_KEEP)
    return any(townplan._inside(grown, x, y) for x, y in street_pts)


def _street_points(plan):
    """The streets' middle lines, a point every 64: nothing is fitted or slid over them."""
    out = []
    for st in plan.get('streets') or ():
        P = st.get('pts') or []
        for a, b in zip(P, P[1:]):
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // 64))
            out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]
    return out


def _doorway(dx, dy, c, sn):
    """The way out of a door at (dx, dy) in its plot's frame (c, sn): the strip of ground in front of it, as world points.
    (One in seven doors of the walled towns opened straight onto another building's wall within 256, lab jdoor0. The
    user, test5 practice: "doorways must remain accessible, and the entrances tend to line up along streets, common
    access coves".)"""
    h = DOOR_WAY / 2.0
    return [_world(dx, dy, c, sn, fx, fy) for fx, fy in ((-h, -16 - DOOR_CLEAR), (h, -16 - DOOR_CLEAR), (h, -16), (-h, -16))]


def _shut_doors(plan):
    """Buildings whose door another stands in front of, left out (rows drawn together can close one up)."""
    import townplan
    built = [q for q in plan['plots'] if q.get('b') and q.get('rect')]
    shut = [q for q in built if q.get('way') and any(o is not q and townplan._overlap(_shrink_rect(o['rect'], 8), q['way']) for o in built)]
    if shut:
        plan['plots'] = [q for q in plan['plots'] if q not in shut]


def _lone_forts(plan, C):
    """A fort's tower or stretch of fort wall, left out: in the game they stand in a fort's own run, and set among houses
    they read as broken wall or open stumps, in groups too (round guard towers are open at the top). The user,
    2026-10-31: "keep a whole keep and clean up the loose bits that don't fit and don't have neighbours"."""
    lone = [q for q in plan['plots'] if q.get('b') and (built(C, q['b']) or {}).get('fort')
            and not (built(C, q['b']) or {}).get('keep')]
    if lone:
        plan['plots'] = [q for q in plan['plots'] if q not in lone]


JOIN_GAP = 1200                # (a gap this small or less along a row is closed, as often as the culture joins its buildings)


def _close_rows(plan, rng):
    """Buildings drawn together as often as the culture's towns join theirs (townplan figures 'joined': Hlaalu 0.74,
    Common 0.68, Redoran 0.57, Telvanni 0.50): along a street side towards the neighbour before it, in an open town
    towards the nearest. Each is smaller than the plot cut for it, and the towns came out a building, a gap, a building
    where the game's stand wall to wall, lab jdens. Slid in small steps until it meets its neighbour, never into
    another building."""
    import townplan
    j = ((plan.get('figures') or {}).get('joined')) or 0.0
    if j <= 0:
        return
    built = [q for q in plan['plots'] if q.get('b') and q.get('rect')]
    street_pts = _street_points(plan)

    def clear(rect, me, way=None):
        sh = _shrink_rect(rect, 8)
        # (never slid over a street's middle line: a guard tower and a farmhouse stood on street points, the in-game
        # walk 2026-11-03)
        if _over_street(sh, street_pts):
            return False
        return not any(o is not me and (townplan._overlap(sh, _shrink_rect(o['rect'], 8))
                                         or (o.get('way') and townplan._overlap(sh, o['way']))
                                         or (way and townplan._overlap(way, _shrink_rect(o['rect'], 8)))) for o in built)

    def slide(b, vx, vy, toward):
        # (steps of 24 up to JOIN_GAP; kept where it last stood clear, if it then touches the one it moved toward)
        last = None
        for k in range(1, int(JOIN_GAP // 24) + 1):
            d = 24.0 * k
            moved = [[p[0] + vx * d, p[1] + vy * d] for p in b['rect']]
            mway = [[p[0] + vx * d, p[1] + vy * d] for p in b['way']] if b.get('way') else None
            if not clear(moved, b, mway):
                break
            last = d
        if not last:
            return
        moved = [[p[0] + vx * (last + 24), p[1] + vy * (last + 24)] for p in b['rect']]
        if not townplan._overlap(_shrink_rect(moved, 8), _shrink_rect(toward['rect'], 8)):
            return                               # (stopped by something else first, or never reached it)
        mx, my = vx * last, vy * last
        b['rect'] = [[round(p[0] + mx, 1), round(p[1] + my, 1)] for p in b['rect']]
        if b.get('way'):
            b['way'] = [[round(p[0] + mx, 1), round(p[1] + my, 1)] for p in b['way']]
        b['x'], b['y'] = b['x'] + mx, b['y'] + my
        if b.get('door'):
            b['door'] = [round(b['door'][0] + mx, 1), round(b['door'][1] + my, 1)]
    def toward_nearest(bs):
        for b in sorted(bs, key=lambda q: rng.random()):
            if rng.random() > j:
                continue
            a = min((o for o in built if o is not b), key=lambda o: math.hypot(o['x'] - b['x'], o['y'] - b['y']), default=None)
            if a is None:
                continue
            vx, vy = a['x'] - b['x'], a['y'] - b['y']
            L_ = math.hypot(vx, vy) or 1.0
            if (math.sin(b['face']) * vx + math.cos(b['face']) * vy) / L_ > 0.5:
                continue                             # (door first: it would stand with its door against the other's wall)
            slide(b, vx / L_, vy / L_, a)
    if plan.get('layout') == 'open':
        toward_nearest(built)
        return
    rows = {}
    for q in built:
        if q.get('street') and q.get('si') is not None:
            rows.setdefault(q['si'], []).append(q)
    for row in rows.values():
        row.sort(key=lambda q: q.get('at', 0.0))
        # (neighbours along the street on the same side: facing within 40 degrees of each other; a bending street turns
        # every door a little, and grouping by the exact facing made a row of one)
        for i, a in enumerate(row):
            b = next((b for b in row[i + 1:] if abs(((b['face'] - a['face'] + math.pi) % (2 * math.pi)) - math.pi) < math.radians(40)), None)
            if b is None or rng.random() > j:
                continue
            vx, vy = a['x'] - b['x'], a['y'] - b['y']
            L_ = math.hypot(vx, vy) or 1.0
            slide(b, vx / L_, vy / L_, a)
    # (the buildings off the street, behind the rows: towards their nearest too, as the game's yards close up; left where
    # their plots were cut, a Redoran town joined none of its buildings, the Tamriel practice 2026-10-31)
    toward_nearest([q for q in built if not q.get('street')])


def _shrink_rect(r, d):
    cx, cy = sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r)
    out = []
    for x, y in r:
        dx, dy = x - cx, y - cy
        h = math.hypot(dx, dy) or 1.0
        out.append((x - dx / h * d, y - dy / h * d))
    return out


# How far Make it has got, for the Town panel's bar (GET /api/town/progress, asked while it works; PIN2, 2026-11-01: "It
# takes a bit for the town to appear. you think you can do a progress bar?"). The shares are each stage's time in a
# test server (a walled Hlaalu town of 28 buildings with people, 52 s): planning 15 s, the town itself 8 s, its
# interiors and their people 29 s. The town's own shares (planning to PLAN_END, then the stages) run to STAGE_END of the
# bar when interiors follow, to the end without.
PROGRESS = {'on': False, 'what': '', 'frac': 0.0, 'ins': False}
PLAN_END = 0.65
STAGE_END = 0.45


def _say(what, frac):
    if PROGRESS['on']:
        f = frac * STAGE_END if PROGRESS['ins'] else frac
        PROGRESS.update(what=what, frac=round(max(PROGRESS['frac'], min(1.0, f)), 3))


def progress():
    return {k: v for k, v in PROGRESS.items() if k != 'ins'}


def make(db, outline, culture, seed=1, walls='', dress=False, interiors=False, people=False, name='', opts=None):
    """_make, with how far it has got said as it goes (PROGRESS)."""
    PROGRESS.update(on=True, what='Planning streets and plots', frac=0.0, ins=bool(interiors))
    try:
        return _make(db, outline, culture, seed, walls, dress, interiors, people, name, opts)
    finally:
        PROGRESS.update(on=False, what='', frac=0.0, ins=False)


LAST = {}                      # (the last town's plan, for the checks)


def _make(db, outline, culture, seed=1, walls='', dress=False, interiors=False, people=False, name='', opts=None):
    """The town built: its plan (townplan.plan, the same seed gives the same town) and a building of the culture's on
    every plot, each set down on the ground in front of its door as the game's stands on its own. One Undo step.
    walls: '' none, 'auto' the culture's own, or a wall family (townwalls.py): laid round it, piece joined to piece.
    dress: its yards, streets and square dressed as the culture's game towns are (towndress.py).
    interiors: behind each door one of the game's interiors for that building, named in the town's name; people: its
    household in it (towninside.py). name: the town's ('' makes one).
    {'buildings', 'pieces', 'cells', 'fitted', 'road', 'wall', 'dressed', 'interiors', 'people', 'name'}."""
    import editing
    import townplan
    from project import set_ref_pos, zs
    editing._require_project(db)
    plan = planned(db, outline, culture, seed, walls, opts)
    LAST['plan'] = plan
    C = by_uid(catalog(db))
    mine = db.project.plugin.lower()
    made, pieces, cells = 0, 0, set()
    rmemo = {}
    doors, new_refs = [], set()
    # the wall laid out and its ground evened first, so the buildings stand on the ground as it ends up: evened after
    # they were set down, the land rose round them and buried them to their roofs (the user's Chillmorrow, test3)
    W = None
    if walls:
        import townwalls
        _say('Laying the wall', 0.66)
        W = townwalls.lay(db, plan, None if walls == 'auto' else walls)
        # (stairs up to the walk inside, where no house is to stand: the game's walled towns climb to theirs)
        # (on ground no house stands on first; failing that, in the place of one house, its plot left empty)
        memo_s = {}

        def on_plots(st):
            cs_, _b = townwalls._box(db, st['id'], st['pose'], memo_s)
            if not cs_:
                return None
            cs_ = _shrink_rect(cs_, -48)
            return [q for q in plan['plots'] if q.get('b') and any(r_ and townplan._overlap(cs_, r_) for r_ in (q.get('rect'), q.get('way')))]
        stairs = townwalls.wall_stairs(W, free=lambda st: on_plots(st) == [], db=db)
        if not stairs:
            stairs = townwalls.wall_stairs(W, most=2, db=db, free=lambda st: len(on_plots(st) or [None, None]) <= 1 and not any(
                q.get('kind') in SPECIAL for q in on_plots(st) or ()))
        for st in stairs:
            for q in on_plots(st) or ():
                q['b'] = None
            W['pieces'].append(st)
        try:
            # (a wall already standing on or by the line, another make's, keeps its ground: townwalls.wall_guard, here
            # and in the terrace and hull passes; the town's levelling buried 14 of a castle's pieces 480-720 deep)
            plan['_wall_guard'] = townwalls.wall_guard(db, W.get('outline') or [])
            townwalls.level_ground(db, W, new_refs, keep=plan['_wall_guard'])
        except Exception as e:
            print('wall ground:', e)
    _say('Levelling the streets', 0.69)
    try:
        _level_streets(db, plan, new_refs)
    except Exception as e:
        print('streets:', e)
    _say('Levelling the ground', 0.7)
    try:
        _terrace(db, plan, W, new_refs)
    except Exception as e:
        print('terraces:', e)
    try:
        _smooth_hull(db, plan, W, new_refs)
    except Exception as e:
        print('smoothing:', e)
    plan.pop('_street_ground', None)
    _say('Clearing the ground', 0.74)
    try:
        cleared = _clear_ground(db, plan, W)
    except Exception as e:
        print('clearing:', e)
        cleared = 0
    wall_boxes = []
    wall_guard = []                      # (the wall's feet and a band round them: never cut lower by a building's ground fit)
    if W is not None:
        memo_w = {}
        for p_ in W.get('pieces') or ():
            cs_, _b = townwalls._box(db, p_['id'], p_['pose'], memo_w)
            if cs_:
                wall_boxes.append(_shrink_rect(cs_, 16))
                wall_guard.append(_shrink_rect(cs_, -WALL_GUARD))
        # (and the way in behind each gate kept open, GATE_CLEAR deep into the town)
        poly_ = W.get('outline') or []
        if poly_:
            mx_, my_ = sum(p_[0] for p_ in poly_) / len(poly_), sum(p_[1] for p_ in poly_) / len(poly_)
            for p_ in W.get('pieces') or ():
                if p_.get('kind') not in ('gate', 'end'):
                    continue
                g_ = p_['pose']
                dx_, dy_ = mx_ - g_.x, my_ - g_.y
                h_ = math.hypot(dx_, dy_) or 1.0
                wall_boxes.append(townplan._rect(g_.x + dx_ / h_ * GATE_CLEAR / 2, g_.y + dy_ / h_ * GATE_CLEAR / 2,
                                                 math.atan2(dx_ / h_, dy_ / h_), 640, GATE_CLEAR))
    for k_, q in enumerate(plan['plots']):
        _say('Setting the buildings', 0.76 + 0.1 * k_ / float(len(plan['plots']) or 1))
        b = q.get('b') and built(C, q['b'])
        if not b:
            continue
        if W and W.get('outline') and q.get('rect') and not all(townwalls._inside(W['outline'], p_) for p_ in q['rect'] + (q.get('way') or [])):
            q['b'] = None                # (outside the wall, where the land made it turn in: not built, the town is walled;
            continue                     # no yard, interior or household for it either)
        if wall_boxes and q.get('rect') and any(townplan._overlap(_shrink_rect(q['rect'], 16), w_) or (q.get('way') and townplan._overlap(q['way'], w_))
                                                for w_ in wall_boxes):
            q['b'] = None                # (into the wall, a tower or the keep, or its door against them: houses back onto
            continue                     # the wall now, 2 clashes in 5 towns, lab jwclash)
        m = b['m']
        c, sn, yaw = _frame(q['face'])
        dx, dy = q['door']
        if wall_boxes and _door_to_wall(db, m, q, dx, dy, c, sn, wall_boxes, rmemo):
            q['b'] = None                # (a back door of its against the wall: it led nowhere, or out of the town
            continue                     # through the wall, 3 Hlaalu houses backing a wall in one town, lab w03)
        # (the ground in front of the door: the building stands on it as the game's stood on its own, fground)
        fx, fy = _world(dx, dy, c, sn, 0.0, -120.0)
        gz = mapdata.terrain_z(db, fx, fy)
        if gz is None:
            continue
        z0 = gz - _fground(db, m, rmemo)
        front = min((p_ for p_ in m['fpieces'] if p_.get('door')), key=lambda p_: p_['x'] ** 2 + p_['y'] ** 2 + (p_['z'] * 3) ** 2, default=None)
        q.pop('door_pieces', None)
        # (no door set without its building: a house whose walls are of a data file not loaded stood as a door alone,
        # and an interior and a household were made behind it)
        if not any(db.resolve_id(p_['id']) is not None for p_ in m['fpieces'] if not p_.get('door') and not OPENING.search(p_['id'])):
            q['b'] = None
            continue
        gid = None                           # (its pieces kept as one building: Select the whole building, groups.building)
        hung_out = _hung_into_ground(db, m, dx, dy, c, sn, z0, rmemo)
        for p_ in m['fpieces']:
            if id(p_) in hung_out:
                continue
            low = p_['id'].lower()
            if low not in rmemo:
                rmemo[low] = db.resolve_id(p_['id'])
            ri = rmemo[low]
            if ri is None:
                continue
            wx, wy = _world(dx, dy, c, sn, p_['x'], p_['y'])
            key = '#%d,%d' % (math.floor(wx / 8192.0), math.floor(wy / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            rk = db.project.new_ref_key()
            pos = (wx, wy, z0 + p_['z'], p_.get('rx', 0.0), p_.get('ry', 0.0), (p_['rz'] + yaw) % (2 * math.pi))
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], pos, p_.get('s') or 1.0))
            gid = gid or rk
            db.project.town_parts[rk] = gid
            pieces += 1
            cells.add(key)
            new_refs.add(rk)
            if db.recs[ri][0] == 'DOOR':
                # (each door where the game's stood in its building's frame: towninside links it the way the game's led)
                q.setdefault('door_pieces', []).append({'key': key, 'rk': rk, 'id': p_['id'], 'x': p_['x'], 'y': p_['y'], 'z': p_['z']})
            if p_.get('door'):
                doors.append((key, rk))
                q['door_z'] = pos[2]
                if p_ is front:
                    q['door_ref'] = (key, rk)        # (the way in, at the module's origin: its interior's door links here)
            elif db.recs[ri][0] == 'DOOR' and not re.search(r'trap|hatch|gate|marker', p_['id'], re.I):
                q.setdefault('more_doors', []).append((key, rk))      # (its back door leads in too: towninside)
        made += 1
    # (the ground fitted to the buildings before the wall is set on it, not after: the fit raised the ground to the door
    # sills of the houses on a hill by up to 380 along the wall's line once the wall stood, and the east wall of the
    # user's Sketh lay buried 300 to 870 deep for 25 pieces in a row, its gate arches hanging; lab w93, 2026-11-07)
    fitted = 0
    if pieces:
        _say('Fitting the ground to the buildings', 0.865)
        db.sync_project()
        fitted = _fit_ground(db, doors, new_refs, [(tuple(q['door_ref']), q['rect']) for q in plan['plots'] if q.get('door_ref') and q.get('rect')],
                             guard=wall_guard)
        import os as _os
        if _os.environ.get('TOWN_UNCOVER', '1') != '0':
            try:
                uncovered = _uncover(db, plan, new_refs, guard=wall_guard)
                if uncovered:
                    print('town: %d land points cut back from over the floors' % uncovered)
            except Exception as e:
                print('town uncover:', e)
    wall = 0
    wall_refs = []
    if W is not None:
        _say('Setting the wall on the ground', 0.87)
        db.sync_project()
        W = townwalls.grounded(db, W)
        try:
            # (the fill keeps off the town's own buildings and their door fronts: a house 520 under the wall had its door
            # buried 493 by the wall's fill, the lab's Sketh 2026-11-06)
            townwalls.fill_ground(db, W, new_refs, keep=townwalls.building_guard(db, W.get('outline') or []) +
                                  townwalls.wall_guard(db, W.get('outline') or [], mine=new_refs))
        except Exception as e:
            print('wall fill:', e)
        townwalls.drop_doubled(db, W, new_refs)     # (where a castle's or another town's wall already stands)
        # (no wall-walk arches: the game stands ex_imp_wallent_02 along its walks, but set there without a building they
        # read as doorways to nowhere, the user's Chillmorrow, test4: "don't add them unless they go on a building")
        for p_ in W['pieces']:
            ri = db.resolve_id(p_['id'])
            if ri is None:
                continue
            q_ = p_['pose']
            key = '#%d,%d' % (math.floor(q_.x / 8192.0), math.floor(q_.y / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            rk = db.project.new_ref_key()
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]),
                           set_ref_pos([('NAME', zs(db.recs[ri][1]))], (q_.x, q_.y, q_.z, 0.0, 0.0, q_.rz % (2 * math.pi)), 1.0))
            wall_refs.append((key, rk, p_['id'], [q_.x, q_.y, q_.z, 0.0, 0.0, q_.rz % (2 * math.pi)]))
            wall += 1
            pieces += 1
            cells.add(key)
            new_refs.add(rk)
        # (the streets carried out through the gates, to be paved with the rest)
        have = {tuple(r) for r in plan.get('roads') or ()}
        gate = townwalls.road_patches(W.get('roads') or [])
        plan['roads'] = sorted([list(r) for r in have | gate])
        plan['paint_extra'] = sorted([list(r) for r in gate])
    dressed = 0
    dress_refs = set()
    stall_refs = {}
    life_refs = []
    if dress and made:
        _say('Dressing yards and streets', 0.89)
        import towndress
        blocked = [p_['corners'] for p_ in (W or {}).get('pieces') or () if p_.get('corners')]
        db.sync_project()
        # (what the buildings already carry: a banner of a building's own and another its surroundings brought, set
        # in one spot, flickered)
        also = [(r_['id'], r_['p']) for ck_ in cells for r_ in mapdata.cellmap(db, ck_).get('refs') or () if r_['k'] in new_refs]
        laid_ = towndress.dress(db, plan, seed, blocked, also=also)
        # (then the story layer: the ground between the houses as their yards, fenced, each with a kind of life;
        # storydress.yards. Kept clear of what the dressing laid)
        try:
            import storydress
            laid_ += storydress.yards(db, plan, seed, blocked, also=also + [(t_['id'], t_['p']) for t_ in laid_])
        except Exception as e_:
            print('town yards:', e_)
        for t in laid_:
            ri = db.resolve_id(t['id'])
            if ri is None:
                continue
            key = '#%d,%d' % (math.floor(t['p'][0] / 8192.0), math.floor(t['p'][1] / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            rk = db.project.new_ref_key()
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], tuple(t['p']), t.get('s') or 1.0))
            dressed += 1
            pieces += 1
            cells.add(key)
            new_refs.add(rk)
            dress_refs.add(rk)
            if t.get('stall') is not None:
                stall_refs.setdefault(t['stall'], []).append((key, rk))
            if t.get('role') in ('stall', 'storage', 'sign', 'awning'):
                life_refs.append((key, rk, t['role'], t.get('stall')))
    painted = 0
    inside = {}
    import towninside
    name = (name or '').strip() or towninside.town_name(db, culture, seed)
    if pieces:
        _say('Paving the roads', 0.96)
        painted = _paint_roads(db, plan)
        try:
            _unsnow(db, plan)
        except Exception as e:
            print('snow:', e)
        _say('Laying the walking paths', 0.97)
        walks = 0
        if PATHS:
            try:
                walks = _lay_paths(db, plan, cells, outline)
            except Exception as e:
                print('paths:', e)
        # (its people outdoors: sellers at the stalls, guards, townsfolk, as many a building as the culture's game towns:
        # townlife.py. The user, 2026-11-03: "Guards and npcs are also noticeably lacking")
        life = {}
        if people and dress and made:
            _say('Bringing the streets to life', 0.975)
            try:
                import townlife
                life = townlife.people(db, plan, culture, seed, cells, new_refs, W, stall_refs)
            except Exception as e:
                print('town life:', e)
        _say('Saving', 0.98)
        editing.commit(db, 'Built a %s town: %d buildings (%d pieces) in %d cells%s%s%s%s' % (
            culture, made, pieces, len(cells), ((', a wall of %d pieces' % wall) if wall else '') + ((', %d things set out' % dressed) if dressed else ''),
            (', the ground fitted to %d' % fitted) if fitted else '', (', %d road patches' % painted) if painted else '',
            ((', %d path points' % walks) if walks else '') + ((', %d people outdoors' % life['people']) if life.get('people') else '')))
        if interiors and made:
            # (each interior copied and linked, its people placed: steps of their own, folded with the town into one.
            # interiors 'shells': the game building's architecture and doors only, for you to furnish; else furnished by
            # the Workshop's own furnisher, never the source's decor: towninside.make_own)
            rooms = 'shells' if interiors == 'shells' else 'furnished'
            people = people and rooms == 'furnished'
            stack = getattr(db.project, 'undo_stack', [])
            n0 = len(stack)
            what = 'Making interiors and their people' if people else 'Making interiors'
            inside = towninside.furnish(db, plan, name, culture, seed, people, catalog(db),
                                        lambda f: PROGRESS.update(what=what, frac=round(STAGE_END + (1 - STAGE_END) * f, 3)) if PROGRESS['on'] else None,
                                        rooms=rooms)
            if wall_refs and W and W.get('outline'):
                try:
                    # (the keep and big towers first: ways in at the ground and on the walk, a stair between, castle.py)
                    import castle
                    keeps = castle.wall_keeps(db, wall_refs, W['outline'], name, set(), random.Random('%s|%s|wall keeps' % (seed, culture)), rooms=rooms)
                    inside['interiors'] += len(keeps)
                except Exception as e:
                    keeps = []
                    print('wall keeps:', e)
                try:
                    wroom = towninside.wall_rooms(db, wall_refs, W['outline'], name, set(), random.Random('%s|%s|wall rooms' % (seed, culture)), rooms=rooms)
                    inside['interiors'] += len(wroom)
                    inside['wall_rooms'] = len(wroom) + len(keeps)
                except Exception as e:
                    print('wall rooms:', e)
            try:
                import doors as doors_
                doors_.face_arrivals(db, sorted(cells))      # (keeps, towers and every interior: arrivals at their doors' faces)
            except Exception as e:
                print('door arrivals:', e)
            if PATHS and wall_refs and inside.get('wall_rooms'):
                # (the paths again, now with the keep and tower doors: they were laid before those doors were set)
                try:
                    _lay_paths(db, plan, cells, outline, _wall_ways(db, plan, cells))
                except Exception as e:
                    print('paths to the wall doors:', e)
            if len(stack) > n0:
                editing.fold(db, len(stack) - n0 + 1, 'Built %s, a %s town: %d buildings, %d interiors%s%s' % (
                    name, culture, made, inside['interiors'], (', %d people' % inside['people']) if inside['people'] else '',
                    (', a wall of %d pieces' % wall) if wall else ''))
    return {'buildings': made, 'pieces': pieces, 'cells': sorted(cells), 'fitted': fitted, 'road': painted, 'wall': wall,
            'dressed': dressed, 'interiors': inside.get('interiors', 0), 'wall_rooms': inside.get('wall_rooms', 0), 'people': inside.get('people', 0) + (life.get('people', 0) if pieces else 0), 'outdoors': life if pieces else {}, 'name': name}


PATHS = True                   # (the town's walking paths outdoors: townpaths)


def _lay_paths(db, plan, cells, outline, extra=()):
    """The town's walking paths into its cells' path grids (townpaths), out of every built plot's front door (and
    extra: more (door x, y, out x, out y) ways, the wall's keep and tower doors). No Undo step. The points laid."""
    import townpaths
    db.sync_project()
    ways = list(extra)
    for q in plan['plots']:
        if not q.get('b') or not q.get('door_ref') or not q.get('door'):
            continue
        c, sn, _yaw = _frame(q['face'])
        dx, dy = q['door']
        fx, fy = _world(dx, dy, c, sn, 0.0, -1.0)
        ways.append((dx, dy, fx - dx, fy - dy))
    keys = sorted(set(cells) | {'#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0)) for x, y in outline})
    P, L, _D = townpaths.lay(db, plan, keys, ways)
    return sum(townpaths.write(db, P, L, [tuple(v) for v in outline]).values())


def _wall_ways(db, plan, cells):
    """The ways out of the doors the wall's keeps and towers got after the paths were laid (castle.wall_keeps,
    towninside.wall_rooms): (door x, y, out x, out y) each, the way out being the arrival the room's door back sets."""
    import doors as doors_
    own = {tuple(q['door_ref']) for q in plan['plots'] if q.get('door_ref')}
    out = []
    for ck in cells:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r['type'] != 'DOOR' or not r.get('new') or not (r.get('to') or {}).get('cell') or (ck, r['k']) in own:
                continue
            pr = doors_.partner(db, ck, r)
            if pr is None or not pr[1].get('to'):
                continue
            to = pr[1]['to']
            out.append((r['p'][0], r['p'][1], to['x'] - r['p'][0], to['y'] - r['p'][1]))
    return out


REMOVE_PAD = 1600              # (a town's wall and dressing stand this far outside its outline at most)
REMOVE_BEFORE = 80             # (a building's pieces are made at most this many before its front door)


def remove(db, outline, look=False):
    """Everything a town's Make it built, taken away as one step: its buildings, wall and dressing (the objects made in
    one unbroken run, from its first building to its last interior, round its outline) and its interiors with their
    people. What you added later, and the ground, stay. For rebuilding a town whose Undo lies under later work (the
    user's Nargorewatch, 2026-11-01: 500 edits on top of it). look: only count. {'things', 'interiors', 'name'}"""
    import editing
    import townplan
    from editing import EditError, commit
    editing._require_project(db)
    p = db.project
    poly = [(float(a), float(b)) for a, b in outline]
    if len(poly) < 3:
        raise EditError("Draw the town's outline first.")
    near = lambda x, y: townplan._inside(poly, x, y) or townplan._edge_dist(poly, x, y) <= REMOVE_PAD
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    keys = ['#%d,%d' % (gx, gy) for gx in range(int((min(xs) - REMOVE_PAD) // 8192), int((max(xs) + REMOVE_PAD) // 8192) + 1)
            for gy in range(int((min(ys) - REMOVE_PAD) // 8192), int((max(ys) + REMOVE_PAD) // 8192) + 1)]
    idx = lambda rk: int(rk.rsplit('|', 1)[1]) if rk.rsplit('|', 1)[-1].isdigit() else -1
    made, fronts = [], {}
    for ck in keys:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r.get('new') and near(r['p'][0], r['p'][1]):
                made.append((ck, r))
                to = r.get('to') if r['type'] == 'DOOR' else None
                if to and to.get('cell') and to['key'] in p.cells:
                    fronts[to['key']] = min(fronts.get(to['key'], 1 << 30), idx(r['k']))
    # (its interiors: the places its doors lead into, named "<town>, ...")
    pre = Counter(k.split(', ', 1)[0] for k in fronts if ', ' in k).most_common(1)
    if pre:
        town = pre[0][0]
        inside = [k for k in p.cells if k.startswith(town + ', ')]
        hi = max([idx(rk) for k in inside for rk in (p.cells[k].get('refs') or {})] + [max(fronts.values())])
        lo = min(v for k, v in fronts.items() if k.startswith(town + ', ')) - REMOVE_BEFORE
    else:
        # (a town made with Inside: None has no interiors to find it by: its own building pieces (town_parts) and the
        # run of things made round them, the user 2026-11-03, "I just wanted to see the town plan from the outside")
        parts = [idx(r['k']) for _ck, r in made if r['k'] in p.town_parts]
        if not parts:
            raise EditError('No town built here: none of the doors inside it leads into an interior a town made.')
        town = 'Town'
        inside = []
        lo, hi = min(parts) - REMOVE_BEFORE, max(parts)
    out = [(ck, r['k']) for ck, r in made if lo <= idx(r['k']) <= hi]
    # (an interior a door left standing still leads into stays: another town of the same name, or one you linked)
    gone = {rk for _ck, rk in out}
    kept = {(r.get('to') or {}).get('key') for _ck, r in made if r['type'] == 'DOOR' and r['k'] not in gone}
    inside = [k for k in inside if k not in kept]
    if look:
        return {'things': len(out), 'interiors': len(inside), 'name': town.title()}
    for ck, rk in out:
        c = p.cells.get(ck)
        if c and rk in (c.get('refs') or {}):
            c['refs'].pop(rk)
            p.town_parts.pop(rk, None)
    for k in inside:
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)
    commit(db, 'Removed the town %s: %d things and %d interiors' % (town.title(), len(out), len(inside)))
    return {'things': len(out), 'interiors': len(inside), 'name': town.title()}


CLEARABLE = re.compile(r'tree|flora|plant|bush|shrub|grass|fern|log|stump|root|kelp|weed|reed|rock|boulder|stone_|mushroom|'
                       r'kollop|comberry|wickwheat|saltrice|heather|scathecraw|timsa|bittergreen|marshmerrow|coda|hackle', re.I)
NOT_CLEARABLE = re.compile(r'wall|house|door|tower|bridge|stair|cave|ruin|_x_|_in_|platform|planter', re.I)
CLEAR_PAD = 160                # (round each plot, and this far either side of the wall's line, the ground is cleared)


def _clear_ground(db, plan, W):
    """The plants, trees and loose rocks standing on the town's plots, its streets and the wall's line taken away, as
    the game's towns stand on cleared ground: on the generated forests of Tamriel.esm a town went up with trees
    through its houses, its streets and its wall (the town practice of 2026-10-31). Things of the mod's own go;
    another plugin's are marked deleted in the mod, so one Undo brings them all back. The count."""
    import editing
    import townplan
    rects = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    roads = {tuple(r) for r in plan.get('roads') or ()}
    wall = (W or {}).get('outline') or []
    segs = [(wall[i], wall[(i + 1) % len(wall)]) for i in range(len(wall))] if wall else []
    pts = [p_ for r in rects for p_ in r] + [((x + 0.5) * townplan.PATCH, (y + 0.5) * townplan.PATCH) for x, y in roads] + list(wall)
    if not pts:
        return 0

    def seg_d(px, py, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        return math.hypot(px - (a[0] + dx * t), py - (a[1] + dy * t))

    def on_town(x, y, rad=8.0):
        # (rad: half the thing's own size, so a big boulder whose middle is clear but whose side reaches a house goes too)
        if (int(x // townplan.PATCH), int(y // townplan.PATCH)) in roads:
            return True
        for r in rects:
            if townplan._overlap(_shrink_rect(r, -CLEAR_PAD), [(x - rad, y - rad), (x + rad, y - rad), (x + rad, y + rad), (x - rad, y + rad)]):
                return True
        return any(seg_d(x, y, a, b) <= CLEAR_PAD + 120 + rad for a, b in segs)

    def rad_of(r):
        b = r.get('b')
        if not b:
            return 8.0
        return max(8.0, 0.5 * max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0))
    mine = db.project.plugin.lower()
    n = 0
    xs = [p_[0] for p_ in pts]
    ys = [p_[1] for p_ in pts]
    for gx in range(int(math.floor(min(xs) / 8192.0)), int(math.floor(max(xs) / 8192.0)) + 1):
        for gy in range(int(math.floor(min(ys) / 8192.0)), int(math.floor(max(ys) / 8192.0)) + 1):
            key = '#%d,%d' % (gx, gy)
            m = mapdata.cellmap(db, key)
            # (by name alone: Tamriel.esm's trees and boulders are big enough to count as architecture)
            hits = [r for r in m.get('refs') or () if r.get('type') in ('STAT', 'CONT') and CLEARABLE.search(r['id'])
                    and not NOT_CLEARABLE.search(r['id']) and on_town(r['p'][0], r['p'][1], rad_of(r))]
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


TERRACE_BLEND = 320            # (a terrace fades back into the land round it over this far, or TERRACE_FADE times its rise)
TERRACE_FADE = 3.0             # (a cosine fade is steepest at its middle, pi/2 times its mean: 3x keeps that under 30 degrees)
TERRACE_BLEND_MAX = 1024       # (a 256 rise faded over 320 left banks of 40-60 degrees between houses, 2026-11-01)


TERRACE_CUT_IN = 768           # (inside a plot's own outline the ground is cut down this far at most)
TERRACE_STEP = 0.5             # neighbouring terraces differ by at most this times the ground between them (about 27°)
TERRACE_NEAR = 600             # (terraces this near each other are neighbours)
TERRACE_GIVE = 128             # (and a terrace moves at most this from its own door's ground for them)


def _terrace_steps(areas):
    """[(rect, level)] with neighbouring levels drawn together: each plot levelled to its own door left two joined
    houses 200-500 apart in height with a gap of 40-200 between them, a cliff no fade could soften (the town practice
    of 2026-11-01: plot levelling took the steep ground of a town from 1.2% to 3.7%)."""
    def gap(a, b):
        return min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in a for q in b)
    zs = [z for _r, z in areas]
    z0 = list(zs)
    pairs = []
    for i in range(len(areas)):
        for j in range(i + 1, len(areas)):
            d = gap(areas[i][0], areas[j][0])
            if d < TERRACE_NEAR:
                pairs.append((i, j, max(32.0, TERRACE_STEP * d)))
    for _round in range(30):
        moved = False
        for i, j, allow in pairs:
            dz = zs[i] - zs[j]
            if abs(dz) > allow + 1:
                fix = (abs(dz) - allow) / 2.0 * (1 if dz > 0 else -1)
                # (each at most TERRACE_GIVE from its own door's ground: further, and on a hillside the plot itself
                # came out sloped under the land's own limit)
                ni = max(z0[i] - TERRACE_GIVE, min(z0[i] + TERRACE_GIVE, zs[i] - fix))
                nj = max(z0[j] - TERRACE_GIVE, min(z0[j] + TERRACE_GIVE, zs[j] + fix))
                if abs(ni - zs[i]) + abs(nj - zs[j]) > 0.5:
                    zs[i], zs[j] = ni, nj
                    moved = True
        if not moved:
            break
    return [(r, z) for (r, _z), z in zip(areas, zs)]


def _terrace(db, plan, W, skip=()):
    """Each plot's ground evened towards the height in front of its door, by at most townplan.TERRACE_TOL, fading back into
    the land round it, before its building goes down: the game's builders terraced their hillside towns, and a plot
    refused for uneven ground left a hill town of a few buildings far apart (the user, 2026-10-31: towns "dense or wide
    according to their culture"; the land may be reshaped within tolerance). What else stands there follows the ground."""
    import townwalls
    wg = plan.get('_wall_guard') or []
    import landscape
    import townplan
    tol = townplan.TERRACE_TOL
    street_ground = plan.get('_street_ground') or set()
    areas = []
    for q in plan['plots']:
        if not q.get('b') or not q.get('rect') or not q.get('door'):
            continue
        if W and W.get('outline') and not all(townwalls_inside(W, p_) for p_ in q['rect']):
            continue
        c, sn, _yaw = _frame(q['face'])
        fx, fy = _world(q['door'][0], q['door'][1], c, sn, 0.0, -120.0)
        gz = mapdata.terrain_z(db, fx, fy)
        if gz is None or gz < 0:
            continue
        areas.append(([tuple(p_) for p_ in q['rect']], gz))
    if not areas:
        return 0
    areas = _terrace_steps(areas)
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    xs = [x for r, _z in areas for x, _y in r]
    ys = [y for r, _z in areas for _x, y in r]

    def inside(px, py, r):
        sgn = None
        for i in range(len(r)):
            x1, y1 = r[i]
            x2, y2 = r[(i + 1) % len(r)]
            cr = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
            if abs(cr) < 1e-9:
                continue
            if sgn is None:
                sgn = cr > 0
            elif (cr > 0) != sgn:
                return False
        return True

    def dist(px, py, r):
        if inside(px, py, r):
            return 0.0
        best = 1e18
        for i in range(len(r)):
            ax, ay = r[i]
            bx, by = r[(i + 1) % len(r)]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            best = min(best, math.hypot(px - (ax + dx * t), py - (ay + dy * t)))
        return best
    new_h, before = {}, {}
    for gx in range(int(math.floor((min(xs) - TERRACE_BLEND_MAX) / G)), int(math.floor((max(xs) + TERRACE_BLEND_MAX) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - TERRACE_BLEND_MAX) / G)), int(math.floor((max(ys) + TERRACE_BLEND_MAX) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            near = [(r, z) for r, z in areas if min(x for x, _y in r) - TERRACE_BLEND_MAX <= gx * G + G and max(x for x, _y in r) + TERRACE_BLEND_MAX >= gx * G
                    and min(y for _x, y in r) - TERRACE_BLEND_MAX <= gy * G + G and max(y for _x, y in r) + TERRACE_BLEND_MAX >= gy * G]
            if not near:
                continue
            h = list(L['h'])
            changed = False
            for j in range(N):
                for i in range(N):
                    x, y = gx * G + i * step, gy * G + j * step
                    n = j * N + i
                    z0 = h[n]
                    if (x, y) in street_ground:
                        continue                  # (a levelled street's own ground)
                    if wg and any(townwalls._in_poly(k_, x, y) for k_ in wg):
                        continue                  # (a wall already standing, another make's: its ground stays)
                    ws, inside_z, miss = [], None, 1.0
                    for r, z in near:
                        d = dist(x, y, r)
                        # (under the building itself the hill is cut away to its floor, deeper than round it: a barn
                        # stood sunk 200 into the hillside, its goods buried, lab sg1; the user's house "with the
                        # ground climbing up its walls on the high side")
                        want = max(z0 - (TERRACE_CUT_IN if d <= 0 else tol), min(z0 + tol, z))
                        reach = max(TERRACE_BLEND, min(TERRACE_BLEND_MAX, TERRACE_FADE * abs(want - z0)))
                        if d >= reach:
                            continue
                        if d <= 0:
                            inside_z = want
                            break
                        w = 0.5 + 0.5 * math.cos(math.pi * d / reach)
                        ws.append((w, want))
                        miss *= 1.0 - w
                    if inside_z is not None:
                        nz = inside_z
                    elif ws:
                        # (between plots, all of them by how near: the nearest alone flipped from one plot's level to the
                        # next's halfway, and where neither reached the ground stayed low, a trench between two raised
                        # houses, the town practice of 2026-11-01. How strongly: as near as the plots together are)
                        tw = sum(w for w, _z in ws)
                        nz = z0 + (1.0 - miss) * (sum(w * z for w, z in ws) / tw - z0)
                    else:
                        continue
                    if abs(nz - z0) >= 1:
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


SMOOTH_R = 2                   # the ground inside a town is evened over this many land vertices either way (256)
SMOOTH_PASSES = 2
SMOOTH_BLEND = 384             # (and fades back into the land this far outside the town)


def _smooth_hull(db, plan, W, skip=()):
    """The ground between a town's houses evened out: every land vertex inside the town (the wall's outline, else
    the hull of its plots and streets) drawn to the mean of the ground round it, the levelled streets and the plots'
    terraces left as they are so the land flows between them; fading back into the land outside. (The streets and
    plots were level but the ground between kept the raised land's every bump: "the terrain is still rather lumpy
    ... the end result still looks messy", the user's Nargorewatch, 2026-11-03.) What stands there follows the
    ground. Cells changed."""
    import townwalls
    wg = plan.get('_wall_guard') or []
    import landscape
    import townplan
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    hull = list((W or {}).get('outline') or ())
    if len(hull) < 3:
        pts = [tuple(p_) for q in plan['plots'] if q.get('b') and q.get('rect') for p_ in q['rect']]
        pts += [tuple(p_) for st in plan.get('streets') or () for p_ in st.get('pts') or ()]
        hull = townplan._hull(pts) if len(pts) >= 3 else []
    if len(hull) < 3:
        return 0
    keep = set(plan.get('_street_ground') or ())
    rects = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]

    def edge_d(px, py):
        best = 1e18
        for i in range(len(hull)):
            (ax, ay), (bx, by) = hull[i], hull[(i + 1) % len(hull)]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            best = min(best, math.hypot(px - (ax + dx * t), py - (ay + dy * t)))
        return best
    xs = [p_[0] for p_ in hull]
    ys = [p_[1] for p_ in hull]
    cells = [(gx, gy) for gx in range(int(math.floor((min(xs) - SMOOTH_BLEND) / G)), int(math.floor((max(xs) + SMOOTH_BLEND) / G)) + 1)
             for gy in range(int(math.floor((min(ys) - SMOOTH_BLEND) / G)), int(math.floor((max(ys) + SMOOTH_BLEND) / G)) + 1)]
    H = {}
    for gx, gy in cells:
        L = mapdata.land(db, gx, gy)
        if L and L.get('h'):
            H[(gx, gy)] = list(L['h'])
    if not H:
        return 0
    before = {k: list(v) for k, v in H.items()}

    def at(gx, gy, i, j):
        # (the vertex i, j of cell gx, gy, carried into the neighbour when off the edge; None off the known land)
        while i < 0:
            gx -= 1; i += N - 1
        while i > N - 1:
            gx += 1; i -= N - 1
        while j < 0:
            gy -= 1; j += N - 1
        while j > N - 1:
            gy += 1; j -= N - 1
        h = H.get((gx, gy))
        return None if h is None else h[j * N + i]
    R = SMOOTH_R
    wts = {(di, dj): 1.0 / (1.0 + math.hypot(di, dj)) for di in range(-R, R + 1) for dj in range(-R, R + 1)}
    changed = set()
    for _pass in range(SMOOTH_PASSES):
        new = {}
        for (gx, gy), h in H.items():
            out = list(h)
            touched = False
            for j in range(N):
                for i in range(N):
                    x, y = gx * G + i * step, gy * G + j * step
                    z0 = h[j * N + i]
                    if z0 < 0 or (x, y) in keep or (wg and any(townwalls._in_poly(k_, x, y) for k_ in wg)):
                        continue
                    inside = townplan._inside(hull, x, y)
                    if not inside:
                        d = edge_d(x, y)
                        if d >= SMOOTH_BLEND:
                            continue
                        share = 0.5 + 0.5 * math.cos(math.pi * d / SMOOTH_BLEND)
                    else:
                        share = 1.0
                    if any(townplan._inside(r, x, y) for r in rects):
                        continue              # (a plot's own terrace)
                    tot = wsum = 0.0
                    for (di, dj), w in wts.items():
                        v = at(gx, gy, i + di, j + dj)
                        if v is None or v < 0:
                            continue
                        tot += w * v
                        wsum += w
                    if not wsum:
                        continue
                    nz = z0 + share * (tot / wsum - z0)
                    if abs(nz - z0) >= 1:
                        out[j * N + i] = nz
                        touched = True
            if touched:
                new[(gx, gy)] = out
                changed.add((gx, gy))
        for k, v in new.items():
            H[k] = v
    for gx, gy in sorted(changed):
        after = landscape.write(db, gx, gy, H[(gx, gy)], None, None, around=landscape.around_of(db, gx, gy, {k: H[k] for k in changed}))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if changed:
        db.sync_project()
    return len(changed)


STREET_TOL = 256               # a street's ground moves at most this from the land's
STREET_SMOOTH = 768            # (its height along it the land's across its width, averaged this far either way)
STREET_EDGE = 64               # level across its width and this beyond
STREET_BLEND = 384             # fading back into the land over this


def _street_profile(db, st, pinned):
    """[(x, y, z)] every 128 along a street: the land's middle height across its width, smoothed along it and kept
    within STREET_TOL of the land; where an earlier street levelled the ground (a junction), its level."""
    pts = st.get('pts') or []
    hw = (st.get('w') or 512) / 2.0
    raw = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, by - ay)
        if L < 1:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        for k in range(int(L // 128)):
            x, y = ax + ux * k * 128, ay + uy * k * 128
            zs_ = sorted(z for z in (mapdata.terrain_z(db, x - uy * a * hw, y + ux * a * hw) for a in (-1, -0.5, 0, 0.5, 1)) if z is not None)
            raw.append((x, y, zs_[len(zs_) // 2] if zs_ else None))
    if len(pts) >= 2 and raw:
        x, y = pts[-1]
        z = mapdata.terrain_z(db, x, y)
        raw.append((x, y, z))
    n = len(raw)
    W = max(1, int(STREET_SMOOTH // 128))
    out = []
    for i, (x, y, z0) in enumerate(raw):
        if z0 is None or z0 < 0:
            out.append((x, y, None))          # (across water: left as it is)
            continue
        pz = pinned(x, y)
        if pz is not None:
            out.append((x, y, pz))
            continue
        ws = [(1.0 - abs(j - i) / float(W + 1), raw[j][2]) for j in range(max(0, i - W), min(n, i + W + 1)) if raw[j][2] is not None and raw[j][2] >= 0]
        z = sum(w * v for w, v in ws) / sum(w for w, _ in ws)
        out.append((x, y, max(z0 - STREET_TOL, min(z0 + STREET_TOL, z))))
    return out


def _level_streets(db, plan, skip=()):
    """Each street level across its width and running smoothly along it (the land's own grade, its humps and dips
    taken out), main street first, fading back into the land round it; what stands there follows the ground. A
    street that climbs climbs as the land does, smoothly. (The streets followed the land square by square: they
    tilted sideways and humped between the houses, the user's Tessellated Shores, 2026-11-01.) Before the terraces,
    so each plot's door front stands on the street's level. Cells changed."""
    import landscape
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    streets = sorted(plan.get('streets') or (), key=lambda s: (not s.get('main'), bool(s.get('lane') or s.get('court'))))
    target = {}                               # (gx, gy, i, j): (z, weight)

    def vkey(x, y):
        return (int(math.floor(x / G)), int(math.floor(y / G)), int(round((x % G) / step)), int(round((y % G) / step)))

    def pinned(x, y):
        t = target.get(vkey(x, y))
        return t[0] if t and t[1] >= 0.99 else None
    for st in streets:
        prof = _street_profile(db, st, pinned)
        good = [(x, y, z) for x, y, z in prof if z is not None]
        if len(good) < 2:
            continue
        hw = (st.get('w') or 512) / 2.0
        reach = hw + STREET_EDGE + STREET_BLEND
        xs, ys = [p[0] for p in good], [p[1] for p in good]
        mine = {}
        for vx in range(int(math.floor((min(xs) - reach) / step)), int(math.floor((max(xs) + reach) / step)) + 2):
            for vy in range(int(math.floor((min(ys) - reach) / step)), int(math.floor((max(ys) + reach) / step)) + 2):
                x, y = vx * step, vy * step
                # (the nearest point of the profile line: between two samples, its height between theirs)
                best = None
                for (ax, ay, az), (bx, by, bz) in zip(prof, prof[1:]):
                    if az is None or bz is None:
                        continue
                    dx, dy = bx - ax, by - ay
                    L2 = dx * dx + dy * dy
                    t = 0.0 if not L2 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
                    d = math.hypot(x - ax - dx * t, y - ay - dy * t)
                    if best is None or d < best[0]:
                        best = (d, az + (bz - az) * t)
                if best is None or best[0] >= reach:
                    continue
                d, z = best
                w = 1.0 if d <= hw + STREET_EDGE else 0.5 + 0.5 * math.cos(math.pi * (d - hw - STREET_EDGE) / STREET_BLEND)
                k = vkey(x, y)
                old = target.get(k)
                if old is None or w > old[1] + 1e-6:
                    mine[k] = (z, w)
        target.update(mine)
    # (the street's own ground kept by what follows: the terraces faded over the streets between plots and put their
    # humps back, lab ja2)
    plan['_street_ground'] = {(gx * G + i * step, gy * G + j * step) for (gx, gy, i, j), (z, w) in target.items() if w >= 0.99}
    if not target:
        return 0
    cells_ = set()
    for (gx, gy, i, j) in target:
        cells_.add((gx, gy))
        if i == 0:
            cells_.add((gx - 1, gy))
        if j == 0:
            cells_.add((gx, gy - 1))
        if i == 0 and j == 0:
            cells_.add((gx - 1, gy - 1))
    new_h, before = {}, {}
    for gx, gy in cells_:
        L = mapdata.land(db, gx, gy)
        if not L or not L.get('h'):
            continue
        h = list(L['h'])
        changed = False
        for j in range(N):
            for i in range(N):
                # (each cell's own edge vertices by the world spot: a cell's last row is its neighbour's first)
                zw = target.get(vkey(gx * G + i * step, gy * G + j * step))
                if zw is None:
                    continue
                n = j * N + i
                z0 = h[n]
                if z0 < 0:
                    continue                  # (water: no street raised out of it)
                nz = z0 + zw[1] * (zw[0] - z0)
                if abs(nz - z0) >= 1:
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


def townwalls_inside(W, p):
    import townwalls
    return townwalls._inside(W['outline'], p)


def _in_rect(r, x, y):
    """Is the point inside a convex plot outline (any winding)?"""
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


WALL_GUARD = 320               # (the ground this far round a town wall's pieces is never cut by a building's ground fit or
                               # the floor pass: a house's landing by the wall cut 500 from under the wall and its gate on the
                               # user's island, the wall and gate doors left hanging over a trench, 2026-11-06)


def _uncover(db, plan, skip=(), guard=()):
    """No ground over a building's floor inside its own plot: where a later step (the wall's fill, a neighbour's landing,
    a terrace moved for its neighbours) raised the hill back over a wall, it is cut to the door's sill again. (The
    user, 2026-11-06: "some of these homes are half buried", their doors clipped into the dirt; measured on their
    island town, one house in ten had ground over its sill at a corner, the worst by 300.) The land points inside
    the plot alone; the blend to the land round it is the terraces'. The points moved."""
    import landscape
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    plots = [(q['rect'], q['door_z'], q) for q in plan['plots'] if q.get('b') and q.get('rect') and q.get('door_z') is not None]
    if not plots:
        return 0
    memo = {}
    C = by_uid(catalog(db))

    def footprint(q):
        # (the building's own pieces' boxes in the world, a step wider: a house wider than its plot kept a buried corner,
        # lab w81; its windows, doors and openings left out)
        c, sn, yaw = _frame(q['face'])
        dx, dy = q['door']
        out = []
        bb = built(C, q['b'])
        for p_ in (bb['m']['fpieces'] if bb else ()):
            low = p_['id'].lower()
            if p_.get('door') or OPENING.search(low) or re.search(r'win|door|chimney|dormer|balcony|awning', low):
                continue
            if low not in memo:
                ri = db.resolve_id(p_['id'])
                memo[low] = (mapdata.object_bounds(db, ri) if ri is not None else None)
            b = memo[low]
            if not b:
                continue
            sc = p_.get('s') or 1.0
            rz = (p_['rz'] + yaw) % (2 * math.pi)
            cr, sr = math.cos(rz), math.sin(rz)
            wx, wy = _world(dx, dy, c, sn, p_['x'], p_['y'])
            quad = []
            for lx, ly in ((b[0] - 32, b[1] - 32), (b[3] + 32, b[1] - 32), (b[3] + 32, b[4] + 32), (b[0] - 32, b[4] + 32)):
                quad.append((wx + (lx * cr + ly * sr) * sc, wy + (-lx * sr + ly * cr) * sc))
            out.append(quad)
        return out

    def in_quad(px, py, r):
        sgn = None
        for i in range(len(r)):
            x1, y1 = r[i]
            x2, y2 = r[(i + 1) % len(r)]
            cr = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
            if abs(cr) < 1e-9:
                continue
            if sgn is None:
                sgn = cr > 0
            elif (cr > 0) != sgn:
                return False
        return True
    new_h, before, moved = {}, {}, 0
    for r, dz, q in plots:
        quads = [r] + footprint(q)
        xs = [p[0] for qd in quads for p in qd]
        ys = [p[1] for qd in quads for p in qd]
        top = dz - 8
        for gx in range(int(math.floor(min(xs) / G)), int(math.floor(max(xs) / G)) + 1):
            for gy in range(int(math.floor(min(ys) / G)), int(math.floor(max(ys) / G)) + 1):
                h = new_h.get((gx, gy))
                if h is None:
                    L = mapdata.land(db, gx, gy)
                    if not L or not L.get('h'):
                        continue
                    h = list(L['h'])
                    before[(gx, gy)] = list(L['h'])
                    new_h[(gx, gy)] = h
                for j in range(N):
                    y = gy * G + j * step
                    if y < min(ys) or y > max(ys):
                        continue
                    for i in range(N):
                        x = gx * G + i * step
                        if x < min(xs) or x > max(xs) or not any(in_quad(x, y, qd) for qd in quads):
                            continue
                        if guard and any(_in_rect(g_, x, y) for g_ in guard):
                            continue
                        n = j * N + i
                        if h[n] > top:
                            h[n] = top
                            moved += 1
    changed = {k: h for k, h in new_h.items() if h != before[k]}
    for (gx, gy), h in changed.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, changed))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if changed:
        db.sync_project()
    return moved


def _fit_ground(db, doors, skip, plots=(), guard=()):
    """The ground fitted to each new building the way the game's meet theirs (groundfit: raised where its foot would
    show a gap, a landing a step under its door; the game never levels the ground under a building), one after another
    so each sees the ground the last left; what else stands on the ground (trees, rocks) follows it. No Undo step."""
    import frombuilding
    import groundfit
    import landscape
    n = 0
    for key, rk in doors:
        try:
            b = frombuilding.building_at(db, key, rk)
            pl = groundfit.plan(db, b)
        except Exception:
            continue
        if not pl:
            continue
        # (the ground inside the other buildings' plots left as it is: one building's landing faded out over its
        # neighbour and filled an open barn 300 deep, its goods buried, lab sg2)
        others = [r for d, r in plots if d != (key, rk)]
        if others or guard:
            G, N = landscape.CELL, landscape.N
            st = G / (N - 1.0)
            for c in pl['cells']:
                old = mapdata.land(db, c['gx'], c['gy']).get('h')
                if not old:
                    continue
                c['h'] = list(c['h'])
                for j in range(N):
                    for i in range(N):
                        n = j * N + i
                        if c['h'][n] != old[n]:
                            x, y = c['gx'] * G + i * st, c['gy'] * G + j * st
                            if any(_in_rect(r, x, y) for r in others):
                                c['h'][n] = old[n]
                            elif c['h'][n] < old[n] and guard and any(_in_rect(g_, x, y) for g_ in guard):
                                c['h'][n] = old[n]       # (never lower under or beside the wall: WALL_GUARD)
        new_h = {(c['gx'], c['gy']): c['h'] for c in pl['cells']}
        for c in pl['cells']:
            gx, gy = c['gx'], c['gy']
            before = mapdata.land(db, gx, gy).get('h')
            after = landscape.write(db, gx, gy, c['h'], None, None, around=landscape.around_of(db, gx, gy, new_h))
            if before:
                landscape._follow_ground(db, gx, gy, before, after, skip)
        db.sync_project()
        n += 1
    return n


_road_tex = {}


def _town_roads(db):
    """[(x, y, culture, {LTEX id: road patches})]: each game town's middle and what its streets are paved with."""
    k = id(db.recs)
    if k not in _road_tex:
        import landscape
        out = []
        for t in townsurvey.survey(db)['towns']:
            if not t['roads'] or not t['buildings']:
                continue
            want = {tuple(int(v) for v in r.split(',')) for r in t['roads']}
            c = {}
            for gx, gy in t['cells']:
                L = landscape.read(db, gx, gy)
                if not L.get('exists') or not L.get('t'):
                    continue
                for n_, tid in enumerate(L['t']):
                    if tid and (gx * 16 + n_ % 16, gy * 16 + n_ // 16) in want:
                        c[tid] = c.get(tid, 0) + 1
            if c:
                bs = t['buildings']
                out.append((sum(b['x'] for b in bs) / len(bs), sum(b['y'] for b in bs) / len(bs), t['culture'], c))
        _road_tex[k] = out
    return _road_tex[k]


def road_texture(db, culture, near=None):
    """The ground texture the culture's own towns pave their streets with (LTEX id): the one its towns nearest the
    new town use (by their road patches, nearer counting more), so a town by Pelagiad gets the Heartland's road, not
    the Gold Coast's dirt the culture's commonest across all its towns."""
    ts = [t for t in _town_roads(db) if t[2] == culture] or         [t for t in _town_roads(db) if t[2] in townsurvey.KIN.get(culture, ())]
    if not ts:
        return None
    if near is not None:
        ts.sort(key=lambda t: math.hypot(t[0] - near[0], t[1] - near[1]))
        ts = ts[:3]
    score = {}
    for i, (_x, _y, _c, c) in enumerate(ts):
        tot = float(sum(c.values()))
        for tid, n in c.items():
            score[tid] = score.get(tid, 0.0) + n / tot / (1 + i)
    return max(score, key=score.get)


PAINT_SHARE = 0.7              # a road square is painted within this share of its street's half-width of the street's line
PAINT_MIN = 256                # (or this, whichever is more)


def _paint_set(plan):
    """The road squares to paint: the plan's own, narrowed to its streets' middles. The ground's texture squares are 512
    across, and a street 300 wide touched two of them: the whole of a street's squares painted made the streets bare
    fields of dirt, a town's road a fifth to a third of it where the game's is a tenth to a fifth (Common 21% vs 7%,
    the town practice of 2026-11-01). Its square whole."""
    rs = {tuple(r) for r in plan.get('roads') or ()}
    S = plan.get('streets') or []
    if not S:
        return rs
    keep = set()
    for st in S:
        r = max(PAINT_MIN, (st.get('w') or 0) / 2.0 * PAINT_SHARE)
        pts = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay) or 1.0
            for k in range(int(L // 64) + 1):
                x, y = ax + (bx - ax) * k * 64 / L, ay + (by - ay) * k * 64 / L
                for px in range(int((x - r) // 512), int((x + r) // 512) + 1):
                    for py in range(int((y - r) // 512), int((y + r) // 512) + 1):
                        if (px, py) in rs and math.hypot((px + 0.5) * 512 - x, (py + 0.5) * 512 - y) <= r:
                            keep.add((px, py))
    sq = plan.get('square')
    if sq:
        keep |= {p for p in rs if math.hypot((p[0] + 0.5) * 512 - sq[0], (p[1] + 0.5) * 512 - sq[1]) <= sq[2]}
    keep |= {tuple(p) for p in plan.get('paint_extra') or ()}          # (the roads out through the wall's gates)
    # (squares meeting only at a corner joined by one of the two between: a slanting street painted as a staircase of
    # corners blurred into a smudge, the user's Griffbarrow from above; 4.6% of our squares, the game's 0.3%)
    for p in sorted(keep):
        for i, j in ((1, 1), (1, -1)):
            q = (p[0] + i, p[1] + j)
            if q in keep and (p[0] + i, p[1]) not in keep and (p[0], p[1] + j) not in keep:
                a, b = (p[0] + i, p[1]), (p[0], p[1] + j)
                keep.add(a if a in rs or b not in rs else b)
    # (and a square or two of ground left alone inside the road, no plot on it, painted: at a slanting junction a bare
    # square ringed by road read as a loop round nothing, small rings 1.8 a hundred road squares, the game's 0.55)
    import townplan
    plots = [q['rect'] for q in plan.get('plots') or () if q.get('b') and q.get('rect')]
    for p in sorted(keep):
        for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            h = (p[0] + i, p[1] + j)
            if h in keep:
                continue
            ring = {h} | ({(h[0] + i, h[1] + j)} if (h[0] + i, h[1] + j) not in keep else set())
            near = {(a[0] + x, a[1] + y) for a in ring for x, y in ((1, 0), (-1, 0), (0, 1), (0, -1))} - ring
            if near <= keep and not any(any(townplan._inside(r, (a[0] + 0.5) * 512, (a[1] + 0.5) * 512) for r in plots) for a in ring):
                keep |= ring
    return keep or rs


SNOW = re.compile(r'snow|glacier|_ice|ice_|frost', re.I)
SNOW_TOWN = 0.6                # (a town whose ground is mostly snow keeps it: a Solstheim village stands in the snow)


def _unsnow(db, plan):
    """The region's snow off the town's own ground: its plots and streets, levelled, had the high land's snow paint
    left on them, white slabs against the houses (the user's Tessellated Shores video, 2026-11-01). Each snow square
    there is painted with the commonest other ground of the town's squares. No Undo step. Squares painted."""
    import landscape
    want = {tuple(r) for r in plan.get('roads') or ()}
    for q in plan['plots']:
        if not q.get('b') or not q.get('rect'):
            continue
        xs, ys = [p[0] for p in q['rect']], [p[1] for p in q['rect']]
        for px in range(int((min(xs) - 128) // 512), int((max(xs) + 128) // 512) + 1):
            for py in range(int((min(ys) - 128) // 512), int((max(ys) + 128) // 512) + 1):
                want.add((px, py))
    by = defaultdict(list)
    for px, py in want:
        by[(px // 16, py // 16)].append((px % 16) + (py % 16) * 16)
    Ls, count, snowy = {}, Counter(), 0
    for (gx, gy), idx in by.items():
        L = landscape.read(db, gx, gy)
        if not L.get('exists') or not L.get('t'):
            continue
        Ls[(gx, gy)] = L
        tex = L.get('tex') or {}
        for i in idx:
            t = L['t'][i]
            if t and SNOW.search(t + ' ' + (tex.get(t) or '')):
                snowy += 1
            elif t:
                count[t] += 1
    tot = snowy + sum(count.values())
    if not snowy or not count or snowy >= SNOW_TOWN * tot:
        return 0
    tid = count.most_common(1)[0][0]
    n = 0
    for (gx, gy), L in Ls.items():
        tex = L.get('tex') or {}
        t = list(L['t'])
        hit = False
        for i in by[(gx, gy)]:
            if t[i] and SNOW.search(t[i] + ' ' + (tex.get(t[i]) or '')):
                t[i] = tid
                hit = True
                n += 1
        if hit:
            landscape.write(db, gx, gy, None, t, None)
    if n:
        db.sync_project()
    return n


def _paint_roads(db, plan):
    """The plan's streets painted with the culture's road texture. No Undo step. The patches painted."""
    import landscape
    if not plan.get('roads'):
        return 0
    rs = sorted(_paint_set(plan))
    tid = road_texture(db, plan['culture'], (sum(r[0] for r in rs) / len(rs) * 512 + 256, sum(r[1] for r in rs) / len(rs) * 512 + 256))
    if not tid:
        return 0
    by = {}
    for px, py in rs:
        by.setdefault((px // 16, py // 16), []).append((px % 16) + (py % 16) * 16)
    n = 0
    for (gx, gy), idx in by.items():
        L = landscape.read(db, gx, gy)
        if not L.get('exists') or not L.get('t'):
            continue
        t = list(L['t'])
        for i in idx:
            t[i] = tid
            n += 1
        landscape.write(db, gx, gy, None, t, None)
    db.sync_project()
    return n
