"""Particle models (.nif) read and written whole, block by block.

The game's particles are one emitter (NiParticleSystemController, or Bethesda's NiBSPArrayController) on
NiRotatingParticles or NiAutoNormalParticles, with up to four modifiers chained after it: grow and fade, gravity,
colour over life and spin. Those models also hold ordinary shapes, properties, extra data and other controllers,
so every block they use is read here, field by field with its exact size, as kf.py does for animation: no
searching. A block of a kind not listed is refused rather than guessed at, and a file read and written again is
the same to the byte.

One description serves both ways: each block's fields are walked by the same function, which reads them in
order or writes them back from what was read."""
import math
import struct

HEADER = b'NetImmerse File Format, Version 4.0.0.2\n'
VERSION = 0x04000002


class PartError(ValueError):
    pass


class _NaN(float):
    """A NaN as the file has it: Python quiets a signalling NaN when it packs one, so the bits are kept (a dozen
    of the game's particle models hold them in unused vertex slots)."""
    def __new__(cls, bits):
        x = float.__new__(cls, float('nan'))
        x.bits = bits
        return x


_CODES = {}


def _codes(fmt):
    """'<3fI' -> ['f', 'f', 'f', 'I']."""
    got = _CODES.get(fmt)
    if got is None:
        got, num = [], ''
        for ch in fmt.lstrip('<'):
            if ch.isdigit():
                num += ch
            else:
                got.extend(ch * int(num or 1))
                num = ''
        _CODES[fmt] = got
    return got


def _keep_nans(fmt, val, data, p):
    """val with every NaN float replaced by a _NaN holding its bits."""
    if 'f' not in fmt or all(x == x for x in val):
        return val
    out, q = [], p
    for code, x in zip(_codes(fmt), val):
        if code == 'f' and x != x:
            x = _NaN(struct.unpack_from('<I', data, q)[0])
        out.append(x)
        q += struct.calcsize('<' + code)
    return tuple(out)


def _pack(fmt, val):
    if not any(isinstance(x, _NaN) for x in val):
        return struct.pack(fmt, *val)
    return b''.join(struct.pack('<I', x.bits) if isinstance(x, _NaN) else struct.pack('<' + c, x)
                    for c, x in zip(_codes(fmt), val))


class _IO:
    """Walks a block's fields: reading fills the current dict, writing packs it back."""

    def __init__(self, data=None):
        self.reading = data is not None
        self.data, self.p, self.out, self.d = data, 0, [], None

    def v(self, name, fmt):
        """One field; several values (a tuple) when the format holds more than one."""
        fmt = '<' + fmt
        if self.reading:
            try:
                val = struct.unpack_from(fmt, self.data, self.p)
            except struct.error:
                raise PartError('The file ends inside a block.')
            val = _keep_nans(fmt, val, self.data, self.p)
            self.p += struct.calcsize(fmt)
            val = val[0] if len(val) == 1 else val
            self.d[name] = val
            return val
        val = self.d[name]
        self.out.append(_pack(fmt, val if isinstance(val, tuple) else (val,)))
        return val

    def arr(self, name, n, code):
        """n values of one kind, always a tuple."""
        fmt = '<%d%s' % (n, code)
        if self.reading:
            if n > 10_000_000:
                raise PartError('A list is too long to be one.')
            try:
                val = struct.unpack_from(fmt, self.data, self.p)
            except struct.error:
                raise PartError('The file ends inside a block.')
            val = _keep_nans(fmt, val, self.data, self.p)
            self.p += struct.calcsize(fmt)
            self.d[name] = val
            return val
        val = self.d[name]
        if len(val) != n:
            raise PartError('%s holds %d, not %d.' % (name, len(val), n))
        self.out.append(_pack(fmt, val))
        return val

    def s(self, name):
        """A string, kept as its bytes."""
        if self.reading:
            n = self.v('_n', 'I')
            del self.d['_n']
            if n > 65536:
                raise PartError('A name is too long to be one.')
            val = self.data[self.p:self.p + n]
            if len(val) != n:
                raise PartError('The file ends inside a name.')
            self.p += n
            self.d[name] = val
            return val
        val = self.d[name]
        self.out.append(struct.pack('<I', len(val)) + val)
        return val

    def items(self, name, n, fn):
        """n sub-records, each a dict walked by fn."""
        outer = self.d
        if self.reading:
            if n > 1_000_000:
                raise PartError('A list is too long to be one.')
            got = []
            for _i in range(n):
                self.d = {}
                fn(self)
                got.append(self.d)
            outer[name] = got
        else:
            got = outer[name]
            if len(got) != n:
                raise PartError('%s holds %d, not %d.' % (name, len(got), n))
            for sub in got:
                self.d = sub
                fn(self)
        self.d = outer
        return got

    def sub(self, name, fn):
        """One sub-record (a dict) walked by fn."""
        outer = self.d
        if self.reading:
            self.d = {}
            fn(self)
            outer[name] = self.d
        else:
            self.d = outer[name]
            fn(self)
        self.d = outer


# ----- the blocks -----------------------------------------------------------------------------------------------
def _keys(comps):
    """A key group of comps values a key (1 a float, 3 a position, 4 a colour)."""
    def walk(io):
        n = io.v('n', 'I')
        if n:
            kind = io.v('kind', 'I')
            if kind not in (1, 2, 3, 5):
                raise PartError('Unknown key kind %d.' % kind)
            more = 2 * comps if kind == 2 else 3 if kind == 3 else 0
            io.items('keys', n, lambda io: io.v('k', '%df' % (1 + comps + more)))
    return walk


def _net(io):
    io.s('name')
    io.v('extra', 'i')
    io.v('ctrl', 'i')


def _av(io):
    _net(io)
    io.v('flags', 'H')
    io.v('trans', '3f')
    io.v('rot', '9f')
    io.v('scale', 'f')
    io.v('vel', '3f')
    io.arr('props', io.v('nprops', 'I'), 'i')
    if io.v('hasbb', 'I'):
        kind = io.v('bbkind', 'I')
        if kind == 0:
            io.v('bb', '4f')              # a sphere: centre, radius
        elif kind == 1:
            io.v('bb', '3f9f3f')          # a box: centre, axes, extents
        else:
            raise PartError('Unknown bounding volume %d.' % kind)


def _node(io):
    _av(io)
    io.arr('kids', io.v('nkids', 'I'), 'i')
    io.arr('effects', io.v('neffects', 'I'), 'i')


def _lodnode(io):
    _node(io)
    io.v('index', 'I')            # the switch node's shown child
    io.v('lod_center', '3f')
    io.items('levels', io.v('nlevels', 'I'), lambda io: io.v('range', '2f'))


def _switchnode(io):
    _node(io)
    io.v('index', 'I')


def _pixeldata(io):
    io.v('pixel_format', 'IIIIII8B')   # format, the four masks, bits a pixel, eight unknown bytes
    io.v('palette', 'i')
    nmip = io.v('nmips', 'I')
    io.v('bytes_per_pixel', 'I')
    io.items('mips', nmip, lambda io: io.v('m', 'III'))     # width, height, offset
    io.arr('pixels', io.v('npixels', 'I'), 'B')


def _nothing(io):
    pass


def _sortnode(io):
    _node(io)
    io.v('sorting', 'I')
    io.v('sorter', 'i')


def _geom(io):
    _av(io)
    io.v('data', 'i')
    io.v('skin', 'i')


def _geomdata(io):
    nv = io.v('nv', 'H')
    if io.v('hasv', 'I'):
        io.arr('verts', 3 * nv, 'f')
    if io.v('hasn', 'I'):
        io.arr('norms', 3 * nv, 'f')
    io.v('center', '3f')
    io.v('radius', 'f')
    if io.v('hasc', 'I'):
        io.arr('colors', 4 * nv, 'f')
    nuv = io.v('nuv', 'H')
    if io.v('hasuv', 'I'):
        io.arr('uv', 2 * nv * nuv, 'f')


def _trishapedata(io):
    _geomdata(io)
    nt = io.v('ntri', 'H')
    io.v('ntripts', 'I')
    io.arr('tris', 3 * nt, 'H')
    io.items('match', io.v('nmatch', 'H'), lambda io: io.arr('idx', io.v('n', 'H'), 'H'))


def _particlesdata(io):
    _geomdata(io)
    io.v('nparts', 'H')
    io.v('pradius', 'f')
    io.v('nactive', 'H')
    if io.v('hassizes', 'I'):
        io.arr('sizes', io.d['nv'], 'f')


def _rotparticlesdata(io):
    _particlesdata(io)
    if io.v('hasrot', 'I'):
        io.arr('rots', 4 * io.d['nv'], 'f')


def _flags(io):
    _net(io)
    io.v('flags', 'H')


def _alpha(io):
    _flags(io)
    io.v('threshold', 'B')


def _material(io):
    _flags(io)
    io.v('ambient', '3f')
    io.v('diffuse', '3f')
    io.v('specular', '3f')
    io.v('emissive', '3f')
    io.v('gloss', 'f')
    io.v('alpha', 'f')


def _stencil(io):
    _flags(io)
    io.v('enabled', 'B')
    io.v('stencil', '7I')         # function, reference, mask, fail, z fail and pass actions, draw mode


def _vertexcolor(io):
    _flags(io)
    io.v('vmode', 'I')
    io.v('lmode', 'I')


def _texdesc(io, slot):
    io.v(slot, 'iIIIhhH')        # source, clamp, filter, UV set, PS2 L and K, unknown


def _texturing(io):
    _flags(io)
    io.v('apply', 'I')
    count = io.v('count', 'I')
    for slot in ('base', 'dark', 'detail', 'gloss', 'glow', 'bump'):
        if io.v('has_' + slot, 'I'):
            _texdesc(io, slot)
            if slot == 'bump':
                io.v('bump_more', '6f')
    for k in range(max(0, count - 6)):
        if io.v('has_decal%d' % k, 'I'):
            _texdesc(io, 'decal%d' % k)


def _sourcetexture(io):
    _net(io)
    if io.v('external', 'B'):
        io.s('file')
    elif io.v('internal', 'B'):
        io.v('pixels', 'i')
    io.v('format', 'IIIB')        # pixel layout, mipmaps, alpha format, static


def _texeffect(io):
    _av(io)
    io.arr('affected', io.v('naffected', 'I'), 'I')
    io.v('projection', '9f3f')
    io.v('modes', 'IIII')         # filtering, clamping, type, coordinates
    io.v('source', 'i')
    io.v('clip', 'B')
    io.v('plane', '4f')
    io.v('ps2', 'hhH')


def _stringextra(io):
    io.v('next', 'i')
    io.v('left', 'I')
    io.s('s')


def _textkeys(io):
    io.v('next', 'i')
    io.v('unused', 'I')
    io.items('keys', io.v('n', 'I'), lambda io: (io.v('t', 'f'), io.s('s')))


def _vertweights(io):
    io.v('next', 'i')
    io.v('bytes', 'I')
    io.arr('w', io.v('n', 'H'), 'f')


def _ctrl(io):
    io.v('next', 'i')
    io.v('flags', 'H')
    io.v('freq', 'f')
    io.v('phase', 'f')
    io.v('start', 'f')
    io.v('stop', 'f')
    io.v('target', 'i')


def _datactrl(io):
    _ctrl(io)
    io.v('data', 'i')


def _uvctrl(io):
    _ctrl(io)
    io.v('unknown', 'H')
    io.v('data', 'i')


def _flipctrl(io):
    _ctrl(io)
    io.v('slot', 'I')
    io.v('unknown', 'I')
    io.v('delta', 'f')
    io.arr('sources', io.v('nsources', 'I'), 'i')


def _morpher(io):
    _ctrl(io)
    io.v('data', 'i')
    io.v('always', 'B')


def _pathctrl(io):
    _ctrl(io)
    io.v('bank', 'iffh')          # bank direction, max bank angle, smoothing, follow axis
    io.v('path', 'i')
    io.v('percent', 'i')


EMIT = ('speed', 'speed_random', 'v_dir', 'v_angle', 'h_dir', 'h_angle')


def _emitter(io):
    _ctrl(io)
    for k in EMIT:
        io.v(k, 'f')
    io.v('normal', '3f')
    io.v('color', '4f')
    io.v('size', 'f')
    io.v('emit_start', 'f')
    io.v('emit_stop', 'f')
    io.v('unknown_byte', 'B')
    io.v('rate', 'f')
    io.v('life', 'f')
    io.v('life_random', 'f')
    io.v('emit_flags', 'H')
    io.v('box', '3f')
    io.v('emitter', 'i')
    io.v('unknown', 'HfIIH')
    n = io.v('nparts', 'H')
    io.v('nvalid', 'H')
    io.items('parts', n, lambda io: io.v('p', '3f3ffffHH'))
    io.v('link', 'i')
    io.v('modifier', 'i')
    io.v('link2', 'i')
    io.v('trailer', 'B')


def _mod(io):
    io.v('next', 'i')
    io.v('ctrl', 'i')


def _growfade(io):
    _mod(io)
    io.v('grow', 'f')
    io.v('fade', 'f')


def _gravity(io):
    _mod(io)
    io.v('decay', 'f')
    io.v('force', 'f')
    io.v('type', 'I')             # 0 a wind along the direction, 1 a pull towards the position
    io.v('pos', '3f')
    io.v('dir', '3f')


def _colormod(io):
    _mod(io)
    io.v('data', 'i')


def _spin(io):
    _mod(io)
    io.v('random_axis', 'B')
    io.v('axis', '3f')
    io.v('speed', 'f')


def _planar(io):
    _mod(io)
    io.v('bounce', 'f')
    io.v('plane', '2f3f3f3f4f')   # height, width, position, x and y vectors, the plane


def _keyframedata(io):
    nr = io.v('nrot', 'I')
    if nr:
        kind = io.v('rkind', 'I')
        if kind == 4:
            io.v('order', 'f')
            for ax in 'xyz':
                io.sub('rot_' + ax, _keys(1))
        elif kind in (1, 2, 3, 5):
            io.items('rots', nr, lambda io: io.v('k', '%df' % (8 if kind == 3 else 5)))
        else:
            raise PartError('Unknown rotation key kind %d.' % kind)
    io.sub('pos', _keys(3))
    io.sub('scale', _keys(1))


def _keys_block(comps):
    return lambda io: io.sub('keys', _keys(comps))


def _visdata(io):
    io.items('keys', io.v('n', 'I'), lambda io: io.v('k', 'fB'))


def _uvdata(io):
    for k in range(4):
        io.sub('g%d' % k, _keys(1))


def _morphdata(io):
    nm = io.v('nmorphs', 'I')
    nv = io.v('nv', 'I')
    io.v('relative', 'B')

    def morph(io):
        n = io.v('n', 'I')
        kind = io.v('kind', 'I')
        if n and kind not in (1, 2, 3, 5):
            raise PartError('Unknown key kind %d.' % kind)
        more = 2 if kind == 2 else 3 if kind == 3 else 0
        io.items('keys', n, lambda io: io.v('k', '%df' % (2 + more)))
        io.arr('v', 3 * nv, 'f')
    io.items('morphs', nm, morph)


def _skininstance(io):
    io.v('data', 'i')
    io.v('root', 'i')
    io.arr('bones', io.v('nbones', 'I'), 'i')


def _skindata(io):
    io.v('xf', '9f3ff')
    nb = io.v('nbones', 'I')
    io.v('partition', 'i')

    def bone(io):
        io.v('xf', '9f3ff3ff')
        io.items('w', io.v('n', 'H'), lambda io: io.v('w', 'Hf'))
    io.items('bones', nb, bone)


BLOCKS = {
    b'NiNode': _node, b'NiBSParticleNode': _node, b'NiBSAnimationNode': _node, b'RootCollisionNode': _node,
    b'NiBillboardNode': _node, b'NiCollisionSwitch': _node, b'NiLODNode': _lodnode, b'NiSortAdjustNode': _sortnode,
    b'NiSwitchNode': _switchnode, b'NiPixelData': _pixeldata, b'NiAlphaAccumulator': _nothing,
    b'NiParticlesData': lambda io: _particlesdata(io),
    b'NiTriShape': _geom, b'NiRotatingParticles': _geom, b'NiAutoNormalParticles': _geom, b'NiParticles': _geom,
    b'NiTriShapeData': _trishapedata, b'NiAutoNormalParticlesData': _particlesdata,
    b'NiRotatingParticlesData': _rotparticlesdata,
    b'NiAlphaProperty': _alpha, b'NiMaterialProperty': _material, b'NiZBufferProperty': _flags,
    b'NiVertexColorProperty': _vertexcolor, b'NiShadeProperty': _flags, b'NiDitherProperty': _flags,
    b'NiWireframeProperty': _flags, b'NiSpecularProperty': _flags, b'NiStencilProperty': _stencil,
    b'NiFlipController': _flipctrl,
    b'NiTexturingProperty': _texturing, b'NiSourceTexture': _sourcetexture, b'NiTextureEffect': _texeffect,
    b'NiStringExtraData': _stringextra, b'NiTextKeyExtraData': _textkeys, b'NiVertWeightsExtraData': _vertweights,
    b'NiKeyframeController': _datactrl, b'NiVisController': _datactrl, b'NiAlphaController': _datactrl,
    b'NiMaterialColorController': _datactrl, b'NiUVController': _uvctrl, b'NiGeomMorpherController': _morpher,
    b'NiPathController': _pathctrl,
    b'NiParticleSystemController': _emitter, b'NiBSPArrayController': _emitter,
    b'NiParticleGrowFade': _growfade, b'NiGravity': _gravity, b'NiParticleColorModifier': _colormod,
    b'NiParticleRotation': _spin, b'NiPlanarCollider': _planar,
    b'NiKeyframeData': _keyframedata, b'NiFloatData': _keys_block(1), b'NiColorData': _keys_block(4),
    b'NiPosData': _keys_block(3), b'NiVisData': _visdata, b'NiUVData': _uvdata, b'NiMorphData': _morphdata,
    b'NiSkinInstance': _skininstance, b'NiSkinData': _skindata,
}


# ----- whole files ----------------------------------------------------------------------------------------------
def read(data):
    """{'blocks': [(type, fields)], 'roots': (indexes)}. Raises PartError for anything not read exactly."""
    if not data or not data.startswith(HEADER):
        raise PartError("That isn't a Morrowind model.")
    io = _IO(data)
    io.p = len(HEADER)
    io.d = {}
    ver, n = io.v('ver', 'I'), io.v('n', 'I')
    if ver != VERSION:
        raise PartError("That model is from another game's version of the format.")
    blocks = []
    for _b in range(n):
        io.d = {}
        t = io.s('t')
        walk = BLOCKS.get(t)
        if walk is None:
            raise PartError('This model holds a %s, which the Workshop does not read.' % t.decode('ascii', 'replace'))
        io.d = {}
        walk(io)
        blocks.append((t, io.d))
    io.d = {}
    roots = io.arr('roots', io.v('nroots', 'I'), 'i')
    if io.p != len(data):
        raise PartError('This model has more in it than the Workshop reads.')
    return {'blocks': blocks, 'roots': roots}


def write(f):
    io = _IO()
    io.out.append(HEADER + struct.pack('<II', VERSION, len(f['blocks'])))
    for t, fields in f['blocks']:
        io.out.append(struct.pack('<I', len(t)) + t)
        io.d = fields
        BLOCKS[t](io)
    io.out.append(struct.pack('<I%di' % len(f['roots']), len(f['roots']), *f['roots']))
    return b''.join(io.out)


# ----- the emitters, for the 3D view ------------------------------------------------------------------------------
EMITTERS = (b'NiParticleSystemController', b'NiBSPArrayController')
NODES = {b'NiNode', b'NiBSParticleNode', b'NiBSAnimationNode', b'NiBillboardNode', b'NiCollisionSwitch', b'NiLODNode',
         b'NiSortAdjustNode', b'NiSwitchNode'}
_I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _apply(R, v):
    return tuple(R[i][0] * v[0] + R[i][1] * v[1] + R[i][2] * v[2] for i in range(3))


def _placed(f):
    """Every node and shape's place in the model's own coordinates, and the properties it draws with (its own
    first, then its parents'): {index: (R, t, s, props)}. The root node's own transform is ignored, as the game
    does and nif.mesh_from_nif does; hidden branches and the collision are left out."""
    B, out = f['blocks'], {}

    def visit(i, R, t, s, props, top):
        if not 0 <= i < len(B) or i in out:
            return
        typ, b = B[i]
        if typ == b'RootCollisionNode' or 'trans' not in b or (b['flags'] & 1 and not top):
            return
        if top and typ in NODES:
            lR, lt, ls = _I3, (0.0, 0.0, 0.0), 1.0
        else:
            r = b['rot']
            lR, lt, ls = (r[0:3], r[3:6], r[6:9]), b['trans'], b['scale']
        nR = _mul(R, lR)
        nt = tuple(t[k] + s * v for k, v in enumerate(_apply(R, lt)))
        ns = s * ls
        mine = list(b.get('props', ())) + props
        out[i] = (nR, nt, ns, mine)
        for k in b.get('kids', ()):
            visit(k, nR, nt, ns, mine, False)

    for root in f['roots'][:1]:
        visit(root, _I3, (0.0, 0.0, 0.0), 1.0, [], True)
    return out


def _prop(B, props, typ):
    return next((B[p][1] for p in props if 0 <= p < len(B) and B[p][0] == typ), None)


def _texture(B, props):
    tp = _prop(B, props, b'NiTexturingProperty')
    if not tp or not tp.get('has_base'):
        return ''
    src = tp['base'][0]
    if 0 <= src < len(B) and B[src][0] == b'NiSourceTexture' and B[src][1].get('external'):
        return B[src][1]['file'].decode('cp1252', 'replace')
    return ''


def _key_values(g):
    """A key group as [(time, values...)], whatever its kind (the extra tangent numbers dropped)."""
    if not g or not g.get('n'):
        return []
    return [k['k'] for k in g['keys']]


def effects(data):
    """The model's emitters, each with its settings and where it is in the model's own coordinates:
    [{'at', 'R', 's' (the emitter's place), 'pR', 'pt', 'ps' (the particles' place: gravity's frame), the
    emitter's numbers, 'grow', 'fade', 'gravity': [...], 'colors': [(t, r, g, b, a)], 'spin', 'tex', 'blend',
    'zwrite', 'emissive', 'diffuse', 'alpha'}]. [] when the model has none; PartError when it can't be read."""
    f = read(data)
    B = f['blocks']
    placed = _placed(f)
    out = []
    for ci, (typ, b) in enumerate(B):
        if typ not in EMITTERS:
            continue
        tgt, emi = b['target'], b['emitter']
        if tgt not in placed or 'data' not in B[tgt][1]:
            continue                      # (a hidden or unplaced particle shape draws nothing)
        pR, pt, ps, props = placed[tgt]
        eR, et, es, _p = placed.get(emi, (pR, pt, ps, props))
        e = {'at': et, 'R': eR, 's': es, 'pR': pR, 'pt': pt, 'ps': ps, 'ctrl_i': ci, 'props_of': props}
        for k in EMIT + ('size', 'rate', 'life', 'life_random', 'box', 'emit_start', 'emit_stop', 'start', 'stop',
                         'freq', 'phase', 'flags', 'emit_flags', 'nparts', 'color'):
            e[k] = b[k]
        # (OpenMW: without "no auto adjust" the rate keeps the system full: particles over the mean lifetime)
        e['per_second'] = b['rate'] if b['emit_flags'] & 1 else b['nparts'] / max(0.001, b['life'] + b['life_random'] / 2)
        e['grow'] = e['fade'] = 0.0
        e['gravity'], e['colors'], e['spin'] = [], [], None
        m, seen = b['modifier'], set()
        while 0 <= m < len(B) and m not in seen:
            seen.add(m)
            mt, mb = B[m]
            if mt == b'NiParticleGrowFade':
                e['grow'], e['fade'] = mb['grow'], mb['fade']
            elif mt == b'NiGravity':
                e['gravity'].append({'type': mb['type'], 'force': mb['force'], 'decay': mb['decay'],
                                     'pos': mb['pos'], 'dir': mb['dir']})
            elif mt == b'NiParticleColorModifier':
                d = mb['data']
                if 0 <= d < len(B) and B[d][0] == b'NiColorData':
                    e['colors'] = _key_values(B[d][1]['keys'])
            elif mt == b'NiParticleRotation':
                e['spin'] = {'speed': mb['speed'], 'axis': mb['axis'], 'random': mb['random_axis']}
            m = mb.get('next', -1)
        e['tex'] = _texture(B, props)
        a = _prop(B, props, b'NiAlphaProperty')
        af = a['flags'] if a else 0
        e['blend'] = {'on': bool(af & 1), 'src': (af >> 1) & 15, 'dst': (af >> 5) & 15}
        e['alpha_flags'], e['alpha_threshold'] = (af, a['threshold']) if a else (None, 0)
        z = _prop(B, props, b'NiZBufferProperty')
        e['zwrite'] = bool(z['flags'] & 2) if z else True
        mat = _prop(B, props, b'NiMaterialProperty')
        e['emissive'] = mat['emissive'] if mat else (1.0, 1.0, 1.0)
        e['diffuse'] = mat['diffuse'] if mat else (1.0, 1.0, 1.0)
        e['alpha'] = mat['alpha'] if mat else 1.0
        # (vertex colours as the emissive: the particles' own colours are their light, unlit by the room)
        vc = _prop(B, props, b'NiVertexColorProperty')
        e['self_lit'] = bool(vc and vc['vmode'] == 1)
        e['vc'] = (vc['flags'], vc['vmode'], vc['lmode']) if vc else None
        out.append(e)
    return out


def say(e):
    """An emitter in a few plain words: 'about 34 a second, live 0.67 s, rise at 5.2 a second, size 2.5'."""
    # (which way they leave as placed: the cone's middle turned by the emitter, an upside-down sheet lets fall)
    v, h = e['v_dir'], e['h_dir']
    d = (math.cos(h) * math.sin(v), math.sin(h) * math.sin(v), math.cos(v))
    dz = _apply(e['R'], d)[2] if e.get('R') else d[2]
    up = math.degrees(math.acos(max(-1.0, min(1.0, dz))))
    way = 'rise' if up < 30 else 'fall' if up > 150 else 'shoot out'
    words = ['about %g a second' % round(e['per_second'], 1 if e['per_second'] < 10 else 0),
             'live %g s' % round(e['life'], 2)]
    if e['speed']:
        words.append('%s at %g a second' % (way, round(e['speed'], 1)))
    if e['v_angle'] > 0.01:
        words.append('spread %d°' % round(math.degrees(min(e['v_angle'], math.pi))))
    words.append('size %g' % round(e['size'], 1))
    if e['grow'] > 0.01:
        words.append('grow %g s' % round(e['grow'], 2))
    if e['fade'] > 0.01:
        words.append('fade %g s' % round(e['fade'], 2))
    for g in e['gravity']:
        if g['type'] == 0:
            dz = g['dir'][2]
            words.append('%s %g' % ('a wind up' if dz > 0.7 else 'gravity' if dz < -0.7 else 'a wind', round(g['force'])))
        else:
            words.append('a pull of %g' % round(g['force']))
    if e['colors']:
        words.append('changing colour')
    if e['spin'] and e['spin']['speed']:
        words.append('spinning')
    return ', '.join(words)
