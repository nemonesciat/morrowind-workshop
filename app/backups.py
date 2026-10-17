"""Automatic backups of your projects: a copy of the project file when you open it and then every
few minutes while you work (the newest few dozen are kept), so a bad change or a broken file is
never the end of a mod. Restoring one first backs up how things are now, so it can be undone too.

Backups live in backups\\<project name>\\ next to the projects folder."""
import os
import re
import shutil
import time

from project import APP_DIR, load_settings

BACKUP_DIR = os.path.join(APP_DIR, 'backups')
DEFAULT_KEEP = 30
DEFAULT_MINUTES = 10
_last = {}          # project file -> when it was last backed up


def _dir_for(project):
    return os.path.join(BACKUP_DIR, re.sub(r'[^A-Za-z0-9 _-]', '_', project.name))


def settings():
    s = load_settings()
    keep = s.get('backup_keep', DEFAULT_KEEP)
    minutes = s.get('backup_minutes', DEFAULT_MINUTES)
    return max(1, min(500, int(keep))), max(1, min(240, int(minutes)))


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
    name = time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(now)) + (' ' + why if why else '') + '.json'
    dst = os.path.join(d, name)
    try:
        shutil.copy2(project.path, dst)
    except OSError:
        return None
    _last[project.path] = now
    # keep only the newest ones
    files = sorted(f for f in os.listdir(d) if f.endswith('.json'))
    for f in files[:-keep]:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    return dst


def listing(project):
    d = _dir_for(project)
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d), reverse=True):
            if not f.endswith('.json'):
                continue
            p = os.path.join(d, f)
            out.append({'file': f, 'size': os.path.getsize(p), 'time': os.path.getmtime(p),
                        'why': f[20:-5].strip()})
    return {'folder': d, 'backups': out}


def restore(project, file):
    """Put a backup in place of the project file (after backing up the current one)."""
    d = _dir_for(project)
    src = os.path.join(d, os.path.basename(file))
    if not os.path.isfile(src):
        raise ValueError('That backup no longer exists.')
    maybe_backup(project, force=True, why='before restoring')
    shutil.copy2(src, project.path + '.tmp')
    os.replace(project.path + '.tmp', project.path)
    return src
