"""Models and textures, looked at and changed: the Workshop's asset window.

For an object's record (or a model file), what its model is (where the file comes from: a game archive,
a data folder, your mod or your Library; its shapes, triangles and what else is in it: collision,
animation, a skeleton, particles), the textures it draws with (file, format, size, where it comes from,
and which are missing), and what uses it. A texture can then be changed:

- everywhere: a copy of the game's file is put in your mod's own folder under the same name, so the
  game draws your copy wherever the texture is used (loose files win over the archives);
- for this object only: a copy under a new name, and a new record of the object drawn with it (as
  Retexture makes one), so nothing else changes.

Either way the copy is opened in your picture editor (the one Windows opens the file with, or the one
chosen in settings), and the 3D view draws it again whenever it is saved."""
import os
import re
import struct
import subprocess

import editing
import library
import nif
import nifwrite
from editing import EditError
from project import load_settings

KINDS = {
    b'NiTriShape': 'shape', b'NiTriStrips': 'shape', b'RootCollisionNode': 'collision', b'NiKeyframeController': 'animation',
    b'NiKeyframeData': 'animation', b'NiTextKeyExtraData': 'animation', b'NiSkinInstance': 'skin', b'NiParticleSystemController': 'particles',
    b'NiBSParticleNode': 'particles', b'NiAutoNormalParticles': 'particles', b'NiRotatingParticles': 'particles', b'NiLight': 'light',
    b'NiPointLight': 'light', b'NiFlipController': 'flipbook', b'NiUVController': 'scrolling texture', b'NiVisController': 'animation',
    b'NiGeomMorpherController': 'morphs', b'NiBillboardNode': 'billboard', b'NiSwitchNode': 'switch',
}


def _source(db, rel):
    """Where a data file comes from, in words: ('mod'|'library'|'folder'|'archive'|None, label, full path or None)."""
    rel = rel.lower().replace('\\', '/')
    full = db.meshes.loose.get(rel)
    if full:
        mine = os.path.normcase(os.path.abspath(library.data_dir(db)))
        f = os.path.normcase(os.path.abspath(full))
        if '/wslib/' in rel:
            return 'library', 'your Library', full
        if f.startswith(mine + os.sep):
            return 'mod', "your mod's folder", full
        # (the data folder it is in, by its last two folder names: "Data Files", "TR_Data/...")
        root = full[:-len(rel)].rstrip('\\/') if full.lower().replace('\\', '/').endswith(rel) else os.path.dirname(full)
        return 'folder', os.path.basename(root) or root, full
    if rel in db.meshes.packed:
        return 'archive', os.path.basename(db.meshes.packed[rel][0]), None
    return None, 'missing', None


def picture_info(raw):
    """(format, width, height, mip levels) of a DDS, TGA, PNG, BMP or JPEG file's bytes, as far as read."""
    if not raw:
        return None
    if raw[:4] == b'DDS ' and len(raw) >= 128:
        h, w = struct.unpack_from('<II', raw, 12)
        mips = struct.unpack_from('<I', raw, 28)[0] or 1
        pf_flags, four = struct.unpack_from('<I4s', raw, 80)
        fmt = four.decode('ascii', 'replace').strip('\0') if pf_flags & 0x4 else ('RGBA' if struct.unpack_from('<I', raw, 88)[0] == 32 else 'RGB')
        return {'format': 'DDS ' + fmt, 'w': w, 'h': h, 'mips': mips}
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack_from('>II', raw, 16)
        return {'format': 'PNG', 'w': w, 'h': h, 'mips': 1}
    if raw[:2] == b'BM':
        w, h = struct.unpack_from('<ii', raw, 18)
        return {'format': 'BMP', 'w': w, 'h': abs(h), 'mips': 1}
    if raw[:2] == b'\xff\xd8':
        return {'format': 'JPEG', 'w': None, 'h': None, 'mips': 1}
    if len(raw) >= 18 and raw[2] in (1, 2, 3, 9, 10, 11):
        w, h = struct.unpack_from('<HH', raw, 12)
        return {'format': 'TGA', 'w': w, 'h': h, 'mips': 1}
    return None


def model_info(db, model):
    """What's in a model file (path as records give it, under meshes/)."""
    rel = 'meshes/' + model.lower().replace('\\', '/')
    raw = db.meshes.read(rel)
    where, label, full = _source(db, rel)
    out = {'model': model, 'path': rel, 'from': where, 'from_label': label, 'file': full, 'bytes': len(raw) if raw else 0}
    if not raw:
        return dict(out, missing=True)
    head = raw[:raw.find(b'\n')] if b'\n' in raw[:64] else raw[:40]
    out['version'] = head.decode('ascii', 'replace').replace('NetImmerse File Format, ', '')
    blocks = nif._blocks(raw) or []
    have = {}
    for typ, _p in blocks:
        k = KINDS.get(typ)
        if k:
            have[k] = have.get(k, 0) + 1
    out['blocks'] = len(blocks)
    out['has'] = have
    shapes = nif.mesh_from_nif(raw) or []
    out['shapes'] = len(shapes)
    out['vertices'] = sum(len(s['p']) // 3 for s in shapes)
    out['triangles'] = sum(len(s['i']) // 3 for s in shapes)
    b = nif.bounds_from_nif(raw)
    out['size'] = [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])] if b else None
    out['textures'] = textures_of(db, raw)
    return out


def textures_of(db, raw):
    """The textures a model draws with: as the model names it, the file the game finds, and what it is."""
    out = []
    for name in nifwrite.textures_in(raw):
        path = db.meshes.texture_path(name)
        t = {'name': name, 'path': path}
        if path:
            data = db.meshes.read(path)
            where, label, full = _source(db, path)
            t.update(picture_info(data) or {}, bytes=len(data or b''), **{'from': where, 'from_label': label, 'file': full})
        else:
            t['missing'] = True
        out.append(t)
    return out


def uses(db, model):
    """Records drawn with this model (the versions in force), and in how many places they are placed."""
    low = model.lower().replace('/', '\\')
    recs, places = [], set()
    for ri, r in enumerate(db.recs):
        if r is None or not r[5] or not db.winner[ri] or ri in db.dead:
            continue
        if r[5].lower().replace('/', '\\') == low:
            recs.append({'id': r[1], 'type': r[0], 'name': r[2] or ''})
            places.update(db.used_in.get(r[1].lower(), ()))
    return {'records': recs[:60], 'n_records': len(recs), 'places': len(places)}


def for_record(db, rec_i):
    r = db.recs[rec_i]
    if r is None or not r[5]:
        raise EditError('That has no model.')
    out = model_info(db, r[5])
    out.update(uses(db, r[5]), id=r[1], type=r[0], name=r[2] or '')
    # (moves: keyframes in the model, or a creature's x-model and .kf beside it; people come later)
    import nifanim
    f = nifanim.files_for(db, r[5])
    out['animated'] = r[0] != 'NPC_' and bool(f['kf'] or (out.get('has') or {}).get('animation'))
    out['anim_files'] = f
    return out


# ----- thumbnails: browsers draw no DDS or TGA, so the window's pictures are decoded here --------------
def _c565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _dxt(raw, p, w, h, kind):
    """RGBA rows of a DXT1/3/5 image of w x h at p."""
    px = bytearray(w * h * 4)
    bs = 8 if kind == 'DXT1' else 16
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            if p + bs > len(raw):
                break
            alpha = None
            q = p
            if kind == 'DXT3':
                a = int.from_bytes(raw[q:q + 8], 'little')
                alpha = [((a >> (4 * i)) & 15) * 17 for i in range(16)]
                q += 8
            elif kind == 'DXT5':
                a0, a1 = raw[q], raw[q + 1]
                bits = int.from_bytes(raw[q + 2:q + 8], 'little')
                if a0 > a1:
                    pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
                else:
                    pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
                alpha = [pal[(bits >> (3 * i)) & 7] for i in range(16)]
                q += 8
            c0, c1, idx = struct.unpack_from('<HHI', raw, q)
            r0, r1 = _c565(c0), _c565(c1)
            if c0 > c1 or kind != 'DXT1':
                pal = [r0 + (255,), r1 + (255,), tuple((2 * a + b) // 3 for a, b in zip(r0, r1)) + (255,), tuple((a + 2 * b) // 3 for a, b in zip(r0, r1)) + (255,)]
            else:
                pal = [r0 + (255,), r1 + (255,), tuple((a + b) // 2 for a, b in zip(r0, r1)) + (255,), (0, 0, 0, 0)]
            for i in range(16):
                x, y = bx + (i & 3), by + (i >> 2)
                if x < w and y < h:
                    c = pal[(idx >> (2 * i)) & 3]
                    o = (y * w + x) * 4
                    px[o:o + 4] = bytes((c[0], c[1], c[2], alpha[i] if alpha else c[3]))
            p += bs
    return px


def _decode(raw, want=96):
    """(w, h, RGBA bytes) of a DDS (DXT1/3/5 or plain 24/32 bit) or TGA picture, at the smallest mip level at
    least want across; None for what this doesn't read."""
    if raw[:4] == b'DDS ' and len(raw) >= 128:
        h, w = struct.unpack_from('<II', raw, 12)
        mips = struct.unpack_from('<I', raw, 28)[0] or 1
        pf_flags, four, bits = struct.unpack_from('<I4sI', raw, 80)
        kind = four.decode('ascii', 'replace') if pf_flags & 0x4 else ('RGBA' if bits == 32 else 'RGB' if bits == 24 else None)
        if kind not in ('DXT1', 'DXT3', 'DXT5', 'RGBA', 'RGB'):
            return None
        p = 128
        for _lvl in range(mips):
            if kind.startswith('DXT'):
                size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if kind == 'DXT1' else 16)
            else:
                size = w * h * (bits // 8)
            if max(w, h) // 2 < want or _lvl == mips - 1:
                break
            p += size
            w, h = max(1, w // 2), max(1, h // 2)
        if kind.startswith('DXT'):
            return w, h, _dxt(raw, p, w, h, kind)
        n = bits // 8
        px = bytearray(w * h * 4)
        for i in range(w * h):
            b, g, r = raw[p + i * n:p + i * n + 3]
            px[i * 4:i * 4 + 4] = bytes((r, g, b, raw[p + i * n + 3] if n == 4 else 255))
        return w, h, px
    if len(raw) >= 18 and raw[2] in (2, 10) and raw[16] in (24, 32):
        idl, w, h, bits, desc = raw[0], struct.unpack_from('<H', raw, 12)[0], struct.unpack_from('<H', raw, 14)[0], raw[16], raw[17]
        n, p, px, i = bits // 8, 18 + idl, bytearray(w * h * 4), 0

        def put(k, b, g, r, a):
            x, y = k % w, k // w
            if not desc & 0x20:
                y = h - 1 - y                           # (bottom-up rows, the usual)
            px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, a))
        while i < w * h and p < len(raw):
            if raw[2] == 2:
                c = raw[p:p + n]; p += n
                put(i, c[0], c[1], c[2], c[3] if n == 4 else 255); i += 1
            else:
                hdr = raw[p]; p += 1
                cnt = (hdr & 127) + 1
                if hdr & 128:
                    c = raw[p:p + n]; p += n
                    for _ in range(cnt):
                        if i < w * h:
                            put(i, c[0], c[1], c[2], c[3] if n == 4 else 255); i += 1
                else:
                    for _ in range(cnt):
                        c = raw[p:p + n]; p += n
                        if i < w * h:
                            put(i, c[0], c[1], c[2], c[3] if n == 4 else 255); i += 1
        # (down to about want across, by skipping pixels)
        step = max(1, max(w, h) // want)
        if step > 1:
            w2, h2 = (w + step - 1) // step, (h + step - 1) // step
            small = bytearray(w2 * h2 * 4)
            for y in range(h2):
                for x in range(w2):
                    o = ((y * step) * w + x * step) * 4
                    small[(y * w2 + x) * 4:(y * w2 + x) * 4 + 4] = px[o:o + 4]
            return w2, h2, small
        return w, h, px
    return None


def _png(w, h, px):
    import zlib
    rows = b''.join(b'\0' + bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b'')


def _png_pixels(raw):
    """(w, h, RGBA bytes) of an 8-bit RGB or RGBA PNG (what Blender and this module write), else None."""
    import zlib
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    p, idat, w = 8, b'', None
    while p + 8 <= len(raw):
        n, typ = struct.unpack_from('>I4s', raw, p)
        body = raw[p + 8:p + 8 + n]
        if typ == b'IHDR':
            w, h, depth, ctype, _c, _f, inter = struct.unpack('>IIBBBBB', body)
            if depth != 8 or ctype not in (2, 6) or inter:
                return None
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        p += 12 + n
    if w is None:
        return None
    bpp = 4 if ctype == 6 else 3
    data, stride = zlib.decompress(idat), w * bpp
    out, prev, q = bytearray(w * h * 4), bytearray(stride), 0
    for y in range(h):
        f = data[q]; row = bytearray(data[q + 1:q + 1 + stride]); q += 1 + stride
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                row[i] = (row[i] + a) & 255
            elif f == 2:
                row[i] = (row[i] + b) & 255
            elif f == 3:
                row[i] = (row[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        for x in range(w):
            o = y * w * 4 + x * 4
            out[o:o + 3] = row[x * bpp:x * bpp + 3]
            out[o + 3] = row[x * bpp + 3] if bpp == 4 else 255
        prev = row
    return w, h, out


def _pixel_key(raw):
    """A fingerprint of a picture's pixels (the same picture saved again by another program keeps it)."""
    import hashlib
    d = _png_pixels(raw)
    return hashlib.sha1(struct.pack('<II', d[0], d[1]) + bytes(d[2])).hexdigest() if d else None


_THUMBS = {}


def thumb(db, path, want=96):
    """A small PNG of a texture or icon for the asset window and the Library's cards (PNG, JPEG and BMP files as
    they are), about want across, or None."""
    path = (path or '').lower().replace('\\', '/')
    if not path.startswith(('textures/', 'icons/')) or '..' in path:
        return None
    raw = db.meshes.read(path)
    if raw is None:
        return None
    want = max(32, min(512, int(want or 96)))
    key = (path, len(raw), hash(raw[:64]), hash(raw[-64:]), want)
    if key in _THUMBS:
        return _THUMBS[key]
    if raw[:8] == b'\x89PNG\r\n\x1a\n' or raw[:2] in (b'\xff\xd8', b'BM'):
        out = (raw, 'image/png' if raw[:4] == b'\x89PNG' else 'image/jpeg' if raw[:2] == b'\xff\xd8' else 'image/bmp')
    else:
        d = _decode(raw, want)
        out = (_png(*d), 'image/png') if d else None
    if len(_THUMBS) > 400:
        _THUMBS.clear()
    _THUMBS[key] = out
    return out


# ----- changing a texture ---------------------------------------------------------------------------
# (picture editors where they install themselves, for the window's list: GIMP, Paint.NET, Krita, Photoshop,
# Affinity on Windows; GIMP, Krita, Pinta, KolourPaint on Linux: osplat.picture_editors)
def editors():
    """The picture editors found on this PC, and the one chosen: {'found': [{'name', 'exe'}], 'chosen': exe or ''}."""
    import osplat
    found, seen = [], set()
    for name, exe in osplat.picture_editors():
        low = os.path.basename(exe).lower()
        if 'console' in low or low in seen:
            continue                                     # (gimp-console-2.10.exe: no window)
        seen.add(low)
        found.append({'name': name, 'exe': exe})
    return {'found': found, 'chosen': _editor()}


def _editor():
    s = load_settings() or {}
    return (s.get('image_editor') or '').strip()


def _open(path):
    """The file in the chosen picture editor, or in whatever the computer opens it with."""
    import osplat
    exe = _editor()
    if exe and os.path.isfile(exe):
        if osplat.WINDOWS:
            subprocess.Popen([exe, path])
        else:
            osplat.detached([exe, path])
        return exe
    osplat.open_path(path, edit=True)
    return None


def edit_texture(db, path, how='everywhere', rec_i=None, open_it=True):
    """A copy of a texture to change. how 'everywhere': the game's file copied into the mod's folder under
    the same name (an override). how 'own': a copy under a new name and a new record of rec_i drawn with
    it. Returns {'file', 'path', 'id' (own), 'stamp'}."""
    editing._require_project(db)
    path = (path or '').lower().replace('\\', '/')
    if not path.startswith('textures/') or '..' in path:
        raise EditError('That is not a texture.')
    raw = db.meshes.read(path)
    if raw is None:
        raise EditError('That texture is missing, so there is nothing to copy.')
    base = library.data_dir(db)
    out = {}
    if how == 'own':
        if rec_i is None:
            raise EditError('Pick the object to give its own copy to.')
        r = db.recs[int(rec_i)]
        stem, ext = os.path.splitext(os.path.basename(path))
        slug = re.sub(r'[^a-z0-9_]+', '_', (r[1] or 'obj').lower()).strip('_')[:24] or 'obj'
        folder = os.path.join(base, 'textures', library.SUB)
        os.makedirs(folder, exist_ok=True)
        fname = library._free_name(folder, '%s_%s' % (stem, slug), ext) + ext
        full = os.path.join(folder, fname)
        with open(full, 'wb') as f:
            f.write(raw)
        rel = 'textures/%s/%s' % (library.SUB, fname)
        library._register(db, rel, full)
        # (the record copy, drawn with the copy: every texture name the model gives that finds this file)
        name_in_model = None
        model_raw = db.meshes.read('meshes/' + (r[5] or '').lower().replace('\\', '/'))
        for t in nifwrite.textures_in(model_raw or b''):
            if db.meshes.texture_path(t) == path:
                name_in_model = t
        if not name_in_model:
            raise EditError("The object's model doesn't draw with that texture.")
        made = library.retexture_record(db, int(rec_i), {name_in_model: '%s\\%s' % (library.SUB, fname)}, (r[2] or r[1]) + ' (own texture)')
        out.update(id=made.get('id'), type=made.get('type'))
    else:
        full = os.path.join(base, *path.split('/'))
        if not os.path.exists(full):
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as f:
                f.write(raw)
        rel = path
        prev = db.meshes.loose.get(rel)
        if prev and os.path.normcase(os.path.abspath(prev)) != os.path.normcase(os.path.abspath(full)):
            _COVERED[rel] = prev                     # (a loose file of another folder this copy now covers)
        library._register(db, rel, full)
    out.update(file=full, path=rel, stamp=stamp(full))
    if open_it:
        out['editor'] = _open(full)
    return out


def stamp(full):
    """When the file last changed, to notice a save in the picture editor."""
    try:
        return os.path.getmtime(full)
    except OSError:
        return None


def give_back(db, path):
    """Take your copy of a game texture or model out of your mod's folder (to the Recycle Bin when it can),
    so the game draws its own again."""
    path = (path or '').lower().replace('\\', '/')
    where, _label, full = _source(db, path)
    if where != 'mod' or not full or not path.startswith(('textures/', 'meshes/')):
        raise EditError("That isn't one of your mod's copies.")
    db.meshes.cache.pop(path, None)
    import modfiles
    try:
        modfiles._recycle([full])
    except Exception:
        os.remove(full)
    # (the game's own again: the loose file this copy covered, else the archive's)
    if path in _COVERED:
        db.meshes.loose[path] = _COVERED.pop(path)
    else:
        db.meshes.loose.pop(path, None)
    return {'ok': True, 'now': _source(db, path)[1]}


_COVERED = {}      # (texture or model path -> the loose file a copy in the mod's folder covers, for give_back)


# ----- to Blender and back ----------------------------------------------------------------------------
# A model goes out as one .glb (glTF binary, what Blender opens best) with its textures inside as PNG
# pictures, each named after the game's texture, and in the file's extras where it came from, the scale
# (1/70: a Morrowind unit is about 1.4 cm, so it is the right size in metres) and a fingerprint of each
# picture. Coming back, the axes and scale are undone exactly and the model keeps its own origin (the
# Library's import recentres a model; a round trip must not, or every placed copy would move), and a
# picture that wasn't repainted keeps pointing at the game's texture: only a changed one becomes new.
# (a test Workshop, with its own home, keeps its exports there)
EXPORTS = os.path.join(os.environ['WORKSHOP_HOME'], 'exports') if os.environ.get('WORKSHOP_HOME') else \
    os.path.join(os.path.expanduser('~'), 'Documents', 'Morrowind Workshop exports')
TO_METRES = 1.0 / library.UNITS_PER_METRE


def _glb(doc, binary):
    import json
    js = json.dumps(doc, separators=(',', ':')).encode('utf-8')
    js += b' ' * (-len(js) % 4)
    binary += b'\0' * (-len(binary) % 4)
    body = struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(binary), 0x004E4942) + binary
    return struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body


def export_glb(db, model, out=None):
    """The model as a .glb for Blender (path as records give it). Returns {'file', 'shapes', 'pictures', 'lost'}."""
    import hashlib
    rel = 'meshes/' + model.lower().replace('\\', '/')
    raw = db.meshes.read(rel)
    if not raw:
        raise EditError("The model's file is missing (%s)." % model)
    shapes = nif.mesh_from_nif(raw, max_verts=400000) or []
    fx = _fx_out(db, raw)
    if not shapes and not fx:
        raise EditError('This model has nothing to draw that can be taken out (no triangle shapes).')
    have = model_info(db, model).get('has', {})
    lost = [k for k in ('animation', 'skin', 'particles', 'morphs', 'flipbook', 'scrolling texture', 'light', 'switch', 'billboard')
            if have.get(k) and not (k == 'particles' and fx)]
    bin_ = bytearray()
    doc = {'asset': {'version': '2.0', 'generator': 'Morrowind Workshop'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'name': os.path.splitext(os.path.basename(model))[0], 'children': []}],
           'meshes': [], 'materials': [], 'textures': [], 'images': [], 'samplers': [{'wrapS': 10497, 'wrapT': 10497}],
           'accessors': [], 'bufferViews': [], 'buffers': []}

    def view(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        v = {'buffer': 0, 'byteOffset': len(bin_), 'byteLength': len(data)}
        if target:
            v['target'] = target
        bin_.extend(data)
        doc['bufferViews'].append(v)
        return len(doc['bufferViews']) - 1
    pics, mats = {}, {}
    for n, s in enumerate(shapes):
        P = s['p']
        # (game: X east, Y north, Z up, in units; glTF: Y up, in metres)
        verts = [(P[k] * TO_METRES, P[k + 2] * TO_METRES, -P[k + 1] * TO_METRES) for k in range(0, len(P), 3)]
        tris = [(s['i'][k], s['i'][k + 2], s['i'][k + 1]) for k in range(0, len(s['i']) - 2, 3)]    # (the other way round)
        normals = nifwrite._normals(verts, tris)
        acc = []
        pv = view(b''.join(struct.pack('<3f', *v) for v in verts), 34962)
        doc['accessors'].append({'bufferView': pv, 'componentType': 5126, 'count': len(verts), 'type': 'VEC3',
                                 'min': [min(v[i] for v in verts) for i in range(3)], 'max': [max(v[i] for v in verts) for i in range(3)]})
        attrs = {'POSITION': len(doc['accessors']) - 1}
        nv = view(b''.join(struct.pack('<3f', *v) for v in normals), 34962)
        doc['accessors'].append({'bufferView': nv, 'componentType': 5126, 'count': len(normals), 'type': 'VEC3'})
        attrs['NORMAL'] = len(doc['accessors']) - 1
        if s['uv'] and len(s['uv']) == len(verts) * 2:
            uv = view(struct.pack('<%df' % len(s['uv']), *s['uv']), 34962)
            doc['accessors'].append({'bufferView': uv, 'componentType': 5126, 'count': len(verts), 'type': 'VEC2'})
            attrs['TEXCOORD_0'] = len(doc['accessors']) - 1
        big = len(verts) > 65535
        iv = view(struct.pack('<%d%s' % (len(tris) * 3, 'I' if big else 'H'), *[i for t in tris for i in t]), 34963)
        doc['accessors'].append({'bufferView': iv, 'componentType': 5125 if big else 5123, 'count': len(tris) * 3, 'type': 'SCALAR'})
        ia = len(doc['accessors']) - 1
        # the material: one per texture and look, with its picture once
        tex = s.get('tex')
        mk = (tex or '', bool(s.get('alpha')), bool(s.get('double')))
        if mk not in mats:
            m = {'name': (tex or 'untextured'), 'pbrMetallicRoughness': {'metallicFactor': 0.0, 'roughnessFactor': 1.0}}
            if s.get('alpha'):
                m['alphaMode'] = 'MASK'
                m['alphaCutoff'] = 0.5
            if s.get('double'):
                m['doubleSided'] = True
            if tex:
                if tex not in pics:
                    path = db.meshes.texture_path(tex)
                    d = _decode(db.meshes.read(path) or b'', want=1 << 16) if path else None
                    png = _png(*d) if d else None
                    if png is None and path and (db.meshes.read(path) or b'')[:8] == b'\x89PNG\r\n\x1a\n':
                        png = db.meshes.read(path)
                    if png:
                        doc['images'].append({'name': tex, 'mimeType': 'image/png', 'bufferView': view(png)})
                        doc['textures'].append({'source': len(doc['images']) - 1, 'sampler': 0})
                        pics[tex] = (len(doc['textures']) - 1, _pixel_key(png))
                    else:
                        pics[tex] = (None, None)
                if pics[tex][0] is not None:
                    m['pbrMetallicRoughness']['baseColorTexture'] = {'index': pics[tex][0]}
            doc['materials'].append(m)
            mats[mk] = len(doc['materials']) - 1
        doc['meshes'].append({'name': 'shape %d' % (n + 1), 'primitives': [{'attributes': attrs, 'indices': ia, 'material': mats[mk]}]})
        doc['nodes'].append({'name': 'shape %d' % (n + 1), 'mesh': len(doc['meshes']) - 1})
        doc['nodes'][0]['children'].append(len(doc['nodes']) - 1)
    doc['buffers'].append({'byteLength': len(bin_)})
    for k in ('textures', 'images', 'meshes', 'materials', 'accessors', 'bufferViews'):
        if not doc[k]:
            del doc[k]
    if not bin_:
        del doc['buffers']                       # (an effect alone: no shapes, nothing in the file but its root)
        doc.pop('samplers', None)
    # (on the file, the scene and the root object: Blender keeps a scene's and an object's custom properties
    # through its import and export, and not always the file's own)
    ws = {'model': model, 'units_per_metre': library.UNITS_PER_METRE, 'pictures': {t: h for t, (_i, h) in pics.items() if h}}
    doc['extras'] = {'workshop': ws}
    doc['scenes'][0]['extras'] = {'workshop': ws}
    doc['nodes'][0]['extras'] = {'workshop': ws}
    if not out:
        os.makedirs(EXPORTS, exist_ok=True)
        out = os.path.join(EXPORTS, re.sub(r'[^A-Za-z0-9_.-]+', '_', os.path.splitext(os.path.basename(model))[0]) + '.glb')
    with open(out, 'wb') as f:
        f.write(_glb(doc, bytes(bin_)))
    _fx_write(db, fx, out)
    return {'file': out, 'shapes': len(shapes), 'pictures': sum(1 for v in pics.values() if v[0] is not None), 'lost': lost,
            'stamp': stamp(out), 'particles': len(fx)}


# ----- particles to Blender and back (particles from Blender, stage 3) -------------------------------------------
# A model's particle effects go out beside its .glb: <glb>.fx.json holds, for each, the classic particle settings the
# Blender script sets up (partmake.to_blender) and the game's own numbers. The script builds them and keeps a copy
# of the file as built (<glb>.start.blend). Coming back, the saved .blend is read as any .blend is (blendread,
# stage 2), and each group of settings left as it was keeps the game's exact numbers (partmake.unchanged).
def _fx_out(db, raw):
    import partnif
    if not any(struct.pack('<I', len(k)) + k in raw for k in partnif.EMITTERS):
        return []
    try:
        fx = partnif.effects(raw)
    except partnif.PartError:
        return []
    for n, e in enumerate(fx):
        e['tex_game'] = e['tex']
        e['tex'] = db.meshes.texture_path(e['tex']) if e['tex'] else ''
        e['name'] = 'Particles %d' % (n + 1)
    return fx


def _fx_write(db, fx, glb):
    import json
    import partmake
    side = glb + '.fx.json'
    for p in (side, glb + '.start.blend'):
        if os.path.exists(p):
            os.remove(p)
    if not fx:
        return
    out = []
    stem = os.path.splitext(glb)[0]
    for n, e in enumerate(fx):
        b = partmake.to_blender(e, library.UNITS_PER_METRE)
        b['picture'] = ''
        if e['tex']:
            data = db.meshes.read(e['tex']) or b''
            d = _decode(data, want=1 << 16)
            png = _png(*d) if d else data if data[:8] == b'\x89PNG\r\n\x1a\n' else None
            if png:
                b['picture'] = '%s_fx%d.png' % (stem, n + 1)
                with open(b['picture'], 'wb') as f:
                    f.write(png)
        out.append(b)
    with open(side, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'units_per_metre': library.UNITS_PER_METRE, 'systems': out}, f)


def blender():
    """Blender's program on this PC, newest first, or None."""
    import osplat
    found = osplat.blenders()
    s = load_settings() or {}
    if s.get('blender') and os.path.isfile(s['blender']):
        return s['blender']
    return found[0] if found else None


# (what Blender runs on opening: the export brought in, and each Ctrl+S of the .blend sends a .glb back over
# the export, so the Workshop sees the change; the scene is cleared first so the default cube doesn't come too)
BLENDER_SCRIPT = r'''
import bpy, json, math, os
glb = r"%s"
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
if os.path.getsize(glb) > 64:
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except RuntimeError:
        pass                                # (an effect alone has no shapes to bring in)
%s
def _back(*_a):
    # (where the .blend is, so its particle systems can be read back as Blender keeps them)
    bpy.context.scene['ws_blend'] = bpy.data.filepath
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_extras=True, export_image_format='AUTO')
bpy.app.handlers.save_post.append(_back)
'''

# (the game's particle effects as Blender's classic particle systems: an emitter the size of the game's box, turned
# as it is, a count over frames, a push along the cone's middle with a random speed for its spread, a sprite as the
# particle, a wind of its own for its pulls, and a material: the picture, a Color Ramp over the particle's life,
# Emission for a glow. A copy of the file as built is kept beside the export, to tell later what was changed)
PARTICLE_SCRIPT = r'''
from mathutils import Matrix, Vector
fx = json.load(open(glb + '.fx.json', encoding='utf-8'))
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = 24, 1.0
for sy in fx['systems']:
    nm = sy['name']
    bx = sy['box']
    if all(b > 1e-6 for b in bx) or sum(1 for b in bx if b > 1e-6) == 2:
        h = [b / 2 for b in bx]
        vs = [(sx * h[0], sy_ * h[1], sz * h[2]) for sx in (-1, 1) for sy_ in (-1, 1) for sz in (-1, 1)]
        fs = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        how = 'VOLUME' if all(b > 1e-6 for b in bx) else 'FACE'
    else:
        vs, fs, how = [(0.0, 0.0, 0.0)], [], 'VERT'
    me = bpy.data.meshes.new(nm)
    me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new(nm, me)
    scene.collection.objects.link(ob)
    R = sy['R']
    ob.matrix_world = Matrix(((R[0][0], R[0][1], R[0][2], sy['at'][0]), (R[1][0], R[1][1], R[1][2], sy['at'][1]),
                              (R[2][0], R[2][1], R[2][2], sy['at'][2]), (0, 0, 0, 1)))
    ob.show_instancer_for_render = False
    # the look
    m = bpy.data.materials.new(nm)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    col = sy['color']
    m.diffuse_color = (col[0], col[1], col[2], col[3])
    if sy['glow']:
        sh = nt.nodes.new('ShaderNodeEmission'); colour_in = sh.inputs['Color']
        tr = nt.nodes.new('ShaderNodeBsdfTransparent'); add = nt.nodes.new('ShaderNodeAddShader')
        nt.links.new(sh.outputs[0], add.inputs[0]); nt.links.new(tr.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs['Surface'])
    else:
        sh = nt.nodes.new('ShaderNodeBsdfPrincipled'); colour_in = sh.inputs['Base Color']
        nt.links.new(sh.outputs[0], out.inputs['Surface'])
    colour = None
    if sy['picture'] and os.path.isfile(sy['picture']):
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(sy['picture'])
        tex.image.pack()
        colour = tex.outputs['Color']
        if not sy['glow']:
            nt.links.new(tex.outputs['Alpha'], sh.inputs['Alpha'])
    if sy['ramp']:
        info = nt.nodes.new('ShaderNodeParticleInfo')
        div = nt.nodes.new('ShaderNodeMath'); div.operation = 'DIVIDE'
        nt.links.new(info.outputs['Age'], div.inputs[0]); nt.links.new(info.outputs['Lifetime'], div.inputs[1])
        cr = nt.nodes.new('ShaderNodeValToRGB')
        nt.links.new(div.outputs[0], cr.inputs['Fac'])
        els = cr.color_ramp.elements
        while len(els) < len(sy['ramp']):
            els.new(0.5)
        while len(els) > len(sy['ramp']):
            els.remove(els[-1])
        for el, k in zip(els, sy['ramp']):
            el.position = k[0]; el.color = (k[1], k[2], k[3], k[4])
        if colour is not None:
            mix = nt.nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1
            nt.links.new(colour, mix.inputs[1]); nt.links.new(cr.outputs['Color'], mix.inputs[2])
            colour = mix.outputs[0]
        else:
            colour = cr.outputs['Color']
    if colour is not None:
        nt.links.new(colour, colour_in)
    else:
        colour_in.default_value = (col[0], col[1], col[2], 1.0)
    if hasattr(m, 'surface_render_method'):
        m.surface_render_method = 'BLENDED'
    ob.data.materials.append(m)
    # the particle: a sprite, kept out of the render (it is drawn where the particles are)
    sp_me = bpy.data.meshes.new(nm + ' sprite')
    sp_me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    sp_me.materials.append(m)
    sprite = bpy.data.objects.new(nm + ' sprite', sp_me)
    scene.collection.objects.link(sprite)
    sprite.location = (0, 0, -50)
    sprite.hide_render = True
    # the system
    ob.modifiers.new(nm, 'PARTICLE_SYSTEM')
    ps = ob.particle_systems[0].settings
    ps.name = nm
    ps.count = sy['count']
    ps.frame_start, ps.frame_end = sy['frame_start'], sy['frame_end']
    ps.lifetime, ps.lifetime_random = sy['lifetime'], sy['lifetime_random']
    ps.emit_from = how
    ps.normal_factor = 0.0
    ps.object_align_factor = sy['object_align']
    ps.factor_random = sy['factor_random']
    ps.particle_size, ps.size_random = sy['size'], 0.0
    ps.render_type, ps.instance_object = 'OBJECT', sprite
    ps.material_slot = m.name
    ps.effector_weights.gravity = 0.0
    # (its pulls: a wind of its own, which only this system feels)
    coll = bpy.data.collections.new(nm + ' forces')
    scene.collection.children.link(coll)
    ps.effector_weights.collection = coll
    if sy['wind']:
        bpy.ops.object.effector_add(type='WIND')
        wind = bpy.context.object
        wind.name = nm + ' wind'
        for c in list(wind.users_collection):
            c.objects.unlink(wind)
        coll.objects.link(wind)
        z = Vector(sy['wind']['dir']).normalized()
        wind.rotation_euler = Vector((0, 0, 1)).rotation_difference(z).to_euler()
        wind.location = Vector(sy['at'])
        wind.field.strength = sy['wind']['strength']
        wind.field.flow = 0.0
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=glb + '.start.blend', copy=True, compress=False)
'''


def open_in_blender(file):
    exe = blender()
    if not exe:
        raise EditError('Blender was not found on this PC. Open the exported file in your 3D program: File ▸ Import ▸ glTF.')
    script = os.path.join(EXPORTS, '_open_%s.py' % re.sub(r'[^A-Za-z0-9_]+', '_', os.path.splitext(os.path.basename(file))[0]))
    with open(script, 'w', encoding='utf-8') as f:
        f.write(blender_script(file))
    subprocess.Popen([exe, '--python', script])
    return exe


def blender_script(file):
    """What Blender runs on opening an export: the model, its particle effects if it has any, and the way back."""
    parts = PARTICLE_SCRIPT if os.path.isfile(file + '.fx.json') else ''
    return BLENDER_SCRIPT % (file, parts)


def _gl_extras(path):
    import json
    raw = open(path, 'rb').read()
    if raw[:4] != b'glTF':
        return {}
    clen, ctype = struct.unpack_from('<II', raw, 12)
    doc = json.loads(raw[20:20 + clen].decode('utf-8')) if ctype == 0x4E4F534A else {}
    holders = [doc] + doc.get('scenes', []) + doc.get('nodes', [])
    # (the .blend it was saved from, set by the Blender script on each save: its particle systems come back from it)
    blend = next((h['extras']['ws_blend'] for h in holders if isinstance(h.get('extras'), dict) and h['extras'].get('ws_blend')), None)
    for holder in holders:
        ws = (holder.get('extras') or {}).get('workshop')
        if isinstance(ws, dict) and ws.get('model'):
            return dict(ws, ws_blend=blend) if blend else ws
    return {}


def _fx_back(glb, ex):
    """The particle systems of the .blend a save came from (blendread, as stage 2 reads any .blend), each matched with
    the game effect it was sent as: s['keep'] is what keeps the game's own numbers."""
    import json
    import blendread
    import partmake
    blend = ex.get('ws_blend')
    if not blend or not os.path.isfile(blend):
        return []
    systems = library.blend_systems(blend)[0]
    side, start = glb + '.fx.json', glb + '.start.blend'
    if systems and os.path.isfile(side) and os.path.isfile(start):
        game = {g['name']: g['game'] for g in json.load(open(side, encoding='utf-8')).get('systems', [])}
        first = {s['object']: s for s in blendread.particles(start)}
        for s in systems:
            if s['object'] in game and s['object'] in first:
                s['keep'] = partmake.unchanged(s, first[s['object']], game[s['object']])
    return systems


def import_back(db, glb, how='everywhere', rec_i=None, model=None, collision='shape', into=None):
    """A .glb that went out to Blender, back into the game: how 'everywhere' writes it over the model in your
    mod's folder (an override of the game's file), 'own' as a new model and a new record of rec_i; into: the
    own model an earlier return made (meshes/wslib/...), written over again at each later save."""
    import hashlib
    editing._require_project(db)
    if not glb or not os.path.isfile(glb):
        raise EditError('The exported file is gone: export the model again.')
    ex = _gl_extras(glb)
    model = model or ex.get('model')
    if not model:
        raise EditError("This file didn't come from the Workshop's export, so it can't go back over a model. Bring it in on the Library page instead.")
    k = float(ex.get('units_per_metre') or library.UNITS_PER_METRE)
    parts, images = library.read_gltf(glb) if os.path.getsize(glb) > 64 else ([], [])
    systems = _fx_back(glb, ex)
    if systems:
        import blendread
        helpers = blendread.helper_names(ex['ws_blend'])
        parts = [p for p in parts if p.get('node') not in helpers]       # (the emitters and sprites are not the model)
    if not parts and not systems:
        raise EditError('There is nothing to draw in it (no triangles).')
    hashes = ex.get('pictures') or {}
    saved, new_pics = {}, 0
    for p in parts:
        p['verts'] = [(v[0] * k, -v[2] * k, v[1] * k) for v in p['verts']]
        if p.get('normals'):
            p['normals'] = [(v[0], -v[2], v[1]) for v in p['normals']]
        p['tris'] = [(a, c, b) for a, b, c in p['tris']]
        img = p.pop('image', None)
        if img is not None and img < len(images):
            im = images[img]
            data = im.get('raw') or (open(im['path'], 'rb').read() if im.get('path') else None)
            name = im.get('name') or ''
            if img not in saved:
                key = _pixel_key(data) if data else None
                same = next((t for t, h in hashes.items() if h and h == key), None)
                if same:
                    saved[img] = same                    # (not repainted: the game's own texture still)
                elif data:
                    saved[img] = library._copy_picture(db, raw=data, name=os.path.splitext(name or 'texture')[0] + '_edit', ext=im.get('ext') or '.png')[0]
                    new_pics += 1
                else:
                    saved[img] = name or None
            p['texture'] = saved[img]
    stem = os.path.splitext(os.path.basename(model))[0]
    raw = nifwrite.write_nif(parts, stem, collision) if parts else None
    out = {'pictures_new': new_pics, 'shapes': len(parts)}
    if systems:
        import partmake
        import partnif
        f = partnif.read(raw) if raw else partmake.root(stem)
        out['particles'], out['particles_changed'] = len(systems), {}
        for s in systems:
            keep = s.get('keep') or {}
            if 'picture' in keep:
                tex = keep['picture']['texture']        # (not repainted: the game's own texture still)
            elif isinstance(s.get('picture'), dict):
                tex = library._copy_picture(db, raw=s['picture']['raw'], name=stem + '_fx', ext=s['picture']['ext'])[0]
                new_pics += 1
            elif s.get('picture'):
                tex = library._copy_picture(db, src_path=s['picture'])[0]
                new_pics += 1
            else:
                tex = library._particle_dot(db)
            partmake.add(f, s, k, (0.0, 0.0, 0.0), tex)
            out['particles_changed'][s['object']] = partmake.changed(keep) if s.get('keep') else ['all']
        raw = partnif.write(f)
        out['pictures_new'] = new_pics
    return _put_model(db, raw, model, how, rec_i, into, out)


def fx_edit(db, rec_i, edits, how='everywhere', into=None):
    """The sliders in Model & textures: a model's particle effects changed in place (fxedit), written where it goes
    as a round trip's return is. Returns {'path', 'ids', 'changed'} and, for 'own', the new record."""
    import fxedit
    editing._require_project(db)
    model = db.recs[int(rec_i)][5] if rec_i is not None else None
    into_rel = (into or '').lower().replace('\\', '/')
    rel = into_rel if how == 'own' and into_rel else 'meshes/' + (model or '').lower().replace('\\', '/')
    raw = db.meshes.read(rel)
    if not raw:
        raise EditError("The model's file is missing.")
    greys = {}

    def grey(name):
        # (a grey copy of the texture: the colour picked is then the colour seen)
        if name in greys:
            return greys[name]
        path = db.meshes.texture_path(name)
        data = db.meshes.read(path) or b'' if path else b''
        d = _decode(data, want=1 << 16) or _png_pixels(data)
        if not d:
            greys[name] = None
            return None
        w, h, px = d
        out = bytearray(px)
        for i in range(0, len(out), 4):
            v = int(round(0.299 * out[i] + 0.587 * out[i + 1] + 0.114 * out[i + 2]))
            out[i] = out[i + 1] = out[i + 2] = v
        stem = os.path.splitext(os.path.basename(name.replace('\\', '/')))[0]
        greys[name] = library._copy_picture(db, raw=_png(w, h, bytes(out)), name=stem + '_grey', ext='.png')[0]
        return greys[name]
    try:
        new, changed = fxedit.apply(raw, edits, grey)
    except Exception as e:
        import partnif
        if isinstance(e, partnif.PartError):
            raise EditError("This model's particles can't be changed here: %s" % e)
        raise
    out = {'changed': changed}
    return _put_model(db, new, model, how, rec_i, into, out)


def _put_model(db, raw, model, how, rec_i, into, out):
    """A changed model written where it goes: 'everywhere' over the model in your mod's folder, 'own' as a new
    model and a new record of rec_i, or into the own model an earlier change made. out is filled and returned."""
    into = (into or '').lower().replace('\\', '/')
    if how == 'own' and into:
        where, _l, full = _source(db, into)
        if where not in ('library', 'mod') or not full or not into.startswith('meshes/'):
            raise EditError("That model isn't one of your mod's own.")
        with open(full, 'wb') as f:
            f.write(raw)
        library._register(db, into, full)
        name = into[len('meshes/'):].replace('/', '\\')
        out.update(file=full, path=into, ids=[r['id'] for r in uses(db, name)['records']])
        return out
    if how == 'own':
        if rec_i is None:
            raise EditError('Pick the object to give the new model to.')
        folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
        os.makedirs(folder, exist_ok=True)
        stem = library._free_name(folder, library._slug(os.path.basename(model)) + '_edit', '.nif')
        full = os.path.join(folder, stem + '.nif')
        with open(full, 'wb') as f:
            f.write(raw)
        rel = 'meshes/%s/%s.nif' % (library.SUB, stem)
        library._register(db, rel, full)
        out.update(record_with_model(db, int(rec_i), '%s\\%s.nif' % (library.SUB, stem)))
    else:
        rel = 'meshes/' + model.lower().replace('\\', '/')
        full = os.path.join(library.data_dir(db), *rel.split('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        prev = db.meshes.loose.get(rel)
        if prev and os.path.normcase(os.path.abspath(prev)) != os.path.normcase(os.path.abspath(full)):
            _COVERED[rel] = prev
        with open(full, 'wb') as f:
            f.write(raw)
        library._register(db, rel, full)
    out.update(file=full, path=rel, ids=[r['id'] for r in uses(db, model)['records']] if how != 'own' else [out.get('id')])
    return out


def record_with_model(db, rec_i, model_name, new_name=None):
    """A copy of a record under a new id, drawn with another model (as Retexture makes one)."""
    from esm import iter_subrecords
    from project import join_subs, zs
    import create
    r = db.recs[rec_i]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    new_id = create.suggest_id(db, '', (new_name or r[1] + '_edit'))[:31]
    subs = []
    for t, d in iter_subrecords(data):
        d = bytes(d)
        if t == 'NAME' and not subs:
            d = zs(new_id)
        elif t == 'MODL':
            d = zs(model_name)
        subs.append((t, d))
    db.project.set_record(r[0], new_id.lower(), flags & ~0x20, join_subs(subs), created=True)
    editing.commit(db, 'Made "%s", a copy of "%s" with its own model' % (new_id, r[1]))
    return {'id': new_id, 'type': r[0], 'i': db.resolve_id(new_id)}


# ----- mesh fixes ---------------------------------------------------------------------------------------
def find_texture(db, name):
    """Textures the game has under the same file name (any folder, any picture kind) for a missing one."""
    stem = os.path.splitext(os.path.basename(name.lower().replace('\\', '/')))[0]
    out = []
    for rel in list(db.meshes.loose) + list(db.meshes.packed):
        if rel.startswith('textures/') and os.path.splitext(os.path.basename(rel))[0] == stem:
            out.append(rel)
    return sorted(set(out))[:20]


def fix_texture(db, rec_i, name, to, how='everywhere'):
    """Point the model's missing texture name at a texture the game has: written over the model in your mod's
    folder ('everywhere') or as a new model and record ('own')."""
    editing._require_project(db)
    r = db.recs[int(rec_i)]
    model = r[5]
    raw = db.meshes.read('meshes/' + (model or '').lower().replace('\\', '/'))
    if not raw:
        raise EditError("The model's file is missing.")
    to = (to or '').lower().replace('\\', '/')
    if not to.startswith('textures/') or to not in db.meshes.loose and to not in db.meshes.packed:
        raise EditError('That texture is not in the game.')
    new_raw, n = nifwrite.retexture(raw, {name.lower().replace('/', '\\'): to[len('textures/'):].replace('/', '\\')})
    if not n:
        raise EditError('That texture name is not in the model.')
    if how == 'own':
        folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
        os.makedirs(folder, exist_ok=True)
        stem = library._free_name(folder, library._slug(os.path.basename(model)) + '_fixed', '.nif')
        full = os.path.join(folder, stem + '.nif')
        with open(full, 'wb') as f:
            f.write(new_raw)
        library._register(db, 'meshes/%s/%s.nif' % (library.SUB, stem), full)
        return record_with_model(db, int(rec_i), '%s\\%s.nif' % (library.SUB, stem))
    rel = 'meshes/' + model.lower().replace('\\', '/')
    full = os.path.join(library.data_dir(db), *rel.split('/'))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    prev = db.meshes.loose.get(rel)
    if prev and os.path.normcase(os.path.abspath(prev)) != os.path.normcase(os.path.abspath(full)):
        _COVERED[rel] = prev
    with open(full, 'wb') as f:
        f.write(new_raw)
    library._register(db, rel, full)
    return {'path': rel, 'file': full}
