"""Conversations: everything a character can say, how their lines lead to one another (the
conversation map), and which line they would say for a given state of the game (the tester).

The game picks a line the same way for every topic: it goes down the topic's lines from the top
and says the first one whose conditions all fit. Some conditions are about the speaker (who they
are, their race, class, faction, where they stand, their script's variables) and never change for
one character; the rest are about the state of the game (quest stages, the player, items, globals).
So for one character the first kind decides which lines are theirs at all, and the second kind
decides which of those they say right now.

A line can never be said by a character when a line above it, also theirs, asks for a subset of
its conditions about the game: whenever the lower line fits, the upper one fits too and wins."""
import re

import dialogue
import mwscript
import npc
from editing import EditError

GREETINGS = ['greeting %d' % n for n in range(10)]
SAID_TYPES = (0, 2, 3)                      # topics, greetings, persuasion (voice lines and journals aren't said)
F = dialogue.FUNCTIONS
SPEAKER_KINDS = ('not_id', 'not_faction', 'not_class', 'not_race', 'not_cell')

# what a player state starts with, for the tests the tester doesn't take from the speaker
DEFAULTS = {'Player level': 1, 'Player reputation': 0, 'Player health %': 100, 'Player magicka': 100,
            'Player fatigue': 100, 'Player health': 100, 'Health %': 100, 'Player expelled': 0,
            'Player has common disease': 0, 'Player has blight disease': 0, 'Player has corprus': 0,
            'Player is a vampire': 0, 'Player clothing value': 10, 'Player crime level': 0, 'Detected': 0,
            'Alarmed': 0, 'Attacked': 0, 'Should attack': 0, 'Werewolf': 0, 'Player werewolf kills': 0,
            'Weather': 0, 'Friend hit': 0, 'Creature target': 0}
for _a in ('strength', 'intelligence', 'willpower', 'agility', 'speed', 'endurance', 'personality', 'luck'):
    DEFAULTS['Player ' + _a] = 40
for _f in F:
    if _f.startswith('Player ') and _f not in DEFAULTS and _f[7:8].isupper():
        DEFAULTS[_f] = 30                    # skills
# tests the tester works out from the speaker and the player, not a field of their own
DERIVED = ('Same sex as player', 'Same race as player', 'Same faction as player', 'Faction rank difference',
           'Reputation', 'Level', 'Hello', 'Fight', 'Flee', 'Alarm', 'Talked to player before', 'Choice',
           'Player sex (0 male, 1 female)')

# globals the game's scripts roll afresh all the time: a line that needs one is said only sometimes
RANDOM = {'random100'}

_IDX = {'key': None, 'slim': {}, 'touched': set(), 'names': None, 'namekey': None}


# ---------------------------------------------------------------- reading the game's lines
def _q(m, a=1, b=2):
    return (m.group(a) or m.group(b) or '').strip()


_RX_JOURNAL = re.compile(r'\b(?:Journal|SetJournalIndex)\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*,?\s*(-?\d+)', re.I)
_RX_TOPIC = re.compile(r'\bAddTopic\s*,?\s*(?:"([^"]+)"|([\w\'-]+))', re.I)
_RX_CHOICE = re.compile(r'\bChoice\b(.*)', re.I)
_RX_ANSWER = re.compile(r'"([^"]*)"\s*,?\s*(\d+)')
_RX_ITEM = re.compile(r'(?:(\w+)\s*->\s*)?(AddItem|RemoveItem)\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*,?\s*(-?\d+)', re.I)
_RX_DISP = re.compile(r'\b(ModDisposition|SetDisposition)\s*,?\s*(-?\d+)', re.I)
_RX_GOODBYE = re.compile(r'^\s*Goodbye\b', re.I | re.M)
_RX_FACTION = re.compile(r'\b(PCJoinFaction|PCRaiseRank|PCLowerRank|PCExpell|ModPCFacRep)\b', re.I)


def effects(result):
    """What a line's result script does, in parts the map and the tester understand."""
    res = re.sub(r';[^\n]*', '', result or '')
    out = {'sets': [], 'learns': [], 'choices': [], 'gives': [], 'takes': [], 'disp': None, 'bye': False, 'faction': []}
    for m in _RX_JOURNAL.finditer(res):
        out['sets'].append({'quest': _q(m).lower(), 'stage': int(m.group(3))})
    for m in _RX_TOPIC.finditer(res):
        out['learns'].append(_q(m).lower())
    for m in _RX_CHOICE.finditer(res):
        out['choices'] += [{'label': a, 'n': int(n)} for a, n in _RX_ANSWER.findall(m.group(1))]
    for m in _RX_ITEM.finditer(res):
        who = (m.group(1) or '').lower()
        if who != 'player':
            continue
        it = {'id': _q(m, 3, 4), 'n': abs(int(m.group(5)))}
        out['gives' if m.group(2).lower() == 'additem' else 'takes'].append(it)
    for m in _RX_DISP.finditer(res):
        out['disp'] = {'set': m.group(1).lower() == 'setdisposition', 'n': int(m.group(2))}
    out['bye'] = bool(_RX_GOODBYE.search(res))
    out['faction'] = sorted({m.group(1) for m in _RX_FACTION.finditer(res)})
    return out


def _slim(d):
    """The parts of a line that decide whose line it is, and the quests it touches."""
    nots = tuple((c['kind'], c['name'].lower()) for c in d['conds'] if c['kind'] in SPEAKER_KINDS)
    locs = tuple(c['name'].lower() for c in d['conds'] if c['kind'] == 'local')
    quests = {c['name'].lower() for c in d['conds'] if c['kind'] == 'journal'}
    if d['result']:
        quests |= {_q(m).lower() for m in _RX_JOURNAL.finditer(d['result'])}
    return (d['actor'].lower(), d['race'].lower(), d['cls'].lower(), d['faction'].lower(), d['rank'],
            d['cell'].lower(), d['sex'], nots, locs, frozenset(quests))


def _index(db):
    """topic key -> [slim line] for every said topic, kept until the game data is read again.
    Topics your mod touches are read afresh each time."""
    key = (id(db.files), len(db.plugins))
    if _IDX['key'] != key:
        _IDX.update(key=key, slim={}, touched=set(), names=None, namekey=None)
        for (tag, k), lst in list(db.by_key.items()):
            if tag != 'DIAL':
                continue
            vs = [v for v in lst if v not in db.dead]
            if not vs or dialogue._dial_type(db, vs[-1]) not in SAID_TYPES:
                continue
            _IDX['slim'][k] = (dialogue._dial_type(db, vs[-1]), db.recs[vs[-1]][1],
                               [_slim(d) for _ii, d in dialogue.ordered_lines(db, k)])
    if db.project is not None:
        for k in list(db.project.records):
            if k.startswith('INFO|') or k.startswith('DIAL|'):
                _IDX['touched'].add(k.split('|')[1])
    for k in _IDX['touched']:
        vs = dialogue._dial_versions(db, k)
        t = dialogue._dial_type(db, vs[-1]) if vs else None
        if t in SAID_TYPES:
            _IDX['slim'][k] = (t, db.recs[vs[-1]][1], [_slim(d) for _ii, d in dialogue.ordered_lines(db, k)])
        else:
            _IDX['slim'].pop(k, None)
    return _IDX['slim']


def _topic_names(db):
    """Topic names the player can click, by their first word, longest first (for the links in a line)."""
    idx = _index(db)
    nk = len(idx)
    if _IDX['names'] is None or _IDX['namekey'] != nk:
        by = {}
        for k, (t, name, _l) in idx.items():
            if t == 0 and k:
                by.setdefault(k.split()[0] if k.split() else k, []).append(k)
        for v in by.values():
            v.sort(key=len, reverse=True)
        _IDX['names'], _IDX['namekey'] = by, nk
    return _IDX['names']


def links(db, text):
    """Topics a line mentions: the words the game turns into links when it is said."""
    by, low, out, i = _topic_names(db), (text or '').lower(), [], 0
    n = len(low)
    while i < n:
        if (low[i].isalnum() or low[i] == "'") and (i == 0 or not (low[i - 1].isalnum() or low[i - 1] == "'")):
            j = i
            while j < n and (low[j].isalnum() or low[j] in "'-"):
                j += 1
            hit = None
            for name in by.get(low[i:j], ()):
                e = i + len(name)
                if low.startswith(name, i) and (e >= n or not low[e].isalnum()):
                    hit = name
                    break
            if hit:
                if hit not in out:
                    out.append(hit)
                i += len(hit)
                continue
            i = j
        else:
            i += 1
    return out


# ---------------------------------------------------------------- the speaker
def speaker(db, npc_id, cell=None):
    """What the game knows about a character when it picks their lines."""
    o = npc.read(db, npc_id)
    cells = []
    for pl in o['placed']:
        nm = pl['name']
        if pl['key'].startswith('#'):
            nm = re.sub(r'\s*\(-?\d+,\s*-?\d+\)$', '', nm)
        if nm and nm not in cells:
            cells.append(nm)
    locs = set()
    if o.get('script'):
        try:
            txt = mwscript.read(db, o['script'])['text']
            locs = {m.group(2).lower() for m in re.finditer(r'^\s*(short|long|float)\s+(\w+)', txt, re.I | re.M)}
        except EditError:
            pass
    return {'id': o['id'], 'low': o['id'].lower(), 'name': o['name'], 'creature': o['kind'] == 'creature',
            'race': o['race'], 'cls': o['cls'], 'faction': o['faction'], 'rank': o['rank'], 'female': o['female'],
            'level': o['level'], 'disposition': o['disposition'], 'reputation': o['reputation'],
            'hello': o['hello'], 'fight': o['fight'], 'flee': o['flee'], 'alarm': o['alarm'],
            'script': o.get('script') or '', 'locals': sorted(locs), 'cells': cells,
            'cell': cell if cell is not None else (cells[0] if cells else '')}


def _who_ok(sl, s):
    """Whether a line (slim) can be this speaker's at all: the speaker tests only."""
    actor, race, cls, fac, rank, cell, sex, nots, locs, _q2 = sl
    if actor and actor != s['low']:
        return False
    if s['creature'] and (race or cls or fac or sex >= 0):
        return False
    if race and race != s['race'].lower():
        return False
    if cls and cls != s['cls'].lower():
        return False
    if fac:
        if fac == 'ffff':
            if s['faction']:
                return False
        elif fac != s['faction'].lower() or (rank >= 0 and s['rank'] < rank):
            return False
    if cell and not s['cell'].lower().startswith(cell):
        return False
    if sex >= 0 and sex != (1 if s['female'] else 0):
        return False
    for kind, name in nots:
        if kind == 'not_id' and name == s['low']:
            return False
        if kind == 'not_faction' and name == s['faction'].lower():
            return False
        if kind == 'not_class' and name == s['cls'].lower():
            return False
        if kind == 'not_race' and name == s['race'].lower():
            return False
        if kind == 'not_cell' and s['cell'].lower().startswith(name):
            return False
    for name in locs:
        if name not in s['locals']:
            return False
    return True


def _tier(d):
    """How particular a line is about its speaker: their own, a group's (race, class, faction,
    place, script) or anyone's."""
    if d['actor']:
        return 'own'
    if d['race'] or d['cls'] or (d['faction'] and d['faction'].lower() != 'ffff') or d['cell'] or \
            any(c['kind'] in SPEAKER_KINDS + ('local', 'not_local') for c in d['conds']):
        return 'group'
    return 'all'


def lines_of(db, s):
    """Every topic this speaker has lines in: {key: {'id', 'type', 'lines': [line]}}, lines in the
    game's order. Greetings are one topic, 'greeting', checked Greeting 0 to 9 in turn."""
    idx = _index(db)
    out = {}
    for k, (t, name, slims) in idx.items():
        if not any(_who_ok(sl, s) for sl in slims):
            continue
        full = dialogue.ordered_lines(db, k)
        keep = []
        for (ii, d), sl in zip(full, slims):
            if _who_ok(sl, s) and not d['deleted']:
                ln = dialogue._line_out(db, ii, d)
                ln['topic'] = k
                keep.append(ln)
        if not keep:
            continue
        if k in GREETINGS:
            g = out.setdefault('greeting', {'id': 'Greeting', 'type': 2, 'lines': [], 'parts': {}})
            g['parts'][k] = keep
        else:
            out[k] = {'id': name, 'type': t, 'lines': keep}
    if 'greeting' in out:
        g = out['greeting']
        g['lines'] = [ln for k in GREETINGS for ln in g['parts'].get(k, [])]
        del g['parts']
    return out


# ---------------------------------------------------------------- one state of the game
def _cmp(a, op, b):
    return {'=': a == b, '!=': a != b, '>': a > b, '>=': a >= b, '<': a < b, '<=': a <= b}.get(op, False)


def _func_value(name, s, p):
    """A test's value in this state, or None when the tester can't tell."""
    vals = p.get('values') or {}
    if name in vals and vals[name] not in (None, ''):
        return float(vals[name])
    pfac = (p.get('faction') or '').lower()
    if name == 'Choice':
        return float(p['choice']) if p.get('choice') is not None else -1.0
    if name == 'Talked to player before':
        return 1.0 if p.get('talked') else 0.0
    if name == 'Player sex (0 male, 1 female)':
        return float(p.get('sex') or 0)
    if name == 'Same sex as player':
        return 1.0 if (1 if s['female'] else 0) == int(p.get('sex') or 0) else 0.0
    if name == 'Same race as player':
        return 1.0 if s['race'].lower() == (p.get('race') or '').lower() else 0.0
    if name == 'Same faction as player':
        return 1.0 if s['faction'] and s['faction'].lower() == pfac else 0.0
    if name == 'Faction rank difference':
        return float(int(p.get('rank') or 0) - s['rank']) if s['faction'] and s['faction'].lower() == pfac else None
    if name in ('Reputation', 'Level', 'Hello', 'Fight', 'Flee', 'Alarm'):
        return float(s[name.lower()])
    if name == 'Player level' and p.get('level') is not None:
        return float(p['level'])
    if name in DEFAULTS:
        return float(DEFAULTS[name])
    return None


def check_line(d, s, p, known=None):
    """('yes' | 'no' | 'maybe', [verdict per condition]) for a line of this speaker in state p.
    The speaker tests have passed already; 'maybe' means a test the tester can't tell."""
    verdicts, worst = [], 'yes'

    def put(v):
        nonlocal worst
        verdicts.append(v)
        if v == 'no':
            worst = 'no'
        elif v == 'maybe' and worst == 'yes':
            worst = 'maybe'
    disp = p.get('disposition')
    disp_v = 'yes' if not d['disp'] or disp is None or disp >= d['disp'] else 'no'
    pc_v = 'yes'
    if d['pcfaction']:
        pf = (p.get('faction') or '').lower()
        if d['pcfaction'].lower() == 'ffff':
            pc_v = 'no' if pf else 'yes'
        elif pf != d['pcfaction'].lower() or (d['pcrank'] >= 0 and int(p.get('rank') or 0) < d['pcrank']):
            pc_v = 'no'
    for c in d['conds']:
        k, name = c['kind'], c['name'].lower()
        if k in SPEAKER_KINDS or (k == 'not_local' and name not in s['locals']):
            put('yes')
            continue
        if k == 'journal':
            v = (p.get('quests') or {}).get(name, 0)
        elif k == 'item':
            v = (p.get('items') or {}).get(name, 0)
        elif k == 'dead':
            v = (p.get('dead') or {}).get(name, 0)
        elif k == 'global':
            v = (p.get('globals') or {}).get(name)
            if v is None and name not in RANDOM:
                v = (known or {}).get(name, 0)
        elif k in ('local', 'not_local'):
            v = (p.get('locals') or {}).get(name, 0)
        elif k == 'function':
            v = _func_value(F[c['func']] if 0 <= c['func'] < len(F) else '', s, p)
        else:
            v = None
        if v is None:
            put('maybe')
            continue
        ok = _cmp(float(v), c['op'], float(c['value']))
        put('yes' if ok != (k == 'not_local') else 'no')
    if disp_v == 'no' or pc_v == 'no':
        worst = 'no'
    return worst, verdicts, disp_v, pc_v


def _state_key(c):
    return (c['kind'], c['name'].lower(), c.get('func'), c['op'], float(c['value']))


def shadowed(lines):
    """For one speaker's lines of a topic (in order): line index -> index of the line above that
    always wins over it. The speaker tests are the same for both, so only the rest count."""
    out = {}
    keys = []
    for ln in lines:
        keys.append({_state_key(c) for c in ln['conds'] if c['kind'] not in SPEAKER_KINDS})
    for j, lj in enumerate(lines):
        for i in range(j):
            li = lines[i]
            if keys[i] <= keys[j] and (li['disp'] or 0) <= (lj['disp'] or 0) and \
                    (not li['pcfaction'] or (li['pcfaction'].lower() == lj['pcfaction'].lower() and li['pcrank'] <= lj['pcrank'])):
                out[j] = i
                break
    return out


# ---------------------------------------------------------------- what the page asks for
def _known_globals(db, names):
    import questtest
    info = questtest.globals_info(db, names)
    return {k.lower(): v['start'] for k, v in info.items()}


def inputs(db, s, topics):
    """The things this character's lines depend on, for the tester's state panel."""
    quests, globs, items, dead, locs, funcs = {}, set(), set(), set(), set(), set()
    for t in topics.values():
        for ln in t['lines']:
            for c in ln['conds']:
                k, name = c['kind'], c['name']
                if k == 'journal':
                    quests[name.lower()] = name
                elif k == 'global':
                    globs.add(name)
                elif k == 'item':
                    items.add(name)
                elif k == 'dead':
                    dead.add(name)
                elif k in ('local', 'not_local') and name.lower() in s['locals']:
                    locs.add(name.lower())
                elif k == 'function' and 0 <= c['func'] < len(F) and F[c['func']] not in ('Choice',):
                    funcs.add(F[c['func']])
            for st in effects(ln['result'])['sets']:
                quests.setdefault(st['quest'], st['quest'])
    qs = []
    for k, name in sorted(quests.items()):
        try:
            q = dialogue.quest(db, k)
            qs.append({'key': k, 'id': q['id'], 'title': q['title'],
                       'stages': [{'index': x['index'], 'text': x['text'][:140], 'finished': x['finished']} for x in q['stages']]})
        except EditError:
            qs.append({'key': k, 'id': name, 'title': '', 'stages': []})
    gl = _known_globals(db, globs)
    fvals = []
    for f in sorted(funcs):
        v = _func_value(f, s, {'values': {}, 'level': 1})
        fvals.append({'name': f, 'default': v, 'derived': f in DERIVED})
    return {'quests': qs, 'globals': [{'name': g, 'start': gl.get(g.lower(), 0), 'random': g.lower() in RANDOM}
                                      for g in sorted(globs, key=str.lower)],
            'items': sorted(items, key=str.lower), 'dead': sorted(dead, key=str.lower), 'locals': sorted(locs),
            'functions': fvals}


def _brief(ln, s, p, known, fx=None):
    st, verdicts, dv, pv = check_line(ln, s, p, known)
    return {'inam': ln['inam'], 'topic': ln['topic'], 'text': ln['text'], 'result': ln['result'], 'mine': ln['mine'],
            'src': ln['src'], 'conds': ln['conds'], 'verdicts': verdicts, 'disp': ln['disp'], 'disp_ok': dv,
            'pcfaction': ln['pcfaction'], 'pc_ok': pv, 'actor': ln['actor'], 'race': ln['race'], 'cls': ln['cls'],
            'faction': ln['faction'], 'cell': ln['cell'], 'sex': ln['sex'], 'tier': _tier(ln), 'state': st,
            'fx': fx if fx is not None else effects(ln['result'])}


def _pick(lines, s, p, known):
    """The line said for a topic: (index said or None, [indices that might be said before it])."""
    maybe = []
    for n, ln in enumerate(lines):
        st = check_line(ln, s, p, known)[0]
        if st == 'yes':
            return n, maybe
        if st == 'maybe':
            maybe.append(n)
    return None, maybe


_LAST = {'key': None, 'val': None}


def _speaker_lines(db, npc_id, cell=None):
    """(speaker, topics), kept for the last character asked about while nothing changes."""
    s = speaker(db, npc_id, cell)
    mine = hash(tuple((k, v['data']) for k, v in db.project.records.items() if k.startswith(('INFO|', 'DIAL|', 'NPC_|', 'SCPT|')))) \
        if db.project else None
    key = (s['low'], s['cell'], id(db.files), len(db.plugins), mine)
    if _LAST['key'] != key:
        _LAST['key'], _LAST['val'] = key, lines_of(db, s)
    return s, _LAST['val']


def say(db, npc_id, state=None, open_topic=None, cell=None):
    """The tester: in this state of the game, what the character greets you with, which topics
    they have something to say about, and (for the topic you open) every line and why it is or
    isn't the one said."""
    s, topics = _speaker_lines(db, npc_id, cell)
    p = dict(state or {})
    if p.get('disposition') is None:
        p['disposition'] = s['disposition']
    gnames = set()
    for t in topics.values():
        for ln in t['lines']:
            gnames |= {c['name'] for c in ln['conds'] if c['kind'] == 'global'}
    known = _known_globals(db, gnames)
    out = {'speaker': s, 'topics': [], 'detail': None, 'state': p}
    for k, t in topics.items():
        said, maybe = _pick(t['lines'], s, p, known)
        if said is None and not maybe:
            if k != open_topic:
                continue
        ln = t['lines'][said] if said is not None else None
        out['topics'].append({'key': k, 'id': t['id'], 'type': t['type'], 'n': len(t['lines']),
                              'said': _brief(ln, s, p, known) if ln else None, 'maybe': len(maybe),
                              'own': any(x['actor'] for x in t['lines'])})
    out['topics'].sort(key=lambda x: (x['type'] != 2, x['type'], x['id'].lower()))
    if open_topic and open_topic in topics:
        t = topics[open_topic]
        sh = shadowed(t['lines'])
        said, maybe = _pick(t['lines'], s, p, known)
        rows = []
        for n, ln in enumerate(t['lines']):
            b = _brief(ln, s, p, known)
            b['said'] = n == said
            b['shadow'] = sh.get(n)
            rows.append(b)
        out['detail'] = {'key': open_topic, 'id': t['id'], 'type': t['type'], 'lines': rows, 'said': said}
    out['inputs'] = inputs(db, s, topics)
    return out


def problems(db, npc_id, cell=None, everything=False):
    """Lines of this character that can never be said: a line above always wins. Only where
    your mod's lines are involved, unless everything: the game's own data has thousands of these
    (lore lines written twice, a place's line under a wider place's), and nothing to do about them."""
    s, topics = _speaker_lines(db, npc_id, cell)
    out = []
    for k, t in topics.items():
        for j, i in shadowed(t['lines']).items():
            lj, li = t['lines'][j], t['lines'][i]
            if not everything and not lj['mine']:      # (a line of yours over the game's is how you give someone their own)
                continue
            out.append({'topic': k, 'id': t['id'], 'line': {'inam': lj['inam'], 'text': lj['text'][:200], 'mine': lj['mine'],
                                                             'src': lj['src'], 'tier': _tier(lj), 'topic': lj['topic']},
                        'by': {'inam': li['inam'], 'text': li['text'][:200], 'mine': li['mine'], 'src': li['src'],
                               'tier': _tier(li), 'topic': li['topic']}})
    return out


TIERS = {'own': 0, 'group': 1, 'all': 2}


def conversation_map(db, npc_id, scope='own', cell=None):
    """The conversation map: this character's topics as boxes of lines, with what each line
    leads to (topics it mentions or adds, choices, quest stages it sets) and what it needs
    (quest stages). scope: 'own' (lines just for them), 'group' (also their race, class,
    faction, place) or 'all' (also what everyone says)."""
    s, topics = _speaker_lines(db, npc_id, cell)
    lim = TIERS.get(scope, 0)
    boxes, wanted = {}, set()
    for k, t in topics.items():
        sh = shadowed(t['lines'])
        rows = []
        for n, ln in enumerate(t['lines']):
            tier = _tier(ln)
            if TIERS[tier] > lim:
                continue
            fx = effects(ln['result'])
            lk = [x for x in links(db, ln['text']) if x != k]
            needs = [{'quest': c['name'].lower(), 'op': c['op'], 'value': c['value']} for c in ln['conds'] if c['kind'] == 'journal']
            answer = next((int(c['value']) for c in ln['conds'] if c['kind'] == 'function' and c['func'] == dialogue.CHOICE), None)
            rows.append({'inam': ln['inam'], 'n': n, 'text': ln['text'], 'tier': tier, 'mine': ln['mine'], 'src': ln['src'],
                         'topic': ln['topic'], 'links': lk, 'needs': needs, 'answer': answer, 'fx': fx,
                         'other': sum(1 for c in ln['conds'] if c['kind'] != 'journal' and not
                                      (c['kind'] == 'function' and c['func'] == dialogue.CHOICE)) + (1 if ln['disp'] else 0),
                         'shadow': sh.get(n)})
            wanted |= set(lk) | set(fx['learns'])
        if rows:
            boxes[k] = {'key': k, 'id': t['id'], 'type': t['type'], 'lines': rows, 'n': len(t['lines']), 'ghost': False}
    # topics the shown lines lead to but whose lines aren't shown: a box with no lines
    for k in wanted:
        if k not in boxes:
            t = topics.get(k)
            boxes[k] = {'key': k, 'id': t['id'] if t else k, 'type': 0, 'lines': [], 'n': len(t['lines']) if t else 0,
                        'ghost': True, 'theirs': t is not None}
    quests = {}
    for b in boxes.values():
        for r in b['lines']:
            for q in [x['quest'] for x in r['needs']] + [x['quest'] for x in r['fx']['sets']]:
                if q not in quests:
                    try:
                        qq = dialogue.quest(db, q)
                        quests[q] = {'key': q, 'id': qq['id'], 'title': qq['title'],
                                     'stages': [{'index': x['index'], 'text': x['text'][:160], 'finished': x['finished']} for x in qq['stages']]}
                    except EditError:
                        quests[q] = {'key': q, 'id': q, 'title': '', 'stages': []}
    counts = {tier: sum(1 for t in topics.values() for ln in t['lines'] if _tier(ln) == tier) for tier in TIERS}
    return {'speaker': s, 'scope': scope, 'boxes': sorted(boxes.values(), key=lambda b: (b['type'] != 2, b['ghost'], b['id'].lower())),
            'quests': list(quests.values()), 'counts': counts}


def quest_map(db, qkey):
    """The quest as a flow: its stages, and every line in the game that needs a stage of it or
    moves it on, with who says it."""
    q = dialogue.quest(db, qkey)
    low = q['key']
    idx = _index(db)
    rows = []
    for k, (t, name, slims) in idx.items():
        if not any(low in sl[9] for sl in slims):
            continue
        for (ii, d), sl in zip(dialogue.ordered_lines(db, k), slims):
            if low not in sl[9] or d['deleted']:
                continue
            fx = effects(d['result'])
            needs = [{'op': c['op'], 'value': c['value']} for c in d['conds'] if c['kind'] == 'journal' and c['name'].lower() == low]
            sets = [x['stage'] for x in fx['sets'] if x['quest'] == low]
            if not needs and not sets:
                continue
            ai = db.resolve_id(d['actor']) if d['actor'] else None
            who = (db.recs[ai][2] or d['actor'] if ai is not None else d['actor']) or ' · '.join(x for x in (d['race'], d['cls'], d['faction'] if d['faction'].lower() != 'ffff' else '', d['cell']) if x) or 'anyone'
            other = [c for c in d['conds'] if not (c['kind'] == 'journal' and c['name'].lower() == low)]
            rows.append({'topic': k, 'tid': 'Greeting' if k in GREETINGS else name, 'inam': d['inam'], 'text': d['text'],
                         'who': who, 'actor': d['actor'], 'needs': needs, 'sets': sets, 'other': other,
                         'mine': db.recs[ii][3] == db.proj_pidx, 'src': db.plugins[db.recs[ii][3]]['name'],
                         'learns': fx['learns'], 'choices': fx['choices'], 'gives': fx['gives'], 'takes': fx['takes']})
    return {'quest': q, 'lines': rows[:600], 'more': max(0, len(rows) - 600)}
