"""The checks for weapons and armour your mod makes (verify.py shows them on Health check and Get ready to share):

- a new piece that never reaches the world: no levelled list, person, creature, container, place, script or
  dialogue line has it, so a player can't come by it;
- a piece in a levelled list at a level far from where the game puts its own pieces of that worth in that list;
- a set with one of a pair: a left pauldron, gauntlet or bracer without its right, or the other way round.

A piece's tier is read from its worth against the game's own pieces of its type (gearsurvey's groups), not from
its name: a forged "Sunsteel" piece, between steel and silver, is not steel because its name says so."""
import bisect
import re
import struct
from collections import defaultdict

import gearplaces
import gearsurvey
from esm import iter_subrecords, zstr
from project import ref_info, unb64

# how far a list's level for a piece may be from the game's own level for that worth. Measured 2026-10-27 with
# measure(): the game's own 6,832 list entries, each held out of its list in turn, are within 2 levels 84% of the
# time, 7 at 95%, 10 at 98%, 12 at 99%; so more than 10 off is further than the game itself goes
TIER_TOL = 10
PAIRS = (('LPauldron', 'RPauldron', 'pauldron'), ('LGauntlet', 'RGauntlet', 'gauntlet'), ('LBracer', 'RBracer', 'bracer'))
SLOT_WORDS = re.compile(r'\b(left|right|helm(et)?|cuirass|pauldrons?|gauntlets?|bracers?|greaves|boots|shield|buckler|tower shield|'
                        r'gloves?|l|r)\b', re.I)


def _cur(db, tag, key):
    """The record as the game will see it (your mod's version when it has one): its index or None."""
    lst = [v for v in db.by_key.get((tag, key), []) if v not in db.dead]
    return lst[-1] if lst else None


def _mine_new(db):
    """Your mod's own weapons and armour that are new (not a change to another file's piece): [(tag, key, piece)]."""
    p = db.project
    out = []
    for rec in p.records.values():
        if rec['tag'] not in ('WEAP', 'ARMO') or rec['flags'] & 0x20:
            continue
        lst = [v for v in db.by_key.get((rec['tag'], rec['key']), []) if v not in db.dead]
        if not lst or any(db.recs[v][3] != db.proj_pidx for v in lst):
            continue
        it = gearsurvey._read(db, lst[-1])
        if it:
            out.append((rec['tag'], rec['key'], it))
    return out


def tier_by_worth(db, it):
    """A piece's tier (0..1) by its value against the game's own of its type: where its value falls among the
    materials' typical values, read off their tiers. None when the type has no game pieces."""
    gs = gearsurvey.survey(db)
    pts = sorted((g['stats']['Value']['med'], gs['tiers'][m]) for (k, t, m), g in gs['groups'].items()
                 if k == it['kind'] and t == it['type'] and m in gs['tiers'])
    if not pts:
        return None
    v = it['stats']['Value']
    xs = [x for x, _t in pts]
    i = bisect.bisect_left(xs, v)
    if i <= 0:
        return pts[0][1]
    if i >= len(pts):
        return pts[-1][1]
    (x0, t0), (x1, t1) = pts[i - 1], pts[i]
    f = 0 if x1 == x0 else (v - x0) / float(x1 - x0)
    return t0 + (t1 - t0) * f


def _reached(db, ids):
    """Of these item ids (lower case), the ones something in the game as it will be loaded hands out."""
    want = set(ids)
    got = set()
    for (tag, _k), lst in db.by_key.items():
        if tag not in ('LEVI', 'NPC_', 'CREA', 'CONT') or not want - got:
            continue
        lv = [v for v in lst if v not in db.dead]
        if not lv:
            continue
        r = db.recs[lv[-1]]
        for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
            if t == 'INAM' and tag == 'LEVI':
                i = zstr(d).lower()
            elif t == 'NPCO' and len(d) >= 36:
                i = zstr(bytes(d)[4:36]).lower()
            else:
                continue
            if i in want:
                got.add(i)
    p = db.project
    for c in p.cells.values():
        for r in c['refs'].values():
            if r.get('deleted'):
                continue
            rid = (ref_info([(t, unb64(d)) for t, d in r['subs']])[0] or '').lower()
            if rid in want:
                got.add(rid)
    # (a script that hands it out, or a dialogue line's result: AddItem "id" and the like)
    texts = []
    for rec in p.records.values():
        if rec['tag'] in ('SCPT', 'INFO'):
            for t, d in iter_subrecords(unb64(rec['data'])):
                if t in ('SCTX', 'BNAM'):
                    texts.append(bytes(d).decode('cp1252', 'replace').lower())
    for s in getattr(p, 'lua', None) or []:
        texts.append((s.get('text') or '').lower())
    blob = '\n'.join(texts)
    for i in want - got:
        if i in blob:
            got.add(i)
    return got


def _off_tier(db, mine):
    """(tag, key, text) for your pieces in a list of the game's at a level far from the game's own for their worth."""
    s = gearplaces.survey(db)
    by_id = {key.lower(): (tag, key, it) for tag, key, it in mine}
    out = []
    for (tag, k), lst in db.by_key.items():
        if tag != 'LEVI':
            continue
        lv = [v for v in lst if v not in db.dead]
        if not lv:
            continue
        r = db.recs[lv[-1]]
        lid = r[1]
        game = s['lists'].get(lid)
        if not game:
            continue
        cur = None
        for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
            if t == 'INAM':
                cur = zstr(d).lower()
            elif t == 'INTV' and cur is not None:
                level = struct.unpack_from('<h', bytes(d))[0] if len(d) >= 2 else 1
                if cur in by_id:
                    gtag, gkey, it = by_id[cur]
                    tier = tier_by_worth(db, it)
                    same = [(g, l) for g, l in game['entries'] if s['gear'][g]['type'] == it['type']]
                    want = gearplaces._level_at(s, same or game['entries'], tier)
                    if tier is not None and abs(level - want) > TIER_TOL:
                        out.append((gtag, gkey, '%s is in the list %s at level %d; the game\'s own pieces of its worth come at about level %d there.'
                                    % (it['name'] or it['id'], lid, level, want)))
                cur = None
    return out


def _stem(name):
    return re.sub(r'\s+', ' ', SLOT_WORDS.sub(' ', name or '')).strip(' ,-').lower()


def _half_pairs(mine):
    """(tag, key, text) for a set (your armour of one name) with one of a pair and not the other."""
    sets = defaultdict(dict)
    for tag, key, it in mine:
        if it['kind'] == 'armor' and _stem(it['name']):
            sets[_stem(it['name'])][it['type']] = (tag, key, it)
    out = []
    for stem, slots in sets.items():
        if len(slots) < 2:
            continue
        for left, right, word in PAIRS:
            has_l, has_r = left in slots, right in slots
            if has_l != has_r:
                tag, key, it = slots[left] if has_l else slots[right]
                out.append((tag, key, 'The set "%s" has a %s %s but no %s one: the other arm goes bare.'
                            % (stem.title(), 'left' if has_l else 'right', word, 'right' if has_l else 'left')))
    return out


def findings(db):
    """[(sev, tag, key, text)] for your mod's weapons and armour."""
    if not getattr(db, 'project', None):
        return []
    mine = _mine_new(db)
    if not mine:
        return []
    out = []
    got = _reached(db, [key.lower() for _t, key, _it in mine])
    for tag, key, it in mine:
        if key.lower() not in got:
            out.append(('warning', tag, key, '%s never reaches the world: no list, person, container, place or script has it, so a player '
                        'can\'t come by it. Right-click it and pick Into the world… to put it where the game puts its own.' % (it['name'] or it['id'])))
    out += [('warning',) + x for x in _off_tier(db, mine)]
    out += [('warning',) + x for x in _half_pairs(mine)]
    return out


def measure(db):
    """How far the game's own lists put their own pieces from the level _level_at gives for their worth, each
    piece held out of its list: {'n', 'within': {d: share}, 'p95'}. Sets TIER_TOL."""
    s = gearplaces.survey(db)
    diffs = []
    for lid, lst in s['lists'].items():
        for g, lv in lst['entries']:
            it = s['gear'][g]
            tier = tier_by_worth(db, it)
            rest = [(x, l) for x, l in lst['entries'] if x != g]
            if tier is None or len(rest) < 2:
                continue
            same = [(x, l) for x, l in rest if s['gear'][x]['type'] == it['type']]
            diffs.append(abs(lv - gearplaces._level_at(s, same or rest, tier)))
    diffs.sort()
    n = len(diffs)
    return {'n': n, 'within': {d: round(sum(1 for x in diffs if x <= d) / float(n), 3) for d in (0, 1, 2, 3, 4, 6, 8, 10)} if n else {},
            'p95': diffs[int(0.95 * (n - 1))] if n else None, 'p99': diffs[int(0.99 * (n - 1))] if n else None}
