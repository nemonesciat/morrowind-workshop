"""How the game's own, hand-made interiors dress their bookshelves, shelves, tables, desks and counters:
for every such piece of furniture, what small things stand on or in it and exactly where (in the
furniture's own frame, shelf by shelf), kept as whole "dressings" per instance so Auto-furnish can
re-place a real one instead of scattering things at random.

An object is on a piece of furniture when its footprint lies inside the furniture's box and its bottom
sits on one of the furniture's surfaces: the shelf levels, found as the heights where object bottoms
cluster (a table has one, at its top; a bookshelf three or four)."""
import json
import math
import os
import re
import struct
import threading
from collections import Counter

import kits
import mapdata
from esm import iter_subrecords
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


def _mul(A, B):
    (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = A
    (b00, b01, b02), (b10, b11, b12), (b20, b21, b22) = B
    return ((a00 * b00 + a01 * b10 + a02 * b20, a00 * b01 + a01 * b11 + a02 * b21, a00 * b02 + a01 * b12 + a02 * b22),
            (a10 * b00 + a11 * b10 + a12 * b20, a10 * b01 + a11 * b11 + a12 * b21, a10 * b02 + a11 * b12 + a12 * b22),
            (a20 * b00 + a21 * b10 + a22 * b20, a20 * b01 + a21 * b11 + a22 * b21, a20 * b02 + a21 * b12 + a22 * b22))


# (the same few rotations come up thousands of times over in a survey of the game's shelves: remembered)
_turned_memo = {}
_local_memo = {}
_box_memo = {}


def _turned(rx, ry, rz):
    """The game's rotation (OpenMW's makeOsgQuat): turned about its own Z first, then Y, then X, each
    clockwise. As a matrix on column vectors: X(-rx) . Y(-ry) . Z(-rz). (Not Z.Y.X: a book standing on a
    shelf is spun flat first, then tipped up; the other order lays most of the game's books down.)"""
    key = (rx, ry, rz)
    M = _turned_memo.get(key)
    if M is not None:
        return M
    a, b, c = -rx, -ry, -rz
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    X = ((1, 0, 0), (0, ca, -sa), (0, sa, ca))
    Y = ((cb, 0, sb), (0, 1, 0), (-sb, 0, cb))
    Z = ((cc, -sc, 0), (sc, cc, 0), (0, 0, 1))
    M = _mul(X, _mul(Y, Z))
    if len(_turned_memo) > 50000:
        _turned_memo.clear()
    _turned_memo[key] = M
    return M


def euler_of(M):
    """(rx, ry, rz) in the game's convention for a rotation matrix of _turned's form."""
    b = math.asin(max(-1.0, min(1.0, M[0][2])))
    if abs(math.cos(b)) > 1e-6:
        a = math.atan2(-M[1][2], M[2][2])
        c = math.atan2(-M[0][1], M[0][0])
    else:                                              # (looking straight up or down: one angle will do)
        a = math.atan2(M[2][1], M[1][1])
        c = 0.0
    return (-a) % (2 * math.pi), (-b) % (2 * math.pi), (-c) % (2 * math.pi)


def local_rot(rx, ry, rz, shelf_rz):
    """A thing's rotation relative to the furniture it stands on (turned shelf_rz about Z): (rx, ry, rz)."""
    key = (rx, ry, rz, shelf_rz)
    got = _local_memo.get(key)
    if got is not None:
        return got
    S = _turned(0, 0, shelf_rz)
    St = tuple(tuple(S[j][i] for j in range(3)) for i in range(3))       # (its inverse)
    got = euler_of(_mul(St, _turned(rx, ry, rz)))
    if len(_local_memo) > 50000:
        _local_memo.clear()
    _local_memo[key] = got
    return got


def compose_on(rx, ry, rz, shelf_rz):
    """The inverse: a relative rotation put back on a shelf turned shelf_rz: world (rx, ry, rz)."""
    return euler_of(_mul(_turned(0, 0, shelf_rz), _turned(rx, ry, rz)))


def box_turned(b, rx, ry, rz, s=1.0):
    """Axis-aligned box (x0, y0, z0, x1, y1, z1) of a model's bounds turned every way and scaled, about its origin."""
    key = (tuple(b), rx, ry, rz, s)
    got = _box_memo.get(key)
    if got is not None:
        return got
    R = _turned(rx, ry, rz)
    pts = []
    for x in (b[0] * s, b[3] * s):
        for y in (b[1] * s, b[4] * s):
            for z in (b[2] * s, b[5] * s):
                pts.append((R[0][0] * x + R[0][1] * y + R[0][2] * z, R[1][0] * x + R[1][1] * y + R[1][2] * z,
                            R[2][0] * x + R[2][1] * y + R[2][2] * z))
    got = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
           max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
    if len(_box_memo) > 50000:
        _box_memo.clear()
    _box_memo[key] = got
    return got


def _bounds_of(db, cache, rid):
    k = rid.lower()
    if k not in cache:
        ri = db.resolve_id(rid)
        cache[k] = (mapdata.object_bounds(db, ri), db.recs[ri][0]) if ri is not None else (None, '')
    return cache[k]


PLANTER = re.compile(r'planter|flowerbox|plantpot|plant_pot|gardenbed|garden_bed')
WINERACK = re.compile(r'winerack|wine_rack|bottlerack')
# what the game grows in its planters, whatever its size: plants, shrubs, small trees, rocks, ferns, moss
GARDEN = re.compile(r'flora_|_plant|fern|shrub|bush|tree|vine|mushroom|flower|ivy|rock|stone|grass|moss|kelp|reed|weed')


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


_items = {}         # cell key -> its live refs (the whole-game survey reads the same cells 260 times over)


def _cell_items(db, ck):
    """The live refs of a cell as (id, id lower, pos, scale, bounds, small kind), read once per load order;
    None when it can't be read."""
    if _items.get('_recs') is not db.recs or len(_items) > 6000:
        _items.clear()
        _items['_recs'] = db.recs
    if ck in _items and ck not in ('_recs', '_bounds'):
        return _items[ck]
    try:
        refs, _h = db.cell_refs(ck)
    except Exception:
        _items[ck] = None
        return None
    out = []
    bounds = _items.setdefault('_bounds', {})
    for ref in refs.values():
        r2, pos, sc, dead = ref_info(ref['subs'])
        if dead:
            continue
        b, tag = _bounds_of(db, bounds, r2)
        out.append((r2, r2.lower(), pos, sc, b, _small_kind(tag, b)))
    _items[ck] = out
    return out


_busy = set()       # the ids being surveyed right now (a twin that names this one back never recurses into it)


def groups_of(db, bounds, dressing):
    """The compositions in one dressing: each object that stands on the surface itself, with whatever
    the game stands on or in it (a fish on a plate, a pen in an inkwell, an ingredient on a paper, coins
    on a scale): [{'base': object, 'riders': [objects]}]. A rider's middle lies inside the base's
    footprint and its bottom is up off the base's bottom (on its top, or down inside it); a book packed
    beside another on the same board is no rider."""
    boxes = []
    for o in dressing['objects']:
        ob, _tag = _bounds_of(db, bounds, o['id'])
        if not ob:
            boxes.append(None)
            continue
        tb = box_turned(ob, o['rx'], o['ry'], o['rz'], o['s'])
        boxes.append((o['x'] + tb[0], o['y'] + tb[1], o['z'] + tb[2], o['x'] + tb[3], o['y'] + tb[4], o['z'] + tb[5]))
    rider_of = {}
    for i, o in enumerate(dressing['objects']):
        wb = boxes[i]
        if wb is None:
            continue
        best = None
        for j, p in enumerate(dressing['objects']):
            pb = boxes[j]
            if j == i or pb is None:
                continue
            if not (pb[0] - 2 <= o['x'] <= pb[3] + 2 and pb[1] - 2 <= o['y'] <= pb[4] + 2):
                continue
            if wb[2] < pb[2] + 2 or wb[2] > pb[5] + 6:
                continue                # (not up off the base's bottom, or floating above its top)
            area = (pb[3] - pb[0]) * (pb[4] - pb[1])
            if area <= (wb[3] - wb[0]) * (wb[4] - wb[1]) * 0.8:
                continue                # (the base is the bigger footprint: a plate under the fish, not the fish under the plate)
            if best is None or area < best[0]:
                best = (area, j)
        if best is not None:
            rider_of[i] = best[1]
    # (a rider's rider rides the same base: the pen in the inkwell on the tray)
    def root(i):
        seen = set()
        while i in rider_of and i not in seen:
            seen.add(i)
            i = rider_of[i]
        return i
    out = {}
    for i, o in enumerate(dressing['objects']):
        if boxes[i] is None:
            continue
        r = root(i)
        if r == i:
            out.setdefault(i, {'base': o, 'riders': []})
        else:
            out.setdefault(r, {'base': dressing['objects'][r], 'riders': []})['riders'].append(o)
    return list(out.values())


def alone_rates(db, bounds, survey):
    """For every id in a model's dressings: (times it stands on its own or as a base, times it rides on
    something). An id the game only ever stands on another thing (a fish only ever on a plate, a pen
    only in an inkwell) is not offered on its own."""
    from collections import Counter
    alone, rode = Counter(), Counter()
    for d in survey['dressings']:
        for g in groups_of(db, bounds, d):
            alone[g['base']['id'].lower()] += 1
            for o in g['riders']:
                rode[o['id'].lower()] += 1
    return alone, rode


# (the on-disk table of dressings per model: 'shelfdress2' since the model reader began ignoring a mesh's root
# transform, which moved the bounds, and so the surface levels kept here, of 268 of the game's models)
SHELF_TABLE = 'shelfdress2'


def _own_result(db, rid, limit=120):
    """This id's own dressings, from the memory cache, the disk cache or a walk of the game's places:
    never its twins' (so a twin's lookup cannot call back into the model that asked)."""
    low = rid.lower()
    if low in _cache and _cache[low][0] is db.recs:
        return _cache[low][1]
    import modelcache
    kept = modelcache.get(db, SHELF_TABLE, low)
    if kept is not None:
        return kept
    out = _survey_own(db, rid, limit)
    modelcache.put(db, SHELF_TABLE, low, out)
    return out


def survey(db, rid, limit=120):
    """Every dressing of this furniture model in the game's own places: {'n': instances looked at,
    'levels': [surface heights above the model's origin], 'dressings': [{'cell', 'purpose', 'objects':
    [{'id', 'kind', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's', 'level'}]}] (one per dressed instance),
    'empty': instances with nothing on them}. Positions are in the furniture's own frame, at scale 1."""
    low = rid.lower()
    if low in _cache and _cache[low][0] is db.recs:
        return _cache[low][1]
    if low in _busy:
        return _own_result(db, rid, limit)       # (asked again from inside its own twins' lookup: its own result, no further twins)
    _busy.add(low)
    try:
        import modelcache
        kept = modelcache.get(db, SHELF_TABLE, low)         # (on disk from an earlier furnish: the cells aren't walked again)
        if kept is not None:
            if len(kept['dressings']) < 3:
                s2 = twin_survey(db, rid, limit)              # (a thin result kept from before the twins were looked up)
                if s2 is not None and len(s2['dressings']) > len(kept['dressings']):
                    kept = s2
            _cache[low] = (db.recs, kept)
            return kept
        # (a model the game stands nowhere under this id, with the very same mesh as one it dresses: the
        # game's activator bookshelf beside its furniture twin, a hidden door made from a bookcase: the
        # twin's dressings, in the same frame. The user: "Why doesn't this bookshelf have an auto decorate
        # option? other ones do")
        import furnish
        twin = furnish.taught_twin(db, rid)
        if twin and twin.lower() != low and twin.lower() not in _busy:
            s2 = survey(db, twin, limit)
            _cache[low] = (db.recs, s2)
            return s2
        out = _survey_own(db, rid, limit)
        if len(out['dressings']) < 3:
            # (a variant record the game stands once or twice, furn_com_r_bookshelf_01_telvos: the same mesh's
            # twin with the game's dressings, else the id's stem, furn_com_r_bookshelf_01; two thin models that
            # name each other as twins each keep their own thin result)
            s2 = twin_survey(db, rid, limit)
            if s2 is not None and len(s2['dressings']) > len(out['dressings']):
                _cache[low] = (db.recs, s2)
                return s2
        _cache[low] = (db.recs, out)
        modelcache.put(db, SHELF_TABLE, low, out)
        return out
    finally:
        _busy.discard(low)


def twin_survey(db, rid, limit=120):
    """The dressings of a model's twin (the same mesh, most used by the game first) or of its id's stem
    (the name less its last suffix: a Telvos or a Huleen variant of a bookshelf), the first with three
    dressings or more; None when there is none. Each twin's own dressings only (never the twin's twins),
    so two thin models that name each other can never call each other forever."""
    import furnish
    low = rid.lower()
    tried = {low}
    cands = list(furnish.mesh_siblings(db, rid))
    stem = low
    while '_' in stem:
        stem = stem.rsplit('_', 1)[0]
        if db.resolve_id(stem) is not None:
            cands.append(stem)
    for c in cands:
        if c.lower() in tried or c.lower() in _busy:
            continue
        tried.add(c.lower())
        s2 = _own_result(db, c, limit)
        if len(s2['dressings']) >= 3:
            return s2
    return None


def _survey_own(db, rid, limit=120):
    """This very id's dressings, walked from the game's places (survey() wraps it with the cache and the twins)."""
    low = rid.lower()
    import modelcache
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
    # (an exemplary place's dressings count several times over, and are never left out of the spread)
    import taste
    cells = taste.order(sorted(set(cells) | {c for c in taste.places() if low in db.used_in and c in {db.recs[ci][7] for ci in db.used_in.get(low, ()) if db.recs[ci][0] == 'CELL'}}))
    # pass 1: every candidate object inside each instance's box, with its bottom relative to the instance
    inst = []           # (cell, name, pos, [(obj rec, bottom_rel)])
    # (a planter's dressing is its garden: plants, shrubs, small trees and rocks of any size, sunk into
    # the soil or standing up on a rock, not only the small things a shelf holds)
    is_planter = bool(PLANTER.search(low))
    top_slack = 60 if is_planter else LEVEL_NEAR
    for ck in cells:
        items = _cell_items(db, ck)
        if items is None:
            continue
        info = mapdata.cell_info(db, ck) or {}
        things, mine = [], []
        for r2, r2low, pos, sc, b, kd in items:
            if r2low == low:
                if abs((sc or 1.0) - 1.0) < 0.02:
                    mine.append(pos)
                continue
            if not kd and is_planter and b and GARDEN.search(r2low) and not PLANTER.search(r2low) \
                    and _bounds_of(db, bounds, r2)[1] in ('STAT', 'ACTI'):
                kd = 'STAT'
            if kd and b:
                things.append((r2, pos, sc or 1.0, b, kd))
        for pos in mine:
            px, py, pz, _rx, _ry, rz = pos
            found = []
            for r2, p2, s2, b2, kd in things:
                if abs(p2[0] - px) > 400 or abs(p2[1] - py) > 400 or not (fb[2] - 40 <= p2[2] - pz <= fb[5] + 200):
                    continue
                lx, ly = _local(p2[0] - px, p2[1] - py, rz)
                lrx, lry, lrz = local_rot(p2[3], p2[4], p2[5], rz)
                ob = box_turned(b2, lrx, lry, lrz, s2)
                # its footprint inside the furniture's box (a little overhang allowed); a plant in a planter
                # by its root (its origin): a shrub's fronds overhang the box on every side
                if is_planter:
                    if not (fb[0] - EDGE <= lx <= fb[3] + EDGE and fb[1] - EDGE <= ly <= fb[4] + EDGE):
                        continue
                elif lx + ob[0] < fb[0] - EDGE or lx + ob[3] > fb[3] + EDGE or ly + ob[1] < fb[1] - EDGE or ly + ob[4] > fb[4] + EDGE:
                    continue
                bottom = p2[2] + ob[2] - pz
                if bottom < fb[2] - LEVEL_NEAR or bottom > fb[5] + top_slack:
                    continue
                found.append({'id': r2, 'kind': kd, 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(p2[2] - pz, 1),
                              'rx': round(lrx, 3), 'ry': round(lry, 3), 'rz': round(lrz, 3),
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
                if not is_planter:
                    continue
                lv = min(levels, key=lambda l: abs(o['bottom'] - l)) if levels else o['bottom']    # (soil is uneven: every plant counts)
            o = dict(o)
            o['level'] = round(lv, 1)
            objs.append(o)
        if objs:
            out['dressings'].append({'cell': ck, 'purpose': _purpose(name), 'objects': objs})
        else:
            out['empty'] += 1
    _cache[low] = (db.recs, out)
    modelcache.put(db, SHELF_TABLE, low, out)
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


def _axes(b):
    """Which model axis is the thinnest, the middle and the longest: (thickness, width, height)."""
    dims = [b[3] - b[0], b[4] - b[1], b[5] - b[2]]
    return tuple(sorted(range(3), key=lambda i: dims[i]))


# what suits a room: a dressing is a fit when at least half of it is of these kinds
WANTED = {'study': ('BOOK',), 'kitchen': ('INGR', 'MISC', 'ALCH'), 'tavern': ('ALCH', 'MISC', 'INGR', 'LIGH'),
          'shop': ('MISC', 'ALCH', 'INGR', 'WEAP', 'ARMO', 'CLOT', 'CONT', 'BOOK', 'APPA'),
          'bedroom': ('MISC', 'LIGH', 'BOOK', 'ALCH', 'CLOT'), 'living': ('MISC', 'INGR', 'ALCH', 'LIGH', 'BOOK'),
          'shrine': ('LIGH', 'MISC', 'BOOK', 'INGR'), 'hall': ('MISC', 'LIGH', 'BOOK', 'ALCH')}
_books_cache = {}


def _everyday_books(db, min_uses=2):
    """Every book (not a scroll, not a skill book, not a quest's) the game leaves lying about in a few
    places. (Skill books come at the game's own rate, with the other interesting things.)"""
    if min_uses in _books_cache and _books_cache[min_uses][0] is db.recs:
        return _books_cache[min_uses][1]
    out = []
    for i in range(len(db.recs)):
        r = db.recs[i]
        if r[0] == 'BOOK' and i not in db.dead and r[1].lower().startswith(('bk_', 't_bk')) and plain(db, r[1], min_uses) \
                and not interesting(db, r[1]):
            out.append(r[1])
    _books_cache[min_uses] = (db.recs, out)
    return out


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
            try:
                _t, _f, data = db.files[r[3]].record_at(r[4])
                ok = not any(st == 'SCRI' for st, _sd in iter_subrecords(data))
            except Exception:
                ok = True
    _plain_cache[key] = (db.recs, ok)
    return ok


# ------------------------------------------------------------------ the interesting things
# weight and value live at the start of each item's stats block (as verify.py reads them)
STATS = {'WEAP': ('WPDT', '<fi'), 'ARMO': ('AODT', '<xxxxfi'), 'CLOT': ('CTDT', '<xxxxfh'), 'MISC': ('MCDT', '<fi'),
         'BOOK': ('BKDT', '<fiiii'), 'ALCH': ('ALDT', '<fi'), 'APPA': ('AADT', '<xxxxffi'), 'LOCK': ('LKDT', '<fi'),
         'PROB': ('PBDT', '<fi'), 'REPA': ('RIDT', '<fi'), 'LIGH': ('LHDT', '<fi'), 'INGR': ('IRDT', '<fi')}
_value_cache = {}


def value_of(db, rid):
    """(record type, value in gold, extra) of an item: extra has 'scroll' and 'skill' for a book."""
    k = rid.lower()
    hit = _value_cache.get(k)
    if hit and hit[0] is db.recs:
        return hit[1]
    out = (None, 0, {})
    ri = db.resolve_id(rid)
    if ri is not None:
        r = db.recs[ri]
        tag, val, extra = r[0], 0, {}
        st = STATS.get(tag)
        if st:
            try:
                _t, _f, data = db.files[r[3]].record_at(r[4])
                for t, d in iter_subrecords(data):
                    if t == st[0] and len(d) >= struct.calcsize(st[1]):
                        v = struct.unpack_from(st[1], d)
                        if tag == 'APPA':
                            val = v[2]
                        elif tag == 'BOOK':
                            val, extra = v[1], {'scroll': v[2], 'skill': v[3]}
                        else:
                            val = v[1]
                        break
            except Exception:
                pass
        out = (tag, val, extra)
    _value_cache[k] = (db.recs, out)
    return out


# what makes a thing on a shelf "interesting": a potion rather than a mug, a soul gem, a mortar, a gem, a
# spell scroll, a skill book, a ring, a blade on show. The everyday drinks and blank paper the game
# strews about (worth a few coins) don't count; these kinds always do
INTEREST_MIN_VALUE = 35
INTERESTING = ('potion', 'apparatus', 'soulgem', 'gem', 'valuable', 'scroll', 'skillbook', 'jewellery', 'weapon',
               'armour', 'tool', 'ingredient')
ALWAYS = ('apparatus', 'soulgem', 'skillbook', 'jewellery')
# arms and armour on show belong in a shop or a guild hall, not a home; nothing from a ruin or a camp either
ARMS = ('weapon', 'armour')
ARMS_THEMES = ('shop', 'guild')
NOT_HOME = ('ruin', 'camp')


def category(db, rid):
    """What kind of thing this is, in the survey's words (potion, gem, scroll, dish, cutlery, ...)."""
    tag, val, ex = value_of(db, rid)
    low = rid.lower()
    if tag == 'INGR':
        return 'gem' if re.search(r'diamond|ruby|emerald|pearl|sapphire|amethyst|amber|moonstone|gem', low) else 'ingredient'
    if tag == 'ALCH':
        return 'potion'
    if tag == 'APPA':
        return 'apparatus'
    if tag == 'MISC':
        if 'soulgem' in low:
            return 'soulgem'
        if re.search(r'^gold_\d|(^|_)coins?(_|\d|$)', low):
            return 'gold'                  # (the coins: not T_Com_MetalPieceGold, a thousand-gold ingot)
        if re.search(r'bookend', low):
            return 'bookend'
        if val >= 50:
            return 'valuable'
        return 'misc'
    if tag == 'BOOK':
        if ex.get('scroll'):
            return 'scroll'
        if ex.get('skill', -1) >= 0:
            return 'skillbook'
        return 'book'
    if tag == 'CLOT':
        return 'jewellery' if re.search(r'ring|amulet', low) else 'clothes'
    if tag in ('LOCK', 'PROB', 'REPA'):
        return 'tool'
    if tag == 'WEAP':
        return 'weapon'
    if tag == 'ARMO':
        return 'armour'
    return (tag or 'none').lower()


def interesting(db, rid):
    """The category when this is an interesting thing to find on a shelf, else None."""
    c = category(db, rid)
    if c not in INTERESTING:
        return None
    if c in ALWAYS or value_of(db, rid)[1] >= INTEREST_MIN_VALUE:
        return c
    return None


# the everyday things that may stand in for one another (same family, same size, modelled the same way)
FAMILY_WORDS = (('bottle', r'bottle|flask|decanter'), ('cup', r'cup|goblet|mug|tankard|glass_'), ('plate', r'plate|platter|tray'),
                ('bowl', r'bowl'), ('pitcher', r'pitcher|jug|vase|urn'), ('cutlery', r'fork|knife|spoon'),
                ('pot', r'_pot_|pot_|_pot$'), ('cloth', r'cloth|folded'), ('paper', r'paper|scroll|quill|inkwell'))
ROUND = ('bottle', 'cup', 'bowl', 'pitcher', 'pot', 'drink')
# things the game only stands as part of a scene (a painter's palette and pots with the easel, brushes and
# canvases; the alchemist's apparatus; a smith's tongs): never swapped in as an everyday thing, never stood
# alone on a bedside or dining table (the user: "the paints look out of place without the easel")
SCENE_ONLY = re.compile(r'paint|pigment|easel|canvas|brush|dye_|_dye|inkpot|ink_pot|palette|mortar|pestle|alembic|retort|calcinator|tongs|anvil')


def family(db, rid):
    """Which family of everyday thing this is (bottle, cup, plate, bowl, pitcher, cutlery, drink for a
    potion, food for an ingredient), or None when it isn't one that is swapped for another."""
    tag, _v, _e = value_of(db, rid)
    low = rid.lower()
    if tag == 'ALCH':
        return 'drink'
    if tag == 'INGR':
        return 'food'
    if tag != 'MISC' or 'soulgem' in low or re.search(r'gold_\d|coin|bookend', low):
        return None
    if SCENE_ONLY.search(low):
        return None            # (a painter's pot is no cooking pot: never swapped in among cups and bottles)
    for fam, pat in FAMILY_WORDS:
        if re.search(pat, low):
            return fam
    return None


_interest = {}
_ithread = {}
INTEREST_V = 'v2'


def _wrap(a):
    """An angle in (-pi, pi], to a tenth (so a turn of 6.28 reads as none)."""
    return round(((a + math.pi) % (2 * math.pi)) - math.pi, 1)


def _idisk(db):
    import project
    import taste
    sig = taste.sig(db)                 # (keyed by the plugins that hold interiors, like every other survey)
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'shelfinterest_%s_%s.json' % (sig, INTEREST_V))


def interest_survey(db, min_uses=3):
    """What the game stands on its dressed furniture beyond the everyday, over every model of those kinds:
    {'purpose': {room purpose: {'n': dressings, 'with': dressings holding something interesting, 'kinds':
    {furniture kind: [n, with]}, 'items': {id: [category, sightings, value, rx, ry, rz] (its usual pose
    on the furniture)}, 'everyday': {id:
    sightings} (the dishes, bottles and food on them)}}, 'theme': {place theme: {'n', 'with', 'cap': a
    value most things there stay under}}}. A few minutes the first time; kept on disk after."""
    if 'survey' in _interest and _interest['survey'][0] is db.recs:
        return _interest['survey'][1]
    path = None
    try:
        path = _idisk(db)
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _interest['survey'] = (db.recs, saved)
        return saved
    except Exception:
        pass
    import roomsurvey
    P, T = {}, {}
    names = {}
    poses = {}
    for rid in models(db, None, min_uses):
        s = survey(db, rid)
        kind = kind_of(rid)
        for d in s['dressings']:
            ck = d['cell']
            if ck not in names:
                names[ck] = (mapdata.cell_info(db, ck) or {}).get('name') or ck
            theme = roomsurvey.theme_of(names[ck])
            p = P.setdefault(d['purpose'], {'n': 0, 'with': 0, 'kinds': {}, 'items': {}, 'everyday': {}})
            t = T.setdefault(theme, {'n': 0, 'with': 0, 'vals': []})
            k = p['kinds'].setdefault(kind, [0, 0])
            p['n'] += 1
            t['n'] += 1
            k[0] += 1
            got = False
            for o in d['objects']:
                low = o['id'].lower()
                c = interesting(db, low)
                if c:
                    got = True
                    it = p['items'].setdefault(low, [c, 0, value_of(db, low)[1], 0.0, 0.0, 0.0])
                    it[1] += 1
                    t['vals'].append(it[2])
                    poses.setdefault(low, Counter())[(_wrap(o['rx']), _wrap(o['ry']), _wrap(o['rz']))] += 1
                elif o['kind'] in ('MISC', 'INGR', 'ALCH') and family(db, low):
                    p['everyday'][low] = p['everyday'].get(low, 0) + 1
            if got:
                p['with'] += 1
                t['with'] += 1
                k[1] += 1
    for p in P.values():
        for low, it in p['items'].items():
            (rx, ry, rz), _n = poses[low].most_common(1)[0]
            it[3], it[4], it[5] = rx, ry, rz
        p['items'] = {low: it for low, it in p['items'].items() if it[1] >= 2}
        p['everyday'] = dict(sorted(p['everyday'].items(), key=lambda kv: -kv[1])[:200])
    for t in T.values():
        v = sorted(t['vals'])
        t['cap'] = v[min(len(v) - 1, int(0.9 * len(v)))] if v else INTEREST_MIN_VALUE
        del t['vals']
    out = {'purpose': P, 'theme': T}
    _interest['survey'] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def interest_ready(db):
    """The whole-game survey when it's to hand (in memory or on disk); otherwise None, with the survey
    started in the background so it's there next time (a few minutes the first time)."""
    if 'survey' in _interest and _interest['survey'][0] is db.recs:
        return _interest['survey'][1]
    try:
        if os.path.isfile(_idisk(db)):
            return interest_survey(db)
    except Exception:
        return None
    t = _ithread.get('t')
    if t is None or not t.is_alive():
        import background
        _ithread['t'] = background.start('the interesting things on the game\'s shelves', lambda: interest_survey(db), task=('shelfsurvey', 'interest_survey', []))
    return None


def interest_rate(db, purpose, kind):
    """How often the game's dressings of this kind of furniture, in rooms like this, hold something
    interesting (0..1); None while the survey is still running."""
    s = interest_ready(db)
    if not s:
        return None
    p = s['purpose'].get(purpose)
    if p and p['kinds'].get(kind, [0, 0])[0] >= 20:
        n, w = p['kinds'][kind]
        return w / float(n)
    if p and p['n'] >= 20:
        return p['with'] / float(p['n'])
    n = sum(v['n'] for v in s['purpose'].values()) or 1
    return sum(v['with'] for v in s['purpose'].values()) / float(n)


def value_cap(db, theme):
    """What most interesting things in places of this theme stay under (nine in ten of the game's), or
    None while the survey is still running."""
    s = interest_ready(db)
    if not s:
        return None
    return s['theme'].get(theme, s['theme'].get('house', {})).get('cap', INTEREST_MIN_VALUE * 4)


def _fp_of(o):
    return (o['x'] + o['fp'][0], o['y'] + o['fp'][1], o['z'] + o['fp'][2], o['x'] + o['fp'][3], o['y'] + o['fp'][4], o['z'] + o['fp'][5])


def _fits_on(fb, levels, box, level, objs):
    """A thing with this box (in the furniture's frame) stands on this level inside the furniture's
    sides, under the next shelf, and clear of everything else on it."""
    if box[0] < fb[0] - EDGE or box[3] > fb[3] + EDGE or box[1] < fb[1] - EDGE or box[4] > fb[4] + EDGE:
        return False
    above = [lv for lv in levels if lv > level + 1]
    if above and box[5] > min(above) - 2:
        return False
    return not any(_overlap(box, _fp_of(p)) for p in objs)


def _relevel(db, bounds, o):
    """After a swap for a thing of nearly the same size: its bottom kept exactly where the old one's was
    (the models' bottoms differ by a unit or two, which would leave a book sunk or afloat)."""
    b, _t = _bounds_of(db, bounds, o['id'])
    if b and o.get('fp'):
        fp = box_turned(b, o['rx'], o['ry'], o['rz'], o['s'])
        o['z'] = round(o['z'] + o['fp'][2] - fp[2], 1)
        o['fp'] = fp


def _stand(db, bounds, rid, x, y, rx, ry, rz, level, s=1.0):
    """An object standing with its bottom on a level: {'id', 'kind', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's', 'fp', 'level'}."""
    b, tag = _bounds_of(db, bounds, rid)
    if not b:
        return None
    fp = box_turned(b, rx, ry, rz, s)
    return {'id': rid, 'kind': tag, 'x': round(x, 1), 'y': round(y, 1), 'z': round(level - fp[2], 1), 'rx': rx, 'ry': ry,
            'rz': rz, 's': s, 'fp': fp, 'level': level}


def _place_on(db, bounds, fb, levels, objs, rid, pose, rng, swap_kinds=('MISC', 'INGR', 'ALCH')):
    """Stand one more thing on a dressing, in its usual pose (rx, ry, rz relative to the furniture; a
    thing that stands upright may be spun any way, a tilted one keeps its whole pose, since the game turns
    about Z first and a different spin would tip it another way): in the place of an everyday thing of
    about its size (a mortar where a bowl stood), or in a gap along a row where the game left one; the
    object, or None when there is nowhere it fits."""
    b, _tag = _bounds_of(db, bounds, rid)
    if not b:
        return None
    rx, ry, rz0 = pose
    upright = abs(rx) < 0.05 and abs(ry) < 0.05
    ax, _length = _axis(fb)
    xy = ('x', 'y')[ax]
    # in the place of an everyday thing of about its size
    slots = [o for o in objs if o['kind'] in swap_kinds and category(db, o['id']) in ('misc', 'ingredient', 'potion') and family(db, o['id'])]
    rng.shuffle(slots)
    for o in slots[:4]:
        new = _stand(db, bounds, rid, o['x'], o['y'], rx, ry, o['rz'] if upright else rz0, o['level'])
        if not new:
            continue
        span_old = o['fp'][ax + 3] - o['fp'][ax]
        if new['fp'][ax + 3] - new['fp'][ax] > span_old + 12:
            continue
        rest = [p for p in objs if p is not o]
        if _fits_on(fb, levels, _fp_of(new), o['level'], rest):
            objs.remove(o)
            objs.append(new)
            return new
    # in a gap along a row: a long thing lies along the row, a round one is spun any way
    if not upright:
        rz = rz0
    elif family(db, rid) in ROUND:
        rz = rng.uniform(0, 2 * math.pi)
    else:
        w, d = b[3] - b[0], b[4] - b[1]
        along = (0.0 if (w >= d) == (ax == 0) else math.pi / 2) if max(w, d) > 1.5 * min(w, d) else rng.choice((0.0, math.pi / 2))
        rz = (along + rng.choice((0.0, math.pi)) + rng.uniform(-0.15, 0.15)) % (2 * math.pi)
    fp = box_turned(b, rx, ry, rz)
    need = fp[ax + 3] - fp[ax] + 6
    across = ('y', 'x')[ax]
    for level in rng.sample(levels, len(levels)):
        row = [o for o in objs if o['level'] == level]
        spans = sorted((o[xy] + o['fp'][ax], o[xy] + o['fp'][ax + 3]) for o in row)
        gaps, cur = [], fb[ax]
        for a, b2 in spans:
            if a - cur >= need:
                gaps.append((cur, a))
            cur = max(cur, b2)
        if fb[ax + 3] - cur >= need:
            gaps.append((cur, fb[ax + 3]))
        if not gaps:
            continue
        g0, g1 = rng.choice(gaps)
        half = (fp[ax + 3] - fp[ax]) / 2.0
        at = rng.uniform(g0 + half + 3, g1 - half - 3) - (fp[ax] + half)
        mid = (sum(o[across] for o in row) / len(row)) if row else (fb[1 - ax] + fb[4 - ax]) / 2.0
        mid = max(fb[1 - ax] - fp[1 - ax] + 2, min(fb[4 - ax] - fp[4 - ax] - 2, mid))
        x, y = (at, mid) if ax == 0 else (mid, at)
        new = _stand(db, bounds, rid, x, y, rx, ry, rz, level)
        if new and _fits_on(fb, levels, _fp_of(new), level, objs):
            objs.append(new)
            return new
    return None


def pick_interesting(db, purpose, theme, rng, min_uses=2, cap=None):
    """One interesting thing the game stands on shelves in rooms like this, in places like this: (id,
    category, (rx, ry, rz) its usual pose) or None. Picked by how often the game uses it, so the common ones come up most;
    never a quest's own thing (plain); never worth more than most things in places of this theme."""
    s = interest_ready(db)
    if not s:
        return None
    p = s['purpose'].get(purpose)
    items = {low: list(it) for low, it in p['items'].items()} if p and sum(it[1] for it in p['items'].values()) >= 40 else {}
    if not items:
        # (few seen in rooms of this purpose: what the game stands in any room of a home)
        for q_name, q in s['purpose'].items():
            if q_name in NOT_HOME and purpose not in NOT_HOME:
                continue
            for low, it in q['items'].items():
                if low in items:
                    items[low][1] += it[1]
                else:
                    items[low] = list(it)
    if cap is None:
        cap = value_cap(db, theme)
    arms = theme in ARMS_THEMES or purpose == 'shop'
    pool = [(low, it) for low, it in items.items() if it[2] <= cap and (arms or it[0] not in ARMS)]
    if not pool:
        return None
    total = sum(it[1] for _l, it in pool)
    for _try in range(8):
        r = rng.random() * total
        for low, it in pool:
            r -= it[1]
            if r <= 0:
                break
        if db.resolve_id(low) is not None and plain(db, low, min_uses):
            return low, it[0], (it[3], it[4], it[5])
    return None


def everyday_pool(db, purpose, rid=None):
    """The everyday things (bottles, cups, dishes, food, drink) the game stands on furniture in rooms
    like this, most used first; from this model's own dressings while the whole-game survey runs."""
    s = interest_ready(db)
    out = []
    if s:
        p = s['purpose'].get(purpose)
        if p and len(p['everyday']) >= 20:
            out = list(p['everyday'])
        else:
            seen = Counter()
            for q_name, q in s['purpose'].items():
                if q_name not in NOT_HOME or purpose in NOT_HOME:
                    seen.update(q['everyday'])
            out = [low for low, _n in seen.most_common(200)]
    if not out and rid:
        seen = Counter(o['id'].lower() for d in survey(db, rid)['dressings'] for o in d['objects'] if o['kind'] in ('MISC', 'INGR', 'ALCH'))
        out = [low for low, _n in seen.most_common(200)]
    return out


def dressing(db, rid, purpose, rng, books=(), min_uses=2, theme='house', used=None, cap=None, rate_k=1.0, max_value=None,
             band=None, budget=None, fill_books=False):
    """A dressing for a new piece of this furniture, from what the game puts on it: one of the game's own
    dressings (picked at random, so the common patterns come up most; from rooms of this purpose when the
    game has dressed it in a few of those; one not used in this house yet, when `used` is the house's set
    of dressings used so far), with variation: a book swapped for another of the same size that the game
    uses in places like this, a bottle or a dish for another of its kind and size, round things turned a
    little, the odd end piece dropped or another added, and, as often as the game's own shelves in rooms
    like this hold one, something interesting (a potion, a soul gem, a mortar, a gem, a scroll) stood
    where there is room, never two things in one spot. [{'id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's'}] in
    the furniture's frame, or None when the game never dresses this model (the caller then does what it
    did before). cap: nothing interesting dearer than this (None: the theme's own cap); rate_k: the
    game's rate of interesting things, times this; max_value: nothing at all dearer than this, everyday
    things included (a dear dish swapped for a plain one of its size, else dropped). band: the household's
    (Project Tamriel's tableware classes: nothing finer than a class above the band's, beyond a piece or two,
    and no ebonyware); budget: the home's book allowance, {'left', 'titles', 'stems'}, shared over the house
    (one to three common books outside the study, no second copy, no series). fill_books: a shelf of books,
    asked for by hand ("Fill with books"): only the game's dressings of the model that are mostly books, the
    fullest of a few draws, never bare, and no house allowance."""
    s = survey(db, rid)
    if not s['dressings']:
        return None
    nbooks = lambda d: sum(1 for o in d['objects'] if o['kind'] == 'BOOK')
    if fill_books:
        # (counting the books a copy keeps: a quest's own, placed once, are left out, so a shelf of them came
        # out bare)
        nbooks = lambda d: sum(1 for o in d['objects'] if o['kind'] == 'BOOK' and plain(db, o['id'], min_uses))
        # (the user: "IMPOSSIBLE to get a bookshelf with books on it ... I hit decorate like 10 times": a
        # house's allowance of three books and a draw among dishes and candles left it bare of books)
        bookish = sorted((d for d in s['dressings'] if d['objects']), key=lambda d: (nbooks(d) >= 0.6 * len(d['objects']), nbooks(d)), reverse=True)
        pool_b = [d for d in bookish if nbooks(d) >= 0.6 * len(d['objects'])] or bookish[:5]
        if not pool_b or not nbooks(max(pool_b, key=nbooks)):
            return None
        # (the fuller ones: a "shelf of books" with three on it was the user's complaint, not the answer)
        most = max(nbooks(d) for d in pool_b)
        full_b = [d for d in pool_b if nbooks(d) >= max(6, most // 2)]
        if len(full_b) >= 2:
            pool_b = full_b
        purpose, budget = 'study', None
    # (a cap given by the caller is a band's: nothing at all dearer than it, books included; the theme's
    # own cap, used when none is given, holds the interesting things only, as before)
    hard = max_value if max_value is not None else cap
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
    if fill_books:
        pool = pool_b
    elif rng.random() < max(0.0, empty_share - 0.3):
        return []
    # not the same one twice in a house (the pool is small: a house's shelves would all match)
    low = rid.lower()
    keys = {id(d): (low, i) for i, d in enumerate(s['dressings'])}
    if used is not None and not fill_books:
        fresh = [d for d in pool if keys[id(d)] not in used]
        if fresh:
            pool = fresh
    # (two picked, the fuller one kept most of the time: rows packed the way the game's best ones are;
    # a tall bookshelf in a study or a library never takes a dressing of under four things, and takes
    # the fullest of three draws two times in three: the game's library shelves carry 8 to 20 books,
    # and "three books on one shelf" was the user's verdict on a library)
    tall = kind_of(rid) == 'bookshelf' and len(s.get('levels') or []) >= 2
    if tall and purpose in ('study', 'shop', 'living') and not fill_books:
        full = [d for d in pool if len(d['objects']) >= 4]
        if len(full) >= 2:
            pool = full
    # (a wine rack is stocked the way the game stocks it: bottles lying in the lattice, as many as the
    # game's median rack holds; a dressing that is only a bottle or two stood on the rack's top is one of
    # the game's bare racks, and was the user's "two bottles, upright" in 2.3.3)
    rack = bool(WINERACK.search(rid.lower()))
    if rack:
        fri_ = db.resolve_id(rid)
        fb_ = mapdata.object_bounds(db, fri_) if fri_ is not None else None
        top_ = fb_[5] if fb_ else None
        racked = lambda d: [o for o in d['objects'] if top_ is None or o['level'] < top_ - 12]
        # (the game racks scrolls in the same lattice in its clerks' offices; a wine rack takes bottles)
        bottles = lambda d: sum(1 for o in racked(d) if o['kind'] != 'BOOK') >= 0.6 * len(racked(d))
        sizes_ = sorted(len(racked(d)) for d in s['dressings'] if racked(d))
        gmed_ = sizes_[len(sizes_) // 2] if sizes_ else 0
        full = [d for d in pool if len(racked(d)) >= max(3, gmed_) and bottles(d)]
        if len(full) < 2:
            full = [d for d in s['dressings'] if len(racked(d)) >= max(3, gmed_) and bottles(d)]
        if len(full) >= 2:
            pool = full
            tall = True
    draws = 3 if tall else 2
    picks = [rng.choice(pool) for _ in range(draws)]
    chosen = max(picks, key=lambda d: len(d['objects'])) if rng.random() < (0.67 if tall else 0.5) else picks[0]
    if fill_books:
        # (the most books of three draws: a full shelf, but not always the very same one)
        chosen = max([rng.choice(pool) for _ in range(3)], key=nbooks)
    elif tall:
        # (and at least as full as the game's median dressing of the model, one time in two)
        sizes = sorted(len(d['objects']) for d in s['dressings'])
        gmed = sizes[len(sizes) // 2] if sizes else 0
        if len(chosen['objects']) < gmed and rng.random() < 0.5:
            chosen = max(chosen, rng.choice(pool), key=lambda d: len(d['objects']))
    if used is not None:
        used.add(keys[id(chosen)])
    bounds = {}
    objs = []
    for o in chosen['objects']:
        # (nothing the game placed only once: a quest's own book or note stays where it is)
        if not plain(db, o['id'], min_uses):
            continue
        objs.append(dict(o))
    # a book swapped now and then for another of the same size: from the place's own palette, and from
    # every everyday book the game leaves about, so a shelf isn't six copies of the one title the game's
    # own shelf happened to hold (a title already on the shelf is always swapped)
    same = {}
    bpool = [b for b in (books or []) if not interesting(db, b)] + [b for b in _everyday_books(db, min_uses) if b not in (books or [])]
    if hard is not None:
        bpool = [b for b in bpool if value_of(db, b)[1] <= hard]
    titles = set()
    for o in objs:
        if o['kind'] != 'BOOK':
            continue
        key = o['id'].lower()
        again = key in titles
        titles.add(key)
        if not again and rng.random() > 0.6:
            continue
        b0, _t = _bounds_of(db, bounds, o['id'])
        if not b0:
            continue
        if key not in same:
            # (the same size side for side, so the model's height runs the same way: some of the game's
            # books are modelled with their height along X, and would stand turned a quarter round)
            same[key] = [bk for bk in bpool if bk.lower() != key
                         and (lambda bb: bb and _same_size(bb, b0) and _axes(bb) == _axes(b0))(_bounds_of(db, bounds, bk)[0])]
        fresh = [bk for bk in same[key] if bk.lower() not in titles] or same[key]
        if fresh:
            o['id'] = rng.choice(fresh)
            titles.add(o['id'].lower())
            _relevel(db, bounds, o)
    # (and books from the palette may be a quest's too)
    objs = [o for o in objs if o['kind'] != 'BOOK' or plain(db, o['id'], min_uses)]
    fri = db.resolve_id(rid)
    fb = mapdata.object_bounds(db, fri)
    ax = _axis(fb)[0] if fb else 0
    # the everyday things varied too: a bottle, a cup, a dish, a loaf swapped now and then for another of
    # its kind and size that the game stands in rooms like this (modelled the same way round, so it
    # stands as the old one did), and round things turned a little, so two shelves from the one game
    # dressing don't match piece for piece
    pool_e = []
    same_e = {}

    import wealthsurvey as _ws
    ware_ok = (lambda e: _ws.ware_over(band, _ws.ware_class(e)) == 0) if band else (lambda e: True)

    def swap_everyday(o, fam, dear=False, limit=None, to=None):
        """o swapped for another everyday thing of its family and size (its value about the same, or
        anything plain when the old one was too dear for the place; never over `limit`): True when done.
        to: that very thing (the other copies of a set swapped as the first one was)."""
        key = o['id'].lower()
        b0, _t = _bounds_of(db, bounds, o['id'])
        if not b0 or not fb:
            return False
        if to is not None:
            e = to
        else:
            if not pool_e:
                pool_e.extend(everyday_pool(db, purpose, rid))
            ck = (key, dear, limit)
            if ck not in same_e:
                v0 = value_of(db, key)[1]
                same_e[ck] = [e for e in pool_e if e != key and family(db, e) == fam and not interesting(db, e)
                              and (lambda bb: bb and _same_size(bb, b0, 3.0) and _axes(bb) == _axes(b0))(_bounds_of(db, bounds, e)[0])
                              and (dear or max(v0, value_of(db, e)[1]) <= 15 or 0.4 <= (value_of(db, e)[1] or 1) / float(v0 or 1) <= 2.5)
                              and (limit is None or value_of(db, e)[1] <= limit)
                              and ware_ok(e)
                              and plain(db, e, min_uses)]
            if not same_e[ck]:
                return False
            e = rng.choice(same_e[ck])
        new = _stand(db, bounds, e, o['x'], o['y'], o['rx'], o['ry'], o['rz'], o['level'], o['s'])
        if new and _fits_on(fb, s['levels'], _fp_of(new), o['level'], [p for p in objs if p is not o]):
            o.update(new)
            return True
        return False

    # nothing dearer than most things in places of this sort (the game's own dressing of a rich mage's
    # study may hold an ebony platter: in a plain house that becomes a plain one of its size, or goes)
    if cap is None:
        cap = value_cap(db, theme)
    if cap is not None:
        for o in list(objs):
            if interesting(db, o['id']) and value_of(db, o['id'])[1] > cap:
                fam = family(db, o['id'])
                if not (fam and swap_everyday(o, fam, dear=True, limit=max_value)):
                    objs.remove(o)
    if hard is not None:
        # (nothing worth more than this at all: the silver platter the game laid becomes a plain one of
        # its size, or goes; a dear book another of its size from the pool, or goes)
        for o in list(objs):
            if value_of(db, o['id'])[1] > hard:
                if o['kind'] == 'BOOK':
                    b0, _t = _bounds_of(db, bounds, o['id'])
                    fresh = [bk for bk in bpool if bk.lower() not in titles and b0
                             and (lambda bb: bb and _same_size(bb, b0) and _axes(bb) == _axes(b0))(_bounds_of(db, bounds, bk)[0])]
                    if fresh:
                        o['id'] = rng.choice(fresh)
                        titles.add(o['id'].lower())
                        _relevel(db, bounds, o)
                        continue
                    objs.remove(o)
                    continue
                fam = family(db, o['id'])
                if not (fam and swap_everyday(o, fam, dear=True, limit=hard)):
                    objs.remove(o)
    # tableware above the household's station (Project Tamriel's classes): a piece or two of finer ware
    # may stay in a plain house, the rest become plain ones of their size, or go; ebonyware always goes
    if band:
        fine_kept = 0
        for o in list(objs):
            over = _ws.ware_over(band, _ws.ware_class(o['id'])) if o['kind'] == 'MISC' else 0
            if not over:
                continue
            if over < 9 and fine_kept < 1 and rng.random() < 0.5:
                fine_kept += 1
                continue
            fam = family(db, o['id'])
            if not (fam and swap_everyday(o, fam, dear=True, limit=max_value)):
                objs.remove(o)
    # the home's book allowance: outside the study and the shop, one to three common books in the house,
    # never a second copy of a title nor another volume of a series already about (books are content)
    if budget is not None and purpose not in ('study', 'shop'):
        for o in list(objs):
            if o['kind'] != 'BOOK':
                continue
            key = o['id'].lower()
            stem = _stem(key)
            if budget['left'] <= 0 or key in budget['titles'] or (stem and stem in budget['stems']):
                b0, _t = _bounds_of(db, bounds, o['id'])
                fresh = [bk for bk in bpool if bk.lower() not in budget['titles'] and bk.lower() not in titles and b0
                         and not (_stem(bk.lower()) and _stem(bk.lower()) in budget['stems'])
                         and (lambda bb: bb and _same_size(bb, b0) and _axes(bb) == _axes(b0))(_bounds_of(db, bounds, bk)[0])]
                if budget['left'] > 0 and fresh:
                    o['id'] = rng.choice(fresh)
                    _relevel(db, bounds, o)
                    key, stem = o['id'].lower(), _stem(o['id'].lower())
                else:
                    objs.remove(o)
                    continue
            budget['left'] -= 1
            budget['titles'].add(key)
            if stem:
                budget['stems'].add(stem)
    # (a set is swapped as a set: the game's three plates of one model on a table become three of another
    # model, never three odd ones; the game's tables of four things or more repeat a model, 0.80 distinct
    # models a thing, where a swap per thing made every table 1.00. pt-showcases-study.md, T5)
    set_to = {}
    for o in objs:
        if o['kind'] not in ('MISC', 'INGR', 'ALCH') or interesting(db, o['id']):
            continue
        fam = family(db, o['id'])
        if not fam or fam in ('paper', 'cloth'):
            continue
        key0 = o['id'].lower()
        if key0 in set_to:
            if set_to[key0]:
                swap_everyday(o, fam, to=set_to[key0])
        elif rng.random() < 0.35 and swap_everyday(o, fam):
            set_to[key0] = o['id']
        else:
            set_to[key0] = None
        b0, _t = _bounds_of(db, bounds, o['id'])
        if not b0:
            continue
        if fam in ROUND and abs(o['rx']) < 0.05 and abs(o['ry']) < 0.05 and rng.random() < 0.7:
            rz = (o['rz'] + rng.uniform(-0.6, 0.6)) % (2 * math.pi)
            fp = box_turned(b0, o['rx'], o['ry'], rz, o['s'])
            turned = dict(o, rz=round(rz, 3), fp=fp)
            if _fits_on(fb, s['levels'], _fp_of(turned), o['level'], [p for p in objs if p is not o]):
                o.update(turned)
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
            # (the end pieces borrowed from another dressing keep to the caps too: a gold ingot from a
            # rich study's shelf came into plain houses this way before)
            extra = [o for o in other['objects'] if o['kind'] != 'BOOK' and plain(db, o['id'], min_uses)
                     and not (cap is not None and interesting(db, o['id']) and value_of(db, o['id'])[1] > cap)
                     and not (hard is not None and value_of(db, o['id'])[1] > hard)]
            rng.shuffle(extra)
            for o in extra[:3]:
                box = (o['x'] + o['fp'][0], o['y'] + o['fp'][1], o['z'] + o['fp'][2], o['x'] + o['fp'][3], o['y'] + o['fp'][4], o['z'] + o['fp'][5])
                if not any(_overlap(box, (p['x'] + p['fp'][0], p['y'] + p['fp'][1], p['z'] + p['fp'][2],
                                          p['x'] + p['fp'][3], p['y'] + p['fp'][4], p['z'] + p['fp'][5])) for p in objs):
                    objs.append(dict(o))
                    break
    # something interesting, as often as the game's own shelves in rooms like this hold one and no more:
    # the dressing copied may hold one already (the game's rate, less the rare things plain() leaves
    # out), so one is stood only when it doesn't, at the rate that makes up the difference
    if fb and objs and not any(interesting(db, o['id']) for o in objs):
        rate = interest_rate(db, purpose, kind_of(rid) or 'table')
        if rate and rate_k > 0:
            # (a poor house gets them at a fraction of the game's rate, a rich one more often: rate_k)
            rate = min(0.95, rate * rate_k)
            have = sum(1 for d in pool if any(interesting(db, o['id']) and plain(db, o['id'], min_uses) for o in d['objects'])) / float(len(pool))
            if rng.random() < max(0.0, rate - have) / max(0.05, 1.0 - have):
                it = pick_interesting(db, purpose, theme, rng, min_uses, cap=cap)
                if it:
                    iid, cat, pose = it
                    if cat == 'skillbook':
                        # (a skill book goes where a book of its size stands, the same way round)
                        bb = _bounds_of(db, bounds, iid)[0]
                        slots = [o for o in objs if o['kind'] == 'BOOK' and bb
                                 and (lambda b0: b0 and _same_size(bb, b0) and _axes(bb) == _axes(b0))(_bounds_of(db, bounds, o['id'])[0])]
                        if slots:
                            o = rng.choice(slots)
                            o['id'] = iid
                            _relevel(db, bounds, o)
                    else:
                        _place_on(db, bounds, fb, s['levels'], objs, iid, pose, rng)
    if fb and tall:
        # a tall shelf is never thinner than the game's median dressing of the model, whatever the
        # household's level (the user: "is this the furnishing level?"; the level lowers what the things
        # are worth, not how many there are): topped up with things borrowed from the model's other
        # dressings at their own spots, under the caps, where they fit
        sizes = sorted(len(d['objects']) for d in s['dressings'])
        gmed = sizes[len(sizes) // 2] if sizes else 0
        donors = [d for d in s['dressings'] if d is not chosen and d['objects']]
        tries = 0
        while len(objs) < gmed and tries < 60 and donors:
            tries += 1
            o = dict(rng.choice(rng.choice(donors)['objects']))
            if not plain(db, o['id'], min_uses) or 'fp' not in o:
                continue
            v_ = value_of(db, o['id'])[1]
            if (hard is not None and v_ > hard) or (cap is not None and interesting(db, o['id']) and v_ > cap):
                if o['kind'] != 'BOOK':
                    continue
                b0, _t = _bounds_of(db, bounds, o['id'])
                fresh = [bk for bk in bpool if bk.lower() not in titles and b0
                         and (lambda bb: bb and _same_size(bb, b0) and _axes(bb) == _axes(b0))(_bounds_of(db, bounds, bk)[0])]
                if not fresh:
                    continue
                o['id'] = rng.choice(fresh)
                _relevel(db, bounds, o)
            if o['kind'] == 'BOOK' and o['id'].lower() in titles:
                continue
            if _fits_on(fb, s['levels'], _fp_of(o), o['level'], objs):
                objs.append(o)
                if o['kind'] == 'BOOK':
                    titles.add(o['id'].lower())
    if fb:
        shelf_sense(db, bounds, fb, s['levels'], objs, ax)
    return [{k: o[k] for k in ('id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's')} for o in objs]


def board_over(own, x, y, bottom):
    """The clear height over a spot of a piece of furniture (world coordinates; own: the piece's own
    geometry, seethrough.overlay), or None when nothing is over it. A surface within 5 of the bottom is the
    board the thing stands in (the user's hut: books sunk a unit or two into their board, whose top face
    read as "2 units of room") and is looked past."""
    z = bottom + 0.5
    for _ in range(4):
        h = own.nearest_any((x, y, z), (0.0, 0.0, 1.0), 800)
        if h is None:
            return None
        top = z + h[0]
        if top - bottom >= 5.0:
            return top - bottom
        z = top + 0.5
    return None


def fit_books(db, objs, fb, headroom, books, rng, max_value=None):
    """Every book on a dressing fits under the board above it (the user's "too large books" on a shelf, the
    tall Tamriel Data tome standing through the shelf over it). The dressing's levels only know the boards
    the game's own dressings of the model put something on, so a board the game left bare had no say;
    here the clear height over each book is measured by the caller from the furniture's own mesh
    (headroom(x, y, bottom) in the furniture's frame: the height free over that spot, or None when nothing
    is over it). A book that doesn't fit is, in turn:
    - swapped for a shorter book of its thickness that the game leaves about, the same way round, standing
      where it stood (the tallest that fits, so the row's tops stay even);
    - laid down flat on its cover, spine out, as the game lays its big books: in its own spot or slid along
      the row to a free one, or on another book laid flat there (a pile, never higher than the board allows);
    - left out.
    objs: the dressing ({'id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's'} in the furniture's frame); returns it fitted."""
    bounds = {}
    ax = _axis(fb)[0]

    def kind(o):
        ri = db.resolve_id(o['id'])
        return db.recs[ri][0] if ri is not None else ''

    def box(o):
        b, _t = _bounds_of(db, bounds, o['id'])
        if not b:
            return None
        fp = box_turned(b, o['rx'], o['ry'], o['rz'], o['s'])
        return (o['x'] + fp[0], o['y'] + fp[1], o['z'] + fp[2], o['x'] + fp[3], o['y'] + fp[4], o['z'] + fp[5])

    live = {id(o): box(o) for o in objs}
    out, flats = [], []
    pool = None

    def clear(bx, skip):
        if bx[0] < fb[0] - EDGE or bx[3] > fb[3] + EDGE or bx[1] < fb[1] - EDGE or bx[4] > fb[4] + EDGE:
            return False
        return not any(_overlap(bx, b2) for k2, b2 in live.items() if k2 not in skip and b2)

    for o in objs:
        bx = live.get(id(o))
        if not bx or kind(o) != 'BOOK':
            out.append(o)
            continue
        cx, cy = (bx[0] + bx[3]) / 2.0, (bx[1] + bx[4]) / 2.0
        room = headroom(cx, cy, bx[2])
        if room is None or bx[5] - bx[2] <= room - 1.5:
            out.append(o)
            continue
        b0, _t = _bounds_of(db, bounds, o['id'])
        # 1. a shorter book of its thickness, the same way round
        if pool is None:
            pool = [bk for bk in list(books or []) + list(_everyday_books(db)) if not interesting(db, bk)]
            if max_value is not None:
                pool = [bk for bk in pool if value_of(db, bk)[1] <= max_value]
        dims0 = sorted((b0[3] - b0[0], b0[4] - b0[1], b0[5] - b0[2]))
        fits = []
        for bk in pool:
            bb, _t2 = _bounds_of(db, bounds, bk)
            if not bb or _axes(bb) != _axes(b0):
                continue
            dims = sorted((bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]))
            if abs(dims[0] - dims0[0]) > 3 or dims[1] > dims0[1] + 4:
                continue
            fp2 = box_turned(bb, o['rx'], o['ry'], o['rz'], o['s'])
            if fp2[5] - fp2[2] > room - 2:
                continue
            o2 = dict(o, id=bk, z=round(o['z'] + (bx[2] - o['z']) - fp2[2], 1))
            b2 = box(o2)
            if b2 and clear(b2, {id(o)}):
                fits.append((fp2[5] - fp2[2], o2, b2))
        if fits:
            top = max(h for h, _o, _b in fits)
            near = [f for f in fits if f[0] >= top - 6]
            _h, o2, b2 = rng.choice(near)
            live[id(o)] = b2
            out.append(o2)
            continue
        # 2. laid down flat on its cover, spine out (its height along the row), or across when the row has no room
        best = None
        for rx_ in (0.0, math.pi / 2, -math.pi / 2):
            for ry_ in (0.0, math.pi / 2, -math.pi / 2):
                for rz_ in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
                    fp = box_turned(b0, rx_, ry_, rz_, o['s'])
                    hz = fp[5] - fp[2]
                    if hz > dims0[0] + 0.5:
                        continue                 # (not lying on its cover)
                    along = (fp[ax + 3] - fp[ax]) >= (fp[4 - ax] - fp[1 - ax])
                    pref = (0 if along else 1, abs(rx_) + abs(ry_))
                    if best is None or pref < best[0]:
                        best = (pref, (rx_, ry_, rz_), fp)
                    elif pref == best[0] and rng.random() < 0.3:
                        best = (pref, (rx_, ry_, rz_), fp)
        placed = False
        if best:
            (rx_, ry_, rz_), fp = best[1], best[2]
            rz_ = (rz_ + rng.uniform(-0.08, 0.08)) % (2 * math.pi)
            fp = box_turned(b0, rx_, ry_, rz_, o['s'])
            hz = fp[5] - fp[2]
            steps = [0] + [s_ * k for k in range(1, 9) for s_ in (6, -6)]
            for dxy in steps:
                ox_, oy_ = (cx + dxy, cy) if ax == 0 else (cx, cy + dxy)
                # (on the board, or on a book laid flat there already: a pile of two or three)
                for under in [None] + [f for f in flats if f[0] <= ox_ <= f[3] and f[1] <= oy_ <= f[4]]:
                    base = bx[2] if under is None else under[5]
                    r_ = headroom(ox_, oy_, bx[2])
                    if r_ is not None and (base - bx[2]) + hz > r_ - 1.5:
                        continue
                    o2 = dict(o, x=round(ox_ - (fp[0] + fp[3]) / 2.0, 1), y=round(oy_ - (fp[1] + fp[4]) / 2.0, 1),
                              z=round(base - fp[2], 1), rx=rx_, ry=ry_, rz=round(rz_, 3))
                    b2 = box(o2)
                    skip = {id(o)}
                    if under is not None:
                        skip |= {k2 for k2, bb2 in live.items() if bb2 == under}
                    if b2 and clear(b2, skip):
                        live[id(o)] = b2
                        flats.append(b2)
                        out.append(o2)
                        placed = True
                        break
                if placed:
                    break
        if not placed:
            live[id(o)] = None                   # 3. left out
    return out


_SERIES = re.compile(r'^(.*?)[ _]?(\d+|i{1,3}|iv|v)$')


def _stem(low):
    """A book's series stem (bk_briefhistoryempire1 → bk_briefhistoryempire), or None."""
    m = _SERIES.match(low)
    return m.group(1) if m and len(m.group(1)) >= 6 else None


BOOKEND = re.compile(r'bookend')


def book_pose(db, bounds, o):
    """How a book stands: ('upright' | 'flat' | 'lean', lean direction along the row (+1/-1/0)). The
    model's height axis, turned as the book is: straight up is upright, lying down is flat, between is
    a lean (towards the side its top tips to)."""
    b, _t = _bounds_of(db, bounds, o['id'])
    if not b:
        return 'upright', 0
    h = _axes(b)[2]
    R = _turned(o['rx'], o['ry'], o['rz'])
    vx, vy, vz = R[0][h], R[1][h], R[2][h]
    if abs(vz) >= 0.985:               # (within ten degrees of straight up; a tilt of fifteen is a lean)
        return 'upright', 0
    if abs(vz) <= 0.3:
        return 'flat', 0
    return 'lean', (vx, vy)


def shelf_sense(db, bounds, fb, levels, objs, ax):
    """What a shelf's row has to make sense after the copying, swapping and dropping above (from the
    user's library: "books tilted as if leaning, with nothing beside them", "a pair of bookends and no
    books between them", "a single book lying flat in a bay"): a leaning book stands upright (like its
    nearest upright neighbour, else it goes) unless something stands on the side it leans to within a
    hand's width; a bookend goes unless three upright books stand in a run beside it; a flat book goes
    unless it lies on a stack (another flat thing right under or over it) or against an upright run."""
    xy = ('x', 'y')[ax]
    lo, hi = ax, ax + 3
    rows = {}
    for o in objs:
        rows.setdefault(o['level'], []).append(o)
    gone = []
    for lv, row in rows.items():
        poses = {id(o): (book_pose(db, bounds, o) if o['kind'] == 'BOOK' else ('other', 0)) for o in row}

        def beside(o, side, gap=4.0):
            """Something on this side of o along the row (its footprint within gap of o's edge)."""
            a = _fp_of(o)
            for p in row:
                if p is o or p in gone:
                    continue
                q = _fp_of(p)
                if q[2] > a[5] - 2 or q[5] < a[2] + 2:
                    continue                 # (not at this height)
                # (the neighbour reaches past o's edge on that side, and starts no farther than gap beyond
                # it; the game's leaning books overlap their neighbours a little)
                if side > 0 and q[hi] > a[hi] and q[lo] - a[hi] <= gap:
                    return p
                if side < 0 and q[lo] < a[lo] and a[lo] - q[hi] <= gap:
                    return p
            return None

        def run_beside(o, side):
            """How many upright books stand in a run from o's side."""
            n, cur = 0, o
            while True:
                nxt = beside(cur, side, gap=8.0)
                if nxt is None or poses[id(nxt)][0] != 'upright':
                    return n
                n += 1
                cur = nxt
        # leaning books first (an upright neighbour is what a lean needs)
        for o in row:
            kind, d = poses[id(o)]
            if kind != 'lean':
                continue
            # (the side its top tips to along the row, from the book's turned geometry; a book tipped
            # back across the row leans on the shelf's back board, as the game's do: left as it is)
            if abs(d[ax]) < 0.15:
                continue
            side = 1 if (d[ax] > 0) else -1
            if beside(o, side) is not None:
                continue
            up = [p for p in row if p not in gone and poses[id(p)][0] == 'upright' and p is not o]
            if up:
                near = min(up, key=lambda p: abs(p[xy] - o[xy]))
                new = _stand(db, bounds, o['id'], o['x'], o['y'], near['rx'], near['ry'], near['rz'], lv, o['s'])
                if new and _fits_on(fb, levels, _fp_of(new), lv, [p for p in objs if p is not o and p not in gone]):
                    o.update(new)
                    poses[id(o)] = ('upright', 0)
                    continue
            gone.append(o)
        # bookends: only beside a run of three upright books
        for o in row:
            if o in gone or not BOOKEND.search(o['id'].lower()):
                continue
            if max(run_beside(o, 1), run_beside(o, -1)) < 3:
                gone.append(o)
        # flat books: on a stack, or against an upright run; never alone in a bay
        for o in row:
            if o in gone or poses[id(o)][0] != 'flat':
                continue
            a = _fp_of(o)
            stacked = any(p is not o and p not in gone and abs(p['x'] - o['x']) < 12 and abs(p['y'] - o['y']) < 12
                          and (abs(_fp_of(p)[2] - a[5]) < 4 or abs(a[2] - _fp_of(p)[5]) < 4) for p in row)
            against = any(poses[id(p)][0] == 'upright' for p in (beside(o, 1), beside(o, -1)) if p is not None)
            if not stacked and not against:
                gone.append(o)
    for o in gone:
        if o in objs:
            objs.remove(o)
    LAST_SENSE['dropped'] += len(gone)
    return objs


LAST_SENSE = Counter()      # (for the lab: how many things the shelf-sense pass took off)
