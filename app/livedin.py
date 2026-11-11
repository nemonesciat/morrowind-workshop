"""Lived in: what people leave round the spots they use, the way the game leaves it (the user, 2026-10-30: "when making
these, you want them to feel lived in", and interiors and dungeons "more realistic than hollow shells").

The game's spots people use are its anchors: beds, bedrolls, fires, tables and work spots (an anvil, an alembic, a
loom, a desk). Round 85% of its bedrolls lies something, four things at the median, eight and a half in a camp: a
bowl, a cup, bread, a bottle of local brew, a sack of food. What lies within reach of each of the game's anchors is
kept whole, in the anchor's own frame, as an example (a scene), with the place's setting and, in a dungeon, the kind
of band living there. A place is then made lived in anchor by anchor: one of the game's scenes round the same kind of
spot, the same model and the same band and setting first, laid round yours, turned with it, each thing set down on
what is under it (the table's top, the floor) or left out where there is nothing to set it on.

Only things a person leaves: no keys, nothing with a script (quest things), no people. One Undo."""
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

import mapdata

VERSION = 5                     # (2: 'camps', the game's dungeon camps kept whole; 3: no plants; 4: 'stories'; 5: no hung things)
REACH = 192                     # across from an anchor's origin, units: what lies within reach of it
DZ = 160                        # up or down from the anchor's middle
KEEP = 60                       # scenes kept a kind of anchor and setting
TOP = 0.5                       # a thing higher than this share of the anchor's height lies on it (a table's top)
ALREADY = 2                     # an anchor with this many small things round it already is left as it is
ANCHORS = [('bedroll', re.compile(r'bedroll')),
           ('bed', re.compile(r'(^|_)bed(_|\d|$)|_bed_|bunk|hammock')),
           ('fire', re.compile(r'campfire|firepit|fire_pit|light_fire|logpile|_fire_|firewood|cauldron|cookpot|kettle')),
           ('table', re.compile(r'table')),
           ('work', re.compile(r'anvil|forge|alembic|loom|spinning|grindstone|workbench|desk'))]
NOT_ANCHOR = re.compile(r'chair|stool|bench(?!.*work)|shelf|rug|banner|tapestry')
SMALL = {'MISC', 'INGR', 'ALCH', 'BOOK', 'APPA', 'WEAP', 'ARMO', 'CLOT', 'LOCK', 'PROB', 'REPA'}
# (no keys, notes for a quest, markers; and no plants, eggs or corpses: the game files a harvestable mushroom or
# lichen as a small container, and the first camps grew kanet on their tables, lab jcamp3)
NOT_THING = re.compile(r'^key_|_key$|_key_|^bk_.*(note|letter)_|marker|^sound|propylon|^misc_soulgem_azura|^t_.*_unique'
                       r'|flora|kollop|_egg|egg_|corpse|_dead|plant|kanet|lichen|mushroom|bittergreen|_bush|^bm_.*_(berry|herb)')
_mem = {}


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'livedin_%s_v%d.json' % (_sig(db), VERSION))


def anchor_kind(low, tag):
    """'bedroll', 'bed', 'fire', 'table', 'work' or None, for a thing's id and record type."""
    if tag not in ('STAT', 'ACTI', 'CONT', 'LIGH', 'DOOR', 'MISC', 'APPA') or NOT_ANCHOR.search(low):
        return None
    for k, rx in ANCHORS:
        if rx.search(low):
            return k
    return None


class _Info:
    """Record type, box and whether it has a script, by id."""
    def __init__(self, db):
        self.db, self.m = db, {}

    def __call__(self, rid):
        low = rid.lower()
        if low not in self.m:
            ri = self.db.resolve_id(rid)
            if ri is None:
                self.m[low] = (None, None, False)
            else:
                from esm import iter_subrecords
                r = self.db.recs[ri]
                scripted = False
                if r[0] in SMALL or r[0] in ('CONT', 'LIGH'):
                    try:
                        scripted = any(t == 'SCRI' for t, _d in iter_subrecords(self.db.files[r[3]].record_at(r[4])[2]))
                    except Exception:
                        scripted = False
                self.m[low] = (r[0], mapdata.object_bounds(self.db, ri), scripted)
        return self.m[low]


def _small(low, tag, b, s, scripted):
    """A thing a person leaves lying about: small, loose, no script, no key."""
    if scripted or NOT_THING.search(low) or not b:
        return False
    w = max(b[3] - b[0], b[4] - b[1]) * s
    if tag in SMALL:
        return True
    return (tag == 'LIGH' and w < 40) or (tag == 'CONT' and w < 70)


def _bands(db, places):
    """{place key: band kind} for the game's dungeons with a hostile band (castsurvey.band_kind)."""
    import castsurvey
    people, out = {}, {}
    for p in places:
        if p['setting'] not in castsurvey.DUNGEONS:
            continue
        ps = []
        for n in p['npcs']:
            low = n.lower()
            if low not in people:
                ri = db.resolve_id(n)
                people[low] = castsurvey.person(db, ri) if ri is not None else None
            o = people[low]
            if o and o['fight'] >= castsurvey.HOSTILE:
                ps.append(o)
        if len(ps) >= 2:
            out[p['key']] = castsurvey.band_kind(ps, p['setting'])
    return out


def learn(db):
    """{'scenes': {kind: [{'a': anchor id, 'h': its height, 'set', 'band', 'items': [[id, lx, ly, lz, rx, ry, rz,
    s, top]]}]}, 'share': {kind: share of anchors with something}, 'median': {kind: things}}. Cached by the load order."""
    key = id(db.recs)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                _mem[key] = json.load(f)
                return _mem[key]
    except (OSError, ValueError):
        pass
    import castsurvey
    from project import ref_info
    places = castsurvey.read_places(db)
    band = _bands(db, places)
    info = _Info(db)
    by = defaultdict(list)
    counts = defaultdict(list)
    camps, beds_per, people = defaultdict(list), defaultdict(list), {}
    stories, story_n = defaultdict(list), defaultdict(list)
    for p in places:
        k = p['key']
        try:
            refs, _h = db.cell_refs(k, without_project=True)
        except Exception:
            continue
        things = []
        for r in refs.values():
            rid, pos, s, dead = ref_info(r['subs'])[:4]
            if dead or not rid:
                continue
            tag, b, scr = info(rid)
            if tag is None:
                continue
            things.append((rid, rid.lower(), tag, b, pos, s or 1.0, scr))
        small = [t for t in things if _small(t[1], t[2], t[3], t[5], t[6])]
        for rid, low, tag, b, pos, s, _scr in things:
            ak = anchor_kind(low, tag)
            if not ak or not b:
                continue
            bottom, h = pos[2] + b[2] * s, (b[5] - b[2]) * s
            cz = bottom + h / 2
            c, sn = math.cos(pos[5]), math.sin(pos[5])
            items = []
            for t in small:
                if t[1] == low and t[4] == pos:
                    continue
                dx, dy = t[4][0] - pos[0], t[4][1] - pos[1]
                if abs(dx) >= REACH or abs(dy) >= REACH or abs(t[4][2] - cz) >= DZ:
                    continue
                lx, ly = c * dx - sn * dy, sn * dx + c * dy
                lz = t[4][2] - bottom
                items.append([t[0], round(lx, 1), round(ly, 1), round(lz, 1), round(t[4][3], 3), round(t[4][4], 3),
                              round((t[4][5] - pos[5]) % (2 * math.pi), 3), round(t[5], 2), 1 if lz > h * TOP else 0])
            counts[ak].append(len(items))
            if items:
                by[(ak, p['setting'])].append({'a': low, 'h': round(h, 1), 'set': p['setting'], 'band': band.get(k, ''), 'items': items})
        if p['setting'] in castsurvey.DUNGEONS:
            _camps_of(db, p, things, band.get(k, ''), camps, beds_per, people)
            _stories_of(db, p, things, band.get(k, ''), stories, story_n)
    scenes = defaultdict(list)
    for (ak, st), lst in by.items():
        # (spread over the game: one in so many, the busier ones kept as readily as the bare ones)
        rng = random.Random(hash((ak, st)) & 0xFFFF)
        rng.shuffle(lst)
        banded = [x for x in lst if x['band']]
        scenes[ak] += (banded[:KEEP // 2] + [x for x in lst if not x['band']])[:KEEP] if banded else lst[:KEEP]
    kept = {}
    for key, lst in camps.items():
        rng = random.Random(hash(key) & 0xFFFF)
        rng.shuffle(lst)
        kept[key] = lst[:KEEP]
    out = {'scenes': dict(scenes),
           'share': {k: round(sum(1 for n in v if n) / len(v), 3) for k, v in counts.items() if v},
           'median': {k: sorted(v)[len(v) // 2] for k, v in counts.items() if v},
           # (camps by 'band|setting', and the beds a hostile person the game's dungeons of the band have)
           'camps': kept, 'beds_per': {b: round(sorted(v)[len(v) // 2], 2) for b, v in beds_per.items() if len(v) >= 5}}
    tk = {}
    for key, lst in stories.items():
        rng = random.Random(hash(key) & 0xFFFF)
        rng.shuffle(lst)
        tk[key] = lst[:KEEP]
    # (stories by 'kind|setting', and how many a place of the setting has: the mean, kind by kind)
    out['stories'] = tk
    out['story_n'] = {k: round(sum(v) / len(v), 2) for k, v in story_n.items() if v}
    _mem[key] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except OSError:
        pass
    return out


def _pick(scenes, low, h, setting, band, rng):
    """A scene for an anchor: the same model, band and setting first, of a height near its own; one of the best few."""
    def score(sc):
        v = 0.0
        if sc['a'] == low:
            v += 3
        if band and sc['band'] == band:
            v += 2
        if sc['set'] == setting:
            v += 1.5
        v -= min(2.0, abs(sc['h'] - h) / max(20.0, h))
        return v + rng.random() * 0.5
    best = sorted(scenes, key=score, reverse=True)[:6]
    return rng.choice(best) if best else None


def apply(db, cell, band='', amount=1.0, seed=None, setting=None, only=None, commit=True, camps=True, stories=True, already=None):
    """Make a place lived in: round each of its anchors (or only these ref keys) that has next to nothing round it,
    one of the game's own scenes for such a spot. band: who lives there (a castsurvey band kind) to pick scenes by;
    setting: the kind of place (else read from its name and pieces). amount: the share of anchors dressed (1: as many
    as the game dresses). already: an anchor with this many small things round it is left as it is (ALREADY; a second
    pass to fill a place to the game's count asks more, and keeps clear of what lies there). One Undo step (commit
    False: none, the caller's change takes it in). {'anchors', 'things'}."""
    import editing
    import dwemer
    from project import set_ref_pos, zs
    editing._require_project(db)
    L = learn(db)
    seed = int(seed) if seed is not None else random.randrange(1, 1 << 30)
    rng = random.Random(seed)
    m = mapdata.cellmap(db, cell)
    if not m.get('exists'):
        raise editing.EditError('There is no place called that.')
    setting = setting or _setting_of(db, m)
    camp = {'camps': 0, 'pieces': 0, 'anchors': []}
    import castsurvey
    if camps and not only and setting in castsurvey.DUNGEONS:
        # (a dungeon with too few beds for its band: the game's own camps first, then what they leave round them)
        camp = lay_camps(db, cell, band, None, seed, m)
        if camp['pieces']:
            m = mapdata.cellmap(db, cell)
    story = {'stories': 0, 'pieces': 0}
    if stories and not only and setting in castsurvey.DUNGEONS:
        # (and what happened there: the game's own fallen adventurers, offerings and bones of such places)
        story = tell_stories(db, cell, band, seed, m)
        if story['pieces']:
            m = mapdata.cellmap(db, cell)
    info = _Info(db)
    sc = dwemer._thing_scene(db, m['refs'])
    small = []
    anchors = []
    for r in m['refs']:
        tag, b, scr = info(r['id'])
        if tag is None:
            continue
        low = r['id'].lower()
        if _small(low, tag, b, r['s'] or 1.0, scr):
            small.append(r['p'])
        ak = anchor_kind(low, tag)
        if ak and b and (not only or r['k'] in only):
            anchors.append((r, ak, b))
    mine = db.project.plugin.lower()
    c_, _refs = editing._cell(db, cell)
    placed, dressed = 0, 0
    taken = []
    clear = _keep_clear(db, cell, m)
    # (a second pass keeps clear of the things lying there already: a cup set into the first pass's bowl)
    lying = [(p[0], p[1], p[2]) for p in small] if already and already > ALREADY else []
    for r, ak, b in anchors:
        pos, s = r['p'], r['s'] or 1.0
        bottom, h = pos[2] + b[2] * s, (b[5] - b[2]) * s
        near = sum(1 for p in small if abs(p[0] - pos[0]) < REACH and abs(p[1] - pos[1]) < REACH and abs(p[2] - bottom - h / 2) < DZ)
        if near >= (already or ALREADY) and not only:
            continue
        share = (L['share'].get(ak) or 0.8) * amount
        if not only and r['k'] not in camp['anchors'] and rng.random() > share:
            continue
        scene = _pick(L['scenes'].get(ak) or [], r['id'].lower(), h, setting, band, rng)
        if not scene:
            continue
        c, sn = math.cos(pos[5]), math.sin(pos[5])
        put = 0
        for rid, lx, ly, lz, rx, ry, rrz, isc, top in scene['items']:
            if top and abs(scene['h'] - h) > max(12.0, 0.15 * h):
                continue                      # (it lay on a table of another height: nothing to set it on here)
            x, y = pos[0] + c * lx + sn * ly, pos[1] - sn * lx + c * ly
            if any(math.hypot(x - tx, y - ty) < 6 for tx, ty in taken):
                continue
            if lying and any(math.hypot(x - tx, y - ty) < 14 and abs(bottom + lz - tz) < 60 for tx, ty, tz in lying):
                continue
            # (set down on what's under it: from a little over where it lay, the first surface below)
            want = bottom + (lz * h / scene['h'] if top and scene['h'] else lz)
            # (nothing between the spot and it: a bedroll against a cave wall had the far half of the game's
            # arrangement go into the rock. Its own anchor in the way is no wall)
            d = math.hypot(x - pos[0], y - pos[1])
            if d > 24:
                o = (pos[0], pos[1], max(want, bottom) + 14.0)
                wall = sc.nearest_any(o, ((x - pos[0]) / d, (y - pos[1]) / d, 0.0), d + 12)
                if wall is not None and sc.owner(wall[1]) != r['k']:
                    continue
            hit = sc.nearest_any((x, y, want + 40.0), (0.0, 0.0, -1.0), 140.0)
            if hit is None:
                continue
            surf = want + 40.0 - hit[0]
            if abs(surf - want) > 48:
                continue                      # (a wall or a hole where it lay)
            ri = db.resolve_id(rid)
            if ri is None:
                continue
            ib = mapdata.object_bounds(db, ri)
            z = surf - (ib[2] * isc if ib else 0.0) if abs(rx) < 0.3 and abs(ry) < 0.3 else surf + max(0.0, lz - (want - bottom))
            if ib and not top:
                # (the user's Senchal, 2026-11-11: "crate in middle of stair landing", "crates in way of path", "make
                # sure the clutter is at least arranged so it isn't in the way or clipping into walls")
                rad = min(max(ib[3] - ib[0], ib[4] - ib[1]) * isc / 2.0, 70.0)
                if _in_clear(clear, x, y, surf, rad):
                    continue                  # (on a stair's foot or head, a door's floor or a way between them)
                mid = z + (ib[2] + ib[5]) / 2.0 * isc
                near_ = [sc.nearest_any((x, y, mid), (math.cos(a_ * math.pi / 4), math.sin(a_ * math.pi / 4), 0.0), max(rad, 30.0)) for a_ in range(8)]
                near_ = [h_ for h_ in near_ if h_ is not None and sc.owner(h_[1]) != r['k']]
                if rad >= BODY_MIN and any(h_[0] < rad * BODY_IN for h_ in near_):
                    continue                  # (its body in a wall, a post or another piece)
                if (abs(rx) > 0.3 or abs(ry) > 0.3) and not near_ and d > LEAN_REACH:
                    continue                  # (it leaned on something that is not here: a book stood on its edge in the open floor)
            rk = db.project.new_ref_key()
            editing._store(c_, rk, mine, int(rk.rsplit('|', 1)[1]),
                           set_ref_pos([('NAME', zs(db.recs[ri][1]))], (x, y, z, rx, ry, (pos[5] + rrz) % (2 * math.pi)), isc))
            taken.append((x, y))
            put += 1
        if put:
            dressed += 1
            placed += put
    if placed:
        db.sync_project()
    if (placed or camp['pieces'] or story['pieces']) and commit:
        editing.commit(db, 'Made %s lived in: %s%s%d things round %d spots' % (
            editing.cell_label(db, cell), ('%d camps, ' % camp['camps']) if camp['camps'] else '',
            ('%d stories, ' % story['stories']) if story['stories'] else '', placed, dressed))
    return {'anchors': dressed, 'things': placed, 'looked': len(anchors), 'seed': seed, 'camps': camp['camps'], 'camp_pieces': camp['pieces'],
            'stories': story['stories'], 'story_pieces': story['pieces']}


# ---------------------------------------------------------------- camps for a dungeon that has none
# (the user, 2026-10-30: "make the interiors and dungeons feel more realistic than hollow shells". The game's
# bandits' caves: 85% have camps, two a place, a bedroll each with a log, a guar-hide screen, torch posts, a stool and
# a fire pit, about 200 units across; 0.8 bedrolls a bandit, lab jcamp0)
CAMP_LINK = 420                 # anchors this near each other are one camp
CAMP_NEAR = 160                 # furniture this near a camp's anchor is the camp's
CAMP_APART = 380                # camps laid this far apart at least
DOOR_CLEAR = 220                # and this far from a door
CAMP_KINDS = ('bedroll', 'bed', 'fire', 'table')


STAIR_ROUND = 0.75              # (and within this share of a tile of a flight's own footprint)
STAIR_CLEAR = 150               # nothing is laid on the floor this near a stair's foot or head
DOOR_FLOOR = 110                # ... or a door's floor
BODY_MIN = 14                   # (a thing this big across at least is kept out of walls: a coin's box is nothing)
BODY_IN = 0.7                   # (a wall nearer its middle than this share of its half width cuts into it)
LEAN_REACH = 60                 # (a tilted thing this near its anchor leans on it)


def _keep_clear(db, cell, m):
    """The floor a made home keeps clear of loose things: ([(x0, y0, x1, y1, z)] along the ways between its doors and
    stairs, [(x, y, z, r)] round each stair's foot and head and each door's floor). Interiors only; nothing where the
    place has no rooms to read."""
    if not cell or cell.startswith('#'):
        return [], [], []
    try:
        import furnish
        import walkroom
        info = furnish.rooms(db, cell)
        fl = walkroom.Floor(info)
        if not fl.cells:
            return [], [], []
        discs = []
        for o in walkroom.openings(fl, m['refs']):
            pts = [fl.cells[nd] for nd in (o[1] if isinstance(o[1], (list, tuple, set, frozenset)) else [o[1]]) if nd in fl.cells]
            if not pts:
                continue
            x, y, z = (sum(p_[k] for p_ in pts) / len(pts) for k in range(3))
            discs.append((x, y, z, STAIR_CLEAR if o[0].startswith('stair') else DOOR_FLOOR))
        # (and the floor round a flight, the tile before its foot and its head whichever way it runs: the roof stair's
        # ends are read a little off, and a crate stood 190 before its foot, "in the middle of the stair landing")
        T = info.get('tile') or 256
        round_ = []
        for r in m['refs']:
            if r.get('b') and r['type'] in ('STAT', 'ACTI') and walkroom.STAIR.search(r['id'].lower()):
                f = walkroom._fp(r)
                if f[5] - f[4] >= 100:
                    g = T * STAIR_ROUND
                    round_.append((f[0] - g, f[1] - g, f[2] + g, f[3] + g, f[4] - 40, f[5] + 40))
        return list(walkroom.clearings(info, m['refs'])), discs, round_
    except Exception as e:
        print('lived in, the ways:', cell, e)
        return [], [], []


def _in_clear(clear, x, y, z, rad):
    boxes, discs, round_ = clear
    for x0, y0, x1, y1, z0, z1 in round_:
        if z0 <= z <= z1 and x0 < x < x1 and y0 < y < y1:
            return True
    for x0, y0, x1, y1, bz in boxes:
        if abs(bz - z) < 60 and x0 - rad < x < x1 + rad and y0 - rad < y < y1 + rad:
            return True
    for dx, dy, dz, r in discs:
        if abs(dz - z) < 60 and math.hypot(x - dx, y - dy) < r + rad:
            return True
    return False


def _camps_of(db, p, things, band, camps, beds_per, people):
    """The game place's camps, kept whole under 'band|setting' (and 'setting'), in camps; its beds a hostile person
    under band in beds_per."""
    import castsurvey
    import cliffrocks
    an = [(t, anchor_kind(t[1], t[2])) for t in things]
    an = [(t, k) for t, k in an if k in CAMP_KINDS and t[3]]
    groups = []
    for t, k in an:
        hit = [g for g in groups if any(math.hypot(t[4][0] - u[4][0], t[4][1] - u[4][1]) < CAMP_LINK and abs(t[4][2] - u[4][2]) < 200 for u, _k in g)]
        g = [(t, k)]
        for h in hit:
            g += h
            groups.remove(h)
        groups.append(g)
    hostile = 0
    for n in p['npcs']:
        low = n.lower()
        if low not in people:
            ri = db.resolve_id(n)
            people[low] = castsurvey.person(db, ri) if ri is not None else None
        if people[low] and people[low]['fight'] >= castsurvey.HOSTILE:
            hostile += 1
    if band and hostile:
        beds_per[band].append(sum(1 for _t, k in an if k in ('bedroll', 'bed')) / float(hostile))
    furn = [t for t in things if not (_small(t[1], t[2], t[3], t[5], t[6]) or t[2] in ('DOOR', 'NPC_', 'CREA', 'LEVC')
                                      or mapdata.is_architecture(t[2], t[1], t[3]) or cliffrocks.is_rock(t[1]) or 'marker' in t[1])]
    for g in groups:
        if not any(k in ('bedroll', 'bed') for _t, k in g):
            continue
        mem = {id(t) for t, _k in g}
        pieces = [t for t, _k in g] + [t for t in furn if id(t) not in mem and any(
            math.hypot(t[4][0] - u[4][0], t[4][1] - u[4][1]) < CAMP_NEAR and abs(t[4][2] - u[4][2]) < 150 for u, _k in g)]
        cx = sum(t[4][0] for t, _k in g) / len(g)
        cy = sum(t[4][1] for t, _k in g) / len(g)
        floors = sorted(t[4][2] + t[3][2] * t[5] for t, _k in g)
        fz = floors[len(floors) // 2]
        rec = {'beds': sum(1 for _t, k in g if k in ('bedroll', 'bed')), 'band': band, 'set': p['setting'],
               'pieces': [[t[0], round(t[4][0] - cx, 1), round(t[4][1] - cy, 1), round(t[4][2] - fz, 1), round(t[4][3], 3),
                           round(t[4][4], 3), round(t[4][5], 3), round(t[5], 2), 1 if anchor_kind(t[1], t[2]) else 0] for t in pieces]}
        if len(rec['pieces']) > 40:
            continue                          # (a whole barracks, not a camp)
        camps[(band or '-') + '|' + p['setting']].append(rec)


# ---------------------------------------------------------------- stories: what happened here
# (the user, 2026-10-30: "implement worldbuilding storytelling". The game's own: a cave's fallen adventurer, a skeleton
# with its sword, armour and gold; a tomb's dead among ash urns, prayer stools and braziers; a Dwemer ruin's skull by
# its history books and coins; a Dreugh altar's offerings of gold and pearls. Remains in 92% of tombs, half the caves,
# lab jstory0)
STORY_ANCH = [('remains', re.compile(r'corpse|skeleton|skull|bonepile|bone_pile|_bones|furn_bone|remains|^dead_|_dead_|_dead$')),
              ('altar', re.compile(r'altar|shrine|_offering|dae_statue|daedric_statue|ritual'))]
STORY_LINK = 250                # remains or altars this near each other tell one story
STORY_NEAR = 200                # what lies this near them is the story's
STORY_SKIP = re.compile(r'^sound|mist|collision|marker|flora|web')
STORY_MAX = {'fallen': 2, 'offering': 1, 'bones': 2}
HUNG = 70                       # a story's thing whose bottom is this far over the floor hangs (left out)


def story_anchor(low, tag, b):
    """'remains', 'altar' or None, for a thing that a story is told round."""
    if tag not in ('CONT', 'STAT', 'ACTI', 'NPC_', 'MISC', 'LIGH') or mapdata.is_architecture(tag, low, b):
        return None
    for k, rx in STORY_ANCH:
        if rx.search(low):
            return k
    return None


def _stories_of(db, p, things, band, stories, story_n):
    """The game place's stories, kept whole under 'kind|setting' in stories (kind: 'offering' round an altar, 'fallen'
    where remains lie with gear, notes or gold, else 'bones'); how many of each it tells in story_n."""
    an = [(t, story_anchor(t[1], t[2], t[3])) for t in things]
    an = [(t, k) for t, k in an if k and t[3]]
    groups = []
    for t, k in an:
        hit = [g for g in groups if any(math.hypot(t[4][0] - u[4][0], t[4][1] - u[4][1]) < STORY_LINK and abs(t[4][2] - u[4][2]) < 150 for u, _k in g)]
        g = [(t, k)]
        for h in hit:
            g += h
            groups.remove(h)
        groups.append(g)
    n = Counter()
    for g in groups:
        mem = {id(t) for t, _k in g}
        near = [t for t in things if id(t) not in mem and t[3] and not t[6] and not STORY_SKIP.search(t[1])
                and t[2] not in ('NPC_', 'CREA', 'LEVC', 'DOOR') and not mapdata.is_architecture(t[2], t[1], t[3])
                and not re.search(r'^key_|_key$|_key_', t[1])
                and any(math.hypot(t[4][0] - u[4][0], t[4][1] - u[4][1]) < STORY_NEAR and abs(t[4][2] - u[4][2]) < 150 for u, _k in g)]
        floors = sorted(t[4][2] + t[3][2] * t[5] for t, _k in g)
        fz = floors[len(floors) // 2]
        # (not what hangs on a wall or from the roof: laid on open floor it floated, hooks over a cult's bones, lab jstory1)
        pieces = [t for t, _k in g if not t[6]] + [t for t in near if t[4][2] + t[3][2] * t[5] - fz < HUNG]
        if not pieces or len(pieces) > 40:
            continue
        kinds = {k for _t, k in g}
        tags = {t[2] for t in near}
        kind = 'offering' if 'altar' in kinds else 'fallen' if (tags & {'WEAP', 'ARMO', 'BOOK', 'CLOT'} or any('gold' in t[1] or 'corpse' in t[1] for t in pieces)) else 'bones'
        n[kind] += 1
        cx = sum(t[4][0] for t, _k in g) / len(g)
        cy = sum(t[4][1] for t, _k in g) / len(g)
        stories[kind + '|' + p['setting']].append({'kind': kind, 'band': band, 'set': p['setting'],
            'pieces': [[t[0], round(t[4][0] - cx, 1), round(t[4][1] - cy, 1), round(t[4][2] - fz, 1), round(t[4][3], 3), round(t[4][4], 3),
                        round(t[4][5], 3), round(t[5], 2), 1 if id(t) in mem else 0] for t in pieces]})
    for kind in ('fallen', 'offering', 'bones'):
        story_n[kind + '|' + p['setting']].append(n[kind])


def tell_stories(db, cell, band='', seed=None, m=None):
    """The game's own stories for a dungeon that tells too few: as many of each kind (a fallen adventurer, an
    offering, bones) as the game's places of its kind tell, from places of its kind (and the band's first), laid whole
    on clear floor. No Undo step of its own. {'stories', 'pieces'}."""
    L = learn(db)
    S, N = L.get('stories') or {}, L.get('story_n') or {}
    rng = random.Random((int(seed) if seed is not None else random.randrange(1, 1 << 30)) + 31)
    m = m or mapdata.cellmap(db, cell)
    setting = _setting_of(db, m)
    have = Counter()
    for r in m['refs']:
        k = story_anchor(r['id'].lower(), r['type'], r.get('b'))
        if k:
            have[k] += 1
    if sum(have.values()) >= 3:
        return {'stories': 0, 'pieces': 0}
    F = _Fitter(db, cell, m, apart=300)
    if not F.rooms:
        return {'stories': 0, 'pieces': 0}
    told, made = 0, 0
    for kind in ('fallen', 'offering', 'bones'):
        mean = N.get(kind + '|' + setting)
        if mean is None:
            continue
        want = min(STORY_MAX[kind], int(mean) + (1 if rng.random() < mean - int(mean) else 0))
        pool = S.get(kind + '|' + setting) or []
        if band:
            pool = [x for x in pool if x['band'] == band] or pool
        for _i in range(want):
            if not pool:
                break
            lay = F.fit(rng.choice(pool)['pieces'], rng)
            if lay:
                made += len(F.put(lay))
                told += 1
    if made:
        db.sync_project()
    return {'stories': told, 'pieces': made}


def _camp_pool(L, band, setting):
    """The camps to choose from: the band's in such a place, the band's anywhere, such a place's, any dungeon's."""
    C = L.get('camps') or {}
    for want in ((band + '|' + setting) if band else None, band and [k for k in C if k.startswith(band + '|')],
                 ['-|' + setting] if setting else None, list(C)):
        if not want:
            continue
        keys = [want] if isinstance(want, str) else want
        pool = [c for k in keys for c in C.get(k) or []]
        # (the fuller camps, a bedroll with its fire, log, stool or screen, when there are enough of them: a lone
        # bedroll in a side room is a camp in the game's count too, and laid alone it made a bare dungeon no less bare)
        full = [c for c in pool if len(c['pieces']) >= 3]
        if len(full) >= 4:
            return full
        if len(pool) >= 4:
            return pool
    return []


def lay_camps(db, cell, band='', people=None, seed=None, m=None):
    """Camps for a dungeon with too few beds for who lives there: the game's own camps of the band (or the kind of
    place), laid whole on clear floor, turned to fit, apart from each other and from the doors. people: how many
    live there (else the hostile people in it, at least 2). No Undo step of its own. {'camps', 'pieces', 'anchors':
    the new beds', fires' and tables' ref keys}."""
    import editing
    import dwemer
    import cliffrocks
    import castsurvey
    from project import set_ref_pos, zs
    L = learn(db)
    rng = random.Random(int(seed) if seed is not None else random.randrange(1, 1 << 30))
    m = m or mapdata.cellmap(db, cell)
    setting = _setting_of(db, m)
    info = _Info(db)
    if people is None:
        people = 0
        for r in m['refs']:
            if r['type'] == 'NPC_' and r.get('ri') is not None:
                o = castsurvey.person(db, r['ri'])
                people += bool(o and o['fight'] >= castsurvey.HOSTILE)
    people = max(2, int(people))
    want_beds = max(1, int(round(people * float((L.get('beds_per') or {}).get(band, 0.8)))))
    have = sum(1 for r in m['refs'] if anchor_kind(r['id'].lower(), r['type']) in ('bedroll', 'bed'))
    if have >= want_beds:
        return {'camps': 0, 'pieces': 0, 'anchors': []}
    pool = _camp_pool(L, band, setting)
    if not pool:
        return {'camps': 0, 'pieces': 0, 'anchors': []}
    F = _Fitter(db, cell, m)
    if not F.rooms:
        return {'camps': 0, 'pieces': 0, 'anchors': []}
    made_camps, made, anchors = 0, 0, []
    tries = 0
    while have < want_beds and made_camps < 6 and tries < 6:
        tries += 1
        lay = F.fit(rng.choice(pool)['pieces'], rng)
        if not lay:
            continue
        made_camps += 1
        for rk, low, tag, anc in F.put(lay):
            made += 1
            if anc:
                anchors.append(rk)
                if anchor_kind(low, tag) in ('bedroll', 'bed'):
                    have += 1
    if made:
        db.sync_project()
    return {'camps': made_camps, 'pieces': made, 'anchors': anchors, 'beds_wanted': want_beds, 'why': dict(F.why)}


class _Fitter:
    """Laying a whole layout of the game's (a camp, a story) on a place's clear floor: away from the walls, the doors,
    what stands there and what was laid before, turned to fit. pieces: [[id, dx, dy, dz over the floor, rx, ry, rz, s,
    anchor]], round the layout's middle; a piece that can't stand is left out, unless it is an anchor."""
    def __init__(self, db, cell, m, apart=CAMP_APART):
        import dwemer
        import cliffrocks
        import editing
        self.db, self.cell, self.apart = db, cell, apart
        self.sc = dwemer._thing_scene(db, m['refs'])
        self.feet = cliffrocks._Feet()
        for r in m['refs']:
            if r['type'] in ('NPC_', 'CREA', 'LEVC') or r.get('arch') or not r.get('b'):
                continue
            self.feet.add(r['p'][0], r['p'][1], r['p'][5], r['s'] or 1.0, r['b'])
        self.doors = [r['p'] for r in m['refs'] if r['type'] == 'DOOR']
        try:
            import furnish
            self.rooms = [rm for rm in furnish.rooms(db, cell)['rooms'] if rm['x_max'] - rm['x_min'] > 200 and rm['y_max'] - rm['y_min'] > 200]
        except Exception:
            self.rooms = []
        self.centres, self.why, self.bounds = [], Counter(), {}
        self.c_ = editing._cell(db, cell)[0]

    def floor(self, x, y, z):
        h = self.sc.nearest_any((x, y, z + 80.0), (0.0, 0.0, -1.0), 260.0)
        return None if h is None else z + 80.0 - h[0]

    def fit(self, pieces, rng, tries=80):
        """The best spot and turn for the layout: [(id, x, y, z, rx, ry, rz, s, anchor)], or None."""
        sc, why, best = self.sc, self.why, None
        for _t in range(tries):
            rm = rng.choice(self.rooms)
            x0 = rng.uniform(rm['x_min'] + 100, rm['x_max'] - 100)
            y0 = rng.uniform(rm['y_min'] + 100, rm['y_max'] - 100)
            if any(math.hypot(x0 - a, y0 - b) < self.apart for a, b in self.centres) or any(math.hypot(x0 - d[0], y0 - d[1]) < DOOR_CLEAR for d in self.doors):
                why['near a camp or door'] += 1
                continue
            f0 = self.floor(x0, y0, rm['floor'])
            if f0 is None or abs(f0 - rm['floor']) > 40:
                why['no floor'] += 1
                continue
            turn = rng.random() * 2 * math.pi
            c, sn = math.cos(turn), math.sin(turn)
            ok, lay = True, []
            for pc in pieces:
                rid, dx, dy, dz, rx, ry, rz, s, anc = pc
                x, y = x0 + c * dx - sn * dy, y0 + sn * dx + c * dy
                fz = self.floor(x, y, f0)
                d = math.hypot(x - x0, y - y0)
                blocked = False
                if d > 20:
                    blocked = sc.nearest_any((x0, y0, f0 + 30.0), ((x - x0) / d, (y - y0) / d, 0.0), d + 20) is not None
                up = sc.nearest_any((x, y, (fz or f0) + 10.0), (0.0, 0.0, 1.0), 110.0)
                if fz is None or abs(fz - f0) > 36 or blocked or up is not None or self.feet.under(x, y):
                    why['piece: ' + ('no floor' if fz is None or abs(fz - f0) > 36 else 'wall' if blocked else 'low roof' if up is not None else 'taken')] += 1
                    if anc:
                        ok = False
                        break
                    continue
                lay.append((rid, x, y, fz + dz, rx, ry, (rz + turn) % (2 * math.pi), s, anc))
            if ok and lay and (best is None or len(lay) > len(best[1])):
                best = ((x0, y0), lay)
                if len(lay) == len(pieces):
                    break
        if not best:
            return None
        self.centres.append(best[0])
        return best[1]

    def put(self, lay):
        """The layout into the place (no Undo step): [(ref key, id lower, record type, anchor)]."""
        import editing
        from project import set_ref_pos, zs
        db = self.db
        mine = db.project.plugin.lower()
        out = []
        for rid, x, y, z, rx, ry, rz, s, anc in lay:
            ri = db.resolve_id(rid)
            if ri is None:
                continue
            rk = db.project.new_ref_key()
            editing._store(self.c_, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], (x, y, z, rx, ry, rz), s))
            low = rid.lower()
            if low not in self.bounds:
                self.bounds[low] = mapdata.object_bounds(db, ri)
            if self.bounds[low]:
                self.feet.add(x, y, rz, s, self.bounds[low])
            out.append((rk, low, db.recs[ri][0], anc))
        return out


def _setting_of(db, m):
    """The kind of place it is, as castsurvey files the game's (cave, house, camp ...), or ''."""
    try:
        import castsurvey
        ids = [r['id'] for r in m['refs']]
        key = m.get('key') or ''
        return castsurvey.setting_of(db, m.get('name') or key, ids, key.startswith('#'), '')[0]
    except Exception:
        return ''
