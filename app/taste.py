"""The taste set: the game's own interiors the user has marked as exemplary ("Use as an example" on the
World map's Place panel), kept as a list of cell keys in the Workshop settings. Every survey that
averages over the game's places (what a room of each kind holds, how dense it is, which set pieces it
is composed of, how walls and lights go, where furniture stands, the catalogue rules, how well off a
home is) weights an exemplary place WEIGHT times a plain one, so Auto-furnish leans towards the places
the user likes best rather than the game's average. Only places the game (or another mod) made can be
examples: the mod's own builds must never teach it.

Each survey's cache file carries a stamp of the taste set in its name, so a change to the set makes
the surveys run again in the background (a few minutes each); until they are done, the newest earlier
survey stands in (stale()), so Auto-furnish never falls back to the hand-written recipes meanwhile."""
import glob
import hashlib
import json
import os
import threading

import project

WEIGHT = 5                  # how many plain places one exemplary place counts for
KEY = 'exemplary'           # the settings entry: a list of cell keys
_lock = threading.Lock()
_snap = {'mtime': None, 'places': []}


def places():
    """The exemplary places' cell keys (lower case), in the order they were marked."""
    try:
        mt = os.path.getmtime(project.SETTINGS_FILE)
    except OSError:
        mt = None
    if _snap['mtime'] != mt:
        s = project.load_settings()
        _snap['places'] = [str(k).lower() for k in (s.get(KEY) or []) if k]
        _snap['mtime'] = mt
    return list(_snap['places'])


def is_marked(cell_key):
    return (cell_key or '').lower() in set(places())


def mark(cell_key, on=True):
    """Add a place to the taste set (or take it out); returns the list after."""
    key = (cell_key or '').lower()
    with _lock:
        s = project.load_settings()
        lst = [str(k).lower() for k in (s.get(KEY) or []) if k]
        if on and key not in lst:
            lst.append(key)
        if not on:
            lst = [k for k in lst if k != key]
        s[KEY] = lst
        project.save_settings(s)
        _snap['mtime'] = None
    return lst


def weight(cell_key):
    """How many plain places this one counts for in a survey: WEIGHT for an exemplary place, else 1."""
    return WEIGHT if (cell_key or '').lower() in set(places()) else 1


def order(cells):
    """The game's places in survey order: the exemplary ones first (so a survey that stops after its
    first few hundred never misses them), each WEIGHT times over, then the rest as they came."""
    ex = set(places())
    first = [c for c in cells if c in ex]
    out = []
    for c in first:
        out += [c] * WEIGHT
    return out + [c for c in cells if c not in ex]


def spread(cells, limit, per=4.5):
    """A spread of the game's places over the whole sorted list rather than its first names (the first
    few hundred interiors by name are nearly all Tamriel Rebuilt's, and Bethesda's Ald-ruhn, Balmora and
    Vivec would never be seen): every k-th cell, k set so that about `per` × limit candidates are tried
    (about one place in four is a kit-built interior with rooms). The exemplary places come first, each
    WEIGHT times over, whatever the stride."""
    step = max(1.0, len(cells) / float(limit * per))
    picked = [cells[int(n * step)] for n in range(int(len(cells) / step))]
    return order(picked + [c for c in set(places()) & set(cells) if c not in set(picked)])


def stamp():
    """A short mark of the taste set for cache file names: '' when no place is marked."""
    p = sorted(set(places()))
    if not p:
        return ''
    return '_t' + hashlib.md5('|'.join(p).encode('utf-8')).hexdigest()[:6]


def sig(db):
    """The load order's signature, as every survey's cache file name carries it."""
    return hashlib.md5('|'.join(sorted(p['name'].lower() for p in (db.plugins or []))).encode('utf-8')).hexdigest()[:12]


def cache_file(name):
    """The cache file for a survey: cache/<name><taste stamp>.json (name like 'roomsurvey_<sig>_400_v5')."""
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name + stamp() + '.json')


def stale_path(path):
    """The newest earlier survey of the same kind (made with another taste set, or none), to stand in
    while the one for the current set runs; None when there is none."""
    base = path[:-5] if path.endswith('.json') else path
    i = base.rfind('_t')
    if i > 0 and len(base) - i == 8 and all(c in '0123456789abcdef' for c in base[i + 2:]):
        base = base[:i]
    cands = []
    for p in glob.glob(glob.escape(base) + '*.json'):
        if os.path.abspath(p) == os.path.abspath(path):
            continue
        tail = p[len(base):-5]
        if tail and not (tail.startswith('_t') and len(tail) == 8):
            continue              # (another limit or version: not the same survey)
        try:
            cands.append((os.path.getmtime(p), p))
        except OSError:
            pass
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0][1]


def stale(cache, key, recs, path, load=None):
    """A stand-in survey while the current taste set's runs: the newest earlier file of the kind, loaded
    once (with load(path), or json.load) and kept in the module's cache under ('stale', key); None when
    there is none."""
    sk = ('stale', key)
    if sk in cache and cache[sk][0] is recs:
        return cache[sk][1]
    p = stale_path(path)
    out = None
    if p:
        try:
            if load is not None:
                out = load(p)
            else:
                with open(p, encoding='utf-8') as f:
                    out = json.load(f)
        except Exception:
            out = None
    cache[sk] = (recs, out)
    return out


def listing(db):
    """The taste set for people: [{'key', 'name', 'style', 'rooms', 'game_made'}] in the order marked."""
    import kits
    import mapdata
    out = []
    for k in places():
        info = mapdata.cell_info(db, k)
        row = {'key': k, 'name': (info or {}).get('name') or k, 'exists': bool(info), 'game_made': bool(info) and kits.game_made(db, k)}
        if info:
            try:
                m = mapdata.cellmap(db, k)
                from collections import Counter
                st = Counter(kits.kit_prefix(r['id']) for r in m.get('refs', []) if r.get('arch') and kits.kit_prefix(r['id'])).most_common(1)
                row['style'] = st[0][0] if st else ''
            except Exception:
                row['style'] = ''
        out.append(row)
    return out
