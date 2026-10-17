"""Auto-furnish: fill the rooms of an interior with fitting furniture and clutter.

Rooms are found from the place's floor pieces (the same kit measurements the builder uses).
What goes in them comes from similar places in your load order, so a Hlaalu house gets Hlaalu
furniture. Which way each piece of furniture faces is learnt from where it stands in real
interiors (it faces into the room), so beds and shelves end up with their backs to the wall."""
import math
import random
import struct

import editing
import kits
import mapdata
from editing import EditError
from esm import zstr
from project import ref_info, set_ref_pos, split_cell, zs

STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

# what a kind of furniture is called, by words in its ID or name (and the record types it can be)
FAMILIES = {
    'bed': (('bed',), ('STAT', 'ACTI')),
    'table': (('table',), ('STAT', 'ACTI')),
    'chair': (('chair', 'stool'), ('STAT', 'ACTI')),
    'bench': (('bench',), ('STAT', 'ACTI')),
    'bookshelf': (('bookshelf', 'bookcase'), ('STAT', 'ACTI', 'CONT')),
    'shelf': (('shelf',), ('STAT', 'ACTI', 'CONT')),
    'cupboard': (('cupboard', 'closet', 'dresser', 'wardrobe', 'armoire', 'drawers'), ('CONT', 'STAT')),
    'chest': (('chest',), ('CONT',)),
    'crate': (('crate',), ('CONT', 'STAT')),
    'barrel': (('barrel',), ('CONT', 'STAT')),
    'sack': (('sack',), ('CONT', 'STAT')),
    'urn': (('urn', '_pot'), ('CONT', 'STAT')),
    'rug': (('rug', 'carpet'), ('STAT',)),
    'counter': (('counter',), ('STAT', 'ACTI')),
    'shrine': (('shrine', 'altar'), ('ACTI', 'STAT')),
    'dish': (('plate', 'bowl', 'cup', 'goblet', 'mug', 'pitcher', 'tankard', 'flask', 'jug'), ('MISC',)),
    'bottle': (('bottle',), ('MISC', 'ALCH')),
    'book': (('',), ('BOOK',)),
    'food': (('',), ('INGR',)),
    'candle': (('candle',), ('LIGH',)),
}
NOT = {'table': ('tablet',), 'bed': ('bedroll',), 'shelf': ('bookshelf', 'bookcase'), 'chest': ('chestnut',)}

# what goes in a kind of room: (kind of thing, how many, where)
RECIPES = {
    'bedroom': [('rug', 1, 'centre'), ('bed', 1, 'wall'), ('chest', 1, 'wall'), ('cupboard', 1, 'wall'),
                ('table', 1, 'wall'), ('chair', 1, 'by_table'), ('candle', 1, 'on_table'), ('book', 1, 'on_table'),
                ('dish', 1, 'on_table')],
    'living': [('rug', 1, 'centre'), ('table', 1, 'centre'), ('chair', 3, 'by_table'), ('bench', 1, 'wall'),
               ('shelf', 1, 'wall'), ('cupboard', 1, 'wall'), ('urn', 1, 'corner'), ('dish', 3, 'on_table'),
               ('bottle', 2, 'on_table'), ('food', 2, 'on_table')],
    'kitchen': [('table', 1, 'centre'), ('chair', 2, 'by_table'), ('barrel', 2, 'corner'), ('sack', 2, 'wall'),
                ('crate', 1, 'wall'), ('shelf', 1, 'wall'), ('food', 4, 'on_table'), ('dish', 3, 'on_table')],
    'storage': [('crate', 3, 'wall'), ('barrel', 3, 'corner'), ('sack', 3, 'wall'), ('chest', 1, 'wall'),
                ('urn', 2, 'corner')],
    'study': [('rug', 1, 'centre'), ('bookshelf', 2, 'wall'), ('table', 1, 'centre'), ('chair', 1, 'by_table'),
              ('book', 3, 'on_table'), ('candle', 1, 'on_table'), ('cupboard', 1, 'wall')],
    'shop': [('counter', 1, 'centre'), ('shelf', 2, 'wall'), ('chest', 1, 'wall'), ('crate', 2, 'wall'),
             ('barrel', 1, 'corner'), ('bottle', 2, 'on_table'), ('dish', 2, 'on_table')],
    'shrine': [('rug', 1, 'centre'), ('shrine', 1, 'wall'), ('bench', 2, 'wall'), ('urn', 2, 'corner'),
               ('candle', 2, 'on_table')],
    'hall': [('rug', 1, 'centre'), ('bench', 1, 'wall'), ('urn', 2, 'corner')],
    'tavern': [('counter', 1, 'wall'), ('table', 2, 'centre'), ('chair', 5, 'by_table'), ('barrel', 3, 'corner'),
               ('bench', 1, 'wall'), ('bottle', 4, 'on_table'), ('dish', 4, 'on_table'), ('food', 2, 'on_table')],
}
PURPOSE_WORDS = {'bed': 'bedroom', 'sleep': 'bedroom', 'kitchen': 'kitchen', 'cook': 'kitchen', 'pantry': 'kitchen',
                 'store': 'storage', 'cellar': 'storage', 'storage': 'storage', 'study': 'study', 'library': 'study',
                 'office': 'study', 'shop': 'shop', 'store front': 'shop', 'trader': 'shop', 'shrine': 'shrine',
                 'chapel': 'shrine', 'temple': 'shrine', 'hall': 'hall', 'corridor': 'hall', 'tavern': 'tavern',
                 'inn': 'tavern', 'club': 'tavern', 'bar': 'tavern', 'living': 'living', 'main': 'living',
                 'common': 'living', 'dining': 'living', 'parlor': 'living', 'parlour': 'living'}


def purpose_for(name, tiles, w, h):
    low = (name or '').lower()
    for word, p in PURPOSE_WORDS.items():
        if word in low:
            return p
    if min(w, h) == 1:
        return 'hall'
    if tiles <= 4:
        return 'bedroom'
    return 'living'


# ------------------------------------------------------------------ rooms
def rooms(db, cell_key, names=None):
    """The rooms of a place, from its kit floor pieces: [{id, name, purpose, tiles, x_min, ...}]."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('Auto-furnish works in interiors.')
    tiles = {}
    T = None
    for r in m['refs']:
        prefix = kits.kit_prefix(r['id'])
        kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
        if not kp:
            continue
        piece = next((p for p in kp['pieces'] if p['id'].lower() == r['id'].lower()), None)
        if not piece or abs((r['s'] or 1) - 1) > 0.05:
            continue
        T = T or kp['tile']
        if kp['tile'] != T:
            continue
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        pat = kits.rotate(piece['pattern'], q)
        floor = r['p'][2] + piece['zmin']
        tiles[(r['p'][0], r['p'][1], round(floor / 64))] = {'pat': pat, 'x': r['p'][0], 'y': r['p'][1], 'floor': floor}
    if not tiles:
        return {'tile': None, 'rooms': [], 'refs': m['refs']}
    # a place made with "Build from pieces" remembers its rooms
    plan = (db.project.cells.get(cell_key) or {}).get('plan') if db.project else None
    if plan and plan.get('rooms'):
        result = []
        for n, pr in enumerate(plan['rooms']):
            # tiles are [x, y] or, in buildings with more than one floor, [x, y, floor height]
            g = [k for k in tiles if any(abs(k[0] - pt[0]) < 24 and abs(k[1] - pt[1]) < 24 and
                                         (len(pt) < 3 or abs(tiles[k]['floor'] - pt[2]) < 64) for pt in pr['tiles'])]
            if not g:
                continue
            xs = [tiles[k]['x'] for k in g]
            ys = [tiles[k]['y'] for k in g]
            w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
            result.append({'id': n, 'name': pr['name'], 'tiles': len(g), 'w': w, 'h': h,
                           'purpose': purpose_for(pr['name'], len(g), w, h),
                           'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2,
                           'y_max': max(ys) + T / 2, 'floor': min(tiles[k]['floor'] for k in g),
                           '_tiles': [tiles[k] for k in g]})
        return {'tile': T, 'rooms': result, 'refs': m['refs']}
    # otherwise: tiles side by side and open towards each other make one room, unless a door frame
    # stands between them
    frames = [(r['p'][0], r['p'][1]) for r in m['refs'] if 'jamb' in r['id'].lower() or r['type'] == 'DOOR']

    def framed(a, b):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        return any(abs(fx - mx) < 40 and abs(fy - my) < 40 for fx, fy in frames)

    def nb(k, s):
        x, y, lv = k
        for kk in tiles:
            if kk[2] == lv and abs(kk[0] - (x + STEP[s][0] * T)) < 24 and abs(kk[1] - (y + STEP[s][1] * T)) < 24:
                return kk
        return None
    seen, out = set(), []
    for k in sorted(tiles):
        if k in seen:
            continue
        group, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            group.append(c)
            for s in STEP:
                n = nb(c, s)
                if n and n not in seen and tiles[c]['pat'][s] == 'open' and tiles[n]['pat'][OPP[s]] == 'open' \
                        and not framed(c, n):
                    seen.add(n)
                    todo.append(n)
        out.append(group)
    out.sort(key=lambda g: (-len(g), g[0]))
    result = []
    for n, g in enumerate(out):
        xs = [tiles[k]['x'] for k in g]
        ys = [tiles[k]['y'] for k in g]
        w, h = round((max(xs) - min(xs)) / T) + 1, round((max(ys) - min(ys)) / T) + 1
        name = (names or {}).get(n) or 'Room %d' % (n + 1)
        result.append({'id': n, 'name': name, 'tiles': len(g), 'w': w, 'h': h,
                       'purpose': purpose_for(name, len(g), w, h),
                       'x_min': min(xs) - T / 2, 'x_max': max(xs) + T / 2, 'y_min': min(ys) - T / 2, 'y_max': max(ys) + T / 2,
                       'floor': min(tiles[k]['floor'] for k in g), '_tiles': [tiles[k] for k in g]})
    return {'tile': T, 'rooms': result, 'refs': m['refs']}


# ------------------------------------------------------------------ which way things face
_facing = {}


def front_of(db, rid):
    """The direction an object's front points in its own coordinates, learnt from real interiors
    (furniture faces into the room). (x, y) unit vector, or None if it can't be told."""
    low = rid.lower()
    if low in _facing:
        return _facing[low]
    sx = sy = 0.0
    n = 0
    for ci in list(db.used_in.get(low, ()))[:14]:
        r = db.recs[ci]
        if r[0] != 'CELL':
            continue
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
            _hdr, crefs = split_cell(data)
        except Exception:
            continue
        pts, mine = [], []
        for cr in crefs:
            cid, pos, _s, dele = ref_info(cr['subs'])
            if dele:
                continue
            pts.append(pos)
            if cid.lower() == low:
                mine.append(pos)
        for pos in mine[:4]:
            near = [p for p in pts if 30 < math.hypot(p[0] - pos[0], p[1] - pos[1]) < 700 and abs(p[2] - pos[2]) < 300]
            if len(near) < 4:
                continue
            cx = sum(p[0] for p in near) / len(near) - pos[0]
            cy = sum(p[1] for p in near) / len(near) - pos[1]
            d = math.hypot(cx, cy)
            if d < 1:
                continue
            th = pos[5]
            # into the object's own frame (the game turns things clockwise)
            lx, ly = (cx * math.cos(th) - cy * math.sin(th)) / d, (cx * math.sin(th) + cy * math.cos(th)) / d
            sx += lx
            sy += ly
            n += 1
    out = None
    if n >= 2:
        sx, sy = sx / n, sy / n
        if max(abs(sx), abs(sy)) > 0.25:
            out = (1.0 if sx > 0 else -1.0, 0.0) if abs(sx) > abs(sy) else (0.0, 1.0 if sy > 0 else -1.0)
    _facing[low] = out
    return out


_heights = {}


def hang_height(db, rid):
    """How far above the floor an object's bottom usually is in real interiors (wall shelves,
    sconces, banners hang; most things stand on the floor). 0 for things that stand."""
    low = rid.lower()
    if low in _heights:
        return _heights[low]
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    out = 0.0
    if b:
        bounds_of = {}

        def bnd(cid):
            k = cid.lower()
            if k not in bounds_of:
                cri = db.resolve_id(cid)
                bounds_of[k] = (mapdata.object_bounds(db, cri), db.recs[cri][0]) if cri is not None else (None, '')
            return bounds_of[k]
        found = []
        for ci in list(db.used_in.get(low, ()))[:10]:
            r = db.recs[ci]
            if r[0] != 'CELL':
                continue
            try:
                _t, _f, data = db.files[r[3]].record_at(r[4])
                _hdr, crefs = split_cell(data)
            except Exception:
                continue
            all_refs = []
            for cr in crefs:
                cid, pos, sc, dele = ref_info(cr['subs'])
                if not dele:
                    all_refs.append((cid, pos, sc or 1.0))
            for cid, pos, sc in all_refs:
                if cid.lower() != low or len(found) >= 12:
                    continue
                bottom = pos[2] + b[2] * sc
                # the floor under it: the top of the room pieces (architecture) right below it
                floors = []
                resting = False
                for oid, op, osc in all_refs:
                    if abs(op[0] - pos[0]) > 200 or abs(op[1] - pos[1]) > 200:
                        continue
                    ob, otag = bnd(oid)
                    if not ob:
                        continue
                    if not mapdata.is_architecture(otag, oid, ob):
                        # standing on a crate, a barrel or a table here, not hanging on the wall
                        if op is not pos and abs(op[0] - pos[0]) < 60 and abs(op[1] - pos[1]) < 60 and \
                                abs(op[2] + ob[5] * osc - bottom) < 8:
                            resting = True
                        continue
                    fz = op[2] + ob[2] * osc
                    if fz <= bottom + 4 and bottom - fz < 400:
                        floors.append(fz)
                if floors and not resting:
                    found.append(bottom - max(floors))
        if len(found) >= 2:
            found.sort()
            med = found[len(found) // 2]
            _mount[low] = med             # (for things on walls that reach nearly to the floor)
            if med > 40:                  # it hangs: remember how high
                out = med
    _heights[low] = out
    return out


_mount = {}


def mount_height(db, rid):
    """How far above the floor the bottom of an object usually is, even when that is only a little
    (a long tapestry); None if the game doesn't use it in enough places to tell."""
    hang_height(db, rid)
    return _mount.get(rid.lower())


def _turn_to_face(front, direction):
    """Turn (radians, multiple of 90 degrees) so the local front points along the world direction."""
    f = front or (0.0, -1.0)
    best, bd = 0.0, -9
    for q in range(4):
        th = q * math.pi / 2
        wx, wy = f[0] * math.cos(th) + f[1] * math.sin(th), -f[0] * math.sin(th) + f[1] * math.cos(th)
        d = wx * direction[0] + wy * direction[1]
        if d > bd:
            best, bd = th, d
    return best


def _footprint(b, rot, x, y):
    """Axis-aligned box (x0, y0, x1, y1) of a model turned by a multiple of 90 degrees at (x, y)."""
    corners = [(b[0], b[1]), (b[3], b[1]), (b[0], b[4]), (b[3], b[4])]
    c, s = math.cos(rot), math.sin(rot)
    pts = [(x + px * c + py * s, y - px * s + py * c) for px, py in corners]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _overlaps(a, b, pad=4):
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


# ------------------------------------------------------------------ choosing things
CORE_KINDS = ('bed', 'table', 'chair', 'bench', 'chest', 'cupboard', 'shelf')
_related = {}


def related_cells(db, culture, limit=40):
    """Interiors built from pieces of the same culture (e.g. every Dunmer house kit), most built-up first."""
    key = (culture, limit)
    if _related.get('recs') is not db.recs:
        _related.clear()
        _related['recs'] = db.recs
    if key in _related:
        return _related[key]
    counts = {}
    for oid, cells in db.used_in.items():
        if not kits.kit_prefix(oid):
            continue                                  # only building pieces say what a place is
        label = next((mapdata.STYLE_WORDS[w] for w in oid.split('_')[:4] if w in mapdata.STYLE_WORDS), None)
        if not label or STYLE_SET.get(label, 'imperial') != culture:
            continue
        for ci in cells:
            r = db.recs[ci]
            if r is not None and r[0] == 'CELL' and not r[7].startswith('#') and ci not in db.dead:
                counts[r[7]] = counts.get(r[7], 0) + 1
    out = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:limit])
    _related[key] = out
    return out


def _sort_into(fam, groups):
    for g in groups:
        for it in g['items']:
            low = (it['id'] + ' ' + (it['name'] or '')).lower()
            for k, (words, types) in FAMILIES.items():
                if it['type'] not in types:
                    continue
                if not any(w in low for w in words):
                    continue
                if any(w in low for w in NOT.get(k, ())):
                    continue
                if 'marker' in low or 'unique' in low:
                    continue
                if it['id'] not in fam[k]:
                    fam[k].append(it['id'])
                break


def candidates(db, cell_key):
    """Things used in places like this one, sorted into kinds of furniture (most used first).
    When few places are built from the same pieces (a style only a mod or two uses), it also
    learns from other places of the same culture: other Dunmer houses for a Dres one, and plain
    common furniture for a style with no relatives."""
    pal = mapdata.palette(db, cell_key, limit=80)
    fam = {k: [] for k in FAMILIES}
    _sort_into(fam, pal.get('groups', []))
    style = pal.get('style', '')
    have = sum(1 for k in CORE_KINDS if fam[k])
    if pal.get('similar', 0) < 8 or have < 4:
        culture = STYLE_SET.get(style, 'imperial')
        cells = {k: v for k, v in related_cells(db, culture).items() if k != cell_key}
        if cells:
            # (after this place's own things; a long list, so rarer pieces like beds make it in)
            _sort_into(fam, mapdata.palette_from(db, cells, limit=400))
        fam['_borrowed'] = culture
    return fam, style


DECOR_WORDS = ('tapestry', 'banner', 'painting', 'picture', 'portrait', 'sconce', 'weaponrack', 'weapon_rack', 'rack',
               'trophy', 'plaque', 'map', 'mask', 'shield', 'flag', 'herbs', 'hanging', 'wall')
NOT_DECOR = ('door', 'window', 'marker', 'unique', 'gate', 'light_de_lantern', 'chandelier', 'rug', 'carpet', 'curtain',
             'rope', 'web', 'ivy', 'flora', 'railing', 'rail_', 'pole', 'post', 'burial', 'shutter', 'chain', 'beam',
             'pillar', 'column', 'stair', 'ladder', 'cage', 'bone', 'skull', 'blood', 'cobweb', 'moss', 'screen')
# which pieces suit which kind of place, by the start of their IDs
DECOR_SETS = {'dunmer': ('furn_de_', 't_de_', 'light_de_', 'furn_banner', 'furn_tapestry'),
              'imperial': ('furn_com_', 'furn_imp', 't_imp_', 't_com_', 'light_com_', 'furn_c_'),
              'nordic': ('furn_nord', 't_nor_', 't_sky_', 'furn_com_', 'light_com_')}
STYLE_SET = {'Hlaalu': 'dunmer', 'Redoran': 'dunmer', 'Telvanni': 'dunmer', 'Velothi': 'dunmer', 'Dunmer': 'dunmer',
             'Daedric': 'dunmer', 'Common': 'imperial', 'Imperial': 'imperial', 'Breton': 'imperial', 'Cyrodiilic': 'imperial',
             'Nordic': 'nordic', 'Skyrim': 'nordic', 'Ashlander': 'dunmer', 'Redguard': 'imperial',
             'High Elf': 'imperial', 'Stronghold': 'imperial'}
CULTURE_NAMES = {'dunmer': 'other Dunmer places', 'imperial': 'common and Imperial places', 'nordic': 'other Nordic places'}
_decor_global = {}


def wall_decor(db, cell_key):
    """Things that hang on the walls in places like this one (tapestries, banners, paintings, wall
    shelves, sconces, racks), learnt from where the game itself puts them: well up off the floor,
    and flat against a wall. [(id, how high it hangs, kind)] most used first."""
    pal = mapdata.palette(db, cell_key, limit=120)
    out, seen = [], set()
    items = [it for g in pal.get('groups', []) for it in g['items']]
    # and the game's own tapestries, banners, paintings and sconces of the same make, used anywhere
    dset = DECOR_SETS.get(STYLE_SET.get(pal.get('style', ''), ''), ())
    if dset:
        key = (dset, id(db.recs))
        if key not in _decor_global:
            found = []
            for (tag, k), lst in db.by_key.items():
                if tag not in ('STAT', 'LIGH') or not k.startswith(dset) or not any(w in k for w in ('tapestry', 'banner', 'painting', 'sconce')):
                    continue
                if not lst or lst[-1] in db.dead:
                    continue
                n = len(db.used_in.get(k, ()))
                if n >= 3:
                    found.append((n, {'id': db.recs[lst[-1]][1], 'name': db.recs[lst[-1]][2], 'type': tag}))
            found.sort(key=lambda x: -x[0])
            _decor_global[key] = [f[1] for f in found[:40]]
        items += _decor_global[key]
    for it in items:
        if True:
            rid, low = it['id'], (it['id'] + ' ' + (it.get('name') or '')).lower()
            if rid.lower() in seen or it['type'] not in ('STAT', 'ACTI', 'LIGH', 'MISC'):
                continue
            seen.add(rid.lower())
            if any(w in low for w in NOT_DECOR):
                continue
            b = mapdata.object_bounds(db, db.resolve_id(rid))
            if not b:
                continue
            w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
            thin, wide = min(w, d), max(w, d)
            named = any(w_ in low for w_ in DECOR_WORDS)
            flat = thin <= (44 if named else 32) and wide >= 40 and h >= 30     # (a tapestry's rod adds depth)
            if it['type'] == 'LIGH' and 'sconce' not in low and 'wall' not in low:
                continue                       # free-standing candles and lamps are not wall things
            if not (flat or named) or wide > 420 or h > 400:
                continue
            hang = hang_height(db, rid)
            if hang < 50:
                # a long tapestry or banner can reach nearly to the floor: still a wall thing if it's flat
                m = mount_height(db, rid)
                if not (named and flat and m is not None and m >= 0):
                    continue                   # the game keeps it on the floor or a table
                hang = max(4.0, m)
            kind = next((k for k in ('tapestry', 'banner', 'painting', 'sconce', 'rack', 'shelf', 'trophy', 'herbs')
                         if k in low), 'light' if it['type'] == 'LIGH' else 'decor')
            out.append((rid, hang, kind))
    return out


DECOR_PER_PURPOSE = {'storage': 0.15, 'kitchen': 0.25, 'hall': 0.3}       # share of free wall spots used (default 0.4)
DECOR_KINDS = {'shrine': ('banner', 'tapestry', 'sconce'), 'storage': ('rack', 'herbs', 'decor', 'sconce'),
               'kitchen': ('herbs', 'decor', 'sconce', 'tapestry')}


def _decorate(db, room, purpose, T, decor, refs, placed, put, rng):
    """Hang things on the free walls of one room: flat against the wall, facing in, at the height the
    game hangs them, never over a doorway or into furniture that stands that high."""
    if not decor:
        return []
    floor = room['floor']
    # what already stands here, with its height (so a tapestry can hang above a low chest, not a shelf)
    solid = []
    for r in list(refs) + list(placed):
        b = r.get('b')
        if not b or r.get('arch') or r['type'] in ('NPC_', 'CREA'):
            continue
        s = r.get('s') or 1.0
        solid.append((_footprint([v * s for v in b], r['p'][5], r['p'][0], r['p'][1]), r['p'][2] + b[2] * s, r['p'][2] + b[5] * s,
                      r['type'] == 'DOOR'))
    spots = []
    for t in room['_tiles']:
        walls_here = [s for s in STEP if t['pat'][s] == 'wall']
        for s in walls_here:
            off = t['pat']['offset'].get(s, T / 2 - 16) - 3              # the wall's inside face
            spots.append({'x': t['x'] + STEP[s][0] * off, 'y': t['y'] + STEP[s][1] * off, 'in': (-STEP[s][0], -STEP[s][1]),
                          'corner': len(walls_here) >= 2})
    rng.shuffle(spots)
    spots.sort(key=lambda sp: sp['corner'])                              # the middle of a wall first
    want = max(1, int(round(len(spots) * DECOR_PER_PURPOSE.get(purpose, 0.4))))
    kinds = DECOR_KINDS.get(purpose)
    pool = [d for d in decor if not kinds or d[2] in kinds] or decor
    lights = [d for d in pool if d[2] in ('sconce', 'light')]
    others = [d for d in pool if d[2] not in ('sconce', 'light')]
    # a couple of different pieces per room, a sconce or two for light
    plan = []
    if others:
        picks = others[:6]
        rng.shuffle(picks)
        plan += [picks[n % min(2, len(picks))] for n in range(max(1, want - (1 if lights else 0)))]
    if lights:
        plan += [lights[0]] * min(2, max(1, want // 3))
    got = []
    for rid, hang, kind in plan:
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        front = front_of(db, rid)
        z0, z1 = floor + hang, floor + hang + (b[5] - b[2])
        for sp in list(spots):
            rot = _turn_to_face(front, sp['in'])
            box0 = _footprint(b, rot, 0, 0)
            back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sp['in']]
            x, y = sp['x'] + sp['in'][0] * (back + 1), sp['y'] + sp['in'][1] * (back + 1)
            box = _footprint(b, rot, x, y)
            # clear of doors (any height) and of whatever stands as high as it hangs, with a little room around
            pad = (box[0] - 24, box[1] - 24, box[2] + 24, box[3] + 24)
            if any(_overlaps(pad if door else box, fb, 0) and (door or (zb < z1 + 4 and zt > z0 - 4))
                   for fb, zb, zt, door in solid):
                continue
            rec = put(rid, x, y, rot, hang_from=z0)
            if rec is None:
                break
            solid.append((box, z0, z1, False))
            spots.remove(sp)
            # not two things side by side on the same stretch of wall
            spots[:] = [o for o in spots if math.hypot(o['x'] - sp['x'], o['y'] - sp['y']) > T * 0.9 or o['in'] != sp['in']]
            got.append(rid)
            break
    return got


def furnish(db, cell_key, plan=None, seed=None, walls=True, walls_only=False):
    """Fill rooms with furniture. plan: [{'id': room id, 'purpose': ...}] (all rooms, by their
    guessed purpose, if None). Everything goes in as one change. Returns what was placed."""
    editing._require_project(db)
    info = rooms(db, cell_key)
    if not info['rooms']:
        raise EditError('No rooms found here. Auto-furnish works in places built from modular room pieces '
                        '(like the ones "Build from pieces" makes, and most town interiors).')
    T = info['tile']
    fam, style = candidates(db, cell_key)
    decor = wall_decor(db, cell_key) if (walls or walls_only) else []
    rng = random.Random(seed if seed is not None else cell_key)
    wanted = {p['id']: p.get('purpose') for p in (plan or [])}
    # everything already standing here takes up room
    refs = info['refs']
    taken = []
    for r in refs:
        if r.get('b') and not r.get('arch') and r['type'] not in ('LIGH',):
            taken.append(_footprint(r['b'], r['p'][5], r['p'][0], r['p'][1]))
    # keep doorways clear: doors, and room sides that open into other rooms
    for r in refs:
        if r['type'] == 'DOOR':
            taken.append((r['p'][0] - 110, r['p'][1] - 110, r['p'][0] + 110, r['p'][1] + 110))
        # and the landings at both ends of a staircase
        low = r['id'].lower()
        if r['type'] == 'STAT' and ('stair' in low or 'ramp' in low) and info['tile']:
            T = info['tile']
            along_x = abs(math.sin(r['p'][5])) < 0.5          # which way the stairs run, before turning
            prefix = kits.kit_prefix(r['id'])
            si = kits.stairs(db, prefix) if prefix and prefix in kits.kits(db) else None
            sp = next((p for p in si['pieces'] if p['id'].lower() == low), None) if si else None
            if sp:
                along_x = (sp['low'] in 'EW') == along_x
            ax, ay = (T * 1.5, T * 0.5) if along_x else (T * 0.5, T * 1.5)
            taken.append((r['p'][0] - ax, r['p'][1] - ay, r['p'][0] + ax, r['p'][1] + ay))
    surf = [dict(r) for r in refs]           # for finding floor and table heights as things are added
    placed = []
    c, _r = editing._cell(db, cell_key)
    mine = db.project.plugin.lower()

    def put(rid, x, y, rot, on_top=False, hang_from=None):
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri)
        if not b:
            return None
        tag = db.recs[ri][0]
        if hang_from is not None:
            z = hang_from - b[2]                 # hung on the wall at its usual height
        else:
            z = mapdata.surface_z(db, surf, True, x, y, b, 1.0, 'MISC' if on_top else tag, None)
        nk = db.project.new_ref_key()
        editing._store(c, nk, mine, int(nk.rsplit('|', 1)[1]), set_ref_pos([('NAME', zs(rid))], (x, y, z, 0, 0, rot), 1.0))
        rec = {'id': rid, 'p': [x, y, z, 0, 0, rot], 's': 1.0, 'b': b, 'type': tag,
               'arch': False}
        surf.append(rec)
        placed.append(rec)
        return rec

    report = []
    for room in info['rooms']:
        purpose = wanted.get(room['id'], room['purpose']) if plan is not None else room['purpose']
        if plan is not None and room['id'] not in wanted:
            continue
        if not purpose or purpose == 'none' or purpose not in RECIPES:
            continue
        tl = room['_tiles']
        # inside the room (wall spots already stand off the measured wall face)
        inner = (room['x_min'] + 8, room['y_min'] + 8, room['x_max'] - 8, room['y_max'] - 8)
        # open sides of this room (to other rooms, doorways) stay clear
        for t in tl:
            for s, (dx, dy) in STEP.items():
                if t['pat'][s] == 'door' or (t['pat'][s] == 'open' and not any(
                        abs(u['x'] - (t['x'] + dx * T)) < 24 and abs(u['y'] - (t['y'] + dy * T)) < 24 for u in tl)):
                    mx, my = t['x'] + dx * T * 0.45, t['y'] + dy * T * 0.45
                    taken.append((mx - 100, my - 100, mx + 100, my + 100))
        # spots along the walls: (x, y on the wall's inside face, direction into the room, is it a corner)
        slots = []
        for t in tl:
            walls_here = [s for s in STEP if t['pat'][s] == 'wall']
            for s in walls_here:
                off = t['pat']['offset'].get(s, T / 2 - 16) - 14
                wx, wy = t['x'] + STEP[s][0] * off, t['y'] + STEP[s][1] * off
                inward = (-STEP[s][0], -STEP[s][1])
                slots.append({'x': wx, 'y': wy, 'in': inward, 'corner': len(walls_here) >= 2, 'side': s})
        rng.shuffle(slots)
        cx, cy = (room['x_min'] + room['x_max']) / 2, (room['y_min'] + room['y_max']) / 2
        area_k = max(1.0, room['tiles'] / 9.0)
        tables = []
        got = []

        def pick(kind):
            lst = fam.get(kind) or []
            if not lst:
                return None
            return lst[min(len(lst) - 1, int(rng.random() ** 2 * min(4, len(lst))))]

        def fits(box):
            if box[0] < inner[0] or box[1] < inner[1] or box[2] > inner[2] or box[3] > inner[3]:
                return False
            return not any(_overlaps(box, o) for o in taken)

        for kind, count, where in ([] if walls_only else RECIPES[purpose]):
            n = count if where in ('centre', 'on_table') else max(1, int(round(count * area_k)))
            for _ in range(n):
                rid = pick(kind)
                if not rid:
                    break
                ri = db.resolve_id(rid)
                b = mapdata.object_bounds(db, ri)
                if not b:
                    continue
                front = front_of(db, rid)
                done = None
                if where in ('wall', 'corner'):
                    order = sorted(slots, key=lambda s: (not s['corner']) if where == 'corner' else s['corner'])
                    for sl in order:
                        rot = _turn_to_face(front, sl['in'])
                        box0 = _footprint(b, rot, 0, 0)
                        # back against the wall: move out by the part of the box behind the origin
                        depth_back = {(0, 1): -box0[1], (0, -1): box0[3], (1, 0): -box0[0], (-1, 0): box0[2]}[sl['in']]
                        x = sl['x'] + sl['in'][0] * (depth_back + 2)
                        y = sl['y'] + sl['in'][1] * (depth_back + 2)
                        if where == 'corner':          # into the corner along the wall
                            pass
                        box = _footprint(b, rot, x, y)
                        if fits(box):
                            done = (x, y, rot, box)
                            slots.remove(sl)
                            break
                elif where == 'centre':
                    rot = 0.0 if (room['x_max'] - room['x_min']) >= (room['y_max'] - room['y_min']) else math.pi / 2
                    if kind != 'rug':
                        rot = _turn_to_face(front, (0, -1)) if front else rot
                    for dx, dy in ((0, 0), (64, 0), (-64, 0), (0, 64), (0, -64), (128, 128), (-128, -128)):
                        box = _footprint(b, rot, cx + dx, cy + dy)
                        if kind == 'rug':
                            if box[0] >= inner[0] and box[1] >= inner[1] and box[2] <= inner[2] and box[3] <= inner[3]:
                                done = (cx + dx, cy + dy, rot, None)
                                break
                        elif fits(box):
                            done = (cx + dx, cy + dy, rot, box)
                            break
                elif where == 'by_table' and tables:
                    t = tables[len(got) % len(tables)]
                    tb = t['box']
                    sides = [((tb[0] + tb[2]) / 2, tb[3] + 30, (0, -1)), ((tb[0] + tb[2]) / 2, tb[1] - 30, (0, 1)),
                             (tb[2] + 30, (tb[1] + tb[3]) / 2, (-1, 0)), (tb[0] - 30, (tb[1] + tb[3]) / 2, (1, 0))]
                    rng.shuffle(sides)
                    for x, y, face in sides:
                        rot = _turn_to_face(front, face)
                        box = _footprint(b, rot, x + (-face[0]) * 10, y + (-face[1]) * 10)
                        if fits(box):
                            done = (x + (-face[0]) * 10, y + (-face[1]) * 10, rot, box)
                            break
                elif where == 'on_table' and tables:
                    t = rng.choice(tables)
                    tb = t['box']
                    for _try in range(8):
                        x = rng.uniform(tb[0] + 15, tb[2] - 15)
                        y = rng.uniform(tb[1] + 15, tb[3] - 15)
                        box = _footprint(b, 0, x, y)
                        if not any(_overlaps(box, o, 0) for o in t['items']):
                            done = (x, y, rng.uniform(0, 2 * math.pi), None)
                            t['items'].append(box)
                            break
                if not done:
                    continue
                hang = hang_height(db, rid) if where in ('wall', 'corner') else 0.0
                rec = put(rid, done[0], done[1], done[2], on_top=(where == 'on_table'),
                          hang_from=(room['floor'] + hang) if hang > 0 else None)
                if rec is None:
                    continue
                if done[3] is not None:
                    taken.append(done[3])
                got.append(rid)
                if kind in ('table', 'counter'):
                    tables.append({'box': done[3], 'items': []})
        if walls or walls_only:
            got += _decorate(db, room, purpose, T, decor, refs, placed, put, rng)
        report.append({'room': room['name'], 'purpose': purpose, 'placed': len(got)})
    if not placed:
        if walls_only:
            raise EditError('Found no free wall to hang things on, or nothing that hangs on walls in places like this.')
        raise EditError('Could not find fitting furniture for these rooms (nothing similar in the load order?).')
    # walking paths around the new furniture (only where the mod made the paths, or there were none)
    db.sync_project()
    if not any(v not in db.dead and db.recs[v][3] != db.proj_pidx for v in db.by_key.get(('PGRD', cell_key), [])):
        try:
            import pathgrid
            pathgrid.generate(db, cell_key, note=False)
        except EditError:
            pass
    editing.commit(db, 'Auto-furnished %s (%d things in %d rooms)' % (editing.cell_label(db, cell_key), len(placed),
                                                                      len([r for r in report if r['placed']])))
    return {'placed': len(placed), 'rooms': report, 'style': style,
            'borrowed': CULTURE_NAMES.get(fam.get('_borrowed')) if fam.get('_borrowed') else None}
