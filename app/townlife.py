"""A made town's life: its market stalls with their sellers, its storage by the houses' walls, its guards at the gates,
the doors of its great houses, its square and its streets, and its townsfolk about the doors and the square, as many a
building as the game's own towns of the culture have, learnt from them (the user, 2026-11-03: "the towns feeling
sparse and empty. Hardly any signs of storage or commerce. Guards and npcs are also noticeably lacking. Vendor
stalls and whatnot").

  learn(db)   per culture: how many guards, sellers, townsfolk, stalls and storage the game's towns have a building,
              where its guards and townsfolk stand (gate, door, square, street), their classes and factions, how far
              they wander; the stalls round each of its outdoor sellers whole, in the seller's frame (tables, stands,
              awnings, the goods set out), the stalls nobody keeps, and the storage standing together by the walls
  dress(...)  the stalls and storage for a town being dressed (towndress.dress calls it, sharing its space)
  people(...) the town's people outdoors: new NPC records of the culture's classes and factions, sellers with their
              barter, the stalls' goods and crates theirs (taking them is theft), guards of the culture's own

Never a whole layout copied: each stall or stack of crates is one of the game's small scenes, set where this town has
room for it, by its own streets, square and walls."""
import json
import math
import os
import random
import re
import struct
from collections import Counter, defaultdict

import mapdata
import townsurvey

VERSION = 8                    # (2: people on buildings counted, storage away from the yards; 3: signs; 4: awnings, big towns; 5: by example;
                               # 6: storage set inside a building's pieces not counted; 7: and as the audit counts it)
NEAR = 900                     # (a town's outdoor refs: within this of a building's box)
SELL_NEAR = 320                # what stands this near an outdoor seller is their stall
STALL_LONE = 500               # (a stall with no seller this near is one nobody keeps)
STORE_LINK = 200               # storage things this near each other stand together
STORE_MAX = 14                 # (more together is a warehouse yard or a dock: kept to this many)
WALL_NEAR = 500                # (storage this near a building's wall stands by it)
GATE_NEAR = 900
DOOR_NEAR = 400
SCENE_MAX = 30
BARTER = 0x37FF                # (the services that are buying and selling: every item kind, magic items, potions)
STALLY = re.compile(r'marketstand|market_?stand|stall|awning|canopy|overhang|table|counter|screen|shelf|rack|bench|stool|'
                    r'crate|barrel|sack|basket|urn|keg|cart|lantern|lamp|_pot|pot_|bucket|bowl|platter|tray|cloth|rug|'
                    r'pole|post|pillar|beam|support|frame', re.I)   # (and the posts an awning hangs from: the Dunmer cloth
                                                                     # overhangs came without them, "missing support
                                                                     # posts", the user 2026-11-06)
STALL_CORE = re.compile(r'marketstand|market_?stand|stall|awning|canopy|overhang|table|counter', re.I)
CANOPY = re.compile(r'awning|canopy|overhang|tent', re.I)
STORAGE = re.compile(r'crate|_box|box_|chest|barrel|keg|cask|sack|bag_|_bag|basket|bale|haypile|(^|_)urn|amphora|cart(?!ograph)|'
                     r'wagon|wheelbarrow|woodpile|firewood|log_?pile|logpile', re.I)
GOODS_T = ('INGR', 'MISC', 'ALCH', 'CLOT', 'WEAP', 'ARMO', 'BOOK', 'APPA', 'LOCK', 'PROB', 'REPA')
THING_T = ('STAT', 'CONT', 'LIGH', 'ACTI', 'MISC', 'APPA', 'INGR', 'ALCH', 'CLOT', 'WEAP', 'ARMO', 'BOOK', 'LOCK', 'PROB', 'REPA')
GUARD_ID = re.compile(r'guard|ordinator|legion|watchman|sentry|soldier', re.I)
GUARD_CLS = re.compile(r'^guard$|ordinator|sharpshooter', re.I)
TRADE_CLS = re.compile(r'trader|merchant|pawnbroker|smith|outfitter|clothier|alchemist|apothecary|bookseller|enchanter|publican|'
                       r'fishmonger|butcher|baker|vendor|peddler|monger', re.I)
NOT_SELLER = re.compile(r'caravaner|shipmaster|gondolier|guide|riverstrider|silt|boatman|ferry', re.I)
SPECIAL = ('guard', 'manor', 'temple', 'tavern', 'guild')
TOWN_FIGHT = 30                # (no one in a town attacks on sight: towninside's cap)
GUARD_KINDS = 3                # (a town's guards share this many records, as the game's own generic guards do)
SEEN = {}                      # (the last town's figures, for the checks)
BIG_TOWN = 25                  # (a town of this many buildings or more lives as the game's big towns do: their own rates)
AWNING = re.compile(r'awning|canopy|overhang', re.I)
AWNING_NEAR = (400, -300, 150)  # (an awning this near a door, sideways, out and in, in its frame, is the door's)
LONE_MOST = 3                  # (a lone stall scene stands this often in a town at most, whatever the rate asks)
AWNING_HEAD = 180              # (an awning whose underside is under this over the door's floor stands on posts, or hangs in the
                               # way: kept off the doors' ways)


# ------------------------------------------------------------------------------------------------ learning
def _disk(db):
    import taste
    # (the Workshop's own cache folder, beside projects: under app\ the Setup removed it with the program files at every
    # install, and the strays, town dressing and town life were learnt again, minutes each, the user's 2026-11-09)
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'townlife_%s_v%d.json' % (taste.sig(db), VERSION))


_mem = {}


def learn(db):
    k = id(db.recs)
    if k in _mem:
        return _mem[k]
    path = _disk(db)
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                _mem[k] = json.load(f)
                return _mem[k]
        except (OSError, ValueError):
            pass
    out = _learn(db)
    try:
        with open(path + '.part', 'w', encoding='utf-8') as f:
            json.dump(out, f)
        os.replace(path + '.part', path)
    except OSError:
        pass
    _mem[k] = out
    return out


_P = {}


def _person(db, rid):
    import castsurvey
    k = rid.lower()
    if (id(db.recs), k) not in _P:
        ri = db.resolve_id(rid)
        _P[(id(db.recs), k)] = castsurvey.person(db, ri) if ri is not None and db.recs[ri][0] == 'NPC_' else None
    return _P[(id(db.recs), k)]


def role_of(db, r):
    """'guard', 'seller' or 'folk' for an NPC ref (None: not a person)."""
    o = _person(db, r['id'])
    if not o:
        return None
    if GUARD_ID.search(r['id']) or GUARD_ID.search(o['name'] or '') or GUARD_CLS.search(o['cls'] or ''):
        return 'guard'
    if NOT_SELLER.search(o['cls'] or '') or o['travel']:
        return 'folk'
    if o['services'] & BARTER or TRADE_CLS.search(o['cls'] or ''):
        return 'seller'
    return 'folk'


def _in_box(box, x, y, pad=0.0):
    return box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad


def _size(r):
    b, s = r['b'], r['s'] or 1.0
    return max(b[3] - b[0], b[4] - b[1]) * s


POLE = re.compile(r'pole|post|pillar|beam|support|frame', re.I)
CLOTH_THIN = 100               # (a canopy model under this tall is the cloth alone, with no poles of its own)
CLOTH_HOLD = 320               # (it is kept in a scene only with a pole within this of it, or a wall it hangs from)
CLOTH_FLAT = 50                # (a canopy model under this thick is a sheet of cloth: Tamriel Data's overhangs are 27-46; the game's
                               # bracket awnings, furn_de_overhang_05/09, the Common wooden one, the GC canopies, 76-97, hold themselves off a wall)
CLOTH_LONG = 300               # (a sheet this long across is stretched: each end of its span wants a pole or a wall)
WALL_AT = 60                   # (an end this near a building piece hangs from it)


def _held_cloth(things, refs):
    """The scene's things less any cloth canopy that nothing holds up: a cloth-only overhang (Tamriel Data's
    T_De_Furn_Overhang_03a and kin, 40 tall) with no pole, post or frame within CLOTH_HOLD in the scene. In the game
    they hang from poles or a wall; set out alone they hung in the air, "missing support posts", the user 2026-11-06.
    refs: the scene's game refs, in the things' order, for their bounds."""
    by = {r['id'].lower(): r for r in refs if r.get('b')}
    out = []
    for t in things:
        r = by.get(t['id'].lower())
        if CANOPY.search(t['id']) and r is not None and (r['b'][5] - r['b'][2]) * (r['s'] or 1.0) < CLOTH_THIN:
            held = any(POLE.search(o['id']) and math.hypot(o['x'] - t['x'], o['y'] - t['y']) <= CLOTH_HOLD for o in things if o is not t)
            if not held:
                continue
        out.append(t)
    return out


def _stall_thing(r):
    """A thing that makes a stall: a stand, a table, an awning on its posts, the goods set out, a crate of stock."""
    import landscape
    low = r['id'].lower()
    if r['type'] not in THING_T or not r.get('b') or landscape.NATURAL.search(low):
        return False
    if re.search(r'marker|collision|sound|door|_light_off|^key_|gold_', low):
        return False
    if r['type'] in GOODS_T:
        return True
    return bool(STALLY.search(low)) and _size(r) < 900


def _solid(db, refs, boxes):
    """The town's architecture outlines (turned), by 1024 squares: [(pts, z0, z1)]."""
    import towndress
    G = defaultdict(list)
    memo = {}
    for r in refs:
        if not r.get('arch') or not r.get('b') or r['type'] in ('NPC_', 'CREA'):
            continue
        b, sc = r['b'], r['s'] or 1.0
        if max(b[3] - b[0], b[4] - b[1]) * sc < 150 or (b[5] - b[2]) * sc < 100:
            continue
        pts, _b = towndress._rect_of(r['id'], r['p'][0], r['p'][1], r['p'][5], sc, memo, db)
        if not pts:
            continue
        z0, z1 = r['p'][2] + b[2] * sc, r['p'][2] + b[5] * sc
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        for gx in range(int(min(xs) // 1024), int(max(xs) // 1024) + 1):
            for gy in range(int(min(ys) // 1024), int(max(ys) // 1024) + 1):
                G[(gx, gy)].append((pts, z0, z1))
    return G


def _in_solid(r, G):
    import towndress
    x, y, z = r['p'][0], r['p'][1], r['p'][2]
    return any(z0 - 40 <= z <= z1 - 40 and towndress._in_poly(pts, x, y) for pts, z0, z1 in G.get((int(x // 1024), int(y // 1024)), ()))


def _bottom(r):
    return r['p'][2] + r['b'][2] * (r['s'] or 1.0)


def _learn(db):
    import towndress
    AW = defaultdict(dict)                       # (main piece -> {interior: [awning]}: the very game building's own)
    rmemo = {}
    C = defaultdict(lambda: {'towns': 0, 'buildings': 0, 'road': 0, 'n': Counter(), 'big': Counter(), 'big_b': 0, 'guard_at': Counter(), 'folk_at': Counter(),
                             'guards': Counter(), 'folk': Counter(), 'sellers': Counter(), 'wander': defaultdict(list),
                             'stalls': [], 'lone_stalls': [], 'storage': []})
    for t in townsurvey.survey(db)['towns']:
        bl = [b for b in t['buildings'] if b.get('box')]
        if len(bl) < 3:
            continue
        cult = t['culture'] or '?'
        D = C[cult]
        D['towns'] += 1
        D['buildings'] += len(bl)
        n0 = Counter(D['n'])
        D['road'] += len(t['roads'])
        boxes = [b['box'] for b in bl]
        roads = {tuple(int(v) for v in r.split(',')) for r in t['roads']}
        sqset = {p for p in roads if all((p[0] + i, p[1] + j) in roads for i in (-1, 0, 1) for j in (-1, 0, 1))}
        refs = [r for gx, gy in t['cells'] for r in mapdata.cellmap(db, '#%d,%d' % (gx, gy)).get('refs') or ()]
        refs = [r for r in refs if any(_in_box(b, r['p'][0], r['p'][1], NEAR) for b in boxes)]
        gates = [(r['p'][0], r['p'][1]) for r in refs if r['type'] in ('STAT', 'DOOR') and re.search(r'gate', r['id'], re.I)
                 and not re.search('door', r['id'], re.I)]
        D['n']['gates'] += len(gates)
        D['n']['sign'] += sum(1 for r in refs if r['type'] in ('STAT', 'ACTI') and towndress.SIGN.search(r['id']) and not towndress.HOLDER.search(r['id'].lower()))
        loose = [r for r in refs if r['type'] in THING_T and r.get('b') and not any(_in_box(b, r['p'][0], r['p'][1], -24) for b in boxes)]
        sellers = []
        for r in refs:
            if r['type'] != 'NPC_':
                continue
            ro = role_of(db, r)
            if ro is None:
                continue
            x, y = r['p'][0], r['p'][1]
            o = _person(db, r['id'])
            D['n'][ro] += 1
            gz = mapdata.terrain_z(db, x, y)
            if any(_in_box(b, x, y, -24) for b in boxes):
                at = 'high'                      # (on a building, a balcony, a walkway over the street: counted, not placed)
            elif gates and min(math.hypot(x - g[0], y - g[1]) for g in gates) < GATE_NEAR:
                at = 'gate'
            elif gz is not None and r['p'][2] - gz > 300:
                at = 'high'
            else:
                near_door = min(((math.hypot(x - b['x'], y - b['y']), b) for b in bl), key=lambda v: v[0])
                patch = (int(x // 512), int(y // 512))
                if near_door[0] < DOOR_NEAR:
                    at = 'door:' + ('special' if (near_door[1].get('kind') or 'house') in SPECIAL else 'house')
                elif patch in sqset:
                    at = 'square'
                else:
                    at = 'street'
            w = (o.get('wander') or [0])[0] if o.get('ai') in ('', 'wander') else -1     # (-1: on a travel round)
            if ro == 'guard':
                D['guard_at'][at] += 1
                D['guards']['%s|%s' % (o['cls'], o['faction'])] += 1
                D['wander']['guard|' + at].append(w)
            elif ro == 'seller':
                sellers.append((r, o))
                D['sellers']['%s|%s|%d' % (o['cls'], o['faction'], o['services'])] += 1
            else:
                D['folk_at'][at] += 1
                D['folk']['%s|%s' % (o['cls'], o['faction'])] += 1
                D['wander']['folk|' + at].append(w)
        # the stalls round each seller, in the seller's frame (the seller at its origin, facing +y)
        used = set()
        for r, o in sellers:
            x, y, ang = r['p'][0], r['p'][1], r['p'][5]
            gz = mapdata.terrain_z(db, x, y)
            if gz is None:
                continue
            things, core = [], 0
            for q in loose:
                if id(q) in used or not _stall_thing(q) or math.hypot(q['p'][0] - x, q['p'][1] - y) > SELL_NEAR:
                    continue
                qg = mapdata.terrain_z(db, q['p'][0], q['p'][1])
                if qg is None:
                    continue
                up = q['p'][2] - qg
                if CANOPY.search(q['id']) and _bottom(q) - qg > 60:
                    continue                     # (an awning on a wall, not on posts of its own)
                things.append(towndress._thing(q, x, y, ang, up, False))
                core += bool(STALL_CORE.search(q['id']))
                used.add(id(q))
            things = _held_cloth(things, [q for q in loose if id(q) in used])
            D['n']['seller at stall' if core else 'seller alone'] += 1
            if core and 2 <= len(things) <= SCENE_MAX:
                D['stalls'].append({'town': t['name'], 'things': things, 'up': round(r['p'][2] - gz, 1),
                                    'seller': {'cls': o['cls'], 'faction': o['faction'], 'services': o['services'], 'race': o['race'], 'id': o['id']}})
        # stalls nobody keeps: a stand, a stall or an awning on its posts, and what stands with it
        for q in loose:
            if id(q) in used or not re.search(r'marketstand|market_?stand|stall|awning|canopy', q['id'], re.I) or _size(q) > 900:
                continue
            if any(math.hypot(q['p'][0] - r['p'][0], q['p'][1] - r['p'][1]) < STALL_LONE for r, _o in sellers):
                continue
            qg = mapdata.terrain_z(db, q['p'][0], q['p'][1])
            if qg is None or _bottom(q) - qg > 60:
                continue
            x, y, ang = q['p'][0], q['p'][1], q['p'][5]
            things = []
            for q2 in loose:
                if id(q2) in used or not _stall_thing(q2) or math.hypot(q2['p'][0] - x, q2['p'][1] - y) > SELL_NEAR:
                    continue
                g2 = mapdata.terrain_z(db, q2['p'][0], q2['p'][1])
                if g2 is None:
                    continue
                things.append(towndress._thing(q2, x, y, ang, q2['p'][2] - g2, False))
                used.add(id(q2))
            things = _held_cloth(things, [q2 for q2 in loose if id(q2) in used])
            D['n']['lone stall'] += 1
            if 1 <= len(things) <= SCENE_MAX:
                D['lone_stalls'].append({'town': t['name'], 'things': things})
        # storage standing together, by a wall (framed facing it) or in the open (facing the road); not what is set
        # inside a building's own pieces (a shack's, a porch's), only what stands out in the town (on a dock or a porch's
        # top counts): counted as the town audit counts it, the storage step aimed at 0.94 a building where the game
        # stands 0.53 out in the town, Redoran, lab AFTER3
        solid = _solid(db, refs, boxes)
        st = [q for q in loose if id(q) not in used and STORAGE.search(q['id']) and _size(q) < 700 and not _in_solid(q, solid)]
        every = [q for q in refs if q['type'] in THING_T and q.get('b') and id(q) not in used and STORAGE.search(q['id'])
                 and _size(q) < 700 and not _in_solid(q, solid)]
        D['n']['storage'] += len(every)
        for q in every:
            if not any(math.hypot(q['p'][0] - bd['x'], q['p'][1] - bd['y']) <= towndress.YARD
                       and towndress._local(bd['x'], bd['y'], bd['face'] + math.pi, q['p'][0], q['p'][1])[1] <= towndress.BEHIND for bd in bl):
                D['n']['storage away'] += 1
        left = list(st)
        while left:
            grp = [left.pop()]
            i = 0
            while i < len(grp):
                a = grp[i]
                for j in range(len(left) - 1, -1, -1):
                    if math.hypot(left[j]['p'][0] - a['p'][0], left[j]['p'][1] - a['p'][1]) <= STORE_LINK:
                        grp.append(left.pop(j))
                i += 1
            grp = grp[:STORE_MAX]
            cx = sum(q['p'][0] for q in grp) / len(grp)
            cy = sum(q['p'][1] for q in grp) / len(grp)
            # (and what stands on them: a bottle on a barrel, a basket on a crate)
            ons = [q for q in loose if id(q) not in used and q not in st and q['type'] in GOODS_T + ('STAT',) and towndress._dressing(q)
                   and any(math.hypot(q['p'][0] - g['p'][0], q['p'][1] - g['p'][1]) < 60 for g in grp)]
            best = None
            for b in boxes:
                px, py = min(max(cx, b[0]), b[2]), min(max(cy, b[1]), b[3])
                d = math.hypot(cx - px, cy - py)
                if d > 1 and (best is None or d < best[0]):
                    best = (d, px, py)
            if best and best[0] < WALL_NEAR:
                d, px, py = best
                ang = math.atan2(-(px - cx) / d, -(py - cy) / d)       # (-y toward the wall)
                by = 'wall'
            else:
                ang = towndress._toward_road(cx, cy, roads)
                by = 'road'
                if ang is None:
                    ang, by = 0.0, 'open'
            things = []
            for q in grp + ons:
                qg = mapdata.terrain_z(db, q['p'][0], q['p'][1])
                if qg is not None:
                    things.append(towndress._thing(q, cx, cy, ang, q['p'][2] - qg, False))
                    used.add(id(q))
            # (in a building's yard, before or beside its door, the yards' dressing brings it: towndress's rule)
            yard = False
            for bd in bl:
                if math.hypot(cx - bd['x'], cy - bd['y']) <= towndress.YARD:
                    _lx, ly = towndress._local(bd['x'], bd['y'], bd['face'] + math.pi, cx, cy)
                    if ly <= towndress.BEHIND:
                        yard = True
                        break
            if things:
                D['storage'].append({'town': t['name'], 'things': things, 'by': by, 'gap': round(best[0], 1) if best else None,
                                     'n': len(grp), 'yard': yard})
        if len(bl) >= BIG_TOWN:
            D['big_b'] += len(bl)
            for k, v in D['n'].items():
                D['big'][k] += v - n0.get(k, 0)
        # awnings, canopies and overhangs over a building's door, in its door's frame, by its main piece: laid only on a
        # made building of that very model, where they fit its front as the game's did
        aws = [r for r in loose if AWNING.search(r['id']) and r['type'] == 'STAT']
        for b in bl:
            main = (b.get('main') or '').lower()
            if not main:
                continue
            mine_r = []
            for r in aws:
                lx, ly = towndress._local(b['x'], b['y'], b['face'] + math.pi, r['p'][0], r['p'][1])
                if abs(lx) < AWNING_NEAR[0] and AWNING_NEAR[1] < ly < AWNING_NEAR[2]:
                    near = min(bl, key=lambda o: math.hypot(r['p'][0] - o['x'], r['p'][1] - o['y']))
                    if near is b:
                        mine_r.append(r)
            # (a cloth-only overhang comes with the poles that hold it, or not at all: Firewatch hangs two of Tamriel
            # Data's cloths off Kul-Tei's house front over an egg seller's crates; copied over a Nord house's door
            # alone they hung over an empty street "like rugs", the user's Skethwall 2026-11-07)
            held, marked = [], set()
            for r in list(mine_r):
                if r.get('b') and _stretched(r['b'], r.get('s') or 1.0):
                    ok, poles = cloth_held(db, r, refs, rmemo)
                    if not ok:
                        mine_r.remove(r)
                        continue
                    marked.add(id(r))
                    held += [o for o in poles if not any(o is h for h in held + mine_r)]
            mine_ = [dict(towndress._thing(r, b['x'], b['y'], b['face'] + math.pi, r['p'][2] - b['z'], True), **({'held': True} if id(r) in marked else {}))
                     for r in mine_r + held]
            if mine_ and b.get('interior'):
                AW[main][(b.get('interior') or '').lower()] = mine_
    out = {}
    for cult, D in C.items():
        b = float(max(1, D['buildings']))
        bb = float(max(1, D['big_b']))
        out[cult] = {'towns': D['towns'], 'buildings': D['buildings'], 'road': D['road'],
                     'rate': {k: round(v / b, 4) for k, v in D['n'].items()},
                     'big_buildings': D['big_b'], 'rate_big': {k: round(v / bb, 4) for k, v in D['big'].items()},
                     'gates': D['n']['gates'], 'guard_at': dict(D['guard_at']), 'folk_at': dict(D['folk_at']),
                     'guards': D['guards'].most_common(12), 'folk': D['folk'].most_common(40), 'sellers': D['sellers'].most_common(24),
                     'wander': {k: sorted(v) for k, v in D['wander'].items()},
                     'stalls': D['stalls'], 'lone_stalls': D['lone_stalls'], 'storage': D['storage']}
    out['_awnings'] = dict(AW)
    return out


def ready(db):
    if id(db.recs) in _mem or os.path.isfile(_disk(db)):
        try:
            return learn(db)
        except Exception:
            return None
    import background
    background.start('how the game\'s towns live', lambda: learn(db), task=('townlife', 'learn', []))
    return None


def _cultures(L, cult):
    """The culture first, then its kin, then the rest by how much they hold."""
    kin = list(townsurvey.KIN.get(cult, ()))
    for c, ks in townsurvey.KIN.items():
        if cult in ks:
            kin.append(c)
    rest = sorted((c for c in L if c != cult and c not in kin and not c.startswith('_')), key=lambda c: -L[c]['buildings'])
    return [c for c in [cult] + kin + rest if c in L]


def _pick(L, cult, key, least=3):
    """The culture's own scenes of a kind, else its kin's."""
    for c in _cultures(L, cult):
        if len(L[c].get(key) or ()) >= least:
            return L[c][key]
    return []


def _rate(L, cult, key, B=0):
    """The culture's figure a building (a big town's, for a town of BIG_TOWN buildings or more, when the culture has
    big towns enough), else its kin's."""
    rk, least = ('rate_big', 'big_buildings') if B >= BIG_TOWN else ('rate', 'buildings')
    C = L.get(cult)
    if C and C.get(least, 0) >= 60:
        return C[rk].get(key, 0.0)
    if C and C['buildings'] >= 30:
        return C['rate'].get(key, 0.0)
    near = [c for c in _cultures(L, cult) if L[c]['buildings'] >= 30][:2]
    return sum(L[c]['rate'].get(key, 0.0) for c in near) / max(1, len(near))


# ------------------------------------------------------------------------------------------------ the stalls and storage
STALL_WHOLE = 0.8              # a stall is laid when this share of its ground things fit, every stand and table of it
STORE_WHOLE = 0.75
STALL_TRIES = 60
STORE_TRIES = 6                # (sides tried a cluster)
MARKET_SHARE = 0.6             # (of the stalls, this share in the square when the town has one)
ROAD_SHARE = 0.5               # (of the storage the game stands by its roads, this share laid so: the rest by the walls)
# generic trade signs, by a town's look (none named for a game shop): the set's id words, then each trade's
SIGN_SETS = (('Imperial', r'^t_imp_setcyr_sign'), ('Gold Coast', r'^t_imp_setcyr_sign'), ('Anvil', r'^t_imp_setcyr_sign'),
             ('Nordic', r'^t_nor_set_sign'), ('Reach', r'^t_rga_set_sign'), ('Common', r'^active_sign_c_|^furn_sign_inn_01$|^t_imp_setmw_signshop'))
SIGN_TRADE = {'tavern': r'tavern|inn', 'guild': r'guild', 'smith': r'smith|weapon|armor|arms',
              'shop': r'general|goods|merchant|alchem|potion|apothecary|cloth|books|pawn'}
SIGN_SIDE = (90, 220)          # (beside the door, as the game's hang: 70-250 off its middle)
SIGN_OUT = -45                 # (out from the wall)
SIGN_UP = (165, 215)           # (over the door's foot)
SIGN_WALL = 80                 # (its wall this near: the town audit's own reach for a hung thing)


def _module_ids(db, q, memo):
    """The ids of the pieces a plot's building is made of (its module in townbuild's catalogue), lowercase."""
    try:
        import townbuild
        if 'C' not in memo:
            memo['C'] = townbuild.by_uid(townbuild.catalog(db))
        b = memo['C'].get((q.get('b') or {}).get('uid')) or {}
        return {p['id'].lower() for p in (b.get('m') or {}).get('fpieces') or ()}
    except Exception:
        return set()


def _ground_things(sc):
    return [t for t in sc['things'] if t['z'] < 24]


def _try(db, sc, x, y, ang, space, memo, whole, seller=None):
    import towndress
    before = list(space.polys)
    got = towndress._lay(db, sc, x, y, ang, space, memo)
    ground = _ground_things(sc)
    gl = [g for g in got if g['up'] < 24]
    core = [t for t in ground if STALL_CORE.search(t['id'])]
    core_got = [g for g in gl if STALL_CORE.search(g['id'])]
    ok = ground and len(gl) >= whole * len(ground) and len(core_got) >= len(core)
    if ok and seller is not None:
        # (the seller's own spot: on the ground, in none of the stall's things but an awning over them)
        sx, sy = seller
        if any(towndress._in_poly(g['pts'], sx, sy) for g in gl if not CANOPY.search(g['id'])):
            ok = False
    if not ok:
        space.polys[:] = before
        return None
    return got


def _street_spots(plan, rng, depth):
    """Spots beside the streets, nearest the town's middle first: (x, y, ang facing the street)."""
    try:
        from townbuild import PAINT_SHARE, PAINT_MIN
    except Exception:
        PAINT_SHARE, PAINT_MIN = 0.7, 256
    import towndress
    xs = [q['door'][0] for q in plan['plots'] if q.get('door') and q.get('b')]
    ys = [q['door'][1] for q in plan['plots'] if q.get('door') and q.get('b')]
    if not xs:
        return []
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    out = []
    for st in plan.get('streets') or ():
        r = max(PAINT_MIN, (st.get('w') or 0) / 2.0 * PAINT_SHARE)
        pts = st.get('pts') or []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L_ = math.hypot(bx - ax, by - ay)
            if L_ < 300:
                continue
            ux, uy = (bx - ax) / L_, (by - ay) / L_
            for k in range(int(L_ // 380)):
                t = (k + 0.5 + rng.uniform(-0.3, 0.3)) * 380
                qx, qy = ax + ux * t, ay + uy * t
                for side in (1, -1):
                    nx, ny = -uy * side, ux * side
                    # (depth None: a person's spot on the street itself, off its middle line)
                    off = r * rng.uniform(0.25, 0.8) if depth is None else r + towndress.STREET_MARGIN + depth
                    x, y = qx + nx * off, qy + ny * off
                    out.append((math.hypot(x - mx, y - my) + rng.uniform(0, 600), x, y, math.atan2(-nx, -ny)))
    out.sort()
    return [o[1:] for o in out]


def _depth(sc):
    """How far a stall reaches in front of its seller (+y)."""
    ys = [t['y'] for t in _ground_things(sc)]
    return max([60.0] + ys)


def _stretched(b_, sc_):
    """A canopy model that is a long sheet of cloth (under CLOTH_FLAT thick, CLOTH_LONG or more across): nothing of its own
    holds its far end up. (Measured over the game's towns, cloth_game.py 2026-11-07: Tamriel Data's overhang_01a..10a,
    211-269 by 347-469 by 27-46; the bracket awnings are 76-97 thick and under 250 deep.)"""
    sc_ = sc_ or 1.0
    return bool(b_) and (b_[5] - b_[2]) * sc_ < CLOTH_FLAT and max(b_[3] - b_[0], b_[4] - b_[1]) * sc_ >= CLOTH_LONG


def _pt_poly_dist(pts, x, y):
    import towndress
    if towndress._in_poly(pts, x, y):
        return 0.0
    best = 1e9
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if not L else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def _span_ends(pts, b):
    """The midpoints of a footprint's two short edges (the ends of a cloth's span)."""
    if b[3] - b[0] >= b[4] - b[1]:
        return [((pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2), ((pts[3][0] + pts[0][0]) / 2, (pts[3][1] + pts[0][1]) / 2)]
    return [((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2), ((pts[2][0] + pts[3][0]) / 2, (pts[2][1] + pts[3][1]) / 2)]


def _ends_at_walls(db, id_, x, y, rz, s, polys, memo):
    """Whether each end of a cloth's span lies within WALL_AT of one of the polygons (building footprints, the wall)."""
    import towndress
    pts, b = towndress._rect_of(id_, x, y, rz, s or 1.0, memo, db)
    if not pts:
        return False
    return all(any(_pt_poly_dist(p_, ex, ey) <= WALL_AT for p_ in polys) for ex, ey in _span_ends(pts, b))


def cloth_held(db, r, refs, memo):
    """What holds a stretched cloth up, among a place's refs ({'id', 'p', 's', 'type', 'b'?}): (held, poles). Held by poles
    within CLOTH_HOLD of it (returned, to come along with it), or by a building piece within WALL_AT of each end of its
    long axis (a cloth across an alley). Kul-Tei's in Firewatch hang off one wall over an egg seller's crates: not held."""
    import towndress
    x, y, z = r['p'][0], r['p'][1], r['p'][2]
    poles = [o for o in refs if o is not r and POLE.search(o['id']) and abs(o['p'][2] - z) < 600 and
             math.hypot(o['p'][0] - x, o['p'][1] - y) <= CLOTH_HOLD]
    if poles:
        return True, poles
    big = []
    for o in refs:
        if o is r or o.get('type') != 'STAT' or AWNING.search(o['id']) or math.hypot(o['p'][0] - x, o['p'][1] - y) > 1500:
            continue
        opts, ob = towndress._rect_of(o['id'], o['p'][0], o['p'][1], o['p'][5], o.get('s') or 1.0, memo, db)
        if opts and max(ob[3] - ob[0], ob[4] - ob[1]) * (o.get('s') or 1.0) >= 300 and ob[2] * (o.get('s') or 1.0) + o['p'][2] < z < ob[5] * (o.get('s') or 1.0) + o['p'][2] + 200:
            big.append(opts)
    return _ends_at_walls(db, r['id'], x, y, r['p'][5], r.get('s') or 1.0, big, memo), []


def _door_awnings(db, L, built, memo, space=None):
    """Awnings over doors, on made buildings of the very game building the game hangs them on, as it does: [thing].
    A stretched cloth (_stretched) is laid only with a pole of its list within CLOTH_HOLD (the survey brings a cloth's
    poles along) or with a building footprint or the wall (space's 'plot' and 'wall' polygons) at each end of its span
    here: the game's spanned an alley to a facing wall, and the made town's streets are wider (Kul-Tei's cloths over an
    empty street, the user's Skethwall 2026-11-07)."""
    import towndress
    AWS = L.get('_awnings') or {}
    out = []
    cat_memo = {}
    walls = [p_ for p_ in (space.polys if space is not None else []) if space.kind.get(id(p_)) in ('plot', 'wall')]
    for q in built:
        # (only the very building's own: the same model with its door elsewhere took one 358 in the air and two cut
        # into its walls, lab T5. The made building is the game example its uid names)
        ex = ((q.get('b') or {}).get('uid') or '').split('#', 1)[-1]
        A = AWS.get(((q.get('b') or {}).get('key') or '').lower()) or {}
        if not ex or ex not in A or q.get('door_z') is None:
            continue
        ways = [towndress._door_clear(o['door'][0], o['door'][1], o['face']) for o in built]
        # (and never one the building's own pieces hold already: a Dunmer shack's module carries its awnings, and they
        # were laid a second time 200 over its own, lab b24)
        own = _module_ids(db, q, cat_memo)
        for t in A[ex]:
            if t['id'].lower() in own:
                continue
            wx, wy = towndress._world(q['door'][0], q['door'][1], q['face'] + math.pi, t['x'], t['y'])
            # (on posts that reach the ground, never over a door's way in: a Hlaalu overhang's posts stood on two door
            # fronts in the game test, Sandar 2026-11-03)
            b_ = memo.get(('b', t['id']))
            if b_ is None:
                ri_ = db.resolve_id(t['id'])
                b_ = memo[('b', t['id'])] = (mapdata.object_bounds(db, ri_) if ri_ is not None else None) or (0, 0, 0, 0, 0, 0)
            sc_ = t.get('s') or 1.0
            if _stretched(b_, sc_) and \
                    not any(POLE.search(o['id']) and math.hypot(o['x'] - t['x'], o['y'] - t['y']) <= CLOTH_HOLD for o in A[ex] if o is not t) and \
                    not _ends_at_walls(db, t['id'], wx, wy, (t['rz'] + q['face'] + math.pi) % (2 * math.pi), sc_, walls, memo):
                continue
            # (nor one hung low over a door's way: a balcony 112 over the door front, the in-game walk 2026-11-03)
            if t['z'] + b_[2] * sc_ < AWNING_HEAD:
                rz_ = (t['rz'] + q['face'] + math.pi) % (2 * math.pi)
                pts_, _bb = towndress._rect_of(t['id'], wx, wy, rz_, sc_, memo, db)
                if pts_ and any(towndress._overlap(pts_, w_) for w_ in ways):
                    continue
            out.append({'id': t['id'], 'p': [round(wx, 2), round(wy, 2), round(q.get('sill_z', q['door_z']) + t['z'], 2), t.get('rx') or 0.0, t.get('ry') or 0.0,
                                             round((t['rz'] + q['face'] + math.pi) % (2 * math.pi), 5)],
                        's': t.get('s') or 1.0, 'role': 'awning', 'hung': True, 'on': None, 'up': 0.0})
    return out


def dress(db, plan, rng, space, memo, laid=(), amount=1.0):
    """Stalls (with their sellers' spots) and storage for a town being dressed, in its dressing's space. [thing], each
    {'id', 'p', 's', 'pts', 'role', 'stall'?}; SEEN['sellers'] = the spots of the stalls' sellers."""
    import towndress
    L = ready(db)
    SEEN.clear()
    SEEN['sellers'] = []
    if not L:
        return []
    cult = plan.get('culture')
    trade = plan.get('trade') or ''
    built = [q for q in plan['plots'] if q.get('b') and q.get('door')]
    B = len(built)
    if not B:
        return []
    # awnings over doors, on buildings of the models the game hangs them on, as often as it does
    out = _door_awnings(db, L, built, memo, space)
    SEEN['awnings'] = len(out)
    # the stalls: as many as the culture's towns have outdoor sellers at a stall a building, and the lone ones
    scenes = [s for s in _pick(L, cult, 'stalls') if _ground_things(s)]
    lone = [s for s in _pick(L, cult, 'lone_stalls', 2) if _ground_things(s)]
    n_sell = int(_rate(L, cult, 'seller at stall', B) * B * amount + rng.random())
    n_lone = int(_rate(L, cult, 'lone stall', B) * B * amount + rng.random())
    SEEN['want'] = {'stalls': n_sell, 'lone stalls': n_lone}
    spots = []
    if plan.get('square'):
        sx, sy, sr = plan['square']
        k0 = rng.uniform(0, 2 * math.pi)
        for ring in (0.8, 0.55, 1.05):
            for k in range(10):
                a = k0 + k * 2 * math.pi / 10 + ring
                x, y = sx + math.cos(a) * sr * ring, sy + math.sin(a) * sr * ring
                spots.append(('square', x, y, math.atan2(sx - x, sy - y)))
    n_sq = int(round((n_sell + n_lone) * MARKET_SHARE)) if spots else 0
    made_sell = made_lone = 0
    stall_n = 0
    for want, pool, kind in ((n_sell, scenes, 'sell'), (n_lone, lone, 'lone')):
        if not pool:
            continue
        # (no scene over and over: a big town set the same two cloth overhangs out 28 times, "the same arrangement,
        # used way too often", the user 2026-11-06. Each scene a few times at most, the lone ones fewer still)
        if kind == 'lone':
            want = min(want, LONE_MOST * len(pool))
        cap = max(2, int(math.ceil(want / float(len(pool)))))
        times = {}
        tries = 0
        while want > 0 and tries < STALL_TRIES:
            tries += 1
            open_ = [s_ for s_ in pool if times.get(id(s_), 0) < cap]
            if not open_:
                break
            sc = _lean_choice(rng, open_, trade)
            times[id(sc)] = times.get(id(sc), 0) + 1
            if rng.random() < 0.5:
                sc = {'things': [dict(t, x=-t['x'], rz=(-t['rz']) % (2 * math.pi)) for t in sc['things']], 'seller': sc.get('seller'), 'up': sc.get('up')}
            depth = _depth(sc) if kind == 'sell' else 0.0
            if spots and n_sq > 0:
                _w, x, y, ang = spots.pop(0)
            else:
                st = _street_spots(plan, rng, depth)
                if not st:
                    break
                x, y, ang = st[min(len(st) - 1, int(rng.random() ** 2 * len(st)))]
            if kind == 'lone':
                ang = ang + rng.choice((0.0, math.pi / 2, -math.pi / 2, math.pi))
            gz = mapdata.terrain_z(db, x, y)
            if gz is None or gz < 0:
                continue
            got = _try(db, sc, x, y, ang, space, memo, STALL_WHOLE, (x, y) if kind == 'sell' else None)
            if not got:
                continue
            if spots and n_sq > 0 and abs(math.hypot(x - plan['square'][0], y - plan['square'][1]) - plan['square'][2]) < plan['square'][2]:
                n_sq -= 1
            for g in got:
                g['role'] = 'stall'
                g['stall'] = stall_n
            out.extend(got)
            if kind == 'sell':
                seller_sq = towndress._world(x, y, ang, 0, 0)
                pts = [towndress._world(x, y, ang, lx, ly) for lx, ly in ((-28, -28), (28, -28), (28, 28), (-28, 28))]
                space.take(pts)
                SEEN['sellers'].append({'x': seller_sq[0], 'y': seller_sq[1], 'rz': ang % (2 * math.pi), 'seller': sc.get('seller') or {},
                                        'stall': stall_n})
                made_sell += 1
            else:
                made_lone += 1
            stall_n += 1
            want -= 1
    # storage: by the houses' side and back walls, as much as the game's towns have a building, less what the yards brought
    clusters = _pick(L, cult, 'storage')
    # (what the game stands away from its doors' yards, by the side and back walls; less what the yards brought beyond
    # the game's own yards, Redoran's and Nordic yards carry their storage already)
    have = sum(1 for g in list(laid) + out if STORAGE.search(g['id']) and not g.get('hung'))
    want = min(_rate(L, cult, 'storage away', B) * B, _rate(L, cult, 'storage', B) * B - have) * amount
    SEEN['want']['storage'] = round(want, 1)
    by_wall = [c for c in clusters if c['by'] == 'wall'] or clusters
    by_road = [c for c in clusters if c['by'] != 'wall']
    placed = 0
    tries = 0
    why = Counter()
    while want > 0 and by_wall and tries < max(60, 10 * B):
        tries += 1
        q = rng.choice(built)
        rect = q.get('rect')
        if not rect:
            continue
        if by_road and rng.random() < ROAD_SHARE * len(by_road) / float(len(clusters)):
            # (stacked by a street, as the game's stand where carts unload)
            sc = _lean_choice(rng, by_road, trade)
            st = _street_spots(plan, rng, _depth(sc))
            if not st:
                continue
            x, y, ang = st[rng.randrange(len(st))]
            ang += math.pi                       # (-y toward the street)
        else:
            sc = _lean_choice(rng, by_wall, trade)
            gap = min(260.0, max(48.0, sc.get('gap') or 96.0))
            cx = sum(p[0] for p in rect) / 4.0
            cy = sum(p[1] for p in rect) / 4.0
            dx_, dy_ = q['door'][0], q['door'][1]
            edges = []
            for i in range(4):
                (ax, ay), (bx, by) = rect[i], rect[(i + 1) % 4]
                edges.append((math.hypot((ax + bx) / 2.0 - dx_, (ay + by) / 2.0 - dy_), (ax, ay), (bx, by)))
            edges.sort()
            _d, (ax, ay), (bx, by) = rng.choice(edges[1:])          # (never the door's own wall)
            L_ = math.hypot(bx - ax, by - ay)
            if L_ < 200:
                continue
            t = rng.uniform(0.15, 0.85)
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            nx, ny = -(by - ay) / L_, (bx - ax) / L_
            if (px - cx) * nx + (py - cy) * ny < 0:
                nx, ny = -nx, -ny                # (outward)
            x, y = px + nx * gap, py + ny * gap
            ang = math.atan2(nx, ny)             # (-y toward the wall)
        c0 = dict(towndress.LAST.get('count') or {})
        got = _try(db, sc, x, y, ang, space, memo, STORE_WHOLE)
        if not got:
            c1 = towndress.LAST.get('count') or {}
            for k, v in c1.items():
                if v > c0.get(k, 0) and k.startswith('refused'):
                    why[k] += v - c0.get(k, 0)
            continue
        for g in got:
            g['role'] = 'storage'
        out.extend(got)
        want -= sum(1 for g in got if STORAGE.search(g['id']))
        placed += 1
    SEEN['storage why'] = dict(why.most_common(6))
    SEEN['storage tries'] = tries
    # shop signs by the doors of the town's trades, as often as the culture's game towns hang them a building
    n_sign = int(_rate(L, cult, 'sign', B) * B * amount + rng.random())
    signs = _signs(db, L, cult, plan, rng, n_sign, memo)
    out.extend(signs)
    SEEN['made'] = {'stalls': made_sell, 'lone stalls': made_lone, 'storage clusters': placed, 'signs': len(signs)}
    SEEN['laid'] = [(g['id'], round(g['p'][0]), round(g['p'][1]), round(g['p'][2]), g.get('role')) for g in out]
    return out


def _signs(db, L, cult, plan, rng, n, memo):
    """n hung trade signs by the doors of the town's shops, taverns and guilds."""
    import doors
    import towndress
    if n <= 0:
        return []
    pat = next((rx for c, rx in SIGN_SETS if c == cult), None)
    if pat is None:
        return []                                # (the Dunmer towns hang banners: their yards bring them)
    ids = sorted(db.recs[lst[-1]][1] for (tag, k), lst in db.by_key.items() if tag == 'ACTI' and lst and re.search(pat, k)
                 and towndress.SIGN.search(k) and k not in towndress.NAMED)
    if not ids:
        return []
    plots = [q for q in plan['plots'] if q.get('b') and q.get('door') and q.get('kind') in ('shop', 'tavern', 'guild')]
    rng.shuffle(plots)
    out = []
    for q in plots:
        if len(out) >= n:
            break
        trade = SIGN_TRADE.get(q['kind'])
        cands = [i for i in ids if re.search(trade, i, re.I)] if trade else []
        if q['kind'] == 'shop':
            gen = [i for i in cands if re.search('general|goods|merchant', i, re.I)]
            cands = gen if gen and rng.random() < 0.7 else cands
        if not cands or q.get('door_z') is None:
            continue
        sid = rng.choice(cands)
        ang = q['face'] + math.pi
        for side in rng.sample((1, -1), 2):
            lx = side * rng.uniform(*SIGN_SIDE)
            wx, wy = towndress._world(q['door'][0], q['door'][1], ang, lx, SIGN_OUT)
            z = q.get('sill_z', q['door_z']) + rng.uniform(*SIGN_UP)       # (over the sill: the door's own height is its middle on some doors)
            g = {'id': sid, 'p': [round(wx, 2), round(wy, 2), round(z, 2), 0.0, 0.0, round(ang % (2 * math.pi), 5)], 's': 1.0}
            if not towndress._held(db, g, q['face'], memo):
                continue
            # (and its wall near enough to square it against: held by a wall 120 off to its side, a sign hung in the
            # air beside a porch, lab AFTER)
            sc = doors._local_scene(db, {'p': [wx, wy, z, 0, 0, 0]})
            if not any(sc.nearest_any((wx, wy, z), (math.cos(a_ * math.pi / 4), math.sin(a_ * math.pi / 4), 0.0), SIGN_WALL) is not None
                       for a_ in range(8)):
                continue
            g.update(hung=True, on=None, role='sign', up=0.0)
            out.append(g)
            break
    return out


# ------------------------------------------------------------------------------------------------ after the ground is fitted
SETTLE_SINK = 10               # (a thing's foot this far under the fitted ground is raised onto it)
SETTLE_STEEP = 64              # (a stand, table or crate whose ground now rises this much across goes, its stall whole:
                               # towndress's STEEP_MAX, what it would not have laid them on)
SETTLE_CORE = re.compile(r'table|stand|stall|counter|crate|barrel|cart|wagon|bench|awning|canopy', re.I)


def settle(db, refs):
    """The stalls and storage set down again on the ground as it was fitted round the buildings after the dressing (the
    land rose under a hill town's stall and buried its wares, lab AFTER): a ground thing sunk under it raised onto it; a
    stand, table or crate whose ground turned steep taken away, with the rest of its stall. refs: [(cell key, ref key,
    role, stall n)]. -> the stalls taken away."""
    import editing
    from project import ref_info, set_ref_pos, unb64
    memo = {}
    gone_stalls = set()
    rows = []
    for key, rk, role, n in refs:
        m = {r['k']: r for r in mapdata.cellmap(db, key).get('refs') or ()}
        r = m.get(rk)
        if not r or not r.get('b') or role in ('sign', 'awning'):
            continue
        rows.append((key, rk, role, n, r))
    raised = 0
    for key, rk, role, n, r in rows:
        b, sc = r['b'], r['s'] or 1.0
        x, y, z = r['p'][0], r['p'][1], r['p'][2]
        g = mapdata.terrain_z(db, x, y)
        if g is None:
            continue
        foot = z + b[2] * sc
        if SETTLE_CORE.search(r['id']) and foot - g < 24:
            import towndress
            pts, _b = towndress._rect_of(r['id'], x, y, r['p'][5], sc, memo, db)
            gs = [mapdata.terrain_z(db, px, py) for px, py in pts or ()]
            if gs and None not in gs and max(gs) - min(gs) > SETTLE_STEEP:
                if n is not None:
                    gone_stalls.add(n)
                else:
                    rows_gone = [(key, rk)]
                    _drop(db, rows_gone)
                continue
        if foot < g - SETTLE_SINK and foot - g > -200:
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            raw = (cell.get('refs') or {}).get(rk)
            if not raw:
                continue
            subs = [(t, unb64(d) if isinstance(d, str) else d) for t, d in raw['subs']]
            pos = list(ref_info(subs)[1])
            pos[2] = round(g - b[2] * sc - 2, 2)
            editing._store(cell, rk, raw.get('origin'), raw.get('idx'), set_ref_pos(subs, tuple(pos)))
            raised += 1
    if gone_stalls:
        _drop(db, [(key, rk) for key, rk, role, n, r in rows if n in gone_stalls] +
              [(key, rk) for key, rk, role, n in refs if n in gone_stalls and role in ('sign', 'awning')])
    SEEN['settled'] = {'raised': raised, 'stalls taken away': len(gone_stalls)}
    SEEN['gone stalls'] = sorted(gone_stalls)
    db.sync_project()
    return gone_stalls


def _drop(db, keys):
    import editing
    for key, rk in keys:
        try:
            cell, _refs = editing._cell(db, key)
        except editing.EditError:
            continue
        (cell.get('refs') or {}).pop(rk, None)


# ------------------------------------------------------------------------------------------------ the people outdoors
PERSON_CLEAR = 40              # (a person stands this clear of things and buildings)
PATROL = 1024                  # (a guard's round: how far a patrol wanders, at most)
# (townsfolk are none of the game's service people, who stand in their shops or ply their routes: a caravaner or a
# riverstrider outdoors with nowhere to take you, lab b13)
NOT_FOLK = re.compile(r'service|caravaner|shipmaster|gondolier|riverstrider|guide|silt|boatman|ferry|slave', re.I)
FOLK_FACTION = 0.15            # (a townsperson's faction only when this share of the culture's townsfolk are of it: an
                               # Indoril commoner and a Navy sailor stood in an inland Hlaalu town, lab b13)
DOOR_OUT = 260                 # (a person by a door stands this far out of it)


def _wander(L, cult, key, rng, default):
    """How far one of the culture's people of this kind and spot wanders, as the game's do (a game patrol walking a
    round of travel points wanders PATROL far: a made town has no rounds of its own)."""
    for c in _cultures(L, cult)[:3]:
        ws = (L[c].get('wander') or {}).get(key) or ()
        if len(ws) >= 3:
            w = rng.choice(ws)
            return PATROL if w < 0 else int(min(PATROL, w))
    return default


def _classes(L, cult, key, least=4):
    for c in _cultures(L, cult):
        lst = L[c].get(key) or []
        if sum(n for _k, n in lst) >= least:
            return lst
    return []


def _ctx(L, cult, key):
    for c in _cultures(L, cult):
        d = L[c].get(key) or {}
        if sum(d.values()) >= 4:
            return d
    return {'street': 1}


def _free_spot(db, x, y, polys, taken):
    """Can a person stand here: dry ground, not steep, clear of buildings, things, doors' ways and other people."""
    import towndress
    gz = mapdata.terrain_z(db, x, y)
    if gz is None or gz < 0:
        return None
    for ox, oy in ((PERSON_CLEAR, 0), (-PERSON_CLEAR, 0), (0, PERSON_CLEAR), (0, -PERSON_CLEAR)):
        g2 = mapdata.terrain_z(db, x + ox, y + oy)
        if g2 is None or abs(g2 - gz) > 36:
            return None
    sq = [(x - PERSON_CLEAR, y - PERSON_CLEAR), (x + PERSON_CLEAR, y - PERSON_CLEAR), (x + PERSON_CLEAR, y + PERSON_CLEAR), (x - PERSON_CLEAR, y + PERSON_CLEAR)]
    if any(towndress._overlap(sq, p) for p in polys):
        return None
    if any(math.hypot(x - a, y - b) < 2 * PERSON_CLEAR for a, b in taken):
        return None
    return gz


def _obb(db, r, memo):
    import towndress
    pts, _b = towndress._rect_of(r['id'], r['p'][0], r['p'][1], r['p'][5], r['s'] or 1.0, memo, db)
    return pts


def _polys(db, plan, cells, new_refs, W):
    """What people keep clear of: the buildings' plots, the wall, every made thing, the doors' ways in."""
    import towndress
    memo = {}
    polys = [list(map(tuple, q['rect'])) for q in plan['plots'] if q.get('b') and q.get('rect')]
    polys += [[tuple(p) for p in o] for o in plan.get('obstacles') or ()]
    polys += [p_['corners'] for p_ in (W or {}).get('pieces') or () if p_.get('corners')]
    for q in plan['plots']:
        if q.get('door') and q.get('b'):
            polys.append(towndress._door_clear(q['door'][0], q['door'][1], q['face']))
    for ck in cells:
        for r in mapdata.cellmap(db, ck).get('refs') or ():
            if r['k'] in new_refs and r['type'] not in ('NPC_', 'CREA') and r.get('b'):
                b, s = r['b'], r['s'] or 1.0
                if (b[5] - b[2]) * s < 24 or max(b[3] - b[0], b[4] - b[1]) * s > 3000:
                    continue                     # (flat paving, or a whole wall run: its pieces' corners are in already)
                if r['p'][2] + b[2] * s > (mapdata.terrain_z(db, r['p'][0], r['p'][1]) or 0) + 180:
                    continue                     # (high over the ground: a sign, an awning's roof, a bridge)
                pts = _obb(db, r, memo)
                if pts:
                    polys.append(pts)
    return polys


def _gates(W):
    return [p_ for p_ in (W or {}).get('pieces') or () if p_.get('pose') is not None and hasattr(p_['pose'], 'x')
            and (p_.get('kind') == 'gate' or re.search(r'gate', p_.get('id') or '', re.I))]


def _spots_for(db, plan, at, rng, W, n, polys, taken):
    """n spots of a kind ('gate', 'door:special', 'door:house', 'square', 'street'): [(x, y, z, rz)]."""
    import towndress
    cands = []
    built = [q for q in plan['plots'] if q.get('b') and q.get('door')]
    if at == 'gate' and W:
        mid = (sum(q['door'][0] for q in built) / max(1, len(built)), sum(q['door'][1] for q in built) / max(1, len(built)))
        for p_ in _gates(W):
            gx, gy = p_['pose'].x, p_['pose'].y
            d = math.hypot(mid[0] - gx, mid[1] - gy) or 1
            ux, uy = (mid[0] - gx) / d, (mid[1] - gy) / d
            for out_ in (420, 560):
                for side in (1, -1):
                    x = gx + ux * out_ - uy * 260 * side
                    y = gy + uy * out_ + ux * 260 * side
                    cands.append((x, y, math.atan2(ux, uy)))          # (facing into the town, the gate at their back)
    elif at.startswith('door:'):
        want_special = at == 'door:special'
        for q in built:
            if (q.get('kind') in SPECIAL) != want_special:
                continue
            fx, fy = q['door'][0], q['door'][1]
            rect = q.get('rect') or []
            if rect:
                cx, cy = sum(p[0] for p in rect) / len(rect), sum(p[1] for p in rect) / len(rect)
            else:
                cx, cy = fx - math.sin(q['face']), fy - math.cos(q['face'])
            d = math.hypot(fx - cx, fy - cy) or 1
            ux, uy = (fx - cx) / d, (fy - cy) / d
            for side in (1, -1, 0.6, -0.6):
                x = fx + ux * DOOR_OUT - uy * 200 * side
                y = fy + uy * DOOR_OUT + ux * 200 * side
                cands.append((x, y, math.atan2(ux, uy) + rng.uniform(-0.4, 0.4)))
        rng.shuffle(cands)
    elif at == 'square' and plan.get('square'):
        sx, sy, sr = plan['square']
        for k in range(24):
            a = rng.uniform(0, 2 * math.pi)
            rr = sr * rng.uniform(0.2, 0.9)
            x, y = sx + math.cos(a) * rr, sy + math.sin(a) * rr
            cands.append((x, y, rng.uniform(0, 2 * math.pi)))
    else:
        for x, y, ang in _street_spots(plan, rng, None)[:n * 16]:
            cands.append((x, y, ang + math.pi + rng.uniform(-1.2, 1.2)))
        rng.shuffle(cands)
    if len(cands) < n * 4 and at in ('street', 'square'):
        # (an open town, no streets: between its buildings, round their doors)
        for q in built:
            for _k in range(6):
                a = rng.uniform(0, 2 * math.pi)
                rr = rng.uniform(300, 900)
                cands.append((q['door'][0] + math.sin(a) * rr, q['door'][1] + math.cos(a) * rr, rng.uniform(0, 2 * math.pi)))
        rng.shuffle(cands)
    out = []
    for x, y, rz in cands:
        if len(out) >= n:
            break
        z = _free_spot(db, x, y, polys, taken)
        if z is None:
            continue
        taken.append((x, y))
        out.append((x, y, z, rz % (2 * math.pi)))
    return out


def _plan_people(db, L, plan, rng, W, polys):
    """[(role, spot, cls, faction, wander, seller)] for the town: sellers at their stalls, guards, townsfolk."""
    cult = plan.get('culture')
    B = sum(1 for q in plan['plots'] if q.get('b') and q.get('door'))
    taken = []
    out = []
    gone = set(SEEN.get('gone stalls') or ())
    for s in SEEN.get('sellers') or ():
        if s['stall'] in gone:
            continue
        z = mapdata.terrain_z(db, s['x'], s['y'])
        if z is None:
            continue
        taken.append((s['x'], s['y']))
        out.append(('seller', (s['x'], s['y'], z, s['rz']), s['seller'], s['stall']))
    # (sellers with no stall: a peddler by a door, in the street)
    n_alone = int(_rate(L, cult, 'seller alone', B) * B + rng.random())
    for sp in _spots_for(db, plan, 'street', rng, W, n_alone, polys, taken):
        out.append(('seller', sp, {}, None))
    has_gate = bool(_gates(W))
    for role, rkey, ckey in (('guard', 'guard', 'guard_at'), ('folk', 'folk', 'folk_at')):
        n = int(_rate(L, cult, rkey, B) * B + rng.random())
        ctx = dict(_ctx(L, cult, ckey))
        ctx.pop('high', None)                      # (the wall walks: at the gates instead)
        if not has_gate:
            ctx.pop('gate', None)
        elif role == 'guard':
            ctx['gate'] = max(ctx.get('gate', 0), 0.25 * sum(ctx.values()))
        if not plan.get('square'):
            ctx.pop('square', None)
        tot = float(sum(ctx.values())) or 1.0
        # (each kind of spot its share, the remainder to the street)
        want = {k: int(n * v / tot + rng.random()) for k, v in ctx.items()}
        for at, k in sorted(want.items(), key=lambda kv: kv[0] != 'gate'):
            if k <= 0:
                continue
            got = _spots_for(db, plan, at, rng, W, k, polys, taken)
            if len(got) < k and at != 'street':
                got += _spots_for(db, plan, 'street', rng, W, k - len(got), polys, taken)
            SEEN.setdefault('spots', {})['%s %s' % (role, at)] = (k, len(got))
            for sp in got:
                out.append((role, sp, at, None))
    return out


def _valid(db, tag, name):
    ri = db.resolve_id(name) if name else None
    return ri is not None and db.recs[ri][0] == tag


def people(db, plan, culture, seed, cells, new_refs, W=None, stall_refs=None):
    """The town's people outdoors, made and placed (no commit: inside the town's own). stall_refs: {stall n: [(cell key,
    ref key)]}, the stalls' things, owned by their sellers. -> {'people', 'guards', 'sellers', 'folk', 'owned'}."""
    import castsurvey
    import create
    import editing
    import populate
    from project import set_ref_pos, zs
    L = ready(db)
    S = castsurvey.ready(db) if hasattr(castsurvey, 'ready') else castsurvey.survey(db)
    if not L or not S:
        return {'people': 0}
    rng = random.Random('%s|%s|town life' % (seed, culture))
    polys = _polys(db, plan, cells, new_refs, W)
    wanted = _plan_people(db, L, plan, rng, W, polys)
    cast = S['casts'].get('outdoors') or S['casts'].get('house') or {}
    guards = _classes(L, culture, 'guards')
    folk = [[k, n] for k, n in _classes(L, culture, 'folk') if not NOT_FOLK.search(k.split('|')[0])]
    import towntrade
    # (what the town lives by: its fishers, farmers or miners in the streets as often as the game's towns of that trade
    # have them, and other trades' people seldom; towntrade.FOLK_SHARE)
    folk = towntrade.lean_pairs(folk, plan.get('trade'), towntrade.canon_of(S['classes']))
    tot_f = float(sum(n for _k, n in folk)) or 1.0
    fshare = Counter()
    for k, n in folk:
        fshare[k.split('|')[1] if '|' in k else ''] += n / tot_f
    sellers_l = _classes(L, culture, 'sellers', 2)
    G = {}                                       # (a few guard records shared by the town's guards)
    made = []
    taken_names = set()
    mine = db.project.plugin.lower()
    counts = Counter()

    def make_person(cls, faction, role):
        if cls not in S['classes'] or not _valid(db, 'CLAS', cls):
            return None
        params = {'faction': faction} if faction and _valid(db, 'FACT', faction) else {}
        p = populate.person(db, S, rng, cls, cast, params, taken=taken_names, role=role)
        taken_names.add(p['name'])
        p['fight'] = min(int(p.get('fight') or 30), TOWN_FIGHT)
        return p

    def new_record(p):
        nid = create.suggest_id(db, create._prefix(db), p['name'])
        k = 1
        while db.resolve_id(nid) is not None or any(m[0].lower() == nid.lower() for m in made):
            k += 1
            nid = create.suggest_id(db, create._prefix(db), '%s %d' % (p['name'], k))
        db.project.set_record('NPC_', nid.lower(), 0, populate._npc_record(db, nid, p), created=True)
        made.append((nid, p))
        return nid

    placed = []
    for role, sp, at, extra in wanted:
        x, y, z, rz = sp
        if role == 'seller':
            info, at = at or {}, 'stall'
            cls, fac = info.get('cls') or '', info.get('faction') or ''
            if cls not in S['classes'] and sellers_l:
                pk = _w_pick(rng, sellers_l)
                cls, fac = pk[0], pk[1] if len(pk) > 1 else ''
                info = dict(info, services=int(pk[2]) if len(pk) > 2 and pk[2].isdigit() else 0)
            p = make_person(cls, fac, 'seller')
            if p is None and sellers_l:
                c2, f2 = _w_pick(rng, sellers_l)[:2]
                p = make_person(c2, f2, 'seller')
            if p is None:
                continue
            if not (p['services'] & BARTER):
                p['services'] = (p['services'] | (int(info.get('services') or 0) & BARTER)) or 0x400
            p['gold'] = max(int(p.get('gold') or 0), 300)
            p['wander'] = 0                       # (a seller keeps to their stall)
            nid = new_record(p)
            p['stall'] = extra
            counts['sellers'] += 1
        elif role == 'guard':
            # (posted guards stand; the street's walk their rounds, a record of their own, as the game's patrols)
            walk = at == 'street'
            key = (walk, rng.randrange(GUARD_KINDS - 1 if walk else GUARD_KINDS))
            if key not in G:
                cf = _w_pick(rng, guards) if guards else ('Guard', '')
                p = make_person(cf[0], cf[1], 'guard') or make_person('Guard', '', 'guard')
                if p is None:
                    continue
                p['wander'] = _wander(L, culture, 'guard|street', rng, 512) if walk else 0
                G[key] = (new_record(p), p)
            nid, p = G[key]
            counts['guards'] += 1
        else:
            cf = _w_pick(rng, folk) if folk else ('Commoner', '')
            fac = cf[1] if len(cf) > 1 and fshare.get(cf[1], 0) >= FOLK_FACTION else ''
            p = make_person(cf[0], fac, 'folk')
            if p is None:
                continue
            p['wander'] = _wander(L, culture, 'folk|' + at, rng, 256)
            nid = new_record(p)
            counts['folk'] += 1
        placed.append((nid, role, (x, y, z + 4, rz), p, at))
    if not made:
        return {'people': 0}
    db.sync_project()
    owners = {}
    for nid, role, pos, p, at in placed:
        key = '#%d,%d' % (math.floor(pos[0] / 8192.0), math.floor(pos[1] / 8192.0))
        try:
            cell, _refs = editing._cell(db, key)
        except editing.EditError:
            continue
        rk = db.project.new_ref_key()
        editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(nid))], (pos[0], pos[1], pos[2], 0.0, 0.0, pos[3]), 1.0))
        new_refs.add(rk)
        if isinstance(cells, set):
            cells.add(key)
        if role == 'seller':
            owners[p['stall']] = nid
    # the stalls' goods and stock are their sellers': taking them is theft
    owned = 0
    for n, nid in owners.items():
        for key, rk in (stall_refs or {}).get(n, ()):
            try:
                cell, refs = editing._cell(db, key)
            except editing.EditError:
                continue
            from project import ref_info, unb64
            raw = (cell.get('refs') or {}).get(rk)
            if not raw:
                continue
            subs = [(t, unb64(d) if isinstance(d, str) else d) for t, d in raw['subs']]
            rid = ref_info(subs)[0]
            ri = db.resolve_id(rid)
            if ri is None or db.recs[ri][0] not in ('CONT',) + GOODS_T or any(t in ('ANAM', 'CNAM') for t, _d in subs):
                continue
            at_ = next((i for i, (t, _d) in enumerate(subs) if t == 'DATA'), len(subs))
            subs[at_:at_] = [('ANAM', zs(nid))]
            editing._store(cell, rk, raw.get('origin', mine), raw.get('idx', int(rk.rsplit('|', 1)[1])), subs)
            owned += 1
    SEEN['people'] = dict(counts)
    SEEN['owned'] = owned
    return {'people': sum(counts.values()), 'guards': counts['guards'], 'sellers': counts['sellers'], 'folk': counts['folk'],
            'owned': owned, 'records': len(made)}


def _lean_choice(rng, pool, trade):
    """A scene from the pool, those carrying the goods the town lives by (fish, crops, ore and carts) picked
    towntrade.GOODS_LEAN times as often. A town of no trade: rng.choice, the same picks as before."""
    if not trade:
        return rng.choice(pool)
    import towntrade
    ws = [towntrade.goods_weight(s, trade) for s in pool]
    t = rng.random() * sum(ws)
    for s, w in zip(pool, ws):
        t -= w
        if t <= 0:
            return s
    return pool[-1]


def _w_pick(rng, pairs):
    """A weighted pick from [['cls|faction|...', n]] -> the key split."""
    tot = sum(n for _k, n in pairs)
    t = rng.random() * tot
    for k, n in pairs:
        t -= n
        if t <= 0:
            return k.split('|')
    return pairs[-1][0].split('|')
