"""Motion to Blender and back: one animation group of a creature or person out as a .glb (the skeleton as
joints, the skinned shapes bound to it, the rigid parts on their bones, the group's motion as an
animation named after it), and the motion Blender saves back put into the animation file as keyframes.

Blender's importer turns bones to its own liking (its bone heuristic), so a joint's transform coming back
is not the bone's own: each bone's turn is found once from the rest pose (the one sent, the one returned),
C = (sent rest)^-1 x (returned rest) in the scene, and taken off every frame. What comes back is then the
bones' own transforms, written as keys into the group's span (kf.put), so the groups around it stay."""
import json
import math
import os
import re
import struct

import kf
import nifanim

FPS = 30.0


# ----- 4×4 matrices as rows -----------------------------------------------------------------------------
def _mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _inv(M):
    """An affine 4×4 matrix's inverse."""
    a, b, c = M[0][:3], M[1][:3], M[2][:3]
    det = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if abs(det) < 1e-12:
        det = 1e-12
    inv3 = [[(b[1] * c[2] - b[2] * c[1]) / det, (a[2] * c[1] - a[1] * c[2]) / det, (a[1] * b[2] - a[2] * b[1]) / det],
            [(b[2] * c[0] - b[0] * c[2]) / det, (a[0] * c[2] - a[2] * c[0]) / det, (a[2] * b[0] - a[0] * b[2]) / det],
            [(b[0] * c[1] - b[1] * c[0]) / det, (a[1] * c[0] - a[0] * c[1]) / det, (a[0] * b[1] - a[1] * b[0]) / det]]
    t = [M[0][3], M[1][3], M[2][3]]
    it = [-sum(inv3[i][k] * t[k] for k in range(3)) for i in range(3)]
    return [inv3[0] + [it[0]], inv3[1] + [it[1]], inv3[2] + [it[2]], [0, 0, 0, 1]]


def _q_mat(q):
    """(w, x, y, z) as a 3×3 rotation."""
    w, x, y, z = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


def _mat_q(R):
    """A 3×3 rotation as (w, x, y, z)."""
    tr = R[0][0] + R[1][1] + R[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = (0.25 * s, (R[2][1] - R[1][2]) / s, (R[0][2] - R[2][0]) / s, (R[1][0] - R[0][1]) / s)
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        s = math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2]) * 2
        q = ((R[2][1] - R[1][2]) / s, 0.25 * s, (R[0][1] + R[1][0]) / s, (R[0][2] + R[2][0]) / s)
    elif R[1][1] > R[2][2]:
        s = math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2]) * 2
        q = ((R[0][2] - R[2][0]) / s, (R[0][1] + R[1][0]) / s, 0.25 * s, (R[1][2] + R[2][1]) / s)
    else:
        s = math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1]) * 2
        q = ((R[1][0] - R[0][1]) / s, (R[0][2] + R[2][0]) / s, (R[1][2] + R[2][1]) / s, 0.25 * s)
    m = math.sqrt(sum(v * v for v in q)) or 1.0
    q = tuple(v / m for v in q)
    return q if q[0] >= 0 else tuple(-v for v in q)


def _trs(q, t, s):
    """A matrix from a rotation (w, x, y, z), a position and a scale (one number or three)."""
    R = _q_mat(q)
    s3 = (s, s, s) if not isinstance(s, (tuple, list)) else s
    return [[R[i][0] * s3[0], R[i][1] * s3[1], R[i][2] * s3[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def _split(M):
    """A matrix as (rotation (w, x, y, z), position, uniform scale)."""
    cols = [math.sqrt(sum(M[i][j] ** 2 for i in range(3))) for j in range(3)]
    s = sum(cols) / 3.0 or 1.0
    R = [[M[i][j] / (cols[j] or 1.0) for j in range(3)] for i in range(3)]
    return _mat_q(R), (M[0][3], M[1][3], M[2][3]), s


def _node_mat(n):
    """A node's own matrix (rows) from its R, t, s."""
    return [[n['R'][i][0] * n['s'], n['R'][i][1] * n['s'], n['R'][i][2] * n['s'], n['t'][i]] for i in range(3)] + [[0, 0, 0, 1]]


# (game: X east, Y north, Z up, in units; glTF: Y up, in metres) — the scene's own wrapper node does it
def _wrap(k):
    return [[k, 0, 0, 0], [0, 0, k, 0], [0, -k, 0, 0], [0, 0, 0, 1]]


def _gl_trs(M):
    """glTF node fields for a row matrix: translation, rotation (x, y, z, w), scale."""
    q, t, s = _split(M)
    det = sum(M[0][i] * (M[1][(i + 1) % 3] * M[2][(i + 2) % 3] - M[1][(i + 2) % 3] * M[2][(i + 1) % 3]) for i in range(3))
    out = {'translation': [t[0], t[1], t[2]], 'rotation': [q[1], q[2], q[3], q[0]], 'scale': [s, s, s]}
    if det < 0:
        # (a mirrored part, as people's left-side parts are: given as a matrix, columns first)
        return {'matrix': [M[r][c] for c in range(4) for r in range(4)]}
    return out


# ----- out -------------------------------------------------------------------------------------------------
def export_group(db, rec_i, group, out=None):
    """One animation group as a .glb for Blender. Returns {'file', 'group', 'bones', 'frames', 'stamp'}."""
    import assets
    import library
    rec_i = int(rec_i)
    d = nifanim.for_record(db, rec_i)
    g = next((x for x in d['groups'] if x['name'].lower() == (group or '').lower()), None)
    if not g:
        raise ValueError('There is no group called "%s".' % group)
    file = d['sources'][g['src']]['file'] if d.get('sources') else d['keyfile']
    if not file or not file.endswith('.kf'):
        raise ValueError("Only an animation in its own file (.kf), as creatures' and people's are, goes to Blender.")
    K = kf.read(db.meshes.read(file))
    by_bone = {tr['bone'].lower(): tr for tr in K['tracks']}
    T = d['tree']
    nodes = T['nodes']
    k = 1.0 / library.UNITS_PER_METRE
    bin_ = bytearray()
    doc = {'asset': {'version': '2.0', 'generator': 'Morrowind Workshop'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [], 'meshes': [], 'materials': [], 'textures': [], 'images': [], 'skins': [], 'animations': [],
           'samplers': [{'wrapS': 10497, 'wrapT': 10497}], 'accessors': [], 'bufferViews': [], 'buffers': []}

    def view(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        v = {'buffer': 0, 'byteOffset': len(bin_), 'byteLength': len(data)}
        if target:
            v['target'] = target
        bin_.extend(data)
        doc['bufferViews'].append(v)
        return len(doc['bufferViews']) - 1

    def acc(vals, typ, comp=5126, target=None, minmax=False):
        n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[typ]
        fmt = {5126: 'f', 5123: 'H', 5125: 'I', 5121: 'B'}[comp]
        flat = [x for v in vals for x in (v if isinstance(v, (tuple, list)) else (v,))]
        a = {'bufferView': view(struct.pack('<%d%s' % (len(flat), fmt), *flat), target), 'componentType': comp, 'count': len(vals), 'type': typ}
        if minmax:
            a['min'] = [min(v[i] if n > 1 else v for v in vals) for i in range(n)] if n > 1 else [min(vals)]
            a['max'] = [max(v[i] if n > 1 else v for v in vals) for i in range(n)] if n > 1 else [max(vals)]
        doc['accessors'].append(a)
        return len(doc['accessors']) - 1
    # the scene's wrapper, then a node per bone with its own transform at rest
    W = _wrap(k)
    doc['nodes'].append({'name': (d['name'] or d['id']) + ' (Morrowind)', 'children': [], **_gl_trs(W)})
    base = 1
    for i, n in enumerate(nodes):
        doc['nodes'].append({'name': n['name'] or 'node %d' % i, **_gl_trs(_node_mat(n))})
    for i, n in enumerate(nodes):
        parent = n['parent']
        (doc['nodes'][base + parent].setdefault('children', []) if parent >= 0 else doc['nodes'][0]['children']).append(base + i)
    # shapes: skinned ones bound to the joints, rigid ones on their bones
    world = []
    for n in nodes:
        world.append(_mul(world[n['parent']], _node_mat(n)) if n['parent'] >= 0 else _node_mat(n))
    rest_inv = [_inv(M) for M in world]
    pics, mats = {}, {}

    def material(s):
        tex = s.get('tex')
        mk = (tex or '', bool(s.get('alpha')))
        if mk in mats:
            return mats[mk]
        m = {'name': (tex or 'untextured').rsplit('/', 1)[-1], 'pbrMetallicRoughness': {'metallicFactor': 0.0, 'roughnessFactor': 1.0}, 'doubleSided': True}
        if s.get('alpha'):
            m['alphaMode'], m['alphaCutoff'] = 'MASK', 0.5
        if tex:
            if tex not in pics:
                raw = db.meshes.read(tex) or b''
                dd = assets._decode(raw, want=1 << 16) if raw else None
                png = assets._png(*dd) if dd else (raw if raw[:8] == b'\x89PNG\r\n\x1a\n' else None)
                if png:
                    doc['images'].append({'name': tex.rsplit('/', 1)[-1], 'mimeType': 'image/png', 'bufferView': view(png)})
                    doc['textures'].append({'source': len(doc['images']) - 1, 'sampler': 0})
                    pics[tex] = len(doc['textures']) - 1
                else:
                    pics[tex] = None
            if pics[tex] is not None:
                m['pbrMetallicRoughness']['baseColorTexture'] = {'index': pics[tex]}
        doc['materials'].append(m)
        mats[mk] = len(doc['materials']) - 1
        return mats[mk]
    for si, s in enumerate(T['shapes']):
        P = s['p']
        verts = [(P[j], P[j + 1], P[j + 2]) for j in range(0, len(P), 3)]
        tris = [(s['i'][j], s['i'][j + 2], s['i'][j + 1]) for j in range(0, len(s['i']) - 2, 3)]
        import nifwrite
        attrs = {'POSITION': acc(verts, 'VEC3', target=34962, minmax=True), 'NORMAL': acc(nifwrite._normals(verts, tris), 'VEC3', target=34962)}
        if s.get('uv') and len(s['uv']) == len(verts) * 2:
            attrs['TEXCOORD_0'] = acc([(s['uv'][j], s['uv'][j + 1]) for j in range(0, len(s['uv']), 2)], 'VEC2', target=34962)
        big = len(verts) > 65535
        prim = {'attributes': attrs, 'indices': acc([i for t in tris for i in t], 'SCALAR', 5125 if big else 5123, 34963), 'material': material(s)}
        doc['meshes'].append({'name': s.get('name') or 'shape %d' % (si + 1), 'primitives': [prim]})
        sk = s.get('skin')
        node = {'name': s.get('name') or 'shape %d' % (si + 1), 'mesh': len(doc['meshes']) - 1}
        if sk and sk.get('inv') and all(b >= 0 for b in sk['bones']):
            # (each vertex bent by up to four bones, the heaviest, as the game draws it)
            js, ws = [], []
            for v in range(len(verts)):
                wl = sorted(sk['weights'][v] if v < len(sk['weights']) else [], key=lambda w: -w[1])[:4]
                tot = sum(w[1] for w in wl) or 1.0
                js.append(tuple([w[0] for w in wl] + [0] * (4 - len(wl))))
                ws.append(tuple([w[1] / tot for w in wl] + [0.0] * (4 - len(wl))) if wl else (1.0, 0.0, 0.0, 0.0))
            # (every node is a joint, so Blender makes every one a bone it can pose, not only those the skin uses)
            js = [tuple(sk['bones'][j] if w else 0 for j, w in zip(jj, ww)) for jj, ww in zip(js, ws)]
            attrs['JOINTS_0'] = acc(js, 'VEC4', 5123, 34962)
            attrs['WEIGHTS_0'] = acc(ws, 'VEC4', target=34962)
            ibm = list(rest_inv)
            for j, b in enumerate(sk['bones']):
                ibm[b] = _node_mat(sk['inv'][j])
            doc['skins'].append({'joints': [base + b for b in range(len(nodes))], 'skeleton': base,
                                 'inverseBindMatrices': acc([[M[r][c] for c in range(4) for r in range(4)] for M in ibm], 'MAT4')})
            node['skin'] = len(doc['skins']) - 1
            doc['nodes'].append(node)
            doc['nodes'][0]['children'].append(len(doc['nodes']) - 1)
        else:
            M = [[s['M'][r * 4 + c] for c in range(4)] for r in range(4)] if s.get('M') else _node_mat(s)
            node.update(_gl_trs(M))
            doc['nodes'].append(node)
            owner = base + s['node'] if s.get('node', -1) >= 0 else 0
            doc['nodes'][owner].setdefault('children', []).append(len(doc['nodes']) - 1)
    if not doc['skins']:
        # (nothing skinned, as a machine of rigid parts: a skin of every node still, so they come in as bones)
        doc['skins'].append({'joints': [base + b for b in range(len(nodes))], 'skeleton': base,
                             'inverseBindMatrices': acc([[M[r][c] for c in range(4) for r in range(4)] for M in rest_inv], 'MAT4')})
    # the group's motion, sampled FPS times a second from its start, every tracked bone
    a, b = g['start'], g['stop']
    n = max(2, int(round((b - a) * FPS)) + 1)
    times = [min(b - a, i / FPS) for i in range(n)]
    tacc = acc(times, 'SCALAR', minmax=True)
    anim = {'name': g['name'], 'channels': [], 'samplers': []}
    for i, nd in enumerate(nodes):
        tr = by_bone.get(nd['name'].lower())
        if not tr:
            continue
        q0, t0, s0 = _split(_node_mat(nd))
        rots, poss, scls = [], [], []
        for t in times:
            q, p, sc = kf.sample(tr, a + t)
            q = q or q0
            rots.append((q[1], q[2], q[3], q[0]))
            poss.append(tuple(p) if p else t0)
            scls.append((sc, sc, sc) if sc is not None else (s0, s0, s0))
        for path, vals, typ in (('rotation', rots, 'VEC4'), ('translation', poss, 'VEC3'), ('scale', scls, 'VEC3')):
            anim['samplers'].append({'input': tacc, 'output': acc(vals, typ), 'interpolation': 'LINEAR'})
            anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': base + i, 'path': path}})
    doc['animations'].append(anim)
    doc['buffers'].append({'byteLength': len(bin_)})
    for key in ('textures', 'images', 'skins'):
        if not doc[key]:
            del doc[key]
    ws = {'motion': True, 'record': d['id'], 'type': d['type'], 'group': g['name'], 'file': file, 'units_per_metre': library.UNITS_PER_METRE,
          'length': round(b - a, 4)}
    doc['extras'] = {'workshop': ws}
    doc['scenes'][0]['extras'] = {'workshop': ws}
    doc['nodes'][0]['extras'] = {'workshop': ws}
    if not out:
        os.makedirs(assets.EXPORTS, exist_ok=True)
        out = os.path.join(assets.EXPORTS, re.sub(r'[^A-Za-z0-9_.-]+', '_', '%s_%s' % (d['id'], g['name'])) + '.glb')
    with open(out, 'wb') as f:
        f.write(assets._glb(doc, bytes(bin_)))
    return {'file': out, 'group': g['name'], 'bones': len(anim['channels']) // 3, 'frames': n, 'stamp': assets.stamp(out)}


# (what Blender runs on opening a motion: the skeleton kept as sent, not turned to the guessed bind pose, and
# every Ctrl+S sends the .glb back with the actions)
BLENDER_SCRIPT = r'''
import bpy
glb = r"%s"
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.context.scene.render.fps = 30
bpy.ops.import_scene.gltf(filepath=glb, guess_original_bind_pose=False)
def _back(*_a):
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_extras=True, export_animations=True,
                              export_animation_mode='ACTIONS', export_force_sampling=True, export_image_format='AUTO')
bpy.app.handlers.save_post.append(_back)
'''


def open_in_blender(file):
    import subprocess
    import assets
    exe = assets.blender()
    if not exe:
        raise ValueError('Blender was not found on this PC. Open the exported file in your 3D program: File ▸ Import ▸ glTF.')
    script = os.path.join(assets.EXPORTS, '_open_%s.py' % re.sub(r'[^A-Za-z0-9_]+', '_', os.path.splitext(os.path.basename(file))[0]))
    with open(script, 'w', encoding='utf-8') as f:
        f.write(BLENDER_SCRIPT % file)
    subprocess.Popen([exe, '--python', script])
    return exe


# ----- back --------------------------------------------------------------------------------------------------
def _read_glb(path):
    raw = open(path, 'rb').read()
    if raw[:4] != b'glTF':
        raise ValueError('That is not a .glb file.')
    p, doc, binc = 12, None, b''
    while p < len(raw):
        clen, ctype = struct.unpack_from('<II', raw, p)
        if ctype == 0x4E4F534A:
            doc = json.loads(raw[p + 8:p + 8 + clen].decode('utf-8'))
        elif ctype == 0x004E4942:
            binc = raw[p + 8:p + 8 + clen]
        p += 8 + clen
    if not doc:
        raise ValueError('That .glb could not be read.')

    def accessor(ai):
        a = doc['accessors'][ai]
        comps = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        fmt = {5126: 'f', 5123: 'H', 5125: 'I', 5121: 'B', 5122: 'h', 5120: 'b'}[a['componentType']]
        v = doc['bufferViews'][a['bufferView']]
        size = struct.calcsize('<' + fmt)
        stride = v.get('byteStride') or size * comps
        o = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        out = [struct.unpack_from('<%d%s' % (comps, fmt), binc, o + i * stride) for i in range(a['count'])]
        if a.get('normalized') and fmt != 'f':
            m = float((1 << (8 * size - (1 if fmt.islower() else 0))) - 1)
            out = [tuple(x / m for x in t) for t in out]
        return [t[0] for t in out] if comps == 1 else out
    return doc, accessor


def _node_local(n, over=None):
    """A glTF node's matrix (rows), with animated parts in over {'translation', 'rotation', 'scale'}."""
    over = over or {}
    if 'matrix' in n and not over:
        m = n['matrix']
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t = over.get('translation', n.get('translation', [0, 0, 0]))
    r = over.get('rotation', n.get('rotation', [0, 0, 0, 1]))
    s = over.get('scale', n.get('scale', [1, 1, 1]))
    return _trs((r[3], r[0], r[1], r[2]), t, tuple(s))


def _sample_channel(times, values, interp, t):
    if interp == 'CUBICSPLINE':
        values = values[1::3]                           # (in-tangent, value, out-tangent: the values only)
    if t <= times[0]:
        return list(values[0])
    for i in range(len(times) - 1):
        if times[i] <= t <= times[i + 1]:
            if interp == 'STEP':
                return list(values[i])
            f = (t - times[i]) / max(1e-9, times[i + 1] - times[i])
            a, b = values[i], values[i + 1]
            if len(a) == 4:
                q = kf._slerp((a[3], a[0], a[1], a[2]), (b[3], b[0], b[1], b[2]), f)
                return [q[1], q[2], q[3], q[0]]
            return [x + (y - x) * f for x, y in zip(a, b)]
    return list(values[-1])


def motion_of(db, rec_i, glb):
    """The motion in a .glb that went out from export_group, as an animation part (starting at 0) of the
    bones' own transforms: {'part', 'group', 'file', 'length', 'bones'}."""
    doc, accessor = _read_glb(glb)
    ws = {}
    for holder in [doc] + doc.get('scenes', []) + doc.get('nodes', []):
        x = (holder.get('extras') or {}).get('workshop')
        if isinstance(x, dict) and x.get('motion'):
            ws = x
            break
    if not ws:
        raise ValueError("This file didn't come from the Workshop's motion export.")
    d = nifanim.for_record(db, int(rec_i))
    nodes = d['tree']['nodes']
    gname = ws.get('group')
    anims = doc.get('animations') or []
    anim = next((x for x in anims if x.get('name', '').lower() == gname.lower()), None) or \
        next((x for x in anims if gname.lower() in x.get('name', '').lower()), None) or (anims[0] if anims else None)
    if not anim:
        raise ValueError('There is no animation in the file Blender saved.')
    gl_nodes = doc.get('nodes', [])
    parent = {}
    for i, n in enumerate(gl_nodes):
        for c in n.get('children', []):
            parent[c] = i
    chans = {}
    times = set()
    for ch in anim['channels']:
        tgt = ch['target']
        if 'node' not in tgt or tgt.get('path') not in ('translation', 'rotation', 'scale'):
            continue
        smp = anim['samplers'][ch['sampler']]
        ts = accessor(smp['input'])
        times.update(round(t, 5) for t in ts)
        chans.setdefault(tgt['node'], {})[tgt['path']] = (ts, accessor(smp['output']), smp.get('interpolation', 'LINEAR'))
    if not times:
        raise ValueError('The animation in the file has no keys.')
    times = sorted(times)
    t0 = times[0]
    by_name = {}
    for i, n in enumerate(gl_nodes):
        by_name.setdefault((n.get('name') or '').lower(), i)

    def worlds(at):
        cache = {}

        def w(i):
            if i in cache:
                return cache[i]
            over = {}
            if at is not None and i in chans:
                over = {p: _sample_channel(*chans[i][p], at) for p in chans[i]}
            L = _node_local(gl_nodes[i], over)
            cache[i] = _mul(w(parent[i]), L) if i in parent else L
            return cache[i]
        return w
    import library
    W = _wrap(1.0 / float(ws.get('units_per_metre') or library.UNITS_PER_METRE))
    Wi = _inv(W)
    # the bones' world at rest as sent, and each bone's turn by Blender
    sent = []
    for i, nd in enumerate(nodes):
        L = _node_mat(nd)
        sent.append(_mul(sent[nd['parent']], L) if nd['parent'] >= 0 else L)
    rest = worlds(None)
    C = {}
    for i, nd in enumerate(nodes):
        gi = by_name.get((nd['name'] or '').lower())
        if gi is not None:
            C[i] = _mul(_inv(_mul(W, sent[i])), rest(gi))
    if len(C) < 0.8 * len(nodes):
        raise ValueError('The skeleton came back with other bones (%d of %d found).' % (len(C), len(nodes)))
    K = kf.read(db.meshes.read(ws['file']))
    tracked = {tr['bone'].lower() for tr in K['tracks']}
    tracks = {i: {'rot': [], 'pos': [], 'scale': []} for i in C}
    for t in times:
        w = worlds(t)
        mine = {}
        for i in C:
            mine[i] = _mul(_mul(Wi, w(by_name[(nodes[i]['name'] or '').lower()])), _inv(C[i]))
        for i in C:
            p = nodes[i]['parent']
            L = _mul(_inv(mine[p]), mine[i]) if p >= 0 and p in mine else mine[i]
            q, pos, s = _split(L)
            tracks[i]['rot'].append((t - t0, q, None))
            tracks[i]['pos'].append((t - t0, pos, None))
            tracks[i]['scale'].append((t - t0, s, None))
    length = times[-1] - t0
    part = {'name': b'', 'tk_int': 0, 'tk': [], 'tracks': []}
    for i, tr in tracks.items():
        nd = nodes[i]
        moved = nd['name'].lower() in tracked or _moves(tr)
        if not moved:
            continue
        keep_scale = any(abs(s - 1.0) > 1e-3 for _t, s, _e in tr['scale']) or any(x['bone'].lower() == nd['name'].lower() and x['scale'] for x in K['tracks'])
        part['tracks'].append({'bone': nd['name'], 'flags': 12, 'freq': 1.0, 'phase': 0.0, 'start': 0.0, 'stop': length,
                               'rk': 1, 'rot': _thin(_fix_signs(tr['rot']), 1e-5), 'xyz': None, 'pk': 1, 'pos': _thin(tr['pos'], 0.01),
                               'sk': 1 if keep_scale else 0, 'scale': _thin(tr['scale'], 1e-4) if keep_scale else []})
    for tr in part['tracks']:
        for key in ('rot', 'pos', 'scale'):
            tr[key] = [(t, v, ()) for t, v, _e in tr[key]]
    return {'part': part, 'group': gname, 'file': ws['file'], 'length': length, 'bones': len(part['tracks']),
            'rest': {nd['name'].lower(): _split(_node_mat(nd)) for nd in nodes}}


def _moves(tr):
    a = tr['rot'][0][1]
    return any(1 - abs(sum(x * y for x, y in zip(a, q))) > 1e-5 for _t, q, _e in tr['rot']) or \
        any(max(abs(x - y) for x, y in zip(tr['pos'][0][1], p)) > 0.01 for _t, p, _e in tr['pos'])


def _fix_signs(keys):
    """Quaternions turned to the same side as the one before, so no key swings the long way round."""
    out = []
    for t, q, e in keys:
        if out and sum(x * y for x, y in zip(out[-1][1], q)) < 0:
            q = tuple(-x for x in q)
        out.append((t, q, e))
    return out


def _thin(keys, tol):
    """Keys that the keys either side give anyway (by straight interpolation) left out."""
    if len(keys) <= 2:
        return keys
    out = [keys[0]]
    for i in range(1, len(keys) - 1):
        a, b, c = out[-1], keys[i], keys[i + 1]
        f = (b[0] - a[0]) / max(1e-9, c[0] - a[0])
        if isinstance(b[1], tuple):
            mid = tuple(x + (y - x) * f for x, y in zip(a[1], c[1]))
            off = max(abs(x - y) for x, y in zip(mid, b[1]))
        else:
            off = abs(a[1] + (c[1] - a[1]) * f - b[1])
        if off > tol:
            out.append(b)
    out.append(keys[-1])
    return out


def import_motion(db, rec_i, glb, how='everywhere'):
    """Motion saved in Blender put into the group it came from: over the animation file in your mod's
    folder ('everywhere'), as a new copy of the creature with its own files, or for a person their own
    animation ('own'). The group keeps its text keys, spaced to its new length."""
    import editing
    editing._require_project(db)
    rec_i = int(rec_i)
    m = motion_of(db, rec_i, glb)
    d = nifanim.for_record(db, rec_i)
    g = next((x for x in d['groups'] if x['name'].lower() == m['group'].lower()), None)
    if not g:
        raise ValueError('There is no group called "%s" any more.' % m['group'])
    file = d['sources'][g['src']]['file'] if d.get('sources') else d['keyfile']
    K = kf.read(db.meshes.read(file))
    part = m['part']
    old = kf._snap(K, g['stop']) - kf._snap(K, g['start'])
    if abs(m['length'] - old) < 0.5 / FPS and m['length'] > 0:
        # (as long as it was, give or take the sampling: exactly as long, so the groups after it stay put)
        part = nifanim.stretch(part, old / m['length'])
        m['length'] = old
    f = m['length'] / old if old > 0 else 1.0
    own = nifanim._part_of(K, g['name'], g['start'], g['stop'])
    part['tk'] = [(t * f, x) for t, x in own['tk']]
    if d['type'] == 'NPC_' and how == 'own':
        out = nifanim.person_put(db, rec_i, g['name'], part)
    else:
        new = kf.put(K, g['start'], g['stop'], part, rest=m['rest'])
        out = nifanim._write_anim(db, rec_i, kf.write(new), how, file, 'motion')
        out['missing'] = new.get('missing', [])
    out.update(group=g['name'], length=round(m['length'], 4), bones=m['bones'])
    return out
