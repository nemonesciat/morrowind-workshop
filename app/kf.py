"""Animation files (.kf) read and written whole, and their groups cut out, put back and added.

A .kf is a NiSequenceStreamHelper whose extra data are the text keys and then one NiStringExtraData (a
bone's name) for each NiKeyframeController in its chain, in the same order; each controller has its
NiKeyframeData. The blocks are read in order with their exact sizes (no searching), so anything else in
the file is refused rather than guessed at.

A track keeps its keys as the file has them: their kind (1 linear, 2 quadratic with tangents, 3 TBC with
tension, bias and continuity, 4 for rotations as three float tracks about X, Y and Z) and each key's extra
numbers, so a file read and written again is the same to the byte. Keys put in a track take its kind:
TBC keys with tension, bias and continuity 0; quadratic keys with tangents from their neighbours."""
import math
import struct

HEADER = b'NetImmerse File Format, Version 4.0.0.2\n'
VERSION = 0x04000002


class KfError(ValueError):
    pass


# ----- reading ----------------------------------------------------------------------------------------------
def _group(data, p, comps):
    """A key group: (kind, [(t, value, extra)]) and where it ends; value a tuple when comps > 1."""
    n = struct.unpack_from('<I', data, p)[0]
    p += 4
    if not n:
        return (0, []), p
    kind = struct.unpack_from('<I', data, p)[0]
    p += 4
    if kind not in (1, 2, 3, 5):
        raise KfError('Unknown key kind %d.' % kind)
    more = 2 * comps if kind == 2 else 3 if kind == 3 else 0
    out = []
    fmt = '<%df' % (1 + comps + more)
    for _k in range(n):
        v = struct.unpack_from(fmt, data, p)
        p += 4 * len(v)
        out.append((v[0], tuple(v[1:1 + comps]) if comps > 1 else v[1], tuple(v[1 + comps:])))
    return (kind, out), p


def _keyframe_data(data, p):
    tr = {}
    nrot = struct.unpack_from('<I', data, p)[0]
    p += 4
    tr['rk'], tr['rot'], tr['xyz'] = 0, [], None
    if nrot:
        kind = struct.unpack_from('<I', data, p)[0]
        p += 4
        tr['rk'] = kind
        if kind == 4:
            order = struct.unpack_from('<f', data, p)[0]
            p += 4
            axes = []
            for _a in range(3):
                g, p = _group(data, p, 1)
                axes.append(g)
            tr['xyz'] = (order, axes, nrot)
        elif kind in (1, 2, 3, 5):
            more = 3 if kind == 3 else 0
            fmt = '<%df' % (5 + more)
            for _k in range(nrot):
                v = struct.unpack_from(fmt, data, p)
                p += 4 * len(v)
                tr['rot'].append((v[0], tuple(v[1:5]), tuple(v[5:])))
        else:
            raise KfError('Unknown rotation key kind %d.' % kind)
    (tr['pk'], tr['pos']), p = _group(data, p, 3)
    (tr['sk'], tr['scale']), p = _group(data, p, 1)
    return tr, p


def _string(data, p):
    n = struct.unpack_from('<I', data, p)[0]
    if n > 4096:
        raise KfError('A name is too long to be one.')
    return data[p + 4:p + 4 + n], p + 4 + n


def read(data):
    """{'name', 'tk': [(t, text)] as the file has them (one text may hold several lines), 'tk_int', 'tracks':
    [{'bone', 'flags', 'freq', 'phase', 'start', 'stop', 'rk', 'rot', 'xyz', 'pk', 'pos', 'sk', 'scale'}]}."""
    if not data or not data.startswith(HEADER):
        raise KfError("That isn't a Morrowind animation file.")
    p = len(HEADER)
    ver, n = struct.unpack_from('<II', data, p)
    p += 8
    if ver != VERSION:
        raise KfError("That animation file is from another game's version of the format.")
    blocks = []
    for _b in range(n):
        t, p = _string(data, p)
        if t == b'NiSequenceStreamHelper':
            name, p = _string(data, p)
            extra, ctrl = struct.unpack_from('<ii', data, p)
            p += 8
            blocks.append((t, {'name': name, 'extra': extra, 'ctrl': ctrl}))
        elif t == b'NiTextKeyExtraData':
            nxt, unused, cnt = struct.unpack_from('<iII', data, p)
            p += 12
            keys = []
            for _k in range(cnt):
                tm = struct.unpack_from('<f', data, p)[0]
                s, p = _string(data, p + 4)
                keys.append((tm, s.decode('cp1252', 'replace')))
            blocks.append((t, {'next': nxt, 'unused': unused, 'keys': keys}))
        elif t == b'NiStringExtraData':
            nxt, left = struct.unpack_from('<iI', data, p)
            s, p = _string(data, p + 8)
            blocks.append((t, {'next': nxt, 's': s.decode('cp1252', 'replace'), 'left': left}))
        elif t == b'NiKeyframeController':
            nxt, flags, freq, phase, start, stop, target, dref = struct.unpack_from('<iHffffii', data, p)
            p += 30
            blocks.append((t, {'next': nxt, 'flags': flags, 'freq': freq, 'phase': phase, 'start': start, 'stop': stop,
                               'target': target, 'data': dref}))
        elif t == b'NiKeyframeData':
            tr, p = _keyframe_data(data, p)
            blocks.append((t, tr))
        else:
            raise KfError('This animation file holds a %s, which the Workshop does not change.' % t.decode('ascii', 'replace'))
    nroots = struct.unpack_from('<I', data, p)[0]
    if p + 4 + 4 * nroots != len(data):
        raise KfError('This animation file has more in it than the Workshop reads.')
    if not blocks or blocks[0][0] != b'NiSequenceStreamHelper':
        raise KfError('This animation file does not start with its sequence.')
    head = blocks[0][1]
    out = {'name': head['name'], 'tk': [], 'tk_int': 0, 'tracks': []}
    names, e, seen = [], head['extra'], set()
    while 0 <= e < len(blocks) and e not in seen:
        seen.add(e)
        t, b = blocks[e]
        if t == b'NiTextKeyExtraData':
            out['tk'], out['tk_int'] = b['keys'], b['unused']
        elif t == b'NiStringExtraData':
            names.append((b['s'], b['left']))
        e = b['next']
    c, k, seen = head['ctrl'], 0, set()
    while 0 <= c < len(blocks) and c not in seen:
        seen.add(c)
        t, b = blocks[c]
        if t != b'NiKeyframeController':
            raise KfError('This animation file has a controller the Workshop does not change.')
        if not 0 <= b['data'] < len(blocks) or blocks[b['data']][0] != b'NiKeyframeData':
            raise KfError('A track has no keyframes.')
        tr = dict(blocks[b['data']][1])
        tr.update(bone=names[k][0] if k < len(names) else '', left=names[k][1] if k < len(names) else None, flags=b['flags'], freq=b['freq'], phase=b['phase'],
                  start=b['start'], stop=b['stop'])
        out['tracks'].append(tr)
        k += 1
        c = b['next']
    return out


# ----- writing ----------------------------------------------------------------------------------------------
def _pstr(s):
    b = s if isinstance(s, bytes) else s.encode('cp1252', 'replace')
    return struct.pack('<I', len(b)) + b


def _pgroup(kind, keys, comps):
    if not keys:
        return struct.pack('<I', 0)
    out = [struct.pack('<II', len(keys), kind)]
    for t, v, extra in keys:
        vals = (t,) + (tuple(v) if comps > 1 else (v,)) + tuple(extra)
        out.append(struct.pack('<%df' % len(vals), *vals))
    return b''.join(out)


def _pdata(tr):
    out = []
    if tr['rk'] == 4:
        order, axes, nrot = tr['xyz']
        out.append(struct.pack('<IIf', nrot, 4, order))
        for kind, keys in axes:
            out.append(_pgroup(kind, keys, 1))
    elif tr['rot']:
        out.append(struct.pack('<II', len(tr['rot']), tr['rk']))
        for t, q, extra in tr['rot']:
            vals = (t,) + tuple(q) + tuple(extra)
            out.append(struct.pack('<%df' % len(vals), *vals))
    else:
        out.append(struct.pack('<I', 0))
    out.append(_pgroup(tr['pk'], tr['pos'], 3))
    out.append(_pgroup(tr['sk'], tr['scale'], 1))
    return b''.join(out)


def write(k):
    """The file's bytes: the sequence, the text keys, the bones' names, the controllers, then their keyframe
    data in the opposite order (as the game's files have them)."""
    tracks = k['tracks']
    n = len(tracks)
    TK, S0, C0, D0 = 1, 2, 2 + n, 2 + 2 * n
    blocks = [(b'NiSequenceStreamHelper', _pstr(k.get('name') or b'') + struct.pack('<ii', TK, C0 if n else -1))]
    tk = sorted(k['tk'], key=lambda x: x[0])
    body = struct.pack('<iII', S0 if n else -1, k.get('tk_int', 0), len(tk))
    body += b''.join(struct.pack('<f', t) + _pstr(txt) for t, txt in tk)
    blocks.append((b'NiTextKeyExtraData', body))
    for j, tr in enumerate(tracks):
        s = _pstr(tr['bone'])
        # (the bytes after the name's count: some tools wrote 0 there)
        left = tr.get('left')
        blocks.append((b'NiStringExtraData', struct.pack('<iI', S0 + j + 1 if j + 1 < n else -1, len(s) if left is None else left) + s))
    for j, tr in enumerate(tracks):
        blocks.append((b'NiKeyframeController', struct.pack('<iHffffii', C0 + j + 1 if j + 1 < n else -1, tr.get('flags', 12),
                                                           tr.get('freq', 1.0), tr.get('phase', 0.0), tr['start'], tr['stop'], -1,
                                                           D0 + n - 1 - j)))
    for j in range(n - 1, -1, -1):
        blocks.append((b'NiKeyframeData', _pdata(tracks[j])))
    out = [HEADER, struct.pack('<II', VERSION, len(blocks))]
    for t, b in blocks:
        out.append(_pstr(t) + b)
    out.append(struct.pack('<II', 1, 0))
    return b''.join(out)


# ----- sampling ---------------------------------------------------------------------------------------------
def _slerp(a, b, f):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = tuple(-x for x in b), -d
    if d > 0.9995:
        q = tuple(x + (y - x) * f for x, y in zip(a, b))
    else:
        th = math.acos(min(1.0, d))
        s = math.sin(th)
        wa, wb = math.sin((1 - f) * th) / s, math.sin(f * th) / s
        q = tuple(x * wa + y * wb for x, y in zip(a, b))
    m = math.sqrt(sum(x * x for x in q)) or 1.0
    return tuple(x / m for x in q)


def _at(keys, t, mix):
    if not keys:
        return None
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0, _e0), (t1, v1, _e1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return mix(v0, v1, (t - t0) / max(1e-9, t1 - t0))
    return keys[-1][1]


def _lerp(a, b, f):
    if isinstance(a, tuple):
        return tuple(x + (y - x) * f for x, y in zip(a, b))
    return a + (b - a) * f


def euler_q(x, y, z):
    """(w, x, y, z) from rotations about X, then Y, then Z."""
    cx, sx, cy, sy, cz, sz = math.cos(x / 2), math.sin(x / 2), math.cos(y / 2), math.sin(y / 2), math.cos(z / 2), math.sin(z / 2)
    return (cz * cy * cx + sz * sy * sx, cz * cy * sx - sz * sy * cx, cz * sy * cx + sz * cy * sx, sz * cy * cx - cz * sy * sx)


def as_quaternions(tr):
    """A track whose rotation is three XYZ float tracks, turned into quaternion keys (linear) at every time
    one of them has a key; other tracks come back as they are."""
    if tr['rk'] != 4:
        return tr
    _order, axes, _n = tr['xyz']
    xs, ys, zs = [a[1] for a in axes]
    times = sorted({k[0] for k in xs + ys + zs})
    get = lambda keys, t: _at(keys, t, _lerp) if keys else 0.0
    rot = [(t, euler_q(get(xs, t), get(ys, t), get(zs, t)), ()) for t in times]
    return dict(tr, rk=1 if rot else 0, rot=rot, xyz=None)


def sample(tr, t):
    """A track's (rotation (w, x, y, z) or None, position or None, scale or None) at time t."""
    tr = as_quaternions(tr)
    return (_at(tr['rot'], t, _slerp), _at(tr['pos'], t, _lerp), _at(tr['scale'], t, _lerp))


# ----- groups: cut out, put back, added -------------------------------------------------------------------
def _extra(kind, comps, keys, n):
    """The extra numbers a new key needs in a group of this kind: TBC 0, 0, 0; quadratic tangents from its
    neighbours (as a per-segment slope)."""
    if kind == 3:
        return (0.0, 0.0, 0.0)
    if kind == 2:
        a = keys[max(0, n - 1)][1]
        b = keys[min(len(keys) - 1, n + 1)][1]
        if comps > 1:
            d = tuple((y - x) / 2 for x, y in zip(a, b))
            return d + d
        d = (b - a) / 2
        return (d, d)
    return ()


def _fill(kind, comps, keys):
    """Give keys made without their extra numbers (extra None) what their kind needs."""
    return [(t, v, e if e is not None else _extra(kind, comps, keys, n)) for n, (t, v, e) in enumerate(keys)]


def _span_keys(keys, a, b, mix, shift):
    """The keys from a to b (with keys made at a and b when none sits there) moved by shift; extra None on
    the made ones."""
    if not keys:
        return []
    inside = [(t + shift, v, e) for t, v, e in keys if a - 1e-5 <= t <= b + 1e-5]
    if not inside or inside[0][0] - shift > a + 1e-5:
        inside.insert(0, (a + shift, _at(keys, a, mix), None))
    if inside[-1][0] - shift < b - 1e-5:
        inside.append((b + shift, _at(keys, b, mix), None))
    return inside


def _snap(k, t):
    """t moved onto the file's own text key time when it is that time rounded (groups come rounded)."""
    near = min((x for x, _txt in k['tk']), key=lambda x: abs(x - t), default=None)
    return near if near is not None and abs(near - t) < 0.0006 else t


def cut(k, start, stop, to=0.0):
    """The part of an animation from start to stop as an animation of its own, starting at time to: every
    track's keys in that span (an XYZ rotation as quaternions), and the text keys in it."""
    start, stop = _snap(k, start), _snap(k, stop)
    shift = to - start
    out = {'name': k.get('name', b''), 'tk_int': k.get('tk_int', 0), 'tk': [], 'tracks': []}
    for tr in k['tracks']:
        q = as_quaternions(tr)
        nt = dict(q, rot=_span_keys(q['rot'], start, stop, _slerp, shift), pos=_span_keys(q['pos'], start, stop, _lerp, shift),
                  scale=_span_keys(q['scale'], start, stop, _lerp, shift), start=to, stop=to + stop - start)
        nt['rot'] = _fill(nt['rk'], 4, nt['rot'])
        nt['pos'] = _fill(nt['pk'], 3, nt['pos'])
        nt['scale'] = _fill(nt['sk'], 1, nt['scale'])
        out['tracks'].append(nt)
    out['tk'] = [(t + shift, txt) for t, txt in k['tk'] if start - 1e-5 <= t <= stop + 1e-5]
    return out


def length(k):
    """The last time anything happens in an animation."""
    end = max([t for t, _x in k['tk']] + [0.0])
    for tr in k['tracks']:
        q = as_quaternions(tr)
        for part in ('rot', 'pos', 'scale'):
            if q[part]:
                end = max(end, q[part][-1][0])
        end = max(end, tr['stop'])
    return end


def _lines(tk):
    return [(t, x.strip()) for t, txt in tk for x in txt.replace('\r\n', '\n').split('\n') if x.strip()]


def _joined(lines):
    """Text key lines at one time joined into one text, as the game's files have them."""
    by = []
    for t, x in sorted(lines, key=lambda l: l[0]):
        if by and abs(by[-1][0] - t) < 1e-5:
            by[-1] = (by[-1][0], by[-1][1] + '\r\n' + x)
        else:
            by.append((t, x))
    return by


def _dedupe(keys):
    out = []
    for x in keys:
        if out and abs(out[-1][0] - x[0]) < 1e-5:
            out[-1] = x                                  # (two keys at one time: the later one stays)
        else:
            out.append(x)
    return out


def put(k, start, stop, part, rest=None):
    """An animation with the span from start to stop replaced by part (an animation starting at 0, as cut
    gives one; it may be longer or shorter). Later keys move by the difference, so the groups after it keep
    their timing; a bone the part doesn't move holds its pose through the span. A bone the part moves that
    has no track yet gets one when rest {bone: (rotation, position, scale)} gives its pose elsewhere, else
    it is left out and named in 'missing'. start == stop puts the part in as a new span at that time."""
    if stop > start:
        start, stop = _snap(k, start), _snap(k, stop)
    plen = max([t for t, _x in part['tk']] + [tr['stop'] for tr in part['tracks']] + [0.0])
    delta = plen - (stop - start)
    if abs(delta) < 1e-5:
        delta, plen = 0.0, stop - start             # (as long as before, but for float noise)
    span = stop - start
    theirs = {tr['bone'].lower(): tr for tr in part['tracks']}
    known = {tr['bone'].lower() for tr in k['tracks']}
    end = length(k)
    tracks = list(k['tracks'])
    missing = []
    for tr in part['tracks']:
        b = tr['bone'].lower()
        if b in known:
            continue
        r = (rest or {}).get(b)
        if not r:
            missing.append(tr['bone'])
            continue
        # (a new track: the bone at rest through the rest of the file)
        q, p, s = r
        tracks.append({'bone': tr['bone'], 'flags': 12, 'freq': 1.0, 'phase': 0.0, 'start': 0.0, 'stop': end,
                       'rk': 1, 'rot': [(0.0, tuple(q), ()), (end, tuple(q), ())], 'xyz': None,
                       'pk': 1, 'pos': [(0.0, tuple(p), ()), (end, tuple(p), ())], 'sk': 0, 'scale': []})
    out = dict(k, tracks=[], missing=missing)
    for tr in tracks:
        mine = theirs.get(tr['bone'].lower())
        src = as_quaternions(tr) if mine and (tr['rk'] == 4 or mine['rot']) else tr
        nt = dict(src)
        for key, comps, kk, mix in (('rot', 4, 'rk', _slerp), ('pos', 3, 'pk', _lerp), ('scale', 1, 'sk', _lerp)):
            old = src[key]
            if not old and not (mine and mine[key]):
                continue
            before = [(t, v, e) for t, v, e in old if t < start - 1e-5]
            after = [(t + delta, v, e) for t, v, e in old if t > stop + 1e-5]
            if mine and mine[key]:
                mid = [(t + start, v, None) for t, v, _e in mine[key]]
                # (the bone holds its old pose up to the span, and from the span's end to its next old key
                # moves as it did from the old stop, so neither side of the span changes)
                # (needed only where the part's own first or last pose differs from the old one there)
                differs = lambda x, y: max(abs(p - q) for p, q in zip(x, y)) > 1e-4 if isinstance(x, tuple) else abs(x - y) > 1e-4
                if old and before and before[-1][0] < start - 0.002 and differs(mid[0][1], _at(old, start, mix)):
                    mid.insert(0, (start - 0.001, _at(old, start, mix), None))
                if old and after and after[0][0] > start + plen + 0.002 and span > 0 and differs(mid[-1][1], _at(old, stop, mix)):
                    mid.append((start + plen + 0.001, _at(old, stop, mix), None))
            else:
                # (this bone doesn't move in the part: it holds its pose through the span, stretched to it)
                if span > 0:
                    mid = [(start + (t - start) * plen / span, v, e) for t, v, e in _span_keys(old, start, stop, mix, 0.0)]
                else:
                    v = _at(old, start, mix)
                    mid = [(start, v, None), (start + plen, v, None)]
            if not nt[kk]:
                nt[kk] = 1
            nt[key] = _fill(nt[kk], comps, _dedupe(before + mid + after))
        nt['start'] = min(tr['start'], start)
        nt['stop'] = tr['stop'] + delta if tr['stop'] >= stop - 1e-5 else max(tr['stop'], start + plen)
        out['tracks'].append(nt)
    # text keys: the span's own come from the part; the lines on its old start and stop the part names again go
    inner = [(t + start, x) for t, x in _lines(part['tk'])]
    names = {x.lower() for _t, x in inner}
    lines = []
    for t, x in _lines(k['tk']):
        if start + 1e-5 < t < stop - 1e-5:
            continue
        if (abs(t - start) < 1e-5 or abs(t - stop) < 1e-5) and x.lower() in names and span > 0:
            continue
        lines.append((t if t <= start + 1e-5 else t + delta, x))
    out['tk'] = _joined(lines + inner)
    return out


def append(k, part, gap=0.0667):
    """An animation with part added after its end."""
    at = round(length(k) + gap, 4)
    return put(k, at, at, part)


def remove_group_keys(tk, name):
    """Text keys without a group's own keys (its Start, Stop and loop keys)."""
    import re
    rx = re.compile(r'^\s*%s\s*:\s*(start|stop|loop start|loop stop)\s*$' % re.escape(name), re.I)
    out = []
    for t, txt in tk:
        lines = [x for x in txt.replace('\r\n', '\n').split('\n') if x.strip() and not rx.match(x)]
        if lines:
            out.append((t, '\r\n'.join(lines)))
    return out
