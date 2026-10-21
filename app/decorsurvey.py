"""Where the game keeps its small decor in homes: lanterns, candles, standing lamps and small chests. On
what each stands (the floor, a table, a shelf, a counter, another chest, a cupboard; or hung up with
nothing under it) and, on the floor, where (a corner, along a wall, out in the room, at a bed's foot).
Auto-furnish goes by the shares: a lantern on a table or hung, a small chest on a shelf or at a bed, not
loose in the middle of the floor. A few minutes the first time (the game's rooms are walked as
roomsurvey.py walks them); kept in the cache folder after."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import furnish
import kits
import mapdata

KINDS = {'lantern': re.compile(r'lantern'), 'candle': re.compile(r'candle'), 'lamp': re.compile(r'lamp|torch|brazier|sconce')}
STRONGBOX = 48              # a chest up to this long is a strongbox (it goes on a shelf or a table)
SMALL_CHEST = 90            # up to this long, a small chest (a clothes chest that stands on the floor)
ON_KINDS = ('table', 'counter', 'shelf', 'bookshelf', 'chest', 'cupboard', 'bed', 'bench', 'crate', 'barrel')
HUNG = 100                  # a thing with nothing under it, its bottom this far up, is hung (from a hook, a beam)
LIMIT = 200
_cache = {}
_thread = {}


def kind_of(db, rid, tag, b):
    """lantern, candle, lamp (a light that stands or is fixed), small_chest, or None."""
    low = rid.lower()
    if tag == 'LIGH':
        for k, pat in KINDS.items():
            if pat.search(low):
                return k
        return None
    if tag in ('CONT', 'STAT', 'ACTI') and 'chest' in low and 'chestnut' not in low and b:
        if 'chest_small' in low or 'strongbox' in low or max(b[3] - b[0], b[4] - b[1]) <= STRONGBOX:
            return 'strongbox'
        if max(b[3] - b[0], b[4] - b[1]) <= SMALL_CHEST:
            return 'small_chest'
    return None


def placing(db, r, rm, refs, T=256, all_refs=None):
    """Where this thing is: {'on': floor|table|...|hung|other, 'up': its bottom above the room's floor,
    'where': corner|wall|middle (on the floor), 'by': bed|table|None (on the floor, close to one); for a
    hung thing 'above' (what it hangs from), 'gap_up' (to the ceiling, when all_refs has the building's
    pieces) and 'at_wall'}."""
    s = r.get('s') or 1.0
    b = r['b']
    bottom = r['p'][2] + b[2] * s
    up = bottom - rm['floor']
    out = {'on': 'floor', 'up': round(up), 'where': None, 'by': None}
    if up >= 12:
        # what is under it: furniture whose top is just under its bottom and whose footprint holds its point
        under = None
        for f in refs:
            if f is r or not f.get('b') or f.get('arch') or f['type'] in ('LIGH', 'NPC_', 'CREA', 'DOOR'):
                continue
            fs = f.get('s') or 1.0
            fb = furnish._footprint([v * fs for v in f['b']], f['p'][5], f['p'][0], f['p'][1])
            if not (fb[0] - 10 <= r['p'][0] <= fb[2] + 10 and fb[1] - 10 <= r['p'][1] <= fb[3] + 10):
                continue
            top = f['p'][2] + f['b'][5] * fs
            fbot = f['p'][2] + f['b'][2] * fs
            if fbot - 10 <= bottom <= top + 10 and (under is None or top > under[1]):
                under = (f, top)
        if under:
            fam = furnish_family(db, under[0])
            out['on'] = fam if fam in ON_KINDS else 'other'
            out['under'] = under[0]['id'].lower()
        elif up >= HUNG:
            out['on'] = 'hung'
            # what it hangs from: the nearest thing right above it (a hook, a rope, a beam), how far the
            # ceiling is above its top, and whether it is at a wall
            top = r['p'][2] + b[5] * s
            above, gap = None, None
            for f in refs + [a for a in all_refs if a.get('arch')] if all_refs is not None else refs:
                if f is r or not f.get('b'):
                    continue
                fs = f.get('s') or 1.0
                fb = furnish._footprint([v * fs for v in f['b']], f['p'][5], f['p'][0], f['p'][1])
                if not (fb[0] - 6 <= r['p'][0] <= fb[2] + 6 and fb[1] - 6 <= r['p'][1] <= fb[3] + 6):
                    continue
                fbot = f['p'][2] + f['b'][2] * fs
                if f.get('arch'):
                    if fbot >= top - 4 and (gap is None or fbot - top < gap):
                        gap = round(fbot - top)
                elif fbot >= top - 20 and fbot - top <= 80 and (above is None or fbot < above[1]):
                    above = (f['id'].lower(), fbot)
            out['above'] = above[0] if above else None
            out['gap_up'] = gap
            out['at_wall'] = min(r['p'][0] - rm['x_min'], rm['x_max'] - r['p'][0], r['p'][1] - rm['y_min'], rm['y_max'] - r['p'][1]) < 56
        else:
            out['on'] = 'other'            # (a ledge, a step: something the survey can't name)
    if out['on'] == 'floor':
        dx = min(r['p'][0] - rm['x_min'], rm['x_max'] - r['p'][0])
        dy = min(r['p'][1] - rm['y_min'], rm['y_max'] - r['p'][1])
        near = sum(1 for d in (dx, dy) if d < T * 0.35)
        out['where'] = 'corner' if near == 2 else 'wall' if near == 1 else 'middle'
        for f in refs:
            fam = furnish_family(db, f)
            if fam in ('bed', 'table') and f.get('b') and abs(f['p'][2] - r['p'][2]) < 100:
                fs = f.get('s') or 1.0
                fb = furnish._footprint([v * fs for v in f['b']], f['p'][5], f['p'][0], f['p'][1])
                if fb[0] - 60 <= r['p'][0] <= fb[2] + 60 and fb[1] - 60 <= r['p'][1] <= fb[3] + 60:
                    out['by'] = fam
                    break
    return out


_fam = {}


def furnish_family(db, r):
    key = (r['id'].lower(), r['type'])
    if key not in _fam:
        import roomsurvey
        _fam[key] = roomsurvey.family_of(db, r['id'], r['type'])
    return _fam[key]


def _disk(db):
    import taste
    return taste.cache_file('decorsurvey_%s_v4' % taste.sig(db))


def survey(db, limit=LIMIT):
    """{'cells', 'kinds': {kind: {'n', 'on': {what: n}, 'where': {corner|wall|middle: n}, 'by': {bed|table: n},
    'hung_up': median height of the hung ones' bottoms above the floor, 'ids': {id: {'n', 'on': {...},
    'hung_up'}}}}, 'rooms': {kind|room kind: {'n', 'on': {...}}}} over the game's own homes (house, manor)."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = None
    try:
        path = _disk(db)
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache['survey'] = (db.recs, saved)
        return saved
    except Exception:
        pass
    import roomsurvey
    K = defaultdict(lambda: {'n': 0, 'on': Counter(), 'where': Counter(), 'by': Counter(), 'ups': [], 'ids': {},
                             'above': Counter(), 'gaps': [], 'at_wall': 0, 'under': Counter()})
    R = defaultdict(lambda: {'n': 0, 'on': Counter()})
    rooms_seen = Counter()
    seen = 0
    import taste
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    cells = taste.order(cells)             # (the exemplary places first, each counted several times over)
    for ck in cells:
        if seen >= limit:
            break
        if roomsurvey.theme_of(ck) not in ('house', 'manor') and not taste.is_marked(ck):
            continue
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        if not info['rooms'] or info['tile'] != 256:
            continue
        seen += 1
        T = info['tile']
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        arch = [r for r in info['refs'] if r.get('b') and r.get('arch')]
        for rm in info['rooms']:
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and rm['floor'] - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= rm['floor'] + 400]
            shell = [r for r in arch if rm['x_min'] - 64 <= r['p'][0] <= rm['x_max'] + 64 and rm['y_min'] - 64 <= r['p'][1] <= rm['y_max'] + 64
                     and rm['floor'] - 64 <= r['p'][2] <= rm['floor'] + 700]
            floor = [r for r in inside if furnish_family(db, r) in roomsurvey.FLOOR_KINDS]
            room_kind = roomsurvey.room_kind(Counter(furnish_family(db, r) for r in floor))
            rooms_seen[room_kind] += 1
            rooms_seen['*'] += 1
            for r in inside:
                k = kind_of(db, r['id'], r['type'], r['b'])
                if not k:
                    continue
                p = placing(db, r, rm, inside, T, all_refs=shell)
                D = K[k]
                D['n'] += 1
                D['on'][p['on']] += 1
                if p['where']:
                    D['where'][p['where']] += 1
                if p['by']:
                    D['by'][p['by']] += 1
                if p['on'] == 'hung':
                    D['ups'].append(p['up'])
                    D['above'][p['above'] or '-'] += 1
                    if p['gap_up'] is not None:
                        D['gaps'].append(p['gap_up'])
                    D['at_wall'] += 1 if p['at_wall'] else 0
                elif p['on'] not in ('floor', 'other'):
                    D['under'][p['under']] += 1
                I = D['ids'].setdefault(r['id'].lower(), {'n': 0, 'on': Counter(), 'ups': [], 'gaps': [], 'above': Counter()})
                I['n'] += 1
                I['on'][p['on']] += 1
                if p['on'] == 'hung':
                    I['ups'].append(p['up'])
                    I['above'][p['above'] or '-'] += 1
                    if p['gap_up'] is not None:
                        I['gaps'].append(p['gap_up'])
                RR = R[k + '|' + room_kind]
                RR['n'] += 1
                RR['on'][p['on']] += 1
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    out = {'cells': seen, 'kinds': {}, 'rooms': {}, 'rooms_seen': dict(rooms_seen)}
    for k, D in K.items():
        ids = {i: {'n': v['n'], 'on': dict(v['on']), 'hung_up': med(v['ups']), 'gap_up': med(v['gaps']), 'above': v['above'].most_common(3)}
               for i, v in D['ids'].items() if v['n'] >= 3}
        out['kinds'][k] = {'n': D['n'], 'on': dict(D['on']), 'where': dict(D['where']), 'by': dict(D['by']),
                           'hung_up': med(D['ups']), 'gap_up': med(D['gaps']), 'above': D['above'].most_common(12),
                           'at_wall': D['at_wall'], 'under': D['under'].most_common(12),
                           'ids': dict(sorted(ids.items(), key=lambda kv: -kv[1]['n'])[:40])}
    for k, RR in R.items():
        out['rooms'][k] = {'n': RR['n'], 'on': dict(RR['on'])}
    _cache['survey'] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def ready(db):
    """The survey when it's to hand (in memory or on disk); otherwise None, with the survey started in
    the background so it's there next time (a few minutes the first time)."""
    import taste
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    t = _thread.get('t')
    if t is None or not t.is_alive():
        import background
        _thread['t'] = background.start('where the game hangs lanterns and keeps its strongboxes', lambda: survey(db), task=('decorsurvey', 'survey', []))
    return taste.stale(_cache, 'survey', db.recs, _disk(db))


def shares(db, kind, room_kind=None):
    """{'on': {what: share}, 'where': {corner|wall|middle: share of the floor ones}, 'by': {bed|table: share
    of the floor ones}, 'hung_up': height} for a kind of thing (in rooms of a kind when the game has
    enough of them there), or None while the survey runs."""
    s = ready(db)
    if not s or kind not in s['kinds']:
        return None
    D = s['kinds'][kind]
    on = D['on']
    if room_kind and s['rooms'].get(kind + '|' + room_kind, {}).get('n', 0) >= 30:
        on = s['rooms'][kind + '|' + room_kind]['on']
    n = float(sum(on.values()) or 1)
    nf = float(sum(D['where'].values()) or 1)
    return {'n': D['n'], 'on': {k: round(v / n, 3) for k, v in on.items()}, 'where': {k: round(v / nf, 3) for k, v in D['where'].items()},
            'by': {k: round(v / nf, 3) for k, v in D['by'].items()}, 'hung_up': D['hung_up']}


def model_on(db, rid, kind):
    """How the game keeps this very model: {what: share} by id, or None when it is seen fewer than 3 times."""
    s = ready(db)
    if not s or kind not in s['kinds']:
        return None
    I = s['kinds'][kind]['ids'].get(rid.lower())
    if not I:
        return None
    n = float(sum(I['on'].values()) or 1)
    return {'on': {k: round(v / n, 3) for k, v in I['on'].items()}, 'hung_up': I['hung_up'], 'n': I['n']}


def hung_per_room(db, room_kind=None):
    """How many lanterns and lamps hang in a room of this kind in the game's homes (all kinds when it
    has too few of the kind); None while the survey runs."""
    s = ready(db)
    if not s or not s.get('rooms_seen'):
        return None
    kinds = ('lantern', 'lamp')
    if room_kind and s['rooms_seen'].get(room_kind, 0) >= 30:
        n = sum(s['rooms'].get(k + '|' + room_kind, {}).get('on', {}).get('hung', 0) for k in kinds)
        return n / float(s['rooms_seen'][room_kind])
    n = sum(s['kinds'].get(k, {}).get('on', {}).get('hung', 0) for k in kinds)
    return n / float(s['rooms_seen']['*'])


def off_floor(db, rid):
    """A chest the game keeps off the floor (a strongbox on a shelf, a table, a counter): by what the
    survey saw of the model, else by its size (a chest_small_* is one)."""
    ri = db.resolve_id(rid)
    if ri is None:
        return False
    b = mapdata.object_bounds(db, ri)
    k = kind_of(db, rid, db.recs[ri][0], b)
    if not k:
        return False
    m = model_on(db, rid, k)
    if m and m['n'] >= 5:
        # (a strongbox stands on the floor only when the game mostly keeps that model there)
        return m['on'].get('floor', 0) < (0.5 if k == 'strongbox' else 0.3)
    return k == 'strongbox'


def hangs(db, rid):
    """How a light is kept: ('hung', bottom height above the floor, gap under the ceiling) when the game
    hangs the model more often than not, ('floor', 0, None) when it stands, None when unknown."""
    for k in ('lantern', 'lamp', 'candle'):
        m = model_on(db, rid, k)
        if m and m['n'] >= 3:
            if m['on'].get('hung', 0) >= 0.5:
                s = ready(db)['kinds'][k]['ids'][rid.lower()]
                return 'hung', m['hung_up'], s.get('gap_up')
            if m['on'].get('floor', 0) >= 0.4:
                return 'floor', 0, None
            return 'furniture', 0, None
    low = rid.lower()
    if 'lantern' in low:
        return 'hung', 170, None
    return None


def report(db):
    """For people: the shares, in words."""
    s = survey(db)
    out = ['%d homes walked' % s['cells']]
    for k, D in s['kinds'].items():
        n = float(D['n'] or 1)
        on = ', '.join('%s %d%%' % (w, round(100 * v / n)) for w, v in sorted(D['on'].items(), key=lambda kv: -kv[1]))
        nf = float(sum(D['where'].values()) or 1)
        wh = ', '.join('%s %d%%' % (w, round(100 * v / nf)) for w, v in sorted(D['where'].items(), key=lambda kv: -kv[1]))
        by = ', '.join('%s %d%%' % (w, round(100 * v / nf)) for w, v in sorted(D['by'].items(), key=lambda kv: -kv[1]))
        out.append('%s: %d seen; on: %s; of those on the floor: %s; by a %s; hung %s up, %s under the ceiling, at a wall %d of %d, from %s; under them when on something: %s'
                   % (k, D['n'], on, wh, by or 'nothing', D['hung_up'], D['gap_up'], D['at_wall'], D['on'].get('hung', 0), D['above'][:6], D['under'][:8]))
    return out
