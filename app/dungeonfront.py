"""A dungeon's way in as it stands outdoors (the Land panel's Dungeon). The user, 2026-11-12: "We need the dungeon
tool for the land menu to make the exterior structures too, not just a door with an interior."

What the game has: a Dwemer ruin's towers, walls and pipes round its door, a Daedric shrine's blocks and arches, a
stronghold's platform, a tomb's doorway set in its mound of rock, a cave's mouth in the rocks of a slope. Each of
the game's own entrances of a kind is read as a front: its door, the built pieces that hang together with it (each
touching the last, out to REACH), the rocks set against them, and its lights, in the door's frame. Built pieces keep
their height against the door (a ruin is one rigid thing); rocks keep their height over the ground under them. No
plants, no people, nothing with a script, no other door.

Laid, a front of the kind is turned to the new door; of the kind's fronts, one whose ground fell most like the new
spot's is taken (from the region nearest in weather first), turned a little either way if that fits better. The
ground it stood on in the game is learnt with it (heights against the ground at the door, on a grid under its
pieces), and the new ground is shaped to that under the front, fading out round it, so that a tower is neither
buried nor left hanging wherever the door is put. The dungeon generator stands its outside door in it.

Learnt per kind the first time one is built, from the outdoor doors that lead into the game's places of that kind,
and kept on disk under the load order (cache/dungeonfront_<kind>_...). Nothing is learnt at start-up."""
import hashlib
import json
import math
import os
import re

import mapdata

VERSION = 6                     # (2: the ground under a front learnt with it; 3: and before its door; 4: finer for caves and tombs)
# (how far from its door a front may reach; how near the door a piece starts it)
REACH = {'dwemer': 3200.0, 'daedric': 3200.0, 'stronghold': 3600.0, 'ayleid': 3200.0, 'tomb': 1100.0, 'cave': 900.0}
NEAR = {'dwemer': 500.0, 'daedric': 500.0, 'stronghold': 600.0, 'ayleid': 500.0, 'tomb': 350.0, 'cave': 350.0}
GAP = 72.0                      # (pieces this near each other hang together)
RADIUS_MOST = 640.0             # (a piece counts as this wide at most when asked what it touches)
MAX_THINGS = 170                # (more than this round one door is a town or a fortress, not a front)
MIN_THINGS = 2
KIND_V = {'ayleid': 'c'}        # (a kind learnt another way alone: its own cache, the others' kept)
OVER_MOST = 700.0               # (a door this far over the ground stands on a sea stack or a cliff's face: no model for one on the land)
OVER_LEAST = -300.0             # (and one this far under it lies in a pit the land does not show)
TYPES = {'STAT', 'ACTI', 'LIGH'}
NATURE = re.compile(r'flora|tree|grass|kelp|_reed|bush|plant|mushroom|lichen|root|stump|^sound|marker|collision|decal|mist|'
                    r'^tr_m\d|_uni(que)?$|_unique|^ex_.*log_|vine|fern|moss|ivy|lily|coral|barnacle|bubble|lava|smoke|steam(?!stack)|'
                    r'waterfall|^in_', re.I)
ROCK = re.compile(r'rock|boulder|^terrain_|menhir|_terr|cliff|crag|stalag', re.I)
# (what a town or a road leaves by a door: not the front's)
TOWNISH = re.compile(r'sign|banner|lantern|streetlight|lamppost|crate|barrel|sack|cart|wagon|boat|ship|dock|pier|fence|bridge|'
                     r'silt|market|stall|tent|campfire|firepit|bedroll', re.I)
FIT_GOOD = 140.0                # (the ground is shaped to the front: a fair fit is enough)
GRID = 256.0                    # (the ground under a front is kept on this grid;
GRID_OF = {'cave': 128.0, 'tomb': 128.0}   # a cave's mouth and a tomb's door stand in steep ground: on the land's own)
UNDER = 320.0                   # (this near a built piece or the door: the ground is the front's)
PAD = 200.0                     # (the new ground is the front's own within this of its grid, fading out over BLEND)
BLEND = 640.0
CUT = 900.0                     # (the ground is cut or raised this much at most)
LANE = 640.0                    # (the way up to the door: this far before it,
LANE_SIDE = 150.0               # this wide either side (two of the land's points at least), fading out over LANE_BLEND)
LANE_BLEND = 250.0
LANE_UP = 0.30                  # (the ground before the door rises no faster than this away from it,
LANE_DOWN = 0.55                # and falls no faster than this)
LANE_CLEAR = 420.0              # (no rock or plant this far before the door)
DOOR_RARE = 0.05                # (a door under this share of the kind's fronts is not the kind's way in,
TIP = 0.5                       # and a front with more than TIPPED_MOST of its built pieces tipped this far off the level
TIPPED_MOST = 0.3               # is carved to its own rock: see choose)
STANDS = 256.0                  # (the ground this near a building that stands there already is left as it is,
STANDS_BLEND = 512.0            # coming in over this: a town's houses went up and down with the ground beside them)
TURNS = (0.0, math.pi / 8, -math.pi / 8, math.pi / 4, -math.pi / 4)
_mem = {}


def group(kind):
    """The kind's group of fronts ('cave' for every cave), or None for a kind with no front of its own (a fort is a
    castle's, a sewer a town's)."""
    if (kind or '').startswith('cave'):
        return 'cave'
    return kind if kind in REACH else None


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db, kind):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'dungeonfront_%s_%s_v%d%s.json' % (kind, _sig(db), VERSION, KIND_V.get(kind, '')))


def learn(db, kind, say=None):
    """[{'region', 'cell', 'door' (its id), 'over' (the door over its ground), 'doors' (other doors that stood in it),
    'reach', 'things': [[id, lx, ly, h, rx, ry, rz, s, follows, ground]]}]: every lone entrance of the kind, in its
    door's frame. h: against the door's height, or over the ground where it follows the ground (a rock). ground: the
    ground at the thing against the ground at the door."""
    import create
    import dwemer
    import kits
    import livedin
    import townsurvey
    from project import ref_info
    G = group(kind)
    if not G:
        return []
    key = (_sig(db), kind)
    if key in _mem:
        return _mem[key]
    path = _disk(db, kind)
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                _mem[key] = json.load(f)
                return _mem[key]
    except (OSError, ValueError):
        pass
    K = dwemer.kit(kind)
    tube = re.compile(K['tube'])
    must = re.compile(K['must']) if K.get('must') else None
    words = tuple(K.get('outside') or ())
    info = livedin._Info(db)
    town = set()
    try:
        for t in townsurvey.survey(db)['towns']:
            town.update(tuple(c) for c in t['cells'])
    except Exception as e:
        print('dungeon fronts: no towns to leave out:', e)
    pairs = create._door_pairs(db)
    cands = []
    for dest, doors in pairs.items():
        out = [d for d in doors if str(d['cell']).startswith('#') and any(w in (d['id'] or '').lower() for w in words)]
        if out:
            cands.append((dest, out))
    of_kind = {}
    exits = {}                  # (where each of the kind's places puts you out of doors: its doors with no place named)

    def is_kind(dest):
        if dest not in of_kind:
            ok = False
            lst = db.by_key.get(('CELL', dest)) or []
            if lst and lst[-1] not in db.dead and kits.game_made(db, dest):
                try:
                    refs, _h = db.cell_refs(dest)
                    ids = [(ref_info(r['subs'])[0] or '').lower() for r in refs.values()]
                    ok = sum(1 for i in ids if tube.match(i)) >= 10 and (not must or any(must.match(i) for i in ids))
                    if ok:
                        import struct
                        ex = []
                        for r in refs.values():
                            sb = dict(r['subs'])
                            if 'DODT' in sb and 'DNAM' not in sb and len(sb['DODT']) >= 12:
                                ex.append(struct.unpack_from('<3f', sb['DODT']))
                        exits[dest] = ex
                except Exception:
                    ok = False
            of_kind[dest] = ok
        return of_kind[dest]
    memo = {}

    def from_inside():
        """A kind whose doors outdoors lead into halls of other pieces than its kit's (K['front_tube']: an Ayleid
        ruin's entrance halls are its wide ones): every place of the game's built of them, and the door that stands
        where it puts you out of doors, read from the outdoor cell as the game has it with every plugin's part."""
        import struct
        wide = re.compile(K['front_tube'])
        got = {}
        for (tag, k), lst in list(db.by_key.items()):
            if tag != 'CELL' or k.startswith('#') or not lst or lst[-1] in db.dead or not kits.game_made(db, k):
                continue
            try:
                refs, _h = db.cell_refs(k)
            except Exception:
                continue
            n, ex = 0, []
            for r in refs.values():
                rid = (ref_info(r['subs'])[0] or '').lower()
                if wide.match(rid):
                    n += 1
                sb = dict(r['subs'])
                if 'DODT' in sb and 'DNAM' not in sb and len(sb['DODT']) >= 12:
                    ex.append(struct.unpack_from('<3f', sb['DODT']))
            if n < 10 or not ex:
                continue
            of_kind[k] = True
            exits[k] = ex
            for e in ex:
                c = (int(math.floor(e[0] / 8192.0)), int(math.floor(e[1] / 8192.0)))
                best = None
                for q in refs_of(c):
                    d_ = math.hypot(q[2][0] - e[0], q[2][1] - e[1])
                    if q[4] and d_ < 400.0 and any(w in q[1] for w in words) and (best is None or d_ < best[0]):
                        best = (d_, q)
                if best:
                    q = best[1]
                    got.setdefault(k, {})[(round(q[2][0]), round(q[2][1]))] = {'id': q[0], 'pos': q[2], 'cell': '#%d,%d' % c}
        return [(k, list(v.values())) for k, v in got.items()]

    def refs_of(c):
        if c not in memo:
            out = []
            try:
                refs, _h = db.cell_refs('#%d,%d' % c, without_project=True)
            except Exception:
                refs = {}
            for r in refs.values():
                rid, pos, s, dead = ref_info(r['subs'])[:4]
                if dead or not rid:
                    continue
                out.append((rid, rid.lower(), pos, s or 1.0, 'DNAM' in dict(r['subs'])))
            memo[c] = out
            if len(memo) > 600:
                for k in list(memo)[:300]:
                    memo.pop(k, None)
        return memo[c]

    def radius(q):
        b = info(q[0])[1]
        if not b:
            return 32.0
        return min(RADIUS_MOST, max(abs(b[0]), abs(b[1]), abs(b[3]), abs(b[4])) * q[3])
    R, N = REACH[G], NEAR[G]
    if K.get('front_tube'):
        have = {(dest, round(d['pos'][0]), round(d['pos'][1])) for dest, doors in cands for d in doors}
        for dest, doors in from_inside():
            doors = [d for d in doors if (dest, round(d['pos'][0]), round(d['pos'][1])) not in have]
            if doors:
                cands.append((dest, doors))
    found = []
    for n, (dest, doors) in enumerate(cands):
        if say and n % 40 == 0:
            say('Reading the game\'s %s entrances' % K['label'].lower(), n / float(max(1, len(cands))))
        if not is_kind(dest):
            continue
        for d in doors:
            try:
                gx, gy = (int(v) for v in str(d['cell'])[1:].split(','))
            except ValueError:
                continue
            if (gx, gy) in town:
                continue
            ax, ay, az, arz = d['pos'][0], d['pos'][1], d['pos'][2], d['pos'][5]
            g0 = mapdata.terrain_z(db, ax, ay)
            if g0 is None or (K.get('front_tube') and not OVER_LEAST <= az - g0 <= OVER_MOST):     # (the kinds learnt before keep theirs)
                continue
            near = [q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in refs_of((gx + dx, gy + dy))
                    if math.hypot(q[2][0] - ax, q[2][1] - ay) < R + RADIUS_MOST]
            built, rocks, lights, others = [], [], [], 0
            for q in near:
                if abs(q[2][0] - ax) < 1 and abs(q[2][1] - ay) < 1 and q[1] == (d['id'] or '').lower():
                    continue                           # (the door itself: the generator stands its own there)
                tag, _b, scr = info(q[0])
                if tag == 'DOOR':
                    if q[4] and math.hypot(q[2][0] - ax, q[2][1] - ay) < R:
                        others += 1
                    continue
                if tag not in TYPES or scr or NATURE.search(q[1]):
                    continue
                if ROCK.search(q[1]):
                    rocks.append(q)
                elif tag == 'LIGH':
                    lights.append(q)
                elif not TOWNISH.search(q[1]):
                    built.append(q)
            # (the built pieces that hang together with the door, each touching the last)
            rad = {id(q): radius(q) for q in built + rocks + lights}
            dist = lambda a, b: math.hypot(a[2][0] - b[2][0], a[2][1] - b[2][1])
            mem = [q for q in built if math.hypot(q[2][0] - ax, q[2][1] - ay) < rad[id(q)] + N]
            left = [q for q in built if q not in mem]
            grew = bool(mem)
            while grew and len(mem) <= MAX_THINGS:
                grew = False
                for q in list(left):
                    if math.hypot(q[2][0] - ax, q[2][1] - ay) < R and any(dist(q, m) < rad[id(q)] + rad[id(m)] + GAP for m in mem):
                        mem.append(q)
                        left.remove(q)
                        grew = True
            # (the rocks set against them or by the door, and the lights that hang on them)
            by = lambda q, pad: math.hypot(q[2][0] - ax, q[2][1] - ay) < rad[id(q)] + N or any(dist(q, m) < 0.6 * (rad[id(q)] + rad[id(m)]) + pad for m in mem)
            rk = [q for q in rocks if by(q, 0.0)]
            lt = [q for q in lights if by(q, 48.0)]
            keep = [(q, 0) for q in mem] + [(q, 1) for q in rk] + [(q, 0) for q in lt]
            if len(keep) < MIN_THINGS or len(keep) > MAX_THINGS:
                continue
            phi = -arz
            cs, sn = math.cos(-phi), math.sin(-phi)
            rows, reach = [], 0.0
            for q, follows in keep:
                g = mapdata.terrain_z(db, q[2][0], q[2][1])
                if g is None:
                    g = g0
                dx, dy = q[2][0] - ax, q[2][1] - ay
                lx, ly = dx * cs - dy * sn, dx * sn + dy * cs
                h = (q[2][2] - g) if follows else (q[2][2] - az)
                reach = max(reach, math.hypot(dx, dy))
                rows.append([q[0], round(lx, 1), round(ly, 1), round(h, 1), round(q[2][3], 4), round(q[2][4], 4),
                             round((-q[2][5] - phi) % (2 * math.pi), 4), round(q[3], 3), follows, round(g - g0, 1)])
            # (the ground it stands on: against the ground at the door, on a grid under the door and its built pieces)
            pts = [(0.0, 0.0)] + [(r[1], r[2]) for r in rows if not r[8]] + [(0.0, sg_ * t_) for sg_ in (-1.0, 1.0) for t_ in (128.0, 256.0, 384.0, 512.0, 640.0)]
            ground = []
            grid = GRID_OF.get(G, GRID)
            n_ = int(math.ceil((max(reach, 640.0) + UNDER) / grid))
            for j in range(-n_, n_ + 1):
                for i in range(-n_, n_ + 1):
                    lx, ly = i * grid, j * grid
                    if not any(math.hypot(lx - px, ly - py) < UNDER for px, py in pts):
                        continue
                    # (local to world: the frame turned back by phi)
                    g = mapdata.terrain_z(db, ax + lx * math.cos(phi) - ly * math.sin(phi), ay + lx * math.sin(phi) + ly * math.cos(phi))
                    if g is not None:
                        ground.append([lx, ly, round(g - g0, 1)])
            # (the way out of this door: where the game's own place puts you, coming out by it)
            out_ = None
            ex_ = sorted(((math.hypot(e[0] - ax, e[1] - ay), e) for e in exits.get(dest, ())), key=lambda t: t[0])
            if ex_ and 30.0 < ex_[0][0] < 700.0:
                dx, dy = ex_[0][1][0] - ax, ex_[0][1][1] - ay
                out_ = [round(dx * cs - dy * sn, 1), round(dx * sn + dy * cs, 1)]
            ci = mapdata.cell_info(db, str(d['cell'])) or {}
            found.append({'region': (ci.get('region') or '').lower(), 'cell': str(d['cell'])[1:], 'into': dest, 'door': d['id'], 'out': out_,
                          'over': round(az - g0, 1), 'doors': others, 'reach': round(reach), 'built': len(mem), 'things': rows,
                          'ground': ground})
    _mem[key] = found
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(found, f)
    except OSError:
        pass
    return found


def used(db):
    """The game's places whose fronts this mod's dungeons already stand in (kept with each dungeon's place)."""
    p = getattr(db, 'project', None)
    out = set()
    for c in (getattr(p, 'cells', None) or {}).values():
        if isinstance(c, dict) and c.get('ruin_front'):
            out.add(c['ruin_front'])
    return out


def fit(db, scene, x, y, phi):
    """The mean difference between how the ground falls under the front's things in the game and at (x, y) turned to
    phi (each against the ground at the door), the ground before the door counted too; None off the land."""
    z0 = mapdata.terrain_z(db, x, y)
    if z0 is None:
        return None
    c, s = math.cos(phi), math.sin(phi)
    tot, n = 0.0, 0
    for row in scene['things']:
        g = mapdata.terrain_z(db, x + row[1] * c - row[2] * s, y + row[1] * s + row[2] * c)
        if g is None:
            return None
        w = 1.0 if row[8] else 2.0                # (a built piece left hanging or buried shows more than a rock)
        tot += w * abs((g - z0) - row[9])
        n += w
    return tot / max(1.0, n)


def _odd(S, i):
    """Front i is not one to build after: its door is one few of the kind's fronts have (DOOR_RARE), or more than
    TIPPED_MOST of its built pieces are tipped over (TIP off the level)."""
    n = float(len(S))
    if sum(1 for sc in S if sc.get('door') == S[i].get('door')) / n < DOOR_RARE:
        return True

    def off(a):
        a = abs(a) % (2 * math.pi)
        return min(a, 2 * math.pi - a)
    built = [t for t in S[i].get('things') or () if not t[8]]
    tipped = sum(1 for t in built if off(t[4]) > TIP or off(t[5]) > TIP)
    return bool(built) and tipped / float(len(built)) > TIPPED_MOST


def choose(db, kind, x, y, phi, region='', rng=None, tries=40):
    """(front index, phi, fit) for a door at (x, y) facing phi: of the kind's fronts with no other door in them
    first, those whose ground fits within FIT_GOOD, the one from the region nearest in weather (a random one among
    them); else the best fitting. Each is tried turned a little either way."""
    import random
    rng = rng or random.Random(0)
    S = learn(db, kind)
    if not S:
        return None
    try:
        import landregion
        mine = landregion._weather(db, (region or '').lower()) if region else None
    except Exception:
        landregion, mine = None, None
    wd = {}

    def near(r):
        if r not in wd:
            w = landregion._weather(db, r) if (mine and r and landregion) else None
            wd[r] = 0.0 if r == (region or '').lower() else (sum(abs(a - b) for a, b in zip(mine, w)) if (mine and w) else 9.0)
        return wd[r]
    lone = [i for i, sc in enumerate(S) if not sc.get('doors')]
    idx = lone if len(lone) >= 3 else list(range(len(S)))
    # (a front of the kind's own make: entered by a door the kind's places are entered by, its pieces standing as
    # they were built. Bthzundcheft's is 17 pieces of which 13 lie on their sides and 8 are scaled, fitted to the
    # cliff it is carved from, behind the great round doors that elsewhere only cover the real door (2 of the 68
    # Dwemer fronts): on open ground "a heap of dwemer building pieces", and "this door is used as an activated
    # piece that hides a door, not a door itself", the user, 2026-11-13)
    own = [i for i in idx if not _odd(S, i)]
    if len(own) >= 3:
        idx = own
    # (not the place another dungeon of this mod already took after, while others are to be had)
    taken = used(db)
    fresh = [i for i in idx if S[i].get('into') not in taken]
    # (a kind with few fronts, the Ayleid ruins' three: each in turn, where three ruins all took after the same one)
    if len(fresh) >= 3 or (fresh and len(idx) <= 6):
        idx = fresh
    # (the fuller half of them: a ruin with its towers and its way in, not the six blocks of the smallest one the
    # game has, which fit any ground and so were taken first; the user, 2026-11-12, "a very lazy way to do a dwemer
    # dungeon". The ground is shaped to the front, so how it fits counts for less than what it is)
    sizes = sorted(S[i].get('built', 0) for i in idx)
    half = sizes[len(sizes) // 2] if sizes else 0
    # (and not the few greatest: a whole fortress over the hills says more than a dungeon's way in needs to)
    most = sizes[min(len(sizes) - 1, int(len(sizes) * 0.85))] if sizes else 0
    full = [i for i in idx if half <= S[i].get('built', 0) <= max(most, half)]
    if len(full) >= 3:
        idx = full
    rng.shuffle(idx)
    good, best = [], None
    for k in idx[:max(1, tries)]:
        for t in TURNS:
            f = fit(db, S[k], x, y, phi + t)
            if f is None:
                continue
            f += 12.0 * abs(t)                    # (the way the user turned it is the way it should face, all else equal)
            if f <= FIT_GOOD:
                good.append((round(near(S[k]['region']), 1), rng.random(), k, phi + t, f))
            if best is None or f < best[2]:
                best = (k, phi + t, f)
    if good:
        good.sort()
        g = good[0]
        return g[2], g[3], round(g[4])
    return (best[0], best[1], round(best[2])) if best else None


def lay(db, kind, k, x, y, phi):
    """Front k of the kind for a door at (x, y) facing phi: {'door': its id, 'z': the door's height, 'rz': its turn,
    'pieces': [{id, x, y, z, rx, ry, rz, s}]}, on the ground as it is."""
    S = learn(db, kind)[k]
    c, s = math.cos(phi), math.sin(phi)
    g0 = mapdata.terrain_z(db, x, y)
    if g0 is None:
        return None
    z0 = g0 + S.get('over', 0.0)
    out = []
    for rid, lx, ly, h, rx, ry, rz, sc, follows, _g in S['things']:
        wx, wy = x + lx * c - ly * s, y + lx * s + ly * c
        if follows:
            g = mapdata.terrain_z(db, wx, wy)
            if g is None:
                continue
            z = g + h
        else:
            z = z0 + h
        out.append({'id': rid, 'x': round(wx, 1), 'y': round(wy, 1), 'z': round(z, 1), 'rx': rx, 'ry': ry,
                    'rz': round((-(rz + phi)) % (2 * math.pi), 4), 's': sc})
    return {'door': S['door'], 'z': round(z0, 1), 'rz': round((-phi) % (2 * math.pi), 4), 'pieces': out,
            'from': S.get('into') or S.get('cell'), 'fit': None, 'kind': kind, 'k': k, 'x': x, 'y': y, 'phi': phi}


def ground(db, kind, k, x, y, phi):
    """The ground at (x, y) shaped to the ground front k stood on in the game: the front's own within PAD of its
    grid, fading out over BLEND, cut or raised CUT at most; the ground at the door stays as it is. What stands on
    the ground follows it. No Undo step of its own. Returns the cells changed."""
    import landscape
    S = learn(db, kind)[k]
    G = S.get('ground') or []
    g0 = mapdata.terrain_z(db, x, y)
    if not G or g0 is None:
        return 0
    c, s = math.cos(phi), math.sin(phi)
    reach = max(math.hypot(q[0], q[1]) for q in G) + PAD + BLEND
    C = landscape.CELL
    step = C / (landscape.N - 1.0)
    # (what is built there already, with how wide it is: the ground under and beside it stays)
    stands = []
    for gx in range(int(math.floor((x - reach) / C)), int(math.floor((x + reach) / C)) + 1):
        for gy in range(int(math.floor((y - reach) / C)), int(math.floor((y + reach) / C)) + 1):
            try:
                m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
            except Exception:
                continue
            for r in (m.get('refs') or []):
                low = str(r.get('id') or '').lower()
                if math.hypot(r['p'][0] - x, r['p'][1] - y) < 8.0:
                    continue                           # (the dungeon's own door, just set here)
                # (a building's pieces and doors; not the land's rocks, which are big too)
                house = (low.startswith(('in_', 'ex_')) or '_ex_' in low or '_x_' in low) and not ROCK.search(low) and not NATURE.search(low)
                if (r.get('arch') and house) or r.get('type') == 'DOOR':
                    b = r.get('b')
                    rad = 0.5 * max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0) if b else 64.0
                    if math.hypot(r['p'][0] - x, r['p'][1] - y) < reach + rad + STANDS + STANDS_BLEND:
                        stands.append((r['p'][0], r['p'][1], min(rad, 1200.0)))
    new_h, before = {}, {}
    for gx in range(int(math.floor((x - reach) / C)), int(math.floor((x + reach) / C)) + 1):
        for gy in range(int(math.floor((y - reach) / C)), int(math.floor((y + reach) / C)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(landscape.N):
                wy = gy * C + j * step
                if abs(wy - y) > reach:
                    continue
                for i in range(landscape.N):
                    wx = gx * C + i * step
                    dx, dy = wx - x, wy - y
                    if abs(dx) > reach:
                        continue
                    lx, ly = dx * c + dy * s, -dx * s + dy * c
                    near = sorted(((lx - q[0]) ** 2 + (ly - q[1]) ** 2, q[2]) for q in G)[:4]
                    d = math.sqrt(near[0][0])
                    if d >= PAD + BLEND:
                        continue
                    ws = [(1.0 / (d2 + 64.0), g) for d2, g in near]
                    want = g0 + sum(w * g for w, g in ws) / sum(w for w, _g in ws)
                    w = 1.0 if d <= PAD else 0.5 + 0.5 * math.cos(math.pi * (d - PAD) / BLEND)
                    for sx, sy, sr in stands:
                        ds = math.hypot(wx - sx, wy - sy) - sr
                        if ds < STANDS + STANDS_BLEND:
                            w *= max(0.0, min(1.0, (ds - STANDS) / STANDS_BLEND))
                    if w <= 0.0:
                        continue
                    n = j * landscape.N + i
                    z = h[n]
                    nz = z + w * (max(z - CUT, min(z + CUT, want)) - z)
                    if abs(nz - z) >= 1:
                        h[n] = nz
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    own = _own_keys(db, x, y) if new_h else set()
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, own)
    if new_h:
        db.sync_project()
    return len(new_h)


def _own_keys(db, x, y, pieces=()):
    """The refs that are this front's own: the dungeon's door at (x, y) and the pieces just set down (by id and
    spot). They stay where they were set while the ground is shaped for them: an Ayleid ruin's door stands at the
    foot of a sunken stair, 157 under the ground at its spot, and followed the ground down as the way in was cut to
    it, 160 under its own doorway (the night of 2026-11-12)."""
    want = {}
    for q in pieces or ():
        want.setdefault((q['id'].lower(), int(round(q['x'])), int(round(q['y']))), True)
    out = set()
    cells = {(int(math.floor(x / 8192.0)), int(math.floor(y / 8192.0)))}
    for q in pieces or ():
        cells.add((int(math.floor(q['x'] / 8192.0)), int(math.floor(q['y'] / 8192.0))))
    for gx, gy in cells:
        try:
            m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
        except Exception:
            continue
        for r in (m.get('refs') or []):
            if r.get('type') == 'DOOR' and math.hypot(r['p'][0] - x, r['p'][1] - y) < 8.0:
                out.add(r['k'])
            elif (str(r.get('id') or '').lower(), int(round(r['p'][0])), int(round(r['p'][1]))) in want:
                out.add(r['k'])
    return out


def _door_foot(db, door_id, z):
    """The height of a door's foot standing at z."""
    try:
        import livedin
        b = livedin._Info(db)(door_id)[1] if door_id else None
    except Exception:
        b = None
    return z + (b[2] if b else 0.0)


def _reshape(db, x, y, reach, fn, own=()):
    """The land's heights within reach of (x, y) put through fn(wx, wy, z) -> new z or None. What stands on the
    ground follows it, but the front's own door and pieces (own, their ref keys). No Undo step of its own. Returns
    the cells changed."""
    import landscape
    C = landscape.CELL
    step = C / (landscape.N - 1.0)
    new_h, before = {}, {}
    for gx in range(int(math.floor((x - reach) / C)), int(math.floor((x + reach) / C)) + 1):
        for gy in range(int(math.floor((y - reach) / C)), int(math.floor((y + reach) / C)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(landscape.N):
                wy = gy * C + j * step
                if abs(wy - y) > reach:
                    continue
                for i in range(landscape.N):
                    wx = gx * C + i * step
                    if abs(wx - x) > reach:
                        continue
                    n = j * landscape.N + i
                    nz = fn(wx, wy, h[n])
                    if nz is not None and abs(nz - h[n]) >= 1:
                        h[n] = nz
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, set(own or ()))
    if new_h:
        db.sync_project()
    return len(new_h)


def _front(db, F, S, solid):
    """The way out of the door, (unit x, unit y, how far) in the world: where the game's own place puts you out by
    this door, turned with the front; for a front with none known, the side away from its built pieces as
    doors.outside_spot finds it; else the frame's own -y."""
    x, y, phi = F['x'], F['y'], F['phi']
    c, s = math.cos(phi), math.sin(phi)
    o = S.get('out')
    if o and math.hypot(o[0], o[1]) > 30.0:
        wx, wy = o[0] * c - o[1] * s, o[0] * s + o[1] * c
        L = math.hypot(wx, wy)
        return wx / L, wy / L, max(110.0, min(260.0, L))
    try:
        import doors
        m = mapdata.cellmap(db, '#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0)))
        ds = [r for r in (m.get('refs') or []) if r.get('type') == 'DOOR' and math.hypot(r['p'][0] - x, r['p'][1] - y) < 16.0]
        if ds and solid:
            d = ds[0]
            mx, my = doors.middle(d)
            ax = sum(q['x'] for q in solid) / len(solid) - mx
            ay = sum(q['y'] for q in solid) / len(solid) - my
            L = math.hypot(ax, ay) or 1.0
            spot = doors.outside_spot(db, d, (-ax / L, -ay / L))
            if spot:
                vx, vy = spot[0] - mx, spot[1] - my
                L = math.hypot(vx, vy)
                if L > 1.0:
                    return vx / L, vy / L, max(110.0, min(260.0, L))
    except Exception as e:
        print('dungeon front, the door\'s face:', repr(e))
    return s, -c, 128.0


def _way_out(db, F, name, front):
    """Where you come out of the dungeon called name: before its door on the side it opens to, on the ground, your
    back to the door. True when it was set."""
    import doors
    import editing
    x, y = F['x'], F['y']
    key = name.lower()
    m = mapdata.cellmap(db, key)
    ax, ay = x + front[0] * front[2], y + front[1] * front[2]
    g = mapdata.terrain_z(db, ax, ay)
    want = [round(ax, 1), round(ay, 1), round((g if g is not None else F['z']) + 14.0, 1), 0.0, 0.0,
            round(math.atan2(front[0], front[1]) % (2 * math.pi), 4)]
    did = False
    for r in (m.get('refs') or []):
        to = r.get('to') or {}
        if r.get('type') != 'DOOR' or not str(to.get('key', '')).startswith('#') or math.hypot(to.get('x', 9e9) - x, to.get('y', 9e9) - y) > 700.0:
            continue
        c_, refs = editing._cell(db, key)
        ref = refs.get(r['k'])
        if ref is not None:
            editing._store(c_, r['k'], ref['origin'], ref['idx'], doors._set_link(ref['subs'], to.get('cell') or '', want))
            did = True
    if did:
        db.sync_project()
    return did


def approach(db, F, foot, graded, front, own=()):
    """The way up to the door kept open: before the door (out to LANE along front) the ground is no higher than the
    door's foot and a walkable rise away from it, and, where the game's own door stood on the ground (graded), no
    pit either. Returns the cells changed."""
    x, y = F['x'], F['y']
    fx, fy = front[0], front[1]

    def fn(wx, wy, z):
        dx, dy = wx - x, wy - y
        t = dx * fx + dy * fy
        if t < -64.0 or t > LANE:
            return None
        side = abs(dx * fy - dy * fx)
        if side >= LANE_SIDE + LANE_BLEND:
            return None
        t = max(0.0, t)
        hi = foot - 4.0 + LANE_UP * t
        lo = foot - 18.0 - LANE_DOWN * t
        want = min(z, hi)
        if graded:
            want = max(want, lo)
        if want == z:
            return None
        w = 1.0 if side <= LANE_SIDE else 0.5 + 0.5 * math.cos(math.pi * (side - LANE_SIDE) / LANE_BLEND)
        return z + w * (want - z)
    return _reshape(db, x, y, LANE + LANE_SIDE + LANE_BLEND, fn, own)


def _in_lane(x, y, front, px, py, wide=0.0):
    dx, dy = px - x, py - y
    t = dx * front[0] + dy * front[1]
    return 24.0 < t < LANE_CLEAR and abs(dx * front[1] - dy * front[0]) < LANE_SIDE + wide


def clear(db, F, pieces, front):
    """The land's own trees, plants and rocks taken out where the front's built pieces stand and before its door (a
    tree through a tower's wall, a rock across the way in): another plugin's deleted in the mod, the mod's own
    removed (not the front's own, just laid: theirs are in pieces). Returns how many."""
    import cliffrocks
    import editing
    import landdecor
    import livedin
    from project import ref_info
    info = livedin._Info(db)
    x, y = F['x'], F['y']
    cores = []
    own = set()
    for q in pieces:
        low = q['id'].lower()
        own.add((low, round(q['x']), round(q['y'])))
        if ROCK.search(low):
            continue
        b = info(q['id'])[1]
        r = 0.5 * max(b[3] - b[0], b[4] - b[1]) * (q.get('s') or 1.0) if b else 48.0
        cores.append((q['x'], q['y'], min(RADIUS_MOST, 0.7 * r)))
    mine = db.project.plugin.lower()
    reach = max([math.hypot(q['x'] - x, q['y'] - y) for q in pieces] or [0.0]) + RADIUS_MOST + LANE
    n = 0
    for gx in range(int(math.floor((x - reach) / 8192.0)), int(math.floor((x + reach) / 8192.0)) + 1):
        for gy in range(int(math.floor((y - reach) / 8192.0)), int(math.floor((y + reach) / 8192.0)) + 1):
            ck = '#%d,%d' % (gx, gy)
            try:
                refs, _h = db.cell_refs(ck)
            except Exception:
                continue
            cell = None
            for rk, ref in list(refs.items()):
                rid, pos, _s, dead = ref_info(ref['subs'])[:4]
                if dead or not rid:
                    continue
                low = rid.lower()
                if (low, round(pos[0]), round(pos[1])) in own:
                    continue
                rock = cliffrocks.is_rock(low)
                if not (rock or landdecor.kind_of(low)):
                    continue
                if not (_in_lane(x, y, front, pos[0], pos[1], 64.0 if rock else 0.0)
                        or any(math.hypot(pos[0] - cx, pos[1] - cy) < cr for cx, cy, cr in cores)):
                    continue
                if cell is None:
                    cell, _r = editing._cell(db, ck)
                if ref.get('origin') == mine:
                    cell['refs'].pop(rk, None)
                else:
                    editing._store(cell, rk, ref['origin'], ref['idx'], ref['subs'], deleted=True)
                n += 1
    if n:
        db.sync_project()
    return n


def check(db, F, foot, front):
    """How the door stands now: {'buried': the ground over the door's foot (0 when it is clear), 'rise': the most the
    ground before the door stands over a walkable way up to it, 'drop': the deepest it falls away under one}."""
    x, y = F['x'], F['y']
    g = mapdata.terrain_z(db, x, y)
    rise = drop = 0.0
    t = 64.0
    while t <= LANE:
        q = mapdata.terrain_z(db, x + t * front[0], y + t * front[1])
        if q is not None:
            rise = max(rise, q - (foot + 6.0 + LANE_UP * t))
            drop = max(drop, (foot - 18.0 - LANE_DOWN * t) - q)
        t += 64.0
    return {'buried': round(max(0.0, (g if g is not None else foot) - foot)), 'rise': round(max(0.0, rise)), 'drop': round(max(0.0, drop))}


def build(db, F, name):
    """The front planned as F laid round the door of the dungeon called name, just built: the ground shaped to it,
    its pieces set down (in the dungeon's own record of the places ledger), the way up to the door kept open on the
    side the door opens to, what grows in it cleared, where you come out set at that face, and all of it folded into
    the dungeon's one Undo step. Returns {'pieces', 'cleared', and check()'s figures}."""
    import cliffrocks
    import editing
    import ledger
    p = db.project
    stack = getattr(p, 'undo_stack', [])
    note = stack[-1][1] if stack else None
    S = learn(db, F['kind'])[F['k']]
    foot = _door_foot(db, F.get('door'), F['z'])
    g0 = mapdata.terrain_z(db, F['x'], F['y'])
    # (the game's own door stood on the ground, or up on its pieces: a platform, a flight of steps)
    graded = abs(foot - (g0 if g0 is not None else foot)) < 40.0
    cells = ground(db, F['kind'], F['k'], F['x'], F['y'], F['phi'])
    again = lay(db, F['kind'], F['k'], F['x'], F['y'], F['phi']) or F      # (the rocks on the ground as it is now)
    pid = ledger.named(db, 'dungeon', name)

    def put(pcs):
        if not pcs:
            return 0
        if pid:
            with ledger.open(db, 'dungeon', name, resume=pid):
                return cliffrocks.place(db, pcs)
        return cliffrocks.place(db, pcs)
    solid = [q for q in again['pieces'] if not ROCK.search(q['id'].lower())]
    rocks = [q for q in again['pieces'] if ROCK.search(q['id'].lower())]
    n = put(solid)
    db.sync_project()
    front = _front(db, F, S, solid)                # (which way the door opens: the game's own way out of it)
    # (no rock of the front's own across the way in)
    rocks = [q for q in rocks if not _in_lane(F['x'], F['y'], front, q['x'], q['y'])]
    cells += approach(db, F, foot, graded, front, _own_keys(db, F['x'], F['y'], solid))
    if rocks:
        # (on the ground as the way in left it)
        n += put(rocks)
    gone = 0
    try:
        gone = clear(db, F, solid + rocks, front)
    except Exception as e:
        print('dungeon front, clearing:', repr(e))
    try:
        c0 = (getattr(p, 'cells', None) or {}).get(name.lower())
        if isinstance(c0, dict):
            c0['ruin_front'] = S.get('into')       # (whose way in it has: the next dungeon takes after another)
    except Exception:
        pass
    db.sync_project()
    try:
        # (where you come out of it: before its door, on that side)
        _way_out(db, F, name, front)
    except Exception as e:
        print('dungeon front, the way out:', repr(e))
    c_, s_ = math.cos(F['phi']), math.sin(F['phi'])
    out = {'pieces': n, 'cleared': gone, 'like': S.get('into'), 'door': [round(F['x']), round(F['y']), round(F['z']), F.get('rz')],
           'faces': [round(front[0], 2), round(front[1], 2)], 'up': 0 if graded else round(foot - (g0 if g0 is not None else foot))}
    try:
        out.update(check(db, F, foot, front))
        if not graded:
            out['drop'] = 0                        # (a door up on its own pieces: the way to it is theirs, not the ground's)
        off = [abs((mapdata.terrain_z(db, F['x'] + r[1] * c_ - r[2] * s_, F['y'] + r[1] * s_ + r[2] * c_) or g0) - g0 - r[9])
               for r in S['things'] if not r[8]]
        out['off'] = round(sum(off) / max(1, len(off)))
        print('dungeon front: "%s" as %s (fit %s before): %d pieces, %d cleared, %d cells shaped; the ground under its built pieces %d off the '
              'game\'s on average; its door: ground over its foot %d, before it %d too high, %d too low'
              % (name, S.get('into'), F.get('fit'), n, gone, cells, out['off'], out['buried'], out['rise'], out['drop']), flush=True)
    except Exception as e:
        print('dungeon front, check:', repr(e))
    db.sync_project()
    editing.commit(db, 'The way in to "%s" outdoors: %d pieces%s' % (name, n, ', the ground shaped under them' if cells else ''))
    if note and len(getattr(p, 'undo_stack', [])) >= 2:
        editing.fold(db, 2, note)
    return out


def plan(db, kind, x, y, rz, region='', seed=0):
    """The front for a dungeon of the kind whose door is to stand at (x, y) turned rz (lay's answer, with 'fit'), or
    None for a kind with no front of its own or none in this load order."""
    import random
    if not group(kind):
        return None
    got = choose(db, kind, x, y, -float(rz or 0.0), region, random.Random(int(seed) or int(abs(x) + abs(y))))
    if not got:
        return None
    F = lay(db, kind, got[0], x, y, got[1])
    if F:
        F['fit'] = got[2]
        if db.resolve_id(F['door']) is None:
            F['door'] = None
    return F
