"""Examples of what OpenMW 0.52 opens up, each made whole with one click and then yours to open and change (Create >
New with OpenMW 0.52 > Examples): a Fishing skill, Piety with its two skills, an aurora and other weathers of the sky,
a cursed chest and a glowing treasure chest. Each is made of the same records the forms make (myrecords.py), so
changing one teaches the form. The user (2026-11-02): "a great way to introduce people to altering these new
mechanical systems in the game"; Fishing, Piety (raised by books and shrines, strengthening altars' blessings),
auroras and other mystical weathers, chests."""
import re

import editing
import myrecords
from editing import EditError, commit
from esm import iter_subrecords
from project import join_subs, zs

HOLY = re.compile(r'\b(god|gods|tribunal|almsivi|vivec|temple|divine|divines|saint|saints|prayer|prayers|pilgrim|sermon|'
                  r'daedra|aedra|akatosh|arkay|stendarr|azura|faith|cult|worship|monomyth|nirn|cantatas|consolations)\b', re.I)
SHRINE = re.compile(r'^shrine of|altar', re.I)
DAEDRIC = re.compile(r'sound|velothi_altar|daedr|mephala|boethia|molag|malacath|sheogorath|dagon|vaermina|hircine|peryite|namira|'
                     r'clavicus|hermaeus|sanguine|meridia|nocturnal|jyggalag|bal\b|dark_?brotherhood', re.I)
NINE = re.compile(r'imp_altar|setchapel_altar|legion_altar|nine divines', re.I)
NORTH = re.compile(r'sheogorad|solstheim|felsaad|moesring|hirstaang|isinfier|brodir|thirsk|skyrim|reaver|falkheim|druadach|pale|frost', re.I)
ASH = re.compile(r'ashlands|molag amur|red mountain|armun', re.I)
MIST = re.compile(r'bitter coast|grazelands|ascadian|lagoon|marsh|swamp|mournhold', re.I)
INSTRUMENT = re.compile(r'\b(lute|drum|fiddle|flute|bagpipes?|harp|lyre)\b', re.I)
FLORA = re.compile(r'flora|kollop', re.I)

EXAMPLES = [
    {'key': 'fishing', 'icon': '🎣', 'name': 'Fishing', 'line': 'A skill: use a fishing pole by the water, and with skill a fish bites.'},
    {'key': 'piety', 'icon': '🙏', 'name': 'Piety', 'line': 'An attribute and two skills: pray at shrines, read holy books; blessings grow with it.'},
    {'key': 'aurora', 'icon': '🌌', 'name': 'Aurora', 'line': 'A night weather of the north: glowing curtains over the sky.'},
    {'key': 'arcane', 'icon': '🌀', 'name': 'Arcane storm', 'line': 'A violet storm of falling sparks over the ash lands.'},
    {'key': 'mist', 'icon': '🌫', 'name': 'Mourning mist', 'line': 'A pale night mist on the coasts and marshes.'},
    {'key': 'cursed', 'icon': '⚠', 'name': 'Cursed chest', 'line': 'A chest that strikes whoever opens it.'},
    {'key': 'treasure', 'icon': '✨', 'name': 'Glowing treasure', 'line': 'A chest that glows until opened, filled by the player\'s level.'},
    {'key': 'performance', 'icon': '🪕', 'name': 'Performance', 'line': 'A skill: play a lute or a drum, and with skill passers-by toss you coins.'},
    {'key': 'foraging', 'icon': '🌿', 'name': 'Foraging', 'line': 'A skill: pick from plants, and with skill you find one more of what they hold.'},
]

# What each example is tried with (Create > New with OpenMW 0.52 > ▶ Try it): a test setup of its own, switched on, and
# where to start. Console commands as the game takes them at the start (PlaceAtPC puts a chest beside you).
TRY = {
    'fishing': {'items': [['misc_de_fishing_pole', 1]], 'where': 'by water: a dock or a shore (Seyda Neen\'s dock)',
                'how': 'Use the fishing pole from your inventory.'},
    'piety': {'where': 'in a temple, by a shrine (the Temple in Balmora)', 'how': 'Activate the shrine; read the holy book you carry.'},
    'aurora': {'globals': [['GameHour', 22]], 'where': 'outdoors in the north (Sheogorad, Solstheim)',
               'how': 'It comes on some nights there: wait (T) a few hours at a time.'},
    'arcane': {'where': 'outdoors in the ash lands (the Ashlands, Molag Amur)', 'how': 'It comes now and then: wait (T) a few hours at a time.'},
    'mist': {'globals': [['GameHour', 22]], 'where': 'outdoors on the Bitter Coast or the Grazelands',
             'how': 'It comes on some nights there: wait (T) a few hours at a time.'},
    'cursed': {'commands': 'PlaceAtPC "ws_cursed_chest" 1 128 1', 'god': True, 'where': 'anywhere: the chest is put beside you',
               'how': 'Open it (god mode is on, so the curse won\'t kill you).'},
    'treasure': {'commands': 'PlaceAtPC "ws_treasure_chest" 1 128 1', 'where': 'anywhere dark: the chest is put beside you',
                 'how': 'It glows until you open it.'},
    'performance': {'where': 'in a town, among people', 'how': 'Use the instrument from your inventory.'},
    'foraging': {'where': 'in the wilds, among plants (the Bitter Coast)', 'how': 'Pick from the plants round you.'},
}


def made(db):
    """The examples this mod has made already (their records are there): the ones ▶ Try it is offered for."""
    have = lambda kind, rid: _have(db, kind, rid)
    out = {k for k, kind, rid in (('fishing', 'skills', 'Fishing'), ('piety', 'attributes', 'Piety'), ('aurora', 'weathers', 'Aurora'),
                                  ('arcane', 'weathers', 'ArcaneStorm'), ('mist', 'weathers', 'MourningMist'),
                                  ('performance', 'skills', 'Performance'), ('foraging', 'skills', 'Foraging')) if have(kind, rid)}
    for k, rid in (('cursed', 'ws_cursed_chest'), ('treasure', 'ws_treasure_chest')):
        if db.resolve_id(rid) is not None:
            out.add(k)
    return out


def try_setup(db, key):
    """The test setup an example is tried with: {name, items, ..., where, how}; the items it needs found in the mod (the
    holy book, the instrument)."""
    t = dict(TRY.get(key) or {})
    if not t:
        raise EditError('There is no example called %s.' % key)
    items = [list(i) for i in t.pop('items', [])]
    d = myrecords.raw(db)
    for h in d.get('happens') or ():
        if key == 'piety' and h.get('when') == 'read' and h.get('ids'):
            items.append([h['ids'][0], 1])
        if key == 'performance' and h.get('name') == 'Play for coins' and h.get('ids'):
            items.append([h['ids'][0], 1])
    name = 'Try: ' + next(x['name'] for x in EXAMPLES if x['key'] == key)
    return {'name': name, 'items': [i for i in items if db.resolve_id(i[0]) is not None], 'spells': [], 'journal': [],
            'globals': t.get('globals') or [], 'god': bool(t.get('god')), 'level': 0, 'commands': t.get('commands') or '',
            'where': t['where'], 'how': t['how']}



def _have(db, kind, rid):
    return any(x['id'].lower() == rid.lower() for x in myrecords.raw(db)[kind])


def _copy(db, src, new_id, name):
    """A copy of a game record with its own ID and name, for an example to own (a trap on every chest_small_02 in the
    game would curse them all)."""
    if db.resolve_id(new_id) is not None:
        return new_id
    ri = db.resolve_id(src)
    if ri is None:
        raise EditError('The game\'s %s is not in your load order.' % src)
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs, named = [], False
    for t, d in iter_subrecords(data):
        if t == 'NAME' and not named:
            d, named = zs(new_id), True
        elif t == 'FNAM':
            d = zs(name)
        subs.append((t, bytes(d)))
    db.project.set_record(r[0], new_id.lower(), flags & ~0x20, join_subs(subs), created=True)
    commit(db, 'Made "%s" (%s) from %s, for an example' % (name, new_id, src))
    return new_id


def _ids(db, tags, test, limit=40, last=None):
    """IDs of records of these kinds that pass test(id, name); those matching last at the end (the skill books' sermons
    after the plain holy books), so the first limit are the best."""
    out, seen = [], set()
    for i, r in enumerate(db.recs):
        if r[0] in tags and i not in db.dead and r[1] and r[1].lower() not in seen and test(r[1], r[2] or ''):
            seen.add(r[1].lower())
            out.append(r[1])
    if last is not None:
        out.sort(key=lambda x: bool(last.search(x)))
    return out[:limit]


def _regions(db, pat, n=6):
    import regions
    rs = [r for r in regions.all_regions(db) if pat.search(r['id'] + ' ' + (r.get('name') or ''))]
    rs.sort(key=lambda r: -(r.get('cells') or 0))
    return [r['id'] for r in rs[:n]]


def _has(db, tag, rid):
    ri = db.resolve_id(rid)
    return ri is not None and db.recs[ri][0] == tag


def _by_class(db, pairs):
    """Who has a skill: everyone of these classes, at these values (the classes the load order has)."""
    return [{'how': 'class', 'id': c, 'value': v} for c, v in pairs if _has(db, 'CLAS', c)]


def _save(db, kind, rec):
    return myrecords.save(db, kind, rec)['saved']


def fishing(db):
    if _have(db, 'skills', 'Fishing'):
        raise EditError('Your mod has a Fishing skill already.')
    if db.resolve_id('misc_de_fishing_pole') is None:
        raise EditError('The game\'s fishing pole (misc_de_fishing_pole) is not in your load order.')
    sk = _save(db, 'skills', {'name': 'Fishing', 'attribute': 'agility', 'specialization': 'stealth',
                               'description': 'Patience and a steady hand by the water: the more skilled, the more often a fish bites.',
                               'gains': [1, 1, 1, 1],
                               'links': [{'how': 'race', 'id': r, 'bonus': b} for r, b in (('Argonian', 10), ('Nord', 5)) if _has(db, 'RACE', r)]})
    fish = myrecords.save(db, 'ingredients', {'new': True, 'name': 'Fresh Fish', 'look': 'ingred_crab_meat_01', 'weight': 0.5, 'value': 4,
                                               'effects': [{'id': 'restorefatigue'}, {'id': 'restorehealth'}, {'id': 'waterbreathing'}, {'id': ''}]})['saved']['id']
    _save(db, 'happens', {'name': 'Catch a fish', 'when': 'use', 'ids': ['misc_de_fishing_pole'], 'water': True, 'chance': 15,
                          'by': {'kind': 'skill', 'stat': sk['id'], 'per': 0.7}, 'miss': 'Nothing bites.',
                          'then': [{'do': 'raise', 'skill': sk['id'], 'gain': 1}, {'do': 'give', 'id': fish, 'count': 1},
                                   {'do': 'say', 'text': 'You catch a fish!'}]})
    return {'open': ('happens', 'CatchAFish'), 'made': 'the Fishing skill, a Fresh Fish ingredient and "Catch a fish": use a fishing '
                                                       'pole (misc_de_fishing_pole) standing by water'}


def piety(db):
    if _have(db, 'attributes', 'Piety'):
        raise EditError('Your mod has a Piety attribute already.')
    races = [r['id'] for r in myrecords._named(db, 'RACE')][:40]
    at = _save(db, 'attributes', {'name': 'Piety', 'description': 'Faith and devotion. Blessings and a patron\'s favour grow with it.',
                                   'links': [{'how': 'race', 'id': r, 'male': 30, 'female': 30} for r in races]})
    dev = _save(db, 'skills', {'name': 'Devotion', 'attribute': at['id'], 'specialization': 'magic',
                                'description': 'Prayer at the shrines and altars of the gods.',
                                'people': _by_class(db, (('Priest', 45), ('Monk', 40), ('Pilgrim', 35), ('Healer', 30)))})
    scr = _save(db, 'skills', {'name': 'Scripture', 'attribute': at['id'], 'specialization': 'magic',
                                'description': 'Knowledge of the holy books, the sermons and the lives of the saints.',
                                'people': _by_class(db, (('Priest', 40), ('Monk', 35), ('Scholar', 30), ('Pilgrim', 25)))})
    shrines = _ids(db, ('ACTI',), lambda i, n: bool(SHRINE.search(n)) and not DAEDRIC.search(i + ' ' + n) and not NINE.search(i + ' ' + n))
    altars = _ids(db, ('ACTI',), lambda i, n: bool(NINE.search(i + ' ' + n)) and bool(n))
    books = _ids(db, ('BOOK',), lambda i, n: bool(HOLY.search(n.replace("'", ' '))) and not DAEDRIC.search(i), last=re.compile('^bookskill', re.I))
    if shrines:
        _save(db, 'happens', {'name': 'Pray at a shrine', 'when': 'activate', 'ids': shrines, 'daily': True, 'chance': 100,
                              'then': [{'do': 'raise', 'skill': dev['id'], 'gain': 2},
                                       {'do': 'bless', 'kind': 'attribute', 'stat': 'willpower', 'amount': 1, 'hours': 12,
                                        'scale': {'kind': 'attribute', 'stat': at['id'], 'per': 0.08}},
                                       {'do': 'say', 'text': 'Your prayer is heard.'}]})
    if altars:
        _save(db, 'happens', {'name': 'Take a patron Divine', 'when': 'activate', 'ids': altars, 'chance': 100,
                              'then': [{'do': 'raise', 'skill': dev['id'], 'gain': 1},
                                       {'do': 'patron', 'kind': 'attribute', 'stat': 'personality', 'amount': 2, 'group': 'divine',
                                        'scale': {'kind': 'attribute', 'stat': at['id'], 'per': 0.1}},
                                       {'do': 'say', 'text': 'The Nine watch over you.'}]})
    if books:
        _save(db, 'happens', {'name': 'Read a holy book', 'when': 'read', 'ids': books, 'once': True, 'chance': 100,
                              'then': [{'do': 'raise', 'skill': scr['id'], 'gain': 3},
                                       {'do': 'say', 'text': 'The words stay with you.'}]})
    return {'open': ('attributes', at['id']), 'made': 'Piety, with Devotion (%d shrines%s) and Scripture (%d holy books)' % (
        len(shrines), ', %d altars for a patron Divine' % len(altars) if altars else '', len(books))}


def _weather(db, rec):
    if _have(db, 'weathers', rec['name'].replace(' ', '')):
        raise EditError('Your mod has a weather called %s already.' % rec['name'])
    return _save(db, 'weathers', rec)


def aurora(db):
    import skyart
    model = skyart.make_aurora(db, 'green')
    regs = _regions(db, NORTH) or _regions(db, re.compile('.'), 2)
    w = _weather(db, {'name': 'Aurora', 'template': 'clear', 'night': True,
                      'colours': {'skyColor': {'night': [8, 28, 34], 'sunset': [40, 50, 70]}, 'fogColor': {'night': [14, 36, 38]},
                                  'ambientColor': {'night': [50, 82, 72]}},
                      'fields': {'particleEffect': model, 'cloudSpeed': 0.6, 'glareView': 0},
                      'regions': [{'region': r, 'chance': 8} for r in regs]})
    return {'open': ('weathers', w['id']), 'made': 'the Aurora, a night weather of %s, and its glowing curtains (%s)' % (', '.join(regs) or 'nowhere yet', model)}


def arcane(db):
    import skyart
    model = skyart.make_sparks(db)
    regs = _regions(db, ASH, 4)
    w = _weather(db, {'name': 'Arcane Storm', 'template': 'thunderstorm',
                      'colours': {'skyColor': {t: c for t, c in (('sunrise', [70, 40, 90]), ('day', [90, 60, 120]), ('sunset', [80, 40, 100]), ('night', [30, 10, 45]))},
                                  'fogColor': {t: c for t, c in (('sunrise', [80, 50, 110]), ('day', [110, 80, 150]), ('sunset', [90, 50, 120]), ('night', [35, 15, 55]))},
                                  'ambientColor': {'day': [110, 90, 140], 'night': [45, 30, 70]}},
                      'fields': {'particleEffect': model, 'isStorm': True},
                      'regions': [{'region': r, 'chance': 3} for r in regs]})
    return {'open': ('weathers', w['id']), 'made': 'the Arcane Storm, with violet sparks falling (%s), in %s' % (model, ', '.join(regs) or 'no region yet')}


def mist(db):
    regs = _regions(db, MIST, 5)
    w = _weather(db, {'name': 'Mourning Mist', 'template': 'foggy', 'night': True,
                      'colours': {'fogColor': {t: [150, 160, 176] for t in ('sunrise', 'day', 'sunset')} | {'night': [52, 58, 70]},
                                  'skyColor': {'night': [40, 45, 56]}, 'ambientColor': {'night': [60, 66, 80]}},
                      'fields': {'cloudSpeed': 0.3, 'distantLandFogFactor': 0.2},
                      'regions': [{'region': r, 'chance': 6} for r in regs]})
    return {'open': ('weathers', w['id']), 'made': 'the Mourning Mist, a pale night mist in %s' % (', '.join(regs) or 'no region yet')}


def cursed(db):
    cid = _copy(db, 'chest_small_02', 'ws_cursed_chest', 'Cursed Chest')
    spell = next((s for s in ('fireball', 'shockball', 'poisonbloom', 'frostball') if db.resolve_id(s) is not None), None)
    if not spell:
        raise EditError('No spell to curse it with was found (fireball).')
    t = _save(db, 'traps', {'name': 'Cursed chest', 'objects': [cid], 'spell': spell, 'once': True,
                            'text': 'A rune flares on the lid!'})
    return {'open': ('traps', t['id']), 'made': 'a Cursed Chest (%s) that casts %s on whoever opens it: place it from search' % (cid, spell)}


def treasure(db):
    cid = _copy(db, 'chest_small_01', 'ws_treasure_chest', 'Treasure Chest')
    r = _save(db, 'loot', {'name': 'Glowing treasure', 'what': ['weapon', 'armor', 'potion'], 'count': 3, 'chance': 100,
                           'perlevel': 120, 'containers': [cid], 'glow': [255, 214, 120]})
    return {'open': ('loot', r['id']), 'made': 'a Treasure Chest (%s) that glows until opened, filled by the player\'s level' % cid}


def performance(db):
    if _have(db, 'skills', 'Performance'):
        raise EditError('Your mod has a Performance skill already.')
    tools = _ids(db, ('MISC',), lambda i, n: bool(INSTRUMENT.search(n) or INSTRUMENT.search(i.replace('_', ' '))))
    if not tools:
        raise EditError('No lute or drum was found in your load order.')
    sk = _save(db, 'skills', {'name': 'Performance', 'attribute': 'personality', 'specialization': 'stealth',
                               'description': 'Music for an audience: the more skilled, the more often passers-by toss a coin.',
                               'links': [{'how': 'race', 'id': r, 'bonus': b} for r, b in (('Breton', 5), ('Wood Elf', 5)) if _has(db, 'RACE', r)],
                               'people': _by_class(db, (('Bard', 45), ('Minstrel', 40), ('Publican', 20)))})
    gold = next((g for g in ('Gold_001', 'gold_001') if db.resolve_id(g) is not None), None)
    then = [{'do': 'raise', 'skill': sk['id'], 'gain': 1}]
    if gold:
        then.append({'do': 'give', 'id': gold, 'count': 12})
    then += [{'do': 'bless', 'kind': 'attribute', 'stat': 'personality', 'amount': 1, 'hours': 6,
              'scale': {'kind': 'skill', 'stat': sk['id'], 'per': 0.05}},
             {'do': 'say', 'text': 'Passers-by toss you a few coins.'}]
    _save(db, 'happens', {'name': 'Play for coins', 'when': 'use', 'ids': tools, 'daily': True, 'chance': 25,
                          'by': {'kind': 'skill', 'stat': sk['id'], 'per': 0.7}, 'miss': 'Nobody stops to listen.', 'then': then})
    return {'open': ('happens', 'PlayForCoins'), 'made': 'the Performance skill and "Play for coins": use a lute or a drum (%d instruments), once a day' % len(tools)}


def foraging(db):
    if _have(db, 'skills', 'Foraging'):
        raise EditError('Your mod has a Foraging skill already.')
    plants = _ids(db, ('CONT',), lambda i, n: bool(FLORA.search(i)), limit=600)
    if not plants:
        raise EditError('No plants were found in your load order.')
    sk = _save(db, 'skills', {'name': 'Foraging', 'attribute': 'intelligence', 'specialization': 'stealth',
                               'description': 'Knowing where the good leaves and roots are: the more skilled, the more a plant gives.',
                               'links': [{'how': 'race', 'id': r, 'bonus': b} for r, b in (('Wood Elf', 10), ('Khajiit', 5)) if _has(db, 'RACE', r)],
                               'people': _by_class(db, (('Alchemist', 40), ('Scout', 35), ('Hunter', 35), ('Pilgrim', 25)))})
    _save(db, 'happens', {'name': 'Forage', 'when': 'activate', 'ids': plants, 'daily': True, 'chance': 10,
                          'by': {'kind': 'skill', 'stat': sk['id'], 'per': 0.6},
                          'then': [{'do': 'raise', 'skill': sk['id'], 'gain': 0.5}, {'do': 'give', 'id': '*', 'count': 1},
                                   {'do': 'say', 'text': 'You find a little more.'}]})
    return {'open': ('happens', 'Forage'), 'made': 'the Foraging skill and "Forage": pick from a plant (%d kinds), once a day each' % len(plants)}


MAKERS = {'fishing': fishing, 'piety': piety, 'aurora': aurora, 'arcane': arcane, 'mist': mist, 'cursed': cursed, 'treasure': treasure,
          'performance': performance, 'foraging': foraging}


def make(db, key):
    """One example, made whole: its records as one operation (a single row in My mod, one Undo there)."""
    editing._require_project(db)
    fn = MAKERS.get(key)
    if not fn:
        raise EditError('There is no example called %s.' % key)
    with editing.operation('example'):
        out = fn(db)
    return dict(myrecords.read(db), example=out)
