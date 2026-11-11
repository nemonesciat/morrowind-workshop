"""Clear what stands in the cells before the land is made (2026-11-09).

Tamriel.esm fills the continent's unbuilt towns and wilds with low-detail stand-ins (DLT_Buildings_*, DLT_Trees_*,
DLT_Rocks_*) so the far land isn't empty. The user, shaping there: "It should remove them, however, I want it to at
least replace the trees and rocks that were there to give the empty continent the appearance of life"; and later "It
might not always be desireable to clear all the objects in a selected region of cells. But where one chooses to
automatically shape and dress the land, perhaps this should be an option?"

The Land stage's "Clear what's there first", three scopes:
  'standins'  Tamriel.esm's stand-ins only; a real tree or rock of the region (or of the region its plants come
              from, landregion.plant_region) set where each stand-in tree or rock stood, sized like it.
  'nature'    any other mod's trees, rocks and plants, and the stand-ins; buildings, ruins and doors stay.
  'all'       every object of another mod.
Never the mod's own objects, never kept land (the page sends only the cells being made). Other mods' objects are
marked removed in the mod, so turning the mod off brings them back. No commit: the land press's own step takes it.
"""
import math
import random
import re
from collections import Counter

import mapdata

STANDIN = re.compile(r'^dlt_', re.I)
SCOPES = ('standins', 'nature', 'all')
SAMPLE = 60                 # (the region's game cells read for its trees and rocks)
MIN_KIND = 6                # (fewer of a kind there: the plant region's)
_mem = {}


def _size(r):
    b = r.get('b')
    if not b:
        return 0.0
    return max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0)


def _what(low):
    import cliffrocks
    import landdecor
    if STANDIN.search(low):
        return 'tree' if 'tree' in low else 'rock' if 'rock' in low else 'standin'
    if cliffrocks.is_rock(low):
        return 'rock'
    k = landdecor.kind_of(low)
    return 'tree' if k == 'trees' else 'plant' if k in ('plants', 'grass', 'logs') else None


def takes(r, scope):
    """Does the scope clear this ref (a cellmap ref)?"""
    if r.get('mine') or r.get('new'):
        return False
    low = r['id'].lower()
    if scope == 'all':
        return True
    if STANDIN.search(low):
        return True
    if scope == 'nature':
        return _what(low) in ('tree', 'rock', 'plant') and r['type'] in ('STAT', 'ACTI', 'CONT', 'MISC')
    return False


def _keys(cells):
    return sorted({tuple(c) if isinstance(c, (tuple, list)) else tuple(int(v) for v in str(c).lstrip('#').split(',')) for c in cells or ()})


def count(db, cells):
    """{'standins', 'nature', 'all'}: how many objects each scope would clear in the cells."""
    out = Counter()
    for gx, gy in _keys(cells):
        for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ():
            for s in SCOPES:
                if takes(r, s):
                    out[s] += 1
    return {s: out[s] for s in SCOPES}


def palette(db, region):
    """The real trees and rocks of a region's game cells: {'tree': [(id, size, sink)], 'rock': [...]}, no stand-ins;
    a kind with too few borrowed from the region its plants come from."""
    key = (id(db.recs), region)
    if key in _mem:
        return _mem[key]
    import landsurvey
    S = landsurvey.ready(db) or {}

    def read(reg):
        got = {'tree': [], 'rock': [], 'n': 0}
        cells = [k for k, c in (S.get('cells') or {}).items() if (c.get('region') or '') == reg and c.get('k') in ('land', 'shore')]
        random.Random(reg).shuffle(cells)
        got['n'] = len(cells[:SAMPLE])
        for k in cells[:SAMPLE]:
            for r in mapdata.cellmap(db, '#' + k, original=True).get('refs') or ():
                low = r['id'].lower()
                w = _what(low)
                if w not in got or STANDIN.search(low) or r['type'] not in ('STAT', 'ACTI'):
                    continue
                g = mapdata.terrain_z(db, r['p'][0], r['p'][1])
                got[w].append((r['id'], _size(r) or 128.0, (r['p'][2] - g) if g is not None else 0.0))
        return got
    out = read(region)
    per = {w: len(out[w]) / float(out['n'] or 1) for w in ('tree', 'rock')}
    # (Tamriel.esm's regions hold only stand-ins: the nearest hand-made region in weather and on the map lends its
    # trees and rocks, as landregion.plant_region picks the plants' region)
    for alt in _nearest(db, region):
        if min(len(out['tree']), len(out['rock'])) >= MIN_KIND:
            break
        more = read(alt)
        try:
            import landregion
            more['rock'] = [t for t in more['rock'] if landregion.home_rock_ok(t[0], region)]
        except Exception:
            pass
        for w in ('tree', 'rock'):
            if len(out[w]) < MIN_KIND and len(more[w]) >= MIN_KIND:
                out[w] = more[w]
                per[w] = len(more[w]) / float(more['n'] or 1)
    # (how many a cell the region they came from has: the stand-ins' clumps spread to no more than that)
    out['per'] = per
    _mem[key] = out
    return out


def _nearest(db, region, n=8):
    """Hand-made regions nearest a region in weather and on the map, the nearest first."""
    try:
        import landregion
        mine, C = landregion._weather(db, region), landregion._centres(db)
        here = C.get(region)
        ranked = []
        for r in set(landregion.handmade(db)) | set(landregion.clad_regions(db)):
            w = landregion._weather(db, r)
            if r == region or mine is None or w is None or not C.get(r):
                continue
            d = sum(abs(a - b) for a, b in zip(mine, w))
            if here:
                d += math.hypot(here[0] - C[r][0], here[1] - C[r][1]) / landregion.ROCK_FAR
            ranked.append((d, r))
        return [r for _d, r in sorted(ranked)[:n]]
    except Exception as e:
        print('stand-ins, nearest regions:', e)
        return []


def clear(db, cells, scope='standins', seed=1, say=None, rocks=True, trees_k=1.0):
    """The scope's objects in the cells marked removed; for stand-in trees and rocks, the region's own set in their
    place. {'removed', 'replaced'}; no commit."""
    import editing
    import landrange
    from project import set_ref_pos, zs
    if scope not in SCOPES:
        return {'removed': 0, 'replaced': 0}
    rng = random.Random(seed * 13 + 5)
    mine = db.project.plugin.lower()
    removed = replaced = 0
    keys = _keys(cells)
    for n_, (gx, gy) in enumerate(keys):
        if say and n_ % 8 == 0:
            say(n_ / float(len(keys) or 1))      # (the bar moves through a big clear: it sat at 1% for minutes)
        key = '#%d,%d' % (gx, gy)
        refs = [r for r in mapdata.cellmap(db, key).get('refs') or () if takes(r, scope)]
        if not refs:
            continue
        c, raw = editing._cell(db, key)
        region = landrange._region_of(db, gx, gy) or ''
        P = palette(db, region) if any(STANDIN.search(r['id']) for r in refs) else {'tree': [], 'rock': [], 'per': {}}
        spots = {'tree': [], 'rock': []}
        for r in refs:
            ref = raw.get(r['k'])
            if not ref:
                continue
            editing._store(c, r['k'], ref['origin'], ref['idx'], ref['subs'], deleted=True)
            removed += 1
            w = _what(r['id'].lower())
            if not STANDIN.search(r['id']) or w not in ('tree', 'rock') or not P[w] or (w == 'rock' and not rocks):
                continue
            # (a stand-in tree is often a clump: as many of the region's trees as its spread holds, up to four)
            size = _size(r) or 256.0
            pool = P[w]
            if w == 'rock':
                pool = sorted(pool, key=lambda t: abs(t[1] - size))[:max(3, len(pool) // 5)]
            typical = sorted(t[1] for t in pool)[len(pool) // 2] or 256.0
            # (a tree for each stand-in tree at Trees 1, two at 2: clumps by the stand-in's size made 67 trees a cell, more
            # than Vorndgad Forest's 52; a Cover is for forest, lab 2026-11-09)
            n = 1 if w == 'rock' else int(trees_k) + (1 if rng.random() < trees_k - int(trees_k) else 0)
            for j in range(n):
                a, d = rng.uniform(0, 2 * math.pi), (size * 0.3 * math.sqrt(rng.random())) if n > 1 else 0.0
                spots[w].append((r['p'][0] + d * math.cos(a), r['p'][1] + d * math.sin(a), size, pool))
        # (no more a cell than the region they come from has: trees at its rate, rocks at half, the press setting the
        # slopes' own; lab 2026-11-09, 577 stand-ins became 57 trees a cell uncapped)
        for w, share in (('tree', 1.0), ('rock', 0.5)):
            got = spots[w]
            rng.shuffle(got)
            # (trees as many as the stand-ins stood for, times the Trees slider: they show where the map meant forest, the
            # user's "this region is supposed to have many trees"; rocks at half the lending region's rate)
            cap = len(got) if w == 'tree' else int(round((P.get('per') or {}).get(w, 0) * share))
            for x, y, size, pool in got[:cap]:
                tid, tsize, sink = rng.choice(pool)
                ri = db.resolve_id(tid)
                if ri is None:
                    continue
                g = mapdata.terrain_z(db, x, y)
                if g is None:
                    continue
                sc = max(0.5, min(2.0, size / tsize)) if w == 'rock' else rng.uniform(0.85, 1.15)
                rk = db.project.new_ref_key()
                ck = '#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0))
                try:
                    c2, _r2 = (c, None) if ck == key else editing._cell(db, ck)
                except editing.EditError:
                    continue
                editing._store(c2, rk, mine, int(rk.rsplit('|', 1)[1]),
                               set_ref_pos([('NAME', zs(db.recs[ri][1]))], (x, y, g + sink * sc, 0.0, 0.0, rng.uniform(0, 2 * math.pi)), sc))
                replaced += 1
    if removed:
        db.sync_project()
    return {'removed': removed, 'replaced': replaced}
