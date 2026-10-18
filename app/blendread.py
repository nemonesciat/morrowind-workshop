"""Reading Blender's own files (.blend) without Blender: the meshes of its objects, placed as in the
scene, with their UV maps and the pictures their materials use. Blender 2.80 and newer, compressed or
not. Modifiers are not applied, except Mirror (so half-modelled bodies come out whole)."""
import math
import os
import struct

from editing import EditError


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
        self.blocks, self.by_ptr = [], {}
        while pos + 8 <= len(raw):
            code = raw[pos:pos + 4]
            if self.new_head:
                sdna, old, ln, cnt = struct.unpack_from(self.e + 'iQqq', raw, pos + 4)
                hs = 36
            else:
                ln, = struct.unpack_from(self.e + 'i', raw, pos + 4)
                old, = struct.unpack_from(self.e + ('Q' if self.psize == 8 else 'I'), raw, pos + 8)
                sdna, cnt = struct.unpack_from(self.e + 'ii', raw, pos + 8 + self.psize)
                hs = 16 + self.psize
            b = {'code': code, 'at': pos + hs, 'len': ln, 'sdna': sdna, 'count': cnt}
            self.blocks.append(b)
            if old:
                self.by_ptr[old] = b
            pos += hs + ln
            if code == b'ENDB':
                break
        self._dna()

    def _dna(self):
        raw, e = self.raw, self.e
        dna = next((b for b in self.blocks if b['code'] == b'DNA1'), None)
        if not dna:
            raise EditError('This Blender file has no description of its contents.')
        p = dna['at'] + 8

        def strings(p, n):
            out = []
            for _ in range(n):
                q = raw.index(b'\0', p)
                out.append(raw[p:q].decode('latin-1'))
                p = q + 1
            return out, (p + 3) & ~3
        n, = struct.unpack_from(e + 'i', raw, p)
        names, p = strings(p + 4, n)
        n, = struct.unpack_from(e + 'i', raw, p + 4)
        types, p = strings(p + 8, n)
        tlen = struct.unpack_from(e + '%dh' % n, raw, p + 4)
        p = (p + 4 + 2 * n + 3) & ~3
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
                return struct.unpack_from(e + fmt, raw, p)[0]
            return list(struct.unpack_from(e + '%d%s' % (count, fmt), raw, p))
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
        return self.by_ptr.get(ptr) if ptr else None

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
    (like the other readers), with the object's name on each part."""
    bl = Blend(open(path, 'rb').read())
    folder = os.path.dirname(os.path.abspath(path))
    parts, cache = [], {}
    for b in bl.blocks:
        if b['code'][:2] != b'OB' or bl.get('Object', b['at'], 'type') != 1:
            continue
        ob = b['at']
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
    if not parts:
        raise EditError('There are no meshes in this Blender file to bring in.')
    return parts
