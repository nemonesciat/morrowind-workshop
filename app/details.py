"""The small details (2026-11-14): the fungus on a tree's trunk, the roots at its foot, lichen and barnacles on a
rock, the vines, spores and webs of a cave's walls. The user: "We also need to focus on perfecting smaller details in
the world in general. Things like mushrooms on trees and moss in caves. The little details that fill out the world
between points of interest."

Measured that day (lab det1, det2): outdoors, of the game's fungus, moss, lichen, vines, roots, webs and barnacles,
40% sit on a tree, 26% on a rock, 8% on a building, the rest on the ground. Four in five of one Bitter Coast tree
wear shelf fungus or mushrooms, a third to a half of the West Gash's trees have root pieces at their feet, a fifth to
two fifths of the Othreleth Woods' wear fungus; one rock in ten wears lichen or barnacles. A tree the Workshop lays
is laid alone: none wore anything.

learn(db): from a sample of every region's cells and of the game's caves, for each tree, rock and cave piece model
that anything sits on: instances of it, each with what sat on it in the model's own frame (so it stays on the trunk
however the tree is turned or scaled), the bare ones kept too, so that drawing an instance gives the game's share
of bare ones. Dry land, under the water and indoors are kept apart (barnacles are the wet rocks'). Kept on disk.
dress(): the refs given (what a Make land laid, a made cave's pieces) each given one of its model's instances."""
import hashlib
import json
import math
import os
import random
import re
import threading

import mapdata

VERSION = 2
DETAIL = re.compile(r'fung|mushroom|shroom|moss|lichen|vine|ivy|barnacle|_root|web|hypha|bungler|russula|bracket|coprinus|stoneflower|puffball|toadstool|spore|bloat')
# (what is fixed to its host even at its foot; the rest are plants of the ground when they stand on it: the land's
# growth lays those)
ATTACHED = re.compile(r'fung|moss|lichen|vine|ivy|barnacle|_root|web|bracket')
TREE = re.compile(r'tree|_palm|parasol|sapling|stump|_oak|_pine|_birch|_willow|_elm|trunk')
ROCK = re.compile(r'rock|boulder|cliff|menhir|_crag')
CAVE = re.compile(r'^in_\w*cave|^t_\w+_cave|cavern')
NOT_HOST = re.compile(r'door|sign|light|lamp|banner|rug|marker|sound|mist')
LOOK = 50                       # (cells a region looked over)
CAVES = 320                     # (interiors with cave pieces looked over)
KEEP = 36                       # (instances kept a model and setting, over all the game)
KEEP_REGION = 20                # (... and in one region)
MIN_SEEN = 6                    # (a model seen fewer times than this teaches nothing)
PAD = 24.0
OFF_GROUND = 24.0               # (a thing this far over the ground sits on its host, not on the ground)
_lock = threading.RLock()
_mem = {}


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'details_%s_v%d.json' % (_sig(db), VERSION))


def ready(db):
    return _sig(db) in _mem or os.path.exists(_disk(db))


def warm(db):
    """Learnt in a survey process if it hasn't been (the land map asks when it opens)."""
    if ready(db):
        return
    import background
    background.start("the game's small details", lambda: learn(db), task=('details', 'learn', []))


def host_kind(low, arch=False):
    if DETAIL.search(low) or NOT_HOST.search(low):
        return None
    if TREE.search(low):
        return 'tree'
    if ROCK.search(low):
        return 'rock'
    if CAVE.search(low):
        return 'cave'
    return None


def _mat(rx, ry, rz):
    import seethrough
    return seethrough._matrix(rx, ry, rz)


def _mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _tr(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]


def _euler(M):
    import settle
    return settle._euler(M)


def _where(kind, outdoors, g):
    """The setting a host is filed under: 'i' indoors, 'w' a rock under the water (barnacles are the wet rocks'), 'd'
    dry land and every tree (the fungus on a trunk is the same with the foot in a swamp)."""
    if not outdoors:
        return 'i'
    return 'w' if (kind != 'tree' and g is not None and g < -20) else 'd'


def _keep(a, items, cap, rng):
    """One more instance into a fair sample of at most cap."""
    a['n'] += 1
    if items:
        a['worn'] += 1
    if len(a['sets']) < cap:
        a['sets'].append(items)
    else:
        j = rng.randrange(a['n'])
        if j < cap:
            a['sets'][j] = items


def _scan(db, key, outdoors, acc, region='', rng=None):
    m = mapdata.cellmap(db, key, original=True)
    refs = [r for r in m.get('refs') or () if r['type'] in ('STAT', 'ACTI', 'CONT') and r.get('b')]
    hosts, dets = [], []
    for r in refs:
        low = r['id'].lower()
        if DETAIL.search(low):
            dets.append(r)
        else:
            k = host_kind(low)
            if k:
                hosts.append((r, k))
    if not hosts:
        return
    hat = None
    if outdoors:
        gx, gy = (int(v) for v in key[1:].split(','))
        L = mapdata.land(db, gx, gy)
        if L.get('exists'):
            H = L['h']
            hat = lambda x, y: H[min(64, max(0, int(round((y - gy * 8192.0) / 128.0)))) * 65 + min(64, max(0, int(round((x - gx * 8192.0) / 128.0))))]
    worn, mats = {}, {}
    for d in dets:
        p = d['p']
        g = hat(p[0], p[1]) if hat else None
        low = d['id'].lower()
        up = (p[2] - g) if g is not None else None
        if up is not None and up <= OFF_GROUND and not ATTACHED.search(low):
            continue                            # (a plant of the ground under a tree's crown)
        best = None
        for h, k in hosts:
            hp, b, s = h['p'], h['b'], h.get('s') or 1.0
            if abs(hp[0] - p[0]) > 1600 or abs(hp[1] - p[1]) > 1600:
                continue
            M = mats.get(h['k'])
            if M is None:
                M = mats[h['k']] = _mat(hp[3], hp[4], hp[5])
            dx, dy, dz = p[0] - hp[0], p[1] - hp[1], p[2] - hp[2]
            # (into the host's own frame: its turn's transpose)
            lx = (M[0][0] * dx + M[1][0] * dy + M[2][0] * dz) / s
            ly = (M[0][1] * dx + M[1][1] * dy + M[2][1] * dz) / s
            lz = (M[0][2] * dx + M[1][2] * dy + M[2][2] * dz) / s
            if not (b[0] - PAD <= lx <= b[3] + PAD and b[1] - PAD <= ly <= b[4] + PAD and b[2] - PAD <= lz <= b[5] + PAD):
                continue
            v = ({'tree': 0, 'rock': 1, 'cave': 2}[k], (b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2]))
            if best is None or v < best[0]:
                best = (v, h, (lx, ly, lz), M, s)
        if best is None:
            continue
        _v, h, loc, M, s = best
        R = _mul(_tr(M), _mat(p[3], p[4], p[5]))
        e = _euler(R)
        mode = 'g' if (up is not None and up <= OFF_GROUND) else 'on'
        worn.setdefault(h['k'], []).append([d['id'], round(loc[0], 1), round(loc[1], 1), round(loc[2], 1), round(e[0], 3), round(e[1], 3), round(e[2], 3),
                                            round((d.get('s') or 1.0) / s, 3), mode, round(up, 1) if mode == 'g' else 0])
    rng = rng or random.Random(1)
    for h, k in hosts:
        where = _where(k, outdoors, hat(h['p'][0], h['p'][1]) if (outdoors and hat) else None)
        a = acc.setdefault(h['id'].lower() + '|' + where, {'n': 0, 'worn': 0, 'sets': [], 'by': {}})
        items = (worn.get(h['k']) or [])[:14]
        _keep(a, items, KEEP, rng)
        if region:
            _keep(a['by'].setdefault(region, {'n': 0, 'worn': 0, 'sets': []}), items, KEEP_REGION, rng)


def _learn(db):
    import regions
    import background
    rmap = regions.region_map(db)
    proj = db.project.cells if db.project else {}
    by = {}
    for k, r in rmap.items():
        by.setdefault(r, []).append(k)
    acc = {}
    rng = random.Random(20261114)
    regs = sorted(by)
    for n, reg in enumerate(regs):
        background.progress(n, len(regs) + 40, 'regions')
        for k in sorted(by[reg], key=lambda k: hashlib.md5(k.encode()).hexdigest())[:LOOK]:
            if ('#' + k) not in proj:
                try:
                    _scan(db, '#' + k, True, acc, reg, rng)
                except Exception:
                    continue
    caves = sorted((key for (tag, key) in db.by_key if tag == 'CELL' and not key.startswith('#') and key not in proj
                    and re.search(r'cave|cavern|grotto|mine|hole|lair|den\b|tunnel|barrow|ruin|tomb', key)), key=lambda k: hashlib.md5(k.encode()).hexdigest())
    done = 0
    for key in caves:
        if done >= CAVES:
            break
        try:
            refs = mapdata.cellmap(db, key, original=True).get('refs') or ()
            if sum(1 for r in refs if CAVE.search(r['id'].lower())) < 6:
                continue
            _scan(db, key, False, acc, '', rng)
            done += 1
            background.progress(len(regs) + 40 * done // CAVES, len(regs) + 40, 'caves')
        except Exception:
            continue
    hosts = {}
    for hid, a in acc.items():
        if a['n'] >= MIN_SEEN and a['worn']:
            # (a region where the model is always bare is kept too, with no instances: bare there)
            by = {r: {'n': v['n'], 'worn': round(v['worn'] / v['n'], 3), 'sets': v['sets'] if v['worn'] else []}
                  for r, v in a['by'].items() if v['n'] >= MIN_SEEN}
            hosts[hid] = {'n': a['n'], 'worn': round(a['worn'] / a['n'], 3), 'sets': a['sets'], 'by': by}
    return {'version': VERSION, 'hosts': hosts, 'seen': len(acc)}


def learn(db):
    """{'hosts': {'<model id>|d' (dry land, and every tree), '|w' (a rock under the water) or '|i' (indoors): {'n'
    seen, 'worn' (the share with anything on it), 'sets': [[item]] (a fair sample of its instances over all the game),
    'by': {region: the same for that region alone}}}}; an item: [id, x, y, z (in the host's frame, a unit of its
    scale), rx, ry, rz (its turn in that frame), its scale over the host's, 'on' or 'g' (at the host's foot: set on
    the ground there), its height over the ground]. From disk, or learnt now (half a minute or so, once for a load
    order)."""
    with _lock:
        sig = _sig(db)
        if sig in _mem:
            return _mem[sig]
        path = _disk(db)
        try:
            with open(path, encoding='utf-8') as f:
                got = json.load(f)
            if got.get('version') == VERSION:
                _mem[sig] = got
                return got
        except (OSError, ValueError):
            pass
        got = _learn(db)
        try:
            tmp = path + '.part'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(got, f)
            os.replace(tmp, path)
        except OSError as e:
            print('details: not saved,', e)
        _mem[sig] = got
        return got


def plan(db, cells, seed=1, amount=1.0, only=None, wait=True, regions_for=None):
    """What the hosts among some of the mod's refs get: [{'cell', 'id', 'x', 'y', 'z', 'rx', 'ry', 'rz', 's'}].
    cells: {cell key: the ref keys to dress (None: all the mod's own there)}. only: host kinds ('tree', 'rock',
    'cave'). wait: False gives nothing while the game's details are not learnt yet (and has them learnt meanwhile).
    regions_for(cell key): the regions whose look the cell's things were laid in, the first choice first (default:
    the cell's own): a model is dressed as that region dresses it (the West Gash's trees have roots at their feet
    there and none in the regions that borrow them), as the game does over all where the region never set it.
    A host that wears something already is left as it is."""
    if not wait and not ready(db):
        warm(db)
        return []
    H = learn(db)['hosts']
    rng = random.Random(int(seed) * 7919 + 11)
    out = []
    rmap = None
    wear_ids = {}
    for key in sorted(cells):
        want = cells[key]
        if regions_for:
            looks = [r for r in (regions_for(key) or ()) if r]
        elif key.startswith('#'):
            if rmap is None:
                import regions
                rmap = regions.region_map(db)
            looks = [r for r in (rmap.get(key[1:]),) if r]
        else:
            looks = []
        m = mapdata.cellmap(db, key)
        refs = m.get('refs') or ()
        outdoors = key.startswith('#')
        dets = [r for r in refs if DETAIL.search(r['id'].lower())]
        for h in refs:
            if want is not None and h['k'] not in want:
                continue
            if want is None and not h.get('mine'):
                continue
            low = h['id'].lower()
            k = host_kind(low)
            if not k or (only and k not in only) or not h.get('b'):
                continue
            hp, s = h['p'], h.get('s') or 1.0
            where = _where(k, outdoors, mapdata.terrain_z(db, hp[0], hp[1]) if outdoors else None)
            L = H.get(low + '|' + where)
            if not L:
                continue
            L = next((L['by'][r] for r in looks if r in (L.get('by') or {})), L)
            if not L['sets']:
                continue
            b = h['b']
            M = _mat(hp[3], hp[4], hp[5])
            reach = max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) * s + 64
            worn = False
            wears = wear_ids.get(id(L))
            if wears is None:
                wears = wear_ids[id(L)] = {it[0].lower() for st in L['sets'] for it in st}
            for d in dets:
                if d['id'].lower() not in wears:
                    continue                    # (not a thing this model wears: something else's, standing by)
                dx, dy, dz = d['p'][0] - hp[0], d['p'][1] - hp[1], d['p'][2] - hp[2]
                if abs(dx) > reach or abs(dy) > reach or abs(dz) > reach:
                    continue
                lx = (M[0][0] * dx + M[1][0] * dy + M[2][0] * dz) / s
                ly = (M[0][1] * dx + M[1][1] * dy + M[2][1] * dz) / s
                lz = (M[0][2] * dx + M[1][2] * dy + M[2][2] * dz) / s
                if not (b[0] - PAD <= lx <= b[3] + PAD and b[1] - PAD <= ly <= b[4] + PAD and b[2] - PAD <= lz <= b[5] + PAD):
                    continue
                if outdoors and not ATTACHED.search(d['id'].lower()):
                    gd = mapdata.terrain_z(db, d['p'][0], d['p'][1])
                    if gd is not None and d['p'][2] - gd <= OFF_GROUND:
                        continue                # (a plant of the ground under it is nothing it wears)
                worn = True
                break
            if worn:
                continue                        # (dressed already, by the game's own set or an earlier pass)
            items = rng.choice(L['sets'])
            if not items or (amount < 1.0 and rng.random() >= amount):
                continue
            for rid, lx, ly, lz, rx, ry, rz, sr, mode, up in items:
                x = hp[0] + (M[0][0] * lx + M[0][1] * ly + M[0][2] * lz) * s
                y = hp[1] + (M[1][0] * lx + M[1][1] * ly + M[1][2] * lz) * s
                z = hp[2] + (M[2][0] * lx + M[2][1] * ly + M[2][2] * lz) * s
                if outdoors:
                    g = mapdata.terrain_z(db, x, y)
                    if g is None:
                        continue
                    if mode == 'g':
                        z = g + up
                    elif z < g - 8:
                        continue                # (that side of the host is in the ground here)
                e = _euler(_mul(M, _mat(rx, ry, rz)))
                out.append({'cell': key, 'id': rid, 'x': x, 'y': y, 'z': z, 'rx': e[0], 'ry': e[1], 'rz': e[2], 's': round(sr * s, 3)})
    return out


def place(db, items):
    """The planned details written into the mod's cells (no Undo step of their own). The ref keys set, by cell."""
    import editing
    from project import set_ref_pos, zs
    mine = db.project.plugin.lower()
    made = {}
    memo = {}
    for r in items:
        low = r['id'].lower()
        if low not in memo:
            memo[low] = db.resolve_id(r['id'])
        ri = memo[low]
        if ri is None:
            continue
        try:
            c, _refs = editing._cell(db, r['cell'])
        except editing.EditError:
            continue
        rk = db.project.new_ref_key()
        pos = (r['x'], r['y'], r['z'], r['rx'], r['ry'], r['rz'])
        editing._store(c, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], pos, r['s']))
        made.setdefault(r['cell'], []).append(rk)
    return made


def dress(db, cells, seed=1, amount=1.0, only=None, wait=True, regions_for=None):
    """plan() and place(): {'set': how many, 'keys': {cell: [ref keys]}}."""
    made = place(db, plan(db, cells, seed, amount, only, wait, regions_for))
    return {'set': sum(len(v) for v in made.values()), 'keys': made}
