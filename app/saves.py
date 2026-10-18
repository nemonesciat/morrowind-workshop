"""Your characters, from OpenMW's saves: so Play here can start as one of them (from their latest
save, moved to the spot you picked) instead of a new character. Only the start of each save file
is read: who it is, where, which mods it needs, and its little picture."""
import glob
import os
import struct

from esm import openmw_userdir


def saves_dir():
    base = os.environ.get('WORKSHOP_OPENMW_USERDIR') or openmw_userdir()
    return os.path.join(base, 'saves')


def _header(path, want_picture=False):
    """{name, level, class, cell, desc, needs: [content files], picture?} from a save's first records."""
    with open(path, 'rb') as f:
        head = f.read(16)
        if len(head) < 16 or head[:4] != b'TES3':
            return None
        f.seek(16 + struct.unpack_from('<I', head, 4)[0])
        h2 = f.read(16)
        if len(h2) < 16 or h2[:4] != b'SAVE':
            return None
        body = f.read(struct.unpack_from('<I', h2, 4)[0])
    out = {'name': '', 'level': 0, 'class': '', 'cell': '', 'desc': '', 'needs': []}
    p = 0
    while p + 8 <= len(body):
        st, ss = body[p:p + 4], struct.unpack_from('<I', body, p + 4)[0]
        v = body[p + 8:p + 8 + ss]
        p += 8 + ss
        txt = lambda: v.split(b'\x00')[0].decode('cp1252', 'replace')
        if st == b'PLNA':
            out['name'] = txt()
        elif st == b'PLLE' and ss >= 4:
            out['level'] = struct.unpack_from('<i', v)[0]
        elif st == b'PLCN':
            out['class'] = txt()
        elif st == b'PLCE':
            out['cell'] = txt()
        elif st == b'DESC':
            out['desc'] = txt()
        elif st == b'DEPE':
            out['needs'].append(txt())
        elif st == b'SCRN' and want_picture:
            out['picture'] = bytes(v)
    return out


def _latest(folder):
    files = glob.glob(os.path.join(saves_dir(), folder, '*.omwsave'))
    return max(files, key=os.path.getmtime) if files else None


def characters(db=None):
    """Every character with saves, newest played first."""
    root = saves_dir()
    loaded = {p['name'].lower() for p in (db.plugins if db else [])}
    out = []
    for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        f = _latest(d)
        if not f:
            continue
        try:
            h = _header(f)
        except OSError:
            h = None
        if not h:
            continue
        missing = [n for n in h['needs'] if not n.lower().endswith('.omwscripts') and loaded and n.lower() not in loaded]
        out.append({'folder': d, 'name': h['name'] or d, 'level': h['level'], 'class': h['class'], 'cell': h['cell'],
                    'desc': h['desc'], 'file': os.path.basename(f), 'time': os.path.getmtime(f),
                    'saves': len(glob.glob(os.path.join(root, d, '*.omwsave'))), 'missing': missing,
                    # (a quick start from the Workshop: a new character nobody named)
                    'quick': (h['name'] or '').lower() == 'player'})
    out.sort(key=lambda c: (c['quick'], -c['time']))
    return out


def latest_save(folder):
    """The newest save of a character (a full path), or None."""
    if not folder or os.sep in folder or '/' in folder or folder in ('.', '..'):
        return None
    return _latest(folder)


def picture(folder):
    f = latest_save(folder)
    h = _header(f, want_picture=True) if f else None
    return h.get('picture') if h else None
