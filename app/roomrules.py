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
NOT_LAMP = re.compile(r'sconce|candle|wall|hang|chandelier|_de_paper')


ONE_ONLY = ('bed', 'counter', 'shrine')          # one to a room, whatever the game's average (a bunk room comes as a set piece)
MIN_PER_9 = 0.2                                  # a kind the game stands less often than this per 3 x 3 room is left to the set pieces
TABLE_CAP = {'bedroom': 1, 'living': 2, 'storage': 1, 'hall': 1, 'kitchen': 2, 'shop': 1, 'study': 2, 'shrine': 1}    # (a second table in a bedroom reads as clutter, not as lived in; five in a kitchen made "a pathetic dining room")
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
