"""Animations in Morrowind's models: the node tree with its shapes and skins, the keyframes that move the
nodes, and the text keys that name the animation groups and time the sounds.

Where they live: an object that moves (a Dwemer machine, a banner) carries its keyframe controllers on its
own nodes. A creature's skeleton and skinned shapes are in the x-prefixed copy of its model (r\\xGuar.nif)
and its animation in the .kf of that name (r\\xGuar.kf): a NiSequenceStreamHelper whose extra data are the
text keys followed by one NiStringExtraData (a node's name) for each NiKeyframeController, in the same
order. People share the skeleton and animation of base_anim.nif / xbase_anim.kf.

Text keys are one NiTextKeyExtraData: a next-ref, an unused int, the count, then (time, text) pairs; one
text may hold several keys joined by line breaks ("Idle: Start\\r\\nIdle: Loop Start"). Groups are named
"<Group>: Start / Loop Start / Loop Stop / Stop"; "SoundGen: Left" and "Sound: <id>" time the sounds."""
import re
import struct

import nif

HEADER = nif.HEADER


def _spans(data):
    """[(type, start of its type string, start of its body, end)] for every block, or None."""
    b = nif._blocks(data)
    if not b:
        return None
    starts = [after - 4 - len(t) for t, after in b]
    # (the footer: the roots, a count and that many refs)
    foot = None
    for n in range(1, 9):
        p = len(data) - 4 - 4 * n
        if p > starts[-1] and struct.unpack_from('<I', data, p)[0] == n:
            foot = p
            break
    if foot is None:
        return None
    ends = starts[1:] + [foot]
    return [(t, s, a, e) for (t, a), s, e in zip(b, starts, ends)]


def _str(data, p):
    n = struct.unpack_from('<I', data, p)[0]
    return data[p + 4:p + 4 + n].decode('cp1252', 'replace'), p + 4 + n


def _net(data, p):
    """NiObjectNET: name, extra data ref, controller ref; and where it ends."""
    name, p = _str(data, p)
    extra, ctrl = struct.unpack_from('<ii', data, p)
    return name, extra, ctrl, p + 8


# ----- text keys --------------------------------------------------------------------------------------
def text_keys(data):
    """[(time, text)] of a file's text keys (one entry per line of each key), and the block's index; ([], None)."""
    sp = _spans(data)
    if not sp:
        return [], None
    for i, (t, _s, p, _e) in enumerate(sp):
        if t == b'NiTextKeyExtraData':
            n = struct.unpack_from('<I', data, p + 8)[0]
            q, out = p + 12, []
            for _k in range(n):
                tm = struct.unpack_from('<f', data, q)[0]
                txt, q = _str(data, q + 4)
                for line in re.split(r'\r?\n', txt):
                    if line.strip():
                        out.append((round(tm, 4), line.strip()))
            return out, i
    return [], None


def write_text_keys(data, keys):
    """A copy of the file with its text keys replaced by keys [(time, text)] (keys at the same time are
    joined into one text, as the game's files have them)."""
    sp = _spans(data)
    old, i = text_keys(data)
    if i is None:
        raise ValueError('This file has no text keys to change.')
    norm = lambda ks: sorted((round(float(t), 4), x.strip()) for t, x in ks if x.strip())
    if norm(keys) == norm(old):
        return data                                     # (nothing changed: the file as it was, to the byte)
    t, s, p, e = sp[i]
    head = data[p:p + 8]                                # (next ref, the unused int)
    by_t = {}
    for tm, txt in sorted(keys, key=lambda k: float(k[0])):
        by_t.setdefault(round(float(tm), 4), []).append(txt.strip())
    body = head + struct.pack('<I', len(by_t))
    for tm, lines in sorted(by_t.items()):
        b = '\r\n'.join(lines).encode('cp1252', 'replace')
        body += struct.pack('<fI', tm, len(b)) + b
    return data[:p] + body + data[e:]


def groups(keys):
    """The animation groups the text keys name: [{'name', 'start', 'stop', 'loop_start', 'loop_stop'}] by start."""
    out = {}
    for tm, txt in keys:
        m = re.match(r'^([^:]+):\s*(Start|Stop|Loop Start|Loop Stop)\s*$', txt, re.I)
        if not m or m.group(1).strip().lower() in ('sound', 'soundgen'):
            continue
        g = out.setdefault(m.group(1).strip().lower(), {'name': m.group(1).strip()})
        g[m.group(2).lower().replace(' ', '_')] = tm
    return sorted((g for g in out.values() if 'start' in g and 'stop' in g), key=lambda g: g['start'])


# ----- keyframes ---------------------------------------------------------------------------------------
def _keygroup(data, p, comps):
    """A key group of comps floats: ([(time, value)], interpolation, end)."""
    n = struct.unpack_from('<I', data, p)[0]
    p += 4
    if not n:
        return [], 0, p
    kind = struct.unpack_from('<I', data, p)[0]
    p += 4
    out = []
    for _k in range(n):
        vals = struct.unpack_from('<%df' % (1 + comps), data, p)
        p += 4 * (1 + comps)
        if kind == 2:
            p += 8 * comps                               # forward and backward tangents
        elif kind == 3:
            p += 12                                      # tension, bias, continuity
        # (rounded for the page, far below what shows: a hundredth of a unit, four places of a turn or scale)
        out.append((round(vals[0], 4), tuple(round(v, 2) for v in vals[1:]) if comps > 1 else round(vals[1], 4)))
    return out, kind, p


def _euler_q(x, y, z):
    """A quaternion (w, x, y, z) from rotations about X, then Y, then Z (NIF's XYZ rotation keys)."""
    import math
    cx, sx, cy, sy, cz, sz = math.cos(x / 2), math.sin(x / 2), math.cos(y / 2), math.sin(y / 2), math.cos(z / 2), math.sin(z / 2)
    # q = qz * qy * qx
    return (cz * cy * cx + sz * sy * sx, cz * cy * sx - sz * sy * cx, cz * sy * cx + sz * cy * sx, sz * cy * cx - cz * sy * sx)


def _sample(keys, t):
    if not keys:
        return None
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / max(1e-6, t1 - t0)
            return v0 + (v1 - v0) * f
    return keys[-1][1]


def keyframe_data(data, p):
    """NiKeyframeData at p: {'rot': [(t, (w, x, y, z))], 'pos': [(t, (x, y, z))], 'scale': [(t, s)]}."""
    nrot = struct.unpack_from('<I', data, p)[0]
    p += 4
    rot = []
    if nrot:
        kind = struct.unpack_from('<I', data, p)[0]
        p += 4
        if kind == 4:
            # three float tracks, about X, Y and Z, after a float (the axis order): sampled together into quaternions
            p += 4
            xs, _k, p = _keygroup(data, p, 1)
            ys, _k, p = _keygroup(data, p, 1)
            zs, _k, p = _keygroup(data, p, 1)
            times = sorted({k[0] for k in xs + ys + zs})
            rot = [(tm, tuple(round(c, 4) for c in _euler_q(_sample(xs, tm) or 0.0, _sample(ys, tm) or 0.0, _sample(zs, tm) or 0.0))) for tm in times]
        else:
            for _k in range(nrot):
                tm, w, x, y, z = struct.unpack_from('<5f', data, p)
                p += 20 + (12 if kind == 3 else 0)
                rot.append((round(tm, 4), (round(w, 4), round(x, 4), round(y, 4), round(z, 4))))
    pos, _k, p = _keygroup(data, p, 3)
    scl, _k, p = _keygroup(data, p, 1)
    return {'rot': rot, 'pos': pos, 'scale': scl}, p


def _controller(data, sp, ci):
    """A NiKeyframeController's data, its target and the next controller: (keys or None, target, next)."""
    if not 0 <= ci < len(sp):
        return None, -1, -1
    t, _s, p, _e = sp[ci]
    nxt, _flags, _f, _ph, start, stop, target = struct.unpack_from('<iHffffi', data, p)
    if t != b'NiKeyframeController':
        return None, target, nxt
    dref = struct.unpack_from('<i', data, p + 26)[0]
    if not 0 <= dref < len(sp) or sp[dref][0] != b'NiKeyframeData':
        return None, target, nxt
    keys, _end = keyframe_data(data, sp[dref][2])
    keys['start'], keys['stop'] = round(start, 4), round(stop, 4)
    return keys, target, nxt


def tracks_of_kf(data):
    """A .kf file's tracks: {node name: keys}."""
    sp = _spans(data)
    if not sp or sp[0][0] != b'NiSequenceStreamHelper':
        return {}
    _name, extra, ctrl, _p = _net(data, sp[0][2])
    names = []
    while 0 <= extra < len(sp):
        t, _s, p, _e = sp[extra]
        nxt = struct.unpack_from('<i', data, p)[0]
        if t == b'NiStringExtraData':
            s, _q = _str(data, p + 8)
            names.append(s)
        extra = nxt
    out, n = {}, 0
    while 0 <= ctrl < len(sp):
        keys, _target, nxt = _controller(data, sp, ctrl)
        if keys is not None and n < len(names):
            out[names[n]] = keys
        n += 1
        ctrl = nxt
    return out


# ----- retiming: every time in a file moved by a function -------------------------------------------------
def _remap_group(buf, p, comps, g):
    n = struct.unpack_from('<I', buf, p)[0]
    p += 4
    if not n:
        return p
    kind = struct.unpack_from('<I', buf, p)[0]
    p += 4
    for _k in range(n):
        struct.pack_into('<f', buf, p, g(struct.unpack_from('<f', buf, p)[0]))
        p += 4 * (1 + comps) + (8 * comps if kind == 2 else 12 if kind == 3 else 0)
    return p


def remap_times(data, g):
    """A copy of a .kf or .nif with every key time t moved to g(t): keyframes, the controllers' start and
    stop times, and the text keys. Times are floats in place, so the file keeps its size and layout."""
    sp = _spans(data)
    if not sp:
        raise ValueError('This file could not be read.')
    buf = bytearray(data)
    for t, _s, p, _e in sp:
        if t == b'NiKeyframeData':
            nrot = struct.unpack_from('<I', buf, p)[0]
            q = p + 4
            if nrot:
                kind = struct.unpack_from('<I', buf, q)[0]
                q += 4
                if kind == 4:
                    q += 4                             # (the axis order)
                    for _axis in range(3):
                        q = _remap_group(buf, q, 1, g)
                else:
                    for _k in range(nrot):
                        struct.pack_into('<f', buf, q, g(struct.unpack_from('<f', buf, q)[0]))
                        q += 20 + (12 if kind == 3 else 0)
            q = _remap_group(buf, q, 3, g)
            _remap_group(buf, q, 1, g)
        elif t == b'NiKeyframeController':
            for off in (14, 18):                       # (start and stop, after next, flags, frequency, phase)
                struct.pack_into('<f', buf, p + off, g(struct.unpack_from('<f', buf, p + off)[0]))
        elif t == b'NiTextKeyExtraData':
            n = struct.unpack_from('<I', buf, p + 8)[0]
            q = p + 12
            for _k in range(n):
                struct.pack_into('<f', buf, q, g(struct.unpack_from('<f', buf, q)[0]))
                q += 4 + 4 + struct.unpack_from('<I', buf, q + 4)[0]
    return bytes(buf)


def retimer(start, stop, factor):
    """The time function for a group from start to stop played factor times as long (2: half speed):
    earlier times stay, the group's stretch, later ones move by the difference."""
    delta = (stop - start) * (factor - 1)

    def g(t):
        if t <= start + 1e-5:
            return t
        if t <= stop + 1e-5:
            return start + (t - start) * factor
        return t + delta
    return g


# ----- the node tree, shapes and skins ------------------------------------------------------------------
def tree(data, max_verts=200000, keep_root=False):
    """{'nodes': [{'name', 'parent', 'R', 't', 's', 'tracks'?}], 'shapes': [{'node', 'p', 'n', 'uv', 'i', 'tex',
    'alpha', 'double', 'skin'?}]}: every node with its own (local) transform, and every shape in its node's
    frame; a skinned shape with its bones (node indices), each bone's skin transform and the vertices'
    weights. Keyframes on a node's own controllers come as its 'tracks'."""
    sp = _spans(data)
    if not sp:
        return None
    nodes, shapes, at = [], [], {}
    total = [0]

    def visit(i, parent, inherited):
        if not 0 <= i < len(sp) or i in at:
            return
        typ, _s, p, _e = sp[i]
        if typ in nif.SKIP_SUBTREES or not (typ in nif.NODE_TYPES or typ in nif.GEOM_TYPES):
            return
        name, _extra, ctrl, q = _net(data, p)
        flags, (R, t, s), p2 = nif._read_av(data, p)
        if i == 0 and not keep_root:
            # (the game ignores a placed model's root transform; a body part's it keeps, as npcbody.py does:
            # the common trousers' groin, knee and ankle pieces sit by it)
            R, t, s = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0.0, 0.0, 0.0], 1.0
        props = list(struct.unpack_from('<%di' % struct.unpack_from('<I', data, q + 2 + 12 + 36 + 4 + 12)[0], data, q + 2 + 12 + 36 + 4 + 12 + 4))
        props += inherited
        if typ in nif.NODE_TYPES:
            ni = len(nodes)
            at[i] = ni
            nd = {'name': name, 'parent': parent, 'R': R, 't': t, 's': s, 'hidden': bool(flags & 1 and i != 0)}
            # (its own keyframes: the first keyframe controller in its chain)
            while 0 <= ctrl < len(sp):
                keys, _tg, nxt = _controller(data, sp, ctrl)
                if keys is not None:
                    nd['tracks'] = keys
                    break
                ctrl = nxt
            nodes.append(nd)
            nc = struct.unpack_from('<I', data, p2)[0]
            for k in struct.unpack_from('<%di' % nc, data, p2 + 4):
                visit(k, ni, props)
            return
        if flags & 1 or total[0] > max_verts:
            return
        dref, skref = struct.unpack_from('<ii', data, p2)
        if not 0 <= dref < len(sp) or sp[dref][0] not in (b'NiTriShapeData', b'NiTriStripsData'):
            return
        verts, uvs, idx = nif._geometry(data, sp[dref][2], sp[dref][0] == b'NiTriStripsData')
        if not verts or not idx:
            return
        tex, alpha, double = nif._texture_of(data, [(x[0], x[2]) for x in sp], props)
        # this shape's node: a node of its own (a shape is a leaf; it hangs on its parent node)
        sh = {'node': parent, 'name': name, 'R': R, 't': t, 's': s, 'p': [round(v, 3) for v in verts], 'uv': [round(u, 4) for u in uvs],
              'i': idx, 'tex': tex, 'alpha': alpha, 'double': double}
        if 0 <= skref < len(sp) and sp[skref][0] == b'NiSkinInstance':
            sh['skin'] = _skin(data, sp, skref, len(verts) // 3)
        shapes.append(sh)
        total[0] += len(verts) // 3
    visit(0, -1, [])
    # skins name their bones by block: as node indices
    for sh in shapes:
        sk = sh.get('skin')
        if sk:
            sk['bones'] = [at.get(b, -1) for b in sk.pop('bone_blocks')]
            sk['root'] = at.get(sk.pop('root_block'), -1)
    return {'nodes': nodes, 'shapes': shapes}


def _skin(data, sp, si, nverts):
    p = sp[si][2]
    dref, root, nb = struct.unpack_from('<iiI', data, p)
    bones = list(struct.unpack_from('<%di' % nb, data, p + 12))
    out = {'bone_blocks': bones, 'root_block': root, 'inv': [], 'weights': [[] for _ in range(nverts)]}
    if not 0 <= dref < len(sp) or sp[dref][0] != b'NiSkinData':
        return out
    _t, _s, q, end = sp[dref]
    r = struct.unpack_from('<13f', data, q)
    out['skin'] = {'R': [list(r[0:3]), list(r[3:6]), list(r[6:9])], 't': list(r[9:12]), 's': r[12]}
    q += 52
    n = struct.unpack_from('<I', data, q)[0]
    q += 4

    def read_bones(q, with_partition):
        q2 = q + (4 if with_partition else 0)
        inv, w = [], [[] for _ in range(nverts)]
        for b in range(n):
            if q2 + 70 > end:
                return None
            v = struct.unpack_from('<13f', data, q2)
            inv.append({'R': [list(v[0:3]), list(v[3:6]), list(v[6:9])], 't': list(v[9:12]), 's': v[12]})
            q2 += 52 + 16
            nv = struct.unpack_from('<H', data, q2)[0]
            q2 += 2
            if q2 + 6 * nv > end:
                return None                              # (the other layout: this guess runs past the block)
            for _k in range(nv):
                vi, wt = struct.unpack_from('<Hf', data, q2)
                q2 += 6
                if vi < nverts:
                    w[vi].append((b, round(wt, 4)))
        return (inv, w) if q2 == end else None
    got = read_bones(q, False) or read_bones(q, True)
    if got:
        out['inv'], out['weights'] = got
    return out


# ----- what a record animates with ------------------------------------------------------------------------
def _mat(R, t, s):
    return [[R[i][0] * s, R[i][1] * s, R[i][2] * s, t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def _mul4(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _person(db, rec_i):
    """A person's race, sex, build, their own animation model (MODL, '' for none) and the skeleton the game
    gives them without one (the beast one, the female one or everyone's)."""
    import npcbody
    from esm import zstr
    subs = npcbody._subs(db, rec_i)
    d = {}
    for t, v in subs:
        d.setdefault(t, v)
    race = zstr(d.get('RNAM', b''))
    flags = struct.unpack_from('<i', d.get('FLAG', b'\0\0\0\0'))[0]
    female = bool(flags & 1)
    rri = db.resolve_id(race)
    beast, height, weight = False, 1.0, 1.0
    if rri is not None:
        rd = dict(npcbody._subs(db, rri)).get('RADT', b'')
        if len(rd) >= 140:
            hm, hf, wm, wf = struct.unpack_from('<4f', rd, 120)
            height, weight = (hf, wf) if female else (hm, wm)
            beast = bool(struct.unpack_from('<i', rd, 136)[0] & 2)
    return {'subs': subs, 'd': d, 'race': race, 'female': female, 'beast': beast, 'height': height, 'weight': weight,
            'modl': zstr(d['MODL']).lower().replace('\\', '/') if d.get('MODL') else '',
            'default': 'base_animkna.nif' if beast else 'base_anim_female.nif' if female else 'base_anim.nif'}


LAYER_NAMES = {'base_anim.nif': "everyone's", 'base_anim_female.nif': "women's", 'base_animkna.nif': "beast folk's"}


def layers(db, p, modl=None):
    """The animation files a person moves with, in the game's order (OpenMW's NpcAnimation): everyone's
    (xbase_anim.kf), then their own skeleton's when it is neither that nor the default one, the default
    one's (the women's or beast folk's) when they have their own model, and their own model's last. A group
    comes from the last file that has it. modl: another own model to try ('' for none)."""
    own = (p['modl'] if modl is None else modl) or p['default']
    order = []
    if own != 'base_anim.nif':
        order.append('base_anim.nif')
    if own != p['default'] and p['default'] != 'base_anim.nif':
        order.append(p['default'])
    order.append(own)
    out = []
    for m in order:
        f = files_for(db, m)
        if f['kf']:
            out.append({'model': m, 'file': f['kf'], 'label': LAYER_NAMES.get(m) or 'own (%s)' % m.rsplit('/', 1)[-1][:-4]})
    return out


def npc_body(db, rec_i, modl=None):
    """A person for the animation window: their skeleton (their own model's, or the shared one: everyone's,
    the female or beast one) as the tree, and their body parts and clothes on it as npcbody.py picks them: a
    rigid part rides on its bone, with its own placing in its file ('M', mirrored for the left side, as
    parts are made for the right), a skinned part's bones found on the skeleton by name. Returns (tree,
    skeleton path, build) or raises. modl: another own model to try ('' for none)."""
    import npcbody
    from esm import zstr
    p = _person(db, rec_i)
    subs, d, race, female = p['subs'], p['d'], p['race'], p['female']
    height, weight = p['height'], p['weight']
    skel_path = 'meshes/' + ((p['modl'] if modl is None else modl) or p['default'])
    if db.meshes.read(skel_path) is None:
        skel_path = files_for(db, skel_path[len('meshes/'):])['skeleton'] or 'meshes/base_anim.nif'
    if db.meshes.read(skel_path) is None:
        skel_path = 'meshes/base_anim.nif'
    T = tree(db.meshes.read(skel_path))
    if not T:
        raise ValueError("The game's skeleton for people could not be read.")
    by_name = {n['name'].lower(): i for i, n in enumerate(T['nodes'])}
    T['shapes'] = []
    # (what each slot wears, as the 3D view's body picks it)
    skel = npcbody.skeleton(db, skel_path) or {}
    slots = {}
    parts = npcbody._race_parts(db, race)
    for part, sl in npcbody.PART_SLOTS.items():
        bid = parts.get((part, female)) or parts.get((part, False))
        if bid:
            for s in sl:
                slots[s] = (bid, 0)
    if d.get('BNAM'):
        slots[0] = (zstr(d['BNAM']), 0)
    if d.get('KNAM'):
        slots[1] = (zstr(d['KNAM']), 0)
    worn = npcbody._worn(db, subs)
    for rank, item in ((1, 'CLOT'), (2, 'ARMO')):
        for wi in worn.get(item, []):
            pairs, cur = {}, None
            for t, v in npcbody._subs(db, wi):
                if t == 'INDX' and v:
                    cur = v[0]
                    pairs.setdefault(cur, {})
                elif t in ('BNAM', 'CNAM') and cur is not None:
                    pairs[cur][t] = zstr(v)
            for slot, pr in pairs.items():
                pid = (pr.get('CNAM') if female else None) or pr.get('BNAM')
                if pid and slots.get(slot, (None, -1))[1] <= rank:
                    slots[slot] = (pid, rank)
    for slot, (pid, _rank) in slots.items():
        node = npcbody.SLOT_NODE.get(slot)
        model = npcbody._model_of(db, pid)
        if not node or not model or node not in by_name:
            continue
        raw = db.meshes.read('meshes/' + model.lower().replace('\\', '/'))
        P = tree(raw, keep_root=True) if raw else None
        if not P:
            continue
        world = []
        for nd in P['nodes']:
            L = _mat(nd['R'], nd['t'], nd['s'])
            world.append(_mul4(world[nd['parent']], L) if nd['parent'] >= 0 else L)
        skinned = [s for s in P['shapes'] if s.get('skin')]
        shapes = P['shapes']
        if skinned:
            # (a skins file holds several parts: this slot's, by name: "Tri Chest", "Tri Left Hand 0")
            mine = [s for s in skinned if node in (s.get('name') or '').lower()]
            shapes = mine or ([] if any(w in (s.get('name') or '').lower() for s in skinned for w in ('hand', 'chest', 'foot')) else skinned)
        left = node.startswith('left')
        for s in shapes:
            s = dict(s, tex=db.meshes.texture_path(s['tex']))
            sk = s.get('skin')
            if sk:
                names = [P['nodes'][b]['name'].lower() if b >= 0 else '' for b in sk['bones']]
                if not all(n in by_name for n in names):
                    continue
                s['skin'] = dict(sk, bones=[by_name[n] for n in names])
                s['node'] = -1
            else:
                M = _mul4(world[s['node']] if s['node'] >= 0 else _mat(I3, [0, 0, 0], 1.0), _mat(s['R'], s['t'], s['s']))
                if left:
                    M = [[-M[0][j] for j in range(4)]] + M[1:]          # (x mirrored, after its own placing)
                s['node'] = by_name[node]
                s['M'] = [round(v, 5) for row in M for v in row]
            for k in ('R', 't', 's'):
                s.pop(k, None)
            T['shapes'].append(s)
    if not T['shapes']:
        raise ValueError('No body parts were found for this person.')
    return T, skel_path, {'height': height, 'weight': weight}


I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _length(tracks, keys):
    return round(max([k[0] for tr in tracks.values() for part in ('rot', 'pos', 'scale') for k in tr[part]] + [k[0] for k in keys] + [0.0]), 3)


def source(db, file):
    """One animation file's tracks, text keys and groups."""
    file = (file or '').lower().replace('\\', '/')
    raw = db.meshes.read(file) if file.startswith('meshes/') and file.endswith('.kf') else None
    if not raw:
        raise ValueError('That animation file is missing.')
    tracks = tracks_of_kf(raw)
    keys, _i = text_keys(raw)
    return {'file': file, 'tracks': tracks, 'keys': keys, 'groups': groups(keys), 'length': _length(tracks, keys)}


def own_model(db, rec_i):
    """The person's own animation model when it is one of your mod's that only they use, else None."""
    import library
    p = _person(db, rec_i)
    m = p['modl']
    if not m.startswith(library.SUB + '/'):
        return None
    me = db.recs[rec_i][1].lower()
    for i, mm in _npc_models(db):
        if mm == m and db.recs[i][1].lower() != me:
            return None
    return m


def _npc_models(db):
    """[(record index, own animation model)] for every person with one."""
    import npcbody
    from esm import zstr
    out = []
    for i, r in enumerate(db.recs):
        if r is not None and r[0] == 'NPC_':
            for t, v in npcbody._subs(db, i):
                if t == 'MODL':
                    out.append((i, zstr(v).lower().replace('\\', '/')))
                    break
    return out


def _for_person(db, rec_i, modl=None):
    """A person: their body on their skeleton, and their animation as the layers the game puts together.
    'sources' are the files in order, each with its text keys and groups; 'groups' every group once, from
    the last file that has it ('src'); the tracks and keys given are those of the file the first group shown
    (Idle) comes from; others come from /api/anim/source when a group of theirs is picked."""
    r = db.recs[rec_i]
    p = _person(db, rec_i)
    T, skel_path, build = npc_body(db, rec_i, modl)
    for n in T['nodes']:
        n.pop('tracks', None)
    srcs = layers(db, p, modl)
    if not srcs:
        raise ValueError("The game's animation for people (xbase_anim.kf) is missing.")
    merged = {}
    for si, s in enumerate(srcs):
        raw = db.meshes.read(s['file'])
        s['keys'], _i = text_keys(raw)
        s['groups'] = groups(s['keys'])
        for g in s['groups']:
            merged[g['name'].lower()] = dict(g, src=si)
    G = sorted(merged.values(), key=lambda g: (g['src'], g['start']))
    first = next((g for g in G if g['name'].lower() == 'idle'), G[0] if G else None)
    si = first['src'] if first else len(srcs) - 1
    s = source(db, srcs[si]['file'])
    return {'id': r[1], 'type': r[0], 'name': r[2] or '', 'files': files_for(db, skel_path[len('meshes/'):]), 'tree': T,
            'tracks': s['tracks'], 'keys': s['keys'], 'src': si, 'groups': G, 'keyfile': srcs[si]['file'], 'length': s['length'],
            'sources': [{'file': x['file'], 'model': x['model'], 'label': x['label'], 'keys': x['keys'], 'groups': x['groups']} for x in srcs],
            'build': build, 'shared': True, 'modl': p['modl'] if modl is None else modl, 'own': own_model(db, rec_i) if modl is None else None,
            'trying': modl}


def for_record(db, rec_i, modl=None):
    """Everything the animation window needs for an object, creature or person: its node tree and shapes
    (textures resolved), the tracks by node name, the text keys, the groups, and which file holds the keys."""
    r = db.recs[rec_i]
    if r is None or (not r[5] and r[0] != 'NPC_'):
        raise ValueError('That has no model.')
    if r[0] == 'NPC_':
        return _for_person(db, rec_i, modl)
    f = files_for(db, r[5])
    base = f['skeleton'] or f['model']
    raw = db.meshes.read(base)
    if not raw:
        raise ValueError("The model's file is missing.")
    T = tree(raw)
    if not T:
        raise ValueError('This model could not be read.')
    for s in T['shapes']:
        s['tex'] = db.meshes.texture_path(s['tex'])
    if f['kf']:
        kraw = db.meshes.read(f['kf'])
        tracks = tracks_of_kf(kraw)
        keys, _i = text_keys(kraw)
        keyfile = f['kf']
    else:
        tracks = {n['name']: n.pop('tracks') for n in T['nodes'] if n.get('tracks')}
        keys, _i = text_keys(raw)
        keyfile = base if keys else None
    for n in T['nodes']:
        n.pop('tracks', None)
    length = max([k[0] for tr in tracks.values() for part in ('rot', 'pos', 'scale') for k in tr[part]] + [k[0] for k in keys] + [0.0])
    return {'id': r[1], 'type': r[0], 'name': r[2] or '', 'files': f, 'tree': T, 'tracks': tracks, 'keys': keys,
            'groups': groups(keys), 'keyfile': keyfile, 'length': round(length, 3)}


def _write_anim(db, rec_i, new_kf, how, kf_src=None, label='own animation'):
    """Write an animation file for an object or creature: over its own .kf (or model) in your mod's folder
    ('everywhere'), or as copies of its model, x-model and the new .kf under one new name with a new record
    ('own'). kf_src: the file new_kf replaces (its own keyfile when None)."""
    import os
    import editing
    import library
    import assets
    editing._require_project(db)
    r = db.recs[int(rec_i)]
    if r[0] == 'NPC_':
        if how == 'own':
            raise ValueError("A person's own animation is made with person_put.")
        info = {'kf': kf_src or for_record(db, int(rec_i))['keyfile'], 'skeleton': None, 'model': None}
    else:
        info = files_for(db, r[5])
    keyfile = kf_src or info['kf'] or info['skeleton'] or info['model']
    base = library.data_dir(db)

    def put(rel, data):
        full = os.path.join(base, *rel.split('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        prev = db.meshes.loose.get(rel)
        if prev and os.path.normcase(os.path.abspath(prev)) != os.path.normcase(os.path.abspath(full)):
            assets._COVERED[rel] = prev
        with open(full, 'wb') as fh:
            fh.write(data)
        library._register(db, rel, full)
        return full
    if how != 'own':
        return {'path': keyfile, 'file': put(keyfile, new_kf), 'how': 'everywhere'}
    folder = os.path.join(base, 'meshes', library.SUB)
    os.makedirs(folder, exist_ok=True)
    stem = library._free_name(folder, library._slug(os.path.splitext(os.path.basename(r[5]))[0]) + '_anim', '.nif')
    rels = {'model': 'meshes/%s/%s.nif' % (library.SUB, stem), 'skeleton': 'meshes/%s/x%s.nif' % (library.SUB, stem),
            'kf': 'meshes/%s/x%s.kf' % (library.SUB, stem)}
    for part in ('model', 'skeleton'):
        if info.get(part):
            put(rels[part], new_kf if info[part] == keyfile else db.meshes.read(info[part]))
    if info.get('kf') or keyfile.endswith('.kf'):
        put(rels['kf'], new_kf if keyfile.endswith('.kf') else db.meshes.read(info['kf']))
    made = assets.record_with_model(db, int(rec_i), '%s\\%s.nif' % (library.SUB, stem), (r[2] or r[1]) + ' (%s)' % label)
    return dict(made, path=rels['kf'] if keyfile.endswith('.kf') else rels['model'], how='own')


def retime(db, rec_i, group, factor, how='everywhere'):
    """A group played factor times as long (0.5 twice as fast, 2 half speed), in the file that holds the
    object's animation; the groups after it keep their own timing, moved along."""
    factor = float(factor)
    if not 0.1 <= factor <= 10:
        raise ValueError('Make it between a tenth and ten times as long.')
    d = for_record(db, int(rec_i))
    g = next((x for x in d['groups'] if x['name'].lower() == (group or '').lower()), None)
    if not g:
        raise ValueError('There is no group called "%s".' % group)
    keyfile = d['sources'][g['src']]['file'] if d.get('sources') else d['keyfile']
    raw = db.meshes.read(keyfile)
    if d['type'] == 'NPC_' and how == 'own':
        import kf
        part = stretch(_part_of(kf.read(raw), g['name'], g['start'], g['stop']), factor)
        out = person_put(db, rec_i, g['name'], part)
    else:
        out = _write_anim(db, rec_i, remap_times(raw, retimer(g['start'], g['stop'], factor)), how, keyfile, 'retimed')
    out['group'] = {'name': g['name'], 'start': g['start'], 'stop': round(g['start'] + (g['stop'] - g['start']) * factor, 4)}
    return out


def adopt(db, rec_i, from_i, how='everywhere'):
    """Give an object or creature another one's animation: the other's .kf in place of its own (their
    skeletons must name the same bones). Returns the bones matched and what was written."""
    me, other = for_record(db, int(rec_i)), for_record(db, int(from_i))
    if me['type'] == 'NPC_' or other['type'] == 'NPC_':
        raise ValueError("People share the game's animation for their skeleton: giving them another's comes later.")
    if not other['files'].get('kf'):
        raise ValueError("%s has no animation file (.kf) to give." % (other['name'] or other['id']))
    if not me['files'].get('skeleton') and not me['files'].get('kf'):
        raise ValueError("%s has no skeleton of its own (an x-model) for an animation to move." % (me['name'] or me['id']))
    if other['files']['kf'] == me['files'].get('kf'):
        raise ValueError('%s already moves with that animation (they share it).' % (me['name'] or me['id']))
    mine = {n['name'].lower(): n for n in me['tree']['nodes']}
    raw = db.meshes.read(other['files'].get('skeleton') or other['files']['model'])
    ot = {n['name'].lower(): n for n in (tree(raw) or {'nodes': []})['nodes']}
    matched, nbones = _skeleton_match(mine, other['tracks'].keys(), ot, me['name'] or me['id'], other['name'] or other['id'])
    theirs = range(nbones)
    kf = db.meshes.read(other['files']['kf'])
    target = me['files'].get('kf') or (me['files']['model'][:-4].rsplit('/', 1)[0] + '/x' + me['files']['model'].rsplit('/', 1)[1][:-4] + '.kf')
    out = _write_anim(db, rec_i, kf, how, target, 'animation of ' + (other['name'] or other['id']))
    out.update(matched=matched, bones=len(theirs))
    return out


def save_keys(db, rec_i, keys, how='everywhere', file=None, group=None):
    """The object's text keys changed: written over the file in your mod's folder ('everywhere', an override
    of the game's) or into copies under a new name with a new record ('own'). For a person, file is the
    layer the keys are in, and 'own' puts the group (by name) into their own animation file. Returns what
    was written."""
    import os
    import editing
    import library
    import assets
    editing._require_project(db)
    r = db.recs[int(rec_i)]
    clean = []
    for k in keys:
        t, txt = float(k[0]), str(k[1]).strip()
        if txt:
            if not 0 <= t <= 10000:
                raise ValueError('A text key\'s time must be 0 seconds or more.')
            clean.append((t, txt))
    if r[0] == 'NPC_':
        # (a person's layers: everyone's file changes everyone using it; their own model's file is theirs)
        files = [s['file'] for s in layers(db, _person(db, int(rec_i)))]
        keyfile = file if file in files else files[-1]
        if how == 'own':
            return person_keys(db, int(rec_i), keyfile, clean, group)
        info = {'kf': keyfile, 'skeleton': None, 'model': None}
    else:
        info = files_for(db, r[5])
    keyfile = info['kf'] or (info['skeleton'] or info['model'])
    raw = db.meshes.read(keyfile)
    if not raw:
        raise ValueError('The file with the text keys is missing.')
    new = write_text_keys(raw, clean)
    base = library.data_dir(db)

    def put(rel, data):
        full = os.path.join(base, *rel.split('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        prev = db.meshes.loose.get(rel)
        if prev and os.path.normcase(os.path.abspath(prev)) != os.path.normcase(os.path.abspath(full)):
            assets._COVERED[rel] = prev
        with open(full, 'wb') as fh:
            fh.write(data)
        library._register(db, rel, full)
        return full
    if how != 'own':
        return {'path': keyfile, 'file': put(keyfile, new), 'how': 'everywhere'}
    # (an own copy: the model, its x-model and its .kf under one new name, so the copy still finds them)
    folder = os.path.join(base, 'meshes', library.SUB)
    os.makedirs(folder, exist_ok=True)
    stem = library._free_name(folder, library._slug(os.path.splitext(os.path.basename(r[5]))[0]) + '_anim', '.nif')
    rels = {'model': 'meshes/%s/%s.nif' % (library.SUB, stem), 'skeleton': 'meshes/%s/x%s.nif' % (library.SUB, stem),
            'kf': 'meshes/%s/x%s.kf' % (library.SUB, stem)}
    for part in ('model', 'skeleton', 'kf'):
        src = info.get(part)
        if not src:
            continue
        data = new if src == keyfile else db.meshes.read(src)
        put(rels[part], data)
    made = assets.record_with_model(db, int(rec_i), '%s\\%s.nif' % (library.SUB, stem), (r[2] or r[1]) + ' (own animation)')
    return dict(made, path=rels['kf'] if info['kf'] else rels['model'], how='own')


# ----- a person's own animation ------------------------------------------------------------------------------
def _put_file(db, rel, data):
    """A file into your mod's folder at rel (meshes/...), noting a loose file of the game's it covers."""
    import os
    import library
    import assets
    full = os.path.join(library.data_dir(db), *rel.split('/'))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    prev = db.meshes.loose.get(rel)
    if prev and os.path.normcase(os.path.abspath(prev)) != os.path.normcase(os.path.abspath(full)):
        assets._COVERED[rel] = prev
    with open(full, 'wb') as fh:
        fh.write(data)
    library._register(db, rel, full)
    return full


def _part_of(k, name, start, stop, keys=None):
    """A group cut out of an animation (kf.read) as one of its own, starting at 0, with only its own text
    keys and its sounds; keys: the text keys to use in place of the file's ([(time, text)], file times)."""
    import kf
    part = kf.cut(k, start, stop)
    lines = kf._lines(part['tk']) if keys is None else [(t - start, x) for t, x in kf._lines(keys) if start - 1e-4 <= t <= stop + 1e-4]
    mine = lambda x: x.split(':', 1)[0].strip().lower() in (name.lower(), 'sound', 'soundgen')
    part['tk'] = kf._joined([(max(0.0, t), x) for t, x in lines if mine(x)])
    return part


def stretch(part, factor):
    """An animation played factor times as long."""
    f = lambda keys: [(t * factor, v, e) for t, v, e in keys]
    return dict(part, tk=[(t * factor, x) for t, x in part['tk']],
                tracks=[dict(tr, rot=f(tr['rot']), pos=f(tr['pos']), scale=f(tr['scale']), start=tr['start'] * factor,
                             stop=tr['stop'] * factor) for tr in part['tracks']])


def _set_model(db, rec_i, model):
    """A person's own animation model (MODL) set, or taken out (model '' or None)."""
    from esm import iter_subrecords
    from project import join_subs, zs
    import editing
    r = db.recs[rec_i]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data) if t != 'MODL']
    if model:
        subs.insert(1, ('MODL', zs(model.replace('/', '\\'))))
    db.project.set_record(r[0], r[7], r[6], join_subs(subs))
    editing.commit(db, ('Gave %s the animation "%s"' % (r[2] or r[1], model)) if model else
                   ('%s moves with the shared animation again' % (r[2] or r[1])))
    return db.resolve_id(r[1])


def person_put(db, rec_i, name, part):
    """For one person only: their own animation file gets the group (over the same group in it, or added
    after its end), layered by the game over the shared animation. A person without an own model of the
    mod's gets one: their skeleton copied under a new name in meshes/wslib, with the .kf beside it, and their
    record's model (MODL) pointed at it. Returns what was written."""
    import kf
    import editing
    editing._require_project(db)
    rec_i = int(rec_i)
    p = _person(db, rec_i)
    base = None
    if p['modl']:
        f = files_for(db, p['modl'])
        if f['kf']:
            base = kf.read(db.meshes.read(f['kf']))
    if base is not None:
        g = next((x for x in groups(kf._lines(base['tk'])) if x['name'].lower() == name.lower()), None)
        new = kf.put(base, g['start'], g['stop'], part) if g else kf.append(base, part)
    else:
        new = dict(part, missing=[])
    out = _person_kf(db, rec_i, kf.write(new), 'Changed the animation "%s"' % name)
    out['missing'] = new.get('missing', [])
    return out


def _person_kf(db, rec_i, data, note):
    """A person's own animation file written: over their own model's of the mod's, or with a new own model
    (their skeleton copied under a new name in meshes/wslib, the .kf beside it, their MODL pointed at it)."""
    import os
    import editing
    import library
    p = _person(db, rec_i)
    mine = own_model(db, rec_i)
    if mine:
        rel = mine
    else:
        folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
        os.makedirs(folder, exist_ok=True)
        stem = library._free_name(folder, library._slug(db.recs[rec_i][1]) + '_anim', '.nif')
        rel = '%s/%s.nif' % (library.SUB, stem)
        src = p['modl'] or p['default']
        f = files_for(db, src)
        skel = db.meshes.read('meshes/' + src) or (db.meshes.read(f['skeleton']) if f['skeleton'] else None)
        if not skel:
            raise ValueError("This person's skeleton file is missing.")
        _put_file(db, 'meshes/' + rel, skel)
        _put_file(db, 'meshes/%s/x%s' % tuple(rel.rsplit('/', 1)), db.meshes.read(f['skeleton']) if f['skeleton'] else skel)
    d, fn = rel.rsplit('/', 1)
    kfrel = 'meshes/%s/x%s.kf' % (d, fn[:-4])
    full = _put_file(db, kfrel, data)
    if not mine:
        _set_model(db, rec_i, rel)
    else:
        editing.commit(db, note)
    return {'path': kfrel, 'file': full, 'model': rel, 'how': 'own', 'i': db.resolve_id(db.recs[rec_i][1]), 'id': db.recs[rec_i][1]}


def bring_kf(db, rec_i, data, how='everywhere'):
    """An animation file made elsewhere (a .kf from Blender's NIF tools, another mod) given to a creature
    (over its own in your mod's folder, or as its own copy) or to one person (as their own animation,
    layered over the shared one). Its bones must be this skeleton's: 80% by name, and where it moves a bone
    to a place, about as far from its parent."""
    import kf
    import editing
    editing._require_project(db)
    rec_i = int(rec_i)
    k = kf.read(data)
    if not k['tracks']:
        raise ValueError('That animation file moves nothing.')
    gs = groups(kf._lines(k['tk']))
    if not gs:
        raise ValueError('That animation file names no groups (no "Idle: Start" and so on in its text keys).')
    me = for_record(db, rec_i)
    who = me['name'] or me['id']
    if me['type'] != 'NPC_' and not me['files'].get('skeleton') and not me['files'].get('kf'):
        raise ValueError('%s has no skeleton of its own (an x-model) for an animation to move.' % who)
    mine = {n['name'].lower(): n for n in me['tree']['nodes']}
    theirs = {tr['bone'].lower(): {'t': tr['pos'][0][1]} for tr in k['tracks'] if tr['pos']}
    # (a bone it doesn't move to a place counts as the same length)
    for tr in k['tracks']:
        b = tr['bone'].lower()
        if b not in theirs and b in mine:
            theirs[b] = mine[b]
    matched, bones = _skeleton_match(mine, [tr['bone'] for tr in k['tracks']], theirs, who, 'the animation file')
    if me['type'] == 'NPC_':
        out = _person_kf(db, rec_i, data, 'Gave %s an animation of their own' % who)
    else:
        target = me['files'].get('kf') or (me['files']['model'][:-4].rsplit('/', 1)[0] + '/x' + me['files']['model'].rsplit('/', 1)[1][:-4] + '.kf')
        out = _write_anim(db, rec_i, data, how, target, 'brought-in animation')
    out.update(matched=matched, bones=bones, groups=[g['name'] for g in gs])
    return out


def person_keys(db, rec_i, keyfile, keys, group):
    """Text keys changed for one person only: the group (with its Start and Stop where the keys now put
    them) into their own animation file."""
    import kf
    if not group:
        raise ValueError('Pick the group to keep for this person.')
    gs = [g for g in groups(keys) if g['name'].lower() == group.lower()]
    if not gs:
        raise ValueError('The group "%s" needs its Start and Stop keys.' % group)
    g = gs[0]
    if g['stop'] <= g['start']:
        raise ValueError('The group must stop after it starts.')
    k = kf.read(db.meshes.read(keyfile))
    return person_put(db, rec_i, g['name'], _part_of(k, g['name'], g['start'], g['stop'], keys))


def _skeleton_match(mine, names, theirs, me, other):
    """Raise unless an animation moving the bones names (with the skeleton theirs, {name: node}) fits the
    skeleton mine ({name: node}): 80% of the bones by name, 75% of those about as long from their parents."""
    names = {k.lower() for k in names}
    matched = [k for k in names if k in mine]
    if not names or len(matched) < 0.8 * len(names):
        raise ValueError("Their skeletons don't match: only %d of the %d bones %s moves are in %s." % (len(matched), len(names), other, me))
    # (most skeletons name their bones alike, Bip01 and on, though their bodies differ: the bones must also
    # sit about as far from their parents in both, or the walk of one bends the other out of shape)
    length = lambda n: sum(v * v for v in n['t']) ** 0.5
    alike = [k for k in matched if k in theirs and abs(length(mine[k]) - length(theirs[k])) <= 0.25 * max(length(mine[k]), length(theirs[k]), 2.0)]
    if len(alike) < 0.75 * len(matched):
        raise ValueError("Their skeletons differ: %s's bones are named like %s's, but only %d of %d are the same length, so its "
                         "animation would bend %s out of shape." % (other, me, len(alike), len(matched), me))
    return len(matched), len(names)


def person_animations(db):
    """The own animation models people in the game move with: [{'model', 'example', 'people', 'groups'}]."""
    seen = {}
    for i, m in _npc_models(db):
        e = seen.setdefault(m, [db.recs[i][2] or db.recs[i][1], 0])
        e[1] += 1
    out = []
    for m, (ex, n) in seen.items():
        f = files_for(db, m)
        if not f['kf'] or m in LAYER_NAMES:
            continue
        raw = db.meshes.read(f['kf'])
        gs = groups(text_keys(raw)[0])
        if gs:
            sp = _spans(raw) or []
            beast = any(t == b'NiStringExtraData' and b'tail' in raw[p:e].lower() for t, _s, p, e in sp)
            out.append({'model': m, 'example': ex, 'people': n, 'groups': [g['name'] for g in gs][:8], 'count': len(gs), 'beast': beast})
    return sorted(out, key=lambda x: (-x['people'], x['model']))


def person_adopt(db, rec_i, model):
    """A person given another own animation model (one other people move with), or back to the shared
    animation (model ''): their record's MODL. Their skeletons must agree."""
    import editing
    editing._require_project(db)
    rec_i = int(rec_i)
    p = _person(db, rec_i)
    model = (model or '').lower().replace('\\', '/')
    who = db.recs[rec_i][2] or db.recs[rec_i][1]
    if model:
        f = files_for(db, model)
        if not f['kf']:
            raise ValueError('That model has no animation file (.kf) beside it.')
        node_map = lambda path: {n['name'].lower(): n for n in ((tree(db.meshes.read(path)) if path and db.meshes.read(path) else None) or {'nodes': []})['nodes']}
        mine = node_map('meshes/' + p['default'])
        theirs = node_map('meshes/' + model if db.meshes.read('meshes/' + model) else f['skeleton'])
        # (beast folk walk on other legs and have a tail: their animations and others' don't swap)
        tail = lambda nodes: any('tail' in n for n in nodes)
        if tail(mine) != tail(theirs):
            raise ValueError("%s is made for %s, and %s is not." % (model.rsplit('/', 1)[-1][:-4], 'beast folk' if tail(theirs) else 'people without tails',
                                                                    who))
        matched, bones = _skeleton_match(mine, tracks_of_kf(db.meshes.read(f['kf'])).keys(), theirs, who, model.rsplit('/', 1)[-1][:-4])
    else:
        matched = bones = 0
    i = _set_model(db, rec_i, model)
    return {'i': i, 'id': db.recs[i][1], 'model': model, 'matched': matched, 'bones': bones}


def files_for(db, model):
    """The files an object's animation is in: {'model', 'skeleton' (x-model or None), 'kf' or None}, as paths
    under meshes/ that exist."""
    m = model.lower().replace('\\', '/')
    d, f = m.rsplit('/', 1) if '/' in m else ('', m)
    pre = 'meshes/' + (d + '/' if d else '')
    xs = pre + 'x' + f
    kf = pre + 'x' + f[:-4] + '.kf'
    has = lambda p: p in db.meshes.loose or p in db.meshes.packed
    if not has(xs) and f.startswith('x') and has('meshes/' + m):
        # (a model named with its x already, as some people's are: it is its own skeleton, its .kf beside it)
        xs, kf = 'meshes/' + m, 'meshes/' + m[:-4] + '.kf'
    return {'model': 'meshes/' + m, 'skeleton': xs if has(xs) else None, 'kf': kf if has(kf) else None}
