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
import floortrace
import kits
import mapdata
import shelfsurvey as _shelfsurvey_mod
shelfsurvey_PLANTER = _shelfsurvey_mod.PLANTER
shelfsurvey_GARDEN = _shelfsurvey_mod.GARDEN
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
NOT = {'table': ('tablet',), 'bed': ('bedroll',), 'shelf': ('bookshelf', 'bookcase', 'shelffungus', 'fungus'), 'chest': ('chestnut',),
       'counter': ('door', 'barrel'), 'screen': ('in_', 'ex_', 'marker', 'window'), 'planter': ('marker',),
       'fire': ('in_', 'ex_', 'marker', 'chimney', 'smoke', 'light_fire', 'sound',      # (a kit's hearth wall is the building, not furniture)
                # (and a hearth's tools are not a hearth: Tamriel Data's fireplace tool stand "is a fireplace" by
                # its name and was laid as the user's Rich Imperial Manor kitchen's hearth, 2026-10-23)
                'stand', 'hook', 'shovel', 'broom', 'poker', 'tong', 'tool', 'tapestr', 'sign', 'banner'),
       'shrine': ('base', 'block', 'slab', 'pedestal', 'stand', 'platform', 'plinth', 'podium', 'pillar', 'column', 'cube', 'step', 'in_', 'ex_',
                  # (an altar is of its culture, like the rest of the furniture: a dreugh altar belongs in a
                  # grotto, a daedric one in a daedric ruin, never in a house; the user's "a Hlaalu home isn't
                  # supposed to have a dreugh altar")
                  'dreugh', 'dreu_', 'daedric', 'dae_', 'dwemer', 'dwrv', 'sixth', '6th', 'ashland', 'cave', 'ruin', 'grotto', 'sacrific'),
       'bath': ('tube', 'bathroom', 'marker', 'in_', 'ex_'), 'rack': ('wine', 'bottle', 'scroll', 'spice', 'coat', 'hat'), 'target': ('targeting', 'marker')}
# (a bare stone piece: an altar base, a block, a slab, a plinth, a pedestal with nothing on it. Never
# furniture in a house, whatever family a name puts it in: the user's "white stone block" by a tapestry)
BARE_STONE = re.compile(r'(altar|shrine)[^a-z]*(base|block|slab|plinth|pedestal|step|platform)|pedestal|plinth|podium|_slab|stoneblock|stone_block|marbleblock')
# (the dreugh's own make, Tamriel Data's t_dreu_ altars and furniture: only in a dreugh's grotto, never
# in a house; the user's "Dreugh altars and furniture don't go in land based dwellings")
DREUGH_MAKE = re.compile(r'^t_dreu_|dreugh')
HANGING_KINDS = ('shelf',)      # the only furniture put up on a wall (at the height the game hangs it)
BED_OFF_THE_WAY = True          # a bed in a small room never across the line from its doorway to its middle (for the lab: off to compare)
WORK_TABLE_REACH = 300          # a kitchen's hearth has a table or counter this near (the game's median 249): 0 to leave it to the recipe
WINERACK = re.compile(r'winerack|wine_rack|bottlerack')
COUNTER_PART = re.compile(r'_end|_cnr|corner|_curve|_short|_half')      # the end and corner pieces of a counter run
KEEPER_GAP = 96                 # a counter stands this far off the wall: the keeper's side (the game's traders stand 71 behind it)
TALL_BOTTLE = re.compile(r'misc_com_bottle|t_com_bottle|t_imp_drink_|t_de_drink_|wine')     # the slim bottles the game racks
FAT_BOTTLE = re.compile(r'^potion_|^p_|liquor|brew|brandy|whiskey|sujamma|mazte|shein|greef|flin|cyro')   # Dunmer flasks and potions
DRESSED_KINDS = ('bookshelf', 'shelf', 'table', 'counter', 'rack', 'cupboard', 'bed')     # set out the way the game dresses the model (shelfsurvey.py; a bed: its pillow, as the game lays it)
ARRANGE = True                  # lay the game's own set pieces first (arrangesurvey.py)
SCENES = True                   # and every recipe kind the game keeps company as a scene (arrangesurvey.scene)
TRADES = True                   # trade rooms from their own anchor sets, smith's tools only at a forge (tradesurvey.py)
SCENE_KINDS = ('table', 'bed', 'bookshelf', 'shelf', 'cupboard', 'counter', 'shrine', 'bench', 'planter', 'fire', 'chest', 'screen')
SMALL_KINDS = ('crate', 'planter', 'urn', 'basket', 'chest', 'sack', 'barrel', 'screen')   # never alone in open floor
# what rides on what: a set piece's small member only on the kind of main piece the game had it on
SURFACE_KINDS = ('table', 'counter', 'shelf', 'bookshelf', 'cupboard', 'chest', 'crate', 'barrel', 'bench')
RIDE = {'pillow': ('bed', 'bench', 'chair'), 'plant': ('planter',), 'basket': SURFACE_KINDS, 'lamp': SURFACE_KINDS + ('bed',),
        'apparatus': ('table', 'counter', 'shelf', 'bookshelf', 'cupboard')}
HANGING_LIGHT = re.compile(r'chandelier|candelabra|lantern|hanging|_hang|chain')
BEAM = re.compile(r'beam|rafter|joist')      # a building piece a light can hang from where there is no ceiling (an open hall)
# a piece that exists only inside another: a bath's water sheet (t_imp_furnr_bath_02_w), a flame, a glow. Never
# furniture on its own, in any recipe, palette or dressing; the user's "bath water shouldn't be a decoration
# unless actually in a bath"
RIDER_ONLY = re.compile(r'(_w|_water|_flame|_fire_fx|_fx|_glow|_steam)$|_water_|_waterplane')
ESSENTIAL = {'bedroom': 'bed', 'shop': 'counter', 'tavern': 'counter', 'shrine': 'shrine', 'bath': 'bath', 'barracks': 'bed',
             'armoury': 'rack', 'mess': 'table', 'training': 'target', 'dining': 'table',
             'smithy': 'forge', 'alchemist': 'table', 'enchanter': 'table', 'bookseller': 'bookshelf', 'clothier': 'counter',
             'pawnbroker': 'counter'}   # the piece a room of the kind is for
# the trades' rooms (tradesurvey.py): the purpose, and the trade the survey reads its people's class as. A trade
# room is furnished as a shop from its own anchor set: a smithy round its forge (the anvil and the bellows at it,
# or no smithing at all), an apothecary's round the alchemy bench, a bookseller's round its shelves; and the
# pieces other trades are known by stay out (a smithy's writing set and scales: the user's "you won't be doing
# much forging with a desk and quill", 2026-10-23). A plain shop is a general trader's.
TRADE_ROOMS = {'smithy': 'smith', 'alchemist': 'alchemist', 'enchanter': 'enchanter', 'bookseller': 'bookseller',
               'clothier': 'clothier', 'pawnbroker': 'pawnbroker'}
TRADE_SCENE = {'alchemist': 'alchemist', 'bookseller': 'scribe'}     # a trade's own scene with its kit, laid always (scenesurvey)
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
    'study': [('bookshelf', 2, 'wall'), ('table', 1, 'corner'), ('rug', 1, 'under_table'), ('chair', 1, 'by_table'),
              ('book', 3, 'on_table'), ('candle', 1, 'on_table'), ('cupboard', 1, 'wall'), ('chair', 1, 'wall')],
    'shop': [('counter', 1, 'centre'), ('rug', 1, 'before'), ('shelf', 2, 'wall'), ('chest', 1, 'wall'), ('crate', 2, 'wall'),
             ('barrel', 1, 'corner'), ('bottle', 2, 'on_table'), ('dish', 2, 'on_table')],
    'shrine': [('shrine', 1, 'wall'), ('rug', 1, 'before'), ('bench', 2, 'wall'), ('urn', 2, 'corner'),
               ('candle', 2, 'on_table')],
    'hall': [('rug', 1, 'runner'), ('bench', 1, 'wall'), ('urn', 2, 'corner')],
    # caves, mines and camps: people sleep rough here; ruins: what's left lying about
    'camp': [('bedroll', 2, 'wall'), ('fire', 1, 'centre'), ('crate', 2, 'wall'), ('barrel', 2, 'corner'), ('sack', 2, 'wall'),
             ('chest', 1, 'wall'), ('urn', 1, 'corner')],
    'ruin': [('crate', 2, 'wall'), ('barrel', 2, 'corner'), ('urn', 2, 'corner'), ('chest', 1, 'wall'), ('sack', 1, 'wall')],
    'tavern': [('fire', 1, 'wall'), ('counter', 1, 'wall'), ('table', 2, 'centre'), ('bench', 2, 'by_table'), ('chair', 5, 'by_table'), ('barrel', 3, 'corner'),
               ('bottle', 4, 'on_table'), ('dish', 4, 'on_table'), ('food', 2, 'on_table')],     # (the benches before the chairs: they take the long sides, R9)
    # the room-kind survey's kinds (roomkindsurvey.py, packaging/nexus/room-kinds-survey.md): these are
    # the hand-written stand-ins until it has run; roomrules.kind_recipe gives the game's own rates
    'bath': [('bath', 1, 'wall'), ('screen', 1, 'centre'), ('chair', 1, 'wall'), ('bench', 1, 'wall'), ('shelf', 1, 'wall'),
             ('planter', 1, 'wall'), ('dish', 2, 'on_table')],
    'corridor': [('chair', 1, 'wall'), ('shelf', 1, 'wall')],
    'entry': [('bench', 1, 'wall'), ('lamp', 1, 'wall'), ('planter', 1, 'corner'), ('rug', 1, 'runner'), ('basket', 1, 'wall')],
    'landing': [('rug', 1, 'runner'), ('bench', 1, 'wall'), ('urn', 1, 'corner')],
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
    # the trades' rooms (tradesurvey.py, packaging/nexus/trade-rooms.md): the anchor first, then what the game's
    # rooms of the trade hold in a third or more of them (a smith's: table 61%, chest 51%, crates 50%, barrels 40%,
    # shelves 39%, racks 24%; the anvil, the bellows and the coals come with the forge, lay_forge_set)
    'smithy': [('forge', 1, 'wall'), ('rack', 2, 'wall'), ('crate', 2, 'wall'), ('barrel', 1, 'corner'), ('chest', 1, 'wall'),
               ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('shelf', 1, 'wall')],
    'alchemist': [('table', 1, 'wall'), ('chair', 1, 'by_table'), ('shelf', 2, 'wall'), ('bookshelf', 1, 'wall'), ('chest', 1, 'wall'),
                  ('sack', 2, 'wall'), ('urn', 1, 'corner'), ('bottle', 3, 'on_table'), ('food', 2, 'on_table')],
    'enchanter': [('table', 1, 'centre'), ('chair', 2, 'by_table'), ('bookshelf', 1, 'wall'), ('shelf', 1, 'wall'), ('chest', 1, 'wall'),
                  ('bench', 1, 'wall'), ('candle', 2, 'on_table'), ('book', 2, 'on_table'), ('wares', 3, 'on_table')],
    'bookseller': [('bookshelf', 3, 'wall'), ('counter', 1, 'centre'), ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('chest', 1, 'wall'),
                   ('shelf', 1, 'wall'), ('candle', 2, 'on_table'), ('book', 3, 'on_table')],
    'clothier': [('counter', 1, 'centre'), ('loom', 1, 'wall'), ('bookshelf', 1, 'wall'), ('chest', 2, 'wall'), ('shelf', 1, 'wall'),
                 ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('basket', 1, 'wall'), ('wares', 3, 'on_table')],
    'pawnbroker': [('counter', 1, 'centre'), ('shelf', 2, 'wall'), ('chest', 1, 'wall'), ('crate', 2, 'wall'), ('table', 1, 'wall'),
                   ('chair', 1, 'by_table'), ('bookshelf', 1, 'wall'), ('wares', 2, 'on_table')],
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
                 # (the trades before "shop" and "store": a blacksmith's shop is a smithy, a bookstore a bookseller's)
                 'smith': 'smithy', 'forge': 'smithy', 'armorer': 'smithy', 'armourer': 'smithy', 'workshop': 'smithy',
                 'alchem': 'alchemist', 'apothecar': 'alchemist', 'enchant': 'enchanter',
                 'bookseller': 'bookseller', 'bookshop': 'bookseller', 'book shop': 'bookseller', 'bookstore': 'bookseller',
                 'clothier': 'clothier', 'tailor': 'clothier', 'outfitter': 'clothier', 'pawn': 'pawnbroker',
                 'bed': 'bedroom', 'sleep': 'bedroom', 'kitchen': 'kitchen', 'cook': 'kitchen', 'pantry': 'kitchen',
                 'store': 'storage', 'cellar': 'storage', 'storage': 'storage', 'study': 'study', 'library': 'study',
                 'office': 'study', 'shop': 'shop', 'store front': 'shop', 'trader': 'shop', 'shrine': 'shrine',
                 'chapel': 'shrine', 'temple': 'shrine', 'hall': 'hall', 'corridor': 'hall', 'landing': 'hall',
                 'passage': 'hall', 'entrance': 'hall', 'entry': 'hall', 'foyer': 'hall', 'vestibule': 'hall', 'gallery': 'hall', 'tavern': 'tavern',
                 'inn': 'tavern', 'club': 'tavern', 'bar': 'tavern', 'living': 'living', 'main': 'living',
                 'common': 'living', 'parlor': 'living', 'parlour': 'living',
                 'camp': 'camp', 'cave': 'camp', 'mine': 'camp', 'den': 'camp', 'ruin': 'ruin', 'vault': 'ruin'}


def purpose_for(name, tiles, w, h):
    low = (name or '').lower()
    for word, p in PURPOSE_WORDS.items():
        if word in low and (TRADES or p not in TRADE_ROOMS):
            return p
    if min(w, h) == 1:
        return 'hall'
    if tiles <= 4:
        return 'bedroom'
    return 'living'


# ------------------------------------------------------------------ rooms
FLOOR_T = 128            # the grid traced floors are cut into
# the big statics the map reader calls architecture that are furniture all the same (redoransurvey.is_thing)
BIG_FURNITURE = re.compile(r'planter|rug|carpet|flora_|_tree|tree_|mushroom|shroom|hearth|kiln|forge|fireplace|stove|oven|practice_mat')
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


STYLE_CYCLE = True       # (an unsure style: each furnish leads with another likely make; the lab turns it off to compare)
STYLE_KINDS = ('bed', 'table', 'chair', 'bench', 'chest', 'cupboard', 'shelf', 'bookshelf')


def _make_of(rid):
    """The make a piece of furniture belongs to by its id: furn_de_p_bench_03 -> furn_de_p, T_De_FurnM_Table_05 ->
    t_de_furnm, furn_com_rm_chair_03 -> furn_com_rm; None for an id of no make."""
    parts = rid.lower().split('_')
    if parts[0] == 't' and len(parts) > 3:
        return '_'.join(parts[:3])
    if parts[0] == 'furn' and len(parts) > 3:
        return '_'.join(parts[:3])
    return None


ROUGH_SHELLS = {'Cave': 'camp', 'Ashlander': 'camp', 'Mine': 'camp', 'Dwemer': 'ruin', 'Daedric': 'ruin', 'Ruin': 'ruin'}
ROUGH_NAMES = re.compile(r'tomb|crypt|catacomb|barrow|burial|ossuary|sepulch|mausoleum')


def rough_kind(db, cell_key, refs):
    """What a place's unnamed rooms are furnished as when it is no home: 'camp' in a cave, a mine or a yurt
    (by the shell pieces it is built of), 'ruin' in a Dwemer or Daedric ruin or a tomb (by its name); None in a
    house."""
    shell = Counter(mapdata.style_of(r['id'].lower()) for r in refs
                    if (r['id'].lower().startswith(('in_', 'ex_')) or kits.kit_prefix(r['id'].lower())) and mapdata.style_of(r['id'].lower()))
    if shell and ROUGH_SHELLS.get(shell.most_common(1)[0][0]):
        return ROUGH_SHELLS[shell.most_common(1)[0][0]]
    name = (mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key
    return 'ruin' if ROUGH_NAMES.search(name.lower()) else None


def rooms(db, cell_key, names=None, trace='geometry'):
    """The rooms of a place, from its kit floor pieces: [{id, name, purpose, tiles, x_min, ...}].
    trace: whether a place not laid in kit tiles (a cave, a yurt, a Redoran manor) has its floor traced
    from its meshes instead (_floor_tiles: most of a second), False for none, or a function of the
    place's refs that says; the surveys that only read kit-tiled places pass False and go ten times
    as fast. 'geometry' (the tools' default): any interior's floors, walls, doorways and rooms read from
    its own geometry (floortrace.py), a place laid only in part in room pieces too; the surveys keep the
    reading they learnt from (True or a function: _floor_tiles, as before)."""
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
    # (a big piece of a known kit that its piece list does not carry, a stair, a hall piece, is still the
    # kit's own, not a ready-made room: Redoran large's in_r_l_int_stairs_02 made every built Redoran large
    # house "premade", its 34 tiles were thrown away for a traced floor, and the traced 128-unit grid never
    # met the plan's 512 tiles: "No rooms found here", 2026-10-22)
    # (and a big rug scaled 2.2 times, a big planter, a tree or a kiln hearth is furniture, however big the
    # map reader finds it: only a building piece, named in_/ex_ as the game names its shells, makes a place
    # ready-made. The first Redoran hall with its island rugs lost its rooms to this test, 2026-10-22)
    known = kits.kits(db)
    premade = any(r.get('arch') and r.get('b') and (r['b'][3] - r['b'][0]) * (r['b'][4] - r['b'][1]) * (r['s'] or 1) ** 2 > 2.5 * 256 * 256
                  and not (kits.kit_prefix(r['id']) in known)
                  and (r['id'].lower().startswith(('in_', 'ex_')) or '_in_' in r['id'].lower() or '_ex_' in r['id'].lower())
                  and not BIG_FURNITURE.search(r['id'].lower())
                  for r in m['refs'])
    # a place made with "Build from pieces" remembers its rooms
    plan = (db.project.cells.get(cell_key) or {}).get('plan') if db.project else None
    # (any other interior: its floors, walls and doorways read from its own geometry, floortrace.py: the game's
    # hand-made houses, caves and tombs, a Nord house shell, a place half pieces and half by hand. The user:
    # "the furnish ability only works for modular rooms, but it really ought to work in other settings")
    traced = False
    geometry = trace == 'geometry'
    if not tiles or premade:
        if not geometry and trace is not True and not (trace and trace(m['refs'])):
            return {'tile': None, 'rooms': [], 'refs': m['refs']}
        got = (floortrace.trace(db, m, cell_key) if geometry else None) or _floor_tiles(db, m)
        if got:
            tiles, T, traced = got, FLOOR_T, geometry
    elif geometry and not (plan and plan.get('rooms')) and T and T >= 2 * FLOOR_T:
        # (laid in room pieces only in part, like a game manor whose pieces the kits don't all list: the floor
        # the pieces leave out, traced, when it is a good share of the place)
        got = floortrace.trace(db, m, cell_key)
        if got:
            rest = [t for t in got.values() if not any(abs(t['x'] - kt['x']) < T / 2 and abs(t['y'] - kt['y']) < T / 2
                                                       and abs(t['floor'] - kt['floor']) < 64 for kt in tiles.values())]
            if len(rest) >= 8 and len(rest) >= 0.25 * len(got):
                tiles, T, traced = floortrace.join(tiles, T, got), FLOOR_T, True
    if not tiles:
        return {'tile': None, 'rooms': [], 'refs': m['refs']}

    def _traced_rooms(keys, first, names_):
        """Traced tiles cut into rooms (floortrace.segment), sized for purpose_for in the kits' 256 tiles."""
        out_ = []
        for g in floortrace.segment({k: tiles[k] for k in keys}, m):
            n = first + len(out_)
            xs = [tiles[k]['x'] for k in g]
            ys = [tiles[k]['y'] for k in g]
            w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
            name = (names_ or {}).get(n) or 'Room %d' % (n + 1)
            f = T / 256.0
            out_.append({'id': n, 'name': name, 'tiles': len(g), 'w': w, 'h': h,
                         'purpose': purpose_for(name, len(g) * f * f, max(1, round(w * f)), max(1, round(h * f))),
                         'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2, 'y_max': max(ys) + T / 2,
                         'floor': min(tiles[k]['floor'] for k in g), '_tiles': [tiles[k] for k in g], 'traced': True})
        # (a narrow piece is a hall when it runs on, four tiles or more; the scraps the cut leaves by a bed or a
        # bookshelf, between rooms, are left bare when the place has rooms proper. On 100 game places the
        # scraps read as halls had the game's own furniture "across" them, 2026-10-24)
        big_ = any(len(rm['_tiles']) >= 9 for rm in out_)
        for rm in out_:
            if not re.match(r'^room \d+$', rm['name'].lower()):
                continue
            if big_ and len(rm['_tiles']) < 6:
                rm['purpose'] = 'none'
            elif rm['purpose'] == 'hall' and max(rm['w'], rm['h']) < 4:
                f = T / 256.0
                rm['purpose'] = purpose_for('', max(len(rm['_tiles']) * f * f, 4.01), 2, 2)
        return out_
    if plan and plan.get('rooms'):
        result = []
        # (the plan's tiles are its own size; traced tiles are smaller and fall inside them)
        PT = (plan.get('tile') or 256) / 2 if traced else 24
        claimed = set()
        for n, pr in enumerate(plan['rooms']):
            # tiles are [x, y] or, in buildings with more than one floor, [x, y, floor height]
            g = [k for k in tiles if any(abs(k[0] - pt[0]) < PT and abs(k[1] - pt[1]) < PT and
                                         (len(pt) < 3 or abs(tiles[k]['floor'] - pt[2]) < 64) for pt in pr['tiles'])]
            claimed.update(g)
            if not g:
                continue
            xs = [tiles[k]['x'] for k in g]
            ys = [tiles[k]['y'] for k in g]
            w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
            result.append({'id': n, 'name': pr['name'], 'tiles': len(g), 'w': w, 'h': h,
                           'purpose': purpose_for(pr['name'], len(g), w, h),
                           'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2,
                           'y_max': max(ys) + T / 2, 'floor': min(tiles[k]['floor'] for k in g),
                           '_tiles': [tiles[k] for k in g],
                           # (a chimney outside over the room: its hearth on the wall nearest it, frombuilding.py)
                           **({'hearth_near': pr['hearth_near']} if pr.get('hearth_near') else {})})
        if traced:
            # (a shell or a hand-made part added to a built place: its rooms after the plan's)
            result += _traced_rooms([k for k in tiles if k not in claimed], len(plan['rooms']), names)
        return {'tile': T, 'rooms': result, 'refs': m['refs'], 'traced': traced}
    if traced:
        out_ = _traced_rooms(list(tiles), 0, names)
        rough_ = rough_kind(db, cell_key, m['refs'])
        if rough_:
            # (a cave's or a tomb's rooms as what they are, in the dialog and the right-click menu too, which name
            # each room's kind; its tunnels left bare and walkable, as the game leaves its own)
            for rm in out_:
                if re.match(r'^room \d+$', rm['name'].lower()):
                    rm['purpose'] = 'none' if rm['purpose'] in ('hall', 'none') else rough_
        return {'tile': T, 'rooms': out_, 'refs': m['refs'], 'traced': True}
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
    kept = modelcache.get(db, 'hang2', low)       # ('hang2': the heights come from bounds, which the model reader's root-transform change moved)
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
    modelcache.put(db, 'hang2', low, [out, _mount.get(low)])
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
                if 'marker' in low or 'unique' in low or BARE_STONE.search(it['id'].lower()) or RIDER_ONLY.search(it['id'].lower()):
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
    # (Project Tamriel's rule: Dunmer and Imperial furniture are never mixed; a Dunmer house keeps its
    # Dunmer pieces where it has any of a kind, an Imperial one its Imperial)
    own = STYLE_SET.get(style)
    import wealthsurvey
    if own in ('dunmer', 'imperial'):
        other = 'imperial' if own == 'dunmer' else 'dunmer'
        for k in FAMILIES:
            kept = [rid for rid in fam[k] if wealthsurvey.culture_of(rid) != other]
            if kept and len(kept) < len(fam[k]):
                fam[k] = kept
    # (a planter that stands on the floor is a planter the game stands on the floor: a pot a hand wide
    # belongs on a table or a shelf and comes with the dressings; a hanging planter hangs, so it comes by
    # its own path. The user's "planters like this belong on a table, not in the middle of a floor".)
    fam['planter'] = [rid for rid in fam['planter'] if floor_planter(db, rid)]
    # (and the poor and the rich make never in one house unless a band says so: the palette's commoner
    # of the two stays, with the middling make and the pieces of no make)
    tiers = {}
    for k in FAMILIES:
        for rid in fam[k]:
            t = wealthsurvey.set_tier(rid)
            if t in ('poor', 'rich'):
                tiers[t] = tiers.get(t, 0) + 1
    if tiers.get('poor') and tiers.get('rich'):
        drop = 'rich' if tiers['poor'] >= tiers['rich'] else 'poor'
        for k in FAMILIES:
            kept = [rid for rid in fam[k] if wealthsurvey.set_tier(rid) != drop]
            if kept and len(kept) < len(fam[k]):
                fam[k] = kept
        fam['_tier'] = 'poor' if drop == 'rich' else 'rich'
    return fam, style


_hearths = {}
BUILDING_BITS = re.compile(r'railing|rail_|beam|pillar|column|_post|wall|floor|stair|ceiling|door|window')     # (never a hearth set's member)
SMALL_POT = 40          # (a planter narrower than this is a tabletop pot, never a floor planter)
THING_TAGS_ON_TOP = ('MISC', 'BOOK', 'INGR', 'ALCH', 'LIGH', 'APPA', 'LOCK', 'PROB', 'REPA', 'WEAP', 'ARMO', 'CLOT', 'STAT', 'ACTI', 'CONT')


def floor_planter(db, rid):
    """A planter the game stands on the floor: wide enough, and not a hanging one."""
    low = rid.lower()
    if 'hanging' in low or 'hang' in low:
        return False
    b = mapdata.object_bounds(db, db.resolve_id(rid))
    return bool(b) and max(b[3] - b[0], b[4] - b[1]) >= SMALL_POT


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
        if max(b[3] - b[0], b[4] - b[1]) < 60 or (b[5] - b[2]) < 30:
            continue                  # (a hearth is big: a tool stand a hand wide is not one)
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
             'pillar', 'column', 'stair', 'ladder', 'cage', 'bone', 'skull', 'blood', 'cobweb', 'moss', 'screen',
             # (a ship's rigging tackle and an archery target are flat and hang high in the game, from rigging and
             # on a range; they came out on the suite's Hlaalu kitchen walls as "decor", 2.3.3)
             'tackle', 'rigging', 'target', 'dummy', 'sail', 'anchor', 'oar',
             # (Tamriel Data's dungeon sets, a barrow's broken plaque: a ruin's, never a house's wall; it hung
             # floating in every lab Nord house's halls, 2026-10-23)
             '_dng')
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
# which furniture makes never enter a house of a culture (the game's Nord houses take Imperial furniture)
CULTURE_FORBIDS = {'dunmer': ('imperial', 'nordic'), 'imperial': ('dunmer',), 'nordic': ('dunmer',)}
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
               'mess': 'living', 'guardroom': 'living', 'armoury': 'storage', 'training': 'storage',
               'smithy': 'shop', 'alchemist': 'shop', 'enchanter': 'shop', 'bookseller': 'shop', 'clothier': 'shop', 'pawnbroker': 'shop'}      # Auto-furnish's room purposes in wallsurvey2's words (its halls are rooms with no furniture)


def bath_models(db, culture):
    """The tubs and basins the game's places of this culture bathe in (room-kind survey R1): Imperial and
    Gold Coast houses the marble basins and baths, every other culture the half-barrel tub, Hlaalu its own
    basin too; only ids that exist here."""
    imp = ('t_imp_furnr_basin_02', 't_imp_furnr_basin_01', 't_imp_furnr_basin_03', 't_imp_furnr_bath_01',
           't_imp_furnr_bath_02', 't_imp_furn_bath_01_cloth')      # (never the _w water sheets: they ride in their tub)
    de = ('t_com_furn_bathhalfbarrel_01', 't_com_furn_bathhalfbarrel_02', 't_de_furn_basin_01')
    ids = imp + de if culture == 'imperial' else de + imp
    return [i for i in ids if db.resolve_id(i) is not None]


def trade_wares(db, trade, culture):
    """What a trade lays out on its tables (tradesurvey's pieces the trade is known by): an enchanter's soul
    gems (in 54% of the game's enchanters' rooms), a clothier's cloth bolts (65%), a pawnbroker's scales (35%);
    the house's culture's own make first; only ids that exist here."""
    imp = culture == 'imperial'
    ids = {'enchanter': ('misc_soulgem_petty', 'misc_soulgem_lesser', 'misc_soulgem_common', 'misc_soulgem_greater'),
           'clothier': (('t_imp_clothbolt_01', 't_imp_clothbolt_02', 't_imp_clothbolt_03') if imp else ()) +
                       ('misc_clothbolt_01', 'misc_clothbolt_02', 'misc_clothbolt_03'),
           'pawnbroker': ('t_imp_silverscales_01', 't_com_scalesbrass_01') if imp else ('t_de_scales_01', 't_de_scales_02')}.get(trade, ())
    return [i for i in ids if db.resolve_id(i) is not None]


def trade_looms(db, culture):
    """A clothier's loom or spinning wheel, the house's culture's make first (in 42% of the game's clothiers' rooms)."""
    ids = ('t_imp_furn_spinningwheel_01', 't_imp_furn_loom_01', 'furn_spinningwheel_01', 'furn_de_loom_01')
    if culture != 'imperial':
        ids = ids[2:] + ids[:2]
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


# the hallway round (hallsurvey.py, packaging/nexus/hallways-survey.md): a hall is dressed one of the ways
# the game's halls of the house's culture are, the arrangement drawn by how often the game's runs show it
HALL_ROUND = True        # (False: the halls as before the round, for comparisons)
HALL_PURPOSES = ('hall', 'corridor', 'entry', 'landing')
HALL_TOKENS = {'rug': 'runner', 'tapestry': 'cloth', 'banner': 'cloth', 'stores': 'stores', 'bench': 'bench', 'chair': 'chair',
               'table': 'table', 'urn': 'urns', 'planter': 'planter', 'plant': 'planter', 'chest': 'chest', 'bookshelf': 'bookshelf',
               'cupboard': 'cupboard', 'shrine': 'shrine'}
HALL_CLEAR = 48          # the walking line keeps this far from what the round stands (a way 96 wide; a hall is 228 inside)
HALL_DOOR = 90           # (from a doorway's middle to the thing's edge: the game's hall things, p10 of their middles 130 off)
HALL_END_CLEAR = 32     # (at a dead end's far wall the line stops at the tile's middle: the end is the game's place for things)
HALL_BARE_K = 0.15       # the game leaves most halls bare (Velothi 93%); the user asked for dressed halls, so a seventh as often
HALL_STYLES = {'Hlaalu': 'Hlaalu', 'Redoran': 'Redoran', 'Velothi': 'Velothi', 'Imperial': 'Imperial', 'Common': 'Common',
               'Telvanni': 'Telvanni', 'Indoril': 'Indoril', 'Mournhold': 'Mournhold', 'Dunmer': 'Velothi'}
# (until the hall survey has run: the arrangements of the whole game's house halls, 2617 runs, 2026-10-23)
HALL_DEFAULT = [['bare', 1400], ['tapestry', 304], ['rug+tapestry', 110], ['rug', 88], ['stores', 50], ['stores+tapestry', 38],
                ['bench+rug+tapestry', 23], ['bench+tapestry', 19], ['bench', 18], ['chair', 17], ['rug+stores+tapestry', 15],
                ['bookshelf', 13], ['shrine', 13], ['chair+table+tapestry', 11], ['banner', 11], ['bookshelf+rug+tapestry', 11]]


def hall_menu(rule, used=()):
    """A culture's ways of dressing a hall, from the hall survey's arrangements (its runs' sets of things):
    [(elements, weight, signature)], one entry per set of elements. The bare way weighs HALL_BARE_K of the
    game's count; a way this house's other halls already took weighs a quarter (halls not all alike)."""
    merged = {}
    for sig, n in ((rule or {}).get('arrangements') or HALL_DEFAULT):
        els = tuple(sorted({HALL_TOKENS[t] for t in sig.split('+') if t in HALL_TOKENS}))
        w = n * (HALL_BARE_K if not els else 1.0) * (0.25 if els in used else 1.0)
        if els in merged:
            merged[els][1] += w
        else:
            merged[els] = [els, w, sig]
    return [tuple(v) for v in merged.values()]


def hall_round(H):
    """Dress a hall (a corridor, an entry, a landing) one of the ways the game's halls of the house's
    culture are dressed (hallsurvey.py): a runner down the middle, benches, a chest, a small table with a
    candle and a chair, a bookshelf, a shrine at the far end, a group of stores or a pair of urns at the end
    or in a corner, a planter, a standing lamp; tapestries and banners by the wall decor that follows (the
    hang factor returned). Everything stands with its back to a wall, keeps HALL_CLEAR off the walking line
    (from every way in or out of a tile to its middle), off the doorways (the doorway clearances in taken)
    and wholly off the runner, at the game's spacing, and the hall holds no more than about the game's
    density for the culture. H: the furnish closures and state (see the call in furnish()). Returns the
    factor the room's wall hangings are multiplied by."""
    import hallsurvey
    import roomsurvey
    db, room, T, rng, fl = H['db'], H['room'], H['T'], H['rng'], H['fl']
    culture = hallsurvey.culture_of(H.get('cell_style') or '') or HALL_STYLES.get(H.get('style'))
    if culture in hallsurvey.DUNGEONS:
        culture = None
    rule = hallsurvey.rule(db, culture or '*')
    used = H['used']
    menu = hall_menu(rule, used)
    if not menu:
        return 1.0

    def draw(tried):
        """One of the culture's ways, by the game's counts, not one already tried for this hall."""
        left = [m for m in menu if m[0] not in tried] or menu
        r = rng.random() * sum(w for _e, w, _s in left)
        for e, w, s in left:
            r -= w
            if r <= 0:
                return e, s
        return left[-1][0], left[-1][2]
    tiles = room['_tiles']
    n_tiles = room['tiles'] * (T / 256.0) ** 2
    units = [{'x0': t['x'] - T / 2, 'y0': t['y'] - T / 2, 'x1': t['x'] + T / 2, 'y1': t['y'] + T / 2, 'pat': t['pat'], 'axis': None} for t in tiles]
    lines = [seg for u in units for seg in hallsurvey.walk_lines(u)]
    rcx, rcy = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
    # how full the game's halls of the culture are: floor things per tile (the stores and lamps counted)
    per_tile = (rule or {}).get('floor_per_tile') or 0.7
    cap = int(math.ceil(per_tile * n_tiles * 1.5)) + 1
    mine = [p for p in H['placed'] if p.get('room') == room['name']]
    n_floor = [sum(1 for p in mine if p['type'] in ('STAT', 'CONT', 'ACTI') and p.get('b')
                   and p['p'][2] + p['b'][2] * (p.get('s') or 1.0) < fl + 30
                   and roomsurvey.family_of(db, p['id'], p['type']) not in ('rug', None))]
    # (the rugs already in the hall: what the round stands, it stands wholly off them)
    rug_boxes = [o for o, f in H['rugs'] if abs(f - fl) < 60 and _overlaps(o, (room['x_min'], room['y_min'], room['x_max'], room['y_max']), 0)]
    # the doorways of this floor, at the middle of their frames (a door's own point is often at its hinge):
    # the round keeps HALL_DOOR from them, the game's distance, instead of furnish's wide door clearances
    frames = [o for o in H['openings'] if 'jamb' in o['id'].lower() or 'doorway' in o['id'].lower()]
    door_pts = []
    for o in H['openings']:
        if abs(o['p'][2] - fl) > 200:
            continue
        jb = [j for j in frames if math.hypot(j['p'][0] - o['p'][0], j['p'][1] - o['p'][1]) < 140] if o['type'] == 'DOOR' else []
        door_pts.append((jb[0]['p'][0], jb[0]['p'][1]) if jb else (o['p'][0], o['p'][1]))
    all_pts = [(o['p'][0], o['p'][1]) for o in H['openings']]

    def fits_hall(box):
        """In the room and clear of what stands here, of the clearings that are not a doorway's (a stair's
        landing stays clear), and HALL_DOOR from every doorway's middle."""
        if not H['fits_raw'](box):
            return False
        for o in H['taken']:
            if not o[3] or not (o[1] < fl + 150 and o[2] > fl + 4) or not _overlaps(box, o[0]):
                continue
            mx, my = (o[0][0] + o[0][2]) / 2, (o[0][1] + o[0][3]) / 2
            if any(abs(mx - px) < 2 and abs(my - py) < 2 for px, py in all_pts):
                continue                     # (a door's own wide clearance: the round keeps its own distance)
            return False
        return all(math.hypot(max(box[0] - px, 0, px - box[2]), max(box[1] - py, 0, py - box[3])) >= HALL_DOOR for px, py in door_pts)
    here = []                                # (x, y, kind) of what this round stood
    trace = H['trace']
    why = Counter()                          # (why spots were refused: for the trace)

    def tile_at(sl):
        k = _tile_of(sl['x'] + sl['in'][0] * 20, sl['y'] + sl['in'][1] * 20, room, T)
        return next((t for t in tiles if k and (t['x'], t['y']) == k), None)

    def slot_where(sl):
        """'end' for the far wall of a dead end (three walls), else 'side'."""
        t = tile_at(sl)
        if t is None:
            return 'side'
        walls = [s for s in STEP if t['pat'][s] == 'wall']
        if len(walls) >= 3:
            op = next((s for s in STEP if s not in walls), None)
            if op and sl['side'] == OPP[op]:
                return 'end'
        return 'side'

    def try_spot(rid, sl, along, need):
        b = mapdata.object_bounds(db, db.resolve_id(rid))
        if not b:
            return None
        rot = _turn_to_face(front_of(db, rid), sl['in'])
        box0 = _footprint(b, rot, 0, 0)
        depth_back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sl['in']]
        ax, ay = -sl['in'][1], sl['in'][0]
        x = sl['x'] + sl['in'][0] * (depth_back + 2) + ax * along
        y = sl['y'] + sl['in'][1] * (depth_back + 2) + ay * along
        box = _footprint(b, rot, x, y)
        st = H['settle'](b, rot, x, y, sl['in'], box)
        if st is None:
            why['ledge'] += 1
            return None
        x, y, box = st
        if not fits_hall(box):
            why['taken'] += 1
            return None
        if any(_overlaps(box, rb, 0) for rb in rug_boxes):
            why['runner'] += 1
            return None
        if hallsurvey.clear_of((box[0], box[1], 0, box[2], box[3], 0), lines, (rcx, rcy)) < need:
            why['line'] += 1
            return None
        return x, y, rot, box

    def place(kind, where='side', spacing=None, near=None, within=None, rid=None):
        """One thing of the kind with its back to a wall of the hall ('end': the far wall of a dead end
        first, then the sides), spread from what the round stood (or beside `near`); its record or None."""
        if n_floor[0] >= cap:
            why['full'] += 1
            return None
        rid = rid or H['pick'](kind)
        if not rid:
            why['no ' + kind] += 1
            return None
        spacing = T * 0.9 if spacing is None else spacing
        slots = list(H['slots'])
        rng.shuffle(slots)
        if near is not None:
            slots.sort(key=lambda sl: math.hypot(sl['x'] - near[0], sl['y'] - near[1]))
            if within is not None:
                slots = [sl for sl in slots if math.hypot(sl['x'] - near[0], sl['y'] - near[1]) <= within + T / 2]
            alongs = (0, -72, 72, -100, 100)
        else:
            if where == 'end':
                slots.sort(key=lambda sl: slot_where(sl) != 'end')
            else:
                # (the far ones first: things spread down the hall as the game's are, a bench a tile and a half apart)
                slots.sort(key=lambda sl: -min([math.hypot(sl['x'] - p[0], sl['y'] - p[1]) for p in here] or [T * 9]))
            alongs = (0, -56, 56)
        for sl in slots:
            need = HALL_END_CLEAR if slot_where(sl) == 'end' else HALL_CLEAR
            for along in alongs:
                s = try_spot(rid, sl, along, need)
                if not s:
                    continue
                if near is not None and within is not None and math.hypot(s[0] - near[0], s[1] - near[1]) > within:
                    continue
                if any(k == kind and math.hypot(s[0] - px, s[1] - py) < spacing for px, py, k in here):
                    why['spacing'] += 1
                    continue
                rec = H['put'](rid, s[0], s[1], s[2], floor=fl, room=room['name'], ledge=H.get('ledge'))
                if not rec:
                    why['put'] += 1
                    return None
                H['taken'].append((s[3], fl, fl + 200, False))
                here.append((s[0], s[1], kind))
                n_floor[0] += 1
                H['got'].append(rid)
                return rec
        return None

    def runner(els):
        """A long narrow rug down the longest straight run of the hall's tiles, lying in its middle."""
        if any(abs(f - fl) < 60 and _overlaps(o, (room['x_min'], room['y_min'], room['x_max'], room['y_max']), 0) for o, f in H['rugs']):
            return None                      # (the hall has its rug already)
        best = None
        for along_x in (True, False):
            rows_ = {}
            for t in tiles:
                c0 = t['y'] if along_x else t['x']
                rows_.setdefault(round(c0 / 8), (c0, []))[1].append(t['x'] if along_x else t['y'])
            for c0, vs in rows_.values():
                vs.sort()
                run = [vs[0]]
                for v in vs[1:] + [None]:
                    if v is not None and abs(v - run[-1] - T) < 24:
                        run.append(v)
                        continue
                    if best is None or len(run) > best[0]:
                        best = (len(run), along_x, c0, run[0], run[-1])
                    if v is not None:
                        run = [v]
        if best is None:
            return None
        n_, along_x, c_, a0, a1 = best
        mid = (a0 + a1) / 2
        x, y = (mid, c_) if along_x else (c_, mid)
        # (a narrow one, when things are to stand by the walls too: they stand wholly off it)
        narrow = 120 if len(els) > 2 else 170
        rugs = sorted([r for r in H['big_rugs'] if r[2] >= 1.6 * r[3] and r[3] <= narrow and r[2] <= n_ * T - 30], key=lambda r: -r[2])
        if not rugs:
            why['no runner rug'] += 1
        for rug in rugs[:6]:
            s = H['rug_at'](rug, x, y, along_x, clearings=False)
            if s and H['put'](rug[0], s[0], s[1], s[2], floor=fl, flat=True, room=room['name']):
                H['rugs'].append((s[3], fl))
                rug_boxes.append(s[3])
                H['got'].append(rug[0])
                return rug[0]
            why['runner refused'] += 1
        return None

    def by_door(kind):
        """One of the kind beside a doorway of the hall (HALL_DOOR off its middle, within 190), or None."""
        pts = [p for p in door_pts if room['x_min'] - 40 <= p[0] <= room['x_max'] + 40 and room['y_min'] - 40 <= p[1] <= room['y_max'] + 40]
        rng.shuffle(pts)
        for pt in pts:
            rec = place(kind, near=pt, within=190, spacing=0)
            if rec:
                return rec
        return None

    def lay(els):
        """Stand the way's floor pieces; what was laid, by kind."""
        laid = []
        if 'runner' in els and runner(els):
            laid.append('runner')
        if 'shrine' in els:
            rec = place('shrine', where='end')
            if rec:
                laid.append('shrine')
                H['dress'](rec, H['purpose'])
        if 'table' in els:
            for _try in range(3):
                tid = H['pick']('table')
                tb = mapdata.object_bounds(db, db.resolve_id(tid)) if tid else None
                if not tb or min(tb[3] - tb[0], tb[4] - tb[1]) > 90 or max(tb[3] - tb[0], tb[4] - tb[1]) > 170:
                    continue                 # (a hall's table is a small one: a side table, not the dining table)
                rec = place('table', where='end', rid=tid)
                if not rec:
                    continue
                laid.append('table')
                # a candle on it, as the game lights its hall tables, and a chair beside it
                cid = H['pick']('candle')
                cb = mapdata.object_bounds(db, db.resolve_id(cid)) if cid else None
                if cb:
                    top_ = rec['p'][2] + rec['b'][5] * (rec.get('s') or 1.0)
                    if H['put'](cid, rec['p'][0], rec['p'][1], rng.uniform(0, 2 * math.pi), on_top=True, at_z=top_ - cb[2], room=room['name'], on_ref=rec.get('k')):
                        laid.append('candle')
                if 'chair' in els and place('chair', near=(rec['p'][0], rec['p'][1]), within=170, spacing=0):
                    laid.append('chair')
                break
        for kind in ('bookshelf', 'cupboard', 'chest'):
            if kind in els:
                rec = place(kind)
                if rec:
                    laid.append(kind)
                    if kind == 'bookshelf':
                        H['dress'](rec, H['purpose'])
        if 'bench' in els:
            for _ in range(1 + (n_tiles >= 4) + (n_tiles >= 7)):
                if place('bench', spacing=T * 1.4):
                    laid.append('bench')
        if 'chair' in els and 'table' not in els:
            for _ in range(1 + (rng.random() < 0.4)):
                if place('chair', spacing=T * 0.5):
                    laid.append('chair')
        if 'stores' in els:
            kinds = ['crate', 'barrel', 'sack', 'basket']
            first = place(rng.choice(kinds), where='end')
            if first:
                laid.append('stores')
                for _ in range(rng.choice((1, 1, 2))):
                    if not place(rng.choice(kinds), near=(first['p'][0], first['p'][1]), within=150, spacing=0):
                        break
                    laid.append('stores')
        if 'urns' in els:
            first = by_door('urn') or place('urn', where='end')
            if first:
                laid.append('urn')
                # (the game's hall urns stand in twos: the nearest urn 60 off, Hlaalu)
                if rng.random() < 0.6 and place('urn', near=(first['p'][0], first['p'][1]), within=130, spacing=0):
                    laid.append('urn')
        if 'planter' in els:
            # (by a doorway, where the game stands a hall's planter, or beside what the round stood: never a
            # lone pot at a plain wall)
            rec = by_door('planter') or (place('planter', near=here[0][:2], within=120, spacing=0) if here else None)
            if rec:
                laid.append('planter')
                H['dress'](rec, H['purpose'])
        return laid

    # a way whose floor pieces this hall can't take (none of them fits) gives way to another, twice at most
    tried = []
    for _attempt in range(3):
        els, sig = draw(tried)
        tried.append(els)
        laid = lay(els)
        if laid or not [e for e in els if e != 'cloth']:
            break
    used.append(els)
    # a standing lamp, as often as the culture's halls stand one (Redoran's lamps by the doorways)
    lamp_ = ((rule or {}).get('kinds') or {}).get('light:lamp') or {}
    if lamp_ and (lamp_.get('place') or {}).get('floor', 0) >= 0.5 * (lamp_.get('n') or 1) and rng.random() < (lamp_.get('runs_with') or 0) * 0.6:
        if H['stand_light']():
            laid.append('lamp')
    trace.append((room['name'], 'hall', '+'.join(els) or 'bare', 'the %s halls\' way (%s)%s: %s%s' % (
        culture or 'game\'s', sig, ' after %d that would not fit' % (len(tried) - 1) if len(tried) > 1 else '',
        ', '.join(laid) or 'nothing more', ' [refused: %s]' % ', '.join('%s %d' % kv for kv in why.most_common()) if why else '')))
    return 1.6 if 'cloth' in els else 1.0


def _tile_of(x, y, room, T):
    """The room tile (x, y) a point is on, or None."""
    for t in room['_tiles']:
        if abs(x - t['x']) <= T / 2 and abs(y - t['y']) <= T / 2:
            return (t['x'], t['y'])
    return None


def window_tiles(room, refs, T):
    """The room's tiles whose wall piece has a window in it (the kit's window pieces, by id: placesurvey.WINDOW),
    on this floor: {(x, y)}. Nothing hangs on their walls, and a planter or a basket stands under them."""
    import placesurvey
    out = set()
    for a in refs:
        if not (a.get('arch') and a.get('b') and placesurvey.WINDOW.search(a['id'].lower())):
            continue
        if not (room['floor'] - 60 <= a['p'][2] <= room['floor'] + 300):
            continue
        t = _tile_of(a['p'][0], a['p'][1], room, T)
        if t is not None:
            out.add(t)
    return out


def house_hangings(db, decor, rng, band=None):
    """The wall things for one house: the game's own houses keep to a couple of kinds of tapestry or
    banner (half of them use one or two), so the house gets two, picked from the most used, and up to two
    of each other kind (racks, herbs...). Also, as wallsurvey.py found: a hanger or banner post that is
    almost never without its banner isn't hung on its own (a banner goes up with what it hangs from).
    band: a Rich or Exquisite house takes its two from the rich tier the game hangs in its rich homes
    (framed paintings, the ornate tapestries: wealthsurvey.decor_tiers) when the palette has two of them,
    a Poor or Modest one from the plain."""
    import wallsurvey
    import wealthsurvey
    decor = [d for d in decor if wallsurvey.hangs_alone(db, d[0]) or wallsurvey.partner(db, d[0])]
    # (and no torn hangings from ruins and dungeons in a lived-in place; nothing is hung in a ruin)
    decor = [d for d in decor if not re.search(r'dngruin|_ruin|ruins_|dng_|dngcryp|crypt', d[0].lower())]
    out, count = [], {}
    cloth = [d for d in decor if d[2] in ('tapestry', 'banner', 'painting')]
    top = cloth[:4]
    rng.shuffle(top)
    keep = {d[0] for d in top[:2]}
    tier = {d[0]: wealthsurvey.decor_tier(db, d[0], 'hang') for d in cloth}
    rich = [d for d in cloth if tier[d[0]] == 'rich']
    poor_ = [d for d in cloth if tier[d[0]] == 'poor']
    plain = [d for d in cloth if tier[d[0]] is None]
    if band == 'exquisite' and len(rich) >= 2:
        # (the game's exquisite homes: over half their hangings of the rich tier; both kinds from it)
        keep = {d[0] for d in rng.sample(rich[:4], 2)}
    elif band == 'rich' and rich:
        # (its rich homes: two in five of the rich tier, the rest plain, never the poor tier's weaves: one
        # kind from the rich tier and one of neither tier, both from the rich tier when there is nothing else)
        r0 = rng.choice(rich[:4])
        rest = plain[:4] or [d for d in rich[:4] if d is not r0]
        keep = {r0[0]} | ({rng.choice(rest)[0]} if rest else set())
    elif band in ('poor', 'modest') and (poor_ or plain):
        # (the poor tier the game hangs in its poor homes first, then whatever is of neither tier)
        lst = (poor_[:4] + plain[:4])[:4] if len(poor_) < 2 else poor_[:4]
        keep = {d[0] for d in rng.sample(lst, min(2, len(lst)))}
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
            # (not a bed: the game hangs its tapestry over the bed's head, Goldstone's and Gormash's
            # bedrooms every one; counting the bed as tall left every bed's wall bare)
            _tall[key] = roomsurvey.family_of(db, r['id'], r['type']) in ('counter', 'shelf', 'cupboard', 'bookshelf', 'shrine')
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
    # (no hanging on a window tile's wall: the kits' window pieces are wall pieces named for the window,
    # in_c_plain_room_side_window and the like; the user's "placing tapestries over windows makes both
    # look bad". The game hangs over a window WINDOW_RATE of the time (wallsurvey2 v4: 'hung_over'))
    wt = window_tiles(room, refs, T)
    if wt:
        n0 = len(spots)
        spots = [sp for sp in spots if _tile_of(sp['x'] + sp['in'][0] * 30, sp['y'] + sp['in'][1] * 30, room, T) not in wt]   # (30 in from the face: the spot's own tile)
        last_trace.append((room['name'], 'window', '-', '%d of %d wall spots on window tiles %s dropped' % (n0 - len(spots), n0, sorted(wt))))
        if not spots:
            return []
    rng.shuffle(spots)
    # tapestries flanking a stair (wallsurvey2 v3: 63% of the game's flights have a flat hanging within a
    # tile and a half, 58% of those one either side of the flight): the spots nearest a flight on this
    # floor come first, at the game's rate, the one across the flight's line as its twin (the same model)
    extra = 0
    st_rule = (wallsurvey2.ready(db) or {}).get('stairs') or {}
    if (st_rule.get('hang') or 0) >= 0.2 and st_rule.get('n', 0) >= 20:
        for st in refs:
            if not (st.get('arch') and re.search(r'stair|ramp', st['id'].lower())) or abs(st['p'][2] - floor) > 100:
                continue
            if not (room['x_min'] - T <= st['p'][0] <= room['x_max'] + T and room['y_min'] - T <= st['p'][1] <= room['y_max'] + T):
                continue
            if rng.random() >= st_rule['hang']:
                continue
            near_ = sorted([sp for sp in spots if math.hypot(sp['x'] - st['p'][0], sp['y'] - st['p'][1]) < T * 1.6],
                           key=lambda sp: math.hypot(sp['x'] - st['p'][0], sp['y'] - st['p'][1]))
            if not near_:
                continue
            along_x = abs(math.sin(st['p'][5])) < 0.5
            side_of = lambda sp: 1 if ((sp['y'] if along_x else sp['x']) > (st['p'][1] if along_x else st['p'][0])) else -1
            first = near_[0]
            first['rank'] = -2
            extra += 1
            if rng.random() < (st_rule.get('hang_pair') or 0.5):
                other = next((sp for sp in near_[1:] if side_of(sp) != side_of(first)), None)
                if other is not None:
                    other['rank'] = -1
                    first['twin'] = other
                    extra += 1
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
    want = max(want, extra)                          # (the stair's flanking pair comes whatever the room's count)
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
            # its match: the spot across the stair's line (its twin), or the spot mirrored about the doorway
            # or the wall's middle, takes the same model next (two of a kind flanking a stair or a door,
            # or set either side of a wall's middle)
            tw = sp.get('twin')
            if tw is not None and tw in spots:
                tw['for'] = rid
                force = tw
            elif abs(sp['mirror'] - (sp['x'] if sp['line'][0] in ('N', 'S') else sp['y'])) > 20:
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
    n = nb = 0
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
        ds_ = shelfsurvey.survey(db, rid)['dressings']
        n = len(ds_)
        # (how many of them are mostly books: "Fill with books" shows when there are any)
        nb = sum(1 for d in ds_ if d['objects'] and sum(1 for o in d['objects'] if o['kind'] == 'BOOK') >= 0.6 * len(d['objects']))
    dressed = bool(c) and any(v.get('on') == ref and not v.get('deleted') for v in c['refs'].values())
    return {'dressable': n > 0, 'dressed': dressed, 'model': rid, 'kind': fam_, 'dressings_known': n, 'book_dressings': nb if n else 0}


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
        return {'room': None, 'name': None, 'purpose': None, 'furnished': 0, 'purposes': list(RECIPES), 'pieces': 0}
    # (the pieces in it "Dress the whole room" would dress: furniture the game dresses, by kind)
    import roomsurvey as _rs2
    T = info['tile'] or 256
    n_pieces = 0
    for r in mapdata.cellmap(db, cell_key).get('refs', []):
        if r.get('arch') or not r.get('b') or r['type'] not in ('STAT', 'ACTI', 'CONT'):
            continue
        if not any(abs(r['p'][0] - tl['x']) <= T / 2 and abs(r['p'][1] - tl['y']) <= T / 2 for tl in rm['_tiles']):
            continue
        if not (-60 <= r['p'][2] + r['b'][2] * (r.get('s') or 1.0) - rm['floor'] < 300):
            continue
        if _rs2.family_of(db, r['id'], r['type']) in PIECE_KINDS + ('bed', 'chest', 'crate', 'barrel', 'bench'):
            n_pieces += 1
    return {'room': rm['id'], 'name': rm['name'], 'purpose': rm['purpose'], 'tiles': rm['tiles'], 'traced': bool(rm.get('traced')),
            'furnished': len(room_refs(db, cell_key, rm, info['tile'] or 256)), 'purposes': list(RECIPES), 'pieces': n_pieces}


SKETCH_KINDS = ('bed', 'table', 'chair', 'bench', 'bookshelf', 'shelf', 'cupboard', 'chest', 'rug', 'counter', 'shrine', 'fire',
                'planter', 'screen', 'rack', 'bath', 'target', 'bedroll')     # (what a sketch furnish lays: the big pieces, no clutter, riders or lights)


def furnish(db, cell_key, plan=None, seed=None, walls=True, walls_only=False, replace=False, level=None, like=None, piece=None,
            room=None, purpose=None, add=False, dress_room=False, commit=True, sketch=False, books=False):
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
    room, name, purpose}. The user: "We need this feature for Rooms".
    dress_room (with room): every dressable piece in that room is dressed the game's way, as "Dress
    this" does one piece (its earlier dressing off first), all as one undoable change: between one
    piece and a whole house. Returns {placed, removed, pieces, room, name}.
    commit: False leaves the change uncommitted (the caller commits several as one).
    sketch: only the big pieces (SKETCH_KINDS: the bed, the tables and seats, the shelves, the rugs, the chests,
    the set pieces' same), no clutter groups, dressings, riders, wall decor or lights: the furniture sketch in
    the "Add a room" ghost (the extend session's), fast, with last_placed holding just the sketch."""
    editing._require_project(db)
    if sketch:
        walls = False
    if room is not None and dress_room:
        info0 = rooms(db, cell_key)
        room_rec = next((r for r in info0['rooms'] if r['id'] == room), None)
        if room_rec is None:
            raise EditError('No such room here any more.')
        T0 = info0['tile'] or 256
        import roomsurvey as _rs1
        pieces = []
        for r in mapdata.cellmap(db, cell_key).get('refs', []):
            if r.get('arch') or not r.get('b') or r['type'] not in ('STAT', 'ACTI', 'CONT', 'DOOR'):
                continue
            if not any(abs(r['p'][0] - tl['x']) <= T0 / 2 and abs(r['p'][1] - tl['y']) <= T0 / 2 for tl in room_rec['_tiles']):
                continue
            bottom_ = r['p'][2] + r['b'][2] * (r.get('s') or 1.0)
            if not (-60 <= bottom_ - room_rec['floor'] < 300):
                continue
            if _rs1.family_of(db, r['id'], r['type']) not in PIECE_KINDS + ('bed', 'chest', 'crate', 'barrel', 'bench'):
                continue
            if piece_info(db, cell_key, r['k'])['dressable']:
                pieces.append(r['k'])
        rng0 = random.Random(seed if seed is not None else cell_key)
        total = removed_all = done_n = 0
        for k in pieces:
            try:
                out = furnish(db, cell_key, piece=k, replace=True, seed=rng0.randrange(1 << 30), level=level, commit=False)
            except EditError:
                continue                     # (none of the game's dressings of that one fit as it stands)
            total += out['placed']
            removed_all += out['removed']
            done_n += 1
        if not total:
            raise EditError('Nothing of the game\'s fits on the %s\'s pieces as they stand (%d the game dresses).' % (room_rec['name'], len(pieces)))
        db.sync_project()
        import modelcache
        modelcache.save()
        editing.commit(db, 'Dressed the %s the game\'s way (%d things on %d pieces)' % (room_rec['name'], total, done_n))
        return {'placed': total, 'removed': removed_all, 'pieces': done_n, 'room': room_rec['id'], 'name': room_rec['name']}
    room_rec = None
    if room is not None:
        info0 = rooms(db, cell_key)
        room_rec = next((r for r in info0['rooms'] if r['id'] == room), None)
        if room_rec is None:
            raise EditError('No such room here any more.')
        if purpose and purpose not in RECIPES and purpose != 'none':
            raise EditError('"%s" is not a kind of room Auto-furnish knows.' % purpose)
        # (a traced cave's tunnel is left bare in the whole-place furnish; asked for by itself, a hall)
        plan = [{'id': room, 'purpose': purpose or (room_rec['purpose'] if room_rec['purpose'] != 'none' else 'hall')}]
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
        raise EditError('No rooms found here: no floor a person could stand on was found in the building\'s pieces '
                        '(Auto-furnish reads the floors, walls and doorways of any interior, room pieces or not).')
    T = info['tile']
    rooms_by_name = {r['name']: r['id'] for r in info['rooms']}     # (put() tags each thing with its room)
    fam, style = candidates(db, cell_key)
    house_culture = STYLE_SET.get(style)            # (put(): no furniture of another culture, by any path)
    house_tier = fam.get('_tier')                   # (and not the make the palette lost: no rich bench in a poor house)
    if L:
        # the band's makes of furniture first (the poor Dunmer set for a poor house, the rich one for a
        # rich house; the palette's order within a make is kept, so the place's own pieces still lead)
        for k in list(fam):
            if k in FAMILIES and fam[k]:
                fam[k] = wealthsurvey.order_by_tier(fam[k], L['tiers'], L.get('keep', 1))
    extras_left = list(L['extras']) if L else []      # the trade's set pieces still to lay (once a house)
    if not fam.get('fire'):
        fam['fire'] = hearth_models(db, STYLE_SET.get(style, 'imperial'), pits=style in ('Ashlander', 'Cave', 'Mine'))     # (a kitchen's hearth; none in a Hlaalu house: "a log fire in the middle of the floor")
    if style not in ('Ashlander', 'Cave', 'Mine') and fam.get('fire'):
        # (the palette of a house may hold a firepit or a campfire from the places like it: a house's
        # kitchen fire is a fireplace, a stove or an oven, never a camp's pit; the user's "a campfire in a
        # rich home. Fireplaces for kitchen should be stoves, not actual fireplaces, unless you're in a cave")
        fam['fire'] = [f for f in fam['fire'] if not re.search(r'pit|campfire|cookingfire|cookfire|bonfire', f.lower())]
    # (the room-kind survey's pieces the palettes seldom hold: a bathing room's tub, an armoury's rack, a
    # training room's dummy)
    if not fam.get('bath'):
        fam['bath'] = bath_models(db, STYLE_SET.get(style, 'imperial'))
    if not fam.get('rack'):
        fam['rack'] = [i for i in ('furn_uni_weaponrack_01', 'furn_de_weaponrack_01', 't_com_furn_weaponrack_01') if db.resolve_id(i) is not None]
    if not fam.get('target'):
        fam['target'] = [i for i in ('furn_practice_dummy', 'furn_archery_target', 't_com_furn_practicedummy_01') if db.resolve_id(i) is not None]
    if not fam.get('loom'):
        fam['loom'] = trade_looms(db, STYLE_SET.get(style, 'imperial'))      # (a clothier's: tradesurvey)
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
    # (a dreugh's grotto, by its name or its own dreugh-made building pieces: the only place for their altars)
    grotto = 'dreugh' in ((mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key).lower() \
        or any(r['id'].lower().startswith('t_dreu_') and '_furn_' not in r['id'].lower() for r in mapdata.cellmap(db, cell_key).get('refs', []))
    if rough:
        for rm in info['rooms']:
            if re.match(r'^room \d+$', (rm['name'] or '').lower()) or not rm['name']:
                # (a traced cave's tunnel stays bare and walkable, as the game leaves its own: the lab's beds
                # and chests across Shulk's tunnels, 2026-10-24; furnished as a hall when asked for by itself)
                rm['purpose'] = 'none' if info.get('traced') and rm['purpose'] == 'hall' and plan is None else rough
    rng = random.Random(seed if seed is not None else cell_key)
    if STYLE_CYCLE and fam.get('_borrowed') and not L and not like:
        # (unsure of the style, from few places like this one or none: each draw puts one of the likely makes of
        # furniture first, so furnishing again shows another. The user: "cycle through styles in cases where you
        # aren't certain, and then the user can re-furnish to see another style")
        makes = Counter(_make_of(rid) for k in STYLE_KINDS for rid in fam.get(k) or [] if _make_of(rid))
        top = [mk for mk, n in makes.most_common(4) if n >= 3]
        if len(top) > 1:
            pick_ = top[random.Random((seed if seed is not None else 0) * 7 + 3).randrange(len(top))]
            for k in STYLE_KINDS:
                if fam.get(k):
                    fam[k] = [r for r in fam[k] if _make_of(r) == pick_] + [r for r in fam[k] if _make_of(r) != pick_]
            fam['_lead'] = pick_
    decor = house_hangings(db, wall_decor(db, cell_key), rng, band=L['band'] if L else None) if (walls or walls_only) else []
    rug_tier, rug_rich_p = {}, None
    if L and L.get('band') in ('rich', 'exquisite', 'poor', 'modest') and fam.get('rug'):
        # (the band's rugs: a poor house never the patterned rug the game keeps for its rich homes, a rich
        # house never the poor tier's plain one; and a rich house's rug is of the rich tier at the game's
        # rate for the band, one in four in its rich homes, rolled rug by rug where one is laid, since the
        # rug itself is chosen by its fit under the table or by the bed)
        rug_tier = {r: wealthsurvey.decor_tier(db, r, 'rug') for r in fam['rug']}
        drop_ = 'poor' if L['band'] in ('rich', 'exquisite') else 'rich'
        kept_ = [r for r in fam['rug'] if rug_tier[r] != drop_]
        if kept_:
            fam['rug'] = kept_
        sh_ = ((wealthsurvey.decor_tiers(db) or {}).get('shares') or {}).get(L['band']) or {}
        if L['band'] in ('rich', 'exquisite'):
            rug_rich_p = ('rich', max(0.25, sh_.get('rug_rich') or 0.0))     # (exquisite: too few rugs seen to say; the rich rate at least)
        else:
            rug_rich_p = ('poor', max(0.12, sh_.get('rug_poor') or 0.0))     # (the poor homes' own plain rug, one in four there)
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
    # the big rugs, the big planters and the kiln hearths the game's own places lay, which the palette never
    # holds: the map reader calls any static over 200 x 200 "architecture" (mapdata.is_architecture), so
    # furn_de_rug_big_04, furn_planter_03 and furn_redoran_hearth_02 were never laid anywhere. The surveys
    # that read them by name (redoransurvey, gardensurvey) give them back to the palette, in their styles
    import redoransurvey as _rsv
    import gardensurvey as _gsv
    redoran = _rsv.is_redoran(cell_style)
    if redoran:
        have_ = {x.lower() for x in (fam.get('rug') or [])}
        for rid_ in _rsv.big_rugs(db)[:8]:
            if rid_ not in have_:
                fam.setdefault('rug', []).append(rid_)
        hearth_ = [h for h in _rsv.hearth_ids(db) if h not in [x.lower() for x in (fam.get('fire') or [])]]
        if hearth_:
            fam['fire'] = hearth_ + list(fam.get('fire') or [])      # (the kiln hearth first: every Redoran kitchen's)
    have_ = {x.lower() for x in (fam.get('planter') or [])}
    for rid_ in _gsv.models_for(db, style, cell_style)[:4]:
        if rid_ not in have_:
            fam.setdefault('planter', []).append(rid_)
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
        elif r.get('b') and r.get('arch') and (r['b'][5] - r['b'][2]) * (r['s'] or 1) > 30 \
                and not _is_floor_piece(db, r['id']):
            # (rugs are flat; a traced floor's tile still holds the rubble, the column or the boulder standing
            # on part of it: the lab's beds and tables into Dun Akafell's rubble and pillars, 2026-10-24)
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

    def wall_by_ray(b, rot, x, y, z, front, scale=1.0):
        """A wall right behind a hung thing's back by the building's real surfaces: from a hand's width
        inside its back, at its middle height, a ray out through the back hits the building within 40.
        The tile patterns say which sides are walls; a kit piece's doorway or a post is not one."""
        if not _scene:
            floor_by_mesh(x, y, z)
        if not _scene[0].tris:
            return True
        f = front or (0.0, -1.0)
        c_, s_ = math.cos(rot), math.sin(rot)
        fx, fy = f[0] * c_ + f[1] * s_, -f[0] * s_ + f[1] * c_          # (the front, turned as it stands)
        box = _footprint([v * scale for v in b], rot, x, y)
        depth = max(box[2] - box[0], box[3] - box[1]) if abs(fx) < 0.5 and abs(fy) < 0.5 else (box[3] - box[1] if abs(fy) > abs(fx) else box[2] - box[0])
        bx_, by_ = x - fx * (depth / 2 - 6), y - fy * (depth / 2 - 6)    # (just inside the back)
        zm = z + (b[2] + b[5]) / 2 * scale
        hit = _scene[0].nearest((bx_, by_, zm), (-fx, -fy, 0.0), 40)
        return hit is not None

    def ceiling_over(x, y, z0, reach=900):
        """The height of the building's surface straight over (x, y) from z0 up, by the real geometry
        of the pieces (the way the health check looks for a ceiling), or None when nothing is above:
        an open hall, a two-storey void, a stairwell."""
        if not _scene:
            floor_by_mesh(x, y, z0)
        hit = _scene[0].nearest((x, y, z0), (0.0, 0.0, 1.0), reach)
        return None if hit is None else z0 + hit[0]

    def beam_near(x, y, fl, reach=160):
        """A beam piece within reach of (x, y) a light could hang from where no ceiling is above: the
        nearest point under it, and the height of its underside, as (x, y, z); None when there is none."""
        best = None
        for r in refs:
            if not (r.get('arch') and r.get('b') and BEAM.search(r['id'].lower())):
                continue
            s_ = r.get('s') or 1.0
            bottom = r['p'][2] + r['b'][2] * s_
            if not (fl + 100 < bottom < fl + 900):
                continue
            fp_ = _footprint([v * s_ for v in r['b']], r['p'][5], r['p'][0], r['p'][1])
            px, py = min(max(x, fp_[0] + 8), fp_[2] - 8), min(max(y, fp_[1] + 8), fp_[3] - 8)
            d_ = math.hypot(px - x, py - y)
            if d_ > reach:
                continue
            z_ = ceiling_over(px, py, fl + 100)
            if z_ is None or z_ > bottom + 60:
                continue                     # (the ray finds nothing of it: not under the beam after all)
            if best is None or d_ < best[0]:
                best = (d_, px, py, z_)
        return None if best is None else best[1:]

    import hearthsurvey
    _bearers = {}

    def bearer(rid):
        """A hearth: a model that holds a fire (hearthsurvey.is_bearer), not its tools."""
        low = rid.lower()
        if low not in _bearers:
            _bearers[low] = hearthsurvey.is_bearer(db, low)
        return _bearers[low]

    def hearth_near(x, y, z, fl=None, rm=None):
        """A hearth standing here (built in or laid) whose box reaches within the survey's reach of (x, y)
        on this level (z: the height the thing goes at, None for any; fl: the room's floor, which the
        hearth stands on: a log fire upstairs is not the kiln's below it; rm: the room, which the hearth
        stands in: not the dining room's beyond the wall)."""
        for h in surf:
            if not h.get('b') or not bearer(h['id']):
                continue
            s_ = h.get('s') or 1.0
            if z is not None and not (h['p'][2] + h['b'][2] * s_ - 40 <= z <= h['p'][2] + h['b'][5] * s_ + 20):
                continue
            if fl is not None and not (fl - 150 <= h['p'][2] + h['b'][2] * s_ <= fl + 120):     # (a pit or a kiln sunk into the floor; never the storey below)
                continue
            fp = _footprint([v * s_ for v in h['b']], h['p'][5], h['p'][0], h['p'][1])
            if rm is not None and T and not any(abs((fp[0] + fp[2]) / 2 - tl['x']) <= T / 2 + 8 and abs((fp[1] + fp[3]) / 2 - tl['y']) <= T / 2 + 8
                                                for tl in rm['_tiles']):
                continue
            if math.hypot(max(fp[0] - x, 0, x - fp[2]), max(fp[1] - y, 0, y - fp[3])) <= hearthsurvey.REACH + 30:
                return True
        return False

    import tradesurvey
    room_trade = {}                          # room name: the trade it is furnished for (a plain shop: a general trader's)
    _foreign, _heat = {}, {}

    def forge_near(x, y, fl, rm, reach, any_heat=False):
        """A forge or coals standing in this room on its floor (any_heat: or a hearth or a fire light, as a
        smithy's own fire may be) whose box reaches within reach of (x, y); reach None: anywhere in the room."""
        for h in surf:
            if not h.get('b'):
                continue
            k_ = (h['id'].lower(), h['type'])
            if k_ not in _heat:
                _heat[k_] = tradesurvey.heat_of(db, h['id'], h['type'])
            if not _heat[k_] or (not any_heat and _heat[k_] not in tradesurvey.HEAT):
                continue
            s_ = h.get('s') or 1.0
            if fl is not None and not (fl - 150 <= h['p'][2] + h['b'][2] * s_ <= fl + 150):
                continue
            fp = _footprint([v * s_ for v in h['b']], h['p'][5], h['p'][0], h['p'][1])
            if rm is not None and T and not any(abs((fp[0] + fp[2]) / 2 - tl['x']) <= T / 2 + 8 and abs((fp[1] + fp[3]) / 2 - tl['y']) <= T / 2 + 8
                                                for tl in rm['_tiles']):
                continue
            if reach is None or math.hypot(max(fp[0] - x, 0, x - fp[2]), max(fp[1] - y, 0, y - fp[3])) <= reach:
                return True
        return False

    def trade_refuses(rid, tag, x, y, room):
        """Why a trade's piece may not stand here, or None (tradesurvey.py): a smith's anvil or bellows with no
        forge or coals within the reach the game's smiths keep them at (in a smithy its own fire will do), a
        grindstone in a room with no forge; and in a trade's room, a piece another trade is known by that the
        game's rooms of this trade never hold (a smithy's writing set and scales, the user's "accounting desks
        swapped in where forges should be")."""
        if not TRADES:
            return None
        rm_ = next((r for r in info['rooms'] if r['name'] == room), None) if room else None
        tr_ = room_trade.get(room)
        tool_ = tradesurvey.tool_of(rid, tag)
        if tool_:
            reach_ = tradesurvey.REACH[tool_]
            if not forge_near(x, y, rm_['floor'] if rm_ else None, rm_, None if reach_ is None else reach_ + 30, any_heat=tr_ == 'smith'):
                return 'a smith\'s %s with no forge %s: left out' % (tool_, 'in the room' if reach_ is None else 'within %d' % reach_)
        if tr_:
            pc_ = tradesurvey.piece_of(rid, tag)
            if pc_:
                if tr_ not in _foreign:
                    _foreign[tr_] = tradesurvey.foreign(db, tr_)
                if pc_ in _foreign[tr_]:
                    return '%s (%s) in a %s\'s room: the game\'s never hold one' % (tradesurvey.PIECE_NAMES.get(pc_, pc_), rid, tr_)
        return None

    def put(rid, x, y, rot, on_top=False, hang_from=None, floor=None, flat=False, room=None, at_z=None, tilt=(0, 0), scale=1.0, ledge=None, on_ref=None):
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri)
        if not b:
            return None
        tag = db.recs[ri][0]
        if sketch and (on_top or at_z is not None or tag not in ('STAT', 'ACTI', 'CONT') or roomsurvey.family_of(db, rid, tag) not in SKETCH_KINDS):
            return None                      # (a sketch: the big pieces only)
        if tag in mapdata.ITEM_TYPES and abs(scale - 1.0) > 0.001:
            scale = 1.0                      # (a thing that can be picked up is never scaled: the game sets it back to 1 when put down)
        if house_culture and tag in ('STAT', 'ACTI', 'CONT') and 'furn' in rid.lower():
            # (Project Tamriel's rule, by every path a piece comes in: no Dunmer furniture in an Imperial
            # house nor Imperial in a Dunmer one; a counter, a screen, a scene's member or a rack alike)
            import wealthsurvey
            cul = wealthsurvey.culture_of(rid)
            if cul and cul in CULTURE_FORBIDS.get(house_culture, ()):
                last_trace.append((room, 'set', rid, '%s furniture in a %s house: left out' % (cul, house_culture)))
                return None
        tier_ = (L['tiers'][0] if L and L['tiers'] and L['tiers'][0] in ('poor', 'rich') else house_tier)
        if tier_ and tag in ('STAT', 'ACTI', 'CONT') and 'furn' in rid.lower():
            import wealthsurvey
            t_ = wealthsurvey.set_tier(rid)
            if t_ in ('poor', 'rich') and t_ != tier_:
                last_trace.append((room, 'set', rid, 'the %s make in a house of the %s make: left out' % (t_, tier_)))
                return None
        if tag in ('STAT', 'ACTI') and theme != 'temple' and BARE_STONE.search(rid.lower()):
            return None                      # (a bare stone block, slab or pedestal: never furniture in a house, by any path)
        if tag in ('STAT', 'ACTI', 'CONT') and not grotto and DREUGH_MAKE.search(rid.lower()):
            last_trace.append((room, 'set', rid, "the dreugh's make outside a dreugh grotto: left out"))
            return None
        if RIDER_ONLY.search(rid.lower()) and not on_top and at_z is None:
            # (a bath's water sheet, a flame: only ever inside the piece it belongs to, a tub or a hearth
            # standing here already with the sheet's middle over it)
            host = False
            for h in surf:
                if h.get('arch') or not h.get('b') or h['type'] not in ('STAT', 'ACTI', 'CONT'):
                    continue
                hf = _footprint([v * (h.get('s') or 1.0) for v in h['b']], h['p'][5], h['p'][0], h['p'][1])
                if hf[0] - 8 <= x <= hf[2] + 8 and hf[1] - 8 <= y <= hf[3] + 8 and abs(h['p'][2] - z) < 80 \
                        and roomsurvey.family_of(db, h['id'], h['type']) in ('bath', 'fire', 'planter', 'urn'):
                    host = True
                    break
            if not host:
                return None
        if not rough and tag in ('LIGH', 'STAT', 'ACTI', 'MISC', 'CONT'):
            # a hearth is a whole set or nothing, by every path a piece comes in (hearthsurvey): no camp fire
            # in a house, no second fire in a room, and no fire, fire tools or tool stand without the hearth
            # they belong to within reach (the user's kitchen of "fire accessories by crates and a table")
            rm0_ = next((r for r in info['rooms'] if r['name'] == room), None) if room else None
            if tag != 'MISC' and bearer(rid):
                if hearthsurvey.PIT.search(rid.lower()):
                    last_trace.append((room, 'fire', rid, 'a camp fire in a house: left out'))
                    return None
                if rm0_ is not None and any(bearer(h['id']) and rm0_['x_min'] - 40 <= h['p'][0] <= rm0_['x_max'] + 40
                                            and rm0_['y_min'] - 40 <= h['p'][1] <= rm0_['y_max'] + 40 and abs(h['p'][2] - rm0_['floor']) < 150
                                            for h in surf if h.get('b')):
                    last_trace.append((room, 'fire', rid, 'a second fire in the room: left out'))
                    return None
            elif hearthsurvey.tethered(db, rid, tag):
                z0_ = at_z if at_z is not None else floor if floor is not None else (rm0_['floor'] if rm0_ else None)
                # (a forge's coals and fire burn in the forge: tradesurvey's sets)
                if not hearth_near(x, y, z0_, rm0_['floor'] if rm0_ else None, rm0_) and not forge_near(x, y, rm0_['floor'] if rm0_ else None, rm0_, 40):
                    last_trace.append((room, 'fire', rid, 'a fire thing with no hearth within reach: left out'))
                    return None
        if not rough and tag in ('STAT', 'ACTI', 'CONT', 'MISC', 'APPA', 'LIGH'):
            why_ = trade_refuses(rid, tag, x, y, room)
            if why_:
                last_trace.append((room, 'trade', rid, why_))
                return None
        if L and L['cap'] is not None and tag in mapdata.ITEM_TYPES:
            import shelfsurvey
            if shelfsurvey.value_of(db, rid)[1] > L['cap']:
                return None                      # (a band was chosen: nothing dearer than its cap anywhere)
        if L and L['cont_max'] is not None and tag == 'CONT':
            import wealthsurvey      # (put() imports it in its branches above, so it is put()'s own name: a poor house failed here)
            if (wealthsurvey.container_value(db, rid) or 0) > L['cont_max']:
                return None                      # (a poor house, or loot kept worthless: no strongbox of gems on a shelf)
        room_ = next((r for r in info['rooms'] if r['name'] == room), None) if room else None
        low_ = rid.lower()
        is_pot = tag in ('STAT', 'ACTI', 'CONT') and bool(shelfsurvey_PLANTER.search(low_))
        if is_pot and at_z is None and not on_top and hang_from is None and 'hang' in low_:
            # a hanging planter hangs from the ceiling over the spot, as the game's do (the user's "this one
            # is supposed to be a hanging plant" stood on the floor with its hook in the air)
            ceil_ = ceiling_over(x, y, (floor if floor is not None else z) + 100) if floor is not None else None
            if ceil_ is None:
                last_trace.append((room, 'planter', rid, 'a hanging planter with no ceiling over the spot: left out'))
                return None
            at_z = ceil_ - 4 - b[5] * scale
        elif is_pot and at_z is None and not on_top and hang_from is None and max(b[3] - b[0], b[4] - b[1]) * scale < SMALL_POT:
            last_trace.append((room, 'planter', rid, 'a tabletop pot on the floor: left out'))
            return None                  # (a pot a hand wide stands on a table or a shelf, never on the floor)
        elif is_pot and at_z is not None and not on_top and room_ is not None and max(b[3] - b[0], b[4] - b[1]) * scale < SMALL_POT \
                and at_z + b[2] * scale < room_['floor'] + 30:
            # (the same pot set at floor level by a shelf's dressing, beside the shelf: the game's bookshelf
            # dressings stand one there with a sack; a lone tabletop pot on the floor either way)
            last_trace.append((room, 'planter', rid, 'a tabletop pot set on the floor by a dressing: left out'))
            return None
        if on_ref and shelfsurvey_GARDEN.search(low_) and not shelfsurvey_PLANTER.search(low_):
            # a plant in a pot fits its pot: no shrub twice the pot's width nor three times its height, and its
            # bottom in the pot, not stacked on another plant (the user's "small pot, big plant" and the
            # flowers floating a head above their pot)
            base_ = next((p for p in placed if p.get('k') == on_ref), None)
            if base_ is not None and base_.get('b') and shelfsurvey_PLANTER.search(base_['id'].lower()):
                bs_ = base_.get('s') or 1.0
                pw_ = max(base_['b'][3] - base_['b'][0], base_['b'][4] - base_['b'][1]) * bs_
                ph_ = (base_['b'][5] - base_['b'][2]) * bs_
                top_ = base_['p'][2] + base_['b'][5] * bs_
                # (how big a plant the game grows in this very pot: the survey's 90th percentile of plant width
                # and height over the pot's, when the model was seen planted ten times or more; the Imperial
                # tabletop pots take flowers 1.4 to 2.2 times their width. Twice and three times when unknown.)
                import gardensurvey as _gsvf
                M_ = ((_gsvf.ready(db) or {}).get('models') or {}).get(base_['id'].lower()) or {}
                kw_, kh_ = (M_['fit_w'][4] * 1.1, M_['fit_h'][4] * 1.1) if M_.get('with', 0) >= 10 and M_.get('fit_w') else (2.0, 3.0)
                if pw_ < 80 and (max(b[3] - b[0], b[4] - b[1]) * scale > kw_ * pw_ or (b[5] - b[2]) * scale > kh_ * ph_ + 20):
                    last_trace.append((room, 'planter', rid, 'too big a plant for the pot: left out'))
                    return None
                # (a pot up on a table or a shelf: a flower or two that stays low, rooted inside the pot, not
                # a floor pot's tall stem; the user's "too big a pot for a table" was a 93-tall bugloss in it.
                # The game's plants in pots on furniture: median 52 tall, p90 78, p95 92 (203 in 100 places);
                # 85 turns away 7% of them. Rooted outside the pot: 3.4% of the game's.)
                fl_r = next((r_['floor'] for r_ in info['rooms'] if r_['name'] == room), None)
                if fl_r is not None and base_['p'][2] + base_['b'][2] * bs_ > fl_r + 30:
                    if (b[5] - b[2]) * scale > 85.0:
                        last_trace.append((room, 'planter', rid, 'too tall a plant for a pot on a table: left out'))
                        return None
                    bfp_ = _footprint([v * bs_ for v in base_['b']], base_['p'][5], base_['p'][0], base_['p'][1])
                    if not (bfp_[0] - 4 <= x <= bfp_[2] + 4 and bfp_[1] - 4 <= y <= bfp_[3] + 4):
                        last_trace.append((room, 'planter', rid, 'a plant beside a pot on a table, not in it: left out'))
                        return None
                # (floating over the rim is the fault; sunk deep is the game's own way of showing less of a
                # plant, its base hidden in the floor: a pod plant 71 under the rim of a 33-tall pot in the
                # game's gardens of that pot. Its top must still show above the rim.)
                bot_ = base_['p'][2] + base_['b'][2] * bs_
                if at_z is not None and (at_z + b[2] * scale > top_ + 40 or at_z + b[5] * scale < bot_ + ph_ * 0.5):
                    last_trace.append((room, 'planter', rid, 'a plant not in its pot (%.0f over its rim): left out' % (at_z + b[2] * scale - top_)))
                    return None
        if on_top and at_z is None and tag in ('STAT', 'ACTI', 'CONT'):
            # (a pot or a box set on a table by a recipe, not by a game dressing: never into what the
            # dressing already stood there; the user's "plant pot clipping into table clutter")
            fp_ = _footprint([v * scale for v in b], rot, x, y)
            for p_ in placed:
                if not p_.get('b') or p_.get('arch') or p_['type'] not in THING_TAGS_ON_TOP or p_.get('room') != room:
                    continue
                pb_ = p_['b']; ps_ = p_.get('s') or 1.0
                if p_['p'][2] + pb_[2] * ps_ < z - 200:
                    continue
                if _overlaps(fp_, _footprint([v * ps_ for v in pb_], p_['p'][5], p_['p'][0], p_['p'][1]), -2) and abs(p_['p'][2] - z) < 60:
                    last_trace.append((room, 'on top', rid, 'into %s on the table: left out' % p_['id']))
                    return None
        if at_z is not None:
            z = at_z                             # exactly where a game dressing puts it on its shelf
        elif hang_from is not None:
            z = hang_from - b[2]                 # hung on the wall at its usual height
            # (a hung piece needs a wall right behind its back along its whole width: a wall shelf
            # "hanging in mid-air a little out from a free-standing column, attached to nothing")
            if tag in ('STAT', 'ACTI', 'CONT') and room_ is not None and T and not wall_behind(b, rot, x, y, room_, T, front_of(db, rid), scale, reach=24):
                return None
            if (tag in ('STAT', 'ACTI', 'CONT') or (tag == 'LIGH' and ('sconce' in low_ or info.get('traced')))) and room_ is not None \
                    and not wall_by_ray(b, rot, x, y, z, front_of(db, rid), scale):
                # (a traced place's wall lights too: a cave's rock falls away above the height its tile faces are
                # measured at, and Black Teeth's wall burners hung in the air)
                last_trace.append((room, 'hang', rid, 'no wall behind it by the building\'s geometry: left out'))
                return None              # (the tile's pattern calls a side a wall where the piece has its doorway: the user's shelf by the post; a sconce off the wall by a pillar)
            if room_ is not None and T and _tile_of(x, y, room_, T) in _win_cache.setdefault(room_['name'], window_tiles(room_, refs, T)):
                last_trace.append((room, 'hang', rid, 'over a window: left out'))
                return None              # (nothing hangs over a window, by any path: the user's "tapestries over windows")
        else:
            # on this room's own floor (not up on the floor of a room above it), or on a table in it; a
            # rug always on the floor
            under = [r for r in surf if r.get('arch')] if flat else surf
            if info.get('traced') and floor is not None and not on_top and room_ is not None and T:
                # (a traced room's floor is its lowest tile's: a cave's floor climbs and falls across it, so
                # a thing stands on the floor of the tile it is on)
                tl_ = next((t_ for t_ in room_['_tiles'] if abs(x - t_['x']) <= T / 2 and abs(y - t_['y']) <= T / 2), None)
                if tl_ is not None:
                    floor = tl_['floor']
            z = mapdata.surface_z(db, under, True, x, y, b, 1.0, 'MISC' if on_top else tag,
                                  None if floor is None else floor + 64)
            if floor is not None and (z + b[2] < floor - 40 or (z + b[2] > floor + 100 + (ledge or 0) and not on_top)):
                return None                      # no floor under it here (a stairwell): leave it out
                #                                  (or none found and the nearest piece was the floor above)
            if floor is not None and not on_top and (tag not in mapdata.ITEM_TYPES or flat or info.get('traced')):
                # (a traced place's pieces are whole rooms and rock: their boxes' tops are no floor, so a lamp
                # or a basket set down on its floor goes by the mesh too; Black Teeth's lamps stood on nothing)
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
                if info.get('traced') and tag in ('STAT', 'ACTI', 'CONT'):
                    # (a traced floor is the game's own, rock and steps and all: the floor under each corner of
                    # its foot no higher than its bottom (no rock through a bedroll, no chest into a stair) nor
                    # far below it (no table leg over a ledge). The lab's cave bedrolls, 2026-10-24)
                    fp_ = _footprint([v * scale for v in b], rot, x, y)
                    bot_ = z + b[2] * scale
                    for cx_, cy_ in ((fp_[0] + 6, fp_[1] + 6), (fp_[2] - 6, fp_[1] + 6), (fp_[0] + 6, fp_[3] - 6), (fp_[2] - 6, fp_[3] - 6),
                                     ((fp_[0] + fp_[2]) / 2, fp_[1] + 6), ((fp_[0] + fp_[2]) / 2, fp_[3] - 6), (fp_[0] + 6, (fp_[1] + fp_[3]) / 2), (fp_[2] - 6, (fp_[1] + fp_[3]) / 2)):
                        zc_ = floor_by_mesh(cx_, cy_, bot_)
                        if zc_ is None or zc_ > bot_ + 10 or zc_ < bot_ - 40:
                            last_trace.append((room, 'floor', rid, 'the floor under its foot is not level (%s): left out' % ('none' if zc_ is None else '%+.0f' % (zc_ - bot_))))
                            return None
        if tag in ('STAT', 'ACTI', 'CONT') and not on_top and at_z is None and hang_from is None and room_ is not None:
            # two rules every path keeps: nothing taller than the room (its turned top over the kit's
            # storey less the beams), and a bookshelf, a cupboard or a standing shelf only with a real
            # wall right behind its back (the user's "awkward bookshelf" out in the middle of a dining
            # room, side-on to the table, and the saint shrine "clipping the ceilings")
            if room_top and z + b[5] * scale > room_['floor'] + room_top + 16 and not ((bearer(rid) or tradesurvey.piece_of(rid, tag) == 'forge')
                                                                                       and z + b[5] * scale <= room_['floor'] + hearthsurvey.TALL):
                # (a forge's chimney the same: the Gold Coast smiths' t_com_set_forge_02 is 295 tall under 236)
                # (a fireplace's chimney breast goes up through the storey above, as the game's do: Gold
                # Coast's 521 over the floor under a ceiling of 236; lay_hearth_set keeps it clear up there)
                # (16 of give: the Gold Coast bookshelf's top sits 6 over the beams' line and under the
                # storey's top, as the game's own Gold Coast studies have it; the rule is for a shrine's
                # pillar through the ceiling, not a shelf's cornice among the beams)
                last_trace.append((room, 'height', rid, 'taller than the room: %.0f over' % (z + b[5] * scale - room_['floor'] - room_top)))
                return None
            fam_p = roomsurvey.family_of(db, rid, tag)
            if fam_p in ('bookshelf', 'cupboard', 'shelf') and T and (not wall_behind(b, rot, x, y, room_, T, front_of(db, rid), scale, reach=30)
                                                                   or (info.get('traced') and not wall_by_ray(b, rot, x, y, z, front_of(db, rid), scale))):
                # (a traced room's faces are measured at a few spots: the real wall at its back by a ray as well)
                last_trace.append((room, fam_p, rid, 'no wall behind it: left out'))
                return None
        if info.get('traced') and tag == 'LIGH' and at_z is not None and not on_top and HANGING_LIGHT.search(low_):
            # (a light hung in a traced room leaves head room under it by the real floor there: a room's floor is
            # its lowest tile's, and the lab's lanterns in Wraithspire's raised halls hung at knee height)
            if not _scene:
                floor_by_mesh(x, y, z)
            down_ = _scene[0].nearest((x, y, z + b[2] * scale), (0.0, 0.0, -1.0), 900)
            if down_ is not None and down_[0] < 100:
                last_trace.append((room, 'light', rid, 'hung %.0f over the floor there: left out' % down_[0]))
                return None
        nk = db.project.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                       set_ref_pos([('NAME', zs(rid))], (x, y, z, tilt[0], tilt[1], rot), scale))
        c['refs'][nk]['by'] = 'furnish'          # (so a later Auto-furnish can take it out first)
        if piece is not None:
            c['refs'][nk]['on'] = piece          # (laid on this one piece: "Dress again" takes it off first)
        elif on_ref is not None:
            # (a rider: a dressing's thing, a plant, a hearth's tools, a crate's top, tagged with its base, so
            # that a base taken away shows its riders as faults in Check this place, with "Remove them")
            c['refs'][nk]['on'] = on_ref
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
    _win_cache = {}                          # (each room's window tiles, for put(): nothing hangs over a window)

    # (Project Tamriel's rule: a home has one to three common books outside its study, never two copies of
    # a book nor a series; the shelves fill out with other things. Libraries, shops and guilds are free.)
    book_budget = {'left': 3, 'titles': set(), 'stems': set()} if theme == 'house' else None

    def dress(rec, purpose, min_z=None, fill_books=False):
        """Set a new bookshelf, shelf, table or counter out the way the game dresses that model (see
        shelfsurvey.py): the things of one of its real dressings, at the same spots on the same shelves,
        with books and dishes swapped, the odd end piece changed and now and then something interesting
        (as often as the game's own). None when the game never dresses it. min_z: only what stands this
        high over the piece's origin (a hearth's mantelpiece, not the tools at its foot)."""
        if sketch:
            return None
        import shelfsurvey
        d = shelfsurvey.dressing(db, rec['id'], purpose, rng, books=fam.get('book') or [], theme=theme, used=dressings_used,
                                 cap=L['cap'] if L else None, rate_k=L['rate'] if L else 1.0, max_value=L['max_value'] if L else None,
                                 band=L['band'] if L else 'comfortable', budget=book_budget, fill_books=fill_books)
        if d is None:
            return None
        if min_z is not None:
            d = [o for o in d if o['z'] - rec['b'][2] >= min_z]         # (this high over the piece's bottom, not its origin)
            if not d:
                return None
        if WINERACK.search(rec['id'].lower()):
            # a wine rack holds wine: the tall bottles the game racks (misc_com_bottle_05/08/14, Tamriel
            # Data's wines), never the fat Dunmer liquor flasks or a healing potion that the kind-swap of
            # a dressing brought in (the user: "bottles that fit, the tall thin types")
            pool = sorted({o['id'] for dd in shelfsurvey.survey(db, rec['id'])['dressings'] for o in dd['objects']
                           if TALL_BOTTLE.search(o['id'].lower()) and not FAT_BOTTLE.search(o['id'].lower())})
            # (a swapped-in bottle is modelled the same way round and about the same size as the one it
            # replaces, so it lies in the slot as that one did: a wine bottle modelled upright, put in the
            # pose of one modelled along its length, stood up inside the lattice. The user's walk, 2.3.3)
            bnd_ = {}
            kept_ = []
            for o in d:
                if not (FAT_BOTTLE.search(o['id'].lower()) or not TALL_BOTTLE.search(o['id'].lower())):
                    kept_.append(o)
                    continue
                b0_, _t0 = shelfsurvey._bounds_of(db, bnd_, o['id'])
                cands_ = [p_ for p_ in pool if b0_ and (lambda bb: bb and shelfsurvey._same_size(bb, b0_, 3.0) and shelfsurvey._axes(bb) == shelfsurvey._axes(b0_))(shelfsurvey._bounds_of(db, bnd_, p_)[0])]
                # (none of the slim bottles modelled its way round: the game's own bottle stays, in the game's pose)
                kept_.append(dict(o, id=rng.choice(cands_)) if cands_ else o)
            d = kept_
        px, py, pz, rz = rec['p'][0], rec['p'][1], rec['p'][2], rec['p'][5]
        room_d = next((r for r in info['rooms'] if r['name'] == rec.get('room')), None)
        # the furniture's own geometry, for checking that each thing rests on it (a gold ingot stood in
        # the air under a wall shelf: the dressing's level was the bracket's, not the board's)
        import seethrough
        own = seethrough.overlay(db, [{'op': 'place', 'id': rec['id'], 'p': list(rec['p']), 's': rec.get('s', 1.0)}])
        # (a plant is sunk into a planter's soil or stands up on a rock: the soil within 30 under or 40
        # over its bottom will do, where a shelf's thing must rest on the board within 22)
        is_pl = roomsurvey.family_of(db, rec['id'], rec['type']) == 'planter'
        if own.tris and not is_pl and not WINERACK.search(rec['id'].lower()):
            # every book under the board above it, measured on the piece's own mesh (shelfsurvey.fit_books:
            # a shorter book swapped in, a tall one laid down flat or piled, else left out)
            def room_at(x, y, bottom):
                wx_, wy_ = shelfsurvey.to_world(x, y, rz)
                return shelfsurvey.board_over(own, px + wx_, py + wy_, pz + bottom)
            d = shelfsurvey.fit_books(db, d, rec['b'], room_at, fam.get('book') or [], rng, max_value=L['max_value'] if L else None)
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
            # (nothing stands higher than the piece's top: a cobweb or a hung broom the game had on the wall
            # over its kiln hearth came out in the air 200 over ours, the model's dressing reading them as its)
            if bottom > pz + rec['b'][5] * (rec.get('s') or 1.0) + 40:
                continue
            # (and nothing through the ceiling: the game's lilypads and mosses stand in tall halls' beds)
            if room_top and room_d is not None and ob and pz + o['z'] + shelfsurvey.box_turned(ob, orx, ory, orz, o['s'])[5] > room_d['floor'] + room_top:
                continue
            # (not for a wine rack: a bottle lies across two slats of the lattice, nothing straight under its
            # middle, and the game's own racks are where its pose came from)
            if is_pl:
                hit = own.nearest((px + wx, py + wy, bottom + 40), (0.0, 0.0, -1.0), 80) if own.tris else (0, None)
                if hit is None or hit[0] > 40 + 30:
                    continue                             # (no soil near its bottom)
            else:
                hit = own.nearest((px + wx, py + wy, bottom + 8), (0.0, 0.0, -1.0), 40) if own.tris and not WINERACK.search(rec['id'].lower()) else (0, None)
                if hit is None or hit[0] > 8 + 14:
                    continue                             # (nothing of the furniture within reach under it)
            # (and within the room's walls: a ledger lying across a bookshelf's back edge reached into the wall)
            if ob and room_d is not None and T:
                tb_ = shelfsurvey.box_turned(ob, orx, ory, orz, o['s'])
                if not on_floor((px + wx + tb_[0], py + wy + tb_[1], px + wx + tb_[3], py + wy + tb_[4]), room_rects(room_d, T)):
                    continue
            if put(o['id'], px + wx, py + wy, orz, at_z=pz + o['z'], tilt=(orx, ory), scale=o['s'], room=rec.get('room'), on_ref=rec.get('k')):
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
        # "one thing" is a composition when the game composes it (the user: a piece of fish laid straight
        # on the table, no plate): each object of a dressing that stands on the surface itself with what
        # the game stands on or in it (a fish on its plate, a pen in its inkwell, an ingredient on its
        # paper, coins on a scale), laid together at a free spot; a thing the game only ever stands on
        # another (never on its own in any dressing) is not offered on its own
        bounds_ = {}
        alone_n, rode_n = shelfsurvey.alone_rates(db, bounds_, s)

        def plain_ok(o):
            if db.resolve_id(o['id']) is None or not shelfsurvey.plain(db, o['id'], 2):
                return False
            if L and L['cap'] is not None and shelfsurvey.interesting(db, o['id']) and shelfsurvey.value_of(db, o['id'])[1] > L['cap']:
                return False
            return True
        cands = []
        for d in s['dressings']:
            for g in shelfsurvey.groups_of(db, bounds_, d):
                o = g['base']
                if not plain_ok(o):
                    continue
                if shelfsurvey.BOOKEND.search(o['id'].lower()):
                    continue             # (a bookend needs a run of three to join: not one at a time)
                if not g['riders'] and rode_n.get(o['id'].lower(), 0) >= 2 and alone_n.get(o['id'].lower(), 0) == 0:
                    continue             # (the game never stands this on its own: only with what it rides on)
                riders = [r_ for r_ in g['riders'] if plain_ok(r_)]
                w_ = 1.0 + 3.0 * short.get(o['kind'], 0)
                cands.append((rng.random() ** (1.0 / w_), o, riders))
        cands.sort(key=lambda t: -t[0])
        # (a composition as often as the game's dressings of this model hold one, against its lone
        # things: the plate of fish comes up at the game's own rate, not one time in a thousand)
        n_grp = sum(1 for c_ in cands if c_[2])
        if n_grp and rng.random() < max(0.25, n_grp / float(len(cands))):
            cands = [c_ for c_ in cands if c_[2]] + [c_ for c_ in cands if not c_[2]]
        own = seethrough.overlay(db, [{'op': 'place', 'id': rec['id'], 'p': list(rec['p']), 's': rec.get('s', 1.0)}])
        fb_ = rec['b']
        ax_ = 0 if (fb_[3] - fb_[0]) >= (fb_[4] - fb_[1]) else 1          # (the row runs along the longer side)
        room_d = next((r for r in info['rooms'] if r['name'] == rec.get('room')), None)
        rects_ = room_rects(room_d, T) if room_d is not None and T else None

        def world_of(o):
            """An object of a dressing on this piece: ((X, Y, Z), (rx, ry, rz), world box) or None."""
            wx, wy = shelfsurvey.to_world(o['x'], o['y'], rz)
            orx, ory, orz = shelfsurvey.compose_on(o['rx'], o['ry'], o['rz'], rz)
            ob, _tag = shelfsurvey._bounds_of(db, bounds_, o['id'])
            if not ob:
                return None
            tb = shelfsurvey.box_turned(ob, orx, ory, orz, o['s'])
            X, Y, Z = px + wx, py + wy, pz + o['z']
            return (X, Y, Z), (orx, ory, orz), (X + tb[0], Y + tb[1], Z + tb[2], X + tb[3], Y + tb[4], Z + tb[5])

        def clear_of_have(wb):
            return not any(wb[0] < hb[3] - 2 and hb[0] < wb[3] - 2 and wb[1] < hb[4] - 2 and hb[1] < wb[4] - 2 and wb[2] < hb[5] - 2 and hb[2] < wb[5] - 2 for _r, hb in have)
        for _w, o, riders in cands[:600]:
            w_ = world_of(o)
            if w_ is None:
                continue
            (X, Y, Z), (orx, ory, orz), wb = w_
            if not clear_of_have(wb):
                continue                 # (something stands there already)
            if rects_ is not None and not on_floor((wb[0], wb[1], wb[3], wb[4]), rects_):
                continue
            hit = own.nearest((X, Y, wb[2] + 8), (0.0, 0.0, -1.0), 40) if own.tris and not WINERACK.search(rec['id'].lower()) else (0, None)
            if hit is None or hit[0] > 8 + 14:
                continue                 # (nothing of the piece under it)
            # (the riders come with it only when their places are free too; a plate whose fish would
            # land in a candle is laid elsewhere)
            rw = []
            for r_ in riders:
                w2 = world_of(r_)
                if w2 is None or not clear_of_have(w2[2]) or (rects_ is not None and not on_floor((w2[2][0], w2[2][1], w2[2][3], w2[2][4]), rects_)):
                    rw = None
                    break
                rw.append((r_, w2))
            if rw is None:
                continue
            if o['kind'] == 'BOOK' and own.tris:
                # (never a book taller than the room under the board above it)
                up_ = shelfsurvey.board_over(own, X, Y, wb[2])
                if up_ is not None and wb[5] - wb[2] > up_ - 1.5:
                    continue
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
                name_ = (db.recs[ri_][2] or o['id']) if ri_ is not None else o['id']
                n_ = 1
                with_ = []
                for r_, ((X2, Y2, Z2), (rx2, ry2, rz2), _wb2) in rw:
                    r2 = put(r_['id'], X2, Y2, rz2, at_z=Z2, tilt=(rx2, ry2), scale=r_['s'], room=rec.get('room'), on_top=True)
                    if r2:
                        n_ += 1
                        ri2 = db.resolve_id(r_['id'])
                        with_.append((db.recs[ri2][2] or r_['id']) if ri2 is not None else r_['id'])
                if with_:
                    name_ = '%s with %s' % (name_, ', '.join(with_[:3]) + (' and more' if len(with_) > 3 else ''))
                return {'placed': n_, 'added': o['id'], 'name': name_, 'kind': o['kind'], 'with': with_}
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
                r_ = put(oid, wx, wy, (rz + drz) % (2 * math.pi), at_z=pz + dz, scale=sc, room=rec.get('room'), on_top=True, on_ref=rec.get('k'))
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
        if sketch:
            return []
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
            room_ = next((r for r in info['rooms'] if r['name'] == rec.get('room')), None)
            if tag in ('STAT', 'CONT', 'ACTI') and not _overlaps(box, own, 0):
                if any(_overlaps(box, o[0]) for o in taken if o[1] < fl_ + 150 and o[2] > fl_ + 4 and o[0] is not own):
                    continue
                # (and on the room's floor as the walls bound it: a log pile through the wall behind the hearth)
                if room_ is not None and not on_floor(box, room_rects(room_, T)):
                    continue
            elif tag in ('STAT', 'CONT', 'ACTI') and room_ is not None and T and not on_floor(box, room_rects(room_, T)):
                continue                 # (the coals inside the firebox still cut no wall: the hearth's back is at the face)
            up = dz * fs > 24 or _overlaps(box, own, 0)
            if tag in mapdata.ITEM_TYPES and not up:
                continue             # (a cup, a tool, a cloth the game had on a table by its hearth: never on the floor here)
            if re.search(r'coal|ember|flame|fire_|_fire|logpile|campfire', oid.lower()) and not _overlaps(box, own, 0):
                continue             # (the fire itself burns in the firebox, never on the floor before the hearth: the user's "campfire" by a fireplace)
            if tag in mapdata.ITEM_TYPES and not _overlaps(box, own, 0):
                continue             # (a dish the game had on a shelf by its kiln, 168 off: on the hearth or not at all)
            r_ = put(oid, wx, wy, (rz + drz) % (2 * math.pi), on_top=up and tag in mapdata.ITEM_TYPES, floor=None if up else fl_,
                     at_z=(pz + dz * fs) if up else None, scale=sc, room=rec.get('room'), on_ref=rec.get('k'))
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
    piece_room = None
    if piece is not None:
        # (one piece: the room it stands in, whatever that room is for. Of the rooms under it, the one whose
        # floor is nearest below its bottom: a house's storeys have rooms of the same outline, and the ground
        # floor's room also "held" a bookshelf upstairs, 262 over its floor; every book on the shelf then came
        # out through that room's ceiling and Dress this said none of 80 dressings fit. The user's Test Home)
        pb_ = piece_rec['p'][2] + piece_rec['b'][2] * (piece_rec.get('s') or 1.0)
        under_ = [rm for rm in info['rooms'] if rm['x_min'] <= piece_rec['p'][0] <= rm['x_max'] and rm['y_min'] <= piece_rec['p'][1] <= rm['y_max']
                  and -60 <= pb_ - rm['floor'] < 300]             # (a wall shelf hangs well above the floor)
        if under_:
            piece_room = min(under_, key=lambda rm: (pb_ - rm['floor'] < -60, abs(pb_ - rm['floor']) if pb_ >= rm['floor'] - 60 else 1e9))['id']
    for room in info['rooms']:
        purpose = wanted.get(room['id'], room['purpose']) if plan is not None else room['purpose']
        if plan is not None and room['id'] not in wanted and piece is None:
            continue
        if piece is not None:
            if room['id'] != piece_room:
                continue
            if not purpose or purpose == 'none' or purpose not in RECIPES:
                purpose = 'living'
        if not purpose or purpose == 'none' or purpose not in RECIPES:
            continue
        if purpose == 'hall':
            purpose = hall_kind(room, refs, T, info['rooms'])     # (a corridor, an entry or a landing: room-kind survey R2)
        # a trade's room is furnished as a shop from its own anchor set (TRADE_ROOMS: its recipe, its essential
        # piece, its scene); a plain shop is a general trader's, or the smithy when the household is a smith's
        trade_p = purpose if TRADES and purpose in TRADE_ROOMS else None
        if TRADES and purpose == 'shop' and L and 'forge' in extras_left and 'smith' not in room_trade.values():
            trade_p = 'smithy'
        trade = (TRADE_ROOMS.get(trade_p) or ('trader' if purpose == 'shop' else None)) if TRADES else None
        if trade:
            room_trade[room['name']] = trade
        if trade_p:
            purpose = 'shop'
            fam['wares'] = trade_wares(db, trade, STYLE_SET.get(style) or fam.get('_borrowed'))
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
        bar_front = [None]  # the counter run's customer strip (taken), where a tavern's bar stools may still stand
        row_last = [None, None]   # the last practice dummy's spot and the wall the row is on: the next stands beside it (R11)
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
            lst = [r for r in (fam.get(kind) or []) if not RIDER_ONLY.search(r.lower())]     # (no water sheet as a tub)
            if kind == 'bed' and L and L.get('band') in ('worthless', 'poor') and fam.get('bedroll') and purpose == 'bedroom':
                # (the catalogue's R4 poor rooms, Blind Dock Lodgings and Gormash's: a bedroll or a mat,
                # not a bed; the poor band's fewer things do the rest)
                lst = fam['bedroll']
            if kind == 'chest':
                # (a strongbox goes on a shelf or a table, as the game keeps it: decorsurvey.py; the
                # chest that stands on the floor is a clothes chest)
                import decorsurvey
                lst = [r for r in lst if not decorsurvey.off_floor(db, r)]
            if L and L['cap'] is not None and kind in ('dish', 'bottle', 'book', 'food', 'candle'):
                import shelfsurvey
                under = [r for r in lst if shelfsurvey.value_of(db, r)[1] <= L['cap']]
                # (a poor house keeps every kind of thing a rich one has, at a lower value: with nothing
                # of the kind under the band's cap, its cheapest few, never none)
                lst = under or sorted(lst, key=lambda r: shelfsurvey.value_of(db, r)[1])[:3]
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
        # a hearth the builder placed as part of the building (the Common kitchens' in_imp_fireplace_grand
        # and in_nord_fireplace_01 against a wall, 'in_' statics the fire family rightly refuses as
        # furniture): the room's hearth all the same, dressed with its cookery and logs, no second one laid
        built_hearths = []
        for a in refs:
            if not (a.get('arch') and a.get('b') and re.search(r'fireplace|hearth|stove', a['id'].lower())):
                continue
            if not (fl - 100 <= a['p'][2] <= fl + 100 and room['x_min'] - 40 <= a['p'][0] <= room['x_max'] + 40 and room['y_min'] - 40 <= a['p'][1] <= room['y_max'] + 40):
                continue
            built_hearths.append({'id': a['id'], 'p': list(a['p'][:6]), 'b': list(a['b']), 's': a.get('s') or 1.0, 'type': a['type'],
                                  'room': room['name'], 'arch': True, 'k': a.get('k')})
        # the room's windows (the kit's window props on its walls), for what the game stands under them:
        # a planter under a window 29% of the time, a basket 16% (wallsurvey2 v3)
        windows_here = []
        win_tiles = window_tiles(room, refs, T)
        for a in refs:
            if not (a.get('arch') and a.get('b') and placesurvey.WINDOW.search(a['id'].lower())):
                continue
            if not (fl - 60 <= a['p'][2] <= fl + 300 and room['x_min'] - 40 <= a['p'][0] <= room['x_max'] + 40 and room['y_min'] - 40 <= a['p'][1] <= room['y_max'] + 40):
                continue
            edges_ = {'N': room['y_max'] - a['p'][1], 'S': a['p'][1] - room['y_min'], 'E': room['x_max'] - a['p'][0], 'W': a['p'][0] - room['x_min']}
            side_ = min(edges_, key=lambda k: abs(edges_[k]))
            if abs(edges_[side_]) < 60:
                windows_here.append(((a['p'][0], a['p'][1]), side_))
        # (the doorways and stairs of this room, for the planting path: a door or a door jamb, as the survey
        # and the check count doorways, not a bare doorway piece)
        doors_here = [o for o in openings if (o['type'] == 'DOOR' or 'jamb' in o['id'].lower()) and abs(span(o)[0] - fl) < 60
                      and room['x_min'] - 40 <= o['p'][0] <= room['x_max'] + 40 and room['y_min'] - 40 <= o['p'][1] <= room['y_max'] + 40]
        stairs_here = [r for r in refs if r.get('arch') and re.search(r'stair|ramp', r['id'].lower()) and abs(r['p'][2] - fl) < 100
                       and room['x_min'] - T <= r['p'][0] <= room['x_max'] + T and room['y_min'] - T <= r['p'][1] <= room['y_max'] + T]

        def window_for(kind):
            """A window to stand this under, at the game's rate for the kind, or None."""
            if not windows_here:
                return None
            import wallsurvey2 as _w2
            wr = (_w2.ready(db) or {}).get('windows') or {}
            if (wr.get('windows') or 0) < 20:
                return None
            rate = wr.get(kind + 's_under') or 0
            if rate < 0.05 or rng.random() >= rate:
                return None
            return rng.choice(windows_here)

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

        def across_way_in(box):
            """In a small room, a box standing across the way in: on the line from a doorway to the room's
            middle. The game's beds in rooms of up to nine tiles are 3.7% of the time (7 of 187); the user's
            bed in the tiny home stood in the way."""
            if room['tiles'] > 9 or not doors_here:
                return False
            mx, my = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
            for d in doors_here:
                for i in range(41):
                    t = i / 40.0
                    px, py = d['p'][0] + (mx - d['p'][0]) * t, d['p'][1] + (my - d['p'][1]) * t
                    if box[0] + 10 <= px <= box[2] - 10 and box[1] + 10 <= py <= box[3] - 10:
                        return True
            return False

        def wall_spot(b, front, where, pp=None, kind=None, gap=2, near=None, side=None, align=None, columns_first=False, within=None):
            """A free spot for this thing with its back to a wall (a corner first when where is
            'corner'): ((x, y, rot, box), direction into the room), or (None, None). The slot is used up.
            pp: how the game places the kind (placesurvey.prefs): which wall, how often a corner, how
            often the foot of a column. gap: how far off the wall (a counter leaves the keeper's side).
            near: a point (x, y) the slots nearest to are tried first (a kitchen's sack by the door).
            align: a point on the named wall the thing is centred on, within its slot's tile (a planter
            under the window). within: with near, only slots that close to it (a planter that must stand
            BY the door or the seat it was given, or nowhere); with columns_first, only a column's foot."""
            order = slot_order(where, pp)
            if near is not None:
                # (the same wall first when one is named: a row of dummies keeps to its wall, R11)
                order = sorted(order, key=lambda sl: ((sl['side'] != side) if side else 0, math.hypot(sl['x'] - near[0], sl['y'] - near[1])))
                if within is not None:
                    order = [sl for sl in order if math.hypot(sl['x'] - near[0], sl['y'] - near[1]) <= within]
            if col_slots and (columns_first or (pp and (pp.get('at_column') or 0) > 0 and rng.random() < pp['at_column'])):
                order = list(col_slots) + ([] if (columns_first and within is not None) else order)
            if kind == 'counter':
                order = [sl for sl in order if not sl.get('column') and not sl['corner']] or order
            if kind in HANGING_KINDS + ('rack',):
                # (nothing hangs on a column's foot, nor on a window tile's wall over the window)
                order = [sl for sl in order if not sl.get('column') and _tile_of(sl['x'] + sl['in'][0] * 20, sl['y'] + sl['in'][1] * 20, room, T) not in win_tiles]
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
                if align is not None and side and sl['side'] == side:
                    # (centred under the window, kept within the slot's own tile)
                    half_ = ((box0[2] - box0[0]) if sl['in'][1] else (box0[3] - box0[1])) / 2
                    if sl['in'][1]:
                        x = min(max(align[0], sl['x'] - T / 2 + half_ + 4), sl['x'] + T / 2 - half_ - 4)
                    else:
                        y = min(max(align[1], sl['y'] - T / 2 + half_ + 4), sl['y'] + T / 2 - half_ - 4)
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
                if kind == 'bed' and BED_OFF_THE_WAY and across_way_in(box):
                    continue
                if fits(box):
                    (col_slots if sl.get('column') else slots).remove(sl)
                    return (x, y, rot, box), sl['in']
            return None, None

        def lay_hearth_set(purpose):
            """The room's hearth laid as one of the game's own whole sets (hearthsurvey): the hearth of the
            house's kit or culture with its back to a wall at the game's own gap (a kit's fireplace sunk into
            the wall as the game's are), and the members of one real set of that model round it at their
            offsets and turns: the fire inside it, the firewood, the cauldron or pot, the tools, the things on
            its mantel, and the counter, shelf, table or stores the game stood beside it when they fit. The
            fire is the set's core: a hearth whose fire would not go in is taken out again with everything
            laid with it, and the next spot or model tried. Returns the hearth's record, 0 when no hearth
            of the style fits (the room goes without a fire), None when the survey is not to hand."""
            cands = hearthsurvey.choices(db, cell_style, band=L['band'] if L else None, height=storey_h)
            if cands is None:
                return None
            rate_ = hearthsurvey.room_rate(db, purpose)
            if rate_ is not None and rng.random() >= rate_:
                # (a kitchen always; a dining room or a living room as often as the game's have a hearth:
                # every dining room had one once the hearth came whole, 45 of 45 in the lab)
                last_trace.append((room['name'], 'fire', 'no hearth this time: the game has one in %.0f%% of rooms like this' % (100 * rate_)))
                return 0
            if not cands:
                last_trace.append((room['name'], 'fire', 'no hearth the game stands in houses of this style: none laid'))
                return 0
            cult_ = hearthsurvey.culture_of_kit(cell_style)
            FURN_ = ('table', 'counter', 'shelf', 'cupboard', 'barrel', 'crate', 'sack', 'urn', 'chest') + \
                (('chair', 'bench') if purpose in ('living', 'dining', 'tavern', 'mess') else ())
            for rid, F in cands[:3]:
                ri_ = db.resolve_id(rid)
                b_ = mapdata.object_bounds(db, ri_) if ri_ is not None else None
                if not b_:
                    continue
                back_ = {'+x': (1, 0), '-x': (-1, 0), '+y': (0, 1), '-y': (0, -1)}.get(F.get('back') or '-y')
                front_ = (-back_[0], -back_[1])
                gap_ = F['gap'] if F.get('gap') is not None else 2
                if not hearthsurvey.built_piece(rid):
                    gap_ = max(2, gap_)      # (only a kit's fireplace sinks into the wall; the Redoran kiln went 57 into it)
                for _try in range(3):
                    spot_, inward_ = wall_spot(b_, front_, 'wall', kind='fire', gap=max(2, gap_), near=room.get('hearth_near'))
                    if not spot_:
                        break
                    x_, y_, rot_, box_ = spot_
                    # (what lies behind that wall: another room of this floor, or the outside)
                    bx_ = (box_[0] + box_[2]) / 2 - inward_[0] * ((box_[2] - box_[0]) / 2 + 48)
                    by_ = (box_[1] + box_[3]) / 2 - inward_[1] * ((box_[3] - box_[1]) / 2 + 48)
                    behind = any(abs(rm2['floor'] - fl) < 100 and any(abs(bx_ - tl['x']) <= T / 2 and abs(by_ - tl['y']) <= T / 2 for tl in rm2['_tiles'])
                                 for rm2 in info['rooms'] if rm2 is not room)
                    if gap_ < 2 and not behind:
                        # (the kit's fireplace stands into the wall as far as the game's do: its back is the wall's;
                        # never into a wall with a room behind it, where its back came out in the hall)
                        x_ += inward_[0] * (gap_ - 2)
                        y_ += inward_[1] * (gap_ - 2)
                    top_ = fl + (b_[5] - b_[2])
                    fp_ = _footprint(b_, rot_, x_, y_)
                    if any(_overlaps(fp_, o[0], 0) for o in taken if o[1] < top_ and o[2] > fl + 150):
                        # (its chimney breast goes up through the storey above, as the game's do: never
                        # through what stands up there, a doorway's clearance or a stair's landing)
                        last_trace.append((room['name'], 'fire', rid, 'its chimney would run into what stands above: another wall'))
                        continue
                    n_placed, n_taken = len(placed), len(taken)
                    h_ = put(rid, x_, y_, rot_, floor=fl, room=room['name'])
                    if h_ is None:
                        continue
                    taken.append((fp_, fl, top_, False))
                    ex_ = hearthsurvey.whole_set(db, rid, rng, culture=cult_, kind=purpose) or {'members': [], 'fire_in': False}
                    want_fire = F['fire_in'] >= 0.5 and ex_.get('fire_in')
                    fs_ = h_.get('s') or 1.0
                    c_, s_ = math.cos(rot_), math.sin(rot_)
                    own_ = _footprint([v * fs_ for v in h_['b']], rot_, h_['p'][0], h_['p'][1])
                    bottom_ = h_['p'][2] + h_['b'][2] * fs_
                    wanted, laid_, fire_ok, furn_laid, furn_boxes, on_furn, stand_boxes, bowl_bottoms = 0, [], False, [], [], set(), [], []
                    for m in sorted(ex_['members'], key=lambda m: (m['role'] != 'fire', m['role'] not in FURN_, m.get('type') in mapdata.ITEM_TYPES)):     # (the fire, the furniture, the tool stand, then what stands on them)
                        rl_ = m['role']
                        if rl_ == 'thing' and not m.get('in'):
                            continue          # (a cup on the table the game had beside it: with its table, or not at all)
                        if rl_ not in ('fire', 'wood', 'cook', 'tool', 'grate', 'thing') + FURN_:
                            continue
                        if rl_ == 'fire' and not m.get('in'):
                            continue          # (the fire burns in the hearth, never before it on the floor: a camp fire)
                        if re.match(r'^t_[a-z]+_set[a-z]*_|^(in|ex)_', m['id'].lower()) or BUILDING_BITS.search(m['id'].lower()):
                            continue          # (the building round the game's hearth, a Gold Coast railing: not the set's)
                        oi_ = db.resolve_id(m['id'])
                        ob_ = mapdata.object_bounds(db, oi_) if oi_ is not None else None
                        if not ob_:
                            continue
                        tag_ = db.recs[oi_][0]
                        wx = h_['p'][0] + (m['x'] * c_ + m['y'] * s_) * fs_
                        wy = h_['p'][1] + (-m['x'] * s_ + m['y'] * c_) * fs_
                        wz = h_['p'][2] + m['z'] * fs_
                        mrot = (rot_ + m['rz']) % (2 * math.pi)
                        sc_ = m.get('s') or 1.0
                        mbox = _footprint([v * sc_ for v in ob_], mrot, wx, wy)
                        in_ = _overlaps(mbox, own_, 0)
                        mcx, mcy = (mbox[0] + mbox[2]) / 2, (mbox[1] + mbox[3]) / 2
                        if tag_ in mapdata.ITEM_TYPES and wz + ob_[2] * sc_ > bottom_ + 12 \
                                and not (own_[0] - 4 <= mcx <= own_[2] + 4 and own_[1] - 4 <= mcy <= own_[3] + 4) \
                                and not any(fb_[0] - 4 <= mcx <= fb_[2] + 4 and fb_[1] - 4 <= mcy <= fb_[3] + 4 for fb_ in furn_boxes + stand_boxes):
                            continue          # (up on a counter or a shelf by the hearth that is not laid here: the Indoril stove's ladle in the air)
                        wanted += 1
                        if not in_ and not inside(mbox):
                            continue          # (a tool the game leant by its hearth, here through the wall in the next room)
                        if rl_ in FURN_ or (tag_ in ('STAT', 'CONT', 'ACTI') and not in_):
                            # (standing on the floor beside the hearth: in the room and clear of what stands there)
                            if not fits(mbox):
                                continue
                            r_ = put(m['id'], wx, wy, mrot, floor=fl, room=room['name'], scale=sc_, on_ref=None if rl_ in FURN_ else h_['k'])
                            if r_ is not None:
                                taken.append((mbox, fl, fl + 150, False))
                                if rl_ in FURN_:
                                    furn_laid.append(r_)
                                    furn_boxes.append(mbox)
                                else:
                                    stand_boxes.append(mbox)      # (the tool stand the broom and the hook stand in)
                        else:
                            if tag_ == 'MISC' and 'bowl' in m['id'].lower():
                                # (the game's bowls on its kiln are sunk by different amounts: one depth for all here,
                                # as the check's "bowls sunk unevenly" asks)
                                b_bot = wz + ob_[2] * sc_
                                near_ = [b0 for b0 in bowl_bottoms if 3 < abs(b_bot - b0) <= 12]
                                if near_:
                                    wz += near_[0] - b_bot
                                bowl_bottoms.append(wz + ob_[2] * sc_)
                            r_ = put(m['id'], wx, wy, mrot, on_top=tag_ in mapdata.ITEM_TYPES, at_z=wz, scale=sc_, room=room['name'], on_ref=h_['k'])
                        if r_ is not None:
                            laid_.append(m['id'])
                            fire_ok = fire_ok or rl_ == 'fire'
                            if rl_ not in FURN_:
                                on_furn.update(n_ for n_, fb_ in enumerate(furn_boxes) if fb_[0] - 4 <= mcx <= fb_[2] + 4 and fb_[1] - 4 <= mcy <= fb_[3] + 4)
                    if (want_fire and not fire_ok) or len(laid_) < min(2, wanted):
                        # (a hearth with no fire, or with nothing of its set: out again, everything with it)
                        for r_ in placed[n_placed:]:
                            c['refs'].pop(r_['k'], None)
                            if r_ in surf:
                                surf.remove(r_)
                        del placed[n_placed:]
                        del taken[n_taken:]
                        last_trace.append((room['name'], 'fire', rid, 'its set would not go in whole (%d of %d, fire %s): taken out' % (len(laid_), wanted, fire_ok)))
                        continue
                    for n_, fr_ in enumerate(furn_laid):
                        if n_ not in on_furn and roomsurvey.family_of(db, fr_['id'], fr_['type']) in DRESSED_KINDS:     # (dressed by the set already: not twice)
                            got.extend(o['id'] for o in (dress(fr_, purpose) or []))
                    got.extend([rid] + laid_)
                    last_trace.append((room['name'], 'fire', rid, 'the game\'s whole hearth set from %s: %d of %d things%s'
                                       % (ex_.get('cell'), len(laid_), wanted, ', its fire in it' if fire_ok else '')))
                    return h_
            last_trace.append((room['name'], 'fire', 'no wall took a whole hearth set: none laid'))
            return 0

        def lay_work_table(h_):
            """A kitchen's work table at its hearth: a table against a wall within reach of the fire,
            dressed as the game dresses that model in kitchens (a board, a bowl, food), when no table or
            counter stands that near already. The game's cooking hearths have their nearest table at 249
            (median of 62, 2026-10-24); Auto-furnish's stood at 563, across the room
            (packaging/nexus/pt-showcases-study.md, K6). Returns the table's record or None."""
            if purpose != 'kitchen' or not h_ or sketch or walls_only or not WORK_TABLE_REACH:
                return None
            hx_, hy_ = h_['p'][0], h_['p'][1]
            # (from the hearth's edge, not its middle: a Redoran kiln is 300 across, and no wall slot lay
            # within 300 of its middle)
            hb_ = h_.get('b') or (0, 0, 0, 0, 0, 0)
            reach_ = WORK_TABLE_REACH + max(hb_[3] - hb_[0], hb_[4] - hb_[1]) * (h_.get('s') or 1.0) / 2 - 60
            if any(math.hypot((t['box'][0] + t['box'][2]) / 2 - hx_, (t['box'][1] + t['box'][3]) / 2 - hy_) <= reach_ for t in tables):
                return None
            cands_ = []
            for tid_ in (fam.get('table') or [])[:16]:
                ti_ = db.resolve_id(tid_)
                tb_ = mapdata.object_bounds(db, ti_) if ti_ is not None else None
                # (a work table, not the dining board: 70 to 190 long)
                if tb_ and 70 <= max(tb_[3] - tb_[0], tb_[4] - tb_[1]) <= 190:
                    cands_.append((tid_, tb_))
            for tid_, tb_ in cands_[:4]:
                spot_, _in = wall_spot(tb_, front_of(db, tid_), 'wall', kind='table', near=(hx_, hy_), within=reach_)
                if not spot_:
                    continue
                x_, y_, rot_, box_ = spot_
                rec_ = put(tid_, x_, y_, rot_, floor=fl, room=room['name'])
                if rec_ is None:
                    continue
                taken.append((box_, fl, fl + 200, False))
                laid_ = dress(rec_, purpose)
                tables.append({'box': box_, 'items': [], 'dressed': bool(laid_), 'counter': False})
                got.append(tid_)
                got.extend(o['id'] for o in (laid_ or []))
                pre['table'] += 1           # (the recipe's table: this one)
                last_trace.append((room['name'], 'table', tid_, 'the work table by the hearth, %.0f from it' % math.hypot(x_ - hx_, y_ - hy_)))
                return rec_
            last_trace.append((room['name'], 'table', 'no wall within reach of the hearth took a work table'))
            return None

        def lay_forge_set():
            """A smithy's anchor (tradesurvey.py): a forge of the house's kit or culture with its back to a wall,
            and one of the game's own sets round that model at their offsets and turns, the smith's pieces of it
            only: the anvil and the bellows at it, the coals and the fire in it, the grindstone, the tools, the
            quench bucket, the logs. The anvil is the set's core: when the game's set brings none within reach,
            one goes before the forge's mouth; a forge no anvil will stand at is taken out again with everything
            laid with it, and the next spot or model tried. Returns the forge's record, or 0 when no forge fits
            (the room goes without smithing: put() lets no anvil, bellows or grindstone stand in it)."""
            for h in surf:
                if h.get('b') and tradesurvey.piece_of(h['id'], h['type']) == 'forge' and inside(_footprint(h['b'], h['p'][5], h['p'][0], h['p'][1]), loose=True) \
                        and abs(h['p'][2] + h['b'][2] * (h.get('s') or 1.0) - fl) < 150:
                    last_trace.append((room['name'], 'forge', h['id'], 'the room\'s own forge'))
                    return h
            cands = tradesurvey.forge_choices(db, cell_style, height=storey_h)
            if not cands:
                last_trace.append((room['name'], 'forge', 'no forge known for this style%s: no smithing here' % ('' if cands is not None else ' (the survey is not to hand)')))
                return 0
            anvils = [i for i in ('furn_anvil00', 't_com_var_anvil_01') if db.resolve_id(i) is not None]
            for rid, F in cands[:3]:
                ri_ = db.resolve_id(rid)
                b_ = mapdata.object_bounds(db, ri_) if ri_ is not None else None
                if not b_:
                    continue
                front_ = front_of(db, rid)
                for _try in range(3):
                    spot_, inward_ = wall_spot(b_, front_, 'wall', kind='forge', gap=2)
                    if not spot_:
                        break
                    x_, y_, rot_, box_ = spot_
                    top_ = fl + (b_[5] - b_[2])
                    if any(_overlaps(box_, o[0], 0) for o in taken if o[1] < top_ and o[2] > fl + 150):
                        last_trace.append((room['name'], 'forge', rid, 'its chimney would run into what stands above: another wall'))
                        continue
                    n_placed, n_taken = len(placed), len(taken)
                    f_ = put(rid, x_, y_, rot_, floor=fl, room=room['name'])
                    if f_ is None:
                        continue
                    taken.append((box_, fl, top_, False))
                    ex_ = tradesurvey.forge_set(db, rid, rng) or {'members': [], 'cell': None}
                    fs_ = f_.get('s') or 1.0
                    c_, s_ = math.cos(rot_), math.sin(rot_)
                    own_ = _footprint([v * fs_ for v in f_['b']], rot_, f_['p'][0], f_['p'][1])
                    hosts_ = [own_]
                    laid_, anvil_ = [], None
                    # (the floor pieces first, the anvil before them all; then what lies on them and in the forge)
                    for m in sorted(ex_['members'], key=lambda m: (m['piece'] != 'anvil', m['type'] not in ('STAT', 'ACTI', 'CONT'))):
                        oi_ = db.resolve_id(m['id'])
                        ob_ = mapdata.object_bounds(db, oi_) if oi_ is not None else None
                        if not ob_:
                            continue
                        tag_ = db.recs[oi_][0]
                        wx = f_['p'][0] + (m['x'] * c_ + m['y'] * s_) * fs_
                        wy = f_['p'][1] + (-m['x'] * s_ + m['y'] * c_) * fs_
                        mrot = (rot_ + m['rz']) % (2 * math.pi)
                        sc_ = m.get('s') or 1.0
                        mbox = _footprint([v * sc_ for v in ob_], mrot, wx, wy)
                        in_ = m.get('in') or _overlaps(mbox, own_, 0)
                        if tag_ in ('STAT', 'ACTI', 'CONT') and not in_:
                            if m['piece'] == 'anvil' and (anvil_ is not None or m['d'] > tradesurvey.REACH['anvil']):
                                continue      # (one anvil, at the forge)
                            if not inside(mbox) or not fits(mbox):
                                continue
                            r_ = put(m['id'], wx, wy, mrot, floor=fl, room=room['name'], scale=sc_)
                            if r_ is not None:
                                taken.append((mbox, fl, fl + 150, False))
                                hosts_.append(mbox)
                                if m['piece'] == 'anvil':
                                    anvil_ = r_
                        else:
                            mcx, mcy = (mbox[0] + mbox[2]) / 2, (mbox[1] + mbox[3]) / 2
                            if not any(h_[0] - 6 <= mcx <= h_[2] + 6 and h_[1] - 6 <= mcy <= h_[3] + 6 for h_ in hosts_):
                                continue      # (on a piece of the game's set that is not laid here: left out)
                            r_ = put(m['id'], wx, wy, mrot, on_top=tag_ in mapdata.ITEM_TYPES, at_z=f_['p'][2] + m['z'] * fs_,
                                     tilt=(m.get('rx', 0), m.get('ry', 0)), scale=sc_, room=room['name'], on_ref=f_['k'])
                        if r_ is not None:
                            laid_.append(m['id'])
                    if anvil_ is None and anvils:
                        # (the game's set brought none within reach: one before the forge's mouth, a little
                        # to one side, turned along the forge's front, as the game's smiths stand theirs)
                        aid = anvils[0]
                        ab_ = mapdata.object_bounds(db, db.resolve_id(aid))
                        fx_, fy_ = inward_
                        half_f = ((own_[3] - own_[1]) if fy_ else (own_[2] - own_[0])) / 2
                        cx_f, cy_f = (own_[0] + own_[2]) / 2, (own_[1] + own_[3]) / 2
                        for fwd in (half_f + 70, half_f + 110, half_f + 150):
                            for side in (0, 70, -70, 120, -120):
                                ax_ = cx_f + fx_ * fwd + (-fy_) * side
                                ay_ = cy_f + fy_ * fwd + fx_ * side
                                arot_ = _turn_to_face(front_of(db, aid), (-fy_, fx_)) if front_of(db, aid) else math.atan2(fx_, fy_)
                                abox_ = _footprint(ab_, arot_, ax_, ay_)
                                if inside(abox_) and fits(abox_):
                                    anvil_ = put(aid, ax_, ay_, arot_, floor=fl, room=room['name'])
                                    if anvil_ is not None:
                                        taken.append((abox_, fl, fl + 150, False))
                                        laid_.append(aid)
                                        break
                            if anvil_ is not None:
                                break
                    if anvil_ is None:
                        # (a forge with no anvil at it is no smithy: out again, everything with it)
                        for r_ in placed[n_placed:]:
                            c['refs'].pop(r_['k'], None)
                            if r_ in surf:
                                surf.remove(r_)
                        del placed[n_placed:]
                        del taken[n_taken:]
                        last_trace.append((room['name'], 'forge', rid, 'no anvil would stand at it: taken out'))
                        continue
                    got.extend([rid] + laid_)
                    if 'forge' in extras_left:
                        extras_left.remove('forge')
                    last_trace.append((room['name'], 'forge', rid, 'the game\'s smith set from %s: %d things with it' % (ex_.get('cell'), len(laid_))))
                    return f_
            last_trace.append((room['name'], 'forge', 'no wall took a forge with its anvil: no smithing here'))
            return 0

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
            # (a small shop draws from the runs the game lays in rooms as small: countersurvey.SMALL_ROOM)
            tiles_ = room['tiles'] * (T / 256.0) ** 2
            cands = countersurvey.compositions(db, cell_style, purpose, culture=culture, tiles=tiles_)
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
            if len(suits) < 3:
                # (a style with few runs of its own that fit, Common plain's five: the runs of its
                # culture's make as well, so a shop isn't the one run every seed)
                wider = [r_ for r_ in (countersurvey.compositions(db, '*', purpose, culture=culture, tiles=tiles_) or []) if r_ not in cands]
                rng.shuffle(wider)
                cands += wider
                suits += [r_ for r_ in wider if r_['length'] <= 0.75 * long_wall and r_['n'] <= n_cap]
                rng.shuffle(suits)                      # (the one run of the style's own not first every seed)
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
                            tables.append({'box': bx_, 'items': [], 'dressed': bool(laid_), 'counter': True, 'open': tuple(sl['in'])})
                            fronts.append({'box': bx_, 'in': sl['in'], 'kind': 'counter'})
                            ids.append(r_['id'])
                        # the slots the run covers are used up (nothing else goes behind it); what the game
                        # stands behind its counters goes there, at the game's rates
                        whole = (RB[0] + X, RB[1] + Y, RB[2] + X, RB[3] + Y)
                        behind_slots = [s2 for s2 in slots if s2['in'] == sl['in'] and
                                        (whole[0] - T / 2 <= s2['x'] <= whole[2] + T / 2 if iny else whole[1] - T / 2 <= s2['y'] <= whole[3] + T / 2)]
                        for s2 in behind_slots:
                            slots.remove(s2)
                        # the keeper's stool: a chair stands behind two runs in five in the game (every run
                        # in the Gold Coast's shops), at the back of the segment nearest the run's middle,
                        # facing the counter, on the keeper's side when there is one to stand in
                        mx_, my_ = (whole[0] + whole[2]) / 2, (whole[1] + whole[3]) / 2
                        a_, abx = min(recs_, key=lambda rb: math.hypot(rb[0]['p'][0] - mx_, rb[0]['p'][1] - my_))
                        # (the game's rate is per run, and half its runs stand against the wall with no room
                        # for a stool: the rate over the runs that leave a keeper's side)
                        kd_ = rule.get('keeper_gap_dist') or {}
                        wide_ = sum(v for k, v in kd_.items() if int(k) >= 64) / float(sum(kd_.values()) or 1) if kd_ else 0.5
                        p_stool = min(1.0, (rule.get('behind') or {}).get('chair', 0.4) / max(0.3, wide_))
                        if gap >= 70 and rng.random() < p_stool:
                            chairs_ = fam.get('chair') or []
                            stools_ = [c_ for c_ in chairs_ if 'stool' in c_.lower()] or chairs_[:4]
                            if stools_:
                                sid_ = stools_[min(len(stools_) - 1, int(rng.random() ** 2 * len(stools_)))]
                                sb_ = mapdata.object_bounds(db, db.resolve_id(sid_))
                                if sb_:
                                    srot_ = _turn_to_face(front_of(db, sid_), sl['in'])
                                    sb0_ = _footprint(sb_, srot_, 0, 0)
                                    if iny:
                                        d_ = sb0_[3] - sb0_[1]
                                        sx_, sy_ = (abx[0] + abx[2]) / 2, (abx[1] - d_ / 2 - 8) if iny > 0 else (abx[3] + d_ / 2 + 8)
                                    else:
                                        d_ = sb0_[2] - sb0_[0]
                                        sx_, sy_ = ((abx[0] - d_ / 2 - 8) if inx > 0 else (abx[2] + d_ / 2 + 8)), (abx[1] + abx[3]) / 2
                                    sbox_ = _footprint(sb_, srot_, sx_, sy_)
                                    if fits(sbox_):
                                        srec_ = put(sid_, sx_, sy_, srot_, floor=fl, room=room['name'])
                                        if srec_:
                                            taken.append((sbox_, fl, fl + 200, False))
                                            ids.append(sid_)
                                            last_trace.append((room['name'], 'counter', sid_, 'the keeper\'s stool behind the run'))
                        if gap >= 80 and behind_slots:
                            rng.shuffle(behind_slots)
                            for kind_, rate in sorted((rule.get('behind') or {}).items(), key=lambda kv: -kv[1]):
                                if kind_ not in ('shelf', 'sack', 'crate', 'barrel', 'chest', 'bookshelf') or rng.random() >= rate:
                                    continue          # (the chair behind is the keeper's stool, laid above)
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
                        # (the main piece for the scene's other members: the segment nearest the run's middle, a_)
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
                # (a table with its back to a wall, a study's desk: the rug's back edge at the table's,
                # the rest out in the room, instead of half under the wall and refused: catalogue R5)
                edges = {'W': tb[0] - room['x_min'], 'E': room['x_max'] - tb[2], 'S': tb[1] - room['y_min'], 'N': room['y_max'] - tb[3]}
                at_ = min(edges, key=edges.get)
                # (only a rug the table stands wholly on: Project Tamriel's "furniture wholly on or off a rug";
                # a table too big for every rug gets none under it)
                for rug in fit[:4]:
                    along_x = tw >= td
                    s = rug_at(rug, (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2, along_x, furniture=False)
                    if s:
                        return rug, s
                    if edges[at_] < 60:
                        across = rug[3] if (along_x == (at_ in ('N', 'S'))) else rug[2]       # (the rug's size square to the wall)
                        t_across = td if at_ in ('N', 'S') else tw
                        d_ = max(0.0, across / 2 - t_across / 2 + 2)
                        sx_ = STEP[{'W': 'E', 'E': 'W', 'N': 'S', 'S': 'N'}[at_]]
                        s = rug_at(rug, (tb[0] + tb[2]) / 2 + sx_[0] * d_, (tb[1] + tb[3]) / 2 + sx_[1] * d_, along_x, furniture=False)
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
        no_ceiling = [0]    # (how many spots this room refused a hanging light for want of a ceiling)

        def hang_light(hid, up, gap, x, y):
            """A light hung at (x, y), its bottom `up` above the floor (lowered under a ceiling to the gap
            the game leaves there); None when it can't hang here, or when no ceiling is found over the
            spot (a light hangs from the ceiling or not at all: the user's "floating candelabras"). The
            ceiling is the building's real surface over the spot, as the health check finds it (a piece's
            box over an open stairwell is no ceiling); over an open hall or a two-storey void the light
            goes under a beam within reach, or not at all (the caller stands a lamp instead)."""
            hb = mapdata.object_bounds(db, db.resolve_id(hid))
            if not hb:
                return None
            box = _footprint(hb, 0, x, y)
            if not inside(box) or any(_overlaps(box, o[0]) for o in taken if o[3] and o[1] < fl + 150 and o[2] > fl + 4):
                return None
            if any(abs(h[0] - x) < 120 and abs(h[1] - y) < 120 for h in hung_here):
                return None
            z = fl + up - hb[2]
            ceiling = ceiling_over(x, y, fl + 100)
            if ceiling is None:
                bm = beam_near(x, y, fl)
                if bm is None:
                    no_ceiling[0] += 1
                    last_trace.append((room['name'], 'light', hid, 'no ceiling over (%.0f, %.0f): not hung' % (x, y)))
                    return None
                x, y, ceiling = bm
                box = _footprint(hb, 0, x, y)
                if not inside(box) or any(_overlaps(box, o[0]) for o in taken if o[3] and o[1] < fl + 150 and o[2] > fl + 4) \
                        or any(abs(h[0] - x) < 120 and abs(h[1] - y) < 120 for h in hung_here):
                    return None
                last_trace.append((room['name'], 'light', hid, 'hung under a beam at (%.0f, %.0f)' % (x, y)))
            # hung from the ceiling by its own hook or chain, as far below it as the game hangs that model
            # (hanggap.py): at one height off the floor a chandelier's chain stopped short of a high
            # ceiling (the user's "lots of chandeliers fail to come up to the ceiling", Big Ass Fail)
            import hanggap
            z = ceiling - hanggap.usual_gap(db, hid) - hb[5]
            if z + hb[2] < fl + 110:
                return None
            rec = put(hid, x, y, rng.uniform(0, 2 * math.pi), at_z=z, room=room['name'])
            if rec:
                got.append(hid)
                hung_here.append((x, y))
            return rec

        def void_banners():
            """Banners hung into a two-storey void (catalogue rule 5): in a room with no building over
            part of its floor by the real geometry (a hall open to the gallery above, a stairwell), as
            often as the style's own such rooms carry one (Hlaalu one in six, the Imperial styles one in
            sixteen), one or two, high on the walls (the game's median 264 up) where the wall goes on up."""
            vr = catalogue.rule(db, 'void', cell_style)
            if not vr or not (vr.get('with_banner') or 0) or rng.random() >= vr['with_banner']:
                return []
            open_tiles = [t for t in tl if ceiling_over(t['x'], t['y'], fl + 100) is None]
            if not open_tiles:
                return []
            cloth = sorted([d for d in decor if d[2] in ('banner', 'tapestry')], key=lambda d: d[2] != 'banner')
            if not cloth:
                return []
            per = vr.get('per_room') or 0.5
            n = max(1, min(2, int(per) + (1 if rng.random() < per - int(per) else 0)))
            height = vr.get('height') or 264
            spots_ = []
            for t in open_tiles:
                for s in STEP:
                    if t['pat'][s] != 'wall':
                        continue
                    off = t['pat']['offset'].get(s, T / 2 - 16) - 3
                    spots_.append((t['x'] + STEP[s][0] * off, t['y'] + STEP[s][1] * off, (-STEP[s][0], -STEP[s][1])))
            rng.shuffle(spots_)
            got_ = []
            for x_, y_, in_ in spots_:
                if len(got_) >= n:
                    break
                rid_, _hang, _kind = cloth[len(got_) % len(cloth)]
                b_ = mapdata.object_bounds(db, db.resolve_id(rid_))
                if not b_:
                    continue
                rot_ = _turn_to_face(front_of(db, rid_), in_)
                box0 = _footprint(b_, rot_, 0, 0)
                back_ = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[in_]
                px_, py_ = x_ + in_[0] * (back_ + 1), y_ + in_[1] * (back_ + 1)
                z0 = fl + height
                zm = z0 + (b_[5] - b_[2]) / 2
                # (a wall there at that height, by the building's geometry: the gallery's wall over the void)
                if not _scene:
                    floor_by_mesh(px_, py_, fl)
                hit = _scene[0].nearest((px_ + in_[0] * 20, py_ + in_[1] * 20, zm), (-in_[0], -in_[1], 0.0), 80)
                if hit is None:
                    continue
                if any(math.hypot(gx - px_, gy - py_) < T * 0.9 for gx, gy in got_pos):
                    continue
                rec_ = put(rid_, px_, py_, rot_, hang_from=z0, room=room['name'])
                if rec_:
                    got_.append(rid_)
                    got_pos.append((px_, py_))
                    last_trace.append((room['name'], 'banner', rid_, 'hung into the void, %.0f up' % height))
            return got_
        got_pos = []

        def stand_light(near=None):
            """A standing lamp of the room's palette at a wall (the game stands four lamps in five at a
            wall), where a light could not be hung: an open hall, a two-storey void, a gallery."""
            lid = pick('lamp')
            lb = mapdata.object_bounds(db, db.resolve_id(lid)) if lid else None
            if not lb:
                return None
            done_, _f = wall_spot(lb, front_of(db, lid), 'wall', pp=placesurvey.prefs(db, 'lamp', purpose), kind='lamp', near=near)
            if not done_:
                return None
            rec_ = put(lid, done_[0], done_[1], done_[2], floor=fl, room=room['name'])
            if rec_:
                taken.append((done_[3], fl, fl + 200, False))
                got.append(lid)
                last_trace.append((room['name'], 'light', lid, 'a standing lamp where no light could hang (no ceiling over the room)'))
            return rec_

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
            top = rec['p'][2] + rec['b'][5] * (rec.get('s') or 1.0)
            if not ov.tris:
                # (a container has no overlay mesh: its box top is its lid, as the dressings take it)
                return top if rec.get('type') == 'CONT' else None
            hit = ov.nearest((x, y, top + 10), (0.0, 0.0, -1.0), (rec['b'][5] - rec['b'][2]) * (rec.get('s') or 1.0) + 20)
            return None if hit is None else top + 10 - hit[0]

        def beds_in_room():
            return [f for f in fronts if f.get('kind') == 'bed']

        def screen_turn(b_, sx_, sy_):
            """The turn that stands a screen's long side across the line from the nearest bed to the room's
            middle (its face to the bed)."""
            bd_ = min(beds_in_room(), key=lambda f: math.hypot((f['box'][0] + f['box'][2]) / 2 - sx_, (f['box'][1] + f['box'][3]) / 2 - sy_))
            bcx_, bcy_ = (bd_['box'][0] + bd_['box'][2]) / 2, (bd_['box'][1] + bd_['box'][3]) / 2
            dx_, dy_ = cx - bcx_, cy - bcy_
            if math.hypot(dx_, dy_) < 1:
                dx_, dy_ = 0.0, 1.0
            rot_ = math.atan2(dx_, dy_) % (2 * math.pi)
            if (b_[3] - b_[0]) < (b_[4] - b_[1]):
                rot_ = (rot_ + math.pi / 2) % (2 * math.pi)       # (a model whose long side runs along y)
            return rot_, (bcx_, bcy_), (dx_, dy_)

        def screen_spot(b_):
            """Where a screen stands to screen the bed: a step out from the bed's side towards the room,
            or by its head, wherever it fits clear of the wall; (x, y, rot, box), face or None."""
            rot_, (bcx_, bcy_), (dx_, dy_) = screen_turn(b_, cx, cy)
            n_ = math.hypot(dx_, dy_) or 1.0
            ux_, uy_ = dx_ / n_, dy_ / n_
            bd_ = min(beds_in_room(), key=lambda f: math.hypot((f['box'][0] + f['box'][2]) / 2 - bcx_, (f['box'][1] + f['box'][3]) / 2 - bcy_))
            half_ = max(bd_['box'][2] - bd_['box'][0], bd_['box'][3] - bd_['box'][1]) / 2
            depth_ = min(b_[3] - b_[0], b_[4] - b_[1])
            for along_ in (0.0, 0.5, -0.5, 1.0, -1.0):
                for out_ in (half_ * 0.55 + depth_ / 2 + 24, half_ * 0.8 + depth_ / 2 + 24):
                    px_, py_ = bcx_ + ux_ * out_ - uy_ * along_ * half_ * 0.6, bcy_ + uy_ * out_ + ux_ * along_ * half_ * 0.6
                    box_ = _footprint(b_, rot_, px_, py_)
                    if inside(box_) and fits(box_) and min(px_ - inner[0], inner[2] - px_, py_ - inner[1], inner[3] - py_) > depth_ + 40:
                        return (px_, py_, rot_, box_), (-ux_, -uy_)
            return None

        def plant_in(prec, x_, y_, rot_):
            """What grows in a planter just stood: one of the game's own dressings of that planter model
            (shelfsurvey, as a bookshelf's books: several plants at their heights, flowers along the front,
            a shrub, rocks and ferns; the user: "garden displays should look elaborate and arranged like the
            many examples in the world"), else a single plant at the game's offset as often as the game's
            planters hold one (catalogue rule 3; three in five when the catalogue hasn't run), its bottom on
            the planter's own soil by the mesh, never floating, never loose on the floor."""
            # (not the shelf dressings of the planter model: a small pot stands on the game's tables among the
            # tableware, so its "dressing" brought a helm, cutlery and an astrolabe into the pot; the garden
            # survey's gardens hold the plants and rocks alone, and read the big beds the shelf dressings never saw)
            import gardensurvey as _gsv3
            g_ = _gsv3.dressing(db, prec['id'], rng, min_n=2, scale=prec.get('s') or 1.0)
            if g_:
                c_, s_ = math.cos(rot_), math.sin(rot_)
                n_g, first_ = 0, None
                pfp_ = _footprint([v * (prec.get('s') or 1.0) for v in prec['b']], rot_, x_, y_)
                for t in g_:
                    if db.resolve_id(t['id']) is None:
                        continue
                    wx, wy = x_ + t['x'] * c_ + t['y'] * s_, y_ - t['x'] * s_ + t['y'] * c_
                    tb = mapdata.object_bounds(db, db.resolve_id(t['id']))
                    if not tb:
                        continue
                    rooted = pfp_[0] - 4 <= wx <= pfp_[2] + 4 and pfp_[1] - 4 <= wy <= pfp_[3] + 4     # (rooted in the planter: its fronds may brush the wall)
                    # (the loose flowers the game strews round a bed on the floor; never round a pot up on a
                    # table, where they lay beside it at its rim's height: the user's "flowers outside pots")
                    raised_ = prec['p'][2] + prec['b'][2] * (prec.get('s') or 1.0) > fl + 30
                    if not rooted and (raised_ or not inside(_footprint([v * t.get('s', 1.0) for v in tb], (rot_ + t['rz']) % (2 * math.pi), wx, wy), loose=True)):
                        continue
                    if room_top and prec['p'][2] + t['z'] + tb[5] * t.get('s', 1.0) > fl + room_top - 4:
                        continue              # (a tree through a low ceiling; a flower's tip just under the ceiling line is the game's own)
                    r_ = put(t['id'], wx, wy, (rot_ + t['rz']) % (2 * math.pi), at_z=prec['p'][2] + t['z'], tilt=(t.get('rx', 0), t.get('ry', 0)),
                             scale=t.get('s', 1.0), room=room['name'], on_ref=prec.get('k'))
                    if r_:
                        n_g += 1
                        first_ = first_ or t['id']
                if n_g:
                    last_trace.append((room['name'], 'planter', prec['id'], 'the game\'s garden bed: %d things' % n_g))
                    return {'id': first_, 'n': n_g, 'p': prec['p']}
            pr = catalogue.rule(db, 'planters', cell_style)
            # (at least one planter in two gets its plant whatever the style's own rate: the Common houses'
            # planters stand empty in the game, and an empty planter box reads as a stone block)
            if piece is None and rng.random() >= max(0.5, (pr or {}).get('with_plant') or 0.6):
                return None               # (asked for this one planter, it always gets its plant)
            pl = arrangesurvey.plant_for(db, prec['id'], rng)
            if not pl:
                return None
            if not _gsv2.fits(db, pl['id'], prec['id']):
                # (a plant the game grows in pots of this size, by the survey's fit figures: no shrub in a
                # hand-wide pot; the game's plant for this very model passes, another model's may not)
                for _try in range(6):
                    pl = arrangesurvey.plant_for(db, prec['id'], rng)
                    if pl and _gsv2.fits(db, pl['id'], prec['id']):
                        break
                else:
                    last_trace.append((room['name'], 'planter', prec['id'], 'no plant of the game\'s fits this pot: left bare'))
                    return None
            c_, s_ = math.cos(rot_), math.sin(rot_)
            px_, py_ = x_ + pl['x'] * c_ + pl['y'] * s_, y_ - pl['x'] * s_ + pl['y'] * c_
            pb = mapdata.object_bounds(db, db.resolve_id(pl['id']))
            top = surface_on(prec, px_, py_)
            if not pb or top is None or not inside(_footprint([v * pl['s'] for v in pb], (rot_ + pl['rz']) % (2 * math.pi), px_, py_), loose=True):
                return None               # (and it stays in the room)
            return put(pl['id'], px_, py_, (rot_ + pl['rz']) % (2 * math.pi), at_z=top - 6 - pb[2] * pl['s'], scale=pl['s'], room=room['name'], on_ref=prec.get('k'))

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
            if a['fam'] == 'fire' and not rough and re.search(r'pit|campfire|cookingfire|cookfire|bonfire', rid.lower()):
                return kinds_laid         # (a camp's fire scene borrowed from another place: no pit in a house)
            if a['fam'] == 'fire' and not rough and not sketch and hearthsurvey.ready(db):
                return kinds_laid         # (a house's hearth comes whole from the hearth survey's sets, lay_hearth_set, not as a scene's anchor)
            if a['fam'] == 'fire' and built_hearths:
                return kinds_laid         # (the room has its hearth in the building: no second fire from a set piece)
            if a['fam'] == 'fire' and any(roomsurvey.family_of(db, p['id'], p['type']) == 'fire' for p in placed if p.get('room') == room['name']):
                return kinds_laid         # (one fire to a room: the built Redoran kitchen got three fireplaces, each with its stools)
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
            elif a['fam'] == 'planter':
                return kinds_laid         # (planting is one path, plant_room: no set piece stands a planter)
            elif ex.get('wall', True) or a['fam'] in ('bed', 'bookshelf', 'cupboard', 'shelf', 'shrine') or where in ('wall', 'corner') or _small_alone(a['fam'], ex):
                # (a wall piece, a bookshelf or a cupboard, always to a wall, whatever the game's example
                # did: a bookshelf stood 223 units out in a study from a mid-room example; a shrine too:
                # the game's stand at a median 90 from the wall, and the user's saint shrine stood "in
                # the middle of a Common stone cellar room, beside a bench, nothing round it")
                done, face = wall_spot(b, front, 'corner' if where == 'corner' else 'wall', kind='bed' if a['fam'] == 'bed' else None)
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
            # (a bed whose set piece brings its own pillows is not dressed with more)
            laid = dress(arec, purpose) if a['fam'] in DRESSED_KINDS and not run_laid \
                and not (a['fam'] == 'bed' and any(m_['fam'] == 'pillow' for m_ in ex['members'])) else None
            if a['fam'] == 'fire':
                got.extend(dress_hearth(arec, purpose))
                if re.search(r'fireplace|hearth', rid.lower()):
                    dress(arec, purpose, min_z=60)    # (the mantelpiece: what the game stands up on a fireplace)
                if 'redoran_hearth' in rid.lower():
                    hearth_stores(arec)
            if a['fam'] == 'planter' and not run_laid:
                # (the planter's garden the game's way; the set piece's own plant then stays out)
                pl_ = plant_in(arec, done[0], done[1], done[2])
                if pl_:
                    got.append(pl_['id'])
                    skip = tuple(skip) + ('plant',)
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
                if m['fam'] in ('planter', 'plant'):
                    continue              # (planting is one path, plant_room: a set piece's planter and its plant stay out)
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
                if m['fam'] == 'fire' and not rough and (re.search(r'pit|campfire|cookingfire|cookfire|bonfire', mlow) or hearthsurvey.ready(db)):
                    continue              # (no pit in a house; and a hearth only whole, from its own set)
                if m['fam'] == 'fire' and (built_hearths or any(roomsurvey.family_of(db, p['id'], p['type']) == 'fire' for p in placed if p.get('room') == room['name'])):
                    continue              # (one fire to a room)
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
                if not on_top and m['fam'] == 'screen' and beds_in_room():
                    mrot = screen_turn([v * m.get('s', 1.0) for v in mb], wx, wy)[0]     # (across the bed's line to the room: it screens something)
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
                        if not wall_by_ray([v * m.get('s', 1.0) for v in mb], mrot, wx, wy, at_z, front_of(db, mid)):
                            continue      # (a wall behind it by the building's real surfaces, as every hung thing)
                        if _tile_of(wx, wy, room, T) in win_tiles:
                            continue      # (and never over a window)
                if not on_top and mtag in ('MISC', 'APPA', 'BOOK', 'INGR', 'ALCH', 'CLOT', 'WEAP', 'ARMO', 'LOCK', 'PROB', 'REPA'):
                    # (an item of the set piece stands on a surface or not at all: the game's goblet on a
                    # low bench seat or a mat came out on the house's floorboards, the user's "random
                    # clutter on the floor")
                    continue
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

        # ---------------------------------------------------------------------------------------------
        # the Redoran manors' way (redoransurvey), the game's garden beds (gardensurvey) and its scenes with
        # their kit (scenesurvey): 2.3.2, from the user's photographs of Ald-ruhn (screenshot-catalogue-3)
        import redoransurvey as _rsv2
        import gardensurvey as _gsv2
        import scenesurvey as _ssv
        import shelfsurvey

        def scene_for_table(prec_, must_be_bare):
            """Which scene, if any, a table or desk asked to be dressed draws, at the game's rate of scenes per
            table in rooms of this kind (a scribe's desk on one study table in ten, one shop table in five);
            must_be_bare: only when nothing stands on it yet (Add one thing)."""
            if roomsurvey.family_of(db, prec_['id'], prec_['type']) not in ('table', 'counter'):
                return None
            if must_be_bare:
                import contents
                if contents.on_piece(db, cell_key, prec_['k'])['n']:
                    return None
            for sk_, _r in _ssv.scenes_for(db, purpose):
                if scene_fits_trade(sk_) and rng.random() < _ssv.table_rate(db, sk_, purpose):
                    return sk_
            return None

        def scene_fits_trade(sk_):
            """Whether a scene with its kit may be laid in this room: never the smith's corner (an anvil and its
            tools come with a forge, lay_forge_set, or not at all: the user's anvil by a writing desk with no fire
            anywhere), and in a trade's room never the scene of a piece the trade's rooms never hold (no scribe's
            desk in a smithy)."""
            if not TRADES:
                return True
            if sk_ == 'smith':
                return False
            tr_ = room_trade.get(room['name'])
            if not tr_:
                return True
            if tr_ not in _foreign:
                _foreign[tr_] = tradesurvey.foreign(db, tr_)
            return tradesurvey.SCENE_PIECE.get(sk_) not in _foreign[tr_]

        def nearest_model(rid_, kind):
            """The place's own make of a thing of this kind about the same size as the game's, as
            lay_arrangement's local(); the original when the palette has nothing of the size."""
            lst = fam.get(kind) or []
            ri0 = db.resolve_id(rid_)
            b0 = mapdata.object_bounds(db, ri0) if ri0 is not None else None
            if not lst or not b0 or any(x.lower() == rid_.lower() for x in lst[:12]):
                return rid_
            w0, d0, h0 = b0[3] - b0[0], b0[4] - b0[1], b0[5] - b0[2]
            close = []
            for cand in lst[:12]:
                rc = db.resolve_id(cand)
                bc = mapdata.object_bounds(db, rc) if rc is not None else None
                if bc and all(0.7 <= (x / y if y else 1) <= 1.4 for x, y in ((bc[3] - bc[0], w0), (bc[4] - bc[1], d0), (bc[5] - bc[2], h0))):
                    close.append(cand)
            return rng.choice(close) if close else rid_

        def bench_round(px_, py_, pw_, want_n, bench_id=None):
            """Benches on the sides of a planter island, facing it (the catalogue's 178: "benches on four
            sides"): one a side, as many as asked for, each clear of the room's things. Returns how many."""
            bid = bench_id or (fam.get('bench') or [None])[0]
            if not bid or db.resolve_id(bid) is None:
                return 0
            bb = mapdata.object_bounds(db, db.resolve_id(bid))
            if not bb:
                return 0
            bfront = front_of(db, bid)
            n_ = 0
            sides_ = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            rng.shuffle(sides_)
            for sx_, sy_ in sides_[:want_n]:
                rot_ = _turn_to_face(bfront, (-sx_, -sy_))             # (its front to the planter)
                box0 = _footprint(bb, rot_, 0, 0)
                depth_ = (box0[2] - box0[0]) / 2 if sx_ else (box0[3] - box0[1]) / 2
                x_, y_ = px_ + sx_ * (pw_ / 2 + depth_ + 28), py_ + sy_ * (pw_ / 2 + depth_ + 28)
                box_ = _footprint(bb, rot_, x_, y_)
                if not fits(box_):
                    continue
                r_ = put(bid, x_, y_, rot_, floor=fl, room=room['name'])
                if r_:
                    taken.append((box_, fl, fl + 200, False))
                    got.append(bid)
                    n_ += 1
            return n_

        def rug_tuple(rid_):
            """A rug as rug_sizes() lists them, for one id; None when unknown here."""
            for r_ in all_rugs:
                if r_[0].lower() == rid_.lower():
                    return r_
            ri_ = db.resolve_id(rid_)
            b_ = mapdata.object_bounds(db, ri_) if ri_ is not None else None
            if not b_:
                return None
            return (rid_, b_, max(b_[3] - b_[0], b_[4] - b_[1]), min(b_[3] - b_[0], b_[4] - b_[1]))

        def lay_rug_flat(rug, x_, y_, along_x, touch=False, scale=1.0):
            """A rug laid at (x, y) under whatever stands there (a rug lies under furniture): inside the room,
            on this floor, clear of doorways, not over another rug (touching allowed when tiling); scale: as
            the game lays the model (the manors' 287-unit rugs are scaled 2.2 times). The box, or None."""
            rid_, rb = rug[0], [v * scale for v in rug[1]]
            long_x = (rb[3] - rb[0]) >= (rb[4] - rb[1])
            rot_ = 0.0 if long_x == along_x else math.pi / 2
            box = _footprint(rb, rot_, x_, y_)
            x_, y_ = x_ - ((box[0] + box[2]) / 2 - x_), y_ - ((box[1] + box[3]) / 2 - y_)
            box = _footprint(rb, rot_, x_, y_)
            if not inside(box):
                return None
            pad_ = -6 if touch else 40
            if any(abs(f - fl) < 60 and _overlaps(box, (o[0] - pad_, o[1] - pad_, o[2] + pad_, o[3] + pad_), 0) for o, f in rugs):
                return None
            for qx, qy in ((box[0] + 8, box[1] + 8), (box[2] - 8, box[1] + 8), (box[0] + 8, box[3] - 8), (box[2] - 8, box[3] - 8)):
                zq = floor_by_mesh(qx, qy, fl)
                if zq is None or abs(zq - fl) > 24:
                    return None
            if not touch and any(_overlaps(box, o[0]) for o in taken if o[3] and o[1] < fl + 150 and o[2] > fl + 4):
                return None               # (not across a doorway or the stair's foot; a tiling rug may lie in a doorway, as the game's do)
            r_ = put(rid_, x_, y_, rot_, floor=fl, flat=True, room=room['name'], scale=scale)
            if not r_:
                return None
            rugs.append((box, fl))
            got.append(rid_)
            return box

        def lay_island():
            """The Redoran hall's planter island (the catalogue's 174 to 186; redoransurvey): a big round
            planter at the hall's middle with a tree or a mushroom cluster and ferns, as one of the game's own
            gardens of the model, benches at its sides facing it (five at the council hall's), candles on its
            rim, candle stands by it, a lantern above, and big rugs radiating out from it, each at the game's
            rate. Every domed entrance hall of the manors has one; another big room one time in six. Returns
            the number of things laid."""
            I = _rsv2.island_rule(db)
            if not I or not I['examples']:
                last_trace.append((room['name'], 'island', '-', 'the Redoran survey has no island yet'))
                return 0
            wide = min(room['x_max'] - room['x_min'], room['y_max'] - room['y_min'])
            if wide < 1000 or room['tiles'] * (T / 256.0) ** 2 < 12:
                last_trace.append((room['name'], 'island', '-', 'the hall is too small for one (%.0f wide)' % wide))
                return 0
            # (the hall with the front door, the manors' domed entrance, always; another big room at the game's rate)
            is_entry = purpose == 'entry' or bool(front_doors(room, refs, T, info['rooms']))
            if not is_entry and rng.random() >= max(0.15, I['with']):
                last_trace.append((room['name'], 'island', '-', 'not this hall (the game: one big room in %.0f)' % (1 / max(0.01, I['with']))))
                return 0
            exs = [e for e in I['examples'] if db.resolve_id(e['planter']) is not None and e['contents']]
            if not exs:
                last_trace.append((room['name'], 'island', '-', 'none of the game\'s island planters exists here'))
                return 0
            ex = rng.choice(exs)
            pid = ex['planter']
            pb = mapdata.object_bounds(db, db.resolve_id(pid))
            if not pb:
                return 0
            prot = rng.choice((0.0, math.pi / 2, math.pi, 1.5 * math.pi))
            done = None
            why_ = []
            for dx, dy in ((0, 0), (T * 0.25, 0), (-T * 0.25, 0), (0, T * 0.25), (0, -T * 0.25), (T * 0.5, 0), (-T * 0.5, 0), (0, T * 0.5), (0, -T * 0.5),
                           (T * 0.25, T * 0.25), (-T * 0.25, -T * 0.25), (T * 0.25, -T * 0.25), (-T * 0.25, T * 0.25)):
                box = _footprint(pb, prot, cx + dx, cy + dy)
                zq = floor_by_mesh(cx + dx, cy + dy, fl)
                if not inside(box):
                    why_.append('outside')
                elif not fits(box):
                    why_.append('taken')
                elif zq is None or abs(zq - fl) > 24:
                    why_.append('no floor')
                else:
                    done = (cx + dx, cy + dy, prot, box)
                    break
            if not done:
                last_trace.append((room['name'], 'island', pid, 'no clear floor at the hall\'s middle (%s)' % ', '.join(sorted(set(why_)))))
                return 0
            px_, py_ = done[0], done[1]
            prec = put(pid, px_, py_, prot, floor=fl, room=room['name'])
            if not prec:
                return 0
            taken.append((done[3], fl, fl + 300, False))
            got.append(pid)
            n = 1
            pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
            c_, s_ = math.cos(prot), math.sin(prot)

            def world(m):
                return px_ + m['x'] * c_ + m['y'] * s_, py_ - m['x'] * s_ + m['y'] * c_
            # what grows in it: one of the game's fullest gardens of this very model, else the example's own
            things = _gsv2.dressing(db, pid, rng, min_n=max(3, int((I.get('n_in') or 6) * 0.6))) or ex['contents']
            for t in things:
                if db.resolve_id(t['id']) is None:
                    continue
                wx, wy = world(t)
                tb = mapdata.object_bounds(db, db.resolve_id(t['id']))
                if not tb or not inside(_footprint([v * t.get('s', 1.0) for v in tb], (prot + t['rz']) % (2 * math.pi), wx, wy), loose=True):
                    continue
                if room_top and prec['p'][2] + t['z'] + tb[5] * t.get('s', 1.0) * 1.1 > fl + room_top - 40:
                    continue              # (the manors' trees stand under a dome; a low hall keeps the ferns)
                if put(t['id'], wx, wy, (prot + t['rz']) % (2 * math.pi), at_z=prec['p'][2] + t['z'], tilt=(t.get('rx', 0), t.get('ry', 0)),
                       scale=t.get('s', 1.0), room=room['name'], on_ref=prec.get('k')):
                    n += 1
            # the benches: the example's own round it when it has two or more, else one a side
            n_b = 0
            for bm in ex['benches']:
                bid = nearest_model(bm['id'], 'bench')
                bb = mapdata.object_bounds(db, db.resolve_id(bid)) if db.resolve_id(bid) is not None else None
                if not bb:
                    continue
                wx, wy = world(bm)
                rot_ = (prot + bm['rz']) % (2 * math.pi)
                box = _footprint(bb, rot_, wx, wy)
                if not fits(box):
                    continue
                r_ = put(bid, wx, wy, rot_, floor=fl, room=room['name'])
                if r_:
                    taken.append((box, fl, fl + 200, False))
                    got.append(bid)
                    n_b += 1
            if n_b < 2:
                n_b += bench_round(px_, py_, pw_, max(2, min(4, int(round(I.get('benches_mean') or 3)))))
            n += n_b
            # candles on the rim and candle stands by it, as the example had them (and the game's rates)
            for lm in ex['rim']:
                if db.resolve_id(lm['id']) is None:
                    continue
                wx, wy = world(lm)
                if put(lm['id'], wx, wy, (prot + lm['rz']) % (2 * math.pi), on_top=True, at_z=prec['p'][2] + lm['z'], room=room['name'], on_ref=prec.get('k')):
                    n += 1
            for lm in ex['stands']:
                if db.resolve_id(lm['id']) is None:
                    continue
                wx, wy = world(lm)
                lb = mapdata.object_bounds(db, db.resolve_id(lm['id']))
                box = _footprint(lb, 0, wx, wy) if lb else None
                if box and fits(box) and put(lm['id'], wx, wy, (prot + lm['rz']) % (2 * math.pi), floor=fl, room=room['name']):
                    taken.append((box, fl, fl + 150, False))
                    n += 1
            if not ex['stands'] and fam.get('lamp') and rng.random() < (I.get('stand') or 0):
                lid = fam['lamp'][0]
                lb = mapdata.object_bounds(db, db.resolve_id(lid))
                if lb:
                    for sx_, sy_ in rng.sample([(1, 1), (1, -1), (-1, 1), (-1, -1)], 2):
                        wx, wy = px_ + sx_ * (pw_ / 2 + 60), py_ + sy_ * (pw_ / 2 + 60)
                        box = _footprint(lb, 0, wx, wy)
                        if fits(box) and put(lid, wx, wy, rng.uniform(0, 2 * math.pi), floor=fl, room=room['name']):
                            taken.append((box, fl, fl + 150, False))
                            n += 1
                            break
            # the lantern above it (the game: one island in sixteen; the example's own when it had one)
            if ex['above'] or rng.random() < (I.get('lantern') or 0):
                hid_ = next((a['id'] for a in ex['above'] if db.resolve_id(a['id']) is not None), None)
                if hid_ is None:
                    hm_, _pr, _ty = roomrules.hung_lights(db, 'living')
                    hid_ = hm_[0][0] if hm_ else None
                up_ = (ex['above'][0]['up'] if ex['above'] else None) or 260
                if hid_ and hang_light(hid_, up_, None, px_, py_):
                    n += 1
            # the rugs radiating out to the arches (174, 178): the example's own, else one or two big rugs
            # laid out from the planter's sides along the hall's axes
            n_r = 0
            for rm_ in ex['rugs']:
                rug = rug_tuple(rm_['id'])
                if not rug:
                    continue
                wx, wy = world(rm_)
                along_x = abs(math.cos(prot + rm_['rz'])) >= abs(math.sin(prot + rm_['rz']))
                if lay_rug_flat(rug, wx, wy, along_x, scale=rm_.get('s') or 1.0):
                    n_r += 1
            if not n_r:
                want_r = max(1, int(round(I.get('rugs_near') or 1)))
                bigs = sorted([(r_, _rsv2.rug_scale(db, r_[0])) for r_ in big_rugs], key=lambda t_: -t_[0][2] * t_[0][3] * t_[1] * t_[1])[:4]
                sides_ = [(1, 0), (0, 1), (-1, 0), (0, -1)]
                rng.shuffle(sides_)
                for sx_, sy_ in sides_:
                    if n_r >= want_r:
                        break
                    for rug, sc_ in bigs:
                        along_x = bool(sx_)
                        reach_ = (rug[2] / 2 if (rug[1][3] - rug[1][0] >= rug[1][4] - rug[1][1]) == along_x else rug[3] / 2) * sc_
                        wx, wy = px_ + sx_ * (pw_ / 2 + reach_ + 30), py_ + sy_ * (pw_ / 2 + reach_ + 30)
                        if lay_rug_flat(rug, wx, wy, along_x, scale=sc_):
                            n_r += 1
                            break
            n += n_r
            last_trace.append((room['name'], 'island', pid, 'the planter island: %d things in it, %d benches, %d rugs' % (len(things), n_b, n_r)))
            return n

        def tile_rugs():
            """The Redoran rooms' rugs, tiling the floor (the catalogue's 181, 182: "three square rugs tiling
            the main floor"; redoransurvey: a small Redoran bedroom has 3.6 rugs per nine tiles covering half
            its floor, nine rooms in ten have one): big rugs laid side by side on the free floor until the
            room is covered as the game's rooms of the kind are. Returns how many were laid."""
            if not redoran or walls_only:
                return 0
            kind_ = {'bedroom': 'bedroom', 'living': 'living', 'hall': 'living', 'entry': 'living', 'dining': 'living', 'landing': 'living',
                     'study': 'study', 'kitchen': 'kitchen', 'storage': 'storage', 'shop': 'shop', 'tavern': 'tavern', 'corridor': 'living'}.get(purpose)
            if not kind_:
                return 0
            K = _rsv2.room_rule(db, cell_style, kind_)
            if not K or not K.get('cover_with') or K['cover_with'] < 0.25:
                return 0
            area_ = room['tiles'] * T * T
            have_ = sum((o[2] - o[0]) * (o[3] - o[1]) for o, f in rugs if abs(f - fl) < 60
                        and room['x_min'] <= (o[0] + o[2]) / 2 <= room['x_max'] and room['y_min'] <= (o[1] + o[3]) / 2 <= room['y_max']) / float(area_ or 1)
            if have_ == 0 and rng.random() >= K['rooms_with_rug']:
                return 0
            target = K['cover_with'] * rng.uniform(0.8, 1.1)
            if have_ >= target:
                return 0
            # (each rug at the scale the game lays it in Redoran rooms: the manors' big rugs are scaled 2.2 times)
            scales_ = {r_[0].lower(): _rsv2.rug_scale(db, r_[0]) for r_ in big_rugs}
            pool_ = [r_ for r_ in big_rugs if r_[2] * scales_[r_[0].lower()] <= min(room['x_max'] - room['x_min'], room['y_max'] - room['y_min']) * 0.8 and r_[2] <= 1.7 * r_[3]]
            if not pool_:
                return 0
            own_ = [r_ for r_ in pool_ if r_[0].lower() in (K.get('rug_ids') or {})]
            spots_ = []
            for t in tl:
                for dx, dy in ((0, 0), (T / 4, 0), (-T / 4, 0), (0, T / 4), (0, -T / 4), (T / 4, T / 4), (-T / 4, -T / 4)):
                    spots_.append((t['x'] + dx, t['y'] + dy))
            rng.shuffle(spots_)
            n_ = 0
            big_ = sorted(pool_, key=lambda r_: -r_[2] * r_[3] * scales_[r_[0].lower()] ** 2)[:3]
            for sx_, sy_ in spots_:
                if have_ >= target or n_ >= 12:
                    break
                # (the biggest rugs while a lot of floor is still bare, the game's own models for the rest)
                rug = rng.choice(big_) if (target - have_) > 0.25 and rng.random() < 0.6 else rng.choice(own_ if own_ and rng.random() < 0.8 else pool_)
                box = lay_rug_flat(rug, sx_, sy_, rng.random() < 0.5, touch=True, scale=scales_[rug[0].lower()])
                if box:
                    have_ += (box[2] - box[0]) * (box[3] - box[1]) / float(area_ or 1)
                    n_ += 1
            if n_:
                last_trace.append((room['name'], 'rug', '-', '%d rugs tiling the floor to %.0f%% (the game\'s %.0f%%)' % (n_, 100 * have_, 100 * K['cover_with'])))
            return n_

        def hearth_stores(hrec):
            """The sacks, urns and baskets the game stands by the Redoran kiln hearth (redoransurvey: a sack by
            one hearth in two, an urn by two in five), at the walls within reach of it."""
            s_ = _rsv2.ready(db)
            by_ = ((s_ or {}).get('hearth') or {}).get('by') or {}
            n_ = 0
            hx_, hy_ = hrec['p'][0], hrec['p'][1]
            for kind_ in ('sack', 'urn', 'basket'):
                e_ = by_.get(kind_, 0)
                k_ = int(e_) + (1 if rng.random() < e_ - int(e_) else 0)
                for _ in range(min(2, k_)):
                    rid_ = pick(kind_)
                    b_ = mapdata.object_bounds(db, db.resolve_id(rid_)) if rid_ else None
                    if not b_:
                        break
                    done_, face_ = wall_spot(b_, front_of(db, rid_), 'wall', near=(hx_, hy_), within=240)
                    if not done_:
                        break
                    r_ = put(rid_, done_[0], done_[1], done_[2], floor=fl, room=room['name'])
                    if r_:
                        taken.append((done_[3], fl, fl + 150, False))
                        got.append(rid_)
                        n_ += 1
            if n_:
                last_trace.append((room['name'], 'fire', hrec['id'], '%d stores by the kiln hearth' % n_))
            return n_

        # ---- planting: everything that grows in the room comes by this one path (gardensurvey v3, the
        # game's planting manual: packaging/nexus/planting-survey.md). The user's verdict on the old paths:
        # "small planters used in tacky ways, almost no large planters, none placed tastefully, the plant
        # arrangements never impress".

        def draw(dist):
            """One key of a {key: weight} drawn by weight; None for an empty one."""
            tot_ = sum(dist.values()) or 0
            if tot_ <= 0:
                return None
            r_ = rng.random() * tot_
            for k_, w_ in dist.items():
                r_ -= w_
                if r_ <= 0:
                    return k_
            return list(dist)[-1]

        def grow(prec, x_, y_, rot_):
            """What grows in a planter just stood (plant_in), counted."""
            pl_ = plant_in(prec, x_, y_, rot_)
            return pl_['n'] if pl_ and 'n' in pl_ else (1 if pl_ else 0)

        def planter_model(cls, wide_cap=None):
            """A floor planter model of this class the game uses most in places of this style (its commonest
            first, a less used one now and then), at the scale the game stands it at for the class (the Hlaalu
            big urn is furn_planter_02 scaled up), with its bounds at that scale: (id, bounds, scale); None
            when none fits the room."""
            models_ = _gsv2.floor_models(db, cls, style, cell_style)
            cands_ = []
            for pid in models_[:6]:
                pb = mapdata.object_bounds(db, db.resolve_id(pid))
                sc_ = _gsv2.scale_for(db, cls, pid, style, cell_style)
                if pb and abs(sc_ - 1.0) > 0.01:
                    pb = [v * sc_ for v in pb]
                if pb and max(pb[3] - pb[0], pb[4] - pb[1]) < SMALL_POT:
                    continue                  # (a tabletop pot at the game's scale is still a tabletop pot: never on the floor)
                if pb and (wide_cap is None or max(pb[3] - pb[0], pb[4] - pb[1]) <= wide_cap):
                    cands_.append((pid, pb, sc_))
            if not cands_:
                return None
            return cands_[min(len(cands_) - 1, int(rng.random() ** 2 * min(4, len(cands_))))]

        def lay_bed(pid, pb, G, sc_=1.0):
            """One of the game's garden beds (a planter 150 wide or more): where the game stands it in rooms
            of this kind (the middle of a hall, a wall, a nook, under a window), dressed as one of the game's
            own gardens of the model (several kinds at their heights, flowers to the front, a shrub or a tree),
            benches at it as often as the game's beds have them, and loose flora and rocks round it as often
            as the game stands them by a bed. pb: its bounds at scale sc_. True when laid."""
            pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
            # (the garden first: a bed the game never planted this full is not laid; "holds 2 things, the
            # game's usually hold 3" was Check this place's verdict on a thin one. Of the game's gardens of
            # the model, the one with the most things that fit under this room's ceiling: Briricca's bank bed
            # has goldenrod 236 tall, and a 256 storey took it down to three thundergloom)
            things = None
            best_n = -1
            for _k in range(5):
                cand_ = _gsv2.dressing(db, pid, rng, min_n=_gsv2.usual(db, pid) or 2, scale=sc_)
                if not cand_:
                    break
                n_fit = sum(1 for t in cand_ if db.resolve_id(t['id']) is not None and (not room_top or (
                    (mapdata.object_bounds(db, db.resolve_id(t['id'])) or [0] * 6)[5] * t.get('s', 1.0) + t['z'] + pb[2] <= room_top - 4)))
                if n_fit > best_n:
                    things, best_n = cand_, n_fit
                if n_fit >= len(cand_):
                    break
            if not things:
                last_trace.append((room['name'], 'bed', pid, 'no garden of the game\'s for the model: left out'))
                return False
            spots_ = dict(G.get('spots') or {'middle': 0.5, 'wall': 0.5})
            if not windows_here:
                spots_.pop('window', None)
            if pw_ < 170:
                spots_.pop('middle', None)    # (the game's mid-room beds are its big ones, 244 wide at the median)
            mode = draw(spots_) or 'wall'
            front = front_of(db, pid)
            done = face = None
            if mode == 'middle':
                rot_ = rng.choice((0.0, math.pi / 2))
                for dx, dy in ((0, 0), (T * 0.3, 0), (-T * 0.3, 0), (0, T * 0.3), (0, -T * 0.3), (T * 0.6, T * 0.6), (-T * 0.6, -T * 0.6)):
                    box = _footprint(pb, rot_, cx + dx, cy + dy)
                    zq = floor_by_mesh(cx + dx, cy + dy, fl)
                    if fits(box) and zq is not None and abs(zq - fl) <= 24:
                        done = (cx + dx, cy + dy, rot_, box)
                        break
            elif mode == 'window':
                w_ = rng.choice(windows_here)
                done, face = wall_spot(pb, front, 'wall', near=w_[0], side=w_[1], align=w_[0], within=T * 0.5)
            elif mode == 'nook':
                done, face = wall_spot(pb, front, 'corner')
            if not done:
                done, face = wall_spot(pb, front, 'wall')
            if not done:
                last_trace.append((room['name'], 'bed', pid, 'no spot (%s)' % mode))
                return False
            prec = put(pid, done[0], done[1], done[2], floor=fl, room=room['name'], scale=sc_)
            if not prec:
                return False
            taken.append((done[3], fl, fl + 300, False))
            got.append(pid)
            px_, py_, prot = done[0], done[1], done[2]
            c_, s_ = math.cos(prot), math.sin(prot)
            n_in = 0
            for t in things:
                if db.resolve_id(t['id']) is None:
                    continue
                wx, wy = px_ + t['x'] * c_ + t['y'] * s_, py_ - t['x'] * s_ + t['y'] * c_
                tb = mapdata.object_bounds(db, db.resolve_id(t['id']))
                if not tb:
                    continue
                # (a plant rooted in the bed stays, its fronds may brush the wall the bed stands at; one whose
                # root is outside the bed must be inside the room. A bed in a nook lost its garden to the
                # room's inner line and stood with one plant, "holds 1 thing; the game's usually hold 5")
                rooted = done[3][0] - 4 <= wx <= done[3][2] + 4 and done[3][1] - 4 <= wy <= done[3][3] + 4
                if not rooted and not inside(_footprint([v * t.get('s', 1.0) for v in tb], (prot + t['rz']) % (2 * math.pi), wx, wy), loose=True):
                    continue
                # (a tree of the game's tall halls through a low room's ceiling stays out; a flower whose tip
                # reaches the ceiling line is the game's own way: the Gold Coast beds lost their goldenrod and
                # peonies, 205 to 236 tall under a 256 storey, to a margin meant for trees)
                if room_top and prec['p'][2] + t['z'] + tb[5] * t.get('s', 1.0) > fl + room_top - 4:
                    continue      # (a goldenrod's tip 2 through the ceiling at +10 was Check this place's "taller than the room")
                if put(t['id'], wx, wy, (prot + t['rz']) % (2 * math.pi), at_z=prec['p'][2] + t['z'], tilt=(t.get('rx', 0), t.get('ry', 0)),
                       scale=t.get('s', 1.0), room=room['name'], on_ref=prec.get('k')):
                    n_in += 1
            if not n_in:
                n_in = grow(prec, px_, py_, prot)
            n_b = 0
            if mode == 'middle' and pw_ >= 180 and rng.random() < (G.get('island') or 0):
                n_b = bench_round(px_, py_, pw_, 2)
            # loose flora and rocks round it, as often as the game's beds have them by (the game's own ids
            # for rooms of the kind), in a ring just off its sides
            n_f = 0
            p_f = (G.get('flora_near_planter') or 0) * min(1.0, (G.get('flora_groups_per_9') or 0) * area_f / 0.25)
            ids_ = [i for i in (G.get('flora_ids') or {}) if db.resolve_id(i) is not None]
            if ids_ and rng.random() < p_f:
                k_ = max(1, min(6, int(G.get('flora_size') or 2) + rng.choice((-1, 0, 1))))
                for _k in range(k_ * 3):
                    if n_f >= k_:
                        break
                    fid = rng.choice(ids_)
                    fb = mapdata.object_bounds(db, db.resolve_id(fid))
                    if not fb or max(fb[3] - fb[0], fb[4] - fb[1]) > 120:
                        continue
                    ang = rng.uniform(0, 2 * math.pi)
                    d_ = pw_ / 2 + max(fb[3] - fb[0], fb[4] - fb[1]) / 2 + rng.uniform(10, 60)
                    wx, wy = px_ + math.cos(ang) * d_, py_ + math.sin(ang) * d_
                    frot = rng.uniform(0, 2 * math.pi)
                    box = _footprint(fb, frot, wx, wy)
                    if not inside(box, loose=True) or any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4 and o[0] is not done[3]):
                        continue
                    if put(fid, wx, wy, frot, floor=fl, room=room['name'], on_ref=prec.get('k')):
                        n_f += 1
            last_trace.append((room['name'], 'bed', pid, 'a garden bed (%s): %d things in it, %d benches, %d loose plants' % (mode, n_in, n_b, n_f)))
            return True

        def planter_at(mode, pb, front, near_=None):
            """A wall spot for a floor planter at one of the game's spots: a post's foot, under a window,
            beside a doorway, at a stair's foot, a corner, by a seat, a plain wall. ((x, y, rot, box), face)
            or (None, None)."""
            if mode == 'post':
                return wall_spot(pb, front, 'wall', columns_first=True, within=0)
            if mode == 'window' and windows_here:
                w_ = near_ or rng.choice(windows_here)
                return wall_spot(pb, front, 'wall', near=w_[0], side=w_[1], align=w_[0], within=T * 0.5)
            if mode == 'door' and doors_here:
                # (beside the doorway, on the door's wall: centred a door's half-width plus its own off the
                # door's middle, within the next tile's slot, so it stands within 200 of the door as the game's
                # do and the check counts; the door's own tile has no wall slot on that side)
                d_ = near_ or rng.choice(doors_here)
                side_ = wall_side_of(d_['p'][0], d_['p'][1])
                along_ = (1, 0) if side_ in 'NS' else (0, 1)
                pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
                # (just past the doorway's clear space, max(150, 0.6 tile) either side of the door's point; a
                # pot too wide to stand there within 200 of the door is not "by the door": another spot)
                off_ = max(150, T * 0.6) + pw_ / 2 + 6
                if off_ > 196:
                    return None, None
                for sgn in rng.sample((1, -1), 2):
                    tx_ = d_['p'][0] + along_[0] * sgn * off_
                    ty_ = d_['p'][1] + along_[1] * sgn * off_
                    done, face = wall_spot(pb, front, 'wall', near=(tx_, ty_), side=side_, align=(tx_, ty_), within=T * 0.7)
                    if done:
                        return done, face
                # (in a furnished room the wall slots either side of a door have mostly gone to the recipe's
                # benches, shelves and chests by the time the planting comes: the door spot comes when it is free)
                return None, None
            if mode == 'stair' and stairs_here:
                s_ = near_ or rng.choice(stairs_here)
                return wall_spot(pb, front, 'wall', near=(s_['p'][0], s_['p'][1]), within=T * 1.1)
            if mode == 'corner':
                return wall_spot(pb, front, 'corner')
            if mode == 'seat':
                # (by a bench or a table that stands at a wall: the game's pots by a seat are within 110 of it,
                # and so is the check's reach; a chair out at a table has no wall slot that close)
                seats_ = [p for p in placed if p.get('room') == room['name'] and roomsurvey.family_of(db, p['id'], p['type']) in ('bench', 'table', 'chair')
                          and min(p['p'][0] - room['x_min'], room['x_max'] - p['p'][0], p['p'][1] - room['y_min'], room['y_max'] - p['p'][1]) < T * 0.6]
                if seats_:
                    s_ = rng.choice(seats_)
                    side_ = wall_side_of(s_['p'][0], s_['p'][1])
                    sb_ = _footprint([v * (s_.get('s') or 1.0) for v in s_['b']], s_['p'][5], s_['p'][0], s_['p'][1])
                    along_ = (1, 0) if side_ in 'NS' else (0, 1)
                    half_ = ((sb_[2] - sb_[0]) if along_[0] else (sb_[3] - sb_[1])) / 2
                    pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
                    for sgn in rng.sample((1, -1), 2):
                        tx_ = s_['p'][0] + along_[0] * sgn * (half_ + pw_ / 2 + 10)
                        ty_ = s_['p'][1] + along_[1] * sgn * (half_ + pw_ / 2 + 10)
                        done, face = wall_spot(pb, front, 'wall', near=(tx_, ty_), side=side_, align=(tx_, ty_), within=T * 0.8)
                        if done and math.hypot(done[0] - s_['p'][0], done[1] - s_['p'][1]) < 125:
                            return done, face      # (within the game's 110 or so of the seat's middle, as the check reads it)
                return None, None
            if mode == 'plain wall':
                return wall_spot(pb, front, 'wall')
            return None, None

        def stand_pot(pid, pb, x_, y_, rot_, box, sc_=1.0):
            """One floor planter stood at a spot found for it (at scale sc_), with its garden; the record or None."""
            if not fits(box):
                return None
            prec = put(pid, x_, y_, rot_, floor=fl, room=room['name'], ledge=ledge_h, scale=sc_)
            if not prec:
                return None
            taken.append((box, fl, fl + 200, False))
            got.append(pid)
            grow(prec, x_, y_, rot_)
            return prec

        def beside(pid, pb, done, face, gap_, sgn):
            """Where a matching planter stands next to one just stood, gap_ apart along the wall on side sgn:
            (x, y, rot, box) when it fits in the room, else None."""
            along_ = (face[1], -face[0]) if face else (1, 0)
            x_ = done[0] + along_[0] * sgn * gap_
            y_ = done[1] + along_[1] * sgn * gap_
            box = _footprint(pb, done[2], x_, y_)
            if not inside(box) or not fits(box):
                return None
            if face and T and not wall_behind(pb, done[2], x_, y_, room, T, front_of(db, pid), reach=30):
                return None
            return (x_, y_, done[2], box)

        def company_plan(pb, done, face):
            """Where an urn or a basket stands beside a pot that would otherwise stand alone (a corner single):
            the game stands a vase, a basket or a lamp by one planter in four (wallsurvey2), and Check this
            place's lone-pot test wants company (a planter, an urn, a bench, a table, a chair or a basket by its
            family) or a post, a door, a window, a seat or a stair within reach. (rid, x, y, rot, box) or None."""
            along_ = (face[1], -face[0]) if face else (1, 0)
            pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
            for kind_ in ('urn',):
                # (an urn: the one companion every reader agrees on; a basket named only "Basket" in its record,
                # or the Common food basket, is no company to the check's family reading)
                rid_ = pick(kind_)
                b_ = mapdata.object_bounds(db, db.resolve_id(rid_)) if rid_ else None
                if not b_ or roomsurvey.family_of(db, rid_, db.recs[db.resolve_id(rid_)][0]) != kind_:
                    continue
                w_ = max(b_[3] - b_[0], b_[4] - b_[1])
                rot_ = _turn_to_face(front_of(db, rid_), face) if face else done[2]
                for sgn_ in rng.sample((1, -1), 2):
                    x_ = done[0] + along_[0] * sgn_ * (pw_ / 2 + w_ / 2 + 12)
                    y_ = done[1] + along_[1] * sgn_ * (pw_ / 2 + w_ / 2 + 12)
                    box_ = _footprint(b_, rot_, x_, y_)
                    if inside(box_) and fits(box_):
                        return (rid_, x_, y_, rot_, box_)
            return None

        def wall_side_of(x_, y_):
            """The room's wall nearest a point: 'N', 'S', 'E' or 'W'."""
            edges_ = {'N': room['y_max'] - y_, 'S': y_ - room['y_min'], 'E': room['x_max'] - x_, 'W': x_ - room['x_min']}
            return min(edges_, key=lambda k: abs(edges_[k]))

        def flank_door(pid, pb, d_, sc_=1.0):
            """Two matching planters either side of a doorway, as the game pairs its urns at a door (the
            survey's pairs: flank_door share): each centred a door's half-width plus its own off the door's
            middle, back to the door's wall. The records laid."""
            edges_ = {'N': room['y_max'] - d_['p'][1], 'S': d_['p'][1] - room['y_min'], 'E': room['x_max'] - d_['p'][0], 'W': d_['p'][0] - room['x_min']}
            side_ = min(edges_, key=lambda k: abs(edges_[k]))
            along_ = (1, 0) if side_ in 'NS' else (0, 1)
            pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
            front = front_of(db, pid)
            out_ = []
            off_ = max(150, T * 0.6) + pw_ / 2 + 6        # (just past the doorway's clear space)
            if off_ > 196:
                return out_
            for sgn in rng.sample((1, -1), 2):
                tx_ = d_['p'][0] + along_[0] * sgn * off_
                ty_ = d_['p'][1] + along_[1] * sgn * off_
                done, face = wall_spot(pb, front, 'wall', near=(tx_, ty_), side=side_, align=(tx_, ty_), within=T * 0.7)
                if not done:
                    continue
                prec = stand_pot(pid, pb, done[0], done[1], done[2], done[3], sc_)
                if prec:
                    out_.append(prec)
            return out_

        def plant_room(island_here):
            """The room's planting, all of it, as the game plants rooms of this kind in places of this style
            (gardensurvey v3): as many floor planters as the game's rooms of this size hold (drawn from the
            game's own count distribution), each of the class the style uses (a garden bed, a big urn, a mid
            pot; the style's own models, its commonest first), at one of the game's spots for the class (a
            post's foot, under a window, flanking a doorway, a stair's foot, a corner, by a seat), grouped as
            the game groups them (a matching pair either side of a door, a row of three under a window, a pair
            along a wall), never alone at a plain wall or out in the open; tabletop pots only on tables and
            shelves at the game's rate; hanging planters hung from a beam or the ceiling at the game's rate
            and height; every pot's plant one of the game's whole gardens of that model (or a plant the game
            grows in pots of its size), its bottom in the pot. Returns the number of planters laid."""
            if walls_only or sketch or purpose in ('storage', 'barracks', 'armoury', 'training', 'guardroom', 'mess', 'camp', 'ruin'):
                return 0
            G = _gsv2.rule(db, purpose)
            if not G or 'floor_per_9' not in G:
                last_trace.append((room['name'], 'planter', '-', 'the garden survey has not run yet: nothing planted'))
                return 0
            S = _gsv2.style_rule(db, style, cell_style) or {}
            dens_ = L['density'] if L else 1.0
            tiles9_ = room['tiles'] * (T / 256.0) ** 2
            bucket_ = 'small' if tiles9_ <= 6 else 'mid' if tiles9_ <= 12 else 'large'
            dist_ = (G.get('per_room') or {}).get(bucket_) or {}
            if sum(dist_.values()) < 8:
                # (too few rooms of this size seen: the kind's rate per nine tiles instead)
                e_ = G['floor_per_9'] * area_f
                n_ = int(e_) + (1 if rng.random() < e_ - int(e_) else 0)
            else:
                n_ = int(draw(dist_) or 0)
            if dens_ != 1.0 and n_:
                nf_ = n_ * dens_
                n_ = int(nf_) + (1 if rng.random() < nf_ - int(nf_) else 0)
            n_ = min(n_, 4 if bucket_ == 'large' else 3 if bucket_ == 'mid' else 2)
            if purpose == 'entry' and entry_axis is not None and n_ == 1:
                n_ = 2                        # (an entrance hall's planters stand in a pair about the door's axis, R1)
            if island_here:
                n_ -= 1
            laid_ = 0
            if n_ <= 0:
                last_trace.append((room['name'], 'planter', '-', 'no floor planter this time (the game: %s in %s rooms of the kind)' % (dist_ or G['floor_per_9'], bucket_)))
            classes_ = dict(S.get('classes') or G.get('class_share') or {'pot': 0.6, 'urn': 0.2, 'bed': 0.2})
            wide_ = min(room['x_max'] - room['x_min'], room['y_max'] - room['y_min'])
            # (the big models the game uses for the style first: a room's first planter is a garden bed or a
            # big urn when the style stands them at all (one in twenty of its floor planters or more); the
            # game's own rooms are mostly small pots, and the user's verdict on those was "small planters used
            # in tacky ways, almost no large planters")
            big_first = [c_ for c_ in ('bed', 'urn') if classes_.get(c_, 0) >= 0.05]
            if S.get('spots'):
                # (the style's own spots for a class only when it was seen at twenty or more; the kind's else)
                S = dict(S, spots={c_: v_ for c_, v_ in S['spots'].items() if sum((S.get('models') or {}).get(c_, {}).values()) >= 20})
            groups_ = dict(G.get('groups') or {'single': 0.7, 'pair': 0.2, 'row': 0.1})
            groups_['pair'] = groups_.get('pair', 0) + groups_.pop('cluster', 0)
            gap_p = ((_gsv2.ready(db) or {}).get('pairs') or {}).get('spacing') or [120, 140, 170, 220, 300]
            gap_r = ((_gsv2.ready(db) or {}).get('rows') or {}).get('gap') or [100, 120, 140, 170, 220]
            tries_ = 0
            while laid_ < n_ and tries_ < n_ + 3:
                tries_ += 1
                cls = (big_first[0] if laid_ == 0 and tries_ == 1 and big_first else draw(classes_)) or 'pot'
                if cls == 'bed' and (wide_ < 700 or purpose in ('bedroom', 'corridor', 'landing')):
                    cls = 'urn'               # (no garden bed in a small room, a bedroom or a passage)
                pm_ = planter_model(cls, wide_cap=wide_ * 0.45 if cls == 'bed' else wide_ * 0.3)
                if pm_ is None:
                    pm_ = planter_model('pot' if cls != 'pot' else 'urn', wide_cap=wide_ * 0.3)
                if pm_ is None:
                    last_trace.append((room['name'], 'planter', cls, 'no floor planter of the class in the style: left out'))
                    break
                pid, pb, sc_ = pm_
                if max(pb[3] - pb[0], pb[4] - pb[1]) >= _gsv2.BED_W:
                    # (a bed by its size as stood: the Gold Coast bed at half size is an urn, and stands as one)
                    if lay_bed(pid, pb, G, sc_):
                        laid_ += 1
                    continue
                # a mid pot or a big urn: the game's spot for the class, among the spots this room has
                spots_ = dict(((S.get('spots') or {}).get(cls) or (G.get('cls_spots') or {}).get(cls) or {'post': 0.3, 'window': 0.2, 'door': 0.2, 'corner': 0.2, 'stair': 0.1}))
                spots_.pop('open', None)
                if not windows_here:
                    spots_.pop('window', None)
                if not doors_here:
                    spots_.pop('door', None)
                if not stairs_here:
                    spots_.pop('stair', None)
                if not col_slots:
                    spots_.pop('post', None)
                plain_ = spots_.pop('plain wall', 0)
                pattern = draw(groups_) or 'single'
                if n_ - laid_ < 2:
                    pattern = 'single'
                if pattern != 'single':
                    spots_['plain wall'] = plain_      # (a pair or a row along a plain wall is company enough)
                if purpose == 'entry' and entry_axis is not None and doors_here and 'door' in spots_:
                    spots_ = {'door': 1.0}
                    pattern = 'pair'
                mode = draw(spots_)
                if mode is None:
                    last_trace.append((room['name'], 'planter', pid, 'no post, window, doorway, seat, stair or corner to stand by: left out'))
                    continue
                front = front_of(db, pid)
                n_here = 0
                if pattern == 'pair' and mode == 'door' and ((purpose == 'entry' and entry_axis is not None) or rng.random() < (G.get('pair_door') or 0.5)):
                    recs_ = flank_door(pid, pb, rng.choice(doors_here), sc_)
                    n_here = len(recs_)
                    if n_here:
                        last_trace.append((room['name'], 'planter', pid, 'a matching pair flanking the doorway (%d)' % n_here))
                if not n_here:
                    done, face = planter_at(mode, pb, front)
                    # (no spot of that kind free: the room's other spots, by the game's weight for them, before
                    # giving up; a room with its corners taken still has its posts and doorways)
                    tried_ = {mode}
                    while not done and len(tried_) < 4:
                        rest_ = {m_: w_ for m_, w_ in spots_.items() if m_ not in tried_ and m_ != 'plain wall'}
                        mode = draw(rest_)
                        if mode is None:
                            break
                        tried_.add(mode)
                        done, face = planter_at(mode, pb, front)
                    if not done:
                        last_trace.append((room['name'], 'planter', pid, 'no free spot (%s): left out' % ', '.join(sorted(tried_))))
                        continue
                    pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
                    # (the partners' spots first: a pot that would stand alone at a plain wall is not stood
                    # at all, the user's "never"; a row of three under the window, the middle one on the
                    # window's line and one either side at the game's gap; a pair at the game's spacing)
                    more_ = []
                    if pattern == 'row':
                        gap_ = max(pw_ + 10, gap_r[2])
                        more_ = [d2_ for d2_ in (beside(pid, pb, done, face, gap_, sgn) for sgn in (1, -1)) if d2_]
                    elif pattern == 'pair':
                        gap_ = max(pw_ + 10, gap_p[2])
                        for sgn in rng.sample((1, -1), 2):
                            d2_ = beside(pid, pb, done, face, gap_, sgn)
                            if d2_:
                                more_ = [d2_]
                                break
                    if mode == 'plain wall' and not more_:
                        last_trace.append((room['name'], 'planter', pid, 'would stand alone at a plain wall: left out'))
                        continue
                    comp_ = None
                    if mode == 'corner' and not more_:
                        # (a single in a corner keeps company, an urn at its side: the game's corner pots have a
                        # vase or a basket by them one time in four, and the user's rule is that no pot stands
                        # alone with nothing it belongs with; the urn first, and no urn, no pot)
                        comp_ = company_plan(pb, done, face)
                        r2_ = put(comp_[0], comp_[1], comp_[2], comp_[3], floor=fl, room=room['name'], ledge=ledge_h) if comp_ else None
                        if not r2_:
                            last_trace.append((room['name'], 'planter', pid, 'would stand alone in the corner (no room for an urn beside it): left out'))
                            continue
                        taken.append((comp_[4], fl, fl + 200, False))
                        got.append(comp_[0])
                    prec = stand_pot(pid, pb, done[0], done[1], done[2], done[3], sc_)
                    if not prec:
                        continue
                    n_here = 1
                    for d2_ in more_:
                        if stand_pot(pid, pb, d2_[0], d2_[1], d2_[2], d2_[3], sc_):
                            n_here += 1
                    last_trace.append((room['name'], 'planter', pid, '%s at the %s (%d)%s' % (pattern, mode, n_here, (' with %s beside it' % comp_[0]) if comp_ else '')))
                laid_ += n_here
            # tabletop pots on the room's tables and shelves, at the game's rate for the kind of room
            e_s = (G.get('furniture_pots_per_9') or 0) * area_f * dens_      # (the game's pots on tables and shelves; not its sills and ledges)
            n_s = int(e_s) + (1 if rng.random() < e_s - int(e_s) else 0)
            n_s = min(n_s, 3)
            if n_s:
                # (the pots the game stands on tables and shelves in places of this style, the small pot of
                # the floor as often as not; the tabletop class of every style when the style has none)
                # (only the pots the game keeps on furniture at least two times in five: Imperial
                # t_imp_furn_planter_03 is on a table 19 times in 128, a floor pot, too big for a table top)
                GM_ = (_gsv2.ready(db) or {}).get('models') or {}
                pots_ = [i for i, n_ in (S.get('surface_models') or {}).items() if db.resolve_id(i) is not None
                         and _gsv2.classify(db, i) not in ('bed', 'urn', 'hanging')
                         and n_ >= 0.4 * max(1, (GM_.get(i.lower()) or {}).get('n') or n_)] \
                    or _gsv2.floor_models(db, 'tabletop', style, cell_style)[:6]
                hosts_ = [p for p in placed if p.get('room') == room['name'] and not p.get('arch') and p['type'] in ('STAT', 'ACTI', 'CONT')
                          and roomsurvey.family_of(db, p['id'], p['type']) in ('table', 'counter', 'shelf', 'cupboard', 'chest', 'bookshelf')]
                n_done = 0
                for _k in range(n_s * 4):
                    if n_done >= n_s or not pots_ or not hosts_:
                        break
                    pid = rng.choice(pots_[:4])
                    pb = mapdata.object_bounds(db, db.resolve_id(pid))
                    h_ = rng.choice(hosts_)
                    if not pb:
                        continue
                    hb_ = _footprint([v * (h_.get('s') or 1.0) for v in h_['b']], h_['p'][5], h_['p'][0], h_['p'][1])
                    pw_ = max(pb[3] - pb[0], pb[4] - pb[1])
                    if hb_[2] - hb_[0] < pw_ + 16 or hb_[3] - hb_[1] < pw_ + 16:
                        continue
                    # (towards one end of the top, as the game's pots stand, not dead centre on a table)
                    x_ = rng.uniform(hb_[0] + pw_ / 2 + 6, hb_[2] - pw_ / 2 - 6)
                    y_ = rng.uniform(hb_[1] + pw_ / 2 + 6, hb_[3] - pw_ / 2 - 6)
                    top_ = surface_on(h_, x_, y_)
                    if top_ is None or top_ < fl + 64 or top_ > fl + 200:
                        continue              # (on the piece's real top by its mesh, never on its box; not on a low chest, where it reads as a pot on the floor)
                    fp_ = _footprint(pb, h_['p'][5], x_, y_)
                    if any(p_.get('room') == room['name'] and p_.get('b') and p_['type'] in THING_TAGS_ON_TOP and abs(p_['p'][2] - (top_ - pb[2])) < 60
                           and _overlaps(fp_, _footprint([v * (p_.get('s') or 1.0) for v in p_['b']], p_['p'][5], p_['p'][0], p_['p'][1]), -2) for p_ in placed if p_ is not h_):
                        continue              # (not into the dressing already on the table)
                    prec = put(pid, x_, y_, h_['p'][5], at_z=top_ - pb[2], room=room['name'], on_ref=h_.get('k'))
                    if not prec:
                        continue
                    n_done += 1
                    grow(prec, x_, y_, h_['p'][5])
                    last_trace.append((room['name'], 'planter', pid, 'a tabletop pot on %s' % h_['id']))
            # a pot that came bare by another path (a shelf's or a table's dressing stands the pot, and its plant
            # was left out or never in the dressing) gets its plant here: every pot planted, size-matched
            for p_ in [p for p in placed if p.get('room') == room['name'] and p['type'] in ('STAT', 'ACTI', 'CONT') and shelfsurvey_PLANTER.search(p['id'].lower())]:
                k_ = p_.get('k')
                if not k_ or any(v.get('on') == k_ for v in c['refs'].values()):
                    continue              # (something rides on it already: its plant, or a pot in a pot)
                if grow(p_, p_['p'][0], p_['p'][1], p_['p'][5]):
                    last_trace.append((room['name'], 'planter', p_['id'], 'a bare pot of a dressing\'s, planted'))
            # hanging planters, from a beam or the ceiling, at the game's rate and height
            e_h = (G.get('hung_per_9') or 0) * area_f * dens_
            n_h = int(e_h) + (1 if rng.random() < e_h - int(e_h) else 0)
            n_h = min(n_h, 2)
            if n_h:
                H = (_gsv2.ready(db) or {}).get('hanging') or {}
                hm_ = [i for i in (S.get('hanging_models') or {}) if db.resolve_id(i) is not None] or _gsv2.floor_models(db, 'hanging', style, cell_style)[:4]
                low_h = (H.get('height') or [150, 170, 234, 350, 370])[2]      # (no lower than the game's median: head height, not hip height)
                n_done = 0
                pts_ = [(w_[0][0] + {'N': 0, 'S': 0, 'E': -1, 'W': 1}[w_[1]] * T * 0.35, w_[0][1] + {'N': -1, 'S': 1, 'E': 0, 'W': 0}[w_[1]] * T * 0.35) for w_ in windows_here]
                pts_ += [(sl['x'] + sl['in'][0] * 70, sl['y'] + sl['in'][1] * 70) for sl in slots[:8]]
                rng.shuffle(pts_)
                for (qx, qy) in pts_:
                    if n_done >= n_h or not hm_:
                        break
                    pid = rng.choice(hm_[:3])
                    pb = mapdata.object_bounds(db, db.resolve_id(pid))
                    if not pb:
                        continue
                    bm_ = beam_near(qx, qy, fl, reach=160)
                    if bm_:
                        qx, qy, top_z = bm_
                    else:
                        top_z = ceiling_over(qx, qy, fl + 100)
                    if top_z is None:
                        continue
                    at_z = top_z - 4 - pb[5]
                    if at_z + pb[2] < fl + low_h:
                        continue              # (too low a ceiling to hang it at the game's height)
                    if any(math.hypot(hx - qx, hy - qy) < 70 for hx, hy in hung_here):
                        continue
                    box = _footprint(pb, 0.0, qx, qy)
                    if not inside(box, loose=True):
                        continue
                    prec = put(pid, qx, qy, rng.choice((0.0, math.pi / 2, math.pi, 1.5 * math.pi)), at_z=at_z, room=room['name'])
                    if not prec:
                        continue
                    hung_here.append((qx, qy))
                    got.append(pid)
                    n_done += 1
                    grow(prec, qx, qy, prec['p'][5])
                    last_trace.append((room['name'], 'planter', pid, 'hung from %s at %.0f up' % ('a beam' if bm_ else 'the ceiling', at_z + pb[2] - fl)))
            return laid_

        def rec_of_box(box_):
            """The placed table whose footprint this is (tables[] keeps boxes, not records)."""
            for p in placed:
                if p.get('room') != room['name'] or not p.get('b'):
                    continue
                fp_ = _footprint([v * (p.get('s') or 1.0) for v in p['b']], p['p'][5], p['p'][0], p['p'][1])
                if all(abs(fp_[i] - box_[i]) < 2 for i in range(4)):
                    return p
            return None

        def lay_scene(sk, on_rec=None):
            """One of the game's scenes with its kit, laid whole (scenesurvey): the scribe's desk or the
            alchemist's bench on a table standing here (a bare one; the piece asked for, on_rec, when Dress
            this or Add one thing asked), each piece at the game's own spot on the table, resting on its real
            surface; the painter's corner or the smith's at a wall, the easel or the anvil with its stool, its
            small table and what rides on them at the game's exact offsets. Never a piece of it alone
            (shelfsurvey.SCENE_ONLY keeps the single pieces off everyday tables). Returns the number laid."""
            S = _ssv.ready(db)
            if not S:
                return 0
            bare_ = [t for t in tables if not t.get('counter') and not t.get('dressed')] if on_rec is None else []
            ex = None
            # (the scribe's desk and the alchemist's bench are things on a table: never laid loose on the floor
            # from an example whose base the survey could not name; the easel and the anvil stand on the floor)
            floor_ok = sk in ('painter', 'smith')
            if on_rec is not None:
                ex = _ssv.pick(db, sk, rng, on_table=True, purpose=purpose)
            else:
                ex = _ssv.pick(db, sk, rng, on_table=(True if (bare_ and rng.random() < 0.8) or not floor_ok else None), purpose=purpose)
                if ex and ex['base'] is None and not floor_ok:
                    ex = _ssv.pick(db, sk, rng, on_table=True, purpose=purpose)
            if not ex:
                return 0
            if ex['base'] and ex['base']['fam'] in ('table', 'counter'):
                trec = on_rec
                if trec is None:
                    if bare_:
                        t_ = rng.choice(bare_)
                        trec = rec_of_box(t_['box'])
                    if trec is None:
                        tid = nearest_model(ex['base']['id'], 'table')
                        tb0 = mapdata.object_bounds(db, db.resolve_id(tid)) if db.resolve_id(tid) is not None else None
                        if not tb0 or len([t for t in tables if not t.get('counter')]) >= table_cap:
                            return 0
                        done_, face_ = wall_spot(tb0, front_of(db, tid), 'wall', pp=placesurvey.prefs(db, 'table', purpose), kind='table')
                        if not done_:
                            return 0
                        trec = put(tid, done_[0], done_[1], done_[2], floor=fl, room=room['name'])
                        if not trec:
                            return 0
                        taken.append((done_[3], fl, fl + 200, False))
                        got.append(tid)
                        tables.append({'box': done_[3], 'items': [], 'dressed': True, 'counter': False})
                if trec is None:
                    return 0
                ts_ = trec.get('s') or 1.0
                tbox = _footprint([v * ts_ for v in trec['b']], trec['p'][5], trec['p'][0], trec['p'][1])
                t_ = next((t for t in tables if all(abs(t['box'][i] - tbox[i]) < 2 for i in range(4))), None)
                items_ = t_['items'] if t_ else []
                R = trec['p'][5]
                c_, s_ = math.cos(R), math.sin(R)
                n_ = 0
                for m in ex['members']:
                    mri = db.resolve_id(m['id'])
                    mb = mapdata.object_bounds(db, mri) if mri is not None else None
                    if not mb:
                        continue
                    wx = trec['p'][0] + m['x'] * c_ + m['y'] * s_
                    wy = trec['p'][1] - m['x'] * s_ + m['y'] * c_
                    mrot = (R + m['rz']) % (2 * math.pi)
                    ms = m.get('s', 1.0)
                    if m['on']:
                        if not (tbox[0] + 2 <= wx <= tbox[2] - 2 and tbox[1] + 2 <= wy <= tbox[3] - 2):
                            continue
                        top_ = surface_on(trec, wx, wy)
                        if top_ is None:
                            continue
                        box = _footprint([v * ms for v in mb], mrot, wx, wy)
                        if any(_overlaps(box, o, 0) for o in items_):
                            continue
                        if db.recs[mri][0] == 'LIGH' and HANGING_LIGHT.search(m['id'].lower()):
                            continue
                        tb_ = shelfsurvey.box_turned(mb, m.get('rx', 0), m.get('ry', 0), mrot, ms)
                        at_z = top_ + max(-2.0, m['z']) - tb_[2]
                        r_ = put(m['id'], wx, wy, mrot, on_top=True, at_z=at_z, tilt=(m.get('rx', 0), m.get('ry', 0)), scale=ms, room=room['name'], on_ref=trec.get('k'))
                        if r_:
                            items_.append(box)
                            n_ += 1
                    elif m.get('floor') and m['fam'] in ('chair', 'bench', 'stool', 'planter', 'crate', 'barrel', 'chest', 'urn', 'basket', 'sack'):
                        box = _footprint([v * ms for v in mb], mrot, wx, wy)
                        if not fits(box):
                            continue
                        if m['fam'] in ('chair', 'bench'):
                            dvx, dvy = (tbox[0] + tbox[2]) / 2 - wx, (tbox[1] + tbox[3]) / 2 - wy
                            dn = math.hypot(dvx, dvy) or 1.0
                            mrot = _turn_to_face(front_of(db, m['id']), (dvx / dn, dvy / dn))
                            box = _footprint([v * ms for v in mb], mrot, wx, wy)
                            if max(tbox[0] - box[2], box[0] - tbox[2], tbox[1] - box[3], box[1] - tbox[3], 0) > 60:
                                continue      # (the game's chair stood at a bigger table: here it would sit at nothing)
                            if not fits(box) or not keep_approach(box, mrot, front_of(db, m['id'])):
                                continue
                        r_ = put(m['id'], wx, wy, mrot, floor=fl, room=room['name'], scale=ms)
                        if r_:
                            taken.append((box, fl, fl + 200, False))
                            got.append(m['id'])
                            n_ += 1
                if t_ is not None:
                    t_['dressed'] = True
                if n_:
                    last_trace.append((room['name'], 'scene', sk, '%d pieces on %s' % (n_, trec['id'])))
                return n_
            if on_rec is not None or ex['base']:
                return 0
            # a floor scene: the easel or the anvil at a wall (out in the room when no wall slot is free), its
            # stool, its small table and the rest at the game's exact offsets, what rides on a piece on it
            aid = ex['anchor']['id']
            ab = mapdata.object_bounds(db, db.resolve_id(aid))
            if not ab:
                return 0
            front = front_of(db, aid)
            done_, face_ = wall_spot(ab, front, 'wall')
            if not done_:
                rot_ = _turn_to_face(front, (0, -1)) if front else 0.0
                for dx, dy in ((0, 0), (96, 0), (-96, 0), (0, 96), (0, -96)):
                    box = _footprint(ab, rot_, cx + dx, cy + dy)
                    if fits(box):
                        done_ = (cx + dx, cy + dy, rot_, box)
                        break
            if not done_:
                return 0
            arec = put(aid, done_[0], done_[1], done_[2], floor=fl, room=room['name'])
            if not arec:
                return 0
            taken.append((done_[3], fl, fl + 200, False))
            got.append(aid)
            n_ = 1
            R = done_[2]
            c_, s_ = math.cos(R), math.sin(R)
            hosts_ = [done_[3]]
            # the floor pieces first (a stool, a small table, a bucket, a log pile), then what rides on them
            order_ = sorted(ex['members'], key=lambda m: 0 if m.get('floor') else 1)
            for m in order_:
                mri = db.resolve_id(m['id'])
                mb = mapdata.object_bounds(db, mri) if mri is not None else None
                if not mb:
                    continue
                wx = arec['p'][0] + m['x'] * c_ + m['y'] * s_
                wy = arec['p'][1] - m['x'] * s_ + m['y'] * c_
                mrot = (R + m['rz']) % (2 * math.pi)
                ms = m.get('s', 1.0)
                tag_ = db.recs[mri][0]
                if m.get('floor'):
                    if m['fam'] in ('bookshelf', 'cupboard', 'shelf', 'screen') or max(mb[3] - mb[0], mb[4] - mb[1]) > 160:
                        continue              # (the wall pieces and the big things the example stood near are not the scene)
                    box = _footprint([v * ms for v in mb], mrot, wx, wy)
                    if not fits(box):
                        continue
                    r_ = put(m['id'], wx, wy, mrot, floor=fl, room=room['name'], scale=ms)
                    if r_:
                        taken.append((box, fl, fl + 200, False))
                        got.append(m['id'])
                        hosts_.append(box)
                        n_ += 1
                    continue
                if tag_ == 'LIGH' and HANGING_LIGHT.search(m['id'].lower()):
                    continue
                if tag_ in ('STAT', 'ACTI', 'CONT') and max(mb[3] - mb[0], mb[4] - mb[1]) * ms > 48:
                    # (a big piece the game's example had up on a step or a raised floor: here it stands on
                    # the floor like the rest, or not at all; two archery targets and a rigging tackle from a
                    # barracks' smith scene hung 57 to 115 in the air in the suite's Hlaalu kitchen)
                    if m['fam'] in ('bookshelf', 'cupboard', 'shelf', 'screen') or max(mb[3] - mb[0], mb[4] - mb[1]) > 160:
                        continue
                    box = _footprint([v * ms for v in mb], mrot, wx, wy)
                    if fits(box):
                        r_ = put(m['id'], wx, wy, mrot, floor=fl, room=room['name'], scale=ms)
                        if r_:
                            taken.append((box, fl, fl + 200, False))
                            got.append(m['id'])
                            hosts_.append(box)
                            n_ += 1
                    continue
                if not any(h_[0] - 6 <= wx <= h_[2] + 6 and h_[1] - 6 <= wy <= h_[3] + 6 for h_ in hosts_):
                    continue                  # (a thing the game had on a piece that is not here: left out)
                box = _footprint([v * ms for v in mb], mrot, wx, wy)
                on_anchor = hosts_[0][0] - 6 <= wx <= hosts_[0][2] + 6 and hosts_[0][1] - 6 <= wy <= hosts_[0][3] + 6
                if not on_anchor and not inside(box, loose=True):
                    continue                  # (the canvas on the easel goes where the easel is; the rest keeps to the room)
                # (the same models as the game's at the same offsets on a flat floor: the game's own heights)
                if put(m['id'], wx, wy, mrot, on_top=True, at_z=arec['p'][2] + m['zo'], tilt=(m.get('rx', 0), m.get('ry', 0)), scale=ms, room=room['name'], on_ref=arec.get('k')):
                    n_ += 1
            last_trace.append((room['name'], 'scene', sk, '%d pieces round the %s' % (n_, aid)))
            return n_

        def lay_scenes():
            """The scenes the game lays in rooms of this kind, each at the game's rate per room (a scribe's desk
            in one study in two, an alchemist's bench in one in six, a painter's corner in one in a hundred and
            sixty); a trade's own scene always (the painter's easel, the apothecary's apparatus, the smith's
            forge: wealthsurvey's extras). Returns how many scenes were laid."""
            if walls_only or purpose not in ('study', 'shop', 'living', 'kitchen', 'tavern', 'bedroom', 'shrine', 'hall', 'entry', 'dining'):
                return 0
            forced = {sk for sk, ex_ in (('painter', 'easel'), ('alchemist', 'apparatus'), ('scribe', 'desk')) + ((('smith', 'forge'),) if not TRADES else ())
                      if ex_ in extras_left}
            tr_ = room_trade.get(room['name'])
            if TRADE_SCENE.get(tr_):
                forced.add(TRADE_SCENE[tr_])         # (an apothecary's bench, a bookseller's desk: the trade's own, always)
            laid_ = 0
            for sk, r_ in _ssv.scenes_for(db, purpose) + [(sk, 0.0) for sk in forced if not any(s2 == sk for s2, _r in _ssv.scenes_for(db, purpose))]:
                if not scene_fits_trade(sk):
                    continue
                p_ = 1.0 if sk in forced else min(1.0, r_ * area_f * (L['density'] if L else 1.0))
                if rng.random() >= p_:
                    continue
                if lay_scene(sk):
                    laid_ += 1
                    for ex_ in ({'painter': 'easel', 'alchemist': 'apparatus', 'smith': 'forge', 'scribe': 'desk'}.get(sk),):
                        if ex_ in extras_left:
                            extras_left.remove(ex_)
                    if laid_ >= 2:
                        break
            return laid_

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
                # (one more thing on it, everything on it kept; a bare desk draws a whole scene, the scribe's
                # inkwell, quill and papers together, as often as the game's tables of the kind carry one)
                sk_ = scene_for_table(prec, True)
                n_sc = lay_scene(sk_, on_rec=prec) if sk_ else 0
                if n_sc:
                    res_ = {'placed': n_sc, 'added': sk_, 'name': 'the %s\'s things (%d of them)' % (sk_, n_sc), 'kind': 'scene', 'with': []}
                else:
                    res_ = add_one(prec, purpose)
                piece_out = dict(res_, model=prec['id'], kind=fam_, room=room['name'])
                report.append({'room': room['name'], 'purpose': purpose, 'placed': res_['placed']})
                break
            if fam_ == 'planter':
                p_ = plant_in(prec, prec['p'][0], prec['p'][1], prec['p'][5])
                got_ = [p_['id']] if p_ else []
            elif fam_ == 'fire':
                got_ = dress_hearth(prec, purpose) + ([o['id'] for o in (dress(prec, purpose, min_z=60) or [])]
                                                      if re.search(r'fireplace|hearth', prec['id'].lower()) else [])   # (the tools at its foot, and a fireplace's mantelpiece)
            elif fam_ == 'shrine':
                import shrinesurvey
                got_ = dress_shrine(prec, shrinesurvey.composition(db, prec['id'], rng))
            elif books:
                # ("Fill with books": the model's dressings that are mostly books, whatever the room)
                got_ = [o['id'] for o in (dress(prec, purpose, fill_books=True) or [])]
            else:
                # (a table or a desk dressed again draws a whole scene as often as the game's tables of the
                # kind carry one: the scribe's desk, the alchemist's bench; else the model's everyday dressing)
                sk_ = scene_for_table(prec, False)
                n0_ = len(placed)
                if sk_ and lay_scene(sk_, on_rec=prec):
                    got_ = [p['id'] for p in placed[n0_:]]
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
        # the Redoran hall's planter island first: it takes the hall's middle before the set pieces do
        island_laid = 0
        if redoran and not walls_only and purpose in ('entry', 'hall', 'living', 'landing', 'dining', 'tavern'):
            island_laid = lay_island()
            if island_laid:
                pre['planter'] += 1
        if ARRANGE and not walls_only:
            # (a trade's own set piece, a smith's forge or an apothecary's bench, goes in the first room
            # that could hold it: not a bedroom, a store or a corridor)
            want = tuple(extras_left) if purpose in ('living', 'shop', 'study', 'kitchen', 'tavern', 'shrine') else ()
            # (a smith's forge goes in his shop or his living room, never his study or a shrine: two grindstones
            # stood among the user's shrine's flowers, 2026-10-23; a smithy lays its own, lay_forge_set)
            if TRADES:
                want = tuple(w for w in want if w != 'forge' or (purpose in ('living', 'shop', 'kitchen') and trade != 'smith'))
            picks = arrangesurvey.pick(db, purpose, theme, rng, room['tiles'], want=want, like=like_scenes)
            if purpose == 'mess':
                # (a mess is one long bench table by its own rule, not the game's small table sets)
                picks = [ex for ex in picks if ex['anchor']['fam'] != 'table']
            if trade == 'smith':
                picks = [ex for ex in picks if ex['anchor']['fam'] != 'forge']

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
        ess = ESSENTIAL.get(trade_p or purpose)
        if not ess or any(m['fam'] == ess for ex in picks for m in ex['members']):
            lay_pending()
        # (floor clutter goes in groups after the furniture, the way the game stands it, once surveyed;
        # before that, in groups of the game's usual sizes, so a storeroom isn't limited to one piece a
        # wall tile: the game packs 38 pieces into nine tiles of store)
        cs = roomrules.clusters(db) or DEFAULT_CLUSTERS
        clutter = []
        if walls_only:
            recipe_rows = []
        elif trade_p:
            recipe_rows = list(RECIPES[trade_p])     # (the trade's own anchor set: tradesurvey's figures, by hand)
        elif purpose in roomrules.KIND_PURPOSES:
            recipe_rows = roomrules.kind_recipe(db, purpose, RECIPES[purpose], culture=STYLE_SET.get(cell_style) or fam.get('_borrowed'),
                                                tiles=room['tiles'], style=style)
        else:
            recipe_rows = roomrules.recipe(db, purpose, RECIPES[purpose], theme=theme, like=like_rooms)
        if HALL_ROUND and purpose in HALL_PURPOSES and not sketch:
            recipe_rows = []          # (a hall's floor is the hallway round's, after the room's set pieces: hall_round)
        if built_hearths and not walls_only and purpose in ('kitchen', 'dining', 'living', 'tavern', 'mess'):
            bh_ = built_hearths[0]
            got.extend(dress_hearth(bh_, purpose))     # (the built-in hearth's own dressing: the game's logs and tools by that model)
            if not kits.kit_prefix(bh_['id']) and bh_.get('k'):
                # (a free-standing 'in_' fireplace, the Common kitchens' grand fireplace: the fire goes INTO it,
                # as the game's own have it: the log pile light, the logs, the pot, and the mantel's things,
                # from the game's dressings of that very model; the user's "fire should be in the fireplace")
                d_ = dress(bh_, purpose)
                got.extend(o['id'] for o in (d_ or []))
            last_trace.append((room['name'], 'fire', bh_['id'], 'the builder\'s hearth: the room\'s own'))
            lay_work_table(bh_)
        for kind, count, where in recipe_rows:
            if kind == 'fire' and built_hearths:
                continue                                           # (the room has its hearth in the building)
            if kind == 'fire' and not rough and not sketch:
                # (a house's hearth comes whole, from the game's own sets, or not at all: hearthsurvey)
                h_ = lay_hearth_set(purpose)
                if h_:
                    lay_work_table(h_)
                if h_ is not None:
                    continue
            if kind == 'planter':
                continue                                           # (planting is one path, plant_room, after the furniture)
            if kind == 'forge':
                if not sketch:
                    lay_forge_set()                                # (the smithy's forge with its anvil and bellows, whole or not at all)
                continue
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
                if not sketch:
                    groups += place_clutter(clutter, cs)
                clutter = []
            left = n
            while left > 0:
                left -= 1
                if kind == 'rug':
                    pool_ = big_rugs if where not in ('by_bed', 'rug') else all_rugs
                    if rug_rich_p is not None:
                        # (a rich house's rug is of the rich tier, the patterned one, at the game's rate for its
                        # band, one in four in its rich homes, a poor house's of the poor tier the same way; the
                        # rug is chosen by fit, so the tier is chosen first and the pool cut to it)
                        tier_w, p_w = rug_rich_p
                        of_ = [r for r in pool_ if rug_tier.get(r[0]) == tier_w]
                        rest_ = [r for r in pool_ if rug_tier.get(r[0]) != tier_w]
                        if of_ and rest_:
                            pool_ = of_ if rng.random() < p_w else rest_
                    got_rug = place_rug(where, pool_)
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
                if SCENES and kind in SCENE_KINDS and where in ('wall', 'corner', 'centre') and purpose != 'dining' \
                        and not (purpose == 'barracks' and kind == 'bed'):
                    # (a dining room is laid by its own rule, R2, not by the game's small sets; a barracks'
                    # bunks go in a row out from one wall, by their own rule below)
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
                # (at the style's own rate, whatever it is: a Gold Coast shelf in six, a Hlaalu one in
                # twenty-two; none where the style's places stand none)
                dv = catalogue.rule(db, 'dividers', cell_style) if kind == 'shelf' and where in ('wall', 'corner') else None
                if dv and dv.get('own') and (dv.get('share') or 0) >= 0.03 and rng.random() < dv['share']:
                    done, face = divider_spot(b, front)
                    if done:
                        where = 'divider'
                if where == 'by_bed':
                    # across the foot of the bed, its front away from the bed (the game: chests by beds
                    # stand across the bed's line 441 times to 167 along it, and face away 322 to 147; the
                    # user: "a large chest at 90 degrees facing outwards, if any chest is used at all"), a
                    # big one when the palette has one; failing that, by a wall like anything else. In a
                    # barracks each bunk gets its own chest (84% of the game's bunks have one): the first
                    # bunk without one, not the last bunk laid every time
                    beds = [f for f in fronts if f.get('kind') == 'bed']
                    if kind == 'chest':
                        free_ = [f for f in beds if not f.get('chested')]
                        if purpose == 'barracks' and free_:
                            beds = beds[:beds.index(free_[0]) + 1]
                        elif free_:
                            beds = beds[:beds.index(free_[-1]) + 1]
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
                                if kind == 'chest':
                                    beds[-1]['chested'] = True
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
                        bar_front[0] = run_['front']        # (a tavern's stools may stand in this strip)
                    if run_ or purpose != 'kitchen':
                        continue
                if purpose == 'bedroom' and kind == 'table' and not tables and any(f.get('kind') == 'bed' for f in fronts):
                    # the bedside table (the catalogue's R4: a small table with a candle at the bedhead;
                    # Gormash's and Goldstone's servants' rooms keep a 68-wide table touching the bed's
                    # head end): the palette's smallest table, beside the bed at its wall end, when it fits
                    small_ = []
                    for tid_ in (fam.get('table') or [])[:16]:
                        tb_ = mapdata.object_bounds(db, db.resolve_id(tid_))
                        if tb_ and max(tb_[3] - tb_[0], tb_[4] - tb_[1]) <= 110:
                            small_.append((max(tb_[3] - tb_[0], tb_[4] - tb_[1]), tid_, tb_))
                    bed_f = [f for f in fronts if f.get('kind') == 'bed'][-1]
                    if small_:
                        small_.sort()
                        _l, tid_, tb_ = small_[0]
                        fb_ = bed_f['box']
                        inx_, iny_ = bed_f.get('in') or (0, -1)
                        trot_ = 0.0
                        tbox0 = _footprint(tb_, trot_, 0, 0)
                        tw_, th_ = tbox0[2] - tbox0[0], tbox0[3] - tbox0[1]
                        # (the head end is at the wall: the end the bed's inward direction points away from)
                        if inx_:
                            hx_ = fb_[0] if inx_ > 0 else fb_[2]
                            tx_ = hx_ + inx_ * (tw_ / 2 + 4)
                            spots_ = [(tx_, fb_[3] + th_ / 2 + 6), (tx_, fb_[1] - th_ / 2 - 6)]
                        else:
                            hy_ = fb_[1] if iny_ > 0 else fb_[3]
                            ty_ = hy_ + iny_ * (th_ / 2 + 4)
                            spots_ = [(fb_[2] + tw_ / 2 + 6, ty_), (fb_[0] - tw_ / 2 - 6, ty_)]
                        rng.shuffle(spots_)
                        for sx_, sy_ in spots_:
                            bx_ = _footprint(tb_, trot_, sx_, sy_)
                            if fits(bx_):
                                rid, ri, b, front = tid_, db.resolve_id(tid_), tb_, front_of(db, tid_)
                                done = (sx_, sy_, trot_, bx_)
                                face = None
                                where = 'bedside'          # (laid: the wall and centre branches below leave it)
                                last_trace.append((room['name'], 'table', tid_, 'the bedside table at the bed\'s head'))
                                break
                if purpose == 'study' and kind == 'table' and not tables and where in ('centre', 'wall', 'corner'):
                    # (the catalogue's R5: the desk in the corner under the window, with its chair and a
                    # small rug, the wall shelf of scrolls above it; a corner slot first, a wall's else)
                    where = 'corner'
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
                    if purpose == 'mess':
                        # (one long table per three tiles, the game's 3 per nine: a nine-tile mess hall's
                        # table is three of the palette's long tables end to end)
                        n_seg = max(1, min(4, int(round(room['tiles'] * (T / 256.0) ** 2 / 3.0))))
                    hearths_ = [p for p in placed if p.get('room') == room['name'] and (roomsurvey.family_of(db, p['id'], p['type']) == 'fire' or bearer(p['id']))] + built_hearths
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
                    while laid_ is None and n_seg > 1:
                        # (one segment fewer, down to one, when the whole does not fit)
                        n_seg -= 1
                        for mx_, my_ in centres:
                            segs_ = []
                            for i_ in range(n_seg):
                                off = (i_ - (n_seg - 1) / 2.0) * seg
                                sx_, sy_ = (mx_ + off, my_) if long_x else (mx_, my_ + off)
                                segs_.append((sx_, sy_, _footprint(b, rot, sx_, sy_)))
                            if all(fits(bx_) for _x, _y, bx_ in segs_):
                                laid_ = segs_
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
                if where == 'both_sides' and kind in ('chair', 'bench'):
                    # chairs down both long sides of the long table (R2: "chairs down both sides"), evenly
                    # spaced, each facing the table, each with its approach clear; a mess's benches the same
                    # way, one to a side of each segment (the game's mess: table+bench*2, room-kind survey R5)
                    LB = long_box[0] or (tables[-1]['box'] if tables else None)
                    if not LB:
                        continue
                    lx_ = (LB[2] - LB[0]) >= (LB[3] - LB[1])
                    length_ = (LB[2] - LB[0]) if lx_ else (LB[3] - LB[1])
                    per_side = max(1, int(length_ // 80)) if kind == 'chair' else max(1, int(length_ // (max(b[3] - b[0], b[4] - b[1]) + 24)))
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
                    last_trace.append((room['name'], kind, rid, '%d %ss down both sides' % (n_chairs, kind)))
                    left = 0
                    continue
                if where in ('wall', 'corner'):
                    # (the practice dummies in a row at one wall, Goldstone's armoury: catalogue R11; each
                    # after the first takes the free slot nearest the last, the next tile along that wall.
                    # A barracks' bunks the same: in a row out from one wall, a tile apart, parallel, the
                    # game's 256 to 300 between them, room-kind survey R5)
                    in_row = kind == 'target' or (purpose == 'barracks' and kind == 'bed')
                    near_t = row_last[0] if in_row and row_last[0] is not None else None
                    # (a basket under a window, as often as the game's stand there: wallsurvey2 v3; the
                    # planters come by the planting path, plant_room, not the recipe)
                    win_ = window_for(kind) if kind == 'basket' and not near_t else None
                    done, face = wall_spot(b, front, 'wall' if (near_t or win_) else where, pp=pp, kind=kind, gap=KEEPER_GAP if kind == 'counter' else 2,
                                           near=near_t or (win_[0] if win_ else None), side=(row_last[1] if near_t else (win_[1] if win_ else None)),
                                           align=(win_[0] if (win_ and win_[1]) else None))
                    if done and win_:
                        last_trace.append((room['name'], kind, rid, 'under the window'))
                    if done and in_row:
                        row_last[0] = (done[0], done[1])
                        if row_last[1] is None and face:
                            row_last[1] = {(0, 1): 'S', (0, -1): 'N', (1, 0): 'W', (-1, 0): 'E'}.get(tuple(face))   # (the wall it stands at: face points into the room)
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
                    # (every table in turn, from the one this seat's number points at: a tavern's seven
                    # chairs all tried the one table the counter's strip had hemmed in, and none sat)
                    i0_ = len(got) % len(tables)
                    order_t = tables[i0_:] + tables[:i0_]
                    is_stool = bool(re.search(r'stool', rid.lower()))
                    for t in order_t:
                        if t.get('counter') and not (purpose == 'tavern' and is_stool):
                            continue             # (a chair at a counter: only a tavern's bar stools, R9)
                        tb = t['box']
                        sides = [((tb[0] + tb[2]) / 2, tb[3] + 30, (0, -1)), ((tb[0] + tb[2]) / 2, tb[1] - 30, (0, 1)),
                                 (tb[2] + 30, (tb[1] + tb[3]) / 2, (-1, 0)), (tb[0] - 30, (tb[1] + tb[3]) / 2, (1, 0))]
                        if t.get('counter') and t.get('open'):
                            # (the bar's customer side only, spread along the segment: the stools in a row)
                            ox_, oy_ = t['open']
                            spread_ = rng.uniform(-0.3, 0.3)
                            sides = [((tb[0] + tb[2]) / 2 + (tb[2] - tb[0]) * spread_ * (1 if oy_ else 0), (tb[1] + tb[3]) / 2 + (tb[3] - tb[1]) * spread_ * (1 if ox_ else 0), (-ox_, -oy_))]
                            sides = [(sx_ + ox_ * ((tb[2] - tb[0]) / 2 + 30 if ox_ else 0), sy_ + oy_ * ((tb[3] - tb[1]) / 2 + 30 if oy_ else 0), f_) for sx_, sy_, f_ in sides]
                        else:
                            rng.shuffle(sides)
                        for x, y, face in sides:
                            rot = _turn_to_face(front, face)
                            box = _footprint(b, rot, x + (-face[0]) * 10, y + (-face[1]) * 10)
                            ok_ = fits(box) if not t.get('counter') else (inside(box) and not any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4 and o is not bar_front[0]))
                            if ok_ and keep_approach(box, rot, front):
                                done = (x + (-face[0]) * 10, y + (-face[1]) * 10, rot, box)
                                break
                        if done:
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
                if kind == 'table' and where != 'bedside' and done[3] is not None and any(_overlaps(done[3], f['box'], -100) for f in fronts if f.get('kind') == 'bed'):
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
                if kind == 'screen' and done is not None and beds_in_room():
                    # (a screen is for blocking a view: it stands beside the bed on the room's side, turned
                    # across the line from the bed to the room, as the user turned theirs; never flat
                    # against a wall where it hides nothing)
                    sp_ = screen_spot(b)
                    if sp_ is None:
                        last_trace.append((room['name'], kind, rid, 'no clear spot beside the bed to screen it: left out'))
                        continue
                    done, face = sp_
                if kind in ('bookshelf', 'cupboard', 'shelf', 'counter') and face and not hang and done[3] is not None:
                    # (and the pace before it is free of what stands already: a chest across a dresser's
                    # doors, the user's "chest blocking dresser")
                    fx_, fy_ = face
                    bx_ = done[3]
                    front_box = (min(bx_[0], bx_[0] + fx_ * 56), min(bx_[1], bx_[1] + fy_ * 56), max(bx_[2], bx_[2] + fx_ * 56), max(bx_[3], bx_[3] + fy_ * 56))
                    if any(_overlaps(front_box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4 and not o[3]):
                        last_trace.append((room['name'], kind, rid, 'something stands before it: left out'))
                        continue
                rec = put(rid, done[0], done[1], done[2], on_top=(where == 'on_table'),
                          hang_from=(fl + hang) if hang > 0 else None, floor=fl, room=room['name'],
                          ledge=ledge_h if where in ('wall', 'corner', 'divider') and kind in catalogue.LEDGE_KINDS else None)
                if rec is None:
                    last_trace.append((room['name'], kind, rid, 'put refused it (no floor there, or over the band\'s cap)'))
                    continue
                if done[3] is not None:
                    taken.append((done[3], fl, fl + 200, False))
                    if kind in ('bookshelf', 'cupboard', 'shelf', 'counter') and face and not hang:
                        # (the floor before a shelf or a cupboard stays clear of furniture and crates, a
                        # pace deep, so it can be reached; a rug may still lie there. The user's "crates
                        # blocking bookshelf".)
                        fx_, fy_ = face
                        bx_ = done[3]
                        reach_ = 56
                        front_box = (min(bx_[0], bx_[0] + fx_ * reach_), min(bx_[1], bx_[1] + fy_ * reach_),
                                     max(bx_[2], bx_[2] + fx_ * reach_), max(bx_[3], bx_[3] + fy_ * reach_))
                        taken.append((front_box, fl, fl + 200, True))
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
                # what stands on it, the way the game sets out this very model (books packed along a
                # bookshelf, dishes and a candle on a table, wares on a counter)
                laid = dress(rec, purpose) if kind in DRESSED_KINDS else None
                if kind == 'fire':
                    got.extend(dress_hearth(rec, purpose))      # (the pot on the fire, the firewood by it)
                    if re.search(r'fireplace|hearth', rid.lower()):
                        got.extend(o['id'] for o in (dress(rec, purpose, min_z=60) or []))   # (and the mantelpiece: a fireplace's, not a stove's or a pit's)
                    if 'redoran_hearth' in rid.lower():
                        hearth_stores(rec)                       # (the sacks and urns by the kiln hearth: the catalogue's 203)
                if kind == 'shrine':
                    got.extend(dress_shrine(rec, shrine_comp))  # (the statue on the altar, the candles, the offerings)
                if kind in ('table', 'counter'):
                    tables.append({'box': done[3], 'items': [], 'dressed': bool(laid), 'counter': kind == 'counter'})
                    if purpose == 'study' and len(tables) == 1 and where in ('corner', 'wall') and face and fam.get('shelf'):
                        # the wall shelf of scrolls over the desk (R5: Narusya's, the Old Ebonheart guild's
                        # and the Firewatch study's desks): a hung shelf on the desk's wall, above its top,
                        # at the game's height for the model, dressed the game's way
                        for sid_ in (fam.get('shelf') or [])[:8]:
                            sb_ = mapdata.object_bounds(db, db.resolve_id(sid_))
                            if not sb_ or (sb_[5] - sb_[2]) >= 70:
                                continue              # (a shelf unit that stands on the floor is no wall shelf)
                            sh_ = shelf_hang(sid_, sb_)
                            if not sh_ or sh_ < b[5] + 6:
                                continue              # (hung under the desk's top, or no known height)
                            srot_ = _turn_to_face(front_of(db, sid_), face)
                            sbox0 = _footprint(sb_, srot_, 0, 0)
                            dbox0 = _footprint(b, done[2], 0, 0)
                            d_back = {(0, 1): -dbox0[1], (0, -1): dbox0[3], (1, 0): -dbox0[0], (-1, 0): dbox0[2]}[face]
                            s_back = {(0, 1): -sbox0[1], (0, -1): sbox0[3], (1, 0): -sbox0[0], (-1, 0): sbox0[2]}[face]
                            wx_, wy_ = done[0] - face[0] * (d_back + 2), done[1] - face[1] * (d_back + 2)      # (the wall's face behind the desk)
                            sx_, sy_ = wx_ + face[0] * (s_back + 1), wy_ + face[1] * (s_back + 1)
                            if not wall_behind(sb_, srot_, sx_, sy_, room, T, front_of(db, sid_), reach=24):
                                continue
                            srec_ = put(sid_, sx_, sy_, srot_, hang_from=fl + sh_, room=room['name'])
                            if srec_:
                                got.append(sid_)
                                hung_here.append((sx_, sy_))
                                dress(srec_, purpose)
                                last_trace.append((room['name'], 'shelf', sid_, 'the wall shelf over the desk'))
                                break
                if kind in ('bed', 'shrine', 'counter') and done[3] is not None and face:
                    fronts.append({'box': done[3], 'in': face, 'kind': kind})
        if picks:
            lay_pending()                        # (a recipe with nothing after the essential piece)
        # the room's planting (one path: the game's floor planters, beds, tabletop pots and hanging ones at its
        # rates and spots) and its scenes with their kit, at the game's rates for rooms of this kind
        if not walls_only and not sketch:
            plant_room(island_laid)
            lay_scenes()
        # what rides on the stores, the way the game tops them (room-kind survey R3): a small crate, a
        # sack, a bowl or a travel lantern on one crate in two, a sack on a sack one in four, the odd thing
        # on a barrel or a chest; and a kitchen's hearth gets its cookery and its logs (R4)
        if not walls_only:
            import roomkindsurvey
            RK = roomkindsurvey.ready(db)
            KK = (RK or {}).get('kinds', {}).get(roomrules.KIND_OF.get(purpose, 'storage'), {}).get('*') if RK else None
            # (in every kind of room: a living room's crate is topped as the game tops its stores' crates,
            # one in two; before, only a store's, a kitchen's and a hall's were, and a house's crates stood
            # bare nine times in ten)
            def top_stores():
                """What rides on the room's stores laid so far (each looked at once: the clutter groups of
                most rooms are laid after this pass runs the first time, so it runs again after them)."""
                tops_done = seen_n = 0
                for srec in [p for p in placed if p.get('room') == room['name'] and p.get('k') not in topped_keys
                             and roomsurvey.family_of(db, p['id'], p['type']) in ('crate', 'sack', 'barrel', 'chest')]:
                    topped_keys.add(srec.get('k'))
                    seen_n += 1
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
                        trec = put(tid, tx_, ty_, trot, on_top=True, at_z=top_ - tb[2], room=room['name'], on_ref=srec.get('k'))
                        if trec:
                            got.append(tid)
                            tops_done += 1
                        break
                if tops_done or seen_n:
                    last_trace.append((room['name'], 'tops', '-', '%d things on %d stores' % (tops_done, seen_n)))
            topped_keys = set()
            if KK and not sketch:
                top_stores()
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
                hearths_ = [p for p in placed if p.get('room') == room['name'] and (roomsurvey.family_of(db, p['id'], p['type']) == 'fire' or bearer(p['id']))] + built_hearths
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
                            if db.recs[db.resolve_id(cid)][0] in mapdata.ITEM_TYPES:
                                continue      # (a pan or a kettle stands on the hearth or not at all; a cauldron may stand beside it)
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
        hall_hang = 1.0
        if HALL_ROUND and purpose in HALL_PURPOSES and not walls_only and not sketch and slots:
            # the hallway round: one of the ways the game's halls of the culture are dressed (hallsurvey.py)
            hall_hang = hall_round({'db': db, 'room': room, 'T': T, 'rng': rng, 'fl': fl, 'purpose': purpose, 'cell_style': cell_style,
                                    'style': style, 'used': info.setdefault('_hall_used', []), 'slots': slots, 'placed': placed,
                                    'taken': taken, 'got': got, 'rugs': rugs, 'big_rugs': big_rugs, 'trace': last_trace, 'pick': pick,
                                    'put': put, 'fits_raw': lambda b_: fits(b_, clearings=False), 'openings': openings,
                                    'settle': settle, 'rug_at': rug_at, 'dress': dress,
                                    'stand_light': stand_light, 'ledge': ledge_h})
        if purpose == 'hall' and not walls_only and slots and not any(roomsurvey.family_of(db, r['id'], r['type']) in roomsurvey.FLOOR_KINDS + ('planter', 'basket')
                                                                   for r in placed if r.get('room') == room['name']):
            # (a hall whose bench found no wall clear of its doorways: something smaller against a wall,
            # so the hall is never bare floor and lamps: a planter, an urn, a crate, whichever fits)
            for kind in ('urn', 'basket', 'crate'):
                rid = pick(kind)
                b = mapdata.object_bounds(db, db.resolve_id(rid)) if rid else None
                if not b:
                    continue
                done, face = wall_spot(b, front_of(db, rid), 'corner', pp=placesurvey.prefs(db, kind, purpose), kind=kind)
                prec_ = put(rid, done[0], done[1], done[2], floor=fl, room=room['name'], ledge=ledge_h) if done else None
                if prec_:
                    taken.append((done[3], fl, fl + 200, False))
                    got.append(rid)
                    break
        if clutter and not sketch:
            rng.shuffle(clutter)
            # (mostly one kind to a group, as the game's are: like kinds together)
            if rng.random() > cs.get('mixed', 0.3):
                clutter.sort()
            groups += place_clutter(clutter, cs)
            if not walls_only and KK:
                top_stores()                      # (what rides on the groups just laid)
        if redoran and not walls_only:
            tile_rugs()                          # (the Redoran rooms' rugs tiling the floor, to the game's cover)
        if not walls_only and not sketch and purpose not in ('ruin', 'camp'):
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
                no_ceiling[0] = 0
                for _try in range(13):
                    if _try == 12:
                        # (no spot under a ceiling or a beam: an open hall, a two-storey void. The light
                        # stands on the floor instead, a lamp of the room's own palette at a wall)
                        if no_ceiling[0] >= 6:
                            stand_light()
                        break
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
            got += _decorate(db, room, purpose, T, decor, refs, placed, put, rng, hung, hang_k=(L['hang'] if L else 1.0) * hall_hang)
            got += void_banners()
        if not walls_only and purpose == 'bath':
            # the game's bathing rooms have 5.5 lights per nine tiles, a standing lamp or a candle on
            # the shelf, never a ceiling light (room-kind survey R1): a lamp at a wall makes up the shortfall
            import roomkindsurvey as _rks
            RKb = (_rks.ready(db) or {}).get('kinds', {}).get('bath', {}).get('*') or {}
            want_l = (RKb.get('lights_per_9') or 5.5) * room['tiles'] * (T / 256.0) ** 2 / 9.0
            have_l = sum(1 for p in placed if p.get('room') == room['name'] and p['type'] == 'LIGH')
            n_more = int(round(want_l)) - have_l
            for _ in range(max(0, min(3, n_more))):
                if not stand_light():
                    break
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

                def stand_by_stair(x, y, st=st, rm=rm, fl=fl, sx=sx, sy=sy, standing=standing):
                    """A standing lamp at the side of the flight's end, out of the way of whoever comes
                    down it, clear of what stands there and on the room's floor as the walls bound it (the
                    user's lamps 20 to 33 units into a wall came from here). The record, or None."""
                    lid = standing[0]
                    lb = mapdata.object_bounds(db, db.resolve_id(lid))
                    if not lb:
                        return None
                    px, py = (x - sx, y - sy)
                    side = (-py / T * 70, px / T * 70)
                    box = _footprint(lb, 0, x + side[0], y + side[1])
                    rects_ = room_rects(rm, T)
                    if any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4) or not on_floor(box, rects_):
                        box = _footprint(lb, 0, x - side[0], y - side[1])
                        if any(_overlaps(box, o[0]) for o in taken if o[1] < fl + 150 and o[2] > fl + 4) or not on_floor(box, rects_):
                            return None
                        side = (-side[0], -side[1])
                    rec = put(lid, x + side[0], y + side[1], rng.uniform(0, 2 * math.pi), floor=fl, room=rm['name'])
                    if rec:
                        taken.append((box, fl, fl + 200, False))
                        lit_by.append(rec)
                    return rec
                for x, y in cands:
                    if not (rm['x_min'] + 40 <= x <= rm['x_max'] - 40 and rm['y_min'] + 40 <= y <= rm['y_max'] - 40):
                        continue
                    if use_standing:
                        if stand_by_stair(x, y):
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
                    # (the ceiling over the spot by the building's real geometry; a stair's head opens
                    # into the floor above, and a light hung there hung from nothing. With no ceiling,
                    # under a beam within reach, or a standing lamp at the flight's side instead)
                    ceil_ = ceiling_over(x, y, fl + 100)
                    if ceil_ is None:
                        bm_ = beam_near(x, y, fl)
                        if bm_ is None:
                            if standing and stand_by_stair(x, y):
                                break
                            continue
                        x, y, ceil_ = bm_
                    if z + hb[5] > ceil_ - 4:
                        z = ceil_ - (gap if gap is not None and gap < 160 else 8) - hb[5]
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
            return {'placed': len(placed), 'removed': 0, 'model': piece_out['model'], 'kind': piece_out.get('kind'), 'dressings_known': known,
                    'added': piece_out.get('added'), 'name': piece_out.get('name'), 'with': piece_out.get('with') or []}
        if not placed:
            if not known:
                raise EditError('The game never puts anything on this (%s), so there is nothing to copy.' % piece_out['model'])
            raise EditError('None of the game\'s %d dressings of this model fit here as it stands (too close to a wall, or things in the way).' % known)
        db.sync_project()
        import modelcache
        modelcache.save()
        placed_last[:] = placed
        if commit:
            db.sync_project()
            if not any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), [])):
                try:
                    import pathgrid
                    pathgrid.generate(db, cell_key, note=False)
                except EditError:
                    pass
            editing.commit(db, 'Dressed %s the game\'s way (%d things)' % (piece_out['model'], len(placed)))
        return {'placed': len(placed), 'removed': removed, 'model': piece_out['model'], 'kind': piece_out['kind'], 'dressings_known': known}
    if room_rec is not None:
        if not placed:
            raise EditError('Nothing of the game\'s fits in the %s as a %s (no spot clear of its doorways, or no such furniture in the load order).' % (room_rec['name'], plan[0]['purpose']))
        db.sync_project()
        # (the walking paths made again round the room's new furniture, in the same change, as after a whole
        # furnish: Test Home's were made at the build, room-by-room furnishing left 12% of its links through
        # furniture, 2026-10-24)
        if not any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), [])):
            try:
                import pathgrid
                pathgrid.generate(db, cell_key, note=False)
            except EditError:
                pass
        import modelcache
        modelcache.save()
        placed_last[:] = placed
        pur_ = next((r['purpose'] for r in report if r['room'] == room_rec['name']), plan[0]['purpose'])
        if commit:
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
