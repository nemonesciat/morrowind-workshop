"""Quick-start creators: new interiors with working doors, NPCs by role,
readable notes/books, and filled containers. Everything is built from what
already exists in your load order, so it looks and behaves like the base game."""
import math
import random
import re
import struct

import editing
import mapdata
from editing import EditError
from esm import ENC, iter_subrecords, zstr
from project import b64, join_subs, ref_info, set_ref_pos, split_cell, zs

OWNER_TAGS = {'ANAM', 'BNAM', 'CNAM', 'INDX'}     # who owns a placed object (not wanted in a fresh copy)
DOOR_TAGS = {'DODT', 'DNAM'}


def _data(db, i):
    r = db.recs[i]
    return db.files[r[3]].record_at(r[4])[2]


def _winners(db, tag):
    return [lst[-1] for k, lst in db.by_key.items() if k[0] == tag and lst and lst[-1] not in db.dead]


def _check_id(db, tag, new_id):
    new_id = (new_id or '').strip()
    if not new_id:
        raise EditError('Give it an ID.')
    if len(new_id.encode(ENC, 'replace')) > 31:
        raise EditError('IDs can be at most 31 characters.')
    if db.resolve_id(new_id) is not None or db.by_key.get((tag, new_id.lower())):
        raise EditError('Something with the ID "%s" already exists.' % new_id)
    return new_id


def suggest_id(db, prefix, name):
    base = re.sub(r'[^a-z0-9]+', '_', (name or 'new').lower()).strip('_')[:20] or 'new'
    stem = ('%s_%s' % (prefix, base))[:28] if prefix else base
    cand, n = stem, 2
    while db.resolve_id(cand) is not None or any(db.by_key.get((t, cand)) for t in ('NPC_', 'BOOK', 'CONT')):
        cand = '%s_%d' % (stem, n)
        n += 1
    return cand


def _prefix(db):
    return re.sub(r'[^a-z0-9]+', '', db.project.name.lower())[:6] or 'mod'


# ===================================================================== interiors
_interior_cache = None


def interior_templates(db):
    """Small/medium interiors with a door, with a style guess, for "New interior"."""
    global _interior_cache
    if _interior_cache is not None and _interior_cache[0] is db.recs:
        return _interior_cache[1]
    out = []
    for k, lst in db.by_key.items():
        if k[0] != 'CELL' or k[1].startswith('#'):
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        data = _data(db, live[-1])
        n = data.count(b'FRMR')
        if not 25 <= n <= 160 or b'DODT' not in data:
            continue
        votes = {}
        _hdr, refs = split_cell(data)
        for ref in refs:
            rid = ''
            for t, d in ref['subs']:
                if t == 'NAME':
                    rid = zstr(d).lower()
                    break
            if not (rid.startswith('in_') or '_in_' in rid or '_i_' in rid):
                continue
            label = mapdata.style_of(rid)
            if label:
                votes[label] = votes.get(label, 0) + 1
        style = max(votes, key=votes.get) if votes else 'Other'
        out.append({'key': k[1], 'name': db.recs[live[-1]][1], 'objects': n, 'style': style})
    out.sort(key=lambda t: (t['style'], t['objects']))
    _interior_cache = (db.recs, out)
    return out


_pairs_cache = None


def _door_pairs(db):
    """Outside doors and where they lead: interior name (lower) -> list of (door ref info)."""
    global _pairs_cache
    if _pairs_cache is not None and _pairs_cache[0] is db.recs:
        return _pairs_cache[1]
    pairs = {}
    _pairs_cache = (db.recs, pairs)
    for k, lst in db.by_key.items():
        if k[0] != 'CELL':
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        data = _data(db, live[-1])
        if b'DNAM' not in data:
            continue
        _hdr, refs = split_cell(data)
        for ref in refs:
            s = dict(ref['subs'])
            if 'DNAM' in s and 'DODT' in s:
                rid, pos, _sc, deleted = ref_info(ref['subs'])
                if not deleted:
                    pairs.setdefault(zstr(s['DNAM']).lower(), []).append(
                        {'id': rid, 'pos': pos, 'dest': struct.unpack_from('<6f', s['DODT']), 'cell': k[1]})
    return pairs


MATCHING, OTHER, HATCHES = 'Doors used for this style', 'All other outside doors', 'Trapdoors and hatches'


def _is_hatch(door_id):
    k = door_id.lower()
    return 'trap' in k or 'hatch' in k


def outside_doors(db, template_key=None, style=None, limit=14):
    """Outside doors in groups: the ones used for rooms of this style (most used first), then every
    other door the game uses outdoors, then trapdoors. The template room's own door is marked."""
    pairs = _door_pairs(db)
    names_of_style = {t['name'].lower() for t in interior_templates(db) if not style or t['style'] == style}
    counts, everywhere = {}, {}
    for dest, lst in pairs.items():
        for pr in lst:
            if pr['cell'].startswith('#'):                  # a door that stands outdoors
                everywhere[pr['id']] = everywhere.get(pr['id'], 0) + 1
            if dest in names_of_style and not _is_hatch(pr['id']):
                counts[pr['id']] = counts.get(pr['id'], 0) + 1
    own = None
    if template_key:
        tinfo = mapdata.cell_info(db, template_key)
        if tinfo:
            lst = pairs.get(tinfo['name'].lower(), [])
            if lst:
                own = lst[0]['id']
    out, seen = [], set()

    def add(did, n, group):
        ri = db.resolve_id(did)
        if ri is None or db.recs[ri][0] != 'DOOR' or db.recs[ri][1].lower() in seen:
            return
        seen.add(db.recs[ri][1].lower())
        out.append({'id': db.recs[ri][1], 'name': db.recs[ri][2] or did, 'uses': n, 'group': group})

    for did, n in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]:
        add(did, n, MATCHING)
    if own and own.lower() not in seen:
        add(own, 0, HATCHES if _is_hatch(own) else MATCHING)
    rest = sorted(everywhere.items(), key=lambda kv: (_is_hatch(kv[0]), kv[0].lower()))
    for did, n in rest:
        add(did, n, HATCHES if _is_hatch(did) else OTHER)
    for d in out:
        if own and d['id'].lower() == own.lower():
            d['original'] = True
    order = (MATCHING, OTHER, HATCHES)
    out.sort(key=lambda d: order.index(d['group']))     # stable: keeps "most used first" inside a group
    if not out and db.resolve_id('ex_common_door_01') is not None:
        out.append({'id': 'ex_common_door_01', 'name': 'Door', 'uses': 0, 'group': OTHER})
    return out


def _rot2(dx, dy, angle):
    """Rotate a horizontal offset the way the game turns objects (clockwise for positive angles)."""
    c, s = math.cos(angle), math.sin(angle)
    return dx * c + dy * s, -dx * s + dy * c


def create_interior(db, template_key, name, contents, entrance, door_id=None, save=True):
    """Copy a template room into a new interior and link it to a new outside door.
    contents: 'furnished' | 'lights' | 'empty'. entrance: {cell, x, y, z, rz} or None.
    save=False leaves the commit to the caller (a hidden door made in the same change: mechanism.py)."""
    editing._require_project(db)
    p = db.project
    name = (name or '').strip()
    if not name:
        raise EditError('Give the new interior a name.')
    if len(name.encode(ENC, 'replace')) > 63:
        raise EditError('Interior names can be at most 63 characters.')
    key = name.lower()
    if db.by_key.get(('CELL', key)) and any(v not in db.dead for v in db.by_key[('CELL', key)]):
        raise EditError('There is already a place called "%s".' % name)
    refs, header = db.cell_refs(template_key)
    if header is None:
        raise EditError('That template room no longer exists.')
    tinfo = mapdata.cell_info(db, template_key)
    pairs = _door_pairs(db)

    # the template's front door: a load door that leads outside (or anywhere, failing that)
    front, front_k = None, None
    for rk, ref in refs.items():
        s = dict(ref['subs'])
        if 'DODT' in s and not ref_info(ref['subs'])[3]:
            if 'DNAM' not in s:
                front, front_k = ref, rk
                break
            if front is None:
                front, front_k = ref, rk

    new_refs = []
    centre = [0.0, 0.0, 0.0]
    for rk, ref in refs.items():
        rid, pos, scale, deleted = ref_info(ref['subs'])
        if deleted:
            continue
        ri = db.resolve_id(rid)
        if ri is None:
            continue
        tag = db.recs[ri][0]
        if tag in ('NPC_', 'CREA', 'LEVC'):
            continue
        b = mapdata.object_bounds(db, ri)
        arch = mapdata.is_architecture(tag, rid, b) or tag == 'DOOR'
        if contents == 'empty' and not arch:
            continue
        if contents == 'lights' and not (arch or tag == 'LIGH'):
            continue
        subs = [(t, d) for t, d in ref['subs'] if t not in OWNER_TAGS]
        if rk != front_k:
            subs = [(t, d) for t, d in subs if t not in DOOR_TAGS]      # other doors become normal doors
        new_refs.append((rk, subs))
        for a in range(3):
            centre[a] += pos[a]
    if not new_refs:
        raise EditError('Nothing to copy from that template.')
    centre = [c / len(new_refs) for c in centre]

    # where the player arrives inside: same spot the original outside door used, or just inside the door
    inside_arrival = None
    for pr in pairs.get(tinfo['name'].lower() if tinfo else '', []):
        inside_arrival = pr['dest']
        orig_outside = pr
        break
    else:
        orig_outside = None
    if inside_arrival is None and front is not None:
        fp = ref_info(front['subs'])[1]
        dx, dy = centre[0] - fp[0], centre[1] - fp[1]
        d = math.hypot(dx, dy) or 1
        inside_arrival = (fp[0] + dx / d * 96, fp[1] + dy / d * 96, fp[2] + 16, 0, 0, math.atan2(dx, dy))

    # the outside door
    outside = None
    if entrance and entrance.get('cell'):
        if not door_id:
            choices = outside_doors(db, template_key, tinfo and next(
                (t['style'] for t in interior_templates(db) if t['key'] == template_key), None))
            plain = [d for d in choices if not d.get('original')] or choices
            door_id = plain[0]['id'] if plain else 'ex_common_door_01'
        ri = db.resolve_id(door_id)
        if ri is None or db.recs[ri][0] != 'DOOR':
            raise EditError('"%s" is not a door.' % door_id)
        ex, ey = float(entrance['x']), float(entrance['y'])
        if entrance.get('z') is None:
            em = mapdata.cellmap(db, entrance['cell'])
            if not em.get('exists'):
                raise EditError('There is no place at the chosen entrance spot.')
            ez = mapdata.surface_z(db, em['refs'], em['interior'], ex, ey, None, 1.0, 'DOOR')
        else:
            ez = float(entrance['z'])
        erz = float(entrance.get('rz') or 0)
        # where you come out: copy the original door's arrival offset, turned to match the new door
        if orig_outside and front is not None:
            front_dest = struct.unpack_from('<6f', dict(front['subs'])['DODT'])
            op = orig_outside['pos']
            lx, ly = _rot2(front_dest[0] - op[0], front_dest[1] - op[1], -op[5])
            wx, wy = _rot2(lx, ly, erz)
            out_arrival = (ex + wx, ey + wy, ez + (front_dest[2] - op[2]), 0, 0, front_dest[5] - op[5] + erz)
        else:
            wx, wy = _rot2(0, -128, erz)
            out_arrival = (ex + wx, ey + wy, ez + 16, 0, 0, erz + math.pi)
        outside = (entrance['cell'], door_id, (ex, ey, ez, 0, 0, erz), out_arrival)

    # ---- write it all as one change
    hdr = []
    for t, d in header[0]:
        if t == 'NAME':
            d = zs(name)
        elif t == 'RGNN':
            continue
        hdr.append([t, b64(d)])
    if not any(t == 'NAME' for t, _d in hdr):
        hdr.insert(0, ['NAME', b64(zs(name))])
    c = p.cells[key] = {'flags': 0, 'header': hdr, 'refs': {}}
    mine = p.plugin.lower()
    for rk, subs in new_refs:
        if rk == front_k:
            subs = [(t, d) for t, d in subs if t not in DOOR_TAGS]
            if outside:
                oa = outside[3]
                subs = _insert_before_data(subs, [('DODT', struct.pack('<6f', *oa))] +
                                           ([('DNAM', zs(mapdata.cell_info(db, outside[0])['name']))]
                                            if not outside[0].startswith('#') else []))
        nk = p.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), subs)
    if outside:
        oc, _refs = editing._cell(db, outside[0])
        dsubs = set_ref_pos([('NAME', zs(outside[1]))], outside[2])
        dsubs = _insert_before_data(dsubs, [('DODT', struct.pack('<6f', *inside_arrival)), ('DNAM', zs(name))])
        nk = p.new_ref_key()
        editing._store(oc, nk, mine, int(nk.rsplit('|', 1)[1]), dsubs)
    if save:
        editing.commit(db, 'Created interior "%s" (copied from %s)%s' % (
            name, tinfo['name'] if tinfo else template_key,
            ' with its entrance in %s' % editing.cell_label(db, outside[0]) if outside else ''))
    return key


def _insert_before_data(subs, extra):
    out, done = [], False
    for t, d in subs:
        if t == 'DATA' and not done:
            out += extra
            done = True
        out.append((t, d))
    if not done:
        out += extra
    return out


# ===================================================================== NPCs
SERVICES = {
    'General goods': 0x4 | 0x8 | 0x10 | 0x20 | 0x40 | 0x80 | 0x100 | 0x200 | 0x400 | 0x2000,
    'Weapons & armor': 0x1 | 0x2 | 0x200 | 0x20000,
    'Alchemist': 0x10 | 0x100 | 0x2000,
    'Bookseller': 0x8,
    'Clothier': 0x4,
    'Enchanter & spells': 0x800 | 0x1000 | 0x8000 | 0x10000,
    'Trainer': 0x4000,
}
ROLES = {
    'townsperson': {'wander': 512, 'essential': False, 'gold': 25, 'alarm': 0, 'fight': 30},
    'quest': {'wander': 128, 'essential': True, 'gold': 50, 'alarm': 0, 'fight': 30},
    'merchant': {'wander': 0, 'essential': False, 'gold': 800, 'alarm': 0, 'fight': 30},
    'guard': {'wander': 256, 'essential': False, 'gold': 20, 'alarm': 100, 'fight': 30},
}


def options(db):
    races = sorted(({'id': db.recs[i][1], 'name': db.recs[i][2] or db.recs[i][1]} for i in _winners(db, 'RACE')),
                   key=lambda r: (r['id'].lower().startswith('t_'), r['name']))
    classes = sorted(({'id': db.recs[i][1], 'name': db.recs[i][2] or db.recs[i][1]} for i in _winners(db, 'CLAS')),
                     key=lambda r: r['name'].lower())
    factions = []
    for i in _winners(db, 'FACT'):
        ranks = [zstr(d) for t, d in iter_subrecords(_data(db, i)) if t == 'RNAM']
        factions.append({'id': db.recs[i][1], 'name': db.recs[i][2] or db.recs[i][1], 'ranks': ranks})
    factions.sort(key=lambda f: f['name'].lower())
    styles = {}
    for t in interior_templates(db):
        styles[t['style']] = styles.get(t['style'], 0) + 1
    # an example record of each book look and each container kind, so the form can show it in 3D
    book_examples = {}
    for kind, model in BOOK_KINDS.items():
        for i in _winners(db, 'BOOK'):
            if db.recs[i][5].lower() == model:
                book_examples[kind] = db.recs[i][1]
                break
    container_examples = {}
    for kind in CONTAINER_KINDS:
        base = _container_base(db, kind)
        if base is not None:
            container_examples[kind] = {'id': db.recs[base][1], 'name': db.recs[base][2] or kind}
    return {'races': races, 'classes': classes, 'factions': factions,
            'styles': sorted(styles.items(), key=lambda s: -s[1]),
            'services': list(SERVICES), 'roles': list(ROLES),
            'book_kinds': list(BOOK_KINDS), 'container_kinds': list(CONTAINER_KINDS),
            'book_examples': book_examples, 'container_examples': container_examples,
            'race_counts': _race_counts(db),
            'prefix': _prefix(db) if db.project else 'mod'}


def _race_counts(db):
    """How many of the game's people are of each race (the commonest makes the best default)."""
    counts = {}
    for i in _winners(db, 'NPC_'):
        for t, d in iter_subrecords(_data(db, i)):
            if t == 'RNAM':
                r = zstr(d).lower()
                counts[r] = counts.get(r, 0) + 1
                break
    return counts


_KINDS_OF_PEOPLE = {'slave', 'guard', 'prisoner', 'dreamer', 'sleeper', 'priest', 'priestess', 'trader', 'merchant', 'publican',
                    'pilgrim', 'warrior', 'mage', 'assassin', 'archer', 'noble', 'smith', 'farmer', 'miner', 'worker', 'servant',
                    'adventurer', 'bandit', 'outlaw', 'thief', 'witch', 'cultist', 'insane', 'ghost', 'spirit', 'hermit', 'beggar',
                    'sailor', 'scout', 'soldier', 'legionnaire', 'ordinator', 'armiger', 'monk', 'healer', 'child', 'villager',
                    'captain', 'commoner', 'citizen', 'hunter', 'fisherman', 'shipmaster', 'caravaner', 'guide', 'apprentice',
                    'scavenger', 'smuggler', 'raider', 'berserker', 'reaver', 'marauder', 'wanderer', 'drunk', 'madman',
                    'argonian', 'khajiit', 'nord', 'imperial', 'breton', 'redguard', 'orc', 'dunmer', 'altmer', 'bosmer', 'elf'}


def suggest_name(db, race, female, seed=None):
    """A name in the manner of the game's own people of that race and sex: a first name one of them
    has, and a family name another has (where the race uses them), in a pairing no one has yet."""
    race = (race or '').lower()
    global _names_cache
    if _names_cache is None or _names_cache[0] is not db.recs:
        _names_cache = (db.recs, {})
    people = _names_cache[1].get((race, female))
    if people is None:
        people = _names_cache[1][(race, female)] = _people_named(db, race, female)
    return _pick_name(people, random.Random(seed))


_names_cache = None


def _people_named(db, race, female):
    """The real names of the game's people of a race and sex (not the kinds: "Guard", "Dead Adventurer")."""
    people = []
    for i in _winners(db, 'NPC_'):
        info = _npc_info(db, i)
        if info['race'] != race or info['female'] != female:
            continue
        name = (db.recs[i][2] or '').strip()
        if not name or any(ch.isdigit() for ch in name):
            continue
        # (a mod's stand-ins and test people are no pattern to follow: "Im-Kur placeholder", "test npc")
        if any(w in name.lower() for w in ('placeholder', 'test', 'dummy', 'todo', 'unused', 'dead ', 'corpse')) or \
                not all(p[:1].isupper() and not p.endswith("'") for p in name.split()):
            continue
        # ("Insane Argonian", "Argonian Slave", "Khajiit Trader": a kind of person, not a name)
        words = {w.strip(".,'").lower() for w in name.split()}
        if words & _KINDS_OF_PEOPLE or race in words or (db.recs[i][2] or '').lower() == race:
            continue
        people.append(name)
    # a name several people share is a kind, not a name ("Guard", "Dead Adventurer", "Ordinator"): real names are one each
    shared = {n.lower() for n in people if sum(1 for m in people if m.lower() == n.lower()) > 1}
    return [n for n in people if n.lower() not in shared and "'s" not in n.lower()]


def _pick_name(people, rng):
    if not people:
        return ''
    taken = {n.lower() for n in people}
    # a race whose people mostly go by one name (Argonians, Khajiit) gets whole one-word names, not halves of
    # two-word ones ("Big Head" is no first name); a race with family names gets a first and a family name
    two = [n for n in people if len(n.split()) == 2]
    family_names = len(two) >= len(people) / 2
    if not family_names:
        ones = [n for n in people if len(n.split()) == 1] or people
        return rng.choice(ones)
    firsts = [n.split()[0] for n in two]
    lasts = [n.split()[1] for n in two]
    name = ''
    for _try in range(40):
        name = rng.choice(firsts) + ' ' + rng.choice(lasts)
        if name.lower() not in taken:
            break
    return name


def popular(db, types, limit=8):
    """The items of these record types the game uses most (placed in the most places, carried by the
    most people and lists): the usual things to start a new item from."""
    types = set(types or ())
    scored = []
    for (tag, key), lst in db.by_key.items():
        if tag not in types or not lst or lst[-1] in db.dead:
            continue
        i = lst[-1]
        r = db.recs[i]
        if not r[2]:
            continue
        n = len(db.used_in.get(key, ()))
        if n:
            scored.append((-n, r[2].lower(), i))
    scored.sort()
    return [{'i': i, 'id': db.recs[i][1], 'name': db.recs[i][2], 'type': db.recs[i][0], 'uses': -n}
            for n, _nm, i in scored[:limit]]


def _npc_info(db, i):
    s = {}
    items = []
    for t, d in iter_subrecords(_data(db, i)):
        if t == 'NPCO' and len(d) >= 36:
            items.append((struct.unpack_from('<i', d)[0], zstr(d[4:36])))
        elif t not in s:
            s[t] = d
    flags = struct.unpack_from('<i', s.get('FLAG', b'\0\0\0\0'))[0]
    return {'race': zstr(s.get('RNAM', b'')).lower(), 'class': zstr(s.get('CNAM', b'')).lower(),
            'female': bool(flags & 1), 'script': bool(s.get('SCRI')), 'items': items, 'flags': flags}


def _pick_template(db, race, female, cls, want_armor):
    best, bs = None, -1
    for i in _winners(db, 'NPC_'):
        info = _npc_info(db, i)
        if info['race'] != race.lower() or info['female'] != female:
            continue
        score = 10 if info['class'] == cls.lower() else 0
        score += 0 if info['script'] else 3
        kinds = [db.recs[db.resolve_id(it)][0] if db.resolve_id(it) is not None else '' for _n, it in info['items']]
        score += min(4, kinds.count('CLOT'))
        if not want_armor:
            score += sum(1 for _n, it in info['items'] if it.lower().startswith('common_'))
        if want_armor:
            score += 2 * min(4, kinds.count('ARMO')) + (2 if 'WEAP' in kinds else 0)
        if score > bs:
            best, bs = (i, info), score
    return best


def _pick_body(db, race_id, race_name, female, part, seed):
    names = {race_id.lower(), (race_name or '').lower()}
    cands = []
    for i in _winners(db, 'BODY'):
        s = dict(iter_subrecords(_data(db, i)))
        by = s.get('BYDT', b'\0\0\0\0')
        if len(by) < 4 or by[0] != part or by[1] != 0 or by[3] != 0 or bool(by[2] & 1) != female:
            continue
        if zstr(s.get('FNAM', b'')).lower() in names:
            cands.append(db.recs[i][1])
    if not cands:
        return ''
    cands.sort()
    return random.Random(seed).choice(cands)


def create_npc(db, o):
    editing._require_project(db)
    role = o.get('role') or 'townsperson'
    rd = ROLES.get(role, ROLES['townsperson'])
    name = (o.get('name') or '').strip()
    if not name:
        raise EditError('Give the NPC a name.')
    new_id = _check_id(db, 'NPC_', o.get('id') or suggest_id(db, _prefix(db), name))
    race_i = db.resolve_id(o.get('race') or 'Dark Elf')
    if race_i is None or db.recs[race_i][0] != 'RACE':
        raise EditError('Unknown race.')
    race_id, race_name = db.recs[race_i][1], db.recs[race_i][2]
    cls = o.get('class') or ('Guard' if role == 'guard' else 'Commoner')
    cls_i = db.resolve_id(cls)
    if cls_i is None or db.recs[cls_i][0] != 'CLAS':
        raise EditError('Unknown class "%s".' % cls)
    cls = db.recs[cls_i][1]
    female = o.get('sex') == 'female'
    level = max(1, min(100, int(o.get('level') or 5)))
    faction, rank = (o.get('faction') or '').strip(), int(o.get('rank') or 0)
    if faction and db.resolve_id(faction) is None:
        raise EditError('Unknown faction "%s".' % faction)
    seed = '%s|%s' % (new_id, o.get('look') or 0)
    head = _pick_body(db, race_id, race_name, female, 0, seed)
    hair = _pick_body(db, race_id, race_name, female, 1, seed + 'h')
    tpl = _pick_template(db, race_id, female, cls, role == 'guard')
    items, slots = [], set()
    if tpl:
        for n, it in tpl[1]['items']:
            ri = db.resolve_id(it)
            if ri is None:
                continue
            tag = db.recs[ri][0]
            if tag == 'CLOT':
                # one of each worn piece: pants, shoes, shirt, belt, robe, skirt
                ctype = next((struct.unpack_from('<i', d)[0] for t, d in iter_subrecords(_data(db, ri))
                              if t == 'CTDT'), -1)
                if ctype in (0, 1, 2, 3, 4, 7) and ctype not in slots:
                    slots.add(ctype)
                    items.append((1, it))
            elif role == 'guard' and tag in ('ARMO', 'WEAP'):
                items.append((1, it))
    for ctype, fallback in ((2, 'common_shirt_01'), (0, 'common_pants_01'), (1, 'common_shoes_01')):
        covered = slots & ({0, 4, 7} if ctype == 0 else {ctype})
        if not covered and db.resolve_id(fallback) is not None:
            items.append((1, fallback))
    essential = o.get('essential')
    essential = rd['essential'] if essential is None else bool(essential)
    flags = 0x10 | 0x8 | (1 if female else 0) | (2 if essential else 0)
    services = SERVICES.get(o.get('services') or 'General goods', 0) if role == 'merchant' else 0
    gold = int(o.get('gold') if o.get('gold') not in (None, '') else rd['gold'])
    subs = [('NAME', zs(new_id)), ('FNAM', zs(name)), ('RNAM', zs(race_id)), ('CNAM', zs(cls)),
            ('ANAM', zs(faction)), ('BNAM', zs(head)), ('KNAM', zs(hair)),
            ('NPDT', struct.pack('<hBBBxxxi', level, 50, 0, max(0, min(9, rank)) if faction else 0, gold)),
            ('FLAG', struct.pack('<i', flags))]
    for n, it in items[:12]:
        subs.append(('NPCO', struct.pack('<i', n) + it.encode(ENC, 'replace')[:31].ljust(32, b'\0')))
    subs.append(('AIDT', struct.pack('<BBBBBBBBi', 30, 0, rd['fight'], 30, rd['alarm'], 0, 0, 0, services)))
    subs.append(('AI_W', struct.pack('<hhB8BB', rd['wander'], 5, 0, 60, 20, 20, 20, 0, 0, 0, 0, 1)))
    db.project.set_record('NPC_', new_id.lower(), 0, join_subs(subs), created=True)
    placed = _maybe_place(db, new_id, o.get('place'), commit_note='Created %s "%s" (%s %s %s)' % (
        {'townsperson': 'townsperson', 'quest': 'quest character', 'merchant': 'merchant',
         'guard': 'guard'}.get(role, 'NPC'), name, 'female' if female else 'male', race_name, cls))
    return {'id': new_id, 'i': db.overlay.get(('NPC_', new_id.lower())), 'placed': placed}


def _maybe_place(db, rec_id, place, commit_note, extra_subs=None):
    """Commit the new record, and place it in one go if a spot was given (one undo step)."""
    if not place or not place.get('cell'):
        editing.commit(db, commit_note)
        return None
    db.sync_project()           # the new record must exist before it can be placed
    z = None if place.get('z') is None else float(place['z'])
    if z is not None and place.get('surface'):
        # a spot clicked in the 3D view: the thing's bottom rests on it (as a drop from the palette does)
        import mapdata
        b = mapdata.object_bounds(db, db.resolve_id(rec_id))
        z -= b[2] if b else 0.0
    rk = editing.place_ref(db, place['cell'], rec_id,
                           [float(place['x']), float(place['y']), z, 0, 0,
                            float(place.get('rz') or 0)], 1.0, place.get('cut'), extra_subs=extra_subs,
                           note=commit_note)
    return {'cell': place['cell'], 'ref': rk}


# ===================================================================== books & notes
BOOK_KINDS = {
    'Note': 'm\\text_note_01.nif',
    'Letter': 'm\\text_parchment_02.nif',
    'Scroll': 'm\\text_scroll_01.nif',
    'Book': 'm\\text_octavo_06.nif',
    'Large book': 'm\\text_quarto_03.nif',
}


def _book_look(db, model):
    for i in _winners(db, 'BOOK'):
        if db.recs[i][5].lower() != model:
            continue
        s = {}
        for t, d in iter_subrecords(_data(db, i)):
            s.setdefault(t, d)
        if 'BKDT' in s and 'ITEX' in s and 'SCRI' not in s and 'ENAM' not in s:
            w, v, scroll, _skill, _ench = struct.unpack_from('<fiiii', s['BKDT'])
            return s['MODL'], s['ITEX'], w, v, scroll
    return None


def book_html(text):
    esc = (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    paras = [p.strip().replace('\n', '<BR>') for p in re.split(r'\n\s*\n', esc.strip()) if p.strip()]
    return ('<DIV ALIGN="LEFT"><FONT COLOR="000000" SIZE="3" FACE="Magic Cards"><BR>' +
            '<BR><BR>'.join(paras) + '<BR>\r\n')


def create_book(db, o):
    editing._require_project(db)
    title = (o.get('title') or '').strip()
    if not title:
        raise EditError('Give it a title.')
    kind = o.get('kind') or 'Note'
    look = _book_look(db, BOOK_KINDS.get(kind, BOOK_KINDS['Note']))
    if not look:
        raise EditError('No "%s" model found in your load order.' % kind)
    model, icon, weight, value, scroll = look
    new_id = _check_id(db, 'BOOK', o.get('id') or suggest_id(db, _prefix(db), title))
    value = int(o.get('value') if o.get('value') not in (None, '') else value)
    subs = [('NAME', zs(new_id)), ('MODL', model), ('FNAM', zs(title[:31])),
            ('BKDT', struct.pack('<fiiii', weight, value, scroll, -1, 0)), ('ITEX', icon),
            ('TEXT', book_html(o.get('text')).encode(ENC, 'replace'))]
    db.project.set_record('BOOK', new_id.lower(), 0, join_subs(subs), created=True)
    gave = ''
    if (o.get('give_to') or '').strip():
        import items
        gave = items._give(db, o['give_to'], new_id, 'item')       # (into a character's or container's inventory)
    placed = _maybe_place(db, new_id, None if gave else o.get('place'),
                          'Created %s "%s"%s' % (kind.lower(), title, (' and gave it to ' + gave) if gave else ''))
    return {'id': new_id, 'i': db.overlay.get(('BOOK', new_id.lower())), 'placed': placed, 'given': gave}


# ===================================================================== containers
CONTAINER_KINDS = {
    'Chest': ['com_chest_02', 'com_chest_01', 'chest'],
    'Crate': ['crate_01', 'crate_02', 'crate'],
    'Barrel': ['barrel_01', 'barrel_02', 'barrel'],
    'Sack': ['com_sack_01', 'com_sack_02', 'sack'],
    'Basket': ['com_basket_01', 'basket'],
    'Urn': ['urn_01', 'urn'],
    'Cupboard': ['furn_com_cupboard', 'cupboard', 'closet'],
    'Desk': ['furn_com_desk', 'desk'],
}


def _container_base(db, kind):
    words = CONTAINER_KINDS.get(kind, CONTAINER_KINDS['Chest'])
    for w in words[:-1]:
        lst = db.by_key.get(('CONT', w))
        if lst:
            return lst[-1]
    best, bn = None, 1e9
    for i in _winners(db, 'CONT'):
        rid = db.recs[i][1].lower()
        if words[-1] not in rid or 'npc' in rid:
            continue
        s = list(iter_subrecords(_data(db, i)))
        if any(t == 'SCRI' for t, _d in s):
            continue
        n = sum(1 for t, _d in s if t == 'NPCO')
        flag = next((struct.unpack_from('<i', d)[0] for t, d in s if t == 'FLAG'), 0)
        if flag & 3:
            continue
        if n < bn:
            best, bn = i, n
    return best


def create_container(db, o):
    editing._require_project(db)
    kind = o.get('kind') or 'Chest'
    base = _container_base(db, kind)
    if base is None:
        raise EditError('No "%s" container found in your load order.' % kind)
    name = (o.get('name') or db.recs[base][2] or kind).strip()
    new_id = _check_id(db, 'CONT', o.get('id') or suggest_id(db, _prefix(db), name))
    subs = []
    for t, d in iter_subrecords(_data(db, base)):
        if t in ('NPCO', 'SCRI'):
            continue
        if t == 'NAME':
            d = zs(new_id)
        elif t == 'FNAM':
            d = zs(name[:31])
        elif t == 'FLAG':
            d = struct.pack('<i', struct.unpack_from('<i', d)[0] & ~3)    # not organic, doesn't respawn
        subs.append((t, bytes(d)))
    for it in (o.get('items') or [])[:40]:
        iid, n = (it.get('id') or '').strip(), int(it.get('count') or 1)
        if not iid:
            continue
        if db.resolve_id(iid) is None:
            raise EditError('No item called "%s".' % iid)
        subs.append(('NPCO', struct.pack('<i', n) + iid.encode(ENC, 'replace')[:31].ljust(32, b'\0')))
    db.project.set_record('CONT', new_id.lower(), 0, join_subs(subs), created=True)
    extra = []
    lock = int(o.get('lock') or 0)
    if lock > 0:
        extra.append(('FLTV', struct.pack('<i', min(100, lock))))
    if (o.get('owner') or '').strip():
        if db.resolve_id(o['owner'].strip()) is None:
            raise EditError('No one called "%s" to own it.' % o['owner'])
        extra.append(('ANAM', zs(o['owner'].strip())))
    placed = _maybe_place(db, new_id, o.get('place'), 'Created %s "%s" with %d kinds of items' % (
        kind.lower(), name, len(o.get('items') or [])), extra_subs=extra or None)
    return {'id': new_id, 'i': db.overlay.get(('CONT', new_id.lower())), 'placed': placed}
