"""Data for the World map: objects in a cell and terrain heights."""
import base64
import math
import re
import struct
import zlib

from esm import iter_subrecords, zstr
from project import ref_info

CELL_SIZE = 8192
# False in the survey process (surveyworker.py): the surveys read a place's refs and never its lighting
# or path grid, and reading those parsed every cell's header a second time (a fifth of the builder's
# room-shape survey over 6,000 places)
EXTRAS = True


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
    # own: the place itself was made by your mod (no other plugin has it)
    own = db.proj_pidx is not None and all(db.recs[v][3] == db.proj_pidx for v in lst)
    return {'i': w, 'key': cell_key, 'id': r[1], 'name': name, 'interior': interior,
            'gx': gx, 'gy': gy, 'region': region, 'has_water': bool(flags & 2), 'own': own,
            # (an interior that behaves like outdoors, Mournhold's districts: its buildings are buildings, frombuilding.py)
            'like_exterior': interior and bool(flags & 0x80)}


def _land_only(db, cell_key):
    """An outdoor cell with land but no cell record (a land-only mod's sea floor, maybe shaped into an island), as
    cell_info has it: unnamed, in its land's region. Putting something there or naming it makes the cell
    (editing._cell). None where there is no land either."""
    m = re.match(r'#(-?\d+),(-?\d+)$', cell_key or '')
    if not m:
        return None
    import landrange
    import landscape
    gx, gy = int(m.group(1)), int(m.group(2))
    if landscape._winner(db, gx, gy) is None:
        return None
    region = landrange._region_of(db, gx, gy)
    ri = db.resolve_id(region) if region else None
    return {'i': None, 'key': cell_key, 'id': 'Wilderness (%d, %d)' % (gx, gy), 'name': '', 'interior': False, 'gx': gx, 'gy': gy,
            'region': db.recs[ri][1] if ri is not None else region, 'has_water': True, 'own': False, 'like_exterior': False,
            'no_cell': True}


def cellmap(db, cell_key, original=False):
    """A place's objects for the map and the 3D view (original: without the mod being made)."""
    info = cell_info(db, cell_key) or _land_only(db, cell_key)
    if not info:
        return {'exists': False, 'key': cell_key, 'refs': []}
    refs, _hdr = db.cell_refs(cell_key, without_project=original)
    out, gone = [], []
    type_cache = {}
    mine_plugin = db.project.plugin.lower() if getattr(db, 'project', None) else None
    for rk, ref in refs.items():
        rid, pos, scale, deleted = ref_info(ref['subs'])
        if deleted:
            # taken out by your mod: still shown faintly on the map, to bring back if you like
            if ref['pidx'] == db.proj_pidx:
                ti = db.resolve_id(rid)
                gone.append({'k': rk, 'id': rid, 'name': db.recs[ti][2] if ti is not None else '',
                             'type': db.recs[ti][0] if ti is not None else '',
                             'p': [round(v, 2) if n < 3 else round(v, 5) for n, v in enumerate(pos)]})
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
                    'new': ref['pidx'] == db.proj_pidx and ref['origin'] == mine_plugin,
                    'src': db.plugins[ref['pidx']]['name']})
    info['exists'] = True
    info['refs'] = out
    info['gone'] = gone
    # (a Dwemer ruin the Workshop made: how, so the map's menu can make it again; dwemer.py)
    pc = db.project.cells.get(cell_key) if getattr(db, 'project', None) else None
    if pc and pc.get('ruin'):
        info['ruin'] = pc['ruin']
    if not EXTRAS:
        info['paths'] = None
        info['lighting'] = None
    elif info['interior']:
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
               'ruin': 'Ruin', 'v': 'Velothi', 'velothismall': 'Velothi', 'velothilarge': 'Velothi', 'veloth': 'Velothi',
               'dae': 'Daedric', 'mh': 'Mournhold', 'om': 'Mournhold', 'impsmall': 'Imperial', 'dwe': 'Dwemer',
               'stronghold': 'Stronghold', 'mold': 'Cave', 'mud': 'Cave', 'lava': 'Cave', 'py': 'Cave',
               'moldcave': 'Cave', 'mudcave': 'Cave', 'lavacave': 'Cave', 'pycave': 'Cave', 'sethla': 'Hlaalu',
               'setred': 'Redoran', 'settel': 'Telvanni', 'setveloth': 'Velothi', 'setind': 'Indoril', 'setdres': 'Dres',
               'setmh': 'Mournhold', 'setom': 'Mournhold', 'setnecrom': 'Dunmer', 'setgc': 'Imperial', 'setmw': 'Imperial',
               'setanv': 'Imperial', 'setstr': 'Imperial', 'setkvaurb': 'Imperial', 'setreach': 'Reach'}
# the original game's Redoran and Telvanni pieces are just in_r_... and in_t_...
STYLE_FIRST = {'r': 'Redoran', 't': 'Telvanni'}


def style_of(rid):
    """The building style a piece's ID names (in_hlaalu_..., in_r_s_int_..., T_De_SetInd_I_...), or None."""
    parts = rid.lower().split('_')
    if parts[0] in ('in', 'ex') and len(parts) > 2 and parts[1] in STYLE_FIRST:
        return STYLE_FIRST[parts[1]]
    # Tamriel Data's set name (t_de_setind_...) says more than "de" does
    if parts[0] == 't' and len(parts) > 2 and STYLE_WORDS.get(parts[2]):
        return STYLE_WORDS[parts[2]]
    # otherwise the style word comes early in the name (in_hlaalu_..., ex_de_..., T_Imp_...)
    for w in parts[:4]:
        if w in STYLE_WORDS:
            return STYLE_WORDS[w]
    return None


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
        label = style_of(a)
        if label:
            votes[label] = votes.get(label, 0) + 1
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
    if m.get('interior'):
        # the style's patch pieces (loose walls, door frames, posts, columns) for fixing gaps by hand
        try:
            import fixit
            patch = fixit.patch_pieces(db, cell_key, limit)
            if patch:
                groups.insert(0, {'name': 'Fix-it pieces', 'items': patch, 'fixit': True})
        except Exception as e:
            print('fix-it pieces:', e)
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
    # (the user: "Furniture divided into three sections of their own: Furniture, Wall, and Floor")
    # (and "a tab for plants or gardening ... to contain planters and the decoration that goes in them":
    # planters, pots, the plants and flowers that stand in them, whatever record kind they are)
    groups = {'Furniture': [], 'Wall hangings': [], 'Rugs & mats': [], 'Plants & gardening': [], 'Containers': [], 'Lights': [],
              'Clutter & items': [], 'People & creatures': []}
    for oid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        ri = db.resolve_id(oid)
        if ri is None:
            continue
        r = db.recs[ri]
        b = object_bounds(db, ri)
        if is_architecture(r[0], r[1], b):
            continue
        if r[0] in ('STAT', 'ACTI', 'CONT', 'MISC', 'INGR') and _PLANT_RE.search(r[1]):
            g = 'Plants & gardening'
        elif r[0] in ('STAT', 'ACTI', 'DOOR'):
            g = _palette_kind(r[1], b)
        elif r[0] == 'CONT':
            g = 'Containers'
        elif r[0] == 'LIGH':
            g = 'Lights'
        elif r[0] in ITEM_TYPES:
            g = 'Clutter & items'
        elif r[0] in ('NPC_', 'CREA', 'LEVC'):
            # (only people the game itself stands in more than one place: guards, Ordinators, the stock
            # fighters and merchants of a set; a named person stood once in the game would be a duplicate
            # here. The user: "might be undesired to place duplicate NPCs in a new interior")
            if r[0] == 'NPC_':
                cells_with = {db.recs[ci][7] for ci in db.used_in.get(oid, ()) if db.recs[ci][0] == 'CELL'}
                if len(cells_with) < 2 and not re.search(r'guard|ordinator|templar|legion|soldier|watch', oid):
                    continue
            g = 'People & creatures'
        else:
            continue
        if len(groups[g]) < limit:
            # (mesh: the sidebar folds the records that share a model under the one used most, "20 variants")
            groups[g].append({'id': r[1], 'name': r[2], 'type': r[0], 'here': oid in here, 'mesh': (r[5] or '').lower(),
                              'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])] if b else None})
    db.meshes.save()
    return [{'name': k, 'items': v} for k, v in groups.items() if v]


_WALL_RE = re.compile(r'tapestr|banner|hanger|flag|pennant|curtain|painting|picture|plaque|wallhang|wall_hang|mounted|skull_wall|antler|trophy', re.I)
_FLOOR_RE = re.compile(r'rug|carpet|mat_|_mat\b|floormat|doormat|cushion|pillow', re.I)
# planters and what grows in them: the game's flora_ plants (the harvestable ones are containers), planter boxes
# and beds, potted plants, flowers, shrubs, vines, ferns, trees small enough for a room; not a flour sack or a plate
_PLANT_RE = re.compile(r'(^|_)flora|planter|plant(er|_|s?$|s_)|flower|shrub|bush|fern|vine|ivy|tree_|_tree|garden|'
                       r'herb|moss|mushroom|fungus|lily|rose|hackle|kelp|reed|sapling|topiary|wreath|bouquet', re.I)


def _palette_kind(rid, b):
    """Which palette group a piece of scenery belongs to: 'Wall hangings' (tapestries, banners, hangers,
    paintings), 'Rugs & mats' (rugs, mats, cushions; also anything flat and wide that lies on the floor), else
    'Furniture'."""
    low = rid.lower()
    if _WALL_RE.search(low):
        return 'Wall hangings'
    if _FLOOR_RE.search(low):
        return 'Rugs & mats'
    if b and (b[5] - b[2]) <= 10 and (b[3] - b[0]) >= 60 and (b[4] - b[1]) >= 60 \
            and not re.search(r'lid|door|grate|trap|hatch|plank|board|sign|panel', low):
        return 'Rugs & mats'       # (flat and wide, lying on the floor: a mat with an odd name; not a crate lid or a door)
    return 'Furniture'


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


def land_after(db, key):
    """Plugins that load after your mod in openmw.cfg and have their own ground for this outdoor cell, when your mod
    changes it: started from OpenMW's launcher, the game shows theirs (Play here loads your mod last)."""
    if not db.project or not key.startswith('#') or getattr(db, 'proj_pidx', None) is None:
        return []
    k = ('LAND', key[1:])
    lst = [v for v in db.by_key.get(k, []) if v not in db.dead]
    if not any(db.recs[v][3] == db.proj_pidx for v in lst):
        return []
    order = [c.lower() for c in getattr(db, 'cfg_content_all', [])]
    mine = db.project.plugin.lower()
    if mine not in order:
        return []
    at = order.index(mine)
    out = []
    for v in lst:
        name = db.plugins[db.recs[v][3]]['name']
        if db.recs[v][3] != db.proj_pidx and name.lower() in order and order.index(name.lower()) > at and name not in out:
            out.append(name)
    return out


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
            # (your mod's version of a cell keeps its record number through every edit, the record list updated in
            # place: keyed by its bytes too, or the 2D map showed the ground as first drawn; PIN2, 2026-10-28)
            if db.recs[ri][3] == getattr(db, 'proj_pidx', None):
                ri = (ri, zlib.crc32(db.files[db.recs[ri][3]].record_at(db.recs[ri][4])[2]))
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
    # (a land with textures but no heights, as Morrowind.esm's and Distant Seafloor's round Roth Roryn: the game lays
    # it flat at -2048, its default; shown and shaped that way here too, where it had been left out, sea with no floor)
    flat = heights is None and len(data) > 0
    if flat:
        heights = [-2048] * (65 * 65)
    out = {'exists': heights is not None, 'h': heights, 'c': colors}
    if flat:
        out['flat'] = True
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
