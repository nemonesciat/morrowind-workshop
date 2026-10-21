"""What the game's containers hold, by the kind of room they stand in and the kind of place: the barrels
in a kitchen hold saltrice and food, the chest in a bedroom clothes and a few coins, the crates in a
trader's storeroom armour and weapons. A container's contents belong to its record (barrel_01_saltrice
is the same barrel everywhere), so "filling" a new container the game's way means standing the game's
own container records in rooms like the ones the game stands them in: Auto-furnish picks the barrel the
game puts in kitchens, and its contents (the game's own leveled lists, where it uses them) come with it.

Where the containers stand comes from the room survey (roomsurvey.py: room kind from what is in the
room, the kind of place from the cell's name); what they hold is read from the records here."""
import re
import struct
from collections import Counter

import kits
import roomsurvey
from esm import iter_subrecords, zstr

_contents = {}
_plain = {}
# Auto-furnish's room purposes, in the room survey's kinds
KIND_OF = {'hall': 'living', 'camp': 'storage', 'ruin': 'storage'}
MIN_POOL = 4           # fewer sightings than this for a room kind and theme: widen to every theme, then every kind


def contents(db, rid):
    """What a container record holds: {'items': [{'id', 'name', 'type', 'count'}], 'lists': [ids of leveled
    lists among them], 'organic', 'respawn', 'script', 'name'}; None for something that isn't a container."""
    low = rid.lower()
    if low in _contents and _contents[low][0] is db.recs:
        return _contents[low][1]
    out = None
    ri = db.resolve_id(rid)
    if ri is not None and db.recs[ri][0] == 'CONT':
        r = db.recs[ri]
        out = {'id': r[1], 'name': r[2], 'items': [], 'lists': [], 'organic': False, 'respawn': False, 'script': ''}
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
            for st, sd in iter_subrecords(data):
                if st == 'NPCO' and len(sd) >= 36:
                    n = struct.unpack_from('<i', sd)[0]
                    iid = zstr(sd[4:36])
                    ii = db.resolve_id(iid)
                    typ = db.recs[ii][0] if ii is not None else ''
                    out['items'].append({'id': iid, 'name': db.recs[ii][2] if ii is not None else '', 'type': typ, 'count': n})
                    if typ == 'LEVI':
                        out['lists'].append(iid)
                elif st == 'FLAG' and len(sd) >= 4:
                    f = struct.unpack_from('<i', sd)[0]
                    out['organic'], out['respawn'] = bool(f & 1), bool(f & 2)
                elif st == 'SCRI':
                    out['script'] = zstr(sd)
        except Exception:
            pass
    _contents[low] = (db.recs, out)
    return out


def plain(db, rid):
    """A container fit to stand in a new place: not scripted (a quest's own), stood by the game in at
    least two places (a one-off chest is somebody's), not named unique, holding no key."""
    low = rid.lower()
    if low in _plain and _plain[low][0] is db.recs:
        return _plain[low][1]
    c = contents(db, rid)
    ok = bool(c) and not c['script'] and 'unique' not in low and kits.game_uses(db, low) >= 2 \
        and not any(re.search(r'(^|_)key(_|$|s)', it['id'].lower()) for it in c['items'])
    _plain[low] = (db.recs, ok)
    return ok


def survey(db):
    """{(family, room kind, theme): [(container id, sightings)]} from the room survey, or None until it
    has run (it runs in the background the first time)."""
    s = roomsurvey.ready(db)
    return s['containers'] if s else None


def _pool(table, fam, kind, theme):
    """The containers of this family seen in rooms like this: for this theme when a few were, else any
    theme, else any kind of room."""
    for keys in (((fam, kind, theme),), [k for k in table if k[0] == fam and k[1] == kind],
                 [k for k in table if k[0] == fam]):
        pool = Counter()
        for k in keys:
            for rid, n in table.get(k, ()):
                pool[rid] += n
        if sum(pool.values()) >= MIN_POOL:
            return pool
    return pool


def pick(db, fam, purpose, theme, rng, palette=(), band_pool=None, max_value=None):
    """The container to stand in a room of this purpose, in a place of this theme: one the game stands in
    rooms like it, chosen at random by how often (the ones used in places of this style three times
    as readily). None when the survey hasn't run or knows nothing of this family.
    band_pool: {container id: sightings} in places as well off as this one is to be (wealthsurvey.py):
    those come up three times as readily too. max_value: nothing holding more than this, about (a
    leveled list by its mean draw); an empty one when nothing cheap enough stands in such rooms."""
    table = survey(db)
    if not table:
        return None
    kind = KIND_OF.get(purpose, purpose)
    pool = _pool(table, fam, kind, theme)
    pal = {p.lower() for p in palette or ()}
    bp = {k.lower() for k in (band_pool or {})}
    weights = [(rid, n * (3 if rid.lower() in pal else 1) * (3 if rid.lower() in bp else 1))
               for rid, n in pool.items() if plain(db, rid) and db.resolve_id(rid) is not None]
    if max_value is not None:
        import wealthsurvey
        cheap = [(rid, w) for rid, w in weights if (wealthsurvey.container_value(db, rid) or 0) <= max_value]
        if not cheap:
            # (none cheap enough in rooms like this: any of the family's that is, from anywhere, else an empty one)
            every = Counter()
            for k, lst in table.items():
                if k[0] == fam:
                    for rid, n in lst:
                        every[rid] += n
            cheap = [(rid, n) for rid, n in every.items() if plain(db, rid) and db.resolve_id(rid) is not None
                     and (wealthsurvey.container_value(db, rid) or 0) <= max_value]
        weights = cheap
    if not weights:
        return None
    total = sum(w for _r, w in weights)
    x = rng.random() * total
    for rid, w in weights:
        x -= w
        if x <= 0:
            return rid
    return weights[-1][0]


def describe(db, rid):
    """A container's contents in a few words: 'saltrice x10, random_food (list)'."""
    c = contents(db, rid)
    if not c:
        return ''
    if not c['items']:
        return 'empty'
    bits = []
    for it in c['items'][:6]:
        bits.append('%s%s%s' % (it['name'] or it['id'], ' (list)' if it['type'] == 'LEVI' else '',
                                ' x%d' % abs(it['count']) if abs(it['count']) > 1 else ''))
    if len(c['items']) > 6:
        bits.append('+%d more' % (len(c['items']) - 6))
    return ', '.join(bits)


def summary(db, fam=None, kind=None, theme=None, top=8):
    """For people: for each family, room kind and theme, the containers the game stands there and what
    they hold. [{'family', 'kind', 'theme', 'n', 'models': [{'id', 'n', 'holds', 'lists', 'plain'}]}]"""
    table = survey(db)
    if table is None:
        return {'ready': False, 'note': 'The room survey is still running (a few minutes); try again later.'}
    out = []
    for (f, k, t), lst in sorted(table.items(), key=lambda kv: -sum(n for _r, n in kv[1])):
        if (fam and f != fam) or (kind and k != kind) or (theme and t != theme):
            continue
        out.append({'family': f, 'kind': k, 'theme': t, 'n': sum(n for _r, n in lst),
                    'models': [{'id': rid, 'n': n, 'holds': describe(db, rid), 'lists': (contents(db, rid) or {}).get('lists', []),
                                'plain': plain(db, rid)} for rid, n in lst[:top]]})
    return {'ready': True, 'rows': out}
