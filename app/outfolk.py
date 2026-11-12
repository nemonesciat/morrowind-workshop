"""People on the roads, beasts in the wild (docs/worldbuilding-next-2026-11.md, proposal 3): travellers by the roads,
campers at the camps, and the land's and the water's creatures, for the marked cells, as many as the game has.

What the game has outside its towns (lab a22, 2026-11-08, VV + TR outside the towns' cells: 1,302 people and 13,315
creatures and creature lists, the roads as a12 reads them), a hundred land cells: 51 people, 6.2 within 512 of a road
(guards, barbarians, warriors, rogues, agents, commoners, traders, merchants, scouts), 7.6 at a camp (about two a
camp: barbarians, scouts, hunters, rogues, warriors, archers; Ashlanders on Dunmer land), 17 by a door (the places'
own people) and 20 elsewhere (mostly a plantation's slaves and guards); most alone, three at most (p90). Creatures:
3.8 a land cell and 2.9 a water cell, one at a time (nearest neighbour 2,131 at the median), hardly any near a town
(0.02 times as often within 2,048 of one, 0.18 within 4,096), more on low ground, by the shore and on the flat.

Who: the classes the game stands there (ROAD, CAMP), each person made as Populate makes one (populate.person) in
the place's region's outdoor cast (its races and factions: Imperials and the Kingdom of Anvil on the Gold Coast);
the creatures and creature lists of the region's own outdoor cast, else of the region nearest in weather that has
some, the ones that swim in the water. One change, one Undo."""
import math
import random
import re
from collections import Counter

import mapdata

ROAD_RATE = 6.19                # (people a hundred land cells within 512 of a road)
ROAD = [['Guard', 22], ['Barbarian', 18], ['Warrior', 10], ['Rogue', 8], ['Agent', 7], ['Commoner', 7], ['Trader', 5],
        ['Merchant', 5], ['Scout', 5], ['Herder', 4], ['Noble', 4], ['Nightblade', 4], ['Witchhunter', 3], ['Pilgrim', 3]]
CAMP = [['Barbarian', 19], ['Scout', 18], ['Hunter', 18], ['Rogue', 18], ['Warrior', 15], ['Mabrigash', 13], ['Archer', 11],
        ['Wise Woman', 8], ['Smuggler', 8], ['Thief', 6], ['Sharpshooter', 6], ['Commoner', 5], ['Mage', 4], ['Assassin', 4]]
ASHLANDER = ('Mabrigash', 'Wise Woman')
# (who keeps company: a camp's people and a road's group are of one kind, guards with guards)
KIN = {'outlaw': ('Barbarian', 'Rogue', 'Thief', 'Smuggler', 'Warrior', 'Archer', 'Sharpshooter', 'Assassin', 'Nightblade', 'Agent'),
       'hunter': ('Hunter', 'Scout', 'Archer'), 'ashlander': ASHLANDER, 'guard': ('Guard',),
       'trader': ('Trader', 'Merchant', 'Commoner', 'Noble', 'Pilgrim', 'Herder', 'Witchhunter')}
ROAD_GROUP = [[1, 60], [2, 25], [3, 15]]
CAMP_GROUP = [[1, 30], [2, 45], [3, 25]]
BESIDE = (180.0, 420.0)         # (a traveller this far from the road's line: by it, off its bed)
LAND_RATE = 3.79                # (creatures a land cell)
WATER_RATE = 2.86               # (creatures a water cell)
# (the land creatures' lifts by band: height, slope, the sea's distance, the nearest settlement's)
BINS = {'z': [0, 100, 300, 700, 1500, 3000, 6000, 1e9], 'slope': [0, 5, 10, 15, 20, 30, 40, 91], 'coast': [0, 1100, 2100, 4200, 8300, 16500, 1e9],
        'town': [0, 2048, 4096, 8192, 16384, 32768, 1e9]}
LIFT = {"z": [2.177, 1.483, 1.0, 0.905, 0.852, 0.928, 1.008], "slope": [1.341, 1.462, 1.479, 1.259, 0.919, 0.533, 0.384],
        "coast": [1.647, 1.029, 0.874, 0.841, 0.861, 1.064], "town": [0.017, 0.18, 0.638, 1.014, 1.078, 1.181]}
STEP = 512.0                    # (the ground read every 512, as placeplan reads it)
BUCKET = 32768.0               # (the town lift's last band begins at 32,768)
APART = 400.0                   # (creatures no nearer each other: the game's tenth percentile, 438)
DEEP = 120.0                    # (water this deep at least for a swimmer)
SWIMS = re.compile(r'h2o|fish|longfin|dreugh|mudcrab_?water|_eel|lurker|water\+|water-|water$|slaugh', re.I)
NOT_WILD = re.compile(r'dead|corpse|summon|_unique|quest|_stat_birds|seagull', re.I)


def _w(rng, pairs):
    tot = sum(n for _k, n in pairs)
    if tot <= 0:
        return None
    t = rng.random() * tot
    for k, n in pairs:
        t -= n
        if t <= 0:
            return k
    return pairs[-1][0]


def _band(v, edges):
    for i in range(len(edges) - 1):
        if v < edges[i + 1]:
            return i
    return len(edges) - 2


class _Casts:
    """The survey's outdoor casts by region: a region's own, else the nearest in weather with what is asked for."""

    def __init__(self, db, S):
        import landregion
        self.db, self.S, self.lr = db, S, landregion
        self.by = {k.split('|', 1)[1].lower(): v for k, v in S['casts'].items() if k.startswith('outdoors|')}
        self.memo = {}
        # (the regions whose land was made by hand, and every region by its name in small letters)
        try:
            self.hand = {k.lower() for k in landregion.handmade(db)}
            self.names = {k.lower(): k for k in landregion._survey(db)}
        except Exception as e:
            print('out folk, regions:', e)
            self.hand, self.names = set(), {}
        self.src = {}

    def source(self, r):
        """The region whose cast a region takes (small letters): its own where its land is hand-made; a heightmap
        region's, the hand-made region its plants come from (landregion.plant_region). Tamriel.esm stands the same
        stand-in animals over the whole continent, Solstheim's wolves and bears, Skyrim's goats, Cyrodiil's goblins,
        and Shipal-Shin's canyons were given all of them; practice 2, 2026-11-11."""
        if r not in self.src:
            out = r
            if r and self.hand and r not in self.hand:
                try:
                    pr = self.lr.plant_region(self.db, self.names.get(r, r))
                    if pr and pr.lower() in self.hand:
                        out = pr.lower()
                except Exception as e:
                    print('out folk, source region:', e)
            self.src[r] = out
        return self.src[r]

    def get(self, region, need, tag=''):
        key = (region, tag or id(need))
        if key in self.memo:
            return self.memo[key]
        r = self.source((region or '').lower())
        own = self.by.get(r) or self.by.get(r + ' region')
        if own and need(own):
            self.memo[key] = own
            return own
        mine = self.lr._weather(self.db, r) if r else None
        best = None
        for k, C in self.by.items():
            if not need(C):
                continue
            w = self.lr._weather(self.db, k)
            d = sum(abs(a - b) for a, b in zip(mine, w)) if (mine and w) else 9.0
            if best is None or d < best[0]:
                best = (d, C)
        self.memo[key] = best[1] if best else (self.S['casts'].get('outdoors') or {})
        return self.memo[key]


def _creature_pool(db, C, wet):
    out = []
    for cid, n in C.get('creatures') or []:
        if n < 3 or NOT_WILD.search(cid):
            continue
        ri = db.resolve_id(cid)
        if ri is None or db.recs[ri][0] not in ('CREA', 'LEVC'):
            continue
        if bool(SWIMS.search(cid)) == wet:
            out.append([db.recs[ri][1], n])
    return out


def _settlements(towns):
    out = []
    for pts in towns:
        if len(pts) >= 3:
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            out.append((cx, cy, max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)))
    return out


def _seg_d(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def plan(db, cells, roads=(), towns=(), camps=(), seed=1, amount=1.0, culture=''):
    """Who and what for the marked cells: {'people': [{cls, kin, x, y, z, rz, at, region}], 'creatures': [{id, x, y, z,
    rz}], 'land_cells', 'water_cells'}. roads: the road lines; towns: the settlements' outlines (none are put inside
    one); camps: [(x, y)] the camps laid; culture: the land's (Ashlanders camp only on Dunmer land)."""
    import castsurvey
    import landrange
    import placeplan
    rng = random.Random('%s|out folk' % seed)
    keys = sorted({landrange._key(k) for k in cells or []})
    if not keys:
        return {'people': [], 'creatures': [], 'land_cells': 0, 'water_cells': 0}
    S = castsurvey.ready(db) if hasattr(castsurvey, 'ready') else castsurvey.survey(db)
    casts = _Casts(db, S) if S else None
    sett = _settlements(towns)
    # (settlements by squares of BUCKET: a point looks at those in its square and the eight round, the farther ones all
    # past the town lift's last band)
    bucket = {}
    for t_ in sett:
        bucket.setdefault((math.floor(t_[0] / BUCKET), math.floor(t_[1] / BUCKET)), []).append(t_)

    def near_sett(x, y):
        bx, by = math.floor(x / BUCKET), math.floor(y / BUCKET)
        return [t_ for dx in (-1, 0, 1) for dy in (-1, 0, 1) for t_ in bucket.get((bx + dx, by + dy), ())]
    inside = lambda x, y, pad=0.0: any(math.hypot(x - cx, y - cy) < r + pad for cx, cy, r in near_sett(x, y))
    reg = {}

    def region(x, y):
        c = (math.floor(x / 8192.0), math.floor(y / 8192.0))
        if c not in reg:
            reg[c] = landrange._region_of(db, c[0], c[1])
        return reg[c]
    dunmer = placeplan._dunmer(culture) if culture else True
    # ---------- the ground, every STEP of the marked cells
    land, water = [], []
    for gx, gy in keys:
        for i in range(int(8192 / STEP)):
            for j in range(int(8192 / STEP)):
                x, y = gx * 8192.0 + (i + 0.5) * STEP, gy * 8192.0 + (j + 0.5) * STEP
                z = mapdata.terrain_z(db, x, y)
                if z is None:
                    continue
                (land if z > 0 else water).append((x, y, z))
    land_cells = len(land) * STEP * STEP / 8192.0 ** 2
    water_cells = len(water) * STEP * STEP / 8192.0 ** 2
    segs = [(a[0], a[1], b[0], b[1]) for pts in roads for a, b in zip(pts, pts[1:])]
    mine_k = {('%d,%d' % k) for k in keys}
    # (the road's distance on the STEP grid: a walk out from the points along every road)
    from collections import deque
    rdist = {}
    q = deque()
    for ax, ay, bx, by in segs:
        m = max(1, int(math.hypot(bx - ax, by - ay) / (STEP / 2)))
        for j in range(m + 1):
            k = (round((ax + (bx - ax) * j / m) / STEP), round((ay + (by - ay) * j / m) / STEP))
            if k not in rdist:
                rdist[k] = 0.0
                q.append(k)
    grid = {(round(x / STEP), round(y / STEP)) for x, y, _z in land + water}
    while q:
        k = q.popleft()
        if rdist[k] > 2048:
            continue
        for dx, dy, c in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            j = (k[0] + dx, k[1] + dy)
            if j in grid and rdist.get(j, 1e9) > rdist[k] + c * STEP:
                rdist[j] = rdist[k] + c * STEP
                q.append(j)
    near_road = lambda x, y: rdist.get((round(x / STEP), round(y / STEP)), 1e9)
    people = []
    # ---------- travellers by the roads
    want = ROAD_RATE / 100.0 * land_cells * amount
    n = int(want) + (1 if rng.random() < want - int(want) else 0)
    lens = [math.hypot(s[2] - s[0], s[3] - s[1]) for s in segs]
    tot = sum(lens)
    groups = 0
    for _t in range(n * 30):
        if len(people) >= n or not tot:
            break
        t = rng.random() * tot
        for s, ln in zip(segs, lens):
            t -= ln
            if t <= 0:
                break
        f = rng.random()
        ux, uy = (s[2] - s[0]) / (ln or 1), (s[3] - s[1]) / (ln or 1)
        side = rng.choice((-1, 1)) * rng.uniform(*BESIDE)
        x, y = s[0] + (s[2] - s[0]) * f - uy * side, s[1] + (s[3] - s[1]) * f + ux * side
        if '%d,%d' % (math.floor(x / 8192.0), math.floor(y / 8192.0)) not in mine_k:
            continue
        z = mapdata.terrain_z(db, x, y)
        if z is None or z <= 8 or inside(x, y, 512) or min(_seg_d(x, y, *s_) for s_ in segs) < BESIDE[0] * 0.8:
            continue
        if any(math.hypot(x - q['x'], y - q['y']) < 2000 for q in people):
            continue
        first = _w(rng, ROAD)
        kin = next((k for k, cs in KIN.items() if first in cs), 'trader')
        size = _w(rng, ROAD_GROUP)
        face = math.atan2(uy, ux) + (math.pi if rng.random() < 0.5 else 0.0)
        for m in range(size):
            cls = first if m == 0 else (_w(rng, [c for c in ROAD if c[0] in KIN[kin]]) or first)
            a = face + math.pi / 2
            px, py = x + math.cos(a) * 70 * m, y + math.sin(a) * 70 * m
            pz = mapdata.terrain_z(db, px, py) or z
            people.append({'cls': cls, 'kin': kin, 'x': round(px, 1), 'y': round(py, 1), 'z': round(pz, 1),
                           'rz': round((math.pi / 2 - face) % (2 * math.pi), 3), 'at': 'road', 'region': region(px, py), 'group': groups})
        groups += 1
    # ---------- campers at the camps
    camp_pool = [c for c in CAMP if dunmer or c[0] not in ASHLANDER]
    for cx, cy in camps:
        if inside(cx, cy):
            continue
        if amount < 1 and rng.random() > amount:
            continue
        first = _w(rng, camp_pool)
        kin = next((k for k, cs in KIN.items() if first in cs), 'outlaw')
        size = _w(rng, CAMP_GROUP)
        for m in range(size):
            cls = first if m == 0 else (_w(rng, [c for c in camp_pool if c[0] in KIN[kin]]) or first)
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(120, 260)
            px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
            pz = mapdata.terrain_z(db, px, py)
            if pz is None or pz <= 8:
                continue
            people.append({'cls': cls, 'kin': kin, 'x': round(px, 1), 'y': round(py, 1), 'z': round(pz, 1),
                           'rz': round((math.pi / 2 - math.atan2(cy - py, cx - px)) % (2 * math.pi), 3), 'at': 'camp', 'region': region(px, py),
                           'group': groups})
        groups += 1
    # ---------- the creatures
    creatures = []
    pools = {}
    if casts:
        towns_c = [(cx, cy) for cx, cy, _r in sett]
        # (the sea's distance on the STEP grid, for the shore's lift)
        idx = {(round(x / STEP), round(y / STEP)): z for x, y, z in land + water}
        dist = {k: 0.0 for k, z in idx.items() if z <= 0}
        q = deque(dist)
        while q:
            k = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                j = (k[0] + dx, k[1] + dy)
                if j in idx and j not in dist:
                    dist[j] = dist[k] + STEP
                    q.append(j)

        def weight(x, y, z):
            if inside(x, y, 128) or (segs and near_road(x, y) < 400):
                return 0.0
            k = (round(x / STEP), round(y / STEP))
            zs = [idx.get((k[0] + 1, k[1]), z), idx.get((k[0] - 1, k[1]), z), idx.get((k[0], k[1] + 1), z), idx.get((k[0], k[1] - 1), z)]
            sl = math.degrees(math.atan(math.hypot(zs[0] - zs[1], zs[2] - zs[3]) / (2 * STEP)))
            dt = min((math.hypot(x - a, y - b) for a, b, _r in near_sett(x, y)), default=1e9)
            return (LIFT['z'][_band(z, BINS['z'])] * LIFT['slope'][_band(sl, BINS['slope'])] * LIFT['coast'][_band(dist.get(k, 1e9), BINS['coast'])]
                    * LIFT['town'][_band(dt, BINS['town'])])
        for pts, rate, wet in ((land, LAND_RATE, False), (water, WATER_RATE, True)):
            cells_n = len(pts) * STEP * STEP / 8192.0 ** 2
            want = rate * cells_n * amount
            n = int(want) + (1 if rng.random() < want - int(want) else 0)
            if not n or not pts:
                continue
            if wet:
                pts = [p for p in pts if p[2] < -DEEP]
                ws = [1.0] * len(pts)
            else:
                ws = [weight(*p) for p in pts]
            import bisect
            cum, acc = [], 0.0
            for wv in ws:
                acc += wv
                cum.append(acc)
            tot = acc
            if tot <= 0:
                continue
            got = 0
            mine = []
            for _t in range(n * 20):
                if got >= n:
                    break
                p = pts[min(len(pts) - 1, bisect.bisect_left(cum, rng.random() * tot))]
                x, y = p[0] + rng.uniform(-STEP / 2, STEP / 2), p[1] + rng.uniform(-STEP / 2, STEP / 2)
                if any(math.hypot(x - a, y - b) < APART for a, b in mine[-400:]):
                    continue
                rk_ = (region(x, y), wet)
                if rk_ not in pools:
                    C = casts.get(rk_[0], lambda C_: bool(_creature_pool(db, C_, wet)), 'wet' if wet else 'dry')
                    pools[rk_] = _creature_pool(db, C, wet)
                pool = pools[rk_]
                cid = _w(rng, pool)
                if not cid:
                    continue
                g = mapdata.terrain_z(db, x, y)
                if g is None:
                    continue
                z = (g * 0.5 if wet else g + 8)
                mine.append((x, y))
                creatures.append({'id': cid, 'x': round(x, 1), 'y': round(y, 1), 'z': round(z, 1), 'rz': round(rng.uniform(0, 2 * math.pi), 3)})
                got += 1
    return {'people': people, 'creatures': creatures, 'land_cells': round(land_cells, 1), 'water_cells': round(water_cells, 1)}


def build(db, cells, roads=(), towns=(), camps=(), seed=1, amount=1.0, culture=''):
    """plan()'s people made (a new NPC record each, as Populate makes them, in their region's outdoor cast) and placed
    with the creatures, one Undo. {'people', 'creatures', 'records', 'land_cells'}."""
    import castsurvey
    import create
    import editing
    import populate
    from project import set_ref_pos, zs
    editing._require_project(db)
    # (the mod's own towns and castles standing, by their records: the page sends the shapes still drawn, and Keep
    # takes a made place's shape off the map)
    towns = [t for t in towns or ()]
    try:
        import ledger
        for rec in ledger._places(db.project).values():
            if rec.get('kind') in ('town', 'castle') and rec.get('state') != 'making':
                ring = (rec.get('fort') or {}).get('ring') if rec.get('kind') == 'castle' else None
                ol = ring or rec.get('outline')
                if ol and len(ol) >= 3:
                    towns.append([[float(q[0]), float(q[1])] for q in ol])
    except Exception as e:
        print('out folk, standing places:', e)
    P = plan(db, cells, roads, towns, camps, seed, amount, culture)
    S = castsurvey.ready(db) if hasattr(castsurvey, 'ready') else castsurvey.survey(db)
    if not S or not (P['people'] or P['creatures']):
        return {'people': 0, 'creatures': 0, 'records': 0, 'land_cells': P['land_cells']}
    casts = _Casts(db, S)
    rng = random.Random('%s|out folk people' % seed)
    mine = db.project.plugin.lower()
    taken, made = set(), []
    placed = []
    for q in P['people']:
        if q['cls'] not in S['classes'] or db.resolve_id(q['cls']) is None:
            continue
        cast = casts.get(q['region'], lambda C: (C.get('places') or 0) >= 4, 'people')
        p = populate.person(db, S, rng, q['cls'], cast, {}, taken=taken, role=None)
        taken.add(p['name'])
        # (a traveller keeps near the road and a camper by the fire: the game's people out there wander 100 at the median)
        p['wander'] = min(int(p.get('wander') or 0), 256 if q['at'] == 'road' else 160)
        nid = create.suggest_id(db, create._prefix(db), p['name'])
        k = 1
        while db.resolve_id(nid) is not None or any(m[0].lower() == nid.lower() for m in made):
            k += 1
            nid = create.suggest_id(db, create._prefix(db), '%s %d' % (p['name'], k))
        db.project.set_record('NPC_', nid.lower(), 0, populate._npc_record(db, nid, p), created=True)
        made.append((nid, p))
        placed.append((nid, q))
    if made:
        db.sync_project()
    n_people = n_cr = 0
    for rid, q in placed + [(c['id'], c) for c in P['creatures']]:
        key = '#%d,%d' % (math.floor(q['x'] / 8192.0), math.floor(q['y'] / 8192.0))
        try:
            cell, _refs = editing._cell(db, key)
        except editing.EditError:
            continue
        rk = db.project.new_ref_key()
        editing._store(cell, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(rid))], (q['x'], q['y'], q['z'], 0.0, 0.0, q['rz']), 1.0))
        if 'cls' in q:
            n_people += 1
        else:
            n_cr += 1
    said = populate.write_lines(db, made) if made else 0
    db.sync_project()
    editing.commit(db, 'People and beasts: %d %s on the roads and at the camps, %d creature%s' % (
        n_people, 'person' if n_people == 1 else 'people', n_cr, '' if n_cr == 1 else 's'))
    return {'people': n_people, 'creatures': n_cr, 'records': len(made), 'lines': said, 'land_cells': P['land_cells'],
            'kinds': dict(Counter(q['cls'] for _n, q in placed))}
