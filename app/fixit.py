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
        # (a two-storey hall piece counts as a tile of its lower storey: Redoran (large)'s lcorner_01 and kin)
        tall = None if piece else next((p for p in kp.get('tall') or [] if p['id'].lower() == r['id'].lower()), None)
        piece = piece or tall
        if not piece or abs((r['s'] or 1) - 1) > 0.02 or abs(r['p'][3]) > 0.05 or abs(r['p'][4]) > 0.05:
            continue
        q = int(round(r['p'][5] / (math.pi / 2))) % 4
        if abs(r['p'][5] - q * math.pi / 2) > 0.1 and abs(r['p'][5] - q * math.pi / 2 - 2 * math.pi) > 0.1:
            continue                                      # (turned at an odd angle: not part of a grid)
        floor = r['p'][2] + piece['zmin']
        out.append({'ref': r['k'], 'id': r['id'], 'piece': piece, 'kit': kp, 'q': q,
                    'pat': kits.rotate(piece['lower'] if tall else piece['pattern'], q), 'x': r['p'][0], 'y': r['p'][1], 'z': r['p'][2],
                    'floor': floor, 'T': kp['tile'], 'H': kp['height'], 'tall': bool(tall)})
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
             if db.recs[ci][0] == 'CELL' and not db.recs[ci][7].startswith('#') and db.recs[ci][7] != own_cell
             and kits.game_made(db, db.recs[ci][7])]
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
        if not bx or bx[5] - bx[2] < H * 0.4:
            continue
        w, d = bx[3] - bx[0], bx[4] - bx[1]
        # (the Common sets' in_c_pillar_wood / _stone are 132 across: wider than 110, and the post rules
        # never saw them, so no corner of a Common place ever "wanted" a post. A piece named for a post
        # counts up to 160 across)
        if (w <= 110 and d <= 110) or (COLUMN_WORDS.search(r['id'].lower()) and w <= 160 and d <= 160):
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
        cells |= {db.recs[ci][7] for ci in db.used_in.get(p['id'].lower(), ()) if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7])
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


DECOR_POST = re.compile(r'glass|screen|lattice|broken|ruin|fancy|banner|flag|lamp|light')


def _kit_statics(db, kp):
    """The style's statics: the kit's own, and the others that share its name (a set's posts and ledges,
    whose names don't say "room" or "wall": T_De_SetHla_I_LedgePost_01)."""
    out = list(kp['ris'])
    seen = set(out)
    pre = (kp.get('prefix') or '').lower() + '_'
    if len(pre) > 1:
        for (tag, k), lst in db.by_key.items():
            if tag == 'STAT' and k.startswith(pre) and lst and lst[-1] not in db.dead and lst[-1] not in seen:
                seen.add(lst[-1])
                out.append(lst[-1])
    return out


def post_piece(db, kp):
    """The style's own narrow post or column, a storey tall (for covering the join where a door frame
    meets a wall): (id, bottom of its model) or None. The one the game uses most, and never a
    decorative one (a glass pillar) when a plain one exists."""
    pre = kp.get('prefix')
    if pre in _post_piece and _post_piece[pre][0] is db.recs:
        return _post_piece[pre][1]
    best = None
    for ri in _kit_statics(db, kp):
        rid = db.recs[ri][1]
        if not re.search(r'post|pillar|column', rid.lower()):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or b[3] - b[0] > 110 or b[4] - b[1] > 110 or not kp['height'] * 0.8 <= b[5] - b[2] <= kp['height'] * 1.3:
            continue
        uses = kits.game_uses(db, rid.lower())
        score = (not DECOR_POST.search(rid.lower()), uses)
        if best is None or score > best[2]:
            best = (rid, b[2], score)
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


def _frames_shown(db, prefix):
    """Whether the game's own places in this style show where door frames meet walls (enough of them
    to go by), rather than the Workshop just guessing that they want a post there."""
    if not prefix:
        return False
    fr = [r for s, r in post_rules(db, prefix).items() if 1 in s[1] and 2 in s[1]]
    return sum(r['n'] for r in fr) >= 20


def grid_spot(db, ri, x, y, T, x0, y0, inside=()):
    """Where the game stands a column or post meant to show at (x, y): its own point on the grid of the
    floor pieces (every half tile from a tile's middle at x0, y0), in whichever of its four turns puts the
    model there. That matters for a column drawn well off its own point (Indoril's stands at a tile's
    corner when its point is in the tile's middle): centring its model on the spot puts it a little off
    the line of the walls, where the game's own places never have it. (x, y, turn) or None when no turn
    lands it within a hand's width of the spot, or its model is round its own point anyway. inside:
    points inside the rooms (tile middles); of turns that land it equally near, the one that stands it
    on the side of the corner toward them comes first. Returns every such turn, best first."""
    import builder
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    if not b or math.hypot((b[0] + b[3]) / 2, (b[1] + b[4]) / 2) < 24:
        return []
    step = T / 2.0
    out = []
    for q in range(4):
        rot = q * math.pi / 2
        cx, cy = builder._centred(db, ri, x, y, rot)
        gx, gy = x0 + round((cx - x0) / step) * step, y0 + round((cy - y0) / step) * step
        # (how far the model's middle then is from the spot, and from the rooms)
        err = math.hypot(gx - cx, gy - cy)
        if err >= 50:
            continue
        mx, my = x + (gx - cx), y + (gy - cy)
        room = min((math.hypot(px - mx, py - my) for px, py in inside), default=0)
        out.append((round(err / 8), room, gx, gy, rot))
    out.sort()
    return [o[2:] for o in out]


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
        rot = 0.0
        # (or on the grid, the way the game stands it, for one drawn off its own point)
        g = grid_spot(db, ri, v['x'], v['y'], tiles[0]['T'], tiles[0]['x'], tiles[0]['y'],
                      [(t['x'], t['y']) for t in tiles if abs(t['floor'] - v['floor']) < 32])
        if g:
            x, y, rot = g[0]
        out.append({'x': x, 'y': y, 'z': z, 'id': rid, 'floor': v['floor'], 'why': why, 'vx': v['x'], 'vy': v['y'],
                    'prefix': v['kit'].get('prefix'), 'rot': rot})

    objs = _narrow_tall(m, tiles[0]['H'], {t['ref'] for t in tiles})
    V = _vertices(tiles)
    _add_frames(V, m, tiles)
    for v in V.values():
        if not v['walls'] and not v.get('frames'):
            continue
        if _posts_near(v, objs):
            continue
        # (only for a style the game's own places show standing posts there: with nothing to go by,
        # a real slit at the join is found and covered as a hole anyway)
        if v.get('frames') and v['walls'] and _frames_shown(db, v['kit'].get('prefix')) and _frames_want_posts(db, v['kit'].get('prefix')):
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
    ([(id, pos)]). Holes only while the place has more of them per floor piece than the game's own
    places of the style (gapsurvey.py): the game's own interiors have slits at many joins, and
    posts and walls over every one of them is more than the game ever does."""
    # (the posts are never left to the game's rate here: the rate gate is for what the finder shows, and
    # the game's Gold Coast places "want" a post at a third of their tiles because they stand one at only
    # half their corners; the builder stands them where the style stands them, at a door frame's ends
    # and where walls meet. Measured 2026-10-22 on the user's Gold Coast house: 137 posts wanted and 19 of
    # 21 door jambs with bare ends while the gate held the builder back. Returns [(id, pos, scale, kind)])
    res = scan(db, cell_key, gate=())
    res['issues'] = [i for i in res['issues'] if i['kind'] in ('post', 'hole') and i['fixes']
                     and all(o.get('op') == 'place' for o in i['fixes'][0]['ops'])]
    if res['issues']:
        first = min(_rank(i) for i in res['issues'])       # (posts first; the builder looks again after)
        now = [i for i in res['issues'] if _rank(i) == first]
        # (when only a post or two is left to do, say round a stairwell, gaps well away from them go in
        # the same round, rather than a round each)
        if len(now) < 3:
            now += [i for i in res['issues'] if _rank(i) != first and all(
                math.hypot(i['x'] - j['x'], i['y'] - j['y']) > 384 or abs(i['z'] - j['z']) > 200 for j in now)]
        res['issues'] = now
    kind_at = {}
    for i in res['issues']:
        for o in i['fixes'][0]['ops']:
            kind_at.setdefault((o['id'].lower(), round(o['p'][0]), round(o['p'][1]), round(o['p'][2])), i['kind'])
    # (never a post standing in the passage between two tiles of one room: on the middle of an edge both
    # tiles are open across, where a seam's fix would put it)
    m = mapdata.cellmap(db, cell_key)
    tiles, _pre = _tiles(db, m)
    out = []
    for o in _fix_ops(res):
        if COLUMN_WORDS.search(o['id'].lower()) and _in_passage(tiles, o['p'][0], o['p'][1], o['p'][2]):
            continue
        out.append((o['id'], tuple(float(v) for v in o['p'][:6]), float(o.get('s', 1.0)),
                    kind_at.get((o['id'].lower(), round(o['p'][0]), round(o['p'][1]), round(o['p'][2])), 'hole')))
    return out


def joint_ops(db, cell_key):
    """For "Build from pieces", before its closing rounds: the joint survey's answers wherever what the
    builder laid is not what the game stands in that situation (a walled side piece with its addon and
    pillar in place of a loose wall beside a stairwell, say), as fixit.apply ops, one answer per edge."""
    import joints
    m = mapdata.cellmap(db, cell_key)
    tiles, prefix = _tiles(db, m)
    if not tiles or not prefix:
        return []
    ops = []
    for i in joints.issues(db, m, tiles, prefix):
        for op in i['fixes'][0]['ops']:
            if op['op'] in ('swap', 'delete') and any(o['op'] == op['op'] and o.get('ref') == op['ref'] for o in ops):
                continue
            if op['op'] == 'place' and any(o['op'] == 'place' and o['id'].lower() == op['id'].lower() and
                                           math.hypot(o['p'][0] - op['p'][0], o['p'][1] - op['p'][1]) < 24 and abs(o['p'][2] - op['p'][2]) < 24
                                           and abs(o['p'][5] - op['p'][5]) < 0.05 for o in ops):
                continue
            ops.append(op)
    return ops


def coplanar_drop(db, refs, kp):
    """For "Build from pieces", before its pieces are written: the indexes of the pieces in refs whose
    faces would lie in the same plane as a neighbour's, the way the user found them in the game: a plain
    floor sheet on a floor tile's own floor (two floors in one tile flicker), a loose wall along a side the
    tile walls itself (wall on wall), or a second loose wall on the line of the first. The duplicate is
    dropped; a dressing sheet the game itself lays on its floors (a tiled floor) is left as learnt."""
    import kits as _k
    T = kp['tile']
    H = kp['height']
    pieces = {p['id'].lower(): p for p in kp['pieces']}
    for p in kp.get('tall') or []:
        pieces.setdefault(p['id'].lower(), p)
    wall_ids = {w['id'].lower() for w in kp['walls']}
    tiles = []
    for n, item in enumerate(refs):
        rid, pos = item[0], item[1]
        p = pieces.get(str(rid).lower())
        if not p or (len(item) > 3 and abs(item[3] - 1.0) > 0.02):
            continue
        q = int(round(pos[5] / (math.pi / 2))) % 4
        tiles.append((n, pos[0], pos[1], pos[2] + p['zmin'], _k.rotate(p['lower'] if 'lower' in p else p['pattern'], q)))
    drop, walls_laid = set(), []
    for n, item in enumerate(refs):
        rid, pos = item[0], item[1]
        low = str(rid).lower()
        if low in pieces:
            continue
        ri = db.resolve_id(rid)
        b = mapdata.object_bounds(db, ri) if ri is not None else None
        if not b:
            continue
        w, d, h = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        if h <= 8 and min(w, d) >= 200 and 'floor' in low and 'tile' not in low:
            # a plain floor sheet on a tile's own floor
            bottom = pos[2] + b[2]
            if any(abs(tx - pos[0]) < 24 and abs(ty - pos[1]) < 24 and abs(fz - bottom) <= 1.0 and pat.get('floor', True) for _n, tx, ty, fz, pat in tiles):
                drop.add(n)
            continue
        if low in wall_ids:
            c, s = math.cos(pos[5]), math.sin(pos[5])
            bcx, bcy = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
            cx, cy = pos[0] + bcx * c + bcy * s, pos[1] - bcx * s + bcy * c
            thin_x = w < d
            along_x = abs(math.cos(pos[5])) > 0.7 if not thin_x else abs(math.sin(pos[5])) > 0.7
            z0 = pos[2] + b[2]
            # on a side a tile walls itself?
            on_wall = False
            for _n, tx, ty, fz, pat in tiles:
                if abs(fz - z0) > H * 0.6:
                    continue
                for side, (dx, dy) in STEP.items():
                    ex, ey = tx + dx * T / 2.0, ty + dy * T / 2.0
                    u = (cx - ex) * (-dy) + (cy - ey) * dx
                    dd = (cx - ex) * dx + (cy - ey) * dy
                    if abs(dd) <= T * 0.25 and abs(u) <= T * 0.4 and pat[side] == 'wall' and dd <= 4:
                        on_wall = True
                        break
                if on_wall:
                    break
            if on_wall:
                drop.add(n)
                continue
            # on the line of a loose wall laid already (the same orientation, within 8 units: the stair's cap
            # wall and its edge wall stood 6 apart on Reeking Pit 2's stairwell, one inside the other)
            for ox, oy, oz, oax in walls_laid:
                if oax == along_x and abs(oz - z0) < 4 and ((along_x and abs(oy - cy) <= 8 and abs(ox - cx) < T * 0.9) or (not along_x and abs(ox - cx) <= 8 and abs(oy - cy) < T * 0.9)):
                    drop.add(n)
                    break
            else:
                walls_laid.append((cx, cy, z0, along_x))
    return drop


def _in_passage(tiles, x, y, z):
    """Whether a point stands on the middle of an edge two floor tiles are open across (the way from one
    to the other), rather than at a corner or on a wall."""
    for t in tiles:
        if abs(t['floor'] - z) > 160:
            continue
        h = t['T'] / 2.0
        for s in kits.SIDES:
            dx, dy = STEP[s]
            ex, ey = t['x'] + dx * h, t['y'] + dy * h
            if abs(x - ex) > 40 or abs(y - ey) > 40:
                continue
            pat = t.get('spot') or t['pat']
            if pat[s] != 'open':
                return False
            o = _neighbour(tiles, t, s)
            if not o:
                return False
            opat = o.get('spot') or o['pat']
            return opat[kits.SIDES[(kits.SIDES.index(s) + 2) % 4]] == 'open'
    return False


COLUMN_WORDS = re.compile(r'post|pillar|column')
_USES_POSTS = {}


def uses_posts(db, prefix):
    """Whether the game's own places in this style stand posts or columns at a fair share of their
    corners (Imperial Gold Coast, the Common styles), rather than seldom (most others). A style no
    place uses goes by all of them together: seldom."""
    if prefix in _USES_POSTS and _USES_POSTS[prefix][0] is db.recs:
        return _USES_POSTS[prefix][1]
    import jointsurvey
    try:
        stats, places = jointsurvey.survey(db, prefix) if prefix else ({}, 0)
    except Exception:
        stats, places = {}, 0
    n = sum(v['n'] for v in stats.values())
    w = sum(v['with'] for v in stats.values())
    res = bool(places >= 3 and n >= 50 and w / float(n) >= 0.12)
    _USES_POSTS[prefix] = (db.recs, res)
    return res


def spare_columns(db, cell_key, keys=None, trace=False):
    """Posts and columns that close nothing: taken away, no see-through hole opens round where they
    stand, and it isn't a corner where the game itself always stands one in this style. keys: only
    these refs (the ones "Build from pieces" just put in); else every loose post or column of the place.
    Returns the refs to take out, worked out one after another (two side by side may each look needed
    while the other stands, so each is tried with the ones already gone left out)."""
    import seethrough
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        return []
    tiles, _pre = _tiles(db, m)
    if not tiles:
        return []
    tile_refs = {t['ref'] for t in tiles}
    floors = [bx for r in m['refs'] if r['k'] not in tile_refs and (r.get('arch') or r['type'] in ('STAT', 'ACTI'))
              for bx in [_world_box(r)] if bx and (bx[3] - bx[0]) * (bx[4] - bx[1]) >= 128 * 96]
    T, H = tiles[0]['T'], tiles[0]['H']
    cands = []
    for r in m['refs']:
        if r['k'] in tile_refs or r['type'] != 'STAT' or not COLUMN_WORDS.search(r['id'].lower()):
            continue
        if keys is not None and r['k'] not in keys:
            continue
        bx = _world_box(r)
        if bx and bx[3] - bx[0] <= 136 and bx[4] - bx[1] <= 136:
            cands.append((r, bx))
    # (crowded ones first: where three stand on one corner, the extra ones are likeliest)
    crowd = lambda c: -sum(1 for o, ob in cands if o is not c[0] and abs((ob[0] + ob[3]) / 2 - (c[1][0] + c[1][3]) / 2) < 48
                           and abs((ob[1] + ob[4]) / 2 - (c[1][1] + c[1][4]) / 2) < 48 and abs(ob[2] - c[1][2]) < 64)
    cands.sort(key=crowd)
    gone = set()
    for r, bx in cands:
        cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
        near = [t for t in tiles if abs(t['x'] - cx) <= T and abs(t['y'] - cy) <= T and t['floor'] - 16 <= bx[2] + 16 and bx[2] < t['floor'] + H]
        if not near:
            continue
        m2 = dict(m, refs=[x for x in m['refs'] if x['k'] not in gone and x['k'] != r['k']])
        try:
            hs = _see_holes(db, m2, tiles, floors, near)
        except Exception as e:
            print('spare columns:', e)
            return sorted(gone)
        R = 72
        if trace is not False:
            trace.append('%s at %.0f,%.0f z %.0f..%.0f near %d tiles: holes %s' % (r['id'], cx, cy, bx[2], bx[5], len(near),
                         [(h['kind'], round(h['x']), round(h['y']), round(h['z'])) for h in hs]))
        if any(h['kind'] == 'wall' and math.hypot(h['x'] - cx, h['y'] - cy) < R and h['z'] - 8 <= bx[5] and h['z'] + 8 >= bx[2] for h in hs):
            continue                                   # (it covers a slit: it stays)
        # a corner the game always stands a post on (in this style), left without one; (a post where a
        # door frame meets a wall only counts when the game's own places show the style does that: with
        # nothing to go by, it stays only if it covers a hole, like any other)
        if any(math.hypot(p['vx'] - cx, p['vy'] - cy) < 40 and abs(p['floor'] - bx[2]) < H and
               (p['why'] == 'game' or _frames_shown(db, p.get('prefix'))) for p in missing_posts(db, m2, tiles)):
            continue
        gone.add(r['k'])
    return sorted(gone)


def door_frame(kp):
    """The style's full-width door frame (Hlaalu's door jamb, Redguard's door wall), or None."""
    return next((j for j in kp.get('jambs', []) if not j.get('load') and j['width'] >= kp['tile'] * 0.9), None)


def frameless_doorways(db, cell_key):
    """Doorways between rooms built as a bare gap in the wall, in a style that has a full-width door
    frame (a place built before the Workshop knew the frame): a one-tile opening where the wall
    carries on at both ends. The frames to stand there: [{'op': 'place', ...}]."""
    import builder
    m = mapdata.cellmap(db, cell_key)
    tiles, _pre = _tiles(db, m)
    if not tiles:
        return []
    T = tiles[0]['T']
    at = {}
    for t in tiles:
        at.setdefault((round(t['x'] / T), round(t['y'] / T), round(t['floor'] / 64)), t)
    pat = lambda t: t.get('spot') or t['pat']
    framed = [((bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, bx[2]) for r in m['refs']
              if re.search(r'jamb|frame|doorway|door', r['id'].lower()) for bx in [_world_box(r)] if bx]
    ops, seen = [], set()
    for (gx, gy, gf), t in at.items():
        fr = door_frame(t['kit'])
        if not fr:
            continue
        for s in ('E', 'N'):
            dx, dy = STEP[s]
            o = at.get((gx + dx, gy + dy, gf))
            if not o or pat(t)[s] != 'open' or pat(o)[OPPOSITE[s]] != 'open':
                continue
            # the wall goes on past both ends of the opening (beside it on one side or the other)
            ends = ('N', 'S') if s in 'EW' else ('E', 'W')
            walled = 0
            for e in ends:
                ex, ey = STEP[e]
                a, b = at.get((gx + ex, gy + ey, gf)), at.get((gx + dx + ex, gy + dy + ey, gf))
                if (a and pat(a)[s] == 'wall') or (b and pat(b)[OPPOSITE[s]] == 'wall'):
                    walled += 1
            if walled < 2:
                continue
            mx, my = t['x'] + dx * T / 2, t['y'] + dy * T / 2
            if any(math.hypot(f[0] - mx, f[1] - my) < 48 and abs(f[2] - t['floor']) < 160 for f in framed):
                continue                                   # (a frame or a door stands there already)
            if (round(mx), round(my), gf) in seen:
                continue
            seen.add((round(mx), round(my), gf))
            rot = 0 if (s in 'EW') == fr['thin_x'] else math.pi / 2
            px, py = builder._centred(db, fr['ri'], mx, my, rot)
            ops.append({'op': 'place', 'id': fr['id'], 'p': [round(px, 2), round(py, 2), round(t['floor'] - fr['zmin'], 2), 0, 0, rot]})
    return ops


def wall_holes(db, cell_key):
    """The see-through holes in a place's walls as it is now, seen from everywhere: [(x, y, z)]."""
    m = mapdata.cellmap(db, cell_key)
    tiles, _pre = _tiles(db, m)
    if not tiles:
        return []
    tile_refs = {t['ref'] for t in tiles}
    floors = [bx for r in m['refs'] if r['k'] not in tile_refs and (r.get('arch') or r['type'] in ('STAT', 'ACTI'))
              for bx in [_world_box(r)] if bx and (bx[3] - bx[0]) * (bx[4] - bx[1]) >= 128 * 96]
    return [(h['x'], h['y'], h['z']) for h in _see_holes(db, m, tiles, floors, tiles) if h['kind'] == 'wall']


def column_box(r):
    """Where a placed post or column stands: its box, from the cell map's entry."""
    return _world_box(r)


def _see_holes(db, m, tiles, floors, spots):
    """The see-through holes seen from these tiles only (the rest of the place as it is)."""
    import seethrough
    frames = [bx for r in m['refs'] if re.search(r'jamb|frame|doorway|arch|_dj(_|\d|$)', r['id'].lower())
              for bx in [_world_box(r)] if bx]

    def walled(t, s):
        if (t.get('spot') or t['pat'])[s] != 'open':
            return True
        o = _neighbour(tiles, t, s)
        if isinstance(o, dict) and (o.get('spot') or o['pat'])[OPPOSITE[s]] != 'open':
            return True
        x0, y0, x1, y1 = _edge(t, s)
        for bx in frames:
            if s in 'NS' and bx[1] - 40 <= y0 <= bx[4] + 40 and min(bx[3], x1) - max(bx[0], x0) >= 32:
                return True
            if s in 'EW' and bx[0] - 40 <= x0 <= bx[3] + 40 and min(bx[4], y1) - max(bx[1], y0) >= 32:
                return True
        return False
    # (the whole building, for following where a view goes; looking out only from the spots asked about)
    seen, uniq = set(), []
    for t in tiles:
        if t['ref'] in seen:
            continue
        seen.update(t.get('mates', []))
        uniq.append(t)
    want = {t['ref'] for t in spots}
    only = {t['ref'] for t in uniq if t['ref'] in want or any(x in want for x in t.get('mates', []))}
    hs, _sc = seethrough.holes(db, m, uniq, lambda t, s: _neighbour(tiles, t, s, floors), lambda t: _above(tiles, t), (),
                               walled, floors, only=only)
    return hs


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


def _railed(near, t, side):
    """A railing stands on this side of the tile at its floor: the edge of a gallery looking down into a
    two-storey hall (the Gold Coast's Railing_01/02, the Hlaalu manor's LedgeRailSide_01, Redoran's
    railing_01 across an upper doorway), which the game leaves open on purpose."""
    x0, y0, x1, y1 = _edge(t, side)
    ex, ey = (x0 + x1) / 2, (y0 + y1) / 2
    for r in near:
        low = r['id'].lower()
        if 'rail' not in low or 'trail' in low:
            continue
        bx = _world_box(r)
        if not bx:
            continue
        if bx[0] - 24 <= ex <= bx[3] + 24 and bx[1] - 24 <= ey <= bx[4] + 24 and t['floor'] - 40 <= bx[2] <= t['floor'] + 100:
            return True
    return False


def _stair_beyond(near, t, side, tile_refs=()):
    """A staircase just past this side of the tile (its run, or the landing it climbs to or from): a wall
    there would stand across the stairs. Looked for from the floor the tile is on up to a storey over the
    stair's top, since the top step of a flight ends level with the floor it comes out on."""
    dx, dy = STEP[side]
    x0, y0, x1, y1 = _edge(t, side)
    ex, ey = (x0 + x1) / 2, (y0 + y1) / 2
    probes = [(ex + dx * k + ax * u, ey + dy * k + ay * u) for k in (24, 64, 128) for u in (-t['T'] * 0.3, 0.0, t['T'] * 0.3)
              for ax, ay in [(-dy, dx)]]
    for r in near:
        if r['k'] in tile_refs or 'stair' not in r['id'].lower():
            continue
        bx = _world_box(r)
        if not bx or bx[2] > t['floor'] + 64 or bx[5] + t['H'] < t['floor'] + 30:
            continue
        if any(bx[0] - 8 <= px <= bx[3] + 8 and bx[1] - 8 <= py <= bx[4] + 8 for px, py in probes):
            return True
    return False


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
    for ri in _kit_statics(db, kp):
        rid = db.recs[ri][1]
        if db.recs[ri][0] != 'STAT' or not re.search(r'post|pillar|column|support|beam', rid.lower()):
            continue
        b = mapdata.object_bounds(db, ri)
        if not b or b[3] - b[0] > 136 or b[4] - b[1] > 136 or not kp['height'] * 0.5 <= b[5] - b[2] <= kp['height'] * 1.5:
            continue
        out.append((kits.game_uses(db, rid.lower()), rid, ri, b))
    # (the plain ones, most used first; a decorative one, a glass pillar say, only in a style with no other)
    plain = [x for x in out if not DECOR_POST.search(x[1].lower())]
    out = sorted(plain or out, key=lambda x: -x[0])
    res = [(rid, ri, b) for _n, rid, ri, b in out[:limit]]
    if not res:
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
    cands, slid, pairs, centred, between = [], [], [], [], []
    wall_ids = {w['id'].lower() for w in t['kit']['walls']}
    uc = (hole['u0'] + hole['u1']) / 2

    def on_floor(r):
        """Does this piece stand on the tile's floor? (By its box: some columns have their origin at the
        top or the middle, not the foot.)"""
        bx = _world_box(r)
        return bool(bx) and abs(bx[2] - t['floor']) < t['H'] * 0.6

    def stands(rid, x, y, within=24):
        """Is this piece already standing (nearly) there? A second one on top of it covers nothing more."""
        return any(r['id'].lower() == rid.lower() and math.hypot(r['p'][0] - x, r['p'][1] - y) < within and on_floor(r)
                   for r in near)

    def crowd(x, y, within=None):
        """How many posts or columns stand at this spot already (within a third of a tile, on this floor):
        two is as many as one corner takes; a third in a row is what you'd take out again by hand."""
        return sum(1 for r in near if r['k'] not in tile_refs and r['type'] == 'STAT' and COLUMN_WORDS.search(r['id'].lower())
                   and math.hypot(r['p'][0] - x, r['p'][1] - y) < (within or t['T'] / 3) and on_floor(r))

    def crowded(c):
        """A fix that would stand a column where two already stand within a quarter tile of it."""
        return any(o.get('op') == 'place' and COLUMN_WORDS.search(o['id'].lower()) and crowd(o['p'][0], o['p'][1], t['T'] / 4) >= 2
                   for o in c['ops'])
    for u in spots:
        x, y = ex + ax * u, ey + ay * u
        here = crowd(x, y)
        if here >= 2:
            continue                                    # (no third column at one corner)
        for rid, ri, b in _narrow_pieces(db, t['kit']):
            # (how wide the column is: a second one closer than that would stand inside the first, as
            # happened with a stone pillar at a corner and another over the slit 36 units along)
            wide = max(b[3] - b[0], b[4] - b[1])
            near_w = max(24, wide * 0.75)
            # first on the grid, the way the game stands it (a column drawn off its own point lines up
            # with the walls there and not when centred on the spot; see grid_spot)
            # (nor a column of any kind that close: a stair's own wooden post beside a stone pillar)
            gs = [g for g in grid_spot(db, ri, x, y, t['T'], t['x'], t['y'], [(t['x'], t['y'])])[:2]
                  if not stands(rid, g[0], g[1], near_w) and not crowd(g[0], g[1], near_w)]
            for gx, gy, grot in gs:
                cands.append({'label': 'Add %s' % rid,
                              'ops': [{'op': 'place', 'id': rid, 'p': [round(gx, 2), round(gy, 2), t['floor'] - b[2], 0, 0, grot]}]})
            # where one on the grid leaves a slit (the top of a stairwell, say): what you'd do by hand, so
            # it still lines up with the walls and reads as one solid piece rather than one off the line:
            # slid along the wall's own line over the slit, or a second one beside it on that line (or on
            # the grid), a little overlap and all
            # (a pair only where none stands yet: with one there already, a second beside it is the pair)
            z_ = t['floor'] - b[2]
            for gx, gy, grot in gs:
                for d in (16, -16, 32, -32, 48, -48):
                    sx, sy = gx + ax * d, gy + ay * d
                    if stands(rid, sx, sy, near_w) or crowd(sx, sy, near_w):
                        continue
                    slid.append({'label': 'Add %s' % rid,
                                 'ops': [{'op': 'place', 'id': rid, 'p': [round(sx, 2), round(sy, 2), z_, 0, 0, grot]}]})
                    if abs(d) >= max(32, wide - 2) and not here:
                        pairs.append({'label': 'Add two %s, lined up' % rid,
                                      'ops': [{'op': 'place', 'id': rid, 'p': [round(gx, 2), round(gy, 2), z_, 0, 0, grot]},
                                              {'op': 'place', 'id': rid, 'p': [round(sx, 2), round(sy, 2), z_, 0, 0, grot]}]})
            for i_, (gx, gy, grot) in enumerate(gs if not here else []):
                for hx, hy, hrot in gs[i_ + 1:]:
                    if math.hypot(hx - gx, hy - gy) < wide - 2:
                        continue                        # (the two would stand inside each other)
                    pairs.append({'label': 'Add two %s, lined up' % rid,
                                  'ops': [{'op': 'place', 'id': rid, 'p': [round(gx, 2), round(gy, 2), z_, 0, 0, grot]},
                                          {'op': 'place', 'id': rid, 'p': [round(hx, 2), round(hy, 2), z_, 0, 0, hrot]}]})
            # a slit just along from the corner (the 8 units a Common room corner's model stops short):
            # one column between the corner and the slit covers both, where two would stand in each
            # other (a stone pillar at the corner and another over the slit, 36 units along)
            if abs(u) >= h - 1 and 0 < abs(uc - u) < 56 and not gs:
                um = (u + uc) / 2
                for rot in (0.0, math.pi / 2):
                    cx, cy = builder._centred(db, ri, ex + ax * um, ey + ay * um, rot)
                    if stands(rid, cx, cy, near_w) or crowd(cx, cy, near_w):
                        continue
                    between.append({'label': 'Add %s (over the corner and the slit)' % rid,
                                    'ops': [{'op': 'place', 'id': rid, 'p': [round(cx, 2), round(cy, 2), t['floor'] - b[2], 0, 0, rot]}]})
            # failing those, centred on the spot, every turn: some are half columns made to stand against a
            # wall, seen from the front only
            for rot in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
                cx, cy = builder._centred(db, ri, x, y, rot)
                if stands(rid, cx, cy, near_w) or crowd(cx, cy, near_w):
                    continue
                centred.append({'label': 'Add %s' % rid,
                                'ops': [{'op': 'place', 'id': rid, 'p': [round(cx, 2), round(cy, 2), t['floor'] - b[2], 0, 0, rot]}]})
    cands = [c for c in between + cands + slid + pairs + centred if not crowded(c)]
    # before any of those: what the game stands at an edge in this situation (the joint survey), when it
    # has a strong answer and what stands here is not it: a walled side piece with its addon and pillar
    # in place of a bare wall or a post
    try:
        import joints
        jf = joints.fix_for(db, {'refs': list(near)}, None, t, hole['side'])
        if jf:
            cands.insert(0, jf)
    except Exception as e:
        print('joint survey:', e)
    # is anything of the building just past this side (a hall piece that isn't a whole tile, stairs, a
    # door)? Then nothing goes there: a wall "outside" would stand across the way through
    nx_, ny_ = STEP[hole['side']]
    probes = [(ex + ax * u + nx_ * k, ey + ay * u + ny_ * k, t['floor'] + 60)
              for u in (hole['u0'], (hole['u0'] + hole['u1']) / 2, hole['u1'], 0.0) for k in (24, 64)]
    # (a staircase there counts from its foot to a storey over its top: the top step of a flight ends
    # level with the floor it comes out on, and a wall across it would block the stairs)
    occupied = _stair_beyond(near, t, hole['side'], tile_refs)
    for r in near if not occupied else []:
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
        if o.get('tall'):
            continue          # (not a 764-tall hall piece grown by 3%: 23 units taller and wider, a whole second hall wall)
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
        # (not a copy of a loose wall slid along its own line: it would lie mostly on top of the first,
        # and a third on that. The slit at a loose wall's end is for a post, below. Nor a third column
        # at a corner that has two)
        if r['id'].lower() in wall_ids or stands(r['id'], cx, cy, 6):
            continue
        if COLUMN_WORDS.search(r['id'].lower()) and (crowd(cx, cy) >= 2 or crowd(cx, cy, t['T'] / 4) >= 2):
            continue
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
    # a style whose own places seldom stand a post at a corner (most of them: see jointsurvey.py) gets
    # its slits closed some other way first, and a post only when nothing else will do. Not at the end
    # of a loose wall, though: a wall piece narrower than the tile (Indoril's 226 in 256) leaves a slit
    # at each end that the game's own places fill with the style's column
    def wall_end():
        for r in near:
            if r['id'].lower() not in wall_ids:
                continue
            bx = _world_box(r)
            if not bx or bx[2] > t['floor'] + t['H'] * 0.6 or bx[5] < t['floor'] + 20:
                continue
            ends = [(bx[0], (bx[1] + bx[4]) / 2), (bx[3], (bx[1] + bx[4]) / 2)] if bx[3] - bx[0] >= bx[4] - bx[1] \
                else [((bx[0] + bx[3]) / 2, bx[1]), ((bx[0] + bx[3]) / 2, bx[4])]
            if any(math.hypot(px - hole['x'], py - hole['y']) < 48 for px, py in ends):
                return True
        return False
    if not uses_posts(db, t['kit'].get('prefix')) and not wall_end():
        is_post = lambda c: c['label'].startswith('Add ') and COLUMN_WORDS.search(c['label'].lower())
        cands = [c for c in cands if not is_post(c)] + [c for c in cands if is_post(c)]
    good, best = [], None
    for n_, c in enumerate(cands):
        # (with one good fix in hand, a few more to choose from, not every column and turn there is)
        if good and n_ >= 40 or n_ >= 220:
            break
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


def _opening_issues(db, m, tiles, floors):
    """The edges of a stairwell's opening on the floor the stairs come out on: no tile stands there, so
    the tile-by-tile scan never looks out from it. An edge with no floor piece beyond it, where rays
    from the tiles round the opening get out to the void, is a hole (the stair piece's own back wall,
    when it has one at that height, stops them and nothing is reported)."""
    import seethrough
    out = []
    stairs = [r for r in m['refs'] if r.get('ri') is not None and r['type'] == 'STAT' and re.search(r'stair|ramp', r['id'].lower())]
    if not stairs or not tiles:
        return out
    sc = None
    for r in stairs:
        pre = kits.kit_prefix(r['id'])
        info = kits.stairs(db, pre) if pre and pre in kits.kits(db) else None
        sp = next((p for p in (info or {}).get('pieces', []) if p['id'].lower() == r['id'].lower()), None)
        if not sp or sp.get('len', 1) > 1 or 'cx' in sp:
            continue
        kp = kits.kit_pieces(db, pre)
        T, H = kp['tile'], kp['height']
        upper = r['p'][2] + sp['z_low'] + kp['zmin'] + sp['rise']
        ox, oy = r['p'][0], r['p'][1]
        if any(abs(t['x'] - ox) < 24 and abs(t['y'] - oy) < 24 and abs(t['floor'] - upper) < 64 for t in tiles):
            continue                                  # (floored over: no opening)
        near = [t for t in tiles if abs(t['floor'] - upper) < 64 and abs(t['x'] - ox) <= T * 1.1 and abs(t['y'] - oy) <= T * 1.1
                and not (abs(t['x'] - ox) < 24 and abs(t['y'] - oy) < 24)]
        if not near:
            continue
        for s, (dx, dy) in STEP.items():
            bx_, by_ = ox + dx * T, oy + dy * T
            if any(abs(t['x'] - bx_) < 24 and abs(t['y'] - by_) < 24 and abs(t['floor'] - upper) < 64 for t in tiles):
                continue
            if any(b[0] <= bx_ <= b[3] and b[1] <= by_ <= b[4] and b[2] <= upper + 64 and b[5] >= upper - 16 for b in floors):
                continue
            if sc is None:
                sc = seethrough.place_scene(db, m)
            ex, ey = ox + dx * T / 2, oy + dy * T / 2
            ax, ay = abs(dy), abs(dx)
            rays = []
            for t in near:
                eye = (t['x'], t['y'], t['floor'] + min(H * 0.45, 128))
                for k in range(-4, 5):
                    u = k * T * 0.1
                    for j in range(6):
                        tgt = (ex + ax * u, ey + ay * u, upper + 20 + (H - 40) * (j + 0.5) / 6.0)
                        d = (tgt[0] - eye[0], tgt[1] - eye[1], tgt[2] - eye[2])
                        L = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) or 1.0
                        d = (d[0] / L, d[1] / L, d[2] / L)
                        if not sc.blocked(eye, d, 4000):
                            rays.append((eye, d, 4000))
            if len(rays) < 6:
                continue
            wall = (kp['walls'] and None) or kits.family_wall(db, pre)
            fixes = []
            if kp['walls'] or wall:
                t_ = {'x': ox, 'y': oy, 'floor': upper, 'T': T, 'H': H, 'kit': kp}
                if kp['walls']:
                    fixes = [_wall_fix(db, t_, [s])] if _wall_fix(db, t_, [s]) else []
                else:
                    import builder
                    rid_, pos_, _e = builder._loose_wall_ref(db, wall, ox, oy, s, upper, T)
                    fixes = [{'label': 'Add a wall piece (%s)' % rid_, 'ops': [{'op': 'place', 'id': rid_, 'p': list(pos_)}]}]
            out.append({'kind': 'hole', 'side': s, 'ref': r['k'], 'id': r['id'], 'x': ex, 'y': ey, 'z': upper + H / 2,
                        'text': 'The stairwell\'s opening looks out onto nothing here: the void shows through', 'fixes': fixes})
    return out


# How many clips and coplanar face pairs the game's own places show per 100 architecture pieces, by the kind
# of pair (measured 2026-10-21 on 18 Common stone, Common plain and Gold Coast places with stairs, 1,633
# pieces: posts sunk into the wall ends they cover, tiles overlapping at their seams, a post's face flush
# with a wall). A place is only told about a kind it shows more than twice as often.
CLASH_BASELINE = {('clip', 'post-tile'): 37.0, ('zfight', 'post-tile'): 20.0, ('clip', 'tile-tile'): 14.5,
                  ('zfight', 'post-wall'): 11.2, ('zfight', 'tile-tile'): 11.0, ('clip', 'tile-wall'): 9.6,
                  ('zfight', 'post-stair'): 4.8, ('clip', 'post-stair'): 4.4, ('clip', 'wall-wall'): 3.9,
                  ('zfight', 'tile-wall'): 1.4, ('clip', 'stair-tile'): 0.9, ('zfight', 'post-post'): 0.8}


def _pair_kind(i):
    if i.get('pair'):
        return i['pair']                 # (a kind with no rate of the game's: always listed)
    tag = lambda s: 'post' if COLUMN_WORDS.search(s) else 'stair' if 'stair' in s else 'wall' if re.search(r'_wall|wall_', s) else 'tile'
    return '-'.join(sorted((tag(i['id'].lower()), tag((i.get('other') or '').lower()))))


def clash_issues(db, m, tiles=None):
    """The user's two acceptance rules for closure pieces, as the finder's lines: 'clip' (a piece's mesh
    cuts into a neighbouring piece's solid: a post sunk through a beam, a wall through the stair) and
    'zfight' (faces of two pieces lying in one plane within a unit of each other and overlapping, which
    flicker in the game). Looked for between every pair of architecture pieces whose boxes overlap by
    more than a seam, with the known good stack left out: two room pieces on one spot share their floor
    and ceiling by design (the game's own corners, the user's hand fix), only their walls must differ."""
    import seethrough
    if tiles is None:
        tiles, _p = _tiles(db, m)
    refs = [r for r in m['refs'] if r.get('ri') is not None and r['type'] == 'STAT' and r.get('arch')]
    if len(refs) < 2:
        return []
    sc = seethrough.place_scene(db, m)
    boxes = {r['k']: _world_box(r) for r in refs}
    tile_ref = {t['ref'] for t in tiles}
    spot_of = {t['ref']: (round(t['x'] / 8), round(t['y'] / 8), round(t['floor'] / 8)) for t in tiles}
    is_tile = lambda r: r['k'] in tile_ref
    # the world triangles of a piece, with their planes
    tri_cache = {}

    def tris_of(k):
        if k in tri_cache:
            return tri_cache[k]
        out = []
        for n in range(*sc.of_ref.get(k, (0, 0))):
            x0, y0, z0, ax, ay, az, bx, by, bz = sc.tris[n]
            nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
            L = math.sqrt(nx * nx + ny * ny + nz * nz)
            if L < 1e-6:
                continue
            nx, ny, nz = nx / L, ny / L, nz / L
            if (nx, ny, nz) < (0, 0, 0):            # (one sign for both faces of a plane)
                nx, ny, nz = -nx, -ny, -nz
            d = nx * x0 + ny * y0 + nz * z0
            xs = (x0, x0 + ax, x0 + bx)
            ys = (y0, y0 + ay, y0 + by)
            zs = (z0, z0 + az, z0 + bz)
            out.append(((nx, ny, nz), d, (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)), L / 2.0))
        tri_cache[k] = out
        return out

    def plane_key(n, d):
        return (round(n[0], 2), round(n[1], 2), round(n[2], 2), int(round(d)))

    def overlap_area(b1, b2, n):
        # (the two triangles' boxes, projected along the plane's normal: how much they share)
        axes = sorted(range(3), key=lambda i: abs(n[i]))[:2]
        area = 1.0
        for i in axes:
            w = min(b1[i + 3], b2[i + 3]) - max(b1[i], b2[i])
            if w <= 0:
                return 0.0
            area *= w
        return area
    out = []
    seen = set()
    for i, a in enumerate(refs):
        A = boxes[a['k']]
        if not A:
            continue
        for b in refs[i + 1:]:
            B = boxes[b['k']]
            if not B:
                continue
            ox = min(A[3], B[3]) - max(A[0], B[0])
            oy = min(A[4], B[4]) - max(A[1], B[1])
            oz = min(A[5], B[5]) - max(A[2], B[2])
            if ox < 12 or oy < 12 or oz < 4:
                continue
            stacked = is_tile(a) and is_tile(b) and spot_of.get(a['k']) == spot_of.get(b['k'])
            ta, tb = tris_of(a['k']), tris_of(b['k'])
            if not ta or not tb:
                continue
            region = (max(A[0], B[0]) - 2, max(A[1], B[1]) - 2, max(A[2], B[2]) - 2, min(A[3], B[3]) + 2, min(A[4], B[4]) + 2, min(A[5], B[5]) + 2)
            inside = lambda bx: not (bx[3] < region[0] or bx[0] > region[3] or bx[4] < region[1] or bx[1] > region[4] or bx[5] < region[2] or bx[2] > region[5])
            # --- coplanar faces
            planes = {}
            for n, d, bx, area in tb:
                if inside(bx) and area >= 16:
                    planes.setdefault(plane_key(n, d), []).append((n, d, bx))
            hits, where = 0, None
            for n, d, bx, area in ta:
                if not inside(bx) or area < 16:
                    continue
                if stacked and abs(n[2]) > 0.99:
                    continue                     # (floor and ceiling of two pieces on one spot: by design)
                k0 = plane_key(n, d)
                for dd in (-1, 0, 1):
                    for n2, d2, bx2 in planes.get(k0[:3] + (k0[3] + dd,), ()):
                        if abs(d - d2) <= 1.0 and overlap_area(bx, bx2, n) >= 64:
                            hits += 1
                            if where is None:
                                where = ((bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, (bx[2] + bx[5]) / 2)
                            break
                    else:
                        continue
                    break
            if hits >= 2:
                # (a flat floor sheet a tile across lying on a floor piece's own floor at the same height is
                # never the kit's joinery: the user's "two floor pieces in one tile" on Reeking Pit 2, which the
                # game's tile-on-tile rate had hidden; such a pair is always listed, see scan)
                def flat_sheet(r_, bx_):
                    return bx_[5] - bx_[2] <= 8 and min(bx_[3] - bx_[0], bx_[4] - bx_[1]) >= 200 and not is_tile(r_)
                sheet_on_tile = (flat_sheet(a, A) and is_tile(b)) or (flat_sheet(b, B) and is_tile(a))
                # the fixes the user makes by hand: the lesser piece (the smaller, or the one that isn't a
                # floor tile) set a hair lower so the faces no longer share a plane, or taken out when it is a
                # second floor in one tile
                vol = lambda bx: (bx[3] - bx[0]) * (bx[4] - bx[1]) * max(1.0, bx[5] - bx[2])
                lesser = b if is_tile(a) and not is_tile(b) else a if is_tile(b) and not is_tile(a) else (a if vol(A) <= vol(B) else b)
                lp = list(lesser['p'])
                fixes = [{'label': 'Set %s a hair lower' % lesser['id'],
                          'ops': [{'op': 'move', 'ref': lesser['k'], 'p': [lp[0], lp[1], lp[2] - 1.0, lp[3], lp[4], lp[5]]}]}]
                if sheet_on_tile:
                    sheet = a if flat_sheet(a, A) else b
                    fixes.insert(0, {'label': 'Take out %s (a second floor in the tile)' % sheet['id'], 'ops': [{'op': 'delete', 'ref': sheet['k']}]})
                out.append({'kind': 'zfight', 'ref': a['k'], 'id': a['id'], 'other': b['id'], 'other_ref': b['k'],
                            'x': where[0], 'y': where[1], 'z': where[2], 'n_faces': hits, 'pair': 'sheet-tile' if sheet_on_tile else None,
                            'text': ('A floor sheet lies on this piece\'s own floor (%s on %s): two floors in one tile flicker' % (a['id'], b['id'])
                                     if sheet_on_tile else 'Faces of %s and %s lie in one plane here (%d): they would flicker' % (a['id'], b['id'], hits)),
                            'fixes': fixes})
            # --- one piece's mesh cutting into the other's solid: points on the closure-like piece's faces
            # that fall inside the other's mesh (a ray straight up from the point crosses the other's
            # faces an odd number of times), deep enough to be no seam
            if stacked or (is_tile(a) and is_tile(b)):
                continue
            for p, q in ((a, b), (b, a)) if not (is_tile(a) or is_tile(b)) else (((b, a),) if is_tile(a) else ((a, b),)):
                if (p['k'], q['k']) in seen:
                    continue
                seen.add((p['k'], q['k']))
                tp = [t for t in tris_of(p['k']) if inside(t[2]) and t[3] >= 16]
                tq = [(x, y, z, ax, ay, az, bx, by, bz) for n_ in range(*sc.of_ref.get(q['k'], (0, 0)))
                      for (x, y, z, ax, ay, az, bx, by, bz) in [sc.tris[n_]]
                      if not (max(x, x + ax, x + bx) < region[0] or min(x, x + ax, x + bx) > region[3] or
                              max(y, y + ay, y + by) < region[1] or min(y, y + ay, y + by) > region[4])]
                if not tp or not tq:
                    continue
                buried = 0
                for n, d, bx, area in tp[:400]:
                    px, py, pz = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, (bx[2] + bx[5]) / 2
                    if px < region[0] + 3 or px > region[3] - 3 or py < region[1] + 3 or py > region[4] - 3:
                        continue
                    above = below = 0
                    for (x, y, z, ax, ay, az, bx2, by2, bz2) in tq:
                        # the point's xy inside the triangle's xy projection
                        det = ax * by2 - ay * bx2
                        if abs(det) < 1e-9:
                            continue
                        u = ((px - x) * by2 - (py - y) * bx2) / det
                        v = (ax * (py - y) - ay * (px - x)) / det
                        if u < 0 or v < 0 or u + v > 1:
                            continue
                        tz = z + u * az + v * bz2
                        if tz > pz + 3:
                            above += 1
                        elif tz < pz - 3:
                            below += 1
                    if above % 2 == 1 and below % 2 == 1:
                        buried += 1
                        if buried >= 3:
                            break
                if buried >= 3:
                    out.append({'kind': 'clip', 'ref': p['k'], 'id': p['id'], 'other': q['id'], 'other_ref': q['k'],
                                'x': (region[0] + region[3]) / 2, 'y': (region[1] + region[4]) / 2, 'z': (region[2] + region[5]) / 2,
                                'text': '%s cuts into %s here' % (p['id'], q['id']), 'fixes': []})
    return out


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
        if (t['ref'], hole['side']) in gap_sides or hole['side'] in t.get('railed', ()):
            continue                      # (a railed gallery edge looks over the railing on purpose)
        fixes = _hole_fixes(db, sc, hole, m['refs'], {x['ref'] for x in tiles}, spots)
        if fixes:
            planned += fixes[0]['ops']
        out.append({'kind': 'hole', 'side': hole['side'], 'ref': t['ref'], 'id': t['id'],
                    'x': hole['x'], 'y': hole['y'], 'z': hole['z'],
                    'text': ('Pieces don\'t meet here: the void shows through' if hole['void'] else
                             'Pieces don\'t meet here: a slit into the next room'),
                    'fixes': fixes})
    return out


def scan(db, cell_key, everything=False, clashes=False, gate=('gap', 'doorway', 'post', 'ceiling')):
    """The gaps of a place: {'issues': [{kind, text, x, y, z, ref, side(s), fixes: [{label, ops}]}],
    'tiles': how many floor pieces were looked at, 'style', 'typical': how gappy the game's own places
    of this style are (gapsurvey.py), 'rate': this place's see-through holes per floor piece, 'hidden':
    how many see-through holes were left out because the place has no more of them than the game's own
    places of the style, 'hidden_kinds': {kind: n} for the gaps, dead doorways, posts wanted and missing
    ceilings left out because the place shows the kind at no more than twice the game's rate for the
    style (the game's own Gold Coast places "want" a post at a third of their tiles: the same joinery,
    not a fault; the slack CLASH_BASELINE gives clips). The default list is what is worse than the game's
    own places; everything=True lists every line the finder has, and the clips and z-fights above twice
    the game's rate (clashes=True adds those to the default list too). Measured on the user's houses
    2026-10-22 (packaging/nexus/builder-learning-round.md): 45 posts wanted on a Gold Coast house → 0
    by default, 12 on a Common plain house stay (the game's Common plain places want none)."""
    res = _scan(db, cell_key)
    if clashes or everything:
        # (the user's acceptance rules for closure pieces: nothing clips, nothing flickers. The game's own
        # places are full of both by the raw measure: posts sunk into wall ends, tiles overlapping at
        # their seams, faces of a post flush with a wall. So a kind of pair is only reported where this
        # place shows more than twice the game's rate of it; the rest is counted, not listed)
        try:
            m_ = mapdata.cellmap(db, cell_key)
            found = clash_issues(db, m_)
            n_pieces = max(1, sum(1 for r in m_['refs'] if r.get('ri') is not None and r['type'] == 'STAT' and r.get('arch')))
            by = {}
            for i in found:
                by.setdefault((i['kind'], _pair_kind(i)), []).append(i)
            like_game, excess = {}, []
            for key, lst in by.items():
                base = CLASH_BASELINE.get(key, 0.0) * n_pieces / 100.0
                if len(lst) > 2 * base + 1 or key[1] == 'sheet-tile':
                    excess += lst
                else:
                    like_game[' '.join(key)] = len(lst)
            res['issues'] += excess
            res['clashes_like_the_game'] = like_game
            for n, i in enumerate(res['issues']):
                i['n'] = n
        except Exception as e:
            print('clash check:', e)
    res['hidden'] = 0
    res['hidden_kinds'] = {}
    res['typical'] = None
    tiles = res.get('tiles') or 0
    holes = [i for i in res['issues'] if i['kind'] == 'hole']
    res['rate'] = round(len(holes) / float(tiles), 3) if tiles else 0.0
    if not tiles or not res.get('prefix'):
        return res
    try:
        import gapsurvey
        res['typical'] = gapsurvey.typical(db, res['prefix'])
    except Exception as e:
        print('gap survey:', e)
    # (one game place is no rate: Dres has one; the gate needs three or more)
    typ = res['typical'] if res['typical'] and res['typical'].get('places', 0) >= 3 else None
    if typ and not everything:
        per = typ['per_tile']
        if holes and res['rate'] <= per.get('hole', 0):
            # (no worse than the game's own: the see-through spots stay out of the way, the rest shows)
            res['issues'] = [i for i in res['issues'] if i['kind'] != 'hole']
            res['hidden'] = len(holes)
        for kind in gate:
            n = sum(1 for i in res['issues'] if i['kind'] == kind)
            if n and n / float(tiles) <= 2 * per.get(kind, 0):
                res['issues'] = [i for i in res['issues'] if i['kind'] != kind]
                res['hidden_kinds'][kind] = n
        for n, i in enumerate(res['issues']):
            i['n'] = n
    return res


def excess(res):
    """Whether a scanned place has more see-through holes per floor piece than the game's own places of
    its style (True when there's nothing to go by)."""
    t = res.get('typical')
    if not t or not res.get('tiles'):
        return True
    return res['rate'] > t['per_tile'].get('hole', 0)


def _scan(db, cell_key):
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
            if _stair_beyond(m['refs'], t, s, tile_refs):
                continue                  # (stairs go through here: never a wall across them)
            if _railed(m['refs'], t, s):
                t.setdefault('railed', set()).add(s)
                continue                  # (a gallery's edge over a two-storey hall, railed: the game's halls look down so)
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
            if t.get('tall'):
                piece = None                  # (a two-storey hall piece: no single-storey piece swaps for it)
            if piece and (piece['id'].lower() != t['id'].lower() or q != t['q']):
                wf = _wall_fix(db, t, missing) if missing else None
                if not missing or wf:
                    fixes.append({'label': 'Swap for %s%s' % (piece['id'], ' and add walls' if missing else ' (walled there)'),
                                  'ops': [{'op': 'swap', 'ref': t['ref'], 'id': piece['id'], 'rz': q * math.pi / 2}] + dels +
                                  (wf['ops'] if wf else [])})
            # then a piece with exactly these sides, if that's another one
            v = _variant(kp, want) if not t.get('tall') else None
            if v and not (piece and v[0]['id'].lower() == piece['id'].lower()):
                fixes.append({'label': 'Swap for %s (walled there)' % v[0]['id'],
                              'ops': [{'op': 'swap', 'ref': t['ref'], 'id': v[0]['id'], 'rz': v[1] * math.pi / 2}] + dels})
            w = _wall_fix(db, t, sides)
            if w:
                fixes.append(w)
            # (first of all: what the game itself stands at an edge in this situation, when the joint survey
            # has a strong answer and this isn't it: a walled side piece with its addon and pillar, say)
            try:
                import joints
                jf = joints.fix_for(db, m, tiles, t, sides[0])
                if jf:
                    jf.pop('swap', None)
                    fixes.insert(0, jf)
            except Exception as e:
                print('joint survey:', e)
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
            if not pat.get('ceiling') and not roofed and not _above(tiles, t) and not t.get('tall') and \
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
                       'fixes': [{'label': 'Add %s' % p['id'], 'ops': [{'op': 'place', 'id': p['id'], 'p': [p['x'], p['y'], p['z'], 0, 0, p.get('rot', 0.0)]}]}]})
    # half-length pieces where a whole one should be
    issues += _short_issues(db, m)
    # what the player can actually see through: slits and corners where pieces don't meet
    issues += _hole_issues(db, m, tiles, floors, issues, cell_key)
    # a stairwell opening's own edge on the floor above, with nothing beyond it
    issues += _opening_issues(db, m, tiles, floors)
    # edges where what stands is not what the game stands in that situation (joints.py: the joint survey)
    try:
        import joints
        issues += joints.issues(db, m, tiles, prefix)
    except Exception as e:
        print('joint survey:', e)
    # in the order to fix them in (posts first: they often close what's below them in the list)
    issues.sort(key=lambda i: _rank(i) if i['fixes'] else 3)
    for n, i in enumerate(issues):
        i['n'] = n
    fr = door_frame(tiles[0]['kit']) if tiles else None
    # how often the game's own places in this style stand a post at a corner (what the fixes go by)
    share = None
    try:
        import jointsurvey
        stats, places = jointsurvey.survey(db, prefix) if prefix else ({}, 0)
        n = sum(v['n'] for v in stats.values())
        share = {'places': places, 'share': round(sum(v['with'] for v in stats.values()) / float(n), 2) if n else None}
    except Exception:
        pass
    return {'issues': issues, 'tiles': len(tiles), 'style': kits.friendly(prefix) if prefix else None, 'prefix': prefix,
            'door_frame': fr['id'] if fr and not tiles[0]['kit'].get('entry_doors') else None, 'posts': share}


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
                out.append({'id': rid, 'rz': r['p'][5], 'uses': kits.game_uses(db, rid.lower())})
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
    res = scan(db, cell_key)           # (see-through holes only while the place has more than the game's own)
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
    patch.sort(key=lambda ri: -kits.game_uses(db, db.recs[ri][1].lower()))
    for ri in patch:
        add(ri)
    for p in kp['pieces']:
        add(p['ri'])
    return items[:limit]
