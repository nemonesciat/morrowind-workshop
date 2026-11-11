"""Cover: a drawn outline made forest, swamp, grassland, rocky or bare (2026-11-09).

The user, on the Tulmek Washes coast after a Make land: "this region is supposed to have many trees ... maybe there
should be a slider or some ability to choose density of what is laid down. Or is there some other way to draw an area
and make it forested, swampy, etc?"

A Cover shape in the Land stage, made with the land: inside its outline the press's own trees, plants and rocks are
taken out and the outline dressed (landdecor.dress_all, which dresses as a chosen region's land is dressed) as the
kind's region, picked among the hand-made regions nearest the cell's own in weather and on the map by what they hold:
  forest    the one with the most trees a cell;
  swamp     a marsh, swamp or bitter coast by name, the nearest; its water plants come with it (landdecor.WATER);
  grass     the one with the most plants a tree;
  rocky     the one with the most rocks a cell; rocks only;
  bare      nothing: other mods' and the press's trees, plants and rocks inside taken out.
density (0 to 3) multiplies what is laid. Each region's figures are read once from its game cells, and kept."""
import math
import random
import re

import mapdata

KINDS = ('forest', 'swamp', 'grass', 'rocky', 'bare')
# (what each kind lays at density 1, as Dress amounts: growth, rocks)
LAYS = {'forest': (2.0, 0.6), 'swamp': (1.6, 0.4), 'grass': (1.3, 0.4), 'rocky': (0.3, 2.0), 'bare': (0.0, 0.0)}
SWAMP = re.compile(r'marsh|swamp|bitter coast|mire|bayou|mangrove|fen\b|bog\b|floodland|wetland', re.I)
NEAREST = 10
SAMPLE = 40
_stats = {}
_pick = {}


def _in(pts, x, y):
    n, inside, j = len(pts), False, len(pts) - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def stats(db, region):
    """A region's trees, plants and rocks a cell of its game land: {'tree', 'plant', 'rock', 'cells'}."""
    key = (id(db.recs), region)
    if key in _stats:
        return _stats[key]
    import landsurvey
    import standins
    S = landsurvey.ready(db) or {}
    cells = [k for k, c in (S.get('cells') or {}).items() if (c.get('region') or '') == region and c.get('k') == 'land']
    random.Random(region).shuffle(cells)
    n = {'tree': 0, 'plant': 0, 'rock': 0}
    for k in cells[:SAMPLE]:
        for r in mapdata.cellmap(db, '#' + k, original=True).get('refs') or ():
            w = standins._what(r['id'].lower())
            if w in n and not standins.STANDIN.search(r['id']):
                n[w] += 1
    m = float(len(cells[:SAMPLE]) or 1)
    out = {w: v / m for w, v in n.items()}
    out['cells'] = len(cells[:SAMPLE])
    _stats[key] = out
    return out


def pick(db, region, kind):
    """The hand-made region whose land a kind of cover takes after, for land in this region ('' none)."""
    key = (id(db.recs), region, kind)
    if key in _pick:
        return _pick[key]
    import landregion
    import standins
    best = ''
    if kind == 'swamp':
        near = standins._nearest(db, region, 200)
        best = next((r for r in near if SWAMP.search(r)), '')
        if not best:
            best = next((r for r in landregion.handmade(db) if SWAMP.search(r)), '')
    elif kind in ('forest', 'grass', 'rocky'):
        near = ([region] if region in set(landregion.handmade(db)) else []) + standins._nearest(db, region, NEAREST)
        scored = []
        for r in near:
            s = stats(db, r)
            if s['cells'] < 5:
                continue
            v = s['tree'] if kind == 'forest' else s['plant'] / (s['tree'] + 3.0) if kind == 'grass' else s['rock']
            scored.append((v, r))
        best = max(scored)[1] if scored else ''
    _pick[key] = best
    return best


def lay(db, layers, keys, set_now, seed=1):
    """Each cover layer laid inside its outline: the press's own nature there (set_now: {cell: ref keys this press
    set}) taken out, then the outline dressed as its kind's region. -> {'covers', 'laid', 'cleared', 'like'}."""
    import editing
    import landdecor
    import landrange
    import standins
    out = {'covers': 0, 'laid': 0, 'cleared': 0, 'like': []}
    keyset = set(keys)
    for L in layers:
        if L.get('kind') != 'cover' or L.get('on') is False or len(L.get('pts') or ()) < 3:
            continue
        pts = [tuple(p) for p in L['pts']]
        p = L.get('p') or {}
        kind = p.get('cover') if p.get('cover') in KINDS else 'forest'
        dens = max(0.0, min(3.0, float(p.get('density', 1.0) or 0.0)))
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        cells = [(gx, gy) for gx in range(math.floor(min(xs) / 8192.0), math.floor(max(xs) / 8192.0) + 1)
                 for gy in range(math.floor(min(ys) / 8192.0), math.floor(max(ys) / 8192.0) + 1) if (gx, gy) in keyset]
        if not cells:
            continue
        # (inside the outline: the press's own trees, plants and rocks out, and for bare land the others' too)
        for gx, gy in cells:
            key = '#%d,%d' % (gx, gy)
            mine_now = set(set_now.get((gx, gy)) or ())
            c, raw = editing._cell(db, key)
            for r in mapdata.cellmap(db, key).get('refs') or ():
                if r.get('deleted') or not _in(pts, r['p'][0], r['p'][1]):
                    continue
                w = standins._what(r['id'].lower())
                if w not in ('tree', 'plant', 'rock'):
                    continue
                if r['k'] in mine_now:
                    c['refs'].pop(r['k'], None)
                    out['cleared'] += 1
                elif kind == 'bare' and standins.takes(r, 'nature'):
                    ref = raw.get(r['k'])
                    if ref:
                        editing._store(c, r['k'], ref['origin'], ref['idx'], ref['subs'], deleted=True)
                        out['cleared'] += 1
        db.sync_project()
        out['covers'] += 1
        g, rk = LAYS[kind]
        if kind == 'bare' or dens <= 0:
            continue
        reg = landrange._region_of(db, *cells[0]) or ''
        like = (L.get('like') or '').lower() or pick(db, reg, kind)      # (the shape's own Like, else the one picked)
        if like:
            out['like'].append(like)
        try:
            r = landdecor.dress_all(db, ['%d,%d' % k for k in cells], like, {'rocks': rk * dens, 'growth': g * dens},
                                    seed + out['covers'], [list(q) for q in pts], '')
            out['laid'] += (r.get('rocks') or 0) + (r.get('growth') or 0)
        except editing.EditError as e:
            print('cover:', e)
    return out
