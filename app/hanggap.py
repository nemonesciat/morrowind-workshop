"""How far below the ceiling the game hangs each of its hanging lights (2026-10-23): the gap from the top of
a light's box to the building's surface straight above it, read in the game-made interiors. A chandelier's
box ends at its hook, and the game hangs it there (98 chandeliers in 150 places: half within 9 of the
ceiling, three in four within 16); a lantern's box ends below its loop or its rope (half within 34, one in
ten 161 or more, from beams). Auto-furnish hung every light at one height off the floor (the game's 168),
which left the chain of a chandelier short of a high ceiling (the user's "lots of chandeliers fail to come
up to the ceiling", Big Ass Fail); it now hangs each at its own model's gap, and Check this place reports a
hanging light hung well below where the game hangs that model.

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import os
import random
import re
from collections import defaultdict

V = 'v1'
PLACES = 400                # (game places with a hanging light read, at most)
HANG = re.compile(r'chandelier|candelabra|lantern|hanging')
# (until the survey is to hand: the game's medians by kind, and the gap beyond which a light hangs short)
KIND_GAP = {'chandelier': 9, 'candelabra': 9, 'lantern': 34, 'hanging': 34}
_cache = {}
_thread = {}


def kind(low):
    m = HANG.search(low)
    return m.group(0) if m else None


def _disk(db):
    import taste
    return taste.cache_file('hanggap_%s_%d_%s' % (taste.sig(db), PLACES, V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('how high the game hangs its lights', lambda: survey(db), task=('hanggap', 'survey', []))
    return None


def survey(db):
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def light_gaps(db, m, sc=None):
    """The hanging lights of a cell map that hang (well clear of anything under them): [(ref, gap to the
    surface above or None, height of the bottom over what is below)]."""
    import mapdata
    import seethrough
    lights = [r for r in m['refs'] if r['type'] == 'LIGH' and HANG.search(r['id'].lower()) and r.get('ri') is not None]
    if not lights:
        return []
    sc = sc or seethrough.place_scene(db, m)
    out = []
    for r in lights:
        b = mapdata.object_bounds(db, r['ri'])
        if not b:
            continue
        s = r.get('s') or 1.0
        top, bot = r['p'][2] + b[5] * s, r['p'][2] + b[2] * s
        down = sc.nearest((r['p'][0], r['p'][1], bot - 2), (0.0, 0.0, -1.0), 600)
        if down is None or down[0] < 60:
            continue                     # (standing on a table or the floor, or over nothing)
        up = sc.nearest((r['p'][0], r['p'][1], top + 2), (0.0, 0.0, 1.0), 800)
        out.append((r, (up[0] + 2) if up is not None else None, down[0] + 2))
    return out


def _survey(db):
    import mapdata
    import planfrom
    places = list(planfrom.places(db))
    random.Random(3).shuffle(places)
    by_id, by_kind = defaultdict(list), defaultdict(list)
    n = 0
    for p in places:
        try:
            got = light_gaps(db, mapdata.cellmap(db, p['key']))
        except Exception:
            continue
        got = [g for g in got if g[1] is not None]
        if not got:
            continue
        n += 1
        for r, gap, _h in got:
            by_id[r['id'].lower()].append(round(gap, 1))
            by_kind[kind(r['id'].lower())].append(round(gap, 1))
        if n >= PLACES:
            break

    def stats(v):
        v = sorted(v)
        q = lambda f: v[int(f * (len(v) - 1))]
        return {'n': len(v), 'p50': q(0.5), 'p75': q(0.75), 'p90': q(0.9)}
    return {'places': n, 'ids': {k: stats(v) for k, v in by_id.items() if len(v) >= 3},
            'kinds': {k: stats(v) for k, v in by_kind.items() if v}}


def usual_gap(db, rid):
    """How far below the ceiling the game hangs this light: its own median where the game hangs it three
    times or more, else its kind's; never more than 40 (a lantern the game hangs from a beam lower down is
    hung by its rope here, from the ceiling)."""
    low = (rid or '').lower()
    S = ready(db) or {}
    st = (S.get('ids') or {}).get(low) or (S.get('kinds') or {}).get(kind(low) or '')
    g = st['p50'] if st else KIND_GAP.get(kind(low) or '', 9)
    return max(0.0, min(40.0, g))


def short_by(db, rid, gap):
    """How much further below the ceiling this light hangs than the game ever hangs it (beyond its p90, or
    its kind's p75 plus 24 for a model the game hangs fewer than three times), or 0."""
    low = (rid or '').lower()
    S = ready(db) or {}
    st = (S.get('ids') or {}).get(low)
    if st:
        limit = max(st['p90'], st['p50'] + 24)
    else:
        kst = (S.get('kinds') or {}).get(kind(low) or '')
        limit = (kst['p75'] if kst else KIND_GAP.get(kind(low) or '', 9) * 2) + 24
    return max(0.0, gap - limit)
