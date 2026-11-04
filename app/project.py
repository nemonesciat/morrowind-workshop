"""Your mod project: every change you make is kept here, and compiled into a real
.omwaddon plugin in OpenMW's data folder. Original game files are never touched."""
import base64
import json
import os
import re
import struct
import time

from esm import ENC, iter_subrecords, zstr

APP_DIR = os.environ.get('WORKSHOP_HOME') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(APP_DIR, 'projects')
SETTINGS_FILE = os.path.join(APP_DIR, 'workshop_settings.json')

REF_START = ('FRMR', 'MVRF')


def b64(b):
    return base64.b64encode(bytes(b)).decode('ascii')


def unb64(s):
    return base64.b64decode(s)


def sub(tag, data):
    return tag.encode('ascii') + struct.pack('<I', len(data)) + bytes(data)


def zs(s):
    return s.encode(ENC, 'replace') + b'\0'


def join_subs(subs):
    return b''.join(sub(t, d) for t, d in subs)


LAND_ORDER = ('INTV', 'DATA', 'VNML', 'VHGT', 'WNAM', 'VCLR', 'VTEX')


def land_in_order(data):
    """A land record's parts in the game's order. OpenMW reads them in that order and skips one out of place, so a
    land saved before 2026-10-28 with its heights after its textures showed flat sea floor in game (landscape.write)."""
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    known = sorted((s for s in subs if s[0] in LAND_ORDER), key=lambda s: LAND_ORDER.index(s[0]))
    rest = [s for s in subs if s[0] not in LAND_ORDER]
    out = known + rest
    if [t for t, _d in out] == [t for t, _d in subs]:
        return data
    return join_subs(out)


_LINKS = {}         # (a line's data -> its INAM and PNAM: read on every write of the mod otherwise)


def _chain_order(infos):
    """Dialogue lines in the order of their "previous line" links (each after the one it follows)."""
    def link(r, tag):
        got = _LINKS.get(r['data'])
        if got is None:
            got = {}
            for t, d in iter_subrecords(unb64(r['data'])):
                if t in ('INAM', 'PNAM') and t not in got:
                    got[t] = zstr(d)
            if len(_LINKS) > 100000:
                _LINKS.clear()
            _LINKS[r['data']] = got
        return got.get(tag, '')
    by_id = {link(r, 'INAM'): r for r in infos}
    out, done = [], set()

    def place(r, depth=0):
        k = link(r, 'INAM')
        if k in done:
            return
        p = link(r, 'PNAM')
        if p in by_id and p not in done and depth < 500:
            place(by_id[p], depth + 1)
        if k not in done:
            done.add(k)
            out.append(r)
    for r in infos:
        place(r)
    return out


def split_cell(data):
    """Split CELL data into (header subrecords, list of refs). Each ref is
    {'frmr': int, 'subs': [(tag, bytes)...]} (subs exclude FRMR)."""
    header, refs, cur = [], [], None
    after_mvrf = False
    for t, d in iter_subrecords(data):
        if t == 'FRMR':
            cur = {'frmr': struct.unpack_from('<I', d)[0] if len(d) >= 4 else 0, 'subs': []}
            refs.append(cur)
            after_mvrf = False
        elif t == 'MVRF':
            cur, after_mvrf = None, True     # moved-reference marker, not part of a reference
        elif after_mvrf and t in ('CNAM', 'CNDT'):
            continue
        elif t == 'NAM0':
            continue
        elif cur is None:
            header.append((t, bytes(d)))
        else:
            cur['subs'].append((t, bytes(d)))
    return header, refs


def ref_info(subs):
    """id, position (x,y,z,rx,ry,rz), scale, deleted from a ref's subrecords."""
    rid, pos, scale, deleted = '', (0.0,) * 6, 1.0, False
    for t, d in subs:
        if t == 'NAME':
            rid = zstr(d)
        elif t == 'DATA' and len(d) >= 24:
            pos = struct.unpack_from('<6f', d)
        elif t == 'XSCL' and len(d) >= 4:
            scale = struct.unpack_from('<f', d)[0]
        elif t == 'DELE':
            deleted = True
    return rid, pos, scale, deleted


def set_ref_pos(subs, pos=None, scale=None):
    out, had_data = [], False
    for t, d in subs:
        if t == 'DATA' and pos is not None:
            d = struct.pack('<6f', *pos)
            had_data = True
        if t == 'XSCL' and scale is not None:
            continue
        out.append((t, d))
    if pos is not None and not had_data:
        out.append(('DATA', struct.pack('<6f', *pos)))
    if scale is not None and abs(scale - 1.0) > 1e-4:
        # XSCL goes right after NAME (and before DATA)
        idx = next((n + 1 for n, (t, _d) in enumerate(out) if t == 'NAME'), 0)
        out.insert(idx, ('XSCL', struct.pack('<f', scale)))
    return out


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, obj, **kw):
    """A JSON file written whole or not at all (a copy beside it, then put in its place): a Workshop closed or killed
    mid-write left a half file, and the settings, a prefab or a plan in it were gone (2026-11-02 audit)."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj, **kw))
    os.replace(tmp, path)


def save_settings(s):
    write_json(SETTINGS_FILE, s, indent=2)


def safe_name(name):
    keep = ''.join(c for c in name if c.isalnum() or c in ' _-').strip()
    return keep[:60] or 'MyMod'


SOON = set()            # projects with a save_soon not done yet
SAVE_LOCK = None        # the lock edits hold (workshop.edit_lock): a later save waits for the edit under way


def _nolock():
    import contextlib
    return contextlib.nullcontext()


def save_pending():
    """The saves asked for with save_soon, now (the Workshop closing, another mod opening)."""
    for p in list(SOON):
        try:
            p.save()
        except Exception as e:
            print('save failed:', e)


class Project:
    def __init__(self, path):
        self.path = path
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            # (the file unreadable, the Workshop or the computer stopped mid-save: the whole copy a save writes before
            # putting it in place, if there is one, is the newest the mod was)
            try:
                with open(path + '.tmp', encoding='utf-8') as f:
                    d = json.load(f)
            except (OSError, ValueError):
                raise e
            print('%s could not be read (%s): opened the copy its last save left' % (os.path.basename(path), e))
            if os.path.exists(path):
                os.replace(path, path + '.unreadable')
            os.replace(path + '.tmp', path)
        self.name = d['name']
        self.plugin = d['plugin']
        self.author = d.get('author', '')
        self.description = d.get('description', '')
        self.records = d.get('records', {})   # "TAG|key" -> {tag, key, flags, data, created}
        self.cells = d.get('cells', {})       # cell key -> {flags, header, refs: {refkey: {...}}}
        self.next_ref = d.get('next_ref', 1)
        self.log = d.get('log', [])
        # (big changes' undo data kept beside the project, see _log_to_keep: read back in, so Undo still reaches them)
        for e in self.log:
            if e.get('diff_file') and 'diff' not in e:
                try:
                    with open(os.path.join(self._history_dir(), e['diff_file']), encoding='utf-8') as f:
                        e['diff'] = json.load(f)
                except (OSError, ValueError):
                    pass
        self.release = d.get('release', {})     # version, changelog, readme bits (Release page)
        self.lua = d.get('lua', [])             # Lua scripts: [{name, kind, attach: [ids], text}]
        self.lua_files = d.get('lua_files', [])  # the Lua files last written, so old ones can be cleared
        self.grass = d.get('grass', {})         # groundcover: cell key -> [[id, x, y, z, rz, scale]] (own plugin)
        self.land = d.get('land', {})           # land shaping: {'marks': ['gx,gy', ...]} the cells marked on the land map
        self.scattered = set(d.get('scattered') or [])   # ref keys the Scatter brush placed (its Remove clears only these)
        self.town_parts = d.get('town_parts') or {}       # ref key -> its building's id, for the buildings a town built
        self.quests = d.get('quests', {})       # the quest Board's plans: quest key -> {'cast': [ids picked before any move uses them]}
        self.rolls = d.get('rolls', {})         # interiors in limbo (rollinside.py): door 'cell|ref' -> {'old', 'name', 'rolls', ...}
        self.forged = d.get('forged', {})       # the Forge: piece id (lower) -> {'mat'} or {'between': [a, b, f]}, what it was
                                                # forged as ("Duskglass" isn't glass); outside Undo, read only while the record is there
        # a plugin opened as the mod itself (adopt.py): the file it is saved into, the masters its header
        # listed (names and sizes, kept in that order so its objects' indices stay what saved games know),
        # its header's format version, and the dated copy made of it beside it when it was opened
        self.source = d.get('source')
        self.order = d.get('order') or []        # the file's record keys in its own order (new records go after)
        self.masters = [list(m) for m in d.get('masters') or []]
        self.tes3_version = d.get('tes3_version') or 1.3
        self.hedr_raw = d.get('hedr')
        self.plugin_backup = d.get('plugin_backup')
        self.undo_stack = []
        self.last_state = self.snapshot()
        self.pending_write = None
        try:
            import backups
            backups.maybe_backup(self, force=True, why='opened')     # how it was before this session
        except Exception as e:
            print('backup failed:', e)

    @classmethod
    def create(cls, name, author='', description=''):
        os.makedirs(PROJECTS_DIR, exist_ok=True)
        name = safe_name(name)
        path = os.path.join(PROJECTS_DIR, name + '.json')
        if os.path.exists(path):
            return cls(path)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'name': name, 'plugin': name + '.omwaddon', 'author': author[:31],
                       'description': description[:255], 'records': {}, 'cells': {}, 'next_ref': 1}, f)
        return cls(path)

    BIG_DIFF = 20_000              # (an entry's undo data this big goes to the history folder, not the project file)
    HISTORY_MAX = 400_000_000      # (and the folder keeps the newest of them within this much)

    def _history_dir(self):
        return os.path.splitext(self.path)[0] + ' history'

    def _log_to_keep(self, limit=2_000_000, count=500):
        """The newest log entries, no more than `count` and about `limit` bytes of them in the project file: the diffs
        kept with each change made a 1 MB project a 7 MB file, written again after every move. A big change's diff (a
        town, a reshaped valley) is written once to the history folder beside the project and the entry keeps its file
        name: inline, the first save after any later edit dropped it, and its Undo with it (the user's town, 2026-10-31,
        on a project whose file kept 36 entries)."""
        out, total, hist, kept_files = [], 0, 0, set()
        hd = self._history_dir()
        for e in reversed(self.log):
            if len(out) >= count:
                break
            d = e.get('diff')
            # (each entry's size measured once: measured again on every save, 0.8 s a save on a big mod)
            sizes = self.__dict__.setdefault('_diff_sizes', {})
            got = sizes.get(id(e))
            if got and got[0] is d:
                n, raw = got[1], None
            else:
                raw = json.dumps(d) if d else ''
                n = len(raw)
                sizes[id(e)] = (d, n)
            if d and n > self.BIG_DIFF:
                name = e.get('diff_file') or '%d-%d.json' % (e.get('id', 0), int(time.time()))
                path = os.path.join(hd, name)
                if not os.path.exists(path):
                    try:
                        os.makedirs(hd, exist_ok=True)
                        with open(path + '.tmp', 'w', encoding='utf-8') as f:
                            f.write(raw if raw is not None else json.dumps(d))
                        os.replace(path + '.tmp', path)
                    except OSError:
                        name = None
                if name:
                    hist += n
                    if hist > self.HISTORY_MAX:
                        break
                    e['diff_file'] = name
                    kept_files.add(name)
                    lite = {k: v for k, v in e.items() if k != 'diff'}
                    out.append(lite)
                    total += len(json.dumps(lite))
                    continue
            size = n + 200
            if out and total + size > limit:
                break
            out.append(e)
            total += size
        out.reverse()
        # (history files no kept entry names any more: gone)
        try:
            for fn in os.listdir(hd):
                if fn.endswith('.json') and fn not in kept_files:
                    os.remove(os.path.join(hd, fn))
        except OSError:
            pass
        return out

    def save_soon(self, delay=1.5):
        """Save in a moment, once: for what is kept in the mod but isn't an edit (cells marked, the shapes drawn). Each
        mark saved the whole mod there and then, a second or more on a big one, and marks clicked one after another
        queued behind each other ("knuckle draggingly slow", 2026-11-02). A save meanwhile covers it."""
        import threading
        n = self._soon_n = getattr(self, '_soon_n', 0) + 1
        SOON.add(self)

        def run():
            if getattr(self, '_soon_n', 0) != n or self not in SOON:
                return                                  # (a newer one comes, or a save took it)
            with SAVE_LOCK or _nolock():
                if self in SOON:
                    self.save()
        t = threading.Timer(delay, run)
        t.daemon = True
        t.start()

    def save(self, texts=None):
        """texts: {place key: its JSON text} already made for this write (editing._write_now), put in as they are."""
        SOON.discard(self)
        tmp = self.path + '.tmp'
        d = {'name': self.name, 'plugin': self.plugin, 'author': self.author,
             'description': self.description, 'records': self.records, 'cells': self.cells,
             'next_ref': self.next_ref, 'log': self._log_to_keep(), 'release': self.release,
             'lua': self.lua, 'lua_files': self.lua_files, 'grass': self.grass}
        if self.land:
            d['land'] = self.land
        if self.forged:
            d['forged'] = self.forged
        if self.quests:
            d['quests'] = self.quests
        if getattr(self, 'rolls', None):
            d['rolls'] = self.rolls
        if self.scattered:
            d['scattered'] = sorted(self.scattered)
        if self.town_parts:
            d['town_parts'] = self.town_parts
        if self.source:
            d.update({'source': self.source, 'masters': self.masters, 'tes3_version': self.tes3_version,
                      'plugin_backup': self.plugin_backup, 'order': self.order, 'hedr': self.hedr_raw})
        # (dumps, then one write: json.dump to a file runs the pure-Python encoder, ten times slower. A 32 MB mod
        # took 2-20 s a save, and every mark, shape and brush stroke saves: "knuckle draggingly slow", 2026-11-02)
        if texts is None:
            text = json.dumps(d)
        else:
            # (the same text json.dumps(d) makes, the places put in from texts)
            def val(k, v):
                if k != 'cells':
                    return json.dumps(v)
                return '{' + ', '.join('%s: %s' % (json.dumps(ck), texts.get(ck) or json.dumps(c)) for ck, c in v.items()) + '}'
            text = '{' + ', '.join('%s: %s' % (json.dumps(k), val(k, v)) for k, v in d.items()) + '}'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, self.path)
        try:
            import backups
            backups.maybe_backup(self)            # (every few minutes; see backups.py)
        except Exception as e:
            print('backup failed:', e)

    def state(self):
        return json.dumps({'records': self.records, 'cells': self.cells, 'next_ref': self.next_ref, 'lua': self.lua,
                           'grass': self.grass, 'scattered': sorted(self.scattered), 'town_parts': self.town_parts,
                           'rolls': getattr(self, 'rolls', None) or {}})

    def snapshot(self, prev=None):
        """The state in parts (Snap), sharing the parts that didn't change with prev (the last one by default)."""
        prev = prev if prev is not None else self.__dict__.get('last_state')
        prev = prev if isinstance(prev, Snap) else None
        return Snap.of(self.records, self.cells, self.grass or {}, {'next_ref': self.next_ref, 'lua': self.lua,
                       'scattered': sorted(self.scattered), 'town_parts': self.town_parts, 'rolls': getattr(self, 'rolls', None) or {}}, prev)

    def restore(self, state, cur=None):
        """Put the project back as a state was (a Snap, or a state() text). cur: a Snap of the project as it is now, so
        the parts the same in both are kept as they are, not read again."""
        if not isinstance(state, Snap):
            d = json.loads(state)
            self.records, self.cells, self.next_ref = d['records'], d['cells'], d['next_ref']
            self.lua = d.get('lua', [])
            self.grass = d.get('grass', {})
            self.scattered = set(d.get('scattered') or [])
            self.town_parts = d.get('town_parts') or {}
            self.rolls = d.get('rolls') or {}
            return
        cur = cur if isinstance(cur, Snap) else None

        def back(parts, now, live):
            if now is None:
                return {k: json.loads(s) for k, s in parts.items()}
            return {k: live[k] if k in live and (now.get(k) is s or now.get(k) == s) else json.loads(s) for k, s in parts.items()}
        self.records = back(state.r, cur and cur.r, self.records)
        self.cells = back(state.c, cur and cur.c, self.cells)
        self.grass = back(state.g, cur and cur.g, self.grass or {})
        m = json.loads(state.m)
        self.next_ref, self.lua = m['next_ref'], m.get('lua', [])
        self.scattered = set(m.get('scattered') or [])
        self.town_parts = m.get('town_parts') or {}
        self.rolls = m.get('rolls') or {}

    def cell_bytes_of(self, key, c, masters, text=None):
        """cell_bytes, kept for each place by its JSON text: a place that didn't change isn't encoded again. Every change
        encoded every place twice (to sync, then to write), 2 s and more a change on a 32 MB mod (2026-11-02 audit)."""
        text = text if text is not None else json.dumps(c)
        memo = self.__dict__.setdefault('_cellbin', {})
        sig = (tuple(masters), self.plugin.lower(), bool(self.source))
        got = memo.get(key)
        if got is not None and got[1] == sig and (got[0] is text or got[0] == text):
            return got[2]
        b = self.cell_bytes(c, masters)
        if len(memo) > 2 * len(self.cells) + 100:
            for k in [k for k in memo if k not in self.cells]:
                del memo[k]
        memo[key] = (text, sig, b)
        return b

    # ----- Lua scripts (OpenMW): files next to the plugin, listed in a .omwscripts file -----
    def lua_allowed(self):
        """Lua scripts (and their .omwscripts list) belong to OpenMW's own plugin format. A mod that is a plain
        .esp (one opened from an existing file, say) keeps its scripts in the project, but they are not
        written out: the Scripts page and Get ready to share say so."""
        return os.path.splitext(self.plugin)[1].lower() not in ('.esp', '.esm')

    def lua_slug(self):
        return re.sub(r'[^a-z0-9_]+', '_', os.path.splitext(self.plugin)[0].lower()).strip('_') or 'mymod'

    def lua_omwscripts(self):
        return os.path.splitext(self.plugin)[0] + '.omwscripts'

    def lua_path(self, s):
        return 'scripts/%s/%s.lua' % (self.lua_slug(), s['name'])

    def lua_outputs(self):
        """{relative path: text} of every file the Lua scripts need, including the .omwscripts list."""
        if not self.lua or not self.lua_allowed():
            return {}
        out, lines, attach = {}, [], {}
        for s in self.lua:
            path = self.lua_path(s)
            import myeffects
            out[path] = myeffects.own_events(s.get('text') or '', self.lua_slug())
            ids = [i.strip().lower() for i in s.get('attach') or [] if i.strip()]
            if ids:
                lines.append('CUSTOM: ' + path)
                for i in ids:
                    attach.setdefault(i, []).append(path)
            else:
                lines.append('%s: %s' % (s.get('kind') or 'GLOBAL', path))
        if attach:
            # a small global script that gives the chosen objects their scripts when they come into play
            helper = 'scripts/%s/_attach.lua' % self.lua_slug()
            table = ',\n'.join('  [%s] = {%s}' % (json.dumps(k), ', '.join(json.dumps(p) for p in v)) for k, v in sorted(attach.items()))
            out[helper] = ('-- Made by Morrowind Workshop: puts your scripts on the objects you chose.\n'
                           'local scripts = {\n%s\n}\n\nlocal function give(obj)\n  local list = scripts[obj.recordId]\n'
                           '  if not list then return end\n  for _, path in ipairs(list) do\n'
                           '    if not obj:hasScript(path) then obj:addScript(path) end\n  end\nend\n\n'
                           'return {\n  engineHandlers = {\n    onObjectActive = give,\n    onActorActive = give,\n'
                           '    onItemActive = give,\n  },\n}\n' % table)
            lines.insert(0, 'GLOBAL: ' + helper)
        out[self.lua_omwscripts()] = '# Made by Morrowind Workshop for %s\n' % self.plugin + '\n'.join(lines) + '\n'
        return out

    def write_lua(self, data_dir):
        """Write the Lua files into the data folder (only what changed), and clear ones no longer used."""
        outs = self.lua_outputs()
        for rel, text in outs.items():
            full = os.path.join(data_dir, *rel.split('/'))
            try:
                with open(full, encoding='utf-8', newline='') as f:
                    if f.read() == text:
                        continue
            except OSError:
                pass
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
        for rel in self.lua_files:
            if rel not in outs:
                try:
                    os.remove(os.path.join(data_dir, *rel.split('/')))
                except OSError:
                    pass
        if sorted(outs) != sorted(self.lua_files):
            self.lua_files = sorted(outs)
            self.save()

    def note(self, text, diff=None):
        nid = max([e.get('id', 0) for e in self.log] + [0]) + 1
        e = {'id': nid, 't': time.strftime('%Y-%m-%d %H:%M'), 'text': text}
        if diff:
            e['diff'] = diff
        self.log.append(e)
        return e

    # ----- records -----
    def set_record(self, tag, key, flags, data, created=False):
        k = tag + '|' + key
        prev = self.records.get(k)
        self.records[k] = {'tag': tag, 'key': key, 'flags': flags, 'data': b64(data),
                           'created': created or bool(prev and prev.get('created'))}

    def remove_record(self, tag, key):
        return self.records.pop(tag + '|' + key, None)

    def change_count(self):
        n = len(self.records)
        for c in self.cells.values():
            n += len(c['refs'])
        # each script, and each cell with groundcover, counts as one change
        n += len(getattr(self, 'lua', None) or [])
        n += sum(1 for v in (getattr(self, 'grass', None) or {}).values() if v)
        return n

    # ----- cells -----
    def cell(self, key, header, flags):
        c = self.cells.get(key)
        if c is None:
            c = self.cells[key] = {'flags': flags, 'header': [[t, b64(d)] for t, d in header], 'refs': {}}
        return c

    def new_ref_key(self):
        k = '%s|%d' % (self.plugin.lower(), self.next_ref)
        self.next_ref += 1
        return k

    # ----- compiling -----
    def cell_bytes(self, c, masters):
        """Build CELL record data. masters: list of lowercase master names. Each object's bytes are kept by what it
        holds, so an unchanged one isn't encoded again: every change and every write of the mod encoded all of it,
        seconds on a big mod, hundreds of times in a town (2026-11-02)."""
        memo = self.__dict__.setdefault('_chunks', {})
        if len(memo) > 600000:
            memo.clear()
        out = [join_subs([(t, unb64(d)) for t, d in c['header']])]

        def chunk(r):
            origin = r['origin']
            if origin == self.plugin.lower():
                upper = 0
            elif origin in masters:
                upper = masters.index(origin) + 1
            else:
                # a change to an object of a file that is not in the load order any more (a mod merged into
                # this one and switched off, say): nothing to write it against; Health check lists these
                return None
            frmr = (upper << 24) | (r['idx'] & 0xFFFFFF)
            key = (frmr, bool(r.get('deleted')), tuple(d for _t, d in r['subs']), tuple(t for t, _d in r['subs']),
                   tuple(d for _t, d in r['mvrf']) if r.get('mvrf') else None)
            b = memo.get(key)
            if b is None:
                b = memo[key] = encode(r, frmr)
            return b

        def encode(r, frmr):
            subs = [(t, unb64(d)) for t, d in r['subs']]
            if r.get('deleted') and not any(t == 'DELE' for t, _d in subs):
                subs = [(t, d) for t, d in subs if t == 'NAME'] + [('DELE', b'\0\0\0\0')]
            b = sub('FRMR', struct.pack('<I', frmr)) + join_subs(subs)
            if r.get('mvrf'):
                # an object moved to this cell from another (outdoors): the marker the file had stays with it
                b = join_subs([(t, unb64(d)) for t, d in r['mvrf']]) + b
            return b

        refs = sorted(c['refs'].values(), key=lambda r: (r['origin'] == self.plugin.lower(), r['idx']))
        if self.source:
            # a plugin opened as the mod, written the Construction Set's way: the objects it keeps track of
            # (doors, people: "persistent", read before NAM0) first, then NAM0 with the count of the rest and
            # the rest; no NAM0 when there is no rest. Anything placed here counts among the rest.
            pers = [b for b in (chunk(r) for r in refs if r.get('pers')) if b is not None]
            rest = [b for b in (chunk(r) for r in refs if not r.get('pers')) if b is not None]
            out += pers
            if rest:
                out.append(sub('NAM0', struct.pack('<I', len(rest))))
                out += rest
            return b''.join(out)
        new_refs = sum(1 for k in c['refs'] if k.startswith(self.plugin.lower() + '|'))
        out.append(sub('NAM0', struct.pack('<I', new_refs)))
        out += [b for b in (chunk(r) for r in refs) if b is not None]
        return b''.join(out)

    def _emit_order(self, recs):
        """The records as they go into the file. A mod made here: game settings first, then by type and id,
        dialogue topics (each with its lines) last. A plugin opened as the mod: in the order the file had
        them (new records at the end), each topic's lines right after it."""
        if not self.source:
            out = [r for r in sorted(recs, key=lambda r: (r['tag'] != 'GMST', r['tag'], r['key'])) if r['tag'] not in ('DIAL', 'INFO')]
            for d in sorted((r for r in recs if r['tag'] == 'DIAL'), key=lambda r: r['key']):
                out.append(d)
                out += _chain_order([r for r in recs if r['tag'] == 'INFO' and r['key'].split('|', 1)[0] == d['key']])
            return out
        # (the order is kept apart from the records: Undo and Redo put records back in another order)
        by_key = {r['tag'] + '|' + r['key']: r for r in recs}
        first = [by_key[k] for k in self.order if k in by_key]
        seen = set(self.order)
        recs = first + [r for k, r in by_key.items() if k not in seen]
        infos = {}
        for r in recs:
            if r['tag'] == 'INFO':
                infos.setdefault(r['key'].split('|', 1)[0], []).append(r)
        out = []
        for r in recs:
            if r['tag'] == 'INFO':
                continue
            out.append(r)
            if r['tag'] == 'DIAL':
                out += _chain_order(infos.pop(r['key'], []))
        return out

    def build(self, masters_with_sizes, out_path, texts=None):
        """Write the .omwaddon. masters_with_sizes: [(name, size)] in load order. texts: the places' JSON texts, if made."""
        masters = [m.lower() for m, _s in masters_with_sizes]
        body = []
        count = 0
        def emit(r):
            data = unb64(r['data'])
            if r['tag'] == 'LAND':
                data = land_in_order(data)
            body.append(r['tag'].encode('ascii') + struct.pack('<III', len(data), 0, r['flags']) + data)

        cells = [(key, c) for key, c in self.cells.items() if c['refs'] or c.get('props')]
        if self.source and not self.records and not cells:
            # a plugin opened as the mod, with nothing in it (its opening was undone): the file is left as it
            # is rather than written over with an empty plugin; Redo puts everything back
            return 0

        def emit_cell(key, c):
            data = self.cell_bytes_of(key, c, masters, texts.get(key) if texts else None)
            body.append(b'CELL' + struct.pack('<III', len(data), 0, c.get('flags', 0)) + data)

        recs = self._emit_order(list(self.records.values()))
        if self.source:
            # a plugin opened as the mod: records and places in the order the file had them (places sit
            # among the records there), whatever is new at the end
            at = {k: n for n, k in enumerate(self.order)}
            items = [(at.get(r['tag'] + '|' + r['key'], len(at) + n), 0, n, r) for n, r in enumerate(recs)]
            items += [(at.get('CELL|' + k, len(at) + len(recs) + n), 1, n, (k, c)) for n, (k, c) in enumerate(cells)]
            # (a topic's lines stay right after it: they take the topic's position)
            last = None
            fixed = []
            for pos, kind, n, x in items:
                if kind == 0 and x['tag'] == 'INFO' and last is not None:
                    pos = last
                elif kind == 0 and x['tag'] == 'DIAL':
                    last = pos
                fixed.append((pos, kind, n, x))
            for _pos, kind, _n, x in sorted(fixed, key=lambda it: (it[0], it[1], it[2])):
                if kind == 0:
                    emit(x)
                else:
                    emit_cell(*x)
                count += 1
        else:
            for r in recs:
                emit(r)
                count += 1
            for key, c in cells:
                emit_cell(key, c)
                count += 1
        hedr = struct.pack('<fI', self.tes3_version or 1.3, 0) + self.author.encode(ENC, 'replace')[:31].ljust(32, b'\0') + \
            self.description.encode(ENC, 'replace')[:255].ljust(256, b'\0') + struct.pack('<I', count)
        if self.source and self.hedr_raw:
            # the file's own header bytes (the Construction Set leaves old text after the terminators),
            # the author and description put in only where they were changed here
            raw = bytearray(unb64(self.hedr_raw))
            if len(raw) >= 300:
                if zstr(raw[8:40]) != self.author:
                    raw[8:40] = hedr[8:40]
                if zstr(raw[40:296]) != self.description:
                    raw[40:296] = hedr[40:296]
                struct.pack_into('<I', raw, 296, count)
                hedr = bytes(raw)
        head = [sub('HEDR', hedr)]
        for name, size in masters_with_sizes:
            head.append(sub('MAST', zs(name)))
            head.append(sub('DATA', struct.pack('<Q', size)))
        head = b''.join(head)
        blob = b'TES3' + struct.pack('<III', len(head), 0, 0) + head + b''.join(body)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            self.write_lua(os.path.dirname(out_path))
        except OSError:
            pass                                  # (a script file in use: written next time)
        if self.source:
            try:
                with open(out_path, 'rb') as f:
                    same = f.read() == blob
            except OSError:
                same = False
            if same:
                self.pending_write = None
                return count                      # (nothing changed in the file: no write, no backup)
            try:
                import backups
                backups.backup_plugin(self, out_path)     # (a copy of the file as it was, every few minutes)
            except Exception as e:
                print('plugin backup failed:', e)
        tmp = out_path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(blob)
        try:
            os.replace(tmp, out_path)
            self.pending_write = None
        except OSError:
            # OpenMW keeps the plugin open while the game runs ("access is denied" / "in use").
            # Finish the write when it lets go.
            self.pending_write = (tmp, out_path)
            _start_retry(self)
        return count


class Snap:
    """A project's state in parts: each record, place and cell of grass as its own JSON text, the rest in one. Undo keeps
    one a step, and a part that didn't change is the same string as in the step before, so a step costs what it changed.
    The whole mod's text a step (30 MB on a big mod: the 300 MB cap was reached in ten steps) and a whole read of it to
    find what a change did made every move, Undo and brush stroke take 2-5 s there (2026-11-02 audit)."""
    __slots__ = ('r', 'c', 'g', 'm', 'size')

    def __init__(self, r, c, g, m, size):
        self.r, self.c, self.g, self.m, self.size = r, c, g, m, size     # (size: the bytes of the parts new in it)

    @staticmethod
    def of(records, cells, grass, meta, prev=None):
        size = [0]

        def parts(d, old):
            out = {}
            for k, v in d.items():
                s = json.dumps(v)
                o = old.get(k) if old else None
                if o is not None and o == s:
                    s = o
                else:
                    size[0] += len(s)
                out[k] = s
            return out
        m = json.dumps(meta)
        if prev is not None and prev.m == m:
            m = prev.m
        else:
            size[0] += len(m)
        return Snap(parts(records, prev and prev.r), parts(cells, prev and prev.c), parts(grass, prev and prev.g), m, size[0])

    @staticmethod
    def from_text(s):
        d = json.loads(s)
        return Snap.of(d['records'], d['cells'], d.get('grass') or {}, {'next_ref': d['next_ref'], 'lua': d.get('lua', []),
                       'scattered': d.get('scattered') or [], 'town_parts': d.get('town_parts') or {}})

    def text(self):
        """The whole state as Project.state() writes it."""
        def obj(parts):
            return '{' + ', '.join('%s: %s' % (json.dumps(k), v) for k, v in parts.items()) + '}'
        m = json.loads(self.m)
        return '{"records": %s, "cells": %s, "next_ref": %s, "lua": %s, "grass": %s, "scattered": %s, "town_parts": %s}' % (
            obj(self.r), obj(self.c), json.dumps(m['next_ref']), json.dumps(m.get('lua', [])), obj(self.g),
            json.dumps(m.get('scattered') or []), json.dumps(m.get('town_parts') or {}))


_AS_SNAP = {}       # (a state text made into a Snap: the last one, by its text)


def as_snap(s):
    if isinstance(s, Snap):
        return s
    got = _AS_SNAP.get(s)
    if got is None:
        got = Snap.from_text(s)
        _AS_SNAP.clear()
        _AS_SNAP[s] = got
    return got


def state_text(s):
    """A state (Snap or text) as text, for what reads it whole (building together, the live link)."""
    return s.text() if isinstance(s, Snap) else s


def state_diff(before, after):
    """What changed between two project states (Snaps, or state() texts), per record and per placed object,
    as [before, after] pairs, so one change can be taken back on its own later."""
    b, a = as_snap(before), as_snap(after)
    recs = {}
    for k in set(b.r) | set(a.r):
        x, y = b.r.get(k), a.r.get(k)
        if x is y or x == y:
            continue
        x, y = json.loads(x) if x is not None else None, json.loads(y) if y is not None else None
        if x != y:
            recs[k] = [x, y]
    cells = {}
    for ck in set(b.c) | set(a.c):
        x, y = b.c.get(ck), a.c.get(ck)
        if x is y or x == y:
            continue
        bc, ac = json.loads(x) if x is not None else {}, json.loads(y) if y is not None else {}
        br, ar = bc.get('refs', {}), ac.get('refs', {})
        refs = {rk: [br.get(rk), ar.get(rk)] for rk in set(br) | set(ar) if br.get(rk) != ar.get(rk)}
        if refs:
            meta = {'flags': (ac or bc).get('flags', 0), 'header': (ac or bc).get('header', [])}
            if ck not in b.c:
                meta['new'] = True                  # this change made the place (or first touched it)
            if (ac or bc).get('plan'):
                meta['plan'] = (ac or bc)['plan']
            if (ac or bc).get('props'):             # (the place's own settings were changed: kept without objects)
                meta['props'] = (ac or bc)['props']
            cells[ck] = {'meta': meta, 'refs': refs}
    if not recs and not cells:
        return None
    return {'r': recs, 'c': cells}


def _start_retry(project):
    if getattr(project, '_retrying', False):
        return
    project._retrying = True

    def loop():
        while project.pending_write:
            time.sleep(2)
            pw = project.pending_write
            if not pw:
                break
            try:
                os.replace(*pw)
                if project.pending_write == pw:
                    project.pending_write = None
            except FileNotFoundError:
                project.pending_write = None
            except OSError:
                pass
        project._retrying = False

    import threading
    threading.Thread(target=loop, daemon=True).start()
