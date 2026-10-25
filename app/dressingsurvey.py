"""How the game dresses a kit's rooms, learned from its own interiors: the thin panels it lays over the
tiles' walls (Tamriel Data's Gold Coast set has two sets of them: WallRichAddon, pale carved ashlar, and
WallStoneAddon, grey stone, which make Anvil's guild halls and its castle-like halls out of the same timber
house kit), the pilasters it stands where walls meet, the floor sheets, the cornice along the ceiling, the
arches over the openings between two tiles, and the railings along a gallery's edge over a two-storey hall.

A dressing is a set of panels used together: the places are sorted by the panels they use most (a
place with three or more of one set is dressed in it), and every rule is measured per dressing against
the game's undressed places ('plain') as the control. Offsets are kept in a canonical frame: as if the
thing stood on the tile's own W side, in the tile's frame; the builder turns them to any side (`place`).

A "well" is the game's two-storey hall: a column with no tile on either storey, ringed by tiles on both,
with a floor sheet at the bottom, a ceiling slab at the top, railings along the gallery's edge above and
pillars at its corners (Anvil's guild of mages, the conservatory of Saint Laeca, the bazaar).

rules(db, style, dressing) -> what to lay and how often; dressings(db, style) -> the ones worth offering."""
import math
import re
from collections import Counter, defaultdict

import kits
import mapdata
import variantsurvey

_cache = {}
SIDES = kits.SIDES
VEC = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
MIN_PLACES = 8               # a dressing worth offering: this many places of the game dressed in it
MIN_PANEL_SHARE = 0.4        # ... and its panels on at least this share of the walled sides there
LOOSE_WALL_RE = re.compile(r'^wall_\d+$')


def turn_xy(lx, ly, q):
    """A local offset turned q quarter turns clockwise (the game's way: N -> E)."""
    for _ in range(q % 4):
        lx, ly = ly, -lx
    return lx, ly


def _local(dx, dy, rz):
    """A world offset in the frame of something turned rz."""
    c, s = math.cos(rz), math.sin(rz)
    return dx * c - dy * s, dx * s + dy * c


def _world(lx, ly, rz):
    c, s = math.cos(rz), math.sin(rz)
    return lx * c + ly * s, -lx * s + ly * c


def _side_of(lx, ly):
    if abs(lx) >= abs(ly):
        return 'E' if lx > 0 else 'W'
    return 'N' if ly > 0 else 'S'


def _q(rz):
    return int(round(rz / (math.pi / 2))) % 4


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0


def kind_of(low, b, T, H):
    """What a thing of the kit is, by its shape: 'panel' (a plane a tile long and a storey tall, laid over a
    wall or standing as an arch on an edge), 'pillar' (a square footprint well under half a tile), 'sheet'
    (a flat sheet a tile across at floor level), 'ceiling' (a slab a tile across at the top of the storey),
    'cornice' (a strip up at the ceiling along a side), 'rail' (a tile long, low), or None."""
    name = low.rsplit('_i_', 1)[-1]
    w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
    thin, long_ = min(w, d), max(w, d)
    if 'pillar' in low or 'column' in low or 'post' in low or 'tilecol' in low:
        return 'pillar' if max(w, d) <= T * 0.55 else None
    if 'window' in low or 'stair' in low:
        return None
    if 'arch' in low and T * 0.8 <= long_ <= T * 1.15 and thin <= T * 0.3 and b[2] >= H * 0.5:
        return 'arch'                 # (an arch over the join of two tiles, up at the ceiling)
    if abs(long_ - T) <= T * 0.12 and abs(thin - T) <= T * 0.12:
        if h <= 8 and abs(b[2]) <= 8:
            return 'sheet'
        if h <= 48 and b[2] >= H * 0.8:
            return 'ceiling'
        return None
    if thin <= 4 and T * 0.8 <= long_ <= T * 1.15 and h >= H * 0.8:
        return 'panel'
    if thin <= T * 0.35 and T * 0.8 <= long_ <= T * 1.15 and h >= H * 0.8 and 'wall' in low and 'addon' not in low:
        return 'wall'                 # (a loose wall stood on a tile's open side)
    if thin <= T * 0.35 and T * 0.8 <= long_ <= T * 1.15 and h >= H * 0.8 and 'door' in low:
        return 'doorwall'             # (a loose wall with a doorway through it)
    if thin <= T * 0.2 and T * 0.8 <= long_ <= T * 1.15 and h <= 100 and b[2] >= H * 0.85:
        return 'cornice'
    if 'rail' in low and thin <= 64 and T * 0.75 <= long_ <= T * 1.15 and h <= 160 and b[2] < H * 0.6:
        return 'rail'
    return None


def _survey(db, style):
    kp = kits.kit_pieces(db, style)
    if not kp:
        return {}
    T, H = kp['tile'], kp['height']
    ids = {p['id'].lower(): p for p in kp['pieces']}
    pre = style.lower() + '_'
    bounds = {}

    def box(low):
        if low not in bounds:
            ri = db.resolve_id(low)
            bounds[low] = (mapdata.object_bounds(db, ri) if ri is not None else None, db.recs[ri][1] if ri is not None else low)
        return bounds[low]

    # the panel sets: thin full-height planes named alike but for their number
    panel_set = {}
    for ri in kp['ris']:
        low = db.recs[ri][1].lower()
        b = mapdata.object_bounds(db, ri)
        if b and kind_of(low, b, T, H) == 'panel':
            panel_set[low] = low[len(pre):].rsplit('_', 1)[0]
    walk = variantsurvey._walk(db, style, limit=400)
    per = {}

    def acc(d):
        if d not in per:
            per[d] = {'places': 0, 'tiles': 0, 'walled': 0, 'outside': 0, 'open_edges': 0, 'door_edges': 0,
                      'corner': Counter(), 'corner_pillar': Counter(), 'corner_ids': Counter(), 'corner_group': Counter(),
                      'inner': 0, 'inner_pillar': 0, 'inner_ids': Counter(), 'inner_group': Counter(),
                      'well': 0, 'well_edges_up': 0, 'well_edges_low': 0, 'well_low_open': 0, 'well_corner': 0, 'well_corner_pillar': Counter(),
                      'things': defaultdict(lambda: {'n': 0, 'on': Counter(), 'cx': [], 'cy': [], 'dz': [], 'dq': Counter()}),
                      'stairs': Counter(), 'jambs': Counter(), 'cells': [],
                      'stair_faces': defaultdict(Counter), 'jamb_panels': defaultdict(Counter)}
        return per[d]

    for ck, pieces, others in walk:
        if not pieces:
            continue
        # the grid's origin from the tiles themselves (the game's grids aren't on multiples of the tile)
        ox = Counter(round(pos[0] % T) for _l, pos in pieces).most_common(1)[0][0]
        oy = Counter(round(pos[1] % T) for _l, pos in pieces).most_common(1)[0][0]
        gxy = lambda x, y: (int(round((x - ox) / T)), int(round((y - oy) / T)))
        at = {}
        for low, pos in pieces:
            gx, gy = gxy(pos[0], pos[1])
            at[(gx, gy, int(round(pos[2] / 64.0)))] = (low, pos)
        sets = Counter(panel_set[o[0]] for o in others if o[0] in panel_set)
        dressing = 'plain'
        if sets:
            top, n = sets.most_common(1)[0]
            if n >= 3:
                dressing = top
        A = acc(dressing)
        A['places'] += 1
        A['tiles'] += len(at)
        A['cells'].append((ck, len(at)))
        wall = {}
        for key, (low, pos) in at.items():
            pw = kits.rotate(ids[low]['pattern'], _q(pos[5]))
            wall[key] = {s: pw[s] for s in SIDES}
        # the loose walls (and door walls) the game stands on a tile's open side count as that side's wall
        for oid, op, bot, top, tag in others:
            if not oid.startswith(pre):
                continue
            b, rid = box(oid)
            if not b:
                continue
            kind = kind_of(oid, b, T, H)
            if kind not in ('wall', 'doorwall'):
                continue
            bcx, bcy = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
            wdx, wdy = _world(bcx, bcy, op[5])
            wx, wy = op[0] + wdx, op[1] + wdy
            g = gxy(wx, wy)
            gz = int(round(op[2] / 64.0))
            for dz in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5):
                key = (g[0], g[1], gz + dz)
                if key in at:
                    dx, dy = wx - at[key][1][0], wy - at[key][1][1]
                    if max(abs(dx), abs(dy)) >= T * 0.3:
                        s = _side_of(dx, dy)
                        if wall[key][s] == 'open':
                            wall[key][s] = 'wall' if kind == 'wall' else 'door'
                    break
        corner = Counter()
        for (gx, gy, gz), pw in wall.items():
            for s in SIDES:
                if pw[s] == 'wall':
                    A['walled'] += 1
                    if s in 'EW':
                        cx_ = 1 if s == 'E' else 0
                        corner[(gx + cx_, gy, gz)] += 1
                        corner[(gx + cx_, gy + 1, gz)] += 1
                    else:
                        cy_ = 1 if s == 'N' else 0
                        corner[(gx, gy + cy_, gz)] += 1
                        corner[(gx + 1, gy + cy_, gz)] += 1
                nbt = (gx + VEC[s][0], gy + VEC[s][1], gz)
                if s in 'NE' and nbt in wall:
                    o = SIDES[(SIDES.index(s) + 2) % 4]
                    a_, b_ = pw[s], wall[nbt][o]
                    if a_ == 'open' and b_ == 'open':
                        A['open_edges'] += 1
                    elif 'door' in (a_, b_):
                        A['door_edges'] += 1
        for key, n in corner.items():
            A['corner'][min(n, 3)] += 1
        # the corner points inside a room (all four tiles round them, no wall meeting): where a set stands
        # its free columns in rows (the chapel set's half columns, two back to back)
        inner = set()
        for (gx, gy, gz) in at:
            for cx_ in (0, 1):
                for cy_ in (0, 1):
                    pt = (gx + cx_, gy + cy_, gz)
                    if pt not in corner and all((gx + cx_ - 1 + dx, gy + cy_ - 1 + dy, gz) in at for dx in (0, 1) for dy in (0, 1)):
                        inner.add(pt)
        A['inner'] += len(inner)
        # the wells: a hole in a storey's tiles enclosed by them on every side (a flood fill inside the
        # storey's bounding box that never reaches its edge), with no tile over any of it on the storey above
        well = set()
        for gz in {k[2] for k in at}:
            here = {(k[0], k[1]) for k in at if k[2] == gz}
            xs = [p[0] for p in here]; ys = [p[1] for p in here]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            seen = set()
            for sx in range(x0, x1 + 1):
                for sy in range(y0, y1 + 1):
                    if (sx, sy) in here or (sx, sy) in seen:
                        continue
                    comp, todo, edge = set(), [(sx, sy)], 0
                    while todo:
                        p = todo.pop()
                        if p in comp or p in here:
                            continue
                        if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
                            edge += 1
                            continue
                        comp.add(p)
                        todo += [(p[0] + v[0], p[1] + v[1]) for v in VEC.values()]
                    seen |= comp
                    if not comp or len(comp) > 12:
                        continue
                    # (a hole that reaches the building's edge is a well too when most of its boundary is
                    # tiles: the game closes such a hall's outer side with a two-storey loose wall)
                    bound = sum(1 for p in comp for v in VEC.values() if (p[0] + v[0], p[1] + v[1]) in here)
                    if bound < 0.6 * (bound + edge):
                        continue
                    # (a floorless upper-storey piece over the hole, the Hlaalu manor's NoFloor pieces, is the
                    # hall's upper storey, not a floor over it)
                    cand = {p for p in comp if (p[0], p[1], gz + 4) not in at or ids[at[(p[0], p[1], gz + 4)][0]].get('floorless')}
                    if len(cand) >= max(1, len(comp) // 2) and any((p[0] + v[0], p[1] + v[1], gz + 4) in at for p in cand for v in VEC.values()):
                        well |= {(p[0], p[1], gz) for p in cand}
        A['well'] += len(well)
        # sides open to nothing (no tile beyond on this storey, not a well): a loose wall stands there in
        # the game, or the building's edge
        for (gx, gy, gz), pw in wall.items():
            for s in SIDES:
                beyond = (gx + VEC[s][0], gy + VEC[s][1], gz)
                if pw[s] == 'open' and beyond not in at and beyond not in well:
                    A['outside'] += 1
        wcorner = set()
        for (gx, gy, gz) in well:
            for s, v in VEC.items():
                o = SIDES[(SIDES.index(s) + 2) % 4]
                low_n = (gx + v[0], gy + v[1], gz)
                up_n = (gx + v[0], gy + v[1], gz + 4)
                if low_n in at:
                    A['well_edges_low'] += 1
                    if wall[low_n][o] != 'wall':
                        A['well_low_open'] += 1
                if up_n in at:
                    A['well_edges_up'] += 1
            for cx_ in (0, 1):
                for cy_ in (0, 1):
                    if any((gx + cx_ - 1 + dx, gy + cy_ - 1 + dy, gz) in at for dx in (0, 1) for dy in (0, 1)):
                        wcorner.add((gx + cx_, gy + cy_, gz))
                        wcorner.add((gx + cx_, gy + cy_, gz + 4))
        A['well_corner'] += len(wcorner)
        # the stairs' own walls: a one-tile stair is one model two storeys tall with its side walls built in,
        # and the game lays the dressing's panels over them at the stair's own origin, turned to each wall,
        # storey by storey (Gold Coast's Stair_01: both long sides on both storeys, its head wall upstairs)
        pans = [(oid, op) for oid, op, _b, _t, _g in others if oid in panel_set]
        for oid, op, bot, top, tag in others:
            if not oid.startswith(pre) or 'stair' not in oid[len(pre):]:
                continue
            _sb, srid = box(oid)
            faces = set()
            for pid, pp in pans:
                if abs(pp[0] - op[0]) <= 24 and abs(pp[1] - op[1]) <= 24 and -24 <= pp[2] - op[2] <= 2 * H + 24:
                    faces.add((_q(pp[5] - op[5]), int(round((pp[2] - op[2]) / float(H)))))
            A['stair_faces'][srid]['n'] += 1
            for f_ in faces:
                A['stair_faces'][srid]['%d,%d' % f_] += 1
        # the door panels: a doorway's jamb has its panel with the doorway cut in it at the jamb's own origin,
        # turned as the jamb is, and often a second one turned about for the wall's other face (Gold Coast:
        # DJambRich_01 with WallRichAddon_03, DJambRich_02 with _02, the stone set's likewise)
        for oid, op, bot, top, tag in others:
            if not oid.startswith(pre) or not ('jamb' in oid[len(pre):] or 'frame' in oid[len(pre):]):
                continue
            _jb, jrid = box(oid)
            A['jamb_panels'][jrid]['n'] += 1
            c_, s_ = math.cos(op[5]), math.sin(op[5])
            for pid, pp in pans:
                dx, dy = pp[0] - op[0], pp[1] - op[1]
                if abs(dx * c_ - dy * s_) < 40 and abs(dx * s_ + dy * c_) < 40 and abs(pp[2] - op[2]) < 40:
                    A['jamb_panels'][jrid][box(pid)[1]] += 1
        pillar_at = {}
        for oid, op, bot, top, tag in others:
            if not oid.startswith(pre):
                continue
            b, rid = box(oid)
            if not b:
                continue
            name = oid[len(pre):]
            if 'stair' in name:
                A['stairs'][rid] += 1
                continue
            if 'jamb' in name or 'frame' in name:
                A['jambs'][rid] += 1
            kind = kind_of(oid, b, T, H)
            if not kind:
                continue
            bcx, bcy = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
            wdx, wdy = _world(bcx, bcy, op[5])
            wx, wy = op[0] + wdx, op[1] + wdy
            gz = int(round(op[2] / 64.0))
            th = A['things'][rid]
            th['n'] += 1
            if kind == 'pillar':
                px, py = (wx - ox) / T + 0.5, (wy - oy) / T + 0.5
                if abs(px - round(px)) < 0.16 and abs(py - round(py)) < 0.16:
                    for dz in (0, 1, -1, 2, -2, 3, -3, 4):
                        key = (int(round(px)), int(round(py)), gz + dz)
                        if key in corner or key in wcorner or key in inner:
                            # (the turn that puts the pillar's body on the point's +x side: how the game
                            # turns a half column against a wall, and the pairs it stands back to back)
                            lx, ly = _local(wx - ((key[0] - 0.5) * T + ox), wy - ((key[1] - 0.5) * T + oy), 0)
                            pillar_at.setdefault(key, []).append((rid, _q(op[5]), round(lx), round(ly)))
                            th['on']['corner' if key in corner else 'well corner' if key in wcorner else 'inner'] += 1
                            th['dz'].append(round(op[2] - key[2] * 64))
                            th['dq'][_q(op[5])] += 1
                            break
                    else:
                        th['on']['free'] += 1
                else:
                    th['on']['free'] += 1
                continue
            gx, gy = gxy(wx, wy)
            if kind in ('sheet', 'ceiling'):
                here = (gx, gy, gz)
                if here in well or (gx, gy, gz - 4) in well:
                    th['on']['well' if kind == 'sheet' else 'well top'] += 1
                    th['dz'].append(round(op[2] - (gz if kind == 'sheet' else gz - 4) * 64))
                elif here in at:
                    th['on']['tile'] += 1
                    th['dz'].append(round(op[2] - at[here][1][2]))
                else:
                    th['on']['nothing'] += 1
                continue
            # on a side of a tile: the tile holding the body (a panel 9 in from the edge), else, for a thing
            # on the edge line itself (an arch, a railing), the tile on either side of it along its thin axis
            thin_x = (b[3] - b[0]) < (b[4] - b[1])
            nx, ny = _world(1 if thin_x else 0, 0 if thin_x else 1, op[5])
            tile_key = None
            for (qx, qy) in ((wx, wy), (wx + nx * T * 0.3, wy + ny * T * 0.3), (wx - nx * T * 0.3, wy - ny * T * 0.3)):
                g = gxy(qx, qy)
                for dz in (0, 1, -1, 2, -2):
                    if (g[0], g[1], gz + dz) in at:
                        tile_key = (g[0], g[1], gz + dz)
                        break
                if tile_key:
                    break
            if not tile_key:
                th['on']['nothing'] += 1
                continue
            low, pos = at[tile_key]
            dx, dy = wx - pos[0], wy - pos[1]
            if max(abs(dx), abs(dy)) < T * 0.3:
                th['on']['centre'] += 1
                continue
            lx, ly = _local(dx, dy, pos[5])
            lside = _side_of(lx, ly)
            wside = _side_of(dx, dy)
            what = wall[tile_key][wside]
            beyond = (tile_key[0] + VEC[wside][0], tile_key[1] + VEC[wside][1], tile_key[2])
            if what == 'open':
                what = 'well' if beyond in well or (beyond[0], beyond[1], beyond[2] - 4) in well else ('open' if beyond in at else 'outside')
            th['on'][what] += 1
            k = (3 - SIDES.index(lside)) % 4
            o_x, o_y = _local(op[0] - pos[0], op[1] - pos[1], pos[5])
            o_x, o_y = turn_xy(o_x, o_y, k)
            th['cx'].append(round(o_x)); th['cy'].append(round(o_y)); th['dz'].append(round(op[2] - pos[2]))
            th['dq'][(_q(op[5] - pos[5]) + k) % 4] += 1
        for pt, n in corner.items():
            if pt in pillar_at:
                A['corner_pillar'][min(n, 3)] += 1
                A['corner_ids'][pillar_at[pt][0][0]] += 1
                A['corner_group'][len(pillar_at[pt])] += 1
        for pt in wcorner:
            if pt in pillar_at:
                A['well_corner_pillar'][pillar_at[pt][0][0]] += 1
        for pt in inner:
            if pt in pillar_at:
                A['inner_pillar'] += 1
                A['inner_ids'][pillar_at[pt][0][0]] += 1
                # how the game groups them at one point: ids and quarter turns, sorted
                A['inner_group'][tuple(sorted((r_, q_) for r_, q_, _x, _y in pillar_at[pt]))] += 1
    out = {}
    for d, A in per.items():
        things = {}
        for rid, th in A['things'].items():
            if th['n'] < 4:
                continue
            things[rid] = {'n': th['n'], 'on': dict(th['on']), 'x': _med(th['cx']), 'y': _med(th['cy']), 'dz': _med(th['dz']),
                           'turn': th['dq'].most_common(1)[0][0] if th['dq'] else 0,
                           'turn_share': round(th['dq'].most_common(1)[0][1] / float(sum(th['dq'].values())), 2) if th['dq'] else 0}
        out[d] = {'places': A['places'], 'tiles': A['tiles'], 'walled_sides': A['walled'], 'outside_sides': A['outside'], 'open_edges': A['open_edges'],
                  'door_edges': A['door_edges'], 'corners': {k: [A['corner'][k], A['corner_pillar'][k]] for k in sorted(A['corner'])},
                  'corner_ids': dict(A['corner_ids'].most_common(3)), 'corner_group': dict(A['corner_group']),
                  'inner': A['inner'], 'inner_pillar': A['inner_pillar'], 'inner_ids': dict(A['inner_ids'].most_common(3)),
                  'inner_group': [(list(k), v) for k, v in A['inner_group'].most_common(3)],
                  'wells': A['well'], 'well_edges_up': A['well_edges_up'], 'well_edges_low': A['well_edges_low'], 'well_low_open': A['well_low_open'],
                  'well_corners': A['well_corner'], 'well_corner_pillars': dict(A['well_corner_pillar'].most_common(3)),
                  'things': things, 'stairs': dict(A['stairs'].most_common(8)), 'jambs': dict(A['jambs'].most_common(6)),
                  'stair_faces': {rid: dict(c) for rid, c in A['stair_faces'].items()},
                  'jamb_panels': {rid: dict(c) for rid, c in A['jamb_panels'].items()},
                  'cells': sorted(A['cells'], key=lambda c: -c[1])[:12]}
    return out


def _disk(db, style):
    """Where this style's survey is kept on disk (keyed by the load order): the walk of a kit's places
    takes about 40 s for Gold Coast's 2,000, and the style picker asked for it on every start."""
    import os
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    # (v2, 2026-10-22: the mesh reader ignores a model's root transform as the game does; a hall's opening
    # with the kit's floorless upper-storey pieces over it counts as a well; a railing up to 64 thick and up
    # to six tenths of the storey over its origin counts as one, the Hlaalu manor's LedgeRailSide_01)
    # (v3, 2026-10-25: the panels over the stairs' own walls, per stair model: 'stair_faces'; v4: each door
    # jamb's door panel, 'jamb_panels')
    return os.path.join(folder, 'dressingsurvey_%s_%s_v4.json' % (style.lower(), taste.sig(db)))


def survey(db, style):
    import json
    key = ('survey', style.lower())
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = _disk(db, style)
    try:
        with open(path, encoding='utf-8') as f:
            out = json.load(f)
        # (json turns the per-dressing 'corners' keys into strings: back to ints)
        for s in out.values():
            s['corners'] = {int(k): v for k, v in s['corners'].items()}
        _cache[key] = (db.recs, out)
        return out
    except Exception:
        pass
    out = _survey(db, style)
    _cache[key] = (db.recs, out)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


def rules(db, style, dressing):
    """What the builder lays for this dressing, with the game's shares. {'places', 'panels': [(id, share of
    walled sides, canon)], 'loose_panels': [(id, share of sides open to nothing, canon)] (the same panels
    over the loose walls at the building's edge), 'arches': [(id, share of open joins, share of doorways,
    canon)], 'beam': (id, share of open joins, share of doorways, canon) | None (a beam at the ceiling
    across the join of two tiles), 'floor': (id, share of tiles) | None (a floor sheet over the tile),
    'pillar': {'id', 'corner2': share of corner points where two walls meet, 'corner1': ... where a wall
    ends, 'well': share of a well's corner points, 'well_id'}, 'rails': [(id, share of gallery edges,
    canon)], 'well': {'sheet': (id, share), 'ceiling': (id, share, dz), 'open_low': share of the lower
    ring's sides open to the well, 'n'}, 'jambs': {plain id: rich twin}, 'stairs': [(id, n)]}; canon =
    {'x', 'y', 'dz', 'turn'}: the thing's origin in the tile's frame with the thing on the tile's W side."""
    s = survey(db, style).get(dressing)
    if not s:
        return None
    kp = kits.kit_pieces(db, style)
    T, H = kp['tile'], kp['height']
    walled = float(max(1, s['walled_sides']))
    canon = lambda th: {'x': th['x'], 'y': th['y'], 'dz': th['dz'], 'turn': th['turn']}
    panels, loose_panels, arches, door_arches, rails, beam, floor, ceiling, sheet = [], [], [], [], [], None, None, None, None
    door_panels = []             # (id, share of doorways, canon): the panels with a doorway cut in them
    open_e, door_e = float(max(1, s['open_edges'])), float(max(1, s['door_edges']))
    for rid, th in sorted(s['things'].items(), key=lambda kv: -kv[1]['n']):
        low = rid.lower()
        ri = db.resolve_id(low)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        kind = kind_of(low, b, T, H)
        on = th['on']
        tot = float(max(1, sum(on.values())))
        if kind in ('panel', 'arch'):
            # (a panel over a wall; the same panel also stands over the loose walls the game puts on a
            # tile's open side at the building's edge)
            if kind == 'panel' and on.get('wall', 0) / tot >= 0.4:
                panels.append((rid, round(on['wall'] / walled, 3), canon(th)))
                if on.get('outside', 0) >= 3:
                    loose_panels.append((rid, round(on['outside'] / float(max(1, s['outside_sides'])), 3), canon(th)))
            elif (on.get('open', 0) + on.get('door', 0)) / tot >= (0.2 if kind == 'arch' else 0.4):
                # an arch over the opening between two tiles: how often per open join, and per doorway
                arches.append((rid, round(on.get('open', 0) / open_e, 3), round(on.get('door', 0) / door_e, 3), canon(th)))
                # (a panel with a doorway cut in it, over a doorway's wall: Gold Coast's WallRichAddon_03/_02)
                if kind == 'panel' and on.get('door', 0) >= 3:
                    door_panels.append((rid, round(on['door'] / door_e, 3), canon(th)))
        elif kind == 'cornice' and (on.get('open', 0) + on.get('door', 0)) / tot >= 0.4 and beam is None:
            # (the Gold Coast "skirting" is a beam up at the ceiling across the join of two tiles)
            beam = (rid, round(on.get('open', 0) / open_e, 3), round(on.get('door', 0) / door_e, 3), canon(th))
        elif kind == 'sheet':
            if on.get('tile', 0) / tot >= 0.5 and floor is None:
                floor = (rid, round(on['tile'] / float(max(1, s['tiles'])), 3))
            if on.get('well', 0) >= 3 and (sheet is None or on['well'] > sheet[2]):
                sheet = (rid, round(on['well'] / float(max(1, s['wells'])), 3), on['well'])
        elif kind == 'ceiling' and on.get('well top', 0) >= 3 and (ceiling is None or on['well top'] > ceiling[3]):
            ceiling = (rid, round(on['well top'] / float(max(1, s['wells'])), 3), th['dz'], on['well top'])
        elif kind == 'rail' and on.get('well', 0) >= 3:
            rails.append((rid, round(on['well'] / float(max(1, s['well_edges_up'])), 3), canon(th)))
    c = s['corners']
    pil = {'id': next(iter(s['corner_ids']), None), 'well_id': next(iter(s['well_corner_pillars']), None),
           'corner2': round(c.get(2, [0, 0])[1] / float(max(1, c.get(2, [0, 0])[0])), 3),
           'corner1': round(c.get(1, [0, 0])[1] / float(max(1, c.get(1, [0, 0])[0])), 3),
           'well': round(sum(s['well_corner_pillars'].values()) / float(max(1, s['well_corners'])), 3),
           # free columns at the corner points inside rooms, and how the game groups them there
           'inner': round(s['inner_pillar'] / float(max(1, s['inner'])), 3),
           'inner_group': s['inner_group'][0][0] if s['inner_group'] else None}
    # the rich twins of the kit's door frames and jambs (DJamb_01 -> DJambRich_01), where the dressed
    # places use the twin more than the plain one
    swaps = {}
    for rid, n in s['jambs'].items():
        low = rid.lower()
        if 'rich' in low:
            continue
        twin = re.sub(r'_(\d+)$', r'rich_\1', low)
        twin_id = next((r for r in s['jambs'] if r.lower() == twin), None)
        if twin_id and s['jambs'][twin_id] > n:
            swaps[low] = twin_id
    # the stairs' own walls the game panels: per stair model, the (quarter turn from the stair's, storey)
    # faces it dresses in a quarter of its dressed stairs or more
    stair_faces = {}
    for rid, c in (s.get('stair_faces') or {}).items():
        n = c.get('n', 0)
        if n >= 3:
            faces = sorted(tuple(int(v) for v in k.split(',')) for k, m in c.items() if k != 'n' and m >= 0.25 * n)
            if faces:
                stair_faces[rid.lower()] = faces
    # each jamb's door panel: the panel the game stands at its origin most, when it does for a quarter of
    # that jamb's doorways or more
    jamb_panels = {}
    for rid, c in (s.get('jamb_panels') or {}).items():
        n = c.get('n', 0)
        best = max(((k, m) for k, m in c.items() if k != 'n'), key=lambda x: x[1], default=None)
        if n >= 3 and best and best[1] >= 0.25 * n:
            jamb_panels[rid.lower()] = best[0]
    return {'places': s['places'], 'panels': panels, 'loose_panels': loose_panels, 'arches': arches, 'beam': beam, 'floor': floor,
            'stair_faces': stair_faces, 'door_panels': door_panels, 'jamb_panels': jamb_panels,
            'pillar': pil, 'rails': rails,
            'well': {'sheet': sheet and sheet[:2], 'ceiling': ceiling and ceiling[:3],
                     'open_low': round(s['well_low_open'] / float(max(1, s['well_edges_low'])), 3), 'n': s['wells']},
            'jambs': swaps, 'stairs': sorted(s['stairs'].items(), key=lambda kv: -kv[1])}


def has_panels(db, style):
    """Whether the kit has any wall panel at all (cheap: no walk of the game's places)."""
    kp = kits.kit_pieces(db, style)
    if not kp:
        return False
    key = ('panels', style.lower())
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    T, H = kp['tile'], kp['height']
    got = False
    for ri in kp['ris']:
        b = mapdata.object_bounds(db, ri)
        if b and kind_of(db.recs[ri][1].lower(), b, T, H) == 'panel':
            got = True
            break
    _cache[key] = (db.recs, got)
    return got


def dressings(db, style):
    """The dressings of this kit worth offering as styles of their own: [(dressing, places, panel share)],
    the game's most used first; one with MIN_PLACES places whose panels cover MIN_PANEL_SHARE of the walls."""
    out = []
    for d, s in survey(db, style).items():
        if d == 'plain' or s['places'] < MIN_PLACES:
            continue
        r = rules(db, style, d)
        share = sum(sh for _i, sh, _c in r['panels']) if r else 0
        if share >= MIN_PANEL_SHARE:
            out.append((d, s['places'], round(share, 2)))
    return sorted(out, key=lambda x: -x[1])


def place(canon, cx, cy, floor_z, side):
    """World pose (x, y, z, 0, 0, rz) for a thing kept in the canonical frame (on the tile's W side), put
    on world side `side` of a tile centred (cx, cy) whose floor is at floor_z."""
    q = (SIDES.index(side) + 1) % 4
    ox, oy = turn_xy(canon['x'], canon['y'], q)
    return (cx + ox, cy + oy, floor_z + canon['dz'], 0, 0, ((canon['turn'] + q) % 4) * math.pi / 2)


def report(db, style):
    s = survey(db, style)
    lines = []
    for d, v in sorted(s.items(), key=lambda kv: -kv[1]['places']):
        lines.append('%s: %d places, %d tiles, %d walled sides, %d sides open to nothing, %d open edges, %d door edges; wells %d (gallery edges %d, lower ring sides %d of which open %d, corners %d, pillars %s)' % (
            d, v['places'], v['tiles'], v['walled_sides'], v['outside_sides'], v['open_edges'], v['door_edges'], v['wells'], v['well_edges_up'], v['well_edges_low'], v['well_low_open'], v['well_corners'], v['well_corner_pillars']))
        lines.append('  places: %s' % v['cells'][:8])
        lines.append('  corner points by walls meeting -> [points, with a pillar]: %s, pillars %s, per point %s; inner points %d with a pillar %d %s groups %s' % (
            v['corners'], v['corner_ids'], v['corner_group'], v['inner'], v['inner_pillar'], v['inner_ids'], v['inner_group']))
        lines.append('  stairs %s' % v['stairs'])
        lines.append('  jambs %s' % v['jambs'])
        for rid, th in sorted(v['things'].items(), key=lambda kv: -kv[1]['n']):
            lines.append('  %-34s n %4d on %s at x %d y %d dz %d turn %d (%.2f)' % (rid, th['n'], th['on'], th['x'], th['y'], th['dz'], th['turn'], th['turn_share']))
        r = rules(db, style, d)
        if r:
            lines.append('  rules: panels %s on loose walls %s arches (per open join, per doorway) %s beam %s floor %s pillar %s rails %s well %s jambs %s' % (
                [(p[0], p[1]) for p in r['panels']], [(p[0], p[1]) for p in r['loose_panels']], [(p[0], p[1], p[2]) for p in r['arches']],
                r['beam'] and r['beam'][:3], r['floor'], r['pillar'], [(p[0], p[1]) for p in r['rails']], r['well'], r['jambs']))
    lines.append('offered: %s' % dressings(db, style))
    return '\n'.join(lines)
