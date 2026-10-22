"""Auto-furnish: fill the rooms of an interior with fitting furniture and clutter.

Rooms are found from the place's floor pieces (the same kit measurements the builder uses).
What goes in them comes from similar places in your load order, so a Hlaalu house gets Hlaalu
furniture. Which way each piece of furniture faces is learnt from where it stands in real
interiors (it faces into the room), so beds and shelves end up with their backs to the wall."""
import math
import random
import re
import sys
from collections import Counter
import struct

import editing
import kits
import mapdata
from editing import EditError
from esm import zstr
from project import ref_info, set_ref_pos, split_cell, zs

STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

# what a kind of furniture is called, by words in its ID or name (and the record types it can be)
FAMILIES = {
    'bed': (('bed', 'bunk'), ('STAT', 'ACTI')),
    'table': (('table',), ('STAT', 'ACTI')),
    'chair': (('chair', 'stool'), ('STAT', 'ACTI')),
    'bench': (('bench',), ('STAT', 'ACTI')),
    'bookshelf': (('bookshelf', 'bookcase'), ('STAT', 'ACTI', 'CONT')),
    'shelf': (('shelf',), ('STAT', 'ACTI', 'CONT')),
    'cupboard': (('cupboard', 'closet', 'dresser', 'wardrobe', 'armoire', 'drawers'), ('CONT', 'STAT')),
    'chest': (('chest',), ('CONT',)),
    'crate': (('crate',), ('CONT', 'STAT')),
    'barrel': (('barrel',), ('CONT', 'STAT')),
    'sack': (('sack',), ('CONT', 'STAT')),
    'urn': (('urn', '_pot'), ('CONT', 'STAT')),
    'rug': (('rug', 'carpet'), ('STAT',)),
    'counter': (('counter', 'bar'), ('STAT', 'ACTI')),      # (the game's counters are its "bar" pieces)
    'shrine': (('shrine', 'altar'), ('ACTI', 'STAT')),         # (NOT: a bare altar base, block or slab with no statue on it)
    'dish': (('plate', 'bowl', 'cup', 'goblet', 'mug', 'pitcher', 'tankard', 'flask', 'jug'), ('MISC',)),
    'bottle': (('bottle',), ('MISC', 'ALCH')),
    'book': (('',), ('BOOK',)),
    'food': (('',), ('INGR',)),
    'candle': (('candle',), ('LIGH',)),
    'bedroll': (('bedroll', 'bedding', 'hammock'), ('STAT', 'ACTI')),
    'fire': (('firepit', 'fire_pit', 'campfire', 'fireplace', 'cookingfire', 'cookfire', 'hearth', 'stove', 'oven'), ('STAT', 'ACTI', 'LIGH')),
    # (the set pieces' other kinds the game stands loose too: a basket by the sacks, a folding screen or a
    # planter against a wall; none of them says what kind of room it is)
    'basket': (('basket',), ('CONT', 'STAT')),
    'screen': (('wallscreen', 'screen'), ('STAT',)),
    'planter': (('planter', 'flowerbox', 'plantpot', 'plant_pot'), ('STAT', 'ACTI', 'CONT')),
    # (the room-kind survey's kinds: a bathing room's tub or basin, an armoury's weapon rack, a training
    # room's practice dummy)
    'bath': (('bath', 'tub', 'basin', 'washstand'), ('STAT', 'ACTI', 'CONT')),
    'winerack': (('winerack', 'wine_rack', 'bottlerack'), ('STAT', 'CONT', 'ACTI')),     # (a dining room's, on the wall; stocked by the dressings)
    'rack': (('weaponrack', 'weapon_rack', 'armorrack', 'armourrack'), ('STAT', 'CONT', 'ACTI')),
    'target': (('practice_dummy', 'dummy', 'archerytarget', 'archery_target', 'target_'), ('STAT', 'ACTI')),
}
NOT = {'table': ('tablet',), 'bed': ('bedroll',), 'shelf': ('bookshelf', 'bookcase'), 'chest': ('chestnut',),
       'counter': ('door', 'barrel'), 'screen': ('in_', 'ex_', 'marker', 'window'), 'planter': ('marker',),
       'fire': ('in_', 'ex_', 'marker', 'chimney', 'smoke', 'light_fire', 'sound'),      # (a kit's hearth wall is the building, not furniture)
       'shrine': ('base', 'block', 'slab', 'pedestal', 'stand', 'platform', 'plinth', 'podium', 'pillar', 'column', 'cube', 'step', 'in_', 'ex_'),
       'bath': ('tube', 'bathroom', 'marker', 'in_', 'ex_'), 'rack': ('wine', 'bottle', 'scroll', 'spice', 'coat', 'hat'), 'target': ('targeting', 'marker')}
# (a bare stone piece: an altar base, a block, a slab, a plinth, a pedestal with nothing on it. Never
# furniture in a house, whatever family a name puts it in: the user's "white stone block" by a tapestry)
BARE_STONE = re.compile(r'(altar|shrine)[^a-z]*(base|block|slab|plinth|pedestal|step|platform)|pedestal|plinth|podium|_slab|stoneblock|stone_block|marbleblock')
HANGING_KINDS = ('shelf',)      # the only furniture put up on a wall (at the height the game hangs it)
WINERACK = re.compile(r'winerack|wine_rack|bottlerack')
COUNTER_PART = re.compile(r'_end|_cnr|corner|_curve|_short|_half')      # the end and corner pieces of a counter run
KEEPER_GAP = 96                 # a counter stands this far off the wall: the keeper's side (the game's traders stand 71 behind it)
TALL_BOTTLE = re.compile(r'misc_com_bottle|t_com_bottle|t_imp_drink_|t_de_drink_|wine')     # the slim bottles the game racks
FAT_BOTTLE = re.compile(r'^potion_|^p_|liquor|brew|brandy|whiskey|sujamma|mazte|shein|greef|flin|cyro')   # Dunmer flasks and potions
DRESSED_KINDS = ('bookshelf', 'shelf', 'table', 'counter', 'rack', 'cupboard')     # set out the way the game dresses the model (shelfsurvey.py)
ARRANGE = True                  # lay the game's own set pieces first (arrangesurvey.py)
SCENES = True                   # and every recipe kind the game keeps company as a scene (arrangesurvey.scene)
SCENE_KINDS = ('table', 'bed', 'bookshelf', 'shelf', 'cupboard', 'counter', 'shrine', 'bench', 'planter', 'fire', 'chest', 'screen')
SMALL_KINDS = ('crate', 'planter', 'urn', 'basket', 'chest', 'sack', 'barrel', 'screen')   # never alone in open floor
# what rides on what: a set piece's small member only on the kind of main piece the game had it on
SURFACE_KINDS = ('table', 'counter', 'shelf', 'bookshelf', 'cupboard', 'chest', 'crate', 'barrel', 'bench')
RIDE = {'pillow': ('bed', 'bench', 'chair'), 'plant': ('planter',), 'basket': SURFACE_KINDS, 'lamp': SURFACE_KINDS + ('bed',),
        'apparatus': ('table', 'counter', 'shelf', 'bookshelf', 'cupboard')}
HANGING_LIGHT = re.compile(r'chandelier|candelabra|lantern|hanging|_hang|chain')
ESSENTIAL = {'bedroom': 'bed', 'shop': 'counter', 'tavern': 'counter', 'shrine': 'shrine', 'bath': 'bath', 'barracks': 'bed',
             'armoury': 'rack', 'mess': 'table', 'training': 'target', 'dining': 'table'}   # the piece a room of the kind is for
CONTAINER_KINDS = ('chest', 'crate', 'barrel', 'sack', 'urn', 'cupboard')   # the game's own filled ones, by room (containersurvey.py)
# how the game groups its floor clutter, until the room survey has counted its groups (roomrules.clusters):
# groups of two to five, mostly along the walls, a fifth out on the floor, a crate's width apart
DEFAULT_CLUSTERS = {'sizes': [[1, 0.25], [2, 0.3], [3, 0.25], [4, 0.12], [5, 0.08]], 'where': {'corner': 0.3, 'wall': 0.5, 'middle': 0.2},
                    'nn': {'crate': 70, 'barrel': 70, 'sack': 55, 'urn': 60, 'basket': 50, 'chest': 80}, 'nn_any': 65, 'mixed': 0.3, 'groups': 0}
last_placed = []                # what the last Auto-furnish put where (for tests)
last_trace = []                 # why recipe items were left out: (room, kind, id, reason) (for tests)
last_clutter = []               # how the clutter groups went (for tests)
last_dress = []                 # (model, room, things in the dressing, things that stood) per dressed piece (for tests)

# what goes in a kind of room: (kind of thing, how many, where). Rugs go where the game puts them: under
# the table, beside the bed, in front of a shrine or counter (where people stand); a long one down a hall;
# a small mat inside the front door (see furnish())
RECIPES = {
    'bedroom': [('bed', 1, 'wall'), ('rug', 1, 'by_bed'), ('chest', 1, 'wall'), ('cupboard', 1, 'wall'),
                ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('candle', 1, 'on_table'), ('book', 1, 'on_table'),
                ('dish', 1, 'on_table')],
    'living': [('table', 1, 'centre'), ('rug', 1, 'under_table'), ('chair', 3, 'by_table'), ('bench', 1, 'wall'),
               ('shelf', 1, 'wall'), ('cupboard', 1, 'wall'), ('urn', 1, 'corner'), ('dish', 3, 'on_table'),
               ('bottle', 2, 'on_table'), ('food', 2, 'on_table')],
    'kitchen': [('table', 1, 'wall'), ('cupboard', 1, 'wall'), ('chair', 2, 'by_table'), ('barrel', 2, 'corner'), ('sack', 2, 'wall'),
                ('crate', 1, 'wall'), ('shelf', 1, 'wall'), ('food', 4, 'on_table'), ('dish', 3, 'on_table')],
    'storage': [('crate', 3, 'wall'), ('barrel', 3, 'corner'), ('sack', 3, 'wall'), ('chest', 1, 'wall'),
                ('urn', 2, 'corner')],
    'study': [('bookshelf', 2, 'wall'), ('table', 1, 'centre'), ('rug', 1, 'under_table'), ('chair', 1, 'by_table'),
              ('book', 3, 'on_table'), ('candle', 1, 'on_table'), ('cupboard', 1, 'wall')],
    'shop': [('counter', 1, 'centre'), ('rug', 1, 'before'), ('shelf', 2, 'wall'), ('chest', 1, 'wall'), ('crate', 2, 'wall'),
             ('barrel', 1, 'corner'), ('bottle', 2, 'on_table'), ('dish', 2, 'on_table')],
    'shrine': [('shrine', 1, 'wall'), ('rug', 1, 'before'), ('bench', 2, 'wall'), ('urn', 2, 'corner'),
               ('candle', 2, 'on_table')],
    'hall': [('rug', 1, 'runner'), ('bench', 1, 'wall'), ('urn', 2, 'corner')],
    # caves, mines and camps: people sleep rough here; ruins: what's left lying about
    'camp': [('bedroll', 2, 'wall'), ('fire', 1, 'centre'), ('crate', 2, 'wall'), ('barrel', 2, 'corner'), ('sack', 2, 'wall'),
             ('chest', 1, 'wall'), ('urn', 1, 'corner')],
    'ruin': [('crate', 2, 'wall'), ('barrel', 2, 'corner'), ('urn', 2, 'corner'), ('chest', 1, 'wall'), ('sack', 1, 'wall')],
    'tavern': [('counter', 1, 'wall'), ('table', 2, 'centre'), ('chair', 5, 'by_table'), ('barrel', 3, 'corner'),
               ('bench', 1, 'wall'), ('bottle', 4, 'on_table'), ('dish', 4, 'on_table'), ('food', 2, 'on_table')],
    # the room-kind survey's kinds (roomkindsurvey.py, packaging/nexus/room-kinds-survey.md): these are
    # the hand-written stand-ins until it has run; roomrules.kind_recipe gives the game's own rates
    'bath': [('bath', 1, 'wall'), ('screen', 1, 'centre'), ('chair', 1, 'wall'), ('bench', 1, 'wall'), ('shelf', 1, 'wall'),
             ('planter', 1, 'wall'), ('dish', 2, 'on_table')],
    'corridor': [('chair', 1, 'wall'), ('shelf', 1, 'wall')],
    'entry': [('bench', 1, 'wall'), ('lamp', 1, 'wall'), ('planter', 1, 'corner'), ('rug', 1, 'runner'), ('basket', 1, 'wall')],
    'landing': [('barrel', 1, 'wall'), ('urn', 1, 'corner'), ('chair', 1, 'corner')],
    'barracks': [('bed', 3, 'wall'), ('chest', 3, 'by_bed'), ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('shelf', 1, 'wall'),
                 ('dish', 2, 'on_table'), ('candle', 1, 'on_table')],
    'armoury': [('rack', 3, 'wall'), ('chest', 2, 'wall'), ('crate', 2, 'wall'), ('barrel', 1, 'corner'), ('table', 1, 'wall'),
                ('shelf', 1, 'wall')],
    'training': [('target', 2, 'centre'), ('rack', 2, 'wall'), ('crate', 2, 'wall'), ('barrel', 1, 'corner'), ('bench', 1, 'wall')],
    'mess': [('table', 1, 'centre'), ('bench', 2, 'by_table'), ('chair', 2, 'by_table'), ('shelf', 1, 'wall'), ('chest', 1, 'wall'),
             ('dish', 4, 'on_table'), ('bottle', 2, 'on_table'), ('food', 2, 'on_table'), ('candle', 1, 'on_table')],
    'guardroom': [('bench', 1, 'wall'), ('chair', 1, 'corner'), ('chest', 1, 'corner'), ('barrel', 1, 'corner')],
    # the user's screenshot catalogue, rule R2: one long table (two of the game's long tables end to end, as
    # Vinicius Manor's), chairs down both long sides, one big rug under it, by the hearth, the plate
    # dresser and the wine rack on the walls, the table laid with plates and goblets
    'dining': [('fire', 1, 'wall'), ('table', 1, 'long'), ('rug', 1, 'under_table'), ('chair', 6, 'both_sides'),
               ('cupboard', 1, 'wall'), ('winerack', 1, 'wall'), ('dish', 4, 'on_table'), ('bottle', 2, 'on_table'),
               ('food', 2, 'on_table'), ('candle', 1, 'on_table')],
}
# (the words first in the list win: "weapon store" is an armoury before "store" is storage, "barracks"
# a barracks before "bar" is a tavern)
PURPOSE_WORDS = {'dining': 'dining', 'refectory': 'mess',
                 'barracks': 'barracks', 'bunk': 'barracks', 'dormitory': 'barracks', 'sleeping quarters': 'barracks',
                 'armoury': 'armoury', 'armory': 'armoury', 'arms room': 'armoury', 'weapon store': 'armoury',
                 'training': 'training', 'practice': 'training', 'drill': 'training', 'sparring': 'training',
                 'mess': 'mess', 'canteen': 'mess', 'refectory': 'mess',
                 'guard': 'guardroom', 'watch room': 'guardroom', 'gatehouse': 'guardroom',
                 'bath': 'bath', 'washroom': 'bath', 'privy': 'bath', 'lavatory': 'bath',
                 'bed': 'bedroom', 'sleep': 'bedroom', 'kitchen': 'kitchen', 'cook': 'kitchen', 'pantry': 'kitchen',
                 'store': 'storage', 'cellar': 'storage', 'storage': 'storage', 'study': 'study', 'library': 'study',
                 'office': 'study', 'shop': 'shop', 'store front': 'shop', 'trader': 'shop', 'shrine': 'shrine',
                 'chapel': 'shrine', 'temple': 'shrine', 'hall': 'hall', 'corridor': 'hall', 'tavern': 'tavern',
                 'inn': 'tavern', 'club': 'tavern', 'bar': 'tavern', 'living': 'living', 'main': 'living',
                 'common': 'living', 'parlor': 'living', 'parlour': 'living',
                 'camp': 'camp', 'cave': 'camp', 'mine': 'camp', 'den': 'camp', 'ruin': 'ruin', 'vault': 'ruin'}


def purpose_for(name, tiles, w, h):
    low = (name or '').lower()
    for word, p in PURPOSE_WORDS.items():
        if word in low:
            return p
    if min(w, h) == 1:
        return 'hall'
    if tiles <= 4:
        return 'bedroom'
    return 'living'


# ------------------------------------------------------------------ rooms
FLOOR_T = 128            # the grid traced floors are cut into
_geo = {}


def _turned(rx, ry, rz):
    """The game's rotation of an object as a matrix (turned by -x, -y, -z in Z-Y-X order, like the 3D view)."""
    a, b, c = -rx, -ry, -rz
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    X = ((1, 0, 0), (0, ca, -sa), (0, sa, ca))
    Y = ((cb, 0, sb), (0, 1, 0), (-sb, 0, cb))
    Z = ((cc, -sc, 0), (sc, cc, 0), (0, 0, 1))
    mul = lambda A, B: tuple(tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(X, mul(Y, Z))        # (the game's order: about Z first, then Y, then X; see shelfsurvey._turned)


def _floor_tiles(db, m, G=32):
    """The walkable floor of a place, traced from its own walls and floors: level surfaces are floor,
    steep ones at head height are walls. Cut into tiles of FLOOR_T, with a wall on each side where the
    floor ends or a step is too high. Same shape as the tiles of a kit-built place, or None."""
    T = FLOOR_T
    floor, walls = {}, {}
    for r in m['refs']:
        if not r.get('arch') or r['type'] != 'STAT':
            continue
        key = r['id'].lower()
        if key not in _geo:
            ri = db.resolve_id(r['id'])
            _geo[key] = kits._model(db, ri) if ri is not None else None
        shapes = _geo[key]
        if not shapes:
            continue
        s = r['s'] or 1.0
        px, py, pz, rx, ry, rz = r['p']
        R = _turned(rx, ry, rz)
        for sh in shapes:
            p, idx = sh['p'], sh['i']
            V = []
            for k in range(0, len(p) - 2, 3):
                x, y, z = p[k] * s, p[k + 1] * s, p[k + 2] * s
                V.append((px + R[0][0] * x + R[0][1] * y + R[0][2] * z, py + R[1][0] * x + R[1][1] * y + R[1][2] * z,
                          pz + R[2][0] * x + R[2][1] * y + R[2][2] * z))
            for t in range(0, len(idx) - 2, 3):
                A, B, C = V[idx[t]], V[idx[t + 1]], V[idx[t + 2]]
                ux, uy, uz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
                vx, vy, vz = C[0] - A[0], C[1] - A[1], C[2] - A[2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                area = math.sqrt(nx * nx + ny * ny + nz * nz)
                if area < 1:
                    continue
                if abs(nz) / area > 0.8:
                    # level: floor at every grid point inside it (the lowest one, if there are several)
                    i0, i1 = int(math.floor(min(A[0], B[0], C[0]) / G)), int(math.ceil(max(A[0], B[0], C[0]) / G))
                    j0, j1 = int(math.floor(min(A[1], B[1], C[1]) / G)), int(math.ceil(max(A[1], B[1], C[1]) / G))
                    if (i1 - i0) * (j1 - j0) > 40000:
                        continue
                    d = ux * vy - uy * vx
                    if abs(d) < 1e-6:
                        continue
                    for i in range(i0, i1 + 1):
                        for j in range(j0, j1 + 1):
                            qx, qy = (i + 0.5) * G - A[0], (j + 0.5) * G - A[1]
                            l1, l2 = (qx * vy - qy * vx) / d, (ux * qy - uy * qx) / d
                            if l1 < 0 or l2 < 0 or l1 + l2 > 1:
                                continue
                            zz = A[2] + l1 * uz + l2 * vz
                            if (i, j) not in floor or zz < floor[(i, j)]:
                                floor[(i, j)] = zz
                elif abs(nz) / area < 0.5:
                    # steep: a wall in each grid square along it, from its bottom to its top
                    zlo, zhi = min(A[2], B[2], C[2]), max(A[2], B[2], C[2])
                    pts = (A, B, C)
                    L = max(math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]) for a, b in ((0, 1), (1, 2), (0, 2)))
                    n = max(1, int(L / (G / 2)))
                    for a, b in ((0, 1), (1, 2), (0, 2)):
                        for k in range(n + 1):
                            x = pts[a][0] + (pts[b][0] - pts[a][0]) * k / n
                            y = pts[a][1] + (pts[b][1] - pts[a][1]) * k / n
                            walls.setdefault((int(math.floor(x / G)), int(math.floor(y / G))), []).append((zlo, zhi))
    if not floor:
        return None
    # standing room: nothing solid from knee to head height above the floor
    ok = {c: z for c, z in floor.items() if not any(lo < z + 150 and hi > z + 35 for lo, hi in walls.get(c, ()))}
    n = T // G
    tiles = {}
    for (i, j) in {(c[0] // n, c[1] // n) for c in ok}:
        zs = [ok[(i * n + a, j * n + b)] for a in range(n) for b in range(n) if (i * n + a, j * n + b) in ok]
        if len(zs) < n * n * 0.7:
            continue
        zs.sort()
        tiles[(i, j)] = zs[len(zs) // 2]
    out = {}
    for (i, j), z in tiles.items():
        pat = {'cover': {}, 'offset': {}}
        for s, (dx, dy) in STEP.items():
            o = tiles.get((i + dx, j + dy))
            pat[s] = 'open' if o is not None and abs(o - z) < 40 else 'wall'
            pat['offset'][s] = T / 2 - 4
            pat['cover'][s] = 0.0
        x, y = (i + 0.5) * T, (j + 0.5) * T
        out[(x, y, round(z / 64))] = {'pat': pat, 'x': x, 'y': y, 'floor': z}
    return out or None


def _overlap_area(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _is_floor_piece(db, rid):
    """A kit's floor tile, wall, door frame or stairs (the building itself), not something standing in it."""
    prefix = kits.kit_prefix(rid)
    kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
    low = rid.lower()
    if kp and any(p['id'].lower() == low for p in kp['pieces'] + kp['jambs'] + kp['walls']):
        return True
    return any(w in low for w in ('wall', 'floor', 'ceiling', 'stair', 'ramp', 'jamb', 'door', 'room', 'hall', 'corner',
                                  'side', 'center', 'centre', 'entry', 'end', 'cap', 'shell', 'cave', 'arch'))


def rooms(db, cell_key, names=None, trace=True):
    """The rooms of a place, from its kit floor pieces: [{id, name, purpose, tiles, x_min, ...}].
    trace: whether a place not laid in kit tiles (a cave, a yurt, a Redoran manor) has its floor traced
    from its meshes instead (_floor_tiles: most of a second), False for none, or a function of the
    place's refs that says; the surveys that only read kit-tiled places pass False and go ten times
    as fast."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('Auto-furnish works in interiors.')
    tiles = {}
    T = None
    for r in m['refs']:
        prefix = kits.kit_prefix(r['id'])
        kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
        if not kp:
            continue
        piece = next((p for p in kp['pieces'] if p['id'].lower() == r['id'].lower()), None)
        if not piece or abs((r['s'] or 1) - 1) > 0.05:
            continue
        T = T or kp['tile']
        if kp['tile'] != T:
            continue
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        pat = kits.rotate(piece['pattern'], q)
        floor = r['p'][2] + piece['zmin']
        tiles[(r['p'][0], r['p'][1], round(floor / 64))] = {'pat': pat, 'x': r['p'][0], 'y': r['p'][1], 'floor': floor}
    # places not (only) built from tiles: yurts, caves, Dwemer halls, Velothi's ready-made rooms
    premade = any(r.get('arch') and r.get('b') and (r['b'][3] - r['b'][0]) * (r['b'][4] - r['b'][1]) * (r['s'] or 1) ** 2 > 2.5 * 256 * 256
                  and not (kits.kit_prefix(r['id']) and any(p['id'].lower() == r['id'].lower() for p in
                           (kits.kit_pieces(db, kits.kit_prefix(r['id'])) or {}).get('pieces', [])))
                  for r in m['refs'])
    if not tiles or premade:
        if trace is not True and not (trace and trace(m['refs'])):
            return {'tile': None, 'rooms': [], 'refs': m['refs']}
        traced = _floor_tiles(db, m)
        if traced:
            tiles, T = traced, FLOOR_T
    if not tiles:
        return {'tile': None, 'rooms': [], 'refs': m['refs']}
    # a place made with "Build from pieces" remembers its rooms
    plan = (db.project.cells.get(cell_key) or {}).get('plan') if db.project else None
    if plan and plan.get('rooms'):
        result = []
        for n, pr in enumerate(plan['rooms']):
            # tiles are [x, y] or, in buildings with more than one floor, [x, y, floor height]
            g = [k for k in tiles if any(abs(k[0] - pt[0]) < 24 and abs(k[1] - pt[1]) < 24 and
                                         (len(pt) < 3 or abs(tiles[k]['floor'] - pt[2]) < 64) for pt in pr['tiles'])]
            if not g:
                continue
            xs = [tiles[k]['x'] for k in g]
            ys = [tiles[k]['y'] for k in g]
            w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
            result.append({'id': n, 'name': pr['name'], 'tiles': len(g), 'w': w, 'h': h,
                           'purpose': purpose_for(pr['name'], len(g), w, h),
                           'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2,
                           'y_max': max(ys) + T / 2, 'floor': min(tiles[k]['floor'] for k in g),
                           '_tiles': [tiles[k] for k in g]})
        return {'tile': T, 'rooms': result, 'refs': m['refs']}
    # otherwise: tiles side by side and open towards each other make one room, unless a door frame
    # stands between them
    frames = [(r['p'][0], r['p'][1]) for r in m['refs'] if 'jamb' in r['id'].lower() or r['type'] == 'DOOR']

    def framed(a, b):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        return any(abs(fx - mx) < 40 and abs(fy - my) < 40 for fx, fy in frames)

    near = {}
    for kk in tiles:
        near.setdefault((round(kk[0] / 32), round(kk[1] / 32), kk[2]), []).append(kk)

    def nb(k, s):
        x, y, lv = k
        tx, ty = x + STEP[s][0] * T, y + STEP[s][1] * T
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for kk in near.get((round(tx / 32) + dx, round(ty / 32) + dy, lv), ()):
                    if abs(kk[0] - tx) < 24 and abs(kk[1] - ty) < 24:
                        return kk
        return None
    seen, out = set(), []
    for k in sorted(tiles):
        if k in seen:
            continue
        group, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            group.append(c)
            for s in STEP:
                n = nb(c, s)
                if n and n not in seen and tiles[c]['pat'][s] == 'open' and tiles[n]['pat'][OPP[s]] == 'open' \
                        and not framed(c, n):
                    seen.add(n)
                    todo.append(n)
        out.append(group)
    out.sort(key=lambda g: (-len(g), g[0]))
    result = []
    for n, g in enumerate(out):
        xs = [tiles[k]['x'] for k in g]
        ys = [tiles[k]['y'] for k in g]
        w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
        name = (names or {}).get(n) or 'Room %d' % (n + 1)
        result.append({'id': n, 'name': name, 'tiles': len(g), 'w': w, 'h': h,
                       'purpose': purpose_for(name, len(g), w, h),
                       'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2, 'y_max': max(ys) + T / 2,
                       'floor': min(tiles[k]['floor'] for k in g), '_tiles': [tiles[k] for k in g]})
    return {'tile': T, 'rooms': result, 'refs': m['refs']}


# ------------------------------------------------------------------ which way things face
_facing = {}


_mesh_index = {}


def mesh_siblings(db, rid):
    """The other records (statics, activators, containers, doors) with the very same mesh as this one,
    the ones the game uses most first: the game's activator bookshelf and its furniture twin, the
    user's hidden door made from a bookcase. What the game taught about one holds for the others (the
    dressings, which way it faces, how high it hangs), since the mesh is what stands in the room."""
    if _mesh_index.get('recs') is not db.recs:
        idx = {}
        for ri, r in enumerate(db.recs):
            if r[0] in ('STAT', 'ACTI', 'CONT', 'DOOR') and r[5] and ri not in db.dead:
                idx.setdefault(r[5].lower().replace('/', '\\'), []).append(ri)
        _mesh_index.clear()
        _mesh_index.update({'recs': db.recs, 'idx': idx})
    ri = db.resolve_id(rid)
    if ri is None:
        return []
    m = (db.recs[ri][5] or '').lower().replace('/', '\\')
    if not m:
        return []
    out = [db.recs[j][1] for j in _mesh_index['idx'].get(m, []) if j != ri and db.recs[j][1].lower() != rid.lower()]
    out.sort(key=lambda i: -kits.game_uses(db, i.lower()))
    return out


def taught_twin(db, rid):
    """A record of the same mesh the game stands somewhere, for one it stands nowhere (an activator
    bookshelf, a mod's own copy): its id, or None."""
    if kits.game_uses(db, rid.lower()):
        return None
    for sib in mesh_siblings(db, rid):
        if kits.game_uses(db, sib.lower()):
            return sib
    return None


def front_of(db, rid):
    """The direction an object's front points in its own coordinates, learnt from real interiors
    (furniture faces into the room). (x, y) unit vector, or None if it can't be told."""
    low = rid.lower()
    if low in _facing:
        return _facing[low]
    import modelcache
    kept = modelcache.get(db, 'front', low)
    if kept is not None:
        _facing[low] = tuple(kept) if kept else None
        return _facing[low]
    twin = taught_twin(db, rid)
    if twin:
        _facing[low] = front_of(db, twin)      # (the same mesh under another id: what the game taught of it)
        return _facing[low]
    sx = sy = 0.0
    n = 0
    for ci in list(db.used_in.get(low, ()))[:14]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not kits.game_made(db, r[7]):
            continue
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
            _hdr, crefs = split_cell(data)
        except Exception:
            continue
        pts, mine = [], []
        for cr in crefs:
            cid, pos, _s, dele = ref_info(cr['subs'])
            if dele:
                continue
            pts.append(pos)
            if cid.lower() == low:
                mine.append(pos)
        for pos in mine[:4]:
            near = [p for p in pts if 30 < math.hypot(p[0] - pos[0], p[1] - pos[1]) < 700 and abs(p[2] - pos[2]) < 300]
            if len(near) < 4:
                continue
            cx = sum(p[0] for p in near) / len(near) - pos[0]
            cy = sum(p[1] for p in near) / len(near) - pos[1]
            d = math.hypot(cx, cy)
            if d < 1:
                continue
            th = pos[5]
            # into the object's own frame (the game turns things clockwise)
            lx, ly = (cx * math.cos(th) - cy * math.sin(th)) / d, (cx * math.sin(th) + cy * math.cos(th)) / d
            sx += lx
            sy += ly
            n += 1
    out = None
    if n >= 2:
        sx, sy = sx / n, sy / n
        if max(abs(sx), abs(sy)) > 0.25:
            out = (1.0 if sx > 0 else -1.0, 0.0) if abs(sx) > abs(sy) else (0.0, 1.0 if sy > 0 else -1.0)
    _facing[low] = out
    modelcache.put(db, 'front', low, list(out) if out else [])
    return out


_heights = {}


def hang_height(db, rid):
    """How far above the floor an object's bottom usually is in real interiors (wall shelves,
    sconces, banners hang; most things stand on the floor). 0 for things that stand."""
    low = rid.lower()
    if low in _heights:
        return _heights[low]
    import modelcache
    kept = modelcache.get(db, 'hang', low)
    if kept is not None:
        _heights[low] = kept[0]
        if kept[1] is not None:
            _mount[low] = kept[1]
        return kept[0]
    twin = taught_twin(db, rid)
    if twin:
        _heights[low] = hang_height(db, twin)  # (the same mesh under another id)
        if twin.lower() in _mount:
            _mount[low] = _mount[twin.lower()]
        return _heights[low]
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    out = 0.0
    if b:
        bounds_of = {}

        def bnd(cid):
            k = cid.lower()
            if k not in bounds_of:
                cri = db.resolve_id(cid)
                bounds_of[k] = (mapdata.object_bounds(db, cri), db.recs[cri][0]) if cri is not None else (None, '')
            return bounds_of[k]
        found = []
        for ci in list(db.used_in.get(low, ()))[:10]:
            r = db.recs[ci]
            if r[0] != 'CELL' or not kits.game_made(db, r[7]):
                continue
            try:
                _t, _f, data = db.files[r[3]].record_at(r[4])
                _hdr, crefs = split_cell(data)
            except Exception:
                continue
            all_refs = []
            for cr in crefs:
                cid, pos, sc, dele = ref_info(cr['subs'])
                if not dele:
                    all_refs.append((cid, pos, sc or 1.0))
            for cid, pos, sc in all_refs:
                if cid.lower() != low or len(found) >= 12:
                    continue
                bottom = pos[2] + b[2] * sc
                # the floor under it: the top of the room pieces (architecture) right below it
                floors = []
                resting = False
                for oid, op, osc in all_refs:
                    if abs(op[0] - pos[0]) > 200 or abs(op[1] - pos[1]) > 200:
                        continue
                    ob, otag = bnd(oid)
                    if not ob:
                        continue
                    if not mapdata.is_architecture(otag, oid, ob):
                        # standing on a crate, a barrel or a table here, not hanging on the wall
                        if op is not pos and abs(op[0] - pos[0]) < 60 and abs(op[1] - pos[1]) < 60 and \
                                abs(op[2] + ob[5] * osc - bottom) < 8:
                            resting = True
                        continue
                    fz = op[2] + ob[2] * osc
                    if fz <= bottom + 4 and bottom - fz < 400:
                        floors.append(fz)
                if floors and not resting:
                    found.append(bottom - max(floors))
        if len(found) >= 2:
            found.sort()
            med = found[len(found) // 2]
            _mount[low] = med             # (for things on walls that reach nearly to the floor)
            if med > 40:                  # it hangs: remember how high
                out = med
    _heights[low] = out
    modelcache.put(db, 'hang', low, [out, _mount.get(low)])
    return out


_mount = {}


def mount_height(db, rid):
    """How far above the floor the bottom of an object usually is, even when that is only a little
    (a long tapestry); None if the game doesn't use it in enough places to tell."""
    hang_height(db, rid)
    return _mount.get(rid.lower())


def _turn_to_face(front, direction):
    """Turn (radians, multiple of 90 degrees) so the local front points along the world direction."""
    f = front or (0.0, -1.0)
    best, bd = 0.0, -9
    for q in range(4):
        th = q * math.pi / 2
        wx, wy = f[0] * math.cos(th) + f[1] * math.sin(th), -f[0] * math.sin(th) + f[1] * math.cos(th)
        d = wx * direction[0] + wy * direction[1]
        if d > bd:
            best, bd = th, d
    return best


def _footprint(b, rot, x, y):
    """Axis-aligned box (x0, y0, x1, y1) of a model turned by a multiple of 90 degrees at (x, y)."""
    corners = [(b[0], b[1]), (b[3], b[1]), (b[0], b[4]), (b[3], b[4])]
    c, s = math.cos(rot), math.sin(rot)
    pts = [(x + px * c + py * s, y - px * s + py * c) for px, py in corners]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _overlaps(a, b, pad=4):
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


def room_rects(room, T):
    """The room's floor as the walls bound it: each tile's rectangle, cut back to the wall's measured face
    on its wall sides (kept on the room under '_rects'). Every path that stands a thing on the floor
    checks its box against these with on_floor(), so nothing cuts into a wall or reaches across the
    mouth of a one-tile nook into the wall beside it (the user's "chair standing inside the wall", the
    lamp and the stone block "with its back half clipped into the wall")."""
    if room.get('_rects') is not None:
        return room['_rects']
    rects = []
    for t in room['_tiles']:
        r_ = [t['x'] - T / 2, t['y'] - T / 2, t['x'] + T / 2, t['y'] + T / 2]
        for s, (dx, dy) in STEP.items():
            if t['pat'][s] != 'wall':
                continue
            face = (t['x'] if s in ('E', 'W') else t['y']) + (dx + dy) * t['pat']['offset'].get(s, T / 2 - 16)
            if s == 'E':
                r_[2] = min(r_[2], face + 2)
            elif s == 'W':
                r_[0] = max(r_[0], face - 2)
            elif s == 'N':
                r_[3] = min(r_[3], face + 2)
            else:
                r_[1] = max(r_[1], face - 2)
        rects.append(tuple(r_))
    room['_rects'] = rects
    return rects


def wall_behind(b, rot, x, y, room, T, front, scale=1.0, reach=14):
    """Is there a wall (the room's edge as the walls bound it) right behind this thing's back along
    its whole width: the two ends and the middle of its back edge, `reach` units behind it, all off
    the room's floor (room_rects). front: the model's own front (front_of), (0, -1) when unknown."""
    rects = room_rects(room, T)
    fr = front or (0.0, -1.0)
    c, s = math.cos(rot), math.sin(rot)
    fx, fy = fr[0] * c + fr[1] * s, -fr[0] * s + fr[1] * c
    bx, by = -fx, -fy
    box = _footprint([v * scale for v in b], rot, x, y)
    # the back edge: the box's side the back direction points to
    if abs(bx) > abs(by):
        ex = box[2] if bx > 0 else box[0]
        pts = ((ex + bx * reach, box[1] + 4), (ex + bx * reach, box[3] - 4), (ex + bx * reach, (box[1] + box[3]) / 2))
    else:
        ey = box[3] if by > 0 else box[1]
        pts = ((box[0] + 4, ey + by * reach), (box[2] - 4, ey + by * reach), ((box[0] + box[2]) / 2, ey + by * reach))
    for px, py in pts:
        if any(r_[0] - 1 <= px <= r_[2] + 1 and r_[1] - 1 <= py <= r_[3] + 1 for r_ in rects):
            return False                        # (floor behind it: nothing to hang on)
    return True


def on_floor(box, rects, inner=None):
    """Is the box wholly on the room's floor as the walls bound it (room_rects): every corner and
    mid-edge on some tile's rectangle, and inside `inner` when given."""
    if inner is not None and not (box[0] >= inner[0] and box[1] >= inner[1] and box[2] <= inner[2] and box[3] <= inner[3]):
        return False
    pts = ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3]),
           ((box[0] + box[2]) / 2, box[1]), ((box[0] + box[2]) / 2, box[3]), (box[0], (box[1] + box[3]) / 2), (box[2], (box[1] + box[3]) / 2))
    for px, py in pts:
        if not any(r_[0] - 1 <= px <= r_[2] + 1 and r_[1] - 1 <= py <= r_[3] + 1 for r_ in rects):
            return False
    return True


# ------------------------------------------------------------------ choosing things
CORE_KINDS = ('bed', 'table', 'chair', 'bench', 'chest', 'cupboard', 'shelf')
_related = {}


def related_cells(db, culture, limit=40):
    """Interiors built from pieces of the same culture (e.g. every Dunmer house kit), most built-up first."""
    key = (culture, limit)
    if _related.get('recs') is not db.recs:
        _related.clear()
        _related['recs'] = db.recs
    if key in _related:
        return _related[key]
    counts = {}
    for oid, cells in db.used_in.items():
        if not kits.kit_prefix(oid):
            continue                                  # only building pieces say what a place is
        label = mapdata.style_of(oid)
        if not label or STYLE_SET.get(label, 'imperial') != culture:
            continue
        for ci in cells:
            r = db.recs[ci]
            if r is not None and r[0] == 'CELL' and not r[7].startswith('#') and ci not in db.dead:
                counts[r[7]] = counts.get(r[7], 0) + 1
    out = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:limit])
    _related[key] = out
    return out


def _named(low, words):
    """Is one of these words in the name? Short words only as a word of their own ("urn", not the
    "urn" in "furn_de_rope"; "bed", not "bedroll"), longer ones anywhere ("chair" in "armchair")."""
    tokens = None
    for w in words:
        w = w.strip('_')
        if not w:
            return True
        if len(w) > 3:
            if w in low:
                return True
            continue
        if tokens is None:
            tokens = re.split(r'[^a-z0-9]+', low)
        if any(t == w or re.fullmatch(w + r'\d*[a-z]?', t) for t in tokens):
            return True
    return False


def _sort_into(fam, groups):
    for g in groups:
        for it in g['items']:
            low = (it['id'] + ' ' + (it['name'] or '')).lower()
            for k, (words, types) in FAMILIES.items():
                if it['type'] not in types:
                    continue
                if not _named(low, words):
                    continue
                if any(w in low for w in NOT.get(k, ())):
                    continue
                if 'marker' in low or 'unique' in low or BARE_STONE.search(it['id'].lower()):
                    continue
                if it['id'] not in fam[k]:
                    fam[k].append(it['id'])
                break


def candidates(db, cell_key):
    """Things used in places like this one, sorted into kinds of furniture (most used first).
    When few places are built from the same pieces (a style only a mod or two uses), it also
    learns from other places of the same culture: other Dunmer houses for a Dres one, and plain
    common furniture for a style with no relatives."""
    pal = mapdata.palette(db, cell_key, limit=80)
    fam = {k: [] for k in FAMILIES}
    _sort_into(fam, pal.get('groups', []))
    style = pal.get('style', '')
    have = sum(1 for k in CORE_KINDS if fam[k])
    # (or when the place's own palette, the 80 most used things in places like it, has no bed, table
    # or chair at all: a Hlaalu house's beds come after its clutter in use, and the bedrooms of a
    # Hlaalu house went without a bed unless a set piece brought one)
    if pal.get('similar', 0) < 8 or have < 4 or any(not fam[k] for k in CORE_KINDS):
        culture = STYLE_SET.get(style, 'imperial')
        cells = {k: v for k, v in related_cells(db, culture).items() if k != cell_key}
        if cells:
            # (after this place's own things; a long list, so rarer pieces like beds make it in)
            _sort_into(fam, mapdata.palette_from(db, cells, limit=400))
        fam['_borrowed'] = culture
    return fam, style


_hearths = {}


def hearth_models(db, culture, pits=False):
    """The free-standing hearths the game's places of this culture use (a fireplace, a firepit, a stove;
    never a kit's hearth wall, which is the building), most used first. The palette seldom has one (the
    game's kit kitchens have a free-standing one in one room in twelve: the Common sets' hearths are in
    their wall pieces), so a kitchen asks here for its hearth."""
    key = (culture, id(db.recs))
    if key in _hearths:
        return _hearths[key]
    words, types = FAMILIES['fire']
    found = []
    for (tag, k), lst in db.by_key.items():
        if tag not in types or not lst or lst[-1] in db.dead:
            continue
        if not _named(k, words) or any(w in k for w in NOT['fire']):
            continue
        if not k.startswith(DECOR_SETS.get(culture, ())) and not k.startswith(('furn_', 'light_')):
            continue
        if not pits and 'pit' in k:
            continue                  # (a firepit is a camp's or a yurt's: a house kitchen takes a fireplace or a stove, or none)
        n = kits.game_uses(db, k)
        if n < 3:
            continue
        b = mapdata.object_bounds(db, lst[-1])
        if not b or max(b[3] - b[0], b[4] - b[1]) > 260 or (b[5] - b[2]) > 400:
            continue
        # (the culture's own set first: a Dunmer firepit in a Dunmer house, the Common fireplace elsewhere)
        own = k.startswith(DECOR_SETS.get(culture, ()))
        found.append((0 if own else 1, -n, db.recs[lst[-1]][1]))
    found.sort()
    _hearths[key] = [f[2] for f in found[:6]]
    return _hearths[key]


DECOR_WORDS = ('tapestry', 'banner', 'painting', 'picture', 'portrait', 'sconce', 'weaponrack', 'weapon_rack', 'rack',
               'trophy', 'plaque', 'map', 'mask', 'shield', 'flag', 'herbs', 'hanging', 'wall')
NOT_DECOR = ('door', 'window', 'marker', 'unique', 'gate', 'light_de_lantern', 'chandelier', 'rug', 'carpet', 'curtain',
             'rope', 'web', 'ivy', 'flora', 'railing', 'rail_', 'pole', 'post', 'burial', 'shutter', 'chain', 'beam',
             'pillar', 'column', 'stair', 'ladder', 'cage', 'bone', 'skull', 'blood', 'cobweb', 'moss', 'screen')
# which pieces suit which kind of place, by the start of their IDs
DECOR_SETS = {'dunmer': ('furn_de_', 't_de_', 'light_de_', 'furn_banner', 'furn_tapestry'),
              'imperial': ('furn_com_', 'furn_imp', 't_imp_', 't_com_', 'light_com_', 'furn_c_'),
              'nordic': ('furn_nord', 't_nor_', 't_sky_', 'furn_com_', 'light_com_')}
STYLE_SET = {'Hlaalu': 'dunmer', 'Redoran': 'dunmer', 'Telvanni': 'dunmer', 'Velothi': 'dunmer', 'Dunmer': 'dunmer',
             'Daedric': 'dunmer', 'Common': 'imperial', 'Imperial': 'imperial', 'Breton': 'imperial', 'Cyrodiilic': 'imperial',
             'Nordic': 'nordic', 'Skyrim': 'nordic', 'Ashlander': 'dunmer', 'Redguard': 'imperial',
             'High Elf': 'imperial', 'Stronghold': 'imperial', 'Mournhold': 'dunmer', 'Indoril': 'dunmer', 'Dres': 'dunmer',
             'Dwemer': 'dunmer', 'Cave': 'dunmer', 'Reach': 'nordic'}
CULTURE_NAMES = {'dunmer': 'other Dunmer places', 'imperial': 'common and Imperial places', 'nordic': 'other Nordic places'}
_decor_global = {}


def wall_decor(db, cell_key):
    """Things that hang on the walls in places like this one (tapestries, banners, paintings, wall
    shelves, sconces, racks), learnt from where the game itself puts them: well up off the floor,
    and flat against a wall. [(id, how high it hangs, kind)] most used first."""
    pal = mapdata.palette(db, cell_key, limit=120)
    out, seen = [], set()
    items = [it for g in pal.get('groups', []) for it in g['items']]
    # and the game's own tapestries, banners, paintings and sconces of the same make, used anywhere
    dset = DECOR_SETS.get(STYLE_SET.get(pal.get('style', ''), ''), ())
    if dset:
        key = (dset, id(db.recs))
        if key not in _decor_global:
            found = []
            for (tag, k), lst in db.by_key.items():
                if tag not in ('STAT', 'LIGH') or not k.startswith(dset) or not any(w in k for w in ('tapestry', 'banner', 'painting', 'sconce')):
                    continue
                if not lst or lst[-1] in db.dead:
                    continue
                n = len(db.used_in.get(k, ()))
                if n >= 3:
                    found.append((n, {'id': db.recs[lst[-1]][1], 'name': db.recs[lst[-1]][2], 'type': tag}))
            found.sort(key=lambda x: -x[0])
            _decor_global[key] = [f[1] for f in found[:40]]
        items += _decor_global[key]
    for it in items:
        if True:
            rid, low = it['id'], (it['id'] + ' ' + (it.get('name') or '')).lower()
            if rid.lower() in seen or it['type'] not in ('STAT', 'ACTI', 'LIGH', 'MISC'):
                continue
            seen.add(rid.lower())
            if any(w in low for w in NOT_DECOR):
                continue
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            if not b:
                continue
            w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
            thin, wide = min(w, d), max(w, d)
            named = any(w_ in low for w_ in DECOR_WORDS)
            flat = thin <= (44 if named else 32) and wide >= 40 and h >= 30     # (a tapestry's rod adds depth)
            if it['type'] == 'LIGH' and 'sconce' not in low and 'wall' not in low:
                continue                       # free-standing candles and lamps are not wall things
            if not (flat or named) or wide > 420 or h > 400:
                continue
            hang = hang_height(db, rid)
            if hang < 50:
                # a long tapestry or banner can reach nearly to the floor: still a wall thing if it's flat
                m = mount_height(db, rid)
                if not (named and flat and m is not None and m >= 0):
                    continue                   # the game keeps it on the floor or a table
                hang = max(4.0, m)
            kind = next((k for k in ('tapestry', 'banner', 'painting', 'sconce', 'rack', 'shelf', 'trophy', 'herbs')
                         if k in low), 'light' if it['type'] == 'LIGH' else 'decor')
            out.append((rid, hang, kind))
    return out


DECOR_PER_PURPOSE = {'storage': 0.15, 'kitchen': 0.25, 'hall': 0.3, 'camp': 0.1, 'corridor': 0.3, 'entry': 0.3, 'landing': 0.3,
                     'bath': 0.3, 'armoury': 0.2, 'training': 0.2}       # share of free wall spots used (default 0.4)
DECOR_KINDS = {'shrine': ('banner', 'tapestry', 'sconce'), 'storage': ('rack', 'herbs', 'decor', 'sconce'),
               'kitchen': ('herbs', 'decor', 'sconce', 'tapestry'), 'camp': ('herbs', 'sconce', 'light')}
SURVEY_KIND = {'hall': 'empty', 'corridor': 'empty', 'entry': 'empty', 'landing': 'empty', 'bath': 'living', 'barracks': 'bedroom', 'dining': 'living',
               'mess': 'living', 'guardroom': 'living', 'armoury': 'storage', 'training': 'storage'}      # Auto-furnish's room purposes in wallsurvey2's words (its halls are rooms with no furniture)


def bath_models(db, culture):
    """The tubs and basins the game's places of this culture bathe in (room-kind survey R1): Imperial and
    Gold Coast houses the marble basins and baths, every other culture the half-barrel tub, Hlaalu its own
    basin too; only ids that exist here."""
    imp = ('t_imp_furnr_basin_02', 't_imp_furnr_basin_02_w', 't_imp_furnr_basin_01', 't_imp_furnr_basin_03', 't_imp_furnr_bath_01',
           't_imp_furnr_bath_02', 't_imp_furn_bath_01_cloth')
    de = ('t_com_furn_bathhalfbarrel_01', 't_com_furn_bathhalfbarrel_02', 't_de_furn_basin_01')
    ids = imp + de if culture == 'imperial' else de + imp
    return [i for i in ids if db.resolve_id(i) is not None]


def front_doors(room, refs, T, all_rooms=None):
    """The doors on this room's edge that lead out of the building: a door whose other side is outdoors
    (its destination is no interior cell), or, in a house built from pieces whose doors lead nowhere yet,
    a door with no room's floor beyond it. [(door ref, direction into the room)]."""
    fl = room['floor']
    out = []
    tiles = [tl for rm in (all_rooms or [room]) for tl in rm['_tiles'] if abs(rm['floor'] - fl) < 100]
    for d in refs:
        if d['type'] != 'DOOR':
            continue
        if not (room['x_min'] - 40 <= d['p'][0] <= room['x_max'] + 40 and room['y_min'] - 40 <= d['p'][1] <= room['y_max'] + 40 and fl - 60 <= d['p'][2] <= fl + 200):
            continue
        cx, cy = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
        vx, vy = cx - d['p'][0], cy - d['p'][1]
        inward = ((1.0 if vx > 0 else -1.0), 0.0) if abs(vx) >= abs(vy) else (0.0, (1.0 if vy > 0 else -1.0))
        to = d.get('to')
        if to and to.get('cell'):
            continue                      # (leads to another interior: not the way out)
        if not to:
            # (leads nowhere: the way out only when no floor lies beyond it)
            bx, by = d['p'][0] - inward[0] * T * 0.7, d['p'][1] - inward[1] * T * 0.7
            if any(abs(bx - tl['x']) <= T / 2 and abs(by - tl['y']) <= T / 2 for tl in tiles):
                continue
        out.append((d, inward))
    return out


def hall_kind(room, refs, T, all_rooms=None):
    """Which kind of hall a hall is (room-kind survey R2): a 'corridor' (one tile wide, three or more
    long), an 'entry' (the room with the front door, up to six tiles), else a 'landing'."""
    if min(room['w'], room['h']) == 1 and max(room['w'], room['h']) >= 3:
        return 'corridor'
    if room['tiles'] <= 6 and front_doors(room, refs, T, all_rooms):
        return 'entry'
    return 'landing'


def house_hangings(db, decor, rng):
    """The wall things for one house: the game's own houses keep to a couple of kinds of tapestry or
    banner (half of them use one or two), so the house gets two, picked from the most used, and up to two
    of each other kind (racks, herbs...). Also, as wallsurvey.py found: a hanger or banner post that is
    almost never without its banner isn't hung on its own (a banner goes up with what it hangs from)."""
    import wallsurvey
    decor = [d for d in decor if wallsurvey.hangs_alone(db, d[0]) or wallsurvey.partner(db, d[0])]
    # (and no torn hangings from ruins and dungeons in a lived-in place; nothing is hung in a ruin)
    decor = [d for d in decor if not re.search(r'dngruin|_ruin|ruins_|dng_|dngcryp|crypt', d[0].lower())]
    out, count = [], {}
    cloth = [d for d in decor if d[2] in ('tapestry', 'banner', 'painting')]
    top = cloth[:4]
    rng.shuffle(top)
    keep = {d[0] for d in top[:2]}
    for d in decor:
        if d[2] in ('tapestry', 'banner', 'painting'):
            if d[0] in keep:
                out.append(d)
        elif count.get(d[2], 0) < 2:
            count[d[2]] = count.get(d[2], 0) + 1
            out.append(d)
    return out


def _decorate(db, room, purpose, T, decor, refs, placed, put, rng, hung, hang_k=1.0):
    """Hang things on the free walls of one room: flat against the wall, facing in, at the height the
    game hangs them, never over a doorway or into furniture that stands that high. hung: what hangs in
    the house so far, [(x, y, floor, direction it faces)]. hang_k: the game's count, times this (a poor
    house's bare walls, a rich one's hung ones: wealthsurvey.py)."""
    if not decor:
        return []
    import wallsurvey
    floor = room['floor']
    # what already stands here, with its height (so a tapestry can hang above a low chest, not a shelf)
    solid = []
    import roomsurvey
    _tall = {}
    for r in list(refs) + list(placed):
        b = r.get('b')
        if not b or r.get('arch') or r['type'] in ('NPC_', 'CREA'):
            continue
        s = r.get('s') or 1.0
        # (a counter, a shelf, a cupboard, a bookshelf, a bed or a shrine standing flush to the wall: the
        # wall stretch its end butts against takes no hanging unless the hanging clears its top. The user's
        # tapestry at the side wall, with the counter's end merged into it)
        key = (r['id'].lower(), r['type'])
        if key not in _tall:
            _tall[key] = roomsurvey.family_of(db, r['id'], r['type']) in ('counter', 'shelf', 'cupboard', 'bookshelf', 'bed', 'shrine')
        solid.append((_footprint([v * s for v in b], r['p'][5], r['p'][0], r['p'][1]), r['p'][2] + b[2] * s, r['p'][2] + b[5] * s,
                      r['type'] == 'DOOR', _tall[key]))
    # the room's walls as the game sees them (wallsurvey2.py): unbroken runs of wall between corners and
    # doorways. The game hangs things at the middle of a wall tile (four in five), one to a tile along a
    # long wall, on a one-tile wall half the time, and on the wall either side of a doorway in the door's
    # own tile (a quarter of all hangings), often as a matching pair
    import roomsurvey
    import wallsurvey2
    rule = wallsurvey2.hang_rule(db, SURVEY_KIND.get(purpose, purpose)) if purpose not in ('camp', 'ruin') else None
    lines = wallsurvey2._lines(room, T)
    # what stands against each run (its origin at the wall): the game leaves the wall over a bed, a
    # cupboard, a counter or a shrine bare more often than a free wall
    against = {}
    fams = {}
    for r in list(refs) + list(placed):
        if not r.get('b') or r.get('arch') or r['type'] in ('NPC_', 'CREA', 'DOOR', 'LIGH'):
            continue
        if not (room['x_min'] <= r['p'][0] <= room['x_max'] and room['y_min'] <= r['p'][1] <= room['y_max'] and abs(r['p'][2] - floor) < 100):
            continue
        key = (r['id'].lower(), r['type'])
        if key not in fams:
            fams[key] = roomsurvey.family_of(db, r['id'], r['type'])
        fam = fams[key]
        if fam not in ('bed', 'bookshelf', 'shelf', 'cupboard', 'table', 'chest', 'counter', 'shrine', 'bench'):
            continue
        for (s, lc), L in lines.items():
            nd = abs((r['p'][1] if s in ('N', 'S') else r['p'][0]) - L['off'])
            if nd < 100:
                against.setdefault((s, lc), []).append((r['p'][0] if s in ('N', 'S') else r['p'][1], fam))
    spots = []
    wall_tiles = 0
    # (the wall either side of a doorway, in the door's own tile: one hanging in seven in the game's
    # halls, about 92 units off the doorway's middle; seldom in a furnished room)
    door_off = (rule or {}).get('door_off') or 92
    door_rank = T * 0.75 if (rule or {}).get('door_share', 0) >= 0.1 else T * 1.5     # (after a wall's middle tiles)
    for (s, lc), L in lines.items():
        runs, _dws = wallsurvey2._runs(L, T)
        face = L['off'] - 3 * (1 if s in ('N', 'E') else -1)       # the wall's inside face, a hair off it
        inward = (-STEP[s][0], -STEP[s][1])

        def at(along, **kw):
            x, y = (along, face) if s in ('N', 'S') else (face, along)
            sp = {'x': x, 'y': y, 'in': inward, 'line': (s, lc), 'avoid': set()}
            sp.update(kw)
            return sp
        for run in runs:
            mid = (run[0] + run[1]) / 2
            n_tiles = int(round((run[1] - run[0]) / T))
            wall_tiles += n_tiles
            here = against.get((s, lc), [])
            for a_, kind in sorted(L['along'].items()):
                if kind != 'wall' or not (run[0] <= a_ <= run[1]):
                    continue
                sp = at(a_, run=run, rank=abs(a_ - mid), mirror=2 * mid - a_, n=n_tiles)
                sp['avoid'] = {f for a2, f in here if abs(a2 - a_) < T * 0.75}
                spots.append(sp)
        for a_, kind in L['along'].items():
            if kind == 'door':
                for side in (-1, 1):
                    spots.append(at(a_ + side * door_off, run=('door', a_), rank=door_rank, mirror=a_ - side * door_off, n=1, door=True))
    if not spots:
        return []
    rng.shuffle(spots)
    spots.sort(key=lambda sp: (sp['rank'], -sp['n']))               # a wall's middle first, longer walls first
    # not two things on top of each other, or round a corner from each other (back to back on the two
    # sides of one wall is fine; side by side on the next tile is how the game hangs them)
    gap = T * 0.9

    def crowded(sp):
        for hx, hy, hf, hin in hung:
            if abs(hf - floor) > 100 or math.hypot(hx - sp['x'], hy - sp['y']) > gap:
                continue
            if hin == (-sp['in'][0], -sp['in'][1]) and (abs(hx - sp['x']) < 40 if hin[0] == 0 else abs(hy - sp['y']) < 40):
                continue
            return True
        return False
    spots = [sp for sp in spots if not crowded(sp)]
    # how many: the game's rate per tile of wall for rooms of this kind (a bedroom three or four, a study
    # four, a living room two, a hall one); until the survey has run, about one for every four floor
    # tiles, fewer in stores and kitchens
    area = room['tiles'] * (T / 256.0) ** 2
    if rule:
        want_f = rule['per_wall_tile'] * wall_tiles * (T / 256.0) * hang_k
        want = int(want_f) + (1 if rng.random() < want_f - int(want_f) else 0)
        if want == 0 and rng.random() < rule['rooms_with'] * hang_k:
            want = 1
        want = min(want, rule.get('p90') or 6, 8)       # (never more than nine in ten of the game's rooms have)
        avoid = dict(rule['avoid'])
    else:
        want_f = area * 0.25 * DECOR_PER_PURPOSE.get(purpose, 0.4) / 0.4 * hang_k
        want = max(0 if hang_k < 1 else 1, min(3, int(want_f) + (1 if rng.random() < want_f - int(want_f) else 0)))
        avoid = {'bed': 0.4, 'cupboard': 0.5, 'counter': 0.6, 'shrine': 0.7}
    kinds = DECOR_KINDS.get(purpose)
    pool = [d for d in decor if not kinds or d[2] in kinds] or decor
    lights = [d for d in pool if d[2] in ('sconce', 'light')]
    others = [d for d in pool if d[2] not in ('sconce', 'light')]
    # one kind of hanging for the room, repeated (as in the game's own rooms: half of those with more
    # than one keep to one model, the rest mostly to two)
    plan = []
    if others and want:
        main = rng.choice(others[:2])
        second = None
        if len(others) > 1 and rng.random() > (rule['repeat'] if rule else 0.5):
            second = rng.choice([d for d in others[:4] if d is not main])
        plan += [main if (second is None or i % 2 == 0) else second for i in range(want)]
    # sconces as often as the game's rooms of the kind have them (a hall one time in nine, a living room
    # one in fourteen; next to never in a Dunmer house, whose palette has none), one or two when they come
    if lights:
        lr = wallsurvey2.light_rule(db, SURVEY_KIND.get(purpose, purpose)) if purpose not in ('camp', 'ruin') else None
        if lr:
            p_sc = lr['rooms_with'].get('sconce', 0)
            n_sc = max(1, int(round(lr['per_room_when'].get('sconce', 1))))
            if rng.random() < p_sc:
                plan += [lights[0]] * min(2, n_sc)
        else:
            plan += [lights[0]] * min(2, max(1, want // 3))
    got = []
    force = None                       # (the matching spot of a pair, to take the same model next)
    while plan:
        # (a pair's second half takes the same model as its first, out of turn)
        i = next((n for n, d in enumerate(plan) if d[0] == force.get('for')), 0) if force is not None else 0
        rid, hang, kind = plan.pop(i)
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        front = front_of(db, rid)
        z0, z1 = floor + hang, floor + hang + (b[5] - b[2])
        # (a flat thing, a tapestry or a painting, hangs behind a bench, a table or a chest the way the
        # game's do: a bench under a tapestry is its favourite picture. Not behind a bookshelf or a
        # cupboard, which stand as high as it hangs)
        flat = min(b[3] - b[0], b[4] - b[1]) <= 44 and kind in ('tapestry', 'banner', 'painting')
        order = list(spots)
        if force is not None and force in order and force.get('for') == rid:
            order.remove(force)
            order.insert(0, force)
        force = None
        for sp in order:
            if sp['avoid'] and rng.random() < max([avoid.get(f, 0) for f in sp['avoid']] + [0]):
                continue               # (the wall over a bed or a cupboard: bare more often than a free wall)
            rot = _turn_to_face(front, sp['in'])
            box0 = _footprint(b, rot, 0, 0)
            back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sp['in']]
            x, y = sp['x'] + sp['in'][0] * (back + 1), sp['y'] + sp['in'][1] * (back + 1)
            box = _footprint(b, rot, x, y)
            # clear of doors (any height) and of whatever stands as high as it hangs, with a little room around
            pad = (box[0] - 24, box[1] - 24, box[2] + 24, box[3] + 24)
            if any(_overlaps(pad if door else box, fb, 0) and (door or (zb < z1 + 4 and zt > z0 - 4 and (not flat or zt > floor + 110 or tall)))
                   for fb, zb, zt, door, tall in solid):
                continue
            # (beside a doorway: the thing must fit between the opening and the tile's edge)
            if sp.get('door') and max(box0[2] - box0[0], box0[3] - box0[1]) > 2 * (door_off - 56):
                continue
            rec = put(rid, x, y, rot, hang_from=z0, room=room['name'])
            if rec is None:
                break
            solid.append((box, z0, z1, False, False))
            # what it hangs from, where the game puts it (a hanger above a banner, a banner post...)
            pt = wallsurvey.partner(db, rid)
            if pt and wallsurvey.HANGY.search(pt['id']):
                pri = db.resolve_id(pt['id'])
                pb = mapdata.object_bounds(db, pri) if pri is not None else None
                if pb:
                    lx, ly, dz = pt['offset']
                    c_, s_ = math.cos(rot), math.sin(rot)
                    px, py = x + lx * c_ + ly * s_, y - lx * s_ + ly * c_
                    put(pt['id'], px, py, (rot + pt['dq'] * math.pi / 2) % (2 * math.pi), hang_from=rec['p'][2] + dz + pb[2],
                        room=room['name'])
            spots.remove(sp)
            hung.append((sp['x'], sp['y'], floor, sp['in']))
            spots[:] = [o for o in spots if not crowded(o)]
            got.append(rid)
            # its match: the spot mirrored about the doorway or the wall's middle takes the same model
            # next (two of a kind flanking a door, or set either side of a wall's middle)
            if abs(sp['mirror'] - (sp['x'] if sp['line'][0] in ('N', 'S') else sp['y'])) > 20:
                m = next((o for o in spots if o['line'] == sp['line'] and o['run'] == sp['run']
                          and abs((o['x'] if o['line'][0] in ('N', 'S') else o['y']) - sp['mirror']) < 20), None)
                if m is not None:
                    m['for'] = rid
                    force = m
            break
    return got


placed_last = []                 # (the last furnish's records, with 'via': the path that laid each; for the lab)


def placed_before(db, cell_key):
    """The keys of the things Auto-furnish put in this place earlier (they carry a mark), still there."""
    c = (db.project.cells or {}).get(cell_key) if db.project else None
    if not c:
        return []
    return [k for k, r in c['refs'].items() if r.get('by') == 'furnish' and not r.get('deleted')]


PIECE_KINDS = DRESSED_KINDS + ('planter', 'fire', 'shrine', 'cupboard', 'chest', 'crate', 'barrel', 'bench', 'rack')


def piece_info(db, cell_key, ref):
    """Can this placed piece be dressed the game's way (one of the game's own dressings of its model), and
    does it carry one already: {'dressable', 'dressed', 'model', 'kind', 'dressings_known'}."""
    import roomsurvey
    c = (db.project.cells or {}).get(cell_key) if db.project else None
    m = mapdata.cellmap(db, cell_key)
    r = next((x for x in m.get('refs', []) if x.get('k') == ref), None)
    if r is None:
        return {'dressable': False, 'dressed': False, 'model': None, 'kind': None, 'dressings_known': 0}
    rid, tag = r['id'], r['type']
    fam_ = roomsurvey.family_of(db, rid, tag)
    n = 0
    rng = random.Random(0)
    if fam_ == 'planter':
        import arrangesurvey
        n = 1 if arrangesurvey.plant_for(db, rid, rng) else 0
    elif fam_ == 'fire':
        n = 1 if roomsurvey.hearth_dressing(db, rid, rng, None) else 0
    elif fam_ == 'shrine':
        import shrinesurvey
        rule_ = shrinesurvey.rule(db, rid)
        n = len(rule_['examples']) if rule_ else 0
    elif tag in ('STAT', 'ACTI', 'CONT', 'DOOR'):
        # (an activator or a hidden door with a furniture model's mesh takes the model's dressings: shelfsurvey)
        import shelfsurvey
        n = len(shelfsurvey.survey(db, rid)['dressings'])
    dressed = bool(c) and any(v.get('on') == ref and not v.get('deleted') for v in c['refs'].values())
    return {'dressable': n > 0, 'dressed': dressed, 'model': rid, 'kind': fam_, 'dressings_known': n}


def room_at(db, cell_key, at):
    """The room of this place that holds the point (x, y, z): (info, room) or (info, None)."""
    info = rooms(db, cell_key)
    T = info['tile'] or 256
    x, y, z = at[0], at[1], (at[2] if len(at) > 2 and at[2] is not None else None)
    best = None
    for rm in info['rooms']:
        if not any(abs(x - tl['x']) <= T / 2 and abs(y - tl['y']) <= T / 2 for tl in rm['_tiles']):
            continue
        if z is not None and not (rm['floor'] - 60 <= z <= rm['floor'] + 300):
            continue
        if best is None or (z is not None and abs(rm['floor'] - z) < abs(best['floor'] - z)):
            best = rm
    return info, best


def room_refs(db, cell_key, room, T):
    """The keys of what Auto-furnish laid in this room: tagged with the room when laid, else, for things
    laid by an earlier version, by where they stand (on the room's tiles, on its floor or on the
    furniture up to the storey: what rides on a table inside the room goes with it)."""
    c = (db.project.cells or {}).get(cell_key) if db.project else None
    if not c:
        return []
    m = mapdata.cellmap(db, cell_key)
    out = []
    for r in m.get('refs', []):
        v = c['refs'].get(r.get('k'))
        if not v or v.get('by') != 'furnish' or v.get('deleted'):
            continue
        if v.get('room') is not None:
            if v['room'] == room['id']:
                out.append(r['k'])
            continue
        if any(abs(r['p'][0] - tl['x']) <= T / 2 and abs(r['p'][1] - tl['y']) <= T / 2 for tl in room['_tiles']) \
                and room['floor'] - 60 <= r['p'][2] <= room['floor'] + 300:
            out.append(r['k'])
    return out


def room_info(db, cell_key, at=None, room=None):
    """Which room is here and what it holds: {'room': id, 'name', 'purpose', 'furnished': things Auto-furnish
    laid in it, 'purposes': the kinds it could be furnished as}; room None when the point is in no room."""
    if room is not None:
        info = rooms(db, cell_key)
        rm = next((r for r in info['rooms'] if r['id'] == room), None)
    else:
        info, rm = room_at(db, cell_key, at or (0, 0, None))
    if rm is None:
        return {'room': None, 'name': None, 'purpose': None, 'furnished': 0, 'purposes': list(RECIPES)}
    return {'room': rm['id'], 'name': rm['name'], 'purpose': rm['purpose'], 'tiles': rm['tiles'],
            'furnished': len(room_refs(db, cell_key, rm, info['tile'] or 256)), 'purposes': list(RECIPES)}


def furnish(db, cell_key, plan=None, seed=None, walls=True, walls_only=False, replace=False, level=None, like=None, piece=None,
            room=None, purpose=None, add=False):
    """Fill rooms with furniture. plan: [{'id': room id, 'purpose': ...}] (all rooms, by their
    guessed purpose, if None). Everything goes in as one change. Returns what was placed. replace:
    first take out what Auto-furnish put here before (else the rooms are furnished on top of it).
    level: how well off the household is (wealthsurvey.py): 'poor', 'modest', 'comfortable' (today's
    way, the same as None), 'rich', 'exquisite', 'trade:<a class, faction or trade>' (the band such
    people live in, with the set piece their homes have: a smith's forge), or {'band': 'worthless',
    'max_value': N} (nothing worth more than N gold anywhere, containers included).
    like: the cell key of one of the game's places (an exemplary one from the taste set, taste.py) to
    furnish like: its rooms are the model for what each kind of room holds, how full it is and which
    scenes it is composed of; the game's rooms fill in what it lacks.
    piece: the key of one placed thing here: only that piece is dressed, the way the game dresses its
    model (a bookshelf's books, a table's dishes, a counter's wares, a planter's plant, a hearth's pots,
    a shrine's statue), as one change tagged with the piece's key; with replace, what an earlier call
    laid on it comes off first (a fresh draw). Returns {placed, removed, model, dressings_known}.
    room: one room's id (rooms()): only that room is furnished, as the kind `purpose` says when given
    (else its own), everything it holds tagged with the room; with replace, what Auto-furnish laid in that
    room before comes out first and nothing in the other rooms is touched. Returns {placed, removed,
    room, name, purpose}. The user: "We need this feature for Rooms"."""
    editing._require_project(db)
    room_rec = None
    if room is not None:
        info0 = rooms(db, cell_key)
        room_rec = next((r for r in info0['rooms'] if r['id'] == room), None)
        if room_rec is None:
            raise EditError('No such room here any more.')
        if purpose and purpose not in RECIPES and purpose != 'none':
            raise EditError('"%s" is not a kind of room Auto-furnish knows.' % purpose)
        plan = [{'id': room, 'purpose': purpose or room_rec['purpose']}]
    import wealthsurvey
    L = wealthsurvey.level(db, level)
    wealthsurvey.ready(db)                   # (the wealth survey runs in the background the first time, for later)
    like_rooms = like_scenes = None
    if like:
        import roomsurvey as _rs
        import arrangesurvey as _as
        if not kits.game_made(db, like):
            raise EditError('"Furnish like" takes one of the game\'s own places as the model, not one of your mod\'s.')
        like_rooms = _rs.one(db, like)
        like_scenes = _as.one(db, like)
        if not like_rooms['cells']:
            raise EditError('That place has no rooms Auto-furnish can read (it is not built from room pieces).')
    removed = 0
    if replace:
        c0 = db.project.cells.get(cell_key)
        if room_rec is not None:
            keep_out = set(room_refs(db, cell_key, room_rec, info0['tile'] or 256))     # (one room: only what stands in it)
        for k in placed_before(db, cell_key):
            if piece is not None and c0['refs'][k].get('on') != piece:
                continue                     # (one piece: only what was laid on it before comes off)
            if room_rec is not None and k not in keep_out:
                continue
            c0['refs'].pop(k, None)
            removed += 1
        db.sync_project()
    info = rooms(db, cell_key)
    if not info['rooms']:
        raise EditError('No rooms found here. Auto-furnish works in places built from modular room pieces '
                        '(like the ones "Build from pieces" makes, and most town interiors).')
    T = info['tile']
    rooms_by_name = {r['name']: r['id'] for r in info['rooms']}     # (put() tags each thing with its room)
    fam, style = candidates(db, cell_key)
    if L:
        # the band's makes of furniture first (the poor Dunmer set for a poor house, the rich one for a
        # rich house; the palette's order within a make is kept, so the place's own pieces still lead)
        for k in list(fam):
            if k in FAMILIES and fam[k]:
                fam[k] = wealthsurvey.order_by_tier(fam[k], L['tiers'], L.get('keep', 1))
    extras_left = list(L['extras']) if L else []      # the trade's set pieces still to lay (once a house)
    if not fam.get('fire'):
        fam['fire'] = hearth_models(db, STYLE_SET.get(style, 'imperial'), pits=style in ('Ashlander', 'Cave', 'Mine'))     # (a kitchen's hearth; none in a Hlaalu house: "a log fire in the middle of the floor")
    # (the room-kind survey's pieces the palettes seldom hold: a bathing room's tub, an armoury's rack, a
    # training room's dummy)
    if not fam.get('bath'):
        fam['bath'] = bath_models(db, STYLE_SET.get(style, 'imperial'))
    if not fam.get('rack'):
        fam['rack'] = [i for i in ('furn_uni_weaponrack_01', 'furn_de_weaponrack_01', 't_com_furn_weaponrack_01') if db.resolve_id(i) is not None]
    if not fam.get('target'):
        fam['target'] = [i for i in ('furn_practice_dummy', 'furn_archery_target', 't_com_furn_practicedummy_01') if db.resolve_id(i) is not None]
    if not fam.get('shrine'):
        # (a shrine room in a house whose palette has no shrine: the game's own house shrines of the culture)
        import shrinesurvey
        import roomsurvey as _rs0
        fam['shrine'] = shrinesurvey.house_models(db, _rs0.theme_of((mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key),
                                                  STYLE_SET.get(style, 'imperial'))[:6]
    cont_pool = wealthsurvey.containers_of(db, L['band']) if L else None
    # caves, camps and ruins aren't homes: rough sleeping and stores there, unless a room was named
    ROUGH = {'Cave': 'camp', 'Ashlander': 'camp', 'Mine': 'camp', 'Dwemer': 'ruin', 'Daedric': 'ruin', 'Ruin': 'ruin'}
    rough = ROUGH.get(style)
    if not rough:
        # the walls say it better than the furniture: a yurt full of Dunmer things is still a tent
        shell = {}
        for r in mapdata.cellmap(db, cell_key).get('refs', []):
            low = r['id'].lower()
            if low.startswith(('in_', 'ex_')) or kits.kit_prefix(low):
                st = mapdata.style_of(low)
                if st:
                    shell[st] = shell.get(st, 0) + 1
        if shell:
            top = max(shell, key=shell.get)
            rough = ROUGH.get(top)
    if rough:
        for rm in info['rooms']:
            if re.match(r'^room \d+$', (rm['name'] or '').lower()) or not rm['name']:
                rm['purpose'] = rough
    rng = random.Random(seed if seed is not None else cell_key)
    decor = house_hangings(db, wall_decor(db, cell_key), rng) if (walls or walls_only) else []
    # the kind of place its name says it is (a tavern, a shop, a temple): what the game keeps in the
    # containers there goes by it
    import roomsurvey
    theme = roomsurvey.theme_of((mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key)
    theme0 = theme                           # (the containers go by the place's own name: a smith's house gets no vendor's stock chest)
    if L and L.get('theme') and theme == 'house':
        theme = L['theme']                   # (a smith's house is dressed like a shop, a priest's like a temple)
    # the building kit the place is made of (its light models are the style's: wallsurvey2.style_lights)
    _styles = Counter(kits.kit_prefix(r['id']) for r in info['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
    cell_style = _styles.most_common(1)[0][0] if _styles else ''
    # the kit's storey: nothing taller than the room is laid in it (the user's saint shrine "clipping the
    # ceilings" of a Common stone cellar; the beams hang about 20 below the storey's top)
    _kp = kits.kit_pieces(db, cell_style) if cell_style and cell_style in kits.kits(db) else None
    storey_h = (_kp or {}).get('height') or None
    room_top = (storey_h - 20) if storey_h else None
    wanted = {p['id']: p.get('purpose') for p in (plan or [])}
    # everything already standing here takes up room: (box, bottom, top), so that a room only minds
    # what stands on its own floor, not the furniture of the room above or below it
    refs = info['refs']
    taken = []

    def span(r):
        b, s = r.get('b'), r.get('s') or 1.0
        return (r['p'][2] + b[2] * s, r['p'][2] + b[5] * s) if b else (r['p'][2] - 20, r['p'][2] + 200)
    for r in refs:
        if r.get('b') and not r.get('arch') and r['type'] not in ('LIGH',):
            taken.append((_footprint([v * (r['s'] or 1.0) for v in r['b']], r['p'][5], r['p'][0], r['p'][1]),) + span(r) + (False,))
        elif r.get('b') and r.get('arch') and info['tile'] != FLOOR_T and (r['b'][5] - r['b'][2]) * (r['s'] or 1) > 30 \
                and not _is_floor_piece(db, r['id']):
            # (traced floors already leave out what stands in the way; rugs are flat)
            # big things standing in a room that aren't its floor and walls: a tree, a pillar, a statue
            s = r['s'] or 1.0
            fp = _footprint([v * s for v in r['b']], r['p'][5], r['p'][0], r['p'][1])
            # (one that covers most of a room is the building itself, like a hut's shell)
            area = (fp[2] - fp[0]) * (fp[3] - fp[1])
            shell = any(_overlap_area(fp, (rm['x_min'], rm['y_min'], rm['x_max'], rm['y_max'])) >
                        0.4 * (rm['x_max'] - rm['x_min']) * (rm['y_max'] - rm['y_min']) for rm in info['rooms'])
            if area < 700 * 700 and not shell:
                taken.append((fp,) + span(r) + (False,))
    # keep doorways clear: doors and door frames, with room to walk through on both sides (a door's
    # own point is often at its hinge, so the clear space reaches well past it), and room sides that
    # open into other rooms
    clear = max(150, (info['tile'] or 256) * 0.6)
    openings = []
    for r in refs:
        low = r['id'].lower()
        if r['type'] == 'DOOR' or 'jamb' in low or 'doorway' in low:
            zb, zt = span(r)
            taken.append(((r['p'][0] - clear, r['p'][1] - clear, r['p'][0] + clear, r['p'][1] + clear), zb, zt, True))
            openings.append(r)
        # and the landings at both ends of a staircase
        if r['type'] == 'STAT' and ('stair' in low or 'ramp' in low) and info['tile']:
            T = info['tile']
            along_x = abs(math.sin(r['p'][5])) < 0.5          # which way the stairs run, before turning
            prefix = kits.kit_prefix(r['id'])
            si = kits.stairs(db, prefix) if prefix and prefix in kits.kits(db) else None
            sp = next((p for p in si['pieces'] if p['id'].lower() == low), None) if si else None
            if sp:
                along_x = (sp['low'] in 'EW') == along_x
            ax, ay = (T * 1.5, T * 0.5) if along_x else (T * 0.5, T * 1.5)
            zb, zt = span(r)
            taken.append(((r['p'][0] - ax, r['p'][1] - ay, r['p'][0] + ax, r['p'][1] + ay), zb - 40, zt + 40, True))
    T = info['tile']
    surf = [dict(r) for r in refs]           # for finding floor and table heights as things are added
    placed = []
    # the rugs here (box, floor height): rugs don't lie next to or over each other
    rugs = [(_footprint([v * (r['s'] or 1.0) for v in r['b']], r['p'][5], r['p'][0], r['p'][1]), r['p'][2])
            for r in refs if r.get('b') and _named(r['id'].lower(), FAMILIES['rug'][0])]
    # and what already hangs on the walls (on the floor of the room it's in)
    levels = sorted(set(rm['floor'] for rm in info['rooms']))
    hung = [(r['p'][0], r['p'][1], max([f for f in levels if f <= r['p'][2] + 10], default=r['p'][2]), (0, 0))
            for r in refs if re.search(r'tapestr|banner|painting', r['id'].lower())]
    c, _r = editing._cell(db, cell_key)
    mine = db.project.plugin.lower()
    global last_placed, last_clutter, last_arrangements, last_trace
    last_placed = placed                     # (for tests: what went where)
    last_trace = []
    last_clutter = []
    last_arrangements = []                   # (for tests: the game's set pieces laid, per room)

    rack_pending = []                        # wine racks put down in the room, to be stocked when the room is done
    _scene = []                              # the building's geometry, for looking straight down (built once, when first needed)

    def floor_by_mesh(x, y, fl):
        """The height of the building's surface straight under (x, y) from a little above this floor, by
        the real geometry of the pieces (not their boxes), or None when there is nothing below."""
        if not _scene:
            import seethrough
            _scene.append(seethrough.place_scene(db, {'refs': [r for r in surf if r.get('arch') and r.get('ri') is not None]}))
        hit = _scene[0].nearest((x, y, fl + 150), (0.0, 0.0, -1.0), 900)
        return None if hit is None else fl + 150 - hit[0]

    def put(rid, x, y, rot, on_top=False, hang_from=None, floor=None, flat=False, room=None, at_z=None, tilt=(0, 0), scale=1.0, ledge=None):
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri)
        if not b:
            return None
        tag = db.recs[ri][0]
        if tag in ('STAT', 'ACTI') and theme != 'temple' and BARE_STONE.search(rid.lower()):
            return None                      # (a bare stone block, slab or pedestal: never furniture in a house, by any path)
        if L and L['cap'] is not None and tag in mapdata.ITEM_TYPES:
            import shelfsurvey
            if shelfsurvey.value_of(db, rid)[1] > L['cap']:
                return None                      # (a band was chosen: nothing dearer than its cap anywhere)
        if L and L['cont_max'] is not None and tag == 'CONT':
            if (wealthsurvey.container_value(db, rid) or 0) > L['cont_max']:
                return None                      # (a poor house, or loot kept worthless: no strongbox of gems on a shelf)
        room_ = next((r for r in info['rooms'] if r['name'] == room), None) if room else None
        if at_z is not None:
            z = at_z                             # exactly where a game dressing puts it on its shelf
        elif hang_from is not None:
            z = hang_from - b[2]                 # hung on the wall at its usual height
            # (a hung piece needs a wall right behind its back along its whole width: a wall shelf
            # "hanging in mid-air a little out from a free-standing column, attached to nothing")
            if tag in ('STAT', 'ACTI', 'CONT') and room_ is not None and T and not wall_behind(b, rot, x, y, room_, T, front_of(db, rid), scale, reach=24):
                return None
        else:
            # on this room's own floor (not up on the floor of a room above it), or on a table in it; a
            # rug always on the floor
            under = [r for r in surf if r.get('arch')] if flat else surf
            z = mapdata.surface_z(db, under, True, x, y, b, 1.0, 'MISC' if on_top else tag,
                                  None if floor is None else floor + 64)
            if floor is not None and (z + b[2] < floor - 40 or (z + b[2] > floor + 100 + (ledge or 0) and not on_top)):
                return None                      # no floor under it here (a stairwell): leave it out
                #                                  (or none found and the nearest piece was the floor above)
            if floor is not None and not on_top and (tag not in mapdata.ITEM_TYPES or flat):
                # a thing standing on the floor rests on the floor's real surface, not a piece's box (a
                # chair over a raised step's box floated; the Gold Coast stair piece's box top is not its floor);
                # or up on the style's wall ledge, when the caller settled it there (catalogue rule 4)
                zm = floor_by_mesh(x, y, floor)
                if zm is not None and 24 < abs(zm - floor) <= 60 and not (ledge and 0 < zm - floor <= ledge + 30) and tag not in mapdata.ITEM_TYPES:
                    return None                  # (its middle over a step, a bath's rim: a chair there sits at table height)
                if zm is not None and (abs(zm - floor) <= 60 or (ledge and 0 < zm - floor <= ledge + 30)):
                    z = round(zm - b[2] * scale, 2)
                elif z + b[2] * scale > floor + 10:
                    # (no floor mesh under its middle, or none at this level: on the room's floor, never
                    # on the top of whatever furniture its box reaches over. The user's chairs "raised,
                    # their seats at the table-top height, as if sitting on the table")
                    z = round(floor - b[2] * scale, 2)
        if tag in ('STAT', 'ACTI', 'CONT') and not on_top and at_z is None and hang_from is None and room_ is not None:
            # two rules every path keeps: nothing taller than the room (its turned top over the kit's
            # storey less the beams), and a bookshelf, a cupboard or a standing shelf only with a real
            # wall right behind its back (the user's "awkward bookshelf" out in the middle of a dining
            # room, side-on to the table, and the saint shrine "clipping the ceilings")
            if room_top and z + b[5] * scale > room_['floor'] + room_top:
                last_trace.append((room, 'height', rid, 'taller than the room: %.0f over' % (z + b[5] * scale - room_['floor'] - room_top)))
                return None
            fam_p = roomsurvey.family_of(db, rid, tag)
            if fam_p in ('bookshelf', 'cupboard', 'shelf') and T and not wall_behind(b, rot, x, y, room_, T, front_of(db, rid), scale, reach=30):
                last_trace.append((room, fam_p, rid, 'no wall behind it: left out'))
                return None
        nk = db.project.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                       set_ref_pos([('NAME', zs(rid))], (x, y, z, tilt[0], tilt[1], rot), scale))
        c['refs'][nk]['by'] = 'furnish'          # (so a later Auto-furnish can take it out first)
        if piece is not None:
            c['refs'][nk]['on'] = piece          # (laid on this one piece: "Dress again" takes it off first)
        if room is not None and room in rooms_by_name:
            c['refs'][nk]['room'] = rooms_by_name[room]   # (laid in this room: "Furnish it again" takes the room's out first)
        rec = {'id': rid, 'p': [x, y, z, tilt[0], tilt[1], rot], 's': scale, 'b': b, 'type': tag,
               'arch': False, 'room': room, 'k': nk, 'via': sys._getframe(1).f_code.co_name}   # (via: which path laid it, for the lab)
        surf.append(rec)
        placed.append(rec)
        if WINERACK.search(rid.lower()) and not on_top:
            rack_pending.append(rec)
        return rec

    dressings_used = set()                   # (the game's dressings used in this house: no two shelves alike)

    def dress(rec, purpose):
        """Set a new bookshelf, shelf, table or counter out the way the game dresses that model (see
        shelfsurvey.py): the things of one of its real dressings, at the same spots on the same shelves,
        with books and dishes swapped, the odd end piece changed and now and then something interesting
        (as often as the game's own). None when the game never dresses it."""
        import shelfsurvey
        d = shelfsurvey.dressing(db, rec['id'], purpose, rng, books=fam.get('book') or [], theme=theme, used=dressings_used,
                                 cap=L['cap'] if L else None, rate_k=L['rate'] if L else 1.0, max_value=L['max_value'] if L else None)
        if d is None:
            return None
        if WINERACK.search(rec['id'].lower()):
            # a wine rack holds wine: the tall bottles the game racks (misc_com_bottle_05/08/14, Tamriel
            # Data's wines), never the fat Dunmer liquor flasks or a healing potion that the kind-swap of
            # a dressing brought in (the user: "bottles that fit, the tall thin types")
            pool = [o['id'] for dd in shelfsurvey.survey(db, rec['id'])['dressings'] for o in dd['objects']
                    if TALL_BOTTLE.search(o['id'].lower()) and not FAT_BOTTLE.search(o['id'].lower())]
            if pool:
                d = [dict(o, id=rng.choice(pool)) if (FAT_BOTTLE.search(o['id'].lower()) or not TALL_BOTTLE.search(o['id'].lower())) else o for o in d]
            else:
                d = [o for o in d if not FAT_BOTTLE.search(o['id'].lower())]
        px, py, pz, rz = rec['p'][0], rec['p'][1], rec['p'][2], rec['p'][5]
        room_d = next((r for r in info['rooms'] if r['name'] == rec.get('room')), None)
        # the furniture's own geometry, for checking that each thing rests on it (a gold ingot stood in
        # the air under a wall shelf: the dressing's level was the bracket's, not the board's)
        import seethrough
        own = seethrough.overlay(db, [{'op': 'place', 'id': rec['id'], 'p': list(rec['p']), 's': rec.get('s', 1.0)}])
        kept = []
        for o in d:
            wx, wy = shelfsurvey.to_world(o['x'], o['y'], rz)
            # (the thing's rotation relative to the shelf, put back on this shelf's turn the way the game
            # composes rotations: not simply rz added, which lays tilted books down)
            orx, ory, orz = shelfsurvey.compose_on(o['rx'], o['ry'], o['rz'], rz)
            ob = mapdata.object_bounds(db, db.resolve_id(o['id'])) if db.resolve_id(o['id']) is not None else None
            # (its bottom as it stands, turned: an upright book is modelled lying down and stood up by a
            # quarter turn, so its unturned box put the bottom twenty units too high and the ray under it
            # missed the board; two thirds of a full dressing were thrown away as "floating")
            bottom = pz + o['z'] + (shelfsurvey.box_turned(ob, orx, ory, orz, o['s'])[2] if ob else 0)
            # (not for a wine rack: a bottle lies across two slats of the lattice, nothing straight under its
            # middle, and the game's own racks are where its pose came from)
            hit = own.nearest((px + wx, py + wy, bottom + 8), (0.0, 0.0, -1.0), 40) if own.tris and not WINERACK.search(rec['id'].lower()) else (0, None)
            if hit is None or hit[0] > 8 + 14:
                continue                                 # (nothing of the furniture within reach under it)
            # (and within the room's walls: a ledger lying across a bookshelf's back edge reached into the wall)
            if ob and room_d is not None and T:
                tb_ = shelfsurvey.box_turned(ob, orx, ory, orz, o['s'])
                if not on_floor((px + wx + tb_[0], py + wy + tb_[1], px + wx + tb_[3], py + wy + tb_[4]), room_rects(room_d, T)):
                    continue
            if put(o['id'], px + wx, py + wy, orz, at_z=pz + o['z'], tilt=(orx, ory), scale=o['s'], room=rec.get('room')):
                kept.append(o)
        last_dress.append((rec['id'], rec.get('room'), len(d), len(kept)))
        return kept or None

    def add_one(rec, purpose):
        """One more thing on this piece, keeping all that stands on it (laid by Auto-furnish, by Dress
        this, or by hand: contents.on_piece's geometry): an object the game stands on this model, at one
        of its game positions that is free of what is there (turned boxes), resting on the piece by the
        mesh, inside the room's walls, a kind the piece is short of against the model's median dressing
        first (a thin bookshelf gets a book, a table with no candle a candle), and a book only where the
        shelf-sense rules allow (upright beside a run, never leaning on air, never a lone flat one).
        The user: "this function just adds one piece, which you can repeat until satisfied". Returns
        {'placed': 1, 'added': id, 'name'} or {'placed': 0, 'note': ...}."""
        import contents
        import shelfsurvey
        import seethrough
        s = shelfsurvey.survey(db, rec['id'])
        if not s['dressings']:
            return {'placed': 0, 'note': 'The game never puts anything on this (%s), so there is nothing to add.' % rec['id']}
        px, py, pz, rz = rec['p'][0], rec['p'][1], rec['p'][2], rec['p'][5]
        m_ = mapdata.cellmap(db, cell_key)
        on_keys = set(contents.on_piece(db, cell_key, rec['k'])['on'])
        have = []
        for r_ in m_['refs']:
            if r_.get('k') in on_keys and r_.get('b'):
                tb_ = shelfsurvey.box_turned(r_['b'], r_['p'][3], r_['p'][4], r_['p'][5], r_.get('s') or 1.0)
                have.append((r_, (r_['p'][0] + tb_[0], r_['p'][1] + tb_[1], r_['p'][2] + tb_[2], r_['p'][0] + tb_[3], r_['p'][1] + tb_[4], r_['p'][2] + tb_[5])))
        have_kinds = Counter(r_['type'] for r_, _b in have)
        # what the model usually holds, by kind, against what it holds now
        from collections import defaultdict
        per = defaultdict(list)
        for d in s['dressings']:
            c_ = Counter(o['kind'] for o in d['objects'])
            for k_ in set(c_) | set(per):
                per[k_].append(c_.get(k_, 0))
        med = {k_: sorted(v)[len(v) // 2] for k_, v in per.items()}
        short = {k_: max(0, med[k_] - have_kinds.get(k_, 0)) for k_ in med}
        cands = []
        for d in s['dressings']:
            for o in d['objects']:
                if db.resolve_id(o['id']) is None or not shelfsurvey.plain(db, o['id'], 2):
                    continue
                if shelfsurvey.BOOKEND.search(o['id'].lower()):
                    continue             # (a bookend needs a run of three to join: not one at a time)
                if L and L['cap'] is not None and shelfsurvey.interesting(db, o['id']) and shelfsurvey.value_of(db, o['id'])[1] > L['cap']:
                    continue
                w_ = 1.0 + 3.0 * short.get(o['kind'], 0)
                cands.append((rng.random() ** (1.0 / w_), o))
        cands.sort(key=lambda t: -t[0])
        own = seethrough.overlay(db, [{'op': 'place', 'id': rec['id'], 'p': list(rec['p']), 's': rec.get('s', 1.0)}])
        fb_ = rec['b']
        ax_ = 0 if (fb_[3] - fb_[0]) >= (fb_[4] - fb_[1]) else 1          # (the row runs along the longer side)
        room_d = next((r for r in info['rooms'] if r['name'] == rec.get('room')), None)
        rects_ = room_rects(room_d, T) if room_d is not None and T else None
        bounds_ = {}
        for _w, o in cands[:600]:
            wx, wy = shelfsurvey.to_world(o['x'], o['y'], rz)
            orx, ory, orz = shelfsurvey.compose_on(o['rx'], o['ry'], o['rz'], rz)
            ob, _tag = shelfsurvey._bounds_of(db, bounds_, o['id'])
            if not ob:
                continue
            tb = shelfsurvey.box_turned(ob, orx, ory, orz, o['s'])
            X, Y, Z = px + wx, py + wy, pz + o['z']
            wb = (X + tb[0], Y + tb[1], Z + tb[2], X + tb[3], Y + tb[4], Z + tb[5])
            if any(wb[0] < hb[3] - 2 and hb[0] < wb[3] - 2 and wb[1] < hb[4] - 2 and hb[1] < wb[4] - 2 and wb[2] < hb[5] - 2 and hb[2] < wb[5] - 2 for _r, hb in have):
                continue                 # (something stands there already)
            if rects_ is not None and not on_floor((wb[0], wb[1], wb[3], wb[4]), rects_):
                continue
            hit = own.nearest((X, Y, wb[2] + 8), (0.0, 0.0, -1.0), 40) if own.tris and not WINERACK.search(rec['id'].lower()) else (0, None)
            if hit is None or hit[0] > 8 + 14:
                continue                 # (nothing of the piece under it)
            if o['kind'] == 'BOOK':
                pose, d_ = shelfsurvey.book_pose(db, bounds_, o)
                if pose == 'lean':
                    if abs(d_[ax_]) < 0.15:
                        pass                 # (tipped back against the board: fine)
                    else:
                        side = 1 if d_[ax_] > 0 else -1
                        ux, uy = shelfsurvey.to_world(side if ax_ == 0 else 0, side if ax_ == 1 else 0, rz)
                        axis = 0 if abs(ux) >= abs(uy) else 1
                        sgn = (ux if axis == 0 else uy) > 0
                        edge = wb[3 if axis == 0 else 4] if sgn else wb[0 if axis == 0 else 1]
                        mid_z = (wb[2] + wb[5]) / 2
                        ok_ = any(hb[5] > mid_z and hb[2] < wb[5] and (hb[1] < wb[4] and hb[4] > wb[1] if axis == 0 else hb[0] < wb[3] and hb[3] > wb[0])
                                  and ((sgn and hb[3 if axis == 0 else 4] > edge and hb[0 if axis == 0 else 1] - edge <= 4)
                                       or (not sgn and hb[0 if axis == 0 else 1] < edge and edge - hb[3 if axis == 0 else 4] <= 4)) for _r, hb in have)
                        if not ok_:
                            continue     # (it would lean on air)
                elif pose == 'flat':
                    stacked = any(abs(hb[5] - wb[2]) < 4 and hb[0] - 12 <= X <= hb[3] + 12 and hb[1] - 12 <= Y <= hb[4] + 12 for _r, hb in have)
                    against = any(hb[5] > (wb[2] + wb[5]) / 2 and hb[2] < wb[5] and max(hb[0] - wb[3], wb[0] - hb[3], hb[1] - wb[4], wb[1] - hb[4]) <= 4 for _r, hb in have)
                    if not stacked and not against:
                        continue         # (a lone flat book in a bay)
            r_new = put(o['id'], X, Y, orz, at_z=Z, tilt=(orx, ory), scale=o['s'], room=rec.get('room'), on_top=True)
            if r_new:
                ri_ = db.resolve_id(o['id'])
                return {'placed': 1, 'added': o['id'], 'name': (db.recs[ri_][2] or o['id']) if ri_ is not None else o['id'], 'kind': o['kind']}
        return {'placed': 0, 'note': 'No room left on it: every spot the game uses on this model is taken.'}

    def shrine_ok(rid):
        """May this shrine model be laid: the game stands it somewhere (a model the game never uses is
        an unknown: the user's "blank monoliths"), where the game stands it (a home's shrine in a home,
        the house's own culture's make, never a chapel's altar in a house), under the room's ceiling with
        its statue (a shorter composition when the tallest would reach the beams), and, when the game
        gives it a statue in half its places or more, one of the game's dressings with a statue is to
        hand. (composition or None, allowed)."""
        import shrinesurvey
        r = shrinesurvey.rule(db, rid)
        if shrinesurvey.ready(db) is None:
            return None, True                 # (not surveyed yet: as before)
        if not r:
            return None, False
        if not shrinesurvey.allowed(db, rid, theme, STYLE_SET.get(style) or fam.get('_borrowed')):
            return None, False
        b_ = mapdata.object_bounds(db, db.resolve_id(rid))
        max_top = None
        if room_top and b_:
            max_top = room_top + b_[2]        # (the highest point allowed, over the base's origin)
            if b_[5] > max_top:
                return None, False            # (the base alone reaches the beams)
        comp = shrinesurvey.composition(db, rid, rng, max_top=max_top)
        if r['with_statue'] >= 0.5 and not (comp and comp['statue']):
            return None, False
        return comp, True

    def dress_shrine(rec, comp):
        """The shrine's statue, candles and offerings on its base, at the game's own offsets in the
        base's frame (shrinesurvey.py): the saint or the god on the altar, the candles either side, the
        flowers, coins and food laid before it. A home's low altar table whose game dressing is bare or
        thin gets the user's offering set instead: gems, coins, a cup, a scroll, a book, candles, laid
        on its top by the mesh."""
        import shrinesurvey
        px, py, pz, rz = rec['p'][0], rec['p'][1], rec['p'][2], rec['p'][5]
        c_, s_ = math.cos(rz), math.sin(rz)
        got_ = []
        if comp:
            for row in ([comp['statue']] if comp['statue'] else []) + list(comp['candles']) + list(comp['offer']):
                oid, lx, ly, dz, drz, sc = row[:6]
                if db.resolve_id(oid) is None:
                    continue
                wx, wy = px + lx * c_ + ly * s_, py - lx * s_ + ly * c_
                ob_ = mapdata.object_bounds(db, db.resolve_id(oid))
                if ob_ and row is not comp['statue']:
                    # (a candle or an offering rests on the altar's real top under it, by the mesh: an
                    # example's offset from a bigger altar left a scroll floating 123 over this one)
                    top_ = surface_on(rec, wx, wy)
                    if top_ is None or abs((pz + dz + ob_[2] * sc) - top_) > 30:
                        if top_ is None:
                            continue
                        dz = top_ - ob_[2] * sc - pz
                r_ = put(oid, wx, wy, (rz + drz) % (2 * math.pi), at_z=pz + dz, scale=sc, room=rec.get('room'), on_top=True)
                if r_:
                    got_.append(oid)
        b_ = rec.get('b')
        low_ = bool(b_) and (b_[5] - b_[2]) <= shrinesurvey.LOW_ALTAR
        if low_ and theme != 'temple' and len([g for g in got_ if not re.search(r'candle', g.lower())]) < 2:
            ab = _footprint([v * (rec.get('s') or 1.0) for v in b_], rz, px, py)
            laid_ = []
            for oid in shrinesurvey.offering_set(db, rng, books=(fam.get('book') or [])[:20]):
                ob = mapdata.object_bounds(db, db.resolve_id(oid))
                if not ob:
                    continue
                for _try in range(6):
                    ox_ = rng.uniform(ab[0] + 14, ab[2] - 14)
                    oy_ = rng.uniform(ab[1] + 14, ab[3] - 14)
                    obox = _footprint(ob, 0, ox_, oy_)
                    if any(_overlaps(obox, q, 0) for q in laid_):
                        continue
                    top_ = surface_on(rec, ox_, oy_)
                    if top_ is None or top_ < pz + b_[2] + 20:
                        continue
                    r_ = put(oid, ox_, oy_, rng.uniform(0, 2 * math.pi), at_z=top_ - ob[2], room=rec.get('room'), on_top=True)
                    if r_:
                        got_.append(oid)
                        laid_.append(obox)
                    break
            if laid_:
                last_trace.append((rec.get('room'), 'shrine', rec['id'], 'the offering set on the altar table: %d things' % len(laid_)))
        return got_

    def dress_hearth(rec, purpose):
        """What the game stands at a hearth like this one (roomsurvey.hearth_dressing): a cooking pot
        on the fire, a kettle, firewood, a bucket, a bellows, at the game's own offsets round it; each
        on the floor or the hearth's own surface, clear of what stands in the room already."""
        import roomsurvey
        d = roomsurvey.hearth_dressing(db, rec['id'], rng, purpose)
        if not d:
            return []
        px, py, pz, rz = rec['p'][0], rec['p'][1], rec['p'][2], rec['p'][5]
        fs = rec.get('s') or 1.0
        c_, s_ = math.cos(rz), math.sin(rz)
        got_ = []
        own = _footprint([v * fs for v in rec['b']], rz, px, py)
        for oid, lx, ly, dz, drz, sc, tag in d:
            if db.resolve_id(oid) is None:
                continue
            import shelfsurvey
            if not shelfsurvey.plain(db, oid, 2):
                continue
            wx, wy = px + (lx * c_ + ly * s_) * fs, py + (-lx * s_ + ly * c_) * fs
            ob = mapdata.object_bounds(db, db.resolve_id(oid))
            if not ob:
                continue
            box = _footprint([v * sc for v in ob], (rz + drz) % (2 * math.pi), wx, wy)
            fl_ = rec['p'][2] + rec['b'][2] * fs
            if tag in ('STAT', 'CONT', 'ACTI') and not _overlaps(box, own, 0):
                if any(_overlaps(box, o[0]) for o in taken if o[1] < fl_ + 150 and o[2] > fl_ + 4 and o[0] is not own):
                    continue
                # (and on the room's floor as the walls bound it: a log pile through the wall behind the hearth)
                room_ = next((r for r in info['rooms'] if r['name'] == rec.get('room')), None)
                if room_ is not None and not on_floor(box, room_rects(room_, T)):
                    continue
            up = dz * fs > 24 or _overlaps(box, own, 0)
            r_ = put(oid, wx, wy, (rz + drz) % (2 * math.pi), on_top=up and tag in mapdata.ITEM_TYPES, floor=None if up else fl_,
                     at_z=(pz + dz * fs) if up else None, scale=sc, room=rec.get('room'))
            if r_:
                got_.append(oid)
                if tag in ('STAT', 'CONT', 'ACTI') and not up:
                    taken.append((box, fl_, fl_ + 150, False))
        return got_

    def rug_sizes():
        out = []
        for rid in fam.get('rug') or []:
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            if b:
                out.append((rid, b, max(b[3] - b[0], b[4] - b[1]), min(b[3] - b[0], b[4] - b[1])))
        return out
    all_rugs = rug_sizes()
    mats = [r for r in all_rugs if r[2] <= 200]                 # door mats: the small ones
    big_rugs = [r for r in all_rugs if r[2] > 200] or all_rugs

    def rug_free(box, fl):
        """Not on or right next to another rug (a hand's width apart at least)."""
        return not any(abs(f - fl) < 60 and _overlaps(box, (o[0] - 40, o[1] - 40, o[2] + 40, o[3] + 40), 0) for o, f in rugs)

    report = []
    groups = []                              # the sizes of the clutter groups made
    piece_rec = None
    if piece is not None:
        piece_rec = next((r for r in refs if r.get('k') == piece and r.get('b')), None)
        if piece_rec is None:
            raise EditError('That thing is not here any more.')
    piece_out = None
    for room in info['rooms']:
        purpose = wanted.get(room['id'], room['purpose']) if plan is not None else room['purpose']
        if plan is not None and room['id'] not in wanted and piece is None:
            continue
        if piece is not None:
            # (one piece: only the room it stands in, whatever that room is for)
            pb_ = piece_rec['p'][2] + piece_rec['b'][2] * (piece_rec.get('s') or 1.0)
            if not (room['x_min'] <= piece_rec['p'][0] <= room['x_max'] and room['y_min'] <= piece_rec['p'][1] <= room['y_max']
                    and -60 <= pb_ - room['floor'] < 300):      # (a wall shelf hangs well above the floor)
                continue
            if not purpose or purpose == 'none' or purpose not in RECIPES:
                purpose = 'living'
        if not purpose or purpose == 'none' or purpose not in RECIPES:
            continue
        if purpose == 'hall':
            purpose = hall_kind(room, refs, T, info['rooms'])     # (a corridor, an entry or a landing: room-kind survey R2)
        tl = room['_tiles']
        # inside the room (wall spots already stand off the measured wall face)
        inner = (room['x_min'] + 8, room['y_min'] + 8, room['x_max'] - 8, room['y_max'] - 8)
        fl = room['floor']
        # open sides of this room (to other rooms, doorways) stay clear
        for t in tl:
            for s, (dx, dy) in STEP.items():
                if t['pat'][s] == 'door' or (t['pat'][s] == 'open' and not any(
                        abs(u['x'] - (t['x'] + dx * T)) < 24 and abs(u['y'] - (t['y'] + dy * T)) < 24 for u in tl)):
                    mx, my = t['x'] + dx * T * 0.45, t['y'] + dy * T * 0.45
                    taken.append(((mx - 100, my - 100, mx + 100, my + 100), fl, fl + 200, True))
            # the mouth of a one-tile nook (three walls: the game's alcove for a bed between posts) stays
            # clear on the room's side: nothing stands across it (the user's cupboard blocking the alcove)
            walls_t = [s for s in STEP if t['pat'][s] == 'wall']
            if len(walls_t) == 3:
                op = next(s for s in STEP if s not in walls_t)
                dx, dy = STEP[op]
                mx, my = t['x'] + dx * (T / 2 + 75), t['y'] + dy * (T / 2 + 75)
                half = (T * 0.45, 75) if op in ('N', 'S') else (75, T * 0.45)
                taken.append(((mx - half[0], my - half[1], mx + half[0], my + half[1]), fl, fl + 200, True))
        # spots along the walls: (x, y on the wall's inside face, direction into the room, is it a corner)
        slots = []
        for t in tl:
            walls_here = [s for s in STEP if t['pat'][s] == 'wall']
            for s in walls_here:
                off = t['pat']['offset'].get(s, T / 2 - 16) - 14
                wx, wy = t['x'] + STEP[s][0] * off, t['y'] + STEP[s][1] * off
                inward = (-STEP[s][0], -STEP[s][1])
                slots.append({'x': wx, 'y': wy, 'in': inward, 'corner': len(walls_here) >= 2, 'side': s})
        rng.shuffle(slots)
        cx, cy = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
        # what each wall of the room is (the door's wall, the one opposite it, a window wall, a long or a
        # short wall: placesurvey.py), and the free-standing columns in it, whose feet the game stands
        # planters and urns at
        import placesurvey
        import catalogue
        wall_sides = placesurvey.room_sides(room, T, openings, [r for r in refs if r.get('arch') and r.get('b')])
        col_slots = []
        for a in refs:
            if not (a.get('arch') and a.get('b') and catalogue.COLUMN.search(a['id'].lower())):
                continue
            if not (fl - 60 <= a['p'][2] <= fl + 200 and room['x_min'] + T * 0.3 <= a['p'][0] <= room['x_max'] - T * 0.3
                    and room['y_min'] + T * 0.3 <= a['p'][1] <= room['y_max'] - T * 0.3):
                continue
            import fixit
            bx = fixit._world_box(a)
            if not bx or max(bx[3] - bx[0], bx[4] - bx[1]) > T * 0.6:
                continue
            mx, my = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            for s, (dx, dy) in STEP.items():
                # (the slot's point is on the column's face, like a wall slot's on the wall's; the thing
                # stands with its back to the column, facing away from it)
                face = (bx[3] if dx > 0 else bx[0]) if dx else mx, (bx[4] if dy > 0 else bx[1]) if dy else my
                col_slots.append({'x': face[0] + dx * 2, 'y': face[1] + dy * 2, 'in': (dx, dy), 'corner': False, 'side': s, 'column': True})
        rng.shuffle(col_slots)
        ledge = catalogue.rule(db, 'ledge', cell_style)
        ledge_h = (ledge or {}).get('height') if ledge and (ledge.get('share') or 0) >= 0.2 and ledge.get('own') else None
        # how big the room is, in standard 256-unit tiles (traced floors are cut finer); a huge hall
        # doesn't get endless furniture
        area_k = max(1.0, min(3.0, room['tiles'] * (T / 256.0) ** 2 / 9.0))
        area_f = max(0.4, min(3.0, room['tiles'] * (T / 256.0) ** 2 / 9.0))      # (for the game's per-nine-tile rates: a small room gets less)
        tables = []
        fronts = []         # what people stand in front of: a bed's side, a shrine, a counter ({box, in})
        got = []
        hung_here = []      # the lanterns hung in this room, (x, y)
        long_box = [None]   # a dining room's long table (two tables end to end) as one box, for its rug and chairs
        # an entrance hall's axis: from the front door's middle through the room (R1: the entry is symmetrical about it)
        entry_axis = None
        if purpose == 'entry':
            fds_ = front_doors(room, refs, T, info['rooms'])
            if fds_:
                d_, inward_ = fds_[0]
                # (the axis runs square to the door's wall, into the room; a door set off the room's middle,
                # as a two-wide hall's must be, keeps the room's own middle line: the room is still symmetrical)
                mid_ = ((room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2)
                off_ = (d_['p'][0] - mid_[0]) if inward_[1] else (d_['p'][1] - mid_[1])
                ax_pt = (d_['p'][0], d_['p'][1]) if abs(off_) < T * 0.3 else mid_
                entry_axis = (ax_pt, inward_)
        MIRROR_KINDS = ('bench', 'lamp', 'planter', 'urn', 'chest', 'basket', 'screen', 'chair', 'bookshelf', 'shelf', 'barrel', 'sack')
        WALL_MIRROR = ('bench', 'chest', 'screen', 'bookshelf', 'shelf', 'barrel')   # (these keep a wall at their back on the far side too)

        def entry_mirror(b, front, x, y, rot, kind):
            """Where this thing's twin stands across the entrance hall's axis (R1): (x, y, rot, box), or
            None when it is on the axis itself or its twin would not fit (or, for a wall piece, would
            stand off the wall)."""
            if entry_axis is None:
                return None
            (dx_, dy_), (ax_, ay_) = entry_axis
            vx_, vy_ = x - dx_, y - dy_
            al_ = vx_ * ax_ + vy_ * ay_
            mxx, myy = 2 * (dx_ + ax_ * al_) - x, 2 * (dy_ + ay_ * al_) - y
            if math.hypot(mxx - x, myy - y) <= 60:
                return None
            fr_ = front or (0.0, -1.0)
            c_, s_ = math.cos(rot), math.sin(rot)
            fwx, fwy = fr_[0] * c_ + fr_[1] * s_, -fr_[0] * s_ + fr_[1] * c_
            dd_ = fwx * ax_ + fwy * ay_
            mfx, mfy = 2 * dd_ * ax_ - fwx, 2 * dd_ * ay_ - fwy          # (the facing mirrored across the axis)
            mrot_ = _turn_to_face(front, (mfx, mfy))
            mbox_ = _footprint(b, mrot_, mxx, myy)
            if not fits(mbox_):
                return None
            if kind in WALL_MIRROR and not wall_behind(b, mrot_, mxx, myy, room, T, fr_, reach=30):
                return None
            return mxx, myy, mrot_, mbox_

        def pick(kind):
            lst = fam.get(kind) or []
            if kind == 'chest':
                # (a strongbox goes on a shelf or a table, as the game keeps it: decorsurvey.py; the
                # chest that stands on the floor is a clothes chest)
                import decorsurvey
                lst = [r for r in lst if not decorsurvey.off_floor(db, r)]
            if L and L['cap'] is not None and kind in ('dish', 'bottle', 'book', 'food', 'candle'):
                import shelfsurvey
                lst = [r for r in lst if shelfsurvey.value_of(db, r)[1] <= L['cap']]
            if not lst:
                return None
            if kind == 'counter':
                # (a counter standing on its own is a straight segment, never an end or a corner piece of
                # a run: the user's "barely started shop counter")
                straight = [r for r in lst if not COUNTER_PART.search(r.lower())]
                lst = straight or lst
            if kind == 'shrine':
                # (the shrine models the game stands in places like this, of the house's own culture; the
                # game's own house shrines when the palette has none such)
                import shrinesurvey
                cu_ = STYLE_SET.get(style) or fam.get('_borrowed')
                ok_ = [r for r in lst if shrinesurvey.allowed(db, r, theme, cu_)]
                if not ok_ and shrinesurvey.ready(db) is not None:
                    ok_ = shrinesurvey.house_models(db, theme, cu_)[:6]
                    if not ok_:
                        return None
                lst = ok_ or lst
            if kind in CONTAINER_KINDS:
                # the container the game stands in rooms like this, in places like this, with its
                # contents (a kitchen barrel's saltrice, a bedroom chest's clothes and coins); in places
                # as well off as this one is to be, when a band was chosen
                import containersurvey
                for _try in range(6):
                    rid = containersurvey.pick(db, kind, purpose, theme0, rng, palette=lst, band_pool=cont_pool,
                                               max_value=L['cont_max'] if L else None)
                    if rid and (kind != 'chest' or not decorsurvey.off_floor(db, rid)):
                        return rid
                if L and L['cont_max'] is not None:
                    # (nothing cheap enough among the game's: the palette's own empty ones, else none)
                    lst = [r for r in lst if (wealthsurvey.container_value(db, r) or 0) <= L['cont_max']]
                    if not lst:
                        return None
            return lst[min(len(lst) - 1, int(rng.random() ** 2 * min(4, len(lst))))]

        # the room's floor as the walls bound it (room_rects): the one wall check every path goes through
        tile_rects = room_rects(room, T)

        def inside(box, loose=False):
            if loose:
                # (a plant's fronds may brush the wall its planter stands at)
                return box[0] >= inner[0] and box[1] >= inner[1] and box[2] <= inner[2] and box[3] <= inner[3]
            return on_floor(box, tile_rects, inner)

        def fits(box, clearings=True):
            """Inside the room and clear of what stands on this floor (and of doorways, unless clearings
            is False: a door mat may lie in one)."""
            if not inside(box):
                return False
            return not any(_overlaps(box, o[0]) for o in taken
                           if o[1] < fl + 150 and o[2] > fl + 4 and (clearings or not o[3]))

        def slot_order(where, pp):
            """The wall slots in the order to try them: corners first (or last) by the recipe's word, and
            otherwise drawn by the game's own choice of wall for the kind (placesurvey: the wall opposite
            the door for a bed, a long wall for a bookshelf...), a corner slot as often as the kind stands
            in a corner. Without the survey, the old order."""
            if not pp or not pp.get('wall'):
                return sorted(slots, key=lambda s: (not s['corner']) if where == 'corner' else s['corner'])
            ck = max(0.2, min(5.0, pp.get('corner', 0.2) / max(0.05, 1 - pp.get('corner', 0.2))))
            pool = []
            for s in slots:
                w = pp['wall'].get(placesurvey.wall_class(s['side'], wall_sides), 0.05) + 0.02
                if s['corner']:
                    w *= ck
                if where == 'corner':
                    w *= 20.0 if s['corner'] else 1.0
                pool.append([w, s])
            out = []
            while pool:
                total = sum(w for w, _s in pool)
                r = rng.random() * total
                for i, (w, s) in enumerate(pool):
                    r -= w
                    if r <= 0:
                        out.append(pool.pop(i)[1])
                        break
                else:
                    out.append(pool.pop()[1])
            return out

        def settle(b, rot, x, y, inward, box):
            """A thing with its back to a wall in a style whose rooms have ledges along the walls: on the
            ledge when the whole of it stands up there (a bench, a planter, an urn: the catalogue's benches
            on the Redoran ledges), else moved out until all four corners are down on the floor (a bed or
            a table half up on the ledge would tilt). Returns (x, y, box) or None."""
            if ledge_h is None:
                return x, y, box
            for step in range(0, 14):
                d = step * 16
                qx, qy = x + inward[0] * d, y + inward[1] * d
                qb = _footprint(b, rot, qx, qy)
                hs = [floor_by_mesh(px, py, fl) for px, py in ((qb[0] + 6, qb[1] + 6), (qb[2] - 6, qb[1] + 6), (qb[0] + 6, qb[3] - 6), (qb[2] - 6, qb[3] - 6))]
                if any(h is None for h in hs):
                    return None
                lo, hi = min(hs), max(hs)
                if hi - lo <= 20 and (abs(lo - fl) <= 24 or (step == 0 and 24 < lo - fl <= ledge_h + 30)):
                    return qx, qy, qb
                if hi - lo <= 20 and abs(lo - fl) > 24:
                    return None                      # (all four up on something that isn't the ledge)
            return None

        def wall_spot(b, front, where, pp=None, kind=None, gap=2, near=None):
            """A free spot for this thing with its back to a wall (a corner first when where is
            'corner'): ((x, y, rot, box), direction into the room), or (None, None). The slot is used up.
            pp: how the game places the kind (placesurvey.prefs): which wall, how often a corner, how
            often the foot of a column. gap: how far off the wall (a counter leaves the keeper's side).
            near: a point (x, y) the slots nearest to are tried first (a kitchen's sack by the door)."""
            order = slot_order(where, pp)
            if near is not None:
                order = sorted(order, key=lambda sl: math.hypot(sl['x'] - near[0], sl['y'] - near[1]))
            if col_slots and pp and (pp.get('at_column') or 0) > 0 and rng.random() < pp['at_column']:
                order = list(col_slots) + order
            if kind == 'counter':
                order = [sl for sl in order if not sl.get('column') and not sl['corner']] or order
            if kind in HANGING_KINDS:
                order = [sl for sl in order if not sl.get('column')]      # (nothing hangs on a column's foot)
            # (in an entrance hall a thing that can stand in a mirrored pair takes a slot whose twin
            # across the door's axis is free, when there is one: R1)
            passes = (True, False) if (purpose == 'entry' and entry_axis is not None and kind in MIRROR_KINDS) else (False,)
            for want_twin in passes:
              for sl in order:
                rot = _turn_to_face(front, sl['in'])
                box0 = _footprint(b, rot, 0, 0)
                # back against the wall: move out by the part of the box behind the origin
                depth_back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sl['in']]
                x = sl['x'] + sl['in'][0] * (depth_back + gap)
                y = sl['y'] + sl['in'][1] * (depth_back + gap)
                box = _footprint(b, rot, x, y)
                if gap > 20:
                    # (the keeper's side behind a counter stays clear too)
                    back = (x - sl['in'][0] * gap, y - sl['in'][1] * gap)
                    bb = _footprint(b, rot, back[0], back[1])
                    if not fits((min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))):
                        continue
                if not sl.get('column'):
                    st = settle(b, rot, x, y, sl['in'], box)
                    if st is None:
                        continue
                    x, y, box = st
                if want_twin and entry_mirror(b, front, x, y, rot, kind) is None:
                    continue
                if fits(box):
                    (col_slots if sl.get('column') else slots).remove(sl)
                    return (x, y, rot, box), sl['in']
            return None, None

        def lay_counter_run(pp, dress_fn):
            """A counter laid as one of the game's own runs (countersurvey.py: three to six segments in an
            L, a U or a straight line, with its end and corner pieces, at the game's own offsets and
            turns), with its back to a wall at the gap the game's run had (half the game's runs stand
            against the wall; the rest leave a keeper's side of 96 to 256 behind), its ends flush to a
            side wall as often as the game's are, every segment dressed the way the game dresses that
            model, and what the game stands behind its counters (a shelf, a chair, a sack) at the game's
            rates. Returns {anchor, done, face, n, ids} or None when no run fits the room."""
            import countersurvey
            culture = STYLE_SET.get(cell_style) or fam.get('_borrowed') or None
            cands = countersurvey.compositions(db, cell_style, purpose, culture=culture)
            if not cands:
                return None
            rule = countersurvey.rule(db, cell_style) or {}
            cands = list(cands)
            rng.shuffle(cands)
            # (a run that suits the room: the game's eleven-segment U is a trade hall's, not a four-tile
            # shop's; a run longer than three quarters of the room's longer wall only when none shorter fits)
            long_wall = max(room['x_max'] - room['x_min'], room['y_max'] - room['y_min'])
            n_cap = max(3, int(round(room['tiles'] * 0.5)))    # (a four-by-three shop: six segments at most)
            suits = [r_ for r_ in cands if r_['length'] <= 0.75 * long_wall and r_['n'] <= n_cap]
            cands = suits[:8] + sorted(cands, key=lambda r_: r_['length'])[:4] + [r_ for r_ in cands if r_ not in suits][:4]
            order = [sl for sl in slot_order('wall', pp) if not sl.get('column') and not sl['corner']]
            order += [sl for sl in slot_order('wall', pp) if not sl.get('column') and sl['corner']]   # (a corner slot last: an L's elbow in the room's corner)
            if not order:
                return None
            flush_first = rng.random() < 2 * (rule.get('ends_at_wall') or 0.29)
            for run in cands:
                segs = []
                for mid, rz, off, sc in zip(run['models'], run['rzs'], run['offsets'], run['scales']):
                    ri_ = db.resolve_id(mid)
                    b_ = mapdata.object_bounds(db, ri_) if ri_ is not None else None
                    if not b_ or db.recs[ri_][0] not in ('STAT', 'ACTI', 'CONT'):
                        break
                    segs.append((mid, rz, off, sc, [v * sc for v in b_]))
                if len(segs) != len(run['models']):
                    continue
                # (against the wall, or a keeper's side wide enough to stand in: never the cramped between)
                gap = max(0, min(192, run.get('keeper_gap') or 0))
                gap = 2 if gap < 40 else max(80, gap)
                for sl in order:
                    R = _turn_to_face(tuple(run['open']), sl['in'])
                    c_, s_ = math.cos(R), math.sin(R)
                    rel = []                 # (each segment turned about the first: offset, turn, box about (0, 0))
                    for mid, rz, off, sc, b_ in segs:
                        ox = off[0] * c_ + off[1] * s_
                        oy = -off[0] * s_ + off[1] * c_
                        rel.append((mid, (rz + R) % (2 * math.pi), ox, oy, sc, _footprint(b_, rz + R, ox, oy)))
                    RB = (min(r_[5][0] for r_ in rel), min(r_[5][1] for r_ in rel), max(r_[5][2] for r_ in rel), max(r_[5][3] for r_ in rel))
                    inx, iny = sl['in']
                    # the run's back edge at the wall's gap, its middle on the slot, or an end flush to a side wall
                    if iny:
                        Y = sl['y'] + iny * gap - (RB[1] if iny > 0 else RB[3])
                        mids = [sl['x'] - (RB[0] + RB[2]) / 2 + d for d in (0, T, -T, 2 * T, -2 * T)]
                        flush = [inner[0] + 2 - RB[0], inner[2] - 2 - RB[2]]
                        xs = (flush + mids) if flush_first else (mids + flush)
                        tries = [(x_, Y) for x_ in xs]
                    else:
                        X = sl['x'] + inx * gap - (RB[0] if inx > 0 else RB[2])
                        mids = [sl['y'] - (RB[1] + RB[3]) / 2 + d for d in (0, T, -T, 2 * T, -2 * T)]
                        flush = [inner[1] + 2 - RB[1], inner[3] - 2 - RB[3]]
                        ys = (flush + mids) if flush_first else (mids + flush)
                        tries = [(X, y_) for y_ in ys]
                    for X, Y in tries:
                        boxes = [(r_[5][0] + X, r_[5][1] + Y, r_[5][2] + X, r_[5][3] + Y) for r_ in rel]
                        if not all(fits(bx_) for bx_ in boxes):
                            continue
                        if gap > 20:
                            # (the keeper's side behind the run stays clear: nothing between it and the wall)
                            whole = (RB[0] + X, RB[1] + Y, RB[2] + X, RB[3] + Y)
                            back = (whole[0] - max(0, inx) * gap + max(0, -inx) * 0, whole[1] - max(0, iny) * gap, whole[2] + max(0, -inx) * gap, whole[3] + max(0, -iny) * gap)
                            strip = (back[0], back[1], back[2], back[3])
                            if any(_overlaps(strip, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4):
                                continue
                        if any(floor_by_mesh(bx_[0] + 6, bx_[1] + 6, fl) is None or abs((floor_by_mesh((bx_[0] + bx_[2]) / 2, (bx_[1] + bx_[3]) / 2, fl) or fl) - fl) > 24 for bx_ in boxes):
                            continue      # (every segment down on this floor, none up on a ledge or over a stairwell)
                        recs_ = []
                        for (mid, rz_, ox, oy, sc, _b), bx_ in zip(rel, boxes):
                            r_ = put(mid, X + ox, Y + oy, rz_, floor=fl, room=room['name'], scale=sc)
                            if r_ is None:
                                continue
                            recs_.append((r_, bx_))
                        if not recs_:
                            continue
                        ids = []
                        for r_, bx_ in recs_:
                            taken.append((bx_, fl, fl + 200, False))
                            laid_ = dress_fn(r_, purpose)
                            tables.append({'box': bx_, 'items': [], 'dressed': bool(laid_), 'counter': True})
                            fronts.append({'box': bx_, 'in': sl['in'], 'kind': 'counter'})
                            ids.append(r_['id'])
                        # the slots the run covers are used up (nothing else goes behind it); what the game
                        # stands behind its counters goes there, at the game's rates
                        whole = (RB[0] + X, RB[1] + Y, RB[2] + X, RB[3] + Y)
                        behind_slots = [s2 for s2 in slots if s2['in'] == sl['in'] and
                                        (whole[0] - T / 2 <= s2['x'] <= whole[2] + T / 2 if iny else whole[1] - T / 2 <= s2['y'] <= whole[3] + T / 2)]
                        for s2 in behind_slots:
                            slots.remove(s2)
                        if gap >= 80 and behind_slots:
                            rng.shuffle(behind_slots)
                            for kind_, rate in sorted((rule.get('behind') or {}).items(), key=lambda kv: -kv[1]):
                                if kind_ not in ('shelf', 'chair', 'sack', 'crate', 'barrel', 'chest', 'bookshelf') or rng.random() >= rate:
                                    continue
                                rid_ = pick(kind_)
                                b2 = mapdata.object_bounds(db, db.resolve_id(rid_)) if rid_ else None
                                if not b2:
                                    continue
                                fr_ = front_of(db, rid_)
                                for s2 in list(behind_slots):
                                    rot2 = _turn_to_face(fr_, s2['in'])
                                    box0 = _footprint(b2, rot2, 0, 0)
                                    depth_back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[s2['in']]
                                    x2, y2 = s2['x'] + s2['in'][0] * (depth_back + 2), s2['y'] + s2['in'][1] * (depth_back + 2)
                                    box2 = _footprint(b2, rot2, x2, y2)
                                    hang2 = shelf_hang(rid_, b2) if kind_ in HANGING_KINDS else 0.0
                                    if hang2 is None or not fits(box2):
                                        continue
                                    r2 = put(rid_, x2, y2, rot2, floor=fl, room=room['name'], hang_from=(fl + hang2) if hang2 > 0 else None)
                                    if r2 is None:
                                        continue
                                    if not hang2:
                                        taken.append((box2, fl, fl + 200, False))
                                    ids.append(rid_)
                                    if kind_ in DRESSED_KINDS:
                                        dress_fn(r2, purpose)
                                    behind_slots.remove(s2)
                                    break
                        if gap >= 80:
                            # (and the rest of the keeper's side stays clear like a doorway: the recipe's
                            # bookshelf stood behind the run from a slot on the side wall)
                            if iny:
                                strip = (whole[0], min(whole[1], sl['y']), whole[2], max(whole[3], sl['y']))
                            else:
                                strip = (min(whole[0], sl['x']), whole[1], max(whole[2], sl['x']), whole[3])
                            taken.append((strip, fl, fl + 200, True))
                        # (the main piece for the scene's other members: the segment nearest the run's middle)
                        mx_, my_ = (whole[0] + whole[2]) / 2, (whole[1] + whole[3]) / 2
                        a_, abx = min(recs_, key=lambda rb: math.hypot(rb[0]['p'][0] - mx_, rb[0]['p'][1] - my_))
                        # (the customer side, a tile deep along the run's open side, is kept clear like a
                        # doorway once the scene's stools are in: the user's dresser "in the way" in front
                        # of the counter, which "defeats the purpose of the counter")
                        if iny:
                            front_ = (whole[0], whole[3], whole[2], whole[3] + T) if iny > 0 else (whole[0], whole[1] - T, whole[2], whole[1])
                        else:
                            front_ = (whole[2], whole[1], whole[2] + T, whole[3]) if inx > 0 else (whole[0] - T, whole[1], whole[0], whole[3])
                        last_trace.append((room['name'], 'counter', run['models'][0], 'a run of %d (%s) from %s, gap %d' % (len(recs_), run['shape'], run['cell'], gap)))
                        return {'anchor': a_, 'done': (a_['p'][0], a_['p'][1], R, abx), 'face': sl['in'], 'n': len(recs_), 'ids': ids,
                                'front': (front_, fl, fl + 200, True)}
            last_trace.append((room['name'], 'counter', '-', 'no run of the game\'s fits this room'))
            return None

        def divider_spot(b, front):
            """A shelf standing out from a wall as a room divider, the way Hlaalu's shops stand their
            shelves of pots and jars (catalogue rule 6): turned across the room, one end at the wall."""
            for sl in slot_order('wall', None):
                if sl['corner']:
                    continue
                side = rng.choice((1, -1))
                along = (sl['in'][1] * side, -sl['in'][0] * side)        # (its front along the wall)
                rot = _turn_to_face(front, along)
                box0 = _footprint(b, rot, 0, 0)
                depth_back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sl['in']]
                x = sl['x'] + sl['in'][0] * (depth_back + 2)
                y = sl['y'] + sl['in'][1] * (depth_back + 2)
                box = _footprint(b, rot, x, y)
                st = settle(b, rot, x, y, sl['in'], box)
                if st is None:
                    continue
                x, y, box = st
                if fits(box):
                    slots.remove(sl)
                    return (x, y, rot, box), along
            return None, None

        def place_clutter(items, cs):
            """Crates, barrels, sacks and urns in groups the way the game stands them (roomsurvey
            clusters): a group starts at a corner or by a wall as often as the game's do, is as big as the
            game's groups are, and each further piece stands next to one already in the group, about as
            far off as the game keeps its own kind. items: the kinds to place, in order; returns the
            group sizes made."""
            sizes = [(s, w) for s, w in cs['sizes'] if w > 0] or [(1, 1.0)]
            w_corner = cs['where'].get('corner', 0.5)
            w_wall = cs['where'].get('wall', 0.4)
            groups = []
            sack_by_door = [False]
            guard = 0
            while items and guard < 40:
                guard += 1
                # how big this group is to be
                x_ = rng.random() * sum(w for _s, w in sizes)
                target = sizes[-1][0]
                for s_, w in sizes:
                    x_ -= w
                    if x_ <= 0:
                        target = s_
                        break
                target = min(target, len(items))
                # where it starts: in a corner or along a wall
                kind = items[0]
                rid = pick(kind)
                if not rid:
                    items[:] = [k for k in items if k != kind]
                    continue
                b = mapdata.object_bounds(db, db.resolve_id(rid))
                if not b:
                    items.pop(0)
                    continue
                front = front_of(db, rid)
                where = 'corner' if rng.random() * (w_corner + w_wall) < w_corner else 'wall'
                # (a kitchen's first sack stands by the door, as Nelara's and the catalogue's kitchens
                # keep theirs: R3)
                near_ = None
                if purpose == 'kitchen' and kind == 'sack' and not sack_by_door[0]:
                    drs_ = [o_ for o_ in openings if room['x_min'] - 60 <= o_['p'][0] <= room['x_max'] + 60 and room['y_min'] - 60 <= o_['p'][1] <= room['y_max'] + 60 and abs(o_['p'][2] - fl) < 200]
                    if drs_:
                        near_ = (drs_[0]['p'][0], drs_[0]['p'][1])
                        where = 'wall'
                        sack_by_door[0] = True
                done, face = wall_spot(b, front, where, near=near_)
                if not done:
                    done, face = wall_spot(b, front, 'wall' if where == 'corner' else 'corner', near=near_)
                pp_ = placesurvey.prefs(db, kind, purpose)
                if not done and target >= 2 and ((pp_ or {}).get('at', {}).get('middle', 0) >= 0.2 or purpose in ('storage', 'kitchen', 'armoury')):
                    # (a store's groups stand out on the floor one time in four in the game: room-kind survey R3)
                    # (the wall slots all taken by furniture: a little way out from a wall, or out on the
                    # floor, as a fifth of the game's groups are; only a group of two or more, and only
                    # for a kind the game does stand out in the room: never a lone crate mid-floor)
                    for _try in range(14):
                        side = rng.choice(list(STEP))
                        sx, sy = STEP[side]
                        rot = _turn_to_face(front, (-sx, -sy))
                        box0 = _footprint(b, rot, 0, 0)
                        depth = rng.uniform(0, T * 0.5) if rng.random() < 0.75 else rng.uniform(T * 0.5, T * 1.5)
                        x, y = rng.uniform(inner[0] + 60, inner[2] - 60), rng.uniform(inner[1] + 60, inner[3] - 60)
                        if sx:
                            x = (inner[2] - box0[2] - depth) if sx > 0 else (inner[0] - box0[0] + depth)
                        else:
                            y = (inner[3] - box0[3] - depth) if sy > 0 else (inner[1] - box0[1] + depth)
                        box = _footprint(b, rot, x, y)
                        if fits(box):
                            done, face = (x, y, rot, box), (-sx, -sy)
                            break
                if not done:
                    # (no spot for this kind: the other kinds still get their turn; a storeroom whose
                    # barrels found no corner lost its crates and sacks too, and stood half empty)
                    last_clutter.append((room['name'], kind, 'no spot for a group', len(items)))
                    items[:] = [k for k in items if k != kind]
                    continue
                rec = put(rid, done[0], done[1], done[2], floor=fl, room=room['name'], ledge=ledge_h)
                if rec is None:
                    items.pop(0)
                    continue
                taken.append((done[3], fl, fl + 200, False))
                got.append(rid)
                items.pop(0)
                group = [(done[0], done[1], done[2], rec)]
                # the rest of the group, each beside one already standing
                while items and len(group) < target:
                    kind = items[0]
                    rid = pick(kind)
                    if not rid:
                        items.pop(0)
                        continue
                    b = mapdata.object_bounds(db, db.resolve_id(rid))
                    if not b:
                        items.pop(0)
                        continue
                    # beside one of the group: along the wall first, then out into the room, close enough
                    # to touch (the game's own stand about a crate's width apart, origin to origin)
                    near = cs['nn'].get(kind) or cs.get('nn_any') or 60
                    spot = None
                    dirs = [(face[1], -face[0]), (-face[1], face[0]), face, (face[0] + face[1], face[1] - face[0]), (face[0] - face[1], face[1] + face[0])]
                    for _try in range(16):
                        bx, by, brot, br = rng.choice(group)
                        ux, uy = dirs[min(len(dirs) - 1, int(rng.random() ** 2 * len(dirs)))]
                        rot = (brot + rng.choice((0, 0, 0, math.pi / 2, -math.pi / 2)) + rng.uniform(-0.12, 0.12)) % (2 * math.pi)
                        # the two boxes side by side along that way, plus a hand's width now and then
                        fa, fb = _footprint([v * (br['s'] or 1.0) for v in br['b']], brot, 0, 0), _footprint(b, rot, 0, 0)
                        ext = lambda f, u: abs(u[0]) * (f[2] - f[0]) / 2 + abs(u[1]) * (f[3] - f[1]) / 2
                        d = max(near * 0.6, ext(fa, (ux, uy)) + ext(fb, (ux, uy)) + rng.uniform(2, 18)) / math.hypot(ux, uy)
                        x, y = bx + d * ux, by + d * uy
                        box = _footprint(b, rot, x, y)
                        if fits(box):
                            spot = (x, y, rot, box)
                            break
                    if not spot:
                        last_clutter.append((room['name'], kind, 'no spot beside', len(group), target))
                        break                    # (no room beside this group: the next piece starts another)
                    rec = put(rid, spot[0], spot[1], spot[2], floor=fl, room=room['name'])
                    items.pop(0)
                    if rec is None:
                        continue
                    taken.append((spot[3], fl, fl + 200, False))
                    got.append(rid)
                    group.append((spot[0], spot[1], spot[2], rec))
                for _x, _y, _r, rec in group:
                    rec['group'] = len(groups)
                groups.append(len(group))
                last_clutter.append((room['name'], 'group', len(group), target, len(items)))
            return groups

        def rug_at(rug, x, y, along_x, clearings=True, furniture=True):
            """A rug lying at (x, y), its long side along x or y: (x, y, rot, box) if it's free there."""
            rid, rb = rug[0], rug[1]
            long_x = (rb[3] - rb[0]) >= (rb[4] - rb[1])
            rot = 0.0 if long_x == along_x else math.pi / 2
            box = _footprint(rb, rot, x, y)
            # (where the model's middle isn't its origin, put the middle there)
            x, y = x - ((box[0] + box[2]) / 2 - x), y - ((box[1] + box[3]) / 2 - y)
            box = _footprint(rb, rot, x, y)
            if not inside(box) or not rug_free(box, fl):
                return None
            # floor under all four corners on this room's own floor, by the building's real geometry: a
            # rug at the edge of the stairwell opening upstairs hung out over the stairs (the Gold Coast
            # stair's upper piece has the opening inside its own box, so a box check passed it)
            for qx, qy in ((box[0] + 8, box[1] + 8), (box[2] - 8, box[1] + 8), (box[0] + 8, box[3] - 8), (box[2] - 8, box[3] - 8)):
                zq = floor_by_mesh(qx, qy, fl)
                if zq is None or abs(zq - fl) > 24:
                    return None
            if furniture and not fits(box, clearings):
                return None
            return (x, y, rot, box)

        def place_rug(where, rug_list):
            if where == 'rug':
                # where the game lays a room's rug (catalogue rule 2): a round rug centred in the room
                # in the styles that do so (Redoran, Indoril), a rectangular one under the table elsewhere,
                # beside the bed in a bedroom, at the style's own rates
                rr = catalogue.rule(db, 'rugs', cell_style)
                is_round = lambda r: catalogue.is_round(db, r[0])
                rounds = [r for r in rug_list if is_round(r)]
                rects = [r for r in rug_list if not is_round(r)] or rug_list
                if rr and rounds and rng.random() < (rr.get('round_share') or 0):
                    if rng.random() < (rr.get('round_centred') or 0) or not tables:
                        for rug in sorted(rounds, key=lambda r: -r[2])[:4]:
                            s = rug_at(rug, cx, cy, True, furniture=False)
                            if s:
                                return rug, s
                    got_ = place_rug('under_table', rounds)
                    if got_:
                        return got_
                beds_here = [f for f in fronts if f.get('kind') == 'bed']
                p_bed = (rr or {}).get('rect_by_bed') or 0
                order = ['by_bed', 'under_table'] if beds_here and rng.random() < p_bed else ['under_table', 'by_bed']
                for w in order:
                    got_ = place_rug(w, rects)
                    if got_:
                        return got_
                if rr and rng.random() < (rr.get('rect_centred') or 0):
                    for rug in sorted(rects, key=lambda r: -r[2])[:4]:
                        s = rug_at(rug, cx, cy, (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min']), furniture=False)
                        if s:
                            return rug, s
                return None
            if where == 'under_table' and tables:
                tb = long_box[0] or tables[-1]['box']        # (a dining room's long table: one rug under the whole)
                tw, td = tb[2] - tb[0], tb[3] - tb[1]
                # the smallest rug that is bigger than the table all round, or failing that the biggest
                fit = sorted([r for r in rug_list if r[2] >= max(tw, td) + 40 and r[3] >= min(tw, td) + 20], key=lambda r: r[2])
                for rug in (fit or sorted(rug_list, key=lambda r: -r[2]))[:4]:
                    s = rug_at(rug, (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2, tw >= td, furniture=False)
                    if s:
                        return rug, s
            elif where in ('by_bed', 'before') and fronts:
                f = fronts[-1]
                fb, (ix, iy) = f['box'], f['in']
                for rug in sorted(rug_list, key=lambda r: abs(r[2] - 200))[:4]:
                    half_l, half_s = rug[2] / 2, rug[3] / 2
                    if where == 'before':
                        # in front of it, lying across its front
                        mx, my = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
                        reach = (fb[2] - fb[0]) / 2 if ix else (fb[3] - fb[1]) / 2
                        spots = [(mx + ix * (reach + half_s + 8), my + iy * (reach + half_s + 8), iy != 0)]
                    else:
                        # beside the bed, along its long side, where one gets out of it
                        if (fb[2] - fb[0]) >= (fb[3] - fb[1]):
                            spots = [((fb[0] + fb[2]) / 2, fb[3] + half_s + 6, True), ((fb[0] + fb[2]) / 2, fb[1] - half_s - 6, True)]
                        else:
                            spots = [(fb[2] + half_s + 6, (fb[1] + fb[3]) / 2, False), (fb[0] - half_s - 6, (fb[1] + fb[3]) / 2, False)]
                        rng.shuffle(spots)
                    for x, y, ax in spots:
                        s = rug_at(rug, x, y, ax)
                        if s:
                            return rug, s
            elif where == 'runner':
                # a long, narrow rug down the middle of a hall
                along_x = (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min'])
                for rug in sorted([r for r in rug_list if r[2] >= 1.6 * r[3]], key=lambda r: -r[2]):
                    s = rug_at(rug, cx, cy, along_x, clearings=False, furniture=False)
                    if s:
                        return rug, s
            return None

        # what goes in a room like this: the game's own rooms of the kind, once surveyed (roomrules.py),
        # the hand-written recipe until then; the standing lamps the game lights such rooms with
        import roomrules
        fam['lamp'] = roomrules.floor_lamps(db, purpose)

        # the lanterns and hanging lamps: the game hangs a lantern (three in four hang, one in a hundred
        # stands on the floor; decorsurvey.py) at the height it hangs the model, mostly out over the
        # room (a wall one time in five), never over a doorway, as many as such rooms have up high
        def hang_light(hid, up, gap, x, y):
            """A light hung at (x, y), its bottom `up` above the floor (lowered under a ceiling to the gap
            the game leaves there); None when it can't hang here, or when no ceiling is found over the
            spot (a light hangs from the ceiling or not at all: the user's "floating candelabras")."""
            hb = mapdata.object_bounds(db, db.resolve_id(hid))
            if not hb:
                return None
            box = _footprint(hb, 0, x, y)
            if not inside(box) or any(_overlaps(box, o[0]) for o in taken if o[3] and o[1] < fl + 150 and o[2] > fl + 4):
                return None
            if any(abs(h[0] - x) < 120 and abs(h[1] - y) < 120 for h in hung_here):
                return None
            z = fl + up - hb[2]
            over = [r['p'][2] + r['b'][2] * (r.get('s') or 1) for r in refs if r.get('arch') and r.get('b')
                    and r['p'][2] + r['b'][2] * (r.get('s') or 1) > fl + 100
                    and mapdata._rotated_contains(r, x, y)]
            if not over:
                return None
            ceiling = min(over)
            if z + hb[5] > ceiling - 4:
                z = ceiling - (gap if gap is not None and gap < 160 else 8) - hb[5]
            if z + hb[2] < fl + 110:
                return None
            rec = put(hid, x, y, rng.uniform(0, 2 * math.pi), at_z=z, room=room['name'])
            if rec:
                got.append(hid)
                hung_here.append((x, y))
            return rec

        def approach_box(box, rot, front):
            """The half-tile behind a seat (away from what it faces)."""
            f = front or (0.0, -1.0)
            fx = f[0] * math.cos(rot) + f[1] * math.sin(rot)
            fy = -f[0] * math.sin(rot) + f[1] * math.cos(rot)
            cx_, cy_ = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            w_ = max(box[2] - box[0], box[3] - box[1]) / 2 + 10
            ax_, ay_ = cx_ - fx * (w_ + 64), cy_ - fy * (w_ + 64)
            return (ax_ - w_, ay_ - w_, ax_ + w_, ay_ + w_)

        def keep_approach(box, rot, front):
            """The half-tile behind a seat stays clear, the way a doorway does: nothing stands between a
            chair and the room (the user's candle stand "right in front of the desk's chair, so the chair
            can't be reached"). False when something stands there already: the seat is not laid."""
            ab = approach_box(box, rot, front)
            if any(_overlaps(ab, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4 and not o[3]):
                return False
            taken.append((ab, fl, fl + 150, True))
            return True

        def shelf_hang(rid_, b_):
            """How high a wall shelf hangs: the game's height for the model, else the height the game
            hangs shelves in rooms of this kind; 0 for a shelf unit that stands on the floor (tall), None
            for a wall shelf with no known height (not placed: the user's Hlaalu ledge "lying on the
            floor against the wall" with its urns and cups)."""
            h_ = hang_height(db, rid_)
            if h_ > 0:
                return h_
            if (b_[5] - b_[2]) >= 70:
                return 0.0
            import wallsurvey2
            hr_ = wallsurvey2.hang_rule(db, SURVEY_KIND.get(purpose, purpose))
            return ((hr_ or {}).get('height') or {}).get('shelf') or None

        def surface_on(rec, x, y):
            """The top of a placed piece's real surface straight under (x, y), by its mesh, or None."""
            import seethrough
            ov = seethrough.overlay(db, [{'op': 'place', 'id': rec['id'], 'p': list(rec['p']), 's': rec.get('s', 1.0)}])
            if not ov.tris:
                return None
            top = rec['p'][2] + rec['b'][5] * (rec.get('s') or 1.0)
            hit = ov.nearest((x, y, top + 10), (0.0, 0.0, -1.0), (rec['b'][5] - rec['b'][2]) * (rec.get('s') or 1.0) + 20)
            return None if hit is None else top + 10 - hit[0]

        def plant_in(prec, x_, y_, rot_):
            """A plant in a planter just stood, as often as the game's planters hold one (catalogue rule 3;
            three in five when the catalogue hasn't run), its bottom on the planter's own soil by the mesh,
            never floating, never loose on the floor."""
            pr = catalogue.rule(db, 'planters', cell_style)
            # (at least one planter in two gets its plant whatever the style's own rate: the Common houses'
            # planters stand empty in the game, and an empty planter box reads as a stone block)
            if piece is None and rng.random() >= max(0.5, (pr or {}).get('with_plant') or 0.6):
                return None               # (asked for this one planter, it always gets its plant)
            pl = arrangesurvey.plant_for(db, prec['id'], rng)
            if not pl:
                return None
            c_, s_ = math.cos(rot_), math.sin(rot_)
            px_, py_ = x_ + pl['x'] * c_ + pl['y'] * s_, y_ - pl['x'] * s_ + pl['y'] * c_
            pb = mapdata.object_bounds(db, db.resolve_id(pl['id']))
            top = surface_on(prec, px_, py_)
            if not pb or top is None or not inside(_footprint([v * pl['s'] for v in pb], (rot_ + pl['rz']) % (2 * math.pi), px_, py_), loose=True):
                return None               # (and it stays in the room)
            return put(pl['id'], px_, py_, (rot_ + pl['rz']) % (2 * math.pi), at_z=top - 6 - pb[2] * pl['s'], scale=pl['s'], room=room['name'])

        def lay_arrangement(ex, where=None, skip=()):
            """One of the game's own set pieces (arrangesurvey.py: a bar with its stools and barrels, a
            shrine with its bench and urns, planters along a wall, a dining set), laid as the game lays
            it: its main piece with its back to a wall (or mid-room, as the game had it), the rest at
            the game's own offsets round it. Returns the kinds it stood, by count.
            where: the recipe's own word for the main piece ('corner' puts it in a corner; the game's
            example says wall or mid-room otherwise); skip: member kinds left out (a bed scene's chest:
            the recipe stands it across the foot of the bed by its own rule)."""
            kinds_laid = Counter()

            def local(rid_, kind):
                """The same kind of thing from the place's own palette, about the same size, so the game's
                arrangement comes in the house's own style (an Imperial table from Anvil in a Dunmer house
                would not); the original where the palette has nothing of the size. With a band chosen,
                the band's make of it when the palette has one of the size (and the original, if it is
                of the wrong make, is swapped for the palette's nearest)."""
                lst = fam.get(kind) or []
                ri0 = db.resolve_id(rid_)
                b0 = mapdata.object_bounds(db, ri0) if ri0 is not None else None
                wrong = bool(L) and L['tiers'][0] is not None and wealthsurvey.set_tier(rid_) not in (None, L['tiers'][0])
                if not lst or not b0 or (not wrong and any(x.lower() == rid_.lower() for x in lst[:12])):
                    return rid_
                w0, d0, h0 = b0[3] - b0[0], b0[4] - b0[1], b0[5] - b0[2]
                close = []
                for cand in lst[:12]:
                    rc = db.resolve_id(cand)
                    bc = mapdata.object_bounds(db, rc) if rc is not None else None
                    if not bc:
                        continue
                    w, d, h = bc[3] - bc[0], bc[4] - bc[1], bc[5] - bc[2]
                    if all(0.7 <= (x / y if y else 1) <= 1.4 for x, y in ((w, w0), (d, d0), (h, h0))):
                        close.append(cand)
                if close and L and L['tiers'][0] is not None:
                    best = [c for c in close if wealthsurvey.set_tier(c) == L['tiers'][0]]
                    close = best or close
                return rng.choice(close) if close else rid_

            def _small_alone(fam_, ex_):
                """A small piece (a crate, a planter, an urn, a basket, a chest, a screen) the game's example
                had out in the room: mid-floor only as part of a scene of two or more floor pieces, and only
                for a kind the placement survey shows out in the room one time in five; else to a wall."""
                if fam_ not in SMALL_KINDS:
                    return False
                others = [m_ for m_ in ex_['members'] if not m_.get('anchor') and m_['fam'] in roomsurvey.FLOOR_KINDS + SMALL_KINDS and m_['z'] <= 24]
                pp_ = placesurvey.prefs(db, fam_, purpose)
                return len(others) < 2 or not pp_ or pp_['at'].get('middle', 0) < 0.2

            a = ex['anchor']
            rid = local(a['id'], a['fam'])
            ri = db.resolve_id(rid)
            b = mapdata.object_bounds(db, ri) if ri is not None else None
            if not b or db.recs[ri][0] not in ('STAT', 'ACTI', 'CONT', 'LIGH'):
                return kinds_laid
            import decorsurvey
            if a['fam'] == 'chest' and decorsurvey.off_floor(db, rid):
                return kinds_laid         # (a strongbox belongs on a shelf, not loose on the floor)
            # (a shrine only in a shrine room, a temple or a priest's home; a bar only in a shop, a tavern
            # or a kitchen: the user's altar slab in a Common living room, "a strange choice here")
            if a['fam'] == 'shrine' and purpose != 'shrine' and theme != 'temple' and 'shrine' not in extras_left:
                return kinds_laid
            if a['fam'] == 'counter' and purpose not in ('shop', 'tavern', 'kitchen'):
                return kinds_laid
            shrine_comp = None
            if a['fam'] == 'shrine':
                shrine_comp, ok_ = shrine_ok(rid)
                if not ok_:
                    last_trace.append((room['name'], 'shrine', rid, 'the game never stands this model, or never without its statue: left out'))
                    return kinds_laid
            front = front_of(db, rid)
            done = face = None
            # (a bed always goes to a wall, whatever the game's example did: beds that followed a mid-room
            # example stood in the middle of the floor, the user's "beds always have a tendency to sit in
            # the middle of the room")
            run_laid = None
            if a['fam'] == 'counter':
                # (a counter is one of the game's own runs of segments, laid whole: countersurvey.py; the
                # scene's stools and barrels come round it. Only when no run fits does a lone straight
                # segment stand at a wall with the keeper's gap behind it)
                run_laid = lay_counter_run(placesurvey.prefs(db, 'counter', purpose), dress)
                if run_laid:
                    done, face = run_laid['done'], run_laid['face']
                else:
                    done, face = wall_spot(b, front, 'wall', pp=placesurvey.prefs(db, 'counter', purpose), kind='counter', gap=KEEPER_GAP)
            elif ex.get('wall', True) or a['fam'] in ('bed', 'bookshelf', 'cupboard', 'shelf', 'shrine') or where in ('wall', 'corner') or _small_alone(a['fam'], ex):
                # (a wall piece, a bookshelf or a cupboard, always to a wall, whatever the game's example
                # did: a bookshelf stood 223 units out in a study from a mid-room example; a shrine too:
                # the game's stand at a median 90 from the wall, and the user's saint shrine stood "in
                # the middle of a Common stone cellar room, beside a bench, nothing round it")
                done, face = wall_spot(b, front, 'corner' if where == 'corner' else 'wall')
            else:
                rot = _turn_to_face(front, (0, -1)) if front else 0.0
                for dx, dy in ((0, 0), (64, 0), (-64, 0), (0, 64), (0, -64)):
                    box = _footprint(b, rot, cx + dx, cy + dy)
                    if fits(box):
                        done = (cx + dx, cy + dy, rot, box)
                        face = (0, -1)
                        break
                if not done:
                    done, face = wall_spot(b, front, 'wall')
            if not done:
                return kinds_laid
            if a['fam'] == 'table' and any(_overlaps(done[3], t['box'], -160) for t in tables):
                return kinds_laid         # (a dining set hard against the room's table: one table doubled)
            a_hang = shelf_hang(rid, b) if a['fam'] in HANGING_KINDS else 0.0
            if a_hang is None:
                return kinds_laid         # (a wall shelf with no known hanging height)
            if run_laid:
                arec = run_laid['anchor']
                rid = arec['id']
                got.extend(run_laid['ids'])
                kinds_laid['counter'] += run_laid['n']
                skip = tuple(skip) + ('counter',)    # (the run is whole: the scene's own segments are not added to it)
            else:
                arec = put(rid, done[0], done[1], done[2], floor=fl, room=room['name'], ledge=ledge_h if a['fam'] in catalogue.LEDGE_KINDS else None,
                           hang_from=(fl + a_hang) if a_hang > 0 else None)
                if arec is None:
                    return kinds_laid
                taken.append((done[3], fl, fl + 200, False))
                got.append(rid)
                kinds_laid[a['fam']] += 1
            for m in ex['members']:
                if m['fam'] in extras_left:
                    extras_left.remove(m['fam'])      # (the trade's set piece is laid: once a house)
            laid = dress(arec, purpose) if a['fam'] in DRESSED_KINDS and not run_laid else None
            if a['fam'] == 'fire':
                got.extend(dress_hearth(arec, purpose))
            if a['fam'] == 'shrine':
                got.extend(dress_shrine(arec, shrine_comp))
            if a['fam'] in ('table', 'counter') and not run_laid:
                tables.append({'box': done[3], 'items': [], 'dressed': bool(laid), 'counter': a['fam'] == 'counter'})
            if a['fam'] in ('bed', 'shrine', 'counter') and face and not run_laid:
                fronts.append({'box': done[3], 'in': face, 'kind': a['fam']})
            R = done[2]
            c_, s_ = math.cos(R), math.sin(R)
            anchor_mesh = []                  # (the main piece's geometry, built once, for what rides on it)
            for m in ex['members']:
                if m.get('anchor') or m['fam'] in skip:
                    continue
                mid = local(m['id'], m['fam'])
                mri = db.resolve_id(mid)
                mb = mapdata.object_bounds(db, mri) if mri is not None else None
                if not mb or db.recs[mri][0] not in ('STAT', 'ACTI', 'CONT', 'LIGH', 'MISC', 'APPA'):
                    continue
                if db.recs[mri][0] in ('MISC', 'APPA'):
                    # (a thing worth taking that came with the game's set piece, a gold bar on a rich
                    # study's table, keeps to the shelf rule's cap for places of this theme: it was the
                    # one way a thing dearer than the cap got into a plain house)
                    import shelfsurvey
                    if shelfsurvey.interesting(db, mid) and shelfsurvey.value_of(db, mid)[1] > (shelfsurvey.value_cap(db, theme) or 10 ** 9):
                        continue
                # (the offset was kept in the main piece's own frame: back into the world, turned as it now stands)
                wx = done[0] + m['x'] * c_ + m['y'] * s_
                wy = done[1] - m['x'] * s_ + m['y'] * c_
                mrot = (R + m['rz']) % (2 * math.pi)
                # (a pillow rides on its bed however low the game's bed had it: set down "on the floor"
                # it was stood on the bed's box top, the headboard, and floated over the mattress)
                on_top = m['z'] > 24 or m['fam'] == 'pillow'
                if not on_top and m['fam'] == 'chest' and decorsurvey.off_floor(db, m['id']):
                    continue              # (a strongbox belongs on a shelf, not loose on the floor)
                mtag = db.recs[mri][0]
                mlow = mid.lower()
                # a light is hung from the ceiling or stands on the floor, nothing in between: a hanging
                # light (a lantern, a chandelier, a candelabra ring) goes up by the room's own ceiling at
                # the height the game had it, or not at all; a standing light (a lamp or candle stand)
                # goes down on the floor by the mesh; a candle rides a table or a shelf (the user's "floating
                # candelabras", "lanterns on the floor")
                hanging_light = mtag == 'LIGH' and (HANGING_LIGHT.search(mlow) or (decorsurvey.hangs(db, mid) or ('',))[0] == 'hung')
                if mtag == 'LIGH' and not hanging_light and not ('candle' in mlow and 'stand' not in mlow and 'candelabra' not in mlow):
                    on_top = False            # (a standing lamp or candle stand: down on the floor)
                # (only something small rides on the main piece, and only the kind of piece it was learnt
                # on: a pillow on a bed, never on a table; a plant in its planter; a candle, a small chest
                # or a basket on a table or a shelf. A chest or a shelf the game had up on a ledge above a
                # table would come out standing on the table: left out)
                if on_top and not hanging_light:
                    allowed = RIDE.get(m['fam'])
                    if allowed is None:
                        allowed = SURFACE_KINDS if max(mb[3] - mb[0], mb[4] - mb[1]) * m.get('s', 1.0) <= 48 else ()
                    if a['fam'] not in allowed:
                        continue
                if m['fam'] in ('chair', 'bench'):
                    # (a seat is laid only with something to sit at: the set piece's own table or counter,
                    # a bed, a bookshelf, a hearth; and it faces the table's middle, whatever the game's
                    # offset turn was for another table: the user's chairs "with their back to the table")
                    near_t = [t for t in tables if max(t['box'][0] - wx, wx - t['box'][2], t['box'][1] - wy, wy - t['box'][3], 0) < 70]
                    if a['fam'] in ('table', 'counter', 'fire', 'shrine'):
                        dvx, dvy = done[0] - wx, done[1] - wy
                        dn = math.hypot(dvx, dvy) or 1.0
                        mrot = _turn_to_face(front_of(db, mid), (dvx / dn, dvy / dn))
                    elif near_t:
                        tb_ = near_t[0]['box']
                        dvx, dvy = (tb_[0] + tb_[2]) / 2 - wx, (tb_[1] + tb_[3]) / 2 - wy
                        dn = math.hypot(dvx, dvy) or 1.0
                        mrot = _turn_to_face(front_of(db, mid), (dvx / dn, dvy / dn))
                    else:
                        # (a seat only at a table, a desk or a counter within reach: the user's "lone chair
                        # standing in the middle of a room facing a bookshelf's side, pointless"; the
                        # reading corner's chair comes when the recipe's table stands by it)
                        continue
                if m['fam'] == 'counter' and purpose not in ('shop', 'tavern', 'kitchen'):
                    continue              # (a bar segment in a living room: "ugly broken desk/counter")
                if not on_top and m['fam'] in ('bookshelf', 'cupboard', 'shelf', 'planter', 'screen'):
                    # (a wall piece of the set piece stands with its back to a wall, as the game had it,
                    # or not at all: the user's "bookshelf by the table in the place a chair would take",
                    # "plants in place of chairs")
                    box_ = _footprint([v * m.get('s', 1.0) for v in mb], mrot, wx, wy)
                    at_wall = wall_behind([v * m.get('s', 1.0) for v in mb], mrot, wx, wy, room, T, front_of(db, mid), reach=30)
                    at_col = m['fam'] == 'planter' and any(abs(cs['x'] - wx) < 60 and abs(cs['y'] - wy) < 60 for cs in col_slots)
                    if not at_wall and not at_col:
                        continue
                if m['fam'] == 'shrine' and purpose != 'shrine' and theme != 'temple':
                    continue
                # (a floor piece the game's set piece had at an odd angle stands square when it comes near
                # a wall: a planter box at 46 degrees with a corner to the wall reads as a block clipped
                # into it)
                if not on_top and m['fam'] in roomsurvey.FLOOR_KINDS + SMALL_KINDS and abs(mrot / (math.pi / 2) - round(mrot / (math.pi / 2))) > 0.05 \
                        and min(wx - inner[0], inner[2] - wx, wy - inner[1], inner[3] - wy) < T * 0.6:
                    mrot = (round(mrot / (math.pi / 2)) * (math.pi / 2)) % (2 * math.pi)
                # (a plant stands in its planter, a pillow on its bed: inside the main piece's own footprint,
                # where the clear-space check would refuse it)
                inside_anchor = abs(m['x']) <= (b[3] - b[0]) / 2 + 4 and abs(m['y']) <= (b[4] - b[1]) / 2 + 4
                box = _footprint([v * m.get('s', 1.0) for v in mb], mrot, wx, wy)
                if m['fam'] == 'counter' and a['fam'] == 'counter':
                    # (the next segment of a counter run: the game's pieces meet or overlap a hair; clear
                    # of everything but the run's own pieces, inside the room)
                    run_boxes = [t['box'] for t in tables]
                    if not inside(box) or any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4
                                               and not any(o[0] is rb for rb in run_boxes)):
                        continue
                elif not inside(box):
                    continue              # (a stool under the table's edge, or up on a dais, still cuts no wall: the user's "chair standing inside the wall")
                if on_top and not hanging_light and not (done[3][0] - 4 <= wx <= done[3][2] + 4 and done[3][1] - 4 <= wy <= done[3][3] + 4):
                    # (a thing that rides on the main piece lands on the main piece as it stands here, in
                    # its own turned footprint: the game's offset from a bed of another make or turn put
                    # two pillows a tile out through the bedroom's wall)
                    continue
                elif not on_top and not inside_anchor and not fits(box):
                    continue
                if m['fam'] == 'table' and any(_overlaps(box, f['box'], -100) for f in fronts if f.get('kind') == 'bed'):
                    continue              # (a set piece's table hard against the bed: the same gap as the recipe's)
                if m['fam'] == 'table' and len([t for t in tables if not t.get('counter')]) >= table_cap:
                    continue              # (a scene's extra table over the room's cap: five tables in a kitchen)
                if m['fam'] in ('chair', 'bench') and a['fam'] in ('table', 'counter') and not on_top:
                    ab_ = approach_box(box, mrot, front_of(db, mid))
                    if any(_overlaps(ab_, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4 and not o[3] and o[0] is not done[3]):
                        continue          # (something already stands where one would sit down: no seat here)
                if m['fam'] in HANGING_KINDS + ('rack',) and not on_top:
                    sh_ = shelf_hang(mid, mb)
                    if sh_ is None:
                        continue
                    if sh_ > 0:
                        at_z = fl + sh_ - mb[2] * m.get('s', 1.0)
                        on_top = True     # (a wall shelf of the set piece hangs at its height, never on the floor)
                at_z = (arec['p'][2] + m['z']) if on_top else None
                if hanging_light:
                    # (a light the game hung by this set piece: hung from this room's ceiling at the height
                    # the game had it, clear of doorways, or not at all; never set down on the floor)
                    up_ = m['z'] * m.get('s', 1.0) + mb[2] * m.get('s', 1.0)
                    if up_ < 110:
                        continue
                    hrec = hang_light(mid, up_, None, wx, wy)
                    if hrec:
                        kinds_laid[m['fam']] += 1
                    continue
                elif on_top:
                    # on a bed (or table) of the house's own palette, not the game's: the surveyed offset is
                    # the other model's, so the pillow floated at the game bed's mattress height over a lower
                    # one (or sank into a higher). The height things stand at on this model, from the game's
                    # own dressings of it (shelfsurvey levels), nearest the example's
                    # (the top one: the mattress, the table's top; the lower ones are the floor inside the
                    # piece's footprint, or a shelf under a table)
                    import shelfsurvey
                    lv_ = shelfsurvey.survey(db, rid).get('levels') or []
                    if lv_:
                        at_z = arec['p'][2] + max(lv_) - mb[2] * m.get('s', 1.0)
                    # (and the main piece's real surface under it, by the mesh: nothing rides on empty
                    # air over a swapped model whose top is elsewhere)
                    if not anchor_mesh:
                        import seethrough
                        anchor_mesh.append(seethrough.overlay(db, [{'op': 'place', 'id': arec['id'], 'p': list(arec['p']), 's': arec.get('s', 1.0)}]))
                    if anchor_mesh[0].tris:
                        hit_ = anchor_mesh[0].nearest((wx, wy, at_z + mb[2] * m.get('s', 1.0) + 20), (0.0, 0.0, -1.0), 60)
                        if hit_ is None or hit_[0] > 20 + 14:
                            continue
                mrec = put(mid, wx, wy, mrot, on_top=on_top, floor=fl, room=room['name'], scale=m.get('s', 1.0), at_z=at_z)
                if mrec is None:
                    continue
                if not on_top and not inside_anchor:
                    taken.append((box, fl, fl + 200, False))
                if m['fam'] in ('chair', 'bench') and a['fam'] in ('table', 'counter'):
                    keep_approach(box, mrec['p'][5], front_of(db, mid))
                got.append(mid)
                kinds_laid[m['fam']] += 1
                mlaid = dress(mrec, purpose) if m['fam'] in DRESSED_KINDS else None
                if m['fam'] == 'fire':
                    got.extend(dress_hearth(mrec, purpose))
                if m['fam'] in ('table', 'counter'):
                    tables.append({'box': box, 'items': [], 'dressed': bool(mlaid), 'counter': m['fam'] == 'counter'})
                if m['fam'] in ('bed', 'shrine', 'counter'):
                    fronts.append({'box': box, 'in': face or (0, -1), 'kind': m['fam']})
            if run_laid:
                taken.append(run_laid['front'])      # (the customer side stays clear, the scene's stools in)
            return kinds_laid

        import arrangesurvey
        if piece is not None:
            # one piece, dressed the way the game dresses its model, by the same paths as a whole house:
            # the shelf dressings for furniture, the plant for a planter, the hearth's pots and firewood,
            # the shrine's statue, candles and offerings. The user: "If I right click a bookshelf and
            # choose auto-furnish, it will populate a bookshelf, maybe doing it again clears it and does
            # a new arrangement"
            prec = dict(piece_rec)
            prec['room'] = room['name']
            fam_ = roomsurvey.family_of(db, prec['id'], prec['type'])
            got_ = []
            if add:
                # (one more thing on it, everything on it kept)
                res_ = add_one(prec, purpose)
                piece_out = dict(res_, model=prec['id'], kind=fam_, room=room['name'])
                report.append({'room': room['name'], 'purpose': purpose, 'placed': res_['placed']})
                break
            if fam_ == 'planter':
                p_ = plant_in(prec, prec['p'][0], prec['p'][1], prec['p'][5])
                got_ = [p_['id']] if p_ else []
            elif fam_ == 'fire':
                got_ = dress_hearth(prec, purpose)
            elif fam_ == 'shrine':
                import shrinesurvey
                got_ = dress_shrine(prec, shrinesurvey.composition(db, prec['id'], rng))
            else:
                d_ = dress(prec, purpose)
                got_ = [o['id'] for o in (d_ or [])]
            piece_out = {'placed': len(got_), 'model': prec['id'], 'kind': fam_, 'room': room['name']}
            report.append({'room': room['name'], 'purpose': purpose, 'placed': len(got_)})
            break
        # the game's own set pieces first: a bar, a shrine with its bench, planters along a wall, a dining
        # set, a reading corner, laid the way the game lays them (arrangesurvey.py), then the recipe
        # fills in what such rooms hold besides, less what the set pieces stood already
        pre = Counter()
        picks = []
        import arrangesurvey
        if ARRANGE and not walls_only:
            # (a trade's own set piece, a smith's forge or an apothecary's bench, goes in the first room
            # that could hold it: not a bedroom, a store or a corridor)
            want = tuple(extras_left) if purpose in ('living', 'shop', 'study', 'kitchen', 'tavern', 'shrine') else ()
            picks = arrangesurvey.pick(db, purpose, theme, rng, room['tiles'], want=want, like=like_scenes)

        import roomrules as _rr
        table_cap = _rr.TABLE_CAP.get(purpose, 3)

        def lay_pending():
            while picks:
                ex = picks.pop(0)
                # (no bed outside a bedroom, whatever set piece brings it: a kitchen got a bed)
                laid_kinds = lay_arrangement(ex, skip=() if purpose in ('bedroom', 'barracks') else ('bed',))
                pre.update(laid_kinds)
                last_arrangements.append({'room': room['name'], 'purpose': purpose, 'cell': ex['cell'],
                                          'sig': '+'.join(sorted(m['fam'] for m in ex['members'])), 'laid': dict(laid_kinds)})
        # the room's essential piece (a bedroom's bed, a shop's counter, a shrine's altar) goes first,
        # before set pieces that don't bring it take the wall slots; set pieces that do bring it go first
        ess = ESSENTIAL.get(purpose)
        if not ess or any(m['fam'] == ess for ex in picks for m in ex['members']):
            lay_pending()
        # (floor clutter goes in groups after the furniture, the way the game stands it, once surveyed;
        # before that, in groups of the game's usual sizes, so a storeroom isn't limited to one piece a
        # wall tile: the game packs 38 pieces into nine tiles of store)
        cs = roomrules.clusters(db) or DEFAULT_CLUSTERS
        clutter = []
        if walls_only:
            recipe_rows = []
        elif purpose in roomrules.KIND_PURPOSES:
            recipe_rows = roomrules.kind_recipe(db, purpose, RECIPES[purpose], culture=STYLE_SET.get(cell_style) or fam.get('_borrowed'),
                                                tiles=room['tiles'], style=style)
        else:
            recipe_rows = roomrules.recipe(db, purpose, RECIPES[purpose], theme=theme, like=like_rooms)
        for kind, count, where in recipe_rows:
            if picks and kind != ess:
                lay_pending()
            # (a big room gets more of most things, not more beds, shrines or counters)
            if isinstance(count, float):
                # the game's rate per nine tiles (roomrules.recipe), scaled by this room's floor and
                # rounded by chance: a kind the game has in one such room in five comes one time in five,
                # and the room ends up as full as the game's, not as full as the commonest few kinds make it
                e = count * area_f
                n = int(e) + (1 if rng.random() < e - int(e) else 0)
                if kind == ess or (kind == 'table' and purpose in ('living', 'study', 'kitchen', 'tavern', 'shop') and not tables) \
                        or (kind == 'bench' and purpose == 'hall' and room['tiles'] * (T / 256.0) ** 2 >= 3):
                    n = max(1, n)            # (a dining room gets its table, a shop its counter, a hall its bench, whatever the dice)
                if kind == 'bed' and n > 1 and room['tiles'] * (T / 256.0) ** 2 < 6:
                    n = 1                    # (a second bed only where there is floor for two)
            else:
                n = count if where in ('centre', 'on_table', 'long') or kind in ('rug', 'bed', 'shrine', 'counter', 'chest') else max(1, int(round(count * area_k)))
                if purpose == 'barracks' and kind in ('bed', 'chest'):
                    n = max(2, int(round(count * area_k)))     # (a barracks' bunks and their chests come by the room's size)
            if L and L['density'] != 1.0 and kind not in ('bed', 'shrine', 'counter', 'rug') and where != 'centre':
                # (a poor house holds fewer things than the game's middling ones, a rich one more:
                # the surveyed band's pieces per nine tiles over the comfortable band's)
                nf = n * L['density']
                n = int(nf) + (1 if rng.random() < nf - int(nf) else 0)
                if n <= 0:
                    continue
            if pre.get(kind):
                take = min(n, pre[kind])
                pre[kind] -= take
                n -= take
                if n <= 0:
                    continue
            if kind == 'chest' and where in ('wall', 'corner') and any(f.get('kind') == 'bed' for f in fronts):
                where = 'by_bed'                  # (a bedroom's chest goes to the foot of the bed, not into the clutter groups)
            if cs and kind in roomsurvey.CLUTTER and where in ('wall', 'corner'):
                if kind == 'chest':
                    last_trace.append((room['name'], kind, 'to the clutter groups', [f.get('kind') for f in fronts]))
                clutter += [kind] * n
                continue
            if clutter and purpose in ('storage', 'kitchen', 'armoury') and kind not in roomsurvey.CLUTTER \
                    and not (purpose == 'kitchen' and kind in ('fire', 'table', 'cupboard')):
                # (a kitchen's hearth, bench table and dresser take their walls before the stores do:
                # the stores took every slot and the hearth found "no spot"; the catalogue's R3)
                # (a store's stores take the walls before its shelf and its chest do, not after: the
                # crates and sacks found no wall left and the room stood half empty)
                if rng.random() > cs.get('mixed', 0.3):
                    clutter.sort()
                groups += place_clutter(clutter, cs)
                clutter = []
            left = n
            while left > 0:
                left -= 1
                if kind == 'rug':
                    got_rug = place_rug(where, big_rugs if where not in ('by_bed', 'rug') else all_rugs)
                    if got_rug:
                        rug, (x, y, rot, box) = got_rug
                        if put(rug[0], x, y, rot, floor=fl, flat=True, room=room['name']):
                            rugs.append((box, fl))
                            got.append(rug[0])
                    continue
                # the game decorates in scenes, not items: a table with its chairs and what stands by it,
                # a bed with its pillows and the shelf over its head, a planter with its plant, a work
                # corner of shelf, barrel and basket (arrangesurvey.scene). A piece of a kind the game
                # stands with company is laid as such a scene, at the game's own offsets, and the
                # companions count against the recipe's own; a lone piece is the exception, as often as
                # the game's own pieces stand alone
                if SCENES and kind in SCENE_KINDS and where in ('wall', 'corner', 'centre') and purpose != 'dining':
                    # (a dining room is laid by its own rule, R2, not by the game's small sets)
                    ex = arrangesurvey.scene(db, kind, purpose, theme, rng, like=like_scenes)
                    if ex:
                        laid = lay_arrangement(ex, where=where, skip=('chest', 'bed') if kind == 'bed' else ('bed',))
                        if laid.get(kind):
                            last_arrangements.append({'room': room['name'], 'purpose': purpose, 'cell': ex['cell'], 'for': kind,
                                                      'sig': '+'.join(sorted(m['fam'] for m in ex['members'])), 'laid': dict(laid)})
                            laid[kind] -= 1
                            left -= laid.pop(kind)       # (a scene that brought two of the kind)
                            pre.update(laid)
                            continue
                rid = pick(kind)
                if not rid:
                    last_trace.append((room['name'], kind, 'nothing of the kind in the palette'))
                    break                    # (none of this kind: the next of the count won't do better)
                ri = db.resolve_id(rid)
                b = mapdata.object_bounds(db, ri)
                if not b:
                    last_trace.append((room['name'], kind, rid, 'no bounds'))
                    continue
                front = front_of(db, rid)
                done = None
                face = None
                if kind == 'chest' and where in ('wall', 'corner') and any(f.get('kind') == 'bed' for f in fronts):
                    where = 'by_bed'              # (the surveyed recipe files a bedroom's chest under "wall")
                # where the game stands this kind (placesurvey.prefs): a table at the wall as often as the
                # game's tables are, a cupboard in a corner as often as its cupboards
                pp = placesurvey.prefs(db, kind, purpose)
                if kind == 'fire':
                    where = 'centre' if 'pit' in rid.lower() else 'wall'      # (a Dunmer firepit mid-room, a fireplace at the wall)
                elif where == 'centre' and pp and rng.random() < pp['at'].get('wall', 0):
                    where = 'wall'
                elif where == 'wall' and pp and rng.random() < pp.get('corner', 0):
                    where = 'corner'
                # (Hlaalu's shops stand their shelves of pots and jars out from the walls as room dividers:
                # catalogue rule 6, at the style's own rate)
                dv = catalogue.rule(db, 'dividers', cell_style) if kind == 'shelf' and where in ('wall', 'corner') else None
                if dv and dv.get('own') and (dv.get('share') or 0) >= 0.15 and rng.random() < dv['share']:
                    done, face = divider_spot(b, front)
                    if done:
                        where = 'divider'
                if where == 'by_bed':
                    # across the foot of the bed, its front away from the bed (the game: chests by beds
                    # stand across the bed's line 441 times to 167 along it, and face away 322 to 147; the
                    # user: "a large chest at 90 degrees facing outwards, if any chest is used at all"), a
                    # big one when the palette has one; failing that, by a wall like anything else
                    beds = [f for f in fronts if f.get('kind') == 'bed']
                    if beds and kind == 'chest':
                        import decorsurvey
                        big = [r_ for r_ in (fam.get('chest') or [])[:12] if not decorsurvey.off_floor(db, r_)
                               for bb in [mapdata.object_bounds(db, db.resolve_id(r_))] if bb and max(bb[3] - bb[0], bb[4] - bb[1]) >= 90]
                        if big:
                            rid = big[0]
                            ri = db.resolve_id(rid)
                            b = mapdata.object_bounds(db, ri)
                            front = front_of(db, rid)
                    if beds:
                        fb = beds[-1]['box']
                        bw, bh = fb[2] - fb[0], fb[3] - fb[1]
                        mx, my = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
                        long_x = bw >= bh
                        gap = 10
                        # the two short ends, the one away from the wall first (the bed's head is at the wall)
                        inx, iny = beds[-1].get('in') or (0, -1)
                        ends = ([((1, 0), (fb[2], my)), ((-1, 0), (fb[0], my))] if long_x else
                                [((0, 1), (mx, fb[3])), ((0, -1), (mx, fb[1]))])
                        ends.sort(key=lambda e: -(e[0][0] * inx + e[0][1] * iny))
                        for (ox_, oy_), (ex_, ey_) in ends:
                            rot = _turn_to_face(front, (ox_, oy_))             # (its front away from the bed)
                            box0 = _footprint(b, rot, 0, 0)
                            depth = {(1, 0): -box0[0], (-1, 0): box0[2], (0, 1): -box0[1], (0, -1): box0[3]}[(ox_, oy_)]
                            x, y = ex_ + ox_ * (depth + gap), ey_ + oy_ * (depth + gap)
                            box = _footprint(b, rot, x, y)
                            if fits(box):
                                done = (x, y, rot, box)
                                face = (ox_, oy_)
                                break
                    if not done:
                        where = 'wall'
                if kind == 'counter':
                    if purpose not in ('shop', 'tavern', 'kitchen'):
                        continue          # (the living rooms' recipe a hall borrows has the odd bar: none here)
                    if any(t.get('counter') for t in tables):
                        continue
                    # (the recipe's counter, when no scene brought one: one of the game's runs, whole;
                    # never a lone segment in a shop or a tavern, "a barely started shop counter")
                    run_ = lay_counter_run(pp, dress)
                    if run_:
                        got.extend(run_['ids'])
                        taken.append(run_['front'])
                    if run_ or purpose != 'kitchen':
                        continue
                if purpose == 'kitchen' and kind == 'table' and not tables:
                    # (a kitchen's first table is the long bench table along the wall, the game's
                    # counter-as-furniture: Hasi Manor's, Thimistrel Manor's and the Legion boarding
                    # house's kitchens keep a 156 to 178 table with its back to the wall; the catalogue's R3)
                    where = 'wall'
                    longs_ = []
                    for tid_ in (fam.get('table') or [])[:16]:
                        tb_ = mapdata.object_bounds(db, db.resolve_id(tid_))
                        if tb_ and max(tb_[3] - tb_[0], tb_[4] - tb_[1]) >= 150:
                            longs_.append(tid_)
                    if longs_:
                        rid = rng.choice(longs_[:4])
                        ri = db.resolve_id(rid)
                        b = mapdata.object_bounds(db, ri)
                        front = front_of(db, rid)
                if where == 'long' and kind == 'table':
                    # the dining room's long table (catalogue R2): the longest table model, two of them end to
                    # end along the room (one in a small room), the whole nearest the hearth when there is one
                    cands_ = []
                    for tid in fam.get('table') or []:
                        tb_ = mapdata.object_bounds(db, db.resolve_id(tid))
                        if tb_:
                            cands_.append((max(tb_[3] - tb_[0], tb_[4] - tb_[1]) / max(1.0, min(tb_[3] - tb_[0], tb_[4] - tb_[1])), max(tb_[3] - tb_[0], tb_[4] - tb_[1]), tid, tb_))
                    longs = [c_ for c_ in cands_ if c_[0] >= 1.5 and c_[1] >= 140] or sorted(cands_, key=lambda c_: -c_[1])[:1]
                    if not longs:
                        last_trace.append((room['name'], kind, '-', 'no long table in the palette'))
                        continue
                    longs.sort(key=lambda c_: -c_[1])
                    ratio_, tlen_, tid, tb_ = longs[0]
                    rid = tid
                    b = tb_
                    long_x = (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min'])
                    model_long_x = (tb_[3] - tb_[0]) >= (tb_[4] - tb_[1])
                    rot = 0.0 if long_x == model_long_x else math.pi / 2
                    seg = tlen_ + 2
                    n_seg = 2 if room['tiles'] * (T / 256.0) ** 2 >= 6 else 1
                    hearths_ = [p for p in placed if p.get('room') == room['name'] and roomsurvey.family_of(db, p['id'], p['type']) == 'fire']
                    centres = [(cx + dx, cy + dy) for dx, dy in ((0, 0), (64, 0), (-64, 0), (0, 64), (0, -64), (128, 0), (-128, 0), (0, 128), (0, -128))]
                    if hearths_:
                        hx_, hy_ = hearths_[0]['p'][0], hearths_[0]['p'][1]
                        centres.sort(key=lambda c_: math.hypot(c_[0] - hx_, c_[1] - hy_))
                    laid_ = None
                    hearth_box = _footprint([v * (hearths_[0].get('s') or 1.0) for v in hearths_[0]['b']], hearths_[0]['p'][5], hearths_[0]['p'][0], hearths_[0]['p'][1]) if hearths_ else None
                    for mx_, my_ in centres:
                        segs_ = []
                        for i_ in range(n_seg):
                            off = (i_ - (n_seg - 1) / 2.0) * seg
                            sx_, sy_ = (mx_ + off, my_) if long_x else (mx_, my_ + off)
                            segs_.append((sx_, sy_, _footprint(b, rot, sx_, sy_)))
                        if not all(fits(bx_) for _x, _y, bx_ in segs_):
                            continue
                        if hearth_box is not None:
                            # (by the hearth, but with both long sides free for the chairs: the hearth at the
                            # table's end, never along its side)
                            U = (min(bx_[0] for _x, _y, bx_ in segs_), min(bx_[1] for _x, _y, bx_ in segs_), max(bx_[2] for _x, _y, bx_ in segs_), max(bx_[3] for _x, _y, bx_ in segs_))
                            strips = ((U[0], U[3], U[2], U[3] + 90), (U[0], U[1] - 90, U[2], U[1])) if long_x else ((U[2], U[1], U[2] + 90, U[3]), (U[0] - 90, U[1], U[0], U[3]))
                            if any(_overlaps(st_, hearth_box, 0) for st_ in strips):
                                continue
                        laid_ = segs_
                        break
                    if laid_ is None and n_seg == 2:
                        n_seg = 1
                        for mx_, my_ in centres:
                            bx_ = _footprint(b, rot, mx_, my_)
                            if fits(bx_):
                                laid_ = [(mx_, my_, bx_)]
                                break
                    if laid_ is None:
                        last_trace.append((room['name'], kind, rid, 'no room for the long table'))
                        continue
                    recs_ = []
                    for sx_, sy_, bx_ in laid_:
                        r_ = put(rid, sx_, sy_, rot, floor=fl, room=room['name'])
                        if r_:
                            taken.append((bx_, fl, fl + 200, False))
                            got.append(rid)
                            recs_.append((r_, bx_))
                    if not recs_:
                        continue
                    for r_, bx_ in recs_:
                        laid_d = dress(r_, purpose)
                        tables.append({'box': bx_, 'items': [], 'dressed': bool(laid_d), 'counter': False})
                    long_box[0] = (min(bx_[0] for _r, bx_ in recs_), min(bx_[1] for _r, bx_ in recs_), max(bx_[2] for _r, bx_ in recs_), max(bx_[3] for _r, bx_ in recs_))
                    last_trace.append((room['name'], 'table', rid, 'a long table of %d (%.0f long)%s' % (len(recs_), long_box[0][2] - long_box[0][0] if long_x else long_box[0][3] - long_box[0][1], ', by the hearth' if hearths_ else '')))
                    continue
                if where == 'both_sides' and kind == 'chair':
                    # chairs down both long sides of the long table (R2: "chairs down both sides"), evenly
                    # spaced, each facing the table, each with its approach clear
                    LB = long_box[0] or (tables[-1]['box'] if tables else None)
                    if not LB:
                        continue
                    lx_ = (LB[2] - LB[0]) >= (LB[3] - LB[1])
                    length_ = (LB[2] - LB[0]) if lx_ else (LB[3] - LB[1])
                    per_side = max(1, int(length_ // 80))
                    n_chairs = 0
                    for i_ in range(per_side):
                        along_ = (LB[0] if lx_ else LB[1]) + (i_ + 0.5) * length_ / per_side
                        for sgn_ in (1, -1):
                            if n_chairs >= n:
                                break
                            if lx_:
                                x_, y_, face = along_, (LB[3] + 30 if sgn_ > 0 else LB[1] - 30), (0, -sgn_)
                            else:
                                x_, y_, face = (LB[2] + 30 if sgn_ > 0 else LB[0] - 30), along_, (-sgn_, 0)
                            rot = _turn_to_face(front, face)
                            box = _footprint(b, rot, x_ - face[0] * 10, y_ - face[1] * 10)
                            # (a chair down a long table's side may stand with its back near the wall, as the
                            # manor's do: its approach is the gap it slides out into, not a half tile)
                            if fits(box):
                                r_ = put(rid, x_ - face[0] * 10, y_ - face[1] * 10, rot, floor=fl, room=room['name'])
                                if r_:
                                    taken.append((box, fl, fl + 200, False))
                                    got.append(rid)
                                    n_chairs += 1
                    last_trace.append((room['name'], 'chair', rid, '%d chairs down both sides' % n_chairs))
                    left = 0
                    continue
                if where in ('wall', 'corner'):
                    done, face = wall_spot(b, front, where, pp=pp, kind=kind, gap=KEEPER_GAP if kind == 'counter' else 2)
                elif where == 'centre':
                    long_x = (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min'])
                    rot = 0.0 if long_x else math.pi / 2
                    rot = _turn_to_face(front, (0, -1)) if front else rot
                    face = (0, -1)
                    spots = ((0, 0), (64, 0), (-64, 0), (0, 64), (0, -64), (128, 128), (-128, -128))
                    if kind == 'table' and tables:
                        # a second table stands well apart from the first, along the room (two tables end
                        # to end or either side of a column read as one table doubled, the user's "doubled
                        # up" tables); with no such spot the room keeps the one table
                        spots = tuple((d, 0) if long_x else (0, d) for d in (384, -384, 320, -320, 256, -256))
                    # (and a table keeps its distance from a bed: the game's median gap is 151; the user's
                    # "the table is uncomfortably close to that bed")
                    bedboxes = [f['box'] for f in fronts if f.get('kind') == 'bed']
                    for dx, dy in spots:
                        box = _footprint(b, rot, cx + dx, cy + dy)
                        if fits(box) and (kind != 'table' or not any(_overlaps(box, t['box'], -160) for t in tables)) and \
                                not (kind == 'table' and any(_overlaps(box, fb_, -100) for fb_ in bedboxes)):
                            done = (cx + dx, cy + dy, rot, box)
                            break
                elif where == 'by_table' and tables:
                    t = tables[len(got) % len(tables)]
                    tb = t['box']
                    sides = [((tb[0] + tb[2]) / 2, tb[3] + 30, (0, -1)), ((tb[0] + tb[2]) / 2, tb[1] - 30, (0, 1)),
                             (tb[2] + 30, (tb[1] + tb[3]) / 2, (-1, 0)), (tb[0] - 30, (tb[1] + tb[3]) / 2, (1, 0))]
                    rng.shuffle(sides)
                    for x, y, face in sides:
                        rot = _turn_to_face(front, face)
                        box = _footprint(b, rot, x + (-face[0]) * 10, y + (-face[1]) * 10)
                        if fits(box) and keep_approach(box, rot, front):
                            done = (x + (-face[0]) * 10, y + (-face[1]) * 10, rot, box)
                            break
                elif where == 'on_table' and tables:
                    # (a table set out the game's way is laid already; the scatter is for the others)
                    bare = [t for t in tables if not t.get('dressed')]
                    if not bare:
                        continue
                    t = rng.choice(bare)
                    tb = t['box']
                    for _try in range(8):
                        x = rng.uniform(tb[0] + 15, tb[2] - 15)
                        y = rng.uniform(tb[1] + 15, tb[3] - 15)
                        box = _footprint(b, 0, x, y)
                        if not any(_overlaps(box, o, 0) for o in t['items']):
                            done = (x, y, rng.uniform(0, 2 * math.pi), None)
                            t['items'].append(box)
                            break
                if not done:
                    last_trace.append((room['name'], kind, rid, 'no spot (%s), %d slots left' % (where, len(slots))))
                    continue
                if kind == 'table' and done[3] is not None and any(_overlaps(done[3], f['box'], -100) for f in fronts if f.get('kind') == 'bed'):
                    last_trace.append((room['name'], kind, rid, 'too close to the bed (%s)' % where))
                    continue                  # (a table by the wall hard against the bed, as much as one mid-room)
                # (only wall shelves hang on the wall: a chest or a crate the game keeps up on a shelf or a
                # table stands on the floor here)
                hang = shelf_hang(rid, b) if where in ('wall', 'corner', 'divider') and kind in HANGING_KINDS else 0.0
                if hang is None:
                    last_trace.append((room['name'], kind, rid, 'a wall shelf with no known hanging height: left out'))
                    continue
                if hang and where == 'divider':
                    last_trace.append((room['name'], kind, rid, 'a wall shelf stands out from no wall: no divider'))
                    continue              # (a room divider is a standing shelf; a hung one would float in the air)
                shrine_comp = None
                if kind == 'shrine':
                    shrine_comp, ok_ = shrine_ok(rid)
                    if not ok_:
                        last_trace.append((room['name'], kind, rid, 'the game never stands this model, or never without its statue: left out'))
                        continue
                rec = put(rid, done[0], done[1], done[2], on_top=(where == 'on_table'),
                          hang_from=(fl + hang) if hang > 0 else None, floor=fl, room=room['name'],
                          ledge=ledge_h if where in ('wall', 'corner', 'divider') and kind in catalogue.LEDGE_KINDS else None)
                if rec is None:
                    last_trace.append((room['name'], kind, rid, 'put refused it (no floor there, or over the band\'s cap)'))
                    continue
                if done[3] is not None:
                    taken.append((done[3], fl, fl + 200, False))
                got.append(rid)
                if purpose == 'entry' and entry_axis is not None and kind in MIRROR_KINDS and done[3] is not None:
                    # the entrance hall is symmetrical (catalogue R1, Vinicius Manor's entry: a bench either side
                    # of the door, a candle stand at each end, a planter either side of the stair foot): what
                    # stands on one side of the door's axis stands mirrored on the other
                    mm_ = entry_mirror(b, front, done[0], done[1], done[2], kind)
                    if mm_ is not None:
                        mxx, myy, mrot_, mbox_ = mm_
                        hang_m = (fl + hang) if hang > 0 else None
                        if True:
                            mrec = put(rid, mxx, myy, mrot_, hang_from=hang_m, floor=fl, room=room['name'], ledge=ledge_h if kind in catalogue.LEDGE_KINDS else None)
                            if mrec:
                                taken.append((mbox_, fl, fl + 200, False))
                                got.append(rid)
                                # (the mirrored slot is used up: the wall slot nearest it)
                                near_sl = [sl for sl in slots if abs(sl['x'] - mxx) < T * 0.5 and abs(sl['y'] - myy) < T * 0.5]
                                for sl in near_sl[:1]:
                                    slots.remove(sl)
                                last_trace.append((room['name'], kind, rid, 'mirrored across the door\'s axis'))
                                if kind == 'planter':
                                    prec2 = plant_in(mrec, mxx, myy, mrot_)
                                    if prec2:
                                        got.append(prec2['id'])
                if kind == 'planter':
                    # (a plant in it, as often as the game's planters hold one: catalogue rule 3; never a
                    # plant loose on the floor)
                    prec = plant_in(rec, done[0], done[1], done[2])
                    if prec:
                        got.append(prec['id'])
                # what stands on it, the way the game sets out this very model (books packed along a
                # bookshelf, dishes and a candle on a table, wares on a counter)
                laid = dress(rec, purpose) if kind in DRESSED_KINDS else None
                if kind == 'fire':
                    got.extend(dress_hearth(rec, purpose))      # (the pot on the fire, the firewood by it)
                if kind == 'shrine':
                    got.extend(dress_shrine(rec, shrine_comp))  # (the statue on the altar, the candles, the offerings)
                if kind in ('table', 'counter'):
                    tables.append({'box': done[3], 'items': [], 'dressed': bool(laid), 'counter': kind == 'counter'})
                if kind in ('bed', 'shrine', 'counter') and done[3] is not None and face:
                    fronts.append({'box': done[3], 'in': face, 'kind': kind})
        if picks:
            lay_pending()                        # (a recipe with nothing after the essential piece)
        # what rides on the stores, the way the game tops them (room-kind survey R3): a small crate, a
        # sack, a bowl or a travel lantern on one crate in two, a sack on a sack one in four, the odd thing
        # on a barrel or a chest; and a kitchen's hearth gets its cookery and its logs (R4)
        if not walls_only:
            import roomkindsurvey
            RK = roomkindsurvey.ready(db)
            KK = (RK or {}).get('kinds', {}).get(roomrules.KIND_OF.get(purpose, 'storage'), {}).get('*') if RK else None
            if KK and purpose in ('storage', 'kitchen', 'armoury', 'landing', 'entry', 'training'):
                tops_done = 0
                for srec in [p for p in placed if p.get('room') == room['name'] and roomsurvey.family_of(db, p['id'], p['type']) in ('crate', 'sack', 'barrel', 'chest')]:
                    sfam = roomsurvey.family_of(db, srec['id'], srec['type'])
                    if rng.random() >= (KK.get('topped') or {}).get(sfam, 0.0):
                        continue
                    pool_ = [i for i, _n in (KK.get('top_ids') or {}).get(sfam, []) if db.resolve_id(i) is not None]
                    if not pool_:
                        continue
                    sb = _footprint([v * (srec.get('s') or 1.0) for v in srec['b']], srec['p'][5], srec['p'][0], srec['p'][1])
                    for _try in range(4):
                        tid = rng.choice(pool_)
                        tb = mapdata.object_bounds(db, db.resolve_id(tid))
                        if not tb or max(tb[3] - tb[0], tb[4] - tb[1]) > min(sb[2] - sb[0], sb[3] - sb[1]) + 10:
                            continue      # (nothing wider than the top it rides on)
                        tx_ = rng.uniform(sb[0] + (tb[3] - tb[0]) / 2, sb[2] - (tb[3] - tb[0]) / 2) if sb[2] - sb[0] > tb[3] - tb[0] else (sb[0] + sb[2]) / 2
                        ty_ = rng.uniform(sb[1] + (tb[4] - tb[1]) / 2, sb[3] - (tb[4] - tb[1]) / 2) if sb[3] - sb[1] > tb[4] - tb[1] else (sb[1] + sb[3]) / 2
                        top_ = surface_on(srec, tx_, ty_)
                        if top_ is None:
                            continue
                        trot = rng.choice((0.0, math.pi / 2, math.pi, 3 * math.pi / 2)) if db.recs[db.resolve_id(tid)][0] in ('CONT', 'STAT') else rng.uniform(0, 2 * math.pi)
                        trec = put(tid, tx_, ty_, trot, on_top=True, at_z=top_ - tb[2], room=room['name'])
                        if trec:
                            got.append(tid)
                            tops_done += 1
                        break
                if tops_done:
                    last_trace.append((room['name'], 'tops', '-', '%d things on the stores' % tops_done))
            if purpose == 'kitchen':
                # the bread paddle, laid flat on the kitchen's table (the catalogue's R3: the Anvil kitchen's
                # paddle on the trestle; the North Wall bakery's and Hasi Manor's lie flat on the table top)
                pads_ = [i for i in ('T_Com_Breadpaddle_01b', 'T_Com_Breadpaddle_02b', 'T_Com_Breadpaddle_01a', 'T_Com_Breadpaddle_02a') if db.resolve_id(i) is not None]
                ktabs_ = [p for p in placed if p.get('room') == room['name'] and roomsurvey.family_of(db, p['id'], p['type']) == 'table']
                if pads_ and ktabs_ and not any('breadpaddle' in p['id'].lower() for p in placed if p.get('room') == room['name']):
                    trec_ = max(ktabs_, key=lambda p: max(p['b'][3] - p['b'][0], p['b'][4] - p['b'][1]) * (p.get('s') or 1.0))
                    tbx_ = _footprint([v * (trec_.get('s') or 1.0) for v in trec_['b']], trec_['p'][5], trec_['p'][0], trec_['p'][1])
                    pid_ = rng.choice(pads_)
                    pb_ = mapdata.object_bounds(db, db.resolve_id(pid_))
                    along_x = (tbx_[2] - tbx_[0]) >= (tbx_[3] - tbx_[1])
                    if pb_:
                        prot_ = 0.0 if ((pb_[3] - pb_[0]) >= (pb_[4] - pb_[1])) == along_x else math.pi / 2
                        for _try in range(5):
                            px_ = rng.uniform(tbx_[0] + 30, tbx_[2] - 30)
                            py_ = rng.uniform(tbx_[1] + 20, tbx_[3] - 20)
                            pbox_ = _footprint(pb_, prot_, px_, py_)
                            if pbox_[0] < tbx_[0] - 20 or pbox_[2] > tbx_[2] + 20 or pbox_[1] < tbx_[1] - 10 or pbox_[3] > tbx_[3] + 10:
                                continue           # (a paddle may hang a little over the table's end, no more)
                            top_ = surface_on(trec_, px_, py_)
                            if top_ is None:
                                continue
                            prec_ = put(pid_, px_, py_, prot_, on_top=True, at_z=top_ - pb_[2], room=room['name'])
                            if prec_:
                                got.append(pid_)
                                last_trace.append((room['name'], 'paddle', pid_, 'flat on the table'))
                                break
            if purpose == 'kitchen' and KK:
                hearths_ = [p for p in placed if p.get('room') == room['name'] and roomsurvey.family_of(db, p['id'], p['type']) == 'fire']
                cooks_ = [p for p in placed if p.get('room') == room['name'] and roomkindsurvey.mark_of(p) == 'cook']
                if hearths_ and not cooks_:
                    hrec_ = hearths_[0]
                    pool_ = [i for i, _n in KK.get('cook_ids') or [] if db.resolve_id(i) is not None
                             and re.search(r'pan_|pot|kettle|cauldron|skillet|teapot|cook', i) and not re.search(r'flute|music|instrument|potion|flower|plant', i)]
                    hb = _footprint([v * (hrec_.get('s') or 1.0) for v in hrec_['b']], hrec_['p'][5], hrec_['p'][0], hrec_['p'][1])
                    for _try in range(6):
                        if not pool_:
                            break
                        cid = rng.choice(pool_)
                        cb = mapdata.object_bounds(db, db.resolve_id(cid))
                        if not cb:
                            continue
                        # (on the hearth where it has a surface, else on the floor beside it)
                        cx_, cy_ = (hb[0] + hb[2]) / 2 + rng.uniform(-20, 20), (hb[1] + hb[3]) / 2 + rng.uniform(-20, 20)
                        top_ = surface_on(hrec_, cx_, cy_)
                        crec = None
                        if top_ is not None and top_ - fl < 120:
                            if not inside(_footprint(cb, 0, cx_, cy_)):
                                continue      # (a cauldron on the hearth's top reached into the wall behind it)
                            crec = put(cid, cx_, cy_, 0.0, on_top=True, at_z=top_ - cb[2], room=room['name'])   # (the turn its box was checked at)
                        else:
                            side_ = rng.choice(((hb[2] + 30, (hb[1] + hb[3]) / 2), (hb[0] - 30, (hb[1] + hb[3]) / 2), ((hb[0] + hb[2]) / 2, hb[3] + 30), ((hb[0] + hb[2]) / 2, hb[1] - 30)))
                            crot = rng.choice((0.0, math.pi / 2, math.pi, 3 * math.pi / 2))
                            cbox = _footprint(cb, crot, side_[0], side_[1])
                            if not fits(cbox):
                                continue
                            crec = put(cid, side_[0], side_[1], crot, floor=fl, room=room['name'])   # (the turn the box was checked at)
                            if crec:
                                taken.append((cbox, fl, fl + 100, False))
                        if crec:
                            got.append(cid)
                            last_trace.append((room['name'], 'cookery', cid, 'on or by the hearth'))
                            break
                    # (three or four logs in the corner next to the hearth: firewood 0.5 per nine tiles, 40% in a corner)
                    logs_ = [i for i in ('furn_log_01', 'furn_log_03', 'furn_log_04', 'furn_log_02') if db.resolve_id(i) is not None]
                    if logs_ and not any(roomkindsurvey.mark_of(p) == 'firewood' for p in placed if p.get('room') == room['name']):
                        lb = mapdata.object_bounds(db, db.resolve_id(logs_[0]))
                        for side_ in ((hb[2] + 40, (hb[1] + hb[3]) / 2), (hb[0] - 40, (hb[1] + hb[3]) / 2)):
                            n_logs = 0
                            for k_ in range(rng.choice((3, 4))):
                                lx_, ly_ = side_[0] + rng.uniform(-18, 18), side_[1] + rng.uniform(-18, 18)
                                lrot = rng.uniform(0, 2 * math.pi)
                                lid_ = rng.choice(logs_)
                                lb = mapdata.object_bounds(db, db.resolve_id(lid_)) or lb
                                lbox = _footprint(lb, lrot, lx_, ly_)
                                if not inside(lbox) or any(_overlaps(lbox, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4 and o[3]):
                                    break
                                lrec = put(lid_, lx_, ly_, lrot, floor=fl, room=room['name'])
                                if lrec:
                                    got.append(lrec['id'])
                                    n_logs += 1
                            if n_logs:
                                taken.append(((side_[0] - 40, side_[1] - 40, side_[0] + 40, side_[1] + 40), fl, fl + 60, False))
                                last_trace.append((room['name'], 'firewood', logs_[0], '%d logs by the hearth' % n_logs))
                                break
        # every seat in the room faces the table it stands at: a reading chair laid before the recipe's
        # table came beside it was left with its back to the table (the user's "chairs not facing their
        # table or desk")
        for r_ in [p for p in placed if p.get('room') == room['name'] and p.get('k') and roomsurvey.family_of(db, p['id'], p['type']) == 'chair']:
            near_t = [t for t in tables if max(t['box'][0] - r_['p'][0], r_['p'][0] - t['box'][2], t['box'][1] - r_['p'][1], r_['p'][1] - t['box'][3], 0) < 70]
            if not near_t:
                continue
            # (the nearest table, and the nearest point of it: a chair down the side of a long table faces
            # straight in, not slantwise at the far segment's middle)
            tb_ = min(near_t, key=lambda t: max(t['box'][0] - r_['p'][0], r_['p'][0] - t['box'][2], t['box'][1] - r_['p'][1], r_['p'][1] - t['box'][3], 0))['box']
            nx_, ny_ = min(max(r_['p'][0], tb_[0] + 10), tb_[2] - 10), min(max(r_['p'][1], tb_[1] + 10), tb_[3] - 10)
            dvx, dvy = nx_ - r_['p'][0], ny_ - r_['p'][1]
            if abs(dvx) < 8 and abs(dvy) < 8:
                dvx, dvy = (tb_[0] + tb_[2]) / 2 - r_['p'][0], (tb_[1] + tb_[3]) / 2 - r_['p'][1]
            dn = math.hypot(dvx, dvy) or 1.0
            rot_ = _turn_to_face(front_of(db, r_['id']), (dvx / dn, dvy / dn))
            # (turned only when it still stands on the room's floor as the walls bound it: a chair turned
            # a quarter by the wall put its back through it; and only its turn changes, never its height)
            if abs((rot_ - r_['p'][5] + math.pi) % (2 * math.pi) - math.pi) > 0.3 and r_['k'] in c['refs'] \
                    and inside(_footprint([v * (r_.get('s') or 1.0) for v in r_['b']], rot_, r_['p'][0], r_['p'][1])):
                r_['p'][5] = rot_
                editing._store(c, r_['k'], mine, int(r_['k'].rsplit('|', 1)[1]),
                               set_ref_pos([('NAME', zs(r_['id']))], tuple(r_['p']), r_.get('s', 1.0)))
                c['refs'][r_['k']]['by'] = 'furnish'
        if purpose == 'hall' and not walls_only and slots and not any(roomsurvey.family_of(db, r['id'], r['type']) in roomsurvey.FLOOR_KINDS + ('planter', 'basket')
                                                                   for r in placed if r.get('room') == room['name']):
            # (a hall whose bench found no wall clear of its doorways: something smaller against a wall,
            # so the hall is never bare floor and lamps: a planter, an urn, a crate, whichever fits)
            for kind in ('planter', 'urn', 'basket', 'crate'):
                rid = pick(kind)
                b = mapdata.object_bounds(db, db.resolve_id(rid)) if rid else None
                if not b:
                    continue
                done, face = wall_spot(b, front_of(db, rid), 'corner', pp=placesurvey.prefs(db, kind, purpose), kind=kind)
                prec_ = put(rid, done[0], done[1], done[2], floor=fl, room=room['name'], ledge=ledge_h) if done else None
                if prec_:
                    taken.append((done[3], fl, fl + 200, False))
                    got.append(rid)
                    if kind == 'planter':
                        plant_in(prec_, done[0], done[1], done[2])
                    break
        if clutter:
            rng.shuffle(clutter)
            # (mostly one kind to a group, as the game's are: like kinds together)
            if rng.random() > cs.get('mixed', 0.3):
                clutter.sort()
            groups += place_clutter(clutter, cs)
        if not walls_only and purpose not in ('ruin', 'camp'):
            import wallsurvey2
            skind = SURVEY_KIND.get(purpose, purpose)
            lr = wallsurvey2.light_rule(db, skind)
            hung_models, per_room, typical = roomrules.hung_lights(db, purpose)
            corridor = purpose == 'hall' or (min(room['w'], room['h']) == 1 and room['tiles'] >= 3)
            if corridor and not hung_models:
                # (the game lights a corridor with a lantern or a lamp about every tile, three in four
                # of them at a wall: wallsurvey2.corridor_rule; the hall's own survey has no lanterns)
                hung_models, _pr, _ty = roomrules.hung_lights(db, 'living')
                cr = wallsurvey2.corridor_rule(db)
                per_room = (cr['per_tile'] * sum(cr['kinds'].get(k, 0) for k in ('lantern', 'hanging lamp', 'chandelier')) if cr else 0.3) \
                    * room['tiles'] * (T / 256.0) ** 2
                typical = 10 ** 6
            # (as many as the game's rooms of the kind have, one more in a room twice the usual size)
            want = per_room * (1.0 if room['tiles'] * (T / 256.0) ** 2 < 2 * typical else 1.4) if hung_models else 0
            if L:
                want *= L['lights']          # (a poor house hangs fewer lanterns, a rich one more)
            n_hung = int(want) + (1 if rng.random() < want - int(want) else 0)
            # where the game hangs a lantern in rooms of this kind: at a wall (half of them in a living
            # room, a quarter in a tavern), over a table (one in twelve; one in seven over a shop's
            # counter), at the bed in a bedroom (a quarter), else out over the room
            rel = (lr or {}).get('rel', {}).get('lantern', {})
            p_wall = (lr or {}).get('at_wall', {}).get('lantern', 0.45) if lr else 0.2
            p_table = sum(v for k, v in rel.items() if k in ('over table', 'over counter', 'on table', 'on counter')) if rel else 0.5
            p_bed = sum(v for k, v in rel.items() if k in ('by bed', 'over bed')) if rel else 0.0
            beds = [f['box'] for f in fronts if f.get('kind') == 'bed']
            for _ in range(min(n_hung, 2 if not corridor else 6)):
                hid, up, gap = hung_models[min(len(hung_models) - 1, int(rng.random() ** 2 * min(4, len(hung_models))))]
                for _try in range(12):
                    roll = rng.random()
                    if corridor:
                        # along the corridor, one to a tile, at a wall three times in four
                        t = rng.choice(tl)
                        wall_sides = [s for s in STEP if t['pat'][s] == 'wall']
                        if wall_sides and rng.random() < 0.71:
                            s = rng.choice(wall_sides)
                            off = t['pat']['offset'].get(s, T / 2 - 16) - 48
                            x, y = t['x'] + STEP[s][0] * off, t['y'] + STEP[s][1] * off
                        else:
                            x, y = t['x'], t['y']
                    elif beds and roll < p_bed:
                        bb = rng.choice(beds)
                        long_x = (bb[2] - bb[0]) >= (bb[3] - bb[1])
                        # at the bed's head or foot, just inside its end
                        x = rng.choice((bb[0] + 40, bb[2] - 40)) if long_x else (bb[0] + bb[2]) / 2
                        y = (bb[1] + bb[3]) / 2 if long_x else rng.choice((bb[1] + 40, bb[3] - 40))
                    elif slots and roll < p_bed + p_wall:
                        sl = rng.choice(slots)
                        x, y = sl['x'] + sl['in'][0] * 48, sl['y'] + sl['in'][1] * 48
                    elif tables and roll < p_bed + p_wall + p_table:
                        tb = rng.choice(tables)['box']
                        x, y = (tb[0] + tb[2]) / 2 + rng.uniform(-20, 20), (tb[1] + tb[3]) / 2 + rng.uniform(-20, 20)
                    else:
                        x, y = rng.uniform(inner[0] + 60, inner[2] - 60), rng.uniform(inner[1] + 60, inner[3] - 60)
                    if hang_light(hid, up, gap, x, y):
                        break
            # a chandelier over the room (over the table in a study or a tavern), as often as the game's
            # rooms of the kind have one: a tavern two in five, a shop one in six, a study one in seven,
            # a living room one in sixteen; only where the house's own style hangs them (Imperial)
            if lr and lr['rooms_with'].get('chandelier', 0) > 0 and rng.random() < lr['rooms_with']['chandelier']:
                chand = roomrules.chandeliers(db, cell_style)
                if chand:
                    hid = chand[min(len(chand) - 1, int(rng.random() ** 2 * len(chand)))]
                    up = lr['height'].get('chandelier') or 168
                    crel = lr['rel'].get('chandelier', {})
                    if tables and rng.random() < sum(v for k, v in crel.items() if k.startswith('over')):
                        tb = rng.choice(tables)['box']
                        x, y = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
                    else:
                        x, y = cx, cy
                    hang_light(hid, up, 40, x, y)
        # a small mat just inside the front door, where people stand as they come in
        if not walls_only and mats and purpose not in ('ruin', 'camp'):
            for o in openings:
                low = o['id'].lower()
                if not (o['type'] == 'DOOR' and (o.get('to') or 'load' in low)) and 'jamb_load' not in low:
                    continue
                ox, oy = o['p'][0], o['p'][1]
                if not (room['x_min'] - 40 <= ox <= room['x_max'] + 40 and room['y_min'] - 40 <= oy <= room['y_max'] + 40) \
                        or abs(span(o)[0] - fl) > 60:
                    continue
                # (the frame marks the doorway's middle; a door's own point is often at its hinge)
                jb = [j for j in openings if 'jamb' in j['id'].lower() and math.hypot(j['p'][0] - ox, j['p'][1] - oy) < 140]
                if jb:
                    ox, oy = jb[0]['p'][0], jb[0]['p'][1]
                edges = {(1, 0): ox - room['x_min'], (-1, 0): room['x_max'] - ox, (0, 1): oy - room['y_min'], (0, -1): room['y_max'] - oy}
                ix, iy = min(edges, key=lambda k: abs(edges[k]))
                ex = room['x_min'] if ix == 1 else room['x_max'] if ix == -1 else ox
                ey = room['y_min'] if iy == 1 else room['y_max'] if iy == -1 else oy
                for rug in sorted(mats, key=lambda r: -r[2]):
                    s = rug_at(rug, ex + ix * (rug[3] / 2 + 30), ey + iy * (rug[3] / 2 + 30), iy != 0, clearings=False)
                    if s and put(rug[0], s[0], s[1], s[2], floor=fl, flat=True, room=room['name']):
                        rugs.append((s[3], fl))
                        got.append(rug[0])
                        break
        if (walls or walls_only) and purpose != 'ruin':      # (nobody hangs tapestries in a ruin)
            got += _decorate(db, room, purpose, T, decor, refs, placed, put, rng, hung, hang_k=L['hang'] if L else 1.0)
        # the room's wine racks, stocked the way the game stocks that model (a rack stood as part of a set
        # piece, or as decoration, was empty before)
        for rrec in rack_pending:
            bottles = dress(rrec, purpose)
            got += [o['id'] for o in (bottles or [])]
        rack_pending.clear()
        report.append({'room': room['name'], 'purpose': purpose, 'placed': len(got)})
    # the stairs: the game has a light within a tile and a half of nineteen flights in twenty (a lantern
    # most often, about a tile off); a flight with none gets a lantern hung a tile from it, in a furnished
    # room on its own floor, never over a doorway
    if not walls_only and T:
        import wallsurvey2
        st_rule = (wallsurvey2.ready(db) or {}).get('stairs')
        if st_rule and st_rule.get('lit', 0) >= 0.5:
            lit_by = [r for r in list(refs) + list(placed) if r['type'] == 'LIGH']
            done_rooms = {r['room'] for r in report if r['placed']}
            for st in refs:
                low = st['id'].lower()
                if not (st.get('arch') and ('stair' in low or 'ramp' in low)):
                    continue
                sx, sy, sz = st['p'][0], st['p'][1], st['p'][2]
                if any(math.hypot(l['p'][0] - sx, l['p'][1] - sy) < T * 1.5 and sz - 100 <= l['p'][2] <= sz + 450 for l in lit_by):
                    continue
                rm = next((r for r in info['rooms'] if r['name'] in done_rooms and abs(r['floor'] - sz) < 100
                           and r['x_min'] - T <= sx <= r['x_max'] + T and r['y_min'] - T <= sy <= r['y_max'] + T), None)
                if not rm:
                    continue
                hung_models, _pr, _ty = roomrules.hung_lights(db, rm['purpose'] if rm['purpose'] in RECIPES else 'living')
                if not hung_models:
                    hung_models, _pr, _ty = roomrules.hung_lights(db, 'living')
                fl = rm['floor']
                # the catalogue's rule 1: a light at the foot of the flight (the game: at the foot more
                # often than the head), a standing lamp or candle stand as often as the style's own stairs
                # have one rather than a lantern
                import catalogue
                sl = catalogue.rule(db, 'stair_light', cell_style)
                standing = roomrules.floor_lamps(db, rm['purpose'] if rm['purpose'] in RECIPES else 'living') or roomrules.floor_lamps(db, 'living')
                k_stand = sum(v for k, v in ((sl or {}).get('kinds') or {}).items() if k in ('sconce', 'candle', 'lamp'))
                use_standing = bool(standing) and (not hung_models or rng.random() < k_stand)
                if not use_standing and not hung_models:
                    continue
                cands = [(sx + dx * T, sy + dy * T) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                rng.shuffle(cands)
                prefix = kits.kit_prefix(st['id'])
                si = kits.stairs(db, prefix) if prefix and prefix in kits.kits(db) else None
                sp = next((p for p in si['pieces'] if p['id'].lower() == low), None) if si else None
                if sp and (sl is None or rng.random() < (sl.get('foot') or 0.6)):
                    # (the foot end first: the piece's low side, turned as it stands)
                    dx, dy = STEP[sp['low']]
                    c_, s_ = math.cos(st['p'][5]), math.sin(st['p'][5])
                    fx, fy = dx * c_ + dy * s_, -dx * s_ + dy * c_
                    cands.sort(key=lambda c: -((c[0] - sx) * fx + (c[1] - sy) * fy))
                for x, y in cands:
                    if not (rm['x_min'] + 40 <= x <= rm['x_max'] - 40 and rm['y_min'] + 40 <= y <= rm['y_max'] - 40):
                        continue
                    if use_standing:
                        lid = standing[0]
                        lb = mapdata.object_bounds(db, db.resolve_id(lid))
                        if not lb:
                            continue
                        # (at the side of the flight's foot, out of the way of whoever comes down it)
                        px, py = (x - sx, y - sy)
                        side = (-py / T * 70, px / T * 70)
                        box = _footprint(lb, 0, x + side[0], y + side[1])
                        rects_ = room_rects(rm, T)
                        # (clear of what stands there, and on the room's floor as the walls bound it: the
                        # user's lamps 20 to 33 units into a wall came from here)
                        if any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4) or not on_floor(box, rects_):
                            box = _footprint(lb, 0, x - side[0], y - side[1])
                            if any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4) or not on_floor(box, rects_):
                                continue
                            side = (-side[0], -side[1])
                        rec = put(lid, x + side[0], y + side[1], rng.uniform(0, 2 * math.pi), floor=fl, room=rm['name'])
                        if rec:
                            taken.append((box, fl, fl + 200, False))
                            lit_by.append(rec)
                            break
                        continue
                    hid, up, gap = hung_models[0]
                    hb = mapdata.object_bounds(db, db.resolve_id(hid))
                    if not hb:
                        break
                    box = _footprint(hb, 0, x, y)
                    if any(_overlaps(box, o[0]) for o in taken if o[3] and o[1] < fl + 150 and o[2] > fl + 4
                           and not (o[0][0] <= sx <= o[0][2] and o[0][1] <= sy <= o[0][3])):
                        continue            # (a doorway's clearing; the stair's own clearing doesn't count)
                    z = fl + up - hb[2]
                    over = [r['p'][2] + r['b'][2] * (r.get('s') or 1) for r in refs if r.get('arch') and r.get('b')
                            and r['p'][2] + r['b'][2] * (r.get('s') or 1) > fl + 100 and mapdata._rotated_contains(r, x, y)]
                    if over and z + hb[5] > min(over) - 4:
                        z = min(over) - (gap if gap is not None and gap < 160 else 8) - hb[5]
                        if z + hb[2] < fl + 110:
                            continue
                    rec = put(hid, x, y, rng.uniform(0, 2 * math.pi), at_z=z, room=rm['name'])
                    if rec:
                        lit_by.append(rec)
                        break
    if piece is not None:
        known = piece_info(db, cell_key, piece)['dressings_known']
        if piece_out is None:
            raise EditError('That piece stands in no room Auto-furnish can read (not on a room piece\'s floor).')
        if add:
            if not placed:
                return {'placed': 0, 'removed': 0, 'model': piece_out['model'], 'kind': piece_out.get('kind'), 'dressings_known': known,
                        'note': piece_out.get('note') or 'No room left on it.'}
            db.sync_project()
            import modelcache
            modelcache.save()
            placed_last[:] = placed
            editing.commit(db, 'Added %s to %s' % (piece_out.get('name') or piece_out.get('added'), piece_out['model']))
            return {'placed': 1, 'removed': 0, 'model': piece_out['model'], 'kind': piece_out.get('kind'), 'dressings_known': known,
                    'added': piece_out.get('added'), 'name': piece_out.get('name')}
        if not placed:
            if not known:
                raise EditError('The game never puts anything on this (%s), so there is nothing to copy.' % piece_out['model'])
            raise EditError('None of the game\'s %d dressings of this model fit here as it stands (too close to a wall, or things in the way).' % known)
        db.sync_project()
        import modelcache
        modelcache.save()
        placed_last[:] = placed
        editing.commit(db, 'Dressed %s the game\'s way (%d things)' % (piece_out['model'], len(placed)))
        return {'placed': len(placed), 'removed': removed, 'model': piece_out['model'], 'kind': piece_out['kind'], 'dressings_known': known}
    if room_rec is not None:
        if not placed:
            raise EditError('Nothing of the game\'s fits in the %s as a %s (no spot clear of its doorways, or no such furniture in the load order).' % (room_rec['name'], plan[0]['purpose']))
        db.sync_project()
        import modelcache
        modelcache.save()
        placed_last[:] = placed
        pur_ = next((r['purpose'] for r in report if r['room'] == room_rec['name']), plan[0]['purpose'])
        editing.commit(db, 'Furnished the %s the game\'s way (%d things)' % (room_rec['name'], len(placed)))
        return {'placed': len(placed), 'removed': removed, 'room': room_rec['id'], 'name': room_rec['name'], 'purpose': pur_}
    if not placed:
        if walls_only:
            raise EditError('Found no free wall to hang things on, or nothing that hangs on walls in places like this.')
        raise EditError('Could not find fitting furniture for these rooms (nothing similar in the load order?).')
    # walking paths around the new furniture (only where the mod made the paths, or there were none)
    db.sync_project()
    if not any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), [])):
        try:
            import pathgrid
            pathgrid.generate(db, cell_key, note=False)
        except EditError:
            pass
    import modelcache
    modelcache.save()                        # (what was learnt about the models this time, kept for the next furnish)
    placed_last[:] = placed                  # (for the lab: what was laid, and by which path)
    editing.commit(db, 'Auto-furnished %s (%d things in %d rooms)' % (editing.cell_label(db, cell_key), len(placed),
                                                                      len([r for r in report if r['placed']])))
    # how many of the containers stood here hold something (the game's own filled ones)
    import containersurvey
    filled = sum(1 for r in placed if r['type'] == 'CONT' and (containersurvey.contents(db, r['id']) or {}).get('items'))
    return {'placed': len(placed), 'rooms': report, 'style': style, 'groups': groups, 'filled': filled,
            'containers': sum(1 for r in placed if r['type'] == 'CONT'),
            'borrowed': CULTURE_NAMES.get(fam.get('_borrowed')) if fam.get('_borrowed') else None,
            'level': L['label'] if L else None, 'band': L['band'] if L else 'comfortable',
            'extras_left': extras_left}
