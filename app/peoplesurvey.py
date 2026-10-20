"""Where the game's people stand: by what furniture, in rooms of each kind and places of each theme
(the trader behind the counter, the publican by the bar, a guard by the door, the owner at the table),
as pairs like the room survey's furniture pairs but for people. For the Populate feature: who to put in
a room like this, and where to stand them.

The raw sightings come from the room survey (roomsurvey.py, 'people'): for every NPC in a surveyed
room, the room's kind and the place's theme, the NPC's class, the nearest piece of furniture (within
300 units) and the NPC's offset and turn in that furniture's own frame, and how far the nearest door
is. This module sorts them by role and furniture."""
import math
from collections import Counter, defaultdict

import furnish
import roomsurvey

# classes by the part they play in a place (words in the class ID or name)
ROLES = {'publican': ('publican',),
         'trader': ('trader', 'merchant', 'pawnbroker', 'bookseller', 'clothier', 'outfitter', 'apothecary', 'alchemist',
                    'smith', 'enchanter', 'armorer', 'shipmaster', 'caravaner', 'gondolier', 'guild guide', 'guildguide'),
         'guard': ('guard', 'ordinator', 'legion', 'warden', 'buoyant'),
         'priest': ('priest', 'monk', 'healer', 'acolyte', 'cleric', 'ashkhan', 'wise woman', 'wisewoman', 'gulakhan'),
         'noble': ('noble', 'retainer', 'king', 'queen', 'duke', 'count'),
         'servant': ('servant', 'slave', 'commoner', 'farmer', 'miner', 'pauper', 'herder', 'hunter', 'fisher', 'laborer', 'labourer'),
         'scholar': ('scholar', 'mage', 'wizard', 'sorcerer', 'apprentice', 'savant', 'battlemage', 'conjurer', 'necromancer', 'witch', 'bard'),
         'fighter': ('warrior', 'knight', 'rogue', 'archer', 'barbarian', 'scout', 'agent', 'thief', 'assassin', 'nightblade',
                     'spellsword', 'drillmaster', 'master-at-arms', 'champion', 'crusader', 'mercenary', 'pilgrim')}
NEAR_DOOR = 200          # standing this close to a door: by the door
_cache = {}


def role_of(cls):
    low = (cls or '').lower()
    for role, words in ROLES.items():
        if any(w in low for w in words):
            return role
    return 'other'


def _front(db, rid):
    f = furnish.front_of(db, rid)
    return f or (0.0, -1.0)


def survey(db):
    """{'people': sightings, 'rooms': {(theme, kind): {'n', 'roles', 'by', 'by_door'}}, 'stands': {(role,
    furniture): {'n', 'dx', 'dy', 'dist', 'turn', 'behind', 'ids'}}, 'roles': {role: {'n', 'themes', 'kinds',
    'by', 'classes'}}}, or None until the room survey has run."""
    s = roomsurvey.ready(db)
    if not s:
        return None
    if 'people' in _cache and _cache['people'][0] is s:
        return _cache['people'][1]
    raw = s.get('people') or []
    rooms = defaultdict(lambda: {'n': 0, 'roles': Counter(), 'by': Counter(), 'door': 0})
    stands = defaultdict(list)
    roles = defaultdict(lambda: {'n': 0, 'themes': Counter(), 'kinds': Counter(), 'by': Counter(), 'classes': Counter()})
    fronts = {}
    for kind, theme, cls, fam, lx, ly, dq, dist, by_id, door_d in raw:
        role = role_of(cls)
        R = rooms[(theme, kind)]
        R['n'] += 1
        R['roles'][role] += 1
        R['by'][fam or 'nothing'] += 1
        if door_d is not None and door_d <= NEAR_DOOR:
            R['door'] += 1
        ro = roles[role]
        ro['n'] += 1
        ro['themes'][theme] += 1
        ro['kinds'][kind] += 1
        ro['by'][fam or 'nothing'] += 1
        ro['classes'][cls] += 1
        if fam:
            key = by_id.lower()
            if key not in fronts:
                fronts[key] = _front(db, by_id)
            fx, fy = fronts[key]
            stands[(role, fam)].append((lx, ly, dq, dist, by_id, lx * fx + ly * fy < 0))
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    out = {'people': len(raw), 'rooms': {}, 'stands': {}, 'roles': {}}
    for k, R in rooms.items():
        n = R['n']
        out['rooms'][k] = {'n': n, 'roles': [[r, round(c / n, 2)] for r, c in R['roles'].most_common()],
                           'by': [[f, round(c / n, 2)] for f, c in R['by'].most_common()], 'by_door': round(R['door'] / n, 2)}
    for k, lst in stands.items():
        if len(lst) < 3:
            continue
        xs = sorted(abs(p[0]) for p in lst)
        ys = sorted(abs(p[1]) for p in lst)
        out['stands'][k] = {'n': len(lst), 'dx': med(xs), 'dy': med(ys), 'dist': med(sorted(p[3] for p in lst)),
                            'turn': Counter(p[2] for p in lst).most_common(1)[0][0],
                            'facing': round(sum(1 for p in lst if p[2] == 2) / len(lst), 2),
                            'behind': round(sum(1 for p in lst if p[5]) / len(lst), 2),
                            'ids': [i for i, _n in Counter(p[4] for p in lst).most_common(4)]}
    for role, ro in roles.items():
        n = ro['n']
        out['roles'][role] = {'n': n, 'themes': ro['themes'].most_common(4), 'kinds': ro['kinds'].most_common(4),
                              'by': [[f, round(c / n, 2)] for f, c in ro['by'].most_common(5)], 'classes': ro['classes'].most_common(6)}
    _cache['people'] = (s, out)
    return out


def who(db, theme, kind):
    """Who stands in a room of this kind in a place of this theme: [(role, share of the people there)], or
    [] when the game shows nobody there (or the survey hasn't run)."""
    s = survey(db)
    if not s:
        return []
    R = s['rooms'].get((theme, kind))
    return [tuple(x) for x in R['roles']] if R else []


def stand(db, role, by):
    """How someone of this role stands by this furniture, in its own frame: {'dx', 'dy', 'dist', 'turn',
    'behind' (share standing behind its front: the trader behind the counter), 'ids'}, or None."""
    s = survey(db)
    return s['stands'].get((role, by)) if s else None


def summary(db):
    """For people (and the Populate feature): the whole thing with string keys."""
    s = survey(db)
    if not s:
        return {'ready': False, 'note': 'The room survey is still running (a few minutes); try again later.'}
    return {'ready': True, 'people': s['people'],
            'rooms': {'|'.join(k): v for k, v in sorted(s['rooms'].items(), key=lambda kv: -kv[1]['n'])},
            'stands': {'|'.join(k): v for k, v in sorted(s['stands'].items(), key=lambda kv: -kv[1]['n'])},
            'roles': s['roles']}


def report(db):
    """A few lines for the log: who stands where."""
    s = survey(db)
    if not s:
        return ['people survey: not ready']
    out = ['people: %d sightings' % s['people']]
    for k, v in sorted(s['rooms'].items(), key=lambda kv: -kv[1]['n'])[:14]:
        out.append('  %s/%s: %d, roles %s, by %s, by a door %.0f%%' % (k[0], k[1], v['n'], v['roles'][:4], v['by'][:4], v['by_door'] * 100))
    for k, v in sorted(s['stands'].items(), key=lambda kv: -kv[1]['n'])[:16]:
        out.append('  %s by %s: n %d, dx %s dy %s dist %s, turn %s, facing %.0f%%, behind %.0f%%' % (
            k[0], k[1], v['n'], v['dx'], v['dy'], v['dist'], v['turn'], v['facing'] * 100, v['behind'] * 100))
    return out
