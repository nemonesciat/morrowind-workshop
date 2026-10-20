"""How gappy the game's own, hand-made places are, style by style: the gap finder (fixit.scan) run over
a few of the game's interiors built from each style's room pieces, and the see-through holes (and
the other kinds of issue) it finds there per floor piece. A Hlaalu or Velothi place of the game's own
has a see-through spot at many of its joins; an Imperial small one hardly any. Find gaps shows, and
the builder's closing rounds fix, only what is worse than the game's own places of the style; the
whole list stays behind "show everything".

The survey of a style runs in the background the first time it's asked for (half a minute to a few
minutes: the see-through check is slow) and is kept in the Workshop's cache folder."""
import json
import os
import threading
from collections import Counter

import kits

_cache = {}
_threads = {}
PLACES = 8               # the game's places looked at per style
MIN_TILES = 8            # a place must be built from at least this many of the style's pieces
MAX_TILES = 80           # (bigger ones take minutes to look through)
KINDS = ('hole', 'gap', 'doorway', 'post', 'ceiling')


def _disk(db, prefix):
    import hashlib
    import project
    sig = hashlib.md5('|'.join(sorted(p['name'].lower() for p in (db.plugins or []))).encode('utf-8')).hexdigest()[:12]
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'gapsurvey_%s_%s_v1.json' % (sig, prefix.replace('/', '_')))


def cells_for(db, prefix, limit=PLACES):
    """The game's own places built from this style's pieces, with MIN_TILES..MAX_TILES of them: a spread
    over the list, up to limit."""
    import stairsurvey
    kp = kits.kit_pieces(db, prefix)
    cells = set()
    for p in (kp or {}).get('pieces', [])[:8]:
        cells |= {db.recs[ci][7] for ci in db.used_in.get(p['id'].lower(), ()) if db.recs[ci][0] == 'CELL'
                  and kits.game_made(db, db.recs[ci][7]) and not db.recs[ci][7].startswith('#')}
    cands = sorted(cells)
    cands = cands[::max(1, len(cands) // (limit * 6))]           # (a spread over the whole list, not just the As)
    good = []
    for ck in cands:
        try:
            tiles, _other = stairsurvey._cell_pieces(db, ck)
        except Exception:
            continue
        n = sum(1 for t in tiles if t['kit'] == prefix)
        if MIN_TILES <= n <= MAX_TILES:
            good.append(ck)
    if len(good) > limit:
        good = good[::max(1, len(good) // limit)][:limit]
    return good


def survey(db, prefix, limit=PLACES):
    """{'places': n, 'cells': [{'key', 'tiles', 'hole', 'gap', ...}], 'per_tile': {kind: the typical (median)
    rate per floor piece}, 'mean': {kind: mean rate}} for the game's places in this style (kept on disk)."""
    key = (prefix, limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db, prefix)
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache[key] = (db.recs, saved)
        return saved
    except Exception:
        pass
    import fixit
    rows = []
    for ck in cells_for(db, prefix, limit):
        try:
            res = fixit.scan(db, ck, everything=True)
        except Exception:
            continue
        if not res.get('tiles'):
            continue
        c = Counter(i['kind'] for i in res['issues'])
        rows.append(dict({'key': ck, 'tiles': res['tiles']}, **{k: c.get(k, 0) for k in KINDS}))
    med = lambda v: sorted(v)[len(v) // 2] if v else 0.0
    out = {'places': len(rows), 'cells': rows,
           'per_tile': {k: round(med([r[k] / float(r['tiles']) for r in rows]), 3) for k in KINDS},
           'mean': {k: round(sum(r[k] for r in rows) / float(sum(r['tiles'] for r in rows) or 1), 3) for k in KINDS}}
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def ready(db, prefix, limit=PLACES):
    """The style's survey when it's to hand (in memory or on disk); otherwise None, with the survey
    started in the background so it's there next time."""
    if not prefix:
        return None
    key = (prefix, limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db, prefix)):
            return survey(db, prefix, limit)
    except Exception:
        return None
    t = _threads.get(prefix)
    if t is None or not t.is_alive():
        t = threading.Thread(target=lambda: survey(db, prefix, limit), daemon=True)
        _threads[prefix] = t
        t.start()
    return None


def typical(db, prefix):
    """The game's typical see-through holes per floor piece in this style (and the other kinds), or None
    until surveyed: {'per_tile': {...}, 'places': n}."""
    s = ready(db, prefix)
    if not s or not s['places']:
        return None
    return {'per_tile': s['per_tile'], 'places': s['places']}


def summary(db, styles=None):
    """For people: each surveyed style's rates, place by place."""
    out = {}
    for pre in (styles or list(kits.kits(db))):
        s = ready(db, pre)
        if s:
            out[pre] = {'style': kits.friendly(pre), 'places': s['places'], 'per_tile': s['per_tile'], 'mean': s['mean'],
                        'cells': s['cells']}
        else:
            out[pre] = {'style': kits.friendly(pre), 'ready': False}
    return out
