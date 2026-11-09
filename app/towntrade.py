"""What a town lives by, carried into the town itself (docs/worldbuilding-next-2026-11.md, livelihoods stage 2): the
trade a proposed town was given (placeplan.works), or one chosen on any town, leans its buildings, the households in
its houses, its townsfolk and the goods on its stalls and in its storage the way the game's towns of that trade lean.

The figures (lab 2026-11-08, townsurvey's 149 towns, each given its trade by its docks, boats and nets, farm pieces,
crops and beasts, mine doors and people, lab a14: 55 harbours, 39 farms, 29 mines, 26 trade alone):
- buildings (a16, 2,278 buildings): each kind's share in the trade's towns against all towns';
- households (a19, 913 people in the towns' houses): each trade's own people's share of them, by the town's trade;
- townsfolk (a18, 888 townsfolk in the towns' outdoor cells, no guards, sellers or service people): each trade's own
  people's share of them in the towns of each trade, the same leaning the people of a house;
- goods (a17, 548 stall, lone stall and storage scenes): storage with crops stands in 46% of a farm town's scenes, 29%
  elsewhere; with ore, carts and picks in mine and harbour towns. A scene carrying the trade's goods is picked
  GOODS_LEAN times as often.
"""
import re

TRADES = ('harbour', 'farm', 'mine', 'trade')
LABEL = {'harbour': 'the sea', 'farm': 'farming', 'mine': 'a mine', 'trade': 'trade'}

# (each special building's share against the game's towns' as a whole; kinds within 15% of 1 left as the culture has them)
KIND_LIFT = {'harbour': {'guard': 1.19, 'guild': 1.2},
             'farm': {'shop': 0.62, 'guard': 0.6, 'guild': 0.47, 'temple': 0.77},
             'mine': {'shop': 1.32, 'manor': 1.28, 'tavern': 1.38, 'guild': 1.56},
             'trade': {'shop': 1.33, 'tavern': 0.55, 'guard': 0.7}}

# (who each trade's own people are, by their counts in the game's towns of that trade)
OWN_CLASSES = {'harbour': [['t_glb_fisherman', 44], ['t_glb_sailor', 36], ['t_glb_dockworker', 9]],
               'farm': [['farmer', 37], ['herder', 21], ['hunter', 19]],
               'mine': [['t_glb_miner', 11], ['miner', 4]]}
OWN = {c: t for t, cs in OWN_CLASSES.items() for c, _n in cs}
# (each trade's own people's share of the townsfolk (no guards, sellers or service people) in the game's towns by what
# they live by, a18, 888 townsfolk: a fisher in a farm town is one in seventy, a miner outside a mine town hardly ever)
FOLK_SHARE = {'harbour': {'harbour': 0.193, 'farm': 0.069, 'mine': 0.002},
              'farm': {'harbour': 0.014, 'farm': 0.358, 'mine': 0.0},
              'mine': {'harbour': 0.009, 'farm': 0.07, 'mine': 0.132},
              'trade': {'harbour': 0.0, 'farm': 0.102, 'mine': 0.0}}
# (the same for the people of the game's houses, a19, 913 people in the towns' houses: fewer of a trade's own live in
# its houses than walk its streets, a harbour town's 8% against its streets' 19%)
HOUSE_SHARE = {'harbour': {'harbour': 0.077, 'farm': 0.03, 'mine': 0.005},
               'farm': {'harbour': 0.007, 'farm': 0.257, 'mine': 0.004},
               'mine': {'harbour': 0.0, 'farm': 0.047, 'mine': 0.039},
               'trade': {'harbour': 0.0, 'farm': 0.106, 'mine': 0.0}}

# (the yards behind a town's houses: how many of the game's houses have fishing things beside them (dried fish, oars,
# nets, hanging fish, rope) or farm things (hay, fences, troughs, crops), by the town's trade; j_yard, 945 houses. The
# rest of a town's yards are the culture's kitchens, gardens and workshops)
YARD_SHARE = {'harbour': {'fishing': 0.155, 'pen': 0.055},
              'farm': {'pen': 0.294, 'fishing': 0.034},
              'mine': {'pen': 0.041, 'fishing': 0.016},
              'trade': {'pen': 0.035, 'fishing': 0.035}}


def yard_kind(rng, trade, kinds):
    """A house's yard in a town of this trade: a fishing or a pen yard as often as the game's houses have one,
    else one of kinds (the plot's own) that isn't. None for a town of no trade (the plot's own mix)."""
    sh = YARD_SHARE.get(clean(trade))
    if not sh:
        return None
    r = rng.random()
    for k, p in sh.items():
        if r < p:
            return k
        r -= p
    rest = [k for k in kinds if k not in sh] or list(kinds)
    return rng.choice(rest)


GOODS = {'harbour': re.compile(r'fish|crab|scales|_eel|kelp|pearl|mussel|clam|setharbor|fishtrap|_net\b', re.I),
         'farm': re.compile(r'saltrice|ashyam|marshmerrow|wheat|cabbage|bread|apple|corn|potato|leek|onion|comberry|'
                            r'setfarm|haypile|haystack|crate_01_eggs|kwama_egg|cheese|_bale', re.I),
         'mine': re.compile(r'ingmine|_ore|raw_ebony|raw_glass|crate_01_ebony|ingot|metalpiece|miner|_pick\b|coals|'
                            r'guarcart|furn_cart|mine_cart|_minecart', re.I)}
GOODS_LEAN = 2.0                 # (a scene with the trade's goods picked this many times as often: storage with crops
                                 # stands 1.6 times as often in a farm town's scenes as elsewhere, the stalls too few to read)


def clean(t):
    return t if t in TRADES else ''


def kind_lift(trade):
    return KIND_LIFT.get(clean(trade), {})


def lean_pairs(pairs, trade, canon, table=None):
    """[[key, n]] leant to the town's trade: each trade's own people (OWN_CLASSES) given together the share of the
    townsfolk the game's towns of this trade give them (table: FOLK_SHARE, or HOUSE_SHARE for a house), the rest keeping theirs among themselves. The
    town's own trade's people are put in where the list has none of them. Keys are 'cls|...' (townlife) or bare classes
    (populate); canon(cls) is the class as the game spells it, or None where it can't be made. A town of no trade keeps
    its culture's mix."""
    trade = clean(trade)
    if not trade:
        return pairs
    want = (table or FOLK_SHARE)[trade]
    groups = {g: [] for g in OWN_CLASSES}
    rest = []
    for k, n in pairs:
        g = OWN.get(k.split('|')[0].lower())
        (groups[g] if g else rest).append([k, n])
    own = [[canon(c), n] for c, n in OWN_CLASSES.get(trade, ())]
    own = [[c, n] for c, n in own if c]
    if trade in groups and not groups[trade] and own:
        groups[trade] = own
    tot = float(sum(n for _k, n in pairs)) or 1.0
    kept = 1.0 - sum(want.get(g, 0) for g, ls in groups.items() if ls)
    rn = float(sum(n for _k, n in rest))
    out = [[k, n * tot * kept / rn] for k, n in rest] if rn else []
    for g, ls in groups.items():
        gn = float(sum(n for _k, n in ls))
        if gn and want.get(g, 0) > 0:
            out += [[k, n * tot * want[g] / gn] for k, n in ls]
    return out


def canon_of(classes):
    """canon() over a survey's classes ({name: ...} or names): the class as spelt there, or None."""
    m = {c.lower(): c for c in classes}
    return lambda c: m.get(c.lower())


def goods_weight(scene, trade):
    rx = GOODS.get(clean(trade))
    if rx is None:
        return 1.0
    return GOODS_LEAN if any(rx.search(t.get('id') or '') for t in scene.get('things') or ()) else 1.0
