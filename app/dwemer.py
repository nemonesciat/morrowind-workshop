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

V = 'v8'                                # (v8: the game's joins of each pair of pieces, 'rels'; v7: a thing goes to the piece whose floor is under it, no sets from scaled pieces; v6: table tops; v3: no grass in caves; v2: platforms kept under what stands on them, no copies of pieces that had a door)
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
SIZES = {'small': (16, 1), 'medium': (38, 2), 'large': (75, 3)}      # tunnel pieces, halls (the game's 20/49/96 pieces with their halls)
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
        'dress': r'^(furn_|dwrv_|ex_dwrv_pipe|in_dwe_pipe|sound_|light_|t_dwe_dngruin_f_|t_dwe_furn|active_)',
        'not_dress': r'boulder|rock|marker|mist|in_dwrv_(corr|hall|shaft|wall|doorjam)|door',
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
        'mix': {'ramp': 2.5, 'dead end': 0.25, 'cross': 0.5},
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
        'more': 'in_dae_all_lev+0', 'outside': ('dae',), 'example': 'Zaintashara, Shrine',
        'ambi': ((30, 40, 40), (10, 10, 10), (31, 44, 41))},
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
        'setting': 'cave', 'empty': 0.45, 'prize': [['chest_small_02_lev_gold', 'com_chest_02_lev_gold', 'crate_smuggler_01'], []],
        'more': None, 'outside': ('cave',), 'example': _ex, 'ambi': ((40, 36, 32), (50, 46, 40), (18, 16, 14))}
KINDS = ('dwemer', 'cave_mold', 'cave_mud', 'cave_py', 'cave_lava', 'tomb', 'daedric')

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
    return taste.cache_file('dungeon_%s_%s_%s' % (kind, taste.sig(db), VG))


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
    out = []
    for (tag, k), lst in db.by_key.items():
        if tag != 'CELL' or k.startswith('#') or not lst or lst[-1] in db.dead or not kits.game_made(db, k):
            continue
        try:
            refs, _h = db.cell_refs(k)
        except Exception:
            continue
        n = 0
        for r in refs.values():
            rid = (mapdata.ref_info(r['subs'])[0] or '').lower()
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
                     [(r['id'].lower(), r['p'][0], r['p'][1], r['p'][2], r['p'][5], bool(r.get('to'))) for r in m['refs'] if r['type'] == 'DOOR']))
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
        ports, agree = _learn_ports(obs, side_n, n_of, {K['base']: bp}, multi)
        score = sum(agree.get(a, 0) * n_of[a] for a in ports) / max(1, sum(n_of[a] for a in ports))
        if best is None or score > best[0]:
            best = (score, ports, agree)
    _score, ports, agree = best
    if kind == 'dwemer':
        # (the door survey of 2026-10-24: the game's front doors stand in a frame at (0, 0, -32), its inner
        # doors as a pair of leaves either side of its middle, 164 of 182 front doors, 463 of 519 inner ones)
        doors = {'jamb': {'dz': 0, 'turn': 0, 'n': 0}, 'inner': [K['inner_door'], [[112, 0, 0, 180], [-112, 0, 0, 0]]],
                 'load': {'id': K['load_door'], 'holder': K['jamb'], 'pose': [0, 0, -32, 0], 'n': 0}}
    else:
        doors = _learn_doors(K, ports, data, piece_b)
    # (and how the game stands each pair of pieces against each other: B in A's frame. A join the game never
    # makes, a corridor turned the other way round against a dead end, left a gap to the void beside it, the
    # user's Nchudzamn, 2026-10-25; such joins are refused while growing)
    rels = defaultdict(set)
    for aid, s_, bid, rel in obs:
        rels[aid + '|' + bid].add(tuple(rel[1:]))
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
    return {'dwemer': "the game's Dwemer ruins", 'tomb': "the game's Velothi tombs", 'daedric': "the game's Daedric ruins"}.get(
        kind, "the game's caves (%s)" % kit(kind)['label'].split('(')[-1].rstrip(')'))


def ready(db, kind='dwemer'):
    """The kind's survey if it is to hand (in memory or on disk); else None, with it started in the survey
    process (about 17 s for the Dwemer ruins, once per load order)."""
    K = kit(kind)
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
        pieces overlap at the join, a hall's exit piece over its corridor by 128)."""
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

    def place_at(self, pid, port_index, target, depth, hall=None):
        """pid laid so its opening port_index meets the open opening target; its other openings join the
        open list (or close a loop where they meet one). Returns the piece's index, or None when it doesn't fit."""
        px, py, pz, ps = self.S['ports'][pid][port_index]
        want = OPP[target['side']]
        for q in range(4):
            rz = q * math.pi / 2
            if _dir_of(*_rot(*SIDES[ps], rz)) != want:
                continue
            wx, wy = _rot(px, py, rz)
            x, y, z = target['x'] - wx, target['y'] - wy, target['z'] - pz
            if not self.game_joins(target['owner'], pid, x, y, z, rz):
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
            for o in new:
                self.open.append(dict(o, owner=n, depth=depth + 1, dz=sign(o['z'] - target['z'])))
            return n
        return None


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


def _lay_room(L, target, w, h, depth, hall_no, rng, tall=False):
    """A room of w x h tiles joined to the open opening target by the room's entry piece (a room's edge
    tile with the doorway in it), floor, side and corner tiles turned so their walls face out, a roof over
    every tile the game roofs; all of one height (tall: a Velothi tomb's two-storey rooms). True when it
    fits. Daedric rooms are of 512 tiles, Velothi ones of 256."""
    K, S = L.K, L.S
    eids = [e for e in _entries(K) if S['ports'].get(e) and _tall(K, e) == tall and L.db.resolve_id(e) is not None
            and S.get('agree', {}).get(e, 0) >= AGREE]
    if not eids:
        return False
    eid = max(eids, key=lambda e: S['n'].get(e, 0) * (0.6 + rng.random()))
    ent = [k for k, p in enumerate(S['ports'].get(eid, []))]
    tiles = S.get('tiles') or {}
    by_walls = defaultdict(list)
    for tid, rec in tiles.items():
        if L.db.resolve_id(tid) is None or rec['n'] < 20 or _tall(K, tid) != tall:
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
        k0 = rng.randint(1, w - 2) if w >= 3 else 0     # (the entry tile has the one wall, the doorway's: never a corner)
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
        return True
    return False


def generate(db, size='medium', levels='some', twist='branching', seed=None, kind='dwemer', entry=None, final=None):
    """A place's layout: {'pieces': [...], 'seams': [...], 'entrance': {...}, 'halls': n, 'seed'}. A growth
    that gets boxed in early, or finds no room for its last hall, is grown again from a seed drawn from this
    one (a tenth of a second each), and the best of up to 24 kept: the same seed always gives the same place.
    entry: a dead end's piece number to be the way in instead; final: the hall to be the last one (picked on
    the Dungeon tool's plan)."""
    lay = _generate(db, size, levels, twist, seed, kind)
    if entry is not None or final is not None:
        _pick(db, survey(db, kind=kind), kit(kind), lay, entry, final)
    return lay


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
    seam = next((s for s in lay['seams'] if s[5] == entry or s[4] == entry), None)
    if seam is None:
        return
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
    lay['picked'] = {'entry': entry, 'final': lay['final']}


def _generate(db, size='medium', levels='some', twist='branching', seed=None, kind='dwemer'):
    K = kit(kind)
    S = survey(db, kind=kind)
    if not S or K['base'] not in S['ports']:
        raise EditError('The Workshop has not learnt the %s pieces yet: the game\'s own could not be read.' % K['label'])
    seed = int(seed) if seed is not None else random.getrandbits(31)
    target = SIZES.get(size, SIZES['medium'])[0]
    best = None
    sub = random.Random(seed)
    for attempt in range(24):
        lay = _grow(db, S, K, size, levels, twist, seed if attempt == 0 else sub.getrandbits(31))
        score = (lay['final'] is not None, min(lay['tunnels'], target), -lay['open_left'])
        if best is None or score > best[0]:
            best = (score, lay)
        if lay['final'] is not None and lay['tunnels'] >= 0.8 * target and not lay['open_left']:
            break
    out = best[1]
    out['seed'] = seed
    return out


def _lay_any(L, port, depth, hall_no, rng, final=False):
    """A hall, chamber or room, as the kind has them, at an open opening; True when one fits."""
    how = L.K.get('halls')
    if how == 'dwemer':
        sizes = ((5, 4), (4, 4), (4, 3), (5, 3)) if final else [rng.choice([(4, 3), (4, 4), (5, 3), (5, 4)])]
        return any(_lay_hall(L, port, w, h, depth, hall_no, rng, second_exit=not final) for w, h in sizes)
    if how == 'tiled':
        # (Project Tamriel's Daedric guide: rooms of 2x3 to 3x4 tiles)
        sizes = ((3, 4), (3, 3), (3, 2)) if final else [rng.choice([(3, 2), (3, 3), (3, 4), (4, 3)]), (3, 2)]
        return any(_lay_room(L, port, w, h, depth, hall_no, rng) for w, h in sizes)
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


def _grow(db, S, K, size, levels, twist, seed):
    rng = random.Random(seed)
    target, n_halls = SIZES.get(size, SIZES['medium'])
    # the tunnel pieces to grow with, as often as the game uses each (with the asked-for mix)
    mix = {'linear': {'T': 0.3, 'cross': 0.15, 'straight': 1.3, 'corner': 1.0, 'dead end': 0.3},
           'branching': {}, 'maze': {'T': 1.6, 'cross': 1.8, 'dead end': 1.2, 'straight': 0.8}}.get(twist, {})
    ramp_k = {'flat': 0.0, 'some': 1.0, 'steep': 2.5}.get(levels, 1.0)
    pool = []
    for pid, ps in S['ports'].items():
        r = role_of(pid, K, S)
        if r in ('hall', 'shaft', 'other', 'room', 'entry') or (K.get('skip') and re.search(K['skip'], pid)) or db.resolve_id(pid) is None or len(ps) < 1 or S.get('agree', {}).get(pid, 0) < AGREE:
            continue
        w = S['n'].get(pid, 1) * mix.get(r, 1.0) * (ramp_k if r == 'ramp' else 1.0) * (K.get('mix') or {}).get(r, 1.0)
        if w > 0:
            pool.append((pid, r, w))
    if not pool:
        raise EditError('No %s tunnel pieces with known openings.' % K['label'])
    L = _Layout(db, S, K)
    L.big = size == 'large'
    load = (S.get('door') or {}).get('load') or {}
    holder = load.get('holder') if isinstance(load, dict) else None
    entrance = None
    if holder and holder != K.get('jamb') and S['ports'].get(holder):
        # the way in: the kind's own entrance piece (a cave's exit), its openings the way on
        first = L.add(holder, 0.0, 0.0, 0.0, 0.0, 0)
        for o in L.ports_of(holder, 0.0, 0.0, 0.0, 0.0):
            L.open.append(dict(o, owner=first, depth=1))
        entrance = {'piece': first}
    else:
        # the way in: a plain straight, its west end the front door's frame
        first = L.add(K['base'], 0.0, 0.0, 0.0, 0.0, 0)
        ports0 = L.ports_of(K['base'], 0.0, 0.0, 0.0, 0.0)
        for k, o in enumerate(ports0):
            if k == 0:
                entrance = dict(o, owner=first)
            else:
                L.open.append(dict(o, owner=first, depth=1))
    halls_at = sorted({max(3, int(target * f)) for f in ([0.45, 0.8][:max(0, n_halls - 1)] if n_halls > 1 else [])})
    if n_halls > 2:
        halls_at = sorted({max(3, int(target * f)) for f in (0.3, 0.6)})
    hall_no = 0
    tunnels = 1
    tries = 0
    while any(not o.get('cap') for o in L.open) and tunnels < target and tries < target * 60:
        tries += 1
        # which opening grows next: the newest mostly for a long winding route, any for a branching one
        grow = [o for o in L.open if not o.get('cap')]
        if twist == 'linear' or (twist == 'branching' and rng.random() < 0.55):
            port = max(grow, key=lambda o: (o['depth'], rng.random()))
        else:
            port = rng.choice(grow)
        if halls_at and tunnels >= halls_at[0]:
            if _lay_any(L, port, port['depth'], hall_no, rng):
                hall_no += 1
                halls_at.pop(0)
            elif tries % 8 == 0:
                halls_at.pop(0)                 # (no room for it anywhere near: grow on without it)
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
            # (nothing fits here: this opening is left for a dead end)
            port['stuck'] = True
            if all(o.get('stuck') or o.get('cap') for o in L.open):
                break
    # the last hall at the far end: the deepest opening that takes one
    final = None
    for port in sorted((o for o in L.open if not o.get('cap')), key=lambda o: -o['depth']):
        if _lay_any(L, port, port['depth'], hall_no, rng, final=True):
            final = hall_no
            hall_no += 1
            break
    # every other open end closed: a dead end, or failing that the piece before it taken away
    dead = K['dead_end']

    def cap():
        for _round in range(60):
            if not L.open:
                break
            port = L.open[0]
            if any(L.place_at(dead, k, port, port['depth']) is not None for k in range(len(S['ports'].get(dead, [])))):
                continue
            # (no room for a dead end: take away the piece the opening belongs to, when it is a tunnel with no
            # other piece hanging off it, and open the seam it hung from instead)
            own = port['owner']
            hangs = [s for s in L.seams if s[4] == own]
            if L.pieces[own]['hall'] is None and not hangs and own != first:
                seam = next(s for s in L.seams if s[5] == own)
                L.open = [o for o in L.open if o['owner'] != own]
                L.seams.remove(seam)
                L.pieces[own] = dict(L.pieces[own], gone=True, box=(0, 0, 0, 0, 0, 0))
                L.open.append({'x': seam[0], 'y': seam[1], 'z': seam[2], 'side': seam[3], 'owner': seam[4], 'depth': L.pieces[seam[4]]['depth'] + 1})
            else:
                L.open.pop(0)                       # (left open: Find gaps shows it)
    cap()
    # a side branch that climbs or drops only to end is taken back to where it left, and capped there (the
    # user: "a bed at the end of a descending staircase hallway ... who would build that just to put a bed
    # there and no room?"); a level stub stays, an alcove
    for _cut in range(40):
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
            for c_ in chain:
                L.pieces[c_] = dict(L.pieces[c_], gone=True, box=(0, 0, 0, 0, 0, 0))
            L.seams = [s for s in L.seams if s[4] not in chain and s[5] not in chain]
            L.open = [o for o in L.open if o['owner'] not in chain]
            L.open.append({'x': top[0], 'y': top[1], 'z': top[2], 'side': top[3], 'owner': top[4], 'depth': L.pieces[top[4]]['depth'] + 1})
            done = True
            break
        if not done:
            break
        cap()
    pieces = [p for p in L.pieces if not p.get('gone')]
    return {'seed': seed, 'grown_from': seed, 'pieces': L.pieces, 'seams': L.seams, 'entrance': entrance, 'halls': hall_no, 'final': final,
            'open_left': len(L.open), 'tunnels': sum(1 for p in pieces if p['hall'] is None)}


# where the way into a shrine's room lies, seen from its statue: in front of it, the statue's -Y (the game's
# Daedric ruins: the room's entrance piece at 270° in the statue's frame 25 times of 60, within 45° of it 35;
# the user: "usually the statue faces the door")
SHRINE_FACES = 270


def _shrine(db, c, S, lay, rng, key=None):
    """One of the game's shrines laid in the last room, as a whole: its statue in the room's middle, all
    round it as the game had it (the user: "usually it has a shrine and a statue, an altar, gemstones and
    cups"; 59 of the game's 112 Daedric ruins have one). Of a few shrines and the four quarter turns, the
    one that leaves least of itself outside the room, its statue facing the room's way in. The room's own
    dressing is taken out of the shrine's footprint first (the user saw a shrine "clip into that platform
    with decor"). True when one is laid."""
    hp = [p for p in lay['pieces'] if p.get('hall') == lay['final'] and not p.get('gone') and p.get('box')]
    if not hp:
        return False
    x0, y0 = min(p['box'][0] for p in hp) + 40, min(p['box'][1] for p in hp) + 40
    x1, y1 = max(p['box'][3] for p in hp) - 40, max(p['box'][4] for p in hp) - 40
    fz = min(p['p'][2] for p in hp)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    # (the way in: the room's entry piece, else the piece of the room nearest the front door's side)
    K = lay.get('K') or {}
    way = next((p for p in hp if p['id'] in _entries(K)), None) or min(hp, key=lambda p: p.get('depth', 0))
    wa = math.atan2(way['p'][1] - my, way['p'][0] - mx)
    best = None
    for sh in rng.sample(S['shrines'], min(8, len(S['shrines']))):
        if db.resolve_id(sh['statue']) is None:
            continue
        for q in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            out = 0
            for it in sh['items']:
                wx, wy = _rot(it[2], it[3], q)
                if not (x0 <= mx + wx <= x1 and y0 <= my + wy <= y1):
                    out += 1
            share = out / max(1, len(sh['items']))
            # (the way in, in the statue's frame turned by q: _rot turns clockwise, so its frame's angle is
            # the world's plus q)
            la = math.degrees(wa + q) % 360
            off = abs((la - SHRINE_FACES + 180) % 360 - 180)
            score = (share > 0.2, round(off / 45), share)
            if best is None or score < best[0]:
                best = (score, sh, q)
    if best is None or best[0][0]:
        return False
    _score, sh, q = best
    refs = [(sh['statue'], (mx, my, fz + sh['z'], 0, 0, q), [], sh.get('s') or 1.0)]
    for rid, t, lx, ly, lz, rx, ry, drz, s in sh['items']:
        if db.resolve_id(rid) is None:
            continue
        wx, wy = _rot(lx, ly, q)
        if not (x0 - 40 <= mx + wx <= x1 + 40 and y0 - 40 <= my + wy <= y1 + 40):
            continue                                   # (what would stand outside the room's walls)
        refs.append((rid, (mx + wx, my + wy, fz + lz, rx, ry, (q + drz) % (2 * math.pi)), [], s))
    if key:
        # the room's own dressing out of the shrine's footprint (its things' spread, and a hand round it)
        xs = [p[1][0] for p in refs]
        ys = [p[1][1] for p in refs]
        fx0, fy0, fx1, fy1 = min(xs) - 64, min(ys) - 64, max(xs) + 64, max(ys) + 64
        struct = re.compile(K.get('tube', '^$') + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['roofs']) if K.get('roofs') else ''))
        for r in mapdata.cellmap(db, key)['refs']:
            i = r['id'].lower()
            if r['type'] in ('DOOR', 'NPC_') or struct.match(i) or i == K.get('jamb'):
                continue
            x, y, z = r['p'][:3]
            if fx0 <= x <= fx1 and fy0 <= y <= fy1 and fz - 60 <= z <= fz + 700:
                c['refs'].pop(r['k'], None)
    _write_refs(db, c, refs)
    db.sync_project()
    return True


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


def _dress_refs(db, S, lay, rng, loot='usual', creatures='usual', K=None):
    """What stands in each piece: a whole set copied from a real piece of the same kind in the game's places
    (or none, as often as the game leaves that kind bare), turned and moved to this piece. Kwama egg sacs and
    veins only in an egg mine (lay['mine'])."""
    K = K or kit('dwemer')
    mine = bool(lay.get('mine'))
    out = []
    uniq = set(S.get('uniques') or [])
    # (as a share of the game's own: under 1 some of each are left out, over 1 the fuller of the game's
    # sets are drawn, empty barrels come full and more of the kind's creatures roam)
    loot_x, crea_x = amount('loot', loot), amount('creatures', creatures)
    keep_loot, keep_crea = min(1.0, loot_x), min(1.0, crea_x)
    is_loot = lambda t: t not in ('CREA', 'LEVC', 'LIGH', 'STAT', 'ACTI')
    more = K.get('more')
    n_crea = 0
    for n, p in enumerate(lay['pieces']):
        if p.get('gone') or not p.get('id'):
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
        # (richer: the most loot of a few draws, one more draw for each whole step over the game's)
        draws = 1 + int(max(0.0, loot_x - 1.0) * 2 + rng.random())
        chosen = max((_set_items(rng.choice(pool_)) for _ in range(draws)), key=lambda d: sum(1 for row in d if is_loot(row[1])))
        x, y, z, rz = p['p'][0], p['p'][1], p['p'][2], p['p'][5]
        for rid, t, lx, ly, lz, rx, ry, drz, s in chosen:
            low = rid.lower()
            if low in uniq or db.resolve_id(rid) is None or MASONRY_FIRE.match(low):
                continue
            if not mine and t not in ('CREA', 'LEVC', 'INGR') and (EGG_MINE.search(low) or EGG_MINE.search((db.recs[db.resolve_id(rid)][5] or '').lower())):
                continue                         # (an egg mine's, not a cave's; kwama foragers still roam)
            if t in ('CREA', 'LEVC') and rng.random() >= keep_crea:
                continue
            if is_loot(t) and rng.random() >= keep_loot:
                continue
            if low.endswith('_empty') and rng.random() < loot_x - 1.0 and db.resolve_id(rid[:-6]) is not None:
                rid = rid[:-6]                     # (a full barrel where the game had an empty one)
            n_crea += t in ('CREA', 'LEVC')
            wx, wy = _rot(lx, ly, rz)
            # (rubble and debris lying flat at the piece's own height share the floor's face and flicker: the
            # user's Daedric ruin, in_dae_rubble_01a at the foot of a stair. The game lays most of them so too,
            # 98 of its 186; lifted a hair here)
            # (most of the game's rubble lies turned over, rx a half turn: lifted whatever its turn)
            if t == 'STAT' and FLAT_ON_FLOOR.search(low):
                lz += FLAT_LIFT
            out.append((rid, (x + wx, y + wy, z + lz, rx, ry, (rz + drz) % (2 * math.pi)), [], s))
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


def preview(db, kind='dwemer', size='medium', levels='some', twist='branching', seed=None, entry=None, final=None):
    """The layout a build with these choices would make, for the Dungeon tool's plan: each piece's box from
    above (x0, y0, x1, y1), its floor-ish height, what it is and its hall; the way in and the last hall.
    {'learning': [...]} while the kind is still being learnt."""
    S = ready(db, kind)
    if S is None:
        import learning
        return {'learning': learning.ruin_pending(db, kind)}
    seed = int(seed) if seed not in (None, '') else random.getrandbits(31)
    lay = generate(db, size, levels, twist, seed, kind=kind, entry=entry, final=final)
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
    if zs_ and ez is not None and max(zs_) > min(zs_):
        dry_to = round(max(0.0, min(1.0, (ez - min(zs_)) / (max(zs_) - min(zs_)))), 2)
    # (what the game's own places of the kind would put in pieces like these, for the sliders' "as the game's"
    # figures: creatures and loose loot from the sets of each piece, on average; and the share of them lived in)
    cr = lt = 0.0
    for p in lay['pieces']:
        if p.get('gone') or not p.get('id'):
            continue
        c_, l_ = _set_amounts(S, p['id'])
        cr += c_
        lt += l_
    return {'seed': seed, 'kind': kind, 'pieces': out, 'entrance': [round(e.get('x', 0)), round(e.get('y', 0))] + ([round(ez)] if ez is not None else []),
            'dry_to': dry_to, 'picked': lay.get('picked') or {},
            # (a cave's way in is a piece of its own, its mouth: not moved on the plan)
            'entry_pickable': 'piece' not in (lay.get('entrance') or {}),
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
              water=o.get('water', 'none'))
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
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else ''))
    gone = 0
    for _pass in range(3):
        m = mapdata.cellmap(db, key)
        struct_ = {r['k'] for r in m['refs'] if tube.match(r['id'].lower()) or r['type'] == 'DOOR' or r['id'].lower() == K.get('jamb')}
        keep = struct_ | {r['k'] for r in m['refs'] if r['type'] in ('LIGH', 'NPC_', 'CREA', 'LEVC')
                          or re.search(r'rug|mist|sound|web|vine|moss|marker', r['id'].lower())}
        # (the floor: from the building pieces alone)
        sc_t = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['k'] in struct_]))
        sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['type'] != 'DOOR']))
        L = _Layout(db, S, K)
        out = set()
        # (the user: machines "cannot be blocking corridors and intersections": the way through every tunnel
        # piece, a person's width of it (one line in a natural cave, whose rocks hug its walls), stays clear;
        # halls and rooms keep their machinery)
        width = (0,) if K.get('kind', '').startswith('cave') else (-40, 0, 40)
        for p in lay['pieces']:
            if p.get('gone') or not p.get('id') or p.get('hall') is not None:
                continue
            ports = L.ports_of(p['id'], p['p'][0], p['p'][1], p['p'][2], p['p'][5])
            if not ports:
                continue
            mx = sum(o['x'] for o in ports) / len(ports)
            my = sum(o['y'] for o in ports) / len(ports)
            mz = sum(o['z'] for o in ports) / len(ports)
            for o, off in [(o, off) for o in ports for off in width]:
                dx, dy = SIDES[o['side']]
                ax, ay, az = o['x'] - dx * 24 - dy * off, o['y'] - dy * 24 + dx * off, o['z']
                n = max(2, int(math.hypot(mx - ax, my - ay) / 48) + 1)
                line = []
                for k in range(n + 1):
                    t = k / n
                    x, y, z = ax + (mx - ax) * t, ay + (my - ay) * t, az + (mz - az) * t
                    h = sc_t.nearest_any((x, y, z + 150), (0.0, 0.0, -1.0), 700)
                    if h is not None:
                        line.append((x, y, z + 150 - h[0]))
                for (x0, y0, f0), (x1, y1, f1) in zip(line, line[1:]):
                    if abs(f1 - f0) > 120:
                        continue                    # (a drop or a step: not one walk)
                    for hgt in (50, 110):
                        a_ = (x0, y0, f0 + hgt)
                        d = (x1 - x0, y1 - y0, f1 - f0)
                        ln = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
                        if ln < 1:
                            continue
                        hit = sc.nearest_any(a_, (d[0] / ln, d[1] / ln, d[2] / ln), ln)
                        if hit is not None:
                            k_ = sc.owner(hit[1])
                            if k_ and k_ not in keep:
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
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else ''))
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
        sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['type'] != 'DOOR']))
        # (what may be taken out of the way: copied dressing, never a shrine, its platform and stairs, an altar or a light)
        rockish = {r['k'] for r in m['refs'] if r['type'] in ('STAT', 'ACTI', 'CONT', 'MISC')
                   and not re.search(r'statue|platform|stair|ramp|altar|shrine|^ex_dae_|^active_dae_|light|lamp|sconce|brazier|censer'
                                     r'|plat|plank|dock|rail|ladder|bridge|board|beam|scaffold|walkway', r['id'].lower())}
        # (a grid of the floor not reached, to find its neighbours of the reached quickly)
        cells_ = defaultdict(list)
        for v in range(len(pts)):
            if v not in seen:
                cells_[(int(pts[v][0] // 200), int(pts[v][1] // 200))].append(v)
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


def _water(db, key, lay, K, how, rng):
    """Water in the place: how (0 to 1, or the old 'pools' and 'flooded') is how far up it stands, from the
    lowest floor (0.1: pools there) to the highest (1); the way in goes under when it is lower than that;
    with no water, the slaughterfish, dreugh, kelp and pearls its dressing brought from the game's wet caves
    are taken out, and with water only those under it stay. The water height, or None."""
    share = amount('water', how)
    import seethrough
    c = db.project.cells.get(key)
    if not c:
        return None
    m = mapdata.cellmap(db, key)
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else ''))
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if tube.match(r['id'].lower())]))
    floors = []
    for p in lay['pieces']:
        if p.get('gone') or not p.get('box'):
            continue
        b = p['box']
        f = sc.nearest_any(((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, b[5] - 20), (0.0, 0.0, -1.0), b[5] - b[2])
        if f is not None:
            floors.append(b[5] - 20 - f[0])
    level = None
    if share > 0 and floors:
        floors.sort()
        # (that share of the way up from the lowest floor to the highest, a wading depth at least. Up to the
        # way in only, it stayed dry where the front door is near the bottom: the user's large steep ruin at
        # its top setting had water under every floor. The slider says where the way in goes under)
        level = floors[0] + max(40.0, share * (floors[-1] - floors[0]))
    # what lives in water: kept only under it
    gone = [r['k'] for r in m['refs'] if WATER_LIFE.search(r['id'].lower()) and r['type'] in ('CREA', 'LEVC', 'CONT', 'ACTI', 'STAT')
            and (level is None or r['p'][2] > level - 20)]
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
        # (and fish in it: one for every few pieces under water, half way down)
        fish = next((f for f in ('slaughterfish', 'slaughterfish_small') if db.resolve_id(f) is not None), None)
        wet = [p for p in lay['pieces'] if not p.get('gone') and p.get('box') and p['box'][2] + 60 < level]
        if fish and K.get('setting') in ('cave', 'tomb', 'daedric', 'dwemer'):
            mine = db.project.plugin.lower()
            for p in rng.sample(wet, min(len(wet) // 4, 8)):
                b = p['box']
                f = sc.nearest_any(((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, level - 10), (0.0, 0.0, -1.0), level - b[2])
                if f is None or f[0] < 60:
                    continue
                nk = db.project.new_ref_key()
                editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]),
                               set_ref_pos([('NAME', zs(fish))], ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, level - 10 - f[0] / 2, 0, 0, rng.random() * 6.28), 1.0))
    db.sync_project()
    return level


def unb64_(d):
    from project import unb64
    return unb64(d) if isinstance(d, str) else d


LOOSE = re.compile(r'crate|barrel|sack|chest|urn|basket|keg|box')


def _settle(db, key):
    """Crates, barrels, sacks, chests, urns and baskets keep the lean they had on the game's rock; where one
    stands on something flat here (a plank deck, a floor) it is set level and down on it, and a stacked one
    on the one under it. The user's Greedy Grove had crates tilted on a level deck. The number set level."""
    import seethrough
    m = mapdata.cellmap(db, key)
    loose = [r for r in m['refs'] if r['type'] in ('CONT', 'MISC') and LOOSE.search(r['id'].lower()) and r.get('b')]
    if not loose:
        return 0
    ids = {id(r) for r in loose}
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if id(r) not in ids and r['type'] != 'DOOR']))
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
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else ''))
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
    tube = re.compile(K['tube'] + (('|' + K['tiles']) if K.get('tiles') else '') + (('|' + K['roofs']) if K.get('roofs') else ''))
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
        if h is not None and h[0] - 6 <= 140:
            # (down onto it, level: what was on a table lies on the floor)
            set_z = r['p'][2] - (h[0] - 6)
            editing._store(c, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], (x, y, set_z, 0.0, 0.0, r['p'][5]), None))
            dropped += 1
        else:
            c['refs'].pop(r['k'], None)
            gone += 1
    db.sync_project()
    return dropped, gone


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
    sc = seethrough.place_scene(db, dict(m, refs=[r for r in m['refs'] if r['type'] not in ('NPC_', 'CREA', 'LEVC')]))
    ids_by_k = {r['k']: r['id'].lower() for r in m['refs']}
    gone = []
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
        if not touches:
            gone.append(r['k'])
    for k_ in gone:
        c['refs'].pop(k_, None)
    db.sync_project()
    return len(gone)


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
                if fz is not None and fz > p['p'][2] - 300 and sc.nearest_any((x, y, fz + 20), (0.0, 0.0, 1.0), 1200) is not None:
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
    n = rng.choice([1, 1, 2, 2, 3, 3, 4])
    cast = populate.cast(db, key, {'setting': K['setting'], 'count': n}, seed=rng.getrandbits(31))
    people = (cast.get('people') or [])[:n]
    if not people:
        return 0
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
        r = populate.place(db, key, people, own=False)
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
    r = populate.place(db, key, people, own=False)
    return r.get('placed', 0)


def _write_refs(db, c, refs):
    p = db.project
    mine = p.plugin.lower()
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


def build(db, name, size='medium', levels='some', twist='branching', loot='usual', creatures='usual',
          doors=0.12, entrance=None, outside_door=None, seed=None, commit=True, occupants='auto', kind='dwemer', water='none',
          entry_piece=None, final_hall=None):
    """A new dungeon of the kind called name, laid out, dressed and written into the mod as a new place.
    entrance: {cell, x, y, z, rz} outside, for a door there that leads in (as Build from pieces does), or None."""
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
    lay = generate(db, size, levels, twist, seed, kind=kind, entry=entry_piece, final=final_hall)
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
        if not pc.get('gone') and pc['id'] in tiles and roof and tiles[pc['id']].get('roof', 0) >= 0.5:
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
        for k_seam, (sx, sy, sz, side, a, b) in enumerate(lay['seams']):
            if not leads_on(b) or not only_way(k_seam):
                continue
            A, B = lay['pieces'][a], lay['pieces'][b]
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
    refs.append((lid, (door_pos[0], door_pos[1], door_pos[2], 0, 0, drot), door_extra, 1.0))
    for did, pos in leaves:
        refs.append((did, pos, door_extra, 1.0))
    # what's in it
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
    _write_refs(db, c, refs)
    db.sync_project()
    if kind != 'dwemer':
        # (where the floor really is by the front door: the arrival spot stands on it)
        try:
            import seethrough
            sc = seethrough.place_scene(db, mapdata.cellmap(db, key))
            fz = _floor_at(sc, arrive[0], arrive[1], door_pos[2] - 20)
            if fz is not None:
                arrive[2] = fz + 16
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
        _upright(db, key)
        cleared = _clear_ways(db, key, lay, S, K)
        cleared += _unblock(db, key, lay, K, _walk_starts(db, lay))
        cleared += _declip(db, key, K)
        cleared += _in_rock(db, key, K)
        cleared += _floaters(db, key)
        # (last, after everything taken out of the way: what stood on a plank that went comes down to the floor)
        _settle(db, key)
        _orphans(db, key, K)
    except Exception as ex:
        cleared = 0
        print('dungeon ways through:', ex)
    tables_set = 0
    try:
        tables_set = _lay_tops(db, key, S, rng, loot)
    except Exception as ex:
        print('dungeon table tops:', ex)
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
    c['ruin'] = {'kind': kind, 'water': water, 'size': size, 'levels': levels, 'twist': twist, 'loot': loot, 'creatures': creatures, 'seed': lay['seed'],
                 'entrance': entrance, 'outside_door': outside_door, 'occupants': occupants}
    db.sync_project()
    note = 'Made a %s "%s" (%d tunnel pieces, %d %s)%s' % (
        K['label'][0].lower() + K['label'][1:] if not K['label'].startswith(('Dwemer', 'Velothi', 'Daedric')) else K['label'], name,
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
    steps = len(getattr(p, 'undo_stack', [])) - n0
    if steps > 1:
        editing.fold(db, steps, note + (' and %d %s' % (people, 'person living in it' if people == 1 else 'people living in it') if people else ''))
    return {'key': key, 'name': name, 'kind': kind, 'seed': lay['seed'], 'tunnels': lay['tunnels'], 'halls': lay['halls'],
            'open_left': lay['open_left'], 'refs': len(refs), 'entrance': out_spot[0] if out_spot else None,
            'arrive': [round(v, 1) for v in arrive[:3]], 'people': people, 'final': lay['final'] is not None, 'cleared': cleared, 'water': water_at, 'tables_set': tables_set}
