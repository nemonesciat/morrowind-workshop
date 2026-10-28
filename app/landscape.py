"""The ground outdoors: read and write landscape (LAND) heights and ground textures.

Each exterior cell has a 65 x 65 grid of heights (128 units apart) and 16 x 16 ground textures.
Ground textures are numbered per plugin, so when your mod changes a cell's ground it also carries
its own copies of the texture entries (LTEX) that cell uses."""
import math
import re
import struct

import editing
import mapdata
from editing import EditError, commit, _require_project
from esm import iter_subrecords, zstr
from project import join_subs, ref_info, set_ref_pos, unb64, zs

N = 65
CELL = 8192
# rocks, trees and plants: the ground's own dressing, which moves with it at any size (buildings and doors don't)
# (the Telvanni coast's menhirs are rock spires, named ex_t_menhir: 114 of 388 held pieces in Sheogorad, 2026-10-26)
NATURAL = re.compile(r'rock|tree|flora|plant|stump|cliff|terrain_|boulder|mushroom|kelp|coral|grass|bush|shrub|_log_?\d|'
                     r'menhir|barnacle|spire|stalag')


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


def _normals(h, around=None):
    """VNML from 65*65 heights. around(x, y): the height just over the cell's edge (x or y -1 or 65), or None;
    with it the border points lean the way the land beyond does, and the light has no seam at the edge."""
    def at(x, y):
        if 0 <= x < N and 0 <= y < N:
            return h[y * N + x]
        v = around(x, y) if around else None
        return h[min(N - 1, max(0, y)) * N + min(N - 1, max(0, x))] if v is None else v
    out = bytearray(N * N * 3)
    for y in range(N):
        for x in range(N):
            if 0 < x < N - 1 and 0 < y < N - 1:
                hx = h[y * N + x + 1] - h[y * N + x - 1]
                hy = h[(y + 1) * N + x] - h[(y - 1) * N + x]
            else:
                hx = at(x + 1, y) - at(x - 1, y)
                hy = at(x, y + 1) - at(x, y - 1)
            nx, ny, nz = -hx, -hy, 256.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            o = (y * N + x) * 3
            out[o] = int(round(nx / ln * 127)) & 0xFF
            out[o + 1] = int(round(ny / ln * 127)) & 0xFF
            out[o + 2] = int(round(nz / ln * 127)) & 0xFF
    return bytes(out)


def _wnam(h):
    """WNAM, the 9 x 9 heights the in-game world map is drawn from (OpenMW draws it from these alone; a
    landscape without them is see-through on the map). Learnt from Morrowind.esm's 1,292 (2026-10-25): each
    of the 81 is the highest point of its ninth of the cell, over 128 above the sea and over 16 below it
    (OpenMW-CS's divisors), rounded down; the closest of the rules tried to what the game has, within one
    step at 45% of its points and 2.5 steps off on average (its own were made from heights changed since)."""
    out = bytearray(81)
    cut = [int(k * N / 9) for k in range(10)]
    for j in range(9):
        for i in range(9):
            top = max(h[y * N + x] for y in range(cut[j], cut[j + 1]) for x in range(cut[i], cut[i + 1]))
            v = math.floor(top / 128.0) if top >= 0 else math.floor(top / 16.0)
            out[j * 9 + i] = max(-128, min(127, v)) & 0xFF
    return bytes(out)


def write(db, gx, gy, heights=None, tex=None, colors=None, around=None):
    """Put changed heights (65*65 list), ground textures (16*16 LTEX ids) and/or vertex colours (65*65*3 bytes)
    into the mod. around(x, y): the heights just beyond the cell's edges, for its normals (_normals)."""
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
    new = {'VHGT': vhgt, 'VNML': _normals(heights, around), 'VTEX': vtex, 'WNAM': _wnam(heights)}
    if colors is not None:
        colors = bytes(colors)
        if len(colors) != N * N * 3:
            raise EditError('Vertex colours must be 65 x 65 RGB.')
        new['VCLR'] = colors
    # always in the game's order, INTV DATA VNML VHGT WNAM VCLR VTEX: OpenMW reads a land's parts in that order and
    # skips one out of place. Built on a record with textures only (Morrowind.esm's or Distant Seafloor's round Roth
    # Roryn), the heights went after the textures: the Workshop showed the edit, the game flat sea floor (PIN2, 2026-10-28)
    have = dict(subs)
    flags_d = have.get('DATA', b'')
    parts = {'INTV': have.get('INTV'), 'DATA': struct.pack('<I', (struct.unpack_from('<I', flags_d)[0] if len(flags_d) >= 4 else 0)
                                                           | 1 | 4 | (2 if 'VCLR' in new or 'VCLR' in have else 0))}
    for t in ('VNML', 'VHGT', 'WNAM', 'VCLR', 'VTEX'):
        parts[t] = new.get(t, have.get(t))
    order = ('INTV', 'DATA', 'VNML', 'VHGT', 'WNAM', 'VCLR', 'VTEX')
    out = [(t, parts[t]) for t in order if parts.get(t) is not None]
    out += [(t, d) for t, d in subs if t not in order]
    db.project.set_record('LAND', '%d,%d' % (gx, gy), flags & ~0x20, join_subs(out))
    return heights


def edit(db, cells, keep_objects=True, note=None, skip=()):
    """cells: [{gx, gy, h?: 65*65, t?: 256, c?: base64 of 65*65 RGB}]. Objects standing on the ground move with it (not those
    in skip, ref keys: a building the ground is fitted to, groundfit.py)."""
    import base64
    _require_project(db)
    if not cells:
        raise EditError('Nothing to change.')
    moved = 0
    new_h = {(int(c['gx']), int(c['gy'])): c['h'] for c in cells if c.get('h')}
    for c in cells:
        gx, gy = int(c['gx']), int(c['gy'])
        before = mapdata.land(db, gx, gy).get('h') if keep_objects and c.get('h') else None
        cols = c.get('c')
        if isinstance(cols, str):
            cols = base64.b64decode(cols)
        after = write(db, gx, gy, c.get('h'), c.get('t'), cols, around=around_of(db, gx, gy, new_h))
        if before:
            moved += _follow_ground(db, gx, gy, before, after, skip)
            _follow_paths(db, gx, gy, before, after)
    db.sync_project()
    did = []
    if any(c.get('h') for c in cells):
        did.append('reshaped')
    if any(c.get('t') for c in cells):
        did.append('painted')
    if any(c.get('c') for c in cells):
        did.append('shaded')
    commit(db, note or 'Ground %s in %d cell%s%s' % (' and '.join(did) or 'changed', len(cells), '' if len(cells) == 1 else 's',
                                                    (' (%d objects followed it)' % moved) if moved else ''))
    return {'moved': moved}


def around_of(db, gx, gy, new_h=None):
    """around(x, y) for _normals: the heights over a cell's edges, from the cells being changed with it
    (new_h: {(gx, gy): heights}) or else the land as it is."""
    memo = {}

    def heights(cx, cy):
        if (cx, cy) in (new_h or {}):
            return new_h[(cx, cy)]
        if (cx, cy) not in memo:
            memo[(cx, cy)] = mapdata.land(db, cx, cy).get('h')
        return memo[(cx, cy)]

    def around(x, y):
        cx, cy = gx, gy
        if x < 0:
            cx, x = gx - 1, x + 64
        elif x > 64:
            cx, x = gx + 1, x - 64
        if y < 0:
            cy, y = gy - 1, y + 64
        elif y > 64:
            cy, y = gy + 1, y - 64
        h = heights(cx, cy)
        return h[y * N + x] if h else None
    return around


def new_land(db, gx, gy, region='', sync=True):
    """Land for an outdoor cell that has none: the game's sea bed (-2048, what OpenMW stands in for a cell with no
    landscape), and the cell itself if no plugin has it (unnamed, in the region given). Nothing committed.
    sync=False: the caller syncs the project once after making many."""
    _require_project(db)
    if _winner(db, gx, gy) is not None:
        return False
    key = '#%d,%d' % (gx, gy)
    if not db.by_key.get(('CELL', key)) and key not in db.project.cells:
        # (as the game's unnamed outdoor cells: NAME empty, DATA flags 2, the region)
        hdr = [('NAME', b'\0'), ('DATA', struct.pack('<iii', 2, gx, gy))]
        if region:
            hdr.append(('RGNN', zs(region)))
        c = db.project.cell(key, hdr, 0)
        c['props'] = True
    h = [-2048.0] * (N * N)
    vhgt, h = _encode_heights(h)
    subs = [('INTV', struct.pack('<ii', gx, gy)), ('DATA', struct.pack('<I', 1 | 4)), ('VNML', _normals(h)),
            ('VHGT', vhgt), ('WNAM', _wnam(h)), ('VTEX', bytes(512))]
    db.project.set_record('LAND', '%d,%d' % (gx, gy), 0, join_subs(subs), created=True)
    if sync:
        db.sync_project()
    return True


def _follow_paths(db, gx, gy, before, after):
    """The cell's walking-path points that stood on the ground move up or down with it."""
    key = '#%d,%d' % (gx, gy)
    lst = [v for v in db.by_key.get(('PGRD', key), []) if v not in db.dead]
    if not lst:
        return 0
    r = db.recs[lst[-1]]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    subs = [(t, bytes(d)) for t, d in iter_subrecords(data)]
    moved = 0
    for n, (t, d) in enumerate(subs):
        if t != 'PGRP':
            continue
        b = bytearray(d)
        for o in range(0, len(b) - 15, 16):
            x, y, z = struct.unpack_from('<iii', b, o)
            wx, wy = gx * CELL + x, gy * CELL + y
            old = _height_at(before, gx, gy, wx, wy)
            if abs(z - old) > 64:
                continue                        # (on a bridge, a roof, a ledge: not on the ground)
            dz = _height_at(after, gx, gy, wx, wy) - old
            if abs(dz) >= 1:
                struct.pack_into('<i', b, o + 8, int(round(z + dz)))
                moved += 1
        subs[n] = (t, bytes(b))
    if moved:
        had = any(db.recs[v][3] != db.proj_pidx for v in lst)
        db.project.set_record('PGRD', key, 0, join_subs(subs), created=not had)
    return moved


def _height_at(h, gx, gy, x, y):
    fx, fy = (x - gx * CELL) / 128.0, (y - gy * CELL) / 128.0
    x0, y0 = max(0, min(63, int(fx))), max(0, min(63, int(fy)))
    tx, ty = fx - x0, fy - y0
    a, b = h[y0 * N + x0], h[y0 * N + x0 + 1]
    c, d = h[(y0 + 1) * N + x0], h[(y0 + 1) * N + x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def _follow_ground(db, gx, gy, before, after, skip=()):
    """Move things that stood on the ground by as much as the ground under them moved."""
    key = '#%d,%d' % (gx, gy)
    m = mapdata.cellmap(db, key)
    if not m.get('exists'):
        return 0
    moved = 0
    c = None
    for r in m['refs']:
        if r['k'] in skip:
            continue
        x, y = r['p'][0], r['p'][1]
        if not (gx * CELL <= x < (gx + 1) * CELL and gy * CELL <= y < (gy + 1) * CELL):
            continue
        b = r.get('b') or [0, 0, 0, 0, 0, 0]
        bottom = r['p'][2] + b[2] * (r['s'] or 1)
        top = r['p'][2] + b[5] * (r['s'] or 1)
        old = _height_at(before, gx, gy, x, y)
        natural = bool(NATURAL.search(r['id'].lower()))
        if not r.get('arch') or natural:
            # (standing on the ground: its bottom at it, or its model through it, as the game sinks its rocks and
            # trees; rocks, trees and plants follow at any size, 2026-10-26)
            if not (bottom - 60 <= old <= top + 30):
                continue
        elif abs(bottom - old) > 400:
            continue
        elif max(b[3] - b[0], b[4] - b[1]) * (r['s'] or 1) > 1000:
            continue                                # buildings and walls stay put (land shaping holds the ground)
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
