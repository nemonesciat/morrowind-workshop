"""Other modding programs working with the Workshop's open mod: the OpenMW Suite for Blender and Maya first.

The Workshop's open mod is the main copy. A program asks once to connect (POST /bridge/hello); the user says Allow in
the Workshop's window, and the program gets a key of its own. From then on what it sends goes into the open mod like a
second Workshop window's work: it joins the user's unsaved changes, one Undo each, marked with the program's name in
My changes, and the user's Save writes it all. (The user, 2026-11-25: "Join my unsaved work". Coding agents and
scripts stay refused while anything is unsaved: editing.refuse_external.)

What a program can do (docs/bridge-api.md says it for the program's own authors):
  status        the Workshop's version, the open mod, whether anything is unsaved, the program's block of numbers
  changes       what changed since change n (the second window's own list: editing.CHANGES)
  snapshot      the open mod written to disk with the unsaved work in it (Play here's test copy), to read
  place / move / delete    objects, a new one under the number the program gave it from its own block
  file          a model, animation, picture or sound copied into the mod's folder
  scene         a cutscene (openmw-scene/1) kept in the mod, checked
  action        any of the Workshop's own actions, as the page would ask it (the list: actions)

Finding the Workshop: a running Workshop writes running.json in a fixed folder (%LOCALAPPDATA%\\Morrowind Workshop
on Windows, ~/.local/share/morrowind-workshop elsewhere): its address, its own folder and its version."""
import json
import os
import re
import secrets
import shutil
import threading
import time

import editing
from editing import EditError
import project as _projmod
from project import load_settings, save_settings

API = 1                              # the bridge's own version: raised when a call changes
SCENE_FORMAT = 'openmw-scene/1'
MARK = '⇄ '                     # (a program's change in My changes: "⇄ OpenMW Suite (Blender): Placed ...")
BLOCK = 2_000_000                    # numbers for a program's new objects (as Build together's people: together.BLOCK)
TOP = 16_000_000                     # (blocks from the top down: the game counts to 16.7 million, the mod from 1 up)
FILE_FOLDERS = ('meshes', 'textures', 'icons', 'bookart', 'sound', 'music', 'splash', 'video', 'fonts')
FILE_KINDS = {'.nif', '.kf', '.dds', '.tga', '.bmp', '.png', '.jpg', '.wav', '.mp3', '.ogg', '.bik', '.fnt', '.tex'}
CELL = 8192

ASKS = {}                            # request id -> {'program', 'version', 'state', 'key', 't'}
LOCK = threading.Lock()
SEEN = {}                            # program key -> {'last', 'calls', 'what'}


# ------------------------------------------------------------------ where a running Workshop says it is
def pointer_path():
    p = os.environ.get('WORKSHOP_BRIDGE_POINTER')
    if p:
        return p
    if os.environ.get('WORKSHOP_HOME'):
        return None                  # (a test server or another program's engine copy: never the user's pointer)
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        return os.path.join(base, 'Morrowind Workshop', 'running.json')
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'morrowind-workshop', 'running.json')


def announce(port):
    """Write running.json for other programs to find this Workshop (and take it away at exit)."""
    p = pointer_path()
    if not p:
        return
    try:
        import helpinfo
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'port': port, 'url': 'http://127.0.0.1:%d/' % port,
                       'bridge': 'http://127.0.0.1:%d/bridge/' % port, 'bridge_api': API,
                       'version': helpinfo.version(), 'home': _projmod.APP_DIR}, f)
        import atexit
        atexit.register(_forget, p)
    except OSError as e:
        print('could not write', p, e)


def _forget(p):
    try:
        with open(p, encoding='utf-8') as f:
            if json.load(f).get('pid') != os.getpid():
                return
        os.remove(p)
    except (OSError, ValueError):
        pass


# ------------------------------------------------------------------ programs and their keys
def programs():
    return [dict(x) for x in load_settings().get('bridge_programs') or []]


def _save_programs(lst):
    s = load_settings()
    s['bridge_programs'] = lst
    save_settings(s)


def _by_key(key):
    if not key:
        return None
    for p in programs():
        if p.get('key') and secrets.compare_digest(str(p['key']), str(key)):
            return p
    return None


def _free_block(lst):
    used = {p.get('block') for p in lst}
    for n in range(1, 6):
        lo = TOP - n * BLOCK
        if lo not in used:
            return lo
    raise EditError('Too many programs are connected: remove one in the Workshop first.')


def hello(program, version=''):
    """A program asks to connect: the user is asked in the Workshop's window. Returns the request's id."""
    program = re.sub(r'\s+', ' ', str(program or '')).strip()[:60]
    if not program:
        raise EditError('Say which program is asking ("program").')
    now = time.time()
    with LOCK:
        for k in [k for k, a in ASKS.items() if now - a['t'] > 600]:
            ASKS.pop(k)
        for k, a in ASKS.items():
            if a['program'] == program and a['state'] == 'waiting':
                a['t'] = now
                return {'id': k, 'state': 'waiting'}
        if sum(1 for a in ASKS.values() if a['state'] == 'waiting') >= 3:
            raise EditError('Too many programs are waiting for an answer in the Workshop.')
        rid = secrets.token_hex(8)
        ASKS[rid] = {'program': program, 'version': str(version or '')[:40], 'state': 'waiting', 'key': None, 't': now}
    return {'id': rid, 'state': 'waiting'}


def hello_state(rid):
    """waiting / allowed (with the key, given once) / refused / unknown."""
    with LOCK:
        a = ASKS.get(rid or '')
        if not a:
            return {'state': 'unknown'}
        if a['state'] == 'allowed' and a.get('key'):
            key, a['key'] = a['key'], None
            ASKS.pop(rid, None)
            p = _by_key(key) or {}
            return {'state': 'allowed', 'key': key, 'block': [p.get('block'), p.get('block', 0) + BLOCK - 1]}
        return {'state': a['state']}


def asks():
    """For the window: programs waiting for the user's answer."""
    with LOCK:
        return [{'id': k, 'program': a['program'], 'version': a['version']} for k, a in ASKS.items() if a['state'] == 'waiting']


def answer(rid, allow):
    with LOCK:
        a = ASKS.get(rid or '')
        if not a or a['state'] != 'waiting':
            raise EditError('That request is no longer waiting.')
        if not allow:
            a['state'] = 'refused'
            return {'ok': True}
        lst = [p for p in programs() if p.get('name') != a['program']]
        old = next((p for p in programs() if p.get('name') == a['program']), None)
        key = secrets.token_urlsafe(24)
        lst.append({'name': a['program'], 'key': key, 'version': a['version'], 'since': time.time(),
                    'block': (old or {}).get('block') or _free_block(lst)})
        _save_programs(lst)
        a['state'], a['key'] = 'allowed', key
    return {'ok': True}


def remove(name):
    _save_programs([p for p in programs() if p.get('name') != name])
    return listing()


def listing():
    now = time.time()
    out = []
    for p in programs():
        s = SEEN.get(p['name']) or {}
        out.append({'name': p['name'], 'version': p.get('version') or '', 'since': p.get('since'),
                    'last': round(now - s['last']) if s.get('last') else None, 'calls': s.get('calls', 0)})
    return out


# ------------------------------------------------------------------ what a program asks
def _need_mod(db):
    if db.project is None:
        raise EditError('No mod is open in the Workshop.')
    if db.state != 'ready':
        raise EditError('The Workshop is still loading: try again in a moment.')
    return db.project


def status(db, prog):
    import helpinfo
    p = db.project
    since = editing.unsaved(db) if p else None
    import scenes as _sc
    return {'bridge_api': API, 'workshop': helpinfo.version(), 'scene_format': SCENE_FORMAT, 'scene_player': _sc.VERSION,
            'lua_slug': p.lua_slug() if p else None, 'lua_ok': bool(p and p.lua_allowed()),
            'program': prog['name'], 'block': [prog['block'], prog['block'] + BLOCK - 1],
            'ready': db.state == 'ready',
            'mod': None if p is None else {'name': p.name, 'plugin': os.path.basename(editing.plugin_path(db)),
                                           'folder': os.path.dirname(editing.plugin_path(db)),
                                           'unsaved': bool(since), 'unsaved_since': since,
                                           'masters': list(getattr(db, 'proj_masters', None) or [])},
            'changes': editing.CHANGES['n']}


def changes(db, since):
    out = editing.changes_since(int(since or 0))
    p = db.project
    out['mod'] = p.plugin if p else None
    out['unsaved'] = bool(editing.unsaved(db)) if p else False
    return out


def snapshot(db):
    """The open mod on disk as it is now. With nothing unsaved: the mod's own file. With unsaved work: Play here's
    test copy (a folder of the Workshop's own, never the mod's) - read it, don't keep it: the next snapshot or Play
    here writes it again."""
    p = _need_mod(db)
    folder = editing.play_copy(db)
    plugin = os.path.basename(editing.plugin_path(db))
    if folder is None:
        return {'unsaved': False, 'plugin': editing.plugin_path(db), 'folder': os.path.dirname(editing.plugin_path(db)),
                'changes': editing.CHANGES['n']}
    return {'unsaved': True, 'plugin': os.path.join(folder, plugin), 'folder': folder, 'changes': editing.CHANGES['n'],
            'note': 'A test copy with the unsaved work in it; the mod itself is in %s.' % os.path.dirname(editing.plugin_path(db))}


def cell_key(cell):
    """[x, y] or "#x,y" -> "#x,y"; an interior's name as it is."""
    if isinstance(cell, (list, tuple)) and len(cell) == 2:
        return '#%d,%d' % (int(cell[0]), int(cell[1]))
    c = str(cell or '').strip()
    if not c:
        raise EditError('Say which cell ("cell": [x, y] outdoors, or an interior\'s name).')
    return c if c.startswith('#') else c.lower()          # (the Workshop knows interiors by their name in lower case)


def ref_key(ref):
    """{"file", "index"} or "file|index" -> the Workshop's key for a placed object."""
    if isinstance(ref, dict):
        f, i = ref.get('file') or ref.get('plugin'), ref.get('index')
        if not f or i is None:
            raise EditError('An object is {"file": plugin, "index": number}.')
        return '%s|%d' % (str(f).lower(), int(i))
    s = str(ref or '')
    if '|' not in s:
        raise EditError('An object is {"file": plugin, "index": number}.')
    return s.lower()


def _as_ref(k):
    f, i = k.rsplit('|', 1)
    return {'file': f, 'index': int(i)}


def _pos(body, place=False):
    """"pos": [x, y, z] or [x, y, z, rx, ry, rz]: game units, turns in degrees ("degrees": false for radians).
    A new object's z may be null: it is set down on what is under it."""
    raw = body.get('pos')
    if not isinstance(raw, (list, tuple)) or len(raw) < 3 or len(raw) > 6:
        raise EditError('"pos" is [x, y, z] or [x, y, z, rx, ry, rz] (game units, turns in degrees).')
    try:
        pos = [None if (v is None and n == 2 and place) else float(v) for n, v in enumerate(raw)]
    except (TypeError, ValueError):
        raise EditError('"pos" holds numbers.')
    if len(pos) > 3 and body.get('degrees', True):
        pos = pos[:3] + [v * 3.141592653589793 / 180 for v in pos[3:]]
    return pos


def _number_used(p, n):
    k = '%s|%d' % (p.plugin.lower(), n)
    return any(k in (c.get('refs') or {}) for c in p.cells.values())


def place(db, prog, body):
    p = _need_mod(db)
    key = cell_key(body.get('cell'))
    pos = _pos(body, place=True)
    n = body.get('index')
    if n is not None:
        n = int(n)
        lo = prog['block']
        if not lo <= n < lo + BLOCK:
            raise EditError('Index %d is outside your block (%d to %d).' % (n, lo, lo + BLOCK - 1))
        if _number_used(p, n):
            raise EditError('Index %d is already used in this mod.' % n)
        _projmod.WANT_REF.n = n
    try:
        rk = editing.place_ref(db, key, str(body.get('id') or ''), pos, float(body.get('scale') or 1.0))
    finally:
        _projmod.WANT_REF.n = None
    return {'ref': _as_ref(rk), 'cell': key}


def move(db, body):
    _need_mod(db)
    key = cell_key(body.get('cell'))
    pos = _pos(body)
    rk = ref_key(body.get('ref'))
    editing.move_ref(db, key, rk, pos, body.get('scale'))
    return {'ref': _as_ref(rk), 'cell': key}


def delete(db, body):
    _need_mod(db)
    key = cell_key(body.get('cell'))
    rk = ref_key(body.get('ref'))
    editing.delete_ref(db, key, rk)
    return {'ref': _as_ref(rk), 'cell': key, 'deleted': True}


RECORD_TAGS = {'ACTI', 'ALCH', 'APPA', 'ARMO', 'BODY', 'BOOK', 'BSGN', 'CLAS', 'CLOT', 'CONT', 'CREA', 'DOOR', 'ENCH',
               'FACT', 'GLOB', 'INGR', 'LAND', 'LEVC', 'LEVI', 'LIGH', 'LOCK', 'LTEX', 'MISC', 'NPC_', 'PGRD', 'PROB',
               'RACE', 'REGN', 'REPA', 'SCPT', 'SNDG', 'SOUN', 'SPEL', 'STAT', 'WEAP'}


def _record_key(tag, rid, subs):
    """The Workshop's key for a record: its ID in lower case; a LAND's "x,y" (from INTV); a PGRD's cell key."""
    import struct
    if tag == 'LAND':
        d = next((d for t, d in subs if t == 'INTV'), None)
        if not d or len(d) < 8:
            raise EditError('A LAND record needs its INTV (the cell\'s x and y).')
        x, y = struct.unpack_from('<ii', d)
        return '%d,%d' % (x, y)
    if tag == 'PGRD':
        return cell_key(rid)
    from project import zstr
    name = next((zstr(d) for t, d in subs if t == 'NAME'), '')
    if not name:
        raise EditError('A %s record needs its NAME.' % tag)
    if rid and str(rid).lower() != name.lower():
        raise EditError('"id" is %s but the record\'s NAME is %s.' % (rid, name))
    return name.lower()


def put_record(db, body):
    """A record as the program writes it: {"type": "NPC_", "id": "mi_flima", "flags": 0, "subs": [["NAME", base64], ...]}.
    For LAND (the cell's heights, texture paint, vertex colours) the INTV says which cell; for PGRD "id" is the cell
    ([x, y] or an interior's name). Replaces the mod's own version of the record, or overrides the game's."""
    import base64
    from project import join_subs
    p = _need_mod(db)
    tag = str(body.get('type') or '').upper()
    if tag not in RECORD_TAGS:
        raise EditError('"type" is one of: %s.' % ' '.join(sorted(RECORD_TAGS)))
    raw = body.get('subs')
    if not isinstance(raw, list) or not raw:
        raise EditError('"subs" is the record\'s subrecords: [["NAME", "<base64>"], ...], in order.')
    subs = []
    for s in raw:
        if not (isinstance(s, (list, tuple)) and len(s) == 2 and isinstance(s[0], str) and len(s[0]) == 4):
            raise EditError('Each subrecord is ["TAG", "<base64>"].')
        try:
            subs.append((s[0], base64.b64decode(s[1] or '', validate=True)))
        except Exception:
            raise EditError('Subrecord %s is not base64.' % s[0])
    key = _record_key(tag, body.get('id'), subs)
    game = any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get((tag, key), []))
    had = (tag + '|' + key) in p.records
    p.set_record(tag, key, int(body.get('flags') or 0) & ~0x20, join_subs(subs), created=not game)
    db.sync_project()
    label = {'LAND': 'the land of cell (%s)' % key, 'PGRD': 'the path grid of %s' % key}.get(tag, '%s "%s"' % (tag, body.get('id') or key))
    editing.commit(db, ('Changed %s' if (had or game) else 'Made %s') % label)
    return {'type': tag, 'key': key, 'made': not (had or game)}


def drop_record(db, body):
    """Take back the mod's version of a record: one it made is removed, one it changed goes back to the game's."""
    p = _need_mod(db)
    tag = str(body.get('type') or '').upper()
    key = cell_key(body.get('id')) if tag == 'PGRD' else str(body.get('id') or '').lower()
    if tag == 'LAND' and isinstance(body.get('id'), (list, tuple)):
        key = '%d,%d' % (int(body['id'][0]), int(body['id'][1]))
    if (tag + '|' + key) not in p.records:
        raise EditError('The mod has no %s "%s".' % (tag, key))
    p.remove_record(tag, key)
    db.sync_project()
    editing.commit(db, 'Took back %s "%s"' % (tag, key))
    return {'type': tag, 'key': key, 'removed': True}


def ref_fields(db, body):
    """An object's details beyond where it stands: {"cell", "ref", "owner", "faction", "rank", "global", "soul", "lock",
    "key", "trap", "uses", "charge"} (as the Workshop's own object window has them; fields left out stay as they are)
    and "door": {"cell": [x, y] or an interior's name, "pos": [x, y, z, rx, ry, rz]} (degrees) or null for none."""
    import math
    import struct
    import refprops
    from project import zs
    _need_mod(db)
    key = cell_key(body.get('cell'))
    rk = ref_key(body.get('ref'))
    fields = {k: body[k] for k in ('owner', 'faction', 'rank', 'global', 'soul', 'lock', 'key', 'trap', 'uses', 'charge')
              if k in body}
    changed, notes = False, []
    if fields:
        now = refprops.read(db, key, rk)
        n = refprops.save(db, key, rk, dict(now or {}, **fields), save=False)
        if n:
            notes.append(n)
            db.sync_project()                          # (the door below reads the object with these details in)
        changed = True
    if 'door' in body:
        c, refs = editing._cell(db, key)
        ref = refs.get(rk)
        if not ref:
            raise EditError('That object is no longer in this cell.')
        subs = [(t, d) for t, d in ref['subs'] if t not in ('DODT', 'DNAM')]
        dr = body.get('door')
        if dr:
            pos = [float(v) for v in (dr.get('pos') or [])]
            if len(pos) not in (3, 6):
                raise EditError('"door": {"cell", "pos": [x, y, z, rx, ry, rz]}.')
            pos = (pos + [0, 0, 0])[:6]
            pos = pos[:3] + [math.radians(v) for v in pos[3:]]
            # (after the owner, before the lock and DATA, as the game writes refs: refprops.save's order)
            at = next((i for i, (t, _d) in enumerate(subs) if t in ('FLTV', 'KNAM', 'TNAM', 'UNAM', 'DATA')), len(subs))
            add = [('DODT', struct.pack('<6f', *pos))]
            dc = dr.get('cell')
            if isinstance(dc, str) and dc.strip():
                add.append(('DNAM', zs(dc.strip())))
            subs[at:at] = add
        editing._store(c, rk, ref['origin'], ref['idx'], subs)
        notes.append('Set where a door leads in %s' % editing.cell_label(db, key))
        changed = True
    if not changed:
        raise EditError('Nothing to change: give the fields, or "door".')
    if notes:
        editing.commit(db, '; '.join(notes))           # (one change, one Undo, however many details)
    return {'ref': _as_ref(rk), 'cell': key}


CELL_TAGS = ('NAME', 'DATA', 'RGNN', 'NAM5', 'WHGT', 'INTV', 'AMBI')


def put_cell(db, body):
    """An interior's header, as the program writes it: {"cell": its name, "subs": [["NAME", b64], ["DATA", b64],
    ["AMBI", b64], ["WHGT", b64]...]}. A new interior is made in the mod (empty: place things in it after); one that
    exists (the game's or the mod's) gets this header: its light, water and flags come from it.
    Outdoors, a cell's name goes through the Workshop's own action (/api/cell/name)."""
    import base64
    import struct
    from project import b64, zs, zstr
    p = _need_mod(db)
    raw = body.get('cell')
    name = '' if isinstance(raw, (list, tuple)) else str(raw or '').strip()
    if not name or name.startswith('#'):
        raise EditError('"cell" is an interior\'s name (outdoors, a cell\'s name goes through /api/cell/name).')
    if len(name.encode('cp1252', 'replace')) > 63:
        raise EditError('An interior\'s name can be at most 63 characters.')
    subs = []
    for s in body.get('subs') or []:
        if not (isinstance(s, (list, tuple)) and len(s) == 2 and s[0] in CELL_TAGS):
            raise EditError('"subs" are the cell header\'s subrecords, of: %s.' % ' '.join(CELL_TAGS))
        try:
            subs.append((s[0], base64.b64decode(s[1] or '', validate=True)))
        except Exception:
            raise EditError('Subrecord %s is not base64.' % s[0])
    have = dict(subs)
    if have.get('NAME') is not None and zstr(have['NAME']).lower() != name.lower():
        raise EditError('"cell" is %s but the header\'s NAME is %s.' % (name, zstr(have['NAME'])))
    if 'DATA' in have and (len(have['DATA']) < 12 or not struct.unpack_from('<i', have['DATA'])[0] & 1):
        raise EditError('The header\'s DATA must say it is an interior (flag 1).')
    # (always a NAME, an interior DATA and an AMBI, in the game's order)
    out = [('NAME', zs(name)), ('DATA', have.get('DATA') or struct.pack('<Iii', 1, 0, 0))]
    for t in ('RGNN', 'NAM5', 'WHGT', 'INTV'):
        if t in have:
            out.append((t, have[t]))
    out.append(('AMBI', have.get('AMBI') or struct.pack('<IIIf', 0x404040, 0x505050, 0x202020, 0.5)))
    key = name.lower()
    exists = any(v not in db.dead for v in db.by_key.get(('CELL', key), []))
    if key in p.cells or exists:
        c = p.cells[key] if key in p.cells else editing._cell(db, key)[0]
        c['header'] = [[t, b64(d)] for t, d in out]
        c['props'] = True
        what = 'Changed the light and water of "%s"' % name
    else:
        p.cells[key] = {'flags': 0, 'header': [[t, b64(d)] for t, d in out], 'refs': {}}
        what = 'Made the interior "%s"' % name
    db.sync_project()
    editing.commit(db, what)
    return {'cell': key, 'made': what.startswith('Made')}


def take_file(db, body):
    """A file from this PC into the mod's folder, under the path the game will look for it ("to": meshes/...).
    Files aren't held for Save: they go in at once, as the Library's do. The same file again is nothing to do; a
    different one already there is kept unless "replace" is true (the one there then goes to the Workshop's own
    folder, cache/replaced files, the last five of each: never kept in the mod's folder)."""
    _need_mod(db)
    src = str(body.get('path') or '')
    if not src or not os.path.isfile(src):
        raise EditError('There is no file at "%s".' % src)
    to = str(body.get('to') or '').replace('\\', '/').strip('/')
    parts = [x for x in to.split('/') if x]
    if not parts or parts[0].lower() not in FILE_FOLDERS or any(x in ('.', '..') for x in parts) or ':' in to:
        raise EditError('"to" is a path in the game\'s data, starting with one of: %s.' % ', '.join(FILE_FOLDERS))
    if os.path.splitext(parts[-1])[1].lower() not in FILE_KINDS:
        raise EditError('Only models, animations, pictures, sounds and videos: %s.' % ' '.join(sorted(FILE_KINDS)))
    root = os.path.dirname(editing.plugin_path(db))
    dst = os.path.join(root, *parts)
    if os.path.abspath(dst) == os.path.abspath(src):
        return {'to': '/'.join(parts), 'path': dst, 'same': True}
    kept = None
    if os.path.exists(dst):
        if _same_file(src, dst):
            # (the same file sent again, as a program's every Save sends its models: nothing to do)
            return {'to': '/'.join(parts), 'path': dst, 'same': True, 'kept': None}
        if not body.get('replace'):
            raise EditError('%s is already in the mod: send "replace": true to put this one in its place.' % '/'.join(parts))
        # (the one replaced is kept in the Workshop's own folder, never the mod's: the last five of each)
        kept_dir = os.path.join(_projmod.APP_DIR, 'cache', 'replaced files', re.sub(r'[^\w. -]+', '_', db.project.name), *parts[:-1])
        os.makedirs(kept_dir, exist_ok=True)
        kept = os.path.join(kept_dir, parts[-1] + '.' + time.strftime('%Y%m%d-%H%M%S'))
        shutil.move(dst, kept)
        olds = sorted(f for f in os.listdir(kept_dir) if f.startswith(parts[-1] + '.'))
        for f in olds[:-5]:
            try:
                os.remove(os.path.join(kept_dir, f))
            except OSError:
                pass
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return {'to': '/'.join(parts), 'path': dst, 'kept': kept}


def _same_file(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, 'rb') as fa, open(b, 'rb') as fb:
            while True:
                x, y = fa.read(1 << 20), fb.read(1 << 20)
                if x != y:
                    return False
                if not x:
                    return True
    except OSError:
        return False


# ------------------------------------------------------------------ scenes
def _cell_of(x, y):
    return int(x // CELL), int(y // CELL)


def check_scene(db, sc):
    """Problems with a scene, as [{'level': 'error'|'warning', 'text'}]. Unknown fields are kept and not judged."""
    out = []

    def bad(t, level='error'):
        out.append({'level': level, 'text': t})
    if not isinstance(sc, dict):
        return [{'level': 'error', 'text': 'A scene is a JSON object.'}]
    if sc.get('format') != SCENE_FORMAT:
        bad('"format" is "%s".' % SCENE_FORMAT)
    sid = sc.get('scene') or sc.get('id')
    if not sid or not re.match(r'^[A-Za-z0-9_]{1,40}$', str(sid)):
        bad('"scene" is the scene\'s id: letters, numbers and _ (at most 40).')
    cell = sc.get('cell')
    grid = None
    if isinstance(cell, (list, tuple)) and len(cell) == 2:
        grid = (int(cell[0]), int(cell[1]))
    elif not (isinstance(cell, str) and cell.strip()):
        bad('"cell" is [x, y] outdoors, or an interior\'s name.')
    elif db.recs and ('CELL', cell.strip().lower()) not in db.by_key and cell.strip() not in (db.project.cells if db.project else {}):
        bad('There is no interior called "%s".' % cell, 'warning')
    try:
        length = float(sc.get('length'))
        if length <= 0:
            raise ValueError
    except (TypeError, ValueError):
        bad('"length" is the scene\'s length in seconds.')
        length = None

    def where(name, p):
        if grid and isinstance(p, (list, tuple)) and len(p) >= 2:
            c = _cell_of(float(p[0]), float(p[1]))
            if abs(c[0] - grid[0]) > 1 or abs(c[1] - grid[1]) > 1:
                bad('%s is in cell %s, not beside the scene\'s cell %s.' % (name, list(c), list(grid)), 'warning')
            elif c != grid:
                bad('%s is in the next cell, %s (the scene\'s is %s).' % (name, list(c), list(grid)), 'warning')
    keys = set()
    for a in sc.get('actors') or []:
        if not isinstance(a, dict) or not a.get('key'):
            bad('Each actor has a "key" the rest of the scene calls it by.')
            continue
        keys.add(a['key'])
        if a.get('ref'):
            try:
                rk = ref_key(a['ref'])
            except EditError as e:
                bad('%s: %s' % (a['key'], e))
                continue
            if grid:
                refs, _h = db.cell_refs('#%d,%d' % grid)
                if rk not in refs:
                    bad('%s: no object %s in the scene\'s cell.' % (a['key'], rk), 'warning')
        elif a.get('id'):
            if db.resolve_id(str(a['id'])) is None:
                bad('%s: there is no "%s".' % (a['key'], a['id']))
            if a.get('pick') not in (None, 'nearest'):
                bad('%s: "pick" is "nearest".' % a['key'])
        else:
            bad('%s: an actor is a placed object ("ref": {"file", "index"}) or "id" with "pick": "nearest".' % a['key'])
        for c in a.get('clips') or []:
            if not isinstance(c, dict) or not c.get('group'):
                bad('%s: each clip names its animation "group".' % a['key'])
    keys.add('player')
    marks = sc.get('marks') or {}
    for m, v in marks.items() if isinstance(marks, dict) else []:
        if not (isinstance(v, (list, tuple)) and len(v) in (3, 4)):
            bad('Mark %s is [x, y, z] or [x, y, z, yaw].' % m)
        else:
            where('Mark %s' % m, v)
    for s in sc.get('shots') or []:
        nm = 'Shot "%s"' % (s.get('name') or s.get('at'))
        if 'pos' in s and ('aim' in s or 'offset' in s or 'from' in s):
            bad('%s: a fixed shot has "pos", an aimed one "aim" with "offset" or "from"; never both.' % nm)
        if 'pos' in s:
            where(nm, s['pos'])
        for part in ('aim', 'from'):
            t = s.get(part)
            if isinstance(t, dict) and t.get('actor') and t['actor'] not in keys:
                bad('%s: no actor "%s".' % (nm, t['actor']))
        if length is not None and isinstance(s.get('at'), (int, float)) and not 0 <= s['at'] <= length:
            bad('%s starts outside the scene (0 to %g s).' % (nm, length), 'warning')
    for ln in sc.get('lines') or []:
        who = ln.get('who') or ln.get('actor')
        if who and who not in keys:
            bad('Line "%s": no actor "%s".' % (str(ln.get('text'))[:30], who))
        v = str(ln.get('voice') or '')
        if v and not v.lower().replace('\\', '/').startswith('sound/'):
            bad('Line "%s": voices are full data paths, such as Sound/Vo/... (core.sound.say).' % str(ln.get('text'))[:30], 'warning')
    end = sc.get('end')
    if not isinstance(end, dict) or not isinstance(end.get('do'), list):
        bad('"end" holds "do": what happens when the scene ends (it always runs: on finishing, skip, load or a missing actor).')
    return out


def put_scene(db, sc):
    p = _need_mod(db)
    problems = check_scene(db, sc)
    if any(x['level'] == 'error' for x in problems):
        return {'kept': False, 'problems': problems}
    sid = str(sc.get('scene') or sc.get('id'))
    new = sid not in (p.scenes or {})
    old = (p.scenes or {}).get(sid) or {}
    if 'trigger' not in sc and old.get('trigger'):
        sc = dict(sc, trigger=old['trigger'])            # (what starts it is the user's choice, made in the Workshop)
    tr = sc.get('trigger')
    if isinstance(tr, dict) and tr.get('kind') == 'dialogue':
        # (the scene maker's "After a line of dialogue": a global of its own that the line sets)
        sc = dict(sc, trigger={'kind': 'global', 'name': scene_global(db, sid), 'value': 1, 'once': tr.get('once', True), 'from': 'dialogue'})
    p.scenes = dict(p.scenes or {})
    p.scenes[sid] = sc
    import scenes as _sc
    _sc.movie_records(db)                            # (a movie cue needs a little MWScript: PlayBink isn't in Lua)
    editing.commit(db, ('Added scene "%s"' if new else 'Changed scene "%s"') % (sc.get('name') or sid))
    return {'kept': True, 'scene': sid, 'problems': problems}


TRIGGERS = {'area': 'the player comes near a spot', 'quest': 'a quest reaches a stage',
            'global': 'a global variable is set (a dialogue result or MWScript: set <name> to 1)',
            'dialogue': 'a line of dialogue says so'}


def scene_global(db, sid):
    """The global variable a line of dialogue sets to start a scene (made in the mod when missing)."""
    import struct
    from project import join_subs, zs
    p = db.project
    gv = ('ws' + p.lua_slug()[:12] + '_' + re.sub(r'[^a-z0-9_]', '', sid.lower()))[:31]
    if db.resolve_id(gv) is None:
        p.set_record('GLOB', gv.lower(), 0, join_subs([('NAME', zs(gv)), ('FNAM', b's'), ('FLTV', struct.pack('<f', 0.0))]),
                     created=True)
        db.sync_project()
    return gv


def set_trigger(db, sid, tr):
    """What starts a scene, chosen by the user in the Workshop: {'kind': 'area', 'center': [x, y, z], 'radius',
    'cell'?, 'once'} / {'kind': 'quest', 'quest', 'stage', 'once'} / {'kind': 'global', 'name', 'value', 'once'};
    None: only another script or program starts it (the event WsScene_Play)."""
    p = _need_mod(db)
    sc = (p.scenes or {}).get(sid or '')
    if sc is None:
        raise EditError('No scene "%s" in this mod.' % sid)
    if tr and tr.get('kind') == 'dialogue':
        # (a line's result sets it: "set <global> to 1"; the Dialogue page writes that line, scenes.js)
        tr = {'kind': 'global', 'name': scene_global(db, sid), 'value': 1, 'once': tr.get('once', True), 'from': 'dialogue'}
    if tr:
        k = tr.get('kind')
        if k not in TRIGGERS:
            raise EditError('A scene starts when %s.' % '; or '.join(TRIGGERS.values()))
        if k == 'area' and not (isinstance(tr.get('center'), (list, tuple)) and len(tr['center']) == 3):
            raise EditError('Pick the spot the player comes near.')
        if k == 'quest' and not (tr.get('quest') and int(tr.get('stage') or 0) > 0):
            raise EditError('Pick the quest and its stage.')
        if k == 'global':
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]{0,31}$', str(tr.get('name') or '')):
                raise EditError('Name the global variable.')
            if db.resolve_id(str(tr['name'])) is None:
                raise EditError('There is no global variable "%s": make it under Rules › Global variables first.' % tr['name'])
        tr = {k2: v for k2, v in tr.items() if k2 in ('kind', 'center', 'radius', 'cell', 'once', 'quest', 'stage', 'name', 'value', 'from')}
    p.scenes = dict(p.scenes)
    p.scenes[sid] = {k2: v for k2, v in sc.items() if k2 != 'trigger'}
    if tr:
        p.scenes[sid]['trigger'] = tr
    editing.commit(db, ('Scene "%s" starts when %s' % (sc.get('name') or sid, TRIGGERS['dialogue' if tr.get('from') == 'dialogue' else tr['kind']])) if tr
                   else 'Scene "%s" starts only when asked' % (sc.get('name') or sid))
    return {'scene': sid, 'trigger': tr or None}


def scenes(db):
    p = _need_mod(db)
    return [{'scene': k, 'name': v.get('name') or k, 'length': v.get('length'), 'trigger': v.get('trigger'),
             'cell': v.get('cell'), 'actors': len(v.get('actors') or []), 'shots': len(v.get('shots') or [])}
            for k, v in sorted((p.scenes or {}).items())]


def get_scene(db, sid):
    p = _need_mod(db)
    sc = (p.scenes or {}).get(sid or '')
    if sc is None:
        raise EditError('No scene "%s" in this mod.' % sid)
    return sc


def drop_scene(db, sid):
    p = _need_mod(db)
    if sid not in (p.scenes or {}):
        raise EditError('No scene "%s" in this mod.' % sid)
    p.scenes = {k: v for k, v in p.scenes.items() if k != sid}
    import scenes as _sc
    _sc.movie_records(db)
    editing.commit(db, 'Removed scene "%s"' % sid)
    return {'removed': sid}


# ------------------------------------------------------------------ any of the Workshop's own actions
def action(prog, body, port):
    import urllib.error
    import urllib.request
    from urllib.parse import urlencode
    import mcpserver
    path = '/' + str(body.get('action') or '').strip().lstrip('/')
    if not path.startswith('/api/'):
        path = '/api/' + path[1:]
    both = [a for a in mcpserver.catalogue().values() if a['path'] == path]
    if not both:
        raise EditError('There is no Workshop action %s: GET /bridge/actions?search=... finds them.' % path)
    m = str(body.get('method') or '').upper()
    a = next((x for x in both if x['method'] == m), None) if m else (both[0] if len(both) == 1 else None)
    if a is None:
        raise EditError('%s is both GET (to read) and POST (to change): say which with "method".' % path)
    if a.get('kept'):
        raise EditError('%s is kept for the user (%s).' % (path, a['kept']))
    args = body.get('args') if isinstance(body.get('args'), dict) else {}
    url = 'http://127.0.0.1:%d%s' % (port, path)
    win = 'bridge:' + prog['name']
    if a['method'] == 'GET':
        req = urllib.request.Request(url + ('?' + urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in args.items()}) if args else ''),
                                     headers={'X-Workshop-Window': win})
    else:
        req = urllib.request.Request(url, data=json.dumps(args).encode('utf-8'), method='POST',
                                     headers={'Content-Type': 'application/json', 'X-Workshop-Window': win})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3600) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get('error')
        except Exception:
            msg = None
        raise EditError('%s: %s' % (path, msg or 'the Workshop answered %s' % e.code))
    try:
        return json.loads(raw)
    except ValueError:
        return {'ok': True, 'bytes': len(raw)}


def actions(search):
    import mcpserver
    cat = mcpserver.catalogue()
    words = [w for w in re.split(r'\W+', str(search or '').lower()) if w]
    hits = [a for a in cat.values() if not a.get('kept') and
            all(w in (a['path'] + ' ' + a['what'] + ' ' + ' '.join(a['args'])).lower() for w in words)]
    return {'found': [{k: a[k] for k in ('path', 'method', 'what', 'args')} for a in hits[:60]], 'more': max(0, len(hits) - 60)}


# ------------------------------------------------------------------ HTTP: /bridge/...
def _mark(p, before, name):
    for e in p.log[before:]:
        t = e.get('text') or ''
        if t and not t.startswith(MARK):
            e['text'] = '%s%s: %s' % (MARK, name, t)


def _show(prog, what, text, cell=None, refs=None, changed=True, error=None):
    """The window's line saying what the program did, and following it to the place (as for coding agents)."""
    try:
        import mcpserver
        mcpserver._note({'agent': prog['name'], 'tool': what, 'title': what, 'changed': changed, 'text': (text or '')[:300],
                         'cell': cell, 'refs': refs or [], 'error': (error or '')[:300] or None, 'focus': None})
    except Exception:
        pass


def http(handler, db, lock, method):
    """Answer GET/POST /bridge/... for the Workshop's request handler."""
    from urllib.parse import parse_qs, urlparse

    def send(code, obj):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode('utf-8')
        handler.send_response(code)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(body)))
        handler.send_header('Cache-Control', 'no-store')
        handler.end_headers()
        handler.wfile.write(body)

    origin = handler.headers.get('Origin')
    if origin:
        return send(403, {'error': 'Requests from web pages are refused.'})
    u = urlparse(handler.path)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    path = u.path[len('/bridge'):].rstrip('/') or '/'
    body = {}
    if method == 'POST':
        n = int(handler.headers.get('Content-Length') or 0)
        try:
            body = json.loads(handler.rfile.read(n).decode('utf-8') or '{}') if n else {}
        except ValueError:
            return send(400, {'error': 'The body is not JSON.'})
        if not isinstance(body, dict):
            return send(400, {'error': 'The body is a JSON object.'})
    try:
        if path == '/hello':
            if method == 'POST':
                return send(200, hello(body.get('program'), body.get('version')))
            return send(200, hello_state(q.get('id')))
        key = re.sub(r'^Bearer\s+', '', handler.headers.get('Authorization') or '') or handler.headers.get('X-Bridge-Key') or ''
        prog = _by_key(key)
        if prog is None:
            return send(401, {'error': 'Not connected: POST /bridge/hello and have the user press Allow in the Workshop.'})
        s = SEEN.setdefault(prog['name'], {'calls': 0})
        s['last'], s['calls'] = time.time(), s['calls'] + 1
        port = handler.server.server_address[1]
        if method == 'GET':
            if path == '/status':
                return send(200, status(db, prog))
            if path == '/changes':
                return send(200, changes(db, q.get('since')))
            if path == '/scenes':
                return send(200, {'scenes': scenes(db)})
            if path == '/scene':
                return send(200, get_scene(db, q.get('scene') or q.get('id')))
            if path == '/actions':
                return send(200, actions(q.get('search')))
            return send(404, {'error': 'No such bridge call: %s %s.' % (method, u.path)})
        if path == '/action':
            out = None
            p = db.project
            before = len(p.log) if p else 0
            try:
                out = action(prog, body, port)
            finally:
                if p is not None and db.project is p:
                    with lock:
                        _mark(p, before, prog['name'])
            aa = body.get('args') if isinstance(body.get('args'), dict) else {}
            c = aa.get('cell') or aa.get('key')
            _show(prog, str(body.get('action') or '').replace('/api/', ''), '; '.join(
                _unmarked(e.get('text'), prog['name']) for e in (p.log[before:] if p is not None and db.project is p else [])),
                cell=c if isinstance(c, str) else None, changed=bool(p is not None and len(p.log) > before))
            return send(200, out)
        with lock:
            editing.ORIGIN.window = 'bridge:' + prog['name']
            _projmod.EXTERNAL.on = False          # (joins the user's unsaved work, as a second window's would)
            p = db.project
            before = len(p.log) if p else 0
            try:
                if path == '/snapshot':
                    out = snapshot(db)
                elif path == '/place':
                    out = place(db, prog, body)
                elif path == '/move':
                    out = move(db, body)
                elif path == '/delete':
                    out = delete(db, body)
                elif path == '/file':
                    out = take_file(db, body)
                elif path == '/record':
                    out = put_record(db, body)
                elif path == '/record/delete':
                    out = drop_record(db, body)
                elif path == '/ref_fields':
                    out = ref_fields(db, body)
                elif path == '/cell':
                    out = put_cell(db, body)
                elif path == '/scene':
                    out = put_scene(db, body.get('scene') if isinstance(body.get('scene'), dict) else body)
                elif path == '/scene/delete':
                    out = drop_scene(db, body.get('scene') or body.get('id'))
                elif path == '/check_scene':
                    out = {'problems': check_scene(db, body.get('scene') if isinstance(body.get('scene'), dict) else body)}
                else:
                    return send(404, {'error': 'No such bridge call: %s %s.' % (method, u.path)})
            finally:
                editing.ORIGIN.window = None
                if p is not None and db.project is p:
                    _mark(p, before, prog['name'])
        if p is not None and len(p.log) > before:
            refs = [out['ref']['file'] + '|' + str(out['ref']['index'])] if isinstance(out, dict) and isinstance(out.get('ref'), dict) else []
            _show(prog, path.strip('/'), '; '.join(_unmarked(e.get('text'), prog['name']) for e in p.log[before:]),
                  cell=out.get('cell') if isinstance(out, dict) else None, refs=refs)
        return send(200, out)
    except EditError as e:
        return send(400, {'error': str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return send(500, {'error': 'The Workshop failed: %s' % e})


def _unmarked(t, name):
    t = str(t or '')
    return t[len('%s%s: ' % (MARK, name)):] if t.startswith('%s%s: ' % (MARK, name)) else t
