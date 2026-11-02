"""Which way a door model faces out: the side of it the game puts you on when you come out of the interior behind
it, learnt from the game's own doors (shellsurvey's pairs: an outdoor door, its interior, where its way back puts you).

Measured on the towns' 3,502 game doors with a way back, learnt on half their cells and tried on the other half: a
model's front was known for 1,635 of 1,884 doors and right for 94% of them; where unknown, doors.outside_spot's walls
and roofs (84% alone); the two together 91%. The guess before, towards the middle of the things near the door, was
right for 55% (lab jside/jside2, 2026-11-01: the user and PIN2 came out of the Workshop's linked doors "out of bounds")."""
import hashlib
import json
import math
import os
from collections import defaultdict

import mapdata

VERSION = 1
MIN_N = 3                      # a model's front is trusted from this many of the game's doors
MIN_SHARE = 0.8                # all facing the same way, this share of them at least
_mem = {}


def _disk(db):
    import project
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    sig = hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'doorfronts_%s_v%d.json' % (sig, VERSION))


def thin_axis(door):
    """The door's thin axis in the world, (ux, uy): out of the wall it stands in, one way or the other."""
    b, rz = door['b'], door['p'][5]
    lx, ly = (1.0, 0.0) if (b[3] - b[0]) < (b[4] - b[1]) else (0.0, 1.0)
    c, s = math.cos(rz), math.sin(rz)
    return lx * c + ly * s, -lx * s + ly * c                # (turned clockwise, as the game turns)


def learn(db):
    """{model id (lower): [ways out along +thin axis, along -]} from the game's doors; written to disk."""
    import shellsurvey as ss
    pairs = ss.survey(db)['pairs']
    by_cell = defaultdict(list)
    for p in pairs:
        if p.get('ext_cell') and p.get('eframe'):
            by_cell[p['ext_cell']].append(p)
    st = defaultdict(lambda: [0, 0])
    for ck, ps in by_cell.items():
        m = mapdata.cellmap(db, ck, original=True)
        ds = [r for r in m.get('refs') or () if r['type'] == 'DOOR' and r.get('b')]
        for p in ps:
            e = p['eframe']
            d = min(ds, key=lambda r: math.hypot(r['p'][0] - e['x'], r['p'][1] - e['y']), default=None)
            if d is None or math.hypot(d['p'][0] - e['x'], d['p'][1] - e['y']) > 32 or d['id'].lower() != (p.get('ext_door') or '').lower():
                continue
            ux, uy = thin_axis(d)
            g = -(e['ux'] * ux + e['uy'] * uy)               # (eframe runs from where you arrive towards the door)
            if abs(g) < 0.3:
                continue
            st[d['id'].lower()][0 if g > 0 else 1] += 1
    out = {'version': VERSION, 'fronts': dict(st)}
    try:
        with open(_disk(db), 'w', encoding='utf-8') as f:
            json.dump(out, f)
    except OSError:
        pass
    _mem[id(db.recs)] = out
    return out


def ready(db):
    """The learnt fronts, or None with them being learnt in the background (from the shell survey, once)."""
    key = id(db.recs)
    if key in _mem:
        return _mem[key]
    try:
        with open(_disk(db), encoding='utf-8') as f:
            _mem[key] = json.load(f)
            return _mem[key]
    except (OSError, ValueError):
        pass
    import shellsurvey as ss
    if ss.ready(db) is None:
        return None
    import background
    background.start('which way the game\'s doors face out', lambda: learn(db), task=('doorfronts', 'learn', []))
    return None


def front(db, door):
    """+1 when the game puts you out along the door's +thin axis (thin_axis), -1 the other way, None not known."""
    s = ready(db)
    if not s:
        return None
    a, b = (s.get('fronts') or {}).get(door['id'].lower(), (0, 0))
    if a + b < MIN_N or max(a, b) < MIN_SHARE * (a + b):
        return None
    return 1 if a > b else -1
