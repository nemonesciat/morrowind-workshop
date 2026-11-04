"""Making quests on the Board: a stage is a journal entry, a move is what gets the player from one
stage to the next, and each kind of move is written the way the game writes it.

- talk / meet / bring / show: a dialogue line for the person (a topic, or a greeting), that needs the
  stage it starts from (Journal = from), the item for bring and show, and whose result sets the next
  stage, takes the item (bring), hands over the reward, and teaches the topic to ask about next.
- kill / read / open / use / take: a short script on the person or thing (OnDeath, OnActivate,
  OnPCAdd) that sets the stage once; the thing's own script, if it has one, is left alone (refused).
- enter / wait / approach: a block in the quest's own watcher script (started with the game) that
  looks every frame while the quest stands at the stage it starts from.

Every move is one change in My mod (editing.operation 'quest'), so Undo takes the whole of it back."""
import re

import dialogue
import editing
import mwscript
from editing import EditError

VERBS = ('talk', 'meet', 'bring', 'show', 'kill', 'read', 'open', 'use', 'take', 'enter', 'wait', 'approach')
LINE_VERBS = ('talk', 'meet', 'bring', 'show')
THING_VERBS = {'read': 'OnActivate', 'open': 'OnActivate', 'use': 'OnActivate', 'take': 'OnPCAdd'}
WATCH_VERBS = ('kill', 'enter', 'wait', 'approach')       # (kill through the watcher's dead count: no script on the victim)
GREETING = 'greeting 5'                       # (the game's quest greetings go here, over the lore greetings below)


def _sid(db, base):
    """A script ID of our own: letters, digits and _, ≤ 31, not taken."""
    base = re.sub(r'[^A-Za-z0-9_]+', '_', base).strip('_')[:28] or 'quest'
    if base[0].isdigit():
        base = 'q_' + base
    sid, n = base, 1
    while mwscript._winner(db, sid) is not None:
        n += 1
        sid = '%s_%d' % (base[:26], n)
    return sid


def _has_script(db, rid):
    ri = db.resolve_id(rid)
    if ri is None:
        raise EditError('Nothing has the ID "%s".' % rid)
    from esm import iter_subrecords, zstr
    r = db.recs[ri]
    for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
        if t == 'SCRI':
            return zstr(d)
    return ''


def _stage_cond(qid, frm):
    """The stage test a line starts from: the game's idiom is the exact stage (= 0 before the quest begins)."""
    return {'kind': 'journal', 'code': '00', 'op': '=', 'name': qid, 'value': int(frm or 0), 'float': False}


def _item_cond(iid, n):
    return {'kind': 'item', 'code': '00', 'op': '>=', 'name': iid, 'value': max(1, int(n or 1)), 'float': False}


def _line(db, q, mv):
    """One dialogue line, written and put at the top of its topic."""
    who = (mv.get('who') or '').strip()
    if not who:
        raise EditError('Say who the player talks to.')
    if db.resolve_id(who) is None:
        raise EditError('Nothing has the ID "%s".' % who)
    verb = mv['verb']
    if verb == 'meet':
        tkey = GREETING
    else:
        topic = (mv.get('topic') or '').strip()
        if not topic:
            raise EditError('Name the topic the player asks about.')
        tkey = topic.lower()
        if not dialogue._dial_versions(db, tkey):
            dialogue.create_topic(db, topic, 0)
    conds = [_stage_cond(q['id'], mv.get('from'))]
    res = ['Journal "%s" %d' % (q['id'], int(mv['to']))]
    items = [it for it in (mv.get('items') or []) if it.get('id')]
    if verb in ('bring', 'show'):
        if not items:
            raise EditError('Say which item the player %s.' % ('brings' if verb == 'bring' else 'shows'))
        for it in items:
            conds.append(_item_cond(it['id'], it.get('n', 1)))
        if verb == 'bring':
            for it in items:
                res.append('player->RemoveItem "%s" %d' % (it['id'], max(1, int(it.get('n') or 1))))
    for g in mv.get('gives') or []:
        if g.get('id'):
            res.append('player->AddItem "%s" %d' % (g['id'], max(1, int(g.get('n') or 1))))
    for t in mv.get('learns') or []:
        if t.strip():
            res.append('AddTopic "%s"' % t.strip())
            if not dialogue._dial_versions(db, t.strip().lower()):
                dialogue.create_topic(db, t.strip(), 0)
    line = {'actor': who, 'text': (mv.get('say') or '').strip(), 'result': '\n'.join(res), 'conds': conds,
            'disp': 0, 'rank': -1, 'sex': -1, 'pcrank': -1}
    inam = dialogue.save_line(db, tkey, line, {'top': True})
    return {'via': 'line', 'topic': tkey, 'inam': inam}


def _thing(db, q, mv):
    """A script on the person or thing: sets the stage once when it dies, is used, or is picked up."""
    verb = mv['verb']
    target = (mv.get('who') or mv.get('thing') or '').strip()
    if not target:
        raise EditError('Say which thing the player %ss.' % verb)
    have = _has_script(db, target)
    if have:
        raise EditError('"%s" already runs the script "%s". Add the stage to that script instead (Scripts), so it keeps doing what it does.' % (target, have))
    ri = db.resolve_id(target)
    tag = db.recs[ri][0]
    if verb == 'kill' and tag not in ('NPC_', 'CREA'):
        raise EditError('"%s" is not a person or creature.' % target)
    if verb == 'take' and tag in ('NPC_', 'CREA', 'DOOR', 'ACTI', 'CONT', 'STAT'):
        raise EditError('"%s" can\'t be picked up.' % target)
    if tag not in mwscript.SCRIPTABLE:
        raise EditError('Scripts can\'t be put on that kind of thing (%s).' % tag)
    sid = _sid(db, '%s_%s_%s' % (q['id'][:12], target[:10], verb))
    ev = THING_VERBS[verb]
    frm = int(mv.get('from') or 0)
    inner = '\t\tJournal "%s" %d\n\t\tset done to 1' % (q['id'], int(mv['to']))
    if frm:
        inner = '\t\tif ( GetJournalIndex "%s" >= %d )\n%s\n\t\tendif' % (q['id'], frm, '\n'.join('\t' + s for s in inner.split('\n')))
    act = '\tActivate\n' if verb in ('read', 'open', 'use') else ''        # (the book still opens, the door still opens)
    text = 'begin %s\n\nshort done\n\nif ( %s == 1 )\n\tif ( done == 0 )\n%s\n\tendif\n%sendif\n\nend\n' % (sid, ev, inner, act)
    mwscript.save(db, sid, text, create=True, save=False)
    mwscript.attach(db, sid, target)
    return {'via': 'script', 'script': sid}


def _watch(db, q, mv):
    """A block in the quest's watcher script, which runs from the start of the game."""
    verb = mv['verb']
    frm = int(mv.get('from') or 0)
    to = int(mv['to'])
    sid = (db.project.quests.get(q['key'], {}) or {}).get('watch')
    if sid and mwscript._winner(db, sid) is None:
        sid = None
    if verb == 'kill':
        who = (mv.get('who') or mv.get('thing') or '').strip()
        if not who or db.resolve_id(who) is None:
            raise EditError('Say who dies.')
        if db.recs[db.resolve_id(who)][0] not in ('NPC_', 'CREA'):
            raise EditError('"%s" is not a person or creature.' % who)
        block = '\tif ( GetDeadCount "%s" > 0 )\n\t\tJournal "%s" %d\n\tendif' % (who, q['id'], to)
    elif verb == 'enter':
        place = (mv.get('place') or '').strip()
        if not place:
            raise EditError('Name the place the player enters (a cell name, or the start of one: "Vivec" for all of Vivec).')
        test = 'GetPCCell "%s" == 1' % place
        block = '\tif ( %s )\n\t\tJournal "%s" %d\n\tendif' % (test, q['id'], to)
    elif verb == 'approach':
        who = (mv.get('who') or mv.get('thing') or '').strip()
        if not who or db.resolve_id(who) is None:
            raise EditError('Say who or what the player comes near.')
        block = '\tif ( "%s"->GetDistance player < %d )\n\t\tJournal "%s" %d\n\tendif' % (who, int(mv.get('dist') or 400), q['id'], to)
    else:
        days = max(1, int(mv.get('days') or 1))
        var = 'w%d' % frm
        block = ('\tif ( %s == 0 )\n\t\tset %s to DaysPassed\n\telseif ( DaysPassed >= ( %s + %d ) )\n\t\tJournal "%s" %d\n\tendif'
                 % (var, var, var, days, q['id'], to))
        block = ('float ' + var, block)
    if sid is None:
        sid = _sid(db, '%s_watch' % q['id'][:20])
        text = 'begin %s\n\n; the quest "%s": what the game watches for while it is under way\n\nend\n' % (sid, q['id'])
        new = True
    else:
        text = mwscript.read(db, sid)['text']
        new = False
    decl = ''
    if isinstance(block, tuple):
        decl, block = block
    guard = '\nif ( GetJournalIndex "%s" == %d )\n%s\nendif\n' % (q['id'], frm, block)
    if decl:
        text = re.sub(r'(?im)^(begin[^\n]*\n)', lambda m: m.group(1) + '\n' + decl + '\n', text, count=1)
    text = re.sub(r'(?im)^\s*end\s*$', lambda m: guard + '\nend', text, count=1) if re.search(r'(?im)^\s*end\s*$', text) else text + guard + '\nend\n'
    mwscript.save(db, sid, text, create=new, save=False)
    if new:
        mwscript.attach(db, sid, '*start*')
    else:
        editing.commit(db, 'Added a stage of "%s" to its watcher script' % q['id'])
    qq = db.project.quests.setdefault(q['key'], {})
    qq['watch'] = sid
    return {'via': 'script', 'script': sid}


def add_move(db, qkey, mv):
    """Write one move of a quest: what the player does to reach a stage, in the game's own records."""
    editing._require_project(db)
    q = dialogue.quest(db, qkey)
    verb = (mv.get('verb') or '').lower()
    if verb not in VERBS:
        raise EditError('Pick what the player does.')
    try:
        to = int(mv.get('to'))
    except (TypeError, ValueError):
        raise EditError('Pick the stage this leads to.')
    if to not in {s['index'] for s in q['stages']}:
        raise EditError('The quest has no stage %d. Add it first.' % to)
    with editing.operation('quest'):
        if verb in LINE_VERBS:
            out = _line(db, q, mv)
        elif verb in THING_VERBS:
            out = _thing(db, q, mv)
        else:
            out = _watch(db, q, mv)
    out['to'] = to
    return out


def add_stage(db, qkey, index, text, finished=False):
    """A new journal entry (stage) of the quest."""
    q = dialogue.quest(db, qkey)
    stages = [{'index': s['index'], 'text': s['text'], 'finished': s['finished'], 'restart': s['restart'], 'inam': s['inam']}
              for s in q['stages']]
    if any(s['index'] == int(index) for s in stages):
        raise EditError('The quest already has a stage %d.' % int(index))
    stages.append({'index': int(index), 'text': text or '', 'finished': bool(finished)})
    dialogue.save_quest(db, q['id'], q['title'], stages)
    return {'index': int(index)}


def new_quest(db, qid, title, first=''):
    """A quest of your own: its ID, its title, and its first entry at stage 10."""
    key = dialogue.save_quest(db, qid, title, [{'index': 10, 'text': first or '', 'finished': False}])
    return {'key': key}


def pin(db, qkey, ids):
    """The cast the user picked for a quest before any move uses them (kept in the project)."""
    editing._require_project(db)
    qq = db.project.quests.setdefault(qkey.lower(), {})
    qq['cast'] = [i for i in ids if i][:60]
    db.project.save()
    return {'cast': qq['cast']}


def pinned(db, qkey):
    if not db.project:
        return []
    return list((db.project.quests.get(qkey.lower(), {}) or {}).get('cast') or [])
