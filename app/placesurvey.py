"""Where the game stands each kind of furniture in a room, measured: how far from the nearest wall
(against it, a step off it, out in the room), how often in a corner, how often at the foot of a
free-standing column, and which wall it chooses (the wall opposite the door, the door's own wall,
beside the doorway, a long wall or a short one, a wall with a window). Measured over the game's own
kit-built interiors (never the mod's), as the bed survey was: 1,628 beds, chests across the foot
441 to 167. Auto-furnish's wall slots and its "centre" and "corner" rules go by it (placesurvey.prefs).

Kept in the cache folder once done (a few minutes); ready() runs it in the background the first time.
An exemplary place (taste.py) counts several times over."""
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

LIMIT = 200
AT_WALL = 40            # a box edge this close to a wall's face is against it
NEAR_WALL = 110         # a step off it
CORNER = 0.55           # a box middle within this many tiles of a corner is in the corner
COLUMN = re.compile(r'pillar|column|post|colum')
WINDOW = re.compile(r'win(dow)?(_|$|\d)')
FAMS = tuple(roomsurvey.FLOOR_KINDS) + ('planter', 'screen', 'basket')
_cache = {}
_thread = {}


def _disk(db, limit):
    import taste
    return taste.cache_file('placesurvey_%s_%d_v1' % (taste.sig(db), limit))


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background
    (while a survey for a changed taste set runs, the newest earlier one stands in)."""
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
        import background
        _thread['t'] = background.start('where the game stands each kind of furniture', lambda: survey(db, limit), task=('placesurvey', 'survey', [limit]))
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


def room_sides(rm, T, doors, arch):
    """What each side of a room is: {'N': {'door': bool, 'window': bool, 'long': bool, 'door_along':
    [along coordinates of its doorways]}, ...}, from its tiles, the doors and frames on its edge and
    the window props against its walls."""
    long_x = (rm['x_max'] - rm['x_min']) >= (rm['y_max'] - rm['y_min'])
    out = {s: {'door': False, 'window': False, 'long': (s in ('N', 'S')) == long_x, 'door_along': []} for s in furnish.STEP}
    edge = {'N': rm['y_max'], 'S': rm['y_min'], 'E': rm['x_max'], 'W': rm['x_min']}
    for t in rm['_tiles']:
        for s in furnish.STEP:
            if t['pat'][s] == 'door':
                out[s]['door'] = True
                out[s]['door_along'].append(t['x'] if s in ('N', 'S') else t['y'])
    for d in doors:
        if not (rm['floor'] - 60 <= d['p'][2] <= rm['floor'] + 200):
            continue
        x, y = d['p'][0], d['p'][1]
        for s in furnish.STEP:
            on = abs((y if s in ('N', 'S') else x) - edge[s]) < 48
            span_ok = (rm['x_min'] - 20 <= x <= rm['x_max'] + 20) if s in ('N', 'S') else (rm['y_min'] - 20 <= y <= rm['y_max'] + 20)
            if on and span_ok:
                out[s]['door'] = True
                out[s]['door_along'].append(x if s in ('N', 'S') else y)
    for a in arch:
        if not WINDOW.search(a['id'].lower()) or not (rm['floor'] - 60 <= a['p'][2] <= rm['floor'] + 400):
            continue
        x, y = a['p'][0], a['p'][1]
        for s in furnish.STEP:
            on = abs((y if s in ('N', 'S') else x) - edge[s]) < 80
            span_ok = (rm['x_min'] - 20 <= x <= rm['x_max'] + 20) if s in ('N', 'S') else (rm['y_min'] - 20 <= y <= rm['y_max'] + 20)
            if on and span_ok:
                out[s]['window'] = True
    return out


def wall_class(side, sides):
    """How the game would name this wall: 'opposite_door', 'door_wall', 'window', 'long', 'short'
    (the first that fits; a windowed wall counts as a window wall before long or short)."""
    opp = furnish.OPP[side]
    S = sides[side]
    if S['door']:
        return 'door_wall'
    if sides[opp]['door'] and not S['door']:
        return 'opposite_door'
    if S['window']:
        return 'window'
    return 'long' if S['long'] else 'short'


def _survey(db, limit):
    import taste
    F = defaultdict(lambda: {'n': 0, 'd_wall': [], 'at': Counter(), 'corner': 0, 'col_rooms': 0, 'at_col': 0,
                             'wall': Counter(), 'beside_door': 0, 'at_wall_n': 0})
    FK = defaultdict(lambda: {'n': 0, 'at': Counter(), 'corner': 0, 'wall': Counter()})
    seen = 0
    cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                   and lst[-1] not in db.dead and kits.game_made(db, k))
    cells = taste.spread(cells, limit)      # (over the whole list: Bethesda's towns as well as TR's)
    for ck in cells:
        if seen >= limit:
            break
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            continue
        if not info['rooms'] or info['tile'] != 256:
            continue
        seen += 1
        T = info['tile']
        arch = [r for r in info['refs'] if r.get('b') and r.get('arch')]
        doors = [r for r in info['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()]
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in refs:
            r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in refs if rm['x_min'] <= r['p'][0] <= rm['x_max'] and rm['y_min'] <= r['p'][1] <= rm['y_max']
                      and fl - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= fl + 160 and r['_fam'] in FAMS]
            if not inside:
                continue
            floor = [r for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS]
            kind = roomsurvey.room_kind(Counter(r['_fam'] for r in floor))
            sides = room_sides(rm, T, doors, arch)
            # the walls: each tile side that is a wall, as a segment on the wall's face
            walls = []
            corners = []
            for t in rm['_tiles']:
                for s, (dx, dy) in furnish.STEP.items():
                    if t['pat'][s] != 'wall':
                        continue
                    off = t['pat']['offset'].get(s, T / 2 - 16)
                    if s in ('N', 'S'):
                        walls.append((s, t['y'] + dy * off, t['x'] - T / 2, t['x'] + T / 2))
                    else:
                        walls.append((s, t['x'] + dx * off, t['y'] - T / 2, t['y'] + T / 2))
                # a corner: two walls meeting at this tile
                for sa, sb in (('N', 'E'), ('N', 'W'), ('S', 'E'), ('S', 'W')):
                    if t['pat'][sa] == 'wall' and t['pat'][sb] == 'wall':
                        corners.append((t['x'] + furnish.STEP[sb][0] * T / 2, t['y'] + furnish.STEP[sa][1] * T / 2))
            # free-standing columns in the room: a small square piece standing clear of the walls
            cols = []
            for a in arch:
                low = a['id'].lower()
                if not COLUMN.search(low) or not (fl - 60 <= a['p'][2] <= fl + 200):
                    continue
                if not (rm['x_min'] + T * 0.3 <= a['p'][0] <= rm['x_max'] - T * 0.3 and rm['y_min'] + T * 0.3 <= a['p'][1] <= rm['y_max'] - T * 0.3):
                    continue
                bx = _box(a)
                if bx and max(bx[3] - bx[0], bx[4] - bx[1]) <= T * 0.6:
                    cols.append(bx)
            for r in inside:
                bx = _box(r)
                if not bx:
                    continue
                fam = r['_fam']
                D = F[fam]
                DK = FK[kind + '|' + fam]
                D['n'] += 1
                DK['n'] += 1
                # distance from the box to the nearest wall face it lies along
                best = None
                for s, face, a0, a1 in walls:
                    if s in ('N', 'S'):
                        if bx[3] < a0 - 20 or bx[0] > a1 + 20:
                            continue
                        d = (face - bx[4]) if s == 'N' else (bx[1] - face)
                    else:
                        if bx[4] < a0 - 20 or bx[1] > a1 + 20:
                            continue
                        d = (face - bx[3]) if s == 'E' else (bx[0] - face)
                    d = max(-40.0, d)
                    if best is None or d < best[0]:
                        best = (d, s, (a0 + a1) / 2)
                if best is None:
                    continue
                d, s, along = best
                D['d_wall'].append(round(d))
                at = 'wall' if d <= AT_WALL else 'near' if d <= NEAR_WALL else 'middle'
                D['at'][at] += 1
                DK['at'][at] += 1
                cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
                if corners and min(math.hypot(cx - qx, cy - qy) for qx, qy in corners) < CORNER * T:
                    D['corner'] += 1
                    DK['corner'] += 1
                if cols:
                    D['col_rooms'] += 1
                    if any(max(c[0] - bx[3], bx[0] - c[3], c[1] - bx[4], bx[1] - c[4], 0) < 60 for c in cols):
                        D['at_col'] += 1
                if at == 'wall':
                    D['at_wall_n'] += 1
                    wc = wall_class(s, sides)
                    D['wall'][wc] += 1
                    DK['wall'][wc] += 1
                    pos = cx if s in ('N', 'S') else cy
                    if sides[s]['door_along'] and min(abs(pos - a) for a in sides[s]['door_along']) < T:
                        D['beside_door'] += 1
    out = {'cells': seen, 'fams': {}, 'kinds': {}}
    for fam, D in F.items():
        n = float(D['n'] or 1)
        ds = sorted(D['d_wall'])
        pct = lambda q: ds[min(len(ds) - 1, int(q * len(ds)))] if ds else None
        aw = float(D['at_wall_n'] or 1)
        out['fams'][fam] = {'n': D['n'], 'd_wall': [pct(0.25), pct(0.5), pct(0.75)],
                            'at': {k: round(v / n, 3) for k, v in D['at'].items()},
                            'corner': round(D['corner'] / n, 3),
                            'at_column': round(D['at_col'] / float(D['col_rooms'] or 1), 3), 'col_seen': D['col_rooms'],
                            'wall': {k: round(v / aw, 3) for k, v in D['wall'].items()},
                            'beside_door': round(D['beside_door'] / aw, 3)}
    for kf, DK in FK.items():
        n = float(DK['n'] or 1)
        aw = float(sum(DK['wall'].values()) or 1)
        out['kinds'][kf] = {'n': DK['n'], 'at': {k: round(v / n, 3) for k, v in DK['at'].items()}, 'corner': round(DK['corner'] / n, 3),
                            'wall': {k: round(v / aw, 3) for k, v in DK['wall'].items()}}
    return out


MIN_N = 20


def prefs(db, fam, purpose=None):
    """How the game places a kind of furniture: {'at': {'wall', 'near', 'middle'}, 'corner': share,
    'at_column': share of those in rooms with a free column that stand at one, 'wall': {wall class:
    share of those at a wall}, 'beside_door': share, 'd_wall': [25th, median, 75th distance]}; the
    room kind's own figures when it has enough (20), else every room's; None until surveyed."""
    s = ready(db)
    if not s or fam not in s['fams'] or s['fams'][fam]['n'] < MIN_N:
        return None
    out = dict(s['fams'][fam])
    if purpose:
        K = s['kinds'].get(purpose + '|' + fam)
        if K and K['n'] >= MIN_N:
            out['at'] = K['at']
            out['corner'] = K['corner']
            if sum(K['wall'].values()) >= 0.99:
                out['wall'] = K['wall']
    return out


def report(db):
    """For people: per family, where the game stands it."""
    s = survey(db)
    lines = ['%d places walked' % s['cells']]
    for fam, D in sorted(s['fams'].items(), key=lambda kv: -kv[1]['n']):
        lines.append('%-10s n %5d: at wall %3.0f%% near %3.0f%% middle %3.0f%%; wall distance 25/50/75 %s; in a corner %3.0f%%; at a column %3.0f%% (of %d in rooms with one); '
                     'walls: %s; beside a doorway %3.0f%%' % (
                         fam, D['n'], 100 * D['at'].get('wall', 0), 100 * D['at'].get('near', 0), 100 * D['at'].get('middle', 0), D['d_wall'],
                         100 * D['corner'], 100 * D['at_column'], D['col_seen'],
                         ', '.join('%s %.0f%%' % (k, 100 * v) for k, v in sorted(D['wall'].items(), key=lambda kv: -kv[1])), 100 * D['beside_door']))
    return '\n'.join(lines)
