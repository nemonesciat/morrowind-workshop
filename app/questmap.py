"""Quests on the map: a quest's stages and steps with where each step happens (the people and things it
names, where they stand; a spot to reach, with its ring), for the quest maker docked under the 3D view, and
one call that adds the next stage and its step together (or begins a quest), as one Undo.

The steps themselves are written by questmake (dialogue lines, a script on a thing, the quest's watcher).
A spot to reach is a block in the watcher; its comment line `; at a spot: <cell key>|x|y|z|radius` is where
the map reads it back, so Undo and the script stay the one truth."""
import re

import dialogue
import editing
import mapdata
import questboard
import questmake
from editing import EditError

AFTER_RX = re.compile(r';\s*after quest:\s*(?P<quest>[^|\n]+)\|(?P<stage>-?\d+)\s*->\s*(?P<to>\d+)', re.I)
SPOT_RX = re.compile(r';\s*at a spot:\s*(?P<cell>[^|\n]+)\|(?P<x>-?[\d.]+)\|(?P<y>-?[\d.]+)\|(?P<z>-?[\d.]+)\|(?P<r>[\d.]+)\s*->\s*(?P<to>\d+)', re.I)


def game_cell_name(db, cell_key):
    """The name the game's GetPCCell tests against: an interior's name, a named outdoor cell's name, or (out in
    the wild) its region's name."""
    ci = mapdata.cell_info(db, cell_key) or {}
    if ci.get('interior') or not str(cell_key).startswith('#'):
        return ci.get('name') or ci.get('id') or cell_key
    if ci.get('name'):
        return ci['name']
    reg = ci.get('region') or ''
    ri = db.resolve_id(reg) if reg else None
    return (db.recs[ri][2] or db.recs[ri][1]) if ri is not None else reg


def spots_of(db, rid, limit=3, near=None):
    """Where something stands: [{'cell', 'name', 'pos'}] for its placed copies (people and things placed in cells;
    the first few). The place on the map (near) is looked at first, so a thing just placed there is found before
    the game's other copies of it."""
    from project import ref_info
    low = (rid or '').lower()
    out, seen = [], set()
    if not low:
        return out
    cells = []
    if near:
        cells.append(near)
    for ci in sorted(db.used_in.get(low, ())):
        r = db.recs[ci]
        if r is not None and r[0] == 'CELL' and ci not in db.dead:
            cells.append(r[7])
    for ck in cells:
        if ck in seen:
            continue
        seen.add(ck)
        try:
            refs, _h = db.cell_refs(ck)
        except Exception:
            continue
        for rk, ref in refs.items():
            if ref.get('deleted'):
                continue
            rid2, pos, _s, gone = ref_info(ref['subs'])
            if not gone and rid2.lower() == low:
                ci = mapdata.cell_info(db, ck) or {}
                out.append({'cell': ck, 'name': ci.get('id') or ck, 'pos': [round(pos[0]), round(pos[1]), round(pos[2])]})
                break
        if len(out) >= limit:
            break
    return out


def _watch_spots(db, qkey):
    """The spots to reach written in the quest's watcher: [{'to', 'cell', 'center', 'radius'}], and the other
    quests it waits for: [{'to', 'quest', 'stage'}]."""
    import mwscript
    sid = ((db.project.quests.get(qkey, {}) if db.project else {}) or {}).get('watch')
    if not sid or mwscript._winner(db, sid) is None:
        return sid, [], []
    try:
        text = mwscript.read(db, sid)['text']
    except Exception:
        return sid, [], []
    after = [{'to': int(m.group('to')), 'quest': m.group('quest').strip(), 'stage': int(m.group('stage'))} for m in AFTER_RX.finditer(text)]
    out = []
    for m in SPOT_RX.finditer(text):
        out.append({'to': int(m.group('to')), 'cell': m.group('cell').strip(), 'center': [float(m.group('x')), float(m.group('y')), float(m.group('z'))],
                    'radius': float(m.group('r'))})
    return sid, out, after


def overview(db, qkey, near=None):
    """The quest for the map: its stages, each with the steps that reach it and where they happen (near: the
    place on the map, looked at first)."""
    b = questboard.board(db, qkey)
    q = b['quest']
    wsid, spots, after = _watch_spots(db, q['key'])
    cache = {}

    def where(rid):
        k = (rid or '').lower()
        if k not in cache:
            cache[k] = spots_of(db, rid, near=near)
        return cache[k]
    steps = []
    for n, m in enumerate(b['moves']):
        ids = [m.get('who')] + list(m.get('carriers') or [])
        pins, seen = [], set()
        for rid in ids:
            if not rid or rid.lower() in seen or rid.lower().endswith('_watch'):
                continue
            seen.add(rid.lower())
            for s in where(rid):
                pins.append(dict(s, id=rid))
        st = {'n': n, 'verb': m['verb'], 'via': m['via'], 'who': m.get('who') or '', 'whoName': m.get('whoName') or '',
              'carriers': m.get('carriers') or [], 'items': m.get('items') or [], 'places': m.get('places') or [],
              'gives': m.get('gives') or [], 'takes': m.get('takes') or [], 'topic': m.get('tid') or m.get('topic') or '',
              'needs': m.get('needs') or [], 'sets': m.get('sets') or [], 'text': m.get('text') or '', 'mine': m.get('mine'),
              'script': m.get('script') or '', 'inam': m.get('inam') or '', 'pins': pins[:4]}
        if m['via'] == 'script' and wsid and m.get('script', '').lower() == wsid.lower():
            for sp in spots:
                if sp['to'] in st['sets']:
                    st['verb'], st['ring'] = 'reach', sp
                    break
            waits = {str(w.get('quest', '')).lower() for w in m.get('waits') or []}
            for af in after:
                if st['verb'] != 'reach' and af['to'] in st['sets'] and af['quest'].lower() in waits:
                    st['verb'], st['after'] = 'after', af
                    break
        steps.append(st)
    stages = [{'index': f['index'], 'text': f['text'], 'finished': f['finished'], 'missing': f['missing'],
               'reachable': f['reachable'], 'deadend': f['deadend'], 'in': f['in']} for f in b['frames']]
    # (where it goes: the places its steps happen in, stage by stage, each once)
    route, seen = [], set()
    for s in stages:
        for st in steps:
            if s['index'] not in st['sets']:
                continue
            p = st['pins'][0] if st['pins'] else ({'cell': st['ring']['cell'], 'pos': st['ring']['center']} if st.get('ring') else None)
            if not p and st['verb'] == 'enter' and st['places'] and mapdata.cell_info(db, st['places'][0].lower()):
                p = {'cell': st['places'][0].lower(), 'pos': None}            # (a place gone into: the place itself)
            if p and p['cell'] not in seen:
                seen.add(p['cell'])
                ci = mapdata.cell_info(db, p['cell']) or {}
                route.append({'cell': p['cell'], 'name': ci.get('id') or p.get('name') or p['cell'], 'pos': p['pos'], 'stage': s['index']})
    # (whose quest it is: a quest of another plugin, continued here, makes this mod change it)
    vs = [v for v in db.by_key.get(('DIAL', q['key']), []) if v not in db.dead]
    src = db.plugins[db.recs[vs[0]][3]]['name'] if vs else ''
    own = bool(q.get('created')) or (db.proj_pidx is not None and bool(vs) and db.recs[vs[0]][3] == db.proj_pidx)
    return {'quest': {'key': q['key'], 'id': q['id'], 'title': q['title'], 'own': own, 'plugin': src,
                      'mine': any(s.get('mine') for s in q['stages']) or not q['stages']},
            'stages': stages, 'steps': steps, 'cast': b['cast'], 'route': route}


def every(db):
    """Every quest in the load order, for the picker: [{'key', 'id', 'title', 'plugin', 'mine', 'stages'}], the
    pinned ones marked."""
    pins = set(pinned(db))
    return [{'key': r['key'], 'id': r['id'], 'title': r.get('title') or '', 'plugin': r.get('plugin') or '', 'mine': bool(r.get('mine')),
             'stages': r.get('stages', 0), 'pinned': r['key'] in pins} for r in questboard.quests(db)]


def pinned(db):
    """The quests pinned (☆) in this mod, to work on from the map: their keys."""
    if not db.project:
        return []
    return [k for k, v in (db.project.quests or {}).items() if isinstance(v, dict) and v.get('pinned')]


def pin(db, key, on):
    editing._require_project(db)
    key = (key or '').lower()
    dialogue.quest(db, key)                      # (a quest it must be)
    qq = db.project.quests.setdefault(key, {})
    if on:
        qq['pinned'] = True
    else:
        qq.pop('pinned', None)
    db.project.save()
    return {'pinned': pinned(db)}


def mine(db):
    """The quests of the open mod (and those it changes): [{'key', 'id', 'title', 'stages'}]."""
    out = []
    for r in questboard.quests(db, mine=True):
        out.append({'key': r.get('key'), 'id': r.get('id'), 'title': r.get('title') or '', 'stages': r.get('stages', 0)})
    return out


def place_item(db, qkey, pl):
    """A quest item put on a spot: a copy of the item of its own (named for the quest), so taking this one and
    no other copy in the game moves the quest. Its ID is returned."""
    ri = db.resolve_id(pl['id'])
    if ri is None:
        raise EditError('Nothing has the ID "%s".' % pl['id'])
    base = re.sub(r'[^A-Za-z0-9_]+', '_', '%s_%s' % (qkey[:12], db.recs[ri][1]))[:28]
    nid, n = base, 1
    while db.resolve_id(nid) is not None:
        n += 1
        nid = '%s_%d' % (base[:26], n)
    editing.duplicate_record(db, ri, nid)
    db.sync_project()
    # (a copy made for the quest is a quest item, not the original: what the original's own script did (a banner
    #  that lights at night, a chest that's someone's) would stop the quest's step from going on it)
    old = questmake._has_script(db, nid)
    if old:
        import mwscript
        mwscript.attach(db, old, nid, detach=True)
        db.sync_project()
    p = [float(v) for v in pl['pos']][:3]
    b = mapdata.object_bounds(db, db.resolve_id(nid))
    p[2] -= (b[2] if b else 0.0)
    editing.place_ref(db, pl['cell'], nid, p + [0.0, 0.0, 0.0], 1.0, None)
    return nid


def step(db, body):
    """Begin a quest, or add its next stage, with the step that reaches it, as one change.
    body: {'key'} of a quest, or {'new': {'id', 'title'}}; 'text' (the journal line), 'index' (the new stage;
    10 past the last when not given), 'finished'; 'move' (questmake's move: verb, who, thing, topic, say, items,
    gives, learns, place, days, dist; or verb 'reach' with 'cell', 'center', 'radius'); 'from' (the stage it starts
    from; the last stage when not given, nothing for a new quest)."""
    editing._require_project(db)
    stack = getattr(db.project, 'undo_stack', [])
    n0, ids0 = len(stack), {e.get('id') for e in db.project.log}
    try:
        return _step(db, body, stack, n0)
    except Exception:
        _take_back(db, n0, ids0)
        raise


def _take_back(db, n0, ids0):
    """A step refused part way (a thing that already runs a script, a name taken): what it had made is taken
    back, and leaves nothing behind, in the mod, in My changes or in Redo."""
    p = db.project
    stack = getattr(p, 'undo_stack', [])
    n = len(stack) - n0
    if n <= 0:
        return
    if n > 1:
        editing.fold(db, n, 'A quest step that was refused')
    redo0 = len(getattr(p, 'redo_stack', []))
    editing.undo(db)
    p.redo_stack[:] = p.redo_stack[:redo0]
    p.log[:] = [e for e in p.log if e.get('id') in ids0]


def _step(db, body, stack, n0):
    mv = dict(body.get('move') or {})
    text = (body.get('text') or '').strip()
    with editing.operation('quest'):
        if body.get('new'):
            nw = body['new']
            qid = re.sub(r'[^A-Za-z0-9_]+', '_', (nw.get('id') or nw.get('title') or '').strip()).strip('_')[:31]
            if not qid:
                raise EditError('Give the quest a name.')
            if dialogue._dial_versions(db, qid.lower()):
                raise EditError('There is already a quest or topic "%s": choose another name.' % qid)
            key = questmake.new_quest(db, qid, (nw.get('title') or qid).strip(), text)['key']
            index, frm = 10, 0
        else:
            key = (body.get('key') or '').lower()
            q = dialogue.quest(db, key)
            have = sorted(s['index'] for s in q['stages'])
            index = int(body['index']) if body.get('index') not in (None, '') else (have[-1] + 10 if have else 10)
            frm = int(body['from']) if body.get('from') not in (None, '') else (max([i for i in have if i < index], default=0))
            if index not in have:
                questmake.add_stage(db, key, index, text, bool(body.get('finished')))
        pl = body.get('place')
        if pl and pl.get('id') and pl.get('cell') and pl.get('pos'):
            mv['thing'] = place_item(db, key, pl)
        if mv.get('verb'):
            mv['to'], mv['from'] = index, frm
            if mv['verb'] == 'reach':
                mv['cellname'] = game_cell_name(db, mv.get('cell') or '')
            out = questmake.add_move(db, key, mv)
        else:
            out = {}
        # (the stage, its step and anything placed for it: one Undo, named for what it is)
        n = len(stack) - n0
        if n > 1:
            editing.fold(db, n, ('Began the quest "%s"' if body.get('new') else 'Added stage %d of "%s"' % (index, '%s')) % key)
    return {'key': key, 'index': index, 'from': frm, 'move': out}


# ---------------------------------------------------------------- taking a step out, moving a ring
def _watch_blocks(text, qid):
    """The watcher's blocks as questmake writes them: [(start, end, from, inner)], each
    "if ( GetJournalIndex "q" == from )" with its lines (each begins with a tab), then "endif"."""
    # (the script's text may come back with Windows line ends)
    rx = re.compile(r'\r?\nif \( GetJournalIndex "%s" == (\d+) \)\r?\n((?:\t[^\n]*\n)+)endif\r?\n' % re.escape(qid), re.I)
    return [(m.start(), m.end(), int(m.group(1)), m.group(2)) for m in rx.finditer(text)]


def _one_change(db, note, work):
    """work() as one Undo named note; refused part way, nothing is left behind."""
    editing._require_project(db)
    stack = getattr(db.project, 'undo_stack', [])
    n0, ids0 = len(stack), {e.get('id') for e in db.project.log}
    try:
        with editing.operation('quest'):
            out = work()
            n = len(stack) - n0
            if n > 1:
                editing.fold(db, n, note)
        return out
    except Exception:
        _take_back(db, n0, ids0)
        raise


def remove_step(db, key, st):
    """Take one step out of a quest, the way it was written: a line deleted; a script on a thing taken off it and
    deleted; a block of the watcher cut out. st: the step as overview gives it (via, topic, inam, script, sets,
    needs, carriers). The stage stays (its journal line), marked as nothing leading to it."""
    import mwscript
    q = dialogue.quest(db, key)
    to = (st.get('sets') or [None])[0]

    def work():
        if st.get('via') == 'line':
            dialogue.delete_line(db, st.get('topic') or '', st.get('inam') or '')
            return {'removed': 'line'}
        sid = st.get('script') or ''
        rec = db.project.records.get('SCPT|' + sid.lower())
        if not rec:
            raise EditError('That step comes from %s: only steps of your mod can be taken out here.' % (
                ('the script "%s"' % sid) if sid else 'another mod'))
        wsid = ((db.project.quests.get(key, {}) or {}).get('watch') or '').lower()
        if sid.lower() == wsid:
            text = mwscript.read(db, sid)['text'].replace('\r\n', '\n')
            jr = re.compile(r'Journal "%s" %d\b' % (re.escape(q['id']), int(to)), re.I)
            blocks = [b for b in _watch_blocks(text, q['id']) if jr.search(b[3])]
            if not blocks:
                raise EditError('That step is no longer in the quest\'s watcher script.')
            s0, e0 = blocks[0][0], blocks[0][1]
            mwscript.save(db, sid, text[:s0] + '\n' + text[e0:], create=False, save=False)
            editing.commit(db, 'Took the step to stage %s out of "%s"' % (to, q['id']))
            return {'removed': 'watch'}
        for c in st.get('carriers') or []:
            try:
                mwscript.attach(db, sid, c, detach=True)
            except EditError:
                pass
        if rec.get('created'):
            db.project.remove_record('SCPT', sid.lower())
            db.sync_project()
            editing.commit(db, 'Removed the script "%s"' % sid)
        return {'removed': 'script'}
    return _one_change(db, 'Took the step to stage %s out of "%s"' % (to, q['id']), work)


def remove_stage(db, key, index):
    """A stage (journal line) nothing reaches any more, taken out."""
    q = dialogue.quest(db, key)
    stages = [{'index': s['index'], 'text': s['text'], 'finished': s['finished'], 'restart': s['restart'], 'inam': s['inam']}
              for s in q['stages'] if s['index'] != int(index)]
    return _one_change(db, 'Took stage %d out of "%s"' % (int(index), q['id']), lambda: dialogue.save_quest(db, q['id'], q['title'], stages))


def move_ring(db, key, to, center=None, radius=None):
    """A spot to reach moved, or made bigger or smaller: its watcher block written again."""
    import mwscript
    q = dialogue.quest(db, key)
    wsid = (db.project.quests.get(key, {}) or {}).get('watch')
    if not wsid:
        raise EditError('This quest has no spot to reach.')
    text = mwscript.read(db, wsid)['text'].replace('\r\n', '\n')
    m = next((mm for mm in SPOT_RX.finditer(text) if int(mm.group('to')) == int(to)), None)
    if not m:
        raise EditError('That spot is no longer in the quest\'s watcher.')
    cell = m.group('cell').strip()
    c = [float(v) for v in (center or [m.group('x'), m.group('y'), m.group('z')])]
    r = int(float(radius if radius not in (None, '') else m.group('r')))
    blk = next(b for b in _watch_blocks(text, q['id']) if b[0] <= m.start() < b[1])
    new = questmake.reach_block(q, cell, game_cell_name(db, cell), c, r, int(to))
    whole = '\nif ( GetJournalIndex "%s" == %d )\n%s\nendif\n' % (q['id'], blk[2], new)

    def work():
        mwscript.save(db, wsid, text[:blk[0]] + whole + text[blk[1]:], create=False, save=False)
        editing.commit(db, 'Moved the spot to reach for stage %d of "%s"' % (int(to), q['id']))
        return {'center': c, 'radius': r}
    return _one_change(db, 'Moved the spot to reach for stage %d of "%s"' % (int(to), q['id']), work)
