"""Low-level readers for Morrowind / OpenMW data: plugins (.esm/.esp/.omwaddon),
BSA archives and openmw.cfg. Read-only: nothing here ever writes to game files."""
import mmap
import os
import struct

import osplat

ENC = 'cp1252'


def zstr(b):
    i = b.find(b'\0')
    if i >= 0:
        b = b[:i]
    return b.decode(ENC, 'replace')


def iter_subrecords(data):
    pos, n = 0, len(data)
    while pos + 8 <= n:
        tag = data[pos:pos + 4].decode('ascii', 'replace')
        size = struct.unpack_from('<I', data, pos + 4)[0]
        yield tag, data[pos + 8:pos + 8 + size]
        pos += 8 + size


class PluginFile:
    """Memory-mapped plugin. Records are yielded as (tag, offset, flags, data)."""

    def __init__(self, path):
        self.path = path
        self._f = open(path, 'rb')
        self.mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        self.header = {'author': '', 'description': '', 'masters': [], 'version': 0.0}
        tag = self.mm[0:4]
        if tag != b'TES3':
            raise ValueError('not a Morrowind plugin (missing TES3 header)')
        size = struct.unpack_from('<I', self.mm, 4)[0]
        for st, sd in iter_subrecords(self.mm[16:16 + size]):
            if st == 'HEDR' and len(sd) >= 300:
                self.header['version'] = round(struct.unpack_from('<f', sd, 0)[0], 2)
                self.header['author'] = zstr(sd[8:40])
                self.header['description'] = zstr(sd[40:296])
            elif st == 'MAST':
                self.header['masters'].append(zstr(sd))
        self.first = 16 + size

    def records(self):
        mm, pos, end = self.mm, self.first, len(self.mm)
        unpack = struct.unpack_from
        while pos + 16 <= end:
            tag, size, _unused, flags = unpack('<4sIII', mm, pos)
            yield tag.decode('ascii', 'replace'), pos, flags, mm[pos + 16:pos + 16 + size]
            pos += 16 + size

    def record_at(self, offset):
        tag, size, _unused, flags = struct.unpack_from('<4sIII', self.mm, offset)
        return tag.decode('ascii', 'replace'), flags, self.mm[offset + 16:offset + 16 + size]

    def close(self):
        try:
            self.mm.close()
            self._f.close()
        except Exception:
            pass


def bsa_file_list(path):
    """Return lowercase, forward-slash paths of every file inside a Morrowind BSA."""
    with open(path, 'rb') as f:
        head = f.read(12)
        version, hash_off, count = struct.unpack('<III', head)
        if version != 0x100:
            raise ValueError('unsupported BSA version %x' % version)
        f.seek(12 + count * 8)
        name_offs = struct.unpack('<%dI' % count, f.read(count * 4))
        names_start = 12 + count * 12
        names = f.read(12 + hash_off - names_start)
    out = []
    for o in name_offs:
        e = names.find(b'\0', o)
        out.append(names[o:e].decode(ENC, 'replace').lower().replace('\\', '/'))
    return out


def bsa_entries(path):
    """[(lowercase path, absolute offset, size)] for every file in a Morrowind BSA."""
    with open(path, 'rb') as f:
        version, hash_off, count = struct.unpack('<III', f.read(12))
        if version != 0x100:
            raise ValueError('unsupported BSA version %x' % version)
        sizes = struct.unpack('<%dI' % (count * 2), f.read(count * 8))
        name_offs = struct.unpack('<%dI' % count, f.read(count * 4))
        names = f.read(12 + hash_off - (12 + count * 12))
    data_start = 12 + hash_off + count * 8
    out = []
    for n, o in enumerate(name_offs):
        e = names.find(b'\0', o)
        out.append((names[o:e].decode(ENC, 'replace').lower().replace('\\', '/'),
                    data_start + sizes[2 * n + 1], sizes[2 * n]))
    return out


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('&&', '&').replace('&"', '"')
    return v


def openmw_userdir(install=None):
    """Where OpenMW keeps your openmw.cfg, settings.cfg and openmw.log (Documents\\My Games\\OpenMW on
    Windows, ~/.config/openmw on Linux)."""
    return osplat.openmw_dirs(install)[0]


def openmw_userdata(install=None):
    """Where OpenMW keeps its data folder and your saves (the same folder on Windows, ~/.local/share/openmw on Linux)."""
    return osplat.openmw_dirs(install)[1]


def find_openmw(hint=None):
    """The folder the game's program is in: the one chosen in the Workshop, else where OpenMW usually goes
    (Program Files and Windows' list of installed programs; on Linux the PATH, /usr/games, openmw.org's
    download unpacked at home, the Flatpak). None if not found."""
    for d in (hint, os.environ.get('WORKSHOP_OPENMW_INSTALL')):
        if osplat.has_game(d):
            return os.path.normpath(d)
    try:
        for d in osplat.openmw_installs():
            if osplat.has_game(d):
                return os.path.normpath(d)
    except Exception:
        pass
    return None


def read_openmw_config(install_hint=None):
    """Find and merge OpenMW's config files. Returns dict with data dirs,
    content files (load order), fallback archives and the config path(s)."""
    # Find the OpenMW install (global cfg holds resources/vfs-mw)
    install = find_openmw(install_hint)
    userdir, userdata = osplat.openmw_dirs(install)
    user_cfg = os.path.join(userdir, 'openmw.cfg')
    global_data = osplat.global_data_dir(install)

    result = {'data': [], 'content': [], 'archives': [], 'groundcover': [], 'config_files': [], 'install': install,
              'userdir': userdir, 'userdata': userdata, 'user_cfg': user_cfg, 'user_cfg_exists': os.path.isfile(user_cfg),
              'global_dirs': osplat.global_cfg_dirs(install)}

    def parse(path, base_dir):
        if not os.path.isfile(path):
            return
        result['config_files'].append(path)
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key, val = key.strip(), _unquote(val)
                if key in ('data', 'data-local'):
                    val = val.replace('?userdata?', userdata + os.sep).replace('?userconfig?', userdir + os.sep)
                    val = val.replace('?local?', (install or '') + os.sep).replace('?global?', global_data + os.sep)
                    if not os.path.isabs(val):
                        val = os.path.normpath(os.path.join(base_dir, val))
                    val = os.path.normpath(val)
                    if key == 'data-local':
                        result['data_local'] = val
                    elif val not in result['data']:
                        result['data'].append(val)
                elif key == 'content':
                    result['content'].append(val)
                elif key == 'fallback-archive':
                    result['archives'].append(val)
                elif key == 'groundcover':
                    result['groundcover'].append(val)       # grass plugins, drawn as groundcover
                elif key == 'fallback' and ',' in val:
                    # (Morrowind.ini's settings as OpenMW keeps them: the weather's colours by the hour, and more)
                    k, v = val.split(',', 1)
                    result.setdefault('fallback', {})[k.strip()] = v.strip()
                elif key == 'replace':
                    for k in [x.strip() for x in val.split(',')]:
                        if k in ('data', 'content', 'fallback-archive', 'groundcover'):
                            result[{'data': 'data', 'content': 'content', 'fallback-archive': 'archives',
                                    'groundcover': 'groundcover'}[k]] = []

    for g in result['global_dirs']:                 # (the game's own openmw.cfg: its folder, or /etc/openmw on Linux)
        parse(os.path.join(g, 'openmw.cfg'), g)
    parse(user_cfg, userdir)
    # data-local always has the highest priority
    if result.get('data_local') and os.path.isdir(result['data_local']):
        result['data'].append(result['data_local'])
    return result
