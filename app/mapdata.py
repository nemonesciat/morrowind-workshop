"""Data for the World map: objects in a cell and terrain heights."""
import base64
import math
import struct

from esm import iter_subrecords, zstr
from project import ref_info

CELL_SIZE = 8192


def cell_info(db, cell_key):
    lst = [v for v in db.by_key.get(('CELL', cell_key), []) if v not in db.dead]
    if not lst:
        return None
    w = lst[-1]
    r = db.recs[w]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    name, region, flags, gx, gy = '', '', 0, 0, 0
    for st, sd in iter_subrecords(data):
        if st == 'NAME':
            name = zstr(sd)
        elif st == 'DATA' and len(sd) >= 12:
            flags, gx, gy = struct.unpack_from('<iii', sd)
        elif st == 'RGNN':
            region = zstr(sd)
        elif st in ('FRMR', 'MVRF'):
            break
    interior = bool(flags & 1) and not cell_key.startswith('#')
    return {'i': w, 'key': cell_key, 'id': r[1], 'name': name, 'interior': interior,
            'gx': gx, 'gy': gy, 'region': region, 'has_water': bool(flags & 2)}


def cellmap(db, cell_key):
    info = cell_info(db, cell_key)
    if not info:
        return {'exists': False, 'key': cell_key, 'refs': []}
    refs, _hdr = db.cell_refs(cell_key)
    out = []
    type_cache = {}
    for rk, ref in refs.items():
        rid, pos, scale, deleted = ref_info(ref['subs'])
        if deleted:
            continue
        low = rid.lower()
        if low not in type_cache:
            ti = db.resolve_id(rid)
            type_cache[low] = (db.recs[ti][0], db.recs[ti][2], ti, object_bounds(db, ti)) if ti is not None \
                else ('', '', None, None)
        tag, nm, ti, bnd = type_cache[low]
        to = None
        if tag == 'DOOR':
            import doors
            to = doors.link_of(ref['subs'])
            if to and not to['cell']:
                ti_ = cell_info(db, to['key'])
                gx, gy = to['key'][1:].split(',')
                to['label'] = '%s (%s, %s)' % ((ti_['name'] or ti_['region'] or 'Outdoors') if ti_ else 'Outdoors', gx, gy)
        if tag == 'LIGH':
            import places
            lt = places.light_of(db, rid)
        else:
            lt = None
        out.append({'k': rk, 'id': rid, 'type': tag, 'name': nm, 'ri': ti, 'b': bnd, 'to': to, 'light': lt,
                    'arch': is_architecture(tag, rid, bnd),
                    'p': [round(v, 2) if n < 3 else round(v, 5) for n, v in enumerate(pos)],
                    's': round(scale, 3), 'mine': ref['pidx'] == db.proj_pidx,
                    'src': db.plugins[ref['pidx']]['name']})
    info['exists'] = True
    info['refs'] = out
    if info['interior']:
        import pathgrid
        import places
        info['paths'] = pathgrid.read(db, cell_key)
        try:
            info['lighting'] = places.read(db, cell_key)
        except Exception:
            info['lighting'] = None
    elif cell_key.startswith('#'):
        # outdoor paths are stored from the cell's corner: give them in world positions
        import pathgrid
        pg = pathgrid.read(db, cell_key)
        if pg:
            ox, oy = info['gx'] * 8192, info['gy'] * 8192
            pg['pts'] = [[p[0] + ox, p[1] + oy, p[2]] for p in pg['pts']]
        info['paths'] = pg
    db.meshes.save()
    return info


ACTOR_BOX = [-30, -30, 0, 30, 30, 128]
ITEM_TYPES = {'WEAP', 'ARMO', 'CLOT', 'MISC', 'BOOK', 'ALCH', 'INGR', 'APPA', 'LOCK', 'PROB', 'REPA', 'LIGH'}
# whole name parts (split on "_") that say what style a place is built in
STYLE_WORDS = {'hlaalu': 'Hlaalu', 'hla': 'Hlaalu', 'redoran': 'Redoran', 'red': 'Redoran', 'telvanni': 'Telvanni',
               'tel': 'Telvanni', 'dwrv': 'Dwemer', 'dwemer': 'Dwemer', 'daed': 'Daedric', 'velothi': 'Velothi',
               'imp': 'Imperial', 'nord': 'Nordic', 'nor': 'Nordic', 'ashl': 'Ashlander', 'cave': 'Cave',
               'mine': 'Mine', 'sewer': 'Sewer', 'de': 'Dunmer', 'c': 'Common', 'com': 'Common', 'bre': 'Breton',
               'cyr': 'Cyrodiilic', 'sky': 'Skyrim', 'he': 'High Elf', 'rga': 'Redguard', 'strong': 'Stronghold',
               'ruin': 'Ruin', 'v': 'Velothi'}


def is_architecture(tag, rid, b):
    """Walls, floors, buildings: big static pieces that should not be grabbed by accident."""
    if tag not in ('STAT', 'ACTI') or not b:
        return False
    low = rid.lower()
    if low.startswith(('in_', 'ex_')) or '_in_' in low or '_ex_' in low or '_i_' in low or '_x_' in low:
        return True
    return (b[3] - b[0]) * (b[4] - b[1]) >= 200 * 200


def _rotated_contains(ref, x, y):
    b = ref['b']
    if not b:
        return False
    rz, s = ref['p'][5], ref['s'] or 1.0
    dx, dy = x - ref['p'][0], y - ref['p'][1]
    # undo the object's turn (the game turns objects by -rz around the up axis)
    c, sn = math.cos(rz), math.sin(rz)
    lx, ly = (dx * c - dy * sn) / s, (dx * sn + dy * c) / s
    return b[0] <= lx <= b[3] and b[1] <= ly <= b[4]


def terrain_z(db, x, y):
    gx, gy = math.floor(x / CELL_SIZE), math.floor(y / CELL_SIZE)
    L = land(db, gx, gy)
    if not L.get('exists'):
        return None
    H = L['h']
    fx, fy = (x - gx * CELL_SIZE) / 128.0, (y - gy * CELL_SIZE) / 128.0
    x0, y0 = min(63, int(fx)), min(63, int(fy))
    tx, ty = fx - x0, fy - y0
    a, b = H[y0 * 65 + x0], H[y0 * 65 + x0 + 1]
    c, d = H[(y0 + 1) * 65 + x0], H[(y0 + 1) * 65 + x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def surface_z(db, refs, interior, x, y, new_b=None, scale=1.0, new_type='', cut=None):
    """Height to set a new object down at (x, y): on the floor or ground, or on a
    table/shelf top for small items. Returns the z for the object's origin."""
    base = None if interior else terrain_z(db, x, y)
    floors, tops = [], []
    for r in refs:
        if not r.get('b') or not _rotated_contains(r, x, y):
            continue
        s = r['s'] or 1.0
        bottom, top = r['p'][2] + r['b'][2] * s, r['p'][2] + r['b'][5] * s
        if cut is not None and bottom > cut:
            continue
        if r.get('arch'):
            floors.append(bottom)
        elif r['type'] not in ('NPC_', 'CREA', 'LEVC') and r['type'] not in ITEM_TYPES:
            tops.append(top)
    if interior:
        if floors:
            base = max(floors)
        elif refs:
            near = min(refs, key=lambda r: (r['p'][0] - x) ** 2 + (r['p'][1] - y) ** 2)
            base = near['p'][2] + ((near['b'][2] * (near['s'] or 1)) if near.get('b') else 0)
        else:
            base = 0.0
    if base is None:
        base = 0.0
    small = new_type in ITEM_TYPES or (new_b is not None and (new_b[5] - new_b[2]) * scale < 60)
    surface = base
    if small:
        cand = [t for t in tops if base < t < base + 250]
        if cand:
            surface = max(cand)
    lift = -(new_b[2] * scale) if new_b else 0.0
    return round(surface + lift, 2)


def palette(db, cell_key, limit=24):
    """Objects that typically appear in places like this one, grouped for the sidebar."""
    m = cellmap(db, cell_key)
    if not m.get('exists'):
        return {'style': '', 'groups': []}
    arch_ids = {r['id'].lower() for r in m['refs'] if r.get('arch')}
    here = {r['id'].lower() for r in m['refs']}
    # style label from architecture names
    votes = {}
    for a in arch_ids:
        parts = a.split('_')
        # the style word comes early in the name (in_hlaalu_..., ex_de_..., T_Imp_Set...)
        for w in parts[:4]:
            label = STYLE_WORDS.get(w)
            if label:
                votes[label] = votes.get(label, 0) + 1
                break
    style = max(votes, key=votes.get) if votes else ''
    # find similar cells: ones built from the same pieces
    overlap = {}
    for a in arch_ids:
        for ci in db.used_in.get(a, ()):
            r = db.recs[ci]
            if r[0] == 'CELL' and r[7] != cell_key:
                overlap[r[7]] = overlap.get(r[7], 0) + 1
    similar = sorted(overlap, key=overlap.get, reverse=True)[:30]
    weights = {ck: overlap[ck] for ck in similar}
    weights[cell_key] = len(arch_ids) or 1
    borrowed = None
    if len(similar) < 8 and m.get('interior'):
        # few places are built like this (a style only a mod or two uses): also learn from places
        # of the same culture, counted for less than the truly similar ones
        import furnish
        borrowed = furnish.STYLE_SET.get(style, 'imperial')
        for ck, n in furnish.related_cells(db, borrowed).items():
            if ck not in weights:
                weights[ck] = n * 0.2
    groups = palette_from(db, weights, arch_ids, here, limit)
    return {'style': style, 'similar': len(similar), 'groups': groups,
            'borrowed': furnish.CULTURE_NAMES.get(borrowed) if borrowed else None}


def palette_from(db, weights, skip=(), here=(), limit=24):
    """What stands in these cells (cell key -> weight), most used first, grouped for the sidebar."""
    from database import CELL_REF_RE
    counts = {}
    for ck, weight in weights.items():
        lst = [v for v in db.by_key.get(('CELL', ck), []) if v not in db.dead]
        if not lst:
            continue
        seen = set()
        for v in lst:
            r = db.recs[v]
            _t, _f, data = db.files[r[3]].record_at(r[4])
            for mm in CELL_REF_RE.finditer(data):
                size = struct.unpack('<I', mm.group(1))[0]
                seen.add(zstr(data[mm.end():mm.end() + size]).lower())
        for oid in seen:
            if oid in skip or 'marker' in oid:
                continue
            counts[oid] = counts.get(oid, 0) + weight
    groups = {'Furniture': [], 'Containers': [], 'Lights': [], 'Clutter & items': [], 'People & creatures': []}
    for oid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        ri = db.resolve_id(oid)
        if ri is None:
            continue
        r = db.recs[ri]
        b = object_bounds(db, ri)
        if is_architecture(r[0], r[1], b):
            continue
        if r[0] in ('STAT', 'ACTI', 'DOOR'):
            g = 'Furniture'
        elif r[0] == 'CONT':
            g = 'Containers'
        elif r[0] == 'LIGH':
            g = 'Lights'
        elif r[0] in ITEM_TYPES:
            g = 'Clutter & items'
        elif r[0] in ('NPC_', 'CREA', 'LEVC'):
            g = 'People & creatures'
        else:
            continue
        if len(groups[g]) < limit:
            groups[g].append({'id': r[1], 'name': r[2], 'type': r[0], 'here': oid in here,
                              'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])] if b else None})
    db.meshes.save()
    return [{'name': k, 'items': v} for k, v in groups.items() if v]


def object_bounds(db, ri):
    """Bounding box [xmin, ymin, zmin, xmax, ymax, zmax] of an object's model, or None."""
    if ri is None:
        return None
    r = db.recs[ri]
    if r[0] in ('NPC_', 'LEVC'):
        return ACTOR_BOX
    if r[0] == 'LEVI':
        return None
    return db.meshes.bounds(r[5]) or (ACTOR_BOX if r[0] == 'CREA' else None)


_LITE = {}          # land record index -> (heights, vertex colours), for the zoomed-out map


def lands_overview(db, x0, y0, x1, y1, step):
    """Ground of many cells at once for the 2D map, every step-th point (1, 2, 4 or 8):
    {"gx,gy": {"n": points per side, "h": heights, "c": base64 colours, "name": place name}}."""
    step = step if step in (1, 2, 4, 8) else 1
    idx = list(range(0, 65, step))
    n = len(idx)
    if getattr(db, '_lite_recs', None) is not db.recs:
        _LITE.clear()
        db._lite_recs = db.recs
    out = {}
    for gy in range(y0, y1 + 1):
        for gx in range(x0, x1 + 1):
            lst = [v for v in db.by_key.get(('LAND', '%d,%d' % (gx, gy)), []) if v not in db.dead]
            if not lst:
                continue
            ri = lst[-1]
            full = _LITE.get(ri)
            if full is None:
                L = land(db, gx, gy)
                if not L.get('exists'):
                    continue
                info = cell_info(db, '#%d,%d' % (gx, gy))
                full = _LITE[ri] = (L['h'], base64.b64decode(L['c']) if L.get('c') else None, (info or {}).get('name') or '')
                if len(_LITE) > 3000:
                    _LITE.pop(next(iter(_LITE)))
            H, C, name = full
            h = [H[y * 65 + x] for y in idx for x in idx]
            c = None
            if C:
                c = base64.b64encode(bytes(b for y in idx for x in idx for b in C[(y * 65 + x) * 3:(y * 65 + x) * 3 + 3])).decode('ascii')
            out['%d,%d' % (gx, gy)] = {'n': n, 'h': h, 'c': c, 'name': name}
    return out


def land(db, gx, gy, with_textures=False):
    lst = [v for v in db.by_key.get(('LAND', '%d,%d' % (gx, gy)), []) if v not in db.dead]
    if not lst:
        return {'exists': False}
    r = db.recs[lst[-1]]
    _t, _f, data = db.files[r[3]].record_at(r[4])
    heights, colors, vtex = None, None, None
    for st, sd in iter_subrecords(data):
        if st == 'VHGT' and len(sd) >= 4 + 65 * 65:
            base = struct.unpack_from('<f', sd)[0]
            deltas = struct.unpack_from('<4225b', sd, 4)
            heights = []
            row = base
            for y in range(65):
                row += deltas[y * 65]
                col = row
                heights.append(int(col * 8))
                for x in range(1, 65):
                    col += deltas[y * 65 + x]
                    heights.append(int(col * 8))
        elif st == 'VCLR' and len(sd) >= 65 * 65 * 3:
            colors = base64.b64encode(bytes(sd[:65 * 65 * 3])).decode('ascii')
        elif st == 'VTEX' and len(sd) >= 512:
            vtex = struct.unpack_from('<256H', sd)
    out = {'exists': heights is not None, 'h': heights, 'c': colors}
    if with_textures:
        # 16 x 16 ground textures per cell (stored in 4x4 blocks of 4x4; put them in plain rows)
        raw = vtex or (0,) * 256
        grid = [0] * 256
        n = 0
        for y1 in range(4):
            for x1 in range(4):
                for y2 in range(4):
                    for x2 in range(4):
                        grid[(y1 * 4 + y2) * 16 + x1 * 4 + x2] = raw[n]
                        n += 1
        names = _land_textures(db)
        paths, index, t = [], {}, []
        for v in grid:
            # 0 = the default ground; otherwise a land texture of the plugin this landscape comes from
            name = '_land_default.dds' if v == 0 else names.get((r[3], v - 1)) or names.get(('any', v - 1)) or '_land_default.dds'
            if name not in index:
                index[name] = len(paths)
                paths.append(db.meshes.texture_path(name))
            t.append(index[name])
        out['t'], out['tex'] = t, paths
    return out


_ltex_cache = None


def _land_textures(db):
    """(plugin file, texture index) -> texture file name, for every land texture."""
    global _ltex_cache
    if _ltex_cache is not None and _ltex_cache[0] is db.recs and _ltex_cache[2] == (len(db.recs), len(db.dead)):
        return _ltex_cache[1]
    out = {}
    for ri, r in enumerate(db.recs):
        if r is None or r[0] != 'LTEX' or ri in db.dead:
            continue
        _t, _f, data = db.files[r[3]].record_at(r[4])
        idx, tex = None, ''
        for st, sd in iter_subrecords(data):
            if st == 'INTV' and len(sd) >= 4:
                idx = struct.unpack_from('<i', sd)[0]
            elif st == 'DATA':
                tex = zstr(sd)
        if idx is not None and tex:
            out[(r[3], idx)] = tex
            out[('any', idx)] = out.get(('any', idx)) or tex
    _ltex_cache = (db.recs, out, (len(db.recs), len(db.dead)))
    return out
