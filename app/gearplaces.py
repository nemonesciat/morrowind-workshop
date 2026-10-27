"""Where the game puts its weapons and armour, so a new piece can go where the game would put one like it
(packaging/nexus/weapons-armour-plan.md, stage 2: "into the world, the game's way").

Read from the load order (the mod being made left out), in a second or two, kept while the records stay:
- the random lists (LEVI) that hold each piece, and at what level;
- the people (NPC_) who carry it, with their class, race and faction, and whether they sell it (a smith's or a
  trader's stock: weapons or armour in their services);
- the containers (CONT) that hold it outright.

The game's lists come in three kinds, and a new piece joins each the way the game's own do:
- a material's list (random_steel_weapon: steel things of many types): only that material;
- a type's list at levels (l_n_wpn_melee_long blade: long blades of many materials): any material within the
  list's own range of tiers, at the level its tier would have there;
- a list of a culture or a place (T_MwDe_Random_Weapons): only where a piece of the same type and material is.

propose() says where a piece of this type and material would go; measure() takes each of the game's own pieces
out in turn and checks whether it would be sent back where the game has it."""
import bisect
import math
import struct
from collections import Counter, defaultdict

import gearsurvey
from esm import iter_subrecords, zstr

SELLS = 0x1 | 0x2          # (the services that sell weapons and armour)
THEME = 0.6                # (a list is a material's or a type's when this share of its gear is of one)
USE_W = 0.6                # (how much a list's wide use counts in its rank: measured, see measure_top)
_cache = {}


def _live(db, tag):
    proj = getattr(db, 'proj_pidx', None)
    for (tg, _k), lst in db.by_key.items():
        if tg != tag:
            continue
        lv = [v for v in lst if v not in db.dead and (proj is None or db.recs[v][3] != proj)]
        if lv:
            yield lv[-1]


def _subs(db, ri):
    r = db.recs[ri]
    return iter_subrecords(db.files[r[3]].record_at(r[4])[2])


def survey(db):
    """{'gear': {id: piece}, 'lists': {list id: {'id', 'entries': [(gear id, level)], 'others': n}},
    'in_lists': {gear id: [(list id, level)]}, 'people': {gear id: [(npc id, class, race, faction, sells)]},
    'containers': {gear id: [container id]}, 'tiers': {material: 0..1}}."""
    if _cache.get('recs') is db.recs:
        return _cache['out']
    gs = gearsurvey.survey(db)
    tiers = gs['tiers']
    gear = {}
    for tag in ('WEAP', 'ARMO'):
        for ri in _live(db, tag):
            it = gearsurvey._read(db, ri)
            if it:
                it['tier'] = tiers.get(it['mat'])
                gear[db.recs[ri][1].lower()] = it
    lists, in_lists = {}, defaultdict(list)
    users = Counter()             # (how many people, containers and other lists draw on each list)
    for ri in _live(db, 'LEVI'):
        lid = db.recs[ri][1]
        ent, others, cur = [], 0, None
        for t, d in _subs(db, ri):
            if t == 'INAM':
                cur = zstr(d).lower()
            elif t == 'INTV' and cur is not None:
                lv = struct.unpack_from('<h', bytes(d))[0] if len(d) >= 2 else 1
                if cur in gear:
                    ent.append((cur, lv))
                    in_lists[cur].append((lid, lv))
                else:
                    others += 1
                    users[cur] += 1
                cur = None
        if ent:
            lists[lid] = {'id': lid, 'entries': ent, 'others': others}
    people, containers = defaultdict(list), defaultdict(list)
    for ri in _live(db, 'NPC_'):
        cls = race = fac = ''
        serv, items = 0, []
        for t, d in _subs(db, ri):
            if t == 'CNAM':
                cls = zstr(d)
            elif t == 'RNAM':
                race = zstr(d)
            elif t == 'ANAM':
                fac = zstr(d)
            elif t == 'AIDT' and len(d) >= 12:
                serv = struct.unpack_from('<i', bytes(d), 8)[0]
            elif t == 'NPCO' and len(d) >= 36:
                items.append(zstr(bytes(d)[4:36]).lower())
        for iid in items:
            if iid in gear:
                people[iid].append((db.recs[ri][1], cls, race, fac, bool(serv & SELLS)))
            else:
                users[iid] += 1
    for ri in _live(db, 'CONT'):
        for t, d in _subs(db, ri):
            if t == 'NPCO' and len(d) >= 36:
                iid = zstr(bytes(d)[4:36]).lower()
                if iid in gear:
                    containers[iid].append(db.recs[ri][1])
                else:
                    users[iid] += 1
    for lid, lst in lists.items():
        lst['users'] = users.get(lid.lower(), 0)
    out = {'gear': gear, 'lists': lists, 'in_lists': dict(in_lists), 'people': dict(people),
           'containers': dict(containers), 'tiers': tiers}
    _cache.update(recs=db.recs, out=out)
    return out


def _list_kind(s, lst, skip=None):
    """What a list is about, from its gear (the piece being measured left out): ('material', m), ('type',
    (kind, type)) or ('mixed', None), with its entries."""
    ent = [(g, lv) for g, lv in lst['entries'] if g != skip]
    if len(ent) < 2:
        return None, ent
    gear = s['gear']
    mats = Counter(gear[g]['mat'] for g, _lv in ent if gear[g]['mat'])
    types = Counter((gear[g]['kind'], gear[g]['type']) for g, _lv in ent)
    n = float(len(ent))
    if mats:
        m, c = mats.most_common(1)[0]
        if c / n >= THEME and len(types) >= 2:
            return ('material', m), ent
    t, c = types.most_common(1)[0]
    if c / n >= THEME and len(mats) >= 2:
        return ('type', t), ent
    return ('mixed', None), ent


def _level_at(s, ent, tier):
    """The level a piece of this tier would have in a list: the levels of the list's pieces by their tier,
    read off where this tier falls (the nearest when outside them)."""
    pts = sorted((s['gear'][g]['tier'], lv) for g, lv in ent if s['gear'][g]['tier'] is not None)
    if not pts or tier is None:
        return 1
    xs = [p[0] for p in pts]
    i = bisect.bisect_left(xs, tier)
    if i <= 0:
        return pts[0][1]
    if i >= len(pts):
        return pts[-1][1]
    (x0, y0), (x1, y1) = pts[i - 1], pts[i]
    f = 0 if x1 == x0 else (tier - x0) / (x1 - x0)
    return int(round(y0 + (y1 - y0) * f))


def tier_of(db, mat=None, between=None):
    """A material's tier (0 the cheapest to 1), or a new material's between two: f of the way from a to b."""
    t = survey(db)['tiers']
    if between:
        a, b, f = between
        if a in t and b in t:
            return t[a] + (t[b] - t[a]) * float(f)
    return t.get(mat)


def propose_lists(db, kind, ty, mat, skip=None, enchanted=False, tier=None):
    """The game's lists a piece of this kind, type and material would join, the likeliest first: [{'list',
    'level', 'why', 'score'}]. Measured on the game's own pieces (measure()): the lists of mostly enchanted
    things take a plain piece one time in eighteen, so a plain piece leaves them out, an enchanted one keeps to
    them; a list that holds this type (a material's) or this material (a type's) already comes first."""
    s = survey(db)
    tier = s['tiers'].get(mat) if tier is None else tier
    out = []
    for lid, lst in s['lists'].items():
        lk, ent = _list_kind(s, lst, skip)
        if lk is None:
            continue
        gear = s['gear']
        if (sum(1 for g, _lv in ent if gear[g]['enchanted']) >= 0.5 * len(ent)) != bool(enchanted):
            continue
        same_kind = [g for g, _lv in ent if gear[g]['kind'] == kind]
        if not same_kind:
            continue
        if lk[0] == 'material':
            if lk[1] != mat:
                continue
            # (a material's list of this kind: weapons for a weapon, armour for armour)
            if len(same_kind) / float(len(ent)) < 0.5:
                continue
            same_t = [(g, l) for g, l in ent if gear[g]['type'] == ty]
            lv = _level_at(s, same_t or ent, tier)
            out.append({'list': lid, 'level': lv, 'why': 'the game\'s %s list' % mat, 'score': 2 + len(same_t) / float(len(ent))})
        elif lk[0] == 'type':
            if lk[1] != (kind, ty) or tier is None:
                continue
            tt = [gear[g]['tier'] for g, _lv in ent if gear[g]['tier'] is not None]
            if not tt or not (min(tt) - 0.05 <= tier <= max(tt) + 0.05):
                continue
            same_m = sum(1 for g, _lv in ent if gear[g]['mat'] == mat)
            out.append({'list': lid, 'level': _level_at(s, ent, tier), 'why': 'a list of %s by level' % gearsurvey.LABEL.get(ty, ty).lower(),
                        'score': 2 + same_m / float(len(ent))})
        else:
            hits = [(g, l) for g, l in ent if gear[g]['kind'] == kind and gear[g]['type'] == ty and gear[g]['mat'] == mat]
            if hits:
                out.append({'list': lid, 'level': sorted(l for _g, l in hits)[len(hits) // 2], 'why': 'holds %s of %s already' % (gearsurvey.LABEL.get(ty, ty).lower(), mat),
                            'score': 1 + len(hits) / float(len(ent))})
    # (the widely used lists first: the ones many people, containers and lists draw on, where the game's own
    # pieces mostly are, before a guard troop's or a vault's own)
    for x in out:
        x['users'] = s['lists'][x['list']].get('users', 0)
        x['score'] = round(x['score'] + USE_W * math.log1p(x['users']), 3)
    out.sort(key=lambda x: -x['score'])
    return out


def _carriers(s, kind, ty, mat, skip=None):
    """The people who carry pieces of this kind, type and material (the piece measured left out)."""
    out = []
    for g, ppl in s['people'].items():
        if g == skip:
            continue
        p = s['gear'][g]
        if p['kind'] == kind and p['type'] == ty and p['mat'] == mat:
            out.extend(ppl)
    return out


def propose_people(db, kind, ty, mat, skip=None, top=8):
    """The classes whose people carry pieces like this, most first, and the merchants who sell them:
    {'classes': [(class, n)], 'merchants': [(npc id, class)]}."""
    s = survey(db)
    car = _carriers(s, kind, ty, mat, skip)
    cls = Counter(c[1] for c in car if not c[4])
    sellers = []
    seen = set()
    for c in car:
        if c[4] and c[0] not in seen:
            seen.add(c[0])
            sellers.append((c[0], c[1]))
    return {'classes': cls.most_common(top), 'merchants': sellers}


# (a list named for a people, a faction, a troop or a place is for them, not for anyone: offered unticked)
FOR_SOME = ('guard', 'hla', 'ind', 'redoran', 'red_', 'telv', 'tel_', 'ashl', 'ashlander', 'smuggl', 'ordin', 'legion',
            'nord', 'orc', 'khaj', 'argon', 'bandit', 'vault', 'akavir', 'redguard', 'riekling', 'reaver', 'necrom',
            'golden', 'saint', 'dremora', 'mage', 'thief', 'fighter', 'temple', 'imperial', 'dunmer', 'breton', 'bosmer',
            'altmer', 'cult', 'vamp', 'skaal', 'rank', 'quest', 'special', 'boss', 'enchant', 'sailor', 'pirate', 'clothing', 'hats')


def _item(db, item_id, mat=None):
    ri = db.resolve_id(item_id)
    if ri is None or db.recs[ri][0] not in ('WEAP', 'ARMO'):
        raise ValueError('That is not a weapon or an armour piece: %s' % item_id)
    it = gearsurvey._read(db, ri)
    if not it:
        raise ValueError('That is not a weapon or an armour piece: %s' % item_id)
    if mat:
        it['mat'] = mat            # (what it was forged as: "Sunsteel" is not steel because its name says so)
    return it


def _holds(db, rec_id, rid, sub):
    """Does the record as it stands now (your mod's version, when it has one) hold this item: a list's entries
    (INAM) or a person's belongings (NPCO)?"""
    ri = db.resolve_id(rec_id)
    if ri is None:
        return False
    low = rid.lower()
    for t, d in _subs(db, ri):
        if t == sub and (zstr(bytes(d)) if sub == 'INAM' else zstr(bytes(d)[4:36])).lower() == low:
            return True
    return False


def places(db, item_id, mat=None, between=None):
    """Where the game would put this piece, in groups for the Forge's "Into the world": {'item', 'general':
    [list offers, ticked], 'some': [list offers for a people or faction, unticked], 'carriers': [people who carry
    a piece like it: theirs can be swapped for this], 'classes': [(class, n)], 'sellers': [merchants who sell
    pieces like it]}. Each offer says why, and the list's level for this piece."""
    s = survey(db)
    # (a new material between two: the lists of the nearer one, at the levels of its own tier between them)
    if between:
        a, b, f = between[0], between[1], float(between[2])
        mat = a if f <= 0.5 else b         # (halfway: the cheaper one's, rather than over-placing it)
    it = _item(db, item_id, mat)
    kind, ty, mat = it['kind'], it['type'], it['mat']
    if not mat:
        # (nothing says what it is made of: asked, with the game's materials to pick from)
        return {'item': {'id': item_id, 'name': it['name'], 'kind': kind, 'type': ty, 'type_label': gearsurvey.LABEL.get(ty, ty),
                         'material': None, 'enchanted': it['enchanted']},
                'need_material': True, 'materials': sorted(s['tiers'], key=lambda m: s['tiers'][m])}
    tier = tier_of(db, mat, between)
    have = {l.lower() for l, _lv in s['in_lists'].get(item_id.lower(), [])}
    general, some = [], []
    for x in propose_lists(db, kind, ty, mat, skip=item_id.lower(), enchanted=it['enchanted'], tier=tier):
        lri = db.resolve_id(x['list'])
        x['src'] = db.plugins[db.recs[lri][3]]['name'] if lri is not None else ''
        x['in'] = x['list'].lower() in have or _holds(db, x['list'], item_id, 'INAM')
        low = x['list'].lower()
        (some if any(t in low for t in FOR_SOME) or x['why'].startswith('holds') else general).append(x)
    if between:
        # (a new material between two: the lists by level first, where its own tier gives it its level; a plain
        # material's list hands its pieces out at any level, and would give this one away with the cheaper ones)
        for x in general:
            if x['why'].startswith('a list of'):
                x['score'] = round(x['score'] + 1.5, 3)
        general.sort(key=lambda x: -x['score'])
    # people who carry a piece of this type and material: theirs swapped for this one (a guard's steel sword for
    # your steel sword), the merchants among them selling it besides
    car, sellers, seen = [], [], set()
    for g, ppl in s['people'].items():
        p = s['gear'][g]
        if g == item_id.lower() or p['kind'] != kind or p['type'] != ty or p['mat'] != mat or p['enchanted']:
            continue
        for npc_id, cls, race, fac, sells in ppl:
            if npc_id in seen:
                continue
            seen.add(npc_id)
            ni = db.resolve_id(npc_id)
            if _holds(db, npc_id, item_id, 'NPCO'):
                continue                  # (carries or sells this one already)
            row = {'npc': npc_id, 'name': (db.recs[ni][2] if ni is not None else '') or npc_id, 'cls': cls, 'race': race,
                   'faction': fac, 'theirs': g, 'theirs_name': s['gear'][g]['name'] or g}
            (sellers if sells else car).append(row)
    cls = Counter(c['cls'] for c in car)
    return {'item': {'id': item_id, 'name': it['name'], 'kind': kind, 'type': ty, 'type_label': gearsurvey.LABEL.get(ty, ty),
                     'material': mat, 'between': list(between) if between else None, 'enchanted': it['enchanted']},
            'general': general[:12], 'some': some[:24], 'carriers': car, 'classes': cls.most_common(10), 'sellers': sellers}


def place(db, item_id, lists=(), swaps=(), sells=()):
    """Put the piece into the world as chosen in "Into the world", as one change (one Undo): into each list at
    its level; in place of the like piece a person carries; into a merchant's stock, restocked like the game's.
    lists: [{'list', 'level'}]; swaps: [{'npc', 'theirs'}]; sells: [npc id]."""
    import editing
    it = _item(db, item_id)
    rid = db.recs[db.resolve_id(item_id)][1]
    it['name'] = it['name'] or rid
    n = _put_lists(db, rid, lists)
    by_npc = defaultdict(list)
    for x in swaps:
        by_npc[x['npc']].append((rid, x.get('theirs')))
    n += _put_people(db, by_npc)
    n += _put_stock(db, sells, [rid])
    if n > 1:
        editing.fold(db, n, 'Put %s into the world: %s' % (it['name'] or rid, ', '.join(w for w in (
            '%d list%s' % (len(lists), '' if len(lists) == 1 else 's') if lists else '',
            '%d %s' % (len(swaps), 'person' if len(swaps) == 1 else 'people') if swaps else '',
            '%d merchant%s' % (len(sells), '' if len(sells) == 1 else 's') if sells else '') if w)))
    _cache.clear()
    return {'changed': n}


def _put_lists(db, rid, lists):
    """Into each list at its level (one save each); how many lists changed."""
    import levlists
    n = 0
    for x in lists:
        o = levlists.read(db, x['list'])
        if any(e['id'].lower() == rid.lower() for e in o['entries']):
            continue
        o['entries'].append({'id': rid, 'level': max(1, int(x.get('level') or 1))})
        levlists.save(db, x['list'], o)
        n += 1
    return n


def _put_people(db, by_npc):
    """Each person's like pieces swapped for these, all of theirs at once (one save a person): by_npc {npc id:
    [(new id, their piece id)]}; how many people changed."""
    import npc as npcmod
    n = 0
    for npc_id, pairs in by_npc.items():
        o = npcmod.read(db, npc_id)
        for rid, theirs in pairs:
            if any(e['id'].lower() == rid.lower() for e in o['items']):
                continue
            hit = next((e for e in o['items'] if e['id'].lower() == (theirs or '').lower()), None)
            if hit:
                hit['id'] = rid
            else:
                o['items'].append({'id': rid, 'count': 1, 'restock': False})
        npcmod.save(db, npc_id, o)
        n += 1
    return n


def _put_stock(db, sellers, rids):
    """Into each merchant's stock, restocked as the game's are (one save a merchant); how many changed."""
    import npc as npcmod
    n = 0
    for npc_id in sellers:
        o = npcmod.read(db, npc_id)
        new = [r for r in rids if not any(e['id'].lower() == r.lower() for e in o['items'])]
        if new:
            o['items'].extend({'id': r, 'count': 1, 'restock': True} for r in new)
            npcmod.save(db, npc_id, o)
            n += 1
    return n


def set_places(db, ids, mat=None, between=None):
    """Where a whole set would go, for "Into the world"'s whole-set view: {'pieces': [{'item', 'general'}] (each
    piece's own lists), 'classes': [{'cls', 'people', 'slots'}] (classes whose people carry pieces like the set's,
    with how many of the set's slots the best-matched of them carry), 'sellers': [merchants who sell pieces like
    any of the set's]}."""
    pieces, car, sellers = [], defaultdict(dict), {}
    for iid in ids:
        p = places(db, iid, mat, between)
        if p.get('need_material'):
            continue
        pieces.append({'item': p['item'], 'general': p['general'][:8]})
        for c in p['carriers']:
            car[c['npc']].setdefault('cls', c['cls'])
            car[c['npc']].setdefault('name', c['name'])
            car[c['npc']].setdefault('pairs', []).append((p['item']['id'], c['theirs']))
        for sl in p['sellers']:
            sellers.setdefault(sl['npc'], sl)
    by_cls = defaultdict(list)
    for npc_id, c in car.items():
        by_cls[c['cls']].append(len(c['pairs']))
    classes = sorted(({'cls': k, 'people': len(v), 'slots': max(v)} for k, v in by_cls.items()), key=lambda x: (-x['people'], -x['slots']))
    # (the merchants who sell the most kinds of the set's pieces first)
    return {'pieces': pieces, 'classes': classes[:10], 'sellers': list(sellers.values())}


def place_set(db, ids, lists, classes, sells, mat=None, between=None, name=''):
    """The whole set into the world as one change (one Undo): lists {piece id: [{'list', 'level'}]}; classes
    [{'cls', 'n'}]: in each, the n people who carry the most pieces like the set's wear all of it (each of their
    like pieces swapped); sells: merchants who stock every piece."""
    import editing
    rids = [db.recs[db.resolve_id(i)][1] for i in ids if db.resolve_id(i) is not None]
    n = 0
    for rid in rids:
        n += _put_lists(db, rid, (lists or {}).get(rid) or (lists or {}).get(rid.lower()) or [])
    by_npc = {}
    if classes:
        car = defaultdict(lambda: {'pairs': []})
        for iid in rids:
            p = places(db, iid, mat, between)
            for c in p.get('carriers', []):
                car[c['npc']]['cls'] = c['cls']
                car[c['npc']]['pairs'].append((iid, c['theirs']))
        for want in classes:
            of = sorted((k for k, c in car.items() if c.get('cls') == want['cls']), key=lambda k: -len(car[k]['pairs']))
            for k in of[:max(0, int(want.get('n') or 0))]:
                by_npc[k] = car[k]['pairs']
    n_people = _put_people(db, by_npc)
    n_stock = _put_stock(db, sells or [], rids)
    n += n_people + n_stock
    n_lists = n - n_people - n_stock
    if n > 1:
        editing.fold(db, n, 'Put the %s set into the world: %s' % (name or 'new', ', '.join(w for w in (
            '%d list entr%s' % (n_lists, 'y' if n_lists == 1 else 'ies') if n_lists else '',
            '%d %s wearing it' % (n_people, 'person' if n_people == 1 else 'people') if n_people else '',
            '%d merchant%s' % (n_stock, '' if n_stock == 1 else 's') if n_stock else '') if w)))
    _cache.clear()
    return {'changed': n, 'lists': n_lists, 'people': n_people, 'merchants': n_stock}


def measure_top(db, ks=(3, 5, 8)):
    """The lists offered first, as the Forge would offer them ticked: of a piece's top k, how many are lists it is
    really in, and how many of its real lists are among them."""
    s = survey(db)
    pieces = [g for g, p in s['gear'].items() if p['mat'] and not p['enchanted'] and g in s['in_lists']]
    out = {}
    props = {}
    for g in pieces:
        p = s['gear'][g]
        props[g] = [x['list'] for x in propose_lists(db, p['kind'], p['type'], p['mat'], skip=g)]
    for k in ks:
        hit = prop = real_n = anyhit = 0
        for g in pieces:
            real = {l for l, _lv in s['in_lists'][g]}
            top = set(props[g][:k])
            h = len(real & top)
            hit += h; prop += len(top); real_n += len(real); anyhit += h > 0
        out[k] = {'right': round(hit / float(max(1, prop)), 3), 'found': round(hit / float(max(1, real_n)), 3),
                  'one_real': round(anyhit / float(max(1, len(pieces))), 3)}     # (pieces with a real list among them)
    return out


def measure(db, limit=None):
    """Each of the game's plain pieces with a material, taken out in turn: are the lists it would be sent to
    the ones it is in, and at about the same level; are the classes it would go to the ones that carry it?"""
    s = survey(db)
    pieces = [g for g, p in s['gear'].items() if p['mat'] and not p['enchanted'] and (g in s['in_lists'] or g in s['people'])]
    if limit:
        pieces = pieces[:limit]
    lst_real = lst_hit = lst_prop = lst_right = 0
    lv_err = []
    by_kind = Counter()
    cls_real = cls_hit = 0
    for g in pieces:
        p = s['gear'][g]
        if g in s['in_lists']:
            real = {l for l, _lv in s['in_lists'][g]}
            prop = propose_lists(db, p['kind'], p['type'], p['mat'], skip=g)
            pl = {x['list'] for x in prop}
            lst_real += len(real)
            lst_hit += len(real & pl)
            lst_prop += len(pl)
            lst_right += len(real & pl)
            lvl = dict(s['in_lists'][g])
            for x in prop:
                if x['list'] in lvl:
                    lv_err.append(abs(x['level'] - lvl[x['list']]))
                    by_kind[x['why'].split(' ')[1] if x['why'].startswith('the game') else x['why'].split(' ')[0]] += 1
        if g in s['people']:
            real = Counter(c[1] for c in s['people'][g] if not c[4])
            if real:
                prop = {c for c, _n in propose_people(db, p['kind'], p['type'], p['mat'], skip=g)['classes']}
                # (the carriers' classes, counted by how many of them: the share of its carriers in a class sent to)
                cls_real += sum(real.values())
                cls_hit += sum(n for c, n in real.items() if c in prop)
    lv_err.sort()
    return {'pieces': len(pieces),
            'lists_found': round(lst_hit / float(max(1, lst_real)), 3),          # (its real lists that it is sent back to)
            'lists_right': round(lst_right / float(max(1, lst_prop)), 3),        # (the lists it is sent to that are real)
            'level_off_median': lv_err[len(lv_err) // 2] if lv_err else None,
            'level_within_2': round(sum(1 for e in lv_err if e <= 2) / float(max(1, len(lv_err))), 3),
            'carriers_covered': round(cls_hit / float(max(1, cls_real)), 3)}  # (its carriers whose class it is sent to)
