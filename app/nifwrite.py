"""Writes simple Morrowind .nif models (NetImmerse 4.0.0.2): a root node with one textured shape per
material. Used for models brought in from other programs (OBJ, glTF), so they work in the game and in
the Workshop like any Morrowind model. With no collision node, OpenMW collides with the shapes themselves.

A part: {'name', 'verts': [(x, y, z)], 'normals': [(x, y, z)] or None, 'uvs': [(u, v)] or None,
'tris': [(a, b, c)], 'texture': 'wslib\\name.png' or None, 'color': (r, g, b) 0..1, 'alpha': bool,
'double': bool, 'glow': bool or (r, g, b)}. Coordinates are the game's: Z up, in game units."""
import math
import struct

HEADER = b'NetImmerse File Format, Version 4.0.0.2\n'
VERSION = 0x04000002


def _s(text):
    b = (text or '').encode('cp1252', 'replace')
    return struct.pack('<I', len(b)) + b


def _net(name):
    """NiObjectNET: name, extra data, controller."""
    return _s(name) + struct.pack('<ii', -1, -1)


def _av(name, flags, props):
    """NiAVObject (after its type): at the origin, no rotation, scale 1."""
    return (_net(name) + struct.pack('<H', flags) + struct.pack('<3f', 0, 0, 0) +
            struct.pack('<9f', 1, 0, 0, 0, 1, 0, 0, 0, 1) + struct.pack('<f', 1.0) + struct.pack('<3f', 0, 0, 0) +
            struct.pack('<I', len(props)) + b''.join(struct.pack('<i', p) for p in props) + struct.pack('<I', 0))


def _normals(verts, tris):
    acc = [[0.0, 0.0, 0.0] for _ in verts]
    for a, b, c in tris:
        A, B, C = verts[a], verts[b], verts[c]
        ux, uy, uz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
        vx, vy, vz = C[0] - A[0], C[1] - A[1], C[2] - A[2]
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        for i in (a, b, c):
            for k in range(3):
                acc[i][k] += n[k]
    out = []
    for n in acc:
        L = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
        out.append((n[0] / L, n[1] / L, n[2] / L))
    return out


def _split(part, limit=65000):
    """Shapes can have at most 65535 corners: big parts become several."""
    if len(part['verts']) <= limit:
        return [part]
    out, cur, remap = [], None, None
    for tri in part['tris']:
        if cur is None or len(cur['verts']) > limit - 3:
            cur = dict(part, verts=[], normals=[] if part.get('normals') else None, uvs=[] if part.get('uvs') else None, tris=[])
            remap = {}
            out.append(cur)
        nt = []
        for i in tri:
            if i not in remap:
                remap[i] = len(cur['verts'])
                cur['verts'].append(part['verts'][i])
                if cur['normals'] is not None:
                    cur['normals'].append(part['normals'][i])
                if cur['uvs'] is not None:
                    cur['uvs'].append(part['uvs'][i])
            nt.append(remap[i])
        cur['tris'].append(tuple(nt))
    return out


def _box_part(parts):
    """A plain box round all the parts: what the game bumps into instead of every triangle."""
    vs = [v for p in parts for v in p['verts']]
    lo = [min(v[k] for v in vs) for k in range(3)]
    hi = [max(v[k] for v in vs) for k in range(3)]
    c = [(x, y, z) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    tris = [t for a, b, cc, d in quads for t in ((a, b, cc), (a, cc, d))]
    return {'name': 'Collision box', 'verts': c, 'normals': None, 'uvs': None, 'tris': tris}


def write_nif(parts, root_name='Scene Root', collision='shape'):
    """The bytes of a .nif file holding these parts. collision: 'shape' (bump into it as it is
    shaped), 'box' (a plain box round it), or 'none' (walk through it)."""
    parts = [p for part in parts if part['verts'] and part['tris'] for p in _split(part)]
    if not parts:
        raise ValueError('There is nothing to draw in this model (no triangles).')
    blocks = []                          # (type, body) in order; refs are positions in this list

    def add(typ, body=b''):
        blocks.append([typ, body])
        return len(blocks) - 1
    root = add('NiNode')
    shapes = []
    for n, part in enumerate(parts):
        verts, tris = part['verts'], part['tris']
        normals = part.get('normals') or _normals(verts, tris)
        uvs = part.get('uvs')
        props = []
        if part.get('texture'):
            src = add('NiSourceTexture', _net('') + b'\x01' + _s(part['texture']) + struct.pack('<III', 6, 2, 3) + b'\x01')
            tp = add('NiTexturingProperty', _net('') + struct.pack('<H', 0) + struct.pack('<I', 2) + struct.pack('<I', 7) +
                     struct.pack('<I', 1) + struct.pack('<iIIIhhH', src, 3, 2, 0, 0, -75, 0) + struct.pack('<6I', 0, 0, 0, 0, 0, 0))
            props.append(tp)
        col = part.get('color') or (1.0, 1.0, 1.0)
        # a lamp's parts glow (lit from inside, whatever light falls on them)
        glow = tuple(part['glow']) if isinstance(part.get('glow'), (list, tuple)) else ((1.0, 1.0, 1.0) if part.get('glow') else (0, 0, 0))
        props.append(add('NiMaterialProperty', _net('') + struct.pack('<H', 1) +
                         struct.pack('<3f', *col) + struct.pack('<3f', *col) + struct.pack('<3f', 0, 0, 0) +
                         struct.pack('<3f', *glow) + struct.pack('<ff', 10.0, part.get('opacity', 1.0))))
        if part.get('alpha'):
            props.append(add('NiAlphaProperty', _net('') + struct.pack('<H', 237) + b'\x00'))
        if part.get('double'):
            # draw both sides (leaves, cloth, thin walls)
            props.append(add('NiStencilProperty', _net('') + struct.pack('<H', 0) + b'\x00' +
                             struct.pack('<6I', 3, 0, 0xFFFFFFFF, 0, 0, 0) + struct.pack('<I', 3) + struct.pack('<H', 0)[:0]))
        # bounding sphere of the shape
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        cz = sum(v[2] for v in verts) / len(verts)
        rad = max(math.sqrt((v[0] - cx) ** 2 + (v[1] - cy) ** 2 + (v[2] - cz) ** 2) for v in verts)
        data = struct.pack('<H', len(verts)) + struct.pack('<I', 1) + b''.join(struct.pack('<3f', *v) for v in verts)
        data += struct.pack('<I', 1) + b''.join(struct.pack('<3f', *v) for v in normals)
        data += struct.pack('<4f', cx, cy, cz, rad)
        data += struct.pack('<I', 0)                                    # no vertex colours
        if uvs:
            data += struct.pack('<H', 1) + struct.pack('<I', 1) + b''.join(struct.pack('<2f', *uv) for uv in uvs)
        else:
            data += struct.pack('<H', 0) + struct.pack('<I', 0)
        data += struct.pack('<H', len(tris)) + struct.pack('<I', len(tris) * 3)
        data += b''.join(struct.pack('<3H', *t) for t in tris)
        data += struct.pack('<H', 0)                                    # no match groups
        dref = add('NiTriShapeData', data)
        shape = add('NiTriShape')
        blocks[shape][1] = _av(part.get('name') or 'Tri Shape %d' % n, 4, props) + struct.pack('<ii', dref, -1)
        shapes.append(shape)
    kids = list(shapes)
    if collision in ('box', 'none'):
        # a RootCollisionNode: the game collides with what's in it instead of the visible shapes
        # (nothing in it: nothing to bump into)
        inner = []
        if collision == 'box':
            bp = _box_part(parts)
            d = struct.pack('<H', 8) + struct.pack('<I', 1) + b''.join(struct.pack('<3f', *v) for v in bp['verts'])
            d += struct.pack('<I', 0) + struct.pack('<4f', 0, 0, 0, 0) + struct.pack('<I', 0)
            d += struct.pack('<H', 0) + struct.pack('<I', 0)
            d += struct.pack('<H', 12) + struct.pack('<I', 36) + b''.join(struct.pack('<3H', *t) for t in bp['tris'])
            d += struct.pack('<H', 0)
            bd = add('NiTriShapeData', d)
            bs = add('NiTriShape')
            blocks[bs][1] = _av('Collision box', 4, []) + struct.pack('<ii', bd, -1)
            inner.append(bs)
        rc = add('RootCollisionNode')
        blocks[rc][1] = _av('Collision', 0, []) + struct.pack('<I', len(inner)) + b''.join(struct.pack('<i', s) for s in inner) + \
            struct.pack('<I', 0)
        kids.append(rc)
    blocks[root][1] = _av(root_name, 12, []) + struct.pack('<I', len(kids)) + b''.join(struct.pack('<i', s) for s in kids) + \
        struct.pack('<I', 0)
    out = HEADER + struct.pack('<II', VERSION, len(blocks))
    for typ, body in blocks:
        out += _s(typ) + body
    out += struct.pack('<Ii', 1, root)                                  # one root: the node
    return out


def retexture(data, mapping):
    """A copy of a .nif with texture file names swapped: mapping {old name (lower case): new name}.
    Strings in NiSourceTexture blocks are rewritten; blocks refer to each other by number, not by
    position, so names may change length. Returns (new bytes, how many were swapped)."""
    import nif
    blocks = nif._blocks(data)
    if not blocks:
        raise ValueError('This model could not be read.')
    out, last, n = [], 0, 0
    for typ, p in blocks:
        if typ != b'NiSourceTexture':
            continue
        _name, q = nif._str(data, p)
        q += 8
        if data[q] != 1:
            continue
        L = struct.unpack_from('<I', data, q + 1)[0]
        old = data[q + 5:q + 5 + L].decode('cp1252', 'replace')
        key = old.lower().replace('/', '\\')
        new = mapping.get(key) or mapping.get(key.rsplit('\\', 1)[-1])
        if new is None:
            continue
        out.append(data[last:q + 1])
        out.append(_s(new))
        last = q + 5 + L
        n += 1
    out.append(data[last:])
    return b''.join(out), n


def textures_in(data):
    """Texture file names a .nif uses, in order, without repeats."""
    import nif
    blocks = nif._blocks(data) or []
    seen = []
    for typ, p in blocks:
        if typ != b'NiSourceTexture':
            continue
        _name, q = nif._str(data, p)
        q += 8
        if data[q] == 1:
            t, _ = nif._str(data, q + 1)
            if t and t.lower() not in [s.lower() for s in seen]:
                seen.append(t)
    return seen
