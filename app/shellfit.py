"""The fittings of a one-piece shell (2026-11-09): the hooks on its walls, the ropes strung under its roof, its posts
and coiled ropes, and what the game hangs from them, read in the game's own places built of that one shell.

The user, 2026-11-09: "Do not neglect the walls and the lighting. Things hanging from the ceiling or from ropes ...
These inhabitants presumably have little space to use, so make their living spaces seem utilized." The game's Dunmer
shacks have their ropes and hooks in 92% of them, 2.8 a tile of 256; ours had none. A shack is one model, so a fitting
is read in the shell's own frame: across the game's shacks of in_de_shack_03 the same hook spots and rope runs come
back, place after place. Only spots that come back in two places or more are kept (never one place's own fittings,
[[no-wholesale-copies]]), and a made shack of that shell gets as many as the game's have, drawn by how often each spot
is used, each with what the game hangs from that kind of fitting (dried fish, a lantern, a bottle on a cord).

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

import mapdata

V = 'v4'
FIT = re.compile(r'shack_hook|furn_hook|rope_hook|_rope_\d|_rope\d|rope1_|coiled_?rope|roped_pole|shack_post|t_com_var_rope|t_com_rope')
HUNG_TAGS = ('INGR', 'MISC', 'LIGH', 'CLOT', 'WEAP', 'APPA', 'ARMO', 'ALCH', 'BOOK')
SPOT = 24.0                 # (a fitting spot's size in the shell's frame: two places' hooks this near are one spot)
MIN_PLACES = 2              # (a spot is kept when the game uses it in this many places of the shell)
HANG_REACH = 36.0           # (a thing this near a fitting across, and 0-110 under its origin, hangs from it)
LIGHT_APART = 260           # (a rope's lantern this far from any other light at least)
VALUE_MAX = 40              # (nothing dearer hangs from a hook in a made home)
NOT_HUNG = re.compile(r'^gold_|key|soulgem|^bk_|scroll|_unique|^t_.*_uni_')    # (lying on a shelf under the hook, not on it)
_cache = {}
_thread = {}


def family(low):
    if 'hook' in low:
        return 'hook'
    if 'coiled' in low:
        return 'coil'
    if 'post' in low or 'pole' in low:
        return 'post'
    return 'rope'


def _disk(db):
    import taste
    return taste.cache_file('shellfit_%s_%s' % (taste.sig(db), V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('how the game fits out its huts and shacks', lambda: survey(db), task=('shellfit', 'survey', []))
    return None


def survey(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache['survey'] = (db.recs, out)
            return out
    except Exception:
        path = None
    out = _survey(db)
    _cache['survey'] = (db.recs, out)
    if path:
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(out, f)
            os.replace(tmp, path)
        except Exception:
            pass
    return out


def _local(shell, p):
    """A point (x, y, z) and turn in the shell's own frame."""
    sx, sy, sz, rz, s = shell['p'][0], shell['p'][1], shell['p'][2], shell['p'][5], shell.get('s') or 1.0
    dx, dy = p[0] - sx, p[1] - sy
    c, sn = math.cos(rz), math.sin(rz)
    # (the inverse of the game's turn: world = origin + R(rz) local, with x' = x c + y s, y' = -x s + y c)
    lx, ly = (dx * c - dy * sn) / s, (dx * sn + dy * c) / s
    return lx, ly, (p[2] - sz) / s, (p[5] - rz) % (2 * math.pi)


def _world(shell, lx, ly, lz, lrz):
    sx, sy, sz, rz, s = shell['p'][0], shell['p'][1], shell['p'][2], shell['p'][5], shell.get('s') or 1.0
    c, sn = math.cos(rz), math.sin(rz)
    x, y = sx + (lx * c + ly * sn) * s, sy + (-lx * sn + ly * c) * s
    return x, y, sz + lz * s, (lrz + rz) % (2 * math.pi)


def one_shell(db, m):
    """The place's one shell (its only architecture of any size), or None."""
    arch = [r for r in m.get('refs') or () if r.get('b') and mapdata.is_architecture(r['type'], r['id'], r['b'])
            and not FIT.search(r['id'].lower())]
    big = [r for r in arch if (r['b'][3] - r['b'][0]) * (r['b'][4] - r['b'][1]) * (r.get('s') or 1.0) ** 2 > 250 * 250]
    return big[0] if len(big) == 1 else None


def _survey(db):
    spots = defaultdict(lambda: defaultdict(list))      # shell -> spot key -> [(cell, id, lx, ly, lz, lrz, s)]
    per_cell = defaultdict(list)                        # shell -> fittings a place
    hung = defaultdict(list)                            # fitting family -> [(id, dx, dy, dz, drz)]
    carry = Counter()
    seen = Counter()
    for (tag, key), _lst in db.by_key.items():
        if tag != 'CELL' or key.startswith('#'):
            continue
        try:
            m = mapdata.cellmap(db, key)
        except Exception:
            continue
        if not m.get('interior') or m.get('own'):
            continue
        sh = one_shell(db, m)
        if sh is None:
            continue
        model = sh['id'].lower()
        fits = [r for r in m['refs'] if r['type'] in ('STAT', 'ACTI') and FIT.search(r['id'].lower())]
        per_cell[model].append(len(fits))
        if not fits:
            continue
        things = [r for r in m['refs'] if r['type'] in HUNG_TAGS]
        for f in fits:
            lx, ly, lz, lrz = _local(sh, f['p'])
            k = '%d,%d,%d,%s' % (round(lx / SPOT), round(ly / SPOT), round(lz / SPOT), family(f['id'].lower()))
            spots[model][k].append((key, f['id'], lx, ly, lz, lrz, f.get('s') or 1.0))
            fam = family(f['id'].lower())
            seen[fam] += 1
            c, sn = math.cos(f['p'][5]), math.sin(f['p'][5])
            got = False
            for t in things:
                dx, dy, dz = t['p'][0] - f['p'][0], t['p'][1] - f['p'][1], t['p'][2] - f['p'][2]
                if math.hypot(dx, dy) <= HANG_REACH and -110 <= dz <= 10 and not NOT_HUNG.search(t['id'].lower()):
                    # (in the fitting's own frame, so a fish on a hook turned to the wall stays on its hook)
                    hung[fam].append((t['id'], dx * c - dy * sn, dx * sn + dy * c, dz, (t['p'][5] - f['p'][5]) % (2 * math.pi), t['p'][3], t['p'][4]))
                    got = True
            carry[fam] += got
    out = {'shells': {}, 'hung': {}, 'carry': {}}
    for model, S in spots.items():
        cells = per_cell[model]
        kept = []
        for k, lst in S.items():
            places = len(set(x[0] for x in lst))
            if places < MIN_PLACES:
                continue
            ids = Counter(x[1] for x in lst)
            n = float(len(lst))
            kept.append({'k': k, 'places': places, 'id': ids.most_common(1)[0][0],
                         'p': [sum(x[i] for x in lst) / n for i in (2, 3, 4)],
                         'rz': math.atan2(sum(math.sin(x[5]) for x in lst), sum(math.cos(x[5]) for x in lst)) % (2 * math.pi),
                         's': sum(x[6] for x in lst) / n})
        if kept:
            cs = sorted(cells)
            out['shells'][model] = {'places': len(cells), 'fits_p50': cs[len(cs) // 2], 'spots': sorted(kept, key=lambda s_: -s_['places'])}
    for fam, lst in hung.items():
        out['hung'][fam] = lst[:400]
        out['carry'][fam] = carry[fam] / float(seen[fam] or 1)
    out['outside'] = _survey_outside(db)
    return out


OUT_MODEL = re.compile(r'^ex_de_shack_0\d$|^ex_de_shack_\d\d$|^t_de_setsh_x_shack|^ex_nord_house_0\d$|^ex_common_house_tall_0\d$')
OUT_REACH = 320             # (what stands this near an outside shack is its own: the next shack's is farther)
OUT_SPOT = 48.0
OUT_NOT = re.compile(r'^ex_|terrain|^in_|road|tree|rock|mtn|landscape|grass|kelp|bush|plant|flora|fern|marker|sound|light_fire|smoke|mist|water|dock|pier|bridge|wall|fence|gate|_sign|banner|^furn_de_ex_tower|collision')


def out_kind(low, tag):
    for k, rx in (('barrel', r'barrel'), ('crate', r'crate|box'), ('sack', r'sack'), ('basket', r'basket'),
                  ('rope', r'rope|hook|_post|pole|net'), ('seat', r'bench|stool|chair'), ('table', r'table'),
                  ('drying', r'fish|drying|_rack|line'), ('wood', r'scrap|plank|wood|log|firewood'), ('pot', r'urn|pot_|jar|_pot')):
        if re.search(rx, low):
            return k
    if tag == 'LIGH':
        return 'light'
    return None


def _survey_outside(db):
    import mapdata as _m
    spots = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(list)
    for (tag, key), _lst in db.by_key.items():
        if tag != 'CELL' or not key.startswith('#'):
            continue
        try:
            m = _m.cellmap(db, key)
        except Exception:
            continue
        if m.get('own'):
            continue
        refs = m.get('refs') or ()
        for sh in refs:
            model = sh['id'].lower()
            if not OUT_MODEL.match(model):
                continue
            n = 0
            for r in refs:
                if r is sh or r['type'] in ('NPC_', 'CREA', 'DOOR', 'LEVC', 'LEVI'):
                    continue
                low = r['id'].lower()
                if OUT_NOT.search(low) or math.hypot(r['p'][0] - sh['p'][0], r['p'][1] - sh['p'][1]) > OUT_REACH:
                    continue
                k = out_kind(low, r['type'])
                if not k:
                    continue
                n += 1
                lx, ly, lz, lrz = _local(sh, r['p'])
                g = _m.terrain_z(db, r['p'][0], r['p'][1])
                up = (r['p'][2] - g) if g is not None else lz
                spots[model]['%d,%d,%s' % (round(lx / OUT_SPOT), round(ly / OUT_SPOT), k)].append(
                    (key + '|' + str(sh['k']), r['id'], lx, ly, lz, lrz, r.get('s') or 1.0, up, r['p'][3], r['p'][4]))
            counts[model].append(n)
    out = {}
    for model, S in spots.items():
        kept = []
        for k, lst in S.items():
            places = len(set(x[0] for x in lst))
            if places < MIN_PLACES:
                continue
            ids = Counter(x[1] for x in lst)
            rid = ids.most_common(1)[0][0]
            mem = [x for x in lst if x[1] == rid] or lst
            nn = float(len(mem))
            kept.append({'places': places, 'id': rid, 'kind': k.rsplit(',', 1)[1],
                         'p': [sum(x[i] for x in mem) / nn for i in (2, 3, 4)],
                         'rz': math.atan2(sum(math.sin(x[5]) for x in mem), sum(math.cos(x[5]) for x in mem)) % (2 * math.pi),
                         's': sum(x[6] for x in mem) / nn, 'up': sorted(x[7] for x in mem)[len(mem) // 2],
                         'tilt': [mem[0][8], mem[0][9]]})
        cs = sorted(counts[model])
        if kept and cs:
            out[model] = {'places': len(cs), 'n_p50': cs[len(cs) // 2], 'n_p75': cs[min(len(cs) - 1, int(len(cs) * 0.75))],
                          'n_p90': cs[min(len(cs) - 1, int(len(cs) * 0.9))], 'spots': sorted(kept, key=lambda s_: -s_['places'])}
    return out


def dress_outside(db, buildings, seed=1, avoid=()):
    """Round each of a town's one-piece buildings (refs: dicts with 'id', 'p', 's'), the things the game sets round
    that model outside, at the spots its own places use (two places at least), as many as its median: ropes and hooks
    on the walls, barrels and baskets by the door, a bench. On the ground where the game's stand on it, at the wall's
    height where they hang. [{'id', 'p', 's'}] to lay; nothing within 40 of what is there (avoid: [(id, p)])."""
    S = ready(db)
    O = (S or {}).get('outside') or {}
    if not O:
        return []
    import mapdata as _m
    rng = random.Random(seed)
    taken = [(p[0], p[1]) for _i, p in avoid]
    out = []
    for b in buildings:
        E = O.get(b['id'].lower())
        if not E or not (E.get('n_p75') or E.get('n_p50')):
            continue
        sh = {'p': b['p'], 's': b.get('s') or 1.0}
        pool = list(E['spots'])
        # (as many as the game's better-kept places of the model, its upper quartile: at its median a shack has one
        # thing by it, and the user asked for living spaces that "seem utilized")
        want = max(E.get('n_p75') or 0, E['n_p50'])
        got = 0
        while pool and got < want:
            sp = pool.pop(rng.choices(range(len(pool)), [s_['places'] for s_ in pool])[0])
            x, y, z, rz = _world(sh, sp['p'][0], sp['p'][1], sp['p'][2], sp['rz'])
            if any(math.hypot(x - tx, y - ty) < 40 for tx, ty in taken):
                continue
            if sp['up'] <= 40:
                g = _m.terrain_z(db, x, y)
                if g is None:
                    continue
                z = g + sp['up']                  # (on the ground there, as the game's stand on theirs)
            out.append({'id': sp['id'], 'p': [x, y, z, sp['tilt'][0], sp['tilt'][1], rz], 's': sp['s']})
            taken.append((x, y))
            got += 1
    return out


def fit_out(db, key, seed=1):
    """A made place of one shell fitted out as the game's of that shell are: as many fittings as the game's places of
    it hold at the median, at the spots they use, each kind of fitting carrying what the game hangs from it as often as
    the game's do. Nothing where furniture stands. The number of things placed (no Undo step of its own)."""
    S = ready(db)
    if not S:
        return 0
    m = mapdata.cellmap(db, key)
    sh = one_shell(db, m)
    if sh is None:
        return 0
    E = S['shells'].get(sh['id'].lower())
    if not E or not E.get('fits_p50'):
        return 0
    if any(FIT.search(r['id'].lower()) for r in m['refs']):
        return 0                                # (fitted out already)
    rng = random.Random(seed)
    import editing
    from project import set_ref_pos, zs
    c_, _r = editing._cell(db, key)
    mine = db.project.plugin.lower()
    boxes = []
    for r in m['refs']:
        if r.get('b') and r['type'] in ('STAT', 'ACTI', 'CONT') and r is not sh and not mapdata.is_architecture(r['type'], r['id'], r['b']):
            s = r.get('s') or 1.0
            b = r['b']
            c, sn = math.cos(r['p'][5]), math.sin(r['p'][5])
            xs = [r['p'][0] + (px * c + py * sn) * s for px in (b[0], b[3]) for py in (b[1], b[4])]
            ys = [r['p'][1] + (-px * sn + py * c) * s for px in (b[0], b[3]) for py in (b[1], b[4])]
            boxes.append((min(xs), min(ys), max(xs), max(ys), r['p'][2] + b[2] * s, r['p'][2] + b[5] * s))
    pool = list(E['spots'])
    want = E['fits_p50']
    placed = 0
    laid = []

    def put(rid, x, y, z, rx, ry, rz, s=1.0):
        ri = db.resolve_id(rid)
        if ri is None:
            return None
        rk = db.project.new_ref_key()
        editing._store(c_, rk, mine, int(rk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(db.recs[ri][1]))], (x, y, z, rx, ry, rz), s))
        c_['refs'][rk]['by'] = 'furnish'
        return rk
    while pool and len(laid) < want:
        w = [s_['places'] for s_ in pool]
        sp = pool.pop(rng.choices(range(len(pool)), w)[0])
        x, y, z, rz = _world(sh, sp['p'][0], sp['p'][1], sp['p'][2], sp['rz'])
        ri = db.resolve_id(sp['id'])
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        s = sp['s'] * (sh.get('s') or 1.0)
        r0 = max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) * s
        lo, hi = z + b[2] * s, z + b[5] * s
        fam = family(sp['id'].lower())
        # (a hook or a rope among furniture: only clear of what stands there, its box over the furniture's tops)
        if any(bx[0] - 8 < x + r0 and x - r0 < bx[2] + 8 and bx[1] - 8 < y + r0 and y - r0 < bx[3] + 8 and lo < bx[5] + 10 and hi > bx[4]
               for bx in boxes):
            continue
        if put(sp['id'], x, y, z, 0.0, 0.0, rz, s):
            placed += 1
            laid.append((fam, x, y, z, rz))
    # what hangs from them (a lantern only where no light hangs near already: the furnisher's own and the ropes'
    # together came to 0.62 lights up high a tile, to the game's 0.26)
    lights = [(r['p'][0], r['p'][1]) for r in m['refs'] if r['type'] == 'LIGH']
    for fam, x, y, z, rz in laid:
        H = S['hung'].get(fam) or []
        if not H or rng.random() > (S['carry'].get(fam) or 0.0):
            continue
        for _try in range(8):
            rid, dx, dy, dz, drz, rx, ry = rng.choice(H)
            ri = db.resolve_id(rid)
            if ri is None:
                continue
            try:
                import shelfsurvey
                if shelfsurvey.value_of(db, rid)[1] > VALUE_MAX:
                    continue
            except Exception:
                pass
            c, sn = math.cos(rz), math.sin(rz)
            hx, hy = x + dx * c + dy * sn, y - dx * sn + dy * c
            if db.recs[ri][0] == 'LIGH':
                if any(math.hypot(hx - lx_, hy - ly_) < LIGHT_APART for lx_, ly_ in lights):
                    continue
                lights.append((hx, hy))
            if put(rid, hx, hy, z + dz, rx, ry, (rz + drz) % (2 * math.pi)):
                placed += 1
            break
    if placed:
        db.sync_project()
    return placed
