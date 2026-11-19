"""Reading Blender's own files (.blend) without Blender: the meshes of its objects, placed as in the
scene, with their UV maps and the pictures their materials use. Blender 2.80 and newer, compressed or
not. Modifiers are not applied, except Mirror (so half-modelled bodies come out whole)."""
import bisect
import math
import os
import struct

from editing import EditError


class _Ptr(int):
    """A pointer read from the file, with where it was read (to look it up among its own ID's blocks)."""
    def __new__(cls, v, near):
        o = int.__new__(cls, v)
        o.near = near
        return o


class Blend:
    def __init__(self, raw):
        if raw[:4] == b'\x28\xb5\x2f\xfd':                 # zstd (Blender 3.0 and newer)
            try:
                import zstandard
            except ImportError:
                raise EditError('This .blend file is compressed in a way the Workshop cannot open here. In Blender, '
                                'turn off File > Save Options > Compress, save it again, and bring it in.')
            raw = zstandard.ZstdDecompressor().stream_reader(raw).read()
        elif raw[:2] == b'\x1f\x8b':                       # gzip (older Blender)
            import gzip
            raw = gzip.decompress(raw)
        if raw[:7] != b'BLENDER':
            raise EditError('This is not a Blender file the Workshop can read.')
        self.raw = raw
        if raw[7:8] in (b'_', b'-'):                        # BLENDER-v402 (older header)
            self.psize = 8 if raw[7:8] == b'-' else 4
            self.e = '<' if raw[8:9] == b'v' else '>'
            pos, self.new_head = 12, False
        else:                                               # BLENDER17-01v0500 (Blender 5)
            self.psize, self.e = 8, '<'
            pos, self.new_head = int(raw[7:9]), True
        self.blocks, self.by_ptr, self.local, owner = [], {}, {}, -1
        while pos + 8 <= len(raw):
            code = raw[pos:pos + 4]
            if self.new_head:
                # (code, SDNA index, old pointer, length, count: 32 bytes)
                sdna, old, ln, cnt = struct.unpack_from(self.e + 'iQqq', raw, pos + 4)
                hs = 32
            else:
                ln, = struct.unpack_from(self.e + 'i', raw, pos + 4)
                old, = struct.unpack_from(self.e + ('Q' if self.psize == 8 else 'I'), raw, pos + 8)
                sdna, cnt = struct.unpack_from(self.e + 'ii', raw, pos + 8 + self.psize)
                hs = 16 + self.psize
            b = {'code': code, 'at': pos + hs, 'len': ln, 'sdna': sdna, 'count': cnt}
            if code[2:] == b'\0\0':
                owner = len(self.blocks)             # an ID (object, mesh...): its data follows it
            self.blocks.append(b)
            if old:
                self.by_ptr[old] = b
                # (Blender 5 numbers each ID's blocks on their own, so an address is first looked for there)
                self.local[(owner, old)] = b
            b['owner'] = owner
            pos += hs + ln
            if code == b'ENDB':
                break
        self.starts = [b['at'] for b in self.blocks]
        self._dna()

    def _dna(self):
        raw, e = self.raw, self.e
        dna = next((b for b in self.blocks if b['code'] == b'DNA1'), None)
        if not dna:
            raise EditError('This Blender file has no description of its contents.')
        p = dna['at'] + 8
        a0 = dna['at']          # (padding counts from the block's start: Blender 5's header is 17 bytes)
        al = lambda q: a0 + ((q - a0 + 3) & ~3)

        def strings(p, n):
            out = []
            for _ in range(n):
                q = raw.index(b'\0', p)
                out.append(raw[p:q].decode('latin-1'))
                p = q + 1
            return out, al(p)
        n, = struct.unpack_from(e + 'i', raw, p)
        names, p = strings(p + 4, n)
        n, = struct.unpack_from(e + 'i', raw, p + 4)
        types, p = strings(p + 8, n)
        tlen = struct.unpack_from(e + '%dh' % n, raw, p + 4)
        p = al(p + 4 + 2 * n)
        n, = struct.unpack_from(e + 'i', raw, p + 4)
        p += 8
        self.structs, self.struct_of = [], {}
        for _ in range(n):
            t, nf = struct.unpack_from(e + 'hh', raw, p)
            p += 4
            fields, off = {}, 0
            for _ in range(nf):
                ft, fn = struct.unpack_from(e + 'hh', raw, p)
                p += 4
                nm = names[fn]
                ptr = nm.startswith('*') or nm.startswith('(*')
                count = 1
                for d in nm[nm.index('['):].replace(']', '').split('[')[1:] if '[' in nm else ():
                    count *= int(d)
                base = nm.lstrip('*(').split('[')[0].split(')')[0]
                size = (self.psize if ptr else tlen[ft]) * count
                fields[base] = (types[ft], off, ptr, count, nm)
                off += size
            self.structs.append((types[t], fields, tlen[t]))
            self.struct_of[types[t]] = len(self.structs) - 1

    # -------------------------------------------------------------- reading values
    def fields(self, sname):
        return self.structs[self.struct_of[sname]][1]

    def size_of(self, sname):
        return self.structs[self.struct_of[sname]][2]

    def get(self, sname, at, field, default=None):
        f = self.fields(sname).get(field)
        if not f:
            return default
        t, off, ptr, count, _nm = f
        p = at + off
        e, raw = self.e, self.raw
        if ptr:
            fmt = 'Q' if self.psize == 8 else 'I'
            if count == 1:
                return _Ptr(struct.unpack_from(e + fmt, raw, p)[0], at)
            return [_Ptr(v, at) for v in struct.unpack_from(e + '%d%s' % (count, fmt), raw, p)]
        if t == 'char':
            s = raw[p:p + count]
            return s.split(b'\0', 1)[0].decode('utf-8', 'replace') if count > 1 else s[0]
        fmt = {'int': 'i', 'float': 'f', 'short': 'h', 'ushort': 'H', 'uchar': 'B', 'double': 'd', 'int8_t': 'b',
               'uint': 'I', 'int64_t': 'q', 'uint64_t': 'Q'}.get(t)
        if not fmt:
            return at + off                       # an embedded struct: its position
        vals = struct.unpack_from(e + '%d%s' % (count, fmt), raw, p)
        return vals[0] if count == 1 else list(vals)

    def block(self, ptr):
        if not ptr:
            return None
        near = getattr(ptr, 'near', None)
        if near is not None:
            k = bisect.bisect_right(self.starts, near) - 1
            if k >= 0:
                b = self.local.get((self.blocks[k]['owner'], int(ptr)))
                if b:
                    return b
        return self.by_ptr.get(ptr)

    def name_of(self, at):
        return self.get('ID', at, 'name', '')[2:]

    def listbase(self, lb_at, sname):
        """The items of a ListBase (first/last pointers), each a position of a `sname`."""
        out, ptr, seen = [], self.get('ListBase', lb_at, 'first'), set()
        while ptr and ptr not in seen:
            seen.add(ptr)
            b = self.block(ptr)
            if not b:
                break
            out.append(b['at'])
            ptr = self.get(sname, b['at'], 'next')
        return out

    def array(self, ptr, fmt, n):
        b = self.block(ptr)
        if not b:
            return None
        k = struct.calcsize(fmt)
        n = min(n, b['len'] // k) if k else 0
        return list(struct.unpack_from(self.e + '%d%s' % (n, fmt) if len(fmt) == 1 else self.e + fmt * n, self.raw, b['at']))

    def layers(self, cd_at):
        out = []
        n = self.get('CustomData', cd_at, 'totlayer') or 0
        b = self.block(self.get('CustomData', cd_at, 'layers'))
        if not b:
            return out
        ls = self.size_of('CustomDataLayer')
        for i in range(n):
            at = b['at'] + i * ls
            out.append({'type': self.get('CustomDataLayer', at, 'type'), 'name': self.get('CustomDataLayer', at, 'name', ''),
                        'data': self.get('CustomDataLayer', at, 'data'), 'active': self.get('CustomDataLayer', at, 'active')})
        return out


# CustomData types (from Blender's source; they keep their numbers)
CD_MVERT, CD_MLOOPUV, CD_MPOLY, CD_MLOOP = 0, 16, 25, 26
CD_PROP_INT32, CD_PROP_FLOAT2, CD_PROP_FLOAT3 = 11, 49, 48


# Blender 5's attribute kinds, as the CustomData kinds the reading below knows
_ATTR_KIND = {3: CD_PROP_INT32, 6: CD_PROP_FLOAT2, 7: CD_PROP_FLOAT3}


def _stored(bl, st):
    """The attributes in a Blender 5 AttributeStorage, as layers: {'type', 'name', 'data', 'active', 'domain'}.
    Only those kept as whole arrays (one value for every item)."""
    out = []
    b = bl.block(bl.get('AttributeStorage', st, 'dna_attributes'))
    if not b:
        return out
    sz = bl.size_of('Attribute')
    for i in range(bl.get('AttributeStorage', st, 'dna_attributes_num') or 0):
        a = b['at'] + i * sz
        nb = bl.block(bl.get('Attribute', a, 'name'))
        db = bl.block(bl.get('Attribute', a, 'data'))
        kind = _ATTR_KIND.get(bl.get('Attribute', a, 'data_type'))
        if not nb or not db or kind is None or bl.get('Attribute', a, 'storage_type') != 0:
            continue
        name = bl.raw[nb['at']:nb['at'] + nb['len']].split(bytes(1), 1)[0].decode('utf-8', 'replace')
        out.append({'type': kind, 'name': name, 'data': bl.get('AttributeArray', db['at'], 'data'), 'active': 0,
                    'domain': bl.get('Attribute', a, 'domain')})
    return out


def _mesh(bl, me_at):
    """Vertices, faces (lists of corner indices), each corner's vertex and UV, each face's material slot."""
    nv = bl.get('Mesh', me_at, 'totvert') or 0
    nf = bl.get('Mesh', me_at, 'totpoly', None)
    if nf is None:
        nf = bl.get('Mesh', me_at, 'faces_num') or 0
    nl = bl.get('Mesh', me_at, 'totloop', None)
    if nl is None:
        nl = bl.get('Mesh', me_at, 'corners_num') or 0
    vd = bl.get('Mesh', me_at, 'vdata') or bl.get('Mesh', me_at, 'vert_data')
    pd = bl.get('Mesh', me_at, 'pdata') or bl.get('Mesh', me_at, 'face_data')
    ld = bl.get('Mesh', me_at, 'ldata') or bl.get('Mesh', me_at, 'corner_data')
    vl, pl, ll = bl.layers(vd), bl.layers(pd), bl.layers(ld)
    if 'attribute_storage' in bl.fields('Mesh'):
        # Blender 5 keeps the attributes in a list of their own, by domain (point, edge, face, corner)
        for a in _stored(bl, bl.get('Mesh', me_at, 'attribute_storage')):
            [vl, None, pl, ll][a['domain']].append(a) if a['domain'] in (0, 2, 3) else None
    pos = None
    for L in vl:
        if L['name'] == 'position':
            pos = bl.array(L['data'], 'f', nv * 3)
    if pos is None:
        for L in vl:
            if L['type'] == CD_MVERT:                          # MVert {co[3], ...} (Blender before 3.5)
                b = bl.block(L['data'])
                sz = bl.size_of('MVert')
                pos = []
                for i in range(nv):
                    pos += struct.unpack_from(bl.e + '3f', bl.raw, b['at'] + i * sz)
    if not pos:
        return None
    verts = [tuple(pos[i * 3:i * 3 + 3]) for i in range(len(pos) // 3)]
    offs = bl.array(bl.get('Mesh', me_at, 'poly_offset_indices') or bl.get('Mesh', me_at, 'face_offset_indices'), 'i', nf + 1)
    starts = None
    mat_idx = None
    if offs:
        starts = [(offs[i], offs[i + 1] - offs[i]) for i in range(nf)]
    else:
        for L in pl:
            if L['type'] == CD_MPOLY:                          # MPoly {loopstart, totloop, mat_nr, ...}
                b = bl.block(L['data'])
                sz = bl.size_of('MPoly')
                f = bl.fields('MPoly')
                starts, mat_idx = [], []
                for i in range(nf):
                    at = b['at'] + i * sz
                    starts.append((bl.get('MPoly', at, 'loopstart'), bl.get('MPoly', at, 'totloop')))
                    mat_idx.append(bl.get('MPoly', at, 'mat_nr') or 0 if 'mat_nr' in f else 0)
    if not starts:
        return None
    for L in pl:
        if L['name'] == 'material_index' and L['type'] == CD_PROP_INT32:
            mat_idx = bl.array(L['data'], 'i', nf)
    cv = None
    for L in ll:
        if L['name'] == '.corner_vert':
            cv = bl.array(L['data'], 'i', nl)
    if cv is None:
        for L in ll:
            if L['type'] == CD_MLOOP:                          # MLoop {v, e}
                cv = bl.array(L['data'], 'i' * 2, nl)[0::2]
    if cv is None:
        return None
    uvs = None
    uv_layers = [L for L in ll if (L['type'] == CD_PROP_FLOAT2 and not L['name'].startswith('.')) or L['type'] == CD_MLOOPUV]
    if uv_layers:
        L = next((x for x in uv_layers if x['active'] == uv_layers.index(x)), uv_layers[0])
        if L['type'] == CD_MLOOPUV:
            sz = bl.size_of('MLoopUV')
            b = bl.block(L['data'])
            uvs = [struct.unpack_from(bl.e + '2f', bl.raw, b['at'] + i * sz) for i in range(nl)] if b else None
        else:
            a = bl.array(L['data'], 'f', nl * 2)
            uvs = [(a[i * 2], a[i * 2 + 1]) for i in range(len(a) // 2)] if a else None
    return {'verts': verts, 'faces': starts, 'corner_vert': cv, 'uvs': uvs, 'mat_idx': mat_idx}


def _picture(bl, mat_at, folder):
    """The picture a material shows: an Image Texture node (the one feeding Base Color if there are
    several). A picture packed into the .blend comes as raw bytes."""
    tree = bl.block(bl.get('Material', mat_at, 'nodetree'))
    if not tree:
        return None
    nodes = bl.listbase(bl.get('bNodeTree', tree['at'], 'nodes'), 'bNode')
    images = [n for n in nodes if bl.get('bNode', n, 'idname', '') == 'ShaderNodeTexImage' and bl.get('bNode', n, 'id')]
    if not images:
        return None
    pick = images[0]
    for lk in bl.listbase(bl.get('bNodeTree', tree['at'], 'links'), 'bNodeLink'):
        to = bl.block(bl.get('bNodeLink', lk, 'tosock'))
        fr = bl.block(bl.get('bNodeLink', lk, 'fromnode'))
        if to and fr and bl.get('bNodeSocket', to['at'], 'name', '') == 'Base Color' and fr['at'] in images:
            pick = fr['at']
    im = bl.block(bl.get('bNode', pick, 'id'))
    if not im:
        return None
    pf = bl.block(bl.get('Image', im['at'], 'packedfile'))
    if not pf:
        pfs = bl.listbase(bl.get('Image', im['at'], 'packedfiles'), 'ImagePackedFile') if 'packedfiles' in bl.fields('Image') else []
        if pfs:
            pf = bl.block(bl.get('ImagePackedFile', pfs[0], 'packedfile'))
    if pf:
        n = bl.get('PackedFile', pf['at'], 'size')
        d = bl.block(bl.get('PackedFile', pf['at'], 'data'))
        if d and n:
            raw = bl.raw[d['at']:d['at'] + n]
            ext = '.png' if raw[:4] == b'\x89PNG' else '.jpg' if raw[:2] == b'\xff\xd8' else '.tga'
            return {'raw': raw, 'ext': ext}
    fp = bl.get('Image', im['at'], 'name', '') or bl.get('Image', im['at'], 'filepath', '')
    if fp.startswith('//'):
        fp = os.path.join(folder, fp[2:])
    fp = fp.replace('\\', os.sep).replace('/', os.sep)
    if os.path.isfile(fp):
        return fp
    alt = os.path.join(folder, os.path.basename(fp))
    for cand in (alt, os.path.join(folder, 'textures', os.path.basename(fp))):
        if os.path.isfile(cand):
            return cand
    return None


def _colour(bl, mat_at):
    try:
        return tuple(max(0.0, min(1.0, float(bl.get('Material', mat_at, k)))) for k in ('r', 'g', 'b'))
    except (TypeError, ValueError):
        return (1, 1, 1)


def _mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _local(bl, ob):
    loc = bl.get('Object', ob, 'loc') or [0, 0, 0]
    size = bl.get('Object', ob, 'size') or [1, 1, 1]
    mode = bl.get('Object', ob, 'rotmode') or 0
    if mode == 0:                                              # quaternion
        w, x, y, z = bl.get('Object', ob, 'quat') or [1, 0, 0, 0]
        n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
        w, x, y, z = w / n, x / n, y / n, z / n
        R = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
             [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
             [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    elif mode == -1:                                           # axis and angle
        ax = bl.get('Object', ob, 'rotAxis') or [0, 1, 0]
        a = bl.get('Object', ob, 'rotAngle') or 0.0
        n = math.sqrt(sum(v * v for v in ax)) or 1.0
        x, y, z = (v / n for v in ax)
        c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
        R = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y], [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
             [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    else:                                                      # Euler, in the order Blender names
        rx, ry, rz = bl.get('Object', ob, 'rot') or [0, 0, 0]
        X = [[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]]
        Y = [[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]]
        Z = [[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]]
        order = {1: 'XYZ', 2: 'XZY', 3: 'YXZ', 4: 'YZX', 5: 'ZXY', 6: 'ZYX'}.get(mode, 'XYZ')
        mats = {'X': X, 'Y': Y, 'Z': Z}
        R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        for ch in order:                                       # XYZ: X first, so R = Z * Y * X
            M = mats[ch]
            R = [[sum(M[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return [[R[0][0] * size[0], R[0][1] * size[1], R[0][2] * size[2], loc[0]],
            [R[1][0] * size[0], R[1][1] * size[1], R[1][2] * size[2], loc[1]],
            [R[2][0] * size[0], R[2][1] * size[1], R[2][2] * size[2], loc[2]], [0, 0, 0, 1]]


def _world(bl, ob, depth=0):
    M = _local(bl, ob)
    par = bl.block(bl.get('Object', ob, 'parent'))
    if par and depth < 32:
        inv = bl.get('Object', ob, 'parentinv')
        P = [inv[i * 4:i * 4 + 4] for i in range(4)] if inv else None
        if P:
            P = [[P[c][r] for c in range(4)] for r in range(4)]   # stored column by column
            M = _mul(P, M)
        M = _mul(_world(bl, par['at'], depth + 1), M)
    return M


def _mirror_axes(bl, ob):
    """Axes of the object's Mirror modifiers (0 x, 1 y, 2 z), as long as they're on."""
    axes = []
    if 'modifiers' not in bl.fields('Object'):
        return axes
    for md in bl.listbase(bl.get('Object', ob, 'modifiers'), 'ModifierData'):
        if bl.get('ModifierData', md, 'type') != 5:                # eModifierType_Mirror
            continue
        if not (bl.get('ModifierData', md, 'mode') or 0) & 1:      # not shown in the viewport
            continue
        flag = bl.get('MirrorModifierData', md, 'flag') or 0
        axis_bits = flag & 0x38 if flag & 0x38 else (1 << 3)        # MOD_MIR_AXIS_X/Y/Z = 1<<3..1<<5
        for k in range(3):
            if axis_bits & (1 << (3 + k)):
                axes.append(k)
    return axes


def objects(path):
    """The names of the mesh objects in a .blend file (for the import window)."""
    bl = Blend(open(path, 'rb').read())
    return [bl.name_of(b['at']) for b in bl.blocks if b['code'][:2] == b'OB' and bl.get('Object', b['at'], 'type') == 1
            and bl.block(bl.get('Object', b['at'], 'data'))]


def read_blend(path):
    """Parts of a Blender file: each mesh object's faces as the scene places them, in metres with Y up
    (like the other readers), with the object's name on each part. A particle system's helpers (an emitter
    that isn't shown in a render, the object each particle is drawn as) are not parts: see particles()."""
    bl = Blend(open(path, 'rb').read())
    folder = os.path.dirname(os.path.abspath(path))
    parts, cache = [], {}
    helpers = _particle_helpers(bl)
    for b in bl.blocks:
        if b['code'][:2] != b'OB' or bl.get('Object', b['at'], 'type') != 1:
            continue
        ob = b['at']
        if ob in helpers:
            continue
        meb = bl.block(bl.get('Object', ob, 'data'))
        if not meb or meb['code'][:2] != b'ME':
            continue
        if meb['at'] not in cache:
            cache[meb['at']] = _mesh(bl, meb['at'])
        m = cache[meb['at']]
        if not m:
            continue
        # materials: the mesh's slots (or the object's, when it overrides them)
        n_me = bl.get('Mesh', meb['at'], 'totcol') or 0
        slots = bl.array(bl.get('Mesh', meb['at'], 'mat'), 'Q' if bl.psize == 8 else 'I', n_me) or []
        n_ob = bl.get('Object', ob, 'totcol') or 0
        ob_slots = bl.array(bl.get('Object', ob, 'mat'), 'Q' if bl.psize == 8 else 'I', n_ob) or []
        matbits = bl.array(bl.get('Object', ob, 'matbits'), 'b', n_ob) or []
        mats = []
        for i in range(max(len(slots), len(ob_slots))):
            ptr = ob_slots[i] if i < len(matbits) and matbits[i] and i < len(ob_slots) else (slots[i] if i < len(slots) else 0)
            mb = bl.block(ptr)
            mats.append(mb['at'] if mb else None)
        M = _world(bl, ob)
        mirrors = _mirror_axes(bl, ob)
        variants = [(1, 1, 1)]
        for ax in mirrors:
            variants += [tuple(-s if k == ax else s for k, s in enumerate(v)) for v in variants]
        name = bl.name_of(ob)
        groups = {}
        for fi, (start, count) in enumerate(m['faces']):
            mi = m['mat_idx'][fi] if m['mat_idx'] and fi < len(m['mat_idx']) else 0
            groups.setdefault(mi, []).append((start, count))
        for mi, faces in groups.items():
            mat = mats[mi] if 0 <= mi < len(mats) else None
            for sgn in variants:
                flip = (sgn[0] * sgn[1] * sgn[2]) < 0
                verts, uvs, tris, seen = [], [], [], {}
                for start, count in faces:
                    ids = []
                    for c in range(start, start + count):
                        vi = m['corner_vert'][c] if c < len(m['corner_vert']) else 0
                        uv = tuple(m['uvs'][c]) if m['uvs'] and c < len(m['uvs']) else (0.0, 0.0)
                        key = (vi, uv)
                        if key not in seen:
                            seen[key] = len(verts)
                            v = m['verts'][vi] if vi < len(m['verts']) else (0, 0, 0)
                            v = (v[0] * sgn[0], v[1] * sgn[1], v[2] * sgn[2])
                            w = [sum(M[r][k] * (v + (1.0,))[k] for k in range(4)) for r in range(3)]
                            verts.append((w[0], w[2], -w[1]))              # Blender's Z up -> Y up
                            uvs.append((uv[0], 1.0 - uv[1]))
                        ids.append(seen[key])
                    for i in range(1, len(ids) - 1):
                        tris.append((ids[0], ids[i + 1], ids[i]) if flip else (ids[0], ids[i], ids[i + 1]))
                if tris:
                    parts.append({'name': name, 'object': name, 'verts': verts, 'uvs': uvs if m['uvs'] else None,
                                  'normals': None, 'tris': tris, 'color': _colour(bl, mat) if mat else (1, 1, 1),
                                  'picture': _picture(bl, mat, folder) if mat else None})
    if not parts and not helpers:
        raise EditError('There are no meshes in this Blender file to bring in.')
    return parts


# ------------------------------------------------------------------ particle systems (Blender's classic ones)
PART_FROM_VERT, PART_FROM_FACE, PART_FROM_VOLU = 0, 1, 2
PART_DRAW_OB = 7
PFIELD_WIND = 4
OB_DUPLI_FLAG_RENDER = 2


def _systems(bl):
    """(object position, ParticleSystem position, ParticleSettings position) for each emitter particle system."""
    out = []
    if 'particlesystem' not in bl.fields('Object'):
        return out
    for b in bl.blocks:
        if b['code'][:2] != b'OB':
            continue
        for psy in bl.listbase(bl.get('Object', b['at'], 'particlesystem'), 'ParticleSystem'):
            pa = bl.block(bl.get('ParticleSystem', psy, 'part'))
            if pa and (bl.get('ParticleSettings', pa['at'], 'type') or 0) == 0:     # an emitter (not hair)
                out.append((b['at'], psy, pa['at']))
    return out


def id_props(bl, id_at):
    """The names of an ID's own custom properties (its top-level ID property group)."""
    f = bl.fields('ID')
    if 'properties' not in f:
        return []
    g = bl.block(bl.get('ID', id_at, 'properties'))
    if not g:
        return []
    names = []
    for c in bl.listbase(bl.get('IDPropertyData', bl.get('IDProperty', g['at'], 'data'), 'group'), 'IDProperty'):
        names.append(bl.get('IDProperty', c, 'name', ''))
    return names


def _particle_helpers(bl):
    """Objects that only serve particles: emitters not drawn in a render, what particles are drawn as, and the meshes
    the UnitParticles add-on makes of its particles (marked unitparticles_output_of)."""
    out = set()
    for b in bl.blocks:
        if b['code'][:2] == b'OB' and 'unitparticles_output_of' in id_props(bl, bl.get('Object', b['at'], 'id')):
            out.add(b['at'])
    for ob, _psy, pa in _systems(bl):
        if not (bl.get('Object', ob, 'duplicator_visibility_flag') or 0) & OB_DUPLI_FLAG_RENDER:
            out.add(ob)
        inst = bl.block(bl.get('ParticleSettings', pa, 'dup_ob'))
        if inst and (bl.get('ParticleSettings', pa, 'ren_as') or 0) == PART_DRAW_OB:
            out.add(inst['at'])
    return out


def _srgb(c):
    c = max(0.0, min(1.0, float(c)))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _nodes(bl, mat_at):
    tree = bl.block(bl.get('Material', mat_at, 'nodetree')) if mat_at else None
    return [(bl.get('bNode', n, 'idname', ''), n) for n in bl.listbase(bl.get('bNodeTree', tree['at'], 'nodes'), 'bNode')] if tree else []


def _ramp(bl, mat_at):
    """A Color Ramp in the material (its colours over a particle's life): [(pos, r, g, b, a)], sRGB."""
    for idname, n in _nodes(bl, mat_at):
        if idname != 'ShaderNodeValToRGB':
            continue
        cb = bl.block(bl.get('bNode', n, 'storage'))
        if not cb:
            continue
        tot = max(0, min(32, bl.get('ColorBand', cb['at'], 'tot') or 0))
        at0, sz = bl.get('ColorBand', cb['at'], 'data'), bl.size_of('CBData')
        keys = []
        for i in range(tot):
            d = at0 + i * sz
            keys.append((max(0.0, min(1.0, bl.get('CBData', d, 'pos'))), _srgb(bl.get('CBData', d, 'r')),
                         _srgb(bl.get('CBData', d, 'g')), _srgb(bl.get('CBData', d, 'b')),
                         max(0.0, min(1.0, bl.get('CBData', d, 'a')))))
        keys.sort()
        if keys:
            if keys[0][0] > 0:
                keys.insert(0, (0.0,) + keys[0][1:])
            if keys[-1][0] < 1:
                keys.append((1.0,) + keys[-1][1:])
            return keys
    return []


def _axes(M):
    """A 4x4 matrix's rotation (columns made unit length) and its scale on each axis."""
    sc = [math.sqrt(sum(M[r][c] ** 2 for r in range(3))) or 1.0 for c in range(3)]
    return [[M[r][c] / sc[c] for c in range(3)] for r in range(3)], sc


def particles(path):
    """The file's emitter particle systems, in Blender's own space (metres, Z up), each as the game's single
    cone emitter: {'name', 'object', 'at' (the emitter's middle), 'R' (its turn), 'box' (its size on its own
    axes), 'speed', 'speed_random', 'v_dir', 'v_angle', 'h_dir', 'h_angle' (radians, on the emitter's axes),
    'rate' (a second), 'duration', 'life', 'life_random' (seconds), 'size' (a particle's radius), 'accel'
    (gravity and winds together, metres a second a second), 'colors' [(t, r, g, b, a)], 'color', 'glow',
    'picture', 'left' [what did not come along]}."""
    bl = Blend(open(path, 'rb').read())
    folder = os.path.dirname(os.path.abspath(path))
    out = []
    systems = _systems(bl)
    if not systems:
        return out
    sc = next((b['at'] for b in bl.blocks if b['code'][:2] == b'SC'), None)
    fps, gravity = 24.0, [0.0, 0.0, -9.81]
    if sc is not None:
        r = bl.get('Scene', sc, 'r')
        fps = (bl.get('RenderData', r, 'frs_sec') or 24) / (bl.get('RenderData', r, 'frs_sec_base') or 1.0)
        ph = bl.get('Scene', sc, 'physics_settings')
        gravity = bl.get('PhysicsSettings', ph, 'gravity') if (bl.get('PhysicsSettings', ph, 'flag') or 0) & 1 else [0.0, 0.0, 0.0]
    winds = []
    for b in bl.blocks:
        if b['code'][:2] != b'OB':
            continue
        pd = bl.block(bl.get('Object', b['at'], 'pd'))
        if pd and bl.get('PartDeflect', pd['at'], 'forcefield') == PFIELD_WIND and bl.get('PartDeflect', pd['at'], 'f_strength'):
            R, _s = _axes(_world(bl, b['at']))
            winds.append(([R[0][2], R[1][2], R[2][2]], bl.get('PartDeflect', pd['at'], 'f_strength'), b['at']))
    for ob, psy, pa in systems:
        g = lambda k, d=0.0: bl.get('ParticleSettings', pa, k, d)
        left = []
        M = _world(bl, ob)
        R, scale = _axes(M)
        meb = bl.block(bl.get('Object', ob, 'data'))
        m = _mesh(bl, meb['at']) if meb and meb['code'][:2] == b'ME' else None
        verts = m['verts'] if m else [(0.0, 0.0, 0.0)]
        lo = [min(v[k] for v in verts) for k in range(3)]
        hi = [max(v[k] for v in verts) for k in range(3)]
        mid = [(lo[k] + hi[k]) / 2 for k in range(3)]
        at = [sum(M[r][k] * (mid + [1.0])[k] for k in range(4)) for r in range(3)]
        box = [(hi[k] - lo[k]) * scale[k] for k in range(3)]
        # the way they leave: the faces' mean normal (or the object's Z), plus the object-aligned push
        normal, spread_n = [0.0, 0.0, 1.0], 0.0
        if m and m['faces'] and g('from', 1) in (PART_FROM_FACE, PART_FROM_VOLU, PART_FROM_VERT):
            ns = []
            for start, count in m['faces']:
                pts = [verts[m['corner_vert'][c]] for c in range(start, start + count) if c < len(m['corner_vert'])]
                if len(pts) < 3:
                    continue
                nx = ny = nz = 0.0
                for i in range(len(pts)):            # Newell's way: works for any polygon
                    a, b2 = pts[i], pts[(i + 1) % len(pts)]
                    nx += (a[1] - b2[1]) * (a[2] + b2[2])
                    ny += (a[2] - b2[2]) * (a[0] + b2[0])
                    nz += (a[0] - b2[0]) * (a[1] + b2[1])
                ns.append((nx, ny, nz))
            tot = [sum(n[k] for n in ns) for k in range(3)]
            area = sum(math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) for n in ns)
            L = math.sqrt(sum(t * t for t in tot))
            if area > 0 and L / area > 0.3:
                normal = [t / L for t in tot]
                cos = [sum(n[k] * normal[k] for k in range(3)) / (math.sqrt(sum(x * x for x in n)) or 1) for n in ns if any(n)]
                spread_n = math.acos(max(-1.0, min(1.0, min(cos)))) if cos else 0.0
            elif area > 0:
                spread_n = math.pi                  # (a ball or a closed shape: every way)
        nf, ov = g('normfac'), g('ob_vel') or [0.0, 0.0, 0.0]
        vel = [normal[k] * nf + ov[k] for k in range(3)]
        speed = math.sqrt(sum(v * v for v in vel))
        rnd = abs(g('randfac'))
        if speed > 1e-6:
            d = [v / speed for v in vel]
            spread = spread_n * abs(nf) / (abs(nf) + math.sqrt(sum(v * v for v in ov)) or 1)
            spread = min(math.pi, spread + math.atan2(rnd * 0.6, speed))
        else:
            d, spread, speed = [0.0, 0.0, 1.0], math.pi, rnd / 2
        v_dir = math.acos(max(-1.0, min(1.0, d[2])))
        h_dir = math.atan2(d[1], d[0]) if v_dir > 1e-3 else 0.0
        h_angle = math.pi if v_dir < 1e-3 or spread >= v_dir else min(math.pi, spread / max(math.sin(v_dir), 1e-3))
        if g('tanfac'):
            left.append('tangent speed')
        if g('obfac'):
            left.append('speed from the moving object')
        # when and how long
        sta, end = g('sta', 1.0), g('end', 200.0)
        duration = max(1.0, end - sta) / fps
        total = max(1, bl.get('ParticleSettings', pa, 'totpart') or 1)
        life_f, rl = max(1.0, g('lifetime', 50.0)), max(0.0, min(1.0, g('randlife')))
        size = g('size', 0.05)
        inst = bl.block(bl.get('ParticleSettings', pa, 'dup_ob'))
        if inst and (g('ren_as', 0) or 0) == PART_DRAW_OB:
            ib = bl.block(bl.get('Object', inst['at'], 'data'))
            im = _mesh(bl, ib['at']) if ib and ib['code'][:2] == b'ME' else None
            if im:
                _R, isc = _axes(_world(bl, inst['at']))
                size *= max((max(v[k] for v in im['verts']) - min(v[k] for v in im['verts'])) * isc[k] for k in range(3)) / 2
        if g('randsize'):
            size *= 1 - g('randsize') / 2          # (the game has one size: the middle one)
        if g('avefac'):
            left.append('spin')
        # pulls: the scene's gravity by the system's gravity weight, and each wind by its weight
        ew = bl.block(bl.get('ParticleSettings', pa, 'effector_weights'))
        gw = bl.get('EffectorWeights', ew['at'], 'global_gravity', 1.0) if ew else 1.0
        ww = bl.get('EffectorWeights', ew['at'], 'weight') if ew else None
        wind_w = ww[PFIELD_WIND] if isinstance(ww, list) and len(ww) > PFIELD_WIND else 1.0
        mass = max(1e-3, g('mass', 1.0))
        # (a system given a collection of its own forces feels only those: a game effect sent to Blender has one)
        mine = winds
        grp = bl.block(bl.get('EffectorWeights', ew['at'], 'group')) if ew else None
        if grp:
            obs = {bl.block(bl.get('CollectionObject', co, 'ob'))['at'] for co in
                   bl.listbase(bl.get('Collection', grp['at'], 'gobject'), 'CollectionObject')
                   if bl.block(bl.get('CollectionObject', co, 'ob'))}
            mine = [w for w in winds if w[2] in obs]
        accel = [gravity[k] * gw + sum(w[0][k] * w[1] for w in mine) * wind_w / mass for k in range(3)]
        # the look: the material on the particles' slot
        slots = []
        n_ob = bl.get('Object', ob, 'totcol') or 0
        ob_slots = bl.array(bl.get('Object', ob, 'mat'), 'Q' if bl.psize == 8 else 'I', n_ob) or []
        n_me = bl.get('Mesh', meb['at'], 'totcol') or 0 if meb and meb['code'][:2] == b'ME' else 0
        me_slots = bl.array(bl.get('Mesh', meb['at'], 'mat'), 'Q' if bl.psize == 8 else 'I', n_me) or [] if n_me else []
        matbits = bl.array(bl.get('Object', ob, 'matbits'), 'b', n_ob) or []
        for i in range(max(len(ob_slots), len(me_slots))):
            ptr = ob_slots[i] if i < len(matbits) and matbits[i] and i < len(ob_slots) else (me_slots[i] if i < len(me_slots) else 0)
            mb = bl.block(ptr)
            slots.append(mb['at'] if mb else None)
        omat = (g('omat', 1) or 1) - 1
        mat = slots[omat] if 0 <= omat < len(slots) else None
        if mat is None and inst:
            ib = bl.block(bl.get('Object', inst['at'], 'data'))
            n = bl.get('Mesh', ib['at'], 'totcol') or 0 if ib and ib['code'][:2] == b'ME' else 0
            ims = bl.array(bl.get('Mesh', ib['at'], 'mat'), 'Q' if bl.psize == 8 else 'I', n) or [] if n else []
            mb = bl.block(ims[0]) if ims else None
            mat = mb['at'] if mb else None
        kinds = {k for k, _n in _nodes(bl, mat)}
        col = [1.0, 1.0, 1.0, 1.0]
        if mat is not None:
            c = _colour(bl, mat)
            a = bl.get('Material', mat, 'a', 1.0)
            col = [_srgb(c[0]), _srgb(c[1]), _srgb(c[2]), max(0.0, min(1.0, a if a is not None else 1.0))]
        out.append({'name': bl.get('ParticleSystem', psy, 'name', '') or 'Particles', 'object': bl.name_of(ob),
                    'at': at, 'R': R, 'box': box, 'speed': speed, 'speed_random': rnd,
                    'v_dir': v_dir, 'v_angle': spread, 'h_dir': h_dir, 'h_angle': h_angle,
                    'rate': total / duration, 'duration': duration,
                    'life': life_f * (1 - rl) / fps, 'life_random': life_f * rl / fps, 'size': size, 'accel': accel,
                    'colors': _ramp(bl, mat), 'color': col,
                    'glow': bool(kinds & {'ShaderNodeEmission', 'ShaderNodeAddShader'}),
                    'picture': _picture(bl, mat, folder) if mat is not None else None, 'left': left})
        pic = out[-1]['picture']
        out[-1]['picture_key'] = _key(pic['raw'] if isinstance(pic, dict) else open(pic, 'rb').read() if pic else b'')
    return out


def _key(raw):
    import hashlib
    return hashlib.sha1(raw).hexdigest() if raw else ''


def helper_names(path):
    """The names of a file's particle helpers (blendread.read_blend leaves them out; so does the way back)."""
    bl = Blend(open(path, 'rb').read())
    return {bl.name_of(ob) for ob in _particle_helpers(bl)}
