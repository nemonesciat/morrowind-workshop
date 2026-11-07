"""Automatic backups of your projects: a copy of the project file when you open it and then every
few minutes while you work (the newest few dozen are kept), so a bad change or a broken file is
never the end of a mod. Restoring one first backs up how things are now, so it can be undone too.

Backups live in backups\\<project name>\\ next to the projects folder."""
import gzip
import os
import re
import shutil
import time

from project import APP_DIR, load_settings

BACKUP_DIR = os.path.join(APP_DIR, 'backups')
DEFAULT_KEEP = 30
DEFAULT_MINUTES = 10
DEFAULT_MB = 0                 # (space for one mod's backups at most, 0: no limit; the oldest go first)
DEFAULT_ZIP = False            # (backups stored gzipped: a project file packs to about a tenth; a 28 MB mod's 30 backups
                               # took 235 MB, the user 2026-11-06)
_last = {}          # project file -> when it was last backed up


def _dir_for(project):
    return os.path.join(BACKUP_DIR, re.sub(r'[^A-Za-z0-9 _-]', '_', project.name))


def settings():
    s = load_settings()
    keep = s.get('backup_keep', DEFAULT_KEEP)
    minutes = s.get('backup_minutes', DEFAULT_MINUTES)
    return max(1, min(500, int(keep))), max(1, min(240, int(minutes)))


def more_settings():
    """(MB at most for a mod's backups, 0 for no limit; whether they are stored gzipped)."""
    s = load_settings()
    try:
        mb = max(0, min(100000, int(s.get('backup_mb', DEFAULT_MB))))
    except (TypeError, ValueError):
        mb = DEFAULT_MB
    return mb, bool(s.get('backup_zip', DEFAULT_ZIP))


def _is_backup(f):
    return f.endswith('.json') or f.endswith('.json.gz')


def _trim(d, keep):
    """The newest `keep` project backups kept, and within the space allowed (the oldest go first)."""
    mb, _zip = more_settings()
    files = sorted(f for f in os.listdir(d) if _is_backup(f))
    gone = set(files[:-keep]) if keep else set()
    if mb:
        left = [f for f in files if f not in gone]
        total = sum(os.path.getsize(os.path.join(d, f)) for f in left)
        while len(left) > 1 and total > mb * 1024 * 1024:
            f = left.pop(0)
            total -= os.path.getsize(os.path.join(d, f))
            gone.add(f)
    for f in gone:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass


def total_size(project):
    """(bytes, files) a mod's backups take."""
    d = _dir_for(project)
    if not os.path.isdir(d):
        return 0, 0
    fs = [os.path.join(d, f) for f in os.listdir(d)]
    return sum(os.path.getsize(f) for f in fs if os.path.isfile(f)), len(fs)


def clear_old(project, keep=3):
    """All but the newest `keep` of a mod's project backups removed. How many went."""
    d = _dir_for(project)
    if not os.path.isdir(d):
        return 0
    files = sorted(f for f in os.listdir(d) if _is_backup(f))
    n = 0
    for f in files[:-max(1, keep)]:
        try:
            os.remove(os.path.join(d, f))
            n += 1
        except OSError:
            pass
    return n


def maybe_backup(project, force=False, why=''):
    """Copy the project file into its backups folder if it's time (or force). Returns the backup path."""
    keep, minutes = settings()
    now = time.time()
    if not force and now - _last.get(project.path, 0) < minutes * 60:
        return None
    if not os.path.isfile(project.path):
        return None
    d = _dir_for(project)
    os.makedirs(d, exist_ok=True)
    _mb, zipped = more_settings()
    name = time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(now)) + (' ' + why if why else '') + ('.json.gz' if zipped else '.json')
    dst = os.path.join(d, name)
    try:
        if zipped:
            with open(project.path, 'rb') as src, gzip.open(dst, 'wb', compresslevel=6) as out:
                shutil.copyfileobj(src, out, 1 << 20)
        else:
            shutil.copy2(project.path, dst)
    except OSError:
        return None
    _last[project.path] = now
    _trim(d, keep)      # (the newest ones, within the space allowed)
    return dst


def backup_plugin(project, path, force=False, why=''):
    """A copy of the plugin file a mod saves straight into (a .esp opened as the mod, adopt.py), taken before
    the file is written over: at the same cadence as the project backups, into the same folder, the newest
    `keep` of them kept. Returns the copy's path, or None when it was not time."""
    keep, minutes = settings()
    now = time.time()
    key = 'plugin:' + os.path.normcase(path)
    if not force and now - _last.get(key, 0) < minutes * 60:
        return None
    if not os.path.isfile(path):
        return None
    d = _dir_for(project)
    os.makedirs(d, exist_ok=True)
    name = time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(now)) + (' ' + why if why else '') + ' ' + os.path.basename(path) + '.bak'
    dst = os.path.join(d, name)
    try:
        shutil.copy2(path, dst)
    except OSError:
        return None
    _last[key] = now
    files = sorted(f for f in os.listdir(d) if f.endswith('.bak'))
    for f in files[:-keep]:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    return dst


def listing(project):
    d = _dir_for(project)
    out, plugins = [], []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d), reverse=True):
            p = os.path.join(d, f)
            if _is_backup(f):
                stem = f[:-8] if f.endswith('.json.gz') else f[:-5]
                out.append({'file': f, 'size': os.path.getsize(p), 'time': os.path.getmtime(p),
                            'why': stem[20:].strip(), 'zipped': f.endswith('.gz')})
            elif f.endswith('.bak'):
                # copies of the plugin file itself (a mod that is a .esp opened as the mod): put one back by hand
                plugins.append({'file': f, 'size': os.path.getsize(p), 'time': os.path.getmtime(p), 'why': f[20:-4].strip()})
    total, n_files = total_size(project)
    return {'folder': d, 'backups': out, 'plugin_backups': plugins, 'total': total, 'files': n_files,
            'plugin_backup': getattr(project, 'plugin_backup', None)}


def restore(project, file):
    """Put a backup in place of the project file (after backing up the current one)."""
    d = _dir_for(project)
    src = os.path.join(d, os.path.basename(file))
    if not os.path.isfile(src):
        raise ValueError('That backup no longer exists.')
    maybe_backup(project, force=True, why='before restoring')
    if src.endswith('.gz'):
        with gzip.open(src, 'rb') as f, open(project.path + '.tmp', 'wb') as out:
            shutil.copyfileobj(f, out, 1 << 20)
    else:
        shutil.copy2(src, project.path + '.tmp')
    os.replace(project.path + '.tmp', project.path)
    return src
