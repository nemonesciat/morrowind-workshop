"""Your OpenMW load order (the content= lines in openmw.cfg): read it, with the plugins in your
data folders that are switched off, and write it back after a change (with a backup first).

Only openmw.cfg is changed. OpenMW's own Launcher notices the change the next time it opens and
keeps it as a new profile, so nothing here fights with it."""
import os
import shutil
import struct
import time

from esm import iter_subrecords, zstr

EXTS = ('.esm', '.esp', '.omwaddon', '.omwgame', '.omwscripts')
# the Workshop's own helper files for "Play here", and OpenMW's built-in scripts (always loaded);
# never part of your load order
INTERNAL = ('workshoplink.omwscripts', 'workshopsparerooms.omwaddon', 'builtin.omwscripts')


class LoadOrderError(Exception):
    pass


def _masters(path):
    """Masters listed in a plugin's header (nothing for Lua script lists)."""
    if path.lower().endswith('.omwscripts'):
        return []
    try:
        with open(path, 'rb') as f:
            head = f.read(16)
            if head[:4] != b'TES3':
                return []
            size = struct.unpack_from('<I', head, 4)[0]
            data = f.read(min(size, 1 << 20))
        return [zstr(sd) for st, sd in iter_subrecords(data) if st == 'MAST']
    except (OSError, struct.error):
        return []


def _files_in(dirs):
    """name (lower case) -> (name as spelt, full path) for every plugin in the data folders;
    later folders win, like in the game."""
    out = {}
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if n.lower().endswith(EXTS) and os.path.isfile(os.path.join(d, n)):
                out[n.lower()] = (n, os.path.join(d, n))
    return out


def read(db):
    cfg = db.config or {}
    files = _files_in(cfg.get('data', []))
    grass = {g.lower() for g in cfg.get('groundcover', [])}
    project = db.project.plugin.lower() if db.project else None
    enabled = list(getattr(db, 'cfg_content_all', None) or cfg.get('content', []))
    rows, seen = [], set()

    def row(name, on):
        f = files.get(name.lower())
        return {'name': f[0] if f else name, 'enabled': on, 'found': bool(f),
                'folder': os.path.dirname(f[1]) if f else None,
                'kind': os.path.splitext(name)[1].lower().lstrip('.'),
                'masters': _masters(f[1]) if f else [],
                'mine': name.lower() == project}
    for n in enabled:
        if n.lower() in seen or n.lower() in INTERNAL:
            continue
        seen.add(n.lower())
        rows.append(row(n, True))
    off = [row(f[0], False) for k, f in sorted(files.items())
           if k not in seen and k not in INTERNAL and k not in grass and not k.endswith(' grass.omwaddon')]
    return {'cfg': cfg.get('user_cfg'), 'cfg_exists': cfg.get('user_cfg_exists', False),
            'install': cfg.get('install'), 'enabled': rows, 'available': off,
            'problems': problems([r['name'] for r in rows], {r['name'].lower(): r for r in rows + off})}


def problems(order, info):
    """What would break with plugins in this order: missing files, masters that are off or load later."""
    out = []
    pos = {n.lower(): i for i, n in enumerate(order)}
    for i, n in enumerate(order):
        r = info.get(n.lower()) or {}
        if r and not r.get('found'):
            out.append({'plugin': n, 'text': 'The file isn\'t in any of your data folders.'})
        for m in r.get('masters', []):
            j = pos.get(m.lower())
            if j is None:
                out.append({'plugin': n, 'text': 'Needs %s, which is %s.' % (m, 'switched off' if m.lower() in info else 'not installed')})
            elif j > i:
                out.append({'plugin': n, 'text': 'Needs %s, which loads after it. Masters must load first.' % m})
    return out


def sort_masters(order, info):
    """The same order, moved only as much as needed for every master to load before what needs it."""
    order = list(order)
    for _ in range(len(order) * 2):
        moved = False
        pos = {n.lower(): i for i, n in enumerate(order)}
        for i, n in enumerate(order):
            for m in (info.get(n.lower()) or {}).get('masters', []):
                j = pos.get(m.lower())
                if j is not None and j > i:
                    order.insert(i, order.pop(j))
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break
    return order


def save(db, order):
    """Write this list of enabled plugins (top to bottom) into openmw.cfg."""
    cfg = (db.config or {}).get('user_cfg')
    if not cfg or not os.path.isfile(cfg):
        raise LoadOrderError('OpenMW\'s settings file (openmw.cfg) wasn\'t found. Run the OpenMW Launcher once first.')
    clean, seen = [], set()
    for n in order:
        n = (n or '').strip()
        if n and n.lower() not in seen and n.lower() not in INTERNAL and '\n' not in n and '=' not in n:
            seen.add(n.lower())
            clean.append(n)
    if not any(n.lower().endswith(('.esm', '.omwgame')) for n in clean):
        raise LoadOrderError('Keep at least one game file (like Morrowind.esm) switched on.')
    with open(cfg, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8', errors='replace')
    nl = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    out, placed = [], False
    for line in lines:
        if line.strip().lower().startswith('content='):
            if not placed:
                out += ['content=' + n for n in clean]          # the new list where the old one was
                placed = True
            continue
        out.append(line)
    if not placed:
        out += ['content=' + n for n in clean]
    backup = cfg + '.workshop-backup-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(cfg, backup)
    tmp = cfg + '.workshop-new'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(nl.join(out) + nl)
    os.replace(tmp, cfg)
    return {'ok': True, 'backup': backup, 'count': len(clean)}
