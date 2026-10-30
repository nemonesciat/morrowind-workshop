"""The piece-to-piece adjacency survey: which building piece the game's own interiors stand against which,
on which side, at what offset and turn, and how often; learnt once per kit with the other surveys
(learning.py), kept in the cache folder under the load order's signature.

The joint survey (joints.py) reads the floor tiles of a kit and what stands at each tile's edge. This
survey is wider and coarser: every building piece of a place (floor pieces, hall segments, domes, ramps,
stairs, caps, bridges, railings, whatever the game joins to the kit), and for each piece the pieces
standing against each of its six faces, in the piece's own frame. From it come the Extend mode's candidates
("the game joins this here 7 times in 10"), the open edges of a built place (a face of a piece with nothing
against it, which the game nearly always fills), and the patterns (a run of hall segments, a piece with
its ring of neighbours), mined from the chains.

A piece's frame: its model's box, turned by its own rz. A neighbour B of A is recorded as (B's id, B's
origin in A's frame rounded to 8 units, B's turn relative to A's in 15-degree steps), on the face of A's
box that B's box lies beyond (E +X, W -X, N +Y, S -Y, U above, D below). Measured 2026-10-22: 77 kits
in about 40 s."""
import json
import math
import os
import re
from collections import Counter

import kits
import mapdata
from mapdata import ref_info

VERSION = 4
PLACES = 40
TOL = 40                      # a face is "against" another within this many units (pieces overlap by their trim)
MIN_OVERLAP = 64              # ... and the boxes overlap along the face by at least this much
SMALL = re.compile(r'addon|skirt|window|jamb|frame|pillar|column|post|partition|marker|rug|banner|light|trim|fireplace|hearth|forge|counter|shelf|bench|pew')
MIN_DIM = 96                  # smaller pieces are the joint survey's business (posts, addons) or trim
SIDES6 = ('E', 'W', 'N', 'S', 'U', 'D')
SIDE_WORDS = {'E': 'east', 'W': 'west', 'N': 'north', 'S': 'south', 'U': 'top', 'D': 'underside'}

_cache = {}
_bounds = {}
_hall_roots = {}


def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'adjacency_%s_v%d.json' % (taste.sig(db), VERSION))


def _box(db, rid):
    low = rid.lower()
    if low not in _bounds:
        ri = db.resolve_id(rid)
        _bounds[low] = (ri, mapdata.object_bounds(db, ri) if ri is not None else None)
    return _bounds[low]


def is_piece(db, rid, tag=None, b=None):
    """Whether a placed thing is a building piece this survey reads: architecture (mapdata's sense) of
    some size, not the small loose pieces the joint survey knows."""
    low = rid.lower()
    if low.startswith(('furn_', 'flora_', 'ex_', 'light_', 'act_')) or SMALL.search(low):
        return False
    if tag is None or b is None:
        ri, b = _box(db, rid)
        if ri is None or not b:
            return False
        tag = db.recs[ri][0]
    if not mapdata.is_architecture(tag, rid, b):
        return False
    return max(b[3] - b[0], b[4] - b[1]) >= MIN_DIM and (b[5] - b[2]) >= 40


# ------------------------------------------------------------------ frames
def to_local(A, wx, wy):
    """A world point in A's frame (A turned clockwise by its rz, as the game turns things)."""
    dx, dy = wx - A['x'], wy - A['y']
    c, s = math.cos(A['rz']), math.sin(A['rz'])
    return dx * c - dy * s, dx * s + dy * c


def to_world(A, lx, ly):
    c, s = math.cos(A['rz']), math.sin(A['rz'])
    return A['x'] + lx * c + ly * s, A['y'] - lx * s + ly * c


def local_box(A, B):
    """B's box as an axis-aligned box in A's frame: (x0, y0, z0, x1, y1, z1)."""
    b = B['b']
    s = B['s']
    rel = B['rz'] - A['rz']
    c, sn = math.cos(rel), math.sin(rel)
    ox, oy = to_local(A, B['x'], B['y'])
    xs, ys = [], []
    for lx in (b[0] * s, b[3] * s):
        for ly in (b[1] * s, b[4] * s):
            xs.append(ox + lx * c + ly * sn)
            ys.append(oy - lx * sn + ly * c)
    return (min(xs), min(ys), B['z'] + b[2] * s, max(xs), max(ys), B['z'] + b[5] * s)


def own_box(A):
    b, s = A['b'], A['s']
    return (b[0] * s, b[1] * s, A['z'] + b[2] * s, b[3] * s, b[4] * s, A['z'] + b[5] * s)


def side_of(A, B):
    """The face of A that B stands against: one of SIDES6, or None (apart, or on the same spot)."""
    a = own_box(A)
    L = local_box(A, B)
    ox = min(a[3], L[3]) - max(a[0], L[0])
    oy = min(a[4], L[4]) - max(a[1], L[1])
    oz = min(a[5], L[5]) - max(a[2], L[2])
    gaps = {'E': L[0] - a[3], 'W': a[0] - L[3], 'N': L[1] - a[4], 'S': a[1] - L[4], 'U': L[2] - a[5], 'D': a[2] - L[5]}
    best = None
    for s_ in SIDES6:
        g = gaps[s_]
        if g > TOL or g < -TOL:
            continue
        if s_ in ('E', 'W') and (oy < MIN_OVERLAP or oz < MIN_OVERLAP):
            continue
        if s_ in ('N', 'S') and (ox < MIN_OVERLAP or oz < MIN_OVERLAP):
            continue
        if s_ in ('U', 'D') and (ox < MIN_OVERLAP or oy < MIN_OVERLAP):
            continue
        # (the face the boxes are nearest to meeting at: a piece beyond a corner touches two faces by the
        # tolerance; the one with the bigger overlap along it wins)
        along = oy if s_ in ('E', 'W') else ox if s_ in ('N', 'S') else min(ox, oy)
        score = (-along, abs(g))
        if best is None or score < best[0]:
            best = (score, s_)
    return best[1] if best else None


def overlaps(A, B, slack=24):
    """Whether two pieces' boxes run into each other by more than a trim's worth."""
    a = own_box(A)
    L = local_box(A, B)
    ox = min(a[3], L[3]) - max(a[0], L[0])
    oy = min(a[4], L[4]) - max(a[1], L[1])
    oz = min(a[5], L[5]) - max(a[2], L[2])
    return ox > slack and oy > slack and oz > slack


def relation(A, B):
    """B in A's frame: (B id, x, y, z, turn in degrees)."""
    lx, ly = to_local(A, B['x'], B['y'])
    dq = round(math.degrees((B['rz'] - A['rz']) % (2 * math.pi)) / 15.0) * 15 % 360
    return (B['id'], int(round(lx / 8.0)) * 8, int(round(ly / 8.0)) * 8, int(round((B['z'] - A['z']) / 8.0)) * 8, int(dq))


def placed(A, rel):
    """A piece standing in the relation to A: {'id', 'p': [x, y, z, 0, 0, rz]}."""
    bid, lx, ly, lz, dq = rel
    wx, wy = to_world(A, lx, ly)
    return {'id': bid, 'p': [round(wx, 2), round(wy, 2), round(A['z'] + lz, 2), 0, 0, round((A['rz'] + math.radians(dq)) % (2 * math.pi), 5)]}


# ------------------------------------------------------------------ reading a place
def read_pieces(db, cell_key, m=None):
    """The building pieces of a place: [{ref, id, x, y, z, rz, s, b, ri}]."""
    out = []
    if m is None:
        refs, _h = db.cell_refs(cell_key)
        items = []
        for rk, ref in refs.items():
            rid, pos, scale, dead = ref_info(ref['subs'])
            if not dead and pos:
                items.append((rk, rid, pos, scale or 1.0))
    else:
        items = [(r['k'], r['id'], r['p'], r['s'] or 1.0) for r in m['refs'] if r['type'] in ('STAT', 'ACTI')]
    for rk, rid, pos, scale in items:
        ri, b = _box(db, rid)
        if ri is None or not b or not is_piece(db, rid, db.recs[ri][0], b):
            continue
        if abs(pos[3]) > 0.05 or abs(pos[4]) > 0.05:
            continue                                 # (tilted: not a building piece as the game lays them)
        out.append({'ref': rk, 'id': rid.lower(), 'x': pos[0], 'y': pos[1], 'z': pos[2], 'rz': pos[5] % (2 * math.pi),
                    's': scale, 'b': b, 'ri': ri})
    return out


def neighbours(pieces, A):
    """[(side, B)] for every piece standing against a face of A."""
    out = []
    for B in pieces:
        if B is A or B['ref'] == A['ref']:
            continue
        if abs(B['x'] - A['x']) > 1600 or abs(B['y'] - A['y']) > 1600 or abs(B['z'] - A['z']) > 1200:
            continue
        s_ = side_of(A, B)
        if s_:
            out.append((s_, B))
    return out


# ------------------------------------------------------------------ the survey
def _cells_for(db, prefix, limit=PLACES):
    import joints
    return joints._cells_for(db, prefix, limit)


def survey_kit(db, prefix, limit=PLACES):
    """One kit: {'places', 'n': {id: occurrences}, 'adj': {id: {side: {'n', 'c': {rel_str: n}}}},
    'runs': {id: {side: {'step': [x, y, z], 'lengths': {n: count}}}}, 'rings': [{'id', 'members', 'n'}]}."""
    n_of = Counter()
    adj = {}
    rings = Counter()
    runs = {}
    alts = {}
    places = 0
    for ck in _cells_for(db, prefix, limit):
        try:
            pieces = read_pieces(db, ck)
        except Exception:
            continue
        own = [p for p in pieces if kits.kit_prefix(p['id']) == prefix]
        if len(own) < 3:
            continue
        places += 1
        nb_of = {}
        for A in pieces:
            nbs = neighbours(pieces, A)
            nb_of[A['ref']] = nbs
            n_of[A['id']] += 1
            by_side = {}
            for s_, B in nbs:
                by_side.setdefault(s_, []).append(B)
            rec = adj.setdefault(A['id'], {})
            for s_, lst in by_side.items():
                r = rec.setdefault(s_, {'n': 0, 'c': Counter()})
                r['n'] += 1
                for B in lst:
                    r['c'][rel_str(relation(A, B))] += 1
            # the whole neighbourhood of this piece, as one set (a dome with its ring)
            members = frozenset(rel_str(relation(A, B)) for s_, B in nbs)
            if len(members) >= 2:
                rings[(A['id'], members)] += 1
        # runs: a piece followed by the same piece on one side (turned the same way, or about: the game lays
        # its hall segments alternately turned), chained
        same = lambda P, C: C['id'] == P['id'] and relation(P, C)[4] in (0, 180)
        for A in pieces:
            for s_, B in nb_of[A['ref']]:
                if not same(A, B):
                    continue
                rel = relation(A, B)
                # (a run starts where the opposite side has no such piece before it)
                opp = {'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N', 'U': 'D', 'D': 'U'}[s_]
                if any(s2 == opp and same(A, C) for s2, C in nb_of[A['ref']]):
                    continue
                n = 1
                cur = A
                seen = {A['ref']}
                while True:
                    nxt = next((C for s2, C in nb_of[cur['ref']] if s2 == s_ and same(cur, C) and C['ref'] not in seen), None)
                    if not nxt:
                        break
                    seen.add(nxt['ref'])
                    n += 1
                    cur = nxt
                r = runs.setdefault(A['id'], {}).setdefault(s_, {'step': list(rel[1:4]), 'lengths': Counter()})
                r['lengths'][n] += 1
        _alt_runs(pieces, nb_of, alts)
    out_adj = {}
    for aid, rec in adj.items():
        out_adj[aid] = {s_: {'n': r['n'], 'c': dict(r['c'].most_common(40))} for s_, r in rec.items()}
    out_runs = {aid: {s_: {'step': r['step'], 'lengths': {str(k): v for k, v in r['lengths'].items()}} for s_, r in rec.items()}
                for aid, rec in runs.items()}
    out_rings = []
    for (aid, members), n in rings.most_common():
        # (a set seen twice or more; for a piece the game itself stands only once or twice, its domed hall,
        # the one set it stands round it)
        if (n < 2 and n_of[aid] > 2) or len(out_rings) >= 150:
            continue
        out_rings.append({'id': aid, 'members': sorted(members), 'n': n})
    out_alts = {aid: {s_: {k: {'step': r['step'], 'lengths': {str(n): v for n, v in r['lengths'].items()}} for k, r in rr.items()}
                      for s_, rr in rec.items()} for aid, rec in alts.items()}
    return {'places': places, 'n': dict(n_of), 'adj': out_adj, 'runs': out_runs, 'rings': out_rings, 'alts': out_alts,
            'halls': survey_halls(db, prefix)}


AXES = {'E': (1, 0), 'W': (-1, 0), 'N': (0, 1), 'S': (0, -1)}


def _along(A, B, d):
    """B's offset in A's frame as (forward along d, sideways, up)."""
    lx, ly = to_local(A, B['x'], B['y'])
    return lx * d[0] + ly * d[1], abs(lx * d[1] - ly * d[0]), B['z'] - A['z']


def alt_next(A, cur, d, nb_of):
    """The next junction and copy of A beyond cur along d (in A's frame), or None."""
    f0 = _along(A, cur, d)[0]
    for s2, B in nb_of[cur['ref']]:
        fb, lat, dz = _along(A, B, d)
        if B['id'] == A['id'] or fb <= f0 + 64 or lat > 64 or abs(dz) > 64:
            continue
        for s3, C in nb_of[B['ref']]:
            fc, lat2, dz2 = _along(A, C, d)
            if C['id'] == A['id'] and relation(A, C)[4] in (0, 180) and fc > fb + 64 and lat2 <= 64 and abs(dz2) <= 64:
                return B, C
    return None


def _alt_runs(pieces, nb_of, alts):
    """Runs that alternate a segment with a junction (a Redoran hall segment, a 3way or 4way, the segment
    again...): from A along each of its sides, B (another piece) then a copy of A beyond it, in line,
    chained. alts[A id][side]['B rel'] = {'step': A's copy in A's frame [x, y, z, turn], 'lengths': {copies of A: n}}."""
    next_pair = lambda A, cur, d: alt_next(A, cur, d, nb_of)
    for A in pieces:
        for s_, d in AXES.items():
            back = (-d[0], -d[1])
            if next_pair(A, A, back):
                continue                                    # (not the start of its chain)
            first = next_pair(A, A, d)
            if not first:
                continue
            n, cur, seen = 1, A, {A['ref']}
            pair = first
            while pair and pair[1]['ref'] not in seen:
                seen.add(pair[1]['ref'])
                n += 1
                cur = pair[1]
                pair = next_pair(A, cur, d)
            B, C = first
            rc = relation(A, C)
            r = alts.setdefault(A['id'], {}).setdefault(s_, {}).setdefault(rel_str(relation(A, B)), {'step': list(rc[1:5]), 'lengths': Counter()})
            r['lengths'][n] += 1


# ------------------------------------------------------------------ halls: a big centre with its whole ring
HALL_MIN = (500, 1000)                # a hall centre's box: at least this on its short and long side (Redoran's domes)
HALL_REACH = 560                      # its ring: the pieces within this of its box (the side pieces and the corners)


def hall_root(db, rid, b=None):
    """Whether a piece is the centre of a big hall (Redoran (large)'s domed lcenter_02, 1024 across): big
    enough that its ring reaches round the corners, which no single face of it touches."""
    if b is None:
        ri, b = _box(db, rid)
        if ri is None or not b:
            return False
    w, h = b[3] - b[0], b[4] - b[1]
    return min(w, h) >= HALL_MIN[0] and max(w, h) >= HALL_MIN[1] and is_piece(db, rid)


def survey_halls(db, prefix):
    """Every place of the game that stands one of the kit's hall centres (they are rare: the game has two
    domed Redoran halls, and the kit's own places sample may hold neither), and round each the whole ring:
    the pieces against its faces and the corner pieces beyond them, as relations in the centre's frame.
    {root id: {'n', 'fill': {side: n}, 'rings': [{'members', 'cell'}], 'faces': {side: {rel: n}},
    'ends': {member id: {side: {rel: n}}}}}."""
    if _hall_roots.get('recs') is not db.recs:
        # (every kit's hall centres in one pass over the placed ids: the survey asks once per kit)
        by = {}
        for rid in db.used_in:
            pre = kits.kit_prefix(rid)
            if pre and hall_root(db, rid):
                by.setdefault(pre, []).append(rid.lower())
        _hall_roots.clear()
        _hall_roots.update(recs=db.recs, by=by)
    roots = _hall_roots['by'].get(prefix, [])
    out = {}
    for rid in sorted(roots):
        cells = sorted({db.recs[ci][7] for ci in db.used_in.get(rid, ()) if db.recs[ci][0] == 'CELL'
                        and kits.game_made(db, db.recs[ci][7]) and not db.recs[ci][7].startswith('#')})
        rec = {'n': 0, 'fill': Counter(), 'rings': [], 'faces': {}, 'ends': {}}
        for ck in cells[:12]:
            try:
                pieces = read_pieces(db, ck)
            except Exception:
                continue
            for A in [p for p in pieces if p['id'] == rid]:
                rec['n'] += 1
                a = own_box(A)
                members = []
                for B in pieces:
                    if B is A or overlaps(A, B) or abs(B['z'] - A['z']) > 160:
                        continue
                    L = local_box(A, B)
                    if L[0] < a[0] - HALL_REACH or L[3] > a[3] + HALL_REACH or L[1] < a[1] - HALL_REACH or L[4] > a[4] + HALL_REACH:
                        continue
                    members.append(B)
                nbs = neighbours(pieces, A)
                for s_ in {s for s, _B in nbs}:
                    rec['fill'][s_] += 1
                for s_, B in nbs:
                    f = rec['faces'].setdefault(s_, Counter())
                    f[rel_str(relation(A, B))] += 1
                # (what stands at the ends of each side piece: the corners, in the side piece's own frame)
                mset = {m['ref'] for m in members}
                for B in members:
                    for s2, C in neighbours(pieces, B):
                        if C['ref'] in mset and C is not A:
                            e = rec['ends'].setdefault(B['id'], {}).setdefault(s2, Counter())
                            e[rel_str(relation(B, C))] += 1
                rec['rings'].append({'members': sorted(rel_str(relation(A, B)) for B in members), 'cell': ck})
        if rec['n']:
            out[rid] = {'n': rec['n'], 'fill': dict(rec['fill']), 'rings': rec['rings'][:6],
                        'faces': {s_: dict(c) for s_, c in rec['faces'].items()},
                        'ends': {m: {s_: dict(c) for s_, c in e.items()} for m, e in rec['ends'].items()}}
    return out


def rel_str(rel):
    return '%s|%d|%d|%d|%d' % rel


def parse_rel(s):
    bid, x, y, z, dq = s.split('|')
    return (bid, int(x), int(y), int(z), int(dq))


def survey(db, limit=PLACES):
    """Every kit, kept on disk: {prefix: survey_kit(...)}."""
    if _cache.get('recs') is db.recs and _cache.get('all'):
        return _cache['all']
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache.update(recs=db.recs, all=saved)
        return saved
    except Exception:
        pass
    out = {}
    for prefix in kits.kits(db):
        try:
            out[prefix] = survey_kit(db, prefix, limit)
        except Exception as e:
            print('adjacency survey, %s: %s' % (prefix, e))
    _cache.update(recs=db.recs, all=out)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


_started = [None]


def ready(db):
    """The survey when it's to hand (in memory or on disk), else None with it started in the survey
    process (learning.py lists it among the surveys a furnish and a build wait for)."""
    if _cache.get('recs') is db.recs and _cache.get('all'):
        return _cache['all']
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    t = _started[0]
    if t is None or not t.is_alive():
        import background
        _started[0] = background.start('which building piece the game joins to which', lambda: survey(db), task=('adjacency', 'survey', []))
    return None


# ------------------------------------------------------------------ what the survey says about a piece
def kit_of(db, pieces):
    """The kit most of a place's pieces belong to (by prefix), or None."""
    votes = Counter(kits.kit_prefix(p['id']) for p in pieces)
    votes.pop(None, None)
    known = kits.kits(db)
    for pre, n in votes.most_common():
        if pre in known:
            return pre
    return None


def record(db, prefix, aid):
    """The kit's record for a piece id: {'n', 'adj': {side: {'n', 'c'}}} or None."""
    sv = ready(db)
    rec = (sv or {}).get(prefix)
    if not rec:
        return None
    n = rec['n'].get(aid)
    if not n:
        # (a piece the kit's places never show: any kit that shows it, the one with most)
        best = None
        for pre, r2 in sv.items():
            if r2['n'].get(aid) and (best is None or r2['n'][aid] > best[0]):
                best = (r2['n'][aid], pre)
        if not best:
            return None
        rec, n = sv[best[1]], best[0]
    hall = rec.get('halls', {}).get(aid)
    if hall is None:
        hall = next((r2['halls'][aid] for r2 in sv.values() if aid in r2.get('halls', {})), None)
    return {'n': n, 'adj': rec['adj'].get(aid, {}), 'runs': rec.get('runs', {}).get(aid, {}),
            'alts': rec.get('alts', {}).get(aid, {}), 'hall': hall,
            'rings': [g for g in rec.get('rings', []) if g['id'] == aid]}


def _turned(A, k):
    return dict(A, rz=(A['rz'] + k * math.pi / 2) % (2 * math.pi))


def _quarter_turns(A):
    """The quarter turns under which a piece's box is the same: all four for a square one, half for a long one."""
    b = A['b']
    return (0, 1, 2, 3) if abs((b[3] - b[0]) - (b[4] - b[1])) < 64 else (0, 2)


def closed_hall(db, prefix, A, rec=None):
    """A hall centre's ring closed the game's way: on each side the side piece the game stands there that
    spans the side and is walled beyond (Redoran's lwall_02; its sides are alike, so the four are pooled),
    and at each corner the piece the game stands at the side pieces' ends (lcorner_01). [{'id', 'p'}] in the
    world, round A as it stands."""
    rec = rec or record(db, prefix, A['id'])
    hall = (rec or {}).get('hall')
    if not hall:
        return []
    ks = _quarter_turns(A)
    # the side pieces of every face, seen from the face turned to the north
    pooled = Counter()
    for s_, c in hall.get('faces', {}).items():
        if s_ not in AXES:
            continue
        for rs, n in c.items():
            B = _piece_at_rel(db, A, parse_rel(rs))
            if not B:
                continue
            for k in ks:
                Ak = _turned(A, k)
                if side_of(Ak, B) == 'N':
                    pooled[rel_str(relation(Ak, B))] += n
                    break
    a = own_box(A)
    out = []
    for k in ks:
        Ak = _turned(A, k)
        # (Ak's north face is this side of A; a long piece's two ends take the end pieces)
        span = (a[3] - a[0]) if k % 2 == 0 else (a[4] - a[1])
        for rs, n in pooled.most_common():
            B = _piece_at_rel(db, Ak, parse_rel(rs))
            if not B or any(overlaps(B, X) for X in out):
                continue
            L = local_box(Ak, B)
            if (L[3] - L[0]) < span * 0.9:
                continue                                # (a bridge or a stair: not the side itself)
            brec = record(db, prefix, B['id'])
            back = side_of(B, Ak)
            outward = {'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N'}.get(back)
            if not outward or join_share(brec, outward) >= 0.5:
                continue                                # (it leads on: an entrance, more hall)
            out.append(B)
            break
    sides = list(out)
    # the corners: at the ends of the side pieces, the piece beyond both of the centre's faces
    for sx in (-1, 1):
        for sy in (-1, 1):
            votes = Counter()
            for W in sides:
                ends = (hall.get('ends', {}).get(W['id']) or {})
                wrec = record(db, prefix, W['id'])
                for s2 in ('E', 'W', 'N', 'S'):
                    c = Counter(ends.get(s2, {}))
                    for rs, n in ((wrec or {}).get('adj', {}).get(s2, {}).get('c', {}) or {}).items():
                        c[rs] += n
                    for rs, n in c.items():
                        C = _piece_at_rel(db, W, parse_rel(rs))
                        if not C:
                            continue
                        L = local_box(A, C)
                        cx, cy = (L[0] + L[3]) / 2.0, (L[1] + L[4]) / 2.0
                        if not (cx * sx > a[3 if sx > 0 else 0] * sx and cy * sy > a[4 if sy > 0 else 1] * sy):
                            continue
                        if overlaps(A, C) or any(overlaps(C, X) for X in out):
                            continue
                        votes[(C['id'], round(C['x']), round(C['y']), round(C['z']), round(math.degrees(C['rz'])) % 360)] += n
            if votes:
                (cid, x, y, z, dq), _n = votes.most_common(1)[0]
                C = _piece_at_rel(db, A, None, world=(cid, x, y, z, math.radians(dq)))
                if C:
                    out.append(C)
    return [{'id': B['id'], 'p': [round(B['x'], 2), round(B['y'], 2), round(B['z'], 2), 0, 0, round(B['rz'] % (2 * math.pi), 5)]} for B in out]


def is_hall_centre(A, rec):
    """Whether the game stands a whole ring round this piece: its four sides filled in most of its halls
    and pieces beyond two of its faces at once (the corners)."""
    hall = (rec or {}).get('hall')
    if not hall or not hall.get('n'):
        return False
    if any(hall.get('fill', {}).get(s_, 0) < 0.75 * hall['n'] for s_ in AXES):
        return False
    a = own_box(A)
    for g in hall.get('rings', []):
        for ms in g['members']:
            _bid, x, y, _z, _dq = parse_rel(ms)
            if (x > a[3] or x < a[0]) and (y > a[4] or y < a[1]):
                return True
    return False


def game_halls(db, prefix, A, rec=None):
    """The rings the game itself stands round this hall centre: [{'members': [{'id', 'p'}], 'cell'}]."""
    rec = rec or record(db, prefix, A['id'])
    out = []
    for g in ((rec or {}).get('hall') or {}).get('rings', []):
        out.append({'cell': g.get('cell'), 'members': [placed(A, parse_rel(ms)) for ms in g['members']]})
    return out


def _piece_at_rel(db, A, rel, world=None):
    """A piece standing in the relation to A (or at a world spot), as read_pieces gives them."""
    if world:
        bid, x, y, z, rz = world
    else:
        it = placed(A, rel)
        bid, (x, y, z, _a, _b, rz) = it['id'], it['p']
    ri, b = _box(db, bid)
    if ri is None or not b:
        return None
    return {'ref': 'hall|%s|%d|%d|%d' % (bid, x, y, z), 'id': bid.lower(), 'x': x, 'y': y, 'z': z, 'rz': rz % (2 * math.pi), 's': 1.0, 'b': b, 'ri': ri}


def join_share(rec, side):
    """How often the game has something against this face of the piece: 0..1."""
    if not rec or not rec['n']:
        return 0.0
    return min(1.0, rec['adj'].get(side, {}).get('n', 0) / float(rec['n']))


def candidates(rec, side, limit=12):
    """What the game joins to this face, most often first: [(rel tuple, n, share)]."""
    r = (rec or {}).get('adj', {}).get(side)
    if not r:
        return []
    total = float(r['n'] or 1)
    out = []
    for s_, n in sorted(r['c'].items(), key=lambda kv: -kv[1]):
        if len(out) >= limit or n < 2 and len(out) >= 4:
            break
        out.append((parse_rel(s_), n, n / total))
    return out


def face_segment(A, side):
    """The floor-line segment of a face of A in the world: (x0, y0, x1, y1, z, nx, ny) with the outward
    normal; for 'U' the rim at the top (its four corners come back as the segment list of the caller)."""
    b, s = A['b'], A['s']
    x0, y0, x1, y1 = b[0] * s, b[1] * s, b[3] * s, b[4] * s
    z = A['z'] + b[2] * s
    if side == 'E':
        pts, n = ((x1, y0), (x1, y1)), (1, 0)
    elif side == 'W':
        pts, n = ((x0, y1), (x0, y0)), (-1, 0)
    elif side == 'N':
        pts, n = ((x1, y1), (x0, y1)), (0, 1)
    elif side == 'S':
        pts, n = ((x0, y0), (x1, y0)), (0, -1)
    elif side == 'U':
        pts, n, z = ((x0, y0), (x1, y1)), (0, 0), A['z'] + b[5] * s
    else:
        pts, n, z = ((x0, y0), (x1, y1)), (0, 0), z
    (ax, ay), (bx, by) = pts
    wx0, wy0 = to_world(A, ax, ay)
    wx1, wy1 = to_world(A, bx, by)
    c, sn = math.cos(A['rz']), math.sin(A['rz'])
    nx, ny = n[0] * c + n[1] * sn, -n[0] * sn + n[1] * c
    return (round(wx0, 1), round(wy0, 1), round(wx1, 1), round(wy1, 1), round(z, 1), round(nx, 3), round(ny, 3))


def summary(db, prefixes=None):
    """For people: per kit, the pieces seen most and what the game joins to each face of them."""
    sv = ready(db) or {}
    out = {}
    for pre in (prefixes or sorted(sv)):
        rec = sv.get(pre)
        if not rec:
            continue
        rows = []
        for aid, n in sorted(rec['n'].items(), key=lambda kv: -kv[1])[:10]:
            faces = {}
            for s_, r in rec['adj'].get(aid, {}).items():
                top = sorted(r['c'].items(), key=lambda kv: -kv[1])[:3]
                faces[s_] = {'share': round(r['n'] / float(n), 2), 'top': [(parse_rel(k)[0], parse_rel(k)[4], v) for k, v in top]}
            rows.append({'id': aid, 'n': n, 'faces': faces})
        out[pre] = {'places': rec['places'], 'pieces': len(rec['n']), 'rows': rows,
                    'runs': {aid: {s_: r['lengths'] for s_, r in rr.items()} for aid, rr in rec.get('runs', {}).items()},
                    'rings': rec.get('rings', [])[:8]}
    return out
