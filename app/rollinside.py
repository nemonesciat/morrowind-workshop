"""Roll the interior: another interior for a built town's building, kept in limbo beside the old one until one is
kept. (The user, 2026-11-04: "put the generated interiors in limbo and roll the dice on them, generate a new one
until one matches the specifications I had in mind, then lock it in place"; and "it shouldn't finalize all those NPC
details... move the NPCs over if you're redoing the interior".)

The interior and its people are two layers. A roll makes the shell and its furnishing only (frombuilding.build, then
towninside.make_own), named "<name> (roll N)", and the building's door leads into the roll being looked at. Keeping
one relinks the door, moves the old interior's people over (their records, lines and routines untouched: only where
they stand and what they own), takes the old interior and the other rolls out, makes the walking paths, and gives
the kept place the old name. One Undo step for a roll, one for keeping. Cancel puts the old interior back.

Each roll carries a verdict from the purpose check (purposecheck.issues), so a shrine in a smithy shows on its chip;
"roll until" rolls again on its own until the verdict has what was asked for (a forge, a bed, two floors, no fault).
The state lives in project.rolls: {door "cell|refkey": {'old', 'name', 'rolls': [keys], 'picked', 'kind', 'level'}}."""
import math
import random
import re
import zlib

import kits
import mapdata
import editing
from editing import EditError, commit
from project import ref_info, set_ref_pos, zs, b64

MAX_ROLLS = 4
MAX_TRIES = 8
NAME_MAX = 44                  # of a building's name in a roll's: "(roll 9)" and a place of its own (": Upstairs") must fit in 63
DUP_TRIES = 6                  # rolls thrown away for being the same layout as one on the card before the same one is kept
WANTS = ('forge', 'bed', 'floors', 'clean')


def _rolls(db):
    p = db.project
    if not hasattr(p, 'rolls') or p.rolls is None:
        p.rolls = {}
    return p.rolls


def _building(db, cell, ref):
    import frombuilding
    b = frombuilding.building_at(db, cell, ref)
    if b.get('door') is None:
        raise EditError('The building has no door to roll an interior behind.')
    return b


def _door_ref(db, dcell, dk):
    return next((r for r in mapdata.cellmap(db, dcell).get('refs') or () if r['k'] == dk), None)


def _leads_to(db, dcell, dk):
    r = _door_ref(db, dcell, dk)
    return ((r or {}).get('to') or {}).get('key') or None


def _shared(db, b, key):
    """Another building's door leads into this place too: a town's joined houses made before each had its own interior
    (the user's North Senchal, 2026-11-10). A roll then leaves the place alone: it is the other building's."""
    if not key:
        return False
    mine = {x['k'] for x in b.get('doors') or ()} | {b['door']['k']}
    c = b['door']['cell']
    m = re.match(r'#(-?\d+),(-?\d+)$', c)
    cells = ['#%d,%d' % (int(m.group(1)) + i, int(m.group(2)) + j) for i in (-1, 0, 1) for j in (-1, 0, 1)] if m else [c]
    for ck in cells:
        try:
            refs = mapdata.cellmap(db, ck).get('refs') or ()
        except Exception:
            continue
        for r in refs:
            if r.get('type') == 'DOOR' and r['k'] not in mine and ((r.get('to') or {}).get('key') or '').lower() == key.lower():
                return True
    return False


def _own_cell(db, key):
    """A place that exists only in this mod (made here): the only kind a roll may take out."""
    return bool(key) and key in db.project.cells and not any(v not in db.dead for v in db.by_key.get(('CELL', key.lower()), [])
                                                            if db.recs[v][3] != db.proj_pidx)


def _name_of(db, key):
    return (mapdata.cell_info(db, key) or {}).get('name') or key


def _base_name(db, b, old):
    import frombuilding
    if old:
        return re.sub(r'\s*\(roll \d+\)\s*$', '', _name_of(db, old)).strip() or old
    try:
        return frombuilding._suggest_name(db, b)
    except Exception:
        return 'Interior'


def _unique(db, name):
    import towninside
    taken = set()
    return towninside._unique(db, name, taken)


# ---------------------------------------------------------------- what a roll is like

def card(db, key):
    """One interior as the card shows it: rooms, floors, things, people, what it has (forge, bed, counter, shrine),
    the purpose check's verdict, and a small plan."""
    import purposecheck
    import furnish
    m = mapdata.cellmap(db, key)
    refs = m.get('refs') or []
    try:
        rooms = furnish.rooms(db, key)['rooms']
    except Exception:
        rooms = []
    things = [r for r in refs if not r.get('arch') and r['type'] not in ('DOOR', 'NPC_', 'CREA', 'LIGH')]
    people = [r for r in refs if r['type'] in ('NPC_', 'CREA')]
    has, marks = {}, []
    for r in things:
        f = purposecheck._fam(db, r)
        if f in ('forge', 'anvil', 'bed', 'counter', 'shrine', 'target', 'table', 'shelf', 'fire', 'bookshelf'):
            has[f] = has.get(f, 0) + 1
            if f in ('forge', 'anvil', 'bed', 'counter', 'shrine', 'target', 'fire'):
                marks.append({'f': f, 'x': round(r['p'][0]), 'y': round(r['p'][1]), 'z': round(r['p'][2])})
    try:
        faults = purposecheck.issues(db, key, m)
    except Exception as e:
        print('roll verdict:', key, e)
        faults = []
    kinds = {}
    for f in faults:
        kinds[f['kind']] = kinds.get(f['kind'], 0) + 1
    floors = sorted({round((rm.get('floor') or 0) / 128) for rm in rooms})
    bad = [f for f in faults if f['kind'] in ('purpose', 'nobed', 'stairend')]
    verdict = bad[0]['text'] if bad else ('serves its purpose' if rooms else 'no rooms read')
    doors = [{'x': round(r['p'][0]), 'y': round(r['p'][1]), 'z': round(r['p'][2]), 'out': bool(r.get('to') and not r['to'].get('cell'))}
             for r in refs if r['type'] == 'DOOR']
    return {'key': key, 'name': _name_of(db, key), 'rooms': len(rooms), 'floors': max(1, len(floors)), 'things': len(things),
            'people': len(people), 'has': has, 'faults': kinds, 'verdict': verdict, 'ok': not bad,
            'plan': {'rooms': [{'x0': round(rm['x_min']), 'y0': round(rm['y_min']), 'x1': round(rm['x_max']), 'y1': round(rm['y_max']),
                                'z': round(rm.get('floor') or 0), 'name': rm.get('name') or ''} for rm in rooms],
                     'marks': marks, 'doors': doors}}


def _fits(c, until):
    """Does a card have what 'roll until' asks for?"""
    for w in until or ():
        if w == 'forge' and not (c['has'].get('forge') or c['has'].get('anvil')):
            return False
        if w == 'bed' and not c['has'].get('bed'):
            return False
        if w == 'floors' and c['floors'] < 2:
            return False
        if w == 'clean' and not c['ok']:
            return False
    return True


def _kind_of(db, key, b=None):
    """What the building is for: by the old interior's name and people, else by the sign outside."""
    import purposecheck
    if key:
        m = mapdata.cellmap(db, key)
        people = []
        for r in m.get('refs') or ():
            if r['type'] == 'NPC_':
                try:
                    import npc
                    o_ = npc.read(db, r['id']) or {}
                    people.append(o_.get('cls') or o_.get('class') or '')
                except Exception:
                    pass
        k = purposecheck.kind_of(_name_of(db, key), people)
        if k:
            return k
    if b:
        try:
            import frombuilding
            return frombuilding.shop_trade(b) or ''
        except Exception:
            return ''
    return ''


# ---------------------------------------------------------------- the state

def view(db, cell, ref):
    """The card's state for a building: the old interior, the rolls, which the door leads to."""
    b = _building(db, cell, ref)
    d = b['door']
    k = '%s|%s' % (d['cell'], d['k'])
    st = _rolls(db).get(k)
    cur = _leads_to(db, d['cell'], d['k'])
    if not st:
        st = {'old': cur, 'name': _base_name(db, b, cur), 'rolls': [], 'picked': cur, 'kind': _kind_of(db, cur, b), 'level': None,
              'own_old': _own_cell(db, cur)}
    else:
        st['picked'] = cur
    out = {'door': k, 'cell': cell, 'ref': ref, 'name': st['name'], 'kind': st['kind'], 'level': st.get('level'), 'cellar': st.get('cellar'),
           'old': card(db, st['old']) if st['old'] and st['old'] in db.project.cells or (st['old'] and mapdata.cell_info(db, st['old'])) else None,
           'own_old': st.get('own_old', _own_cell(db, st['old'])), 'rolls': [card(db, rk) for rk in st['rolls'] if mapdata.cell_info(db, rk)],
           'picked': cur, 'building': {'id': (b['group'][0]['id'] if b.get('group') else ''), 'pieces': len(b.get('group') or ())},
           'open': k in _rolls(db)}
    return out


def _one_step(db, n0, note):
    """Everything committed since the operation began, as one Undo step named note (editing.fold)."""
    commit(db, note)
    n = len(getattr(db.project, 'undo_stack', [])) - n0
    if n > 1:
        editing.fold(db, n, note)


def _save(db, k, st):
    _rolls(db)[k] = st


def _kits_for(db, b):
    """The kits the game itself builds this building model's interiors in, most used first: [(kit, pairs)], from the
    shell survey's pairs (kept where the game has two or more such interiors, and the builder knows the kit). A roll
    draws its kit from these, weighted, so a Common house comes out plain, stone, thatch or rich as the game's own do
    (the user, 2026-11-04: "the game and workshop know which model the exterior is: generate from an allowed set of
    interior layouts, and rolling should give another one"). [] when the survey is not to hand or shows one kit."""
    import frombuilding
    import shellsurvey as ss
    from collections import Counter
    try:
        s = ss.ready(db)
        if not s:
            return []
        kit0, bld, _pr = frombuilding.pick_style(db, b)
        main = (bld.get('main') or '').lower()
        c = Counter(p['kit'] for p in s['pairs'] if ss.usable(p) and p.get('kit') and (p['building'].get('main') or '').lower() == main)
        # (a pair built from a family's shared pieces ('in_c': the Common sets' common stock) names no kit the builder
        # has: its count goes to the family's kits, shared out, so a Common house rolls plain, stone, thatch or rich)
        shared = Counter()
        for k_, n in list(c.items()):
            if frombuilding._buildable(db, k_):
                continue
            fam = [x for x in kits.kits(db) if x.lower().startswith(k_.lower() + '_') and frombuilding._buildable(db, x)]
            for x in fam:
                shared[x] += n / float(len(fam))
            del c[k_]
        for k_, n in shared.items():
            c[k_] = c.get(k_, 0) + n
        out = [(k_, round(n, 2)) for k_, n in c.most_common() if n >= 1.5 and frombuilding._buildable(db, k_)]
        return out if len(out) >= 2 else []
    except Exception as e:
        print('roll kits:', e)
        return []


def _shell_sig(db, key):
    """The shell of a place as a number: its architecture pieces, where they stand and how they are turned (the
    furnishing left out), so two rolls of the same layout can be told apart from two of different ones."""
    m = mapdata.cellmap(db, key) if key else None
    if not m:
        return None
    arch = sorted((r['id'].lower(), round(r['p'][0]), round(r['p'][1]), round(r['p'][2]), round(math.degrees(r['p'][5] if len(r['p']) > 5 else 0)) % 360)
                  for r in m.get('refs') or () if r.get('arch'))
    return zlib.crc32(repr(arch).encode()) if arch else None


def _family(db, key):
    """A mod-made place with the places of its own: those named after it with a part after a colon (an upper place
    behind a door up high outside, "<name>: Upstairs"; frombuilding.upper_ways), so a roll's places are made, renamed and
    taken out together."""
    p = db.project
    low = (key or '').lower()
    return [k for k in p.cells if k == low or k.startswith(low + ': ')]


def _delete_cell(db, key):
    p = db.project
    for k in _family(db, key):
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)


def _unlink_outward(db, key):
    """A roll's own door leads out at the building's door: nothing to undo; the building's door is relinked by the caller."""
    return None


# ---------------------------------------------------------------- rolling

def roll(db, cell, ref, kind=None, level=None, until=None, cellar=None):
    """Another interior behind the building's door, in limbo with the others; rolled again on its own while 'until'
    is not met (up to MAX_TRIES). The door leads into the new one. One Undo step."""
    import frombuilding
    import towninside
    editing._require_project(db)
    import ledger
    # (a roll is its building's place's own: the town that made the building takes its rolls with it, ledger.py)
    with editing.operation('roll'), ledger.open(db, 'interior', '', resume=ledger.top_of(db, ledger.owner(db, ref))):
        n0 = len(getattr(db.project, 'undo_stack', []))
        b = _building(db, cell, ref)
        d = b['door']
        k = '%s|%s' % (d['cell'], d['k'])
        R = _rolls(db)
        cur = _leads_to(db, d['cell'], d['k'])
        st = R.get(k)
        if not st:
            kind0 = _kind_of(db, cur, b)
            if _shared(db, b, cur):
                cur = None               # (the other building's place: not this one's to take out, rename or empty)
            st = {'old': cur, 'name': _base_name(db, b, cur), 'rolls': [], 'picked': cur, 'kind': kind0, 'level': None,
                  'own_old': _own_cell(db, cur), 'n': 0}
        if kind is not None:
            st['kind'] = kind
        if level is not None:
            st['level'] = level or None
        if cellar is not None:
            st['cellar'] = cellar if cellar in ('usual', 'big') else None
        tries = MAX_TRIES if until else 1 + DUP_TRIES
        made, tried, dups = None, 0, 0
        # (a roll is another layout: a shell the same as one on the card already, or as the old interior's, is thrown
        # away and rolled again (the user, 2026-11-04: "rolling should give another one"); a building so small that
        # the planner has only the one cut gets the same shell after DUP_TRIES, furnished anew)
        seen = {_shell_sig(db, c_) for c_ in st['rolls'] + [st['old']] if c_}
        kits_ = _kits_for(db, b)
        # (a building the game makes one ready-made interior for, a hut, a pod: every roll of it is that one shell, so the
        # rolls take turns, the ready-made one fitted out from another of the game's examples, then a layout planned from
        # the footprint, and so on; the user, 2026-11-04: "Reroll interior just isn't doing anything to some homes")
        pod = False
        try:
            import podtwins
            pods_ = podtwins.pods_of(db, b)
            pod = bool(pods_) and b.get('door') is not None and any(podtwins.reaches(b['door'], it) for it, _t in pods_)
        except Exception as e:
            print('roll pods:', e)
        for t in range(tries):
            # (built under a scratch name and renamed once kept: a try thrown away left its name taken for a moment,
            # and the next came out "(roll 3) 2")
            name = _unique(db, '%s ~%d' % (st['name'][:NAME_MAX].rstrip(), t + 1))
            seed = zlib.crc32(('%s|%s|%d|%d' % (k, st['name'], t, random.randrange(1 << 20))).encode()) % 100000
            # (the kit: one of those the game pairs with this building model, drawn as often as the game uses each)
            kit = random.Random(seed).choices([k_ for k_, _n in kits_], weights=[n for _k, n in kits_])[0] if kits_ else None
            try:
                # (a cellar is the planner's: a building the game makes a ready-made interior for (a hut, a pod) is planned
                # from its footprint instead when one is asked for)
                planned = bool(st.get('cellar')) or (pod and (st.get('n', 0) + t) % 2 == 1)    # (by the count kept: the list is capped at four)
                out = frombuilding.build(db, d['cell'], d['k'], name, door_key=d['k'], seed=seed, kit=kit,
                                         cellar=st.get('cellar') or None, route='plan' if planned else None,
                                         variant=st.get('n', 0) + t)
            except EditError as e:
                print('roll try %d (%s):' % (t + 1, 'planned' if planned else 'as the game has it'), e)
                _delete_cell(db, name.lower())       # (whatever the try left behind: the user's armorer kept a "(rolling 5)")
                db.sync_project()
                if t == tries - 1 and made is None:
                    raise EditError('No interior could be planned for this building: %s' % e)
                continue
            key = out['key']
            sig = _shell_sig(db, key)
            if pod and not planned:
                sig = None                     # (the ready-made shell: the same every time by nature, fitted out anew)
            if sig in seen and dups < DUP_TRIES and t < tries - 1:
                dups += 1
                _delete_cell(db, key)
                db.sync_project()
                continue
            seen.add(sig)
            tried += 1
            # (a ready-made interior is fitted out like the game's own place it was copied from: furnished from the
            # kit's recipes alone, Tamriel Data's Gold Coast poor house held 2 things and its barn none, lab 2026-11-05)
            like = ((out.get('cells') or [{}])[0].get('from')) if (out.get('plan') or {}).get('style_name') == 'Ready-made interiors' else None
            try:
                towninside.make_own(db, key, like, 'furnished', seed, st['kind'] or None, None, level=st.get('level'))
            except EditError as e:
                print('roll furnish:', name, e)
            db.sync_project()
            c = card(db, key)
            if _fits(c, until) or t == tries - 1 or not until:
                st['n'] = st.get('n', 0) + 1
                made = _rename(db, b, key, _unique(db, '%s (roll %d)' % (st['name'][:NAME_MAX].rstrip(), st['n'])))
                break
            _delete_cell(db, key)          # (not what was asked for: gone, the next try takes its place)
            db.sync_project()
        if made is None:
            raise EditError('Nothing could be rolled for this building.')
        st['rolls'].append(made)
        # (four at a time: the oldest not looked at goes)
        while len(st['rolls']) > MAX_ROLLS:
            gone = st['rolls'].pop(0)
            if gone != made:
                _delete_cell(db, gone)
        st['picked'] = made
        _save(db, k, st)
        db.sync_project()
        _one_step(db, n0, 'Rolled an interior for %s: %s%s' % (_name_of(db, d['cell']) if not d['cell'].startswith('#') else 'the building', _name_of(db, made),
                                                               (' (after %d tries)' % tried) if tried > 1 else ''))
    return view(db, cell, ref)


def pick(db, cell, ref, key):
    """Look at another roll (or the old interior): the building's door leads into it."""
    import frombuilding
    editing._require_project(db)
    b = _building(db, cell, ref)
    d = b['door']
    k = '%s|%s' % (d['cell'], d['k'])
    st = _rolls(db).get(k)
    if not st or (key not in st['rolls'] and key != st['old']):
        raise EditError('That roll is no longer there.')
    if _leads_to(db, d['cell'], d['k']) == key:
        return view(db, cell, ref)
    with editing.operation('roll'):
        n0 = len(getattr(db.project, 'undo_stack', []))
        _relink(db, b, key)
        st['picked'] = key
        db.sync_project()
        _one_step(db, n0, 'Looking at %s' % _name_of(db, key))
    return view(db, cell, ref)


def _relink(db, b, key):
    """The building's door into the interior, and its door out, both ways (frombuilding.link_both)."""
    import frombuilding
    m = mapdata.cellmap(db, key)
    ds = [r for r in m.get('refs') or () if r['type'] == 'DOOR']
    if not ds:
        raise EditError('%s has no door to link.' % _name_of(db, key))
    outs = [r for r in ds if r.get('to') and not r['to'].get('cell')]
    idoor = outs[0] if outs else ds[0]
    frombuilding.link_both(db, b, key, idoor)


# ---------------------------------------------------------------- keeping

def keep(db, cell, ref, key, people='move'):
    """Lock a roll in: the door leads into it, the old interior's people move over (records, lines and routines
    untouched; where they stand, what they own, and their days re-planned for the new rooms), the old interior and
    the other rolls go, the walking paths are made, and the place takes the old name. people: 'move' (the old
    interior's), 'none' (nobody; Populate adds people later). One Undo step."""
    editing._require_project(db)
    b = _building(db, cell, ref)
    d = b['door']
    k = '%s|%s' % (d['cell'], d['k'])
    R = _rolls(db)
    st = R.get(k)
    if not st or key not in st['rolls']:
        raise EditError('That roll is no longer there.')
    import ledger
    with editing.operation('roll'), ledger.open(db, 'interior', '', resume=ledger.top_of(db, ledger.owner(db, ref))):
        n0 = len(getattr(db.project, 'undo_stack', []))
        if _leads_to(db, d['cell'], d['k']) != key:
            _relink(db, b, key)
        old = st['old']
        moved = 0
        if old and old != key and st.get('own_old') and people == 'move':
            moved = _move_people(db, old, key)
        for rk in st['rolls']:
            if rk != key:
                _delete_cell(db, rk)
        if old and old != key and st.get('own_old'):
            _delete_cell(db, old)
        db.sync_project()
        final = key
        # (the old name back, when it is free: "Smith (roll 3)" on the door tooltip would say how it was made)
        # (a building with no place of its own before takes the plain name too)
        if ((old and old != key and st.get('own_old')) or not old) and not mapdata.cell_info(db, st['name']) and st['name'].lower() not in db.project.cells:
            try:
                final = _rename(db, b, key, st['name'])
            except Exception as e:
                print('roll rename:', key, e)
                final = key
        try:
            import pathgrid
            pathgrid.generate(db, final, note=False)
        except Exception as e:
            print('roll paths:', final, e)
        R.pop(k, None)
        db.sync_project()
        _one_step(db, n0, 'Kept %s for its building%s' % (_name_of(db, final), (', its %d people moved in' % moved) if moved else ''))
    return {'key': final, 'name': _name_of(db, final), 'moved': moved}


def cancel(db, cell, ref):
    """Every roll taken out; the door leads into the old interior again. One Undo step."""
    editing._require_project(db)
    b = _building(db, cell, ref)
    d = b['door']
    k = '%s|%s' % (d['cell'], d['k'])
    st = _rolls(db).pop(k, None)
    if not st:
        return view(db, cell, ref)
    with editing.operation('roll'):
        n0 = len(getattr(db.project, 'undo_stack', []))
        if st['old'] and mapdata.cell_info(db, st['old']) and _leads_to(db, d['cell'], d['k']) != st['old']:
            _relink(db, b, st['old'])
        for rk in st['rolls']:
            _delete_cell(db, rk)
        db.sync_project()
        _one_step(db, n0, 'Put %s back, the rolls taken out' % (_name_of(db, st['old']) if st['old'] else 'the building as it was'))
    return view(db, cell, ref)


def _rename(db, b, key, name):
    """A mod-made place under another name: the cell moved whole (its refs keep their keys, so saved games and the
    people's routines know them), its door relinked both ways, the old key gone; the places of its own ("<name>:
    Upstairs") renamed with it and every door to them, inside and outside, pointed at the new names. The new key."""
    import doors as doors_
    from editing import _cell, _store
    p = db.project
    c = p.cells.get(key)
    if c is None:
        return key
    new_key = name.lower()
    renamed = {}                               # old key -> (new key, new name)
    for k in _family(db, key):
        suffix = k[len(key):]                  # ('' for the place itself, ': Upstairs' for a place of its own)
        c_ = p.cells.get(k)
        if c_ is None:
            continue
        nm = name + suffix
        hdr = []
        for t, dat in c_.get('header') or []:
            hdr.append([t, b64(zs(nm))] if t == 'NAME' else [t, dat])
        nc = dict(c_)
        nc['header'] = hdr
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)
        p.cells[nm.lower()] = nc
        renamed[k] = (nm.lower(), nm)
    db.sync_project()
    # (the doors that led to the old names: those of the family's own places between themselves, and any outside)
    for ck in list(renamed.values()) + [(b['door']['cell'], None)] if b and b.get('door') else list(renamed.values()):
        ck_ = ck[0]
        m = mapdata.cellmap(db, ck_)
        for r in m.get('refs') or ():
            to = r.get('to') or {}
            if r['type'] != 'DOOR' or not to.get('cell') or (to.get('key') or to['cell'].lower()) not in renamed:
                continue
            nk, nm = renamed[to.get('key') or to['cell'].lower()]
            c1, refs1 = _cell(db, ck_)
            r1 = refs1.get(r['k'])
            if r1 is not None:
                _store(c1, r['k'], r1['origin'], r1['idx'], doors_._set_link(r1['subs'], nm, [to.get('x', 0), to.get('y', 0), to.get('z', 0), 0.0, 0.0, to.get('rz', 0)]))
    db.sync_project()
    _relink(db, b, new_key)
    return new_key


def _move_people(db, old, new):
    """The old interior's own people (and creatures) placed in the new one: by the furniture their kind stands at, else
    on a clear floor; the head of the household owns the new place's beds and containers; their routines planned
    again in the new rooms. The number moved."""
    import populate
    from editing import _cell, _store
    om = mapdata.cellmap(db, old)
    ppl = [r for r in om.get('refs') or () if r['type'] in ('NPC_', 'CREA') and r.get('new')]
    if not ppl:
        return 0
    # (who heads the house: the owner of its beds)
    head = None
    oc, orefs = _cell(db, old)
    for rk, ref in orefs.items():
        for t, dat in ref['subs']:
            if t == 'ANAM':
                head = (bytes(dat).split(b'\0')[0]).decode('cp1252', 'replace')
                break
        if head:
            break
    try:
        info = populate.place_info(db, new)
    except EditError:
        info = None
    rng = random.Random('%s|%s|move' % (old, new))
    taken, used = [], set()
    nc, nrefs = _cell(db, new)
    moved, made = 0, []
    for r in ppl:
        o = orefs.get(r['k'])
        if o is None:
            continue
        role = ''
        try:
            import npc
            o_ = npc.read(db, r['id']) or {}
            role = _role_of(o_.get('cls') or '')
        except Exception:
            pass
        rel = 'head' if head and r['id'].lower() == head.lower() else 'family'
        sp = populate.spot(db, info, {'role': role, 'relation': rel}, rng, taken, used) if info else None
        if not sp:
            sp = _any_floor(info, rng, taken) if info else None
        if not sp:
            continue
        taken.append((sp[0], sp[1]))
        subs = [(t, bytes(dat)) for t, dat in o['subs']]
        subs = set_ref_pos(subs, (float(sp[0]), float(sp[1]), float(sp[2]), 0.0, 0.0, float(sp[3])), None)
        _store(nc, r['k'], o['origin'], o['idx'], subs)
        oc['refs'].pop(r['k'], None)
        moved += 1
        made.append((r['id'], {'role': role, 'relation': rel, 'spot': sp[:4], 'name': r.get('name') or r['id']}))
    if head and info and info.get('setting') in populate.HOUSEHOLDS:
        for rk, ref in nrefs.items():
            rid, _pos, _s, deleted = ref_info(ref['subs'])
            ri = db.resolve_id(rid)
            low = rid.lower()
            if deleted or ri is None or 'marker' in low or not (db.recs[ri][0] == 'CONT' or (db.recs[ri][0] == 'ACTI' and 'bed' in low)):
                continue
            if db.recs[ri][0] == 'CONT' and not any(w in low for w in populate.OWNED):
                continue
            subs = list(ref['subs'])
            if any(t in ('ANAM', 'CNAM', 'BNAM') for t, _d in subs):
                continue
            at = next((n for n, (t, _d) in enumerate(subs) if t in ('DODT', 'DNAM', 'UNAM', 'DATA')), len(subs))
            subs[at:at] = [('ANAM', zs(head))]
            _store(nc, rk, ref['origin'], ref['idx'], subs)
    # (their days: the old rows point at the old rooms' beds and fires)
    try:
        import routines
        routines.unregister(db, [nid for nid, _p in made])
        if info and made:
            days = routines.plan(db, info, made)
            if days:
                routines.register(db, days)
    except Exception as e:
        print('roll routines:', new, e)
    db.sync_project()
    try:
        import towninside
        towninside.stand_people(db, new)
    except Exception as e:
        print('roll stand:', new, e)
    return moved


def _role_of(cls):
    import purposecheck
    for k, rx in purposecheck.CLASS_TRADE:
        if re.search(rx, cls or '', re.I):
            return k
    return ''


def _any_floor(info, rng, taken):
    import populate
    rooms = list(info.get('rooms') or [])
    rng.shuffle(rooms)
    for rm in rooms:
        for _t in range(30):
            x = rng.uniform(rm['x_min'] + 30, rm['x_max'] - 30) if rm['x_max'] - rm['x_min'] > 70 else (rm['x_min'] + rm['x_max']) / 2
            y = rng.uniform(rm['y_min'] + 30, rm['y_max'] - 30) if rm['y_max'] - rm['y_min'] > 70 else (rm['y_min'] + rm['y_max']) / 2
            if populate._clear(info, taken, x, y):
                return [round(x, 1), round(y, 1), round(rm['floor'] + 4, 1), round(rng.uniform(0, 2 * math.pi), 4), '']
    return None


# ---------------------------------------------------------------- the town's faulty interiors

def faulty(db, cell):
    """The buildings of an outdoor cell whose mod-made interior fails the purpose check: [{ref, door, key, name, verdict}],
    for going through a town's weak interiors one by one."""
    import purposecheck
    out = []
    seen = set()
    for r in mapdata.cellmap(db, cell).get('refs') or ():
        if r['type'] != 'DOOR' or not r.get('to') or not r['to'].get('cell'):
            continue
        key = (r['to'].get('key') or '').lower()
        if not key or key in seen or not _own_cell(db, key):
            continue
        seen.add(key)
        try:
            faults = [f for f in purposecheck.issues(db, key) if f['kind'] in ('purpose', 'nobed', 'stairend', 'bare', 'deaddoor')]
        except Exception:
            faults = []
        if faults:
            out.append({'ref': r['k'], 'key': key, 'name': _name_of(db, key), 'verdict': faults[0]['text'], 'n': len(faults)})
    return {'faulty': out}
