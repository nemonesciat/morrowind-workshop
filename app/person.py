"""A person on the map, all in one card (web/person.js): what they say now and every line of theirs, what they
wear and carry (with the items' own icons), what they trade and teach, where they take travellers, and the
quests they are part of. Lines are written here in plain terms (a greeting, a topic, a rumour; when it applies;
two answers to choose from); jobs (fetch, deliver, find, hunt, meet) are whole quests written through the quest
maker. Every change is one Undo; one that can't be written leaves nothing behind (questmap._one_change)."""
import re
import struct

import dialogue
import editing
import npc
import questmap
from editing import EditError

# ---------------------------------------------------------------- items: icons and where they're worn
_ICONS = {}
# (armour pieces and clothing by the type number in their DATA: where a person wears them)
ARMOR_SLOT = {0: 'head', 1: 'chest', 2: 'shoulder', 3: 'shoulder', 4: 'legs', 5: 'feet', 6: 'hands', 7: 'hands', 8: 'shield', 9: 'hands', 10: 'hands'}
CLOTH_SLOT = {0: 'legs', 1: 'feet', 2: 'shirt', 3: 'belt', 4: 'robe', 5: 'hands', 6: 'hands', 7: 'skirt', 8: 'ring', 9: 'amulet'}


def _subs(db, ri):
    from esm import iter_subrecords
    r = db.recs[ri]
    return [(t, bytes(d)) for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2])]


def item_info(db, rid):
    """{'id', 'name', 'type', 'slot', 'icon'}: what the item is, where it's worn (None when not), its icon path."""
    from esm import zstr
    ri = db.resolve_id(rid)
    if ri is None:
        return {'id': rid, 'name': rid, 'type': '', 'slot': None, 'icon': '', 'missing': True}
    r = db.recs[ri]
    icon, slot = '', None
    for t, d in _subs(db, ri):
        if t == 'ITEX':
            icon = zstr(d)
        elif t in ('AODT', 'CTDT') and len(d) >= 4:
            n = struct.unpack_from('<i', d, 0)[0]
            slot = (ARMOR_SLOT if t == 'AODT' else CLOTH_SLOT).get(n)
    if r[0] == 'WEAP':
        slot = 'weapon'
    return {'id': r[1], 'name': r[2] or r[1], 'type': r[0], 'slot': slot, 'icon': icon}


def icon_png(db, rid):
    """An item's icon as a PNG (the game's .dds or .tga icon, decoded), or None."""
    key = (rid or '').lower()
    if key in _ICONS:
        return _ICONS[key]
    import assets
    info = item_info(db, rid)
    out = None
    p = (info.get('icon') or '').replace('\\', '/').lower()
    if p:
        base = 'icons/' + re.sub(r'\.(tga|bmp)$', '', p)
        for path in (base + '.dds', base + '.tga', 'icons/' + p):
            raw = db.meshes.read(path)
            if raw:
                dec = assets._decode(raw, 32)
                if dec:
                    out = assets._png(dec[0], dec[1], dec[2])
                    break
    _ICONS[key] = out
    return out


# ---------------------------------------------------------------- the card
def card(db, npc_id):
    """Everything the person card shows."""
    o = npc.read(db, npc_id)
    for it in o['items']:
        it.update({k: v for k, v in item_info(db, it['id']).items() if k != 'id'})
    places = npc.placements(db, o['id'])
    says, topics = '', []
    try:
        import convo
        t = convo.say(db, o['id'], {})
        for tp in t.get('topics') or []:
            s = tp.get('said') or {}
            if tp.get('key') == 'greeting':
                says = s.get('text') or ''
            elif s.get('text'):
                topics.append({'topic': tp.get('id') or tp.get('key'), 'text': s['text']})
    except Exception as e:
        print('person card: what they say:', e)
    lines, quests = [], []
    try:
        ch = dialogue.character(db, o['id'])
        qkeys = set()
        for tp in ch['topics']:
            kind = 'greeting' if tp['type'] == 2 else 'rumour' if tp['key'] in RUMOUR_TOPICS else 'topic' if tp['type'] == 0 else None
            for ln in tp['lines']:
                if (ln.get('actor') or '').lower() != o['id'].lower():
                    continue                         # (their own lines: the ones written for them by name)
                qkeys |= {c['name'].lower() for c in ln.get('conds') or [] if c.get('kind') == 'journal'}
                if kind:
                    lines.append({'kind': kind, 'topic': tp['id'], 'tkey': tp['key'], 'inam': ln['inam'], 'text': ln['text'],
                                  'mine': ln.get('mine', False), 'when': plain_conds(ln.get('conds') or [])})
        for k in sorted(qkeys):
            try:
                q = dialogue.quest(db, k)
                quests.append({'key': q['key'], 'id': q['id'], 'title': q['title'] or q['id']})
            except Exception:
                pass
    except Exception as e:
        print('person card: lines:', e)
    o.update({'places': places, 'copies': len(places), 'says': says, 'answers': topics[:12], 'lines': lines, 'quests': quests})
    return o


def save(db, npc_id, change):
    """Part of a person changed (items, services, gold, travel, auto): through the character editor's own save,
    as one Undo."""
    o = npc.read(db, npc_id)
    was_auto = o.get('auto')
    for k in ('items', 'services', 'gold', 'travel', 'auto', 'spells'):
        if k in change:
            o[k] = change[k]
    if was_auto and not o.get('auto') and not o.get('attributes'):
        # (stats worked out no longer: they keep the ones the game worked out, as the character page does, so
        #  the services ticked here are theirs)
        c = npc.autocalc(db, o.get('race'), o.get('cls'), o.get('level') or 1, o.get('female'))
        if c:
            o.update({k: (list(c[k]) if isinstance(c[k], (list, tuple)) else c[k]) for k in ('attributes', 'skills', 'health', 'magicka', 'fatigue')})
    o['items'] = [{'id': it['id'], 'count': int(it.get('count') or 1), 'restock': bool(it.get('restock'))} for it in o['items']]
    npc.save(db, npc_id, o)
    return card(db, npc_id)


# ---------------------------------------------------------------- lines in plain terms
RUMOUR_TOPICS = ('latest rumors', 'little secret', 'little advice')
GREETING = 'greeting 5'


def plain_conds(conds):
    """A line's conditions in a few words, for the card."""
    out = []
    for c in conds:
        k = c.get('kind')
        if k == 'journal':
            out.append('%s %s %s' % (c['name'], c['op'], c['value']))
        elif k == 'item':
            out.append('carries %s' % c['name'])
        elif k == 'global' and c['name'].lower() == 'gamehour':
            out.append('hour %s %s' % (c['op'], c['value']))
        elif k == 'global':
            out.append('once' if re.search(r'_said\d*$', c['name'], re.I) else '%s %s %s' % (c['name'], c['op'], c['value']))
        elif k == 'function' and 'choice' in str(c.get('func', '')).lower():
            out.append('answer %s' % c['value'])
    return ', '.join(out)


def _choice_func(db):
    try:
        return dialogue.options(db).get('choice')
    except Exception:
        return None


def _known_topics(db, topic):
    """A topic of the mod's own, known to the player from the start: one start script of the mod lists them, so
    the player can ask about it (Morrowind lists only topics the player knows)."""
    import mwscript
    from project import join_subs, zs
    p = db.project
    sid = re.sub(r'[^A-Za-z0-9_]', '_', 'ws_%s_topics' % p.lua_slug()[:20])[:31]
    have = mwscript.read(db, sid)['text'].replace('\r\n', '\n') if mwscript._winner(db, sid) is not None else None
    t = topic.replace('"', '').strip()
    if have is not None and re.search(r'(?im)^\s*AddTopic "%s"\s*$' % re.escape(t), have):
        return
    if have is None:
        text = ('begin %s\n\n; the topics of this mod the player knows from the start (made by the person card)\n'
                'short done\n\nif ( done == 0 )\n\tAddTopic "%s"\n\tset done to 1\nendif\n\nend\n' % (sid, t))
        mwscript.save(db, sid, text, create=True, save=False)
        mwscript.attach(db, sid, '*start*')
    else:
        text = re.sub(r'(?m)^(\tset done to 1)$', '\tAddTopic "%s"\n\\1' % t.replace('\\', ''), have, count=1)
        # (a game already under way has run it: a new topic goes in a second block too)
        text = re.sub(r'(?im)^\s*end\s*$', 'if ( done == 1 )\n\tAddTopic "%s"\nendif\n\nend' % t, text, count=1)
        mwscript.save(db, sid, text, create=False, save=False)
        editing.commit(db, 'The player knows the topic "%s"' % t)


def _once_global(db, npc_id):
    """A global of the mod's own that marks a line as said (for a line said once)."""
    from project import join_subs, zs
    base = re.sub(r'[^A-Za-z0-9_]', '_', 'ws_%s_said' % npc_id[:12])[:27]
    n = 1
    while db.resolve_id('%s%d' % (base, n)) is not None:
        n += 1
    gid = '%s%d' % (base, n)
    db.project.set_record('GLOB', gid.lower(), 0, join_subs([('NAME', zs(gid)), ('FNAM', b's'), ('FLTV', struct.pack('<f', 0.0))]), created=True)
    db.sync_project()
    editing.commit(db, 'A marker for a line of %s said once' % npc_id)
    return gid


def say_line(db, body):
    """A line for a person, in plain terms. body: {'who', 'kind': 'greeting'|'topic'|'rumour', 'topic' (for a
    topic), 'text', 'when': {'once': bool, 'quest': id, 'op': '>='|'<'|'=', 'stage': n, 'carries': item id,
    'from_hour': h, 'to_hour': h}, 'answers': [{'label', 'text', 'stage': n, 'quest': id, 'give': item id,
    'bye': bool}] (two choices for the player)}. One Undo."""
    who = (body.get('who') or '').strip()
    if db.resolve_id(who) is None:
        raise EditError('Nothing has the ID "%s".' % who)
    kind = body.get('kind') or 'topic'
    text = (body.get('text') or '').strip()
    if not text:
        raise EditError('Write what they say.')
    when = body.get('when') or {}
    answers = [a for a in (body.get('answers') or []) if (a.get('label') or '').strip()]
    if answers and len(answers) < 2:
        raise EditError('Give the player two answers, or none.')

    def work():
        if kind == 'greeting':
            tkey = GREETING
        elif kind == 'rumour':
            tkey = 'latest rumors'
        else:
            topic = (body.get('topic') or '').strip()
            if not topic:
                raise EditError('Name the topic the player asks about.')
            tkey = topic.lower()
            if not dialogue._dial_versions(db, tkey):
                dialogue.create_topic(db, topic, 0)
            if not tkey.startswith('greeting') and tkey not in RUMOUR_TOPICS:
                _known_topics(db, topic)
        conds, res = [], []
        if when.get('quest') and when.get('stage') not in (None, ''):
            conds.append({'kind': 'journal', 'code': '00', 'op': when.get('op') or '>=', 'name': when['quest'], 'value': int(when['stage']), 'float': False})
        if when.get('carries'):
            if db.resolve_id(when['carries']) is None:
                raise EditError('Nothing has the ID "%s".' % when['carries'])
            conds.append({'kind': 'item', 'code': '00', 'op': '>=', 'name': when['carries'], 'value': 1, 'float': False})
        if when.get('from_hour') not in (None, ''):
            conds.append({'kind': 'global', 'code': '00', 'op': '>=', 'name': 'GameHour', 'value': float(when['from_hour']), 'float': True})
        if when.get('to_hour') not in (None, ''):
            conds.append({'kind': 'global', 'code': '00', 'op': '<', 'name': 'GameHour', 'value': float(when['to_hour']), 'float': True})
        if when.get('once'):
            g = _once_global(db, who)
            conds.append({'kind': 'global', 'code': '00', 'op': '=', 'name': g, 'value': 0, 'float': False})
            res.append('set %s to 1' % g)
        choice = _choice_func(db) if answers else None
        if answers:
            res.append('Choice ' + ' '.join('"%s" %d' % (a['label'].replace('"', "'").strip(), n + 1) for n, a in enumerate(answers)))
        line = {'actor': who, 'text': text, 'result': '\n'.join(res), 'conds': conds, 'disp': 0, 'rank': -1, 'sex': -1, 'pcrank': -1}
        inam = dialogue.save_line(db, tkey, line, {'top': True})
        # (each answer: a line of theirs that follows the player's choice, above the line that asks)
        for n, a in reversed(list(enumerate(answers))):
            ar = []
            if a.get('quest') and a.get('stage') not in (None, ''):
                ar.append('Journal "%s" %d' % (a['quest'], int(a['stage'])))
            if a.get('give'):
                ar.append('player->AddItem "%s" %d' % (a['give'], max(1, int(a.get('count') or 1))))
            if a.get('bye'):
                ar.append('Goodbye')
            dialogue.save_line(db, tkey, {'actor': who, 'text': (a.get('text') or '…').strip(), 'result': '\n'.join(ar),
                                          'conds': conds + [{'kind': 'function', 'func': choice, 'op': '=', 'value': n + 1}] if choice else conds,
                                          'disp': 0, 'rank': -1, 'sex': -1, 'pcrank': -1}, {'before': inam})
        return {'topic': tkey, 'inam': inam}
    return questmap._one_change(db, 'A %s for %s' % ({'greeting': 'greeting', 'rumour': 'rumour'}.get(kind, 'line'), who), work)


def remove_line(db, tkey, inam):
    return questmap._one_change(db, 'Took a line out', lambda: dialogue.delete_line(db, tkey, inam))


# ---------------------------------------------------------------- jobs: a whole quest from a person, in a few answers
JOBS = ('fetch', 'deliver', 'find', 'hunt', 'meet')


def job(db, body):
    """A quest from a person in two or three answers, written as the quest maker writes it, one Undo.
    body: {'kind', 'giver', 'title', 'item', 'count', 'to' (a person: deliver, meet), 'target' (hunt), 'spot':
    {cell, pos} (find), 'reward', 'reward_count', 'topic'}."""
    kind = body.get('kind')
    if kind not in JOBS:
        raise EditError('Pick the kind of job.')
    giver = (body.get('giver') or '').strip()
    title = (body.get('title') or '').strip()
    if not title:
        raise EditError('Give the job a title.')
    if db.resolve_id(giver) is None:
        raise EditError('Nothing has the ID "%s".' % giver)
    topic = (body.get('topic') or title).strip().lower()[:30]
    item, n = (body.get('item') or '').strip(), max(1, int(body.get('count') or 1))
    reward = [{'id': body['reward'], 'n': max(1, int(body.get('reward_count') or 1))}] if body.get('reward') else []
    gname = (db.recs[db.resolve_id(giver)][2] or giver)
    stack = getattr(db.project, 'undo_stack', [])

    def step(st, **kw):
        return questmap._step(db, dict(st, **kw), stack, len(stack))

    def work():
        if kind in ('fetch', 'deliver', 'find') and not item:
            raise EditError('Say which item.')
        if kind in ('deliver', 'meet') and db.resolve_id(body.get('to') or '') is None:
            raise EditError('Say who to (right-click them, or type their ID).')
        if kind == 'hunt' and db.resolve_id(body.get('target') or '') is None:
            raise EditError('Say who or what to hunt.')
        iname = (db.recs[db.resolve_id(item)][2] if item and db.resolve_id(item) is not None else item) or item
        if kind == 'fetch':
            r = step({'new': {'title': title}, 'text': '%s wants %s%s.' % (gname, '%d ' % n if n > 1 else '', iname),
                      'move': {'verb': 'talk', 'who': giver, 'topic': topic, 'say': body.get('ask') or 'Bring me %s, and you won\'t regret it.' % iname}})
            step({'key': r['key'], 'text': 'I brought %s to %s.' % (iname, gname), 'finished': True,
                  'move': {'verb': 'bring', 'who': giver, 'topic': topic, 'items': [{'id': item, 'n': n}], 'gives': reward, 'say': 'Just what I needed. Thank you.'}})
        elif kind == 'deliver':
            to = body['to']
            tname = db.recs[db.resolve_id(to)][2] or to
            r = step({'new': {'title': title}, 'text': '%s asked me to take %s to %s.' % (gname, iname, tname),
                      'move': {'verb': 'talk', 'who': giver, 'topic': topic, 'gives': [{'id': item, 'n': n}],
                               'say': body.get('ask') or 'Take this to %s. Quickly, and quietly.' % tname}})
            step({'key': r['key'], 'text': 'I gave %s to %s.' % (iname, tname), 'finished': True,
                  'move': {'verb': 'bring', 'who': to, 'topic': topic, 'items': [{'id': item, 'n': n}], 'gives': reward, 'say': 'From %s? Good. Here, for your trouble.' % gname}})
        elif kind == 'find':
            sp = body.get('spot') or {}
            if not (sp.get('cell') and sp.get('pos')):
                raise EditError('Pick where it lies: right-click the ground there.')
            r = step({'new': {'title': title}, 'text': '%s lost %s and asked me to find it.' % (gname, iname),
                      'move': {'verb': 'talk', 'who': giver, 'topic': topic, 'say': body.get('ask') or 'I lost %s. Find it for me?' % iname}})
            r2 = step({'key': r['key'], 'text': 'I found %s.' % iname, 'move': {'verb': 'take'}, 'place': {'id': item, 'cell': sp['cell'], 'pos': sp['pos']}})
            copy = (r2.get('move') or {}).get('thing')
            m = questmap.overview(db, r['key'])
            copy = copy or next((p['id'] for s in m['steps'] if s['verb'] == 'take' for p in s['pins']), item)
            step({'key': r['key'], 'text': 'I gave %s back to %s.' % (iname, gname), 'finished': True,
                  'move': {'verb': 'bring', 'who': giver, 'topic': topic, 'items': [{'id': copy, 'n': 1}], 'gives': reward, 'say': 'You found it! Thank you.'}})
        elif kind == 'hunt':
            tg = body['target']
            tname = db.recs[db.resolve_id(tg)][2] or tg
            r = step({'new': {'title': title}, 'text': '%s wants %s dead.' % (gname, tname),
                      'move': {'verb': 'talk', 'who': giver, 'topic': topic, 'say': body.get('ask') or 'Deal with %s, and I\'ll make it worth your while.' % tname}})
            step({'key': r['key'], 'text': '%s is dead.' % tname, 'move': {'verb': 'kill', 'who': tg}})
            step({'key': r['key'], 'text': 'I told %s it is done.' % gname, 'finished': True,
                  'move': {'verb': 'talk', 'who': giver, 'topic': topic, 'gives': reward, 'say': 'Good work. Here is what I promised.'}})
        else:
            to = body['to']
            tname = db.recs[db.resolve_id(to)][2] or to
            r = step({'new': {'title': title}, 'text': '%s asked me to see %s.' % (gname, tname),
                      'move': {'verb': 'talk', 'who': giver, 'topic': topic, 'say': body.get('ask') or 'Go and see %s. Tell them I sent you.' % tname}})
            step({'key': r['key'], 'text': 'I met %s.' % tname, 'finished': True,
                  'move': {'verb': 'talk', 'who': to, 'topic': topic, 'gives': reward, 'say': '%s sent you? Then you\'re welcome here.' % gname}})
        return {'key': r['key']}
    return questmap._one_change(db, 'A %s job from %s: "%s"' % (kind, gname, title), work)


# ---------------------------------------------------------------- a container's contents, as icons
def contents(db, cont_id):
    """{'id', 'name', 'i', 'items': [{id, name, count, restock, icon, type}], 'copies'}: what a container holds."""
    from esm import zstr
    ri = db.resolve_id(cont_id)
    if ri is None or db.recs[ri][0] != 'CONT':
        raise EditError('"%s" is not a container.' % cont_id)
    r = db.recs[ri]
    items = []
    for t, d in _subs(db, ri):
        if t == 'NPCO' and len(d) >= 36:
            n = struct.unpack_from('<i', d, 0)[0]
            it = {'id': zstr(d[4:36]), 'count': abs(n), 'restock': n < 0}
            it.update({k: v for k, v in item_info(db, it['id']).items() if k != 'id'})
            items.append(it)
    copies = sum(1 for ci in db.used_in.get(r[1].lower(), ()) if db.recs[ci] is not None and db.recs[ci][0] == 'CELL' and ci not in db.dead)
    return {'id': r[1], 'name': r[2] or r[1], 'i': ri, 'items': items, 'copies': copies}


def save_contents(db, cont_id, items):
    ri = db.resolve_id(cont_id)
    if ri is None:
        raise EditError('Nothing has the ID "%s".' % cont_id)
    items = [{'id': it['id'], 'count': max(1, int(it.get('count') or 1)), 'restock': bool(it.get('restock'))} for it in items if it.get('id')]
    questmap._one_change(db, 'Changed what %s holds' % cont_id, lambda: editing.set_contents(db, ri, items))
    return contents(db, cont_id)
