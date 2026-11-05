"""Can you walk up it? Every kit stair of a place walked from the middle of the tile at its foot to the middle of the one
at its head, up its slope: at each step a ray on at knee and at chest height, and one straight up for your head. Anything
of the building in the way that isn't the stair itself (a wall across the run, a floor or ceiling piece closing over it,
another flight stood inside this one) and the stair can't be used. The fault "Build from pieces" kept making in One
stairwell plans (the user, 2026-10-31: "make sure the stairways are useable and open")."""
import math

import mapdata
import seethrough

STEP_LEN = 32
KNEE, CHEST = 40, 90
HEAD = 110                  # room over the treads a body needs (the player is about 128 tall, standing on them)


def walk(db, cell_key, sc=None, m=None):
    """[{'ref', 'id', 'ok', 'where': 'run'|'over'|None, 'by': the piece in the way, 'at': (x, y, z)}] for the place's stairs."""
    m = m or mapdata.cellmap(db, cell_key)
    # (doors left out: they open, and the game stands them across many a stair's head)
    sc = sc or seethrough.place_scene(db, {'refs': [r for r in m['refs'] if r['type'] != 'DOOR']})
    out = []
    for r in m['refs']:
        if r.get('ri') is None or r['type'] != 'STAT' or 'stair' not in r['id'].lower():
            continue
        got = _ends(db, r)
        if not got:
            continue
        (fx, fy, fz), (hx, hy, hz) = got
        own = sc.of_ref.get(r['k'])
        skip = set(range(*own)) if own else set()
        res = {'ref': r['k'], 'id': r['id'], 'ok': True, 'where': None, 'by': None, 'at': None}
        # the way up: flat across the foot tile to the stair, up the stair's own tile, flat on to the middle of the head
        # tile (a straight line from end to end rose across the flat tiles and ran into their floors)
        sx, sy = r['p'][0], r['p'][1]
        ux, uy = (hx - fx) / 2.0, (hy - fy) / 2.0          # (a tile, the stair's way up)
        lo_edge = (sx - ux / 2, sy - uy / 2)
        hi_edge = (sx + ux / 2, sy + uy / 2)
        pts = _line((fx, fy, fz), (lo_edge[0], lo_edge[1], fz)) + _line((lo_edge[0], lo_edge[1], fz), (hi_edge[0], hi_edge[1], hz)) +             _line((hi_edge[0], hi_edge[1], hz), (hx, hy, hz))
        prev = None
        for (px, py, pz) in pts:
            # the tread or floor under you, near where the line says (the kits' floors stand a little over or under it)
            dn = sc._hits((px, py, pz + 90), (0.0, 0.0, -1.0), 180, set(), True, both=True)
            if dn is None:
                continue
            gz = pz + 90 - dn[0]
            hit = None
            if prev is not None:
                ddx, ddy, ddz = px - prev[0], py - prev[1], gz - prev[2]
                L = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) or 1.0
                for h in (KNEE, CHEST):
                    hit = _hit(sc, (prev[0], prev[1], prev[2] + h), (ddx / L, ddy / L, ddz / L), L, skip)
                    if hit is not None:
                        by = _owner(sc, m, hit)
                        if by and 'stair' in by.lower():
                            # (the next flight of a pair in line stands where this one's head tile would be: the way
                            # goes on up it, not into it. Hlaalu's Stairs_H_01 over H_02, 12 of 146 game flights, 2026-11-04)
                            hit = 'chained'
                            break
                        res.update(ok=False, where='run', by=by, at=(round(px), round(py), round(gz + h)))
                        break
            if hit is None:
                hit = _hit(sc, (px, py, gz + 16), (0.0, 0.0, 1.0), HEAD, skip)
                if hit is not None:
                    res.update(ok=False, where='over', by=_owner(sc, m, hit), at=(round(px), round(py), round(gz + 16)))
            if hit is not None:
                break
            prev = (px, py, gz)
        out.append(res)
    return out


def _ends(db, r):
    """A one-tile kit stair's foot and head: the middles of the tiles below and above it, at its floors' heights; or None.
    By every kit's stairs (stairwellsurvey's list): by its own name's kit alone, Common plain's stairs, the Common family's,
    went unseen."""
    import kits
    import stairwellsurvey
    SP = _SP.get('sp') if _SP.get('recs') is db.recs else None
    if SP is None:
        SP = stairwellsurvey._stair_pieces(db)
        _SP.update(recs=db.recs, sp=SP)
    sp = SP.get(r['id'].lower())
    if not sp and r.get('ri') is not None and r['id'].lower().startswith('in_'):
        # (a kit stair no style's learning lists: measured from its model, a 256 tile)
        g = kits.stair_shape(db, r['ri'], 256, 200)
        sp = SP[r['id'].lower()] = {'id': r['id'], 'low': g['low'], 'z_low': g['bottom'] + 2, 'rise': g['rise'], 'tile': 256,
                                    'len': g.get('len', 1)} if g else None
    if not sp or sp.get('len', 1) != 1 or abs(r['p'][3]) > 0.05 or abs(r['p'][4]) > 0.05:
        return None
    q = int(round(r['p'][5] / (math.pi / 2))) % 4
    down = kits.SIDES[(kits.SIDES.index(sp['low']) + q) % 4]
    st = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}[down]
    # (z_low is where the floor piece's origin stands: its floor lies zmin under that, 128 for Hlaalu's mid-height
    # origins; walked from the origin's height, the way up ran 125 too high and hit the landing's pieces at the head:
    # 3 of 146 game flights, 2026-11-04)
    T, lower = sp['tile'], r['p'][2] + sp['z_low'] + (sp.get('zmin') or 0)
    ox, oy = r['p'][0], r['p'][1]
    if sp.get('cx') is not None:
        # (a stair whose origin is at one end of its model: the builder stands the model's middle on the tile
        # (builder._centred), so the tile's middle is the model's middle, not the origin. Telvanni (small)'s
        # in_t_stairs_strt_256 stood 136 off its origin, the walk started inside the wall of the tile before its
        # foot, and 9 flights of 9 read "closed over" in the lab, 2026-11-05)
        c_, s_ = math.cos(r['p'][5]), math.sin(r['p'][5])
        cx_, cy_ = sp['cx'], sp.get('cy') or 0.0
        ox, oy = ox + cx_ * c_ + cy_ * s_, oy - cx_ * s_ + cy_ * c_
    return (ox + st[0] * T, oy + st[1] * T, lower), (ox - st[0] * T, oy - st[1] * T, lower + sp['rise'])


_SP = {}


def _line(a, b):
    """Points every STEP_LEN from a to b (b left out: the next stretch starts there)."""
    L = math.dist(a, b)
    n = max(1, int(L / STEP_LEN))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, a[2] + (b[2] - a[2]) * i / n) for i in range(n)]


def _hit(sc, o, d, tmax, skip):
    """The first triangle a ray meets, from either side, leaving out the stair's own: its index or None."""
    seen = set(skip)
    got = sc._hits(o, d, tmax, seen, True, both=True)
    return got[1] if got else None


def _owner(sc, m, tri):
    k = sc.owner(tri)
    r = next((x for x in m['refs'] if x['k'] == k), None) if k else None
    return r['id'] if r else None
