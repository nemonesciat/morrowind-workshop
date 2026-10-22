"""What Auto-furnish puts in a room, from the game's own rooms (roomsurvey.py) rather than a hand-written
list: which furniture a room of each kind gets and how many, what goes on its tables, how many lights it
has and of what kind, and how furniture stands by other furniture (a chest at the foot of the bed).
Until the survey has run once (a few minutes, in the background), the hand-written recipes stand."""
import re

import roomsurvey

MIN_ROOMS = 12            # fewer surveyed rooms of a kind than this: the hand-written recipe stays
# where each kind of thing goes, in Auto-furnish's own words (the survey's "middle" is the origin of a big
# piece standing clear of the wall by its own depth, so big things keep to the walls)
WHERE = {'table': 'centre', 'chair': 'by_table', 'rug': 'rug', 'fire': 'centre', 'bedroll': 'wall', 'counter': 'centre',
         'shrine': 'wall', 'chest': 'by_bed'}
ON_TOP = {'dish': 'dish', 'food': 'food', 'bottle': 'bottle', 'book': 'book', 'candle': 'candle'}
LAMP = re.compile(r'lamp|lantern|torch|brazier')
NOT_LAMP = re.compile(r'sconce|candle|wall|hang|chandelier|_de_paper|torch')     # (a torch is a wall mount: stood on the floor it floated)


ONE_ONLY = ('bed', 'counter', 'shrine')          # one to a room, whatever the game's average (a bunk room comes as a set piece)
MIN_PER_9 = 0.2                                  # a kind the game stands less often than this per 3 x 3 room is left to the set pieces
TABLE_CAP = {'bedroom': 1, 'living': 2, 'storage': 1, 'hall': 1, 'kitchen': 2, 'shop': 1, 'study': 2, 'shrine': 1,
             'bath': 1, 'corridor': 1, 'entry': 0, 'landing': 0, 'barracks': 1, 'armoury': 1, 'training': 1, 'mess': 1, 'guardroom': 1, 'dining': 1}    # (a second table in a bedroom reads as clutter, not as lived in; five in a kitchen made "a pathetic dining room")
# the room-kind survey's purposes (roomkindsurvey.py): Auto-furnish's purpose -> (the survey's kind, its sub-kind)
KIND_OF = {'bath': 'bath', 'corridor': 'hall', 'entry': 'hall', 'landing': 'hall', 'storage': 'storage', 'kitchen': 'kitchen',
           'barracks': 'guard', 'armoury': 'guard', 'training': 'guard', 'mess': 'guard', 'guardroom': 'guard'}
KIND_SUB = {'corridor': 'corridor', 'entry': 'entry', 'landing': 'landing', 'barracks': 'barracks', 'armoury': 'armoury',
            'training': 'training', 'mess': 'mess', 'guardroom': 'guardroom'}
KIND_PURPOSES = ('bath', 'corridor', 'entry', 'landing', 'storage', 'barracks', 'armoury', 'training', 'mess', 'guardroom')
KIND_FLOOR = roomsurvey.FLOOR_KINDS + ('basket', 'screen', 'planter', 'bath', 'rack', 'target')     # what Auto-furnish can stand of the survey's kinds
KIND_CENTRE = ('target', 'screen', 'table')      # out in the room when the game has them there
MIN_KIND_ROOMS = 4
# (the survey counts the lights the game stands on the floor; Auto-furnish's standing lamps are one of
# roomrules.floor_lamps for the nearest room kind)
LIGHT_KIND = {'bath': 'living', 'corridor': 'empty', 'entry': 'empty', 'landing': 'empty', 'barracks': 'bedroom', 'mess': 'living', 'dining': 'living',
              'guardroom': 'living', 'armoury': 'storage', 'training': 'storage'}


def kind_recipe(db, purpose, fallback, culture=None, tiles=9, style=None):
    """[(kind, count per nine tiles, where)] for one of the room-kind survey's purposes (a bathing room, a
    corridor, an entry, a landing, a storeroom, a barracks, an armoury, a training room, a mess, a
    guardroom), from the game's rooms of the kind (its own culture's when it has four or more, else all):
    every furniture kind the game stands there at its rate, where the game stands it (a corner, the
    wall, out in the room), the one-to-a-room kinds capped, the lights at the game's rate; the hand-written
    stand-in until the survey has run."""
    import roomkindsurvey
    s = roomkindsurvey.ready(db)
    if not s:
        return fallback
    K = s['kinds'].get(KIND_OF.get(purpose))
    if not K:
        return fallback
    S = None
    sub = KIND_SUB.get(purpose)
    if sub and K.get('sub:' + sub, {}).get('rooms', 0) >= MIN_KIND_ROOMS:
        S = K['sub:' + sub]
    elif not sub:
        # (the house's own building style when the survey has eight rooms of the kind in it: the
        # survey's "Imperial" stores are the Legion forts', not a Common house's)
        S = K.get(style) if style and K.get(style, {}).get('rooms', 0) >= MIN_KIND_ROOMS * 2 else K.get('*')
    if not S or S.get('rooms', 0) < MIN_KIND_ROOMS:
        S = K.get('*')
    if not S:
        return fallback
    out = []
    for fam, rate in sorted(S['per_9'].items(), key=lambda kv: -kv[1]):
        if fam not in KIND_FLOOR or rate < MIN_PER_9:
            continue
        count = float(rate)
        if fam == 'counter' or fam == 'shrine':
            continue
        if fam == 'bed' and purpose != 'barracks':
            continue
        if fam == 'rack' and purpose not in ('armoury', 'training', 'barracks', 'guardroom'):
            continue                    # (a storeroom's racks are wine racks, the dressings' business; a weapon rack is a guard's)
        if fam == 'target' and purpose not in ('training', 'armoury'):
            continue                    # (the practice dummies: a training room's, and an armoury's in a row at one wall, R11)
        if fam == 'target' and purpose == 'armoury':
            count = max(2.0, count)
        if fam == 'bath' and purpose != 'bath':
            continue                    # (a washtub among a storeroom's barrels is not a bathing room's)
        if purpose == 'storage' and fam in ('planter', 'screen', 'bench', 'table', 'cupboard'):
            continue                    # (a store is stores: the odd planter or bench in the game's is a back room's)
        if purpose in ('corridor', 'landing', 'entry') and fam in ('barrel', 'crate', 'sack', 'chair', 'table', 'cupboard', 'bookshelf', 'bed', 'chest'):
            # (the catalogue's R6: halls, galleries and corridors are lit and carpeted, not furnished: a
            # runner down the middle, a sconce every bay, nothing on the floor but the odd bench, urn
            # or planter; the survey's halls read the game's back passages' stores along with them.
            # A corridor keeps its chairs against the wall: 2.2 per nine tiles, 71% at a wall, in the
            # game's corridors, room-kind survey R2)
            if not (purpose == 'entry' and fam == 'chest') and not (purpose == 'corridor' and fam == 'chair'):
                continue
        if fam == 'planter' and rate < 0.5:
            continue
        if fam == 'table':
            cap = TABLE_CAP.get(purpose, 1)
            if not cap:
                continue
            count = min(count, float(cap))
        elif fam == 'rug':
            continue                    # (rugs go by the room's own rule below)
        elif fam == 'bath':
            count = max(1.0, count)     # (a bathing room always has its tub)
        w = S.get('where_f', {}).get(fam, {})
        tot = float(sum(w.values()) or 1)
        if fam == 'table' and purpose == 'mess':
            # (a mess is one long table, two of the palette's long tables end to end as a dining room's,
            # with a bench down each side: the game's mess scene is table+bench*2, room-kind survey R5)
            where, count = 'long', 1
        elif fam == 'bench' and purpose == 'mess':
            where = 'both_sides'
        elif fam == 'chair' and purpose == 'mess':
            # (the game's mess chairs stand at the wall three times in five, the benches having the table)
            where = 'wall' if w.get('wall', 0) / tot >= 0.5 else 'by_table'
        elif fam == 'chair' and purpose in ('mess', 'barracks', 'guardroom'):
            where = 'by_table' if any(f == 'table' for f, _c, _w in out) or 'table' in S['per_9'] else 'wall'
        elif fam in ('chair', 'bench') and purpose == 'mess':
            where = 'by_table'
        elif fam == 'chest' and purpose == 'barracks':
            where = 'by_bed'
        elif fam in KIND_CENTRE and w.get('middle', 0) / tot >= 0.5:
            where = 'centre'
        elif w.get('corner', 0) / tot >= 0.4:
            where = 'corner'
        else:
            where = 'wall'
        out.append((fam, count, where))
    if purpose == 'kitchen':
        # (the catalogue's R3 kitchen: the hearth with its cookery, the long bench table at the wall and
        # the plate dresser, always; the survey's kit kitchens have their hearth in the wall pieces, so
        # it never reached the recipe, and the stores took every wall before anything else)
        have = {f for f, _c, _w in out}
        if 'fire' not in have:
            out.append(('fire', 1, 'wall'))
        if 'table' not in have:
            out.append(('table', 1.0, 'wall'))
        else:
            out = [(f, max(c, 1.0) if f == 'table' else c, w) for f, c, w in out]
        if 'cupboard' not in have:
            out.append(('cupboard', 1.0, 'wall'))
        else:
            out = [(f, max(c, 1.0) if f == 'cupboard' else c, w) for f, c, w in out]
    if purpose == 'armoury' and not any(f == 'target' for f, _c, _w in out):
        out.append(('target', 2.0, 'wall'))   # (Goldstone's armoury: the practice dummies in a row at one wall, R11)
    if purpose == 'armoury':
        # (the racks along one wall, not every wall: twelve racks in a twelve-tile armoury left no wall
        # for the dummies; four per nine tiles at most, and the dummies take their wall first)
        out = [(f, min(c, 4.0) if f == 'rack' else c, w) for f, c, w in out]
    # (the room's own piece first, then the big pieces, then the rest, as the other recipes)
    first = ('fire', 'bath', 'bed', 'target', 'rack', 'table', 'cupboard')
    out.sort(key=lambda r: (r[0] not in first, first.index(r[0]) if r[0] in first else 9, r[0] in ('chair', 'chest', 'rug')))
    if purpose == 'entry':
        # (the catalogue's R1: an entrance hall is symmetrical about the door's axis: a bench either side
        # of the door, a candle stand at each end, a planter either side of the stair foot. The recipe
        # brings one of each at least, and Auto-furnish mirrors them across the axis)
        have = {f for f, _c, _w in out}
        if 'bench' not in have:
            out.insert(0, ('bench', 1.0, 'wall'))
        else:
            out = [(f, max(c, 1.0) if f == 'bench' else c, w) for f, c, w in out]
        if 'planter' not in have:
            out.append(('planter', 0.6, 'corner'))
        out.append(('rug', 1, 'runner'))
    if purpose in ('corridor', 'landing'):
        out.append(('rug', 1, 'runner'))          # (R6: the runner down the middle, Goldstone's corridors)
    if purpose == 'barracks' and S.get('rug_rooms', 0) >= 0.1:
        out.append(('rug', 1, 'by_bed'))
    if purpose == 'mess':
        out.append(('rug', 1, 'under_table'))
    # what goes on the tables (the survey's tops of its tables), and the lights
    tops = dict((S.get('tops') or {}).get('table', []))
    total = sum(tops.values()) or 1
    n_tables = sum(c for f, c, _w in out if f == 'table') or 1
    for what, n in sorted(tops.items(), key=lambda kv: -kv[1]):
        if what in ON_TOP and n / float(total) >= 0.06:
            out.append((ON_TOP[what], max(1, int(round(5 * n / float(total) * n_tables))), 'on_table'))
    lw = S.get('lights_where') or {}
    ltot = float(sum(lw.values()) or 1)
    floor_n = int(round(S.get('lights_per_9', 0) * lw.get('floor', 0) / ltot))
    if purpose == 'entry':
        floor_n = max(1, floor_n)             # (a candle stand to mirror, R1)
    if floor_n and floor_lamps(db, LIGHT_KIND.get(purpose, 'living')):
        out.append(('lamp', floor_n, 'wall'))
    cand_n = int(round(S.get('lights_per_9', 0) * lw.get('furniture', 0) / ltot * 0.5))
    if cand_n and any(f == 'table' for f, _c, _w in out) and not any(f == 'candle' for f, _c, _w in out):
        out.append(('candle', cand_n, 'on_table'))
    return out
EXTRA_KINDS = ('basket', 'screen', 'planter')    # the set pieces' other kinds Auto-furnish can stand on its own (furnish.FAMILIES has them)
BUNK_THEMES = ('guild', 'tavern')                # where the game's bedrooms are bunk rooms: as many beds as it stands, up to three


def recipe(db, purpose, fallback, like=None, theme='house'):
    """[(kind, count, where)] for a room of this purpose: the game's own, when enough rooms were seen.
    Counts are for a 3 x 3 room, as the game stands them per nine tiles of such rooms (a float: Auto-furnish
    scales it with the room's floor and rounds by chance, so a bench the game has in one bedroom in five
    comes one time in five); the one-to-a-room kinds (a bed, a counter, a shrine) are a plain 1.
    like: the survey of one exemplary place (roomsurvey.one, "Furnish like…"): its rooms of the purpose
    are the model when it has any, the game's rooms fill in what they lack."""
    s = roomsurvey.ready(db)
    if purpose == 'hall' and s:
        return _hall_recipe(s, fallback)
    K = s['kinds'].get(purpose) if s else None
    if not K or K['rooms'] < MIN_ROOMS:
        if purpose == 'kitchen':
            out = _kitchen_stores(db, list(fallback))
            if not any(f == 'fire' for f, _c, _w in out):
                out.insert(0, ('fire', 1, 'wall'))    # (first: the hearth takes its wall before the stores do, R3)
            return out
        return fallback
    if like and like.get('kinds', {}).get(purpose, {}).get('rooms'):
        K = _blend(like['kinds'][purpose], K)
    if 'per_9' not in K:
        # (an older survey file, from before the per-nine-tiles counts: the mean count per room, scaled
        # by the typical room's size)
        K = dict(K, per_9={f: v * 9.0 / max(4, K.get('tiles') or 9) for f, v in K['per_room'].items()}, extra_per_9={})
    out = []
    for fam, rate in sorted(K['per_9'].items(), key=lambda kv: -kv[1]):
        if fam not in roomsurvey.FLOOR_KINDS or rate < MIN_PER_9:
            continue
        count = float(rate)
        if fam == 'counter' and purpose not in ('shop', 'tavern'):
            continue                # (the game's bar pieces turn up as ledges in a bedroom or two: no bar there)
        if fam == 'bed' and purpose != 'bedroom':
            continue
        if fam == 'shrine' and purpose != 'shrine':
            continue                # (an altar in a living room: "a strange choice here")
        if fam == 'bed' and theme in BUNK_THEMES:
            count = max(1.0, min(3.0, count))   # (a guild's or an inn's bunk room)
        elif fam in ONE_ONLY:
            count = 1
        elif fam == 'table':
            count = min(count, TABLE_CAP.get(purpose, 3))
        elif fam == 'rug':
            count = 1               # (rugs go where the furniture is: under the table, beside the bed; see furnish)
        elif fam == 'chest' and purpose == 'bedroom':
            count = max(1.0, count)   # (the chest at the foot of the bed)
        where = WHERE.get(fam)
        if where is None:
            w = K['where'].get(fam, {})
            where = 'corner' if fam in ('barrel', 'urn', 'crate') and w.get('corner', 0) >= 0.4 * sum(w.values() or [1]) else 'wall'
        out.append((fam, count, where))
    # the set pieces' other kinds the game stands loose as well (baskets by the sacks)
    for fam, rate in (K.get('extra_per_9') or {}).items():
        if fam in EXTRA_KINDS and rate >= MIN_PER_9:
            out.append((fam, float(rate), 'wall'))
    if purpose == 'kitchen':
        out = _kitchen_stores(db, out)
        # (the catalogue's R3 kitchen: the long bench table at the wall and the plate dresser, always)
        have = {f for f, _c, _w in out}
        if 'table' not in have:
            out.append(('table', 1, 'wall'))
        else:
            out = [(f, max(c, 1.0) if f == 'table' else c, w) for f, c, w in out]
        if 'cupboard' not in have:
            out.append(('cupboard', 1, 'wall'))
        else:
            out = [(f, max(c, 1.0) if f == 'cupboard' else c, w) for f, c, w in out]
    if purpose == 'study':
        out.append(('chair', 1, 'wall'))      # (the reading chair at the wall: the catalogue's R5)
    if purpose == 'tavern' and not any(f == 'fire' for f, _c, _w in out):
        out.append(('fire', 1, 'wall'))       # (the tavern's hearth: the catalogue's R9, the Anchor's Rest)
    if purpose == 'tavern':
        # (the benches at the long tables, the Katariah's and the Anchor's Rest's: by the tables, not the
        # walls, and before the chairs, so they take the long sides)
        out = [(f, c, 'by_table' if f == 'bench' else w) for f, c, w in out]
        if not any(f == 'bench' for f, _c, _w in out):
            out.append(('bench', 1.0, 'by_table'))
        out = [r for r in out if r[0] == 'bench'] + [r for r in out if r[0] != 'bench']
    if purpose == 'kitchen' and not any(f == 'fire' for f, _c, _w in out):
        # a hearth in every kitchen (the user's catalogue: a Common stone kitchen's fireplace with a pot
        # beside it). The game's kit kitchens have a free-standing one in only one room in twelve, because
        # the Common sets' hearths are part of their wall pieces; Auto-furnish stands one where the
        # culture's places have a free-standing model (furnish.hearth_models), else none.
        out.append(('fire', 1, 'wall'))
    # the order things go in: the room's own piece first (the bed takes the best wall), the big pieces
    # next (they take the walls), then the rest
    out.sort(key=lambda r: (r[0] not in ('bed', 'counter', 'shrine', 'fire'), r[0] != 'table', r[0] in ('rug', 'chair', 'chest')))
    # what the game puts on its tables and counters in rooms like this
    tops = {}
    for (kind, under), lst in s['tops'].items():
        if kind == purpose and under in ('table', 'counter'):
            for what, n in lst:
                tops[what] = tops.get(what, 0) + n
    total = sum(tops.values()) or 1
    n_tables = sum(c for f, c, _w in out if f in ('table', 'counter')) or 1
    for what, n in sorted(tops.items(), key=lambda kv: -kv[1]):
        if what in ON_TOP and n / total >= 0.06:
            out.append((ON_TOP[what], max(1, int(round(6 * n / total * n_tables))), 'on_table'))
    # lights, as many as the game gives a room like this: lamps on the floor by the walls, candles on the tables
    L = lights(db, purpose)
    if L:
        if 'lamp_per_9' in L:
            # (wallsurvey2: standing lamps and candles counted by kind; the dressings bring candles too,
            # so the recipe asks for only part of the game's candles)
            floor_n = int(round(L['lamp_per_9']))
            cand_n = int(round(L['candle_per_9'] * 0.5))
        else:
            floor_n = int(round(L['per_9'] * L['where'].get('floor', 0)))
            cand_n = int(round(L['per_9'] * L['where'].get('furniture', 0) * 0.5))
        if floor_n and floor_lamps(db, purpose):
            out.append(('lamp', floor_n, 'wall'))
        if cand_n and not any(f == 'candle' for f, _c, _w in out):
            out.append(('candle', cand_n, 'on_table'))
    return out


def _kitchen_stores(db, out):
    """A kitchen's stores at the room-kind survey's rates, which read Tamriel Data's crates, sacks and
    barrels by name as well as id (R4): six crates, six sacks, five barrels per nine tiles along the
    walls, baskets and an urn; the recipe's own lines for those kinds replaced."""
    try:
        import roomkindsurvey
        rk = roomkindsurvey.ready(db)
        KK = rk['kinds']['kitchen']['*'] if rk and rk.get('kinds', {}).get('kitchen') else None
    except Exception:
        KK = None
    if not KK or KK.get('rooms', 0) < MIN_KIND_ROOMS:
        return out
    for fam in ('crate', 'sack', 'barrel', 'basket', 'urn'):
        rate = KK['per_9'].get(fam, 0)
        if rate < MIN_PER_9:
            continue
        w = KK.get('where_f', {}).get(fam, {})
        where = 'corner' if w.get('corner', 0) >= 0.4 * sum(w.values() or [1]) else 'wall'
        out = [r for r in out if r[0] != fam] + [(fam, float(rate), where)]
    return out


HALL_KINDS = {'bench': 0.6, 'urn': 0.6, 'chest': 0.4, 'crate': 0.3, 'barrel': 0.3, 'planter': 0.8, 'screen': 0.5, 'basket': 0.4,
              'shelf': 0.3, 'bookshelf': 0.15}      # what a hall takes of the game's living rooms' rates (the rest is a living room's)


def _hall_recipe(s, fallback):
    """A hall's recipe: the game names no room a hall, so its rooms with nothing standing in them ('empty':
    lanterns, plants, a rack) and its living rooms at a fraction of their rates stand for it: a bench or two
    along the wall, an urn, a planter, a chest, a runner rug, never a table or a chair. "Halls tend to be
    completely barren and boring to look at" was the user's verdict on the hand-written one."""
    Kl = s['kinds'].get('living')
    Ke = s['kinds'].get('empty')
    if not Kl or Kl['rooms'] < MIN_ROOMS or 'per_9' not in Kl:
        return fallback
    out = []
    for fam, k in HALL_KINDS.items():
        rate = (Kl['per_9'].get(fam) or Kl.get('extra_per_9', {}).get(fam) or 0) * k
        if Ke and 'extra_per_9' in Ke:
            rate = max(rate, (Ke['extra_per_9'].get(fam) or 0))       # (what the game's empty rooms hold anyway)
        if rate >= MIN_PER_9 * 0.5:
            w = Kl['where'].get(fam, {})
            where = 'corner' if fam in ('barrel', 'urn', 'crate') and w.get('corner', 0) >= 0.4 * sum(w.values() or [1]) else 'wall'
            out.append((fam, float(rate), where))
    out.sort(key=lambda r: -r[1])
    # (a hall of three tiles or more always gets its bench: the catalogue's halls have one along the wall,
    # and a hall left to the dice came out as "completely barren")
    if out and out[0][0] != 'bench':
        out = [r for r in out if r[0] != 'bench']
        out.insert(0, ('bench', max(1.0, (Kl['per_9'].get('bench') or 0) * HALL_KINDS['bench']), 'wall'))
    else:
        out[0] = ('bench', max(1.0, out[0][1]), 'wall')
    out.append(('rug', 1, 'runner'))
    return out


def _blend(M, K):
    """One exemplary place's rooms of a kind as the model, with the game's rooms of the kind behind
    them: the model's rates for every kind it has (and none for the kinds it hasn't, when it has three
    rooms or more to say so), the game's where the model is a room or two."""
    n = M['rooms']
    w = min(1.0, n / 3.0)                # one room: a third model, two thirds game; three or more: all model
    per9 = {}
    for f in set(M.get('per_9', {})) | set(K.get('per_9', {})):
        per9[f] = w * M.get('per_9', {}).get(f, 0) + (1 - w) * K.get('per_9', {}).get(f, 0)
    extra = {}
    for f in set(M.get('extra_per_9', {})) | set(K.get('extra_per_9', {})):
        extra[f] = w * M.get('extra_per_9', {}).get(f, 0) + (1 - w) * K.get('extra_per_9', {}).get(f, 0)
    where = dict(K.get('where', {}))
    where.update(M.get('where', {}))
    return dict(K, per_9=per9, extra_per_9=extra, where=where, cover=M.get('cover', K.get('cover')),
                all_per_9=M.get('all_per_9', K.get('all_per_9')), like=True)


def density(db, purpose, like=None):
    """How full the game's rooms of this kind are: {'cover': median floor cover, 'per_9': pieces of every
    kind per nine tiles}; None until surveyed."""
    s = roomsurvey.ready(db)
    K = s['kinds'].get(purpose) if s else None
    if not K or K['rooms'] < MIN_ROOMS or 'cover' not in K:
        return None
    if like and like.get('kinds', {}).get(purpose, {}).get('rooms'):
        K = _blend(like['kinds'][purpose], K)
    # (the pieces standing on the floor and the set pieces' other kinds; not the dishes and books on the
    # tables, which the dressings bring)
    per9 = sum(K.get('per_9', {}).values()) + sum(v for f, v in (K.get('extra_per_9') or {}).items() if f not in roomsurvey.TOP_KINDS)
    return {'cover': K['cover'], 'per_9': round(per9, 2)}


def lights(db, purpose):
    """How a room of this kind is lit, from the game: {'per_9': lights per 3 x 3 tiles, 'where': shares,
    'ids': the lights used most}; None when too few rooms were seen."""
    s = roomsurvey.ready(db)
    purpose = LIGHT_KIND.get(purpose, purpose)
    K = s['kinds'].get(purpose) if s else None
    if not K or K['rooms'] < MIN_ROOMS or not K.get('lights_where'):
        return None
    w = K['lights_where']
    total = sum(w.values()) or 1
    out = {'per_9': K['lights_per_9'], 'where': {k: round(v / total, 2) for k, v in w.items()}, 'ids': [i for i, _n in K['light_ids']]}
    # by kind of light, from the walls-and-lights survey when it has run (standing lamps 1.2 to 1.6 per
    # 3 x 3 in a home's rooms, candles 2.7 to 4.3, mostly on tables and counters)
    import wallsurvey2
    W = wallsurvey2.light_rule(db, purpose)
    if W and W['rooms'] >= MIN_ROOMS:
        out['lamp_per_9'] = W['per_9'].get('lamp', 0)
        out['candle_per_9'] = W['per_9'].get('candle', 0)
        out['sconce'] = (W['rooms_with'].get('sconce', 0), W['per_room_when'].get('sconce', 0))
    return out


def floor_lamps(db, purpose):
    """The standing lamps the game lights rooms of this kind with (ids that exist here): not the lanterns
    and lamps it hangs up (decorsurvey.py: the game stands a lantern on the floor one time in a hundred)."""
    import decorsurvey
    L = lights(db, purpose)
    if not L:
        return []
    out = []
    for i in L['ids']:
        low = i.lower()
        if LAMP.search(low) and not NOT_LAMP.search(low) and db.resolve_id(i) is not None:
            h = decorsurvey.hangs(db, i)
            if h and h[0] != 'floor':
                continue
            out.append(i)
    return out


def hung_lights(db, purpose):
    """The lanterns and lamps the game hangs in rooms of this kind: [(id, bottom height above the floor,
    gap under the ceiling or None)], how many hang in a room of this kind, and the game's typical size of
    such a room in tiles (a bigger room gets a few more, not in proportion)."""
    import decorsurvey
    L = lights(db, purpose)
    if not L:
        return [], 0, 9
    out = []
    for i in L['ids']:
        low = i.lower()
        if db.resolve_id(i) is None or 'sconce' in low or 'wall' in low:
            continue                      # (a sconce is fixed to a wall, not hung in the air)
        h = decorsurvey.hangs(db, i)
        if h and h[0] == 'hung':
            out.append((i, h[1], h[2]))
    # how many hang per room of this kind (decorsurvey), for a room of the game's typical size
    per_room = decorsurvey.hung_per_room(db, purpose)
    if not per_room:
        return out, 0, 9
    s = roomsurvey.ready(db)
    K = s['kinds'].get(purpose) if s else None
    return out, per_room, max(4, (K or {}).get('tiles') or 9)


def chandeliers(db, style):
    """The chandeliers the game hangs in places built of this kit (the Imperial sets: a Dunmer house
    has none), most used first; [] when the style hangs none or the survey hasn't run."""
    import wallsurvey2
    S = wallsurvey2.style_lights(db, style)
    if not S:
        return []
    return [i for i, _n in S['light'].get('chandelier', []) if db.resolve_id(i) is not None]


MIN_GROUPS = 30


def clusters(db):
    """How the game groups floor clutter (crates, barrels, sacks, urns): {'nn': {family: typical
    distance to the nearest of its own kind}, 'nn_any', 'sizes': [[size, share]], 'where': {'corner':
    share, 'wall': ..., 'middle': ...}, 'mixed': share of groups of more than one family}; None until
    enough groups were seen."""
    s = roomsurvey.ready(db)
    c = s.get('clusters') if s else None
    return c if c and c.get('groups', 0) >= MIN_GROUPS else None


def beside(db, thing, by):
    """How the game stands one thing by another: {'dist', 'dx', 'dy', 'along_x', 'facing'} in the
    other's own frame (a chest 160 from the bed, mostly along its length), or None."""
    s = roomsurvey.ready(db)
    return s['pairs'].get((thing, by)) if s else None
