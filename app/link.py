"""Live link between the Workshop and a running OpenMW started with "Play here".

Workshop -> game: workshop_link/state.txt in OpenMW's data-local folder, which an
in-game Lua script reads twice a second. It lists every object that should look
different from what the game loaded at start (placed, moved, removed), so undo
and redo just work: the game always converges on the current list.

Game -> Workshop: the in-game scripts print [WSLINK] lines to openmw.log, which
this module follows like `tail -f`."""
import json
import math
import os
import random
import re
import shutil
import struct
import threading
import time

import mapdata
from esm import zstr
from project import APP_DIR, join_subs, ref_info, unb64, zs


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def editing_label(db, cell_key):
    info = mapdata.cell_info(db, cell_key)
    return (info['name'] or info['id']) if info else cell_key

SCRIPT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'link_scripts')
CONTENT_NAME = 'WorkshopLink.omwscripts'
# Empty rooms loaded with the game. The game can't add new places while it runs, so a room
# made in the Workshop meanwhile is shown in one of these until the next restart.
SPARE_NAME = 'WorkshopSpareRooms.omwaddon'
SPARE_COUNT = 12


def spare_room(n):
    return 'Workshop Spare Room %d' % n


def _rgb(r, g, b):
    return r | (g << 8) | (b << 16)


def spare_rooms_bytes():
    def sub(tag, data):
        return tag.encode('ascii') + struct.pack('<I', len(data)) + data
    body = []
    for n in range(1, SPARE_COUNT + 1):
        data = sub('NAME', spare_room(n).encode('ascii') + b'\0') + sub('DATA', struct.pack('<Iii', 1, 0, 0)) + \
            sub('AMBI', struct.pack('<IIIf', _rgb(85, 80, 75), _rgb(120, 115, 105), _rgb(0, 0, 0), 1.0))
        body.append(b'CELL' + struct.pack('<III', len(data), 0, 0) + data)
    hedr = struct.pack('<fI', 1.3, 0) + b'Morrowind Workshop'.ljust(32, b'\0') + \
        b'Empty rooms for the live link. Safe to ignore.'.ljust(256, b'\0') + struct.pack('<I', SPARE_COUNT)
    head = sub('HEDR', hedr)
    return b'TES3' + struct.pack('<III', len(head), 0, 0) + head + b''.join(body)


def _fmt_t(pos, scale):
    return '\t'.join('%.3f' % v for v in list(pos[:6]) + [scale or 1.0])


class LiveLink:
    def __init__(self, db, edit_lock):
        self.db = db
        self.edit_lock = edit_lock
        self.version = 0
        self.tp_seq = int(time.time())
        self.tp = None
        self.baseline = None          # project cells as they were when the game started
        self.session = None
        self.last_seen = 0
        self.player = None
        self.applied = -1
        self.received = -1
        self.pick = None
        self.pick_seq = 0
        self.armed = None             # {'id', 'name'} object to place with Shift+J
        self.messages = []            # recent errors / notes from the game
        self.commands = []            # quest-test commands for the game: (seq, line)
        self.done = {}                # seq -> 'ok' or what went wrong
        self.watch = (set(), set())   # global variables, items the game reports on
        self.game = self._fresh_game()
        self.lock = threading.Lock()
        self._tail_pos = None
        self._log_path = None
        self.run_linked = None        # did the game run that writes the log load the link? (None: unknown)
        self.last_event = 0           # when the game last really said something
        threading.Thread(target=self._tail_loop, daemon=True).start()

    # ------------------------------------------------------------- paths
    def data_dir(self):
        """The Workshop's own data folder for the link (scripts, spare rooms, state file). It is not
        one of OpenMW's data folders: the Workshop adds it (--data) only when it starts the game, so
        these files never show up in OpenMW's Launcher or in a game started some other way."""
        return os.environ.get('WORKSHOP_LINK_DIR') or os.path.join(APP_DIR, 'link_data')

    def _old_data_dir(self):
        """Where versions before 1.2.3 put these files: OpenMW's own data folder."""
        cfg = self.db.config or {}
        return os.environ.get('WORKSHOP_PLUGIN_DIR') or cfg.get('data_local') or \
            (os.path.join(cfg['userdir'], 'data') if cfg.get('userdir') else None)

    def _remove_old_copies(self):
        """Take the Workshop's own link files out of OpenMW's data folder (only those exact files)."""
        d = self._old_data_dir()
        if not d or os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(self.data_dir())):
            return []
        gone = []
        for rel in (CONTENT_NAME, SPARE_NAME, os.path.join('scripts', 'workshoplink', 'global.lua'),
                    os.path.join('scripts', 'workshoplink', 'player.lua'), os.path.join('workshop_link', 'state.txt'),
                    os.path.join('workshop_link', 'state.txt.tmp'), os.path.join('workshop_link', 'baseline.json')):
            p = os.path.join(d, rel)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                    gone.append(rel)
            except OSError:
                pass
        for rel in (os.path.join('scripts', 'workshoplink'), 'workshop_link'):
            try:
                os.rmdir(os.path.join(d, rel))              # (only if now empty)
            except OSError:
                pass
        if gone:
            print('live link: moved out of %s: %s' % (d, ', '.join(gone)))
        return gone

    def state_path(self):
        return os.path.join(self.data_dir(), 'workshop_link', 'state.txt')

    def install(self):
        """Put the in-game scripts and an (empty) state file into the link's data folder."""
        self._remove_old_copies()
        d = self.data_dir()
        target = os.path.join(d, 'scripts', 'workshoplink')
        os.makedirs(target, exist_ok=True)
        for fn in ('global.lua', 'player.lua'):
            shutil.copyfile(os.path.join(SCRIPT_SRC, fn), os.path.join(target, fn))
        with open(os.path.join(d, CONTENT_NAME), 'w', encoding='utf-8') as f:
            f.write('GLOBAL: scripts/workshoplink/global.lua\nPLAYER: scripts/workshoplink/player.lua\n')
        spare = spare_rooms_bytes()
        sp = os.path.join(d, SPARE_NAME)
        try:
            if not os.path.isfile(sp) or open(sp, 'rb').read() != spare:
                with open(sp, 'wb') as f:
                    f.write(spare)
        except OSError:
            pass                                  # in use by a running game: it's already there
        os.makedirs(os.path.dirname(self.state_path()), exist_ok=True)
        if not os.path.exists(self.state_path()):
            self._write('version\t0\n')

    # ------------------------------------------------------------- sessions
    def start_session(self):
        """Called right before launching the game: what the game will load is the baseline."""
        self.install()
        p = self.db.project
        st = json.loads(p.state()) if p else {'cells': {}, 'records': {}}
        self.baseline = st['cells']
        self.baseline_records = sorted(st['records'])
        self.session = time.time()
        self.spares = {}                          # new place (cell key) -> spare room it's shown in
        self.project_plugin = p.plugin if p else None
        self._save_baseline()
        self.applied = self.received = -1
        self.player = None
        self.pick = None
        self.messages = []
        self.tp = None
        self.commands, self.done = [], {}
        self.game = self._fresh_game()
        self.refresh_watch()
        self.write_state()

    # ------------------------------------------------------------- quest testing
    @staticmethod
    def _fresh_game():
        return {'quests': {}, 'globals': {}, 'items': {}}

    def refresh_watch(self, extra_globals=(), extra_items=()):
        """What the game keeps us told about: the mod's globals and what its lines check, plus extras."""
        import questtest
        try:
            g, i = questtest.watch_list(self.db)
        except Exception as e:
            print('watch list failed:', e)
            g, i = set(), set()
        g |= {x for x in extra_globals if x}
        i |= {x for x in extra_items if x}
        old = self.watch

        def merge(a, b):          # game IDs ignore letter case: keep one spelling of each
            out = {x.lower(): x for x in b}
            out.update({x.lower(): x for x in a})
            return set(out.values())
        self.watch = (merge(old[0], g), merge(old[1], i))
        return self.watch != old

    def command(self, verb, *args):
        """A one-off command for the game (set a quest stage, give an item...). Returns its number."""
        clean = [str(a).replace('\t', ' ').replace('\n', ' ') for a in args]
        with self.lock:
            self.tp_seq += 1
            seq = self.tp_seq
            self.commands.append((seq, '\t'.join(['cmd', str(seq), verb] + clean)))
            del self.commands[:-30]
        self.write_state(bump=False)
        return seq

    def _save_baseline(self):
        """Remember the session, so restarting the Workshop doesn't lose the link to a running game."""
        with open(self._baseline_path(), 'w', encoding='utf-8') as f:
            json.dump({'session': self.session, 'project': self.project_plugin, 'cells': self.baseline,
                       'records': self.baseline_records, 'spares': self.spares}, f)

    def _spare_for(self, cell_key):
        """The spare room a new interior is shown in while the game runs (None if it can't be)."""
        spares = getattr(self, 'spares', None)
        if spares is None:
            return None
        if cell_key in spares:
            return spares[cell_key]
        info = mapdata.cell_info(self.db, cell_key)
        if cell_key.startswith('#') or not info or not info['interior'] or len(spares) >= SPARE_COUNT:
            return None
        spares[cell_key] = spare_room(len(spares) + 1)
        try:
            self._save_baseline()
        except OSError:
            pass
        return spares[cell_key]

    def game_running(self):
        """Is openmw.exe running? (checked at most every 2 seconds)"""
        now = time.time()
        if now - getattr(self, '_proc_checked', 0) > 2:
            self._proc_checked = now
            try:
                import subprocess
                out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq openmw.exe', '/NH'], capture_output=True,
                                     text=True, timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self._proc_running = 'openmw.exe' in out.stdout.lower()
            except Exception:
                self._proc_running = now - self.last_seen < 6
        return self._proc_running

    def connected(self):
        """The game has talked to us since it started, and is still running.
        (A paused game - e.g. while you're in the Workshop window - goes quiet.)"""
        if not self.last_seen:
            return False
        if time.time() - self.last_event < 6:
            return True
        # quiet: only linked if this run of the game ever spoke (a game started from OpenMW's own
        # Launcher runs without the link, even right after a "Play here" session)
        return (self.session is not None and self.last_seen >= self.session and self.game_running()
                and self.run_linked is not False)

    def unlinked_game(self):
        """OpenMW is running, but without the live link (it wasn't started from the Workshop)."""
        return self.run_linked is False and self.game_running() and not (time.time() - self.last_event < 6)

    def paused(self):
        return self.connected() and time.time() - self.last_event >= 6

    # ------------------------------------------------------------- state file
    def _write(self, text):
        path = self.state_path()
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        for _ in range(20):                    # the game may be reading it right now
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.05)

    def _cell_fields(self, cell_key):
        spare = getattr(self, 'spares', {}).get(cell_key)
        if spare:
            return 'int\t%s\t0\t0' % spare
        info = mapdata.cell_info(self.db, cell_key)
        if not info:
            return None
        if info['interior']:
            return 'int\t%s\t0\t0' % info['name']
        return 'ext\t%s\t%d\t%d' % (info['name'], info['gx'], info['gy'])

    def entries(self):
        """Every object whose wanted look differs from what the game loaded."""
        db, p = self.db, self.db.project
        if not p or self.baseline is None:
            return []
        mine = p.plugin.lower()
        cur_cells = p.cells
        out = []
        waiting = set()
        base_recs = set(getattr(self, 'baseline_records', []))

        def cell_in_game(ck):
            if ck in self.baseline:
                return True
            return any(db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('CELL', ck), []) if v not in db.dead)

        def record_in_game(rid):
            ri = db.resolve_id(rid)
            if ri is None:
                return False
            r = db.recs[ri]
            return (r[3] != db.proj_pidx or ('%s|%s' % (r[0], r[7])) in base_recs or len(db.versions(ri)) > 1 or
                    self._standin_ok(r[0], r[7]))

        def reachable(ck):
            """The place exists in the game, for real or as a stand-in spare room."""
            return cell_in_game(ck) or self._spare_for(ck) is not None

        for ck in sorted(set(cur_cells) | set(self.baseline)):
            if not reachable(ck):
                if ck.startswith('#'):
                    waiting.add('the new place "%s"' % editing_label(db, ck))
                else:
                    waiting.add('the new place "%s" (all %d spare rooms are in use)' % (editing_label(db, ck), SPARE_COUNT))
                continue
            cur = (cur_cells.get(ck) or {}).get('refs', {})
            base = (self.baseline.get(ck) or {}).get('refs', {})
            changed = [k for k in set(cur) | set(base) if cur.get(k) != base.get(k)]
            if not changed:
                continue
            cell = self._cell_fields(ck)
            if not cell:
                continue
            master = None
            for k in changed:
                c, b = cur.get(k), base.get(k)
                some = c or b
                if some['origin'] != mine and master is None:
                    master, _hdr = db.cell_refs(ck, without_project=True)

                def look(entry):
                    """(record id, pos, scale, present?) of a project entry, or of the original if None"""
                    if entry is not None:
                        rid, pos, scale, deleted = ref_info([(t, unb64(d)) for t, d in entry['subs']])
                        return rid, pos, scale, not (deleted or entry.get('deleted'))
                    if some['origin'] == mine:
                        return None, None, None, False      # our own object, not placed
                    m = master.get(k)
                    if not m:
                        return None, None, None, False
                    rid, pos, scale, deleted = ref_info(m['subs'])
                    return rid, pos, scale, not deleted

                g_id, g_pos, g_s, g_here = look(b)   # what the game shows now
                w_id, w_pos, w_s, w_here = look(c)   # what we want
                rid = w_id or g_id
                if not rid:
                    continue
                if w_here and not record_in_game(rid):
                    waiting.add('"%s" (new since the game started)' % rid)
                    continue
                door = ''
                if c is not None:
                    s = {t: unb64(d) for t, d in c['subs']}
                    dn = zstr(s['DNAM']) if 'DNAM' in s else ''
                    if dn and not reachable(dn.lower()):
                        waiting.add('the door to "%s"' % dn)
                        continue
                    if 'DODT' in s and len(s['DODT']) >= 24:
                        # objects made while the game runs have no door link of their own: send where it leads
                        d = struct.unpack_from('<6f', s['DODT'])
                        dest = self._cell_fields(dn.lower()) if dn else \
                            'ext\t\t%d\t%d' % (math.floor(d[0] / 8192), math.floor(d[1] / 8192))
                        if dest:
                            door = '\tdoor\t%s\t%.3f\t%.3f\t%.3f\t%.4f' % (dest, d[0], d[1], d[2], d[5])
                    else:
                        # a door whose link was removed in the Workshop: stop it taking people anywhere
                        # (until a restart). Only if the game's copy of it does lead somewhere.
                        if b is not None:
                            had = any(t == 'DODT' for t, _d in b['subs'])
                        elif some['origin'] != mine and master:
                            had = any(t == 'DODT' for t, _d in (master.get(k) or {}).get('subs', []))
                        else:
                            had = False
                        if had:
                            door = '\tdoor\tnone\t\t0\t0\t0\t0\t0\t0'
                orig = _fmt_t(g_pos, g_s) if g_here else '-\t-\t-\t-\t-\t-\t-'
                none = '-\t-\t-\t-\t-\t-\t-'
                if not g_here and not w_here:
                    continue
                if g_here and w_here and g_id and w_id and g_id.lower() != w_id.lower():
                    # swapped for something else: hide the old one and make the new one
                    out.append('ref\t%s~was\tdel\t%s\t%s\t%s\t%s' % (k, g_id, cell, orig, none))
                    out.append('ref\t%s\tnew\t%s\t%s\t%s\t%s%s' % (k, w_id, cell, none, _fmt_t(w_pos, w_s), door))
                    continue
                if not g_here:
                    action, target = 'new', _fmt_t(w_pos, w_s)
                elif not w_here:
                    action, target = 'del', none
                else:
                    action, target = 'mod', _fmt_t(w_pos, w_s)
                out.append('ref\t%s\t%s\t%s\t%s\t%s\t%s%s' % (k, action, rid, cell, orig, target, door))
        self.waiting = sorted(waiting)
        return out

    def _baseline_path(self):
        return os.path.join(self.data_dir(), 'workshop_link', 'baseline.json')

    def resume(self):
        """After a Workshop restart: pick up the session of a game that's still running."""
        if self.baseline is not None or not self.db.config or not self.db.project:
            return
        try:
            with open(self._baseline_path(), encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if d.get('project') == self.db.project.plugin and self.game_running():
            self.baseline = d['cells']
            self.baseline_records = d.get('records', [])
            self.spares = d.get('spares', {})
            self.project_plugin = d.get('project')
            self.session = d['session']
            self.last_seen = max(self.last_seen, self.session)
            with self.lock:
                try:
                    with open(self.state_path(), encoding='utf-8') as f:
                        first = f.readline().split('\t')
                    self.version = max(self.version, int(first[1]))
                except (OSError, ValueError, IndexError):
                    pass

    def write_state(self, bump=True):
        self.resume()
        if self.baseline is None:
            return
        with self.lock:
            if bump:
                self.version += 1        # the game re-checks objects only when this changes
            lines = ['version\t%d' % self.version]
            if self.tp:
                lines.append(self.tp)
            if getattr(self, 'arm_line', None):
                lines.append(self.arm_line)
            lines += [ln for _s, ln in self.commands]
            lines += ['watch\tglobal\t%s' % n for n in sorted(self.watch[0])]
            lines += ['watch\titem\t%s' % n for n in sorted(self.watch[1])]
            lines += self.entries()
            lines += getattr(self, 'palette_lines', [])
            lines += self._library_lines()
            self._write('\n'.join(lines) + '\n')

    def _standin_ok(self, tag, key):
        """A record made since the game started that the game can still show: it makes a stand-in
        for Library models and for the mod's own lights (recoloured lamps, sound sources)."""
        if tag not in ('STAT', 'ACTI', 'CONT', 'MISC', 'DOOR', 'LIGH'):
            return False
        p = self.db.project
        rec = p.records.get('%s|%s' % (tag, key)) if p else None
        if not rec:
            return False
        if tag == 'LIGH':
            return True
        import library
        from esm import iter_subrecords
        model = next((zstr(d) for t, d in iter_subrecords(unb64(rec['data'])) if t == 'MODL'), '').replace('/', '\\').lower()
        if not model.startswith(library.SUB + '\\'):
            return False
        # (a model file brought in after the game started isn't among the game's files yet)
        full = os.path.join(library.data_dir(self.db), 'meshes', *model.split('\\'))
        try:
            return not self.session or os.path.getmtime(full) < self.session
        except OSError:
            return False

    def _library_lines(self):
        """For the in-game spawn menu: your Library models and prefabs, and the Library records the
        mod has (the game makes stand-ins for ones made after it started)."""
        out = []
        try:
            import groups
            import library
            from esm import iter_subrecords, zstr
            for e in library.listing(self.db)['items']:
                if e.get('type') == 'model' and e.get('ok'):
                    out.append('lib\t%s\t%s\t%s\t%s' % (e['id'], (e.get('name') or e['id']).replace('\t', ' '),
                                                        e.get('icon') or '', e.get('file') or ''))
            for p in groups.prefabs():
                out.append('prefab\t%s\t%s\t%d' % (p['file'], p['name'].replace('\t', ' '), len(p['items'])))
                # where each of its objects sits, for the preview that follows the aim in game
                for it in p['items'][:60]:
                    out.append('pfitem\t%s\t%s\t%.1f\t%.1f\t%.1f\t%.4f' % (p['file'], it['id'], float(it.get('dx', 0)),
                                                                        float(it.get('dy', 0)), float(it.get('dz', 0)),
                                                                        float(it.get('rz', 0))))
            p = self.db.project
            for k, rec in (p.records.items() if p else []):
                if rec['tag'] not in ('STAT', 'ACTI', 'CONT', 'MISC', 'DOOR', 'LIGH'):
                    continue
                from project import unb64
                subs = dict((t, d) for t, d in iter_subrecords(unb64(rec['data'])))
                model = zstr(subs.get('MODL', b'')).replace('/', '\\')
                # Library models, and lights made in the mod (recoloured in game, sound sources)
                if model.lower().startswith(library.SUB + '\\') or rec['tag'] == 'LIGH':
                    line = 'librec\t%s\t%s\t%s\t%s' % (zstr(subs.get('NAME', b'')), rec['tag'], ('meshes\\' + model) if model else '',
                                                       zstr(subs.get('FNAM', b'')).replace('\t', ' '))
                    if rec['tag'] == 'LIGH' and len(subs.get('LHDT', b'')) >= 24:
                        # (a light's stand-in needs its colour and reach)
                        _w, _v, _t, radius, r_, g_, b_, _a, flags = struct.unpack('<fiiiBBBBI', subs['LHDT'][:24])
                        line += '\t%d\t%d\t%d\t%d\t%d\t%s' % (radius, r_, g_, b_, flags, zstr(subs.get('SNAM', b'')))
                    out.append(line)
        except Exception as e:
            print('library lines for the game failed:', e)
        return out

    def _arm_library(self, entry_id):
        """Chosen from My Library in the game's build menu: its record in the mod (made now if needed),
        then readied in game like anything chosen in the Workshop."""
        import library
        with self.edit_lock:
            try:
                r = library.make_record(self.db, entry_id)
            except Exception as e:
                self._note('Could not use that Library model: %s' % e)
                return
        e = library.entry(entry_id) or {}
        self.arm_from_workshop(r['id'], e.get('name') or r['id'])

    def _on_placeprefab(self, pf_file, x, y, z, yaw, kind, name):
        import groups
        pf = next((p for p in groups.prefabs() if p['file'] == pf_file), None)
        if not pf:
            self._note('That prefab is gone.')
            return
        key = self._key_for(kind, name, x, y)
        with self.edit_lock:
            try:
                r = groups.place(self.db, key, pf['items'], x, y, z, yaw, pf['name'])
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': r['placed'][-1]['ref'], 'id': '', 'placed': True}
            except Exception as e:
                self._note('Could not place %s: %s' % (pf['name'], e))

    def arm_from_workshop(self, rid, name):
        """Something was chosen in the Workshop: ready it in game too (with its preview)."""
        self.armed = {'id': rid, 'name': name or rid}
        self.tp_seq += 1
        self.arm_line = 'arm\t%d\t%s\t%s' % (self.tp_seq, rid, (name or rid).replace('\t', ' '))
        self.write_state(bump=False)

    def disarm_from_workshop(self):
        """Stop placing in game too (its preview goes away)."""
        self.armed = None
        self.tp_seq += 1
        self.arm_line = 'arm\t%d\t\t' % self.tp_seq
        self.write_state(bump=False)

    def teleport(self, cell_key, x, y, z, yaw=0.0):
        db = self.db
        new_place = self.baseline is not None and cell_key not in self.baseline and not any(
            db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('CELL', cell_key), []) if v not in db.dead)
        if new_place:
            self._spare_for(cell_key)             # made since the game started: go to its spare room
        cell = self._cell_fields(cell_key)
        if not cell:
            raise ValueError('Unknown cell')
        self.tp_seq += 1
        self.tp = 'tp\t%d\t%s\t%.1f\t%.1f\t%.1f\t%.3f' % (self.tp_seq, cell, x, y, z, yaw)
        self.write_state()

    # ------------------------------------------------------------- log follower
    ALT_LOG = None      # the log of a game started with the Workshop's own config folder (a very long load order)

    def _log(self):
        path = os.environ.get('WORKSHOP_GAME_LOG') or os.path.join(self.db.config.get('userdir') or '', 'openmw.log')
        alt = self.ALT_LOG
        try:
            if alt and os.path.exists(alt) and (not os.path.exists(path) or os.path.getmtime(alt) >= os.path.getmtime(path)):
                path = alt
        except OSError:
            pass
        if self._log_path and path != self._log_path:
            self._tail_pos = 0                  # another log now: that game's, from its start
            self.run_linked = False
        self._log_path = path
        return path

    def _tail_loop(self):
        while True:
            time.sleep(0.25)
            try:
                if not self.db.config:
                    continue
                path = self._log()
                if not os.path.exists(path):
                    continue
                size = os.path.getsize(path)
                if self._tail_pos is None:
                    self._tail_pos = size           # start from the end: ignore old sessions
                    # ...but did the game that wrote this log (perhaps still running) have the link?
                    try:
                        with open(path, 'rb') as f:
                            self.run_linked = b'[WSLINK] ' in f.read()
                    except OSError:
                        self.run_linked = None
                    continue
                if size < self._tail_pos:
                    self._tail_pos = 0              # the game restarted and began a new log
                    self.run_linked = False         # (until this run says something)
                if size == self._tail_pos:
                    continue
                with open(path, 'rb') as f:
                    f.seek(self._tail_pos)
                    chunk = f.read(size - self._tail_pos)
                cut = chunk.rfind(b'\n')
                if cut < 0:
                    continue
                self._tail_pos += cut + 1
                for raw in chunk[:cut].split(b'\n'):
                    i = raw.find(b'[WSLINK] ')
                    if i >= 0:
                        self._event(raw[i + 9:].decode('utf-8', 'replace').rstrip('\r').split('\t'))
            except Exception as e:
                print('live link:', e)

    def _event(self, f):
        self.last_seen = self.last_event = time.time()
        self.run_linked = True
        kind = f[0]
        # stand-in records the game made for Library models: the Workshop knows them by their real ids
        aliases = self.__dict__.setdefault('aliases', {})
        if kind in ('pick', 'move', 'del', 'lightcolor') and len(f) > 1:
            f = [f[0], aliases.get(f[1].lower(), f[1])] + list(f[2:])
        if kind == 'alias' and len(f) >= 3:
            aliases[f[1].lower()] = f[2]
            return
        if kind == 'libarm' and len(f) >= 2:
            threading.Thread(target=self._arm_library, args=(f[1],), daemon=True).start()
            return
        if kind == 'placebrush' and len(f) >= 5:
            self._on_placebrush(f[1], f[2], f[3], f[4])
            return
        if kind == 'placeprefab' and len(f) >= 8:
            self._on_placeprefab(f[1], float(f[2]), float(f[3]), float(f[4]), float(f[5]), f[6], f[7])
            return
        if kind == 'pos' and len(f) >= 9:
            self.player = {'kind': f[1], 'name': f[2], 'gx': int(f[3]), 'gy': int(f[4]), 'x': float(f[5]),
                           'y': float(f[6]), 'z': float(f[7]), 'yaw': float(f[8]),
                           'cell': self._key_for(f[1], f[2], float(f[5]), float(f[6]))}
            self._maybe_palette()
        elif kind in ('applied', 'received') and len(f) >= 2:
            setattr(self, kind, int(f[1]))
        elif kind == 'pick' and len(f) >= 9:
            self._on_pick(f[1], float(f[2]), float(f[3]), float(f[4]), f[5], f[6])
        elif kind == 'placeat' and len(f) >= 9:
            if len(f) >= 10 and f[9]:
                self.armed = {'id': f[9], 'name': f[9]}
            exact = len(f) >= 11 and f[10] == 'exact'      # position of the in-game preview, already resting
            scale = _num(f[11]) if len(f) >= 12 else None   # made bigger or smaller in game
            self._on_placeat(float(f[1]), float(f[2]), float(f[3]), float(f[4]), f[5], f[6], exact, scale)
        elif kind == 'arm' and len(f) >= 2:
            self.armed = {'id': f[1], 'name': f[2] if len(f) > 2 else f[1]}
        elif kind == 'disarm':
            self.armed = None             # stopped placing in game (Shift+X)
        elif kind == 'move' and len(f) >= 13:
            self._on_move(f[1], [float(v) for v in f[2:5]], [float(v) for v in f[5:8]], float(f[8]), f[9], f[10],
                          _num(f[13]) if len(f) >= 14 else None)
        elif kind == 'lightcolor' and len(f) >= 11:
            self._on_lightcolor(f[1], float(f[2]), float(f[3]), float(f[4]), f[5], f[6], int(f[7]), int(f[8]), int(f[9]),
                                float(f[10]))
        elif kind == 'del' and len(f) >= 9:
            self._on_delete(f[1], float(f[2]), float(f[3]), float(f[4]), f[5], f[6])
        elif kind == 'undo':
            self._on_undo()
        elif kind == 'error' and len(f) >= 2:
            self._note(f[1])
        elif kind == 'quest' and len(f) >= 4:
            self.game['quests'][f[1].lower()] = {'stage': int(f[2]), 'finished': f[3] == '1'}
        elif kind == 'global' and len(f) >= 3:
            try:
                self.game['globals'][f[1].lower()] = float(f[2])
            except ValueError:
                self.game['globals'][f[1].lower()] = None      # the game doesn't have it
        elif kind == 'item' and len(f) >= 3:
            self.game['items'][f[1].lower()] = int(f[2]) if f[2].lstrip('-').isdigit() else None
        elif kind == 'done' and len(f) >= 3:
            self.done[int(f[1])] = f[2]
            if f[2] != 'ok':
                self._note('The game could not do that: %s' % f[2])
        elif kind == 'hello':
            # a fresh game: anything it shows came from the plugin it loaded
            self.game = self._fresh_game()
            self.write_state()

    def _note(self, text):
        self.messages.append({'t': time.time(), 'text': text})
        del self.messages[:-20]

    def _key_for(self, kind, name, x, y):
        if kind == 'int':
            for key, spare in getattr(self, 'spares', {}).items():
                if spare.lower() == name.lower():
                    return key                    # in a spare room: really the new place it stands for
            return name.lower()
        return '#%d,%d' % (math.floor(x / 8192), math.floor(y / 8192))

    def _find_ref(self, rid, x, y, z, kind, name, limit=150.0):
        """The Workshop's (cell key, ref) for an object the game told us about."""
        key = self._key_for(kind, name, x, y)
        keys = [key]
        if key.startswith('#'):
            gx, gy = (int(v) for v in key[1:].split(','))
            keys += ['#%d,%d' % (gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        best, bd, bk = None, limit, key
        for k in keys:
            for r in mapdata.cellmap(self.db, k).get('refs', []):
                if r['id'].lower() == rid.lower():
                    d = math.dist(r['p'][:3], (x, y, z))
                    if d < bd:
                        best, bd, bk = r, d, k
        return bk, best

    def _on_pick(self, rid, x, y, z, kind, name):
        key, best = self._find_ref(rid, x, y, z, kind, name)
        self.pick_seq += 1
        self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': best['k'] if best else None, 'id': rid}

    def _on_move(self, rid, orig, new, yaw, kind, name, scale=None):
        import editing
        key, r = self._find_ref(rid, orig[0], orig[1], orig[2], kind, name)
        if not r:
            self._note('Moved %s in game, but could not find it in the Workshop.' % rid)
            return
        p = list(r['p'])
        p[0], p[1], p[2], p[5] = new[0], new[1], new[2], yaw
        if scale is not None and abs(scale - (r.get('s') or 1.0)) < 0.001:
            scale = None                                   # (its size didn't change)
        with self.edit_lock:
            try:
                editing.move_ref(self.db, key, r['k'], p, scale)
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': r['k'], 'id': rid, 'moved': True}
            except Exception as e:
                self._note('Could not move %s: %s' % (rid, e))

    def _on_delete(self, rid, x, y, z, kind, name):
        import editing
        key, r = self._find_ref(rid, x, y, z, kind, name, limit=40.0)
        if not r:
            self._note('Could not find %s in the Workshop to remove it.' % rid)
            return
        with self.edit_lock:
            try:
                editing.delete_ref(self.db, key, r['k'])
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': None, 'id': rid, 'deleted': True}
            except Exception as e:
                self._note('Could not remove %s: %s' % (rid, e))

    def _on_undo(self):
        import editing
        with self.edit_lock:
            try:
                undone = editing.undo(self.db)
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': (self.player or {}).get('cell'), 'ref': None,
                             'id': '', 'undone': undone[0] if undone else ''}
            except Exception as e:
                self._note(str(e))

    # ------------------------------------------------------------- suggestions for the in-game menu
    def _maybe_palette(self):
        cell = (self.player or {}).get('cell')
        if not cell or cell == getattr(self, '_palette_cell', None) or getattr(self, '_palette_busy', False):
            return
        self._palette_cell = cell
        self._palette_busy = True

        def work():
            try:
                pal = mapdata.palette(self.db, cell, limit=30)
                lines = []
                for g in pal.get('groups', []):
                    for it in g['items']:
                        name = (it['name'] or '').replace('\t', ' ')
                        lines.append('palette\t%s\t%s\t%s' % (it['id'], name, g['name']))
                # brushes for painting in game: what grows in this region (outdoors) and your own
                try:
                    lines += self._brush_lines(cell)
                except Exception as e:
                    print('brushes for game failed:', e)
                self.palette_lines = lines
                self.write_state(bump=False)
            except Exception as e:
                print('palette for game failed:', e)
            finally:
                self._palette_busy = False
        threading.Thread(target=work, daemon=True).start()

    BRUSH_GAP = {'grass': 110, 'plants': 200, 'rocks': 380, 'trees': 650, 'logs': 700}

    def _brush_lines(self, cell):
        import scatter
        sets = scatter.sets(self.db, cell).get('sets', [])
        self.brush_sets = {s['key']: s for s in sets}
        return ['brush\t%s\t%s\t%d\t%d' % (s['key'], s['label'].replace('\t', ' '),
                                           s.get('gap') or self.BRUSH_GAP.get(s['key'], 200), len(s['items']))
                for s in sets if s.get('items')]

    def _on_placebrush(self, set_key, kind, name, pts_text):
        """A patch painted with a brush in game: the game found the ground at each spot; what goes on
        each (the brush's mix), its size and turn are picked here, as the Workshop's own brush does."""
        import groups
        pts = []
        for p in pts_text.split(';'):
            try:
                x, y, z = (float(v) for v in p.split(','))
                pts.append((x, y, z))
            except ValueError:
                continue
        if not pts:
            return
        key = self._key_for(kind, name, pts[0][0], pts[0][1])
        st = getattr(self, 'brush_sets', {}).get(set_key)
        if not st:
            try:
                self._brush_lines(key)
                st = self.brush_sets.get(set_key)
            except Exception:
                st = None
        if not st or not st.get('items'):
            self._note('That brush is gone.')
            return
        items = st['items']
        total = sum(max(1, i.get('n', 1)) for i in items)
        outdoors = key.startswith('#')
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        rows = []
        for x, y, z in pts:
            pick, it = random.random() * total, items[0]
            for i in items:
                pick -= max(1, i.get('n', 1))
                if pick <= 0:
                    it = i
                    break
            s = it['smin'] + random.random() * max(0.0, it['smax'] - it['smin'])
            sink = it.get('sink', 0.0) if outdoors else 0.0
            rows.append({'id': it['id'], 'lib': it.get('lib'), 'type': 'STAT' if it.get('lib') else None,
                         'dx': x - cx, 'dy': y - cy, 'dz': z - sink * s - it.get('zmin', 0.0) * s,
                         'rz': random.random() * math.pi * 2, 's': round(s, 2)})
        with self.edit_lock:
            try:
                r = groups.place(self.db, key, rows, cx, cy, 0.0, 0.0, st['label'].lower())
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': r['placed'][-1]['ref'], 'id': '', 'placed': True}
            except Exception as e:
                self._note('Could not paint with %s: %s' % (st['label'], e))

    def _on_placeat(self, x, y, z, yaw, kind, name, exact=False, scale=None):
        import editing
        if not self.armed:
            self._note('Pick something to place in the Workshop first (search or palette), then press Shift+J.')
            return
        key = self._key_for(kind, name, x, y)
        ri = self.db.resolve_id(self.armed['id'])
        b = mapdata.object_bounds(self.db, ri) if ri is not None else None
        s = max(0.5, min(2.0, scale)) if scale else 1.0
        z0 = z if exact else z - (b[2] * s if b else 0.0)      # rest the object's bottom on the surface
        with self.edit_lock:
            try:
                rk = editing.place_ref(self.db, key, self.armed['id'], [x, y, z0, 0, 0, yaw], s)
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': rk, 'id': self.armed['id'], 'placed': True}
            except Exception as e:
                self._note('Could not place %s: %s' % (self.armed['id'], e))

    def _on_lightcolor(self, rid, x, y, z, kind, name, r, g, b, mul):
        """A light recoloured (or made brighter / dimmer) in game. Colour belongs to the kind of light,
        so this lamp gets a light record of its own with the new colour (made once, then reused)."""
        import editing
        from esm import iter_subrecords
        key, ref = self._find_ref(rid, x, y, z, kind, name, limit=40.0)
        ri = self.db.resolve_id(rid)
        if not ref or ri is None or self.db.recs[ri][0] != 'LIGH':
            self._note('Could not find that light in the Workshop.')
            return
        rec = self.db.recs[ri]
        _t, _flags, data = self.db.files[rec[3]].record_at(rec[4])
        subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
        lh = next((d for t, d in subs if t == 'LHDT'), None)
        if not lh or len(lh) < 24:
            self._note('%s has no light settings to change.' % rid)
            return
        w, v, tm, radius, r0, g0, b0, a0, flags = struct.unpack('<fiiiBBBBI', lh[:24])
        if r < 0:
            r, g, b = r0, g0, b0
        radius = int(max(16, min(4096, round(radius * mul))))
        if abs(mul - 1) < 0.001 and (r, g, b) == (r0, g0, b0):
            return                                          # (nothing to change)
        # the same base light in the same colour and reach: one record, reused
        base = re.sub(r'_c[0-9a-f]{6}(_r\d+)?$', '', rid.lower())
        base_radius = radius
        bi = self.db.resolve_id(base)
        if bi is not None and self.db.recs[bi][0] == 'LIGH':
            bd = next((d for t, d in iter_subrecords(self.db.files[self.db.recs[bi][3]].record_at(self.db.recs[bi][4])[2])
                       if t == 'LHDT'), None)
            if bd and len(bd) >= 16:
                base_radius = struct.unpack_from('<i', bd, 12)[0]
        tail = '_c%02x%02x%02x' % (r, g, b) + ('_r%d' % radius if radius != base_radius else '')
        new_id = base[:31 - len(tail)] + tail                # (IDs can be 31 letters long)
        new_lh = struct.pack('<fiiiBBBBI', w, v, tm, radius, r, g, b, a0, flags) + lh[24:]
        with self.edit_lock:
            try:
                have = self.db.resolve_id(new_id)
                p = self.db.project
                if have is None or p.records.get('LIGH|%s' % new_id.lower()):
                    out = [(t, zs(new_id) if t == 'NAME' else (new_lh if t == 'LHDT' else d)) for t, d in subs]
                    p.set_record('LIGH', new_id.lower(), 0, join_subs(out), created=have is None)
                    self.db.sync_project()
                elif self.db.recs[have][0] != 'LIGH':
                    raise ValueError('the name %s is taken' % new_id)
                editing.swap_ref(self.db, key, ref['k'], new_id)
                self.pick_seq += 1
                self.pick = {'seq': self.pick_seq, 'cell': key, 'ref': ref['k'], 'id': new_id, 'placed': True}
            except Exception as e:
                self._note('Could not change the light: %s' % e)

    def status(self):
        self.resume()
        return {'connected': self.connected(), 'paused': self.paused(), 'session': self.session is not None,
                'unlinked_game': self.unlinked_game(),
                'player': self.player,
                'version': self.version, 'applied': self.applied, 'received': self.received,
                'pick': self.pick, 'armed': self.armed, 'waiting': getattr(self, 'waiting', []),
                'spares': [{'cell': k, 'name': editing_label(self.db, k), 'spare': v}
                           for k, v in sorted(getattr(self, 'spares', {}).items(), key=lambda kv: kv[1])],
                'messages': [m['text'] for m in self.messages if time.time() - m['t'] < 30],
                'game': self.game, 'done': {str(k): v for k, v in list(self.done.items())[-30:]}}

    def in_game(self, tag, key):
        """Did the running game load this record (from a master, or the mod as it was at the start)?"""
        db = self.db
        lst = [v for v in db.by_key.get((tag, key.lower()), []) if v not in db.dead]
        if any(db.recs[v][3] != db.proj_pidx for v in lst):
            return True
        return ('%s|%s' % (tag, key.lower())) in set(getattr(self, 'baseline_records', []) or [])
