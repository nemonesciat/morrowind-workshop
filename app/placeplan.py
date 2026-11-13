"""Places for shaped land (docs/terrain-tools-research-2026-11.md, P10): towns, villages and dungeons proposed at the
game's rates and on the ground the game puts them, as layers of the land plan for the user to move, drop or keep
before anything is built. Towns are the plan's own town layers (built by Shape, then build, as any drawn town);
dungeons are one-point 'dungeon' layers, built with the dungeon generator (dwemer.build) by Build the dungeons.

What the game does (lab a11, 2026-11-08, Vvardenfell and TR's 2,552 hand-made land cells, the doors into interiors
clustered within 1,024 and named by kind, and townsurvey's 149 towns), a hundred land cells: 20 caves, 9 tombs,
2.8 Daedric ruins, 2.4 Dwemer ruins, 1.5 towers, 0.8 forts; 2.3 villages, 1.7 towns, 0.4 cities. Where: LIFT, the
share of a kind's places in each band of five features over the share of all land in it, on the 512 grid:

  z       height                                  (villages and towns low, Dwemer ruins high)
  slope   over 1,024                              (settlements on the flat, caves and tombs on 20-40 degrees,
                                                   Dwemer on the steepest)
  tpi     height over the mean within 2,048       (caves and tombs in hollows 3-4 times as often as the land is)
  coast   distance to the sea                     (towns and cities near it)
  wet     log2 of the ground draining through     (towns on big streams: twice as often past 2,048 points)

A point's weight for a kind is the product of its five lifts (each band's own; the rare kinds' pulled towards 1 by how
few places they rest on). Each kind is laid by weighted draws in turn, settlements first, each kept its own kind's
spacing (the game's tenth percentile of nearest neighbours) and off the settlements, the other dungeons and the places
the land already has."""
import bisect
import math
import random
import re

FIGS = {"bins": {"z": [0, 100, 300, 700, 1500, 3000, 6000, 1e9], "slope": [0, 5, 10, 15, 20, 30, 40, 91],
                 "tpi": [-1e9, -400, -150, -50, 50, 150, 400, 1e9], "coast": [0, 1100, 2100, 4200, 8300, 16500, 1e9],
                 "wet": [0, 3, 5, 7, 9, 11, 99]},
        "lift": {"city": {"z": [1.052, 1.552, 1.17, 0.997, 0.859, 0.812, 0.888], "slope": [1.435, 1.104, 0.959, 0.826, 1.073, 0.931, 0.806], "tpi": [0.86, 0.897, 1.232, 1.44, 0.978, 0.8, 0.816], "coast": [1.265, 1.329, 1.219, 1.101, 0.793, 0.786], "wet": [0.937, 0.787, 1.087, 1.909, 1.02, 1.21]},
                 "town": {"z": [1.426, 1.567, 1.257, 1.001, 0.874, 0.697, 0.685], "slope": [2.719, 1.027, 1.112, 1.072, 0.624, 0.609, 0.67], "tpi": [0.778, 0.837, 1.197, 1.211, 1.28, 1.119, 0.54], "coast": [1.286, 1.396, 1.332, 1.097, 0.659, 0.813], "wet": [0.747, 1.103, 1.337, 1.168, 1.292, 1.917]},
                 "village": {"z": [0.865, 2.13, 0.931, 1.096, 0.657, 0.947, 0.899], "slope": [3.34, 1.529, 0.946, 0.648, 0.581, 0.515, 0.503], "tpi": [0.405, 0.994, 1.258, 1.685, 0.913, 0.894, 0.61], "coast": [1.093, 1.187, 1.283, 1.157, 0.654, 0.934], "wet": [0.889, 0.978, 1.213, 0.992, 1.401, 1.632]},
                 "cave": {"z": [1.208, 1.03, 1.059, 1.135, 0.929, 0.844, 0.824], "slope": [0.466, 0.574, 0.689, 1.027, 1.233, 1.324, 1.288], "tpi": [3.796, 1.405, 0.682, 0.626, 0.569, 0.572, 0.412], "coast": [1.114, 1.137, 0.871, 0.995, 1.022, 0.972], "wet": [0.624, 1.66, 1.181, 0.82, 0.945, 0.532]},
                 "tomb": {"z": [0.666, 1.626, 1.296, 1.31, 0.744, 0.552, 0.478], "slope": [0.571, 0.56, 0.893, 0.93, 1.266, 1.499, 0.945], "tpi": [3.223, 1.859, 0.8, 0.586, 0.377, 0.492, 0.344], "coast": [0.982, 1.136, 1.415, 1.007, 0.997, 0.735], "wet": [0.55, 1.713, 1.291, 0.745, 1.118, 0.745]},
                 "dwemer": {"z": [0.847, 0.398, 0.708, 0.793, 1.388, 1.206, 1.349], "slope": [0.389, 0.373, 0.768, 0.892, 1.039, 1.052, 2.016], "tpi": [1.895, 1.196, 0.685, 1.365, 0.722, 0.59, 0.898], "coast": [0.73, 0.652, 1.108, 0.967, 0.924, 1.235], "wet": [0.756, 1.36, 0.964, 1.255, 1.075, 1.092]},
                 "daedric": {"z": [0.752, 1.277, 0.93, 1.308, 0.791, 0.885, 0.781], "slope": [1.43, 1.259, 1.033, 0.639, 0.83, 1.238, 0.775], "tpi": [2.574, 0.963, 1.233, 0.706, 0.793, 0.776, 0.663], "coast": [0.949, 1.031, 1.311, 0.858, 0.861, 1.06], "wet": [0.812, 1.172, 1.714, 0.609, 0.426, 0.519]},
                 "fort": {"z": [1.433, 0.916, 1.207, 1.151, 0.969, 0.657, 0.727], "slope": [2.128, 0.925, 0.792, 0.809, 1.066, 0.988, 0.651], "tpi": [1.106, 1.006, 0.917, 1.234, 1.09, 0.739, 1.027], "coast": [1.252, 1.333, 1.024, 0.917, 1.105, 0.765], "wet": [0.957, 1.096, 0.905, 0.949, 1.331, 1.016]},
                 "tower": {"z": [0.661, 1.357, 1.27, 0.877, 0.892, 1.023, 0.942], "slope": [1.792, 1.522, 1.303, 0.717, 0.676, 0.836, 0.645], "tpi": [1.002, 0.762, 1.092, 0.761, 0.828, 0.99, 1.648], "coast": [1.536, 2.001, 1.059, 0.69, 0.776, 0.88], "wet": [1.015, 1.09, 0.871, 0.898, 1.014, 0.767]}},
        "rate": {"city": 0.39, "town": 1.72, "village": 2.27, "cave": 20.29, "tomb": 9.09, "dwemer": 2.35, "daedric": 2.82, "fort": 0.78, "tower": 1.49},
        "spacing": {"city": 59285, "town": 21479, "village": 17260, "cave": 4207, "tomb": 10185, "dwemer": 2305, "daedric": 3359, "fort": 1417, "tower": 2008}}
SETTLEMENTS = ('city', 'town', 'village')
DUNGEONS = ('fort', 'tower', 'dwemer', 'daedric', 'tomb', 'cave')
# places that grow from each other (lab a20, 2026-11-08, VV + TR: 112 settlements, the lone places' doors outside
# them clustered within 1,024 and named by kind, the roads as a12 reads them, each against 40,000 random points of
# land): the lift of each band of 'road', the distance to the nearest road, and 'town', to the nearest settlement (a
# village's: the nearest town or city). Villages keep off the towns (8-16k from one 0.47 times as often as the land
# is, past 16k 1.1): they fill the gaps, they don't lie between towns (less often than random land). Farms cling to
# the roads (9.3 times within 512), dungeons by them too (2-4 times) but off the settlements (caves and tombs a
# quarter as often 2-8k from one), towers and forts beside them.
GROW = {'bins': {'road': [0, 512, 1024, 2048, 4096, 8192, 16384, 1e9], 'town': [0, 2048, 4096, 8192, 16384, 32768, 1e9]},
        'lift': {'village': {'town': [1.782, 0.816, 0.469, 0.606, 1.064, 1.126]},
                 'farmstead': {'road': [9.331, 3.014, 0.746, 0.488, 0.478, 0.308, 0.278], 'town': [0.764, 0.421, 1.058, 1.111, 1.09, 0.563]},
                 'inn': {'road': [2.289, 1.198, 0.926, 0.902, 0.967, 0.898, 0.917], 'town': [1.995, 1.235, 1.173, 1.019, 0.953, 0.92]},
                 'cave': {'road': [1.985, 1.447, 0.678, 0.866, 0.99, 1.093, 0.81], 'town': [0.404, 0.248, 0.754, 1.061, 1.021, 1.118]},
                 'tomb': {'road': [3.09, 2.579, 0.564, 0.53, 0.73, 0.846, 1.22], 'town': [0.355, 0.194, 0.403, 1.185, 1.074, 0.926]},
                 'dwemer': {'road': [2.506, 1.823, 0.809, 0.362, 0.769, 1.166, 1.263], 'town': [1.007, 0.557, 0.52, 0.927, 1.14, 1.043]},
                 'daedric': {'road': [4.05, 2.758, 0.949, 0.672, 0.641, 0.856, 0.46], 'town': [0.894, 0.493, 0.461, 1.026, 1.012, 1.324]},
                 'fort': {'road': [2.05, 1.865, 0.951, 0.738, 0.786, 0.723, 1.384], 'town': [1.708, 1.704, 1.317, 0.946, 0.768, 1.521]},
                 'tower': {'road': [3.015, 2.068, 1.096, 0.801, 0.553, 0.898, 0.907], 'town': [3.169, 1.361, 1.714, 0.949, 0.872, 0.912]}},
        # (a hundred land cells: 90 farms in 2,553 cells, 0.8 a settlement; 5 lone inns, about one in 330 cells of road)
        'rate': {'farmstead': 3.52, 'inn': 0.2},
        # (random land's distance to the nearest road, every 5%: a dungeon's distance to the proposed roads is read
        # as the game's at the same rank among the land, the proposed roads being the ways between settlements alone,
        # about a quarter of the game's road a cell with its tracks to farms and ruins)
        'road_q': [0, 512, 724, 1145, 1536, 2048, 2560, 3114, 3692, 4375, 5120, 5971, 6888, 8095, 9441, 10993, 12953, 15773, 19597,
                   25728, 71022],
        # (the farms' median nearest neighbour; the inns' tenth percentile)
        'spacing': {'farmstead': 6000, 'inn': 60000}}
# farmsteads and roadside inns: town layers of a few buildings (the planner needs a village's outline to lay one plot:
# 1,600 across at density 0.5 gave two or three buildings, a smaller outline none, lab 2026-11-08), the ground a
# village's
HAMLETS = ('farmstead', 'inn')
HAMLET_R = 1600.0
HAMLET_DENSITY = 0.5
GROUND = {'farmstead': 'village', 'inn': 'village'}
NO_SPECIAL = {'shop': 0, 'tavern': 0, 'temple': 0, 'guild': 0, 'manor': 0, 'guard': 0}
# the small things between places (smallthings.py; lab a21, 2026-11-08, VV + TR outside the towns' cells): a hundred
# land cells of each, the sites smallthings keeps (on the ground, with something by the anchor: a lone cairn is a rock
# of the land, 10% of them kept; 71% of camps, the rest on ledges or at cave mouths), and where: the same five ground
# lifts as the dungeons' and the road and town lifts as GROW's. Carts stand by the roads (6.2 times within 512), camps
# on the flat and off the towns, remains in hollows, wrecks on the shore.
SMALL_KINDS = ('camp', 'cart', 'burial', 'cairn', 'remains', 'shrine', 'fishing', 'wreck')
SMALL = {'rate': {'camp': 5.14, 'cart': 2.77, 'burial': 1.01, 'cairn': 0.55, 'remains': 0.33, 'shrine': 0.39, 'wreck': 0.35, 'fishing': 0.24},
         # (the game's tenth percentile of nearest neighbours, at least 1,000: its camps and cairns stand in groups)
         'spacing': {'camp': 1500, 'cart': 2200, 'burial': 1000, 'cairn': 1200, 'remains': 1200, 'shrine': 7000, 'wreck': 20000, 'fishing': 6000},
         'lift': {'wreck': {"z": [2.328, 2.058, 1.069, 0.804, 0.805, 0.831, 0.903], "slope": [0.868, 0.981, 0.978, 0.999, 1.358, 0.828, 0.826], "tpi": [0.881, 1.012, 0.838, 1.081, 1.153, 0.819, 1.224], "coast": [2.555, 1.108, 0.837, 0.819, 0.812, 0.806], "wet": [0.995, 0.88, 1.111, 0.9, 1.026, 2.143]},
                  'camp': {"z": [1.457, 1.042, 1.049, 1.161, 0.897, 0.959, 0.507], "slope": [2.705, 1.56, 1.056, 0.883, 0.759, 0.447, 0.437], "tpi": [1.774, 1.191, 1.155, 0.962, 0.807, 0.677, 0.769], "coast": [0.818, 1.03, 1.061, 0.99, 1.066, 0.971], "wet": [0.804, 0.999, 1.335, 1.171, 1.553, 1.563]},
                  'remains': {"z": [0.966, 1.145, 1.315, 0.705, 0.74, 1.313, 1.566], "slope": [1.477, 1.611, 1.152, 0.873, 0.725, 0.469, 1.06], "tpi": [3.291, 1.172, 0.71, 0.923, 0.55, 0.535, 0.769], "coast": [0.52, 0.696, 0.863, 1.097, 1.135, 1.153], "wet": [0.569, 1.414, 1.751, 1.039, 0.808, 0.665]},
                  'cairn': {"z": [0.86, 0.873, 1.059, 1.792, 0.704, 0.508, 0.219], "slope": [1.192, 1.303, 1.244, 1.641, 1.042, 0.491, 0.409], "tpi": [1.049, 1.348, 1.195, 0.977, 0.969, 0.79, 0.644], "coast": [0.462, 0.415, 0.605, 0.554, 0.882, 2.018], "wet": [0.654, 1.125, 1.146, 1.79, 1.029, 3.349]},
                  'burial': {"z": [0.752, 0.595, 0.936, 0.869, 1.108, 1.355, 1.043], "slope": [0.738, 1.128, 1.344, 0.686, 0.976, 0.833, 1.191], "tpi": [0.77, 0.775, 0.556, 1.156, 0.934, 0.947, 1.812], "coast": [0.748, 0.944, 0.766, 0.776, 1.07, 1.336], "wet": [1.261, 0.646, 0.985, 0.809, 0.702, 0.861]},
                  'shrine': {"z": [0.989, 0.797, 0.859, 1.132, 0.717, 1.601, 0.814], "slope": [1.36, 1.029, 1.162, 0.757, 0.726, 1.088, 1.075], "tpi": [1.011, 0.825, 1.023, 0.866, 1.362, 1.028, 1.001], "coast": [1.193, 1.011, 0.879, 1.12, 0.972, 0.931], "wet": [0.982, 0.934, 1.015, 1.063, 1.432, 1.127]},
                  'cart': {"z": [1.017, 1.223, 1.046, 1.094, 0.804, 1.311, 0.339], "slope": [2.662, 1.719, 1.037, 0.677, 0.728, 0.584, 0.411], "tpi": [1.496, 1.316, 1.165, 1.374, 0.969, 0.395, 0.553], "coast": [0.613, 0.845, 1.362, 0.804, 1.155, 0.998], "wet": [0.625, 1.075, 1.691, 1.416, 1.574, 1.327]},
                  'fishing': {"z": [2.271, 2.469, 1.014, 0.749, 0.822, 0.776, 0.848], "slope": [1.991, 0.785, 1.062, 0.944, 1.031, 0.773, 0.771], "tpi": [0.826, 0.86, 1.06, 1.4, 0.944, 1.066, 0.779], "coast": [1.859, 1.049, 1.183, 0.863, 0.925, 0.751], "wet": [0.938, 1.044, 1.053, 0.844, 1.478, 1.168]}},
         'road': {'wreck': [1.006, 0.891, 0.846, 0.918, 0.889, 1.172, 1.227], 'camp': [1.256, 0.959, 1.003, 0.719, 1.119, 1.152, 0.903],
                  'remains': [1.943, 0.842, 0.769, 1.087, 1.024, 0.907, 1.003], 'cairn': [0.695, 0.979, 0.443, 0.472, 0.737, 1.787, 1.547],
                  'burial': [1.074, 0.599, 0.562, 1.421, 1.304, 0.898, 0.659], 'shrine': [1.381, 1.523, 1.214, 1.219, 0.799, 0.726, 0.875],
                  'cart': [6.241, 3.121, 1.12, 0.629, 0.597, 0.382, 0.369], 'fishing': [1.895, 1.08, 0.791, 0.863, 0.992, 1.027, 1.041]},
         'town': {'wreck': [1.928, 1.154, 0.873, 0.931, 0.958, 1.34], 'camp': [0.417, 0.232, 0.512, 1.032, 1.046, 1.33],
                  'remains': [0.592, 0.33, 0.446, 0.957, 1.198, 0.945], 'cairn': [0.526, 0.293, 1.084, 1.183, 1.041, 0.497],
                  'burial': [1.413, 0.803, 0.745, 1.649, 0.714, 0.693], 'shrine': [1.809, 1.056, 0.985, 1.092, 0.947, 0.92],
                  'cart': [0.808, 1.159, 0.8, 0.976, 1.15, 0.613], 'fishing': [1.862, 1.095, 1.023, 1.26, 0.776, 1.118]}}
FIGS['lift'].update(SMALL['lift'])
for _k in SMALL_KINDS:
    GROW['lift'][_k] = {'road': SMALL['road'][_k], 'town': SMALL['town'][_k]}
GROW['spacing'].update(SMALL['spacing'])
# views and landmarks (lab a23, 2026-11-08, VV + TR: from road points about 1,024 apart, rays out to VIEW_REACH over
# the 512 grid, the eye 128 over the road; a place is seen when the line to VIEW_TOP over its ground clears the land
# between): the share of the road within VIEW_REACH of a place that sees it, by band (the first, no road within
# reach). Against the land, Daedric ruins stand where the road sees them (86% of it at the median, the land 50%),
# caves and tombs out of sight (33%, 43%); but their ground says most of that (hollows are hidden). The lifts here are
# over what each kind's own ground gives (a23b: the land weighted by the kind's five ground lifts): Daedric ruins 1.9
# times as often where over 70% of the road sees them, Dwemer ruins 1.3, towers a little; caves, tombs and wayside
# shrines about as their ground puts them. (A first try with the lifts against the land counted the hollows twice:
# caves fell to 23% seen, the game's 33%.)
VIEW_REACH = 8192.0
VIEW_EYE = 128.0
VIEW_TOP = 300.0
VIEW_RAYS = 90
VIEW_BINS = [-1.5, -0.5, 0.05, 0.15, 0.3, 0.5, 0.7, 1.01]
VIEW_LIFT = {'daedric': [0.748, 0.863, 0.802, 1.022, 0.751, 0.861, 1.878], 'tower': [0.9, 0.881, 1.1, 1.035, 1.26, 0.985, 1.078],
             'fort': [1.013, 0.88, 1.192, 1.116, 1.11, 0.899, 0.998], 'dwemer': [1.04, 0.801, 1.349, 0.931, 0.843, 0.793, 1.338],
             'cave': [0.922, 1.026, 1.451, 1.159, 1.078, 0.824, 1.059], 'tomb': [1.015, 0.68, 1.223, 0.938, 1.278, 1.117, 0.928],
             'shrine': [0.925, 0.901, 0.976, 1.094, 1.066, 1.091, 1.066]}
SMALL_FIT = 120.0               # (a scene whose ground falls more unlike the spot's than this on the mean is not laid there)
SMALL_GAP = 800.0               # (a small thing this far from any other place, and this far outside a settlement's outline)
# (by the road as the game's are, whatever share of the land lies near the proposed roads: farmsteads and inns with
# their outline reaching it, carts and wayside shrines beside it off its bed)
ROADSIDE = {'farmstead': HAMLET_R, 'inn': HAMLET_R, 'cart': 300.0, 'shrine': 400.0}
ROAD_CLEAR = 448.0              # (a dungeon's door no nearer a proposed road's line: its bed is cut 160 either side, eased over 256)
# (the game's outlines: 90% of a place's buildings within this of its middle, townsurvey's towns, medians)
RADIUS = {'village': 1600.0, 'town': 3600.0, 'city': 8900.0}
SETTLE_GAP = 12000.0            # (settlements at least this apart, whatever their sizes)
DUNGEON_GAP = 3000.0            # (dungeons at least this from each other, and from a settlement's edge and the places already there)
DUNMER_ONLY = ('tomb', 'tower')         # (the kits that are the Dunmer's own: Velothi tombs and towers)
NOT_DUNMER = ('Gold Coast', 'Imperial', 'Nordic', 'Reach')
KIT = {'dwemer': 'dwemer', 'daedric': 'daedric', 'fort': 'fort', 'tower': 'tower', 'tomb': 'tomb'}
SUFFIX = {'cave': '%s Cave', 'tomb': '%s Ancestral Tomb', 'dwemer': '%s', 'daedric': '%s Shrine', 'fort': 'Fort %s', 'tower': '%s',
          'mine': '%s Mine', 'eggmine': '%s Egg Mine', 'farmstead': '%s Farm', 'plantation': '%s Plantation', 'inn': '%s Inn',
          'tradehouse': '%s Tradehouse'}
LABEL = {'harbour': 'harbour', 'mine': 'mine', 'farm': 'farm', 'city': 'city', 'town': 'town', 'village': 'village', 'cave': 'cave', 'tomb': 'tomb', 'dwemer': 'Dwemer ruin',
         'daedric': 'Daedric ruin', 'fort': 'fort', 'tower': 'tower', 'farmstead': 'farmstead', 'inn': 'roadside inn'}
STEP = 512.0
RING = 2                        # (cells round the marked ones read for the features: the coast, the hollows)


def _band(v, edges):
    for i in range(len(edges) - 1):
        if v < edges[i + 1]:
            return i
    return len(edges) - 2


def _grid(db, keys):
    """The land at every 512 units over the marked cells and RING round them: (z list, w, h, X0, Y0)."""
    import mapdata
    xs, ys = [k[0] for k in keys], [k[1] for k in keys]
    X0, Y0, X1, Y1 = min(xs) - RING, min(ys) - RING, max(xs) + RING, max(ys) + RING
    w, h = (X1 - X0 + 1) * 16, (Y1 - Y0 + 1) * 16
    z = [-2048.0] * (w * h)
    for cx in range(X0, X1 + 1):
        for cy in range(Y0, Y1 + 1):
            L = mapdata.land(db, cx, cy)
            if not L.get('exists'):
                continue
            H = L['h']
            for j in range(16):
                for i in range(16):
                    z[((cy - Y0) * 16 + j) * w + (cx - X0) * 16 + i] = float(H[j * 4 * 65 + i * 4])
    return z, w, h, X0, Y0


def features(db, keys):
    """The five features at every 512 point: {'z', 'slope', 'tpi', 'coast', 'wet'} lists, and (w, h, X0, Y0)."""
    import landwater
    z, w, h, X0, Y0 = _grid(db, keys)
    n = w * h
    slope = [0.0] * n
    for y in range(h):
        for x in range(w):
            i = y * w + x
            a = z[i + 1] if x + 1 < w else z[i]
            b = z[i - 1] if x else z[i]
            c = z[i + w] if y + 1 < h else z[i]
            d = z[i - w] if y else z[i]
            slope[i] = math.degrees(math.atan(math.hypot(a - b, c - d) / (2 * STEP) * 1.0))
    # TPI: the height over the mean within 2,048 (a 9 x 9 box, by sums)
    row = [0.0] * n
    for y in range(h):
        acc = 0.0
        for x in range(-4, w + 4):
            if x + 4 < w:
                acc += z[y * w + x + 4]
            if x - 5 >= 0:
                acc -= z[y * w + x - 5]
            if 0 <= x < w:
                row[y * w + x] = acc / (min(w - 1, x + 4) - max(0, x - 4) + 1)
    tpi = [0.0] * n
    for x in range(w):
        acc = 0.0
        for y in range(-4, h + 4):
            if y + 4 < h:
                acc += row[(y + 4) * w + x]
            if y - 5 >= 0:
                acc -= row[(y - 5) * w + x]
            if 0 <= y < h:
                tpi[y * w + x] = z[y * w + x] - acc / (min(h - 1, y + 4) - max(0, y - 4) + 1)
    # the sea's distance (a breadth-first walk on the grid, eight ways)
    from collections import deque
    coast = [1e9] * n
    q = deque()
    for i in range(n):
        if z[i] <= 0:
            coast[i] = 0.0
            q.append(i)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for dx, dy, c in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h:
                j = yy * w + xx
                if coast[i] + c * STEP < coast[j]:
                    coast[j] = coast[i] + c * STEP
                    q.append(j)
    # the ground draining through each point, the most of it and its eight round
    out = bytearray(1 if (z[i] <= 0 or i % w in (0, w - 1) or i // w in (0, h - 1)) else 0 for i in range(n))
    f, order = landwater.fill(z, w, h, out)
    rec, _d = landwater.flow(f, w, h, out)
    A = landwater.area(rec, order)
    wet = [0.0] * n
    for i in range(n):
        x, y = i % w, i // w
        m = A[i]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and A[yy * w + xx] > m:
                    m = A[yy * w + xx]
        wet[i] = math.log2(max(1.0, m))
    return {'z': z, 'slope': slope, 'tpi': tpi, 'coast': coast, 'wet': wet}, (w, h, X0, Y0)


def weight(kind, feats, i):
    """A point's weight for a kind: the product of its lifts."""
    L = FIGS['lift'][GROUND.get(kind, kind)]
    p = 1.0
    for f, edges in FIGS['bins'].items():
        p *= L[f][_band(feats[f][i], edges)]
    return p


def _existing(db, keys):
    """Where the land has places already: its doors outside (towns, caves, ruins), [(x, y)]."""
    import mapdata
    xs, ys = [k[0] for k in keys], [k[1] for k in keys]
    out = []
    for cx in range(min(xs) - 1, max(xs) + 2):
        for cy in range(min(ys) - 1, max(ys) + 2):
            m = mapdata.cellmap(db, '#%d,%d' % (cx, cy))
            for r in m.get('refs') or []:
                if r.get('type') == 'DOOR':
                    out.append((r['p'][0], r['p'][1]))
    return out


_TOWNS = {}


def culture_at(db, x, y, region=''):
    """The culture a place at (x, y) takes: the game town's nearest in its region's weather and on the map (as
    landregion.rock_region picks rock), not the nearest alone: across Tamriel.esm's land the nearest game town is
    often hundreds of cells off, TR's Redoran towns for the Jerall Mountains and the Heartlands (lab 2026-11-08)."""
    import landregion
    import mapdata
    import townplan
    import townsurvey
    key = id(db.recs)
    if key not in _TOWNS:
        ok = {c['id'] for c in townplan.cultures(db)}
        lst = []
        for t in townsurvey.survey(db)['towns']:
            if t['culture'] not in ok or not t['buildings']:
                continue
            tx = sum(b['x'] for b in t['buildings']) / len(t['buildings'])
            ty = sum(b['y'] for b in t['buildings']) / len(t['buildings'])
            ci = mapdata.cell_info(db, '#%d,%d' % (math.floor(tx / 8192.0), math.floor(ty / 8192.0)))
            r = ((ci or {}).get('region') or '').lower()
            lst.append((tx, ty, t['culture'], landregion._weather(db, r) if r else None))
        _TOWNS.clear()
        _TOWNS[key] = lst
    mine = landregion._weather(db, region) if region else None
    best = None
    for tx, ty, cult, w in _TOWNS[key]:
        d = math.hypot(tx - x, ty - y) / (landregion.ROCK_FAR * 8192.0)
        if mine and w:
            d += sum(abs(a - b) for a, b in zip(mine, w))
        if best is None or d < best[0]:
            best = (d, cult)
    return best[1] if best else 'Hlaalu'


# (a made name carrying another kind of place's word, or a word of one letter: "O Camp" for a tower, "In Plantation
# Ancestral Tomb", made from the game's own "Dren Plantation" and Ashlander camps, 2026-11-08)
NOT_IN_NAME = re.compile(r'\b(camp|plantation|manor|fort|mine|stronghold|keep|village|town|hall|ruins?|shrine|tower|tomb|cave|cavern|'
                         r'grotto|egg|outpost|farm|inn|tavern|castle|city|port|harbou?r|docks?|\w)\b', re.I)


def _name(db, kind, culture, rng, used):
    """A new place's name from the culture's own names, none the game or this proposal has."""
    import towninside
    free = lambda low: low not in used and not any(v not in db.dead for v in db.by_key.get(('CELL', low), []))
    last = ''
    for _t in range(24):
        try:
            base = towninside.town_name(db, culture, rng.randrange(1, 1 << 30))
        except Exception:
            return ''
        if NOT_IN_NAME.search(base):
            continue
        last = base
        nm = SUFFIX[kind] % base
        if free(nm.lower()):
            used.add(nm.lower())
            return nm
    # (a culture with few town names to make new ones from runs out: the last one again with a numeral)
    for k in ('II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'):
        nm = SUFFIX[kind] % ('%s %s' % (last or culture, k))
        if free(nm.lower()):
            used.add(nm.lower())
            return nm
    return ''


def _dunmer(culture):
    return culture not in NOT_DUNMER


FIT_RAYS = 24
FIT_STEP = 192.0
FIT_DRY = 40.0                  # (ground this far over the water at least: a town's edge stops at the shore)
FIT_STEEP = 32.0                # (and at ground steeper than this, degrees)
FIT_MIN = 0.35                  # (no ray shorter than this share of the size: the place keeps a body)


def fit_outline(db, x, y, r):
    """A town's or castle's outline for a marker (the Land stage's Town and Castle, 2026-11-09: "Why is it so hard to
    just draw a shape where 'I want a city here' ... and just figure it out"): rays out from the marker, each stopping
    at the shore or at steep ground before r, smoothed round, so the place fits the land under it."""
    r = max(400.0, min(16000.0, float(r)))
    rad = []
    for k in range(FIT_RAYS):
        a = 2 * math.pi * k / FIT_RAYS
        c, s = math.cos(a), math.sin(a)
        d, ok = 0.0, 0.0
        while d < r:
            d += FIT_STEP
            px, py = x + c * d, y + s * d
            z = mapdata_z(db, px, py)
            sl = _slope(db, px, py)
            if z is None or z < FIT_DRY or (sl is not None and sl > FIT_STEEP):
                break
            ok = d
        rad.append(max(ok, r * FIT_MIN))
    # (smoothed, three rays a side: a single steep spot cut a notch into the outline)
    sm = [sum(rad[(k + j) % FIT_RAYS] for j in range(-3, 4)) / 7.0 for k in range(FIT_RAYS)]
    sm = [min(rad[k] * 1.15, sm[k]) for k in range(FIT_RAYS)]
    return [[round(x + math.cos(2 * math.pi * k / FIT_RAYS) * sm[k]), round(y + math.sin(2 * math.pi * k / FIT_RAYS) * sm[k])] for k in range(FIT_RAYS)]


def _outline(x, y, r, rng):
    pts = []
    for k in range(8):
        a = k * math.pi / 4 + rng.uniform(-0.15, 0.15)
        rr = r * rng.uniform(0.85, 1.15)
        pts.append([round(x + math.cos(a) * rr), round(y + math.sin(a) * rr)])
    return pts


def _cave_kit(region, z):
    reg = (region or '').lower()
    if any(w in reg for w in ('ash', 'molag', 'red mountain', 'armun')):
        return 'cave_lava'
    return 'cave_mold' if z > 2500 else 'cave_mud'


def _land_shares(Q, edges):
    """The share of the game's land in each band of edges, from its quantiles Q (every 1/(len(Q)-1))."""
    def cdf(d):
        if d >= Q[-1]:
            return 1.0
        for k in range(len(Q) - 1):
            if d < Q[k + 1]:
                return (k + (d - Q[k]) / max(1e-6, Q[k + 1] - Q[k])) / (len(Q) - 1)
        return 1.0
    return [cdf(b) - cdf(a) for a, b in zip(edges, edges[1:])]


def _seen(Z, w, h, roads, index):
    """For each point of the 512 grid: the share of the road points within VIEW_REACH (one every 1,024 along the
    roads) whose view reaches VIEW_TOP over its ground, the land between lower than the line; -1 where no road is
    within reach."""
    pts = []
    for q in roads:
        P = q['pts']
        acc = 1024.0
        for (ax, ay), (bx, by) in zip(P, P[1:]):
            L = math.hypot(bx - ax, by - ay)
            t = 0.0
            while t < L:
                if acc >= 1024.0:
                    i = index(ax + (bx - ax) * t / L, ay + (by - ay) * t / L) if L else None
                    if i is not None:
                        pts.append(i)
                    acc = 0.0
                step = min(L - t, 1024.0 - acc)
                t += max(step, 1.0)
                acc += max(step, 1.0)
    n = w * h
    seen, near = [0] * n, [0] * n
    sm, nm = [-1] * n, [-1] * n
    steps = int(VIEW_REACH / STEP)
    dirs = [(math.cos(2 * math.pi * a / VIEW_RAYS), math.sin(2 * math.pi * a / VIEW_RAYS)) for a in range(VIEW_RAYS)]
    for k, i0 in enumerate(pts):
        x0, y0 = i0 % w, i0 // w
        z0 = max(Z[i0], 0.0) + VIEW_EYE
        for cx, cy in dirs:
            top = -1e9
            for d in range(1, steps + 1):
                x, y = int(round(x0 + cx * d)), int(round(y0 + cy * d))
                if not (0 <= x < w and 0 <= y < h):
                    break
                j = y * w + x
                zg = max(Z[j], 0.0)
                dd = d * STEP
                if nm[j] != k:
                    nm[j] = k
                    near[j] += 1
                if (zg + VIEW_TOP - z0) / dd >= top and sm[j] != k:
                    sm[j] = k
                    seen[j] += 1
                sg = (zg - z0) / dd
                if sg > top:
                    top = sg
    return [seen[i] / float(near[i]) if near[i] else -1.0 for i in range(n)]


def _dist_field(sources, w, h):
    """The distance on the 512 grid from the nearest of the sources (grid indices), eight ways; 1e9 where none."""
    from collections import deque
    D = [1e9] * (w * h)
    q = deque()
    for i in set(sources):
        D[i] = 0.0
        q.append(i)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for dx, dy, c in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h:
                j = yy * w + xx
                if D[i] + c * STEP < D[j]:
                    D[j] = D[i] + c * STEP
                    q.append(j)
    return D


def propose(db, cells, amounts=None, seed=1, kinds=None, culture='', livelihoods=True, grow=True, say=None, names=True):
    """Places for the marked cells: {'places': [{kind, label, x, y, z, rz, r, outline, culture, kit, name}],
    'roads': [landroads.route's roads], 'expected': {kind: the game's number for this much land}, 'land_cells'}.
    amounts: {'settlements', 'dungeons', 'small'} (1 as the game's rates). kinds: those to propose (default all). culture:
    every place's (else culture_at).
    grow: the places grow from each other as the game's sit by each other (GROW): the cities and towns first, the
    villages in the gaps between them, then the roads joining them all (and the game's towns near), then the farmsteads
    and roadside inns along those roads, the dungeons by the roads and off the settlements, the small things last (SMALL:
    camps, carts, graves, remains, shrines, wrecks, fishing spots, each a scene of the game's). Off, every kind on the
    ground alone and no roads."""
    import landrange
    keys = sorted({landrange._key(k) for k in cells or []})
    if not keys:
        return {'places': [], 'roads': [], 'expected': {}, 'land_cells': 0}
    A = {'settlements': 1.0, 'dungeons': 1.0, 'small': 1.0}
    A.update({k: max(0.0, min(3.0, float(v))) for k, v in (amounts or {}).items() if k in A})
    feats, (w, h, X0, Y0) = features(db, keys)
    mine = set(keys)
    cand = []
    for i in range(w * h):
        x, y = i % w, i // w
        if (X0 + x // 16, Y0 + y // 16) in mine and feats['z'][i] > 48:
            cand.append(i)
    land_cells = len(cand) / 256.0
    rng = random.Random(int(seed) * 7919 + 13)
    world = lambda i: ((X0 * 16 + i % w) * STEP, (Y0 * 16 + i // w) * STEP)

    def index(x, y):
        gx, gy = int(round(x / STEP)) - X0 * 16, int(round(y / STEP)) - Y0 * 16
        return gy * w + gx if 0 <= gx < w and 0 <= gy < h else None

    have = _existing(db, keys)
    placed, expected, used = [], {}, set()
    rel = {}                    # (the fields the places grow by: 'town' and 'road' distances on the grid)

    def relw(kind, i):
        L = GROW['lift'].get(kind)
        if not L:
            return 1.0
        p = 1.0
        if 'view' in rel and kind in VIEW_LIFT:
            p *= VIEW_LIFT[kind][_band(rel['view'][i], VIEW_BINS)]
        if 'town' in L and 'town' in rel:
            p *= L['town'][_band(rel['town'][i], GROW['bins']['town'])]
        if 'road' in L and 'road' in rel:
            d = rel['road'][i]
            if kind in ROADSIDE:
                # (a farm's or an inn's outline reaching the road, the road not through its buildings; a cart beside it)
                off = ROADSIDE[kind]
                if d < off * 0.8:
                    return 0.0
                return p * rel['hamlet'][kind][_band(max(0.0, d - off), GROW['bins']['road'])]
            elif d < ROAD_CLEAR:
                return 0.0
            else:
                d = rel['road_g'][i]
            p *= L['road'][_band(d, GROW['bins']['road'])]
        return p

    def lay(kind, amt, rate):
        if kinds and kind not in kinds:
            return
        want = rate / 100.0 * land_cells * amt
        expected[kind] = round(rate / 100.0 * land_cells, 2)
        n = int(want) + (1 if rng.random() < want - int(want) else 0)
        if not n or not cand:
            return
        ws = [weight(kind, feats, i) * (relw(kind, i) if grow else 1.0) for i in cand]
        tot = sum(ws)
        if tot <= 0:
            return
        got = 0
        for _try in range(n * 40):
            if got >= n:
                break
            # (a weighted draw: the cumulative weights walked from a random point)
            t = rng.random() * tot
            for i, wv in zip(cand, ws):
                t -= wv
                if t <= 0:
                    break
            x, y = world(i)
            x += rng.uniform(-200, 200)
            y += rng.uniform(-200, 200)
            if not _room(kind, x, y, placed, have):
                continue
            z = feats['z'][i]
            P = {'kind': kind, 'label': LABEL.get(kind, kind), 'x': round(x), 'y': round(y), 'z': round(z)}
            region = landrange._region_of(db, math.floor(x / 8192.0), math.floor(y / 8192.0))
            P['culture'] = culture or culture_at(db, x, y, region)
            if kind in SETTLEMENTS:
                P['r'] = RADIUS[kind]
                P['outline'] = _outline(x, y, RADIUS[kind], rng)
            elif kind in HAMLETS:
                P['r'] = HAMLET_R
                P['outline'] = _outline(x, y, HAMLET_R, rng)
                P['density'] = HAMLET_DENSITY
                dun = _dunmer(P['culture'])
                if kind == 'farmstead':
                    # (a farmhouse and its outbuildings; a plantation's manor one time in three, as among the game's
                    # named farms: 19 farmhouses and farms, 9 plantations)
                    big = rng.random() < 0.33
                    P['counts'] = dict(NO_SPECIAL, manor=1 if big else 0)
                    P['trade'] = 'farm'
                    P['name'] = _name(db, 'plantation' if big and dun else 'farmstead', P['culture'], rng, used)
                else:
                    P['counts'] = dict(NO_SPECIAL, tavern=1)
                    P['trade'] = 'trade'
                    P['name'] = _name(db, 'tradehouse' if dun else 'inn', P['culture'], rng, used)
            elif kind in SMALL_KINDS:
                # (a wreck on the shore, a fishing spot by the water, as every one of the game's stands)
                if kind == 'wreck' and (feats['coast'][i] > 1100 or z > 400):
                    continue
                if kind == 'fishing' and not ((feats['coast'][i] <= 1600 or feats['wet'][i] >= 9) and z < 700):
                    continue
                import smallthings
                way = smallthings._sea_way(db, x, y) if kind in ('wreck', 'fishing') else None
                ch = smallthings.choose(db, kind, x, y, way, region, rng)
                if not ch or ch[2] > SMALL_FIT:
                    continue
                P['what'] = kind
                P['label'] = smallthings.LABEL[kind]
                P['scene'], P['phi'], P['fit'] = ch[0], round(ch[1], 4), ch[2]
            else:
                if kind in DUNMER_ONLY and not _dunmer(P['culture']):
                    continue
                P['kit'] = KIT.get(kind) or _cave_kit(region, z)
                # (the door's back to the slope, its front, -y, downhill: the way the ground falls round it)
                ix, iy = i % w, i // w
                gx = (feats['z'][i + 1] if ix + 1 < w else z) - (feats['z'][i - 1] if ix else z)
                gy = (feats['z'][i + w] if iy + 1 < h else z) - (feats['z'][i - w] if iy else z)
                P['rz'] = round((math.pi / 2 - math.atan2(gy, gx)) % (2 * math.pi), 3) if (gx or gy) else 0.0
                P['name'] = _name(db, kind, P['culture'], rng, used)
            placed.append(P)
            got += 1

    def town_field(ks):
        src = [index(P['x'], P['y']) for P in placed if P['kind'] in ks] + [index(x, y) for x, y in game_towns]
        return _dist_field([i for i in src if i is not None], w, h)

    game_towns, roads = [], []
    if grow:
        import landroads
        game_towns = [(t[0], t[1]) for t in landroads._towns(db, keys, [])]
    if say:
        say('Towns', 0.05)
    for kind in ('city', 'town'):
        lay(kind, A['settlements'], FIGS['rate'][kind])
    if grow:
        rel['town'] = town_field(('city', 'town'))
    lay('village', A['settlements'], FIGS['rate']['village'])
    if grow:
        S = [P for P in placed if P['kind'] in SETTLEMENTS]
        if len(S) + len(game_towns) >= 2:
            if say:
                say('The roads between them', 0.2)
            R = landroads.route(db, cells, [{'kind': 'town', 'pts': P['outline'], 'p': {'culture': P['culture']}, 'name': P['kind'], 'on': True} for P in S],
                                say=(lambda what, f: say(what, 0.2 + 0.6 * f)) if say else None)
            roads = R['roads']
        rel['town'] = town_field(SETTLEMENTS)
        src = []
        for q in roads:
            pts = q['pts']
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                k = max(1, int(math.hypot(bx - ax, by - ay) / (STEP / 2)))
                src += [index(ax + (bx - ax) * j / k, ay + (by - ay) * j / k) for j in range(k + 1)]
        src = [i for i in src if i is not None]
        if src:
            rel['road'] = D = _dist_field(src, w, h)
            ds = sorted(D[i] for i in cand)
            Q = GROW['road_q']
            G_ = [0.0] * (w * h)
            for i in cand:
                f = bisect.bisect_right(ds, D[i]) / float(len(ds)) * (len(Q) - 1)
                k = min(len(Q) - 2, int(f))
                G_[i] = Q[k] + (Q[k + 1] - Q[k]) * (f - k)
            rel['road_g'] = G_
            # (how much of the road near each point sees it: the landmarks where the roads look at them)
            if say:
                say('What the roads see', 0.84)
            rel['view'] = _seen(feats['z'], w, h, roads, index)
            # (farms and inns as far from the roads as the game's are, whatever share of the land lies near the
            # proposed ones: each band weighted by the game's share of them in it over this land's share in it)
            gsh = _land_shares(Q, GROW['bins']['road'])
            rel['hamlet'] = {}
            for hk, off in ROADSIDE.items():
                tw = [l * g for l, g in zip(GROW['lift'][hk]['road'], gsh)]
                cnt = [0] * len(tw)
                for i in cand:
                    if D[i] >= off * 0.8:
                        cnt[_band(max(0.0, D[i] - off), GROW['bins']['road'])] += 1
                nc, nt = float(sum(cnt)) or 1.0, sum(tw)
                rel['hamlet'][hk] = [(t / nt) / (c / nc) if c else 0.0 for t, c in zip(tw, cnt)]
        if say:
            say('Farms and inns along the roads', 0.85)
        lay('farmstead', A['settlements'], GROW['rate']['farmstead'])
        if src:
            lay('inn', A['settlements'], GROW['rate']['inn'])
    if say:
        say('Dungeons', 0.9)
    for kind in DUNGEONS:
        lay(kind, A['dungeons'], FIGS['rate'][kind])
    if say:
        say('Small things between', 0.95)
    for kind in SMALL_KINDS:
        lay(kind, A['small'], SMALL['rate'][kind])
    if livelihoods:
        # (no field across a road: its middle at least its half-diagonal and the road's bed from the way)
        R_ = rel.get('road')
        near = (lambda x, y: (index(x, y) is not None and R_[index(x, y)] < 830 + 416)) if R_ else None
        placed += works(db, [P for P in placed if P['kind'] in SETTLEMENTS + HAMLETS], rng, used, near)
    if grow and names:
        # (the land's own names: its peaks, passes, headlands, lakes and crossings, and the inns and forts by a pass
        # or a crossing named for it)
        if say:
            say('Naming the land', 0.98)
        cult = lambda x, y: culture or culture_at(db, x, y, landrange._region_of(db, math.floor(x / 8192.0), math.floor(y / 8192.0)))
        N = name_land(db, feats, w, h, X0, Y0, cand, roads, land_cells, rng, used, cult)
        take_names(placed, N)
        placed += N
    return {'places': placed, 'roads': roads, 'expected': expected, 'land_cells': round(land_cells, 1)}


# ---------- names from the land ----------

# (the game names its land's features sparingly, each the name of the one cell it stands in: VV + TR's 2,553 land
# cells hold 8 mountains (Mount Kand, Mount Assarnibibi, Mount Aras), 9 passes (Stormgate Pass, Verulas Pass), 5
# points (Khartag Point), 2 lakes (Lake Dolosamsi), a falls and 2 crossings, lab 2026-11-08; rivers have no cell's
# name. A hundred land cells of each:)
NAME_RATE = {'peak': 0.31, 'pass': 0.35, 'point': 0.2, 'lake': 0.08}
NAME_FORM = {'peak': 'Mount %s', 'pass': '%s Pass', 'point': '%s Point', 'lake': 'Lake %s', 'crossing': '%s Crossing'}
# (Solstheim's and Skyrim's way: Hvitkald Peak, Lake Fjalding)
NAME_FORM_NORD = {'peak': '%s Peak'}
NORD = ('Nordic', 'Reach')
CROSSING_SHARE = 0.3            # (bridges whose cell takes the crossing's name)
PEAK_RING = 6144.0              # (a peak stands this much over the lowest ground this far round it ...)
PEAK_RISE = 900.0               # (... at least)
PASS_SIDE = 2048.0              # (a road's highest point between lower ground ahead and behind, the ground this far ...)
PASS_RISE = 250.0               # (... either side across it this much higher: a saddle)
POINT_SEA = 0.6                 # (a headland: this share of the ground within POINT_R under the sea)
POINT_R = 3072.0
TAKE_NAME = 6000.0              # (an inn or a fort this near a named pass or crossing takes its name)


def _base(db, culture, rng, used):
    """A new base name in the culture's way (as the places' names), none the game or this proposal has."""
    import towninside
    for _t in range(24):
        try:
            b = towninside.town_name(db, culture, rng.randrange(1, 1 << 30))
        except Exception:
            return ''
        if NOT_IN_NAME.search(b) or b.lower() in used:
            continue
        used.add(b.lower())
        return b
    return ''


def _form(kind, culture):
    return (NAME_FORM_NORD.get(kind) if culture in NORD else None) or NAME_FORM[kind]


def name_land(db, feats, w, h, X0, Y0, cand, roads, land_cells, rng, used, culture_of, amount=1.0):
    """The land's named features for the marked cells, as the game names its own: [{'kind': 'label', 'what', 'name',
    'base', 'x', 'y', 'cell', 'culture'}]: the most prominent peaks, the passes where a road crosses a ridge, the
    headlands, the lakes inland, and some of the bridges' crossings. culture_of(x, y): whose names."""
    import mapdata
    Z = feats['z']
    world = lambda i: ((X0 * 16 + i % w) * STEP, (Y0 * 16 + i // w) * STEP)
    candset = set(cand)
    found = {k: [] for k in ('peak', 'pass', 'point', 'lake', 'crossing')}
    # peaks: the highest point within PEAK_RING standing PEAK_RISE over the lowest of the ring round it
    r = int(PEAK_RING / STEP)
    for i in cand:
        x, y = i % w, i // w
        z = Z[i]
        if z < 600:
            continue
        top, low = True, z
        for dx in range(-r, r + 1, 2):
            for dy in range(-r, r + 1, 2):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h:
                    v = Z[yy * w + xx]
                    if v > z:
                        top = False
                        break
                    if dx * dx + dy * dy >= (r - 1) ** 2:
                        low = min(low, v)
            if not top:
                break
        if top and z - low >= PEAK_RISE:
            found['peak'].append((z - low, i))
    # passes: along each road, its highest points between lower ground ahead and behind with higher ground across
    for q in roads:
        pts = q['pts']
        samp = []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            for j in range(max(1, int(L / 512))):
                t = j * 512 / L if L else 0
                samp.append((ax + (bx - ax) * t, ay + (by - ay) * t, (bx - ax) / (L or 1), (by - ay) / (L or 1)))
        zs = [mapdata_z(db, x, y) for x, y, _u, _v in samp]
        for j in range(4, len(samp) - 4):
            z = zs[j]
            if z is None or any(zs[k] is None for k in (j - 4, j + 4)) or not (z >= max(v for v in zs[j - 4:j + 5] if v is not None)):
                continue
            x, y, ux, uy = samp[j]
            sides = [mapdata_z(db, x - uy * PASS_SIDE * s, y + ux * PASS_SIDE * s) for s in (1, -1)]
            if all(v is not None and v - z >= PASS_RISE for v in sides) and z - max(zs[j - 4], zs[j + 4]) >= 60:
                i = index_of(x, y, w, h, X0, Y0)
                if i in candset:
                    found['pass'].append((min(sides) - z, i))
    # headlands and lakes: the water round each shore point, and the water not joined to the grid's edge
    rr = int(POINT_R / STEP)
    for i in cand:
        if feats['coast'][i] > STEP * 1.5:
            continue
        x, y = i % w, i // w
        wet = tot = 0
        for dx in range(-rr, rr + 1, 2):
            for dy in range(-rr, rr + 1, 2):
                if dx * dx + dy * dy > rr * rr:
                    continue
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h:
                    tot += 1
                    wet += Z[yy * w + xx] <= 0
        if tot and wet / tot >= POINT_SEA:
            found['point'].append((wet / tot, i))
    from collections import deque
    seen = bytearray(w * h)
    for s0 in range(w * h):
        if seen[s0] or Z[s0] > 0:
            continue
        comp, q, edge = [], deque([s0]), False
        seen[s0] = 1
        while q:
            i = q.popleft()
            comp.append(i)
            x, y = i % w, i // w
            if x in (0, w - 1) or y in (0, h - 1):
                edge = True
            for j in (i + 1, i - 1, i + w, i - w):
                if 0 <= j < w * h and not seen[j] and Z[j] <= 0 and abs(j % w - x) <= 1:
                    seen[j] = 1
                    q.append(j)
        if not edge and len(comp) >= 4:
            mx = sum(i % w for i in comp) / len(comp)
            my = sum(i // w for i in comp) / len(comp)
            found['lake'].append((len(comp), min(comp, key=lambda i: (i % w - mx) ** 2 + (i // w - my) ** 2)))
    out = []
    taken_cells = set()

    def add(what, x, y):
        cell = '%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0))
        # (a cell with a name already keeps it: Tamriel.esm names 95 cells "Cyrodiil City", and a peak was put in one)
        if cell in taken_cells or ((mapdata.cell_info(db, '#' + cell) or {}).get('name') or '').strip():
            return False
        cult = culture_of(x, y)
        b = _base(db, cult, rng, used)
        if not b:
            return False
        taken_cells.add(cell)
        out.append({'kind': 'label', 'what': what, 'name': _form(what, cult) % b, 'base': b, 'x': round(x), 'y': round(y),
                    'cell': cell, 'culture': cult, 'label': what})
        return True
    for what, rate in NAME_RATE.items():
        want = rate / 100.0 * land_cells * amount
        n = int(want) + (1 if rng.random() < want - int(want) else 0)
        if what in ('peak', 'pass') and found[what] and n == 0 and land_cells >= 60:
            n = 1                       # (a province's one great peak or its pass over the hills is named however small it is)
        lst = sorted(found[what], reverse=True)
        picked = []
        for _sc, i in lst:
            if len(picked) >= n:
                break
            x, y = world(i)
            if any(math.hypot(x - a, y - b) < 8192 * 3 for a, b in picked):
                continue
            if add(what, x, y):
                picked.append((x, y))
    for q in roads:
        for b in q.get('bridges') or []:
            if rng.random() < CROSSING_SHARE * amount:
                add('crossing', (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    return out


def index_of(x, y, w, h, X0, Y0):
    gx, gy = int(round(x / STEP)) - X0 * 16, int(round(y / STEP)) - Y0 * 16
    return gy * w + gx if 0 <= gx < w and 0 <= gy < h else None


def take_names(placed, names):
    """An inn or a fort near a named pass or crossing takes its name, as the game's Maar-Bani Crossing's tradehouse and
    Armun Pass Outpost: the inn the feature's whole name, the fort its base ("Fort Verulas")."""
    for N in names:
        if N['what'] not in ('pass', 'crossing'):
            continue
        for P in placed:
            if P['kind'] in ('inn', 'fort') and math.hypot(P['x'] - N['x'], P['y'] - N['y']) < TAKE_NAME:
                P['name'] = N['name'] if P['kind'] == 'inn' else SUFFIX['fort'] % N['base']
                P['named_for'] = N['name']


# ---------- livelihoods: what each settlement lives by, and its works ----------

# the game's towns by what they live by against the sea's distance from them (lab a14, 2026-11-08, 149 towns: docks,
# boats and nets, farm pieces, crops and beasts, mine doors and the people's classes in a town's cells and one round)
TRADE_ODDS = {'coast': {'harbour': 0.71, 'farm': 0.15, 'mine': 0.09, 'trade': 0.06},
              'near': {'harbour': 0.53, 'mine': 0.18, 'farm': 0.16, 'trade': 0.13},
              'inland': {'farm': 0.36, 'mine': 0.25, 'trade': 0.25, 'harbour': 0.14}}
FIELDS = {'village': 1, 'town': 2, 'city': 3, 'farmstead': 1}
FIELD = (1400.0, 900.0)         # (a field's size: the game's farm plots, storydress's own sizes, about a sixth of a cell)
MINE_REACH = (800.0, 4500.0)    # (a mine's door this far out of the town's edge, on ground of MINE_SLOPE or more)
MINE_SLOPE = 22.0


def _sea_band(db, x, y):
    for r in range(0, 4097, 256):
        for a in range(0, 360, 15 if r else 360):
            z = mapdata_z(db, x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a)))
            if z is not None and z < 0:
                return 'coast' if r <= 1024 else 'near'
    return 'inland'


def mapdata_z(db, x, y):
    import mapdata
    return mapdata.terrain_z(db, x, y)


def _slope(db, x, y, d=256.0):
    a, b = mapdata_z(db, x + d, y), mapdata_z(db, x - d, y)
    c, e = mapdata_z(db, x, y + d), mapdata_z(db, x, y - d)
    if None in (a, b, c, e):
        return None
    return math.degrees(math.atan(math.hypot(a - b, c - e) / (2 * d)))


def _mine_spot(db, P, rng):
    """A hillside for the town's mine: (x, y, door turn) on ground of MINE_SLOPE or more within MINE_REACH of its edge,
    the steepest of a ring of tries, its door's front down the slope."""
    best = None
    for _ in range(48):
        a = rng.uniform(0, 2 * math.pi)
        d = P['r'] + rng.uniform(*MINE_REACH)
        x, y = P['x'] + math.cos(a) * d, P['y'] + math.sin(a) * d
        z = mapdata_z(db, x, y)
        sl = _slope(db, x, y)
        if z is None or z < 64 or sl is None or sl < MINE_SLOPE:
            continue
        if best is None or sl > best[0]:
            gx = mapdata_z(db, x + 256, y) - mapdata_z(db, x - 256, y)
            gy = mapdata_z(db, x, y + 256) - mapdata_z(db, x, y - 256)
            best = (sl, x, y, (math.pi / 2 - math.atan2(gy, gx)) % (2 * math.pi))
    return best[1:] if best else None


def _field_spots(db, P, n, rng, taken, near=None):
    """Up to n field outlines beside the town on its flattest ground (each FIELD across, its long side along the way
    round the town), clear of the water, of each other and of the places laid."""
    out = []
    for _ in range(80):
        if len(out) >= n:
            break
        a = rng.uniform(0, 2 * math.pi)
        d = P['r'] + rng.uniform(300, 2200) + FIELD[0] / 2
        x, y = P['x'] + math.cos(a) * d, P['y'] + math.sin(a) * d
        if any(math.hypot(x - q[0], y - q[1]) < FIELD[0] for q in out + taken) or (near and near(x, y)):
            continue
        ux, uy = -math.sin(a), math.cos(a)                 # (the long side round the town)
        vx, vy = math.cos(a), math.sin(a)
        ok, zs = True, []
        for i in (-0.5, 0, 0.5):
            for j in (-0.5, 0, 0.5):
                px, py = x + ux * FIELD[0] * i + vx * FIELD[1] * j, y + uy * FIELD[0] * i + vy * FIELD[1] * j
                z = mapdata_z(db, px, py)
                sl = _slope(db, px, py)
                if z is None or z < 48 or sl is None or sl > 8:
                    ok = False
                    break
                zs.append(z)
            if not ok:
                break
        if not ok or max(zs) - min(zs) > 160:
            continue
        hx, hy = ux * FIELD[0] / 2, uy * FIELD[0] / 2
        wx, wy = vx * FIELD[1] / 2, vy * FIELD[1] / 2
        out.append((x, y, [[round(x - hx - wx), round(y - hy - wy)], [round(x + hx - wx), round(y + hy - wy)],
                           [round(x + hx + wx), round(y + hy + wy)], [round(x - hx + wx), round(y - hy + wy)]]))
    return out


def works(db, settlements, rng, used, near=None):
    """Each settlement's livelihood (TRADE_ODDS by the sea's distance, among those its site allows: a harbour needs
    a shore a game dock fits, a mine a hillside, a farm flat ground) set on it as 'trade', and its works as places:
    a 'harbour' (the game dock scene to lay on its shore), a 'mine' (a dungeon of the cave kit on the hillside, an egg
    mine on Dunmer land), 'farm' fields beside it (none where near(x, y), a proposed road's way)."""
    import harbours
    out = []
    taken = [(P['x'], P['y']) for P in settlements]
    for P in settlements:
        if P['kind'] == 'inn':
            continue
        odds = dict(TRADE_ODDS[_sea_band(db, P['x'], P['y'])]) if P['kind'] != 'farmstead' else {'farm': 1.0}
        got = None
        while odds and got is None:
            tot = sum(odds.values())
            t = rng.random() * tot
            for k, v in odds.items():
                t -= v
                if t <= 0:
                    break
            if k == 'harbour':
                A = harbours.anchor(db, P['x'], P['y'], P['r'], P['culture'], P['kind'])
                if A:
                    got = ('harbour', A)
            elif k == 'mine':
                M = _mine_spot(db, P, rng)
                if M:
                    got = ('mine', M)
            elif k == 'farm':
                F = _field_spots(db, P, FIELDS[P['kind']], rng, taken, near)
                if F:
                    got = ('farm', F)
            else:
                got = ('trade', None)
            odds.pop(k, None)
        kind, w = got or ('trade', None)
        if P['kind'] == 'farmstead':
            kind = 'farm' if w else ''
        P['trade'] = kind or 'farm'
        if kind == 'harbour':
            k_, x, y, phi, f = w
            out.append({'kind': 'harbour', 'label': 'harbour', 'x': round(x), 'y': round(y), 'phi': round(phi, 4), 'scene': k_, 'fit': f,
                        'of': [P['x'], P['y']], 'culture': P['culture']})
        elif kind == 'mine':
            x, y, rz = w
            egg = _dunmer(P['culture'])
            out.append({'kind': 'mine', 'label': 'egg mine' if egg else 'mine', 'x': round(x), 'y': round(y), 'z': round(mapdata_z(db, x, y) or 0),
                        'rz': round(rz, 3), 'culture': P['culture'], 'kit': 'cave_mud' if egg else 'cave_mold',
                        'name': _name(db, 'eggmine' if egg else 'mine', P['culture'], rng, used), 'of': [P['x'], P['y']]})
        elif kind == 'farm':
            for x, y, pts in w:
                taken.append((x, y))
                out.append({'kind': 'farm', 'label': 'farm', 'x': round(x), 'y': round(y), 'outline': pts, 'culture': P['culture'], 'of': [P['x'], P['y']]})
    return out


def _room(kind, x, y, placed, have):
    """Whether a place of the kind may stand at (x, y): its own kind's spacing, off the settlements, farmsteads, inns
    and dungeons laid and the places the land has."""
    sett = kind in SETTLEMENTS
    mine_r = RADIUS.get(kind) or (HAMLET_R if kind in HAMLETS else 0.0)
    sp = FIGS['spacing'].get(kind) or GROW['spacing'].get(kind, 0)
    if kind in SMALL_KINDS:
        for P in placed:
            d = math.hypot(P['x'] - x, P['y'] - y)
            if (P['kind'] == kind and d < sp) or d < (P['r'] + SMALL_GAP / 2 if 'r' in P else SMALL_GAP):
                return False
        return not any(math.hypot(hx - x, hy - y) < SMALL_GAP for hx, hy in have)
    for P in placed:
        d = math.hypot(P['x'] - x, P['y'] - y)
        if P['kind'] == kind and d < sp:
            return False
        if sett and P['kind'] in SETTLEMENTS and d < SETTLE_GAP:
            return False
        if 'r' in P and d < P['r'] + ((mine_r + (0.0 if sett else 1024.0)) if mine_r else DUNGEON_GAP):
            return False
        if 'r' not in P and P['kind'] not in SMALL_KINDS and d < (mine_r + DUNGEON_GAP if mine_r else DUNGEON_GAP):
            return False
    pad = mine_r + DUNGEON_GAP if mine_r else DUNGEON_GAP
    return not any(math.hypot(hx - x, hy - y) < pad for hx, hy in have)


def build_places(db, dungeons=(), farms=(), harbours_=(), say=None, small=(), labels=()):
    """The proposed works built as one change: the dungeons (and mines) with the dungeon generator, the farms' fields
    (storydress.lay_field), the harbours' docks (the game scene laid on the shore). Returns build_dungeons' answer
    and {'farms': [{id, things}], 'harbours': [{id, pieces}]}."""
    import cliffrocks
    import editing
    import harbours
    import storydress
    n0 = len(getattr(db.project, 'undo_stack', []) or [])
    r = build_dungeons(db, dungeons, say=say, fold=False) if dungeons else {'built': [], 'failed': [], 'learning': None}
    r['farms'], r['harbours'] = [], []
    for F in farms:
        try:
            got = storydress.lay_field(db, F['pts'], F.get('culture') or 'Hlaalu', 'farm', F.get('seed') or 1, clear=True)
            r['farms'].append({'id': F.get('id'), 'things': (got or {}).get('things', 0), 'plants': (got or {}).get('plants', 0),
                               'cleared': (got or {}).get('cleared', 0)})
        except Exception as e:
            r['failed'].append({'id': F.get('id'), 'why': str(e)})
    made = 0
    for H in harbours_:
        try:
            pcs = harbours.lay(db, int(H['scene']), float(H['x']), float(H['y']), float(H['phi']))
        except (IndexError, KeyError, ValueError) as e:
            r['failed'].append({'id': H.get('id'), 'why': 'the harbour scene is gone: propose again (%s)' % e})
            continue
        n = cliffrocks.place(db, pcs)
        made += n
        r['harbours'].append({'id': H.get('id'), 'pieces': n})
    if made:
        db.sync_project()
        editing.commit(db, 'Laid %d harbour%s' % (len(r['harbours']), '' if len(r['harbours']) == 1 else 's'))
    # (the small things: each the game's scene laid on the ground as it is now)
    import smallthings
    r['small'] = []
    made = 0
    for Q in small:
        try:
            pcs = smallthings.lay(db, Q['what'], int(Q['scene']), float(Q['x']), float(Q['y']), float(Q['phi']))
        except (IndexError, KeyError, ValueError) as e:
            r['failed'].append({'id': Q.get('id'), 'why': 'the scene is gone: propose again (%s)' % e})
            continue
        n = cliffrocks.place(db, pcs)
        made += n
        r['small'].append({'id': Q.get('id'), 'things': n})
    if made:
        db.sync_project()
        editing.commit(db, 'Laid %d small place%s' % (len(r['small']), '' if len(r['small']) == 1 else 's'))
    # (the land's names: each its cell's, as the game names Mount Kand's; a cell named already keeps its name)
    r['labels'] = []
    for Q in labels:
        key = '#' + str(Q.get('cell') or '')
        name = ' '.join(str(Q.get('name') or '').split())[:63]
        if not name or not re.match(r'#-?\d+,-?\d+$', key):
            continue
        try:
            c, _refs = editing._cell(db, key)
        except editing.EditError:
            continue
        from project import b64, unb64, zs
        hdr = [(t, unb64(d)) for t, d in c['header']]
        had = next((d for t, d in hdr if t == 'NAME'), b'')
        if had.strip(b'\0'):
            r['failed'].append({'id': Q.get('id'), 'why': 'cell %s has a name already' % key[1:]})
            continue
        out = [(t, zs(name) if t == 'NAME' else d) for t, d in hdr]
        if not any(t == 'NAME' for t, _d in out):
            out.insert(0, ('NAME', zs(name)))
        c['header'] = [[t, b64(d)] for t, d in out]
        c['props'] = True
        r['labels'].append({'id': Q.get('id'), 'cell': key[1:], 'name': name})
    if r['labels']:
        db.sync_project()
        editing.commit(db, 'Named %d place%s on the land' % (len(r['labels']), '' if len(r['labels']) == 1 else 's'))
    n1 = len(getattr(db.project, 'undo_stack', []) or [])
    if n1 - n0 > 1:
        nb = len(r['built']) + len(r['farms']) + len(r['harbours']) + len(r['small']) + len(r['labels'])
        editing.fold(db, n1 - n0, 'Built %d place%s' % (nb, '' if nb == 1 else 's'))
    return r


def build_dungeons(db, dungeons, say=None, fold=True):
    """The dungeon layers built with the dungeon generator, each a new place with its door outside at the layer's
    point; one Undo for them all. dungeons: [{id, kit, name, x, y, z, rz, size}]. Returns {'built': [{id, cell}],
    'failed': [{id, why}], 'learning': the kits still being learnt (theirs left for later) or None}."""
    import dwemer
    import editing
    import mapdata
    from editing import EditError
    built, failed, learning = [], [], []
    for n, D in enumerate(dungeons):
        if (D.get('kit') or 'cave_mud') in learning:
            continue
        if say:
            say('Building %d of %d' % (n + 1, len(dungeons)), n / max(1, len(dungeons)))
        x, y = float(D['x']), float(D['y'])
        g = mapdata.terrain_z(db, x, y)
        kit_ = D.get('kit') or 'cave_mud'
        cell_ = '#%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0))
        # (what the game builds round such a door outdoors: a ruin's towers, a cave's mouth in the rocks; the user,
        # 2026-11-12, "not just a door with an interior". A kind with none of its own, or none in this load order,
        # gets the door alone, as before)
        F = None
        try:
            import dungeonfront
            if dwemer.ready(db, kit_) is not None:
                F = dungeonfront.plan(db, kit_, x, y, float(D.get('rz') or 0), (mapdata.cell_info(db, cell_) or {}).get('region') or '',
                                      seed=D.get('seed') or 0)
        except Exception as e:
            print('dungeon front:', repr(e))
        try:
            r = dwemer.build(db, D.get('name') or 'A Place', D.get('size') or 'small', 'some', 'branching',
                             entrance={'cell': cell_, 'x': x, 'y': y,
                                       'z': F['z'] if F else (g if g is not None else D.get('z')),
                                       'rz': F['rz'] if F else float(D.get('rz') or 0)},
                             kind=kit_, outside_door=(F or {}).get('door') or None)
        except EditError as e:
            failed.append({'id': D.get('id'), 'why': str(e)})
            continue
        if r.get('learning'):
            # (the generator learns a kit's pieces first, in the survey process: that kit's wait for it, the rest go on)
            learning.append(D.get('kit') or 'cave_mud')
            continue
        if F:
            try:
                r['front'] = dungeonfront.build(db, F, D.get('name') or 'A Place')
            except Exception as e:
                print('dungeon front:', repr(e))
        built.append({'id': D.get('id'), 'cell': r.get('cell') or r.get('name') or D.get('name'), 'front': r.get('front') or None})
    if fold and len(built) > 1:
        editing.fold(db, len(built), 'Built %d dungeons' % len(built))
    return {'built': built, 'failed': failed, 'learning': ', '.join(learning) or None}
