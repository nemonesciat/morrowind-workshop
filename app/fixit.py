"""Fix-it tools for places built from a style's room pieces (by "Build from pieces", by hand, or the
game's own): finding the gaps (a side open onto nothing, a doorway that leads nowhere, a missing
ceiling), the pieces that close them, other pieces that fit the same spot, and the patch pieces of a
style (loose walls, door frames, posts and columns) to fix things by hand."""
import math
import os
import re

import editing
import kits
import mapdata
from editing import EditError
from project import ref_info, set_ref_pos, zs

STEP = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
YAW = {'N': 0.0, 'E': math.pi / 2, 'S': math.pi, 'W': 3 * math.pi / 2}
PATCH_WORDS = ('pillar', 'column', 'post', 'endcap', '_end', 'cap', 'arch', 'jamb', 'wall', 'rail', 'trim')


def _tiles(db, m):
    """The place's floor tiles: [{ref, piece, kit, q, pat, x, y, floor, lvl}] and the main kit."""
    out, votes = [], {}
    for r in m['refs']:
        prefix = kits.kit_prefix(r['id'])
        kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
        if not kp:
            continue
        piece = next((p for p in kp['pieces'] if p['id'].lower() == r['id'].lower()), None)
        if not piece or abs((r['s'] or 1) - 1) > 0.02 or abs(r['p'][3]) > 0.05 or abs(r['p'][4]) > 0.05:
            continue
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        if abs(r['p'][5] - q * math.pi / 2) > 0.1 and abs(r['p'][5] - q * math.pi / 2 - 2 * math.pi) > 0.1:
            continue                                      # (turned at an odd angle: not part of a grid)
        floor = r['p'][2] + piece['zmin']
        out.append({'ref': r['k'], 'id': r['id'], 'piece': piece, 'kit': kp, 'q': q,
                    'pat': kits.rotate(piece['pattern'], q), 'x': r['p'][0], 'y': r['p'][1], 'z': r['p'][2],
                    'floor': floor, 'T': kp['tile'], 'H': kp['height']})
        votes[prefix] = votes.get(prefix, 0) + 1
    # the game often stacks two pieces on one spot (two walls turned differently make a corner): a spot
    # has every wall any of its pieces has
    for t in out:
        mates = [o for o in out if o is not t and abs(o['x'] - t['x']) < 8 and abs(o['y'] - t['y']) < 8
                 and abs(o['floor'] - t['floor']) < 32]
        if mates:
            pat = dict(t['pat'])
            for s in kits.SIDES:
                got = [t['pat'][s]] + [o['pat'][s] for o in mates]
                pat[s] = 'wall' if 'wall' in got else 'door' if 'door' in got else 'open'
            pat['ceiling'] = any(x['pat'].get('ceiling') for x in [t] + mates)
            t['spot'] = pat
            t['mates'] = [o['ref'] for o in mates]
            t['mate_pieces'] = [(o['id'], o['q']) for o in mates]
    return out, (max(votes, key=votes.get) if votes else None)


_learned = {}
_cell_tiles = {}


def _plain_tiles(db, cell_key):
    """(x, y, floor) of a place's kit floor pieces, cached (for learning how pieces are used)."""
    if cell_key not in _cell_tiles:
        try:
            m = mapdata.cellmap(db, cell_key)
            ts, _p = _tiles(db, m)
            _cell_tiles[cell_key] = [(t['id'].lower(), t['q'], t['x'], t['y'], t['floor'], t['T']) for t in ts]
        except Exception:
            _cell_tiles[cell_key] = []
        if len(_cell_tiles) > 2000:
            _cell_tiles.pop(next(iter(_cell_tiles)))
    return _cell_tiles[cell_key]


def learned(db, piece_id, own_cell=None):
    """How the game itself uses a piece: for each of its own sides (before turning), 'closed' when
    there is almost never anything beyond it in the game's places (it works as a wall, whatever its
    model looks like), 'open' when there almost always is, else None."""
    low = piece_id.lower()
    if _learned.get('_recs') is not db.recs:
        _learned.clear()
        _cell_tiles.clear()
        _learned['_recs'] = db.recs
    if low in _learned:
        return _learned[low]
    counts = {s: [0, 0] for s in kits.SIDES}       # side -> [nothing beyond, something beyond]
    open_top = [0, 0]                               # [nothing above, a floor above]
    cells = [db.recs[ci][7] for ci in list(db.used_in.get(low, ()))[:30]
             if db.recs[ci][0] == 'CELL' and not db.recs[ci][7].startswith('#') and db.recs[ci][7] != own_cell]
    for ck in cells:
        ts = _plain_tiles(db, ck)
        for pid, q, x, y, floor, T in ts:
            if pid != low:
                continue
            for n, s in enumerate(kits.SIDES):
                side = kits.SIDES[(n + q) % 4]                  # where this own side faces once turned
                dx, dy = STEP[side]
                nb = any(abs(o[2] - (x + dx * T)) < 24 and abs(o[3] - (y + dy * T)) < 24 and abs(o[4] - floor) < 64 for o in ts)
                counts[s][1 if nb else 0] += 1
            up = any(abs(o[2] - x) < 24 and abs(o[3] - y) < 24 and 64 < o[4] - floor < 900 for o in ts)
            open_top[1 if up else 0] += 1
    out = {}
    for s, (nothing, something) in counts.items():
        total = nothing + something
        out[s] = None if total < 4 else 'closed' if nothing >= total * 0.85 else 'open' if something >= total * 0.85 else None
    # the game uses it with nothing built on top: open to the roof on purpose (thatch, halls)
    out['open_top'] = sum(open_top) >= 4 and open_top[0] >= sum(open_top) * 0.85
    _learned[low] = out
    return out


def _closed_by_use(db, t, side, cell_key):
    """Is this side of the spot closed in the game's own use of its piece(s)?"""
    for rid, q in [(t['id'], t['q'])] + [(o_id, o_q) for o_id, o_q in t.get('mate_pieces', [])]:
        lr = learned(db, rid, cell_key)
        own = kits.SIDES[(kits.SIDES.index(side) - q) % 4]
        if lr.get(own) == 'closed':
            return True
    return False


# ------------------------------------------------------------------ posts and columns where walls meet
DIRS = ('N', 'E', 'S', 'W')


def _vertices(tiles):
    """The corners where floor tiles meet: {key: {x, y, floor, T, H, tiles, walls: set of directions a
    wall (or a wall with a doorway) runs off in from that corner}}."""
    V = {}
    for t in tiles:
        h = t['T'] / 2.0
        pat = t.get('spot') or t['pat']
        for cx, cy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vx, vy = t['x'] + cx * h, t['y'] + cy * h
            key = (round(vx / 16), round(vy / 16), round(t['floor'] / 64))
            v = V.setdefault(key, {'x': vx, 'y': vy, 'floor': t['floor'], 'T': t['T'], 'H': t['H'], 'tiles': 0,
                                   'walls': set(), 'kit': t['kit']})
            v['tiles'] += 1
            ns, ew = ('N' if cy > 0 else 'S'), ('E' if cx > 0 else 'W')
            if pat[ns] in ('wall', 'door'):
                v['walls'].add('W' if cx > 0 else 'E')         # that side runs from the corner along X, into the tile
            if pat[ew] in ('wall', 'door'):
                v['walls'].add('S' if cy > 0 else 'N')         # ...and that one along Y
    return V


def _add_frames(V, m, tiles):
    """Door frames standing on an edge between tiles (the Hlaalu way of making a doorway): the corners
    at their two ends get a 'frame' edge running toward the frame."""
    if not tiles:
        return
    T = tiles[0]['T']
    ids = {j['id'].lower() for t in tiles for j in t['kit'].get('jambs', [])}
    for r in m['refs']:
        low = r['id'].lower()
        if low not in ids and 'jamb' not in low and 'doorframe' not in low:
            continue
        bx = _world_box(r)
        if not bx:
            continue
        cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
        along_x = (bx[3] - bx[0]) >= (bx[4] - bx[1])
        ends = (((cx - T / 2, cy), 'E'), ((cx + T / 2, cy), 'W')) if along_x else (((cx, cy - T / 2), 'N'), ((cx, cy + T / 2), 'S'))
        for (ex, ey), d in ends:
            for v in V.values():
                if abs(v['x'] - ex) < 24 and abs(v['y'] - ey) < 24 and bx[2] < v['floor'] + 60 and bx[5] > v['floor'] + 60:
                    v.setdefault('frames', set()).add(d)


def _shape(v):
    """How the walls meet at a corner, the same whichever way it's turned: (tiles round it, pattern of
    edges: 0 nothing, 1 a door frame, 2 a wall)."""
    bits = [2 if d in v['walls'] else 1 if d in v.get('frames', ()) else 0 for d in DIRS]
    best = min(tuple(bits[(i + k) % 4] for i in range(4)) for k in range(4))
    return (v['tiles'], best)


def _posts_near(v, objs):
    """Something post-like standing on this corner: [(id, z, rz)] (any narrow, tall object)."""
    out = []
    for r, bx in objs:
        if abs((bx[0] + bx[3]) / 2 - v['x']) < 36 and abs((bx[1] + bx[4]) / 2 - v['y']) < 36 \
                and bx[2] < v['floor'] + 60 and bx[5] > v['floor'] + v['H'] * 0.4:
            out.append((r['id'], r['p'][2], r['p'][5]))
    return out


def _narrow_tall(m, H, skip=()):
    out = []
    for r in m['refs']:
        if r['k'] in skip or r['type'] != 'STAT':
            continue
        bx = _world_box(r)
        if bx and bx[3] - bx[0] <= 110 and bx[4] - bx[1] <= 110 and bx[5] - bx[2] >= H * 0.4:
            out.append((r, bx))
    return out


_post_rules = {}


def post_rules(db, prefix):
    """Where the game stands posts or columns in places built with this style: {corner shape: {'share':
    how often a corner like that has one, 'n': corners seen, 'id': the post used most, 'dz': its height
    above the floor}}."""
    if _post_rules.get('_recs') is not db.recs:
        _post_rules.clear()
        _post_rules['_recs'] = db.recs
    if prefix in _post_rules:
        return _post_rules[prefix]
    kp = kits.kit_pieces(db, prefix)
    cells = set()
    for p in (kp or {}).get('pieces', [])[:8]:
        cells |= {db.recs[ci][7] for ci in db.used_in.get(p['id'].lower(), ()) if db.recs[ci][0] == 'CELL'
                  and not db.recs[ci][7].startswith('#')}
    stats = {}
    for ck in sorted(cells)[:45]:
        try:
            m = mapdata.cellmap(db, ck)
        except Exception:
            continue
        tiles, pre = _tiles(db, m)
        tiles = [t for t in tiles if kits.kit_prefix(t['id']) == prefix]
        if len(tiles) < 4:
            continue
        objs = _narrow_tall(m, tiles[0]['H'], {t['ref'] for t in tiles})
        V = _vertices(tiles)
        _add_frames(V, m, tiles)
        for v in V.values():
            st = stats.setdefault(_shape(v), {'n': 0, 'with': 0, 'ids': {}, 'dz': []})
            st['n'] += 1
            near = _posts_near(v, objs)
            if near:
                st['with'] += 1
                rid, z, _rz = near[0]
                st['ids'][rid] = st['ids'].get(rid, 0) + 1
                st['dz'].append(z - v['floor'])
    out = {}
    for shape, st in stats.items():
        if not st['ids']:
            out[shape] = {'share': 0.0, 'n': st['n']}
            continue
        rid = max(st['ids'], key=st['ids'].get)
        dz = sorted(st['dz'])
        out[shape] = {'share': st['with'] / float(st['n']), 'n': st['n'], 'id': rid, 'dz': dz[len(dz) // 2]}
    _post_rules[prefix] = out
    return out


_post_piece = {}


def post_piece(db, kp):
    """The style's own narrow post or column, a storey tall (for covering the join where a door frame
    meets a wall): (id, bottom of its model) or None."""
    pre = kp.get('prefix')
    if pre in _post_piece and _post_piece[pre][0] is db.recs:
        return _post_piece[pre][1]
    best = None
    for ri in kp['ris']:
        rid = db.recs[ri][1]
        if not re.search(r'post|pillar|column', rid.lower()):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or b[3] - b[0] > 110 or b[4] - b[1] > 110 or not kp['height'] * 0.8 <= b[5] - b[2] <= kp['height'] * 1.3:
            continue
        uses = len(db.used_in.get(rid.lower(), ()))
        if best is None or uses > best[2]:
            best = (rid, b[2], uses)
    res = (best[0], best[1]) if best else None
    _post_piece[pre] = (db.recs, res)
    return res


def _frames_want_posts(db, prefix):
    """False for a style whose door frames close the join with the wall themselves: the game has many
    corners where one meets a wall and (next to) never stands a post there (Redoran's rounded frames)."""
    if not prefix:
        return True
    rules = post_rules(db, prefix)
    fr = [r for s, r in rules.items() if 1 in s[1] and 2 in s[1]]
    n = sum(r['n'] for r in fr)
    return n < 20 or sum(r['share'] * r['n'] for r in fr) / n >= 0.03


def missing_posts(db, m, tiles, only_frames=False):
    """Corners that want a post or column and haven't one: [{x, y, z, id, floor, why}]. Two kinds:
    where a door frame meets a wall (the join shows, unless the style's post covers it: what you'd
    add by hand), and corners where the game itself (almost) always stands one in this style."""
    if not tiles:
        return []
    import builder
    out = []

    def at(rid, v, z, why):
        # stand the middle of the model on the corner (some posts' models sit well off their origin)
        ri = next((i for i in db.by_id.get(rid.lower(), ()) if db.recs[i][0] == 'STAT'), None)
        x, y = builder._centred(db, ri, v['x'], v['y'], 0.0) if ri is not None else (v['x'], v['y'])
        out.append({'x': x, 'y': y, 'z': z, 'id': rid, 'floor': v['floor'], 'why': why, 'vx': v['x'], 'vy': v['y']})

    objs = _narrow_tall(m, tiles[0]['H'], {t['ref'] for t in tiles})
    V = _vertices(tiles)
    _add_frames(V, m, tiles)
    for v in V.values():
        if not v['walls'] and not v.get('frames'):
            continue
        if _posts_near(v, objs):
            continue
        if v.get('frames') and v['walls'] and _frames_want_posts(db, v['kit'].get('prefix')):
            pp = post_piece(db, v['kit'])
            if pp:
                at(pp[0], v, v['floor'] - pp[1], 'frame')
                continue
        if only_frames:
            continue
        prefix = v['kit'].get('prefix')
        rule = post_rules(db, prefix).get(_shape(v)) if prefix else None
        if not rule or rule.get('share', 0) < 0.6 or rule['n'] < 5 or not rule.get('id'):
            continue
        at(rule['id'], v, v['floor'] + rule['dz'], 'game')
    return out


def closing_pieces(db, cell_key):
    """For "Build from pieces": the pieces to add (no swaps) that the gap finder would: posts where
    door frames meet walls, at corners where the game always stands one, and over see-through holes
    ([(id, pos)])."""
    res = scan(db, cell_key)
    res['issues'] = [i for i in res['issues'] if i['kind'] in ('post', 'hole') and i['fixes']
                     and all(o.get('op') == 'place' for o in i['fixes'][0]['ops'])]
    if res['issues']:
        first = min(_rank(i) for i in res['issues'])       # (posts first; the builder looks again after)
        res['issues'] = [i for i in res['issues'] if _rank(i) == first]
    return [(o['id'], tuple(float(v) for v in o['p'][:6]), float(o.get('s', 1.0))) for o in _fix_ops(res)]


def _world_box(r):
    """A placed object's box in the world (turned about Z only), or None."""
    b = r.get('b')
    if not b:
        return None
    s = r['s'] or 1.0
    rz = r['p'][5]
    c, sn = math.cos(rz), math.sin(rz)
    xs, ys = [], []
    for lx in (b[0], b[3]):
        for ly in (b[1], b[4]):
            # the game turns clockwise
            xs.append(r['p'][0] + (lx * c + ly * sn) * s)
            ys.append(r['p'][1] + (-lx * sn + ly * c) * s)
    return (min(xs), min(ys), r['p'][2] + b[2] * s, max(xs), max(ys), r['p'][2] + b[5] * s)


def _edge(t, side):
    """An edge of a tile: (x0, y0, x1, y1) of its line."""
    h = t['T'] / 2.0
    x, y = t['x'], t['y']
    return {'N': (x - h, y + h, x + h, y + h), 'S': (x - h, y - h, x + h, y - h),
            'E': (x + h, y - h, x + h, y + h), 'W': (x - h, y - h, x - h, y + h)}[side]


def _covered(t, side, boxes):
    """Something else closes this side: a loose wall, a door frame, a door, a big piece of furniture."""
    x0, y0, x1, y1 = _edge(t, side)
    band = 48
    lo_z, hi_z = t['floor'] + 30, t['floor'] + 110
    for bx in boxes:
        if bx[2] > lo_z or bx[5] < hi_z:
            continue                                     # not across the height people walk at
        if side in 'NS':
            if bx[1] > y0 + band or bx[4] < y0 - band:
                continue
            span = min(bx[3], x1) - max(bx[0], x0)
        else:
            if bx[0] > x0 + band or bx[3] < x0 - band:
                continue
            span = min(bx[4], y1) - max(bx[1], y0)
        if span >= t['T'] * 0.6:
            return True
    return False


def _neighbour(tiles, t, side, floors=()):
    """What carries on past this side: another floor piece of the style, or any other piece of the
    building with a floor there (a plain floor slab, another set's room, stairs)."""
    dx, dy = STEP[side]
    tx, ty = t['x'] + dx * t['T'], t['y'] + dy * t['T']
    for o in tiles:
        if o is not t and abs(o['x'] - tx) < 24 and abs(o['y'] - ty) < 24 and abs(o['floor'] - t['floor']) < 64:
            return o
    for k in (0.6, 0.9):
        # (0.9: a half-length hall piece in the middle of the next tile)
        px, py = t['x'] + dx * t['T'] * k, t['y'] + dy * t['T'] * k
        for bx in floors:
            # (up to this floor's height counts: stairs coming up to it from below)
            if bx[0] <= px <= bx[3] and bx[1] <= py <= bx[4] and bx[2] <= t['floor'] + 64 and bx[5] >= t['floor'] - 16:
                return True
    return None


def _above(tiles, t):
    for o in tiles:
        if o is not t and abs(o['x'] - t['x']) < 24 and abs(o['y'] - t['y']) < 24 and 64 < o['floor'] - t['floor'] < t['H'] * 1.6:
            return o
    return None


def _variant(kp, want, ceiling=None, exclude=None):
    """The piece and turn of this kit with exactly these sides (and a ceiling, if asked): (piece, q) or None."""
    best = None
    for p in kp['pieces']:
        for q in range(4):
            pat = kits.rotate(p['pattern'], q)
            if any(pat[s] != want[s] for s in kits.SIDES):
                continue
            if ceiling is not None and bool(pat.get('ceiling')) != ceiling:
                continue
            if exclude and (p['id'].lower(), q) == exclude:
                continue
            score = (p['uses'] == 0, -p['uses'])
            if best is None or score < best[0]:
                best = (score, p, q)
    return (best[1], best[2]) if best else None


def _wall_fix(db, t, sides):
    """Loose wall pieces of the style along these sides of a tile."""
    import builder
    kp = t['kit']
    if not kp['walls']:
        return None
    wall = builder.plain_wall(kp, db)
    ops = []
    for s in sides:
        off = t['T'] / 2 - wall['thick'] / 2 - 2
        wx, wy = t['x'] + STEP[s][0] * off, t['y'] + STEP[s][1] * off
        rot = 0 if (s in 'EW') == wall['thin_x'] else math.pi / 2
        import seethrough
        rot = seethrough.facing(db, wall['ri'], (-STEP[s][0], -STEP[s][1]), rot)     # (its finished side in)
        wx, wy = builder._centred(db, wall['ri'], wx, wy, rot)
        ops.append({'op': 'place', 'id': wall['id'], 'p': [wx, wy, t['floor'] - wall['zmin'], 0, 0, rot]})
    return {'label': 'Add a wall piece (%s)' % wall['id'], 'ops': ops}


_narrow = {}


def _narrow_pieces(db, kp, limit=6):
    """The style's posts, pillars and columns about a storey tall, most used first: [(id, ri, bounds)]."""
    pre = kp.get('prefix')
    if pre in _narrow and _narrow[pre][0] is db.recs:
        return _narrow[pre][1]
    out = []
    for ri in kp['ris']:
        rid = db.recs[ri][1]
        if db.recs[ri][0] != 'STAT' or not re.search(r'post|pillar|column|support|beam', rid.lower()):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or b[3] - b[0] > 136 or b[4] - b[1] > 136 or not kp['height'] * 0.5 <= b[5] - b[2] <= kp['height'] * 1.5:
            continue
        out.append((len(db.used_in.get(rid.lower(), ())), rid, ri, b))
    out.sort(key=lambda x: -x[0])
    res = [(rid, ri, b) for _n, rid, ri, b in out[:limit]]
    if len(res) < 2:
        # a style without posts of its own: the columns the game stands by its doorways in this style,
        # then the ones it uses most in the same places, from a set of the same people (Nordic with
        # Nordic, Indoril with Indoril...)
        import builder
        fam = '_'.join((pre or '').lower().split('_')[:2]) + '_'
        by_doors = list(dict.fromkeys(p[0] for w in kits.edge_doors(db, pre) for p in w['parts']
                                      if re.search(r'post|pillar|column|support', p[0].lower())))
        for rid in by_doors + builder._co_used(db, kp, 'STAT', lambda key: key.startswith(fam) and
                                               re.search(r'post|pillar|column|support|beam', key)):
            ri = db.resolve_id(rid)
            b = mapdata.object_bounds(db, ri)
            if not b or b[3] - b[0] > 136 or b[4] - b[1] > 136 or not kp['height'] * 0.5 <= b[5] - b[2] <= kp['height'] * 1.5:
                continue
            if all(x[0].lower() != rid.lower() for x in res):
                res.append((rid, ri, b))
            if len(res) >= limit:
                break
    _narrow[pre] = (db.recs, res)
    return res


SHELL = 1.03        # how much bigger a backing copy of a floor piece is (so it's never taken for one: see _tiles)


def _hole_fixes(db, sc, hole, near=(), tile_refs=(), near_tiles=()):
    """Pieces of the style that close a see-through hole, tried against the same rays: [{label, ops}].
    near: the place's objects (for jambs and frames to repeat)."""
    import builder
    import seethrough
    t = hole['tile']
    h = t['T'] / 2.0
    ex, ey, ax, ay = hole['edge']
    spots = []
    if hole['u0'] < -h + 56:
        spots.append(-h)                            # the corner at that end
    if hole['u1'] > h - 56:
        spots.append(h)
    spots.append((hole['u0'] + hole['u1']) / 2)      # the hole itself
    cands = []
    for u in spots:
        x, y = ex + ax * u, ey + ay * u
        for rid, ri, b in _narrow_pieces(db, t['kit']):
            # every turn: some are half columns made to stand against a wall, seen from the front only
            for rot in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
                cx, cy = builder._centred(db, ri, x, y, rot)
                cands.append({'label': 'Add %s' % rid,
                              'ops': [{'op': 'place', 'id': rid, 'p': [round(cx, 2), round(cy, 2), t['floor'] - b[2], 0, 0, rot]}]})
    # is anything of the building just past this side (a hall piece that isn't a whole tile, stairs, a
    # door)? Then nothing goes there: a wall "outside" would stand across the way through
    nx_, ny_ = STEP[hole['side']]
    probes = [(ex + ax * u + nx_ * k, ey + ay * u + ny_ * k, t['floor'] + 60)
              for u in (hole['u0'], (hole['u0'] + hole['u1']) / 2, hole['u1'], 0.0) for k in (24, 64)]
    occupied = False
    for r in near:
        if r['k'] in tile_refs or r['k'] == t['ref'] or r['k'] in t.get('mates', ()) or \
                not (r.get('arch') or r['type'] == 'DOOR' or 'stair' in r['id'].lower()):
            continue
        bx = _world_box(r)
        if bx and (bx[3] - bx[0] >= 96 and bx[4] - bx[1] >= 96 or r['type'] == 'DOOR' or 'stair' in r['id'].lower()) and \
                any(bx[0] <= p[0] <= bx[3] and bx[1] <= p[1] <= bx[4] and bx[2] <= p[2] <= bx[5] for p in probes):
            occupied = True
            break
    if hole['void'] and not hole.get('inside') and not occupied and t['kit']['walls']:
        # a wall of the style standing just behind the hole, outside the room: only seen through the
        # hole, which then shows wall instead of nothing (for a style without posts, or a crooked seam)
        wall = builder.plain_wall(t['kit'], db)
        nx, ny = STEP[hole['side']]
        rot = 0 if (hole['side'] in 'EW') == wall['thin_x'] else math.pi / 2
        rot = seethrough.facing(db, wall['ri'], (-nx, -ny), rot)      # (its finished side toward the room)
        for u in spots[-1:] + spots[:-1]:
            bx, by = ex + ax * u + nx * (wall['thick'] / 2 + 6), ey + ay * u + ny * (wall['thick'] / 2 + 6)
            bx, by = builder._centred(db, wall['ri'], bx, by, rot)
            cands.append({'label': 'Back it with %s (outside the room)' % wall['id'],
                          'ops': [{'op': 'place', 'id': wall['id'], 'p': [round(bx, 2), round(by, 2), t['floor'] - wall['zmin'], 0, 0, rot]}]})
    # a copy of the floor piece a little bigger, in the same spot: its walls just behind the piece's own
    # (and its floor and ceiling just past them), seen only through the seam, in the same stuff. (Not
    # full size, so it's never taken for a floor piece of its own.) This one's, then the other pieces at
    # the ends of the hole.
    ends = [t] + [o for o in near_tiles if o is not t and abs(o['floor'] - t['floor']) < 32 and
                  min(math.hypot(o['x'] - (ex + ax * u), o['y'] - (ey + ay * u)) for u in (hole['u0'], hole['u1'])) < t['T'] * 0.75]

    def shell(p, x, y, q):
        # (grown about its origin: one with its origin at its floor goes down by half the growth, so
        # the copy's floor and ceiling both stand clear of the piece's own and don't flicker)
        low = p['height'] * (SHELL - 1) / 2 if p['zmin'] > -50 else 0
        return {'op': 'place', 'id': p['id'], 'p': [round(x, 2), round(y, 2), t['floor'] - p['zmin'] - low, 0, 0, q * math.pi / 2],
                's': SHELL}
    for o in ends[:3]:
        cands.append({'label': 'Back it with a copy of %s just behind it' % o['id'], 'ops': [shell(o['piece'], o['x'], o['y'], o['q'])]})
    if hole['void'] and not hole.get('inside') and not occupied and hole['u1'] - hole['u0'] >= 40:
        w = _wall_fix(db, t, [hole['side']])
        if w:
            cands.append(w)
    # a door jamb or frame standing by the hole, once more, moved over it (same stuff as the doorway)
    xh, yh = hole['x'], hole['y']
    for r in near:
        if r['type'] != 'STAT' or r['k'] in tile_refs or not r.get('ri') or not r.get('arch'):
            continue
        bx = _world_box(r)
        if not bx or math.hypot((bx[0] + bx[3]) / 2 - xh, (bx[1] + bx[4]) / 2 - yh) > 200 or \
                min(bx[3] - bx[0], bx[4] - bx[1]) > 80 or bx[5] - bx[2] < t['H'] * 0.5:
            continue
        # slid along its own line to where the rays through the hole cross that line
        along_x = (bx[3] - bx[0]) >= (bx[4] - bx[1])
        bcx, bcy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
        cross = []
        for o, d, tmax in hole['rays']:
            k = 1 if along_x else 0
            if abs(d[k]) < 1e-3:
                continue
            tt = ((bcy if along_x else bcx) - o[k]) / d[k]
            if 0 < tt < tmax:
                cross.append(o[1 - k] + d[1 - k] * tt)
        if len(cross) < len(hole['rays']) * 0.5:
            continue
        cross.sort()
        shift = cross[len(cross) // 2] - (bcx if along_x else bcy)
        if abs(shift) < 8:
            continue
        cx, cy = r['p'][0] + (shift if along_x else 0), r['p'][1] + (0 if along_x else shift)
        cands.append({'label': 'Add another %s over it' % r['id'],
                      'ops': [{'op': 'place', 'id': r['id'], 'p': [round(cx, 2), round(cy, 2), r['p'][2], r['p'][3], r['p'][4], r['p'][5]]}]})
    # a loose wall that doesn't reach the ceiling (an arched or carved top): the style's wall that does
    wall_ids = {w['id'].lower() for w in t['kit']['walls']}
    full = builder.plain_wall(t['kit'], db) if wall_ids else None
    for r in near:
        if not full or r['id'].lower() not in wall_ids or r['id'].lower() == full['id'].lower():
            continue
        wbx = _world_box(r)
        if not wbx or math.hypot((wbx[0] + wbx[3]) / 2 - hole['x'], (wbx[1] + wbx[4]) / 2 - hole['y']) > t['T'] * 0.7:
            continue
        along_y = (wbx[4] - wbx[1]) > (wbx[3] - wbx[0])
        rot = 0 if along_y == full['thin_x'] else math.pi / 2
        inward = (t['x'] - (wbx[0] + wbx[3]) / 2, t['y'] - (wbx[1] + wbx[4]) / 2)
        L = math.hypot(*inward) or 1.0
        rot = seethrough.facing(db, full['ri'], (inward[0] / L, inward[1] / L), rot)
        px, py = builder._centred(db, full['ri'], (wbx[0] + wbx[3]) / 2, (wbx[1] + wbx[4]) / 2, rot)
        pos = [round(px, 2), round(py, 2), t['floor'] - full['zmin'], 0, 0, rot]
        c = {'label': 'Swap the wall for %s (reaches the ceiling)' % full['id'],
             'ops': [{'op': 'swap', 'ref': r['k'], 'id': full['id'], 'rz': rot, 'p': pos}],
             'swap': (r['k'], full['id'], pos, 1.0)}
        # (first, when that wall is what's wrong: it stops short of the ceiling)
        if wbx[5] < t['floor'] + t['H'] - 12:
            cands.insert(0, c)
        else:
            cands.append(c)
    # a door that doesn't fill its doorway: another of the doors used with the style, sized to cover it
    for r in near:
        if r['type'] != 'DOOR' or not r.get('ri'):
            continue
        dbx = _world_box(r)
        if not dbx or math.hypot((dbx[0] + dbx[3]) / 2 - hole['x'], (dbx[1] + dbx[4]) / 2 - hole['y']) > t['T'] * 0.6:
            continue
        cur_w, cur_h = max(dbx[3] - dbx[0], dbx[4] - dbx[1]), dbx[5] - dbx[2]
        cur_thin_x = (dbx[3] - dbx[0]) < (dbx[4] - dbx[1])
        dcx, dcy = (dbx[0] + dbx[3]) / 2, (dbx[1] + dbx[4]) / 2
        nxs, nys = STEP[hole['side']]
        for did in builder._co_used(db, t['kit'], 'DOOR', lambda k: 'door' in k)[:15]:
            if did.lower() == r['id'].lower() or any(w in did.lower() for w in ('trap', 'hatch', 'cage', 'jail', 'secret', 'hidden', 'gate')):
                continue
            dri = db.resolve_id(did)
            cb = mapdata.object_bounds(db, dri) if dri is not None else None
            if not cb:
                continue
            w_c, h_c = max(cb[3] - cb[0], cb[4] - cb[1]), cb[5] - cb[2]
            if w_c < 1 or h_c < 1:
                continue
            s_ = max(cur_w * 1.08 / w_c, cur_h / h_c)
            if s_ > 2.0:
                continue
            rot = 0.0 if ((cb[3] - cb[0]) < (cb[4] - cb[1])) == cur_thin_x else math.pi / 2
            rot = builder._facing(db, dri, (-nxs, -nys), rot)
            px, py = builder._centred(db, dri, dcx, dcy, rot, s_)
            pos = [round(px, 2), round(py, 2), round(dbx[2] - cb[2] * s_, 2), 0, 0, rot]
            cands.append({'label': 'Swap the door for %s (fills the doorway)' % did,
                          'ops': [{'op': 'swap', 'ref': r['k'], 'id': did, 'rz': rot, 'p': pos, 's': round(s_, 3)}],
                          'swap': (r['k'], did, pos, s_)})
    # the piece next door has a wall (or a doorway) on this side and this one is open: the variant of
    # this piece with the same on that side meets it
    nbt = hole.get('nb')
    if nbt and not t.get('mates'):
        pat = t.get('spot') or t['pat']
        theirs = (nbt.get('spot') or nbt['pat'])[OPPOSITE[hole['side']]]
        if pat[hole['side']] != theirs:
            v = _variant(t['kit'], {s: (theirs if s == hole['side'] else pat[s]) for s in kits.SIDES})
            if v:
                rz = v[1] * math.pi / 2
                cands.insert(0, {'label': 'Swap for %s (meets the piece next to it)' % v[0]['id'],
                                 'ops': [{'op': 'swap', 'ref': t['ref'], 'id': v[0]['id'], 'rz': rz}],
                                 'swap': (t['ref'], v[0]['id'], [t['x'], t['y'], t['z'], 0, 0, rz])})
    good, best = [], None
    for c in cands:
        f = seethrough.closes(db, sc, hole, [] if c.get('swap') else c['ops'], c.pop('swap', None))
        if os.environ.get('SEETHROUGH_DEBUG'):
            print('  try', c['label'], [[round(v) for v in o['p'][:3]] for o in c['ops'] if 'p' in o], round(f, 2))
        if f >= 0.9:
            if not any(g['label'] == c['label'] for g in good):
                good.append(c)
            if len(good) >= 3:
                break
        elif f >= 0.5 and (best is None or f > best[0]):
            best = (f, c)
    if not good and best:
        best[1]['label'] += ' (closes most of it)'
        good = [best[1]]
    return good


def _short_issues(db, m):
    """Half-length pieces (a hall piece 128 long) put down where a whole tile should be: the floor and
    walls stop short of the next piece. Fixed the way you would by hand: a second one end to end
    (sliding the first over, when it was set in the middle)."""
    halves = {}
    for r in m['refs']:
        pre = kits.kit_prefix(r['id'])
        if pre and pre in kits.kits(db) and pre not in halves:
            kp = kits.kit_pieces(db, pre)
            halves[pre] = (kp, {h['id'].lower(): h for h in kp.get('halves', [])})
    boxes = [(r, bx) for r in m['refs'] if r.get('arch') for bx in [_world_box(r)]
             if bx and (bx[3] - bx[0]) >= 96 and (bx[4] - bx[1]) >= 96]
    out = []
    for r in m['refs']:
        pre = kits.kit_prefix(r['id'])
        kp, hv = halves.get(pre, (None, {}))
        h = hv.get(r['id'].lower())
        if not h or abs((r['s'] or 1) - 1) > 0.05:
            continue
        T, H, L = kp['tile'], kp['height'], h['length']
        floor = r['p'][2] + h['zmin']
        rz = r['p'][5]
        lx, ly = (1.0, 0.0) if h['axis'] == 'x' else (0.0, 1.0)
        dx, dy = lx * math.cos(rz) + ly * math.sin(rz), -lx * math.sin(rz) + ly * math.cos(rz)
        bx0 = _world_box(r)
        if not bx0:
            continue
        cx, cy = (bx0[0] + bx0[3]) / 2, (bx0[1] + bx0[4]) / 2
        gaps = {}
        for sgn in (1, -1):
            ex, ey = cx + sgn * dx * L / 2, cy + sgn * dy * L / 2
            g = T
            for k in range(1, int(T / 8) + 1):
                px, py = ex + sgn * dx * (8 * k - 4), ey + sgn * dy * (8 * k - 4)
                if any(o is not r and bx[0] - 1 <= px <= bx[3] + 1 and bx[1] - 1 <= py <= bx[4] + 1 and
                       bx[2] <= floor + 24 and bx[5] >= floor + H * 0.5 for o, bx in boxes):
                    g = 8 * (k - 1)
                    break
            gaps[sgn] = g
        if gaps[1] <= 8 and gaps[-1] <= 8:
            continue
        ops = None
        p = list(r['p'])

        def at(shift):
            return [round(p[0] + dx * shift, 2), round(p[1] + dy * shift, 2), p[2], p[3], p[4], p[5]]
        if min(gaps.values()) >= L / 2 - 16 and L <= T * 0.7:
            # set in the middle of a tile: slide it to one end, a second one at the other
            ops = [{'op': 'move', 'ref': r['k'], 'p': at(-L / 2)}, {'op': 'place', 'id': r['id'], 'p': at(L / 2)}]
        else:
            for sgn in (1, -1):
                if L - 16 <= gaps[sgn] <= T:
                    ops = (ops or []) + [{'op': 'place', 'id': r['id'], 'p': at(sgn * L)}]
        for sgn in (1, -1):
            if gaps[sgn] <= 8:
                continue
            mx, my = cx + sgn * dx * (L / 2 + min(gaps[sgn], L) / 2), cy + sgn * dy * (L / 2 + min(gaps[sgn], L) / 2)
            out.append({'kind': 'gap', 'ref': r['k'], 'id': r['id'], 'x': mx, 'y': my, 'z': floor + 110,
                        'text': 'A half-length piece stops short here: the floor and walls are missing for %d units' % gaps[sgn],
                        'fixes': [{'label': 'Fill it with a second %s' % r['id'], 'ops': ops}] if ops else []})
    return out


def _cover_fixes(db, sc, hole, t, spots):
    """For a hole in a floor or a ceiling: a copy of the floor piece (or one next to it) a little bigger
    in the same spot, its floor just under and its ceiling just over the piece's own."""
    import seethrough
    best = None
    for o in [t] + [o for o in spots if o is not t and abs(o['floor'] - t['floor']) < 32 and
                    math.hypot(o['x'] - hole['x'], o['y'] - hole['y']) < t['T'] * 0.9][:4]:
        p = o['piece']
        low = p['height'] * (SHELL - 1) / 2 if p['zmin'] > -50 else 0
        op = {'op': 'place', 'id': p['id'], 'p': [o['x'], o['y'], o['floor'] - p['zmin'] - low, 0, 0, o['q'] * math.pi / 2], 's': SHELL}
        f = seethrough.closes(db, sc, hole, [op])
        if f >= 0.9:
            return [{'label': 'Back it with a copy of %s just behind it' % p['id'], 'ops': [op]}]
        if f >= 0.5 and (best is None or f > best[0]):
            best = (f, {'label': 'Back it with a copy of %s just behind it (closes most of it)' % p['id'], 'ops': [op]})
    return [best[1]] if best else []


def _hole_issues(db, m, tiles, floors, issues, cell_key):
    import seethrough
    seen, spots = set(), []
    for t in tiles:
        if t['ref'] in seen:
            continue
        seen.update(t.get('mates', []))
        spots.append(t)
    # (what the other fixes would add counts as there already: no hole is reported twice)
    known = [(op['id'], op['p']) for i in issues if i['kind'] == 'post' for op in i['fixes'][0]['ops']]
    gap_sides = {(i['ref'], i.get('side')) for i in issues if i['kind'] in ('gap', 'doorway')}
    ceilings = {i['ref'] for i in issues if i['kind'] == 'ceiling'}
    frames = [bx for r in m['refs'] if re.search(r'jamb|frame|doorway|arch|_dj(_|\d|$)', r['id'].lower())
              for bx in [_world_box(r)] if bx]

    def walled(t, s):
        """A wall, a doorway or a door frame on this side (not open floor running on into the room)."""
        if (t.get('spot') or t['pat'])[s] != 'open':
            return True
        o = _neighbour(tiles, t, s)
        if isinstance(o, dict) and (o.get('spot') or o['pat'])[OPPOSITE[s]] != 'open':
            return True
        x0, y0, x1, y1 = _edge(t, s)
        for bx in frames:
            # (one standing along this side, not just touching its end from the next side)
            if s in 'NS' and bx[1] - 40 <= y0 <= bx[4] + 40 and min(bx[3], x1) - max(bx[0], x0) >= 32:
                return True
            if s in 'EW' and bx[0] - 40 <= x0 <= bx[3] + 40 and min(bx[4], y1) - max(bx[1], y0) >= 32:
                return True
        return False
    try:
        hs, sc = seethrough.holes(db, m, spots, lambda t, s: _neighbour(tiles, t, s, floors), lambda t: _above(tiles, t), known,
                                  walled, floors)
    except Exception as e:
        print('see-through check:', e)
        return []
    out, planned = [], []
    for hole in hs:
        t = hole['tile']
        # (the fix for a hole next to it closes this one too: one post for a corner seen from two sides)
        if planned and hole['kind'] == 'wall' and seethrough.closes(db, sc, hole, planned) >= 0.9:
            continue
        if hole['kind'] == 'ceiling':
            if t['ref'] in ceilings or learned(db, t['id'], cell_key).get('open_top'):
                continue
            out.append({'kind': 'hole', 'ref': t['ref'], 'id': t['id'], 'x': hole['x'], 'y': hole['y'], 'z': hole['z'],
                        'text': 'A hole in the ceiling: the void shows through', 'fixes': _cover_fixes(db, sc, hole, t, spots)})
            continue
        if hole['kind'] == 'floor':
            out.append({'kind': 'hole', 'ref': t['ref'], 'id': t['id'], 'x': hole['x'], 'y': hole['y'], 'z': hole['z'],
                        'text': 'A hole in the floor: the void shows through', 'fixes': _cover_fixes(db, sc, hole, t, spots)})
            continue
        if (t['ref'], hole['side']) in gap_sides:
            continue
        fixes = _hole_fixes(db, sc, hole, m['refs'], {x['ref'] for x in tiles}, spots)
        if fixes:
            planned += fixes[0]['ops']
        out.append({'kind': 'hole', 'side': hole['side'], 'ref': t['ref'], 'id': t['id'],
                    'x': hole['x'], 'y': hole['y'], 'z': hole['z'],
                    'text': ('Pieces don\'t meet here: the void shows through' if hole['void'] else
                             'Pieces don\'t meet here: a slit into the next room'),
                    'fixes': fixes})
    return out


def scan(db, cell_key):
    """The gaps of a place: {'issues': [{kind, text, x, y, z, ref, side(s), fixes: [{label, ops}]}],
    'tiles': how many floor pieces were looked at, 'style'}."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('The gap finder works in interiors built from room pieces.')
    tiles, prefix = _tiles(db, m)
    if not tiles:
        return {'issues': [], 'tiles': 0, 'style': None,
                'note': 'This place isn\'t built from a style\'s room pieces, so there is nothing to check.'}
    tile_refs = {t['ref'] for t in tiles}
    boxes = [bx for r in m['refs'] if r['k'] not in tile_refs and r['type'] in ('STAT', 'DOOR', 'ACTI', 'CONT', 'LIGH')
             for bx in [_world_box(r)] if bx]
    # other parts of the building with a floor (to see that a room carries on past an open side)
    # (any big piece counts: half-length hall pieces, platforms and the like aren't always named as building)
    floors = [bx for r in m['refs'] if r['k'] not in tile_refs and (r.get('arch') or r['type'] in ('STAT', 'ACTI'))
              for bx in [_world_box(r)] if bx and (bx[3] - bx[0]) * (bx[4] - bx[1]) >= 128 * 96]
    # the game hides views into nothing with flat black squares
    blacks = [r for r in m['refs'] if 'blacksquare' in r['id'].lower() or 'black_square' in r['id'].lower()]
    # where doors stand (the middle of each door's box)
    door_spots = [((bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, bx[2]) for r in m['refs'] if r['type'] == 'DOOR'
                  for bx in [_world_box(r)] if bx]
    issues, done = [], set()
    for t in tiles:
        if t['ref'] in done:
            continue
        done.update(t.get('mates', []))
        kp, pat = t['kit'], t.get('spot') or t['pat']
        gaps, dead_doors = [], []
        for s in kits.SIDES:
            if pat[s] == 'wall' or _neighbour(tiles, t, s, floors) or _covered(t, s, boxes):
                continue
            x0, y0, x1, y1 = _edge(t, s)
            ex, ey = (x0 + x1) / 2, (y0 + y1) / 2
            if any(math.hypot(b['p'][0] - ex, b['p'][1] - ey) < t['T'] * 0.75 for b in blacks):
                continue
            # a door in the doorway (the way out, or one to somewhere else) closes it, whatever its size
            if any(math.hypot(d[0] - ex, d[1] - ey) < max(96, t['T'] * 0.35) and abs(d[2] - t['floor']) < 160 for d in door_spots):
                continue
            if _closed_by_use(db, t, s, cell_key):
                continue                  # (the game itself leaves nothing beyond this side of the piece)
            (gaps if pat[s] == 'open' else dead_doors).append(s)
        # (a spot of stacked pieces swapped for one piece: the others go)
        dels = [{'op': 'delete', 'ref': r} for r in t.get('mates', [])]
        if gaps or dead_doors:
            sides = gaps + dead_doors
            want = {s: ('wall' if s in sides else pat[s]) for s in kits.SIDES}
            fixes = []
            # first: the piece "Build from pieces" would choose for a spot like this (it knows which
            # pieces are plain and which have bits standing in the way), with loose walls for what it lacks
            import builder
            piece, q, missing, _p = builder._pick(kp, want)
            if piece and (piece['id'].lower() != t['id'].lower() or q != t['q']):
                wf = _wall_fix(db, t, missing) if missing else None
                if not missing or wf:
                    fixes.append({'label': 'Swap for %s%s' % (piece['id'], ' and add walls' if missing else ' (walled there)'),
                                  'ops': [{'op': 'swap', 'ref': t['ref'], 'id': piece['id'], 'rz': q * math.pi / 2}] + dels +
                                  (wf['ops'] if wf else [])})
            # then a piece with exactly these sides, if that's another one
            v = _variant(kp, want)
            if v and not (piece and v[0]['id'].lower() == piece['id'].lower()):
                fixes.append({'label': 'Swap for %s (walled there)' % v[0]['id'],
                              'ops': [{'op': 'swap', 'ref': t['ref'], 'id': v[0]['id'], 'rz': v[1] * math.pi / 2}] + dels})
            w = _wall_fix(db, t, sides)
            if w:
                fixes.append(w)
            for s in sides:
                x0, y0, x1, y1 = _edge(t, s)
                issues.append({'kind': 'gap' if s in gaps else 'doorway', 'side': s, 'ref': t['ref'], 'id': t['id'],
                               'x': (x0 + x1) / 2, 'y': (y0 + y1) / 2, 'z': t['floor'] + 110,
                               'text': ('An open side looking out onto nothing (a black gap)' if s in gaps else
                                        'A doorway that leads nowhere'), 'fixes': fixes})
        # a missing ceiling, where nothing is built on top (and no separate ceiling or roof piece covers it)
        roofed = any(bx[0] <= t['x'] <= bx[3] and bx[1] <= t['y'] <= bx[4] and bx[2] > t['floor'] + t['H'] * 0.5
                     for bx in floors)
        # (only when the style has a piece with a ceiling here: in styles whose ceilings are domes or
        # beams, a piece's ceiling isn't flat enough to be seen, and the style has nothing better anyway)
        v = _variant(kp, {s: pat[s] for s in kits.SIDES}, ceiling=True) \
            if not pat.get('ceiling') and not roofed and not _above(tiles, t) and \
            not learned(db, t['id'], cell_key).get('open_top') else None
        if v:
            fixes = [{'label': 'Swap for %s (with a ceiling)' % v[0]['id'],
                      'ops': [{'op': 'swap', 'ref': t['ref'], 'id': v[0]['id'], 'rz': v[1] * math.pi / 2}] + dels}]
            issues.append({'kind': 'ceiling', 'ref': t['ref'], 'id': t['id'], 'x': t['x'], 'y': t['y'],
                           'z': t['floor'] + t['H'] - 20, 'text': 'No ceiling over this spot', 'fixes': fixes})
    # corners where walls meet and the style always stands a post or column, but this place hasn't
    for p in missing_posts(db, m, tiles):
        issues.append({'kind': 'post', 'ref': None, 'id': p['id'], 'x': p['vx'], 'y': p['vy'], 'z': p['floor'] + 110,
                       'text': ('Where a door frame meets the wall: a post covers the join' if p['why'] == 'frame' else
                                'A gap where walls meet: the style stands a post here'),
                       'fixes': [{'label': 'Add %s' % p['id'], 'ops': [{'op': 'place', 'id': p['id'], 'p': [p['x'], p['y'], p['z'], 0, 0, 0]}]}]})
    # half-length pieces where a whole one should be
    issues += _short_issues(db, m)
    # what the player can actually see through: slits and corners where pieces don't meet
    issues += _hole_issues(db, m, tiles, floors, issues, cell_key)
    # in the order to fix them in (posts first: they often close what's below them in the list)
    issues.sort(key=lambda i: _rank(i) if i['fixes'] else 3)
    for n, i in enumerate(issues):
        i['n'] = n
    return {'issues': issues, 'tiles': len(tiles), 'style': kits.friendly(prefix) if prefix else None}


def variants(db, cell_key, refkey):
    """Other pieces of the same style that fit the spot of this floor piece, most alike first:
    [{id, rz, pattern ('NESW' letters), same (how many sides match), ceiling}]."""
    m = mapdata.cellmap(db, cell_key)
    tiles, _p = _tiles(db, m)
    t = next((x for x in tiles if x['ref'] == refkey), None)
    if not t:
        # a loose piece (wall, frame, post): others of the style the same size
        r = next((x for x in m['refs'] if x['k'] == refkey), None)
        prefix = kits.kit_prefix(r['id']) if r else None
        kp = kits.kit_pieces(db, prefix) if prefix and prefix in kits.kits(db) else None
        if not r or not kp:
            return {'variants': [], 'note': 'This isn\'t one of a building style\'s pieces.'}
        b = r.get('b')
        out = []
        for ri in kp['ris']:
            rid = db.recs[ri][1]
            if rid.lower() == r['id'].lower():
                continue
            ob = mapdata.object_bounds(db, ri)
            if not ob or not b:
                continue
            if all(abs((ob[k + 3] - ob[k]) - (b[k + 3] - b[k])) < max(24, (b[k + 3] - b[k]) * 0.2) for k in range(3)):
                out.append({'id': rid, 'rz': r['p'][5], 'uses': len(db.used_in.get(rid.lower(), ()))})
        out.sort(key=lambda v: -v['uses'])
        return {'variants': out[:24]}
    kp = t['kit']
    out = []
    for p in kp['pieces']:
        for q in range(4):
            pat = kits.rotate(p['pattern'], q)
            if p['id'].lower() == t['id'].lower() and q == t['q']:
                continue
            same = sum(1 for s in kits.SIDES if pat[s] == t['pat'][s])
            out.append({'id': p['id'], 'rz': q * math.pi / 2, 'same': same, 'uses': p['uses'],
                        'pattern': ''.join(pat[s][0].upper() for s in kits.SIDES), 'ceiling': bool(pat.get('ceiling'))})
    # (one turn of each look: the turns of a symmetrical piece look alike)
    seen, uniq = set(), []
    for v in sorted(out, key=lambda v: (-v['same'], v['uses'] == 0, -v['uses'])):
        key = (v['id'].lower(), v['pattern'])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(v)
    return {'variants': uniq[:30], 'current': ''.join(t['pat'][s][0].upper() for s in kits.SIDES)}


def apply(db, cell_key, ops, label=None, commit=True):
    """Make these changes as one step (one undo): swap a piece for another (keeping its spot, at a new
    turn), or place a new one. (commit=False: made, but saved as a step by a later commit.)"""
    editing._require_project(db)
    if not ops:
        raise EditError('Nothing to change.')
    c, refs = editing._cell(db, cell_key)
    mine = db.project.plugin.lower()
    done = []
    for op in ops:
        if op.get('op') == 'swap':
            ref = refs.get(op['ref'])
            if not ref:
                continue
            ri = db.resolve_id(op['id'])
            if ri is None:
                raise EditError('No object called "%s".' % op['id'])
            _rid, pos, scale, _dead = ref_info(ref['subs'])
            pos = list(op['p'][:6]) if op.get('p') else list(pos)        # (a door swapped is centred and sized anew)
            pos[5] = float(op.get('rz', pos[5])) % (2 * math.pi)
            subs = [(t, zs(db.recs[ri][1]) if t == 'NAME' else d) for t, d in ref['subs']]
            if db.recs[ri][0] != 'DOOR':
                subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
            editing._store(c, op['ref'], ref['origin'], ref['idx'],
                           set_ref_pos(subs, tuple(float(v) for v in pos), float(op['s']) if op.get('s') else None))
            done.append(op['ref'])
        elif op.get('op') == 'move':
            ref = refs.get(op['ref'])
            if not ref:
                continue
            editing._store(c, op['ref'], ref['origin'], ref['idx'],
                           set_ref_pos(ref['subs'], tuple(float(v) for v in op['p'][:6]), None))
            done.append(op['ref'])
        elif op.get('op') == 'delete':
            ref = refs.get(op['ref'])
            if not ref:
                continue
            if ref['origin'] == mine:
                c['refs'].pop(op['ref'], None)           # something of this mod: just gone
            else:
                editing._store(c, op['ref'], ref['origin'], ref['idx'], ref['subs'], deleted=True)
            done.append(op['ref'])
        elif op.get('op') == 'place':
            ri = db.resolve_id(op['id'])
            if ri is None:
                raise EditError('No object called "%s".' % op['id'])
            rk = db.project.new_ref_key()
            origin, idx = rk.rsplit('|', 1)
            p = [float(v) for v in op['p']][:6]
            editing._store(c, rk, origin, int(idx), set_ref_pos([('NAME', zs(db.recs[ri][1]))], tuple(p), float(op.get('s', 1.0))))
            done.append(rk)
    if not done:
        raise EditError('Those pieces are no longer there.')
    if not commit:
        db.sync_project()
        return {'changed': done}
    editing.commit(db, label or 'Fixed %d spot%s in %s' % (len(done), '' if len(done) == 1 else 's',
                                                          editing.cell_label(db, cell_key)))
    return {'changed': done}


def fix_all(db, cell_key):
    """Every gap with a fix, each with its first fix, as one step. A few rounds: a piece put in can
    show a smaller gap beside it, closed by the next round (all of it one undo)."""
    editing._require_project(db)
    changed, placed = [], []
    res = scan(db, cell_key)
    for _round in range(6):
        # the smallest fixes first, looking again after each kind: a post often closes what a wall
        # would otherwise be put in for, and a wall first can leave the corner a post should cover
        todo = [i for i in res['issues'] if i['fixes']]
        ops = []
        for rank in sorted({_rank(i) for i in todo}):
            ops = _fix_ops({'issues': [i for i in todo if _rank(i) == rank]}, placed)
            if ops:
                break                 # (nothing new of this kind to do: the next kind)
        if not ops:
            break
        changed += apply(db, cell_key, ops, commit=False)['changed']
        placed += [o for o in ops if o.get('op') == 'place']
        res = scan(db, cell_key)
    if not changed:
        return {'changed': [], 'left': len(res['issues'])}
    editing.commit(db, 'Closed the gaps in %s' % editing.cell_label(db, cell_key))
    return {'changed': changed, 'left': len(res['issues'])}


def _rank(i):
    """Which fixes go first: posts and columns, then the pieces a place is missing (a half-length
    piece's other half, a wall, a ceiling), then backing pieces and door swaps."""
    label = i['fixes'][0]['label']
    if i['kind'] == 'post' or (label.startswith('Add ') and 'wall' not in label) or label.startswith('Swap the wall'):
        return 0
    if 'half-length' in i['text']:
        return 1                  # (before walling anything: the side it leaves open is then open no more)
    if i['kind'] in ('gap', 'doorway', 'ceiling'):
        return 2
    return 3


def _fix_ops(res, placed=()):
    """The first fix of every gap that has one, without doing anything twice."""
    ops, seen = [], set()
    for i in res['issues']:
        if not i['fixes']:
            continue
        key = ((round(i['x']), round(i['y']), round(i['z'])) if i['kind'] in ('post', 'hole') or not i['ref'] else i['ref'],
               i['fixes'][0]['label'])
        if key in seen:
            continue                 # (one fix per tile: its sides were all fixed together)
        seen.add(key)
        # a tile is swapped only once: a later fix for the same tile (a ceiling) is left for another round
        if any(o.get('op') == 'swap' and o['ref'] == i['ref'] for o in ops) and \
                any(o.get('op') == 'swap' for o in i['fixes'][0]['ops']):
            continue
        for op in i['fixes'][0]['ops']:
            if op.get('op') in ('swap', 'move', 'delete') and any(o.get('op') == op['op'] and o.get('ref') == op['ref'] for o in ops):
                continue             # (a piece two fixes change, changed once)
            # (the same piece in the same place, wanted by two fixes, goes in once)
            # (or, in one go, so near it's the same post twice; one put in before that didn't close
            # this, near but not on the spot, doesn't stop it)
            if op.get('op') == 'place' and (
                    any(o.get('op') == 'place' and o['id'] == op['id'] and abs(o['p'][0] - op['p'][0]) < 48 and
                        abs(o['p'][1] - op['p'][1]) < 48 and abs(o['p'][2] - op['p'][2]) < 32 for o in ops) or
                    any(o['id'] == op['id'] and abs(o['p'][0] - op['p'][0]) < 4 and abs(o['p'][1] - op['p'][1]) < 4 and
                        abs(o['p'][2] - op['p'][2]) < 4 and abs(o['p'][5] - op['p'][5]) < 0.05 for o in placed)):
                continue
            ops.append(op)
    return ops


def patch_pieces(db, cell_key, limit=24):
    """The style's pieces for fixing things by hand, for the Suggested list: loose walls, door frames,
    posts, columns, arches, end caps, then the floor pieces most used."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        return []
    _tiles_, prefix = _tiles(db, m)
    if not prefix:
        return []
    kp = kits.kit_pieces(db, prefix)
    items, seen = [], set()

    def add(ri):
        r = db.recs[ri]
        if r[1].lower() in seen:
            return
        seen.add(r[1].lower())
        b = mapdata.object_bounds(db, ri)
        items.append({'id': r[1], 'name': r[2], 'type': r[0], 'here': False,
                      'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])] if b else None})
    for w in kp['walls'] + kp['jambs']:
        add(w['ri'])
    patch = [ri for ri in kp['ris'] if re.search(r'pillar|column|post|endcap|_end|_cap|arch|trim|rail', db.recs[ri][1].lower())]
    patch.sort(key=lambda ri: -len(db.used_in.get(db.recs[ri][1].lower(), ())))
    for ri in patch:
        add(ri)
    for p in kp['pieces']:
        add(p['ri'])
    return items[:limit]
