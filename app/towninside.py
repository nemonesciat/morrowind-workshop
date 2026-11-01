"""A built town's insides (townbuild.make, interiors=True): behind each building's door one of the game's own interiors
for that very building, copied whole (frombuilding.copy_game_interior: its furniture and what lies about, people and
owners left out), its door linked both ways; and with people=True its household, cast as the game's places of its kind
have them (populate.cast), placed and owning its beds and chests.

Every building on a plot is a game building that stands outside one or more of the game's interiors (the exterior
survey's examples), so each has interiors made for it: the one of the plot's kind is taken (a smithy's for a smithy),
never a tomb's, a cave's or a mine's, and a whole place before an upper floor or a wing.

The interiors are named as the game names its own (survey of the interiors behind the game's town buildings, lab
jtint0, 2026-10-31): "<Town>, <Name>'s House" (323), "<Name>: Trader" and the other trades (100+), "<Family>
Tradehouse"; a temple, a guild or a guard tower by what it is. The name is the household's head's: the cast is made
on the game's original first (the copy keeps every position, so its spots hold), then the copy is named after its head.
A tavern with a name of its own gets one made from the words of that culture's tavern names ("The Ruby Crab Inn")."""
import random
import re
import zlib

import mapdata
import townsurvey
from editing import EditError

# (the doors of the game's tombs, barrows, caves and mines are in its towns too, Velothi's ancestral tombs most; a
# plot takes none of them, and no interior is copied from one)
NOT_TOWN = re.compile(r'tomb|barrow|crypt|cave\b|cavern|grotto|\bmine\b|mine entrance|ruin|propylon|daedric|catacomb|sewer|'
                      r'\babyss\b|dungeon|\blair\b|egg mine|stronghold|shrine of|underground|ancestral', re.I)
# (part of a place, not a place: "Gateway Inn: North Wing", "Red Palace: Upper Floor")
PART = re.compile(r':\s*(upper|lower|top|ground|second|third|north|south|east|west)?\s*(floor|level|wing|basement|cellar|'
                  r'quarters|tower|hall|antechamber|auditorium|kitchen|storage|attic|vault|spire|rooms?)\b', re.I)
TRADE = re.compile(r"^([A-Z][\w'-]*(?: [A-Z][\w'-]*){0,3}): ([A-Z][\w ]+)$")
OWNED = re.compile(r"^([A-Z][\w'-]*(?: (?:the |gro-|gra-)?[A-Z][\w'-]*){0,3})'s? ([A-Z][\w ]+)$")
FAMILY = re.compile(r"^([A-Z][\w'-]+) (Tradehouse|Manor|House|Household|Residence|Farmhouse|Cornerclub|Hall)$")
NOT_PERSON = re.compile(r'\b(of|the|temple|hall|inn|tower|manor|guild|chapel|shrine|office|market|club|palace|house|tavern)\b', re.I)
TAVERN_WORDS = re.compile(r'\b(the|inn|tavern|tradehouse|hostel|club|cornerclub|entrance|of|and|house|wing|north|south|east|west)\b', re.I)


def town_ok(name):
    """Is the game interior behind a building one a town's plot can stand for (not a tomb's, a cave's, a mine's)?"""
    return not NOT_TOWN.search(name or '')


def _name_of(db, key):
    return (mapdata.cell_info(db, key) or {}).get('name') or key


def _tail(name):
    """The place's own part of a game interior's name: "Ald-ruhn, Dandera Selaro: Smith" → "Dandera Selaro: Smith"."""
    return name.split(',', 1)[1].strip() if ',' in name else name.strip()


def template(db, m, kind, rng, used=None):
    """The game interior to copy for a building (its exterior module m) on a plot of this kind, or None: the plot's kind
    first, a whole place before a part, one not copied yet in this town before one that was."""
    used = used if used is not None else {}
    rows = []
    for e in m.get('examples') or ():
        if not db.by_key.get(('CELL', e)):
            continue
        nm = _name_of(db, e)
        if not town_ok(nm):
            continue
        rows.append((townsurvey.kind_of(e) != kind, bool(PART.search(nm)), used.get(e, 0), rng.random(), e))
    return min(rows)[-1] if rows else None


# ---------------------------------------------------------------- names

def town_name(db, culture, seed=1):
    """A town name made from the culture's own town names: the start of one and the end of another
    ("Gni" + "ruhn"), never one the game has."""
    towns = townsurvey.survey(db)['towns']
    names = [t['name'] for t in towns if t.get('name') and t.get('culture') == culture] or [t['name'] for t in towns if t.get('name')]
    have = {n.lower() for n in names}
    rng = random.Random('%s|%s|town' % (seed, culture))
    chunks = lambda s: re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy]+$)?", s.lower())
    for _t in range(200):
        a, b = rng.choice(names), rng.choice(names)
        a_, b_ = chunks(a.split(',')[0]), chunks(b.split(',')[0])
        if len(a_) < 1 or len(b_) < 2:
            continue
        nm = ''.join(a_[:rng.randint(1, max(1, len(a_) - 1))] + b_[-rng.randint(1, max(1, len(b_) - 1)):])
        nm = re.sub(r'([ -])(\w)', lambda g: g.group(1) + g.group(2).upper(), nm).strip(' -')
        nm = nm[:1].upper() + nm[1:]
        if 4 <= len(nm.replace(' ', '')) <= 12 and nm.lower() not in have and not re.search(r'(.)\1\1|[ -]{2}', nm):
            return nm
    return 'New ' + culture


def _possessive(name):
    return name + ("'" if name.endswith('s') else "'s")


def _tavern(db, culture, rng):
    """A tavern name from the words of the culture's game tavern names: "The <word> <word> Inn"."""
    names = []
    for t in townsurvey.survey(db)['towns']:
        if t.get('culture') != culture:
            continue
        for b in t.get('buildings') or ():
            if b.get('kind') == 'tavern' and b.get('name'):
                names.append(_tail(b['name']))
    words = [w for n in names for w in re.findall(r"[A-Z][a-z']+", TAVERN_WORDS.sub(' ', n)) if not w.endswith("'s")]
    ends = [m.group(1) for n in names for m in [re.search(r'\b(Inn|Tavern|Tradehouse|Hostel|Cornerclub|Club)\b', n)] if m] or ['Inn']
    if len(words) < 2:
        return None
    return 'The %s %s %s' % (rng.choice(words), rng.choice(words), rng.choice(ends))


DWELLING = re.compile(r'(House|Shack|Hut|Lodge|Farmhouse|Cabin|Yurt|Tent|Manor|Hall|Apartment|Residence|Household|Tower|Farm)')


def interior_name(db, town, tmpl_name, kind, head, family, culture, rng):
    """The copy's name, after its head where the game's own is after a person, and always for a home (a house plot in a
    farm's storage or a slave shack is somebody's: "Slave Shack Two" six times over, lab jtint1)."""
    tail = PART.sub('', _tail(tmpl_name)).strip(' :') or _tail(tmpl_name)
    # ("Guar Farm: Erdlan Galelan's Shack": the person's part)
    if ': ' in tail and OWNED.match(tail.split(': ', 1)[1]):
        tail = tail.split(': ', 1)[1]
    m = TRADE.match(tail)
    if m and head and not NOT_PERSON.search(m.group(1)):
        tail = '%s: %s' % (head, m.group(2))
    else:
        m = OWNED.match(tail)
        if m and head and not NOT_PERSON.search(m.group(1)):
            tail = '%s %s' % (_possessive(head), m.group(2))
        else:
            m = FAMILY.match(tail)
            if m and (family or head):
                tail = '%s %s' % (family or head.split()[-1], m.group(2))
            elif kind == 'tavern':
                tail = _tavern(db, culture, rng) or tail
            elif kind not in ('temple', 'guild', 'guard', 'tavern') and head:
                w = DWELLING.findall(tail)
                tail = '%s %s' % (_possessive(head), w[-1] if w else 'House')
    return '%s, %s' % (town, tail)


def _unique(db, name, taken):
    base, n = name[:60], 2
    while name.lower() in taken or (db.by_key.get(('CELL', name.lower())) and
                                    any(v not in db.dead for v in db.by_key[('CELL', name.lower())])):
        name = '%s %d' % (base[:58], n)
        n += 1
    taken.add(name.lower())
    return name


# ---------------------------------------------------------------- the insides

def _building(db, q, dr):
    """The building at a plot as frombuilding knows one, from what the town knows: its door, and its frame from the plot's
    facing (+y inward). (building_at gave up on a joined Dunmer row, "the pieces run on into the rest of the town", and
    read the pieces round every door again)"""
    import shellsurvey as ss
    import townbuild
    m = mapdata.cellmap(db, dr[0])
    d = next((r for r in m.get('refs', []) if r['k'] == dr[1]), None)
    if d is None:
        raise EditError("The building's door is no longer there.")
    c, sn, _yaw = townbuild._frame(q['face'])
    ux, uy = sn, c
    sill = d['p'][2] + (d.get('b') or [0, 0, 0])[2] * (d.get('s') or 1.0)
    return {'door': {'k': d['k'], 'cell': dr[0], 'id': d['id'], 'p': d['p']}, 'frame': ss.Frame(d['p'][0], d['p'][1], sill, ux, uy),
            'cell': dr[0]}


def furnish(db, plan, town, culture, seed=1, people=True, catalog=None, say=None):
    """An interior behind every built plot's door (q['door_ref']), and its people. Each step its own change; the caller
    folds them with the town into one. say(done share): told as each plot is gone through (townbuild's progress bar).
    {'interiors', 'people', 'names', 'skipped'}"""
    import frombuilding
    C = {c['key']: c for c in (catalog or ())}
    # (a cast for every interior when the people survey is learnt, people or not: a home is named after its head, and
    # without one nine homes were "Farmhands' Lodge" 1 to 3; only placing them is slow)
    import castsurvey
    S = castsurvey.ready(db)
    rng = random.Random('%s|%s|inside' % (seed, culture))
    taken, names, used = set(), [], {}
    said = []
    made = folks = skipped = 0
    for k, q in enumerate(plan['plots']):
        if say:
            say(k / float(len(plan['plots']) or 1))
        dr = q.get('door_ref')
        b = q.get('b') and C.get(q['b']['key'])
        if not dr or not b:
            continue
        kind = q.get('kind') or b['kind']
        t = template(db, b['m'], kind, rng, used)
        if t is None:
            skipped += 1
            continue
        used[t] = used.get(t, 0) + 1
        tname = _name_of(db, t)
        cast_ = None
        head = family = None
        if S is not None:
            import populate
            import castsurvey
            try:
                # (the plot in the seed: by the template alone, six copies of one shack had one Drathyn Sarothril, lab jtint2)
                cast_ = populate.cast(db, t, {}, seed=zlib.crc32(('%s|%s|%s|%d' % (seed, town, t, made + skipped)).encode()))
            except Exception as e:
                print('town cast:', t, e)
                cast_ = None
            ppl = (cast_ or {}).get('people') or []
            if ppl:
                h = next((p for p in ppl if p.get('relation') in ('head', 'leader')), ppl[0])
                head = h['name']
                family = castsurvey._split_name(h['name'], h.get('race') or '')[1] or None
        name = _unique(db, interior_name(db, town, tname, townsurvey.kind_of(tname), head, family, culture, rng), taken)
        try:
            out = frombuilding.copy_game_interior(db, dr[0], dr[1], t, name, 'furnished', door_key=dr[1], b=_building(db, q, dr))
        except EditError as e:
            print('town interior:', name, e)
            skipped += 1
            continue
        made += 1
        names.append(out['name'])
        q['inside_kind'] = kind
        q['interior'] = out['key']
        ppl = (cast_ or {}).get('people') or [] if people else []
        if ppl:
            import populate
            try:
                pl = populate.place(db, out['key'], ppl, own=True, lines=False)
                said += pl['people']
                folks += len(ppl)
            except EditError as e:
                print('town people:', name, e)
    if said:
        import populate
        import editing
        if populate.write_lines(db, said):
            editing.commit(db, 'Lines for the people of %s' % town)
    return {'interiors': made, 'people': folks, 'names': names, 'skipped': skipped}
