"""The game's arrangements: the set pieces its hand-made interiors are composed of, learnt from the
game's own rooms. A bar is a counter with stools along its front, bottles on it and barrels behind;
a shrine an altar with candles and offerings and a bench before it; a garden a row of planters with
plants in them along a wall; a dining set a table with its chairs under a chandelier; a reading corner
a chair by a lamp and a bookshelf. The survey groups the furniture standing in each of the game's rooms
by nearness, names each group by what it is made of, and keeps how the pieces stand relative to the
group's main piece. Auto-furnish can then lay a whole arrangement the way the game does, rather than
one piece at a time (see arrangements() and furnish.py)."""
import math
import re
from collections import Counter, defaultdict

import furnish
import kits
import roomsurvey

_cache = {}
LIMIT = 200                # places walked (was 400: the whole queue of surveys has to finish in minutes, not a quarter of an hour)
LINK = 200                 # two pieces this close (origin to origin) belong to one arrangement
MAX_MEMBERS = 12
# more kinds of floor piece than furnish.FAMILIES knows, for the set pieces that give a place character
EXTRA = {
    'planter': (('planter', 'flowerbox', 'plantpot', 'plant_pot'), ('STAT', 'ACTI', 'CONT')),
    'plant': (('flora_', '_plant', 'fern', 'shrub', 'bush', 'tree', 'vine', 'kelp', 'mushroom', 'flower', 'ivy'), ('STAT', 'CONT', 'ACTI')),
    'lamp': (('lamp', 'lantern', 'candelabra', 'sconce', 'torch', 'light_'), ('LIGH',)),
    'brazier': (('brazier', 'firepit', 'fire_pit', 'hearth', 'fireplace'), ('LIGH', 'STAT', 'ACTI')),
    'forge': (('forge', 'anvil', 'furnace', 'bellows', 'grindstone', 'smith'), ('STAT', 'ACTI')),
    'loom': (('loom', 'spinning'), ('STAT', 'ACTI')),
    'bath': (('bath', 'tub', 'basin', 'washbasin'), ('STAT', 'ACTI', 'CONT')),
    'rack': (('rack', 'weaponrack', 'armorrack', 'stand_', 'mannequin'), ('STAT', 'CONT', 'ACTI')),
    'bannerpost': (('bannerpost', 'banner_post', 'flagpole'), ('STAT',)),
    'screen': (('screen', 'divider', 'partition'), ('STAT',)),
    'basket': (('basket',), ('CONT', 'STAT')),
    'cage': (('cage',), ('STAT', 'ACTI', 'CONT')),
    'pillow': (('pillow', 'cushion'), ('STAT', 'MISC')),
    'well': (('well', 'fountain'), ('STAT', 'ACTI')),
    'apparatus': (('', ), ('APPA',)),
}
# the main piece of an arrangement: the first of these it holds
ANCHOR_ORDER = ('counter', 'bed', 'shrine', 'forge', 'loom', 'bath', 'well', 'fire', 'table', 'planter', 'bookshelf',
                'cupboard', 'rack', 'shelf', 'chest', 'bench', 'chair', 'screen', 'brazier', 'lamp', 'plant', 'bannerpost',
                'cage', 'crate', 'barrel', 'sack', 'urn', 'basket', 'rug', 'bedroll', 'pillow', 'apparatus')
SKIP = re.compile(r'marker|_nf$|collision|invisible')


def family(db, rid, tag):
    f = roomsurvey.family_of(db, rid, tag)
    if f in roomsurvey.FLOOR_KINDS:
        return f
    low = rid.lower()
    if SKIP.search(low):
        return None
    for k, (words, types) in EXTRA.items():
        if tag in types and (any(w and w in low for w in words) or (words == ('',) and tag in types)):
            if k == 'lamp' and ('candle' in low and 'candelabra' not in low):
                return None                    # (a candle on a table is a dressing, not a floor piece)
            if k == 'plant' and ('planter' in low):
                return 'planter'
            return k
    return None


def _disk(db, limit):
    import taste
    return taste.cache_file('arrangesurvey_%s_%d_v3' % (taste.sig(db), limit))


_thread = {}
EXAMPLES = 20              # examples kept per signature (the game's own offsets, to lay a scene from)


def ready(db, limit=LIMIT):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background
    (while a survey for a changed taste set runs, the newest earlier one stands in)."""
    import os
    import threading
    import taste
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db, limit)):
            return survey(db, limit)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('how the game groups furniture', lambda: survey(db, limit), task=('arrangesurvey', 'survey', [limit]))
    return taste.stale(_cache, key, db.recs, _disk(db, limit))


def survey(db, limit=LIMIT):
    """{'cells': n, 'rooms': n, 'groups': n, 'sigs': {signature: {'n', 'themes': {...}, 'kinds': {...}, 'wall': share
    of anchors against a wall, 'examples': [{'cell', 'theme', 'kind', 'anchor': {'id', 'fam'}, 'members':
    [{'id', 'fam', 'x', 'y', 'z', 'dq', 's'}]}]}}}. A signature is the arrangement's make-up, e.g.
    'counter+chair*3+barrel*2'. Member offsets are in the anchor's frame (x across it, y along its facing)."""
    import json
    import os
    key = ('survey', limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db, limit)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db, limit)
    _cache[key] = (db.recs, out)
    try:
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
    except Exception:
        pass
    return out


def _signature(fams):
    c = Counter(fams)
    return '+'.join('%s*%d' % (k, n) if n > 1 else k for k, n in sorted(c.items(), key=lambda kv: (ANCHOR_ORDER.index(kv[0]) if kv[0] in ANCHOR_ORDER else 99, kv[0])))


def one(db, cell_key):
    """The set pieces of a single place (for "Furnish likeâ€¦"), the same shape as the whole survey's."""
    return _survey(db, 1, cells=[cell_key])


def _survey(db, limit, cells=None):
    import taste
    sigs = defaultdict(lambda: {'n': 0, 'themes': Counter(), 'kinds': Counter(), 'wall': 0, 'examples': []})
    # per room kind and family: how many of the game's pieces stand in a group of two or more, and how
    # many alone (a bed with nothing within reach of it): Auto-furnish lays a lone piece as seldom as the game
    alone = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    if cells is None:
        cells = sorted(k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and lst
                       and lst[-1] not in db.dead and kits.game_made(db, k))
        cells = taste.order(cells)             # (the exemplary places first, each counted several times over)
    seen = rooms_n = groups_n = 0
    given = cells is not None and len(cells) <= limit
    for ck in cells:
        if seen >= limit:
            break
        try:
            info = furnish.rooms(db, ck, trace=given)
        except Exception:
            continue
        if not info['rooms'] or info['tile'] not in ((256, furnish.FLOOR_T) if given else (256,)):
            continue
        seen += 1
        theme = roomsurvey.theme_of(ck)
        refs = [r for r in info['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        for r in refs:
            r['_fam'] = family(db, r['id'], r['type'])
        for rm in info['rooms']:
            rooms_n += 1
            floor = [r for r in refs if r['_fam'] and rm['x_min'] - 40 <= r['p'][0] <= rm['x_max'] + 40 and rm['y_min'] - 40 <= r['p'][1] <= rm['y_max'] + 40
                     and rm['floor'] - 30 <= r['p'][2] + r['b'][2] * (r.get('s') or 1) <= rm['floor'] + 160]
            if not floor:
                continue
            counts = Counter(r['_fam'] for r in floor if r['_fam'] in roomsurvey.FLOOR_KINDS)
            kind = roomsurvey.room_kind(counts)
            # groups: pieces within LINK of one another
            left = list(range(len(floor)))
            while left:
                grp = [left.pop(0)]
                i = 0
                while i < len(grp):
                    a = floor[grp[i]]
                    for j in list(left):
                        b = floor[j]
                        if math.hypot(a['p'][0] - b['p'][0], a['p'][1] - b['p'][1]) <= LINK:
                            grp.append(j)
                            left.remove(j)
                    i += 1
                for i_ in grp:
                    alone[kind][floor[i_]['_fam']][0 if 2 <= len(grp) <= MAX_MEMBERS else 1] += 1
                if len(grp) < 2 or len(grp) > MAX_MEMBERS:
                    continue
                members = [floor[i_] for i_ in grp]
                fams = [m['_fam'] for m in members]
                anchor = min(members, key=lambda m: (ANCHOR_ORDER.index(m['_fam']) if m['_fam'] in ANCHOR_ORDER else 99,
                                                     -(m['b'][3] - m['b'][0]) * (m['b'][4] - m['b'][1])))
                sig = _signature(fams)
                S = sigs[sig]
                S['n'] += 1
                groups_n += 1
                S['themes'][theme] += 1
                S['kinds'][kind] += 1
                ax, ay, az, arz = anchor['p'][0], anchor['p'][1], anchor['p'][2], anchor['p'][5]
                # against a wall: the anchor's box within 48 of the room's edge
                s_ = anchor.get('s') or 1.0
                ab = anchor['b']
                near_wall = min(ax + ab[0] * s_ - rm['x_min'], rm['x_max'] - (ax + ab[3] * s_), ay + ab[1] * s_ - rm['y_min'], rm['y_max'] - (ay + ab[4] * s_)) < 48
                S['wall'] += 1 if near_wall else 0
                if len(S['examples']) < EXAMPLES:
                    c, s = math.cos(arz), math.sin(arz)
                    mem = []
                    for m in members:
                        dx, dy = m['p'][0] - ax, m['p'][1] - ay
                        lx, ly = dx * c - dy * s, dx * s + dy * c
                        mem.append({'id': m['id'], 'fam': m['_fam'], 'x': round(lx, 1), 'y': round(ly, 1), 'z': round(m['p'][2] - az, 1),
                                    'dq': int(round(((m['p'][5] - arz) % (2 * math.pi)) / (math.pi / 2))) % 4,
                                    'rz': round((m['p'][5] - arz) % (2 * math.pi), 3), 's': round(m.get('s') or 1.0, 3),
                                    'anchor': m is anchor})
                    S['examples'].append({'cell': ck, 'theme': theme, 'kind': kind, 'wall': near_wall,
                                          'anchor': {'id': anchor['id'], 'fam': anchor['_fam']}, 'members': mem})
    out = {'cells': seen, 'rooms': rooms_n, 'groups': groups_n,
           'sigs': {k: {'n': v['n'], 'themes': dict(v['themes']), 'kinds': dict(v['kinds']),
                        'wall': round(v['wall'] / max(1, v['n']), 2), 'examples': v['examples']} for k, v in sigs.items()},
           'alone': {kind: {fam: list(v) for fam, v in fams.items()} for kind, fams in alone.items()}}
    return out


def anchor_of(sig):
    """The main piece's family of a signature ('counter+chair*3+barrel*2' â†’ 'counter'): the first named,
    since the signature is written in ANCHOR_ORDER."""
    return sig.split('+')[0].split('*')[0]


def alone_share(db, fam, purpose, limit=LIMIT):
    """How often the game stands a piece of this family on its own in rooms of this kind (nothing within
    LINK of it): a share, or None until surveyed or when too few were seen (fewer than 8)."""
    s = ready(db, limit)
    if not s or 'alone' not in s:
        return None
    kinds = {'hall': ('empty', 'living'), 'living': ('living', 'empty')}.get(purpose, (purpose,))
    grp = lone = 0
    for kd in kinds:
        v = s['alone'].get(kd, {}).get(fam)
        if v:
            grp += v[0]
            lone += v[1]
    if grp + lone < 8:
        # (too few in rooms of the kind: over every kind of room)
        grp = lone = 0
        for kd in s['alone']:
            v = s['alone'][kd].get(fam)
            if v:
                grp += v[0]
                lone += v[1]
    if grp + lone < 8:
        return None
    return round(lone / float(grp + lone), 3)


def scene(db, fam, purpose, theme, rng, limit=LIMIT, like=None):
    """A set piece anchored on a piece of this family, for a room of this purpose: one of the game's own
    examples (as pick() returns them), drawn by how often the game has it in such rooms, a little more for
    the place's own theme; None when the game stands the kind alone as often as not (by its alone share:
    a lone piece is the exception, not the rule), when nothing was seen, or until the survey is done.
    like: one exemplary place's own survey (one()): its scenes with this anchor come first."""
    s = ready(db, limit)
    if not s:
        return None
    share = alone_share(db, fam, purpose, limit)
    # (a counter is never laid alone in a shop or a tavern: the game's counters are runs of segments, and
    # a lone segment is "a barely started shop counter")
    if fam == 'counter' and purpose in ('shop', 'tavern'):
        share = 0.0
    if share is not None and rng.random() < share:
        return None
    kinds = {'hall': ('empty', 'living'), 'living': ('living', 'empty'), 'camp': (), 'ruin': ()}.get(purpose, (purpose,))
    if not kinds:
        return None
    pool = []
    for src, boost in ((like, 3.0), (s, 1.0)):
        if not src:
            continue
        for sig, v in src['sigs'].items():
            if anchor_of(sig) != fam:
                continue
            k = sum(v['kinds'].get(kd, 0) for kd in kinds)
            t = v['themes'].get(theme, 0)
            if not k and src is s:
                continue
            exs = [e for e in v['examples'] if e['kind'] in kinds] or v['examples']
            exs = [e for e in exs if e['anchor']['fam'] == fam]
            if not exs:
                continue
            w = (k + 0.5 * t + (1 if src is like else 0)) * boost
            if fam == 'counter':
                # (a run of two, three or four segments, as the game's shops have them, over a lone piece
                # with a lamp on it)
                n_seg = sum(1 for m in exs[0]['members'] if m['fam'] == 'counter')
                w *= {1: 0.15, 2: 1.0, 3: 1.6, 4: 1.8}.get(n_seg, 1.5)
            pool.append((w, exs))
    if not pool:
        return None
    total = sum(w for w, _e in pool)
    r = rng.random() * total
    for w, exs in pool:
        r -= w
        if r <= 0:
            return rng.choice(exs)
    return rng.choice(pool[-1][1])


def plant_for(db, planter_id, rng, limit=LIMIT):
    """A plant the game stands in this very planter model, with its offset in the planter's frame:
    {'id', 'x', 'y', 'z', 'rz', 's'}; any planter's plant when the model was never seen with one; None
    until surveyed or when the game grows nothing in planters."""
    s = ready(db, limit)
    if not s:
        return None
    own, any_ = [], []
    low = planter_id.lower()
    for sig, v in s['sigs'].items():
        if anchor_of(sig) != 'planter':
            continue
        for e in v['examples']:
            if e['anchor']['fam'] != 'planter':
                continue
            for m in e['members']:
                if m['fam'] == 'plant' and db.resolve_id(m['id']) is not None:
                    (own if e['anchor']['id'].lower() == low else any_).append(m)
    pool = own or any_
    if not pool:
        return None
    m = rng.choice(pool)
    return {'id': m['id'], 'x': m['x'], 'y': m['y'], 'z': m['z'], 'rz': m['rz'], 's': m.get('s', 1.0)}


def scenes_report(db, limit=LIMIT, top=8):
    """For people: per room kind, the scenes the game lays (the commonest signatures, with their counts)
    and, per anchor family, how often a piece of it stands alone."""
    s = survey(db, limit)
    lines = []
    for kind in sorted(s['alone'], key=lambda k: -sum(sum(v) for v in s['alone'][k].values())):
        rows = [(sig, v['kinds'].get(kind, 0)) for sig, v in s['sigs'].items() if v['kinds'].get(kind, 0)]
        rows.sort(key=lambda x: -x[1])
        n_rooms = sum(sum(v) for v in s['alone'][kind].values())
        lines.append('== %s (%d pieces seen): %d scenes' % (kind, n_rooms, sum(n for _s, n in rows)))
        for sig, n in rows[:top]:
            lines.append('   %4d  %s' % (n, sig))
        al = sorted(s['alone'][kind].items(), key=lambda kv: -(kv[1][0] + kv[1][1]))
        lines.append('   alone: ' + ', '.join('%s %d%% of %d' % (f, round(100.0 * v[1] / (v[0] + v[1])), v[0] + v[1]) for f, v in al[:12] if v[0] + v[1] >= 5))
    return '\n'.join(lines)


def arrangements(db, purpose=None, theme=None, min_n=3, limit=LIMIT):
    """The arrangements the game uses in rooms of this purpose (and places of this theme), commonest first:
    [(signature, n, share in this kind, examples)]. None until the survey is done."""
    s = ready(db, limit)
    if not s:
        return None
    out = []
    for sig, v in s['sigs'].items():
        if v['n'] < min_n:
            continue
        k = v['kinds'].get(purpose, 0) if purpose else v['n']
        t = v['themes'].get(theme, 0) if theme else v['n']
        if purpose and not k:
            continue
        out.append((sig, v['n'], k, t, v))
    out.sort(key=lambda x: -(x[2] if purpose else x[1]))
    return out


CHARACTER = ('counter', 'shrine', 'planter', 'forge', 'loom', 'bath', 'well', 'rack', 'brazier', 'fire', 'bed', 'table', 'bookshelf')
NOT_ALONE = ('crate', 'barrel', 'sack', 'urn', 'rug', 'basket', 'pillow', 'plant', 'lamp', 'chair', 'bench')


def pick(db, purpose, theme, rng, tiles, limit=LIMIT, want=(), like=None):
    """One or two arrangements for a room of this purpose in a place of this theme, as the game lays them:
    [example dicts] (see survey), commonest in such rooms first by weighted chance; the second only in a
    big room. Arrangements that are only loose clutter, rugs or seats are left to the furnisher's own ways.
    [] until the survey is done, or when the game has none for the purpose.
    want: the kinds a trade's home has (a smith's forge, an apothecary's apparatus, a priest's shrine:
    wealthsurvey.py): an arrangement that brings one is laid first when the game has one in any room of
    the kind, else in any room at all."""
    # (the survey sorts rooms by what's in them: a hall or an entry with planters and lamps only is 'empty'
    # there; a living room is 'living')
    kinds = {'hall': ('empty', 'living'), 'living': ('living', 'empty'), 'camp': (), 'ruin': ()}.get(purpose, (purpose,))
    if not kinds:
        return []
    cands = arrangements(db, None, theme, min_n=1 if want else 2, limit=limit)
    if not cands:
        return []
    if like:
        # (the model place's own set pieces first: seen once there is enough, and they weigh as much
        # as the game's commonest)
        cands = [(sig, v['n'] + 3, 3 + v['kinds'].get(purpose, 0), 3, v) for sig, v in like['sigs'].items()
                 if any(e['anchor']['fam'] in CHARACTER for e in v['examples'])] + cands
    good = []
    wanted = []
    for sig, n, k, t, v in cands:
        fams = [p.split('*')[0] for p in sig.split('+')]
        if not any(f in CHARACTER for f in fams) or all(f in NOT_ALONE for f in fams):
            continue
        brings = [f for f in fams if f in want]
        k = sum(v['kinds'].get(kd, 0) for kd in kinds)
        if not k and not brings:
            continue
        # (a set piece that gives a place character, a bar or a shrine or a forge, is rarer: seen twice is
        # enough; the everyday ones need three; one the trade asked for, once: every forge the game
        # stands is set about differently)
        rare = any(f in ('counter', 'shrine', 'forge', 'loom', 'bath', 'well', 'planter', 'rack', 'brazier') for f in fams)
        if n < (1 if brings else 2 if rare else 3):
            continue
        exs = [e for e in v['examples'] if e['kind'] in kinds] or v['examples']
        exs = [e for e in exs if e['anchor']['fam'] in CHARACTER]
        if brings:
            # (the trade's piece is the set piece's main one, or stands with a table, a shelf or a
            # counter (an alchemist's apparatus on its bench); and no bed comes with it into a room
            # that isn't a bedroom: a guard tower's bunk with a grindstone beside it stays there)
            exs = [e for e in exs if (e['anchor']['fam'] in want or e['anchor']['fam'] in ('table', 'bookshelf', 'shelf', 'counter', 'chest'))
                   and (purpose == 'bedroom' or not any(m['fam'] == 'bed' for m in e['members']))]
        if not exs:
            continue
        if brings:
            wanted.append((n + 2 * k + 0.5 * t, exs))
            continue
        # (weight: how often the game has it in rooms of this kind, a little more for the place's own theme)
        good.append((k + 0.5 * t, exs))
    if not good and not wanted:
        return []
    out = []
    pool = list(good)
    big = ('table', 'bed', 'counter', 'shrine', 'bookshelf', 'cupboard')
    if wanted:
        # the trade's own set piece first (the commonest of them, mostly), then the room's usual one
        total = sum(w for w, _e in wanted)
        r = rng.random() * total
        for w, exs in wanted:
            r -= w
            if r <= 0:
                break
        ex = rng.choice(exs)
        out.append(ex)
        have = {m['fam'] for m in ex['members'] if m['fam'] in big}
        pool = [(w2, e2) for w2, e2 in pool if not any(m['fam'] in have for m in e2[0]['members'])]
    for _n in range(max(0, (2 if tiles >= 9 else 1) - len(out))):
        if not pool:
            break
        total = sum(w for w, _e in pool)
        r = rng.random() * total
        for i, (w, exs) in enumerate(pool):
            r -= w
            if r <= 0:
                ex = rng.choice(exs)
                out.append(ex)
                pool.pop(i)
                # (the second set piece brings no second table, bed or counter: two dining sets in one
                # room read as an error, not as a lived-in room)
                have = {m['fam'] for m in ex['members'] if m['fam'] in big}
                pool = [(w2, e2) for w2, e2 in pool if not any(m['fam'] in have for m in e2[0]['members'])]
                break
    return out


def report(db, limit=LIMIT, top=60):
    s = survey(db, limit)
    lines = ['%d places, %d rooms, %d arrangements of 2-%d pieces' % (s['cells'], s['rooms'], s['groups'], MAX_MEMBERS)]
    ranked = sorted(s['sigs'].items(), key=lambda kv: -kv[1]['n'])
    lines.append('== commonest arrangements')
    for sig, v in ranked[:top]:
        lines.append('  %4d  %-40s wall %.0f%%  themes %s  rooms %s' % (
            v['n'], sig, v['wall'] * 100, dict(Counter(v['themes']).most_common(3)), dict(Counter(v['kinds']).most_common(3))))
    for word, title in (('counter', 'bars and counters'), ('planter', 'gardens (planters)'), ('plant', 'plants'), ('shrine', 'shrines'),
                        ('forge', 'forges'), ('loom', 'looms'), ('bath', 'baths'), ('rack', 'racks'), ('brazier', 'braziers'), ('lamp', 'lamps')):
        got = [(sig, v) for sig, v in ranked if re.search(r'(^|\+)%s(\*|\+|$)' % word, sig)][:10]
        if not got:
            continue
        lines.append('== %s' % title)
        for sig, v in got:
            ex = v['examples'][0] if v['examples'] else None
            lines.append('  %4d  %-40s wall %.0f%%  e.g. %s: %s' % (
                v['n'], sig, v['wall'] * 100, ex['cell'] if ex else '', ', '.join('%s@(%.0f,%.0f)' % (m['id'], m['x'], m['y']) for m in (ex['members'] if ex else [])[:7])))
    return '\n'.join(lines)
