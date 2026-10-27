"""What differs between Windows and Linux, in one place: where OpenMW and its settings are, how the game
is started, opening files and folders, asking for a file or folder, whether the game is running, free
memory, a gentler priority for the surveys, the bin, and finding other programs (picture editors,
Blender). The rest of the Workshop is the same on both.

On Linux OpenMW keeps openmw.cfg, settings.cfg and openmw.log in ~/.config/openmw and the data folder
and saves in ~/.local/share/openmw (the Flatpak keeps both under ~/.var/app/org.openmw.OpenMW); on
Windows all of it is in Documents\\My Games\\OpenMW."""
import glob
import os
import shutil
import subprocess
import time

WINDOWS = os.name == 'nt'
EXE = '.exe' if WINDOWS else ''
FLATPAK_ID = 'org.openmw.OpenMW'
HOME = os.path.expanduser('~')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


# ------------------------------------------------------------------ OpenMW: its folders
def _home(pat):
    return HOME + pat[1:] if pat.startswith('~') else pat


def _xdg(var, default):
    v = os.environ.get(var)
    return v if v and os.path.isabs(v) else os.path.join(HOME, default)


def _flatpak_home():
    return os.path.join(HOME, '.var', 'app', FLATPAK_ID)


def is_flatpak(install):
    return bool(install) and ('%sflatpak%sapp%s%s' % (os.sep, os.sep, os.sep, FLATPAK_ID)) in install


def openmw_dirs(install=None):
    """(config folder, data folder): openmw.cfg, settings.cfg and openmw.log are in the first; the data
    folder (mods go in its data subfolder) and the saves in the second. The same folder on Windows."""
    if os.environ.get('WORKSHOP_OPENMW_USERDIR'):
        d = os.environ['WORKSHOP_OPENMW_USERDIR']             # (tests, or an unusual setup)
        return d, d
    if WINDOWS:
        docs = os.path.join(HOME, 'Documents')
        try:
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
            if buf.value:
                docs = buf.value
        except Exception:
            pass
        d = os.path.join(docs, 'My Games', 'OpenMW')
        return d, d
    native = (os.path.join(_xdg('XDG_CONFIG_HOME', '.config'), 'openmw'),
              os.path.join(_xdg('XDG_DATA_HOME', os.path.join('.local', 'share')), 'openmw'))
    fp = _flatpak_home()
    flat = (os.path.join(fp, 'config', 'openmw'), os.path.join(fp, 'data', 'openmw'))
    # (the Flatpak's own folders when the game is the Flatpak, or when only the Flatpak has been set up)
    if is_flatpak(install) or (not install and not os.path.isdir(native[0]) and os.path.isdir(flat[0])):
        return flat
    return native


def _flatpak_installs():
    for base in (os.path.join(_xdg('XDG_DATA_HOME', os.path.join('.local', 'share')), 'flatpak'), '/var/lib/flatpak'):
        d = os.path.join(base, 'app', FLATPAK_ID, 'current', 'active', 'files', 'bin')
        if os.path.isdir(d):
            yield d


def _windows_installs():
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                 os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        try:
            for d in sorted(os.listdir(base), reverse=True):
                if d.lower().startswith('openmw'):
                    yield os.path.join(base, d)
        except OSError:
            pass
    try:
        import winreg
    except ImportError:
        return
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                root = winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\Uninstall', 0,
                                      winreg.KEY_READ | view)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    k = winreg.OpenKey(root, winreg.EnumKey(root, i))
                    name = winreg.QueryValueEx(k, 'DisplayName')[0]
                except OSError:
                    continue
                if not str(name).lower().startswith('openmw'):
                    continue
                for val in ('InstallLocation', 'DisplayIcon', 'UninstallString'):
                    try:
                        v = str(winreg.QueryValueEx(k, val)[0]).strip('"').split(',')[0]
                    except OSError:
                        continue
                    yield v if val == 'InstallLocation' else os.path.dirname(v)


def openmw_installs():
    """Folders the game's program may be in, most likely first (each still to be checked)."""
    if WINDOWS:
        yield from _windows_installs()
        return
    w = shutil.which('openmw')
    if w:
        yield os.path.dirname(os.path.realpath(w))
    yield from ('/usr/bin', '/usr/games', '/usr/local/bin', '/usr/local/games')
    # (openmw.org's own download, unpacked: a folder named after it in the usual places)
    for pat in ('/opt/openmw*', '~/openmw*', '~/OpenMW*', '~/Applications/openmw*', '~/Games/openmw*',
                '~/Games/OpenMW*', '~/.local/share/openmw-*'):
        for d in sorted(glob.glob(_home(pat)), reverse=True):
            yield d
    yield from _flatpak_installs()


def has_game(install, program='openmw'):
    """The game (or 'openmw-launcher', its Launcher) is in this folder."""
    return bool(install) and os.path.isfile(os.path.join(install, program + EXE))


def game_argv(install, program='openmw'):
    """The start of the command line that runs the game (or its Launcher) from this folder."""
    if is_flatpak(install):
        return ['flatpak', 'run', '--command=' + program, FLATPAK_ID]
    return [os.path.join(install, program + EXE)]


def program_name(program='openmw'):
    return program + EXE


def global_cfg_dirs(install):
    """Folders with the game's own openmw.cfg and defaults.bin, read before yours, in OpenMW's order. On Windows
    and in openmw.org's own downloads that is the game's folder; a Linux system install keeps them in /etc."""
    out = []
    if not WINDOWS and install:
        if is_flatpak(install):
            out.append(os.path.normpath(os.path.join(install, '..', 'etc', 'openmw')))
        elif not os.path.isfile(os.path.join(install, 'openmw.cfg')):
            out += ['/etc/openmw', '/usr/local/etc/openmw', '/etc/xdg/openmw']
    if install:
        out.append(install)
    seen, keep = set(), []
    for d in out:
        if d not in seen and os.path.isdir(d):
            seen.add(d)
            keep.append(d)
    return keep


def global_data_dir(install):
    """What openmw.cfg's ?global? stands for: the game's folder, or /usr/share/games/openmw on a Linux system install."""
    if WINDOWS or not install or os.path.isfile(os.path.join(install, 'openmw.cfg')):
        return install or ''
    if is_flatpak(install):
        return os.path.normpath(os.path.join(install, '..', 'share', 'games', 'openmw'))
    for d in ('/usr/share/games/openmw', '/usr/share/openmw', '/usr/local/share/games/openmw'):
        if os.path.isdir(d):
            return d
    return install


# ------------------------------------------------------------------ is the game running?
def process_running(program='openmw'):
    """True or False, or None when it can't be told."""
    if WINDOWS:
        try:
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s.exe' % program, '/NH'], capture_output=True,
                                 text=True, timeout=5, creationflags=NO_WINDOW)
            return ('%s.exe' % program) in out.stdout.lower()
        except Exception:
            return None
    try:
        for pid in os.listdir('/proc'):
            if pid.isdigit():
                try:
                    with open('/proc/%s/comm' % pid, encoding='utf-8', errors='replace') as f:
                        if f.read().strip() == program:
                            return True
                except OSError:
                    pass
        return False
    except OSError:
        return None


# ------------------------------------------------------------------ the computer
def free_memory():
    """Bytes of memory free for use now, or None."""
    try:
        if WINDOWS:
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullAvailPhys
            return None
        with open('/proc/meminfo', encoding='ascii', errors='replace') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return None


def lower_priority():
    """This process at a gentler priority (the surveys, so the Workshop and the game stay quick)."""
    try:
        if WINDOWS:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)   # BELOW_NORMAL
        else:
            os.nice(5)
    except Exception:
        pass


def background_flags():
    """creationflags for a survey process: below normal and no window on Windows; nothing elsewhere."""
    if WINDOWS:
        return getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0x00004000) | getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
    return 0


def detached(argv, cwd=None, env=None):
    """Start a program that carries on by itself (the game, an editor): its own process group, no window
    of ours, nothing of ours left open on Linux."""
    if WINDOWS:
        return subprocess.Popen(argv, cwd=cwd, env=env, creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    return subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ files and folders
def open_path(path, edit=False):
    """Open a file or folder the way the desktop would (edit: in the program that edits that kind, where
    Windows knows one). False when nothing could open it."""
    try:
        if WINDOWS:
            if edit:
                try:
                    os.startfile(path, 'edit')
                    return True
                except OSError:
                    pass
            os.startfile(path)
            return True
        for opener in ('xdg-open', 'gio', 'kde-open', 'gnome-open'):
            exe = shutil.which(opener)
            if exe:
                detached([exe, 'open', path] if opener == 'gio' else [exe, path])
                return True
    except OSError:
        pass
    return False


def show_in_folder(path):
    """The folder a file is in, with the file picked out where the file manager can do that."""
    if WINDOWS:
        if os.path.isfile(path):
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
            return True
        return open_path(path if os.path.isdir(path) else os.path.dirname(path))
    if os.path.isfile(path) and shutil.which('dbus-send'):
        # (the freedesktop file manager call: Nautilus, Dolphin, Nemo and Thunar pick the file out)
        from urllib.parse import quote
        try:
            r = subprocess.run(['dbus-send', '--session', '--print-reply', '--dest=org.freedesktop.FileManager1',
                                '/org/freedesktop/FileManager1', 'org.freedesktop.FileManager1.ShowItems',
                                'array:string:file://' + quote(os.path.abspath(path)), 'string:'],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    return open_path(path if os.path.isdir(path) else os.path.dirname(path))


def find_ci(folder, rel):
    """folder/rel as it really is on disk, whatever the case of each part of rel (game files are named in any
    case, and Linux keeps Meshes and meshes apart). None when there is no such file."""
    parts = [p for p in rel.replace('\\', '/').split('/') if p]
    p = os.path.join(folder, *parts)
    if WINDOWS or os.path.exists(p):
        return p if os.path.exists(p) else None
    cur = folder
    for part in parts:
        low = part.lower()
        try:
            hit = next((n for n in os.listdir(cur) if n.lower() == low), None)
        except OSError:
            return None
        if hit is None:
            return None
        cur = os.path.join(cur, hit)
    return cur


def to_trash(paths):
    """Move files and folders to the bin, where they can be restored. Raises OSError when that fails."""
    paths = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not paths:
        return
    if WINDOWS:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [('hwnd', wintypes.HWND), ('wFunc', ctypes.c_uint), ('pFrom', wintypes.LPCWSTR),
                        ('pTo', wintypes.LPCWSTR), ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', wintypes.BOOL),
                        ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', wintypes.LPCWSTR)]
        FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = '\0'.join(paths) + '\0\0'
        op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
        r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if r != 0 or op.fAnyOperationsAborted:
            raise OSError('Windows could not move those files to the Recycle Bin (code %s)' % hex(r))
        return
    gio = shutil.which('gio')
    if gio:
        r = subprocess.run([gio, 'trash', '--'] + paths, capture_output=True, text=True)
        if r.returncode == 0:
            return
    # (the freedesktop.org trash, as file managers keep it: the file in files/, where it came from in info/)
    from urllib.parse import quote
    trash = os.path.join(_xdg('XDG_DATA_HOME', os.path.join('.local', 'share')), 'Trash')
    os.makedirs(os.path.join(trash, 'files'), exist_ok=True)
    os.makedirs(os.path.join(trash, 'info'), exist_ok=True)
    for p in paths:
        base = os.path.basename(p.rstrip('/'))
        name, n = base, 1
        while os.path.exists(os.path.join(trash, 'files', name)) or os.path.exists(os.path.join(trash, 'info', name + '.trashinfo')):
            n += 1
            name = '%s.%d' % (base, n)
        with open(os.path.join(trash, 'info', name + '.trashinfo'), 'w', encoding='utf-8') as f:
            f.write('[Trash Info]\nPath=%s\nDeletionDate=%s\n' % (quote(p), time.strftime('%Y-%m-%dT%H:%M:%S')))
        shutil.move(p, os.path.join(trash, 'files', name))


def trash_name():
    return 'Recycle Bin' if WINDOWS else 'bin'


# ------------------------------------------------------------------ asking for a file or folder
def _ps_dialog(script):
    r = subprocess.run(['powershell', '-NoProfile', '-STA', '-Command', script], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    return (r.stdout or '').strip()


def _q(s):
    return "'" + str(s or '').replace("'", "''") + "'"


def _linux_dialog(zenity, kdialog):
    """'' when cancelled, None when there is no dialog program (zenity or kdialog) on this computer."""
    for exe, args in (('zenity', zenity), ('kdialog', kdialog), ('qarma', zenity)):
        path = shutil.which(exe)
        if path:
            r = subprocess.run([path] + args, capture_output=True, text=True)
            return (r.stdout or '').strip().splitlines()[0] if (r.stdout or '').strip() else ''
    return None


def pick_folder(title, start=None):
    """A folder chosen in the desktop's own folder picker: its path, '' when cancelled, None when this computer
    has no picker the Workshop can use."""
    if WINDOWS:
        return _ps_dialog("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                          "$d.Description = %s; %s"
                          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
                          "if ($d.ShowDialog($o) -eq 'OK') { $d.SelectedPath }" % (
                              _q(title), ('$d.SelectedPath = %s; ' % _q(start)) if start else ''))
    s = (start or HOME).rstrip('/') + '/'
    return _linux_dialog(['--file-selection', '--directory', '--title=' + title, '--filename=' + s],
                         ['--title', title, '--getexistingdirectory', start or HOME])


def pick_file(title, start=None, kinds=None):
    """A file chosen in the desktop's own file picker. kinds: (label, ['*.esp', ...]). As pick_folder."""
    if WINDOWS:
        filt = ''
        if kinds:
            pats = ';'.join(kinds[1])
            filt = "$d.Filter = %s; " % _q('%s (%s)|%s|All files (*.*)|*.*' % (kinds[0], pats, pats))
        return _ps_dialog("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; "
                          "$d.Title = %s; %s%s"
                          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
                          "if ($d.ShowDialog($o) -eq 'OK') { $d.FileName }" % (
                              _q(title), filt, ('$d.InitialDirectory = %s; ' % _q(start)) if start else ''))
    s = (start or HOME).rstrip('/') + '/'
    z = ['--file-selection', '--title=' + title, '--filename=' + s]
    k = ['--title', title, '--getopenfilename', start or HOME]
    if kinds:
        # (Linux names are case-sensitive: both cases of each pattern)
        pats = []
        for p in kinds[1]:
            pats += [p.lower(), p.upper()]
        z += ['--file-filter=%s | %s' % (kinds[0], ' '.join(pats)), '--file-filter=All files | *']
        k += ['%s (%s)' % (kinds[0], ' '.join(pats))]
    return _linux_dialog(z, k)


NO_PICKER = ('This computer has no file picker the Workshop can use. Install zenity (or kdialog on KDE) '
             'from your system\'s software centre, then try again.')


# ------------------------------------------------------------------ other programs
_WIN_EDITORS = [('GIMP', r'%ProgramFiles%\GIMP*\bin\gimp-*.exe'), ('Paint.NET', r'%ProgramFiles%\paint.net\paintdotnet.exe'),
                ('Krita', r'%ProgramFiles%\Krita (x64)\bin\krita.exe'), ('Photoshop', r'%ProgramFiles%\Adobe\Adobe Photoshop*\Photoshop.exe'),
                ('Affinity Photo', r'%ProgramFiles%\Affinity\Photo*\Photo.exe'), ('GIMP', r'%LOCALAPPDATA%\Programs\GIMP*\bin\gimp-*.exe')]
_LINUX_EDITORS = [('GIMP', 'gimp'), ('Krita', 'krita'), ('Pinta', 'pinta'), ('KolourPaint', 'kolourpaint')]


def picture_editors():
    """[(name, program)] of the picture editors found on this computer."""
    out = []
    if WINDOWS:
        for name, pat in _WIN_EDITORS:
            for exe in sorted(glob.glob(os.path.expandvars(pat))):
                out.append((name, exe))
        return out
    for name, cmd in _LINUX_EDITORS:
        exe = shutil.which(cmd)
        if exe:
            out.append((name, exe))
    return out


def blenders():
    """Blender's program wherever it usually is, newest first."""
    if WINDOWS:
        found = sorted(glob.glob(os.path.expandvars(r'%ProgramFiles%\Blender Foundation\Blender*\blender.exe')), reverse=True)
        # (a portable Blender, unpacked from blender.org's zip onto the Desktop or into Downloads)
        for pat in (r'%USERPROFILE%\Desktop\blender-*\blender.exe', r'%USERPROFILE%\Downloads\blender-*\blender.exe',
                    r'%LOCALAPPDATA%\Programs\Blender*\blender.exe'):
            found += sorted(glob.glob(os.path.expandvars(pat)), reverse=True)
        return found
    found = []
    for pat in ('~/blender-*/blender', '~/Downloads/blender-*/blender', '~/Desktop/blender-*/blender',
                '~/Applications/blender-*/blender', '/opt/blender*/blender'):
        found += sorted(glob.glob(_home(pat)), reverse=True)
    w = shutil.which('blender')
    if w:
        found.append(w)
    return found


def is_program(path, name=None):
    """path is a program on this computer (named name, without .exe, when given)."""
    if not path or not os.path.isfile(path):
        return False
    base = os.path.basename(path).lower()
    if WINDOWS:
        return base.endswith('.exe') and (not name or base == name + '.exe')
    return os.access(path, os.X_OK) and (not name or base == name or base.startswith(name + '-') or base.startswith(name + '.'))


# ------------------------------------------------------------------ problem reports
def anonymise(text):
    """Paths in text with the home folder (and its Windows short form) left out."""
    import re
    token = '%USERPROFILE%' if WINDOWS else '~'
    if WINDOWS:
        try:                                       # (Windows' short "8.3" form of it, like C:\Users\JOHNSM~1)
            import ctypes
            buf = ctypes.create_unicode_buffer(520)
            if ctypes.windll.kernel32.GetShortPathNameW(HOME, buf, 520):
                text = re.sub(re.escape(buf.value), token, text, flags=re.I)
        except Exception:
            pass
    return re.sub(re.escape(HOME), token, text, flags=re.I if WINDOWS else 0)


def system_name():
    import platform
    return ('Windows: ' if WINDOWS else 'System: ') + platform.platform()
