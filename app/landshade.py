"""Shading the ground the way the game shades it: the land's vertex colours (VCLR), learnt from the cells around.

The game's landscapes carry a colour at each of their 65 x 65 points, multiplied into the ground textures. Two
habits stand out, and both are learnt here from the landscapes near the cell being shaded (up to ~150 of them,
so it is the local region's style):
- by texture: ground that is all one texture is tinted much the same wherever it lies (grass a little
  yellow-green, roads darker, rock greyer);
- at seams: where two textures meet, the game often darkens or tints the join, which hides the hard edge.

"texture" sets each point to the learnt tint of the textures around it (blended as the textures blend);
"seams" darkens or tints only the points where two textures meet, by as much as the game does at that pair,
on top of what is there. Strength 0-1 mixes the result with the colours already there. One Undo for all.
"""
import base64
import math
import struct
from collections import defaultdict

import mapdata
from editing import EditError, commit, _require_project
from esm import iter_subrecords

N = 65
REACH = 7                      # (cells each way to learn from)
MAX_CELLS = 150
_learnt = {}


def _land_of(db, ri):
    """(texture file per patch [256, lower, '' = default], colours bytes or None) of one LAND record."""
    import landscape
    r = db.recs[ri]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    vtex, vclr = None, None
    for st, sd in iter_subrecords(data):
        if st == 'VTEX' and len(sd) >= 512:
            vtex = struct.unpack_from('<256H', sd)
        elif st == 'VCLR' and len(sd) >= N * N * 3:
            vclr = bytes(sd[:N * N * 3])
    allt = landscape._ltex_all(db)
    grid = [''] * 256
    if vtex:
        n = 0
        for y1 in range(4):
            for x1 in range(4):
                for y2 in range(4):
                    for x2 in range(4):
                        v = vtex[n]
                        n += 1
                        if v:
                            ent = allt.get((r[3], v - 1)) or next((e for (f, i), e in allt.items() if i == v - 1), None)
                            grid[(y1 * 4 + y2) * 16 + x1 * 4 + x2] = ent[1].lower() if ent else ''
    return grid, vclr


# (each point's share of the patches around it, as the 3D view and the game blend them: a patch counts fully
# at its middle and fades towards its neighbours' middles)
def _smooth(t):
    return t * t * (3 - 2 * t)


_WEIGHTS = []
for _p in range(N):
    g = _p / 4.0 - 0.5
    b = math.floor(g)
    f = _smooth(g - b)
    _WEIGHTS.append(((max(0, min(15, b)), 1 - f), (max(0, min(15, b + 1)), f)))


def _mix(grid, x, y):
    """{texture: weight} at point (x, y)."""
    out = {}
    for px, wx in _WEIGHTS[x]:
        for py, wy in _WEIGHTS[y]:
            w = wx * wy
            if w > 0:
                t = grid[py * 16 + px]
                out[t] = out.get(t, 0) + w
    return out


def learn(db, gx, gy):
    """{tint: {texture: [r, g, b]}, seam: {(a, b): [ratio r, g, b]}, cells} from the landscapes near (gx, gy)."""
    key = (gx // 4, gy // 4)
    hit = _learnt.get(key)
    if hit and hit[0] is db.recs:
        return hit[1]
    cand = []
    for dx in range(-REACH, REACH + 1):
        for dy in range(-REACH, REACH + 1):
            lst = [v for v in db.by_key.get(('LAND', '%d,%d' % (gx + dx, gy + dy)), []) if v not in db.dead]
            if lst:
                cand.append((dx * dx + dy * dy, lst[-1]))
    cand.sort()
    tint_s, tint_n, seam_s, seam_n = {}, {}, {}, {}
    used = 0
    for _d, ri in cand[:MAX_CELLS]:
        grid, col = _land_of(db, ri)
        if not col or len(set(grid)) < 1:
            continue
        used += 1
        pure = {}
        # first the tints of each texture where it is alone; then the seams against them
        # (every other point is plenty to learn from, and four times quicker)
        mixes = [[None] * N for _ in range(N)]
        for y in range(0, N, 2):
            for x in range(0, N, 2):
                m = _mix(grid, x, y)
                mixes[y][x] = m
                if len(m) == 1:
                    t = next(iter(m))
                    o = (y * N + x) * 3
                    s = tint_s.setdefault(t, [0, 0, 0])
                    s[0] += col[o]; s[1] += col[o + 1]; s[2] += col[o + 2]
                    tint_n[t] = tint_n.get(t, 0) + 1
                    p = pure.setdefault(t, [0, 0, 0, 0])
                    p[0] += col[o]; p[1] += col[o + 1]; p[2] += col[o + 2]; p[3] += 1
        local = {t: [p[0] / p[3], p[1] / p[3], p[2] / p[3]] for t, p in pure.items() if p[3] >= 4}
        for y in range(0, N, 2):
            for x in range(0, N, 2):
                m = mixes[y][x]
                if len(m) != 2:
                    continue
                (a, wa), (b, wb) = sorted(m.items())
                if min(wa, wb) < 0.3 or a not in local or b not in local:
                    continue
                # (the seam against what the two textures have on their own in this cell: how much darker the join is)
                o = (y * N + x) * 3
                base = [local[a][i] * wa + local[b][i] * wb for i in range(3)]
                s = seam_s.setdefault((a, b), [0.0, 0.0, 0.0])
                for i in range(3):
                    s[i] += col[o + i] / max(8.0, base[i])
                seam_n[(a, b)] = seam_n.get((a, b), 0) + 1
    out = {'tint': {t: [s[0] / tint_n[t], s[1] / tint_n[t], s[2] / tint_n[t]] for t, s in tint_s.items() if tint_n[t] >= 10},
           'seam': {k: [v / seam_n[k] for v in s] for k, s in seam_s.items() if seam_n[k] >= 6},
           'cells': used}
    # (any pair the game has no example of nearby: the average seam of the region)
    if out['seam']:
        avg = [sum(v[i] for v in out['seam'].values()) / len(out['seam']) for i in range(3)]
    else:
        avg = [1.0, 1.0, 1.0]
    out['seam_any'] = avg
    _learnt[key] = (db.recs, out)
    return out


def learn_near(db, gx, gy, region=''):
    """learn() at the cell, or (land far out in the sea, with no game landscapes round it) at the middle cell of the
    region it takes after (landsurvey's cells)."""
    L = learn(db, gx, gy)
    if L['cells'] >= 8 or not region:
        return L
    import landsurvey
    s = landsurvey.ready(db)
    ks = [k for k, c in ((s or {}).get('cells') or {}).items() if c['region'] == region.lower() and c['k'] != 'sea' and c['vclr']]
    if not ks:
        return L
    xs = sorted(int(k.split(',')[0]) for k in ks)
    ys = sorted(int(k.split(',')[1]) for k in ks)
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    best = min(ks, key=lambda k: (int(k.split(',')[0]) - mx) ** 2 + (int(k.split(',')[1]) - my) ** 2)
    return learn(db, *(int(v) for v in best.split(',')))


def hollow_shades(db, region):
    """{curvature bin: brightness against level ground} for the region (landsurvey 'shade': the game's vertex
    colours at hollows (+) and crests (-), over each texture's own colour); the game's mean if the region has none."""
    import landsurvey
    s = landsurvey.ready(db)
    regs = (s or {}).get('regions') or {}
    R = regs.get(region or '')
    tab = (R or {}).get('shade') or {}
    if '0' not in tab or len(tab) < 3:
        acc = defaultdict(lambda: [0.0, 0])
        for r in regs.values():
            for k, (v, n) in (r.get('shade') or {}).items():
                acc[k][0] += v * n
                acc[k][1] += n
        tab = {k: [a[0] / a[1], a[1]] for k, a in acc.items() if a[1]}
    if '0' not in tab:
        return {}
    level = tab['0'][0]
    return {int(k): v / level for k, (v, _n) in tab.items()}


def shade(db, cells, mode='seams', strength=1.0, note=True, region=''):
    """cells: ['gx,gy' or [gx, gy]]. mode 'texture', 'seams' or 'hollows' (darker in the hollows, lighter on the
    crests, by as much as the game's are in the region). Writes the new colours into the mod, one step (note=False:
    no step of its own, for a bigger change that makes one; no error when there is nothing to shade either)."""
    import landscape
    _require_project(db)
    strength = max(0.0, min(1.0, float(strength)))
    done, notes = 0, []
    for c in cells or []:
        gx, gy = (int(v) for v in (c.split(',') if isinstance(c, str) else c))
        w = landscape._winner(db, gx, gy)
        if w is None:
            continue
        grid, col = _land_of(db, w)
        new, n = colours(db, gx, gy, mode, strength, region, grid, col)
        if new is None:
            continue
        landscape.write(db, gx, gy, None, None, new)
        done += 1
        if mode != 'hollows':
            notes.append(n)
    if not note:
        return {'cells': done, 'learnt_from': min(notes) if notes else 0}
    if not done:
        raise EditError('Nothing to shade here: %s' % ('no texture here has a tint the game uses nearby.' if mode == 'texture'
                                                      else 'no ground above the water here.' if mode == 'hollows'
                                                      else 'there are no seams between textures in this cell.'))
    db.sync_project()
    commit(db, 'Shaded the ground %s in %d cell%s' % ('by texture' if mode == 'texture' else 'at the seams', done, '' if done == 1 else 's'))
    return {'cells': done, 'learnt_from': min(notes) if notes else 0}


def mixes(grid):
    """Every point's {texture: weight}, for colours() to share between its modes."""
    return [_mix(grid, x, y) for y in range(N) for x in range(N)]


def colours(db, gx, gy, mode, strength, region, grid, col, H=None, around=None, mix=None):
    """(the cell's new colours as bytes, or None where shade() would leave the cell as it is; how many cells the
    tints were learnt from). grid: texture file per patch; col: its colours now (None: none yet); H, around: its
    heights and the heights round it, for 'hollows' (read from the land when not given); mix: mixes(grid)."""
    import landscape
    L = learn_near(db, gx, gy, region) if mode != 'hollows' else {'cells': 0}
    cur = bytearray(col) if col else bytearray(b'\xff' * (N * N * 3))
    new = bytearray(cur)
    if mode == 'hollows':
        import mapdata
        hs = hollow_shades(db, region or ((mapdata.cell_info(db, '#%d,%d' % (gx, gy)) or {}).get('region') or '').lower())
        if not hs:
            return None, 0
        if H is None:
            H = mapdata.land(db, gx, gy)['h']
        if around is None:
            around = landscape.around_of(db, gx, gy)
        def at(x, y):
            if 0 <= x < N and 0 <= y < N:
                return H[y * N + x]
            v = around(x, y)
            return H[min(N - 1, max(0, y)) * N + min(N - 1, max(0, x))] if v is None else v
        for y in range(N):
            for x in range(N):
                z = H[y * N + x]
                if z < 0:
                    continue
                lap = (at(x - 1, y) + at(x + 1, y) + at(x, y - 1) + at(x, y + 1) - 4 * z) / 4.0
                b = max(-4, min(4, lap / 32.0))
                lo = math.floor(b)
                f0, f1 = hs.get(lo, 1.0), hs.get(lo + 1, 1.0)
                k = f0 + (f1 - f0) * (b - lo)
                o = (y * N + x) * 3
                for i in range(3):
                    v = cur[o + i] + (cur[o + i] * k - cur[o + i]) * strength
                    new[o + i] = max(0, min(255, int(round(v))))
        return (bytes(new) if new != cur else None), 0
    for y in range(N):
        for x in range(N):
            m = mix[y * N + x] if mix else _mix(grid, x, y)
            o = (y * N + x) * 3
            if mode == 'texture':
                known = [(t, wt) for t, wt in m.items() if t in L['tint']]
                tw = sum(wt for _t, wt in known)
                if tw < 0.5:
                    continue
                want = [sum(L['tint'][t][i] * wt for t, wt in known) / tw for i in range(3)]
            else:
                if len(m) < 2:
                    continue
                top = sorted(m.items(), key=lambda kv: -kv[1])[:2]
                (a, wa), (b, wb) = sorted(top)
                if min(wa, wb) < 0.15:
                    continue
                k = L['seam'].get((a, b)) or L['seam_any']
                # (strongest where the two are half and half, fading out as one takes over)
                f = min(1.0, min(wa, wb) / 0.5)
                want = [cur[o + i] * (1 + (k[i] - 1) * f) for i in range(3)]
            for i in range(3):
                v = cur[o + i] + (want[i] - cur[o + i]) * strength
                new[o + i] = max(0, min(255, int(round(v))))
    if new == cur and col is not None:
        return None, L['cells']
    return bytes(new), L['cells']


def summary(db, gx, gy):
    """What was learnt near a cell, for the panel: the textures here with their tints, and the seams here."""
    import landscape
    w = landscape._winner(db, gx, gy)
    if w is None:
        return {'exists': False}
    grid, _col = _land_of(db, w)
    L = learn(db, gx, gy)
    here = sorted(set(grid))
    seams = sorted({tuple(sorted((grid[i], grid[j]))) for i in range(256) for j in (i + 1, i + 16)
                    if j < 256 and (j != i + 1 or i % 16 != 15) and grid[i] != grid[j]})
    return {'exists': True, 'cells': L['cells'],
            'tints': [{'tex': t, 'rgb': [round(v) for v in L['tint'][t]]} for t in here if t in L['tint']],
            'seams': [{'a': a, 'b': b, 'k': [round(v, 3) for v in (L['seam'].get((a, b)) or L['seam_any'])], 'learnt': (a, b) in L['seam']}
                      for a, b in seams]}
