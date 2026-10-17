"""Dialogue and quests: topics, greetings, what each character says, and journal stages.

Morrowind keeps dialogue as topics (DIAL) with lines (INFO) under them. The game uses the
first line, top to bottom, whose conditions all match, so the order matters. Lines from
different plugins are chained together with "previous"/"next" line IDs (PNAM/NNAM)."""
import random
import struct
import time

from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import join_subs, zs

TYPES = ['Topic', 'Voice', 'Greeting', 'Persuasion', 'Journal']
OPS = ['=', '!=', '>', '>=', '<', '<=']
# speaker/player tests used by "Function" conditions, by their number in the game data
FUNCTIONS = ['Faction reaction (lowest)', 'Faction reaction (highest)', 'Rank requirement', 'Reputation',
             'Health %', 'Player reputation', 'Player level', 'Player health %', 'Player magicka',
             'Player fatigue', 'Player strength'] + ['Player ' + s for s in (
    'Block', 'Armorer', 'Medium Armor', 'Heavy Armor', 'Blunt Weapon', 'Long Blade', 'Axe', 'Spear',
    'Athletics', 'Enchant', 'Destruction', 'Alteration', 'Illusion', 'Conjuration', 'Mysticism', 'Restoration',
    'Alchemy', 'Unarmored', 'Security', 'Sneak', 'Acrobatics', 'Light Armor', 'Short Blade', 'Marksman',
    'Mercantile', 'Speechcraft', 'Hand-to-hand')] + [
    'Player sex (0 male, 1 female)', 'Player expelled', 'Player has common disease', 'Player has blight disease',
    'Player clothing value', 'Player crime level', 'Same sex as player', 'Same race as player',
    'Same faction as player', 'Faction rank difference', 'Detected', 'Alarmed', 'Choice',
    'Player intelligence', 'Player willpower', 'Player agility', 'Player speed', 'Player endurance',
    'Player personality', 'Player luck', 'Player has corprus', 'Weather', 'Player is a vampire', 'Level',
    'Attacked', 'Talked to player before', 'Player health', 'Creature target', 'Friend hit', 'Fight', 'Hello',
    'Alarm', 'Flee', 'Should attack', 'Werewolf', 'Player werewolf kills']
CHOICE = FUNCTIONS.index('Choice')
# condition kinds: SCVR type character -> (kind, function code(s))
KINDS = {'1': 'function', '2': 'global', '3': 'local', '4': 'journal', '5': 'item', '6': 'dead',
         '7': 'not_id', '8': 'not_faction', '9': 'not_class', 'A': 'not_race', 'B': 'not_cell', 'C': 'not_local'}
KIND_CHAR = {v: k for k, v in KINDS.items()}
KIND_CODE = {'journal': 'JX', 'item': 'IX', 'dead': 'DX', 'not_id': 'XX', 'not_faction': 'FX',
             'not_class': 'CX', 'not_race': 'RX', 'not_cell': 'LX'}
SPEAKER_FIELDS = [('actor', 'ONAM'), ('race', 'RNAM'), ('cls', 'CNAM'), ('faction', 'FNAM'), ('cell', 'ANAM'),
                  ('pcfaction', 'DNAM'), ('sound', 'SNAM')]


# ---------------------------------------------------------------- reading and writing lines
def parse_info(data):
    d = {'inam': '', 'prev': '', 'next': '', 'type': 0, 'disp': 0, 'rank': -1, 'sex': -1, 'pcrank': -1,
         'unk': 0, 'text': '', 'result': '', 'conds': [], 'qname': False, 'qfinish': False, 'qrestart': False,
         'deleted': False}
    for f, _t in SPEAKER_FIELDS:
        d[f] = ''
    tags = {t: f for f, t in SPEAKER_FIELDS}
    cond = None
    for st, sd in iter_subrecords(data):
        sd = bytes(sd)
        if st == 'INAM':
            d['inam'] = zstr(sd)
        elif st == 'PNAM':
            d['prev'] = zstr(sd)
        elif st == 'NNAM':
            d['next'] = zstr(sd)
        elif st == 'DATA' and len(sd) >= 12:
            d['type'], d['disp'], d['rank'], d['sex'], d['pcrank'], d['unk'] = struct.unpack_from('<B3xibbbb', sd)
        elif st in tags:
            d[tags[st]] = zstr(sd)
        elif st == 'NAME':
            d['text'] = zstr(sd).replace('\r\n', '\n')
        elif st == 'BNAM':
            d['result'] = zstr(sd).replace('\r\n', '\n')
        elif st == 'SCVR' and len(sd) >= 5:
            s = sd.decode(ENC, 'replace')
            kind = KINDS.get(s[1], 'other')
            cond = {'kind': kind, 'code': s[2:4], 'op': OPS[int(s[4])] if s[4].isdigit() and int(s[4]) < 6 else '=',
                    'name': zstr(sd[5:]), 'value': 0, 'float': False}
            if kind == 'function':
                cond['func'] = int(s[2:4]) if s[2:4].isdigit() else -1
            d['conds'].append(cond)
        elif st in ('INTV', 'FLTV') and cond is not None and len(sd) >= 4:
            cond['value'] = struct.unpack_from('<i' if st == 'INTV' else '<f', sd)[0]
            cond['float'] = st == 'FLTV'
            cond = None
        elif st == 'QSTN':
            d['qname'] = True
        elif st == 'QSTF':
            d['qfinish'] = True
        elif st == 'QSTR':
            d['qrestart'] = True
        elif st == 'DELE':
            d['deleted'] = True
    return d


def _scvr(n, c, db=None):
    kind = c.get('kind', 'function')
    ch = KIND_CHAR.get(kind)
    if ch is None:
        raise EditError('Unknown kind of condition: %s' % kind)
    op = OPS.index(c.get('op', '='))
    name = (c.get('name') or '').strip()
    if kind == 'function':
        code, name = '%02d' % int(c.get('func', 0)), ''
    elif kind in ('global', 'local', 'not_local'):
        code = c.get('code') or 'sX'
        if kind == 'global' and db is not None:
            code = _global_code(db, name) or code
    else:
        code = KIND_CODE[kind]
    if kind != 'function' and not name:
        raise EditError('A condition is missing what it checks (a quest, item, name...).')
    return ('%d%s%s%d' % (n, ch, code, op)).encode('ascii') + name.encode(ENC, 'replace')


def _global_code(db, name):
    ri = db.resolve_id(name) if name else None
    if ri is None or db.recs[ri][0] != 'GLOB':
        return None
    r = db.recs[ri]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    for st, sd in iter_subrecords(data):
        if st == 'FNAM' and sd:
            return {'s': 'sX', 'l': 'lX', 'f': 'fX'}.get(chr(sd[0]), 'sX')
    return 'sX'


def build_info(d, db=None):
    subs = [('INAM', zs(d['inam'])), ('PNAM', zs(d.get('prev', ''))), ('NNAM', zs(d.get('next', ''))),
            ('DATA', struct.pack('<B3xibbbb', int(d.get('type', 0)), int(d.get('disp', 0)), int(d.get('rank', -1)),
                                 int(d.get('sex', -1)), int(d.get('pcrank', -1)), int(d.get('unk', 0))))]
    for f, t in SPEAKER_FIELDS:
        v = (d.get(f) or '').strip()
        if v:
            subs.append((t, zs(v)))
    if d.get('deleted'):
        subs.append(('DELE', b'\0\0\0\0'))
        return join_subs(subs)
    text = (d.get('text') or '').replace('\r\n', '\n').replace('\n', '\r\n')
    if len(text.encode(ENC, 'replace')) > 1023:
        raise EditError('A line can be at most 1023 characters long. Split it into two lines.')
    subs.append(('NAME', text.encode(ENC, 'replace')))
    conds = d.get('conds') or []
    if len(conds) > 6:
        raise EditError('A line can have at most 6 conditions.')
    for n, c in enumerate(conds):
        subs.append(('SCVR', _scvr(n, c, db)))
        is_float = c.get('float') or (c.get('kind') in ('global', 'local', 'not_local') and (c.get('code') == 'fX' or
                                       (db is not None and _global_code(db, c.get('name', '')) == 'fX')))
        try:
            v = float(c.get('value') or 0)
        except (TypeError, ValueError):
            raise EditError('"%s" is not a number.' % c.get('value'))
        subs.append(('FLTV', struct.pack('<f', v)) if is_float else ('INTV', struct.pack('<i', int(round(v)))))
    res = (d.get('result') or '').strip().replace('\r\n', '\n').replace('\n', '\r\n')
    if res:
        subs.append(('BNAM', res.encode(ENC, 'replace')))
    if d.get('qname'):
        subs.append(('QSTN', b'\x01'))
    if d.get('qfinish'):
        subs.append(('QSTF', b'\x01'))
    if d.get('qrestart'):
        subs.append(('QSTR', b'\x01'))
    return join_subs(subs)


def _new_inam(db, dkey):
    while True:
        cand = '%d%d' % (int(time.time() * 1000) % 10 ** 12, random.randrange(10 ** 6, 10 ** 7))
        if not db.by_key.get(('INFO', dkey + '|' + cand)):
            return cand


# ---------------------------------------------------------------- topics
def _dial_versions(db, dkey):
    return [v for v in db.by_key.get(('DIAL', dkey), []) if v not in db.dead]


def _dial_type(db, v):
    r = db.recs[v]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    for st, sd in iter_subrecords(data):
        if st == 'DATA' and sd:
            return sd[0]
    return 0


def ordered_lines(db, dkey):
    """Every line of a topic in the order the game checks them: [(rec index, parsed line)]."""
    # a linked list: line id -> [value, previous id, next id]
    nodes, ends = {}, [None, None]          # ends = [first id, last id]

    def unlink(k):
        _v, p, n = nodes.pop(k)
        if p is None:
            ends[0] = n
        else:
            nodes[p][2] = n
        if n is None:
            ends[1] = p
        else:
            nodes[n][1] = p

    def insert_after(k, val, p):
        n = ends[0] if p is None else nodes[p][2]
        nodes[k] = [val, p, n]
        if p is None:
            ends[0] = k
        else:
            nodes[p][2] = k
        if n is None:
            ends[1] = k
        else:
            nodes[n][1] = k

    for v in _dial_versions(db, dkey):
        pending = []
        for ii in db.dial_infos.get(v, []):
            if ii in db.dead:
                continue
            r = db.recs[ii]
            _t, _f, data = db.files[r[3]].record_at(r[4])
            pending.append((ii, parse_info(data)))
        # each line goes after its "previous line"; a plugin's own chain may come in any order
        while pending:
            rest = []
            for ii, d in pending:
                k = d['inam']
                if k in nodes:
                    if d['deleted']:
                        unlink(k)
                    elif d['prev'] != nodes[k][0][1]['prev'] and (not d['prev'] or d['prev'] in nodes) and d['prev'] != k:
                        unlink(k)                   # moved by a later plugin
                        insert_after(k, (ii, d), d['prev'] or None)
                    else:
                        nodes[k][0] = (ii, d)
                elif d['deleted']:
                    continue
                elif not d['prev']:
                    insert_after(k, (ii, d), None)
                elif d['prev'] in nodes:
                    insert_after(k, (ii, d), d['prev'])
                else:
                    rest.append((ii, d))
            if len(rest) == len(pending):
                for ii, d in rest:          # previous line not found: the game puts it at the end
                    insert_after(d['inam'], (ii, d), ends[1])
                break
            pending = rest
    order, k = [], ends[0]
    while k is not None:
        order.append(nodes[k][0])
        k = nodes[k][2]
    return order


def _line_out(db, ii, d):
    r = db.recs[ii]
    out = dict(d)
    out['i'] = ii
    out['mine'] = r[3] == db.proj_pidx
    out['src'] = db.plugins[r[3]]['name']
    return out


def topic(db, dkey):
    dkey = dkey.lower()
    vs = _dial_versions(db, dkey)
    if not vs:
        raise EditError('There is no topic called "%s".' % dkey)
    w = vs[-1]
    return {'key': dkey, 'id': db.recs[w][1], 'type': _dial_type(db, w), 'i': w,
            'mine': any(db.recs[v][3] == db.proj_pidx for v in vs) and db.project is not None,
            'created': bool(db.project and (db.project.records.get('DIAL|' + dkey) or {}).get('created')),
            'lines': [_line_out(db, ii, d) for ii, d in ordered_lines(db, dkey)]}


def index(db, q='', kind=None, mine=False, limit=400):
    """Topics, greetings and quests, optionally filtered."""
    q = (q or '').lower().strip()
    out = []
    for (tag, key), lst in db.by_key.items():
        if tag != 'DIAL':
            continue
        vs = [v for v in lst if v not in db.dead]
        if not vs:
            continue
        w = vs[-1]
        is_mine = db.proj_pidx is not None and any(db.recs[v][3] == db.proj_pidx for v in vs)
        if mine and not is_mine:
            continue
        name = db.recs[w][1]
        if q and q not in key:
            continue
        t = _dial_type(db, w)
        if kind is not None and t != kind:
            continue
        n = sum(1 for v in vs for ii in db.dial_infos.get(v, []) if db.winner[ii])
        mine_n = sum(1 for v in vs if db.recs[v][3] == db.proj_pidx for ii in db.dial_infos.get(v, []))
        out.append({'key': key, 'id': name, 'type': t, 'lines': n, 'mine': is_mine, 'mine_lines': mine_n})
    out.sort(key=lambda x: (not x['mine'], x['type'] != 2, x['id'].lower()))
    return out[:limit]


def create_topic(db, name, kind=0):
    _require_project(db)
    name = (name or '').strip()
    if not name:
        raise EditError('Give the topic a name. It is the word players click on, so keep it short.')
    if len(name.encode(ENC, 'replace')) > 31:
        raise EditError('Topic names can be at most 31 characters.')
    key = name.lower()
    if _dial_versions(db, key):
        raise EditError('There is already a topic called "%s".' % name)
    db.project.set_record('DIAL', key, 0, join_subs([('NAME', zs(name)), ('DATA', bytes([int(kind)]))]), created=True)
    commit(db, 'Created %s "%s"' % ('quest' if kind == 4 else TYPES[int(kind)].lower(), name))
    return key


def _ensure_dial(db, dkey):
    if 'DIAL|' + dkey in db.project.records:
        return
    vs = _dial_versions(db, dkey)
    if not vs:
        raise EditError('There is no topic called "%s".' % dkey)
    r = db.recs[vs[-1]]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    db.project.set_record('DIAL', dkey, flags & ~0x20, data)


def _put(db, dkey, d, created):
    db.project.set_record('INFO', dkey + '|' + d['inam'].lower(), 0, build_info(d, db), created=created)


def _relink(db, dkey, order=None):
    """Point each of my lines at the line just above/below it in the wanted order (by default
    the current one). All of them, so no two of my lines claim to follow the same line."""
    lines = {d['inam']: (ii, d) for ii, d in ordered_lines(db, dkey)}
    order = order if order is not None else list(lines)
    for n, inam in enumerate(order):
        rec = db.project.records.get('INFO|' + dkey + '|' + inam.lower())
        if not rec or inam not in lines:
            continue
        d = lines[inam][1]
        prev = order[n - 1] if n > 0 else ''
        nxt = order[n + 1] if n + 1 < len(order) else ''
        if d['prev'] != prev or d['next'] != nxt:
            _put(db, dkey, dict(d, prev=prev, next=nxt), rec.get('created'))
    db.sync_project()


def save_line(db, dkey, line, where=None):
    """Add or change a line. where: {'before': inam} | {'after': inam} | {'top': True} (new lines only)."""
    _require_project(db)
    dkey = dkey.lower()
    vs = _dial_versions(db, dkey)
    if not vs:
        raise EditError('There is no topic called "%s".' % dkey)
    _ensure_dial(db, dkey)
    db.sync_project()
    t = _dial_type(db, vs[-1])
    lines = ordered_lines(db, dkey)
    d = {k: line.get(k, v) for k, v in parse_info(b'').items()}
    for f, _t in SPEAKER_FIELDS:
        d[f] = line.get(f, '') or ''
    d['type'] = t
    old = next(((ii, x) for ii, x in lines if line.get('inam') and x['inam'] == line['inam']), None)
    if old:
        d['inam'], d['prev'], d['next'] = old[1]['inam'], old[1]['prev'], old[1]['next']
        rec = db.project.records.get('INFO|' + dkey + '|' + d['inam'].lower())
        created = bool(rec and rec.get('created'))
        verb = 'Changed'
    else:
        d['inam'] = _new_inam(db, dkey)
        where = where or {'top': True}
        ids = [x['inam'] for _i, x in lines]
        if where.get('after') in ids:
            at = ids.index(where['after']) + 1
        elif where.get('before') in ids:
            at = ids.index(where['before'])
        elif where.get('bottom'):
            at = len(ids)
        else:
            at = 0
        d['prev'] = ids[at - 1] if at > 0 else ''
        d['next'] = ids[at] if at < len(ids) else ''
        created = True
        verb = 'Added'
        ids.insert(at, d['inam'])
    _put(db, dkey, d, created)
    db.sync_project()
    _relink(db, dkey, None if old else ids)
    what = 'journal entry' if t == 4 else 'greeting' if t == 2 else 'line'
    who = (' for ' + d['actor']) if d.get('actor') else ''
    commit(db, '%s a %s in "%s"%s' % (verb, what, db.recs[vs[-1]][1], who))
    return d['inam']


def delete_line(db, dkey, inam):
    _require_project(db)
    dkey = dkey.lower()
    k = 'INFO|' + dkey + '|' + inam.lower()
    rec = db.project.records.get(k)
    if not rec:
        raise EditError('Only lines from your mod can be removed here.')
    ids = [x['inam'] for _i, x in ordered_lines(db, dkey) if x['inam'].lower() != inam.lower()]
    db.project.records.pop(k)
    db.sync_project()
    _relink(db, dkey, ids)
    _maybe_drop_dial(db, dkey)
    commit(db, 'Removed a line from "%s"' % dkey)


def _maybe_drop_dial(db, dkey):
    d = db.project.records.get('DIAL|' + dkey)
    if d and not d.get('created') and not any(k.startswith('INFO|' + dkey + '|') for k in db.project.records):
        db.project.records.pop('DIAL|' + dkey)


def move_line(db, dkey, inam, step):
    """Move one of my lines up (-1) or down (+1); the game uses the first line that fits."""
    _require_project(db)
    dkey = dkey.lower()
    lines = ordered_lines(db, dkey)
    ids = [x['inam'] for _i, x in lines]
    if inam not in ids:
        raise EditError('That line is not in this topic.')
    n = ids.index(inam)
    ii, d = lines[n]
    if db.recs[ii][3] != db.proj_pidx:
        raise EditError('Only lines from your mod can be moved.')
    m = max(0, min(len(ids) - 1, n + (1 if step > 0 else -1)))
    if m == n:
        return
    rest = [x for x in ids if x != inam]
    rest.insert(m, inam)
    _relink(db, dkey, rest)
    commit(db, 'Moved a line %s in "%s"' % ('up' if step < 0 else 'down', dkey))


# ---------------------------------------------------------------- characters
def character(db, npc_id):
    """Everything a character says: lines written just for them, by topic."""
    ri = db.resolve_id(npc_id)
    if ri is None or db.recs[ri][0] not in ('NPC_', 'CREA'):
        raise EditError('No character called "%s".' % npc_id)
    r = db.recs[ri]
    info = {'id': r[1], 'name': r[2], 'type': r[0], 'i': ri}
    if r[0] == 'NPC_':
        _t, _f, data = db.files[r[3]].record_at(r[4])
        for st, sd in iter_subrecords(data):
            if st == 'RNAM':
                info['race'] = zstr(sd)
            elif st == 'CNAM':
                info['cls'] = zstr(sd)
            elif st == 'ANAM':
                info['faction'] = zstr(sd)
    low = r[1].lower()
    dials = {}
    for ii, rr in enumerate(db.recs):
        if rr is None or rr[0] != 'INFO' or not db.winner[ii] or ii in db.dead:
            continue
        ex = rr[5].lower()
        if not ex.endswith(' ' + low):
            continue
        d = db.info_dial.get(ii)
        if d is None or ex != (db.recs[d][1] + ' ' + r[1]).lower():
            continue
        dials[db.recs[d][7]] = db.recs[d]
    topics = []
    for dkey in sorted(dials):
        t = topic(db, dkey)
        t['lines'] = [x for x in t['lines'] if x['actor'].lower() == low]
        if t['lines']:
            topics.append(t)
    topics.sort(key=lambda t: (t['type'] != 2, t['type'] != 0, t['id'].lower()))
    info['topics'] = topics
    return info


# ---------------------------------------------------------------- quests
def quest(db, qkey):
    t = topic(db, qkey)
    if t['type'] != 4:
        raise EditError('"%s" is not a quest.' % t['id'])
    title, stages = '', []
    for ln in t['lines']:
        if ln['qname']:
            title = ln['text']
        else:
            stages.append({'index': ln['disp'], 'text': ln['text'], 'finished': ln['qfinish'],
                           'restart': ln['qrestart'], 'inam': ln['inam'], 'mine': ln['mine'], 'src': ln['src']})
    stages.sort(key=lambda s: s['index'])
    return {'key': t['key'], 'id': t['id'], 'title': title, 'stages': stages, 'mine': t['mine'],
            'created': t['created']}


def save_quest(db, qid, title, stages):
    """Create or update a quest: its title (shown in the journal) and numbered stages."""
    _require_project(db)
    qid = (qid or '').strip()
    if not qid:
        raise EditError('Give the quest an ID (players never see it), e.g. "MyMod_LostRing".')
    if len(qid.encode(ENC, 'replace')) > 31:
        raise EditError('Quest IDs can be at most 31 characters.')
    key = qid.lower()
    vs = _dial_versions(db, key)
    created_now = False
    if vs:
        if _dial_type(db, vs[-1]) != 4:
            raise EditError('"%s" is already used by a topic that is not a quest.' % qid)
    else:
        db.project.set_record('DIAL', key, 0, join_subs([('NAME', zs(qid)), ('DATA', bytes([4]))]), created=True)
        created_now = True
    _ensure_dial(db, key)
    db.sync_project()
    seen = set()
    for s in stages:
        try:
            s['index'] = int(s['index'])
        except (TypeError, ValueError, KeyError):
            raise EditError('Each stage needs a number, like 10, 20, 100.')
        if s['index'] in seen:
            raise EditError('Two stages have the number %d.' % s['index'])
        seen.add(s['index'])
    cur = {ln[1]['inam']: (ln[0], ln[1]) for ln in ordered_lines(db, key)}
    keep = set()
    entries = [{'qname': True, 'disp': 0, 'text': (title or '').strip() or qid}] + \
        [{'disp': s['index'], 'text': s.get('text', ''), 'qfinish': bool(s.get('finished')),
          'qrestart': bool(s.get('restart')), 'inam': s.get('inam')} for s in sorted(stages, key=lambda s: s['index'])]
    title_line = next((d for _i, d in cur.values() if d['qname']), None)
    if title_line:
        entries[0]['inam'] = title_line['inam']
    order = []
    for e in entries:
        old = cur.get(e.get('inam') or '')
        if old:
            d = dict(old[1])
            changed = (d['text'] != e['text'] or d['disp'] != e['disp'] or d['qfinish'] != e.get('qfinish', False)
                       or d['qrestart'] != e.get('qrestart', False) or d['qname'] != e.get('qname', False))
            d.update(text=e['text'], disp=e['disp'], qname=e.get('qname', False),
                     qfinish=e.get('qfinish', False), qrestart=e.get('qrestart', False))
            if changed:
                rec = db.project.records.get('INFO|' + key + '|' + d['inam'].lower())
                _put(db, key, d, bool(rec and rec.get('created')))
        else:
            d = {k: v for k, v in parse_info(b'').items()}
            d.update(type=4, inam=_new_inam(db, key), text=e['text'], disp=e['disp'], qname=e.get('qname', False),
                     qfinish=e.get('qfinish', False), qrestart=e.get('qrestart', False))
            _put(db, key, d, True)
        keep.add(d['inam'])
        order.append(d['inam'])
    # stages removed in the editor (only my own can go)
    for inam, (ii, d) in cur.items():
        if inam not in keep and db.recs[ii][3] == db.proj_pidx:
            db.project.records.pop('INFO|' + key + '|' + inam.lower(), None)
    # chain my lines in stage order
    db.sync_project()
    ids = [x[1]['inam'] for x in ordered_lines(db, key)]
    mine_order = [i for i in order if i in ids]
    base = [i for i in ids if i not in set(mine_order)]
    final = base + mine_order if base else mine_order
    for n, inam in enumerate(final):
        rec = db.project.records.get('INFO|' + key + '|' + inam.lower())
        if not rec:
            continue
        d = next(x[1] for x in ordered_lines(db, key) if x[1]['inam'] == inam)
        d = dict(d, prev=final[n - 1] if n > 0 else '', next=final[n + 1] if n + 1 < len(final) else '')
        _put(db, key, d, rec.get('created'))
    commit(db, '%s quest "%s"' % ('Created' if created_now else 'Updated', (title or qid)))
    return key


def quests_using(db, qkey):
    """Lines elsewhere that check or set this quest (so you can see how it's wired up)."""
    low = qkey.lower()
    out = []
    for ii, rr in enumerate(db.recs):
        if rr is None or rr[0] != 'INFO' or not db.winner[ii] or ii in db.dead:
            continue
        r = rr
        _t, _f, data = db.files[r[3]].record_at(r[4])
        if low.encode(ENC, 'replace') not in data.lower():
            continue
        d = parse_info(data)
        dk = db.info_dial.get(ii)
        if dk is None or db.recs[dk][7] == low:
            continue
        sets = low in d['result'].lower()
        checks = any(c['kind'] == 'journal' and c['name'].lower() == low for c in d['conds'])
        if sets or checks:
            out.append({'topic': db.recs[dk][1], 'tkey': db.recs[dk][7], 'actor': d['actor'], 'text': d['text'][:160],
                        'sets': sets, 'checks': checks, 'mine': r[3] == db.proj_pidx})
    return out[:200]


def my_characters(db):
    """People and creatures in this mod (new or changed), for the quick list."""
    out = []
    for (tag, key), ri in getattr(db, 'overlay', {}).items():
        if tag in ('NPC_', 'CREA'):
            r = db.recs[ri]
            out.append({'id': r[1], 'name': r[2], 'type': tag})
    return sorted(out, key=lambda x: (x['name'] or x['id']).lower())


def options(db):
    """Lists for the editor's dropdowns."""
    def ids(tag):
        return sorted({db.recs[lst[-1]][1] for (t, k), lst in db.by_key.items() if t == tag and lst and lst[-1] not in db.dead},
                      key=str.lower)
    return {'functions': FUNCTIONS, 'ops': OPS, 'races': ids('RACE'), 'classes': ids('CLAS'),
            'factions': ids('FACT'), 'globals': ids('GLOB'), 'choice': CHOICE,
            'greetings': ['Greeting %d' % n for n in range(10)]}
