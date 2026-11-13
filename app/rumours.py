"""Rumours and quests from what was placed (docs/worldbuilding-next-2026-11.md, proposal 7): the places the mod made in
the marked cells talked about in the towns it made near them, and the dungeons a band holds made into simple quests.

What the game does (lab 2026-11-08, its dialogue): 413 of its places have a topic of their own (Sulipund, Agi Bay
Grotto, Ald Sotha), most of their lines telling the way ("Sulipund is further along the trail from Punabi") and said
by the people of a town near (a Cell condition, 343 lines, with a class 225) or by someone in particular; its 2,486
"latest rumors" lines are a town's (1,598 of them by Cell), and a third of them name a place.

So each dungeon the mod made (its outside door in the marked cells, its inside a Workshop ruin) gets:
- a topic of its own, its name, with a line for the people of each of the two nearest of the mod's towns within
  NEAR: where it lies from the town (a compass way and how far, and a named peak or lake by it) and who is there (read
  from its people and creatures: bandits, smugglers, necromancers, worshippers, the dead, Daedra, machines, beasts);
- a "latest rumors" line in those towns that teaches the topic;
- where a band of people holds it, a quest from the nearest town's publican (else a guard): talk of it, the band's
  leader dead, back for the reward, written by questmake as the Quest Board writes moves.
One change, one Undo."""
import math
import random
import re
import struct

import mapdata

NEAR = 40000.0                  # (a town this near a dungeon talks of it)
TOWNS_EACH = 2
QUESTS_PER_TOWN = 2
REWARD = (100, 25)              # (gold: this, and this a level of the band's leader)
UNDEAD = re.compile(r'skeleton|ghost|zombie|bonelord|bonewalker|draugr|wraith|lich|ancestor|dwarven_ghost|mummy|dead', re.I)
DAEDRA = re.compile(r'scamp|clannfear|daedroth|dremora|atronach|hunger|ogrim|twilight|golden_saint|daedra', re.I)
MACHINE = re.compile(r'centurion|sphere|steam|spider_centurion|dwemer|dwrv', re.I)
BAND_OF = [('smugglers', ('smuggler',)), ('necromancers', ('necromancer',)), ('worshippers', ('worshipper', 'healer', 'witch', 'sorcerer')),
           ('bandits', ('barbarian', 'rogue', 'thief', 'warrior', 'archer', 'scout', 'sharpshooter', 'assassin', 'nightblade', 'agent',
                        'bandit', 'smith', 'mabrigash', 'crusader', 'knight', 'battlemage', 'spellsword', 'monk', 'acrobat', 'pilgrim'))]
SAY = {
    'bandits': ["Bandits have holed up there. Nobody takes that way alone any more.", "There's a band of cutthroats in there now. They've robbed two caravans this month.",
                "Outlaws. They come down to the road at night. Stay clear unless you can handle a blade."],
    'smugglers': ["Smugglers use it, they say. The guards would pay well to see it cleared.", "It's a smugglers' den. Moon sugar, skooma, whatever sells. Best not to ask."],
    'necromancers': ["There are lights there at night, and things walking that shouldn't. A necromancer, I'd wager.",
                     "Someone's been at the dead out there. A necromancer, people say. The Temple won't go near it."],
    'worshippers': ["Daedra worshippers. They keep to themselves, but folk who go looking don't come back.", "A cult, they say. Strange chanting on still nights."],
    'dead': ["It's a place of the dead. Leave it be.", "The dead don't rest there. You'd want silver, or magic, if you go."],
    'daedra': ["Daedra. Real ones. I wouldn't go within a mile of it.", "Something from Oblivion has made it its home. Don't."],
    'machines': ["The old Dwemer machines still walk its halls, they say. Scavengers try their luck now and then.",
                 "Dwemer work. The machines in there still guard whatever's left."],
    'beasts': ["Something lairs in there. The herders have lost animals to it.", "Beasts, mostly. Hunters go in for the hides, when they're brave."],
    'empty': ["Nobody's been in there for years, as far as I know.", "Quiet, these days. Who knows what's left inside."],
}
DEAD = re.compile(r'dead|corpse|_body|skeleton', re.I)
DIRS = ('east', 'north-east', 'north', 'north-west', 'west', 'south-west', 'south', 'south-east')


def _way(ax, ay, bx, by):
    a = math.atan2(by - ay, bx - ax)
    d = DIRS[int(round(a / (math.pi / 4))) % 8]
    r = math.hypot(bx - ax, by - ay)
    far = 'just' if r < 6000 else 'a short walk' if r < 15000 else "half a day's walk" if r < 30000 else 'a long way'
    return '%s %s' % (far, d) if far != 'just' else 'just %s' % d


def _npc(db, rid):
    """(class, level) of a person."""
    from esm import iter_subrecords, zstr
    ri = db.resolve_id(rid)
    if ri is None or db.recs[ri][0] != 'NPC_':
        return '', 0
    r = db.recs[ri]
    cls, lvl = '', 0
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'CNAM':
            cls = zstr(d)
        elif t == 'NPDT' and len(d) >= 2:
            lvl = struct.unpack_from('<h', bytes(d))[0]
    return cls, lvl


def _inside(db, name):
    """The people and creatures in a place's cells (its name and those named "<name>, ...")."""
    low = name.lower()
    keys = [k for (tag, k), lst in db.by_key.items() if tag == 'CELL' and not k.startswith('#') and (k == low or k.startswith(low + ','))
            and any(v not in db.dead for v in lst)]
    people, creatures = [], []
    for k in keys:
        for r in mapdata.cellmap(db, k).get('refs') or []:
            # (no corpses: the dungeon's dressing has the game's dead, TR_M1_dead_Skeemeet was taken for a band's leader)
            if r.get('type') == 'NPC_' and not DEAD.search(r['id']):
                people.append(r['id'])
            elif r.get('type') in ('CREA', 'LEVC'):
                creatures.append(r['id'].lower())
    return people, creatures


def _band(db, people, creatures):
    """What holds the place, and its leader (the highest-level person), or None."""
    seen = []
    for rid in people:
        cls, lvl = _npc(db, rid)
        seen.append((lvl, rid, cls.lower()))
    if seen:
        seen.sort(reverse=True)
        cl = [c for _l, _r, c in seen]
        for band, words in BAND_OF:
            if sum(1 for c in cl if any(w in c for w in words)) >= max(1, len(cl) // 2):
                return band, seen[0][1], seen[0][0]
        return 'bandits', seen[0][1], seen[0][0]
    if not creatures:
        return 'empty', None, 0
    n = len(creatures)
    for band, rx in (('dead', UNDEAD), ('daedra', DAEDRA), ('machines', MACHINE)):
        if sum(1 for c in creatures if rx.search(c)) * 2 >= n:
            return band, None, 0
    return 'beasts', None, 0


def gather(db, cells):
    """The mod's towns and dungeons in the marked cells, from its outside doors: {'towns': {name: {x, y, doors}},
    'dungeons': [{name, x, y}], 'labels': [{name, x, y}]} (labels: the named cells, the land's names)."""
    import landrange
    keys = sorted({landrange._key(k) for k in cells or []})
    towns, dungeons, labels = {}, {}, []
    for gx, gy in keys:
        m = mapdata.cellmap(db, '#%d,%d' % (gx, gy))
        if (m.get('name') or '').strip():
            labels.append({'name': m['name'].strip(), 'x': (gx + 0.5) * 8192.0, 'y': (gy + 0.5) * 8192.0})
        for r in m.get('refs') or []:
            to = r.get('to') or {}
            if r.get('type') != 'DOOR' or not r.get('mine') or not to.get('cell'):
                continue
            dest = to['cell']
            x, y = r['p'][0], r['p'][1]
            if ',' in dest:
                t = dest.split(',')[0].strip()
                T = towns.setdefault(t, {'x': 0.0, 'y': 0.0, 'doors': 0})
                T['x'] += x
                T['y'] += y
                T['doors'] += 1
            else:
                pc = db.project.cells.get(dest.lower()) if getattr(db, 'project', None) else None
                if pc and pc.get('ruin'):
                    dungeons.setdefault(dest, {'name': dest, 'x': x, 'y': y})
    for t, T in towns.items():
        T['x'] /= T['doors']
        T['y'] /= T['doors']
    # (a town is three doors or more: a lone house is not one to talk of the land round it)
    towns = {t: T for t, T in towns.items() if T['doors'] >= 3}
    return {'towns': towns, 'dungeons': list(dungeons.values()), 'labels': labels}


def _giver(db, town):
    """The town's publican, else a guard, else anyone: an NPC record of the mod's in the town's cells."""
    low = town.lower()
    best = None
    for (tag, k), lst in db.by_key.items():
        if tag != 'CELL' or not k.startswith(low + ','):
            continue
        for r in mapdata.cellmap(db, k).get('refs') or []:
            if r.get('type') != 'NPC_' or not r.get('new'):
                continue
            cls, _lvl = _npc(db, r['id'])
            rank = 0 if cls.lower() == 'publican' else 1 if 'guard' in cls.lower() else 2
            if best is None or rank < best[0]:
                best = (rank, r['id'])
    return best[1] if best else None


def plan(db, cells, seed=1):
    """What would be said and asked, changing nothing: {'places': [{name, band, leader, towns: [(town, line)],
    rumour, quest: {giver, town, reward} or None}], 'towns'}."""
    rng = random.Random('%s|rumours' % seed)
    G = gather(db, cells)
    out = []
    per_town = {}
    for D in G['dungeons']:
        near = sorted(((math.hypot(T['x'] - D['x'], T['y'] - D['y']), t) for t, T in G['towns'].items()))
        near = [(d, t) for d, t in near if d < NEAR][:TOWNS_EACH]
        if not near:
            continue
        people, creatures = _inside(db, D['name'])
        band, leader, lvl = _band(db, people, creatures)
        # (a dungeon with a story of its own, dgstory.py: the town says that, not the band's stock lines)
        say = SAY[band]
        try:
            import dgstory
            st = dgstory.of(db, D['name'])
            if st and st.get('say') and people:
                say = list(st['say'])
        except Exception:
            pass
        mark = min(((math.hypot(L['x'] - D['x'], L['y'] - D['y']), L['name']) for L in G['labels'] if L['name'] != D['name']
                    and math.hypot(L['x'] - D['x'], L['y'] - D['y']) < 9000), default=None)
        lines = []
        for _d, t in near:
            T = G['towns'][t]
            where = '%s lies %s of %s%s.' % (D['name'], _way(T['x'], T['y'], D['x'], D['y']), t,
                                              (', under %s' % mark[1]) if mark and re.match(r'(mount|.* peak$)', mark[1], re.I) else
                                              (', by %s' % mark[1]) if mark else '')
            lines.append((t, '%s %s' % (where, rng.choice(say))))
        rumour = 'Have you heard about %s? %s' % (D['name'], rng.choice(say))
        said = {line.split('. ', 1)[-1] for _t, line in lines}
        ask = next((x for x in say if x not in said), say[0])
        quest = None
        if leader:
            t = near[0][1]
            if per_town.get(t, 0) < QUESTS_PER_TOWN:
                g = _giver(db, t)
                if g:
                    per_town[t] = per_town.get(t, 0) + 1
                    quest = {'giver': g, 'town': t, 'reward': REWARD[0] + REWARD[1] * max(1, lvl), 'way': _way(G['towns'][t]['x'], G['towns'][t]['y'], D['x'], D['y'])}
        out.append({'name': D['name'], 'band': band, 'leader': leader, 'towns': lines, 'rumour': rumour, 'quest': quest, 'ask': ask,
                    'near': [t for _d, t in near]})
    return {'places': out, 'towns': sorted(G['towns']), 'dungeons': len(G['dungeons'])}


BAND_WORD = {'bandits': 'the bandits', 'smugglers': 'the smugglers', 'necromancers': 'the necromancer', 'worshippers': 'the cultists'}


def build(db, cells, seed=1):
    """plan() written: the topics, the towns' lines, the rumours and the quests. One Undo. {'topics', 'lines',
    'quests', 'places', 'towns'}."""
    import dialogue
    import editing
    import questmake
    editing._require_project(db)
    P = plan(db, cells, seed)
    n_top = n_lines = n_q = 0
    n0 = len(getattr(db.project, 'undo_stack', []) or [])
    with editing.operation('rumours'):
        for D in P['places']:
            name = D['name'][:31]
            key = name.lower()
            if not dialogue._dial_versions(db, key):
                dialogue.create_topic(db, name, 0)
                n_top += 1
            for town, text in D['towns']:
                dialogue.save_line(db, key, {'cell': town, 'text': text, 'disp': 0, 'rank': -1, 'sex': -1, 'pcrank': -1, 'conds': []},
                                   {'bottom': True})
                n_lines += 1
            for town in D['near'][:1]:
                dialogue.save_line(db, 'latest rumors', {'cell': town, 'text': D['rumour'], 'result': 'AddTopic "%s"' % name,
                                                         'disp': 0, 'rank': -1, 'sex': -1, 'pcrank': -1, 'conds': []}, {'top': True})
                n_lines += 1
            Q = D['quest']
            if Q:
                qid = re.sub(r'[^A-Za-z0-9_]+', '_', 'ws_%s_%s' % (Q['town'][:10], name[:14])).strip('_')[:31]
                k = 1
                while dialogue._dial_versions(db, qid.lower()):
                    k += 1
                    qid = '%s_%d' % (qid[:28], k)
                who = BAND_WORD.get(D['band'], 'them')
                title = 'Trouble at %s' % name
                qk = questmake.new_quest(db, qid, title, '%s in %s asked me to deal with %s at %s, %s of town.'
                                         % (_fname(db, Q['giver']), Q['town'], who, name, Q['way']))['key']
                questmake.add_stage(db, qk, 20, 'I have dealt with %s at %s. I should go back to %s for my reward.'
                                    % (who, name, _fname(db, Q['giver'])))
                questmake.add_stage(db, qk, 100, '%s paid me %d gold for clearing %s.' % (_fname(db, Q['giver']), Q['reward'], name), finished=True)
                questmake.add_move(db, qk, {'verb': 'talk', 'who': Q['giver'], 'topic': name, 'from': 0, 'to': 10,
                                            'say': "%s? %s If you could clear %s out, I'd make it worth your while: %d gold." % (
                                                name, D.get('ask') or SAY[D['band']][0], who, Q['reward'])})
                questmake.add_move(db, qk, {'verb': 'kill', 'who': D['leader'], 'from': 10, 'to': 20})
                questmake.add_move(db, qk, {'verb': 'talk', 'who': Q['giver'], 'topic': name, 'from': 20, 'to': 100,
                                            'say': "You've done it? Then the road is safer for all of us. Here, as I promised.",
                                            'gives': [{'id': 'Gold_001', 'n': Q['reward']}]})
                n_q += 1
    # (every line and quest one Undo step, as Build the places folds its own)
    n1 = len(getattr(db.project, 'undo_stack', []) or [])
    if n1 - n0 > 1:
        editing.fold(db, n1 - n0, 'Rumours and quests: %d place%s talked of, %d quest%s' % (len(P['places']), '' if len(P['places']) == 1 else 's', n_q, '' if n_q == 1 else 's'))
    return {'topics': n_top, 'lines': n_lines, 'quests': n_q, 'places': len(P['places']), 'towns': len(P['towns']), 'dungeons': P['dungeons']}


def _fname(db, rid):
    ri = db.resolve_id(rid)
    return (db.recs[ri][2] if ri is not None else '') or rid
