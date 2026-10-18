"""Help menu things: the Workshop's version, what it's built from (third-party notices), a
problem report to send when something goes wrong, and the Settings page."""
import importlib.metadata as md
import os
import platform
import re
import sys
import time

from project import APP_DIR, PROJECTS_DIR, load_settings, save_settings

HERE = os.path.dirname(os.path.abspath(__file__))
LICENSES = os.path.join(HERE, 'web', 'vendor', 'licenses')


def version():
    try:
        with open(os.path.join(HERE, 'version.txt'), encoding='ascii') as f:
            return f.read().strip()
    except OSError:
        return 'development copy'


def openmw_version(db):
    """From the newest openmw.log (the Workshop never starts the game just to ask)."""
    cfg = db.config or {}
    log = os.environ.get('WORKSHOP_GAME_LOG') or os.path.join(cfg.get('userdir') or '', 'openmw.log')
    try:
        with open(log, encoding='utf-8', errors='replace') as f:
            for line in f.readlines()[:40]:
                m = re.search(r'OpenMW version ([^\s]+)', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    inst = cfg.get('install') or ''
    m = re.search(r'(\d+\.\d+(\.\d+)?)', os.path.basename(inst))
    return (m.group(1) + ' (from its folder name)') if m else 'unknown'


def _license_of(dist):
    meta = dist.metadata
    lic = meta.get('License-Expression') or ''
    if not lic:
        lic = (meta.get('License') or '').strip().splitlines()[0] if meta.get('License') else ''
    if not lic or len(lic) > 60:
        cls = [c.split('::')[-1].strip() for c in meta.get_all('Classifier') or [] if c.startswith('License ::')]
        lic = ', '.join(cls) or lic[:60] or 'see its licence file'
    return lic


def components():
    """Everything the Workshop ships that others made, with its licence."""
    out = [{'name': 'Python', 'version': platform.python_version(), 'license': 'PSF License',
            'by': 'Python Software Foundation', 'url': 'https://www.python.org'},
           {'name': 'three.js', 'version': 'r128', 'license': 'MIT', 'by': 'three.js authors',
            'url': 'https://threejs.org', 'text': 'three.js-LICENSE.txt'},
           {'name': 'Cinzel (font)', 'version': '', 'license': 'SIL Open Font License 1.1',
            'by': 'The Cinzel Project Authors', 'url': 'https://github.com/NDISCOVER/Cinzel', 'text': 'Cinzel-OFL.txt'},
           {'name': 'Inter (font)', 'version': '', 'license': 'SIL Open Font License 1.1',
            'by': 'The Inter Project Authors', 'url': 'https://github.com/rsms/inter', 'text': 'Inter-OFL.txt'}]
    seen, todo = set(), ['anthropic', 'zstandard']
    while todo:
        n = todo.pop()
        key = re.sub(r'[-_.]+', '-', n).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            d = md.distribution(n)
        except md.PackageNotFoundError:
            continue
        out.append({'name': d.metadata['Name'], 'version': d.version, 'license': _license_of(d),
                    'by': d.metadata.get('Author') or (d.metadata.get('Author-email') or '').split('<')[0].strip(),
                    'url': d.metadata.get('Home-page') or ''})
        for r in d.requires or []:
            if 'extra ==' not in r:
                todo.append(re.split(r'[\s;<>=!~\[(]', r.strip())[0])
    return out


def about(db):
    comps = components()
    for c in comps:
        if c.get('text'):
            try:
                with open(os.path.join(LICENSES, c['text']), encoding='utf-8') as f:
                    c['text'] = f.read()
            except OSError:
                c['text'] = ''
    return {'version': version(), 'python': platform.python_version(), 'openmw': openmw_version(db),
            'components': comps}


def notices_text():
    """THIRD_PARTY_NOTICES.txt (written into the installer by the build)."""
    lines = ['Morrowind Workshop %s: third-party software' % version(), '=' * 60, '',
             'The Workshop includes the following, each under its own licence.', '']
    for c in components():
        lines.append('%s %s' % (c['name'], c['version'])
                     + ('  by %s' % c['by'] if c.get('by') else ''))
        lines.append('    Licence: %s%s' % (c['license'], ('    ' + c['url']) if c.get('url') else ''))
        if c.get('text'):
            try:
                with open(os.path.join(LICENSES, c['text']), encoding='utf-8') as f:
                    lines += ['', '    ' + '\n    '.join(f.read().strip().splitlines()), '']
            except OSError:
                pass
        lines.append('')
    lines.append('Python\'s own licence is in python\\LICENSE_PYTHON.txt; each Python package\'s licence is in its '
                 '"dist-info" folder under python\\Lib\\site-packages.')
    lines.append('Morrowind Workshop is not made by or affiliated with Bethesda Softworks or the OpenMW project.')
    return '\n'.join(lines) + '\n'


# ------------------------------------------------------------------ problem report
def _anon(text):
    """Leave the Windows user name out of paths."""
    home = os.path.expanduser('~')
    user = os.environ.get('USERNAME') or os.path.basename(home)
    try:                                       # (also Windows' short "8.3" form of it, like C:\Users\JOHNSM~1)
        import ctypes
        buf = ctypes.create_unicode_buffer(520)
        if ctypes.windll.kernel32.GetShortPathNameW(home, buf, 520):
            text = re.sub(re.escape(buf.value), '%USERPROFILE%', text, flags=re.I)
    except Exception:
        pass
    text = re.sub(re.escape(home), '%USERPROFILE%', text, flags=re.I)
    if user and len(user) > 2:
        text = re.sub(re.escape(user), '<user>', text, flags=re.I)
    return re.sub(r'sk-ant-[A-Za-z0-9_\-]+', 'sk-ant-<hidden>', text)       # (never an API key)


def _tail(path, n):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return ''.join(f.readlines()[-n:])
    except OSError:
        return '(not found)\n'


def report(db, link, what=''):
    cfg = db.config or {}
    p = db.project
    lines = ['Morrowind Workshop problem report', '=' * 40,
             'When: %s' % time.strftime('%Y-%m-%d %H:%M'),
             'Workshop: %s' % version(),
             'Windows: %s' % platform.platform(),
             'OpenMW: %s, in %s' % (openmw_version(db), cfg.get('install') or 'NOT FOUND'),
             'openmw.cfg: %s (%s)' % (cfg.get('user_cfg'), 'found' if cfg.get('user_cfg_exists') else 'MISSING'),
             'Load order: %d plugins, %d data folders, %d archives' % (len(getattr(db, 'cfg_content_all', []) or []),
                                                                     len(cfg.get('data', [])), len(cfg.get('archives', []))),
             'Game data: %s, %s records%s' % (db.state, getattr(db, 'count', None) or (db.summary() or {}).get('records'),
                                             (', error: ' + db.error) if getattr(db, 'error', None) else ''),
             'Mod open: %s' % ((p.name + ' (' + p.plugin + ')') if p else 'none'),
             'Live link: %s' % ('connected' if link.connected() else 'not linked' if link.unlinked_game() else 'off'),
             '', 'What happened (from the person reporting):', (what or '(not filled in)').strip(), '']
    log = os.path.join(APP_DIR, 'workshop.log')
    lines += ['--- Workshop log (last 150 lines) ---', _tail(log, 150) if os.path.isfile(log) else
              '(no log file: started from a terminal)\n']
    game_log = os.environ.get('WORKSHOP_GAME_LOG') or os.path.join(cfg.get('userdir') or '', 'openmw.log')
    lines += ['--- OpenMW log (last 60 lines) ---', _tail(game_log, 60)]
    text = _anon('\n'.join(lines))
    d = os.path.join(APP_DIR, 'reports')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'problem report %s.txt' % time.strftime('%Y-%m-%d %H-%M-%S'))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return {'text': text, 'path': path, 'folder': d}


# ------------------------------------------------------------------ settings page
def get_settings(db):
    import backups
    s = load_settings()
    key = s.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY') or ''
    keep, minutes = backups.settings()
    cfg = db.config or {}
    return {'openmw_install': cfg.get('install'), 'openmw_chosen': s.get('openmw_install'),
            'openmw_cfg': cfg.get('user_cfg'), 'openmw_userdir': cfg.get('userdir'),
            'ai_configured': bool(key), 'ai_key_end': key[-4:] if key else '', 'ai_from_env': bool(
                os.environ.get('ANTHROPIC_API_KEY') and not s.get('anthropic_api_key')),
            'ai_ack': bool(s.get('ai_ack')),
            'backup_keep': keep, 'backup_minutes': minutes, 'backups_folder': backups.BACKUP_DIR,
            'guide_on_start': s.get('guide_on_start', False), 'guide_seen': bool(s.get('guide_seen')),
            'projects_folder': PROJECTS_DIR, 'app_folder': APP_DIR, 'version': version()}


def set_settings(body):
    s = load_settings()
    if 'backup_keep' in body:
        s['backup_keep'] = max(1, min(500, int(body['backup_keep'])))
    if 'backup_minutes' in body:
        s['backup_minutes'] = max(1, min(240, int(body['backup_minutes'])))
    for k in ('guide_on_start', 'guide_seen', 'ai_ack'):
        if k in body:
            s[k] = bool(body[k])
    if body.get('openmw_reset'):
        s.pop('openmw_install', None)
    save_settings(s)
    return {'ok': True}
