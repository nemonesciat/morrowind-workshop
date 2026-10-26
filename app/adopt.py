"""Open an existing plugin (.esp or .omwaddon) as the mod itself.

A mod made in the Workshop is always its own plugin, written afresh from the project. Here an existing
file becomes the project instead: its records are the project's records (its new ones marked as made
here, its changes to a master's records as changes), its places carry the file's cell headers and its
own placed objects as the project's own, with the SAME object indices the file gave them (saved games
remember placed objects by that index, so new objects get indices above the file's highest), its edits of
a master's objects stay edits of those masters, and the file's masters (names and sizes), author and
description are kept. From then on the Workshop saves straight into that file after every change, as it
does with a mod of its own: a dated copy is made beside the file when it is opened, and later copies go
under Backups. A master file (.esm) is refused: make a plugin that changes it instead.

What a plain .esp cannot hold is OpenMW's own: Lua scripts, their .omwscripts list and the script that
carries things on a sliding panel. They stay in the project (Scripts page and Get ready to share say so)
and are written out only for a .omwaddon."""
import json
import os
import shutil
import struct
import subprocess
import time

from esm import PluginFile, iter_subrecords, zstr
from editing import EditError
from project import PROJECTS_DIR, Project, b64, safe_name, state_diff
import database

MASTER_EXTS = ('.esm', '.omwgame')
PLUGIN_EXTS = ('.esp', '.omwaddon')


def _header(pf):
    """version, kind (1 = master), author, description, [(master, size)] from the file's TES3 header."""
    size = struct.unpack_from('<I', pf.mm, 4)[0]
    out = {'version': 1.3, 'kind': 0, 'author': '', 'description': '', 'masters': [], 'hedr_raw': None}
    last = None
    for st, sd in iter_subrecords(pf.mm[16:16 + size]):
        if st == 'HEDR' and len(sd) >= 300:
            out['hedr_raw'] = bytes(sd[:300])
            out['version'] = round(struct.unpack_from('<f', sd, 0)[0], 2)
            out['kind'] = struct.unpack_from('<I', sd, 4)[0]
            out['author'] = zstr(sd[8:40])
            out['description'] = zstr(sd[40:296])
        elif st == 'MAST':
            last = [zstr(sd), 0]
            out['masters'].append(last)
        elif st == 'DATA' and last is not None and len(sd) >= 8:
            last[1] = struct.unpack_from('<Q', sd)[0]
            last = None
    return out


def record_key(db, tag, data, dial_id=''):
    """The key the Workshop files a record under (as database._parse_plugin does), so a record of the
    file and a later edit of the same thing meet in one place."""
    if tag == 'CELL':
        return db._cell_info(data)[3]
    if tag == 'LAND':
        xy = struct.unpack_from('<ii', data, 8) if data[:4] == b'INTV' else (0, 0)
        return '%d,%d' % xy
    if tag == 'PGRD':
        rid = database._id_of(tag, data[:200])[0]
        dd = data.find(b'DATA')
        gx = struct.unpack_from('<ii', data, dd + 8) if dd >= 0 else (0, 0)
        if not rid:
            rid = '%d, %d' % gx
        return ('#%d,%d' % gx) if gx != (0, 0) else rid.lower()
    if tag == 'INFO':
        inam = ''
        for st, sd in iter_subrecords(data):
            if st == 'INAM':
                inam = zstr(sd)
                break
        return (dial_id + '|' + inam).lower()
    return database._id_of(tag, data)[0].lower()


def cell_from(data, flags, own, masters_lower):
    """A CELL record's data as a project place: {flags, header, refs}. The file's own objects keep their
    index (key "<file>|<idx>"), a master's objects are keyed by the master ("<master>|<idx>"). Objects
    written before NAM0 (the ones the game keeps track of: doors, people) are marked 'pers', so the file
    is written back the same way. Returns (place, NAM0 the file wrote, highest own index, [problems])."""
    header, refs, problems = [], {}, []
    cur, moved, nam0, own_max = None, None, None, 0
    for t, d in iter_subrecords(data):
        d = bytes(d)
        if t == 'FRMR':
            frmr = struct.unpack_from('<I', d)[0] if len(d) >= 4 else 0
            upper, idx = frmr >> 24, frmr & 0xFFFFFF
            if upper == 0:
                origin = own
                own_max = max(own_max, idx)
            elif upper <= len(masters_lower):
                origin = masters_lower[upper - 1]
            else:
                origin = '?%d' % upper
                problems.append('an object of master #%d, which the file does not list' % upper)
            cur = {'origin': origin, 'idx': idx, 'subs': [], 'deleted': False}
            if nam0 is None:
                cur['pers'] = True
            if moved:
                cur['mvrf'] = moved
            moved = None
            key = '%s|%d' % (origin, idx)
            if key in refs:
                problems.append('object %s twice in one place' % key)
            refs[key] = cur
        elif t == 'MVRF':
            cur, moved = None, [['MVRF', b64(d)]]
        elif moved is not None and cur is None and t in ('CNDT', 'CNAM'):
            moved.append([t, b64(d)])
        elif t == 'NAM0':
            nam0 = struct.unpack_from('<I', d)[0] if len(d) >= 4 else None
        elif cur is None:
            header.append([t, b64(d)])
        else:
            cur['subs'].append([t, b64(d)])
            if t == 'DELE':
                cur['deleted'] = True
    c = {'flags': flags, 'header': header, 'refs': refs}
    if not refs:
        c['props'] = True        # (a place whose settings alone the file changes, or a new empty place: written all the same)
    return c, nam0, own_max, problems


def read_plugin(db, path):
    """Everything the file holds, as a project: records, cells, next_ref, header, and what was odd about it."""
    try:
        pf = PluginFile(path)
    except (ValueError, OSError) as e:
        raise EditError('%s could not be read as a Morrowind plugin: %s' % (os.path.basename(path), e))
    try:
        head = _header(pf)
        own = os.path.basename(path).lower()
        masters_lower = [m[0].lower() for m in head['masters']]
        # which plugins in the load order are this file's masters (a record they define is a change, not new)
        master_pidx = {db.plugin_index(m) for m in masters_lower} - {None}
        records, cells, problems, order = {}, {}, [], []
        dial_id, own_max, n_refs, n_master_refs, dupes = '', 0, 0, 0, 0
        for tag, _off, flags, data in pf.records():
            data = bytes(data)
            if tag == 'CELL':
                key = db._cell_info(data)[3]
                c, nam0, cmax, probs = cell_from(data, flags, own, masters_lower)
                problems += ['%s: %s' % (key, x) for x in probs]
                if key in cells:
                    dupes += 1
                else:
                    order.append('CELL|' + key)
                cells[key] = c
                own_max = max(own_max, cmax)
                n_refs += sum(1 for r in c['refs'].values() if r['origin'] == own)
                n_master_refs += sum(1 for r in c['refs'].values() if r['origin'] != own)
                continue
            key = record_key(db, tag, data, dial_id)
            if tag == 'DIAL':
                dial_id = database._id_of(tag, data)[0]
            k = tag + '|' + key
            if k in records:
                dupes += 1
            else:
                order.append(k)
            defined = any(v not in db.dead and db.recs[v][3] in master_pidx for v in db.by_key.get((tag, key), []))
            records[k] = {'tag': tag, 'key': key, 'flags': flags, 'data': b64(data), 'created': not defined}
        if dupes:
            problems.append('%d records or objects the file holds twice (the later one is kept)' % dupes)
        return {'head': head, 'records': records, 'cells': cells, 'order': order, 'next_ref': own_max + 1, 'own_refs': n_refs,
                'master_refs': n_master_refs, 'problems': problems,
                'missing_masters': [m[0] for m in head['masters'] if db.plugin_index(m[0].lower()) is None]}
    finally:
        pf.close()


def _existing(ppath):
    try:
        with open(ppath, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def adopt(db, path):
    """Make (or remake) the project for this file and return it, with a summary. The caller makes it the
    open mod and reads the game data again. One Undo step takes the opening back (the project is then
    empty, and the file is left as it is until Redo)."""
    path = os.path.abspath((path or '').strip())
    if not os.path.isfile(path):
        raise EditError('There is no file at %s.' % (path or '(nothing chosen)'))
    file_name = os.path.basename(path)
    base, ext = os.path.splitext(file_name)
    if ext.lower() in MASTER_EXTS:
        raise EditError('%s is a master file. The Workshop edits plugins (.esp and .omwaddon): to change a master, '
                        'start a mod of your own and make the changes in it.' % file_name)
    if ext.lower() not in PLUGIN_EXTS:
        raise EditError('%s is not a Morrowind plugin: pick a .esp or .omwaddon file.' % file_name)
    if db.project and getattr(db.project, 'source', None) and \
            os.path.normcase(os.path.abspath(db.project.source)) == os.path.normcase(path):
        raise EditError('%s is the mod that is open already.' % file_name)
    if db.project and not getattr(db.project, 'source', None) and db.project.plugin.lower() == file_name.lower():
        raise EditError('%s is the file of the mod that is open already (%s).' % (file_name, db.project.name))
    read = read_plugin(db, path)
    head = read['head']
    if head['kind'] & 1:
        raise EditError('%s is marked as a master file inside, whatever its name. The Workshop edits plugins: '
                        'start a mod of your own and make the changes in it.' % file_name)
    pname = safe_name(base)
    ppath = os.path.join(PROJECTS_DIR, pname + '.json')
    old = _existing(ppath) if os.path.exists(ppath) else None
    if old is not None and os.path.normcase(os.path.abspath(old.get('source') or '')) != os.path.normcase(path):
        raise EditError('There is already a mod called "%s" in the Workshop that is not this file. Rename the file, '
                        'or that mod\'s project under Mods, first.' % pname)
    # the dated copy beside the file, once; the project remembers where it went
    backup = (old or {}).get('plugin_backup')
    if not backup or not os.path.isfile(backup):
        backup = '%s.%s.bak' % (path, time.strftime('%Y-%m-%d %H-%M-%S'))
        shutil.copy2(path, backup)
    # what the file cannot hold stays with the project it had before (Lua scripts, grass, the release notes)
    old = old or {}
    d = {'name': pname, 'plugin': file_name, 'author': head['author'][:31], 'description': head['description'][:255],
         'records': read['records'], 'cells': read['cells'], 'next_ref': max(read['next_ref'], 1),
         'log': old.get('log', []), 'release': old.get('release', {}), 'lua': old.get('lua', []),
         'lua_files': old.get('lua_files', []), 'grass': old.get('grass', {}),
         'source': path, 'masters': head['masters'], 'tes3_version': head['version'], 'plugin_backup': backup,
         'order': read['order'], 'hedr': b64(head['hedr_raw']) if head.get('hedr_raw') else None}
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    tmp = ppath + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f)
    os.replace(tmp, ppath)
    p = Project(ppath)
    # opening the file is one Undo step: before it, the project was empty
    empty = json.dumps({'records': {}, 'cells': {}, 'next_ref': p.next_ref, 'lua': p.lua, 'grass': p.grass})
    n_rec, n_cells = len(p.records), len(p.cells)
    note = 'Opened %s as this mod (%s record%s, %s place%s, %s object%s)' % (
        file_name, format(n_rec, ','), '' if n_rec == 1 else 's', format(n_cells, ','), '' if n_cells == 1 else 's',
        format(read['own_refs'], ','), '' if read['own_refs'] == 1 else 's')
    entry = p.note(note, state_diff(empty, p.state()))
    p.undo_stack = [(empty, note, entry['id'])]
    p.save()
    return {'ok': True, 'project': p, 'name': pname, 'plugin': file_name, 'path': path, 'backup': backup,
            'records': n_rec, 'places': n_cells, 'objects': read['own_refs'], 'master_objects': read['master_refs'],
            'masters': [m[0] for m in head['masters']], 'missing_masters': read['missing_masters'],
            'problems': read['problems'], 'reopened': bool(old), 'plain_esp': not p.lua_allowed(),
            'lua_kept': len(p.lua), 'note': note}


def _cfg_rename(db, old, new):
    """openmw.cfg: a content= or groundcover= line naming the old file now names the new one (backup first)."""
    cfg = (db.config or {}).get('user_cfg')
    if not cfg or not os.path.isfile(cfg):
        return False
    with open(cfg, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8', errors='replace')
    lines, changed = [], False
    for line in text.splitlines():
        k, _s, v = line.partition('=')
        if k.strip().lower() in ('content', 'groundcover') and v.strip().lower() == old.lower():
            line = k + '=' + new
            changed = True
        lines.append(line)
    if not changed:
        return False
    nl = '\r\n' if '\r\n' in text else '\n'
    shutil.copy2(cfg, cfg + '.workshop-backup-' + time.strftime('%Y%m%d-%H%M%S'))
    tmp = cfg + '.workshop-new'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(nl.join(lines) + nl)
    os.replace(tmp, cfg)
    db.cfg_content_all = [new if c.lower() == old.lower() else c for c in getattr(db, 'cfg_content_all', [])]
    return True


def save_as(db, name, ext, overwrite=False):
    """The Construction Set's Save As: the mod's changes go into a new file (<name>.esp or .omwaddon in your mods
    folder), which is the active file from then on. The mod's own objects keep their numbers under the new name;
    the old file of a mod made here is renamed away (and the load order follows); a file opened as the mod stays
    as it was. The Undo history starts afresh (a backup of the project is kept first)."""
    import editing
    p = db.project
    if not p:
        raise EditError('Start a mod, or open a file as your mod, first.')
    name = (name or '').strip()
    if name.lower().endswith(PLUGIN_EXTS):
        name = os.path.splitext(name)[0]
    if not name.strip() or not any(c.isalnum() for c in name):
        raise EditError('Give the file a name.')
    name = safe_name(name)
    ext = (ext or '').lower().strip()
    if not ext.startswith('.'):
        ext = '.' + ext
    if ext not in PLUGIN_EXTS:
        raise EditError('Save as .esp or .omwaddon.')
    new_file = name + ext
    old_file = p.plugin
    old_path = editing.plugin_path(db)
    folder = os.path.dirname(old_path) if p.source else (os.environ.get('WORKSHOP_PLUGIN_DIR') or db.config.get('data_local')
                                                        or os.path.join(db.config['userdir'], 'data'))
    new_path = os.path.join(folder, new_file)
    if os.path.normcase(os.path.abspath(new_path)) == os.path.normcase(os.path.abspath(old_path)):
        raise EditError('%s is the file this mod saves into already.' % new_file)
    if db.plugin_index(new_file.lower()) is not None and not overwrite:
        raise EditError('%s is in your load order: the mod would be loaded twice. Pick another name, or switch that file off first.' % new_file)
    if os.path.exists(new_path) and not overwrite:
        raise EditError('There is a %s in %s already. Pick another name, or tick "write over it".' % (new_file, folder))
    editing.flush(db)
    import backups
    backups.maybe_backup(p, force=True, why='before save as')
    backup = None
    if os.path.exists(new_path):
        backup = '%s.%s.bak' % (new_path, time.strftime('%Y-%m-%d %H-%M-%S'))
        shutil.copy2(new_path, backup)
    # the mod's own objects under the new name, same numbers
    old_low, new_low = old_file.lower(), new_file.lower()
    n_rekeyed = 0
    for c in p.cells.values():
        refs = {}
        for k, r in c['refs'].items():
            if r.get('origin') == old_low:
                r = dict(r, origin=new_low)
                k = '%s|%d' % (new_low, r['idx'])
                n_rekeyed += 1
            if isinstance(r.get('on'), str) and r['on'].lower().startswith(old_low + '|'):
                r = dict(r, on=new_low + r['on'][len(old_low):])
            refs[k] = r
        c['refs'] = refs
    was_own = not p.source
    old_grass = None
    try:
        import grass
        old_grass = grass.file_path(db) if getattr(p, 'grass', None) else None
    except Exception:
        pass
    p.plugin = new_file
    p.source = new_path
    p.plugin_backup = backup
    if was_own:
        p.order = []                       # (written in the Workshop's own order, new things after)
    # the Undo history would put objects back under the old name: it starts afresh, as after a merge
    p.undo_stack = []
    p.redo_stack = []
    for e in p.log:
        e.pop('diff', None)
    p.note('Saved as %s%s' % (new_file, ' (was %s)' % old_file if old_file.lower() != new_low else ''))
    p.last_state = p.state()
    p.save()
    db.sync_project()
    editing.build(db)                      # (the new file, written now)
    moved_old = cfg_changed = False
    if was_own:
        # the old file was the Workshop's own output: it goes, or the game would load the mod twice
        try:
            os.remove(old_path)
            moved_old = True
        except OSError:
            pass
        if old_grass and os.path.isfile(old_grass):
            try:
                os.replace(old_grass, grass.file_path(db))
            except OSError:
                pass
    # the load order follows the new name (a file that was opened as the mod stays on disk, switched off:
    # loaded beside the new file, the game would show everything twice)
    cfg_changed = _cfg_rename(db, old_file, new_file)
    try:
        _cfg_rename(db, os.path.splitext(old_file)[0] + ' Grass.omwaddon', os.path.splitext(new_file)[0] + ' Grass.omwaddon')
    except OSError:
        pass
    return {'ok': True, 'plugin': new_file, 'path': new_path, 'was': old_file, 'rekeyed': n_rekeyed, 'backup': backup,
            'old_removed': moved_old, 'cfg_changed': cfg_changed, 'plain_esp': not p.lua_allowed(), 'lua_kept': len(p.lua),
            'reload': True}


def candidates(db):
    """Plugins in the data folders that could be opened as the mod: from the load order page's lists, with
    where they are; the open mod's own file left out."""
    import loadorder
    info = loadorder.read(db)
    mine = db.project.plugin.lower() if db.project else None
    src = os.path.normcase(os.path.abspath(db.project.source)) if db.project and getattr(db.project, 'source', None) else None
    out = []
    for on, rows in ((True, info['enabled']), (False, info['available'])):
        for r in rows:
            if r['kind'] not in ('esp', 'omwaddon') or not r.get('found') or r['name'].lower() == mine:
                continue
            path = os.path.join(r['folder'], r['name'])
            if src and os.path.normcase(os.path.abspath(path)) == src:
                continue
            pname = safe_name(os.path.splitext(r['name'])[0])
            ex = _existing(os.path.join(PROJECTS_DIR, pname + '.json')) if os.path.exists(os.path.join(PROJECTS_DIR, pname + '.json')) else None
            out.append({'name': r['name'], 'folder': r['folder'], 'path': path, 'enabled': on, 'masters': r.get('masters', []),
                        'size': os.path.getsize(path) if os.path.isfile(path) else 0,
                        'adopted': bool(ex and os.path.normcase(os.path.abspath(ex.get('source') or '')) == os.path.normcase(os.path.abspath(path))),
                        'clash': bool(ex) and not (ex.get('source') and os.path.normcase(os.path.abspath(ex.get('source'))) == os.path.normcase(os.path.abspath(path)))})
    return {'plugins': out, 'data_dirs': (db.config or {}).get('data', [])}


def pick_file(db):
    """Ask for a plugin file with Windows' own file picker (nothing is opened yet). {path} or {cancelled}."""
    start = (db.config or {}).get('data_local') or os.path.join((db.config or {}).get('userdir', ''), 'data')
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; "
          "$d.Title = 'Open a plugin as your mod'; $d.Filter = 'Morrowind plugins (*.esp;*.omwaddon)|*.esp;*.omwaddon|All files (*.*)|*.*'; "
          "$d.InitialDirectory = '%s'; "
          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
          "if ($d.ShowDialog($o) -eq 'OK') { $d.FileName }") % start.replace("'", "''")
    r = subprocess.run(['powershell', '-NoProfile', '-STA', '-Command', ps], capture_output=True, text=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    path = (r.stdout or '').strip()
    if not path:
        return {'ok': False, 'cancelled': True}
    known = {os.path.normcase(os.path.abspath(d)) for d in (db.config or {}).get('data', [])}
    return {'ok': True, 'path': path, 'name': os.path.basename(path),
            'in_data': os.path.normcase(os.path.abspath(os.path.dirname(path))) in known}
