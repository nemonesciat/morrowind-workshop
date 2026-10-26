"""Dressing a land plan (packaging/terrain-shaping-proposal.md, stage 4): the ground textures the game lays at each
slope, height and distance from the water in the region (landsurvey 'textures3', v2), with about the game's own
number of textures a cell, then the region's shading (landshade: its tints, its seams, and its darker hollows).

The texture of a 512-unit patch is picked among the region's top textures for its band, by their shares, with
broad noise so neighbouring patches agree (the game's ground comes in patches, not salt and pepper); variety 0
always takes the commonest, 1 follows the shares. A last tidy-up gives a lone patch its neighbours' texture.
Roads and the default texture are never picked: a road is laid on purpose, not by slope."""
import math
from collections import Counter, deque

import landrange
import landsurvey


def _tables(db, region):
    """{(slope, height, shore): [(LTEX id, texture file, share)]} and the same without shore, for the region."""
    s = landsurvey.ready(db)
    R = (s or {}).get('regions', {}).get(region) if s else None
    if not R:
        return {}, {}
    by_file = {}
    import landscape
    for (_f, _i), (rid, tex) in landscape._ltex_all(db).items():
        by_file.setdefault(tex.lower(), rid)

    def keep(top):
        out = [(by_file[n], n, sh) for n, sh in top if n != 'default' and 'road' not in n and n in by_file]
        tot = sum(sh for _r, _n, sh in out)
        return [(r, n, sh / tot) for r, n, sh in out] if tot else []
    t3 = {tuple(int(v) for v in k.split(',')): keep(v['top']) for k, v in (R.get('textures3') or {}).items() if v['n'] >= 12}
    t2 = {tuple(int(v) for v in k.split(',')): keep(v['top']) for k, v in (R.get('textures') or {}).items() if v['n'] >= 12}
    return {k: v for k, v in t3.items() if v}, {k: v for k, v in t2.items() if v}


def patch_stats(F, gx, gy):
    """[(slope degrees, height, wet)] for the cell's 256 patches from the working grid (any spacing 64 divides)."""
    G = F.G
    per = 64 // F.s                    # (grid points a cell)
    pp = max(1, per // 16)             # (grid points a patch)
    ox, oy = (gx - G.x0) * per, (gy - G.y0) * per
    out = []
    for py in range(16):
        for px in range(16):
            x0, y0 = ox + (px * per) // 16, oy + (py * per) // 16
            pts = [F.z[(y0 + j) * F.w + x0 + i] for j in range(pp + 1) for i in range(pp + 1)]
            a, b = F.z[y0 * F.w + x0], F.z[y0 * F.w + x0 + pp]
            c, d = F.z[(y0 + pp) * F.w + x0], F.z[(y0 + pp) * F.w + x0 + pp]
            run = pp * F.step
            gxs, gys = ((b - a) + (d - c)) / (2 * run), ((c - a) + (d - b)) / (2 * run)
            z = sum(pts) / len(pts)
            out.append((math.degrees(math.atan(math.hypot(gxs, gys))), z, z < 0))
    return out


def _shore_dist(stats_by_cell):
    """{(gx, gy, px, py): patches to the nearest wet patch, at most the survey's reach}."""
    wet, dist = [], {}
    for (gx, gy), st in stats_by_cell.items():
        for k, (_s, _z, w) in enumerate(st):
            if w:
                wet.append((gx * 16 + k % 16, gy * 16 + k // 16))
    q = deque()
    for p in wet:
        dist[p] = 0
        q.append(p)
    reach = landsurvey.SHORE_BANDS[-1]
    while q:
        p = q.popleft()
        if dist[p] >= reach:
            continue
        for nb in ((p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)):
            if nb not in dist:
                dist[nb] = dist[p] + 1
                q.append(nb)
    return dist


def _pick(choices, u, variety):
    if variety <= 0 or len(choices) == 1:
        return choices[0]
    # (shares flattened towards the commonest as variety falls)
    ws = [sh ** (1.0 / max(0.05, variety)) for _r, _n, sh in choices]
    tot = sum(ws)
    acc = 0.0
    for c, wt in zip(choices, ws):
        acc += wt / tot
        if u <= acc:
            return c
    return choices[-1]


VARIETIES = (0.25, 0.5, 0.8, 1.0, 1.4, 2.0, 3.0)


def textures(db, F, keys, regions, variety=-1.0, seed=1, also_grid=None):
    """{(gx, gy): [256 LTEX ids]} and {(gx, gy): [256 texture files]} for the cells, from the working grid. variety
    below 0: the one that gives the region's own number of textures a cell (landsurvey 'tex_per_cell', median)."""
    if variety >= 0:
        return _textures(db, F, keys, regions, variety, seed, also_grid)
    s = landsurvey.ready(db)
    want = []
    for r in set(regions.values()):
        m = (((s or {}).get('regions') or {}).get(r) or {}).get('tex_per_cell', {}).get('50')
        if m:
            want.append(m)
    if not want:
        return _textures(db, F, keys, regions, 1.0, seed, also_grid)
    target = sum(want) / len(want)
    best = None
    pre = _prepare(F, keys, also_grid)              # (the patches' slopes and shore distances, once for every try)
    for v in VARIETIES:
        ids, files = _textures(db, F, keys, regions, v, seed, also_grid, cap=int(round(target)), pre=pre)
        counts = sorted(len(set(t)) for t in ids.values())
        med = counts[len(counts) // 2] if counts else 0
        score = abs(med - target)
        if best is None or score < best[0]:
            best = (score, ids, files)
        if med >= target:
            break                       # (more variety only adds textures from here)
    return best[1], best[2]


def _prepare(F, keys, also_grid=None):
    stats = {k: patch_stats(F, *k) for k in keys}
    # (the cells round the plan count for the water too: a coast at the edge of the marked cells)
    if also_grid:
        for k in also_grid:
            if k not in stats:
                stats[k] = patch_stats(F, *k)
    return stats, _shore_dist(stats), {}


def _textures(db, F, keys, regions, variety=1.0, seed=1, also_grid=None, cap=None, pre=None):
    stats, dist, memo = pre or _prepare(F, keys, also_grid)
    reach = landsurvey.SHORE_BANDS[-1]
    tabs = {}
    ids, files = {}, {}
    for gx, gy in keys:
        r = regions.get((gx, gy), '')
        if r not in tabs:
            tabs[r] = _tables(db, r)
        t3, t2 = tabs[r]
        if not t3 and not t2:
            continue
        grid, options = [], []
        for k, (sl, z, _w) in enumerate(stats[(gx, gy)]):
            px, py = k % 16, k // 16
            sb = landsurvey._band(sl, landsurvey.SLOPES)
            hb = landsurvey._band(z, landsurvey.HEIGHTS)
            shb = landsurvey.shore_band(dist.get((gx * 16 + px, gy * 16 + py), reach))
            ch = t3.get((sb, hb, shb)) or t2.get((sb, hb))
            if not ch:
                near = sorted((abs(s - sb) + abs(b - hb) * 2, (s, b)) for (s, b) in t2)
                ch = t2[near[0][1]] if near else None
            if not ch:
                grid.append(None)
                options.append([])
                continue
            # (the patch's own draw, the same for every variety tried: worked out once)
            ukey = (gx, gy, k, seed, sb, hb)
            u = memo.get(ukey)
            if u is None:
                wx, wy = (gx * 16 + px + 0.5) * 512, (gy * 16 + py + 0.5) * 512
                u = memo[ukey] = min(0.999, max(0.0, 0.5 + 0.5 * landrange.noise(wx, wy, seed + 101 + sb * 7 + hb * 13, 1.0) / 1.6))
            grid.append(_pick(ch, u, variety))
            options.append(ch)
        # (no more textures in the cell than the region's own cells have: a rare one gives way to one the cell
        # already has that its band allows, or else to the cell's commonest)
        if cap:
            while True:
                cnt = Counter(c[0] for c in grid if c)
                if len(cnt) <= cap:
                    break
                rare = min(cnt, key=lambda t: cnt[t])
                keep = set(cnt) - {rare}
                common = max(keep, key=lambda t: cnt[t])
                for k, c in enumerate(grid):
                    if c and c[0] == rare:
                        alt = next((o for o in options[k] if o[0] in keep), None)
                        grid[k] = alt or next(g for g in grid if g and g[0] == common)
        # (a lone patch takes the texture most of its neighbours have)
        clean = list(grid)
        for k, c in enumerate(grid):
            if c is None:
                continue
            px, py = k % 16, k // 16
            nbs = [grid[(py + dy) * 16 + px + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                   if 0 <= px + dx < 16 and 0 <= py + dy < 16 and grid[(py + dy) * 16 + px + dx] is not None]
            if nbs and all(n[0] != c[0] for n in nbs):
                clean[k] = Counter(nbs).most_common(1)[0][0]
        if any(c is None for c in clean):
            fill = Counter(c for c in clean if c).most_common(1)
            clean = [c or (fill[0][0] if fill else None) for c in clean]
        if any(c is None for c in clean):
            continue
        ids[(gx, gy)] = [c[0] for c in clean]
        files[(gx, gy)] = [c[1] for c in clean]
    return ids, files
