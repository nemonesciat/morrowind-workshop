"""The joint survey: what the game's own, hand-made interiors stand at each kind of joint between their
floor pieces, kit by kit, so the Workshop can say at any edge of a built house "the game stands this
here" and lay it.

A joint is one side of one floor tile. Its situation is read the same way everywhere: what is beyond
the edge (another tile of the house, and whether that tile's side towards us is a wall, a doorway or
open; a stair that runs through the edge or along it; the void over a lower floor; nothing), whether a
tile stands under this one and over it (the storey), what the tile's own two flanking sides are, and
whether a tile stands beside it at either end of the edge (an outer corner of the house, an inner one,
or the middle of a run). The answer the game gives there is the tile's own side (a wall, a doorway or
open) together with every loose piece of the kit's family standing on the edge: a wall addon on its
face, a pillar at its end, a door jamb in it, a loose wall across it, each with its offset along and
out from the edge, its height over the floor and its turn. A side piece with its addon and the pillar at
its end is one answer; a loose wall across an open tile is another; the survey counts how often each
answer is given in each situation, with the fine situation (every detail above) and a coarser one (what
is beyond, and the storey) so a rare situation can still go by the general rule.

Learnt once for every kit with the other surveys (learning.py), in the survey process, and kept in the
cache folder under the load order's signature. Measured 2026-10-22: 77 kits in about a minute."""
import json
import math
import os
import re
from collections import Counter

import kits
import mapdata
from mapdata import ref_info

VERSION = 1
SIDES = kits.SIDES
STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
RIGHT = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}      # facing out through a side, the side to the right
LEFT = {v: k for k, v in RIGHT.items()}
Q = {'N': 0, 'E': 1, 'S': 2, 'W': 3}                   # quarter turns clockwise from north
PLACES = 40                                            # the game's places looked at per kit
MIN_N = 6                                              # a fine situation seen fewer times goes by the coarse one
STRONG = 0.6                                           # an answer the game gives this often is "what it stands here"
RARE = 0.12                                            # an answer it gives less often than this is "not what it stands"
LOOSE = re.compile(r'pillar|post|column|wall|addon|jamb|frame|beam|arch|ledge|partition|panel')
NOT_LOOSE = re.compile(r'skirt|window|trim|rail|floor|ceil|sheet|stair|ramp|furn|light|rug|_door_|loaddoor')
POSTY = re.compile(r'post|pillar|column')

_cache = {}
_bounds = {}


def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'joints_%s_v%d.json' % (taste.sig(db), VERSION))


def family(prefix):
    parts = prefix.lower().split('_')
    return '_'.join(parts[:-1]) if len(parts) >= 3 else prefix.lower()


def _box(db, rid):
    low = rid.lower()
    if low not in _bounds:
        ri = db.resolve_id(rid)
        _bounds[low] = (ri, mapdata.object_bounds(db, ri) if ri is not None else None)
    return _bounds[low]


def world_centre(pos, b):
    """The middle of a model's box in the world, for a reference at pos (turned about Z, clockwise)."""
    cx, cy = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
    c, s = math.cos(pos[5]), math.sin(pos[5])
    return pos[0] + cx * c + cy * s, pos[1] - cx * s + cy * c, pos[2] + (b[2] + b[5]) / 2.0


# ------------------------------------------------------------------ reading a place
def read_place(db, cell_key, m=None):
    """A place as the survey sees it: {'tiles': [{ref, id, x, y, z, floor, q, pat, spot, T, H, kit, mates}],
    'stairs': [{id, pos, box, up}], 'loose': [{ref, id, pos, box, cx, cy, cz, ri}]}. From a cellmap (the
    finder's) or straight from the place's references (the survey's)."""
    tiles, stairs, loose = [], [], []
    if m is None:
        refs, _h = db.cell_refs(cell_key)
        items = []
        for rk, ref in refs.items():
            rid, pos, scale, dead = ref_info(ref['subs'])
            if not dead and pos:
                items.append((rk, rid, pos, scale or 1.0))
    else:
        items = [(r['k'], r['id'], r['p'], r['s'] or 1.0) for r in m['refs'] if not (r['type'] not in ('STAT', 'ACTI'))]
    for rk, rid, pos, scale in items:
        low = rid.lower()
        pre = kits.kit_prefix(rid)
        kp = kits.kit_pieces(db, pre) if pre and pre in kits.kits(db) else None
        piece = None
        if kp:
            piece = next((p for p in kp['pieces'] if p['id'].lower() == low), None)
            tall = None if piece else next((p for p in kp.get('tall') or [] if p['id'].lower() == low), None)
            piece = piece or tall
        else:
            tall = None
        q = int(round(pos[5] / (math.pi / 2))) % 4
        square = abs((pos[5] - q * math.pi / 2) % (2 * math.pi)) < 0.1 or abs((pos[5] - q * math.pi / 2) % (2 * math.pi) - 2 * math.pi) < 0.1
        if piece and abs(scale - 1) < 0.02 and square and abs(pos[3]) < 0.05 and abs(pos[4]) < 0.05:
            tiles.append({'ref': rk, 'id': rid, 'x': pos[0], 'y': pos[1], 'z': pos[2], 'floor': pos[2] + piece['zmin'], 'q': q,
                          'pat': kits.rotate(piece['lower'] if tall else piece['pattern'], q), 'T': kp['tile'], 'H': kp['height'],
                          'kit': pre, 'kp': kp, 'piece': piece, 'tall': bool(tall)})
            continue
        ri, b = _box(db, rid)
        if ri is None or not b or db.recs[ri][0] not in ('STAT', 'ACTI'):
            continue
        if 'stair' in low or 'ramp' in low:
            if max(b[3] - b[0], b[4] - b[1]) < 96:
                continue
            c, s = math.cos(pos[5]), math.sin(pos[5])
            xs, ys = [], []
            for lx in (b[0], b[3]):
                for ly in (b[1], b[4]):
                    xs.append(pos[0] + lx * c + ly * s)
                    ys.append(pos[1] - lx * s + ly * c)
            stairs.append({'id': low, 'pos': pos, 'q': q, 'ri': ri,
                           'box': (min(xs), min(ys), pos[2] + b[2], max(xs), max(ys), pos[2] + b[5]), 'up': None})
            continue
        if LOOSE.search(low) and not NOT_LOOSE.search(low) and abs(scale - 1) < 0.05:
            cx, cy, cz = world_centre(pos, b)
            loose.append({'ref': rk, 'id': low, 'pos': pos, 'box': b, 'cx': cx, 'cy': cy, 'cz': cz, 'ri': ri,
                          'z0': pos[2] + b[2], 'z1': pos[2] + b[5]})
    # stacked pieces on one spot: the spot has every wall any of them has
    for t in tiles:
        mates = [o for o in tiles if o is not t and abs(o['x'] - t['x']) < 8 and abs(o['y'] - t['y']) < 8 and abs(o['floor'] - t['floor']) < 32]
        if mates:
            spot = dict(t['pat'])
            for s in SIDES:
                got = [t['pat'][s]] + [o['pat'][s] for o in mates]
                spot[s] = 'wall' if 'wall' in got else 'door' if 'door' in got else 'open'
            t['spot'] = spot
            t['mates'] = [o['ref'] for o in mates]
        else:
            t['spot'] = t['pat']
            t['mates'] = []
    # which way each stair climbs, from the kits' learnt stairs (whichever kit learnt the piece: a Common
    # stone house climbs with the plain set's stair)
    lows = _stair_map(db)
    for st in stairs:
        low_side = lows.get(st['id'])
        if low_side:
            st['up'] = SIDES[(SIDES.index(OPP[low_side]) + st['q']) % 4]
        else:
            w, d = st['box'][3] - st['box'][0], st['box'][4] - st['box'][1]
            st['up'] = ('N' if d > w * 1.3 else 'E' if w > d * 1.3 else None)        # (along its long axis, either way)
    return {'tiles': tiles, 'stairs': stairs, 'loose': loose}


_stairs = {}


def _stair_map(db):
    """{stair id: the side its low end opens to, in its own frame} over every kit whose stairs are learnt
    (kits._stairs_disk: on disk, so nothing is learnt here)."""
    disk = kits._stairs_disk(db)
    if _stairs.get('recs') is db.recs and _stairs.get('n') == len(disk):
        return _stairs['map']
    out = {}
    for pre, res in disk.items():
        for p in (res or {}).get('pieces', []):
            out.setdefault(p['id'].lower(), p['low'])
    for pre, (recs, res) in list(kits._stairs.items()):
        if recs is db.recs:
            for p in (res or {}).get('pieces', []):
                out.setdefault(p['id'].lower(), p['low'])
    _stairs.update(recs=db.recs, n=len(disk), map=out)
    return out


def class_of(low):
    """What kind of loose piece this is: post, jamb, addon, wall, arch, beam, ledge or other."""
    if POSTY.search(low):
        return 'post'
    if 'jamb' in low or 'frame' in low:
        return 'jamb'
    if 'addon' in low or 'panel' in low:
        return 'addon'
    if 'wall' in low or 'partition' in low:
        return 'wall'
    for w in ('arch', 'beam', 'ledge'):
        if w in low:
            return w
    return 'other'


def tile_at(tiles, x, y, z, dz=64):
    for o in tiles:
        if abs(o['x'] - x) < 24 and abs(o['y'] - y) < 24 and abs(o['floor'] - z) < dz:
            return o
    return None


# ------------------------------------------------------------------ the situation at an edge
def situation(place, t, s):
    """The situation at side s of tile t: {'fine': tuple, 'coarse': tuple, 'beyond', 'words'}."""
    T, H = t['T'], t['H']
    dx, dy = STEP[s]
    nx, ny = t['x'] + dx * T, t['y'] + dy * T
    n = tile_at(place['tiles'], nx, ny, t['floor'])
    nbside = '-'
    if n:
        beyond = 'tile'
        nbside = n['spot'][OPP[s]]
    else:
        beyond = 'none'
        for st in place['stairs']:
            b = st['box']
            if b[0] - 8 <= nx <= b[3] + 8 and b[1] - 8 <= ny <= b[4] + 8 and b[2] <= t['floor'] + H * 0.9 and b[5] >= t['floor'] - H * 0.9:
                up = st['up']
                beyond = 'stair' if not up else 'stair_end' if up in (s, OPP[s]) else 'stair_side'
                break
        if beyond == 'none' and tile_at(place['tiles'], nx, ny, t['floor'] - H, dz=96):
            beyond = 'well'
    under = bool(tile_at(place['tiles'], t['x'], t['y'], t['floor'] - H, dz=96))
    over = bool(tile_at(place['tiles'], t['x'], t['y'], t['floor'] + H, dz=96))
    flank = (t['spot'][LEFT[s]], t['spot'][RIGHT[s]])
    ends = []
    for e in (LEFT[s], RIGHT[s]):
        ex, ey = STEP[e]
        ends.append('tile' if tile_at(place['tiles'], t['x'] + ex * T, t['y'] + ey * T, t['floor']) else 'none')
    fine = (beyond, nbside, under, over, flank[0], flank[1], ends[0], ends[1])
    return {'fine': fine, 'coarse': fine[:4], 'beyond': beyond}


def describe(key):
    """A situation in words."""
    beyond, nbside, under, over = key[:4]
    under, over = under in (True, 'True'), over in (True, 'True')
    what = {'tile': 'another tile beyond it' + {'wall': ', walled towards it', 'door': ', with a doorway towards it', 'open': ', open towards it'}.get(nbside, ''),
            'stair_end': 'a stair running through it', 'stair_side': 'a stair running along it', 'stair': 'a stair beyond it',
            'well': 'the opening over a lower floor beyond it', 'none': 'nothing beyond it'}[beyond]
    storey = 'an upper storey' if under else 'the ground storey'
    top = '' if over else ', top floor'
    s = '%s, %s%s' % (what, storey, top)
    if len(key) > 4:
        fl, fr, el, er = key[4:]
        s += '; flanks %s/%s, %s at the left end, %s at the right' % (fl, fr, 'a tile' if el == 'tile' else 'nothing', 'a tile' if er == 'tile' else 'nothing')
    return s


# ------------------------------------------------------------------ the answer at an edge
def edge_frame(t, s):
    """(ex, ey: the edge's midpoint; ax, ay: along it to the right; dx, dy: out)."""
    T = t['T']
    dx, dy = STEP[s]
    ax, ay = STEP[RIGHT[s]]
    return t['x'] + dx * T / 2.0, t['y'] + dy * T / 2.0, ax, ay, dx, dy


def loose_on(place, t, s, fam):
    """The family's loose pieces standing on this edge: [(piece, u, d, dz, dq, label)]."""
    T, H = t['T'], t['H']
    ex, ey, ax, ay, dx, dy = edge_frame(t, s)
    out = []
    for L in place['loose']:
        if fam and not L['id'].startswith(fam + '_'):
            continue
        u = (L['cx'] - ex) * ax + (L['cy'] - ey) * ay
        d = (L['cx'] - ex) * dx + (L['cy'] - ey) * dy
        if abs(d) > T * 0.3 or abs(u) > T * 0.55:
            continue
        if L['z1'] < t['floor'] + 16 or L['z0'] > t['floor'] + H - 16:
            continue
        # (a wall, an addon or a jamb counts only when it runs along this edge: one along the next side
        # has its middle at this edge's end too, and is that side's)
        if not POSTY.search(L['id']):
            b = L['box']
            c, sn = math.cos(L['pos'][5]), math.sin(L['pos'][5])
            w, dp = b[3] - b[0], b[4] - b[1]
            # the model's long axis in the world (turned clockwise), against the edge's direction
            lx, ly = (c, -sn) if w >= dp else (sn, c)
            if abs(lx * ax + ly * ay) < 0.7 and max(w, dp) >= 1.5 * min(w, dp):
                continue
        # (a loose wall along a side the tile walls itself stands hidden behind the tile's own wall: not a
        # joint matter, whatever the game or the builder put there)
        if t['spot'][s] == 'wall' and class_of(L['id']) == 'wall':
            continue
        dq = (int(round(L['pos'][5] / (math.pi / 2))) - Q[s]) % 4
        dz = L['pos'][2] - t['floor']
        label = 'R' if u >= T * 0.4 else 'L' if u <= -T * 0.4 else 'mid'
        out.append((L, u, d, dz, dq, label))
    return out


def thin_wall(db, place, t, s, fam):
    """Whether a loose wall on this edge is a thin one: under half as thick as the kit's plain wall."""
    import builder
    try:
        plain = builder.plain_wall(t['kp'])['thick'] if t['kp'].get('walls') else None
    except Exception:
        plain = None
    if not plain:
        return False
    for L, u, d, dz, dq, label in loose_on(place, t, s, fam):
        if class_of(L['id']) == 'wall':
            b = L['box']
            if min(b[3] - b[0], b[4] - b[1]) < plain * 0.5:
                return True
    return False


def answer_of(place, t, s, fam):
    """What stands at this edge: (identity, details). identity = (side kind, (slot, ...)) where a slot is
    'kind@where' (a post at the left end: 'post@L'; an addon on the face: 'addon@mid'), one of each at
    most; details = {'slots': {slot: [(id, u, d, dz, dq)]}, 'tile': (id, dq)}."""
    side = t['spot'][s]
    slots = {}
    for L, u, d, dz, dq, label in loose_on(place, t, s, fam):
        slots.setdefault('%s@%s' % (class_of(L['id']), label), []).append((L['id'], u, d, dz, dq))
    ident = (side, tuple(sorted(slots)))
    return ident, {'slots': slots, 'tile': (t['id'].lower(), (t['q'] - Q[s]) % 4)}


def key_str(k):
    return '|'.join(str(x) for x in k)


def ans_str(a):
    return a[0] + ';' + ','.join(a[1])


def parse_ans(s):
    side, _, rest = s.partition(';')
    return side, tuple(p for p in rest.split(',') if p)


# ------------------------------------------------------------------ the survey
def _cells_for(db, prefix, limit=PLACES):
    kp = kits.kit_pieces(db, prefix)
    cells = set()
    for p in (kp or {}).get('pieces', [])[:8]:
        cells |= {db.recs[ci][7] for ci in db.used_in.get(p['id'].lower(), ()) if db.recs[ci][0] == 'CELL'
                  and kits.game_made(db, db.recs[ci][7]) and not db.recs[ci][7].startswith('#')}
    cells = sorted(cells)
    if len(cells) > limit:
        cells = cells[::max(1, len(cells) // limit)][:limit]
    return cells


def survey_kit(db, prefix, limit=PLACES):
    """One kit: {'places': n, 'edges': n, 'fine': {key: {'n', 'ans': {ans: {'n', 'tile': 'id@dq', 'items': {slot:
    {'id', 'u', 'd', 'dz', 'dq'}}}}}}, 'coarse': {...}}."""
    fam = family(prefix)
    fine, coarse = {}, {}
    places, edges = 0, 0
    try:
        kits.stairs(db, prefix)           # (which way the kit's stairs climb: learnt now if not yet, a second or two)
    except Exception:
        pass
    for ck in _cells_for(db, prefix, limit):
        try:
            place = read_place(db, ck)
        except Exception:
            continue
        own = [t for t in place['tiles'] if t['kit'] == prefix]
        if len(own) < 4:
            continue
        places += 1
        seen = set()
        for t in own:
            if t['ref'] in seen:
                continue
            seen.update(t['mates'])
            for s in SIDES:
                sit = situation(place, t, s)
                ident, det = answer_of(place, t, s, fam)
                edges += 1
                for table, key in ((fine, sit['fine']), (coarse, sit['coarse'])):
                    rec = table.setdefault(key, {'n': 0, 'ans': {}})
                    rec['n'] += 1
                    a = rec['ans'].setdefault(ident, {'n': 0, 'tiles': Counter(), 'slots': {}})
                    a['n'] += 1
                    a['tiles']['%s@%d' % det['tile']] += 1
                    for slot, lst in det['slots'].items():
                        a['slots'].setdefault(slot, []).extend(lst)

    def pack(table):
        out = {}
        med = lambda v: sorted(v)[len(v) // 2]
        for key, rec in table.items():
            ans = {}
            for ident, a in rec['ans'].items():
                items = {}
                for slot, lst in a['slots'].items():
                    top = Counter(x[0] for x in lst).most_common(1)[0][0]
                    mine = [x for x in lst if x[0] == top]
                    items[slot] = {'id': top, 'u': round(med([x[1] for x in mine]), 1), 'd': round(med([x[2] for x in mine]), 1),
                                   'dz': round(med([x[3] for x in mine]), 1), 'dq': Counter(x[4] for x in mine).most_common(1)[0][0]}
                ans[ans_str(ident)] = {'n': a['n'], 'tile': a['tiles'].most_common(1)[0][0], 'items': items}
            out[key_str(key)] = {'n': rec['n'], 'ans': ans}
        return out
    return {'places': places, 'edges': edges, 'fine': pack(fine), 'coarse': pack(coarse)}


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
            print('joint survey, %s: %s' % (prefix, e))
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
        _started[0] = background.start('what the game stands at each kind of joint', lambda: survey(db), task=('joints', 'survey', []))
    return None


def answers(db, prefix, sit, want_n=MIN_N):
    """The game's answers for a situation: (the key used, {'n', 'ans': {ans_str: {...}}}) or (None, None).
    The fine situation when seen often enough, else the coarse one."""
    sv = ready(db)
    rec = (sv or {}).get(prefix)
    if not rec:
        return None, None
    f = rec['fine'].get(key_str(sit['fine']))
    if f and f['n'] >= want_n:
        return sit['fine'], f
    c = rec['coarse'].get(key_str(sit['coarse']))
    if c and c['n'] >= want_n:
        return sit['coarse'], c
    return None, None


def ranked(rec):
    """[(ans_str, n, share, info)] most given first."""
    n = float(rec['n'] or 1)
    return sorted(((a, v['n'], v['n'] / n, v) for a, v in rec['ans'].items()), key=lambda x: -x[1])


def core(a_str):
    """An answer without its posts and jambs: the side kind and the walls and addons on the edge. The
    posts at an edge's ends are the corners' business (the game stands one at about half its corners,
    the builder at every one), and a door jamb across an open join is the doorways' (kits.edge_doors),
    so answers that differ only in them are one answer here; the one laid carries them all the same."""
    side, slots = parse_ans(a_str)
    # (an addon on an open side dresses the jamb or the post there, not the joint: only on a walled side
    # is it the wall's own)
    return side + ';' + ','.join(s for s in slots if not s.startswith(('post@', 'jamb@')) and (side == 'wall' or not s.startswith('addon@')))


def ranked_cores(rec):
    """The answers grouped without their posts: [(core_str, n, share, (ans_str, info) of the fullest
    answer in the group)] most given first."""
    groups = {}
    for a, n, share, info in ranked(rec):
        g = groups.setdefault(core(a), {'n': 0, 'best': None, 'full': None, 'full_n': 0})
        g['n'] += n
        if g['best'] is None:
            g['best'] = (a, info)
        if g['full'] is None and 'post@' in a:
            g['full'], g['full_n'] = (a, info), n
    # (the answer laid for a group is its most given one, or the most given with its posts when the game
    # stands them there a fifth of the time or more: a bare jamb end then gets its pillar offered)
    for g in groups.values():
        if g['full'] and g['full_n'] >= 0.2 * g['n']:
            g['best'] = g['full']
    total = float(rec['n'] or 1)
    return sorted(((c, g['n'], g['n'] / total, g['best']) for c, g in groups.items()), key=lambda x: -x[1])


def side_shares(rec):
    """{side kind: share} over the answers."""
    out = Counter()
    for a, n, share, info in ranked(rec):
        out[a.partition(';')[0]] += share
    return out


# ------------------------------------------------------------------ laying an answer at an edge
def nice(low, prefix=None):
    """A piece's id without the kit's prefix: 'Side_02', 'WallRichAddon_01'."""
    pre = (prefix or '').lower() + '_'
    if pre != '_' and low.startswith(pre):
        return low[len(pre):]
    parts = low.split('_')
    return '_'.join(parts[-2:]) if len(parts) > 2 else low


WHERE = {'L': ' at the left end', 'R': ' at the right end', 'mid': ''}


def answer_label(db, prefix, a_str, info):
    side, slots = parse_ans(a_str)
    tile_id, _dq = info['tile'].split('@') if info.get('tile') else ('', 0)
    words = []
    if side == 'wall':
        words.append(nice(tile_id, prefix) + ' (walled here)' if tile_id else 'a wall')
    elif side == 'door':
        words.append(nice(tile_id, prefix) + ' (a doorway here)' if tile_id else 'a doorway')
    else:
        words.append('open' if not slots else 'open side')
    for slot in slots:
        it = (info.get('items') or {}).get(slot)
        kind, _, where = slot.partition('@')
        words.append((nice(it['id'], prefix) if it else kind) + WHERE.get(where, ''))
    return ' + '.join(words)


def ops_for(db, place, t, s, a_str, info, prefix=None, only_loose=False):
    """The changes that make this edge the answer: [{op...}] (a swap of the tile for one walled or open
    here, the loose pieces the answer has, the loose pieces it has not taken out), and the ghost of
    what is laid: {'ops', 'ghost': [{id, p, s}]}. None when the tile can't be changed to it."""
    import builder
    import fixit
    prefix = prefix or t['kit']
    fam = family(prefix)
    kp = t['kp']
    side, items = parse_ans(a_str)
    ops, ghost = [], []
    how = None
    T = t['T']
    if t['spot'][s] != side and not only_loose:
        if t.get('tall'):
            return None
        want = {k: t['spot'][k] for k in SIDES}
        want[s] = side
        tile_id, tdq = (info['tile'].split('@') if info.get('tile') else ('', '0'))
        chosen = None
        p = next((x for x in kp['pieces'] if x['id'].lower() == tile_id), None)
        if p:
            q = (int(tdq) + Q[s]) % 4
            pat = kits.rotate(p['pattern'], q)
            if all(pat[k] == want[k] for k in SIDES):
                chosen = (p, q)
        if not chosen:
            v = fixit._variant(kp, want)
            if v:
                chosen = v
        if not chosen:
            p2, q2, missing, _pat = builder._pick(kp, want)
            if p2 and not missing:
                chosen = (p2, q2)
        # (never a piece with an archway where the room carries on in place of an open side: the Indoril
        # chapel's entry pieces swapped in that way opened holes on the lab's house, 2026-10-22; the game's
        # own trick below, a second piece stacked on the spot, is taken instead)
        stack = None
        if not chosen and side == 'wall':
            # (or the game's own trick: a second piece on the spot, turned so its wall covers this side and
            # it stands nothing on the sides that stay open: a Side_02 stacked on the corner piece)
            stack = builder._stack_closer(kp, want, t['pat'])
            if not stack:
                return None
        if not chosen and not stack:
            return None
        if stack:
            p3, q3, _pat3 = stack
            rz = q3 * math.pi / 2
            p = [t['x'], t['y'], t['floor'] - p3['zmin'], 0, 0, rz]
            ops.append({'op': 'place', 'id': p3['id'], 'p': p})
            ghost.append({'id': p3['id'], 'p': p, 's': 1.0})
            how = '%s stacked on the %s' % (nice(p3['id'].lower(), prefix), nice(t['id'].lower(), prefix))
        else:
            if chosen[0]['id'].lower() != t['id'].lower() or chosen[1] != t['q']:
                rz = chosen[1] * math.pi / 2
                ops.append({'op': 'swap', 'ref': t['ref'], 'id': chosen[0]['id'], 'rz': rz})
                ghost.append({'id': chosen[0]['id'], 'p': [t['x'], t['y'], t['z'], 0, 0, rz], 's': 1.0})
                how = '%s in place of the %s' % (nice(chosen[0]['id'].lower(), prefix), nice(t['id'].lower(), prefix))
            for mref in t.get('mates', []):
                ops.append({'op': 'delete', 'ref': mref})
    # the loose pieces there now, against the answer's slots: a slot filled stays (whichever piece of the
    # kind fills it), a piece in no slot of the answer goes, an empty slot gets the game's piece
    have = loose_on(place, t, s, fam)
    filled = set()
    for L, u, d, dz, hdq, label in have:
        slot = '%s@%s' % (class_of(L['id']), label)
        if slot in items:
            filled.add(slot)
        elif class_of(L['id']) in ('wall', 'addon'):
            # (a loose wall or addon the answer hasn't goes; a jamb or a post stays: the doorways' and the
            # corners' business. Taking a Common doorframe out with its entrance piece left a slit, 2026-10-22)
            ops.append({'op': 'delete', 'ref': L['ref']})
    ex, ey, ax, ay, dx, dy = edge_frame(t, s)
    posts = [L for L in place['loose'] if POSTY.search(L['id'])]
    for slot in items:
        if slot in filled:
            continue
        it = (info.get('items') or {}).get(slot)
        if not it:
            continue
        low, where = it['id'], slot.partition('@')[2]
        ri, b = _box(db, low)
        if ri is None or not b:
            continue
        u, d, dz, dq = it['u'], it['d'], it['dz'], it['dq']
        if where == 'L':
            u = min(u, -T * 0.4)
        elif where == 'R':
            u = max(u, T * 0.4)
        cx, cy = ex + ax * u + dx * d, ey + ay * u + dy * d
        rot = ((Q[s] + dq) % 4) * math.pi / 2
        if POSTY.search(low) and any(math.hypot(P['cx'] - cx, P['cy'] - cy) < 40 and abs(P['z0'] - t['floor']) < t['H'] * 0.6 for P in posts):
            continue                                       # (a post stands there already)
        px, py = builder._centred(db, ri, cx, cy, rot)
        p = [round(px, 2), round(py, 2), round(t['floor'] + dz, 2), 0, 0, rot]
        ops.append({'op': 'place', 'id': db.recs[ri][1], 'p': p})
        ghost.append({'id': db.recs[ri][1], 'p': p, 's': 1.0})
    if not ops:
        return None
    return {'ops': ops, 'ghost': ghost, 'how': how}


def options(db, place, t, s, prefix=None, limit=4):
    """What the game stands at this edge, most often first: [{'label', 'n', 'share', 'ans', 'ops', 'ghost',
    'current'}] with the situation ('situation', 'key') and what stands there now ('now')."""
    prefix = prefix or t['kit']
    sit = situation(place, t, s)
    key, rec = answers(db, prefix, sit)
    out = {'situation': describe(sit['fine']), 'key': key_str(key) if key else None, 'fine': key_str(sit['fine']),
           'coarse': key_str(sit['coarse']), 'n': rec['n'] if rec else 0, 'options': []}
    ident, _det = answer_of(place, t, s, family(prefix))
    out['now'] = ans_str(ident)
    out['now_label'] = answer_label(db, prefix, out['now'], {'tile': '%s@%d' % _det['tile']})
    if not rec:
        return out
    for c, n, share, (a, info) in ranked_cores(rec):
        if len(out['options']) >= limit or share < 0.08:
            break
        current = c == core(out['now'])
        o = ops_for(db, place, t, s, a, info, prefix) if not current else None
        out['options'].append({'label': answer_label(db, prefix, a, info) + (' (%s here)' % o['how'] if o and o.get('how') else ''),
                               'n': n, 'share': round(share, 2), 'ans': a, 'core': c,
                               'ops': o['ops'] if o else [], 'ghost': o['ghost'] if o else [], 'current': current,
                               'possible': bool(o) or current})
        if current:
            # (the joint is as the game has it, but its posts or jamb may be missing: a bare jamb end, say.
            # Those alone, as one more entry)
            o2 = ops_for(db, place, t, s, a, info, prefix, only_loose=True)
            if o2 and any(op['op'] == 'place' for op in o2['ops']):
                out['options'].append({'label': 'As it is, with its %s' % ' and '.join(sorted({nice(op['id'].lower(), prefix) for op in o2['ops'] if op['op'] == 'place'})),
                                       'n': n, 'share': round(share, 2), 'ans': a, 'core': c, 'ops': o2['ops'], 'ghost': o2['ghost'],
                                       'current': False, 'possible': True})
    return out


MIN_ISSUE_N = 10                                       # a situation seen fewer times raises no finder line
UNANIMOUS = 0.9                                        # the game's share of one side kind for a side-kind line
NEVER = 0.04                                           # ... and its share of the side kind standing here, at most
RULES = ('side', 'loosewall', 'addon')                 # the finder's three rules (see verdict)


def verdict(rec, now, fine=False, thin=False):     # (thin: kept for callers; no rule goes by it now)
    """Whether what stands at an edge is not what the game stands in its situation: (answer to lay, its
    info, the game's share for it, the rule) or None. Three rules, measured on the game's own Gold Coast
    places so that they seldom fault them (2026-10-22): 'side': the game nearly always gives one side
    kind here (a wall, a doorway or open: UNANIMOUS) and this edge has another it (next to) never gives;
    'loosewall': a loose wall closes an open side where the game mostly walls the tile itself and seldom
    closes it so; 'addon': in a situation seen in every detail (the fine key), a walled side the game
    mostly dresses with its wall addon has none. The fullest answer of the group to lay comes with it."""
    if rec['n'] < MIN_ISSUE_N:
        return None
    cur = core(now)
    cur_side = cur.partition(';')[0]
    cores = ranked_cores(rec)
    cur_share = next((share for c, n, share, _b in cores if c == cur), 0.0)
    sides = side_shares(rec)
    top_side, top_share = max(sides.items(), key=lambda kv: kv[1])

    def lay(side_kind):
        for c, n, share, (a, info) in cores:
            if c.partition(';')[0] == side_kind:
                return a, info, share
        return None
    # (a doorway side is the doorways' business, kits.edge_doors: never faulted here; a Common entrance piece
    # facing an open tile is how the builder makes that set's doorways)
    # (nor a doorway side wanted: the Indoril chapel's tiles face each other with archways where the builder
    # lays open pieces, and swapping arches in for them opened eleven holes on the lab's house, 2026-10-22)
    if 'side' in RULES and cur_side != top_side and 'door' not in (cur_side, top_side) and top_share >= UNANIMOUS and sides.get(cur_side, 0.0) <= NEVER:
        r = lay(top_side)
        if r:
            return r + ('side',)
    # (a loose wall across an open side: the game walls the tile itself here at least half the time and
    # better than twice as often as it closes the side with a loose wall. Reeking Pit 2's stairwell side,
    # upper storey: the game's walled piece with its addon 62%, a loose wall 23%, open 15%)
    # (and only where the game dresses that walled side with its wall addon: a walled piece that looks like
    # a loose wall is no better than one; the Indoril chapel's walled entry piece swapped in for a loose
    # wall beside its stairwell made two slits on the lab's house, 2026-10-22)
    if 'loosewall' in RULES and cur_side == 'open' and 'wall@mid' in cur and top_side == 'wall' and top_share >= 0.5 and cur_share < RARE:
        r = lay('wall')
        if r and 'addon@' in core(r[0]):
            return r + ('loosewall',)
    if 'addon' in RULES and fine and cur_side == 'wall' and top_side == 'wall' and 'addon@' not in cur:
        top = cores[0]
        if 'addon@' in top[0] and top[2] >= STRONG and cur_share < RARE:
            return top[3] + (top[2], 'addon')
    return None


# ------------------------------------------------------------------ the finder's kind
def issues(db, m, tiles=None, prefix=None):
    """Edges where what stands is not what the game stands in that situation: [{kind 'joint', ...}]. Only
    where the game's answer is strong (STRONG of MIN_N+ cases) and what stands here is rare (under RARE),
    and the answer can be laid."""
    out = []
    place = read_place(db, None, m)
    if not place['tiles']:
        return out
    votes = Counter(t['kit'] for t in place['tiles'])
    prefix = prefix or votes.most_common(1)[0][0]
    if not ready(db):
        return out
    # (a sheet kit's tiles are floor sheets with every wall a loose piece, the Imperial chapel: its joints are
    # loose walls by design)
    kp0 = kits.kit_pieces(db, prefix)
    if not kp0 or kp0.get('sheet_kit'):
        return out
    fam = family(prefix)
    seen = set()
    joints_done = set()
    for t in place['tiles']:
        if t['ref'] in seen or t['kit'] != prefix:
            continue
        seen.update(t['mates'])
        for s in SIDES:
            sit = situation(place, t, s)
            key, rec = answers(db, prefix, sit, want_n=MIN_ISSUE_N)
            if not rec:
                continue
            ident, _d = answer_of(place, t, s, fam)
            now = ans_str(ident)
            v = verdict(rec, now, fine=(len(key) > 4), thin=thin_wall(db, place, t, s, fam))
            if not v:
                continue
            a, info, share, rule = v
            o = ops_for(db, place, t, s, a, info, prefix, only_loose=(rule == 'addon'))
            if not o:
                continue
            ex, ey, ax, ay, dx, dy = edge_frame(t, s)
            # (one line per joint: the edge between two tiles is seen from both, and one fix serves both)
            jk = (round(ex / 8), round(ey / 8), round(t['floor'] / 32))
            if jk in joints_done:
                continue
            joints_done.add(jk)
            label = answer_label(db, prefix, a, info)
            out.append({'kind': 'joint', 'ref': t['ref'], 'id': t['id'], 'side': s, 'x': ex, 'y': ey, 'z': t['floor'] + 110,
                        'text': 'Not what the game stands here: with %s, it stands %s (%d%% of %d); here %s' % (
                            describe(key), label, round(100 * share), rec['n'], answer_label(db, prefix, now, {'tile': '%s@%d' % _d['tile']})),
                        'fixes': [{'label': 'Make it %s' % label, 'ops': o['ops']}], 'joint': {'key': key_str(key), 'ans': a, 'rule': rule}})
    return out


def fix_for(db, m, tiles, t, s):
    """The game's answer at this edge as one fix for the finder's gap and hole lists (None when there is
    none strong enough, or it is what stands there already)."""
    try:
        place = read_place(db, None, m)
    except Exception:
        return None
    tt = next((x for x in place['tiles'] if x['ref'] == t['ref']), None)
    if not tt or not ready(db):
        return None
    prefix = tt['kit']
    sit = situation(place, tt, s)
    key, rec = answers(db, prefix, sit)
    if not rec:
        return None
    ident, _d = answer_of(place, tt, s, family(prefix))
    v = verdict(rec, ans_str(ident), fine=(len(key) > 4), thin=thin_wall(db, place, tt, s, family(prefix)))
    if not v:
        return None
    a, info, share, rule = v
    o = ops_for(db, place, tt, s, a, info, prefix, only_loose=(rule == 'addon'))
    if not o:
        return None
    swap = next((op for op in o['ops'] if op['op'] == 'swap'), None)
    c = {'label': 'Make it %s (the game\'s way here, %d%% of %d)' % (answer_label(db, prefix, a, info), round(100 * share), rec['n']),
         'ops': o['ops']}
    if swap:
        c['swap'] = (swap['ref'], swap['id'], [tt['x'], tt['y'], tt['z'], 0, 0, swap['rz']], 1.0)
    return c


def summary(db, prefixes=None):
    """For people: per kit, the situations seen most and the game's top answer at each."""
    sv = ready(db) or {}
    out = {}
    for pre in (prefixes or sorted(sv)):
        rec = sv.get(pre)
        if not rec:
            continue
        rows = []
        for key, r in sorted(rec['coarse'].items(), key=lambda kv: -kv[1]['n'])[:12]:
            top = ranked(r)[0]
            rows.append([describe(tuple(key.split('|'))), r['n'], answer_label(db, pre, top[0], top[3]), round(top[2], 2)])
        out[pre] = {'places': rec['places'], 'edges': rec['edges'], 'rows': rows}
    return out
