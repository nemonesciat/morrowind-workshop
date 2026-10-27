"""The Library: your own models and textures, brought into the Workshop and usable in every mod.

Files go into the folder your mods live in (OpenMW's data-local folder, or the Workshop's plugin
folder), under meshes\\wslib and textures\\wslib, so the game finds them straight away and a mod that
uses them takes them along when it is packed for sharing. Models from other programs are turned into
Morrowind .nif models: OBJ (with its .mtl and pictures), glTF and GLB (Blender's usual export). NIF
models are copied as they are, with the textures found beside them. Blender's own .blend files
are read directly (blendread.py). Pictures (PNG, JPG, TGA, DDS,
BMP) are used as they are: OpenMW reads all of them.

An index of what was brought in is kept beside the Workshop's settings (library.json)."""
import base64
import json
import math
import os
import re
import shutil
import struct
import time

import editing
import nifwrite
from editing import EditError
from project import APP_DIR, join_subs, zs

INDEX = os.path.join(APP_DIR, 'library.json')
SUB = 'wslib'
PICTURES = ('.png', '.jpg', '.jpeg', '.tga', '.dds', '.bmp')
SOUNDS = ('.wav', '.mp3', '.ogg', '.flac')
MODELS = ('.nif', '.obj', '.gltf', '.glb', '.dae', '.fbx', '.blend')
EACH = '*each*'                 # "bring in each object of the file as its own model"
UNITS_PER_METRE = 70.0          # a Morrowind unit is about 1.4 cm


# ------------------------------------------------------------------ where things go
def data_dir(db):
    return os.environ.get('WORKSHOP_PLUGIN_DIR') or db.config.get('data_local') or \
        os.path.join(db.config.get('userdata') or db.config['userdir'], 'data')


def _index():
    if not os.path.exists(INDEX):
        return []
    try:
        with open(INDEX, encoding='utf-8-sig') as f:
            return json.load(f).get('items', [])
    except (OSError, ValueError):
        # never start a new list over one that can't be read: keep it aside, then start again
        try:
            os.replace(INDEX, INDEX + '.unreadable-%d' % int(time.time()))
        except OSError:
            raise EditError('The Library\'s list (library.json) can\'t be read or put aside.')
        return []


def _save_index(items):
    tmp = INDEX + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'items': items}, f, indent=1)
    os.replace(tmp, INDEX)


def _slug(name):
    s = re.sub(r'[^a-z0-9]+', '_', os.path.splitext(os.path.basename(name or 'item'))[0].lower()).strip('_')
    return s[:40] or 'item'


def _free_name(folder, stem, ext):
    cand, n = stem, 2
    while os.path.exists(os.path.join(folder, cand + ext)):
        cand = '%s_%d' % (stem, n)
        n += 1
    return cand


def _register(db, rel, full):
    """Make the Workshop (and its 3D view) know a new file at once, without reading everything again."""
    rel = rel.lower().replace('\\', '/')
    db.meshes.loose[rel] = full
    try:
        db.assets.add(rel)
    except AttributeError:
        pass
    db.meshes.cache.pop(rel, None)


def listing(db):
    """What's in the Library, newest first, with which of them are missing on disk."""
    out = []
    base = data_dir(db)
    for it in _index():
        it = dict(it)
        it['ok'] = os.path.isfile(os.path.join(base, *it['file'].split('/')))
        out.append(it)
    out.sort(key=lambda i: -i.get('added', 0))
    return {'items': out, 'folder': os.path.join(base, 'meshes', SUB)}


# ------------------------------------------------------------------ pictures
def _png_size(raw):
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', raw[16:24])
        has_alpha = raw[25] in (4, 6) or b'tRNS' in raw[:4096]
        return w, h, has_alpha
    return None


def _picture_alpha(path):
    """Whether a picture has see-through parts (so the model gets an alpha property)."""
    try:
        with open(path, 'rb') as f:
            raw = f.read(65536)
    except OSError:
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext == '.png':
        s = _png_size(raw)
        return bool(s and s[2])
    if ext == '.tga' and len(raw) > 18:
        return raw[16] == 32 and (raw[17] & 0x0F) > 0
    if ext == '.dds' and len(raw) > 128:
        four = raw[84:88]
        return four in (b'DXT3', b'DXT5') or (struct.unpack_from('<I', raw, 80)[0] & 1 and four == b'\0\0\0\0')
    return False


def _copy_picture(db, src_path=None, raw=None, name='texture', ext='.png'):
    """A picture into textures\\wslib: returns the name a model uses for it (wslib\\x.png)."""
    folder = os.path.join(data_dir(db), 'textures', SUB)
    os.makedirs(folder, exist_ok=True)
    ext = (os.path.splitext(src_path)[1] if src_path else ext).lower()
    if ext == '.jpeg':
        ext = '.jpg'
    if ext not in PICTURES:
        raise EditError('"%s" is not a picture the game can use (PNG, JPG, TGA, DDS or BMP).' % os.path.basename(src_path or name))
    head = (open(src_path, 'rb').read(16) if src_path else raw[:16])
    ok = {'.png': head.startswith(b'\x89PNG'), '.jpg': head.startswith(b'\xff\xd8'), '.dds': head.startswith(b'DDS '),
          '.bmp': head.startswith(b'BM'), '.tga': len(head) >= 16}
    if not ok.get(ext, False):
        raise EditError('"%s" isn\'t a working %s picture (the file may be damaged, or have the wrong ending).' % (
            os.path.basename(src_path or name), ext[1:].upper()))
    stem = _free_name(folder, _slug(src_path or name), ext)
    dest = os.path.join(folder, stem + ext)
    if src_path:
        shutil.copyfile(src_path, dest)
    else:
        with open(dest, 'wb') as f:
            f.write(raw)
    _register(db, 'textures/%s/%s%s' % (SUB, stem, ext), dest)
    return '%s\\%s%s' % (SUB, stem, ext), dest


# ------------------------------------------------------------------ sounds
def _copy_sound(db, src_path):
    """A sound into Sound\\wslib (OpenMW plays WAV, MP3, OGG and FLAC): returns the name a sound
    record uses for it (wslib\\x.wav)."""
    ext = os.path.splitext(src_path)[1].lower()
    head = open(src_path, 'rb').read(12)
    ok = {'.wav': head[:4] == b'RIFF' and head[8:12] == b'WAVE', '.ogg': head[:4] == b'OggS', '.flac': head[:4] == b'fLaC',
          '.mp3': head[:3] == b'ID3' or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)}
    if not ok.get(ext, False):
        raise EditError('"%s" isn\'t a working %s sound (the file may be damaged, or have the wrong ending).' % (
            os.path.basename(src_path), ext[1:].upper()))
    folder = os.path.join(data_dir(db), 'sound', SUB)
    os.makedirs(folder, exist_ok=True)
    stem = _free_name(folder, _slug(src_path), ext)
    dest = os.path.join(folder, stem + ext)
    shutil.copyfile(src_path, dest)
    _register(db, 'sound/%s/%s%s' % (SUB, stem, ext), dest)
    return '%s\\%s%s' % (SUB, stem, ext), dest


# how far a sound carries: the game's (min, max) distances (a fire is 2, 15)
REACH = {'near': (1, 8), 'room': (2, 15), 'far': (5, 40)}


def make_sound(db, entry_id, commit=True):
    """A sound record for a Library sound (for scripts' PlaySound, doors and sound sources)."""
    editing._require_project(db)
    e = entry(entry_id)
    if not e or e.get('type') != 'sound':
        raise EditError('That sound is not in the Library.')
    rid = (e.get('records') or {}).get('SOUN')
    if rid and db.resolve_id(rid) is not None:
        return {'id': rid, 'type': 'SOUN', 'i': db.resolve_id(rid)}
    import create
    rid = create.suggest_id(db, 'lib', _bare(e['id']))
    lo, hi = REACH.get(e.get('reach') or 'room', REACH['room'])
    vol = max(0, min(255, int(round(255 * float(e.get('volume', 0.8))))))
    db.project.set_record('SOUN', rid.lower(), 0, join_subs([('NAME', zs(rid)), ('FNAM', zs(e['sound'])),
                                                             ('DATA', bytes([vol, lo, hi]))]), created=True)
    _remember(entry_id, 'SOUN', rid)
    if commit:
        editing.commit(db, 'Made the sound "%s" from the Library' % (e.get('name') or e['id']))
    else:
        db.sync_project()
    return {'id': rid, 'type': 'SOUN', 'i': db.resolve_id(rid)}


def make_sound_source(db, entry_id, commit=True):
    """Something to place that plays a Library sound over and over where it stands, unseen (a light
    that gives no light, as the game's own torches carry their crackle)."""
    e = entry(entry_id)
    snd = make_sound(db, entry_id, commit=False)
    rid = (e.get('records') or {}).get('LIGH')
    if rid and db.resolve_id(rid) is not None:
        if commit:
            editing.commit(db, 'Made the sound "%s" from the Library' % (e.get('name') or e['id']))
        return {'id': rid, 'type': 'LIGH', 'i': db.resolve_id(rid)}
    import create
    rid = create.suggest_id(db, 'sound', _bare(e['id']))
    # (the game only plays a light's sound when it has a model: the editor's marker, which the game never draws)
    marker = [('MODL', zs('EditorMarker.nif'))] if db.meshes.read('meshes/editormarker.nif') else []
    db.project.set_record('LIGH', rid.lower(), 0, join_subs([('NAME', zs(rid))] + marker + [
        ('LHDT', struct.pack('<fiiiBBBBI', 0.0, 0, -1, 0, 0, 0, 0, 0, 0)), ('SNAM', zs(snd['id']))]), created=True)
    _remember(entry_id, 'LIGH', rid)
    if commit:
        editing.commit(db, 'Made a sound source playing "%s" from the Library' % (e.get('name') or e['id']))
    else:
        db.sync_project()
    return {'id': rid, 'type': 'LIGH', 'i': db.resolve_id(rid)}


def _bare(entry_id):
    return entry_id[4:] if entry_id.startswith('snd_') else entry_id


def _remember(entry_id, tag, rid):
    items = _index()
    for it in items:
        if it['id'] == entry_id:
            it.setdefault('records', {})[tag] = rid
    _save_index(items)


def set_sound(db, entry_id, volume=None, reach=None):
    """Change how loud a Library sound is and how far it carries (its record too, if made)."""
    items = _index()
    e = next((i for i in items if i['id'] == entry_id and i.get('type') == 'sound'), None)
    if not e:
        raise EditError('That sound is not in the Library.')
    if volume is not None:
        e['volume'] = max(0.0, min(1.0, float(volume)))
    if reach in REACH:
        e['reach'] = reach
    _save_index(items)
    rid = (e.get('records') or {}).get('SOUN')
    rec = db.project.records.get('SOUN|%s' % rid.lower()) if db.project and rid else None
    if rec:
        lo, hi = REACH.get(e.get('reach') or 'room')
        vol = max(0, min(255, int(round(255 * float(e.get('volume', 0.8))))))
        db.project.set_record('SOUN', rec['key'], rec['flags'], join_subs([('NAME', zs(rid)), ('FNAM', zs(e['sound'])),
                                                                          ('DATA', bytes([vol, lo, hi]))]))
        editing.commit(db, 'Changed the sound "%s"' % (e.get('name') or e['id']))
    return e


# ------------------------------------------------------------------ reading other programs' models
def _find_beside(folder, name):
    """A file a model names (often with a path from someone else's computer): look beside the model."""
    if not name:
        return None
    name = name.replace('\\', '/').strip()
    for cand in (name, os.path.basename(name)):
        p = os.path.join(folder, cand)
        if os.path.isfile(p):
            return p
    low = os.path.basename(name).lower()
    for root, _d, files in os.walk(folder):
        for fn in files:
            if fn.lower() == low:
                return os.path.join(root, fn)
    return None


def read_obj(path):
    """Parts of an OBJ model (one per material), in its own units and axes, plus the materials."""
    folder = os.path.dirname(path)
    V, T, N = [], [], []
    groups = {}                  # material -> {'verts', 'uvs', 'normals', 'tris', 'map': {}}
    cur = 'default'
    mtl = {}
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        k = parts[0]
        if k == 'v' and len(parts) >= 4:
            V.append(tuple(float(x) for x in parts[1:4]))
        elif k == 'vt' and len(parts) >= 3:
            T.append((float(parts[1]), float(parts[2])))
        elif k == 'vn' and len(parts) >= 4:
            N.append(tuple(float(x) for x in parts[1:4]))
        elif k == 'mtllib':
            p = _find_beside(folder, line.split(None, 1)[1])
            if p:
                mtl.update(_read_mtl(p))
        elif k == 'usemtl':
            cur = line.split(None, 1)[1].strip() if len(parts) > 1 else 'default'
        elif k == 'f' and len(parts) >= 4:
            g = groups.setdefault(cur, {'verts': [], 'uvs': [], 'normals': [], 'tris': [], 'map': {}})
            corner = []
            for c in parts[1:]:
                bits = (c.split('/') + ['', ''])[:3]
                vi = int(bits[0]) if bits[0] else 0
                ti = int(bits[1]) if bits[1] else 0
                ni = int(bits[2]) if bits[2] else 0
                vi = vi - 1 if vi > 0 else len(V) + vi
                ti = (ti - 1 if ti > 0 else len(T) + ti) if ti else None
                ni = (ni - 1 if ni > 0 else len(N) + ni) if ni else None
                key = (vi, ti, ni)
                if key not in g['map']:
                    g['map'][key] = len(g['verts'])
                    g['verts'].append(V[vi])
                    g['uvs'].append((T[ti][0], 1.0 - T[ti][1]) if ti is not None and ti < len(T) else (0.0, 0.0))
                    g['normals'].append(N[ni] if ni is not None and ni < len(N) else None)
                corner.append(g['map'][key])
            for i in range(1, len(corner) - 1):
                g['tris'].append((corner[0], corner[i], corner[i + 1]))
    out = []
    for name, g in groups.items():
        m = mtl.get(name, {})
        normals = g['normals'] if all(n is not None for n in g['normals']) else None
        out.append({'name': name, 'verts': g['verts'], 'uvs': g['uvs'] if T else None, 'normals': normals,
                    'tris': g['tris'], 'color': m.get('color', (1, 1, 1)), 'opacity': m.get('opacity', 1.0),
                    'picture': _find_beside(folder, m.get('map')) if m.get('map') else None})
    return out


def _read_mtl(path):
    out, cur = {}, None
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            k = parts[0].lower()
            if k == 'newmtl':
                cur = out.setdefault(line.split(None, 1)[1].strip(), {})
            elif cur is None:
                continue
            elif k == 'kd' and len(parts) >= 4:
                cur['color'] = tuple(max(0.0, min(1.0, float(x))) for x in parts[1:4])
            elif k == 'd' and len(parts) >= 2:
                cur['opacity'] = max(0.0, min(1.0, float(parts[1])))
            elif k == 'map_kd':
                # the file name is the last thing on the line (options like -s 1 1 1 may come first)
                cur['map'] = line.strip().split(None, 1)[1].split(' -')[-1].strip() if ' ' in line.strip() else None
                if cur['map'] and cur['map'].startswith('-'):
                    cur['map'] = cur['map'].split()[-1]
    return out


_GL_TYPES = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
_GL_COUNT = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_gltf(path):
    """Parts of a glTF 2.0 model (.gltf with its .bin and pictures, or one .glb), with the scene's own
    placing of each piece applied. Animations and skins are left out."""
    raw = open(path, 'rb').read()
    folder = os.path.dirname(path)
    bin_chunk = None
    if raw[:4] == b'glTF':
        _magic, _ver, _length = struct.unpack_from('<III', raw, 0)
        p, doc = 12, None
        while p < len(raw):
            clen, ctype = struct.unpack_from('<II', raw, p)
            chunk = raw[p + 8:p + 8 + clen]
            if ctype == 0x4E4F534A:
                doc = json.loads(chunk.decode('utf-8'))
            elif ctype == 0x004E4942:
                bin_chunk = chunk
            p += 8 + clen
    else:
        doc = json.loads(raw.decode('utf-8'))
    if not doc:
        raise EditError('This glTF file could not be read.')
    buffers = []
    for b in doc.get('buffers', []):
        uri = b.get('uri')
        if uri is None:
            buffers.append(bin_chunk or b'')
        elif uri.startswith('data:'):
            buffers.append(base64.b64decode(uri.split(',', 1)[1]))
        else:
            p = _find_beside(folder, _unquote(uri))
            if not p:
                raise EditError('The model\'s data file "%s" is missing. Bring it in together with the model.' % uri)
            buffers.append(open(p, 'rb').read())

    def view_bytes(vi):
        v = doc['bufferViews'][vi]
        buf = buffers[v['buffer']]
        o = v.get('byteOffset', 0)
        return buf[o:o + v['byteLength']], v.get('byteStride')

    def accessor(ai):
        a = doc['accessors'][ai]
        n, comps, fmt = a['count'], _GL_COUNT[a['type']], _GL_TYPES[a['componentType']]
        if 'bufferView' not in a:
            return [(0,) * comps] * n
        data, stride = view_bytes(a['bufferView'])
        size = struct.calcsize('<' + fmt)
        stride = stride or size * comps
        o = a.get('byteOffset', 0)
        out = [struct.unpack_from('<%d%s' % (comps, fmt), data, o + i * stride) for i in range(n)]
        if a.get('normalized') and fmt != 'f':
            m = float((1 << (8 * size - (1 if fmt.islower() else 0))) - 1)
            out = [tuple(x / m for x in t) for t in out]
        return out
    # pictures: saved later by the caller; here just how to get each one's bytes
    images = []
    for im in doc.get('images', []):
        if 'bufferView' in im:
            data, _s = view_bytes(im['bufferView'])
            ext = '.png' if 'png' in im.get('mimeType', 'png') else '.jpg'
            images.append({'raw': bytes(data), 'ext': ext, 'name': im.get('name') or 'texture'})
        elif im.get('uri', '').startswith('data:'):
            head, b64 = im['uri'].split(',', 1)
            images.append({'raw': base64.b64decode(b64), 'ext': '.png' if 'png' in head else '.jpg', 'name': im.get('name') or 'texture'})
        else:
            images.append({'path': _find_beside(folder, _unquote(im.get('uri', ''))), 'name': im.get('uri', '')})
    textures = doc.get('textures', [])
    mats = []
    for m in doc.get('materials', []):
        pbr = m.get('pbrMetallicRoughness', {})
        col = pbr.get('baseColorFactor', [1, 1, 1, 1])
        tex = pbr.get('baseColorTexture', {}).get('index')
        img = textures[tex].get('source') if tex is not None and tex < len(textures) else None
        mats.append({'name': m.get('name') or 'material', 'color': tuple(col[:3]), 'opacity': col[3] if len(col) > 3 else 1.0,
                     'image': img, 'alpha': m.get('alphaMode', 'OPAQUE') != 'OPAQUE', 'double': bool(m.get('doubleSided'))})
    parts = []

    def node_matrix(nd):
        if 'matrix' in nd:
            m = nd['matrix']
            return [[m[0], m[4], m[8], m[12]], [m[1], m[5], m[9], m[13]], [m[2], m[6], m[10], m[14]], [0, 0, 0, 1]]
        t = nd.get('translation', [0, 0, 0])
        x, y, z, w = nd.get('rotation', [0, 0, 0, 1])
        s = nd.get('scale', [1, 1, 1])
        R = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
             [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
             [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        return [[R[i][0] * s[0], R[i][1] * s[1], R[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]

    def mul(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

    def visit(ni, M):
        nd = doc['nodes'][ni]
        M = mul(M, node_matrix(nd))
        if 'mesh' in nd:
            det = (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
                   + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
            for prim in doc['meshes'][nd['mesh']].get('primitives', []):
                if prim.get('mode', 4) != 4 or 'POSITION' not in prim.get('attributes', {}):
                    continue
                at = prim['attributes']
                pos = accessor(at['POSITION'])
                verts = [tuple(M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2] + M[i][3] for i in range(3)) for v in pos]
                normals = None
                if 'NORMAL' in at:
                    normals = []
                    for v in accessor(at['NORMAL']):
                        w = [M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2] for i in range(3)]
                        L = math.sqrt(sum(c * c for c in w)) or 1
                        normals.append(tuple(c / L for c in w))
                uvs = [tuple(t[:2]) for t in accessor(at['TEXCOORD_0'])] if 'TEXCOORD_0' in at else None
                idx = [i[0] for i in accessor(prim['indices'])] if 'indices' in prim else list(range(len(verts)))
                tris = [(idx[k], idx[k + 1], idx[k + 2]) for k in range(0, len(idx) - 2, 3)]
                if det < 0:
                    tris = [(a, c, b) for a, b, c in tris]
                m = mats[prim['material']] if prim.get('material') is not None and prim['material'] < len(mats) else {}
                parts.append({'name': m.get('name') or 'part', 'verts': verts, 'normals': normals, 'uvs': uvs, 'tris': tris,
                              'color': m.get('color', (1, 1, 1)), 'opacity': m.get('opacity', 1.0),
                              'alpha': m.get('alpha', False), 'double': m.get('double', False),
                              'image': m.get('image')})
        for c in nd.get('children', []):
            visit(c, M)
    scene = doc.get('scenes', [{}])[doc.get('scene', 0)] if doc.get('scenes') else {'nodes': list(range(len(doc.get('nodes', []))))}
    I = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for ni in scene.get('nodes', []):
        visit(ni, I)
    return parts, images


def _unquote(s):
    from urllib.parse import unquote
    return unquote(s or '')


def _mat4_mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _apply_m(M, v, w=1.0):
    return tuple(M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2] + M[i][3] * w for i in range(3))


_I4 = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def read_dae(path):
    """Parts of a COLLADA model (.dae): its meshes as the scene places them, in metres with Y up,
    each material's first picture. Animations and skins are left out."""
    import xml.etree.ElementTree as ET
    folder = os.path.dirname(path)
    root = ET.parse(path).getroot()
    ns = root.tag[:root.tag.index('}') + 1] if root.tag.startswith('{') else ''
    q = lambda tag: ns + tag
    unit = root.find('%s/%s' % (q('asset'), q('unit')))
    metre = float(unit.get('meter', '1')) if unit is not None else 1.0
    up = (root.findtext('%s/%s' % (q('asset'), q('up_axis'))) or 'Y_UP').strip().upper()
    by_id = {e.get('id'): e for e in root.iter() if e.get('id')}
    # pictures: image -> file, effect -> image (through its sampler and surface), material -> effect
    def image_file(img_id):
        im = by_id.get(img_id)
        if im is None:
            return None
        ref = im.findtext('.//' + q('init_from'))
        if not (ref or '').strip():
            ref = im.findtext('.//' + q('ref'))                     # (COLLADA 1.5: init_from/ref)
        ref = (ref or '').strip()
        if ref and not ref.endswith('.') and by_id.get(ref) is not None and by_id.get(ref).tag == q('image'):
            return image_file(ref)
        return _find_beside(folder, _unquote((ref or '').replace('file:///', '').replace('file://', ''))) if ref else None

    def material_picture(mat_id):
        mat = by_id.get(mat_id)
        if mat is None:
            return None, (1, 1, 1)
        inst = mat.find(q('instance_effect'))
        eff = by_id.get((inst.get('url') or '')[1:]) if inst is not None else None
        if eff is None:
            return None, (1, 1, 1)
        col = (1, 1, 1)
        c = eff.find('.//%s/%s' % (q('diffuse'), q('color')))
        if c is not None and c.text:
            v = [float(x) for x in c.text.split()]
            col = tuple(max(0.0, min(1.0, x)) for x in v[:3])
        tex = eff.find('.//%s/%s' % (q('diffuse'), q('texture')))
        if tex is None:
            return None, col
        sampler = tex.get('texture')
        # sampler -> surface -> image (COLLADA 1.4), or straight to an image
        params = {p.get('sid'): p for p in eff.iter(q('newparam'))}
        target = sampler
        for _ in range(3):
            p = params.get(target)
            if p is None:
                break
            ii = p.find('.//' + q('instance_image'))               # (COLLADA 1.5)
            if ii is not None and ii.get('url'):
                target = ii.get('url')[1:]
                break
            src = p.findtext('.//' + q('source')) or p.findtext('.//' + q('init_from'))
            if not src:
                break
            target = src
        return image_file(target), col

    def floats(src_id):
        s = by_id.get(src_id)
        fa = s.find(q('float_array')) if s is not None else None
        acc = s.find('.//' + q('accessor')) if s is not None else None
        stride = int(acc.get('stride', '1')) if acc is not None else 1
        vals = [float(x) for x in (fa.text or '').split()] if fa is not None else []
        return [tuple(vals[i:i + stride]) for i in range(0, len(vals) - stride + 1, stride)]

    parts = []

    def geometry(geo, M, bind):
        mesh = geo.find(q('mesh'))
        if mesh is None:
            return
        vin = mesh.find(q('vertices'))
        pos_src = None
        if vin is not None:
            for inp in vin.findall(q('input')):
                if inp.get('semantic') == 'POSITION':
                    pos_src = inp.get('source')[1:]
        for prim in list(mesh):
            if prim.tag not in (q('triangles'), q('polylist'), q('polygons')):
                continue
            inputs = prim.findall(q('input'))
            nin = max(int(i.get('offset', '0')) for i in inputs) + 1 if inputs else 1
            offs = {}
            for i in inputs:
                sem = i.get('semantic')
                if sem == 'TEXCOORD' and i.get('set') not in (None, '0') and 'TEXCOORD' in offs:
                    continue
                offs[sem] = (int(i.get('offset', '0')), floats(i.get('source')[1:]) if sem != 'VERTEX' else floats(pos_src))
            if 'VERTEX' not in offs:
                continue
            if prim.tag == q('polygons'):
                plist = [[int(x) for x in p_.text.split()] for p_ in prim.findall(q('p')) if p_.text]
                counts = [len(p_) // nin for p_ in plist]
                idx = [x for p_ in plist for x in p_]
            else:
                idx = [int(x) for x in (prim.findtext(q('p')) or '').split()]
                if prim.tag == q('triangles'):
                    counts = [3] * (len(idx) // (3 * nin))
                else:
                    counts = [int(x) for x in (prim.findtext(q('vcount')) or '').split()]
            part = {'verts': [], 'uvs': [], 'normals': [], 'tris': [], 'map': {}}
            k = 0
            for cnt in counts:
                corner = []
                for _ in range(cnt):
                    key = tuple(idx[k * nin:(k + 1) * nin])
                    k += 1
                    if key not in part['map']:
                        vo, vs = offs['VERTEX']
                        v = _apply_m(M, vs[key[vo]])
                        part['map'][key] = len(part['verts'])
                        part['verts'].append(v)
                        if 'NORMAL' in offs:
                            no, nsrc = offs['NORMAL']
                            part['normals'].append(_apply_m(M, nsrc[key[no]], 0.0))
                        if 'TEXCOORD' in offs:
                            to, tsrc = offs['TEXCOORD']
                            t = tsrc[key[to]]
                            part['uvs'].append((t[0], 1.0 - t[1]))
                    corner.append(part['map'][key])
                for i in range(1, len(corner) - 1):
                    part['tris'].append((corner[0], corner[i], corner[i + 1]))
            mat_id = bind.get(prim.get('material'), prim.get('material'))
            pic, col = material_picture(mat_id)
            parts.append({'name': prim.get('material') or 'part', 'verts': part['verts'],
                          'uvs': part['uvs'] if 'TEXCOORD' in offs else None,
                          'normals': part['normals'] if 'NORMAL' in offs else None,
                          'tris': part['tris'], 'color': col, 'picture': pic})

    def node(n, M):
        for t in list(n):
            tag = t.tag[len(ns):]
            v = [float(x) for x in (t.text or '').split()]
            if tag == 'matrix' and len(v) == 16:
                M = _mat4_mul(M, [v[0:4], v[4:8], v[8:12], v[12:16]])
            elif tag == 'translate' and len(v) == 3:
                M = _mat4_mul(M, [[1, 0, 0, v[0]], [0, 1, 0, v[1]], [0, 0, 1, v[2]], [0, 0, 0, 1]])
            elif tag == 'scale' and len(v) == 3:
                M = _mat4_mul(M, [[v[0], 0, 0, 0], [0, v[1], 0, 0], [0, 0, v[2], 0], [0, 0, 0, 1]])
            elif tag == 'rotate' and len(v) == 4:
                x, y, z, a = v[0], v[1], v[2], math.radians(v[3])
                L = math.sqrt(x * x + y * y + z * z) or 1
                x, y, z = x / L, y / L, z / L
                c, s, C = math.cos(a), math.sin(a), 1 - math.cos(a)
                M = _mat4_mul(M, [[c + x * x * C, x * y * C - z * s, x * z * C + y * s, 0], [y * x * C + z * s, c + y * y * C, y * z * C - x * s, 0],
                                  [z * x * C - y * s, z * y * C + x * s, c + z * z * C, 0], [0, 0, 0, 1]])
        for ig in n.findall(q('instance_geometry')):
            bind = {im.get('symbol'): (im.get('target') or '')[1:] for im in ig.iter(q('instance_material'))}
            geo = by_id.get((ig.get('url') or '')[1:])
            if geo is not None:
                geometry(geo, M, bind)
        for inode in n.findall(q('instance_node')):
            sub = by_id.get((inode.get('url') or '')[1:])
            if sub is not None:
                node(sub, M)
        for c in n.findall(q('node')):
            node(c, M)
    scene = root.find('%s/%s' % (q('scene'), q('instance_visual_scene')))
    vs = by_id.get((scene.get('url') or '')[1:]) if scene is not None else None
    if vs is None:
        vs = root.find('.//' + q('visual_scene'))
    if vs is not None:
        for n in vs.findall(q('node')):
            node(n, _I4)
    else:
        for geo in root.iter(q('geometry')):
            geometry(geo, _I4, {})
    # to metres with Y up, like the other formats
    for p in parts:
        fix = (lambda v: (v[0] * metre, v[2] * metre, -v[1] * metre)) if up == 'Z_UP' else (lambda v: (v[0] * metre, v[1] * metre, v[2] * metre))
        p['verts'] = [fix(v) for v in p['verts']]
        if p.get('normals'):
            p['normals'] = [(n[0], n[2], -n[1]) if up == 'Z_UP' else n for n in p['normals']]
        if up == 'X_UP':
            p['verts'] = [(-v[1], v[0], v[2]) for v in p['verts']]
    return parts


def read_fbx(path):
    """Parts of an FBX model (binary, 2011 or newer): its meshes with their own placing, in metres
    with Y up, each material's first picture. Animations and skins are left out."""
    import zlib
    raw = open(path, 'rb').read()
    if not raw.startswith(b'Kaydara FBX Binary'):
        raise EditError('This FBX file is in the text form. Export it again as binary FBX, or as glTF or OBJ.')
    ver = struct.unpack_from('<I', raw, 23)[0]
    big = ver >= 7500

    def read_node(p):
        if big:
            end, nprops, _plen = struct.unpack_from('<QQQ', raw, p)
            p += 24
        else:
            end, nprops, _plen = struct.unpack_from('<III', raw, p)
            p += 12
        nl = raw[p]
        name = raw[p + 1:p + 1 + nl].decode('ascii', 'replace')
        p += 1 + nl
        if end == 0:
            return None, p
        props = []
        for _ in range(nprops):
            t = chr(raw[p])
            p += 1
            if t in 'YCILFD':
                fmt = {'Y': '<h', 'C': '<?', 'I': '<i', 'L': '<q', 'F': '<f', 'D': '<d'}[t]
                props.append(struct.unpack_from(fmt, raw, p)[0])
                p += struct.calcsize(fmt)
            elif t in 'fdlibc':
                n, enc, clen = struct.unpack_from('<III', raw, p)
                p += 12
                data = raw[p:p + clen]
                p += clen
                if enc == 1:
                    data = zlib.decompress(data)
                fmt = {'f': 'f', 'd': 'd', 'l': 'q', 'i': 'i', 'b': '?', 'c': 'B'}[t]
                props.append(list(struct.unpack('<%d%s' % (n, fmt), data[:n * struct.calcsize(fmt)])))
            elif t in 'SR':
                n = struct.unpack_from('<I', raw, p)[0]
                props.append(raw[p + 4:p + 4 + n] if t == 'R' else raw[p + 4:p + 4 + n].decode('utf-8', 'replace'))
                p += 4 + n
            else:
                raise EditError('This FBX file could not be read.')
        kids = []
        while p < end:
            k, p = read_node(p)
            if k is None:
                break
            kids.append(k)
        return {'name': name, 'props': props, 'kids': kids}, end
    top, p = [], 27
    while p < len(raw) - 13:
        n, p = read_node(p)
        if n is None:
            break
        top.append(n)
    find = lambda n, name: next((k for k in n['kids'] if k['name'] == name), None)
    objs = next((n for n in top if n['name'] == 'Objects'), {'kids': []})
    conns = next((n for n in top if n['name'] == 'Connections'), {'kids': []})
    gs = next((n for n in top if n['name'] == 'GlobalSettings'), None)
    settings = {}
    if gs and find(gs, 'Properties70'):
        for pr in find(gs, 'Properties70')['kids']:
            if pr['props']:
                settings[pr['props'][0]] = pr['props'][-1]
    scale_m = float(settings.get('UnitScaleFactor', 1.0)) / 100.0      # FBX units are centimetres
    up_axis = int(settings.get('UpAxis', 1))
    by_id = {}
    for o in objs['kids']:
        if o['props']:
            by_id[o['props'][0]] = o
    links = {}                                   # child -> [parents]
    children = {}
    for c in conns['kids']:
        if len(c['props']) >= 3:
            links.setdefault(c['props'][1], []).append(c['props'][2])
            children.setdefault(c['props'][2], []).append(c['props'][1])

    def props70(o):
        out = {}
        p70 = find(o, 'Properties70')
        for pr in (p70['kids'] if p70 else []):
            if pr['props']:
                out[pr['props'][0]] = pr['props'][4:]
        return out

    def model_matrix(mid):
        M = _I4
        chain = []
        while mid in by_id and by_id[mid]['name'] == 'Model':
            chain.append(mid)
            mid = next((pp for pp in links.get(mid, []) if pp in by_id and by_id[pp]['name'] == 'Model'), None)
        for m in reversed(chain):
            pr = props70(by_id[m])
            t = pr.get('Lcl Translation', [0, 0, 0])
            r = [math.radians(v) for v in pr.get('Lcl Rotation', [0, 0, 0])]
            s = pr.get('Lcl Scaling', [1, 1, 1])
            cx, sx, cy, sy, cz, sz = math.cos(r[0]), math.sin(r[0]), math.cos(r[1]), math.sin(r[1]), math.cos(r[2]), math.sin(r[2])
            Rx = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]]
            Ry = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]]
            Rz = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
            L = _mat4_mul([[1, 0, 0, t[0]], [0, 1, 0, t[1]], [0, 0, 1, t[2]], [0, 0, 0, 1]], _mat4_mul(Rz, _mat4_mul(Ry, Rx)))
            L = _mat4_mul(L, [[s[0], 0, 0, 0], [0, s[1], 0, 0], [0, 0, s[2], 0], [0, 0, 0, 1]])
            M = _mat4_mul(M, L)
        return M

    def picture_of(mat_id):
        for tid in children.get(mat_id, []):
            t = by_id.get(tid)
            if t and t['name'] == 'Texture':
                for key in ('RelativeFilename', 'FileName'):
                    k = find(t, key)
                    if k and k['props']:
                        p = _find_beside(os.path.dirname(path), str(k['props'][0]).replace('\\', '/'))
                        if p:
                            return p
                # the picture may be packed inside the file (Video node with Content)
                for vid in children.get(tid, []):
                    v = by_id.get(vid)
                    c = find(v, 'Content') if v else None
                    if c and c['props'] and isinstance(c['props'][0], bytes) and len(c['props'][0]) > 16:
                        return {'raw': c['props'][0], 'ext': '.png' if c['props'][0][:4] == b'\x89PNG' else '.jpg'}
        return None

    def colour_of(mat_id):
        pr = props70(by_id[mat_id]) if mat_id in by_id else {}
        c = pr.get('DiffuseColor') or pr.get('Diffuse')
        return tuple(max(0.0, min(1.0, float(x))) for x in c[:3]) if c and len(c) >= 3 else (1, 1, 1)
    parts = []
    for gid, g in by_id.items():
        if g['name'] != 'Geometry' or not find(g, 'Vertices'):
            continue
        V = find(g, 'Vertices')['props'][0]
        PV = find(g, 'PolygonVertexIndex')['props'][0]
        verts = [(V[i], V[i + 1], V[i + 2]) for i in range(0, len(V) - 2, 3)]
        uvl = find(g, 'LayerElementUV')
        uv_data = uv_idx = None
        uv_map = ''
        if uvl:
            uv_data = find(uvl, 'UV')['props'][0]
            ui = find(uvl, 'UVIndex')
            uv_idx = ui['props'][0] if ui else None
            mi = find(uvl, 'MappingInformationType')
            uv_map = mi['props'][0] if mi else ''
        mats_l = find(g, 'LayerElementMaterial')
        poly_mat = find(mats_l, 'Materials')['props'][0] if mats_l and find(mats_l, 'Materials') else None
        for mid in links.get(gid, []):
            if mid not in by_id or by_id[mid]['name'] != 'Model':
                continue
            M = model_matrix(mid)
            model_mats = [c for c in children.get(mid, []) if c in by_id and by_id[c]['name'] == 'Material']
            groups_ = {}
            corner, pvi, poly = [], 0, 0
            for k, ix in enumerate(PV):
                last = ix < 0
                vi = ~ix if last else ix
                if uv_data is not None:
                    if uv_map == 'ByPolygonVertex':
                        u = uv_idx[k] if uv_idx is not None else k
                    else:
                        u = uv_idx[vi] if uv_idx is not None else vi
                    uv = (uv_data[2 * u], 1.0 - uv_data[2 * u + 1]) if 0 <= 2 * u + 1 < len(uv_data) else (0.0, 0.0)
                else:
                    uv = None
                corner.append((vi, uv))
                if last:
                    mi_ = poly_mat[poly] if poly_mat and poly < len(poly_mat) else 0
                    g_ = groups_.setdefault(mi_, {'verts': [], 'uvs': [], 'tris': [], 'map': {}})
                    ids = []
                    for vi2, uv2 in corner:
                        key = (vi2, uv2)
                        if key not in g_['map']:
                            g_['map'][key] = len(g_['verts'])
                            g_['verts'].append(_apply_m(M, verts[vi2]))
                            g_['uvs'].append(uv2 or (0.0, 0.0))
                        ids.append(g_['map'][key])
                    for i in range(1, len(ids) - 1):
                        g_['tris'].append((ids[0], ids[i], ids[i + 1]))
                    corner = []
                    poly += 1
            for mi_, g_ in groups_.items():
                mat = model_mats[mi_] if mi_ < len(model_mats) else None
                parts.append({'name': 'part', 'verts': g_['verts'], 'uvs': g_['uvs'] if uv_data is not None else None, 'normals': None,
                              'tris': g_['tris'], 'color': colour_of(mat) if mat else (1, 1, 1),
                              'picture': picture_of(mat) if mat else None})
    for p in parts:
        p['verts'] = [(v[0] * scale_m, v[1] * scale_m, v[2] * scale_m) for v in p['verts']]
        if up_axis == 2:
            p['verts'] = [(v[0], v[2], -v[1]) for v in p['verts']]
    return parts


# ------------------------------------------------------------------ bringing things in
def _to_game(parts, up='y', size=None):
    """From the program's axes and units to the game's: Z up, about 70 units to a metre. Size: how tall
    (in game units) the model should be, or None for "it was made in metres"."""
    def conv(v):
        if up == 'y':
            return (v[0], -v[2], v[1])                # Y up (Blender's export, glTF) -> Z up
        return tuple(v)
    for p in parts:
        p['verts'] = [conv(v) for v in p['verts']]
        if p.get('normals'):
            p['normals'] = [conv(v) for v in p['normals']]
        # OBJ and glTF go round a face's corners anticlockwise seen from outside; Morrowind's
        # models the other way
        p['tris'] = [(a, c, b) for a, b, c in p['tris']]
    allv = [v for p in parts for v in p['verts']]
    if not allv:
        raise EditError('There is nothing to draw in this model (no triangles).')
    lo = [min(v[k] for v in allv) for k in range(3)]
    hi = [max(v[k] for v in allv) for k in range(3)]
    h = max(hi[2] - lo[2], 1e-6)
    k = (size / h) if size else UNITS_PER_METRE
    # stand it on the ground, centred: its middle at the origin, its bottom at height 0
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    for p in parts:
        p['verts'] = [((v[0] - cx) * k, (v[1] - cy) * k, (v[2] - lo[2]) * k) for v in p['verts']]
    return [round((hi[i] - lo[i]) * k, 1) for i in range(3)]


def inspect(path):
    """A quick look at a model before it is brought in: its size as made, so the import window can
    suggest the right scale. {'kind', 'size' (x, y, z in its own units), 'parts', 'pictures'}."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.obj':
        parts = read_obj(path)
        pics = [p['picture'] for p in parts if p.get('picture')]
    elif ext in ('.gltf', '.glb'):
        parts, images = read_gltf(path)
        pics = [i.get('name') for i in images]
    elif ext in ('.dae', '.fbx', '.blend'):
        parts = _read_other(path)
        pics = [p['picture'] if isinstance(p.get('picture'), str) else 'packed picture' for p in parts if p.get('picture')]
    else:
        return {'kind': ext[1:], 'size': None, 'parts': 0, 'pictures': []}
    allv = [v for p in parts for v in p['verts']]
    if not allv:
        raise EditError('There is nothing to draw in this model (no triangles).')
    size = [round(max(v[k] for v in allv) - min(v[k] for v in allv), 3) for k in range(3)]
    out = {'kind': ext[1:], 'size': size, 'parts': len(parts), 'triangles': sum(len(p['tris']) for p in parts),
           'pictures': sorted(set(os.path.basename(p) for p in pics if p))}
    names = list(dict.fromkeys(p['object'] for p in parts if p.get('object')))
    if len(names) > 1:
        # a file with several objects (a kit or a bundle): the window offers to pick one, or each on its own
        objs = []
        for n in names:
            vs = [v for p in parts if p.get('object') == n for v in p['verts']]
            objs.append({'name': n, 'size': [round(max(v[k] for v in vs) - min(v[k] for v in vs), 3) for k in range(3)],
                         'triangles': sum(len(p['tris']) for p in parts if p.get('object') == n)})
        out['objects'] = objs
    return out


def _read_other(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.obj':
        return read_obj(path)
    if ext == '.dae':
        return read_dae(path)
    if ext == '.fbx':
        return read_fbx(path)
    import blendread
    return blendread.read_blend(path)


def _door_pivot(parts):
    """A door turns round its origin: make the model wide across X, its left edge (the hinge) at the
    origin, its middle on Y, standing on the ground."""
    vs = [v for p in parts for v in p['verts']]
    if not vs:
        return
    span = lambda k: max(v[k] for v in vs) - min(v[k] for v in vs)
    if span(1) > span(0):                                  # wide along Y: turn it a quarter round
        for p in parts:
            p['verts'] = [(v[1], -v[0], v[2]) for v in p['verts']]
            if p.get('normals'):
                p['normals'] = [(n[1], -n[0], n[2]) for n in p['normals']]
        vs = [v for p in parts for v in p['verts']]
    x0 = min(v[0] for v in vs)
    ym = (min(v[1] for v in vs) + max(v[1] for v in vs)) / 2
    z0 = min(v[2] for v in vs)
    for p in parts:
        p['verts'] = [(v[0] - x0, v[1] - ym, v[2] - z0) for v in p['verts']]


def _light_settings(s):
    """A lamp's light, checked: colour (r, g, b 0..255), radius, how it flickers, whether it's carried."""
    s = s or {}
    col = s.get('color') or [255, 200, 140]
    try:
        col = [max(0, min(255, int(c))) for c in col[:3]]
    except (TypeError, ValueError):
        col = [255, 200, 140]
    try:
        radius = max(32, min(2048, int(s.get('radius') or 256)))
    except (TypeError, ValueError):
        radius = 256
    flick = s.get('flicker') if s.get('flicker') in ('steady', 'flicker', 'flicker_slow', 'pulse', 'pulse_slow', 'fire') else 'steady'
    return {'color': col, 'radius': radius, 'flicker': flick, 'carry': bool(s.get('carry'))}


DOOR_SOUNDS = {'wood': ('Door Latched One Open', 'Door Latched One Close'), 'creaky': ('Door Creaky Open', 'Door Creaky Close'),
               'heavy': ('Door Heavy Open', 'Door Heavy Close'), 'metal': ('Door Metal Open', 'Door Metal Close'),
               'stone': ('Door Stone Open', 'Door Stone Close'), 'dwemer': ('Dwemer Door Open', 'Dwemer Door Close')}


def import_files(db, paths, name=None, up='y', size=None, kind='static', collision='shape', obj=None, extra=None):
    """Bring in what was dropped: one model (with the files it needs) and/or pictures. Returns the new
    Library entries. Models from other programs become .nif models. obj: for a file of several
    objects, the one to bring in, EACH for every one as its own model, or None for all together."""
    paths = [p for p in paths if os.path.isfile(p)]
    models = [p for p in paths if os.path.splitext(p)[1].lower() in MODELS]
    pictures = [p for p in paths if os.path.splitext(p)[1].lower() in PICTURES]
    sounds = [p for p in paths if os.path.splitext(p)[1].lower() in SOUNDS]
    if not models and not pictures and not sounds:
        raise EditError('Nothing here the Workshop can use: bring in models (.nif, .obj, .fbx, .dae, .gltf, .glb, .blend), '
                        'pictures (.png, .jpg, .tga, .dds, .bmp) or sounds (.wav, .mp3, .ogg, .flac).')
    added, items = [], _index()
    for sp in sounds:
        snd, dest = _copy_sound(db, sp)
        e = {'id': 'snd_' + os.path.splitext(os.path.basename(dest))[0], 'type': 'sound',
             'name': (name if not models and len(sounds) == 1 else None) or _nice(sp),
             'file': 'sound/%s/%s' % (SUB, os.path.basename(dest)), 'sound': snd, 'added': time.time(),
             'from': os.path.basename(sp), 'volume': 0.8, 'reach': (extra or {}).get('reach') if (extra or {}).get('reach') in REACH else 'room'}
        items.append(e)
        added.append(e)
    used_pics = set()
    extra = extra or {}
    light = _light_settings(extra.get('light')) if kind == 'light' else None
    door_sound = extra.get('door_sound') if extra.get('door_sound') in DOOR_SOUNDS else 'wood'

    def one(mp, nm, sz, parts=None):
        e = _import_model(db, mp, nm, up, sz, used_pics, collision, parts=parts, kind=kind, light=light)
        e['kind'] = kind
        if light:
            e['light'] = light
        if kind == 'door':
            e['door_sound'] = door_sound
        items.append(e)
        added.append(e)
    for mp in models:
        ext = os.path.splitext(mp)[1].lower()
        if obj and ext in ('.obj', '.dae', '.fbx', '.blend'):
            parts = _read_other(mp)
            names = list(dict.fromkeys(p.get('object') for p in parts if p.get('object')))
            if obj == EACH and len(names) > 1:
                # a size given for the whole file scales every object alike
                ax = 1 if up == 'y' else 2
                allv = [v[ax] for p in parts for v in p['verts']]
                k = size / max(max(allv) - min(allv), 1e-6) if size and allv else None
                for n in names:
                    sub = [dict(p) for p in parts if p.get('object') == n]
                    hv = [v[ax] for p in sub for v in p['verts']]
                    one(mp, n.strip(), k * max(max(hv) - min(hv), 1e-6) if k and hv else None, sub)
                continue
            if obj != EACH:
                sub = [p for p in parts if p.get('object') == obj]
                if not sub:
                    raise EditError('There is no object called "%s" in %s.' % (obj, os.path.basename(mp)))
                one(mp, name or obj.strip(), size, sub)
                continue
        one(mp, name if len(models) == 1 else None, size)
    for pp in pictures:
        if pp in used_pics:
            continue
        tex, dest = _copy_picture(db, src_path=pp)
        e = {'id': os.path.splitext(os.path.basename(dest))[0], 'name': (name if not models and len(pictures) == 1 else None) or
             _nice(pp), 'type': 'texture', 'file': 'textures/%s/%s' % (SUB, os.path.basename(dest)), 'texture': tex,
             'added': time.time(), 'from': os.path.basename(pp)}
        items.append(e)
        added.append(e)
    _save_index(items)
    return added


def _nice(path):
    return re.sub(r'[_\-]+', ' ', os.path.splitext(os.path.basename(path))[0]).strip().capitalize() or 'Item'


def _import_model(db, path, name, up, size, used_pics, collision='shape', parts=None, kind='static', light=None):
    ext = os.path.splitext(path)[1].lower()
    folder = os.path.join(data_dir(db), 'meshes', SUB)
    os.makedirs(folder, exist_ok=True)
    stem = _free_name(folder, _slug(name or path), '.nif')
    dest = os.path.join(folder, stem + '.nif')
    note = ''
    if ext == '.nif':
        raw = open(path, 'rb').read()
        import nif
        if not nif._blocks(raw):
            raise EditError('"%s" is not a Morrowind model the Workshop can read (it may be from a later game).' % os.path.basename(path))
        # its textures, when they came along or sit beside it, go into the Library too
        mapping = {}
        for t in nifwrite.textures_in(raw):
            src = _find_beside(os.path.dirname(path), t) or _find_beside(os.path.dirname(path), os.path.splitext(t)[0] + '.dds')
            if src and src not in used_pics:
                tex, _d = _copy_picture(db, src_path=src)
                mapping[t.lower().replace('/', '\\')] = tex
                used_pics.add(src)
        if mapping:
            raw, _n = nifwrite.retexture(raw, mapping)
        with open(dest, 'wb') as f:
            f.write(raw)
        dims = None
    else:
        images = []
        if ext in ('.obj', '.dae', '.fbx', '.blend'):
            if parts is None:
                parts = _read_other(path)
            for p in parts:
                if isinstance(p.get('picture'), str):
                    used_pics.add(p['picture'])
        else:
            parts, images = read_gltf(path)
        dims = _to_game(parts, up, size)
        if kind == 'door':
            _door_pivot(parts)
        if light:
            # a lamp looks lit: its parts glow a little in the light's own colour
            for p in parts:
                p['glow'] = tuple(0.35 + 0.5 * c / 255.0 for c in light['color'])
        saved = {}
        for p in parts:
            pic = p.pop('picture', None)
            img = p.pop('image', None)
            if isinstance(pic, dict):
                # a picture packed inside the model file
                key = id(pic)
                if key not in saved:
                    saved[key] = _copy_picture(db, raw=pic['raw'], name=(name or _slug(path)) + '_tex', ext=pic['ext'])
                p['texture'] = saved[key][0]
                p['alpha'] = p.get('alpha') or _picture_alpha(saved[key][1])
            elif pic:
                if pic not in saved:
                    saved[pic] = _copy_picture(db, src_path=pic)
                p['texture'] = saved[pic][0]
                p['alpha'] = p.get('alpha') or _picture_alpha(saved[pic][1])
            elif img is not None and img < len(images):
                im = images[img]
                if img not in saved:
                    if im.get('raw'):
                        saved[img] = _copy_picture(db, raw=im['raw'], name=(name or _slug(path)) + '_tex', ext=im['ext'])
                    elif im.get('path'):
                        saved[img] = _copy_picture(db, src_path=im['path'])
                        used_pics.add(im['path'])
                    else:
                        note = 'Some of its pictures were missing, so parts of it are plain colours.'
                if img in saved:
                    p['texture'] = saved[img][0]
                    p['alpha'] = p.get('alpha') or _picture_alpha(saved[img][1])
            if p.get('opacity', 1.0) < 0.99:
                p['alpha'] = True
        with open(dest, 'wb') as f:
            f.write(nifwrite.write_nif(parts, stem, collision if collision in ('shape', 'box', 'none') else 'shape'))
    rel = 'meshes/%s/%s.nif' % (SUB, stem)
    _register(db, rel, dest)
    b = db.meshes.bounds('%s/%s.nif' % (SUB, stem))
    return {'id': stem, 'name': name or _nice(path), 'type': 'model', 'file': rel, 'model': '%s\\%s.nif' % (SUB, stem),
            'size': dims or ([round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])] if b else None),
            'added': time.time(), 'from': os.path.basename(path), 'note': note}


# ------------------------------------------------------------------ a drop of files from the page
INCOMING = os.path.join(APP_DIR, 'library_incoming')


def _batch_dir(batch):
    if not re.fullmatch(r'[a-z0-9]{6,32}', batch or ''):
        raise EditError('Bad upload.')
    return os.path.join(INCOMING, batch)


def receive(batch, name, raw):
    """One file of a drop (a model and the files it needs come together)."""
    d = _batch_dir(batch)
    os.makedirs(d, exist_ok=True)
    # keep sub-folders a model's textures may sit in (textures/wood.png), but never outside the drop
    parts = [p for p in re.split(r'[\\/]+', name or '') if p and p not in ('.', '..')]
    if not parts:
        raise EditError('A file without a name.')
    dest = os.path.join(d, *parts)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(raw)
    return {'ok': True, 'size': len(raw)}


def _batch_files(batch):
    d = _batch_dir(batch)
    out = []
    for root, _dirs, files in os.walk(d):
        for fn in files:
            out.append(os.path.join(root, fn))
    return out


def inspect_batch(batch):
    files = _batch_files(batch)
    models = [p for p in files if os.path.splitext(p)[1].lower() in MODELS]
    pics = [p for p in files if os.path.splitext(p)[1].lower() in PICTURES]
    snds = [p for p in files if os.path.splitext(p)[1].lower() in SOUNDS]
    other = [os.path.basename(p) for p in files if p not in models and p not in pics and p not in snds and
             os.path.splitext(p)[1].lower() not in ('.mtl', '.bin')]
    info = {'models': [os.path.basename(p) for p in models], 'pictures': [os.path.basename(p) for p in pics],
            'sounds': [os.path.basename(p) for p in snds], 'other': other}
    if len(models) == 1:
        info['model'] = inspect(models[0])
        # suggested size: made in metres (a door is about 2 m) or in game units already
        s = info['model'].get('size')
        if s:
            up = 'y' if info['model']['kind'] in ('dae', 'fbx', 'gltf', 'glb', 'blend') or s[1] >= s[2] * 0.2 else 'z'
            h = s[1] if up == 'y' else s[2]
            info['up'] = up
            info['height_as_metres'] = round(h * UNITS_PER_METRE)
            info['height_as_is'] = round(h, 2) if h < 10 else round(h)
            info['looks_like'] = 'metres' if h < 40 else 'units'
    return info


def import_batch(db, batch, name=None, up='y', size=None, kind='static', collision='shape', obj=None, extra=None):
    try:
        size = float(size) if size not in (None, '') else None
        if size is not None and not 1 <= size <= 50000:
            raise EditError('Give a height between 1 and 50000 game units (a person is about 128).')
        return import_files(db, _batch_files(batch), (name or '').strip() or None, 'z' if up == 'z' else 'y', size,
                            kind if kind in KINDS else 'static', collision, obj or None, extra)
    finally:
        shutil.rmtree(_batch_dir(batch), ignore_errors=True)


# ------------------------------------------------------------------ using them in a mod
KINDS = {'static': 'STAT', 'activator': 'ACTI', 'container': 'CONT', 'item': 'MISC', 'door': 'DOOR', 'light': 'LIGH'}
TAG_WORDS = {'STAT': 'scenery', 'ACTI': 'activator', 'CONT': 'container', 'MISC': 'item', 'DOOR': 'door', 'LIGH': 'light'}
LIGHT_FLAGS = {'steady': 0, 'flicker': 0x08, 'flicker_slow': 0x40, 'pulse': 0x80, 'pulse_slow': 0x100, 'fire': 0x10 | 0x08}


def make_record(db, entry_id, kind=None, name=None, commit=True):
    """A record in your mod for a Library model, so it can be placed: a static (part of the scenery),
    an activator, a container or a small item. Returns {'id', 'type', 'i'}. Reuses one made before."""
    editing._require_project(db)
    e = next((i for i in _index() if i['id'] == entry_id), None)
    if e and e.get('type') == 'sound':
        return make_sound_source(db, entry_id, commit)          # a sound: placed as an unseen source of it
    if not e or e.get('type') != 'model':
        raise EditError('That model is not in the Library.')
    kind = kind or e.get('kind') or 'static'
    tag = KINDS.get(kind, 'STAT')
    import create
    rid = e.get('records', {}).get(tag)
    if rid and db.resolve_id(rid) is not None:
        return {'id': rid, 'type': tag, 'i': db.resolve_id(rid)}
    rid = create.suggest_id(db, 'lib', e['id'])
    label = (name or e.get('name') or e['id'])[:31]
    subs = [('NAME', zs(rid)), ('MODL', zs(e['model']))]
    if tag in ('ACTI', 'CONT', 'MISC', 'DOOR'):
        subs.append(('FNAM', zs(label)))
    if tag == 'CONT':
        subs += [('CNDT', struct.pack('<f', 100.0)), ('FLAG', struct.pack('<I', 8))]
    if tag == 'MISC':
        subs.append(('MCDT', struct.pack('<fii', 1.0, 5, 0)))
        if e.get('icon'):
            subs.append(('ITEX', zs(e['icon'])))
    if tag == 'DOOR':
        # opening and closing sounds (when the game has them)
        for sub, snd in zip(('SNAM', 'ANAM'), DOOR_SOUNDS.get(e.get('door_sound') or 'wood', DOOR_SOUNDS['wood'])):
            if db.resolve_id(snd) is not None:
                subs.append((sub, zs(snd)))
    if tag == 'LIGH':
        li = _light_settings(e.get('light'))
        if li['carry']:
            subs.append(('FNAM', zs(label)))
            if e.get('icon'):
                subs.append(('ITEX', zs(e['icon'])))
        flags = 0x01 | LIGHT_FLAGS[li['flicker']] | (0x02 if li['carry'] else 0)       # 0x01: lights things round it
        subs.append(('LHDT', struct.pack('<fiiiBBBBI', 1.0 if li['carry'] else 0.0, 5 if li['carry'] else 0,
                                         600 if li['carry'] else -1, li['radius'], li['color'][0], li['color'][1],
                                         li['color'][2], 0, flags)))
        if li['flicker'] == 'fire' and db.resolve_id('Fire') is not None:
            subs.append(('SNAM', zs('Fire')))
    db.project.set_record(tag, rid.lower(), 0, join_subs(subs), created=True)
    if not commit:
        db.sync_project()                    # (part of a bigger change, committed by the caller)
    else:
        editing.commit(db, 'Made "%s" (%s) from the Library model %s' % (label, TAG_WORDS[tag], e['model']))
    items = _index()
    for it in items:
        if it['id'] == entry_id:
            it.setdefault('records', {})[tag] = rid
    _save_index(items)
    return {'id': rid, 'type': tag, 'i': db.resolve_id(rid)}


def retexture_record(db, rec_i, mapping, new_name=None):
    """A new object like an existing one, with some of its textures swapped for Library pictures (or
    any texture in the game): mapping {texture the model uses: new texture name}. The model is copied
    into the Library with the new names; the record is copied with its new model. Returns the new id."""
    editing._require_project(db)
    r = db.recs[rec_i]
    from esm import iter_subrecords, zstr
    _t, flags, data = db.files[r[3]].record_at(r[4])
    model = None
    for t, d in iter_subrecords(data):
        if t == 'MODL':
            model = zstr(d)
    if not model:
        raise EditError('This object has no model to retexture.')
    raw = db.meshes.read('meshes/' + model.lower().replace('\\', '/'))
    if not raw:
        raise EditError('Could not find this object\'s model (%s).' % model)
    m = {k.lower().replace('/', '\\'): v for k, v in mapping.items() if v}
    if not m:
        raise EditError('Choose a new texture for at least one of its pictures.')
    new_raw, n = nifwrite.retexture(raw, m)
    if not n:
        raise EditError('None of those textures are in this model.')
    folder = os.path.join(data_dir(db), 'meshes', SUB)
    os.makedirs(folder, exist_ok=True)
    stem = _free_name(folder, _slug(os.path.basename(model)) + '_re', '.nif')
    dest = os.path.join(folder, stem + '.nif')
    with open(dest, 'wb') as f:
        f.write(new_raw)
    _register(db, 'meshes/%s/%s.nif' % (SUB, stem), dest)
    import create
    new_id = create.suggest_id(db, '', (new_name or r[1] + '_re'))[:31]
    subs = []
    for t, d in iter_subrecords(data):
        d = bytes(d)
        if t == 'NAME' and not subs:
            d = zs(new_id)
        elif t == 'MODL':
            d = zs('%s\\%s.nif' % (SUB, stem))
        elif t == 'FNAM' and new_name and r[0] != 'SOUN':
            d = zs(new_name[:31])
        subs.append((t, d))
    db.project.set_record(r[0], new_id.lower(), flags & ~0x20, join_subs(subs), created=True)
    editing.commit(db, 'Made "%s", a retextured copy of "%s"' % (new_id, r[1]))
    items = _index()
    items.append({'id': stem, 'name': new_name or (r[2] or r[1]) + ' (retextured)', 'type': 'model', 'file': 'meshes/%s/%s.nif' % (SUB, stem),
                  'model': '%s\\%s.nif' % (SUB, stem), 'added': time.time(), 'from': 'retexture of ' + r[1],
                  'records': {r[0]: new_id}, 'kind': {'STAT': 'static', 'ACTI': 'activator', 'CONT': 'container', 'MISC': 'item'}.get(r[0], 'static')})
    _save_index(items)
    return {'id': new_id, 'type': r[0], 'i': db.resolve_id(new_id)}


def model_textures(db, rec_i):
    """The textures an object's model uses, for the retexture window."""
    r = db.recs[rec_i]
    from esm import iter_subrecords, zstr
    # (a record number the page kept from before an Undo can name a version of your mod's record that is
    # gone: the one in use now, by its ID; the crawl test's KeyError on Retexture after Undos)
    if rec_i in db.dead:
        ri = db.resolve_id(r[1])
        if ri is None:
            raise EditError('"%s" is no longer in your load order.' % r[1])
        r = db.recs[ri]
    try:
        _t, _f, data = db.files[r[3]].record_at(r[4])
    except KeyError:
        ri = db.resolve_id(r[1])
        if ri is None or ri == rec_i:
            raise EditError('"%s" changed meanwhile: look at it again.' % r[1])
        r = db.recs[ri]
        _t, _f, data = db.files[r[3]].record_at(r[4])
    model = next((zstr(d) for t, d in iter_subrecords(data) if t == 'MODL'), None)
    raw = db.meshes.read('meshes/' + model.lower().replace('\\', '/')) if model else None
    if not raw:
        return {'model': model, 'textures': []}
    return {'model': model, 'textures': [{'name': t, 'path': db.meshes.texture_path(t)} for t in nifwrite.textures_in(raw)]}


def save_icon(db, entry_id, raw):
    """An inventory icon for a Library model (a picture of it, made by the page): kept in icons\\wslib,
    and given to the items your mod already made from it."""
    e = entry(entry_id)
    if not e or e.get('type') != 'model':
        raise EditError('That model is not in the Library.')
    if not raw.startswith(b'\x89PNG'):
        raise EditError('The icon picture could not be made.')
    folder = os.path.join(data_dir(db), 'icons', SUB)
    os.makedirs(folder, exist_ok=True)
    name = e['id'] + '.png'
    with open(os.path.join(folder, name), 'wb') as f:
        f.write(raw)
    _register(db, 'icons/%s/%s' % (SUB, name), os.path.join(folder, name))
    icon = '%s\\%s' % (SUB, name)
    items = _index()
    for it in items:
        if it['id'] == entry_id:
            it['icon'] = icon
    _save_index(items)
    # items already made from it get the icon too
    from esm import iter_subrecords
    p = db.project
    changed = 0
    for tag in ('MISC', 'LIGH'):
        if tag == 'LIGH' and not _light_settings(e.get('light'))['carry']:
            continue                           # (only lights you carry show in the inventory)
        rid = (e.get('records') or {}).get(tag)
        rec = p.records.get('%s|%s' % (tag, (rid or '').lower())) if p and rid else None
        if not rec:
            continue
        from project import unb64
        subs = [(t, bytes(d)) for t, d in iter_subrecords(unb64(rec['data'])) if t != 'ITEX']
        subs.append(('ITEX', zs(icon)))
        p.set_record(tag, rec['key'], rec['flags'], join_subs(subs))
        changed += 1
    if changed:
        editing.commit(db, 'Gave %s an inventory icon' % (e.get('name') or e['id']))
    return {'icon': icon, 'file': 'icons/%s/%s' % (SUB, name)}


ICON_SIZES = {'effect': (32, 64), 'item': (64,)}     # (twice the game's own 16/32 and 32: OpenMW scales an icon to its place, so they stay sharp)


def make_icon(db, name, kind, pictures, source=''):
    """Icons the game's way from a picture (made into PNGs of the right sizes by the page): for a magic
    effect a small icon and its large twin, named with "b_" in front as the game looks for it; for an
    item one inventory icon. Kept in icons\\wslib and in the Library. Returns the path an Icon field takes
    (wslib\\name.png: the small one, for an effect)."""
    if kind not in ICON_SIZES:
        raise EditError('Unknown kind of icon.')
    raws = []
    for p in pictures or []:
        b = p.split(',', 1)[1] if isinstance(p, str) and p.startswith('data:') else p
        try:
            raw = base64.b64decode(b)
        except Exception:
            raw = b''
        if not raw.startswith(b'\x89PNG'):
            raise EditError('The icon picture could not be made.')
        raws.append(raw)
    if len(raws) != len(ICON_SIZES[kind]):
        raise EditError('The icon needs %d picture%s.' % (len(ICON_SIZES[kind]), '' if len(ICON_SIZES[kind]) == 1 else 's'))
    folder = os.path.join(data_dir(db), 'icons', SUB)
    os.makedirs(folder, exist_ok=True)
    stem = _slug(name or source or 'icon')
    stem = _free_name(folder, stem, '.png')
    while kind == 'effect' and os.path.exists(os.path.join(folder, 'b_' + stem + '.png')):
        stem = _free_name(folder, stem + '_1', '.png')
    files = [stem + '.png'] + (['b_' + stem + '.png'] if kind == 'effect' else [])
    for fn, raw in zip(files, raws):
        full = os.path.join(folder, fn)
        with open(full, 'wb') as f:
            f.write(raw)
        _register(db, 'icons/%s/%s' % (SUB, fn), full)
    items = _index()
    items.append({'id': 'icon_' + stem, 'name': (name or stem) + (' (effect icon)' if kind == 'effect' else ' (icon)'), 'type': 'icon',
                  'file': 'icons/%s/%s' % (SUB, files[0]), 'files': ['icons/%s/%s' % (SUB, f) for f in files],
                  'icon_kind': kind, 'from': source, 'added': time.time()})
    _save_index(items)
    return {'icon': '%s\\%s' % (SUB, files[0]), 'files': ['icons/%s/%s' % (SUB, f) for f in files]}


def entry_for_record(rid, db=None):
    """The Library entry a record was made from (by its id, or by the Library model it uses), or None."""
    low = (rid or '').lower()
    idx = _index()
    for e in idx:
        if any(v.lower() == low for v in (e.get('records') or {}).values()):
            return e
    if db is not None:
        ri = db.resolve_id(rid or '')
        if ri is not None:
            from esm import iter_subrecords, zstr
            r = db.recs[ri]
            _t, _f, data = db.files[r[3]].record_at(r[4])
            model = next((zstr(d) for t, d in iter_subrecords(data) if t == 'MODL'), '').lower().replace('/', '\\')
            if model.startswith(SUB + '\\'):
                return next((e for e in idx if (e.get('model') or '').lower() == model), None)
    return None


def entry(entry_id):
    return next((i for i in _index() if i['id'] == entry_id), None)


TAG_KIND = {'STAT': 'static', 'ACTI': 'activator', 'CONT': 'container', 'MISC': 'item', 'DOOR': 'door', 'LIGH': 'light'}


def resolve(db, rid, lib, typ=None):
    """The id to place for an object that may be one of your Library models: the record if your mod
    has it, or a new one made from the Library entry (part of the caller's change). None if neither."""
    if db.resolve_id(rid or '') is not None:
        return rid
    if lib and entry(lib):
        return make_record(db, lib, TAG_KIND.get(typ or '', None), commit=False)['id']
    return None


def remove(db, entry_id):
    """Take something out of the Library list. Its file stays (a mod may still use it)."""
    _save_index([i for i in _index() if i['id'] != entry_id])
