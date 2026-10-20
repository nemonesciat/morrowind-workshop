"""How the game's own, hand-made interiors dress their bookshelves, shelves, tables, desks and counters:
for every such piece of furniture, what small things stand on or in it and exactly where (in the
furniture's own frame, shelf by shelf), kept as whole "dressings" per instance so Auto-furnish can
re-place a real one instead of scattering things at random.

An object is on a piece of furniture when its footprint lies inside the furniture's box and its bottom
sits on one of the furniture's surfaces: the shelf levels, found as the heights where object bottoms
cluster (a table has one, at its top; a bookshelf three or four)."""
import math
import re
from collections import Counter

import kits
import mapdata
from mapdata import ref_info

# the kinds of furniture things are set out on, by words in the ID
KINDS = {'bookshelf': re.compile(r'bookshelf|bookcase|book_?shelf'), 'shelf': re.compile(r'shelf|shelves'),
         'table': re.compile(r'table'), 'desk': re.compile(r'desk'), 'counter': re.compile(r'counter|_bar_|bar$')}
NOT = re.compile(r'tablet|tablecloth|marker|stable|turntable|table_?leg|_sm$')
SMALL = {'BOOK', 'MISC', 'INGR', 'ALCH', 'LIGH', 'APPA', 'LOCK', 'PROB', 'REPA', 'WEAP', 'ARMO', 'CLOT'}
MAX_SMALL = 110          # a STAT or CONT counts as a small thing on a shelf up to this long/high (a bookend, a plant, a small chest)
LEVEL_NEAR = 6           # an object's bottom this close to a surface stands on it
EDGE = 8                 # how far a thing may overhang the furniture's side and still be "on" it
_cache = {}


def kind_of(rid):
    """What kind of furniture this is (bookshelf, shelf, table, desk, counter), or None."""
    low = rid.lower()
    if NOT.search(low):
        return None
    for k in ('bookshelf', 'desk', 'counter', 'shelf', 'table'):
        if KINDS[k].search(low):
            return k
    return None


def _local(dx, dy, rz):
    """A world offset in an object's own frame (it is turned rz, clockwise)."""
    c, s = math.cos(rz), math.sin(rz)
    return dx * c - dy * s, dx * s + dy * c


def to_world(lx, ly, rz):
    """The inverse: an offset in an object's own frame, in the world."""
    c, s = math.cos(rz), math.sin(rz)
    return lx * c + ly * s, -lx * s + ly * c


def _turned(rx, ry, rz):
    a, b, c = -rx, -ry, -rz
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    X = ((1, 0, 0), (0, ca, -sa), (0, sa, ca))
    Y = ((cb, 0, sb), (0, 1, 0), (-sb, 0, cb))
    Z = ((cc, -sc, 0), (sc, cc, 0), (0, 0, 1))
    mul = lambda A, B: tuple(tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(Z, mul(Y, X))


def box_turned(b, rx, ry, rz, s=1.0):
    """Axis-aligned box (x0, y0, z0, x1, y1, z1) of a model's bounds turned every way and scaled, about its origin."""
    R = _turned(rx, ry, rz)
    pts = []
    for x in (b[0] * s, b[3] * s):
        for y in (b[1] * s, b[4] * s):
            for z in (b[2] * s, b[5] * s):
                pts.append((R[0][0] * x + R[0][1] * y + R[0][2] * z, R[1][0] * x + R[1][1] * y + R[1][2] * z,
                            R[2][0] * x + R[2][1] * y + R[2][2] * z))
    return (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))


def _bounds_of(db, cache, rid):
    k = rid.lower()
    if k not in cache:
        ri = db.resolve_id(rid)
        cache[k] = (mapdata.object_bounds(db, ri), db.recs[ri][0]) if ri is not None else (None, '')
    return cache[k]


def _small_kind(tag, b):
    """BOOK, MISC... for items; STAT or CONT only when small enough to stand on a shelf; else None."""
    if tag in SMALL:
        return tag
    if tag in ('STAT', 'CONT', 'ACTI') and b and max(b[3] - b[0], b[4] - b[1]) <= MAX_SMALL and b[5] - b[2] <= MAX_SMALL:
        return 'CONT' if tag == 'CONT' else 'STAT'
    return None


def _purpose(name):
    import furnish
    return furnish.purpose_for(name, 9, 3, 3) if name else 'living'


def survey(db, rid, limit=120):
    """Every dressing of this furniture model in the game's own places: {'n': instances looked at,
    'levels': [surface heights above the model's origin], 'dressings': [{'cell', 'purpose', 'objects':
    [{'id', 'kind', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's', 'level'}]}] (one per dressed instance),
    'empty': instances with nothing on them}. Positions are in the furniture's own frame, at scale 1."""
    low = rid.lower()
    if low in _cache and _cache[low][0] is db.recs:
        return _cache[low][1]
    out = {'n': 0, 'levels': [], 'dressings': [], 'empty': 0}
    fri = db.resolve_id(rid)
    fb = mapdata.object_bounds(db, fri) if fri is not None else None
    if not fb:
        _cache[low] = (db.recs, out)
        return out
    bounds = {}
    cells = sorted({db.recs[ci][7] for ci in db.used_in.get(low, ())
                    if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7])})
    if limit and len(cells) > limit:
        cells = cells[::max(1, len(cells) // limit)][:limit]       # (a spread over the whole list, not just the As)
    # pass 1: every candidate object inside each instance's box, with its bottom relative to the instance
    inst = []           # (cell, name, pos, [(obj rec, bottom_rel)])
    for ck in cells:
        try:
            refs, _h = db.cell_refs(ck)
        except Exception:
            continue
        info = mapdata.cell_info(db, ck) or {}
        things, mine = [], []
        for ref in refs.values():
            r2, pos, sc, dead = ref_info(ref['subs'])
            if dead:
                continue
            if r2.lower() == low:
                if abs((sc or 1.0) - 1.0) < 0.02:
                    mine.append(pos)
                continue
            b, tag = _bounds_of(db, bounds, r2)
            kd = _small_kind(tag, b)
            if kd and b:
                things.append((r2, pos, sc or 1.0, b, kd))
        for pos in mine:
            px, py, pz, _rx, _ry, rz = pos
            found = []
            for r2, p2, s2, b2, kd in things:
                if abs(p2[0] - px) > 400 or abs(p2[1] - py) > 400 or not (fb[2] - 40 <= p2[2] - pz <= fb[5] + 200):
                    continue
                lx, ly = _local(p2[0] - px, p2[1] - py, rz)
                ob = box_turned(b2, p2[3], p2[4], p2[5] - rz, s2)
                # its footprint inside the furniture's box (a little overhang allowed)
                if lx + ob[0] < fb[0] - EDGE or lx + ob[3] > fb[3] + EDGE or ly + ob[1] < fb[1] - EDGE or ly + ob[4] > fb[4] + EDGE:
                    continue
                bottom = p2[2] + ob[2] - pz
                if bottom < fb[2] - LEVEL_NEAR or bottom > fb[5] + LEVEL_NEAR:
                    continue
                found.append({'id': r2, 'kind': kd, 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(p2[2] - pz, 1),
                              'rx': round(p2[3], 3), 'ry': round(p2[4], 3), 'rz': round((p2[5] - rz) % (2 * math.pi), 3),
                              's': round(s2, 3), 'bottom': round(bottom, 1), 'fp': ob})
            inst.append((ck, info.get('name', ''), found))
    out['n'] = len(inst)
    # the surfaces: heights (above the origin) where bottoms cluster
    bottoms = sorted(o['bottom'] for _c, _n, f in inst for o in f)
    levels = []
    if bottoms:
        bins = Counter(int(round(b / 2.0)) for b in bottoms)
        need = max(2, int(0.04 * len(bottoms)))
        for k, n in sorted(bins.items(), key=lambda kv: -kv[1]):
            h = k * 2.0
            if n < need or any(abs(h - lv) < 12 for lv in levels):
                continue
            levels.append(h)
        levels.sort()
    out['levels'] = [round(lv, 1) for lv in levels]
    # pass 2: what stands on a surface makes the dressing; the rest (something leaning, hung above,
    # stacked on another thing) is left out
    for ck, name, found in inst:
        objs = []
        for o in found:
            lv = next((lv for lv in levels if abs(o['bottom'] - lv) <= LEVEL_NEAR), None)
            if lv is None:
                continue
            o = dict(o)
            o['level'] = round(lv, 1)
            objs.append(o)
        if objs:
            out['dressings'].append({'cell': ck, 'purpose': _purpose(name), 'objects': objs})
        else:
            out['empty'] += 1
    _cache[low] = (db.recs, out)
    return out


def _axis(fb):
    """Along which local axis a shelf's rows run (its long side), and the furniture's length along it."""
    w, d = fb[3] - fb[0], fb[4] - fb[1]
    return (0, w) if w >= d else (1, d)


def summary_of(db, rid):
    """For people: how often this model is dressed, with how much, how full its rows are, what goes on it."""
    s = survey(db, rid)
    fri = db.resolve_id(rid)
    fb = mapdata.object_bounds(db, fri) if fri is not None else None
    n = s['n']
    ds = s['dressings']
    out = {'id': rid, 'kind': kind_of(rid), 'n': n, 'dressed': len(ds), 'empty': s['empty'],
           'share_dressed': round(len(ds) / n, 2) if n else 0, 'levels': s['levels'],
           'objects_mean': round(sum(len(d['objects']) for d in ds) / len(ds), 1) if ds else 0,
           'kinds': Counter(), 'most_used': Counter(), 'row_fullness': {}, 'row_ends': Counter(), 'purposes': Counter()}
    if not ds or not fb:
        out['kinds'], out['most_used'], out['row_ends'], out['purposes'] = {}, [], {}, {}
        return out
    ax, length = _axis(fb)
    full = {}
    for d in ds:
        out['purposes'][d['purpose']] += 1
        rows = {}
        for o in d['objects']:
            out['kinds'][o['kind']] += 1
            out['most_used'][o['id'].lower()] += 1
            rows.setdefault(o['level'], []).append(o)
        for lv, objs in rows.items():
            spans = sorted((o[('x', 'y')[ax]] + o['fp'][ax], o[('x', 'y')[ax]] + o['fp'][ax + 3]) for o in objs)
            covered, cur = 0.0, None
            for a, b in spans:
                if cur is None or a > cur[1]:
                    if cur:
                        covered += cur[1] - cur[0]
                    cur = [a, b]
                else:
                    cur[1] = max(cur[1], b)
            if cur:
                covered += cur[1] - cur[0]
            full.setdefault(lv, []).append(min(1.0, covered / length))
            if len(objs) >= 3:
                by = sorted(objs, key=lambda o: o[('x', 'y')[ax]])
                for o in (by[0], by[-1]):
                    out['row_ends'][o['kind']] += 1
    out['row_fullness'] = {str(lv): round(sum(v) / len(v), 2) for lv, v in sorted(full.items())}
    out['kinds'] = dict(out['kinds'].most_common())
    out['most_used'] = out['most_used'].most_common(12)
    out['row_ends'] = dict(out['row_ends'].most_common())
    out['purposes'] = dict(out['purposes'].most_common())
    return out


def models(db, style=None, min_uses=3):
    """The furniture models of these kinds the game uses in at least min_uses places (of a style, by its
    ID prefix: in_hlaalu..., furn_de..., T_De_...)."""
    out = []
    for (tag, k), lst in db.by_key.items():
        if tag not in ('STAT', 'ACTI', 'CONT') or not kind_of(k) or not lst or lst[-1] in db.dead:
            continue
        if style and style.lower() not in k and (mapdata.style_of(k) or '').lower() != style.lower():
            continue
        if kits.game_uses(db, k) >= min_uses:
            out.append(db.recs[lst[-1]][1])
    return sorted(out, key=lambda r: -kits.game_uses(db, r.lower()))


def summary(db, ids):
    return [summary_of(db, rid) for rid in ids]


# ------------------------------------------------------------------ dressing a new piece of furniture
def _overlap(a, b, pad=1.0):
    return a[0] < b[3] - pad and b[0] < a[3] - pad and a[1] < b[4] - pad and b[1] < a[4] - pad and a[2] < b[5] - pad and b[2] < a[5] - pad


def _same_size(a, b, tol=2.5):
    return all(abs(a[i] - b[i]) <= tol for i in range(6))


# what suits a room: a dressing is a fit when at least half of it is of these kinds
WANTED = {'study': ('BOOK',), 'kitchen': ('INGR', 'MISC', 'ALCH'), 'tavern': ('ALCH', 'MISC', 'INGR', 'LIGH'),
          'shop': ('MISC', 'ALCH', 'INGR', 'WEAP', 'ARMO', 'CLOT', 'CONT', 'BOOK', 'APPA'),
          'bedroom': ('MISC', 'LIGH', 'BOOK', 'ALCH', 'CLOT'), 'living': ('MISC', 'INGR', 'ALCH', 'LIGH', 'BOOK'),
          'shrine': ('LIGH', 'MISC', 'BOOK', 'INGR'), 'hall': ('MISC', 'LIGH', 'BOOK', 'ALCH')}
_plain_cache = {}


def plain(db, rid, min_cells=2):
    """Everyday clutter, not a quest's own thing: used in a few of the game's places (a quest book or a
    unique key is placed once), not scripted, not a key; weapons, armour and clothes only when the game
    leaves them lying about in several places (an artifact on a shelf stays where it is)."""
    low = rid.lower()
    key = (low, min_cells)
    if key in _plain_cache and _plain_cache[key][0] is db.recs:
        return _plain_cache[key][1]
    ok = False
    ri = db.resolve_id(rid)
    if ri is not None and not re.search(r'(^|_)key(_|$|s)', low):
        r = db.recs[ri]
        need = min_cells if r[0] not in ('WEAP', 'ARMO', 'CLOT') else max(4, min_cells)
        cells = {db.recs[ci][7] for ci in db.used_in.get(low, ()) if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7])}
        if len(cells) >= need:
            from esm import iter_subrecords
            try:
                _t, _f, data = db.files[r[3]].record_at(r[4])
                ok = not any(st == 'SCRI' for st, _sd in iter_subrecords(data))
            except Exception:
                ok = True
    _plain_cache[key] = (db.recs, ok)
    return ok


def dressing(db, rid, purpose, rng, books=(), min_uses=2):
    """A dressing for a new piece of this furniture, from what the game puts on it: one of the game's own
    dressings (picked at random, so the common patterns come up most; from rooms of this purpose when the
    game has dressed it in a few of those), with small variation: a book swapped for another of the same
    size that the game uses in places like this, the odd end piece dropped or another added, never two
    things in one spot. [{'id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's'}] in the furniture's frame, or None
    when the game never dresses this model (the caller then does what it did before)."""
    s = survey(db, rid)
    if not s['dressings']:
        return None
    pool = [d for d in s['dressings'] if d['purpose'] == purpose]
    if len(pool) < 3:
        pool = s['dressings']
    # and of those, the ones that suit the room: mostly books and papers in a study, food and dishes in a
    # kitchen, wares in a shop (when the game has dressed it that way in a few places)
    want = WANTED.get(purpose)
    if want:
        share = 0.4 if purpose == 'study' else 0.5      # (a study's shelves hold bookends, a candle, an inkwell too)
        fits = lambda ds: [d for d in ds if sum(1 for o in d['objects'] if o['kind'] in want) >= share * len(d['objects'])]
        fit = fits(pool)
        if len(fit) < 6:
            # (few from rooms of this purpose: fitting ones from anywhere, so the same one isn't repeated)
            wider = fits(s['dressings'])
            if len(wider) > len(fit):
                fit = wider
        if len(fit) >= 3:
            pool = fit
    # the game leaves some of these bare: so does this, a little less often
    empty_share = s['empty'] / float(s['n'] or 1)
    if rng.random() < max(0.0, empty_share - 0.3):
        return []
    # (two picked, the fuller one kept most of the time: rows packed the way the game's best ones are)
    a, b = rng.choice(pool), rng.choice(pool)
    chosen = max(a, b, key=lambda d: len(d['objects'])) if rng.random() < 0.67 else a
    bounds = {}
    objs = []
    for o in chosen['objects']:
        # (nothing the game placed only once: a quest's own book or note stays where it is)
        if not plain(db, o['id'], min_uses):
            continue
        objs.append(dict(o))
    # a book swapped now and then for another of the same size from the place's own palette
    same = {}
    for o in objs:
        if o['kind'] != 'BOOK' or not books or rng.random() > 0.45:
            continue
        b0, _t = _bounds_of(db, bounds, o['id'])
        if not b0:
            continue
        key = o['id'].lower()
        if key not in same:
            same[key] = [bk for bk in books if bk.lower() != key and (lambda bb: bb and _same_size(bb, b0))(_bounds_of(db, bounds, bk)[0])]
        if same[key]:
            o['id'] = rng.choice(same[key])
    # (and books from the palette may be a quest's too)
    objs = [o for o in objs if o['kind'] != 'BOOK' or plain(db, o['id'], min_uses)]
    # the odd end piece dropped, or another one from a second dressing added where there is room
    fri = db.resolve_id(rid)
    fb = mapdata.object_bounds(db, fri)
    ax = _axis(fb)[0] if fb else 0
    rows = {}
    for o in objs:
        rows.setdefault(o['level'], []).append(o)
    if objs and rng.random() < 0.3:
        lv = rng.choice(list(rows))
        row = rows[lv]
        if len(row) >= 2:
            end = max(row, key=lambda o: o[('x', 'y')[ax]]) if rng.random() < 0.5 else min(row, key=lambda o: o[('x', 'y')[ax]])
            objs.remove(end)
    if len(pool) > 1 and rng.random() < 0.35:
        other = rng.choice(pool)
        if other is not chosen:
            extra = [o for o in other['objects'] if o['kind'] != 'BOOK' and plain(db, o['id'], min_uses)]
            rng.shuffle(extra)
            for o in extra[:3]:
                box = (o['x'] + o['fp'][0], o['y'] + o['fp'][1], o['z'] + o['fp'][2], o['x'] + o['fp'][3], o['y'] + o['fp'][4], o['z'] + o['fp'][5])
                if not any(_overlap(box, (p['x'] + p['fp'][0], p['y'] + p['fp'][1], p['z'] + p['fp'][2],
                                          p['x'] + p['fp'][3], p['y'] + p['fp'][4], p['z'] + p['fp'][5])) for p in objs):
                    objs.append(dict(o))
                    break
    return [{k: o[k] for k in ('id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's')} for o in objs]
