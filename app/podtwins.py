"""Interiors from their twins: a building outside whose interior the game makes as one ready-made piece gets
that piece inside, fitted out as the game's own are. Telvanni pods (in_t_housepod_01 in ex_t_housepod_01), the
Dunmer shacks (in_de_shack_05 in ex_de_shack_05), the Nordic houses (in_nord_house_03, Seyda Neen's), the
Ashlander tents, the Redoran huts, the shipwrecks' cabins: a place each, the way the game builds its small homes.

Measured 2026-10-24 (packaging/nexus/exterior-interior-mapping.md, steps 6 and 9):
  - 1,088 game interiors are one ready-made piece with a building outside; for the homes the exterior model says
    which piece: ex_de_shack_05 -> in_de_shack_05 47 of 48, ex_ashl_tent_02 -> in_ashl_tent_02 33 of 34,
    ex_redoran_hut_02 -> in_redoran_hut_01 20 of 23, ex_nord_house_01 -> in_nord_house_01 16 of 19 (caves are left
    out: a cave entrance leads to any of dozens of caves);
  - a Telvanni home is a pod per place (211 of the 230 interiors with a pod twin hold one), its bridges are
    walkways outdoors;
  - the door outside stands anywhere round the shell, and the piece inside is turned so its way out faces the
    way in (the pod's hole at its +x side, in_t_housepod_door_exit at 352-384 from the middle, 92 of 97);
  - what is in it (the statics, furniture, containers, lights and clutter; no people) is copied whole from one of
    the game's own interiors of that piece, the most typical: the one whose set of models is nearest all the others'.

build() makes a place per shell that has a door of its own outside, links each both ways and turns the
northmarker. A shell without a door outside is named in the notes (give it a door to give it its place)."""
import json
import math
import os
import re
import struct
from collections import Counter, defaultdict

import editing
import kits
import mapdata
import outside
from editing import EditError
from project import b64, set_ref_pos, zs

VERSION = 3
TWIN_KINDS = re.compile(r'housepod|manor|turret|councilhall')
# (and the pieces beside a home that learnt its interior from it: a snow drift on a longhouse, a pod's stem, a
# tunnel, a silt strider at a camp: a second place each, else)
NOT_SHELL =re.compile(r'cave|rock|blacksquare|dias|tomb|barrow|ruin|crypt|mine|grotto|menhir|_entr|snow|drift|stem|tunnel|siltstrider')
NOT_COPIED = ('NPC_', 'CREA', 'LEVC')     # (the people are the maker's business)
DOOR_REACH = 320              # a door outside this close to a shell's box is that shell's
LEARN_MIN = 2                 # a learnt twin: the game's own pairs of the exterior model, at least this many...
LEARN_SHARE = 0.5             # ...and the interior piece in at least this share of them
_sets = {}
_cache = {}


def _disk(db):
    import project
    import taste
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'twinsurvey_%s_v%d.json' % (taste.sig(db), VERSION))


def survey(db):
    """The game's interiors made of one ready-made piece, against the building outside their door: {'twins':
    {exterior model: {interior piece: n}}, 'modules': {exterior model: a group to place (its building as the game
    stands it, relative to the middle and the ground at its door)}} (kept on disk; a minute and a half)."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = _disk(db)
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        _cache['survey'] = (db.recs, saved)
        return saved
    except Exception:
        pass
    import shellsurvey as ss
    known = kits.kits(db)
    memo, bm = {}, {}
    twins_ = defaultdict(Counter)
    modules = {}
    area = lambda r: (r['b'][3] - r['b'][0]) * (r['b'][4] - r['b'][1]) * (r['s'] or 1) ** 2
    # (the shell: the biggest by volume; by floor area a pod's upper floor and stair piece, wider, would win)
    vol = lambda r: area(r) * (r['b'][5] - r['b'][2]) * (r['s'] or 1)
    for key in ss._interiors(db):
        m = mapdata.cellmap(db, key)
        if not m.get('exists') or not m.get('interior'):
            continue
        outs = [r for r in m['refs'] if r['type'] == 'DOOR' and r.get('to') and not r['to']['cell']]
        if not outs:
            continue
        big = [r for r in m['refs'] if r['type'] == 'STAT' and r.get('b') and r['id'].lower().startswith('in_')
               and kits.kit_prefix(r['id']) not in known and not NOT_SHELL.search(r['id'].lower())]
        if not big:
            continue
        shell = max(big, key=vol)
        if area(shell) < 400 * 400 or sum(1 for r in m['refs'] if r['type'] == 'STAT' and kits.kit_prefix(r['id']) in known) > 3:
            continue
        to = outs[0]['to']
        items = ss.near_items(db, to['x'], to['y'], memo, bm)
        if len(memo) > 60:
            memo.clear()
        back = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'].lower() == key and
                math.hypot(it['p'][0] - to['x'], it['p'][1] - to['y']) < 600]
        if not back:
            continue
        d = min(back, key=lambda it: math.hypot(it['p'][0] - to['x'], it['p'][1] - to['y']))
        others = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'] and it['to']['cell'].lower() != key]
        g = ss.structure(items, d['box'], others)
        if not g:
            continue
        main = max(g, key=lambda it: (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1]) * (it['box'][5] - it['box'][4]))
        if NOT_SHELL.search(main['low']):
            continue
        twins_[main['low']][shell['id'].lower()] += 1
        if main['low'] not in modules and len(g) <= 8:
            # (the building as the game stands it: for "Ready-made homes" in Plan a prefab)
            gz = mapdata.terrain_z(db, to['x'], to['y'])
            ground = (gz if gz is not None and -400 < gz - d['p'][2] < 60 else d['p'][2] - 40)
            climb = [it for it in items if re.search(r'stair|step|ramp|ladder|platform|walkway|landing', it['low']) and it['tag'] == 'STAT'
                     and it not in g and any(outside._touch(it['box'], x['box'], 24) for x in g)]
            rows = g + climb + [d]       # (with its way up: stairs to a high door)
            cx = (min(r['p'][0] for r in rows) + max(r['p'][0] for r in rows)) / 2
            cy = (min(r['p'][1] for r in rows) + max(r['p'][1] for r in rows)) / 2
            modules[main['low']] = {'example': key, 'items': [{'id': r['id'], 'dx': round(r['p'][0] - cx, 2), 'dy': round(r['p'][1] - cy, 2),
                                                               'dz': round(r['p'][2] - ground, 2), 'rx': r['p'][3], 'ry': r['p'][4],
                                                               'rz': round(r['p'][5], 5), 's': r['s'] or 1.0} for r in rows]}
    out = {'version': VERSION, 'twins': {k: dict(v) for k, v in twins_.items()}, 'modules': modules}
    _cache['survey'] = (db.recs, out)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


def ready(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    import background
    background.start('which ready-made interiors the game puts in its small houses', lambda: survey(db),
                     task=('podtwins', 'survey', []))
    return None


def _name_twin(db, low):
    """in_X for ex_X (and the Telvanni small set's in_t_s_X), where the two are near one size."""
    if not low.startswith('ex_'):
        return None
    lst = db.by_key.get(('STAT', low))
    for cand in ('in_' + low[3:], 'in_t_s_' + low[5:] if low.startswith('ex_t_') else None):
        if not cand or ('STAT', cand) not in db.by_key or NOT_SHELL.search(cand):
            continue
        be = mapdata.object_bounds(db, lst[-1]) if lst else None
        bi = mapdata.object_bounds(db, db.by_key[('STAT', cand)][-1])
        if be and bi and 0.6 <= (bi[3] - bi[0]) / max(1.0, be[3] - be[0]) <= 1.4 and 0.6 <= (bi[4] - bi[1]) / max(1.0, be[4] - be[1]) <= 1.4:
            return cand
    return None


def twin_for(db, low):
    """The interior piece for an exterior model: the one the game uses most in its interiors behind it
    (LEARN_MIN pairs, LEARN_SHARE of them), else its name twin; None when the game builds it from tiles."""
    s = ready(db)
    c = ((s or {}).get('twins') or {}).get(low)
    if c and not NOT_SHELL.search(low):
        top, n = max(c.items(), key=lambda kv: kv[1])
        if n >= LEARN_MIN and n >= LEARN_SHARE * sum(c.values()):
            return top
    return _name_twin(db, low)


def twins(db):
    """{exterior model: interior twin}: the Telvanni pods' by name (kept for the pods' callers)."""
    out = {}
    for (tag, key), lst in db.by_key.items():
        if tag == 'STAT' and key.startswith('ex_t_') and TWIN_KINDS.search(key):
            t = _name_twin(db, key)
            if t:
                out[key] = t
    return out


def fit_set(db, twin, variant=0):
    """One of the game's own interiors of this twin, the most typical (variant 1, 2...: the next most typical):
    {'cell', 'members': [(id, type, lx, ly, dz, turn, scale, rx, ry)] in the twin's frame, 'exit': index of its
    door to the outside, 'lighting', 'examples'}. Everything in it but its people is a member."""
    if (twin, variant) in _sets and _sets[(twin, variant)][0] is db.recs:
        return _sets[(twin, variant)][1]
    found = []
    for ci in db.used_in.get(twin, ()):
        if db.recs[ci][0] != 'CELL' or not kits.game_made(db, db.recs[ci][7]):
            continue
        m = mapdata.cellmap(db, db.recs[ci][7])
        if not m.get('interior'):
            continue
        tw = [r for r in m['refs'] if r['id'].lower() == twin]
        if len(tw) != 1:
            continue
        t = tw[0]
        b, s = t['b'], t['s'] or 1.0
        mem = []
        for r in m['refs']:
            if r is t or not r.get('b') or r['type'] in NOT_COPIED:
                continue
            lx, ly = outside._local(r['p'][0] - t['p'][0], r['p'][1] - t['p'][1], t['p'][5])
            dz = r['p'][2] - t['p'][2]
            if not (b[0] * s - 64 <= lx <= b[3] * s + 64 and b[1] * s - 64 <= ly <= b[4] * s + 64 and b[2] * s - 64 <= dz <= b[5] * s + 64):
                continue
            mem.append((r['id'], r['type'], round(lx, 1), round(ly, 1), round(dz, 1), round((r['p'][5] - t['p'][5]) % (2 * math.pi), 4),
                        r['s'] or 1.0, r['p'][3], r['p'][4], bool(r.get('to') and not (r['to'] or {}).get('cell'))))
        # (its way out: a door to the outside, of the usual size, at the shell's own wall; one game pod has its
        # exit scaled twice and set out beyond the wall, 724 from the middle, where the player arrived in the air)
        half = max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) * s
        exits = [n for n, x in enumerate(mem) if x[1] == 'DOOR' and 0.9 <= x[6] <= 1.1 and math.hypot(x[2], x[3]) <= half + 32]
        exits.sort(key=lambda n: not mem[n][9])          # (the one that leads outdoors first)
        if not exits:
            continue
        found.append({'cell': m['key'], 'members': mem, 'exit': exits[0], 'lighting': m.get('lighting') or {}})
    if not found:
        _sets[(twin, variant)] = (db.recs, None)
        return None
    # the most typical: the interior whose set of models is nearest all the others' (Jaccard), the fullest first
    sets_ = [frozenset(x[0].lower() for x in f['members']) for f in found]
    def central(i):
        return sum(len(sets_[i] & o) / float(len(sets_[i] | o) or 1) for j, o in enumerate(sets_) if j != i)
    order = sorted(range(len(found)), key=lambda i: (-round(central(i), 3), -len(found[i]['members'])))
    best = dict(found[order[variant % len(order)]])
    best['examples'] = len(found)
    _sets[(twin, variant)] = (db.recs, best)
    return best

def reaches(d, pod):
    """Whether a door outside stands at this pod: within its box, grown by DOOR_REACH (a manor's door stands
    out on a landing; a turret's down at its foot)."""
    b, s = pod['b'], pod['s'] or 1.0
    lx, ly = outside._local(d['p'][0] - pod['p'][0], d['p'][1] - pod['p'][1], pod['p'][5])
    dz = d['p'][2] - pod['p'][2]
    return (b[0] * s - DOOR_REACH <= lx <= b[3] * s + DOOR_REACH and b[1] * s - DOOR_REACH <= ly <= b[4] * s + DOOR_REACH
            and b[2] * s - DOOR_REACH <= dz <= b[5] * s + DOOR_REACH)


def pods_of(db, b):
    """The building's pieces that have an interior twin: [(item, twin id)] (a pod, a shack, a hut, a tent...)."""
    out = []
    for it in b['group']:
        t = twin_for(db, it['low'])
        if t:
            out.append((it, t))
    return out


def _ambi(lit):
    rgb = lambda c: (c[0] | (c[1] << 8) | (c[2] << 16)) if isinstance(c, (list, tuple)) else int(c or 0)
    try:
        return struct.pack('<IIIf', rgb(lit.get('ambient') or (60, 50, 70)), rgb(lit.get('sunlight') or (80, 70, 90)),
                           rgb(lit.get('fog') or (40, 35, 45)), float(lit.get('density') or 1.0))
    except Exception:
        return struct.pack('<IIIf', 60 | (50 << 8) | (70 << 16), 80 | (70 << 8) | (90 << 16), 40 | (35 << 8) | (45 << 16), 1.0)


def build(db, b, name):
    """A place per pod that has a door outside, each the pod's twin fitted out the game's way, linked both
    ways, northmarker in. Returns {'cells': [{key, name, pod, door}], 'notes', 'key'} (key: the front pod's)."""
    import doors
    import release
    editing._require_project(db)
    p = db.project
    pods = pods_of(db, b)
    if not pods:
        raise EditError('No Telvanni pod here with an interior twin in the game.')
    front_door = b.get('door')
    # each door outside goes to the pod it stands nearest (a pod takes one door: its twin has one hole)
    claims = []
    for d in b['doors']:
        if 'marker' in d['low']:
            continue
        near = [pt for pt in pods if reaches(d, pt[0])]
        if not near:
            continue
        best = min(near, key=lambda pt: math.hypot(d['p'][0] - pt[0]['p'][0], d['p'][1] - pt[0]['p'][1]))
        dd = math.hypot(d['p'][0] - best[0]['p'][0], d['p'][1] - best[0]['p'][1])
        claims.append((d is front_door or bool(front_door and d['k'] == front_door['k']), dd, d, best))
    claims.sort(key=lambda c: (not c[0], c[1]))
    used_pods, used_doors, made, notes = set(), set(), [], []
    for is_front, _dd, d, (pod, twin) in claims:
        if pod['k'] in used_pods or d['k'] in used_doors:
            continue
        S = fit_set(db, twin)
        if not S:
            notes.append('The game has no interior of %s with a door to copy: %s is left as it is.' % (twin, pod['id']))
            continue
        used_pods.add(pod['k'])
        used_doors.add(d['k'])
        n = len(made)
        cname = name if n == 0 else '%s: Pod %d' % (name, n + 1)
        key = cname.lower()
        if any(v not in db.dead for v in db.by_key.get(('CELL', key), [])) or key in p.cells:
            raise EditError('There is already a place called "%s".' % cname)
        # the twin turned so its door hole (its +x side) faces the door outside, from the pod's middle
        th = math.atan2(d['p'][0] - pod['p'][0], d['p'][1] - pod['p'][1])
        ex_m = S['members'][S['exit']]
        hole = math.atan2(ex_m[2], ex_m[3])                       # (where the twin's own exit stands in its frame)
        rz = (th - hole) % (2 * math.pi)
        refs = [(twin, (0.0, 0.0, 0.0, 0.0, 0.0, rz), [], 1.0)]
        exit_at = None
        for k_, (mid, mtype, lx, ly, dz, turn, ms, rx, ry, *_rest) in enumerate(S['members']):
            wx, wy = outside._world(lx, ly, rz)
            pos = (round(wx, 2), round(wy, 2), round(dz, 2), rx, ry, round((rz + turn) % (2 * math.pi), 5))
            if k_ == S['exit']:
                exit_at = pos
            refs.append((mid, pos, [], ms))
        header = [['NAME', b64(zs(cname))], ['DATA', b64(struct.pack('<Iii', 1, 0, 0))], ['AMBI', b64(_ambi(S.get('lighting') or {}))]]
        c = p.cells[key] = {'flags': 0, 'header': header, 'refs': {}}
        mine = p.plugin.lower()
        exit_k = None
        for rid, pos, extra, sc in refs:
            subs = set_ref_pos([('NAME', zs(rid))], pos, round(sc, 3) if abs(sc - 1.0) > 0.005 else 1.0)
            nk = p.new_ref_key()
            editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), subs)
            if pos is exit_at:
                exit_k = nk
        db.sync_project()
        # the doors both ways: in, a step in from the exit towards the pod's middle; out, a step out from the
        # door outside, away from the pod
        ix, iy = exit_at[0], exit_at[1]
        il = math.hypot(ix, iy) or 1.0
        # (on the floor: the exit door's foot, not its origin, which most doors have at their middle)
        eb = mapdata.object_bounds(db, db.resolve_id(ex_m[0])) or [0, 0, 0, 0, 0, 0]
        in_pos = [ix - ix / il * 110, iy - iy / il * 110, exit_at[2] + eb[2] * (ex_m[6] or 1.0) + 12, 0.0, 0.0, math.atan2(-ix, -iy) % (2 * math.pi)]
        sill = d['p'][2] + d['b'][2] * d['s']
        out_pos = [d['p'][0] + math.sin(th) * 110, d['p'][1] + math.cos(th) * 110, sill + 12, 0.0, 0.0, th % (2 * math.pi)]
        c1, refs1 = editing._cell(db, d['cell'])
        r1 = refs1.get(d['k'])
        if r1 is not None:
            editing._store(c1, d['k'], r1['origin'], r1['idx'], doors._set_link(r1['subs'], cname, in_pos))
        c2, refs2 = editing._cell(db, key)
        r2 = refs2[exit_k]
        editing._store(c2, exit_k, r2['origin'], r2['idx'], doors._set_link(r2['subs'], '', out_pos))
        db.sync_project()
        try:
            import pathgrid
            pathgrid.generate(db, key, note=False)
        except Exception:
            pass
        made.append({'key': key, 'name': cname, 'pod': pod['id'], 'twin': twin, 'door': d['id'], 'exit': exit_k,
                     'from': S['cell'], 'examples': S.get('examples')})
    for pod, twin in pods:
        if pod['k'] not in used_pods:
            notes.append('%s has no door of its own outside: give it one to give it its own place (the game\'s pods are '
                         'a place each; its bridges are walkways outdoors).' % pod['id'])
    if not made:
        raise EditError('None of the pods has a door outside to lead into it. ' + ' '.join(notes))
    editing.commit(db, 'Built %d Telvanni pod%s from the building outside: %s' % (len(made), '' if len(made) == 1 else 's',
                                                                              ', '.join(m['name'] for m in made)))
    for m in made:
        try:
            m['northmarker'] = release.place_northmarker(db, m['key'], m['exit'])
        except Exception as e:
            print('northmarker:', e)
    return {'key': made[0]['key'], 'name': made[0]['name'], 'cells': made, 'notes': notes}
