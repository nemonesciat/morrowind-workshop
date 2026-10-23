"""How the game furnishes its Redoran manors and small houses (Ald-ruhn's Venim, Llethri, Sarethi, Arobar,
Ramoran and Morvayn manors, the council hall, the Redoran huts and the Tamriel Data Redoran towns): the
hall's planter island (a tree or a mushroom cluster with ferns in a big planter, benches at its sides,
candles on its rim, a lantern above, rugs radiating out), the rugs' cover room by room (a small house's
rugs tile its floor), the hallways' runners and lights, the bed in its bay with a chest at its foot, the
shelves of pots on the curved walls, the kiln hearth with sacks beside it, the gallery's lights, what
stands in the alcoves. Every figure is a rate the furnisher goes by (furnish.py), not a hand-written
claim: the user photographed the manors on 22 October 2026 (packaging/nexus/screenshot-catalogue-3.md)
and the survey checks the catalogue against the data.

The manors' floors are not laid in 256-unit tiles: furnish.rooms traces them (128-unit tiles). The game's
big planters (furn_planter_04, 294 wide), its big rugs (furn_de_rug_big_*) and its trees are "architecture"
to the map reader (any static over 200 x 200), so this survey admits them by name; the other surveys never
saw them, which is why no big rug was ever laid.

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background
the first time."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey
import arrangesurvey
import fixit

V = 'v2'                # (v2: the rugs' scales: the manors' big rugs are the 287-unit furn_de_rug_big_06 scaled 2.2 times)
LIMIT = 140
EXAMPLES = 24
RED = re.compile(r'^in_(redoran|r_l|r_s)')
MANOR = re.compile(r'^in_(redoran_l|r_l)')
# the big statics the map reader calls architecture that are furniture all the same
BIG_OK = re.compile(r'planter|rug|carpet|flora_|_tree|tree_|mushroom|shroom|hearth|kiln|forge|fireplace|stove|oven|practice_mat|railing')
PLANT = re.compile(r'flora_|_plant|fern|shrub|bush|tree|vine|mushroom|shroom|flower|ivy|grass|moss|kanet|anther|lichen')
TREE = re.compile(r'tree|mushroom|shroom')
HEARTH = re.compile(r'furn_redoran_hearth|hearth|kiln|fireplace|stove|oven|forge')
POT = re.compile(r'pot_|_pot|bowl|jug|jar|vase|urn|pitcher|cup|bottle|plate|basket|flask')
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('redoransurvey_%s_%d_%s' % (taste.sig(db), LIMIT, V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    import taste
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('the Redoran manors', lambda: survey(db), task=('redoransurvey', 'survey', []))
    return taste.stale(_cache, key, db.recs, _disk(db))


def survey(db):
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def is_thing(r):
    """A furnishing (not the building, not people): the map reader's non-architecture, and the big
    statics that are furniture all the same (a big rug, a big planter, a tree, a hearth)."""
    if not r.get('b') or r['type'] in ('NPC_', 'CREA', 'DOOR', 'LEVC'):
        return False
    low = r['id'].lower()
    if 'marker' in low:
        return False
    if not r.get('arch'):
        return True
    if low.startswith(('in_', 'ex_')) or kits.kit_prefix(low):
        return False
    return bool(BIG_OK.search(low))


def family(db, r):
    low = r['id'].lower()
    f = arrangesurvey.family(db, r['id'], r['type'])
    if f:
        return f
    if re.search(r'rug|carpet', low):
        return 'rug'
    if 'planter' in low:
        return 'planter'
    if HEARTH.search(low) and r['type'] in ('STAT', 'ACTI'):
        return 'fire'
    if PLANT.search(low) and r['type'] in ('STAT', 'ACTI', 'CONT'):
        return 'plant'
    return None


def _cells(db):
    """The game's Redoran-built interiors: every cell using three or more Redoran kit pieces."""
    keys = Counter()
    for low, cis in db.used_in.items():
        if not RED.match(low):
            continue
        for ci in cis:
            if db.recs[ci][0] == 'CELL':
                keys[db.recs[ci][7]] += 1
    out = []
    for k, n in keys.items():
        if n < 3 or not k or k.startswith('#') or not kits.game_made(db, k):
            continue
        ci = mapdata.cell_info(db, k)
        if ci and ci.get('interior'):
            out.append((n, k))
    out.sort(key=lambda t: (-t[0], t[1]))
    return [k for _n, k in out]


def _new_room():
    return {'rooms': 0, 'tiles': 0.0, 'rugs': 0, 'cover': 0.0, 'rooms_with_rug': 0, 'rugs2': 0, 'lights': 0, 'hung': 0,
            'shelves': 0, 'shelf_things': 0, 'shelf_pots': 0, 'beds': 0, 'bed_chest': 0, 'bed_rug': 0, 'bed_bay': 0,
            'planters': 0, 'big_planters': 0, 'benches': 0, 'rug_ids': Counter(), 'cover_list': []}


def _survey(db):
    import taste
    cells = _cells(db)
    cells = taste.order(cells)[:LIMIT]
    R = defaultdict(_new_room)
    isl = {'halls': 0, 'with': 0, 'planters': 0, 'bench_n': [], 'rim': 0, 'lantern': 0, 'stand': 0, 'rugs_near': [], 'radial': 0, 'rugs_seen': 0,
           'd_mid': [], 'models': Counter(), 'contents': Counter(), 'n_in': [], 'examples': []}
    HW = {'rooms': 0, 'tiles': 0.0, 'lights': 0, 'kinds': Counter(), 'runner': 0, 'rugs': 0, 'benches': 0, 'at_wall': 0}
    HE = {'n': 0, 'ids': Counter(), 'by': Counter(), 'sacks': [], 'kinds_near': Counter()}
    AL = {'nooks': 0, 'holds': Counter()}
    GA = {'halls': 0, 'with': 0, 'n': [], 'kinds': Counter()}
    big_rugs = Counter()
    rug_scales = defaultdict(list)
    seen = 0
    for ck in cells:
        try:
            info = furnish.rooms(db, ck, trace=True)
        except Exception:
            continue
        if not info['rooms']:
            continue
        seen += 1
        T = info['tile']
        refs = [r for r in info['refs'] if is_thing(r)]
        arch = [r for r in info['refs'] if r.get('arch') and r.get('b') and not is_thing(r)]
        doors = [r for r in info['refs'] if r['type'] == 'DOOR' or 'jamb' in r['id'].lower()]
        for r in refs:
            r['_fam'] = family(db, r)
            r['_box'] = fixit._world_box(r)
        cls = 'manor' if any(MANOR.match(a['id'].lower()) for a in arch) else 'small'
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in refs if r['_box'] and rm['x_min'] - 20 <= r['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= r['p'][1] <= rm['y_max'] + 20
                      and fl - 40 <= r['_box'][2] <= fl + 400]
            if not inside:
                continue
            tiles9 = rm['tiles'] * (T / 256.0) ** 2
            counts = Counter(r['_fam'] for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS)
            kind = roomsurvey.room_kind(counts)
            w_, h_ = rm['x_max'] - rm['x_min'], rm['y_max'] - rm['y_min']
            hallway = min(w_, h_) <= 300 and max(w_, h_) >= 3.5 * min(w_, h_)
            rugs = [r for r in inside if r['_fam'] == 'rug' and r['_box'][2] < fl + 40]
            lights = [r for r in inside if r['type'] == 'LIGH']
            planters = [r for r in inside if r['_fam'] == 'planter' and r['_box'][2] < fl + 60]
            shelves = [r for r in inside if r['_fam'] in ('shelf', 'bookshelf', 'cupboard')]
            beds = [r for r in inside if r['_fam'] == 'bed']
            benches = [r for r in inside if r['_fam'] == 'bench']
            fires = [r for r in inside if r['_fam'] == 'fire']
            cover = sum((r['_box'][3] - r['_box'][0]) * (r['_box'][4] - r['_box'][1]) for r in rugs) / float(tiles9 * 256 * 256 or 1)
            A = R['%s|%s' % (cls, kind)]
            A['rooms'] += 1; A['tiles'] += tiles9; A['rugs'] += len(rugs); A['cover'] += min(1.0, cover)
            if rugs:
                A['rooms_with_rug'] += 1
                A['cover_list'].append(min(1.0, cover))
            A['rugs2'] += 1 if len(rugs) >= 2 else 0
            A['lights'] += len(lights)
            A['hung'] += sum(1 for l in lights if l['_box'][2] > fl + 120)
            A['planters'] += len(planters); A['big_planters'] += sum(1 for p in planters if max(p['_box'][3] - p['_box'][0], p['_box'][4] - p['_box'][1]) >= 180)
            A['benches'] += len(benches)
            for r in rugs:
                A['rug_ids'][r['id'].lower()] += 1
                rug_scales[r['id'].lower()].append(round(r.get('s') or 1.0, 2))
                if r.get('arch'):
                    big_rugs[r['id'].lower()] += 1
            for sh in shelves:
                b = sh['_box']
                on = [o for o in inside if o is not sh and b[0] - 8 <= o['p'][0] <= b[3] + 8 and b[1] - 8 <= o['p'][1] <= b[4] + 8 and b[2] <= o['_box'][2] <= b[5] + 40]
                A['shelves'] += 1; A['shelf_things'] += len(on); A['shelf_pots'] += sum(1 for o in on if POT.search(o['id'].lower()))
            for bd in beds:
                tl = min(rm['_tiles'], key=lambda t: abs(t['x'] - bd['p'][0]) + abs(t['y'] - bd['p'][1]))
                walls = sum(1 for s in furnish.STEP if tl['pat'][s] == 'wall')
                A['beds'] += 1
                A['bed_bay'] += 1 if walls >= 2 else 0
                A['bed_chest'] += 1 if any(o['_fam'] == 'chest' and math.hypot(o['p'][0] - bd['p'][0], o['p'][1] - bd['p'][1]) < 220 for o in inside) else 0
                A['bed_rug'] += 1 if any(math.hypot(o['p'][0] - bd['p'][0], o['p'][1] - bd['p'][1]) < 200 for o in rugs) else 0
            # ---- the hearths: the kiln (furn_redoran_hearth) with its sacks and pots
            for f in fires:
                HE['n'] += 1
                HE['ids'][f['id'].lower()] += 1
                near = [o for o in inside if o is not f and math.hypot(o['p'][0] - f['p'][0], o['p'][1] - f['p'][1]) < 220 and o['_box'][2] < fl + 120]
                HE['by'].update(o['_fam'] or ('pot' if POT.search(o['id'].lower()) else o['type'].lower()) for o in near)
                HE['sacks'].append(sum(1 for o in near if o['_fam'] in ('sack', 'urn', 'basket', 'crate', 'barrel')))
            # ---- hallways: the runner and the lights
            if hallway and cls == 'manor':
                HW['rooms'] += 1; HW['tiles'] += tiles9; HW['lights'] += len(lights); HW['rugs'] += len(rugs); HW['benches'] += len(benches)
                HW['kinds'].update(('sconce' if 'sconce' in l['id'].lower() else 'lantern' if 'lantern' in l['id'].lower() else 'candle' if 'candle' in l['id'].lower() else 'lamp') for l in lights)
                HW['at_wall'] += sum(1 for l in lights if min(l['p'][0] - rm['x_min'], rm['x_max'] - l['p'][0], l['p'][1] - rm['y_min'], rm['y_max'] - l['p'][1]) < 90)
                HW['runner'] += 1 if any(max(r['_box'][3] - r['_box'][0], r['_box'][4] - r['_box'][1]) >= 1.6 * min(r['_box'][3] - r['_box'][0], r['_box'][4] - r['_box'][1]) for r in rugs) else 0
            # ---- the alcoves: one-tile nooks of a manor room, what stands in them
            if cls == 'manor' and tiles9 >= 6:
                for t in rm['_tiles']:
                    walls_t = [s for s in furnish.STEP if t['pat'][s] == 'wall']
                    if len(walls_t) != 3:
                        continue
                    AL['nooks'] += 1
                    held = [o for o in inside if abs(o['p'][0] - t['x']) <= T * 0.6 and abs(o['p'][1] - t['y']) <= T * 0.6 and o['_fam'] in ('bench', 'chest', 'planter', 'table', 'chair', 'urn', 'crate', 'bed', 'shelf', 'bookshelf')]
                    door_ = any(abs(d['p'][0] - t['x']) <= T * 0.7 and abs(d['p'][1] - t['y']) <= T * 0.7 and abs(d['p'][2] - fl) < 100 for d in doors)
                    AL['holds'][held[0]['_fam'] if held else ('door' if door_ else 'nothing')] += 1
            # ---- the hall: the planter island, the gallery's lights
            if cls == 'manor' and tiles9 >= 12:
                isl['halls'] += 1
                GA['halls'] += 1
                gal = [l for l in lights if fl + 300 <= l['_box'][2] <= fl + 720 and min(l['p'][0] - rm['x_min'], rm['x_max'] - l['p'][0], l['p'][1] - rm['y_min'], rm['y_max'] - l['p'][1]) > 60]
                if gal:
                    GA['with'] += 1
                    GA['n'].append(len(gal))
                    GA['kinds'].update(('candle' if 'candle' in l['id'].lower() else 'lantern' if 'lantern' in l['id'].lower() else 'other') for l in gal)
                bigs = [p for p in planters if max(p['_box'][3] - p['_box'][0], p['_box'][4] - p['_box'][1]) >= 180]
                if bigs:
                    isl['with'] += 1
                for p in bigs:
                    b = p['_box']
                    w = max(b[3] - b[0], b[4] - b[1])
                    cont = [o for o in inside if o is not p and o['_fam'] == 'plant' and b[0] - 16 <= o['p'][0] <= b[3] + 16 and b[1] - 16 <= o['p'][1] <= b[4] + 16 and b[2] - 30 <= o['_box'][2] <= b[5] + 160]
                    bn = [o for o in benches if math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < w / 2 + 220]
                    rim = [o for o in lights if 'sconce' not in o['id'].lower() and b[0] - 30 <= o['p'][0] <= b[3] + 30 and b[1] - 30 <= o['p'][1] <= b[4] + 30 and b[5] - 60 <= o['_box'][2] <= b[5] + 80]
                    above = [o for o in lights if math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < 220 and o['_box'][2] > b[5] + 150]
                    stands = [o for o in lights if o not in rim and 'sconce' not in o['id'].lower() and o['_box'][2] < fl + 40 and math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < w / 2 + 180]
                    near_rugs = [o for o in rugs if math.hypot(o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]) < w / 2 + 320]
                    radial = 0
                    for rg in near_rugs:
                        rb = rg['_box']
                        long_x = (rb[3] - rb[0]) >= (rb[4] - rb[1])
                        vx, vy = rg['p'][0] - p['p'][0], rg['p'][1] - p['p'][1]
                        if math.hypot(vx, vy) < 40:
                            continue
                        if (abs(vx) >= abs(vy)) == long_x:
                            radial += 1
                    isl['planters'] += 1
                    isl['models'][p['id'].lower()] += 1
                    isl['bench_n'].append(len(bn))
                    isl['rim'] += 1 if rim else 0
                    isl['lantern'] += 1 if above else 0
                    isl['stand'] += 1 if stands else 0
                    isl['rugs_near'].append(len(near_rugs))
                    isl['rugs_seen'] += len(near_rugs)
                    isl['radial'] += radial
                    isl['n_in'].append(len(cont))
                    isl['contents'].update(('tree' if TREE.search(o['id'].lower()) else 'low') for o in cont)
                    cx, cy = (rm['x_min'] + rm['x_max']) / 2, (rm['y_min'] + rm['y_max']) / 2
                    isl['d_mid'].append(round(math.hypot(p['p'][0] - cx, p['p'][1] - cy) / max(1.0, min(w_, h_)), 2))
                    if len(isl['examples']) < EXAMPLES and (cont or bn):
                        c_, s_ = math.cos(p['p'][5]), math.sin(p['p'][5])

                        def rel(o):
                            dx, dy = o['p'][0] - p['p'][0], o['p'][1] - p['p'][1]
                            return {'id': o['id'], 'x': round(dx * c_ - dy * s_, 1), 'y': round(dx * s_ + dy * c_, 1), 'z': round(o['p'][2] - p['p'][2], 1),
                                    'rz': round((o['p'][5] - p['p'][5]) % (2 * math.pi), 3), 's': round(o.get('s') or 1.0, 3), 'type': o['type']}
                        isl['examples'].append({'cell': ck, 'kind': kind, 'tiles9': round(tiles9, 1), 'planter': p['id'], 'w': round(w),
                                                'contents': [rel(o) for o in cont], 'benches': [rel(o) for o in bn], 'rim': [rel(o) for o in rim],
                                                'above': [dict(rel(o), up=round(o['_box'][2] - fl)) for o in above], 'stands': [rel(o) for o in stands],
                                                'rugs': [dict(rel(o), w=round(o['_box'][3] - o['_box'][0]), d=round(o['_box'][4] - o['_box'][1])) for o in near_rugs]})
    out = {'cells': seen, 'rooms': {}, 'big_rugs': dict(big_rugs.most_common()), 'rug_scales': {k: _med(v) for k, v in rug_scales.items()},
           'hearth': {'n': HE['n'], 'ids': dict(HE['ids'].most_common()), 'by': {k: round(v / float(HE['n'] or 1), 3) for k, v in HE['by'].items()},
                      'stores_near': _med(HE['sacks'])},
           'hallway': {'rooms': HW['rooms'], 'lights_per_9': round(9.0 * HW['lights'] / float(HW['tiles'] or 1), 3), 'kinds': dict(HW['kinds'].most_common()),
                       'runner': round(HW['runner'] / float(HW['rooms'] or 1), 3), 'rugs_per_room': round(HW['rugs'] / float(HW['rooms'] or 1), 2),
                       'benches_per_room': round(HW['benches'] / float(HW['rooms'] or 1), 2), 'at_wall': round(HW['at_wall'] / float(HW['lights'] or 1), 3)},
           'alcove': {'nooks': AL['nooks'], 'holds': {k: round(v / float(AL['nooks'] or 1), 3) for k, v in AL['holds'].items()}},
           'gallery': {'halls': GA['halls'], 'with': round(GA['with'] / float(GA['halls'] or 1), 3), 'n': _med(GA['n']), 'kinds': dict(GA['kinds'].most_common())},
           'island': {'halls': isl['halls'], 'with': round(isl['with'] / float(isl['halls'] or 1), 3), 'planters': isl['planters'],
                      'benches': _med(isl['bench_n']), 'benches_mean': round(sum(isl['bench_n']) / float(len(isl['bench_n']) or 1), 2),
                      'rim': round(isl['rim'] / float(isl['planters'] or 1), 3), 'lantern': round(isl['lantern'] / float(isl['planters'] or 1), 3),
                      'stand': round(isl['stand'] / float(isl['planters'] or 1), 3), 'rugs_near': _med(isl['rugs_near']),
                      'radial': round(isl['radial'] / float(isl['rugs_seen'] or 1), 3), 'n_in': _med(isl['n_in']), 'contents': dict(isl['contents']),
                      'd_mid': _med(isl['d_mid']), 'models': dict(isl['models'].most_common()), 'examples': isl['examples']}}
    for key, A in R.items():
        n = float(A['rooms'] or 1)
        out['rooms'][key] = {'rooms': A['rooms'], 'tiles9': round(A['tiles'] / n, 1), 'rugs_per_9': round(9.0 * A['rugs'] / float(A['tiles'] or 1), 3),
                             'rugs_per_room': round(A['rugs'] / n, 2), 'cover': round(A['cover'] / n, 3), 'cover_with': _med(A['cover_list']),
                             'rooms_with_rug': round(A['rooms_with_rug'] / n, 3), 'rugs2': round(A['rugs2'] / n, 3),
                             'lights_per_9': round(9.0 * A['lights'] / float(A['tiles'] or 1), 3), 'hung': round(A['hung'] / float(A['lights'] or 1), 3),
                             'shelves_per_room': round(A['shelves'] / n, 2), 'shelf_things': round(A['shelf_things'] / float(A['shelves'] or 1), 1),
                             'shelf_pots': round(A['shelf_pots'] / float(A['shelf_things'] or 1), 3),
                             'beds': A['beds'], 'bed_chest': round(A['bed_chest'] / float(A['beds'] or 1), 3), 'bed_rug': round(A['bed_rug'] / float(A['beds'] or 1), 3),
                             'bed_bay': round(A['bed_bay'] / float(A['beds'] or 1), 3),
                             'planters_per_9': round(9.0 * A['planters'] / float(A['tiles'] or 1), 3), 'big_planters_per_9': round(9.0 * A['big_planters'] / float(A['tiles'] or 1), 3),
                             'benches_per_9': round(9.0 * A['benches'] / float(A['tiles'] or 1), 3), 'rug_ids': dict(A['rug_ids'].most_common(8))}
    return out


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def is_redoran(prefix):
    """Whether a kit prefix is one of the Redoran sets (the large manor kit, the small one, the huts)."""
    return bool(prefix and RED.match(prefix.lower()))


def is_manor(prefix):
    return bool(prefix and MANOR.match(prefix.lower()))


def room_rule(db, prefix, kind):
    """The survey's figures for rooms of this kind in houses of this class ('manor' for the large kit, 'small'
    for the rest), the merged kinds when the kind was seen in fewer than four rooms; None until surveyed."""
    s = ready(db)
    if not s:
        return None
    cls = 'manor' if is_manor(prefix) else 'small'
    K = s['rooms'].get('%s|%s' % (cls, kind))
    if K and K['rooms'] >= 4:
        return K
    # (the class's rooms of any kind, pooled)
    pool = [v for k, v in s['rooms'].items() if k.startswith(cls + '|')]
    if not pool:
        return None
    n = float(sum(v['rooms'] for v in pool) or 1)
    merged = {}
    for f in ('rugs_per_9', 'cover', 'rooms_with_rug', 'rugs2', 'lights_per_9', 'hung', 'bed_chest', 'bed_rug', 'planters_per_9', 'big_planters_per_9', 'benches_per_9'):
        merged[f] = round(sum(v[f] * v['rooms'] for v in pool) / n, 3)
    cw = [v['cover_with'] for v in pool if v.get('cover_with') is not None]
    merged['cover_with'] = _med(cw)
    merged['rooms'] = int(n)
    merged['rug_ids'] = dict(Counter({k: c for v in pool for k, c in v['rug_ids'].items()}).most_common(8))
    return merged


def island_rule(db):
    """How the manors' halls hold their planter island: {'with': share of big halls with a big planter,
    'benches', 'rim', 'lantern', 'stand', 'rugs_near', 'radial', 'models', 'examples'}; None until surveyed."""
    s = ready(db)
    return (s or {}).get('island') if s and s.get('island', {}).get('planters') else None


def big_rugs(db):
    """The big rugs the Redoran places lay (the map reader's "architecture"), most used first, that exist
    in this load order."""
    s = ready(db)
    if not s:
        return []
    return [i for i, _n in sorted(s['big_rugs'].items(), key=lambda kv: -kv[1]) if db.resolve_id(i) is not None]


def rug_scale(db, rid):
    """The scale the Redoran places lay this rug at (the median: the manors' big rugs are the 287-unit
    furn_de_rug_big_06 scaled 2.2 times); 1.0 when unknown."""
    s = ready(db)
    return ((s or {}).get('rug_scales') or {}).get(rid.lower()) or 1.0


def hearth_ids(db):
    """The hearth models the Redoran places stand (the kiln hearth), most used first, that exist here."""
    s = ready(db)
    if not s:
        return []
    return [i for i, _n in sorted(s['hearth']['ids'].items(), key=lambda kv: -kv[1]) if db.resolve_id(i) is not None and 'redoran_hearth' in i]


def report(db):
    """For people: the survey in words."""
    s = survey(db)
    out = ['%d Redoran places walked' % s['cells']]
    for k, K in sorted(s['rooms'].items(), key=lambda kv: -kv[1]['rooms']):
        out.append('%-16s rooms %3d (%.1f tiles): rugs/9 %.2f, cover %.0f%% (with: %s), rooms with rug %.0f%%, 2+ %.0f%%; lights/9 %.2f hung %.0f%%; '
                   'shelves/room %.2f, %.1f things each, pots %.0f%%; beds %d: chest %.0f%% rug %.0f%% bay %.0f%%; planters/9 %.2f (big %.2f); benches/9 %.2f; rugs %s'
                   % (k, K['rooms'], K['tiles9'], K['rugs_per_9'], 100 * K['cover'], K['cover_with'], 100 * K['rooms_with_rug'], 100 * K['rugs2'], K['lights_per_9'], 100 * K['hung'],
                      K['shelves_per_room'], K['shelf_things'], 100 * K['shelf_pots'], K['beds'], 100 * K['bed_chest'], 100 * K['bed_rug'], 100 * K['bed_bay'],
                      K['planters_per_9'], K['big_planters_per_9'], K['benches_per_9'], K['rug_ids']))
    I = s['island']
    out.append('island: %d big halls, %.0f%% with a big planter (%d planters: %s); benches at it median %s (mean %.1f); rim lights %.0f%%, lantern above %.0f%%, '
               'candle stand by %.0f%%; rugs near median %s, radial %.0f%%; things in it median %s (%s); off the room middle %s of the room\'s width'
               % (I['halls'], 100 * I['with'], I['planters'], I['models'], I['benches'], I['benches_mean'], 100 * I['rim'], 100 * I['lantern'], 100 * I['stand'],
                  I['rugs_near'], 100 * I['radial'], I['n_in'], I['contents'], I['d_mid']))
    for e in I['examples'][:12]:
        out.append('   %s %s: %s (%d wide) holds %s; benches %s; rim %s; above %s; stands %s; rugs %s'
                   % (e['cell'], e['kind'], e['planter'], e['w'], [(c['id'], c['x'], c['y'], c['z'], c['s']) for c in e['contents']][:8],
                      [(b['id'], b['x'], b['y'], round(b['rz'], 2)) for b in e['benches']], [(r['id'], r['x'], r['y'], r['z']) for r in e['rim']],
                      [(a['id'], a['up']) for a in e['above']], [(a['id'], a['x'], a['y']) for a in e['stands']], [(r['id'], r['x'], r['y'], round(r['rz'], 2), r['w'], r['d']) for r in e['rugs']]))
    out.append('hallways: %s' % s['hallway'])
    out.append('hearths: %s' % s['hearth'])
    out.append('alcoves: %s' % s['alcove'])
    out.append('gallery lights: %s' % s['gallery'])
    out.append('big rugs: %s' % s['big_rugs'])
    out.append('rug scales: %s' % s.get('rug_scales'))
    return out
