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


_CAT_LOCK = __import__('threading').Lock()


def game_catalog(db):
    """[{'key': main piece, 'culture', 'kind', 'w', 'd', 'fp', 'uses', 'm': module}] for every whole building the game
    has outside a door. One at a time: the town's plan and the cultures' list both built it at once, reading every
    building's meshes twice, 36 s for the first town of a session (the user's stall log, 2026-11-09)."""
    with _CAT_LOCK:
        return _game_catalog(db)


def _game_catalog(db):
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
        if _upper_door(db, m, memo):
            continue
        # (the top of a tower stack, learnt as a building for the door on its platform: set on the ground it stood
        # sunk to its roof, the user's island town, test3. A stack part whose module holds no base piece)
        if STACK_PART.search(m['main']) and not any(BASE_PART.search(p_['id']) for p_ in m['fpieces']):
            continue
        # (a Telvanni turret is a tower's top: without a tower body or a stem under it in its module, it stood sunk a
        # thousand units so its door met the ground, the style practice 2026-11-07)
        if re.search(r'turret', m['main'], re.I) and not any(re.search(r'tower_|stem|spiralramp', p_['id'], re.I) and p_ is not m['fpieces'][0]
                                                             and p_['id'].lower() != m['main'].lower() for p_ in m['fpieces']):
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
        out.append({'key': m['main'], 'culture': cult, 'kind': kind, 'w': round(w), 'd': round(d), 'fp': [round(v) for v in fp],
                    'uses': m.get('uses', 1), 'm': m, 'fort': fort, 'keep': keep, 'h': round(_height(db, m['main'], memo)),
                    # (by the game building it was learnt from, not its place in the list: the list changes when the
                    # strays arrive, and a plan made before would have built other buildings than it showed)
                    'uid': '%s#%s' % (m['main'].lower(), ((m.get('examples') or [''])[0] or str(len(out))).lower())})
    seen = set()
    for c in out:
        if c['uid'] in seen:
            c['uid'] += '#%d' % len(seen)
        seen.add(c['uid'])
    _mark_landmarks(out)
    _cat[key] = (out, st)
    _lone_save()
    return out


RUIN = re.compile(r'ruin|broken|collapsed|rubble', re.I)
LANDMARK_SET = 8               # (a data-file set of this many `_x_` buildings or fewer, all of no town kind, standing in LANDMARK_TOWNS game
LANDMARK_TOWNS = 2             # places or fewer, is a set made for one spot: the circus tents, six at the Tourney of the Ebon Hill and two in Anvil's market)
LANDMARK_H = 1600              # (a data file's one-off building this tall is a landmark: Old Ebonheart's chapel, 1643 tall
                               # among Common houses of 750, stood as a lone keep tower among a Common town's houses (the user
                               # 2026-11-06); the `_x_` rule that took it out took every Tamriel Data exterior set with it,
                               # Indoril to no building at all, 2026-11-07. Narsis's 3,000-tall towers, the Indoril chapels,
                               # Velothi's buttress towers are landmarks; Necrom's houses and Velothi's 1,340 houses are not)


def _mark_landmarks(out):
    """'landmark': True on a data file's building (its `_x_` sets) placed once or twice in the game and LANDMARK_H tall:
    a town gets one at most, and it costs on a house, shop or plain plot."""
    for c in out:
        c['landmark'] = bool(re.search(r'_x_', c['key'], re.I)) and (c.get('uses') or 1) <= 2 and (c.get('h') or 0) >= LANDMARK_H
    # (a data file's set made for one spot: a few `_x_` buildings of no town kind, all standing in one game town, the
    # circus's tents (t_com_setcir, six, Old Ebonheart's fairground): each once a town at most. Firuhn, a Common town of
    # 2614s, had 21 of them on its house plots, the user 2026-11-07)
    fam = {}
    for c in out:
        if re.search(r'_x_', c['key'], re.I):
            f = fam.setdefault(family(c['key']), {'n': 0, 'towns': set(), 'kinds': set()})
            f['n'] += 1
            f['kinds'].add(c['kind'])
            for e in (c['m'].get('examples') or [])[:3]:
                f['towns'].add(str(e).split(',')[0].strip().lower())
    spot = {f for f, v in fam.items() if v['n'] <= LANDMARK_SET and len(v['towns']) <= LANDMARK_TOWNS and v['kinds'] <= {'other'}}
    for c in out:
        if family(c['key']) in spot:
            c['landmark'] = True
            c['spot'] = family(c['key'])             # (one building of the set a town, fit)
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


UPPER_DOOR = 300               # a building's own door this far under its front door: the front one is an upper door


def _upper_door(db, m, memo):
    """Is the module's front door an upper door of its building: another door of it stands UPPER_DOOR or more lower?
    Old Ebonheart's Grand Chapel was learnt twice, from its doors on the ground and from its towers' door off the wall
    walk, 573 over them; set by that one, the chapel stood sunk to its turret in the user's Senchal (2026-11-11: "tower
    pieces as standalone buildings, the balconies pressed against the ground"). The building stays, by its ground door."""
    front = min((p_ for p_ in m['fpieces'] if p_.get('door')), key=lambda p_: p_['x'] ** 2 + p_['y'] ** 2 + (p_['z'] * 3) ** 2, default=None)
    if front is None:
        return False
    for p_ in m['fpieces']:
        if p_ is front or re.search(r'trap|hatch|marker|frame|gate|cellar', p_['id'], re.I) or p_['z'] > front['z'] - UPPER_DOOR:
            continue
        k = ('type', p_['id'].lower())
        if k not in memo:
            ri = db.resolve_id(p_['id'])
            memo[k] = db.recs[ri][0] if ri is not None else None
        if memo[k] == 'DOOR':
            return True
    return False


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
DOOR_BEHIND = 120              # (straight out of the door and into it: its own wall, curved or set back. At 800 a house 300
                               # behind a door held it, and the door stood free in the street with its step, an interior behind
                               # it: the user's Senchal, 2026-11-11, "MAKE SURE THESE DOORS ARE ON BUILDINGS")
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
    # (the Workshop's own cache folder, beside projects: under app\ the Setup removed it with the program files at every
    # install, and the strays, town dressing and town life were learnt again, minutes each, the user's 2026-11-09)
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'lonedoors_%s_v6.json' % sig)


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
CHAPEL = re.compile(r'setchapel(?!.*tower)|_x_temple|oe_chapel|velothi_temple', re.I)


def is_chapel(b):
    """A plot's building (its 'key', 'kind') is a chapel or a temple outside: whatever plot it stands on, its inside is
    one (the user walked into a chapel that was a home inside, 2026-11-09)."""
    return bool(b) and (b.get('kind') == 'temple' or bool(CHAPEL.search(b.get('key') or '')))
NUDGES = ((0, 0), (-160, 0), (160, 0), (0, 160), (-320, 0), (320, 0), (0, 320), (-160, 160), (160, 160))
# (the Imperial Cult's own chapels stand in these looks' towns too: Brina Cross, Charach and Anvil's small chapels)
CHAPELS_OF = {'Anvil': 'Imperial', 'Gold Coast': 'Imperial'}
OUTBUILDING = re.compile(r'barn|stable|windmill|silo', re.I)     # (never a home, a shop or a chapel inside)
KIND_NEAR = {('house', 'other'): 0.0, ('other', 'house'): 0.0, ('manor', 'house'): 0.5, ('shop', 'house'): 0.6, ('tavern', 'shop'): 0.6}


def looks(db, culture):
    """[{'id': family, 'label': the game town it is known by, 'buildings', 'towns'}]: the building families a town of
    this culture can be built in, each a lead family of fit (a family that leads one of the culture's game towns):
    Hlaalu's Balmora (ex_hlaalu) and Narsis (t_de_sethla). Fewer than two: no choice to offer. (The style review,
    2026-11-07: Hlaalu towns were Balmora, never Narsis; the lead drawn by towns led gave the Narsis set one time in 18.)"""
    C = catalog(db)
    pool = [c for c in C if c['culture'] == culture]
    own = Counter(family(c_['key']) for c_ in pool)
    M = family_mix(db)
    towns = [t for t in townsurvey.survey(db)['towns'] if t['culture'] == culture and t.get('name') and t['buildings']]
    fams = [f for f, o in M.items() if o['cultures'].get(culture) and own.get(f, 0) >= 4]
    # (each look named for a town of its own: the rarest family first takes the town where it is most itself (its
    # buildings there squared over the town's: Narsis for t_de_sethla, 62 of 193), the next skips the towns taken
    # (ex_hlaalu: Balmora, 41 of 42, before Narsis's 102 of 193 and Bal Foyen's 47 of 68); the name is the cell most of
    # those buildings stand in (Ald-ruhn's are grouped with Buckmoth Legion Fort's cells and named for the fort))
    taken, out = set(), []
    for f in sorted(fams, key=lambda f: (M[f]['cultures'][culture], own[f])):
        best, score = None, 0.0
        for k, t in enumerate(towns):
            if k in taken:
                continue
            mine = [b for b in t['buildings'] if b.get('main') and family(b['main']) == f]
            if len(mine) < 3:
                continue
            sc = len(mine) ** 2 / float(len(t['buildings']))
            if sc > score:
                best, score = (k, mine), sc
        if not best:
            continue
        taken.add(best[0])
        cells = Counter()
        for b in best[1]:
            nm = (mapdata.cell_info(db, '#%d,%d' % (math.floor(b['x'] / 8192.0), math.floor(b['y'] / 8192.0))) or {}).get('name') or ''
            if nm:
                cells[nm.split(',')[0].strip()] += 1
        label = cells.most_common(1)[0][0] if cells else towns[best[0]]['name'].split(',')[0].strip()
        out.append({'id': f, 'label': label, 'buildings': own[f], 'towns': M[f]['cultures'][culture]})
    out.sort(key=lambda o: (-o['towns'], -o['buildings']))
    labels = Counter(o['label'] for o in out)
    for o in out:
        if labels[o['label']] > 1:
            o['label'] += ' (%s)' % o['id']
    return out if len(out) >= 2 else []


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
    own = Counter(family(c_['key']) for c_ in pool if c_['culture'] == cult)
    # (towns led, weighed by the family's buildings on offer: by towns alone the Monastery of St. Felms' ex_velothi,
    # one town of 12 temples and towers, led a Velothi town one time in eleven, and its house plots were filled with
    # Dunmer shacks lent by the kin, the style practice 2026-11-07)
    fams = {f: o['cultures'].get(cult, 0) * own[f] for f, o in M.items() if o['cultures'].get(cult) and f in own}
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
        if len(narrow) >= 8 and len(narrow) >= len(pool) / 3:
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
    if CHAPELS_OF.get(cult):
        # (a temple plot in an ordinary building was a tavern inside with one altar, named a chapel: lab th0)
        lend.setdefault('temple', []).extend(c for c in C if c['culture'] == CHAPELS_OF[cult] and c['kind'] == 'temple'
                                             and 'setchapel' in c['key'].lower() and not c.get('landmark'))
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
    spot_used = set()
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
            if c.get('landmark') and q['kind'] in ('house', 'other', 'shop'):
                k = max(k, 4.0)          # (a one-off landmark, a chapel tower, among the houses: _mark_landmarks)
            if OUTBUILDING.search(c['key']):
                k = max(k, 4.0)          # (a barn on a house plot was a home with one barrel in it, lab th0)
            sw, sd = c['w'] / pw, c['d'] / pd
            size = abs(math.log(sw)) + abs(math.log(sd)) + (2.0 * (max(sw, sd) - 1.15) if max(sw, sd) > 1.15 else 0.0)
            fam = 0.6 * -math.log(max(0.02, share.get(family(c['key']), 0.02))) if share else 0.0
            if q['kind'] == 'temple' and CHAPEL.search(c['key']):
                fam = 0.0                # (a chapel is its own set in every town it stands in)
            elif q['kind'] == 'temple' and c['kind'] == 'temple':
                k = 1.0                  # (a plain house the game uses as a chapel: after the chapels, lab th2)
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
            if cand.get('landmark') and used.get(cand['key']):
                continue                         # (a landmark once a town)
            if cand.get('spot') and cand['spot'] in spot_used:
                continue                         # (one building of a one-spot set a town: 21 circus tents in Firuhn)
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
        if b.get('spot'):
            spot_used.add(b['spot'])
        if b.get('keep'):
            keeps.append(q)
        q['b'] = {'key': b['key'], 'culture': b['culture'], 'kind': b['kind'], 'w': b['w'], 'd': b['d'], 'uid': b['uid']}
        if is_chapel(b):
            q['kind'] = 'temple'         # (a chapel outside is a chapel inside, whatever the plot was for)
        elif q['kind'] in ('temple', 'manor', 'guard', 'guild') and b['kind'] in ('house', 'other'):
            q['kind'] = 'house'          # (no chapel, manor, garrison or guild fitted this plot: the house on it is a home)
        elif q['kind'] in ('temple', 'manor', 'guard', 'guild') and b['kind'] in ('shop', 'tavern'):
            q['kind'] = b['kind']
        elif q['kind'] == 'temple':
            q['kind'] = b['kind']        # (no chapel fitted: a guild hall, a manor or a guard house is what it looks)
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
    # (gates the user put on the wall: a street drawn from the town's middle out to each, so the planner lays the way in
    # there, and the wall opens only at them, townwalls.user_gates)
    gates = [(float(g[0]), float(g[1])) for g in (opts.get('gates') or []) if len(g) >= 2] if walls else []
    if gates and len(outline) >= 3:
        cx, cy = sum(p[0] for p in outline) / len(outline), sum(p[1] for p in outline) / len(outline)
        opts = dict(opts, roads=list(opts.get('roads') or []) + [[[cx, cy], [gx, gy]] for gx, gy in gates])
    # (the bar's planning share: a walled town is planned twice, its two plans the most of it)
    P = PLAN_END
    pl = townplan.plan(db, outline, culture, seed, walled=bool(walls), opts=opts)
    if opts.get('own'):
        pl['own'] = opts['own']             # (built of your own style's prefabs, planned like `culture`'s towns)
    if opts.get('family'):
        pl['family'] = str(opts['family']).lower()      # (the Look: the lead family of its buildings, looks())
    pl['skip'] = list(opts.get('skip') or ())
    pl['nokeep'] = bool(opts.get('nokeep'))     # (a castle's quarter: no keep building in it)
    _say('Choosing the buildings', P * (0.3 if walls else 0.8))
    plan = fit(db, pl, seed)
    if not walls:
        return plan
    if gates:
        plan['user_gates'] = gates
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
    if opts.get('family'):
        pl['family'] = str(opts['family']).lower()
    pl['skip'] = list(opts.get('skip') or ())
    pl['nokeep'] = bool(opts.get('nokeep'))     # (a castle's quarter: no keep building in it)
    _say('Choosing the buildings', P * 0.85)
    again = fit(db, pl, seed)
    built = lambda p_: sum(1 for q in p_['plots'] if q.get('b'))
    if built(again) < 0.75 * built(plan) and len(drawn) < 3:
        return plan
    again['wall_outline'] = [list(p_) for p_ in poly]
    if gates:
        again['user_gates'] = gates
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
    import ledger
    PROGRESS.update(on=True, what='Planning streets and plots', frac=0.0, ins=bool(interiors))
    try:
        # (written into the places ledger: what it is made from, and every piece it makes, ledger.py)
        with ledger.open(db, 'town', name, outline, seed, {'culture': culture, 'walls': walls, 'dress': bool(dress),
                                                           'interiors': interiors, 'people': bool(people), 'opts': opts}) as led:
            out = _make(db, outline, culture, seed, walls, dress, interiors, people, name, opts)
            if led is not None and isinstance(out, dict) and out.get('name'):
                led['name'] = out['name']
            return out
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
    import towntrade
    plan['trade'] = towntrade.clean((opts or {}).get('trade'))     # (what it lives by: its people, households and goods)
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
        plan['open_sea'] = bool((opts or {}).get('open_sea'))     # (a coastal town: no wall where it faces the water)
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
                # (the door's sill, the height its surroundings were learnt from: a door's own height is its middle on
                # the Common and Imperial doors, 98 over the sill, and every lantern, sign and banner learnt round such
                # a building hung 98 too high, a building's own banner set again over itself; the user's Senchal)
                q['sill_z'] = z0
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
        # (every door of a building, not its front one alone: a side door up a step stood 140 over the ground)
        own_ = [(tuple(q['door_ref']), q['rect']) for q in plan['plots'] if q.get('door_ref') and q.get('rect')]
        more_ = [(tuple(d_), q['rect']) for q in plan['plots'] if q.get('door_ref') and q.get('rect') for d_ in q.get('more_doors') or ()]
        fitted = _fit_ground(db, doors + [d_ for d_, _r in more_ if d_ not in doors], new_refs, own_ + more_, guard=wall_guard)
        import os as _os
        if _os.environ.get('TOWN_UNCOVER', '1') != '0':
            try:
                uncovered = _uncover(db, plan, new_refs, guard=wall_guard)
                if uncovered:
                    print('town: %d land points cut back from over the floors' % uncovered)
            except Exception as e:
                print('town uncover:', e)
        # (the streets a plane again, and the ground from each door to its street graded even: the user's hand edits)
        try:
            n_ap = _aprons(db, plan, new_refs, guard=wall_guard)
            # (and a footpath cut into the hill to each door too steep for a plane: the user's hand work, 2026-11-07)
            n_dp = _door_paths(db, plan, new_refs, guard=wall_guard)
            n_rp = _repin_streets(db, plan, new_refs, guard=wall_guard)
            if n_ap or n_dp or n_rp:
                print('town: %d apron points graded, %d footpath points cut (%d paths), %d street points put back at their level'
                      % (n_ap, n_dp, len(plan.get('paths') or ()), n_rp))
        except Exception as e:
            print('town aprons:', e)
    wall = 0
    wall_refs = []
    if W is not None:
        _say('Setting the wall on the ground', 0.87)
        db.sync_project()
        W = townwalls.grounded(db, W)
        W['_fill_lines'] = list(W.get('fill') or [])        # (where a bank is filled under the wall: rockblend's rocks go along it)
        try:
            # (the fill keeps off the town's own buildings and their door fronts: a house 520 under the wall had its door
            # buried 493 by the wall's fill, the lab's Sketh 2026-11-06)
            keep_ = townwalls.building_guard(db, W.get('outline') or []) + townwalls.wall_guard(db, W.get('outline') or [], mine=new_refs) + _tread_guard(plan)
            townwalls.fill_ground(db, W, new_refs, keep=keep_)
            # (and the town's ground inside brought level with the wall's foot, not a bank under the wall with the houses
            # dug in below it: the user's Firuhn, 2026-11-07, "a rampart of earth that could just be more level ground")
            n_in = townwalls.inner_ground(db, W, new_refs, keep=keep_ + [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')])
            if n_in:
                print('town: the ground inside the wall levelled to its foot in %d cells' % n_in)
        except Exception as e:
            print('wall fill:', e)
        try:
            # (a stair up to the walk for each level of the wall that has none: the walk is cut where the wall changes
            # level at a tower, the user's Firuhn 2026-11-07)
            more = townwalls.stair_each_level(W, free=lambda st: on_plots(st) == [], db=db)
            if more:
                W['pieces'] += more
                print('town: %d stairs more, one for each level of the wall' % len(more))
        except Exception as e:
            print('level stairs:', e)
        townwalls.drop_doubled(db, W, new_refs)     # (where a castle's or another town's wall already stands)
        try:
            n_rp = _repin_streets(db, plan, new_refs, guard=wall_guard)
            if n_rp:
                print('town: %d street points put back at their level after the wall' % n_rp)
        except Exception as e:
            print('town repin:', e)
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
    if pieces:
        # (after the wall stands and its ground is shaped)
        # (the creases and facets the terraces, fills and fits leave between what is built, rounded off; the streets,
        # the plots, the treads and the wall's ground stay: the user's "jagged polygons", 2026-11-07)
        if os.environ.get('TOWN_EASE', '1') != '0':
            try:
                n_ev = _ease_verges(db, plan, plan.get('outline') or outline, new_refs, guard=wall_guard, W=W)
                if n_ev:
                    print('town: %d land points beside the streets eased to a bank' % n_ev)
            except Exception as e:
                print('town verges:', e)
        try:
            n_sm = _smooth_kinks(db, plan, plan.get('outline') or outline, new_refs, guard=wall_guard, W=W)
            if n_sm:
                print('town: %d kinked land points rounded' % n_sm)
        except Exception as e:
            print('town smooth:', e)
    # (a building's other door left high over the ground once every pass has had its say, a street pinned level under
    # it: taken out with its step, so no door hangs over a drop and no household is made behind one)
    if pieces and made:
        try:
            db.sync_project()
            n_hd = _drop_high_doors(db, plan, new_refs)
            if n_hd:
                print('town: %d side doors left out, too high over the street under them' % n_hd)
                db.sync_project()
        except Exception as e:
            print('town high doors:', e)
    # (the culture's rocks set into the hill: behind the houses' cut banks, under perched floors, along the footpaths'
    # banks and the wall's, a crown outcrop on a knoll; each sunk until its mesh's bottom rim is under the ground.
    # rockblend.py, the user's lesson of 2026-11-08: "the cliff and rock palette ... a rugged and lofty appearance")
    rocks_n = 0
    if pieces and made and (opts or {}).get('rocks', True) and os.environ.get('TOWN_ROCKS', '1') != '0':
        _say('Setting rocks into the hill', 0.885)
        try:
            import rockblend
            db.sync_project()
            # (first the sheer sides of the streets regraded into a clean step and held by thick rock, tall as the soil
            # behind it: retain.py, by the user's rules of 2026-11-11. The bank pass's rocks keep off them)
            # (on since the user saw the lab's pictures and said so, 2026-11-11: rows of one make of rock, tops 47-64 over
            # the soil; TOWN_RETAIN=0 leaves them out)
            rw = None
            if os.environ.get('TOWN_RETAIN', '1') != '0':
                try:
                    import retain
                    rw = retain.revet(db, plan, W, new_refs, cells, plan.get('culture') or culture, seed, outline=plan.get('outline') or outline)
                    if rw.get('rocks'):
                        pieces += rw['rocks']
                        print('town: %d rocks holding %d sheer sides of its streets (%d land points regraded, %d sides with a gap)'
                              % (rw['rocks'], rw['runs'], rw['ground'], rw['bare']))
                        db.sync_project()
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print('town retaining walls:', e)
            rb = rockblend.blend(db, plan, plan.get('culture') or culture, seed, W, new_refs, cells, outline=plan.get('outline') or outline)
            rb['walls'] = rw or {}
            if rb['rocks']:
                rocks_n = rockblend.place(db, rb['rocks'], new_refs, cells)
                pieces += rocks_n
            # (and the sheer ground the town cut for itself clad as the land's own steep ground is: rockblend.clad_banks.
            # Off: in the lab's Senchal it found 41 steep points free of streets, plots and doors and laid 4 pieces, one
            # 2,000 across; the town's bare strips lie between a street's edge and a house, too narrow for it)
            if os.environ.get('TOWN_CLAD', '0') == '1':
                try:
                    db.sync_project()
                    cb = rockblend.clad_banks(db, plan, W, new_refs, cells, seed, outline=plan.get('outline') or outline)
                    rb['clad'] = {k: v for k, v in cb.items() if k in ('rocks', 'parts', 'dropped', 'cover', 'steep_points', 'rejects', 'why')}
                    rb['clad_placed'] = cb.get('placed') or []
                    if cb.get('rocks'):
                        rocks_n += cb['rocks']
                        pieces += cb['rocks']
                        print('town: %d cliff pieces over its sheer ground (%s), %s of it covered' % (cb['rocks'], ', '.join('%s %d' % kv for kv in sorted((cb.get('parts') or {}).items())), cb.get('cover')))
                except Exception as e:
                    print('town cladding:', e)
            plan['_rocks'] = rb
            if rocks_n or rb.get('dropped'):
                print('town: %d rocks set into the hill (%s; rate factor %s, %d dropped for a naked bottom edge)'
                      % (rocks_n, ', '.join('%s %d' % kv for kv in sorted(rb['kinds'].items())), rb.get('factor'), rb.get('dropped', 0)))
        except Exception as e:
            print('town rocks:', e)
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
        # (and round each shack and hut, what the game sets round that model outside: ropes and hooks on its walls,
        # barrels and baskets by its door; shellfit.dress_outside. The user, 2026-11-09: "some decor on the outside of
        # these shacks too")
        try:
            import shellfit
            blds_ = [r_ for ck_ in cells for r_ in mapdata.cellmap(db, ck_).get('refs') or ()
                     if r_['k'] in new_refs and shellfit.OUT_MODEL.match(r_['id'].lower())]
            laid_ += shellfit.dress_outside(db, blds_, seed, avoid=also + [(t_['id'], t_['p']) for t_ in laid_])
        except Exception as e_:
            print('town shack fronts:', e_)
        # (and its lamp posts last, up to the lights the culture's towns show a building: towndress.lamps)
        try:
            laid_ += towndress.lamps(db, plan, laid_, also)
        except Exception as e_:
            print('town lamps:', e_)
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
        if people and dress and made and interiors != 'later':
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
        if interiors == 'later' and made:
            # (the outside only, the insides and people kept for later: the Land panel's stages, the user 2026-11-09,
            # "populate and interiorize towns ... you got to glance at from the outside")
            _keep_for_later(db, name, culture, seed, outline, plan, cells, new_refs, W, wall_refs, stall_refs, dress)
        elif interiors and made:
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
    return {'buildings': made, 'pieces': pieces, 'cells': sorted(cells), 'fitted': fitted, 'road': painted, 'wall': wall, 'rocks': rocks_n,
            'dressed': dressed, 'interiors': inside.get('interiors', 0), 'wall_rooms': inside.get('wall_rooms', 0), 'people': inside.get('people', 0) + (life.get('people', 0) if pieces else 0), 'outdoors': life if pieces else {}, 'name': name}


PATHS = True                   # (the town's walking paths outdoors: townpaths)


def _plain(o):
    """o as JSON keeps it: tuples and sets as lists, objects as their fields; a dict with keys that aren't text left out."""
    if isinstance(o, dict):
        if any(not isinstance(k, (str, int)) for k in o):
            return None
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_plain(v) for v in (sorted(o, key=repr) if isinstance(o, (set, frozenset)) else o)]
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    if hasattr(o, '_asdict'):
        return {'__pose': _plain(o._asdict())}
    if hasattr(o, '__dict__'):
        return {'__pose': _plain(vars(o))}
    return None


def _unplain(o):
    import types
    if isinstance(o, dict):
        if '__pose' in o and len(o) == 1:
            return types.SimpleNamespace(**{k: _unplain(v) for k, v in (o['__pose'] or {}).items()})
        return {k: _unplain(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_unplain(v) for v in o]
    return o


def _keep_for_later(db, name, culture, seed, outline, plan, cells, new_refs, W, wall_refs, stall_refs, dress):
    """What a town's interiors and people need, kept in the project for insides() (project.land['towns_later'])."""
    p = db.project
    later = dict((getattr(p, 'land', None) or {}).get('towns_later') or {})
    kept = {}
    for k, v in plan.items():
        pv = _plain(v)
        if pv is not None or v is None:
            kept[k] = pv
    later[name] = {'name': name, 'culture': culture, 'seed': seed, 'outline': _plain(outline), 'dress': bool(dress),
                   'plan': kept, 'cells': _plain(cells), 'new_refs': _plain(new_refs), 'wall_refs': _plain(wall_refs),
                   'W': _plain({k: W[k] for k in ('outline', 'pieces') if k in W}) if W else None,
                   'stall_refs': _plain(stall_refs or {})}
    p.land = dict(p.land or {}, towns_later=later)
    p.save_soon()


def later_towns(db):
    """The towns built with their insides left for later whose buildings still stand: [{'name', 'waiting'}]."""
    out = []
    for nm, rec in ((getattr(db.project, 'land', None) or {}).get('towns_later') or {}).items():
        n = len(_waiting_plots(db, rec))
        if n:
            out.append({'name': nm, 'waiting': n})
    return out


def _waiting_plots(db, rec):
    """The town's plots whose door still stands and leads nowhere yet."""
    out, memo = [], {}
    for q in (rec.get('plan') or {}).get('plots') or ():
        dr = q.get('door_ref')
        if not dr:
            continue
        if dr[0] not in memo:
            memo[dr[0]] = {r['k']: r for r in mapdata.cellmap(db, dr[0]).get('refs') or ()}
        r = memo[dr[0]].get(dr[1])
        if r is None or r.get('to') or r.get('type') != 'DOOR':
            continue
        # (a town taken back by Undo frees its ref keys for the next one: a key alone named another town's piece, so the
        # door must stand where the plot's door was set too)
        d = q.get('door')
        if d and len(d) >= 2 and math.hypot(r['p'][0] - d[0], r['p'][1] - d[1]) > 256:
            continue
        out.append(q)
    return out


def insides(db, names=None, interiors=True, people=True, rooms='furnished', reseed=0):
    """The interiors and people of towns built with interiors='later' (the Land panel's third stage), as Make it would
    have made them: each door's interior, the wall's keeps and rooms, the households, and the people outdoors. One Undo
    step for all. {'towns', 'interiors', 'people', 'names'}."""
    import editing
    import random
    import towninside
    editing._require_project(db)
    later = (getattr(db.project, 'land', None) or {}).get('towns_later') or {}
    stack = getattr(db.project, 'undo_stack', [])
    n0 = len(stack)
    out = {'towns': 0, 'interiors': 0, 'people': 0, 'names': []}
    C = catalog(db)
    for nm, rec in list(later.items()):
        if names and nm not in names:
            continue
        live = _waiting_plots(db, rec)
        if not live:
            continue
        # (into the town's own record in the places ledger, so its interiors and people are its too; a town from
        # before the ledger has none, and its insides get a record of their own)
        import ledger
        own = ledger.named(db, 'town', nm)
        with ledger.open(db, 'town' if own else 'interior', nm, resume=own) as led:
            if own and led is not None:
                led['opts'] = dict(led.get('opts') or {}, interiors=(True if rooms == 'furnished' else 'shells') if interiors else False,
                                   people=bool(people))
            culture, seed = rec.get('culture') or '', int(rec.get('seed') or 1) + 7919 * int(reseed or 0)
            plan = dict(_unplain(rec.get('plan') or {}), plots=_unplain(live))
            cells = {c if isinstance(c, str) else tuple(c) for c in rec.get('cells') or ()}      # (keys are text: tuple() of one made letters, and the people outdoors failed)
            new_refs = {r if isinstance(r, str) else tuple(r) for r in rec.get('new_refs') or ()}
            W = _unplain(rec.get('W')) if rec.get('W') else None
            wall_refs = [tuple(r) if isinstance(r, list) else r for r in rec.get('wall_refs') or ()]
            stall_refs = {(int(k) if str(k).lstrip('-').isdigit() else k): [tuple(x) if isinstance(x, list) else x for x in v]
                          for k, v in (rec.get('stall_refs') or {}).items()}
            outline = rec.get('outline') or []
            made_in = folks = 0
            if interiors:
                _say('Making the interiors of %s' % nm, 0.1)
                got = towninside.furnish(db, plan, nm, culture, seed, people and rooms == 'furnished', C, None, rooms=rooms)
                made_in += got.get('interiors', 0)
                folks += got.get('people', 0)
                if wall_refs and W and W.get('outline'):
                    try:
                        import castle
                        made_in += len(castle.wall_keeps(db, wall_refs, W['outline'], nm, set(), random.Random('%s|%s|wall keeps' % (seed, culture)), rooms=rooms))
                    except Exception as e:
                        print('wall keeps:', e)
                    try:
                        made_in += len(towninside.wall_rooms(db, wall_refs, W['outline'], nm, set(), random.Random('%s|%s|wall rooms' % (seed, culture)), rooms=rooms))
                    except Exception as e:
                        print('wall rooms:', e)
                try:
                    import doors as doors_
                    doors_.face_arrivals(db, sorted(cells))
                except Exception as e:
                    print('door arrivals:', e)
                if PATHS and wall_refs:
                    try:
                        _lay_paths(db, plan, cells, outline, _wall_ways(db, plan, cells))
                    except Exception as e:
                        print('paths to the wall doors:', e)
            if people and rec.get('dress', True):
                try:
                    import townlife
                    life = townlife.people(db, plan, culture, seed, cells, new_refs, W, stall_refs)
                    folks += life.get('people', 0)
                    if life.get('people'):
                        editing.commit(db, 'People outdoors in %s: %d' % (nm, life['people']))
                except Exception as e:
                    print('town life:', e)
            out['towns'] += 1
            out['interiors'] += made_in
            out['people'] += folks
            out['names'].append(nm)
    if len(stack) > n0:
        editing.fold(db, len(stack) - n0, 'Made the insides of %s: %d interiors%s' % (
            ', '.join(out['names'][:3]) + (' and %d more' % (len(out['names']) - 3) if len(out['names']) > 3 else ''),
            out['interiors'], (', %d people' % out['people']) if out['people'] else ''))
    return out


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


def made_inside(db, outline, away=()):
    """How many pieces a Make laid as part of a building (project.town_parts) stand inside the outline: whether a town
    or castle stands there, whatever its neighbours are (the remove's look ran its range of made things through a castle
    joined to a city's wall, read the city as not built, and Make places built a second city over it, 2026-11-09)."""
    import townplan
    poly = [(float(a), float(b)) for a, b in outline or ()]
    if len(poly) < 3:
        return 0
    parts = getattr(db.project, 'town_parts', None) or {}
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    n = 0
    for gx in range(int(min(xs) // 8192), int(max(xs) // 8192) + 1):
        for gy in range(int(min(ys) // 8192), int(max(ys) // 8192) + 1):
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                if r.get('new') and r['k'] in parts and townplan._inside(poly, r['p'][0], r['p'][1])                         and not any(math.hypot(r['p'][0] - a[0], r['p'][1] - a[1]) <= a[2] for a in away):
                    n += 1          # (away: circles [x, y, r] left out, a castle's ground inside a city's outline)
    return n


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
        # (the wall, the rocks, the dressing and the people are made after the last building, key after key: the
        # unbroken run of made things on from the last building part is the town's too. Before, the no-interiors
        # remove stopped at the last building part and left the wall and dressing standing; a second Make it there
        # found the old wall and dropped its own, 2026-11-08)
        have = {idx(r['k']) for _ck, r in made}
        while hi + 1 in have:
            hi += 1
    out = [(ck, r['k']) for ck, r in made if lo <= idx(r['k']) <= hi]
    # (an interior a door left standing still leads into stays: another town of the same name, or one you linked)
    gone = {rk for _ck, rk in out}
    kept = {(r.get('to') or {}).get('key') for _ck, r in made if r['type'] == 'DOOR' and r['k'] not in gone}
    inside = [k for k in inside if k not in kept]
    if look:
        share = sum(1 for ck, rk in out for _c, r in made if r['k'] == rk and townplan._inside(poly, r['p'][0], r['p'][1])) / float(len(out) or 1)
        return {'things': len(out), 'interiors': len(inside), 'name': town.title(), 'inside': round(share, 2)}
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
ROCKISH = re.compile(r'rock|boulder|stone_', re.I)
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

    def on_town(x, y, rad=8.0, rock=False):
        # (rad: half the thing's own size, so a big boulder whose middle is clear but whose side reaches a house goes too)
        if (int(x // townplan.PATCH), int(y // townplan.PATCH)) in roads:
            return True
        if rock and rad > 64:
            # (a rock whose body laps the street: the game's boulders stood into made streets, lab 2026-11-10. A tree
            # by a street stays: its crown is over the street, not on it)
            sd = _street_dist(plan, x, y)
            if sd is not None and sd < rad * 0.85:
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
                    and not NOT_CLEARABLE.search(r['id']) and on_town(r['p'][0], r['p'][1], rad_of(r), ROCKISH.search(r['id']) is not None)]
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
TERRACE_STREET_GIVE = 32       # (a plot whose door front stands on a levelled street gives only this: pulled 128 toward a lower
                               # neighbour, a plot sat 130 under the street it faced, a ditch between them, the user's Skethwall 2026-11-07)


def _terrace_steps(areas):
    """[(rect, level)] with neighbouring levels drawn together: each plot levelled to its own door left two joined
    houses 200-500 apart in height with a gap of 40-200 between them, a cliff no fade could soften (the town practice
    of 2026-11-01: plot levelling took the steep ground of a town from 1.2% to 3.7%)."""
    def gap(a, b):
        return min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in a for q in b)
    zs = [a[1] for a in areas]
    z0 = list(zs)
    give = [a[2] if len(a) > 2 else TERRACE_GIVE for a in areas]
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
                # (each at most its give from its own door's ground: further, and on a hillside the plot itself came
                # out sloped under the land's own limit; a plot on a street stays at the street's level)
                ni = max(z0[i] - give[i], min(z0[i] + give[i], zs[i] - fix))
                nj = max(z0[j] - give[j], min(z0[j] + give[j], zs[j] + fix))
                if abs(ni - zs[i]) + abs(nj - zs[j]) > 0.5:
                    zs[i], zs[j] = ni, nj
                    moved = True
        if not moved:
            break
    return [(a[0], z) for a, z in zip(areas, zs)]


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
        on_street = _street_dist(plan, fx, fy) is not None and _street_dist(plan, fx, fy) <= STREET_EDGE + 128
        areas.append(([tuple(p_) for p_ in q['rect']], gz, TERRACE_STREET_GIVE if on_street else TERRACE_GIVE))
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


def _street_dist(plan, x, y):
    """How far a point stands outside the nearest street's width (0 on the street), or None with no streets."""
    best = None
    for st in plan.get('streets') or ():
        hw = (st.get('w') or 512) / 2.0
        pts = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            d = max(0.0, math.hypot(x - ax - dx * t, y - ay - dy * t) - hw)
            if best is None or d < best:
                best = d
    return best


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
STREET_BLEND = 384             # fading back into the land over this at least,
STREET_FADE = 3.0              # or this times the street's rise or drop against the land (a cosine fade is steepest at its
                               # middle, pi/2 times its mean: 3x keeps the verge under 30 degrees, as the terraces' banks)
STREET_BLEND_MAX = 1024        # (and this far at most)


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
    out, pins = [], []
    for i, (x, y, z0) in enumerate(raw):
        if z0 is None or z0 < 0:
            out.append((x, y, None))          # (across water: left as it is)
            continue
        ws = [(1.0 - abs(j - i) / float(W + 1), raw[j][2]) for j in range(max(0, i - W), min(n, i + W + 1)) if raw[j][2] is not None and raw[j][2] >= 0]
        z = sum(w * v for w, v in ws) / sum(w for w, _ in ws)
        z = max(z0 - STREET_TOL, min(z0 + STREET_TOL, z))
        pz = pinned(x, y)
        if pz is not None:
            pins.append((i, pz - z))          # (how far the pinned level stands from the street's own grade there)
            out.append((x, y, pz))
            continue
        out.append((x, y, z))
    # (from a pinned level, a junction's or the square's, the street eases back to its own grade over STREET_SMOOTH
    # instead of stepping off it at the next sample)
    if pins:
        eased = []
        for i, (x, y, z) in enumerate(out):
            if z is None or pinned(x, y) is not None:
                eased.append((x, y, z))
                continue
            k, dz = min(pins, key=lambda pd: abs(pd[0] - i))
            f = max(0.0, 1.0 - abs(k - i) * 128.0 / STREET_SMOOTH)
            eased.append((x, y, z + dz * f))
        out = eased
    return _graded(out, pinned)


def _is_ramp(st):
    return bool(st.get('ramp')) and not st.get('stair')


def _ramp_profile(db, st, pinned):
    """[(x, y, z)] every 128 along a ramp: one even climb from the level at its first point to the level at its last
    (the streets it joins, else the land). The ramps were levelled like any street, after the streets they join and
    never over them: wherever a ramp lay in their width it was held at their level, and the whole climb fell on the two
    or three points between, 184 up at 0.56 where its length gave 0.17 (the user's Senchal, 2026-11-11: "a path that
    should be less steep"). Its own width is now its own (_level_streets)."""
    pts = st.get('pts') or []
    out, run = [], 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, by - ay)
        if L < 1:
            continue
        for k in range(int(L // 128)):
            out.append((ax + (bx - ax) * k * 128 / L, ay + (by - ay) * k * 128 / L, run + k * 128))
        run += L
    if len(pts) >= 2:
        out.append((pts[-1][0], pts[-1][1], run))
    if len(out) < 2 or run < 1:
        return []

    def level(x, y):
        z = pinned(x, y)
        return z if z is not None else mapdata.terrain_z(db, x, y)
    z0, z1 = level(out[0][0], out[0][1]), level(out[-1][0], out[-1][1])
    if z0 is None or z1 is None or z0 < 0 or z1 < 0:
        return _street_profile(db, st, pinned)
    return [(x, y, z0 + (z1 - z0) * d / run) for x, y, d in out]


STREET_MAX_GRADE = 0.3         # a street climbs this much a unit at most along its length (17 degrees)


def _graded(prof, pinned):
    """A street's profile with its climb spread along it: no step of 128 rises or falls more than STREET_MAX_GRADE.
    A street crossing the bank between two levels followed the bank, 184 up in a few steps at 0.6, and the bank pass
    took the paved slope for a bare bank and set rocks on it (the user's Senchal, 2026-11-11: "a path that should be
    less steep and not have rocks at all"). Each run of points takes the middle of the two gentlest lines that hold it
    (cut above, fill below, alike); pinned levels, a junction's or the square's, stay, the points between them eased
    to them."""
    g = STREET_MAX_GRADE * 128.0
    out = list(prof)
    n = len(out)
    i = 0
    while i < n:
        if out[i][2] is None:
            i += 1
            continue
        j = i
        while j < n and out[j][2] is not None:
            j += 1
        f = [out[k][2] for k in range(i, j)]
        m = len(f)
        if m >= 3 and any(abs(f[k + 1] - f[k]) > g for k in range(m - 1)):
            pin = [pinned(out[i + k][0], out[i + k][1]) is not None for k in range(m)]
            up = [max(f[b_] - g * abs(a_ - b_) for b_ in range(m)) for a_ in range(m)]
            lo = [min(f[b_] + g * abs(a_ - b_) for b_ in range(m)) for a_ in range(m)]
            z = [f[k] if pin[k] else (up[k] + lo[k]) / 2.0 for k in range(m)]
            for _pass in range(3):
                for k in range(1, m):
                    if not pin[k]:
                        z[k] = max(z[k - 1] - g, min(z[k - 1] + g, z[k]))
                for k in range(m - 2, -1, -1):
                    if not pin[k]:
                        z[k] = max(z[k + 1] - g, min(z[k + 1] + g, z[k]))
            # (between two pinned levels too near each other for the grade, a ramp 1,077 long whose ends lie in the
            # streets it joins: the climb even over every point it has, the gentlest there is; it stood 184 up over
            # two points at 0.56 with five level ones beside them)
            fixed = [k for k in range(m) if pin[k]]
            for a_, b_ in zip(fixed, fixed[1:]):
                if b_ - a_ >= 2 and any(abs(z[k + 1] - z[k]) > g + 1.0 for k in range(a_, b_)):
                    for k in range(a_ + 1, b_):
                        z[k] = z[a_] + (z[b_] - z[a_]) * (k - a_) / float(b_ - a_)
            for k in range(m):
                out[i + k] = (out[i + k][0], out[i + k][1], z[k])
        i = j
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
    # (the ramps last: a ramp's own width is its own, over the streets it joins)
    streets = sorted(plan.get('streets') or (), key=lambda s: (_is_ramp(s), not s.get('main'), bool(s.get('lane') or s.get('court'))))
    target = {}                               # (gx, gy, i, j): (z, weight)

    def vkey(x, y):
        return (int(math.floor(x / G)), int(math.floor(y / G)), int(round((x % G) / step)), int(round((y % G) / step)))

    def pinned(x, y):
        t = target.get(vkey(x, y))
        return t[0] if t and t[1] >= 0.99 else None
    # (the square first, one flat disc at the median of its ground, pinned like a street: a terrace step of 170 ran
    # across a paved square between two plots' levels, the user's Skethwall 2026-11-07. The streets through it take
    # its level and ease out to their own grade)
    sq = plan.get('square')
    if sq and len(sq) >= 3 and sq[2] > 0:
        x0, y0, r = float(sq[0]), float(sq[1]), float(sq[2])
        zs_ = []
        for vx in range(int(math.floor((x0 - r) / step)), int(math.floor((x0 + r) / step)) + 2):
            for vy in range(int(math.floor((y0 - r) / step)), int(math.floor((y0 + r) / step)) + 2):
                x, y = vx * step, vy * step
                if math.hypot(x - x0, y - y0) <= r:
                    z_ = mapdata.terrain_z(db, x, y)
                    if z_ is not None and z_ >= 0:
                        zs_.append(z_)
        if zs_:
            zq = sorted(zs_)[len(zs_) // 2]
            zq = max(min(zs_) - STREET_TOL, min(max(zs_) + STREET_TOL, zq))
            for vx in range(int(math.floor((x0 - r - STREET_BLEND) / step)), int(math.floor((x0 + r + STREET_BLEND) / step)) + 2):
                for vy in range(int(math.floor((y0 - r - STREET_BLEND) / step)), int(math.floor((y0 + r + STREET_BLEND) / step)) + 2):
                    x, y = vx * step, vy * step
                    d = math.hypot(x - x0, y - y0)
                    if d >= r + STREET_BLEND:
                        continue
                    w = 1.0 if d <= r else 0.5 + 0.5 * math.cos(math.pi * (d - r) / STREET_BLEND)
                    target[vkey(x, y)] = (zq, w, max(0.0, d - r), -1)
    for rank, st in enumerate(streets):
        ramp = _is_ramp(st)
        prof = _ramp_profile(db, st, pinned) if ramp else _street_profile(db, st, pinned)
        good = [(x, y, z) for x, y, z in prof if z is not None]
        if len(good) < 2:
            continue
        hw = (st.get('w') or 512) / 2.0
        reach = hw + STREET_EDGE + STREET_BLEND_MAX
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
                dd = max(0.0, d - hw - STREET_EDGE)             # (how far beyond the level width)
                # (a provisional weight, to choose the street that reaches a point most strongly; the fade's reach is
                # settled against the land's own height when the ground is written)
                w = 1.0 if dd <= 0 else 0.5 + 0.5 * math.cos(math.pi * min(1.0, dd / STREET_BLEND))
                k = vkey(x, y)
                old = target.get(k)
                if old is None or w > old[1] + 1e-6 or (ramp and d <= hw):
                    mine[k] = (z, w, dd, rank)
        target.update(mine)
    if os.environ.get('TOWN_EASE', '1') != '0':
        _meet_streets(target)
    # (the street's own ground kept by what follows: the terraces faded over the streets between plots and put their
    # humps back, lab ja2)
    plan['_street_ground'] = {(gx * G + i * step, gy * G + j * step) for (gx, gy, i, j), zw in target.items() if zw[1] >= 0.99}
    plan['_street_pins'] = {(gx * G + i * step, gy * G + j * step): zw[0] for (gx, gy, i, j), zw in target.items() if zw[1] >= 0.99}
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
                z, w, dd = zw[:3]
                if w < 0.99:
                    # (the verge: a fade as long as the terraces' for the drop it has to make, within STREET_BLEND_MAX)
                    reach = max(STREET_BLEND, min(STREET_BLEND_MAX, STREET_FADE * abs(z - z0)))
                    if dd >= reach:
                        continue
                    w = 0.5 + 0.5 * math.cos(math.pi * dd / reach)
                nz = z0 + w * (z - z0)
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


MEET_REACH = 4                 # (a lesser street comes to a greater one's level over this many land points at VERGE_GRADE)


def _meet_streets(target):
    """Where two streets' level points lie side by side at two heights, a step across the paving (each point takes the
    one street's height: a quarter of a made hill town's bare steep ground, six lab towns, 2026-11-10), the lesser
    street comes to the greater one's level over MEET_REACH points, at VERGE_GRADE; the square and the main street
    stay as they are. A step higher than that reach can ramp is a terrace between two streets and stays."""
    P = {}
    for (gx, gy, i, j), zw in target.items():
        if zw[1] >= 0.99:
            P[(gx * 64 + i, gy * 64 + j)] = [zw[0], zw[3], (gx, gy, i, j)]
    step = 128.0
    most = VERGE_GRADE * step * MEET_REACH
    around = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    for rank in sorted({v[1] for v in P.values()}):
        hi, lo = {}, {}
        front = set()
        for k, (z, r, _key) in P.items():
            if r != rank:
                continue
            for di, dj in around[:4]:
                n = P.get((k[0] + di, k[1] + dj))
                if n is None or n[1] >= rank or abs(n[0] - z) > most or abs(n[0] - z) <= VERGE_GRADE * step:
                    continue
                hi[k] = min(hi.get(k, 1e9), n[0] + VERGE_GRADE * step)
                lo[k] = max(lo.get(k, -1e9), n[0] - VERGE_GRADE * step)
                front.add(k)
        for _round in range(MEET_REACH - 1):
            nxt = set()
            for k in front:
                for di, dj in around:
                    n = (k[0] + di, k[1] + dj)
                    if n not in P or P[n][1] != rank:
                        continue
                    d = VERGE_GRADE * step * (1.4142 if di and dj else 1.0)
                    a, b = hi[k] + d, lo[k] - d
                    if a < hi.get(n, 1e9) - 1e-6:
                        hi[n] = a
                        nxt.add(n)
                    if b > lo.get(n, -1e9) + 1e-6:
                        lo[n] = b
                        nxt.add(n)
            front = nxt
        for k, a in hi.items():
            b = lo.get(k, -1e9)
            if b > a:
                continue
            z = P[k][0]
            nz = min(max(z, b), a)
            if nz != z:
                P[k][0] = nz
                old = target[P[k][2]]
                target[P[k][2]] = (nz,) + tuple(old[1:])


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


PATH_GRADE = 0.25              # (a door whose straight line to its street climbs more than this a unit gets a footpath instead of a
                               # graded plane: the game's doors' straight lines p90 0.23, and where steeper the game's ground offers a
                               # way of 0.25 at the median, 2.6 times as long; 1,474 game doors with a road, 2026-11-07)
PATH_MAX = 0.32                # (no stretch of a footpath climbs more than this a unit)
PATH_REACH = 2400              # (a footpath is cut to a street this far off at most)
PATH_STEP = 64                 # (the way is found on a lattice this fine, with moves up to four steps long: a traverse across a
                               # slope at an angle, as a path climbs a hill, not a staircase of steps along and up it)
PATH_PAD = 1024                # (the lattice reaches this far beyond the door and its street: room for a switchback)
PATH_WANDER = 3.0              # (a footpath is at most this many times its straight line long, and PATH_PAD more: two wandered 3,400 and
                               # 4,600 units round Firuhn's hill for doors 550 over their street, lab 2026-11-07)
PATH_CLEAR = 128               # (the way keeps this far off the plots: the tread's middle; its edges may lap a plot's levelled ground)
PATH_CUT = 400                 # (a stretch may be cut this deep into the ground under it at most)
PATH_FILL = 192                # (and stand this high over a hollow at most: a footpath is dug, not built up. Lower, 96, and no way
                               # crossed the banks between the town's own terraces: a stretch cut down a bank's face lies over the
                               # ground at its foot; 13 of Firuhn's 19 steep doors had no path, lab 2026-11-07)
PATH_EDGE = 32                 # (the tread sits this much over the natural ground at its downhill edge at most: the cut is on the uphill
                               # side, a bank; the user's Flatten work, "carve into the terrain like real paths would")
TREAD_HALF = 192               # (the tread: level across this wide either side of its line: every vertex of each 128 land square the line
                               # crosses (128 * root 2 = 181), else the ground between them bled in from the cut bank, 65-155 over the
                               # tread; about as wide as the user's Flatten brush of 144 cut them)
CUT_BLEND = 128                # (the cut bank on the uphill side rises to the old ground within this: a steep face, by the user's rule)
FILL_BLEND = 256               # (the downhill side eases to the old ground over this)
LANDING_R = 160                # (a level pad this wide round the door's front, at its ground)
APRON_HALF = 160               # (the corridor graded between a door's front and its street: this wide either side of the line)
APRON_BLEND = 160              # (and fading out this far beyond)


def _repin_streets(db, plan, skip=(), guard=()):
    """The levelled streets' and the square's own vertices put back at their level (plan['_street_pins'], _level_streets)
    where a later pass moved them: the buildings' ground fit blended a landing or a sink into the street (a mound in
    front of a door, a bank against a house), the wall's fill raised the street by it. The user flattened every such hump
    by hand on Skethwall (Research/2-6, 2026-11-07). guard: polygons left alone (the wall's). Points moved."""
    import landscape
    pins = plan.get('_street_pins') or {}
    if not pins:
        return 0
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    cells_ = set()
    for (x, y) in pins:
        gx, gy = int(math.floor(x / G)), int(math.floor(y / G))
        i, j = int(round((x - gx * G) / step)), int(round((y - gy * G) / step))
        cells_.add((gx, gy))
        if i == 0:
            cells_.add((gx - 1, gy))
        if j == 0:
            cells_.add((gx, gy - 1))
        if i == 0 and j == 0:
            cells_.add((gx - 1, gy - 1))
    new_h, before, moved = {}, {}, 0
    for gx, gy in cells_:
        L = mapdata.land(db, gx, gy)
        if not L or not L.get('h'):
            continue
        h = list(L['h'])
        changed = False
        for j in range(N):
            for i in range(N):
                x, y = gx * G + i * step, gy * G + j * step
                z = pins.get((x, y))
                if z is None:
                    continue
                n = j * N + i
                if h[n] < 0 or abs(h[n] - z) < 4:
                    continue                      # (the land's heights are kept in steps of 8)
                if guard and any(_in_rect(g_, x, y) for g_ in guard):
                    continue
                h[n] = z
                changed = True
                moved += 1
        if changed:
            new_h[(gx, gy)] = h
            before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return moved


def _aprons(db, plan, skip=(), guard=()):
    """The ground between each door's front and the street it faces graded in a straight line from the one to the
    other, over a corridor APRON_HALF either side of the line and fading APRON_BLEND beyond: a hollow or a hump between
    a plot's terrace and the street's edge (the land's own, which neither pass reached) stays otherwise, 60 deep at one
    door in the lab's rolling town. The user levelled these by hand (Research/1, 5, 6, 2026-11-07). The street's own
    vertices, the plots' footprints and the guard polygons are left alone. Points moved."""
    import landscape
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    pins = plan.get('_street_pins') or {}
    rects = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    streets = plan.get('streets') or []
    jobs = []
    for q in plan['plots']:
        if not q.get('b') or not q.get('door') or q.get('door_z') is None:
            continue
        c, sn, _yaw = _frame(q['face'])
        fx, fy = _world(q['door'][0], q['door'][1], c, sn, 0.0, -120.0)
        best = None
        for st in streets:
            hw = (st.get('w') or 512) / 2.0
            pts = st.get('pts') or []
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = 0.0 if not L2 else max(0.0, min(1.0, ((fx - ax) * dx + (fy - ay) * dy) / L2))
                px, py = ax + dx * t, ay + dy * t
                d = math.hypot(fx - px, fy - py)
                if best is None or d < best[0]:
                    best = (d, px, py, hw)
        if best is None or best[0] > 1200:
            continue
        d, px, py, hw = best
        reach = hw + STREET_EDGE
        if d <= reach + 64:
            continue                              # (the front stands on the street's own level already)
        ux, uy = (px - fx) / d, (py - fy) / d
        ex, ey = fx + ux * (d - reach), fy + uy * (d - reach)      # (where the street's levelled ground begins)
        zf, ze = mapdata.terrain_z(db, fx, fy), mapdata.terrain_z(db, ex, ey)
        if zf is None or ze is None or zf < 0 or ze < 0:
            continue
        if abs(ze - zf) / max(1.0, d - reach) > PATH_GRADE:
            continue                              # (too steep for a plane: a path's, _door_paths)
        jobs.append((fx, fy, ex, ey, zf, ze, d - reach))
    if not jobs:
        return 0
    xs = [v for jb in jobs for v in (jb[0], jb[2])]
    ys = [v for jb in jobs for v in (jb[1], jb[3])]
    pad = APRON_HALF + APRON_BLEND
    new_h, before, moved = {}, {}, 0
    for gx in range(int(math.floor((min(xs) - pad) / G)), int(math.floor((max(xs) + pad) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - pad) / G)), int(math.floor((max(ys) + pad) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(N):
                for i in range(N):
                    x, y = gx * G + i * step, gy * G + j * step
                    if (x, y) in pins:
                        continue
                    n = j * N + i
                    z0 = h[n]
                    if z0 < 0:
                        continue
                    want, wbest = None, 0.0
                    for fx, fy, ex, ey, zf, ze, L_ in jobs:
                        if abs(x - fx) > L_ + pad or abs(y - fy) > L_ + pad:
                            continue
                        ux, uy = (ex - fx) / L_, (ey - fy) / L_
                        t = ((x - fx) * ux + (y - fy) * uy)
                        if t < -32 or t > L_ + 32:
                            continue
                        lat = abs(-(x - fx) * uy + (y - fy) * ux)
                        if lat >= APRON_HALF + APRON_BLEND:
                            continue
                        w = 1.0 if lat <= APRON_HALF else 0.5 + 0.5 * math.cos(math.pi * (lat - APRON_HALF) / APRON_BLEND)
                        if w > wbest:
                            tt = max(0.0, min(1.0, t / L_))
                            want, wbest = zf + (ze - zf) * tt, w
                    if want is None:
                        continue
                    if any(_in_rect(r, x, y) for r in rects) or (guard and any(_in_rect(g_, x, y) for g_ in guard)):
                        continue
                    nz = z0 + wbest * (want - z0)
                    if abs(nz - z0) >= 1:
                        h[n] = nz
                        changed = True
                        moved += 1
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return moved


_MOVES = [(a * sa, b * sb) for a, b in ((1, 0), (0, 1), (1, 1), (1, 2), (2, 1), (1, 3), (3, 1), (1, 4), (4, 1), (2, 3), (3, 2), (3, 4), (4, 3))
          for sa in (1, -1) for sb in (1, -1) if not ((a == 0 and sa < 0) or (b == 0 and sb < 0))]


def _door_paths(db, plan, skip=(), guard=()):
    """A footpath from the street to each door whose straight line is too steep for the apron's plane (over PATH_GRADE):
    its way found on a PATH_STEP lattice round the buildings, each stretch no steeper than PATH_MAX, cut into the ground
    rather than built up (no stretch over PATH_CUT deep or PATH_FILL high), then its tread laid level across TREAD_HALF
    either side at a height that sits at most PATH_EDGE over the downhill edge's ground (so the cut is a bank on the
    uphill side, eased within CUT_BLEND, and the downhill side eases over FILL_BLEND), with a level landing LANDING_R
    round the door's front; a later path may end on an earlier one. The streets' own vertices, the plots' footprints and
    the guard polygons are left alone. The user shaped these by hand on Firuhn's hillside (2026-11-07: "with some shaping
    I made the paths tastefully lead up to each door ... paths that carve into the terrain like real paths would").
    Points moved; the paths in plan['paths']."""
    import landscape
    G, N = landscape.CELL, landscape.N
    vstep = G / (N - 1.0)
    pins = plan.get('_street_pins') or {}
    rects = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    streets = plan.get('streets') or []
    if not streets:
        return 0
    memo = {}

    def zat(x, y):
        k = (round(x / 8.0), round(y / 8.0))
        if k not in memo:
            memo[k] = mapdata.terrain_z(db, x, y)
        return memo[k]

    def blocked(x, y):
        return any(_in_rect(r, x, y) for r in rects) or (guard and any(_in_rect(g_, x, y) for g_ in guard))
    # (the way keeps a tread's half-width off the plots, so the whole tread can be cut: a way along a plot's edge left its
    # tread's vertices inside the plot unwritten and the ground 65-155 over the tread, lab 2026-11-07)
    plots_ = [q for q in plan['plots'] if q.get('b') and q.get('rect')]
    wide = [_grown(r, PATH_CLEAR) for r in rects]

    # (a way may cross a plot's yard, its own or a neighbour's, in front of the door line, never the building's side: the
    # doors 400-700 over their street on Firuhn's hill were boxed in by the plots round them, lab 2026-11-07)
    def blocked_way(x, y, own=None):
        for q_, r in zip(plots_, wide):
            if _in_rect(r, x, y) and _own_side(q_, x, y):
                return True
        return bool(guard) and any(_in_rect(g_, x, y) for g_ in guard)

    paths = []
    steep = 0
    tread_pts = []                              # (earlier paths' points: a goal for a later one)
    for q in plan['plots']:
        if not q.get('b') or not q.get('door') or q.get('door_z') is None:
            continue
        c, sn, _yaw = _frame(q['face'])
        fx, fy = _world(q['door'][0], q['door'][1], c, sn, 0.0, -120.0)
        zf = zat(fx, fy)
        if zf is None or zf < 0:
            continue
        # (the nearest street's levelled edge, as _aprons finds it)
        best = None
        for st in streets:
            hw = (st.get('w') or 512) / 2.0
            pts = st.get('pts') or []
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = 0.0 if not L2 else max(0.0, min(1.0, ((fx - ax) * dx + (fy - ay) * dy) / L2))
                px, py = ax + dx * t, ay + dy * t
                d = math.hypot(fx - px, fy - py)
                if best is None or d < best[0]:
                    best = (d, px, py, hw)
        if best is None or best[0] > PATH_REACH:
            continue
        d, px, py, hw = best
        reach = hw + STREET_EDGE
        if d <= reach + 64:
            continue
        ux, uy = (px - fx) / d, (py - fy) / d
        ex, ey = fx + ux * (d - reach), fy + uy * (d - reach)
        ze = zat(ex, ey)
        if ze is None or ze < 0 or abs(ze - zf) / max(1.0, d - reach) <= PATH_GRADE:
            continue                              # (a plane will do: _aprons)
        steep += 1
        # (a way that comes back within a tread and a half of itself, a hairpin, is found again with that stretch barred: its
        # two legs' treads would merge at odd heights; three tries, else no path)
        barred = set()
        way = None
        why = 'no way'
        for _try in range(5):
            w_ = _find_path(plan, zat, lambda x, y: blocked_way(x, y, q) or (round(x / PATH_STEP), round(y / PATH_STEP)) in barred,
                            fx, fy, ex, ey, tread_pts)
            if not w_:
                break
            why = 'hairpin'
            # (legs one clearly over the other, a switchback up a slope, are no hairpin: each keeps its own vertices and a
            # bank stands between)
            close = [k for k in range(4, len(w_)) if any(math.hypot(w_[k][0] - w_[j][0], w_[k][1] - w_[j][1]) < TREAD_HALF + 64
                                                          and abs((zat(*w_[k]) or 0) - (zat(*w_[j]) or 0)) < 96 for j in range(k - 3))]
            if not close:
                way = w_
                break
            for k in close:
                barred.add((round(w_[k][0] / PATH_STEP), round(w_[k][1] / PATH_STEP)))
        if os.environ.get('TOWN_PATH_DEBUG'):
            print('  path door %d,%d: street %.0f off, %+.0f up, straight %.2f: %s' % (fx, fy, d - reach, ze - zf, abs(ze - zf) / max(1.0, d - reach),
                                                                                       ('%d points' % len(way)) if way else why))
        if not way:
            continue
        prof = _tread_profile(zat, way, zf)
        paths.append({'pts': [(round(x), round(y)) for x, y in way], 'z': [round(v) for v in prof], 'w': 2 * TREAD_HALF,
                      'door': (round(fx), round(fy)), 'own': {'rect': [tuple(p_) for p_ in q['rect']], 'face': q['face'], 'door': list(q['door'])}, 'grade': round(max(abs(prof[k + 1] - prof[k]) / max(1.0, math.hypot(way[k + 1][0] - way[k][0], way[k + 1][1] - way[k][1]))
                                                                        for k in range(len(way) - 1)), 3)})
        tread_pts.extend(way[1:])
    if not paths:
        return 0
    plan['paths'] = paths
    print('town: %d doors too steep for a graded plane, %d footpaths found' % (steep, len(paths)))
    return _lay_treads(db, plan, skip, guard)


def _lay_treads(db, plan, skip=(), guard=()):
    """The ground of plan['paths'] (_door_paths): the treads level across, the landings, the banks either side; the
    streets' pinned vertices, the plots' footprints and the guard polygons left alone. Points moved."""
    import landscape
    G, N = landscape.CELL, landscape.N
    vstep = G / (N - 1.0)
    pins = plan.get('_street_pins') or {}
    rects = [[tuple(p_) for p_ in q['rect']] for q in plan.get('plots') or () if q.get('b') and q.get('rect')]
    paths = plan.get('paths') or []
    if not paths:
        return 0

    plots_ = [q for q in plan.get('plots') or () if q.get('b') and q.get('rect')]

    def blocked(x, y, own=None):
        for q_, r in zip(plots_, rects):
            if _in_rect(r, x, y) and _own_side(q_, x, y):
                return True
        return bool(guard) and any(_in_rect(g_, x, y) for g_ in guard)
    xs = [x for p_ in paths for x, _y in p_['pts']]
    ys = [y for p_ in paths for _x, y in p_['pts']]
    pad = TREAD_HALF + FILL_BLEND + LANDING_R
    new_h, before, moved = {}, {}, 0
    for gx in range(int(math.floor((min(xs) - pad) / G)), int(math.floor((max(xs) + pad) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - pad) / G)), int(math.floor((max(ys) + pad) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(N):
                for i in range(N):
                    x, y = gx * G + i * vstep, gy * G + j * vstep
                    if (x, y) in pins:
                        continue
                    n = j * N + i
                    z0 = h[n]
                    if z0 < 0:
                        continue
                    # (the nearest centre line or landing, by its own distance, then how far outside its tread: where two
                    # stretches of a way came within a tread of each other, the first found set the vertex and the other
                    # stretch's tread was 80 off level across, lab 2026-11-07)
                    lat, tz, raw, own = None, None, None, None
                    for p_ in paths:
                        dx_, dy_ = x - p_['door'][0], y - p_['door'][1]
                        dl = math.hypot(dx_, dy_)
                        if raw is None or dl - LANDING_R < raw:
                            raw, lat, tz, own = dl - LANDING_R, max(0.0, dl - LANDING_R), p_['z'][0], p_.get('own')
                        pts, zs = p_['pts'], p_['z']
                        for k in range(len(pts) - 1):
                            ax, ay = pts[k]
                            bx, by = pts[k + 1]
                            dx, dy = bx - ax, by - ay
                            L2 = dx * dx + dy * dy
                            if not L2:
                                continue
                            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
                            dl = math.hypot(x - ax - dx * t, y - ay - dy * t)
                            if dl - TREAD_HALF < raw:
                                raw, lat, tz, own = dl - TREAD_HALF, max(0.0, dl - TREAD_HALF), zs[k] + (zs[k + 1] - zs[k]) * t, p_.get('own')
                    if tz is None or lat >= FILL_BLEND:
                        continue
                    if blocked(x, y, own):
                        continue
                    if lat <= 0:
                        nz = tz
                    else:
                        blend = CUT_BLEND if z0 > tz else FILL_BLEND
                        if lat >= blend:
                            continue
                        w = 0.5 + 0.5 * math.cos(math.pi * lat / blend)
                        nz = z0 + w * (tz - z0)
                    if abs(nz - z0) >= 1:
                        h[n] = nz
                        changed = True
                        moved += 1
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return moved


def _own_side(q, x, y):
    """Is (x, y) on the building's side of plot q's door line (its yard in front of the door is the other side)? A way out
    of a door may cross its own plot's yard, and its tread is cut there (a notch in the terrace's edge, as the user's hand
    paths do), never the building's side."""
    c, sn, _yaw = _frame(q['face'])
    dx, dy = x - q['door'][0], y - q['door'][1]
    ly = dx * sn + dy * c                        # (the frame's +y: into the plot)
    return ly > -40


def _grown(r, w):
    """A quad grown w outward on every side."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = r[:4]
    ul = math.hypot(x1 - x0, y1 - y0) or 1.0
    vl = math.hypot(x3 - x0, y3 - y0) or 1.0
    ux, uy = (x1 - x0) / ul * w, (y1 - y0) / ul * w
    vx, vy = (x3 - x0) / vl * w, (y3 - y0) / vl * w
    return [(x0 - ux - vx, y0 - uy - vy), (x1 + ux - vx, y1 + uy - vy), (x2 + ux + vx, y2 + uy + vy), (x3 - ux + vx, y3 - uy + vy)]


def _find_path(plan, zat, blocked, fx, fy, ex, ey, tread_pts=()):
    """[(x, y)] from the door's front to the street's levelled ground (or an earlier path), the cheapest way on a
    PATH_STEP lattice: each move's grade under PATH_MAX, its ground within PATH_CUT below and PATH_FILL above its line,
    through no building or guard; cost = length, and more the steeper over PATH_GRADE. None when there is none."""
    import heapq
    S = PATH_STEP
    x0, y0 = min(fx, ex) - PATH_PAD, min(fy, ey) - PATH_PAD
    nx, ny = int((abs(ex - fx) + 2 * PATH_PAD) // S) + 1, int((abs(ey - fy) + 2 * PATH_PAD) // S) + 1
    si, sj = int(round((fx - x0) / S)), int(round((fy - y0) / S))
    near = {}

    def ok(i, j):
        if (i, j) not in near:
            x, y = x0 + i * S, y0 + j * S
            z = zat(x, y)
            near[(i, j)] = z is not None and z >= 0 and (math.hypot(x - fx, y - fy) <= 200 or not blocked(x, y))
        return near[(i, j)]

    goal = {}
    pins = plan.get('_street_pins') or {}

    def at_goal(i, j):
        if (i, j) not in goal:
            x, y = x0 + i * S, y0 + j * S
            sd = _street_dist(plan, x, y)
            g = sd is not None and sd <= STREET_EDGE
            if not g and pins:
                # (the square's and the junctions' levelled ground too: pinned vertices, which a tread may not take)
                g = (float(round(x / 128.0) * 128), float(round(y / 128.0) * 128)) in pins
            if not g and tread_pts:
                g = any(abs(x - tx) <= S and abs(y - ty) <= S for tx, ty in tread_pts)
            goal[(i, j)] = g
        return goal[(i, j)]
    dist = {(si, sj): 0.0}
    plen = {(si, sj): 0.0}
    maxlen = PATH_WANDER * math.hypot(ex - fx, ey - fy) + PATH_PAD
    prev = {}
    heap = [(0.0, si, sj)]
    seen = 0
    while heap:
        c, i, j = heapq.heappop(heap)
        if c > dist.get((i, j), 1e18):
            continue
        if at_goal(i, j) and (i, j) != (si, sj):
            way, k = [], (i, j)
            while k in prev:
                way.append((x0 + k[0] * S, y0 + k[1] * S))
                k = prev[k]
            way.append((fx, fy))
            return way[::-1]
        seen += 1
        if seen > 20000:
            return None
        zi = zat(x0 + i * S, y0 + j * S)
        for da, db_ in _MOVES:
            a, b = i + da, j + db_
            if a < 0 or b < 0 or a >= nx or b >= ny or not ok(a, b):
                continue
            zb = zat(x0 + a * S, y0 + b * S)
            if zb is None:
                continue
            ln = S * math.hypot(da, db_)
            g = abs(zb - zi) / ln
            if g > PATH_MAX:
                continue
            m = max(abs(da), abs(db_))
            bad = False
            for t in range(1, m):
                u = t / float(m)
                xi, yi = i + da * u, j + db_ * u
                if not ok(int(round(xi)), int(round(yi))):
                    bad = True
                    break
                # (a move may cross a street's levelled ground only to end on it: one clipped a street's corner midway and
                # its tread lay over the street's pinned vertices, put back 234 over it by the repin, lab 2026-11-07)
                if at_goal(int(round(xi)), int(round(yi))) and not at_goal(a, b):
                    bad = True
                    break
                zm = zat(x0 + xi * S, y0 + yi * S)
                line = zi + (zb - zi) * u
                if zm is None or zm - line > PATH_CUT or line - zm > PATH_FILL:
                    bad = True
                    break
            if bad:
                continue
            nc = c + ln * (1.0 + 12.0 * max(0.0, g - 0.8 * PATH_GRADE) / PATH_GRADE)
            nl = plen[(i, j)] + ln
            if nl <= maxlen and nc < dist.get((a, b), 1e18):
                dist[(a, b)] = nc
                plen[(a, b)] = nl
                prev[(a, b)] = (i, j)
                heapq.heappush(heap, (nc, a, b))
    return None


def _tread_guard(plan):
    """[[(x, y) x4]] over each footpath's tread and landing (plan['paths']), a little wider: the wall's fill and the other
    ground passes after the paths keep off them (the fill under Firuhn's south wall raised the ground 100-330 back over
    four treads, lab 2026-11-07)."""
    out = []
    w = TREAD_HALF + 64
    for p_ in plan.get('paths') or ():
        pts = p_['pts']
        for k in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            L = math.hypot(bx - ax, by - ay)
            if L < 1:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            ax, ay, bx, by = ax - ux * 64, ay - uy * 64, bx + ux * 64, by + uy * 64
            out.append([(ax - uy * w, ay + ux * w), (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w), (ax + uy * w, ay - ux * w)])
        dx, dy = p_['door']
        r = LANDING_R + 64
        out.append([(dx - r, dy - r), (dx + r, dy - r), (dx + r, dy + r), (dx - r, dy + r)])
    return out


def _tread_profile(zat, way, z_start):
    """The tread's height at each point of a way: the ground there, lowered to PATH_EDGE over the downhill edge's ground
    (a cut, not a bank), smoothed, no stretch steeper than PATH_MAX, the door's end at its front's ground."""
    zs = []
    for k, (x, y) in enumerate(way):
        z = zat(x, y)
        if z is None:
            z = zs[-1] if zs else z_start
        # (downhill: the way the ground falls, from four neighbours)
        zx = ((zat(x + 64, y) or z) - (zat(x - 64, y) or z)) / 128.0
        zy = ((zat(x, y + 64) or z) - (zat(x, y - 64) or z)) / 128.0
        s = math.hypot(zx, zy)
        if s > 0.05:
            ze = zat(x - TREAD_HALF * zx / s, y - TREAD_HALF * zy / s)
            if ze is not None:
                z = min(z, ze + PATH_EDGE)
        zs.append(z)
    zs[0] = z_start
    z_end = zat(way[-1][0], way[-1][1])            # (the street's own level where the way meets it: no lowering there, its
    if z_end is not None:                          # pinned vertices stay and the tread ran into them 40-330 under)
        zs[-1] = z_end
    if len(zs) > 2:
        sm = [zs[0]] + [(zs[k - 1] + 2 * zs[k] + zs[k + 1]) / 4.0 for k in range(1, len(zs) - 1)] + [zs[-1]]
        zs = sm
    # (no stretch steeper than PATH_MAX with both ends held: a clamp from the door's end, then one from the street's,
    # over and over; the way's own ground is such a profile, so they meet)
    for _ in range(6):
        for k in range(1, len(zs)):
            L = max(1.0, math.hypot(way[k][0] - way[k - 1][0], way[k][1] - way[k - 1][1]))
            zs[k] = max(zs[k - 1] - PATH_MAX * L, min(zs[k - 1] + PATH_MAX * L, zs[k]))
        if z_end is not None:
            zs[-1] = z_end
        for k in range(len(zs) - 2, -1, -1):
            L = max(1.0, math.hypot(way[k][0] - way[k + 1][0], way[k][1] - way[k + 1][1]))
            zs[k] = max(zs[k + 1] - PATH_MAX * L, min(zs[k + 1] + PATH_MAX * L, zs[k]))
        zs[0] = z_start
    return zs


SMOOTH_PAD = 512               # (the town's ground is rounded this far beyond its outline)
SMOOTH_ROUNDS = 3
SMOOTH_TOL = 48                # (a kinked point moves this much a round at most)


VERGE_GRADE = 0.55             # (the ground beside a street climbs or falls away from it this much a unit at most,
VERGE_REACH = 5                # this many land points out: the passes after the streets (the wall's fill inside, the buildings' ground
                               # fits) moved the ground round them and the streets were put back at their level, in a trench with
                               # a sheer side or on a causeway: over half of a made hill town's bare steep ground, six lab towns,
                               # 2026-11-10. Steep is 0.7 by the measure; the game's towns stand on little of it bare)


VERGE_FAR = 16                 # (a bank still too steep at VERGE_REACH is carried on until it meets the ground, this far at most:
                               # stopped at five points, a deep cut left a sheer step at the fifth, the lab's Redoran 2026-11-10)


def _ease_verges(db, plan, outline, skip=(), guard=(), W=None):
    """The ground beside the streets eased to VERGE_GRADE from the streets' own level, VERGE_REACH points out: a sheer
    side by a street becomes a bank. The streets' pinned points, the plots (a step wider), the footpaths' treads and
    landings, the guard polygons and the wall's own ground are left as they are, and no bank is eased through them;
    where two streets' levels ask for different heights the ground stays. What stands there follows. Points moved."""
    import landscape
    import landrange
    import townwalls
    pins = plan.get('_street_pins') or {}
    poly = [(float(p_[0]), float(p_[1])) for p_ in outline or ()]
    if not pins or len(poly) < 3:
        return 0
    xs, ys = [p_[0] for p_ in pins], [p_[1] for p_ in pins]
    G_ = landscape.CELL
    pad = (VERGE_REACH + 1) * G_ / 64.0
    x0, y0 = int(math.floor((min(xs) - pad) / G_)), int(math.floor((min(ys) - pad) / G_))
    x1, y1 = int(math.floor((max(xs) + pad) / G_)), int(math.floor((max(ys) + pad) / G_))
    F = landrange.Grid(db, x0, y0, x1, y1)
    if not F.land:
        return 0
    step = G_ / 64.0
    keeps = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    keeps = [_grown(r, 64) for r in keeps] + list(guard or ()) + _tread_guard(plan)
    try:
        keeps += townwalls.wall_guard(db, (W or {}).get('outline') or poly, mine=())
    except Exception:
        pass
    at = lambda i, j: ((x0 * 64 + i) * step, (y0 * 64 + j) * step)
    hi, lo = {}, {}
    for (x, y), z in pins.items():
        i, j = int(round(x / step)) - x0 * 64, int(round(y / step)) - y0 * 64
        if 0 <= i < F.w and 0 <= j < F.h:
            hi[(i, j)] = lo[(i, j)] = z
    front = set(hi)
    street = set(hi)
    held = {}
    hz, hd = dict(hi), {k_: 0.0 for k_ in hi}       # (the street level each point's upper line comes from, and how far)
    ends = {}                                       # (kept ground a bank runs into: the wall's foot, a plot)

    def fixed(i, j):
        if (i, j) not in held:
            x, y = at(i, j)
            held[(i, j)] = F.z[j * F.w + i] < 0 or any(_in_rect(k_, x, y) for k_ in keeps)
        return held[(i, j)]
    for _round in range(VERGE_FAR):
        if _round >= VERGE_REACH:
            front = {f_ for f_ in front if not (lo[f_] - 8 <= F.z[f_[1] * F.w + f_[0]] <= hi[f_] + 8)}
            if not front:
                break
        nxt = set()
        for (i, j) in front:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                n = (i + di, j + dj)
                if n in street or not (0 <= n[0] < F.w and 0 <= n[1] < F.h):
                    continue
                if fixed(*n):
                    ends[n] = F.z[n[1] * F.w + n[0]]
                    continue
                d = VERGE_GRADE * step * (1.4142 if di and dj else 1.0)
                a, b = hi[(i, j)] + d, lo[(i, j)] - d
                if n not in hi or a < hi[n] - 1e-6:
                    hi[n] = a
                    hz[n], hd[n] = hz[(i, j)], hd[(i, j)] + d / VERGE_GRADE
                    nxt.add(n)
                if n not in lo or b > lo[n] + 1e-6:
                    lo[n] = b
                    nxt.add(n)
        front = nxt
    # (a bank cut down to a street and running into higher kept ground, the wall's foot on its fill most of all, left a
    # sheer step at that ground's edge: there the bank runs evenly from the street up to it instead)
    fz, fd = {}, {}
    front = set()
    for (i, j), z_ in ends.items():
        if z_ < 0:
            continue
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (i + di, j + dj)
            if n in hi and n not in street and (n not in fz or z_ - VERGE_GRADE * step > fz[n] - VERGE_GRADE * fd[n]):
                fz[n], fd[n] = z_, step
                front.add(n)
    for _round in range(VERGE_FAR):
        nxt = set()
        for (i, j) in front:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                n = (i + di, j + dj)
                if n not in hi or n in street:
                    continue
                d = fd[(i, j)] + step * (1.4142 if di and dj else 1.0)
                if n not in fz or fz[(i, j)] - VERGE_GRADE * d > fz[n] - VERGE_GRADE * fd[n] + 1e-6:
                    fz[n], fd[n] = fz[(i, j)], d
                    nxt.add(n)
        front = nxt
    before = {gx_gy: F.cell(*gx_gy) for gx_gy in F.land}
    moved = 0
    for (i, j), a in hi.items():
        if (i, j) in street:
            continue
        b = lo[(i, j)]
        if b > a:
            continue                              # (two streets at two levels: the ground between them stays)
        n = j * F.w + i
        z = F.z[n]
        nz = min(max(z, b), a)
        if nz < z and (i, j) in fz and fz[(i, j)] - VERGE_GRADE * fd[(i, j)] > a:
            ds_, dw_ = hd[(i, j)], fd[(i, j)]
            nz = min(z, max(a, (hz[(i, j)] * dw_ + fz[(i, j)] * ds_) / (ds_ + dw_)))
        if abs(nz - z) >= 8:
            F.z[n] = nz
            moved += 1
    if not moved:
        return 0
    changed = {}
    for gx_gy in F.land:
        h = F.cell(*gx_gy)
        if any(abs(p_ - q_) >= 1 for p_, q_ in zip(h, before[gx_gy])):
            changed[gx_gy] = h
    for (gx, gy), h in changed.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, changed))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if changed:
        db.sync_project()
    return moved


def _smooth_kinks(db, plan, outline, skip=(), guard=(), W=None):
    """The kinks left in a made town's ground (landpasses.KINK: a vertex off its neighbours' mean across 128 by more
    than 48, x or y) rounded off over the outline and SMOOTH_PAD round it, SMOOTH_ROUNDS rounds of SMOOTH_TOL at most;
    the streets' pinned vertices, the plots (a step wider), the footpaths' treads and landings, the guard polygons
    and the wall's own ground (its pieces' footprints) are left as they are. What stands on the ground follows it.
    The kinks at first."""
    import landscape
    import landrange
    import landpasses
    import townwalls
    poly = [(float(p_[0]), float(p_[1])) for p_ in outline or ()]
    if len(poly) < 3:
        return 0
    xs, ys = [p_[0] for p_ in poly], [p_[1] for p_ in poly]
    G_ = landscape.CELL
    x0, y0 = int(math.floor((min(xs) - SMOOTH_PAD) / G_)), int(math.floor((min(ys) - SMOOTH_PAD) / G_))
    x1, y1 = int(math.floor((max(xs) + SMOOTH_PAD) / G_)), int(math.floor((max(ys) + SMOOTH_PAD) / G_))
    F = landrange.Grid(db, x0, y0, x1, y1)
    if not F.land:
        return 0
    step = G_ / 64.0
    F.step = step
    F.hold = None
    keeps = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    keeps = [_grown(r, 64) for r in keeps] + list(guard or ()) + _tread_guard(plan)
    try:
        keeps += townwalls.wall_guard(db, (W or {}).get('outline') or poly, mine=())
    except Exception:
        pass
    pins = plan.get('_street_pins') or {}
    import townplan
    inside = bytearray(len(F.z))
    keep = [0.0] * len(F.z)
    for j in range(F.h):
        y = (y0 * 64 + j) * step
        for i in range(F.w):
            x = (x0 * 64 + i) * step
            n = j * F.w + i
            if F.z[n] < 0:
                continue
            if not (townplan._inside(poly, x, y) or townplan._edge_dist(poly, x, y) <= SMOOTH_PAD):
                continue
            inside[n] = 1
            if (x, y) in pins or any(_in_rect(k_, x, y) for k_ in keeps):
                keep[n] = 1.0
    before = {gx_gy: F.cell(*gx_gy) for gx_gy in F.land}
    n_first = landpasses.corners(F, inside, tol=SMOOTH_TOL, rounds=SMOOTH_ROUNDS, keep=keep)
    changed = {}
    for gx_gy in F.land:
        h = F.cell(*gx_gy)
        if any(abs(a - b) >= 1 for a, b in zip(h, before[gx_gy])):
            changed[gx_gy] = h
    for (gx, gy), h in changed.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, changed))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if changed:
        db.sync_project()
    return n_first if changed else 0


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


HIGH_DOOR = 100                # a side door's foot this far over the ground before it, after the ground is done: left out
DOOR_STEP = re.compile(r'entrance|porch|stoop|step|doorframe|door_frame|awning|sign', re.I)


def _drop_high_doors(db, plan, new_refs):
    """The buildings' other doors (more_doors) that ended up HIGH_DOOR or more over the ground in front of them, taken
    out with their own steps, frames, awnings and signs: the ground is brought up to every door (groundfit), but a
    street pinned level under a side door is put back, and the door stood 140 over it with its step in the air, an
    interior behind it (the user's Senchal, 2026-11-11: "some of the ground is too low by the entrance"). The count."""
    p = db.project
    n = 0
    for q in plan['plots']:
        if not q.get('b') or not q.get('more_doors') or not q.get('rect'):
            continue
        cx, cy = sum(v[0] for v in q['rect']) / 4.0, sum(v[1] for v in q['rect']) / 4.0
        keep = []
        for key, rk in q['more_doors']:
            refs = mapdata.cellmap(db, key).get('refs') or ()
            r = next((x for x in refs if x['k'] == rk), None)
            if r is None or not r.get('b'):
                keep.append((key, rk))
                continue
            foot = r['p'][2] + r['b'][2] * (r.get('s') or 1.0)
            ux, uy = r['p'][0] - cx, r['p'][1] - cy
            h = math.hypot(ux, uy) or 1.0
            # (out of the building, along the door's own facing: the way of the two that leads away from its middle)
            fx, fy = -math.sin(r['p'][5]), -math.cos(r['p'][5])
            if fx * ux + fy * uy < 0:
                fx, fy = -fx, -fy
            gs = [mapdata.terrain_z(db, r['p'][0] + fx * d_, r['p'][1] + fy * d_) for d_ in (70, 120)]
            if None in gs or foot - max(gs) < HIGH_DOOR:
                keep.append((key, rk))
                continue
            gid = p.town_parts.get(rk)
            out = [(key, rk)]
            for x in refs:
                if x['k'] != rk and x['k'] in new_refs and p.town_parts.get(x['k']) == gid and DOOR_STEP.search(x['id'])                         and x['type'] != 'DOOR' and math.hypot(x['p'][0] - r['p'][0], x['p'][1] - r['p'][1]) <= LONE_WITH and abs(x['p'][2] - r['p'][2]) < 260:
                    out.append((key, x['k']))
            for ck, k_ in out:
                c = p.cells.get(ck)
                if c and k_ in (c.get('refs') or {}):
                    c['refs'].pop(k_)
                    p.town_parts.pop(k_, None)
                    new_refs.discard(k_)
            q['door_pieces'] = [dp for dp in q.get('door_pieces') or () if dp.get('rk') != rk]
            n += 1
        q['more_doors'] = keep
    return n


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
        mine_ = next((r for d, r in plots if d == (key, rk)), None)
        others = [r for d, r in plots if r is not mine_ and d != (key, rk)]
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
