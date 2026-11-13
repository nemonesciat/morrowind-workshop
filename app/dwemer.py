"""Dungeons (Dwemer ruins, caves, Velothi tombs, Daedric ruins), made the way the game's own are put together.

Morrowind's dungeons are built from tunnel pieces: dead ends, straights, ramps, corners, T-junctions and
crossroads, with door frames between them and big halls, chambers or rooms on the way. Each piece has fixed
openings, which the game fills nearly always (97-100% of the time in its 111 Dwemer ruins) and solid sides it
almost never touches (3-6%). The survey here learns, for each kind, from the game's own places of that kind:

- each piece's openings ("ports"): where on it the next piece joins, at what height, which way out
  (from the joint survey's relations, starting from a plain straight whose openings are its two ends);
- how a door frame stands at a seam, which doors stand in it and where, and where the front door stands
  (in a frame, or in the kind's own entrance piece, as a cave's exit);
- what the game puts in each kind of piece: its lights, rocks, urns, chests and creatures, as whole sets
  copied from real pieces of the game's places (a corner as one real corner had it, or bare, as often as
  the game leaves it bare).

The generator grows a network of tunnels from the front door: a main route with branches, ramps up and
down, halls or chambers on the way with the last one at the far end, door frames with doors at some seams,
and every open end closed by a dead end. No piece may run into another, on its own level or one above or
below. A seed makes the same place again. Measured and written up in packaging/nexus/dwemer-ruins-survey.md
and packaging/nexus/dungeons-survey.md. (The module keeps its first name: it began with the Dwemer ruins.)"""
import json
import math
import os
import random
import re
import struct
from collections import Counter, defaultdict

import editing
import mapdata
from editing import EditError
from esm import ENC
from project import b64, set_ref_pos, zs

V = 'v9'                                # (v9: TR's power box is dressing; v8: the game's joins of each pair of pieces, 'rels'; v7: a thing goes to the piece whose floor is under it, no sets from scaled pieces; v6: table tops; v3: no grass in caves; v2: platforms kept under what stands on them, no copies of pieces that had a door)
VG = 'v9'                              # the other kinds' surveys (v9: the pairs' joins, 'rels'; v8: the room tiles' dressings, from the game's tombs and Daedric rooms)
SIDES = {'E': (1, 0), 'W': (-1, 0), 'N': (0, 1), 'S': (0, -1)}
OPP = {'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N'}
PORT_SHARE = 0.6                        # a side is an opening when the game's pieces of the kind have a neighbour there this often
SLACK = 40                              # pieces' boxes may overlap by this much (their trims), as adjacency.TOL
# what a piece's dressing may hold: the game's lights, containers, creatures, loose things, and the pipes,
# furniture and sounds of its places (not other building pieces, doors, people or rubble across the way)
DRESS_TYPES = {'LIGH', 'CONT', 'CREA', 'LEVC', 'MISC', 'WEAP', 'ARMO', 'CLOT', 'BOOK', 'ALCH', 'INGR', 'APPA',
               'LOCK', 'PROB', 'REPA', 'LEVI'}
SUPPORTS = r'plat|plank|dock|board|shelf|table|bench|crate|rail|stair|ramp|beam|scaffold|ladder|log|bridge|walkway|step'
TABLES = re.compile(r'table|desk|counter')
# (the game's big masonry fire pit, copied with a cave's dressing: "not realistic in any of the three
# settings", the user, 2026-10-24; the camp fires are the furn_de_firepit_f ones)
MASONRY_FIRE = re.compile(r'^furn_de_firepit(_\d+)?$')
TOP_TYPES = {'MISC', 'INGR', 'BOOK', 'ALCH', 'APPA', 'WEAP', 'ARMO', 'CLOT', 'LIGH', 'REPA', 'PROB', 'LOCK'}
# (how many of a made place's bare tables are set with what the game's own dungeons keep on theirs, by the
# loot asked for: the user's Dwemer ruin had its tables bare, "put loot on tables and surfaces")
TOP_SHARE = {'sparse': 0.3, 'usual': 0.65, 'rich': 0.95}
# how much of each, as a share of what the game's own places of the kind hold: 1 is as the game's, 0 none, 2
# twice as much (the user: "normal and rich are just two comparatives that convey little"; sliders since
# 2026-10-25). The old words still read. Water is the share of the floors under water, 0 to 1.
AMOUNT_WORDS = {'creatures': {'none': 0.0, 'few': 0.5, 'usual': 1.0, 'many': 2.0},
                'loot': {'sparse': 0.5, 'usual': 1.0, 'rich': 2.0},
                'water': {'none': 0.0, 'pools': 0.05, 'flooded': 0.3}}
AMOUNT_TOP = {'creatures': 3.0, 'loot': 3.0, 'water': 1.0}


def amount(what, v):
    """A slider's value or one of the old words, as a number (see AMOUNT_WORDS)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = AMOUNT_WORDS[what].get(v, 0.0 if what == 'water' else 1.0)
    return max(0.0, min(AMOUNT_TOP[what], x))


def lived_share(occupants, K):
    """The chance someone lives in the place: the game's own share for the kind ('auto', None), or 0 to 1."""
    if occupants in (None, '', 'auto'):
        return 1.0 - K.get('empty', EMPTY_SHARE)
    if occupants == 'none':
        return 0.0
    if occupants == 'yes':
        return 1.0
    try:
        return max(0.0, min(1.0, float(occupants)))
    except (TypeError, ValueError):
        return 1.0 - K.get('empty', EMPTY_SHARE)
# tunnel pieces, halls (the game's 20/49/96 pieces with their halls; tiny: a lair). No huge: one cell of Dwemer or
# Daedric pieces boxed itself in near 90 tunnel pieces (2 growths in 15 under half); the game's biggest are several
# cells (Upper Level, Lower Level), left for later (the user, 2026-10-29)
SIZES = {'tiny': (8, 1), 'small': (16, 1), 'medium': (38, 2), 'large': (75, 3)}


def size_spec(size):
    """(tunnel pieces, halls) for a size, which may carry the Halls choice after a '+': 'large+many' has half as many
    halls again, 'large+few' one fewer (one at least). Carried in the size so a place made keeps it for Again."""
    base, _s, halls = (size or 'medium').partition('+')
    target, n = SIZES.get(base, SIZES['medium'])
    if halls == 'many':
        n = n + max(1, n // 2)
    elif halls == 'few':
        n = max(1, n - 1)
    return target, n


def halls_for(K, size):
    """(tunnel pieces, halls) for a size of this kind: size_spec's, or as many rooms as the game has to that many
    tunnel pieces of the kind (K['rooms10']: a cave of 38 tunnel pieces has 7 chambers, not 2), the Halls choice
    kept."""
    target, n = size_spec(size)
    r10 = (K or {}).get('rooms10')
    if r10:
        base, _s, halls = (size or 'medium').partition('+')
        m = max(1, int(round(target * float(r10) / 10.0)))
        if halls == 'many':
            m = m + max(1, m // 2)
        elif halls == 'few':
            m = max(1, m - max(1, m // 3))
        n = max(n, m) if halls != 'few' else max(1, m)
    return target, n


GROWS = 40          # growths tried for a layout that keeps the rules (dgrules), from seeds drawn from the one asked for
# A Dwemer ruin's last hall a machine hall, now and then. Of the 401 dressings the game's hall pieces have, some 25 hold one
# of its big machines (a belt drive in 8, a transmission 4, a dynamo 2, a steam engine 2, a great gear 2, a
# generator's hum 7; lab mh1, 2026-11-13), and they stand together in a few halls. So in MACHINE_SHARE of made ruins
# (drawn by the layout's seed) each tile of the last hall that has such a dressing takes one MACHINE_TILE of the
# time, MACHINE_MOST tiles at most; everywhere else, and in the other ruins, as before.
MACHINE = re.compile(r'furn_dwrv_(beltdrive|tranny|dynamo|steam)|in_dwrv_gear|sound_generator|turbine|centrifuge')     # (not the stove: every ruin has those)
MACHINE_SHARE, MACHINE_TILE, MACHINE_MOST = 0.5, 0.45, 5
FINAL_FULL = True   # the last chamber's dressing from the fullest third of the game's for its piece (_dress_refs)
AGREE = 0.85        # a piece whose learnt openings meet the game's joins less often than this is left out (corr2_03 0.5)
# (a chamber's: the game packs its tombs tight, so a tomb's burial room has other pieces against its walls
# a fifth of the time, joins that meet no opening; its doorway is used 80-90% of the time)
ROOM_AGREE = 0.5   # (room_08 and room_11, under it, leave holes: 25% of the rays from them escape)

# ------------------------------------------------------------------ the kinds
# tube: the tunnel pieces (and the kind's entrance pieces, whose openings are learnt the same way); base: a
# plain straight and the openings it might have (the one the game's joins agree with best is kept); rooms:
# the kind's chambers, laid as a whole piece where the Dwemer lay a hall from tiles; jamb: the door frame
# at a seam (its doors and the front door are learnt); dress: the statics a piece's dressing may hold.
KITS = {
    'dwemer': {
        'label': 'Dwemer ruin', 'tube': r'^in_dwrv_(corr\d|hall\d|shaft)', 'jamb': 'in_dwrv_doorjam00',
        'inner_door': 'door_dwrv_inner00', 'load_door': 'door_dwrv_load00', 'dead_end': 'in_dwrv_corr1_00',
        'base': 'in_dwrv_corr2_04', 'base_ports': [[[-128, 0, 0, 'W'], [128, 0, 0, 'E']]], 'halls': 'dwemer',
        # (the wide corridors' T and crossroads: the game joins them to their own corner, corr2_03, whose
        # openings don't agree; next to the narrow ones they leave gaps the eye sees through, 10-18% of
        # the rays from them against none in the game's ruins, 2026-10-24)
        # (and corr4_03, the crossing that leaks in the game's own ruins too, 5% of its eye rays: its voids
        # showed in the user's Nchudjak, Lower Bowels, 2026-10-25)
        'skip': r'^in_dwrv_(corr3_02|corr4_02|corr4_03|corr4_04)$',
        # (TR's power box: the machine the barrel rings and bearings stand round, 29 of its 35 in the game; left out,
        # its fittings floated round nothing, the user's "invisible dwemer machine", Nchudjack, Lower Bowels, 2026-10-30)
        'dress': r'^(furn_|dwrv_|ex_dwrv_pipe|in_dwe_pipe|sound_|light_|t_dwe_dngruin_f_|t_dwe_furn|active_|tr_m2_dwrv_powerbox)',
        'not_dress': r'boulder|rock|marker|mist|in_dwrv_(corr|hall|shaft|wall|doorjam)|door',
        # (fittings that only go with what they're fitted to: left out of a copied set when it isn't within reach)
        'fitted': [[r'barrelring|nchaz_bearing|barrellid', r'powerbox|barrel(?!ring|lid)|in_dwrv_gear|well', 200]],
        # (its shape, against the game's ruins of 29-48 tunnel pieces, the night of 2026-11-12: grown from its
        # shallow openings more than its deepest, with more junctions and four ring corridors, its far end is 17
        # pieces from the door (the game's 12, a made one's 22 before), it goes 576 down (576; 1152), its rooms
        # stand 5 pieces apart (4; 14) and its corridors close as many loops as three in four of the game's)
        'grow': (0.1, 0.45), 'rings': {'small': 1, 'medium': 4, 'large': 8}, 'rooms_near': 1800,
        'mix': {'T': 1.6, 'cross': 1.5, 'ramp': 0.6, 'dead end': 0.8},
        'setting': 'dwemer', 'empty': 0.53, 'prize': [['dwrv_chest10_rare'], ['in_dwe_cent_lev+2']],
        'more': 'in_dwe_all_lev+0', 'outside': ('dwrv', 'dwe'), 'example': 'Nchulmuz, Lower Halls',
        'ambi': ((38, 32, 28), (70, 60, 50), (20, 16, 14))},
    'tomb': {
        'label': 'Velothi tomb',
        'tube': r'^(in_velothismall_(corner_01|hall_0[134]|3way_0[12]|4way_01|cap_0[12]|stairs_01|stairslong_01|ramp_0[12]|ramplong_02|room_\d\d)|in_v_s_int_l?entrance_0[1-5])$',
        'rooms': r'_room_\d\d$', 'room_agree': ROOM_AGREE, 'jamb': 'in_velothismall_dj_01',
        # (and halls tiled from the tomb's own room tiles, 256 square: corners, walls and middles, and their
        # two-storey kin for a large tomb's last hall; the entrance tiles are learnt with the tunnels)
        'tiles': r'^in_v_s_int_l?(corner|wall|center)_0[12]$', 'tile': 256, 'tall': r'^in_v_s_int_l',
        # (of the tall entrances only lentrance_03 meets a tunnel at the hall's floor; _05 a storey up, its
        # stair down not learnt yet: no tall hall entered by it could be walked into, 2026-10-24)
        'entry_room': ['in_v_s_int_entrance_01', 'in_v_s_int_lentrance_03'], 'dead_end': 'in_velothismall_cap_01',
        # (3way_02: the game joins its third side 54% of the time, under PORT_SHARE, so it was learnt with two
        # openings and laid with its third side open on the void, 13.5% of its eye rays out against none in
        # the game's; lentrance_05 is a tall hall's entrance, laid as a tunnel it leaked 52%. The user's
        # Varensis Tomb, 2026-10-25)
        'skip': r'^(in_velothismall_3way_02|in_v_s_int_lentrance_05)$',
        # (the game's tombs climb and drop: stairs and ramps a fifth of their tunnel pieces, a quarter in the
        # user's good ones (Sarethi, Ravel, Tiranshiha), against 8% grown by the game's piece counts alone;
        # dead ends 11% (2%) against 18%, crossroads 3% against 5%. The user: "Take some examples of good
        # Velothi interiors. They aren't so haphazard. Even when they do sprawl")
        # (the night of 2026-11-12, against the game's tombs of 22-35 tunnel pieces: more junctions and growth from the
        # shallow openings bring the far end from 22 pieces off to 13 (the game's 5, its upper quarter 10), the depth
        # from 1024 to 512 (512), the rooms from 15 apart to 7 (3.7); stairs and ramps still more than by the game's
        # counts alone, dead ends still fewer than the game's, as the user's good ones have them)
        'mix': {'ramp': 1.6, 'dead end': 0.7, 'cross': 1.5, 'T': 2.0}, 'grow': (0.05, 0.6), 'rooms_near': 1800,
        'base': 'in_velothismall_hall_04', 'base_ports': [[[-128, 0, 0, 'W'], [128, 0, 0, 'E']], [[0, -128, 0, 'S'], [0, 128, 0, 'N']]],
        'halls': 'pieces', 'dress': r'^(furn_|light_|sound_|active_|in_v_s_wall_|in_velothismall_(column|fresco|pit)|in_velothi_ashpit|in_vs_pit|t_de_furn|t_de_var|t_de_setveloth_i_(debris|rubble))',
        # (no beds: nobody sleeps in a family tomb; the user saw one at the foot of a stair to nowhere)
        'not_dress': r'marker|door|_dj_|velothismall_(corner|hall|3way|4way|cap|stairs|ramp|room)|bed',
        'setting': 'tomb', 'empty': 0.8, 'prize': [['chest_tomb_large02', 'chest_tomb_large00'], ['in_tomb_all_lev+2']],
        'more': 'in_tomb_all_lev+0', 'outside': ('velothi',), 'example': 'Varethi Ancestral Tomb',
        'ambi': ((40, 34, 30), (60, 50, 40), (20, 18, 16))},
    'daedric': {
        'label': 'Daedric ruin',
        'tube': r'^in_dae_(hall_l_(01|corner|3way_01|4way_0[12]|stairs_01|staircurve[12]|endcap_01|entry_01)|hall_ruin_l_0[12]|doorjamb_load)$',
        'tiles': r'^in_dae_room_(l_floor_01|l_corner_0[12]|l_side_01|r_corner_0[12]|ruin_side_01)$',
        'roofs': r'^in_dae_room_(l_roof_0[13]|ruin_roof_03)$',
        # (4way_02 has a roof and no floor: the game hangs it over a pit with a waterfall; laid as a junction
        # it cut a whole made ruin off from its front door, 2026-10-24)
        'skip': r'^in_dae_hall_l_4way_02$',
        'jamb': 'in_dae_doorjamb_01', 'dead_end': 'in_dae_hall_l_endcap_01', 'entry_room': 'in_dae_hall_l_entry_01',
        'base': 'in_dae_hall_l_01', 'base_ports': [[[0, -256, 0, 'S'], [0, 256, 0, 'N']], [[-256, 0, 0, 'W'], [256, 0, 0, 'E']]],
        'halls': 'tiled', 'dress': r'^(furn_|light_|sound_|active_|in_dae_(rubble|pillar|claw|platform)|ex_dae_(pillar|claw)|t_glb_var_|t_dae_dngruin_\w*(rubble|debris|claw|pillar))',
        'not_dress': r'marker|door|in_dae_(room|hall|doorjamb|mezzanine)',
        'shrine': r'statue|^ex_dae_(azura|boethiah|malacath|molagbal|mehrunesdagon|sheogorath|mephala|vaermina|namira|hircine|clavicus|peryite|sanguine|nocturnal|meridia)|^active_dae_',
        'setting': 'daedric', 'empty': 0.5, 'prize': [['com_chest_daed_ruin_01'], ['in_dae_dremora_lev+0', 'in_dae_all_lev+0']],
        # (its shape, 2026-11-13, as the other kinds' of the night before: a medium ruin's first room 7 pieces from the
        # door (13 before), its rooms 10 apart (22), 3 of them (2), the far end 18 pieces off (20); a large one still
        # reaches its size (64 pieces of 75 asked, 63 before; with a room to every ten it fell to 42). The game's own
        # rooms could not be read for a figure: its ruins are split over many small places)
        'grow': (0.1, 0.45), 'rooms10': 0.7, 'rooms_near': 2600,
        'more': 'in_dae_all_lev+0', 'outside': ('dae',), 'example': 'Zaintashara, Shrine',
        'ambi': ((30, 40, 40), (10, 10, 10), (31, 44, 41))},
    # the Chimer keeps' lower and upper levels (Andasreth, Hlormaren, Marandus: 38 places): corridors round the rooms,
    # each room off a corridor's side passage (corr3_01's east side, a short passage, corr2_07, then a door frame and
    # the room's doorway tile, hall02: 162 of 191 times), the rooms tiled from 256 tiles. Seeded by hand: the side
    # passage's opening and the doorway's, which the game uses a third of the time (a plain alcove or wall the rest),
    # and the corridor's end, a wall across it, which the game rarely needs (its corridors run round in rings)
    'stronghold': {
        'label': 'Chimer stronghold', 'tube': r'^in_stronghold_(corr2_0[0145-7]|corr3_01|stairs00|hall02|wall00)$',
        'tiles': r'^in_stronghold_hall0[0134]$', 'tile': 256, 'jamb': 'in_strong_doorjam00',
        'dead_end': 'in_stronghold_wall00', 'entry_room': 'in_stronghold_hall02', 'room_lead': 'in_stronghold_corr2_07',
        'room_t': 'in_stronghold_corr3_01',
        # (the short passage has a frame in its middle, a door in it when it leads into a room)
        'framed': ('in_stronghold_corr2_07',), 'unbacked': True,
        'base': 'in_stronghold_corr2_04', 'base_ports': [[[0, -256, 0, 'S'], [0, 256, 0, 'N']]],
        'seed_ports': {'in_stronghold_corr2_07': [[-128, 0, 0, 'W'], [128, 0, 0, 'E']],
                       'in_stronghold_corr3_01': [[0, 256, 0, 'N'], [0, -256, 0, 'S'], [128, 0, 0, 'E']],
                       'in_stronghold_hall02': [[0, 128, 0, 'N']], 'in_stronghold_wall00': [[-24, 0, 0, 'W']],
                       # (the stairs a storey up, from a short passage to one: 56 of the game's, its joins 0.59 of the time)
                       'in_stronghold_stairs00': [[-256, 0, 0, 'W'], [256, 0, 320, 'E']]},
        # (and those joins, which the frame between them hides from the survey: B in A's frame, each way)
        'seed_rels': {'in_stronghold_corr3_01|in_stronghold_corr2_07': [[256, 0, 0, 0], [256, 0, 0, 180]],
                      'in_stronghold_corr2_07|in_stronghold_hall02': [[-256, 0, 0, 90], [256, 0, 0, 270]]},
        # (straights 0.4: by the game's counts alone a keep grew one corridor 6000 long; the game's turn round their rooms)
        'mix': {'straight': 0.4, 'corner': 1.5},
        'halls': 'tiled', 'room_sizes': ((3, 2), (3, 3), (4, 3), (3, 4), (4, 4), (5, 4)),
        'dress': r'^(furn_|light_|sound_|active_|in_lava_blacksquare|in_strong_rubble|in_stronghold_lpill|t_de_furn|t_com_var|t_glb_var_(spider|web))',
        'not_dress': r'marker|door|in_strong(hold|ruin)?_(corr|hall|wall|divider|stairs|roof|dome|arch)|_doorjam',
        'setting': 'stronghold', 'empty': 0.35, 'prize': [['crate_bandit_01', 'barrel_bandit_01'], ['in_dae_all_lev+2']],
        'more': 'in_dae_all_lev+0', 'outside': ('strong',), 'example': 'Andasreth, Lower Level',
        'ambi': ((15, 15, 18), (14, 18, 18), (27, 34, 35))},
    # the Legion forts' insides (in_impsmall: 150-odd game places, Moonmoth, Buckmoth, the Ebon Tower keeps): corridors
    # of 256, a corner, a T, a crossing, stairs, an end cap, and rooms tiled from the r_ tiles (a corner, a side, an
    # open middle, and the entrance tiles with the doorway), door frames with their doors (2026-11-04)
    'fort': {
        'label': 'Imperial fort',
        'tube': r'^in_impsmall_(corner_01|hall_0[123]|3way_01|4way_01|endcap_01|stairs_01|r_entr_0[1-4]|spiral_01|spiral_bot_01|spiral_end_01|wall_01)$|^in_impbig_blend_01$',
        'tiles': r'^in_impsmall_r_(corner_0[1-3]|center_01|3way_01)$|^in_impbig_(4way|wall)_01$', 'tile': 256, 'halls': 'tiled',
        'entry_room': ['in_impsmall_r_entr_01', 'in_impsmall_r_entr_02', 'in_impsmall_r_entr_03', 'in_impsmall_r_entr_04'],
        'jamb': 'in_impsmall_doorjam_01', 'dead_end': 'in_impsmall_endcap_01',
        'base': 'in_impsmall_hall_01', 'base_ports': [[[0, -128, 0, 'S'], [0, 128, 0, 'N']]],
        # (the short hall (128 long, its floor 128 over its origin) is joined at both ends in the game, 167 of them, its
        # neighbours 192 along and 128 up either way; its south end had a neighbour in 57% of them, under the 60% a learnt
        # opening needs, so it was learnt with one opening and laid as a dead end whose open end showed the void: 16 of
        # 120 fort layouts refused, 2026-11-05. Both ends set by hand from the game's joins; 'v' learns the kind again)
        # (the spiral stair's doorways, the big halls' doorway slab and the wall plate the game closes a spiral's unused
        # doorway with, all set by hand from the game's joins: the keep study of 2026-11-05, lab j_rels. A spiral turn,
        # 512 tall from 384 under its origin, has a doorway on its west and north faces at each of its two landings, their
        # floors 128 under its origin (the doorways 256 under it are the turn below's); the plate closes one 28 inside
        # its face. The stairs' openings set by hand too: learnt, they agree 0.80 with the game's joins and the ramp was
        # never grown, every made fort flat)
        'seed_ports': {'in_impsmall_hall_03': [[0, 64, 128, 'N'], [0, -64, 128, 'S']],
                       'in_impsmall_stairs_01': [[0, 128, 0, 'N'], [0, -128, 128, 'S']],
                       'in_impsmall_spiral_01': [[-128, 0, 0, 'W'], [0, 128, 0, 'N']],
                       'in_impsmall_spiral_bot_01': [], 'in_impsmall_spiral_end_01': [],
                       'in_impbig_blend_01': [[-128, 0, 0, 'W']], 'in_impsmall_wall_01': [[-128, 0, 128, 'E']]}, 'v': 'f6',
        # (the spiral, the plate and the big halls' pieces are laid by their own rules, never grown as tunnel pieces)
        'skip': r'^in_impsmall_(spiral|wall_01)|^in_impbig_',
        'plate': 'in_impsmall_wall_01',
        # the spiral stair tower (the game's keeps climb by it, their curtain towers are stacks of it with a room at each
        # landing): one full turn a piece, 256 up each, one over another (Caldera's Governor's Hall, Buckmoth's Towers:
        # 256 apart; the face survey saw only the pairs 512 apart, whose boxes don't overlap), a floor piece under the
        # lowest and a cap at the top landing with the trap door to the roof over it, in the turn's frame
        'spiral': {'piece': 'in_impsmall_spiral_01', 'rise': 256, 'bot': ['in_impsmall_spiral_bot_01', 256, -128, -256, 270],
                   'end': ['in_impsmall_spiral_end_01', 0, 0, -128, 270], 'trap': ['in_impsmall_trapdoor_01a', -64, 0, 0, 90]},
        # the big halls (in_impbig: Ebon Tower's High Chambers and Library, Ember Keep's Great Hall): 512 tiles open on all
        # four sides, a wall slab in each outer opening, a doorway slab with its steps where a corridor comes in (the hall's
        # floor lies 128 under the corridor's), in the tile's frame; the frame and door in the doorway as the game's stand
        'big': {'tile': 'in_impbig_4way_01', 'wall': 'in_impbig_wall_01', 'blend': 'in_impbig_blend_01', 'pitch': 512,
                'wall_at': {'S': [0, -32, 0, 0], 'N': [0, 32, 0, 180], 'W': [-32, 0, 0, 90], 'E': [32, 0, 0, 270]},
                'blend_at': [-128, 0, -128, 0], 'jamb_at': [-128, 0, 0, 0], 'door_at': [-128, -56, -32, 180],
                'sizes': ((2, 2), (3, 2), (2, 3), (3, 3), (4, 2), (4, 3)), 'share': 0.3},
        # (as the game's keeps turn: corners as often as straights, junctions 18% of the corridor, ramps 11%; and ring
        # corridors, 1 in a medium keep and 2 in a large one tried for, the keep study's 49 rings in 68 interiors)
        'mix': {'corner': 1.3, 'straight': 0.7, 'ramp': 1.4, 'T': 1.2, 'cross': 1.1},
        'rings': {'small': 0.5, 'medium': 1, 'large': 2},
        # (a fort made on its own, 2026-11-13: the first room 5 pieces from the door (9 before), rooms 8 apart (13), 3 in
        # a medium one (2); a keep's planned interior is not touched, halls_for and _grow leave it its own)
        'grow': (0.1, 0.45), 'rooms10': 0.7, 'rooms_near': 1800,
        'dress': r'^(furn_|light_|sound_|active_|in_impsmall_(r_pillar|shutter)|in_imp_fireplace|t_imp_furn|t_imp_var|t_com_(furn|var)|t_glb_var)',
        'not_dress': r'marker|door|in_impsmall_(corner|hall|3way|4way|endcap|stairs|spiral|r_(corner|center|entr|3way)|doorjam|wall|dj_)|in_impbig_',
        # (who lives there: the game's own in_impsmall forts hold garrisons or nobody (97 places, 5.1 people a place, 11 with
        # nobody, not one hostile band, lab j_fortcast 2026-11-05), so the band of an abandoned one is the game's hideouts'
        # (bandits in 31 of 37), living in the rooms as a garrison would, 'camp': 'rooms', as many as the game's forts hold)
        'setting': 'hideout', 'empty': 0.11, 'camp': 'rooms', 'prize': [['chest_small_02_lev_gold', 'com_chest_02_lev_gold'], []],
        # (rooms of one theme, hall tiles dressed to their walls, _dress_refs; no hanging without its wall, no rug off its
        # floor, nothing set down on the floor when its table goes, _keep_tidy and _orphans; shelves with their wall)
        'themes': True, 'tidy': True, 'unbacked': True,
        'more': None, 'outside': ('imp',), 'example': 'Fort Vanvuld',
        'ambi': ((48, 44, 40), (90, 84, 72), (26, 24, 22))},
    # the sewers under the cantons (in_sewer: the Underworks of Vivec and Molag Mar, 21 game places): small corridors of
    # 512 and big ones of 1024, their joints, a canal hall, a collapsed stretch; the way in is a grate in a corridor's end,
    # as the game's are (no door frame of their own: the front door stands in the piece the game stands it in)
    'sewer': {
        'label': 'Sewer', 'tube': r'^in_sewer_(bcorr[1-3]_0\d|scorr\d_0\d)$',
        'rooms': r'^in_sewer_bcorr3_00$', 'room_agree': 0.4, 'halls': 'pieces',
        # (the openings carry their floors' heights, as the walk probe at a join wants them within 260: a small corridor's
        # floor lies 230 under its origin, a big one's walkway 240 and its channel 400 (the meshes, lab j_sewer2))
        'dead_end': 'in_sewer_scorr1_00', 'base': 'in_sewer_scorr2_00', 'base_ports': [[[0, -256, -200, 'S'], [0, 256, -200, 'N']]],
        # (the big corridors' openings set by hand from the game's joins: their neighbours stand 1024 along them, the
        # dead end's 768 off, and the T's stem meets the small corridors 512 up it and 64 higher, where the game's joint
        # plate stands. Learnt through the joint plates (in_sewer_union00, both its openings at its origin) they came out
        # skewed, 2026-11-04)
        'seed_ports': {'in_sewer_bcorr2_04': [[512, 0, -250, 'E'], [-512, 0, -250, 'W']],
                       'in_sewer_bcorr3_00': [[512, 0, -250, 'E'], [-512, 0, -250, 'W'], [0, 512, -136, 'N']],
                       'in_sewer_bcorr1_01': [[-256, 0, -250, 'W']], 'in_sewer_bcorr1_00': [[-256, 0, -250, 'W']]},
        'dress': r'^(furn_|light_|sound_|active_|in_sewer_(pillar|raft|anchor)|in_m_sewer_(column|fountain|niche|drain|arch)|t_de_furn|t_com_var|t_glb_var|in_v_s_wall)',
        'not_dress': r'marker|door|in_sewer_(bcorr|scorr|union|canal|collapse|ent_)',
        'setting': 'sewer', 'empty': 0.45, 'prize': [['chest_small_02_lev_gold', 'com_chest_02_lev_gold'], []],
        'more': None, 'outside': ('sewer', 'trapdoor', 'grate'), 'example': 'Sadrith Vos, Underworks',
        'ambi': ((30, 34, 30), (40, 44, 40), (16, 18, 16))},
    # the Ayleid ruins of Cyrodiil (Tamriel Data's t_ayl_dngruin set, 20 game places with Project Cyrodiil), set from the
    # game's own joins the night of 2026-11-12 (lab dn3, dn4): narrow halls of 512 (a straight, a turn, a T, a crossing,
    # a stair 384 down), rooms tiled from 512 wall, corner and floor tiles, a ceiling over each floor tile (the wall and
    # corner tiles carry their own), the room's doorway its wall tile with the way out (roomwallext_01, a frame in it).
    # An opening nothing joins is closed with the plate the game closes it with (hallend_02, set at the hall's own
    # origin and turned to the opening: 22 of the game's 28), so its opening is given at the hall's end, facing back.
    # The front door is the stone door the game stands in a hall's end with no frame (doorstone_02 at (0, -256, 144)
    # of widehtrans_01, hall_01, hallturn_01 and roomwallext_01 alike). Learnt alone, the T had two openings (its third
    # side joined 59% of the time, under the 60 an opening needs), the crossing none (it was not among the pieces), the
    # room's doorway none, and the plain hall was taken for the room's doorway: a made ruin stopped at one piece, 0-1
    # layouts of 8 kept the rules. The pits and the spiral entrance are not built yet (the wide halls came the day after).
    'ayleid': {
        'label': 'Ayleid ruin',
        # (the wide halls, 2026-11-13: 448 wide and 680 high, a straight, a T, a crossing, a corner, a stair 384 down,
        # the piece that goes from narrow to wide, and their own dead end, the alcove of burial niches the game closes
        # a wide opening with 104 times; a room off a wide hall has the wide doorway tile, roomwallextw_01)
        'tube': r'^t_ayl_dngruin_i_(hall_01|hallturn_01|hall3way_01|hall4way_01|hallstair_01|hallend_02|roomwallext_01|roomwallextw_01'
                r'|wideh_01|wideh3way_01|wideh4way_01|wideh4crn_01|widehstair_01|widehtrans_01|widehcat_01)$',
        'tiles': r'^t_ayl_dngruin_i_(roomwall_01|roomcrn_01|roomflr_01)$', 'tile': 512,
        'roofs': r'^t_ayl_dngruin_i_roomceiling_0\d$', 'roof': 't_ayl_dngruin_i_roomceiling_01',
        'halls': 'tiled', 'entry_room': ['t_ayl_dngruin_i_roomwallext_01', 't_ayl_dngruin_i_roomwallextw_01'],
        'jamb': 't_ayl_dngruin_i_doorframe_03', 'dead_end': 't_ayl_dngruin_i_hallend_02',
        'base': 't_ayl_dngruin_i_hall_01', 'base_ports': [[[0, -256, 0, 'S'], [0, 256, 0, 'N']]],
        'seed_ports': {'t_ayl_dngruin_i_hallturn_01': [[-256, 0, 0, 'W'], [0, -256, 0, 'S']],
                       't_ayl_dngruin_i_hall3way_01': [[0, 256, 0, 'N'], [0, -256, 0, 'S'], [-256, 0, 0, 'W']],
                       't_ayl_dngruin_i_hall4way_01': [[0, 256, 0, 'N'], [0, -256, 0, 'S'], [-256, 0, 0, 'W'], [256, 0, 0, 'E']],
                       't_ayl_dngruin_i_hallstair_01': [[0, 256, 0, 'N'], [0, -256, 384, 'S']],
                       't_ayl_dngruin_i_hallend_02': [[0, 256, 0, 'S']],
                       't_ayl_dngruin_i_roomwallext_01': [[256, 0, 0, 'E']],
                       't_ayl_dngruin_i_roomwallextw_01': [[256, 0, 0, 'E']],
                       't_ayl_dngruin_i_wideh_01': [[0, 256, 0, 'N'], [0, -256, 0, 'S']],
                       't_ayl_dngruin_i_wideh3way_01': [[0, 256, 0, 'N'], [0, -256, 0, 'S'], [256, 0, 0, 'E']],
                       't_ayl_dngruin_i_wideh4way_01': [[0, 256, 0, 'N'], [0, -256, 0, 'S'], [-256, 0, 0, 'W'], [256, 0, 0, 'E']],
                       't_ayl_dngruin_i_wideh4crn_01': [[0, 256, 0, 'N'], [256, 0, 0, 'E']],
                       't_ayl_dngruin_i_widehstair_01': [[0, -256, 0, 'S'], [0, 256, 384, 'N']],
                       't_ayl_dngruin_i_widehtrans_01': [[0, -256, 0, 'S'], [0, 256, 0, 'N']],
                       't_ayl_dngruin_i_widehcat_01': [[-256, 0, 0, 'W']]},
        # (which dead end closes which opening: a wide one the alcove, never the narrow hall's plate)
        'dead_of': [[r'i_wideh(?!trans)|i_roomwallextw', 't_ayl_dngruin_i_widehcat_01'], [r'i_widehtrans_01@N', 't_ayl_dngruin_i_widehcat_01']],
        # (the plate in each piece's frame: at its origin, turned to the opening it closes)
        'seed_rels': {'t_ayl_dngruin_i_hall_01|t_ayl_dngruin_i_hallend_02': [[0, 0, 0, 0], [0, 0, 0, 180]],
                      't_ayl_dngruin_i_hallturn_01|t_ayl_dngruin_i_hallend_02': [[0, 0, 0, 270], [0, 0, 0, 180]],
                      't_ayl_dngruin_i_hall3way_01|t_ayl_dngruin_i_hallend_02': [[0, 0, 0, 0], [0, 0, 0, 180], [0, 0, 0, 270]],
                      't_ayl_dngruin_i_hall4way_01|t_ayl_dngruin_i_hallend_02': [[0, 0, 0, 0], [0, 0, 0, 90], [0, 0, 0, 180], [0, 0, 0, 270]],
                      't_ayl_dngruin_i_hallstair_01|t_ayl_dngruin_i_hallend_02': [[0, 0, 0, 0], [0, 0, 384, 180]],
                      't_ayl_dngruin_i_widehtrans_01|t_ayl_dngruin_i_hallend_02': [[0, 0, 0, 180]],
                      't_ayl_dngruin_i_wideh_01|t_ayl_dngruin_i_widehcat_01': [[0, 512, 0, 270], [0, -512, 0, 90]],
                      't_ayl_dngruin_i_wideh4crn_01|t_ayl_dngruin_i_widehcat_01': [[0, 512, 0, 270], [512, 0, 0, 0]],
                      't_ayl_dngruin_i_widehstair_01|t_ayl_dngruin_i_widehcat_01': [[0, -512, 0, 90], [0, 512, 384, 270]],
                      't_ayl_dngruin_i_widehtrans_01|t_ayl_dngruin_i_widehcat_01': [[0, 512, 0, 270]]},
        # (the front door, by hand: [id, its place from the way in's opening, turned], no frame)
        'front': ['t_ayl_dngruin_doorstone_02', [0, 0, 144, 0]],
        # (door records the game hangs as dressing: the light panels, 639 of them, one by each light fixture; the beds)
        'door_dress': r'doorlightfix|_f_bed_',
        # (its crates, chests and pedestals set down on the floor, _settle)
        'settle': r'_var_cr\d|dngruin_ch\d|i_pedestal',
        'room_sizes': ((3, 2), (3, 3), (4, 3), (3, 4), (4, 4)), 'v': 'a4',
        # (its shape, as the other kinds' of that night: a room to every eight halls (the game's ruins are mostly rooms:
        # 400 room tiles to its 350 hall pieces), the first 4 pieces from the door, rooms 8 apart, the far end 18 pieces
        # off in a ruin of 40 (22 before, rooms 21 apart), three stairs down at most)
        'grow': (0.1, 0.45), 'rooms10': 1.2, 'rooms_near': 2600, 'mix': {'T': 1.5, 'cross': 2.0, 'ramp': 0.7},
        'dress': r'^(furn_|light_|sound_|active_|t_ayl_dngruin_(doorlightfix|f_|i_(lightfix|welkynd|pedestal|rubble|block|divider|chain|hallfitting|secrwall|roomcol))|t_ayl_dngruin_x_(iblock|oblock)|t_glb_var|t_com_var|t_cyr_var)',
        'not_dress': r'marker|door(?!lightfix)|t_ayl_dngruin_i_(hall(?!fitting)|wideh|room(wall|crn|flr|ceiling)|pit|tower|entrance|doorframe)',
        'setting': 'ruin', 'empty': 0.5, 'prize': [['com_chest_02_lev_gold', 'chest_small_02_lev_gold'], []],
        # (its doors outdoors lead into entrance halls of the wide pieces: its fronts are found from those, dungeonfront)
        'more': None, 'outside': ('ayl',), 'front_tube': r'^t_ayl_dngruin_i_(hall|wideh|room|pit|entrance)', 'example': 'Varondo',
        'ambi': ((28, 36, 44), (40, 50, 70), (20, 26, 34))},
}
for _rock, _name, _ex in (('mold', 'grey stone', 'Sarnabi Cave'), ('mud', 'brown earth', 'Hlormar Egg Mine'),
                          ('py', 'pale rock', 'Ashurnibi Cave'), ('lava', 'lava rock', 'Mabrelet Cave')):
    KITS['cave_' + _rock] = {
        'label': 'Cave (%s)' % _name,
        'tube': r'^in_%scave(2_s_0[0-6]|2_s_end|4_s_00|_\d\d|_exit00|_nat_exit00)$' % _rock,
        'rooms': r'cave_\d\d$', 'skip': r'_nat_exit00$', 'dead_end': 'in_%scave2_s_end' % _rock, 'base': 'in_%scave2_s_00' % _rock,
        'base_ports': [[[0, 0, 0, 'S'], [0, 256, 0, 'N']], [[-256, 128, 0, 'W'], [256, 128, 0, 'E']]],
        'halls': 'pieces', 'dress': r'^(furn_|light_|sound_|active_|flora_|in_(mold|mud|py|lava)_rock|in_(mold|mud|py|lava)boulder|in_cave_plant|'
                                    r'in_cavern_(beam|wallmount|stairs|ramp|rail)|in_%scave_(stal|form)|in_lava_blacksquare|t_mw_cave\w*stalag|t_mw_kwa_(vein|web|egg)|'
                                    # (the ways up and the platforms things stand on: kept with the rest)
                                    r'ex_common_plat|ex_de_shack_plank|ex_de_docks|ex_de_railing|t_cr_goblin_plank|ladder)' % _rock,
        # (and no grass, ferns, bushes or trees: little that's green grows without the sun; the user saw grass
        # in a made cave. Mushrooms, moss, vines and fungus stay)
        'not_dress': r'marker|door|cave(2_s_|4_s_|_\d\d|_exit|_nat_exit|_doorway)|grass|fern|bush|shrub|tree|flower|sapling|reed|heather|_bc_?bush',
        # (the night of 2026-11-12, against the game's caves: a chamber to every six tunnel pieces (the game's 1.8 to
        # ten; a made cave of 38 had two), the first 5 pieces from the door (6; 15), chambers 5 apart (3.8; 18), the far
        # end 20 pieces off (11 in a cave two thirds the size; 31))
        'grow': (0.2, 0.3), 'rooms10': 1.6, 'rings': {'small': 0.3, 'medium': 1, 'large': 2}, 'mix': {'cross': 1.6},
        'setting': 'cave', 'empty': 0.45, 'prize': [['chest_small_02_lev_gold', 'com_chest_02_lev_gold', 'crate_smuggler_01'], []],
        'more': None, 'outside': ('cave',), 'example': _ex, 'ambi': ((40, 36, 32), (50, 46, 40), (18, 16, 14))}
# Velothi towers (the guide's and the game's: Shishara, Hanud, Nim, Odirniran, 70 places with a pit): the tomb's small
# Velothi halls and rooms, ending in the tower itself, the pit (in_velothismall_pit_01/02), a two-storey room with its
# steps up the side, columns and dome, laid as the game dresses each; learnt only from the places with a pit. They
# climb from the door (Shishara: the way in at -256, the halls 0 to 128, the pit at 256), and people live in them
KITS['tower'] = dict(KITS['tomb'],
    # (its own shape settings, 2026-11-13, measured climbing: the far end 15 pieces from the door in a tower of 37
    # (22 before; the game's 8 in one of 27), the climb 1152 (1408; 640), the rooms 11 apart (17; 3))
    grow=(0.1, 0.45), rooms_near=1800, rooms10=0.7,
    label='Velothi tower', must=r'^in_velothismall_pit_0[12]$',
    tube=KITS['tomb']['tube'][:-2] + r'|in_velothismall_pit_0[12])$',
    rooms=r'_room_\d\d$|_pit_0[12]$', final_room=r'_pit_0[12]$', tall=None, joins_from='tomb', v='t2',
    # (pit_02, the common pit, 59 of 78: its joins agree 0.42, the game reaches it from halls and corners alike)
    room_agree=0.4,
    # (the tower's own build, laid with its dressing but never cleared as in the way: the steps up the pit's sides (in
    # all 38 of the game's pit dressings), its dome, columns, rails, galleries and upper floor. The clearing took the
    # steps out of every made tower, the user's two storeys left with no way up)
    fixed=r'^in_velothismall_(pitstep|dome|column|rail|curve|ceiling|wall_03|ramp_03)|^in_v_s_int_lcolumn|^in_vs_pit|^in_velothi_platform',
    dress=KITS['tomb']['dress'][:-1] + r'|in_velothismall_(dome|ceiling|wall_03|rail|curve)|in_vs_pit|in_velothi_platform)',
    # (beds stay: the resident mage sleeps upstairs)
    not_dress=r'marker|door|_dj_|velothismall_(corner|hall|3way|4way|cap|stairs|ramp|room|pit_0)',
    mix={'ramp': 2.0, 'dead end': 0.4, 'cross': 0.5},
    # (the pit's lower room furnished: from its floor, 256 under its origin, to 200 over it, 20 things or more)
    furnished={r'_pit_0[12]$': (-280, -56, 20)},
    setting='tower', household=True, empty=0.15, prize=[['chest_small_01', 'com_chest_02'], []], more=None,
    outside=('velothi',), example='Shishara', way='up',
    ambi=((40, 36, 32), (70, 62, 52), (24, 22, 20)))
# A tomb with the domed great room for its last one (the user's model of a great Velothi dungeon, Tiranshiha: "a
# dome-roofed bedroom over a summoning stage ... made tombs should sometimes include it, whole, with its dressing").
# The room is the towers' pit under its dome (in_velothismall_pit_02 with dome_01 over it 64 times of 67, steps up
# its sides): of the game's 231 tombs 6 hold one (lab dome1, 2026-11-13), so it is no tomb's by rule and a made tomb
# gets it now and then by choice, DOME_SHARE of the medium and large ones (variant). Not a kind of its own to choose:
# the tomb's own kit and learning, with the pit, its joins and its dressings taken from the towers' (survey), laid
# as the last room only and kept whole by every clean-up ('fixed'). Rules and figures as a tomb's ('as').
KITS['tomb_dome'] = dict(KITS['tomb'],
    tube=KITS['tower']['tube'], rooms=KITS['tower']['rooms'], final_room=KITS['tower']['final_room'],
    fixed=KITS['tower']['fixed'], furnished=KITS['tower']['furnished'], merge_from=('tomb', 'tower'), **{'as': 'tomb'})
DOME_SHARE = 0.12


def variant(db, kind, size, seed):
    """The kit a place of this kind, size and seed is made from: the kind itself, or a variant of it that the seed
    draws (a tomb with the domed great room). The same seed draws the same, in the plan and in the build."""
    if kind == 'tomb' and DOME_SHARE > 0 and (size or 'medium').partition('+')[0] in ('medium', 'large') \
            and random.Random('%s|dome' % seed).random() < DOME_SHARE:
        try:
            if ready(db, 'tomb_dome') is not None:
                return 'tomb_dome'
        except Exception as ex:
            print('dungeon variant:', repr(ex))
    return kind


def _merged(db, kind):
    """A variant's survey: its first kind's whole, with the last room's pieces (K['final_room']), their joins and
    their dressings from its second's. None while either is still being learnt."""
    K = kit(kind)
    key = (id(db.recs), kind)
    if key in _cache:
        return _cache[key]
    a, b = K['merge_from']
    A, B = ready(db, a), ready(db, b)
    if A is None or B is None:
        return None
    own = re.compile(K['final_room'])
    out = dict(A)
    for k_ in ('ports', 'n', 'agree', 'dress', 'side_share', 'companions'):
        out[k_] = dict(A.get(k_) or {})
        for pid, v in (B.get(k_) or {}).items():
            if own.search(pid):
                out[k_][pid] = v
    # (the pit's joins agree 0.42 with the game's, which reaches it from halls and corners alike: taken as it is)
    for pid in list(out['ports']):
        if own.search(pid):
            out['agree'][pid] = max(out['agree'].get(pid) or 0, 1.0)
    out['rels'] = dict(A.get('rels') or {})
    for rk, v in (B.get('rels') or {}).items():
        if any(own.search(x) for x in rk.split('|')):
            out['rels'][rk] = v
    out['kind'] = kind
    _cache[key] = out
    return out


# (the sewer kit is groundwork, not offered yet: the Underworks' small corridors meet at joint plates whose openings sit
# at their origins, so their openings came out skewed and every layout broke a rule (the dungeon round of
# 2026-11-04/05, test8 notes). The Ayleid kind is offered where its pieces are in the load order, 2026-11-12)
KINDS = ('dwemer', 'cave_mold', 'cave_mud', 'cave_py', 'cave_lava', 'tomb', 'daedric', 'stronghold', 'tower', 'fort', 'ayleid')

_cache = {}
_thread = {}
# the Dwemer roles of each tunnel piece, for the growth's mix and the write-up (the other kinds' roles come
# from their learnt openings)
ROLE = [(r'^in_dwrv_corr1', 'dead end'), (r'^in_dwrv_corr2_0[03]$', 'corner'), (r'^in_dwrv_corr2_01$', 'ramp'),
        (r'^in_dwrv_corr2', 'straight'), (r'^in_dwrv_corr3', 'T'), (r'^in_dwrv_corr4', 'cross'),
        (r'^in_dwrv_hall', 'hall'), (r'^in_dwrv_shaft', 'shaft')]
HALL_TILES = ('in_dwrv_hall2_00', 'in_dwrv_hall3_00', 'in_dwrv_hall4_00')
HALL_EXITS = ('in_dwrv_hall4_01', 'in_dwrv_hall4_02', 'in_dwrv_hall4_03')


def kit(kind):
    K = KITS.get(kind or 'dwemer')
    if K is None:
        raise EditError('There is no dungeon kind "%s" (%s).' % (kind, ', '.join(KINDS)))
    return dict(K, kind=kind or 'dwemer')


def role_of(pid, K=None, S=None):
    K = K or KITS['dwemer']
    if K.get('halls') == 'dwemer':
        return next((r for pat, r in ROLE if re.search(pat, pid)), 'other')
    if K.get('rooms') and re.search(K['rooms'], pid):
        return 'room'
    if S and pid in (S.get('entries') or []):
        return 'entry'
    if pid in _entries(K):
        return 'entry'
    # (a keep's spiral stair and big hall pieces: laid by their own rules, dwemer._lay_spiral and _lay_big)
    if K.get('spiral') and pid in (K['spiral']['piece'], K['spiral']['bot'][0], K['spiral']['end'][0]):
        return 'spiral'
    if K.get('big') and pid == K['big']['blend']:
        return 'blend'
    if K.get('big') and pid in (K['big']['tile'], K['big']['wall']):
        return 'big'
    ps = (S or {}).get('ports', {}).get(pid) or []
    if len(ps) == 1:
        return 'dead end'
    if len(ps) == 2:
        if abs(ps[0][2] - ps[1][2]) >= 64:
            return 'ramp'
        return 'straight' if ps[0][3] == OPP[ps[1][3]] else 'corner'
    if len(ps) == 3:
        return 'T'
    if len(ps) >= 4:
        return 'cross'
    return 'other'


def _disk(db, kind='dwemer'):
    import taste
    if kind == 'dwemer':
        return taste.cache_file('dwemer_%s_%s' % (taste.sig(db), V))
    # (and the kind's own version, K['v']: a kind changed alone is learnt again alone)
    return taste.cache_file('dungeon_%s_%s_%s%s' % (kind, taste.sig(db), VG, (KITS.get(kind) or {}).get('v', '')))


# ------------------------------------------------------------------ frames
def _rot(x, y, rz):
    """A point in a frame turned by rz (clockwise, the game's way) in its parent's frame."""
    c, s = math.cos(rz), math.sin(rz)
    return x * c + y * s, -x * s + y * c


def _dir_of(vx, vy):
    return min(SIDES, key=lambda k: (SIDES[k][0] - vx) ** 2 + (SIDES[k][1] - vy) ** 2)


YAW = {'N': 0.0, 'E': math.pi / 2, 'S': math.pi, 'W': 3 * math.pi / 2}


# ------------------------------------------------------------------ the survey
def _cells(db, K=None):
    import kits
    tube = re.compile((K or KITS['dwemer'])['tube'])
    # (a kind learnt only from the places holding a piece of its own: a Velothi tower's pit, not every tomb)
    must = re.compile(K['must']) if K and K.get('must') else None
    out = []
    for (tag, k), lst in db.by_key.items():
        if tag != 'CELL' or k.startswith('#') or not lst or lst[-1] in db.dead or not kits.game_made(db, k):
            continue
        try:
            refs, _h = db.cell_refs(k)
        except Exception:
            continue
        n = 0
        ids = [(mapdata.ref_info(r['subs'])[0] or '').lower() for r in refs.values()]
        if must and not any(must.match(i) for i in ids):
            continue
        for rid in ids:
            if tube.match(rid):
                n += 1
                if n >= 10:
                    out.append(k)
                    break
    return sorted(out)


def _pieces(m, K):
    tube = re.compile(K['tube'])
    out = []
    for r in m['refs']:
        i = r['id'].lower()
        if (tube.match(i) or i == K.get('jamb')) and r.get('b') and abs(r['p'][3]) < .05 and abs(r['p'][4]) < .05:
            out.append({'ref': r['k'], 'id': i, 'x': r['p'][0], 'y': r['p'][1], 'z': r['p'][2],
                        'rz': r['p'][5] % (2 * math.pi), 's': r.get('s') or 1.0, 'b': r['b']})
    return out


def _learn_ports(obs, side_n, n_of, base, multi=frozenset()):
    """The openings, from the plain straight outwards: a known piece's opening that faces a neighbour's face
    gives that neighbour its opening there (several passes, each piece through its neighbours). Every pass
    learns them all afresh from the last pass's, so an opening first learnt through a neighbour that was
    itself still wrong is put right once that neighbour is: they settle on what the game's joins agree on.
    Returns (ports, agree): agree is the share of each piece's joins that meet an opening of the neighbour's
    facing back, within 16 units. A chamber (in multi) may have more than one opening on a side: every
    spot the game's joins agree on a quarter as often as the first, two tiles or more from it."""
    ports = dict(base)
    for _pass in range(12):
        votes = defaultdict(Counter)
        for aid, s_, bid, rel in obs:
            if bid not in ports or side_n[aid][s_] < PORT_SHARE * n_of[aid]:
                continue
            _b, lx, ly, lz, dq = rel
            q = math.radians(dq)
            out = SIDES[s_]
            for px, py, pz, ps in ports[bid]:
                ax, ay = _rot(px, py, q)
                dx, dy = _rot(*SIDES[ps], q)
                if dx * out[0] + dy * out[1] > -0.9:
                    continue                        # (not the neighbour's opening that faces back at this piece)
                votes[(aid, s_)][(int(round((lx + ax) / 8)) * 8, int(round((ly + ay) / 8)) * 8, int(round((lz + pz) / 8)) * 8)] += 1
        new = {k: [list(p) for p in v] for k, v in base.items()}
        for (aid, s_), c in sorted(votes.items()):
            if aid in base:
                continue
            top = c.most_common()
            (x, y, z), n = top[0]
            new.setdefault(aid, []).append([x, y, z, s_])
            if aid in multi:
                got = [(x, y, z)]
                for (x2, y2, z2), n2 in top[1:]:
                    if n2 >= max(3, 0.25 * n) and all(math.hypot(x2 - a, y2 - b) >= 400 for a, b, _c in got):
                        got.append((x2, y2, z2))
                        new[aid].append([x2, y2, z2, s_])
        if new == ports:
            break
        ports = new
    agree, tried = Counter(), Counter()
    for aid, s_, bid, rel in obs:
        mine_ = [p for p in ports.get(aid, []) if p[3] == s_]
        if not mine_ or bid not in ports:
            continue
        _b, lx, ly, lz, dq = rel
        q = math.radians(dq)
        tried[aid] += 1
        for px, py, pz, ps in ports[bid]:
            ax, ay = _rot(px, py, q)
            if any(abs(lx + ax - m[0]) <= 16 and abs(ly + ay - m[1]) <= 16 and abs(lz + pz - m[2]) <= 16 for m in mine_):
                agree[aid] += 1
                break
    return ports, {a: round(agree[a] / tried[a], 2) for a in tried}


def _wbox(b, x, y, z, rz, s=1.0):
    xs, ys = [], []
    for lx in (b[0] * s, b[3] * s):
        for ly in (b[1] * s, b[4] * s):
            wx, wy = _rot(lx, ly, rz)
            xs.append(x + wx)
            ys.append(y + wy)
    return (min(xs), min(ys), z + b[2] * s, max(xs), max(ys), z + b[5] * s)


def _used_ports(ports, p, nbs):
    """Which of a game piece's learnt openings had a piece joined beyond them: [index]."""
    out = []
    for k, (px, py, pz, ps) in enumerate(ports):
        wx, wy = _rot(px, py, p['rz'])
        dx, dy = _rot(*SIDES[ps], p['rz'])
        tx, ty, tz = p['x'] + wx + dx * 64, p['y'] + wy + dy * 64, p['z'] + pz + 40
        for B in nbs:
            bb = _wbox(B['b'], B['x'], B['y'], B['z'], B['rz'], B.get('s') or 1.0)
            if bb[0] - 8 <= tx <= bb[3] + 8 and bb[1] - 8 <= ty <= bb[4] + 8 and bb[2] - 8 <= tz <= bb[5] + 8:
                out.append(k)
                break
    return out


def _set_items(st):
    """A dressing set's things (sets were plain lists before the openings were kept with them)."""
    return st['d'] if isinstance(st, dict) else st


def _in_frame(F, x, y, z, rz):
    """(x, y, z, turn) in the frame of F = (x, y, z, rz), the turn in whole quarter turns as degrees."""
    lx, ly = _rot(x - F[0], y - F[1], -F[3])
    dq = int(round(math.degrees((rz - F[3]) % (2 * math.pi)) / 90.0)) * 90 % 360
    return (int(round(lx / 16)) * 16, int(round(ly / 16)) * 16, int(round((z - F[2]) / 16)) * 16, dq)


def _flip(pose):
    x, y, z, dq = pose
    return (-x, -y, z, (dq + 180) % 360)


def _learn_doors(K, ports, data, bounds):
    """How the kind's door frames stand at seams, which doors stand in them, and where its front doors stand:
    {'jamb': {'dz', 'turn', 'n'}, 'inner': [id, [poses]], 'load': {'id', 'holder', 'pose', 'n'}}. A frame
    turned half round is the same frame, so a door's pose and its mirror count as one."""
    out = {}
    jamb_dz, jamb_turn = Counter(), Counter()
    sets, inner_ids = Counter(), Counter()
    load = Counter()
    holder_at, holder_in = defaultdict(Counter), defaultdict(Counter)
    for tubes, jambs, doors in data:
        wports = []
        for pid, x, y, z, rz in tubes:
            for px, py, pz, ps in ports.get(pid, []):
                wx, wy = _rot(px, py, rz)
                wports.append((x + wx, y + wy, z + pz, _dir_of(*_rot(*SIDES[ps], rz)), pid))
        for J in jambs:
            near = [w for w in wports if math.hypot(w[0] - J[0], w[1] - J[1]) < 64 and abs(w[2] - J[2]) < 200]
            if near:
                w = min(near, key=lambda w: math.hypot(w[0] - J[0], w[1] - J[1]))
                jamb_dz[int(round((J[2] - w[2]) / 16)) * 16] += 1
                jamb_turn[int(round(math.degrees((J[3] - YAW[w[3]]) % math.pi) / 90.0)) % 2 * 90] += 1
            mine_ = []
            for did, dx, dy, dz, drz, to in doors:
                if to or math.hypot(dx - J[0], dy - J[1]) > 200 or abs(dz - J[2]) > 300:
                    continue
                mine_.append(_in_frame(J, dx, dy, dz, drz))
                inner_ids[did] += 1
            if mine_:
                a, b = tuple(sorted(mine_)), tuple(sorted(_flip(p) for p in mine_))
                sets[min(a, b)] += 1
        # (the front doors: each in the frame or the entrance piece nearest it, the leaves of a double
        # door counted together)
        held = defaultdict(list)
        for did, dx, dy, dz, drz, to in doors:
            if not to:
                continue
            best = None
            for J in jambs:
                d = math.hypot(dx - J[0], dy - J[1])
                if d < 200 and (best is None or d < best[0]):
                    best = (d, K.get('jamb'), tuple(J))
            if best is None:
                for pid, x, y, z, rz in tubes:
                    d = math.hypot(dx - x, dy - y)
                    if d < 260 and (best is None or d < best[0]):
                        best = (d, pid, (x, y, z, rz))
            if best:
                held[(best[1], best[2])].append((did, _in_frame(best[2], dx, dy, dz, drz)))
        for (holder, F), lst in held.items():
            load[(holder, tuple(sorted(lst)))] += 1
            # (how a front door's holder that isn't a tunnel piece stands at the seam it closes)
            if holder != K.get('jamb') and not ports.get(holder):
                # (standing inside a dead end, as the Daedric front doors' frames do: 107 of 120)
                inside = None
                for pid, x, y, z, rz in tubes:
                    if len(ports.get(pid, [])) != 1 or not bounds.get(pid):
                        continue
                    b = bounds[pid]
                    lx, ly = _rot(F[0] - x, F[1] - y, -rz)
                    if b[0] - 8 <= lx <= b[3] + 8 and b[1] - 8 <= ly <= b[4] + 8 and abs(F[2] - z) < 300:
                        inside = (pid, _in_frame((x, y, z, rz), *F))
                        break
                if inside:
                    holder_in[holder][inside] += 1
                    continue
                near = [w for w in wports if math.hypot(w[0] - F[0], w[1] - F[1]) < 300 and abs(w[2] - F[2]) < 200]
                if near:
                    w = min(near, key=lambda w: math.hypot(w[0] - F[0], w[1] - F[1]))
                    lx, ly = _rot(F[0] - w[0], F[1] - w[1], -YAW[w[3]])
                    # (with the piece whose opening it is: a Daedric front door's frame stands in a dead end)
                    holder_at[holder][(int(round(lx / 16)) * 16, int(round(ly / 16)) * 16, int(round((F[2] - w[2]) / 16)) * 16,
                                       int(round(math.degrees((F[3] - YAW[w[3]]) % (2 * math.pi)) / 90.0)) * 90 % 360, w[4])] += 1
    if jamb_dz:
        out['jamb'] = {'dz': jamb_dz.most_common(1)[0][0], 'turn': jamb_turn.most_common(1)[0][0], 'n': sum(jamb_dz.values())}
    if sets:
        out['inner'] = [inner_ids.most_common(1)[0][0], [list(p) for p in sets.most_common(1)[0][0]]]
    if load:
        (holder, lst), n = load.most_common(1)[0]
        out['load'] = {'id': lst[0][0], 'holder': holder, 'pose': list(lst[0][1]), 'leaves': [[d, list(p)] for d, p in lst], 'n': n}
        if sum(holder_in[holder].values()) > sum(holder_at[holder].values()):
            (owner, pose), n2 = holder_in[holder].most_common(1)[0]
            out['load']['in'] = [owner, list(pose)]
        elif holder_at.get(holder):
            (x, y, z, dq, owner), n2 = holder_at[holder].most_common(1)[0]
            out['load']['at'] = [x, y, z, dq]
    return out


def survey(db, force=False, kind='dwemer'):
    """A kind's survey: {'ports': {id: [[x, y, z, side], ...]}, 'n': {id: count}, 'dress': {id: [sets]},
    'door': {...}, 'ambi': [...], 'cells': n}. Kept on disk under the load order's signature."""
    K = kit(kind)
    if K.get('merge_from'):
        got = _merged(db, kind)
        if got is None:
            raise EditError('The Workshop is still learning the %s pieces.' % K['label'])
        return got
    key = (id(db.recs), kind)
    if not force and key in _cache:
        return _cache[key]
    path = _disk(db, kind)
    if not force and os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                _cache[key] = json.load(f)
            return _cache[key]
        except Exception:
            pass
    import adjacency
    cells = _cells(db, K)
    dress_ok = re.compile(K['dress'])
    not_dress = re.compile(K['not_dress'])
    tiles_re = re.compile(K['tiles']) if K.get('tiles') else None
    roofs_re = re.compile(K['roofs']) if K.get('roofs') else None
    door_dress = re.compile(K['door_dress']) if K.get('door_dress') else None
    obs = []                                  # (A id, side, B id, relation)
    n_of, side_n = Counter(), defaultdict(Counter)
    sets = defaultdict(list)
    id_cells = defaultdict(set)
    ambi = []
    data = []
    tile_n, tile_side = Counter(), defaultdict(Counter)
    tile_roof = Counter()
    piece_b = {}
    nb_of = {}                                # (piece ref -> (the piece, the pieces against it))
    shrines = []
    comp = Counter()
    tops = []
    for ck in cells:
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        P = _pieces(m, K)
        tubes = [p for p in P if p['id'] != K.get('jamb')]
        if len(tubes) < 10:
            continue
        for p in tubes:
            piece_b[p['id']] = p['b']
            n_of[p['id']] += 1
            seen = set()
            nb_of[p['ref']] = (p, [])
            for s_, B in adjacency.neighbours(tubes, p):
                if s_ in SIDES:
                    obs.append((p['id'], s_, B['id'], adjacency.relation(p, B)))
                    seen.add(s_)
                    nb_of[p['ref']][1].append(B)
            for s_ in seen:
                side_n[p['id']][s_] += 1
        data.append(([(p['id'], p['x'], p['y'], p['z'], p['rz']) for p in tubes],
                     [(p['x'], p['y'], p['z'], p['rz']) for p in P if p['id'] == K.get('jamb')],
                     [(r['id'].lower(), r['p'][0], r['p'][1], r['p'][2], r['p'][5], bool(r.get('to'))) for r in m['refs'] if r['type'] == 'DOOR'
                      and not (door_dress is not None and door_dress.search(r['id'].lower()))]))
        # (a room kit's tiles: which of their sides the game's rooms carry on past, and how often a roof
        # stands over each; the Daedric rooms are tiled from them)
        T = []
        if tiles_re:
            T = [{'ref': r['k'], 'id': r['id'].lower(), 'x': r['p'][0], 'y': r['p'][1], 'z': r['p'][2], 'rz': r['p'][5] % (2 * math.pi),
                  's': r.get('s') or 1.0, 'b': r['b']} for r in m['refs'] if r.get('b') and tiles_re.match(r['id'].lower())
                 and abs(r['p'][3]) < .05 and abs(r['p'][4]) < .05]
            roofs = [r for r in m['refs'] if roofs_re and roofs_re.match(r['id'].lower())]
            ent = [p for p in tubes if p['id'] in _entries(K)]
            TT = K.get('tile', 512)
            for t in T:
                tile_n[t['id']] += 1
                # (by the tile grid (512 Daedric, 256 Velothi), not the boxes: a floor tile is flat, so nothing stands against it)
                got = set()
                for u in T + ent:
                    if u is t or abs(u['z'] - t['z']) > 64:
                        continue
                    lx, ly = _rot(u['x'] - t['x'], u['y'] - t['y'], -t['rz'])
                    for s_, (sx, sy) in SIDES.items():
                        if abs(lx - sx * TT) < 40 and abs(ly - sy * TT) < 40:
                            got.add(s_)
                for s_ in got:
                    tile_side[t['id']][s_] += 1
                if any(abs(r['p'][0] - t['x']) < 32 and abs(r['p'][1] - t['y']) < 32 for r in roofs):
                    tile_roof[t['id']] += 1
        # what stands in each piece: each thing goes to the piece whose box holds it, the nearest when two do.
        # Two traps (the user's Gold Grotto, 2026-10-24): crates stood in mid-air where the game had them on a
        # wooden platform the dressing left out, and a door frame stood against the rock where the game had a
        # door in it to elsewhere. So a static the list leaves out is kept when something kept stands on it,
        # and a piece that had a door in it is never copied from.
        dress = defaultdict(list)
        dress_w = defaultdict(list)               # (the kept things themselves, for what stands on what)
        maybe = defaultdict(list)                 # (piece ref -> statics left out, kept only as supports)
        doored = set()
        tube_ids = {p['id'] for p in P} | {t['id'] for t in T}
        # (the room tiles hold things too: a made tomb's tiled hall stood bare, 0.04 things a tile against the
        # game's 3.88, the user: "way too barren for its size". A tomb's tiles from the game's tombs only (an
        # ash urn in the place, or a tomb by name), not from the lived-in Velothi halls with their bars)
        tile_hold = []
        if T and (K['kind'] != 'tomb' or 'tomb' in ck or any(r['id'].lower().startswith('urn_ash') for r in m['refs'])):
            tile_hold = T
            for t in T:
                nb_of[t['ref']] = (t, [])
        hold = tubes + tile_hold
        # (a cave's pieces' boxes overlap far: a thing goes to the piece whose floor is under it, when that
        # piece's box holds it too; by box alone, a raised plank deck in the chamber above went with the
        # tunnel under it and was copied into its rock, the user's Golden Colon, 2026-10-24)
        import seethrough
        sc_t = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['k'] in {p['ref'] for p in hold}]))
        by_ref = {p['ref']: p for p in hold}
        for r in m['refs']:
            i, t = r['id'].lower(), r['type']
            support = False
            # (a door record the kind hangs as dressing, K['door_dress']: an Ayleid ruin's light panels, 639 in its 20
            # places; as doors they marked nearly every hall as one with a door in it, never copied from)
            lamp = t == 'DOOR' and door_dress is not None and not r.get('to') and bool(door_dress.search(i))
            if lamp:
                t = 'ACTI'
            if t == 'DOOR':
                pass
            elif t == 'NPC_' or (t not in DRESS_TYPES and not (t in ('STAT', 'ACTI') and dress_ok.match(i))) or not_dress.search(i):
                b_ = r.get('b')
                # (only what things are set on: platforms, planks, shelves and the like, or something small;
                # never a building piece of another set: Tamriel Rebuilt's cave tunnels ran across ours)
                if not (t in ('STAT', 'ACTI') and b_ and i not in tube_ids and not re.search(r'marker|door|_dj_|doorjam', i)
                        and (re.search(SUPPORTS, i) or max(b_[3] - b_[0], b_[4] - b_[1]) * (r.get('s') or 1.0) <= 300)
                        and not re.search(r'tunnel|corr|_hall|room|_wall|ceil|_cave\d|cave_?\d|entr|exit', i)):
                    continue
                support = True
            best, holders = None, {}
            for p in hold:
                b, s = p['b'], p['s']
                lx, ly = _rot(r['p'][0] - p['x'], r['p'][1] - p['y'], -p['rz'])
                if not (b[0] * s - 8 <= lx <= b[3] * s + 8 and b[1] * s - 8 <= ly <= b[4] * s + 8
                        and p['z'] + b[2] * s - 24 <= r['p'][2] <= p['z'] + b[5] * s + 8):
                    continue
                holders[p['ref']] = (lx, ly)
                d = math.hypot(lx, ly)
                if best is None or d < best[0]:
                    best = (d, p, lx, ly)
            if best is None:
                continue
            fh = sc_t.nearest_any((r['p'][0], r['p'][1], r['p'][2] + 20), (0.0, 0.0, -1.0), 3000)
            under = sc_t.owner(fh[1]) if fh is not None else None
            if len(holders) > 1 and under in holders:
                best = (0, by_ref[under]) + holders[under]
            elif under is not None and under != best[1]['ref'] and t != 'DOOR':
                # (standing over another piece's floor, one whose box doesn't hold it: it belongs with that
                # piece's things, not this one's. A cave chamber's box reaches over the next tunnel, and a deck
                # copied with the chamber stood on a made cave's roof, the user's Test Cove, 2026-10-25)
                continue
            _d, p, lx, ly = best
            if t == 'DOOR':
                doored.add(p['ref'])
                continue
            row = [r['id'], t, round(lx, 1), round(ly, 1), round(r['p'][2] - p['z'], 1),
                   round(r['p'][3], 4), round(r['p'][4], 4), round((r['p'][5] - p['rz']) % (2 * math.pi), 4),
                   round(r.get('s') or 1.0, 3)]
            if support:
                maybe[p['ref']].append((row, r))
                continue
            dress[p['ref']].append(row)
            dress_w[p['ref']].append(r)
            id_cells[i].add(ck)
        # (a left-out static something kept stands on: a platform, a plank, a beam; again for what stands on that)
        for pref, lst in maybe.items():
            kept = list(dress_w.get(pref, []))
            left = list(lst)
            for _round in range(3):
                more = []
                for row, s in left:
                    b, sc = s['b'], s.get('s') or 1.0
                    top = s['p'][2] + b[5] * sc
                    def on(o):
                        lx_, ly_ = _rot(o['p'][0] - s['p'][0], o['p'][1] - s['p'][1], -s['p'][5])
                        return (b[0] * sc - 8 <= lx_ <= b[3] * sc + 8 and b[1] * sc - 8 <= ly_ <= b[4] * sc + 8
                                and top - 40 <= o['p'][2] + (o['b'][2] * (o.get('s') or 1.0) if o.get('b') else 0) <= top + 24)
                    if any(on(o) for o in kept):
                        dress[pref].append(row)
                        kept.append(s)
                        id_cells[s['id'].lower()].add(ck)
                    else:
                        more.append((row, s))
                if len(more) == len(left):
                    break
                left = more
        for p in hold:
            # (not from a piece the game scaled: its things stand where an unscaled one has rock)
            if p['ref'] not in doored and abs(p['s'] - 1.0) < 0.02:
                sets[p['id']].append((p['ref'], dress.get(p['ref'], [])))
        # (what the game's dungeons of the kind keep on their tables: in the table's frame, from its top)
        for t in m['refs']:
            if t['type'] not in ('STAT', 'ACTI') or not t.get('b') or not TABLES.search(t['id'].lower()) \
                    or abs(t['p'][3]) > .05 or abs(t['p'][4]) > .05:
                continue
            b, s = t['b'], t.get('s') or 1.0
            top = t['p'][2] + b[5] * s
            on = []
            for r in m['refs']:
                if r['type'] not in TOP_TYPES or not r.get('b'):
                    continue
                lx, ly = _rot(r['p'][0] - t['p'][0], r['p'][1] - t['p'][1], -t['p'][5])
                base = r['p'][2] + r['b'][2] * (r.get('s') or 1.0)
                if b[0] * s + 4 <= lx <= b[3] * s - 4 and b[1] * s + 4 <= ly <= b[4] * s - 4 and top - 8 <= base <= top + 16:
                    on.append([r['id'], r['type'], round(lx, 1), round(ly, 1), round(base - top, 1), round(r['p'][3], 4), round(r['p'][4], 4),
                               round((r['p'][5] - t['p'][5]) % (2 * math.pi), 4), round(r.get('s') or 1.0, 3)])
            if on:
                tops.append({'t': t['id'].lower(), 'w': [round(v * s, 1) for v in (b[0], b[1], b[3], b[4])], 'd': on})
        # (the pieces the game lays with a piece, named after it: a chamber's other half, in_moldcave_21_1
        # with in_moldcave_21, where it stands from it)
        byname = defaultdict(list)
        for r in m['refs']:
            if r['type'] == 'STAT':
                byname[r['id'].lower()].append(r)
        for p in tubes:
            for cid in [i for i in byname if i.startswith(p['id'] + '_') and re.match(r'^_\d+$', i[len(p['id']):])]:
                near = min(byname[cid], key=lambda r: math.hypot(r['p'][0] - p['x'], r['p'][1] - p['y']))
                if math.hypot(near['p'][0] - p['x'], near['p'][1] - p['y']) < 3000:
                    comp[(p['id'], cid, _in_frame((p['x'], p['y'], p['z'], p['rz']), near['p'][0], near['p'][1], near['p'][2], near['p'][5]))] += 1
        # (a kind's shrine: everything round its biggest statue, in the statue's frame, standing on the floor
        # under it: the platform and its stairs, braziers and censers, the offerings, the gems)
        if K.get('shrine'):
            st = [r for r in m['refs'] if r['type'] in ('STAT', 'ACTI') and r.get('b') and re.search(K['shrine'], r['id'].lower())]
            if st:
                big = max(st, key=lambda r: (r['b'][5] - r['b'][2]) * (r.get('s') or 1.0))
                F = (big['p'][0], big['p'][1], big['p'][2], big['p'][5])
                # (the floor under it: the lowest room floor tile within a tile of it)
                fl = [r['p'][2] for r in m['refs'] if tiles_re and tiles_re.match(r['id'].lower())
                      and math.hypot(r['p'][0] - F[0], r['p'][1] - F[1]) < 600 and r['p'][2] <= F[2] + 8]
                floor_z = min(fl) if fl else F[2]
                items = []
                for r in m['refs']:
                    i = r['id'].lower()
                    if r is big or r['type'] in ('NPC_', 'DOOR') or math.hypot(r['p'][0] - F[0], r['p'][1] - F[1]) > 700 \
                            or abs(r['p'][2] - F[2]) > 450 or re.match(K['tube'], i) or (tiles_re and tiles_re.match(i)) \
                            or (roofs_re and roofs_re.match(i)) or re.search(r'marker|mezzanine', i):
                        continue
                    lx, ly = _rot(r['p'][0] - F[0], r['p'][1] - F[1], -F[3])
                    items.append([r['id'], r['type'], round(lx, 1), round(ly, 1), round(r['p'][2] - floor_z, 1), round(r['p'][3], 4),
                                  round(r['p'][4], 4), round((r['p'][5] - F[3]) % (2 * math.pi), 4), round(r.get('s') or 1.0, 3)])
                shrines.append({'statue': big['id'], 'z': round(F[2] - floor_z, 1), 's': round(big.get('s') or 1.0, 3), 'items': items})
        try:
            import places
            pl = places.read(db, ck)
            if pl.get('has_lighting'):
                ambi.append({'ambient': pl['ambient'], 'sunlight': pl['sun'], 'fog': pl['fog'], 'density': pl['density']})
        except Exception:
            pass
    # the openings: from each of the straight's possible pairs, the one the game's joins agree with best
    best = None
    multi = frozenset(a for a in n_of if K.get('rooms') and re.search(K['rooms'], a))
    for bp in K['base_ports']:
        ports, agree = _learn_ports(obs, side_n, n_of, dict(K.get('seed_ports') or {}, **{K['base']: bp}), multi)
        score = sum(agree.get(a, 0) * n_of[a] for a in ports) / max(1, sum(n_of[a] for a in ports))
        if best is None or score > best[0]:
            best = (score, ports, agree)
    _score, ports, agree = best
    for a in K.get('seed_ports') or {}:
        agree[a] = 1.0                          # (set by hand from the game's joins: trusted)
    if kind == 'dwemer':
        # (the door survey of 2026-10-24: the game's front doors stand in a frame at (0, 0, -32), its inner
        # doors as a pair of leaves either side of its middle, 164 of 182 front doors, 463 of 519 inner ones)
        doors = {'jamb': {'dz': 0, 'turn': 0, 'n': 0}, 'inner': [K['inner_door'], [[112, 0, 0, 180], [-112, 0, 0, 0]]],
                 'load': {'id': K['load_door'], 'holder': K['jamb'], 'pose': [0, 0, -32, 0], 'n': 0}}
    else:
        doors = _learn_doors(K, ports, data, piece_b)
    if K.get('front'):
        # (a kind's front door set by hand, K['front']: it stands bare in the way in's opening, no frame)
        doors['load'] = {'id': K['front'][0], 'holder': K.get('jamb'), 'pose': list(K['front'][1]), 'bare': True, 'n': 0}
    # (and how the game stands each pair of pieces against each other: B in A's frame. A join the game never
    # makes, a corridor turned the other way round against a dead end, left a gap to the void beside it, the
    # user's Nchudzamn, 2026-10-25; such joins are refused while growing)
    rels = defaultdict(set)
    for aid, s_, bid, rel in obs:
        rels[aid + '|' + bid].add(tuple(rel[1:]))
    for pair, lst in (K.get('seed_rels') or {}).items():
        a_, b_ = pair.split('|')
        for lx, ly, lz, dq in lst:
            rels[pair].add((lx, ly, lz, dq))
            bx, by = _rot(-lx, -ly, -math.radians(dq))
            rels[b_ + '|' + a_].add((int(round(bx)), int(round(by)), -lz, (360 - dq) % 360))
    out = {'V': V if kind == 'dwemer' else VG, 'kind': kind, 'cells': len(cells), 'n': dict(n_of), 'ports': ports,
           'rels': {k: sorted(v) for k, v in rels.items()},
           'agree': agree, 'base_score': round(_score, 3),
           'side_share': {a: {s_: round(side_n[a][s_] / n_of[a], 2) for s_ in side_n[a]} for a in n_of},
           'door': doors, 'ambi': ambi[:40],
           'entries': sorted({doors['load']['holder']} - {K.get('jamb')}) if doors.get('load') else [],
           'uniques': sorted(i for i, c in id_cells.items() if len(c) < 2),
           # (each set with the openings its piece had joined in the game: a chamber's stairs and platforms
           # are built for the exits it used, so a set is chosen for a piece using the same ones)
           'dress': {a: [{'u': _used_ports(ports.get(a, []), *nb_of[ref]), 'd': d}
                         for ref, d in random.Random(a).sample(s, min(len(s), 80))] for a, s in sets.items()}}
    if kind == 'dwemer':
        out['door'] = {'load': [0, 0, -32], 'inner': [[112, 0, 0, 180], [-112, 0, 0, 0]]}
    if K.get('joins_from'):
        # (the halls' openings and joins from a kind built of the same pieces in many more places: a Velothi tower's
        # from the tombs' 380, its own 64 leaving the rarer joins to chance, every large tower leaking at a corner or
        # a T. Its own pieces, the pit, and its own dressings stay its own)
        J = survey(db, kind=K['joins_from'])
        own = re.compile(K['final_room']) if K.get('final_room') else None
        for pid, ps in J['ports'].items():
            if own and own.search(pid):
                continue
            out['ports'][pid] = ps
            out['agree'][pid] = J['agree'].get(pid, out['agree'].get(pid))
            out['n'][pid] = J['n'].get(pid, out['n'].get(pid, 0))
            if pid in J.get('side_share', {}):
                out['side_share'][pid] = J['side_share'][pid]
        for rk, v in J['rels'].items():
            if not (own and any(own.search(x) for x in rk.split('|'))):
                out['rels'][rk] = v
    # (a companion the game lays with a piece at the same spot a third of the times or more: in_moldcave_21_1,
    # the floor under in_moldcave_21, 6 of its 18; laid alone, its floor is open below)
    comps = defaultdict(list)
    together = Counter()
    for (pid, cid, rel), n in comp.items():
        together[(pid, cid)] += n
    for (pid, cid, rel), n in comp.most_common():
        if n_of[pid] >= 5 and together[(pid, cid)] >= 0.3 * n_of[pid] and not any(c_[0] == cid for c_ in comps[pid]):
            comps[pid].append([cid] + list(rel))
    out['companions'] = dict(comps)
    if shrines:
        out['shrines'] = random.Random(kind).sample(shrines, min(len(shrines), 40))
    out['tops'] = random.Random(kind).sample(tops, min(len(tops), 150))
    if tiles_re:
        out['tiles'] = {t: {'n': n, 'sides': {s_: round(tile_side[t][s_] / n, 2) for s_ in tile_side[t]},
                            'roof': round(tile_roof[t] / n, 2)} for t, n in tile_n.items()}
    try:
        with open(path + '.part', 'w', encoding='utf-8') as f:
            json.dump(out, f)
        os.replace(path + '.part', path)
    except Exception as e:
        print('dungeon survey not kept:', e)
    _cache[key] = out
    return out


def learning_name(kind):
    """What the learning bar calls a kind's survey."""
    names = {'dwemer': "the game's Dwemer ruins", 'tomb': "the game's Velothi tombs", 'daedric': "the game's Daedric ruins", 'ayleid': "the game's Ayleid ruins",
             'stronghold': "the game's Chimer strongholds", 'tower': "the game's Velothi towers"}
    if kind in names:
        return names[kind]
    if kind.startswith('cave'):
        return "the game's caves (%s)" % kit(kind)['label'].split('(')[-1].rstrip(')')
    return "the game's %ss" % kit(kind)['label'].lower()


def ready(db, kind='dwemer'):
    """The kind's survey if it is to hand (in memory or on disk); else None, with it started in the survey
    process (about 17 s for the Dwemer ruins, once per load order)."""
    K = kit(kind)
    if K.get('merge_from'):
        return _merged(db, kind)
    key = (id(db.recs), kind)
    if key in _cache:
        return _cache[key]
    try:
        if os.path.isfile(_disk(db, kind)):
            return survey(db, kind=kind)
    except Exception as e:
        print("the game's %ss: couldn't read the survey:" % K['label'], repr(e))
        return None
    t = _thread.get(kind)
    if t is None or not t.is_alive():
        import background
        _thread[kind] = background.start(learning_name(kind),
                                         lambda: survey(db, kind=kind), task=('dwemer', 'survey', [False, kind]))
    return None


# ------------------------------------------------------------------ the layout
class _Layout:
    """Pieces laid so far, with their world boxes, and the openings still to fill."""

    def __init__(self, db, S, K=None):
        self.db, self.S, self.K = db, S, K or kit('dwemer')
        self.big = False
        self.pieces = []                      # {'id', 'p': [x, y, z, 0, 0, rz], 'box', 'role', 'depth', 'hall'}
        self.open = []                        # {'x', 'y', 'z', 'side', 'owner', 'depth'}
        self.seams = []                       # (x, y, z, side, a, b): where two pieces meet
        self._b = {}
        self.ez = None                        # the way in's floor: nothing goes over it (dgrules)
        self.way = 'down'                     # ('up': a place that climbs from its way in, nothing under it)
        self.too_deep = 0                     # (pieces refused for going deeper than the game's own go)
        self.last_loops = 0                   # (how many open openings the last piece laid closed a loop with)
        self.bound = None                     # ((dx, dy) the way in from the door, half width, depth): a keep's footprint
        # (a keep's own outer blocks, keepmaker.masses: ((x, y, z) the front door's sill, (dx, dy) the way in from it,
        # [(a0, c0, z0, a1, c1, z1)] each block along that way, across it to the right, and up from the sill): every piece
        # stands inside them. The user's Fort Urasek, 2026-11-12: a keep 3,300 wide outside with its bulk and a tower
        # 3,240 high to the right of the door, a Great Hall inside 5,300 wide on one storey running left, 48% of it
        # within the keep's walls)
        self.mass = None
        self.avoid = []                       # (boxes in that frame nothing stands in: the Great Hall, for what lies beside and over it)
        self.too_wide = 0                     # (pieces refused for standing outside it)

    def bounds(self, pid):
        if pid not in self._b:
            ri = self.db.resolve_id(pid)
            self._b[pid] = mapdata.object_bounds(self.db, ri) if ri is not None else None
        return self._b[pid]

    def box(self, pid, x, y, z, rz):
        b = self.bounds(pid)
        xs, ys = [], []
        for lx in (b[0], b[3]):
            for ly in (b[1], b[4]):
                wx, wy = _rot(lx, ly, rz)
                xs.append(x + wx)
                ys.append(y + wy)
        return (min(xs), min(ys), z + b[2], max(xs), max(ys), z + b[5])

    @staticmethod
    def _hit(a, b, slack=SLACK):
        return min(a[3], b[3]) - max(a[0], b[0]) > slack and min(a[4], b[4]) - max(a[1], b[1]) > slack and \
            min(a[5], b[5]) - max(a[2], b[2]) > slack

    def fits(self, boxes, ignore=()):
        """None of the boxes runs into a piece laid already (but the one being joined: the game's joined
        pieces overlap at the join, a hall's exit piece over its corridor by 128); and within the footprint, when one
        is set (a keep's interior under the mass that stands outside: its rooms "veered off where there's nothing
        outside", the user 2026-11-06)."""
        if self.mass:
            (ox, oy, oz), (dx, dy), blocks = self.mass
            for b in boxes:
                # (a plate that closes a doorway, 7 thick, stands where its doorway does: measured like a piece, a tower's
                # stair had "an opening onto nothing" at every doorway in the tower's own face, lab gp2)
                if min(b[3] - b[0], b[4] - b[1]) < 40:
                    continue
                cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
                top, bot = b[5] - oz, b[2] - oz
                for px, py in ((cx + MASS_IN, cy), (cx - MASS_IN, cy), (cx, cy + MASS_IN), (cx, cy - MASS_IN)):
                    a, c = (px - ox) * dx + (py - oy) * dy, (px - ox) * dy - (py - oy) * dx
                    if not any(M[0] - 8 <= a <= M[3] + 8 and M[1] - 8 <= c <= M[4] + 8 and top <= M[5] + MASS_OVER and bot >= M[2] - MASS_UNDER for M in blocks):
                        self.too_wide += 1
                        return False
                if self.avoid:
                    a, c = (cx - ox) * dx + (cy - oy) * dy, (cx - ox) * dy - (cy - oy) * dx
                    if any(A[0] <= a <= A[3] and A[1] <= c <= A[4] and bot < A[5] and top > A[2] + 8 for A in self.avoid):
                        self.too_wide += 1
                        return False
        elif self.bound:
            (dx, dy), hw, depth = self.bound
            for b in boxes:
                cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
                along, across = cx * dx + cy * dy, abs(-cx * dy + cy * dx)
                if along < -320 or along > depth or across > hw:
                    self.too_wide += 1
                    return False
        return not any(self._hit(nb, p['box']) for nb in boxes for n, p in enumerate(self.pieces) if n not in ignore)

    def ports_of(self, pid, x, y, z, rz):
        out = []
        for px, py, pz, ps in self.S['ports'].get(pid, []):
            wx, wy = _rot(px, py, rz)
            dx, dy = _rot(*SIDES[ps], rz)
            out.append({'x': x + wx, 'y': y + wy, 'z': z + pz, 'side': _dir_of(dx, dy)})
        return out

    def blocked(self, port, ignore=()):
        """Whether something already stands just beyond an opening (so nothing can join it)."""
        dx, dy = SIDES[port['side']]
        px, py, pz = port['x'] + dx * 64, port['y'] + dy * 64, port['z'] + 40
        for n, p in enumerate(self.pieces):
            if n in ignore:
                continue
            b = p['box']
            if b[0] + 8 < px < b[3] - 8 and b[1] + 8 < py < b[4] - 8 and b[2] < pz < b[5]:
                return True
        return False

    def companions(self, pid, x, y, z, rz):
        """The pieces the game always lays with this one, where they stand: a cave chamber's lower half
        (in_moldcave_21 with in_moldcave_21_1; laid alone, its rocks hung over nothing). [(id, x, y, z, rz)]"""
        out = []
        for cid, lx, ly, lz, dq in (self.S.get('companions') or {}).get(pid, []):
            if self.db.resolve_id(cid) is None or not self.bounds(cid):
                continue
            wx, wy = _rot(lx, ly, rz)
            out.append((cid, x + wx, y + wy, z + lz, (rz + math.radians(dq)) % (2 * math.pi)))
        return out

    def add(self, pid, x, y, z, rz, depth, hall=None, came=None):
        n = len(self.pieces)
        self.pieces.append({'id': pid, 'p': [round(x, 2), round(y, 2), round(z, 2), 0, 0, round(rz % (2 * math.pi), 5)],
                            'box': self.box(pid, x, y, z, rz), 'role': role_of(pid, self.K, self.S), 'depth': depth, 'hall': hall})
        for cid, cx, cy, cz, crz in self.companions(pid, x, y, z, rz):
            self.pieces.append({'id': cid, 'p': [round(cx, 2), round(cy, 2), round(cz, 2), 0, 0, round(crz, 5)],
                                'box': self.box(cid, cx, cy, cz, crz), 'role': 'other', 'depth': depth, 'hall': hall, 'of': n})
        return n

    def game_joins(self, owner, pid, x, y, z, rz):
        """Whether the game ever stands pid so against the piece it joins (within 16 units, the same turn);
        a pair of common pieces the game never joins at all is refused too. (An old survey has no 'rels':
        anything goes, as before.)"""
        rels = self.S.get('rels')
        if rels is None or owner is None or owner >= len(self.pieces) or not self.pieces[owner].get('id'):
            return True
        A = self.pieces[owner]
        lx, ly = _rot(x - A['p'][0], y - A['p'][1], -A['p'][5])
        dq = int(round(math.degrees((rz - A['p'][5]) % (2 * math.pi)) / 15.0)) * 15 % 360
        got = rels.get(A['id'] + '|' + pid)
        if not got:
            # (a pair the game never joins: only between two rare pieces, whose joins the game shows too few of;
            # with one common one it left corr4_03 open beside corr2_04, 7% of the eye rays out)
            n = self.S.get('n') or {}
            return n.get(A['id'], 0) < 20 and n.get(pid, 0) < 20
        return any(abs(r[0] - lx) <= 16 and abs(r[1] - ly) <= 16 and abs(r[2] - (z - A['p'][2])) <= 16 and r[3] == dq for r in got)

    def level_ok(self, pid, z, target):
        """The height rules (dgrules): the way in is the highest point, the way goes down as you go in (no
        opening of the new piece over the one it is entered by), and no deeper than the game's own go."""
        if self.ez is None:
            return True
        ps = self.S['ports'].get(pid) or []
        if not ps:
            return True
        import dgrules
        cap = dgrules.rise_cap(self.K)
        top, low = z + max(q[2] for q in ps), z + min(q[2] for q in ps)
        if self.way == 'up':
            # (mirrored for a place that climbs from its way in: nothing under the way in, no opening under
            # the one entered by, no higher than the game's own climb)
            if low < target['z'] - cap or low < self.ez - cap:
                return False
            if top > self.ez + dgrules.climb_cap(self.K):
                self.too_deep += 1
                return False
            return True
        if top > target['z'] + cap or top > self.ez + cap:
            return False
        if low < self.ez - dgrules.deep_cap(self.K):
            self.too_deep += 1
            return False
        return True

    def place_at(self, pid, port_index, target, depth, hall=None):
        """pid laid so its opening port_index meets the open opening target; its other openings join the
        open list (or close a loop where they meet one). Returns the piece's index, or None when it doesn't fit."""
        px, py, pz, ps = self.S['ports'][pid][port_index]
        want = OPP[target['side']]
        self.last_loops = 0
        for q in range(4):
            rz = q * math.pi / 2
            if _dir_of(*_rot(*SIDES[ps], rz)) != want:
                continue
            wx, wy = _rot(px, py, rz)
            x, y, z = target['x'] - wx, target['y'] - wy, target['z'] - pz
            if not self.game_joins(target['owner'], pid, x, y, z, rz) or not self.level_ok(pid, z, target):
                continue
            box = self.box(pid, x, y, z, rz)
            boxes = [box] + [self.box(c[0], *c[1:]) for c in self.companions(pid, x, y, z, rz)]
            if not self.fits(boxes, ignore=(target['owner'],)):
                return None
            others = [o for k, o in enumerate(self.ports_of(pid, x, y, z, rz)) if k != port_index]
            # (a ramp may not turn straight back: up and at once down again, or down and up, is nothing a
            # builder would make; the user: "never do this in a dungeon, maybe in a natural cave")
            sign = lambda v: (v > 32) - (v < -32)
            if target.get('dz') and not self.K.get('kind', '').startswith('cave') and role_of(pid, self.K, self.S) == 'ramp' and \
                    any(sign(o['z'] - target['z']) == -target['dz'] for o in others):
                return None
            n_before = len(self.pieces)
            loops, new = [], []
            for o in others:
                twin = next((t for t in self.open if t is not target and abs(t['x'] - o['x']) < 16 and abs(t['y'] - o['y']) < 16
                             and abs(t['z'] - o['z']) < 16 and t['side'] == OPP[o['side']]), None)
                if twin:
                    loops.append(twin)
                    continue
                self.pieces.append({'box': box})
                bl = self.blocked(o, ignore=(n_before,))
                self.pieces.pop()
                if bl:
                    return None                     # (an opening into a wall: nothing could close it)
                new.append(o)
            n = self.add(pid, x, y, z, rz, depth, hall)
            self.open.remove(target)
            self.seams.append((target['x'], target['y'], target['z'], target['side'], target['owner'], n))
            for t in loops:
                self.open.remove(t)
                self.seams.append((t['x'], t['y'], t['z'], t['side'], t['owner'], n))
            self.last_loops = len(loops)
            for o in new:
                self.open.append(dict(o, owner=n, depth=depth + 1, dz=sign(o['z'] - target['z'])))
            return n
        return None

    def snapshot(self):
        return (len(self.pieces), list(self.open), len(self.seams))

    def restore(self, snap):
        del self.pieces[snap[0]:]
        self.open = list(snap[1])
        del self.seams[snap[2]:]


def _hall_plan(w, h, exits):
    """A Dwemer hall of w x h tiles (columns along x, rows down from the north edge): [(id, i, j, quarter
    turns)] for each piece, exit pieces two tiles wide on the edges listed in exits [(edge, first column/row)].
    The hall2 piece opens east and south (the north-west corner), hall3 east, west and south (a north edge),
    hall4_00 all round; an exit piece spans two tiles of an edge with its corridor opening outwards."""
    taken = set()
    out = []
    edge_turn = {'N': 0, 'E': 1, 'S': 2, 'W': 3}
    for edge, k in exits:
        if edge == 'N':
            cells = [(k, 0), (k + 1, 0)]
        elif edge == 'S':
            cells = [(k + 1, h - 1), (k, h - 1)]
        elif edge == 'E':
            cells = [(w - 1, k), (w - 1, k + 1)]
        else:
            cells = [(0, k + 1), (0, k)]
        out.append(('exit', cells[0][0], cells[0][1], edge_turn[edge]))
        taken |= set(cells)
    for i in range(w):
        for j in range(h):
            if (i, j) in taken:
                continue
            n, s, wv, e = j == 0, j == h - 1, i == 0, i == w - 1
            if n and wv:
                out.append(('in_dwrv_hall2_00', i, j, 0))
            elif n and e:
                out.append(('in_dwrv_hall2_00', i, j, 1))
            elif s and e:
                out.append(('in_dwrv_hall2_00', i, j, 2))
            elif s and wv:
                out.append(('in_dwrv_hall2_00', i, j, 3))
            elif n:
                out.append(('in_dwrv_hall3_00', i, j, 0))
            elif e:
                out.append(('in_dwrv_hall3_00', i, j, 1))
            elif s:
                out.append(('in_dwrv_hall3_00', i, j, 2))
            elif wv:
                out.append(('in_dwrv_hall3_00', i, j, 3))
            else:
                out.append(('in_dwrv_hall4_00', i, j, 0))
    return out


def _lay_hall(L, target, w, h, depth, hall_no, rng, second_exit):
    """A Dwemer hall joined to the open opening target by its exit piece; True when it fits. A second exit
    on another edge goes into the open list, for the tunnels to carry on from."""
    exit_id = next((e for e in HALL_EXITS if any(p[3] == 'N' and p[2] == 0 for p in L.S['ports'].get(e, []))), None)
    if not exit_id:
        return False
    port = next(p for p in L.S['ports'][exit_id] if p[3] == 'N' and p[2] == 0)
    # (an exit is two tiles wide and must stand between the corners: on an edge three tiles long it took a
    # corner and left that corner open on the void, the user's Nchudmanz and Nchdeeznuts, 2026-10-24)
    if w < 4:
        return False
    exits = [('N', rng.randint(1, w - 3))]
    if second_exit:
        exits.append(rng.choice([('S', rng.randint(1, w - 3))] + ([('E', rng.randint(1, h - 3)), ('W', rng.randint(1, h - 3))] if h >= 4 else [])))
    plan = _hall_plan(w, h, exits)
    # the hall's frame: the first exit piece's opening on the target, the hall lying away from it
    want = OPP[target['side']]
    q0 = {'N': 0, 'E': 1, 'S': 2, 'W': 3}[want]
    rz0 = q0 * math.pi / 2
    i0, j0 = plan[0][1], plan[0][2]
    # (the exit piece's own origin is its first tile's middle; its corridor opening at port in its frame)
    ox, oy = _rot(port[0], port[1], rz0)
    ex_x, ex_y, ex_z = target['x'] - ox, target['y'] - oy, target['z'] - port[2]
    T = 256
    laid = []
    for pid, i, j, q in plan:
        lx, ly = (i - i0) * T, -(j - j0) * T
        wx, wy = _rot(lx, ly, rz0)
        rz = (rz0 + q * math.pi / 2) % (2 * math.pi)
        rid = exit_id if pid == 'exit' else pid
        laid.append((rid, ex_x + wx, ex_y + wy, ex_z, rz, pid == 'exit'))
    boxes = [L.box(rid, x, y, z, rz) for rid, x, y, z, rz, _e in laid]
    if not L.fits(boxes, ignore=(target['owner'],)):
        return False
    # (a second exit with something already in front of it was never carried on from nor capped: the
    # user's Nchudmanz had a hall corner open on the void, 18 of 96 eye-height rays out; such a hall is
    # laid with its one exit instead)
    if second_exit:
        ex2 = [t for t in laid if t[5]][1:]
        for rid, x, y, z, rz, _e in ex2:
            if any(L.blocked(o) for o, pp in zip(L.ports_of(rid, x, y, z, rz), L.S['ports'][rid]) if pp[3] == 'N' and pp[2] == 0):
                return _lay_hall(L, target, w, h, depth, hall_no, rng, False)
    # every piece of the hall at once; the first exit closes the target, the others join the open list
    first = None
    for k, (rid, x, y, z, rz, is_exit) in enumerate(laid):
        n = L.add(rid, x, y, z, rz, depth, hall=hall_no)
        if is_exit:
            # (only the exit's corridor opening: its other learnt openings are seams inside the hall)
            mine_ = [o for o, pp in zip(L.ports_of(rid, x, y, z, rz), L.S['ports'][rid]) if pp[3] == 'N' and pp[2] == 0]
            for o in mine_:
                if first is None:
                    first = n
                    L.open.remove(target)
                    L.seams.append((target['x'], target['y'], target['z'], target['side'], target['owner'], n))
                elif not L.blocked(o, ignore=(n,)):
                    L.open.append(dict(o, owner=n, depth=depth + 1))
    return True


def _lay_chamber(L, target, depth, hall_no, rng, final=False):
    """One of the kind's chambers (a cave's big rooms, a tomb's burial rooms) joined to the open opening
    target, as often as the game uses each; for the last one, the bigger the better. True when one fits."""
    rooms = [(pid, L.S['n'].get(pid, 1)) for pid in L.S['ports'] if role_of(pid, L.K, L.S) == 'room'
             and L.db.resolve_id(pid) is not None and L.S.get('agree', {}).get(pid, 0) >= L.K.get('room_agree', AGREE)]
    # (a kind whose last room is its own: a Velothi tower ends in its tower, the pit, and has it nowhere else)
    if L.K.get('final_room'):
        fr = re.compile(L.K['final_room'])
        rooms = [(pid, w) for pid, w in rooms if bool(fr.search(pid)) == bool(final)]
    if not rooms:
        return False
    if final:
        size = lambda pid: (lambda b: (b[3] - b[0]) * (b[4] - b[1]))(L.bounds(pid))
        rooms = [(pid, w * size(pid)) for pid, w in rooms]
    order = []
    pool = list(rooms)
    while pool:
        tot = sum(w for _p, w in pool)
        r = rng.random() * tot
        k = next((k for k, (_p, w) in enumerate(pool) if (r := r - w) <= 0), len(pool) - 1)
        order.append(pool.pop(k)[0])
    for pid in order[:8]:
        ks = list(range(len(L.S['ports'][pid])))
        rng.shuffle(ks)
        for k in ks:
            n = L.place_at(pid, k, target, depth, hall=hall_no)
            if n is not None:
                # (an exit high up a wall the game never reached from this way in has no stairs to it in
                # any of its dressings: it is closed with a dead end, not grown on from; the user's Gold Grotto)
                p = L.pieces[n]
                for o in L.open:
                    if o['owner'] != n:
                        continue
                    for j, (px, py, pz, _ps) in enumerate(L.S['ports'][pid]):
                        wx, wy = _rot(px, py, p['p'][5])
                        if abs(o['x'] - p['p'][0] - wx) < 16 and abs(o['y'] - p['p'][1] - wy) < 16 and abs(o['z'] - p['p'][2] - pz) < 16:
                            if not _climbable(L.S, pid, k, j):
                                o['cap'] = True
                            break
                return True
    return False


def _solid(S, tid):
    """A room tile's solid sides: those the game's rooms seldom carry on past (under a third of the time).
    """
    rec = (S.get('tiles') or {}).get(tid)
    if not rec:
        return frozenset()
    return frozenset(s_ for s_ in SIDES if rec['sides'].get(s_, 0) < 0.34)


def _tile_turn(S, tid, walls):
    """The quarter turn that puts a room tile's solid sides on the walls wanted (a set of sides), or None:
    a tile's solid sides are those the game's rooms seldom carry on past (under a third of the time)."""
    rec = (S.get('tiles') or {}).get(tid)
    if not rec:
        return None
    solid = _solid(S, tid)
    if len(solid) != len(walls):
        return None
    for q in range(4):
        rz = q * math.pi / 2
        if {_dir_of(*_rot(*SIDES[s_], rz)) for s_ in solid} == set(walls):
            return q
    return None


def _entries(K):
    e = K.get('entry_room')
    return list(e) if isinstance(e, (list, tuple)) else ([e] if e else [])


def _tall(K, tid):
    """Which height family a room tile is of (a Velothi tomb's tall rooms, in_v_s_int_l*, two storeys high)."""
    return bool(K.get('tall') and re.search(K['tall'], tid))


def _lay_room(L, target, w, h, depth, hall_no, rng, tall=False, k0=None):
    """A room of w x h tiles joined to the open opening target by the room's entry piece (a room's edge
    tile with the doorway in it), floor, side and corner tiles turned so their walls face out, a roof over
    every tile the game roofs; all of one height (tall: a Velothi tomb's two-storey rooms). True when it
    fits. Daedric rooms are of 512 tiles, Velothi ones of 256."""
    K, S = L.K, L.S
    eids = [e for e in _entries(K) if S['ports'].get(e) and _tall(K, e) == tall and L.db.resolve_id(e) is not None
            and S.get('agree', {}).get(e, 0) >= AGREE]
    if not eids:
        return False
    # (each of the kind's doorway tiles in turn, the commonest first: an Ayleid room off a wide hall has the wide
    # doorway tile, off a narrow one the narrow; the join rule tells which fits the opening)
    eids.sort(key=lambda e: -S['n'].get(e, 0) * (0.6 + rng.random()))

    def one(eid, k0=k0):
        ent = [k for k, p in enumerate(S['ports'].get(eid, []))]
        tiles = S.get('tiles') or {}
        by_walls = defaultdict(list)
        for tid, rec in tiles.items():
            if L.db.resolve_id(tid) is None or rec['n'] < 20 or _tall(K, tid) != tall:
                continue
            # (only the kind's room tiles, not a keep's big hall tiles twice their size, K['big'])
            tb = L.bounds(tid)
            if tb and max(tb[3] - tb[0], tb[4] - tb[1]) > K.get('tile', 512) + 32:
                continue
            by_walls[len(_solid(S, tid))].append((tid, rec['n']))
        if not by_walls.get(0) or not by_walls.get(1) or not by_walls.get(2):
            return False
        pick = lambda lst: max(lst, key=lambda t: t[1] * (0.6 + rng.random()))[0]
        floor_id, side_id, corner_id = pick(by_walls[0]), pick(by_walls[1]), pick(by_walls[2])
        T = K.get('tile', 512)
        for k in ent:
            n0 = len(L.pieces)
            open0 = list(L.open)
            seams0 = len(L.seams)
            e = L.place_at(eid, k, target, depth, hall=hall_no)
            if e is None:
                continue
            ep = L.pieces[e]
            # (the room lies on the entry's far side from the hall: the entry tile is on its near edge)
            into = OPP[_dir_of(*_rot(*SIDES[S['ports'][eid][k][3]], ep['p'][5]))]
            L.open = [o for o in L.open if o['owner'] != e]
            ux, uy = SIDES[into]
            vx, vy = -uy, ux                        # (along the near edge)
            # (k0: which tile of the near edge the doorway is, where a plan has set it, _grow_plan)
            k0 = (rng.randint(1, w - 2) if k0 is None else int(k0)) if w >= 3 else 0     # (the entry tile has the one wall, the doorway's: never a corner)
            if w < 3:
                return False
            laid = []
            for i in range(w):
                for j in range(h):
                    if i == k0 and j == 0:
                        continue
                    walls = set()
                    if j == 0:
                        walls.add(OPP[into])
                    if j == h - 1:
                        walls.add(into)
                    if i == 0:
                        walls.add(_dir_of(-vx, -vy))
                    if i == w - 1:
                        walls.add(_dir_of(vx, vy))
                    tid = {0: floor_id, 1: side_id, 2: corner_id}.get(len(walls))
                    q = _tile_turn(S, tid, walls) if tid else None
                    if q is None:
                        break
                    x = ep['p'][0] + (i - k0) * T * vx + j * T * ux
                    y = ep['p'][1] + (i - k0) * T * vy + j * T * uy
                    laid.append((tid, x, y, ep['p'][2], q * math.pi / 2))
                else:
                    continue
                break
            ok = len(laid) == w * h - 1 and L.fits([L.box(t, x, y, z, rz) for t, x, y, z, rz in laid], ignore=(e, target['owner']))
            if not ok:
                # (no room for it here: the entry piece taken back out)
                L.pieces = L.pieces[:n0]
                L.open = open0
                L.seams = L.seams[:seams0]
                continue
            for tid, x, y, z, rz in laid:
                L.add(tid, x, y, z, rz, depth, hall=hall_no)
                # (a ceiling over each floor tile, K['roof']: an Ayleid room's wall and corner tiles carry their own, its
                # floor tiles are a floor and nothing over it, the game's ceiling at the tile's own spot 37 times of 37)
                if K.get('roof') and tid == floor_id and L.db.resolve_id(K['roof']) is not None and L.bounds(K['roof']):
                    L.pieces[L.add(K['roof'], x, y, z, rz, depth, hall=hall_no)]['role'] = 'roof'
            return True
        return False

    return any(one(e) for e in eids)

def generate(db, size='medium', levels='some', twist='branching', seed=None, kind='dwemer', entry=None, final=None, way='down', keep=None):
    """A place's layout: {'pieces': [...], 'seams': [...], 'entrance': {...}, 'halls': n, 'seed'}. A growth
    that gets boxed in early, or finds no room for its last hall, is grown again from a seed drawn from this
    one (a tenth of a second each), and the best of up to 24 kept: the same seed always gives the same place.
    entry: a dead end's piece number to be the way in instead; final: the hall to be the last one (picked on
    the Dungeon tool's plan); way: 'down' from the way in, as most of the game's go, or 'up' (a tower).
    keep: a keep interior's asks (keepmaker.py): {'exits': doorways out besides the front door, 'spirals': spiral
    stair towers, 'turns': (least, most) turns each, 'big': the share of rooms that are big halls, 'traps': a trap
    door to the roof at each spiral's top}."""
    lay = _generate(db, size, levels, twist, seed, kind, way='up' if way == 'up' else 'down', keep=keep)
    if entry is not None or final is not None:
        _pick(db, survey(db, kind=kind), kit(kind), lay, entry, final)
    if keep and keep.get('exits'):
        _exits(db, survey(db, kind=kind), kit(kind), lay, int(keep['exits']))
    return lay


# ------------------------------------------------------------------ a keep's ways out, rings, spiral towers, big halls
# (the keep study of 2026-11-05, docs/keep-study-2026-11.md: a game keep interior has 1-9 doors to other interiors and
# 0-7 to the outside; 15 of 68 interiors have ring corridors, 49 rings in all; the big halls stand on 4-13 floor heights;
# towers are stacks of spiral stairs with a room at each landing; great halls, libraries and chapels are in_impbig)
def _exits(db, S, K, lay, n):
    """n more doorways out of the place: dead ends taken away and the seam each hung from kept as a way out, where a
    frame and a load door will stand (build). The farthest from the way in and from each other first, another floor
    counting as a little farther; each must leave every rule kept (dgrules: an exit closes its end as the front door
    closes the way in). lay['exits']: [{x, y, z, side, owner, piece}]. The number made."""
    import dgrules
    if not K.get('jamb'):
        return 0
    P = lay['pieces']
    e = lay.get('entrance') or {}
    lay.setdefault('exits', [])
    seam_of = lambda k: next((s for s in lay['seams'] if s[5] == k or s[4] == k), None)
    cands = [k for k, q in enumerate(P) if not q.get('gone') and q.get('role') == 'dead end' and q.get('hall') is None
             and q.get('id') and q.get('of') is None and q['id'] != K.get('plate') and seam_of(k) is not None]
    anchors = ([(e['x'], e['y'], e['z'])] if 'x' in e else []) + [(x['x'], x['y'], x['z']) for x in lay['exits']]
    made, tried, kept = 0, set(), {}
    # (in a keep's own blocks: a dead end the keep goes on beyond first, a door that leads on to what hangs from it;
    # those at the keep's outer face after, the doors to the outside)
    mass_ = lay.get('mass')

    def inward(k):
        if not mass_:
            return 0
        seam = seam_of(k)
        if seam is None:
            return 0
        side = seam[3] if seam[5] == k else OPP[seam[3]]
        (ox, oy, _oz), (dx, dy), blocks = mass_
        px, py = seam[0] + SIDES[side][0] * 470.0, seam[1] + SIDES[side][1] * 470.0
        a, c = (px - ox) * dx + (py - oy) * dy, (px - ox) * dy - (py - oy) * dx
        return 1 if any(M[0] <= a <= M[3] and M[1] <= c <= M[4] for M in blocks) else 0
    while made < n and len(tried) < len(cands):
        far = lambda k: min((math.hypot(P[k]['p'][0] - a[0], P[k]['p'][1] - a[1]) + (160 if abs(P[k]['p'][2] - a[2]) > 64 else 0)
                             for a in anchors), default=1e9) + 900.0 * inward(k)
        k = max((k for k in cands if k not in tried), key=far)
        tried.add(k)
        seam = seam_of(k)
        if seam is None or P[k].get('gone'):
            continue
        owner = seam[4] if seam[5] == k else seam[5]
        side = seam[3] if seam[5] == k else OPP[seam[3]]
        before = (dict(P[k]), list(lay['seams']))
        P[k] = dict(P[k], gone=True, box=(0, 0, 0, 0, 0, 0))
        lay['seams'] = [s for s in lay['seams'] if k not in (s[4], s[5])]
        ex = {'x': seam[0], 'y': seam[1], 'z': seam[2], 'side': side, 'owner': owner, 'piece': k}
        lay['exits'].append(ex)
        if not dgrules.ok(dgrules.check(db, lay, S, K, rays=False)):
            lay['exits'].pop()
            P[k] = before[0]
            lay['seams'] = before[1]
            continue
        kept[k] = before
        anchors.append((ex['x'], ex['y'], ex['z']))
        made += 1
    if made:
        # (the rays once, every exit closed as its door will close it: one that shows the void gets its dead end back)
        leak, tight = dgrules.seams_check(db, lay, kind=K['kind'])
        bad = {f[0] for f in leak} | {f[0] for f in tight}
        for ex in [x for x in lay['exits'] if x.get('piece') in kept and x['owner'] in bad]:
            lay['exits'].remove(ex)
            P[ex['piece']] = kept[ex['piece']][0]
            lay['seams'].append(next(s for s in kept[ex['piece']][1] if ex['piece'] in (s[4], s[5])))
            made -= 1
    return made


def _near(a, b, steps):
    """Whether opening b lies within steps tunnel lengths of opening a (256 along, 128 up or down a piece)."""
    return abs(a['x'] - b['x']) + abs(a['y'] - b['y']) <= steps * 256 + 64 and abs(a['z'] - b['z']) <= steps * 128 + 32


def _chain_to(L, port, B, kinds, rng, depth, budget):
    """A chain of up to depth tunnel pieces from the open opening port towards the open opening B, that ends where a
    piece's opening meets an open one (place_at closes the loop there; any open opening will do); everything laid is
    taken back when none does. budget: place_at tries left, shared by the search."""
    snap = L.snapshot()
    for pid, _role, _w in sorted(kinds, key=lambda c: -c[2] * (0.5 + rng.random())):
        ks = list(range(len(L.S['ports'][pid])))
        rng.shuffle(ks)
        for k in ks:
            if budget[0] <= 0:
                return False
            budget[0] -= 1
            n = L.place_at(pid, k, port, port['depth'])
            if n is None:
                continue
            if L.last_loops:
                return True
            if depth > 1:
                for o in [o for o in L.open if o['owner'] == n]:
                    if _near(o, B, depth - 1) and _chain_to(L, o, B, kinds, rng, depth - 1, budget):
                        return True
            L.restore(snap)
    return False


def _close_rings(L, rng, want, pool):
    """Ring corridors: from an open opening, a short chain of tunnel pieces to another open opening, closing a loop (the
    generator's layouts were trees; the game's keeps have 49 rings in 68 interiors). The dead ends are opened again
    first, so a ring may run from one stub to another (cap closes what stays open afterwards). want rings tried
    for; the number closed."""
    kinds = [c for c in pool if c[1] in ('straight', 'corner', 'ramp', 'T', 'cross')]
    if not kinds or want <= 0:
        return 0
    K = L.K
    # (every dead end taken away, its seam an open opening again: the chains may start or end at any of them)
    for n, p in enumerate(L.pieces):
        if p.get('gone') or p.get('role') != 'dead end' or p.get('hall') is not None or p.get('of') is not None or p.get('id') == K.get('plate'):
            continue
        s = next((s for s in L.seams if n in (s[4], s[5])), None)
        if s is None:
            continue
        o = s[4] if s[5] == n else s[5]
        L.pieces[n] = dict(p, gone=True, box=(0, 0, 0, 0, 0, 0))
        L.seams.remove(s)
        L.open.append({'x': s[0], 'y': s[1], 'z': s[2], 'side': s[3] if s[5] == n else OPP[s[3]], 'owner': o, 'depth': L.pieces[o]['depth'] + 1})
    closed = 0
    budget = [2000]
    starts = [o for o in L.open if not o.get('cap')]
    rng.shuffle(starts)
    near = 0
    for A in starts:
        if closed >= want or budget[0] <= 0:
            break
        if A not in L.open:
            continue
        targets = sorted([t for t in L.open if t is not A and not t.get('cap') and _near(A, t, 4)],
                         key=lambda t: abs(t['x'] - A['x']) + abs(t['y'] - A['y']) + 2 * abs(t['z'] - A['z']))
        if not targets:
            continue
        near += 1
        for B in targets[:3]:
            if _chain_to(L, A, B, kinds, rng, 4, budget):
                closed += 1
                break
    L.ring_debug = {'open': len(L.open), 'starts': len(starts), 'near': near, 'budget_left': budget[0]}
    return closed


def _lay_spiral(L, port, depth, rng, turns, order=None):
    """A spiral stair tower at an open opening (K['spiral']): turns of the spiral piece one over another, the floor piece
    under the lowest and the cap over the top, the trap door to the roof noted on the cap. The opening is met by the top
    turn's upper doorway in a place that goes down from its way in, by the lowest turn's lower doorway in one that
    climbs (the height rules); every other doorway is left open for the rooms and passages at the landings, closed with
    the plate otherwise (cap). True when it fits."""
    SP = L.K['spiral']
    pid, rise = SP['piece'], SP['rise']
    ports = L.S['ports'].get(pid) or []
    if len(ports) < 2 or L.db.resolve_id(pid) is None:
        return False
    up = L.way == 'up'
    # (order: which of its doorways meets the opening, where the caller tries each in turn, _grow_plan)
    order = sorted(range(len(ports)), key=lambda k: rng.random()) if order is None else order
    snap = L.snapshot()
    S0 = L.S
    L.S = dict(S0, rels=None)
    try:
        first = next((n for n in (L.place_at(pid, k, port, depth) for k in order) if n is not None), None)
        if first is None:
            return False
        P0 = L.pieces[first]
        x, y, z, rz = P0['p'][0], P0['p'][1], P0['p'][2], P0['p'][5]
        step = rise if up else -rise
        laid = [first]
        for t in range(1, turns):
            zt = z + step * t
            if not L.fits([L.box(pid, x, y, zt, rz)], ignore=set(laid)) or not L.level_ok(pid, zt, port):
                break
            n = L.add(pid, x, y, zt, rz, depth + t)
            L.pieces[n]['of'] = first
            for o in L.ports_of(pid, x, y, zt, rz):
                if not L.blocked(o, ignore=set(laid) | {n}):
                    L.open.append(dict(o, owner=n, depth=depth + t + 1))
            laid.append(n)
        if len(laid) < 2:
            L.restore(snap)
            return False
        lo = min(laid, key=lambda n: L.pieces[n]['p'][2])
        hi = max(laid, key=lambda n: L.pieces[n]['p'][2])
        for n, (cid, lx, ly, lz, dq) in ((lo, SP['bot']), (hi, SP['end'])):
            if L.db.resolve_id(cid) is None:
                continue
            q = L.pieces[n]['p']
            wx, wy = _rot(lx, ly, q[5])
            cx, cy, cz, crz = q[0] + wx, q[1] + wy, q[2] + lz, (q[5] + math.radians(dq)) % (2 * math.pi)
            if not L.fits([L.box(cid, cx, cy, cz, crz)], ignore=set(laid)):
                L.restore(snap)
                return False
            m = L.add(cid, cx, cy, cz, crz, depth)
            L.pieces[m]['of'] = first
            if cid == SP['end'][0] and SP.get('trap'):
                tid, tx, ty, tz, tq = SP['trap']
                wx, wy = _rot(tx, ty, q[5])
                L.pieces[m]['trap'] = [tid, q[0] + wx, q[1] + wy, q[2] + tz, (q[5] + math.radians(tq)) % (2 * math.pi)]
        return True
    finally:
        L.S = S0


def _lay_big(L, target, w, h, depth, hall_no, rng, exits=0, centre=False, at=None, ways_least=2):
    """A big hall of w x h in_impbig tiles (K['big']) joined to the open opening target by its doorway slab, with a wall
    slab in every other outer opening, as the game's great halls, libraries and chapels are put together. True when it
    fits."""
    B = L.K['big']
    tile, wall, blend, T = B['tile'], B['wall'], B['blend'], B['pitch']
    if any(L.db.resolve_id(i) is None for i in (tile, wall, blend)) or not L.S['ports'].get(blend):
        return False
    snap = L.snapshot()
    S0 = L.S
    L.S = dict(S0, rels=None)
    try:
        e = L.place_at(blend, 0, target, depth, hall=hall_no)
        if e is None:
            return False
        ep = L.pieces[e]
        bx, by, bz, bq = B['blend_at']
        trz = (ep['p'][5] - math.radians(bq)) % (2 * math.pi)
        wx, wy = _rot(-bx, -by, trz)
        t0 = (ep['p'][0] + wx, ep['p'][1] + wy, ep['p'][2] - bz)
        ux, uy = _rot(1.0, 0.0, trz)                 # (into the hall from its doorway)
        vx, vy = _rot(0.0, 1.0, trz)                 # (along the doorway's edge)
        # (centre: the way in on the hall's own axis, its length ahead of you; exits: ways on out of the hall, each a
        # doorway slab like the one you came in by, at the far end first, then half way down either side: a keep's
        # Great Hall is the room behind its door, and the rest of the keep leads off it)
        k0 = at if at is not None else h // 2 if centre else rng.randint(0, h - 1)
        ways = [(w - 1, k0, 'E'), (w // 2, 0, 'S'), (w // 2, h - 1, 'N')]
        if L.mass:
            # (in a keep's own blocks: only where a passage has room beyond the doorway, tried round the hall's rim; the
            # way on at the far end of Fort Urasek's hall ran straight into the keep's back wall, and nothing led up)
            def beyond_(i, j, s_):
                x = t0[0] + i * T * ux + (j - k0) * T * vx
                y = t0[1] + i * T * uy + (j - k0) * T * vy
                sx, sy = _rot(SIDES[s_][0], SIDES[s_][1], trz)
                cx, cy, zf = x + sx * (T / 2 + 256), y + sy * (T / 2 + 256), t0[2] + bz
                return L.fits([(cx - 100, cy - 100, zf, cx + 100, cy + 100, zf + 240)])
            rim_ = ways + [(i, 0, 'S') for i in range(w)] + [(i, h - 1, 'N') for i in range(w)] + [(w - 1, j, 'E') for j in range(h)] \
                + [(0, j, 'W') for j in range(h) if j != k0]
            ways = []
            for c_ in rim_:
                if c_ not in ways and len(ways) < int(exits) and beyond_(*c_):
                    ways.append(c_)
            # (a hall that fills the keep's ground leaves no way on: a hall of nine tiles in a middling keep had its
            # front door and nothing else, lab kr_try. Two ways on at least, where any are asked for; a smaller hall
            # or one to the side is tried next)
            if int(exits) >= 2 and len(ways) < ways_least:
                L.restore(snap)
                return False
        ways = ways[:max(0, int(exits))]
        turn_of = {'W': 0.0, 'N': math.pi / 2.0, 'E': math.pi, 'S': 3.0 * math.pi / 2.0}
        laid = []
        outs_ = []
        for i in range(w):
            for j in range(h):
                x = t0[0] + i * T * ux + (j - k0) * T * vx
                y = t0[1] + i * T * uy + (j - k0) * T * vy
                laid.append((tile, x, y, t0[2], trz))
                sides = (['W'] if i == 0 and j != k0 else []) + (['E'] if i == w - 1 else []) + (['S'] if j == 0 else []) + (['N'] if j == h - 1 else [])
                for s_ in sides:
                    if (i, j, s_) in ways:
                        a_ = trz + turn_of[s_]
                        ox, oy = _rot(bx, by, a_)
                        lx, ly, lz, dq = B['wall_at'][s_]
                        qx, qy = _rot(lx, ly, trz)
                        outs_.append((blend, x + ox, y + oy, t0[2] + bz, (a_ + math.radians(bq)) % (2 * math.pi),
                                      (wall, x + qx, y + qy, t0[2] + lz, (trz + math.radians(dq)) % (2 * math.pi))))
                        continue
                    lx, ly, lz, dq = B['wall_at'][s_]
                    ox, oy = _rot(lx, ly, trz)
                    laid.append((wall, x + ox, y + oy, t0[2] + lz, (trz + math.radians(dq)) % (2 * math.pi)))
        if not L.fits([L.box(t, x, y, z, rz) for t, x, y, z, rz in laid if t == tile], ignore=(e, target['owner'])):
            L.restore(snap)
            return False
        for t, x, y, z, rz in laid:
            # (the hall's tiles and walls go with the doorway slab: one place, their floor 128 under the doorway's, not
            # a storey over the way in as their origins would have them read, dgrules.heights)
            L.pieces[L.add(t, x, y, z, rz, depth, hall=hall_no)]['of'] = e
        for t, x, y, z, rz, back_ in outs_:
            k_ = L.add(t, x, y, z, rz, depth, hall=hall_no)
            L.pieces[k_]['hall_exit'] = back_ + (e,)       # (the wall slab that closes it again when nothing grows from it)
            for o in L.ports_of(t, x, y, z, rz)[:1]:
                L.open.append(dict(o, owner=k_, depth=depth + 1))
        return True
    finally:
        L.S = S0


def entry_ends(S, K, lay):
    """The dead ends that may be the way in: those up top, level with the highest floor (dgrules: the way in
    is the highest point). [piece number]"""
    import dgrules
    P = lay['pieces']
    if 'piece' in (lay.get('entrance') or {}):
        return []
    live = [p for p in P if not p.get('gone') and p.get('id') and p.get('of') is None]
    # (for a place that climbs, the dead ends down at the bottom)
    up = dgrules.climbs(lay)
    top = min(dgrules.floor_of(S, p) for p in live) if up else max(dgrules.floor_of(S, p) for p in live)
    out = []
    for n, q in enumerate(P):
        if q.get('gone') or q.get('role') != 'dead end' or q.get('hall') is not None:
            continue
        s = next((s for s in lay['seams'] if n in (s[4], s[5])), None)
        if s is not None and (s[2] <= top + dgrules.rise_cap(K) if up else s[2] >= top - dgrules.rise_cap(K)):
            out.append(n)
    return out


def _pick(db, S, K, lay, entry=None, final=None):
    """The way in and the last hall as picked on the plan (the user: "assign the way in, and the last one").
    The way in: a dead end taken away and the front door put at its seam, the old front door's end capped
    with a dead end; not for a kind whose way in is a piece of its own (a cave's mouth). The last one: any
    hall the layout has. Picks that don't fit are left as the layout had them."""
    halls = {p['hall'] for p in lay['pieces'] if p.get('hall') is not None and not p.get('gone')}
    try:
        final = int(final) if final not in (None, '') else None
    except (TypeError, ValueError):
        final = None
    if final in halls:
        lay['final'] = final
    try:
        entry = int(entry) if entry not in (None, '') else None
    except (TypeError, ValueError):
        entry = None
    e = lay.get('entrance') or {}
    if entry is None or 'piece' in e or not (0 <= entry < len(lay['pieces'])):
        return
    P = lay['pieces'][entry]
    if P.get('gone') or P.get('role') != 'dead end' or P.get('hall') is not None:
        return
    import dgrules
    said = lay.setdefault('said', [])
    seam_of = lambda n: next((s for s in lay['seams'] if s[5] == n or s[4] == n), None)
    # (the way in must be the highest point, dgrules: a dead end lower down gives way to the nearest one up top)
    ends = entry_ends(S, K, lay)
    hi, top = ('lowest', 'at the bottom') if dgrules.climbs(lay) else ('highest', 'up top')
    if entry not in ends:
        if not ends:
            said.append('The way in must be the %s point, and no dead end is %s: it stays where it was.' % (hi, top))
            return
        near = min(ends, key=lambda n: (lay['pieces'][n]['p'][0] - P['p'][0]) ** 2 + (lay['pieces'][n]['p'][1] - P['p'][1]) ** 2)
        said.append('The way in must be the %s point: put at the nearest dead end %s (piece %d) instead.' % (hi, top, near))
        entry, P = near, lay['pieces'][near]
    seam = seam_of(entry)
    if seam is None:
        return
    keep = (list(lay['pieces']), list(lay['seams']), dict(e), len(lay['pieces']))
    owner = seam[4] if seam[5] == entry else seam[5]
    # (the side out of the owner, towards where the dead end stood)
    side = seam[3] if seam[5] == entry else OPP[seam[3]]
    # the old front door's end closed with the kind's dead end, laid as the growth lays one
    # (without the join rule: the game stands the kind's dead end on its first straight's other end, the
    # same joint the other way round, and the rule refused every pick on the user's first try)
    L = _Layout(db, dict(S, rels=None), K)
    L.pieces = lay['pieces']
    dead = K['dead_end']
    old = dict(e)
    target = {'x': old['x'], 'y': old['y'], 'z': old['z'], 'side': old['side'], 'owner': old.get('owner', 0), 'depth': 1}
    L.open = [target]
    L.seams = lay['seams']
    capped = any(L.place_at(dead, k, target, 1) is not None for k in range(len(S['ports'].get(dead, []))))
    if not capped:
        return
    lay['pieces'][entry] = dict(P, gone=True, box=(0, 0, 0, 0, 0, 0))
    lay['seams'] = [s for s in lay['seams'] if entry not in (s[4], s[5])]
    lay['entrance'] = {'x': seam[0], 'y': seam[1], 'z': seam[2], 'side': side, 'owner': owner}
    # (the layout with its way in moved must keep every rule too, or the pick is refused)
    res = dgrules.check(db, lay, S, K)
    if not dgrules.ok(res):
        why = dgrules.say(lay, res)
        lay['pieces'], lay['seams'], lay['entrance'] = keep[0][:keep[3]], keep[1], keep[2]
        said.append('That dead end can\'t be the way in: %s' % why)
        return
    lay['picked'] = {'entry': entry, 'final': lay['final']}


def _generate(db, size='medium', levels='some', twist='branching', seed=None, kind='dwemer', way='down', keep=None):
    asks = keep                                 # (a keep interior's asks; 'keep' below is the layouts kept)
    K = kit(kind)
    S = survey(db, kind=kind)
    if not S or K['base'] not in S['ports']:
        raise EditError('The Workshop has not learnt the %s pieces yet: the game\'s own could not be read.' % K['label'])
    import dgrules
    seed = int(seed) if seed is not None else random.getrandbits(31)
    target, want_halls = halls_for(K if not asks else dict(K, rooms10=None), size)
    best = None
    sub = random.Random(seed)
    # (only a layout that keeps the rules is made, dgrules: the way in highest, all joined, no leaks, no
    # clashes, room to walk; the user: "prioritize making consistent and valid dungeons over total player
    # control". The rays, the slow part, are looked at only for the layout about to be kept)
    rayed = lambda lay: lay['rules'].update(zip(('leak', 'tight'), dgrules.seams_check(db, lay, kind=K['kind']))) or dgrules.ok(lay['rules'])
    keep = []                                   # (layouts that keep the rules but the rays, best first)
    checked = []                                # (at least half the size, with a last hall, rays and all kept)
    for attempt in range(GROWS):
        lay = _grow(db, S, K, size, levels, twist, seed if attempt == 0 else sub.getrandbits(31), way, asks)
        lay['K'] = K
        lay['rules'] = dgrules.check(db, lay, S, K, rays=False)
        # (a last hall counts only on a growth at least half the size asked for: ranked first, a large ruin of two
        # tunnel pieces and a hall beat every full-size one and stopped the search at attempt 15 too, the user's
        # "degenerate dungeons", 4 large Dwemer ruins in 25)
        # (the halls asked for count as much as ten tunnel pieces each: a huge ruin stopped at its first full-size
        # growth with four halls of five, the Halls choice's "many" with three of four)
        score = (dgrules.ok(lay['rules']), lay['final'] is not None and lay['tunnels'] >= 0.5 * target,
                 min(lay['tunnels'], target) + 10 * min(lay['halls'], want_halls), lay['final'] is not None, -lay['open_left'], -attempt)
        if lay.get('planned'):
            # (a layout by plan: whole when its rooms stand, most of them at least; ranked by how many do)
            pl_ = lay['planned']
            score = (score[0], pl_['laid'] >= 1, pl_['laid'], lay['final'] is not None, -lay['open_left'], -attempt)
            if score[0] and pl_['laid'] >= max(1, int(math.ceil(0.75 * pl_['asked']))) and rayed(lay):
                best = (score, lay)
                break
            if score[0]:
                keep.append((score, lay))
            elif best is None or score > best[0]:
                best = (score, lay)
            # (after a few growths the best so far that keeps every rule: where the keep's blocks hold half the
            # programme, forty growths found the same half each time, 128 growths for one Great Hall, lab gp2)
            if attempt >= 5 and keep:
                for sc_, ly_ in sorted(keep, key=lambda k_: k_[0], reverse=True)[:4]:
                    if rayed(ly_):
                        best = (sc_, ly_)
                        break
                if best and best[0][0]:
                    break
                keep = []
            continue
        if score[0] and score[1] and lay['tunnels'] >= 0.8 * target and lay['halls'] >= want_halls and rayed(lay):
            best = (score, lay)
            break
        if score[0] and score[1]:
            # (a good one, but short of the size: its rays looked at now, so the search stops after a while only for
            # one that keeps every rule. Stopping for one that later leaked left the user's seed with no last hall)
            if rayed(lay):
                checked.append((score, lay))
        elif score[0]:
            keep.append((score, lay))
        elif best is None or score > best[0]:
            best = (score, lay)                 # (the nearest miss, for saying what's wrong)
        # (no growth of the size asked for after a while: the best that keeps the rules will do)
        if attempt >= 15 and checked:
            break
    if not (best and best[0][0]) and checked:
        best = max(checked, key=lambda k: k[0])
    if not (best and best[0][0]):
        for score, lay in sorted(keep, key=lambda k: k[0], reverse=True)[:10]:
            if rayed(lay):
                best = (score, lay)
                break
            if best is None or not best[0][0]:
                best = ((False,) + score[1:], lay)
    if best is None:
        # (every growth kept the rules but the rays, and none was kept: said, not a crash)
        raise EditError('No %s with these choices keeps the rules (seed %d): every layout tried shows the void somewhere. Try another seed or size.' % (K['label'], seed))
    out = best[1]
    if not best[0][0]:
        raise EditError('No %s with these choices keeps the rules (seed %d): %s Try another seed or size.'
                        % (K['label'].lower() if K['label'].startswith('Cave') else K['label'], seed, dgrules.say(out, out['rules'])))
    out['seed'] = seed
    out['said'] = []
    if levels == 'steep' and out.get('too_deep'):
        out['said'].append('Kept within the climb of the game\'s own: no higher than %d over the way in.' % dgrules.climb_cap(K) if way == 'up' else
                           'Kept within the depth of the game\'s own: no deeper than %d below the way in.' % dgrules.deep_cap(K))
    return out


# ---- a keep's interior by plan
# (the brief of 2026-11-12, part 2: "the rooms are planned before any piece is laid". Grown by chance and named after,
# most rooms of a keep were whatever the growth left: a first round named 26 of 60 guard rooms. Here the programme
# comes first: for each of a keep's interiors its rooms in order from the door, each with its purpose, its size in
# tiles and whether it begins a storey up; the planner lays the passage to reach them, a T for each room with the
# room off its side, two stair pieces before a room a storey up, and leaves the passage's ends for the doors. The
# Great Hall, where the interior has one, stands first (hall_first) and the passages lead off its ways on.)
PLAN_ROOMS = {
    # (purpose, (tiles wide, tiles deep), a storey up from the last)
    'hall': (('kitchen', (3, 3), 0), ('guard room', (3, 2), 0), ('stores', (3, 2), 0), ('servants', (3, 2), 1)),
    'chambers': (('chamber', (3, 2), 0), ('study', (3, 2), 0), ('chamber', (3, 2), 1), ("lord's chamber", (4, 3), 1)),
    'household': (('kitchen', (3, 3), 0), ('stores', (3, 2), 0), ('servants', (3, 2), 1), ('dining', (3, 3), 0)),
    'garrison': (('barracks', (4, 3), 0), ('armoury', (3, 2), 0), ('guard room', (3, 2), 0), ('mess', (3, 3), 1), ('barracks', (3, 3), 0)),
    'library': (('study', (3, 2), 0),),
    'chapel': (('vestry', (3, 2), 0),),
    'tower': (('guard room', (3, 2), 0), ('armoury', (3, 2), 0), ('stores', (3, 2), 0), ('watch room', (3, 2), 0)),
    # (below ground, where a keep's blocks do not bound them: the gaoler's room by the door and the cells beyond and
    # below it; the undercroft's stores; the treasure chamber behind its guard room)
    'prison': (('guard room', (3, 2), 0), ('cells', (4, 3), 0), ('cells', (3, 3), 1), ('stores', (3, 2), 0)),
    'undercroft': (('stores', (3, 3), 0), ('stores', (3, 2), 0), ('stores', (4, 3), 1), ('stores', (3, 2), 0)),
    'treasury': (('guard room', (3, 2), 0), ('treasury', (3, 3), 0)),
}


GRID = 256.0                   # (a cell of the plan: one passage piece, one room tile; a storey is one cell up)
GRID_DRAWS = 60                # (plans drawn at each opening, the best laid)
GRID_REACH = 9                 # (cells from the opening at most, where the keep's blocks do not bound it)
GRID_DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _grow_plan(L, K, S, rng, keep, hall_no, pool):
    """The rooms of keep['rooms'], drawn on a grid before any piece is laid, then laid to the drawing. The grid: cells of
    256 from an opening on, a storey a cell up, a cell free where a piece would stand inside the keep's blocks and clear
    of what stands already. The drawing: a passage from the opening, each room a rectangle of cells with its doorway on
    the passage, a stair of two pieces to the storey over it, an end of passage for each door asked for; many drawn, the
    one that holds most of the programme kept. The laying: for each passage cell the piece its joins make it (straight,
    corner, T, crossing), the stairs, each room at its doorway. (rooms laid, hall_no after, {hall number: purpose}, the
    last room's number or None, a few counts)."""
    import dgrules
    role = keep.get('role')
    best = {}
    for pid, r_, w_ in pool:
        if r_ not in best or w_ > best[r_][1]:
            best[r_] = (pid, w_)
    T_, ST_, R_ = (best.get('T') or (None,))[0], (best.get('straight') or (K['base'],))[0], (best.get('ramp') or (None,))[0]
    C_, X_ = (best.get('corner') or (None,))[0], (best.get('cross') or (None,))[0]
    up = L.way == 'up'
    sg = 1.0 if up else -1.0
    purposes, final, laid = {}, None, 0
    said = {'drawn': 0, 'refused': 0, 'rooms_refused': 0, 'ends': 0}
    if keep.get('trace') is not None:
        keep['trace'].append('---')
    opens = lambda n: [o for o in L.open if o['owner'] == n and not o.get('cap')]
    key = lambda o: (round(o['x']), round(o['y']), round(o['z']), o['side'])
    step = lambda c, d, n=1: (c[0] + GRID_DIRS[d][0] * n, c[1] + GRID_DIRS[d][1] * n, c[2])
    over = lambda c: (c[0], c[1], c[2] + 1)

    def piece(pid, port, sides=None, dz=None, want=None):
        """(the piece joined at the opening by whichever of its own openings leaves it as wanted: its openings facing
        the sides given, one of them dz higher than the opening)"""
        if not pid:
            return None
        ks = list(range(len(S['ports'].get(pid, []))))
        rng.shuffle(ks)
        for k in ks:
            snap = L.snapshot()
            n = L.place_at(pid, k, port, port['depth'])
            if n is None:
                continue
            P = L.pieces[n]['p']
            ps = L.ports_of(pid, P[0], P[1], P[2], P[5])
            if (sides is None or {o['side'] for o in ps} == sides) and (dz is None or any(abs(o['z'] - port['z'] - dz) < 8 for o in ps)) \
                    and (want is None or want(opens(n))):
                return n
            L.restore(snap)
        return None

    def grid(start):
        """(the cells from an opening on: 0 the way the opening leads, 1 to its left, a storey up (down in a place that
        goes down); where each stands and whether a piece may)"""
        U = SIDES[start['side']]
        vec = [(U[0] * a - U[1] * b, U[1] * a + U[0] * b) for a, b in GRID_DIRS]
        x0, y0, z0 = start['x'] + U[0] * GRID / 2, start['y'] + U[1] * GRID / 2, start['z']
        ez = L.ez if L.ez is not None else z0
        hi, lo = ez + dgrules.climb_cap(K), ez - dgrules.deep_cap(K)
        seen = {}

        def free(c):
            if c not in seen:
                i, j, s = c
                x, y, z = x0 + GRID * (i * vec[0][0] + j * vec[1][0]), y0 + GRID * (i * vec[0][1] + j * vec[1][1]), z0 + sg * GRID * s
                if s < 0 or s > 5 or abs(i) > GRID_REACH or abs(j) > GRID_REACH or (z > hi if up else z < lo):
                    seen[c] = False
                else:
                    wide = L.too_wide
                    seen[c] = L.fits([(x - 118, y - 118, z - 128, x + 118, y + 118, z + 108)])
                    L.too_wide = wide
            return seen[c]
        return {'free': free, 'side': [_dir_of(*v) for v in vec]}

    def draw(g, prog, need, plain, r):
        """(one plan drawn at random from the opening: {'links': {passage cell: the ways it joins on}, 'rooms', 'stairs',
        'score'})"""
        used, links, par, rooms, stairs = {}, {}, {}, [], []
        prog = list(prog)
        ok = lambda c: c not in used and g['free'](c)

        def room(pc, d, strict=True):
            if not prog:
                return False
            purpose, size, up_ = prog[0]
            # (a room the programme has a storey up: over the last room's storey, while the drawing can still climb)
            if strict and up_ and rooms and pc[2] <= rooms[-1]['s']:
                return False
            e, v = step(pc, d), (d + 1) % 4
            sizes = []
            for s_ in (tuple(size), (size[1], size[0]), (3, 2)):
                if s_ not in sizes and s_[0] >= 3 and s_[1] >= 2:
                    sizes.append(s_)
            for w, h in sizes:
                k0s = list(range(1, w - 1))
                r.shuffle(k0s)
                for k0 in k0s:
                    cells = [(e[0] + GRID_DIRS[v][0] * (i - k0) + GRID_DIRS[d][0] * j, e[1] + GRID_DIRS[v][1] * (i - k0) + GRID_DIRS[d][1] * j, e[2])
                             for i in range(w) for j in range(h)]
                    if all(ok(c) for c in cells):
                        for c in cells:
                            used[c] = 'r'
                        rooms.append({'purpose': purpose, 'w': w, 'h': h, 'k0': k0, 'from': pc, 'd': d, 's': pc[2],
                                      'asked': w * h >= size[0] * size[1], 'up': bool(up_), 'prog': prog[0]})
                        links[pc].add(d)
                        prog.pop(0)
                        return True
            return False
        heads = [(None, (0, 0, 0), 0, plain)]
        while heads:
            pr, c, d, pl = heads.pop(0 if r.random() < 0.7 else r.randrange(len(heads)))
            if used.get(c) == 'held':
                del used[c]
            n_free = 0
            while n_free < 7 and ok(step(c, d, n_free)):
                n_free += 1
            if not n_free:
                if pr and pr[0] == 's':
                    # (a stair to nothing: out again)
                    st = stairs[pr[1]]
                    st['gone'] = True
                    links[st['from']].discard(st['d'])
                    for q in st['cells']:
                        used.pop(q, None)
                continue
            n = n_free if r.random() < 0.5 else r.randint(1, n_free)
            run = [step(c, d, k) for k in range(n)]
            back = (d + 2) % 4
            for k, pc in enumerate(run):
                used[pc] = 'p'
                links[pc] = {back}
                par[pc] = ('p', run[k - 1]) if k else pr
                if k:
                    links[run[k - 1]].add(d)
            if pr and pr[0] == 'p':
                links[pr[1]].add(d)
            elif pr and pr[0] == 's':
                stairs[pr[1]]['top'] = c
            # (plain: the opening is a great hall's doorway. Any piece may stand there: a straight, a corner, a T, a
            # crossing, a stair and a room were each set at one and none showed the void, lab gp9. Held to a plain
            # length first, a hall with one row of cells beside it had no side room and one door, lab kr_grid3. Only
            # the doorway's own cell is no door's place: a hall's way on that leads nowhere is walled again)
            for k, pc in enumerate(run):
                sides = [(d + 1) % 4, (d + 3) % 4]
                r.shuffle(sides)
                for sd in sides:
                    if prog and r.random() < 0.85:
                        room(pc, sd)
            t = run[-1]
            # (a stair straight on, or to one side from the passage's end: a keep block is three or four cells across,
            # and a stair straight on with the passage before it and the landing after wants four in a row, lab gp2)
            opts = ['room', 'stair', 'stair left', 'stair right', 'left', 'right']
            r.shuffle(opts)
            for o_ in opts:
                if not prog:
                    break
                if o_ == 'room':
                    if d not in links[t]:
                        room(t, d)
                elif o_.startswith('stair'):
                    sd = d if o_ == 'stair' else (d + 1) % 4 if o_.endswith('left') else (d + 3) % 4
                    a1, a2 = step(t, sd, 1), step(t, sd, 2)
                    cs, top = [a1, a2, over(a1), over(a2)], over(step(t, sd, 3))
                    if R_ and sd not in links[t] and all(ok(q) for q in cs) and ok(top) and r.random() < 0.75:
                        for q in cs:
                            used[q] = 's'
                        used[top] = 'held'
                        links[t].add(sd)
                        stairs.append({'from': t, 'd': sd, 'cells': cs})
                        heads.append((('s', len(stairs) - 1), top, sd, False))
                else:
                    sd = (d + 1) % 4 if o_ == 'left' else (d + 3) % 4
                    if sd not in links[t] and ok(step(t, sd)) and r.random() < 0.6:
                        heads.append((('p', t), step(t, sd), sd, False))
            for k, pc in enumerate(run[:-1]):
                for sd in ((d + 1) % 4, (d + 3) % 4):
                    if prog and sd not in links[pc] and ok(step(pc, sd)) and r.random() < 0.12:
                        heads.append((('p', pc), step(pc, sd), sd, False))
        # (what the programme still holds: at any side of the passage left, whichever storey it is on)
        first = None
        again = True
        while prog and again:
            again = False
            cells = [pc for pc in links if pc != first]
            r.shuffle(cells)
            for pc in cells:
                for d in r.sample(range(4), 4):
                    if d not in links[pc] and room(pc, d, strict=False):
                        again = True
                        break
                if again:
                    break
        # the ends, one for each door: a passage cell with no way on is one (left unlaid, the kit's dead end closes it
        # and a door takes its place); a passage that leads to nothing more is taken back, an end wanting is added
        def leaves():
            return [pc for pc, ds in links.items() if len(ds) == 1 and not (plain and pc == (0, 0, 0))]

        def drop(pc):
            pr = par.get(pc)
            back = next(iter(links[pc]))
            del links[pc]
            used.pop(pc, None)
            if pr and pr[0] == 'p' and pr[1] in links:
                links[pr[1]].discard((back + 2) % 4)
            elif pr and pr[0] == 's':
                st = stairs[pr[1]]
                st['gone'] = True
                if st['from'] in links:
                    links[st['from']].discard(st['d'])
                for q in st['cells']:
                    used.pop(q, None)
        for _k in range(80):
            lv = leaves()
            if len(lv) <= need or len(links) <= 1:
                break
            # (the nearest first: the doors stay far from the way in and from one another)
            drop(min(lv, key=lambda pc: (abs(pc[0]) + abs(pc[1]) + 2 * pc[2], r.random())))
        for _k in range(need):
            lv = leaves()
            if len(lv) >= need:
                break
            cands = [(pc, d) for pc in links if pc != first and len(links[pc]) > 1 for d in range(4) if d not in links[pc] and ok(step(pc, d))]
            if not cands:
                break
            far = lambda q: min([abs(q[0][0] - e[0]) + abs(q[0][1] - e[1]) + 2 * abs(q[0][2] - e[2]) for e in lv] or [9]) + 0.5 * (abs(q[0][0]) + abs(q[0][1])) + r.random()
            pc, d = max(cands, key=far)
            e = step(pc, d)
            used[e] = 'p'
            links[e] = {(d + 2) % 4}
            par[e] = ('p', pc)
            links[pc].add(d)
        ends = len(leaves())
        stairs = [st for st in stairs if not st.get('gone') and st.get('top')]
        score = 100 * len(rooms) + 12 * sum(1 for rm in rooms if rm['asked']) + 15 * sum(1 for k, rm in enumerate(rooms) if rm['up'] and k and rm['s'] > rooms[k - 1]['s']) \
            + 30 * min(ends, need) - len(links) - 3 * len(stairs) - 8 * sum(rm['s'] for rm in rooms if not rm['up'])     # (a room low where it can be: a kitchen two storeys over its hall, lab kr_grid1)
        return {'links': links, 'rooms': rooms, 'stairs': stairs, 'ends': ends, 'score': score, 'used': used}

    def lay(g, plan, start, plain):
        nonlocal hall_no, laid, final
        links, done = plan['links'], []
        room_at = {(rm['from'], rm['d']): rm for rm in plan['rooms']}
        stair_at = {(st['from'], st['d']): st for st in plan['stairs']}
        todo = [(start, (0, 0, 0))]
        while todo:
            port, c = todo.pop(0)
            D = links.get(c) or set()
            if len(D) <= 1:
                if not (plain and c == (0, 0, 0)):
                    said['ends'] += 1           # (an end: the opening left for the kit's dead end, a door's place)
                continue
            pid = (ST_ if (max(D) - min(D)) == 2 else C_) if len(D) == 2 else T_ if len(D) == 3 else X_
            n = piece(pid, port, sides={g['side'][d] for d in D})
            if n is None:
                said['refused'] += 1
                continue
            for d in sorted(D):
                o = next((o for o in L.open if o['owner'] == n and o['side'] == g['side'][d]), None)
                if o is None:
                    continue                    # (the way it was entered by, or one that met a passage laid already)
                if (c, d) in room_at:
                    rm = room_at[(c, d)]
                    if _lay_room(L, o, rm['w'], rm['h'], o['depth'], hall_no, rng, k0=rm['k0']):
                        purposes[hall_no] = rm['purpose']
                        final = hall_no
                        hall_no += 1
                        laid += 1
                        done.append(rm['prog'])
                    else:
                        said['rooms_refused'] += 1
                elif (c, d) in stair_at:
                    snap, p = L.snapshot(), o
                    for _k in range(2):
                        m = piece(R_, p, dz=sg * 128.0)
                        p = (opens(m) or [None])[0] if m is not None else None
                        if p is None:
                            break
                    if p is None:
                        L.restore(snap)
                        said['refused'] += 1
                    else:
                        todo.append((p, stair_at[(c, d)]['top']))
                else:
                    todo.append((o, step(c, d)))
        return done
    def spiral_at(port):
        """(the spiral stair at the opening, by either of its doorways: by the one tried first alone, a stair that had
        no room that way round was given up where it stood the other way)"""
        ks = list(range(len(S['ports'].get(K['spiral']['piece']) or [])))
        rng.shuffle(ks)
        return any(_lay_spiral(L, port, port['depth'], rng, 12, order=[k]) for k in ks)
    if role == 'tower' and K.get('spiral'):
        # a tower: the spiral stair where its tower stands, as high as the tower lets it; its rooms off the stair's foot
        if L.mass:
            (ox_, oy_, _oz), (idx_, idy_), blocks_ = L.mass
            cols_ = [M_ for M_ in blocks_ if M_[3] - M_[0] < 700 and M_[4] - M_[1] < 700 and M_[5] > 700]
            if cols_:
                top_ = max(cols_, key=lambda M_: M_[5])
                ta_, tc_ = (top_[0] + top_[3]) / 2.0, (top_[1] + top_[4]) / 2.0
                far_ = lambda o: math.hypot((o['x'] - ox_) * idx_ + (o['y'] - oy_) * idy_ - ta_, (o['x'] - ox_) * idy_ - (o['y'] - oy_) * idx_ - tc_)
                # (the stair tried at each step of the way: it stands whole inside the tower only from the tower's near
                # face, 474 of the tower's 526 across; walked on to the tower's middle first it had no room, lab gp2.
                # Three turns at least: two stand in the keep's body beside the tower as well)
                tall_ = lambda: sum(1 for p_ in L.pieces if not p_.get('gone') and p_.get('id') == K['spiral']['piece'])
                for _k in range(8):
                    ends_ = sorted([o for o in L.open if not o.get('cap')], key=far_)
                    if not ends_:
                        break
                    snap_ = L.snapshot()
                    if spiral_at(ends_[0]):
                        if tall_() >= 3:
                            break
                        L.restore(snap_)
                    if far_(ends_[0]) <= 140.0:
                        break
                    d0_ = far_(ends_[0])
                    n_ = piece(ST_, ends_[0], want=lambda os_: len(os_) == 1 and far_(os_[0]) < d0_ - 60.0) or \
                        piece(C_, ends_[0], want=lambda os_: len(os_) == 1 and far_(os_[0]) < d0_ - 60.0)
                    if n_ is None:
                        break
                if not tall_():
                    for port in sorted([o for o in L.open if not o.get('cap')], key=far_):
                        if spiral_at(port):
                            break
        if not any(p_.get('role') == 'spiral' for p_ in L.pieces if not p_.get('gone')):
            for port in sorted([o for o in L.open if not o.get('cap')], key=lambda o: o['depth']):
                if spiral_at(port):
                    break
    prog = [(r_[0], tuple(r_[1]), r_[2]) for r_ in keep['rooms']]
    need = int(keep.get('exits', 0))
    tried = set()
    first_ = {key(o) for o in L.open if not o.get('cap')}       # (the openings to plan from: those that stand before any plan is laid)
    for _round in range(10):
        cands = [o for o in L.open if not o.get('cap') and key(o) in first_ and key(o) not in tried]
        if not cands or (not prog and need <= 0):
            break
        # (at each opening the best of the plans drawn there; the opening whose plan holds most first)
        picks = []
        slab = lambda o: L.pieces[o['owner']].get('role') == 'blend' or bool(L.pieces[o['owner']].get('hall_exit'))
        grids = {key(o): grid(o) for o in cands}
        # (which openings can end in a door: one with room for a passage's end beyond it, a plain length first at a
        # great hall's doorway. A hall with three ways on, one of them a cell from the keep's wall, had three doors of
        # the four it needed, lab gp2: the share of an opening that cannot is the others')
        can = {key(o): bool(grids[key(o)]['free']((0, 0, 0)) and (not slab(o) or any(grids[key(o)]['free'](c_) for c_ in ((1, 0, 0), (0, 1, 0), (0, -1, 0))))) for o in cands}
        # (a tower's rooms two to a landing: all four off the stair's foot, the tower was a stair past a row of rooms)
        prog_ = prog[:2] if role == 'tower' and any(p_.get('role') == 'spiral' for p_ in L.pieces if not p_.get('gone')) else prog
        for o in cands:
            plain = slab(o)
            g = grids[key(o)]
            others = sum(1 for q in cands if q is not o and can[key(q)])
            share = max(1 if need > 0 else 0, int(math.ceil(need / float(others + 1))), need - others) if can[key(o)] else 0
            # (more drawn while the best holds less than the programme: the stair that reaches the storey with room on
            # it is one drawing in dozens)
            got = None
            for _t in range(GRID_DRAWS * 6):
                pl_ = draw(g, prog_, share, plain, rng)
                said['drawn'] += 1
                if got is None or pl_['score'] > got['score']:
                    got = pl_
                if _t + 1 >= GRID_DRAWS and (len(got['rooms']) >= len(prog_) or not g['free']((0, 0, 0))):
                    break
            picks.append((got['score'], -o['depth'], rng.random(), o, g, got, plain))
        _sc, _dp, _r, o, g, got, plain = max(picks, key=lambda q: q[:3])
        tried.add(key(o))
        if keep.get('trace') is not None:
            # (the drawing as text, a storey a block: # passage, a letter a room, ^ stair, . free, blank not)
            for s_ in range(0, 6):
                if not any(c_[2] == s_ for c_ in got['used']) and s_:
                    continue
                rows = ['opening %s storey %d (score %s, rooms %s, ends %d)' % (key(o), s_, got['score'], [rm_['purpose'] for rm_ in got['rooms']], got['ends'])]
                for i_ in range(GRID_REACH, -2, -1):
                    row = ''
                    for j_ in range(GRID_REACH, -GRID_REACH - 1, -1):
                        c_ = (i_, j_, s_)
                        u_ = got['used'].get(c_)
                        row += ('#' if c_ in got['links'] else '^' if u_ == 's' else 'r' if u_ == 'r' else '.' if g['free'](c_) else ' ')
                    if row.strip():
                        rows.append(row)
                keep['trace'].append(chr(10).join(rows))
        e0 = said['ends']
        done = lay(g, got, o, plain)
        for q in done:
            prog.remove(q)
        need -= said['ends'] - e0
    return laid, hall_no, purposes, final, said


def _lay_any(L, port, depth, hall_no, rng, final=False):
    """A hall, chamber or room, as the kind has them, at an open opening; True when one fits."""
    how = L.K.get('halls')
    if how == 'dwemer':
        sizes = ((5, 4), (4, 4), (4, 3), (5, 3)) if final else [rng.choice([(4, 3), (4, 4), (5, 3), (5, 4)])]
        return any(_lay_hall(L, port, w, h, depth, hall_no, rng, second_exit=not final) for w, h in sizes)
    if how == 'tiled':
        # (a keep's big hall now and then, K['big'], and for the last room of a large keep: a great hall)
        B = L.K.get('big')
        if B and B.get('share', 0.3) > 0 and (final and L.big or rng.random() < B.get('share', 0.3)):
            sizes_b = sorted(B['sizes'], key=lambda s: -s[0] * s[1])[:3] if final else [rng.choice(B['sizes'])]
            if any(_lay_big(L, port, w, h, depth, hall_no, rng) for w, h in sizes_b):
                return True
        # (Project Tamriel's Daedric guide: rooms of 2x3 to 3x4 tiles; a keep's own sizes from its kit)
        own = L.K.get('room_sizes')
        if own:
            sizes = sorted(own, key=lambda s: -s[0] * s[1]) if final else [rng.choice(own), min(own, key=lambda s: s[0] * s[1])]
        else:
            sizes = ((3, 4), (3, 3), (3, 2)) if final else [rng.choice([(3, 2), (3, 3), (3, 4), (4, 3)]), (3, 2)]
        lead = L.K.get('room_lead')
        if lead and L.pieces[port['owner']].get('id') != lead:
            # (a keep's room is off a short passage of its own, the game's every time: the passage laid first, the
            # room at its far end, both taken back out when the room doesn't fit)
            keep = (len(L.pieces), list(L.open), len(L.seams))
            for k in range(len(L.S['ports'].get(lead, []))):
                e = L.place_at(lead, k, port, depth)
                if e is None:
                    continue
                far = [o for o in L.open if o['owner'] == e]
                if far and any(_lay_room(L, far[0], w, h, depth + 1, hall_no, rng) for w, h in sizes):
                    return True
                del L.pieces[keep[0]:]
                L.open = list(keep[1])
                del L.seams[keep[2]:]
            return False
        return any(_lay_room(L, port, w, h, depth, hall_no, rng) for w, h in sizes)
    # (a Velothi tower's last room is the tower: its pit, laid whole)
    if final and L.K.get('final_room'):
        return _lay_chamber(L, port, depth, hall_no, rng, final=True)
    # (a tomb: a burial room of the game's own, or a hall tiled from its room tiles, now and then; the last
    # one of a large tomb a tall hall, two storeys high, as the game's great burial halls are)
    if L.K.get('tiles') and (final or rng.random() < 0.5):
        tall = final and L.K.get('tall') and L.big
        sizes = ((5, 4), (4, 4), (4, 3), (3, 3)) if final else [rng.choice([(3, 3), (4, 3), (3, 4), (5, 3)]), (3, 3)]
        if any(_lay_room(L, port, w, h, depth, hall_no, rng, tall=bool(tall)) for w, h in sizes):
            return True
        if tall and any(_lay_room(L, port, w, h, depth, hall_no, rng) for w, h in sizes):
            return True
    return _lay_chamber(L, port, depth, hall_no, rng, final=final)


def _keep_room(L, rng, hall_no, final=False, shallow=False):
    """A keep's room (K['room_lead']): at a T's own side, the side off its corridor (its last opening), or failing
    that at a corridor's open end with a T of its own laid there first (K['room_t']), the room off that T's side.
    The newest first while growing, laid before corridors fill round it; the deepest for the last one, the
    shallowest for those still owed. The tunnel pieces it added (0 or 1), or None when no room fits anywhere.
    (Rooms only at the T's that happened to be free left a large keep with many halls 1 time in 8 with all of
    them, a winding one 4 in 8, 2026-10-29)"""
    K, S = L.K, L.S
    grow = [o for o in L.open if not o.get('cap')]
    order = (lambda o: -o['depth']) if final else (lambda o: o['depth']) if shallow else (lambda o: -o['owner'])

    def t_side(o):
        P = L.pieces[o['owner']]
        ps = S['ports'].get(P.get('id')) or []
        return P.get('role') == 'T' and ps and o['side'] == _dir_of(*_rot(*SIDES[ps[-1][3]], P['p'][5]))
    # (and a side passage's open end, grown as a tunnel: the room straight on at it)
    for o in sorted((o for o in grow if t_side(o) or L.pieces[o['owner']].get('id') == K['room_lead']), key=order):
        if _lay_any(L, o, o['depth'], hall_no, rng, final=final):
            return 0
    tid = K.get('room_t')
    tports = S['ports'].get(tid) or []
    if not tid or len(tports) < 3:
        return None
    for o in sorted((o for o in grow if not t_side(o) and L.pieces[o['owner']].get('id') != K['room_lead']), key=order)[:16]:
        keep = (len(L.pieces), list(L.open), len(L.seams))
        for k in range(len(tports) - 1):
            t = L.place_at(tid, k, o, o['depth'])
            if t is None:
                continue
            side = next((x for x in L.open if x['owner'] == t and t_side(x)), None)
            if side is not None and _lay_any(L, side, side['depth'], hall_no, rng, final=final):
                return 1
            del L.pieces[keep[0]:]
            L.open = list(keep[1])
            del L.seams[keep[2]:]
    return None


def _grow(db, S, K, size, levels, twist, seed, way='down', keep=None):
    rng = random.Random(seed)
    target, n_halls = halls_for(K if not keep else dict(K, rooms10=None), size)
    keep = keep or {}
    if K.get('big') and keep.get('big') is not None:
        K = dict(K, big=dict(K['big'], share=float(keep['big'])))
    # the tunnel pieces to grow with, as often as the game uses each (with the asked-for mix)
    mix = {'linear': {'T': 0.3, 'cross': 0.15, 'straight': 1.3, 'corner': 1.0, 'dead end': 0.3},
           'branching': {}, 'maze': {'T': 1.6, 'cross': 1.8, 'dead end': 1.2, 'straight': 0.8}}.get(twist, {})
    ramp_k = {'flat': 0.0, 'some': 1.0, 'steep': 2.5}.get(levels, 1.0) * (1.6 if keep.get('mass') else 1.0)     # (a keep in its blocks climbs)
    pool = []
    for pid, ps in S['ports'].items():
        r = role_of(pid, K, S)
        if r in ('hall', 'shaft', 'other', 'room', 'entry', 'spiral', 'blend', 'big') or (K.get('skip') and re.search(K['skip'], pid)) or db.resolve_id(pid) is None or len(ps) < 1 or S.get('agree', {}).get(pid, 0) < AGREE:
            continue
        w = S['n'].get(pid, 1) * mix.get(r, 1.0) * (ramp_k if r == 'ramp' else 1.0) * (K.get('mix') or {}).get(r, 1.0)
        if w > 0:
            pool.append((pid, r, w))
    if not pool:
        raise EditError('No %s tunnel pieces with known openings.' % K['label'])
    if not S.get('cells'):
        # (its pieces in the load order and no place of the game's built of them: nothing to learn its rooms and dressing from)
        raise EditError("This load order has none of the game's own %ss to learn from." % K['label'].lower().replace('ayleid', 'Ayleid'))
    L = _Layout(db, S, K)
    L.big = (size or '').partition('+')[0] == 'large'
    L.way = way
    load = (S.get('door') or {}).get('load') or {}
    holder = load.get('holder') if isinstance(load, dict) else None
    entrance = None
    if holder and holder != K.get('jamb') and S['ports'].get(holder):
        # the way in: the kind's own entrance piece (a cave's exit), its openings the way on
        first = L.add(holder, 0.0, 0.0, 0.0, 0.0, 0)
        for o in L.ports_of(holder, 0.0, 0.0, 0.0, 0.0):
            L.open.append(dict(o, owner=first, depth=1))
        entrance = {'piece': first}
        L.ez = min(q[2] for q in S['ports'][holder])
    else:
        # the way in: a plain straight, its west end the front door's frame
        first = L.add(K['base'], 0.0, 0.0, 0.0, 0.0, 0)
        ports0 = L.ports_of(K['base'], 0.0, 0.0, 0.0, 0.0)
        for k, o in enumerate(ports0):
            if k == 0:
                entrance = dict(o, owner=first)
                L.ez = o['z']
            else:
                L.open.append(dict(o, owner=first, depth=1))
    if keep.get('mass') and entrance and entrance.get('side'):
        dx, dy = SIDES[OPP[entrance['side']]]
        L.mass = ((float(entrance['x']), float(entrance['y']), float(L.ez if L.ez is not None else entrance.get('z', 0.0))), (dx, dy),
                  [tuple(float(v) for v in b) for b in keep['mass']])
        if keep.get('rooms'):
            # (a tower's sections, one block each as the outside has them, taken as one column: a turn of the spiral
            # stair is 492 high and stood in no one section of 256, so a tower of twelve sections had no stair, lab gp2)
            cols_, rest_ = {}, []
            for M_ in L.mass[2]:
                if M_[3] - M_[0] < 700 and M_[4] - M_[1] < 700:
                    cols_.setdefault((round((M_[0] + M_[3]) / 400.0), round((M_[1] + M_[4]) / 400.0)), []).append(M_)
                else:
                    rest_.append(M_)
            for ms_ in cols_.values():
                ms_.sort(key=lambda M_: M_[2])
                run_ = list(ms_[0])
                for M_ in ms_[1:]:
                    if M_[2] <= run_[5] + 16:
                        run_ = [max(run_[0], M_[0]), max(run_[1], M_[1]), run_[2], min(run_[3], M_[3]), min(run_[4], M_[4]), max(run_[5], M_[5])]
                    else:
                        rest_.append(tuple(run_))
                        run_ = list(M_)
                rest_.append(tuple(run_))
            L.mass = (L.mass[0], L.mass[1], rest_)
        L.avoid = [tuple(float(v) for v in b) for b in keep.get('avoid') or ()]
    elif keep.get('box') and entrance and entrance.get('side'):
        # (the footprint from the door in: the keep's mass outside, a little over for the pieces' own reach)
        dx, dy = SIDES[OPP[entrance['side']]]
        L.bound = ((dx, dy), float(keep['box'][0]) + 128, float(keep['box'][1]) + 128)
    # (the halls on the way, spread evenly through the growth, the last one at the far end: two halls put the middle
    # one at 45%, three at 30% and 60%, as before; any number now, for the Halls choice and the huge size)
    # (a keep's rooms sooner, K['spread']: laid later, the corridors had filled the ground round every T beside one)
    halls_at = sorted({max(3, int(target * K.get('spread', 0.9) * (i + 1) / n_halls)) for i in range(n_halls - 1)})
    hall_no = 0
    tunnels = 1
    tries = 0
    planned = None
    if keep.get('rooms') and K.get('halls') == 'tiled' and keep.get('hall_first') and K.get('big') and L.open and L.mass:
        # (a planned keep: the hall's size chosen with the plan. The biggest hall that fits took the whole ground of a
        # keep of four blocks, twelve tiles, and left the plan nowhere to begin: no side room and one door of the four
        # the Great Hall was to have, lab kr_grid1. Each size that stands behind the door is planned from; the one whose
        # plan holds most rooms and doors is kept, the bigger of two that hold the same)
        port0_, snap0_, sizes_ = L.open[0], L.snapshot(), []
        ex_ = int(keep.get('hall_exits', 3))
        for least_ in (2, 1):
            for w_, h_ in sorted(K['big']['sizes'], key=lambda s_: (-(s_[0] * s_[1]), -s_[0])):
                if w_ < h_ or any(q_[:2] == (w_, h_) for q_ in sizes_):
                    continue
                for at_ in sorted(range(h_), key=lambda q: abs(q - h_ // 2)):
                    if _lay_big(L, port0_, w_, h_, 1, 0, rng, exits=ex_, centre=True, at=at_, ways_least=least_):
                        L.restore(snap0_)
                        sizes_.append((w_, h_, at_, least_))
                        break
        need_, best_ = int(keep.get('exits', 0)), None
        quiet_ = dict(keep, trace=None)
        for n_, (w_, h_, at_, least_) in enumerate(sizes_[:5]):
            sub_ = random.Random('%s|hall|%d' % (seed, n_))
            _lay_big(L, port0_, w_, h_, 1, 0, sub_, exits=ex_, centre=True, at=at_, ways_least=least_)
            got_ = _grow_plan(L, K, S, sub_, quiet_, 1, pool)
            L.restore(snap0_)
            val_ = 2 * got_[0] + 2 * min(got_[4]['ends'], need_) + 0.25 * w_ * h_
            if best_ is None or val_ > best_[0]:
                best_ = (val_, n_)
            if got_[0] >= len(keep['rooms']) and got_[4]['ends'] >= need_:
                break
        if best_ is not None:
            w_, h_, at_, least_ = sizes_[best_[1]]
            sub_ = random.Random('%s|hall|%d' % (seed, best_[1]))
            _lay_big(L, port0_, w_, h_, 1, 0, sub_, exits=ex_, centre=True, at=at_, ways_least=least_)
            halls_at = []
            n_laid_, hall_no, purposes_, final_plan_, said_ = _grow_plan(L, K, S, sub_, keep, 1, pool)
            planned = {'laid': n_laid_, 'asked': len(keep['rooms']), 'purposes': purposes_, 'final': final_plan_, 'said': said_, 'hall': [w_, h_]}
            tunnels = sum(1 for p_ in L.pieces if not p_.get('gone') and p_.get('hall') is None)
    if planned is None and keep.get('hall_first') and K.get('big') and L.open:
        # (a keep's Great Hall begins at its door: the hall first, at the entrance's own opening, the longest that
        # fits, its ways on at the far end and the sides. The game's: a median 315 from the door from outdoors to the
        # hall in 46 fort interiors with one, lab hall1; grown like any room the hall lay 747 off, up a stair
        # corridor, the user's Tharen Rise, 2026-11-11)
        port0_ = L.open[0]
        done_ = False
        # (the biggest hall that leaves two ways on from it; failing any, one way; failing that the biggest that fits:
        # a great keep's Great Hall had no hall in it when every size was refused for its ways, lab kr_after)
        for least_ in ((2, 1, 0) if L.mass else (0,)):
            for w_, h_ in sorted(K['big']['sizes'], key=lambda s_: (-(s_[0] * s_[1]), -s_[0])):
                # (on the door's own line first; then to one side of it, where the keep's blocks stand to one side of the door)
                for at_ in sorted(range(h_), key=lambda q: abs(q - h_ // 2)) if L.mass else (None,):
                    if w_ >= h_ and _lay_big(L, port0_, w_, h_, 1, hall_no, rng, exits=int(keep.get('hall_exits', 3)), centre=True, at=at_, ways_least=least_):
                        hall_no += 1
                        done_ = True
                        break
                if done_:
                    break
            if done_:
                break
        if not done_ and L.mass and L.open:
            # (a small keep's one block holds no hall of big tiles, and a one-tile hall filled it, leaving a Great Hall
            # of seven pieces, lab castle_made: the room behind the door is one of the kit's own rooms then, the
            # passages and stairs round it)
            if _lay_any(L, L.open[0], 1, hall_no, rng):
                hall_no += 1
    # (a keep's spiral stair towers, K['spiral']: as many as asked for, else one in half the large keeps; each a few
    # turns, from a third of the way in; a room at a landing or two straight after)
    spirals = keep.get('spirals')
    if spirals is None:
        spirals = 1 if K.get('spiral') and L.big and rng.random() < 0.5 else 0
    spirals = int(spirals) if K.get('spiral') else 0
    spiral_at = max(4, int(target * 0.3))
    # (in a keep's own blocks, L.mass: the keep climbs by a spiral stair, as the game's do, up each tower that stands
    # against the blocks, where it stands (the user's Fort Urasek: a stair to a small room and a door out where the tower
    # is, "Exit only? No tower?"); with no tower, one somewhere in the blocks. The stair goes as high as its block)
    towers_ = []
    if L.mass and K.get('spiral'):
        cols_ = {}
        for M_ in L.mass[2]:
            if M_[3] - M_[0] < 700 and M_[4] - M_[1] < 700:
                k_ = (round((M_[0] + M_[3]) / 400.0), round((M_[1] + M_[4]) / 400.0))
                cols_[k_] = ((M_[0] + M_[3]) / 2.0, (M_[1] + M_[4]) / 2.0, max(M_[5], cols_.get(k_, (0, 0, -1e9))[2]))
        towers_ = [t_ for t_ in sorted(cols_.values(), key=lambda t_: -t_[2]) if t_[2] > 700][:2]
        spirals = max(spirals, len(towers_), 1)
        spiral_at = 3
    rings_closed = 0
    if planned is None and keep.get('rooms') and K.get('halls') == 'tiled':
        # (a keep's interior by plan, _grow_plan: its rooms as the programme has them, no growth by chance)
        halls_at = []
        n_laid_, hall_no, purposes_, final_plan_, said_ = _grow_plan(L, K, S, rng, keep, hall_no, pool)
        planned = {'laid': n_laid_, 'asked': len(keep['rooms']), 'purposes': purposes_, 'final': final_plan_, 'said': said_}
        tunnels = sum(1 for p_ in L.pieces if not p_.get('gone') and p_.get('hall') is None)
    while planned is None and any(not o.get('cap') for o in L.open) and tunnels < target and tries < target * 60:
        tries += 1
        # which opening grows next: the newest mostly for a long winding route, any for a branching one
        grow = [o for o in L.open if not o.get('cap')]
        # (a kind's own way of growing, K['grow']: how often the deepest opening goes on, how often the shallowest.
        # Always 0.55 for the deepest, a made ruin ran out in a string, its far end 22 pieces from the door where the
        # game's of that size has it 12 off, and twice as deep)
        if twist == 'branching' and K.get('grow') and not L.mass and not keep:
            r_ = rng.random()
            if r_ < K['grow'][0]:
                port = max(grow, key=lambda o: (o['depth'], rng.random()))
            elif r_ < K['grow'][0] + K['grow'][1]:
                port = min(grow, key=lambda o: (o['depth'], rng.random()))
            else:
                port = rng.choice(grow)
        elif twist == 'linear' or (twist == 'branching' and rng.random() < 0.55):
            port = max(grow, key=lambda o: (o['depth'], rng.random()))
        else:
            port = rng.choice(grow)
        if spirals and L.mass and tunnels >= spiral_at:
            (ox_, oy_, _oz), (idx_, idy_), _bl = L.mass
            spot_ = lambda o: ((o['x'] - ox_) * idx_ + (o['y'] - oy_) * idy_, (o['x'] - ox_) * idy_ - (o['y'] - oy_) * idx_)
            ok_ = [o for o in grow if L.pieces[o['owner']].get('role') not in ('spiral', 'blend')]
            laid_ = False
            if towers_ and ok_:
                ta_, tc_, _tt = towers_[0]
                far_ = lambda o: math.hypot(spot_(o)[0] - ta_, spot_(o)[1] - tc_)
                ok_.sort(key=far_)
                near_ = [o for o in ok_[:3] if far_(o) <= 520.0]
                if not near_ and tunnels < 0.6 * target:
                    port = ok_[0]                     # (towards the tower: the opening nearest it grows next)
                    ok_ = []
                else:
                    ok_ = near_ or ok_[:2]
            for o in ok_[:3]:
                n0_ = len(L.pieces)
                if _lay_spiral(L, o, o['depth'], rng, 12):
                    got_ = sum(1 for p_ in L.pieces[n0_:] if p_.get('id') == K['spiral']['piece'])
                    spirals -= 1
                    tunnels += got_
                    spiral_at = tunnels + 6
                    if towers_:
                        towers_.pop(0)
                    for o2 in [o2 for o2 in L.open if L.pieces[o2['owner']].get('role') == 'spiral' and not o2.get('cap')][:6]:
                        if rng.random() < 0.5 and _lay_any(L, o2, o2['depth'], hall_no, rng):
                            hall_no += 1
                    laid_ = True
                    break
            if laid_:
                continue
            if ok_ and not towers_:
                spiral_at = tunnels + 2               # (no room for it at these openings: tried again a little further on)
        elif spirals and tunnels >= spiral_at and L.pieces[port['owner']].get('role') not in ('spiral', 'blend'):
            lo_, hi_ = keep.get('turns') or (2, 3)
            turns = rng.randint(int(lo_), int(hi_))
            if _lay_spiral(L, port, port['depth'], rng, turns):
                spirals -= 1
                tunnels += turns
                spiral_at = tunnels + 6
                for o in [o for o in L.open if L.pieces[o['owner']].get('role') == 'spiral' and not o.get('cap')][:4]:
                    if rng.random() < 0.6 and _lay_any(L, o, o['depth'], hall_no, rng):
                        hall_no += 1
                continue
        if halls_at and tunnels >= halls_at[0]:
            if K.get('room_lead'):
                got = _keep_room(L, rng, hall_no)
                if got is not None:
                    hall_no += 1
                    halls_at.pop(0)
                    tunnels += got
                else:
                    halls_at[0] = tunnels + 1       # (tried again once another piece is laid)
                continue
            if _lay_any(L, port, port['depth'], hall_no, rng):
                hall_no += 1
                halls_at.pop(0)
            elif tries % 8 == 0:
                # (no room for it anywhere near: tried again a few pieces on, where there may be. Dropped, a huge
                # ruin kept four halls of five and a Daedric one three)
                halls_at[0] = tunnels + 3
            continue
        cands = [c for c in pool if not (c[1] == 'dead end' and (len(L.open) <= 1 or tunnels < 4))]
        tot = sum(c[2] for c in cands)
        for _k in range(10):
            r = rng.random() * tot
            pid = next((c[0] for c in cands if (r := r - c[2]) <= 0), cands[-1][0])
            ports = L.S['ports'][pid]
            order = list(range(len(ports)))
            rng.shuffle(order)
            if any(L.place_at(pid, k, port, port['depth']) is not None for k in order):
                tunnels += 1
                break
        else:
            # (in a keep's own blocks, with no more floor this way: up, by a stair)
            if L.mass:
                ramps_ = [c for c in pool if c[1] == 'ramp']
                rng.shuffle(ramps_)
                if any(L.place_at(c[0], k, port, port['depth']) is not None for c in ramps_ for k in range(len(L.S['ports'][c[0]]))):
                    tunnels += 1
                    continue
            # (nothing fits here: this opening is left for a dead end)
            port['stuck'] = True
            if all(o.get('stuck') or o.get('cap') for o in L.open):
                break
    # (a keep's ring corridors, K['rings'] by size: the chance of one more past the whole number)
    want_r = (K.get('rings') or {}).get((size or '').partition('+')[0], 0)
    if keep.get('rings') is not None:
        want_r = keep['rings']
    want_n = int(want_r) + (1 if rng.random() < want_r - int(want_r) else 0)
    if want_n and planned is None:
        rings_closed = _close_rings(L, rng, want_n, pool)
    # (the halls still owed when the size was reached: at the open ends, the shallower first, the deepest kept for the
    # last one)
    for _h in list(halls_at):
        if K.get('room_lead'):
            if _keep_room(L, rng, hall_no, shallow=True) is not None:
                hall_no += 1
            continue
        ends = sorted((o for o in L.open if not o.get('cap')), key=lambda o: o['depth'])[:-1]
        if any(_lay_any(L, port, port['depth'], hall_no, rng) for port in ends):
            hall_no += 1
    # the last hall at the far end: the deepest opening that takes one
    final = planned['final'] if planned else None
    if K.get('room_lead') and planned is None:
        if _keep_room(L, rng, hall_no, final=True) is not None:
            final = hall_no
            hall_no += 1
    # (a kind whose rooms stand near each other, K['rooms_near']: the last one at the deepest opening within that reach
    # of a room already standing, before the deepest of all. A made tomb's two rooms lay 15 pieces apart, the game's 4)
    near_ = lambda o: 0
    if K.get('rooms_near') and not keep:
        hp_ = [p_['p'] for p_ in L.pieces if not p_.get('gone') and p_.get('hall') is not None]
        if hp_:
            near_ = lambda o: 0 if min(abs(o['x'] - q_[0]) + abs(o['y'] - q_[1]) + 2 * abs(o['z'] - q_[2]) for q_ in hp_) <= K['rooms_near'] else 1
    for port in ([] if K.get('room_lead') or planned is not None else sorted((o for o in L.open if not o.get('cap')), key=lambda o: (near_(o), -o['depth']))):
        if _lay_any(L, port, port['depth'], hall_no, rng, final=True):
            final = hall_no
            hall_no += 1
            break
    # every other open end closed: a dead end, or failing that the branch behind it taken away
    # (any of the kind's dead ends, its own first: with only the one, an end with no room for it was left open
    # onto the void, 'open' in a third of the made layouts, dgrules)
    deads = [K['dead_end']] + [c[0] for c in pool if c[1] == 'dead end' and c[0] != K['dead_end']]
    left = [0]
    # (a Great Hall's way on that nothing grew from: its doorway slab out again, the hall's own wall slab back in the
    # opening, _lay_big; capped like a corridor's end it stood a dead end behind a doorway, or took the hall away)
    for o in [o for o in L.open if L.pieces[o['owner']].get('hall_exit')]:
        k_ = o['owner']
        w_ = L.pieces[k_]['hall_exit']
        dep_, hall_ = L.pieces[k_].get('depth', 1), L.pieces[k_].get('hall')
        L.pieces[k_] = dict(L.pieces[k_], gone=True, box=(0, 0, 0, 0, 0, 0))
        L.pieces[L.add(w_[0], w_[1], w_[2], w_[3], w_[4], dep_, hall=hall_)]['of'] = w_[5]
        L.open.remove(o)

    def take_away(nodes):
        """Pieces taken out of the layout; every join they had with the rest opened again on the other side."""
        for c_ in nodes:
            L.pieces[c_] = dict(L.pieces[c_], gone=True, box=(0, 0, 0, 0, 0, 0))
        for s in L.seams:
            if (s[4] in nodes) == (s[5] in nodes):
                continue
            if s[5] in nodes:
                L.open.append({'x': s[0], 'y': s[1], 'z': s[2], 'side': s[3], 'owner': s[4], 'depth': L.pieces[s[4]]['depth'] + 1})
            else:
                L.open.append({'x': s[0], 'y': s[1], 'z': s[2], 'side': OPP[s[3]], 'owner': s[5], 'depth': L.pieces[s[5]]['depth'] + 1})
        L.seams[:] = [s for s in L.seams if s[4] not in nodes and s[5] not in nodes]
        L.open[:] = [o for o in L.open if o['owner'] not in nodes]

    def branch(own):
        """The piece and everything grown on from it, while that is a few tunnel pieces (no hall, not the way in)."""
        out, todo = {own}, [own]
        while todo:
            u = todo.pop()
            if u == first or L.pieces[u].get('hall') is not None or len(out) > 8 or L.pieces[u].get('role') == 'spiral' or L.pieces[u].get('of') is not None:
                return None
            for s in L.seams:
                if s[4] == u and s[5] not in out:
                    out.add(s[5])
                    todo.append(s[5])
        return out

    def cap():
        for _round in range(80):
            if not L.open:
                break
            port = L.open[0]
            # (a spiral's unused doorway is closed with the plate the game closes it with, K['plate'], first)
            deads_ = ([K['plate']] if K.get('plate') and L.pieces[port['owner']].get('role') == 'spiral' and S['ports'].get(K['plate']) else []) + deads
            # (a kind with a dead end for each sort of opening, K['dead_of'] [[owner id, optionally @side of its own
            # frame, the dead end]]: only that one there)
            for pat_, d_id in K.get('dead_of') or ():
                oid_ = L.pieces[port['owner']].get('id') or ''
                side_ = _dir_of(*_rot(*SIDES[port['side']], -L.pieces[port['owner']]['p'][5]))
                rx_, _at, sd_ = pat_.partition('@')
                if re.search(rx_, oid_) and (not sd_ or sd_ == side_):
                    deads_ = [d_id]
                    break
            else:
                if K.get('dead_of'):
                    deads_ = [d_ for d_ in deads_ if d_ not in {x[1] for x in K['dead_of']}]
            fits = lambda: any(L.place_at(d_, k, port, port['depth']) is not None for d_ in deads_ for k in range(len(S['ports'].get(d_, []))))
            # (a keep's side passage is never walled off at its end: open overhead there, it showed the void, 18 of
            # 24 leaks in large keeps; taken back out instead, as the game never ends one)
            framed_end = L.pieces[port['owner']].get('id') in (K.get('framed') or ())
            if not framed_end and fits():
                continue
            # (a dead end the game never stands against this piece, rather than an end open onto the void: the
            # leak rays judge the join, dgrules; lava caves' crossings had no other way to be closed)
            if not framed_end:
                L.S = dict(S, rels=None)
                got = fits()
                L.S = S
                if got:
                    continue
            # (no room for a dead end: take away the piece the opening belongs to, with what was grown on from it,
            # and open the seam it hung from instead)
            sub = branch(port['owner'])
            h = L.pieces[port['owner']].get('hall')
            if not sub and h is not None and h != final:
                # (a hall or chamber on the way with an exit that can't be closed, nothing grown on from it: taken
                # back out whole, its doorway capped instead)
                sub = {n for n, p in enumerate(L.pieces) if p.get('hall') == h and not p.get('gone')}
                if any(s[4] in sub and s[5] not in sub for s in L.seams):
                    sub = None
            if sub:
                take_away(sub)
            else:
                L.open.pop(0)                       # (left open: the rules refuse the layout, dgrules)
                left[0] += 1
    cap()
    # a side branch that climbs or drops only to end is taken back to where it left, and capped there (the
    # user: "a bed at the end of a descending staircase hallway ... who would build that just to put a bed
    # there and no room?"); a level stub stays, an alcove
    # (not in a planned keep: its only ends are the ones its plan left for doors, some up a stair, _grow_plan)
    for _cut in range(40 if planned is None else 0):
        inv = defaultdict(list)
        for s in L.seams:
            inv[s[4]].append(s)
            inv[s[5]].append(s)
        done = False
        for n, p in enumerate(L.pieces):
            # (any dead end, not only the kind's own: a tomb's stairs ran up to a cap_02 with an altar in it and
            # nothing more, "just an altar is strange", the user's Vabothi)
            if p.get('gone') or p.get('role') != 'dead end' or p.get('hall') is not None:
                continue
            chain, cur, climbs, top = [n], n, False, None
            while True:
                par = next((s for s in inv[cur] if s[5] == cur), None)
                if par is None:
                    break
                a = par[4]
                if a == first or L.pieces[a].get('hall') is not None or len(inv[a]) != 2:
                    top = par
                    break
                chain.append(a)
                cur = a
                if L.pieces[a].get('role') == 'ramp':
                    climbs = True
            if top is None or not climbs:
                continue
            # (the top seam is opened again with the rest of the chain's joins)
            take_away(set(chain))
            done = True
            break
        if not done:
            break
        cap()
    pieces = [p for p in L.pieces if not p.get('gone')]
    halls = len({p['hall'] for p in pieces if p.get('hall') is not None})
    return {'seed': seed, 'grown_from': seed, 'pieces': L.pieces, 'seams': L.seams, 'entrance': entrance, 'halls': halls, 'final': final,
            'planned': planned, 'mass': L.mass, 'open_left': len(L.open) + left[0], 'tunnels': sum(1 for p in pieces if p['hall'] is None), 'too_deep': L.too_deep, 'too_wide': L.too_wide, 'way': way,
            'rings': rings_closed, 'spirals': sum(1 for p in pieces if p.get('role') == 'spiral' and p.get('of') is None),
            'ring_debug': getattr(L, 'ring_debug', None)}


# where the way into a shrine's room lies, seen from its statue: in front of it, the statue's -Y (the game's
# Daedric ruins: the room's entrance piece at 270° in the statue's frame 25 times of 60, within 45° of it 35;
# the user: "usually the statue faces the door")
SHRINE_FACES = 270


def _shrine(db, c, S, lay, rng, key=None):
    """One of the game's shrines laid in the last room, as a whole: its statue where the game's stand in their
    rooms (SHRINE_BACK), all round it as the game had it (the user: "usually it has a shrine and a statue, an altar, gemstones and
    cups"; 59 of the game's 112 Daedric ruins have one). Of a few shrines and the four quarter turns, the
    one that leaves least of itself outside the room, its statue facing the room's way in. The room's own
    dressing is taken out of the shrine's footprint first (the user saw a shrine "clip into that platform
    with decor"). True when one is laid."""
    hp = [p for p in lay['pieces'] if p.get('hall') == lay['final'] and not p.get('gone') and p.get('box')]
    if not hp:
        return False
    # (the room's middle from its tiles' own bounds: the middle of the floor found by rays was pulled to one
    # side by the side tiles' half walls, "it's not centered in room", the user's Zajamima, 2026-10-26)
    bx0, by0 = min(p['box'][0] for p in hp), min(p['box'][1] for p in hp)
    bx1, by1 = max(p['box'][3] for p in hp), max(p['box'][4] for p in hp)
    fz = min(p['p'][2] for p in hp)
    mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
    # (the way in: the room's entry piece, else the piece of the room nearest the front door's side)
    K = lay.get('K') or {}
    way = next((p for p in hp if p['id'] in _entries(K)), None) or min(hp, key=lambda p: p.get('depth', 0))
    wa = math.atan2(way['p'][1] - my, way['p'][0] - mx)
    # (the floor inside the room's walls, found by rays across it from the middle: the tiles' boxes run out to
    # the walls' outer faces, and a statue, its platform and steps went through the room's corner and side
    # pieces, "completely discombobulated", the user's Zarathustra, 2026-10-26)
    x0, y0, x1, y1 = _inner_rect(db, hp, mx, my, fz, (bx0, by0, bx1, by1))
    # (and the room's ceiling over it, its roofs with it: the statue's head ran up into it, the user's Zajamima)
    roof_sc = None
    if key:
        import seethrough
        struct = re.compile(K.get('tube', '^$') + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['roofs']) if K.get('roofs') else ''))
        roof_sc = seethrough.Scene()
        for r in mapdata.cellmap(db, key)['refs']:
            if r.get('ri') is not None and struct.match(r['id'].lower()) and bx0 - 64 <= r['p'][0] <= bx1 + 64 and by0 - 64 <= r['p'][1] <= by1 + 64:
                mo = db.recs[r['ri']][5]
                if mo:
                    roof_sc.add_model(seethrough.model_tris(db, mo), r['p'], r['s'])

    def ceiling(x, y):
        h = roof_sc.nearest_any((x, y, fz + 20), (0.0, 0.0, 1.0), 4000) if roof_sc else None
        return fz + 20 + h[0] if h else None

    def bounds(rid):
        ri = db.resolve_id(rid)
        return mapdata.object_bounds(db, ri) if ri is not None else None

    def footprint(rid, lx, ly, s, q, drz, sx, sy):
        """An item's box from above, turned as it would stand with the statue at (sx, sy): (x0, y0, x1, y1)."""
        b = bounds(rid)
        if not b:
            return None
        wx, wy = _rot(lx, ly, q)
        xs, ys = [], []
        for bx in (b[0], b[3]):
            for by in (b[1], b[4]):
                rx_, ry_ = _rot(bx * s, by * s, (q + drz) % (2 * math.pi))
                xs.append(sx + wx + rx_)
                ys.append(sy + wy + ry_)
        return min(xs), min(ys), max(xs), max(ys)

    best = None
    for sh in rng.sample(S['shrines'], len(S['shrines'])):
        if db.resolve_id(sh['statue']) is None:
            continue
        items = _shrine_items(db, sh)
        parts = [(sh['statue'], 0, 0, sh.get('s') or 1.0, 0.0, sh['z'])] + [(it[0], it[2], it[3], it[8], it[7], it[4]) for it in items]
        for q in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            # (where the game's own stand: across the room on its middle line (42 off, p50 of 36 game shrines),
            # and along the way the statue faces three quarters of the way from the wall behind it to the
            # room's middle, its back to that wall; nearer the middle when that doesn't fit)
            back = _rot(0.0, 1.0, q)
            ax = abs(back[0]) > abs(back[1])
            half = ((x1 - x0) if ax else (y1 - y0)) / 2
            for frac in (SHRINE_BACK, SHRINE_BACK / 2, 0.0):
                sx, sy = mx + back[0] * frac * half, my + back[1] * frac * half
                # (every piece of it, the statue first, wholly inside the walls and under the ceiling: a shrine
                # that doesn't fit is left out, not cut down, as the game puts its big shrines only in rooms
                # big enough for them)
                fits = True
                for rid, lx, ly, s, drz, lz in parts:
                    f = footprint(rid, lx, ly, s, q, drz, sx, sy)
                    if not f:
                        continue
                    if f[0] < x0 - 8 or f[1] < y0 - 8 or f[2] > x1 + 8 or f[3] > y1 + 8:
                        fits = False
                        break
                    top = fz + lz + bounds(rid)[5] * s
                    for px, py in ((f[0], f[1]), (f[2], f[1]), (f[0], f[3]), (f[2], f[3]), ((f[0] + f[2]) / 2, (f[1] + f[3]) / 2)):
                        cz = ceiling(px, py)
                        if cz is not None and top > cz - SHRINE_HEADROOM:
                            fits = False
                            break
                    if not fits:
                        break
                if fits:
                    break
            if not fits:
                continue
            # (the way in, in the statue's frame turned by q: _rot turns clockwise, so its frame's angle is
            # the world's plus q)
            la = math.degrees(wa + q) % 360
            off = abs((la - SHRINE_FACES + 180) % 360 - 180)
            score = (round(off / 45), frac != SHRINE_BACK)
            if best is None or score < best[0]:
                best = (score, sh, q, sx, sy, items)
    if best is None:
        return False
    _score, sh, q, sx, sy, items = best
    refs = [(sh['statue'], (sx, sy, fz + sh['z'], 0, 0, q), [], sh.get('s') or 1.0)]
    for rid, t, lx, ly, lz, rx, ry, drz, s in items:
        wx, wy = _rot(lx, ly, q)
        refs.append((rid, (sx + wx, sy + wy, fz + lz, rx, ry, (q + drz) % (2 * math.pi)), [], s))
    if key:
        # the room's own dressing out of the shrine's footprint: anything whose box reaches into the shrine's
        # things' boxes and a hand round them; and every other platform, stair and statue in the room (the
        # user's Zajamima had a room tile's own platform standing beside the shrine's: "the platform is
        # duplicated")
        fp = [f for f in (footprint(rid, 0, 0, s, pos[5], 0.0, pos[0], pos[1]) for rid, pos, _e, s in refs) if f]
        fx0, fy0 = min(f[0] for f in fp) - 64, min(f[1] for f in fp) - 64
        fx1, fy1 = max(f[2] for f in fp) + 64, max(f[3] for f in fp) + 64
        shrine_re = re.compile(SHRINE_STAND + ('|' + K['shrine'] if K.get('shrine') else ''))
        for r in mapdata.cellmap(db, key)['refs']:
            i = r['id'].lower()
            if r['type'] in ('DOOR', 'NPC_') or struct.match(i) or i == K.get('jamb'):
                continue
            x, y, z = r['p'][:3]
            if not (fz - 60 <= z <= fz + 900):
                continue
            if shrine_re.search(i) and bx0 <= x <= bx1 and by0 <= y <= by1:
                c['refs'].pop(r['k'], None)
                continue
            b = r.get('b')
            s = r.get('s') or 1.0
            if b:
                xs_, ys_ = [], []
                for ex in (b[0], b[3]):
                    for ey in (b[1], b[4]):
                        rx_, ry_ = _rot(ex * s, ey * s, r['p'][5])
                        xs_.append(x + rx_)
                        ys_.append(y + ry_)
                hit = min(xs_) < fx1 and max(xs_) > fx0 and min(ys_) < fy1 and max(ys_) > fy0
            else:
                hit = fx0 <= x <= fx1 and fy0 <= y <= fy1
            if hit:
                c['refs'].pop(r['k'], None)
    _write_refs(db, c, refs)
    db.sync_project()
    return True


# (where in its room a shrine's statue stands, along the way it faces: this share of the way from the room's
# middle to the wall behind it; the game's own, from their rooms' tiles: 0.24, p25-p75 0.08-0.35, 16 shrines;
# scratch j_gshrine3.py, 2026-10-26. Made ones stand at 0.19, the walls' own depth taken off)
SHRINE_BACK = 0.23
SHRINE_HEADROOM = 40       # (over the statue's head to the ceiling: the game's own least, 41 of 36 shrines)
SHRINE_STAND = r'platform|stair|step'


CLOSE_OVER = 0.15          # a chamber seeing the void this much more often than the game's own of it is closed
CLOSER_SIZE = 300          # (a rock formation at least this across: one that walls off a chamber's open rock)


def _close_chambers(db, key, lay, S, K, rng):
    """A cave chamber whose open rock shows the void, closed as the game closes it: the game's chambers are
    open shells it fills with big rock formations (in_moldcave_25 holds in_mold_rock_13-24 in most of its 69
    places), and a made one whose drawn set had none, or lost them in the tidying, showed the void from 81%
    of its spots against the game's 8% (the user's Bucci, 2026-10-26). From inside, eye-height rays as
    dgrules.inside; over the game's own share by CLOSE_OVER, the big rocks of one of the game's sets for that
    piece are laid, the first that brings it to the game's share without standing in a doorway. Returns how
    many chambers were closed."""
    import dgrules
    import seethrough
    m = mapdata.cellmap(db, key)
    c = db.project.cells[key]
    closed = 0
    for n, p in enumerate(lay['pieces']):
        if p.get('gone') or p.get('hall') is None or not p.get('box') or p.get('of') is not None:
            continue
        g = dgrules.inside_share(K['kind'], p['id'])
        if g is None:
            continue
        b = p['box']
        # (the whole place: with only what stood near the chamber, rays that the far rock stops counted as out,
        # and chambers as open as the game's got rocks they didn't need)
        near = [r for r in m['refs'] if r.get('ri') is not None and (r.get('arch') or r['type'] == 'DOOR')]

        def scene_with(extra):
            sc = seethrough.Scene()
            for r in near:
                mo = db.recs[r['ri']][5]
                if mo and 'marker' not in mo.lower():
                    sc.add_model(seethrough.model_tris(db, mo), r['p'], r['s'])
            for rid, pos, _e, s in extra:
                mo = db.recs[db.resolve_id(rid)][5]
                if mo:
                    sc.add_model(seethrough.model_tris(db, mo), pos, s)
            return sc
        sc0 = scene_with([])
        spots, seen = dgrules.inside(sc0, b)
        if spots < 4 or seen / spots <= g + CLOSE_OVER:
            continue
        roomy = lambda sc, d: (lambda h: h is not None and h[1] is not None and h[1] >= 100)(dgrules._probe(sc, d[0], d[1], d[2] + 40))
        # (the doorways: a step in from each of the chamber's openings must keep room to stand)
        doors = []
        for px, py, pz, ps in S['ports'].get(p['id']) or []:
            wx, wy = _rot(px, py, p['p'][5])
            dx, dy = _rot(*SIDES[ps], p['p'][5])
            doors.append((p['p'][0] + wx - dx * 96, p['p'][1] + wy - dy * 96, p['p'][2] + pz))
        groups = []
        used_ = set(_ports_used(S, lay, n))
        # (the sets of game chambers that used the same openings first: their rocks leave those ways free)
        for st in (S.get('dress') or {}).get(p['id']) or []:
            grp = []
            for rid, t, lx, ly, lz, rx, ry, drz, s in _set_items(st):
                ri = db.resolve_id(rid)
                bb = mapdata.object_bounds(db, ri) if ri is not None and t == 'STAT' else None
                if not bb or max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) * s < CLOSER_SIZE or not re.search(K['dress'], rid.lower()):
                    continue
                wx, wy = _rot(lx, ly, p['p'][5])
                grp.append((rid, (p['p'][0] + wx, p['p'][1] + wy, p['p'][2] + lz, rx, ry, (p['p'][5] + drz) % (2 * math.pi)), [], s))
            if grp:
                groups.append((isinstance(st, dict) and set(st['u']) == used_, grp))
        head = [g_ for same, g_ in groups if same]
        tail = [g_ for same, g_ in groups if not same]
        rng.shuffle(head)
        rng.shuffle(tail)
        groups = head + tail
        best = None
        for grp in groups[:8]:
            sc = scene_with(grp)
            a, s_ = dgrules.inside(sc, b)
            if not a:
                continue
            # (room to stand a step in from every doorway that had it)
            if any(roomy(sc0, d) and not roomy(sc, d) for d in doors):
                continue
            share = s_ / a
            if best is None or share < best[0]:
                best = (share, grp)
            if share <= g + 0.05:
                break
        if best and best[0] <= g + CLOSE_OVER:
            _write_refs(db, c, best[1])
            db.sync_project()
            m = mapdata.cellmap(db, key)
            closed += 1
    return closed


def _shrine_items(db, sh):
    """A shrine's things, without the platforms and stairs that only stood near it in the game's place: kept,
    the platforms under the statue and those and the stairs joined to them, and what stands on them; the
    survey took everything within 700 of the statue, and a second platform beside the shrine looked doubled."""
    stand = re.compile(SHRINE_STAND)

    def box(it):
        ri = db.resolve_id(it[0])
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            return None
        s = it[8]
        xs, ys = [], []
        for bx in (b[0], b[3]):
            for by in (b[1], b[4]):
                rx_, ry_ = _rot(bx * s, by * s, it[7])
                xs.append(it[2] + rx_)
                ys.append(it[3] + ry_)
        return min(xs), min(ys), max(xs), max(ys)
    live = [it for it in sh['items'] if db.resolve_id(it[0]) is not None]
    plats = [(it, box(it)) for it in live if stand.search(it[0].lower()) and box(it)]
    kept = [(it, b) for it, b in plats if b[0] <= 0 <= b[2] and b[1] <= 0 <= b[3]]
    grew = True
    while grew:
        grew = False
        for it, b in plats:
            if any(it is k[0] for k in kept):
                continue
            if any(b[0] <= k[2] + 24 and b[2] >= k[0] - 24 and b[1] <= k[3] + 24 and b[3] >= k[1] - 24 for _i, k in kept):
                kept.append((it, b))
                grew = True
    dropped = [b for it, b in plats if not any(it is k[0] for k in kept)]
    out = []
    for it in live:
        if stand.search(it[0].lower()):
            if any(it is k[0] for k in kept):
                out.append(it)
            continue
        # (what stood on a platform left out goes with it)
        if it[4] > 30 and any(b[0] <= it[2] <= b[2] and b[1] <= it[3] <= b[3] for b in dropped):
            continue
        out.append(it)
    return out


def _inner_rect(db, hp, mx, my, fz, box):
    """A room's floor inside its walls (x0, y0, x1, y1): rays from about its middle to each side, at knee,
    chest and head height and a little to either side, against the room's own pieces only."""
    import seethrough
    sc = seethrough.Scene()
    for p in hp:
        ri = db.resolve_id(p['id'])
        mo = db.recs[ri][5] if ri is not None else None
        if mo:
            sc.add_model(seethrough.model_tris(db, mo), p['p'], 1.0)
    x0, y0, x1, y1 = box
    for h in (40, 140, 260):
        for off in (-96, 0, 96):
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                o = (mx + (off if dy else 0), my + (off if dx else 0), fz + h)
                hit = sc.nearest_any(o, (float(dx), float(dy), 0.0), 4000)
                if not hit:
                    continue
                if dx < 0:
                    x0 = max(x0, o[0] - hit[0])
                elif dx > 0:
                    x1 = min(x1, o[0] + hit[0])
                elif dy < 0:
                    y0 = max(y0, o[1] - hit[0])
                else:
                    y1 = min(y1, o[1] + hit[0])
    return x0, y0, x1, y1


def _ports_used(S, lay, n):
    """Which of a laid piece's openings something joins: [index] (a seam at the opening's spot)."""
    p = lay['pieces'][n]
    x, y, z, rz = p['p'][0], p['p'][1], p['p'][2], p['p'][5]
    out = []
    for k, (px, py, pz, _ps) in enumerate(S['ports'].get(p['id'], [])):
        wx, wy = _rot(px, py, rz)
        if any((s[4] == n or s[5] == n) and abs(s[0] - x - wx) < 16 and abs(s[1] - y - wy) < 16 and abs(s[2] - z - pz) < 16
               and not lay['pieces'][s[5] if s[4] == n else s[4]].get('gone') for s in lay['seams']):
            out.append(k)
    return out


def _climbable(S, pid, a, b):
    """Whether the game ever joined a chamber at both openings a and b (so a set of its dressing has the way
    from one to the other: stairs, a ramp, a platform). Openings at much the same height need none."""
    ps = S['ports'].get(pid) or []
    if a >= len(ps) or b >= len(ps) or abs(ps[a][2] - ps[b][2]) < 160:
        return True
    sets = (S.get('dress') or {}).get(pid) or []
    if not any(isinstance(st, dict) for st in sets):
        return True                   # (an old survey: no way to tell)
    return any(isinstance(st, dict) and a in st['u'] and b in st['u'] for st in sets)


# ------------------------------------------------------------------ dressing, doors and the place itself
# kwama egg sacs, egg piles and veins: an egg mine's (the user: "you usually don't find these unless you're in a
# kwama egg mine"); the game's egg mines are caves too, so their sets came into every made cave
EGG_MINE = re.compile(r'kwama|_kwa_|egg_?sac|eggsac|egg_?mine|kwamaegg|contain_egg')
FLAT_ON_FLOOR = re.compile(r'rubble|debris|decal|_dirt|_scorch')
FLAT_LIFT = 1.5


# ---- a fort's rooms dressed for what they are, and each thing only with what it leaned or stood on
# (the user, 2026-11-12, on a made Great Hall: "tapestries hanging all throughout the middle of the room. Items on the
# floor. Rugs clipped into walls", and of keeps: "it's rarely ever planned out like a believable castle". Three causes.
# The game's big-hall tile is most often a room of its own with a wall slab on every side (97 of its 289 tiles), and its
# set was laid on the open tiles in the middle of a made hall. Every piece drew its set from any room of any fort, a
# library's shelves beside a dining table. And what lost its table was set down on the floor, a ruin's way (_orphans).
# The game's forts: 2.1% of 2,480 hangings with no wall behind them, 2.1% of 238 rugs off their floor, 12.7% of 16,410
# loose things on the floor; 24 made halls before: 19%, and a third of the loose things on the floor)
HANGING = re.compile(r'tapestry|_c_t_|banner')
RUG = re.compile(r'rug|carpet')
SEAT = re.compile(r'chair|stool|bench')
HALL_EDGE = 112.0              # (furniture this near a hall tile's side stood against the wall there)
HANG_EDGE = 72.0               # (a hanging this near it hung on that wall)
HANG_REACH = 30.0              # (a wall face this far behind a hanging's cloth at most, _keep_tidy)
STAIR_FITTING = re.compile(r'torch_ring|sconce')
ON_RUG_NOT = re.compile(r'crate|barrel|sack|keg|basket')
RUIN_THINGS = re.compile(r'furn_bone|skeleton|skull|furn_web|_web_|spiderweb')
THEME_RX = (('bed', re.compile(r'_bed|bunk|bedroll|hammock')), ('shrine', re.compile(r'altar|shrine|_pew|kneel')),
            ('cook', re.compile(r'kettle|cauldron|cooking|_oven|spit_|ladle|fireplace|hearth|pot_0')),
            ('shelf', re.compile(r'bookshelf|bookcase')), ('arms', re.compile(r'weaponrack|weapon_rack|armou?r_?stand|mannequin|shieldrack')),
            ('table', re.compile(r'table|_bar_|counter')), ('store', re.compile(r'crate|barrel|sack|keg')))
# (what each of a keep's interiors holds, keepmaker.ROLES; 'plain' sets, lights and hangings and the odd chest, go anywhere)
ROLE_THEMES = {'hall': ('dining',), 'chambers': ('beds', 'books', 'dining'), 'household': ('dining', 'stores', 'beds'), 'library': ('books',),
               'chapel': ('shrine',), 'garrison': ('beds', 'arms', 'dining'), 'prison': ('stores',), 'treasury': ('stores', 'arms'),
               'undercroft': ('stores',), 'tower': ('arms', 'stores', 'beds'), 'walls': ('arms', 'stores')}
_THEME = {}
# (the rooms of each of a keep's interiors, the brief of 2026-11-12: one purpose a room, the public ones nearest the
# door and lowest, the private ones farthest and highest; in order from the door, the last repeating. A guide, as the
# user had it, not a rule to the letter)
# (an interior of one room is that role's own room: the barracks' a barracks, the chambers' a chamber; most rooms of
     # a first round were guard rooms, first in every list, lab kr_after)
ROOM_PLAN = {'hall': ('kitchen', 'guard room', 'stores', 'servants'),
             'chambers': ('chamber', 'study', 'audience', 'chamber'),
             'household': ('kitchen', 'servants', 'stores', 'dining'),
             'garrison': ('barracks', 'armoury', 'guard room', 'mess', 'barracks'),
             'tower': ('guard room', 'armoury', 'stores', 'watch room'),
             'walls': ('guard room', 'armoury', 'stores'),
             'library': ('study',), 'chapel': ('vestry',), 'treasury': ('treasury',), 'undercroft': ('stores',),
             'prison': ('cells', 'guard room', 'stores')}
# (and what furnishes each: the themes of the game's own sets, the first that the piece has any of)
PURPOSE_THEMES = {'guard room': ('arms', 'dining'), 'kitchen': ('kitchen', 'dining', 'stores'), 'stores': ('stores',), 'servants': ('beds',),
                  'audience': ('dining',), 'chamber': ('beds',), 'study': ('books',), "lord's chamber": ('beds', 'books'), 'dining': ('dining',),
                  'barracks': ('beds',), 'armoury': ('arms',), 'mess': ('dining',), 'watch room': ('arms', 'beds'), 'vestry': ('books', 'stores'),
                  'treasury': ('stores', 'arms'), 'cells': ('stores',)}


def _set_theme(st):
    """What kind of room a dressing set furnishes: 'beds', 'shrine', 'books', 'arms', 'dining', 'stores', or 'plain'."""
    k = id(st)
    if k not in _THEME:
        c = Counter()
        for row in _set_items(st):
            low = row[0].lower()
            if row[1] == 'BOOK':
                c['book'] += 1
            for nm, rx in THEME_RX:
                if rx.search(low):
                    c[nm] += 1
        _THEME[k] = ('beds' if c['bed'] else 'shrine' if c['shrine'] else 'kitchen' if c['cook'] and (c['table'] or c['store']) else
                     'books' if (c['shelf'] and c['book'] >= 4) or c['book'] >= 8
                     else 'arms' if c['arms'] else 'dining' if c['table'] else 'stores' if c['store'] >= 3 else 'plain')
    return _THEME[k]


def _hall_walls(lay, K):
    """{piece number of a big hall's tile: {side in the tile's own frame: 'open' (the hall goes on), 'door' (a doorway
    slab) or 'wall'}}."""
    B = K.get('big')
    if not B:
        return {}
    T = B['pitch']
    tiles = [(n, p) for n, p in enumerate(lay['pieces']) if not p.get('gone') and p.get('id') == B['tile']]
    blends = [p for p in lay['pieces'] if not p.get('gone') and p.get('id') == B['blend']]
    out = {}
    for n, p in tiles:
        x, y, z, rz = p['p'][0], p['p'][1], p['p'][2], p['p'][5]
        d = {}
        for s_, (sx, sy) in SIDES.items():
            wx, wy = _rot(sx, sy, rz)
            if any(abs(q['p'][0] - (x + wx * T)) < 40 and abs(q['p'][1] - (y + wy * T)) < 40 and abs(q['p'][2] - z) < 40 for _n, q in tiles):
                d[s_] = 'open'
            elif any(math.hypot(b['p'][0] - (x + wx * T / 2), b['p'][1] - (y + wy * T / 2)) < 200 for b in blends):
                d[s_] = 'door'
            else:
                d[s_] = 'wall'
        out[n] = d
    return out


def _side_of(lx, ly, T):
    """(the side of a tile a spot lies nearest, how far from that side)"""
    s_ = max(SIDES, key=lambda k: lx * SIDES[k][0] + ly * SIDES[k][1])
    return s_, T / 2.0 - (lx * SIDES[s_][0] + ly * SIDES[s_][1])


def _to_walls(db, items, walls, T, rng):
    """A hall tile's set turned to the tile's own walls and thinned to what they carry: the quarter turn that keeps the
    most of what stood against a wall in the game, then every hanging and piece of furniture that would stand against an
    open side or a doorway left out, with what stood on it and a table's seats. (the rows, turned; how many left out)"""
    def bound(row):
        b = mapdata.object_bounds(db, db.resolve_id(row[0]))
        return b if b and row[1] in ('STAT', 'ACTI', 'CONT') else None
    info = []
    for row in items:
        low, b = row[0].lower(), bound(row)
        hang = bool(b) and bool(HANGING.search(low))
        rug = bool(b) and bool(RUG.search(low)) and (b[5] - b[2]) * row[8] < 24
        furn = bool(b) and not hang and not rug and max(b[3] - b[0], b[4] - b[1]) * row[8] >= 50 and (b[5] - b[2]) * row[8] >= 24
        info.append((hang, rug, furn, b))

    def lost(q):
        out = set()
        for i, row in enumerate(items):
            hang, rug, furn, b = info[i]
            if not (hang or furn):
                continue
            lx, ly = _rot(row[2], row[3], q * math.pi / 2.0)
            s_, e = _side_of(lx, ly, T)
            if hang and (e > HANG_EDGE or walls.get(s_) != 'wall'):
                out.add(i)                        # (hung on something the set does not bring, or on a wall not here)
            elif furn and e <= HALL_EDGE and walls.get(s_) != 'wall':
                out.add(i)
        return out
    turns = [(len(lost(q)), rng.random(), q) for q in range(4)]
    q = min(turns)[2]
    gone = lost(q)
    # (and what stood on a piece that goes, and the seats round a table that goes)
    for i in sorted(gone):
        hang, rug, furn, b = info[i]
        if not furn:
            continue
        f = items[i]
        for j, row in enumerate(items):
            if j in gone or j == i:
                continue
            lx, ly = _rot(row[2] - f[2], row[3] - f[3], -f[7])
            on = b[0] * f[8] - 10 <= lx <= b[3] * f[8] + 10 and b[1] * f[8] - 10 <= ly <= b[4] * f[8] + 10 \
                and f[4] + b[2] * f[8] - 8 <= row[4] <= f[4] + b[5] * f[8] + 48
            if on and not info[j][2]:
                gone.add(j)
            elif TABLES.search(f[0].lower()) and SEAT.search(row[0].lower()) and math.hypot(row[2] - f[2], row[3] - f[3]) <= 130:
                gone.add(j)
    out = []
    for i, row in enumerate(items):
        if i in gone:
            continue
        lx, ly = _rot(row[2], row[3], q * math.pi / 2.0)
        out.append([row[0], row[1], lx, ly, row[4], row[5], row[6], (row[7] + q * math.pi / 2.0) % (2 * math.pi), row[8]])
    return out, len(gone)


def _keep_tidy(db, key, K):
    """Hangings with no wall face behind their cloth and rugs not wholly on a floor go (K['tidy']): whatever brought them,
    a set from a piece whose wall stood elsewhere, a neighbour's partition, the room above. The game's forts: 2.1% of
    each. The number taken out."""
    import seethrough
    c = db.project.cells.get(key)
    if not c:
        return 0
    m = mapdata.cellmap(db, key)
    refs = [r for r in m['refs'] if r.get('b') and r.get('ri') is not None]
    soft = lambda r: r['type'] in ('STAT', 'ACTI') and (HANGING.search(r['id'].lower()) or (RUG.search(r['id'].lower()) and (r['b'][5] - r['b'][2]) * (r.get('s') or 1.0) < 24))
    arch = [r for r in refs if r.get('arch') and not soft(r)]
    if not arch:
        return 0
    sc = seethrough.place_scene(db, dict(m, refs=arch))
    big = [r for r in refs if not r.get('arch') and not soft(r) and r['type'] in ('STAT', 'ACTI', 'CONT')
           and max(r['b'][3] - r['b'][0], r['b'][4] - r['b'][1]) * (r.get('s') or 1.0) >= 100]
    sc_f = seethrough.place_scene(db, dict(m, refs=[dict(r, arch=True) for r in big]))
    gone = []
    for r in refs:
        if not soft(r):
            continue
        b, s = r['b'], r.get('s') or 1.0
        ex, ey, ez = (b[3] - b[0]) * s, (b[4] - b[1]) * s, (b[5] - b[2]) * s
        base = r['p'][2] + b[2] * s
        if HANGING.search(r['id'].lower()):
            ux, uy = _rot(1.0, 0.0, r['p'][5]) if ex < ey else _rot(0.0, 1.0, r['p'][5])
            mx, my = _rot((b[0] + b[3]) / 2 * s, (b[1] + b[4]) / 2 * s, r['p'][5])
            best = None
            for f in (0.3, 0.5, 0.75):
                for sg in (1.0, -1.0):
                    for sc_ in (sc, sc_f):
                        h = sc_.nearest_any((r['p'][0] + mx, r['p'][1] + my, base + ez * f), (ux * sg, uy * sg, 0.0), 300)
                        if h is not None and (best is None or h[0] < best):
                            best = h[0]
            if best is None or best > min(ex, ey) / 2 + HANG_REACH:
                gone.append(r)
        elif abs(r['p'][3]) + abs(r['p'][4]) < 0.2:
            bad = 0
            for i in range(5):
                for j in range(5):
                    lx, ly = _rot((b[0] + (b[3] - b[0]) * (0.04 + 0.92 * i / 4.0)) * s, (b[1] + (b[4] - b[1]) * (0.04 + 0.92 * j / 4.0)) * s, r['p'][5])
                    h = sc.nearest_any((r['p'][0] + lx, r['p'][1] + ly, base + ez + 60), (0.0, 0.0, -1.0), 110)
                    if h is None or h[0] < 50:
                        bad += 1
            if bad >= 3:
                gone.append(r)
    # (and no crate, barrel or sack on a rug: one piece's rug ran under the next piece's stores, two barrels on a
    # room's octagonal rug in Fort Urasek's remade hall. The game's forts: 46 of 2,671; made keeps 5 to 8%)
    out_k = {r['k'] for r in gone}
    rugs_ = [r for r in refs if soft(r) and not HANGING.search(r['id'].lower()) and r['k'] not in out_k]
    for r in refs:
        if r['type'] not in ('CONT', 'STAT') or not ON_RUG_NOT.search(r['id'].lower()) or soft(r):
            continue
        base = r['p'][2] + r['b'][2] * (r.get('s') or 1.0)
        for g in rugs_:
            gb, gs = g['b'], g.get('s') or 1.0
            lx, ly = _rot(r['p'][0] - g['p'][0], r['p'][1] - g['p'][1], -g['p'][5])
            if gb[0] * gs <= lx <= gb[3] * gs and gb[1] * gs <= ly <= gb[4] * gs and abs(base - g['p'][2]) < 30:
                gone.append(r)
                break
    for r in gone:
        c['refs'].pop(r['k'], None)
    if gone:
        db.sync_project()
    return len(gone)


# ---- a big hall laid out as one room
# (a hall tile dressed to its walls keeps the rules but stands near empty: what the game puts in that tile stands against
# walls a wide hall has only at its rim, and six made halls held 12 pieces of furniture each. So a hall of two tiles and
# more is planned whole, the Workshop's own layout from the pieces the game's halls are furnished with (read off the
# survey's sets: which tables, benches, hangings, lights; how a hanging stands to its wall, how high a chandelier
# hangs): tables in rows down the hall with a way between them from the door, a high table across the far end, a
# hanging on each wall slab, lamps in the corners, chandeliers overhead; a library's shelves round its walls with
# reading tables between, a chapel's benches facing its altar)
HALL_FEAST = (None, 'hall', 'chambers', 'household', 'garrison')
HALL_AISLE = 190.0             # (from the way down the hall to the middle of the first row of tables either side)
HALL_LANE = 100.0              # (a bay's two rows of tables: this far either side of its middle)
HALL_WALL = 21.0               # (a wall slab's face: this far in from its tile's side)
HALL_POST = 81.0               # (the corner post of a hall tile: this far in from its tile's sides)
HALL_RIM = 70.0                # (nothing on the floor nearer a wall's side of its tile than this)
HALL_PILLAR = 92.0             # (half the pillar that stands where four hall tiles meet, with room to pass)
ALTARS = ('furn_imp_altar_cure_01', 'furn_imp_altar_01', 'active_imp_altar_01')
_PARTS = {}


def _hall_class(low, t, ex, ey, ez):
    if HANGING.search(low):
        return 'hanging'
    if RUG.search(low):
        return 'rug' if ez < 24 and max(ex, ey) >= 200 else None
    if t == 'LIGH' or low.startswith('light_'):
        return 'chandelier' if 'chandel' in low else 'sconce' if 'sconce' in low else 'lamp' if re.search(r'lamp|candelab|brazier', low) and ez >= 90 else None
    if 'coatofarms' in low:
        return 'arms'
    if 'chest' in low:
        return 'chest' if ez >= 25 and max(ex, ey) >= 60 else None
    if re.search(r'barrel|keg', low):
        return 'barrel'
    if re.search(r'sack|basket', low):
        return 'sack'
    if 'bookshelf' in low or 'bookcase' in low:
        return 'bookshelf' if ez >= 150 else None
    if 'table' in low:
        return 'long table' if max(ex, ey) >= 150 and min(ex, ey) <= 110 else 'table' if max(ex, ey) <= 140 and min(ex, ey) >= 50 else None
    if 'bench' in low:
        return 'bench' if max(ex, ey) >= 100 else None
    if 'chair' in low:
        return 'chair' if ez >= 60 else None
    if 'planter' in low:
        return 'planter'
    return None


def _hall_parts(db, S, K):
    """What the game's own fort halls are furnished with, read off the survey's sets: {'ids': {class: [id, most used
    first]}, 'wall': {id: (quarter turns from facing into the room, how far in from its tile's side, height)}, 'hung':
    {id: (x, y, z in its tile)}, 'floor': the floor's height in a hall tile's frame}."""
    key = (id(S), K['kind'])
    if key in _PARTS:
        return _PARTS[key]
    B = K['big']
    T = float(B['pitch'])
    uniq = set(S.get('uniques') or [])
    n = defaultdict(Counter)
    wall, hung, rug_z, beside = defaultdict(list), defaultdict(list), [], defaultdict(list)
    for pid, sets in S['dress'].items():
        big = pid == B['tile']
        for st in sets:
            for row in _set_items(st):
                low, t = row[0].lower(), row[1]
                ri = db.resolve_id(row[0])
                if t not in ('STAT', 'ACTI', 'CONT', 'LIGH') or ri is None or low in uniq or abs(row[5]) + abs(row[6]) > 0.1:
                    continue
                b = mapdata.object_bounds(db, ri)
                if not b:
                    continue
                c = _hall_class(low, t, b[3] - b[0], b[4] - b[1], b[5] - b[2])
                if not c:
                    continue
                if abs(row[8] - 1.0) <= 0.05:
                    n[c][low] += 3 if big else 1
                if not big:
                    continue
                if c == 'rug':
                    rug_z.append(row[4] + b[2])
                s_, e = _side_of(row[2], row[3], T)
                lat_ = abs(row[2] * SIDES[s_][1]) + abs(row[3] * SIDES[s_][0])
                if c in ('hanging', 'bookshelf') and 20.0 <= e <= HALL_EDGE and lat_ <= 150.0:
                    inward = math.atan2(-SIDES[s_][0], -SIDES[s_][1])
                    wall[low].append((int(round(math.degrees(inward - row[7]) / 90.0)) % 4, e, row[4]))
                if c in ('arms', 'sconce') and 8.0 <= e <= HALL_EDGE and lat_ <= 175.0:
                    inward = math.atan2(-SIDES[s_][0], -SIDES[s_][1])
                    beside[low].append((int(round(math.degrees(inward - row[7]) / 90.0)) % 4, e, row[4], lat_))
                if c == 'chandelier':
                    hung[low].append((row[2], row[3], row[4]))
    med = lambda v: sorted(v)[len(v) // 2]
    out = {'ids': {c: [i for i, _n in cn.most_common()] for c, cn in n.items()},
           'wall': {i: (Counter(w[0] for w in ws).most_common(1)[0][0], med([w[1] for w in ws]), med([w[2] for w in ws])) for i, ws in wall.items()},
           'hung': {i: (med([h[0] for h in hs]), med([h[1] for h in hs]), med([h[2] for h in hs])) for i, hs in hung.items()},
           # (what hangs beside a hanging on a wall slab, a coat of arms, a sconce: its turn, how far in, how high, how far along)
           'beside': {i: (Counter(w[0] for w in ws).most_common(1)[0][0], med([w[1] for w in ws]), med([w[2] for w in ws]), med([w[3] for w in ws]))
                      for i, ws in beside.items() if len(ws) >= 3},
           'floor': med(rug_z) if rug_z else -T / 2.0}
    _PARTS[key] = out
    return out


def _hall_compose(db, S, K, lay, hall_no, walls, rng, role):
    """A big hall's furnishing, laid out as one room for what the interior is (role: a keep's Great Hall and the like a
    feast hall, its library, its chapel): [(id, pose, [], scale)] in the place's frame, or None for a hall this does
    not plan (one tile, not a rectangle, another role: its tiles are dressed one by one, to their walls)."""
    B = K['big']
    T = float(B['pitch'])
    tiles = [(n, p) for n, p in enumerate(lay['pieces']) if not p.get('gone') and p.get('id') == B['tile'] and p.get('hall') == hall_no]
    if len(tiles) < 2 or not (role in HALL_FEAST or role in ('library', 'chapel')):
        return None
    e = tiles[0][1].get('of')
    if e is None or lay['pieces'][e].get('gone'):
        return None
    ep = lay['pieces'][e]['p']
    trz, tz = tiles[0][1]['p'][5], tiles[0][1]['p'][2]
    ux, uy = _rot(1.0, 0.0, trz)                      # (down the hall from its doorway: the tile's own east)
    vx, vy = _rot(0.0, 1.0, trz)
    t0 = min(tiles, key=lambda q: math.hypot(q[1]['p'][0] - ep[0], q[1]['p'][1] - ep[1]))[1]['p']
    ij = {}
    for n, p in tiles:
        dx, dy = p['p'][0] - t0[0], p['p'][1] - t0[1]
        ij[(int(round((dx * ux + dy * uy) / T)), int(round((dx * vx + dy * vy) / T)))] = n
    i0, i1 = min(k[0] for k in ij), max(k[0] for k in ij)
    j0, j1 = min(k[1] for k in ij), max(k[1] for k in ij)
    w, h = i1 - i0 + 1, j1 - j0 + 1
    if len(ij) != w * h or i0 != 0 or any(n not in walls for n in ij.values()):
        return None
    P = _hall_parts(db, S, K)
    ids = P['ids']
    L, Wd = w * T, h * T
    floor = tz + P['floor']
    Ve = (0 - j0 + 0.5) * T                           # (the way in: across the hall, where its doorway stands)
    head = lambda du, dv: math.atan2(du * ux + dv * vx, du * uy + dv * vy)     # (the turn whose own +y points that way in the hall)
    box = {}

    def dims(rid):
        if rid not in box:
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            box[rid] = b
        return box[rid]
    pick = lambda c, k=1: [i for i in ids.get(c, []) if dims(i)][:k]
    out, taken, ways = [], [], []
    # (kept clear: the way in from every doorway, and the way down the hall from the front one)
    for (i, j), n in ij.items():
        for s_, st in walls[n].items():
            if st != 'door':
                continue
            sx, sy = SIDES[s_]
            cu, cv = (i + 0.5) * T + sx * T / 2, (j - j0 + 0.5) * T + sy * T / 2
            du, dv = -sx * DOORWAY_DEEP, -sy * DOORWAY_DEEP
            hw = DOORWAY_WIDE / 2
            ways.append((min(cu, cu + du) - (hw if sy else 0), min(cv, cv + dv) - (hw if sx else 0), max(cu, cu + du) + (hw if sy else 0), max(cv, cv + dv) + (hw if sx else 0)))
    aisle = (0.0, Ve - 95.0, L, Ve + 95.0)
    # (a pillar stands where four tiles meet, and part of one at the rim: nothing through it)
    for i in range(0, w + 1):
        for j in range(0, h + 1):
            ways.append((i * T - HALL_PILLAR, j * T - HALL_PILLAR, i * T + HALL_PILLAR, j * T + HALL_PILLAR))

    def free(u, v, hu, hv, rug=False, aisle_ok=False, rim=HALL_RIM):
        if not (rim + hu <= u <= L - rim - hu and rim + hv <= v <= Wd - rim - hv):
            return False
        r = (u - hu, v - hv, u + hu, v + hv)
        hit = lambda q: r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3]
        if rug:
            return not any(hit(q) for q in taken if q[4])
        return not any(hit(q) for q in ways) and (aisle_ok or not hit(aisle)) and not any(hit(q) for q in taken if not q[4])

    def put(rid, u, v, rz, z=None, hu=0.0, hv=0.0, rug=False):
        b = dims(rid)
        a, c = u - T / 2, v - T / 2 + j0 * T
        out.append((rid, (t0[0] + a * ux + c * vx, t0[1] + a * uy + c * vy, floor - b[2] if z is None else z, 0.0, 0.0, rz % (2 * math.pi)), [], 1.0))
        if hu or hv:
            taken.append((u - hu, v - hv, u + hu, v + hv, rug))

    def along(rid, du, dv):
        """(the turn that lays a piece's long side along that way in the hall; its half length and half width)"""
        b = dims(rid)
        ex, ey = b[3] - b[0], b[4] - b[1]
        if ex >= ey:
            return math.atan2(-(du * uy + dv * vy), du * ux + dv * vx), ex / 2.0, ey / 2.0
        return head(du, dv), ey / 2.0, ex / 2.0
    lt, bn, ch, tb = (pick('long table') or [None])[0], (pick('bench') or [None])[0], (pick('chair') or [None])[0], (pick('table') or [None])[0]
    rugs = pick('rug', 4)
    lamp = (pick('lamp') or [None])[0]

    def table_row(u, v, du, dv, seats='both'):
        """(a long table at a spot, its length along (du, dv), benches along both sides or chairs along one)"""
        rz, hl, hw = along(lt, du, dv)
        reach = hw + 46.0                         # (the table with its seats)
        hu, hv = (hl, reach) if du else (reach, hl)
        if not free(u, v, hu, hv, rim=HALL_WALL + 14):
            return False
        put(lt, u, v, rz, hu=hu, hv=hv)
        if seats == 'both' and bn:
            brz, _bl, bw = along(bn, du, dv)
            for sg in (1, -1):
                off = (hw + 10 + bw) * sg
                put(bn, u + (0 if du else off), v + (off if du else 0), brz)
        elif ch:
            # (chairs along the far side, facing back down the hall: their front is their own -y, as the game's stand
            # to their tables)
            cb = dims(ch)
            for k in (-1, 1) if hl >= 80 else (0,):
                off = hw + 12 + (cb[4] - cb[1]) / 2.0
                cu, cv = (u + off, v + k * hl * 0.5) if not du else (u + k * hl * 0.5, v + off)
                fu, fv = (-1.0, 0.0) if not du else (0.0, -1.0)
                put(ch, cu, cv, head(-fu, -fv))
        return True
    if role in HALL_FEAST and lt:
        # the high table across the far end: one in each bay there, chairs behind it facing down the hall (none where
        # a way out stands)
        n_high = 0
        for jj in sorted(range(h), key=lambda q: abs((q + 0.5) * T - Ve)):
            vc = (jj + 0.5) * T
            if table_row(L - 235.0, vc, 0, 1, seats='far'):
                n_high += 1
                if rugs and n_high == 1 and free(L - 235.0, vc, 80, 80, rug=True):
                    rr, rl, rw = along(rugs[0], 0, 1)
                    put(rugs[0], L - 235.0, vc, rr, hu=rw, hv=rl, rug=True)
        # rows of tables down the hall: two rows in every bay but the one the way from the door runs down
        hl = along(lt, 1, 0)[1]
        end = L - (470.0 if n_high else 170.0)
        for jj in range(h):
            vc = (jj + 0.5) * T
            for off in ((-HALL_LANE, HALL_LANE) if abs(vc - Ve) > 1.0 else (-HALL_AISLE, HALL_AISLE)):
                u = 150.0 + hl
                while u + hl <= end:
                    if table_row(u, vc + off, 1, 0):
                        if rugs and abs(vc - Ve) > 1.0 and free(u, vc, 60, 60, rug=True):
                            rr, rl, rw = along(rugs[1 % len(rugs)], 1, 0)
                            if rl <= T / 2.0 - HALL_POST and u - rl >= HALL_RIM and u + rl <= L - HALL_RIM:
                                put(rugs[1 % len(rugs)], u, vc, rr, hu=rl, hv=rw, rug=True)
                        u += 2 * hl + 64.0
                    else:
                        u += 32.0
    elif role == 'library':
        # reading tables down the middle, a chair either side
        t_ = tb or lt
        for (i, j), n in sorted(ij.items()):
            u, v = (i + 0.5) * T, (j - j0 + 0.5) * T
            if t_ and free(u, v, 110, 110):
                rz, hl, hw = along(t_, 1, 0)
                put(t_, u, v, rz, hu=hl + 10, hv=hw + 70)
                if ch:
                    cb = dims(ch)
                    for sg in (1, -1):
                        put(ch, u, v + sg * (hw + 14 + (cb[4] - cb[1]) / 2.0), head(0.0, float(sg)))
                if rugs and free(u, v, 60, 60, rug=True):
                    rr, rl, rw = along(rugs[len(out) % len(rugs)], 1, 0)
                    put(rugs[len(out) % len(rugs)], u, v, rr, hu=rl, hv=rw, rug=True)
    elif role == 'chapel':
        altar = next((a for a in ALTARS if db.resolve_id(a) is not None and dims(a)), None) or tb or lt
        if altar and free(L - 210.0, Ve, 60, 60, aisle_ok=True):
            put(altar, L - 210.0, Ve, along(altar, 0, 1)[0], hu=70, hv=110)
        if bn:
            brz, bl, bw = along(bn, 0, 1)
            u = 260.0
            while u <= L - 470.0:
                for sg in (1, -1):
                    for k in range(0, 4):
                        v = Ve + sg * (105.0 + bl + k * (2 * bl + 24))
                        if free(u, v, bw + 30, bl):
                            put(bn, u, v, brz, hu=bw + 30, hv=bl)
                u += 150.0
    # a rug on the way down the hall, by the door and half way
    for u in (300.0, L / 2.0):
        if rugs and free(u, Ve, 100, 60, rug=True):
            rid = rugs[-1] if len(rugs) > 1 else rugs[0]
            rr, rl, rw = along(rid, 1, 0)
            if u - rl >= HALL_RIM and u + rl <= L - HALL_RIM and Ve - rw >= 20 and Ve + rw <= Wd - 20:
                put(rid, u, Ve, rr, hu=rl, hv=rw, rug=True)
    # the walls: a hanging on each slab (a library: shelves either side of its middle, a hanging on every third)
    # (only the hangings the game hangs flat on a hall's wall slab, their pose read off it: one laid by a guessed pose,
    # or by one the game turns another way, stood off its wall and was taken out again, half of a hall's, lab kc_after3)
    posed = [i for i in ids.get('hanging', []) if dims(i) and i in P['wall'] and P['wall'][i][0] == 0]
    hang_ids = [i for i in posed if role != 'chapel' or '_c_t_' in i][:3] or posed[:3]
    shelf = next((i for i in ids.get('bookshelf', []) if dims(i) and i in P['wall']), None)
    slot = 0
    for (i, j), n in sorted(ij.items()):
        for s_ in ('W', 'N', 'E', 'S'):
            if walls[n].get(s_) != 'wall':
                continue
            sx, sy = SIDES[s_]
            cu, cv = (i + 0.5) * T + sx * T / 2, (j - j0 + 0.5) * T + sy * T / 2
            slot += 1
            if role == 'library' and shelf and slot % 3:
                q, e_, z_ = P['wall'][shelf]
                b = dims(shelf)
                half = max(b[3] - b[0], b[4] - b[1]) / 2.0 + 6
                for sg in (1, -1):
                    put(shelf, cu - sx * e_ + (0 if sx else sg * half), cv - sy * e_ + (sg * half if sx else 0), head(-sx, -sy) - q * math.pi / 2.0, z=tz + z_)
                continue
            if not hang_ids:
                continue
            hid = hang_ids[slot % len(hang_ids)]
            b = dims(hid)
            q, e_, z_ = P['wall'].get(hid) or (0, 60.0, P['floor'] + 100.0 - b[2])
            put(hid, cu - sx * e_, cv - sy * e_, head(-sx, -sy) - q * math.pi / 2.0, z=tz + z_)
            # (beside it as the game hangs them: a coat of arms either side, a sconce; the game's halls hold 1.3 hangings
            # and 2.7 lights a tile, the planned hall held 0.4 and 1.1 and 8.6 things a tile to the game's 23)
            au, av = (0.0, 1.0) if sx else (1.0, 0.0)          # (along the wall)
            # (arms on every third slab: either side of every hanging made 2.3 a tile, the game's halls hold 0.2)
            for cls_, sides_ in (('arms', (1, -1) if slot % 3 == 0 else ()), ('sconce', (1 if slot % 2 else -1,))):
                xid = next((i for i in ids.get(cls_, []) if i in P['beside'] and dims(i)), None)
                if not xid:
                    continue
                q2, e2, z2, lat2 = P['beside'][xid]
                lat2 = max(lat2, (b[3] - b[0]) / 2.0 + 30.0) + (40.0 if cls_ == 'sconce' else 0.0)
                for sg in sides_:
                    put(xid, cu - sx * e2 + au * lat2 * sg, cv - sy * e2 + av * lat2 * sg, head(-sx, -sy) - q2 * math.pi / 2.0, z=tz + z2)
            if role in HALL_FEAST and bn and slot % 2 == 0:
                # (a bench along the wall under every other hanging, for those who wait on the tables)
                brz, bl, bw = along(bn, 0 if sx else 1, 1 if sx else 0)
                bu, bv = cu - sx * (HALL_WALL + 12 + bw), cv - sy * (HALL_WALL + 12 + bw)
                if free(bu, bv, bw if sx else bl, bl if sx else bw, rim=HALL_WALL):
                    put(bn, bu, bv, brz, hu=bw if sx else bl, hv=bl if sx else bw)
            elif role in HALL_FEAST or role == 'chapel':
                # (and under the others what the game keeps along a hall's walls: a chest, or barrels, or sacks and baskets)
                kinds_ = [k_ for k_ in ('chest', 'barrel', 'sack') if pick(k_)]
                if kinds_:
                    k_ = kinds_[(slot // 2) % len(kinds_)]
                    sid = pick(k_, 3)[slot % len(pick(k_, 3))]
                    srz, sl, sw = along(sid, au, av)
                    for sg in ((0,) if k_ == 'chest' else (-1, 1)):
                        off = sg * (sl + 8.0)
                        su, sv = cu - sx * (HALL_WALL + 14 + sw) + au * off, cv - sy * (HALL_WALL + 14 + sw) + av * off
                        if free(su, sv, sw if sx else sl, sl if sx else sw, rim=HALL_WALL):
                            put(sid, su, sv, srz + (0.0 if k_ == 'chest' else rng.uniform(-0.5, 0.5)), hu=sw if sx else sl, hv=sl if sx else sw)
    # light: a standing lamp at each pillar along the way down the hall, on the side the way passes; a chandelier over
    # every other tile
    if lamp:
        for jl in range(1, h):
            vl = jl * T
            if abs(vl - Ve) > T / 2.0 + 1.0:
                continue
            sg = 1.0 if Ve > vl else -1.0
            for il in range(1, w):
                put(lamp, il * T, vl + sg * (HALL_POST + 26.0), 0.0)
    chand = next((i for i in ids.get('chandelier', []) if i in P['hung'] and dims(i)), None)
    if chand:
        hx, hy, hz = P['hung'][chand]
        for (i, j), n in sorted(ij.items()):
            if (i + j - j0) % 2 == 0 or len(ij) <= 2:
                put(chand, (i + 0.5) * T + hx, (j - j0 + 0.5) * T + hy, 0.0, z=tz + hz)
    return out


def _dress_refs(db, S, lay, rng, loot='usual', creatures='usual', K=None):
    """What stands in each piece: a whole set copied from a real piece of the same kind in the game's places
    (or none, as often as the game leaves that kind bare), turned and moved to this piece. Kwama egg sacs and
    veins only in an egg mine (lay['mine'])."""
    K = K or kit('dwemer')
    mine = bool(lay.get('mine'))
    out = []
    uniq = set(S.get('uniques') or [])
    # (as a share of the game's own: under 1 some of each are left out; over 1 empty barrels and crates come
    # full, tables are laid fuller and more of the kind's creatures roam; the sets themselves stay the game's)
    loot_x, crea_x = amount('loot', loot), amount('creatures', creatures)
    keep_loot, keep_crea = min(1.0, loot_x), min(1.0, crea_x)
    rich_rng = random.Random(rng.random())
    is_loot = lambda t: t not in ('CREA', 'LEVC', 'LIGH', 'STAT', 'ACTI')
    more = K.get('more')
    n_crea = 0
    # (the way in from each doorway of a big hall, K['big']: from the doorway slab DOORWAY_DEEP into the hall,
    # DOORWAY_WIDE across: a hall tile's set, copied from a game tile with a wall on that side, stood a bookshelf at
    # the foot of the Great Hall's entrance steps with its back to the door; only what lies flat stays there)
    ways_in = []
    blend_ = (K.get('big') or {}).get('blend')
    for p in lay['pieces'] if blend_ else ():
        if p.get('gone') or p.get('id') != blend_:
            continue
        for _px, _py, _pz, ps in S['ports'].get(blend_) or ():
            dx_, dy_ = _rot(*SIDES[ps], p['p'][5])
            ways_in.append((p['p'][0], p['p'][1], -dx_, -dy_))
            break

    def in_way(rid, wx, wy, t=None):
        if not ways_in:
            return False
        b_ = mapdata.object_bounds(db, db.resolve_id(rid))
        if t == 'STAT' and b_ and b_[5] - b_[2] < 24:
            return False                         # (a rug; the books and plates of a shelf that goes, go with it)
        for ox_, oy_, ux_, uy_ in ways_in:
            t_ = (wx - ox_) * ux_ + (wy - oy_) * uy_
            if -160.0 <= t_ <= DOORWAY_DEEP and abs(-(wx - ox_) * uy_ + (wy - oy_) * ux_) <= DOORWAY_WIDE / 2.0:
                return True
        return False
    themed = bool(K.get('themes'))
    role_themes = ROLE_THEMES.get(lay.get('role') or '') or ()
    hall_theme = {}
    hall_walls = _hall_walls(lay, K) if themed else {}
    big_tile, big_T = (K.get('big') or {}).get('tile'), (K.get('big') or {}).get('pitch', 512)
    # (a hall of two tiles and more: planned whole, _hall_compose; its tiles and slabs then take no sets of their own)
    composed = set()
    if themed and big_tile:
        hall_rng = random.Random(rng.random())
        for hk in sorted({p.get('hall') for p in lay['pieces'] if not p.get('gone') and p.get('id') == big_tile and p.get('hall') is not None}):
            try:
                rows_ = _hall_compose(db, S, K, lay, hk, hall_walls, hall_rng, lay.get('role'))
            except Exception as ex:
                rows_ = None
                print('hall layout:', ex)
            if rows_:
                out += rows_
                composed.add(hk)
    big_ids = set((K.get('big') or {}).get(k_) for k_ in ('tile', 'wall', 'blend'))
    spiral_piece = (K.get('spiral') or {}).get('piece')
    # (each room its purpose by where it lies, ROOM_PLAN: lowest and nearest the door first; the chambers' highest room
    # the lord's. Kept with the place, c['ruin']['rooms'])
    room_want, plan_rooms = {}, []
    if themed:
        groups_ = {}
        for p_ in lay['pieces']:
            if not p_.get('gone') and p_.get('hall') is not None and p_.get('box') and p_.get('id'):
                groups_.setdefault(p_['hall'], []).append(p_)
        box_ = lambda ps: [int(round(f(q['box'][k_] for q in ps))) for k_, f in ((0, min), (1, min), (2, min), (3, max), (4, max), (5, max))]
        prog_ = ROOM_PLAN.get(lay.get('role') or '')
        rest_ = sorted((hk for hk in groups_ if hk not in composed),
                       key=lambda hk: (round(min(q['p'][2] for q in groups_[hk]) / 128.0), min(q.get('depth', 0) for q in groups_[hk])))
        planned_ = (lay.get('planned') or {}).get('purposes') or {}
        for idx_, hk in enumerate(rest_ if prog_ or planned_ else ()):
            # (as planned, _grow_plan; a room the plan did not lay, by where it lies as before)
            pur_ = planned_.get(hk) or planned_.get(str(hk)) or (
                "lord's chamber" if lay.get('role') == 'chambers' and len(rest_) > 1 and idx_ == len(rest_) - 1 else (prog_ or ('stores',))[idx_ % len(prog_ or ('stores',))])
            room_want[hk] = PURPOSE_THEMES.get(pur_) or ()
            plan_rooms.append({'hall': hk, 'purpose': pur_, 'box': box_(groups_[hk]), 'pieces': len(groups_[hk])})
        for hk in sorted(composed):
            plan_rooms.append({'hall': hk, 'purpose': {'library': 'library', 'chapel': 'chapel'}.get(lay.get('role'), 'great hall'),
                               'box': box_(groups_[hk]), 'pieces': len(groups_[hk])})
        lay['rooms_plan'] = plan_rooms
    mh_rng = random.Random('%s|machines' % lay.get('seed'))
    machine_hall = K.get('halls') == 'dwemer' and lay.get('final') is not None and MACHINE_SHARE > 0 and mh_rng.random() < MACHINE_SHARE
    n_machines = 0
    lay['machines'] = 0 if machine_hall else None
    for n, p in enumerate(lay['pieces']):
        if p.get('gone') or not p.get('id'):
            continue
        if p.get('hall') in composed and p['id'] in big_ids:
            continue
        sets = S['dress'].get(p['id'])
        if not sets:
            continue
        # (a set from a game piece that used the same openings, else one that used them and more, else any:
        # a chamber's stairs, ramps and platforms are built for its exits)
        used_ = set(_ports_used(S, lay, n))
        same = [st for st in sets if isinstance(st, dict) and set(st['u']) == used_]
        more_ = [st for st in sets if isinstance(st, dict) and set(st['u']) >= used_]
        pool_ = same or more_ or sets
        # (the last room is the one you remember: where it is one piece of the game's (a cave's chamber, a tomb's
        # burial room), its dressing is one of the fullest third the game has for that piece, by what stands in it
        # (creatures apart). Every piece drawn that way once brought doubled platforms and statues with it; one room
        # of a place does not. The night of 2026-11-12, FINAL_FULL)
        if machine_hall and p.get('hall') == lay.get('final') and n_machines < MACHINE_MOST:
            mach_ = [st for st in sets if isinstance(st, dict) and any(MACHINE.search(str(row[0]).lower()) for row in _set_items(st))]
            if mach_ and mh_rng.random() < MACHINE_TILE:
                pool_ = mach_
                n_machines += 1
                lay['machines'] = n_machines
        if FINAL_FULL and p.get('hall') is not None and p.get('hall') == lay.get('final') and K.get('halls') == 'pieces' \
                and not K.get('final_room') and p.get('role') == 'room' and len(pool_) >= 6:
            ranked_ = sorted((st for st in pool_ if isinstance(st, dict)), key=lambda st: -sum(1 for row in _set_items(st) if row[1] not in ('CREA', 'LEVC')))
            if len(ranked_) >= 6:
                pool_ = ranked_[:max(2, len(ranked_) // 3)]
        # (a kind's piece furnished on a storey of its own, K['furnished']: {piece regex: (lowest, highest over the
        # piece's origin, things at least)}: a Velothi tower's lower room from the dressings that furnish it. The game's
        # pits hold a median 47 things down there, but some of its dressings leave it bare, and a made tower's lower
        # room came out empty, the user's Shishkebab)
        for pat, (z0_, z1_, least) in (K.get('furnished') or {}).items():
            if re.search(pat, p['id']):
                fixed_ = re.compile(K['fixed']) if K.get('fixed') else None
                things = lambda st: sum(1 for row in _set_items(st) if z0_ <= row[4] <= z1_ and not (fixed_ and fixed_.search(row[0].lower())))
                full = [st for st in pool_ if things(st) >= least]
                pool_ = full or pool_
        # (one draw, whatever the loot: the most-loot of several draws brought the fullest sets, statues,
        # platforms and machines with them, and a doubled shrine platform in the user's Zajamima. "It should just
        # make more valuable loot and better loot in chests": richer fills what's there, below)
        if themed:
            # (a room's pieces all of one theme, the interior's own (ROLE_THEMES) when it has a role, else the first
            # furnished set's; a corridor's from any of the role's; plain sets anywhere)
            hk = p.get('hall')
            want = (hall_theme.get(hk),) if hall_theme.get(hk) else role_themes
            if hk in room_want:
                # (a room with a purpose: a set of its purpose's first theme the piece has any of, now and then a plain
                # one; with neither, the piece stays bare rather than take what belongs to another kind of room)
                got_ = None
                for th_ in room_want[hk] + ('plain',):
                    for cand in (same, more_, sets):
                        fit = [st for st in cand if isinstance(st, dict) and _set_theme(st) == th_]
                        if fit:
                            got_ = fit
                            break
                    if got_:
                        break
                plain_ = [st for st in sets if isinstance(st, dict) and _set_theme(st) == 'plain']
                if got_ and plain_ and rng.random() < 0.25:
                    got_ = plain_
                if not got_:
                    continue
                pool_ = got_
            elif want:
                for cand in (same, more_, sets):
                    fit = [st for st in cand if isinstance(st, dict) and _set_theme(st) in want + ('plain',)]
                    if fit:
                        pool_ = fit
                        break
        if p['id'] == big_tile and n in hall_walls:
            # (a hall tile: of a few draws, the set that loses the least to this tile's open sides)
            best_ = None
            for st_ in [rng.choice(pool_) for _ in range(5)]:
                rows_, lost_ = _to_walls(db, _set_items(st_), hall_walls[n], big_T, rng)
                if best_ is None or lost_ < best_[0]:
                    best_ = (lost_, rows_, st_)
            chosen, st0 = best_[1], best_[2]
        else:
            st0 = rng.choice(pool_)
            chosen = _set_items(st0)
        if themed and p.get('hall') is not None and not hall_theme.get(p.get('hall')) and isinstance(st0, dict) and _set_theme(st0) != 'plain':
            hall_theme[p.get('hall')] = _set_theme(st0)
        x, y, z, rz = p['p'][0], p['p'][1], p['p'][2], p['p'][5]
        got = []
        bx = p.get('box')
        for rid, t, lx, ly, lz, rx, ry, drz, s in chosen:
            low = rid.lower()
            if low in uniq or db.resolve_id(rid) is None or MASONRY_FIRE.match(low):
                continue
            # (only what stands within the piece's own height: over its roof or under its floor it belonged to
            # whatever stood there in the game, a gallery or the room above. Two big rugs lay tilted on a tomb
            # junction's roof, the user's Vafrothi)
            # (not in caves: a cave piece's box runs far down into the rock and up round its formations)
            if bx and not K.get('kind', '').startswith('cave') and not (bx[2] - 24 <= z + lz <= bx[5] - 4):
                continue
            if not mine and t not in ('CREA', 'LEVC', 'INGR') and (EGG_MINE.search(low) or EGG_MINE.search((db.recs[db.resolve_id(rid)][5] or '').lower())):
                continue                         # (an egg mine's, not a cave's; kwama foragers still roam)
            # (a spiral stair's turns: only what lights them and what hangs on their wall. The game's sets for the
            # piece hold bones, stone blocks, crates and loose things, 210 of 273 not lights; the user: "items in the
            # middle of stairwells". The store under the lowest turn stays, as the game keeps one there)
            if themed and p['id'] == spiral_piece and not (t == 'LIGH' or HANGING.search(low) or STAIR_FITTING.search(low)):
                continue
            # (and in a keep with its household, no bones and no webs: an abandoned fort's)
            if themed and lay.get('role') and RUIN_THINGS.search(low):
                continue
            if t in ('CREA', 'LEVC') and rng.random() >= keep_crea:
                continue
            if is_loot(t) and rng.random() >= keep_loot:
                continue
            if low.endswith('_empty') and rng.random() < loot_x - 1.0 and db.resolve_id(rid[:-6]) is not None:
                rid = rid[:-6]                     # (a full barrel where the game had an empty one)
            # (its own dice: on the main ones, raising Loot changed which sets every piece drew)
            if loot_x > 1.0 and t in RICHER_TYPES and rich_rng.random() < min(0.7, (loot_x - 1.0) * 0.6):
                rid, lz = _richer(db, S, rid, t, lz, s, rich_rng)
            n_crea += t in ('CREA', 'LEVC')
            wx, wy = _rot(lx, ly, rz)
            if t not in ('CREA', 'LEVC') and in_way(rid, x + wx, y + wy, t):
                continue
            # (rubble and debris lying flat at the piece's own height share the floor's face and flicker: the
            # user's Daedric ruin, in_dae_rubble_01a at the foot of a stair. The game lays most of them so too,
            # 98 of its 186; lifted a hair here)
            # (most of the game's rubble lies turned over, rx a half turn: lifted whatever its turn)
            if t == 'STAT' and FLAT_ON_FLOOR.search(low):
                lz += FLAT_LIFT
            got.append((rid, (x + wx, y + wy, z + lz, rx, ry, (rz + drz) % (2 * math.pi)), [], s))
        # (fittings only beside what they are fitted to, after everything left out above)
        for acc_, base_, reach_ in K.get('fitted') or ():
            bases_ = [g for g in got if re.search(base_, g[0].lower())]
            got = [g for g in got if not re.search(acc_, g[0].lower()) or
                   any(math.hypot(g[1][0] - b_[1][0], g[1][1] - b_[1][1]) <= reach_ for b_ in bases_)]
        out += got
    # more creatures than the game's: the kind's own levelled list, as many more as asked for over the ones
    # the copied sets brought (twice the game's: as many again), at junctions and in halls first
    if crea_x > 1.0 and more and db.resolve_id(more):
        alive = [p for p in lay['pieces'] if not p.get('gone') and p.get('id')]
        wide = [p for p in alive if p['role'] in ('cross', 'T', 'hall', 'room')] or alive
        extra = int(round((crea_x - 1.0) * max(n_crea, len(alive) / 8.0)))
        for p in [rng.choice(wide) for _ in range(extra)] if wide else []:
            x, y, z = p['p'][0], p['p'][1], p['p'][2]
            out.append((more, (x, y, z - (100 if K['kind'] == 'dwemer' else 0), 0, 0, rng.random() * 6.28), [], 1.0))
    return out


DOORWAY_DEEP, DOORWAY_WIDE = 420.0, 300.0     # (the way in from a big hall's doorway kept clear, _dress_refs)
MASS_IN = 64.0                 # (a piece's middle this far inside the keep's outer blocks, _Layout.fits)
MASS_OVER, MASS_UNDER = 48.0, 300.0           # (its top this far over a block's usable top at most; its foot this far under the block's)
RICHER_TYPES = ('MISC', 'ALCH', 'INGR', 'APPA', 'BOOK', 'CONT')
RICHER_NOT = re.compile(r'^gold_|key|_uni|unique|_q_|quest|soulgem')
# (a chest for a chest, a crate for a crate: what kind of container it is, by its name)
CONT_FAMILY = re.compile(r'chest|crate|barrel|sack|urn|basket|keg|box|closet|cabinet|cupboard|drawers|desk')
_RICH_POOL = {}


def _worth(db, rid, t):
    """What a thing is worth: an item's value, or what a container holds (wealthsurvey)."""
    if t == 'CONT':
        import wealthsurvey
        return wealthsurvey.container_value(db, rid) or 0.0
    import shelfsurvey
    return shelfsurvey.value_of(db, rid)[1]


def _rich_pool(db, S):
    """The kind's own loose things, from every set its game places hold: (id, type, value, size, bottom)."""
    k = id(S)
    if k not in _RICH_POOL:
        import shelfsurvey
        seen, pool = set(), []
        for sets in (S.get('dress') or {}).values():
            for st in sets or []:
                for row in _set_items(st):
                    rid, t = row[0], row[1]
                    low = rid.lower()
                    if t not in RICHER_TYPES or low in seen or RICHER_NOT.search(low):
                        continue
                    seen.add(low)
                    ri = db.resolve_id(rid)
                    ob = mapdata.object_bounds(db, ri) if ri is not None else None
                    if not ob:
                        continue
                    val = _worth(db, rid, t)
                    fam = CONT_FAMILY.search(low) if t == 'CONT' else None
                    pool.append((rid, t, val, max(ob[3] - ob[0], ob[4] - ob[1], ob[5] - ob[2]), ob[2], fam.group(0) if fam else None))
        _RICH_POOL[k] = pool
    return _RICH_POOL[k]


def _richer(db, S, rid, t, lz, s, rng):
    """(id, height) of a pricier thing of the same kind and about the same size, from the kind's own sets, in
    place of rid, its bottom where rid's was: raised Loot leaves richer things on the shelves and tables ("loot
    setting should affect the kind of decoration and clutter in some capacity, what is left on shelves", the
    user); the same rid when there is none."""
    if RICHER_NOT.search(rid.lower()):
        return rid, lz
    ri = db.resolve_id(rid)
    ob = mapdata.object_bounds(db, ri) if ri is not None else None
    if not ob:
        return rid, lz
    val = _worth(db, rid, t)
    size = max(ob[3] - ob[0], ob[4] - ob[1], ob[5] - ob[2])
    fam = CONT_FAMILY.search(rid.lower()) if t == 'CONT' else None
    if t == 'CONT' and not fam:
        return rid, lz
    # (a step up, not a fortune: 1.5 to 4 times its worth; one swap made a tomb's clutter worth 54,000 gold.
    # A container holding nothing may become one holding up to 300; "better loot in chests", the user)
    top = max(val * 4, val + (300 if t == 'CONT' else 40))
    cand = [c for c in _rich_pool(db, S) if c[1] == t and max(val * 1.5, val + 5) < c[2] <= top
            and 0.7 * size <= c[3] <= 1.3 * size and (t != 'CONT' or c[5] == fam.group(0))]
    if not cand:
        return rid, lz
    c = rng.choice(cand)
    return c[0], lz + (ob[2] - c[4]) * (s or 1.0)


def preview(db, kind='dwemer', size='medium', levels='some', twist='branching', seed=None, entry=None, final=None, way='down'):
    """The layout a build with these choices would make, for the Dungeon tool's plan: each piece's box from
    above (x0, y0, x1, y1), its floor-ish height, what it is and its hall; the way in and the last hall.
    {'learning': [...]} while the kind is still being learnt."""
    S = ready(db, kind)
    if S is None:
        import learning
        return {'learning': learning.ruin_pending(db, kind)}
    seed = int(seed) if seed not in (None, '') else random.getrandbits(31)
    kind0, kind = kind, variant(db, kind, size, seed)
    if kind != kind0:
        S = ready(db, kind)
    lay = generate(db, size, levels, twist, seed, kind=kind, entry=entry, final=final, way=way)
    K = kit(kind)
    out = []
    for n, p in enumerate(lay['pieces']):
        if p.get('gone') or not p.get('box'):
            continue
        b = p['box']
        r = p.get('role') or role_of(p['id'], K, S)
        # (drawn from the height of its joins, where the next piece meets it: a cave piece's box runs far down
        # into the rock, and joined pieces were drawn hundreds apart, "disjoint voxels", the user's lava cave)
        ps = S['ports'].get(p['id']) or []
        # (a room tile has no joins: laid level with its room's entry piece, from its own origin)
        fz = b[2] if K['kind'] == 'dwemer' else p['p'][2] + min(q[2] for q in ps) if ps else p['p'][2]
        # (and its number in the layout, for picking it on the plan)
        out.append([round(b[0]), round(b[1]), round(b[3]), round(b[4]), round(fz), round(max(b[5], fz + 48)), r, p.get('hall'), p['id'], n])
    e = lay['entrance'] or {}
    # (the way in at its own piece's height, as that piece is drawn: drawn at the lowest level, the ▲ seemed
    # to float outside the dungeon, the user's large ruin)
    own = e.get('piece', e.get('owner'))
    fz_of = {n: row[4] for n, row in zip([n for n, p in enumerate(lay['pieces']) if not p.get('gone') and p.get('box')], out)}
    ez = fz_of.get(own)
    if 'piece' in e:
        p0 = lay['pieces'][e['piece']]
        e = {'x': p0['p'][0], 'y': p0['p'][1]}
    # (how far up the water may stand before the way in goes under, as the Water slider counts it: from the
    # lowest floor to the highest)
    zs_ = [row[4] for row in out]
    dry_to = None
    if zs_ and ez is not None and max(zs_) + WATER_OVER_HEAD > min(zs_):
        # (as _water counts it: from the lowest floor to over a standing head on the highest)
        dry_to = round(max(0.0, min(1.0, (ez - min(zs_)) / (max(zs_) + WATER_OVER_HEAD - min(zs_)))), 2)
    # (what the game's own places of the kind would put in pieces like these, for the sliders' "as the game's"
    # figures: creatures and loose loot from the sets of each piece, on average; and the share of them lived in)
    cr = lt = 0.0
    for p in lay['pieces']:
        if p.get('gone') or not p.get('id'):
            continue
        c_, l_ = _set_amounts(S, p['id'])
        cr += c_
        lt += l_
    return {'seed': seed, 'kind': kind0, 'variant': kind if kind != kind0 else None, 'pieces': out, 'entrance': [round(e.get('x', 0)), round(e.get('y', 0))] + ([round(ez)] if ez is not None else []),
            'dry_to': dry_to, 'picked': lay.get('picked') or {},
            # (what the rules changed of what was asked, one line each: dgrules)
            'said': lay.get('said') or [],
            # (a cave's way in is a piece of its own, its mouth: not moved on the plan)
            'entry_pickable': 'piece' not in (lay.get('entrance') or {}),
            # (and only a dead end up top: the way in is the highest point, dgrules)
            'entry_ok': entry_ends(S, K, lay), 'way': lay.get('way', 'down'),
            # (how many of the game's own of the kind climb from their way in, for the Way choice)
            'climbers': list(__import__('dgrules').CLIMBERS.get(kind, (0, 0))),
            'final': lay['final'], 'halls': lay['halls'], 'tunnels': lay['tunnels'], 'open_left': lay['open_left'],
            'hall_word': {'dwemer': 'hall', 'tiled': 'room'}.get(K['halls'], 'chamber'),
            'game': {'creatures': round(cr, 1), 'loot': round(lt, 1), 'lived': round(lived_share('auto', K), 2)}}


_AMOUNTS = {}


def _set_amounts(S, pid):
    """(creatures, loose loot) a piece of this id holds on average in the game's own places (its sets)."""
    k = (id(S), pid)
    if k not in _AMOUNTS:
        sets = [_set_items(st) for st in (S.get('dress') or {}).get(pid) or []]
        n = max(1, len(sets))
        _AMOUNTS[k] = (sum(1 for d in sets for row in d if row[1] in ('CREA', 'LEVC')) / n,
                       sum(1 for d in sets for row in d if row[1] not in ('CREA', 'LEVC', 'LIGH', 'STAT', 'ACTI')) / n)
    return _AMOUNTS[k]


def again(db, key, seed=None):
    """The place made again with a new layout (or the given seed), the same name, kind, options and entrance:
    the old one taken out (its place and its door outside) and the new one made, as one change."""
    p = db.project
    c = p.cells.get(key) if p else None
    if not c or not c.get('ruin'):
        raise EditError('That place is not a dungeon the Workshop made.')
    o = dict(c['ruin'])
    name = next((zstr_(d) for t, d in c['header'] if t == 'NAME'), key)
    outside = c.get('ruin_outside')
    stack = getattr(p, 'undo_stack', [])
    n0 = len(stack)
    if outside:
        try:
            editing.delete_ref(db, outside[0], outside[1])
        except EditError:
            pass
    p.cells.pop(key, None)
    # (the people made for it keep their records and lines, unplaced: a fresh cast is made for the new one)
    db.sync_project()
    editing.commit(db, 'Took out "%s" to make it again' % name)
    r = build(db, name, o.get('size', 'medium'), o.get('levels', 'some'), o.get('twist', 'branching'), o.get('loot', 'usual'),
              o.get('creatures', 'usual'), entrance=o.get('entrance'), outside_door=o.get('outside_door'),
              seed=seed if seed is not None else random.getrandbits(31), occupants=o.get('occupants', 'auto'), kind=o.get('kind', 'dwemer'),
              water=o.get('water', 'none'), way=o.get('way', 'down'), keep=o.get('keep'))
    steps = len(getattr(p, 'undo_stack', [])) - n0
    if steps > 1:
        editing.fold(db, steps, 'Made "%s" again (new layout: %d tunnel pieces, %d halls)' % (name, r['tunnels'], r['halls']))
    return r


def zstr_(d):
    from project import unb64
    raw = unb64(d) if isinstance(d, str) else d
    return raw.split(b'\0', 1)[0].decode(ENC, 'replace')


EMPTY_SHARE = 0.53            # (the game's Dwemer ruins with nobody living in them: castsurvey's 'dwemer' setting)


def _floor_at(sc, x, y, z):
    """The walkable floor under (x, y) from a little above z, or None (the hall middles have none)."""
    h = sc.nearest_any((x, y, z + 60), (0.0, 0.0, -1.0), 420)
    return None if h is None else z + 60 - h[0]


HALL_DOOR_CLEAR = 256         # (how far in from each of a hall's openings the way stays clear)


def _thing_scene(db, refs):
    """What stands in a place, dressing and all (not doors or people), as a Scene. (seethrough.place_scene
    holds the building alone: given the dressing, it left out every barrel, chest and centurion part, so the
    ways through never saw them, the user's Nchudjak: barrels at its doors, a torso across a corridor)"""
    import seethrough
    sc = seethrough.Scene()
    for r in refs:
        if r['type'] in ('NPC_', 'CREA', 'LEVC', 'DOOR') or r.get('ri') is None:
            continue
        model = db.recs[r['ri']][5]
        low = (model or '').lower()
        if not low or 'marker' in low:
            continue
        first = len(sc.tris)
        sc.add_model(seethrough.model_tris(db, model), r['p'], r['s'])
        sc.of_ref[r['k']] = (first, len(sc.tris))
    return sc


def _clear_ways(db, key, lay, S, K):
    """Take out any dressing that stands in the way through a piece: along each piece's way from every
    opening to its middle, at knee and chest height over its floor, whatever static is met first that isn't
    a building piece goes. A rock that sat against a wall or plugged an unused exit in the game piece it was
    copied from can stand in the middle of a tunnel here (the user's Gold Grotto, 2026-10-24). The number
    taken out."""
    import seethrough
    c = db.project.cells.get(key)
    if not c:
        return 0
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    gone = 0
    for _pass in range(3):
        m = mapdata.cellmap(db, key)
        struct_ = {r['k'] for r in m['refs'] if tube.match(r['id'].lower()) or r['type'] == 'DOOR' or r['id'].lower() == K.get('jamb')}
        keep = struct_ | {r['k'] for r in m['refs'] if r['type'] in ('LIGH', 'NPC_', 'CREA', 'LEVC')
                          or re.search(r'rug|mist|sound|web|vine|moss|marker', r['id'].lower())}
        # (and whatever stands in a dead end: the game fills its dead ends, rocks and boulders in 45-60% of its caves'
        # ends, lamps, fittings, beds and barrels in 93% of its Dwemer ones (the game survey of 2026-11-04), and the lines
        # from the next piece's opening, which start a step inside the dead end, took the rocks of 8 made dead ends in 10,
        # lab j_dead. Nothing lies beyond a dead end for them to block)
        dead_ = [p_['box'] for p_ in lay['pieces'] if not p_.get('gone') and p_.get('role') == 'dead end' and p_.get('hall') is None and p_.get('box')]
        keep |= {r['k'] for r in m['refs'] if any(bx[0] - 8 <= r['p'][0] <= bx[3] + 8 and bx[1] - 8 <= r['p'][1] <= bx[4] + 8
                                                    and bx[2] - 64 <= r['p'][2] <= bx[5] + 8 for bx in dead_)}
        # (the floor: from the building pieces alone)
        sc_t = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['k'] in struct_]))
        sc = _thing_scene(db, m['refs'])
        L = _Layout(db, S, K)
        out = set()
        # (the user: machines "cannot be blocking corridors and intersections": the way through every tunnel
        # piece, a person's width of it (one line in a natural cave, whose rocks hug its walls), stays clear;
        # halls and rooms keep their machinery)
        width = (0,) if K.get('kind', '').startswith('cave') else (-40, 0, 40)
        # (low things count too where they're furniture: a chest copied from against a game piece's wall stood
        # in the middle of a corridor junction here, under the knee-high line, "poor worldbuilding", the user's
        # Nchudjak; rubble and bones on the floor are the game's way and stay)
        # (and a length of pipe lying across the way: one lay in the middle of a corridor, the user's Nchudjak)
        low_ok = lambda k_: k_ in byk and (byk[k_]['type'] == 'CONT' or FURNITURE.search(byk[k_]['id'].lower())
                                           or LOOSE_PIPE.search(byk[k_]['id'].lower()))
        byk = {r['k']: r for r in m['refs']}
        for p in lay['pieces']:
            if p.get('gone') or not p.get('id'):
                continue
            # (a dead end is left as its set has it: the game fills its dead ends, rocks and boulders in 45-60% of its
            # caves' ends, lamps, fittings, beds and barrels in 93% of its Dwemer ones (the game survey of 2026-11-04),
            # and the line to its mouth took the rocks of 8 made dead ends in 10, lab j_dead. Nothing lies beyond one)
            if p.get('role') == 'dead end' and p.get('hall') is None:
                continue
            # (a hall keeps its machinery, but not in its doorways: the first stretch in from each opening stays
            # clear, where a barrel by the game hall's blank wall stood in front of a door here, the user's Nchudjak)
            in_hall = p.get('hall') is not None
            ports = L.ports_of(p['id'], p['p'][0], p['p'][1], p['p'][2], p['p'][5])
            if not ports:
                continue
            mx = sum(o['x'] for o in ports) / len(ports)
            my = sum(o['y'] for o in ports) / len(ports)
            mz = sum(o['z'] for o in ports) / len(ports)
            for o, off in [(o, off) for o in ports for off in width]:
                dx, dy = SIDES[o['side']]
                # (from 48 out past the opening, so the threshold is walked too: a pipe lay across a crossing's
                # opening, reaching out from it, where a line starting inside never met it, the user's Nchudjak)
                ax, ay, az = o['x'] + dx * 48 - dy * off, o['y'] + dy * 48 + dx * off, o['z']
                n = max(2, int(math.hypot(mx - ax, my - ay) / 48) + 1)
                reach = min(1.0, HALL_DOOR_CLEAR / max(1.0, math.hypot(mx - ax, my - ay))) if in_hall else 1.0
                line = []
                for k in range(n + 1):
                    t = k / n * reach
                    x, y, z = ax + (mx - ax) * t, ay + (my - ay) * t, az + (mz - az) * t
                    # (looked for from just over the join, inside the way through: a Dwemer tunnel's joins are
                    # 128 over its floor, and from 150 over them the ray met the top of the tunnel's ceiling,
                    # so every line ran over the roof and nothing in a Dwemer tunnel was ever seen, the
                    # user's Nchudjak: barrels at its doors, a centurion's torso across a corridor)
                    h = sc_t.nearest_any((x, y, z + 40), (0.0, 0.0, -1.0), 700)
                    if h is not None:
                        line.append((x, y, z + 40 - h[0]))
                        continue
                    h = sc_t.nearest_any((x, y, z + 150), (0.0, 0.0, -1.0), 700)
                    if h is not None:
                        line.append((x, y, z + 150 - h[0]))
                for (x0, y0, f0), (x1, y1, f1) in zip(line, line[1:]):
                    if abs(f1 - f0) > 120:
                        continue                    # (a drop or a step: not one walk)
                    # (140: head height. A pipe from a game crossing whose side was a wall hung across the
                    # opening here at 128 over the floor, just over the 110 line, the user's Nchudjak)
                    for hgt in (20, 50, 110, 140):
                        a_ = (x0, y0, f0 + hgt)
                        d = (x1 - x0, y1 - y0, f1 - f0)
                        ln = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
                        if ln < 1:
                            continue
                        hit = sc.nearest_any(a_, (d[0] / ln, d[1] / ln, d[2] / ln), ln)
                        if hit is not None:
                            k_ = sc.owner(hit[1])
                            if k_ and k_ not in keep and (hgt > 20 or low_ok(k_)):
                                out.add(k_)
        if not out:
            break
        for k_ in out:
            c['refs'].pop(k_, None)
        gone += len(out)
        db.sync_project()
    return gone


def _unblock(db, key, lay, K, starts):
    """Walk the place as the path search does, from the way in: where walkable floor that can be reached
    meets walkable floor that can't, whatever dressing stands between them is taken out, and the walk is
    tried again (up to four times). Building pieces, doors and frames stay. The number taken out."""
    import pathgrid
    import seethrough
    c = db.project.cells.get(key)
    if not c or not starts:
        return 0
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    gone = 0
    # (what a pass took out comes back when the walk reached no further for it: in the lab a large mud cave
    # lost 96 of its rocks and boulders and the camp's plank decks to floor that was out of reach anyway)
    last, before = {}, -1
    for _pass in range(5):
        try:
            pts, edges, doors = pathgrid.walk_grid(db, key, starts, raw=True)
        except EditError:
            pts = None
        if not pts:
            c['refs'].update(last)
            gone -= len(last)
            db.sync_project()
            return gone
        nb = defaultdict(set)
        for a, b in edges:
            nb[a].add(b)
            nb[b].add(a)
        seen = {min(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - d[0], pts[i][1] - d[1]) + abs(pts[i][2] - d[2])) for d in doors}
        q = list(seen)
        while q:
            u = q.pop()
            for v in nb[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        if last and len(seen) <= before:
            c['refs'].update(last)
            gone -= len(last)
            db.sync_project()
            return gone
        before = len(seen)
        if len(seen) == len(pts) or _pass == 4:
            return gone
        m = mapdata.cellmap(db, key)
        keep = {r['k'] for r in m['refs'] if tube.match(r['id'].lower()) or r['type'] in ('DOOR', 'NPC_', 'CREA', 'LEVC')
                or r['id'].lower() == K.get('jamb')}
        sc = _thing_scene(db, m['refs'])
        dead_ = [p['box'] for p in lay['pieces'] if not p.get('gone') and p.get('role') == 'dead end' and p.get('hall') is None and p.get('box')]
        # (what may be taken out of the way: copied dressing, never a shrine, its platform and stairs, an altar or a light)
        rockish = {r['k'] for r in m['refs'] if r['type'] in ('STAT', 'ACTI', 'CONT', 'MISC')
                   and not re.search(r'statue|platform|stair|ramp|altar|shrine|^ex_dae_|^active_dae_|light|lamp|sconce|brazier|censer'
                                     r'|plat|plank|dock|rail|ladder|bridge|board|beam|scaffold|walkway', r['id'].lower())
                   # (nor what stands in a dead end: the game fills its dead ends, see _clear_ways)
                   and not any(bx[0] - 8 <= r['p'][0] <= bx[3] + 8 and bx[1] - 8 <= r['p'][1] <= bx[4] + 8
                               and bx[2] - 64 <= r['p'][2] <= bx[5] + 8 for bx in dead_)}
        # (a grid of the floor not reached, to find its neighbours of the reached quickly)
        cells_ = defaultdict(list)
        for v in range(len(pts)):
            if v not in seen:
                cells_[(int(pts[v][0] // 200), int(pts[v][1] // 200))].append(v)
        # (the floor at the back of a dead end need not be reached: the game fills its dead ends with rocks and
        # boulders, 45-60% of its caves' dead ends hold them (the game survey of 2026-11-04, j_game), and taking
        # every rock out of the way to the back wall left 85% of made dead ends bare)
        in_dead = lambda P_: any(bx[0] <= P_[0] <= bx[3] and bx[1] <= P_[1] <= bx[4] and bx[2] - 64 <= P_[2] <= bx[5] for bx in dead_)
        out = set()
        for u in seen:
            A = pts[u]
            gx, gy = int(A[0] // 200), int(A[1] // 200)
            for ix in (gx - 1, gx, gx + 1):
                for iy in (gy - 1, gy, gy + 1):
                    for v in cells_.get((ix, iy), ()):
                        B = pts[v]
                        d = math.hypot(B[0] - A[0], B[1] - A[1])
                        dz = B[2] - A[2]
                        if d > 190 or d < 1 or abs(dz) > 200:
                            continue
                        if dead_ and in_dead(B):
                            continue
                        ln = math.sqrt(d * d + dz * dz)
                        for hgt in (45, 90):
                            h = sc.nearest_any((A[0], A[1], A[2] + hgt), ((B[0] - A[0]) / ln, (B[1] - A[1]) / ln, dz / ln), ln)
                            if h is not None:
                                k_ = sc.owner(h[1])
                                if k_ and k_ not in keep and k_ in rockish:
                                    out.add(k_)
        if not out:
            return gone
        by_k = {r['k']: r for r in m['refs']}
        LAST_CLEARED.extend(by_k[k_]['id'] for k_ in out if k_ in by_k)
        last = {k_: c['refs'].pop(k_) for k_ in out if k_ in c['refs']}
        gone += len(last)
        db.sync_project()
    return gone


LAST_CLEARED = []          # (what the last builds took out of the way, for the checks)


WATER_LIFE = re.compile(r'slaughter|dreugh|fish|_eel|kelp|kollop|bubbles')


SWIM_DEEP = 90             # (water this deep over a floor: the player swims there, at any height)


def _clear_swim(db, key, lay, S, K, level, dry=False):
    """Under water the player swims, at any height: a pipe across a flooded corridor at head height or over it
    holds them there (the user's Nchudzamn, Reeking Ileum: big pipes across a submerged straight hall, "made
    my character stick in the hallway underwater", 2026-10-26). Across every piece whose floor is SWIM_DEEP
    under the water, a slice every 32 from each opening to its middle: between its walls, its floor and its
    ceiling or the surface, a person (SWIM_BODY, upright as OpenMW keeps a swimmer) must fit somewhere past
    the things standing there; where one doesn't, those things go. (A blanket line through the whole height
    took out pipes that ran along a wall with room to spare: the user's own place had room for a swimmer in
    all 453 of its flooded slices.) dry: only say what would go. The number taken out (or the list, dry)."""
    import seethrough
    c = db.project.cells.get(key)
    if not c or level is None:
        return [] if dry else 0
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    L = _Layout(db, S, K)
    out = set()
    for _pass in range(3):
        m = mapdata.cellmap(db, key)
        struct_ = {r['k'] for r in m['refs'] if tube.match(r['id'].lower()) or r['type'] == 'DOOR' or r['id'].lower() == K.get('jamb')}
        sc_t = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['k'] in struct_]))
        # (each thing's box, from its model as it stands: lights, creatures, doors and soft things aren't in the way)
        boxes = []
        for r in m['refs']:
            if r['k'] in struct_ or r['k'] in out or r['type'] in ('NPC_', 'CREA', 'LEVC', 'DOOR', 'LIGH') or r.get('ri') is None \
                    or re.search(r'rug|mist|sound|web|vine|moss|marker|kelp', r['id'].lower()):
                continue
            mo = db.recs[r['ri']][5]
            if not mo or 'marker' in mo.lower():
                continue
            one = seethrough.Scene()
            one.add_model(seethrough.model_tris(db, mo), r['p'], r['s'])
            if not one.tris:
                continue
            xs = [t[0] + a for t in one.tris for a in (0, t[3], t[6])]
            ys = [t[1] + a for t in one.tris for a in (0, t[4], t[7])]
            zs = [t[2] + a for t in one.tris for a in (0, t[5], t[8])]
            boxes.append((r['k'], min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
        found = set()
        for p in lay['pieces']:
            if p.get('gone') or not p.get('id'):
                continue
            ports = L.ports_of(p['id'], p['p'][0], p['p'][1], p['p'][2], p['p'][5])
            if not ports:
                continue
            mx = sum(o['x'] for o in ports) / len(ports)
            my = sum(o['y'] for o in ports) / len(ports)
            mz = sum(o['z'] for o in ports) / len(ports)
            for o in ports:
                ln = math.hypot(mx - o['x'], my - o['y'])
                if ln < 16:
                    continue
                ux, uy = (mx - o['x']) / ln, (my - o['y']) / ln
                vx, vy = -uy, ux
                for k in range(int(ln // 32) + 1):
                    t = k * 32 / ln
                    x, y, z = o['x'] + (mx - o['x']) * t, o['y'] + (my - o['y']) * t, o['z'] + (mz - o['z']) * t
                    f = None
                    for z0 in (z + 40, z + 150):
                        h = sc_t.nearest_any((x, y, z0), (0.0, 0.0, -1.0), 700)
                        if h is not None:
                            f = z0 - h[0]
                            break
                    if f is None or level - f < SWIM_DEEP:
                        continue
                    up = sc_t.nearest_any((x, y, f + 20), (0.0, 0.0, 1.0), 900)
                    top = min(f + 20 + up[0] if up else f + 260, level)
                    wl = sc_t.nearest_any((x, y, f + 100), (-vx, -vy, 0.0), 600)
                    wr = sc_t.nearest_any((x, y, f + 100), (vx, vy, 0.0), 600)
                    l0, l1 = -(wl[0] if wl else 150), (wr[0] if wr else 150)
                    blocks, who = [], []
                    for b in boxes:
                        cs = [((cx - x) * vx + (cy - y) * vy, (cx - x) * ux + (cy - y) * uy) for cx in (b[1], b[2]) for cy in (b[3], b[4])]
                        if min(a[1] for a in cs) > 8 or max(a[1] for a in cs) < -8 or b[6] < f + 15 or b[5] > top \
                                or max(a[0] for a in cs) < l0 or min(a[0] for a in cs) > l1:
                            continue
                        blocks.append((min(a[0] for a in cs), max(a[0] for a in cs), b[5], b[6]))
                        who.append(b[0])
                    if blocks and not _body_fits(l0, l1, f, top, blocks):
                        found.update(who)
        if not found:
            break
        out |= found
        if dry:
            continue
        for k_ in found:
            c['refs'].pop(k_, None)
        db.sync_project()
    if dry:
        return sorted(out)
    return len(out)


SWIM_BODY = (64, 136)      # (a person, upright as OpenMW keeps a swimmer: about 60 across and 130 tall)


def _body_fits(l0, l1, z0, z1, blocks):
    """Whether a SWIM_BODY fits anywhere in a slice across the way (l across, z up), clear of the blocks
    [(l0, l1, z0, z1)]: on an 8 grid."""
    ls = range(int(l0) + 4, int(l1) - 4, 8)
    zs = range(int(z0) + 4, int(z1) - 4, 8)
    free = {(a, b) for a in ls for b in zs if not any(c[0] <= a <= c[1] and c[2] <= b <= c[3] for c in blocks)}
    kw, kh = SWIM_BODY[0] // 8, SWIM_BODY[1] // 8
    return any(all((a + 8 * i, b + 8 * j) in free for i in range(kw) for j in range(kh)) for a in ls for b in zs)


# An underground lake in a cave's last chamber, with the Water control left at 0 (the user, 2026-11-13, asked whether a
# cave should get one even then: "Yes, sometimes"). How often: the game's own caves with water standing over some of
# their floors and not most of the place under (lab dn15, a floor under each piece against the place's water height):
# 28 of 123 mud caves, 15 of 58 lava, 80 of 273 grey stone, 28 of 126 pale rock, about a quarter. A made cave's last
# chamber can hold one in 126 of 160 layouts (the rest would put their tunnels under too), so LAKE_SHARE of those that
# can. The water stands LAKE_DEEP over the chamber's low floor at most (wading, not swimming: no fish), never over the
# highest LAKE_SHORE of its floor (somewhere dry to stand), LAKE_LEAST deep at least (a flat chamber has none), with
# no more than LAKE_TUNNELS joins elsewhere going under and the way in well over it. Camps keep to dry floor.
LAKE_SHARE = 0.32
LAKE_DEEP, LAKE_LEAST, LAKE_SHORE, LAKE_TUNNELS, LAKE_DOOR = 110.0, 50.0, 0.25, 2, 100.0


def _floor_under(sc, x, y, z0, reach=700.0):
    """The first floor under (x, y, z0) met from its drawn side (a cave's rock is drawn from inside: its roof, met
    from above, is passed through), or None."""
    z = z0
    for _k in range(5):
        h = sc.nearest_any((x, y, z), (0.0, 0.0, -1.0), reach)
        if h is None:
            return None
        if not sc.back_of(h[1], (0.0, 0.0, -1.0)):
            return z - h[0]
        z = z - h[0] - 1.0
    return None


def _lake_level(sc, lay):
    """Where water may stand in the last chamber as a lake (the rules above), or None."""
    import dgrules
    fin = lay.get('final')
    P = lay['pieces']
    room = [p for p in P if not p.get('gone') and p.get('id') and fin is not None and p.get('hall') == fin and p.get('box') and p.get('of') is None]
    if not room:
        return None
    floors = []
    for p in room:
        b = p['box']
        x = b[0] + 64.0
        while x < b[3]:
            y = b[1] + 64.0
            while y < b[4]:
                f = _floor_under(sc, x, y, b[5] + 10.0, b[5] - b[2] + 200.0)
                if f is not None:
                    up = sc.nearest_any((x, y, f + 4.0), (0.0, 0.0, 1.0), 1500)
                    if up is not None and up[0] >= 100 and not sc.back_of(up[1], (0.0, 0.0, 1.0)):
                        floors.append(f)
                y += 128.0
            x += 128.0
    if len(floors) < 8:
        return None
    floors.sort()
    lo = floors[len(floors) // 20]
    level = min(lo + LAKE_DEEP, floors[int(len(floors) * (1.0 - LAKE_SHORE))] - 10.0)
    if level - lo < LAKE_LEAST:
        return None
    inroom = {id(p) for p in room}
    wet = 0
    for sm in lay['seams']:
        a, b = P[sm[4]], P[sm[5]]
        if a.get('gone') or b.get('gone') or id(a) in inroom or id(b) in inroom:
            continue
        f = _floor_under(sc, sm[0], sm[1], sm[2] + 60.0, 400.0)
        if f is not None and f < level - 20.0:
            wet += 1
    if wet > LAKE_TUNNELS:
        return None
    if lay.get('S') is not None and dgrules.entrance_z(lay, lay['S']) < level + LAKE_DOOR:
        return None
    return level


def _water(db, key, lay, K, how, rng):
    """Water in the place: how (0 to 1, or the old 'pools' and 'flooded') is how far up it stands, from the
    lowest floor (0.1: pools there) to the highest (1); the way in goes under when it is lower than that;
    with no water, the slaughterfish, dreugh, kelp and pearls its dressing brought from the game's wet caves
    are taken out, and with water only those under it stay. A cave left dry has a lake in its last chamber
    now and then (_lake_level). The water height, or None."""
    share = amount('water', how)
    import seethrough
    c = db.project.cells.get(key)
    if not c:
        return None
    m = mapdata.cellmap(db, key)
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if tube.match(r['id'].lower())]))
    floors = _walk_floors(sc, lay)
    level = None
    if share > 0 and floors:
        floors.sort()
        # (that share of the way from the lowest floor people walk on to over a standing head on the highest:
        # 1 is the whole place under. Taken from each piece's box, a Dwemer piece's ran far under its floor and
        # the water stood under every floor, "no water appears at all", the user's Nchudjak, Flooded Bowels,
        # its water at -807 under floors of -218 to 619, 2026-10-26)
        top = floors[-1] + WATER_OVER_HEAD
        level = floors[0] + max(40.0, share * (top - floors[0]))
    elif share <= 0 and LAKE_SHARE > 0 and (K.get('kind') or '').startswith('cave') \
            and random.Random('%s|lake' % lay.get('seed')).random() < LAKE_SHARE:
        # (its own draw from the layout's seed: Again makes the same cave, and nothing else in it is drawn differently)
        try:
            level = _lake_level(sc, lay)
            lay['lake'] = level is not None
        except Exception as ex:
            print('dungeon lake:', repr(ex))
    # what lives in water: kept only under it, inside the place, and no more than WATER_FISH allows
    life = [r for r in m['refs'] if WATER_LIFE.search(r['id'].lower()) and r['type'] in ('CREA', 'LEVC', 'CONT', 'ACTI', 'STAT')]
    swims = lambda r: r['type'] in ('CREA', 'LEVC')
    gone = [r['k'] for r in life if level is None or not _under_water(sc, r['p'][0], r['p'][1], r['p'][2], level, swims(r))]
    allowed = _fish_allowed(lay, sc, level)
    kept_fish = [r for r in life if swims(r) and r['k'] not in gone]
    rng.shuffle(kept_fish)
    gone += [r['k'] for r in kept_fish[allowed:]]
    for k_ in gone:
        c['refs'].pop(k_, None)
    if level is not None:
        hdr = [(t, unb64_(d)) for t, d in c['header']]
        out = []
        for t, d in hdr:
            if t == 'DATA' and len(d) >= 4:
                d = struct.pack('<i', struct.unpack_from('<i', d)[0] | 0x02) + bytes(d[4:])
                out.append((t, d))
                out.append(('WHGT', struct.pack('<f', float(level))))
                continue
            if t == 'WHGT':
                continue
            out.append((t, d))
        c['header'] = [[t, b64(d)] for t, d in out]
        # (and fish in it, up to what's allowed with those the dressing brought: each at a spot inside the
        # place, deep enough to swim, half way down. Set at a piece's box middle, they swam in the rock and in
        # dry tunnels, "casting shadows on walls", and there were "too many", the user, 2026-10-26)
        fish = next((f for f in ('slaughterfish_small', 'slaughterfish') if db.resolve_id(f) is not None), None)
        if fish and K.get('setting') in ('cave', 'tomb', 'daedric', 'dwemer'):
            mine = db.project.plugin.lower()
            spots = _wet_spots(sc, lay, level)
            rng.shuffle(spots)
            for x, y, z in spots[:max(0, allowed - len(kept_fish[:allowed]))]:
                nk = db.project.new_ref_key()
                editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                               set_ref_pos([('NAME', zs(fish))], (x, y, z, 0, 0, rng.random() * 6.28), 1.0))
    db.sync_project()
    return level


WATER_OVER_HEAD = 200      # (full water stands this far over the highest floor: over a standing player's head)
FISH_DEEP = 120            # a fish only where the water is this deep
FISH_PER = 12              # one fish for every this many pieces with water deep enough to swim in ...
FISH_MOST = 4              # ... and never more than this in a place, those the dressing brought counted


def _walk_floors(sc, lay):
    """The floors people walk on: under each join, and under the middle of each hall's tiles (rays down from
    about head height, met from their drawn side)."""
    out = []
    pts = [(s[0], s[1], s[2]) for s in lay['seams'] if not lay['pieces'][s[4]].get('gone') and not lay['pieces'][s[5]].get('gone')]
    pts += [(p['p'][0], p['p'][1], p['p'][2]) for p in lay['pieces'] if not p.get('gone') and p.get('id') and p.get('hall') is not None]
    for x, y, z in pts:
        for z0 in (z + 60, z + 160):
            h = sc.nearest_any((x, y, z0), (0.0, 0.0, -1.0), 400)
            if h and not sc.back_of(h[1], (0.0, 0.0, -1.0)):
                out.append(z0 - h[0])
                break
    return out


def _under_water(sc, x, y, z, level, swims):
    """Whether a thing at (x, y, z) is inside the place (a floor under it and a roof over it, met from their
    drawn side) and under the water: a swimmer FISH_DEEP under it with room below, anything else just under."""
    down = sc.nearest_any((x, y, z + 20), (0.0, 0.0, -1.0), 1200)
    up = sc.nearest_any((x, y, z + 20), (0.0, 0.0, 1.0), 2400)
    if not down or not up or sc.back_of(down[1], (0.0, 0.0, -1.0)) or sc.back_of(up[1], (0.0, 0.0, 1.0)):
        return False
    floor = z + 20 - down[0]
    return level - floor >= (FISH_DEEP if swims else 20) and z < level - (30 if swims else 10)


def _wet_spots(sc, lay, level):
    """Spots for fish: under each join and hall tile middle where the water is FISH_DEEP deep, half way down."""
    out = []
    pts = [(s[0], s[1], s[2]) for s in lay['seams'] if not lay['pieces'][s[4]].get('gone') and not lay['pieces'][s[5]].get('gone')]
    pts += [(p['p'][0], p['p'][1], p['p'][2]) for p in lay['pieces'] if not p.get('gone') and p.get('id') and p.get('hall') is not None]
    for x, y, z in pts:
        for z0 in (z + 60, z + 160):
            if z0 > level:
                continue
            h = sc.nearest_any((x, y, z0), (0.0, 0.0, -1.0), 400)
            if h and not sc.back_of(h[1], (0.0, 0.0, -1.0)):
                floor = z0 - h[0]
                if level - floor >= FISH_DEEP and _under_water(sc, x, y, (floor + level) / 2, level, True):
                    out.append((x, y, (floor + level) / 2))
                break
    return out


def _fish_allowed(lay, sc, level):
    """How many fish a place may hold: one for every FISH_PER pieces deep under water, FISH_MOST at most, none
    when dry."""
    if level is None:
        return 0
    deep = len(_wet_spots(sc, lay, level))
    return min(FISH_MOST, deep // FISH_PER + (1 if deep >= 4 else 0))


def unb64_(d):
    from project import unb64
    return unb64(d) if isinstance(d, str) else d


LOOSE = re.compile(r'crate|barrel|sack|chest|urn|basket|keg|box')


def _settle(db, key, K=None):
    """Crates, barrels, sacks, chests, urns and baskets keep the lean they had on the game's rock; where one
    stands on something flat here (a plank deck, a floor) it is set level and down on it, and a stacked one
    on the one under it. The user's Greedy Grove had crates tilted on a level deck. The number set level.
    A kind's own things of that sort too (K['settle']: an Ayleid ruin's crates, chests and pedestals, which the game
    stands on raised floors a made room has none of: two crates and a pedestal hung in the air, 40 to 200 over the
    floor), and what stands on one goes down with it (the stone in its holder on a pedestal)."""
    import seethrough
    m = mapdata.cellmap(db, key)
    more = re.compile(K['settle']) if K and K.get('settle') else None
    loose = [r for r in m['refs'] if r.get('b') and ((r['type'] in ('CONT', 'MISC') and LOOSE.search(r['id'].lower()))
                                                    or (more is not None and r['type'] in ('CONT', 'MISC', 'STAT', 'ACTI') and more.search(r['id'].lower())))]
    if not loose:
        return 0
    ids = {id(r) for r in loose}
    riders = {}
    if more is not None:
        for r in loose:
            if not more.search(r['id'].lower()):
                continue
            s, b = r.get('s') or 1.0, r['b']
            top = r['p'][2] + b[5] * s
            on = []
            for q in m['refs']:
                if id(q) in ids or not q.get('b') or q['type'] in ('DOOR', 'NPC_', 'CREA', 'LEVC'):
                    continue
                qs, qb = q.get('s') or 1.0, q['b']
                if max(qb[3] - qb[0], qb[4] - qb[1]) * qs > 200:
                    continue
                lx, ly = _rot(q['p'][0] - r['p'][0], q['p'][1] - r['p'][1], -r['p'][5])
                if b[0] * s - 8 <= lx <= b[3] * s + 8 and b[1] * s - 8 <= ly <= b[4] * s + 8 and top - 16 <= q['p'][2] + qb[2] * qs <= top + 64:
                    on.append(q)
            if on:
                riders[id(r)] = on
    riding = {id(q) for lst in riders.values() for q in lst}
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if id(r) not in ids and id(r) not in riding and r['type'] != 'DOOR']))
    c, refs = editing._cell(db, key)
    done, n = [], 0
    for r in sorted(loose, key=lambda r: r['p'][2]):
        s = r.get('s') or 1.0
        b = r['b']
        x, y = r['p'][0], r['p'][1]
        top = r['p'][2] + b[5] * s
        if 'float' in r['id'].lower():
            continue                                  # (a barrel meant to float on water)
        # (far enough down to find the floor under what stood on a plank that was taken out of the way)
        h = sc.nearest_any((x, y, top + 10), (0.0, 0.0, -1.0), (b[5] - b[2]) * s + 700)
        if h is None:
            continue
        t = sc.tris[h[1]]
        nx, ny, nz = t[4] * t[8] - t[5] * t[7], t[5] * t[6] - t[3] * t[8], t[3] * t[7] - t[4] * t[6]
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        fz = top + 10 - h[0]
        # (stacked: on the top of a crate already set, when that is higher than what's under both)
        for (x0, y0, x1, y1, tz) in done:
            if x0 <= x <= x1 and y0 <= y <= y1 and fz < tz <= r['p'][2] + b[2] * s + 40:
                fz, nz, ln = tz, 1.0, 1.0
        ref = refs.get(r['k'])
        if not ref:
            continue
        base = r['p'][2] + b[2] * s
        if abs(nz) / ln < 0.96:
            # (a slope: it keeps its lean, as on the game's rock; brought down onto it when in the air)
            if base - fz > 24:
                editing._store(c, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (x, y, r['p'][2] - (base - fz) + 4, r['p'][3], r['p'][4], r['p'][5]), None))
                n += 1
            continue
        z = fz - b[2] * s
        editing._store(c, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (x, y, z, 0.0, 0.0, r['p'][5]), None))
        # (and what stood on it, by as much)
        for q in riders.get(id(r), []) if abs(z - r['p'][2]) > 4 else []:
            qref = refs.get(q['k'])
            if qref:
                editing._store(c, q['k'], qref['origin'], qref['idx'], set_ref_pos(qref['subs'], (q['p'][0], q['p'][1], q['p'][2] + (z - r['p'][2]), q['p'][3], q['p'][4], q['p'][5]), None))
        hw, hd = (b[3] - b[0]) * s / 2, (b[4] - b[1]) * s / 2
        done.append((x - hw, y - hd, x + hw, y + hd, z + b[5] * s))
        n += 1
    db.sync_project()
    return n


def _lay_tops(db, key, S, rng, loot='usual'):
    """Bare tables set with what the game's own dungeons of the kind keep on theirs (bottles, bowls, food,
    coin, a book, a Dwemer goblet), copied whole from one of its tables in the table's frame: the same
    table when the survey has it, otherwise one whose things all sit well inside this top. The number of
    tables set."""
    learnt = S.get('tops') or []
    loot_x = amount('loot', loot)
    share = min(0.95, TOP_SHARE['usual'] * loot_x)
    kept = bool(kit(S.get('kind') or 'dwemer').get('tidy'))
    if kept:
        share = max(share, 0.95)                # (a kept fort's tables are laid: the game's halls hold 11 loose things a tile)
    c = db.project.cells.get(key)
    if not learnt or not c:
        return 0
    m = mapdata.cellmap(db, key)
    tables = [t for t in m['refs'] if t['type'] in ('STAT', 'ACTI') and t.get('b') and TABLES.search(t['id'].lower())
              and abs(t['p'][3]) < .05 and abs(t['p'][4]) < .05]
    if not tables:
        return 0
    things = [r for r in m['refs'] if r['type'] in TOP_TYPES]
    put, n = [], 0
    for t in tables:
        b, s = t['b'], t.get('s') or 1.0
        top = t['p'][2] + b[5] * s
        w = [v * s for v in (b[0], b[1], b[3], b[4])]
        # (a table the dressing already set, or one left bare by the asked-for loot, stays as it is)
        if any(abs(r['p'][0] - t['p'][0]) < max(w[2], -w[0]) and abs(r['p'][1] - t['p'][1]) < max(w[3], -w[1])
               and top - 24 <= r['p'][2] <= top + 40 for r in things) or rng.random() >= share:
            continue
        # (another table's things only well inside this top: a round one's corners are not top)
        fit = [e for e in learnt if all(0.7 * w[0] <= d[2] <= 0.7 * w[2] and 0.7 * w[1] <= d[3] <= 0.7 * w[3] for d in e['d'])]
        same = [e for e in fit if e['t'] == t['id'].lower()]
        if not (same or fit):
            continue
        e = rng.choice(same or fit)
        if kept:
            e = max([e] + [rng.choice(same or fit) for _ in range(2)], key=lambda q: len(q['d']))
        laid = 0
        for rid, typ, lx, ly, dz, rx, ry, rz, ts in e['d']:
            if typ not in ('LIGH', 'APPA') and rng.random() < 0.8 * max(0.0, 1.0 - loot_x):
                continue
            if rid.lower().endswith('_empty') and rng.random() < loot_x - 1.0 and db.resolve_id(rid[:-6]) is not None:
                rid = rid[:-6]
            ri = db.resolve_id(rid)
            if ri is None:
                continue
            ob = mapdata.object_bounds(db, ri) or (0, 0, 0, 0, 0, 0)
            wx, wy = _rot(lx, ly, t['p'][5])
            x, y = t['p'][0] + wx, t['p'][1] + wy
            put.append((rid, (x, y, top + max(0.0, min(dz, 4.0)) - ob[2] * ts, rx, ry, (t['p'][5] + rz) % (2 * math.pi)), [], ts))
            laid += 1
        n += laid > 0
    if put:
        _write_refs(db, c, put)
        db.sync_project()
    return n


FURNITURE = re.compile(r'chair|stool|bench|table|cupboard|desk|shelf|bookcase|_bed|bedroll|wardrobe|drawers|dresser|closet|chest|crate|barrel|(?<!f)urn|sack|basket|keg')   # (not "f-urn_")
# (not columns, pillars, wells or platforms: the game builds those into its walls, 6-9% of them in its own
# places by this test)
SPILL_CHECK = re.compile(r'ashpit|altar|_pit(?!stop)|pit_|brazier|beltdrive|prayer_stool')
NO_DECLIP = re.compile(r'pipe|fitting|rail|beam|plank|plat|rock|boulder|stal|rubble|vine|moss|web|mushroom|flora|light|lamp|rug|mist|sound|statue|altar')


def _aabb(r):
    b, s = r['b'], r.get('s') or 1.0
    xs, ys = [], []
    for lx in (b[0] * s, b[3] * s):
        for ly in (b[1] * s, b[4] * s):
            wx, wy = _rot(lx, ly, r['p'][5])
            xs.append(r['p'][0] + wx)
            ys.append(r['p'][1] + wy)
    return (min(xs), min(ys), r['p'][2] + b[2] * s, max(xs), max(ys), r['p'][2] + b[5] * s)


def _declip(db, key, K):
    """Furniture and containers run into each other where two pieces' copied dressings meet, or where a
    lean the game gave them is taken away: a chest through a table, crates through crates (the user's
    tombs and ruins, 2026-10-24). Of any two whose boxes (each pulled in by a sixth) share more than a
    quarter of the smaller, the smaller goes. The number taken out."""
    c = db.project.cells.get(key)
    if not c:
        return 0
    m = mapdata.cellmap(db, key)
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    cand = []
    for r in m['refs']:
        i = r['id'].lower()
        if not r.get('b') or r['type'] in ('NPC_', 'CREA', 'LEVC', 'DOOR', 'LIGH') or tube.match(i) or i == K.get('jamb'):
            continue
        if r['type'] not in ('CONT', 'STAT', 'ACTI', 'MISC') or not FURNITURE.search(i) or NO_DECLIP.search(i):
            continue
        a = _aabb(r)
        if a[5] - a[2] < 20:
            continue
        sx, sy, sz = (a[3] - a[0]) / 6, (a[4] - a[1]) / 6, (a[5] - a[2]) / 6
        cand.append((r, (a[0] + sx, a[1] + sy, a[2] + sz, a[3] - sx, a[4] - sy, a[5] - sz)))
    vol = lambda a: max(0.0, a[3] - a[0]) * max(0.0, a[4] - a[1]) * max(0.0, a[5] - a[2])
    gone = set()
    # (pipes are left alone, their tangle is the game's, but furniture they run through goes: the user saw a
    # desk with a Dwemer pipe through it "in a glitchy way")
    pipes = []
    for r in m['refs']:
        if r.get('b') and re.search(r'pipe', r['id'].lower()) and r['type'] in ('STAT', 'ACTI'):
            a = _aabb(r)
            sx, sy, sz = (a[3] - a[0]) / 6, (a[4] - a[1]) / 6, (a[5] - a[2]) / 6
            pipes.append((a[0] + sx, a[1] + sy, a[2] + sz, a[3] - sx, a[4] - sy, a[5] - sz))
    for r1, a in cand:
        for b in pipes:
            o = (max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]), min(a[4], b[4]), min(a[5], b[5]))
            if o[3] > o[0] and o[4] > o[1] and o[5] > o[2] and vol(o) > 0.15 * vol(a):
                gone.add(r1['k'])
                break
    # (a thin pipe straight through a big dresser fills too little of its box for that: the user's Nchudjak
    # alcove. By the pipe's own mesh: short rays through the inside of the furniture's box, any that meets a
    # pipe there and the furniture goes)
    pipe_refs = [r for r in m['refs'] if r.get('b') and re.search(r'pipe', r['id'].lower()) and r['type'] in ('STAT', 'ACTI')]
    near = [(r1, a) for r1, a in cand if r1['k'] not in gone and any(
        max(a[0], b[0]) < min(a[3], b[3]) and max(a[1], b[1]) < min(a[4], b[4]) and max(a[2], b[2]) < min(a[5], b[5])
        for b in (_aabb(p) for p in pipe_refs))]
    if near:
        import seethrough
        sc_p = seethrough.place_scene(db, dict(m, refs=pipe_refs))
        for r1, a in near:
            hit = False
            for fx in (0.2, 0.5, 0.8):
                for fy in (0.2, 0.5, 0.8):
                    x, y = a[0] + (a[3] - a[0]) * fx, a[1] + (a[4] - a[1]) * fy
                    if sc_p.nearest_any((x, y, a[5]), (0.0, 0.0, -1.0), a[5] - a[2]) is not None:
                        hit = True
                        break
                if hit:
                    break
            if not hit:
                for fz in (0.3, 0.7):
                    z = a[2] + (a[5] - a[2]) * fz
                    for f in (0.3, 0.7):
                        if (sc_p.nearest_any((a[0], a[1] + (a[4] - a[1]) * f, z), (1.0, 0.0, 0.0), a[3] - a[0]) is not None
                                or sc_p.nearest_any((a[0] + (a[3] - a[0]) * f, a[1], z), (0.0, 1.0, 0.0), a[4] - a[1]) is not None):
                            hit = True
                            break
                    if hit:
                        break
            if hit:
                gone.add(r1['k'])
    for i, (r1, a) in enumerate(cand):
        if r1['k'] in gone:
            continue
        for r2, b in cand[i + 1:]:
            if r2['k'] in gone:
                continue
            o = (max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]), min(a[4], b[4]), min(a[5], b[5]))
            if o[3] <= o[0] or o[4] <= o[1] or o[5] <= o[2]:
                continue
            if vol(o) > 0.25 * min(vol(a), vol(b)):
                gone.add(r2['k'] if vol(b) <= vol(a) else r1['k'])
                if r1['k'] in gone:
                    break
    for k_ in gone:
        c['refs'].pop(k_, None)
    db.sync_project()
    return len(gone)


IN_ROCK_OK = re.compile(r'rock|boulder|stal|vine|moss|mushroom|flora|plant|sound|kwa_|web|egg|form\d|mist|light|lamp|neon|'
                        r'pipe|fitting|gear|chain|banner|tapestr|rug|marker|statue|platform|_ruin_|rubble|debris|root|cocoon|ore')


def _in_rock(db, key, K, dry=False):
    """Furniture and containers whose box runs into the building itself: up into the rock or
    the ceiling over them, or through a wall at waist height (the user's caves had a raised deck and its
    crates in the rock, the Dwemer ruins a desk and a dresser through a stair's wall, 2026-10-24). Taken
    out (or, dry, listed). Rocks, plants, pipes and lights are made to meet the rock and are left alone."""
    import seethrough
    m = mapdata.cellmap(db, key)
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else '') + (('|' + K['roofs']) if K.get('roofs') else ''))
    struct = [r for r in m['refs'] if tube.match(r['id'].lower()) or r['id'].lower() == K.get('jamb')]
    sc = seethrough.place_scene(db, dict(m, refs=struct))
    sk = {r['k'] for r in struct}
    bad = []
    for r in m['refs']:
        i = r['id'].lower()
        if r['k'] in sk or not r.get('b') or r['type'] not in ('STAT', 'CONT', 'ACTI'):
            continue
        # (the furniture, and the dressing that stands in the room: an ashpit, an altar, a column, a brazier, a
        # platform, which a copied set can push through the wall where the game's next piece made room for
        # it; the user's Vabothi had an ashpit through an alcove's wall. Only the wall test for those: a
        # column meets the ceiling on purpose)
        spill = bool(SPILL_CHECK.search(i))
        if not spill and (IN_ROCK_OK.search(i) or not FURNITURE.search(i)):
            continue
        a = _aabb(r)
        hgt = a[5] - a[2]
        if hgt < 16:
            continue
        why = None
        # (into the rock over it: rock in the top half of its box; the game sinks feet and stilts into the floor)
        mid = a[2] + hgt * 0.5
        for fx, fy in (() if spill else ((0.5, 0.5), (0.25, 0.25), (0.75, 0.75), (0.25, 0.75), (0.75, 0.25))):
            x, y = a[0] + (a[3] - a[0]) * fx, a[1] + (a[4] - a[1]) * fy
            up = sc.nearest_any((x, y, mid), (0.0, 0.0, 1.0), hgt * 0.5)
            if up is not None and up[0] < hgt * 0.5 - max(10.0, 0.1 * hgt):
                why = 'roof'
                break
        if not why and 'shelf' not in i:
            # (through a wall: the box's own diagonals at waist height, pulled in a fifth at each end; a
            # shelf hangs in the wall, as the game's tomb shelves do)
            b, s = r['b'], r.get('s') or 1.0
            zc = a[2] + hgt * 0.45
            cs = []
            for lx, ly in ((b[0], b[1]), (b[3], b[4]), (b[0], b[4]), (b[3], b[1])):
                wx, wy = _rot(lx * s * 0.8, ly * s * 0.8, r['p'][5])
                cs.append((r['p'][0] + wx, r['p'][1] + wy))
            for (x0, y0), (x1, y1) in ((cs[0], cs[1]), (cs[2], cs[3])):
                L = math.hypot(x1 - x0, y1 - y0)
                if L > 8 and sc.nearest_any((x0, y0, zc), ((x1 - x0) / L, (y1 - y0) / L, 0.0), L) is not None:
                    why = 'wall'
                    break
        if why:
            bad.append((r['k'], r['id'], why))
    if dry:
        return bad
    c = db.project.cells.get(key)
    for k_, _i, _w in bad:
        c['refs'].pop(k_, None)
    db.sync_project()
    return len(bad)


def _orphans(db, key, K):
    """The small things left in the air when what they stood on was taken out (a table through the rock, a
    shelf in the way: the user's Nchudjak had mugs, bowls, a bucket and a candle hanging where a table had
    been). Each with nothing within a hand's breadth under it drops onto what is under it, when that is
    near (a cup knocked to the floor of a ruin), and goes when it isn't. (dropped, taken out)"""
    import seethrough
    c = db.project.cells.get(key)
    if not c:
        return 0, 0
    m = mapdata.cellmap(db, key)
    small = [r for r in m['refs'] if r['type'] in TOP_TYPES and r.get('b') and r['type'] != 'LIGH'
             or (r['type'] == 'LIGH' and r.get('b') and re.search(r'candle|lamp_?\d|_lamp', r['id'].lower()) and not re.search(r'hang|chain|lantern|neon|sconce', r['id'].lower()))
             # (and rugs: one laid on a tall room's gallery hung under a made room's ceiling, the user's Valoto)
             or (r['type'] == 'STAT' and r.get('b') and re.search(r'_rug|rug_', r['id'].lower()))]
    if not small:
        return 0, 0
    ids = {id(r) for r in small}
    sc = seethrough.Scene()
    for r in m['refs']:
        if id(r) in ids or r['type'] in ('NPC_', 'CREA', 'LEVC') or r.get('ri') is None:
            continue
        model = db.recs[r['ri']][5]
        if model and 'marker' not in model.lower():
            sc.add_model(seethrough.model_tris(db, model), r['p'], r.get('s') or 1.0)
    c, refs = editing._cell(db, key)
    dropped, gone = 0, 0
    for r in small:
        s, b = r.get('s') or 1.0, r['b']
        base = r['p'][2] + b[2] * s
        x, y = r['p'][0], r['p'][1]
        h = sc.nearest_any((x, y, base + 6), (0.0, 0.0, -1.0), 400)
        if h is not None and h[0] <= 6 + 10:
            continue                                   # (standing on something)
        try:
            import hangsurvey
            if hangsurvey.hangs(db, db.recs[r['ri']][5] if r.get('ri') is not None else '', r['id']):
                continue                               # (what the game hangs: on its pegs, not on a table)
        except Exception:
            pass
        ref = refs.get(r['k'])
        if not ref:
            continue
        if h is not None and h[0] - 6 <= 140 and not K.get('tidy'):
            # (down onto it, level: what was on a table lies on the floor; in a ruin. A kept place, K['tidy'], a fort
            # with its garrison: it goes with its table. Made halls had a third of their loose things on the floor,
            # the game's forts 12.7%)
            set_z = r['p'][2] - (h[0] - 6)
            editing._store(c, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (x, y, set_z, 0.0, 0.0, r['p'][5]), None))
            dropped += 1
        else:
            c['refs'].pop(r['k'], None)
            gone += 1
    db.sync_project()
    return dropped, gone


DOORWAY = re.compile(r'ndoor|doorway|doorjam|_dj_0|door_?frame')
DOOR_FRONT = 120              # (the game's own places have 1-2% of their furniture this close in front of a door)
DOOR_SIDE = 110               # (in a kept place: this far out from a door frame's face, over its whole width, _door_fronts)


def _door_fronts(db, key, K):
    """Furniture and containers standing in front of a door or doorway, within its width and DOOR_FRONT of it
    on either side, go: copied from a game piece whose side there was a wall, a crate stood in a tomb's doorway,
    a barrel in front of a Dwemer door (the user's Veshothi and Nchudjak). The number taken out."""
    c = db.project.cells.get(key)
    if not c:
        return 0
    m = mapdata.cellmap(db, key)
    doors = [r for r in m['refs'] if r.get('b') and (r['type'] == 'DOOR' or DOORWAY.search(r['id'].lower())
                                                    or r['id'].lower() == (K.get('jamb') or '').lower())
             and not (K.get('door_dress') and re.search(K['door_dress'], r['id'].lower()))]
    furn = [r for r in m['refs'] if r.get('b') and not r.get('arch') and (r['type'] == 'CONT' or FURNITURE.search(r['id'].lower()))
            and not NO_DECLIP.search(r['id'].lower())]
    out = set()
    for d in doors:
        rz = d['p'][5]
        cs, sn = math.cos(-rz), math.sin(-rz)
        b = [v * (d.get('s') or 1.0) for v in d['b']]
        thin = 0 if (b[3] - b[0]) <= (b[4] - b[1]) else 1      # (the door's thin side is the way through)
        w0, w1 = (b[1], b[4]) if thin == 0 else (b[0], b[3])
        for r in furn:
            dx, dy = r['p'][0] - d['p'][0], r['p'][1] - d['p'][1]
            lx, ly = dx * cs - dy * sn, dx * sn + dy * cs
            a, w = (lx, ly) if thin == 0 else (ly, lx)
            if abs(a) < DOOR_FRONT and w0 - 10 < w < w1 + 10 and d['p'][2] + b[2] - 40 < r['p'][2] < d['p'][2] + b[5]:
                out.add(r['k'])
    if K.get('tidy'):
        # (a kept place: nothing over knee height anywhere within a door frame's own width and DOOR_SIDE of its face,
        # by the thing's whole footprint. By its middle alone a chest of drawers 137 long stood against the wall just
        # inside the front door of four of Fort Urasek's interiors, the same set drawn for each way in, and a shelf
        # scaled half again reached to 45 from an inner door: the user's "Counter blocking door", 2026-11-12. The game's
        # forts have something there at 124 of 919 doors, stone blocks and shelves; a made keep's front doors none)
        for d in doors:
            rz = d['p'][5]
            cs, sn = math.cos(-rz), math.sin(-rz)
            b = [v * (d.get('s') or 1.0) for v in d['b']]
            thin = 0 if (b[3] - b[0]) <= (b[4] - b[1]) else 1
            w0, w1 = (b[1], b[4]) if thin == 0 else (b[0], b[3])
            for r in furn:
                if r['k'] in out:
                    continue
                rb, rs = r['b'], r.get('s') or 1.0
                if r['p'][2] + rb[5] * rs < d['p'][2] + b[2] + 40 or r['p'][2] + rb[2] * rs > d['p'][2] + b[5]:
                    continue
                c2, s2 = math.cos(r['p'][5]), math.sin(r['p'][5])
                pts = [(r['p'][0] + (lx * c2 + ly * s2) * rs, r['p'][1] + (-lx * s2 + ly * c2) * rs)
                       for lx in (rb[0], (rb[0] + rb[3]) / 2.0, rb[3]) for ly in (rb[1], (rb[1] + rb[4]) / 2.0, rb[4])]
                for px, py in pts:
                    dx, dy = px - d['p'][0], py - d['p'][1]
                    lx, ly = dx * cs - dy * sn, dx * sn + dy * cs
                    a, w = (lx, ly) if thin == 0 else (ly, lx)
                    if abs(a) < DOOR_SIDE and w0 - 4 < w < w1 + 4:
                        out.add(r['k'])
                        break
    out |= _door_walk(db, m, K, doors)
    for k_ in out:
        c['refs'].pop(k_, None)
    db.sync_project()
    return len(out)


def _door_walk(db, m, K, doors):
    """The dressing a person walking straight through a doorway would run into: rays through each door frame,
    along its thin side from DOOR_FRONT before it to DOOR_FRONT past it, at knee, waist and head height over its
    sill and across the middle of its width. Pipes count here (a pipe hung down the middle of a Dwemer door,
    "looks cool, but the character cannot run through", the user's Nchudzamn); the building, doors and lights
    don't. The keys met."""
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    jamb = (K.get('jamb') or '').lower()
    frames = [d for d in doors if d['type'] != 'DOOR']        # (a door's own point is at its hinge: the frame's middle)
    if not frames:
        return set()
    sc = _thing_scene(db, m['refs'])
    byk = {r['k']: r for r in m['refs']}
    keep = lambda r: (tube.match(r['id'].lower()) or r['id'].lower() == jamb or r['type'] in ('DOOR', 'LIGH')
                      or DOORWAY.search(r['id'].lower()) or re.search(r'rug|mist|web|marker', r['id'].lower()))
    met = set()
    for d in frames:
        b, s = d['b'], d.get('s') or 1.0
        R = seethrough_matrix(d['p'][3], d['p'][4], d['p'][5])
        ext = [(b[3] - b[0]) * s, (b[4] - b[1]) * s]
        thin = 0 if ext[0] <= ext[1] else 1
        wide = 1 - thin
        mid = [(b[0] + b[3]) / 2 * s, (b[1] + b[4]) / 2 * s]
        sill = b[2] * s
        here = set()
        for f in (-0.25, 0.0, 0.25):
            for hgt in (40, 90, 120, 150):
                lo = [0.0, 0.0, sill + hgt]
                lo[wide] = mid[wide] + f * ext[wide]
                lo[thin] = mid[thin] - DOOR_FRONT
                o = tuple(d['p'][i] + sum(R[i][j] * lo[j] for j in range(3)) for i in range(3))
                dv = tuple(R[i][thin] for i in range(3))
                skip = set()
                for _ in range(6):                       # (past what may stay, to what's behind it)
                    # (a copy each time: the search adds every triangle it tries to the set it's given)
                    h = sc._hits(o, dv, 2 * DOOR_FRONT, set(skip), True, both=True)
                    if h is None:
                        break
                    k_ = sc.owner(h[1])
                    r = byk.get(k_)
                    if r is None or keep(r):
                        a_, b_ = sc.of_ref.get(k_, (h[1], h[1] + 1))
                        skip |= set(range(a_, b_))
                        continue
                    here.add(k_)
                    break
        met |= here
        # (a pipe met in the doorway takes the rest of its run in the opening with it: the user's Nchudzamn door
        # had five fittings across it, a bar and a drop down the middle, and one alone gone left the others hanging)
        if any(LOOSE_PIPE.search(byk[k_]['id'].lower()) for k_ in here if k_ in byk):
            for r in m['refs']:
                if r['k'] in met or not r.get('b') or not LOOSE_PIPE.search(r['id'].lower()) or keep(r):
                    continue
                dx, dy, dz = (r['p'][i] - d['p'][i] for i in range(3))
                lp = [sum(R[i][j] * v for i, v in enumerate((dx, dy, dz))) for j in range(3)]   # (into the frame's own axes)
                if abs(lp[thin] - mid[thin]) < 60 and abs(lp[wide] - mid[wide]) < ext[wide] / 2 + 10 and sill - 10 < lp[2] < b[5] * s + 10:
                    met.add(r['k'])
    return met


def seethrough_matrix(rx, ry, rz):
    import seethrough
    return seethrough._matrix(rx, ry, rz)


LOOSE_PIPE = re.compile(r'fitting|pipe')


def _loose_pipes(db, key, K):
    """Pipe fittings copied in a set where they ran out of a game piece's wall or floor, and here run out of
    nothing: a length of pipe lying in the air across a room, the user's Nchudjak. Each fitting must meet the
    building (a wall, floor or ceiling) or another fitting that does, by short rays out of each face of its
    box against the real meshes; the rest go, again until none are left hanging. The number taken out."""
    c = db.project.cells.get(key)
    if not c:
        return 0
    gone = 0
    for _pass in range(4):
        out, _n = pipes_hanging(db, mapdata.cellmap(db, key), K)
        if not out:
            break
        for k_ in out:
            c['refs'].pop(k_, None)
        gone += len(out)
        db.sync_project()
    return gone


PIPE_ALONE = 160              # (nothing at all this far out of a fitting's faces: 3.6% of the game's own fittings)


def pipes_hanging(db, m, K, margin=PIPE_ALONE, front_only=False):
    """(the keys of the pipe fittings in place m that hang in the air, the number of fittings): each must meet
    something that isn't a fitting (the building, a machine, a table) within margin of its faces, or a fitting
    joined to one that does. Measured on the game's own Dwemer places: a contact rule (24, front faces) called
    20-34% of them hanging; nothing within 160, either face, 3.6%."""
    import seethrough
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['fixed']) if K.get('fixed') else ''))
    if True:
        pipes = [r for r in m['refs'] if r.get('b') and r['type'] in ('STAT', 'ACTI') and LOOSE_PIPE.search(r['id'].lower())
                 and not tube.match(r['id'].lower())]
        if not pipes:
            return [], 0
        sc = _thing_scene(db, m['refs'])
        pk = {r['k'] for r in pipes}
        grounded, links = set(), defaultdict(set)
        for r in pipes:
            own = sc.of_ref.get(r['k'])
            skip = set(range(own[0], own[1])) if own else set()
            # (along the fitting's own axes, turned and tilted as it stands: one laid on its side runs along
            # the room, and rays up and down its world box missed its ends)
            b, s = r['b'], r.get('s') or 1.0
            R = seethrough._matrix(r['p'][3], r['p'][4], r['p'][5])
            lc = ((b[0] + b[3]) / 2 * s, (b[1] + b[4]) / 2 * s, (b[2] + b[5]) / 2 * s)
            mx, my, mz = (r['p'][i] + sum(R[i][j] * lc[j] for j in range(3)) for i in range(3))
            half = ((b[3] - b[0]) / 2 * s, (b[4] - b[1]) / 2 * s, (b[5] - b[2]) / 2 * s)
            for ax_ in range(3):
                for sg in (1.0, -1.0):
                    d = [R[0][ax_] * sg, R[1][ax_] * sg, R[2][ax_] * sg]
                    # (front faces only: the game's walls are one-sided, and the fittings over the user's
                    # Nchudjak room met the corridor beside it from outside, from behind its faces)
                    h = sc._hits((mx, my, mz), tuple(d), half[ax_] + margin, set(skip), True, both=not front_only)
                    if h is None:
                        continue
                    k_ = sc.owner(h[1])
                    if k_ in pk:
                        links[r['k']].add(k_)
                        links[k_].add(r['k'])
                    else:
                        grounded.add(r['k'])
        # (two fittings touching only each other still hang in the air: held means joined, through fittings,
        # to one that meets the building)
        held, q = set(grounded), list(grounded)
        while q:
            for k2 in links[q.pop()]:
                if k2 not in held:
                    held.add(k2)
                    q.append(k2)
        return [r['k'] for r in pipes if r['k'] not in held], len(pipes)


def _upright(db, key):
    """Chairs, stools, benches and tables the game had knocked over keep their fall when it is a fall (on
    their side, over 60°); one leaning part way over on a level floor is stood upright on it (the user saw
    "tilted chairs" in a made ruin). The number stood up."""
    import seethrough
    m = mapdata.cellmap(db, key)
    tilt = [r for r in m['refs'] if r.get('b') and re.search(r'chair|stool|bench|table', r['id'].lower())
            and 0.08 < max(abs(r['p'][3]), abs(r['p'][4])) < 1.05]
    if not tilt:
        return 0
    ids = {id(r) for r in tilt}
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if id(r) not in ids and r['type'] != 'DOOR']))
    c, refs = editing._cell(db, key)
    n = 0
    for r in tilt:
        b, s = r['b'], r.get('s') or 1.0
        x, y = r['p'][0], r['p'][1]
        h = sc.nearest_any((x, y, r['p'][2] + b[5] * s + 10), (0.0, 0.0, -1.0), (b[5] - b[2]) * s + 120)
        if h is None:
            continue
        t = sc.tris[h[1]]
        nz = t[3] * t[7] - t[4] * t[6]
        ln = math.sqrt((t[4] * t[8] - t[5] * t[7]) ** 2 + (t[5] * t[6] - t[3] * t[8]) ** 2 + nz * nz) or 1.0
        if abs(nz) / ln < 0.96:
            continue
        ref = refs.get(r['k'])
        if not ref:
            continue
        fz = r['p'][2] + b[5] * s + 10 - h[0]
        editing._store(c, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (x, y, fz - b[2] * s, 0.0, 0.0, r['p'][5]), None))
        n += 1
    db.sync_project()
    return n


def _floaters(db, key):
    """Lamps with nothing to hang on: a Dwemer pipe lamp whose pipe was the next piece's in the game, or
    stood in the way and was taken out (the user's "floating light", light_dwrv_neon01). A light with a
    body that meets nothing within a hand's breadth of its sides, top or bottom goes. The number taken out."""
    import seethrough
    c = db.project.cells.get(key)
    m = mapdata.cellmap(db, key)
    # (lamps with a body, and what is mounted rather than stood: the Dwemer pipes, fittings, gears and
    # valves, chains, lanterns, sconces and torches; the user saw them hanging in the air on both storeys
    # of a hall)
    mount = re.compile(r'fitting|pipe|neon|gear|valve|_cog|chain|lantern|sconce|torch|banner')
    cand = [r for r in m['refs'] if r.get('b') and max(r['b'][3] - r['b'][0], r['b'][4] - r['b'][1], r['b'][5] - r['b'][2]) > 20
            and (r['type'] == 'LIGH' or (r['type'] in ('STAT', 'ACTI') and mount.search(r['id'].lower())))]
    if not cand or not c:
        return 0
    # (the dressing too, not the building alone: a Dwemer lamp hangs on a copied pipe as often as on the corridor's
    # own, and with only the building in the scene a third of a made ruin's lights were "floating" and went, the
    # dungeon round of 2026-11-04, lab j_dress2: 29 lights drawn, 19 kept)
    sc = _thing_scene(db, m['refs'])
    for r in m['refs']:
        if r['type'] == 'DOOR' and r.get('ri') is not None and db.recs[r['ri']][5]:
            first_ = len(sc.tris)
            sc.add_model(seethrough.model_tris(db, db.recs[r['ri']][5]), r['p'], r.get('s') or 1.0)
            sc.of_ref[r['k']] = (first_, len(sc.tris))
    ids_by_k = {r['k']: r['id'].lower() for r in m['refs']}
    c_, refs_ = editing._cell(db, key)
    gone = []
    moved = 0
    for r in cand:
        a = _aabb(r)
        cx, cy, cz = (a[0] + a[3]) / 2, (a[1] + a[4]) / 2, (a[2] + a[5]) / 2
        half = ((a[3] - a[0]) / 2, (a[4] - a[1]) / 2, (a[5] - a[2]) / 2)
        touches = False
        neon = 'neon' in r['id'].lower()
        big = max(half)
        q2 = 0.7071
        # (along the axes and the diagonals: a fitting may meet its pipe only at an end. A Dwemer pipe lamp
        # hangs on the side of a pipe, often one built into the corridor itself: it must meet something at
        # its sides, not only above it, where it would be stuck to a bare ceiling)
        dirs = [((1, 0, 0), half[0]), ((-1, 0, 0), half[0]), ((0, 1, 0), half[1]), ((0, -1, 0), half[1]),
                ((q2, q2, 0), big), ((-q2, q2, 0), big), ((q2, -q2, 0), big), ((-q2, -q2, 0), big)]
        if not neon:
            dirs += [((0, 0, 1), half[2]), ((0, 0, -1), half[2])]
        for d, hlen in dirs:
            # (through its own body: what lies beyond it, within a hand's breadth of its side)
            o, left = (cx, cy, cz), hlen + 24
            for _step in range(6):
                h = sc.nearest_any(o, d, left)
                if h is None:
                    break
                ok_ = sc.owner(h[1])
                if ok_ != r['k']:
                    touches = True
                    break
                adv = h[0] + 0.5
                o = (o[0] + d[0] * adv, o[1] + d[1] * adv, o[2] + d[2] * adv)
                left -= adv
                if left <= 0:
                    break
            if touches:
                break
        if touches:
            continue
        # (a light hanging on nothing is slid onto the nearest thing on the side the game mounts that lamp by, when
        # that is within reach: a sconce back onto the wall, a neon lamp up onto its pipe. The game's own placings of
        # the model say which side and how close; a light with no such side, or nothing within reach, goes as before)
        mt = _mount_of(db, r['id']) if r['type'] == 'LIGH' else None
        if mt:
            (ax, ay, az), gap = mt
            s_ = r.get('s') or 1.0
            b_ = r['b']
            wx, wy = _rot(ax, ay, r['p'][5])
            d = (wx, wy, az)
            hlen = (b_[3] - b_[0]) / 2 * s_ if ax else (b_[4] - b_[1]) / 2 * s_ if ay else (b_[5] - b_[2]) / 2 * s_
            o, left, hit = (cx, cy, cz), hlen + MOUNT_REACH, None
            for _step in range(6):
                h = sc.nearest_any(o, d, left)
                if h is None:
                    break
                if sc.owner(h[1]) != r['k']:
                    hit = (math.hypot(math.hypot(o[0] - cx, o[1] - cy), o[2] - cz) + h[0], h[1])
                    break
                adv = h[0] + 0.5
                o = (o[0] + d[0] * adv, o[1] + d[1] * adv, o[2] + d[2] * adv)
                left -= adv
                if left <= 0:
                    break
            ref = refs_.get(r['k'])
            if hit and ref:
                shift = hit[0] - hlen - gap
                if shift > 0:
                    p_ = r['p']
                    editing._store(c_, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (p_[0] + d[0] * shift, p_[1] + d[1] * shift, p_[2] + d[2] * shift, p_[3], p_[4], p_[5]), None))
                    moved += 1
                    continue
        gone.append(r['k'])
    for k_ in gone:
        c['refs'].pop(k_, None)
    db.sync_project()
    return len(gone)


MOUNT_REACH = 160             # (a floating light slid this far at most onto what it hangs on)
_MOUNTS = {}


def _mount_of(db, rid):
    """How the game hangs a light of this model: the side of it, in its own frame (+-X, +-Y, +-Z), that meets what
    it is mounted on, and the gap left, read from the game's own placings of it (12 places at most); None when
    they don't agree on a side (a candle stood on a table meets things on no fixed side). ((dx, dy, dz), gap)"""
    import seethrough
    low = rid.lower()
    key = (id(db.recs), low)
    if key in _MOUNTS:
        return _MOUNTS[key]
    _MOUNTS[key] = None
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    if not b:
        return None
    cells = sorted({db.recs[ci][1].lower() for ci in db.used_in.get(low, ()) if ci < len(db.recs) and db.recs[ci][0] == 'CELL'})
    cells = [ck for ck in cells if not ck.startswith('#') and db.by_key.get(('CELL', ck))]
    got, gaps, n = Counter(), defaultdict(list), 0
    axes = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    for ck in cells[:12]:
        try:
            m = mapdata.cellmap(db, ck, original=True)
        except Exception:
            continue
        mine = [r for r in m['refs'] if r['id'].lower() == low and r.get('b')]
        if not mine:
            continue
        sc = _thing_scene(db, m['refs'])
        for r in mine[:6]:
            a = _aabb(r)
            cx, cy, cz = (a[0] + a[3]) / 2, (a[1] + a[4]) / 2, (a[2] + a[5]) / 2
            s_ = r.get('s') or 1.0
            n += 1
            for ax, ay, az in axes:
                hlen = (b[3] - b[0]) / 2 * s_ if ax else (b[4] - b[1]) / 2 * s_ if ay else (b[5] - b[2]) / 2 * s_
                wx, wy = _rot(ax, ay, r['p'][5])
                d = (wx, wy, az)
                o, left, dist = (cx, cy, cz), hlen + 40, None
                for _step in range(6):
                    h = sc.nearest_any(o, d, left)
                    if h is None:
                        break
                    if sc.owner(h[1]) != r['k']:
                        dist = math.hypot(math.hypot(o[0] - cx, o[1] - cy), o[2] - cz) + h[0]
                        break
                    adv = h[0] + 0.5
                    o = (o[0] + d[0] * adv, o[1] + d[1] * adv, o[2] + d[2] * adv)
                    left -= adv
                    if left <= 0:
                        break
                if dist is not None:
                    got[(ax, ay, az)] += 1
                    gaps[(ax, ay, az)].append(max(0.0, dist - hlen))
            if n >= 40:
                break
        if n >= 40:
            break
    if n < 3 or not got:
        return None
    side, k = got.most_common(1)[0]
    if k < 3 or k < 0.5 * n:
        return None
    g = sorted(gaps[side])
    _MOUNTS[key] = (side, round(g[len(g) // 2], 1))
    return _MOUNTS[key]


def _walk_starts(db, lay):
    """Where the walking paths start: the arrival spot, and a little way into the first tunnel (a cave's
    exit passage can be too low for the path search, which wants a person's headroom)."""
    out = [lay['arrive'][:3]] if lay.get('arrive') else []
    S, K = lay.get('S'), lay.get('K')
    if not S or not lay['pieces']:
        return out
    p0 = lay['pieces'][0]
    for o in _Layout(db, S, K).ports_of(p0['id'], p0['p'][0], p0['p'][1], p0['p'][2], p0['p'][5]):
        dx, dy = SIDES[o['side']]
        out.append([o['x'] + dx * 128, o['y'] + dy * 128, o['z']])
    return out


def ruin_paths(db, key, lay):
    """A Dwemer ruin's walking paths, from its own layout: a point on the floor of each tunnel piece
    (between its openings) and of each hall tile that has a floor, joined along the seams where pieces meet
    and across neighbouring hall tiles; doors are walked through (a dungeon's enemies should follow you,
    Project Tamriel's rule 5 being for patrolled towns). The game's grids have a point a tile and two links
    a point. (The other kinds' chambers are too big for a point a piece: they are walked by pathgrid.)"""
    import pathgrid
    import seethrough
    if (lay.get('K') or {}).get('kind', 'dwemer') != 'dwemer':
        r = pathgrid.redraw(db, key, _walk_starts(db, lay))
        return {'points': r.get('points', 0) if isinstance(r, dict) else 0, 'links': r.get('links', 0) if isinstance(r, dict) else 0}
    m = mapdata.cellmap(db, key)
    sc = seethrough.place_scene(db, m)
    node = {}
    pts = []
    for n, p in enumerate(lay['pieces']):
        if p.get('gone') or not p.get('id'):
            continue
        x, y, z, rz = p['p'][0], p['p'][1], p['p'][2], p['p'][5]
        if p.get('hall') is None:
            ports = [(o['x'], o['y']) for o in _Layout(db, lay['S']).ports_of(p['id'], x, y, z, rz)] if lay.get('S') else []
            if ports:
                x, y = sum(a for a, _b in ports) / len(ports), sum(b for _a, b in ports) / len(ports)
        fz = _floor_at(sc, x, y, z)
        if fz is None or fz < z - 260:
            continue
        node[n] = len(pts)
        pts.append([round(x), round(y), round(fz)])
    edges = set()

    def clear(a, b):
        A, B = pts[a], pts[b]
        d = math.hypot(B[0] - A[0], B[1] - A[1])
        if d < 1:
            return False
        o = (A[0], A[1], (A[2] + B[2]) / 2 + 60)
        h = sc.nearest_any(o, ((B[0] - A[0]) / d, (B[1] - A[1]) / d, 0.0), d)
        return h is None
    for sx, sy, sz, side, a, b in lay['seams']:
        if a in node and b in node:
            edges.add((min(node[a], node[b]), max(node[a], node[b])))
    halls = defaultdict(list)
    for n, p in enumerate(lay['pieces']):
        if n in node and p.get('hall') is not None:
            halls[p['hall']].append(n)
    for h, ns in halls.items():
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                A, B = pts[node[a]], pts[node[b]]
                if 200 < math.hypot(A[0] - B[0], A[1] - B[1]) < 300 and clear(node[a], node[b]):
                    edges.add((min(node[a], node[b]), max(node[a], node[b])))
    used = sorted({i for e in edges for i in e})
    new = {o: k for k, o in enumerate(used)}
    pts = [pts[o] for o in used]
    edges = sorted((new[a], new[b]) for a, b in edges)
    if len(pts) >= 2:
        pathgrid.save(db, key, pts, [list(e) for e in edges])
    return {'points': len(pts), 'links': len(edges)}


def _hall_spots(db, sc, lay, hall):
    """Floor spots in a hall, chamber or room, on a 128 grid inside its pieces, nearest its middle first."""
    hp = [p for p in lay['pieces'] if p.get('hall') == hall and not p.get('gone') and p.get('box')]
    if not hp:
        return []
    spots = []
    seen = set()
    for p in hp:
        b = p['box']
        for gx in range(int(b[0] // 128) + 1, int(b[3] // 128)):
            for gy in range(int(b[1] // 128) + 1, int(b[4] // 128)):
                if (gx, gy) in seen:
                    continue
                seen.add((gx, gy))
                x, y = gx * 128.0, gy * 128.0
                # (from half way up the piece in a tomb or a Daedric room: a Velothi room's ceiling is 118 over
                # its origin, so a ray from 120 up found the top of its roof)
                kind_ = (lay.get('K') or {}).get('kind', 'dwemer')
                z0_ = p['p'][2] if kind_ == 'dwemer' else p['p'][2] + 120 if kind_.startswith('cave') else (b[2] + b[5]) / 2
                fz = _floor_at(sc, x, y, z0_)
                # (indoors: a ceiling over it. From over a low chamber the ray found its roof's top, and a
                # whole camp was laid on the roof of the user's Varensis Tomb)
                # (and dry: nobody camps in the water, lay['water_at'])
                if fz is not None and fz > p['p'][2] - 300 and sc.nearest_any((x, y, fz + 20), (0.0, 0.0, 1.0), 1200) is not None \
                        and (lay.get('water_at') is None or fz >= lay['water_at'] + 8):
                    spots.append((x, y, fz))
    if not spots:
        return []
    mx = sum(s[0] for s in spots) / len(spots)
    my = sum(s[1] for s in spots) / len(spots)
    # (a spot with its neighbours all floor too: room round a fire)
    have = {(round(s[0] / 128), round(s[1] / 128)) for s in spots}
    inner = lambda s: sum((round(s[0] / 128) + dx, round(s[1] / 128) + dy) in have for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    spots.sort(key=lambda s: (-min(inner(s), 9), math.hypot(s[0] - mx, s[1] - my)))
    return spots


def _camp_site(sc, spots, ndeck):
    """Where a camp goes: (x, y, floor z, turn, highest floor under the decks) for the flattest of the floor
    spots, room for ndeck decks side by side (each 256 by 500) and a fire 330 to one side; None when no
    spot has floor all under it and headroom over it."""
    best = None
    for x, y, z in spots[:36]:
        for q in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            fl = []
            ok = True
            pts = [(-330 + dx, dy) for dx in (-80, 0, 80) for dy in (-80, 0, 80)]
            pts += [(d * 256 + dx, dy) for d in range(ndeck) for dx in (-120, 0, 120) for dy in (-240, -120, 0, 120, 240)]
            # (and the ring round the fire where the bedrolls (170 out) and the people (150) go: in a Velothi
            # room 256 across they stood beyond its walls, over the void)
            ring = [(-330 + math.cos(a) * rr, math.sin(a) * rr) for rr in (150, 190) for a in [k * math.pi / 4 for k in range(8)]]
            for lx, ly in pts + ring:
                wx, wy = _rot(lx, ly, q)
                f = _floor_at(sc, x + wx, y + wy, z + 60)
                if f is None or abs(f - z) > 160:
                    ok = False
                    break
                if (lx, ly) in ring:
                    up_ = sc.nearest_any((x + wx, y + wy, f + 20), (0.0, 0.0, 1.0), 1200)
                    if up_ is None or up_[0] < 120:
                        ok = False
                        break
                    # (and no wall between it and the fire: floor beyond a wall is the next room's)
                    fx_, fy_ = _rot(-330, 0, q)
                    dx_, dy_ = x + wx - (x + fx_), y + wy - (y + fy_)
                    L_ = math.hypot(dx_, dy_)
                    if L_ > 1 and sc.nearest_any((x + fx_, y + fy_, z + 50), (dx_ / L_, dy_ / L_, 0.0), L_) is not None:
                        ok = False
                        break
                    continue
                fl.append((lx, f))
            if not ok:
                continue
            up = sc.nearest_any((x, y, z + 20), (0.0, 0.0, 1.0), 1200)
            if up is None or up[0] < 220:
                continue                            # (too low under the roof, or no roof at all: on top of it)
            under = [f for lx, f in fl if lx > -200] or [z]
            fire = [f for lx, f in fl if lx <= -200]
            spread, fs = max(under) - min(under), max(fire) - min(fire)
            # (a deck only where the rock under it is near level, so it lies on it; a fire only where its
            # pit sits on the rock all round)
            if (ndeck and spread > 60) or fs > 40:
                continue
            if best is None or spread + fs < best[0]:
                best = (spread + fs, (x, y, z, q, max(under)))
        if best and best[0] < 30:
            break
    if best is None and ndeck:
        return None
    return best[1] if best else None


def _put_ref(db, c, mine, rid, cx, cy, q, lx, ly, z, rz):
    """One camp thing at (lx, ly) in the camp's frame: z its base height, None for the floor under it, or
    ('low', scene) for the lowest floor under its footprint."""
    ri = db.resolve_id(rid)
    if ri is None:
        return
    b = mapdata.object_bounds(db, ri) or (0, 0, 0, 0, 0, 0)
    wx, wy = _rot(lx, ly, q)
    x, y = cx + wx, cy + wy
    if z is None or isinstance(z, tuple):
        sc = z[1] if isinstance(z, tuple) else _CAMP_SC[0]
        fs = [_floor_at(sc, x + dx, y + dy, _CAMP_SC[1] + 60) for dx in (-0.4 * (b[3] - b[0]), 0, 0.4 * (b[3] - b[0]))
              for dy in (-0.4 * (b[4] - b[1]), 0, 0.4 * (b[4] - b[1]))]
        fs = [f for f in fs if f is not None]
        # (the lowest floor under it: sunk a little into the high side, never in the air over the low one)
        z = min(fs) if fs else _CAMP_SC[1]
    nk = db.project.new_ref_key()
    editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                   set_ref_pos([('NAME', zs(rid))], (x, y, z - b[2], 0, 0, (q + rz) % (2 * math.pi)), 1.0))
    return nk


_CAMP_SC = [None, 0.0]           # (the scene and the camp's floor height, for things set on the floor)

# The game's cave camps, 480 of them in 255 caves (campsurvey, 2026-10-24): one bed (302) or two (103), a
# person or two; the beds against the rock (167 from it, p10 91), head or foot to it, 41% on a plank deck;
# a fire in 39% of them, 330 from the beds, logs and stools round it at 108; crates (57% of camps, 3.6 of
# them), chests (60%), barrels (50%), sacks (38%) by the walls (150-180 from the rock); a table in 42%,
# lanterns and candles in 68%, standing torches in 54%, bottles, brew and bread in 67%.
CAMP_BEDS = (('active_de_bedroll', 0.5), ('active_de_p_bed_28', 0.22), ('active_de_bed_30', 0.15), ('t_com_furn_bedroll_01', 0.13))
CAMP_FIRES = ('light_pitfire00', 'furn_de_firepit_f_323', 'furn_de_firepit_f', 'furn_de_firepit_f_200', 'furn_de_firepit_f_01', 'light_pitfire01')
CAMP_SEATS = ('furn_log_04', 'furn_log_01', 'furn_log_03', 'furn_de_ex_stool_02', 'furn_de_p_stool_02')
CAMP_TABLES = ('furn_de_ex_table_03', 'furn_de_ex_table_02', 'furn_de_p_table_01', 'furn_de_p_table_04')
CAMP_GOODS = (('crate_bandit_01', 0.57), ('crate_smuggler_01', 0.3), ('barrel_bandit_01', 0.5), ('barrel_01_drinks', 0.3), ('com_chest_11_pos', 0.6),
              ('com_sack_02_gold_05', 0.38), ('com_sack_01_chpfood5', 0.3))
CAMP_TORCHES = ('light_tikitorch00', 'light_tikitorch128', 'light_tikitorch00_256')
CAMP_LANTERNS = ('light_de_lantern_06', 'light_de_lantern_06_128', 'light_de_candle_03_64')
CAMP_FOOD = ('misc_com_bottle_06', 'misc_com_bottle_05', 'potion_local_brew_01', 'ingred_bread_01', 'misc_com_wood_bowl_01')


CAMP_WHY = Counter()           # (why camp spots were refused, for the checks)


def _cave_camp(db, c, mine, sc, spots, npeople, rng):
    """A camp in a cave chamber laid the way the game's own are (CAMP_* above): beds along the rock, on a
    plank deck where the rock under one is uneven, now and then a fire out in the open with logs and stools
    round it, goods and torches by the walls, sometimes a table with food and a lantern. Everything has
    floor under all of it, room over it and keeps clear of the rest. Where the people stand, or None."""
    first = lambda ids: next((i for i in ids if db.resolve_id(i) is not None), None)
    resolve = lambda rid: (db.resolve_id(rid) is not None) and rid
    taken = []                                        # (x, y, radius) of what is laid

    def bounds(rid):
        return mapdata.object_bounds(db, db.resolve_id(rid)) or (0, 0, 0, 0, 0, 0)

    def wall_of(x, y, z):
        best = None
        for k in range(16):
            a = k * math.pi / 8
            h = sc.nearest_any((x, y, z + 50), (math.cos(a), math.sin(a), 0.0), 1200)
            if h is not None and (best is None or h[0] < best[0]):
                best = (h[0], a)
        return best

    def fits(rid, x, y, rz, need_flat, z0):
        """Floor under the footprint near z0 (spread at most need_flat), room over it, clear of what is laid."""
        b = bounds(rid)
        r = 0.5 * math.hypot(b[3] - b[0], b[4] - b[1])
        if any(math.hypot(x - tx, y - ty) < r + tr for tx, ty, tr in taken):
            CAMP_WHY['in the way of another'] += 1
            return None
        fl = []
        for fx in (-0.42, 0.0, 0.42):
            for fy in (-0.42, 0.0, 0.42):
                lx, ly = (b[0] + b[3]) / 2 + fx * (b[3] - b[0]), (b[1] + b[4]) / 2 + fy * (b[4] - b[1])
                wx, wy = _rot(lx, ly, rz)
                # (from 60 over the spot: from higher, under a low cave roof the ray began in the rock above)
                f = _floor_at(sc, x + wx, y + wy, z0)
                if f is None or abs(f - z0) > 100:
                    CAMP_WHY['no floor under all of it'] += 1
                    return None
                fl.append(f)
        if max(fl) - min(fl) > need_flat:
            CAMP_WHY['uneven'] += 1
            return None
        hgt = b[5] - b[2]
        for fx, fy in ((0.5, 0.5), (0.15, 0.15), (0.85, 0.85), (0.15, 0.85), (0.85, 0.15)):
            lx, ly = b[0] + (b[3] - b[0]) * fx, b[1] + (b[4] - b[1]) * fy
            wx, wy = _rot(lx, ly, rz)
            if sc.nearest_any((x + wx, y + wy, max(fl) + 4), (0.0, 0.0, 1.0), hgt + (60 if fx == 0.5 else 16)) is not None:
                CAMP_WHY['no room over it'] += 1
                return None
        # (not through the rock to the side: its own diagonals at waist height, pulled in a fifth)
        cs = []
        for lx, ly in ((b[0], b[1]), (b[3], b[4]), (b[0], b[4]), (b[3], b[1])):
            wx, wy = _rot(lx * 0.8, ly * 0.8, rz)
            cs.append((x + wx, y + wy))
        zc = max(fl) + max(10.0, hgt * 0.45)
        for (x0, y0), (x1, y1) in ((cs[0], cs[1]), (cs[2], cs[3])):
            L = math.hypot(x1 - x0, y1 - y0)
            if L > 8 and sc.nearest_any((x0, y0, zc), ((x1 - x0) / L, (y1 - y0) / L, 0.0), L) is not None:
                CAMP_WHY['through the rock'] += 1
                return None
        return (min(fl), max(fl), r)

    laid_keys = []

    def put(rid, x, y, z, rz, r):
        laid_keys.append(_put_ref(db, c, mine, rid, x, y, 0.0, 0.0, 0.0, z, rz))
        taken.append((x, y, r))

    # where the walls are: each floor spot with how far the rock is, and which way
    rich = []
    for x, y, z in spots[:160]:
        w = wall_of(x, y, z)
        if w:
            rich.append((x, y, z, w[0], w[1]))
    if not rich:
        return None
    by_wall = [s for s in rich if 90 <= s[3] <= 320]
    open_ = sorted([s for s in rich if s[3] >= 220], key=lambda s: -s[3])
    rng.shuffle(by_wall)
    # the fire, out in the open (most of the game's camps have none; a camp with people more often does)
    fire_at = None
    fire = rng.choice([f for f in CAMP_FIRES if resolve(f)] or [None])
    if fire and open_ and rng.random() < 0.6:
        for x, y, z, _d, _a in open_[:12]:
            got = fits(fire, x, y, 0.0, 40, z)
            if got:
                put(fire, x, y, got[0], rng.random() * 6.28, got[2] + 60)
                fire_at = (x, y, got[0])
                break
    # the beds against the rock, head to it; on a deck where the rock under one is uneven
    beds = [b for b, _w in CAMP_BEDS if resolve(b)]
    weights = [w for b, w in CAMP_BEDS if resolve(b)]
    deck = resolve('ex_common_plat_lrg')
    nbeds = max(1, npeople)
    centre = fire_at or (sum(s[0] for s in rich) / len(rich), sum(s[1] for s in rich) / len(rich), rich[0][2])
    cand = sorted(by_wall, key=lambda s: abs(math.hypot(s[0] - centre[0], s[1] - centre[1]) - 330))
    # (then anywhere else, the bed still head to the nearest rock)
    cand += sorted([s for s in rich if s not in by_wall], key=lambda s: s[3])
    laid_beds = []
    for x, y, z, d, a in cand:
        if len(laid_beds) >= nbeds or not beds:
            break
        bid = rng.choices(beds, weights)[0]
        b = bounds(bid)
        long_x = (b[3] - b[0]) >= (b[4] - b[1])
        L = max(b[3] - b[0], b[4] - b[1])
        rz = (-a if long_x else math.pi / 2 - a) % (2 * math.pi)
        # (its head a hand from the rock)
        shift = max(0.0, d - L / 2 - 25)
        bx, by = x + math.cos(a) * shift, y + math.sin(a) * shift
        got = fits(bid, bx, by, rz, 24, z)
        if got:
            bz = (got[0] + got[1]) / 2               # (halfway: never buried on the high side)
            put(bid, bx, by, bz, rz, got[2])
            laid_beds.append((bx, by, bz))
            continue
        if deck:
            # (the deck back from the rock along the same line, the bed at its end by the wall)
            db_ = bounds(deck)
            Ld = max(db_[3] - db_[0], db_[4] - db_[1])
            rzd = (-a if (db_[3] - db_[0]) >= (db_[4] - db_[1]) else math.pi / 2 - a) % (2 * math.pi)
            sd = max(0.0, d - Ld / 2 - 10)
            px_, py_ = x + math.cos(a) * sd, y + math.sin(a) * sd
            got = fits(deck, px_, py_, rzd, 60, z)
            if got:
                # (half into the high rock, at most 30 over the low: as the game sets its decks on rough rock)
                dz = (got[0] + got[1]) / 2
                put(deck, px_, py_, dz, rzd, got[2])
                off = max(0.0, Ld / 2 - L / 2 - 20)
                bx, by = px_ + math.cos(a) * off, py_ + math.sin(a) * off
                put(bid, bx, by, dz + (db_[5] - db_[2]), rz, 0)
                laid_beds.append((bx, by, dz + (db_[5] - db_[2])))
    if not laid_beds:
        for k_ in laid_keys:                          # (no bed anywhere: nothing of the camp left behind)
            c['refs'].pop(k_, None)
        return None
    # round the fire, logs and stools facing it
    if fire_at:
        seats = [s for s in CAMP_SEATS if resolve(s)]
        for k in range(rng.choice([2, 2, 3, 4])):
            if not seats:
                break
            a = k * 2 * math.pi / 4 + rng.random() * 0.6
            sx, sy = fire_at[0] + math.cos(a) * 110, fire_at[1] + math.sin(a) * 110
            sid = rng.choice(seats)
            got = fits(sid, sx, sy, -a + math.pi / 2, 30, fire_at[2])
            if got:
                put(sid, sx, sy, got[0], -a + math.pi / 2, got[2] * 0.6)
        cook = [x for x in ('furn_com_cauldron_01', 'furn_de_minercave_grill_01', 't_com_var_souppot_01') if resolve(x)]
        if cook and rng.random() < 0.35:
            _put_ref(db, c, mine, rng.choice(cook), fire_at[0], fire_at[1], 0.0, 0.0, 0.0, fire_at[2], rng.random() * 6.28)
    # goods, a table and lights by the walls
    rest = [s for s in by_wall if all(math.hypot(s[0] - tx, s[1] - ty) > 60 for tx, ty, _r in taken)]
    wants = [g for g, p in CAMP_GOODS if resolve(g) and rng.random() < p]
    if not wants:
        wants = [first([g for g, _p in CAMP_GOODS])] if first([g for g, _p in CAMP_GOODS]) else []
    table = first(CAMP_TABLES) if rng.random() < 0.42 else None
    torch = first(CAMP_TORCHES) if rng.random() < 0.6 else None
    order = ([table] if table else []) + wants + ([torch] if torch else [])
    lantern = first(CAMP_LANTERNS)
    for rid in order:
        for x, y, z, d, a in rest:
            b = bounds(rid)
            depth = min(b[3] - b[0], b[4] - b[1])
            shift = max(0.0, d - depth / 2 - 20)
            gx, gy = x + math.cos(a) * shift, y + math.sin(a) * shift
            rz = (-a + math.pi / 2) % (2 * math.pi) if rid == table else rng.random() * 0.4 - a
            got = fits(rid, gx, gy, rz, 20, z)
            if got:
                put(rid, gx, gy, got[0], rz, got[2])
                if rid == table:
                    top = got[0] - b[2] + b[5]
                    things = ([lantern] if lantern else []) + rng.sample([f for f in CAMP_FOOD if resolve(f)], min(3, len([f for f in CAMP_FOOD if resolve(f)])))
                    for k, t in enumerate(things):
                        ox, oy = _rot(((k % 2) - 0.5) * 0.5 * (b[3] - b[0]), ((k // 2) - 0.5) * 0.4 * (b[4] - b[1]), rz)
                        _put_ref(db, c, mine, t, gx + ox, gy + oy, 0.0, 0.0, 0.0, top, rng.random() * 6.28)
                break
    # where the people stand: round the fire, or by their beds
    if fire_at:
        return [(fire_at[0] + math.cos(k * 2.1) * 160, fire_at[1] + math.sin(k * 2.1) * 160, fire_at[2]) for k in range(max(1, npeople))]
    return [(bx + 60, by + 60, bz) for bx, by, bz in laid_beds]


def occupy(db, key, lay, rng, occupants='auto', K=None):
    """People in the place, as the game's own of the kind have them (in Dwemer ruins smugglers, warriors,
    barbarians, savants and their slaves; nobody, 53% of the time when left to chance). Lived in is a
    density (the user: "0 is no inhabitants and at max expect to find campers and bandits in each major
    cove"): up to the kind's own share it is the chance of one camp, as the game's; over it, one camp for
    sure and each other hall or chamber (not the last) a camp of its own as often as the slider is past the
    game's, every one of them at the top. The people placed, or 0."""
    K = K or kit('dwemer')
    v, g = lived_share(occupants, K), lived_share('auto', K)
    if K.get('household'):
        # (lived in or not, as the slider says; lived in, a household, not camps)
        return _household(db, key, lay, rng, K) if rng.random() < v else 0
    halls = sorted({p['hall'] for p in lay['pieces'] if p.get('hall') is not None and not p.get('gone')} - {lay['final']})
    if v <= g:
        camps = 1 if rng.random() < v else 0
    else:
        extra = (v - g) / max(1e-6, 1.0 - g)
        camps = 1 + sum(1 for _h in halls[1:] if rng.random() < extra)
    placed = 0
    used = set()
    for k in range(camps):
        free = [h for h in halls if h not in used]
        if not free and k:
            break
        hall = rng.choice(free) if free else lay['final']
        if hall is None:
            break
        used.add(hall)
        placed += _one_camp(db, key, lay, rng, K, hall, free if k == 0 else [hall], tunnels=(k == 0))
    return placed


FIREPIT = re.compile(r'firepit|fire_pit|pitfire')
PILLAR = re.compile(r'pill|column|_post')


def _firepits(db, key):
    """Fire pits: one cutting into a pillar or column goes, and of two within FIRE_APART of each other the second goes
    (two tiles' dressings each brought theirs: the user's stronghold had two side by side against its pillars). The
    number taken out."""
    c = db.project.cells.get(key)
    if not c:
        return 0
    m = mapdata.cellmap(db, key)
    fires = [r for r in m['refs'] if r.get('b') and FIREPIT.search(r['id'].lower())]
    if not fires:
        return 0
    shrink = lambda a: (lambda sx, sy: (a[0] + sx, a[1] + sy, a[2], a[3] - sx, a[4] - sy, a[5]))((a[3] - a[0]) / 6, (a[4] - a[1]) / 6)
    posts = [shrink(_aabb(r)) for r in m['refs'] if r.get('b') and PILLAR.search(r['id'].lower()) and not FIREPIT.search(r['id'].lower())]
    hit = lambda a, b: min(a[3], b[3]) > max(a[0], b[0]) and min(a[4], b[4]) > max(a[1], b[1]) and min(a[5], b[5]) > max(a[2], b[2])
    kept, gone = [], []
    for r in fires:
        a = shrink(_aabb(r))
        if any(hit(a, p) for p in posts) or any(math.hypot(r['p'][0] - k['p'][0], r['p'][1] - k['p'][1]) < FIRE_APART and abs(r['p'][2] - k['p'][2]) < 200 for k in kept):
            gone.append(r)
        else:
            kept.append(r)
    for r in gone:
        c['refs'].pop(r['k'], None)
    if gone:
        db.sync_project()
    return len(gone)


FIRE_APART = 600
WALL_FURN = re.compile(r'bookshelf|bookcase|shelf|drawers|cupboard|wardrobe|closet|wallscreen')


def _unbacked(db, key, K):
    """Shelves, drawers and cupboards with no wall of the place within reach on any side, taken out with what is on
    them: a dressing copied from a game place where something it doesn't bring stood behind them (a Velothi tower's pit
    came with a library of six free-standing bookshelves, 12 books cut into them, the game's own towers 0). The
    number taken out."""
    import placecheck
    c = db.project.cells.get(key)
    if not c:
        return 0
    m = mapdata.cellmap(db, key)
    # (as the place check finds them: a shelf with no wall at its back, a book cut into its shelf. Rays of their own
    # met a step or a column beside the shelf and kept most of them)
    res = placecheck.check(db, key, gaps=False)
    by_k = {r['k']: r for r in m['refs']}
    gone = [by_k[i['ref']] for i in res.get('issues') or [] if i.get('kind') == 'nowall' and i.get('ref') in by_k
            and WALL_FURN.search(by_k[i['ref']]['id'].lower()) and by_k[i['ref']].get('b')]
    for i in res.get('issues') or []:
        if i.get('kind') == 'bookclip' and i.get('ref') in c['refs']:
            c['refs'].pop(i['ref'], None)
    for r in gone:
        b, s = r['b'], r.get('s') or 1.0
        top = r['p'][2] + b[5] * s
        # (and what stands on it: its books and jars, inside its box and no higher than its top)
        for o in m['refs']:
            if o is r or o['type'] not in TOP_TYPES:
                continue
            lx, ly = _rot(o['p'][0] - r['p'][0], o['p'][1] - r['p'][1], -r['p'][5])
            if b[0] * s - 8 <= lx <= b[3] * s + 8 and b[1] * s - 8 <= ly <= b[4] * s + 8 and r['p'][2] + b[2] * s - 8 <= o['p'][2] <= top + 24:
                c['refs'].pop(o['k'], None)
        c['refs'].pop(r['k'], None)
    if gone:
        db.sync_project()
    return len(gone)


def _household(db, key, lay, rng, K):
    """A kind's people who live there rather than camp (K['household']: a Velothi tower's mage and company): a cast
    from Populate for the kind's setting, as many as the game's own of the size hold (its towers: 1, 3, 9 at the
    tenth, middle and ninetieth; 2 in a tiny one to 5 in a large one here), standing about the tower and its rooms
    among their own furniture, no camp. The people placed, or 0."""
    import populate
    import seethrough
    n = max(1, min(6, 2 + lay['tunnels'] // 25 + rng.choice([-1, 0, 0, 1])))
    cast = populate.cast(db, key, {'setting': K['setting'], 'count': n}, seed=rng.getrandbits(31))
    people = (cast.get('people') or [])[:n]
    if not people:
        return 0
    m = mapdata.cellmap(db, key)
    sc = seethrough.place_scene(db, m)
    halls = [lay['final']] + sorted({p['hall'] for p in lay['pieces'] if p.get('hall') is not None and not p.get('gone')} - {lay['final']})
    spots = []
    for h in halls:
        if h is None:
            continue
        sp = _hall_spots(db, sc, lay, h)
        if not sp:
            continue
        # (on a floor, not a table top: the room's lowest floor, or a storey up, not the furniture between)
        lo = min(s[2] for s in sp)
        spots.append([s for s in sp if s[2] - lo < 24 or s[2] - lo > 240])
    taken = []
    for k, pp in enumerate(people):
        # (half of them in the tower itself, the rest in its rooms in turn; a stride apart)
        pool = spots[0] if (k % 2 == 0 or len(spots) < 2) else spots[1 + (k // 2) % (len(spots) - 1)]
        pick = next((s for s in pool if all(math.hypot(s[0] - t[0], s[1] - t[1]) > 150 for t in taken)), None)
        if pick is None:
            continue
        taken.append(pick)
        pp['spot'] = [round(pick[0], 1), round(pick[1], 1), round(pick[2] + 4, 1), round(rng.random() * 6.28, 3)]
    people = [pp for pp in people if pp.get('spot')]
    if not people:
        return 0
    db.sync_project()
    r = populate.place(db, key, people, own=False, lived=True, band=cast.get('band') or '')
    return r.get('placed', 0)


def _one_camp(db, key, lay, rng, K, hall, halls, tunnels=True):
    """One camp and its people: a cast from Populate for the kind's setting, their camp in the hall (a cave's
    in the first of the halls with room, then its tunnels when tunnels), a bedroll each, a light, crates and
    a sack; they stand round it. The people placed, or 0."""
    import populate
    import seethrough
    m = mapdata.cellmap(db, key)
    sc = seethrough.place_scene(db, m)
    spots = _hall_spots(db, sc, lay, hall)
    if not spots:
        return 0
    if K.get('camp') == 'rooms':
        # (a band that lives in the rooms, as many as the game's places of the kind hold: its forts 5.1 a place over
        # 33 pieces; 2-4 in a small fort, 4-6 in a medium one, 7-8 in a large)
        # (a second band, when the slider asks for more than the game's share: a few more in another room)
        n = max(2, min(8, 2 + lay['tunnels'] // 12 + rng.choice([-1, 0, 0, 1]))) if tunnels else rng.choice([2, 2, 3])
    else:
        n = rng.choice([1, 1, 2, 2, 3, 3, 4])
    cast = populate.cast(db, key, {'setting': K['setting'], 'count': n}, seed=rng.getrandbits(31))
    people = (cast.get('people') or [])[:n]
    if not people:
        return 0
    if K.get('camp') == 'rooms':
        return _rooms_camp(db, key, lay, rng, K, sc, hall, halls, cast, people)
    c, _refs = editing._cell(db, key)
    p_ = db.project
    mine = p_.plugin.lower()
    # the camp, as Project Tamriel's stronghold guide has its bandits live: poor, round a firepit (a fire
    # pit with a log pile burning in it), a bedroll each, their gold in a sack and their goods in a bandit
    # crate, food in a sack; the first of each kind the load order has. The beds stand on plank decks laid
    # level over the rock, as the game's cave camps have them (a third of their beds stand on
    # ex_common_plat_lrg, the rest on bare rock), three to a deck; the fire on the rock beside
    if (K.get('kind') or '').startswith('cave'):
        # (the chamber picked first, then the others, until one has room for a bed against its rock)
        at = None
        # (last, the tunnels' own floor, hall None: the game camps in its tunnels too)
        for h_ in [hall] + rng.sample([x for x in halls if x != hall], len([x for x in halls if x != hall])) + ([None] if tunnels else []):
            sp = spots if h_ == hall else _hall_spots(db, sc, lay, h_)
            if not sp:
                continue
            _CAMP_SC[0], _CAMP_SC[1] = sc, sp[0][2]
            at = _cave_camp(db, c, mine, sc, sp, len(people), rng)
            if at is not None:
                break
        if at is None:
            return 0
        db.sync_project()
        _in_rock(db, key, K)                    # (the camp too: nothing of it through the rock)
        for k, pp in enumerate(people):
            x, y, z = at[k % len(at)]
            pp['spot'] = [round(x, 1), round(y, 1), round(z + 4, 1), round(rng.random() * 6.28, 3)]
        db.sync_project()
        # (and what they leave round their beds and fire, the game's own scenes of such a band: livedin.py)
        r = populate.place(db, key, people, own=False, lived=True, band=cast.get('band') or '')
        return r.get('placed', 0)
    first = lambda *ids: next((i for i in ids if db.resolve_id(i) is not None), None)
    # (no plank deck: a deck lays beds level over a cave's rock, and the floors here are level already; the
    # user: "This camp is built like the inside of a cave. Wooden platform on the floor. There's no need
    # for that in this type of dungeon", a Velothi tomb, 2026-10-25)
    bed, deck = first('active_de_bedroll', 'active_de_p_bed_28'), None
    ndeck = 1 if len(people) <= 2 else 2
    site = _camp_site(sc, spots, ndeck if deck else 0)
    if site is None and deck:
        deck = None                            # (nowhere near level enough for a deck: beds on the rock)
        site = _camp_site(sc, spots, 0)
    if site is None:
        return 0
    cx, cy, cz, q, top = site
    _CAMP_SC[0], _CAMP_SC[1] = sc, cz
    put = lambda rid, lx, ly, z, rz: _put_ref(db, c, mine, rid, cx, cy, q, lx, ly, z, rz)
    slots = []
    if deck:
        dz = top + 12                          # (the deck's underside on the highest rock under it)
        for d in range(ndeck):
            put(deck, d * 256, 0, dz, 0.0)
            slots += [(d * 256, y) for y in (-165, -55, 55)]
        surf = dz + 11
    else:
        surf = None
    for k, _pp in enumerate(people):
        if k < len(slots) and bed:
            lx, ly = slots[k]
            put(bed, lx, ly, surf, 0.0)
        elif bed:
            # (no deck: bedrolls on the rock round the fire)
            a = k * 2 * math.pi / max(1, len(people))
            put(bed, -330 + math.cos(a) * 170, math.sin(a) * 170, None, a)
    # their goods at the deck's far end, or by the fire
    goods = [first('crate_bandit_01', 'crate_01'), first('com_sack_02_gold_100', 'com_sack_01_chpfood5'), first('com_sack_01_chpfood5', 'crate_01')]
    for k, rid in enumerate(g for g in goods if g):
        if deck:
            put(rid, (ndeck - 1) * 256 + (-60 if k == 0 else 40), 185 + (0 if k == 0 else (k - 1) * 30), surf, rng.random() * 0.3)
        else:
            put(rid, -330 + 200, -120 + k * 70, None, rng.random() * 6.28)
    # the fire on the rock, settled at the lowest floor under it (never in the air on the low side): a camp
    # fire as the game's own dungeon camps have them (pit fires, the logs they sit on, now and then a
    # cauldron, a grill or a soup pot, bowls and bottles; the survey of 2026-10-24), not a masonry fire pit
    fires = [f for f in ('light_pitfire00', 'furn_de_firepit_f_323', 'furn_de_firepit_f', 'furn_de_firepit_f_200', 'furn_de_firepit_f_01', 'light_pitfire01')
             if db.resolve_id(f) is not None]
    fire = rng.choice(fires) if fires else first('light_logpile10', 'light_tikitorch256')
    if fire:
        put(fire, -330, 0, ('low', sc), rng.random() * 6.28)
    log = first('furn_log_01', 'furn_log_02')
    for k in range(rng.choice([1, 2, 2, 3])):
        if log:
            a = math.pi * 0.4 + k * math.pi * 0.6 + rng.random() * 0.3
            put(log, -330 + math.cos(a) * 110, math.sin(a) * 110, ('low', sc), a + math.pi / 2)
    extra = [x for x in ('furn_com_cauldron_01', 'furn_de_minercave_grill_01', 't_com_var_souppot_01') if db.resolve_id(x) is not None]
    if extra and rng.random() < 0.5:
        put(rng.choice(extra), -330, 0, ('low', sc), rng.random() * 6.28)
    for k, ware in enumerate(rng.sample([x for x in ('misc_com_wood_bowl_01', 'misc_com_bottle_01', 'misc_com_wood_cup_01', 'misc_com_bucket_01')
                                         if db.resolve_id(x) is not None], 2)):
        a = -math.pi * 0.6 + k * 0.5
        put(ware, -330 + math.cos(a) * 85, math.sin(a) * 85, ('low', sc), rng.random() * 6.28)
    for k, pp in enumerate(people):
        a = k * 2 * math.pi / max(1, len(people)) + rng.random() * 0.4
        wx, wy = _rot(-330 + math.cos(a) * 150, math.sin(a) * 150, q)
        fz = _floor_at(sc, cx + wx, cy + wy, cz + 40) or cz
        pp['spot'] = [round(cx + wx, 1), round(cy + wy, 1), round(fz + 4, 1), round(rng.random() * 6.28, 3)]
    db.sync_project()
    r = populate.place(db, key, people, own=False, lived=True, band=cast.get('band') or '')
    return r.get('placed', 0)


def _rooms_camp(db, key, lay, rng, K, sc, hall, halls, cast, people):
    """A band living in the rooms (K['camp'] == 'rooms': an Imperial fort's bandits): the people stand about the hall
    picked and the other rooms in turn, a stride apart, on the rooms' floors; no camp fire on the flagstones. What
    such a band leaves round its beds, and beds for those the rooms' own furniture doesn't give, come from the
    game's own camps of the band (livedin.lay_camps, with the kind's setting: the place's name reads as a guild's or a
    garrison's to castsurvey, and a fort of the game's holds no band to learn from, lab j_fortcast 2026-11-05).
    The people placed, or 0."""
    import populate
    import livedin
    pools = []
    for h_ in [hall] + [x for x in halls if x != hall] + [lay['final']]:
        if h_ is None or any(h_ == h for h, _s in pools):
            continue
        sp = _hall_spots(db, sc, lay, h_)
        if not sp:
            continue
        # (on a floor, not a table top: the room's lowest floor, or a storey up, not the furniture between)
        lo = min(s[2] for s in sp)
        sp = [s for s in sp if s[2] - lo < 24 or s[2] - lo > 240]
        if sp:
            pools.append((h_, sp))
    if not pools:
        return 0
    # (a stride from anyone already there: a second band stood on the first's spots)
    taken = [(r['p'][0], r['p'][1]) for r in mapdata.cellmap(db, key)['refs'] if r['type'] == 'NPC_']
    for k, pp in enumerate(people):
        pool = pools[k % len(pools)][1]
        pick = next((s for s in pool if all(math.hypot(s[0] - t[0], s[1] - t[1]) > 150 for t in taken)), None)
        if pick is None:
            pick = next((s for s in sum((p_[1] for p_ in pools), []) if all(math.hypot(s[0] - t[0], s[1] - t[1]) > 150 for t in taken)), None)
        if pick is None:
            continue
        taken.append(pick)
        pp['spot'] = [round(pick[0], 1), round(pick[1], 1), round(pick[2] + 4, 1), round(rng.random() * 6.28, 3)]
    people = [pp for pp in people if pp.get('spot')]
    if not people:
        return 0
    db.sync_project()
    band = cast.get('band') or ''
    r = populate.place(db, key, people, own=False, lived=False, band=band)
    try:
        livedin.apply(db, key, band=band, setting=K['setting'], seed=rng.getrandbits(31), camps=True, stories=True, commit=True)
    except Exception as ex:
        print('dungeon band lived in:', ex)
    return r.get('placed', 0)


def _write_refs(db, c, refs):
    """The refs written into the place's cell record; their ref keys, in order."""
    p = db.project
    mine = p.plugin.lower()
    keys = []
    for rid, pos, extra, scale in refs:
        subs = set_ref_pos([('NAME', zs(rid))], pos, round(scale, 3) if abs(scale - 1.0) > 0.005 else 1.0)
        if extra:
            out, put = [], False
            for t_, d_ in subs:
                if t_ == 'DATA' and not put:
                    out += extra
                    put = True
                out.append((t_, d_))
            subs = out
        nk = p.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), subs)
        keys.append(nk)
    return keys


def build(db, name, *a, **k):
    """_build, written into the places ledger (ledger.py): a dungeon of its own, or part of the keep or town being made."""
    import ledger
    with ledger.open(db, 'dungeon' if (k.get('kind') or 'dwemer') != 'fort' else 'interior', name, seed=k.get('seed'),
                     opts={'kind': k.get('kind') or 'dwemer'}):
        return _build(db, name, *a, **k)


def _build(db, name, size='medium', levels='some', twist='branching', loot='usual', creatures='usual',
           doors=0.12, entrance=None, outside_door=None, seed=None, commit=True, occupants='auto', kind='dwemer', water='none',
           entry_piece=None, final_hall=None, way='down', keep=None):
    """A new dungeon of the kind called name, laid out, dressed and written into the mod as a new place.
    entrance: {cell, x, y, z, rz} outside, for a door there that leads in (as Build from pieces does), or None.
    way: 'down' from the way in, or 'up' for a place that climbs (dgrules). keep: a keep interior's asks (generate):
    its doorways out besides the front door, spiral towers, big halls and trap doors; the doors made come back as
    'doors' [{kind: front|exit|trap, k: ref key, pos, arrive}], unlinked but the front one, for keepmaker to pair."""
    import builder
    K = kit(kind)
    editing._require_project(db)
    p = db.project
    name = (name or '').strip()
    if not name:
        raise EditError('Give the place a name, e.g. "%s".' % K['example'])
    if len(name.encode(ENC, 'replace')) > 63:
        raise EditError('Place names can be at most 63 characters.')
    key = name.lower()
    if any(v not in db.dead for v in db.by_key.get(('CELL', key), [])) or key in p.cells:
        raise EditError('There is already a place called "%s".' % name)
    S = ready(db, kind)
    if S is None:
        import learning
        return {'learning': learning.ruin_pending(db, kind)}
    # (the variant its seed draws, a tomb with the domed great room: the plan drew the same; the place keeps the kind
    # chosen, so Again draws anew)
    kind0 = kind
    if not keep:
        seed = int(seed) if seed not in (None, '') else random.getrandbits(31)
        kind = variant(db, kind, size, seed)
        if kind != kind0:
            K, S = kit(kind), ready(db, kind)
    lay = generate(db, size, levels, twist, seed, kind=kind, entry=entry_piece, final=final_hall, way=way, keep=keep)
    lay['K'] = K
    rng = random.Random(lay['seed'] * 7 + 1)
    refs = []
    for pc in lay['pieces']:
        if not pc.get('gone'):
            refs.append((pc['id'], tuple(pc['p']), [], 1.0))
    # (a Daedric room's roof over each tile the game roofs)
    tiles = S.get('tiles') or {}
    roof = next((r for r in ('in_dae_room_l_roof_03', 'in_dae_room_l_roof_01') if db.resolve_id(r) is not None), None)
    for pc in lay['pieces']:
        # (a kind with a ceiling of its own has it in its layout, _lay_room: Daedric roofs stood over Ayleid floors)
        if not pc.get('gone') and pc['id'] in tiles and roof and tiles[pc['id']].get('roof', 0) >= 0.5 and not K.get('roof'):
            refs.append((roof, tuple(pc['p']), [], 1.0))
    D = S.get('door') or {}
    if kind == 'dwemer':
        jamb_dz, jamb_turn = 0, 0.0
        inner = (K['inner_door'], D.get('inner') or [])
        load = {'id': K['load_door'], 'holder': K['jamb'], 'pose': [0, 0, -32, 0]}
    else:
        jd = D.get('jamb') or {}
        jamb_dz, jamb_turn = jd.get('dz', 0), math.radians(jd.get('turn', 0))
        inner = tuple(D['inner']) if D.get('inner') else (None, [])
        load = D.get('load') or {}
    # door frames with their doors at some seams between tunnels (as often as the game has them: 574 frames
    # for its 5,000-odd Dwemer pieces), never inside a hall
    if K.get('jamb') and inner[0] and db.resolve_id(K['jamb']) is not None:
        # (a door only where the way on beyond it reaches a hall, chamber or room: one into a stub of tunnel
        # that only ends was "a door in a doorway leading nowhere", the user's Varensis Tomb)
        kids = defaultdict(list)
        for s_ in lay['seams']:
            kids[s_[4]].append(s_[5])
        _reach = {}

        def leads_on(n, depth=0):
            if n in _reach:
                return _reach[n]
            pc = lay['pieces'][n]
            _reach[n] = False
            ok = not pc.get('gone') and (pc.get('hall') is not None or (depth < 200 and any(leads_on(k, depth + 1) for k in kids[n])))
            _reach[n] = ok
            return ok
        # (and only where it is the one way between its two sides: a door you can walk round, by a loop of
        # tunnels or through a room with two ways out, is "a little silly", the user. A hall or a room is one
        # place; a join is a door's when taking it away cuts the place in two)
        node = lambda n: ('h', lay['pieces'][n]['hall']) if lay['pieces'][n].get('hall') is not None else n
        links = defaultdict(list)
        for k_, s_ in enumerate(lay['seams']):
            if lay['pieces'][s_[4]].get('gone') or lay['pieces'][s_[5]].get('gone'):
                continue
            u_, v_ = node(s_[4]), node(s_[5])
            links[u_].append((v_, k_))
            links[v_].append((u_, k_))

        def only_way(k_):
            s_ = lay['seams'][k_]
            u_, v_ = node(s_[4]), node(s_[5])
            seen_, todo_ = {u_}, [u_]
            while todo_:
                w_ = todo_.pop()
                for x_, kk_ in links[w_]:
                    if kk_ == k_ or x_ in seen_:
                        continue
                    if x_ == v_:
                        return False
                    seen_.add(x_)
                    todo_.append(x_)
            return True
        framed = set(K.get('framed') or ())
        for n_, pc in enumerate(lay['pieces']):
            if pc.get('gone') or pc.get('id') not in framed:
                continue
            # (a keep's short passage: its frame in the middle of it, as the game's stand (44 of the 83 by a T; at
            # its ends they cut into the T's alcove), with a door when it leads into a room)
            x_, y_, z_, rz_ = pc['p'][0], pc['p'][1], pc['p'][2], pc['p'][5]
            refs.append((K['jamb'], (x_, y_, z_, 0, 0, rz_), [], 1.0))
            if any(n_ in (s_[4], s_[5]) and lay['pieces'][s_[5] if s_[4] == n_ else s_[4]].get('hall') is not None for s_ in lay['seams']):
                for lx, ly, lz, dq in inner[1]:
                    wx, wy = _rot(lx, ly, rz_)
                    refs.append((inner[0], (x_ + wx, y_ + wy, z_ + lz, 0, 0, (rz_ + math.radians(dq)) % (2 * math.pi)), [], 1.0))
        for k_seam, (sx, sy, sz, side, a, b) in enumerate(lay['seams']):
            A, B = lay['pieces'][a], lay['pieces'][b]
            if framed and (A.get('id') in framed or B.get('id') in framed):
                continue
            if not leads_on(b) or not only_way(k_seam):
                continue
            if A.get('gone') or B.get('gone') or A['hall'] is not None or B['hall'] is not None:
                continue
            # (nor in front of a dead end: a door that opens on a blank wall, the user's Varensis Tomb; nor pressed
            # up against a stair or a ramp, the user's Nchuddy, 2026-10-25)
            if A['id'] == K.get('dead_end') or B['id'] == K.get('dead_end') or 'dead end' in (A.get('role'), B.get('role')) \
                    or 'ramp' in (A.get('role'), B.get('role')):
                continue
            if rng.random() >= doors:
                continue
            jr = (YAW[side] + jamb_turn) % (2 * math.pi)
            refs.append((K['jamb'], (sx, sy, sz + jamb_dz, 0, 0, jr), [], 1.0))
            for lx, ly, lz, dq in inner[1]:
                wx, wy = _rot(lx, ly, jr)
                refs.append((inner[0], (sx + wx, sy + wy, sz + jamb_dz + lz, 0, 0, (jr + math.radians(dq)) % (2 * math.pi)), [], 1.0))
    # the front door: in a frame at the first piece's open end, or in the kind's own entrance piece
    e = lay['entrance']
    leaves = []
    lid = load.get('id') or K.get('load_door')
    pose = load.get('pose') or [0, 0, 0, 0]
    if e and 'piece' in e:
        hp = lay['pieces'][e['piece']]
        F = (hp['p'][0], hp['p'][1], hp['p'][2], hp['p'][5])
        # (out: away from the entrance piece's way on)
        on = _Layout(db, S, K).ports_of(hp['id'], *F)
        dx, dy = SIDES[OPP[on[0]['side']]] if on else (0, -1)
    elif load.get('holder') and load['holder'] != K.get('jamb') and (load.get('at') or load.get('in')) \
            and db.resolve_id(load['holder']) is not None and (not load.get('in') or (S['ports'].get(load['in'][0]) and db.resolve_id(load['in'][0]) is not None)):
        # (the kind's own front door frame: inside a dead end laid on the open end, as the game's Daedric
        # ones stand, or at the open end itself)
        if load.get('in'):
            own, (hx, hy, hz, hq) = load['in']
            px, py, pz, ps = S['ports'][own][0]
            q = next(q for q in range(4) if _dir_of(*_rot(*SIDES[ps], q * math.pi / 2)) == OPP[e['side']])
            orz = q * math.pi / 2
            ox, oy = _rot(px, py, orz)
            O = (e['x'] - ox, e['y'] - oy, e['z'] - pz, orz)
            refs.append((own, (O[0], O[1], O[2], 0, 0, orz), [], 1.0))
        else:
            hx, hy, hz, hq = load['at']
            O = (e['x'], e['y'], e['z'], YAW[e['side']])
        wx, wy = _rot(hx, hy, O[3])
        jr = (O[3] + math.radians(hq)) % (2 * math.pi)
        F = (O[0] + wx, O[1] + wy, O[2] + hz, jr)
        refs.append((load['holder'], (F[0], F[1], F[2], 0, 0, jr), [], 1.0))
        dx, dy = SIDES[e['side']]
    elif load.get('bare'):
        # (a front door that stands in the opening itself, no frame: an Ayleid ruin's stone door)
        F = (e['x'], e['y'], e['z'], YAW[e['side']])
        dx, dy = SIDES[e['side']]
    else:
        jr = (YAW[e['side']] + jamb_turn) % (2 * math.pi)
        refs.append((K['jamb'], (e['x'], e['y'], e['z'] + jamb_dz, 0, 0, jr), [], 1.0))
        F = (e['x'], e['y'], e['z'] + jamb_dz, jr)
        dx, dy = SIDES[e['side']]
    wx, wy = _rot(pose[0], pose[1], F[3])
    door_pos = [F[0] + wx, F[1] + wy, F[2] + pose[2]]
    drot = (F[3] + math.radians(pose[3])) % (2 * math.pi)
    ld = db.resolve_id(lid) if lid else None
    if ld is None:
        raise EditError('The front door "%s" is not in the load order.' % lid)
    if kind == 'dwemer':
        drot = builder._facing(db, ld, (-dx, -dy), F[3])
    # (a double door's other leaves: each goes to the same place)
    for did, lp in (load.get('leaves') or [])[1:]:
        if db.resolve_id(did) is None:
            continue
        lx_, ly_ = _rot(lp[0], lp[1], F[3])
        leaves.append((did, (F[0] + lx_, F[1] + ly_, F[2] + lp[2], 0, 0, (F[3] + math.radians(lp[3])) % (2 * math.pi))))
    arrive = [door_pos[0] - dx * 160, door_pos[1] - dy * 160, door_pos[2] - (100 if kind == 'dwemer' else -16), 0, 0, YAW[_dir_of(-dx, -dy)]]
    if load.get('bare'):
        arrive[2] = F[2] + 16                   # (the door's own point is at its middle: the arrival over the floor)
    door_extra = []
    out_spot = None
    if entrance and entrance.get('cell'):
        import create
        ex_, ey_ = float(entrance['x']), float(entrance['y'])
        if entrance.get('z') is None:
            em = mapdata.cellmap(db, entrance['cell'])
            if not em.get('exists'):
                raise EditError('There is no place at the chosen entrance spot.')
            ez_ = mapdata.surface_z(db, em['refs'], em['interior'], ex_, ey_, None, 1.0, 'DOOR')
        else:
            ez_ = float(entrance['z'])
        erz = float(entrance.get('rz') or 0)
        if not outside_door:
            choices = create.outside_doors(db, None, None)
            dw = next((c['id'] for c in choices if any(w in c['id'].lower() for w in K['outside'])), None)
            outside_door = dw or (choices[0]['id'] if choices else 'ex_dwrv_door00')
        if db.resolve_id(outside_door) is None:
            raise EditError('"%s" is not a door.' % outside_door)
        ox, oy = create._rot2(0, -128, erz)
        out_arrival = (ex_ + ox, ey_ + oy, ez_ + 16, 0, 0, (erz + math.pi) % (2 * math.pi))
        info = mapdata.cell_info(db, entrance['cell'])
        door_extra = [('DODT', struct.pack('<6f', *out_arrival))]
        if info and info['interior']:
            door_extra.append(('DNAM', zs(info['name'])))
        out_spot = (entrance['cell'], outside_door, (ex_, ey_, ez_, 0, 0, erz))
    door_ix = [('front', len(refs), list(door_pos), arrive)]
    refs.append((lid, (door_pos[0], door_pos[1], door_pos[2], 0, 0, drot), door_extra, 1.0))
    for did, pos in leaves:
        refs.append((did, pos, door_extra, 1.0))
    # a keep's other ways out (generate's exits): a frame and a load door at each, unlinked, as the front door stands
    for ex in (lay.get('exits') or []) if K.get('jamb') else []:
        jr2 = (YAW[ex['side']] + jamb_turn) % (2 * math.pi)
        F2 = (ex['x'], ex['y'], ex['z'] + jamb_dz, jr2)
        refs.append((K['jamb'], (F2[0], F2[1], F2[2], 0, 0, jr2), [], 1.0))
        wx, wy = _rot(pose[0], pose[1], jr2)
        dpos = [F2[0] + wx, F2[1] + wy, F2[2] + pose[2]]
        dx2, dy2 = SIDES[ex['side']]
        arr2 = [dpos[0] - dx2 * 160, dpos[1] - dy2 * 160, dpos[2] - (100 if kind == 'dwemer' else -16), 0, 0, YAW[_dir_of(-dx2, -dy2)]]
        door_ix.append(('exit', len(refs), dpos, arr2))
        refs.append((lid, (dpos[0], dpos[1], dpos[2], 0, 0, (jr2 + math.radians(pose[3])) % (2 * math.pi)), [], 1.0))
        for did, lp in (load.get('leaves') or [])[1:]:
            if db.resolve_id(did) is not None:
                lx_, ly_ = _rot(lp[0], lp[1], jr2)
                refs.append((did, (F2[0] + lx_, F2[1] + ly_, F2[2] + lp[2], 0, 0, (jr2 + math.radians(lp[3])) % (2 * math.pi)), [], 1.0))
    # (and the trap door to the roof at the top of each spiral tower, when asked for: a tower crown's hatch leads to it)
    if (keep or {}).get('traps'):
        for pc in lay['pieces']:
            t_ = pc.get('trap')
            if pc.get('gone') or not t_ or db.resolve_id(t_[0]) is None:
                continue
            arr3 = [t_[1], t_[2], t_[3] - 112, 0, 0, t_[4]]
            door_ix.append(('trap', len(refs), [t_[1], t_[2], t_[3]], arr3))
            refs.append((t_[0], (t_[1], t_[2], t_[3], 0, 0, t_[4]), [], 1.0))
    # what's in it
    lay['role'] = (keep or {}).get('role')
    refs += _dress_refs(db, S, lay, rng, loot, creatures, K)
    # the last hall's prize: the kind's best chest by its far wall, with a guardian
    prize = []
    if lay['final'] is not None:
        hp = [pc for pc in lay['pieces'] if pc.get('hall') == lay['final'] and not pc.get('gone')]
        mid = [pc for pc in hp if pc['id'] == 'in_dwrv_hall4_00'] or hp
        if mid:
            c0 = mid[len(mid) // 2]
            cz = c0['p'][2] - 96
            for lst, off in zip(K['prize'], (0, 160)):
                rid = next((r for r in lst if db.resolve_id(r) is not None), None)
                if not rid:
                    continue
                if kind == 'dwemer':
                    refs.append((rid, (c0['p'][0] + off, c0['p'][1], cz, 0, 0, rng.random() * 6.28), [], 1.0))
                else:
                    # (set down on the chamber's real floor once the place is written: its box's bottom can
                    # be under the rock, where the user's Gold Grotto had its chest)
                    prize.append((rid, c0, off, rng.random() * 6.28))
    # ---- write the new place: dark and dusty like the game's own
    amb = (S.get('ambi') or [None])
    a0 = rng.choice(amb) if amb and amb[0] else None
    rgb = lambda c: c[0] | (c[1] << 8) | (c[2] << 16)
    if a0 and isinstance(a0, dict):
        ambi = struct.pack('<IIIf', rgb(a0['ambient']), rgb(a0['sunlight']), rgb(a0['fog']), float(a0.get('density', 1.0)))
    else:
        ambi = struct.pack('<IIIf', rgb(K['ambi'][0]), rgb(K['ambi'][1]), rgb(K['ambi'][2]), 1.0)
    header = [['NAME', b64(zs(name))], ['DATA', b64(struct.pack('<Iii', 1, 0, 0))], ['AMBI', b64(ambi)]]
    c = p.cells[key] = {'flags': 0, 'header': header, 'refs': {}}
    ref_keys = _write_refs(db, c, refs)
    made_doors = [{'kind': k_, 'k': ref_keys[i_], 'pos': [round(v, 1) for v in pos_], 'arrive': arr_} for k_, i_, pos_, arr_ in door_ix]
    db.sync_project()
    if kind != 'dwemer':
        # (where the floor really is by the front door: the arrival spot stands on it)
        try:
            import seethrough
            sc = seethrough.place_scene(db, mapdata.cellmap(db, key))
            fz = _floor_at(sc, arrive[0], arrive[1], door_pos[2] - 20)
            if fz is not None:
                arrive[2] = fz + 16
            for d_ in made_doors[1:]:
                fz = _floor_at(sc, d_['arrive'][0], d_['arrive'][1], d_['pos'][2] - 20)
                if fz is not None:
                    d_['arrive'][2] = fz + 16
            # the prize on the floor of the last chamber: the first spot near its middle with floor and a
            # ceiling over it (looked for from part way up the chamber, down)
            # (a Daedric ruin's last room: one of the game's own shrines, statue, platform, offerings, cursed
            # gems and all; its own chest instead of the prize chest)
            lay['K'] = K
            if S.get('shrines') and lay['final'] is not None and _shrine(db, c, S, lay, rng, key):
                prize = [pz for pz in prize if not re.search(r'chest', pz[0])]
            put = []
            for rid, c0, off, rz in prize:
                b = c0.get('box') or (c0['p'][0] - 200, c0['p'][1] - 200, c0['p'][2] - 200, c0['p'][0] + 200, c0['p'][1] + 200, c0['p'][2] + 400)
                mx, my = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
                spot = None
                for dx, dy in ((0, 0), (128, 0), (-128, 0), (0, 128), (0, -128), (256, 0), (-256, 0), (0, 256), (0, -256)):
                    for f in (0.35, 0.55, 0.75):
                        top = b[2] + (b[5] - b[2]) * f
                        dn = sc.nearest_any((mx + dx + off, my + dy, top), (0.0, 0.0, -1.0), b[5] - b[2])
                        up = sc.nearest_any((mx + dx + off, my + dy, top), (0.0, 0.0, 1.0), b[5] - b[2] + 400)
                        if dn is not None and up is not None and dn[0] > 4 and up[0] > 100:
                            spot = (mx + dx + off, my + dy, top - dn[0])
                            break
                    if spot:
                        break
                if spot:
                    ob = mapdata.object_bounds(db, db.resolve_id(rid))
                    put.append((rid, (spot[0], spot[1], spot[2] - (ob[2] if ob else 0), 0, 0, rz), [], 1.0))
            if put:
                _write_refs(db, c, put)
                db.sync_project()
        except Exception as ex:
            print('dungeon arrival floor:', ex)
    water_at = None
    try:
        # (_clear_ways, the straight lines through each piece, took out more than stood in the way: the walk does)
        lay.update(S=S, K=K, arrive=arrive)
        water_at = _water(db, key, lay, K, water, rng)
        lay['water_at'] = water_at
        _upright(db, key)
        cleared = _clear_ways(db, key, lay, S, K)
        # (and under the water, the whole height of every flooded way: the player swims there)
        cleared += _clear_swim(db, key, lay, S, K, water_at)
        cleared += _unblock(db, key, lay, K, _walk_starts(db, lay))
        cleared += _door_fronts(db, key, K)
        cleared += _declip(db, key, K)
        cleared += _in_rock(db, key, K)
        cleared += _floaters(db, key)
        # (fittings with nothing at all within PIPE_ALONE: a length of pipe hung in the middle of a corridor, the
        # user's Nchudjak. Not a contact rule: those called a fifth to a third of the game's own hanging. A
        # length that meets the corridor beside a room from outside still wants a show-through rule)
        cleared += _loose_pipes(db, key, K)
        cleared += _firepits(db, key)
        if K.get('household') or K.get('unbacked'):
            cleared += _unbacked(db, key, K)        # (a tower's or a keep's shelves with nothing behind them)
        if K.get('tidy'):
            cleared += _keep_tidy(db, key, K)       # (a hanging with no wall behind it, a rug not on its floor)
        # (last, after everything taken out of the way: what stood on a plank that went comes down to the floor)
        _settle(db, key, K)
        _orphans(db, key, K)
    except Exception as ex:
        cleared = 0
        print('dungeon ways through:', ex)
    tables_set = 0
    try:
        tables_set = _lay_tops(db, key, S, rng, loot)
    except Exception as ex:
        print('dungeon table tops:', ex)
    # (a cave chamber still showing the void after the tidying: closed with the game's own big rocks for it;
    # its own dice, so the rest of the place comes out as before)
    closed = 0
    if K['kind'].startswith('cave'):
        try:
            closed = _close_chambers(db, key, lay, S, K, random.Random(lay['seed'] * 13 + 5))
        except Exception as ex:
            print('dungeon chamber rock:', ex)
    if out_spot:
        oc, _r = editing._cell(db, out_spot[0])
        dsubs = set_ref_pos([('NAME', zs(out_spot[1]))], out_spot[2], 1.0)
        out = []
        put = False
        for t_, d_ in dsubs:
            if t_ == 'DATA' and not put:
                out += [('DODT', struct.pack('<6f', *arrive)), ('DNAM', zs(name))]
                put = True
            out.append((t_, d_))
        nk = p.new_ref_key()
        mine = p.plugin.lower()
        editing._store(oc, nk, mine, int(nk.rsplit('|', 1)[1]), out)
        c['ruin_outside'] = [out_spot[0], nk]
    c['ruin'] = {'kind': kind0, 'variant': kind if kind != kind0 else None, 'water': water, 'size': size, 'levels': levels, 'twist': twist, 'loot': loot, 'creatures': creatures, 'seed': lay['seed'],
                 'entrance': entrance, 'outside_door': outside_door, 'occupants': occupants, 'way': lay.get('way', 'down')}
    if keep:
        c['ruin']['keep'] = dict(keep)
    if lay.get('rooms_plan'):
        c['ruin']['rooms'] = lay['rooms_plan']
    # (the way in and the way it leads, in the place's own coordinates: where the place lies in a keep is told from it)
    e_ = lay.get('entrance') if isinstance(lay.get('entrance'), dict) else {}
    if e_.get('side') in SIDES:
        c['ruin']['frame'] = [round(float(e_['x']), 1), round(float(e_['y']), 1), round(float(e_.get('z', 0.0)), 1), SIDES[OPP[e_['side']]][0], SIDES[OPP[e_['side']]][1]]
    db.sync_project()
    note = 'Made a %s "%s" (%d tunnel pieces, %d %s)%s' % (
        K['label'][0].lower() + K['label'][1:] if not K['label'].startswith(('Dwemer', 'Velothi', 'Daedric', 'Chimer')) else K['label'], name,
        lay['tunnels'], lay['halls'], {'dwemer': 'halls', 'tiled': 'rooms'}.get(K['halls'], 'chambers'),
        (' with its entrance in %s' % editing.cell_label(db, out_spot[0])) if out_spot else '')
    stack = getattr(p, 'undo_stack', [])
    n0 = len(stack)
    editing.commit(db, note)
    # its walking paths and its people, folded into the same change (one Undo takes the whole place back)
    try:
        lay['S'] = S
        lay['arrive'] = arrive
        ruin_paths(db, key, lay)
        db.sync_project()
    except Exception as ex:
        print('dungeon walking paths:', ex)
    people = 0
    try:
        people = occupy(db, key, lay, rng, occupants, K)
    except Exception as ex:
        print('dungeon occupants:', ex)
    # (and why they are there: one story a place, its note and the goods that say the same on the band's leader,
    # dgstory.py; the night of 2026-11-12, "a reason to be there")
    story = None
    if people and not (keep or {}).get('nostories'):
        try:
            import dgstory
            story = dgstory.tell(db, key, seed=lay['seed'])
            if story:
                editing.commit(db, 'The story of "%s"' % name)
        except Exception as ex:
            print('dungeon story:', repr(ex))
    # (nobody living there: what happened there all the same, as the game's own of the kind tell it: a fallen
    # adventurer with his gear, bones, an offering, and the game's clutter round any fire or table the dressing
    # brought (livedin.py). Remains lie in 92% of the game's tombs and half its caves; made dungeons had an eighth
    # of the game's, the dungeon round of 2026-11-04. With people, populate.place lays them with their camp)
    if not people and not (keep or {}).get('nostories'):
        try:
            import livedin
            livedin.apply(db, key, band='', setting=K['setting'], seed=rng.getrandbits(31), camps=False, stories=True, commit=True)
        except Exception as ex:
            print('dungeon lived in:', ex)
    steps = len(getattr(p, 'undo_stack', [])) - n0
    if steps > 1:
        editing.fold(db, steps, note + (' and %d %s' % (people, 'person living in it' if people == 1 else 'people living in it') if people else ''))
    return {'key': key, 'name': name, 'machine_hall': lay.get('machines'), 'kind': kind0, 'variant': kind if kind != kind0 else None, 'seed': lay['seed'], 'tunnels': lay['tunnels'], 'halls': lay['halls'],
            'open_left': lay['open_left'], 'refs': len(refs), 'entrance': out_spot[0] if out_spot else None,
            'arrive': [round(v, 1) for v in arrive[:3]], 'people': people, 'final': lay['final'] is not None, 'cleared': cleared, 'water': water_at, 'tables_set': tables_set, 'closed': closed,
            'said': lay.get('said') or [], 'doors': made_doors, 'rings': lay.get('rings', 0), 'spirals': lay.get('spirals', 0),
            'story': {k_: story[k_] for k_ in ('band', 'why', 'leader_name', 'note', 'title')} if story else None,
            'lake': bool(lay.get('lake'))}
