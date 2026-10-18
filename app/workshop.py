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
edit_lock = threading.Lock()


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
    subprocess.Popen([exe] + extra + rest, cwd=install, env=env,
                     creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    return extra


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
    script = os.path.join(APP_DIR, 'play_commands.txt')
    with open(script, 'w', encoding='cp1252', errors='replace') as f:
        f.write('\n'.join(cmds) + '\n')
    start = info['name'] if info['interior'] else (info['name'] or 'Seyda Neen')
    args = [exe, '--skip-menu', '--start', start, '--script-run', script] + _game_content_args()
    _spawn(args, install, body.get('launch'))
    return {'ok': True, 'start': start, 'commands': cmds}


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


def open_project_file(path):
    """Open a mod file as the mod being worked on (and reload), as choosing it from the list does."""
    s = load_settings()
    s['project'] = os.path.relpath(path, APP_DIR)
    save_settings(s)
    db.project = Project(path)
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
                        '.woff2': 'font/woff2', '.ico': 'image/x-icon'}.get(os.path.splitext(fp)[1])
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
                self._json(s)
            elif u.path == '/api/launch':
                self._json(launch_settings())
            elif u.path == '/api/openmw':
                self._json(openmw_info())
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
                                     min(int(q.get('limit', 200)), 1000)))
            elif u.path == '/api/record':
                self._json(db.record(int(q['i'])))
            elif u.path == '/api/health':
                self._json({'issues': db.issues, 'sources': db.asset_sources, 'config': db.config,
                            'plugins': [{k: v for k, v in p.items() if k != 'counts'} for p in db.plugins]})
            elif u.path == '/api/cellmap':
                key = q['key'] if 'key' in q else db.recs[int(q['i'])][7]
                self._json(mapdata.cellmap(db, key))
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
            elif u.path == '/api/lev':
                self._json(levlists.read(db, q.get('id', '')))
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
                self._json([t for t in create.interior_templates(db) if not style or t['style'] == style][:400])
            elif u.path == '/api/create/doors':
                self._json(create.outside_doors(db, q.get('template'), q.get('style')))
            elif u.path == '/api/create/suggest_id':
                self._json({'id': create.suggest_id(db, create._prefix(db) if db.project else 'mod', q.get('name', ''))})
            elif u.path == '/api/link':
                self._json(link.status())
            elif u.path == '/api/loadorder':
                self._json(loadorder.read(db))
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
            elif u.path == '/api/dlg/index':
                kind = q.get('kind')
                self._json(dialogue.index(db, q.get('q', ''), int(kind) if kind not in (None, '') else None,
                                          q.get('mine') == '1', min(int(q.get('limit', 400)), 20000)))
            elif u.path == '/api/dlg/topic':
                self._json(dialogue.topic(db, q['key']))
            elif u.path == '/api/dlg/character':
                self._json(dialogue.character(db, q['id']))
            elif u.path == '/api/dlg/quest':
                out = dialogue.quest(db, q['key'])
                out['used'] = dialogue.quests_using(db, q['key'])
                self._json(out)
            elif u.path == '/api/furnish/rooms':
                info = furnish.rooms(db, q['key'])
                self._json({'rooms': [{k: v for k, v in r.items() if not k.startswith('_')} for r in info['rooms']],
                            'purposes': list(furnish.RECIPES)})
            elif u.path == '/api/prefabs':
                self._json(groups.prefabs())
            elif u.path == '/api/items/options':
                self._json(items.options(db))
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
                import fixit
                self._json(fixit.scan(db, q.get('cell', '')))
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
                self._json(builder.styles(db))
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
            elif u.path == '/api/project':
                p = db.project
                parent, sizes = {}, {}
                if p:
                    parent, _kids, _f = editing.activity(db)
                    sizes = editing.branch_sizes(db)
                log = [{'id': e.get('id'), 't': e.get('t'), 'text': e.get('text'), 'undone': e.get('undone', False),
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
            import traceback
            traceback.print_exc()
            self._json({'error': '%s: %s' % (type(e).__name__, e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get('Content-Length') or 0)
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
            if u.path == '/api/openmw/start':
                return self._json(start_openmw(body.get('mode', 'menu'), body.get('launch')))
            if u.path == '/api/launch':
                return self._json(save_launch(body))
            if u.path == '/api/openmw/pick':
                return self._json(pick_openmw())
            # help menu and settings (these work while the game data loads, too)
            if u.path == '/api/settings':
                r = helpinfo.set_settings(body)
                if body.get('openmw_reset') and db.state != 'loading':
                    db.state = 'loading'
                    db.load_async()
                return self._json(r)
            if u.path == '/api/report':
                return self._json(helpinfo.report(db, link, body.get('what', '')))
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
                db.state = 'loading'                     # read everything again in the new order
                db.load_async()
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
            with edit_lock:
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
                if u.path == '/api/region/save':
                    import regions
                    return self._json(regions.save(db, body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/region/assign':
                    import regions
                    return self._json(regions.assign(db, body.get('id') or '', body.get('cells') or []))
                if u.path == '/api/lev/save':
                    return self._json(levlists.save(db, body.get('id'), body.get('data') or {}, bool(body.get('create'))))
                if u.path == '/api/place/settings':
                    places.save(db, body['key'], body.get('settings') or {})
                    return self._json(mapdata.cellmap(db, body['key']))
                if u.path == '/api/release/info':
                    return self._json(release.save_info(db, body))
                if u.path == '/api/release/fix':
                    return self._json(release.fix(db, body.get('action')))
                if u.path == '/api/release/package':
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
                if u.path == '/api/land/edit':
                    return self._json(landscape.edit(db, body.get('cells') or [], body.get('keep_objects', True)))
                if u.path == '/api/group/move':
                    return self._json(groups.move(db, body.get('moves') or []))
                if u.path == '/api/group/delete':
                    return self._json(groups.delete(db, body.get('refs') or []))
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
                if u.path == '/api/items/create':
                    return self._json(items.create_item(db, body))
                if u.path == '/api/spells/create':
                    return self._json(items.create_spell(db, body))
                if u.path == '/api/paths':
                    r = pathgrid.generate(db, body['cell'])
                    m = mapdata.cellmap(db, body['cell'])
                    m['made'] = r
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
                    return self._json(furnish.furnish(db, body['cell'], body.get('plan'), walls=body.get('walls', True) is not False,
                                                      walls_only=bool(body.get('walls_only'))))
                if u.path == '/api/build/interior':
                    return self._json(builder.build_house(
                        db, body.get('name'), body.get('style'), body.get('rooms') or [], body.get('doors'),
                        body.get('exit'), body.get('entrance'), body.get('lighting') or 'normal',
                        body.get('lights', True), body.get('door'), body.get('stairs'), body.get('floors_as') or 'auto'))
                if u.path == '/api/build/outside':
                    import outside
                    return self._json(outside.for_rooms(db, body.get('style'), float(body.get('w') or 768), float(body.get('d') or 768)))
                if u.path == '/api/build/plan':
                    return self._json(builder.plan(db, body.get('style'), body.get('rooms') or [], body.get('stairs'), body.get('floors_as') or 'auto'))
                if u.path == '/api/dlg/topic/new':
                    return self._json({'key': dialogue.create_topic(db, body.get('name'), int(body.get('kind') or 0))})
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
                if u.path == '/api/undo_entry':
                    # with everything built on it, unless asked to take back just this one
                    e = (editing.undo_entry if body.get('only') else editing.undo_branch)(db, int(body['id']))
                    return self._json({'ok': True, 'text': e['text'] if e else ''})
                if u.path == '/api/undo':
                    undone = editing.undo(db, body.get('to'))
                    return self._json({'ok': True, 'undone': undone, 'depth': editing.undo_depth(db)})
                if u.path in ('/api/project/new', '/api/project/open'):
                    _end_together()
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
                if u.path == '/api/play':
                    return self._json(play(body))
                if u.path == '/api/edit':
                    return self._json({'i': editing.edit_record(db, int(body['i']), body['changes'])})
                if u.path == '/api/duplicate':
                    return self._json({'i': editing.duplicate_record(db, int(body['i']), body['id'])})
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
                if u.path == '/api/fixit/all':
                    import fixit
                    r = fixit.fix_all(db, body['cell'])
                    m = mapdata.cellmap(db, body['cell'])
                    m['changed'], m['left'] = r['changed'], r['left']
                    return self._json(m)
                if u.path == '/api/ref/swap':
                    editing.swap_ref(db, body['cell'], body['ref'], body['id'])
                    return self._json(mapdata.cellmap(db, body['cell']))
                if u.path == '/api/ref/restore':
                    editing.restore_ref(db, body['cell'], body['ref'])
                    return self._json(mapdata.cellmap(db, body['cell']))
            self._json({'error': 'not found'}, 404)
        except editing.EditError as e:
            self._json({'error': str(e)}, 400)
        except Exception as e:
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
    url = 'http://127.0.0.1:%d/' % port
    # so the launcher can find a Workshop that is already running instead of starting another
    try:
        with open(RUNNING_FILE, 'w', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'port': port, 'url': url}, f)
        import atexit
        atexit.register(_forget_running)
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
