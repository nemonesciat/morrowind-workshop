"""The game's own stairwells, whole: wherever its hand-made interiors climb two storeys or more by a kit's stair pieces,
one flight a storey over another and a few tiles from it, the whole shaft is kept as an example, every storey of it: each
flight (its piece, where it stands and how it is turned; z in storeys from the bottom flight) and the building pieces round the shaft (z from the bottom flight's floor) (walls, rails, posts,
landings, the floor and ceiling pieces left and the ones left out), all in the bottom flight's frame.

"Build from pieces" stacks its flights by rules (over the one below, beside it, on from its head), and each new kit
showed a new way for the rules to go wrong: walls across the stairs, flights inside each other, see-through sides (the
user's Chillmorrow, 2026-10-31: "Is it not possible to look at examples of proper one stairwell staircases and use their
example?"). An example is a stairwell that stands in the game: laid whole, nothing about it can be wrong in that way.

Kept in the cache folder by load order (taste.cache_file); ready() learns it in the background the first time."""
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict

import kits
from mapdata import ref_info

VERSION = 2                 # (2: the railings round each stair piece, 'rails')
RAIL_SHARE = 0.25           # a railing kept when the game stands it there round that piece this often
REACH = 3.2                 # tiles: the furthest a flight stands from the one below in one stairwell
AROUND = 2                  # tiles round the flights' own kept as the shaft's surroundings
RAIL = re.compile(r'rail|banister|balust', re.I)
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('stairwellsurvey_%s_v%d' % (taste.sig(db), VERSION))


def _kit_ids(db):
    """Every kit's own building pieces (lower ids): the shaft's surroundings are these, never what stands in it."""
    import builder
    out = set()
    for s in builder.styles(db, wait=True):
        kp = kits.kit_pieces(db, kits.split_style(s['id'])[0])
        for p in (kp or {}).get('pieces') or ():
            out.add(p['id'].lower())
    return out


def _built(db, rid, memo):
    """A building static that isn't a kit's own: the railing at a Common stairwell's head, a post, a jamb."""
    low = rid.lower()
    if low not in memo:
        import mapdata
        ri = db.resolve_id(rid)
        memo[low] = bool(ri is not None and db.recs[ri][0] == 'STAT' and
                         mapdata.is_architecture('STAT', rid, mapdata.object_bounds(db, ri)))
    return memo[low]


def _stair_pieces(db):
    """{stair id (lower): {'id', 'styles': [style], 'storey', 'rise', 'z_low', 'low', 'tile', 'height'}} for every kit."""
    import builder
    out = {}
    for s in builder.styles(db, wait=True):
        style = kits.split_style(s['id'])[0]
        info = kits.stairs(db, style)
        kp = kits.kit_pieces(db, style)
        if not info or not kp:
            continue
        for p in info['pieces']:
            o = out.setdefault(p['id'].lower(), {'id': p['id'], 'styles': [], 'storey': info['storey'], 'rise': p['rise'],
                                                 'z_low': p['z_low'], 'low': p['low'], 'tile': kp['tile'],
                                                 'height': p.get('height', 0), 'len': p.get('len', 1)})
            if style not in o['styles']:
                o['styles'].append(style)
    return out


def _q(a):
    return int(round(a / (math.pi / 2))) % 4


def survey(db):
    """{'stairwells': [{'cell', 'style', 'storey', 'tile', 'flights': [{id, x, y, z, q}], 'around': [{id, x, y, z, q}]}],
    'styles': {style: {'stairwells', 'flights': Counter as dict, 'steps': {'dx,dy,dq': n}}}}. Positions in the bottom
    flight's frame: x across (tiles), y along its climb (tiles), z in storeys; q quarter turns from it."""
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = _disk(db)
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
        except Exception:
            pass
    SP = _stair_pieces(db)
    KIT = _kit_ids(db)
    archc = {}
    cells = set()
    for low in SP:
        for ci in db.used_in.get(low, ()):
            if db.recs[ci][0] == 'CELL':
                cells.add(db.recs[ci][7])
    wells = []
    for ck in sorted(cells):
        if ck.startswith('#') or not kits.game_made(db, ck):
            continue
        refs, _h = db.cell_refs(ck)
        items = []
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead or not pos:
                continue
            items.append((rid, rid.lower(), pos))
        fl = [it for it in items if it[1] in SP]
        if len(fl) < 2:
            continue
        # flights a storey apart and near each other, joined into stairwells
        edges = defaultdict(set)
        for i, a in enumerate(fl):
            A = SP[a[1]]
            for j, b in enumerate(fl):
                if i == j:
                    continue
                dz = b[2][2] - a[2][2]
                if abs(dz - A['storey']) > 0.25 * A['storey']:
                    continue
                if math.hypot(b[2][0] - a[2][0], b[2][1] - a[2][1]) > REACH * A['tile']:
                    continue
                edges[i].add(j)
                edges[j].add(i)
        seen = set()
        for i in sorted(edges, key=lambda i: fl[i][2][2]):
            if i in seen:
                continue
            comp, todo = [], [i]
            while todo:
                k = todo.pop()
                if k in seen:
                    continue
                seen.add(k)
                comp.append(k)
                todo += list(edges[k])
            if len(comp) < 2:
                continue
            comp.sort(key=lambda k: (fl[k][2][2], fl[k][2][0], fl[k][2][1]))
            base = fl[comp[0]]
            B = SP[base[1]]
            T, H = B['tile'], B['storey']
            bx, by, bz, yaw = base[2][0], base[2][1], base[2][2], base[2][5]
            c, s = math.cos(yaw), math.sin(yaw)
            q0 = _q(yaw)

            def local(p):
                dx, dy = p[0] - bx, p[1] - by
                # (the frame turns with the piece: its +y is the way the bottom flight faces in the game's own frame)
                return round((dx * c - dy * s) / T, 2), round((dx * s + dy * c) / T, 2), round((p[2] - bz) / H, 2)
            flights = []
            for k in comp:
                rid, low, p = fl[k]
                x, y, z = local(p)
                flights.append({'id': rid, 'x': x, 'y': y, 'z': z, 'q': (_q(p[5]) - q0) % 4})
            xs = [f_['x'] for f_ in flights]
            ys = [f_['y'] for f_ in flights]
            top = max(f_['z'] for f_ in flights)
            # the building pieces round the shaft (any kit's: a Common plain stairwell climbs into a rich storey)
            around = []
            for rid, low, p in items:
                if low in SP and any(fl[k][2] is p for k in comp):
                    continue
                if low not in KIT and not _built(db, rid, archc):
                    continue
                x, y, z = local(p)
                # (by the bottom flight's floor, not its origin: Hlaalu's stairs stand half a storey over their floor, and
                # its storeys came out at -0.5, 0.5, 1.5)
                z = round(z - B['z_low'] / H, 2)
                if not (min(xs) - AROUND <= x <= max(xs) + AROUND and min(ys) - AROUND <= y <= max(ys) + AROUND
                        and -0.6 <= z <= top + 1.6):
                    continue
                around.append({'id': rid, 'x': x, 'y': y, 'z': z, 'q': (_q(p[5]) - q0) % 4})
            style = Counter(st for st in B['styles'] for a in around if kits.kit_prefix(a['id']) == kits.kit_prefix(st)).most_common(1)
            wells.append({'cell': ck, 'style': style[0][0] if style else B['styles'][0], 'storey': H, 'tile': T,
                          'flights': flights, 'around': around})
    rails = _rails(db, SP, cells)
    styles = {}
    for w in wells:
        S_ = styles.setdefault(w['style'], {'stairwells': 0, 'flights': Counter(), 'steps': Counter(), 'cells': []})
        S_['stairwells'] += 1
        S_['flights'][len(w['flights'])] += 1
        if len(S_['cells']) < 6 and w['cell'] not in S_['cells']:
            S_['cells'].append(w['cell'])
        for a, b in zip(w['flights'], w['flights'][1:]):
            S_['steps']['%+.0f,%+.0f,q%d' % (b['x'] - a['x'], b['y'] - a['y'], (b['q'] - a['q']) % 4)] += 1
    for S_ in styles.values():
        S_['flights'] = {str(k): v for k, v in S_['flights'].items()}
        S_['steps'] = dict(S_['steps'].most_common())
    out = {'stairwells': wells, 'styles': styles, 'rails': rails}
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception as e:
        print('stairwell survey not kept:', e)
    _cache[key] = (db.recs, out)
    return out


def _rails(db, SP, cells):
    """{stair id (lower): [{'id', 'x', 'y', 'z', 'q', 'share'}]}: the railings the game stands round each one-tile stair
    piece (within a tile and a half, from its floor to the storey over it), in its own frame (x, y in tiles from its
    origin, z in storeys from its floor, q quarter turns from it), the ones it stands there a quarter of the time or more
    (lab jrail0: Hlaalu's room_stairsl has its room_rail along the upper edge 64% of the time, Common's tall_01 its
    in_c_railing_01 at the head 37%)."""
    from collections import Counter as C_
    seen, uses = defaultdict(C_), C_()
    for ck in sorted(cells):
        if ck.startswith('#') or not kits.game_made(db, ck):
            continue
        refs, _h = db.cell_refs(ck)
        items = []
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if not dead and pos:
                items.append((rid, pos))
        for rid, p in items:
            sp = SP.get(rid.lower())
            if not sp or sp['len'] != 1:
                continue
            uses[rid.lower()] += 1
            c, s = math.cos(p[5]), math.sin(p[5])
            T, H = sp['tile'], sp['storey']
            here = set()
            for oid, o in items:
                if not RAIL.search(oid) or oid.lower() in SP:
                    continue
                dx, dy = o[0] - p[0], o[1] - p[1]
                lx, ly = (dx * c - dy * s) / T, (dx * s + dy * c) / T
                lz = (o[2] - p[2] - sp['z_low']) / H
                if abs(lx) > 1.6 or abs(ly) > 1.6 or not (-0.3 < lz < 1.4):
                    continue
                k = (oid, round(lx * 2) / 2, round(ly * 2) / 2, round(lz * 4) / 4, _q(o[5] - p[5]))
                if k not in here:
                    here.add(k)
                    seen[rid.lower()][k] += 1
    out = {}
    for low, c in seen.items():
        n = uses[low]
        keep = [{'id': k[0], 'x': k[1], 'y': k[2], 'z': k[3], 'q': k[4], 'share': round(v / float(n), 2)}
                for k, v in c.most_common() if n >= 4 and v / float(n) >= RAIL_SHARE]
        if keep:
            out[low] = keep
    return out


def rails_of(db, stair_id):
    """The railings the game stands round this stair piece (see _rails), or []."""
    S = ready(db)
    return ((S or {}).get('rails') or {}).get(stair_id.lower(), [])


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    if os.path.isfile(_disk(db)):
        try:
            return survey(db)
        except Exception:
            return None
    t = _thread.get('t')
    if t is None or not t.is_alive():
        try:
            import background
            _thread['t'] = background.start("the game's stairwells", lambda: survey(db), task=('stairwellsurvey', 'survey', []))
        except Exception:
            t = threading.Thread(target=lambda: survey(db), daemon=True)
            _thread['t'] = t
            t.start()
    return None


# ---------------------------------------------------------------- the steps from one flight to the next

def _up(low, q):
    """The side a flight climbs to, in the stairwell's frame: its piece's low end opens to `low`, turned q quarters (the
    builder's own turn: a piece's side i stands at side i + q, clockwise)."""
    opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[low]
    return kits.SIDES[(kits.SIDES.index(opp) + q) % 4]


STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}


def _right(up):
    return kits.SIDES[(kits.SIDES.index(up) + 1) % 4]


def step_of(a, b, SP):
    """From flight a to the next one up, b, in a's climb: (along, across to the right, quarter turns of the climb)."""
    ua, ub = _up(SP[a['id'].lower()]['low'], a['q']), _up(SP[b['id'].lower()]['low'], b['q'])
    dx, dy = b['x'] - a['x'], b['y'] - a['y']
    along = dx * STEP[ua][0] + dy * STEP[ua][1]
    across = dx * STEP[_right(ua)][0] + dy * STEP[_right(ua)][1]
    return int(round(along)), int(round(across)), (kits.SIDES.index(ub) - kits.SIDES.index(ua)) % 4


def apply_step(x, y, up, st):
    """Where the next flight stands and climbs, from a flight at (x, y) climbing `up`, by a learnt step."""
    along, across, dq = st
    r = _right(up)
    return (x + along * STEP[up][0] + across * STEP[r][0], y + along * STEP[up][1] + across * STEP[r][1],
            kits.SIDES[(kits.SIDES.index(up) + dq) % 4])


def steps(db, style):
    """The game's steps from a flight to the next in this style's stairwells, commonest first: [{'step': (along, across,
    dq), 'n', 'pieces': {stair id: n}, 'cells': [...]}]. One-tile flights only (a longer piece's origin isn't its foot)."""
    S = ready(db)
    if not S:
        return []
    SP = _stair_pieces(db)
    c, pieces, cells = Counter(), defaultdict(Counter), defaultdict(list)
    for w in S['stairwells']:
        if w['style'] != style:
            continue
        fl = w['flights']
        if any(SP.get(f['id'].lower(), {}).get('len', 1) != 1 or f['id'].lower() not in SP for f in fl):
            continue
        for a, b in zip(fl, fl[1:]):
            if abs(b['z'] - a['z'] - 1) > 0.2:
                continue
            st = step_of(a, b, SP)
            c[st] += 1
            pieces[st][a['id']] += 1
            if len(cells[st]) < 4 and w['cell'] not in cells[st]:
                cells[st].append(w['cell'])
    return [{'step': list(st), 'n': n, 'pieces': dict(pieces[st]), 'cells': cells[st]} for st, n in c.most_common()]


def selftest(db):
    """Every learnt stairwell rebuilt from its steps lands where the game has its flights: the share that does."""
    S = ready(db)
    SP = _stair_pieces(db)
    ok = n = 0
    for w in S['stairwells']:
        fl = w['flights']
        for a, b in zip(fl, fl[1:]):
            if a['id'].lower() not in SP or b['id'].lower() not in SP:
                continue
            n += 1
            ua = _up(SP[a['id'].lower()]['low'], a['q'])
            x, y, up = apply_step(a['x'], a['y'], ua, step_of(a, b, SP))
            ok += abs(x - b['x']) < 0.3 and abs(y - b['y']) < 0.3 and up == _up(SP[b['id'].lower()]['low'], b['q'])
    return ok, n
