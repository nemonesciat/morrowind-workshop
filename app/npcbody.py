"""NPC bodies for the 3D view: the race's body parts (head, hair, neck, chest, arms, hands, legs,
feet, a tail), with the clothes and armour the NPC carries on top, put together on the skeleton the
way OpenMW does it.

Each part is attached to its named node of the skeleton (base_anim.nif: "Head", "Chest", "Left
Forearm", ...), parts for the left side mirrored. Skinned parts (the chest and hands, in the "skins"
files) are bent onto the skeleton's resting pose with their bone weights."""
import math
import struct

import nif
from esm import iter_subrecords, zstr

# ESM part slots (as armour and clothing name them) -> skeleton node they hang from
SLOT_NODE = {0: 'head', 1: 'head', 2: 'neck', 3: 'chest', 4: 'groin', 5: 'groin', 6: 'right hand', 7: 'left hand',
             8: 'right wrist', 9: 'left wrist', 10: 'shield bone', 11: 'right forearm', 12: 'left forearm',
             13: 'right upper arm', 14: 'left upper arm', 15: 'right foot', 16: 'left foot', 17: 'right ankle',
             18: 'left ankle', 19: 'right knee', 20: 'left knee', 21: 'right upper leg', 22: 'left upper leg',
             23: 'right clavicle', 24: 'left clavicle', 25: 'weapon bone', 26: 'tail'}
# a race body part (BYDT part) -> the slots it fills
PART_SLOTS = {0: (0,), 1: (1,), 2: (2,), 3: (3,), 4: (4,), 5: (6, 7), 6: (8, 9), 7: (11, 12), 8: (13, 14), 9: (15, 16),
              10: (17, 18), 11: (19, 20), 12: (21, 22), 13: (23, 24), 14: (26,)}
# which armour or clothing type goes where (the best one of each is worn)
ARMOR_SLOTS = 11
_skel_cache, _part_cache = {}, {}
I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _xf(R, t, s, v):
    a = nif._apply(R, v)
    return [t[0] + s * a[0], t[1] + s * a[1], t[2] + s * a[2]]


def _nodes(raw):
    """Every node and shape of a .nif with its transform in the file: [{i, type, name, R, t, s, ...}]."""
    blocks = nif._blocks(raw)
    if not blocks:
        return None, None
    out = {}

    def visit(i, R, t, s, props, parent):
        if i < 0 or i >= len(blocks) or i in out:
            return
        typ, p = blocks[i]
        if not (typ in nif.NODE_TYPES or typ in nif.GEOM_TYPES):
            return
        name, q = nif._str(raw, p)
        flags = struct.unpack_from('<H', raw, q + 8)[0]
        _f, (lR, lt, ls), p2 = nif._read_av(raw, p)
        q2 = q + 8 + 2 + 12 + 36 + 4 + 12
        nprops = struct.unpack_from('<I', raw, q2)[0]
        myprops = list(struct.unpack_from('<%di' % nprops, raw, q2 + 4)) + props
        nR = nif._mul(R, lR)
        nt = [t[k] + s * v for k, v in enumerate(nif._apply(R, lt))]
        ns = s * ls
        rec = {'i': i, 'type': typ, 'name': name, 'R': nR, 't': nt, 's': ns, 'lR': lR, 'lt': lt, 'ls': ls,
               'hidden': bool(flags & 1) and i != 0, 'props': myprops, 'parent': parent}
        out[i] = rec
        if typ in nif.SKIP_SUBTREES:
            return
        if typ in nif.NODE_TYPES:
            nc = struct.unpack_from('<I', raw, p2)[0]
            for k in struct.unpack_from('<%di' % nc, raw, p2 + 4):
                visit(k, nR, nt, ns, myprops, i)
        else:
            rec['data'], rec['skin'] = struct.unpack_from('<ii', raw, p2)
    visit(0, I3, [0, 0, 0], 1.0, [], None)
    return blocks, out


def skeleton(db, path):
    """{node name (lower case): (R, t, s)} of a skeleton, in its resting pose."""
    if path in _skel_cache:
        return _skel_cache[path]
    raw = db.meshes.read(path)
    res = None
    if raw:
        _b, nodes = _nodes(raw)
        if nodes:
            res = {}
            for n in nodes.values():
                if n['type'] in nif.NODE_TYPES:
                    res.setdefault(n['name'].lower(), (n['R'], n['t'], n['s']))
    _skel_cache[path] = res
    return res


def _skin(raw, blocks, nodes, shape, skel, verts):
    """Bend a skinned shape's vertices onto the skeleton with its bone weights; None if unreadable."""
    try:
        typ, p = blocks[shape['skin']]
        if typ != b'NiSkinInstance':
            return None
        data_ref, _root = struct.unpack_from('<ii', raw, p)
        nb = struct.unpack_from('<I', raw, p + 8)[0]
        bones = struct.unpack_from('<%di' % nb, raw, p + 12)
        dtyp, q = blocks[data_ref]
        if dtyp != b'NiSkinData':
            return None
        # The skin's own "overall" transform (36 + 12 + 4 bytes) is skipped: the game never applies it
        # (OpenMW's NifLoader takes only each bone's bind transform, and the bone's pose on the skeleton).
        # The game's own skins files carry an identity there, but Tamriel Rebuilt's Blender exports carry a
        # real turn and offset, and applying it on top of the bone offsets threw gauntlets to chest height
        # and lifted cuirasses above the head (Old Ebonheart's marines, 2026-10-22).
        q += 36 + 12 + 4
        nbones = struct.unpack_from('<I', raw, q)[0]; q += 4
        q += 4                                        # skin partition ref
        if nbones != nb:
            return None
        nv = len(verts) // 3
        acc = [[0.0, 0.0, 0.0] for _ in range(nv)]
        wsum = [0.0] * nv
        for b in range(nb):
            bR = [list(struct.unpack_from('<3f', raw, q + k * 12)) for k in range(3)]
            q += 36
            bt = list(struct.unpack_from('<3f', raw, q)); q += 12
            bs = struct.unpack_from('<f', raw, q)[0]; q += 4
            q += 16                                   # bounding sphere
            n = struct.unpack_from('<H', raw, q)[0]; q += 2
            bname = nodes.get(bones[b], {}).get('name', '').lower()
            pose = skel.get(bname)
            if pose is None:
                bn = nodes.get(bones[b])
                pose = (bn['R'], bn['t'], bn['s']) if bn else (I3, [0, 0, 0], 1.0)
            for _k in range(n):
                vi, w = struct.unpack_from('<Hf', raw, q); q += 6
                if vi >= nv:
                    continue
                v = verts[vi * 3:vi * 3 + 3]
                v = _xf(bR, bt, bs, v)                # mesh (in the skeleton root's space) -> this bone's space
                v = _xf(pose[0], pose[1], pose[2], v)  # bone -> where the bone stands now
                a = acc[vi]
                a[0] += w * v[0]; a[1] += w * v[1]; a[2] += w * v[2]
                wsum[vi] += w
        out = []
        for vi in range(nv):
            w = wsum[vi] or 1.0
            out += [acc[vi][0] / w, acc[vi][1] / w, acc[vi][2] / w]
        return out
    except (struct.error, IndexError, KeyError):
        return None


def part_shapes(db, model, node, skel):
    """One body part on the skeleton: shapes like mesh_from_nif's, in the NPC's own space."""
    key = (model.lower(), node, id(skel))
    if key in _part_cache:
        return _part_cache[key]
    raw = db.meshes.read('meshes/' + model.lower().replace('\\', '/'))
    out = []
    if raw:
        blocks, nodes = _nodes(raw)
        if nodes:
            shapes = [n for n in nodes.values() if n['type'] in nif.GEOM_TYPES and not n['hidden']]
            skinned = [n for n in shapes if n.get('skin', -1) >= 0]
            if skinned:
                # a skins file holds several parts: keep the one for this slot ("Tri Chest", "Tri Left Hand 0")
                mine = [n for n in skinned if node in n['name'].lower()]
                shapes = mine or ([] if any(w in n['name'].lower() for n in skinned for w in ('hand', 'chest', 'foot')) else skinned)
            bone = skel.get(node, (I3, [0, 0, 0], 1.0))
            left = node.startswith('left')
            for n in shapes:
                dtyp, dp = blocks[n['data']] if 0 <= n['data'] < len(blocks) else (None, 0)
                if dtyp not in (b'NiTriShapeData', b'NiTriStripsData'):
                    continue
                verts, uvs, idx = nif._geometry(raw, dp, dtyp == b'NiTriStripsData')
                if not verts or not idx:
                    continue
                pos = None
                if n.get('skin', -1) >= 0:
                    pos = _skin(raw, blocks, nodes, n, skel, verts)
                flip = False
                if pos is None:
                    pos = []
                    for k in range(0, len(verts), 3):
                        v = _xf(n['R'], n['t'], n['s'], verts[k:k + 3])      # within the part's file
                        if left:
                            v[0] = -v[0]                                     # parts are made for the right side
                        pos += _xf(bone[0], bone[1], bone[2], v)
                    det = _det(n['R']) * _det(bone[0])
                    flip = (det < 0) != left
                tex, alpha, double = nif._texture_of(raw, blocks, n['props'])
                if flip:
                    idx = [v for k in range(0, len(idx) - 2, 3) for v in (idx[k], idx[k + 2], idx[k + 1])]
                out.append({'p': [round(v, 2) for v in pos], 'uv': [round(u, 4) for u in uvs], 'i': idx,
                            'tex': db.meshes.texture_path(tex), 'alpha': alpha, 'double': double})
    _part_cache[key] = out
    if len(_part_cache) > 2000:
        _part_cache.pop(next(iter(_part_cache)))
    return out


def _det(R):
    return (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1]) - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
            + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))


def _subs(db, ri):
    r = db.recs[ri]
    return [(t, bytes(d)) for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2])]


_body_index = {}


def _race_parts(db, race):
    """{(BYDT part, female): body part id} of a race's own skin parts (not first-person ones)."""
    stamp = (id(db.recs), len(db.recs))
    if _body_index.get('stamp') != stamp:
        idx = {}
        for (tag, key), lst in db.by_key.items():
            if tag != 'BODY' or not lst or lst[-1] in db.dead or '1st' in key:
                continue
            d = dict(_subs(db, lst[-1]))
            by = d.get('BYDT', b'')
            if len(by) < 4 or by[3] != 0 or by[1]:          # skin parts only, not vampire ones
                continue
            rk = zstr(d.get('FNAM', b'')).lower()
            idx.setdefault(rk, {}).setdefault((by[0], bool(by[2] & 1)), db.recs[lst[-1]][1])
        _body_index.update(stamp=stamp, idx=idx)
    return _body_index['idx'].get(race.lower(), {})


def _model_of(db, rid):
    ri = db.resolve_id(rid) if rid else None
    if ri is None:
        return None
    return next((zstr(d) for t, d in _subs(db, ri) if t == 'MODL'), None)


def npc_body(db, ri):
    """The shapes of an NPC dressed as they would be: [{p, uv, i, tex, alpha, double}] or None."""
    subs = _subs(db, ri)
    d = {}
    for t, v in subs:
        d.setdefault(t, v)
    race = zstr(d.get('RNAM', b''))
    flags = struct.unpack_from('<i', d.get('FLAG', b'\0\0\0\0'))[0]
    female = bool(flags & 1)
    rri = db.resolve_id(race)
    beast, height, weight = False, 1.0, 1.0
    if rri is not None:
        rd = dict(_subs(db, rri)).get('RADT', b'')
        if len(rd) >= 140:
            hm, hf, wm, wf = struct.unpack_from('<4f', rd, 120)
            height, weight = (hf, wf) if female else (hm, wm)
            beast = bool(struct.unpack_from('<i', rd, 136)[0] & 2)
    skel_path = 'meshes/' + (zstr(d['MODL']).lower().replace('\\', '/') if d.get('MODL') else
                             ('base_animkna.nif' if beast else 'base_anim_female.nif' if female else 'base_anim.nif'))
    skel = skeleton(db, skel_path) or skeleton(db, 'meshes/base_anim.nif')
    if not skel:
        return None
    # what fills each slot: the race's skin, the NPC's own head and hair, then clothes, then armour
    slots = {}
    parts = _race_parts(db, race)
    for part, sl in PART_SLOTS.items():
        bid = parts.get((part, female)) or parts.get((part, False))
        if bid:
            for s in sl:
                slots[s] = (bid, 0)
    if d.get('BNAM'):
        slots[0] = (zstr(d['BNAM']), 0)
    if d.get('KNAM'):
        slots[1] = (zstr(d['KNAM']), 0)
    worn = _worn(db, subs)
    # clothes over the skin, armour over clothes; each piece names the slots it covers, with a part
    # for men (BNAM) and maybe one for women (CNAM)
    for rank, item in ((1, 'CLOT'), (2, 'ARMO')):
        for wi in worn.get(item, []):
            pairs, cur = {}, None
            for t, v in _subs(db, wi):
                if t == 'INDX' and v:
                    cur = v[0]
                    pairs.setdefault(cur, {})
                elif t in ('BNAM', 'CNAM') and cur is not None:
                    pairs[cur][t] = zstr(v)
            for slot, pr in pairs.items():
                pid = (pr.get('CNAM') if female else None) or pr.get('BNAM')
                if pid and slots.get(slot, (None, -1))[1] <= rank:
                    slots[slot] = (pid, rank)
    shapes = []
    for slot, (pid, _rank) in slots.items():
        node = SLOT_NODE.get(slot)
        model = _model_of(db, pid)
        if not node or not model or node not in skel:
            continue
        shapes += part_shapes(db, model, node, skel)
    if not shapes:
        return None
    # the race's build: taller, broader
    if abs(height - 1) > 0.01 or abs(weight - 1) > 0.01:
        shapes = [dict(s, p=[v * (height if k % 3 == 2 else weight) for k, v in enumerate(s['p'])]) for s in shapes]
    return shapes


def _worn(db, subs):
    """The best clothing and armour of each kind the NPC carries (what they would wear)."""
    best = {}
    for t, v in subs:
        if t != 'NPCO' or len(v) < 36:
            continue
        iid = zstr(v[4:36])
        ii = db.resolve_id(iid)
        if ii is None or db.recs[ii][0] not in ('ARMO', 'CLOT'):
            continue
        tag = db.recs[ii][0]
        dd = dict(_subs(db, ii))
        if tag == 'ARMO' and len(dd.get('AODT', b'')) >= 12:
            kind, _w, value = struct.unpack_from('<ifi', dd['AODT'])
        elif tag == 'CLOT' and len(dd.get('CTDT', b'')) >= 12:
            kind, _w, value = struct.unpack_from('<ifh', dd['CTDT'])[:3]
            if kind in (8, 9):                       # rings and amulets don't show
                continue
        else:
            continue
        k = (tag, kind)
        if k not in best or value > best[k][0]:
            best[k] = (value, ii)
    out = {}
    for (tag, _kind), (_v, ii) in best.items():
        out.setdefault(tag, []).append(ii)
    return out
