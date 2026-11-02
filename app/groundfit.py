"""Fit the ground to a building put down outdoors, the way the game's own buildings meet the ground, so a
prefab or a hand-built house needs no levelled pad first.

Measured 2026-10-24 on the game's own buildings (packaging/nexus/interior-from-exterior.md, terrain):
  - the game never levels the ground under a building: under 239 of 400 the ground rises above the door's sill
    somewhere (the houses are dug into their slopes, the walls hide it), and round them the slope goes on as it
    was (a spread of 240 round a ring 64 out, at the median);
  - its buildings stand sunk in the ground: along the edge the building's bottom is a median 217 under the
    ground, and nine in ten have a gap over 8 along less than a sixth of their edge (the rest stand on stilts
    or piers);
  - the ground a tile in front of the door is never over the sill (p10 0) and a median 52 under it.
So the fit only does what the game's buildings show: the ground is raised where the building's bottom stands
over it along its edge (to SINK over the bottom), and the door gets a landing STEP under its sill when the ground
there is over the sill or more than LANDING_MAX under it; every change blends back to the ground as it was over
BLEND. Nothing else is flattened. The building's own pieces stay where they are; rocks and plants round it
follow the ground (landscape.edit)."""
import math
import re

import landscape
import mapdata
import shellsurvey as ss
from editing import EditError

SINK = 32            # the ground at least this far up over the building's bottom along its edge
EDGE = 64            # (a ground point outside the building this near its edge shows a gap under it)
STEP = 52            # the landing in front of the door: this far under its sill (the game's median)
LANDING_MAX = 160    # (a landing lower than this under the sill is raised, unless stairs or a ladder lead up to the door)
CLIMB = re.compile(r'stair|step|ramp|ladder|platform|walkway|bridge|dock|pier')
BLEND = 256          # changes fade back to the ground as it was over this far, or BLEND_RISE times their height
BLEND_RISE = 3.0     # (a 200 drop to a landing faded over 256 left a trench of 50-70 degrees, the town practice of 2026-11-01;
                     # a smooth fade is steepest at its middle, 1.5 times its mean: 3x keeps that under 30 degrees)
BLEND_MAX = 1024
N = landscape.N
CELL = landscape.CELL


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def plan(db, b):
    """The ground changes for a building (frombuilding.building_at): {'cells': [{gx, gy, h}], 'raised', 'lowered',
    'landing', 'points'} or None when the ground already meets it as the game's do."""
    fr, group = b.get('frame'), b['group']
    if not fr:
        raise EditError('The building has no door: the ground is fitted from its door.')
    bo = ss.box_outline(group, fr)
    if not bo['cells']:
        raise EditError('The building stands on nothing the Workshop can read.')
    cells = set(bo['cells'])
    x0, y0, x1, y1 = bo['box']
    pad = BLEND_MAX + EDGE + 128
    corners = [fr.back(x, y) for x in (x0 - pad, x1 + pad) for y in (y0 - pad, y1 + pad)]
    wx0, wx1 = min(c[0] for c in corners), max(c[0] for c in corners)
    wy0, wy1 = min(c[1] for c in corners), max(c[1] for c in corners)
    land, want = {}, {}

    def height(gx, gy):
        if (gx, gy) not in land:
            L = mapdata.land(db, gx, gy)
            land[(gx, gy)] = list(L['h']) if L and L.get('h') else None
        return land[(gx, gy)]
    # every ground point (128 apart) in reach, in the building's frame
    pts = []
    for vx in range(int(math.floor(wx0 / 128)), int(math.ceil(wx1 / 128)) + 1):
        for vy in range(int(math.floor(wy0 / 128)), int(math.ceil(wy1 / 128)) + 1):
            x, y = vx * 128.0, vy * 128.0
            gx, gy = int(math.floor(x / CELL)), int(math.floor(y / CELL))
            h = height(gx, gy)
            if h is None:
                continue
            ix, iy = int(round((x - gx * CELL) / 128)), int(round((y - gy * CELL) / 128))
            lx, ly = fr.to(x, y)
            pts.append((x, y, lx, ly, gx, gy, ix, iy, h[iy * N + ix]))
    edge = [c for c in cells if any(n not in cells for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)))]
    G = ss.GRID
    raised = lowered = 0
    landing = False
    door = b.get('door')
    # (stairs, steps, a ladder or a walkway up to the door: the game's high doors have them; the ground is left)
    climb = door is not None and any(CLIMB.search(it['low']) and math.hypot(it['p'][0] - door['p'][0], it['p'][1] - door['p'][1]) < 600
                                     for it in (b.get('items') or ()))
    # (the door's own sill: the frame may come from another, higher door)
    sill = (door['p'][2] + ((door.get('b') or [0, 0, 0])[2]) * (door.get('s') or 1.0)) if door is not None and door.get('p') else fr.z
    reasons = {'sink': 0, 'landing': 0}
    for (x, y, lx, ly, gx, gy, ix, iy, z) in pts:
        c = (int(math.floor(lx / G)), int(math.floor(ly / G)))
        d_edge = 0.0 if c in cells else min(math.hypot((e[0] + 0.5) * G - lx, (e[1] + 0.5) * G - ly) for e in edge)
        target = None
        if 0 < d_edge <= EDGE:
            # (only outside the walls, where a gap shows: the ground under the building is hidden, and the game's
            # rises over the sill under 239 of 400)
            # (the building's bottom over this point: its pieces that stand over it, or the nearest of them)
            over = [it['box'][4] for it in group if it['box'][0] - EDGE <= x <= it['box'][2] + EDGE and it['box'][1] - EDGE <= y <= it['box'][3] + EDGE]
            if over:
                bottom = min(over)
                if z < bottom - 8 and bottom - z < 900:         # (a gap shows; a pier on a sea or a cliff: left as it is)
                    # (never over the door's landing; the door's own sill too: a barn's frame came from its hayloft, and
                    # its open floor was filled 300 deep, its goods buried, the city round of 2026-11-01)
                    target = min(bottom + SINK, fr.z - STEP, sill - STEP)
                    reasons['sink'] += 1
        # (the landing: the ground points nearest the spot a tile out from the door; the ground's grid is 128
        # apart, coarser than a door's width)
        if math.hypot(lx, ly + 96) <= 128:
            # (the game's ground a tile out from a door is never over its sill; far under it only with a way up)
            if z > fr.z + 16 or (z < fr.z - LANDING_MAX and not climb):
                target = fr.z - STEP
                landing = True
                reasons['landing'] += 1
        if target is not None and abs(target - z) > 4:
            want[(gx, gy, ix, iy)] = (target, x, y)
    if not want:
        return None
    # blend: every point within BLEND of a changed one moves part of the way, by its nearest change
    changed = [(k, v) for k, v in want.items()]
    out = {}
    for (x, y, lx, ly, gx, gy, ix, iy, z) in pts:
        k = (gx, gy, ix, iy)
        if k in want:
            nz = want[k][0]
        else:
            # (the change whose fade reaches here most strongly; each fades over its own reach, wider the bigger it is)
            # (towards the change's own height, never past it: added as a difference, a fill at a low corner lifted the
            # higher ground beside it as much, and an open barn up the slope filled 300 deep, the city round of 2026-11-01)
            best = None
            h0 = land[(gx, gy)][iy * N + ix]
            for (k2, (tz, cx, cy)) in changed:
                delta = tz - land[(k2[0], k2[1])][k2[3] * N + k2[2]]
                here = tz - h0
                if here * delta <= 0:
                    continue
                reach = max(BLEND, min(BLEND_MAX, BLEND_RISE * abs(delta)))
                dd = math.hypot(cx - x, cy - y)
                if dd < reach:
                    f = 1 - _smooth(dd / reach)
                    if best is None or abs(here) * f > abs(best[0]) * best[1]:
                        best = (here, f)
            if best is None:
                continue
            nz = h0 + best[0] * best[1]
        h0 = land[(gx, gy)][iy * N + ix]
        if abs(nz - h0) < 2:
            continue
        out.setdefault((gx, gy), {})[(ix, iy)] = nz
        if nz > h0:
            raised += 1
        else:
            lowered += 1
    if not out:
        return None
    res = []
    for (gx, gy), ch in out.items():
        h = list(land[(gx, gy)])
        for (ix, iy), nz in ch.items():
            h[iy * N + ix] = nz
        res.append({'gx': gx, 'gy': gy, 'h': h})
    # (a point on a cell's edge is in its neighbour's grid too: the same height there, or the ground tears)
    byc = {(r['gx'], r['gy']): r for r in res}
    for (gx, gy), ch in out.items():
        for (ix, iy), nz in ch.items():
            for ngx, ngy, nix, niy in ([(gx - 1, gy, 64, iy)] if ix == 0 else []) + ([(gx + 1, gy, 0, iy)] if ix == 64 else []) + \
                                      ([(gx, gy - 1, ix, 64)] if iy == 0 else []) + ([(gx, gy + 1, ix, 0)] if iy == 64 else []):
                if height(ngx, ngy) is None:
                    continue
                if (ngx, ngy) not in byc:
                    byc[(ngx, ngy)] = {'gx': ngx, 'gy': ngy, 'h': list(land[(ngx, ngy)])}
                byc[(ngx, ngy)]['h'][niy * N + nix] = nz
    return {'cells': list(byc.values()), 'raised': raised, 'lowered': lowered, 'landing': landing, 'points': len(want), 'reasons': reasons}


def fit(db, cell_key, ref_key):
    """Fit the ground to the building a piece outdoors belongs to (one change; the building stays put)."""
    import frombuilding
    b = frombuilding.building_at(db, cell_key, ref_key)
    pl = plan(db, b)
    if pl is None:
        return {'ok': True, 'changed': 0, 'text': 'The ground already meets this building the way the game\'s buildings meet theirs.'}
    skip = {g['k'] for g in b['group']} | {d['k'] for d in b['doors']}
    landscape.edit(db, pl['cells'], keep_objects=True, skip=skip,
                   note='Fitted the ground to %s (%d point%s raised, %d lowered%s)' % (
                       b['group'][0]['id'], pl['raised'], '' if pl['raised'] == 1 else 's', pl['lowered'],
                       ', a landing at its door' if pl['landing'] else ''))
    words = []
    if pl['raised']:
        words.append('raised round its foot where it stood over the ground (%d points)' % pl['raised'])
    if pl['lowered']:
        words.append('lowered %d points' % pl['lowered'])
    if pl['landing']:
        words.append('a landing a step under the door')
    return {'ok': True, 'changed': pl['raised'] + pl['lowered'], 'text': 'The ground: ' + '; '.join(words) + '. Undo takes it back.'}
