"""Morrowind Workshop - a modern browser and editor for your OpenMW load order.

Runs a tiny web server on this computer only (127.0.0.1) and opens it in your browser."""
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai  # noqa: E402
import builder  # noqa: E402
import create  # noqa: E402
import dialogue  # noqa: E402
import doors  # noqa: E402
import furnish  # noqa: E402
import groups  # noqa: E402
import items  # noqa: E402
import landscape  # noqa: E402
import pathgrid  # noqa: E402
import editing  # noqa: E402
import mapdata  # noqa: E402
import npc  # noqa: E402
import mwscript  # noqa: E402
import release  # noqa: E402
import places  # noqa: E402
import levlists  # noqa: E402
import groups_ed  # noqa: E402
import questtest  # noqa: E402
import loadorder  # noqa: E402
import backups  # noqa: E402
import helpinfo  # noqa: E402
from esm import find_openmw  # noqa: E402
from link import CONTENT_NAME, SPARE_NAME, LiveLink  # noqa: E402
from database import Database  # noqa: E402
from project import APP_DIR, PROJECTS_DIR, Project, load_settings, save_settings  # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
db = Database()
edit_lock = threading.RLock()        # (re-entrant: a request that holds it may flush pending writes, which take it too)


def code_stamp():
    d = os.path.dirname(os.path.abspath(__file__))
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith('.py')]
    files += [os.path.join(d, 'link_scripts', f) for f in os.listdir(os.path.join(d, 'link_scripts'))]
    return max(os.path.getmtime(f) for f in files)


STARTED_CODE = code_stamp()


def api_key():
    return load_settings().get('anthropic_api_key')


assistant = ai.Assistant(db, api_key)
link = LiveLink(db, edit_lock)
editing.WRITE_LOCK = edit_lock         # (the project file and the plugin are written a moment after each change, under this lock)
db.on_project_change = link.write_state


def open_saved_project():
    s = load_settings()
    p = s.get('project')
    if p and os.path.isfile(os.path.join(APP_DIR, p)):
        try:
            db.project = Project(os.path.join(APP_DIR, p))
        except Exception as e:
            print('Could not open project %s: %s' % (p, e))


def list_projects():
    out = []
    if os.path.isdir(PROJECTS_DIR):
        for f in sorted(os.listdir(PROJECTS_DIR)):
            if f.endswith('.json'):
                out.append(f[:-5])
    return out


# Options for starting the game, ticked in the OpenMW menu (or asked for each time). Some are settings
# for the programs OpenMW is built on (environment variables), some are OpenMW's own options.
LAUNCH_PRESETS = [
    ('controller_bg', 'Controller works while the game is in the background',
     'Your gamepad keeps controlling the game when another window (like the Workshop) is in front.',
     {'env': {'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS': '1'}}),
    ('no_grab', 'Don\'t lock the mouse to the game window',
     'Move the mouse out of the game to the Workshop without pressing Alt+Tab.', {'args': ['--no-grab']}),
    ('no_sound', 'No sound', 'Start the game silent.', {'args': ['--no-sound']}),
    ('script_verbose', 'Extra script messages in the log',
     'Helps find out why a script doesn\'t work (in openmw.log).', {'args': ['--script-verbose']}),
]
_ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def launch_settings():
    s = load_settings().get('launch') or {}
    return {'on': [k for k in s.get('on', []) if any(k == p[0] for p in LAUNCH_PRESETS)], 'args': s.get('args', ''),
            'env': s.get('env', ''), 'ask': bool(s.get('ask')),
            'presets': [{'key': k, 'label': l, 'help': h} for k, l, h, _w in LAUNCH_PRESETS]}


def save_launch(body):
    env = str(body.get('env') or '')
    for line in env.splitlines():
        line = line.strip()
        if line and ('=' not in line or not _ENV_NAME.match(line.split('=', 1)[0].strip())):
            raise editing.EditError('Write each setting as NAME=value on its own line (e.g. SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1).')
    s = load_settings()
    s['launch'] = {'on': [k for k in body.get('on') or [] if any(k == p[0] for p in LAUNCH_PRESETS)],
                   'args': str(body.get('args') or '')[:2000], 'env': env[:4000], 'ask': bool(body.get('ask'))}
    save_settings(s)
    return launch_settings()


def _spawn(args, install, launch=None):
    """Start the game with the chosen start options (the saved ones, or those picked for this one start)."""
    opts = launch if isinstance(launch, dict) else launch_settings()
    env = dict(os.environ)
    extra = []
    for key, _l, _h, what in LAUNCH_PRESETS:
        if key in (opts.get('on') or []):
            env.update(what.get('env', {}))
            extra += what.get('args', [])
    for line in str(opts.get('env') or '').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if _ENV_NAME.match(k.strip()):
                env[k.strip()] = v.strip()
    # your own options, written as on a command line ("quotes" keep spaces together)
    extra += [a.strip('"') for a in re.findall(r'"[^"]*"|\S+', str(opts.get('args') or ''))]
    exe, rest = args[0], args[1:]
    cmd = [exe] + extra + rest
    link.ALT_LOG = None
    if len(subprocess.list2cmdline(cmd)) > LAUNCH_CMD_MAX:
        cmd = _via_config(cmd)
    # (in the Workshop's log, for when a start goes wrong: the whole line but the load order)
    shown = [a for i, a in enumerate(cmd) if not (a == '--content' or (i and cmd[i - 1] == '--content'))]
    print('Starting OpenMW:', subprocess.list2cmdline(shown), '(+ %d content files)' % sum(1 for a in cmd if a == '--content'))
    subprocess.Popen(cmd, cwd=install, env=env,
                     creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    return extra


# Windows refuses a command line over 32,767 characters ("The filename or extension is too long").
# A load order of a thousand-odd plugins, each given as --content, goes over that: then the load
# order goes into an extra openmw.cfg of the Workshop's own instead, handed to OpenMW with --config.
LAUNCH_CMD_MAX = int(os.environ.get('WORKSHOP_LAUNCH_CMD_MAX') or 30000)     # (lower it to try this route)
_CFG_KEYS = ('--data', '--replace', '--content', '--groundcover', '--fallback-archive')


def _via_config(cmd):
    folder = os.path.join(APP_DIR, 'launch_config')
    os.makedirs(folder, exist_ok=True)
    lines, keep, i = [], [cmd[0]], 1
    while i < len(cmd):
        a = cmd[i]
        if a in _CFG_KEYS and i + 1 < len(cmd):
            v = cmd[i + 1]
            if a == '--data':
                v = '"%s"' % v.replace('&', '&&').replace('"', '&"')     # (openmw.cfg's own quoting)
            lines.append('%s=%s' % (a[2:], v))
            i += 2
        else:
            keep.append(a)
            i += 1
    with open(os.path.join(folder, 'openmw.cfg'), 'w', encoding='utf-8') as f:
        f.write('# Written by Morrowind Workshop for starting the game: your load order was too long for\n'
                '# a Windows command line. Rewritten each time; your own openmw.cfg is not changed.\n')
        f.write('\n'.join(lines) + '\n')
    # (the last config folder is where OpenMW keeps its settings and log for this run: start from yours)
    mine = os.path.join((db.config or {}).get('userdir') or '', 'settings.cfg')
    if os.path.isfile(mine):
        shutil.copyfile(mine, os.path.join(folder, 'settings.cfg'))
    link.ALT_LOG = os.path.join(folder, 'openmw.log')
    return keep + ['--config', folder]


def _clean_word(v, n=64):
    return re.sub(r'["\r\n;]', '', str(v or '')).strip()[:n]


def test_setups():
    """Play test setups: what the player gets when the game starts from the Workshop (items, spells,
    quest stages, global variables, other console commands), one of them switched on."""
    s = load_settings()
    ts = s.get('test_setups') or {}
    lst = [x for x in (ts.get('list') or []) if isinstance(x, dict) and x.get('name')]
    on = ts.get('on') if any(x['name'] == ts.get('on') for x in lst) else ''
    names = {}
    for x in lst:
        for i in [it[0] for it in x.get('items', [])] + list(x.get('spells', [])):
            ri = db.resolve_id(str(i))
            if ri is not None and db.recs[ri][2]:
                names[str(i).lower()] = db.recs[ri][2]
    return {'list': lst, 'on': on, 'names': names, 'play_as': s.get('play_as') or ''}


def _active_setup():
    s = load_settings().get('test_setups') or {}
    on = s.get('on')
    for x in [x for x in (s.get('list') or []) if isinstance(x, dict)]:
        if on and x.get('name') == on:
            return x
    return None


def play_as(body):
    """Who Play here starts as: a new character (''), or one of your saved characters (their save folder)."""
    import saves
    folder = str(body.get('folder') or '')
    if folder and not saves.latest_save(folder):
        raise editing.EditError('That character has no saves any more.')
    s = load_settings()
    s['play_as'] = folder
    save_settings(s)
    return {'play_as': folder}


def save_test_setups(body):
    out = []
    for x in (body.get('list') or [])[:40]:
        name = _clean_word(x.get('name'), 60)
        if not name:
            continue
        items = [[_clean_word(i[0]), max(1, min(100000, int(float(i[1] or 1))))] for i in (x.get('items') or [])[:80] if i and _clean_word(i[0])]
        for iid, _n in items:
            if db.resolve_id(iid) is None:
                raise editing.EditError('Test setup "%s": there is no item "%s".' % (name, iid))
        spells = [_clean_word(sp) for sp in (x.get('spells') or [])[:80] if _clean_word(sp)]
        for sp in spells:
            if not db.by_key.get(('SPEL', sp.lower())):
                raise editing.EditError('Test setup "%s": there is no spell "%s".' % (name, sp))
        journal = [[_clean_word(j[0]), int(float(j[1] or 0))] for j in (x.get('journal') or [])[:80] if j and _clean_word(j[0])]
        globs = [[_clean_word(g[0]), float(g[1] or 0)] for g in (x.get('globals') or [])[:80] if g and re.match(r'^[A-Za-z_][\w]*$', _clean_word(g[0]))]
        out.append({'name': name, 'items': items, 'spells': spells, 'journal': journal, 'globals': globs,
                    'god': bool(x.get('god')), 'level': max(0, min(100, int(float(x.get('level') or 0)))),
                    'commands': str(x.get('commands') or '')[:4000]})
    s = load_settings()
    on = body.get('on') or ''
    s['test_setups'] = {'list': out, 'on': on if any(x['name'] == on for x in out) else ''}
    save_settings(s)
    return test_setups()


def give_setup(body):
    """A test setup given to the game that's running now (through the live link): items, quest stages and
    variables. Spells, level and console commands only come with a fresh start."""
    if not link.connected():
        raise editing.EditError('Start the game from the Workshop first (Play here), then this gives it to you there.')
    setup = body.get('setup')
    if not isinstance(setup, dict):
        s = load_settings().get('test_setups') or {}
        setup = next((x for x in (s.get('list') or []) if x.get('name') == body.get('name')), None)
    if not setup:
        raise editing.EditError('No such test setup.')
    sent, skipped = 0, []
    items = [i for i in setup.get('items', []) if db.resolve_id(str(i[0])) is not None]
    if items:
        link.refresh_watch(extra_items=[i[0] for i in items])
    for iid, n in items:
        link.command('give', str(iid), str(int(n)))
        sent += 1
    journal = setup.get('journal', [])
    if len(journal) > 40:
        skipped.append('%d quest stages (that many only come with a fresh start)' % len(journal))
        journal = []
    for quest, stage in journal:
        link.command('journal', str(quest), str(int(stage)))
        sent += 1
    for name, value in setup.get('globals', []):
        link.refresh_watch(extra_globals=[name])
        link.command('global', str(name), str(value))
        sent += 1
    if setup.get('spells'):
        skipped.append('spells')
    if setup.get('level') or setup.get('god') or str(setup.get('commands') or '').strip():
        skipped.append('level, god mode and console commands')
    return {'sent': sent, 'skipped': skipped}


def _setup_commands(setup, god_already=False):
    cmds = []
    if setup.get('god') and not god_already:
        cmds.append('tgm')                       # (it switches god mode on and off: only once)
    if setup.get('level'):
        cmds.append('player->SetLevel %d' % int(setup['level']))
    for iid, n in setup.get('items', []):
        cmds.append('player->AddItem "%s" %d' % (iid, n))
    for sp in setup.get('spells', []):
        cmds.append('player->AddSpell "%s"' % sp)
    for quest, stage in setup.get('journal', []):
        cmds.append('Journal "%s" %d' % (quest, stage))
    for name, value in setup.get('globals', []):
        cmds.append('set %s to %s' % (name, ('%d' % value) if float(value).is_integer() else ('%g' % value)))
    cmds += [ln.strip() for ln in str(setup.get('commands') or '').splitlines() if ln.strip()]
    return cmds


def play(body):
    """Launch OpenMW straight into a cell, with the project plugin loaded."""
    install = db.config.get('install')
    exe = os.path.join(install, 'openmw.exe') if install else None
    if not exe or not os.path.isfile(exe):
        raise editing.EditError('Could not find openmw.exe.')
    if link.game_running():
        raise editing.EditError('The game is still running. Quit it first (or use the map to teleport while linked).')
    # make sure the game loads your latest changes: finish a plugin write the game was blocking
    if db.project:
        editing.build(db)
        if getattr(db.project, 'pending_write', None):
            raise editing.EditError('Your mod file is still in use (is the game closing?). Try again in a moment.')
    info = mapdata.cell_info(db, body['cell'])
    if not info:
        raise editing.EditError('Unknown cell.')
    cmds = []
    if body.get('god'):
        cmds.append('tgm')
    if 'x' in body:
        x, y, z = float(body['x']), float(body['y']), float(body['z'])
        rz = round(math.degrees(float(body.get('rz', 0)))) % 360
        if info['interior']:
            cmds.append('player->PositionCell %.0f %.0f %.0f %d "%s"' % (x, y, z, rz, info['name']))
        else:
            cmds.append('player->Position %.0f %.0f %.0f %d' % (x, y, z, rz))
    elif not info['interior']:
        cx, cy = (info['gx'] + 0.5) * 8192, (info['gy'] + 0.5) * 8192
        ld = mapdata.land(db, info['gx'], info['gy'])
        cz = max(ld['h'][32 * 65 + 32], 0) + 100 if ld.get('exists') else 1000
        cmds.append('player->Position %.0f %.0f %.0f 0' % (cx, cy, cz))
    # the test setup that's switched on (unless this start asks for none)
    setup = _active_setup() if body.get('setup', True) else None
    if setup:
        cmds += _setup_commands(setup, god_already=bool(body.get('god')))
    script =os.path.join(APP_DIR, 'play_commands.txt')
    with open(script, 'w', encoding='cp1252', errors='replace') as f:
        f.write('\n'.join(cmds) + '\n')
    start = info['name'] if info['interior'] else (info['name'] or 'Seyda Neen')
    # as one of your characters: their latest save, then the commands above move them here
    import saves
    who = (load_settings().get('play_as') or '') if body.get('as_saved', True) else ''
    save = saves.latest_save(who) if who else None
    if save and 'x' not in body and info['interior']:
        # (no spot picked: with a save, the game stays wherever the character was saved unless the
        # script moves them, so: just inside the place's door, as the Workshop's doors arrive)
        import doors
        pos, _d = doors.arrival(db, body['cell'])
        cmds.insert(1 if cmds[:1] == ['tgm'] else 0, 'player->PositionCell %.0f %.0f %.0f %d "%s"' % (
            pos[0], pos[1], pos[2], round(math.degrees(pos[5])) % 360, info['name']))
        with open(script, 'w', encoding='cp1252', errors='replace') as f:
            f.write('\n'.join(cmds) + '\n')
    if save:
        args = [exe, '--load-savegame', save, '--script-run', script] + _game_content_args()
    else:
        args = [exe, '--skip-menu', '--start', start, '--script-run', script] + _game_content_args()
    link.from_save = bool(save)          # (a save remembers visited rooms' doors: the link re-tells them their links)
    _spawn(args, install, body.get('launch'))
    return {'ok': True, 'start': start, 'commands': cmds, 'setup': setup['name'] if setup else None,
            'as': who if save else None}


def start_openmw(mode, launch=None):
    """The OpenMW button: the game to its main menu (with your mod and the live link), or OpenMW's Launcher."""
    install = (db.config or {}).get('install')
    if not install:
        raise editing.EditError('OpenMW wasn\'t found. Use "Choose OpenMW\'s folder" to show the Workshop where it is.')
    if mode == 'launcher':
        exe = os.path.join(install, 'openmw-launcher.exe')
        if not os.path.isfile(exe):
            raise editing.EditError('OpenMW\'s Launcher (openmw-launcher.exe) isn\'t in ' + install)
        subprocess.Popen([exe], cwd=install, creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        return {'ok': True}
    exe = os.path.join(install, 'openmw.exe')
    if link.game_running():
        raise editing.EditError('The game is already running.')
    if db.project and db.state == 'ready':
        editing.build(db)
        if getattr(db.project, 'pending_write', None):
            raise editing.EditError('Your mod file is still in use (is the game closing?). Try again in a moment.')
    link.from_save = False               # (the main menu: whichever save the player loads, the link re-tells doors on request below)
    args = [exe] + (_game_content_args() if db.state == 'ready' else [])
    _spawn(args, install, launch)
    return {'ok': True}


def openmw_info():
    cfg = db.config or {}
    install = cfg.get('install') or find_openmw(load_settings().get('openmw_install'))
    return {'install': install, 'found': bool(install),
            'launcher': bool(install) and os.path.isfile(os.path.join(install, 'openmw-launcher.exe')),
            'cfg': cfg.get('user_cfg'), 'cfg_exists': cfg.get('user_cfg_exists', False),
            'running': link.game_running(), 'chosen': load_settings().get('openmw_install')}


def pick_openmw():
    """Ask for OpenMW's folder with Windows' own folder picker; remember it and reload."""
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
          "$d.Description = 'Choose the folder OpenMW is installed in (the one with openmw.exe)'; "
          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
          "if ($d.ShowDialog($o) -eq 'OK') { $d.SelectedPath }")
    r = subprocess.run(['powershell', '-NoProfile', '-STA', '-Command', ps], capture_output=True, text=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    path = (r.stdout or '').strip()
    if not path:
        return {'ok': False, 'cancelled': True}
    if not os.path.isfile(os.path.join(path, 'openmw.exe')):
        raise editing.EditError('There is no openmw.exe in ' + path + '. Choose the folder OpenMW is installed in.')
    s = load_settings()
    s['openmw_install'] = path
    save_settings(s)
    if db.state != 'loading':
        db.state = 'loading'
        db.load_async()
    return {'ok': True, 'install': path}


def _game_content_args():
    """Your load order plus the mod being made (and the live link), last, for starting the game."""
    args = []
    # (the link's own files are added once, below, even if openmw.cfg lists them too: OpenMW
    # refuses to start when a content file is named twice)
    ours = (SPARE_NAME.lower(), CONTENT_NAME.lower())
    content = [c for c in db.cfg_content_all if c.lower() not in ours]
    if db.project and os.path.isfile(editing.plugin_path(db)):
        if db.project.plugin.lower() not in [c.lower() for c in content]:
            content.append(db.project.plugin)
        lc = editing.lua_content(db)
        if lc and lc.lower() not in [c.lower() for c in content]:
            content.append(lc)                       # the mod's Lua scripts
    # live link: the game will load exactly what the plugin holds now
    link.start_session()
    content += [SPARE_NAME, CONTENT_NAME]
    args += ['--data', link.data_dir()]              # (the link's files live in the Workshop's own folder)
    # the folder the mod (and the Library's files) is in, when OpenMW's settings don't list it
    mine = os.path.dirname(editing.plugin_path(db)) if db.project else None
    known = {os.path.normcase(os.path.abspath(d)) for d in db.config.get('data', [])}
    if mine and os.path.isdir(mine) and os.path.normcase(os.path.abspath(mine)) not in known:
        args += ['--data', mine]
    # Pass the whole load order so our plugin is guaranteed to load last
    args += ['--replace', 'content']
    for c in content:
        args += ['--content', c]
    gf = editing.grass_file(db)
    if gf and gf.lower() not in [g.lower() for g in db.config.get('groundcover', [])]:
        args += ['--groundcover', gf]                  # the mod's grass (drawn only with groundcover on)
    return args


def clean_test(body):
    """Start OpenMW with only the base game, the mod's masters and the mod (nothing else you have installed)."""
    install = db.config.get('install')
    exe = os.path.join(install, 'openmw.exe') if install else None
    if not exe or not os.path.isfile(exe):
        raise editing.EditError('Could not find openmw.exe.')
    if link.game_running():
        raise editing.EditError('The game is still running. Quit it first.')
    editing._require_project(db)
    editing.build(db)
    if getattr(db.project, 'pending_write', None):
        raise editing.EditError('Your mod file is still in use (is the game closing?). Try again in a moment.')
    start = (body.get('start') or '').strip()
    if not start:
        s = release.summary(db)
        start = s['new_places'][0] if s['new_places'] and '(' not in s['new_places'][0] else 'Seyda Neen'
    args, what = release.clean_launch_args(db, start)
    _spawn([exe] + args, install, body.get('launch'))
    return dict(what, start=start)


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    if hasattr(os, 'startfile'):
        os.startfile(path)
    return {'ok': True, 'path': path}


# ----- for the Workshop's own developer (My mod > Get ready to share, at the bottom): the Workshop's own
# source copied into the GitHub folder, then GitHub Desktop opened for the commit. The folder is chosen
# once and kept in workshop_settings.json under dev_github_folder.
SRC_APP = os.path.dirname(os.path.abspath(__file__))              # (this app folder: what runs is what is synced)
SRC_ROOT = os.path.dirname(SRC_APP)
GITHUB_FOLDER_DEFAULT = os.path.join(os.path.expanduser('~'), 'Desktop', 'Morrowind Workshop', 'github', 'morrowind-workshop')
PACKAGING_FILES = ('*.cs', '*.py', '*.txt', '*.manifest', '*.md')     # (never packaging\nexus, never the build output)


def github_desktop_exe():
    exe = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'GitHubDesktop', 'GitHubDesktop.exe')
    return exe if os.path.isfile(exe) else None


def github_status():
    folder = load_settings().get('dev_github_folder') or ''
    return {'folder': folder, 'exists': bool(folder and os.path.isdir(folder)),
            'is_repo': bool(folder and os.path.isdir(os.path.join(folder, '.git'))),
            'suggested': GITHUB_FOLDER_DEFAULT, 'source': SRC_ROOT,
            'packaging': os.path.isdir(os.path.join(SRC_ROOT, 'packaging')), 'desktop': bool(github_desktop_exe())}


def github_pick():
    """Ask for the GitHub folder with Windows' own folder picker (starting at the one chosen before, or the usual
    place); remember it."""
    cur = load_settings().get('dev_github_folder') or GITHUB_FOLDER_DEFAULT
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
          "$d.Description = 'Choose your GitHub folder for the Workshop (the one GitHub Desktop commits from)'; "
          "$d.SelectedPath = %s; "
          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
          "if ($d.ShowDialog($o) -eq 'OK') { $d.SelectedPath }") % ("'" + cur.replace("'", "''") + "'")
    r = subprocess.run(['powershell', '-NoProfile', '-STA', '-Command', ps], capture_output=True, text=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    path = (r.stdout or '').strip()
    if not path:
        return dict(github_status(), cancelled=True)
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(SRC_ROOT):
        raise editing.EditError("That is the Workshop's own folder: choose the GitHub copy, not the source.")
    s = load_settings()
    s['dev_github_folder'] = path
    save_settings(s)
    return github_status()


def _robocopy(src, dst, args):
    r = subprocess.run(['robocopy', src, dst] + args + ['/NFL', '/NDL', '/NJH', '/NP', '/R:2', '/W:1'],
                       capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode >= 8:              # (0-7 are the ways robocopy says it worked)
        raise editing.EditError('Copying %s failed: %s' % (os.path.basename(src), (r.stdout or r.stderr or '').strip()[-400:]))
    m = re.search(r'^\s*Files\s*:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', r.stdout or '', re.M)
    return {'total': int(m.group(1)), 'copied': int(m.group(2)), 'removed': int(m.group(6))} if m else {}


def github_sync(body):
    """app\\ mirrored (less __pycache__) and packaging's source files copied into the GitHub folder, then GitHub
    Desktop opened on it for the commit (the commit itself is the user's)."""
    folder = load_settings().get('dev_github_folder') or ''
    if not folder or not os.path.isdir(folder):
        raise editing.EditError('Choose your GitHub folder first.')
    if os.path.normcase(os.path.abspath(folder)) == os.path.normcase(SRC_ROOT):
        raise editing.EditError("That is the Workshop's own folder: choose the GitHub copy, not the source.")
    out = {'folder': folder, 'app': _robocopy(SRC_APP, os.path.join(folder, 'app'), ['/MIR', '/XD', '__pycache__'])}
    pk = os.path.join(SRC_ROOT, 'packaging')
    if os.path.isdir(pk):
        out['packaging'] = _robocopy(pk, os.path.join(folder, 'packaging'), list(PACKAGING_FILES))    # (top level only)
    out['opened'] = False
    if body.get('open', True):
        exe = github_desktop_exe()
        try:
            if exe:
                # (what GitHub Desktop's own "github <path>" command does: open this repository)
                from urllib.parse import quote
                os.startfile('x-github-client://openLocalRepo/' + quote(folder, safe=''))
            else:
                os.startfile('github-windows://')
            out['opened'] = True
        except OSError as e:
            out['open_error'] = str(e)
            if exe:
                subprocess.Popen([exe], creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
                out['opened'] = True
    return out


def open_project_file(path):
    """Open a mod file as the mod being worked on (and reload), as choosing it from the list does."""
    s = load_settings()
    s['project'] = os.path.relpath(path, APP_DIR)
    save_settings(s)
    db.project = Project(path)
    import background
    background.project_path[0] = path
    db.state = 'loading'
    db.load_async()


def _end_together():
    """Switching to another mod ends building together (cleanly: the others are told)."""
    try:
        import together
        if together.active():
            together.stop(db)
    except Exception as e:
        print('building together:', e)


def enable_in_cfg():
    """Add the project plugin to openmw.cfg (after making a backup)."""
    cfg = os.path.join(db.config['userdir'], 'openmw.cfg')
    with open(cfg, encoding='utf-8', errors='replace') as f:
        text = f.read()
    have = {l.strip().lower() for l in text.splitlines()}
    # the plugin, and its Lua scripts' list when it has some; its grass goes in as groundcover
    names = [n for n in (db.project.plugin, editing.lua_content(db)) if n and ('content=' + n).lower() not in have]
    gf = editing.grass_file(db)
    grass_line = ('groundcover=' + gf) if gf and ('groundcover=' + gf).lower() not in have else None
    if not names and not grass_line:
        return {'ok': True, 'already': True}
    backup = cfg + '.workshop-backup-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(cfg, backup)
    with open(cfg, 'a', encoding='utf-8') as f:
        if not text.endswith('\n'):
            f.write('\n')
        for name in names:
            f.write('content=%s\n' % name)
            db.cfg_content_all.append(name)
        if grass_line:
            f.write(grass_line + '\n')
            db.config.setdefault('groundcover', []).append(gf)
    return {'ok': True, 'backup': backup}


def _settings_cfg():
    return os.path.join(db.config['userdir'], 'settings.cfg')


def groundcover_status():
    """Is OpenMW's groundcover switched on (settings.cfg [Groundcover] enabled)?"""
    path, on, section = _settings_cfg(), False, None
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                s = line.strip()
                if s.startswith('['):
                    section = s.strip('[]').strip().lower()
                elif section == 'groundcover' and '=' in s:
                    k, v = (x.strip() for x in s.split('=', 1))
                    if k.lower() == 'enabled':
                        on = v.lower() == 'true'
    except OSError:
        pass
    gf = editing.grass_file(db) if db.project else None
    return {'enabled': on, 'file': gf, 'in_cfg': bool(gf and gf.lower() in [g.lower() for g in db.config.get('groundcover', [])]),
            'others': [g for g in db.config.get('groundcover', []) if not gf or g.lower() != gf.lower()]}


def groundcover_enable():
    """Switch OpenMW's groundcover on in settings.cfg (after making a backup)."""
    path = _settings_cfg()
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    if os.path.isfile(path):
        shutil.copy2(path, path + '.workshop-backup-' + time.strftime('%Y%m%d-%H%M%S'))
    out, section, done, has_section = [], None, False, False
    for line in lines:
        s = line.strip()
        if s.startswith('['):
            if section == 'groundcover' and not done:
                out.append('enabled = true')
                done = True
            section = s.strip('[]').strip().lower()
            has_section = has_section or section == 'groundcover'
        elif section == 'groundcover' and '=' in s and s.split('=', 1)[0].strip().lower() == 'enabled':
            out.append('enabled = true')
            done = True
            continue
        out.append(line)
    if section == 'groundcover' and not done:
        out.append('enabled = true')
        done = True
    if not has_section:
        out += ['', '[Groundcover]', 'enabled = true']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    return groundcover_status()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ('/', '/index.html'):
                with open(os.path.join(WEB, 'index.html'), 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
            elif u.path.startswith('/web/vendor/') and '..' not in u.path:
                # libraries and fonts shipped with the Workshop (so it works offline); they never change
                fp = os.path.join(WEB, 'vendor', os.path.basename(u.path))
                kind = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
                        '.woff2': 'font/woff2', '.ico': 'image/x-icon',
                        # (the window's icon at its biggest, and its drawing)
                        '.png': 'image/png', '.svg': 'image/svg+xml'}.get(os.path.splitext(fp)[1])
                if not kind or not os.path.isfile(fp):
                    return self._json({'error': 'not found'}, 404)
                with open(fp, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                self.wfile.write(body)
            elif u.path.startswith('/web/docs/') and u.path.endswith('.md') and '..' not in u.path:
                # (the Workshop's own papers, read in a Help window: How the Workshop learns)
                fp = os.path.join(WEB, 'docs', os.path.basename(u.path))
                if not os.path.isfile(fp):
                    return self._json({'error': 'not found'}, 404)
                with open(fp, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/markdown; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
            elif u.path.startswith('/web/') and u.path.endswith('.js') and '..' not in u.path:
                fp = os.path.join(WEB, os.path.basename(u.path))
                if not os.path.isfile(fp):
                    return self._json({'error': 'not found'}, 404)
                with open(fp, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/javascript; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
            elif u.path == '/api/status':
                s = db.summary()
                s['projects'] = list_projects()
                s['outdated'] = code_stamp() > STARTED_CODE + 1
                import background
                background.project_path[0] = db.project.path if db.project else None
                if db.state == 'ready' and db.recs:
                    import learning
                    learning.prewarm(db)                 # (the learning starts now, not at the first furnish)
                s['surveys'] = background.status()      # (what is being learnt from the game's places right now)
                self._json(s)
            elif u.path == '/api/surveys':
                import background
                self._json(background.status())
            elif u.path == '/api/mods':
                # your mods and where their files are (My mod > Your mods)
                import modfiles
                self._json({'mods': modfiles.mods(db)})
            elif u.path == '/api/busy':
                # what is holding things up (the dialogs ask when an answer is slow in coming)
                self._json({'busy': busy()})
            elif u.path == '/api/launch':
                self._json(launch_settings())
            elif u.path == '/api/openmw':
                self._json(openmw_info())
            elif u.path == '/api/openmw/settings':
                import omwsettings, esm
                cfg = db.config or {}
                out = omwsettings.read(cfg.get('userdir') or esm.openmw_userdir(), openmw_info()['install'])
                out['running'] = link.game_running()
                self._json(out)
            elif u.path == '/api/about':
                self._json(helpinfo.about(db))
            elif u.path == '/api/settings':
                self._json(helpinfo.get_settings(db))
            elif u.path == '/api/backups':
                self._json(backups.listing(db.project) if db.project else {'folder': backups.BACKUP_DIR, 'backups': []})
            elif u.path == '/api/together/status':
                import together                      # (answers while loading too: joining reloads the mod)
                self._json(together.status())
            elif db.state != 'ready':
                self._json({'error': 'still loading'}, 503)
            elif u.path == '/api/search':
                types = [t for t in q.get('types', '').split(',') if t]
                self._json(db.search(q.get('q', ''), types, q.get('plugin'), int(q.get('offset', 0)),
                                     min(int(q.get('limit', 200)), 1000), sort=q.get('sort', '')))
            elif u.path == '/api/record':
                self._json(db.record(int(q['i'])))
            elif u.path == '/api/uses':
                import uses
                self._json(uses.report(db, q.get('id', '')))
            elif u.path == '/api/testsetups':
                self._json(test_setups())
            elif u.path == '/api/saves':
                import saves
                self._json({'characters': saves.characters(db), 'play_as': load_settings().get('play_as') or '',
                            'folder': saves.saves_dir()})
            elif u.path == '/api/saves/picture':
                import saves
                pic = saves.picture(q.get('folder', ''))
                if not pic:
                    return self._json({'error': 'no picture'}, 404)
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(pic)))
                self.send_header('Cache-Control', 'max-age=60')
                self.end_headers()
                self.wfile.write(pic)
            elif u.path == '/api/health':
                self._json({'issues': db.issues, 'sources': db.asset_sources, 'config': db.config,
                            'plugins': [{k: v for k, v in p.items() if k != 'counts'} for p in db.plugins]})
            elif u.path == '/api/cellmap':
                key = q['key'] if 'key' in q else db.recs[int(q['i'])][7]
                # (original=1: the place as the game and your other mods have it, without this mod: a
                # "before" window, web/twowin.js)
                self._json(mapdata.cellmap(db, key, original=q.get('original') == '1'))
            elif u.path == '/api/lands':
                # many cells' ground for the 2D map; coarser when zoomed out, so it stays quick
                x0, y0, x1, y1, step = (int(q[k]) for k in ('x0', 'y0', 'x1', 'y1', 'step'))
                limit = 400 if step < 4 else 3000
                if (x1 - x0 + 1) * (y1 - y0 + 1) > limit:
                    return self._json({'error': 'Too many cells at once.'}, 400)
                self._json(mapdata.lands_overview(db, x0, y0, x1, y1, step))
            elif u.path == '/api/land':
                L = mapdata.land(db, int(q['gx']), int(q['gy']), with_textures=q.get('tex') == '1')
                if L.get('exists') and q.get('tex') == '1':
                    L['tid'] = landscape.read(db, int(q['gx']), int(q['gy']))['t']   # texture names, for painting
                self._json(L)
            elif u.path == '/api/org':
                self._json(groups_ed.read(db, q.get('kind', ''), q.get('id', '')))
            elif u.path == '/api/org/options':
                self._json(groups_ed.options(db))
            elif u.path == '/api/global':
                self._json(groups_ed.read_global(db, q.get('id', '')))
            elif u.path == '/api/gmst':
                self._json(groups_ed.gmst_list(db, q.get('q', ''), int(q.get('limit', 200)), int(q.get('offset', 0))))
            elif u.path == '/api/regions':
                import regions
                self._json({'regions': regions.all_regions(db), 'map': regions.region_map(db), 'weather': regions.WEATHER})
            elif u.path == '/api/region':
                import regions
                self._json(regions.read(db, q.get('id', '')))
            elif u.path == '/api/daylight':
                import daylight
                self._json(daylight.table())
            elif u.path == '/api/sky':
                # the game's sky pictures and meshes, for the 3D view's sky
                import daylight
                self._json(daylight.sky(db))
            elif u.path == '/api/assets/record':
                import assets
                self._json(assets.for_record(db, int(q['i'])))
            elif u.path == '/api/assets/thumb':
                import assets
                t = assets.thumb(db, q.get('path', ''))
                if not t:
                    return self._json({'error': 'no picture'}, 404)
                self.send_response(200)
                self.send_header('Content-Type', t[1])
                self.send_header('Content-Length', str(len(t[0])))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(t[0])
            elif u.path == '/api/assets/editors':
                import assets
                self._json(assets.editors())
            elif u.path == '/api/assets/stamp':
                # (when the copies being edited last changed: only files in the mod's own folder)
                import assets
                import library
                bases = [os.path.normcase(os.path.abspath(library.data_dir(db))), os.path.normcase(os.path.abspath(assets.EXPORTS))]
                out = {}
                for f in (q.get('files') or '').split('|'):
                    if f and any(os.path.normcase(os.path.abspath(f)).startswith(b + os.sep) for b in bases):
                        out[f] = assets.stamp(f)
                self._json(out)
            elif u.path in ('/api/anim/source', '/api/anim/people'):
                # (one of a person's animation files; the own animations people in the game move with)
                import nifanim
                try:
                    self._json(nifanim.source(db, q.get('file')) if u.path == '/api/anim/source' else {'rows': nifanim.person_animations(db)})
                except ValueError as e:
                    self._json({'error': str(e)}, 400)
            elif u.path in ('/api/anim/record', '/api/anim/tracks'):
                import nifanim
                try:
                    # (modl: another own animation model to try on a person; '' for the shared one only)
                    d = nifanim.for_record(db, int(q['i']), q['modl'].lower().replace('\\', '/') if 'modl' in q else None)
                    if u.path == '/api/anim/tracks':
                        # (another's animation, to try on this skeleton: no shapes)
                        d = {k: d[k] for k in ('id', 'type', 'name', 'tracks', 'keys', 'groups', 'length', 'files')}
                    self._json(d)
                except ValueError as e:
                    self._json({'error': str(e)}, 400)
            elif u.path == '/api/assets/findtex':
                import assets
                self._json({'found': assets.find_texture(db, q.get('name', ''))})
            elif u.path == '/api/assets/blenderhere':
                import assets
                self._json({'blender': assets.blender()})
            elif u.path == '/api/lev':
                self._json(levlists.read(db, q.get('id', '')))
            elif u.path == '/api/myeffects':
                # your own magic effects (Create > New magic effect), the game's effects to start from
                import myeffects
                self._json(myeffects.read(db))
            elif u.path == '/api/ref/props':
                # who owns a placed object, its lock, key, trap, uses left, soul
                import refprops
                self._json(refprops.read(db, q.get('cell', ''), q.get('ref', '')))
            elif u.path == '/api/sounds':
                import sounds_ed
                self._json({'sounds': sounds_ed.all_sounds(db), 'creatures': sounds_ed.creatures_with_sounds(db),
                            'moments': sounds_ed.MOMENTS})
            elif u.path == '/api/sounds/one':
                import sounds_ed
                self._json(sounds_ed.read(db, q.get('id', '')))
            elif u.path == '/api/sounds/files':
                import sounds_ed
                self._json(sounds_ed.files(db, q.get('q', '')))
            elif u.path == '/api/sounds/creature':
                import sounds_ed
                self._json(sounds_ed.creature_sounds(db, q.get('id', '')))
            elif u.path == '/api/verify':
                # the CS's "verify": record-by-record checks of the mod, in plain words
                import verify
                editing._require_project(db)
                self._json(verify.summary(db))
            elif u.path == '/api/place/settings':
                self._json({'settings': places.read(db, q.get('key', '')), 'presets': places.presets()})
            elif u.path == '/api/release/check':
                self._json(release.checks(db))
            elif u.path == '/api/release/info':
                editing._require_project(db)
                self._json(release.info(db))
            elif u.path == '/api/release/readme':
                editing._require_project(db)
                self._json({'text': release.readme(db), 'bbcode': release.readme(db, bbcode=True)})
            elif u.path == '/api/script':
                self._json(mwscript.read(db, q.get('id', '')))
            elif u.path == '/api/script/info':
                self._json({'reference': mwscript.reference(), 'templates': mwscript.templates(), 'mine': mwscript.my_scripts(db)})
            elif u.path == '/api/npc':
                self._json(npc.read(db, q.get('id', '')))
            elif u.path == '/api/npc/options':
                self._json(npc.options(db))
            elif u.path == '/api/npc/calc':
                self._json(npc.autocalc(db, q.get('race', ''), q.get('cls', ''), int(q.get('level') or 1), q.get('female') == '1'))
            elif u.path == '/api/land/textures':
                self._json(landscape.textures(db))
            elif u.path == '/api/landmap':
                # every outdoor cell by how freely it may be shaped, and the cells marked (landsurvey.py)
                import landsurvey
                self._json(landsurvey.landmap(db))
            elif u.path == '/api/land/shadeinfo':
                # what the game's shading near this cell is like (landshade.py)
                import landshade
                self._json(landshade.summary(db, int(q['gx']), int(q['gy'])))
            elif u.path == '/api/model':
                self._json(model_for(q))
            elif u.path == '/api/file':
                # textures for the 3D preview (only from the game's texture folders)
                path = (q.get('path') or '').lower().replace('\\', '/')
                data = db.meshes.read(path) if path.startswith(('textures/', 'icons/', 'sound/')) and '..' not in path else None
                if data is None:
                    return self._json({'error': 'not found'}, 404)
                self.send_response(200)
                self.send_header('Content-Type', {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.flac': 'audio/flac'}.get(
                    os.path.splitext(path)[1], 'application/octet-stream'))
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'max-age=3600')
                self.end_headers()
                self.wfile.write(data)
            elif u.path == '/api/sound':
                # a sound record's file, to hear it in the browser
                from esm import iter_subrecords, zstr
                ri = db.resolve_id(q.get('id', ''))
                path = None
                if ri is not None and db.recs[ri][0] == 'SOUN':
                    r = db.recs[ri]
                    for st, sd in iter_subrecords(db.files[r[3]].record_at(r[4])[2]):
                        if st == 'FNAM':
                            path = 'sound/' + zstr(sd).lower().replace('\\', '/')
                data = db.meshes.read(path) if path and '..' not in path else None
                if data is None:
                    return self._json({'error': 'That sound\'s file is missing.'}, 404)
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg' if path.endswith('.mp3') else 'audio/wav')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'max-age=3600')
                self.end_headers()
                self.wfile.write(data)
            elif u.path == '/api/create/options':
                self._json(create.options(db))
            elif u.path == '/api/create/interiors':
                style = q.get('style', '')
                lst = [t for t in create.interior_templates(db) if not style or t['style'] == style]
                self._json(lst if q.get('all') else lst[:400])        # (all=1: the secret-door dialog lists every style)
            elif u.path == '/api/create/doors':
                self._json(create.outside_doors(db, q.get('template'), q.get('style')))
            elif u.path == '/api/create/suggest_id':
                self._json({'id': create.suggest_id(db, create._prefix(db) if db.project else 'mod', q.get('name', ''))})
            elif u.path == '/api/create/name':
                # a name in the manner of the game's own people of that race and sex (the 🎲 button)
                self._json({'name': create.suggest_name(db, q.get('race', ''), q.get('sex') == 'female')})
            elif u.path == '/api/create/popular':
                # the items of these types the game uses most: the usual bases for a new item
                self._json(create.popular(db, [t for t in q.get('types', '').split(',') if t], min(int(q.get('limit', 8)), 40)))
            elif u.path == '/api/link':
                self._json(link.status())
            elif u.path == '/api/loadorder':
                self._json(loadorder.read(db))
            elif u.path == '/api/adopt/candidates':
                # plugins that could be opened as the mod itself (adopt.py)
                import adopt
                self._json(adopt.candidates(db))
            elif u.path == '/api/test':
                # quest testing: the mod's quests, watched globals and items, and what the game says about them
                sig = (id(db.project), hash(getattr(db.project, 'last_state', None) or ''))   # (changes on every edit)
                if getattr(link, '_watch_sig', None) != sig:
                    link._watch_sig = sig
                    if link.refresh_watch():
                        link.write_state(bump=False)
                names =sorted(link.watch[0], key=str.lower)
                ginfo = questtest.globals_info(db, names)
                out = {'connected': link.connected(), 'quests': questtest.quest_ids(db) if db.project else [],
                       'globals': [dict(ginfo.get(n, {'type': '?', 'start': None, 'missing': True}), name=n,
                                        game=link.game['globals'].get(n.lower())) for n in names],
                       'items': [{'id': i, 'game': link.game['items'].get(i.lower())} for i in sorted(link.watch[1], key=str.lower)],
                       'game_quests': link.game['quests']}
                if q.get('quest'):
                    out['quest_in_game'] = link.in_game('DIAL', q['quest'])
                self._json(out)
            elif u.path == '/api/palette':
                self._json(mapdata.palette(db, q['key']))
            elif u.path == '/api/style/themes':
                # the Style palette's tabs (stylesurvey.py); {'ready': False, 'waiting'} while it's learnt
                import stylesurvey
                out = stylesurvey.themes(db)
                if q.get('key'):
                    try:
                        out['here'] = stylesurvey.theme_here(db, q['key'])
                    except Exception:
                        out['here'] = None
                self._json(out)
            elif u.path == '/api/style/theme':
                # one theme's building pieces, furniture, decor and sets ('*': used everywhere)
                import stylesurvey
                t = stylesurvey.theme(db, q.get('name', ''))
                if t is None:
                    return self._json({'error': 'No such style, or the styles are still being learnt.'}, 404)
                self._json(t)
            elif u.path == '/api/dlg/index':
                kind = q.get('kind')
                self._json(dialogue.index(db, q.get('q', ''), int(kind) if kind not in (None, '') else None,
                                          q.get('mine') == '1', min(int(q.get('limit', 400)), 20000)))
            elif u.path == '/api/dlg/topic':
                self._json(dialogue.topic(db, q['key']))
            elif u.path == '/api/dlg/character':
                self._json(dialogue.character(db, q['id']))
            elif u.path == '/api/convo/map':
                import convo
                self._json(convo.conversation_map(db, q['id'], q.get('scope', 'own'), q.get('cell')))
            elif u.path == '/api/convo/problems':
                import convo
                self._json(convo.problems(db, q['id'], q.get('cell')))
            elif u.path == '/api/convo/build/list':
                import convbuild
                self._json(convbuild.conversations(db, q['id']))
            elif u.path == '/api/convo/build':
                import convbuild
                self._json(convbuild.read(db, q['id'], q['topic']))
            elif u.path == '/api/convo/quest':
                import convo
                self._json(convo.quest_map(db, q['key']))
            elif u.path == '/api/dlg/quest':
                out = dialogue.quest(db, q['key'])
                out['used'] = dialogue.quests_using(db, q['key'])
                self._json(out)
            elif u.path == '/api/furnish/rooms':
                import taste
                info = furnish.rooms(db, q['key'])
                self._json({'rooms': [{k: v for k, v in r.items() if not k.startswith('_')} for r in info['rooms']],
                            'purposes': list(furnish.RECIPES), 'furnished': len(furnish.placed_before(db, q['key'])),
                            'examples': [p for p in taste.listing(db) if p.get('exists') and p.get('game_made')]})
            elif u.path == '/api/taste':
                # the taste set: the game's places marked as exemplary (taste.py); ?key= says whether that
                # place is one, and whether it could be (only the game's own places can teach Auto-furnish)
                import taste
                import kits
                out = {'places': taste.listing(db), 'weight': taste.WEIGHT}
                if q.get('key'):
                    k = q['key'].lower()
                    out['this'] = {'key': k, 'marked': taste.is_marked(k), 'game_made': kits.game_made(db, k)}
                self._json(out)
            elif u.path == '/api/furnish/piece':
                # can this placed piece be dressed the game's way, and does it carry a dressing already
                return self._json(furnish.piece_info(db, q['cell'], q['ref']))
            elif u.path == '/api/furnish/room':
                # which room is at this spot (?at=x,y,z) or this id (?room=), and what Auto-furnish laid in it
                if q.get('room'):
                    return self._json(furnish.room_info(db, q['cell'], room=int(q['room'])))
                at = [float(v) for v in (q.get('at') or '0,0').split(',')]
                return self._json(furnish.room_info(db, q['cell'], at=at))
            elif u.path == '/api/ref/contents':
                # the things standing on a placed piece (its books, dishes, wares), for selecting them with it
                import contents
                return self._json(contents.on_piece(db, q['cell'], q['ref']))
            elif u.path == '/api/furnish/placesurvey':
                # where the game stands each kind of furniture (placesurvey.py)
                import placesurvey
                s = placesurvey.ready(db)
                if not s:
                    return self._json({'ready': False, 'note': 'The placement survey is running in the background (a few minutes).'})
                self._json({'ready': True, 'cells': s['cells'], 'report': placesurvey.report(db), 'fams': s['fams']})
            elif u.path == '/api/furnish/catalogue':
                # the catalogue rules, per style, with their rates (catalogue.py)
                import catalogue
                s = catalogue.ready(db)
                if not s:
                    return self._json({'ready': False, 'note': 'The catalogue survey is running in the background (a few minutes).'})
                self._json({'ready': True, 'cells': s['cells'], 'report': catalogue.report(db), 'styles': s['styles']})
            elif u.path == '/api/furnish/scenes':
                # the game's scenes per room kind, and how often a piece of each kind stands alone (arrangesurvey.py)
                import arrangesurvey
                s = arrangesurvey.ready(db)
                if not s or 'alone' not in s:
                    return self._json({'ready': False, 'note': 'The arrangement survey is running in the background (a few minutes).'})
                self._json({'ready': True, 'cells': s['cells'], 'report': arrangesurvey.scenes_report(db)})
            elif u.path == '/api/prefabs':
                self._json(groups.prefabs())
            elif u.path == '/api/items/options':
                self._json(items.options(db))
            elif u.path in ('/api/forge/options', '/api/forge/propose', '/api/forge/like'):
                # the Forge: a new weapon or armour piece with the numbers the game gives its type and material
                import gearsurvey
                if u.path.endswith('options'):
                    return self._json(gearsurvey.options(db))
                if u.path.endswith('like'):
                    it = gearsurvey._read(db, int(q.get('i', -1))) if q.get('i', '').lstrip('-').isdigit() else None
                    return self._json({'type': it['type'], 'mat': it['mat'], 'i': it['i'], 'kind': it['kind']} if it else {'error': 'Not a weapon or armour piece.'}, 200 if it else 400)
                bw = q.get('between')
                between = (lambda p: (p[0], p[1], float(p[2])))(bw.split(',')) if bw else None
                try:
                    return self._json(gearsurvey.propose(db, q.get('kind'), q.get('type'), q.get('mat') or None, between))
                except ValueError as e:
                    return self._json({'error': str(e)}, 400)
            elif u.path == '/api/spellgive/options':
                # Give spells to people: who there is to pick from (spellgive.py)
                import spellgive
                self._json(spellgive.options(db))
            elif u.path == '/api/grass':
                import grass
                gx, gy = int(q.get('gx', 0)), int(q.get('gy', 0))
                self._json({'cells': grass.cells_near(db, gx, gy, int(q.get('r', 1))), 'status': groundcover_status(),
                            'total': grass.count(db.project) if db.project else 0})
            elif u.path == '/api/lua':
                import luascripts
                self._json(luascripts.listing(db))
            elif u.path == '/api/lua/script':
                import luascripts
                self._json(luascripts.read(db, q.get('name', '')))
            elif u.path == '/api/fixit/scan':
                # (?all=1: every see-through spot, not only what's worse than the game's own places)
                import fixit
                self._json(fixit.scan(db, q.get('cell', ''), everything=q.get('all') in ('1', 'true')))
            elif u.path == '/api/build/gapsurvey':
                # how gappy the game's own places are, style by style (?style=in_hlaalu for one)
                import gapsurvey
                self._json(gapsurvey.summary(db, [q['style']] if q.get('style') else None))
            elif u.path == '/api/fixit/variants':
                import fixit
                self._json(fixit.variants(db, q.get('cell', ''), q.get('ref', '')))
            elif u.path == '/api/scatter/sets':
                import scatter
                self._json(scatter.sets(db, q.get('cell', '')))
            elif u.path == '/api/library':
                import library
                self._json(library.listing(db))
            elif u.path == '/api/library/textures':
                import library
                self._json(library.model_textures(db, int(q['i'])))
            elif u.path == '/api/packs/browse':
                import packshelf
                self._json(packshelf.browse())
            elif u.path == '/api/packs/picture':
                import packshelf
                try:
                    got = packshelf.picture(q.get('source', '0'), q.get('ref', ''))
                except editing.EditError:
                    got = None
                if not got:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('Content-Type', got[1])
                self.send_header('Content-Length', str(len(got[0])))
                self.send_header('Cache-Control', 'max-age=600')
                self.end_headers()
                self.wfile.write(got[0])
            elif u.path == '/api/brushes':
                import scatter
                self._json({'brushes': [scatter._clean(db, b) for b in scatter.load_brushes()]})
            elif u.path == '/api/brushes/item':
                import scatter
                self._json(dict(scatter.item_defaults(db, q.get('id', '')), id=q.get('id', '')))
            elif u.path == '/api/item':
                import items_ed
                self._json(items_ed.read(db, q.get('id', '')))
            elif u.path == '/api/items/template':
                self._json(items.template_info(db, int(q['i'])))
            elif u.path == '/api/build/styles':
                import styletrust
                # (wait=False: within the first minute the stairs are still being learnt in the survey process;
                # the list comes at once with stairs_pending on those, and the page asks again until none are)
                self._json([dict(s, trust=styletrust.rate(s['id'], s.get('uses')), kind=styletrust.kind(s['id'], s.get('uses'))) for s in builder.styles(db, wait=False)])
            elif u.path == '/api/build/plans':
                # saved floor plans, and the places in your mod built from pieces (to start from one)
                import plans
                self._json({'plans': plans.list_plans(), 'built': plans.built_places(db)})
            elif u.path == '/api/build/plans/get':
                import plans
                self._json(plans.load_plan(q.get('name', '')))
            elif u.path == '/api/build/plans/cell':
                import plans
                self._json(plans.plan_of_cell(db, q.get('key', '')))
            elif u.path == '/api/build/plan_from_cell':
                # one of the game's own places read back as a plan for the room planner (nothing is changed)
                import planfrom
                self._json(planfrom.plan_from_cell(db, q.get('cell', '')))
            elif u.path == '/api/build/from_building':
                # a building outdoors (the piece or door right-clicked): is it closed and sound, and the
                # interior that would be built in it (nothing is changed; frombuilding.py)
                import frombuilding
                self._json(frombuilding.preview(db, q.get('cell', ''), q.get('ref', ''), q.get('door') or None, q.get('tolerance') or 'usual'))
            elif u.path == '/api/build/modules':
                # whole buildings of the game's to put down outdoors, sized in interior tiles (housemodules.py)
                import housemodules
                self._json({'styles': housemodules.styles(db),
                            'modules': housemodules.catalogue(db, q.get('style') or None, not q.get('all'), 120)})
            elif u.path == '/api/build/modules/ready':
                # the game's one-piece homes (a shack, a hut, a tent, a Nordic house): their building to place, and the
                # ready-made interior the game puts behind it (podtwins.py)
                import podtwins
                s = podtwins.ready(db)
                rows = []
                for ext, mod in ((s or {}).get('modules') or {}).items():
                    t = podtwins.twin_for(db, ext)
                    if t:
                        rows.append({'key': ext, 'twin': t, 'uses': sum(((s.get('twins') or {}).get(ext) or {}).values()),
                                     'style': mapdata.style_of(ext), 'items': mod['items'], 'example': mod['example']})
                rows.sort(key=lambda r: -r['uses'])
                self._json({'ready': s is not None, 'homes': rows})
            elif u.path == '/api/build/modules/joins':
                import housemodules
                self._json(housemodules.candidates(db, q.get('cell', ''), q.get('ref', ''), True, bool(q.get('walls'))))
            elif u.path == '/api/build/plan_from_cell/places':
                # the game's interiors the Workshop can build a plan from (scored in a background pass the
                # first time: ?all=1 lists every kit-built interior unscored), for "Plan from a place in the game"
                import planfrom
                self._json(planfrom.places(db) if q.get('all') else planfrom.gated(db))
            elif u.path == '/api/furnish/wallsurvey':
                # how the game hangs banners, tapestries and hangers (what with what, and where)
                import wallsurvey
                import kits
                ids = [x for x in (q.get('ids') or '').split(',') if x]
                if not ids:
                    ids = sorted({k for (t, k) in db.by_key if t in ('STAT', 'ACTI', 'LIGH') and wallsurvey.HANGY.search(k)
                                  and kits.game_uses(db, k) >= 3})[:400]
                self._json(wallsurvey.summary(db, ids))
            elif u.path == '/api/furnish/shelfsurvey':
                # how the game dresses bookshelves, shelves, tables, desks and counters: ?id=one model (with
                # its dressings), or ?style=furn_de_r / t_de_furnm (a part of the ID) for a summary of each
                import shelfsurvey
                if q.get('id'):
                    s = shelfsurvey.survey(db, q['id'])
                    return self._json(dict(shelfsurvey.summary_of(db, q['id']),
                                           dressings=[{'cell': d['cell'], 'purpose': d['purpose'],
                                                       'objects': [{k: v for k, v in o.items() if k != 'fp'} for o in d['objects']]}
                                                      for d in s['dressings'][:int(q.get('raw') or 20)]]))
                self._json(shelfsurvey.summary(db, shelfsurvey.models(db, q.get('style'))[:int(q.get('limit') or 40)]))
            elif u.path == '/api/furnish/containersurvey':
                # what the game's containers hold, by family, room kind and theme: ?family=barrel&kind=kitchen&theme=house
                import containersurvey
                self._json(containersurvey.summary(db, q.get('family'), q.get('kind'), q.get('theme')))
            elif u.path == '/api/furnish/arrangesurvey':
                # the game's set pieces: how it groups furniture in a room (arrangesurvey.py)
                import arrangesurvey
                s = arrangesurvey.ready(db)
                if not s:
                    return self._json({'busy': True, 'text': 'Surveying the game\'s rooms (a few minutes the first time)…'})
                self._json({'report': arrangesurvey.report(db), 'groups': s['groups'], 'cells': s['cells']})
            elif u.path == '/api/furnish/wealthsurvey':
                # how well off the game's homes are, by band (wealthsurvey.py): sets, density, hangings, values
                import wealthsurvey
                B = wealthsurvey.bands(db)
                if B is None:
                    return self._json({'ready': False, 'note': 'The wealth survey is running in the background (several minutes).'})
                self._json({'ready': True, 'bands': B, 'rules': {b: wealthsurvey.rule(db, b) for b in wealthsurvey.BANDS},
                            'report': wealthsurvey.report(db)})
            elif u.path == '/api/furnish/trades':
                # the classes and factions for "Furnish as: by trade or faction" (the band each lives in)
                import wealthsurvey
                self._json({'ready': wealthsurvey.trades(db) is not None, 'trades': wealthsurvey.trade_options(db),
                            'read_as': wealthsurvey.trade(db, q.get('text')) if q.get('text') else None})
            elif u.path == '/api/furnish/roomsurvey':
                # the room survey's numbers: themes (what a tavern, a shop, a temple, a guild, a manor
                # contain), clutter groups, and the room kinds
                import roomsurvey
                s = roomsurvey.ready(db)
                if not s:
                    return self._json({'ready': False, 'note': 'The room survey is running in the background (a few minutes).'})
                self._json({'ready': True, 'cells': s['cells'], 'themes': s['layout'].get('themes'), 'themes_text': roomsurvey.themes_report(db),
                            'clusters': s.get('clusters'), 'kinds': s['kinds']})
            elif u.path == '/api/populate/castsurvey':
                # who the game's people are, place by place (castsurvey.py): the whole survey once learnt
                import castsurvey
                import learning
                s = castsurvey.ready(db)
                self._json({'ready': s is not None, 'learning': learning.populate_pending(db) if s is None else [],
                            'survey': s if q.get('full') else ({k: s[k] for k in ('places', 'people', 'wealth_cuts')} if s else None)})
            elif u.path == '/api/populate/peoplesurvey':
                # where the game's people stand, by role and furniture (for Populate)
                import peoplesurvey
                self._json(peoplesurvey.summary(db))
            elif u.path == '/api/build/jointsurvey':
                # where the game's own places stand posts and columns, corner by corner
                import jointsurvey
                self._json(jointsurvey.summary(db, [q['style']] if q.get('style') else None))
            elif u.path == '/api/build/closuresurvey':
                # how the game closes the spaces round its stairs, style by style (closuresurvey.py)
                import closuresurvey
                if q.get('style'):
                    s = closuresurvey.survey(db, q['style'])
                    return self._json({'report': closuresurvey.report(db, [q['style']]),
                                       'columns': {sid: {'%d,%d,%d' % k: v for k, v in closuresurvey.column(db, q['style'], sid).items()}
                                                   for sid in (s or {}).get('stairs', {})}})
                self._json({'report': closuresurvey.report(db)})
            elif u.path == '/api/build/layoutsurvey':
                # how the game lays out and builds its interiors: room sizes, doorways, windows, columns,
                # whole-house layouts, per style family (or per kit with by=style); layoutsurvey.py
                import layoutsurvey
                by = 'style' if q.get('by') == 'style' else 'family'
                self._json({'report': layoutsurvey.report(db, by=by), 'summary': layoutsurvey.summary(db, by=by)})
            elif u.path == '/api/build/stairsurvey':
                # what the game's own places do round their stairs (style by style, and over all)
                import stairsurvey
                if q.get('raw') and q.get('style'):
                    return self._json(stairsurvey.survey(db, q['style'])[:int(q.get('raw') or 20)])
                self._json(stairsurvey.summary(db, [q['style']] if q.get('style') else None))
            elif u.path == '/api/dlg/options':
                self._json(dialogue.options(db))
            elif u.path == '/api/dlg/mine':
                self._json({'characters': dialogue.my_characters(db) if db.project else [],
                            'topics': dialogue.index(db, mine=True) if db.project else []})
            elif u.path == '/api/ai/status':
                self._json({'configured': bool(api_key() or os.environ.get('ANTHROPIC_API_KEY')),
                            'model': ai.MODEL, 'busy': assistant.lock.locked(), 'status': assistant.status,
                            'steps': assistant.steps, 'turns': sum(1 for m in assistant.messages if m['role'] == 'user'
                                                                   and isinstance(m['content'], str))})
            elif u.path == '/api/dev/github':
                self._json(github_status())
            elif u.path == '/api/changes':
                # (asked every second or so by each window: what the other windows changed since)
                self._json(dict(editing.changes_since(int(q.get('since', 0))),
                                project=db.project.plugin if db.project else None))
            elif u.path == '/api/project':
                p = db.project
                parent, sizes = {}, {}
                if p:
                    parent, _kids, _f = editing.activity(db)
                    sizes = editing.branch_sizes(db)
                log = [{'id': e.get('id'), 't': e.get('t'), 'text': editing.note_label(p, e.get('text'), e.get('id')), 'undone': e.get('undone', False),
                        'can_undo': bool(e.get('diff')) and not e.get('undone'),
                        'parent': parent.get(e.get('id')), 'inside': sizes.get(e.get('id'), 0)}
                       for e in (p.log[-200:] if p else [])]
                self._json({'project': db.project_summary(), 'log': log,
                            'changes': changes_list() if p else [], 'path': editing.plugin_path(db) if p else None})
            else:
                self._json({'error': 'not found'}, 404)
        except editing.EditError as e:
            self._json({'error': str(e)}, 400)
        except Exception as e:
            if db.state != 'ready' or 'mmap closed' in str(e):
                # (a request still running when a reload began reads files the reload closed: the crawl test's
                # "ValueError: mmap closed or invalid" from Grow grass during Undo my changes. Say "still loading")
                return self._json({'error': 'Still loading, try again in a moment.'}, 503)
            import traceback
            traceback.print_exc()
            self._json({'error': '%s: %s' % (type(e).__name__, e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get('Content-Length') or 0)
        editing.ORIGIN.window = self.headers.get('X-Workshop-Window')       # (whose change this is: editing.CHANGES)
        if u.path == '/api/library/upload':
            # a file dropped into the Library, as it is (not JSON): kept with the others of the same drop
            import library
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if n > 400 * 1024 * 1024:
                return self._json({'error': 'That file is too big (over 400 MB).'}, 400)
            try:
                return self._json(library.receive(q.get('batch', ''), q.get('name', ''), self.rfile.read(n)))
            except editing.EditError as e:
                return self._json({'error': str(e)}, 400)
        if u.path == '/api/library/icon':
            import library
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                with edit_lock:
                    return self._json(library.save_icon(db, q.get('id', ''), self.rfile.read(n)))
            except editing.EditError as e:
                return self._json({'error': str(e)}, 400)
        if u.path == '/api/pack/open':
            # a shared pack (a zip), as it is
            import pack
            if n > 400 * 1024 * 1024:
                return self._json({'error': 'That pack is too big (over 400 MB).'}, 400)
            try:
                with edit_lock:
                    return self._json(pack.open_pack(db, self.rfile.read(n)))
            except editing.EditError as e:
                return self._json({'error': str(e)}, 400)
        body = json.loads(self.rfile.read(n) or b'{}') if n else {}
        if u.path in ('/api/together/host', '/api/together/join', '/api/together/stop'):
            import together
            try:
                if u.path == '/api/together/host':
                    if together.active() and body.get('restart'):
                        together.stop(db, keep_auto=True)        # (again with a new address or a new code)
                    return self._json(together.host(db, edit_lock, body.get('name', ''), body.get('port'), body.get('public'),
                                                     bool(body.get('new_code'))))
                if u.path == '/api/together/stop':
                    return self._json(together.stop(db))
                saved = load_settings().get('together_joined') or {}
                code = body.get('code') or saved.get('code', '')
                name = body.get('name') or saved.get('name', '')
                return self._json(dict(together.join(db, edit_lock, code, name, open_project_file), reload=True))
            except editing.EditError as e:
                return self._json({'error': str(e)}, 400)
        if u.path in ('/api/packs/sources', '/api/packs/look', '/api/packs/add'):
            import packshelf
            try:
                if u.path == '/api/packs/sources':
                    return self._json({'sources': packshelf.save_sources(body.get('sources'))})
                if u.path == '/api/packs/look':
                    return self._json(packshelf.look(body.get('source', 0), body.get('ref', '')))
                with edit_lock:
                    return self._json(packshelf.add(db, body.get('source', 0), body.get('ref', '')))
            except editing.EditError as e:
                return self._json({'error': str(e)}, 400)
        if u.path == '/api/pack/make':
            import pack
            pic = None
            if body.get('picture'):
                import base64
                try:
                    pic = base64.b64decode(str(body['picture']).split(',', 1)[-1])[:8 * 1024 * 1024]
                except ValueError:
                    pic = None
            try:
                data = pack.export(db, body.get('name'), body.get('prefabs') or [], body.get('brushes') or [], body.get('library') or [],
                                   body.get('description', ''), body.get('author', ''), pic)
                if body.get('share'):
                    # straight into a folder of the pack shelf (a synced one: everyone who has it sees it)
                    import packshelf
                    return self._json({'shared': packshelf.share(data, body.get('name') or 'My pack', body.get('share_to'))})
            except editing.EditError as e:
                return self._json({'error': str(e)}, 400)
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        try:
            if u.path == '/api/reload':
                if db.state != 'loading':
                    db.state = 'loading'
                    db.load_async()
                return self._json({'ok': True})
            # the OpenMW button works even while (or because) the game data couldn't load
            if u.path in ('/api/openmw/settings', '/api/openmw/settings/open'):
                import omwsettings, esm
                userdir = (db.config or {}).get('userdir') or esm.openmw_userdir()
                if u.path.endswith('/open'):
                    # (settings.cfg in whatever Windows opens text files with; made empty first if there's none yet)
                    p = omwsettings.path_of(userdir)
                    if not os.path.isfile(p) and os.path.isdir(userdir):
                        open(p, 'w', encoding='utf-8').close()
                    if not os.path.isfile(p):
                        return self._json({'error': "OpenMW's settings folder wasn't found. Run the OpenMW Launcher once."}, 400)
                    if body.get('open', True) and hasattr(os, 'startfile'):
                        os.startfile(p)
                    return self._json({'ok': True, 'path': p})
                try:
                    return self._json(omwsettings.write(userdir, openmw_info()['install'], body.get('changes') or []))
                except omwsettings.SettingsError as e:
                    return self._json({'error': str(e)}, 400)
            if u.path == '/api/openmw/start':
                editing.flush(db)           # (the plugin on disk before the game reads it)
                return self._json(start_openmw(body.get('mode', 'menu'), body.get('launch')))
            if u.path == '/api/launch':
                return self._json(save_launch(body))
            if u.path == '/api/openmw/pick':
                return self._json(pick_openmw())
            if u.path == '/api/adopt/pick':
                import adopt
                return self._json(adopt.pick_file(db))
            # help menu and settings (these work while the game data loads, too)
            if u.path == '/api/settings':
                r = helpinfo.set_settings(body)
                if body.get('openmw_reset') and db.state != 'loading':
                    db.state = 'loading'
                    db.load_async()
                return self._json(r)
            if u.path == '/api/report':
                return self._json(helpinfo.report(db, link, body.get('what', ''), body.get('page')))
            if u.path == '/api/dev/github/pick':
                return self._json(github_pick())
            if u.path == '/api/dev/github/sync':
                return self._json(github_sync(body))
            if u.path == '/api/open_place':
                where = {'projects': PROJECTS_DIR, 'backups': backups.BACKUP_DIR,
                         'reports': os.path.join(APP_DIR, 'reports'), 'app': APP_DIR,
                         'openmw': (db.config or {}).get('userdir')}.get(body.get('what'))
                if not where:
                    return self._json({'error': 'Unknown folder.'}, 400)
                return self._json(open_folder(where))
            if u.path == '/api/backups/restore':
                if not db.project:
                    return self._json({'error': 'No mod is open.'}, 400)
                with edit_lock:
                    try:
                        backups.restore(db.project, body.get('file', ''))
                    except ValueError as e:
                        return self._json({'error': str(e)}, 400)
                    db.project = Project(db.project.path)     # (fresh, without the undo history of the old one)
                    db.state = 'loading'
                    db.load_async()
                return self._json({'ok': True})
            if db.state != 'ready':
                return self._json({'error': 'Still loading, try again in a moment.'}, 503)
            if u.path == '/api/models':
                # many models at once for the 3D world view: id -> shapes (or None)
                out = {}
                for rid in body.get('ids', [])[:200]:
                    m = model_for({'id': rid})
                    out[rid] = m.get('shapes')
                return self._json(out)
            if u.path == '/api/ai/key':
                s = load_settings()
                key = (body.get('key') or '').strip()
                if key:
                    s['anthropic_api_key'] = key
                else:
                    s.pop('anthropic_api_key', None)
                save_settings(s)
                return self._json({'ok': True, 'configured': bool(key or os.environ.get('ANTHROPIC_API_KEY'))})
            if u.path == '/api/clienterror':
                # a fault in the page, written to the log so "nothing happens" can be traced
                print('page error (%s, %s): %s' % (str(body.get('view') or '')[:40], str(body.get('where') or '')[:200],
                                                    str(body.get('msg') or '')[:2000].replace('\n', ' | ')))
                return self._json({'ok': True})
            if u.path == '/api/loadorder/check':
                info = loadorder.read(db)
                rows = {r['name'].lower(): r for r in info['enabled'] + info['available']}
                order = body.get('order') or []
                return self._json({'problems': loadorder.problems(order, rows),
                                   'sorted': loadorder.sort_masters(order, rows)})
            if u.path == '/api/loadorder/save':
                try:
                    r = loadorder.save(db, body.get('order') or [])
                except loadorder.LoadOrderError as e:
                    return self._json({'error': str(e)}, 400)
                r['game_running'] = link.game_running()
                # plugins ticked on at the end are just added to what is loaded; any other change
                # reads everything again in the new order (from the record cache)
                r.update(db.apply_order(r.pop('order')))
                return self._json(r)
            if u.path == '/api/link/arm':
                if body.get('id'):
                    link.arm_from_workshop(body['id'], body.get('name') or body['id'])
                else:
                    link.disarm_from_workshop()
                return self._json(link.status())
            if u.path == '/api/link/teleport':
                if not link.connected():
                    return self._json({'error': 'The game is not running from the Workshop. Use Play here first.'}, 400)
                link.teleport(body['cell'], float(body['x']), float(body['y']), float(body['z']),
                              float(body.get('yaw') or 0))
                return self._json({'ok': True})
            if u.path == '/api/test/watch':
                if link.refresh_watch(body.get('globals') or [], body.get('items') or []):
                    link.write_state(bump=False)
                return self._json({'ok': True})
            if u.path in ('/api/test/cmd', '/api/test/goto'):
                if not link.connected():
                    return self._json({'error': 'The game is not running from the Workshop. Use Play here first.'}, 400)
                if u.path == '/api/test/goto':
                    found = questtest.find_person(db, body.get('npc') or '')
                    if not found:
                        return self._json({'error': '%s isn\'t placed anywhere in the world.' % body.get('npc')}, 400)
                    key, name, p = found
                    x, y, z, yaw = questtest.spot_in_front(p)
                    link.teleport(key, x, y, z, yaw)
                    return self._json({'ok': True, 'place': name})
                verb, args = body.get('verb'), [a for a in (body.get('args') or []) if a is not None]
                need = {'journal': 2, 'stage': 2, 'finish': 2, 'reset': 1, 'global': 2, 'give': 2, 'take': 2, 'topic': 1}
                if verb not in need or len(args) < need[verb] or not str(args[0]).strip():
                    return self._json({'error': 'Unknown or incomplete test command.'}, 400)
                if verb in ('give', 'take') and db.resolve_id(str(args[0]).strip()) is None:
                    return self._json({'error': 'There is no item "%s".' % args[0]}, 400)
                if verb in ('give', 'take', 'global'):
                    link.refresh_watch(extra_globals=[args[0]] if verb == 'global' else [],
                                       extra_items=[args[0]] if verb != 'global' else [])
                return self._json({'seq': link.command(verb, *[str(a).strip() for a in args[:need[verb]]])})
            if u.path == '/api/quit':
                # from the launcher's Quit (the custom header keeps web pages from doing this)
                if self.headers.get('X-Workshop-Quit') != '1':
                    return self._json({'error': 'Not allowed.'}, 403)
                quit_soon()
                return self._json({'ok': True})
            if u.path == '/api/ai/reset':
                assistant.reset()
                return self._json({'ok': True})
            if u.path == '/api/ai/chat':
                if not db.project:
                    return self._json({'error': 'Start a mod first, so the assistant has somewhere to save its work.'}, 400)
                if assistant.lock.locked():
                    return self._json({'error': 'The assistant is still working on the last request.'}, 409)
                with edit_lock:
                    try:
                        return self._json(assistant.chat(body.get('message', ''), body.get('ctx') or {}))
                    except ai.ToolError as e:
                        return self._json({'error': str(e)}, 400)
            if u.path.startswith('/api/lua/'):
                import luascripts
                if u.path == '/api/lua/check':
                    return self._json({'problems': luascripts.check_text(body.get('text'), body.get('kind'))})
                if u.path == '/api/lua/new':
                    return self._json(luascripts.create(db, body.get('name'), body.get('template') or 'blank'))
                if u.path == '/api/lua/save':
                    return self._json(luascripts.save(db, body.get('name'), body.get('data') or {}))
                if u.path == '/api/lua/delete':
                    return self._json(luascripts.delete(db, body.get('name')))
            if u.path.startswith('/api/grass/'):
                import grass
                if u.path == '/api/grass/add':
                    return self._json(grass.add(db, body.get('items') or []))
                if u.path == '/api/grass/remove':
                    return self._json(grass.remove(db, [[float(v) for v in c[:3]] for c in body.get('circles') or []]))
                if u.path == '/api/grass/fill':
                    return self._json(grass.fill(db, body.get('cells') or [], int(body.get('thickness') or 5), body.get('ids')))
                if u.path == '/api/grass/clear':
                    return self._json(grass.clear(db, body.get('cells') or []))
                if u.path == '/api/grass/enable':
                    return self._json(groundcover_enable())
            if u.path == '/api/item/save':
                import items_ed
                return self._json(items_ed.save(db, body.get('id'), body.get('data') or {}))
            if u.path == '/api/spells/cost':
                return self._json({'cost': items.spell_cost(db, body.get('effects') or [], bool(body.get('constant')))})
            if u.path == '/api/ai/draft':
                try:
                    return self._json(assistant.draft(body))
                except ai.ToolError as e:
                    return self._json({'error': str(e)}, 400)
            if u.path == '/api/library/makeicon':
                # icons the game's way from a picture (library.py): the page made the PNGs of the right sizes
                import library
                return self._json(library.make_icon(db, body.get('name') or '', body.get('kind') or 'item', body.get('pictures') or [],
                                                    body.get('source') or ''))
            if u.path == '/api/populate/cast':
                # Populate: a proposed cast for a place (populate.py; nothing changes)
                import populate
                return self._json(populate.cast(db, body['cell'], body.get('params') or {}, body.get('keep') or [], body.get('seed')))
            if u.path == '/api/convo/say':
                # the tester: what a character says in a given state of the game (convo.py; nothing saved)
                import convo
                return self._json(convo.say(db, body['id'], body.get('state') or {}, body.get('topic'), body.get('cell')))
            if u.path == '/api/ai/effectlua':
                # the Lua for a step of one of your own magic effects, from a description (nothing saved)
                try:
                    return self._json(assistant.effect_lua(body))
                except ai.ToolError as e:
                    return self._json({'error': str(e)}, 400)
            if u.path == '/api/extend/options':
                # add a room through a wall: the proposed room and its ghost pieces (extend.py; nothing is laid)
                import extend
                return self._json(extend.options(db, body['cell'], body.get('ref'), body.get('at'), body.get('w', 3), body.get('h', 3),
                                                 body.get('shift', 0), body.get('name')))
            if u.path == '/api/extend/sketch':
                # the furniture the furnish would lay in the ghost room, big pieces only (a scratch place, thrown away)
                import extend
                return self._json(extend.sketch(db, body['cell'], body.get('ref'), body.get('at'), body.get('w', 3), body.get('h', 3),
                                                body.get('shift', 0), body.get('name'), body.get('kind'), body.get('level')))
            if u.path == '/api/extend/removable':
                import extend
                return self._json(extend.removable(db, body['cell'], body.get('room')))
            if u.path == '/api/extend/edges':
                # Extend mode: every open face of every building piece of the place (adjacency.py; nothing is laid)
                import extend
                return self._json(extend.edges(db, body['cell']))
            if u.path == '/api/extend/candidates':
                # Extend mode: what the game joins to this face of this piece, with ghosts and patterns
                import extend
                return self._json(extend.candidates(db, body['cell'], body['ref'], body['side']))
            if u.path == '/api/extend/run':
                import extend
                return self._json(extend.run_ghost(db, body['cell'], body['ref'], body['rel'], body.get('n', 3)))
            if u.path == '/api/extend/close' and body.get('preview', True):
                import extend
                return self._json(extend.close(db, body['cell'], body.get('refs') or [], preview=True))
            if u.path == '/api/fixhere/options':
                # what the game stands at the joint pointed at (a piece, or a spot on the floor): read-only
                import fixhere
                return self._json(fixhere.options(db, body['cell'], body.get('ref'), body.get('at')))
            if u.path == '/api/place/check':
                # the health check of a place: the furnishing faults and the gap finder's findings in one
                # list, with markers and fixes (placecheck.py). It changes nothing, so it runs OUTSIDE the
                # editing lock: on a big house it takes a while, and while it ran under the lock every
                # Dress this, Add one thing and furnish waited behind it (the user: "Dress doesn't seem to
                # work anymore", with "Checking this place…" in the panel the whole time)
                import placecheck
                return self._json(placecheck.check(db, body['cell'], gaps=body.get('gaps', True)))
            if u.path == '/api/room/score':
                # how much each room of a place looks like one the game made: a number from 0 to 100 and the
                # terms behind it (roomscore.py). Read-only, so outside the editing lock like the health check;
                # fast (no mesh rays) unless asked otherwise; gaps only with fast off
                import roomscore
                return self._json(roomscore.score_place(db, body['cell'], fast=body.get('fast', True), gaps=body.get('gaps', False)))
            with edit_lock:
                if u.path == '/api/doors/pair':
                    # (two doors picked in two windows lead to each other: web/twowin.js)
                    return self._json(doors.link_pair(db, body['cell_a'], body['ref_a'], body['cell_b'], body['ref_b']))
                if u.path == '/api/ref/relink':
                    r = doors.relink(db, body['cell'], body['ref'], body.get('target'), body.get('at'), bool(body.get('both')))
                    m = mapdata.cellmap(db, body['cell'])
                    m['relink'] = r
                    return self._json(m)
                if u.path == '/api/org/save':
                    return self._json(groups_ed.save(db, body.get('kind'), body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/global/save':
                    return self._json(groups_ed.save_global(db, body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/gmst/save':
                    return self._json(groups_ed.save_gmst(db, body.get('id'), body.get('value')))
                if u.path == '/api/assets/edit':
                    import assets
                    return self._json(assets.edit_texture(db, body.get('path'), body.get('how') or 'everywhere', body.get('i'),
                                                          open_it=body.get('open', True) is not False))
                if u.path == '/api/assets/open':
                    # (open again, in the picture editor: only a copy in the mod's own folder)
                    import assets
                    import library
                    f = body.get('file') or ''
                    base = os.path.normcase(os.path.abspath(library.data_dir(db)))
                    if not (os.path.isfile(f) and os.path.normcase(os.path.abspath(f)).startswith(base + os.sep)):
                        return self._json({'error': 'That file is not one of your mod\'s copies.'}, 400)
                    return self._json({'editor': assets._open(f)})
                if u.path == '/api/assets/giveback':
                    import assets
                    r = assets.give_back(db, body.get('path'))
                    _model_cache.pop((body.get('path') or '').lower().replace('\\', '/'), None)
                    return self._json(r)
                if u.path == '/api/assets/export':
                    # a model out to Blender as a .glb (with blender: true, opened there too)
                    import assets
                    ri = int(body['i'])
                    r = assets.export_glb(db, db.recs[ri][5])
                    if body.get('blender'):
                        r['blender'] = assets.open_in_blender(r['file'])
                    return self._json(r)
                if u.path in ('/api/assets/blender', '/api/assets/showfile'):
                    # (only the Workshop's own exports)
                    import assets
                    f = body.get('file') or ''
                    if not (os.path.isfile(f) and os.path.normcase(os.path.abspath(f)).startswith(os.path.normcase(os.path.abspath(assets.EXPORTS)) + os.sep)):
                        return self._json({'error': 'That is not one of the Workshop\'s exports.'}, 400)
                    if u.path == '/api/assets/blender':
                        return self._json({'blender': assets.open_in_blender(f)})
                    subprocess.Popen(['explorer', '/select,', os.path.normpath(f)])
                    return self._json({'ok': True})
                if u.path == '/api/assets/import':
                    import assets
                    r = assets.import_back(db, body.get('file'), body.get('how') or 'everywhere', body.get('i'), into=body.get('into'))
                    _model_cache.pop(r['path'], None)
                    return self._json(r)
                if u.path in ('/api/anim/retime', '/api/anim/adopt', '/api/anim/personadopt', '/api/anim/bringkf'):
                    import nifanim
                    try:
                        if u.path == '/api/anim/retime':
                            return self._json(nifanim.retime(db, body.get('i'), body.get('group'), body.get('factor', 1), body.get('how') or 'everywhere'))
                        if u.path == '/api/anim/personadopt':
                            return self._json(nifanim.person_adopt(db, body.get('i'), body.get('model') or ''))
                        if u.path == '/api/anim/bringkf':
                            import base64
                            data = base64.b64decode(body.get('data') or '')
                            if len(data) > 64 << 20:
                                return self._json({'error': 'That file is too big to be an animation.'}, 400)
                            return self._json(nifanim.bring_kf(db, body.get('i'), data, body.get('how') or 'everywhere'))
                        return self._json(nifanim.adopt(db, body.get('i'), body.get('from'), body.get('how') or 'everywhere'))
                    except ValueError as e:
                        return self._json({'error': str(e)}, 400)
                if u.path in ('/api/anim/blender', '/api/anim/motion'):
                    # one group's motion out to Blender (open: there too), and back from the file Blender saves
                    import animglb
                    import assets
                    try:
                        if u.path == '/api/anim/blender':
                            r = animglb.export_group(db, body.get('i'), body.get('group'))
                            if body.get('open'):
                                r['blender'] = animglb.open_in_blender(r['file'])
                            return self._json(r)
                        f = body.get('file') or ''
                        if not (os.path.isfile(f) and os.path.normcase(os.path.abspath(f)).startswith(os.path.normcase(os.path.abspath(assets.EXPORTS)) + os.sep)):
                            return self._json({'error': 'That is not one of the Workshop\'s exports.'}, 400)
                        return self._json(animglb.import_motion(db, body.get('i'), f, body.get('how') or 'everywhere'))
                    except ValueError as e:
                        return self._json({'error': str(e)}, 400)
                if u.path == '/api/anim/textkeys':
                    import nifanim
                    try:
                        return self._json(nifanim.save_keys(db, body.get('i'), body.get('keys') or [], body.get('how') or 'everywhere',
                                                            body.get('file'), body.get('group')))
                    except ValueError as e:
                        return self._json({'error': str(e)}, 400)
                if u.path == '/api/assets/fixtex':
                    import assets
                    r = assets.fix_texture(db, body.get('i'), body.get('name') or '', body.get('to') or '', body.get('how') or 'everywhere')
                    _model_cache.pop(r.get('path') or '', None)
                    return self._json(r)
                if u.path == '/api/region/save':
                    import regions
                    return self._json(regions.save(db, body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/region/assign':
                    import regions
                    return self._json(regions.assign(db, body.get('id') or '', body.get('cells') or []))
                if u.path == '/api/lev/save':
                    return self._json(levlists.save(db, body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/myeffects/save':
                    import myeffects
                    return self._json(myeffects.save(db, body.get('effect') or {}, body.get('old_id')))
                if u.path == '/api/myeffects/delete':
                    import myeffects
                    return self._json(myeffects.delete(db, body.get('id') or ''))
                if u.path == '/api/ref/props':
                    import refprops
                    r = refprops.save(db, body['cell'], body['ref'], body.get('data') or {})
                    m = mapdata.cellmap(db, body['cell'])
                    m['props'] = r
                    return self._json(m)
                if u.path == '/api/sounds/save':
                    import sounds_ed
                    return self._json(sounds_ed.save(db, body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/sounds/creature/save':
                    import sounds_ed
                    return self._json(sounds_ed.save_creature_sounds(db, body.get('id') or '', body.get('rows') or []))
                if u.path == '/api/place/settings':
                    places.save(db, body['key'], body.get('settings') or {})
                    return self._json(mapdata.cellmap(db, body['key']))
                if u.path == '/api/release/info':
                    return self._json(release.save_info(db, body))
                if u.path == '/api/release/fix':
                    return self._json(release.fix(db, body.get('action')))
                if u.path == '/api/release/package':
                    editing.flush(db)       # (the zip takes the plugin from disk)
                    return self._json(release.package(db))
                if u.path == '/api/release/clean_test':
                    return self._json(clean_test(body))
                if u.path == '/api/release/open':
                    editing._require_project(db)
                    return self._json(open_folder(release.releases_dir() if body.get('what') == 'releases' else release.extra_dir(db)))
                if u.path == '/api/script/attach':
                    return self._json(mwscript.attach(db, body.get('id'), body.get('target') or '', bool(body.get('detach'))))
                if u.path == '/api/script/check':
                    return self._json(mwscript.check(db, body.get('text') or '', body.get('id') or ''))
                if u.path == '/api/script/save':
                    return self._json(mwscript.save(db, body.get('id'), body.get('text') or '', bool(body.get('create'))))
                if u.path == '/api/npc/save':
                    return self._json(npc.save(db, body['id'], body['data']))
                if u.path == '/api/settle':
                    # what lies loose in a spot falls into place, as if with gravity (settle.py); the moves come
                    # back to be made as one Undo (/api/group/move)
                    import settle
                    return self._json(settle.settle(db, body.get('cell') or '', body.get('at'), float(body.get('radius') or 200),
                                                    body.get('refs') or None, float(body.get('max_drop') or 48), bool(body.get('tip'))))
                if u.path == '/api/land/marks':
                    import landsurvey
                    return self._json(landsurvey.set_marks(db, body.get('add') or [], body.get('remove') or [], bool(body.get('clear'))))
                if u.path == '/api/land/raise':
                    # the marked cells raised into land as one piece (landrange.py)
                    import landrange
                    return self._json(landrange.raise_land(db, body.get('cells') or [], body.get('height', 512), body.get('coast', 6144),
                                                           body.get('rough', 1.0), body.get('paint', True) is not False,
                                                           body.get('region') or '', body.get('seed')))
                if u.path == '/api/land/plan':
                    # the shapes drawn on the land map, kept in the project (landshapes.py)
                    import landshapes
                    return self._json(landshapes.save_plan(db, body.get('plan') or {}))
                if u.path == '/api/land/plan/preview':
                    import landshapes
                    return self._json(landshapes.preview(db, body.get('cells') or [], body.get('plan') or {}))
                if u.path == '/api/land/plan/apply':
                    import landshapes
                    return self._json(landshapes.apply(db, body.get('cells') or [], body.get('plan') or {}))
                if u.path == '/api/land/heightmap/export':
                    # cells as a 16-bit greyscale PNG (heightmap.py); the page saves it
                    import heightmap
                    return self._json(heightmap.export_png(db, int(body['x0']), int(body['y0']), int(body['x1']), int(body['y1'])))
                if u.path == '/api/land/heightmap/info':
                    import heightmap
                    return self._json(heightmap.info(body.get('png') or ''))
                if u.path == '/api/land/heightmap/import':
                    import heightmap
                    return self._json(heightmap.import_png(db, body.get('png') or '', int(body['gx']), int(body['gy']), body.get('across'),
                                                           float(body.get('black', -2048)), float(body.get('white', 4096)),
                                                           float(body.get('blend', 2048)), bool(body.get('allow_settled')),
                                                           bool(body.get('paint'))))
                if u.path == '/api/land/shade':
                    import landshade
                    return self._json(landshade.shade(db, body.get('cells') or [], body.get('mode') or 'seams', body.get('strength', 1.0)))
                if u.path == '/api/land/edit':
                    return self._json(landscape.edit(db, body.get('cells') or [], body.get('keep_objects', True)))
                if u.path == '/api/group/move':
                    return self._json(groups.move(db, body.get('moves') or []))
                if u.path == '/api/group/delete':
                    return self._json(groups.delete(db, body.get('refs') or []))
                if u.path == '/api/group/swap':
                    return self._json(groups.swap(db, body.get('refs') or [], body.get('id')))
                if u.path == '/api/group/restore':
                    return self._json(groups.restore(db, body.get('refs') or []))
                if u.path == '/api/testsetups':
                    return self._json(save_test_setups(body))
                if u.path == '/api/testsetups/give':
                    return self._json(give_setup(body))
                if u.path == '/api/saves/use':
                    return self._json(play_as(body))
                if u.path == '/api/group/place':
                    return self._json(groups.place(db, body.get('cell'), body.get('items') or [], body['x'], body['y'],
                                                   body.get('z'), float(body.get('yaw') or 0), body.get('label')))
                if u.path == '/api/group/copy':
                    return self._json({'items': groups.from_refs(db, body.get('refs') or [])})
                if u.path == '/api/prefabs/save':
                    items_ = body.get('items') or groups.from_refs(db, body.get('refs') or [])
                    return self._json(groups.save_prefab(db, body.get('name'), items_, body.get('source', '')))
                if u.path == '/api/prefabs/delete':
                    return self._json(groups.delete_prefab(body.get('name', '')))
                if u.path == '/api/build/plans/save':
                    import plans
                    return self._json(plans.save_plan(body.get('name'), body.get('plan'), body.get('style'), body.get('options')))
                if u.path == '/api/build/plans/delete':
                    import plans
                    return self._json(plans.delete_plan(body.get('name', '')))
                if u.path == '/api/items/create':
                    return self._json(items.create_item(db, body))
                if u.path == '/api/forge/check':
                    import gearsurvey
                    bw = body.get('between')
                    try:
                        return self._json(gearsurvey.check(db, body.get('kind'), body.get('type'), body.get('mat') or None,
                                                           body.get('stats') or {}, tuple(bw) if bw else None))
                    except ValueError as e:
                        return self._json({'error': str(e)}, 400)
                if u.path.startswith('/api/spellgive/'):
                    # Give spells to people: everyone who fits, in their records or by a script (spellgive.py)
                    import spellgive
                    act = u.path.rsplit('/', 1)[1]
                    if act == 'preview':
                        return self._json(spellgive.preview(db, body.get('spells') or [], body.get('filters') or {}))
                    if act == 'give':
                        return self._json(spellgive.give(db, body.get('spells') or [], body.get('filters') or {},
                                                         body.get('mode') or 'records', body.get('label') or ''))
                    if act == 'remove':
                        return self._json(spellgive.remove_rule(db, int(body.get('n', -1))))
                    if act == 'refresh':
                        return self._json(spellgive.refresh(db))
                if u.path == '/api/spells/create':
                    return self._json(items.create_spell(db, body))
                if u.path == '/api/paths':
                    # (redrawn by Project Tamriel's rules: room pieces by their tiles, anything else from its floors)
                    r = pathgrid.redraw(db, body['cell'])
                    m = mapdata.cellmap(db, body['cell'])
                    m['made'] = r
                    return self._json(m)
                if u.path == '/api/paths/save':
                    r = pathgrid.save(db, body['cell'], body.get('pts') or [], body.get('edges') or [])
                    m = mapdata.cellmap(db, body['cell'])
                    m['saved'] = r
                    return self._json(m)
                if u.path.startswith('/api/library/'):
                    import library
                    act = u.path.rsplit('/', 1)[1]
                    if act == 'inspect':
                        return self._json(library.inspect_batch(body.get('batch', '')))
                    if act == 'import':
                        return self._json({'added': library.import_batch(db, body.get('batch', ''), body.get('name'),
                                                                         body.get('up') or 'y', body.get('size'), body.get('kind') or 'static',
                                                                         body.get('collision') or 'shape', body.get('object'),
                                                                         {'light': body.get('light'), 'door_sound': body.get('door_sound'),
                                                                          'reach': body.get('reach')})})
                    if act == 'record':
                        return self._json(library.make_record(db, body.get('id', ''), body.get('kind'), body.get('name')))
                    if act == 'remove':
                        library.remove(db, body.get('id', ''))
                        return self._json({'ok': True})
                    if act == 'sound':
                        # a Library sound: how loud / how far it carries, and its record for scripts
                        e = library.set_sound(db, body.get('id', ''), body.get('volume'), body.get('reach'))
                        if body.get('record'):
                            e = dict(e, made=library.make_sound(db, e['id']))
                        return self._json(e)
                    if act == 'attach':
                        # a sound playing where a selected object stands
                        r = library.make_sound_source(db, body.get('id', ''), commit=False)   # (one undo step with the placing)
                        p = [float(v) for v in body['p']]
                        rk = editing.place_ref(db, body['cell'], r['id'], [p[0], p[1], p[2], 0, 0, 0], 1.0,
                                               note='Added the sound "%s" here' % ((library.entry(body.get('id', '')) or {}).get('name') or r['id']))
                        return self._json({'id': r['id'], 'ref': rk})
                    if act == 'retexture':
                        return self._json(library.retexture_record(db, int(body['i']), body.get('mapping') or {}, body.get('name')))
                if u.path == '/api/brushes/save':
                    import scatter
                    return self._json(scatter.save_brush(db, body.get('brush') or {}))
                if u.path == '/api/brushes/delete':
                    import scatter
                    scatter.delete_brush(str(body.get('id') or ''))
                    return self._json({'ok': True})
                if u.path == '/api/brushes/import':
                    import scatter
                    added, skipped = scatter.import_brushes(db, body.get('data') or {})
                    return self._json({'added': added, 'skipped': skipped})
                if u.path == '/api/furnish':
                    import learning
                    import background
                    waiting = learning.pending(db)
                    if waiting:
                        # (not learnt yet: the page shows the progress and asks again when it is)
                        return self._json({'waiting': waiting, 'surveys': background.status()})
                    return self._json(furnish.furnish(db, body['cell'], body.get('plan'), walls=body.get('walls', True) is not False,
                                                      walls_only=bool(body.get('walls_only')), replace=bool(body.get('replace')),
                                                      level=body.get('level'), like=body.get('like') or None))
                if u.path == '/api/furnish/room':
                    # one room furnished the game's way (as its own kind, or as the kind asked for): one
                    # undoable change; a second call takes the room's earlier things out first
                    import random as _random
                    room_id = body.get('room')
                    if room_id is None and body.get('at'):
                        room_id = furnish.room_info(db, body['cell'], at=body['at'])['room']
                    if room_id is None:
                        return self._json({'error': 'That spot is in no room Auto-furnish can read.'}, 400)
                    if body.get('dress'):
                        # every dressable piece in the room dressed the game's way, as one undoable change
                        return self._json(furnish.furnish(db, body['cell'], room=int(room_id), dress_room=True, seed=_random.randrange(1 << 30)))
                    return self._json(furnish.furnish(db, body['cell'], room=int(room_id), purpose=body.get('purpose') or None,
                                                      replace=body.get('replace', True) is not False, seed=_random.randrange(1 << 30)))
                if u.path == '/api/furnish/piece':
                    # one placed piece dressed the game's way (a bookshelf's books, a table's dishes, a
                    # counter's wares, a planter's plant, a hearth's pots): one undoable change; a second
                    # call takes the earlier dressing off first and lays a fresh draw
                    import random as _random
                    if body.get('add'):
                        # one more thing on the piece, everything on it kept
                        return self._json(furnish.furnish(db, body['cell'], piece=body['ref'], add=True, replace=False, seed=_random.randrange(1 << 30)))
                    return self._json(furnish.furnish(db, body['cell'], piece=body['ref'], replace=True, seed=_random.randrange(1 << 30),
                                                      books=bool(body.get('books'))))
                if u.path == '/api/taste':
                    # mark one of the game's places as an example (or unmark it): the surveys that
                    # Auto-furnish goes by weigh it several times over, and run again in the background
                    import taste
                    import kits
                    key = (body.get('key') or '').lower()
                    if not key or not mapdata.cell_info(db, key):
                        return self._json({'error': 'No such place.'}, 400)
                    if body.get('on', True) and not kits.game_made(db, key):
                        return self._json({'error': 'Only the game\'s own places (or another mod\'s) can be examples: your mod\'s builds must not teach Auto-furnish its own habits.'}, 400)
                    lst = taste.mark(key, bool(body.get('on', True)))
                    return self._json({'ok': True, 'places': taste.listing(db), 'count': len(lst), 'weight': taste.WEIGHT})
                if u.path == '/api/build/interior':
                    return self._json(builder.build_house(
                        db, body.get('name'), body.get('style'), body.get('rooms') or [], body.get('doors'),
                        body.get('exit'), body.get('entrance'), body.get('lighting') or 'normal',
                        body.get('lights', True), body.get('door'), body.get('stairs'), body.get('floors_as') or 'auto',
                        planner=body.get('plan')))
                if u.path == '/api/build/from_building':
                    import frombuilding
                    return self._json(frombuilding.build(db, body.get('cell') or '', body.get('ref') or '', body.get('name'),
                                                         body.get('door') or None, body.get('style') or None,
                                                         int(body['floors']) if body.get('floors') else None,
                                                         body.get('tiles') or None, body.get('tolerance') or 'usual'))
                if u.path == '/api/build/groundfit':
                    # the ground fitted to a building outdoors, the way the game's meet theirs (groundfit.py)
                    import groundfit
                    return self._json(groundfit.fit(db, body.get('cell') or '', body.get('ref') or ''))
                if u.path == '/api/build/modules/fit':
                    # the game's buildings of a style laid over a volume of tiles (Plan a prefab, prefabplan.js)
                    import housemodules
                    return self._json(housemodules.fit_volume(db, body.get('style') or None, {'tiles': body.get('tiles') or []},
                                                              body.get('front') or 'S', kind=body.get('kind') or 'homes',
                                                              tolerance=body.get('tolerance') or 'usual'))
                if u.path == '/api/build/modules/join':
                    import housemodules
                    return self._json(housemodules.join(db, body.get('cell') or '', body.get('ref') or '', body.get('id') or '',
                                                        body.get('pose') or []))
                if u.path == '/api/build/outside':
                    import outside
                    return self._json(outside.for_rooms(db, body.get('style'), float(body.get('w') or 768), float(body.get('d') or 768)))
                if u.path == '/api/build/plan':
                    return self._json(builder.plan(db, body.get('style'), body.get('rooms') or [], body.get('stairs'), body.get('floors_as') or 'auto',
                                                   body.get('doors')))
                if u.path == '/api/build/stairspots':
                    # where the stairs could stand (the planner shades them while you move the stairs)
                    return self._json(builder.stair_spots(db, body.get('style'), body.get('rooms') or [], body.get('stairs'), body.get('doors')))
                if u.path == '/api/build/stairseed':
                    # a plan to grow from: the style's stairwell with a room at its foot and one at its head
                    return self._json(builder.stair_seed(db, body.get('style')))
                if u.path == '/api/build/fit':
                    # Fit together: the plan shuffled a little so the stairs sit better (nothing is built for keeps)
                    return self._json(builder.fit_together(db, body.get('style'), body.get('rooms') or [], body.get('stairs'),
                                                           body.get('doors'), body.get('floors_as') or 'auto'))
                if u.path == '/api/dlg/topic/new':
                    return self._json({'key': dialogue.create_topic(db, body.get('name'), int(body.get('kind') or 0))})
                if u.path == '/api/ruin/build':
                    # a dungeon (Dwemer ruin, cave, tomb, Daedric ruin) laid out, dressed, guarded and lived in as the
                    # game's own are (dwemer.py), one change
                    import dwemer
                    # (loot, creatures, lived in and water may be slider numbers, 0 among them: not "or" defaults)
                    got = lambda k, d: body.get(k) if body.get(k) not in (None, '') else d
                    return self._json(dwemer.build(db, body.get('name'), body.get('size') or 'medium', body.get('levels') or 'some',
                                                   body.get('twist') or 'branching', got('loot', 'usual'), got('creatures', 'usual'),
                                                   entrance=body.get('entrance'), outside_door=body.get('door') or None,
                                                   seed=body.get('seed') if body.get('seed') not in (None, '') else None,
                                                   occupants=got('occupants', 'auto'), kind=body.get('kind') or 'dwemer',
                                                   water=got('water', 'none'), entry_piece=got('entry', None), final_hall=got('final', None),
                                                   way=body.get('way') or 'down'))
                if u.path == '/api/ruin/preview':
                    # the layout those choices make, for the Dungeon tool's plan (nothing is written)
                    import dwemer
                    return self._json(dwemer.preview(db, body.get('kind') or 'dwemer', body.get('size') or 'medium', body.get('levels') or 'some',
                                                     body.get('twist') or 'branching', body.get('seed'), entry=body.get('entry'), final=body.get('final'),
                                                     way=body.get('way') or 'down'))
                if u.path == '/api/ruin/again':
                    import dwemer
                    return self._json(dwemer.again(db, body['cell'], body.get('seed') if body.get('seed') not in (None, '') else None))
                if u.path == '/api/populate/place':
                    # Populate: the cast made real, as new people placed (populate.py), one change
                    import populate
                    return self._json(populate.place(db, body['cell'], body.get('people') or [], body.get('own', True) is not False))
                if u.path == '/api/convo/build/save':
                    # the conversation builder: a tree of lines and answers, written back as the topic's lines
                    import convbuild
                    return self._json(convbuild.save(db, body['id'], body['topic'], body.get('tree') or {}))
                if u.path == '/api/dlg/line/save':
                    inam = dialogue.save_line(db, body['topic'], body['line'], body.get('where'))
                    return self._json({'inam': inam, 'topic': dialogue.topic(db, body['topic'])})
                if u.path == '/api/dlg/line/delete':
                    dialogue.delete_line(db, body['topic'], body['inam'])
                    return self._json({'topic': dialogue.topic(db, body['topic'])})
                if u.path == '/api/dlg/line/move':
                    dialogue.move_line(db, body['topic'], body['inam'], int(body['step']))
                    return self._json({'topic': dialogue.topic(db, body['topic'])})
                if u.path == '/api/dlg/quest/save':
                    key = dialogue.save_quest(db, body.get('id'), body.get('title'), body.get('stages') or [])
                    return self._json(dialogue.quest(db, key))
                if u.path == '/api/create/interior':
                    key = create.create_interior(db, body['template'], body.get('name'), body.get('contents', 'furnished'),
                                                 body.get('entrance'), body.get('door'))
                    return self._json({'ok': True, 'key': key})
                if u.path == '/api/create/npc':
                    return self._json(create.create_npc(db, body))
                if u.path == '/api/create/book':
                    return self._json(create.create_book(db, body))
                if u.path == '/api/create/container':
                    return self._json(create.create_container(db, body))
                if u.path == '/api/project/merge':
                    # another mod of yours folded into this one, as one change (merge.py)
                    import merge
                    if body.get('preview'):
                        return self._json(merge.preview(db, body.get('name') or ''))
                    r = merge.merge(db, body.get('name') or '', body.get('resolve') or {})
                    r['disabled'] = None
                    if body.get('disable_other') and r.get('in_load_order'):
                        # the merged-in mod comes off the game's load order, or the game shows its places twice;
                        # then everything is read again in the new order, as Load order > Save does
                        info = loadorder.read(db)
                        order = [x['name'] for x in info['enabled'] if x['name'].lower() != r['plugin'].lower()]
                        editing.flush(db)
                        try:
                            loadorder.save(db, order)
                            r['disabled'] = r['plugin']
                            r['game_running'] = link.game_running()
                            db.state = 'loading'
                            db.load_async()
                        except loadorder.LoadOrderError as e:
                            r['disable_error'] = str(e)
                    return self._json(r)
                if u.path == '/api/undo_entry':
                    # with everything built on it, unless asked to take back just this one
                    e = (editing.undo_entry if body.get('only') else editing.undo_branch)(db, int(body['id']))
                    return self._json({'ok': True, 'text': e['text'] if e else ''})
                if u.path == '/api/fold':
                    # the last n changes become one named Undo step (the object window's Save: the record,
                    # the spot and the ownership go through their own routes, then fold into one)
                    e = editing.fold(db, int(body.get('n', 0)), body.get('note') or 'Edited an object')
                    return self._json({'ok': True, 'depth': editing.undo_depth(db), 'redo_depth': editing.redo_depth(db),
                                       'note': e['text'] if e else None})
                if u.path == '/api/undo':
                    undone = editing.undo(db, body.get('to'))
                    return self._json({'ok': True, 'undone': [editing.note_label(db.project, n) for n in undone],
                                       'depth': editing.undo_depth(db), 'redo_depth': editing.redo_depth(db)})
                if u.path == '/api/redo':
                    redone = editing.redo(db)
                    return self._json({'ok': True, 'redone': editing.note_label(db.project, redone),
                                       'depth': editing.undo_depth(db), 'redo_depth': editing.redo_depth(db)})
                if u.path in ('/api/project/new', '/api/project/open', '/api/project/adopt'):
                    _end_together()
                    editing.flush(db)       # (the mod being left is written out first)
                if u.path == '/api/project/saveas':
                    # the Construction Set's Save As: the changes go into a new .esp or .omwaddon, the active file from now on
                    import adopt
                    r = adopt.save_as(db, body.get('name') or '', body.get('ext') or '.esp', bool(body.get('overwrite')))
                    db.state = 'loading'
                    db.load_async()         # (the new file is shown from the project; the old name is gone from the content list)
                    return self._json(r)
                if u.path == '/api/project/adopt':
                    # an existing .esp or .omwaddon becomes the mod itself, saved into from now on (adopt.py)
                    import adopt
                    r = adopt.adopt(db, body.get('path') or '')
                    p = r.pop('project')
                    s = load_settings()
                    s['project'] = os.path.relpath(p.path, APP_DIR)
                    save_settings(s)
                    db.project = p
                    import background
                    background.project_path[0] = p.path
                    db.state = 'loading'
                    db.load_async()         # (the file comes off the load order and is shown from the project instead)
                    r['reload'] = True
                    return self._json(r)
                if u.path == '/api/project/new':
                    p = Project.create(body.get('name', 'MyMod'), body.get('author', ''), body.get('description', ''))
                    s = load_settings()
                    s['project'] = os.path.relpath(p.path, APP_DIR)
                    save_settings(s)
                    db.project = p
                    db.state = 'loading'
                    db.load_async()     # reload so the new plugin is excluded and overlaid
                    return self._json({'ok': True, 'reload': True})
                if u.path == '/api/project/open':
                    path = os.path.join(PROJECTS_DIR, os.path.basename(body['name']) + '.json')
                    s = load_settings()
                    s['project'] = os.path.relpath(path, APP_DIR)
                    save_settings(s)
                    db.project = Project(path)
                    db.state = 'loading'
                    db.load_async()
                    return self._json({'ok': True, 'reload': True})
                if u.path == '/api/project/enable':
                    return self._json(enable_in_cfg())
                if u.path == '/api/mods/show':
                    # Explorer at a mod's plugin file (My mod > Show folder, and each row of Your mods)
                    import modfiles
                    return self._json(modfiles.show(db, body.get('name')))
                if u.path == '/api/mods/delete':
                    # a mod you no longer want: to the Recycle Bin, and out of the load order
                    import modfiles
                    return self._json(modfiles.delete(db, body.get('name') or '', bool(body.get('plugin_too', True))))
                if u.path == '/api/play':
                    editing.flush(db)
                    return self._json(play(body))
                if u.path == '/api/edit':
                    return self._json({'i': editing.edit_record(db, int(body['i']), body['changes'])})
                if u.path == '/api/duplicate':
                    return self._json({'i': editing.duplicate_record(db, int(body['i']), body['id'])})
                if u.path == '/api/contents':
                    # a container's contents, edited in its window over the 3D view (objwin.js)
                    return self._json({'i': editing.set_contents(db, int(body['i']), body.get('items') or [])})
                if u.path == '/api/revert':
                    return self._json({'i': editing.revert_record(db, int(body['i']))})
                if u.path == '/api/ref/move':
                    editing.move_ref(db, body['cell'], body['ref'], [float(v) for v in body['p']], body.get('s'))
                    return self._json(mapdata.cellmap(db, body['cell']))
                if u.path == '/api/ref/delete':
                    editing.delete_ref(db, body['cell'], body['ref'])
                    return self._json(mapdata.cellmap(db, body['cell']))
                if u.path == '/api/ref/place':
                    p = [None if v is None else float(v) for v in body['p']]
                    if body.get('surface') and p[2] is not None:
                        # dropped in the 3D view: rest the object's bottom on the spot that was pointed at
                        b = mapdata.object_bounds(db, db.resolve_id(body['id']))
                        p[2] -= (b[2] if b else 0.0) * float(body.get('s') or 1.0)
                    rk = editing.place_ref(db, body['cell'], body['id'], p, float(body.get('s') or 1.0),
                                           body.get('cut'))
                    m = mapdata.cellmap(db, body['cell'])
                    m['placed'] = rk
                    return self._json(m)
                if u.path == '/api/fixit/apply':
                    import fixit
                    r = fixit.apply(db, body['cell'], body.get('ops') or [], body.get('label'))
                    m = mapdata.cellmap(db, body['cell'])
                    m['changed'] = r['changed']
                    return self._json(m)
                if u.path == '/api/extend/apply':
                    # the plan grows by the room and its doorway; only they are laid; the room is furnished
                    import extend
                    return self._json(extend.apply(db, body['cell'], body.get('ref'), body.get('at'), body.get('w', 3), body.get('h', 3),
                                                   body.get('shift', 0), body.get('name'), body.get('furnish', True) is not False,
                                                   body.get('level'), body.get('purpose')))
                if u.path == '/api/extend/remove':
                    # a room of the plan taken out: its pieces and things go, the wall closes again, one change
                    import extend
                    return self._json(extend.remove(db, body['cell'], body.get('room')))
                if u.path == '/api/extend/lay':
                    # Extend mode: pieces laid as one undo step (each click one step; Esc folds them)
                    import extend
                    return self._json(extend.lay(db, body['cell'], body.get('items') or [], body.get('label')))
                if u.path == '/api/extend/fold':
                    import extend
                    return self._json(extend.fold(db, body.get('n', 0), body.get('note') or 'Extended the place'))
                if u.path == '/api/extend/close':
                    import extend
                    return self._json(extend.close(db, body['cell'], body.get('refs') or [], preview=False))
                if u.path == '/api/fixhere/apply':
                    # Fix here: the game's answer at one joint laid as one change, or at every joint of the
                    # place in the same situation (fixhere.py)
                    import fixhere
                    import fixit
                    if body.get('everywhere'):
                        r = fixhere.everywhere(db, body['cell'], body['key'], body['ans'], body.get('label'))
                    else:
                        r = fixit.apply(db, body['cell'], body.get('ops') or [], body.get('label'))
                    m = mapdata.cellmap(db, body['cell'])
                    m['changed'] = r['changed']
                    m['spots'] = r.get('spots')
                    return self._json(m)
                if u.path == '/api/fixit/doorframes':
                    # bare doorways in a place built before the Workshop knew the style's door frame: the
                    # frame in each, then the columns that were only covering the wall ends out again
                    import fixit
                    ops_ = fixit.frameless_doorways(db, body['cell'])
                    n_, k_ = len(ops_), 0
                    if ops_:
                        fixit.apply(db, body['cell'], ops_, commit=False)
                        db.sync_project()
                        c_, _refs = editing._cell(db, body['cell'])
                        k_ = builder._trim_columns(db, body['cell'], c_, None, slow=40)
                        editing.commit(db, 'Put door frames in %d doorway%s in %s%s' % (
                            n_, '' if n_ == 1 else 's', editing.cell_label(db, body['cell']),
                            ' and took out %d column%s' % (k_, '' if k_ == 1 else 's') if k_ else ''))
                    m = mapdata.cellmap(db, body['cell'])
                    m['frames'], m['removed'] = n_, k_
                    return self._json(m)
                if u.path == '/api/fixit/spare':
                    # posts and columns your mod put in that close nothing: out, as one change
                    editing._require_project(db)
                    c_, _refs = editing._cell(db, body['cell'])
                    n_ = builder._trim_columns(db, body['cell'], c_, None, slow=40)
                    if n_:
                        editing.commit(db, 'Took out %d spare column%s in %s' % (n_, '' if n_ == 1 else 's', editing.cell_label(db, body['cell'])))
                    m = mapdata.cellmap(db, body['cell'])
                    m['removed'] = n_
                    return self._json(m)
                if u.path == '/api/fixit/all':
                    import fixit
                    r = fixit.fix_all(db, body['cell'])
                    m = mapdata.cellmap(db, body['cell'])
                    m['changed'], m['left'] = r['changed'], r['left']
                    return self._json(m)
                if u.path == '/api/ref/swap':
                    editing.swap_ref(db, body['cell'], body['ref'], body['id'])
                    return self._json(mapdata.cellmap(db, body['cell']))
                if u.path == '/api/ref/secret':
                    made = editing.secret_ref(db, body['cell'], body['ref'], body.get('kind') or 'door')
                    return self._json(dict(mapdata.cellmap(db, body['cell']), made=made))
                if u.path == '/api/ref/restore':
                    editing.restore_ref(db, body['cell'], body['ref'])
                    return self._json(mapdata.cellmap(db, body['cell']))
                if u.path.startswith('/api/secret/'):
                    # secret entrances: a door to somewhere, an ordinary object again, a rotating or sliding panel
                    import mechanism
                    return self._json(mechanism.api(db, u.path, body))
            self._json({'error': 'not found'}, 404)
        except editing.EditError as e:
            self._json({'error': str(e)}, 400)
        except Exception as e:
            if db.state != 'ready' or 'mmap closed' in str(e):
                # (a request still running when a reload began reads files the reload closed: the crawl test's
                # "ValueError: mmap closed or invalid" from Grow grass during Undo my changes. Say "still loading")
                return self._json({'error': 'Still loading, try again in a moment.'}, 503)
            import traceback
            traceback.print_exc()
            self._json({'error': '%s: %s' % (type(e).__name__, e)}, 500)


_model_cache = {}


def model_for(q):
    """3D model of a record (by index i or id) for the preview, with resolved texture paths."""
    from esm import iter_subrecords, zstr
    from nif import mesh_from_nif
    if q.get('model') and not q.get('i') and not q.get('id'):
        # a model file itself (one in the Library, before anything uses it)
        model = q['model']
        if '..' in model:
            return {'error': 'Unknown model'}
        path = 'meshes/' + model.lower().replace('\\', '/')
        raw = db.meshes.read(path)
        shapes = mesh_from_nif(raw) if raw else None
        for s in shapes or []:
            s['tex'] = db.meshes.texture_path(s['tex'])
        return {'model': model, 'shapes': shapes} if shapes else {'error': 'This model could not be read.', 'model': model}
    ri = int(q['i']) if q.get('i') else db.resolve_id(q.get('id', ''))
    if ri is None:
        return {'error': 'Unknown object'}
    r = db.recs[ri]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    if r[0] == 'NPC_':
        # a person: their race's body, head and hair, with what they wear
        key = 'npc|' + r[1].lower() + '|%d' % ri
        if key not in _model_cache:
            import npcbody
            try:
                _model_cache[key] = npcbody.npc_body(db, ri)
            except Exception:
                _model_cache[key] = None
        if not _model_cache[key]:
            return {'error': 'Could not put this character\'s body together.'}
        return {'model': 'body', 'shapes': _model_cache[key]}
    model = next((zstr(d) for t, d in iter_subrecords(data) if t == 'MODL'), '')
    if not model:
        return {'error': 'No 3D model to preview for this kind of record.'}
    path = 'meshes/' + model.lower().replace('\\', '/')
    if path not in _model_cache:
        raw = db.meshes.read(path)
        shapes = mesh_from_nif(raw) if raw else None
        if shapes:
            for s in shapes:
                s['tex'] = db.meshes.texture_path(s['tex'])
        _model_cache[path] = shapes
        if len(_model_cache) > 3000:
            _model_cache.pop(next(iter(_model_cache)))
    shapes = _model_cache[path]
    if not shapes:
        return {'error': 'This model could not be read.', 'model': model}
    return {'model': model, 'shapes': shapes}


def changes_list():
    out = []
    p = db.project
    for k, ri in db.overlay.items():
        tag, key = k
        r = db.recs[ri]
        if tag == 'CELL':
            c = p.cells.get(key, {'refs': {}})
            mine = p.plugin.lower()
            n_new = sum(1 for rr in c['refs'].values() if rr['origin'] == mine)
            n_del = sum(1 for rr in c['refs'].values() if rr.get('deleted'))
            desc = '%d placed, %d moved, %d removed' % (n_new, len(c['refs']) - n_new - n_del, n_del)
            created = False
        else:
            rec = p.records.get(tag + '|' + key, {})
            created = rec.get('created', False)
            desc = 'new' if created else 'changed'
        out.append({'i': ri, 'type': tag, 'id': r[1], 'name': r[2], 'desc': desc, 'created': created})
    out.sort(key=lambda x: (x['type'], x['id'].lower()))
    return out


def free_port(preferred=8763):
    # (WORKSHOP_PORT: a different one, e.g. for a test copy running beside the real Workshop; 0 = any)
    if os.environ.get('WORKSHOP_PORT', '').isdigit():
        preferred = int(os.environ['WORKSHOP_PORT'])
    for port in (preferred, 0):
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', port))
            p = s.getsockname()[1]
            s.close()
            return p
        except OSError:
            s.close()
    return 0


RUNNING_FILE = os.path.join(APP_DIR, 'workshop_running.json')
SERVER = None

# ---- requests that take long: what the Workshop was doing, written down (2026-10-23: the user's Workshop
# stopped answering for two minutes, the clicks made meanwhile all ran at once when it caught up, and the log
# said nothing). Every request is timed; one still running after STALL_S seconds gets every thread's stack
# written to stalls.log beside the Workshop, once, and the pages ask /api/busy what is holding things up.
STALL_S = 20
INFLIGHT = {}                       # thread id -> (what, when it started)
STALLS_FILE = os.path.join(APP_DIR, 'stalls.log')


def _timed(fn):
    def run(self):
        k = threading.get_ident()
        INFLIGHT[k] = ('%s %s' % (self.command, self.path.split('?')[0]), time.time())
        try:
            return fn(self)
        finally:
            INFLIGHT.pop(k, None)
    return run


Handler.do_GET = _timed(Handler.do_GET)
Handler.do_POST = _timed(Handler.do_POST)


def busy():
    """What the Workshop is in the middle of: [{what, seconds}] of requests running over 2 s, longest first."""
    now = time.time()
    return sorted(({'what': w, 'seconds': round(now - t)} for w, t in list(INFLIGHT.values())
                   if now - t > 2 and not w.endswith('/api/busy')), key=lambda x: -x['seconds'])


def _stall_watch():
    import faulthandler
    told = set()
    while True:
        time.sleep(5)
        now = time.time()
        for k, (what, t0) in list(INFLIGHT.items()):
            if now - t0 < STALL_S or (k, t0) in told:
                continue
            told.add((k, t0))
            try:
                if os.path.isfile(STALLS_FILE) and os.path.getsize(STALLS_FILE) > 2_000_000:
                    os.replace(STALLS_FILE, STALLS_FILE + '.old')
                with open(STALLS_FILE, 'a', encoding='utf-8') as f:
                    f.write('\n==== %s: %s still running after %d s (%d requests in flight: %s)\n' % (
                        time.strftime('%Y-%m-%d %H:%M:%S'), what, now - t0, len(INFLIGHT),
                        '; '.join('%s %ds' % (w, now - s) for w, s in list(INFLIGHT.values()))))
                    f.flush()
                    faulthandler.dump_traceback(file=f, all_threads=True)
                print('A request is taking long (%s, %d s): what the Workshop was doing is in stalls.log' % (what, now - t0))
            except Exception as e:
                print('stall watch:', e)
        told = {x for x in told if x[0] in INFLIGHT}


def _forget_running():
    try:
        with open(RUNNING_FILE, encoding='utf-8') as f:
            if json.load(f).get('pid') != os.getpid():
                return
        os.remove(RUNNING_FILE)
    except (OSError, ValueError):
        pass


def quit_soon():
    """Stop the server cleanly (the launcher's Quit): wait for any edit in progress to finish."""
    def stop():
        with edit_lock:
            _forget_running()
            SERVER.shutdown()
    threading.Thread(target=stop, daemon=True).start()


def main():
    global SERVER
    port = free_port()
    server = SERVER = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=_stall_watch, name='stall-watch', daemon=True).start()
    url = 'http://127.0.0.1:%d/' % port
    # so the launcher can find a Workshop that is already running instead of starting another
    try:
        with open(RUNNING_FILE, 'w', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'port': port, 'url': url}, f)
        import atexit
        atexit.register(_forget_running)
        atexit.register(lambda: editing.flush(db))      # (nothing left unwritten when the Workshop closes)
    except OSError:
        pass
    print('=' * 60)
    print('  Morrowind Workshop is running at %s' % url)
    if sys.stdout and sys.stdout.isatty():       # (not when started by the launcher, which has no window)
        print('  Keep this window open while you use it.')
        print('  Close this window to quit.')
    print('=' * 60)
    open_saved_project()
    db.load_async()
    try:
        import together
        together.autostart(db, edit_lock, open_project_file)     # (back to building together, if that's where it was)
    except Exception as e:
        print('building together:', e)
    if '--no-browser' not in sys.argv and not os.environ.get('WORKSHOP_NO_BROWSER'):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
