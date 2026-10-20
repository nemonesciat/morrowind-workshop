"""Outside buildings for new interiors, copied from the game's own towns.

A house in Morrowind is usually several exterior pieces fitted together (walls, roof, stairs,
awnings) with a load door in one of them. For every house whose door leads into an interior of a
style, the pieces that make up that house are collected with their exact places relative to the
door, so a new building can be put up as a whole, door and all, exactly as the game has it."""
import math

import doors
import kits
import mapdata
from editing import EditError
from project import ref_info

# statics near a door that are not part of the house itself
NOT_A_BUILDING = ('terr', 'rock', 'cliff', 'flora', 'tree', 'bridge', 'plaza', 'root', 'dock', 'canal', 'road',
                  'pylon', 'parapet', 'grass', 'kelp', 'lava', 'mushroom', 'bush', 'water', 'light', 'banner',
                  'sign', 'lamp', 'lantern', 'cityw', 'citywall', 'skywalk', 'walkway', 'cantonwall', 'strongwall', 'shrub')
MAX_PIECES = 30
MAX_EXTENT = 2600
_cache = {}


def _bounds(db, rid, memo):
    if rid not in memo:
        ri = db.resolve_id(rid)
        memo[rid] = (mapdata.object_bounds(db, ri), db.recs[ri][0]) if ri is not None else (None, None)
    return memo[rid]


def _local(dx, dy, rz):
    """A world offset in the frame of something turned by rz (the game turns clockwise)."""
    return dx * math.cos(rz) - dy * math.sin(rz), dx * math.sin(rz) + dy * math.cos(rz)


def _world(lx, ly, rz):
    return lx * math.cos(rz) + ly * math.sin(rz), -lx * math.sin(rz) + ly * math.cos(rz)


def _box(b, pos, s):
    """The world-aligned box around a turned object: (x0, y0, x1, y1, z0, z1)."""
    xs, ys = [], []
    for cx in (b[0], b[3]):
        for cy in (b[1], b[4]):
            wx, wy = _world(cx * s, cy * s, pos[5])
            xs.append(pos[0] + wx)
            ys.append(pos[1] + wy)
    return (min(xs), min(ys), max(xs), max(ys), pos[2] + b[2] * s, pos[2] + b[5] * s)


def _touch(a, b, pad=24):
    return a[0] - pad < b[2] and b[0] - pad < a[2] and a[1] - pad < b[3] and b[1] - pad < a[3] and \
        a[4] - pad < b[5] and b[4] - pad < a[5]


def _family(rid):
    """The set a piece belongs to, e.g. ex_hlaalu_b_05 -> ex_hlaalu, T_De_SetHla_X_Roof -> t_de_sethla."""
    parts = rid.lower().split('_')
    return '_'.join(parts[:3] if parts[0] == 't' else parts[:2])


def shells(db, style, limit=16):
    """Whole outside buildings that lead into interiors built in this style:
    [{id, name, pieces: [{id, x, y, z, rx, ry, rz, s}] (relative to the front door), door, door_scale,
    arrive: [x, y, z] (relative to the door), door_above_ground, size: [w, d] (game units),
    main (its biggest piece), count}]."""
    stamp = (id(db.recs), len(db.recs))
    if style in _cache and _cache[style][0] == stamp:
        return _cache[style][1]
    kp = kits.kit_pieces(db, style)
    if not kp:
        return []
    cells = set()
    for p in kp['pieces'][:10]:
        cells |= set(db.used_in.get(p['id'].lower(), ()))
    memo, ext_refs = {}, {}
    found, seen_doors = [], set()
    for ci in sorted(cells)[:260]:
        r = db.recs[ci]
        if r[0] != 'CELL' or not kits.game_made(db, r[7]):
            continue
        name = r[1] or ''
        irefs, _h = db.cell_refs(r[7])
        for ref in irefs.values():
            _rid, _pos, _s, dead = ref_info(ref['subs'])
            if dead:
                continue
            link = doors.link_of(ref['subs'])
            if not link or link['cell']:
                continue                       # only ways out to the open air
            ek = link['key']
            if ek not in ext_refs:
                items = []
                er, _eh = db.cell_refs(ek)
                for eref in er.values():
                    erid, epos, es, edead = ref_info(eref['subs'])
                    if not edead:
                        b, tag = _bounds(db, erid.lower(), memo)
                        if b:
                            items.append({'id': erid, 'low': erid.lower(), 'p': epos, 's': es or 1.0, 'b': b,
                                          'tag': tag, 'box': _box(b, epos, es or 1.0),
                                          'to': doors.link_of(eref['subs']) if tag == 'DOOR' else None})
                ext_refs[ek] = items
            items = ext_refs[ek]
            # the outside door that leads back in here, nearest where you arrive
            back = None
            for it in items:
                if it['tag'] != 'DOOR' or not it['to'] or it['to']['cell'].lower() != name.lower():
                    continue
                d = math.hypot(it['p'][0] - link['x'], it['p'][1] - link['y'])
                if d < 600 and (back is None or d < back[0]):
                    back = (d, it)
            if not back or (ek, id(back[1])) in seen_doors:
                continue
            seen_doors.add((ek, id(back[1])))
            door = back[1]
            dp = door['p']
            # other houses' doors: pieces holding one of those belong to the neighbours
            others = [it for it in items if it['tag'] == 'DOOR' and it['to'] and it['to']['cell'] and
                      it['to']['cell'].lower() != name.lower() and math.hypot(it['p'][0] - dp[0], it['p'][1] - dp[1]) < MAX_EXTENT]
            cand = [it for it in items if it['tag'] == 'STAT' and it['low'].startswith(('ex_', 't_')) and
                    not any(w in it['low'] for w in NOT_A_BUILDING) and
                    max(it['b'][3] - it['b'][0], it['b'][4] - it['b'][1]) * it['s'] < 2400 and
                    math.hypot(it['p'][0] - dp[0], it['p'][1] - dp[1]) < MAX_EXTENT]
            # the piece the door is set into
            dbox = door['box']
            roots = [it for it in cand if _touch(it['box'], dbox, 40)]
            if not roots:
                continue
            root = max(roots, key=lambda it: (it['box'][2] - it['box'][0]) * (it['box'][3] - it['box'][1]))
            fam = _family(root['id'])
            group, todo = [root], [root]
            while todo and len(group) < MAX_PIECES:
                c = todo.pop()
                for it in cand:
                    # (houses often mix sets: Common walls with Imperial windows and a tower from another)
                    if it in group or not _touch(it['box'], c['box']):
                        continue
                    if any(_touch(it['box'], o['box'], 4) for o in others):
                        continue
                    group.append(it)
                    todo.append(it)
                    if len(group) >= MAX_PIECES:
                        break
            x0 = min(g['box'][0] for g in group)
            y0 = min(g['box'][1] for g in group)
            x1 = max(g['box'][2] for g in group)
            y1 = max(g['box'][3] for g in group)
            if max(x1 - x0, y1 - y0) > MAX_EXTENT or len(group) >= MAX_PIECES:
                continue                      # it ran on into the rest of the town
            drz = dp[5]
            # other doors set into these pieces (into a shop or an upstairs room in the original): copied
            # too, so their doorways aren't left as holes, and they lead into the new place as well
            extra = []
            same = [it for it in items if it['tag'] == 'DOOR' and it is not door and it['to'] and it['to']['cell'] and
                    it['to']['cell'].lower() == name.lower()]
            for o in others + same:
                if any(_touch(o['box'], g['box'], 8) for g in group):
                    lx, ly = _local(o['p'][0] - dp[0], o['p'][1] - dp[1], drz)
                    extra.append({'id': o['id'], 'x': round(lx, 2), 'y': round(ly, 2), 'z': round(o['p'][2] - dp[2], 2),
                                  'rz': round((o['p'][5] - drz) % (2 * math.pi), 5), 's': o['s']})
            # a house whose other doors (or the stairs up to them) would be left as open holes: skip it
            fbox = (x0 - 64, y0 - 64, x1 + 64, y1 + 64, min(g['box'][4] for g in group) - 64, max(g['box'][5] for g in group) + 64)
            loose = [o for o in items if o['tag'] == 'DOOR' and o is not door and o['to'] and o['to']['cell']]
            if any(_touch(o['box'], fbox, 0) for o in loose if not any(_touch(o['box'], g['box'], 8) for g in group)):
                continue
            pieces = []
            for g in group:
                lx, ly = _local(g['p'][0] - dp[0], g['p'][1] - dp[1], drz)
                pieces.append({'id': g['id'], 'x': round(lx, 2), 'y': round(ly, 2), 'z': round(g['p'][2] - dp[2], 2),
                               'rx': g['p'][3], 'ry': g['p'][4], 'rz': round((g['p'][5] - drz) % (2 * math.pi), 5),
                               's': g['s']})
            # the building's footprint in the door's own frame
            pts = []
            for g in group:
                for cx in (g['box'][0], g['box'][2]):
                    for cy in (g['box'][1], g['box'][3]):
                        pts.append(_local(cx - dp[0], cy - dp[1], drz))
            fx0, fx1 = min(p[0] for p in pts), max(p[0] for p in pts)
            fy0, fy1 = min(p[1] for p in pts), max(p[1] for p in pts)
            ax, ay = _local(link['x'] - dp[0], link['y'] - dp[1], drz)
            ground = mapdata.terrain_z(db, dp[0] + (link['x'] - dp[0]) * 0.5, dp[1] + (link['y'] - dp[1]) * 0.5)
            if ground is None:
                continue
            above = dp[2] - ground
            if not 30 < above < 260:
                continue                      # its door is up on a walkway or a balcony, not at the ground
            found.append({'id': '%s|%d' % (name.lower(), len(found)), 'like': name, 'pieces': pieces, 'doors': extra,
                          'door': door['id'], 'door_scale': door['s'], 'arrive': [ax, ay, link['z'] - dp[2]],
                          'door_above_ground': above, 'size': [round(fx1 - fx0), round(fy1 - fy0)],
                          'centre': [(fx0 + fx1) / 2, (fy0 + fy1) / 2],
                          'main': root['id'], 'count': len(pieces), 'family': fam})
    # the same house shape is often used more than once: keep one of each
    out, sigs = [], set()
    for t in sorted(found, key=lambda t: -t['count']):
        sig = tuple(sorted(p['id'].lower() for p in t['pieces']))
        if sig in sigs:
            continue
        sigs.add(sig)
        t['name'] = '%s (%d piece%s, about %d x %d m)' % (
            _short(t['like']), t['count'], '' if t['count'] == 1 else 's',
            round(t['size'][0] / 70.0), round(t['size'][1] / 70.0))
        out.append(t)
    out = out[:limit * 3]
    _cache[style] = (stamp, out)
    return out


def _short(cell_name):
    """'Balmora, Nine-toes' House' -> "Like Nine-toes' House (Balmora)"."""
    if ',' in cell_name:
        town, rest = cell_name.split(',', 1)
        return 'Like %s (%s)' % (rest.strip(), town.strip())
    return 'Like ' + cell_name


def for_rooms(db, style, w, d, limit=16):
    """The buildings for a style, best match for an interior w x d (game units) first, and preferring
    whole buildings (several pieces) over a lone wall piece."""
    out = shells(db, style)
    want = sorted((w, d))

    def score(t):
        have = sorted(t['size'])
        fit = abs(math.log(max(have[0], 50) / max(want[0], 50))) + abs(math.log(max(have[1], 50) / max(want[1], 50)))
        return (t['count'] < 2, round(fit, 2), -t['count'])
    return sorted(out, key=score)[:limit]


def place(db, shell, cell, x, y, facing):
    """Where every piece and the front door go for a building centred on (x, y) whose front door faces
    `facing` (radians clockwise from north). Returns ([(id, pose, scale)], door id, door pose, door
    scale, arrival pose outside the door, [other doors (id, pose, scale)])."""
    if not cell or not cell.startswith('#'):
        raise EditError('Outside buildings go outdoors: pick a spot in the open (not inside a place).')
    ax, ay = shell['arrive'][0], shell['arrive'][1]
    if math.hypot(ax, ay) < 1:
        ax, ay = 0.0, -1.0
    drz = (facing - math.atan2(ax, ay)) % (2 * math.pi)
    cx, cy = _world(shell['centre'][0], shell['centre'][1], drz)
    dx, dy = x - cx, y - cy                          # the door, so the middle of the building is on the spot
    wx, wy = _world(ax, ay, drz)
    ground = mapdata.terrain_z(db, dx + wx * 0.5, dy + wy * 0.5)
    if ground is None:
        ground = mapdata.terrain_z(db, x, y) or 0.0
    dz = ground + shell['door_above_ground']
    pieces = []
    for p in shell['pieces']:
        px, py = _world(p['x'], p['y'], drz)
        pieces.append((p['id'], (dx + px, dy + py, dz + p['z'], p['rx'], p['ry'], (drz + p['rz']) % (2 * math.pi)), p['s']))
    extra = []
    for p in shell.get('doors') or []:
        px, py = _world(p['x'], p['y'], drz)
        extra.append((p['id'], (dx + px, dy + py, dz + p['z'], 0, 0, (drz + p['rz']) % (2 * math.pi)), p['s']))
    out_yaw = math.atan2(wx, wy) % (2 * math.pi)
    return (pieces, shell['door'], (dx, dy, dz, 0, 0, drz), shell['door_scale'],
            (dx + wx, dy + wy, dz + shell['arrive'][2] + 8, 0, 0, out_yaw), extra)
