"""A way up to a gate or a door: a level landing before it, then one straight, even ramp down (or up) to a road or to
open, gentle ground, as wide as the gate and level from side to side.

The town builder cuts footpaths to its house doors (townbuild._door_paths). Gates got none: a castle on its hill stood
760 over the street 900 from its gate, and the user shaped the way up by hand, with Flatten and Smooth and then with
the Ramp (2026-11-13: "I notice a lot of them have very steep approaches"; of the Ramp: "It works really well"). This
makes that ramp by itself: every straight line out of the gate's landing that ends on a road or on open ground is
tried, and the one that climbs gently, moves least earth and is shortest is made, the way the Ramp tool makes one. (A
first version found a winding way of short stretches under 18 degrees on a lattice, as the door paths do: 4,800 long
down that bank, its tread lumpy where it doubled back. The user's own ramp there was straight, 27 degrees.)

    front(db, ref, toward)   the gate's middle, the way out of it, its threshold's height, how wide the way is
    find(db, F, to)          the way's points and heights, or why there is none (NoWay)
    make(db, cell, key, to, look)   the right-click tool: find, and lay unless look
    for_gate(db, x, y, ux, uy, z, half)   the makers' call
"""
import math
import re

import mapdata

GRADE = 0.5                    # (the ramp climbs this much a unit at most: 27 degrees, the user's own on the castle bank)
GRADE_SPOT = 0.84              # (from a spot the user clicked: 40 degrees, where the Ramp tool turns red)
EASY = 0.4                     # (a ramp costs more the steeper it is over this, 22 degrees: under it the shortest wins. At 0.3 the
                               # castle bank's ramp ran 3,300 along the hillside at 16 degrees, past the street at its foot)
REACH = 3600.0                 # (a ramp is this long at most)
AUTO_REACH = 2600.0            # (one a maker lays by itself, this long at most: the lab's town on a mountain ridge got a ramp
                               # 3,520 long down the mountainside; past this the user says where it starts)
SHORT = 448.0                  # (and this long at least)
LANDINGS = (0.0, 192.0, 384.0)  # (the level landing runs this far straight out of the gate's front before the ramp turns off)
TURNS = 10                     # (ramps are tried every this many degrees, up to TURN_MOST either side of straight out)
TURN_MOST = 80
CUT = 480.0                    # (the made ground lies this far under the ground as it was at most)
FILL = 900.0                   # (and this far over it at most: a causeway, where a gate stands over a sheer drop. At 420 the
                               # lab's castle gate, 800 over the ground 256 from it, had no way at all)
GENTLE = 0.2                   # (open ground: no steeper than this all round, measured over each of GENTLE_R)
GENTLE_R = (192.0, 448.0)
ROAD_GENTLE = 0.3              # (a road counts as arrived where it is no steeper than this all round, over each of GENTLE_R: a paved
                               # bank is not the street, nor is a ledge on it, where a first ramp ended 211 down a bank of 760)
OPEN_COST = 900.0              # (a ramp to open ground counts as this much longer than one to a road)
EARTH = 5.0                    # (a unit of ground moved, on average over the ramp, counts as this many units of length)
ROCK_COST = 150.0              # (each rock or tree the way would clear counts as this much length)
HALF_GATE = 256.0              # (a gate's way: level across this far either side of its line)
HALF_DOOR = 192.0              # (a door's: the door paths' own width)
BANK = 1.2                     # (a filled side falls away from the tread's edge this much a unit, 50 degrees, to the ground as it was)
CUT_BANK = 2.0                 # (a cut side rises from it this much a unit, 63 degrees)
SHOULDER = 64.0                # (and the first of either is rounded over this)
WALL_FILL = 96.0               # (and raised by this at most: a way's fill rose against the length beside its gate)
WALL_FOOT = 128.0              # (within this of a wall's or a building's outline the ground is never cut: a way's bank left a wall
                               # length beside its gate standing over air, the lab's gash town)
BEHIND = 1400.0                # (within this of the gate nothing of the way lies behind the gate's own line)
WANT = 0.3                     # (a gate wants a way when the ground before it falls or rises faster than this, 17 degrees, within
                               # WANT_R of its front: a town gate on ground falling 9 degrees got a ramp it had no need of)
WANT_R = (256.0, 512.0, 768.0, 1024.0)
LEAST = 6                      # (fewer land points than this to move by MOVE_LEAST: the ground to the gate is good as it is)
MOVE_LEAST = 24.0
TREE = re.compile(r'flora|tree|plant|bush|grass|kelp|shrub|fern|reed|vine|ivy|log', re.I)
_ROAD = None


class NoWay(Exception):
    """No way to make, and why (said to the user)."""


def _zat(db):
    memo = {}

    def zat(x, y):
        k = (round(x / 8.0), round(y / 8.0))
        if k not in memo:
            memo[k] = mapdata.terrain_z(db, x, y)
        return memo[k]
    return zat


def _road_at(db):
    """road(x, y): is the land patch there one of the road-like textures (the game's roads, a made town's streets)."""
    global _ROAD
    if _ROAD is None:
        import landshapes
        import townsurvey
        _ROAD = re.compile(landshapes.KEEP_TEX.pattern + '|' + townsurvey.ROAD.pattern)
    import landscape
    cells = {}

    def road(x, y):
        gx, gy = int(math.floor(x / 8192.0)), int(math.floor(y / 8192.0))
        if (gx, gy) not in cells:
            grid = None
            try:
                L = landscape.read(db, gx, gy)
                if L.get('exists') and L.get('t'):
                    tex = L.get('tex') or {}
                    grid = [bool(t and _ROAD.search((str(t) + ' ' + str(tex.get(t) or '')).lower())) for t in L['t']]
            except Exception:
                grid = None
            cells[(gx, gy)] = grid
        g = cells[(gx, gy)]
        if not g:
            return False
        px, py = min(15, int((x - gx * 8192.0) / 512.0)), min(15, int((y - gy * 8192.0) / 512.0))
        return g[py * 16 + px]
    return road


def _clearable(r):
    """A thing a made way clears as a made town's streets do (townbuild._clear_ground): plants, trees, loose rocks."""
    import townbuild
    return r.get('type') in ('STAT', 'CONT') and bool(townbuild.CLEARABLE.search(r['id'])) and not townbuild.NOT_CLEARABLE.search(r['id'])


def _obstacles(db, x0, y0, x1, y1):
    """(blocked(x, y, pad), soft(x, y, pad)): does a building piece or a wall stand there (within pad of its outline);
    does something a way clears (a rock's body, a tree's trunk: _clearable). What stands in the cells the box touches,
    read once."""
    hard, easy = {}, {}                           # (512 bucket -> [(cx, cy, cos, sin, bx0, by0, bx1, by1)])
    for gx in range(int(math.floor(x0 / 8192.0)), int(math.floor(x1 / 8192.0)) + 1):
        for gy in range(int(math.floor(y0 / 8192.0)), int(math.floor(y1 / 8192.0)) + 1):
            try:
                refs = mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()
            except Exception:
                refs = ()
            for r in refs:
                b = r.get('b')
                if not b or r.get('type') not in ('STAT', 'ACTI', 'CONT'):
                    continue
                s = r.get('s') or 1.0
                wx, wy = (b[3] - b[0]) * s, (b[4] - b[1]) * s
                px, py, rz = r['p'][0], r['p'][1], r['p'][5]
                into = hard
                if _clearable(r):
                    into = easy
                    if TREE.search(r['id']):
                        if (b[5] - b[2]) * s < 300:
                            continue              # (a plant: no bar, and cleared with the rest)
                        box = (-70.0, -70.0, 70.0, 70.0)    # (a tree: its trunk, not its crown)
                    elif min(wx, wy) >= 120:
                        box = (b[0] * s * 0.85, b[1] * s * 0.85, b[3] * s * 0.85, b[4] * s * 0.85)   # (a rock: its body)
                    else:
                        continue
                elif r.get('arch') or min(wx, wy) >= 200:
                    box = (b[0] * s, b[1] * s, b[3] * s, b[4] * s)      # (a building piece, a wall; a cart, a stall)
                else:
                    continue
                reach = math.hypot(max(abs(box[0]), abs(box[2])), max(abs(box[1]), abs(box[3]))) + 320.0
                if px + reach < x0 or px - reach > x1 or py + reach < y0 or py - reach > y1:
                    continue
                item = (px, py, math.cos(rz), math.sin(rz)) + box
                for i in range(int((px - reach) // 512), int((px + reach) // 512) + 1):
                    for j in range(int((py - reach) // 512), int((py + reach) // 512) + 1):
                        into.setdefault((i, j), []).append(item)

    def test(boxes):
        def at(x, y, pad=0.0):
            for cx, cy, c, sn, bx0, by0, bx1, by1 in boxes.get((int(x // 512), int(y // 512)), ()):
                dx, dy = x - cx, y - cy
                lx, ly = dx * c - dy * sn, dx * sn + dy * c
                if bx0 - pad <= lx <= bx1 + pad and by0 - pad <= ly <= by1 + pad:
                    return True
            return False
        return at
    return test(hard), test(easy)


def front(db, ref, toward=None):
    """The gate or door as the way sees it: {'c': its middle, 'u': the way out of it (unit), 'z': its threshold's height,
    'half': how far the way reaches either side, 'depth': from its middle to its face}. The way out is toward the given
    spot; with none, the side whose ground falls away faster (the side that wants a way)."""
    import doorfronts
    import doors
    b = ref.get('b')
    if not b:
        raise NoWay('That has no outline to find a way to.')
    s = ref.get('s') or 1.0
    cx, cy = doors.middle(ref)
    ux, uy = doorfronts.thin_axis(ref)
    wx, wy = (b[3] - b[0]) * s, (b[4] - b[1]) * s
    depth = min(wx, wy) / 2.0
    is_door = ref.get('type') == 'DOOR'
    g = mapdata.terrain_z(db, cx, cy)
    if g is None:
        raise NoWay('There is no land under it.')
    z = ref['p'][2] + b[2] * s if is_door else g
    if abs(z - g) > 200:
        z = g                                     # (a door set high in a wall, or a model whose box hangs low: the ground's word)
    half = HALF_DOOR if is_door and max(wx, wy) < 300 and 'gate' not in ref['id'].lower() else HALF_GATE     # (a gate's leaf is a gate)
    if toward is not None:
        if (toward[0] - cx) * ux + (toward[1] - cy) * uy < 0:
            ux, uy = -ux, -uy
    else:
        def fall(sx, sy):
            worst = 0.0
            for d in (256.0, 512.0, 768.0, 1024.0):
                t = mapdata.terrain_z(db, cx + sx * (depth + d), cy + sy * (depth + d))
                if t is not None:
                    worst = max(worst, abs(z - t) / d)
            return worst
        if fall(-ux, -uy) > fall(ux, uy):
            ux, uy = -ux, -uy
    return {'c': (cx, cy), 'u': (ux, uy), 'z': float(z), 'half': half, 'depth': depth}


def find(db, F, to=None, blocked=None, is_road=None, most=REACH):
    """The way from the gate: {'pts': [(x, y)] from the gate's middle out, 'z': the made ground's height at each, 'to':
    'road' | 'open' | 'spot'}: its middle, its front, the landing's end, the ramp's far end. Raises NoWay."""
    cx, cy = F['c']
    ux, uy = F['u']
    zt, half, depth = F['z'], F['half'], F['depth']
    sx, sy = cx + ux * (depth + 96.0), cy + uy * (depth + 96.0)
    zat = _zat(db)
    road = _road_at(db)
    reach = REACH if to is None else math.hypot(to[0] - sx, to[1] - sy) + 512.0
    if blocked is None:
        blocked = _obstacles(db, sx - reach - 512, sy - reach - 512, sx + reach + 512, sy + reach + 512)
    blocked, soft = blocked
    free_r = half + 160.0                         # (round the front itself the gate's own pieces are no bar)
    pad = 0.75 * half

    def slope_ok(x, y, t, limit, radii):
        for r in radii:
            for k in range(8):
                a = k * math.pi / 4
                t2 = zat(x + math.cos(a) * r, y + math.sin(a) * r)
                if t2 is None or t2 < 0 or abs(t2 - t) / r > limit:
                    return False
        return True

    ends = {}

    def arrived(x, y):
        """'road', 'open' or None for a ramp's far end."""
        k = (round(x / 32.0), round(y / 32.0))
        if k not in ends:
            t = zat(x, y)
            kind = None
            if t is not None and t >= 0 and not blocked(x, y, pad) and not soft(x, y, 0.0):
                # (is_road: the maker's own streets, not paved yet when it asks)
                if (road(x, y) or (is_road is not None and is_road(x, y))) and slope_ok(x, y, t, ROAD_GENTLE, GENTLE_R):
                    kind = 'road'
                elif slope_ok(x, y, t, GENTLE, GENTLE_R) and not any(
                        blocked(x + math.cos(j * math.pi / 4) * GENTLE_R[-1], y + math.sin(j * math.pi / 4) * GENTLE_R[-1]) for j in range(8)):
                    kind = 'open'
            ends[k] = kind
        return ends[k]

    def tried(a, ex, ey, limit):
        """A landing a long and a ramp from its end to (ex, ey): (cost, grade) or None when it cannot be made."""
        tx, ty = sx + ux * a, sy + uy * a
        L = math.hypot(ex - tx, ey - ty)
        ze = zat(ex, ey)
        if ze is None or ze < 0 or L < SHORT:
            return None
        g = abs(ze - zt) / L
        if g > limit:
            return None
        dx, dy = (ex - tx) / L, (ey - ty) / L
        earth, n, rocks, in_rock = 0.0, 0, 0, False
        # (the landing, then the ramp: the ground at the middle and at both edges against the made height)
        legs = [((sx, sy), (tx, ty), zt, zt)] if a else []
        legs.append(((tx, ty), (ex, ey), zt, ze))
        for (ax, ay), (bx, by), za, zb in legs:
            ln = math.hypot(bx - ax, by - ay)
            vx, vy = (bx - ax) / ln, (by - ay) / ln
            m = max(1, int(ln // 64))
            for i in range(m + 1):
                f = i / float(m)
                x, y, z = ax + (bx - ax) * f, ay + (by - ay) * f, za + (zb - za) * f
                if math.hypot(x - cx, y - cy) < BEHIND and (x - cx) * ux + (y - cy) * uy < depth:
                    return None                   # (behind the gate's line)
                if math.hypot(x - sx, y - sy) > free_r and blocked(x, y, pad):
                    return None
                hit = soft(x, y, 0.5 * half)
                if hit and not in_rock:
                    rocks += 1
                in_rock = hit
                for off in (-0.8 * half, 0.0, 0.8 * half):
                    t = zat(x - vy * off, y + vx * off)
                    if t is None or t < 0 or z - t > FILL or t - z > CUT:
                        return None
                    earth += abs(z - t)
                    n += 1
        cost = (a + L) * (1.0 + 3.0 * max(0.0, g - EASY) / (GRADE - EASY)) + EARTH * earth / max(1, n) + ROCK_COST * rocks
        return cost, g

    best = None                                   # (cost, landing, end, kind)
    if to is not None:
        for a in LANDINGS:
            r = tried(a, to[0], to[1], GRADE_SPOT)
            if r and (best is None or r[0] < best[0]):
                best = (r[0], a, (float(to[0]), float(to[1])), 'spot')
        if best is None:
            raise NoWay('No even slope from there to it can be made: too steep, too deep to dig or fill, or a building in its way.')
    else:
        for a in LANDINGS:
            tx, ty = sx + ux * a, sy + uy * a
            for turn in range(-TURN_MOST, TURN_MOST + 1, TURNS):
                c, sn = math.cos(math.radians(turn)), math.sin(math.radians(turn))
                dx, dy = ux * c - uy * sn, ux * sn + uy * c
                L = SHORT
                while L <= most:
                    ex, ey = tx + dx * L, ty + dy * L
                    kind = arrived(ex, ey)
                    if kind:
                        r = tried(a, ex, ey, GRADE)
                        if r:
                            cost = r[0] + (OPEN_COST if kind == 'open' else 0.0)
                            if best is None or cost < best[0]:
                                best = (cost, a, (ex, ey), kind)
                    L += 128.0
        if best is None:
            raise NoWay('No even slope to it from a road or from open ground was found within reach. Click the ground where it should start.')
    _c, a, (ex, ey), kind = best
    pts = [(cx, cy), (sx, sy)]
    zs = [zt, zt]
    if a:
        pts.append((sx + ux * a, sy + uy * a))
        zs.append(zt)
    pts.append((ex, ey))
    zs.append(zat(ex, ey))
    return {'pts': pts, 'z': zs, 'to': kind}


def lay(db, F, W, dry=False, blocked=None, skip=()):
    """The way's ground: the tread level across F['half'] either side of its line at the profile's height, a level
    landing before the gate, its sides banks of an even slope: down to the ground at BANK where the way is filled, up
    to it at CUT_BANK where it is cut; nothing behind the gate's line, nothing under a building piece but the gate's own passage. Land points
    moved by a unit or more (dry: counted only, those moved by MOVE_LEAST or more)."""
    import landscape
    G, N = landscape.CELL, landscape.N
    vstep = G / (N - 1.0)
    cx, cy = F['c']
    ux, uy = F['u']
    half, depth, zt = F['half'], F['depth'], F['z']
    pts, zs = W['pts'], W['z']
    lx, ly = pts[1]                               # (the front: the landing's middle)
    land_r = half + 64.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    reach = half + max(FILL / BANK, CUT / CUT_BANK) + 128.0
    if blocked is None:
        blocked = _obstacles(db, min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)
    blocked = blocked[0]
    new_h, before, moved, much = {}, {}, 0, 0
    for gx in range(int(math.floor((min(xs) - reach) / G)), int(math.floor((max(xs) + reach) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - reach) / G)), int(math.floor((max(ys) + reach) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            h = list(L['h'])
            changed = False
            for j in range(N):
                y = gy * G + j * vstep
                if y < min(ys) - reach or y > max(ys) + reach:
                    continue
                for i in range(N):
                    x = gx * G + i * vstep
                    if x < min(xs) - reach or x > max(xs) + reach:
                        continue
                    back = (x - cx) * ux + (y - cy) * uy
                    if back < -depth - 32.0 and math.hypot(x - cx, y - cy) < BEHIND:
                        continue
                    n_ = j * N + i
                    z0 = h[n_]
                    dl = math.hypot(x - lx, y - ly)
                    raw, tz = dl - land_r, zt
                    passage = False
                    for k in range(len(pts) - 1):
                        ax, ay = pts[k]
                        bx, by = pts[k + 1]
                        dx, dy = bx - ax, by - ay
                        L2 = dx * dx + dy * dy
                        if not L2:
                            continue
                        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
                        d = math.hypot(x - ax - dx * t, y - ay - dy * t) - half
                        if d < raw:
                            raw, tz = d, zs[k] + (zs[k + 1] - zs[k]) * t
                        if k == 0 and d <= 64.0:
                            passage = True
                    lat = max(0.0, raw)
                    if not passage and blocked(x, y, 0.0):
                        continue
                    if lat <= 0:
                        nz = tz
                    else:
                        # (the bank: from the tread's edge down to the ground at BANK, or up to it at CUT_BANK, its
                        # first SHOULDER rounded)
                        run = lat - SHOULDER * 0.5 if lat > SHOULDER else lat * lat / (2.0 * SHOULDER)
                        if z0 < tz:
                            nz = max(z0, tz - run * BANK)
                        else:
                            nz = min(z0, tz + run * CUT_BANK)
                    if not passage and blocked(x, y, WALL_FOOT):
                        if nz < z0:
                            continue              # (no cut at the foot of a wall or a building)
                        nz = min(nz, z0 + WALL_FILL)      # (and little fill: the wall keeps its height over the ground)
                    if abs(nz - z0) >= 1:
                        h[n_] = nz
                        changed = True
                        moved += 1
                        if abs(nz - z0) >= MOVE_LEAST:
                            much += 1
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    if dry:
        return much
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
        try:
            landscape._follow_paths(db, gx, gy, before[(gx, gy)], after)      # (the walking paths' points ride the ground too)
        except Exception as e:
            print('way up, paths:', e)
    if new_h:
        db.sync_project()
    return moved


def clear(db, F, W):
    """The plants, trees and loose rocks standing on the way taken off it, as a made town's streets are cleared
    (townbuild._clear_ground): the mod's own go; another plugin's are marked deleted in the mod. A rock goes when its
    body laps the tread, a tree or a plant when it stands on it. Nothing behind the gate's line. The count."""
    import editing
    import townbuild
    cx, cy = F['c']
    ux, uy = F['u']
    half = F['half']
    pts = W['pts']
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mine = db.project.plugin.lower()
    n = 0
    for gx in range(int(math.floor((min(xs) - 1024) / 8192.0)), int(math.floor((max(xs) + 1024) / 8192.0)) + 1):
        for gy in range(int(math.floor((min(ys) - 1024) / 8192.0)), int(math.floor((max(ys) + 1024) / 8192.0)) + 1):
            key = '#%d,%d' % (gx, gy)
            hits = []
            for r in mapdata.cellmap(db, key).get('refs') or ():
                if not _clearable(r):
                    continue
                x, y = r['p'][0], r['p'][1]
                if (x - cx) * ux + (y - cy) * uy < F['depth'] and math.hypot(x - cx, y - cy) < BEHIND:
                    continue
                b = r.get('b')
                rad = 0.0
                if b and townbuild.ROCKISH.search(r['id']):
                    rad = 0.5 * 0.85 * min(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0)
                d = min(_seg_d(x, y, pts[k], pts[k + 1]) for k in range(len(pts) - 1))
                if d <= half + rad:
                    hits.append(r)
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


def _seg_d(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if not L2 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
    return math.hypot(px - (a[0] + dx * t), py - (a[1] + dy * t))


def _told(F, W):
    pts, zs = W['pts'], W['z']
    run = sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(1, len(pts) - 1))    # (from the gate's front)
    steep = max(abs(zs[k + 1] - zs[k]) / max(1.0, math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])) for k in range(len(pts) - 1))
    return {'pts': [[round(p[0]), round(p[1]), round(z)] for p, z in zip(pts, zs)], 'run': round(run), 'rise': round(zs[0] - zs[-1]),
            'steepest': round(steep, 3), 'deg': round(math.degrees(math.atan(steep))), 'to': W['to'], 'half': F['half']}


def _ref(db, cell, key):
    for r in mapdata.cellmap(db, cell).get('refs') or ():
        if str(r.get('k')) == str(key):
            return r
    raise NoWay('That is no longer there.')


def make(db, cell, key, to=None, look=False):
    """The right-click tool: a way to the gate or door (cell, key), from the spot `to` when one is given. look: only what
    it would be ({'pts': [[x, y, z]], 'run', 'rise', 'steepest', 'deg', 'to'}); else laid too ('moved').
    {'none': why} when there is nothing to make."""
    try:
        ref = _ref(db, cell, key)
        to_ = (float(to[0]), float(to[1])) if to else None
        F = front(db, ref, to_)
        if to_ is None and steep_before(db, F) <= WANT:
            return {'none': 'The ground to it is gentle as it is.'}
        W = find(db, F, to_)
        if to_ is None and lay(db, F, W, dry=True) < LEAST:
            return {'none': 'The ground to it is gentle as it is.'}
        out = _told(F, W)
        if not look:
            out['cleared'] = clear(db, F, W)      # (first: what stood on the tread does not ride the ground down)
            out['moved'] = lay(db, F, W)
            out['summary'] = db.summary()
        return out
    except NoWay as e:
        return {'none': str(e)}


def steep_before(db, F):
    """How fast the ground falls or rises away from the gate's front at worst: over each of WANT_R, straight out and
    30 degrees either side."""
    cx, cy = F['c']
    ux, uy = F['u']
    sx, sy = cx + ux * (F['depth'] + 96.0), cy + uy * (F['depth'] + 96.0)
    worst = 0.0
    for turn in (-30, 0, 30):
        c, sn = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        dx, dy = ux * c - uy * sn, ux * sn + uy * c
        for d in WANT_R:
            t = mapdata.terrain_z(db, sx + dx * d, sy + dy * d)
            if t is not None:
                worst = max(worst, abs(F['z'] - t) / d)
    return worst


def _one(db, F, skip=(), is_road=None):
    """The makers' way for one gate: made where the gate wants one and one is found; as _told gives it, or None."""
    if steep_before(db, F) <= WANT:
        return None
    try:
        W = find(db, F, is_road=is_road, most=AUTO_REACH)
    except NoWay:
        return None
    if lay(db, F, W, dry=True) < LEAST:
        return None
    out = _told(F, W)
    out['cleared'] = clear(db, F, W)
    out['moved'] = lay(db, F, W, skip=skip)
    out['gate'] = (round(F['c'][0]), round(F['c'][1]))
    out['front'] = (round(W['pts'][1][0]), round(W['pts'][1][1]))
    return out


def for_gate(db, x, y, ux, uy, z=None, half=HALF_GATE, depth=96.0, skip=(), is_road=None):
    """A way from the gate at (x, y) out along (ux, uy), its threshold at z (the ground's there with none). The way as
    _told gives it with 'moved', or None when the ground is good as it is or no way was found."""
    g = mapdata.terrain_z(db, x, y)
    if g is None:
        return None
    d = math.hypot(ux, uy) or 1.0
    return _one(db, {'c': (float(x), float(y)), 'u': (ux / d, uy / d), 'z': float(g if z is None else z), 'half': half, 'depth': depth}, skip, is_road)


def for_wall(db, W, skip=(), is_road=None):
    """The makers' call, once a wall and its ground stand: a way for each of its outer gates whose approach wants one.
    A gate piece (kind 'gate'), or the opening between two end pieces; its way out is across the wall, on the side that
    lies outside the wall's outline (a gate with both sides inside, a ward's, gets none). The gate's own door, where the
    maker hung one within reach, gives the threshold. is_road(x, y): the maker's own streets. The ways made, as _told
    gives them, each with 'gate': (x, y) and 'front'."""
    import doorfronts
    import townwalls
    poly = [tuple(p) for p in W.get('outline') or ()]
    cand = []                                     # (x, y, way across (unit), depth)
    for p in W.get('pieces') or ():
        if p.get('kind') != 'gate':
            continue
        q = p['pose']
        b = mapdata.object_bounds(db, db.resolve_id(p['id'])) if p.get('id') else None
        if b:
            ux, uy = doorfronts.thin_axis({'b': b, 'p': [q.x, q.y, q.z, 0.0, 0.0, q.rz]})
            depth = min(b[3] - b[0], b[4] - b[1]) / 2.0
        else:
            ux, uy, depth = math.sin(q.rz), math.cos(q.rz), 96.0
        cand.append((q.x, q.y, (ux, uy), depth))
    ends = [p['pose'] for p in W.get('pieces') or () if p.get('kind') == 'end']
    used = set()
    for i, a in enumerate(ends):
        if i in used:
            continue
        near = sorted((math.hypot(b.x - a.x, b.y - a.y), j) for j, b in enumerate(ends) if j != i and j not in used)
        if not near or near[0][0] > 2200 or near[0][0] < 1:
            continue
        d, j = near[0]
        used.update((i, j))
        b = ends[j]
        cand.append(((a.x + b.x) / 2.0, (a.y + b.y) / 2.0, (-(b.y - a.y) / d, (b.x - a.x) / d), 96.0))
    out, done = [], []
    for x, y, (ux, uy), depth in cand:
        if any(math.hypot(x - dx, y - dy) < 700 for dx, dy in done):
            continue                              # (a gatehouse's arch and its gate: one way)
        done.append((x, y))
        if len(poly) >= 3:
            a_out = not townwalls._inside(poly, (x + ux * (depth + 300), y + uy * (depth + 300)))
            b_out = not townwalls._inside(poly, (x - ux * (depth + 300), y - uy * (depth + 300)))
            if a_out == b_out:
                continue
            if b_out:
                ux, uy = -ux, -uy
        door = _gate_door(db, x, y)
        try:
            if door is not None:
                F = front(db, door, (x + ux * 2000.0, y + uy * 2000.0))
                F['half'] = HALF_GATE
            else:
                g = mapdata.terrain_z(db, x, y)
                if g is None:
                    continue
                F = {'c': (float(x), float(y)), 'u': (ux, uy), 'z': float(g), 'half': HALF_GATE, 'depth': depth}
        except NoWay:
            continue
        r = _one(db, F, skip, is_road)
        if r:
            out.append(r)
    return out


def for_doors(db, around, skip=(), is_road=None, reach=600.0):
    """A way for each gate door of the mod's own standing within reach of the points `around` (a castle's ring, when
    a town is made beside it: the castle's gate gets its way once the town's streets lie, and to them). The way out
    is the side whose ground falls away faster. The ways made, as for_wall gives them."""
    pts = [(float(p[0]), float(p[1])) for p in around]
    if not pts:
        return []
    mine = db.project.plugin.lower() + '|'
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    doors_ = []
    for gx in range(int(math.floor((min(xs) - reach) / 8192.0)), int(math.floor((max(xs) + reach) / 8192.0)) + 1):
        for gy in range(int(math.floor((min(ys) - reach) / 8192.0)), int(math.floor((max(ys) + reach) / 8192.0)) + 1):
            try:
                refs = mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()
            except Exception:
                continue
            for r in refs:
                if (r.get('type') == 'DOOR' and r.get('b') and 'gate' in r['id'].lower() and str(r.get('k')).lower().startswith(mine)
                        and min(math.hypot(r['p'][0] - x, r['p'][1] - y) for x, y in pts) <= reach):
                    doors_.append(r)
    out, done = [], []
    for r in doors_:
        if any(math.hypot(r['p'][0] - dx, r['p'][1] - dy) < 700 for dx, dy in done):
            continue
        done.append((r['p'][0], r['p'][1]))
        try:
            F = front(db, r)
            F['half'] = HALF_GATE
        except NoWay:
            continue
        w = _one(db, F, skip, is_road)
        if w:
            out.append(w)
    return out


def _gate_door(db, x, y, reach=400.0):
    """The door hung in the gate at (x, y), if the mod has one there: its nearest DOOR named for a gate within reach."""
    best = None
    for gx in {int(math.floor((x + d) / 8192.0)) for d in (-reach, reach)}:
        for gy in {int(math.floor((y + d) / 8192.0)) for d in (-reach, reach)}:
            try:
                refs = mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()
            except Exception:
                continue
            for r in refs:
                if r.get('type') == 'DOOR' and r.get('b') and 'gate' in r['id'].lower():
                    d = math.hypot(r['p'][0] - x, r['p'][1] - y)
                    if d <= reach and (best is None or d < best[0]):
                        best = (d, r)
    return best[1] if best else None
