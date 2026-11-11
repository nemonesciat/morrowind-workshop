"""The game's towns, read whole (the user, 2026-10-30: "start developing the Cities content. survey by culture, learn to
plan and build towns with previews, at least as nice as the dungeon generator").

A town is the neighbouring outdoor cells with three or more building doors (the buildings outside the game's interiors,
shellsurvey's pairs). Each is kept with:

  its cells and name, its culture (the style most of its buildings are in: mapdata.style_of their main piece)
  every building once: its door (where, which way it opens), its outline in the world, what it is (house, shop, tavern,
    temple, guild, manor, guard, by its interior's name), its style and main piece, the interior behind it
  its roads: the land patches (512 across) painted with a road-like texture
  its street furniture: lamps, banners and signs, fences, wells, statues, benches, planters, stalls, where they stand

and stats() reads off each culture's figures: how many buildings a cell, how far apart, how many doors open onto a road,
how much of the land is road and how wide the streets are, the mix of kinds, what lines the streets."""
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict, deque

import mapdata

VERSION = 4                     # (2: each building's own width and depth, as it faces its door; 3: town_style; 4: Anvil, Gold Coast)
TOWN_DOORS = 3                  # building doors a cell needs to be a town's
CELL = 8192
PATCH = 512
ROAD = re.compile(r'road|cobble|path|street|pave|brick|flagstone|walkway|stone_?floor|plaza')
KINDS = [('tavern', r'tavern|cornerclub|club|tradehouse|hostel|\binn\b'), ('temple', r'temple|shrine|chapel|cult'),
         ('guild', r'guild|fighters|mages|thieves'),
         ('shop', r'smith|trader|pawnbroker|outfitter|clothier|alchemist|apothecary|bookseller|enchanter|store|shop|merchant|goods|market|tailor|baker'),
         ('manor', r'manor|council|palace|villa|hall\b'), ('guard', r'fort|keep|garrison|barracks|guard|tower|watch'),
         ('house', r'house|home|shack|hut|residence|hovel|cottage|lodge|apartment|yurt')]
STREET = [('lamp', r'lamppost|streetlight|light_.*(post|pole|street)|lantern.*post|lamp_?post|_lamp_|light_com_lantern'),
          ('banner', r'banner|flag|sign'), ('well', r'(^|_)well'), ('statue', r'statue'), ('bench', r'bench'),
          ('planter', r'planter|flowerpot'), ('fence', r'fence|railing'), ('stall', r'stall|market|awning|cart')]
_mem = {}


def _disk(db):
    import project
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    sig = hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'townsurvey_%s_v%d.json' % (sig, VERSION))


def town_style(main):
    """A building's style as a town's culture: mapdata.style_of, but the game's colonial towns (Seyda Neen, Caldera,
    Pelagiad) are built of its common pieces and its ex_nord cottages, a style of their own ('Common'), not Nordic;
    Skaal's longhouses and Tamriel Data's log cabins are the Nordic ones. (style_of filed all three towns as Nordic.)"""
    low = (main or '').lower()
    if 'common' in low or low.startswith('ex_nord_'):
        return 'Common'
    if low.startswith('ex_s_longhouse') or low.startswith(('t_nor_', 't_sky_')):
        return 'Nordic'
    if low.startswith(('ex_cave', 'ex_snow', 'terrain_')):
        return ''
    # (the Imperial towns are two looks the builder mixed, the user 2026-10-31: Anvil's own sets, and the Gold Coast's
    # villages; the classic ex_imp stays "Imperial", the forts and Ebonheart's)
    if low.startswith(('t_imp_setanv', 't_imp_setstr')):
        return 'Anvil'
    if low.startswith('t_imp_setgc'):
        return 'Gold Coast'
    return mapdata.style_of(main) or ''


# (whose towns lend a look their streets, squares, yards and roads: the classic Imperial look's own game towns are forts
# and Ebonheart, with no streets to learn from, and a town of it came out bare, no gate, road or yard; its buildings stay
# its own, cold-start test of 2.6.1-test3)
KIN = {'Imperial': ('Common', 'Gold Coast')}         # (Common first: the game mixes the two, Pelagiad, Old Ebonheart)


FORT_TOWN = re.compile(r'fort|legion|garrison|keep|barracks')


def kind_of(name):
    """The kind of place a cell's name tells: read from the place's own part, after the town's ("Firewatch, Dralas
    House" is a house, not a guard post for its town's 'watch'; "Skaal Village, ..." no manor for its 'villa': a third
    of a Common town's plots stood guard houses, the user's North Senchal, 2026-11-09). A fort's own rooms stay its."""
    low = (name or '').lower()
    head, sep, tail = low.partition(', ')
    if sep:
        for k, rx in KINDS:
            if re.search(rx, tail):
                return k
        return 'guard' if FORT_TOWN.search(head) else 'other'
    for k, rx in KINDS:
        if re.search(rx, low):
            return k
    return 'other'


def _rekind(out):
    """A learnt survey's kinds read again from its names (kind_of changed with no relearning)."""
    for t in out.get('towns') or ():
        for b in t.get('buildings') or ():
            if b.get('name'):
                b['kind'] = kind_of(b['name'])
    return out


def street_kind(low):
    for k, rx in STREET:
        if re.search(rx, low):
            return k
    return None


def _box(ef, b):
    """A building's box (in its door's frame: +y inward, +x to the right) as a world box."""
    ux, uy = ef['ux'], ef['uy']
    L = math.hypot(ux, uy) or 1.0
    ux, uy = ux / L, uy / L
    pts = [(ef['x'] + fx * uy + fy * ux, ef['y'] - fx * ux + fy * uy) for fx in (b[0], b[2]) for fy in (b[1], b[3])]
    return [round(min(p[0] for p in pts)), round(min(p[1] for p in pts)), round(max(p[0] for p in pts)), round(max(p[1] for p in pts))]


def ready(db):
    """The survey if learnt (in memory or on disk); else None, and the survey process learns it meanwhile."""
    if id(db.recs) in _mem or os.path.isfile(_disk(db)):
        try:
            return survey(db)
        except Exception:
            return None
    import background
    background.start("the game's towns", lambda: survey(db), task=('townsurvey', 'survey', []))
    return None


def survey(db):
    """{'towns': [{'name', 'cells', 'culture', 'buildings': [...], 'roads': ['X,Y' patches], 'street': [...]}]} (on disk)."""
    key = id(db.recs)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            _mem[key] = _rekind(json.load(f))
            return _mem[key]
    except (OSError, ValueError):
        pass
    import shellsurvey as ss
    import landscape
    from project import ref_info
    pairs = ss.survey(db)['pairs']
    by_cell = defaultdict(list)
    for p in pairs:
        ef = p['eframe']
        by_cell[(math.floor(ef['x'] / CELL), math.floor(ef['y'] / CELL))].append(p)
    town_cells = {c for c, v in by_cell.items() if len(v) >= TOWN_DOORS}
    seen, groups = set(), []
    for c in sorted(town_cells):
        if c in seen:
            continue
        q, g = [c], []
        seen.add(c)
        while q:
            a = q.pop()
            g.append(a)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    b = (a[0] + dx, a[1] + dy)
                    if b in town_cells and b not in seen:
                        seen.add(b)
                        q.append(b)
        groups.append(sorted(g))
    towns = []
    for g in groups:
        bl, where = [], set()
        for c in g:
            for p in by_cell[c]:
                b = p['building'].get('box')
                if not b:
                    continue
                ef = p['eframe']
                wb = _box(ef, b)
                sig = (round(wb[0] / 32), round(wb[1] / 32), round(wb[2] / 32), round(wb[3] / 32))
                if sig in where:
                    continue                  # (one building, two interiors: a house and the flat over it)
                where.add(sig)
                main = p['building'].get('main') or ''
                bl.append({'x': round(ef['x']), 'y': round(ef['y']), 'z': round(ef.get('z', 0)),
                           # (which way the door opens: from the door out, the opposite of the frame's inward)
                           'face': round(math.atan2(-ef['ux'], -ef['uy']), 4), 'box': wb, 'kind': kind_of(p['name']),
                           'style': town_style(main), 'main': main, 'interior': p['key'], 'name': p['name'],
                           'height': p['building'].get('height'),
                           # (its own size: across its front, and from its front back, in its door's frame)
                           'fw': round(b[2] - b[0]), 'fd': round(b[3] - b[1]), 'fy0': round(b[1])})
        styles = Counter(b['style'] for b in bl if b['style'])
        culture = styles.most_common(1)[0][0] if styles else ''
        # (a colonial town has its share of Dunmer shacks and Imperial walls: common pieces in a third of it make it one)
        if styles.get('Common', 0) >= 0.3 * sum(styles.values()):
            culture = 'Common'
        names = Counter((mapdata.cell_info(db, '#%d,%d' % c) or {}).get('name') or '' for c in g)
        name = next((n for n, _k in names.most_common() if n), '')
        roads, street = [], []
        for gx, gy in g:
            L = landscape.read(db, gx, gy)
            if L.get('exists') and L.get('t'):
                tex = L.get('tex') or {}
                for n_, t in enumerate(L['t']):
                    if t and ROAD.search((t + ' ' + (tex.get(t) or '')).lower()):
                        roads.append('%d,%d' % (gx * 16 + n_ % 16, gy * 16 + n_ // 16))
            refs, _h = db.cell_refs('#%d,%d' % (gx, gy))
            for r in refs.values():
                rid, pos, s, dead = ref_info(r['subs'])
                if dead or not rid:
                    continue
                k = street_kind(rid.lower())
                if k:
                    street.append({'k': k, 'id': rid, 'p': [round(v, 1) if i < 3 else round(v, 4) for i, v in enumerate(pos)], 's': s or 1.0})
        towns.append({'name': name, 'cells': [list(c) for c in g], 'culture': culture, 'buildings': bl, 'roads': roads, 'street': street})
    out = {'version': VERSION, 'towns': towns}
    _mem[key] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except OSError:
        pass
    return out


def _widths(roads):
    """Each road patch's street width, in patches: the shorter of its runs across (east-west or north-south)."""
    S = {tuple(int(v) for v in k.split(',')) for k in roads}
    out = []
    for x, y in S:
        def run(dx, dy):
            n, a, b = 1, (x - dx, y - dy), (x + dx, y + dy)
            while a in S:
                n += 1
                a = (a[0] - dx, a[1] - dy)
            while b in S:
                n += 1
                b = (b[0] + dx, b[1] + dy)
            return n
        out.append(min(run(1, 0), run(0, 1)))
    return out


def _squares(roads, size=3):
    """Road patches that are part of a size x size block of road: a square, not a street."""
    S = {tuple(int(v) for v in k.split(',')) for k in roads}
    sq = set()
    for x, y in S:
        if all((x + i, y + j) in S for i in range(size) for j in range(size)):
            sq.update((x + i, y + j) for i in range(size) for j in range(size))
    return len(sq)


def stats(db):
    """Each culture's figures from its towns: {culture: {...}}."""
    T = survey(db)['towns']
    C = defaultdict(lambda: {'towns': [], 'buildings': 0, 'cells': 0, 'kinds': Counter(), 'gap': [], 'door_road': [], 'road': [],
                             'width': [], 'square': [], 'street': Counter(), 'size': [], 'turns': []})
    for t in T:
        D = C[t['culture'] or '?']
        bl = t['buildings']
        D['towns'].append(t['name'] or '?')
        D['buildings'] += len(bl)
        D['cells'] += len(t['cells'])
        roads = {tuple(int(v) for v in k.split(',')) for k in t['roads']}
        D['road'].append(len(roads) / (256.0 * len(t['cells'])))
        D['width'] += _widths(t['roads'])
        D['square'].append(_squares(t['roads']) / max(1.0, len(roads)))
        for k in t['street']:
            D['street'][k['k']] += 1
        for b in bl:
            # (each town counts the same, its kinds as shares of its own buildings: pooled, Old Ebonheart's 109 guard
            # towers made a third of every Common town's plots guard posts, the user's island town, test3)
            D['kinds'][b['kind']] += 100.0 / max(1, len(bl))
            bx = b['box']
            D['size'].append(max(bx[2] - bx[0], bx[3] - bx[1]))
            # (does the door open onto a road: any road patch within 384 in front of it)
            fx, fy = math.sin(b['face']), math.cos(b['face'])
            D['door_road'].append(any((int((b['x'] + fx * d) // PATCH), int((b['y'] + fy * d) // PATCH)) in roads for d in (128, 256, 384)))
            # (and is the building square to the town's grid or turned: its door's turn off the nearest quarter)
            D['turns'].append(abs(((b['face'] + math.pi / 4) % (math.pi / 2)) - math.pi / 4))
        boxes = [b['box'] for b in bl]
        for i, a in enumerate(boxes):
            best = None
            for j, c in enumerate(boxes):
                if i == j:
                    continue
                dx = max(0, max(a[0], c[0]) - min(a[2], c[2]))
                dy = max(0, max(a[1], c[1]) - min(a[3], c[3]))
                d = math.hypot(dx, dy)
                if best is None or d < best:
                    best = d
            if best is not None:
                D['gap'].append(best)
    def q(v, f):
        v = sorted(v)
        return round(v[min(len(v) - 1, int(len(v) * f))], 2) if v else None
    out = {}
    for c, D in C.items():
        out[c] = {'towns': D['towns'], 'buildings': D['buildings'], 'per_cell': round(D['buildings'] / max(1, D['cells']), 2),
                  'kinds': {k: round(v, 2) for k, v in D['kinds'].most_common()}, 'gap': [q(D['gap'], f) for f in (0.25, 0.5, 0.75)],
                  'joined': round(sum(1 for g in D['gap'] if g < 8) / max(1, len(D['gap'])), 2),
                  'door_road': round(sum(D['door_road']) / max(1, len(D['door_road'])), 2), 'road': q(D['road'], 0.5),
                  'width': [q(D['width'], f) for f in (0.5, 0.9)], 'square': q(D['square'], 0.5),
                  'street': {k: round(v / max(1, D['cells']), 1) for k, v in D['street'].most_common()},
                  'size': [q(D['size'], f) for f in (0.25, 0.5, 0.75)],
                  'square_to_grid': round(sum(1 for a in D['turns'] if a < math.radians(5)) / max(1, len(D['turns'])), 2)}
    return out
