"""How the game's own places build their counters and bars: every counter and bar segment model (the
Bethesda furn_com and furn_de bar pieces, Tamriel Data's bars and counters, the Imperial shop counters),
where it stands (which kind of room, which kind of place), how the runs are composed (segments in order:
straight, corner and end pieces; straight runs, L-shapes and U-shapes; whether a run ends at a wall or
with an end piece), how far the run stands from the wall behind it (the keeper's side and its clearance),
how it faces the room's door, what stands on the segments (the wares, per trade) and behind them (shelves,
barrels, the keeper's stool), and how often a segment stands alone or bare. Auto-furnish lays its
counters as runs drawn from these compositions (furnish.lay_counter_run) rather than one segment at a
time. Kept in the cache folder once done; ready() runs it in the background the first time."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey

LIMIT = 300
LINK = 200                 # two segments this close (origin to origin, on one floor) are one run
END = re.compile(r'_end|end_?\d|_ends?$')
CORNER = re.compile(r'_cnr|corner|_crn|_curve|_bend')
WARE_TYPES = ('MISC', 'INGR', 'ALCH', 'BOOK', 'WEAP', 'ARMO', 'CLOT', 'APPA', 'LIGH', 'CONT', 'PROB', 'REPA', 'LOCK')
_cache = {}
_thread = {}


def role_of(rid):
    """What part of a run a segment model is: 'end', 'corner' or 'straight'."""
    low = rid.lower()
    if CORNER.search(low):
        return 'corner'
    if END.search(low):
        return 'end'
    return 'straight'


def _disk(db, limit):
    import taste
    return taste.cache_file('countersurvey_%s_%d_v2' % (taste.sig(db), limit))


def ready(db, limit=LIMIT):
    import taste
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db, limit)):
            return survey(db, limit)
    except Exception:
        return None
    t = _thread.get('t')
    if t is None or not t.is_alive():
        try:
            import background
            _thread['t'] = background.start('how the game builds its counters and bars', lambda: survey(db, limit),
                                            task=('countersurvey', 'survey', [limit]))
        except Exception:
            t = threading.Thread(target=lambda: survey(db, limit), daemon=True)
            _thread['t'] = t
            t.start()
    return taste.stale(_cache, key, db.recs, _disk(db, limit))


def survey(db, limit=LIMIT):
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db, limit)
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache[key] = (db.recs, saved)
        return saved
    except Exception:
        pass
    out = _survey(db, limit)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def _box(r):
    import fixit
    return fixit._world_box(r)


def _survey(db, limit):
    import taste
    runs = []                                   # one row per run
    per_model = defaultdict(lambda: {'n': 0, 'alone': 0, 'bare': 0, 'wares': Counter(), 'kinds': Counter(), 'on_n': []})
    seen = 0
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    cells = taste.spread(cells, limit)
    for ck in cells:
        if seen >= limit:
            break
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        if not info['rooms'] or info['tile'] != 256:
            continue
        T = info['tile']
        arch = [r for r in info['refs'] if r.get('arch') and r.get('b')]
        styles = Counter(kits.kit_prefix(r['id']) for r in arch if kits.kit_prefix(r['id']))
        style = styles.most_common(1)[0][0] if styles else '?'
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'LEVC')]
        doors = [r for r in refs if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()]
        refs = [r for r in refs if r['type'] != 'DOOR']
        for r in refs:
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
        segs_all = [r for r in refs if r['_fam'] == 'counter']
        if not segs_all:
            continue
        seen += 1
        theme = roomsurvey.theme_of(ck)
        npcs = [r for r in info['refs'] if r['type'] == 'NPC_']
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and fl - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 400]
            segs = [r for r in inside if r['_fam'] == 'counter' and r['p'][2] + r['b'][2] * (r.get('s') or 1) < fl + 60]
            if not segs:
                continue
            floor = [r for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS]
            kind = roomsurvey.room_kind(Counter(r['_fam'] for r in floor))
            # runs: segments within LINK of one another
            left = list(range(len(segs)))
            groups = []
            while left:
                grp = [left.pop(0)]
                i = 0
                while i < len(grp):
                    a = segs[grp[i]]
                    for j in list(left):
                        b = segs[j]
                        if math.hypot(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1]) <= LINK:
                            grp.append(j)
                            left.remove(j)
                    i += 1
                groups.append([segs[i_] for i_ in grp])
            room_doors = [d for d in doors if rm['x_min'] - 60 <= d['p'][0] <= rm['x_max'] + 60 and rm['y_min'] - 60 <= d['p'][1] <= rm['y_max'] + 60
                          and fl - 60 <= d['p'][2] <= fl + 200]
            for grp in groups:
                boxes = [_box(s) for s in grp]
                # order along the run: chain nearest neighbours from an end
                order = [max(range(len(grp)), key=lambda i: sum(math.hypot(grp[i]['p'][0] - grp[j]['p'][0], grp[i]['p'][1] - grp[j]['p'][1]) for j in range(len(grp))))]
                while len(order) < len(grp):
                    last = grp[order[-1]]
                    nxt = min((i for i in range(len(grp)) if i not in order), key=lambda i: math.hypot(grp[i]['p'][0] - last['p'][0], grp[i]['p'][1] - last['p'][1]))
                    order.append(nxt)
                chain = [grp[i] for i in order]
                roles = [role_of(s['id']) for s in chain]
                # shape: direction changes along the chain
                turns = 0
                for i in range(1, len(chain) - 1):
                    v1 = (chain[i]['p'][0] - chain[i - 1]['p'][0], chain[i]['p'][1] - chain[i - 1]['p'][1])
                    v2 = (chain[i + 1]['p'][0] - chain[i]['p'][0], chain[i + 1]['p'][1] - chain[i]['p'][1])
                    n1, n2 = math.hypot(*v1) or 1, math.hypot(*v2) or 1
                    if abs(v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2) < 0.5:
                        turns += 1
                shape = 'single' if len(chain) == 1 else 'straight' if turns == 0 else 'L' if turns == 1 else 'U'
                # the run's box and axis
                rb = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[3] for b in boxes), max(b[4] for b in boxes))
                along_x = (rb[2] - rb[0]) >= (rb[3] - rb[1])
                # the wall behind: of the two sides across the run's axis, the one nearer a room edge
                if along_x:
                    d_lo, d_hi = rb[1] - rm['y_min'], rm['y_max'] - rb[3]
                else:
                    d_lo, d_hi = rb[0] - rm['x_min'], rm['x_max'] - rb[2]
                keeper_gap = min(d_lo, d_hi) - 16          # (16: the wall face stands that far in from the tile edge)
                keeper_side = ('S' if d_lo <= d_hi else 'N') if along_x else ('W' if d_lo <= d_hi else 'E')
                open_dir = {'S': (0, 1), 'N': (0, -1), 'W': (1, 0), 'E': (-1, 0)}[keeper_side]
                # the run's ends: at a wall (the run's end within 48 of a room edge along its axis) or an end piece
                if along_x:
                    at_wall_ends = sum(1 for e in (rb[0] - rm['x_min'], rm['x_max'] - rb[2]) if e < 48)
                else:
                    at_wall_ends = sum(1 for e in (rb[1] - rm['y_min'], rm['y_max'] - rb[3]) if e < 48)
                end_pieces = sum(1 for r_ in roles if r_ == 'end')
                # the door: does the run's open side face it, and how far
                mx, my = (rb[0] + rb[2]) / 2, (rb[1] + rb[3]) / 2
                door_d = door_face = None
                if room_doors:
                    d_ = min(room_doors, key=lambda d: math.hypot(d['p'][0] - mx, d['p'][1] - my))
                    vx, vy = d_['p'][0] - mx, d_['p'][1] - my
                    vn = math.hypot(vx, vy) or 1
                    door_d = round(vn)
                    door_face = round((vx * open_dir[0] + vy * open_dir[1]) / vn, 2)
                # what stands on the run and behind it
                on = Counter()
                on_ids = Counter()
                n_on = 0
                for o in inside:
                    if o in grp or o['type'] not in WARE_TYPES:
                        continue
                    for b in boxes:
                        if b[0] - 6 <= o['p'][0] <= b[3] + 6 and b[1] - 6 <= o['p'][1] <= b[4] + 6 and b[2] + 20 <= o['p'][2] + o['b'][2] * (o.get('s') or 1) <= b[5] + 40:
                            on[o['_fam'] or o['type']] += 1
                            on_ids[o['id'].lower()] += 1
                            n_on += 1
                            break
                behind = Counter()
                bx0 = (rb[0], rb[1], rb[2], rb[3])
                for o in floor:
                    if o in grp:
                        continue
                    ob = _box(o)
                    if not ob:
                        continue
                    # behind: on the keeper's side of the run, within 220 across and within the run's span
                    if along_x:
                        span = ob[3] > rb[0] - 60 and ob[0] < rb[2] + 60
                        back = (rb[1] - ob[4] if keeper_side == 'S' else ob[1] - rb[3])
                    else:
                        span = ob[4] > rb[1] - 60 and ob[1] < rb[3] + 60
                        back = (rb[0] - ob[3] if keeper_side == 'W' else ob[0] - rb[2])
                    if span and -20 <= back <= 220:
                        behind[o['_fam']] += 1
                keeper_npc = any(abs(n_['p'][0] - mx) < (rb[2] - rb[0]) / 2 + 100 and abs(n_['p'][1] - my) < (rb[3] - rb[1]) / 2 + 100
                                 and ((n_['p'][1] < rb[1] if keeper_side == 'S' else n_['p'][1] > rb[3]) if along_x else (n_['p'][0] < rb[0] if keeper_side == 'W' else n_['p'][0] > rb[2]))
                                 for n_ in npcs if abs(n_['p'][2] - fl) < 200)
                runs.append({'cell': ck, 'style': style, 'theme': theme, 'kind': kind, 'n': len(chain), 'shape': shape,
                             'models': [s['id'].lower() for s in chain], 'roles': roles, 'length': round(max(rb[2] - rb[0], rb[3] - rb[1])),
                             'keeper_gap': round(keeper_gap), 'at_wall_ends': at_wall_ends, 'end_pieces': end_pieces,
                             'door_d': door_d, 'door_face': door_face, 'on': dict(on), 'on_n': n_on, 'on_ids': on_ids.most_common(12),
                             'behind': dict(behind), 'keeper_npc': keeper_npc,
                             'rzs': [round(s['p'][5], 4) for s in chain], 'scales': [s.get('s') or 1.0 for s in chain],
                             'offsets': [[round(s['p'][0] - chain[0]['p'][0], 1), round(s['p'][1] - chain[0]['p'][1], 1)] for s in chain],
                             'open': list(open_dir), 'keeper_side': keeper_side})
                for s in chain:
                    M = per_model[s['id'].lower()]
                    M['n'] += 1
                    M['alone'] += 1 if len(chain) == 1 else 0
                    M['kinds'][kind] += 1
                    b = _box(s)
                    mine_on = [o for o in inside if o not in grp and o['type'] in WARE_TYPES and b[0] - 6 <= o['p'][0] <= b[3] + 6 and b[1] - 6 <= o['p'][1] <= b[4] + 6
                               and b[2] + 20 <= o['p'][2] + o['b'][2] * (o.get('s') or 1) <= b[5] + 40]
                    M['bare'] += 1 if not mine_on else 0
                    M['on_n'].append(len(mine_on))
                    M['wares'].update(o['id'].lower() for o in mine_on)
    return _fold(seen, runs, per_model)


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _fold(seen, runs, per_model):
    out = {'cells': seen, 'runs': runs, 'models': {}, 'styles': {}}
    for m, M in per_model.items():
        out['models'][m] = {'n': M['n'], 'role': role_of(m), 'alone': round(M['alone'] / float(M['n']), 2), 'bare': round(M['bare'] / float(M['n']), 2),
                            'on_med': _med(M['on_n']), 'kinds': dict(M['kinds'].most_common()), 'wares': M['wares'].most_common(20)}
    by = defaultdict(list)
    for r in runs:
        by[r['style']].append(r)
        by['*'].append(r)
    for st, rs in by.items():
        comps = Counter((r['shape'], '-'.join(r['roles'])) for r in rs)
        out['styles'][st] = {
            'runs': len(rs), 'segments': _med([r['n'] for r in rs]), 'segments_mean': round(sum(r['n'] for r in rs) / float(len(rs)), 2),
            'shapes': dict(Counter(r['shape'] for r in rs)), 'kinds': dict(Counter(r['kind'] for r in rs).most_common()),
            'themes': dict(Counter(r['theme'] for r in rs).most_common()),
            'keeper_gap': _med([r['keeper_gap'] for r in rs]), 'keeper_gap_dist': dict(Counter(min(int(max(0, r['keeper_gap']) // 32) * 32, 256) for r in rs)),
            'ends_at_wall': round(sum(r['at_wall_ends'] for r in rs) / float(2 * len(rs)), 2),
            'ends_with_piece': round(sum(min(r['end_pieces'], 2) for r in rs) / float(2 * len(rs)), 2),
            'door_d': _med([r['door_d'] for r in rs if r['door_d'] is not None]),
            'faces_door': round(sum(1 for r in rs if r['door_face'] is not None and r['door_face'] > 0.3) / float(max(1, sum(1 for r in rs if r['door_face'] is not None))), 2),
            'on_per_segment': round(sum(r['on_n'] for r in rs) / float(sum(r['n'] for r in rs)), 2),
            'bare_runs': round(sum(1 for r in rs if r['on_n'] == 0) / float(len(rs)), 2),
            'on_kinds': dict(sum((Counter(r['on']) for r in rs), Counter()).most_common(10)),
            'behind': {k: round(v / float(len(rs)), 2) for k, v in sum((Counter(r['behind']) for r in rs), Counter()).most_common(10)},
            'keeper_npc': round(sum(1 for r in rs if r['keeper_npc']) / float(len(rs)), 2),
            'compositions': [[s, c, n] for (s, c), n in comps.most_common(12)]}
    return out


MAKE = (('dunmer', ('furn_de', 't_de_')), ('imperial', ('furn_com', 't_imp', 't_com', 'furn_imp')))


def make_of(model):
    """Whose make a counter model is ('dunmer', 'imperial' or None): a Hlaalu house takes the Dunmer bars,
    a Common one the Imperial counters, whatever the style's own runs number."""
    low = model.lower()
    for name, pres in MAKE:
        if low.startswith(pres):
            return name
    return None


def compositions(db, style, kind=None, culture=None):
    """The game's counter runs of this style (its kit prefix; with fewer than three, every style's runs of
    the house's culture's make, then every run), as laid: [run rows] with 'models', 'rzs' (each segment's
    turn), 'scales', 'offsets' (from the first segment, in the world), 'open' (the direction the run faces
    into the room), 'shape', 'n', 'keeper_gap'; runs of two or more segments, and singles only of a model
    that stands alone in the game at least one time in three. None until surveyed."""
    s = ready(db)
    if not s:
        return None
    rs = [r for r in s['runs'] if r['style'] == style]
    if len(rs) < 3:
        rs = s['runs']
        if culture:
            own = [r for r in rs if make_of(r['models'][0]) == culture]
            if len(own) >= 3:
                rs = own
    if kind:
        own = [r for r in rs if r['kind'] == kind]
        if len(own) >= 3:
            rs = own
    good = []
    for r in rs:
        if r['n'] >= 2:
            good.append(r)
        else:
            M = s['models'].get(r['models'][0], {})
            if M.get('alone', 0) >= 0.33 and role_of(r['models'][0]) == 'straight':
                good.append(r)
    return good


def rule(db, style):
    """The style's figures (its own when it has 5 runs, else every style's): keeper gap, behind rates,
    faces-door share, wares per segment; None until surveyed."""
    s = ready(db)
    if not s:
        return None
    st = s['styles'].get(style) if style else None
    if st and st['runs'] >= 5:
        return dict(st, style=style, own=True)
    allr = s['styles'].get('*')
    return dict(allr, style='*', own=False) if allr else None


def report(db):
    s = survey(db)
    lines = ['%d places with counters walked, %d runs, %d models' % (s['cells'], len(s['runs']), len(s['models']))]
    for st, S in sorted(s['styles'].items(), key=lambda kv: -kv[1]['runs']):
        if S['runs'] < 3:
            continue
        lines.append('== %s: %d runs; segments median %s (mean %s); shapes %s; rooms %s; places %s' % (st, S['runs'], S['segments'], S['segments_mean'], S['shapes'], S['kinds'], S['themes']))
        lines.append('   keeper gap median %s (%s); ends at a wall %s, with an end piece %s; door distance %s, open side faces the door %s; keeper standing behind %s' % (
            S['keeper_gap'], S['keeper_gap_dist'], S['ends_at_wall'], S['ends_with_piece'], S['door_d'], S['faces_door'], S['keeper_npc']))
        lines.append('   on the segments %s per segment (%s of runs bare): %s; behind (per run): %s' % (S['on_per_segment'], S['bare_runs'], S['on_kinds'], S['behind']))
        lines.append('   compositions: %s' % S['compositions'][:8])
    lines.append('== models')
    for m, M in sorted(s['models'].items(), key=lambda kv: -kv[1]['n'])[:30]:
        lines.append('   %-36s n %3d %-8s alone %.0f%% bare %.0f%% on median %s rooms %s wares %s' % (m, M['n'], M['role'], 100 * M['alone'], 100 * M['bare'], M['on_med'], M['kinds'], M['wares'][:5]))
    return '\n'.join(lines)
