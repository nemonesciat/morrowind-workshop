"""The ground outdoors: read and write landscape (LAND) heights and ground textures.

Each exterior cell has a 65 x 65 grid of heights (128 units apart) and 16 x 16 ground textures.
Ground textures are numbered per plugin, so when your mod changes a cell's ground it also carries
its own copies of the texture entries (LTEX) that cell uses."""
import math
import struct

import editing
import mapdata
from editing import EditError, commit, _require_project
from esm import iter_subrecords, zstr
from project import join_subs, ref_info, set_ref_pos, unb64, zs

N = 65
CELL = 8192


def _winner(db, gx, gy):
    lst = [v for v in db.by_key.get(('LAND', '%d,%d' % (gx, gy)), []) if v not in db.dead]
    return lst[-1] if lst else None


_cache = None


def _ltex_all(db):
    """(plugin file index, texture index) -> (LTEX id, texture file) for every ground texture."""
    global _cache
    stamp = (len(db.recs), len(db.dead), len(db.project.records) if db.project else 0)
    if _cache is not None and _cache[0] is db.recs and _cache[1] == stamp:
        return _cache[2]
    out = {}
    for (tag, _k), lst in list(db.by_key.items()):
        if tag != 'LTEX':
            continue
        for ri in lst:
            r = db.recs[ri]
            if r is None or ri in db.dead:
                continue
            _ltex_one(db, r, out)
    _cache = (db.recs, stamp, out)
    return out


def _ltex_one(db, r, out):
    _t, _f, data = db.files[r[3]].record_at(r[4])
    idx, tex = None, ''
    for st, sd in iter_subrecords(data):
        if st == 'INTV' and len(sd) >= 4:
            idx = struct.unpack_from('<i', sd)[0]
        elif st == 'DATA':
            tex = zstr(sd)
    if idx is not None and tex:
        out[(r[3], idx)] = (r[1], tex)


def textures(db):
    """Every ground texture you can paint with: [{id, file, path}] (one per texture file)."""
    seen, out = set(), []
    for (_f, _i), (rid, tex) in sorted(_ltex_all(db).items(), key=lambda kv: kv[1][0].lower()):
        k = tex.lower()
        if k in seen:
            continue
        seen.add(k)
        path = db.meshes.texture_path(tex)
        if path:                                    # skip textures whose image files aren't installed
            out.append({'id': rid, 'file': tex, 'path': path})
    return out


def read(db, gx, gy):
    """{'exists', 'h': 65*65 heights, 't': 16*16 ground textures as LTEX ids ('' = default), 'tex': {id: path}}."""
    w = _winner(db, gx, gy)
    if w is None:
        return {'exists': False}
    r = db.recs[w]
    L = mapdata.land(db, gx, gy)
    _t, _f, data = db.files[r[3]].record_at(r[4])
    vtex = None
    for st, sd in iter_subrecords(data):
        if st == 'VTEX' and len(sd) >= 512:
            vtex = struct.unpack_from('<256H', sd)
    grid = [0] * 256
    if vtex:
        n = 0
        for y1 in range(4):
            for x1 in range(4):
                for y2 in range(4):
                    for x2 in range(4):
                        grid[(y1 * 4 + y2) * 16 + x1 * 4 + x2] = vtex[n]
                        n += 1
    allt = _ltex_all(db)
    ids, paths = [], {}
    for v in grid:
        if v == 0:
            ids.append('')
            continue
        ent = allt.get((r[3], v - 1))
        if not ent:
            # no texture of that number in the landscape's own plugin: the game falls back to any
            ent = next((e for (f, i), e in allt.items() if i == v - 1), None)
        ids.append(ent[0] if ent else '')
        if ent:
            paths[ent[0]] = db.meshes.texture_path(ent[1])
    return {'exists': True, 'h': L['h'], 't': ids, 'tex': paths, 'c': L.get('c')}


def _project_ltex(db, ltex_id):
    """This mod's own number for a ground texture, adding a copy of its LTEX entry if needed."""
    p = db.project
    mine = {}
    for k, rec in p.records.items():
        if k.startswith('LTEX|'):
            for st, sd in iter_subrecords(unb64(rec['data'])):
                if st == 'INTV':
                    mine[rec['key']] = struct.unpack_from('<i', sd)[0]
    key = ltex_id.lower()
    if key in mine:
        return mine[key]
    src = next(((rid, tex) for (_f, _i), (rid, tex) in _ltex_all(db).items() if rid.lower() == key), None)
    if not src:
        raise EditError('Unknown ground texture "%s".' % ltex_id)
    idx = max(mine.values(), default=-1) + 1
    p.set_record('LTEX', key, 0, join_subs([('NAME', zs(src[0])), ('INTV', struct.pack('<i', idx)), ('DATA', zs(src[1]))]),
                 created=not db.by_key.get(('LTEX', key)))
    return idx


def _encode_heights(h):
    """VHGT data from 65*65 heights (game units): a float start and byte steps (8 units each)."""
    q = [int(round(v / 8.0)) for v in h]
    # keep each step within what a byte can hold (very steep cliffs are softened a little)
    deltas = bytearray(N * N)
    prev_row = q[0]
    for y in range(N):
        first = q[y * N]
        d = max(-128, min(127, first - prev_row))
        cur = prev_row + d
        q[y * N] = cur
        deltas[y * N] = d & 0xFF
        prev_row = cur
        for x in range(1, N):
            want = q[y * N + x]
            d = max(-128, min(127, want - cur))
            cur += d
            q[y * N + x] = cur
            deltas[y * N + x] = d & 0xFF
    first = q[0]
    deltas[0] = 0
    return struct.pack('<f', float(first)) + bytes(deltas) + b'\0\0\0', [v * 8 for v in q]


def _normals(h):
    out = bytearray(N * N * 3)
    for y in range(N):
        for x in range(N):
            hx = h[y * N + min(x + 1, N - 1)] - h[y * N + max(x - 1, 0)]
            hy = h[min(y + 1, N - 1) * N + x] - h[max(y - 1, 0) * N + x]
            nx, ny, nz = -hx, -hy, 256.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            o = (y * N + x) * 3
            out[o] = int(round(nx / ln * 127)) & 0xFF
            out[o + 1] = int(round(ny / ln * 127)) & 0xFF
            out[o + 2] = int(round(nz / ln * 127)) & 0xFF
    return bytes(out)


def write(db, gx, gy, heights=None, tex=None):
    """Put changed heights (65*65 list) and/or ground textures (16*16 LTEX ids) into the mod."""
    _require_project(db)
    w = _winner(db, gx, gy)
    if w is None:
        raise EditError('There is no landscape at %d, %d.' % (gx, gy))
    r = db.recs[w]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    cur = read(db, gx, gy)
    if heights is None:
        heights = cur['h']
    if len(heights) != N * N:
        raise EditError('Heights must be a 65 x 65 grid.')
    vhgt, heights = _encode_heights([float(v) for v in heights])
    # ground textures: always rewrite them in this mod's own numbering
    ids = tex if tex is not None else cur['t']
    if len(ids) != 256:
        raise EditError('Ground textures must be a 16 x 16 grid.')
    nums = {}
    grid = []
    for t in ids:
        if not t:
            grid.append(0)
            continue
        if t.lower() not in nums:
            nums[t.lower()] = _project_ltex(db, t) + 1
        grid.append(nums[t.lower()])
    vt, n = [0] * 256, 0
    for y1 in range(4):
        for x1 in range(4):
            for y2 in range(4):
                for x2 in range(4):
                    vt[n] = grid[(y1 * 4 + y2) * 16 + x1 * 4 + x2]
                    n += 1
    vtex = struct.pack('<256H', *vt)
    new = {'VHGT': vhgt, 'VNML': _normals(heights), 'VTEX': vtex}
    out, done = [], set()
    for t, d in subs:
        if t in new:
            out.append((t, new[t]))
            done.add(t)
        elif t == 'DATA':
            out.append((t, struct.pack('<I', (struct.unpack_from('<I', d)[0] if len(d) >= 4 else 0) | 1 | 4)))
        else:
            out.append((t, d))
    for t in ('VNML', 'VHGT', 'VTEX'):
        if t not in done:
            out.append((t, new[t]))
    db.project.set_record('LAND', '%d,%d' % (gx, gy), flags & ~0x20, join_subs(out))
    return heights


def edit(db, cells, keep_objects=True, note=None):
    """cells: [{gx, gy, h?: 65*65, t?: 256}]. Objects standing on the ground move with it."""
    _require_project(db)
    if not cells:
        raise EditError('Nothing to change.')
    moved = 0
    for c in cells:
        gx, gy = int(c['gx']), int(c['gy'])
        before = mapdata.land(db, gx, gy).get('h') if keep_objects and c.get('h') else None
        after = write(db, gx, gy, c.get('h'), c.get('t'))
        if before:
            moved += _follow_ground(db, gx, gy, before, after)
    db.sync_project()
    did = []
    if any(c.get('h') for c in cells):
        did.append('reshaped')
    if any(c.get('t') for c in cells):
        did.append('painted')
    commit(db, note or 'Ground %s in %d cell%s%s' % (' and '.join(did) or 'changed', len(cells), '' if len(cells) == 1 else 's',
                                                    (' (%d objects followed it)' % moved) if moved else ''))
    return {'moved': moved}


def _height_at(h, gx, gy, x, y):
    fx, fy = (x - gx * CELL) / 128.0, (y - gy * CELL) / 128.0
    x0, y0 = max(0, min(63, int(fx))), max(0, min(63, int(fy)))
    tx, ty = fx - x0, fy - y0
    a, b = h[y0 * N + x0], h[y0 * N + x0 + 1]
    c, d = h[(y0 + 1) * N + x0], h[(y0 + 1) * N + x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def _follow_ground(db, gx, gy, before, after):
    """Move things that stood on the ground by as much as the ground under them moved."""
    key = '#%d,%d' % (gx, gy)
    m = mapdata.cellmap(db, key)
    if not m.get('exists'):
        return 0
    moved = 0
    c = None
    for r in m['refs']:
        x, y = r['p'][0], r['p'][1]
        if not (gx * CELL <= x < (gx + 1) * CELL and gy * CELL <= y < (gy + 1) * CELL):
            continue
        b = r.get('b') or [0, 0, 0, 0, 0, 0]
        bottom = r['p'][2] + b[2] * (r['s'] or 1)
        old = _height_at(before, gx, gy, x, y)
        if abs(bottom - old) > 60 and not r.get('arch'):
            continue                                # not standing on the ground
        if r.get('arch') and abs(bottom - old) > 400:
            continue
        if r.get('arch') and max(b[3] - b[0], b[4] - b[1]) * (r['s'] or 1) > 1000:
            continue                                # buildings and walls stay put (rocks and trees follow)
        dz = _height_at(after, gx, gy, x, y) - old
        if abs(dz) < 0.5:
            continue
        if c is None:
            c, refs = editing._cell(db, key)
        ref = refs.get(r['k'])
        if not ref:
            continue
        p = list(ref_info(ref['subs'])[1])
        p[2] += dz
        editing._store(c, r['k'], ref['origin'], ref['idx'], set_ref_pos(ref['subs'], tuple(p)))
        moved += 1
    return moved
