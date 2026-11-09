"""Harbours for made towns that live by the sea (docs/worldbuilding-next-2026-11.md, livelihoods): the game's own docks
copied whole onto a new shore.

The game's towns by what they live by (lab a14, 2026-11-08, townsurvey's 149 towns, the docks, boats, nets, farm
pieces, crops, beasts, mine doors and the people's classes in their cells and one round): of the towns with the sea
within 1,024, 71% are harbours (Seyda Neen, Hla Oad, Gnaar Mok, Khuul, Anvil), 15% farms, 9% mines; within 4,096,
53% harbours; inland 36% farms, 25% mines, 25% trade alone, 14% harbours (on rivers and lakes).

A scene is one of the game's docks as it stands: its dock pieces, boats, nets, cleats and pilings within 600 of each
other, held in the frame of its shore (its root, the dock piece on the highest ground, and the way out to the water,
towards the pieces over it). Heights stay as the game set them: docks stand at the one water level. For a new town
the scenes are tried on its shore points round its edge, turned to each point's way out; the one whose ground under
each piece is most like the game's (the shore's profile) is laid, a culture's own scenes first."""
import hashlib
import json
import math
import os
import re

import mapdata

VERSION = 1
DOCK = re.compile(r'^(ex_de_docks|t_.*_x_dock|t_.*docks|ex_imp_dock|ex_t_dock|t_imp_legion.*dock|t_de_setmh_x_pier)', re.I)
BOAT = re.compile(r'^(ex_de_rowboat|a_ex_de_rowboat|ex_skiff|ex_longboat|t_com_setharbor_boat|t_imp_setharbor_boat|t_nor_setharbor_boat)', re.I)
NET = re.compile(r'setharbor_fish|fishtrap|setharbor_net|setharbor_crate|setharbor_rope', re.I)
LINK = 600.0
MIN_PIECES = 4
FIT_MAX = 160.0                 # (the mean height difference under the pieces a scene may have on a new shore)
REACH = 2500.0                  # (shore points this far out of the town's edge are tried)
_mem = {}


def _sig(db):
    import cliffsurvey
    return cliffsurvey._sig(db)


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'harbours_%s_v%d.json' % (_sig(db), VERSION))


def learn(db):
    """[{'culture', 'town', 'pieces': [[id, fx, fy, z, turn, scale, ground under it]], 'n'}]: every dock scene of the
    game's towns, in its shore's frame (fx out to the water, fy along the shore; turn: the piece's heading against the
    way out). Cached by the load order."""
    key = _sig(db)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                _mem[key] = json.load(f)
                return _mem[key]
    except (OSError, ValueError):
        pass
    import townsurvey
    from project import ref_info
    out = []
    for t in townsurvey.survey(db)['towns']:
        cells = [tuple(c) for c in t['cells']]
        if not cells:
            continue
        xs, ys = [c[0] for c in cells], [c[1] for c in cells]
        pcs = []
        for x in range(min(xs) - 1, max(xs) + 2):
            for y in range(min(ys) - 1, max(ys) + 2):
                try:
                    refs, _h = db.cell_refs('#%d,%d' % (x, y), without_project=True)
                except Exception:
                    continue
                for ref in refs.values():
                    rid, pos, sc, dele = ref_info(ref['subs'])
                    if dele or not rid:
                        continue
                    low = rid.lower()
                    kind = 'dock' if DOCK.search(low) else 'boat' if BOAT.search(low) else 'net' if NET.search(low) else None
                    if kind:
                        pcs.append((low, kind, pos, sc or 1.0))
        if not pcs:
            continue
        # scenes: pieces within LINK of each other
        lab = [-1] * len(pcs)
        nl = 0
        for i in range(len(pcs)):
            if lab[i] >= 0:
                continue
            st = [i]
            lab[i] = nl
            while st:
                a = st.pop()
                for b in range(len(pcs)):
                    if lab[b] < 0 and math.hypot(pcs[a][2][0] - pcs[b][2][0], pcs[a][2][1] - pcs[b][2][1]) < LINK:
                        lab[b] = nl
                        st.append(b)
            nl += 1
        for c in range(nl):
            mem = [pcs[i] for i in range(len(pcs)) if lab[i] == c]
            docks = [m for m in mem if m[1] == 'dock']
            if len(mem) < MIN_PIECES or not docks:
                continue
            gs = [mapdata.terrain_z(db, m[2][0], m[2][1]) for m in mem]
            if any(g is None for g in gs):
                continue
            dg = [(mapdata.terrain_z(db, m[2][0], m[2][1]), m) for m in docks]
            root = max(dg, key=lambda v: v[0])[1]
            wet = [m for m, g in zip(mem, gs) if g < 0]
            if not wet or root[2] is None:
                continue
            wx, wy = sum(m[2][0] for m in wet) / len(wet), sum(m[2][1] for m in wet) / len(wet)
            phi = math.atan2(wy - root[2][1], wx - root[2][0])
            c_, s_ = math.cos(-phi), math.sin(-phi)
            rows = []
            for m, g in zip(mem, gs):
                dx, dy = m[2][0] - root[2][0], m[2][1] - root[2][1]
                fx, fy = dx * c_ - dy * s_, dx * s_ + dy * c_
                turn = (-m[2][5] - phi) % (2 * math.pi)
                rows.append([m[0], round(fx, 1), round(fy, 1), round(m[2][2], 1), round(turn, 4), round(m[3], 3), round(g, 1),
                             round(m[2][3], 4), round(m[2][4], 4)])
            out.append({'culture': t.get('culture') or '', 'town': t.get('name') or '', 'pieces': rows, 'n': len(rows)})
    _mem[key] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except OSError:
        pass
    return out


def shore_points(db, cx, cy, r, step=256.0):
    """[(x, y, way out)] round a town: points on land under 96 within REACH of its edge with the water within 512
    of them, and the way the ground falls to it."""
    out = []
    R = r + REACH
    n = int(R // step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = cx + i * step, cy + j * step
            d = math.hypot(x - cx, y - cy)
            if d > R or d < r * 0.6:
                continue
            g = mapdata.terrain_z(db, x, y)
            if g is None or not (0 <= g <= 96):
                continue
            best = None
            for a in range(0, 360, 30):
                ar = math.radians(a)
                w = mapdata.terrain_z(db, x + math.cos(ar) * 512, y + math.sin(ar) * 512)
                if w is not None and w < -64 and (best is None or w < best[0]):
                    best = (w, ar)
            if best:
                out.append((x, y, best[1], d))
    out.sort(key=lambda p: p[3])
    return [(x, y, a) for x, y, a, _d in out]


def fit(db, scene, x, y, phi):
    """The mean height difference between the game's ground under a scene's pieces and the ground they would have
    laid at (x, y) turned to phi; None where any piece falls off the land records."""
    c, s = math.cos(phi), math.sin(phi)
    tot = 0.0
    for row in scene['pieces']:
        fx, fy, g0 = row[1], row[2], row[6]
        g = mapdata.terrain_z(db, x + fx * c - fy * s, y + fx * s + fy * c)
        if g is None:
            return None
        tot += abs(g - g0)
    return tot / len(scene['pieces'])


FIT_GOOD = 48.0                 # (scenes fitting this well are all good: the one nearest the town's size is laid)
SIZE = {'village': 6, 'town': 12, 'city': 25}


def anchor(db, cx, cy, r, culture='', size='town', tries=12):
    """The scene to lay on the town's shore and where: (scene index, x, y, way out, its fit) or None. Among the
    scenes fitting within FIT_GOOD, the one nearest the town's size (SIZE pieces), a culture's own first; else the
    best fitting within FIT_MAX. (By fit alone the smallest scenes won every shore: four pieces fit any profile.)"""
    scenes = learn(db)
    pts = shore_points(db, cx, cy, r) if scenes else []
    if not pts:
        return None
    want = SIZE.get(size, 12)
    good, best = [], None
    for k, S in enumerate(scenes):
        own = S['culture'] == culture
        for x, y, phi in pts[:tries]:
            f = fit(db, S, x, y, phi)
            if f is None:
                continue
            if f <= FIT_GOOD:
                good.append((0 if own else 1, abs(math.log(S['n'] / float(want))), f, k, x, y, phi))
            if best is None or f < best[2]:
                best = (0, 0, f, k, x, y, phi)
    if good:
        good.sort()
        g = good[0]
    elif best is not None and best[2] <= FIT_MAX:
        g = best
    else:
        return None
    return g[3], g[4], g[5], g[6], round(g[2])


def lay(db, k, x, y, phi):
    """Scene k's pieces laid at (x, y) turned to phi: [{id, x, y, z, rx, ry, rz, s}]."""
    S = learn(db)[k]
    c, s = math.cos(phi), math.sin(phi)
    out = []
    for rid, fx, fy, z, turn, sc, _g, rx, ry in S['pieces']:
        out.append({'id': rid, 'x': round(x + fx * c - fy * s, 1), 'y': round(y + fx * s + fy * c, 1), 'z': z, 'rx': rx, 'ry': ry,
                    'rz': round((-(turn + phi)) % (2 * math.pi), 4), 's': sc})
    return out
