"""A keep of several linked interiors, the way the game's big Imperial keeps are put together (docs/keep-study-2026-11.md,
2026-11-05: Old Ebonheart's Ebon Tower, Firewatch's Ember Keep, Anvil, read whole).

A game keep is not one room behind one door. Ember Keep is eleven interiors off its Great Hall (barracks, high halls,
kitchens, servants' quarters, offices, a treasure chamber, the chapel and its undercroft under it); the Ebon Tower's
palace is twenty-three, in chains and two rings, with the sewers tying the prison, the undercroft and the treasure
chamber together underneath, and spiral-stair towers hanging off the halls. Each interior opens on the others door to
door, every door paired both ways, and on the walls outside at several arches.

plan() lays out such a set for a keep of a size: which interiors (a great hall, chambers, a garrison, a prison, a tower
or two, an undercroft), how they link (a chain with a ring or two through it) and which of them open to the outside.
make() builds each with the Imperial fort kind (dwemer.build(kind='fort'), with the doorways out it needs, its spiral
towers and big halls) and links them door to door; the doors kept for the outside come back for castle.py to pair with
the castle's own arches, tower crowns and keep doors. Nothing is copied from a game interior: every layout is grown,
dressed and lived in by the Workshop's own layers."""
import math
import random
import re
from collections import defaultdict

import mapdata
from editing import EditError

# the interiors a keep may hold: how each is grown (dwemer.build's size, levels, way) and what it asks for (keep:
# big halls' share, spiral towers and their turns, trap doors to the roof)
ROLES = {
    # (the halls climb from their doors: a keep's rooms rise into the mass that stands outside; only the dungeons and
    # the undercroft go down. Grown the generator's own way, down, "all the rooms sprawl downwards, there's no sense of
    # going up into the rest of the castle from the ground floor": the user, 2026-11-06)
    'hall': {'label': 'Great Hall', 'size': 'medium', 'levels': 'steep', 'big': 0.6, 'way': 'up'},
    'chambers': {'label': 'High Chambers', 'size': 'medium', 'levels': 'steep', 'big': 0.35, 'way': 'up'},
    'household': {'label': 'Household', 'size': 'medium', 'levels': 'steep', 'big': 0.2, 'way': 'up'},
    'library': {'label': 'Library', 'size': 'small', 'levels': 'some', 'big': 1.0, 'way': 'up'},
    'chapel': {'label': 'Chapel', 'size': 'small', 'levels': 'some', 'big': 1.0, 'way': 'up'},
    'garrison': {'label': 'Barracks', 'size': 'medium', 'levels': 'some', 'big': 0.15, 'way': 'up'},
    'prison': {'label': 'Dungeons', 'size': 'small', 'levels': 'some', 'big': 0.0, 'way': 'down'},
    'treasury': {'label': 'Treasure Chamber', 'size': 'small', 'levels': 'flat', 'big': 0.5, 'way': 'up'},
    'undercroft': {'label': 'Undercroft', 'size': 'medium', 'levels': 'some', 'big': 0.2, 'way': 'down'},
    'tower': {'label': '%s Tower', 'size': 'small', 'levels': 'some', 'way': 'up', 'big': 0.0, 'spirals': 1, 'turns': (3, 5), 'traps': True},
    # (one interior for a run of wall towers: passages and spiral stairs inside the wall with a door out at every arch,
    # Firewatch's Wall Towers, 13 doors over 7,197)
    'walls': {'label': 'Wall Towers', 'size': 'large', 'levels': 'some', 'way': 'up', 'big': 0.0, 'spirals': 2, 'turns': (2, 3), 'traps': True},
}
TOWER_NAMES = ('North Tower', 'South Tower', 'East Tower', 'West Tower', 'Old Tower', 'High Tower')
# the sets by size: the interiors (role names, a tower more than once) and the links between them by index; every
# plan has a ring (the Palace's Ducal Chambers - Library - Great Hall - Household ring, the sewer loop under the
# Treasure Chamber) and the undercroft under the halls, the prison and the garrison, as the game's sewers tie them
PLANS = {
    'small': {'roles': ['hall', 'garrison', 'tower', 'undercroft'],
              'links': [(0, 1), (0, 2), (0, 3), (1, 3)]},
    'medium': {'roles': ['hall', 'chambers', 'garrison', 'prison', 'tower', 'tower', 'undercroft'],
               'links': [(0, 1), (0, 2), (2, 3), (3, 6), (6, 0), (1, 4), (2, 5), (1, 6)]},
    'large': {'roles': ['hall', 'chambers', 'household', 'library', 'garrison', 'prison', 'treasury', 'tower', 'tower', 'tower', 'undercroft', 'chapel'],
              'links': [(0, 1), (1, 3), (3, 0), (0, 2), (2, 1), (0, 4), (4, 5), (5, 10), (10, 6), (6, 2), (10, 4), (1, 7), (2, 8), (4, 9), (3, 11), (11, 10)]},
}
# which interiors open to the outside, and how many doors each at most (castle.py hands the keep its doors: the ground
# door under the keep, the arches where the walk runs in, the roof door, the tower crowns): the halls first
# (a tower opens to the outside by the hatch at its top alone, as the game's crowns do: its front door is its foot)
OUTS = {'hall': 3, 'garrison': 2, 'chambers': 2, 'household': 1, 'walls': 16, 'prison': 1, 'undercroft': 1}
OUT_ORDER = ('hall', 'garrison', 'chambers', 'household', 'prison', 'undercroft')


def plan(size='medium', seed=1, outs=None, box=None):
    """The set for a keep of this size: {'interiors': [{'i', 'role', 'label', 'size', 'levels', 'way', 'keep'}], 'links':
    [(i, j)], 'outs': {i: n}} with each interior's keep asks worked out from the doors it needs (one way out for each
    link, each door to the outside, and the front door counting as one). outs: how many doors to the outside the keep
    has to take ({role: n} or a number spread over the halls first), None for the plan's own. box: [half width, depth]
    of the keep's mass outside, from its door in; each hall keeps within it (the towers and the walls' passages stand
    where their own pieces do)."""
    P = PLANS.get((size or 'medium').partition('+')[0], PLANS['medium'])
    rng = random.Random('keep|%s|%s' % (size, seed))
    roles = list(P['roles'])
    links = [tuple(l) for l in P['links']]
    deg = defaultdict(int)
    for a, b in links:
        deg[a] += 1
        deg[b] += 1
    # the doors to the outside: as asked, else the plan's own (the great hall's ground door and a walk door, a tower's crown)
    want_out = {}
    if isinstance(outs, dict):
        for role, n in outs.items():
            for i, r in enumerate(roles):
                if r == role and n > 0:
                    take = min(n, OUTS.get(role, 1))
                    want_out[i] = take
                    n -= take
    elif isinstance(outs, int):
        n = outs
        for role in OUT_ORDER:
            for i, r in enumerate(roles):
                if r == role and n > 0:
                    take = min(n, OUTS.get(role, 1))
                    want_out[i] = take
                    n -= take
    else:
        want_out = {0: 2}
    towers = 0
    out = []
    for i, role in enumerate(roles):
        R = ROLES[role]
        label = R['label']
        if '%s' in label:
            label = TOWER_NAMES[towers % len(TOWER_NAMES)]
            towers += 1
        doors = deg[i] + want_out.get(i, 0)
        keep = {'exits': max(0, doors - 1), 'big': R.get('big', 0.0), 'spirals': R.get('spirals', 0), 'traps': bool(R.get('traps')),
                'nostories': True}
        if R.get('turns'):
            keep['turns'] = list(R['turns'])
        if box and role not in ('tower', 'walls') and R.get('way') != 'down':   # (underground may spread past the mass)
            keep['box'] = [float(box[0]), float(box[1])]
        out.append({'i': i, 'role': role, 'label': label, 'size': R['size'], 'levels': R['levels'], 'way': R.get('way', 'down'),
                    'keep': keep, 'seed': rng.getrandbits(31), 'doors': doors})
    return {'size': size, 'seed': seed, 'interiors': out, 'links': links, 'outs': want_out}


def _free_name(db, nm):
    base, k = nm, 2
    low = nm.lower()
    while any(v not in db.dead for v in db.by_key.get(('CELL', low), [])) or low in db.project.cells:
        nm = '%s %d' % (base, k)
        low = nm.lower()
        k += 1
    return nm


def _layout_with_doors(db, I, tries=6):
    """A seed whose layout gives the interior the doorways it needs (dwemer.generate with its keep asks): the plan's
    seed, else the next few drawn from it. (seed, layout)."""
    import dwemer
    rng = random.Random(I['seed'])
    best = None
    for t in range(tries):
        seed = I['seed'] if t == 0 else rng.getrandbits(31)
        try:
            lay = dwemer.generate(db, I['size'], I['levels'], 'branching', seed=seed, kind='fort', way=I['way'], keep=I['keep'])
        except EditError:
            continue
        got = 1 + len(lay.get('exits') or [])
        if got >= I['doors']:
            return seed, lay
        if best is None or got > best[0]:
            best = (got, seed, lay)
    if best is None:
        raise EditError('No layout for the keep\'s %s keeps the rules.' % I['label'].lower())
    return best[1], best[2]


def make(db, name, *a, **k):
    """_make, written into the places ledger (ledger.py): a keep's interiors, its castle's when one is being made."""
    import ledger
    with ledger.open(db, 'interior', name, seed=k.get('seed')):
        return _make(db, name, *a, **k)


def _make(db, name, size='medium', seed=1, outs=None, people=True, commit=True, progress=None, box=None):
    """The keep's interiors built and linked. name: the keep's ("Fort Vanvuld": its interiors are "Fort Vanvuld, Great
    Hall" and so on). outs: the doors to the outside wanted, as plan(). Returns {'name', 'cells': [keys], 'interiors':
    [{role, label, key, name, doors: [...]}], 'links': n, 'outs': [{cell, k, name, arrive, role, z}] (the doors kept for
    the outside, highest first within each interior), 'rings'}; with commit, one Undo takes the whole keep back."""
    import editing
    import dwemer
    editing._require_project(db)
    p = db.project
    name = (name or '').strip()
    if not name:
        raise EditError('Give the keep a name.')
    S = dwemer.ready(db, 'fort')
    if S is None:
        import learning
        return {'learning': learning.ruin_pending(db, 'fort')}
    PL = plan(size, seed, outs, box)
    stack = getattr(p, 'undo_stack', [])
    n0 = len(stack)
    say = progress or (lambda what, frac: None)
    made = []
    for n_, I in enumerate(PL['interiors']):
        say('Building the %s' % I['label'].lower(), 0.1 + 0.6 * n_ / max(1, len(PL['interiors'])))
        nm = _free_name(db, '%s, %s' % (name, I['label']))
        seed_, lay = _layout_with_doors(db, I)
        r = dwemer.build(db, nm, I['size'], I['levels'], 'branching', seed=seed_, kind='fort', way=I['way'], keep=I['keep'],
                         occupants='none', commit=True)
        if r.get('learning'):
            return r
        doors = [d for d in r.get('doors') or []]
        made.append({'i': I['i'], 'role': I['role'], 'label': I['label'], 'key': r['key'], 'name': nm, 'doors': doors, 'seed': seed_,
                     'tunnels': r.get('tunnels'), 'halls': r.get('halls'), 'rings': r.get('rings', 0), 'spirals': r.get('spirals', 0),
                     'floors': len({round(dwemer_floor(S, pc) / 128) for pc in lay['pieces'] if not pc.get('gone') and pc.get('id') and pc.get('of') is None})})
    # ---- the doors: each link takes a door at either end; the front door is kept for the outside where the outside
    # is wanted, else it is a link's; a tower's front door is its foot, the way in from the hall it hangs off
    say('Linking the doors', 0.75)
    by_i = {m['i']: m for m in made}
    spare = {}
    for m in made:
        ds = list(m['doors'])
        front = [d for d in ds if d['kind'] == 'front']
        rest = [d for d in ds if d['kind'] == 'exit']
        traps = [d for d in ds if d['kind'] == 'trap']
        n_out = PL['outs'].get(m['i'], 0)
        # (the doors for the outside: the front door first, then the highest exits; a tower's crown trap door is for
        # the outside too, when a crown is there to take it)
        keep_out = (front + sorted(rest, key=lambda d: -d['pos'][2]))[:n_out] if n_out else []
        m['out'] = keep_out + traps
        spare[m['i']] = [d for d in front + sorted(rest, key=lambda d: -d['pos'][2]) if d not in keep_out]
    links_done = []
    unmet = []
    for a, b in PL['links']:
        if a not in by_i or b not in by_i or not spare.get(a) or not spare.get(b):
            unmet.append((a, b))
            continue
        da, db_ = spare[a].pop(0), spare[b].pop(0)
        A, B = by_i[a], by_i[b]
        _link(db, A['key'], da['k'], B['name'], db_['arrive'])
        _link(db, B['key'], db_['k'], A['name'], da['arrive'])
        links_done.append((a, b))
    # (a door more than its links and outside doors need: paired with another such, the farthest interior first, so
    # no door leads nowhere; an odd one left is given to the outside)
    extra = [(i, d) for i, ds in spare.items() for d in ds]
    while len(extra) >= 2:
        i, d = extra.pop(0)
        j_, d2 = next(((j, e) for j, e in extra if j != i), extra[0])
        extra.remove((j_, d2))
        _link(db, by_i[i]['key'], d['k'], by_i[j_]['name'], d2['arrive'])
        _link(db, by_i[j_]['key'], d2['k'], by_i[i]['name'], d['arrive'])
        links_done.append((i, j_))
    for i, d in extra:
        by_i[i]['out'].insert(0, d)
    db.sync_project()
    cells = [m['key'] for m in made]
    editing.commit(db, 'Linked the doors of %s' % name)
    try:
        import doors as doors_
        doors_.face_arrivals(db, cells, follow=False)
    except Exception as e:
        print('keep arrivals:', e)
    # ---- people: a garrison in the halls, as the game's keeps of the kind are peopled (populate.cast reads a keep's
    # setting off its name and furniture)
    folks = 0
    if people:
        say('Placing the people', 0.9)
        folks = _people(db, made, seed)
    outs_ = []
    for m in made:
        for d in m['out']:
            outs_.append({'cell': m['key'], 'k': d['k'], 'name': m['name'], 'arrive': d['arrive'], 'role': m['role'], 'kind': d['kind'],
                          'z': d['pos'][2], 'label': m['label']})
    out = {'name': name, 'cells': cells, 'interiors': made, 'links': len(links_done), 'link_list': links_done, 'unmet': unmet, 'outs': outs_,
           'rings': _cycle_rank(len(made), links_done), 'people': folks, 'plan': PL}
    if commit:
        steps = len(getattr(p, 'undo_stack', [])) - n0
        if steps > 1:
            editing.fold(db, steps, 'Made the keep of %s: %d interiors, %d links%s' % (name, len(made), len(links_done), (', %d people' % folks) if folks else ''))
    return out


def dwemer_floor(S, pc):
    import dgrules
    return dgrules.floor_of(S, pc)


def _cycle_rank(n, links):
    """How many independent rings the interiors' link graph has (joins - nodes + parts)."""
    par = list(range(n))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for a, b in links:
        par[f(a)] = f(b)
    parts = len({f(i) for i in range(n)})
    return len(links) - n + parts


def _link(db, cell, rk, dest, pos):
    import doors
    import editing
    c, refs = editing._cell(db, cell)
    ref = refs.get(rk)
    if ref is None:
        return False
    editing._store(c, rk, ref['origin'], ref['idx'], doors._set_link(ref['subs'], dest, [float(v) for v in pos[:6]]))
    return True


def _people(db, made, seed):
    """The keep's people: each interior cast as the game casts a place of its setting (populate.cast: a keep's name and
    furniture read as a garrison's or a guild's), placed in its rooms; the prison and the undercroft get nobody."""
    import zlib
    try:
        import castsurvey
        if castsurvey.ready(db) is None:
            return 0
        import populate
    except Exception:
        return 0
    n, said = 0, []
    for m in made:
        if m['role'] in ('prison', 'undercroft', 'treasury'):
            continue
        try:
            cast_ = populate.cast(db, m['key'], {'density': 'few'} if m['role'] in ('tower', 'library', 'chapel') else {},
                                  seed=zlib.crc32(('%s|%s' % (seed, m['name'])).encode()))
            ppl = (cast_ or {}).get('people') or []
            if ppl:
                pl = populate.place(db, m['key'], ppl, own=True, lines=False)
                said += pl.get('people') or []
                n += len(ppl)
        except Exception as e:
            print('keep people:', m['name'], e)
    if said:
        import editing
        try:
            if populate.write_lines(db, said):
                editing.commit(db, 'Lines for the people of the keep')
        except Exception as e:
            print('keep lines:', e)
    return n


# ------------------------------------------------------------------------------------------------ reading a made keep
LOAD_DOOR = re.compile(r'loaddoor|trap|hatch', re.I)


def doors_of(db, cells):
    """Every door that leads somewhere, or should, in these places (the load doors and hatches; a door that only swings
    in its frame is left out): [{cell, k, id, to (cell key or None), pos}]."""
    out = []
    for ck in cells:
        m = mapdata.cellmap(db, ck)
        for r in m.get('refs') or ():
            if r['type'] == 'DOOR' and (LOAD_DOOR.search(r['id']) or r.get('to')):
                to = (r.get('to') or {}).get('key') if r.get('to') else None
                if r.get('to') and not to:
                    to = ((r['to'].get('cell') or '').lower()) or '#'
                out.append({'cell': ck, 'k': r['k'], 'id': r['id'], 'to': to, 'pos': r['p'][:3]})
    return out


def pairing(db, cells):
    """How the doors of a keep pair: {'doors': n, 'paired': doors leading to another of these places that has a door
    leading back, 'out': doors leading outside them, 'unpaired': doors leading nowhere, 'oneway': doors whose other
    end leads elsewhere}."""
    cells = set(cells)
    ds = doors_of(db, cells)
    leads = defaultdict(set)
    for d in ds:
        if d['to'] and d['to'] in cells:
            leads[(d['cell'], d['to'])].add(d['k'])
    paired = oneway = out = unp = 0
    for d in ds:
        if not d['to']:
            unp += 1
        elif d['to'] not in cells:
            out += 1
        elif leads.get((d['to'], d['cell'])):
            paired += 1
        else:
            oneway += 1
    return {'doors': len(ds), 'paired': paired, 'out': out, 'unpaired': unp, 'oneway': oneway}
