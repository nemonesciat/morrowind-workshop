"""Groundcover: grass for OpenMW's groundcover system, kept apart from the mod in its own plugin
("<mod> Grass.omwaddon", loaded with groundcover= instead of content=). OpenMW draws groundcover
fast, in great numbers, sways it in the wind and lets you walk through it.

The grass lives in the project (p.grass: cell key -> [[id, x, y, z, rz, scale], ...]), so it is
part of undo like everything else, and is written out as a plain plugin whose cells hold only
new references."""
import math
import os
import random
import struct

import editing
import mapdata
import scatter
from editing import EditError, commit, _require_project
from esm import iter_subrecords, zstr
from project import join_subs, set_ref_pos, split_cell, zs

# ground textures grass never grows on, and ones where it only grows here and there
BARE = ('road', 'cobble', 'path', 'flagstone', 'brick', 'tile', 'pave', 'lava', 'cliff', 'gravel',
        'wood', 'plank', 'floor', 'rubble', 'scree', 'snow', 'ice', 'water', 'beach', 'sand', 'wall')
# a few tufts between the stones, not none
STONY = ('stone', 'rock')
SPARSE = ('dirt', 'soil', 'ash', 'dust', 'clay', 'barren', 'dry', 'shore')
# swampy ground is still fairly green
DAMP = ('mud', 'swamp', 'marsh', 'bog')
MAX_PER_CELL = 9000


def file_name(p):
    return os.path.splitext(p.plugin)[0] + ' Grass.omwaddon'


def file_path(db):
    return os.path.join(os.path.dirname(editing.plugin_path(db)), file_name(db.project))


def count(p):
    return sum(len(v) for v in getattr(p, 'grass', {}).values())


def _key(x, y):
    return '#%d,%d' % (math.floor(x / 8192), math.floor(y / 8192))


def add(db, items, note=True):
    """items: [{id, x, y, z, rz, s}] (z is the object's origin)."""
    _require_project(db)
    p = db.project
    n = 0
    for it in items:
        if db.resolve_id(it['id']) is None:
            continue
        k = _key(it['x'], it['y'])
        lst = p.grass.setdefault(k, [])
        if len(lst) >= MAX_PER_CELL:
            continue
        lst.append([it['id'], round(float(it['x']), 1), round(float(it['y']), 1), round(float(it['z']), 1),
                    round(float(it.get('rz', 0)) % (2 * math.pi), 3), round(float(it.get('s', 1) or 1), 2)])
        n += 1
    if not n:
        raise EditError('Nothing to add (cells hold at most %d tufts each).' % MAX_PER_CELL)
    if note:
        commit(db, 'Painted %d tufts of grass' % n)
    return {'added': n, 'total': count(p)}


def remove(db, circles, note=True):
    """Take away the grass inside any of the circles [[x, y, r], ...] (one brush stroke)."""
    _require_project(db)
    p = db.project
    n = 0
    for k in list(p.grass):
        before = len(p.grass[k])
        p.grass[k] = [g for g in p.grass[k] if all(math.hypot(g[1] - x, g[2] - y) > r for x, y, r in circles)]
        n += before - len(p.grass[k])
        if not p.grass[k]:
            del p.grass[k]
    if note and n:
        commit(db, 'Cleared away %d tufts of grass' % n)
    return {'removed': n, 'total': count(p)}


def clear(db, cells):
    _require_project(db)
    p = db.project
    n = 0
    for k in cells:
        n += len(p.grass.pop(k, []))
    if n:
        commit(db, 'Took the grass out of %d cell%s' % (len(cells), '' if len(cells) == 1 else 's'))
    return {'removed': n, 'total': count(p)}


def _texture_class(name):
    low = (name or '').lower()
    if 'grass' in low and not any(w in low for w in ('road', 'cobble', 'path')):
        return 1.0
    if any(w in low for w in BARE):
        return 0.0
    if any(w in low for w in STONY):
        return 0.12
    if any(w in low for w in DAMP):
        return 0.6
    if any(w in low for w in SPARSE):
        return 0.25
    return 1.0


def fill(db, cells, thickness=5, ids=None, seed=None):
    """Grow grass over whole cells the way it would grow: thick on grassy ground, thin on dirt and
    ash, none on roads, rocks, sand or under water, never on steep slopes or inside buildings,
    rocks and trees. Uses the region's own grasses (or the ids given). Replaces their grass."""
    _require_project(db)
    p = db.project
    rng = random.Random(seed if seed is not None else ','.join(cells))
    # (thickness 5: a tuft every ~150 units; each step a tenth closer or further, as the brush: 10 about three times
    # as thick. It was (11 - t) / 6, 36 times as thick at 10)
    gap = 150 * 0.9 ** (max(1, min(10, int(thickness))) - 5)
    # (never closer than a tuft every 60 units, 18,600 a cell at most, whatever asks: a grow that packs them tighter
    # can stop the whole Workshop, PIN2 2026-10-28)
    gap = max(60.0, gap)
    made, cells_done = 0, 0
    for ck in cells:
        gx, gy = (int(v) for v in ck[1:].split(','))
        land = mapdata.land(db, gx, gy, with_textures=True)
        if not land.get('exists'):
            continue
        sets = scatter.sets(db, ck)
        grass = next((s for s in sets['sets'] if s['key'] == 'grass'), None)
        items = [i for i in (grass['items'] if grass else []) if not ids or i['id'].lower() in {x.lower() for x in ids}]
        if not items:
            continue
        total = sum(i['n'] for i in items)
        # what stands here: no grass inside it
        m = mapdata.cellmap(db, ck)
        boxes = []
        for r in m.get('refs', []):
            b = r.get('b')
            if not b or r['type'] in ('NPC_', 'CREA', 'LEVC', 'LIGH') or r['type'] in mapdata.ITEM_TYPES:
                continue
            s = r['s'] or 1.0
            if (b[5] - b[2]) * s < 40:
                continue
            import furnish
            boxes.append(furnish._footprint([v * s for v in b], r['p'][5], r['p'][0], r['p'][1]))
        tex_names = land.get('tex') or []
        tidx = land.get('t') or []
        out = []
        ox, oy = gx * 8192, gy * 8192
        H = land['h']

        def height(x, y):
            fx, fy = (x - ox) / 128.0, (y - oy) / 128.0
            x0, y0 = min(63, int(fx)), min(63, int(fy))
            tx, ty = fx - x0, fy - y0
            return ((H[y0 * 65 + x0] * (1 - tx) + H[y0 * 65 + x0 + 1] * tx) * (1 - ty) +
                    (H[(y0 + 1) * 65 + x0] * (1 - tx) + H[(y0 + 1) * 65 + x0 + 1] * tx) * ty)
        steps = int(8192 / gap)
        for j in range(steps):
            for i in range(steps):
                x = ox + (i + rng.random()) * gap
                y = oy + (j + rng.random()) * gap
                if x >= ox + 8192 or y >= oy + 8192:
                    continue
                px, py = min(15, int((x - ox) / 512)), min(15, int((y - oy) / 512))
                ti = tidx[py * 16 + px] if len(tidx) == 256 else None
                chance = _texture_class(tex_names[ti] if ti is not None and ti < len(tex_names) else '')
                if chance <= 0 or rng.random() > chance:
                    continue
                z = height(x, y)
                if z < 10:
                    continue                              # under water (or at the waterline)
                slope = abs(height(x + 64, y) - height(x - 64, y)) + abs(height(x, y + 64) - height(x, y - 64))
                if slope > 170:
                    continue                              # too steep
                if any(b[0] - 20 < x < b[2] + 20 and b[1] - 20 < y < b[3] + 20 for b in boxes):
                    continue
                pick = rng.random() * total
                it = items[0]
                for c in items:
                    pick -= c['n']
                    if pick <= 0:
                        it = c
                        break
                s = it['smin'] + rng.random() * max(0.0, it['smax'] - it['smin'])
                out.append([it['id'], round(x, 1), round(y, 1), round(z - it['sink'] * s - it['zmin'] * s, 1),
                            round(rng.random() * 2 * math.pi, 3), round(s, 2)])
                if len(out) >= MAX_PER_CELL:
                    break
        if out:
            p.grass[ck] = out
            made += len(out)
            cells_done += 1
    if not made:
        raise EditError('No grass could grow here: no grassy ground, or nothing grass-like is used in this region.')
    commit(db, 'Grew %d tufts of grass in %d cell%s' % (made, cells_done, '' if cells_done == 1 else 's'))
    return {'made': made, 'cells': cells_done, 'total': count(p)}


def cells_near(db, gx, gy, radius=1):
    """The grass of the cells around (gx, gy), for the 3D view: {cell key: [[id, x, y, z, rz, s]]}."""
    p = db.project
    if not p:
        return {}
    out = {}
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            k = '#%d,%d' % (gx + dx, gy + dy)
            if k in p.grass:
                out[k] = p.grass[k]
    return out


# ------------------------------------------------------------------ the plugin
def _masters(db, ids):
    """The plugins that define these objects, and theirs, in load order: [(name, size)]."""
    need = set()
    for i in ids:
        ri = db.resolve_id(i)
        if ri is not None and db.recs[ri][3] != db.proj_pidx:
            need.add(db.recs[ri][3])
    stack = list(need)
    while stack:
        pi = stack.pop()
        for m in db.plugins[pi]['header'].get('masters', []):
            mi = db.plugin_index(m.lower())
            if mi is not None and mi not in need:
                need.add(mi)
                stack.append(mi)
    out = []
    for i in sorted(need):
        pl = db.plugins[i]
        out.append((pl['name'], pl['size'] or (os.path.getsize(pl['path']) if pl['path'] else 0)))
    return out


def write(db):
    """Write (or remove) the grass plugin next to the mod."""
    p = db.project
    if not p:
        return None
    path = file_path(db)
    if not getattr(p, 'grass', None):
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return None
    ids = {g[0] for lst in p.grass.values() for g in lst}
    masters = _masters(db, ids)
    body, n_rec, idx = [], 0, 1
    for ck in sorted(p.grass):
        gx, gy = (int(v) for v in ck[1:].split(','))
        # the cell header, as the game has it (name, flags, region)
        hdr = None
        for v in db.by_key.get(('CELL', ck), []):
            if v in db.dead or db.recs[v][3] == db.proj_pidx:
                continue
            r = db.recs[v]
            h, _refs = split_cell(db.files[r[3]].record_at(r[4])[2])
            hdr = [(t, bytes(d)) for t, d in h]
        if not hdr:
            hdr = [('NAME', b'\0'), ('DATA', struct.pack('<iii', 2, gx, gy))]
        hdr = [(t, d) for t, d in hdr if t in ('NAME', 'DATA', 'RGNN')]
        refs = []
        for g in p.grass[ck]:
            subs = set_ref_pos([('NAME', zs(g[0]))], (g[1], g[2], g[3], 0, 0, g[4]), g[5] if abs(g[5] - 1) > 0.005 else 1.0)
            refs.append(b'FRMR' + struct.pack('<I', 4) + struct.pack('<I', idx & 0xFFFFFF) + join_subs(subs))
            idx += 1
        data = join_subs(hdr) + b'NAM0' + struct.pack('<II', 4, len(refs)) + b''.join(refs)
        body.append(b'CELL' + struct.pack('<III', len(data), 0, 0) + data)
        n_rec += 1
    hedr = struct.pack('<fI', 1.3, 0) + p.author.encode('cp1252', 'replace')[:31].ljust(32, b'\0') + \
        ('Groundcover for %s' % p.plugin).encode('cp1252', 'replace')[:255].ljust(256, b'\0') + struct.pack('<I', n_rec)
    head = [b'HEDR' + struct.pack('<I', len(hedr)) + hedr]
    for name, size in masters:
        mb = zs(name)
        head.append(b'MAST' + struct.pack('<I', len(mb)) + mb + b'DATA' + struct.pack('<I', 8) + struct.pack('<Q', size))
    head = b''.join(head)
    blob = b'TES3' + struct.pack('<III', len(head), 0, 0) + head + b''.join(body)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, path)
    except OSError:
        return None                                    # in use by a running game: written next time
    return path
