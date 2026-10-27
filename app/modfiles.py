"""Your mods' files on disk (My mod > Your mods, 2026-10-23): where each mod's plugin is, a "Show folder" that
opens the file manager with the file picked out, and deleting a mod you no longer want (the user's "deleting excessive
test mods is something I need to do too").

Deleting never destroys anything: the mod's project, its plugin, its Lua scripts' list and folder and its grass
plugin go to the Recycle Bin (the bin on Linux), where they can be restored, and the mod is taken out of openmw.cfg's
load order (a dated copy of openmw.cfg is kept first) so the game doesn't stop at a missing file. The mod
open now can't be deleted (switch to another first); a mod opened from someone's .esp (adopt.py) keeps that
.esp unless asked, since the file was there before the Workshop."""
import json
import os
import re
import shutil
import time

from editing import EditError

_info = {}                  # project path -> (mtime, size, plugin, source)


def _dirs(db):
    from project import PROJECTS_DIR
    plug = os.environ.get('WORKSHOP_PLUGIN_DIR') or db.config.get('data_local') or \
        os.path.join(db.config.get('userdata') or db.config['userdir'], 'data')
    return PROJECTS_DIR, plug


def _read(path):
    st = os.stat(path)
    got = _info.get(path)
    if got and got[0] == st.st_mtime and got[1] == st.st_size:
        return got[2], got[3]
    plugin = source = None
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        plugin, source = d.get('plugin'), d.get('source')
    except (OSError, ValueError):
        pass
    _info[path] = (st.st_mtime, st.st_size, plugin, source)
    return plugin, source


def _files(db, name):
    """(project file, plugin file, the other files the Workshop wrote for it, adopted?) of one mod."""
    pdir, plug = _dirs(db)
    pj = os.path.join(pdir, os.path.basename(name) + '.json')
    if not os.path.isfile(pj):
        raise EditError('There is no mod called "%s".' % name)
    plugin, source = _read(pj)
    plugin = plugin or (name + '.omwaddon')
    pfile = source or os.path.join(plug, plugin)
    base = os.path.splitext(plugin)[0]
    folder = os.path.dirname(pfile)
    slug = re.sub(r'[^a-z0-9_]+', '_', base.lower()).strip('_') or 'mymod'
    extra = [os.path.join(folder, base + '.omwscripts'), os.path.join(folder, base + ' Grass.omwaddon'),
             os.path.join(folder, 'scripts', slug)]
    return pj, pfile, [x for x in extra if os.path.exists(x)], bool(source)


def _cfg(db):
    return os.path.join(db.config['userdir'], 'openmw.cfg')


def _cfg_lines(db):
    try:
        with open(_cfg(db), encoding='utf-8', errors='replace') as f:
            return f.read().splitlines()
    except OSError:
        return []


def mods(db):
    """[{name, plugin, file, folder, exists, size, modified, current, adopted, in_load_order}], newest first."""
    pdir, _plug = _dirs(db)
    cur = os.path.abspath(db.project.path).lower() if db.project else ''
    have = {l.strip().lower() for l in _cfg_lines(db)}
    out = []
    for f in (os.listdir(pdir) if os.path.isdir(pdir) else []):
        if not f.endswith('.json'):
            continue
        name = f[:-5]
        try:
            pj, pfile, _extra, adopted = _files(db, name)
        except EditError:
            continue
        exists = os.path.isfile(pfile)
        st = os.stat(pfile) if exists else os.stat(pj)
        out.append({'name': name, 'plugin': os.path.basename(pfile), 'file': pfile, 'folder': os.path.dirname(pfile),
                    'exists': exists, 'size': st.st_size if exists else 0,
                    'modified': time.strftime('%Y-%m-%d %H:%M', time.localtime(max(st.st_mtime, os.path.getmtime(pj)))),
                    'stamp': max(st.st_mtime, os.path.getmtime(pj)),
                    'current': os.path.abspath(pj).lower() == cur, 'adopted': adopted,
                    'in_load_order': ('content=' + os.path.basename(pfile)).lower() in have})
    out.sort(key=lambda m: (not m['current'], -m['stamp']))
    return out


def show(db, name=None):
    """Explorer at the mod's plugin, picked out (the mod open now when no name is given)."""
    if name:
        _pj, pfile, _extra, _a = _files(db, name)
    else:
        if not db.project:
            raise EditError('Start or open a mod first.')
        import editing
        pfile = editing.plugin_path(db)
    import osplat
    if not os.path.isfile(pfile):
        os.makedirs(os.path.dirname(pfile), exist_ok=True)
    return {'ok': osplat.show_in_folder(pfile), 'path': pfile}


def _recycle(paths):
    """Send files and folders to the bin (restorable). Raises when that fails."""
    import osplat
    try:
        osplat.to_trash(paths)
    except OSError as e:
        raise EditError('%s. Is one of them open in the game or another program?' % (
            str(e) or 'Those files could not be moved to the %s' % osplat.trash_name()))


def delete(db, name, plugin_too=True):
    """Send a mod to the Recycle Bin (its project, plugin, Lua and grass files) and take it out of the load order."""
    pj, pfile, extra, adopted = _files(db, name)
    if db.project and os.path.abspath(pj).lower() == os.path.abspath(db.project.path).lower():
        raise EditError('"%s" is the mod open now. Switch to another one first, then delete it.' % name)
    gone = [pj] + extra
    if os.path.isfile(pfile) and (plugin_too or not adopted):
        gone.append(pfile)
    names = {os.path.basename(p).lower() for p in gone if os.path.isfile(p)}
    _recycle([p for p in gone if os.path.exists(p)])
    # out of the load order (a dated copy of openmw.cfg first), so OpenMW doesn't stop at a missing file
    lines, cfg_changed, backup = _cfg_lines(db), 0, None
    keep = []
    for l in lines:
        m = re.match(r'\s*(content|groundcover)\s*=\s*(.+?)\s*$', l, re.I)
        if m and m.group(2).strip('"').lower() in names:
            cfg_changed += 1
            continue
        keep.append(l)
    if cfg_changed:
        backup = _cfg(db) + '.workshop-backup-' + time.strftime('%Y%m%d-%H%M%S')
        shutil.copy2(_cfg(db), backup)
        with open(_cfg(db), 'w', encoding='utf-8') as f:
            f.write('\n'.join(keep) + '\n')
        try:
            db.cfg_content_all[:] = [c for c in db.cfg_content_all if c.lower() not in names]
        except Exception:
            pass
    _info.pop(pj, None)
    return {'ok': True, 'name': name, 'recycled': [os.path.basename(p) for p in gone],
            'kept_plugin': os.path.basename(pfile) if (adopted and not plugin_too and os.path.isfile(pfile)) else None,
            'load_order_lines': cfg_changed, 'cfg_backup': backup}
