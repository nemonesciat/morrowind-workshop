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

VERSION = 12                    # (6: the Anvil and Gold Coast cultures, out of Imperial; 8: each building's own surroundings; 9: no ladders; 11: holders, posts, instances; 12: lights on their posts, post_lights)
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
NOT_DRESS = re.compile(r'wall|gate|tower|bridge|dock|stair|steps|ladder|_road|platform|collision|marker|^sound|terrain|_door|'
                       r'pylon|propylon|canal|waterfall|pier|_plat|foundation|floor|ramp|roof|window|beam|plank|awning|'
                       r'constr|buttress|pillar|arrowslit|frame|dormer|chimney|column|entrance|overhang|hook|rope|root|'
                       r'brace|stem|spike|block|struct|rubble|grave|railing|fence|fencepost|mooring|bollard|_ruin|'
                       r'waterjet|water_|scrapwood|shack_|skywalk|^in_|_in_|^ex_t_|light_.*off$|_unique|^key_|_key$|gold_')
# a culture's own scenes, the town's story: Telvanni slave pods and markets, gallows, chicken coops, caged crates
LANDMARK = re.compile(r'slavepod|slavemarket|gallows|chickencage|cagechicken|cratecage|storagecage|ropenoose|stocks|pillory')
LANDMARK_NEAR = 350            # what stands this near a landmark is its scene's


def _disk(db):
    import taste
    # (the Workshop's own cache folder, beside projects: under app\ the Setup removed it with the program files at every
    # install, and the strays, town dressing and town life were learnt again, minutes each, the user's 2026-11-09)
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
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
    around = defaultdict(list)
    pairs = []
    for t in townsurvey.survey(db)['towns']:
        bl = [b for b in t['buildings'] if b.get('box')]
        if not bl:
            continue
        cult = t['culture'] or '?'
        roads = {tuple(int(v) for v in r.split(',')) for r in t['roads']}
        sqset = {p for p in roads if all((p[0] + i, p[1] + j) in roads for i in (-1, 0, 1) for j in (-1, 0, 1))}
        scenes = defaultdict(list)
        srefs, posted = defaultdict(list), defaultdict(list)
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
                        # (strung or hung on something that is not the door's wall: kept only on a post of the yard's)
                        if HUNG_KIND.search(r['id']):
                            posted[('y', i)].append(r)
                        continue
                    scenes[i].append(_thing(r, b['x'], b['y'], b['face'] + math.pi, z - b['z'] if hang else up, hang))
                    srefs[i].append(r)
                elif not hang:
                    patch = (int(x // 512), int(y // 512))
                    if patch in sqset:
                        in_sq.append((r, up))
                    elif any((patch[0] + i, patch[1] + j) in roads for i in (-1, 0, 1) for j in (-1, 0, 1)):
                        loose.append((r, up))
                elif HUNG_KIND.search(r['id']):
                    posted['street'].append(r)
        # (a lantern on a lamp post stands on its post, whatever the post's distance from the door: the yard kept the
        # post and dropped its lantern, and a street group took no hung thing at all; a town had 16 of its 21 lamp
        # posts bare, lab ja2, as the user saw at Tessellated Shores, 2026-11-01)
        for i in list(scenes):
            b = bl[i]
            for r in posted.get(('y', i), ()):
                j = _post_of(r, srefs[i])
                if j is not None:
                    scenes[i].append(_thing(r, b['x'], b['y'], b['face'] + math.pi, r['p'][2] - b['z'], True))
                    scenes[i][-1]['on'] = j
                    scenes[i][-1]['dz_on'] = round(r['p'][2] - srefs[i][j]['p'][2], 1)
                    srefs[i].append(r)
                    pairs.append((srefs[i][j], r))
        _around(db, bl, allrefs, around, t['name'], pairs)
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
            things = [_thing(r, cx, cy, ang, up, False) for r, up in grp]
            grefs = [r for r, _u in grp]
            for r in posted.get('street', ()):
                j = _post_of(r, grefs)
                if j is not None:
                    gz = mapdata.terrain_z(db, r['p'][0], r['p'][1]) or 0.0
                    things.append(_thing(r, cx, cy, ang, r['p'][2] - gz, True))
                    things[-1]['on'] = j
                    things[-1]['dz_on'] = round(r['p'][2] - grefs[j]['p'][2], 1)
                    pairs.append((grefs[j], r))
            S['groups'].append({'town': t['name'], 'things': things})
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
                      for c, v in marks.items() if v['scenes']},
            'around': dict(around), 'post_lights': _post_lights(pairs)}


AROUND = 400                   # what stands this near a building's walls, and nearer it than any other, is its own
AROUND_MAX = 40                # (more round one building is a market or a farm, not its surroundings)
FENCE = re.compile(r'fence|railing|palisade')
HOLDER = re.compile(r'hook|bracket|chain|hanger|lightpost|lamp_?post|lightstand|signpost|sign_?post|lantern_?post|post_?lantern|signbase|sign_?base')
# (what holds a light, and is bare without one: a lamp post, a lantern hook or bracket)
LIGHT_HOLDER = re.compile(r'lightpost|lamp_?post|lantern_?post|post_?lantern|lightstand|(lantern|light|lamp)_?(hook|bracket)', re.I)
POST_NEAR = 120                # a light this near a holder, by its top, hangs from it
HUNG_KIND = re.compile(r'lantern|light|lamp|sign|banner', re.I)
SMALL_PLANT = re.compile(r'flora|plant|bush|kreshweed|marshmerrow|comberry|flower|shrub|herb|wickwheat|saltrice|heather')


def _around_thing(r):
    """Dressing, or a fence or a small plant: what a building's own surroundings hold."""
    if _dressing(r):
        return True
    low = r['id'].lower()
    if r['type'] != 'STAT' and r['type'] not in ('ACTI', 'CONT', 'INGR') or not r.get('b'):
        return False
    b, s = r['b'], r['s'] or 1.0
    size = max(b[3] - b[0], b[4] - b[1]) * s
    if FENCE.search(low) and 'gate' not in low:
        return size < BIG
    if HOLDER.search(low):
        return size < 400                        # (what a lantern or a sign hangs from)
    return bool(SMALL_PLANT.search(low)) and size < 300 and not re.search(r'tree|log|stump|rock', low)


def _around(db, bl, refs, out, town, pairs=None):
    """Each building's own surroundings, by its main piece, in its door frame: the barrels against its side, the bench
    under its window, its sign and lanterns, its own fence and flowers. The yard caught only what stood before the door,
    and the game sets most of a town's things round its buildings' other walls: a made town had a sixth of a game
    town's things to a building (the town audit of 2026-11-01, Common 0.6 vs 4.3, Reach 1.6 vs 11.5)."""
    def gap(b, x, y):
        x0, y0, x1, y1 = b['box'][:4]
        return math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1))
    got = defaultdict(list)
    for r in refs:
        if not _around_thing(r):
            continue
        x, y, z = r['p'][0], r['p'][1], r['p'][2]
        d = [(gap(b, x, y), i) for i, b in enumerate(bl) if b.get('main')]
        if not d:
            continue
        g, i = min(d)
        if g > AROUND:
            continue
        b = bl[i]
        gz = mapdata.terrain_z(db, x, y)
        if gz is None:
            continue
        up = z - gz
        foot = up + r['b'][2] * (r['s'] or 1.0)      # (by its foot: a sign post's origin is at its top, 300 up)
        if g <= 0 and foot <= STANDS_ON:
            continue                             # (inside the building: set into it)
        got[i].append((r, up, foot))
    for i, rs in got.items():
        if not 2 <= len(rs) <= AROUND_MAX:
            continue
        b = bl[i]
        things = []
        for r, up, foot in rs:
            # (off the ground and on none of the scene's own things: on the building itself, its porch, balcony,
            # awning or wall. Kept by its height over the door, as the building stands at the door: by the ground
            # its goods stood in the air off a porch and its ivy off the wall, the town audit of 2026-11-01)
            on_thing = foot > STANDS_ON and any(o is not r and o['b'] and _f <= STANDS_ON and _box_has(o, r['p'][0], r['p'][1])
                                                and abs(o['p'][2] + o['b'][5] * (o['s'] or 1.0) - (r['p'][2] + r['b'][2] * (r['s'] or 1.0))) < 32
                                                for o, _u, _f in rs)
            held = foot > STANDS_ON and not on_thing
            if GROUND_KIND.search(r['id']):
                # (a lamp or sign post stands on the ground, its foot a little in it, whatever its origin's height:
                # taken for hung, every Hlaalu lamp post was left out for want of a wall)
                held, up = False, up - foot - 4
            things.append(_thing(r, b['x'], b['y'], b['face'] + math.pi, r['p'][2] - b['z'] if held else up, held))
            things[-1]['dz'] = round(r['p'][2] - b['z'], 1)       # (its height over the door, when nothing it stood on is laid)
        # (each hung light or sign with the holder it hung from: right by its top, a hook, a bracket, a post)
        for k, (r, _u, _f) in enumerate(rs):
            if not things[k]['hang'] or not HUNG_KIND.search(r['id']) or HOLDER.search(r['id'].lower()):
                continue
            top = r['p'][2] + r['b'][5] * (r['s'] or 1.0)
            best = None
            for j, (o, _u2, _f2) in enumerate(rs):
                if j == k or not HOLDER.search(o['id'].lower()):
                    continue
                os_ = o['s'] or 1.0
                d = math.hypot(o['p'][0] - r['p'][0], o['p'][1] - r['p'][1])
                if d <= 120 and o['p'][2] + o['b'][2] * os_ <= top + 60 and o['p'][2] + o['b'][5] * os_ >= top - 40 and (best is None or d < best[0]):
                    best = (d, j)
            if best:
                things[k]['on'] = best[1]
                things[k]['dz_on'] = round(r['p'][2] - rs[best[1]][0]['p'][2], 1)
                if pairs is not None and LIGHT_HOLDER.search(rs[best[1]][0]['id']):
                    pairs.append((rs[best[1]][0], r))
        out[b['main'].lower()].append({'town': town, 'interior': (b.get('interior') or '').lower(), 'things': things})


def _post_of(r, holders):
    """The index of the holder (a post, hook or bracket) a hung light r hangs from among refs, or None: right by it,
    reaching its top."""
    top = r['p'][2] + r['b'][5] * (r['s'] or 1.0)
    best = None
    for j, o in enumerate(holders):
        if o is r or not o.get('b') or not HOLDER.search(o['id'].lower()):
            continue
        os_ = o['s'] or 1.0
        d = math.hypot(o['p'][0] - r['p'][0], o['p'][1] - r['p'][1])
        if d <= POST_NEAR and o['p'][2] + o['b'][2] * os_ <= top + 60 and o['p'][2] + o['b'][5] * os_ >= top - 40 and (best is None or d < best[0]):
            best = (d, j)
    return best[1] if best else None


def _post_lights(pairs):
    """{holder model: [light model, x, y, z, turn] in the holder's own frame}: the light the game hangs on it most."""
    c = defaultdict(Counter)
    for h, r in pairs:
        lx, ly = _local(h['p'][0], h['p'][1], h['p'][5], r['p'][0], r['p'][1])
        c[h['id'].lower()][(r['id'], round(lx / 4) * 4, round(ly / 4) * 4, round((r['p'][2] - h['p'][2]) / 4) * 4,
                            round((r['p'][5] - h['p'][5]) % (2 * math.pi), 2))] += 1
    return {k: list(v.most_common(1)[0][0]) for k, v in c.items()}


def _box_has(r, x, y):
    b, s = r['b'], r['s'] or 1.0
    c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
    dx, dy = x - r['p'][0], y - r['p'][1]
    lx, ly = (dx * c - dy * sn) / s, (dx * sn + dy * c) / s
    return b[0] - 8 <= lx <= b[3] + 8 and b[1] - 8 <= ly <= b[4] + 8


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

    def __init__(self, blocked, kinds=None):
        self.polys = [list(p) for p in blocked]
        self.kind = {}

    def free(self, pts):
        return not any(_overlap(pts, p) for p in self.polys)

    def why(self, pts):
        # (what it ran into, for the checks: the n-th poly's kind)
        for p in self.polys:
            if _overlap(pts, p):
                return self.kind.get(id(p), 'laid')
        return '?'

    def take(self, pts):
        self.polys.append(pts)


def _lay(db, scene, ox, oy, ang, space, memo, door_z=None, keep=None, hold=None):
    """A scene's things set down in a frame at (ox, oy) turned ang; those that would not fit are left out."""
    out = []
    things = scene['things']
    laid = {}
    # (holders first: a lantern or sign that hung from a hook, bracket or post in the game is laid only with it)
    # (and from the bottom up: what stands on the ground, then what is held, lowest first, so a thing on a stall or a
    # table finds it laid)
    for n_, t in sorted(enumerate(things), key=lambda it: (it[1].get('on') is not None, bool(it[1]['hang']), it[1]['z'])):
        if keep and not keep(t):
            continue
        if t['id'].lower() in NAMED:
            continue                    # (a shop's own sign, named for a game place)
        if PALISADE.search(t['id']):
            continue                    # (a palisade only in whole runs: its stakes stood about alone in fans, the user's Nordic village)
        on = t.get('on')
        if on is not None and on not in laid:
            continue
        wx, wy = _world(ox, oy, ang, t['x'], t['y'])
        rz = (t['rz'] + ang) % (2 * math.pi)
        pts, b = _rect_of(t['id'], wx, wy, rz, t.get('s') or 1.0, memo, db)
        if not pts:
            continue
        if t['hang'] and on is not None and t.get('dz_on') is not None:
            z = laid[on]['p'][2] + t['dz_on']          # (on its post, hook or bracket, by the post's height)
        elif t['hang']:
            if door_z is None:
                continue
            z = door_z + t['z']
            # (by the door's height its foot under the ground here: a Telvanni root hook and its lanterns stood 100 deep
            # in the slope by a pod, the city round of 2026-11-02. Stood on the ground instead)
            gz_ = mapdata.terrain_z(db, wx, wy)
            sc_ = t.get('s') or 1.0
            if gz_ is not None and z + b[2] * sc_ < gz_ - SUNK_HELD:
                z = gz_ - b[2] * sc_ - 4
                _count('stood up out of the ground')
            # (held by the built town, checked before anything is stacked on it: a cup stayed in the air when the
            # counter it stood on was left out after, the town audit of 2026-11-01)
            foot = z + b[2] * (t.get('s') or 1.0)
            on_laid = any(_in_poly(o['pts'], wx, wy) and abs(o['p'][2] + o['hi'] - foot) < 32 for o in out)
            if on is None and not on_laid and hold and not hold({'id': t['id'], 'p': [wx, wy, z], 's': t.get('s') or 1.0}):
                _count('refused: not held')
                continue
        else:
            gz = mapdata.terrain_z(db, wx, wy)
            if gz is None or gz < 0:
                _count('refused: water')
                continue
            # (nor on ground too steep to stand it on: benches stood on the cliff above the user's Nargorewatch, 2026-11-01)
            gs = [mapdata.terrain_z(db, x_, y_) for x_, y_ in pts]
            span = max(math.hypot(pts[0][0] - pts[2][0], pts[0][1] - pts[2][1]), 1.0)
            if None in gs or max(gs) - min(gs) > min(STEEP_MAX, max(STEEP_UNDER, STEEP_SLOPE * span)):
                _count('refused: steep')
                continue
            z = gz + t['z']
            sc_ = t.get('s') or 1.0
            if t['z'] + b[2] * sc_ < STANDS_ON and z + b[5] * sc_ < max(gs) + 2:
                z = max(gs) + 2 - b[5] * sc_       # (a flat thing's top clear of the ground under its uphill side)
            # (shrunk a little: things in a scene stand close, and their boxes are loose)
            if not space.free(_shrink(pts, 0.85)):
                _count('refused: space ' + space.why(_shrink(pts, 0.85)))
                continue
        out.append({'id': t['id'], 'p': [round(wx, 2), round(wy, 2), round(z, 2), t.get('rx') or 0.0, t.get('ry') or 0.0, round(rz, 5)],
                    's': t.get('s') or 1.0, 'pts': pts, 'up': 0.0 if t['hang'] else t['z'],
                    'lo': b[2] * (t.get('s') or 1.0), 'hi': b[5] * (t.get('s') or 1.0), 'dz': t.get('dz'), 'n': n_, 'on': on, 'hung': bool(t['hang'])})
        laid[n_] = out[-1]
    # (a thing standing on another of the scene, a cup on its table, only where that stands too: the table left out
    # for want of room, its redware stood in the air, the town audit of 2026-11-01)
    out.sort(key=lambda o: o['up'])
    kept = []
    for o in out:
        if any(k['id'] == o['id'] and abs(k['p'][0] - o['p'][0]) <= 8 and abs(k['p'][1] - o['p'][1]) <= 8 and abs(k['up'] - o['up']) <= 8 for k in kept):
            continue                        # (the game's scenes hold a few things twice in one spot: a town laid them twice)
        if o['up'] + o['lo'] >= STANDS_ON:          # (by its foot: a lamp post's origin is near its top)
            # (and whose top reaches its bottom: a crate on a stack whose middle crate didn't fit stood a crate's height
            # over the bottom one, the town audit of 2026-11-01)
            # (never on a canopy, an awning, a tent or a roof: a crate and a lantern stood on a market canopy, the
            # user's Tessellated Shores, 2026-11-01)
            under = [k for k in kept if k['up'] + k['lo'] < o['up'] + o['lo'] - 4 and _in_poly(k['pts'], o['p'][0], o['p'][1])
                     and k['up'] + k['hi'] >= o['up'] + o['lo'] - 24 and not CANOPY.search(k['id'])]
            if not under:
                # (what it stood on left out: by its height over the door, when the building holds it there)
                if o.get('dz') is not None and door_z is not None and hold:
                    z2 = round(door_z + o['dz'], 2)
                    if hold({'id': o['id'], 'p': [o['p'][0], o['p'][1], z2], 's': o['s']}):
                        o['p'][2] = z2
                        kept.append(o)
                        continue
                continue
            # (set on what it stands on, by its height over that, not on the ground under its own spot: on a slope the
            # eggs and fish of a Hlaalu yard's table stood sunk in the table or over it, the town audit of 2026-11-01)
            k = max(under, key=lambda k: k['up'])
            o['p'][2] = round(k['p'][2] + (o['up'] - k['up']), 2)
        kept.append(o)
    out = _lit_holders(db, kept, memo)
    for o in out:
        if o.get('on') is None and not any(t['hang'] for t in scene['things'] if t['id'] == o['id']):
            space.take(o['pts'])
    return out


SUNK_HELD = 24                 # (a held thing's foot this far under the ground is no wall's or porch's)
CANOPY = re.compile(r'canopy|awning|overhang|tent|roof|shade|parasol', re.I)
POSTS = {}                     # (the learnt holder -> light table, set by dress)
NAMED = set()                  # (signs named for a game place, set by dress)
PALISADE = re.compile(r'palisade|stockade', re.I)
SIGN = re.compile(r'sign(?!post|_?post|base|_?base|way|al)', re.I)
OWN_TRIES = 3                  # copies of a building's own surroundings tried
SET_WHOLE = 0.75               # a yard's set is laid when this share of its ground things fit, else none of it
SAME_SPOT = 12                 # (one model this near itself and turned within SAME_TURN is the same thing twice: it flickers)
SAME_TURN = math.radians(5)
SIGN_OFF = 2                   # a sign stands this clear of its wall's face
SQUARE_MAX = math.radians(30)  # (and is turned square to it when it is within this of square)
LAST = {}                      # (the last dressing's figures, for the checks)


def _whole_sets(things, got, counts, space):
    """got without the arrangements laid in part: the scene's ground things (counts(t)) grouped as the street groups
    are (GROUP apart at most), each kept when SET_WHOLE of it was laid, else all of it taken out with what stood on it
    or hung from it. (got, [(want, have)] per arrangement)."""
    idx = [n for n, t in enumerate(things) if counts(t)]
    parent = {n: n for n in idx}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            ta, tb = things[idx[a]], things[idx[b]]
            if math.hypot(ta['x'] - tb['x'], ta['y'] - tb['y']) <= GROUP:
                parent[find(idx[a])] = find(idx[b])
    sets_ = defaultdict(list)
    for n in idx:
        sets_[find(n)].append(n)
    laid = {g.get('n') for g in got if g.get('n') is not None}
    drop, out = set(), []
    for root, ns in sets_.items():
        have = sum(1 for n in ns if n in laid)
        if have < SET_WHOLE * len(ns):
            drop |= set(ns)
            out.append((len(ns), 0))
        else:
            out.append((len(ns), have))
    if not drop:
        return got, out
    # (and what stood on what was taken out, or hung from it)
    gone = [g for g in got if g.get('n') in drop]
    keep = []
    for g in got:
        if g.get('n') in drop or (g.get('on') is not None and g['on'] in drop):
            continue
        if g.get('up', 0) + g.get('lo', 0) >= STANDS_ON and any(_in_poly(o['pts'], g['p'][0], g['p'][1]) for o in gone if len(set(map(tuple, o['pts']))) > 2):
            continue
        keep.append(g)
    for g in got:
        if g not in keep and g['pts'] in space.polys:
            space.polys.remove(g['pts'])
    return keep, out


def _count(k, n=1):
    c = LAST.setdefault('count', {})
    c[k] = c.get(k, 0) + n


def _named(L):
    """Signs the game stands in one town only: a shop's own, its name painted on (TR_m4_sign_cirifae, "Cirifae's
    Tradehouse", stood on a house that was no tradehouse, the user's Tessellated Shores, 2026-11-01)."""
    towns = defaultdict(set)
    scs = [sc for v in (L.get('around') or {}).values() for sc in v]
    scs += [sc for c in (L.get('yards') or {}).values() for v in c.values() for sc in v]
    scs += [sc for c in (L.get('street') or {}).values() for sc in c.get('groups') or ()]
    for sc in scs:
        for t in sc.get('things') or ():
            if SIGN.search(t['id']) and not HOLDER.search(t['id'].lower()):
                towns[t['id'].lower()].add(sc.get('town'))
    return {k for k, v in towns.items() if len(v) <= 1}


def _no_doubles(out, also=()):
    """out without a thing set twice in one spot, across the whole town: two buildings' surroundings each brought a
    banner to one wall, and they flickered (the user's Tessellated Shores, 2026-11-01). also: [(id, p)] already set."""
    grid = defaultdict(list)
    keep = []
    for i, p in also:
        grid[(i.lower(), int(p[0] // 64), int(p[1] // 64))].append(p)
    for o in out:
        k = o['id'].lower()
        cx, cy = int(o['p'][0] // 64), int(o['p'][1] // 64)
        if any(math.dist(q[:3], o['p'][:3]) < SAME_SPOT and abs(((q[5] - o['p'][5]) + math.pi) % (2 * math.pi) - math.pi) < SAME_TURN
               for i in (-1, 0, 1) for j in (-1, 0, 1) for q in grid.get((k, cx + i, cy + j), ())):
            continue
        grid[(k, cx, cy)].append(o['p'])
        keep.append(o)
    return keep


WELL = re.compile(r'well(?!_?lit)', re.I)
WELL_APART = 1400              # (no well nearer another than this: the game's own, nearest to nearest, p5 1,381, median 3,317)
WELL_PARTS = 300               # (a well's pieces, its roof and its stone ring, stand this near one another)


def _spaced_wells(out, also=()):
    """out with no well nearer another than WELL_APART: each building's surroundings brought its own, and three stood in
    one street, roofed and open (the user's Griffbarrow, 2026-11-02). A well's pieces go together."""
    have = [p[:2] for i, p in also if WELL.search(i)]
    wells = [o for o in out if WELL.search(o['id'])]
    groups = []
    for o in wells:
        g = next((g for g in groups if any(math.dist(o['p'][:2], q['p'][:2]) <= WELL_PARTS for q in g)), None)
        if g is None:
            groups.append([o])
        else:
            g.append(o)
    drop = set()
    for g in groups:
        cx = sum(o['p'][0] for o in g) / len(g)
        cy = sum(o['p'][1] for o in g) / len(g)
        if any(math.dist((cx, cy), h) < WELL_APART for h in have):
            drop |= {id(o) for o in g}
            _count('refused: a well near another', len(g))
        else:
            have.append((cx, cy))
    return [o for o in out if id(o) not in drop]


def _square_signs(db, out, memo):
    """Each hung sign set out from its wall's face by its own depth and turned square to the wall: laid where the
    game's stood on another building, a sign cut into the house it hung on (TR_m4_sign_cirifae in ex_nord_house_05,
    the user's Tessellated Shores, 2026-11-01). A sign whose wall is too far off square is left out."""
    import doors
    import doorfronts
    res = []
    for o in out:
        if not o.get('hung') or o.get('on') is not None or not SIGN.search(o['id']) or HOLDER.search(o['id'].lower()):
            res.append(o)
            continue
        b = memo.get(('b', o['id']))
        if b is None:
            ri = db.resolve_id(o['id'])
            b = memo[('b', o['id'])] = (mapdata.object_bounds(db, ri) if ri is not None else None) or (0, 0, 0, 0, 0, 0)
        sc_ = o.get('s') or 1.0
        ux, uy = doorfronts.thin_axis({'b': b, 'p': o['p']})
        half = min(b[3] - b[0], b[4] - b[1]) * sc_ / 2.0
        cz = o['p'][2] + (b[2] + b[5]) / 2.0 * sc_
        sc = doors._local_scene(db, {'p': [o['p'][0], o['p'][1], cz, 0, 0, 0]})
        best = None
        for sg in (1, -1):
            h = sc.nearest_any((o['p'][0], o['p'][1], cz), (ux * sg, uy * sg, 0.0), half + 160)
            if h is not None and (best is None or h[0] < best[0]):
                best = (h[0], sg, h[1])
        if best is None:
            res.append(o)
            continue
        d, sg, n = best
        t = sc.tris[n]
        nx, ny = t[4] * t[8] - t[5] * t[7], t[5] * t[6] - t[3] * t[8]
        L = math.hypot(nx, ny)
        if L > 1e-6:
            nx, ny = nx / L, ny / L
            # (the turn that brings the sign's thin axis onto the wall's normal, the nearer way)
            da = (math.atan2(nx, ny) - math.atan2(ux, uy) + math.pi / 2) % math.pi - math.pi / 2
            if abs(da) > SQUARE_MAX:
                continue
            o['p'][5] = round((o['p'][5] + da) % (2 * math.pi), 5)
            vx, vy = doorfronts.thin_axis({'b': b, 'p': o['p']})
            ux, uy = (vx, vy) if vx * ux + vy * uy >= 0 else (-vx, -vy)
        # (its back SIGN_OFF clear of the face: moved along the thin axis, the wall at d on side sg)
        move = d - (half + SIGN_OFF)
        o['p'][0] = round(o['p'][0] + ux * sg * move, 2)
        o['p'][1] = round(o['p'][1] + uy * sg * move, 2)
        res.append(o)
    return res


def _lit_holders(db, out, memo):
    """Every lamp post, lantern hook or bracket with its light: the scene's own where it was laid, else the light the
    game hangs on that holder most, where it hangs it; a holder with neither is left out. (Lamp posts stood bare,
    T_Imp_Set_Lamppost_02 in the user's Tessellated Shores, 2026-11-01.)"""
    lit = {o.get('on') for o in out if o.get('on') is not None}
    res = []
    for o in out:
        if o.get('hung') and HOLDER.search(o['id'].lower()) and not LIGHT_HOLDER.search(o['id']) and o.get('n') not in lit:
            continue                    # (a bare hook or bracket, what hung on it left out: a hook in the air, lab ja3)
        if not LIGHT_HOLDER.search(o['id']) or o.get('n') in lit:
            res.append(o)
            continue
        pl = POSTS.get(o['id'].lower())
        if not pl:
            continue                    # (no light for it known: no bare post)
        lid, lx, ly, dz, drz = pl
        wx, wy = _world(o['p'][0], o['p'][1], o['p'][5], lx, ly)
        b = memo.get(('b', lid))
        if b is None:
            ri = db.resolve_id(lid)
            b = memo[('b', lid)] = (mapdata.object_bounds(db, ri) if ri is not None else None) or (0, 0, 0, 0, 0, 0)
        res.append(o)
        res.append({'id': lid, 'p': [round(wx, 2), round(wy, 2), round(o['p'][2] + dz, 2), 0.0, 0.0, round((o['p'][5] + drz) % (2 * math.pi), 5)],
                    's': 1.0, 'pts': [(wx, wy)] * 4, 'up': o['up'] + dz, 'lo': b[2], 'hi': b[5], 'dz': None, 'n': None, 'on': o.get('n')})
    return res


STANDS_ON = 24                 # (a scene's thing this far over the ground stands on another of it)
STEEP_UNDER = 32               # a standing thing's footprint rises no more than this across, or STEEP_SLOPE of its size
STEEP_SLOPE = 0.4              # (about 22°: a 150 bench stood on 70-110 of rise on the cliff, 2026-11-01)
STEEP_MAX = 64                 # (and never more: a firepit tilted over 70-96 of rise)
ON_WALL_KIND = re.compile(r'sign|lantern|lamp|light|banner|flag|ivy|vine|shield|torch|sconce|hook|bracket|chain|hanger|tapestry|wreath|rope', re.I)
GROUND_KIND = re.compile(r'signbase|signway|sign_?post|lightpost|post_|_post|stand', re.I)
ON_WALL = 120                   # a hung thing's building has a wall this near behind it


def _held(db, g, face, memo):
    """Is this thing, hung or set on the building, held by the built town: a wall right behind it, something under it
    or a beam over it? Laid where it was by its game building's door, a lantern hung in the air where the new
    building's wall wasn't, beside its corner, the user's Nargorewatch (2026-11-01, "floating lantern"). Rays from its
    middle both ways along the door's facing, down from its foot and up from its top."""
    import doors
    b = memo.get(('b', g['id']))
    if b is None:
        ri = db.resolve_id(g['id'])
        b = memo[('b', g['id'])] = (mapdata.object_bounds(db, ri) if ri is not None else None) or (0, 0, 0, 0, 0, 0)
    x, y, z = g['p'][0], g['p'][1], g['p'][2] + (b[2] + b[5]) / 2.0 * (g.get('s') or 1.0)
    sc = doors._local_scene(db, {'p': [x, y, z, 0, 0, 0]})
    ux, uy = math.sin(face), math.cos(face)
    s = g.get('s') or 1.0
    # (a wall holds what hangs on walls; a cup or a crate by a wall still wants something under it)
    # (any way round: a lantern on a side wall hangs beside it, not in front of it, and was left out every time)
    if ON_WALL_KIND.search(g['id']) and not GROUND_KIND.search(g['id']) and any(
            sc.nearest_any((x, y, z), (math.cos(a * math.pi / 4), math.sin(a * math.pi / 4), 0.0), ON_WALL) is not None for a in range(8)):
        return True
    foot, top = g['p'][2] + b[2] * s, g['p'][2] + b[5] * s
    down = sc.nearest_any((x, y, foot + 8), (0.0, 0.0, -1.0), 40)
    if down is not None and CANOPY.search(_hit_id(db, sc, down, x, y, memo)):
        down = None                     # (a canopy, an awning or a roof holds nothing up: never stood on)
    return down is not None or sc.nearest_any((x, y, top - 4), (0.0, 0.0, 1.0), 120) is not None


def _hit_id(db, sc, hit, x, y, memo):
    """The model a ray hit belongs to ('' when not known)."""
    k = sc.owner(hit[1]) if hasattr(sc, 'owner') else None
    if k is None:
        return ''
    ids = memo.get('ids')
    if ids is None:
        ids = memo['ids'] = {}
    if k not in ids:
        gx, gy = math.floor(x / 8192.0), math.floor(y / 8192.0)
        for cx in (gx - 1, gx, gx + 1):
            for cy in (gy - 1, gy, gy + 1):
                for r in mapdata.cellmap(db, '#%d,%d' % (cx, cy)).get('refs') or ():
                    ids[r['k']] = r['id']
    return ids.get(k, '')


def _in_poly(pts, x, y):
    c = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


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


def dress(db, plan, seed=1, blocked=(), amount=1.0, also=()):
    """Things for a made town (plan as townbuild.fit made it, each plot with 'door_z' once built): a yard scene of its
    culture and kind before every building (a smithy's forge before some shops, as often as the culture's shops are
    smiths), groups along its streets as many as the culture's towns stand a road patch, and its square's. blocked:
    polygons kept clear (the wall's pieces). [{'id', 'p', 's', 'role'}]."""
    L = learn(db)
    POSTS.clear()
    POSTS.update(L.get('post_lights') or {})
    if LAST.get('L') != id(L):
        NAMED.clear()
        NAMED.update(_named(L))
    LAST.clear()
    LAST['L'] = id(L)
    cult = plan.get('culture')
    rng = random.Random('%s|%s|dress' % (seed, cult))
    near = _near_cultures(L, cult)
    rects = {id(q): [tuple(p) for p in q['rect']] for q in plan['plots'] if q.get('rect')}
    # (and what stood there already: slave pods went down over a walkway, lab 2026-10-30)
    space = _Space(list(blocked) + list(rects.values()) + [[tuple(p) for p in o] for o in plan.get('obstacles') or ()])
    nb_, nr_ = len(blocked), len(rects)
    for i, p_ in enumerate(space.polys):
        space.kind[id(p_)] = 'wall' if i < nb_ else 'plot' if i < nb_ + nr_ else 'obstacle'
    for q in plan['plots']:
        if q.get('door') and q.get('b'):
            space.take(_door_clear(q['door'][0], q['door'][1], q['face']))
            space.kind[id(space.polys[-1])] = 'door way'
    # (and the paved streets themselves: a street lamp stood in the middle of the road, the user's Tessellated Shores,
    # 2026-11-02. A street group was laid at the edge of the street's 512 squares, and its things spread onto the
    # pavement)
    streets = _street_polys(plan, STREET_BLOCK_SHARE)
    for p_ in streets:
        space.take(p_)
        space.kind[id(space.polys[-1])] = 'street'
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
        # (the building's own surroundings first, as the game set them round this very building: they fit its walls)
        own_sc = (L.get('around') or {}).get((q['b'].get('key') or '').lower())
        # (the very game building it was copied from first: another of the same main piece may carry a porch or a
        # wing this one hasn't, and its hooks and lanterns stood off a wall that wasn't there)
        ex = (q['b'].get('uid') or '').split('#', 1)[-1]
        same = [sc_ for sc_ in own_sc or () if sc_.get('interior') and sc_['interior'] == ex]
        own_sc = same or own_sc
        sc = rng.choice(own_sc) if own_sc else _yard_pick(L, near, kind, rng)
        _count('plots ' + ('own' if own_sc else 'yard' if sc and sc['things'] else 'bare'))
        if not sc or not sc['things'] or rng.random() > amount:
            continue
        fw = q['b'].get('w') or q.get('w') or 512
        lim = 1e9 if own_sc else max(300.0, fw / 2.0 + 250)
        # (of the game's several copies of this building's surroundings, the one that fits most here, whole: one copy
        # alone, half of the arrangements went for want of room, the buildings standing closer than the game's, lab jdd3)
        cands = [sc] + [o for o in rng.sample(own_sc, min(len(own_sc), OWN_TRIES)) if o is not sc][:OWN_TRIES - 1] if own_sc else [sc]
        before_ = list(space.polys)
        best = None
        for sc_ in cands:
            space.polys[:] = before_
            mirror = not own_sc and rng.random() < 0.5
            sc2 = {'things': [dict(t, x=-t['x'], rz=(-t['rz']) % (2 * math.pi)) if mirror else t for t in sc_['things']]}
            # (its own outline cut back to the door's wall: the plot's outline reaches past it, porch and all, and
            # every thing by the door fell inside it, lab 2026-10-30)
            own = rects.get(id(q))
            cut = []
            if own in space.polys:
                space.polys.remove(own)
                # (its own surroundings stood round this very model in the game, clear of it: its box is left out
                # altogether; round a Telvanni tower its square box took every thing at the tower's foot, 2026-11-01)
                cut = _behind_door(own, q['door'][0], q['door'][1], q['face']) if not own_sc else []
                if cut:
                    space.take(cut)
            got = _lay(db, sc2, q['door'][0], q['door'][1], q['face'] + math.pi, space, memo, q.get('door_z'),
                       keep=lambda t: abs(t['x']) <= lim, hold=lambda g, f=q['face']: _held(db, g, f, memo))
            if own is not None and own not in space.polys:
                if cut:
                    space.polys.remove(cut)
                space.take(own)
            # (each arrangement whole or not at all: a smithy yard came out as three crates and a scrap on a bare street,
            # the user's Tessellated Shores, 2026-11-01. By its ground things; a lantern off a wall that is not there
            # doesn't count. A building's surroundings hold several arrangements, a forge's, a cart's, a bench's)
            got, sets_ = _whole_sets(sc2['things'], got, lambda t: not t['hang'] and abs(t['x']) <= lim and t['id'].lower() not in NAMED, space)
            if best is None or len(got) > len(best[0]):
                best = (got, sets_, list(space.polys))
        got, sets_, polys_ = best
        space.polys[:] = polys_
        LAST.setdefault('sets', []).extend((kind,) + x for x in sets_)
        want = sum(w for w, _h in sets_)
        _count('offered ' + ('own' if own_sc else 'yard'), want)
        _count('laid ' + ('own' if own_sc else 'yard'), len(got))
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
                cx, cy, ang = _off_street(plan, cx, cy, ang)
                grp = rng.choice(St[0][1]['groups'])
                got = _lay(db, grp, cx, cy, ang, space, memo)
                _count('offered street', len(grp['things']))
                _count('laid street', len(got))
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
    # the town's life: its market stalls with their sellers' spots, its storage by the walls (townlife.py)
    try:
        import townlife
        out.extend(townlife.dress(db, plan, rng, space, memo, out, amount))
    except Exception as e:
        print('town life:', e)
    out = _square_signs(db, _spaced_wells(_no_doubles(out, also), also), memo)
    for o in out:
        o.pop('pts', None)
    _KEPT.clear()
    _KEPT.update(plan=plan, L=L, space=space, memo=memo, rng=rng, amount=amount, mine={id(o) for o in out})
    return out


_KEPT = {}                     # (the last dressing's space, for lamps)


def lamps(db, plan, laid, also=()):
    """The town's lamp posts, once all its dressing is laid (laid: dress's things and what the yards and the shack
    fronts added since; their lights count, and their ground is kept clear): _street_lamps."""
    if _KEPT.get('plan') is not plan:
        return []
    space, memo = _KEPT['space'], _KEPT['memo']
    for o in laid:
        if id(o) not in _KEPT['mine']:
            pts, _b = _rect_of(o['id'], o['p'][0], o['p'][1], o['p'][5] if len(o['p']) > 5 else 0.0, o.get('s') or 1.0, memo, db)
            if pts:
                space.take(pts)
    out = _street_lamps(db, plan, _KEPT['L'], plan.get('culture'), laid, also, space, memo, _KEPT['rng'], _KEPT['amount'])
    for o in out:
        o.pop('pts', None)
    return out


# lights a building in the game's towns, by culture (the median town of each; class LIGH, all of a town's, 106 towns
# measured 2026-11-10). Made towns showed under half of it where the culture lights its streets from posts: a post high
# over the ground is filed with the hung things when the dressing is learnt, and so never came back in a street group.
LAMPS = {'Dunmer': 1.0, 'Hlaalu': 1.0, 'Redoran': 0.8, 'Indoril': 1.6, 'Velothi': 1.15, 'Telvanni': 2.25, 'Mournhold': 1.25,
         'Anvil': 1.26, 'Gold Coast': 0.5, 'Common': 0.69, 'Imperial': 1.4, 'Nordic': 0.57, 'Reach': 0.94, 'Ashlander': 0.7}
LAMP_APART = 600               # no lamp post nearer another light than this
LAMP_ASIDE = 40                # (a door's lamp stands this far beside its clear way in, LAMP_OUT before its wall)
LAMP_MORE = 170                # (and, where neither side takes one, this much further along the wall)
LAMP_BY = 900                  # (a street's lamp within this of a building's middle)
LAMP_OUT = 110


def _is_light(db, id_, memo):
    k = ('light', (id_ or '').lower())
    v = memo.get(k)
    if v is None:
        ri = db.resolve_id(id_)
        v = memo[k] = ri is not None and db.recs[ri][0] == 'LIGH'
    return v


def _street_lamps(db, plan, L, cult, out, also, space, memo, rng, amount=1.0):
    """Lamp posts for a town that shows fewer lights a building than its culture's towns do: the posts the game stands
    by that culture's buildings, each with the lantern the game hangs on it, at the streets' edges and beside doors,
    its arm toward the street, none near another light. A culture whose towns stand no post (its lights hang from
    walls) gets none."""
    rate = LAMPS.get(cult)
    nb = sum(1 for q in plan['plots'] if q.get('b'))
    if not rate or not nb:
        return []
    lit = [(o['p'][0], o['p'][1]) for o in out if _is_light(db, o['id'], memo)]
    lit += [(p_[0], p_[1]) for i_, p_ in also or () if _is_light(db, i_, memo)]
    want = int(round(rate * nb * amount)) - len(lit)
    _count('lamps short', max(0, want))
    if want <= 0:
        return []
    zs = {}
    for key, scs in (L.get('around') or {}).items():
        if townsurvey.town_style(key) != cult:
            continue
        for sc in scs:
            for t in sc['things']:
                i_ = t['id'].lower()
                if not t['hang'] and i_ in POSTS and LIGHT_HOLDER.search(i_):
                    zs.setdefault(i_, []).append(t['z'])
    if not zs:
        return []
    ids = sorted(zs)
    # (by the buildings, as the game stands them: beside a door first, then at the street's edge near a building, then
    # the doors' other sides. On a street far from every building a lamp lit nothing, lab 2026-11-10)
    first, by_street, second, third = [], [], [], []
    cen = [(sum(p[0] for p in q['rect']) / 4.0, sum(p[1] for p in q['rect']) / 4.0) for q in plan['plots'] if q.get('b') and q.get('rect')]
    roads = {tuple(r) for r in plan.get('roads') or ()}
    for p in sorted(roads):
        for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (p[0] + i, p[1] + j) in roads:
                continue
            cx = p[0] * 512 + 256 + i * 300 + rng.uniform(-200, 200) * (j != 0)
            cy = p[1] * 512 + 256 + j * 300 + rng.uniform(-200, 200) * (i != 0)
            if any(math.hypot(cx - a, cy - b_) < LAMP_BY for a, b_ in cen):
                by_street.append(_off_street(plan, cx, cy, math.atan2(i, j)))
    for q in plan['plots']:
        if q.get('b') and q.get('door'):
            ang = q['face'] + math.pi
            side = rng.choice((-1, 1))
            for lst, sd, more in ((first, side, 0), (second, -side, 0), (third, side, LAMP_MORE), (third, -side, LAMP_MORE)):
                x, y = _world(q['door'][0], q['door'][1], ang, sd * (DOOR_CLEAR[0] + LAMP_ASIDE + more + rng.uniform(-30, 30)), -LAMP_OUT)
                lst.append((x, y, ang))
    for lst in (first, by_street, second, third):
        rng.shuffle(lst)
    spots = first + by_street + second + third
    res = []
    for x, y, ang in spots:
        if want <= 0:
            break
        if any(math.hypot(x - a, y - b_) < LAMP_APART for a, b_ in lit):
            continue
        pid = rng.choices(ids, [len(zs[i_]) for i_ in ids])[0]
        lx, ly = POSTS[pid][1], POSTS[pid][2]
        # (its arm, where its lantern hangs, toward the street: the frame's -y)
        rz = (math.pi / 2 + math.atan2(ly, lx)) % (2 * math.pi) if math.hypot(lx, ly) > 8 else rng.uniform(0, 2 * math.pi)
        z = sorted(zs[pid])[len(zs[pid]) // 2]
        got = _lay(db, {'things': [{'id': pid, 'x': 0.0, 'y': 0.0, 'z': z, 'hang': False, 'rz': rz, 's': 1.0}]}, x, y, ang, space, memo)
        if len(got) < 2:
            continue
        for g in got:
            g['role'] = 'street'
        res.extend(got)
        lit.append((x, y))
        want -= 1
    _count('lamps laid', len(res) // 2)
    return res


STREET_MARGIN = 90             # a street group's middle stands this far out from the pavement's edge
STREET_BLOCK_SHARE = 0.75      # (and nothing stands within this share of the pavement's half width of the street's line: the
                               # whole width refused a seventh of a town's dressing, most of it yards' things at the kerb, lab a01)


def _street_polys(plan, share=1.0):
    """The paved streets of a plan as polygons (each straight run a rectangle), as wide as townbuild paints them."""
    try:
        from townbuild import PAINT_SHARE, PAINT_MIN
    except Exception:
        PAINT_SHARE, PAINT_MIN = 0.7, 256
    out = []
    for st in plan.get('streets') or ():
        r = max(PAINT_MIN, (st.get('w') or 0) / 2.0 * PAINT_SHARE) * share
        pts = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L_ = math.hypot(bx - ax, by - ay)
            if L_ < 1:
                continue
            nx, ny = -(by - ay) / L_ * r, (bx - ax) / L_ * r
            out.append([(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)])
    return out


def _off_street(plan, cx, cy, ang):
    """A street group's middle pushed out of the pavement to STREET_MARGIN beyond its edge, facing the street."""
    try:
        from townbuild import PAINT_SHARE, PAINT_MIN
    except Exception:
        PAINT_SHARE, PAINT_MIN = 0.7, 256
    best = None
    for st in plan.get('streets') or ():
        r = max(PAINT_MIN, (st.get('w') or 0) / 2.0 * PAINT_SHARE)
        pts = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L_ = math.hypot(bx - ax, by - ay)
            if L_ < 1:
                continue
            t = max(0.0, min(1.0, ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / (L_ * L_)))
            qx, qy = ax + (bx - ax) * t, ay + (by - ay) * t
            d = math.hypot(cx - qx, cy - qy)
            if best is None or d - r < best[0] - best[1]:
                best = (d, r, qx, qy)
    if best is None:
        return cx, cy, ang
    d, r, qx, qy = best
    if d >= r + STREET_MARGIN or d < 1:
        return cx, cy, ang
    ux, uy = (cx - qx) / d, (cy - qy) / d
    cx, cy = qx + ux * (r + STREET_MARGIN), qy + uy * (r + STREET_MARGIN)
    return cx, cy, math.atan2(ux, uy)                # (-y toward the street: local (0,-1) -> world (-ux, -uy))


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
