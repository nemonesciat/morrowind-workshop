"""The game's scenes that are things-with-their-kit: the painter's corner (an easel with its canvas, a small
table of paint pots, brushes and a palette, a stool), the alchemist's bench (mortar, alembic, retort,
calcinator, ingredients and a book on a table), the smith's corner (an anvil, bellows, tongs and hammer,
logs and coals, a bucket), the scribe's desk (inkwell, quill, paper, a ledger, a candle). For each: the
base it stands on (a table, a counter, a shelf, or the floor), the pieces with their offsets, and the kinds
of room the game puts it in, at what rate. Auto-furnish lays a scene only whole and only in a room kind
the game puts it in (furnish.py); "Add one thing" and "Dress this" on a table or a desk can draw a whole
scene. The SCENE_ONLY list (shelfsurvey.py) still keeps the single pieces off everyday tables.

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import math
import os
import re
from collections import Counter, defaultdict

import furnish
import kits
import mapdata
import roomsurvey
import arrangesurvey
import fixit

V = 'v2'                # (v2: a smith's mark is the anvil or the bellows, not the book "Port of Anvil")
EXAMPLES = 40
REACH = 160
KINDS = ('painter', 'alchemist', 'smith', 'scribe')
MARKS = {
    'painter': re.compile(r'easel'),
    'alchemist': re.compile(r'alembic|retort|calcinator|mortar'),
    'smith': re.compile(r'furn_anvil|anvil0|_anvil_|bellows'),      # (not the book "Port of Anvil")
    'scribe': re.compile(r'inkwell|ink_well|inkpot|quill'),
}
# what a whole scene has (an example is kept only when it holds these)
NEEDS = {
    'painter': (re.compile(r'easel'), re.compile(r'paint|palette|brush|canvas')),
    'alchemist': (re.compile(r'apparatus|alembic|retort|calcinator|mortar'),),
    'smith': (re.compile(r'anvil'), re.compile(r'bellows|tongs|prongs|hammer|coals|log')),
    'scribe': (re.compile(r'inkwell|ink_well|inkpot'), re.compile(r'quill'), re.compile(r'paper|scroll|ledger|book|log|manifest|record')),
}
BASE_KINDS = ('table', 'counter', 'shelf', 'bookshelf', 'cupboard', 'chest', 'crate', 'bench', 'forge', 'barrel')
NOT_MEMBER = re.compile(r'tapestr|banner|rug|carpet|marker|_nf$|collision|invisible|rope|hook')
PURPOSE_KINDS = {'hall': ('empty', 'living'), 'entry': ('empty', 'living'), 'living': ('living',), 'study': ('study',), 'shop': ('shop',),
                 'kitchen': ('kitchen',), 'tavern': ('tavern',), 'bedroom': ('bedroom',), 'storage': ('storage',), 'shrine': ('shrine',)}
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('scenesurvey_%s_%s' % (taste.sig(db), V))


def ready(db):
    import taste
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('the game\'s scenes with their kit', lambda: survey(db), task=('scenesurvey', 'survey', []))
    return taste.stale(_cache, key, db.recs, _disk(db))


def survey(db):
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def mark_kind(r):
    low = r['id'].lower()
    if 'marker' in low:
        return None
    for sk, rx in MARKS.items():
        if rx.search(low):
            if sk == 'scribe' and r['type'] not in ('MISC', 'STAT'):
                return None
            if sk == 'alchemist' and r['type'] != 'APPA':
                return None
            if sk == 'smith' and r['type'] not in ('STAT', 'ACTI', 'MISC'):
                return None
            return sk
    return None


def _mark_cells(db):
    """Every game-made interior that holds one of the scenes' marks, by the records' use lists."""
    keys = set()
    for r in db.recs:
        if r[0] not in ('STAT', 'ACTI', 'MISC', 'APPA') or not mark_kind({'id': r[1], 'type': r[0]}):
            continue
        for ci in db.used_in.get(r[1].lower(), ()):
            if db.recs[ci][0] == 'CELL':
                keys.add(db.recs[ci][7])
    out = []
    for k in keys:
        if not k or k.startswith('#') or not kits.game_made(db, k):
            continue
        ci = mapdata.cell_info(db, k)
        if ci and ci.get('interior'):
            out.append(k)
    return sorted(out)


def _survey(db):
    import taste
    cells = taste.order(_mark_cells(db))
    agg = {sk: {'cells': 0, 'scenes': 0, 'bases': Counter(), 'kinds': Counter(), 'themes': Counter(), 'n': [], 'base_ids': Counter(), 'members': Counter(), 'examples': []} for sk in KINDS}
    rooms_by_kind = Counter()
    tables_by_kind = Counter()
    seen = 0
    for ck in cells:
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        refs = [r for r in m['refs'] if r.get('b') and not r.get('arch') and r['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
        marks = [(mark_kind(r), r) for r in refs]
        marks = [(sk, r) for sk, r in marks if sk]
        if not marks:
            continue
        seen += 1
        for r in refs:
            r['_box'] = fixit._world_box(r)
            r['_fam'] = arrangesurvey.family(db, r['id'], r['type'])
        try:
            info = furnish.rooms(db, ck, trace=False)
        except Exception:
            info = None
        theme = roomsurvey.theme_of(ck)
        room_kind = {}
        if info and info['rooms']:
            for rm in info['rooms']:
                inside = [r for r in refs if rm['x_min'] - 20 <= r['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= r['p'][1] <= rm['y_max'] + 20 and rm['floor'] - 40 <= r['p'][2] <= rm['floor'] + 300]
                kd = roomsurvey.room_kind(Counter(r['_fam'] for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS))
                room_kind[rm['id']] = kd
                rooms_by_kind[kd] += 1
                tables_by_kind[kd] += sum(1 for r in inside if r['_fam'] == 'table')
        done = set()
        kinds_here = set()
        for sk, mk in marks:
            if id(mk) in done or not mk['_box']:
                continue
            grp = [mk]
            done.add(id(mk))
            i = 0
            while i < len(grp):
                a = grp[i]
                for sk2, o in marks:
                    if sk2 == sk and id(o) not in done and o['_box'] and math.hypot(a['p'][0] - o['p'][0], a['p'][1] - o['p'][1]) < 150:
                        grp.append(o)
                        done.add(id(o))
                i += 1
            cx = sum(o['p'][0] for o in grp) / len(grp)
            cy = sum(o['p'][1] for o in grp) / len(grp)
            cz = min(o['_box'][2] for o in grp)
            # the base: furniture whose box holds the first mark's foot, its top near the mark's bottom
            base = None
            for o in refs:
                b = o['_box']
                if not b or o is mk or o['_fam'] not in BASE_KINDS:
                    continue
                if b[0] - 8 <= mk['p'][0] <= b[3] + 8 and b[1] - 8 <= mk['p'][1] <= b[4] + 8 and -40 <= mk['_box'][2] - b[5] <= 40:
                    base = o
                    break
            ref = base or mk
            top = ref['_box'][5] if base else mk['_box'][2]
            members = []
            for o in refs:
                if not o['_box'] or o is base or NOT_MEMBER.search(o['id'].lower()) or math.hypot(o['p'][0] - cx, o['p'][1] - cy) >= REACH:
                    continue
                if o['type'] == 'LIGH':
                    if -20 <= o['_box'][2] - top <= 60:
                        members.append(o)          # (a candle on the desk; not the room's lantern)
                elif abs(o['_box'][2] - cz) < 160:
                    members.append(o)
            kd = '?'
            if info and info['rooms']:
                rm = next((r for r in info['rooms'] if r['x_min'] - 20 <= cx <= r['x_max'] + 20 and r['y_min'] - 20 <= cy <= r['y_max'] + 20 and abs(cz - r['floor']) < 200), None)
                if rm:
                    kd = room_kind.get(rm['id'], '?')
            A = agg[sk]
            A['scenes'] += 1
            A['bases'][base['_fam'] if base else 'floor'] += 1
            if base:
                A['base_ids'][base['id'].lower()] += 1
            A['kinds'][kd] += 1
            A['themes'][theme] += 1
            A['n'].append(len(members))
            A['members'].update(re.sub(r'_\d+[a-z]?$', '', o['id'].lower()) for o in members)
            kinds_here.add(sk)
            # the example: every member's offset in the base's frame (the mark's when it stands on the floor),
            # z from the base's top (the mark's bottom), and whether it rides on the base
            if all(any(rx.search(o['id'].lower()) for o in members + ([base] if base else [])) for rx in NEEDS[sk]) and len(members) >= 3:
                c_, s_ = math.cos(ref['p'][5]), math.sin(ref['p'][5])
                mem = []
                for o in members:
                    dx, dy = o['p'][0] - ref['p'][0], o['p'][1] - ref['p'][1]
                    on = bool(base) and base['_box'][0] - 8 <= o['p'][0] <= base['_box'][3] + 8 and base['_box'][1] - 8 <= o['p'][1] <= base['_box'][4] + 8 and -12 <= o['_box'][2] - top <= 60
                    mem.append({'id': o['id'], 'type': o['type'], 'fam': o['_fam'], 'x': round(dx * c_ - dy * s_, 1), 'y': round(dx * s_ + dy * c_, 1),
                                'z': round(o['_box'][2] - top, 1), 'zo': round(o['p'][2] - ref['p'][2], 1), 'rz': round((o['p'][5] - ref['p'][5]) % (2 * math.pi), 3),
                                'rx': round(o['p'][3], 3), 'ry': round(o['p'][4], 3), 's': round(o.get('s') or 1.0, 3), 'on': on,
                                'floor': (not on) and o['_box'][2] - cz < 30 and o['type'] in ('STAT', 'ACTI', 'CONT')})
                ex = {'cell': ck, 'kind': kd, 'theme': theme, 'base': {'id': base['id'], 'fam': base['_fam']} if base else None,
                      'anchor': {'id': mk['id'], 'type': mk['type']}, 'n': len(members), 'members': mem}
                A['examples'].append(ex)
                if len(A['examples']) > EXAMPLES * 3:
                    A['examples'].sort(key=lambda e: -e['n'])
                    A['examples'] = A['examples'][:EXAMPLES]
        for sk in kinds_here:
            agg[sk]['cells'] += 1
    out = {'cells': seen, 'rooms': dict(rooms_by_kind), 'tables': dict(tables_by_kind), 'scenes': {}}
    for sk, A in agg.items():
        A['examples'].sort(key=lambda e: -e['n'])
        # (a spread of the fullest: not only the one biggest manor's)
        exs = A['examples'][:EXAMPLES]
        n = sorted(A['n'])
        out['scenes'][sk] = {'cells': A['cells'], 'scenes': A['scenes'], 'members': n[len(n) // 2] if n else 0,
                             'bases': dict(A['bases'].most_common()), 'base_ids': dict(A['base_ids'].most_common(10)),
                             'kinds': dict(A['kinds'].most_common()), 'themes': dict(A['themes'].most_common()),
                             'pieces': dict(A['members'].most_common(30)), 'examples': exs}
    return out


def rate(db, scene, purpose):
    """How often the game lays this scene in a room of this kind: scenes per room of the kind (the survey's
    rooms of the kinds standing for the purpose); 0 until surveyed or where the game never does."""
    s = ready(db)
    if not s or scene not in s['scenes']:
        return 0.0
    kinds = PURPOSE_KINDS.get(purpose, (purpose,))
    sc = sum(s['scenes'][scene]['kinds'].get(k, 0) for k in kinds)
    rooms = sum(s['rooms'].get(k, 0) for k in kinds)
    return sc / float(rooms) if rooms else 0.0


def table_rate(db, scene, purpose):
    """How often a table in a room of this kind carries this scene (scenes on a table or counter per table
    of the kind); 0 until surveyed."""
    s = ready(db)
    if not s or scene not in s['scenes']:
        return 0.0
    kinds = PURPOSE_KINDS.get(purpose, (purpose,))
    S = s['scenes'][scene]
    on_table = (S['bases'].get('table', 0) + S['bases'].get('counter', 0)) / float(S['scenes'] or 1)
    sc = sum(S['kinds'].get(k, 0) for k in kinds) * on_table
    tables = sum(s['tables'].get(k, 0) for k in kinds)
    return sc / float(tables) if tables else 0.0


def scenes_for(db, purpose):
    """[(scene, rate)] for a room of this kind, the scenes the game lays there, commonest first."""
    out = [(sk, rate(db, sk, purpose)) for sk in KINDS]
    return sorted([t for t in out if t[1] > 0], key=lambda t: -t[1])


def pick(db, scene, rng, on_table=None, purpose=None):
    """One of the game's examples of the scene, whole: {'base': {'id','fam'} or None, 'anchor', 'members': [...]}.
    on_table True: only examples whose base is a table or a counter (to lay on a table standing here); False:
    only floor scenes (an easel, an anvil); None: any. A room kind's own examples come first. None when there
    is none."""
    s = ready(db)
    if not s or scene not in s['scenes']:
        return None
    exs = [e for e in s['scenes'][scene]['examples'] if all(db.resolve_id(m['id']) is not None for m in e['members'])
           and (e['base'] is None or db.resolve_id(e['base']['id']) is not None)]
    if on_table is True:
        exs = [e for e in exs if e['base'] and e['base']['fam'] in ('table', 'counter')]
    elif on_table is False:
        exs = [e for e in exs if not e['base']]
    if not exs:
        return None
    if purpose:
        kinds = PURPOSE_KINDS.get(purpose, (purpose,))
        own = [e for e in exs if e['kind'] in kinds]
        if own and rng.random() < 0.7:
            exs = own
    return rng.choice(exs)


def report(db):
    s = survey(db)
    out = ['%d places with scenes; rooms read by kind %s; tables %s' % (s['cells'], s['rooms'], s['tables'])]
    for sk, S in s['scenes'].items():
        out.append('%s: %d places, %d scenes, %d pieces each (median); on %s; in %s; themes %s; examples kept %d'
                   % (sk, S['cells'], S['scenes'], S['members'], S['bases'], S['kinds'], S['themes'], len(S['examples'])))
        out.append('   base models %s' % S['base_ids'])
        out.append('   pieces %s' % list(S['pieces'].items())[:24])
        for e in S['examples'][:4]:
            out.append('   ex %s (%s) base %s: %s' % (e['cell'], e['kind'], e['base'], [(m['id'], m['x'], m['y'], m['z'], 'on' if m['on'] else 'floor' if m['floor'] else '-') for m in e['members']][:12]))
        for kd in ('study', 'shop', 'living', 'bedroom', 'kitchen', 'tavern'):
            out.append('   rate in a %s: %.3f per room, %.3f per table' % (kd, rate(db, sk, kd), table_rate(db, sk, kd)))
    return out
