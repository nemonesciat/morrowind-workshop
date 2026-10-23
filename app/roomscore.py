"""The room score: how much a finished room looks like one the game would have made, as one number
from 0 to 100 and the terms that made it (packaging/nexus/room-score-design.md, step 1).

Every term asks one of the surveys Auto-furnish already learns from (never a hand-written rule):

  Shape     layoutsurvey        is the room's size, shape, doorway count and column pattern one the game
                                makes for rooms of this kind in this style family?
  Joinery   joints, adjacency   at each joint of the floor tiles, is what stands there what the game stands
                                in that situation, and how often; at each face of each building piece, is
                                the piece joined to it one the game joins there?
  Continuity edges              is every end of every building piece met by another piece's end, capped by
                                a closer or resting on another piece's face (naked ends at no more than the
                                game's rate for the kit), and across each met pair, are the two textures
                                ones the game puts together? Kit-agnostic: read from the meshes.
  Standing  placesurvey,        for each piece of furniture: at the wall, a step off it or out in the room,
            roomsurvey          in a corner or not, as often as the game stands its kind; and how far from
                                the thing it belongs with (a chair from its table, a chest from its bed)
  Fullness  roomsurvey,         is the count of each kind of thing within the game's range for this kind
            roomkindsurvey      of room and size? Too few and too many both cost (a Poisson likelihood
                                at the game's rate per nine tiles)
  Company   arrangesurvey       is each piece in company the way the game keeps it (a bed with its chest,
                                a table with its chairs), or alone when the game stands it alone?
  Walls     wallsurvey2         are there as many hangings as the game hangs in such a room, and as many
                                lights?
  Faults    placecheck          the 22 detectors, each fault a cost (FAULT_COST), heavier in a bare room
  Taste     catalogue, taste    the catalogue's habits (rugs under tables, plants in planters, planters at
                                walls and posts, a light at a stair foot) at the game's rate for the style,
                                and, when the user has marked exemplary places, how close the room's
                                make-up is to their rooms of the same kind

Each term is a log-likelihood under its survey, normalised two ways so a big room and a small one, a
rare kind and a common one, sit on one scale: every outcome's likelihood is measured against the
likelihood the game's own choices get on average under that same distribution (p over the sum of p
squared, which is 1 on average for a draw from the distribution, so a usual thing scores 1 and a rare
one a fraction, capped at 1 and floored at FLOOR so one awful thing never zeroes a room), and the term
is the geometric mean over the things it covered. A term that covered nothing is left out and the
weights are spread over the rest. The score is the weighted mean of the terms (WEIGHTS, equal to start;
the calibration report says what was tuned and why).

Speed: everything but the detectors is table lookups, and the detectors have a fast mode that feeds
placecheck's own room checks a scene whose rays always hit (so "floating", "hung from nothing" and the
ray-tested shelves are not looked for, and no mesh is loaded). A place's result is cached by the bytes
of its references, so a second ask for an unchanged place is free. Measured in the calibration report.

Nothing here edits a place; score_place reads it the way the place check does."""
import hashlib
import math
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey
from editing import EditError

VERSION = 1

# the weights of the terms in the score (the calibration report, packaging/nexus/room-score-calibration.md,
# says what was tuned from the equal start and why: Faults counts double, since the detectors are the
# user's own verdicts from the walks and the only term that says "bad" rather than "unusual")
WEIGHTS = {'shape': 1.0, 'joinery': 1.0, 'continuity': 1.0, 'standing': 1.0, 'fullness': 1.0, 'company': 1.0, 'walls': 1.0,
           'faults': 2.0, 'taste': 1.0}
TERMS = ('shape', 'joinery', 'continuity', 'standing', 'fullness', 'company', 'walls', 'faults', 'taste')
LABEL = {'shape': 'Shape', 'joinery': 'Joinery', 'continuity': 'Continuity', 'standing': 'Standing', 'fullness': 'Fullness',
         'company': 'Company', 'walls': 'Walls', 'faults': 'Faults', 'taste': 'Taste'}
NAKED_SHARE = 0.005             # the game's naked share assumed until the edge survey is learnt (its places measure 0.5% over all)
UNKNOWN_BLEND = 0.1             # a met edge whose two textures the game never puts together (a wall of another kit)
# how bad each kind of fault is (placecheck.KINDS), from the user's walks: a thing through a wall, a thing
# taller than the room, a gap or a missing ceiling are what they stop for; a book leaning on nothing and a
# planter one plant short are what they shrug at
FAULT_COST = {'wall': 1.5, 'floating': 1.0, 'chair': 0.8, 'nowall': 1.0, 'light': 1.0, 'water': 1.0, 'planter': 0.3,
              'rider': 0.6, 'floor': 0.6, 'window': 0.8, 'lonepot': 0.5, 'tall': 1.5, 'counter': 0.8, 'book': 0.3,
              'gap': 2.0, 'doorway': 1.5, 'ceiling': 2.0, 'post': 0.4, 'joint': 0.5, 'hole': 1.0, 'clip': 0.3, 'zfight': 0.3,
              'naked': 0.8, 'hallblock': 1.5}     # (a hall one can't walk through: as bad as a thing through a wall)
FLOOR = 0.05                    # the least any one outcome counts for (e^-3): one awful thing never zeroes a room
EPS = 1e-6
LINK = 200                      # two floor pieces this close keep company (arrangesurvey.LINK)
MIN_ROOMS = 12                  # a kind in a style family with fewer surveyed rooms goes by every family's
COLUMN = re.compile(r'pillar|column|post|colum')
STAIR = re.compile(r'stair|ramp')
_cache = {}                     # (cell key, ref bytes hash) -> score_place result
_index = {}                     # per-survey indexes, per db.recs


# ------------------------------------------------------------------ the entry points
def score_place(db, cell_key, fast=True, gaps=False, m=None, info=None, cache=True):
    """Every room of a place scored: {'score', 'terms': {term: value}, 'rooms': [{id, name, kind, purpose,
    tiles, things, score, terms, covered, notes}], 'n_rooms', 'fast', 'secs', 'cached'}. fast: no mesh rays
    (see the module note); gaps: run the gap finder too (slow; never in fast mode). m / info: a cellmap or a
    furnish.rooms result to score instead of the place as it is (the lab's spoilt rooms); not cached."""
    import time
    t0 = time.time()
    key = None
    if cache and m is None and info is None:
        hsh = _ref_hash(db, cell_key)
        key = (cell_key.lower(), fast, bool(gaps), hsh) if hsh else None
        hit = _cache.get(key) if key else None
        if hit and hit[0] is db.recs:
            out = dict(hit[1])
            out['cached'] = True
            out['secs'] = round(time.time() - t0, 3)
            return out
    if info is None:
        if m is not None:
            # (a given cellmap: furnish.rooms reads mapdata.cellmap, so hand it this one for the call)
            real = mapdata.cellmap
            try:
                mapdata.cellmap = lambda db_, ck_: m if ck_ == cell_key else real(db_, ck_)
                info = furnish.rooms(db, cell_key)
            finally:
                mapdata.cellmap = real
        else:
            info = furnish.rooms(db, cell_key)
    if not info['rooms']:
        return {'score': None, 'terms': {}, 'rooms': [], 'n_rooms': 0, 'fast': fast, 'secs': round(time.time() - t0, 3),
                'cached': False, 'note': 'No rooms were found here (the place isn\'t laid in a style\'s floor pieces).'}
    P = _place(db, cell_key, info, fast, gaps, m)
    rooms = [_score_room(db, P, rm) for rm in info['rooms']]
    total, terms = _combine([(r['score'], r['terms'], r['tiles']) for r in rooms])
    out = {'score': total, 'terms': terms, 'rooms': rooms, 'n_rooms': len(rooms), 'fast': fast, 'cached': False,
           'secs': round(time.time() - t0, 3), 'weights': dict(WEIGHTS)}
    if key is not None:
        _cache[key] = (db.recs, out)
        if len(_cache) > 64:
            for k in list(_cache)[:16]:
                _cache.pop(k, None)
    return out


def score(db, cell_key, room=None, fast=True, gaps=False, m=None, info=None):
    """One room's score (room: its id or name as furnish.rooms gives them), or the whole place's when
    room is None: {'score', 'terms', ...} as score_place's room entries, with 'place' holding the whole."""
    P = score_place(db, cell_key, fast=fast, gaps=gaps, m=m, info=info)
    if room is None:
        return P
    for r in P['rooms']:
        if r['id'] == room or (isinstance(room, str) and r['name'].lower() == room.lower()):
            out = dict(r)
            out['place'] = {'score': P['score'], 'terms': P['terms'], 'n_rooms': P['n_rooms']}
            return out
    raise EditError('No room %r here.' % (room,))


def forget(cell_key=None):
    """Drop the cached scores (of one place, or all): for callers that changed a place and know it."""
    if cell_key is None:
        _cache.clear()
        return
    for k in [k for k in _cache if k[0] == cell_key.lower()]:
        _cache.pop(k, None)


# ------------------------------------------------------------------ combining
def _combine(rows):
    """The weighted mean of several rooms' scores and terms (by their tile counts): (score, terms)."""
    rows = [r for r in rows if r[0] is not None]
    if not rows:
        return None, {}
    w_all = float(sum(max(1, r[2]) for r in rows))
    total = sum(r[0] * max(1, r[2]) for r in rows) / w_all
    terms = {}
    for t in TERMS:
        have = [(r[1][t], max(1, r[2])) for r in rows if r[1].get(t) is not None]
        if have:
            terms[t] = round(sum(v * w for v, w in have) / float(sum(w for _v, w in have)), 1)
        else:
            terms[t] = None
    return round(total, 1), terms


def _term(ratios):
    """A term's value from its outcome ratios: 100 x the geometric mean (each floored at FLOOR), or None
    when it covered nothing. An item may be (ratio, weight): a bed out of place weighs more than a stool."""
    if not ratios:
        return None
    s = w = 0.0
    for it in ratios:
        r, wt = it if isinstance(it, tuple) else (it, 1.0)
        s += wt * math.log(max(FLOOR, min(1.0, r)))
        w += wt
    return round(100.0 * math.exp(s / w), 1) if w else None


def _weight(x):
    """A thing's weight among a term's items, by its footprint: a crate's 64 x 64 counts 1, a bed about
    2, a cup a third (floor-standing things only come here anyway)."""
    b, s = x.get('b'), x.get('s') or 1.0
    if not b:
        return 1.0
    area = max(1.0, (b[3] - b[0]) * (b[4] - b[1]) * s * s)
    return max(0.3, min(4.0, math.sqrt(area) / 64.0))


def _norm(p, shares):
    """An outcome's likelihood over the likelihood the game's own choices get on average under the same
    distribution: p / sum(q^2) over the distribution's shares, capped at 1."""
    tot = float(sum(shares)) or 1.0
    e = sum((q / tot) ** 2 for q in shares) or 1.0
    return min(1.0, (p / tot) / e)


def _norm2(p):
    """The same for a yes/no event with share p of yes: the ratio for 'yes' (1 - p gives 'no')."""
    e = p * p + (1.0 - p) * (1.0 - p)
    return min(1.0, p / e) if e else 1.0


def _poisson_ratio(n, lam):
    """Poisson(n; lam) over the likelihood the game's own counts get on average at that rate (the sum of
    the squared pmf), capped at 1: 1 around the usual count, less either way."""
    lam = max(0.02, lam)
    lp = -lam + n * math.log(lam) - math.lgamma(n + 1)
    e = 0.0
    k = 0
    while True:
        lk = -lam + k * math.log(lam) - math.lgamma(k + 1)
        e += math.exp(2 * lk)
        if k > lam + 6 * math.sqrt(lam) + 3:
            break
        k += 1
    return min(1.0, math.exp(lp) / e) if e else 1.0


def _count_ratio(n, lam, s=0.8):
    """How far a count is from the game's rate, on a log scale (a count twice or half the rate is as far
    either way; the spread of real rooms is wider than a Poisson's, so a Poisson is not used here):
    exp(-|ln((n + 0.5) / (lam + 0.5))| / s), 1 at the rate, 0.42 at twice or half it."""
    return math.exp(-abs(math.log((n + 0.5) / (max(0.0, lam) + 0.5))) / s)


def _weighted(terms):
    """The score from the terms present: the weighted mean over the terms that covered something."""
    tot = wsum = 0.0
    for t, v in terms.items():
        if v is None:
            continue
        tot += WEIGHTS.get(t, 1.0) * v
        wsum += WEIGHTS.get(t, 1.0)
    return round(tot / wsum, 1) if wsum else None


def _ref_hash(db, cell_key):
    """A hash of the place's references as they are now (their bytes), the cache key."""
    h = hashlib.blake2b(digest_size=16)
    try:
        refs, _hdr = db.cell_refs(cell_key)
    except Exception:
        return None
    for k in sorted(refs):
        h.update(k.encode('utf-8', 'replace'))
        h.update(refs[k]['subs'] if isinstance(refs[k]['subs'], (bytes, bytearray)) else repr(refs[k]['subs']).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ the place, read once
class _Rays:
    """A scene whose every ray hits at once: placecheck's room checks then find nothing afloat and every
    hanging light under a ceiling, and the rest of their checks (boxes against wall faces, chairs with
    nothing to sit at, hangings over windows, clutter on bare floors, counters into tapestries) run as
    they are. The fast mode's stand-in for seethrough.place_scene (no mesh is loaded)."""
    tris = ()

    def nearest(self, o, d, tmax):
        return (8.0, None)


def _things(db, info, fast):
    """The furniture and clutter of the place with its family and world box, the building pieces, and
    the ray scene (a real one, or the fast mode's stand-in)."""
    import placecheck
    if not fast:
        return placecheck._things(db, info)
    import arrangesurvey
    import fixit
    import redoransurvey
    refs = [x for x in info['refs'] if x.get('b') and x['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC') and (not x.get('arch') or redoransurvey.is_thing(x))]
    big_ids = {id(x) for x in refs if x.get('arch')}
    arch = [x for x in info['refs'] if x.get('arch') and x.get('ri') is not None and id(x) not in big_ids]
    for x in refs:
        x['_fam'] = arrangesurvey.family(db, x['id'], x['type']) or redoransurvey.family(db, x)
        x['_box'] = fixit._world_box(x)
    return refs, arch, _Rays()


def _place(db, cell_key, info, fast, gaps, m=None):
    """Everything about the place the rooms' terms share: the things with families and boxes, the
    building pieces, the faults, the joint, adjacency and edge verdicts bucketed by position (m: a given
    cellmap to read the building from instead of the place as it is)."""
    import placecheck
    T = info['tile']
    refs, arch, sc = _things(db, info, fast)
    storey = placecheck._storey(db, info)
    # the furniture's own family (roomsurvey's: what the room surveys count)
    for x in refs:
        x['_rfam'] = roomsurvey.family_of(db, x['id'], x['type'])
    # the faults, room by room (placecheck's own checks), and the gap finder's when asked
    issues = []
    try:
        c = (db.project.cells or {}).get(cell_key) if db.project else None
    except Exception:
        c = None
    if c:
        import shelfsurvey
        planters = {x['k'] for x in info['refs'] if x.get('k') and shelfsurvey.PLANTER.search(x['id'].lower())}
        for x in refs:
            v = c['refs'].get(x.get('k')) or {}
            x['_on_planter'] = v.get('on') in planters
    for rm in info['rooms']:
        try:
            issues += placecheck._room_issues(db, info, rm, refs, arch, sc, storey)
        except Exception as e:
            print('room score, faults in %s:' % rm['name'], e)
    try:
        issues += placecheck._orphan_riders(db, cell_key, refs, info)
    except Exception:
        pass
    if gaps and not fast:
        try:
            import fixit
            res = fixit.scan(db, cell_key, clashes=True)
            for i in res['issues']:
                issues.append(i)
        except Exception as e:
            print('room score, gaps:', e)
    seen, uniq = set(), []
    for i in issues:
        k = (i['kind'], i.get('ref'), i.get('x'), i.get('y'))
        if k not in seen:
            seen.add(k)
            uniq.append(i)
    # the style: the kit most of the floor is laid in
    votes = Counter(kits.kit_prefix(t.get('id') or '') for rm in info['rooms'] for t in rm['_tiles'] if t.get('id'))
    if not votes:
        votes = Counter(kits.kit_prefix(r['id']) for r in info['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
    votes.pop(None, None)
    prefix = votes.most_common(1)[0][0] if votes else None
    P = {'key': cell_key, 'info': info, 'T': T, 'refs': refs, 'arch': arch, 'issues': uniq, 'storey': storey, 'prefix': prefix,
         'family': _family(prefix), 'fast': fast, 'doors': [r for r in info['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()],
         'plan': ((db.project.cells.get(cell_key) or {}).get('plan') if db.project else None)}
    P['joints'] = _joint_ratios(db, P)
    P['adjacency'] = _adjacency_ratios(db, P)
    P['edges'] = _edge_items(db, P, m)
    P['taste_rooms'] = _taste_rooms(db)
    return P


def _family(prefix):
    if not prefix:
        return None
    parts = prefix.lower().split('_')
    return '_'.join(parts[:-1]) if len(parts) >= 3 else prefix.lower()


# ------------------------------------------------------------------ one room
def _inside(P, room):
    """The things standing in this room (on its tiles, at its floor), as placecheck counts them."""
    T = P['T']
    fl = room['floor']
    return [x for x in P['refs'] if x['_box'] and any(abs(x['p'][0] - tl['x']) <= T / 2 and abs(x['p'][1] - tl['y']) <= T / 2 for tl in room['_tiles'])
            and fl - 30 <= x['_box'][2] <= fl + (400 if x['type'] == 'LIGH' else 200)]


def _in_room(room, x, y, z, T, up=200):
    return any(abs(x - tl['x']) <= T / 2 and abs(y - tl['y']) <= T / 2 for tl in room['_tiles']) and room['floor'] - 60 <= z <= room['floor'] + up


def _kind_of(P, room, floor):
    """(the survey kind the room is scored as, the plan's purpose or None). A planned room is scored as
    what it was meant to be (a bedroom with no bed is a poor bedroom, not a fair living room); a room with
    no plan (the game's, a hand-made one) by what stands in it, the way every survey sorts rooms."""
    counts = Counter(x['_rfam'] for x in floor if x['_rfam'] in roomsurvey.FLOOR_KINDS)
    content = roomsurvey.room_kind(counts)
    purpose = room.get('purpose') if P['plan'] else None
    if purpose:
        kind = furnish.SURVEY_KIND.get(purpose, purpose)
        if kind not in ('bedroom', 'tavern', 'shop', 'shrine', 'study', 'kitchen', 'storage', 'empty', 'living'):
            kind = content
        return kind, purpose, content
    return content, None, content


def _score_room(db, P, room):
    T = P['T']
    inside = _inside(P, room)
    floor = [x for x in inside if x['_rfam'] in roomsurvey.FLOOR_KINDS and x['_box'][2] < room['floor'] + 40]
    kind, purpose, content = _kind_of(P, room, floor)
    terms, covered, notes = {}, {}, {}
    for name, fn in (('shape', _shape), ('joinery', _joinery), ('continuity', _continuity), ('standing', _standing),
                     ('fullness', _fullness), ('company', _company), ('walls', _walls), ('faults', _faults), ('taste', _taste)):
        try:
            ratios, note = fn(db, P, room, inside, floor, kind, purpose)
        except Exception as e:
            ratios, note = [], 'not scored: %s' % e
        terms[name] = _term(ratios)
        covered[name] = len(ratios)
        if note:
            notes[name] = note
    return {'id': room['id'], 'name': room['name'], 'kind': kind, 'content_kind': content, 'purpose': purpose, 'tiles': room['tiles'],
            'w': room['w'], 'h': room['h'], 'things': len(inside), 'score': _weighted(terms), 'terms': terms, 'covered': covered, 'notes': notes}


# ------------------------------------------------------------------ Shape (layoutsurvey)
def _layout_index(db):
    """Per (style family, kind) and per kind: the game's rooms' sizes, doorway counts and columns, as
    counts; None until the layout survey is to hand."""
    import layoutsurvey
    idx = _index.get('layout')
    if idx and idx[0] is db.recs:
        return idx[1]
    s = layoutsurvey.ready(db)
    if not s:
        return None
    out = defaultdict(lambda: {'n': 0, 'size': Counter(), 'doors': Counter(), 'cols': Counter(), 'shape': Counter()})
    for r in s['rooms']:
        for key in ((r['family'], r['kind']), ('*', r['kind']), ('*', '*')):
            D = out[key]
            D['n'] += 1
            D['size']['%dx%d' % (r['long'], r['short'])] += 1
            D['doors'][min(r['doors'], 5)] += 1
            D['cols'][1 if r['columns'] else 0] += 1
            D['shape'][r['shape']] += 1
    out = dict(out)
    _index['layout'] = (db.recs, out)
    return out


def _ratio(counter, key, n, k=None):
    """How often the game gives this answer, against what its own answers get on average (_norm), with
    half a count of smoothing so an unseen answer is rare, not impossible."""
    if not n:
        return None
    add = 0.5
    shares = [v + add for v in counter.values()]
    if key not in counter:
        shares.append(add)
    return _norm(counter.get(key, 0) + add, shares)


def _door_spots(P, room):
    """The room's doorways: tile sides with a doorway out of the room, and door or jamb refs on its walls."""
    T = P['T']
    here = {(round(t['x'] / 32), round(t['y'] / 32)) for t in room['_tiles']}
    spots = set()
    for t in room['_tiles']:
        for s, (dx, dy) in furnish.STEP.items():
            if (round((t['x'] + dx * T) / 32), round((t['y'] + dy * T) / 32)) in here:
                continue
            mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
            if t['pat'][s] == 'door':
                spots.add((round(mx / 32), round(my / 32)))
            elif any(abs(d['p'][0] - mx) <= T * 0.55 and abs(d['p'][1] - my) <= T * 0.55 and room['floor'] - 60 <= d['p'][2] <= room['floor'] + 200 for d in P['doors']):
                spots.add((round(mx / 32), round(my / 32)))
    return spots


def _columns(P, room):
    """The free-standing columns in the room (a third of a tile or more from its walls)."""
    T = P['T']
    out = 0
    for a in P['arch']:
        low = a['id'].lower()
        if not COLUMN.search(low):
            continue
        if not (room['floor'] - 60 <= a['p'][2] <= room['floor'] + 200):
            continue
        if not (room['x_min'] + T * 0.3 <= a['p'][0] <= room['x_max'] - T * 0.3 and room['y_min'] + T * 0.3 <= a['p'][1] <= room['y_max'] - T * 0.3):
            continue
        if _in_room(room, a['p'][0], a['p'][1], a['p'][2], T):
            out += 1
    return out


def _shape(db, P, room, inside, floor, kind, purpose):
    idx = _layout_index(db)
    if idx is None:
        return [], 'the layout survey is not learnt yet'
    D = None
    for key in ((P['family'], kind), ('*', kind), ('*', '*')):
        D = idx.get(key)
        if D and D['n'] >= MIN_ROOMS:
            break
    if not D:
        return [], None
    long_, short = max(room['w'], room['h']), min(room['w'], room['h'])
    ratios = []
    r = _ratio(D['size'], '%dx%d' % (long_, short), D['n'])
    if r is not None:
        ratios.append(r)
    r = _ratio(D['doors'], min(len(_door_spots(P, room)), 5), D['n'])
    if r is not None:
        ratios.append(r)
    r = _ratio(D['cols'], 1 if _columns(P, room) else 0, D['n'])
    if r is not None:
        ratios.append(r)
    note = None
    if ratios and ratios[0] < 0.2:
        note = '%dx%d is a rare size for a %s' % (long_, short, kind)
    return ratios, note


# ------------------------------------------------------------------ Joinery (joints, adjacency)
def _joint_ratios(db, P):
    """Per joint of the place: (x, y, floor, ratio): the game's share for what stands at the edge over its
    share for what it stands there most, in the edge's situation. [] until the joint survey is to hand."""
    import joints
    out = []
    try:
        if not joints.ready(db):
            return out
        place = joints.read_place(db, P['key'], {'refs': P['info']['refs']})
    except Exception as e:
        print('room score, joints:', e)
        return out
    if not place['tiles']:
        return out
    votes = Counter(t['kit'] for t in place['tiles'])
    prefix = votes.most_common(1)[0][0]
    kp0 = kits.kit_pieces(db, prefix)
    if not kp0 or kp0.get('sheet_kit'):
        return out
    fam = joints.family(prefix)
    seen = set()
    done = set()
    for t in place['tiles']:
        if t['ref'] in seen or t['kit'] != prefix:
            continue
        seen.update(t['mates'])
        for s in joints.SIDES:
            sit = joints.situation(place, t, s)
            key, rec = joints.answers(db, prefix, sit, want_n=joints.MIN_ISSUE_N)
            if not rec:
                continue
            ident, _d = joints.answer_of(place, t, s, fam)
            now = joints.core(joints.ans_str(ident))
            ex, ey, _ax, _ay, _dx, _dy = joints.edge_frame(t, s)
            jk = (round(ex / 8), round(ey / 8), round(t['floor'] / 32))
            if jk in done:
                continue
            done.add(jk)
            cores = joints.ranked_cores(rec)
            cur = next((n for c, n, share, _b in cores if c == now), 0)
            cur_side, top_side = now.partition(';')[0], (cores[0][0].partition(';')[0] if cores else '')
            if 'door' in (cur_side, top_side) and cur_side != top_side:
                # (a doorway side is the doorways' business, kits.edge_doors: the finder never faults it)
                r = 1.0
            else:
                shares = [n + 0.5 for c, n, share, _b in cores] + ([0.5] if not cur else [])
                r = _norm(cur + 0.5, shares)
            out.append((t['x'], t['y'], t['floor'], r, s))
    return out


def _adjacency_ratios(db, P):
    """Per face of each building piece: (x, y, z, ratio) for whether the face is joined as often as the
    game joins it, and, when joined, whether to the piece the game joins there. [] until surveyed."""
    import adjacency
    out = []
    try:
        if not adjacency.ready(db):
            return out
        pieces = adjacency.read_pieces(db, P['key'], {'refs': P['info']['refs']})
    except Exception as e:
        print('room score, adjacency:', e)
        return out
    if not pieces:
        return out
    prefix = adjacency.kit_of(db, pieces)
    if not prefix:
        return out
    recs = {}
    for A in pieces:
        if A['id'] not in recs:
            recs[A['id']] = adjacency.record(db, prefix, A['id'])
        rec = recs[A['id']]
        if not rec or rec['n'] < 4:
            continue
        by_side = defaultdict(list)
        for s_, B in adjacency.neighbours(pieces, A):
            by_side[s_].append(B)
        for side in adjacency.SIDES6:
            js = min(0.98, max(0.02, adjacency.join_share(rec, side)))
            bs = by_side.get(side)
            if not bs:
                out.append((A['x'], A['y'], A['z'], _norm2(1.0 - js)))
                continue
            out.append((A['x'], A['y'], A['z'], _norm2(js)))
            # which piece: the game's share for this very join (id, offset, turn) against its usual there
            side_rec = rec['adj'].get(side)
            if side_rec and side_rec.get('c'):
                best = 0
                for B in bs:
                    try:
                        rs = adjacency.rel_str(adjacency.relation(A, B))
                    except Exception:
                        continue
                    best = max(best, side_rec['c'].get(rs, 0))
                shares = [v + 0.5 for v in side_rec['c'].values()] + ([0.5] if not best else [])
                out.append((A['x'], A['y'], A['z'], _norm(best + 0.5, shares)))
    return out


def _joinery(db, P, room, inside, floor, kind, purpose):
    T = P['T']
    ratios = []
    for x, y, z, r, _s in P['joints']:
        if any(abs(x - tl['x']) < 24 and abs(y - tl['y']) < 24 and abs(z - tl['floor']) < 64 for tl in room['_tiles']):
            ratios.append(r)
    n_j = len(ratios)
    H = P['storey'] or 256
    for x, y, z, r in P['adjacency']:
        if any(abs(x - tl['x']) <= T / 2 + 8 and abs(y - tl['y']) <= T / 2 + 8 for tl in room['_tiles']) and room['floor'] - 100 <= z <= room['floor'] + H:
            ratios.append(r)
    note = None
    if not ratios:
        note = 'the joint and adjacency surveys are not learnt yet' if not (P['joints'] or P['adjacency']) else None
    elif n_j and min(ratios[:n_j]) <= 0.1:
        note = 'a joint stands what the game seldom stands there'
    return ratios, note


# ------------------------------------------------------------------ Continuity (edges)
def _edge_items(db, P, m=None):
    """The place's building pieces with their ends classified (edges.check, kept by the place's bytes;
    m: a given cellmap, the lab's spoilt places), the game's naked share for the kit and its blends by
    texture: {'pieces': [(x, y, z, [(class, length, tex, mate tex or None)])], 'share': p, 'known': {'a|b'
    pairs the game puts together}, 'surveyed': bool} or None when the meshes can't be read."""
    import edges
    try:
        res = edges.check(db, P['key'], m=m, cache=m is None)
    except Exception as e:
        print('room score, edges:', e)
        return None
    if not res or not res['pieces']:
        return None
    # the ends by piece (a piece belongs to the room its origin stands in): {piece: (x, y, z, [(class, L, tex, mate)])}
    by_piece = {}
    for cls, pi, sg in res['items']:
        if cls in ('below', 'above', 'outside'):
            continue
        if pi not in by_piece:
            _k, _id, p = res['at'][pi]
            by_piece[pi] = (p[0], p[1], p[2], [])
        by_piece[pi][3].append((cls, sg['L'], sg['tex'], sg.get('mate')))
    kit = res.get('kit') or P['prefix']
    share = edges.game_share(db, kit)
    table = edges.game_blends(db, kit)
    known = {k for k, n in (table or {}).items() if n >= 2}
    # (a texture the survey never met at all, a kit with no gated place: nothing to go by, no verdict)
    textures = set()
    for k in known:
        textures.update(k.split('|', 1))
    return {'pieces': list(by_piece.values()), 'share': share if share is not None else NAKED_SHARE, 'known': known,
            'textures': textures, 'surveyed': share is not None, 'counts': res['counts']}


def _continuity(db, P, room, inside, floor, kind, purpose):
    E = P['edges']
    if not E:
        return [], None
    T = P['T']
    H = P['storey'] or 256
    p = min(0.5, max(0.005, E['share']))
    met_r, naked_r = _norm2(1.0 - p), _norm2(p)
    ratios = []
    n_naked = n_met = 0
    rare = 0
    for x, y, z, ends in E['pieces']:
        if not any(abs(x - tl['x']) <= T / 2 + 8 and abs(y - tl['y']) <= T / 2 + 8 for tl in room['_tiles']) or not room['floor'] - 100 <= z <= room['floor'] + H:
            continue
        for cls, L, tex, mate in ends:
            # (an end weighs by its length: a floor sheet's edge is four tiles of a beam's sliver)
            w = max(0.25, min(4.0, L / 64.0))
            if cls == 'naked':
                ratios.append((naked_r, w))
                n_naked += 1
                continue
            ratios.append((met_r, w))
            n_met += 1
            if cls == 'matched' and mate is not None and E['known']:
                # the pair across a met edge: one the game puts together (seen twice or more in the kit's
                # places), or not (a yes/no: a texture's minority partners are not rarities, the game lays a
                # beam against plaster in one join of twenty)
                pair = '%s|%s' % tuple(sorted((tex, mate)))
                if pair not in E['known'] and tex in E['textures'] and mate in E['textures']:
                    ratios.append((UNKNOWN_BLEND, w))
                    rare += 1
    note = None
    if n_naked:
        note = '%d naked edge%s' % (n_naked, '' if n_naked == 1 else 's') + ('' if E['surveyed'] else ' (the edge survey is not learnt yet)')
    elif rare:
        note = '%d join%s of textures the game does not put together' % (rare, '' if rare == 1 else 's')
    return ratios, note


# ------------------------------------------------------------------ Standing (placesurvey, roomsurvey pairs)
def _faces(room, T):
    import placecheck
    return placecheck._faces(room, T)


def _wall_dist(bx, faces, T):
    import placecheck
    return placecheck._wall_dist(bx, faces, T)


def _standing(db, P, room, inside, floor, kind, purpose):
    import placesurvey
    T = P['T']
    faces = _faces(room, T)
    corners = []
    for t in room['_tiles']:
        for sa, sb in (('N', 'E'), ('N', 'W'), ('S', 'E'), ('S', 'W')):
            if t['pat'][sa] == 'wall' and t['pat'][sb] == 'wall':
                corners.append((t['x'] + furnish.STEP[sb][0] * T / 2, t['y'] + furnish.STEP[sa][1] * T / 2))
    ratios = []
    stand = [x for x in inside if x['_rfam'] in placesurvey.FAMS and x['_box'][2] < room['floor'] + 40]
    sk = roomsurvey_kind(kind)
    for x in stand:
        pp = placesurvey.prefs(db, x['_rfam'], sk)
        if not pp:
            continue
        bx = x['_box']
        d = _wall_dist(bx, faces, T) if faces else 9999
        at = 'wall' if d <= placesurvey.AT_WALL else 'near' if d <= placesurvey.NEAR_WALL else 'middle'
        shares = pp.get('at') or {}
        w = _weight(x)
        if shares:
            ratios.append((_norm(shares.get(at, 0.0) + 0.02, [v + 0.02 for v in shares.values()] + ([0.02] if at not in shares else [])), w))
        cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
        if corners and pp.get('corner') is not None:
            in_corner = min(math.hypot(cx - qx, cy - qy) for qx, qy in corners) < placesurvey.CORNER * T
            c = min(0.98, max(0.02, pp['corner']))
            ratios.append((_norm2(c if in_corner else 1.0 - c), w))
    # how far each thing stands from what it belongs with (the game's median, roomsurvey.PAIRS)
    s = roomsurvey.ready(db)
    pairs = (s or {}).get('pairs') or {}
    for a_kind, b_kind in roomsurvey.PAIRS:
        pr = pairs.get((a_kind, b_kind))
        if not pr or pr.get('n', 0) < 5:
            continue
        bs = [x for x in floor if x['_rfam'] == b_kind]
        if not bs:
            continue
        med = max(40.0, float(pr['dist']))
        for a in (x for x in floor if x['_rfam'] == a_kind):
            d = min(math.hypot(b['p'][0] - a['p'][0], b['p'][1] - a['p'][1]) for b in bs)
            ratios.append(math.exp(-max(0.0, d - 1.5 * med) / med))
    note = None
    if not stand:
        note = 'nothing standing on the floor'
    elif ratios and min(r[0] if isinstance(r, tuple) else r for r in ratios) <= FLOOR:
        note = 'something stands where the game seldom stands its kind'
    return ratios, note


def roomsurvey_kind(kind):
    """A score kind in the room survey's words (a hall is 'empty' there)."""
    return furnish.SURVEY_KIND.get(kind, kind)


# ------------------------------------------------------------------ Fullness (roomsurvey, roomkindsurvey)
def _fullness(db, P, room, inside, floor, kind, purpose):
    s = roomsurvey.ready(db)
    if not s:
        return [], 'the room survey is not learnt yet'
    rates, src = None, None
    # (the room-kind survey's halls and baths: rooms the room survey files under 'empty' or 'living')
    rk_kind = {'hall': 'hall', 'corridor': 'hall', 'entry': 'hall', 'landing': 'hall', 'bath': 'bath'}.get(purpose or '')
    if rk_kind:
        try:
            import roomkindsurvey
            RK = roomkindsurvey.ready(db)
            K = ((RK or {}).get('kinds') or {}).get(rk_kind, {}).get('*')
            if K and K.get('rooms', 0) >= MIN_ROOMS:
                rates, src = K['per_9'], 'roomkindsurvey ' + rk_kind
        except Exception:
            rates = None
    if rates is None:
        K = s['kinds'].get(roomsurvey_kind(kind))
        if not K or K.get('rooms', 0) < MIN_ROOMS:
            K = s['kinds'].get('living')
        if not K:
            return [], None
        rates, src = K['per_9'], 'roomsurvey ' + roomsurvey_kind(kind)
    scale = room['tiles'] / 9.0
    counts = Counter(x['_rfam'] for x in floor)
    have = K.get('have') or {}
    fams = {f for f, v in have.items() if f in roomsurvey.FLOOR_KINDS and v >= 0.05} | {f for f in counts if f in roomsurvey.FLOOR_KINDS}
    ratios = []
    worst = None
    for f in sorted(fams):
        n = counts.get(f, 0)
        # whether the kind of thing is here at all, as often as the game's rooms of the kind have one
        p = min(0.98, max(0.02, float(have.get(f, 0.0))))
        r = _norm2(p if n else 1.0 - p)
        if n:
            # and, once here, how many: the game's rate for the room's size, one never too many
            lam = rates.get(f, 0.0) * scale
            mode = max(1, int(math.floor(lam)))
            lam = max(0.05, lam)
            over = (n - mode) * math.log(lam) - (math.lgamma(n + 1) - math.lgamma(mode + 1))
            r = r * min(1.0, math.exp(over))
        ratios.append(r)
        if worst is None or r < worst[0]:
            worst = (r, f, n, rates.get(f, 0.0) * scale, p)
    # and the room as a whole: everything standing on the floor, against the game's rate per nine tiles
    all_rate = sum(v for f, v in rates.items() if f in roomsurvey.FLOOR_KINDS)
    if all_rate:
        ratios.append(_count_ratio(len(floor), all_rate * scale))
    note = None
    if worst and worst[0] < 0.25:
        r, f, n, lam, p = worst
        if n:
            note = '%d %s%s where the game has about %.1f (one in %d rooms of the kind has any)' % (n, f, '' if n == 1 else 's', max(lam, p), round(1 / p))
        else:
            note = 'no %s, which %d rooms in 100 of the kind have' % (f, round(100 * p))
    return ratios, note


# ------------------------------------------------------------------ Company (arrangesurvey)
def _company_index(db):
    """From the arrangement survey: per room kind and anchor family, how many groups, and how many of
    them hold each other family; None until surveyed."""
    import arrangesurvey
    idx = _index.get('company')
    if idx and idx[0] is db.recs:
        return idx[1]
    s = arrangesurvey.ready(db)
    if not s:
        return None
    out = defaultdict(lambda: {'n': 0, 'with': Counter()})
    for sig, S in s['sigs'].items():
        anchor = arrangesurvey.anchor_of(sig)
        fams = {p.split('*')[0] for p in sig.split('+')}
        for kind, n in S['kinds'].items():
            for key in ((kind, anchor), ('*', anchor)):
                D = out[key]
                D['n'] += n
                for f in fams:
                    if f != anchor:
                        D['with'][f] += n
    out = dict(out)
    _index['company'] = (db.recs, out)
    return out


def _company(db, P, room, inside, floor, kind, purpose):
    import arrangesurvey
    idx = _company_index(db)
    if idx is None:
        return [], 'the arrangement survey is not learnt yet'
    mine = {id(x) for x in inside if x.get('_fam') and x['_box'][2] < room['floor'] + 160}
    if not mine:
        return [], 'nothing standing on the floor'
    # the groups over the whole place (a thing's company may stand across a doorway, in the next
    # one-tile space), each group counted for the room its anchor stands in... or any member here
    groups = [g for g in _groups(P) if any(id(x) in mine for x in g)]
    ratios = []
    sk = roomsurvey_kind(kind)
    lonely, missing = [], []
    for g in groups:
        alone = len(g) < 2
        for x in g:
            if id(x) not in mine:
                continue
            a = arrangesurvey.alone_share(db, x['_fam'], kind)
            if a is None:
                continue
            a = min(0.98, max(0.02, a))
            ratios.append((_norm2(a if alone else 1.0 - a), _weight(x)))
            if alone and a < 0.25:
                lonely.append(x['_fam'])
        if alone or len(g) > arrangesurvey.MAX_MEMBERS:
            continue
        anchor = min(g, key=lambda m: (arrangesurvey.ANCHOR_ORDER.index(m['_fam']) if m['_fam'] in arrangesurvey.ANCHOR_ORDER else 99,
                                       -(m['b'][3] - m['b'][0]) * (m['b'][4] - m['b'][1])))
        D = idx.get((sk, anchor['_fam']))
        if not D or D['n'] < 8:
            D = idx.get(('*', anchor['_fam']))
        if not D or D['n'] < 8:
            continue
        fams = {m['_fam'] for m in g}
        for m in g:
            if m is anchor or id(m) not in mine:
                continue
            p = min(0.98, max(0.02, (D['with'].get(m['_fam'], 0) + 0.5) / float(D['n'] + 1.0)))
            ratios.append((_norm2(p), _weight(m)))
        # and the company the game nearly always gives this anchor that is missing here (a table with no
        # chair, a bed with no chest): as unlikely as a group without it is
        if id(anchor) in mine:
            for f, n_with in D['with'].items():
                p = n_with / float(D['n'])
                if p >= 0.5 and f not in fams:
                    ratios.append((_norm2(1.0 - min(0.98, p)), _weight(anchor)))
                    missing.append((anchor['_fam'], f))
    note = None
    if lonely:
        note = 'a %s stands alone (the game keeps its kind in company)' % lonely[0]
    elif missing:
        note = 'a %s with no %s by it' % missing[0]
    return ratios, note


def _groups(P):
    """The place's floor pieces (arrangesurvey's families) in groups: pieces within LINK of one another
    on one storey. Read once per place."""
    if 'groups' in P:
        return P['groups']
    pieces = [x for x in P['refs'] if x.get('_fam') and x['_box']]
    left = list(range(len(pieces)))
    groups = []
    while left:
        grp = [left.pop(0)]
        i = 0
        while i < len(grp):
            a = pieces[grp[i]]
            for j in list(left):
                b = pieces[j]
                if abs(a['_box'][2] - b['_box'][2]) < 200 and math.hypot(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1]) <= LINK:
                    grp.append(j)
                    left.remove(j)
            i += 1
        groups.append([pieces[i_] for i_ in grp])
    P['groups'] = groups
    return groups


# ------------------------------------------------------------------ Walls (wallsurvey2)
def _walls(db, P, room, inside, floor, kind, purpose):
    import wallsurvey2
    sk = roomsurvey_kind(kind)
    hr = wallsurvey2.hang_rule(db, sk)
    lr = wallsurvey2.light_rule(db, sk)
    if not hr and not lr:
        return [], 'the wall survey is not learnt yet'
    fl = room['floor']
    ratios = []
    note = None
    if hr and hr.get('per_wall_tile') is not None:
        hangs = 0
        for r in inside:
            low = r['id'].lower()
            if r['type'] not in ('STAT', 'LIGH', 'ACTI', 'MISC') or not wallsurvey2.HANG.search(low) or wallsurvey2.NOT_HANG.search(low):
                continue
            hk = wallsurvey2._kind(low, wallsurvey2.HANG_KIND) or 'decor'
            up = r['_box'][2] - fl
            if hk == 'shelf' and up < 40:
                continue
            hangs += 1
        wall_tiles = sum(1 for t in room['_tiles'] for s in furnish.STEP if t['pat'][s] == 'wall')
        lam = float(hr['per_wall_tile']) * max(1, wall_tiles)
        # whether anything hangs here at all, as often as the game's rooms of the kind have something
        # (bare walls are usual in a passage, rare in a tavern); and, when something does, how many for
        # the length of wall
        p_any = min(0.98, max(0.02, float(hr.get('rooms_with') or 0.5)))
        ratios.append(_norm2(p_any if hangs else 1.0 - p_any))
        if hangs:
            ratios.append(_count_ratio(hangs, lam))
        if hangs > (hr.get('p90') or 8):
            note = '%d hangings; nine rooms in ten of the kind have %d or fewer' % (hangs, hr['p90'])
        elif not hangs and p_any >= 0.7:
            note = 'bare walls; %d rooms in 100 of the kind hang something' % round(100 * p_any)
    if lr and lr.get('per_9'):
        lights = [r for r in inside if r['type'] == 'LIGH']
        lam = sum(lr['per_9'].values()) * room['tiles'] / 9.0
        ratios.append(_count_ratio(len(lights), lam))
        if not lights and lam >= 1.5 and not note:
            note = 'no light; the game has about %.1f here' % lam
    return ratios, note


# ------------------------------------------------------------------ Faults (placecheck)
def _faults(db, P, room, inside, floor, kind, purpose):
    T = P['T']
    mine = []
    for i in P['issues']:
        if i.get('room') == room['name']:
            mine.append(i)
        elif not i.get('room') and i.get('x') is not None and _in_room(room, i['x'], i['y'], i.get('z', room['floor']), T, up=P['storey'] or 300):
            mine.append(i)
    cost = sum(FAULT_COST.get(i['kind'], 0.5) for i in mine)
    # (one value per room, not per fault: the term is a cost, scaled by how bare the room is, since a fault
    # in a room of six things shows more than one in a room of sixty)
    scale = 1.0 + len(inside) / 12.0
    value = math.exp(-cost / scale)
    note = None
    if mine:
        kinds = Counter(i['kind'] for i in mine)
        import placecheck
        note = ', '.join('%d %s' % (n, placecheck.LABEL.get(k, k).lower()) for k, n in kinds.most_common(3))
    return [value], note


# ------------------------------------------------------------------ Taste (catalogue, the taste set)
def _taste_rooms(db):
    """The exemplary places' rooms (taste.places), each as its kind and the count of each family in it;
    [] when the user has marked none."""
    import taste
    idx = _index.get('taste')
    keys = tuple(taste.places())
    if idx and idx[0] is db.recs and idx[1] == keys:
        return idx[2]
    out = []
    for ck in keys:
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        if not info['rooms']:
            continue
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in refs:
            r['_rfam'] = roomsurvey.family_of(db, r['id'], r['type'])
        for rm in info['rooms']:
            fl = rm['floor']
            fams = Counter(r['_rfam'] for r in refs if r['_rfam'] and rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                           and fl - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 200)
            counts = Counter({f: n for f, n in fams.items() if f in roomsurvey.FLOOR_KINDS})
            out.append({'cell': ck, 'kind': roomsurvey.room_kind(counts), 'fams': fams, 'tiles': rm['tiles']})
    _index['taste'] = (db.recs, keys, out)
    return out


def _taste(db, P, room, inside, floor, kind, purpose):
    import catalogue
    ratios = []
    notes = []
    style = P['prefix'] or '*'
    fl = room['floor']
    T = P['T']
    tables = [x for x in floor if x['_rfam'] in ('table', 'counter')]
    # rugs: under a table as often as the game puts them there (the catalogue's second habit)
    R = catalogue.rule(db, 'rugs', style)
    rugs = [x for x in inside if x['_rfam'] == 'rug' and not catalogue.is_round(db, x['id'])]
    if R and rugs and R.get('rect_under_table') is not None:
        beds = [x for x in floor if x['_rfam'] == 'bed']
        shares = {'table': float(R.get('rect_under_table') or 0) + 0.02, 'bed': float(R.get('rect_by_bed') or 0) + 0.02,
                  'centred': float(R.get('rect_centred') or 0) + 0.02}
        shares['other'] = max(0.02, 1.0 - shares['table'] - shares['bed'] - shares['centred'])
        rcx, rcy = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
        for x in rugs:
            bx = x['_box']
            under = any(o['_box'][0] < bx[3] and bx[0] < o['_box'][3] and o['_box'][1] < bx[4] and bx[1] < o['_box'][4] for o in tables)
            by_bed = any(_gap_xy(bx, o['_box']) < 60 for o in beds)
            centred = math.hypot((bx[0] + bx[3]) / 2 - rcx, (bx[1] + bx[4]) / 2 - rcy) < 0.35 * T
            where = 'table' if under else 'bed' if by_bed else 'centred' if centred else 'other'
            ratios.append(_norm(shares[where], list(shares.values())))
            if where == 'other' and shares['other'] < 0.25:
                notes.append('a rug under nothing')
    # plants in planters, never loose mid-floor; planters at walls and at posts (the third habit)
    Pl = catalogue.rule(db, 'plants', style)
    plants = [x for x in inside if catalogue.PLANT.search(x['id'].lower()) and not catalogue.PLANTER.search(x['id'].lower())]
    planters = [x for x in inside if x['_rfam'] == 'planter' or catalogue.PLANTER.search(x['id'].lower())]
    if Pl and plants and Pl.get('in_planter') is not None:
        p_in = min(0.98, max(0.02, float(Pl['in_planter'] or 0)))
        for x in plants:
            in_pl = any(o['_box'][0] - 12 <= x['p'][0] <= o['_box'][3] + 12 and o['_box'][1] - 12 <= x['p'][1] <= o['_box'][4] + 12 for o in planters if o is not x)
            ratios.append(_norm2(p_in if in_pl else 1.0 - p_in))
            if not in_pl and p_in >= 0.6:
                notes.append('a plant loose on the floor')
    Q = catalogue.rule(db, 'planters', style)
    if Q and planters and Q.get('at_wall') is not None:
        faces = _faces(room, T)
        shares = {'wall': float(Q.get('at_wall') or 0) + 0.02, 'column': float(Q.get('at_column') or 0) + 0.02, 'mid': float(Q.get('mid') or 0) + 0.02}
        cols = [a for a in P['arch'] if COLUMN.search(a['id'].lower()) and abs(a['p'][2] - fl) < 300]
        import wallsurvey2
        for x in planters:
            if x['_box'][2] > fl + 60:
                continue
            at_col = any(wallsurvey2.at_post(a, x['p'][0], x['p'][1]) for a in cols)
            at_wall = faces and _wall_dist(x['_box'], faces, T) <= 48
            where = 'column' if at_col else 'wall' if at_wall else 'mid'
            ratios.append(_norm(shares[where], list(shares.values())))
            if where == 'mid' and shares['mid'] < 0.2:
                notes.append('a planter out in the room')
    # a light at every stair foot (the first habit): the flights that start in this room
    S = catalogue.rule(db, 'stair_light', style)
    stairs = [a for a in P['arch'] if STAIR.search(a['id'].lower()) and _in_room(room, a['p'][0], a['p'][1], a['p'][2], T, up=300)]
    if S and stairs and S.get('lit') is not None:
        p_lit = min(0.98, max(0.02, float(S['lit'] or 0)))
        lights = [r for r in P['refs'] if r['type'] == 'LIGH']
        for a in stairs:
            bx = a.get('_box') or _box_of(a)
            lit = any(_gap_xy(bx, l['_box']) < T and abs(l['_box'][2] - fl) < 300 for l in lights if l.get('_box'))
            ratios.append(_norm2(p_lit if lit else 1.0 - p_lit))
            if not lit and p_lit >= 0.6:
                notes.append('a stair with no light at it')
    # the taste set: the nearest exemplary room of the kind, by the make-up of what stands in it
    ex = [r for r in P['taste_rooms'] if r['kind'] == roomsurvey_kind(kind)]
    if ex:
        mine = Counter(x['_rfam'] for x in inside if x['_rfam'])
        best = 0.0
        for r in ex:
            best = max(best, _cosine(mine, r['fams']))
        ratios.append(max(FLOOR, best))
        if best < 0.5:
            notes.append('unlike the exemplary %ss' % kind)
    note = notes[0] if notes else None
    return ratios, note


def _box_of(r):
    import fixit
    return fixit._world_box(r)


def _gap_xy(a, b):
    return max(a[0] - b[3], b[0] - a[3], a[1] - b[4], b[1] - a[4], 0)


def _cosine(a, b):
    keys = set(a) | set(b)
    if not keys:
        return 1.0
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if not na or not nb:
        return 0.0 if (na or nb) else 1.0
    return dot / (na * nb)


# ------------------------------------------------------------------ for people
def words(result):
    """A room's or a place's result in one line: 'Looks like the game: 62 (Standing 80, Fullness 40...)'."""
    if not result or result.get('score') is None:
        return 'No rooms to score here.'
    parts = []
    for t in TERMS:
        v = (result.get('terms') or {}).get(t)
        if v is not None:
            parts.append('%s %d' % (LABEL[t], round(v)))
    return 'Looks like the game: %d (%s)' % (round(result['score']), ', '.join(parts))
