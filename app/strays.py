"""Windows a learnt building took from the house next door. The exterior survey keeps a building's trim, its windows
among it, when it touches the building: in a row of joined houses the neighbour's windows touch it too, and a town
built the building with them standing in the air beside it or out of its roof, the user's Nargorewatch, 2026-11-01
("inverted windows, detached from walls", "more floaters").

learn(db) -> {example interior: [indices into its module's fpieces]}: a window with no wall of its own building behind
it, but with a wall behind it where the game set it (its first example, back in the game world), stood on the house
next door. A window with no wall behind it either way is left alone: the ray test can't tell (the game's own windows
fail it 5% of the time, lab jwgame3). Learnt once by the survey process and kept on disk."""
import json
import math
import os

import mapdata

VERSION = 1
REACH = 120                    # (a window's wall stands within this of it along its thin axis, one way or the other)
RING = 1.25                    # (and points just outside its outline: a wall with its hole cut lets a ray through it)
PTS = ((0, 0), (0.6, 0), (-0.6, 0), (0, 0.6), (0, -0.6), (RING, 0), (-RING, 0), (0, RING), (0, -RING))

_mem = {}


def _disk(db):
    import taste
    folder = os.path.join(os.environ.get('WORKSHOP_HOME') or os.path.dirname(os.path.abspath(__file__)), 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'strays_%s_v%d.json' % (taste.sig(db), VERSION))


def ready(db):
    """The strays if learnt; else None, and the survey process learns them meanwhile."""
    k = id(db.recs)
    if k in _mem:
        return _mem[k]
    path = _disk(db)
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                _mem[k] = json.load(f)
                return _mem[k]
        except (OSError, ValueError):
            pass
    import exteriorsurvey as es
    if es.ready(db) is None:
        return None                       # (after the buildings are learnt)
    import background
    background.start('which windows belong to the house next door', lambda: learn(db), task=('strays', 'learn', []))
    return None


def _is_window(pid):
    import townbuild
    return 'win' in pid.lower() and bool(townbuild.OPENING.search(pid))


def _backed(sc, b, x, y, z, rz, s):
    """Is there a face within REACH along the window's thin axis, from any of its nine points?"""
    c, sn = math.cos(rz), math.sin(rz)
    w = lambda ax, ay: (ax * c + ay * sn, -ax * sn + ay * c)
    thinx = (b[3] - b[0]) < (b[4] - b[1])
    n, t = (w(1, 0), w(0, 1)) if thinx else (w(0, 1), w(1, 0))
    ox, oy = w((b[0] + b[3]) / 2 * s, (b[1] + b[4]) / 2 * s)
    ox, oy, oz = x + ox, y + oy, z + (b[2] + b[5]) / 2 * s
    hl = ((b[4] - b[1]) if thinx else (b[3] - b[0])) / 2 * s
    hh = (b[5] - b[2]) / 2 * s
    return any(sc.nearest_any((ox + t[0] * a * hl, oy + t[1] * a * hl, oz + h * hh), (n[0] * d, n[1] * d, 0.0), REACH) is not None
               for a, h in PTS for d in (1, -1))


def learn(db):
    import exteriorsurvey as es
    import shellsurvey as ss
    import seethrough
    import townbuild
    import doors
    s = es.ready(db)
    if s is None:
        s = es.survey(db)
    pairs = {p['key']: p for p in ss.survey(db)['pairs']}
    memo = {}
    out = {}
    todo = []
    for m in s.get('modules') or ():
        fp = m.get('fpieces') or []
        wins = [k for k, p in enumerate(fp) if _is_window(p['id']) and not p.get('door')]
        if not wins or not m.get('examples'):
            continue
        sc = seethrough.Scene()
        for p in fp:
            if p.get('door') or townbuild.OPENING.search(p['id']):
                continue
            ri = db.resolve_id(p['id'])
            model = db.recs[ri][5] if ri is not None else None
            if model and 'marker' not in model.lower():
                sc.add_model(seethrough.model_tris(db, model), (p['x'], p['y'], p['z'], p.get('rx') or 0.0, p.get('ry') or 0.0, p.get('rz') or 0.0), p.get('s') or 1.0)
        loose = []
        for k in wins:
            p = fp[k]
            low = p['id'].lower()
            if low not in memo:
                ri = db.resolve_id(p['id'])
                memo[low] = mapdata.object_bounds(db, ri) if ri is not None else None
            b = memo[low]
            if b and not _backed(sc, b, p['x'], p['y'], p['z'], p.get('rz') or 0.0, p.get('s') or 1.0):
                loose.append(k)
        if loose:
            todo.append((m, loose))
    # back in the game world, where the game set them (ordered by place, for the scene cache)
    def where(item):
        p = pairs.get(item[0]['examples'][0])
        return (math.floor(p['eframe']['x'] / 8192), math.floor(p['eframe']['y'] / 8192)) if p else (0, 0)
    todo.sort(key=where)
    for m, loose in todo:
        p = pairs.get(m['examples'][0])
        if not p:
            continue
        ef = p['eframe']
        fr = ss.Frame(ef['x'], ef['y'], ef['z'], ef['ux'], ef['uy'])
        th = fr.yaw()
        drop = []
        for k in loose:
            q = m['fpieces'][k]
            wx, wy = fr.back(q['x'], q['y'])
            wz = q['z'] + fr.z
            sc = doors._local_scene(db, {'p': [wx, wy, wz, 0, 0, 0]})
            if _backed(sc, memo[q['id'].lower()], wx, wy, wz, (q.get('rz') or 0.0) + th, q.get('s') or 1.0):
                drop.append(k)
        if drop:
            out[m['examples'][0]] = drop
    _mem[id(db.recs)] = out
    try:
        tmp = '%s.%d.tmp' % (_disk(db), os.getpid())
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(out, f)
        os.replace(tmp, _disk(db))
    except OSError:
        pass
    return out


def without(db, m):
    """The module without its strays (when learnt)."""
    S = ready(db)
    ex = (m.get('examples') or [None])[0]
    drop = set((S or {}).get(ex) or ())
    if not drop:
        return m
    return dict(m, fpieces=[p for k, p in enumerate(m['fpieces']) if k not in drop])
