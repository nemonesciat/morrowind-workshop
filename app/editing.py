"""All the ways a project can change: field edits, templates, reverts and
placing/moving/removing objects in cells. Every change is saved immediately."""
import os
import re
import struct
import threading
import time

from esm import ENC, iter_subrecords, zstr
from project import Snap, b64, join_subs, ref_info, set_ref_pos, state_diff, state_text, unb64, zs

PLACEABLE = {'STAT', 'ACTI', 'DOOR', 'CONT', 'LIGH', 'NPC_', 'CREA', 'LEVC', 'WEAP', 'ARMO', 'CLOT', 'MISC',
             'BOOK', 'ALCH', 'INGR', 'APPA', 'LOCK', 'PROB', 'REPA'}
NOT_COPYABLE = {'CELL', 'INFO', 'DIAL', 'LAND', 'PGRD', 'GMST', 'SKIL', 'MGEF', 'LTEX'}
INT_RANGES = {'b': (-128, 127), 'B': (0, 255), 'h': (-32768, 32767), 'H': (0, 65535),
              'i': (-2 ** 31, 2 ** 31 - 1), 'I': (0, 2 ** 32 - 1)}


class EditError(Exception):
    pass


def plugin_path(db):
    if getattr(db.project, 'source', None):
        return db.project.source          # a plugin opened as the mod: saved straight into that file (adopt.py)
    d = os.environ.get('WORKSHOP_PLUGIN_DIR') or db.config.get('data_local') or \
        os.path.join(db.config.get('userdata') or db.config['userdir'], 'data')
    return os.path.join(d, db.project.plugin)


def build(db, texts=None):
    """Write the mod (with its Lua files) and its grass file, if it has grass. texts: the places' JSON texts, if made."""
    db.project.build(db.proj_masters, plugin_path(db), texts)
    try:
        import grass
        grass.write(db)
    except Exception as e:                  # grass must never stop the mod itself being saved
        print('could not write the grass file:', e)


def grass_file(db):
    """The mod's groundcover plugin name, when it has grass."""
    p = db.project
    if not p or not getattr(p, 'grass', None):
        return None
    import grass
    return grass.file_name(p)


def lua_content(db):
    """The mod's .omwscripts file name, when it has Lua scripts (it goes in the load order too)."""
    p = db.project
    if not p or not getattr(p, 'lua', None) or not p.lua_allowed():
        return None
    return p.lua_omwscripts()


# One operation made of several changes (a town's Make: its outside, each house copied and peopled, its doors linked):
# each change logged inside it carries the operation's id, so My mod shows them as one row (the user 2026-11-02: two
# towns made after another were lost among their houses' rows and the ground reshaped before them).
# (per thread: a town making lets other requests in between its steps, breathe(), and their changes aren't the town's)
_op = {}


def _cur_op():
    return _op.get(threading.get_ident())


class operation:
    def __init__(self, kind):
        self.kind, self.mine = kind, False

    def __enter__(self):
        me = threading.get_ident()
        if not _op.get(me):                 # (one inside another is part of the outer one)
            if not _op and not BUSY:
                # (long work about to start, none other under way: the marks of what was handed out before it are
                # cleared, so its steps make again only the texts of the places it touches itself, project.Tracked)
                try:
                    import project
                    if project.ACTIVE[0] is not None:
                        project.ACTIVE[0].settle()
                except Exception as e:
                    print('settle:', e)
            _op[me], self.mine = '%s-%d' % (self.kind, int(time.time() * 1000)), True
        return self

    def __exit__(self, *_a):
        if self.mine:
            _op.pop(threading.get_ident(), None)
            held = _writer.get('held')
            if held is not None and not _op and WRITE_LOCK is None:
                _writer['held'] = None
                _write_now(held)             # (no writer thread: what the operation's steps held back, written now)


# Long work (a town, a castle, furnishing many rooms) steps aside after each change it makes for the requests waiting
# for the edit lock, and goes on when they are done: a town held the lock for six minutes and every other click in
# the Workshop waited on it, "staring at a locked screen is unacceptable" (the user, 2026-11-02). Undo, Redo and
# switching mods are refused meanwhile (they would pull the half-made town from under it); BUSY says what is making.
WAITING = [0]                   # requests waiting for WRITE_LOCK now (the server counts them, workshop._EditLock)
BUSY = {}                       # thread -> the operation it lets others in on, while it does
BREATHE_AFTER = 3.0             # (only work that has run this long steps aside)
_req = threading.local()


def request_started():
    _req.t = time.time()


# One press of Undo takes back one change, always. Keeping the big changes within reach (Undo keeps about 100 steps,
# and an evening of ground strokes pushed the town made before them out: the user, 2026-11-02) is done two ways:
# - a group the user opens and closes (the toolbar's Group, My mod's switch): what was done meanwhile becomes one
#   step when it is closed. While it is open its changes are steps like any other;
# - when the history is full, two like steps at its far end become one instead of the oldest being let go
#   (_make_room): a long run of strokes or moves folds where nobody is looking.
# Until 2.7.1 strokes and moves in a row folded as they came, and an open group folded all but its last change: ten
# moves, then Undo twice, stood the thing back at its first spot. Reported as a fault twice, 2026-11-12; the user: "He
# has a point."
# Not recording changes at all was the first idea: Undo goes back to the mod as it was, so a change it didn't know
# of would have been taken away with the step before it.

def group_open(db, name=''):
    p = db.project
    _require_project(db)
    if getattr(p, '_grp', None) and p._grp.get('manual'):
        if name:
            p._grp['name'] = name.strip()[:80]          # (named while open, on My mod)
        return group_state(db)
    # ('old': what Undo had already taken back when the group was opened; put back by Redo, it is not the group's)
    p._grp = {'manual': True, 'start': len(getattr(p, 'undo_stack', [])), 'since': time.time(), 'total': 0,
              'name': (name or '').strip()[:80],
              'old': {r[3] for r in getattr(p, 'redo_stack', []) if len(r) > 3}}
    return group_state(db)


def group_close(db, name=None):
    """Close the open group: what it holds becomes one step named after it."""
    p = db.project
    g = getattr(p, '_grp', None)
    if not (g and g.get('manual')):
        return None
    p._grp = None
    stack = getattr(p, 'undo_stack', [])
    n = len(stack) - g['start']
    if n <= 0:
        return None
    if name is not None:
        g['name'] = (name or '').strip()[:80]
    return _merge(db, len(stack) - n, len(stack), _group_label(g))


def group_state(db):
    p = db.project
    g = getattr(p, '_grp', None) if p else None
    if not (g and g.get('manual')):
        return None
    return {'on': True, 'name': g['name'], 'since': time.strftime('%H:%M', time.localtime(g['since'])), 'changes': g['total']}


def _group_label(g):
    t0 = time.strftime('%H:%M', time.localtime(g['since']))
    head = g['name'] or 'Group'
    return '%s: %d change%s, %s–%s' % (head, g['total'], '' if g['total'] == 1 else 's', t0, time.strftime('%H:%M'))


def _merge(db, i, j, note):
    """Undo steps i to j (stack positions) become one, named note; its log entry stands where the first one stood."""
    p = db.project
    stack = p.undo_stack
    items = stack[i:j]
    if not items:
        return None
    before = items[0][0]
    after = stack[j][0] if j < len(stack) else p.last_state
    ids = {it[2] for it in items if len(it) > 2 and it[2]}
    pos = next((k for k, e in enumerate(p.log) if e.get('id') in ids), None)
    op = next((e.get('op') for e in p.log if e.get('id') in ids and e.get('op')), None)
    p.log[:] = [e for e in p.log if e.get('id') not in ids]
    entry = p.note(note, state_diff(before, after))
    if op:
        entry['op'] = op
    if pos is not None:
        p.log.remove(entry)
        p.log.insert(pos, entry)
    stack[i:j] = [(before, note, entry['id'])]
    _write_soon(db)
    _notify(db, entry)
    return entry


# The open group holds what was done while it was open, and nothing from before it. Where it begins in the history
# (g['start']) stays put when Undo goes back past it, so that Redo puts the earlier steps back as their own. (Until
# 2.7.2-test6 the start followed Undo down: three moves, Group on, three more, Undo six times, Redo six times, Group
# off made one step of all six, the three from before the group among them; tosky0890 on Discord, 2026-11-12: "the
# Undo stack gets messed up when the Group function is enabled afterward".)
def _group_undone(p, i):
    """Undo is taking back the step at stack position i."""
    g = getattr(p, '_grp', None)
    if g and not g.get('manual'):
        p._grp = None
    elif g and i >= g['start']:
        g['total'] = max(0, g['total'] - 1)            # (a step of the group taken back)


def _group_redone(p, i, undid):
    """Redo is putting a step back at stack position i (undid: the Undo that had taken it back)."""
    g = getattr(p, '_grp', None)
    if g and not g.get('manual'):
        p._grp = None
    elif g and undid in g.get('old', ()):
        g['start'] = max(g['start'], i + 1)            # (taken back before the group was opened: it stays outside)
    elif g and i >= g['start']:
        g['total'] += 1


def _grouped(db, entry, note, trimmed):
    """After a commit: counted into the open group. Its steps stay steps (one Undo, one change) until it is closed."""
    p = db.project
    g = getattr(p, '_grp', None)
    if g and g.get('manual'):
        g['start'] = max(0, g['start'] - trimmed)
        at = len(getattr(p, 'undo_stack', [])) - 1     # (where this change stands in the history)
        if at < g['start']:
            # (Undo had gone back past where the group began, and work went on from there: it begins here)
            g['start'], g['total'] = max(0, at), 0
        g['total'] += 1
    elif g:
        p._grp = None


_ROW_RE = re.compile(r' \((\d+) in a row\)$')
UNDO_STEPS = 100


def _make_room(db, stack):
    """The history is full and a step is about to be added: two steps at its far end become one, so that no step is
    let go. The oldest two that stand side by side and are both of the open group, or carry the same note (ground
    strokes in a row, a thing moved again and again). True when room was made; False when no two are alike (the
    oldest step is then let go, as ever) or an operation is under way (it folds its own steps when it ends)."""
    p = db.project
    if _cur_op() or len(stack) < UNDO_STEPS:
        return False
    g = getattr(p, '_grp', None)
    start = g['start'] if g and g.get('manual') else None
    base = [_ROW_RE.sub('', str(it[1])) for it in stack]
    for i in range(len(stack) - 1):
        if start is not None and i + 1 == start:
            continue                                  # (the step before the group and the group's first: never one)
        ingroup = start is not None and i >= start
        if not ingroup and base[i] != base[i + 1]:
            continue
        if ingroup:
            note = _group_label(g)
        else:
            n = sum(int(m.group(1)) if m else 1 for m in (_ROW_RE.search(str(it[1])) for it in stack[i:i + 2]))
            note = '%s (%d in a row)' % (base[i], n)
        _merge(db, i, i + 2, note)
        if start is not None and i < start:
            g['start'] -= 1
        return True
    return False


def breathe():
    """Let the requests waiting for the edit lock have it, then take it back. Call it where the project is in one
    piece: after a commit."""
    lk = WRITE_LOCK
    if lk is None or not WAITING[0] or time.time() - getattr(_req, 't', time.time()) < BREATHE_AFTER:
        return
    if not lk._is_owned():
        return
    me = threading.get_ident()
    n = lk._recursion_count()
    BUSY[me] = _op.get(me) or 'work'
    for _ in range(n):
        lk.release()
    try:
        t0 = time.time()
        while WAITING[0] and time.time() - t0 < 5:
            time.sleep(0.02)
    finally:
        for _ in range(n):
            lk.acquire()
        BUSY.pop(me, None)


BUSY_NAMES = {'town': 'Making a town', 'castle': 'Making a castle', 'land': 'Shaping the land', 'example': 'Making an example'}


def busy_with():
    """What long work is under way while it lets others in ('Making a town'...), or None."""
    for v in list(BUSY.values()):
        return BUSY_NAMES.get(str(v).split('-')[0], 'A big change')
    return None


def commit(db, note=None, reverts=None):
    p = db.project
    before = getattr(p, 'last_state', None)
    after = p.snapshot(before)
    entry = None
    if note:
        entry = p.note(note, state_diff(before, after) if before is not None else None)
        if reverts:
            entry['reverts'] = reverts
        if _cur_op():
            entry['op'] = _cur_op()
    trimmed = 0
    if before is not None:
        # (the state from before an operation's first change, for fold: the undo stack keeps 100 steps, and a town's
        # Make runs to 1,400, so its one Undo step covered the last 100 and left the rest of the town standing;
        # the user's Sketh, 2026-11-07)
        op_ = _cur_op()
        if op_ and (p.__dict__.get('_op_before') or (None,))[0] != op_:
            p._op_before = (op_, before)
            p._op_steps = [op_, 0, 0]       # (the operation's steps on the stack, and how many the stack has let go since)
        stack = p.__dict__.setdefault('undo_stack', [])
        _make_room(db, stack)               # (before the step goes on: last_state is still the state after the last one)
        was = len(stack)
        stack.append((before, note or 'change', entry['id'] if entry else None))
        del stack[:-UNDO_STEPS]
        p.redo_stack = []                   # (a new change after an Undo: what was undone can't come back)
        p.redo_together = []
        # big projects (lots of grass) make big undo steps: keep the history within ~300 MB (a Snap counts the parts
        # new in it; the rest it shares with the step before)
        total = sum(_step_size(s[0]) for s in stack)
        while len(stack) > 5 and total > 300_000_000:
            total -= _step_size(stack.pop(0)[0])
        trimmed = was + 1 - len(stack)
        os_ = p.__dict__.get('_op_steps')
        if op_ and os_ and os_[0] == op_:
            os_[1] += 1
            os_[2] += max(0, trimmed)
    p.last_state = after
    db.sync_project(texts=after.c)
    _write_soon(db)
    _notify(db, entry)
    try:
        import together
        if together.active():
            together.on_commit(db, state_text(before), state_text(after), note)       # (building together: to everyone else)
    except Exception as e:                  # sharing must never break editing
        print('building together:', e)
    if before is not None:
        _grouped(db, entry, note, trimmed)
    breathe()
    return entry


def _step_size(s):
    return s.size if isinstance(s, Snap) else len(s)


# The project file and the plugin are written a moment after a change, not inside it: writing a big
# project (the user's: 7 MB with its change log) took most of a second on every move, so dragging
# things about lagged and a quick second move could be answered after the first. One writer thread
# writes once for a burst of changes, under the server's edit lock (WRITE_LOCK, set by the server; with
# none, as in the lab, every change is written at once). flush() writes what is pending now, for the
# places that need the files on disk: starting the game, packaging a release, switching mods, closing.
WRITE_LOCK = None
WRITE_DELAY = 0.3
_writer = {'pending': None, 'thread': None, 'lock': threading.Lock(), 'done': threading.Event(), 'held': None, 'last': 0.0}
# While long work is under way (a town, a castle) the mod is written to disk at most this often, and once when it is
# done: each write is the whole mod, half a second on a 30 MB one, and a town's forty steps each had one, a third of
# the whole Make (2026-11-09 profile). A crash loses at most this much of a half-made town.
WRITE_HOLD = 20.0


def _hold():
    return bool(_op or BUSY) and time.time() - _writer['last'] < WRITE_HOLD


def _write_now(db):
    import json
    texts = None
    try:
        # (each place's text made once, for the project file and to tell which places' bytes are as they were)
        # (every place's text made anew here, whatever the marks say: what goes to disk is the mod as it is. A place
        # found changed with no mark was kept and changed after a settle: said, and what the Workshop reads and the
        # Undo state put right from the texts just made)
        p = db.project
        texts, stale = p.part_texts('cells', full=True)
        _rt, stale_r = p.part_texts('records', full=True)
        if stale or stale_r:
            print('changed without a mark (kept across a settle):', (stale + stale_r)[:8], len(stale) + len(stale_r))
            db.sync_project(texts=texts)
            p.last_state = p.snapshot(getattr(p, 'last_state', None))
        if not _op and not BUSY and WRITE_LOCK is not None:
            p.settle()                       # (every request done, no long work stepping aside: nothing holds a place)
    except Exception as e:
        print('could not read the places:', e)
    _writer['last'] = time.time()
    try:
        db.project.save(texts)
    except Exception as e:
        print('could not save the project:', e)
    try:
        build(db, texts)
    except Exception as e:
        print('could not write the mod:', e)


def _write_soon(db):
    if WRITE_LOCK is None:
        if _hold():
            _writer['held'] = db
            return
        _writer['held'] = None
        _write_now(db)
        return
    with _writer['lock']:
        _writer['pending'] = db
        _writer['done'].clear()
        t = _writer['thread']
        if t is None or not t.is_alive():
            t = threading.Thread(target=_writer_run, name='project-writer', daemon=True)
            _writer['thread'] = t
            t.start()


def _writer_run():
    while True:
        time.sleep(WRITE_DELAY)                # (a burst of moves becomes one write)
        with _writer['lock']:
            db = _writer['pending']
            _writer['pending'] = None
        if db is None:
            with _writer['lock']:
                if _writer['pending'] is None:
                    _writer['done'].set()
                    return
            continue
        if _hold():                          # (long work under way and written not long ago: looked at again shortly)
            with _writer['lock']:
                if _writer['pending'] is None:
                    _writer['pending'] = db
            continue
        with WRITE_LOCK:
            _write_now(db)


def flush(db=None):
    """Write any change still pending, now (and wait for it)."""
    if WRITE_LOCK is None:
        held, _writer['held'] = _writer.get('held'), None
        if held is not None:
            _write_now(held)
        return
    with _writer['lock']:
        pending = _writer['pending']
        _writer['pending'] = None
    if pending is not None:
        with WRITE_LOCK:
            _write_now(pending)
    t = _writer['thread']
    if t is not None and t.is_alive() and threading.current_thread() is not t:
        _writer['done'].wait(30)


# Every change, counted, with the places it touched and the window that made it: a second Workshop window
# on the same server asks /api/changes?since=n every second or so and reloads what another window changed.
# ORIGIN.window is set by the server for the request being answered (the page's X-Workshop-Window header).
CHANGES = {'n': 0, 'recent': []}
ORIGIN = threading.local()


def _count_change(entry):
    d = (entry or {}).get('diff') or {}
    CHANGES['n'] += 1
    CHANGES['recent'].append({'n': CHANGES['n'], 'by': getattr(ORIGIN, 'window', None),
                              'cells': sorted(d.get('c', {})) if entry and d else None,
                              'records': bool(d.get('r')) if entry and d else True})
    del CHANGES['recent'][:-200]


def changes_since(n):
    """What changed after change n: {'n': now, 'changes': [...]}, or 'all': True when n is too old to say."""
    rec = CHANGES['recent']
    out = [c for c in rec if c['n'] > n]
    return {'n': CHANGES['n'], 'changes': out, 'all': bool(rec) and n < rec[0]['n'] - 1}


def _notify(db, entry=None):
    _count_change(entry)
    cb = getattr(db, 'on_project_change', None)
    if cb:
        try:
            cb()
        except Exception as e:      # the live link must never break editing
            print('live link update failed:', e)


def undo_depth(db):
    return len(getattr(db.project, 'undo_stack', [])) if db.project else 0


def redo_depth(db):
    p = db.project
    if not p:
        return 0
    try:
        import together
        if together.active():
            return len(getattr(p, 'redo_together', []))
    except ImportError:
        pass
    return len(getattr(p, 'redo_stack', []))


def redo_note(db):
    """What Redo would put back, as the lists show it ('' when nothing)."""
    p = db.project
    if not p:
        return ''
    try:
        import together
        if together.active():
            ids = getattr(p, 'redo_together', [])
            e = next((x for x in p.log if ids and x.get('id') == ids[-1]), None)
            return note_label(p, e['text'][len('Undid: '):]) if e and e['text'].startswith('Undid: ') else ''
    except ImportError:
        pass
    stack = getattr(p, 'redo_stack', [])
    return note_label(p, stack[-1][1], stack[-1][2]) if stack else ''


# A whole furnish or build reads as one named step wherever changes are listed (My mod's activity
# list, Undo's tooltip, the Undo toast): "Furnished Bleeding Abcess (636 things)", "Built Bleeding
# Abcess from pieces (412 pieces)". The label is composed here from the change's own note and what
# its diff placed; the notes furnish and the builder write stay as they are.
_FURNISHED_RE = re.compile(r'^Auto-furnished (.+) \((\d+) things? in \d+ rooms?\)')
_BUILT_RE = re.compile(r'^Built a new .+? (?:interior|house) "(.+?)"(?: on \d+ floors?)? \(\d+ rooms?, \d+ tiles?\)')
_ON_TOP_RE = re.compile(r' \(and \d+ changes? made on top of it\)$')


def note_label(p, text, entry_id=None):
    """The note of a change as the lists show it (see above); any other note comes back as it is."""
    if not text:
        return text
    for prefix in ('Undid: ', 'Redid: '):
        if text.startswith(prefix):
            return prefix + note_label(p, text[len(prefix):])
    tail = _ON_TOP_RE.search(text)
    tail = tail.group(0) if tail else ''
    m = _FURNISHED_RE.match(text)
    if m:
        return 'Furnished %s (%s things)%s' % (m.group(1), m.group(2), tail)
    m = _BUILT_RE.match(text)
    if m:
        n = _placed_by(p, text, entry_id)
        return 'Built %s from pieces%s%s' % (m.group(1), ' (%d pieces)' % n if n else '', tail)
    return text


def _placed_by(p, text, entry_id=None):
    """How many objects a logged change placed, from its diff (the entry by id, or the last with this note)."""
    for e in reversed(getattr(p, 'log', None) or []):
        if e.get('id') == entry_id if entry_id is not None else e.get('text') == text:
            d = e.get('diff') or {}
            return sum(1 for cd in d.get('c', {}).values() for _b, a in cd.get('refs', {}).values() if a is not None)
    return 0


TOUCHED_MOST = 200


def _touched(diff):
    """The placed things a step of Undo or Redo changed, as [{cell, ref}]: the page selects those that are still
    there. (All of them, not only those the mod still holds: a thing of the game's put back where the game has it is
    no longer in the mod, and is the very thing to select.) None when there are too many to be a selection (a town
    taken back and put back)."""
    out = []
    for ck, cd in ((diff or {}).get('c') or {}).items():
        for rk in (cd.get('refs') or {}):
            out.append({'cell': ck, 'ref': rk})
            if len(out) > TOUCHED_MOST:
                return []
    return out


def touched(db):
    """What the last Undo or Redo changed (see _touched)."""
    return list(getattr(db.project, '_touched', None) or []) if db.project else []


def undo(db, to_depth=None):
    """Undo the last change, or every change back to a recorded depth."""
    _require_project(db)
    p = db.project
    p._touched = []
    try:
        import together
        if together.active() and to_depth is None:
            # building together: your own last change only (putting the whole mod back would take
            # other people's work with it)
            e = together.own_last(p)
            if not e:
                raise EditError('Nothing of yours to undo.')
            keep = list(getattr(p, 'redo_together', []))
            new = undo_entry(db, e['id'])
            p.redo_together = keep + [new['id']]       # (Redo takes back this "Undid" step, as My mod's list does)
            return [e['text']]
    except ImportError:
        pass
    stack = getattr(p, 'undo_stack', [])
    if not stack:
        raise EditError('Nothing to undo.')
    target = len(stack) - 1 if to_depth is None else max(0, int(to_depth))
    undone, ids, redo = [], [], []
    before = p.last_state
    cur = p.snapshot(before)
    while len(stack) > target:
        _group_undone(p, len(stack) - 1)
        item = stack.pop()
        state, note = item[0], item[1]
        # (Redo puts back the state as it was before this Undo, step by step: the earliest step on top)
        redo.append((cur, note, item[2] if len(item) > 2 else None))
        p.restore(state, cur)
        cur = state
        undone.append(note)
        if len(item) > 2 and item[2]:
            ids.append(item[2])
    for i in ids:
        _set_active(p, i, False)
    after = p.snapshot(cur if isinstance(cur, Snap) else before)
    diff = state_diff(before, after)
    entry = p.note('Undid: ' + '; '.join(undone[:5]) + (' (+%d more)' % (len(undone) - 5) if len(undone) > 5 else ''),
                   diff)
    p._touched = _touched(diff)
    entry['reverts'] = ids
    p.__dict__.setdefault('redo_stack', []).extend(r + (entry['id'],) for r in redo)
    p.last_state = after
    db.sync_project(texts=after.c)
    _write_soon(db)
    _notify(db, entry)
    return undone


def redo(db):
    """Put back the last change Undo took back, exactly as it was. Returns its note."""
    _require_project(db)
    p = db.project
    p._touched = []
    try:
        import together
        if together.active():
            # building together: take back your own last "Undid" step (later changes by others are kept)
            ids = list(getattr(p, 'redo_together', []))
            if not ids:
                raise EditError('Nothing to redo.')
            e = next((x for x in p.log if x.get('id') == ids[-1]), None)
            if not e or e.get('undone'):
                p.redo_together = []
                raise EditError('Nothing to redo.')
            undo_entry(db, ids[-1])
            p.redo_together = ids[:-1]
            return e['text'][len('Undid: '):] if e['text'].startswith('Undid: ') else e['text']
    except ImportError:
        pass
    redo_stack = getattr(p, 'redo_stack', [])
    if not redo_stack:
        raise EditError('Nothing to redo.')
    state, note, orig, undid = redo_stack.pop()
    before = p.last_state
    stack = p.__dict__.setdefault('undo_stack', [])
    _group_redone(p, len(stack), undid)
    now = p.snapshot(before)
    stack.append((now, note, orig))
    p.restore(state, now)
    if orig:
        _set_active(p, orig, True)
    u = next((x for x in p.log if x.get('id') == undid), None)
    if u and all(not x.get('undone') for x in p.log if x.get('id') in u.get('reverts', [])):
        u['undone'] = True                 # (every step that Undo took back is in effect again)
    after = p.snapshot(state if isinstance(state, Snap) else now)
    diff = state_diff(before, after)
    entry = p.note('Redid: ' + note, diff)
    p._touched = _touched(diff)
    entry['reverts'] = [undid] if undid else []
    p.last_state = after
    db.sync_project(texts=after.c)
    _write_soon(db)
    _notify(db, entry)
    return note


def fold(db, n, note):
    """The last n undo steps become one, named note (Extend mode's pieces laid one by one become "Extended
    the Hall by 7 pieces"; a room added and furnished becomes one step). The log keeps one entry for the
    whole, with the diff from before the first to after the last."""
    _require_project(db)
    p = db.project
    stack = getattr(p, 'undo_stack', [])
    asked = int(n)
    n = min(asked, len(stack))
    if n <= 0:
        return None
    items = stack[-n:]
    del stack[-n:]
    before = items[0][0]
    ids = {it[2] for it in items if len(it) > 2 and it[2]}
    op_ = _cur_op()
    ob = p.__dict__.get('_op_before')
    os_ = p.__dict__.get('_op_steps')
    if os_ and os_[0] != op_:
        os_ = None
    # (the whole operation only when the fold asks for all of its steps: a maker inside it that folds its own, a
    # castle's keep made anew, took the operation's start for its own and left the castle's one Undo step starting
    # half way, its record still 'making' and most of it standing after Drop; practice 2, 2026-11-11. The start is
    # kept for the folds that follow in the same operation)
    if op_ and ob and ob[0] == op_ and (os_ is None or asked + os_[2] >= os_[1]):
        before = ob[1]                               # (the whole operation, however many steps the stack kept)
        ids |= {e.get('id') for e in p.log if e.get('op') == op_}
        if os_:
            os_[1], os_[2] = 1, 0
    elif os_:
        os_[1] -= n - 1
    p.log[:] = [e for e in p.log if e.get('id') not in ids]
    after = p.snapshot()
    entry = p.note(note, state_diff(before, after))
    if _cur_op():
        entry['op'] = _cur_op()
    stack.append((before, note, entry['id']))
    p.last_state = after
    db.sync_project(texts=after.c)
    _write_soon(db)
    _notify(db, entry)
    return entry


def _set_active(p, entry_id, active, depth=0):
    """Mark a logged change as in effect or undone. An "Undid ..." entry being
    in effect means the changes it reverted are not, and the other way round."""
    if depth > 50:
        return
    e = next((x for x in p.log if x.get('id') == entry_id), None)
    if not e:
        return
    e['undone'] = not active
    for r in e.get('reverts', []):
        _set_active(p, r, not active, depth + 1)


def _footprint(db, e):
    """What a logged change touched and created, for working out which later changes build on it. (Kept for each entry
    while its diff is the same: My mod's list read every object of every change again, a second a look on a big mod.)"""
    memo = db.project.__dict__.setdefault('_fp_memo', {}) if db is not None and db.project is not None else {}
    got = memo.get(id(e))
    if got is not None and got[0] is e and got[1] is e.get('diff'):
        return got[2]
    f = _footprint_of(db, e)
    if len(memo) > 4000:
        memo.clear()
    memo[id(e)] = (e, e.get('diff'), f)
    return f


def _footprint_of(db, e):
    import base64
    d = e.get('diff') or {}
    f = {'keys': set(), 'cells': set(), 'new_cells': set(), 'new_ids': set(), 'names': set(), 'dials': set(),
         'new_dials': set()}
    for k, (b, a) in d.get('r', {}).items():
        f['keys'].add(('r', k))
        tag, key = k.split('|', 1)
        if tag == 'INFO':
            f['dials'].add(key.split('|', 1)[0])
        elif tag == 'DIAL':
            f['dials'].add(key)
            if b is None:
                f['new_dials'].add(key)
        elif tag == 'PGRD':
            f['cells'].add(key)                 # walking paths belong to their place
        elif b is None:
            f['new_ids'].add(key)
    for ck, cd in d.get('c', {}).items():
        f['cells'].add(ck)
        made = cd.get('meta', {}).get('new')
        if made is None and db is not None:
            # older entries: a place only this mod has, whose objects all appeared in this change
            versions = [v for v in db.by_key.get(('CELL', ck), []) if v not in db.dead]
            made = all(db.recs[v][3] == db.proj_pidx for v in versions) and all(b is None for b, _a in cd['refs'].values())
        if made:
            f['new_cells'].add(ck)
        for rk, (b, a) in cd['refs'].items():
            f['keys'].add(('c', ck, rk))
            for side in (a, b):
                if side:
                    for t, v in side.get('subs', []):
                        if t == 'NAME':
                            f['names'].add(zstr(base64.b64decode(v)).lower())
                            break
    return f


def _live(p):
    """Real changes still in effect. "Undid"/"Redid" entries are bookkeeping: their effect is already
    told by the original changes being marked undone or not."""
    return [e for e in p.log if e.get('diff') and not e.get('undone') and not e.get('reverts')]


def _builds_on(later, earlier):
    return bool(later['keys'] & earlier['keys'] or later['cells'] & earlier['new_cells'] or
                later['names'] & earlier['new_ids'] or later['dials'] & earlier['new_dials'])


class _Group:
    """The union of a group of changes' footprints: _builds_on(later, any of them) in one test, as the lists ask it
    for every pair of changes (cubic in the log, half a second a look at My mod on a big mod)."""
    def __init__(self, fp):
        self.u = {k: set(fp[k]) for k in ('keys', 'new_cells', 'new_ids', 'new_dials')}

    def add(self, fp):
        for k in self.u:
            self.u[k] |= fp[k]

    def built_on_by(self, later):
        u = self.u
        return bool(later['keys'] & u['keys'] or later['cells'] & u['new_cells'] or
                    later['names'] & u['new_ids'] or later['dials'] & u['new_dials'])


def _adds_to(later, earlier):
    """later puts something into what earlier made (its places, things or topics), not just the same things again."""
    return bool(later['cells'] & earlier['new_cells'] or later['names'] & earlier['new_ids'] or
                later['dials'] & earlier['new_dials'])


def activity(db):
    """For each change in the log: the change it builds on (parent) and how many later changes build
    on it, directly or through others (inside). Only changes still in effect count."""
    p = db.project
    live = _live(p)
    fps = {e['id']: _footprint(db, e) for e in live}
    parent, kids = {}, {}
    for n, e in enumerate(live):
        # (shown inside another only when it adds to what that one made: furniture in a house you built, lines in
        # your topic. Changes that make places of their own (a town, a castle) and changes that only go over the same
        # ground again stay on top, by time: each town levelled the ground reshaped before it and sank into a staircase
        # of "Ground reshaped" rows, the user 2026-11-02. Undo still takes back everything built on a change.)
        if fps[e['id']]['new_cells']:
            continue
        for prev in reversed(live[:n]):
            if _adds_to(fps[e['id']], fps[prev['id']]):
                parent[e['id']] = prev['id']
                kids.setdefault(prev['id'], []).append(e['id'])
                break
    return parent, kids, fps


def branch_sizes(db):
    """For each change still in effect: how many later changes Undo would take back with it."""
    live = _live(db.project)
    fps = {e['id']: _footprint(db, e) for e in live}
    out = {}
    for n, e in enumerate(live):
        group, size = _Group(fps[e['id']]), 0
        for later in live[n + 1:]:
            if group.built_on_by(fps[later['id']]):
                group.add(fps[later['id']])
                size += 1
        out[e['id']] = size
    return out


def _dependents(db, entry_id):
    """Every later change still in effect that builds on this one, directly or through another."""
    p = db.project
    live = _live(p)
    fps = {e['id']: _footprint(db, e) for e in live}
    group, out = None, []
    if entry_id in fps:
        group = _Group(fps[entry_id])
    for e in live:
        if e['id'] <= entry_id or group is None:
            continue
        if group.built_on_by(fps[e['id']]):
            group.add(fps[e['id']])
            out.append(e['id'])
    return out


def _revert_diff(p, d):
    """Put back the "before" side of a change."""
    for k, (b, _a) in d['r'].items():
        if b is None:
            p.records.pop(k, None)
        else:
            p.records[k] = b
    for ck, cd in d['c'].items():
        c = p.cells.get(ck)
        if c is None:
            c = p.cells[ck] = {'flags': cd['meta']['flags'], 'header': cd['meta']['header'], 'refs': {}}
            for k in ('plan', 'props'):
                if k in cd['meta']:
                    c[k] = cd['meta'][k]
        for rk, (b, _a) in cd['refs'].items():
            if b is None:
                c['refs'].pop(rk, None)
                (p.town_parts or {}).pop(rk, None)        # (a town's or castle's piece taken back leaves its parts list)
            else:
                c['refs'][rk] = b
        if not c['refs'] and not c.get('props'):
            p.cells.pop(ck, None)


def undo_branch(db, entry_id):
    """Take back a change and every later change built on it (newest first), as one step."""
    _require_project(db)
    p = db.project
    entry = next((e for e in p.log if e.get('id') == entry_id), None)
    if not entry:
        raise EditError('That change is no longer in the list.')
    if entry.get('undone'):
        raise EditError('That change has already been undone.')
    if not entry.get('diff'):
        raise EditError('This change was made before per-change undo existed, so it can\'t be undone on its own.')
    deps = _dependents(db, entry_id)
    if not deps:
        return undo_entry(db, entry_id)
    by_id = {e['id']: e for e in p.log}
    for i in sorted([entry_id] + deps, reverse=True):
        _revert_diff(p, by_id[i]['diff'])
    for i in [entry_id] + deps:
        _set_active(p, i, False)
    text = entry['text']
    label = ('Redid: ' + text[len('Undid: '):]) if text.startswith('Undid: ') else 'Undid: ' + text
    return commit(db, '%s (and %d change%s made on top of it)' % (label, len(deps), '' if len(deps) == 1 else 's'),
                  reverts=[entry_id] + deps)


def undo_group(db, ids, label=''):
    """Take back several changes (one operation's: a town's outside, its houses and doors) and every later change
    built on any of them, newest first, as one step."""
    _require_project(db)
    p = db.project
    by_id = {e['id']: e for e in p.log}
    ids = [i for i in ids if i in by_id and by_id[i].get('diff') and not by_id[i].get('undone')]
    if not ids:
        raise EditError('Those changes are no longer in effect.')
    live = _live(p)
    fps = {e['id']: _footprint(db, e) for e in live}
    group, low = set(ids), min(ids)
    for e in live:
        if e['id'] in group or e['id'] < low:
            continue
        if any(_builds_on(fps[e['id']], fps[g]) for g in group if g in fps):
            group.add(e['id'])
    for i in sorted(group, reverse=True):
        _revert_diff(p, by_id[i]['diff'])
    for i in group:
        _set_active(p, i, False)
    label = label or by_id[max(ids)]['text']
    return commit(db, 'Undid: %s (%d change%s)' % (label, len(group), '' if len(group) == 1 else 's'), reverts=sorted(group))


def undo_entry(db, entry_id):
    """Take back one change from the activity list, leaving later changes alone."""
    _require_project(db)
    p = db.project
    entry = next((e for e in p.log if e.get('id') == entry_id), None)
    if not entry:
        raise EditError('That change is no longer in the list.')
    if entry.get('undone'):
        raise EditError('That change has already been undone.')
    d = entry.get('diff')
    if not d:
        raise EditError('This change was made before per-change undo existed, so it can\'t be undone on its own.')
    # anything changed again since then?
    clashes = []
    for k, (_b, a) in d['r'].items():
        if p.records.get(k) != a:
            clashes.append(('r', k))
    for ck, cd in d['c'].items():
        cur = (p.cells.get(ck) or {}).get('refs', {})
        for rk, (_b, a) in cd['refs'].items():
            if cur.get(rk) != a:
                clashes.append(('c', ck, rk))
    if clashes:
        later = None
        for e in p.log:
            if e.get('id', 0) <= entry_id or e.get('undone') or not e.get('diff'):
                continue
            ed = e['diff']
            for c in clashes:
                hit = c[1] in ed['r'] if c[0] == 'r' else c[2] in ed['c'].get(c[1], {}).get('refs', {})
                if hit:
                    later = e
                    break
            if later:
                break
        if later:
            raise EditError('A later change also affects this: "%s" (%s). Undo that one first.' % (later['text'], later['t']))
        raise EditError('Something here has changed again since then, so it can\'t be undone on its own.')
    _revert_diff(p, d)
    _set_active(p, entry_id, False)
    text = entry['text']
    if text.startswith('Undid: '):
        new = commit(db, 'Redid: ' + text[len('Undid: '):], reverts=[entry_id])
    else:
        new = commit(db, 'Undid: ' + text, reverts=[entry_id])
    return new


def _encode_str(orig, value):
    enc = value.replace('\r\n', '\n').replace('\n', '\r\n').encode(ENC, 'replace')
    nul = orig.find(b'\0')
    if 0 <= nul < len(orig) - 1:          # fixed-size buffer: keep its length
        return enc[:len(orig) - 1].ljust(len(orig), b'\0')
    if orig.endswith(b'\0') or not orig:
        return enc + b'\0'
    return enc


def apply_changes(data, changes):
    subs = [[t, bytearray(d)] for t, d in iter_subrecords(data)]
    for ch in changes:
        n = int(ch['s'])
        if n >= len(subs) or subs[n][0] != ch['t']:
            raise EditError('The record changed underneath this edit. Reload it and try again.')
        d = subs[n][1]
        if ch['k'] == 'num':
            c, v = ch['c'], ch['value']
            try:
                v = float(v) if c in 'fd' else int(round(float(v)))
            except (TypeError, ValueError):
                raise EditError('"%s" is not a number.' % v)
            if c in INT_RANGES:
                lo, hi = INT_RANGES[c]
                if not lo <= v <= hi:
                    raise EditError('%s is out of range (%d to %d).' % (v, lo, hi))
            struct.pack_into('<' + c, d, int(ch['o']), v)
        else:
            subs[n][1] = bytearray(_encode_str(bytes(d), str(ch['value'])))
    return join_subs([(t, bytes(d)) for t, d in subs])


def _require_project(db):
    if not db.project:
        raise EditError('Create a mod project first.')


def _ensure_dial_copy(db, info_i):
    """INFO lines live under their topic, so the topic travels with them."""
    d = db.info_dial.get(info_i)
    if d is None:
        raise EditError('Could not find the topic this line belongs to.')
    dkey = db.recs[d][7]
    if 'DIAL|' + dkey in db.project.records:
        return
    dl = db.by_key[('DIAL', dkey)]
    w = [v for v in dl if v not in db.dead][-1]
    tag, flags, data = db.files[db.recs[w][3]].record_at(db.recs[w][4])
    db.project.set_record('DIAL', dkey, flags, data)


def edit_record(db, i, changes):
    _require_project(db)
    r = db.recs[i]
    tag, key, flags = r[0], r[7], r[6]
    if tag in ('CELL', 'LAND', 'PGRD'):
        raise EditError('Cells are edited on the World map.')
    _t, _f, data = db.files[r[3]].record_at(r[4])
    new = apply_changes(data, changes)
    if tag == 'INFO':
        _ensure_dial_copy(db, i)
    db.project.set_record(tag, key, flags, new)
    commit(db, 'Edited %s "%s"' % (tag, r[2] or r[1]))
    return db.overlay[(tag, key)]


def duplicate_record(db, i, new_id):
    _require_project(db)
    new_id = new_id.strip()
    r = db.recs[i]
    tag = r[0]
    if tag in NOT_COPYABLE:
        raise EditError('This kind of record cannot be used as a template yet.')
    if not new_id:
        raise EditError('Give the new record an ID.')
    if len(new_id.encode(ENC, 'replace')) > 31:
        raise EditError('IDs can be at most 31 characters.')
    if db.by_key.get((tag, new_id.lower())):
        raise EditError('Something with the ID "%s" already exists.' % new_id)
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs = []
    done = False
    for t, d in iter_subrecords(data):
        if t == 'NAME' and not done and tag != 'SCPT':
            d = zs(new_id)
            done = True
        elif t == 'SCHD' and tag == 'SCPT':
            d = new_id.encode(ENC, 'replace')[:31].ljust(32, b'\0') + bytes(d[32:])
        elif t == 'SCTX' and tag == 'SCPT':
            txt = bytes(d).decode(ENC, 'replace')
            txt = re.sub(r'(?im)^(\s*begin\s+)("?)[^\s"]+("?)', lambda m: m.group(1) + m.group(2) + new_id + m.group(3), txt, count=1)
            d = txt.encode(ENC, 'replace')
        subs.append((t, bytes(d)))
    db.project.set_record(tag, new_id.lower(), flags & ~0x20, join_subs(subs), created=True)
    commit(db, 'Created %s "%s" from template "%s"' % (tag, new_id, r[1]))
    return db.overlay[(tag, new_id.lower())]


def set_contents(db, i, items):
    """A container's contents (its NPCO list), as [{id, count, restock}], in place of what it holds now."""
    _require_project(db)
    r = db.recs[i]
    tag, key, flags = r[0], r[7], r[6]
    if tag != 'CONT':
        raise EditError('Only containers keep their contents this way.')
    _t, _f, data = db.files[r[3]].record_at(r[4])
    subs, at = [], None
    for t, d in iter_subrecords(data):
        if t == 'NPCO':
            if at is None:
                at = len(subs)
            continue
        subs.append((t, bytes(d)))
    new = []
    for it in (items or [])[:200]:
        iid = (it.get('id') or '').strip()
        if not iid:
            continue
        if db.resolve_id(iid) is None:
            raise EditError('No item called "%s".' % iid)
        n = max(1, min(2 ** 31 - 1, int(it.get('count') or 1)))
        new.append(('NPCO', struct.pack('<i', -n if it.get('restock') else n) + iid.encode(ENC, 'replace')[:31].ljust(32, b'\0')))
    at = len(subs) if at is None else at
    subs[at:at] = new
    db.project.set_record(tag, key, flags, join_subs(subs))
    commit(db, 'Changed what %s holds (%d kinds of things)' % (r[2] or r[1], len(new)))
    return db.overlay[(tag, key)]


def revert_record(db, i):
    _require_project(db)
    r = db.recs[i]
    tag, key = r[0], r[7]
    if tag == 'CELL':
        db.project.cells.pop(key, None)
    else:
        db.project.remove_record(tag, key)
        if tag == 'INFO':
            dk = key.split('|', 1)[0]
            if not any(k.startswith('INFO|' + dk + '|') for k in db.project.records):
                d = db.project.records.get('DIAL|' + dk)
                if d and not d.get('created'):
                    db.project.records.pop('DIAL|' + dk)
    commit(db, 'Undid changes to %s "%s"' % (tag, r[2] or r[1]))
    lst = db.by_key.get((tag, key))
    return lst[-1] if lst else None


def revert_cells(db, cells, land_only=True):
    """The mod's changes to these outdoor cells ('x,y') taken back at once, as one step (one Undo): the land (its
    heights and ground textures) and the grass on it; with land_only=False the objects and path grid too, a cell
    the mod made gone. (PIN2 wanted to pick cells and undo his terrain work in them, not change by change)"""
    _require_project(db)
    p = db.project
    n = 0
    for c in cells or []:
        gx, gy = (int(v) for v in str(c).lstrip('#').split(','))
        key = '#%d,%d' % (gx, gy)
        hit = p.records.pop('LAND|%d,%d' % (gx, gy), None) is not None
        if (getattr(p, 'grass', None) or {}).pop(key, None):
            hit = True
        if not land_only:
            if p.records.pop('PGRD|' + key, None) is not None:
                hit = True
            if p.cells.pop(key, None) is not None:
                hit = True
        n += hit
    if not n:
        raise EditError('None of your land is in %s.' % ('that cell' if len(cells or []) == 1 else 'those cells'))
    commit(db, 'Undid my land in %d cell%s' % (n, '' if n == 1 else 's'))
    return {'cells': n}


# ---------------- cells ----------------
def _cell(db, cell_key):
    _require_project(db)
    refs, header = db.cell_refs(cell_key)
    if header is None:
        if cell_key in db.project.cells:          # a place that exists only in this mod
            return db.project.cells[cell_key], refs
        # (outdoors, land with no cell: a mod such as a sea floor adds land only, and OpenMW makes up the cell. Shaped
        # into an island there, nothing could be put on it, "That cell does not exist", the user, 2026-10-29. The
        # cell is made as the game's unnamed outdoor cells are, in the land's region, as landscape.new_land does)
        m = re.match(r'#(-?\d+),(-?\d+)$', cell_key)
        if m:
            import landrange
            import landscape
            gx, gy = int(m.group(1)), int(m.group(2))
            if landscape._winner(db, gx, gy) is not None:
                hdr = [('NAME', b'\0'), ('DATA', struct.pack('<iii', 2, gx, gy))]
                region = landrange._region_of(db, gx, gy)
                ri = db.resolve_id(region) if region else None
                region = db.recs[ri][1] if ri is not None else region        # (the region's own spelling)
                if region:
                    hdr.append(('RGNN', zs(region)))
                c = db.project.cell(cell_key, hdr, 0)
                c['props'] = True
                return c, refs
        raise EditError('That cell does not exist in your load order.')
    c = db.project.cell(cell_key, header[0], header[1] & ~0x20)
    return c, refs


def name_cell(db, cell_key, name):
    """Name an outdoor cell (the name on the game's world map, its map window and saves); '' leaves it unnamed, as most
    of the game's outdoor cells are. Land with no cell gets its cell (_cell)."""
    if not re.match(r'#-?\d+,-?\d+$', cell_key or ''):
        raise EditError('Only outdoor cells are named here.')
    name = ' '.join(str(name or '').split())[:63]
    c, _refs = _cell(db, cell_key)
    hdr = [(t, unb64(d)) for t, d in c['header']]
    out = [(t, zs(name) if t == 'NAME' else d) for t, d in hdr]
    if not any(t == 'NAME' for t, _d in out):
        out.insert(0, ('NAME', zs(name)))
    c['header'] = [[t, b64(d)] for t, d in out]
    c['props'] = True
    db.sync_project()
    commit(db, ('Named cell %s "%s"' % (cell_key[1:], name)) if name else 'Took the name off cell %s' % cell_key[1:])
    return {'name': name}


def _store(c, refkey, origin, idx, subs, deleted=False):
    c['refs'][refkey] = {'origin': origin, 'idx': idx, 'subs': [[t, b64(d)] for t, d in subs], 'deleted': deleted}


def _same_turn(a, b):
    """Two (rx, ry, rz) that stand a thing the same way. The page works a thing's turn out anew from the view on every
    move, so the same turn can come back as other figures: the stances are compared, not the angles."""
    import math

    def m(r):
        cx, sx, cy, sy, cz, sz = (math.cos(r[0]), math.sin(r[0]), math.cos(r[1]), math.sin(r[1]),
                                  math.cos(r[2]), math.sin(r[2]))
        return (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx,
                sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx,
                -sy, cy * sx, cy * cx)
    return all(abs(p - q) < 1e-4 for p, q in zip(m(a), m(b)))


def move_ref(db, cell_key, refkey, pos, scale=None):
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    _rid, was_p, was_s, _gone = ref_info(ref['subs'])
    if len(pos) < 6:
        pos = list(pos) + list(was_p[len(pos):])
    # Every move, turn and new size of a thing is its own Undo step, named for what it was. They folded as "moves in a
    # row" until 2.7.1: a bottle moved, then turned, came back to where it began on one Undo (reported 2026-11-12; the
    # user: "they should be separate unless grouped by the button by the player").
    kind = ('turn' if not _same_turn(pos[3:6], was_p[3:6])
            else 'size' if scale is not None and abs(float(scale) - was_s) > 1e-4 else 'move')
    import doors
    was = doors.door_spots(db, [(cell_key, refkey)])
    _store(c, refkey, ref['origin'], ref['idx'], set_ref_pos(ref['subs'], tuple(pos[:6]), scale))
    rid = ref_info(ref['subs'])[0]
    note = '%s "%s" in %s' % ({'turn': 'Turned', 'size': 'Resized', 'move': 'Moved'}[kind], rid, cell_label(db, cell_key))
    commit(db, note)
    if was and doors.follow(db, was):
        fold(db, 2, note)
    return refkey


def delete_ref(db, cell_key, refkey):
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    rid = ref_info(ref['subs'])[0]
    if ref['origin'] == db.project.plugin.lower():
        c['refs'].pop(refkey, None)      # something you placed: just remove it
        if ref.get('src'):               # (a copy a merge brought in: remembered, so merging that mod again doesn't bring it back)
            c.setdefault('gone', []).append(ref['src'])
    else:
        _store(c, refkey, ref['origin'], ref['idx'], ref['subs'], deleted=True)
    _drop_empty(db, cell_key)
    commit(db, 'Removed "%s" from %s' % (rid, cell_label(db, cell_key)))


def place_ref(db, cell_key, obj_id, pos, scale=1.0, cut=None, extra_subs=None, note=None):
    import mapdata
    ri = db.resolve_id(obj_id)
    if ri is None:
        raise EditError('No object called "%s".' % obj_id)
    if db.recs[ri][0] not in PLACEABLE:
        raise EditError('"%s" is a %s, which cannot be placed in the world.' % (obj_id, db.recs[ri][0]))
    pos = (list(pos) + [0.0] * 6)[:6]
    pos = [0.0 if (v is None and n > 2) else v for n, v in enumerate(pos)]
    if pos[2] is None:
        m = mapdata.cellmap(db, cell_key)
        if not m.get('exists'):
            raise EditError('There is no cell at that spot.')
        pos[2] = mapdata.surface_z(db, m['refs'], m['interior'], pos[0], pos[1],
                                   mapdata.object_bounds(db, ri), scale or 1.0, db.recs[ri][0], cut)
    c, _refs = _cell(db, cell_key)
    rk = db.project.new_ref_key()
    origin, idx = rk.rsplit('|', 1)
    subs = [('NAME', zs(obj_id))] + list(extra_subs or [])
    subs = set_ref_pos(subs, tuple(pos), scale)
    _store(c, rk, origin, int(idx), subs)
    commit(db, note or 'Placed "%s" in %s' % (obj_id, cell_label(db, cell_key)))
    return rk


def swap_ref(db, cell_key, refkey, new_id):
    """Replace a placed object with a different one, keeping its spot, turn, scale and door link."""
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    ri = db.resolve_id(new_id)
    if ri is None:
        raise EditError('No object called "%s".' % new_id)
    if db.recs[ri][0] not in PLACEABLE:
        raise EditError('"%s" can\'t be placed in the world.' % new_id)
    old = ref_info(ref['subs'])[0]
    subs = [(t, zs(db.recs[ri][1]) if t == 'NAME' else d) for t, d in ref['subs']]
    if db.recs[ri][0] != 'DOOR':
        subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
    _store(c, refkey, ref['origin'], ref['idx'], subs)
    commit(db, 'Swapped "%s" for "%s" in %s' % (old, db.recs[ri][1], cell_label(db, cell_key)))
    return refkey


def secret_ref(db, cell_key, refkey, kind='door', save=True, sound=None):
    """Turn a placed piece of scenery (a wall, a bookcase) into a hidden door or an activator that looks
    just the same: a new DOOR or ACTI record in your mod with the piece's own model, and the placed
    piece swapped for it, keeping its spot and turn. A door can then be made to lead somewhere (or just
    swing open on its hinge); an activator is for a script. One record per model is reused.
    save=False leaves the commit to the caller (one change made of several steps: mechanism.py)."""
    _require_project(db)
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    old = ref_info(ref['subs'])[0]
    ri = db.resolve_id(old)
    if ri is None:
        raise EditError('No object called "%s".' % old)
    r = db.recs[ri]
    tag = 'ACTI' if kind == 'activator' else 'DOOR'
    if r[0] == tag:
        raise EditError('It already is %s.' % ('an activator' if tag == 'ACTI' else 'a door'))
    if r[0] not in ('STAT', 'ACTI', 'DOOR', 'CONT', 'LIGH', 'MISC'):
        raise EditError('Only something with a model (a wall, a bookcase, a rock, a log pile) can be made into one.')
    _t, _f, data = db.files[r[3]].record_at(r[4])
    model = next((zstr(d) for t, d in iter_subrecords(data) if t == 'MODL'), None)
    if not model:
        raise EditError('"%s" has no model.' % r[1])
    name = next((zstr(d) for t, d in iter_subrecords(data) if t == 'FNAM'), None) or (r[2] or '').strip()
    if not name:
        import mechanism
        name = mechanism.nice_name(r[1]) or 'Wall'
    # (one made before, for the same model and kind, is used again)
    suffix = '_hidden' if tag == 'DOOR' else '_acti'
    base = re.sub(r'_(hidden|acti)(_\d+)?$', '', r[1])          # (a door made this way, turned into an activator)
    stem = base[:31 - len(suffix)] + suffix
    new_id = db.recs[db.by_key[(tag, stem.lower())][-1]][1] if db.by_key.get((tag, stem.lower())) else None
    if new_id is None:
        from library import DOOR_SOUNDS
        new_id, n = stem, 2
        while db.resolve_id(new_id) is not None:
            new_id = '%s_%d' % (stem[:31 - 2 - len(str(n))], n)
            n += 1
        subs = [('NAME', zs(new_id)), ('MODL', zs(model)), ('FNAM', zs(name[:31]))]
        if tag == 'DOOR':
            snd = sound if sound in DOOR_SOUNDS else 'wood' if re.search(r'wood|plank|thatch', model, re.I) else 'stone'
            for sub, sid in zip(('SNAM', 'ANAM'), DOOR_SOUNDS[snd]):
                if db.resolve_id(sid) is not None:
                    subs.append((sub, zs(sid)))
        db.project.set_record(tag, new_id.lower(), 0, join_subs(subs), created=True)
        db.sync_project()
    ni = db.resolve_id(new_id)
    subs = [(t, zs(db.recs[ni][1]) if t == 'NAME' else d) for t, d in ref['subs']]
    if tag != 'DOOR':
        subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
    _store(c, refkey, ref['origin'], ref['idx'], subs)
    if save:
        commit(db, 'Made "%s" into %s "%s" in %s' % (old, 'the activator' if tag == 'ACTI' else 'the hidden door',
                                                     new_id, cell_label(db, cell_key)))
    return {'id': new_id, 'type': tag, 'ref': refkey}


def restore_ref(db, cell_key, refkey):
    _require_project(db)
    c = db.project.cells.get(cell_key)
    if c:
        c['refs'].pop(refkey, None)
    _drop_empty(db, cell_key)
    commit(db, 'Restored an object in %s' % cell_label(db, cell_key))


def _drop_empty(db, cell_key):
    c = db.project.cells.get(cell_key)
    if c is not None and not c['refs']:
        db.project.cells.pop(cell_key)


def cell_label(db, cell_key):
    lst = db.by_key.get(('CELL', cell_key))
    return db.recs[lst[-1]][1] if lst else cell_key
