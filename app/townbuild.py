"""Building a planned town (townplan.py): the culture's own buildings on its plots, then (later stages) the ground under
them, the streets' road, and the dressing.

The buildings are the game's own, whole, from the exterior survey (exteriorsurvey modules: every building outside a
game interior's door, its pieces in its door's frame, door at the origin, +y inward, the ground in front of the door
at fground). Each is catalogued with its culture (townsurvey.town_style of its main piece), its kind (from the
interiors it serves) and its footprint (its pieces' boxes, turned, in its door's frame). A plot takes a building of the
town's culture and the plot's kind about its size, set down with its middle on the plot's and its door facing the
plot's way."""
import math
import random
import re
from collections import Counter

import mapdata
import townsurvey

_cat = {}
WALLISH = re.compile(r'wall|gate|rampart|parapet|battlement|palisade|fence', re.I)
MAX_ACROSS = 3200               # a building wider or deeper than this is a compound or a town wall, not a plot's
NEAR_CULTURES = {'Common': ('Imperial', 'Nordic'), 'Imperial': ('Common',), 'Nordic': ('Common',), 'Dunmer': ('Velothi', 'Redoran'),
                 'Velothi': ('Dunmer', 'Indoril'), 'Indoril': ('Velothi', 'Dunmer'), 'Redoran': ('Dunmer', 'Velothi'),
                 'Mournhold': ('Indoril', 'Velothi'), 'Reach': ('Nordic', 'Common'), 'Hlaalu': ('Dunmer',), 'Telvanni': ('Dunmer',),
                 'Ashlander': (), 'Stronghold': ('Velothi',),
                 # (only when a look has fewer than 12 buildings of its own: Anvil's and the Gold Coast's never mix otherwise)
                 'Anvil': ('Gold Coast',), 'Gold Coast': ('Anvil',)}


def family(key):
    """A building's family by its main piece's name: ex_imp, ex_common, t_imp_setgc, t_de_setnecrom ..."""
    p = re.sub(r'[_ ]?\d+[a-z]?$', '', key.lower()).split('_')
    return '_'.join(p[:3] if p[0] == 't' else p[:2]) if len(p) > 1 else p[0]


_co = {}
_mix = {}


def family_mix(db):
    """{lead family: {'towns': game towns it leads, 'cultures': {culture: n}, 'mix': {family: share of their buildings}}}:
    in the game's towns where a family has the most buildings, what share of all their buildings each family has
    (Pelagiad-like ex_imp towns: their houses ex_common and ex_nord, their fort ex_imp)."""
    k = id(db.recs)
    if k not in _mix:
        out = {}
        for t in townsurvey.survey(db)['towns']:
            fs = {}
            for b in t['buildings']:
                if b.get('main'):
                    f = family(b['main'])
                    fs[f] = fs.get(f, 0) + 1
            if not fs:
                continue
            lead = max(fs, key=fs.get)
            o = out.setdefault(lead, {'towns': 0, 'cultures': {}, 'n': {}})
            o['towns'] += 1
            o['cultures'][t['culture']] = o['cultures'].get(t['culture'], 0) + 1
            for f, n in fs.items():
                o['n'][f] = o['n'].get(f, 0) + n
        for o in out.values():
            tot = float(sum(o['n'].values()) or 1)
            o['mix'] = {f: n / tot for f, n in o.pop('n').items()}
        _mix[k] = out
    return _mix[k]


def families_together(db):
    """{family: {family: game towns with both}}: which families the game's own towns mix."""
    k = id(db.recs)
    if k not in _co:
        co = {}
        for t in townsurvey.survey(db)['towns']:
            fs = {family(b['main']) for b in t['buildings'] if b.get('main')}
            for a in fs:
                for b in fs:
                    co.setdefault(a, {})
                    co[a][b] = co[a].get(b, 0) + 1
        _co[k] = co
    return _co[k]


YARD_NEAR = 64                 # a yard's wall or fence this near the building itself is its own, and stays


def _pbox(db, p, memo):
    """A module piece's box in the module's frame: [x0, y0, x1, y1], or None."""
    low = p['id'].lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
    b = memo[low]
    if not b:
        return None
    s = p.get('s') or 1.0
    c, sn = math.cos(p['rz']), math.sin(p['rz'])
    xs, ys = [], []
    for bx in (b[0] * s, b[3] * s):
        for by in (b[1] * s, b[4] * s):
            xs.append(p['x'] + bx * c + by * sn)
            ys.append(p['y'] - bx * sn + by * c)
    return [min(xs), min(ys), max(xs), max(ys)]


def _trim_yard(db, m, memo):
    """The module without the walls, palisades, fences and platforms standing clear of the building itself, and what
    stands on them: in the game they join the neighbours' into a street wall or a harbour stage, and set down alone
    they stood loose about the town, a Nordic log house's seven palisade lengths in front of it and an Anvil house's
    platform stage, bollards and planks on the square (the unwalled practice, 2026-11-01). A wall a town wall's height
    goes even against the house: Solstheim's palisade posts, 1,100 tall, hid the log houses they stood against. A piece
    a door stands on
    stays, and a house's own walls (the Reach's houses are built of HouseWall lengths) and a keep's."""
    if KEEP.search(m['main']):
        return m
    main = next((p for p in m['fpieces'] if p['id'].lower() == m['main'].lower()), None)
    mb = main and _pbox(db, main, memo)
    if not mb:
        return m
    mb = [mb[0] - YARD_NEAR, mb[1] - YARD_NEAR, mb[2] + YARD_NEAR, mb[3] + YARD_NEAR]
    doors = [(p['x'], p['y']) for p in m['fpieces'] if p.get('door')]
    apart = lambda a, b: a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]
    holds = lambda a: any(a[0] - 32 <= x <= a[2] + 32 and a[1] - 32 <= y <= a[3] + 32 for x, y in doors)
    drop, boxes = set(), []
    for k, p in enumerate(m['fpieces']):
        low = p['id'].lower()
        if p is main or p.get('door') or 'door' in low or 'housewall' in low or not (WALLISH.search(low) or 'platform' in low):
            continue
        b = _pbox(db, p, memo)
        tall = WALLISH.search(low) and 'gateway' not in low and _height(db, low, memo) >= FORT_HEIGHT
        if b and (apart(b, mb) or tall) and not holds(b):
            drop.add(k)
            boxes.append(b)
    if not drop:
        return m
    for k, p in enumerate(m['fpieces']):
        if k not in drop and p is not main and not p.get('door') and 'door' not in p['id'].lower():
            b = _pbox(db, p, memo)
            if b and apart(b, mb) and not holds(b) and any(o[0] <= (b[0] + b[2]) / 2 <= o[2] and o[1] <= (b[1] + b[3]) / 2 <= o[3] for o in boxes):
                drop.add(k)
    return dict(m, fpieces=[p for k, p in enumerate(m['fpieces']) if k not in drop])


def _footprint(db, m, memo):
    """The module's footprint in its door's frame: [x0, y0, x1, y1] (+y inward, the door at the origin)."""
    xs, ys = [], []
    for p in m['fpieces']:
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if not b:
            continue
        s = p.get('s') or 1.0
        c, sn = math.cos(p['rz']), math.sin(p['rz'])
        for bx in (b[0] * s, b[3] * s):
            for by in (b[1] * s, b[4] * s):
                # (turned clockwise, as the game turns: groups.place)
                xs.append(p['x'] + bx * c + by * sn)
                ys.append(p['y'] - bx * sn + by * c)
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def catalog(db):
    """[{'key': main piece, 'culture', 'kind', 'w', 'd', 'fp', 'uses', 'm': module}] for every whole building the game
    has outside a door."""
    key = id(db.recs)
    if key in _cat:
        return _cat[key]
    import exteriorsurvey as es
    s = es.ready(db)
    if s is None:
        return []                  # (not learnt yet: nothing kept, so the next ask finds the catalogue whole)
    memo = {}
    out = []
    try:
        import townwalls
        K = townwalls.kits(db)
        runs = {k['straight'].lower() for k in K.values()}
        fortish = {x.lower() for k in K.values() for x in k['models']}
    except Exception as e:
        print('wall kits:', e)
        runs, fortish = set(), set()
    for m in s.get('modules') or ():
        if not m.get('fpieces') or not any(p.get('door') for p in m['fpieces']):
            continue
        # (a building that brings lengths of town wall with it, two or more of a wall kit's straights or a curved wall:
        # set down alone, its walls stood about the town as strays, a guard tower's three straights seven times over in
        # an Imperial town and Hlaalu's curved yard wall snaking between houses, the Tamriel practice 2026-10-31)
        if sum(1 for p in m['fpieces'] if p['id'].lower() in runs or 'wall_curve' in p['id'].lower()) >= 2:
            continue
        cult = townsurvey.town_style(m['main'])
        if not cult:
            continue
        # (no piece of a town wall, gate or rampart as a building: dropped on a plot it was a stray length of wall; the
        # user: "for a walled city, the walls line up, the pieces snap together, and it looks like a real wall". Walls
        # are laid whole, by the game's joins, in a stage of their own)
        if WALLISH.search(m['main']) or sum(1 for p in m['fpieces'] if WALLISH.search(p['id'])) > 0.5 * len(m['fpieces']):
            continue
        m = _trim_yard(db, m, memo)
        fp = _footprint(db, m, memo)
        if not fp:
            continue
        if _floating(db, m, memo):
            continue
        if _roof_door(db, m, memo):
            continue
        # (the top of a tower stack, learnt as a building for the door on its platform: set on the ground it stood
        # sunk to its roof, the user's island town, test3. A stack part whose module holds no base piece)
        if STACK_PART.search(m['main']) and not any(BASE_PART.search(p_['id']) for p_ in m['fpieces']):
            continue
        # (and the bottom of one with nothing on it: a tower's base and middle without its top or roof stood as an open
        # stump, four round an Imperial keep, the Tamriel practice 2026-10-31)
        if re.search(r'tower', m['main'], re.I) and BASE_PART.search(m['main']) and                 not any(re.search(r'top|roof', p_['id'], re.I) for p_ in m['fpieces']):
            continue
        # (a waterfront's wall, a dock or a pier is no house: Hlaalu's wfcurve stood inland as one, the town practice)
        if WATERFRONT.search(m['main']):
            continue
        w, d = fp[2] - fp[0], fp[3] - fp[1]
        if not (150 < w < MAX_ACROSS and 150 < d < MAX_ACROSS):
            continue
        # (a tomb's, a barrow's, a cave's or a mine's door stands in the game's towns too: no plot takes one)
        import towninside
        ex = [e for e in m.get('examples') or () if towninside.town_ok((mapdata.cell_info(db, e) or {}).get('name') or e)]
        if m.get('examples') and not ex:
            continue
        kinds = [townsurvey.kind_of(e) for e in ex]
        # (a tie the first of them by name: over a set, the kind of a building with one manor and one plain interior
        # changed with each run's string hashes, and a walled town of the same seed stood 56 buildings or 68, lab jdet)
        kind = max(sorted(set(kinds)), key=kinds.count) if kinds else 'other'
        # (a ruin's piece: a broken keep stood among new houses)
        if any(RUIN.search(p['id']) for p in m['fpieces']):
            continue
        # (a fort's part: a keep is whole, a tower or a stretch of fort wall stands only against a neighbour, fit)
        keep = bool(KEEP.search(m['main']))
        # (the building is itself a tower or a fort wall's piece; or a guard tower of any set: the legion's stood three
        # together among the houses on an Imperial town's guard plots, now the wall has towers of its own, test4 practice)
        fort = keep or m['main'].lower() in fortish or bool(re.search(r'guardtower', m['main'], re.I))
        # (a tower that brings a piece of its fort's wall with it, an arch or a length: it trailed off into the open)
        if fort and not keep and any(p['id'].lower() != m['main'].lower() and p['id'].lower() in fortish and 'wall' in p['id'].lower()
                                     and 'wallent' not in p['id'].lower() for p in m['fpieces']):
            continue
        if not keep and any('bridge' in p['id'].lower() or WATERFRONT.search(p['id']) for p in m['fpieces']):
            continue                     # (any building with a bridge to its neighbour, a mooring or a lighthouse: a stub of
                                         # a waterfront or a fort; four legion lighthouses and their bridges stood inland
                                         # on an Imperial town's guard plots, test4 practice)
        # (any house that brings a town wall's length, corner, arch or tower with it, a wall's height: set down inside the
        # town, it stood as a stray stretch of wall among the houses, Common's guard house and tavern built against Old
        # Ebonheart's wall, the user's Chillmorrow, test4. A yard's low wall stays: it is the house's own)
        if not keep and any(p['id'].lower() != m['main'].lower() and p['id'].lower() in fortish and 'wallent' not in p['id'].lower()
                            and _height(db, p['id'], memo) >= FORT_HEIGHT for p in m['fpieces']):
            continue
        if keep and not _keep_whole(db, m, fortish, memo):
            continue
        # (a well is no house: Solstheim's, with its trapdoor, stood on ten house plots of a Nordic-led town)
        if NOT_BUILDING.search(m['main']):
            continue
        out.append({'key': m['main'], 'culture': cult, 'kind': kind, 'w': round(w), 'd': round(d), 'fp': [round(v) for v in fp],
                    'uses': m.get('uses', 1), 'm': m, 'fort': fort, 'keep': keep})
    _cat[key] = out
    return out


RUIN = re.compile(r'ruin|broken|collapsed|rubble', re.I)
KEEP = re.compile(r'keep', re.I)
OPENING = re.compile(r'window|door|shutter|awning|sign|banner', re.I)
STACK_PART = re.compile(r'_top|top_|roof|_med_|_light_|_dark_|upper', re.I)
BASE_PART = re.compile(r'base|_bottom|foundation', re.I)
WATERFRONT = re.compile(r'_wf|waterfront|dock|pier|quay|jetty|mooring|_ship|boat|cutter|shipwreck|lighthouse', re.I)
NOT_BUILDING = re.compile(r'well', re.I)
OPEN_REACH = 100               # a window's or door's middle stands at most this far from one of its building's walls
FORT_HEIGHT = 600              # a wall kit's piece this tall is a town wall's, not a yard's (ex_imp_wall_01 921)
KEEP_DROP = 480                # a keep whose pieces reach further than this under its door stood down a hill or a cliff


def _height(db, pid, memo):
    low = pid.lower()
    if low not in memo:
        memo[low] = mapdata.object_bounds(db, db.resolve_id(pid))
    b = memo[low]
    return (b[5] - b[2]) if b else 0.0


ROOF_DOOR = 200                # a building rising less than this over its door is entered from its roof


def _roof_door(db, m, memo):
    """Is the door on the building's roof? Balmora's houses by the Odai are entered from the upper street, the door on
    top and the walls going down to the river: set on level ground they stood sunk to their parapets, empty stone basins
    among the houses (the town practice, u2_hla). They rise 60-90 over the door; every other culture's 265 and more."""
    doors = [p for p in m['fpieces'] if p.get('door')]
    if not doors:
        return False
    dz = min(p['z'] for p in doors)
    top = None
    for p in m['fpieces']:
        if p.get('door'):
            continue
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if b:
            t = p['z'] + b[5] * (p.get('s') or 1.0)
            top = t if top is None else max(top, t)
    return top is not None and top - dz < ROOF_DOOR


def _keep_whole(db, m, fortish, memo):
    """Can this keep stand on its own on level ground, whole? Most of the game's are a part of a bigger fort, their door
    up on a platform or a hillside: their towers reached 2,000 under the door and stood buried, and the lengths of fort
    wall, arches and wall towers they carry stood loose about the town, its towers' bases without their tops as stumps
    (the user's Chillmorrow, test4: "a randomly thrown together sprawl"). Keeps that reach no further than KEEP_DROP
    under the door, carry no length of wall and have a top on every tower."""
    lowest = 0.0
    bases = tops = 0
    for p in m['fpieces']:
        low = p['id'].lower()
        if low not in memo:
            memo[low] = mapdata.object_bounds(db, db.resolve_id(p['id']))
        b = memo[low]
        if b:
            lowest = min(lowest, p['z'] + b[2] * (p.get('s') or 1.0))
        if low != m['main'].lower() and low in fortish and 'wall' in low and 'wallent' not in low:
            return False
        if 'tower' in low and BASE_PART.search(low):
            bases += 1
        if 'tower' in low and re.search(r'top|roof', low):
            tops += 1
    return lowest >= -KEEP_DROP and tops >= bases


def _floating(db, m, memo):
    """Is a window or door of this building touching none of its walls? The survey cut some buildings short, a window
    or door kept and the wall it stood in left out (28 of 290 Imperial, Anvil and Gold Coast ones, lab jfloat): set down
    whole on a plot, they stood as an incomplete building with windows and doors in the air, the user's first town."""
    boxes = []
    for p in m['fpieces']:
        if p['id'] not in memo:
            ri = db.resolve_id(p['id'])
            memo[p['id']] = mapdata.object_bounds(db, ri) if ri is not None else None
        b = memo[p['id']]
        if not b:
            continue
        sc, c, sn = p.get('s') or 1.0, math.cos(p.get('rz') or 0.0), math.sin(p.get('rz') or 0.0)
        xs = [p['x'] + (bx * c + by * sn) * sc for bx in (b[0], b[3]) for by in (b[1], b[4])]
        ys = [p['y'] + (-bx * sn + by * c) * sc for bx in (b[0], b[3]) for by in (b[1], b[4])]
        boxes.append((bool(OPENING.search(p['id'])), (min(xs), min(ys), p['z'] + b[2] * sc, max(xs), max(ys), p['z'] + b[5] * sc)))
    solid = [b for o, b in boxes if not o]
    touch = lambda a, b: all(a[i] - 24 <= b[i + 3] and b[i] - 24 <= a[i + 3] for i in range(3))
    # (and its middle within OPEN_REACH of a wall: one that only grazes a corner hangs beside the building, its frame
    # standing out from no wall; frames stand 50-90 out of their own walls, lab jwin3. The user, test4: "be careful with
    # windows and doorways, don't add them unless they go on a building")
    def near(b):
        c = [(b[i] + b[i + 3]) / 2.0 for i in range(3)]
        return any(sum(max(s_[i] - c[i], 0.0, c[i] - s_[i + 3]) ** 2 for i in range(3)) <= OPEN_REACH ** 2 for s_ in solid)
    return any(o and (not any(touch(b, s_) for s_ in solid) or not near(b)) for o, b in boxes)


def _frame(face):
    """(c, s) of the turn a building's door frame takes for a plot whose door opens the face way: groups.place's own
    turn, so its +y (inward) runs from the door into the plot."""
    yaw = face + math.pi
    return math.cos(yaw), math.sin(yaw), yaw


def _world(x, y, c, s, dx, dy):
    return x + dx * c + dy * s, y - dx * s + dy * c


SPECIAL = ('temple', 'guild', 'guard', 'tavern')
NUDGES = ((0, 0), (-160, 0), (160, 0), (0, 160), (-320, 0), (320, 0), (0, 320), (-160, 160), (160, 160))
KIND_NEAR = {('house', 'other'): 0.0, ('other', 'house'): 0.0, ('manor', 'house'): 0.5, ('shop', 'house'): 0.6, ('tavern', 'shop'): 0.6}


def fit(db, plan, seed=1):
    """A building for each plot of the plan: the town's culture's own (or the nearest culture's, when it has few),
    the plot's kind first, about the plot's size, not the same one over and over. Each plot gets 'b': {key, culture,
    kind, w, d}, its rect becomes the building's own outline and its door the building's door. The plan, changed."""
    C = catalog(db)
    cult = plan['culture']
    pool = [c for c in C if c['culture'] == cult]
    for near in NEAR_CULTURES.get(cult, ()):
        if len(pool) >= 12:
            break
        pool += [c for c in C if c['culture'] == near]
    if not pool:
        return plan
    rng = random.Random('%d|%s|b' % (int(seed), cult))
    # (one leading family, and the families the game's own towns mix with it: "Imperial" alone mixed Gold Coast towers,
    # Reach timber houses and fort walls in one town, lab 2026-10-30. The lead is drawn by how many of the culture's
    # buildings are of it)
    M = family_mix(db)
    # (the lead: a family that leads the culture's own towns in the game, as often as it does; else by its buildings)
    # (only families the culture's own buildings are of: Common's game towns include Old Ebonheart and Dagon Fel, and
    # ex_vivec led a Common town of Dunmer shacks, a Telvanni stem house and Imperial towers, not one ex_common
    # building, the user's island town, test3)
    own = {family(c_['key']) for c_ in pool if c_['culture'] == cult}
    fams = {f: o['cultures'].get(cult, 0) for f, o in M.items() if o['cultures'].get(cult) and f in own}
    if not fams:
        for c_ in pool:
            if c_['culture'] == cult:
                f = family(c_['key'])
                fams[f] = fams.get(f, 0) + 1
    lead = plan.get('family') if plan.get('family') in fams else None
    if lead is None and fams:
        pick = rng.random() * sum(fams.values())
        for f, n in sorted(fams.items()):
            pick -= n
            if pick <= 0:
                lead = f
                break
    share = {}
    if lead:
        # (the families its game towns mix, by their share of the buildings, from the whole catalogue: an Imperial town
        # of ex_imp alone was all fort sections; let in as equals, a Redoran town came out mostly Hlaalu)
        share = {f: v for f, v in (M.get(lead, {}).get('mix') or {lead: 1.0}).items() if v >= 0.03}
        share.setdefault(lead, 0.5)
        # (from the look's own buildings: taken from the whole catalogue, the families the game mixes with a lead brought
        # in other looks' buildings; a kind the look lacks is lent from its near culture below, as the game mixes them)
        narrow = [c_ for c_ in pool if family(c_['key']) in share]
        if len(narrow) >= 8:
            pool = narrow
    plan['family'] = lead
    # (a kind of building the look has too few of, its near culture's of that kind: the classic Imperial look's game towns
    # are forts, with hardly a shop, tavern or plain house, and the game stands Common ones among Imperial in Pelagiad and
    # Old Ebonheart; the user, 2026-10-31: "appropriate to mix and match between these styles when certain types of pieces
    # are missing")
    have = Counter(c['kind'] for c in pool)
    lend = {}
    for near in NEAR_CULTURES.get(cult, ())[:1]:
        for c in C:
            if c['culture'] == near and have[c['kind']] < 3:
                lend.setdefault(c['kind'], []).append(c)
    used = {}
    import townplan
    placed = [[tuple(p_) for p_ in r] for r in plan.get('obstacles') or ()]
    roads = {tuple(r) for r in plan.get('roads') or ()}
    keep = []
    keeps = []
    ways = []                            # (the ground straight out of each fitted building's door, kept clear)
    # (the special buildings first, then the biggest plots: the ones hardest to fit)
    for q in sorted(plan['plots'], key=lambda q: (q['kind'] == 'house', -q['w'] * q['d'])):
        pw, pd = max(150.0, q['w']), max(150.0, q['d'])

        def cost(c):
            k = 0.0 if c['kind'] == q['kind'] else KIND_NEAR.get((q['kind'], c['kind']), 1.2)
            if q['kind'] in ('house', 'other') and c['kind'] in SPECIAL:
                k = 4.0                  # (a house plot in a chapel or a guard tower: its interior is a chapel's, lab jtint1; 2.5
                                         # still left 4 chapels on 46 Imperial house plots, lab jchap)
            if c['kind'] == 'guard' and q['kind'] != 'guard':
                k = 8.0                  # (a fort's tower on a shop, tavern or house plot: one Imperial town stood seven)
            sw, sd = c['w'] / pw, c['d'] / pd
            size = abs(math.log(sw)) + abs(math.log(sd)) + (2.0 * (max(sw, sd) - 1.15) if max(sw, sd) > 1.15 else 0.0)
            fam = 0.6 * -math.log(max(0.02, share.get(family(c['key']), 0.02))) if share else 0.0
            # (a building whose game interiors are all copied already in this town: the next would repeat one, the same
            # chapel three times in a town, lab jchap)
            u = used.get(c['key'], 0)
            again = 2.0 if u and u >= len(c.get('examples') or ()) else 0.0
            return k + size + fam + 0.35 * u + again - 0.05 * math.log(1 + c['uses']) + rng.random() * 0.25
        # (the best that stands clear of the buildings already fitted: a game building bigger than its plot ran into its
        # neighbour, 2 to 22 pairs a town, lab jtbuild1)
        c, sn, _yaw = _frame(q['face'])
        b = None
        # (the first 80: of the first 30, a plot in five of a walled Hlaalu town found none clear of its neighbours)
        for cand in sorted(pool + lend.get(q['kind'], []), key=cost)[:80]:
            if cand.get('fort') and not cand.get('keep'):
                continue                         # (a fort's loose part: _lone_forts)
            if cand.get('keep') and keeps:
                continue                         # (one keep a town, whole; seven stood in for guard towers)
            fp = cand['fp']
            cfx, cfy = (fp[0] + fp[2]) / 2.0, (fp[1] + fp[3]) / 2.0
            ox, oy = _world(0, 0, c, sn, cfx, cfy)
            for nx_, ny_ in NUDGES:
                # (where it runs into a neighbour on its plot, a little aside or back from the street: the game's buildings
                # are bigger than the plots cut for them, and a walled Hlaalu town built 16 of its 25)
                mx, my = _world(0, 0, c, sn, nx_, ny_)
                dx, dy = q['x'] - ox + mx, q['y'] - oy + my      # (the door, so the building's middle is the plot's)
                rect = [_world(dx, dy, c, sn, fx, fy) for fx, fy in ((fp[0] + 8, fp[1] + 8), (fp[2] - 8, fp[1] + 8), (fp[2] - 8, fp[3] - 8), (fp[0] + 8, fp[3] - 8))]
                if any(townplan._overlap(rect, o) for o in placed):
                    continue
                # (its door with a way out, and no other building's door shut by it)
                way = _doorway(dx, dy, c, sn)
                if any(townplan._overlap(rect, w_) for w_ in ways) or any(townplan._overlap(way, o) for o in placed):
                    continue
                if (nx_ or ny_) and any((int(x_ // townplan.PATCH), int(y_ // townplan.PATCH)) in roads for x_, y_ in rect[2:4] + [
                        ((rect[0][0] + rect[2][0]) / 2, (rect[0][1] + rect[2][1]) / 2)]):
                    continue                             # (nudged onto a street: its far corners and middle stay off them)
                b = cand
                break
            if b is not None:
                break
        if b is None:
            continue
        placed.append(rect)
        ways.append(way)
        keep.append(q)
        used[b['key']] = used.get(b['key'], 0) + 1
        if b.get('keep'):
            keeps.append(q)
        q['b'] = {'key': b['key'], 'culture': b['culture'], 'kind': b['kind'], 'w': b['w'], 'd': b['d']}
        q['door'] = [round(dx, 1), round(dy, 1)]
        if mx or my:
            q['x'], q['y'] = round(q['x'] + mx, 1), round(q['y'] + my, 1)      # (where it was nudged)
        q['rect'] = [[round(v, 1) for v in _world(dx, dy, c, sn, fx, fy)] for fx, fy in ((fp[0], fp[1]), (fp[2], fp[1]), (fp[2], fp[3]), (fp[0], fp[3]))]
        q['way'] = [[round(v, 1) for v in p_] for p_ in way]
    plan['plots'] = [q for q in plan['plots'] if q in keep]
    _close_rows(plan, rng)
    _lone_forts(plan, {c['key']: c for c in C})
    _shut_doors(plan)
    return plan


WALL_BACK = 320                # a walled town's buildings stand back to its wall this close (its own depth ~250)


def planned(db, outline, culture, seed=1, walls=''):
    """The town planned and its buildings fitted (townplan.plan, fit). Walled: planned twice, the second time inside the
    wall the first plan's buildings call for, so its streets and buildings fill the wall corner to corner as the game's
    walled towns do: planned once, the town's streets made a long blob and the wall's box round it left its corners
    bare, two fifths of the ground inside empty against a fifth or less in Firewatch and Ebonheart (the Tamriel
    practice, 2026-11-01)."""
    import townplan
    # (the bar's planning share: a walled town is planned twice, its two plans the most of it)
    P = PLAN_END
    pl = townplan.plan(db, outline, culture, seed, walled=bool(walls))
    _say('Choosing the buildings', P * (0.3 if walls else 0.8))
    plan = fit(db, pl, seed)
    if not walls:
        return plan
    import townwalls
    _say('Planning inside the wall', P * 0.4)
    try:
        W = townwalls.lay(db, plan, None if walls == 'auto' else walls)
    except Exception as e:
        print('town wall:', e)
        return plan
    poly = W.get('outline') or []
    if len(poly) < 4:
        return plan
    inner = townplan.inset(poly, WALL_BACK)
    pl = townplan.plan(db, inner, culture, seed, walled=True, ring=True)
    _say('Choosing the buildings', P * 0.85)
    again = fit(db, pl, seed)
    built = lambda p_: sum(1 for q in p_['plots'] if q.get('b'))
    if built(again) < 0.75 * built(plan):
        return plan
    again['wall_outline'] = [list(p_) for p_ in poly]
    return again


GATE_CLEAR = 1200              # the ground inside a gate kept free of buildings, this deep
DOOR_CLEAR = 320               # the ground straight out of a door kept free of buildings, this deep
DOOR_WAY = 224                 # and this wide


def _doorway(dx, dy, c, sn):
    """The way out of a door at (dx, dy) in its plot's frame (c, sn): the strip of ground in front of it, as world points.
    (One in seven doors of the walled towns opened straight onto another building's wall within 256, lab jdoor0. The
    user, test5 practice: "doorways must remain accessible, and the entrances tend to line up along streets, common
    access coves".)"""
    h = DOOR_WAY / 2.0
    return [_world(dx, dy, c, sn, fx, fy) for fx, fy in ((-h, -16 - DOOR_CLEAR), (h, -16 - DOOR_CLEAR), (h, -16), (-h, -16))]


def _shut_doors(plan):
    """Buildings whose door another stands in front of, left out (rows drawn together can close one up)."""
    import townplan
    built = [q for q in plan['plots'] if q.get('b') and q.get('rect')]
    shut = [q for q in built if q.get('way') and any(o is not q and townplan._overlap(_shrink_rect(o['rect'], 8), q['way']) for o in built)]
    if shut:
        plan['plots'] = [q for q in plan['plots'] if q not in shut]


def _lone_forts(plan, C):
    """A fort's tower or stretch of fort wall, left out: in the game they stand in a fort's own run, and set among houses
    they read as broken wall or open stumps, in groups too (round guard towers are open at the top). The user,
    2026-10-31: "keep a whole keep and clean up the loose bits that don't fit and don't have neighbours"."""
    lone = [q for q in plan['plots'] if q.get('b') and (C.get(q['b']['key']) or {}).get('fort')
            and not (C.get(q['b']['key']) or {}).get('keep')]
    if lone:
        plan['plots'] = [q for q in plan['plots'] if q not in lone]


JOIN_GAP = 1200                # (a gap this small or less along a row is closed, as often as the culture joins its buildings)


def _close_rows(plan, rng):
    """Buildings drawn together as often as the culture's towns join theirs (townplan figures 'joined': Hlaalu 0.74,
    Common 0.68, Redoran 0.57, Telvanni 0.50): along a street side towards the neighbour before it, in an open town
    towards the nearest. Each is smaller than the plot cut for it, and the towns came out a building, a gap, a building
    where the game's stand wall to wall, lab jdens. Slid in small steps until it meets its neighbour, never into
    another building."""
    import townplan
    j = ((plan.get('figures') or {}).get('joined')) or 0.0
    if j <= 0:
        return
    built = [q for q in plan['plots'] if q.get('b') and q.get('rect')]

    def clear(rect, me, way=None):
        sh = _shrink_rect(rect, 8)
        return not any(o is not me and (townplan._overlap(sh, _shrink_rect(o['rect'], 8))
                                         or (o.get('way') and townplan._overlap(sh, o['way']))
                                         or (way and townplan._overlap(way, _shrink_rect(o['rect'], 8)))) for o in built)

    def slide(b, vx, vy, toward):
        # (steps of 24 up to JOIN_GAP; kept where it last stood clear, if it then touches the one it moved toward)
        last = None
        for k in range(1, int(JOIN_GAP // 24) + 1):
            d = 24.0 * k
            moved = [[p[0] + vx * d, p[1] + vy * d] for p in b['rect']]
            mway = [[p[0] + vx * d, p[1] + vy * d] for p in b['way']] if b.get('way') else None
            if not clear(moved, b, mway):
                break
            last = d
        if not last:
            return
        moved = [[p[0] + vx * (last + 24), p[1] + vy * (last + 24)] for p in b['rect']]
        if not townplan._overlap(_shrink_rect(moved, 8), _shrink_rect(toward['rect'], 8)):
            return                               # (stopped by something else first, or never reached it)
        mx, my = vx * last, vy * last
        b['rect'] = [[round(p[0] + mx, 1), round(p[1] + my, 1)] for p in b['rect']]
        if b.get('way'):
            b['way'] = [[round(p[0] + mx, 1), round(p[1] + my, 1)] for p in b['way']]
        b['x'], b['y'] = b['x'] + mx, b['y'] + my
        if b.get('door'):
            b['door'] = [round(b['door'][0] + mx, 1), round(b['door'][1] + my, 1)]
    def toward_nearest(bs):
        for b in sorted(bs, key=lambda q: rng.random()):
            if rng.random() > j:
                continue
            a = min((o for o in built if o is not b), key=lambda o: math.hypot(o['x'] - b['x'], o['y'] - b['y']), default=None)
            if a is None:
                continue
            vx, vy = a['x'] - b['x'], a['y'] - b['y']
            L_ = math.hypot(vx, vy) or 1.0
            if (math.sin(b['face']) * vx + math.cos(b['face']) * vy) / L_ > 0.5:
                continue                             # (door first: it would stand with its door against the other's wall)
            slide(b, vx / L_, vy / L_, a)
    if plan.get('layout') == 'open':
        toward_nearest(built)
        return
    rows = {}
    for q in built:
        if q.get('street') and q.get('si') is not None:
            rows.setdefault(q['si'], []).append(q)
    for row in rows.values():
        row.sort(key=lambda q: q.get('at', 0.0))
        # (neighbours along the street on the same side: facing within 40 degrees of each other; a bending street turns
        # every door a little, and grouping by the exact facing made a row of one)
        for i, a in enumerate(row):
            b = next((b for b in row[i + 1:] if abs(((b['face'] - a['face'] + math.pi) % (2 * math.pi)) - math.pi) < math.radians(40)), None)
            if b is None or rng.random() > j:
                continue
            vx, vy = a['x'] - b['x'], a['y'] - b['y']
            L_ = math.hypot(vx, vy) or 1.0
            slide(b, vx / L_, vy / L_, a)
    # (the buildings off the street, behind the rows: towards their nearest too, as the game's yards close up; left where
    # their plots were cut, a Redoran town joined none of its buildings, the Tamriel practice 2026-10-31)
    toward_nearest([q for q in built if not q.get('street')])


def _shrink_rect(r, d):
    cx, cy = sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r)
    out = []
    for x, y in r:
        dx, dy = x - cx, y - cy
        h = math.hypot(dx, dy) or 1.0
        out.append((x - dx / h * d, y - dy / h * d))
    return out


# How far Make it has got, for the Town panel's bar (GET /api/town/progress, asked while it works; PIN2, 2026-11-01: "It
# takes a bit for the town to appear. you think you can do a progress bar?"). The shares are each stage's time in a
# test server (a walled Hlaalu town of 28 buildings with people, 52 s): planning 15 s, the town itself 8 s, its
# interiors and their people 29 s. The town's own shares (planning to PLAN_END, then the stages) run to STAGE_END of the
# bar when interiors follow, to the end without.
PROGRESS = {'on': False, 'what': '', 'frac': 0.0, 'ins': False}
PLAN_END = 0.65
STAGE_END = 0.45


def _say(what, frac):
    if PROGRESS['on']:
        f = frac * STAGE_END if PROGRESS['ins'] else frac
        PROGRESS.update(what=what, frac=round(max(PROGRESS['frac'], min(1.0, f)), 3))


def progress():
    return {k: v for k, v in PROGRESS.items() if k != 'ins'}


def make(db, outline, culture, seed=1, walls='', dress=False, interiors=False, people=False, name=''):
    """_make, with how far it has got said as it goes (PROGRESS)."""
    PROGRESS.update(on=True, what='Planning streets and plots', frac=0.0, ins=bool(interiors))
    try:
        return _make(db, outline, culture, seed, walls, dress, interiors, people, name)
    finally:
        PROGRESS.update(on=False, what='', frac=0.0, ins=False)


def _make(db, outline, culture, seed=1, walls='', dress=False, interiors=False, people=False, name=''):
    """The town built: its plan (townplan.plan, the same seed gives the same town) and a building of the culture's on
    every plot, each set down on the ground in front of its door as the game's stands on its own. One Undo step.
    walls: '' none, 'auto' the culture's own, or a wall family (townwalls.py): laid round it, piece joined to piece.
    dress: its yards, streets and square dressed as the culture's game towns are (towndress.py).
    interiors: behind each door one of the game's interiors for that building, named in the town's name; people: its
    household in it (towninside.py). name: the town's ('' makes one).
    {'buildings', 'pieces', 'cells', 'fitted', 'road', 'wall', 'dressed', 'interiors', 'people', 'name'}."""
    import editing
    import townplan
    from project import set_ref_pos, zs
    editing._require_project(db)
    plan = planned(db, outline, culture, seed, walls)
    C = {c['key']: c for c in catalog(db)}
    mine = db.project.plugin.lower()
    made, pieces, cells = 0, 0, set()
    rmemo = {}
    doors, new_refs = [], set()
    # the wall laid out and its ground evened first, so the buildings stand on the ground as it ends up: evened after
    # they were set down, the land rose round them and buried them to their roofs (the user's Chillmorrow, test3)
    W = None
    if walls:
        import townwalls
        _say('Laying the wall', 0.66)
        W = townwalls.lay(db, plan, None if walls == 'auto' else walls)
        try:
            townwalls.level_ground(db, W, new_refs)
        except Exception as e:
            print('wall ground:', e)
    _say('Levelling the ground', 0.7)
    try:
        _terrace(db, plan, W, new_refs)
    except Exception as e:
        print('terraces:', e)
    _say('Clearing the ground', 0.74)
    try:
        cleared = _clear_ground(db, plan, W)
    except Exception as e:
        print('clearing:', e)
        cleared = 0
    wall_boxes = []
    if W is not None:
        memo_w = {}
        for p_ in W.get('pieces') or ():
            cs_, _b = townwalls._box(db, p_['id'], p_['pose'], memo_w)
            if cs_:
                wall_boxes.append(_shrink_rect(cs_, 16))
        # (and the way in behind each gate kept open, GATE_CLEAR deep into the town)
        poly_ = W.get('outline') or []
        if poly_:
            mx_, my_ = sum(p_[0] for p_ in poly_) / len(poly_), sum(p_[1] for p_ in poly_) / len(poly_)
            for p_ in W.get('pieces') or ():
                if p_.get('kind') not in ('gate', 'end'):
                    continue
                g_ = p_['pose']
                dx_, dy_ = mx_ - g_.x, my_ - g_.y
                h_ = math.hypot(dx_, dy_) or 1.0
                wall_boxes.append(townplan._rect(g_.x + dx_ / h_ * GATE_CLEAR / 2, g_.y + dy_ / h_ * GATE_CLEAR / 2,
                                                 math.atan2(dx_ / h_, dy_ / h_), 640, GATE_CLEAR))
    for k_, q in enumerate(plan['plots']):
        _say('Setting the buildings', 0.76 + 0.1 * k_ / float(len(plan['plots']) or 1))
        b = q.get('b') and C.get(q['b']['key'])
        if not b:
            continue
        if W and W.get('outline') and q.get('rect') and not all(townwalls._inside(W['outline'], p_) for p_ in q['rect'] + (q.get('way') or [])):
            q['b'] = None                # (outside the wall, where the land made it turn in: not built, the town is walled;
            continue                     # no yard, interior or household for it either)
        if wall_boxes and q.get('rect') and any(townplan._overlap(_shrink_rect(q['rect'], 16), w_) or (q.get('way') and townplan._overlap(q['way'], w_))
                                                for w_ in wall_boxes):
            q['b'] = None                # (into the wall, a tower or the keep, or its door against them: houses back onto
            continue                     # the wall now, 2 clashes in 5 towns, lab jwclash)
        m = b['m']
        c, sn, yaw = _frame(q['face'])
        dx, dy = q['door']
        # (the ground in front of the door: the building stands on it as the game's stood on its own, fground)
        fx, fy = _world(dx, dy, c, sn, 0.0, -120.0)
        gz = mapdata.terrain_z(db, fx, fy)
        if gz is None:
            continue
        z0 = gz - (m.get('fground') if m.get('fground') is not None else -40.0)
        front = min((p_ for p_ in m['fpieces'] if p_.get('door')), key=lambda p_: p_['x'] ** 2 + p_['y'] ** 2 + (p_['z'] * 3) ** 2, default=None)
        for p_ in m['fpieces']:
            low = p_['id'].lower()
            if low not in rmemo:
                rmemo[low] = db.resolve_id(p_['id'])
            ri = rmemo[low]
            if ri is None:
                continue
            wx, wy = _world(dx, dy, c, sn, p_['x'], p_['y'])
            key = '#%d,%d' % (math.floor(wx / 8192.0), math.floor(wy / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            rk = db.project.new_ref_key()
            pos = (wx, wy, z0 + p_['z'], p_.get('rx', 0.0), p_.get('ry', 0.0), (p_['rz'] + yaw) % (2 * math.pi))
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], pos, p_.get('s') or 1.0))
            pieces += 1
            cells.add(key)
            new_refs.add(rk)
            if p_.get('door'):
                doors.append((key, rk))
                q['door_z'] = pos[2]
                if p_ is front:
                    q['door_ref'] = (key, rk)        # (the way in, at the module's origin: its interior's door links here)
        made += 1
    wall = 0
    if W is not None:
        _say('Setting the wall on the ground', 0.87)
        db.sync_project()
        W = townwalls.grounded(db, W)
        # (no wall-walk arches: the game stands ex_imp_wallent_02 along its walks, but set there without a building they
        # read as doorways to nowhere, the user's Chillmorrow, test4: "don't add them unless they go on a building")
        for p_ in W['pieces']:
            ri = db.resolve_id(p_['id'])
            if ri is None:
                continue
            q_ = p_['pose']
            key = '#%d,%d' % (math.floor(q_.x / 8192.0), math.floor(q_.y / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            rk = db.project.new_ref_key()
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]),
                           set_ref_pos([('NAME', zs(db.recs[ri][1]))], (q_.x, q_.y, q_.z, 0.0, 0.0, q_.rz % (2 * math.pi)), 1.0))
            wall += 1
            pieces += 1
            cells.add(key)
            new_refs.add(rk)
        # (the streets carried out through the gates, to be paved with the rest)
        have = {tuple(r) for r in plan.get('roads') or ()}
        plan['roads'] = sorted([list(r) for r in have | townwalls.road_patches(W.get('roads') or [])])
    dressed = 0
    if dress and made:
        _say('Dressing yards and streets', 0.89)
        import towndress
        blocked = [p_['corners'] for p_ in (W or {}).get('pieces') or () if p_.get('corners')]
        for t in towndress.dress(db, plan, seed, blocked):
            ri = db.resolve_id(t['id'])
            if ri is None:
                continue
            key = '#%d,%d' % (math.floor(t['p'][0] / 8192.0), math.floor(t['p'][1] / 8192.0))
            try:
                cell, _refs = editing._cell(db, key)
            except editing.EditError:
                continue
            rk = db.project.new_ref_key()
            editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], tuple(t['p']), t.get('s') or 1.0))
            dressed += 1
            pieces += 1
            cells.add(key)
            new_refs.add(rk)
    fitted = painted = 0
    inside = {}
    import towninside
    name = (name or '').strip() or towninside.town_name(db, culture, seed)
    if pieces:
        _say('Fitting the ground to the buildings', 0.92)
        db.sync_project()
        fitted = _fit_ground(db, doors, new_refs)
        _say('Paving the roads', 0.96)
        painted = _paint_roads(db, plan)
        _say('Saving', 0.98)
        editing.commit(db, 'Built a %s town: %d buildings (%d pieces) in %d cells%s%s%s' % (
            culture, made, pieces, len(cells), ((', a wall of %d pieces' % wall) if wall else '') + ((', %d things set out' % dressed) if dressed else ''),
            (', the ground fitted to %d' % fitted) if fitted else '', (', %d road patches' % painted) if painted else ''))
        if interiors and made:
            # (each interior copied and linked, its people placed: steps of their own, folded with the town into one)
            stack = getattr(db.project, 'undo_stack', [])
            n0 = len(stack)
            what = 'Making interiors and their people' if people else 'Making interiors'
            inside = towninside.furnish(db, plan, name, culture, seed, people, catalog(db),
                                        lambda f: PROGRESS.update(what=what, frac=round(STAGE_END + (1 - STAGE_END) * f, 3)) if PROGRESS['on'] else None)
            if len(stack) > n0:
                editing.fold(db, len(stack) - n0 + 1, 'Built %s, a %s town: %d buildings, %d interiors%s%s' % (
                    name, culture, made, inside['interiors'], (', %d people' % inside['people']) if inside['people'] else '',
                    (', a wall of %d pieces' % wall) if wall else ''))
    return {'buildings': made, 'pieces': pieces, 'cells': sorted(cells), 'fitted': fitted, 'road': painted, 'wall': wall,
            'dressed': dressed, 'interiors': inside.get('interiors', 0), 'people': inside.get('people', 0), 'name': name}


CLEARABLE = re.compile(r'tree|flora|plant|bush|shrub|grass|fern|log|stump|root|kelp|weed|reed|rock|boulder|stone_|mushroom|'
                       r'kollop|comberry|wickwheat|saltrice|heather|scathecraw|timsa|bittergreen|marshmerrow|coda|hackle', re.I)
NOT_CLEARABLE = re.compile(r'wall|house|door|tower|bridge|stair|cave|ruin|_x_|_in_|platform|planter', re.I)
CLEAR_PAD = 160                # (round each plot, and this far either side of the wall's line, the ground is cleared)


def _clear_ground(db, plan, W):
    """The plants, trees and loose rocks standing on the town's plots, its streets and the wall's line taken away, as
    the game's towns stand on cleared ground: on the generated forests of Tamriel.esm a town went up with trees
    through its houses, its streets and its wall (the town practice of 2026-10-31). Things of the mod's own go;
    another plugin's are marked deleted in the mod, so one Undo brings them all back. The count."""
    import editing
    import townplan
    rects = [[tuple(p_) for p_ in q['rect']] for q in plan['plots'] if q.get('b') and q.get('rect')]
    roads = {tuple(r) for r in plan.get('roads') or ()}
    wall = (W or {}).get('outline') or []
    segs = [(wall[i], wall[(i + 1) % len(wall)]) for i in range(len(wall))] if wall else []
    pts = [p_ for r in rects for p_ in r] + [((x + 0.5) * townplan.PATCH, (y + 0.5) * townplan.PATCH) for x, y in roads] + list(wall)
    if not pts:
        return 0

    def seg_d(px, py, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        return math.hypot(px - (a[0] + dx * t), py - (a[1] + dy * t))

    def on_town(x, y, rad=8.0):
        # (rad: half the thing's own size, so a big boulder whose middle is clear but whose side reaches a house goes too)
        if (int(x // townplan.PATCH), int(y // townplan.PATCH)) in roads:
            return True
        for r in rects:
            if townplan._overlap(_shrink_rect(r, -CLEAR_PAD), [(x - rad, y - rad), (x + rad, y - rad), (x + rad, y + rad), (x - rad, y + rad)]):
                return True
        return any(seg_d(x, y, a, b) <= CLEAR_PAD + 120 + rad for a, b in segs)

    def rad_of(r):
        b = r.get('b')
        if not b:
            return 8.0
        return max(8.0, 0.5 * max(b[3] - b[0], b[4] - b[1]) * (r.get('s') or 1.0))
    mine = db.project.plugin.lower()
    n = 0
    xs = [p_[0] for p_ in pts]
    ys = [p_[1] for p_ in pts]
    for gx in range(int(math.floor(min(xs) / 8192.0)), int(math.floor(max(xs) / 8192.0)) + 1):
        for gy in range(int(math.floor(min(ys) / 8192.0)), int(math.floor(max(ys) / 8192.0)) + 1):
            key = '#%d,%d' % (gx, gy)
            m = mapdata.cellmap(db, key)
            # (by name alone: Tamriel.esm's trees and boulders are big enough to count as architecture)
            hits = [r for r in m.get('refs') or () if r.get('type') in ('STAT', 'CONT') and CLEARABLE.search(r['id'])
                    and not NOT_CLEARABLE.search(r['id']) and on_town(r['p'][0], r['p'][1], rad_of(r))]
            if not hits:
                continue
            c, all_refs = editing._cell(db, key)
            for r in hits:
                ref = all_refs.get(r['k'])
                if not ref:
                    continue
                if ref['origin'] == mine:
                    c['refs'].pop(r['k'], None)
                else:
                    editing._store(c, r['k'], ref['origin'], ref['idx'], ref['subs'], deleted=True)
                n += 1
    if n:
        db.sync_project()
    return n


TERRACE_BLEND = 320            # (a terrace fades back into the land round it over this far)


def _terrace(db, plan, W, skip=()):
    """Each plot's ground evened towards the height in front of its door, by at most townplan.TERRACE_TOL, fading back into
    the land round it, before its building goes down: the game's builders terraced their hillside towns, and a plot
    refused for uneven ground left a hill town of a few buildings far apart (the user, 2026-10-31: towns "dense or wide
    according to their culture"; the land may be reshaped within tolerance). What else stands there follows the ground."""
    import landscape
    import townplan
    tol = townplan.TERRACE_TOL
    areas = []
    for q in plan['plots']:
        if not q.get('b') or not q.get('rect') or not q.get('door'):
            continue
        if W and W.get('outline') and not all(townwalls_inside(W, p_) for p_ in q['rect']):
            continue
        c, sn, _yaw = _frame(q['face'])
        fx, fy = _world(q['door'][0], q['door'][1], c, sn, 0.0, -120.0)
        gz = mapdata.terrain_z(db, fx, fy)
        if gz is None or gz < 0:
            continue
        areas.append(([tuple(p_) for p_ in q['rect']], gz))
    if not areas:
        return 0
    G, N = landscape.CELL, landscape.N
    step = G / (N - 1.0)
    xs = [x for r, _z in areas for x, _y in r]
    ys = [y for r, _z in areas for _x, y in r]

    def inside(px, py, r):
        sgn = None
        for i in range(len(r)):
            x1, y1 = r[i]
            x2, y2 = r[(i + 1) % len(r)]
            cr = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
            if abs(cr) < 1e-9:
                continue
            if sgn is None:
                sgn = cr > 0
            elif (cr > 0) != sgn:
                return False
        return True

    def dist(px, py, r):
        if inside(px, py, r):
            return 0.0
        best = 1e18
        for i in range(len(r)):
            ax, ay = r[i]
            bx, by = r[(i + 1) % len(r)]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            best = min(best, math.hypot(px - (ax + dx * t), py - (ay + dy * t)))
        return best
    new_h, before = {}, {}
    for gx in range(int(math.floor((min(xs) - TERRACE_BLEND) / G)), int(math.floor((max(xs) + TERRACE_BLEND) / G)) + 1):
        for gy in range(int(math.floor((min(ys) - TERRACE_BLEND) / G)), int(math.floor((max(ys) + TERRACE_BLEND) / G)) + 1):
            L = mapdata.land(db, gx, gy)
            if not L or not L.get('h'):
                continue
            near = [(r, z) for r, z in areas if min(x for x, _y in r) - TERRACE_BLEND <= gx * G + G and max(x for x, _y in r) + TERRACE_BLEND >= gx * G
                    and min(y for _x, y in r) - TERRACE_BLEND <= gy * G + G and max(y for _x, y in r) + TERRACE_BLEND >= gy * G]
            if not near:
                continue
            h = list(L['h'])
            changed = False
            for j in range(N):
                for i in range(N):
                    x, y = gx * G + i * step, gy * G + j * step
                    best = None
                    for r, z in near:
                        d = dist(x, y, r)
                        if d >= TERRACE_BLEND:
                            continue
                        w = 1.0 if d <= 0 else 0.5 + 0.5 * math.cos(math.pi * d / TERRACE_BLEND)
                        if best is None or w > best[0]:
                            best = (w, z)
                    if not best:
                        continue
                    n = j * N + i
                    z0 = h[n]
                    want = max(z0 - tol, min(z0 + tol, best[1]))
                    nz = z0 + best[0] * (want - z0)
                    if abs(nz - z0) >= 1:
                        h[n] = nz
                        changed = True
            if changed:
                new_h[(gx, gy)] = h
                before[(gx, gy)] = L['h']
    for (gx, gy), h in new_h.items():
        after = landscape.write(db, gx, gy, h, None, None, around=landscape.around_of(db, gx, gy, new_h))
        landscape._follow_ground(db, gx, gy, before[(gx, gy)], after, skip)
    if new_h:
        db.sync_project()
    return len(new_h)


def townwalls_inside(W, p):
    import townwalls
    return townwalls._inside(W['outline'], p)


def _fit_ground(db, doors, skip):
    """The ground fitted to each new building the way the game's meet theirs (groundfit: raised where its foot would
    show a gap, a landing a step under its door; the game never levels the ground under a building), one after another
    so each sees the ground the last left; what else stands on the ground (trees, rocks) follows it. No Undo step."""
    import frombuilding
    import groundfit
    import landscape
    n = 0
    for key, rk in doors:
        try:
            b = frombuilding.building_at(db, key, rk)
            pl = groundfit.plan(db, b)
        except Exception:
            continue
        if not pl:
            continue
        new_h = {(c['gx'], c['gy']): c['h'] for c in pl['cells']}
        for c in pl['cells']:
            gx, gy = c['gx'], c['gy']
            before = mapdata.land(db, gx, gy).get('h')
            after = landscape.write(db, gx, gy, c['h'], None, None, around=landscape.around_of(db, gx, gy, new_h))
            if before:
                landscape._follow_ground(db, gx, gy, before, after, skip)
        db.sync_project()
        n += 1
    return n


_road_tex = {}


def _town_roads(db):
    """[(x, y, culture, {LTEX id: road patches})]: each game town's middle and what its streets are paved with."""
    k = id(db.recs)
    if k not in _road_tex:
        import landscape
        out = []
        for t in townsurvey.survey(db)['towns']:
            if not t['roads'] or not t['buildings']:
                continue
            want = {tuple(int(v) for v in r.split(',')) for r in t['roads']}
            c = {}
            for gx, gy in t['cells']:
                L = landscape.read(db, gx, gy)
                if not L.get('exists') or not L.get('t'):
                    continue
                for n_, tid in enumerate(L['t']):
                    if tid and (gx * 16 + n_ % 16, gy * 16 + n_ // 16) in want:
                        c[tid] = c.get(tid, 0) + 1
            if c:
                bs = t['buildings']
                out.append((sum(b['x'] for b in bs) / len(bs), sum(b['y'] for b in bs) / len(bs), t['culture'], c))
        _road_tex[k] = out
    return _road_tex[k]


def road_texture(db, culture, near=None):
    """The ground texture the culture's own towns pave their streets with (LTEX id): the one its towns nearest the
    new town use (by their road patches, nearer counting more), so a town by Pelagiad gets the Heartland's road, not
    the Gold Coast's dirt the culture's commonest across all its towns."""
    ts = [t for t in _town_roads(db) if t[2] == culture] or         [t for t in _town_roads(db) if t[2] in townsurvey.KIN.get(culture, ())]
    if not ts:
        return None
    if near is not None:
        ts.sort(key=lambda t: math.hypot(t[0] - near[0], t[1] - near[1]))
        ts = ts[:3]
    score = {}
    for i, (_x, _y, _c, c) in enumerate(ts):
        tot = float(sum(c.values()))
        for tid, n in c.items():
            score[tid] = score.get(tid, 0.0) + n / tot / (1 + i)
    return max(score, key=score.get)


def _paint_roads(db, plan):
    """The plan's streets painted with the culture's road texture. No Undo step. The patches painted."""
    import landscape
    if not plan.get('roads'):
        return 0
    rs = plan['roads']
    tid = road_texture(db, plan['culture'], (sum(r[0] for r in rs) / len(rs) * 512 + 256, sum(r[1] for r in rs) / len(rs) * 512 + 256))
    if not tid:
        return 0
    by = {}
    for px, py in plan['roads']:
        by.setdefault((px // 16, py // 16), []).append((px % 16) + (py % 16) * 16)
    n = 0
    for (gx, gy), idx in by.items():
        L = landscape.read(db, gx, gy)
        if not L.get('exists') or not L.get('t'):
            continue
        t = list(L['t'])
        for i in idx:
            t[i] = tid
            n += 1
        landscape.write(db, gx, gy, None, t, None)
    db.sync_project()
    return n
