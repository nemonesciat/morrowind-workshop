"""The conversation builder: one character's lines in one topic, as the tree they make, and back.

A conversation is what someone says when the player clicks a topic (or greets them): one or more
versions, the first that fits being said ("if the quest is at 20 say this, otherwise that"). A
version can offer the player answers (the result script's Choice); each answer leads to what they
say next, which can offer answers again.

In the game's data that is all plain lines of the topic: an answer is a line with the condition
"Choice = n", where n is the number the asking line gave that answer. So the tree is read back from
the lines (this works for the game's own conversations too) and written back as lines, nothing kept
on the side:
- every answer in a conversation gets its own number, so no line answers the wrong question;
- the lines that answer go above the ones that ask, or the asking line (asking for less) would win;
- the whole conversation stays together where it was in the topic, above everyone else's lines."""
import re

import dialogue
from dialogue import CHOICE, _dial_versions, _dial_type, _ensure_dial, _new_inam, _put, _relink, ordered_lines, parse_info
from editing import EditError, commit, _require_project

KEEP = ('race', 'cls', 'faction', 'cell', 'pcfaction', 'sound', 'sex', 'rank', 'pcrank', 'unk', 'qname', 'qfinish', 'qrestart')

_A = [  # (kind, pattern) for the lines of a result script the builder shows as actions
    ('journal', re.compile(r'^(?:Journal|SetJournalIndex)\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*,?\s*(-?\d+)\s*$', re.I)),
    ('give', re.compile(r'^Player\s*->\s*AddItem\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*,?\s*(\d+)\s*$', re.I)),
    ('take', re.compile(r'^Player\s*->\s*RemoveItem\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*,?\s*(\d+)\s*$', re.I)),
    ('topic', re.compile(r'^AddTopic\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*$', re.I)),
    ('disp', re.compile(r'^ModDisposition\s*,?\s*(-?\d+)\s*$', re.I)),
    ('bye', re.compile(r'^Goodbye\s*$', re.I)),
]
_CHOICE = re.compile(r'^Choice\b(.*)$', re.I)
_ANS = re.compile(r'"([^"]*)"\s*,?\s*(\d+)')


def _split_result(res):
    """A result script as ([action], [(label, n)], other script text)."""
    acts, answers, rest = [], [], []
    for raw in (res or '').replace('\r\n', '\n').split('\n'):
        ln = raw.strip()
        if not ln:
            continue
        m = _CHOICE.match(ln)
        if m and _ANS.search(m.group(1)):
            answers += [(a, int(n)) for a, n in _ANS.findall(m.group(1))]
            continue
        for kind, rx in _A:
            m = rx.match(ln)
            if m:
                if kind in ('journal', 'give', 'take'):
                    acts.append({'kind': kind, 'id': (m.group(1) or m.group(2)).strip(), 'n': int(m.group(3))})
                elif kind == 'topic':
                    acts.append({'kind': kind, 'id': (m.group(1) or m.group(2)).strip()})
                elif kind == 'disp':
                    acts.append({'kind': kind, 'n': int(m.group(1))})
                else:
                    acts.append({'kind': kind})
                break
        else:
            rest.append(raw.rstrip())
    return acts, answers, '\n'.join(rest)


def _q(s):
    return '"%s"' % (s or '').replace('"', "'")


def _join_result(acts, answers, script):
    out = []
    for a in acts or []:
        k = a.get('kind')
        if k == 'journal' and a.get('id'):
            out.append('Journal %s %d' % (_q(a['id']), int(a.get('n') or 0)))
        elif k == 'give' and a.get('id'):
            out.append('Player->AddItem %s %d' % (_q(a['id']), max(1, int(a.get('n') or 1))))
        elif k == 'take' and a.get('id'):
            out.append('Player->RemoveItem %s %d' % (_q(a['id']), max(1, int(a.get('n') or 1))))
        elif k == 'topic' and a.get('id'):
            out.append('AddTopic %s' % _q(a['id']))
        elif k == 'disp':
            out.append('ModDisposition %d' % int(a.get('n') or 0))
    if (script or '').strip():
        out.append(script.strip('\n'))
    if answers:
        out.append('Choice ' + ' '.join('%s %d' % (_q(lbl), n) for lbl, n in answers))
    if any(a.get('kind') == 'bye' for a in acts or []):
        out.append('Goodbye')
    return '\n'.join(out)


def _ckey(c):
    return (c.get('kind'), (c.get('name') or '').lower(), c.get('func') if c.get('kind') == 'function' else None,
            c.get('op', '='), float(c.get('value') or 0))


def _choice_of(d):
    for c in d['conds']:
        if c['kind'] == 'function' and c.get('func') == CHOICE and c['op'] == '=':
            return int(c['value'])
    return None


# ---------------------------------------------------------------- reading
def read(db, actor, dkey):
    """The conversation as a tree: {'topic', 'id', 'type', 'say': [version], 'notes': [...]}.
    A version: {inam, text, conds, disp, actions, script, answers: [{label, n, say: [version]}],
    mine, src, keep}."""
    dkey = dkey.lower()
    vs = _dial_versions(db, dkey)
    if not vs:
        raise EditError('There is no topic called "%s".' % dkey)
    low = actor.lower()
    lines = [(ii, d) for ii, d in ordered_lines(db, dkey) if d['actor'].lower() == low and not d['deleted']]
    nodes = []
    for pos, (ii, d) in enumerate(lines):
        acts, answers, script = _split_result(d['result'])
        n = _choice_of(d)
        nodes.append({'pos': pos, 'n': n, 'offers': answers, 'parent': None,
                      'v': {'inam': d['inam'], 'text': d['text'], 'disp': d['disp'],
                            'conds': [c for c in d['conds'] if not (c['kind'] == 'function' and c.get('func') == CHOICE and c['op'] == '=')]
                            if n is not None else d['conds'],
                            'actions': acts, 'script': script, 'answers': [], 'mine': db.recs[ii][3] == db.proj_pidx,
                            'src': db.plugins[db.recs[ii][3]]['name'], 'keep': {k: d[k] for k in KEEP}}})
    notes = []
    # each answer line belongs to a line that offers its number: the first such line below it (where the
    # game's own conversations put the asking line), else the nearest above
    for nd in nodes:
        if nd['n'] is None:
            continue
        below = [p for p in nodes if p is not nd and p['pos'] > nd['pos'] and any(x[1] == nd['n'] for x in p['offers'])]
        above = [p for p in nodes if p is not nd and p['pos'] < nd['pos'] and any(x[1] == nd['n'] for x in p['offers'])]
        cand = below[:1] or above[-1:]
        p = cand[0] if cand else None
        q, loop = p, False
        while q is not None:                     # an answer can't be its own question
            if q is nd:
                loop = True
                break
            q = q['parent']
        if p is None or loop:
            # nothing asks for it (or it would go round in a circle): keep its Choice test as a plain condition
            nd['v']['conds'] = [c for c in lines[nd['pos']][1]['conds']]
            nd['n'] = None
            notes.append('“%s…” answers choice %s, which %s.' % (nd['v']['text'][:40], _choice_of(lines[nd['pos']][1]),
                                                                  'leads back round to it' if loop else 'no line here offers'))
        else:
            nd['parent'] = p
    shared = {}
    for nd in nodes:
        for lbl, n in nd['offers']:
            shared.setdefault(n, []).append(nd)
    for nd in nodes:
        for lbl, n in nd['offers']:
            kids = [k['v'] for k in nodes if k['parent'] is nd and k['n'] == n]
            nd['v']['answers'].append({'label': lbl, 'n': n, 'say': kids, 'shared': len(shared[n]) > 1})
    t = _dial_type(db, vs[-1])
    return {'topic': dkey, 'id': db.recs[vs[-1]][1], 'type': t, 'actor': actor,
            'say': [nd['v'] for nd in nodes if nd['n'] is None], 'notes': notes}


def conversations(db, actor):
    """The topics this character has lines of their own in, as conversations to open."""
    c = dialogue.character(db, actor)
    out = []
    for t in c['topics']:
        if t['type'] in (0, 2, 3):
            out.append({'topic': t['key'], 'id': t['id'], 'type': t['type'], 'lines': len(t['lines']),
                        'choices': sum(1 for ln in t['lines'] if 'choice' in (ln['result'] or '').lower()),
                        'mine': sum(1 for ln in t['lines'] if ln['mine'])})
    return out


# ---------------------------------------------------------------- writing
def save(db, actor, dkey, tree):
    """Write a conversation tree back as the topic's lines, as one change."""
    _require_project(db)
    dkey = dkey.lower()
    actor = (actor or '').strip()
    if not actor:
        raise EditError('A conversation needs the character who says it.')
    vs = _dial_versions(db, dkey)
    if not vs:
        raise EditError('There is no topic called "%s".' % dkey)
    t = _dial_type(db, vs[-1])
    if t not in (0, 2, 3):
        raise EditError('"%s" is not a topic people say.' % db.recs[vs[-1]][1])
    low = actor.lower()
    cur = [(ii, d) for ii, d in ordered_lines(db, dkey)]
    by = {d['inam']: (ii, d) for ii, d in cur}
    old_own = [d['inam'] for _ii, d in cur if d['actor'].lower() == low and not d['deleted']]
    # answers keep the numbers they have (the game's own conversations reuse numbers at different
    # stages, and their lines count on it); a new answer gets a number nothing here uses yet
    used = {n for _ii, d in cur if d['actor'].lower() == low for _l, n in _split_result(d['result'])[1]}

    def collect(vers):
        for v in vers:
            for a in v.get('answers') or []:
                n = a.get('n')
                a['_n'] = n if isinstance(n, int) and n > 0 else None
                if a['_n']:
                    used.add(n)
                collect(a.get('say') or [])
    collect(tree.get('say') or [])

    def number(vers):
        for v in vers:
            for a in v.get('answers') or []:
                if a['_n'] is None:
                    n = 1
                    while n in used:
                        n += 1
                    used.add(n)
                    a['_n'] = n
                number(a.get('say') or [])
    number(tree.get('say') or [])
    # the lines, answers (at any depth) first, then what they say before any answer
    asks, roots, count = [], [], [0]

    def line_of(v, choice):
        text = v.get('text') or ''
        text = text if text.strip() else ''
        conds = list(v.get('conds') or [])        # (a Choice test here is one read back with nothing asking it: it stays)
        for c in conds:
            if c.get('kind') == 'choice':
                raise EditError('Answers are made with "+ Answer", not as a condition.')
        if choice is not None:
            conds = conds + [{'kind': 'function', 'func': CHOICE, 'op': '=', 'value': choice}]
        if len(conds) > 6:
            raise EditError('“%s…” has more than 6 conditions (an answer uses one of them).' % text[:40])
        answers = [(a.get('label') if (a.get('label') or '').strip() else 'Continue', a['_n']) for a in v.get('answers') or []]
        result = _join_result(v.get('actions'), answers, v.get('script'))
        old = by.get(v.get('inam') or '')
        if old:
            # a line that means what it meant keeps its own wording (quotes, order, spacing) and condition order
            o_acts, o_ans, o_script = _split_result(old[1]['result'])
            norm = lambda acts: [{k: a.get(k) for k in ('kind', 'id', 'n') if a.get(k) is not None} for a in acts or []]
            if norm(o_acts) == norm(v.get('actions')) and o_ans == answers and o_script.strip() == (v.get('script') or '').strip():
                result = old[1]['result']
            o_conds = old[1]['conds']
            strip = lambda cs: [_ckey(c) for c in cs if not (c.get('kind') == 'function' and c.get('func') == CHOICE and c.get('op', '=') == '=')]
            if strip(o_conds) == strip(conds) and _choice_of(old[1]) == choice:
                conds = o_conds
        if old and old[1]['actor'].lower() == low:
            d = dict(old[1])
        else:
            d = dict(parse_info(b''))
            d.update(type=t, inam='')
            for k, val in (v.get('keep') or {}).items():
                if k in KEEP:
                    d[k] = val
        d.update(actor=d['actor'] if old and d['actor'] else actor, text=text, conds=conds, result=result,
                 disp=int(v.get('disp') or 0), deleted=False)
        return d

    def walk(vers, choice):
        for v in vers:
            d = line_of(v, choice)
            count[0] += 1
            (roots if choice is None else asks).append(d)
            for a in v.get('answers') or []:
                walk(a.get('say') or [], a['_n'])
    walk(tree.get('say') or [], None)
    wanted = asks + roots
    # lines that were all there already keep their order, unless a line that asks sits above one that
    # answers it and would win over it (asking for no more than the answer does)
    pos0 = {d['inam']: n for n, (_ii, d) in enumerate(cur)}
    in_place = False
    if wanted and all(d['inam'] in pos0 for d in wanted):
        old_order = sorted(wanted, key=lambda d: pos0[d['inam']])
        bad = False
        for i, hi in enumerate(old_order):
            if _choice_of(hi) is not None:
                continue
            ks = {_ckey(c) for c in hi['conds']}
            for lo in old_order[i + 1:]:
                if _choice_of(lo) is not None and ks <= {_ckey(c) for c in lo['conds']} and (hi['disp'] or 0) <= (lo['disp'] or 0) \
                        and all(not hi[f] or hi[f] == lo[f] for f in ('cell', 'pcfaction', 'race', 'cls', 'faction')) and hi['sex'] in (-1, lo['sex']):
                    bad = True
        if not bad:
            wanted, in_place = old_order, True
    for d in wanted:
        if not d['inam']:
            d['inam'] = _new_inam(db, dkey)
    keep_ids = {d['inam'] for d in wanted}
    gone = [i for i in old_own if i not in keep_ids]
    # where the conversation goes: where its first line was, else at the top
    ids = [d['inam'] for _ii, d in cur if not d['deleted']]
    others = [i for i in ids if i not in set(old_own) and i not in keep_ids]
    at = 0
    if old_own:
        first = ids.index(old_own[0])
        at = sum(1 for i in ids[:first] if i in set(others))
    order = others[:at] + [d['inam'] for d in wanted] + others[at:]
    if in_place:                                 # (the lines were all there, in a working order: they stay where they are)
        order = [i for i in ids if i not in set(gone)]
    changed = order != [i for i in ids if i not in set(gone)] or bool(gone)
    same = lambda a, b: dialogue.build_info(dict(a, prev='', next=''), db) == dialogue.build_info(dict(b, prev='', next=''), db)
    edited = bool(gone)
    for d in wanted:
        old = by.get(d['inam'])
        if not old or not same(old[1], d):
            changed = edited = True
    if not edited:                               # nothing you changed: even an order the builder would mend stays
        changed = False
    if not changed:
        return read(db, actor, dkey)
    _ensure_dial(db, dkey)
    for d in wanted:
        if in_place and d['inam'] in by and same(by[d['inam']][1], d):
            continue                             # (unchanged and staying put: the game's own line stays the game's)
        rec = db.project.records.get('INFO|' + dkey + '|' + d['inam'].lower())
        created = bool(rec and rec.get('created')) or d['inam'] not in by
        _put(db, dkey, d, created)
    for inam in gone:
        k = 'INFO|' + dkey + '|' + inam.lower()
        rec = db.project.records.get(k)
        if rec and rec.get('created'):
            db.project.records.pop(k)
        else:                                    # someone else's line: your mod takes it out
            _put(db, dkey, dict(by[inam][1], deleted=True), False)
    db.sync_project()
    _relink(db, dkey, order)
    vs = _dial_versions(db, dkey)
    commit(db, 'Wrote a conversation for %s in "%s" (%d line%s)' % (actor, db.recs[vs[-1]][1], count[0], '' if count[0] == 1 else 's'))
    return read(db, actor, dkey)
