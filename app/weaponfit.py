"""Your own weapon model made to sit in the hand the game's way (weapons-armour-plan.md, stage 3).

The game holds a weapon by its model's origin, and every weapon model of the game lies the same way (measured on
its 820 weapon models, 2026-10-30): along Y, the blade or head running +Y from the grip, flat blades thin in Z, an
axe's bit to +X; the grip a set share of the way along from the end nearest the hand, by type; and a typical
length by type. A model from elsewhere (a sword lying along X, its origin at the tip, ten times too big) is
turned, moved and sized to that: its long axis to Y, its thinnest to Z, the grip end found from where the model is
widest (a blade's guard is near the grip; an axe's or a mace's head is away from it), then put where the game's
own of that type are. Flip, a quarter turn round its length, the grip's place and the size can be set by hand.

A fitted copy is written into the Library's folder (meshes/wslib), the original left as it was. The game ignores
the transform of a model's root node (nif-root-transform), so the copy moves the root's children instead."""
import math
import os
import struct
import time

import nif

# by the WEAP type (WPDT): the grip's share of the length from the hand's end, and the game's median length
# (jweap1, 2026-10-30: the game's own models, their bounds either side of the origin along Y)
GRIP_AT = {0: 0.27, 1: 0.16, 2: 0.21, 3: 0.26, 4: 0.33, 5: 0.50, 6: 0.47, 7: 0.31, 8: 0.34, 9: 0.49, 10: 0.35,
           11: 0.14, 12: 0.94, 13: 0.91}
LENGTH = {0: 38, 1: 67, 2: 112, 3: 42, 4: 64, 5: 104, 6: 112, 7: 44, 8: 61, 9: 84, 10: 50, 11: 21, 12: 62, 13: 21}
# (blades: the widest part, the guard, is near the hand; axes, maces, hammers: the head is away from it)
GUARD_NEAR_HAND = {0, 1, 2, 11}
HEAD_AWAY = {3, 4, 7, 8}
TYPE_NAMES = {0: 'short blade', 1: 'long blade', 2: 'two-handed long blade', 3: 'one-handed blunt weapon',
              4: 'two-handed blunt weapon', 5: 'staff', 6: 'spear', 7: 'one-handed axe', 8: 'two-handed axe', 9: 'bow',
              10: 'crossbow', 11: 'throwing weapon', 12: 'arrow', 13: 'bolt'}
BINS = 24


def _verts(raw):
    """The model's points in its own frame, as the game sees them (root node's transform ignored)."""
    pts = []
    for s in nif.mesh_from_nif(raw) or []:
        p = s['p']
        pts += [(p[k], p[k + 1], p[k + 2]) for k in range(0, len(p) - 2, 3)]
    return pts


def _axes(pts):
    """The model's own axes, longest first: three unit vectors (a principal-axes fit, so a model drawn on a slant
    comes out straight), and the middle."""
    n = float(len(pts))
    c = [sum(p[i] for p in pts) / n for i in range(3)]
    C = [[sum((p[i] - c[i]) * (p[j] - c[j]) for p in pts) / n for j in range(3)] for i in range(3)]
    axes = []
    M = [row[:] for row in C]
    for _k in range(3):
        v = [1.0, 0.7, 0.3]
        for _ in range(60):
            w = [sum(M[i][j] * v[j] for j in range(3)) for i in range(3)]
            for a in axes:                      # (kept square to the axes already found)
                d = sum(w[i] * a[i] for i in range(3))
                w = [w[i] - d * a[i] for i in range(3)]
            L = math.sqrt(sum(x * x for x in w)) or 1.0
            v = [x / L for x in w]
        axes.append(v)
    # (snapped to the model's own X/Y/Z when all three are within a few degrees of them: most models are drawn square)
    if all(max(abs(x) for x in v) > 0.995 for v in axes):
        out = []
        for v in axes:
            k = max(range(3), key=lambda i: abs(v[i]))
            u = [0.0, 0.0, 0.0]
            u[k] = 1.0 if v[k] > 0 else -1.0
            out.append(u)
        axes = out
    return axes, c


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def guess(raw, wtype):
    """The fit the Workshop proposes: {'flip': bool, 'turn': 0, 'grip': share, 'size': scale to the game's length,
    'length': the model's own length, 'game_length'}."""
    pts = _verts(raw)
    if len(pts) < 3:
        raise ValueError('The model has no shape the Workshop can read.')
    (ey, ex_, ez), c = _axes(pts)
    ys = [_dot(p, ey) for p in pts]
    lo, hi = min(ys), max(ys)
    L = (hi - lo) or 1.0
    # the width along the length, in bins: the widest bin tells which end the hand is at
    wide = [0.0] * BINS
    for p, y in zip(pts, ys):
        b = min(BINS - 1, int((y - lo) / L * BINS))
        wide[b] = max(wide[b], abs(_dot(p, ex_) - _dot(c, ex_)), abs(_dot(p, ez) - _dot(c, ez)))
    peak = max(range(BINS), key=lambda b: wide[b])
    near_low = peak < BINS / 2.0
    if wtype in HEAD_AWAY:
        hand_low = not near_low
    elif wtype in GUARD_NEAR_HAND:
        hand_low = near_low
    else:
        hand_low = True
    game_len = LENGTH.get(wtype, 60)
    return {'flip': not hand_low, 'turn': 0, 'grip': GRIP_AT.get(wtype, 0.25), 'size': round(game_len / L, 4),
            'length': round(L, 1), 'game_length': game_len}


def transform(raw, wtype, flip=False, turn=0, grip=None, size=None):
    """(R, t, s): the turn, move and scale that set the model the game's way with these choices (see guess()).
    A point p of the model goes to s * R p + t."""
    pts = _verts(raw)
    (ey, ex_, ez), c = _axes(pts)
    # (square and right-handed: Z kept square to Y, X = Y x Z)
    d = _dot(ez, ey)
    ez = [ez[i] - d * ey[i] for i in range(3)]
    n_ = math.sqrt(_dot(ez, ez)) or 1.0
    ez = [v / n_ for v in ez]
    ex_ = _cross(ey, ez)
    if flip:
        ey = [-v for v in ey]
        ex_ = [-v for v in ex_]
    for _ in range(int(turn) % 4):
        ex_, ez = [-v for v in ez], ex_          # (a quarter turn round the length)
    R = [ex_, ey, ez]                           # (rows: the new X, Y, Z in the model's frame)
    if size is None:
        size = guess(raw, wtype)['size']
    s = float(size)
    q = [[_dot(R[i], p) for i in range(3)] for p in pts]
    ylo, yhi = min(v[1] for v in q), max(v[1] for v in q)
    g = ylo + (yhi - ylo) * (GRIP_AT.get(wtype, 0.25) if grip is None else float(grip))
    # (centred across at the grip: the middle of the points near it)
    near = [v for v in q if abs(v[1] - g) <= (yhi - ylo) * 0.06] or q
    cx = (min(v[0] for v in near) + max(v[0] for v in near)) / 2.0
    cz = (min(v[2] for v in near) + max(v[2] for v in near)) / 2.0
    t = [-s * cx, -s * g, -s * cz]
    return R, t, s


def _av_at(data, p):
    """The offsets of an AV block's translation, rotation and scale, and the values."""
    nlen = struct.unpack_from('<I', data, p)[0]
    q = p + 4 + nlen + 8 + 2
    return q, list(struct.unpack_from('<3f', data, q)), struct.unpack_from('<9f', data, q + 12), struct.unpack_from('<f', data, q + 48)[0]


def apply(raw, R, t, s):
    """A copy of the model with every point p moved to s * R p + t: the root's children re-seated when the root
    is a node (the game ignores a root node's own transform), else the root mesh's own transform."""
    blocks = nif._blocks(raw)
    if not blocks:
        raise ValueError('This model can\'t be rewritten (its file is not one the Workshop can read).')
    new = bytearray(raw)
    typ0, p0 = blocks[0]

    def seat(p):
        q, lt, lr, ls = _av_at(raw, p)
        L = [list(lr[0:3]), list(lr[3:6]), list(lr[6:9])]
        nR = nif._mul(R, L)
        nt = [t[k] + s * v for k, v in enumerate(nif._apply(R, lt))]
        struct.pack_into('<3f', new, q, *nt)
        struct.pack_into('<9f', new, q + 12, *(nR[0] + nR[1] + nR[2]))
        struct.pack_into('<f', new, q + 48, ls * s)

    if typ0 in nif.NODE_TYPES:
        _f, _tr, p = nif._read_av(raw, p0)
        nc = struct.unpack_from('<I', raw, p)[0]
        for k in struct.unpack_from('<%di' % nc, raw, p + 4):
            if 0 <= k < len(blocks) and (blocks[k][0] in nif.NODE_TYPES or blocks[k][0] in nif.GEOM_TYPES):
                seat(blocks[k][1])
    elif typ0 in nif.GEOM_TYPES:
        seat(p0)
    else:
        raise ValueError('This model can\'t be rewritten (its first block is a %s).' % typ0.decode('latin-1'))
    return bytes(new)


def _lib_entry(lib_id):
    import library
    e = next((x for x in library._index() if x.get('id') == lib_id and x.get('type') == 'model'), None)
    if not e:
        raise ValueError('That model is not in the Library.')
    return e


def _raw(db, model):
    raw = db.meshes.read('meshes/' + model.lower().replace('\\', '/'))
    if not raw:
        raise ValueError('Could not read the model %s.' % model)
    return raw


def reference(db, wtype):
    """A plain game weapon of the type to show beside yours: an iron or steel one, else the first."""
    from esm import iter_subrecords, zstr
    best = None
    for ri, r in enumerate(db.recs):
        if r[0] != 'WEAP':
            continue
        try:
            subs = {t: bytes(d) for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2])}
        except Exception:
            continue
        wd = subs.get('WPDT')
        if not wd or struct.unpack_from('<H', wd, 8)[0] != wtype or 'ENAM' in subs or not subs.get('MODL'):
            continue
        low = r[1].lower()
        rank = 0 if low.startswith('iron') else 1 if low.startswith('steel') else 2
        if best is None or rank < best[0]:
            best = (rank, zstr(subs['MODL']), zstr(subs.get('FNAM', b'')) or r[1])
            if rank == 0:
                break
    return (best[1], best[2]) if best else (None, None)


def view(db, lib_id, wtype, flip=None, turn=0, grip=None, size=None):
    """For the Forge's preview: your model fitted with these choices (None: the Workshop's guess) and a game weapon of
    the type, as the 3D preview's shapes ('ghost' on the game's), and the choices."""
    e = _lib_entry(lib_id)
    raw = _raw(db, e['model'])
    g = guess(raw, wtype)
    ch = {'flip': g['flip'] if flip is None else bool(flip), 'turn': int(turn or 0),
          'grip': g['grip'] if grip is None else float(grip), 'size': g['size'] if size is None else float(size)}
    fitted = apply(raw, *transform(raw, wtype, ch['flip'], ch['turn'], ch['grip'], ch['size']))
    shapes = nif.mesh_from_nif(fitted) or []
    for s_ in shapes:
        s_['tex'] = db.meshes.texture_path(s_['tex'])
    ref_model, ref_name = reference(db, wtype)
    if ref_model:
        try:
            for s_ in nif.mesh_from_nif(_raw(db, ref_model)) or []:
                shapes.append(dict(s_, ghost=True, tex=None))
        except Exception:
            pass
    return {'shapes': shapes, 'choices': ch, 'guess': g, 'ref': ref_name, 'type': TYPE_NAMES.get(wtype, 'weapon'),
            'length': round(g['length'] * ch['size'], 1)}


def save(db, lib_id, wtype, flip=None, turn=0, grip=None, size=None):
    """The fitted copy written into the Library ("<name> (fitted)"): its Library id, for the Forge's own model."""
    import library
    e = _lib_entry(lib_id)
    raw = _raw(db, e['model'])
    g = guess(raw, wtype)
    out = apply(raw, *transform(raw, wtype, g['flip'] if flip is None else bool(flip), int(turn or 0),
                                g['grip'] if grip is None else float(grip), g['size'] if size is None else float(size)))
    folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
    os.makedirs(folder, exist_ok=True)
    stem = library._free_name(folder, library._slug(os.path.splitext(os.path.basename(e['model']))[0]) + '_fit', '.nif')
    dest = os.path.join(folder, stem + '.nif')
    with open(dest, 'wb') as f:
        f.write(out)
    library._register(db, 'meshes/%s/%s.nif' % (library.SUB, stem), dest)
    items = library._index()
    entry = dict({k: v for k, v in e.items() if k in ('cat', 'sub', 'icon', 'kind')}, id=stem, name=(e.get('name') or stem) + ' (fitted)',
                 type='model', file='meshes/%s/%s.nif' % (library.SUB, stem), model='%s\\%s.nif' % (library.SUB, stem),
                 added=time.time(), records={}, **{'from': 'fitted to the hand from ' + (e.get('name') or e['model'])})
    items.append(entry)
    library._save_index(items)
    return {'id': stem, 'name': entry['name']}


# ------------------------------------------------------------------ rigid armour: fitted onto the game's own piece
# A worn piece that rides one bone (a helmet, a pauldron, a greave, a bracer, a shield) is drawn in that bone's frame:
# the game's piece for the slot shows where. Yours is laid over it: its axes onto the game piece's axes (longest to
# longest, each the way round its bulk leans), its middle on the game piece's middle, and as big; then turned, flipped
# and sized by hand over the game's piece, faint.

def _moments(pts, axes, c):
    """Per axis: the spread and the lean (third moment: which way the bulk leans)."""
    out = []
    for a in axes:
        ds = [_dot([p[i] - c[i] for i in range(3)], a) for p in pts]
        n = float(len(ds)) or 1.0
        sd = math.sqrt(sum(d * d for d in ds) / n) or 1.0
        out.append((sd, sum(d ** 3 for d in ds) / n / sd ** 3))
    return out


def _spread(pts):
    n = float(len(pts))
    c = [sum(p[i] for p in pts) / n for i in range(3)]
    return math.sqrt(sum(sum((p[i] - c[i]) ** 2 for i in range(3)) for p in pts) / n)


def _sample(pts, n=180):
    step = max(1, len(pts) // n)
    return pts[::step][:n]


def _det(M):
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
            + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))


def _best_turn(P, Q):
    """The turn taking yours onto the target: each of the 24 ways of laying your own axes on the target's (every
    order, every way round, never a mirror), each scaled and centred, and the one whose points lie nearest the
    target's both ways (a chamfer distance on samples) kept. The spreads and leans alone left a third of the
    game's own pieces, scrambled, the wrong way round (lab jarm1, 2026-10-30)."""
    import itertools
    aP, cP = _axes(P)
    aQ, cQ = _axes(Q)
    sP, sQ = _sample(P), _sample(Q)
    k_ = _spread(Q) / max(1e-6, _spread(P))
    Qc = [[q[i] - cQ[i] for i in range(3)] for q in sQ]
    best, best_d = None, None
    for perm in itertools.permutations(range(3)):
        for sg in itertools.product((1.0, -1.0), repeat=3):
            rows = [[sg[k] * v for v in aP[perm[k]]] for k in range(3)]
            M = [[sum(aQ[k][i] * rows[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
            if _det(M) < 0:
                continue
            A = [[k_ * v for v in nif._apply(M, [p[i] - cP[i] for i in range(3)])] for p in sP]
            d = sum(min((a[0] - q[0]) ** 2 + (a[1] - q[1]) ** 2 + (a[2] - q[2]) ** 2 for q in Qc) for a in A) / len(A) +                 sum(min((a[0] - q[0]) ** 2 + (a[1] - q[1]) ** 2 + (a[2] - q[2]) ** 2 for a in A) for q in Qc) / len(Qc)
            if best_d is None or d < best_d:
                best, best_d = M, d
    return best


def _box(pts):
    return [min(p[i] for p in pts) for i in range(3)] + [max(p[i] for p in pts) for i in range(3)]


def onto(raw, target, turn=0, flip=False, size=1.0):
    """(R, t, s) laying the model raw over the model target (see above). turn: quarter turns round the target's
    up (Z); flip: end over end round its X; size: times the matched size."""
    P, Q = _verts(raw), _verts(target)
    if len(P) < 3 or len(Q) < 3:
        raise ValueError('A model has no shape the Workshop can read.')
    M = _best_turn(P, Q)
    # the hand's choices, round the target's own frame
    extra = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    for _ in range(int(turn) % 4):
        extra = nif._mul([[0, -1, 0], [1, 0, 0], [0, 0, 1]], extra)
    if flip:
        extra = nif._mul([[1, 0, 0], [0, -1, 0], [0, 0, -1]], extra)
    R = nif._mul(extra, M)
    # as big: the spread round the middle, on average
    s = _spread(Q) / max(1e-6, _spread(P)) * float(size or 1.0)
    # middles together: the boxes' middles
    q = [[s * v for v in nif._apply(R, p)] for p in P]
    bq, bt = _box(q), _box(Q)
    t = [(bt[i] + bt[i + 3]) / 2.0 - (bq[i] + bq[i + 3]) / 2.0 for i in range(3)]
    return R, t, s


def worn_view(db, lib_id, target_model, turn=0, flip=False, size=1.0):
    """For the Forge: your model laid over the game's worn piece (target_model, a BODY part's model), both as shapes."""
    e = _lib_entry(lib_id)
    raw, tgt = _raw(db, e['model']), _raw(db, target_model)
    fitted = apply(raw, *onto(raw, tgt, turn, flip, size))
    shapes = nif.mesh_from_nif(fitted) or []
    for s_ in shapes:
        s_['tex'] = db.meshes.texture_path(s_['tex'])
    for s_ in nif.mesh_from_nif(tgt) or []:
        shapes.append(dict(s_, ghost=True, tex=None))
    return {'shapes': shapes, 'choices': {'turn': int(turn or 0), 'flip': bool(flip), 'size': float(size or 1.0)}}


def worn_save(db, lib_id, target_model, turn=0, flip=False, size=1.0):
    """The copy laid over the game's worn piece, into the Library: its id."""
    e = _lib_entry(lib_id)
    raw, tgt = _raw(db, e['model']), _raw(db, target_model)
    return _save_copy(db, e, apply(raw, *onto(raw, tgt, turn, flip, size)), '_worn', ' (fitted on)')


def _save_copy(db, e, out, suffix, label):
    import library
    folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
    os.makedirs(folder, exist_ok=True)
    stem = library._free_name(folder, library._slug(os.path.splitext(os.path.basename(e['model']))[0]) + suffix, '.nif')
    dest = os.path.join(folder, stem + '.nif')
    with open(dest, 'wb') as f:
        f.write(out)
    library._register(db, 'meshes/%s/%s.nif' % (library.SUB, stem), dest)
    items = library._index()
    entry = dict({k: v for k, v in e.items() if k in ('cat', 'sub', 'icon', 'kind')}, id=stem, name=(e.get('name') or stem) + label,
                 type='model', file='meshes/%s/%s.nif' % (library.SUB, stem), model='%s\\%s.nif' % (library.SUB, stem),
                 added=time.time(), records={}, **{'from': label.strip(' ()') + ' from ' + (e.get('name') or e['model'])})
    items.append(entry)
    library._save_index(items)
    return {'id': stem, 'name': entry['name']}
