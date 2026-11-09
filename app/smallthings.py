"""The small things between places (docs/worldbuilding-next-2026-11.md, proposal 4): a camp with its bedroll and fire,
a wreck on the beach, someone's remains, an Ashlander cairn, burial banners, a wayside shrine, a cart left by the road,
a fishing spot. What makes wandering between the towns pay.

What the game has (lab a21, 2026-11-08, VV + TR outside the towns' cells, each kind found by its anchor, anchors of
a kind within LINK one site, and a site with a door near a settlement's camp, not a lone one), a hundred land cells:
7.2 camps, 5.4 cairns, 4.7 remains, 3.1 carts, 1.2 burial banners, 0.55 shrines, 0.47 fishing spots, 0.35 wrecks.
Where (placeplan.SMALL): carts on the roads (median 512 from one), shrines by them (1,954), wrecks on the shore (the
sea within 512, the ground at 150), fishing spots by the water, burial banners high (2,600), camps anywhere.

A scene is a site as it stands: its anchors and what lies within REACH of them that a person leaves or builds there
(no plants, rocks or trees of the land, no doors, no people, nothing with a script but a shrine, no quest things),
in the frame of its first anchor (a wreck's: the way out to the sea). Each thing keeps its height over the ground the
game set it on, or, standing on something (a bowl on a cart), its height over the anchor's. Laid, the scene is turned
to its new frame and each thing set on the new ground the same way. Of a kind's scenes, the one whose ground falls
most like the new spot's is laid, one from the same region first."""
import hashlib
import json
import math
import os
import re

import mapdata

VERSION = 4                     # (2: no architecture, books or enchanted things; '_kept'; 3: scenes on the ground only)
KINDS = [('wreck', re.compile(r'shipwreck|wreck|longboatwrk')),
         ('camp', re.compile(r'bedroll|firepit|fire_pit')),
         ('remains', re.compile(r'^t_glb_var_skeleton|^contain_corpse|furn_bone_skull|skeleton|bonepile')),
         ('cairn', re.compile(r'^terrain_cairn')),
         ('burial', re.compile(r'bannerburial|^furn_burial')),
         ('shrine', re.compile(r'^furn_shrine_.*cure|wayshrine')),
         ('cart', re.compile(r'guarcart|^t_de_set_cart|^furn_cart|_set_wagon')),
         ('fishing', re.compile(r'fishing_pole'))]
KIND_OF = dict(KINDS)
LABEL = {'wreck': 'wreck', 'camp': 'camp', 'remains': 'remains', 'cairn': 'cairn', 'burial': 'burial banners', 'shrine': 'wayside shrine',
         'cart': 'cart', 'fishing': 'fishing spot'}
LINK = 400.0
REACH = {'wreck': 900.0, 'camp': 450.0, 'remains': 300.0, 'cairn': 300.0, 'burial': 350.0, 'shrine': 350.0, 'cart': 350.0, 'fishing': 300.0}
TYPES = {'STAT', 'ACTI', 'CONT', 'LIGH', 'MISC', 'INGR', 'ALCH', 'APPA', 'WEAP', 'ARMO', 'CLOT', 'LOCK', 'PROB', 'REPA'}
# (no books: the game's notes by remains are written for its quests; no architecture: the Dwemer walls, a bridge, a
# town's signposts a site stood by in the game, lab j_small 2026-11-08)
BUILT = re.compile(r'^ex_(?!de_shipwreck|longboatwrk|scrapwood|barnacles|de_oar|ship_plank|de_ship_oar|de_railing)|sign|bridge|wall|block|'
                   r'foundation|platform|pillar|stair|sbase|dock|pier|tower|ruin(?!.*scrap)|_x_(?!.*(cart|wagon|shrine))|fence|gate|'
                   r'^in_|^t_[a-z]+_[a-z]+_i_|_cave_i_|overhang|beam|palisade', re.I)
FLOAT = 300.0                   # (a thing this far over the ground is up on something the scene hasn't: left out)
HUNG_KINDS = ('wreck', 'burial')   # (a wreck's hull lies in the water, burial banners hang from ropes between poles)
LEDGE = 100.0                   # (an anchor this far off the ground is on a ledge, a deck, a roof: not a scene on the ground)
# (the land's own and the game's quest things: plants, rocks, trees, sounds, markers; TR's quest ids tr_mN_, notes, keys)
NOT_THING = re.compile(r'flora|tree|rock|terrain_(?!cairn)|grass|menhir|^sound|marker|mist|kelp|_reed|bush|plant|^ex_.*log_|root|stump|'
                       r'collision|^tr_m\d|_uni(que)?$|_unique|^key_|_key$|_key_|^bk_.*(note|letter)|^t_ingflor|^ingred_.*(_leaf|_root|petal|lily)|kanet|'
                       r'lichen|mushroom|bittergreen|^bm_.*(berry|herb)|chalktally|decal|_float', re.I)
BIG = 1400.0                    # (a thing wider than this is a building, not the scene's; a wreck's hull and the anchors stay)
ON = 40.0                       # (a thing this far over the ground stands on something: kept at its height over the anchor)
MIN_THINGS = 2
FIT_GOOD = 40.0
_mem = {}


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'smallthings_%s_v%d.json' % (_sig(db), VERSION))


def kind_of(low):
    for k, rx in KINDS:
        if rx.search(low):
            return k
    return None


def _sea_way(db, x, y):
    """The way to the lowest ground round (x, y) at 1,024, radians; None off the land."""
    best = None
    for k in range(16):
        a = k * math.pi / 8
        z = mapdata.terrain_z(db, x + math.cos(a) * 1024, y + math.sin(a) * 1024)
        if z is not None and (best is None or z < best[0]):
            best = (z, a)
    return best[1] if best else None


def learn(db, say=None):
    """{kind: [{'region', 'cell', 'phi', 'over' (the anchor over its ground), 'things': [[id, lx, ly, h, rx, ry, rz, s, on_anchor, ground]]}]}: every lone
    site of the game outside the towns, in its frame (lx along its way, ly across; h over the ground, or over the
    anchor's z where on_anchor; ground: the ground's height at the thing against the anchor's). Cached by the load
    order."""
    key = _sig(db)
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
    import livedin
    import townsurvey
    from project import ref_info
    info = livedin._Info(db)
    town = set()
    for t in townsurvey.survey(db)['towns']:
        town.update(tuple(c) for c in t['cells'])
    cells = []
    for (tag, k), lst in db.by_key.items():
        if tag == 'CELL' and k.startswith('#') and any(v not in db.dead for v in lst):
            try:
                gx, gy = (int(v) for v in k[1:].split(','))
            except ValueError:
                continue
            if (gx, gy) not in town:
                cells.append((gx, gy))
    memo = {}

    def refs_of(c):
        if c not in memo:
            out = []
            try:
                refs, _h = db.cell_refs('#%d,%d' % c, without_project=True)
            except Exception:
                refs = {}
            for r in refs.values():
                rid, pos, s, dead = ref_info(r['subs'])[:4]
                if dead or not rid:
                    continue
                out.append((rid, rid.lower(), pos, s or 1.0))
            memo[c] = out
        return memo[c]

    found = {k: [] for k, _rx in KINDS}
    sites = {}
    seen = set()
    for n, c in enumerate(cells):
        if say and n % 2000 == 0:
            say('Reading the game\'s lone places', n / float(len(cells)))
        own = refs_of(c)
        anchors = [(r, kind_of(r[1])) for r in own]
        anchors = [(r, k) for r, k in anchors if k]
        if not anchors:
            if len(memo) > 4000:
                memo.clear()
            continue
        near = [r for dx in (-1, 0, 1) for dy in (-1, 0, 1) for r in refs_of((c[0] + dx, c[1] + dy))]
        for r, k in anchors:
            if (r[1], round(r[2][0]), round(r[2][1])) in seen:
                continue
            # (the site: anchors of the kind within LINK of each other)
            site = [r]
            seen.add((r[1], round(r[2][0]), round(r[2][1])))
            grew = True
            while grew:
                grew = False
                for q in near:
                    qk = (q[1], round(q[2][0]), round(q[2][1]))
                    if qk not in seen and KIND_OF[k].search(q[1]) and any(math.hypot(q[2][0] - a[2][0], q[2][1] - a[2][1]) < LINK for a in site):
                        site.append(q)
                        seen.add(qk)
                        grew = True
            R = REACH[k]
            mem = [q for q in near if any(math.hypot(q[2][0] - a[2][0], q[2][1] - a[2][1]) < R for a in site)]
            # (a camp with a door near is a settlement's (tents, a yurt), not a lone one)
            if any((info(q[0])[0] or '') == 'DOOR' for q in mem) and k == 'camp':
                continue
            keep = []
            for q in mem:
                tag, b, scr = info(q[0])
                is_anchor = KIND_OF[k].search(q[1]) is not None
                if tag not in TYPES or NOT_THING.search(q[1]) or (BUILT.search(q[1]) and not is_anchor) or _enchanted(db, q[0], tag):
                    continue
                if scr and not (is_anchor and k == 'shrine'):
                    continue
                if b and not is_anchor and max(b[3] - b[0], b[4] - b[1]) * q[3] > BIG:
                    continue
                keep.append(q)
            sites[k] = sites.get(k, 0) + 1
            if len(keep) < MIN_THINGS and k not in ('shrine', 'cart', 'wreck'):
                continue
            a = site[0]
            az = mapdata.terrain_z(db, a[2][0], a[2][1])
            if az is None or az <= 0 and k != 'wreck':
                continue
            if k not in HUNG_KINDS and abs(a[2][2] - az) > LEDGE:
                continue
            phi = _sea_way(db, a[2][0], a[2][1]) if k in ('wreck', 'fishing') else -a[2][5]
            if phi is None:
                continue
            cs, sn = math.cos(-phi), math.sin(-phi)
            rows = []
            for q in keep:
                g = mapdata.terrain_z(db, q[2][0], q[2][1])
                if g is None:
                    g = az
                dx, dy = q[2][0] - a[2][0], q[2][1] - a[2][1]
                lx, ly = dx * cs - dy * sn, dx * sn + dy * cs
                over = q[2][2] - g
                if over > FLOAT and k not in HUNG_KINDS:
                    continue
                on = over > ON and q is not a
                h = q[2][2] - a[2][2] if on else over
                rows.append([q[0], round(lx, 1), round(ly, 1), round(h, 1), round(q[2][3], 4), round(q[2][4], 4),
                             round((-q[2][5] - phi) % (2 * math.pi), 4), round(q[3], 3), 1 if on else 0, round(g - az, 1)])
            ci = mapdata.cell_info(db, '#%d,%d' % c) or {}
            found[k].append({'region': (ci.get('region') or '').lower(), 'cell': '%d,%d' % c, 'phi': round(phi, 4), 'over': round(a[2][2] - az, 1),
                             'things': rows})
    # (how many of each kind's sites were kept: a lone cairn with nothing by it is a rock of the land, not a grave)
    found['_kept'] = {k: round(len(found[k]) / float(n), 3) for k, n in sites.items() if n}
    _mem[key] = found
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(found, f)
    except OSError:
        pass
    return found


_ENCH = {}


def _enchanted(db, rid, tag):
    """Whether a weapon, armour or clothing has an enchantment (an artifact's or a quest's loot, not a passer-by's)."""
    if tag not in ('WEAP', 'ARMO', 'CLOT'):
        return False
    low = rid.lower()
    if low not in _ENCH:
        from esm import iter_subrecords
        ri = db.resolve_id(rid)
        try:
            r = db.recs[ri]
            _ENCH[low] = any(t == 'ENAM' for t, _d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]))
        except Exception:
            _ENCH[low] = False
    return _ENCH[low]


def fit(db, scene, x, y, phi):
    """The mean difference between how the ground falls under the scene's things in the game and at (x, y) turned
    to phi (each against the anchor's); None where a thing falls off the land records."""
    z0 = mapdata.terrain_z(db, x, y)
    if z0 is None:
        return None
    c, s = math.cos(phi), math.sin(phi)
    tot = 0.0
    for row in scene['things']:
        g = mapdata.terrain_z(db, x + row[1] * c - row[2] * s, y + row[1] * s + row[2] * c)
        if g is None:
            return None
        tot += abs((g - z0) - row[9])
    return tot / max(1, len(scene['things']))


def choose(db, kind, x, y, phi, region='', rng=None, tries=12):
    """(scene index, phi, fit) of the kind's scenes for (x, y): those fitting within FIT_GOOD, from the region nearest
    in weather first (a made land's region is seldom one of the game's: by name alone, Dunmer camps were laid on the
    Gold Coast), a random one among the nearest; else the best fitting. phi None: each scene tried at four turns."""
    import landregion
    import random
    rng = rng or random.Random(0)
    S = learn(db).get(kind) or []
    if not S:
        return None
    idx = list(range(len(S)))
    rng.shuffle(idx)
    good, best = [], None
    region = (region or '').lower()
    mine = landregion._weather(db, region) if region else None
    wd = {}

    def near(r):
        if r not in wd:
            w = landregion._weather(db, r) if (mine and r) else None
            wd[r] = 0.0 if r == region else (sum(abs(a - b) for a, b in zip(mine, w)) if (mine and w) else 9.0)
        return wd[r]
    for k in idx[:max(tries, 1) * 3]:
        for ph in ([phi] if phi is not None else [rng.uniform(0, 2 * math.pi) + j * math.pi / 2 for j in range(4)]):
            f = fit(db, S[k], x, y, ph)
            if f is None:
                continue
            if f <= FIT_GOOD:
                good.append((round(near(S[k]['region']), 1), rng.random(), k, ph, f))
            if best is None or f < best[2]:
                best = (k, ph, f)
        if len(good) >= tries:
            break
    if good:
        good.sort()
        g = good[0]
        return g[2], g[3], round(g[4])
    return (best[0], best[1], round(best[2])) if best else None


def lay(db, kind, k, x, y, phi):
    """Scene k of the kind laid at (x, y) turned to phi: [{id, x, y, z, rx, ry, rz, s}] on the ground as it is."""
    S = learn(db)[kind][k]
    c, s = math.cos(phi), math.sin(phi)
    z0 = mapdata.terrain_z(db, x, y)
    if z0 is None:
        return []
    out = []
    for rid, lx, ly, h, rx, ry, rz, sc, on, _g in S['things']:
        wx, wy = x + lx * c - ly * s, y + lx * s + ly * c
        g = mapdata.terrain_z(db, wx, wy)
        if g is None:
            continue
        z = z0 + S.get('over', 0.0) + h if on else g + h
        out.append({'id': rid, 'x': round(wx, 1), 'y': round(wy, 1), 'z': round(z, 1), 'rx': rx, 'ry': ry,
                    'rz': round((-(rz + phi)) % (2 * math.pi), 4), 's': sc})
    return out
