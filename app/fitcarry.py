"""What a wall fitting carries (2026-11-09): the weapons on a weapon rack, the lantern on a lantern hook, the light in a
sconce, the cloth or fish on a hook, read in the game's own places in the fitting's own frame, and laid on the made
places' bare ones.

The user, 2026-11-09: "do not overlook the empty racks, sconces, hooks ... I see a lot of 'weapon racks' on walls, that
could maybe have a common weapon on them ... or a bare hook". 265 of the mod's 297 weapon racks stood empty, where 41 of
the game's 131 do; its lantern hooks had no lantern. Each fitting model's own loads are learnt (the game's pieces on it,
where they lie on it and how they are turned), pooled by kind where a model has few; a bare fitting in a made place
gets one of them, a weapon rack only cheap weapons (a guard's or a hunter's, not a hero's).

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

import mapdata

V = 'v1'
FIT = re.compile(r'weaponrack|weapon_rack|_rack_0|furnp_rack|sconce|hook')
CARRY_TAGS = ('WEAP', 'ARMO', 'LIGH', 'MISC', 'INGR', 'CLOT', 'ALCH', 'APPA', 'BOOK')
NOT_LOAD = re.compile(r'^gold_|key|soulgem|^bk_|scroll|_unique|propylon|^t_.*_uni_|daedric|ebony|glass_|dwemer|dwarven|adamant|orcish'
                      r'|_artifact|^light_fire|smoke')
WEAPON_VALUE = 60           # (a made home's rack holds cheap weapons: iron, chitin, a hunter's bow)
LOAD_VALUE = 40
# (how often a bare one is loaded: the user wants no empty racks, sconces or lantern hooks; a plain hook may stay bare as
# a few of the game's do)
FILL = {'rack': 0.95, 'sconce': 1.0, 'lantern_hook': 1.0, 'hook': 0.85}
MIN_LOADS = 3               # (a model with fewer loads learnt borrows its kind's)
_cache = {}
_thread = {}


def kind(low):
    if 'sconce' in low:
        return 'sconce'
    if 'hook' in low:
        return 'lantern_hook' if 'lantern' in low or 'lamp' in low else 'hook'
    if 'winerack' in low or 'wine_rack' in low:
        return None
    return 'rack'


def _disk(db):
    import taste
    return taste.cache_file('fitcarry_%s_%s' % (taste.sig(db), V))


def ready(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('what the game hangs on its racks and hooks', lambda: survey(db), task=('fitcarry', 'survey', []))
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
        path = None
    out = _survey(db)
    _cache['survey'] = (db.recs, out)
    if path:
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(out, f)
            os.replace(tmp, path)
        except Exception:
            pass
    return out


def _reach(r):
    b = r.get('b') or [-30, -30, -30, 30, 30, 30]
    s = r.get('s') or 1.0
    return max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) * s + 16, b[2] * s - 40, b[5] * s + 30


def loads_on(f, things):
    """The things lying on fitting f (in its reach across, from under its foot to over its top): [(thing, local pose)]."""
    rad, lo, hi = _reach(f)
    c, sn = math.cos(f['p'][5]), math.sin(f['p'][5])
    out = []
    for t in things:
        dx, dy, dz = t['p'][0] - f['p'][0], t['p'][1] - f['p'][1], t['p'][2] - f['p'][2]
        if math.hypot(dx, dy) <= rad and lo <= dz <= hi:
            out.append((t, (dx * c - dy * sn, dx * sn + dy * c, dz, (t['p'][5] - f['p'][5]) % (2 * math.pi), t['p'][3], t['p'][4])))
    return out


def _survey(db):
    loads = defaultdict(list)          # model -> [[(id, pose)...] one load a fitting]
    seen = Counter()
    for (tag, key), _lst in db.by_key.items():
        if tag != 'CELL':
            continue
        try:
            m = mapdata.cellmap(db, key)
        except Exception:
            continue
        if m.get('own'):
            continue
        refs = m.get('refs') or ()
        fits = [r for r in refs if r['type'] in ('STAT', 'ACTI') and FIT.search(r['id'].lower()) and kind(r['id'].lower())]
        if not fits:
            continue
        things = [r for r in refs if r['type'] in CARRY_TAGS and not NOT_LOAD.search(r['id'].lower())]
        for f in fits:
            low = f['id'].lower()
            seen[low] += 1
            ld = loads_on(f, things)
            if kind(low) == 'rack':
                ld = [x for x in ld if x[0]['type'] in ('WEAP', 'ARMO')]
            if ld:
                loads[low].append([[x[0]['id'], [round(v, 2) for v in x[1]]] for x in ld[:6]])
    out = {'models': {}, 'kinds': defaultdict(list)}
    for low, L in loads.items():
        out['models'][low] = L[:60]
        out['kinds'][kind(low)].extend(L[:20])
    out['seen'] = dict(seen)
    out['kinds'] = dict(out['kinds'])
    return out


def _cheap(db, rid, tag):
    try:
        import shelfsurvey
        return shelfsurvey.value_of(db, rid)[1] <= (WEAPON_VALUE if tag == 'WEAP' else LOAD_VALUE)
    except Exception:
        return True


def fill(db, key, seed=1):
    """The made place's bare racks, sconces and hooks loaded as the game loads that model (or its kind). The number of
    things laid (no Undo step of its own)."""
    S = ready(db)
    if not S:
        return 0
    m = mapdata.cellmap(db, key)
    refs = m.get('refs') or ()
    fits = [r for r in refs if r.get('new') and r['type'] in ('STAT', 'ACTI') and FIT.search(r['id'].lower()) and kind(r['id'].lower())]
    if not fits:
        return 0
    things = [r for r in refs if r['type'] in CARRY_TAGS]
    rng = random.Random(seed)
    import editing
    from project import set_ref_pos, zs
    c_, _r = editing._cell(db, key)
    mine = db.project.plugin.lower()
    laid = 0
    for f in fits:
        low = f['id'].lower()
        k = kind(low)
        if loads_on(f, things) or rng.random() > FILL.get(k, 0.85):
            continue
        L = S['models'].get(low) or []
        if len(L) < MIN_LOADS:
            L = L + (S['kinds'].get(k) or [])
        rng.shuffle(L)
        c, sn = math.cos(f['p'][5]), math.sin(f['p'][5])
        for load in L[:12]:
            ok = []
            for rid, (lx, ly, lz, lrz, rx, ry) in load:
                ri = db.resolve_id(rid)
                if ri is None:
                    ok = None
                    break
                tag = db.recs[ri][0]
                if NOT_LOAD.search(rid.lower()) or not _cheap(db, rid, tag):
                    ok = None
                    break
                ok.append((ri, lx, ly, lz, lrz, rx, ry))
            if not ok:
                continue
            for ri, lx, ly, lz, lrz, rx, ry in ok:
                x, y = f['p'][0] + lx * c + ly * sn, f['p'][1] - lx * sn + ly * c
                rk = db.project.new_ref_key()
                editing._store(c_, rk, mine, int(rk.rsplit('|', 1)[1]),
                               set_ref_pos([('NAME', zs(db.recs[ri][1]))], (x, y, f['p'][2] + lz, rx, ry, (f['p'][5] + lrz) % (2 * math.pi)), 1.0))
                c_['refs'][rk]['by'] = 'furnish'
                laid += 1
            break
    if laid:
        db.sync_project()
    return laid
