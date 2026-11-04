"""The quest Board: a quest read as a row of snapshots of its cast.

A quest's cast is the set of things it touches: the people who speak of it, the items it asks for
or hands over, the places it is tied to, and the things (books, doors, corpses) whose scripts move
it on. A stage is a snapshot of that cast: who holds what, who is dead, what the journal says. The
moves between stages are the lines and script blocks that set a stage, each named by what the
player did (talk, bring, take, kill, read, enter, wait...). The Board shows the frames in a row,
the moves as arrows, and flags stages nothing leads to (unreachable) and stages nothing leads out
of (dead ends), which is what the journal and the editor both hide.

Reading only; the user's own quests are written through the same dialogue and script writers
as the rest of the Workshop (convbuild, mwscript)."""
import re

import convo
import dialogue
import npc
from editing import EditError
from esm import ENC, iter_subrecords, zstr

GOLD = 'gold_001'
# the tags a cast member can have, and what to call it
KIND = {'NPC_': 'person', 'CREA': 'creature', 'BOOK': 'book', 'DOOR': 'door', 'ACTI': 'thing', 'CONT': 'container',
        'MISC': 'item', 'WEAP': 'item', 'ARMO': 'item', 'CLOT': 'item', 'ALCH': 'item', 'INGR': 'item', 'APPA': 'item',
        'LOCK': 'item', 'PROB': 'item', 'REPA': 'item', 'LIGH': 'item', 'STAT': 'thing'}

_RX_IF = re.compile(r'^\s*(if|elseif|else|endif|while|endwhile)\b\s*(.*)$', re.I)
_RX_GJI = re.compile(r'GetJournalIndex\s*,?\s*(?:"([^"]+)"|([\w\'-]+))\s*(==|!=|>=|<=|>|<|=)\s*(-?\d+)', re.I)
_RX_GJI2 = re.compile(r'(-?\d+)\s*(==|!=|>=|<=|>|<|=)\s*GetJournalIndex\s*,?\s*(?:"([^"]+)"|([\w\'-]+))', re.I)
_RX_CELL = re.compile(r'GetPCCell\s*,?\s*(?:"([^"]+)"|([\w\'-]+))', re.I)
_RX_COUNT = re.compile(r'(?:(\w+)\s*->\s*)?GetItemCount\s*,?\s*(?:"([^"]+)"|([\w\'-]+))', re.I)
_RX_DEAD = re.compile(r'GetDeadCount\s*,?\s*(?:"([^"]+)"|([\w\'-]+))', re.I)
_RX_DIST = re.compile(r'(?:(\w+)\s*->\s*)?GetDistance\s*,?\s*(?:"([^"]+)"|([\w\'-]+))', re.I)
_FLIP = {'==': '!=', '!=': '==', '>=': '<', '<=': '>', '>': '<=', '<': '>=', '=': '!='}

_SC = {'key': None, 'byq': {}}


# ---------------------------------------------------------------- scripts that move quests
def _script_text(db, ri):
    r = db.recs[ri]
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'SCTX':
            return bytes(d).decode(ENC, 'replace').rstrip('\0')
    return ''


def _scripts_by_quest(db):
    """quest key -> [(script id, rec idx)] for every script that sets a stage of it; read once per game data."""
    key = (id(db.files), len(db.plugins), len(db.project.log) if db.project else 0)
    if _SC['key'] == key:
        return _SC['byq']
    byq = {}
    for (tag, k), lst in list(db.by_key.items()):
        if tag != 'SCPT':
            continue
        vs = [v for v in lst if v not in db.dead]
        if not vs:
            continue
        ri = vs[-1]
        text = _script_text(db, ri)
        if 'journal' not in text.lower():
            continue
        for m in convo._RX_JOURNAL.finditer(re.sub(r';[^\n]*', '', text)):
            byq.setdefault(convo._q(m).lower(), set()).add((db.recs[ri][1], ri))
    _SC.update(key=key, byq={q: sorted(v) for q, v in byq.items()})
    return _SC['byq']


def _blocks(text):
    """The script as (conditions wrapping it, line) for every line: the if/elseif/else/while tests
    above each line, 'else' as the earlier tests of that chain turned round."""
    out, stack = [], []
    for raw in text.splitlines():
        line = re.sub(r';.*', '', raw).strip()
        if not line:
            continue
        m = _RX_IF.match(line)
        if m:
            w, rest = m.group(1).lower(), m.group(2).strip()
            if w in ('if', 'while'):
                stack.append([rest])
            elif w == 'elseif' and stack:
                stack[-1] = ['not (%s)' % c for c in stack[-1]] + [rest]
            elif w == 'else' and stack:
                stack[-1] = ['not (%s)' % c for c in stack[-1]]
            elif w in ('endif', 'endwhile') and stack:
                stack.pop()
            continue
        out.append(([c for grp in stack for c in grp], line))
    return out


def _needs_from(conds, low):
    """The stage tests about this quest among a block's conditions."""
    needs = []
    for c in conds:
        neg = c.startswith('not (')
        for m in _RX_GJI.finditer(c):
            if convo._q(m).lower() == low:
                op = m.group(3).replace('==', '=')
                needs.append({'op': _FLIP[op] if neg else op, 'value': int(m.group(4))})
        for m in _RX_GJI2.finditer(c):
            if convo._q(m, 3, 4).lower() == low:
                op = _FLIP[m.group(2).replace('==', '=')]        # 10 < GetJournalIndex  ==  GetJournalIndex > 10
                needs.append({'op': _FLIP[op] if neg else op, 'value': int(m.group(1))})
    return needs


def _waits_on(conds, low):
    """The stage tests about other quests among a block's conditions."""
    out = []
    for c in conds:
        neg = c.startswith('not (')
        for m in _RX_GJI.finditer(c):
            if convo._q(m).lower() != low:
                op = m.group(3).replace('==', '=')
                out.append({'quest': convo._q(m), 'op': _FLIP[op] if neg else op, 'value': int(m.group(4))})
    return out


def _verb_of(conds, carrier):
    """What the player did, read off the tests wrapping a script's Journal line."""
    t = ' '.join(conds).lower()
    kind = carrier['kind'] if carrier else ''
    if 'ondeath' in t or 'getdeadcount' in t:
        return 'kill'
    if 'onactivate' in t:
        return {'book': 'read', 'door': 'open', 'container': 'open', 'person': 'talk', 'creature': 'talk'}.get(kind, 'use')
    if 'onpcadd' in t or 'onpcequip' in t:
        return 'take'
    if 'onpcdrop' in t:
        return 'drop'
    if 'getpccell' in t or 'cellchanged' in t:
        return 'enter'
    if 'getdistance' in t or 'getlos' in t:
        return 'approach'
    if 'getitemcount' in t:
        return 'have'
    if 'dayspassed' in t or 'timer' in t or 'getsecondspassed' in t or 'gamehour' in t or 'day ' in t + ' ':
        return 'wait'
    if 'getdisposition' in t or 'getpcrank' in t or 'pcexpelled' in t or 'getfactionreaction' in t:
        return 'stand'
    if 'onpchitme' in t or 'getattacked' in t or 'getcombat' in t or 'gethealth' in t:
        return 'fight'
    if 'getjournalindex' in t or not t:
        return 'script'
    return 'script'


def _script_moves(db, sid, ri, low, cast):
    """Each place a script sets a stage of the quest, as a move."""
    text = _script_text(db, ri)
    carriers = _carriers(db, sid)
    carrier = carriers[0] if carriers else None
    moves = []
    lines = _blocks(text)
    for n, (conds, line) in enumerate(lines):
        for m in convo._RX_JOURNAL.finditer(line):
            if convo._q(m).lower() != low:
                continue
            stage = int(m.group(3))
            # what the same block does around it: items handed over or taken away
            block = [l for c, l in lines[max(0, n - 12):n + 12] if c == conds]
            fx = convo.effects('\n'.join(block))
            verb = _verb_of(conds, carrier)
            who = carrier
            for c in carriers:
                if c['kind'] in ('person', 'creature'):
                    who = c
                    break
            mv = {'via': 'script', 'script': sid, 'verb': verb, 'who': who['id'] if who else '', 'whoName': who['name'] if who else '',
                  'needs': _needs_from(conds, low), 'sets': [stage], 'gives': fx['gives'], 'takes': fx['takes'],
                  'text': _plain(conds), 'topic': '', 'inam': '', 'mine': db.recs[ri][3] == db.proj_pidx,
                  'src': db.plugins[db.recs[ri][3]]['name'], 'carriers': [c['id'] for c in carriers],
                  'waits': _waits_on(conds, low), 'also': [{'quest': convo._q(mm), 'stage': int(mm.group(3))}
                                                           for l_ in block for mm in convo._RX_JOURNAL.finditer(l_) if convo._q(mm).lower() != low]}
            for c in conds:
                for mm in _RX_CELL.finditer(c):
                    _add(cast, db, convo._q(mm), 'place')
                    mv.setdefault('places', []).append(convo._q(mm))
                for mm in _RX_COUNT.finditer(c):
                    _add(cast, db, convo._q(mm, 2, 3))
                    mv.setdefault('items', []).append(convo._q(mm, 2, 3))
                for mm in _RX_DEAD.finditer(c):
                    _add(cast, db, convo._q(mm))
                    mv['who'] = mv['who'] or convo._q(mm)
                    mv['whoName'] = mv['whoName'] or _name(db, convo._q(mm))
                for mm in _RX_DIST.finditer(c):
                    _add(cast, db, convo._q(mm, 2, 3))
            for c in carriers:
                _add(cast, db, c['id'])
            moves.append(mv)
    return moves


def _plain(conds):
    """A script block's tests as one short line."""
    s = ' and '.join(c for c in conds if c)
    s = re.sub(r'\s+', ' ', s)
    return s[:200]


def _carriers(db, sid):
    """The objects and people that carry a script (what the move happens to)."""
    import mwscript
    out = []
    for u in mwscript.used_by(db, sid):
        if u['kind'] in ('dialogue', 'start'):
            continue
        out.append({'id': u.get('id', ''), 'name': u.get('label', ''), 'kind': KIND.get(u['kind'], 'thing')})
    return out[:6]


# ---------------------------------------------------------------- the cast
def _name(db, rid):
    ri = db.resolve_id(rid) if rid else None
    return (db.recs[ri][2] or db.recs[ri][1]) if ri is not None else rid


def _add(cast, db, rid, kind=None):
    """Put a thing in the cast (once), with its kind and where it is."""
    low = (rid or '').lower().strip()
    if not low or low in cast:
        return
    if kind == 'place':
        cast[low] = {'id': rid, 'name': rid, 'kind': 'place', 'where': []}
        return
    ri = db.resolve_id(rid)
    if ri is None:
        cast[low] = {'id': rid, 'name': rid, 'kind': 'unknown', 'where': []}
        return
    r = db.recs[ri]
    kind = 'gold' if low == GOLD else KIND.get(r[0], 'thing')
    where = []
    for ci in sorted(db.used_in.get(low, ()))[:60]:
        rr = db.recs[ci]
        if rr is None or ci in db.dead:
            continue
        if rr[0] == 'CELL':
            nm = rr[1] if rr[7].startswith('#') else (rr[2] or rr[1])
            where.append({'kind': 'place', 'id': rr[7], 'name': nm or rr[7]})
        elif rr[0] in ('NPC_', 'CREA', 'CONT'):
            where.append({'kind': KIND.get(rr[0], 'thing'), 'id': rr[1], 'name': rr[2] or rr[1]})
        if len(where) >= 6:
            break
    seen, uniq = set(), []
    for w in where:
        if w['id'].lower() not in seen:
            seen.add(w['id'].lower())
            uniq.append(w)
    cast[low] = {'id': r[1], 'name': r[2] or r[1], 'kind': kind, 'where': uniq}


# ---------------------------------------------------------------- the board
def _line_moves(db, q, cast):
    """The dialogue lines that need or set a stage, as moves (from the quest Flow's reading)."""
    fl = convo.quest_map(db, q['key'])
    moves = []
    for l in fl['lines']:
        verb = 'meet' if l['tid'] == 'Greeting' else 'talk'
        if l['takes']:
            verb = 'bring'
        elif any(c['kind'] == 'item' for c in l['other']):
            verb = 'show'
        if l['actor']:
            _add(cast, db, l['actor'])
        for c in l['other']:
            if c['kind'] == 'item':
                _add(cast, db, c['name'])
            elif c['kind'] == 'dead':
                _add(cast, db, c['name'])
                if not l['sets']:
                    continue
                verb = 'kill' if verb == 'talk' else verb
        for g in l['gives'] + l['takes']:
            _add(cast, db, g['id'])
        moves.append({'via': 'line', 'topic': l['topic'], 'tid': l['tid'], 'inam': l['inam'], 'verb': verb,
                      'who': l['actor'], 'whoName': l['who'], 'needs': l['needs'], 'sets': l['sets'],
                      'gives': l['gives'], 'takes': l['takes'], 'text': l['text'], 'learns': l['learns'],
                      'choices': l['choices'], 'other': len(l['other']), 'mine': l['mine'], 'src': l['src'],
                      'items': [c['name'] for c in l['other'] if c['kind'] == 'item'],
                      'waits': [{'quest': c['name'], 'op': c['op'], 'value': c['value']} for c in l['other'] if c['kind'] == 'journal'],
                      'also': l.get('also', [])})
    return moves, fl['more']


def _fits(v, nd):
    return {'=': v == nd['value'], '!=': v != nd['value'], '>': v > nd['value'], '>=': v >= nd['value'],
            '<': v < nd['value'], '<=': v <= nd['value']}.get(nd['op'], True)


def board(db, qkey):
    """The quest as frames (its stages), its cast, and the moves between frames."""
    q = dialogue.quest(db, qkey)
    low = q['key']
    cast = {}
    moves, more = _line_moves(db, q, cast)
    for sid, ri in _scripts_by_quest(db).get(low, []):
        moves += _script_moves(db, sid, ri, low, cast)
    # the cast picked on the Board before any move used them (kept in the project)
    import questmake
    pinned = questmake.pinned(db, low)
    for rid in pinned:
        _add(cast, db, rid)
    for c in cast.values():
        c['pinned'] = c['id'].lower() in {p.lower() for p in pinned}
    # the people's places
    for c in list(cast.values()):
        if c['kind'] in ('person', 'creature') and not c['where']:
            c['where'] = [{'kind': 'place', 'id': p['key'], 'name': p['name']} for p in npc.placements(db, c['id'])[:4]]
    stages = sorted({s['index'] for s in q['stages']} | {s for m in moves for s in m['sets']})
    text = {s['index']: s for s in q['stages']}
    frames = []
    for n, idx in enumerate(stages):
        st = text.get(idx)
        before = [0] + stages[:n]
        ins = [i for i, m in enumerate(moves) if idx in m['sets']]
        outs = [i for i, m in enumerate(moves) if idx not in m['sets'] and m['needs'] and all(_fits(idx, nd) for nd in m['needs'])
                and not all(all(_fits(b, nd) for nd in m['needs']) for b in before)]
        frames.append({'index': idx, 'text': st['text'] if st else '', 'finished': bool(st and st['finished']),
                       'missing': st is None, 'mine': bool(st and st['mine']), 'in': ins, 'out': outs})
    # reachable: set by a move whose own needs can be met from a reachable stage (or from nothing)
    reach = set()
    changed = True
    while changed:
        changed = False
        for m in moves:
            ok = not m['needs'] or any(all(_fits(s, nd) for nd in m['needs']) for s in [0] + sorted(reach))
            if ok:
                for s in m['sets']:
                    if s not in reach:
                        reach.add(s)
                        changed = True
    for f in frames:
        f['reachable'] = f['index'] in reach
        # something leads on: a move that can happen at this stage (or at any stage) and sets a later one
        later = [i for i, m in enumerate(moves) if any(s > f['index'] for s in m['sets'])
                 and all(_fits(f['index'], nd) for nd in m['needs'])]
        f['deadend'] = not f['finished'] and not later and f['index'] != max(stages or [0])
    _states(frames, moves, cast)
    verbs = {}
    for m in moves:
        verbs[m['verb']] = verbs.get(m['verb'], 0) + 1
    return {'quest': q, 'cast': sorted(cast.values(), key=lambda c: (_KORD.get(c['kind'], 9), c['name'].lower())),
            'frames': frames, 'moves': moves, 'more': more, 'verbs': verbs,
            'scripts': sorted({m['script'] for m in moves if m['via'] == 'script'})}


_KORD = {'person': 0, 'creature': 1, 'item': 2, 'gold': 3, 'book': 4, 'door': 5, 'container': 6, 'thing': 7, 'place': 8}


def _states(frames, moves, cast):
    """What each frame looks like: the player's bag, who is dead, who holds what, walking the
    stages in order and applying the moves that lead into each (the main line of the quest)."""
    bag, dead, holder = {}, set(), {}
    for c in cast.values():
        if c['kind'] in ('item', 'book') and c['where']:
            w = c['where'][0]
            holder[c['id'].lower()] = w['name']
    for f in frames:
        for i in f['in']:
            m = moves[i]
            for g in m['gives']:
                bag[g['id'].lower()] = bag.get(g['id'].lower(), 0) + g['n']
                holder[g['id'].lower()] = 'Player'
            for g in m['takes']:
                k = g['id'].lower()
                bag[k] = max(0, bag.get(k, 0) - g['n'])
                if not bag[k]:
                    bag.pop(k)
                holder[k] = m['whoName'] or m['who'] or holder.get(k, '')
            if m['verb'] == 'kill' and m['who']:
                dead.add(m['who'].lower())
            if m['verb'] == 'take':
                for cid in m.get('carriers', []):
                    bag[cid.lower()] = bag.get(cid.lower(), 0) + 1
                    holder[cid.lower()] = 'Player'
            for it in m.get('items', []):
                if m['verb'] in ('show', 'have') and it.lower() not in bag:
                    bag[it.lower()] = 1
                    holder[it.lower()] = 'Player'
        f['state'] = {'bag': [{'id': k, 'n': n, 'name': cast.get(k, {}).get('name', k)} for k, n in sorted(bag.items())],
                      'dead': [cast.get(d, {}).get('name', d) for d in sorted(dead)],
                      'with': {k: v for k, v in holder.items() if v and v != 'Player'}}


def _meta(db, vs):
    """A quest's title, how many stages it has and which finish it, read from its lines' tags only."""
    import struct
    title, fin, n = '', [], 0
    for v in vs:
        for ii in db.dial_infos.get(v, []):
            if not db.winner[ii]:
                continue
            r = db.recs[ii]
            qn = qf = False
            disp, text = 0, ''
            for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
                if t == 'QSTN':
                    qn = True
                elif t == 'QSTF':
                    qf = True
                elif t == 'DATA' and len(d) >= 8:
                    disp = struct.unpack_from('<i', d, 4)[0]
                elif t == 'NAME':
                    text = zstr(d)
            if qn:
                title = text
            else:
                n += 1
                if qf:
                    fin.append(disp)
    return title, n, sorted(fin)


def quests(db, mine=False):
    """Every quest: title, the plugin it comes from, stages, which finish it, how many scripts move it."""
    byq = _scripts_by_quest(db)
    out = []
    for t in dialogue.index(db, kind=4, mine=mine, limit=20000):
        vs = [v for v in db.by_key.get(('DIAL', t['key']), []) if v not in db.dead]
        title, n, fin = _meta(db, vs)
        pidx = db.recs[vs[0]][3] if vs else None
        plug = db.plugins[pidx]['name'] if pidx is not None and pidx < len(db.plugins) else ''
        out.append({'key': t['key'], 'id': t['id'], 'title': title, 'plugin': plug, 'stages': n, 'finished': fin,
                    'mine': t['mine'], 'scripts': len(byq.get(t['key'], []))})
    return out


_FL = {'key': None, 'by': {}}


def flags(db, keys):
    """The Board's two faults per quest (stages nothing leads to, stages nothing leads on from), with what it
    read; kept per game data, a quest of the project's read afresh each time."""
    sig = (id(db.files), len(db.plugins))
    if _FL['key'] != sig:
        _FL.update(key=sig, by={})
    out = {}
    for k in keys:
        k = k.lower()
        vs = db.by_key.get(('DIAL', k), [])
        mine = db.proj_pidx is not None and any(db.recs[v][3] == db.proj_pidx for v in vs)
        if k in _FL['by'] and not mine:
            out[k] = _FL['by'][k]
            continue
        try:
            b = board(db, k)
        except EditError as e:
            out[k] = {'error': str(e)}
            continue
        fr = [f for f in b['frames'] if not f['missing']]
        out[k] = {'stages': len(fr), 'reach': sum(1 for f in fr if f['reachable']), 'moves': len(b['moves']),
                  'cast': len(b['cast']), 'unset': [f['index'] for f in fr if not f['in']],
                  'dead': [f['index'] for f in fr if f['deadend']]}
        if not mine:
            _FL['by'][k] = out[k]
    return out


def survey(db, limit=0):
    """How well the Board reads the quests in the loaded data: per quest, stages, how many are
    reachable, dead ends, the verbs. For the lab."""
    rows = []
    for n, t in enumerate(quests(db)):
        if limit and n >= limit:
            break
        try:
            b = board(db, t['key'])
        except EditError:
            continue
        fr = [f for f in b['frames'] if not f['missing']]
        rows.append({'id': t['id'], 'stages': len(fr), 'reach': sum(1 for f in fr if f['reachable']),
                     'dead': sum(1 for f in fr if f['deadend']), 'moves': len(b['moves']),
                     'lines': sum(1 for m in b['moves'] if m['via'] == 'line'),
                     'scripts': sum(1 for m in b['moves'] if m['via'] == 'script'),
                     'cast': len(b['cast']), 'verbs': b['verbs'],
                     'unset': [f['index'] for f in fr if not f['in']]})
    return rows
