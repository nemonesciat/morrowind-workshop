"""How the game's own, hand-made interiors hang banners, tapestries and their hangers: what hangs together
(a banner on its hanger, at what offset), how high, and how far out from the wall. Auto-furnish goes by
it, so a hanger is never hung on its own and a banner hangs from its hanger the way the game does it."""
import math
import re
from collections import Counter

import kits
import mapdata
from mapdata import ref_info

HANGY = re.compile(r'tapestr|banner|hanger|flag|pennant')
HOLDER = re.compile(r'hanger|bannerpost|flagpole|banner_?post|_pole')
_cache = {}


def _local(dx, dy, rz):
    """A world offset in an object's own frame (it is turned rz, clockwise)."""
    c, s = math.cos(rz), math.sin(rz)
    return dx * c - dy * s, dx * s + dy * c


def survey(db, rid, limit=25):
    """Where the game hangs this object: {'n', 'with': Counter of companions, 'offsets': {companion: [(lx,
    ly, dz, dq)]}, 'alone': how often nothing hangs with it}."""
    low = rid.lower()
    if low in _cache and _cache[low][0] is db.recs:
        return _cache[low][1]
    import modelcache
    kept = modelcache.get(db, 'wallhang', low)
    if kept is not None:
        kept = {'n': kept['n'], 'with': Counter(kept['with']), 'offsets': {k: [tuple(o) for o in v] for k, v in kept['offsets'].items()}, 'alone': kept['alone']}
        _cache[low] = (db.recs, kept)
        return kept
    out = {'n': 0, 'with': Counter(), 'offsets': {}, 'alone': 0}
    cells = [db.recs[ci][7] for ci in db.used_in.get(low, ()) if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7])]
    for ck in sorted(set(cells))[:limit]:
        refs, _h = db.cell_refs(ck)
        items = []
        for ref in refs.values():
            r2, pos, sc, dead = ref_info(ref['subs'])
            if not dead:
                items.append((r2.lower(), pos))
        for r2, pos in items:
            if r2 != low:
                continue
            out['n'] += 1
            comp = set()
            for r3, p3 in items:
                if p3 is pos or not HANGY.search(r3):
                    continue
                dx, dy, dz = p3[0] - pos[0], p3[1] - pos[1], p3[2] - pos[2]
                if math.hypot(dx, dy) > 72 or abs(dz) > 260:
                    continue
                lx, ly = _local(dx, dy, pos[5])
                dq = int(round(((p3[5] - pos[5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                if r3 in comp:
                    continue
                comp.add(r3)
                out['with'][r3] += 1
                out['offsets'].setdefault(r3, []).append((round(lx), round(ly), round(dz), dq))
            if not comp:
                out['alone'] += 1
    _cache[low] = (db.recs, out)
    modelcache.put(db, 'wallhang', low, {'n': out['n'], 'with': dict(out['with']), 'offsets': out['offsets'], 'alone': out['alone']})
    return out


def partner(db, rid):
    """What the game (nearly) always hangs with this object, and where: {'id', 'offset': (lx, ly, dz),
    'dq', 'share'} or None. Only when it is with something in at least 3 places out of 5."""
    s = survey(db, rid)
    if s['n'] < 3 or not s['with']:
        return None
    # (hangers, banner posts and flagpoles count together: a banner on either post is on a post; at
    # least half the time is enough for those. Anything else: 3 times in 5)
    holders = [(k, v) for k, v in s['with'].items() if HOLDER.search(k) and not HOLDER.search(rid.lower())]
    if holders and sum(v for _k, v in holders) >= 0.5 * s['n']:
        best, n = max(holders, key=lambda kv: kv[1])
    else:
        best, n = s['with'].most_common(1)[0]
        if n < 0.6 * s['n']:
            return None
    offs = s['offsets'][best]
    mid = lambda i: sorted(o[i] for o in offs)[len(offs) // 2]
    dq = Counter(o[3] for o in offs).most_common(1)[0][0]
    return {'id': best, 'offset': (mid(0), mid(1), mid(2)), 'dq': dq, 'share': round(n / s['n'], 2), 'n': s['n']}


def hangs_alone(db, rid):
    """Whether the game ever hangs this on its own (a hanger with no banner on it: almost never)."""
    s = survey(db, rid)
    return s['n'] < 3 or s['alone'] >= 0.3 * s['n']


def summary(db, ids):
    """For people: for each object, in how many places, what hangs with it and how often."""
    out = []
    for rid in ids:
        s = survey(db, rid)
        p = partner(db, rid)
        out.append({'id': rid, 'n': s['n'], 'alone': s['alone'], 'with': s['with'].most_common(3),
                    'partner': p})
    return out
