"""Reads object sizes (bounding boxes) out of Morrowind .nif meshes, so the map can
draw real footprints and new objects can be set down on floors and tables."""
import json
import os
import re
import struct
import threading

HEADER = b'NetImmerse File Format, Version 4.0.0.2\n'
TYPE_START = re.compile(rb'[\x04-\x30]\x00\x00\x00(?=Ni|RootCollisionNode|AvoidNode|BS)')
NODE_TYPES = {b'NiNode', b'NiBSAnimationNode', b'NiBSParticleNode', b'NiBillboardNode', b'RootCollisionNode',
              b'AvoidNode', b'NiSwitchNode', b'NiLODNode'}
GEOM_TYPES = {b'NiTriShape', b'NiTriStrips'}
SKIP_SUBTREES = {b'RootCollisionNode', b'AvoidNode'}

CACHE_VERSION = 5      # 3: the root node's transform ignored, as the game does; 4: a type name as extra-data text; 5: a root mesh keeps its transform
_IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _blocks(data):
    """Return [(type, offset_after_type_string)] for every block, or None if unsure."""
    if not data.startswith(HEADER):
        return None
    pos = len(HEADER)
    _ver, n = struct.unpack_from('<II', data, pos)
    pos += 8
    found = []
    last_end = -1
    for m in TYPE_START.finditer(data, pos):
        p = m.start()
        L = data[p]
        name = data[p + 4:p + 4 + L]
        if len(name) != L or not name.isalpha():
            continue
        if p == last_end:
            # Usually this is the object's own name right after its type, not a new block. But a
            # NiStringExtraData whose text is itself a type name ("NiTriShape", in Tamriel Rebuilt's
            # tr_a_histcuirass.nif) is followed by the real block: then the earlier match was that text
            # (an extra data's string sits after its next-ref and a "bytes remaining" of 4 + its length).
            prev_start = found[-1][2]
            if (len(found) >= 2 and found[-2][0] == b'NiStringExtraData' and found[-2][1] + 8 == prev_start
                    and struct.unpack_from('<I', data, prev_start - 4)[0] == 4 + data[prev_start]):
                found[-1] = (name, p + 4 + L, p)
                last_end = p + 4 + L
            continue
        found.append((name, p + 4 + L, p))
        last_end = p + 4 + L
    if len(found) != n or found[0][2] != pos:
        return None
    return [(name, after) for name, after, _start in found]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(R, v):
    return [R[i][0] * v[0] + R[i][1] * v[1] + R[i][2] * v[2] for i in range(3)]


def _read_av(data, p):
    nlen = struct.unpack_from('<I', data, p)[0]
    p += 4 + nlen + 8                    # name, extra data, controller
    flags = struct.unpack_from('<H', data, p)[0]
    p += 2
    t = list(struct.unpack_from('<3f', data, p))
    p += 12
    r = struct.unpack_from('<9f', data, p)
    p += 36
    s = struct.unpack_from('<f', data, p)[0]
    p += 4 + 12                          # scale, velocity
    nprops = struct.unpack_from('<I', data, p)[0]
    p += 4 + 4 * nprops
    has_bv = struct.unpack_from('<I', data, p)[0]
    p += 4
    if has_bv:
        bt = struct.unpack_from('<I', data, p)[0]
        p += 4
        if bt == 0:
            p += 16
        elif bt == 1:
            p += 60
        else:
            raise ValueError('bounding volume type %d' % bt)
    R = [list(r[0:3]), list(r[3:6]), list(r[6:9])]
    return flags, (R, t, s), p


def bounds_from_nif(data):
    blocks = _blocks(data)
    if not blocks:
        return None
    lo = [1e18] * 3
    hi = [-1e18] * 3
    seen = set()

    def visit(i, R, t, s):
        if i < 0 or i >= len(blocks) or i in seen:
            return
        seen.add(i)
        typ, p = blocks[i]
        if typ in SKIP_SUBTREES:
            return
        if typ in NODE_TYPES or typ in GEOM_TYPES:
            flags, (lR, lt, ls), p = _read_av(data, p)
            if flags & 1 and i != 0:
                return                   # hidden
            if i == 0 and typ in NODE_TYPES:
                lR, lt, ls = _IDENTITY, (0.0, 0.0, 0.0), 1.0     # (the game ignores the root NODE's own transform; a root mesh keeps its own)
            nR = _mul(R, lR)
            nt = [t[k] + s * v for k, v in enumerate(_apply(R, lt))]
            ns = s * ls
            if typ in NODE_TYPES:
                nc = struct.unpack_from('<I', data, p)[0]
                kids = struct.unpack_from('<%di' % nc, data, p + 4)
                for k in kids:
                    visit(k, nR, nt, ns)
            else:
                dref = struct.unpack_from('<i', data, p)[0]
                if 0 <= dref < len(blocks):
                    _geom(blocks[dref][1], nR, nt, ns)

    def _geom(p, R, t, s):
        nv = struct.unpack_from('<H', data, p)[0]
        has = struct.unpack_from('<I', data, p + 2)[0]
        if not has or not nv:
            return
        verts = struct.unpack_from('<%df' % (nv * 3), data, p + 6)
        for k in range(0, nv * 3, 3):
            v = _apply(R, verts[k:k + 3])
            for a in range(3):
                w = t[a] + s * v[a]
                if w < lo[a]:
                    lo[a] = w
                if w > hi[a]:
                    hi[a] = w

    I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    visit(0, I, [0, 0, 0], 1.0)
    if lo[0] > hi[0]:
        return None
    return [round(v, 1) for v in lo + hi]


def _str(data, p):
    n = struct.unpack_from('<I', data, p)[0]
    return data[p + 4:p + 4 + n].decode('cp1252', 'replace'), p + 4 + n


def _texture_of(data, blocks, prop_refs):
    """Base texture file name from a list of property refs (NiTexturingProperty -> NiSourceTexture)."""
    alpha = False
    double = False
    tex = None
    for pr in prop_refs:
        if not 0 <= pr < len(blocks):
            continue
        typ, p = blocks[pr]
        if typ == b'NiAlphaProperty':
            alpha = True
        elif typ == b'NiStencilProperty':
            # draw mode: 0 default (front only), 1 front, 2 back, 3 both sides
            _name, q = _str(data, p)
            q += 8 + 2 + 1 + 4 * 6
            if q + 4 <= len(data) and struct.unpack_from('<I', data, q)[0] in (2, 3):
                double = True
        elif typ == b'NiTexturingProperty':
            _name, p = _str(data, p)
            p += 8 + 2 + 4                       # extra data, controller, flags, apply mode
            _count, has_base = struct.unpack_from('<II', data, p)
            p += 8
            if has_base:
                src = struct.unpack_from('<i', data, p)[0]
                if 0 <= src < len(blocks) and blocks[src][0] == b'NiSourceTexture':
                    sp = blocks[src][1]
                    _n, sp = _str(data, sp)
                    sp += 8
                    if data[sp] == 1:            # external file
                        tex, _ = _str(data, sp + 1)
    return tex, alpha, double


def _geometry(data, p, strips):
    """Vertices, UVs and triangle indices of a NiTriShapeData / NiTriStripsData block."""
    nv = struct.unpack_from('<H', data, p)[0]
    p += 2
    has_v = struct.unpack_from('<I', data, p)[0]
    p += 4
    verts = struct.unpack_from('<%df' % (nv * 3), data, p) if has_v else ()
    p += nv * 12 if has_v else 0
    has_n = struct.unpack_from('<I', data, p)[0]
    p += 4 + (nv * 12 if has_n else 0)
    p += 16                                      # bounding sphere
    has_c = struct.unpack_from('<I', data, p)[0]
    p += 4 + (nv * 16 if has_c else 0)
    n_uv = struct.unpack_from('<H', data, p)[0]
    p += 2
    has_uv = struct.unpack_from('<I', data, p)[0]
    p += 4
    uvs = struct.unpack_from('<%df' % (nv * 2), data, p) if has_uv and n_uv else ()
    p += nv * 8 * n_uv if has_uv else 0
    idx = []
    if not strips:
        nt = struct.unpack_from('<H', data, p)[0]
        p += 2 + 4
        idx = list(struct.unpack_from('<%dH' % (nt * 3), data, p))
    else:
        _nt, ns = struct.unpack_from('<HH', data, p)
        p += 4
        lens = struct.unpack_from('<%dH' % ns, data, p)
        p += ns * 2
        for L in lens:
            pts = struct.unpack_from('<%dH' % L, data, p)
            p += L * 2
            for k in range(L - 2):
                a, b, c = pts[k], pts[k + 1], pts[k + 2]
                if a == b or b == c or a == c:
                    continue
                idx += [a, b, c] if k % 2 == 0 else [a, c, b]
    return verts, uvs, idx


def mesh_from_nif(data, max_verts=60000):
    """Triangles of a model in its own coordinates, with texture names, for the 3D preview."""
    blocks = _blocks(data)
    if not blocks:
        return None
    shapes = []
    seen = set()
    total = [0]

    def visit(i, R, t, s, inherited):
        if i < 0 or i >= len(blocks) or i in seen or total[0] > max_verts:
            return
        seen.add(i)
        typ, p = blocks[i]
        if typ in SKIP_SUBTREES or not (typ in NODE_TYPES or typ in GEOM_TYPES):
            return
        _name, q = _str(data, p)
        q += 8
        flags = struct.unpack_from('<H', data, q)[0]
        _f, (lR, lt, ls), p2 = _read_av(data, p)
        if flags & 1 and i != 0:
            return
        if i == 0 and typ in NODE_TYPES:
            # The game ignores the root NODE's own transform (Morrowind, and OpenMW for it). Measured on
            # Ald-ruhn, Sarethi Manor: in_redoran_l_3way_01's root is turned 180°, and only with that turn
            # ignored do its three-way pieces at x=0 open east onto the corner and three-way at x=512, as
            # the game's hall does. 268 of the game's placed models carry such a root transform.
            # A model whose root is its mesh itself keeps its transform: contain_crate_01's root shape
            # is shifted 32 down, and the game's own crates all stand with their origin 32 over the
            # floor (the user's crates, laid with the shift ignored, sank 32 into the floor in game).
            lR, lt, ls = _IDENTITY, (0.0, 0.0, 0.0), 1.0
        # property refs sit just before the bounding-volume flag: re-read them
        q = q + 2 + 12 + 36 + 4 + 12
        nprops = struct.unpack_from('<I', data, q)[0]
        props = list(struct.unpack_from('<%di' % nprops, data, q + 4)) + inherited
        nR = _mul(R, lR)
        nt = [t[k] + s * v for k, v in enumerate(_apply(R, lt))]
        ns = s * ls
        if typ in NODE_TYPES:
            nc = struct.unpack_from('<I', data, p2)[0]
            for k in struct.unpack_from('<%di' % nc, data, p2 + 4):
                visit(k, nR, nt, ns, props)
            return
        dref = struct.unpack_from('<i', data, p2)[0]
        if not 0 <= dref < len(blocks):
            return
        dtyp, dp = blocks[dref]
        if dtyp not in (b'NiTriShapeData', b'NiTriStripsData'):
            return
        verts, uvs, idx = _geometry(data, dp, dtyp == b'NiTriStripsData')
        if not verts or not idx:
            return
        pos = []
        for k in range(0, len(verts), 3):
            v = _apply(nR, verts[k:k + 3])
            pos += [round(nt[a] + ns * v[a], 2) for a in range(3)]
        tex, alpha, double = _texture_of(data, blocks, props)
        # a mirrored node turns its triangles inside out: flip them back so the right side faces out
        det = (nR[0][0] * (nR[1][1] * nR[2][2] - nR[1][2] * nR[2][1]) - nR[0][1] * (nR[1][0] * nR[2][2] - nR[1][2] * nR[2][0])
               + nR[0][2] * (nR[1][0] * nR[2][1] - nR[1][1] * nR[2][0]))
        if det < 0:
            idx = [v for k in range(0, len(idx) - 2, 3) for v in (idx[k], idx[k + 2], idx[k + 1])]
        shapes.append({'p': pos, 'uv': [round(u, 4) for u in uvs], 'i': idx, 'tex': tex, 'alpha': alpha, 'double': double})
        total[0] += len(verts) // 3

    I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    visit(0, I, [0, 0, 0], 1.0, [])
    return shapes


class MeshIndex:
    """Finds mesh files in loose folders and BSA archives, and caches their bounds."""

    def __init__(self, cache_path):
        self.loose = {}      # rel path -> full path
        self.packed = {}     # rel path -> (bsa path, offset, size)
        self.cache_path = cache_path
        self.lock = threading.Lock()
        self.dirty = False
        self.cache = {}
        try:
            with open(cache_path, encoding='utf-8') as f:
                d = json.load(f)
            if d.get('v') == CACHE_VERSION:
                self.cache = d['bounds']
        except (OSError, ValueError, KeyError):
            pass

    def read(self, rel):
        rel = rel.lower().replace('\\', '/')
        if rel in self.loose:
            with open(self.loose[rel], 'rb') as f:
                return f.read()
        if rel in self.packed:
            path, off, size = self.packed[rel]
            with open(path, 'rb') as f:
                f.seek(off)
                return f.read(size)
        return None

    def texture_path(self, name):
        """Find a texture file the way the game does (folder 'textures', .dds preferred)."""
        if not name:
            return None
        n = name.lower().replace('\\', '/')
        if not n.startswith('textures/'):
            n = 'textures/' + n
        base = n.rsplit('.', 1)[0]
        for cand in (base + '.dds', n, base + '.tga', base + '.bmp', base + '.png', base + '.jpg'):
            if cand in self.loose or cand in self.packed:
                return cand
        return None

    def bounds(self, model):
        if not model:
            return None
        rel = 'meshes/' + model.lower().replace('\\', '/')
        if rel in self.cache:
            return self.cache[rel]
        b = None
        try:
            data = self.read(rel)
            if data:
                b = bounds_from_nif(data)
        except Exception:
            b = None
        with self.lock:
            self.cache[rel] = b
            self.dirty = True
        return b

    def save(self):
        if not self.dirty:
            return
        with self.lock:
            # (the survey processes and the Workshop itself share this file: each writes its own
            # temporary file, keeps what another process put on disk meanwhile, and a write that loses
            # the race is tried again next time rather than failing the build or furnish that called it.
            # Measured 2026-10-22: with one shared ".tmp" name, every house of the detector suite failed
            # with "the process cannot access the file because it is being used by another process")
            try:
                os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
                try:
                    with open(self.cache_path, encoding='utf-8') as f:
                        d = json.load(f)
                    if d.get('v') == CACHE_VERSION and isinstance(d.get('bounds'), dict):
                        for k, v in d['bounds'].items():
                            self.cache.setdefault(k, v)
                except (OSError, ValueError, KeyError, AttributeError):
                    pass
                tmp = '%s.%d.tmp' % (self.cache_path, os.getpid())
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump({'v': CACHE_VERSION, 'bounds': self.cache}, f)
                os.replace(tmp, self.cache_path)
                self.dirty = False
            except OSError:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
