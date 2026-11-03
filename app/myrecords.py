"""Your own skills, attributes and weathers (2026-11-01, for OpenMW 0.52): records the game itself never had, made as
the game loads by a load script (`openmw.content.skills`, `.attributes`, `.weathers`, new in 0.52), the way the
Workshop makes your own magic effects (myeffects.py). The user: "0.52 RC1 allows for custom skills, attributes, and
weather. We absolutely MUST be able to play with these ... without arcane tutorials with the construction kit and LUA
scripting".

  attribute   name, description, icon, werewolf value
  skill       name, description, icon, specialization (combat, magic, stealth), governing attribute (the game's or
              yours), the four skill gains, werewolf value; and how it rises: using or activating the things you name
              raises it by the gain you give (OpenMW's SkillProgression), so it can be trained in play
  weather     a copy of one of the game's ten weathers (its template) with your own sky, fog, ambient and sun colours
              at sunrise, day, sunset and night, clouds, fog depth, wind, particles, sounds and storm; and where it
              comes: a chance an hour in each region you pick

Kept in the mod's Lua scripts: "my_records" (kind LOAD, first of all: a skill of yours may be an effect's school)
holds the list as JSON between markers and makes the records, one field at a time, so a field OpenMW refuses is
reported in its log and the rest still made; "my_records_global" raises skills and brings weathers. Records need an
.omwaddon (a plain .esp carries no scripts) and OpenMW 0.52 or newer to show in the game."""
import json
import os
import re

from editing import EditError, commit, _require_project

SCRIPT = 'my_records'
GLOBAL = 'my_records_global'
ACTOR = 'my_records_actor'
LOOK = 'my_records_look'
LOOT_TYPES = {'weapon': 'WEAP', 'armor': 'ARMO', 'clothing': 'CLOT', 'potion': 'ALCH', 'ingredient': 'INGR', 'book': 'BOOK',
              'misc': 'MISC', 'apparatus': 'APPA', 'lockpick': 'LOCK', 'probe': 'PROB', 'repair': 'REPA', 'light': 'LIGH'}
PLAYER = 'my_records_player'
HAPPEN = 'my_records_happen'
HAPPEN_PLAYER = 'my_records_happen_player'
BEGIN = '--[[ WORKSHOP MY RECORDS (kept by the Workshop: Create > New skill, attribute or weather write this)'
END = 'WORKSHOP MY RECORDS END ]]'
KINDS = ('skills', 'attributes', 'weathers', 'lists', 'loot', 'ingredients', 'looks', 'traps', 'happens')
ATTRIBUTES = ('strength', 'intelligence', 'willpower', 'agility', 'speed', 'endurance', 'personality', 'luck')
SPECIALIZATIONS = ('combat', 'magic', 'stealth')
SKILLS = ('block', 'armorer', 'mediumarmor', 'heavyarmor', 'bluntweapon', 'longblade', 'axe', 'spear', 'athletics', 'enchant',
          'destruction', 'alteration', 'illusion', 'conjuration', 'mysticism', 'restoration', 'alchemy', 'unarmored',
          'security', 'sneak', 'acrobatics', 'lightarmor', 'shortblade', 'marksman', 'mercantile', 'speechcraft', 'handtohand')
SCHOOLS = ('alteration', 'conjuration', 'destruction', 'illusion', 'mysticism', 'restoration')
SCHOOL_SOUNDS = ('castSound', 'boltSound', 'hitSound', 'areaSound', 'failureSound')
LINK_KINDS = {'skills': ('major', 'minor', 'faction', 'race'), 'attributes': ('class', 'faction', 'race')}
WEATHERS = ('clear', 'cloudy', 'foggy', 'overcast', 'rain', 'thunderstorm', 'ashstorm', 'blight', 'snow', 'blizzard')
TIMES = ('sunrise', 'day', 'sunset', 'night')
COLOURS = ('skyColor', 'fogColor', 'ambientColor', 'sunColor')
# (a weather's other fields the editor offers: name -> kind; the rest stay the template's)
WEATHER_FIELDS = {'cloudTexture': 'texture', 'cloudSpeed': 'number', 'windSpeed': 'number', 'glareView': 'number',
                  'particleEffect': 'mesh', 'rainEffect': 'mesh', 'rainSpeed': 'number', 'isStorm': 'bool',
                  'canUseTorches': 'bool', 'hasRipples': 'bool', 'ambientLoopSoundID': 'sound',
                  'rainLoopSoundID': 'sound', 'thunderFrequency': 'number', 'distantLandFogFactor': 'number',
                  'distantLandFogOffset': 'number'}
NEEDS = (0, 52)                # (the OpenMW that has openmw.content's skills, attributes and weathers)


def _script(db, name):
    p = db.project
    return next((s for s in (p.lua if p else []) if s.get('name') == name), None)


def raw(db):
    """{'skills': [...], 'attributes': [...], 'weathers': [...]} as kept in the mod's my_records script."""
    out = {k: [] for k in KINDS}
    out['options'] = {}
    s = _script(db, SCRIPT)
    text = (s or {}).get('text') or ''
    a, b = text.find(BEGIN), text.find(END)
    if a < 0 or b < 0:
        return out
    try:
        got = json.loads(text[a + len(BEGIN):b]) or {}
    except ValueError:
        return out
    for k in KINDS:
        out[k] = list(got.get(k) or [])
    out['options'] = dict(got.get('options') or {})
    return out


def openmw_version(db):
    """(major, minor) of the OpenMW the Workshop starts, from its own resources/version; None when unknown."""
    inst = (db.config or {}).get('install') or ''
    for path in (os.path.join(inst, 'resources', 'version'), os.path.join(os.path.dirname(inst), 'resources', 'version')):
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                m = re.match(r'\s*(\d+)\.(\d+)', f.readline())
                if m:
                    return int(m.group(1)), int(m.group(2))
        except OSError:
            pass
    try:
        import helpinfo
        m = re.match(r'(\d+)\.(\d+)', helpinfo.openmw_version(db))
        return (int(m.group(1)), int(m.group(2))) if m else None
    except Exception:
        return None


CFG_PART = {'skyColor': 'Sky', 'fogColor': 'Fog', 'ambientColor': 'Ambient', 'sunColor': 'Sun'}


def game_colours(db):
    """{weather: {colour: {time: [r, g, b]}}}: the game's own weathers' colours, from openmw.cfg's fallback lines
    (Weather_Ashstorm_Sky_Day_Color,124,073,058), to start a weather of yours from."""
    fb = (db.config or {}).get('fallback') or {}
    out = {}
    for w in WEATHERS:
        for c, part in CFG_PART.items():
            for t in TIMES:
                v = fb.get('Weather_%s_%s_%s_Color' % (w.capitalize(), part, t.capitalize()))
                try:
                    rgb = [int(x) for x in str(v).split(',')[:3]]
                except (TypeError, ValueError):
                    continue
                if len(rgb) == 3:
                    out.setdefault(w, {}).setdefault(c, {})[t] = rgb
    return out


def game_clouds(db):
    """{weather: its cloud texture}, from openmw.cfg's fallback lines (Weather_Clear_Cloud_Texture=Tx_Sky_Clear.dds)."""
    fb = (db.config or {}).get('fallback') or {}
    out = {}
    for w in WEATHERS:
        v = fb.get('Weather_%s_Cloud_Texture' % w.capitalize())
        if v:
            out[w] = str(v)
    return out


def _named(db, tag):
    """[{id, name}] of the game's and the mod's records of a kind (classes, factions, races)."""
    from esm import iter_subrecords, zstr
    out = []
    for (t, key), lst in db.by_key.items():
        if t != tag:
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        r = db.recs[live[-1]]
        name = r[1]
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
            for st, sd in iter_subrecords(data):
                if st == 'FNAM':
                    name = zstr(bytes(sd)) or name
                    break
        except Exception:
            pass
        if 'deprecated' not in name.lower():
            out.append({'id': r[1], 'name': name})
    return sorted(out, key=lambda x: x['name'].lower())


def read(db):
    v = openmw_version(db)
    try:
        import regions
        regs = [{'id': r['id'], 'name': r.get('name') or r['id']} for r in regions.all_regions(db)]
    except Exception:
        regs = []
    effs = _effect_ids(db)
    return dict(raw(db), loot_types=list(LOOT_TYPES), effects_all=[{'id': k, 'name': v['name'], 'skill': v['skill'], 'attribute': v['attribute']}
                                                                   for k, v in sorted(effs.items(), key=lambda kv: kv[1]['name'])],
                schools_game=list(SCHOOLS), school_sounds=list(SCHOOL_SOUNDS), game_colours=game_colours(db), attributes_game=list(ATTRIBUTES), skills_game=list(SKILLS),
                classes=_named(db, 'CLAS'), factions=_named(db, 'FACT'), races=_named(db, 'RACE'), specializations=list(SPECIALIZATIONS),
                weathers_game=list(WEATHERS), times=list(TIMES), colours=list(COLOURS), game_clouds=game_clouds(db),
                weather_fields=WEATHER_FIELDS, regions=regs, openmw='%d.%d' % v if v else None,
                ready=bool(v and v >= NEEDS), needs='%d.%d' % NEEDS,
                lua=bool(db.project and db.project.lua_allowed()), examples=_examples(db), missing=missing(db))


def missing(db, data=None):
    """{kind: {id: [what it still lacks to do anything in play]}}: the gaps a new modder falls into ("I made a skill and
    nothing happens"), shown on its form with where to fix each."""
    d = data or raw(db)
    out = {k: {} for k in KINDS}
    raised = {a.get('skill', '').lower() for h in d.get('happens') or () for a in h.get('then') or () if a.get('do') == 'raise'}
    governs = {}
    for sk in d['skills']:
        governs.setdefault(sk.get('attribute', '').lower(), []).append(sk['name'])
    for sk in d['skills']:
        n = []
        if not (sk.get('rises') or sk.get('books') or sk.get('school') or sk['id'].lower() in raised):
            n.append('Nothing raises it in play yet: give it a way it rises, a book that teaches it, or a When… then… that raises it.')
        if not (sk.get('people') or sk.get('links')):
            n.append('No one has it: give it to people, a class (as a major or minor skill), a faction or a race.')
        if n:
            out['skills'][sk['id']] = n
    for at in d['attributes']:
        n = []
        if not governs.get(at['id'].lower()):
            n.append('It governs no skill, so levelling up never raises it: make a skill it governs.')
        if not at.get('links'):
            n.append('No race or class gives it a starting value.')
        if n:
            out['attributes'][at['id']] = n
    try:
        import myeffects
        called = {str(st.get('weather') or '').lower() for e in myeffects.effects_raw(db) for st in e.get('steps') or ()}
    except Exception:
        called = set()
    for w in d['weathers']:
        if not w.get('regions') and w['id'].lower() not in called:
            out['weathers'][w['id']] = ['It never comes: give it a region (or call it from one of your magic effects).']

    def placed(i):
        return bool(db.used_in.get(i.lower()))
    for t in d['traps']:
        if not any(placed(o) for o in t.get('objects') or ()):
            out['traps'][t['id']] = ['None of these stands anywhere in the world yet: place one (search for it in the Place panel).']
    for r in d['loot']:
        if r.get('containers') and not any(placed(c) for c in r['containers']) and not r.get('npcs'):
            out['loot'][r['id']] = ['None of its containers stands anywhere in the world yet: place one.']
    return out


SCRIPT_WHAT = {
    SCRIPT: 'Runs as the game loads (a LOAD script): makes your skills, attributes, weathers and ingredients, and adds to the '
            'game lists. The JSON between the markers is what the forms keep; the Lua under it reads it.',
    GLOBAL: 'Runs in the world (a GLOBAL script): hears the player using and activating things to raise your skills, brings '
            'your weathers to their regions, fills containers by your loot rules and springs your traps.',
    PLAYER: 'Runs on the player (a PLAYER script): raises a skill when the world script says so.',
    ACTOR: 'Runs on each person (an NPC script): gives your skills to the people, classes and factions named, once.',
    LOOK: 'Runs on the player: shows your look-at lines while the player looks at the things named.',
    HAPPEN: 'Runs in the world: hears the player using and activating the things your When… then… name, tells the '
            'script on the player, and gives the items and casts the spells it asks for.',
    HAPPEN_PLAYER: 'Runs on the player: checks the "only if" (water, once a day, the chance), raises skills, gives blessings '
                   'and a patron bonus (stat modifiers that wear off or are replaced), and hears books being opened.',
}


def scripts(db):
    """The scripts the forms wrote, each with what it does: to read, and learn from (Create > See the script)."""
    out = []
    for name in (SCRIPT, GLOBAL, PLAYER, ACTOR, LOOK, HAPPEN, HAPPEN_PLAYER):
        sc = _script(db, name)
        if sc:
            out.append({'name': name, 'kind': sc.get('kind'), 'what': SCRIPT_WHAT.get(name, ''), 'text': sc.get('text') or ''})
    return out


def _examples(db):
    import examples
    done = examples.made(db) if db.project else set()
    return [dict(x, made=x['key'] in done, where=examples.TRY.get(x['key'], {}).get('where', '')) for x in examples.EXAMPLES]


def _id(name, given):
    i = re.sub(r'[^A-Za-z0-9_]+', '', given or '') or re.sub(r'[^A-Za-z0-9]+', ' ', name or '').title().replace(' ', '')
    if not i or not i[0].isalpha():
        raise EditError('Give it a name (its ID is made from it).')
    return i[:32]


def _num(v, what, lo=None, hi=None, default=0.0):
    try:
        x = float(v if v not in (None, '') else default)
    except (TypeError, ValueError):
        raise EditError('%s must be a number.' % what)
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return round(x, 4)


def _txt(v, n=400):
    return str(v or '').strip()[:n]


def _ids(v, n=40):
    if isinstance(v, str):
        v = re.split(r'[\s,;]+', v)
    return [str(x).strip()[:64] for x in v or () if str(x).strip()][:n]


def _colour(v):
    if isinstance(v, str) and re.match(r'^#?[0-9a-fA-F]{6}$', v.strip()):
        h = v.strip().lstrip('#')
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return [max(0, min(255, int(round(float(x))))) for x in v[:3]]
    return None


def _clean(db, kind, e):
    if kind == 'lists':
        return _clean_list(db, e)
    if kind == 'loot':
        return _clean_loot(db, e)
    if kind == 'ingredients':
        return _clean_ingredient(db, e)
    if kind == 'looks':
        return _clean_look(db, e)
    if kind == 'traps':
        return _clean_trap(db, e)
    if kind == 'happens':
        return _clean_happen(db, e)
    name = _txt(e.get('name'), 48)
    if not name:
        raise EditError('Give it a name.')
    out = {'id': _id(name, e.get('id')), 'name': name, 'description': _txt(e.get('description'))}
    if kind in ('skills', 'attributes'):
        out['icon'] = _txt(e.get('icon'), 200)
        out['werewolf'] = _num(e.get('werewolf'), 'Werewolf value', 0, 1000)
    if kind == 'skills':
        sp = (e.get('specialization') or 'combat').lower()
        if sp not in SPECIALIZATIONS:
            raise EditError('A skill is combat, magic or stealth.')
        out['specialization'] = sp
        mine = {a['id'].lower() for a in raw(db)['attributes']}
        att = (e.get('attribute') or 'strength').strip()
        if att.lower() not in ATTRIBUTES and att.lower() not in mine:
            raise EditError('%s is neither one of the game\'s attributes nor one of yours.' % att)
        out['attribute'] = att
        gains = list(e.get('gains') or [1, 1, 1, 1])[:4] + [1] * 4
        out['gains'] = [_num(g, 'A skill gain', 0, 100, 1) for g in gains[:4]]
        rises = []
        for r in e.get('rises') or ():
            how = (r.get('how') or 'use').lower()
            if how not in ('use', 'activate'):
                continue
            ids = _ids(r.get('ids'))
            if ids:
                rises.append({'how': how, 'ids': ids, 'gain': _num(r.get('gain'), 'A gain', 0.01, 100, 1)})
        out['rises'] = rises[:12]
        # (books that teach it as the game's skill books do, and who has it: a person, or everyone of a class or faction)
        books = []
        for b in _ids(e.get('books')):
            bi = db.resolve_id(b)
            if bi is None or db.recs[bi][0] != 'BOOK':
                raise EditError('%s is not a book.' % b)
            books.append(db.recs[bi][1])
        out['books'] = books[:40]
        people = []
        for p_ in e.get('people') or ():
            how = (p_.get('how') or 'npc').lower()
            pid = _txt(p_.get('id'), 64)
            if how not in ('npc', 'class', 'faction') or not pid:
                continue
            people.append({'how': how, 'id': pid, 'value': int(_num(p_.get('value'), 'A skill value', 1, 200, 30))})
        out['people'] = people[:40]
        sc = e.get('school')
        if sc:
            # (a school of magic: spells of effects in it train it; sounds like one of the game's six unless given)
            like = (sc.get('like') or 'mysticism').lower()
            out['school'] = {'like': like if like in SCHOOLS else 'mysticism',
                             'autoCalcMax': int(_num(sc.get('autoCalcMax'), 'Spells to auto-calculate', 0, 50, 0))}
            for k in SCHOOL_SOUNDS:
                v = _txt(sc.get(k), 64)
                if v:
                    out['school'][k] = v
        else:
            out['school'] = None
    if kind in LINK_KINDS:
        # (where it counts: a class's major or minor skill or favoured attribute, a faction's, a race's bonus or base
        # value, in place of one of the game's when picked; put in as the game loads)
        links = []
        for l in e.get('links') or ():
            how = (l.get('how') or '').lower()
            rid = _txt(l.get('id'), 64)
            if how not in LINK_KINDS[kind] or not rid:
                continue
            link = {'how': how, 'id': rid}
            inst = _txt(l.get('instead'), 64).lower()
            if inst and how != 'race':
                link['instead'] = inst
            if how == 'race':
                if kind == 'skills':
                    link['bonus'] = _num(l.get('bonus'), 'A race bonus', 0, 100, 5)
                else:
                    link['male'] = _num(l.get('male'), 'A base value', 0, 200, 40)
                    link['female'] = _num(l.get('female', l.get('male')), 'A base value', 0, 200, 40)
            links.append(link)
        out['links'] = links[:40]
    if kind == 'weathers':
        tpl = (e.get('template') or 'clear').lower()
        if tpl not in WEATHERS:
            raise EditError('A weather is made from one of the game\'s ten.')
        out['template'] = tpl
        cols = {}
        for c in COLOURS:
            got = {t: _colour(((e.get('colours') or {}).get(c) or {}).get(t)) for t in TIMES}
            got = {t: v for t, v in got.items() if v}
            if got:
                cols[c] = got
        out['colours'] = cols
        f = {}
        for k, kind_ in WEATHER_FIELDS.items():
            v = (e.get('fields') or {}).get(k)
            if v in (None, ''):
                continue
            f[k] = bool(v) if kind_ == 'bool' else _num(v, k) if kind_ == 'number' else _txt(v, 200)
        out['fields'] = f
        regs = []
        for r in e.get('regions') or ():
            rid = _txt(r.get('region'), 64)
            if rid:
                regs.append({'region': rid, 'chance': _num(r.get('chance'), 'A chance', 0, 100, 10)})
        out['regions'] = regs[:40]
        out['night'] = bool(e.get('night'))      # (only after dark, cleared at dawn: an aurora)
    return out


def _clean_list(db, e):
    """Additions to one of the game's levelled lists, made as the game loads: {id (the list), name, kind, add: [{id, level}]}."""
    lid = _txt(e.get('id') or e.get('list'), 64)
    ri = db.resolve_id(lid) if lid else None
    if ri is None or db.recs[ri][0] not in ('LEVI', 'LEVC'):
        raise EditError("%s is not one of the game's levelled lists." % (lid or 'That'))
    kind = 'creatures' if db.recs[ri][0] == 'LEVC' else 'items'
    add = []
    for a in e.get('add') or ():
        aid = _txt(a.get('id'), 64)
        if not aid:
            continue
        ai = db.resolve_id(aid)
        if ai is None:
            raise EditError('There is nothing called %s.' % aid)
        is_creature = db.recs[ai][0] in ('CREA', 'NPC_', 'LEVC')
        if is_creature != (kind == 'creatures'):
            raise EditError('%s %s.' % (aid, 'is not a creature: it goes in an item list' if kind == 'creatures'
                                        else 'is a creature: it goes in a creature list'))
        add.append({'id': db.recs[ai][1], 'level': int(_num(a.get('level'), 'A level', 1, 1000, 1))})
    if not add:
        raise EditError('Add something to the list.')
    return {'id': db.recs[ri][1], 'name': db.recs[ri][1], 'kind': kind, 'add': add[:100]}


def _clean_loot(db, e):
    """A loot rule: what kinds of things, words in their ID or name, a value range, how many, how likely, matched to the
    player's level or not; and the containers it fills (when first opened) and the people it gives to (when first met).
    Picked in play from every record the player's load order has, other mods' included (OpenMW 0.52)."""
    name = _txt(e.get('name'), 48)
    if not name:
        raise EditError('Give the rule a name.')
    what = [w for w in (e.get('what') or []) if w in LOOT_TYPES]
    if not what:
        raise EditError('Pick what kinds of things it gives.')
    out = {'id': _id(name, e.get('id')), 'name': name, 'what': what,
           'words': [w.lower() for w in _ids(e.get('words'))][:20],
           'min': int(_num(e.get('min'), 'The least value', 0, 1e7, 0)), 'max': int(_num(e.get('max'), 'The most value', 0, 1e7, 0)),
           'count': int(_num(e.get('count'), 'How many', 1, 20, 1)), 'chance': _num(e.get('chance'), 'The chance', 0, 100, 100),
           'perlevel': int(_num(e.get('perlevel'), 'Gold a level', 0, 100000, 0))}
    for field, tags, what_ in (('containers', ('CONT',), 'a container'), ('npcs', ('NPC_', 'CREA'), 'a person or creature')):
        got = []
        for i in _ids(e.get(field)):
            ri = db.resolve_id(i)
            if ri is None or db.recs[ri][0] not in tags:
                raise EditError('%s is not %s.' % (i, what_))
            got.append(db.recs[ri][1])
        out[field] = got[:60]
    if not out['containers'] and not out['npcs']:
        raise EditError('Say which containers or people it gives to.')
    # (the containers glow until first opened: OpenMW 0.52's glow on doors and containers)
    out['glow'] = _colour(e.get('glow')) if e.get('glow') else None
    return out


def _clean_trap(db, e):
    """A trap: a spell that strikes whoever opens, takes or uses a thing (every copy, or only in one place), once or every
    time, with a line for the player. By the game's own rules in OpenMW 0.52 (SpellCasting.inflict, its area going off
    where the thing is); before 0.52, added to their spells."""
    name = _txt(e.get('name'), 48)
    if not name:
        raise EditError('Give the trap a name.')
    objs = []
    for i in _ids(e.get('objects')):
        ri = db.resolve_id(i)
        if ri is None or db.recs[ri][0] in ('NPC_', 'CREA', 'LEVC', 'LEVI', 'SPEL', 'ENCH', 'STAT', 'LAND', 'CELL'):
            raise EditError('%s is not a thing that is opened, taken or used.' % i)
        objs.append(db.recs[ri][1])
    if not objs:
        raise EditError('Say what sets it off (a chest, a door, a book...).')
    sid = _txt(e.get('spell'), 64)
    ri = db.resolve_id(sid) if sid else None
    if ri is None or db.recs[ri][0] != 'SPEL':
        raise EditError('There is no spell called %s.' % (sid or 'that'))
    return {'id': _id(name, e.get('id')), 'name': name, 'objects': objs[:40], 'cell': _txt(e.get('cell'), 64),
            'spell': db.recs[ri][1], 'once': e.get('once') is not False, 'text': _txt(e.get('text'), 200)}


HAPPEN_WHEN = ('use', 'activate', 'read')
HAPPEN_DO = ('raise', 'give', 'bless', 'patron', 'cast', 'say')


def _stat(db, data, kind, sid):
    """A game or own skill or attribute's ID as OpenMW's Lua knows it (lower case for the game's), or an error."""
    sid = _txt(sid, 64)
    low = sid.lower().replace(' ', '')
    if kind == 'attribute':
        if low in ATTRIBUTES:
            return low
        mine = next((a['id'] for a in data['attributes'] if a['id'].lower() == sid.lower()), None)
    else:
        if low in SKILLS:
            return low
        mine = next((s['id'] for s in data['skills'] if s['id'].lower() == sid.lower()), None)
    if not mine:
        raise EditError('%s is not a %s of the game\'s or yours.' % (sid or 'That', kind))
    return mine


def _clean_happen(db, e):
    """When this, then that (Create > When... then...): something the player does (uses an item, activates a thing, reads
    a book), only if (near water, once a day, a chance that grows with a skill or attribute), then what happens (a skill
    rises, items are given, a blessing or a patron's lasting bonus that grows with a stat, a spell, a line). The
    examples' building block: Fishing, Piety (2026-11-02, the user's ideas for showing what OpenMW 0.52 opens up)."""
    data = raw(db)
    name = _txt(e.get('name'), 48)
    if not name:
        raise EditError('Give it a name.')
    when = (e.get('when') or 'use').lower()
    if when not in HAPPEN_WHEN:
        raise EditError('It happens when the player uses, activates or reads something.')
    objs = []
    for i in _ids(e.get('ids'), 600):              # (every plant of the game and Tamriel Data, for Foraging)
        ri = db.resolve_id(i)
        if ri is None:
            raise EditError('There is nothing called %s.' % i)
        t = db.recs[ri][0]
        if when == 'read' and t != 'BOOK':
            raise EditError('%s is not a book.' % i)
        if when == 'use' and t in ('NPC_', 'CREA', 'ACTI', 'DOOR', 'CONT', 'STAT', 'SPEL', 'CELL', 'LAND'):
            raise EditError('%s is not an item the player uses.' % i)
        objs.append(db.recs[ri][1])
    if not objs:
        raise EditError('Say what sets it off.')
    out = {'id': _id(name, e.get('id')), 'name': name, 'when': when, 'ids': objs, 'water': bool(e.get('water')),
           'daily': bool(e.get('daily')), 'once': bool(e.get('once')), 'chance': _num(e.get('chance'), 'The chance', 0, 100, 100),
           'miss': _txt(e.get('miss'), 200), 'by': None, 'then': []}
    by = e.get('by') or {}
    if by.get('stat'):
        kind = 'attribute' if by.get('kind') == 'attribute' else 'skill'
        out['by'] = {'kind': kind, 'stat': _stat(db, data, kind, by['stat']), 'per': _num(by.get('per'), 'The chance a point', 0, 10, 0.5)}
    for t in e.get('then') or ():
        do = (t.get('do') or '').lower()
        if do not in HAPPEN_DO:
            continue
        a = {'do': do}
        if do == 'raise':
            a['skill'] = _stat(db, data, 'skill', t.get('skill'))
            a['gain'] = _num(t.get('gain'), 'The gain', 0.01, 100, 1)
        elif do == 'give' and str(t.get('id') or '').strip() == '*':
            # (one more of what the thing activated holds: a plant's own ingredient, for Foraging)
            if when != 'activate':
                raise EditError('"One more of what it holds" is for things the player activates (plants, chests).')
            a['id'] = '*'
            a['count'] = int(_num(t.get('count'), 'How many', 1, 100, 1))
        elif do == 'give':
            ri = db.resolve_id(_txt(t.get('id'), 64))
            if ri is None or db.recs[ri][0] in ('NPC_', 'CREA', 'ACTI', 'DOOR', 'CONT', 'STAT', 'SPEL', 'CELL', 'LAND', 'LEVC'):
                raise EditError('%s is not an item to give.' % (t.get('id') or 'That'))
            a['id'] = db.recs[ri][1]
            a['count'] = int(_num(t.get('count'), 'How many', 1, 100, 1))
        elif do in ('bless', 'patron'):
            kind = 'attribute' if t.get('kind') == 'attribute' else 'skill'
            a['kind'], a['stat'] = kind, _stat(db, data, kind, t.get('stat'))
            a['amount'] = _num(t.get('amount'), 'The bonus', -100, 100, 5)
            sk = t.get('scale') or {}
            if sk.get('stat'):
                k2 = 'attribute' if sk.get('kind') == 'attribute' else 'skill'
                a['scale'] = {'kind': k2, 'stat': _stat(db, data, k2, sk['stat']), 'per': _num(sk.get('per'), 'The bonus a point', 0, 10, 0.1)}
            if do == 'bless':
                a['hours'] = _num(t.get('hours'), 'How long', 0.1, 720, 24)
            else:
                a['group'] = re.sub(r'[^a-z0-9_]+', '', (_txt(t.get('group'), 32) or 'patron').lower()) or 'patron'
        elif do == 'cast':
            ri = db.resolve_id(_txt(t.get('spell'), 64))
            if ri is None or db.recs[ri][0] != 'SPEL':
                raise EditError('There is no spell called %s.' % (t.get('spell') or 'that'))
            a['spell'] = db.recs[ri][1]
        elif do == 'say':
            a['text'] = _txt(t.get('text'), 200)
            if not a['text']:
                continue
        out['then'].append(a)
    if not out['then']:
        raise EditError('Say what happens.')
    out['then'] = out['then'][:12]
    return out


def _effect_ids(db):
    """{OpenMW effect id (lower case): {name, skill, attribute}}: the game's effects by their OpenMW ids, Tamriel
    Data's and your own (for ingredients)."""
    out = {}
    try:
        import myeffects
        for t in myeffects._vanilla(db).values():
            out[t['key']] = {'name': t.get('name') or t['key'], 'skill': bool(t.get('skill')), 'attribute': bool(t.get('attribute'))}
    except Exception:
        pass
    try:
        import tdeffects
        for e in tdeffects.effects(db):
            out[e['index'].lower()] = {'name': e['name'] + (' (yours)' if e.get('mine') else ' (Tamriel Data)'), 'skill': False, 'attribute': False}
    except Exception:
        pass
    return out


def _make_ingredient(db, e):
    """A new ingredient (the Ingredients tab's "a new one"): a copy of the one it looks like, with its own name, model,
    icon, weight and value, and the game's own effects written into its record too, so 0.51 brews those. Its
    other effects come from the load script, as for any ingredient. Returns its ID. No commit."""
    import struct
    import items
    from esm import iter_subrecords
    from project import join_subs, zs
    name = _txt(e.get('name'), 31)
    if not name:
        raise EditError('Give the ingredient a name.')
    look = _txt(e.get('look'), 64) or 'ingred_bread_01'
    ti = db.resolve_id(look)
    if ti is None or db.recs[ti][0] != 'INGR':
        raise EditError('%s is not an ingredient to take the look from.' % look)
    new_id = items._check_new_id(db, 'INGR', e.get('new_id') or ('ws_ingred_' + re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_'))[:31])
    tr = db.recs[ti]
    _t, _f, data = db.files[tr[3]].record_at(tr[4])
    subs = [(t, bytes(v)) for t, v in iter_subrecords(data) if t != 'SCRI']
    keys = {}
    try:
        import myeffects
        keys = {t['key']: i for i, t in myeffects._vanilla(db).items()}
    except Exception:
        pass
    eff, sk, at = [-1] * 4, [-1] * 4, [-1] * 4
    for n_, x in enumerate((e.get('effects') or [])[:4]):
        k = (x.get('id') or '').strip().lower()
        if k in keys:
            eff[n_] = keys[k]
            if x.get('skill') in SKILLS:
                sk[n_] = SKILLS.index(x['skill'])
            if x.get('attribute') in ATTRIBUTES:
                at[n_] = ATTRIBUTES.index(x['attribute'])
    weight = _num(e.get('weight'), 'The weight', 0, 1000, 0.1)
    value = int(_num(e.get('value'), 'The value', 0, 1e6, 1))
    irdt = struct.pack('<fi4i4i4i', weight, value, *eff, *sk, *at)
    out = []
    for t, v in subs:
        if t == 'NAME':
            v = zs(new_id)
        elif t == 'FNAM':
            v = zs(name)
        elif t == 'MODL' and _txt(e.get('model'), 200):
            v = zs(_txt(e.get('model'), 200))
        elif t == 'ITEX' and _txt(e.get('icon'), 200):
            v = zs(_txt(e.get('icon'), 200))
        elif t == 'IRDT':
            v = irdt
        out.append((t, v))
    if not any(t == 'FNAM' for t, _v in out):
        out.insert(2, ('FNAM', zs(name)))
    db.project.set_record('INGR', new_id.lower(), 0, join_subs(out), created=True)
    return new_id


def _clean_ingredient(db, e, made=None):
    """An ingredient's four effects, any of them yours or Tamriel Data's, set as the game loads (OpenMW 0.52):
    alchemy brews your own effects."""
    iid = _txt(e.get('id'), 64)
    ri = db.resolve_id(iid) if iid and not made else None
    if not made and (ri is None or db.recs[ri][0] != 'INGR'):
        raise EditError('%s is not an ingredient.' % (iid or 'That'))
    E = _effect_ids(db)
    effs = []
    for x in (e.get('effects') or [])[:4]:
        eid = (x.get('id') or '').strip().lower()
        if not eid:
            continue
        if eid not in E:
            raise EditError('%s is not a magic effect the Workshop knows.' % eid)
        row = {'id': eid}
        if E[eid]['attribute'] and x.get('attribute'):
            row['attribute'] = str(x['attribute']).lower()
        if E[eid]['skill'] and x.get('skill'):
            row['skill'] = str(x['skill']).lower()
        effs.append(row)
    if not effs:
        raise EditError('Give it at least one effect.')
    if made:            # (just made by _make_ingredient: not looked up by ID until the change is kept)
        return {'id': made, 'name': _txt(e.get('name'), 31) or made, 'effects': effs}
    return {'id': db.recs[ri][1], 'name': db.recs[ri][1], 'effects': effs}


def _clean_look(db, e):
    """A line shown while the player looks at a thing (OpenMW 0.52's focus): every copy of it, or only in one place."""
    oid = _txt(e.get('object'), 64)
    ri = db.resolve_id(oid) if oid else None
    if ri is None:
        raise EditError('There is nothing called %s.' % (oid or 'that'))
    text = _txt(e.get('text'), 300)
    if not text:
        raise EditError('Write what it says.')
    cell = _txt(e.get('cell'), 64)
    name = _txt(e.get('name'), 48) or text[:40]
    return {'id': _id(name, e.get('id')) if e.get('id') else _id(name, None), 'name': name, 'object': db.recs[ri][1], 'cell': cell, 'text': text}


def lists_by_script(db):
    """Does the mod add to the game's levelled lists by its load script (OpenMW 0.52) rather than replacing them?"""
    return bool(raw(db)['options'].get('lists_by_script')) and bool(db.project and db.project.lua_allowed())


def set_option(db, name, value):
    _require_project(db)
    if name != 'lists_by_script':
        raise EditError('Unknown option %s.' % name)
    if value and not db.project.lua_allowed():
        raise EditError('This needs the mod as an .omwaddon (a plain .esp carries no scripts): Save as... on My mod.')
    data = raw(db)
    data['options'][name] = bool(value)
    _write(db, data)
    commit(db, "%s adding to the game's lists by script" % ('Turned on' if value else 'Turned off'))
    return read(db)


def add_to_list(db, lid, eid, level):
    """One more entry in a game list's additions (for the Forge and the like, when lists_by_script). No commit."""
    data = raw(db)
    cur = next((x for x in data['lists'] if x['id'].lower() == lid.lower()), None)
    adds = list((cur or {}).get('add') or [])
    if any(a['id'].lower() == eid.lower() for a in adds):
        return False
    adds.append({'id': eid, 'level': level})
    clean = _clean_list(db, {'id': lid, 'add': adds})
    data['lists'] = [x for x in data['lists'] if x['id'].lower() != lid.lower()] + [clean]
    _write(db, data)
    return True


def save(db, kind, e, old_id=None):
    """Make or change one of the mod's skills, attributes or weathers. Writes the scripts. One step."""
    _require_project(db)
    if kind not in KINDS:
        raise EditError('Unknown kind %s.' % kind)
    if not db.project.lua_allowed():
        raise EditError('Your own skills, attributes and weathers are made by OpenMW Lua scripts, which a plain .esp can\'t '
                        'carry: use Save as… on My mod to make the mod an .omwaddon first.')
    data = raw(db)
    lst = data[kind]
    old = (old_id or '').lower()
    made = None
    if kind == 'ingredients' and e.get('new') and not old:
        made = _make_ingredient(db, e)
        e = dict(e, id=made)
    clean = _clean_ingredient(db, e, made) if made else _clean(db, kind, e)
    rest = [x for x in lst if x['id'].lower() != old]
    taken = {x['id'].lower() for k in KINDS for x in data[k] if not (k == kind and x['id'].lower() == old)}
    if clean['id'].lower() in taken or (kind == 'attributes' and clean['id'].lower() in ATTRIBUTES) \
            or (kind == 'weathers' and clean['id'].lower() in WEATHERS):
        raise EditError('Something already has the ID %s.' % clean['id'])
    pos = next((n for n, x in enumerate(lst) if x['id'].lower() == old), len(rest))
    rest.insert(min(pos, len(rest)), clean)
    data[kind] = rest
    if kind == 'attributes' and old and old != clean['id'].lower():
        for s in data['skills']:
            if s['attribute'].lower() == old:
                s['attribute'] = clean['id']
    _write(db, data)
    what = kind[:-1]
    if made:
        commit(db, 'Made the ingredient "%s" (%s)' % (_txt(e.get('name'), 31), made))
        return dict(read(db), saved=clean)
    commit(db, '%s the %s "%s" (%s)' % ('Changed' if old else 'Made', what, clean['name'], clean['id']))
    return dict(read(db), saved=clean)


def delete(db, kind, rid):
    _require_project(db)
    data = raw(db)
    gone = [x for x in data.get(kind) or () if x['id'].lower() == (rid or '').lower()]
    if not gone:
        raise EditError('There is no %s of yours called %s.' % (kind[:-1], rid))
    if kind == 'skills':
        try:
            import myeffects
            users = [e['name'] for e in myeffects.effects_raw(db) if (e.get('school') or '').lower() == rid.lower()]
        except Exception:
            users = []
        if users:
            raise EditError('%s is the school of %s. Give %s another school first.' % (gone[0]['name'], ', '.join(users[:4]),
                                                                                    'them' if len(users) > 1 else 'it'))
    if kind == 'attributes':
        users = [s['name'] for s in data['skills'] if s['attribute'].lower() == rid.lower()]
        if users:
            raise EditError('%s governs %s. Give %s another attribute first.' % (gone[0]['name'], ', '.join(users[:4]),
                                                                                'them' if len(users) > 1 else 'it'))
    data[kind] = [x for x in data[kind] if x['id'].lower() != rid.lower()]
    _write(db, data)
    commit(db, 'Removed the %s "%s"' % (kind[:-1], gone[0]['name']))
    return read(db)


# ------------------------------------------------------------------ the scripts
def _lua(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return '%g' % v
    if isinstance(v, (list, tuple)):
        return '{ %s }' % ', '.join(_lua(x) for x in v)
    if isinstance(v, dict):
        return '{ %s }' % ', '.join('[%s] = %s' % (_lua(str(k)), _lua(x)) for k, x in v.items())
    import myeffects
    return myeffects.lua_str(v)          # (Lua has no \u escapes: control characters as \ddd too)


def _put(db, name, kind, text, first=False):
    p = db.project
    s = _script(db, name)
    if text is None:
        if s is not None:
            p.lua.remove(s)
        return
    if s is None:
        s = {'name': name, 'kind': kind, 'attach': []}
        if first:
            p.lua.insert(0, s)
        else:
            p.lua.append(s)
    s['kind'], s['text'] = kind, text
    if first and p.lua.index(s) != 0:
        p.lua.remove(s)
        p.lua.insert(0, s)                       # (before my_effects: a skill of yours may be an effect's school)


def _write(db, data):
    if not any(data[k] for k in KINDS) and not any((data.get('options') or {}).values()):
        for n in (SCRIPT, GLOBAL, PLAYER, ACTOR, LOOK, HAPPEN, HAPPEN_PLAYER):
            _put(db, n, None, None)
        return
    # (in a --[[ ]] comment: a ]] in a name or description would end it; inside strings only, with indent)
    body = json.dumps(dict({k: data[k] for k in KINDS}, options=data.get('options') or {}), indent=1, ensure_ascii=False).replace(']]', ']\\u005d')
    _put(db, SCRIPT, 'LOAD', LOAD_LUA % {'begin': BEGIN, 'json': body, 'end': END, 'data': _lua({k: data[k] for k in KINDS})}, first=True)
    rises = any(s.get('rises') for s in data['skills'])
    need_global = rises or any(w.get('regions') for w in data['weathers']) or bool(data['loot']) or bool(data['traps'])
    # (the event this mod's own: with one name for all, every mod's player script answered every mod's, the lesson of
    # Altvaddert's summons, myeffects.own_events)
    ev = 'WS_MyRecordsRaise_%s' % db.project.lua_slug()
    _put(db, GLOBAL, 'GLOBAL', GLOBAL_LUA % {'data': _lua({'skills': data['skills'], 'weathers': data['weathers'], 'loot': data['loot'], 'traps': data['traps']}), 'event': ev}
         if need_global else None)
    looks = {}
    for l in data['looks']:
        looks.setdefault(l['object'].lower(), []).append({'cell': (l.get('cell') or '').lower(), 'text': l['text']})
    _put(db, LOOK, 'PLAYER', LOOK_LUA % {'data': _lua(looks)} if looks else None)
    _put(db, PLAYER, 'PLAYER', PLAYER_LUA % {'event': ev} if rises else None)
    people = [{'skill': s['id'], 'how': p['how'], 'id': p['id'].lower(), 'value': p['value']}
              for s in data['skills'] for p in s.get('people') or ()]
    _put(db, ACTOR, 'NPC', ACTOR_LUA % {'data': _lua(people)} if people else None)
    # when this, then that: the world's half hears uses and activations, the player's does the rest (and reading)
    hp = data.get('happens') or []
    slug = db.project.lua_slug()
    ev = {'event': 'WS_Happen_%s' % slug, 'give': 'WS_HappenGive_%s' % slug}
    _put(db, HAPPEN, 'GLOBAL', HAPPEN_LUA % dict(ev, data=_lua(hp)) if hp else None)
    _put(db, HAPPEN_PLAYER, 'PLAYER', HAPPEN_PLAYER_LUA % dict(ev, data=_lua(hp)) if hp else None)


LOAD_LUA = '''-- Made by Morrowind Workshop: your own skills, attributes and weathers (Create > New skill / attribute / weather).
-- Needs OpenMW 0.52 or newer (openmw.content's skills, attributes and weathers); older, nothing is made.
-- Each field is set on its own: one OpenMW refuses is named in openmw.log and the rest still made.
%(begin)s
%(json)s
%(end)s
local content = require('openmw.content')
local okUtil, util = pcall(require, 'openmw.util')

local data = %(data)s

local function say(what, id, err)
  print('[Workshop] ' .. what .. ' ' .. tostring(id) .. ': ' .. tostring(err))
end

local function set(list, id, field, value)
  local ok, err = pcall(function() list.records[id][field] = value end)
  if not ok then say('could not set ' .. field .. ' of', id, err) end
end

local function colour(c)
  if not okUtil or not c then return nil end
  return util.color.rgb(c[1] / 255, c[2] / 255, c[3] / 255)
end

local function make(list, id, base)
  local ok, err = pcall(function() list.records[id] = base end)
  if not ok then say('could not make', id, err) end
  return ok
end

local function attributes()
  for _, a in ipairs(data.attributes or {}) do
    if make(content.attributes, a.id, { name = a.name }) then
      if a.description ~= '' then set(content.attributes, a.id, 'description', a.description) end
      if a.icon ~= '' then set(content.attributes, a.id, 'icon', a.icon) end
      set(content.attributes, a.id, 'werewolfValue', a.werewolf)
    end
  end
end

local function skills()
  for _, s in ipairs(data.skills or {}) do
    if make(content.skills, s.id, { name = s.name, attribute = s.attribute, specialization = s.specialization }) then
      if s.description ~= '' then set(content.skills, s.id, 'description', s.description) end
      if s.icon ~= '' then set(content.skills, s.id, 'icon', s.icon) end
      set(content.skills, s.id, 'skillGain', s.gains)
      for _, b in ipairs(s.books or {}) do set(content.books, b, 'skill', s.id) end
      set(content.skills, s.id, 'werewolfValue', s.werewolf)
      if s.school then
        -- a school of magic: like one of the game's six, with your own sounds where given
        local sc = { name = s.name }
        pcall(function()
          local base = content.skills.records[s.school.like].school
          for _, k in ipairs({ 'areaSound', 'boltSound', 'castSound', 'failureSound', 'hitSound', 'autoCalcMax' }) do sc[k] = base[k] end
        end)
        for k, v in pairs(s.school) do if k ~= 'like' and v ~= 0 then sc[k] = v end end
        set(content.skills, s.id, 'school', sc)
      end
    end
  end
end

-- a list with one more, or with it in place of another
local function listWith(list, add, instead)
  local out, put = {}, false
  local n = 0
  pcall(function() n = #list end)
  for i = 1, n do
    local v = list[i]
    if instead and not put and tostring(v):lower() == instead then out[#out + 1] = add; put = true else out[#out + 1] = v end
  end
  if not put then out[#out + 1] = add end
  return out
end

local function mapWith(map, key, value)
  local out = {}
  pcall(function() for k, v in pairs(map) do out[k] = v end end)
  out[key] = value
  return out
end

-- where your skills and attributes count: classes, factions, races (the game's or your mod's)
local function links()
  for _, s in ipairs(data.skills or {}) do
    for _, l in ipairs(s.links or {}) do
      local ok, err = pcall(function()
        if l.how == 'major' or l.how == 'minor' then
          local rec = content.classes.records[l.id]
          local field = l.how == 'major' and 'majorSkills' or 'minorSkills'
          rec[field] = listWith(rec[field], s.id, l.instead)
        elseif l.how == 'faction' then
          local rec = content.factions.records[l.id]
          rec.skills = listWith(rec.skills, s.id, l.instead)
        elseif l.how == 'race' then
          local rec = content.races.records[l.id]
          rec.skills = mapWith(rec.skills, s.id, l.bonus)
        end
      end)
      if not ok then say('could not give ' .. s.id .. ' to', l.id, err) end
    end
  end
  for _, a in ipairs(data.attributes or {}) do
    for _, l in ipairs(a.links or {}) do
      local ok, err = pcall(function()
        if l.how == 'class' then
          local rec = content.classes.records[l.id]
          rec.attributes = listWith(rec.attributes, a.id, l.instead)
        elseif l.how == 'faction' then
          local rec = content.factions.records[l.id]
          rec.attributes = listWith(rec.attributes, a.id, l.instead)
        elseif l.how == 'race' then
          local rec = content.races.records[l.id]
          rec.attributes = mapWith(rec.attributes, a.id, { male = l.male, female = l.female })
        end
      end)
      if not ok then say('could not give ' .. a.id .. ' to', l.id, err) end
    end
  end
end

-- additions to the game's levelled lists: what other mods add stays (a list your mod rewrote replaced theirs)
local function lists()
  for _, l in ipairs(data.lists or {}) do
    local ok, err = pcall(function()
      local list = l.kind == 'creatures' and content.levelledCreatures or content.levelledItems
      local field = l.kind == 'creatures' and 'creatures' or 'items'
      local rec = list.records[l.id]
      local out = {}
      local n = 0
      pcall(function() n = #rec[field] end)
      for i = 1, n do local e = rec[field][i]; out[#out + 1] = { id = e.id, level = e.level } end
      for _, a in ipairs(l.add) do out[#out + 1] = { id = a.id, level = a.level } end
      rec[field] = out
    end)
    if not ok then say('could not add to the list', l.id, err) end
  end
end

-- ingredients with the effects you gave them, the game's, Tamriel Data's or your own: alchemy brews them
local function ingredients()
  for _, g in ipairs(data.ingredients or {}) do
    local ok, err = pcall(function()
      local effs = {}
      for _, e in ipairs(g.effects) do effs[#effs + 1] = { id = e.id, affectedAttribute = e.attribute, affectedSkill = e.skill } end
      content.ingredients.records[g.id].effects = effs
    end)
    if not ok then say('could not set the effects of', g.id, err) end
  end
end

local function weathers()
  for _, w in ipairs(data.weathers or {}) do
    local tpl = content.weathers.records[w.template]
    if make(content.weathers, w.id, { template = tpl }) then
      for field, times in pairs(w.colours or {}) do
        local t = {}
        for when, c in pairs(times) do t[when] = colour(c) end
        set(content.weathers, w.id, field, t)
      end
      for field, value in pairs(w.fields or {}) do set(content.weathers, w.id, field, value) end
    end
  end
end

return {
  engineHandlers = {
    onContentFilesLoaded = function()
      if not content.skills or not content.attributes or not content.weathers then
        print('[Workshop] your own skills, attributes and weathers need OpenMW 0.52 or newer')
        return
      end
      attributes()
      skills()
      links()
      lists()
      ingredients()
      weathers()
    end,
  },
}
'''

ACTOR_LUA = '''-- Made by Morrowind Workshop: who has your own skills (Create > New skill > Who has it). Raised to the value
-- given the first time each is met, never lowered; needs OpenMW 0.52 (skills by their ID).
local self = require('openmw.self')
local types = require('openmw.types')

local people = %(data)s
local done = false

local function fits(p)
  if p.how == 'npc' then return tostring(self.recordId):lower() == p.id end
  local ok, rec = pcall(function() return types.NPC.record(self) end)
  if not ok or not rec then return false end
  if p.how == 'class' then return tostring(rec.class or ''):lower() == p.id end
  if p.how == 'faction' then
    local okF, fs = pcall(types.NPC.getFactions, self)
    if okF and fs then for _, f in ipairs(fs) do if tostring(f):lower() == p.id then return true end end end
  end
  return false
end

local function give()
  if done then return end
  done = true
  for _, p in ipairs(people) do
    if fits(p) then
      local ok, err = pcall(function()
        local stat = types.NPC.stats.skills[p.skill](self)
        if stat.base < p.value then stat.base = p.value end
      end)
      if not ok then print('[Workshop] could not give ' .. p.skill .. ': ' .. tostring(err)) end
    end
  end
end

return {
  engineHandlers = {
    onActive = give,
    onSave = function() return { done = done } end,
    onLoad = function(d) if d then done = d.done end end,
  },
}
'''

PLAYER_LUA = '''-- Made by Morrowind Workshop: your own skills rising as you use things (Create > New skill).
local I = require('openmw.interfaces')

return {
  eventHandlers = {
    ['%(event)s'] = function(e)
      local ok, err = pcall(function() I.SkillProgression.skillUsed(e.skill, { skillGain = e.gain, useType = 0 }) end)
      if not ok then print('[Workshop] could not raise ' .. tostring(e.skill) .. ': ' .. tostring(err)) end
    end,
  },
}
'''

GLOBAL_LUA = '''-- Made by Morrowind Workshop: how your own skills rise, and where your own weathers come (Create > New skill / weather).
local core = require('openmw.core')
local world = require('openmw.world')
local types = require('openmw.types')
local util = require('openmw.util')
local I = require('openmw.interfaces')
local okTime, time = pcall(require, 'openmw_aux.time')

local data = %(data)s

-- a skill rises when the player uses or activates the things named (each with its gain)
local function raise(actor, skill, gain)
  if actor and actor.type == types.Player then
    actor:sendEvent('%(event)s', { skill = skill, gain = gain })
  end
end

local byUse, byActivate = {}, {}
for _, s in ipairs(data.skills or {}) do
  for _, r in ipairs(s.rises or {}) do
    for _, id in ipairs(r.ids) do
      local list = (r.how == 'activate') and byActivate or byUse
      local key = id:lower()
      list[key] = list[key] or {}
      table.insert(list[key], { skill = s.id, gain = r.gain })
    end
  end
end

local function used(object, actor)
  local rs = byUse[(object.recordId or ''):lower()]
  if rs then for _, r in ipairs(rs) do raise(actor, r.skill, r.gain) end end
end

local function activated(object, actor)
  local rs = byActivate[(object.recordId or ''):lower()]
  if rs then for _, r in ipairs(rs) do raise(actor, r.skill, r.gain) end end
end

if I.ItemUsage and next(byUse) then
  for _, t in ipairs({ types.Miscellaneous, types.Potion, types.Ingredient, types.Book, types.Weapon, types.Armor, types.Clothing, types.Apparatus, types.Lockpick, types.Probe, types.Repair, types.Light }) do
    pcall(function() I.ItemUsage.addHandlerForType(t, function(o, a) used(o, a) end) end)
  end
end
if I.Activation and next(byActivate) then
  I.Activation.addHandlerForType(types.Activator, function(o, a) activated(o, a) end)
  for _, t in ipairs({ types.Container, types.Door, types.NPC, types.Creature, types.Miscellaneous, types.Book, types.Light }) do
    pcall(function() I.Activation.addHandlerForType(t, function(o, a) activated(o, a) end) end)
  end
end

-- a weather of yours in the regions picked: OpenMW 0.52 gives it its share of each region's own weather table, as
-- the game's ash storms have theirs (RegionRecord.setProbability), the others made smaller to keep a hundred. Runtime
-- only, so set again on every load; done once, it changes nothing the next time.
local tables = false
local function weatherTables()
  if not (core.regions and core.regions.records) then return false end
  local byRegion = {}
  for _, w in ipairs(data.weathers or {}) do
    local rec = core.weather.records[w.id]
    local wid = (rec and not w.night) and tostring(rec.recordId or w.id) or nil
    if wid then
      for _, r in ipairs(w.regions or {}) do
        local k = tostring(r.region):lower()
        byRegion[k] = byRegion[k] or {}
        byRegion[k][wid] = r.chance
      end
    end
  end
  local done = false
  for rid, mine in pairs(byRegion) do
    local reg = core.regions.records[rid]
    if reg and reg.setProbability then
      local ok, err = pcall(function()
        local cur, want, others = reg.weatherProbabilities or {}, 0, 0
        for _, c in pairs(mine) do want = want + c end
        want = math.min(100, want)
        for wid, c in pairs(cur) do if mine[wid] == nil then others = others + c end end
        for wid, c in pairs(cur) do
          if mine[wid] == nil then reg:setProbability(wid, others > 0 and c * (100 - want) / others or 0) end
        end
        for wid, c in pairs(mine) do reg:setProbability(wid, c) end
      end)
      if ok then done = true else print('[Workshop] weather in ' .. rid .. ': ' .. tostring(err)) end
    end
  end
  return done
end

-- weathers only at night: a chance each hour after dark in their regions, and cleared at dawn where the player is
local function nightHour()
  local h = (core.getGameTime() %% 86400) / 3600
  local dark = h >= 20 or h < 5
  local player = world.players[1]
  for _, w in ipairs(data.weathers or {}) do
    local rec = w.night and core.weather.records[w.id]
    if rec then
      for _, r in ipairs(w.regions or {}) do
        if dark then
          if math.random() * 100 < r.chance then pcall(core.weather.changeWeather, r.region, rec) end
        elseif player then
          pcall(function()
            local cur = core.weather.getCurrent(player.cell)
            if cur and tostring(cur.recordId):lower() == tostring(rec.recordId):lower()
               and tostring(player.cell.region or ''):lower() == r.region:lower() then
              core.weather.changeWeather(r.region, core.weather.records['clear'])
            end
          end)
        end
      end
    end
  end
end

-- before that (or where a region has no table), a chance each game hour
local function weatherHour()
  nightHour()
  if tables then return end
  for _, w in ipairs(data.weathers or {}) do
    local rec = (not w.night) and core.weather.records[w.id]
    if rec then
      for _, r in ipairs(w.regions or {}) do
        if math.random() * 100 < r.chance then
          pcall(core.weather.changeWeather, r.region, rec)
        end
      end
    end
  end
end

-- loot by rules: picked in play from every record the load order has (other mods' too), into the containers named
-- the first time each is opened and onto the people named the first time each is met
local TYPES = { weapon = types.Weapon, armor = types.Armor, clothing = types.Clothing, potion = types.Potion, ingredient = types.Ingredient,
                book = types.Book, misc = types.Miscellaneous, apparatus = types.Apparatus, lockpick = types.Lockpick, probe = types.Probe,
                repair = types.Repair, light = types.Light }
local pools, given = {}, {}
local byContainer, byActor = {}, {}
for _, r in ipairs(data.loot or {}) do
  for _, c in ipairs(r.containers or {}) do local k = c:lower(); byContainer[k] = byContainer[k] or {}; table.insert(byContainer[k], r) end
  for _, c in ipairs(r.npcs or {}) do local k = c:lower(); byActor[k] = byActor[k] or {}; table.insert(byActor[k], r) end
end

local function poolOf(r)
  if pools[r.id] then return pools[r.id] end
  local out = {}
  for _, w in ipairs(r.what) do
    local T = TYPES[w]
    if T then
      for _, rec in ipairs(T.records) do
        local v = rec.value or 0
        local name = rec.name or ''
        if name ~= '' and v >= (r.min or 0) and ((r.max or 0) == 0 or v <= r.max) then
          local hay = (tostring(rec.id) .. ' ' .. name):lower()
          local ok = #(r.words or {}) == 0
          for _, word in ipairs(r.words or {}) do if hay:find(word, 1, true) then ok = true; break end end
          if ok then out[#out + 1] = { id = rec.id, value = v } end
        end
      end
    end
  end
  pools[r.id] = out
  return out
end

local function pick(r)
  local pool = poolOf(r)
  local fit = pool
  if (r.perlevel or 0) > 0 then
    local lv = 1
    pcall(function() lv = types.Actor.stats.level(world.players[1]).current end)
    fit = {}
    for _, e in ipairs(pool) do if e.value <= r.perlevel * lv then fit[#fit + 1] = e end end
    if #fit == 0 then fit = pool end
  end
  if #fit == 0 then return nil end
  return fit[math.random(#fit)].id
end

local function giveTo(inv, rules)
  for _, r in ipairs(rules) do
    if math.random() * 100 < (r.chance or 100) then
      for i = 1, (r.count or 1) do
        local id = pick(r)
        if id then pcall(function() world.createObject(id, 1):moveInto(inv) end) end
      end
    end
  end
end

if I.Activation and next(byContainer) then
  I.Activation.addHandlerForType(types.Container, function(o, actor)
    local rules = byContainer[tostring(o.recordId):lower()]
    if rules and not given[o.id] then
      given[o.id] = true
      local inv = types.Container.inventory(o)
      pcall(function() inv:resolve() end)
      giveTo(inv, rules)
    end
  end)
end

local hasWeather = false
for _, w in ipairs(data.weathers or {}) do if w.regions and #w.regions > 0 then hasWeather = true end end
if hasWeather and okTime then
  time.runRepeatedly(weatherHour, time.hour, { type = time.GameTime })
end

-- containers with loot of a rule that glows: they glow until first opened (OpenMW 0.52's glow on containers)
local glowing = {}
for _, r in ipairs(data.loot or {}) do
  if r.glow then for _, c in ipairs(r.containers or {}) do glowing[c:lower()] = util.color.rgb(r.glow[1] / 255, r.glow[2] / 255, r.glow[3] / 255) end end
end
-- (round the player: OpenMW has no world.activeCells, so the containers of the player's cell, and outside those
-- within reach across cell borders)
local function glowTick()
  local player = world.players[1]
  if not (player and player.cell) then return end
  local list = nil
  if player.cell.isExterior and world.getObjectsInRange then
    pcall(function() list = world.getObjectsInRange(player.position, 6000) end)
  end
  for _, o in ipairs(list or player.cell:getAll(types.Container)) do
    if types.Container.objectIsInstance(o) then
      local c = glowing[tostring(o.recordId):lower()]
      if c and not given[o.id] then pcall(function() o:sendEvent('AddGlow', { color = c, duration = 2.2 }) end) end
    end
  end
end
if next(glowing) and okTime then
  time.runRepeatedly(glowTick, 2 * time.second)
end

-- traps: a spell strikes whoever opens, takes or uses the things named (once, or every time)
local traps, sprung = {}, {}
for _, t in ipairs(data.traps or {}) do
  for _, id in ipairs(t.objects or {}) do local k = id:lower(); traps[k] = traps[k] or {}; table.insert(traps[k], t) end
end

local function inflictAll(id, target)
  local rec = core.magic.spells.records[id]
  if not rec then return end
  if I.SpellCasting and I.SpellCasting.inflict then
    local seen = {}
    for _, e in ipairs(rec.effects) do
      if not seen[e.range] then seen[e.range] = true; pcall(I.SpellCasting.inflict, { id = id }, target, e.range) end
    end
    return
  end
  local idx = {}
  for i = 1, #rec.effects do idx[i] = i - 1 end
  types.Actor.activeSpells(target):add({ id = id, effects = idx, caster = target })
end

local function sprang(o, actor)
  local list = traps[tostring(o.recordId):lower()]
  if not (list and actor and types.Actor.objectIsInstance(actor)) then return end
  local here = ''
  pcall(function() here = (o.cell.name or ''):lower() end)
  for _, t in ipairs(list) do
    local key = tostring(o.id) .. ':' .. t.id
    if (t.cell == '' or t.cell:lower() == here) and not (t.once and sprung[key]) then
      sprung[key] = true
      local pos = o.position
      inflictAll(t.spell, actor)
      -- (its area, if it has one, goes off where the thing is)
      if I.SpellCasting and I.SpellCasting.explodeSpell then
        pcall(I.SpellCasting.explodeSpell, { id = t.spell }, { position = pos, ignore = { [actor.id] = true } })
      end
      if t.text ~= '' and types.Player.objectIsInstance(actor) then actor:sendEvent('ShowMessage', { message = t.text }) end
    end
  end
end

if I.Activation and next(traps) then
  for _, T in ipairs({ types.Container, types.Door, types.Activator, types.Miscellaneous, types.Book, types.Weapon, types.Armor,
                       types.Clothing, types.Light, types.Potion, types.Ingredient, types.Apparatus, types.Lockpick, types.Probe, types.Repair }) do
    pcall(function() I.Activation.addHandlerForType(T, function(o, a) sprang(o, a) end) end)
  end
end
if I.ItemUsage and next(traps) then
  for _, T in ipairs({ types.Miscellaneous, types.Book, types.Weapon, types.Armor, types.Clothing, types.Potion, types.Ingredient, types.Apparatus }) do
    pcall(function() I.ItemUsage.addHandlerForType(T, function(o, a) sprang(o, a) end) end)
  end
end

return {
  engineHandlers = {
    onInit = function() if hasWeather then tables = weatherTables() end end,
    onActorActive = function(a)
      local rules = byActor[tostring(a.recordId):lower()]
      if rules and not given[a.id] and not types.Actor.isDead(a) then
        given[a.id] = true
        giveTo(types.Actor.inventory(a), rules)
      end
    end,
    onSave = function() return { given = given, sprung = sprung } end,
    onLoad = function(d)
      if d and d.given then given = d.given end
      if d and d.sprung then sprung = d.sprung end
      if hasWeather then tables = weatherTables() end
    end,
  },
}
'''

LOOK_LUA = '''-- Made by Morrowind Workshop: lines shown while the player looks at things (Create > New skill > Look at).
-- Needs OpenMW 0.52 (camera.getFocusRay); before it, nothing shows.
local camera = require('openmw.camera')
local ui = require('openmw.ui')
local util = require('openmw.util')

local LOOKS = %(data)s
local shown, el, t = nil, nil, 0

local function textFor(o)
  local list = LOOKS[tostring(o.recordId):lower()]
  if not list then return nil end
  local here = ''
  pcall(function() here = (o.cell.name or ''):lower() end)
  for _, e in ipairs(list) do
    if e.cell == '' or e.cell == here then return e.text end
  end
  return nil
end

return {
  engineHandlers = {
    onFrame = function(dt)
      t = t + dt
      if t < 0.15 then return end
      t = 0
      local text
      if camera.getFocusRay then
        local ok, hit = pcall(camera.getFocusRay)
        local o = ok and hit and hit.hitObject
        if o then text = textFor(o) end
      end
      if text == shown then return end
      if el then el:destroy(); el = nil end
      if text then
        el = ui.create({ layer = 'HUD', type = ui.TYPE.Text, props = {
          text = text, textSize = 18, textColor = util.color.rgb(0.95, 0.9, 0.75), textShadow = true,
          relativePosition = util.vector2(0.5, 0.8), anchor = util.vector2(0.5, 0.5), multiline = true, wordWrap = true, autoSize = true } })
      end
      shown = text
    end,
  },
}
'''


HAPPEN_LUA = '''-- Made by Morrowind Workshop: when this, then that (Create > When... then...). The world's half: hears the player
-- using and activating the things named and tells the player's half (my_records_happen_player), which decides; gives
-- the items and casts the spells it asks for.
local core = require('openmw.core')
local world = require('openmw.world')
local types = require('openmw.types')
local I = require('openmw.interfaces')

local data = %(data)s
local byUse, byActivate = {}, {}
for i, h in ipairs(data) do
  for _, id in ipairs(h.ids) do
    local list = (h.when == 'activate') and byActivate or (h.when == 'use' and byUse or nil)
    if list then local k = id:lower(); list[k] = list[k] or {}; table.insert(list[k], i) end
  end
end

-- (what a container holds as it is opened, its first ingredient else its first thing: "one more of what it holds")
local function holds(o)
  local id
  pcall(function()
    if not types.Container.objectIsInstance(o) then return end
    local inv = types.Container.inventory(o)
    if inv.resolve then inv:resolve() end
    local it = inv:getAll(types.Ingredient)[1] or inv:getAll()[1]
    if it then id = tostring(it.recordId) end
  end)
  return id
end

local function tell(list, o, actor)
  local hs = list[tostring(o.recordId):lower()]
  if hs and actor and types.Player.objectIsInstance(actor) then
    actor:sendEvent('%(event)s', { list = hs, rid = tostring(o.recordId):lower(), key = tostring(o.id), holds = holds(o) })
  end
end

if I.ItemUsage and next(byUse) then
  for _, T in ipairs({ types.Miscellaneous, types.Potion, types.Ingredient, types.Book, types.Weapon, types.Armor, types.Clothing,
                       types.Apparatus, types.Lockpick, types.Probe, types.Repair, types.Light }) do
    pcall(function() I.ItemUsage.addHandlerForType(T, function(o, a) tell(byUse, o, a) end) end)
  end
end
if I.Activation and next(byActivate) then
  for _, T in ipairs({ types.Activator, types.Container, types.Door, types.NPC, types.Creature, types.Miscellaneous, types.Book, types.Light }) do
    pcall(function() I.Activation.addHandlerForType(T, function(o, a) tell(byActivate, o, a) end) end)
  end
end

local function cast(id, target)
  local rec = core.magic.spells.records[id]
  if not rec then return end
  if I.SpellCasting and I.SpellCasting.inflict then
    local seen = {}
    for _, e in ipairs(rec.effects) do
      if not seen[e.range] then seen[e.range] = true; pcall(I.SpellCasting.inflict, { id = id }, target, e.range) end
    end
    return
  end
  local idx = {}
  for n = 1, #rec.effects do idx[n] = n - 1 end
  pcall(function() types.Actor.activeSpells(target):add({ id = id, effects = idx, caster = target }) end)
end

return {
  eventHandlers = {
    ['%(give)s'] = function(e)
      if not (e and e.player) then return end
      if e.id then pcall(function() world.createObject(e.id, e.count or 1):moveInto(types.Actor.inventory(e.player)) end) end
      if e.spell then cast(e.spell, e.player) end
    end,
  },
}
'''

HAPPEN_PLAYER_LUA = '''-- Made by Morrowind Workshop: when this, then that (Create > When... then...). The player's half: checks "only if"
-- (near water, once a day, once ever, a chance that grows with a skill or attribute), then raises skills, gives
-- blessings and a patron's lasting bonus (each growing with a stat), and asks the world's half for items and spells.
local self = require('openmw.self')
local types = require('openmw.types')
local core = require('openmw.core')
local util = require('openmw.util')
local I = require('openmw.interfaces')
local okUi, ui = pcall(require, 'openmw.ui')

local data = %(data)s
local last, blessings, patrons = {}, {}, {}

local function stat(kind, id)
  local ok, s = pcall(function()
    if kind == 'attribute' then return types.Actor.stats.attributes[id](self) end
    return types.NPC.stats.skills[id](self)
  end)
  if ok then return s end
end

local function value(kind, id)
  local s = stat(kind, id)
  if not s then return 0 end
  return s.modified or s.base or 0
end

local function bonus(a)
  local n = a.amount or 0
  if a.scale then n = n + value(a.scale.kind, a.scale.stat) * (a.scale.per or 0) end
  return math.floor(n + 0.5)
end

local function add(kind, id, n)
  local s = stat(kind, id)
  if s then pcall(function() s.modifier = s.modifier + n end) end
end

local function say(text) if text and text ~= '' and okUi then ui.showMessage(text) end end

-- standing by water: the land within a few steps dips under the water level, or (indoors) near it
local function nearWater()
  local cell = self.cell
  if not (cell and cell.hasWater) then return false end
  local wl, p = cell.waterLevel or 0, self.position
  if p.z - wl > 500 then return false end
  if not cell.isExterior then return p.z - wl < 250 end
  for _, d in ipairs({ { 0, 0 }, { 300, 0 }, { -300, 0 }, { 0, 300 }, { 0, -300 }, { 220, 220 }, { -220, 220 }, { 220, -220 }, { -220, -220 } }) do
    local ok, h = pcall(core.land.getHeightAt, util.vector3(p.x + d[1], p.y + d[2], p.z), cell)
    if ok and h and h < wl then return true end
  end
  return false
end

local function day() return math.floor(core.getGameTime() / 86400) end

local function happen(i, rid, key, held)
  local h = data[i]
  if not h then return end
  if h.water and not nearWater() then
    say(h.miss ~= '' and h.when == 'use' and 'There is no water here.' or nil)
    return
  end
  local k = h.id .. ':' .. (h.when == 'read' and rid or key)
  if h.once and last[k] then return end
  if h.daily and last[k] == day() then return end
  last[k] = h.once and true or day()
  -- skills rise for trying; the rest happens when the chance comes up
  for _, a in ipairs(h['then']) do
    if a['do'] == 'raise' then pcall(function() I.SkillProgression.skillUsed(a.skill, { skillGain = a.gain, useType = 0 }) end) end
  end
  local c = h.chance or 100
  if h.by then c = c + value(h.by.kind, h.by.stat) * (h.by.per or 0) end
  if math.random() * 100 >= c then say(h.miss); return end
  for _, a in ipairs(h['then']) do
    local d = a['do']
    if d == 'give' or d == 'cast' then
      local id = a.id
      if id == '*' then id = held end
      if id or a.spell then core.sendGlobalEvent('%(give)s', { player = self.object, id = id, count = a.count, spell = a.spell }) end
    elseif d == 'bless' then
      local n = bonus(a)
      add(a.kind, a.stat, n)
      table.insert(blessings, { kind = a.kind, stat = a.stat, n = n, untilT = core.getGameTime() + (a.hours or 24) * 3600 })
    elseif d == 'patron' then
      local old = patrons[a.group]
      if old then add(old.kind, old.stat, -old.n) end
      local n = bonus(a)
      add(a.kind, a.stat, n)
      patrons[a.group] = { kind = a.kind, stat = a.stat, n = n, from = h.id }
    elseif d == 'say' then
      say(a.text)
    end
  end
end

-- blessings wear off
local wait = 0
local function onUpdate(dt)
  wait = wait + dt
  if wait < 2 then return end
  wait = 0
  local now, keep = core.getGameTime(), {}
  for _, b in ipairs(blessings) do
    if now >= b.untilT then add(b.kind, b.stat, -b.n) else keep[#keep + 1] = b end
  end
  blessings = keep
end

local byRead = {}
for i, h in ipairs(data) do
  if h.when == 'read' then for _, id in ipairs(h.ids) do local k = id:lower(); byRead[k] = byRead[k] or {}; table.insert(byRead[k], i) end end
end

return {
  engineHandlers = {
    onUpdate = onUpdate,
    onSave = function() return { last = last, blessings = blessings, patrons = patrons } end,
    onLoad = function(d)
      if d then last = d.last or {}; blessings = d.blessings or {}; patrons = d.patrons or {} end
    end,
  },
  eventHandlers = {
    ['%(event)s'] = function(e) for _, i in ipairs(e.list or {}) do happen(i, e.rid, e.key, e.holds) end end,
    -- (a book or scroll opened: OpenMW's UI tells the player's scripts, with the book)
    UiModeChanged = function(e)
      if e and (e.newMode == 'Book' or e.newMode == 'Scroll') and e.arg then
        local rid = tostring(e.arg.recordId):lower()
        for _, i in ipairs(byRead[rid] or {}) do happen(i, rid, tostring(e.arg.id)) end
      end
    end,
  },
}
'''
