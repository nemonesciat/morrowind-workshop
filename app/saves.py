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
    files = [f for f in glob.glob(os.path.join(saves_dir(), folder, '*.omwsave')) if os.path.basename(f) != PLAY_COPY]
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
                    'saves': len([x for x in glob.glob(os.path.join(root, d, '*.omwsave')) if os.path.basename(x) != PLAY_COPY]), 'missing': missing,
                    # (a quick start from the Workshop: a new character nobody named)
                    'quick': (h['name'] or '').lower() == 'player'})
    out.sort(key=lambda c: (c['quick'], -c['time']))
    return out


def latest_save(folder):
    """The newest save of a character (a full path), or None."""
    if not folder or os.sep in folder or '/' in folder or folder in ('.', '..'):
        return None
    return _latest(folder)


# ----- Play here from a save, without the trip through where it was saved ---------------------------------
# Loaded as it is, a save first builds the place the character was saved in, then the Workshop's commands move
# them: the user's Nemo, saved in Old Ebonheart, took 38 s and nine Tamriel Rebuilt cells before the move, and
# OpenMW put up its "frozen" notice. So a copy of the save is loaded instead, the same in every way but where
# the player stands (the player record's place and position). The save itself is only read. The copy sits in
# the character's own folder, so that saving in the game goes on under that character (OpenMW takes the
# character from the folder a loaded save is in); it is written over each time and left out of the Workshop's
# lists of saves. Its description in the game's Load menu says what it is.
PLAY_COPY = 'Workshop Play here.omwsave'
PLAY_DESC = 'Workshop: Play here (a copy, moved)'


def _subs(body):
    out, q = [], 0
    while q + 8 <= len(body):
        t, n = struct.unpack_from('<4sI', body, q)
        out.append([t, body[q + 8:q + 8 + n]])
        q += 8 + n
    if q != len(body):
        raise ValueError('a record runs short')
    return out


def _join(subs):
    return b''.join(t + struct.pack('<I', len(v)) + v for t, v in subs)


def cell_id(name=None, grid=None):
    """A cell as an OpenMW save writes it: an interior by its name, an exterior by its grid (x, y)."""
    if name:
        return b'\x02' + name.encode('cp1252', 'replace')
    return b'\x06' + struct.pack('<ii', int(grid[0]), int(grid[1]))


def moved_copy(save, pos, name=None, grid=None, cell_label=''):
    """A copy of a save with the player moved: pos (x, y, z, rx, ry, rz) in the cell named (an interior) or at
    grid (an exterior). Written beside the save as PLAY_COPY; returns its path. Raises when the save isn't laid
    out as expected (the caller then loads the save itself)."""
    data = open(save, 'rb').read()
    out, p, done = [], 0, False
    while p + 16 <= len(data):
        tag, size = struct.unpack_from('<4sI', data, p)
        head, body = data[p:p + 16], data[p + 16:p + 16 + size]
        p += 16 + size
        if tag == b'PLAY':
            subs = _subs(body)
            # (the player's place: the NAME just before LKEP, its last place outdoors; its position: the
            # object's own POS_, the first one in the record)
            k = next((i for i in range(1, len(subs)) if subs[i][0] == b'LKEP' and subs[i - 1][0] == b'NAME'), None)
            j = next((i for i, s in enumerate(subs) if s[0] == b'POS_' and len(s[1]) == 24), None)
            if k is None or j is None or j > k:
                raise ValueError("The save's player record isn't laid out as expected.")
            subs[j][1] = struct.pack('<6f', *[float(v) for v in pos])
            subs[k - 1][1] = cell_id(name, grid)
            if not name:
                subs[k][1] = struct.pack('<3f', *[float(v) for v in pos[:3]])
            body = _join(subs)
            head = head[:4] + struct.pack('<I', len(body)) + head[8:]
            done = True
        elif tag == b'SAVE':
            subs = _subs(body)
            for s in subs:
                if s[0] == b'PLCE' and cell_label:
                    s[1] = cell_label.encode('cp1252', 'replace') + b'\x00'
                elif s[0] == b'DESC':
                    s[1] = PLAY_DESC.encode('cp1252') + b'\x00'
            body = _join(subs)
            head = head[:4] + struct.pack('<I', len(body)) + head[8:]
        out.append(head + body)
    if not done or p != len(data):
        raise ValueError("The save's player record wasn't found.")
    dst = os.path.join(os.path.dirname(save), PLAY_COPY)
    tmp = dst + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(b''.join(out))
    os.replace(tmp, dst)
    return dst


def player_place(path):
    """(position, cell id bytes) of the player in a save: for checking a copy."""
    data = open(path, 'rb').read()
    p = 0
    while p + 16 <= len(data):
        tag, size = struct.unpack_from('<4sI', data, p)
        if tag == b'PLAY':
            subs = _subs(data[p + 16:p + 16 + size])
            k = next(i for i in range(1, len(subs)) if subs[i][0] == b'LKEP' and subs[i - 1][0] == b'NAME')
            j = next(i for i, s in enumerate(subs) if s[0] == b'POS_')
            return struct.unpack('<6f', subs[j][1]), subs[k - 1][1]
        p += 16 + size
    return None


def picture(folder):
    f = latest_save(folder)
    h = _header(f, want_picture=True) if f else None
    return h.get('picture') if h else None
