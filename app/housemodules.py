"""House modules: whole buildings of the game's, to put down outdoors and join into bigger houses the way
the game joins its pieces, each sized in the interior tiles it will be built with.

A module is one of the game's own buildings (exteriorsurvey.py's catalogue: its pieces and its door, as the
game stands them, relative to the door), given here as a group the map's placing tool puts down (groups.py):
items relative to the building's middle and to the ground under its door, so it stands on the ground as the
game's stands. Its size is in the tiles of the kit the game builds its interiors in: a module whose walls
run on the tile lines ("fill" near 1: the tiles' area over the area inside its walls) builds inside without
any leeway, and those are listed first ("good sizes": FILL_GOOD).

Joining: on a big piece of a building standing outdoors (a house, a wing, a tower, a storey), the pieces the
game joins to that model, on which face, where and turned how (exteriorsurvey's 'big' table, from 913 of the
game's buildings), most often first. Each candidate says whether it keeps the building on its tile grid (a
quarter turn, its offset on the half-tile lines along the door's frame) and what the interior would then be:
its tiles, how well they fill the outline, the floors. Measured 2026-10-24: with each game building held out,
its actual partner and spot is among the first five candidates learnt from the others in 47% of its joins.

Then "Build an interior inside this building" (frombuilding.py) builds the whole joined house as one."""
import math
import re

import adjacency
import editing
import exteriorsurvey as es
import kits
import mapdata
import outside
import shellsurvey as ss
from editing import EditError

FILL_GOOD = (0.85, 1.15)
# what is not a house's own wing, tower or storey (a garden wall, a market stand, a stair: offered only on asking).
# Measured over the game's 567 big joins, 2026-10-24: 273 join house-like pieces (85 of them one on top of
# another: the Legion and Imperial towers' stages, Mournhold's mezzanines, Vivec's wings, Hlaalu balconies)
NOT_HOUSE = re.compile(r'wall|fence|stand|curve|gate|bridge|stair|step|ramp|platform|dock|pier|canopy|awning|market|scaffold|'
                       r'foundation|ruin|rock|statue|pillar|column|arch')
MAX_CANDIDATES = 10
SIDE_WORDS = {'E': 'to its right', 'W': 'to its left', 'N': 'behind it', 'S': 'in front of it', 'U': 'on top', 'D': 'under it',
              'in': 'set into it'}


def _survey(db):
    s = es.ready(db)
    if s is None:
        raise EditError('The Workshop is still learning how the game puts its buildings together (a few minutes, once, in '
                        'the background). Try again shortly.')
    return s


def _label(m):
    st = look(m) or m.get('style') or kits.friendly(m.get('kit') or '') or 'House'
    wd = m.get('tiles_wd') or [0, 0]
    fl = m.get('floors') or 1
    return '%s %s: %d×%d tiles, %d floor%s' % (st, m['main'], wd[0], wd[1], fl, '' if fl == 1 else 's')


def catalogue(db, style=None, good=True, limit=60):
    """The modules, one per main model (the most used), good sizes first: [{key, name, style, kit, tile,
    tiles, tiles_wd, floors, fill, good, uses, example, items}]."""
    s = _survey(db)
    best = {}
    for m in s['modules']:
        if style and m.get('style') != style:
            continue
        if not m.get('tiles') or 'ground' not in m:
            continue
        k = m['main']
        if k not in best or m['uses'] > best[k]['uses']:
            best[k] = m
    out = []
    for m in best.values():
        ok = FILL_GOOD[0] <= m['fill'] <= FILL_GOOD[1]
        if good and not ok:
            continue
        out.append({'key': m['main'], 'name': _label(m), 'style': m.get('style'), 'kit': m.get('kit'), 'tile': m['tile'],
                    'tiles': m['tiles'], 'tiles_wd': m.get('tiles_wd'), 'floors': m.get('floors'), 'fill': m['fill'], 'good': ok,
                    'uses': m['uses'], 'example': (m.get('examples') or [None])[0], 'items': items_of(m)})
    out.sort(key=lambda r: (not r['good'], -r['uses'], abs(1 - r['fill'])))
    return out[:limit]


def styles(db):
    """{look: number of the game's homes of that look the prefab planner can lay over a volume}: counted the
    way fit_volume picks them (by the look of their outside pieces, homes only). (Counted by the interior style
    the survey predicted, Redoran, Nordic, Reach and the rest never showed in Plan a prefab even once their
    buildings were learnt, 2026-10-27.)"""
    s = _survey(db)
    c = {}
    for m in s['modules']:
        lk = look(m)
        if lk and m.get('ftiles') and m.get('fpieces') and homely(m):
            c[lk] = c.get(lk, 0) + 1
    return c


def items_of(m):
    """A module as a group for groups.place: its pieces and its door, relative to the middle of its pieces
    and to the ground under its door (dz 0 = the ground)."""
    rows = [dict(p) for p in m['pieces']] + [{'id': m['door'], 'x': 0.0, 'y': 0.0, 'z': 0.0, 'rx': 0.0, 'ry': 0.0, 'rz': 0.0,
                                             's': m.get('door_scale') or 1.0}]
    cx = (min(r['x'] for r in rows) + max(r['x'] for r in rows)) / 2
    cy = (min(r['y'] for r in rows) + max(r['y'] for r in rows)) / 2
    g = m.get('ground', 0.0)
    out = []
    for r in rows:
        # (the pieces are in the door's frame, outside._local: turned back into the world with the door facing
        # north before the placing tool's own turn; the game turns clockwise)
        wx, wy = outside._world(r['x'] - cx, r['y'] - cy, 0.0)
        out.append({'id': r['id'], 'dx': round(wx, 2), 'dy': round(wy, 2), 'dz': round(r['z'] - g, 2),
                    'rx': r.get('rx', 0.0), 'ry': r.get('ry', 0.0), 'rz': round(r['rz'] % (2 * math.pi), 5), 's': r.get('s') or 1.0})
    return out


# ---------------------------------------------------------------- joining

def _placed(db, cell_key, ref_key):
    items = ss.near_items(db, *_xy(db, cell_key, ref_key))
    it = next((i for i in items if i['k'] == ref_key and i['cell'] == cell_key), None)
    if it is None:
        raise EditError('That piece is no longer there.')
    return it, items


def _xy(db, cell_key, ref_key):
    m = mapdata.cellmap(db, cell_key)
    r = next((x for x in m.get('refs', []) if x['k'] == ref_key), None)
    if r is None:
        raise EditError('That piece is no longer there.')
    return r['p'][0], r['p'][1]


def _item_for(db, rid, pos, s=1.0):
    ri = db.resolve_id(rid)
    if ri is None:
        return None
    b = mapdata.object_bounds(db, ri)
    if not b:
        return None
    return {'id': rid, 'low': rid.lower(), 'p': list(pos), 's': s, 'b': b, 'tag': db.recs[ri][0], 'ri': ri, 'k': None, 'cell': None,
            'box': outside._box(b, pos, s), 'to': None}


def candidates(db, cell_key, ref_key, with_size=True, walls=False):
    """What the game joins to this piece: [{n, side, words, id, pose, tile_true, clash, size?}], most often
    first; size: the interior of the building with it joined, when the building has a door."""
    if not cell_key.startswith('#'):
        raise EditError('Modules are joined outdoors.')
    s = _survey(db)
    it, items = _placed(db, cell_key, ref_key)
    table = s.get('big', {}).get(it['low'])
    if not table:
        return {'piece': it['id'], 'candidates': [], 'hidden': 0, 'note': 'The game never joins another big piece to %s.' % it['id']}
    A = es._piece(it)
    rows = []
    hidden = 0
    for side, c in table.items():
        for rs, n in c.items():
            bid, rest = rs.split('@')
            if not walls and NOT_HOUSE.search(bid):
                hidden += n
                continue
            xyz, turn = rest.split('/')
            lx, ly, lz = (int(v) for v in xyz.split(','))
            rows.append((n, side, (bid, lx, ly, lz, int(turn))))
    rows.sort(key=lambda r: -r[0])
    b = None
    try:
        import frombuilding
        b = frombuilding.building_at(db, cell_key, ref_key)
    except EditError:
        pass
    out = []
    here = [i for i in items if ss.is_building_piece(i)]
    for n, side, rel in rows[:MAX_CANDIDATES * 2]:
        pl = adjacency.placed(A, rel)
        pos = pl['p']
        new = _item_for(db, rel[0], pos)
        if new is None:
            continue
        # (one standing there already: joined before)
        if any(i['low'] == new['low'] and math.hypot(i['p'][0] - pos[0], i['p'][1] - pos[1]) < 32 and abs(i['p'][2] - pos[2]) < 32 for i in here):
            continue
        row = {'n': n, 'side': side, 'words': '%s %s' % (rel[0], SIDE_WORDS.get(side, side)), 'id': rel[0],
               'pose': [round(v, 2) for v in pos], 'corners': _corners(new)}
        if b and b['frame']:
            fr = b['frame']
            T = _tile(db, b)
            lx, ly = fr.to(pos[0], pos[1])
            turn = (math.degrees(pos[5] - (fr.yaw())) % 90)
            row['tile_true'] = (min(turn, 90 - turn) < 2 and min(abs(lx) % (T / 2), T / 2 - abs(lx) % (T / 2)) < 12 and
                                min(abs(ly) % (T / 2), T / 2 - abs(ly) % (T / 2)) < 12)
            if with_size and len(out) < MAX_CANDIDATES:
                row['size'] = _size(db, b, new, T)
        out.append(row)
        if len(out) >= MAX_CANDIDATES:
            break
    return {'piece': it['id'], 'candidates': out, 'hidden': hidden,
            'base': _size(db, b, None, _tile(db, b)) if (b and b['frame']) else None}


def _tile(db, b):
    import frombuilding
    kit, _bld, _pr = frombuilding.pick_style(db, b)
    kp = kits.kit_pieces(db, kit) if kit else None
    return kp['tile'] if kp else 256


def _corners(it):
    b, s, p = it['b'], it['s'] or 1.0, it['p']
    out = []
    for cx, cy in ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4])):
        wx, wy = outside._world(cx * s, cy * s, p[5])
        out.append([round(p[0] + wx), round(p[1] + wy)])
    return out


def _size(db, b, extra, T):
    """The interior a building (with `extra` joined) would get: {tiles, fill, floors_closed, closed}."""
    import frombuilding
    group = list(b['group']) + ([extra] if extra else [])
    fr = b['frame']
    g0 = ss.outline(db, group, fr, b['doors'], 0)
    if not g0['closed']:
        return {'closed': False}
    tiles = frombuilding._tiles_in(set(g0['cells']), T)
    ups = sum(1 for k in (1, 2) if (lambda u: u['closed'] and u['area'] >= frombuilding.UP_MIN * g0['area'])(ss.outline(db, group, fr, b['doors'], k)))
    return {'closed': True, 'tiles': len(tiles), 'fill': round(len(tiles) * T * T / float(g0['area']), 2), 'storeys': 1 + ups}


def join(db, cell_key, ref_key, rid, pose):
    """Put the joined piece where the game puts it (one change)."""
    import fixit
    editing._require_project(db)
    if db.resolve_id(rid) is None:
        raise EditError('No piece called "%s".' % rid)
    x, y = float(pose[0]), float(pose[1])
    key = '#%d,%d' % (math.floor(x / 8192), math.floor(y / 8192))
    r = fixit.apply(db, key, [{'op': 'place', 'id': rid, 'p': [float(v) for v in pose[:6]]}],
                    label='Joined %s to a building the way the game joins them' % rid)
    return {'cell': key, 'ref': r['changed'][0]}


# ---------------------------------------------------------------- snapping a piece the way the game joins it

def snaps(db, rid, x, y, z, skip=None, radius=1600, limit=80):
    """Where the game joins this model to the made pieces near (x, y, z) outdoors: [{p: [x, y, z, rx, ry, rz], n, to, side}],
    the most used joins first. From the joins learnt in every exterior cell (exteriorsurvey 'outdoor'), both ways round:
    the model standing against a neighbour, and a neighbour that stands against the model, worked back. For the 3D
    view's snapping: the game's own joins first, flush faces where it has none. Measured 2026-10-27: 45% of the game's
    joins (56% of Hlaalu's) are joins of the same two models on the same face elsewhere; the rest is improvised.
    {'learning': True} while the survey is still being learnt."""
    s = es.ready(db)
    if s is None:
        return {'learning': True, 'snaps': []}
    return {'learning': False, 'snaps': snaps_among(db, s, rid, x, y, ss.near_items(db, x, y), skip, radius, limit)}


def snaps_among(db, s, rid, x, y, items, skip=None, radius=1600, limit=80):
    """snaps() among these items (the world's near a spot, or the prefab workbench's own pieces, bench.py): the
    poses the game joins the model at, merged and the best backed first. s: the exterior survey."""
    J = (s.get('outdoor') or {}).get('joins') or {}
    E = (s.get('outdoor') or {}).get('exact') or {}
    # (a piece no place has takes its placed twin's joins, the same size and name but for its variant: exteriorsurvey.twins)
    TW = (s.get('outdoor') or {}).get('twins') or {}
    low = rid.lower()
    me = low if low in J else TW.get(low, low)        # (whose joins stand for this model)

    def rel_of(model, side, rs):
        # (the join's exact pose where it was learnt, else the grid key's)
        e = ((E.get(model) or {}).get(side) or {}).get(rs)
        if e:
            return e
        xyz, turn = rs.split('@')[1].split('/')
        return [int(v) for v in xyz.split(',')] + [int(turn)]
    items = [it for it in items if es.is_outdoor_piece(it) and it['k'] != skip]
    near = sorted((it for it in items if math.hypot((it['box'][0] + it['box'][2]) / 2 - x, (it['box'][1] + it['box'][3]) / 2 - y) < radius),
                  key=lambda it: math.hypot(it['p'][0] - x, it['p'][1] - y))[:16]
    mine = J.get(me) or {}
    out = []
    for it in near:
        A = es._piece(it)
        nb = it['low'] if it['low'] in J else TW.get(it['low'], it['low'])   # (the neighbour's, likewise)
        # (the model against this neighbour, as the game puts it)
        # (and 'in': one set into the other, a window in a wall, a door in its jamb; a quarter of the game's spots)
        for side, rels in (J.get(nb) or {}).items():
            for rs, n in rels.items():
                bid = rs.split('@')[0]
                if bid != low and bid != me:
                    continue
                lx, ly, lz, turn = rel_of(nb, side, rs)
                pl = adjacency.placed(A, (bid, lx, ly, lz, turn))
                out.append({'p': pl['p'], 'n': n, 'to': it['id'], 'side': side})
        # (this neighbour against the model: the model's pose worked back from it)
        for side, rels in mine.items():
            for rs, n in rels.items():
                bid = rs.split('@')[0]
                if bid != it['low'] and bid != nb:
                    continue
                lx, ly, lz, turn = rel_of(me, side, rs)
                rz = (A['rz'] - math.radians(turn)) % (2 * math.pi)
                c, sn = math.cos(rz), math.sin(rz)
                wx, wy = A['x'] - (lx * c + ly * sn), A['y'] - (-lx * sn + ly * c)
                out.append({'p': [round(wx, 2), round(wy, 2), round(A['z'] - lz, 2), 0, 0, round(rz, 5)], 'n': n, 'to': it['id'],
                            'side': 'to ' + side})
    # (a spot where the same model stands already is taken)
    same = [it for it in items if it['low'] == low]
    out = [o for o in out if not any(math.hypot(o['p'][0] - it['p'][0], o['p'][1] - it['p'][1]) < 12 and abs(o['p'][2] - it['p'][2]) < 12
                                     for it in same)]
    # (one spot the game's way to two neighbours or more is one spot, and far likelier the real one: a rogue join used
    # once lay nearer the dropped piece than its own spot in Balmora, 2026-10-27. k: the neighbours agreeing on it)
    merged = []
    for o in sorted(out, key=lambda o: -o['n']):
        m = next((m for m in merged if math.hypot(m['p'][0] - o['p'][0], m['p'][1] - o['p'][1]) < 3 and abs(m['p'][2] - o['p'][2]) < 3
                  and abs((m['p'][5] - o['p'][5] + math.pi) % (2 * math.pi) - math.pi) < 0.01), None)
        if m is None:
            merged.append(dict(o, k=1, _to={o['to']}))
        else:
            m['n'] += o['n']
            if o['to'] not in m['_to']:
                m['_to'].add(o['to'])
                m['k'] += 1
    for m in merged:
        del m['_to']
    merged.sort(key=lambda o: (-o['k'], -o['n']))
    return merged[:limit]


# ---------------------------------------------------------------- fitting the game's buildings to a volume

OUT_MAX = 0.15                  # a module may stand out of the volume by this share of its tiles (one tile at least)
# how closely the game's buildings must match a stacked volume (Plan a prefab's Close / Usual / Loose): the share of
# a building that may stand out of the volume (the door still goes on the front first, any outer wall only when
# no building of the style has it there)
TOLERANCE = {'close': {'out': 0.06}, 'usual': {'out': OUT_MAX}, 'loose': {'out': 0.35}}
# buildings that are not homes or shops: offered only for "any building" (kind='any')
NOT_HOME = re.compile(r'tomb|ruin|dae_|daed|menhir|gazebo|shrine|barrow|fort|keep|guardtower|legion|wall|gate|bridge|stand|'
                      r'market|chapel|temple|tower|mine|cave|dock|warehouse|stable|silt|canton|plaza|ent_|entrance|boat|ship|column|pillar|'
                      r'exit|ice_|iceberg|karstaag|dng|dungeon|grotto|sewer|striderport')


def look(m):
    """A module's style by its exterior pieces' names: its main piece's, else the one most of its pieces name;
    None when they name none. (The style the game's interior in it was built in is another matter: a barrow's
    interior may be Hlaalu. And never the survey's guess of the interior style: for a building it knew nothing
    of, that guess was the commonest style, Hlaalu, and an ice-cave exit and a Reach house were offered as
    Hlaalu homes, 2026-10-27.)"""
    if 'look' not in m:
        st = mapdata.style_of(m['main'])
        if not st:
            # (only when most of its pieces name one style: a Reach house with a High Elf door was a "High Elf home")
            c = {}
            ps = m.get('pieces') or ()
            for p in ps:
                s_ = mapdata.style_of(p['id'])
                if s_:
                    c[s_] = c.get(s_, 0) + 1
            best = max(c, key=c.get) if c else None
            st = best if best and c[best] > 0.6 * len(ps) else None
        m['look'] = st
    return m['look']


def homely(m):
    import planfrom
    if NOT_HOME.search(m['main']) or m['main'].startswith('in_'):
        return False                     # (an interior piece standing outdoors is no building)
    ex = m.get('examples') or []
    return not ex or not all(planfrom.EXCLUDE_NAME_RE.search(e) for e in ex)


def _turn(i, j, q):
    """A tile of a module's frame turned q quarter turns clockwise, as a point in tiles (tile centres at i T,
    (j + 1/2) T): outside._world's turn."""
    x, y = float(i), j + 0.5
    for _ in range(q % 4):
        x, y = y, -x                     # (clockwise, the game's way: +y towards +x)
    return x, y


def _footprints(m):
    """A module's tiles per storey [{(i, j)}], ground first."""
    out = [{tuple(t) for t in m.get('ftiles') or ()}]
    for up in m.get('fup') or ():
        out.append({tuple(t) for t in up})
    return out


def _placements(m, vol, front=None):
    """Every quarter turn and shift of a module that lands its tiles on the volume's tile lattice: yields
    (q, (ox, oy), [{(x, y)} per storey]) where volume tile (x, y) has its centre at (x T, y T)."""
    fps = _footprints(m)
    if not fps[0]:
        return
    ground = vol[0]
    for q in range(4):
        if front is not None and q != front:
            continue
        pts = {t: _turn(t[0], t[1], q) for fp in fps for t in fp}
        # the lattice offset that makes every turned centre whole
        fx = pts[next(iter(fps[0]))][0] % 1.0
        fy = pts[next(iter(fps[0]))][1] % 1.0
        turned = [{(int(round(pts[t][0] - fx)), int(round(pts[t][1] - fy))) for t in fp} for fp in fps]
        g = turned[0]
        gx = [t[0] for t in g]
        gy = [t[1] for t in g]
        vx = [t[0] for t in ground]
        vy = [t[1] for t in ground]
        for sx in range(min(vx) - max(gx), max(vx) - min(gx) + 1):
            for sy in range(min(vy) - max(gy), max(vy) - min(gy) + 1):
                # (at: where the module's frame origin lands, in volume tiles: a frame point P goes to turn(P) + at)
                yield q, (sx - fx, sy - fy), [{(t[0] + sx, t[1] + sy) for t in fp} for fp in turned]


VARIETY = 1.0                   # a building this much behind the best fit (in tiles) is still drawn among the choices
REPEAT_COST = 3.0               # and one already in the plan is that much behind: used again only when nothing else covers


SOLID_INSET = 32                # a tile taken in this much each way before a piece's mesh is looked for in it (64 let
                                # a door frame 40 deep into its neighbour's wall through)
SOLID_FOOT = 96                 # and only what reaches down to the ground (within this): what stands there
SOLID_BELOW = 32                # (the band read: this far under the ground to SOLID_FOOT over it)


def _solid(db, m, T):
    """The frame tiles a module's own pieces stand on (not its trim), whatever its floor tiles: its walls, stairs,
    porch and door reach past them, and two buildings laid side by side by their floor tiles alone put one's door
    and stairs inside the other (948 of the clashes in 160 two-building prefabs, 2026-10-27). {(i, j)}
    From the pieces' meshes at the ground, not their boxes: a Telvanni root, a Velothi wall run at an angle or a
    curved stair claims the whole box round it, and blocked or let through placements wrongly (2026-10-28). A tile
    is taken where a triangle of a piece crosses the band at the ground inside it, the tile taken in by SOLID_INSET
    (a wall on the line between two tiles takes neither)."""
    if '_solid' not in m:
        out = set()
        g = m.get('fground', -40.0)
        for p in m.get('fpieces') or ():
            if p.get('trim'):
                continue
            ri, b = adjacency._box(db, p['id'])
            if not b or ri is None:
                continue
            s = p.get('s') or 1.0
            tris = ss.world_tris(db, {'low': p['id'].lower(), 'p': [p['x'], p['y'], p['z'], p.get('rx', 0.0), p.get('ry', 0.0), p['rz']],
                                      's': s, 'ri': ri})
            # (its whole height, seen from above: an upper storey overhangs, and a Reach house's was over its neighbour's
            # door and window, which a test at the ground let through, by box or by mesh, 2026-10-28)
            cells = _foot_cells(tris, g)
            # (a tile is taken where the piece stands inside it, the tile taken in by SOLID_INSET)
            for (cx, cy) in cells:
                x, y = (cx + 0.5) * FOOT_CELL, (cy + 0.5) * FOOT_CELL
                i, j = int(math.floor(x / T + 0.5)), int(math.floor(y / T))
                if abs(x - i * T) <= T / 2.0 - SOLID_INSET and abs(y - (j + 0.5) * T) <= T / 2.0 - SOLID_INSET:
                    out.add((i, j))
        m['_solid'] = out
    return m['_solid']


FOOT_CELL = 32                  # the grid a piece's footprint at the ground is drawn on
FOOT_SHUT = 2                   # gaps in its walls up to twice this many cells each side (a doorway, 128) are closed


def _foot_cells(tris, g):
    """Where a piece stands at the ground, on a FOOT_CELL grid: the cells its mesh crosses in the band at the ground,
    and those its mesh there closes round (a house shell is walls with a hollow inside: by its walls alone it took
    almost nothing, and Reach houses were laid into their neighbours' doors, 2026-10-28). {(cx, cy)}"""
    from placecheck import _tri_in_box
    zc, zh = 0.0, 1e6                   # (every height: the piece seen from above)
    h = (FOOT_CELL / 2.0, FOOT_CELL / 2.0, zh)
    wall = set()
    for t in tris:
        xs_, ys_ = (t[0][0], t[1][0], t[2][0]), (t[0][1], t[1][1], t[2][1])
        for cx in range(int(math.floor(min(xs_) / FOOT_CELL)), int(math.floor(max(xs_) / FOOT_CELL)) + 1):
            for cy in range(int(math.floor(min(ys_) / FOOT_CELL)), int(math.floor(max(ys_) / FOOT_CELL)) + 1):
                if (cx, cy) in wall:
                    continue
                ox, oy = (cx + 0.5) * FOOT_CELL, (cy + 0.5) * FOOT_CELL
                if _tri_in_box((t[0][0] - ox, t[0][1] - oy, t[0][2] - zc), (t[1][0] - ox, t[1][1] - oy, t[1][2] - zc),
                               (t[2][0] - ox, t[2][1] - oy, t[2][2] - zc), h):
                    wall.add((cx, cy))
    if not wall:
        return wall
    # (what the walls close round: everything in their box the outside can't reach, past gaps up to a doorway's width,
    # the walls grown by FOOT_SHUT cells for it: the way in at the ground let the outside in, and nothing was inside)
    shut = set(wall)
    for (x, y) in wall:
        for dx in range(-FOOT_SHUT, FOOT_SHUT + 1):
            for dy in range(-FOOT_SHUT, FOOT_SHUT + 1):
                shut.add((x + dx, y + dy))
    x0, x1 = min(c[0] for c in shut) - 1, max(c[0] for c in shut) + 1
    y0, y1 = min(c[1] for c in shut) - 1, max(c[1] for c in shut) + 1
    seen, todo = {(x0, y0)}, [(x0, y0)]
    while todo:
        x, y = todo.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and n not in seen and n not in shut:
                seen.add(n)
                todo.append(n)
    inside = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) not in seen and (x, y) not in shut}
    # (the inside grown back out to the walls, and the walls themselves)
    grown = set(inside)
    for (x, y) in inside:
        for dx in range(-FOOT_SHUT, FOOT_SHUT + 1):
            for dy in range(-FOOT_SHUT, FOOT_SHUT + 1):
                if (x + dx, y + dy) in shut:
                    grown.add((x + dx, y + dy))
    return wall | grown


def _to_volume(tiles, q, at):
    """Frame tiles of a module laid turned q and at `at`, as volume tiles (as _placements lays its floor tiles)."""
    out = set()
    for i, j in tiles:
        x, y = _turn(i, j, q)
        out.add((int(round(x + at[0])), int(round(y + at[1]))))
    return out


def fit_volume(db, style, volume, front='S', limit=6, skip=(), kind='homes', tolerance='usual', seed=None):
    """The game's buildings of a style laid over a volume of tiles: volume {'tiles': [[x, y, storey]]} (in
    the style's kit tiles; storey 0 the ground). Greedy: the module covering most of what is left, standing
    out of the volume least, first; the first one is the front one and keeps its door on the volume's front
    edge (front: the side the door faces, 'S' = -y). Returns {'modules': [{key, name, q, at, tiles}],
    'items': a group for groups.place, 'covered', 'outside', 'missing': [[x, y, storey]], 'notes'}.
    seed: a draw among the fits nearly as good as the best (VARIETY), weighted by how often the game builds each,
    so the same volume doesn't always give the same house (the user: not "cookie cutter"); None, the best one.
    Either way a building already in the plan comes again only when nothing else covers (a Redoran hut x2 was)."""
    import random
    rng = random.Random(seed) if seed is not None else None
    s = _survey(db)
    vol = {}
    for x, y, k in volume.get('tiles') or ():
        vol.setdefault(int(k), set()).add((int(x), int(y)))
    if not vol.get(0):
        raise EditError('Put at least one block on the ground first.')
    storeys = [vol.get(k, set()) for k in range(max(vol) + 1)]
    for k in range(1, len(storeys)):
        if not storeys[k] <= storeys[k - 1]:
            raise EditError('A block on storey %d stands on nothing: every block needs one under it.' % (k + 1))
    mods = [m for m in s['modules'] if m.get('ftiles') and m.get('fpieces') and (not style or look(m) == style) and m['main'] not in skip
            and (kind == 'any' or homely(m))]
    if not mods:
        raise EditError('The game has no buildings of that style the Workshop has read.')
    T = mods[0]['tile']
    mods = [m for m in mods if m['tile'] == T]
    # (one of each main model, the most used: the catalogue's choice)
    best = {}
    for m in mods:
        if m['main'] not in best or m['uses'] > best[m['main']]['uses']:
            best[m['main']] = m
    mods = sorted(best.values(), key=lambda m: -m['uses'])[:80]
    fq = {'S': 0, 'W': 1, 'N': 2, 'E': 3}.get(front, 0)          # (the door's turn: a quarter turn per side)
    left = [set(st) for st in storeys]
    want = sum(len(st) for st in storeys)
    chosen, out_total = [], 0
    tol = TOLERANCE.get(tolerance) or TOLERANCE['usual']
    any_side = False
    used = set()
    taken = set()                   # the volume tiles the chosen buildings stand over, their pieces and floors both
    floors_ = set()                 # and their floors alone (with the tile before the front door)
    for step in range(limit + 1):
        top = None
        cands = []
        for m in mods:
            fps_n = sum(len(fp) for fp in _footprints(m))
            sol = _solid(db, m, T)
            for q, at, laid in _placements(m, storeys, fq if (not chosen and not any_side) else None):
                gain = sum(len(laid[k] & left[k]) for k in range(min(len(laid), len(left))))
                if gain < 2:
                    continue
                # (never standing in a building already laid: its door, stairs or walls on the other's floor, or its
                # floor over the other's. Outside both floors they may meet, eaves over a porch: forbidding that too
                # fitted a second building almost never, cover 94% -> 69%)
                if floors_ and (_to_volume(sol, q, at) & floors_ or laid[0] & taken):
                    continue
                # (standing out of the volume, on the storeys it has; storeys above its top only weigh a little: a roof
                # space reads as a storey, and its interior is not built anyway, the plan follows the volume)
                outside_ = sum(len(laid[k] - storeys[k]) for k in range(min(len(laid), len(storeys))))
                above = sum(len(laid[k]) for k in range(len(storeys), len(laid)))
                overlap = sum(len(laid[k] & (storeys[k] - left[k])) for k in range(min(len(laid), len(storeys))))
                if outside_ > max(1, tol['out'] * len(laid[0])):
                    continue
                if not chosen and not _door_on_front(m, q, at, storeys[0], q if any_side else fq):
                    continue
                score = (gain - 2 * outside_ - overlap - 0.25 * above - (REPEAT_COST if m['main'] in used else 0),
                         m['uses'] > 1, -abs(1 - m['fill']))
                cands.append((score, m, q, at, laid, outside_))
                if top is None or score > top[0]:
                    top = (score, m, q, at, laid, outside_)
        if top is None and not chosen and not any_side:
            any_side = True                      # (no building of the style has its door on that side: any outer wall)
            continue
        if top is None:
            break
        if rng is not None:
            # (the near-best, one placement a building, drawn by how often the game builds it, softened)
            near = {}
            for c in cands:
                if c[0][0] >= top[0][0] - VARIETY and (c[1]['main'] not in near or c[0] > near[c[1]['main']][0]):
                    near[c[1]['main']] = c
            pool = sorted(near.values(), key=lambda c: c[1]['main'])
            top = rng.choices(pool, weights=[math.sqrt(max(1, c[1]['uses'])) for c in pool])[0]
        _sc, m, q, at, laid, o_ = top
        used.add(m['main'])
        taken |= _to_volume(_solid(db, m, T), q, at) | set().union(*laid)
        floors_ |= set().union(*laid)
        if not chosen:
            floors_.add(_ahead(q, _door_tile(q, at)))        # (and the way to the front door stays open)
        for k in range(min(len(laid), len(left))):
            left[k] -= laid[k]
        out_total += o_
        chosen.append({'key': m['main'], 'name': _label(m), 'q': q, 'at': [round(at[0], 2), round(at[1], 2)],
                       'tiles': [[t[0], t[1], k] for k, fp in enumerate(laid) for t in sorted(fp)], '_m': m})
        if not any(left):
            break
    if not chosen:
        raise EditError('None of the game\'s %s buildings fits that volume: try a block at least two tiles across.' % (style or ''))
    items = _compose(chosen, T)
    # the front module's door, and the volume's tiles in the door's frame (tile (0, 0) the door's, +y inward):
    # the interior's plan comes straight from them (frombuilding.build tiles=)
    f0 = chosen[0]
    dt = _door_tile(f0['q'], f0['at'])
    side = {0: 'S', 1: 'W', 2: 'N', 3: 'E'}[f0['q'] % 4]

    def to_door(x, y):
        rx, ry = x - dt[0], y - dt[1]
        for _ in range((4 - f0['q']) % 4):
            rx, ry = ry, -rx                   # (turned back so the door faces -y)
        return rx, ry
    # (and which of the game's buildings stands over each: the interior gets a room or more per building)
    under = {}
    for n_, ch_ in enumerate(chosen):
        for x, y, k in ch_['tiles']:
            under.setdefault((x, y, k), n_)
    covered_t = [[*to_door(x, y), k, under.get((x, y, k), under.get((x, y, 0), 0))]
                 for k, st in enumerate(storeys) for (x, y) in sorted(st) if (x, y) not in left[k]]
    missing = [[t[0], t[1], k] for k, st in enumerate(left) for t in sorted(st)]
    covered = 1 - len(missing) / float(want)
    notes = []
    if missing:
        notes.append('%d of the %d tiles are not under any of the game\'s buildings: the interior will leave them out.' % (len(missing), want))
    if len(chosen) > 1:
        notes.append('%d buildings side by side, as the game builds its rows; the front one has the door.' % len(chosen))
    if side != front:
        notes.append('None of the game\'s %s buildings that fit has its door on that side: the door is on the %s side.' % (
            style or '', {'S': 'front', 'N': 'back', 'W': 'left', 'E': 'right'}[side]))
    kit0 = chosen[0]['_m'].get('kit')
    for ch in chosen:
        ch.pop('_m', None)
    return {'style': style, 'tile': T, 'modules': chosen, 'items': items, 'covered': round(covered, 3),
            'outside': out_total, 'missing': missing, 'notes': notes, 'door_tile': list(dt), 'door_side': side,
            'frame_tiles': covered_t, 'kit': kit0}


def _door_on_front(m, q, at, ground, fq):
    """The front module's door: turned to face the front (q == fq), its tile in the volume and the tile in
    front of it outside the volume."""
    return q == fq and _door_tile(q, at) in ground and _ahead(q, _door_tile(q, at)) not in ground


def _door_tile(q, at):
    """The volume tile holding the door's tile (frame tile (0, 0), centre (0, 1/2))."""
    x, y = 0.0, 0.5
    for _ in range(q % 4):
        x, y = y, -x
    return int(round(x + at[0])), int(round(y + at[1]))


def _ahead(q, t):
    ox, oy = {0: (0, -1), 1: (-1, 0), 2: (0, 1), 3: (1, 0)}[q % 4]
    return t[0] + ox, t[1] + oy

def _compose(chosen, T):
    """The modules' pieces as one group: offsets from the middle of the volume, dz from the ground."""
    rows = []
    # (whose tile each is: a building's trim on a tile its neighbour covers goes. Brought along with each building,
    # its windows, chimneys and railings stood inside the next one's walls: 148 of 160 two-building prefabs had a
    # piece cut into its neighbour, 2026-10-27)
    owner = {}
    for n, ch in enumerate(chosen):
        for x, y, _k in ch['tiles']:
            owner.setdefault((x, y), n)
    for n, ch in enumerate(chosen):
        m = ch['_m']
        th = ch['q'] * math.pi / 2
        ax, ay = ch['at']
        g = m.get('fground', -40.0)
        for p in m['fpieces']:
            # (frame units to tiles: the frame's tile centres sit at (i T, (j + 1/2) T))
            tx, ty = p['x'] / T, p['y'] / T
            wx, wy = outside._world(tx, ty, th)
            if p.get('trim') and owner.get((int(round(wx + ax)), int(round(wy + ay))), n) != n:
                continue
            rows.append({'id': p['id'], 'x': (wx + ax) * T, 'y': (wy + ay) * T, 'dz': round(p['z'] - g, 2), 'rx': p.get('rx', 0.0),
                         'ry': p.get('ry', 0.0), 'rz': round((p['rz'] + th) % (2 * math.pi), 5), 's': p.get('s') or 1.0, 'door': p.get('door'),
                         'mod': n, 'trim': bool(p.get('trim'))})
    cx = (min(r['x'] for r in rows) + max(r['x'] for r in rows)) / 2
    cy = (min(r['y'] for r in rows) + max(r['y'] for r in rows)) / 2
    out = []
    for r in rows:
        out.append({'id': r['id'], 'dx': round(r['x'] - cx, 2), 'dy': round(r['y'] - cy, 2), 'dz': r['dz'], 'rx': r['rx'], 'ry': r['ry'],
                    'rz': r['rz'], 's': r['s'], 'mod': r['mod'], 'trim': r['trim']})
    return out