"""The story layer of a made town's dressing: the ground between its houses given owners. Each house plot's back and
sides are its yard, fenced in the culture's own fence; the yard gets one kind of life (a kitchen yard, a garden, a
workshop yard, a pen) as a set of the Workshop's own, laid against the house's back; and round every house what the
game grows round its own, at the game's rates for the culture and with the region's own species (gardensurvey's
outdoor survey, 2026-11-04): a bed of flowers or herbs at the side wall, a tree by the house, a planter at the door or
along a wall with its garden in it, ivy on the walls of the cultures that grow it, a kitchen garden of the region's
crop in rows at the game's spacing. Farms and orchards for the land (farm, orchard, lay_field) stand on their own.

The survey dressing (towndress, townlife) lays what the game lays at the game's rates: scenes before doors, groups along
streets, stalls and storage. It never decides what a patch of ground is FOR, so the ground between houses read as a
lawn (the user, 2026-11-03: "fill the empty space in between homes and roads with more things, namely planters,
stalls, trees, more crates and boxes"; the brainstorm: "fences that divide the grass into yards, then one yard kind per
house"). Sets here are hand-written in a frame: x across the house's back (right-handed, facing the back fence),
y into the yard from the house's back wall, z over the ground. Things that would stand in something are left out.
Nothing grows in a walking line: the doors' ways and the arrival spots in front of them, the streets, the plots.
"""
import math
import os
import random
import re

import mapdata

# the culture's fence: straights by length (longest first) and a post for the ends; the long axis is the piece's x
FENCES = {
    'Imperial': {'runs': [('t_imp_set_fence_03', 264), ('t_imp_set_fence_01', 134)], 'post': 't_imp_set_fence_02'},
    'Common': {'runs': [('t_imp_set_fence_03', 264), ('t_imp_set_fence_01', 134)], 'post': 't_imp_set_fence_02'},
    'Gold Coast': {'runs': [('t_imp_set_fence_03', 264), ('t_imp_set_fence_01', 134)], 'post': 't_imp_set_fence_02'},
    'Nord': {'runs': [('t_nor_setfarm_x_fencelent_01', 380), ('t_nor_setfarm_x_fencelent_02', 380)], 'post': 't_nor_setfarm_x_fencepost_01'},
    'Breton': {'runs': [('t_bre_setfarm_x_fencelent_01', 380), ('t_bre_setfarm_x_fencelent_02', 380)], 'post': 't_bre_setfarm_x_fencepost_01'},
    'Redguard': {'runs': [('t_rga_setrihad_x_fencestr_01', 390)], 'post': 't_rga_setrihad_x_fencepost_01'},
    'Orc': {'runs': [('t_orc_setnomad_x_fence_01', 288), ('t_orc_setnomad_x_fence_02', 295)], 'post': None},
    'Hlaalu': {'runs': [('t_de_set_x_woodfence_01', 257), ('t_de_set_x_woodfence_01_128', 128)], 'post': None},
    'Velothi': {'runs': [('t_de_set_x_woodfence_01', 257), ('t_de_set_x_woodfence_01_128', 128)], 'post': None},
    'Redoran': {'runs': [('t_de_set_x_woodfence_02', 257), ('t_de_set_x_woodfence_02_128', 128)], 'post': None},
    'Dunmer common': {'runs': [('t_de_set_x_woodfence_01', 257), ('t_de_set_x_woodfence_01_128', 128)], 'post': None},
    # (Anvil's yard wall, docs/cyrodiil-study-2026-11.md: rough stone lengths under a flat cap, end to end, a capped post
    # at every joint, 512 to 544 apart; its origin 88 to 112 over the ground, the foot 16 to 40 in it)
    'Anvil': {'runs': [('t_imp_setanv_x_propertywall_04', 512), ('t_imp_setanv_x_propertywall_02', 256), ('t_imp_setanv_x_propertywall_03', 128)],
              'post': 't_imp_setanv_x_propertywpill_01', 'lift': 100.0, 'gap': 32.0, 'posts': 'each'},
    # (the rough stone wall with a crest of upright stones, Archad's and Anvil's: 256 lengths, 115 to 165 in the ground)
    'Gold Coast poor': {'runs': [('t_imp_setanv_x_stonewall_04', 256)], 'post': 't_imp_setanv_x_stonewall_05', 'lift': 24.0, 'gap': 0.0},
}
# (the town survey's culture names that have no fence of their own borrow a kin's: a Nordic town got no fences at all
# before, its key being 'Nordic' and the fence's 'Nord')
FENCE_KIN = {'Anvil': 'Imperial', 'Imperial Legion': 'Imperial', 'Indoril': 'Velothi', 'Mournhold': 'Velothi', 'Nordic': 'Nord', 'Reach': 'Nord',
             'Dunmer': 'Dunmer common', 'Stronghold': 'Dunmer common', 'Telvanni': 'Dunmer common'}
# the game's farm fences (t_imp_setfarm, t_nor_setfarm, the Common towns' furn_com_fence), for farms and kitchen gardens
FARM_FENCES = {
    'Imperial': {'runs': [('t_imp_setfarm_fencestrt_01', 390)], 'post': 't_imp_setfarm_fencepost_01'},
    'Gold Coast': {'runs': [('t_imp_setfarm_fencestrt_01', 390)], 'post': 't_imp_setfarm_fencepost_01'},
    'Anvil': FENCES['Anvil'],              # (a garden in Anvil is walled: the Garden Quarter's)
    'Common': {'runs': [('furn_com_fence_02', 264)], 'post': 'furn_com_fence_01'},
    'Nord': {'runs': [('t_nor_setfarm_x_fencelent_01', 380), ('t_nor_setfarm_x_fencelent_02', 380)], 'post': 't_nor_setfarm_x_fencepost_01'},
}
FENCE_IN = 24                  # a fence stands this far inside the plot's edge (two plots' fences never meet)
FENCE_GAP = 6                  # (and pieces this far apart along the run)
FENCE_SHARE = 0.8              # (a run is laid when this share of its pieces fit, else none of it: no stray stakes)
YARD_D = 440                   # a yard reaches this far behind the house's back wall (the plot cut for a house is
                               # smaller than the house, so the plot's own back is no guide)
YARD_MIN = 320                 # a yard with less than this behind the house gets no set, only its fence
THING = 44                     # a set thing's own room on the ground (half a side)
ARRIVE = (112, 330)            # the way out of a door kept clear of everything that grows: half-width and depth (the
                               # arrival spot stands 110 to 300 out of the door, doors.outside_spot)
PLANTERS = ['furn_planter_01', 'furn_planter_02', 'furn_planter_03', 'furn_com_planter']   # (the fallback, unsurveyed)
TREE_TRUNK = 60                # a tree's own room on the ground (its trunk; the game's canopies overhang walls and roofs)
TREE_MIN_D = 100               # a tree's trunk never nearer a wall than this (and never nearer than 0.3 of its crown)

# the game's figures baked in for a load order the outdoor survey has not read yet (its own figures, 2026-11-04:
# 149 towns, 8364 outdoor cells; see gardensurvey.outdoor). Percentile sketches are [10th, 25th, 50th, 75th, 90th].
GAME = {
    'beds': {'plants': [2, 2, 3, 4, 6], 'nn': [41, 56, 84, 125, 152], 'wall': [12, 62, 193, 365, 475], 'side': {'side': 0.62, 'front': 0.24, 'back': 0.14}, 'one_kind': 0.6},
    'house_trees': {'d': [25, 84, 178, 274, 339], 'side': {'side': 0.61, 'back': 0.22, 'front': 0.16}},
    'planters': {'by_door': 0.10, 'lx': [122, 174, 238, 283, 293], 'ly': [-197, -121, -77, -38, -31], 'planted': 0.9, 'stand': {'ground': 0.56, 'step': 0.09, 'high': 0.35}},
    'vines': {'bottom': [69, 124, 215, 336, 412], 'side': {'side': 0.56, 'front': 0.39, 'back': 0.05}},
    'farms': {'row_gap': [92, 114, 136, 167, 214], 'in_gap': [36, 68, 128, 208, 235], 'rows': [1, 2, 2, 3, 4], 'per_row': [2.5, 2.8, 3.5, 6, 11], 'align': [0.16, 0.24, 0.43, 0.65, 0.78],
              'plants': [5, 6, 8, 11, 16], 'fenced': 0.14},
    'orchards': {'nn': [47, 85, 140, 217, 379], 'cv': [0.06, 0.15, 0.49, 0.81, 1.02], 'trees': [3, 3, 4, 5, 6]},
    'rate': {'beds': 0.55, 'house_trees': 0.3, 'planters': 0.2, 'vines': 0.25},
}
# a garden's rows: the culture's own crops when the survey has none for the region (the region's come first)
CROPS = {'Dunmer': ['flora_saltrice', 'flora_marshmerrow', 'flora_corkbulb', 'flora_ash_yam'],
         'Imperial': ['t_cyr_flora_spikerice', 't_cyr_flora_wheat', 'flora_wickwheat'],
         'Nord': ['t_sky_flora_withwheat', 't_glb_flora_cabbage', 'flora_wickwheat'],
         'Breton': ['flora_wickwheat', 't_glb_flora_cabbage'],
         'Redguard': ['flora_wickwheat', 'flora_ash_yam']}
# what the survey reads as a crop in a field and nobody farms: both of the game's drumpear "farms" stand by no
# building, unfenced, one on a 40-degree slope (wild clumps that happen to stand in a row), and the region grows
# seven more such clumps that are no farm by any count. A farm drawn on Shipal-Shin ground was 151 of them, which the
# user could not tell from the wild land (2026-11-13)
NOT_FARMED = re.compile(r'drumpear')
# a field beside one of the mod's own towns is that town's: within this of its outline
FIELD_TOWN = 8192.0
# the yard kinds: [(id, x, y, dz, rz)] in the yard frame, y from the house's back wall; alternatives by id prefix are
# tried in order and the first the load order has is used
KINDS = {
    'kitchen': [('barrel_01', -150, 60, 0, 0.0), ('barrel_02', -95, 60, 0, 0.4), ('com_sack_01', 40, 50, 0, 1.1), ('com_sack_02', 80, 55, 0, 2.0),
                ('com_basket_01', 130, 70, 0, 0.3), ('misc_com_bucket_01', 170, 60, 0, 0.0), ('t_com_var_cagechicken_01', -40, 170, 0, 1.6),
                ('crate_01', 150, 200, 0, 0.2)],
    'garden': [('com_basket_02', -170, 60, 0, 0.0), ('misc_com_bucket_01', 160, 50, 0, 0.0)],
    'workshop': [('crate_01', -140, 70, 0, 0.0), ('crate_02', -140, 70, 64, 0.5), ('crate_01', -70, 70, 0, 0.1), ('barrel_01', 60, 60, 0, 0.0),
                 ('barrel_01', 120, 60, 0, 0.9), ('t_com_furn_wheelbarrow_01', 10, 210, 0, 1.3), ('com_sack_02', 180, 70, 0, 0.0)],
    'pen': [('t_com_setfarm_haybale_01', -120, 200, 0, 0.3), ('t_com_setfarm_haybale_01', -40, 220, 0, 1.2), ('t_imp_setfarm_foodtrough_01', 100, 120, 0, 1.571),
            ('t_com_setfarm_haypile_01', 150, 260, 0, 0.0)],
}
# (a fishing household's yard: a net on its drying frame, fish hung to dry, a coil of rope, an oar, a barrel; the game's
# own harbour pieces, those the load order has. towntrade.YARD_SHARE says how often)
FISHING = [(('t_imp_setharbor_fishnet_02', 't_nor_setharbor_fishnet_01'), -40, 100, 0, 0.0),
           (('t_com_setharbor_fishhanging_01',), 135, 70, 0, 0.0), (('t_com_setharbor_fishhanging_01',), 170, 100, 0, 0.6),
           (('t_com_setharbor_rope_01',), 125, 170, 0, 0.8), (('ex_de_oar',), -150, 180, 0, 1.4), (('barrel_01',), 185, 175, 0, 0.3)]


def _fishing_set(db):
    out = []
    for ids, x, y, z, rz in FISHING:
        rid = _first(db, *ids)
        if rid:
            out.append((rid, x, y, z, rz))
    # (a yard with no net and no hanging fish is no fisher's: the oar and the barrel alone are anyone's)
    return out if any(re_fish.search(t[0]) for t in out) else []


re_fish = re.compile(r'fishnet|fishhanging', re.I)
KIND_BY = {'house': ['kitchen', 'garden', 'kitchen', 'pen'], 'manor': ['garden', 'kitchen'], 'shop': ['workshop', 'kitchen'],
           'tavern': ['kitchen', 'workshop'], 'farm': ['pen', 'garden'], 'shack': ['kitchen', 'garden']}
LAST = {}                      # (the last town's figures, for the checks)
WHY = {}                       # (why scenes were left out in the last town, for the lab)
_VAR = {}                      # (every growing thing's ids by kind-name, per load order)


def _unit(x, y):
    h = math.hypot(x, y) or 1.0
    return x / h, y / h


def _rect(cx, cy, dx, dy, half_x, half_y):
    """The corners of a box half_x along (dx, dy) and half_y across it, at (cx, cy)."""
    nx, ny = -dy, dx
    return [(cx + dx * sx * half_x + nx * sy * half_y, cy + dy * sx * half_x + ny * sy * half_y) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _footprint(bb, x, y, rz, s=1.0, pad=0.0):
    """A thing's footprint on the ground as the game turns it (clockwise about its origin): the bounds' corners in the
    world, pad units wider. A set thing's room was a square about its ORIGIN before, and a thing whose mesh stands
    off its origin (a chicken cage, a wheelbarrow) overlapped the house behind it: an eighth of a town's yard things
    stood into a plot, the lab's 191 plots of 2026-11-04."""
    c, sn = math.cos(rz), math.sin(rz)
    out = []
    for lx, ly in ((bb[0] - pad, bb[1] - pad), (bb[3] + pad, bb[1] - pad), (bb[3] + pad, bb[4] + pad), (bb[0] - pad, bb[4] + pad)):
        out.append((x + (lx * c + ly * sn) * s, y + (-lx * sn + ly * c) * s))
    return out


def _inside(poly, x, y):
    c = False
    n = len(poly)
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax:
            c = not c
    return c


def _overlap(a, b):
    import townplan
    return townplan._overlap(a, b)


class _Space:
    def __init__(self, polys, strict=()):
        self.polys = [list(p) for p in polys]
        self.strict = [list(p) for p in strict]      # (kept clear of what grows: the streets' whole width)

    def free(self, pts, grows=False):
        if grows and any(_overlap(pts, p) for p in self.strict):
            return False
        return not any(_overlap(pts, p) for p in self.polys)

    def take(self, pts):
        self.polys.append(pts)


def _bounds(db, memo, rid):
    low = rid.lower()
    if low not in memo:
        ri = db.resolve_id(rid)
        memo[low] = mapdata.object_bounds(db, ri) if ri is not None else None
    return memo[low]


def _first(db, *ids):
    for i in ids:
        if i and db.resolve_id(i) is not None:
            return i
    return None


FOOT_TALL = 220.0               # (a static this tall at most, its origin a FOOT_SHARE of its height or more over its
FOOT_SHARE = 0.3                # lowest point, is a loose thing with its origin in its middle: a hay bale, a grindstone)
NOT_LOOSE = re.compile(r'flora|plant|tree|bush|grass|rock|fence|post|pole|sign|planter', re.I)


def _on_its_foot(db, rid, b):
    """A thing that stands on its own lowest point, whatever lies under its origin: a container or an item (a crate, a
    barrel, a basket, a bucket: their origins are in their middles), or a small static made the same way. Not what
    the game sets into the ground on purpose: plants, rocks, fences and posts."""
    if not rid or not b or b[2] >= 0 or NOT_LOOSE.search(rid):
        return False
    ri = db.resolve_id(rid)
    t = db.recs[ri][0] if ri is not None else None
    if t == 'CONT' or t in mapdata.ITEM_TYPES:
        return True
    h = b[5] - b[2]
    return t in ('STAT', 'ACTI') and h <= FOOT_TALL and -b[2] >= FOOT_SHARE * h


def _ground_z(db, b, x, y, s=1.0, rid=None):
    g = mapdata.terrain_z(db, x, y)
    if g is None:
        return None
    # (a loose thing, named by rid: its lowest point on the ground. A yard's crates, barrels, baskets and buckets
    # stood with their middles on it, half in the dirt: 53 of the 175 loose things outdoors in the user's town,
    # 2026-11-13, "raise all this assorted decor out of the dirt")
    if rid is not None and _on_its_foot(db, rid, b):
        return g - b[2] * s
    # (the piece's foot on the ground: most statics stand at their origin; one with its mesh starting over it is sunk)
    return g - (b[2] * s if b and b[2] > 0 else 0.0)


def _pct(rng, pcts, lo=None, hi=None):
    """A value drawn from a percentile sketch [10th, 25th, 50th, 75th, 90th] (straight between the marks, the tails
    held at the 10th and 90th), clamped to [lo, hi]."""
    if not pcts:
        return lo if lo is not None else 0.0
    marks = [(0.1, pcts[0]), (0.25, pcts[1]), (0.5, pcts[2]), (0.75, pcts[3]), (0.9, pcts[4])]
    u = rng.random()
    v = marks[0][1] if u <= 0.1 else marks[-1][1]
    for (ua, va), (ub, vb) in zip(marks, marks[1:]):
        if ua <= u <= ub:
            v = va + (vb - va) * (u - ua) / (ub - ua)
            break
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _draw(rng, dist):
    """One key of {key: weight} by weight; None for an empty one."""
    tot = float(sum(dist.values())) if dist else 0.0
    if tot <= 0:
        return None
    r = rng.random() * tot
    for k, w in dist.items():
        r -= w
        if r <= 0:
            return k
    return list(dist)[-1]


def _count(rng, rate, cap=3):
    """How many at a rate per building: the whole part, and the rest by chance."""
    if not rate or rate <= 0:
        return 0
    n = int(rate) + (1 if rng.random() < rate - int(rate) else 0)
    return min(cap, n)


def _survey(db):
    try:
        import gardensurvey
        return gardensurvey.outdoor_ready(db)
    except Exception:
        return None


def _fig(db, what, culture, region):
    """The game's figures for a kind of scene, the region's own, else the culture's, else all; the baked ones when
    the survey has not run."""
    try:
        import gardensurvey
        f = gardensurvey.outdoor_rule(db, what, culture, region)
    except Exception:
        f = None
    out = dict(GAME.get(what) or {})
    if f:
        out.update({k: v for k, v in f.items() if v not in (None, [], {})})
    return out


def _rate(db, what, culture):
    """How many of these the game stands a building in towns of this culture (gardensurvey.per_building), else the
    baked mean."""
    try:
        import gardensurvey
        r = gardensurvey.per_building(db, what, culture)
        if r is not None:
            return r
    except Exception:
        pass
    return GAME['rate'].get(what, 0.0)


def _variants(db):
    """{kind-name: [ids]}: every growing thing in the load order by its name without the variant number
    (flora_saltrice: flora_saltrice_01, _02), so a species the survey names comes with all its models."""
    key = id(db.recs)
    if key in _VAR:
        return _VAR[key]
    import gardensurvey
    out = {}
    for r in db.recs:
        if r[0] not in ('STAT', 'ACTI', 'CONT'):
            continue
        low = r[1].lower()
        if 'unique' in low or low.startswith('colony '):
            continue                          # (a quest's own stump, a colony's own tree: never ours)
        if gardensurvey.plant_kind(low) and db.resolve_id(r[1]) is not None:
            out.setdefault(gardensurvey.plant_base(low), []).append(r[1])
    _VAR.clear()
    _VAR[key] = out
    return out


def _region_at(db, x, y, memo):
    k = '#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0))
    if k not in memo:
        ci = mapdata.cell_info(db, k)
        memo[k] = ((ci or {}).get('region') or '').lower()
    return memo[k]


def _wild_trees(db, region):
    """The trees of the region's own wild land ({kind-name: n}, landdecor's squares), for a region whose towns the
    survey saw no trees by."""
    try:
        import landdecor
        from collections import Counter
        import gardensurvey
        lib = landdecor.learn(db, region)
        C = Counter()
        for sqs in lib['squares'].values():
            for sq in sqs:
                for it in sq:
                    low = it[0].lower()
                    if landdecor.kind_of(low) == 'trees' and not re.search(r'log|stump|dead|fallen|branch', low):
                        C[gardensurvey.plant_base(low)] += 1
        return dict(C.most_common(6))
    except Exception:
        return {}


_HOME = {}


def _plant_home(db, region):
    """The region whose plants grow on this region's land: its own where it has any, else the one nearest in weather
    and on the map (landregion.plant_region). One region for a place's beds, trees and undergrowth alike."""
    r = (region or '').lower()
    if r not in _HOME:
        try:
            import landregion
            _HOME[r] = (landregion.plant_region(db, r) or r).lower()
        except Exception as e:
            print('plants: the land\'s region:', e)
            _HOME[r] = r
    return _HOME[r]


def _own_species(db, what, region):
    """What the game grows in scenes of this kind in this very region ({base id: n}), {} where it has under two."""
    import gardensurvey
    s = gardensurvey.outdoor_ready(db)
    if not s or not s.get(what):
        return {}
    key = {'fields': 'crops_by_region', 'orchards': 'trees_by_region', 'beds': 'kinds_by_region', 'house_trees': 'trees_by_region'}.get(what)
    own = ((s[what].get(key) or {}).get((region or '').lower())) if key else None
    return dict(own) if own and sum(own.values()) >= 2 else {}


def _wild_kinds(db, region, kind):
    """{kind-name: n}: what grows wild of a kind ('trees', 'plants') on a region's own land (landdecor's squares)."""
    try:
        import landdecor
        from collections import Counter
        import gardensurvey
        C = Counter()
        for sqs in landdecor.learn(db, region)['squares'].values():
            for sq in sqs:
                for it in sq:
                    low = it[0].lower()
                    if low.startswith('dlt_') or landdecor.kind_of(low) != kind or re.search(r'log|stump|dead|fallen|branch', low):
                        continue
                    C[gardensurvey.plant_base(low)] += 1
        return dict(C.most_common(6))
    except Exception:
        return {}


def _species(db, what, region, culture, fallback=()):
    """{kind-name: weight} of what the game grows in scenes of this kind in this region (gardensurvey.region_species:
    the region's, else the culture's, else every place's), kept to the names this load order has; the fallback names
    when the survey has nothing."""
    V = _variants(db)
    pool = {}
    try:
        import gardensurvey
        # (the region's own; a region the game grows nothing by houses in, the continent's unmade land, takes its
        # land's own region's (_plant_home), beds and trees alike, then what grows wild there: by the culture's whole
        # range a bayou village got Ashlands grass, a Mournhold tree and Cyrodiil figs, the Headland run 2026-11-11)
        home = _plant_home(db, region)
        pool = _own_species(db, what, region) or (_own_species(db, what, home) if home != (region or '').lower() else {})
        if not pool and what in ('beds', 'house_trees') and home:
            pool = {b: n for b, n in _wild_kinds(db, home, 'trees' if what == 'house_trees' else 'plants').items() if V.get(b)}
        if what == 'fields':
            # (crops only: see NOT_FARMED; a region whose only "crop" is one of those takes its culture's)
            farmed = lambda d: {b: n for b, n in (d or {}).items() if not NOT_FARMED.search(b)}
            pool = farmed(_own_species(db, what, region)) or (farmed(_own_species(db, what, home)) if home != (region or '').lower() else {})
            if not pool:
                cc = (((gardensurvey.outdoor_ready(db) or {}).get('fields') or {}).get('crops_by_culture') or {}).get(culture) or {}
                pool = farmed(cc) if sum(cc.values()) >= 2 else {}
            if not pool and not any(V.get(b) for b in fallback):
                # (every place's crops only where the table of the culture's kind has none in this load order)
                pool = farmed(gardensurvey.region_species(db, what, region, culture))
        elif not pool:
            pool = gardensurvey.region_species(db, what, region, culture) or {}
    except Exception:
        pool = {}
    out = {b: n for b, n in pool.items() if V.get(b)}
    if what in ('house_trees', 'orchards'):
        # (a tree by the house is a tree: the survey's tree kinds take in the game's logs and stumps by the same name,
        # and a Gold Coast yard got a fallen log for its tree, the 3D look of 2026-11-05)
        out = {b: n for b, n in out.items() if not re.search(r'log|stump|dead|fallen|branch', b)}
    if not out and what == 'house_trees':
        out = {b: n for b, n in _wild_trees(db, region).items() if V.get(b)}
    if not out:
        out = {b: 1 for b in fallback if V.get(b)}
    return out


def _pick(db, rng, pool):
    """One model id of a species pool: a kind-name by weight, then one of its variants."""
    V = _variants(db)
    base = _draw(rng, pool)
    if not base or not V.get(base):
        return None
    return rng.choice(V[base])


def _fence_run(db, space, memo, F, a, b, inward, gap_at=None):
    """A fence from a to b along a plot's edge, FENCE_IN inside it (inward: the unit normal into the plot): pieces of
    the culture's lengths, longest first, a post at each end. gap_at: (t0, t1) along the run left open (a gate's
    way). [(id, (x, y, z, 0, 0, rz), 1.0)] or [] when the run could not be laid mostly whole."""
    dx, dy = _unit(b[0] - a[0], b[1] - a[1])
    ax, ay = a[0] + inward[0] * FENCE_IN, a[1] + inward[1] * FENCE_IN
    bx, by = b[0] + inward[0] * FENCE_IN, b[1] + inward[1] * FENCE_IN
    L = math.hypot(bx - ax, by - ay)
    runs = [(i, n) for i, n in F['runs'] if db.resolve_id(i) is not None]
    if not runs or L < runs[-1][1]:
        WHY['fence: run too short'] = WHY.get('fence: run too short', 0) + 1
        return []
    rz = math.atan2(-dy, dx) % (2 * math.pi)     # (the piece's x along the run)
    gap, lift = float(F.get('gap', FENCE_GAP)), float(F.get('lift') or 0.0)
    joints = [-gap / 2.0]                        # (where a post stands when the wall has one at every joint)
    out, t, want, got = [], 0.0, 0, 0
    while True:
        piece = next(((i, n) for i, n in runs if t + n <= L + 1), None)
        if piece is None:
            break
        rid, n = piece
        bb = _bounds(db, memo, rid)
        if not bb:
            break
        if gap_at and t < gap_at[1] and t + n > gap_at[0]:
            t += n + gap                     # (the gate's way: no piece across it)
            continue
        mx, my = ax + dx * (t + n / 2.0), ay + dy * (t + n / 2.0)
        # (the piece's bounds centre on the run's middle: its origin may sit at an end)
        cx_, cy_ = (bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0
        wx = cx_ * dx - cy_ * dy
        wy = cx_ * dy + cy_ * dx
        px, py = mx - wx, my - wy
        want += 1
        rect = _rect(mx, my, dx, dy, n / 2.0 - 2, max(14.0, (bb[4] - bb[1]) / 2.0))
        z = _ground_z(db, bb, px, py)
        if z is not None and space.free(rect):
            out.append((rid, (px, py, z + lift, 0.0, 0.0, rz), 1.0, rect))
            got += 1
            joints.append(t + n + gap / 2.0)
        t += n + gap
    if not want or got < FENCE_SHARE * want:
        WHY['fence: %d of %d lengths fit' % (got, want)] = WHY.get('fence: %d of %d lengths fit' % (got, want), 0) + 1
        return []
    for _rid, _p, _s, rect in out:
        space.take(rect)
    laid = [(rid, p, s) for rid, p, s, _r in out]
    post = F.get('post')
    if post and db.resolve_id(post) is not None:
        pb = _bounds(db, memo, post)
        ends = [(ax, ay), (ax + dx * min(L, t), ay + dy * min(L, t))]
        if F.get('posts') == 'each':
            ends = [(ax + dx * j_, ay + dy * j_) for j_ in joints]
        if gap_at:
            ends += [(ax + dx * gap_at[0], ay + dy * gap_at[0]), (ax + dx * gap_at[1], ay + dy * gap_at[1])]
        for ex, ey in ends:
            z = _ground_z(db, pb, ex, ey)
            if z is not None:
                laid.append((post, (ex, ey, z + lift, 0.0, 0.0, rz), 1.0))
    return laid


def _fence_for(db, cult, q, rng, F):
    """The yard wall for one house: a poor Gold Coast hut's is the rough stone wall as often as the wooden fence
    (Archad's huts stand behind it, Thresvy's behind fences); a villa of the Anvil, Stirk or Gold Coast sets in a Gold
    Coast town has Anvil's capped-post wall."""
    key = str((q.get('b') or {}).get('key') or '').lower()
    if 'setgcpoor' in key:
        P = FENCES['Gold Coast poor']
        return P if db.resolve_id(P['runs'][0][0]) is not None and rng.random() < 0.5 else F
    if cult == 'Gold Coast' and re.search(r'setgc_x_|setanv_x_|setstr_x_', key):
        A = FENCES['Anvil']
        return A if db.resolve_id(A['runs'][0][0]) is not None else F
    return F


def _plot_frame(q):
    """(c, s): the unit vectors of the plot's x (across, to the right facing out of the door) and y (into the plot,
    away from the street), as townplan._rect lays them."""
    fx, fy = math.sin(q['face']), math.cos(q['face'])
    Y = (-fx, -fy)
    return (Y[1], -Y[0]), Y                           # (x as the placement turn lays a set's x: to the right facing in)


def _lay_set(db, space, memo, things, ox, oy, X, Y, kind):
    """A set's things in the yard frame at (ox, oy) with x along X and y along Y, each on free ground; the set is laid
    when most of it fits."""
    placed, rects = [], []
    rz0 = math.atan2(Y[0], Y[1])
    for rid, lx, ly, dz, rz in things:
        if db.resolve_id(rid) is None:
            continue
        bb = _bounds(db, memo, rid)
        if not bb:
            continue
        wx = ox + X[0] * lx + Y[0] * ly
        wy = oy + X[1] * lx + Y[1] * ly
        rzw = (rz + rz0) % (2 * math.pi)
        pad = max(0.0, THING - max(bb[3] - bb[0], bb[4] - bb[1]) / 2.0)
        rect = _footprint(bb, wx, wy, rzw, 1.0, pad)
        z = _ground_z(db, bb, wx, wy, rid=rid)
        if z is None or not space.free(rect):
            continue
        placed.append((rid, (wx, wy, z + dz, 0.0, 0.0, rzw), 1.0))
        rects.append(rect)
    if len(placed) < 0.5 * max(1, sum(1 for t in things if db.resolve_id(t[0]) is not None)):
        return []
    for r in rects:
        space.take(r)
    return placed


def _crop_rows(db, space, memo, rng, crop_pool, ox, oy, X, Y, width, depth, fig, cap=None, path=False, role='crop', gaps=None):
    """Furrows of one crop: rows across the width (x) at the game's row gap, plants along each row (y) at its in-row
    gap, each turned about the field's line as much as the game's are (align), at scale 1; a path left through the
    middle of a wide field. The frame's origin is the near edge's middle. [(id, pose, s)]."""
    import gardensurvey
    V = _variants(db)
    base = _draw(rng, crop_pool)
    if not base or not V.get(base):
        return []
    ids = V[base]
    bb0 = _bounds(db, memo, ids[0])
    pw = max(bb0[3] - bb0[0], bb0[4] - bb0[1]) if bb0 else 100
    row_gap = gaps[0] if gaps else _pct(rng, fig.get('row_gap'), max(90, pw * 0.7), 240)
    in_gap = gaps[1] if gaps else _pct(rng, fig.get('in_gap'), max(60, pw * 0.6), 240)
    rows = max(1, min(8, int(round(width / row_gap))))
    per = max(2, int(round(depth / in_gap)))
    align = _pct(rng, fig.get('align'), 0.1, 0.95)
    jitter = (1.0 - align) * math.pi
    base_rz = math.atan2(Y[0], Y[1]) + rng.uniform(0, 2 * math.pi)
    skip = rows // 2 if (path and rows >= 4) else None
    out, rects = [], []
    x0 = -(rows - 1) * row_gap / 2.0
    for r in range(rows):
        if r == skip:
            continue
        for k in range(per):
            if cap and len(out) >= cap:
                break
            lx = x0 + r * row_gap + rng.uniform(-8, 8)
            ly = in_gap / 2.0 + k * in_gap + rng.uniform(-in_gap * 0.1, in_gap * 0.1)
            wx, wy = ox + X[0] * lx + Y[0] * ly, oy + X[1] * lx + Y[1] * ly
            rid = rng.choice(ids)
            bb = _bounds(db, memo, rid)
            rect = _rect(wx, wy, X[0], X[1], 30, 30)
            z = _ground_z(db, bb, wx, wy)
            if z is None or not space.free(rect, grows=True):
                continue
            out.append((rid, (wx, wy, z, 0.0, 0.0, (base_rz + rng.uniform(-jitter, jitter)) % (2 * math.pi)), round(rng.uniform(0.96, 1.04), 3)))
            rects.append(rect)
    if len(out) < 3:
        return []
    for r in rects:
        space.take(r)
    return out


class _House:
    """A plot's house in its own frame: X across (right, facing in from the street), Y inward, the footprint's
    back/front/left/right lines relative to (cx, cy), and the door's x."""

    def __init__(self, q):
        self.q = q
        self.X, self.Y = _plot_frame(q)
        self.cx, self.cy = q['x'], q['y']
        ys = [(p[0] - self.cx) * self.Y[0] + (p[1] - self.cy) * self.Y[1] for p in q['rect']]
        xs = [(p[0] - self.cx) * self.X[0] + (p[1] - self.cy) * self.X[1] for p in q['rect']]
        self.back, self.front, self.xl, self.xr = max(ys), min(ys), min(xs), max(xs)
        self.w = self.xr - self.xl
        self.d = self.back - self.front
        self.dlx = ((q['door'][0] - self.cx) * self.X[0] + (q['door'][1] - self.cy) * self.X[1]) if q.get('door') else None

    def at(self, lx, ly):
        return self.cx + self.X[0] * lx + self.Y[0] * ly, self.cy + self.X[1] * lx + self.Y[1] * ly

    def wall_point(self, side, t, d):
        """A point d outside the wall `side` ('left', 'right', 'back', 'front'), t (0..1) along it, with the wall's
        outward normal in the world and the point's (lx, ly); None when the front wall has no room off the door."""
        X, Y = self.X, self.Y
        if side == 'left':
            lx, ly = self.xl - d, self.front + 50 + t * max(0.0, self.d - 100)
            n = (-X[0], -X[1])
        elif side == 'right':
            lx, ly = self.xr + d, self.front + 50 + t * max(0.0, self.d - 100)
            n = (X[0], X[1])
        elif side == 'back':
            lx, ly = self.xl + 50 + t * max(0.0, self.w - 100), self.back + d
            n = (Y[0], Y[1])
        else:
            # (the front wall, either side of the door's way: a plant in it stands in the walking line)
            if self.dlx is None:
                lx = self.xl + 50 + t * max(0.0, self.w - 100)
            else:
                room_l = (self.dlx - ARRIVE[0] - 40) - (self.xl + 40)
                room_r = (self.xr - 40) - (self.dlx + ARRIVE[0] + 40)
                if room_l < 40 and room_r < 40:
                    return None
                if room_l >= 40 and (room_r < 40 or t < 0.5):
                    lx = self.xl + 40 + (t * 2 % 1.0) * room_l
                else:
                    lx = self.dlx + ARRIVE[0] + 40 + (t * 2 % 1.0) * room_r
            ly = self.front - d
            n = (-Y[0], -Y[1])
        wx, wy = self.at(lx, ly)
        return wx, wy, n, lx, ly

    def side_for(self, which):
        """'side' → left or right by chance; 'front', 'back' as they are."""
        return which

    def arrival(self):
        """The way out of the door, ARRIVE deep, kept clear of plants."""
        if not self.q.get('door'):
            return None
        return self.at_rect(self.dlx, self.front - ARRIVE[1] / 2.0 + 20, ARRIVE[0], ARRIVE[1] / 2.0 + 20)

    def at_rect(self, lx, ly, half_x, half_y):
        wx, wy = self.at(lx, ly)
        return _rect(wx, wy, self.X[0], self.X[1], half_x, half_y)


def _side(rng, shares, h):
    s = _draw(rng, shares) or 'side'
    if s == 'side':
        return rng.choice(('left', 'right'))
    return s


def _lay_bed(db, space, memo, rng, h, pool, fig):
    """A bed of flowers or herbs by the house as the game's: two to six plants of one kind (two now and then), a
    clump at the game's spacing, at the side wall mostly, the game's distance out from it. [(id, pose, s)]."""
    n = int(round(_pct(rng, fig.get('plants'), 2, 7)))
    one = rng.random() < (fig.get('one_kind') if isinstance(fig.get('one_kind'), float) else 0.6)
    kinds = []
    for _k in range(1 if one else 2):
        b = _draw(rng, pool)
        if b and b not in kinds:
            kinds.append(b)
    if not kinds:
        return []
    V = _variants(db)
    nn = _pct(rng, fig.get('nn'), 36, 150)
    # (the spot: the game's side and distance from the wall; a spot in a street, a neighbour's plot or a door's way
    # is tried again elsewhere, four times)
    for _try in range(6):
        side = _side(rng, fig.get('side') or GAME['beds']['side'], h)
        d = _pct(rng, fig.get('wall'), 24, 440)
        wp = h.wall_point(side, rng.random(), d)
        if not wp:
            WHY['bed: no wall room'] = WHY.get('bed: no wall room', 0) + 1
            continue
        wx, wy, nrm, lx, ly = wp
        pts = [(wx, wy)]
        out, rects = [], []
        tries = 0
        while len(out) < n and tries < n * 4:
            tries += 1
            if out:
                ax, ay = rng.choice(pts)
                ang = rng.uniform(0, 2 * math.pi)
                dd = nn * rng.uniform(0.75, 1.3)
                px, py = ax + math.cos(ang) * dd, ay + math.sin(ang) * dd
            else:
                px, py = wx, wy
            rid = rng.choice(V[kinds[len(out) % len(kinds)]])
            bb = _bounds(db, memo, rid)
            prz = rng.uniform(0, 2 * math.pi)
            if bb and max(bb[3] - bb[0], bb[4] - bb[1]) <= 90:
                rect = _footprint(bb, px, py, prz, 1.0, 4.0)
            else:
                half = max(18.0, min(40.0, (max(bb[3] - bb[0], bb[4] - bb[1]) / 2.0) if bb else 24.0))
                rect = _rect(px, py, h.X[0], h.X[1], half, half)   # (a shrub's fronds may hang over the fence: its root's room)
            z = _ground_z(db, bb, px, py)
            if z is None or not space.free(rect, grows=True):
                if not out:
                    break                     # (the spot itself is taken: another)
                continue
            out.append((rid, (px, py, z, 0.0, 0.0, prz), round(rng.uniform(0.95, 1.08), 3)))
            rects.append(rect)
            pts.append((px, py))
        if len(out) >= 2:
            for r in rects:
                space.take(r)
            return out
        WHY['bed: spot taken'] = WHY.get('bed: spot taken', 0) + 1
    return []


def _lay_tree(db, space, memo, rng, h, pool, fig):
    """A tree by the house as the game stands them: at the side or back mostly, the game's distance from the wall,
    one of the region's own trees. [(id, pose, s)]."""
    rid = _pick(db, rng, pool)
    if not rid:
        return []
    bb = _bounds(db, memo, rid)
    if not bb:
        return []
    # (a big tree keeps its trunk further out than a sapling: the game's median 178 is of all its trees, and a
    # wide-crowned one stood with its trunk at the wall and its crown through the roof, the 3D look of 2026-11-05)
    crown = max(bb[3] - bb[0], bb[4] - bb[1])
    least = max(TREE_MIN_D, 0.3 * crown)
    for _try in range(6):
        side = _side(rng, fig.get('side') or GAME['house_trees']['side'], h)
        d = _pct(rng, fig.get('d'), least, max(360.0, least + 40))
        wp = h.wall_point(side, rng.random(), d)
        if not wp:
            continue
        wx, wy, nrm, lx, ly = wp
        rect = _rect(wx, wy, h.X[0], h.X[1], TREE_TRUNK, TREE_TRUNK)
        s = round(rng.uniform(0.9, 1.15), 3)
        z = _ground_z(db, bb, wx, wy, s)
        if z is None or not space.free(rect, grows=True):
            continue
        space.take(rect)
        return [(rid, (wx, wy, z, 0.0, 0.0, rng.uniform(0, 2 * math.pi)), s)]
    WHY['tree: no spot'] = WHY.get('tree: no spot', 0) + 1
    return []


def _garden_of(db, rng, rid, px, py, pz, prz, scale, own=()):
    """What grows in a planter stood outdoors: one of the game's own gardens of that model (gardensurvey.dressing),
    each thing at its offset in the planter's frame; of a few draws, the one with most of the region's own plants in
    it (own: kind-names), so a Gold Coast planter doesn't come up full of Bitter Coast mushrooms. [(id, pose, s)]."""
    things = None
    try:
        import gardensurvey
        best = None
        for _k in range(5 if own else 1):
            g = gardensurvey.dressing(db, rid, rng, min_n=gardensurvey.usual(db, rid) or 1, scale=scale)
            if not g:
                break
            share = sum(1 for t in g if gardensurvey.plant_base(t['id'].lower()) in own) / float(len(g))
            if best is None or share > best[0]:
                best = (share, g)
            if share >= 0.99:
                break
        things = best[1] if best else None
    except Exception:
        things = None
    if not things:
        return []
    c, s = math.cos(prz), math.sin(prz)
    out = []
    for t in things:
        if db.resolve_id(t['id']) is None:
            continue
        wx = px + t['x'] * c + t['y'] * s
        wy = py - t['x'] * s + t['y'] * c
        out.append((t['id'], (wx, wy, pz + t['z'], t.get('rx', 0.0), t.get('ry', 0.0), (prz + t['rz']) % (2 * math.pi)), t.get('s', 1.0)))
    return out


def _lay_planter(db, space, memo, rng, h, fig, culture, own=()):
    """A planter by the house: the culture's own model at its scale, by the door (the game's one in ten: the game's
    offset off the door and out from the wall) or along a side wall, with the game's garden in it nine times in
    ten. [(id, pose, s, role)]."""
    models = {m: n for m, n in (fig.get('models') or {}).items() if db.resolve_id(m) is not None}
    if not models:
        models = {m: 1 for m in PLANTERS if db.resolve_id(m) is not None}
    rid = _draw(rng, models)
    if not rid:
        return []
    scale = float((fig.get('scale') or {}).get(rid) or 1.0)
    bb = _bounds(db, memo, rid)
    if not bb:
        return []
    pw = max(bb[3] - bb[0], bb[4] - bb[1]) * scale
    by_door = h.dlx is not None and rng.random() < max(0.1, float(fig.get('by_door') or 0.1))
    spots = []
    if by_door:
        sgn = rng.choice((-1, 1))
        lx = h.dlx + sgn * max(ARRIVE[0] + pw / 2.0 + 10, _pct(rng, fig.get('lx'), 120, 300))
        ly = h.front + _pct(rng, fig.get('ly'), -200, -30)
        if h.xl + pw / 2.0 <= lx <= h.xr - pw / 2.0:
            wx, wy = h.at(lx, ly)
            spots.append((wx, wy, (-h.Y[0], -h.Y[1])))
    for _k in range(3):
        side = rng.choice(('left', 'right', 'back'))
        wp = h.wall_point(side, rng.random(), pw / 2.0 + rng.uniform(20, 90))
        if wp:
            spots.append((wp[0], wp[1], wp[2]))
    for wx, wy, nrm in spots:
        prz = math.atan2(nrm[0], nrm[1]) % (2 * math.pi)
        rect = _footprint(bb, wx, wy, prz, scale, 6.0)
        z = _ground_z(db, bb, wx, wy, scale)
        if z is None or not space.free(rect, grows=True):
            continue
        space.take(rect)
        out = [(rid, (wx, wy, z, 0.0, 0.0, prz), scale, 'planter')]
        if rng.random() < float(fig.get('planted') or 0.9):
            out += [(i, p, s, 'planter plant') for i, p, s in _garden_of(db, rng, rid, wx, wy, z, prz, scale, own)]
        return out
    WHY['planter: no spot'] = WHY.get('planter: no spot', 0) + 1
    return []


# (a trellis is a frame on legs, not ivy: hung up a wall at ivy's height its feet stood 64 and 107 clear of the
# ground, the user's Tharen Rise, 2026-11-11. The game's: 52 of 52 drumpear and T_De_Set_X trellises outdoors
# stand with their foot at or under the lowest ground under them (a median 8 to 97 in it); the other 5,
# ex_common_trellis and the Anvil set's, stand some 200 up on roofs and terraces and are left out here)
TRELLIS = re.compile(r'trellis', re.I)
TRELLIS_UP = re.compile(r'ex_common_trellis|setanv_x_trellis', re.I)
TRELLIS_IN = 8.0            # (its legs this far into the lowest ground under it)
TRELLIS_STEEP = 100.0       # (ground falling more than this under it: no place for a frame)


def _lay_vine(db, space, memo, rng, h, fig, height):
    """Ivy or a vine on a wall of the house, as the game hangs them: the culture's model, its bottom at the game's
    height up the wall, turned the way the game turns that model against a wall, on the side or front wall.
    [(id, pose, s)]."""
    models = {m: n for m, n in (fig.get('models') or {}).items() if db.resolve_id(m) is not None and not TRELLIS_UP.search(m)}
    if not models:
        return []
    rid = _draw(rng, models)
    bb = _bounds(db, memo, rid)
    if not bb:
        return []
    turns = (fig.get('turn') or {}).get(rid) or {}
    rel = int(max(turns, key=turns.get)) if turns else 0
    s = round(_pct(rng, fig.get('scale'), 0.85, 1.4), 3) if fig.get('scale') else 1.0
    along_x = (bb[3] - bb[0]) >= (bb[4] - bb[1])
    thin = min(bb[3] - bb[0], bb[4] - bb[1]) * s
    long_ = max(bb[3] - bb[0], bb[4] - bb[1]) * s
    top_room = max(120.0, (height or 420) * 0.75 - (bb[5] - bb[2]) * s)
    for _try in range(4):
        side = _side(rng, fig.get('side') or GAME['vines']['side'], h)
        wp = h.wall_point(side, rng.random(), 0.0)
        if not wp:
            continue
        wx, wy, nrm, lx, ly = wp
        yaw = math.atan2(nrm[0], nrm[1]) + rel * math.pi / 2.0
        c, sn = math.cos(yaw), math.sin(yaw)
        # (the bounds' centre under the turn, so the vine's thin side lies against the wall, its length along it)
        cxl, cyl = (bb[0] + bb[3]) / 2.0 * s, (bb[1] + bb[4]) / 2.0 * s
        ox, oy = cxl * c + cyl * sn, -cxl * sn + cyl * c
        off = thin / 2.0 + 3
        ccx, ccy = wx + nrm[0] * off, wy + nrm[1] * off
        px, py = ccx - ox, ccy - oy
        bottom = _pct(rng, fig.get('wall_bottom') or fig.get('bottom'), 40, top_room)
        g = mapdata.terrain_z(db, wx, wy)
        if g is None:
            continue
        along = (-nrm[1], nrm[0])
        rect = _rect(ccx, ccy, along[0], along[1], long_ / 2.0, thin / 2.0 + 2)
        # (a vine hangs over whatever stands at the wall's foot: only another vine is in its way)
        if any(_overlap(rect, p) for p in getattr(space, 'vines', [])):
            continue
        z = g + bottom - bb[2] * s
        if TRELLIS.search(rid):
            gs = [mapdata.terrain_z(db, px + (lx_ * c + ly_ * sn) * s, py + (-lx_ * sn + ly_ * c) * s)
                  for lx_ in (bb[0], bb[3]) for ly_ in (bb[1], bb[4])]
            if any(q is None for q in gs) or max(gs) - min(gs) > TRELLIS_STEEP:
                continue
            z = min(gs) - TRELLIS_IN - bb[2] * s
        space.vines = getattr(space, 'vines', []) + [rect]
        return [(rid, (px, py, z, 0.0, 0.0, yaw % (2 * math.pi)), s)]
    WHY['vine: no wall'] = WHY.get('vine: no wall', 0) + 1
    return []


def _house_height(db, q):
    try:
        import townbuild
        C = townbuild.by_uid(townbuild.catalog(db))
        e = townbuild.built(C, q.get('b')) or {}
        return float(e.get('height') or 0) or None
    except Exception:
        return None


ALSO_BIG = 300.0               # (a laid piece wider than this either way from its origin is kept clear of by its turned footprint)
STANDING = 60                  # a thing of the land this wide (a rock, a tree, a ruin) is ground nothing is laid on


def _standing(db, plan, memo, cells=None):
    """The footprints of what already stands on the town's ground and is not the town's own: the game's rocks, trees,
    ruins and anything 60 wide or more, by their turned bounds, in the cells the plots lie in (or `cells`)."""
    cells = set(cells or ())
    for q in (plan or {}).get('plots') or ():
        if q.get('rect'):
            for p in q['rect']:
                cells.add('#%d,%d' % (math.floor(p[0] / 8192.0), math.floor(p[1] / 8192.0)))
    out = []
    for ck in cells:
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        for r in m.get('refs') or ():
            if r.get('mine') or not r.get('b') or r['type'] not in ('STAT', 'ACTI', 'CONT'):
                continue
            s = r.get('s') or 1.0
            b = r['b']
            if max(b[3] - b[0], b[4] - b[1]) * s < STANDING or 'marker' in r['id'].lower():
                continue
            out.append(_footprint(b, r['p'][0], r['p'][1], r['p'][5], s, 0.0))
    return out


def yards(db, plan, seed=1, blocked=(), also=(), amount=1.0, trees_k=1.0):
    """[{'id', 'p', 's', 'role'}]: fences, yard sets, garden rows, beds, trees, planters and vines for a made town
    (plan as townbuild.fit left it). blocked: polygons kept clear (the wall); also: [(id, p)] things laid already
    (the dressing's), kept clear of. trees_k: the town's own amount of trees, by its houses and on its open ground (1 as
    the culture's towns have them, 0 none, 2 twice)."""
    import towndress
    cult = plan.get('culture') or 'Imperial'
    F = FENCES.get(cult) or FENCES.get(FENCE_KIN.get(cult, ''), None)
    rng = random.Random('%s|%s|story' % (seed, cult))
    memo = {}
    rmemo = {}
    rects = [[tuple(p) for p in q['rect']] for q in plan['plots'] if q.get('rect') and q.get('b')]
    polys = list(blocked) + rects + [[tuple(p) for p in o] for o in plan.get('obstacles') or ()]
    houses = {}
    for q in plan['plots']:
        if q.get('door') and q.get('b'):
            polys.append(towndress._door_clear(q['door'][0], q['door'][1], q['face']))
        if q.get('b') and q.get('rect'):
            h = _House(q)
            houses[id(q)] = h
            a = h.arrival()
            if a:
                polys.append(a)
    polys += towndress._street_polys(plan, towndress.STREET_BLOCK_SHARE)
    for rid, p in also:
        bb = _bounds(db, memo, rid)
        half = max(24.0, (bb[3] - bb[0]) / 2.0 if bb else 24.0, (bb[4] - bb[1]) / 2.0 if bb else 24.0)
        if bb and half > ALSO_BIG:
            # (a big piece, a wall's length or a whole building's shell: its own footprint as it is turned)
            polys.append(_footprint(bb, p[0], p[1], p[5] if len(p) > 5 else 0.0, 1.0, 0.0))
            continue
        polys.append(_rect(p[0], p[1], 1.0, 0.0, half, half))
    # (and the land's own rocks, trees and ruins standing in the town's cells: a bed of lilies came up inside a Gold
    # Coast boulder, the 3D look of 2026-11-05; the dressing's `also` list holds only what the town laid)
    polys += _standing(db, plan, memo)
    # (what grows keeps off the pavement's whole width: a bed at the kerb's edge is a bed on the road)
    space = _Space(polys, strict=towndress._street_polys(plan, 1.0))
    out = []
    n = {'fences': 0, 'posts': 0, 'sets': 0, 'things': 0, 'crops': 0, 'planters': 0, 'planter plants': 0, 'beds': 0, 'bed plants': 0, 'trees': 0, 'vines': 0,
         'yards': 0, 'no room': 0, 'species': set()}
    crop_cult = 'Dunmer' if cult in ('Hlaalu', 'Velothi', 'Redoran', 'Dunmer common', 'Dunmer', 'Indoril', 'Mournhold', 'Telvanni', 'Ashlander', 'Stronghold') \
        else 'Nord' if cult in ('Nordic', 'Reach') else cult
    S = _survey(db)
    WHY.clear()
    # the game's rates a building for the culture (gardensurvey.per_building); planters on balconies and walls
    # ('high', a third of the game's) have no home on the ground, so that share is left out
    r_beds = _rate(db, 'beds', cult) * amount
    r_trees = _rate(db, 'house_trees', cult) * amount * trees_k
    pf0 = _fig(db, 'planters', cult, None)
    r_planters = _rate(db, 'planters', cult) * (1.0 - float((pf0.get('stand') or {}).get('high') or 0)) * amount
    r_vines = _rate(db, 'vines', cult) * amount
    figs = {}

    def fig(what, region):
        k = (what, region)
        if k not in figs:
            figs[k] = _fig(db, what, cult, region)
        return figs[k]
    pools = {}

    def pool(what, region):
        k = (what, region)
        if k not in pools:
            fb = CROPS.get(crop_cult) or CROPS['Imperial'] if what == 'fields' else ()
            pools[k] = _species(db, what, region, cult, fallback=fb)
        return pools[k]

    def add(laid, role, kind=None):
        for item in laid:
            rid, p, s = item[0], item[1], item[2]
            rec = {'id': rid, 'p': [round(v, 4) if i >= 3 else round(v, 2) for i, v in enumerate(p)], 's': round(float(s), 3), 'role': (item[3] if len(item) > 3 else role)}
            if kind:
                rec['kind'] = kind
            out.append(rec)
    for q in plan['plots']:
        if not q.get('b') or not q.get('rect') or rng.random() > amount:
            continue
        h = houses[id(q)]
        X, Y = h.X, h.Y
        cx, cy = h.cx, h.cy
        back, front, xl, xr, w = h.back, h.front, h.xl, h.xr, h.w
        region = _region_at(db, cx, cy, rmemo)
        depth = YARD_D
        n['yards'] += 1
        # the fence: the yard's back edge, YARD_D behind the house, and its two sides from the house's back corners
        Fq = _fence_for(db, cult, q, rng, F)
        if Fq:
            far = {-1: h.at(xl, back + depth), 1: h.at(xr, back + depth)}
            near_ = {-1: h.at(xl, back + 30), 1: h.at(xr, back + 30)}
            runs = [(far[-1], far[1], (-Y[0], -Y[1])), (near_[-1], far[-1], (X[0], X[1])), (far[1], near_[1], (-X[0], -X[1]))]
            for a, b, inward in runs:
                laid = _fence_run(db, space, memo, Fq, a, b, inward)
                add(laid, 'fence')
                for rid, _p, _s in laid:
                    n['posts' if rid == Fq.get('post') else 'fences'] += 1
        # the yard's kind, laid against the house's back
        if depth >= YARD_MIN:
            kinds = KIND_BY.get(q.get('kind') or 'house') or KIND_BY['house']
            kind = None
            if plan.get('trade') and (q.get('kind') or 'house') in ('house', 'shack'):
                # (what the town lives by: a fisher's yard, a farmer's pen as often as the game's houses of such towns)
                import towntrade
                kind = towntrade.yard_kind(rng, plan['trade'], kinds)
                if kind == 'fishing' and not _fishing_set(db):
                    kind = None
            kind = kind or rng.choice(kinds)
            laid = []
            ox = oy = None
            # (against the middle of the back wall, else to one side: a porch or the dressing's own things may stand
            # in the middle)
            for off in (0.0, w / 4.0, -w / 4.0):
                ox, oy = h.at((xl + xr) / 2.0 + off, back)
                laid = _lay_set(db, space, memo, _fishing_set(db) if kind == 'fishing' else KINDS[kind], ox, oy, X, Y, kind)
                if laid:
                    break
            if kind == 'garden':
                # a kitchen garden: rows of the region's crop at the game's row and plant spacing (its farms'), behind
                # the house in its fenced yard; the yard's fence is its border
                ox, oy = h.at((xl + xr) / 2.0, back + 40)
                rows_ = _crop_rows(db, space, memo, rng, pool('fields', region), ox, oy, X, Y, min(w, 520.0), depth - 90, fig('farms', region), cap=14)
                laid += rows_
                for rid, _p, _s in rows_:
                    n['species'].add(rid.lower())
            if laid:
                n['sets'] += 1
                n['things'] += sum(1 for r, _p, _s in laid if not (r.lower().startswith(('flora', 't_cyr_flora', 't_sky_flora', 't_mw_flora', 't_glb_flora'))))
                n['crops'] += sum(1 for r, _p, _s in laid if r.lower().startswith(('flora', 't_cyr_flora', 't_sky_flora', 't_mw_flora', 't_glb_flora')))
                add(laid, 'yard', kind)
            else:
                n['no room'] += 1
        # beds of flowers and herbs by the walls, at the game's rate for the culture, of the region's own kinds
        for _k in range(_count(rng, r_beds)):
            laid = _lay_bed(db, space, memo, rng, h, pool('beds', region), fig('beds', region))
            if laid:
                n['beds'] += 1
                n['bed plants'] += len(laid)
                n['species'].update(r.lower() for r, _p, _s in laid)
                add(laid, 'bed')
        # a tree by the house
        for _k in range(_count(rng, r_trees, cap=2)):
            laid = _lay_tree(db, space, memo, rng, h, pool('house_trees', region), fig('house_trees', region))
            if laid:
                n['trees'] += 1
                n['species'].update(r.lower() for r, _p, _s in laid)
                add(laid, 'tree')
        # a planter at the door or along a wall, with the game's garden in it
        for _k in range(_count(rng, r_planters, cap=2)):
            own_ = set(pool('beds', region)) | set(pool('fields', region))
            laid = _lay_planter(db, space, memo, rng, h, fig('planters', region), cult, own_)
            if laid:
                n['planters'] += 1
                n['planter plants'] += sum(1 for it in laid if it[3] == 'planter plant')
                n['species'].update(it[0].lower() for it in laid if it[3] == 'planter plant')
                add(laid, 'planter')
        # ivy on the walls, where the culture grows it (the Gold Coast's two and a half a building; none in Dunmer towns)
        if r_vines > 0:
            height = _house_height(db, q)
            for _k in range(_count(rng, r_vines, cap=4)):
                laid = _lay_vine(db, space, memo, rng, h, fig('vines', region), height)
                if laid:
                    n['vines'] += 1
                    add(laid, 'vine')
    # the empty ground left between: a kitchen garden where a pocket holds one, trees on the open ground by the streets
    # (the user, 2026-11-08: "Try to fill in empty space where you can ... a garden in the box area ... maybe some tree
    # in the green patch by the road")
    if amount > 0:
        try:
            pk = pockets(db, plan, space, memo, rng, cult, pool, add, amount, trees_k)
            n.update(pk)
        except Exception as e_:
            WHY['pockets: %s' % e_] = 1
    n['species'] = len(n['species'])
    n['why'] = dict(WHY)
    LAST.clear()
    LAST.update(n)
    return out


POCKET_STEP = 128.0            # the lattice the town's open ground is read on
POCKET_SLOPE = 0.3             # ground steeper than this is no garden's or tree's (the banks are rockblend's)
POCKET_IN = 128.0              # (and this far in from the town's outline or wall)
TREE_SLOPE = 0.6               # (a tree stands on ground up to this steep, as the game's do on its banks)
POCKET_MIN = 8                 # a pocket of fewer lattice points is left as it is
GARDEN_MIN = (384.0, 256.0)    # a pocket that holds a box this big (across, deep) gets a fenced garden (the game's fields: 500 by 200 at the median)
GARDEN_MAX = (1400.0, 1100.0)  # (no bigger: the game's kitchen gardens are small)
GARDEN_EDGE = 48.0             # (its fence kept this far in from the pocket's edge)
POCKET_TREE_AREA = 300000.0    # a tree for about every this much open ground left (550 square) ...
POCKET_TREE_GAP = 420.0        # ... no nearer another than this
POCKET_STREET = 900.0          # trees on ground within this of a street first (by the road)
SHADE_TALL = 650.0             # a shade tree is this tall or taller: the user's own in their town stood 711 to 2,650 (median 858),
                               # the yard maker's saplings 136 to 738
SHADE_SHARE = 0.75             # of the trees on open ground this share are shade trees, where the land has them
OPEN_TREES = 0.35              # trees a building on the town's open ground at least, where there is room (the user set 8 by hand
                               # in a town of about two dozen houses)
TREE_ROOM_MOST = 220.0         # (a big tree's trunk keeps this clear at most: its crown overhangs roofs and walls as the game's do)
_SHADE = {}
POCKET_GARDENS = 0.25          # gardens at most this share of the town's buildings (at least one)
WAY_ON = 2000.0                # (a street's end this near the outline along its own line: the ground between is its way on)
# the small growth of the land a building, on the open ground between the houses (grass, bushes, flowers, mushrooms,
# stumps and logs: the game's towns by culture, 149 towns read 2026-11-10; made towns had a third of it)
UNDER = {'Dunmer': 2.5, 'Dunmer common': 2.5, 'Hlaalu': 2.0, 'Telvanni': 1.9, 'Velothi': 3.0, 'Common': 1.1, 'Gold Coast': 7.6, 'Redoran': 1.6,
         'Ashlander': 4.0, 'Reach': 3.2, 'Mournhold': 5.0, 'Nordic': 2.1, 'Indoril': 5.2}
UNDER_ELSE = 2.5
UNDER_REACH = 800.0            # (within this of a building's middle: the town's own ground, not the land beyond)
UNDER_ROOM = 14.0              # (a small plant's own room, half a side)
WILD_MIN = 40                  # (a region with fewer small growing things read than this is not the look)


def _max_rect(grid, W, H):
    """The biggest all-True box in a W x H grid (grid[v][u]): (u0, v0, u1, v1) inclusive, or None."""
    best, out = 0, None
    hgt = [0] * W
    for v in range(H):
        for u in range(W):
            hgt[u] = hgt[u] + 1 if grid[v][u] else 0
        stack = []
        for u in range(W + 1):
            h = hgt[u] if u < W else 0
            start = u
            while stack and stack[-1][1] >= h:
                su, sh = stack.pop()
                if sh * (u - su) > best:
                    best = sh * (u - su)
                    out = (su, v - sh + 1, u - 1, v)
                start = su
            stack.append((start, h))
    return out


def pockets(db, plan, space, memo, rng, cult, pool, add, amount=1.0, trees_k=1.0):
    """The town's open ground (inside its wall or outline, gentle, clear of everything `space` holds: the plots,
    door ways, streets, the dressing, the rocks, the yards) read on a POCKET_STEP lattice and joined into pockets; a
    pocket that holds a GARDEN_MIN box gets a fenced kitchen garden of the region's crop (farm()), its gate toward the
    nearest street, turned as its nearest house; the open ground left gets trees of the region's own kinds, those by
    the streets first. {'gardens', 'pocket trees', 'pockets'}."""
    outline = [tuple(p) for p in (plan.get('wall_outline') or plan.get('outline') or ())]
    if len(outline) < 3:
        # (a plan without its outline: the hull of its plots and streets)
        pts_ = sorted({(round(p[0]), round(p[1])) for q in plan['plots'] if q.get('rect') for p in q['rect']} |
                      {(round(p[0]), round(p[1])) for s_ in plan.get('streets') or () for p in s_.get('pts') or ()})
        if len(pts_) < 3:
            return {}
        cr = lambda o, a_, b_: (a_[0] - o[0]) * (b_[1] - o[1]) - (a_[1] - o[1]) * (b_[0] - o[0])
        lo, hi = [], []
        for p in pts_:
            while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        for p in reversed(pts_):
            while len(hi) >= 2 and cr(hi[-2], hi[-1], p) <= 0:
                hi.pop()
            hi.append(p)
        outline = lo[:-1] + hi[:-1]
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    st = POCKET_STEP

    def edge_d(x, y):
        best = None
        for k in range(len(outline)):
            (ax, ay), (bx, by) = outline[k], outline[(k + 1) % len(outline)]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            d = math.hypot(x - ax - dx * t, y - ay - dy * t)
            best = d if best is None or d < best else best
        return best

    gmemo = {}

    def gz(x, y):
        k = (round(x), round(y))
        if k not in gmemo:
            gmemo[k] = mapdata.terrain_z(db, x, y)
        return gmemo[k]

    why = {}
    # (each street's line carried on from its end to the town's outline, as wide as the street is paved: the way in
    # behind a gate, the stretch before a castle's gate. Open ground to the lattice, and the trees "by the streets
    # first" stood one in the fort's gateway and one inside the town's gate; practice 2, 2026-11-11)
    ways = []
    for s_ in plan.get('streets') or ():
        sp_ = [tuple(p_) for p_ in s_.get('pts') or ()]
        if len(sp_) < 2:
            continue
        half = max(256.0, (s_.get('w') or 0) / 2.0 * 0.7) + POCKET_STEP / 2.0
        for a_, b_ in ((sp_[1], sp_[0]), (sp_[-2], sp_[-1])):
            dx, dy = b_[0] - a_[0], b_[1] - a_[1]
            h_ = math.hypot(dx, dy)
            if h_ < 1:
                continue
            ux, uy = dx / h_, dy / h_
            # (how far on the outline lies along the street's line)
            far = None
            for k in range(len(outline)):
                (px, py), (qx, qy) = outline[k], outline[(k + 1) % len(outline)]
                ex, ey = qx - px, qy - py
                den = ux * ey - uy * ex
                if abs(den) < 1e-9:
                    continue
                t_ = ((px - b_[0]) * ey - (py - b_[1]) * ex) / den
                u_ = ((px - b_[0]) * uy - (py - b_[1]) * ux) / den
                if t_ > 0 and 0.0 <= u_ <= 1.0 and (far is None or t_ < far):
                    far = t_
            if far is None or far > WAY_ON:
                continue
            nx, ny = -uy * half, ux * half
            e_ = (b_[0] + ux * (far + 64.0), b_[1] + uy * (far + 64.0))
            ways.append([(b_[0] + nx, b_[1] + ny), (e_[0] + nx, e_[1] + ny), (e_[0] - nx, e_[1] - ny), (b_[0] - nx, b_[1] - ny)])

    def ok(x, y, slope=POCKET_SLOPE):
        if not _inside(outline, x, y) or edge_d(x, y) < POCKET_IN:
            return False
        if ways and any(_inside(w_, x, y) for w_ in ways):
            why['way on'] = why.get('way on', 0) + 1
            return False
        z = gz(x, y)
        if z is None or z < 8:
            why['water'] = why.get('water', 0) + 1
            return False
        for dx, dy in ((st, 0), (0, st)):
            z2 = gz(x + dx, y + dy)
            if z2 is None or abs(z2 - z) / st > slope:
                why['steep'] = why.get('steep', 0) + 1
                return False
        r_ = _rect(x, y, 1.0, 0.0, st / 2.0, st / 2.0)
        if not space.free(r_, grows=True):
            if os.environ.get('POCKET_DEBUG'):
                if any(_overlap(r_, p_) for p_ in space.strict):
                    why['taken street'] = why.get('taken street', 0) + 1
                else:
                    for k_, p_ in enumerate(space.polys):
                        if _overlap(r_, p_):
                            ar = abs(sum(p_[i][0] * p_[(i + 1) % len(p_)][1] - p_[(i + 1) % len(p_)][0] * p_[i][1] for i in range(len(p_)))) / 2.0
                            kk = 'taken %s' % ('huge' if ar > 4e6 else 'big' if ar > 4e5 else 'mid' if ar > 4e4 else 'small')
                            why[kk] = why.get(kk, 0) + 1
                            break
            why['taken'] = why.get('taken', 0) + 1
            return False
        return True

    pts = set()
    for i in range(int(math.floor(min(xs) / st)), int(math.ceil(max(xs) / st)) + 1):
        for j in range(int(math.floor(min(ys) / st)), int(math.ceil(max(ys) / st)) + 1):
            if ok(i * st, j * st, TREE_SLOPE):
                pts.add((i, j))
    comps = []
    seen = set()
    for v in pts:
        if v in seen:
            continue
        c, stack = [], [v]
        seen.add(v)
        while stack:
            a = stack.pop()
            c.append(a)
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                w = (a[0] + d[0], a[1] + d[1])
                if w in pts and w not in seen:
                    seen.add(w)
                    stack.append(w)
        if len(c) >= POCKET_MIN:
            comps.append(c)
    comps.sort(key=len, reverse=True)
    built = [q for q in plan['plots'] if q.get('b') and q.get('rect')]
    streets = [tuple(p) for s_ in plan.get('streets') or () for p in s_.get('pts') or ()]

    def street_pt(x, y):
        return min(streets, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2) if streets else None

    gardens = 0
    g_cap = max(1, int(round(len(built) * POCKET_GARDENS * min(1.5, amount))))
    trees = []
    region_memo = {}
    out = {'pockets': len(comps), 'gardens': 0, 'pocket trees': 0, 'open points': len(pts), 'pocket sizes': [len(c) for c in comps[:6]], 'refused': dict(why)}
    for c in comps:
        cx = sum(a[0] for a in c) * st / len(c)
        cy = sum(a[1] for a in c) * st / len(c)
        region = _region_at(db, cx, cy, region_memo)
        cset = set(c)
        # 1. a garden: the biggest box the pocket holds, in the frame of its nearest house
        if gardens < g_cap and len(c) * st * st >= GARDEN_MIN[0] * GARDEN_MIN[1] and built:
            q = min(built, key=lambda q_: (sum(p[0] for p in q_['rect']) / 4.0 - cx) ** 2 + (sum(p[1] for p in q_['rect']) / 4.0 - cy) ** 2)
            f0 = q.get('face') or 0.0
            X = (math.cos(f0), -math.sin(f0))
            Y = (math.sin(f0), math.cos(f0))
            us = [a[0] * st * X[0] + a[1] * st * X[1] for a in c]
            vs = [a[0] * st * Y[0] + a[1] * st * Y[1] for a in c]
            u0, v0 = min(us) - st, min(vs) - st
            W, H = int((max(us) - u0) / st) + 2, int((max(vs) - v0) / st) + 2
            grid = []
            for vv in range(H):
                row = []
                for uu in range(W):
                    u, v = u0 + uu * st, v0 + vv * st
                    x, y = X[0] * u + Y[0] * v, X[1] * u + Y[1] * v
                    near = (int(round(x / st)), int(round(y / st)))
                    row.append(near in cset and ok(x, y))
                grid.append(row)
            R = _max_rect(grid, W, H)
            why.setdefault('garden boxes', []).append(None if not R else ((R[2] - R[0] + 1) * st - 2 * GARDEN_EDGE, (R[3] - R[1] + 1) * st - 2 * GARDEN_EDGE))
            if R:
                # (a run of n lattice points holds n steps of ground: half a step past each end point)
                w = (R[2] - R[0] + 1) * st - 2 * GARDEN_EDGE
                d = (R[3] - R[1] + 1) * st - 2 * GARDEN_EDGE
                if max(w, d) >= GARDEN_MIN[0] and min(w, d) >= GARDEN_MIN[1]:
                    um, vm = u0 + (R[0] + R[2]) / 2.0 * st, v0 + (R[1] + R[3]) / 2.0 * st
                    gx, gy = X[0] * um + Y[0] * vm, X[1] * um + Y[1] * vm
                    w, d = min(w, GARDEN_MAX[0] if w >= d else GARDEN_MAX[1]), min(d, GARDEN_MAX[0] if d > w else GARDEN_MAX[1])
                    # (its gate toward the nearest street: of the frame's four ways, the one nearest it; the box's
                    # across and deep follow the way turned)
                    sp = street_pt(gx, gy)
                    face, gw, gd = f0, w, d
                    if sp:
                        want = math.atan2(sp[0] - gx, sp[1] - gy)
                        best = None
                        for k in range(4):
                            fk = f0 + k * math.pi / 2
                            diff = abs((want - fk + math.pi) % (2 * math.pi) - math.pi)
                            if best is None or diff < best[0]:
                                best = (diff, fk, w if k % 2 == 0 else d, d if k % 2 == 0 else w)
                        _df, face, gw, gd = best
                    laid = farm(db, gx, gy, face, gw, gd, cult, region=region, seed=rng.randrange(1 << 30), space=space, memo=memo)
                    why.setdefault('garden crops', []).append(sum(1 for t in laid if t.get('role') == 'crop'))
                    if sum(1 for t in laid if t.get('role') == 'crop') >= 4:
                        gardens += 1
                        add([(t['id'], t['p'], t['s'], 'garden ' + t.get('role', 'crop')) for t in laid], 'garden')
                        space.take(_rect(gx, gy, X[0], X[1], (R[2] - R[0] + 1) * st / 2.0, (R[3] - R[1] + 1) * st / 2.0))
                        cset = {a for a in cset if ok(a[0] * st, a[1] * st, TREE_SLOPE)}
    # 2. trees on the open ground left, in the pockets and in the gaps too small to be one, those by a street first:
    # big shade trees of the land's own kinds where it grows them, a yard's small kinds among them. (The user set eight
    # such by hand in a town the maker had given saplings, 2026-11-13: "with the space where no buildings or roads are,
    # tastefully inserting trees according to some slider would be a nice touch". As many as the open ground holds at
    # one a POCKET_TREE_AREA, OPEN_TREES a building at least, times the town's own amount.)
    left = [a for a in sorted(pts) if ok(a[0] * st, a[1] * st, TREE_SLOPE)] if trees_k > 0 else []
    want_n = int(max(len(left) * st * st / POCKET_TREE_AREA, OPEN_TREES * len(built)) * min(1.5, amount) * trees_k + rng.random()) if left else 0
    cand = sorted(left, key=lambda a: (0 if streets and min((p[0] - a[0] * st) ** 2 + (p[1] - a[1] * st) ** 2 for p in streets) < POCKET_STREET ** 2 else 1, rng.random()))
    got = 0
    shade_n = 0
    # (closer together as the town's amount rises: a grove at 2, where the gap at 1 alone held the count)
    gap = POCKET_TREE_GAP / math.sqrt(max(1.0, min(1.5, amount) * trees_k))
    for a in cand:
        if got >= want_n:
            break
        x, y = a[0] * st + (rng.random() - 0.5) * st * 0.6, a[1] * st + (rng.random() - 0.5) * st * 0.6
        if any(math.hypot(x - tx, y - ty) < gap for tx, ty in trees):
            why['tree: by another'] = why.get('tree: by another', 0) + 1
            continue
        region = _region_at(db, x, y, region_memo)
        tp = pool('house_trees', region)
        shade = _shade_trees(db, region, x, y, memo)
        rid, big = None, False
        if shade and (not tp or rng.random() < SHADE_SHARE):
            rid, big = _draw(rng, shade), True
        if not rid and tp:
            rid = _pick(db, rng, tp)
        bb = _bounds(db, memo, rid) if rid else None
        if not bb:
            continue
        crown = max(bb[3] - bb[0], bb[4] - bb[1])
        room = min(TREE_ROOM_MOST, max(TREE_TRUNK, 0.3 * crown, TREE_MIN_D))
        if not space.free(_rect(x, y, 1.0, 0.0, room, room), grows=True):
            why['tree: no room'] = why.get('tree: no room', 0) + 1
            continue
        sc = round(rng.uniform(0.9, 1.15), 3)
        z = _ground_z(db, bb, x, y, sc)
        if z is None:
            continue
        space.take(_rect(x, y, 1.0, 0.0, TREE_TRUNK, TREE_TRUNK))
        add([(rid, (x, y, z, 0.0, 0.0, rng.uniform(0, 2 * math.pi)), sc)], 'tree')
        trees.append((x, y))
        got += 1
        shade_n += big
    out['shade trees'] = shade_n
    out['tree spots'] = len(left)
    # 3. the small growth of the region's own land on the open ground left by the houses, in tufts of a kind
    try:
        def on_land(x, y):
            if not _inside(outline, x, y) or edge_d(x, y) < POCKET_IN / 2.0:
                return False
            if ways and any(_inside(w_, x, y) for w_ in ways):
                return False                  # (nor the small growth on a street's way on to the wall)
            z = gz(x, y)
            return z is not None and all((lambda z2: z2 is not None and abs(z2 - z) / 64.0 <= TREE_SLOPE)(gz(x + dx, y + dy)) for dx, dy in ((64.0, 0.0), (0.0, 64.0)))
        out['undergrowth'] = _undergrowth(db, plan, space, memo, rng, cult, add, amount, built, on_land)
    except Exception as e_:
        why['undergrowth: %s' % e_] = 1
    out['gardens'] = gardens
    out['pocket trees'] = len(trees)
    out['refused'] = dict(why)
    return out


def _shade_trees(db, region, x, y, memo):
    """{id: weight}: the big trees for a town's open ground: the wild trees SHADE_TALL or taller of the region's own
    land, else of its plant home's, else of the nearest lands that grow such. Empty where none grows near."""
    key = (id(db.recs), region)
    if key in _SHADE:
        return _SHADE[key]
    V = _variants(db)

    def tall_of(reg):
        out = {}
        for base, n in (_wild_kinds(db, reg, 'trees') or {}).items():
            ids = [rid for rid in V.get(base) or () if (lambda bb: bb and bb[5] - bb[2] >= SHADE_TALL)(_bounds(db, memo, rid))]
            for rid in ids:
                out[rid] = out.get(rid, 0.0) + n / float(len(ids))
        return out
    regs = [region] if region else []
    home = _plant_home(db, region)
    if home and home not in regs:
        regs.append(home)
    try:
        import landdecor
        regs += [r for r in landdecor.nearest_lands(db, math.floor(x / 8192.0), math.floor(y / 8192.0), lambda r: True, 8) if r not in regs]
    except Exception:
        pass
    out = {}
    for reg in regs:
        out = tall_of(reg)
        if out:
            break
    _SHADE[key] = out
    return out


def _wild_small(db, x, y):
    """[(id, dz, rx, ry, s)]: the small things growing wild in the region at a spot (landdecor's squares: plants,
    grass, logs, no trees), each as the game laid it; the nearest land's where the region has little of its own."""
    import landdecor
    gx, gy = math.floor(x / 8192.0), math.floor(y / 8192.0)
    regs = [_region_at(db, x, y, {})]
    home = _plant_home(db, regs[0])
    if home and home not in regs:
        regs.append(home)                      # (the same region the beds and trees are of, before the nearest land's)
    try:
        regs += [r for r in landdecor.nearest_lands(db, gx, gy, lambda r: landdecor._broad(db, r) and landdecor._grows(db, r) >= landdecor.ENOUGH, 6) if r not in regs]
    except Exception:
        pass
    for reg in regs:
        # (a region of stand-in trees alone, the continent's unmade land, has no small growth: the next land's then)
        out = []
        for sqs in landdecor.learn(db, reg)['squares'].values():
            for sq in sqs:
                for it in sq:
                    low = it[0].lower()
                    if not low.startswith('dlt_') and landdecor.kind_of(low) in ('plants', 'grass', 'logs') and it[3] <= landdecor.LIFTED and db.resolve_id(it[0]) is not None:
                        out.append((it[0], it[3], it[4], it[5], it[7]))
        if len(out) >= WILD_MIN:
            return out
    return []


def _undergrowth(db, plan, space, memo, rng, cult, add, amount, built, on_land):
    """The count laid: UNDER a building of the region's small wild growth on the free ground within UNDER_REACH of the
    buildings, each in its turn, in tufts of one kind (1 to 4 together); never on a street or a door's way.
    on_land(x, y): the town's own ground, not too steep."""
    want = int(round(len(built) * UNDER.get(cult, UNDER_ELSE) * min(1.5, amount)))
    if want <= 0 or not built:
        return 0
    mids = []
    for q in built:
        mx, my = sum(p[0] for p in q['rect']) / 4.0, sum(p[1] for p in q['rect']) / 4.0
        mids.append((mx, my, max(math.hypot(p[0] - mx, p[1] - my) for p in q['rect'])))
    wild = _wild_small(db, sum(m[0] for m in mids) / len(mids), sum(m[1] for m in mids) / len(mids))
    if not wild:
        return 0
    got = tries = 0
    while got < want and tries < want * 14:
        mx, my, rad = mids[tries % len(mids)]
        tries += 1
        rid = rng.choice(wild)[0]
        same = [w for w in wild if w[0] == rid]
        bb = _bounds(db, memo, rid)
        if not bb:
            continue
        half = max(UNDER_ROOM, min(60.0, 0.25 * max(bb[3] - bb[0], bb[4] - bb[1])))
        ang, r = rng.uniform(0, 2 * math.pi), rng.uniform(0.5 * rad, min(UNDER_REACH, rad + 420.0))
        x0, y0 = mx + r * math.cos(ang), my + r * math.sin(ang)
        if not on_land(x0, y0):
            continue
        for k in range(rng.choice((1, 1, 2, 2, 3, 4))):
            ang, r = rng.uniform(0, 2 * math.pi), (0.0 if k == 0 else rng.uniform(2.2, 4.5) * half)
            x, y = x0 + r * math.cos(ang), y0 + r * math.sin(ang)
            box = _rect(x, y, 1.0, 0.0, half, half)
            g = mapdata.terrain_z(db, x, y)
            if g is None or g < 8 or not on_land(x, y) or not space.free(box, grows=True):
                continue
            _r, dz, rx, ry, s = rng.choice(same)
            space.take(box)
            add([(rid, (x, y, g + dz, rx, ry, rng.uniform(0, 2 * math.pi)), s)], 'wild')
            got += 1
    return got


# ------------------------------------------------------------------ farms and orchards on the land
# (no home in the Workshop's UI yet: a Land panel shape kind 'farm' / 'orchard' drawn as an outline, with the culture
# picked as for a town, would call lay_field. See the 2.6.12-test8 notes.)

def _field_frame(pts):
    """A drawn outline as a field: its centre, the facing of its longest edge (the near edge, where the gate is), and
    its width across and depth along that facing."""
    n = len(pts)
    cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    best = None
    for k in range(n):
        a, b = pts[k], pts[(k + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if best is None or L > best[0]:
            best = (L, a, b)
    _L, a, b = best
    dx, dy = _unit(b[0] - a[0], b[1] - a[1])
    # (the near edge's outward normal points away from the centre)
    nx, ny = -dy, dx
    if (cx - a[0]) * nx + (cy - a[1]) * ny > 0:
        nx, ny = -nx, -ny
    face = math.atan2(nx, ny)
    X, Y = (dx, dy), (-nx, -ny)
    xs = [(p[0] - cx) * X[0] + (p[1] - cy) * X[1] for p in pts]
    ys = [(p[0] - cx) * Y[0] + (p[1] - cy) * Y[1] for p in pts]
    return cx, cy, face, (max(xs) - min(xs)), (max(ys) - min(ys))


def farm(db, cx, cy, face, w, d, culture, region=None, seed=1, space=None, memo=None, fence=True):
    """A farm plot w across and d deep whose near edge faces `face` (the gate side): furrows of one of the region's
    own crops (the game's farms of the region, else the culture's) at the game's row and plant spacing, turned as
    unevenly as the game's, a path through the middle of a wide field, and the culture's farm fence round it with
    the gate's way left open in the near edge. [{'id', 'p', 's', 'role'}]."""
    rng = random.Random('%s|farm|%s' % (seed, culture))
    memo = memo if memo is not None else {}
    space = space or _Space([])
    region = region or _region_at(db, cx, cy, {})
    fx, fy = math.sin(face), math.cos(face)
    Y = (-fx, -fy)
    X = (Y[1], -Y[0])
    crop_cult = 'Dunmer' if culture in ('Hlaalu', 'Velothi', 'Redoran', 'Dunmer common', 'Dunmer', 'Indoril', 'Mournhold', 'Telvanni', 'Ashlander') \
        else 'Nord' if culture in ('Nordic', 'Reach') else culture
    pool = _species(db, 'fields', region, culture, fallback=CROPS.get(crop_cult) or CROPS['Imperial'])
    fig = _fig(db, 'farms', culture, region)
    out = []
    if fence:
        FF = FARM_FENCES.get(culture) or FARM_FENCES.get(FENCE_KIN.get(culture, '')) or FENCES.get(culture) or FENCES.get(FENCE_KIN.get(culture, ''))
        if FF:
            hx, hy = w / 2.0, d / 2.0
            c = lambda lx, ly: (cx + X[0] * lx + Y[0] * ly, cy + X[1] * lx + Y[1] * ly)
            # (the near edge from left to right has the gate's way in its middle)
            edges = [(c(-hx, -hy), c(hx, -hy), (Y[0], Y[1]), (w / 2.0 - 130, w / 2.0 + 130)), (c(hx, -hy), c(hx, hy), (-X[0], -X[1]), None),
                     (c(hx, hy), c(-hx, hy), (-Y[0], -Y[1]), None), (c(-hx, hy), c(-hx, -hy), (X[0], X[1]), None)]
            for a, b, inward, gap in edges:
                for rid, p, s in _fence_run(db, space, memo, FF, a, b, inward, gap_at=gap):
                    out.append({'id': rid, 'p': [round(v, 4) if i >= 3 else round(v, 2) for i, v in enumerate(p)], 's': s, 'role': 'fence'})
    # (the game's fields are small: 5 to 16 plants, 2 rows of 3 or 4 at the median, 500 long and 200 across. A plot
    # drawn bigger is worked as several such fields side by side and end to end, a path between them)
    V = _variants(db)
    base = _draw(rng, pool)
    inner_w, inner_d = max(120.0, w - 140), max(120.0, d - 150)
    PATH = 160
    y = -d / 2.0 + 70
    while y < d / 2.0 - 120:
        # (the in-row gap no wider than a third of the plot's depth: three plants a row at the least, whatever the
        # game's gap for a shallow plot; a 600-deep Redoran plot got fences and no crop)
        in_gap = min(_pct(rng, fig.get('in_gap'), 60, 230), inner_d / 2.6)
        per = max(3, int(round(_pct(rng, fig.get('per_row'), 3, 11))))
        fl = min(inner_d, per * in_gap)
        if y + fl > d / 2.0 - 60:
            fl = d / 2.0 - 60 - y
        if fl < 2.0 * in_gap:
            break
        x = -inner_w / 2.0
        while x < inner_w / 2.0 - 80:
            row_gap = _pct(rng, fig.get('row_gap'), 90, 220)
            nrows = max(1, int(round(_pct(rng, fig.get('rows'), 1, 4))))
            fw = min(inner_w, nrows * row_gap)
            if x + fw > inner_w / 2.0:
                fw = inner_w / 2.0 - x
            if fw < 0.9 * row_gap:
                break
            # (one crop a field; a neighbouring field the same crop two times in three)
            fpool = pool if rng.random() < 0.35 else ({base: 1} if base and V.get(base) else pool)
            ox, oy = cx + X[0] * (x + fw / 2.0) + Y[0] * y, cy + X[1] * (x + fw / 2.0) + Y[1] * y
            rows = _crop_rows(db, space, memo, rng, fpool, ox, oy, X, Y, fw, fl, fig, path=False, gaps=(row_gap, in_gap))
            for rid, p_, s_ in rows:
                out.append({'id': rid, 'p': [round(v, 4) if i >= 3 else round(v, 2) for i, v in enumerate(p_)], 's': s_, 'role': 'crop'})
            x += fw + PATH
        y += fl + PATH
    return out


def fruit_trees(db, region, culture, cx=None, cy=None):
    """{kind-name: n} of the fruit trees an orchard grows here, of those this load order has: the region's own
    orchards' trees, else those of the region whose plants grow on its land (_plant_home), else the culture's
    orchards', else those of the region with orchards nearest on the map. Fruit trees only, {} when the game has
    none: an orchard of the trees by the region's houses was 37 Zifa trees, which bear nothing (2026-11-13)."""
    V = _variants(db)
    try:
        import gardensurvey
        O = (gardensurvey.outdoor_ready(db) or {}).get('orchards') or {}
    except Exception:
        O = {}
    by = O.get('trees_by_region') or {}
    have = lambda d: {b: n for b, n in (d or {}).items() if V.get(b)}
    r = (region or '').lower()
    got = have(by.get(r))
    if not got:
        home = _plant_home(db, r)
        got = have(by.get(home)) if home != r else {}
    if not got:
        # (the culture's orchards, where its towns have any: every Dunmer region took the one orchard tree of one
        # far-off region before)
        got = have(((O.get('by_culture') or {}).get(culture) or {}).get('kinds'))
    if not got and cx is not None:
        try:
            import landregion
            C = {k.lower(): v for k, v in landregion._centres(db).items()}
            gx, gy = cx / 8192.0, cy / 8192.0
            for _d, k in sorted((math.hypot(C[k][0] - gx, C[k][1] - gy), k) for k in by if k in C):
                got = have(by[k])
                if got:
                    break
        except Exception as e:
            print('orchard: the nearest region with fruit trees:', e)
    return got or have((O.get('all') or {}).get('kinds'))


def orchard(db, cx, cy, face, w, d, culture, region=None, seed=1, space=None, memo=None):
    """An orchard w across and d deep: a loose grid of one kind of fruit tree (fruit_trees) at the game's orchard
    spacing, each tree a little off its mark and turned at random, as unevenly spaced as the game's. [] where the
    load order has no fruit tree. [{'id', 'p', 's', 'role'}]."""
    rng = random.Random('%s|orchard|%s' % (seed, culture))
    memo = memo if memo is not None else {}
    space = space or _Space([])
    region = region or _region_at(db, cx, cy, {})
    fx, fy = math.sin(face), math.cos(face)
    Y = (-fx, -fy)
    X = (Y[1], -Y[0])
    V = _variants(db)
    pool = fruit_trees(db, region, culture, cx, cy)
    base = _draw(rng, pool)
    if not base or not V.get(base):
        return []
    ids = V[base]
    bb0 = _bounds(db, memo, ids[0])
    tw = max(bb0[3] - bb0[0], bb0[4] - bb0[1]) if bb0 else 300
    fig = _fig(db, 'orchards', culture, region)
    nn = _pct(rng, fig.get('nn'), max(120.0, tw * 0.6), 420)
    cv = _pct(rng, fig.get('cv'), 0.1, 0.8)
    cols = max(1, int(w // nn))
    rows = max(1, int(d // nn))
    out = []
    x0, y0 = -(cols - 1) * nn / 2.0, -(rows - 1) * nn / 2.0
    for r in range(rows):
        for k in range(cols):
            if rng.random() < 0.15:
                continue                      # (a gap in the grid: the game's orchards are loose)
            lx = x0 + k * nn + rng.gauss(0, nn * cv * 0.7)
            ly = y0 + r * nn + rng.gauss(0, nn * cv * 0.7)
            wx, wy = cx + X[0] * lx + Y[0] * ly, cy + X[1] * lx + Y[1] * ly
            rid = rng.choice(ids)
            bb = _bounds(db, memo, rid)
            rect = _rect(wx, wy, X[0], X[1], TREE_TRUNK, TREE_TRUNK)
            s = round(rng.uniform(0.88, 1.15), 3)
            z = _ground_z(db, bb, wx, wy, s)
            if z is None or not space.free(rect):
                continue
            space.take(rect)
            out.append({'id': rid, 'p': [round(wx, 2), round(wy, 2), round(z, 2), 0.0, 0.0, round(rng.uniform(0, 2 * math.pi), 4)], 's': s, 'role': 'tree'})
    return out


def _clear_field(db, pts, cells, pad=150.0):
    """The land's own trees, plants and rocks (another plugin's) standing inside the outline, or within pad of it,
    taken out (deleted in the mod): a field is cleared land. Returns how many."""
    import cliffrocks
    import editing
    import landdecor
    from project import ref_info
    mine = db.project.plugin.lower()
    n = 0
    for ck in cells:
        try:
            refs, _h = db.cell_refs(ck)
        except Exception:
            continue
        c = None
        for rk, ref in refs.items():
            rid, pos, _s, dead = ref_info(ref['subs'])
            if dead or not rid or ref.get('origin') == mine:
                continue
            low = rid.lower()
            if not (landdecor.kind_of(low) or cliffrocks.is_rock(low)):
                continue
            x, y = pos[0], pos[1]
            if not (_inside(pts, x, y) or min(math.hypot(x - a[0], y - a[1]) for a in pts) < pad):
                continue
            if c is None:
                c, _r = editing._cell(db, ck)
            editing._store(c, rk, ref['origin'], ref['idx'], ref['subs'], deleted=True)
            n += 1
    if n:
        db.sync_project()
    return n


def field_culture(db, pts):
    """The culture of the mod's own made town a field lies beside (the nearest whose outline is within FIELD_TOWN of
    the field's middle), '' where there is none: a farm under a Dunmer town of the mod's was laid as the nearest game
    town's, a Redoran one a long way off (2026-11-13)."""
    pts = [(float(p[0]), float(p[1])) for p in (pts or [])]
    if len(pts) < 3:
        return ''
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    def seg(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L <= 0 else max(0.0, min(1.0, ((cx - a[0]) * dx + (cy - a[1]) * dy) / L))
        return math.hypot(a[0] + dx * t - cx, a[1] + dy * t - cy)
    best = None
    for rec in (getattr(db.project, 'places', None) or {}).values():
        o = rec.get('outline') or []
        c = (rec.get('opts') or {}).get('culture')
        if rec.get('kind') != 'town' or len(o) < 3 or not c:
            continue
        dist = 0.0 if _inside(o, cx, cy) else min(seg(o[k], o[(k + 1) % len(o)]) for k in range(len(o)))
        if dist <= FIELD_TOWN and (best is None or dist < best[0]):
            best = (dist, c)
    return best[1] if best else ''


def lay_field(db, pts, culture, what='farm', seed=None, commit=True, clear=False):
    """A farm or an orchard on an outline drawn on the map (world points, three or more): the outline's longest edge
    is the near side (the gate's), and the field fills the outline's box in that frame. Placed into the mod as one
    Undo step. {'things', 'plants', 'kind', 'seed'}. clear: the land's own trees, plants and rocks in it taken out
    first, and only what is built keeps the field off (Tamriel.esm's trees stand 1,700 across by their bounds: a
    proposed farm among them laid nothing, 2026-11-08)."""
    import editing
    import cliffrocks
    editing._require_project(db)
    pts = [(float(p[0]), float(p[1])) for p in (pts or [])]
    if len(pts) < 3:
        raise editing.EditError('Draw the field as an outline first.')
    seed = int(seed) if seed is not None else random.randrange(1, 1 << 30)
    cx, cy, face, w, d = _field_frame(pts)
    if w < 200 or d < 200:
        raise editing.EditError('That outline is too small for a field.')
    # (round what stands there already: an orchard went through a ruin's pillars, the 3D look of 2026-11-05)
    cells = {'#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0)) for x, y in pts} | {'#%d,%d' % (math.floor(cx / 8192.0), math.floor(cy / 8192.0))}
    cleared = _clear_field(db, pts, cells) if clear else 0
    st = _standing(db, None, {}, cells)
    if clear:
        st = _standing_built(db, cells)
    space = _Space(st)
    if what != 'farm' and not fruit_trees(db, _region_at(db, cx, cy, {}), culture, cx, cy):
        raise editing.EditError('This load order has no fruit trees to make an orchard of.')
    items = (farm if what == 'farm' else orchard)(db, cx, cy, face, w, d, culture, seed=seed, space=space)
    # (only within the outline itself, not its box's corners)
    items = [it for it in items if _inside(pts, it['p'][0], it['p'][1]) or it['role'] == 'fence']
    placed = cliffrocks.place(db, [{'id': it['id'], 'x': it['p'][0], 'y': it['p'][1], 'z': it['p'][2], 'rx': it['p'][3], 'ry': it['p'][4], 'rz': it['p'][5], 's': it['s']} for it in items])
    db.sync_project()
    plants = sum(1 for it in items if it['role'] in ('crop', 'tree'))
    if commit and (placed or cleared):
        editing.commit(db, 'Laid %s of %d %s' % ('a farm' if what == 'farm' else 'an orchard', plants, 'plants' if what == 'farm' else 'trees'))
    return {'things': placed, 'plants': plants, 'kind': what, 'seed': seed, 'cleared': cleared}


def _standing_built(db, cells):
    """As _standing, but only what is built: not the land's trees, plants and rocks."""
    import cliffrocks
    import landdecor
    out = []
    for ck in cells:
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        for r in m.get('refs') or ():
            if r.get('mine') or not r.get('b') or r['type'] not in ('STAT', 'ACTI', 'CONT'):
                continue
            low = r['id'].lower()
            if landdecor.kind_of(low) or cliffrocks.is_rock(low) or 'marker' in low:
                continue
            s = r.get('s') or 1.0
            b = r['b']
            if max(b[3] - b[0], b[4] - b[1]) * s < STANDING:
                continue
            out.append(_footprint(b, r['p'][0], r['p'][1], r['p'][5], s, 0.0))
    return out


# ------------------------------------------------------------------ the fort's yard
# roles for the wall's stretches and the yard's middle, as sets in a frame: x along the wall (or across the yard),
# y into the yard from the wall, z over the ground. Alternatives for a piece are tried in order (the first the load
# order has is used)
FORT_SETS = {
    'smithy': {'back': 460, 'things': [(('furn_s_forge', 'furn_de_forge_01'), 0, 60, 0, 0.0), (('furn_anvil00',), -140, 170, 0, 1.2),
                                       (('furn_de_bellows_01',), 110, 80, 0, 0.0), (('barrel_01',), -230, 50, 0, 0.3),
                                       (('t_imp_furnp_grindstone_01',), 230, 150, 0, 2.6), (('crate_01',), -300, 70, 0, 0.0),
                                       (('misc_com_bucket_01',), 60, 200, 0, 0.0)]},
    'stables': {'back': 430, 'things': [(('t_com_setfarm_haypile_01',), -260, 70, 0, 0.0), (('t_com_setfarm_haybale_01',), -110, 50, 0, 0.4),
                                        (('t_com_setfarm_haybale_01',), -104, 54, 64, 1.9), (('t_imp_setfarm_foodtrough_01',), 110, 90, 0, 1.5708),
                                        (('barrel_01',), 260, 50, 0, 0.0), (('com_sack_01',), 300, 90, 0, 0.7), (('misc_com_bucket_01',), 180, 170, 0, 0.0)]},
    'stores': {'back': 420, 'things': [(('crate_01',), -140, 50, 0, 0.0), (('crate_02',), -140, 50, 64, 0.4), (('crate_01',), -70, 55, 0, 0.1),
                                       (('crate_02',), 10, 50, 0, 0.0), (('barrel_01',), 90, 45, 0, 0.0), (('barrel_02',), 150, 50, 0, 0.9),
                                       (('com_sack_02',), 220, 60, 0, 0.0), (('com_basket_01',), -210, 70, 0, 0.0),
                                       (('t_com_furn_wheelbarrow_01',), -290, 180, 0, 0.6)]},
    'shrine': {'back': 400, 'things': [(('furn_imp_altar_01', 'furn_velothi_altar_01'), 0, 50, 0, 0.0),
                                       (('light_com_candle_01', 'light_com_candle_02', 'light_de_candle_01'), -90, 40, 0, 0.0),
                                       (('light_com_candle_01', 'light_com_candle_02', 'light_de_candle_01'), 90, 40, 0, 0.0)]},
    'drill': {'back': None, 'things': [(('furn_practice_dummy', 't_com_furn_practicedummy'), -160, 0, 0, 0.0),
                                       (('furn_practice_dummy', 't_com_furn_practicedummy'), 160, 40, 0, 0.5),
                                       (('t_com_furn_target_01', 't_de_furn_target_01'), 0, 330, 0, 3.1416),
                                       (('t_com_furn_target_02', 't_com_furn_target_01'), 120, 350, 0, 3.1416)]},
}
BRAZIERS = ('light_com_brazier_01', 'light_imp_brazier_01', 'light_brazier_01', 'light_com_brazier', 'light_de_brazier_01', 'light_dae_brazier00')
GATE_SET_OFF = 1000            # the smithy this far along the wall from the gate (clear of the gatehouse's towers)
CORNER_IN = 560                # a brazier this far in from a yard corner (clear of the corner tower and the wall's pads)
FORT_LAST = {}


def fort(db, poly, gate, keep, free, taken, rng, style='Imperial'):
    """Sets with a job for a fort's yard: the smithy by the gate, the stables on the longest blank stretch, the stores
    and a shrine on the others, a drill ring in the middle, braziers in the corners. poly: the wall's outline (the
    yard); gate, keep: (x, y); free(x, y, r): ground not taken; taken: the castle's list to add ('disc', (x, y), r)
    to. [(id, (x, y, z, 0, 0, rz), s)]."""
    n = len(poly)
    if n < 3:
        return []
    memo = {}
    cx0, cy0 = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n

    def seg_d(px, py, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        return math.hypot(px - a[0] - dx * t, py - a[1] - dy * t), t * math.sqrt(L2)
    edges = []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        d = _unit(b[0] - a[0], b[1] - a[1])
        nrm = (-d[1], d[0])
        if (cx0 - a[0]) * nrm[0] + (cy0 - a[1]) * nrm[1] < 0:
            nrm = (-nrm[0], -nrm[1])
        edges.append({'a': a, 'b': b, 'd': d, 'n': nrm, 'L': math.hypot(b[0] - a[0], b[1] - a[1]),
                      'gate': seg_d(gate[0], gate[1], a, b), 'keep': seg_d(keep[0], keep[1], a, b)})
    gate_e = min(edges, key=lambda e: e['gate'][0])
    keep_e = min(edges, key=lambda e: e['keep'][0])
    rest = sorted((e for e in edges if e is not gate_e and e is not keep_e), key=lambda e: -e['L'])
    plan = []
    # (the smithy along the gate's wall, a way in from the gate; the stables, stores and shrine on the other walls,
    # longest first)
    t_g = gate_e['gate'][1]
    for t_s in (t_g + GATE_SET_OFF, t_g - GATE_SET_OFF):
        if 300 < t_s < gate_e['L'] - 300:
            plan.append(('smithy', gate_e, t_s))
            break
    for role, e in zip(('stables', 'stores'), rest):
        plan.append((role, e, e['L'] * rng.uniform(0.35, 0.65)))
    # (the shrine beside the keep, on its wall: a four-sided yard has only two free walls)
    t_k = keep_e['keep'][1]
    for t_s in (t_k + 900, t_k - 900):
        if 300 < t_s < keep_e['L'] - 300:
            plan.append(('shrine', keep_e, t_s))
            break
    out = []
    laid_roles = []
    tries = {}

    def fit(role, ox, oy, X, Y):
        # (the set's things on free ground at this spot: what fits, of how many)
        S_ = FORT_SETS[role]
        placed, discs = [], []
        rz0 = math.atan2(Y[0], Y[1])
        want = 0
        for alts, lx, ly, dz, rz in S_['things']:
            rid = _first(db, *alts)
            if not rid:
                continue
            want += 1
            bb = _bounds(db, memo, rid)
            wx, wy = ox + X[0] * lx + Y[0] * ly, oy + X[1] * lx + Y[1] * ly
            r = max(THING, (bb[3] - bb[0]) / 2.0 if bb else THING, (bb[4] - bb[1]) / 2.0 if bb else THING)
            # (against each other by their own sizes, a little closer than touching: the set is laid out packed on
            # purpose, and a stacked thing (dz) sits on the one under it)
            own = 0.45 * min((bb[3] - bb[0]), (bb[4] - bb[1])) if bb else THING * 0.6
            g = _ground_z(db, bb, wx, wy, rid=rid)
            if g is None or not free(wx, wy, r) or (dz <= 0 and any(math.hypot(wx - q[0], wy - q[1]) < own + q[3] for q in discs)):
                continue
            placed.append((rid, (wx, wy, g + dz, 0.0, 0.0, (rz + rz0) % (2 * math.pi)), 1.0))
            discs.append((wx, wy, r, own))
        return placed, discs, want

    def commit(role, placed, discs):
        out.extend(placed)
        for wx, wy, r, _own in discs:
            taken.append(('disc', (wx, wy), r))
        laid_roles.append(role)

    def lay(role, ox, oy, X, Y):
        placed, discs, want = fit(role, ox, oy, X, Y)
        if not want or len(placed) < 0.5 * want:
            return False
        commit(role, placed, discs)
        return True

    for role, e, t in plan:
        S_ = FORT_SETS[role]
        Y = e['n']
        X = (Y[1], -Y[0])
        # (the spot along the wall nearest the one asked for where most of the set fits: the wall's towers stand every
        # few lengths, and a set tried at one spot usually straddled one)
        spots = sorted((t_ for t_ in range(300, int(e['L']) - 300, 200)), key=lambda t_: abs(t_ - t))
        best = None
        most = (0, 0)
        for t_ in spots[:14]:
            ox, oy = e['a'][0] + e['d'][0] * t_ + Y[0] * S_['back'], e['a'][1] + e['d'][1] * t_ + Y[1] * S_['back']
            placed, discs, want = fit(role, ox, oy, X, Y)
            most = max(most, (len(placed), want))
            if want and len(placed) >= 0.5 * want and (best is None or len(placed) > len(best[0])):
                best = (placed, discs)
                if len(placed) == want:
                    break
        tries[role] = '%d of %d at best' % most
        if best:
            commit(role, best[0], best[1])
    # the drill ring: in the yard's middle, to one side of the way from the gate to the keep
    gk = _unit(keep[0] - gate[0], keep[1] - gate[1])
    side = (-gk[1], gk[0])
    for s in (1, -1):
        ox, oy = cx0 + side[0] * s * 700, cy0 + side[1] * s * 700
        if lay('drill', ox, oy, (gk[1], -gk[0]), gk):
            break
    # braziers in the corners
    br = _first(db, *BRAZIERS)
    if br:
        bb = _bounds(db, memo, br)
        for k in range(n):
            p = poly[k]
            prev, nxt = poly[k - 1], poly[(k + 1) % n]
            u1 = _unit(prev[0] - p[0], prev[1] - p[1])
            u2 = _unit(nxt[0] - p[0], nxt[1] - p[1])
            bis = _unit(u1[0] + u2[0], u1[1] + u2[1])
            wx, wy = p[0] + bis[0] * CORNER_IN, p[1] + bis[1] * CORNER_IN
            g = _ground_z(db, bb, wx, wy)
            if g is not None and free(wx, wy, 60):
                out.append((br, (wx, wy, g, 0.0, 0.0, 0.0), 1.0))
                taken.append(('disc', (wx, wy), 60.0))
                laid_roles.append('brazier')
    FORT_LAST.clear()
    FORT_LAST['roles'] = laid_roles
    FORT_LAST['things'] = len(out)
    FORT_LAST['tries'] = tries
    return out
