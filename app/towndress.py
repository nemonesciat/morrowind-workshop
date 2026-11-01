"""Towns dressed the way the game dresses its own: what stands round each building's door (a smith's forge and
anvil, a tavern's sign and benches, a trader's crates, lanterns by a manor), what stands along the streets (lamps,
carts, benches, crates) and what stands in the squares (a well, a shrine, a market's barrels), learnt from the game's
towns by culture and kind of building.

  learn(db)   {'yards': {culture: {kind: [scene]}}, 'street': {culture: {'groups': [scene], 'per_road'}},
              'square': {culture: [scene]}, 'smith': {culture: share of shops}} (on disk). A scene is what stood
              round one game building's door (or together by a street, or in a square), whole, in its own frame
  dress(db, plan, rng, blocked)   the things for a town being made: [{'id', 'p': [x, y, z, rx, ry, rz], 's'}]

Only dressing: things a town sets out, never the pieces of a building (its windows, beams, awnings, railings: the
first survey took those too, lab 2026-10-30), never things hung anywhere but by the door (a sign or a lantern on the
wall beside it stands on any building; a rope strung between two shacks does not).
"""
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

import mapdata
import townsurvey

VERSION = 6                     # (6: the Anvil and Gold Coast cultures, out of Imperial)
YARD = 650                     # what stands this near a door, and before or beside it, is its yard's
BEHIND = 250                   # (beside the building, up to this far behind the door's line)
BIG = 600                      # things this long or more are buildings, walls, docks: not dressing
HANG = 60                      # a thing this far over the ground under it hangs on the building (a sign, a lantern)
BY_DOOR = 260                  # a hung thing is kept only this near the door, sideways, and on its wall (|y| < 60)
GROUP = 260                    # street things this near each other stand together as one group
DOOR_CLEAR = (110, 170)        # a door's way in kept clear: this far either side and out in front
TYPES = ('STAT', 'CONT', 'LIGH', 'ACTI', 'MISC', 'APPA', 'INGR', 'ALCH', 'CLOT', 'WEAP', 'ARMO')
DRESS = re.compile(r'bench|stool|chair|table|barrel|crate|sack|basket|urn|_pot|pot_|planter|well|lamp|lantern|'
                   r'lightpost|torch|sign|banner|cart|anvil|forge|bellows|grindstone|coal|cauldron|bucket|hay|woodpile|'
                   r'firewood|firepit|fire|statue|shrine|cage|keg|tub|trough|scarecrow|kiln|rack|stall|wheelbarrow|'
                   r'shovel|crate|chest|box|log_?pile|altar|totem|brazier|tent|guarskin|hide|dummy|target|pole_?banner')
NOT_DRESS = re.compile(r'wall|gate|tower|bridge|dock|stair|steps|_road|platform|collision|marker|^sound|terrain|_door|'
                       r'pylon|propylon|canal|waterfall|pier|_plat|foundation|floor|ramp|roof|window|beam|plank|awning|'
                       r'constr|buttress|pillar|arrowslit|frame|dormer|chimney|column|entrance|overhang|hook|rope|root|'
                       r'brace|stem|spike|block|struct|rubble|grave|railing|fence|fencepost|mooring|bollard|_ruin|'
                       r'waterjet|water_|scrapwood|shack_|skywalk|^in_|_in_|^ex_t_|light_.*off$|_unique|^key_|_key$|gold_')
# a culture's own scenes, the town's story: Telvanni slave pods and markets, gallows, chicken coops, caged crates
LANDMARK = re.compile(r'slavepod|slavemarket|gallows|chickencage|cagechicken|cratecage|storagecage|ropenoose|stocks|pillory')
LANDMARK_NEAR = 350            # what stands this near a landmark is its scene's


def _disk(db):
    import taste
    folder = os.path.join(os.environ.get('WORKSHOP_HOME') or os.path.dirname(os.path.abspath(__file__)), 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'towndress_%s_v%d.json' % (taste.sig(db), VERSION))


_mem = {}


def learn(db):
    k = id(db.recs)
    if k in _mem:
        return _mem[k]
    path = _disk(db)
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                _mem[k] = json.load(f)
                return _mem[k]
        except (OSError, ValueError):
            pass
    out = _learn(db)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except OSError:
        pass
    _mem[k] = out
    return out


def ready(db):
    """What the game sets out in its towns if learnt; else None, and the survey process learns it meanwhile."""
    if id(db.recs) in _mem or os.path.isfile(_disk(db)):
        try:
            return learn(db)
        except Exception:
            return None
    import background
    background.start('how the game dresses its towns', lambda: learn(db), task=('towndress', 'learn', []))
    return None


def _dressing(r):
    """A ref that dresses a town: small enough, set out, not land, not a building's piece, not a person."""
    import landscape
    low = r['id'].lower()
    if r['type'] not in TYPES or not r.get('b'):
        return False
    if landscape.NATURAL.search(low) or NOT_DRESS.search(low):
        return False
    if r['type'] == 'STAT' and not DRESS.search(low):
        return False
    b, s = r['b'], r['s'] or 1.0
    return max(b[3] - b[0], b[4] - b[1]) * s < BIG and (b[5] - b[2]) * s >= 4


def _local(x, y, ang, wx, wy):
    """A world point in a frame turned ang (the game's clockwise turn), origin (x, y)."""
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = wx - x, wy - y
    return dx * c - dy * s, dx * s + dy * c


def _world(x, y, ang, lx, ly):
    c, s = math.cos(ang), math.sin(ang)
    return x + lx * c + ly * s, y - lx * s + ly * c


def _in_box(box, x, y, pad=0.0):
    return box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad


def _thing(r, ox, oy, ang, z0, hang):
    lx, ly = _local(ox, oy, ang, r['p'][0], r['p'][1])
    return {'id': r['id'], 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(z0, 1), 'hang': hang,
            'rz': round((r['p'][5] - ang) % (2 * math.pi), 4), 'rx': round(r['p'][3], 4), 'ry': round(r['p'][4], 4),
            's': r['s'] or 1.0}


def _learn(db):
    yards = defaultdict(lambda: defaultdict(list))
    street = defaultdict(lambda: {'groups': [], 'road': 0})
    square = defaultdict(list)
    smith = defaultdict(lambda: [0, 0])
    marks = defaultdict(lambda: {'scenes': [], 'towns': 0})
    for t in townsurvey.survey(db)['towns']:
        bl = [b for b in t['buildings'] if b.get('box')]
        if not bl:
            continue
        cult = t['culture'] or '?'
        roads = {tuple(int(v) for v in r.split(',')) for r in t['roads']}
        sqset = {p for p in roads if all((p[0] + i, p[1] + j) in roads for i in (-1, 0, 1) for j in (-1, 0, 1))}
        scenes = defaultdict(list)
        loose, in_sq = [], []
        allrefs = [r for gx, gy in t['cells'] for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()]
        marks[cult]['towns'] += 1
        _landmarks(db, allrefs, marks[cult]['scenes'], t['name'])
        for gx, gy in t['cells']:
            for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
                if not _dressing(r):
                    continue
                x, y, z = r['p'][0], r['p'][1], r['p'][2]
                if any(_in_box(b['box'], x, y, -24) for b in bl):
                    continue                     # (inside a building: set into it)
                gz = mapdata.terrain_z(db, x, y)
                if gz is None:
                    continue
                best = None
                for i, b in enumerate(bl):
                    d = math.hypot(x - b['x'], y - b['y'])
                    if d > YARD:
                        continue
                    lx, ly = _local(b['x'], b['y'], b['face'] + math.pi, x, y)
                    if ly > BEHIND:
                        continue
                    if best is None or d < best[0]:
                        best = (d, i, lx, ly)
                up = z - gz
                hang = up > HANG
                if best:
                    _d, i, lx, ly = best
                    b = bl[i]
                    if hang and (abs(lx) > BY_DOOR or abs(ly) > 60):
                        continue                 # (strung or hung on something that is not the door's wall)
                    scenes[i].append(_thing(r, b['x'], b['y'], b['face'] + math.pi, z - b['z'] if hang else up, hang))
                elif not hang:
                    patch = (int(x // 512), int(y // 512))
                    if patch in sqset:
                        in_sq.append((r, up))
                    elif any((patch[0] + i, patch[1] + j) in roads for i in (-1, 0, 1) for j in (-1, 0, 1)):
                        loose.append((r, up))
        for i, b in enumerate(bl):
            things = scenes.get(i, [])
            if len(things) > 24:
                continue                         # (a market or a camp, not one building's yard)
            kind = b.get('kind') or 'house'
            if kind == 'shop':
                is_smith = bool(re.search(r'smith|armor|armour|forge', (b.get('interior') or '').lower()))
                smith[cult][0] += is_smith
                smith[cult][1] += 1
                if is_smith:
                    kind = 'smith'
            yards[cult][kind].append({'town': t['name'], 'fw': b.get('fw'), 'things': things})
        # street groups: things standing together, framed toward the nearest road
        S = street[cult]
        S['road'] += len(roads) - len(sqset)
        for grp in _groups(loose):
            cx = sum(r['p'][0] for r, _u in grp) / len(grp)
            cy = sum(r['p'][1] for r, _u in grp) / len(grp)
            ang = _toward_road(cx, cy, roads)
            if ang is None:
                continue
            S['groups'].append({'town': t['name'], 'things': [_thing(r, cx, cy, ang, up, False) for r, up in grp]})
        if in_sq:
            cx = sum(r['p'][0] for r, _u in in_sq) / len(in_sq)
            cy = sum(r['p'][1] for r, _u in in_sq) / len(in_sq)
            square[cult].append({'town': t['name'], 'things': [_thing(r, cx, cy, 0.0, up, False) for r, up in in_sq
                                                               if math.hypot(r['p'][0] - cx, r['p'][1] - cy) < 900]})
    return {'yards': {c: dict(v) for c, v in yards.items()},
            'street': {c: {'groups': v['groups'], 'per_road': round(len(v['groups']) / float(max(1, v['road'])), 4)} for c, v in street.items()},
            'square': dict(square),
            'smith': {c: round(v[0] / float(max(1, v[1])), 3) for c, v in smith.items()},
            'marks': {c: {'scenes': v['scenes'], 'per_town': round(len(v['scenes']) / float(max(1, v['towns'])), 3)}
                      for c, v in marks.items() if v['scenes']}}


def _landmarks(db, refs, out, town):
    """The town's landmark scenes: each landmark with what stands round it (its door, the crates and cages by it), in
    its own frame; landmarks near one already taken are part of that scene."""
    taken = set()
    for r in refs:
        low = r['id'].lower()
        if not LANDMARK.search(low) or r['type'] == 'DOOR' or r['k'] in taken or not r.get('b'):
            continue
        x, y, ang = r['p'][0], r['p'][1], r['p'][5]
        things = []
        for q in refs:
            if math.hypot(q['p'][0] - x, q['p'][1] - y) > LANDMARK_NEAR:
                continue
            ql = q['id'].lower()
            if not (q is r or LANDMARK.search(ql) or 'slave' in ql and q['type'] in ('STAT', 'DOOR') or _dressing(q)):
                continue
            if q['type'] in ('NPC_', 'CREA', 'LEVC'):
                continue
            gz = mapdata.terrain_z(db, q['p'][0], q['p'][1])
            if gz is None:
                continue
            taken.add(q['k'])
            things.append(_thing(q, x, y, ang, q['p'][2] - gz, False))
        if things and len(things) <= 12:          # (more is a farmyard round it, not its scene)
            out.append({'town': town, 'mark': r['id'], 'things': things})


def _groups(items):
    """Things standing together (each within GROUP of another), up to 8 a group."""
    left = list(items)
    out = []
    while left:
        grp = [left.pop()]
        i = 0
        while i < len(grp) and len(grp) < 8:
            r = grp[i][0]
            for j in range(len(left) - 1, -1, -1):
                q = left[j][0]
                if math.hypot(q['p'][0] - r['p'][0], q['p'][1] - r['p'][1]) <= GROUP:
                    grp.append(left.pop(j))
            i += 1
        out.append(grp)
    return out


def _toward_road(x, y, roads):
    """The frame whose -y points from (x, y) to the middle of the nearest road patch (things by a street face it)."""
    best = None
    px, py = int(x // 512), int(y // 512)
    for i in range(-2, 3):
        for j in range(-2, 3):
            p = (px + i, py + j)
            if p in roads:
                mx, my = p[0] * 512 + 256, p[1] * 512 + 256
                d = math.hypot(mx - x, my - y)
                if best is None or d < best[0]:
                    best = (d, mx, my)
    if best is None or best[0] < 1:
        return None
    # (the frame's -y is toward the road: world dir of local (0, -1) is (-sin a, -cos a))
    dx, dy = (best[1] - x) / best[0], (best[2] - y) / best[0]
    return math.atan2(-dx, -dy)


# ------------------------------------------------------------------------------------------------ dressing a town
def _rect_of(id_, x, y, rz, s, memo, db):
    if id_ not in memo:
        ri = db.resolve_id(id_)
        memo[id_] = mapdata.object_bounds(db, ri) if ri is not None else None
    b = memo[id_]
    if not b:
        return None, None
    c, sn = math.cos(rz), math.sin(rz)
    pts = [(x + bx * s * c + by * s * sn, y - bx * s * sn + by * s * c) for bx, by in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4]))]
    return pts, b


def _overlap(a, b):
    import townplan
    return townplan._overlap(a, b)


class _Space:
    """What a town's dressing must keep clear of: its buildings, its wall, its doors' ways in, what it set already."""

    def __init__(self, blocked):
        self.polys = [list(p) for p in blocked]

    def free(self, pts):
        return not any(_overlap(pts, p) for p in self.polys)

    def take(self, pts):
        self.polys.append(pts)


def _lay(db, scene, ox, oy, ang, space, memo, door_z=None, keep=None):
    """A scene's things set down in a frame at (ox, oy) turned ang; those that would not fit are left out."""
    out = []
    for t in scene['things']:
        if keep and not keep(t):
            continue
        wx, wy = _world(ox, oy, ang, t['x'], t['y'])
        rz = (t['rz'] + ang) % (2 * math.pi)
        pts, b = _rect_of(t['id'], wx, wy, rz, t.get('s') or 1.0, memo, db)
        if not pts:
            continue
        if t['hang']:
            if door_z is None:
                continue
            z = door_z + t['z']
        else:
            gz = mapdata.terrain_z(db, wx, wy)
            if gz is None or gz < 0:
                continue
            z = gz + t['z']
            # (shrunk a little: things in a scene stand close, and their boxes are loose)
            if not space.free(_shrink(pts, 0.85)):
                continue
        out.append({'id': t['id'], 'p': [round(wx, 2), round(wy, 2), round(z, 2), t.get('rx') or 0.0, t.get('ry') or 0.0, round(rz, 5)],
                    's': t.get('s') or 1.0, 'pts': pts})
    for o in out:
        if not any(t['hang'] for t in scene['things'] if t['id'] == o['id']):
            space.take(o['pts'])
    return out


def _shrink(pts, f):
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return [(cx + (x - cx) * f, cy + (y - cy) * f) for x, y in pts]


def _behind_door(rect, x, y, face):
    """A building's outline from its door's wall in: the part behind the door's line (+y in the door's frame)."""
    ang = face + math.pi
    loc = [_local(x, y, ang, px, py) for px, py in rect]
    x0, x1 = min(p[0] for p in loc), max(p[0] for p in loc)
    y0, y1 = max(0.0, min(p[1] for p in loc)), max(p[1] for p in loc)
    return [_world(x, y, ang, lx, ly) for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def _door_clear(x, y, face):
    """The way into a door: kept clear of dressing."""
    ang = face + math.pi
    w, d = DOOR_CLEAR
    return [_world(x, y, ang, lx, ly) for lx, ly in ((-w, -d), (w, -d), (w, 20), (-w, 20))]


def dress(db, plan, seed=1, blocked=(), amount=1.0):
    """Things for a made town (plan as townbuild.fit made it, each plot with 'door_z' once built): a yard scene of its
    culture and kind before every building (a smithy's forge before some shops, as often as the culture's shops are
    smiths), groups along its streets as many as the culture's towns stand a road patch, and its square's. blocked:
    polygons kept clear (the wall's pieces). [{'id', 'p', 's', 'role'}]."""
    L = learn(db)
    cult = plan.get('culture')
    rng = random.Random('%s|%s|dress' % (seed, cult))
    near = _near_cultures(L, cult)
    rects = {id(q): [tuple(p) for p in q['rect']] for q in plan['plots'] if q.get('rect')}
    # (and what stood there already: slave pods went down over a walkway, lab 2026-10-30)
    space = _Space(list(blocked) + list(rects.values()) + [[tuple(p) for p in o] for o in plan.get('obstacles') or ()])
    for q in plan['plots']:
        if q.get('door') and q.get('b'):
            space.take(_door_clear(q['door'][0], q['door'][1], q['face']))
    memo = {}
    out = []
    smith_share = L.get('smith', {}).get(cult, 0.2)
    # yards
    for q in plan['plots']:
        if not q.get('b') or not q.get('door'):
            continue
        kind = q['kind']
        if kind == 'shop' and rng.random() < max(0.15, smith_share):
            kind = 'smith'
        sc = _yard_pick(L, near, kind, rng)
        if not sc or not sc['things'] or rng.random() > amount:
            continue
        fw = q['b'].get('w') or q.get('w') or 512
        lim = max(300.0, fw / 2.0 + 250)
        mirror = rng.random() < 0.5
        sc2 = {'things': [dict(t, x=-t['x'], rz=(-t['rz']) % (2 * math.pi)) if mirror else t for t in sc['things']]}
        # (its own outline cut back to the door's wall: the plot's outline reaches past it, porch and all, and
        # every thing by the door fell inside it, lab 2026-10-30)
        own = rects.get(id(q))
        if own in space.polys:
            space.polys.remove(own)
            cut = _behind_door(own, q['door'][0], q['door'][1], q['face'])
            space.take(cut)
        got = _lay(db, sc2, q['door'][0], q['door'][1], q['face'] + math.pi, space, memo, q.get('door_z'),
                   keep=lambda t: abs(t['x']) <= lim)
        if own is not None and own not in space.polys:
            space.polys.remove(cut)
            space.take(own)
        for g in got:
            g['role'] = 'yard:' + kind
        out.extend(got)
    # streets: groups at the street's edge, facing it
    roads = {tuple(r) for r in plan.get('roads') or ()}
    St = [(c, L['street'][c]) for c in near if c in L.get('street', {}) and L['street'][c]['groups']]
    if St and roads:
        per = St[0][1]['per_road']
        n = int(round(per * len(roads) * amount))
        edge = [p for p in roads if any((p[0] + i, p[1] + j) not in roads for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        rng.shuffle(edge)
        placed = 0
        for p in edge:
            if placed >= n:
                break
            # (just off the road: the side with no road)
            for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (p[0] + i, p[1] + j) in roads:
                    continue
                cx = p[0] * 512 + 256 + i * 330 + rng.uniform(-120, 120) * (j != 0)
                cy = p[1] * 512 + 256 + j * 330 + rng.uniform(-120, 120) * (i != 0)
                ang = math.atan2(i, j)               # (-y toward the road: local (0,-1) -> world (-i, -j))
                grp = rng.choice(St[0][1]['groups'])
                got = _lay(db, grp, cx, cy, ang, space, memo)
                if got:
                    for g in got:
                        g['role'] = 'street'
                    out.extend(got)
                    placed += 1
                break
    # the culture's own scenes, in open ground within the town
    M = L.get('marks', {}).get(cult)
    if M and M['scenes']:
        n = int(M['per_town'] * amount + rng.random())
        xs = [p[0] for q in plan['plots'] for p in q.get('rect') or ()]
        ys = [p[1] for q in plan['plots'] for p in q.get('rect') or ()]
        tries = 0
        while n > 0 and xs and tries < 60:
            tries += 1
            x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
            if (int(x // 512), int(y // 512)) in roads:
                continue
            sc = rng.choice(M['scenes'])
            got = _lay(db, sc, x, y, rng.uniform(0, 2 * math.pi), space, memo)
            # (whole or not at all: half a slave market is no scene)
            if len(got) < len(sc['things']):
                for g in got:
                    space.polys.remove(g['pts'])
                continue
            for g in got:
                g['role'] = 'scene'
            out.extend(got)
            n -= 1
    # the square
    if plan.get('square'):
        sx, sy, _r = plan['square']
        for c in near:
            scs = [s for s in L.get('square', {}).get(c, ()) if s['things']]
            if scs:
                got = _lay(db, rng.choice(scs), sx, sy, rng.choice((0, 1, 2, 3)) * math.pi / 2, space, memo)
                for g in got:
                    g['role'] = 'square'
                out.extend(got)
                break
    for o in out:
        o.pop('pts', None)
    return out


def _near_cultures(L, cult):
    """The culture first, then the others whose yards it would borrow from (the most yards first)."""
    cs = sorted(L['yards'], key=lambda c: -sum(len(v) for v in L['yards'][c].values()))
    kin = [c for c in townsurvey.KIN.get(cult, ()) if c in L['yards']]
    return ([cult] if cult in L['yards'] else []) + kin + [c for c in cs if c != cult and c not in kin]


def _yard_pick(L, near, kind, rng):
    """A game yard of the kind, the town's culture first: a scene of nothing as often as the game leaves a yard bare."""
    for c in near:
        sc = L['yards'].get(c, {}).get(kind) or []
        if len([s for s in sc if s['things']]) >= (1 if kind == 'smith' else 3):
            return rng.choice(sc)
    if kind != 'house':
        return _yard_pick(L, near, 'shop' if kind == 'smith' else 'house', rng)
    return None
