"""The game's own keeps and castles, read whole, for the castle maker (castle.py).

Each fort is found by its interiors' names (a Legion fort's "Interior", "Towers", "Prison"; a stronghold's "Upper Level",
"Lower Level", "Propylon Chamber"; a house stronghold's manor and its houses), its outside by where their doors lead out.
For each one it keeps:

  its figures: the walled ground (the wall pieces' box), how many lengths, towers, gates and keeps, its interiors, what
    each holds (beds, weapon racks, shrines, prison doors...), how they join, how many doors lead out, its people
  its modules: the pieces outside that hold the doors into each group of joined interiors (a Legion keep and the stair
    towers beside it; a stronghold's whole keep; a manor), in the frame of its main piece, with the doors where they
    stand and the interior each leads into, so a castle can stand the keep as the game stood it and copy what lies
    behind it, every door paired as the game paired it
  its tower rooms: the rooms of its "Towers" or "Curtain Wall" interior (spiral stairs, the doors at each storey, the
    trap door to the roof), one per tower, each a cluster of touching pieces
  its door slots: where on each wall or tower piece the game stands a door, and into what kind of room

Measured 2026-11-01 (lab c2-c6): a Legion fort is a keep's halls ("Interior", beds, books, a shrine, a prison door), its
towers as one interior (every tower's spiral stair in one place, a door at the wall walk each side and a trap door to
the roof), and a prison; the strongholds Hlormaren, Marandus and Falasmaryon stand one keep, piece for piece the same
(fort00-03, four entrances: upper and lower levels, the dome, the propylon chamber) inside a wall00 curtain with a
window00 on most lengths; Indarys Manor is ex_r_pcfort's manor, services, a tower and two houses inside its wall, the
wall climbing by its 'wu' pieces, 128 a step."""
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict

import mapdata

VERSION = 1
CELL = 8192
# the game's forts by the look they are built in: the names their interiors start with (and Tamriel Rebuilt's, when
# loaded: a name not in the load order is passed over)
FORTS = {
    'Imperial': ['moonmoth legion fort', 'buckmoth legion fort', 'pelagiad, fort pelagiad', 'gnisis, fort darius', 'fort frostmoth',
                 'ebonheart, hawkmoth', 'ebonheart, castle ebonheart', 'firemoth legion fort', 'wavemoth legion fort', 'windmoth legion fort',
                 'swordmoth legion fort', 'fort ancylis', 'fort heath', 'fort telodrach', 'fort umbermoth', 'firewatch, dustmoth legion garrison',
                 'firewatch, ember keep', 'firewatch, wall towers'],
    'Stronghold': ['andasreth', 'hlormaren', 'berandas', 'falensarano', 'marandus', 'rotheran', 'valenvaryon', 'indoranyon',
                   'telasero', 'falasmaryon'],
    'Redoran': ['indarys manor'],
    'Hlaalu': ['rethan manor'],
    'Telvanni': ['tel uvirith'],
    'Nordic': ['raven rock, factor', 'castle karstaag'],
}
# what an interior is, by its name
ROLES = [('towers', r'towers?$|curtain wall|perimeter wall|wall towers|watchtower|gate tower|lookout|\b(north|south|east|west) wall$'),
         ('prison', r'prison|dungeon|jail|cells'), ('gatehouse', r'gatehouse'), ('chapel', r'chapel|shrine|temple'),
         ('armoury', r'armou?ry|supply'), ('barracks', r'barracks|quarters|garrison'), ('propylon', r'propylon'),
         ('dome', r'\bdome\b'), ('lower', r'lower|bottom|underground|sewer|cellar'), ('keep', r'.')]
# what a room holds, by its things' names
KINDS = [('bed', r'bed|bunk|hammock|bedroll'), ('weapons', r'weaponrack|weapon_rack|_rack_|swordrack|spearrack'),
         ('armour', r'mannequin|armou?r_?stand'), ('shrine', r'altar|shrine'), ('throne', r'throne'), ('table', r'table'),
         ('prison', r'jail|cell_door|prison|_bars|shackle|cagedoor'), ('books', r'bookshelf|bookcase'),
         ('store', r'crate|barrel|sack'), ('cook', r'cauldron|oven|fireplace|hearth|cookpot'), ('chest', r'chest'),
         ('stairs', r'stair|ramp|ladder|spiral'), ('banner', r'banner|tapestry')]
KR = [(k, re.compile(p, re.I)) for k, p in KINDS]
NOT_PIECE = re.compile(r'terrain|flora|tree|rock|grass|bush|kelp|_mt_|mtpeak|marker|bucket|scaffold|rubble|debris|ruin|constr|lockedd', re.I)
# (a fort's own wall pieces a keep may grow into: only the round towers' stacks and the stair towers that stand with it)
STACK = re.compile(r'towers?b?_(base|dark|med|light|top|roof)|guardtower_01|keep|fort0|pcfort_0|enter', re.I)
SPIRAL = re.compile(r'spiral', re.I)
GROUPED = ('Redoran', 'Hlaalu')
WHOLE = {'Stronghold': re.compile(r'^ex_strong', re.I)}
KEEP_MAIN = re.compile(r'keep_0|fort00|pcfort_0[1-4]$|_x_keep_', re.I)
_mem = {}


def _disk(db):
    import project
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    sig = hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'castlesurvey_%s_v%d.json' % (sig, VERSION))


def role_of(key):
    tail = key.split(',', 1)[-1] if ',' in key else key
    for r, p in ROLES:
        if re.search(p, tail, re.I):
            return r
    return 'keep'


def _cells_of(db, group):
    return sorted(k for (t, k) in db.by_key if t == 'CELL' and not k.startswith('#') and (k == group or k.startswith(group + ',') or k.startswith(group + ' ')))


def _wbox(r, pad=0.0):
    """A ref's box in the world: [x0, y0, z0, x1, y1, z1]."""
    b, s = r['b'], r.get('s') or 1.0
    c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
    pts = [(r['p'][0] + (x * c + y * sn) * s, r['p'][1] + (-x * sn + y * c) * s) for x in (b[0], b[3]) for y in (b[1], b[4])]
    return [min(p[0] for p in pts) - pad, min(p[1] for p in pts) - pad, r['p'][2] + b[2] * s - pad,
            max(p[0] for p in pts) + pad, max(p[1] for p in pts) + pad, r['p'][2] + b[5] * s + pad]


def _touch(a, b):
    return a[0] <= b[3] and b[0] <= a[3] and a[1] <= b[4] and b[1] <= a[4] and a[2] <= b[5] and b[2] <= a[5]


def local(A, wx, wy):
    """World (wx, wy) in the frame of a ref A (its rz turns clockwise, as adjacency.to_local)."""
    c, s = math.cos(A[5]), math.sin(A[5])
    dx, dy = wx - A[0], wy - A[1]
    return dx * c - dy * s, dx * s + dy * c


def world(A, lx, ly):
    c, s = math.cos(A[5]), math.sin(A[5])
    return A[0] + lx * c + ly * s, A[1] - lx * s + ly * c


def _inside_out(r, x, y, z):
    """How far a point lies outside a ref's own box (0: inside)."""
    lx, ly = local(r['p'], x, y)
    s = r.get('s') or 1.0
    lx, ly, lz = lx / s, ly / s, (z - r['p'][2]) / s
    b = r['b']
    return max(b[0] - lx, lx - b[3], b[1] - ly, ly - b[4], b[2] - lz, lz - b[5], 0.0)


def _room(db, key):
    m = mapdata.cellmap(db, key)
    if not m.get('exists'):
        return None
    refs = m['refs']
    arch = [r for r in refs if r.get('arch') and r.get('b')]
    kinds = Counter()
    for r in refs:
        for k, rx in KR:
            if rx.search(r['id']):
                kinds[k] += 1
                break
    box = None
    if arch:
        bs = [_wbox(r) for r in arch]
        box = [round(min(b[i] for b in bs)) for i in range(3)] + [round(max(b[i] for b in bs)) for i in range(3, 6)]
    doors = [{'k': r['k'], 'id': r['id'], 'p': r['p'], 'to': (r['to']['cell'] or '').lower() if r['to']['cell'] else '#',
              'tp': [r['to']['x'], r['to']['y'], r['to']['z'], r['to']['rz']]} for r in refs if r['type'] == 'DOOR' and r.get('to')]
    return {'key': key, 'name': m.get('name') or key, 'role': role_of(key), 'pieces': len(arch), 'things': len(refs) - len(arch),
            'npcs': sum(1 for r in refs if r['type'] == 'NPC_'), 'creatures': sum(1 for r in refs if r['type'] in ('CREA', 'LEVC')),
            'kinds': dict(kinds), 'box': box, 'doors': doors}


def _outdoor_refs(db, x, y, rad):
    out = []
    for gx in range(math.floor((x - rad) / CELL), math.floor((x + rad) / CELL) + 1):
        for gy in range(math.floor((y - rad) / CELL), math.floor((y + rad) / CELL) + 1):
            key = '#%d,%d' % (gx, gy)
            for r in mapdata.cellmap(db, key).get('refs') or ():
                if math.hypot(r['p'][0] - x, r['p'][1] - y) <= rad:
                    out.append(dict(r, cell=key))
    return out


def _components(keys, edges, skip):
    par = {k: k for k in keys}

    def f(k):
        while par[k] != k:
            par[k] = par[par[k]]
            k = par[k]
        return k
    for a, b in edges:
        if a in par and b in par and a not in skip and b not in skip:
            par[f(a)] = f(b)
    out = defaultdict(list)
    for k in keys:
        if k not in skip:
            out[f(k)].append(k)
    return list(out.values())


def _fort(db, style, group, wallish):
    keys = _cells_of(db, group)
    if not keys:
        return None
    rooms = [r for r in (_room(db, k) for k in keys) if r]
    if not rooms:
        return None
    # (what lies behind those doors and leads on is the fort's too: its prison, a commander's chambers)
    seen = {r['key'] for r in rooms}
    more = True
    while more:
        more = False
        for r in list(rooms):
            for d in r['doors']:
                t = d['to']
                if t != '#' and t not in seen and db.by_key.get(('CELL', t)) and len(seen) < 30:
                    rr = _room(db, t)
                    seen.add(t)
                    if rr:
                        rooms.append(rr)
                        more = True
    keys = [r['key'] for r in rooms]
    edges = sorted({tuple(sorted((r['key'], d['to']))) for r in rooms for d in r['doors'] if d['to'] in seen and d['to'] != r['key']})
    outs = [(r, d) for r in rooms for d in r['doors'] if d['to'] == '#']
    if not outs:
        return None
    cx = sum(d['tp'][0] for _r, d in outs) / len(outs)
    cy = sum(d['tp'][1] for _r, d in outs) / len(outs)
    refs = _outdoor_refs(db, cx, cy, 5000)
    # the fort's outside doors: those leading into its interiors
    edoors = [r for r in refs if r['type'] == 'DOOR' and r.get('to') and (r['to']['cell'] or '').lower() in seen
              and 'marker' not in r['id'].lower()]
    if not edoors:
        return None
    ex = sum(r['p'][0] for r in edoors) / len(edoors)
    ey = sum(r['p'][1] for r in edoors) / len(edoors)
    arch = [r for r in refs if r.get('arch') and r.get('b') and r['type'] != 'DOOR' and not NOT_PIECE.search(r['id']) and math.hypot(r['p'][0] - ex, r['p'][1] - ey) < 4000]
    walls = [r for r in arch if wallish(r['id'].lower())]
    fig = {'name': group, 'style': style, 'centre': [round(ex), round(ey)], 'interiors': len(rooms),
           'links': len(edges), 'doors_out': len(edoors), 'npcs': sum(r['npcs'] for r in rooms),
           'roles': dict(Counter(r['role'] for r in rooms)), 'kinds': dict(sum((Counter(r['kinds']) for r in rooms), Counter())),
           'rooms': [{'key': r['key'], 'role': r['role'], 'pieces': r['pieces'], 'npcs': r['npcs'], 'kinds': r['kinds'],
                      'size': [r['box'][3] - r['box'][0], r['box'][4] - r['box'][1], r['box'][5] - r['box'][2]] if r['box'] else None,
                      'out': sum(1 for d in r['doors'] if d['to'] == '#'), 'to': sorted({d['to'] for d in r['doors'] if d['to'] not in ('#', r['key'])})}
                     for r in rooms],
           'edges': [list(e) for e in edges]}
    if walls:
        bs = [_wbox(r) for r in walls]
        fig['wall_box'] = [round(min(b[0] for b in bs)), round(min(b[1] for b in bs)), round(max(b[3] for b in bs)), round(max(b[4] for b in bs))]
        fig['wall_size'] = [fig['wall_box'][2] - fig['wall_box'][0], fig['wall_box'][3] - fig['wall_box'][1]]
        low = [r['id'].lower() for r in walls]
        fig['wall'] = {'pieces': len(walls), 'towers': sum(1 for l in low if 'tower' in l and not re.search(r'_(dark|med|light|top)_', l)),
                       'gates': sum(1 for l in low if re.search(r'arch|gate|_wa_|_wg_|wallent_01', l)),
                       'corners': sum(1 for l in low if re.search(r'corner|_wc_', l))}
        over = []
        for r in walls:
            g = mapdata.terrain_z(db, r['p'][0], r['p'][1])
            if g is not None:
                over.append(r['p'][2] - g)
        fig['wall']['levels'] = len({round(r['p'][2] / 32) for r in walls})
        fig['wall']['over_ground'] = round(sorted(over)[len(over) // 2]) if over else None
    fig['keeps'] = sum(1 for r in arch if re.search(r'keep|fort0|pcfort_0[1-4]$', r['id'], re.I))
    # door slots: each outside door on the piece that holds it, in that piece's frame, and the room it leads into
    rmap = {r['key']: r for r in rooms}
    slots = []
    hosts = {}
    for d in edoors:
        x, y, z = d['p'][:3]
        best = min(((_inside_out(a, x, y, z), a) for a in arch), key=lambda t: t[0], default=(None, None))
        if best[1] is None or best[0] > 24:
            continue
        a = best[1]
        lx, ly = local(a['p'], x, y)
        to = d['to']['cell'].lower()
        slots.append({'host': a['id'].lower(), 'door': d['id'], 'lx': round(lx), 'ly': round(ly), 'dz': round(z - a['p'][2]),
                      'turn': round(math.degrees(d['p'][5] - a['p'][5])) % 360, 'role': rmap[to]['role'] if to in rmap else role_of(to),
                      'trap': bool(re.search(r'trap|hatch', d['id'], re.I)), 'over': round(z - (mapdata.terrain_z(db, x, y) or z))})
        hosts[d['k'] + '@' + d['cell']] = a
    # modules: for each group of interiors joined without the tower rooms, the outside pieces that hold its doors and
    # those standing with them, in the main piece's frame
    towers = {r['key'] for r in rooms if r['role'] == 'towers'}
    mods = []
    wset = {r['k'] + '@' + r['cell'] for r in walls}
    for comp in _components(keys, edges, towers):
        cset = set(comp)
        ds = [d for d in edoors if d['to']['cell'].lower() in cset]
        hs = [hosts[d['k'] + '@' + d['cell']] for d in ds if (d['k'] + '@' + d['cell']) in hosts]
        hs = [h for h in hs if (h['k'] + '@' + h['cell']) not in wset or re.search(r'keep|fort0|pcfort_0|enter|tower', h['id'], re.I)]
        if not hs:
            continue
        G = {h['k'] + '@' + h['cell']: h for h in hs}
        boxes = {k: _wbox(h, 16) for k, h in G.items()}
        grew = True
        while grew:
            grew = False
            for a in arch:
                ak = a['k'] + '@' + a['cell']
                if ak in G or ak in wset and not STACK.search(a['id']):
                    continue
                ab = _wbox(a, 16)
                if any(_touch(ab, b) for b in boxes.values()):
                    G[ak] = a
                    boxes[ak] = ab
                    grew = True
                    if len(G) > 60:
                        grew = False
                        break
        mods.append({'G': G, 'boxes': boxes, 'ds': ds, 'net': cset})
    # (one module for a keep whose doors lead into several groups of rooms: a stronghold's four entrances)
    merged = []
    for m in mods:
        for o in merged:
            # (a house stronghold's buildings stand together as the game set them round their manor, Indarys's tower,
            # services and house: one module)
            if set(o['G']) & set(m['G']) or style in GROUPED:
                o['G'].update(m['G'])
                o['boxes'].update(m['boxes'])
                o['ds'] += [d for d in m['ds'] if d not in o['ds']]
                o['net'] |= m['net']
                break
        else:
            merged.append(m)
    out = []
    for m in merged:
        G, boxes, ds, cset = m['G'], m['boxes'], m['ds'], m['net']
        main = max(G.values(), key=lambda r: (bool(KEEP_MAIN.search(r['id'])), (r['b'][3] - r['b'][0]) * (r['b'][4] - r['b'][1]) * (r.get('s') or 1) ** 2))
        if style in WHOLE:
            # (a stronghold stands whole: its wall00 lengths are the sides of the platform its keep stands on, not a
            # curtain round a yard, Hlormaren in 3D, 2026-11-01)
            for a in arch:
                ak = a['k'] + '@' + a['cell']
                if ak not in G and WHOLE[style].search(a['id']) and math.hypot(a['p'][0] - main['p'][0], a['p'][1] - main['p'][1]) < 7000:
                    G[ak] = a
                    boxes[ak] = _wbox(a, 16)
        A = main['p']
        g0 = mapdata.terrain_z(db, A[0], A[1])
        pieces = []
        for r in G.values():
            lx, ly = local(A, r['p'][0], r['p'][1])
            pieces.append([r['id'], round(lx, 1), round(ly, 1), round(r['p'][2] - A[2], 1), round((r['p'][5] - A[5]) % (2 * math.pi), 4),
                           round(r['p'][3], 4), round(r['p'][4], 4), r.get('s') or 1.0])
        mdoors = []
        for d in ds:
            lx, ly = local(A, d['p'][0], d['p'][1])
            to = d['to']['cell'].lower()
            bk, tp = _back_door(rmap.get(to), d)
            if tp:
                ox, oy = local(A, tp[0], tp[1])
                tp = [round(ox, 1), round(oy, 1), round(tp[2] - A[2], 1), round((tp[3] - A[5]) % (2 * math.pi), 4)]
            mdoors.append({'id': d['id'], 'p': [round(lx, 1), round(ly, 1), round(d['p'][2] - A[2], 1), round((d['p'][5] - A[5]) % (2 * math.pi), 4)],
                           's': d.get('s') or 1.0, 'to': to, 'arrive': d['to'] and [d['to']['x'], d['to']['y'], d['to']['z'], d['to']['rz']],
                           'back': bk, 'out': tp})
        bs = list(boxes.values())
        lb = [local(A, x, y) for b in bs for x in (b[0], b[3]) for y in (b[1], b[4])]
        out.append({'fort': group, 'style': style, 'main': main['id'].lower(), 'over': round(A[2] - g0) if g0 is not None else 0,
                     'pieces': pieces, 'doors': mdoors, 'network': sorted(cset),
                     'roles': sorted({rmap[k]['role'] for k in cset if k in rmap}),
                     'box': [round(min(p[0] for p in lb)), round(min(p[1] for p in lb)), round(max(p[0] for p in lb)), round(max(p[1] for p in lb))]})
    return {'fig': fig, 'slots': slots, 'modules': out, 'towers': sorted(towers)}


def _back_door(room, d):
    """The door inside a room that leads back out to this outside door: its ref key (the arrival in front of it)."""
    if not room:
        return None, None
    best = None
    for r in room['doors']:
        if r['to'] != '#':
            continue
        dist = math.hypot(r['tp'][0] - d['p'][0], r['tp'][1] - d['p'][1])
        if best is None or dist < best[0]:
            best = (dist, r)
    if best and best[0] < 800:
        return best[1]['k'], best[1]['tp']
    # (else the door nearest where this one sets you down inside)
    a = d['to']
    best = min(room['doors'], key=lambda r: math.dist(r['p'][:3], (a['x'], a['y'], a['z'])), default=None) if room['doors'] else None
    return (best['k'], None) if best else (None, None)


def tower_rooms(db, key):
    """The rooms of a fort's towers interior, each a cluster of touching pieces holding a spiral stair: [{'key', 'refs':
    [ref keys], 'box', 'doors': [{'k', 'id', 'trap', 'dz', 'to'}], 'height'}]."""
    m = mapdata.cellmap(db, key)
    if not m.get('exists'):
        return []
    refs = m['refs']
    arch = [r for r in refs if r.get('arch') and r.get('b') and r['type'] != 'DOOR']
    B = [_wbox(r, 8) for r in arch]
    n = len(arch)
    par = list(range(n))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if _touch(B[i], B[j]):
                par[f(i)] = f(j)
    cl = defaultdict(list)
    for i in range(n):
        cl[f(i)].append(i)
    out = []
    for ix in cl.values():
        if not any(SPIRAL.search(arch[i]['id']) for i in ix):
            continue
        bx = [min(B[i][k] for i in ix) for k in range(3)] + [max(B[i][k] for i in ix) for k in range(3, 6)]
        if bx[3] - bx[0] > 1400 or bx[4] - bx[1] > 1400:
            continue                     # (a tower joined to a run of wall passages: not one tower's room)
        inside = [r for r in refs if r['type'] != 'DOOR' and r not in [arch[i] for i in ix] and bx[0] <= r['p'][0] <= bx[3] and bx[1] <= r['p'][1] <= bx[4]
                  and bx[2] <= r['p'][2] <= bx[5] and r['type'] not in ('NPC_', 'CREA', 'LEVC')]
        ds = [r for r in refs if r['type'] == 'DOOR' and bx[0] - 32 <= r['p'][0] <= bx[3] + 32 and bx[1] - 32 <= r['p'][1] <= bx[4] + 32
              and bx[2] - 32 <= r['p'][2] <= bx[5] + 32]
        if not ds:
            continue
        out.append({'key': key, 'refs': [arch[i]['k'] for i in ix] + [r['k'] for r in inside], 'box': [round(v) for v in bx],
                    'height': round(bx[5] - bx[2]),
                    'doors': [{'k': r['k'], 'id': r['id'], 'trap': bool(re.search(r'trap|hatch', r['id'], re.I)), 'dz': round(r['p'][2] - bx[2]),
                               'to': ((r['to']['cell'] or '#').lower() if r.get('to') else '')} for r in ds]})
    return out


def survey(db, force=False):
    k = id(db.recs)
    if k in _mem and not force:
        return _mem[k]
    path = _disk(db)
    if os.path.isfile(path) and not force:
        try:
            out = json.load(open(path, encoding='utf-8'))
            # (JSON keeps keys as text: a wall kit's corners are keyed by the turn's hand, -1 and 1, and read back as
            # '-1' and '1' no corner was found, "This wall turns only one way", every Redoran castle after a restart)
            for kit in (out.get('wall_kits') or {}).values():
                kit['corners'] = {int(h): v for h, v in kit.get('corners', {}).items()}
            _mem[k] = out
            return _mem[k]
        except Exception:
            pass
    import townwalls
    K = townwalls.kits(db)
    kit_models = {m for kk in K.values() for m in kk['models']}
    wallish = lambda l: l in kit_models or bool(re.search(r'^ex_imp_(wall|guardtower|towerb?s?_)|^ex_stronghold_wall|_pcfort_w[sca-z]', l))
    out = {'forts': [], 'slots': defaultdict(list), 'modules': [], 'tower_rooms': []}
    for style, groups in FORTS.items():
        for g in groups:
            try:
                F = _fort(db, style, g, wallish)
            except Exception as e:
                print('castle survey %s: %s' % (g, e))
                continue
            if not F:
                continue
            out['forts'].append(F['fig'])
            for s in F['slots']:
                out['slots'][s['host']].append(dict(s, fort=g))
            out['modules'] += F['modules']
            for t in F['towers']:
                for tr in tower_rooms(db, t):
                    out['tower_rooms'].append(dict(tr, fort=g, style=style))
    out['slots'] = dict(out['slots'])
    out['wall_kits'] = _house_kits(db)
    _mem[k] = out
    try:
        json.dump(out, open(path, 'w', encoding='utf-8'))
    except Exception as e:
        print('castle survey save:', e)
    return out


# the great houses' own fort walls (the player's strongholds): learnt from where the game stands them, as townwalls' kits
HOUSE_WALLS = {'ex_r_pcfort': ('indarys manor', r'^ex_r_pcfort_w[scua]_01$'), 'ex_h_pcfort': ('rethan manor', r'^ex_h_pcfort_w[cgu]?_0[12]$')}


def _house_kits(db):
    """{family: townwalls kit} for walls the outdoor survey has no joins for (Indarys's are only there once the player
    has had them built): their joins read from the places themselves."""
    import townwalls
    out = {}
    for fam, (group, pat) in HOUSE_WALLS.items():
        keys = _cells_of(db, group)
        rooms = [r for r in (_room(db, k) for k in keys) if r]
        outs = [d for r in rooms for d in r['doors'] if d['to'] == '#']
        if not outs:
            continue
        cx = sum(d['tp'][0] for d in outs) / len(outs)
        cy = sum(d['tp'][1] for d in outs) / len(outs)
        ws = [r for r in _outdoor_refs(db, cx, cy, 4000) if re.search(pat, r['id'].lower()) and r.get('b')]
        JN = defaultdict(Counter)
        placed = Counter(r['id'].lower() for r in ws)
        for a in ws:
            for b in ws:
                if a is b or math.hypot(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1]) > 420:
                    continue
                lx, ly = local(a['p'], b['p'][0], b['p'][1])
                turn = round(math.degrees(b['p'][5] - a['p'][5])) % 360
                turn = turn - 360 if turn > 180 else turn
                e = (round(lx), round(ly), round(b['p'][2] - a['p'][2]), turn)
                JN[a['id'].lower()][(b['id'].lower(), e)] += 1
        jn = {m: [(t, 2 * n, list(e)) for (t, e), n in c.items()] for m, c in JN.items()}   # (x2: built once)
        kit = townwalls._kit(fam, set(placed), jn, dict(placed))
        if kit and not any(v['kind'] == 'gate' for v in kit['inline'].values()):
            # (its gate, built once at Indarys: ex_r_pcfort_wa_01, 512 long, set in line where two lengths would stand,
            # the lengths running on either side of it, lab c10)
            for g in sorted(m for m in placed if re.search(r'_w[ag]_', m)):
                ri = db.resolve_id(g)
                b = mapdata.object_bounds(db, ri) if ri is not None else None
                if not b:
                    continue
                half = (b[3] - b[0]) / 2.0 if kit['axis'] == 0 else (b[4] - b[1]) / 2.0
                a = kit['L'] / 2.0 + half
                e = [a, 0, 0, 0] if kit['axis'] == 0 else [0, a, 0, 0]
                kit['inline'][g] = {'a': a, 'span': 2 * a, 'e1': e, 'e2': e, 'n': 2, 'kind': 'gate', 'every': 99.0}
                break
        if kit:
            ups = _ups(jn, kit)
            kit['ups'] = ups
            out[fam] = kit
    return out


def _ups(jn, kit):
    """The pieces that carry the run up or down a step (Indarys's 'wu_01'): {model: [dz per piece, the join after it]}."""
    S, ax = kit['straight'], kit['axis']
    out = {}
    for t, n, e in jn.get(S, ()):
        if t == S or abs(e[3]) > 2 or e[ax] <= 0:
            continue
        for t2, n2, e2 in jn.get(t, ()):
            if t2 == S and abs(e2[3]) <= 2 and e2[ax] > 0 and abs(e[2] + e2[2]) >= 32:
                if t not in out or min(n, n2) > out[t]['n']:
                    out[t] = {'e1': e, 'e2': e2, 'dz': e[2] + e2[2], 'n': min(n, n2)}
    return out


def ready(db):
    return id(db.recs) in _mem or os.path.isfile(_disk(db))
