"""Which models the game hangs, and how far below the ceiling (2026-10-25). hanggap.py does this for the
hanging lights; this reads every model the game places in its own interiors: the gap from its bottom to what
is under it (furniture included, so a cup on a table stands) and from its top to what is over it.

- A model the game hangs (clear of anything under it in most of its places: an anchor, a hanging planter, a
  lantern, a chain, a sign on its bracket, a rope) is never dropped by Settle or the physics toggle.
- A model the game hangs from a ceiling or a beam (its top close under a surface where it hangs) has its own
  gap there; Check this place reports one hung from nothing (the user's anchor in mid-air, "isn't attached to
  the ceiling"), with "Hang it from the beam above", at that gap.

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import os
import random
from collections import defaultdict

V = 'v1'
PLACES = 200
CLEAR = 24.0                 # (more than this under it: not standing on anything)
UNDER_CEIL = 64.0            # (its top within this of a surface over it: hung from it)
TYPES = ('STAT', 'ACTI', 'CONT', 'MISC', 'LIGH', 'BOOK', 'ALCH', 'INGR', 'APPA', 'WEAP', 'ARMO', 'CLOT')
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('hangsurvey_%s_%d_%s' % (taste.sig(db), PLACES, V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('which things the game hangs', lambda: survey(db), task=('hangsurvey', 'survey', []))
    return None


def survey(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache['survey'] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache['survey'] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def model_of(db, r):
    return (db.recs[r['ri']][5] or '').lower().replace('\\', '/') if r.get('ri') is not None else ''


def scene_of(db, m):
    """Everything placed (but people) as a Scene, each placed thing's triangles kept apart (of_ref)."""
    import seethrough
    sc = seethrough.Scene()
    sc.max_cells = 250000                  # (a cave's floor is made of big triangles: kept, or crates in mines hung over nothing)
    for r in m['refs']:
        if r['type'] in ('NPC_', 'CREA', 'LEVC', 'LEVI') or r.get('ri') is None:
            continue
        mdl = db.recs[r['ri']][5]
        if not mdl or 'marker' in mdl.lower():
            continue
        a = len(sc.tris)
        sc.add_model(seethrough.model_tris(db, mdl), r['p'], r.get('s') or 1.0)
        sc.of_ref[r['k']] = (a, len(sc.tris))
    return sc


def gaps(db, sc, r):
    """(gap under its bottom or None, gap over its top or None), its own triangles left out."""
    from shelfsurvey import box_turned
    b = r.get('b')
    if not b:
        return None, None
    tb = box_turned(b, r['p'][3], r['p'][4], r['p'][5], r.get('s') or 1.0)
    cx, cy = r['p'][0] + (tb[0] + tb[3]) / 2, r['p'][1] + (tb[1] + tb[4]) / 2
    bot, top = r['p'][2] + tb[2], r['p'][2] + tb[5]
    own = sc.of_ref.get(r['k'])
    skip = set(range(*own)) if own else set()
    # (from partway up it: the game sinks its urns, barrels and crates a little into a cave's uneven floor,
    # and a ray from the very bottom started under the floor, so they read as hung over nothing)
    lift = min(20.0, 0.4 * (top - bot))
    dn = sc._hits((cx, cy, bot + lift), (0.0, 0.0, -1.0), 800, set(skip), True, both=True)
    up = sc._hits((cx, cy, top - 0.5), (0.0, 0.0, 1.0), 800, set(skip), True, both=True)
    return (max(0.0, dn[0] - lift) if dn else None), (up[0] - 0.5 if up else None)


def _survey(db):
    import mapdata
    import planfrom
    places = list(planfrom.places(db))
    random.Random(5).shuffle(places)
    seen = defaultdict(list)
    n = 0
    # (every place read until PLACES; after that only places with a model seen fewer than WANT times, up to
    # MORE places in all: rarer pieces, the anchors and hanging planters, get their three)
    WANT, MORE = 3, PLACES * 3
    import background
    for i, p in enumerate(places):
        if n >= MORE:
            break
        # (for the Learning bar: places looked at, or places read of the most it reads, whichever is further)
        background.progress(max(i, n * len(places) // MORE), len(places), 'places')
        try:
            m = mapdata.cellmap(db, p['key'], original=True)
        except Exception:
            continue
        cand = [r for r in m['refs'] if r['type'] in TYPES and not r.get('arch') and r.get('b')]
        if n >= PLACES and not any(len(seen[model_of(db, r)]) < WANT for r in cand):
            continue
        try:
            sc = scene_of(db, m)
        except Exception:
            continue
        n += 1
        for r in cand:
            if n > PLACES and len(seen[model_of(db, r)]) >= 12:
                continue
            dn, up = gaps(db, sc, r)
            seen[model_of(db, r)].append((None if dn is None else round(dn, 1), None if up is None else round(up, 1)))
    out = {}
    for mdl, v in seen.items():
        if not mdl or len(v) < 3:
            continue
        hung = [(d, u) for d, u in v if d is None or d > CLEAR]
        ceil = sorted(u for d, u in hung if u is not None and u <= UNDER_CEIL)
        st = {'n': len(v), 'hung': round(len(hung) / float(len(v)), 3)}
        if ceil and len(ceil) >= 0.6 * len(hung) and len(hung) >= 0.6 * len(v):
            q = lambda f: ceil[int(f * (len(ceil) - 1))]
            st.update(ceil=round(len(ceil) / float(len(hung)), 3), p50=q(0.5), p90=q(0.9))
        out[mdl] = st
    return {'places': n, 'models': out}


# (a model the game never places in its own interiors, a mod's anchor on its rope: what its name says)
import re
HANG_NAME = re.compile(r'anchor|hanging|hang_|_hang|planterhang|chain|cage|bell(?!y)|chandelier')
# (hung from the beam itself: its loop at the beam, a few units of air at most)
NAME_GAP = (4.0, 16.0)


def _stats(db, model):
    S = ready(db)
    return S and S['models'].get((model or '').lower().replace('\\', '/'))


def hangs(db, model, rid=''):
    """The game hangs this model (clear of anything under it in six of its places in ten, or more); a model
    it never places, by its name."""
    st = _stats(db, model)
    if st:
        return st['hung'] >= 0.6
    return bool(HANG_NAME.search((model or '').lower() + ' ' + (rid or '').lower()))


def ceiling_gap(db, model, rid=''):
    """How far below a ceiling or beam the game hangs this model: (its median gap, its p90), or None when the
    game doesn't hang it from one (by its name, a short gap, for a model the game never places)."""
    st = _stats(db, model)
    if st:
        # (hung from a ceiling in three of its hung places in four, or more)
        return (st['p50'], st['p90']) if 'p50' in st and st.get('ceil', 0) >= 0.75 else None
    return NAME_GAP if HANG_NAME.search((model or '').lower() + ' ' + (rid or '').lower()) else None
