"""Does a place serve its purpose? The faults a player feels on walking in, which the geometry checks never see: a
"Smith" with no forge, a tavern with no bar or tables, a temple with no shrine, a shop with no counter and no wares, a
guild hall furnished as a storeroom, a home whose people have no bed, a room of any size with nothing in it, a door
inside that leads nowhere, an interior that sticks out of the building it stands in. Listed in the Place panel's
health check beside the furnishing faults (placecheck.py), with where to look; the fixes are the tools: Auto-furnish
rooms (pick the kind), Interior from a building, the door's Leads to.

What it reads: the place's name (townsurvey.KINDS: a smith, a tavern...), its people (their classes say the trade when
the name does not), its things by family (roomsurvey.family_of) and by the trade's pieces (tradesurvey.piece_of), its
rooms (furnish.rooms), its doors, and frombuilding.fits for the building outside.

The user (2026-11-04): "survey the game in an immersive way and learn a sense for furnishing buildings with purpose".
This is the first half: knowing when a place has none."""
import math
import re

import mapdata

WORDS = [('smith', r'smith|armou?rer|weaponsmith|forge'), ('tavern', r'tavern|cornerclub|\bclub\b|tradehouse|hostel|\binn\b|meadhouse|alehouse'),
         ('temple', r'temple|shrine|chapel|\bcult\b'), ('mages', r'mages|enchanter|alchem|apothec'), ('fighters', r'fighters|arena'),
         ('guild', r'guild'), ('shop', r'trader|pawnbroker|outfitter|clothier|bookseller|store|shop|merchant|goods|market|tailor|garments|weaver|bakery|baker'),
         ('manor', r'manor|palace|villa'), ('guard', r'\bfort\b|keep|garrison|barracks|guard|\btower|watch'),
         ('house', r'house|home|shack|hut|residence|hovel|cottage|lodge|apartment|yurt')]
CLASS_TRADE = [('smith', r'smith|armou?rer'), ('tavern', r'publican|innkeeper|barkeep'), ('temple', r'priest|monk|healer'),
               ('mages', r'mage|sorcer|wizard|conjur|battlemage|enchant|alchem'), ('fighters', r'warrior|knight|fighter|champion|barbarian'),
               ('shop', r'trader|merchant|clothier|bookseller|pawnbroker|outfitter|tailor|scribe|baker'), ('guard', r'guard|legion|soldier')]
BARE_TILES = 6                  # a room of this many tiles or more with next to nothing in it is bare
BARE_THINGS = 3


def kind_of(name, people):
    """What the place is for, by its name first, then by its people's classes: 'smith', 'tavern', 'temple', 'mages',
    'fighters', 'guild', 'shop', 'manor', 'guard', 'house' or ''."""
    low = (name or '').lower()
    for k, rx in WORDS:
        if re.search(rx, low):
            return k
    for cls in people:
        for k, rx in CLASS_TRADE:
            if re.search(rx, cls or '', re.I):
                return k
    return ''


def _fam(db, r):
    try:
        import roomsurvey
        f = roomsurvey.family_of(db, r['id'], r['type'])
    except Exception:
        f = None
    low = r['id'].lower()
    try:
        import tradesurvey
        pc = tradesurvey.piece_of(r['id'], r['type'])
    except Exception:
        pc = None
    if pc in ('forge', 'anvil', 'bellows'):
        return pc
    if re.search(r'shrine|altar', low) and r['type'] in ('ACTI', 'STAT'):
        return 'shrine'
    if re.search(r'practice_dummy|target', low):
        return 'target'
    if re.search(r'(^|_)bed|bunk|hammock|bedroll', low) and r['type'] in ('ACTI', 'STAT') and not re.search(r'bedroom|rug|ex_', low):
        return 'bed'
    if re.search(r'_bar_|bar_0|counter', low) and r['type'] == 'STAT':
        return 'counter'
    return f


def _room_of(rooms, p, T):
    for rm in rooms:
        if rm['x_min'] - 8 <= p[0] <= rm['x_max'] + 8 and rm['y_min'] - 8 <= p[1] <= rm['y_max'] + 8 and abs(p[2] - (rm.get('floor') or 0)) < 300:
            return rm
    return None


def issues(db, cell_key, m=None):
    """[{kind, text, id, name, ref, room, x, y, z, fixes}] in placecheck's own shape."""
    import furnish
    m = m or mapdata.cellmap(db, cell_key)
    refs = m.get('refs') or []
    name = (mapdata.cell_info(db, cell_key) or {}).get('name') or cell_key
    people = []
    for r in refs:
        if r['type'] == 'NPC_':
            ri = db.resolve_id(r['id'])
            cls = ''
            if ri is not None:
                try:
                    import npc
                    o_ = npc.read(db, r['id']) or {}
                    cls = o_.get('cls') or o_.get('class') or ''
                except Exception:
                    cls = ''
            people.append(cls)
    kind = kind_of(name, people)
    things = [r for r in refs if not r.get('arch') and r['type'] != 'DOOR']
    fams = {}
    for r in things:
        fams.setdefault(_fam(db, r), []).append(r)
    try:
        info = furnish.rooms(db, cell_key)
        rooms, T = info['rooms'], info.get('tile') or 256
    except Exception:
        rooms, T = [], 256
    out = []

    def at_room(rm):
        fl = rm.get('floor') or 0
        return [(rm['x_min'] + rm['x_max']) / 2, (rm['y_min'] + rm['y_max']) / 2, fl + 60]

    def issue(kind_, text, at, room='', ref='', rid='', fixes=()):
        return {'kind': kind_, 'text': text, 'id': rid, 'name': '', 'ref': ref, 'room': room, 'x': at[0], 'y': at[1], 'z': at[2], 'fixes': list(fixes)}

    def has(*ks):
        return any(fams.get(k) for k in ks)

    centre = at_room(rooms[0]) if rooms else [0.0, 0.0, 0.0]
    # the purpose the name gives, and what should be here for it
    want = {'smith': (('forge', 'anvil'), 'no forge or anvil: nothing to smith with'),
            'tavern': (('counter', 'table'), 'no bar and no tables: nowhere to drink'),
            'temple': (('shrine',), 'no shrine or altar'),
            'shop': (('counter', 'shelf', 'table'), 'no counter, shelf or table to sell from'),
            'mages': (('bookshelf', 'table', 'shelf'), 'no bookshelf, table or shelf: nothing of a guild of mages'),
            'fighters': (('rack', 'target', 'bed'), 'no racks, dummies or bunks: nothing of a guild of fighters'),
            'guild': (('table', 'bookshelf', 'rack', 'bed'), 'nothing of a guild hall'),
            'manor': (('table', 'bed'), 'no table and no bed'),
            'house': (('bed',), 'no bed')}
    if kind in want:
        need, why = want[kind]
        if not has(*need):
            label = {'smith': 'Smith', 'tavern': 'Tavern', 'temple': 'Temple', 'shop': 'Shop', 'mages': 'Mages\' guild', 'fighters': 'Fighters\' guild',
                     'guild': 'Guild hall', 'manor': 'Manor', 'house': 'Home'}[kind]
            out.append(issue('purpose', '%s by its name, but %s' % (label, why), centre))
    # people with no bed: a home's household, a trader's family
    if people and kind not in ('guard', 'temple', 'tavern', 'mages', 'fighters', 'guild') and not has('bed') and not any(
            re.search(r'guard|soldier|legion', c or '', re.I) for c in people):
        if kind not in want or has(*want[kind][0]):
            out.append(issue('nobed', '%d %s here and no bed to sleep in' % (len(people), 'person lives' if len(people) == 1 else 'people live'), centre))
    # bare rooms: six tiles or more with next to nothing
    for rm in rooms:
        n_tiles = len(rm.get('_tiles') or ()) * (T / 256.0) ** 2
        if n_tiles < BARE_TILES * 0.75:
            continue
        inside = [r for r in things if _room_of([rm], r['p'], T) is rm and r['type'] != 'LIGH']
        if len(inside) < BARE_THINGS:
            out.append(issue('bare', '%s is bare: %d thing%s in %d tiles' % (rm.get('name') or 'A room', len(inside), '' if len(inside) == 1 else 's', round(n_tiles)), at_room(rm), rm.get('name') or ''))
    # doors inside that lead nowhere: no link, and floor on one side of them only (a hinged door between two rooms,
    # a prison's cell door, has floor on both sides and is no fault)
    tiles = [(t['x'], t['y'], t.get('floor') or rm.get('floor') or 0) for rm in rooms for t in rm.get('_tiles') or ()]

    def floor_at(x, y, z):
        return any(abs(x - tx) <= T * 0.6 and abs(y - ty) <= T * 0.6 and -80 <= z - tz <= 240 for tx, ty, tz in tiles)
    for r in refs:
        if r['type'] == 'DOOR' and not r.get('to') and not re.search(r'marker', r['id'], re.I):
            flat = abs(r['p'][3]) > 1.2 or abs(r['p'][4]) > 1.2 or re.search(r'trap|hatch', r['id'], re.I)
            below = tiles and r['p'][2] < min(tz for _x, _y, tz in tiles) - 60
            if flat or below:
                # (a hatch in the floor with nothing under it: the game's own cellar door copied with a ready-made hut,
                # the user's Nord hut, 2026-11-04)
                rm = _room_of(rooms, r['p'], T)
                out.append(issue('deaddoor', '%s is a trap door to nowhere' % (r.get('name') or r['id']), [r['p'][0], r['p'][1], r['p'][2] + 60], (rm or {}).get('name') or '', r['k'], r['id']))
                continue
            if not tiles:
                continue
            rz = r['p'][5] if len(r['p']) > 5 else 0.0
            nx, ny = math.sin(rz), math.cos(rz)
            sides = [floor_at(r['p'][0] + nx * d, r['p'][1] + ny * d, r['p'][2]) for d in (110, -110)]
            sides += [floor_at(r['p'][0] + ny * d, r['p'][1] - nx * d, r['p'][2]) for d in (110, -110)]
            if sum(sides) >= 3 or (sides[0] and sides[1]) or (sides[2] and sides[3]):
                continue
            rm = _room_of(rooms, r['p'], T)
            out.append(issue('deaddoor', '%s leads nowhere' % (r.get('name') or r['id']), [r['p'][0], r['p'][1], r['p'][2] + 60], (rm or {}).get('name') or '', r['k'], r['id']))
    # the building outside: does the interior fit it?
    try:
        import frombuilding
        f = frombuilding.fits(db, cell_key)
        if f and not f.get('ok'):
            out.append(issue('sizefit', f.get('text') or 'Sticks out of its building', centre))
    except Exception:
        pass
    # every kit stair walked from its foot to its head (stairwalk.py): a wall across the flight, a piece closing over
    # it. (The user's Estmorevale house, 2026-11-04: the game's end cap laid across the foot and a table in front of
    # it, and the card said the house served its purpose)
    try:
        import stairwalk
        for w in stairwalk.walk(db, cell_key, m=m):
            if w['ok']:
                continue
            by = (w.get('by') or {}).get('id') if isinstance(w.get('by'), dict) else w.get('by')
            if w.get('where') == 'over' and by and re.search(r'win|wall|beam|rail|post|pillar|column', by, re.I):
                continue                  # (a window, wall or beam set over a flight: the game's own places have them; a floor closing over it is the fault)
            how = 'closed over' if w.get('where') == 'over' else 'blocked'
            at = list(w.get('at') or [0, 0, 0])
            rm = _room_of(rooms, at, T)
            out.append(issue('stairend', 'The stairs are %s%s: nobody can use them' % (how, (' by %s' % by) if by else ''), at,
                             (rm or {}).get('name') or '', w.get('ref') or '', w.get('id') or ''))
    except Exception as e:
        print('purpose stairs:', cell_key, e)
    return out


KINDS = [
    ('purpose', 'Not what its name says', 'A smith with no forge, a tavern with no bar, a temple with no shrine, a shop with nothing to sell from, a home with no bed.'),
    ('nobed', 'People with no bed', 'Someone lives here and there is no bed to sleep in.'),
    ('bare', 'Bare rooms', 'A room of six tiles or more with next to nothing in it.'),
    ('deaddoor', 'Doors that lead nowhere', 'A door inside with no place behind it.'),
    ('stairend', 'Stairs nobody can use', 'A wall across the foot or the head of a flight, or a piece closing over it.'),
    ('sizefit', 'Bigger than its building', 'The interior reaches well outside the building it stands in.'),
]
