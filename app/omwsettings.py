"""OpenMW's own settings (settings.cfg in your OpenMW folder), read and changed from the Workshop.

Every setting the game has, with its default and the help text beside it, comes from the copy OpenMW
installs with itself (defaults.bin: settings-default.cfg in base64; older installs have the plain file).
Your settings.cfg holds only what you changed from those defaults, as "key = value" lines under
"[Section]" headers. A change rewrites just that line (or adds it under its section). A setting put back
to its default is taken out of the file, the way OpenMW writes it. A copy of the file is kept before each
change. OpenMW writes the file again when it quits, so the game is best closed while settings change."""
import base64
import os
import re
import shutil
import time

# the ones most people look for first, in this order (any the installed OpenMW lacks are left out)
POPULAR = [
    ('Video', 'window mode'), ('Video', 'resolution x'), ('Video', 'resolution y'), ('Video', 'vsync mode'),
    ('Video', 'framerate limit'), ('Video', 'antialiasing'), ('General', 'anisotropy'),
    ('Camera', 'field of view'), ('Camera', 'viewing distance'), ('Terrain', 'distant terrain'),
    ('Shaders', 'lighting method'), ('Shaders', 'force shaders'), ('Shaders', 'auto use object normal maps'),
    ('Shaders', 'auto use terrain normal maps'), ('Shaders', 'soft particles'),
    ('Shadows', 'enable shadows'), ('Shadows', 'actor shadows'), ('Shadows', 'object shadows'),
    ('Shadows', 'terrain shadows'), ('Shadows', 'indoor shadows'),
    ('Water', 'shader'), ('Water', 'refraction'), ('Post Processing', 'enabled'),
    ('Groundcover', 'enabled'), ('Groundcover', 'density'),
    ('GUI', 'scaling factor'), ('GUI', 'subtitles'),
    ('Game', 'show owned'), ('Game', 'show effect duration'), ('Game', 'show enchant chance'), ('Game', 'best attack'),
    ('Game', 'graphic herbalism'), ('Game', 'weapon sheathing'), ('Game', 'shield sheathing'),
    ('Game', 'use additional anim sources'), ('Game', 'smooth movement'), ('Game', 'turn to movement direction'),
    ('Game', 'day night switches'), ('Sound', 'master volume'), ('Sound', 'music volume'),
]


# settings whose values are words, by their default: the words OpenMW takes
WORDS = {'shaders compatibility': ['legacy', 'shaders compatibility', 'shaders']}


class SettingsError(ValueError):
    pass


def path_of(userdir):
    return os.path.join(userdir or '', 'settings.cfg')


def _default_text(install):
    import osplat
    # (beside the game on Windows; /etc/openmw on a Linux system install: the game's own config folders)
    for folder in list(reversed(osplat.global_cfg_dirs(install))) or [install or '']:
        for name in ('defaults.bin', 'settings-default.cfg'):
            p = os.path.join(folder, name)
            try:
                raw = open(p, 'rb').read()
            except OSError:
                continue
            if name.endswith('.bin'):
                try:
                    return base64.b64decode(raw).decode('utf-8', 'replace')
                except ValueError:
                    continue
            return raw.decode('utf-8', 'replace')
    return ''


def _kind(default, help_):
    """bool, int, float, choice ([(value, label)]) or text, from the default and the help text."""
    choices = []
    for line in help_.splitlines():
        # ("0 = Off" one to a line, or "0 = Fullscreen, 1 = Windowed Fullscreen, 2 = Windowed" on one)
        choices += re.findall(r'(?:^|,)\s*(-?\d+)\s*=\s*([^,]+?)\s*(?=,\s*-?\d+\s*=|$)', line.strip())
    if default in ('true', 'false'):
        return 'bool', None
    if default in WORDS:
        return 'words', [(w, w) for w in WORDS[default]]
    if choices and re.fullmatch(r'-?\d+', default) and any(c[0] == default for c in choices):
        return 'choice', [(c[0], c[1].rstrip('.')) for c in choices]
    if re.fullmatch(r'-?\d+', default):
        return 'int', None
    if re.fullmatch(r'-?\d+\.\d*(e-?\d+)?', default):
        return 'float', None
    return 'text', None


def defaults(install):
    """[{'section', 'key', 'default', 'help', 'kind', 'choices'}] in the file's order."""
    out, section, notes = [], None, []
    for line in _default_text(install).splitlines():
        s = line.strip()
        if not s:
            notes = [] if section is None else notes
            continue
        if s.startswith('#'):
            notes.append(s.lstrip('#').strip())
            continue
        if s.startswith('['):
            section, notes = s.strip('[]').strip(), []
            continue
        if '=' in s and section:
            k, v = (x.strip() for x in s.split('=', 1))
            help_ = '\n'.join(notes).strip()
            kind, choices = _kind(v, help_)
            out.append({'section': section, 'key': k, 'default': v, 'help': help_, 'kind': kind, 'choices': choices})
            notes = []
    return out


def _parse(text):
    vals, section = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('['):
            section = s.strip('[]').strip()
        elif section and '=' in s and not s.startswith('#'):
            k, v = (x.strip() for x in s.split('=', 1))
            vals[(section.lower(), k.lower())] = v
    return vals


def read(userdir, install):
    """Everything the window needs: the file, whether it exists, every setting with its value, which were
    changed from the default, and the popular ones."""
    path = path_of(userdir)
    text = ''
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        pass
    mine = _parse(text)
    rows = defaults(install)
    known = set()
    for r in rows:
        k = (r['section'].lower(), r['key'].lower())
        known.add(k)
        r['value'] = mine.get(k, r['default'])
        r['changed'] = k in mine and mine[k] != r['default']
    # (lines in your file that this OpenMW doesn't list: kept as they are, shown so they can be seen)
    extra = [{'section': s, 'key': k, 'value': v} for (s, k), v in mine.items() if (s, k) not in known]
    have = {(r['section'].lower(), r['key'].lower()) for r in rows}
    popular = [[s, k] for s, k in POPULAR if (s.lower(), k.lower()) in have]
    return {'path': path, 'exists': os.path.isfile(path), 'settings': rows, 'popular': popular, 'unknown': extra,
            'defaults_found': bool(rows)}


def _clean(kind, v):
    v = str(v).strip()
    if '\n' in v or '\r' in v:
        raise SettingsError('A setting is one line.')
    if kind == 'bool':
        v = v.lower()
        if v not in ('true', 'false'):
            raise SettingsError('Use true or false.')
    elif kind == 'words' and v not in [w for ws in WORDS.values() for w in ws]:
        raise SettingsError('That setting takes one of: %s.' % ', '.join(w for ws in WORDS.values() for w in ws))
    elif kind in ('int', 'choice'):
        if not re.fullmatch(r'-?\d+', v):
            raise SettingsError('That setting takes a whole number.')
    elif kind == 'float':
        try:
            f = float(v)
        except ValueError:
            raise SettingsError('That setting takes a number.')
        v = repr(f) if '.' in repr(f) else '%s.0' % f
    return v


def write(userdir, install, changes):
    """Change settings: changes [{'section', 'key', 'value'}]. A value equal to the default takes the line
    out. Returns {'path', 'backup', 'changed'}."""
    path = path_of(userdir)
    if not userdir or not os.path.isdir(userdir):
        raise SettingsError("OpenMW's settings folder wasn't found. Run the OpenMW Launcher once, so it sets it up.")
    rows = {(r['section'].lower(), r['key'].lower()): r for r in defaults(install)}
    if not rows:
        raise SettingsError("OpenMW's list of settings (defaults.bin) wasn't found in its folder, so the Workshop can't tell a "
                            "setting from a typing mistake. Open settings.cfg instead.")
    want = {}
    for c in changes or []:
        k = (str(c.get('section', '')).lower(), str(c.get('key', '')).lower())
        r = rows.get(k)
        if not r:
            raise SettingsError('OpenMW has no setting "%s" under [%s].' % (c.get('key'), c.get('section')))
        want[k] = (r, _clean(r['kind'], c.get('value', '')))
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        lines = []
    done, section, out, last_of = set(), None, [], {}
    for line in lines:
        s = line.strip()
        if s.startswith('['):
            section = s.strip('[]').strip().lower()
        elif section and '=' in s and not s.startswith('#'):
            k = (section, s.split('=', 1)[0].strip().lower())
            if k in want:
                r, v = want[k]
                done.add(k)
                if v == r['default']:
                    continue                                   # (back to the default: the line goes)
                line = '%s = %s' % (r['key'], v)
        out.append(line)
        if section:
            last_of[section] = len(out)
    # settings not in the file yet: under their section (made at the end when it isn't there)
    adds = {}
    for k, (r, v) in want.items():
        if k not in done and v != r['default']:
            adds.setdefault(k[0], []).append((r, v))
    for sec, items in adds.items():
        new = ['%s = %s' % (r['key'], v) for r, v in items]
        if sec in last_of:
            at = last_of[sec]
            out[at:at] = new
            for s2 in last_of:
                if last_of[s2] >= at and s2 != sec:
                    last_of[s2] += len(new)
            last_of[sec] = at + len(new)
        else:
            if out and out[-1].strip():
                out.append('')
            out.append('[%s]' % items[0][0]['section'])
            out += new
            last_of[sec] = len(out)
    backup = None
    if os.path.isfile(path):
        backup = path + '.workshop-backup-' + time.strftime('%Y%m%d-%H%M%S')
        shutil.copy2(path, backup)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out).rstrip('\n') + '\n')
    return {'path': path, 'backup': backup, 'changed': len(want)}
