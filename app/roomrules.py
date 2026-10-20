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


def recipe(db, purpose, fallback):
    """[(kind, count, where)] for a room of this purpose: the game's own, when enough rooms were seen.
    Counts are for a 3 x 3 room; Auto-furnish scales them with the floor."""
    s = roomsurvey.ready(db)
    K = s['kinds'].get(purpose) if s else None
    if not K or K['rooms'] < MIN_ROOMS:
        return fallback
    out = []
    for fam, share in sorted(K['have'].items(), key=lambda kv: -kv[1]):
        if fam not in roomsurvey.FLOOR_KINDS or share < 0.25:
            continue
        each = K['per_room'].get(fam, share) / share          # how many, in the rooms that have one
        count = max(1, int(round(each)))
        # (the game's rooms of a kind come in all sizes: a small room gets the lesser of these, and
        # Auto-furnish scales with the floor area anyway)
        if purpose not in ('storage', 'kitchen', 'tavern') and fam in ('chest', 'sack', 'crate', 'barrel', 'bench', 'shelf', 'bookshelf', 'table'):
            count = min(count, 2)
        if fam == 'counter':
            count = 1               # (the game's bars are runs of pieces: a bar, its ends, a corner; one piece until those are surveyed)
        where = WHERE.get(fam)
        if where is None:
            w = K['where'].get(fam, {})
            where = 'corner' if fam in ('barrel', 'urn', 'crate') and w.get('corner', 0) >= 0.4 * sum(w.values() or [1]) else 'wall'
        out.append((fam, count, where))
    # the order things go in: big pieces first (they take the walls), then the rest
    out.sort(key=lambda r: (r[0] not in ('bed', 'counter', 'shrine', 'table'), r[0] in ('rug', 'chair', 'chest')))
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
        floor_n = int(round(L['per_9'] * L['where'].get('floor', 0)))
        if floor_n and floor_lamps(db, purpose):
            out.append(('lamp', floor_n, 'wall'))
        cand_n = int(round(L['per_9'] * L['where'].get('furniture', 0) * 0.5))
        if cand_n and not any(f == 'candle' for f, _c, _w in out):
            out.append(('candle', cand_n, 'on_table'))
    return out


def lights(db, purpose):
    """How a room of this kind is lit, from the game: {'per_9': lights per 3 x 3 tiles, 'where': shares,
    'ids': the lights used most}; None when too few rooms were seen."""
    s = roomsurvey.ready(db)
    K = s['kinds'].get(purpose) if s else None
    if not K or K['rooms'] < MIN_ROOMS or not K.get('lights_where'):
        return None
    w = K['lights_where']
    total = sum(w.values()) or 1
    return {'per_9': K['lights_per_9'], 'where': {k: round(v / total, 2) for k, v in w.items()}, 'ids': [i for i, _n in K['light_ids']]}


def floor_lamps(db, purpose):
    """The standing lamps and lanterns the game lights rooms of this kind with (ids that exist here)."""
    L = lights(db, purpose)
    if not L:
        return []
    out = []
    for i in L['ids']:
        low = i.lower()
        if LAMP.search(low) and not NOT_LAMP.search(low) and db.resolve_id(i) is not None:
            out.append(i)
    return out


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
