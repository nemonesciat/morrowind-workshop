"""Settle: what lies loose in a spot falls into place, as if gravity and a high friction held for a moment.

Morrowind has no gravity for placed things: a cup is wherever it was put, a hair over the table or sunk into
it, a crate half in the floor (the user's hut: crates laid with their model's root shift ignored, 32 into
the floor in game). Settling puts each loose thing in a spot (or the ones selected) to rest on what is
under it, by the real triangles of both: its own mesh's lowest point at a grid of spots across it, against
the first surface under each (furniture, floors, shelves, the things settled before it, the land
outdoors). Lowest things first, so a plate settles on the table before the bread settles on the plate.

- Floating: it drops until its lowest point touches (no further than max_drop: a lantern on its chain, a
  sword on its pegs, a picture on a wall have nothing near under them and stay).
- Sunk: it rises out of a surface it is sunk into (up to half its height; a book through the board over
  it is "too tall", not sunk, and is left to the shelf's own rules).
- Hanging off an edge, its middle over air: nudged back over what holds it (a few units; high friction,
  so nothing slides on its own).
- Through a neighbour: pushed apart along the shorter way out, then settled again.

Turns are kept: the game's things are laid level or tilted on purpose. Returns the moves, for one Undo."""
import math

import mapdata
import seethrough
from shelfsurvey import box_turned

ITEMS = set(mapdata.ITEM_TYPES)
SMALL = 140.0                  # (a crate, a sack, a basket, a small statue: settled too; furniture and pieces never)
STILL = ('NPC_', 'CREA', 'LEVC', 'LEVI', 'DOOR')


def _model(db, r):
    return db.recs[r['ri']][5] if r.get('ri') is not None else ''


def _size(r):
    b, s = r.get('b'), r.get('s') or 1.0
    return max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) * s if b else 0.0


SUNK_ON_PURPOSE = ('flora', 'plant', 'kelp', 'mushroom', 'shrub', 'grass', 'lilypad', 'moss', 'vine', 'ivy', 'root_', 'roots')


def loose(r, chosen=False):
    """Whether a placed thing may be settled: an item, or a small container or static clutter; never a
    building piece, a door or a person. Furniture (a chair, a planter) only when chosen by hand; plants
    never (the game sinks them into their soil and pots on purpose)."""
    if r.get('arch') or r['type'] in STILL or not r.get('b'):
        return False
    low = r['id'].lower()
    if any(w in low for w in SUNK_ON_PURPOSE) or (r['type'] == 'INGR' and 'flor' in low):
        return False
    if r['type'] == 'LIGH':
        # (a candle or a lamp standing on something; never a chandelier, a lantern or anything hung)
        return _size(r) <= 40 and not any(w in low for w in ('chandelier', 'lantern', 'hang', 'chain', 'sconce'))
    if r['type'] in ITEMS:
        return True
    if not chosen and 'furn' in low:
        return False
    return r['type'] in ('CONT', 'STAT', 'ACTI') and _size(r) <= SMALL


def _box(r, p=None):
    p = p or r['p']
    tb = box_turned(r['b'], p[3], p[4], p[5], r.get('s') or 1.0)
    return (p[0] + tb[0], p[1] + tb[1], p[2] + tb[2], p[0] + tb[3], p[1] + tb[4], p[2] + tb[5])


def _up_facing(sc, n):
    """The face's normal points up (a floor, a board's top, a table top), seen the way the game draws it."""
    x0, y0, z0, ax, ay, az, bx, by, bz = sc.tris[n]
    nz = ax * by - ay * bx
    ln = math.sqrt((ay * bz - az * by) ** 2 + (az * bx - ax * bz) ** 2 + nz ** 2) or 1.0
    if sc.two[n]:
        return abs(nz) / ln > 0.7                # (drawn from both sides: level is enough)
    # (the side the game draws faces up, by seethrough's FRONT rule: a ray coming down meets its front; a
    # floor a crate is sunk into is met from behind by the ray going up)
    return nz * seethrough.FRONT / ln > 0.7


def settle(db, cell, at=None, radius=200.0, refs=None, max_drop=48.0):
    """{'moves': [{cell, ref, p, s}], 'report': {...}}: what in the spot (at, within radius; or the refs
    given, ref keys) settles, and where to."""
    m = mapdata.cellmap(db, cell)
    if not m.get('exists'):
        return {'moves': [], 'report': {'note': 'There is no place called %s.' % cell}}
    allr = m['refs']
    keys = set(refs or ())
    if keys:
        pick = [r for r in allr if r['k'] in keys and loose(r, chosen=True)]
    else:
        if not at:
            return {'moves': [], 'report': {'note': 'Nowhere to settle.'}}
        ax_, ay_, az_ = at[0], at[1], at[2] if len(at) > 2 and at[2] is not None else None
        pick = []
        for r in allr:
            if not loose(r) or math.hypot(r['p'][0] - ax_, r['p'][1] - ay_) > radius:
                continue
            if az_ is not None and abs(r['p'][2] - az_) > max(radius, 160):
                continue                     # (one storey: not the things upstairs)
            pick.append(r)
    # (what the game hangs, it hangs: an anchor, a planter on its chain, a lantern, a sign. Never dropped,
    # chosen or not; hangsurvey.py. While that survey is still learning, the drop limit holds them)
    import hangsurvey
    hung = [r for r in pick if hangsurvey.hangs(db, hangsurvey.model_of(db, r), r['id'])]
    pick = [r for r in pick if r not in hung]
    if not pick:
        return {'moves': [], 'report': {'note': 'Nothing loose there to settle.', 'n': 0, 'hung': [r['k'] for r in hung]}}
    picked = {r['k'] for r in pick}
    boxes = [_box(r) for r in pick]
    lo = (min(b[0] for b in boxes) - 300, min(b[1] for b in boxes) - 300)
    hi = (max(b[3] for b in boxes) + 300, max(b[4] for b in boxes) + 300)
    # what holds them: everything else near, by its triangles
    sc = seethrough.Scene()
    for r in allr:
        if r['k'] in picked or r['type'] in ('NPC_', 'CREA', 'LEVC', 'LEVI'):
            continue
        if not (lo[0] <= r['p'][0] <= hi[0] and lo[1] <= r['p'][1] <= hi[1]):
            if not (r.get('arch') and _size(r) > 300):
                continue                     # (big pieces reach in from further off: a floor's middle)
        mdl = _model(db, r)
        if not mdl or 'marker' in mdl.lower():
            continue
        sc.add_model(seethrough.model_tris(db, mdl), r['p'], r.get('s') or 1.0)
    land = _land_at(db) if m.get('info', {}).get('exterior') or cell.startswith('#') else None
    order = sorted(pick, key=lambda r: _box(r)[2])
    moves, rep = [], {'n': len(pick), 'dropped': 0, 'raised': 0, 'nudged': 0, 'apart': 0, 'left': 0}
    done = []                                # (box, ref) of the ones settled already
    for r in order:
        p = list(r['p'])
        own_tris = seethrough.model_tris(db, _model(db, r))
        if not own_tris:
            rep['left'] += 1
            continue
        moved = False
        dz = None
        counted = set()
        last_xy = None
        for _round in range(4):
            # (it may rise out of what it's sunk in once, at the start; after that it only falls: a thing
            # lifted onto a board would otherwise find the board over it and climb again)
            dz, contacts, centre, over_air = _drop(sc, own_tris, r, p, max_drop, land, may_rise=_round == 0)
            if dz is None:
                break
            if _round and (dz < -6.0 or dz > 0.5):
                # (a nudge or a push that would send it over an edge: taken back; it stays where it rested)
                if last_xy:
                    p[0], p[1], p[2] = last_xy
                break
            if abs(dz) >= 0.3:
                p[2] += dz
                moved = True
                kind = 'raised' if dz > 0 else 'dropped'
                if kind not in counted:
                    rep[kind] += 1
                    counted.add(kind)
            # its weight over air: back over what holds it, a little (not a book nor anything tilted: those
            # lean on their neighbours, as the game leans them)
            tilted = abs(p[3]) > 0.05 or abs(p[4]) > 0.05
            if contacts and over_air and not tilted and r['type'] != 'BOOK':
                cx = sum(c[0] for c in contacts) / len(contacts)
                cy = sum(c[1] for c in contacts) / len(contacts)
                d = math.hypot(cx - centre[0], cy - centre[1])
                if d > 0.5 and math.hypot(p[0] - r['p'][0], p[1] - r['p'][1]) < 12:
                    k = min(d, 8.0) / d
                    last_xy = (p[0], p[1], p[2])
                    p[0] += (cx - centre[0]) * k
                    p[1] += (cy - centre[1]) * k
                    if 'nudged' not in counted:
                        rep['nudged'] += 1
                        counted.add('nudged')
                    moved = True
                    continue
            # through a thing settled before it (really through: a third of the smaller one's box, not two
            # books touching in a row): apart, the shorter way
            bx = _box(r, p)
            va = max(1.0, (bx[3] - bx[0]) * (bx[4] - bx[1]) * (bx[5] - bx[2]))
            push = None
            for b2, _r2 in done:
                ox = min(bx[3], b2[3]) - max(bx[0], b2[0])
                oy = min(bx[4], b2[4]) - max(bx[1], b2[1])
                oz = min(bx[5], b2[5]) - max(bx[2], b2[2])
                vb = max(1.0, (b2[3] - b2[0]) * (b2[4] - b2[1]) * (b2[5] - b2[2]))
                if ox > 1.5 and oy > 1.5 and oz > 1.5 and ox * oy * oz > 0.33 * min(va, vb) and bx[2] < b2[5] - 2:
                    cxa, cxb = (bx[0] + bx[3]) / 2, (b2[0] + b2[3]) / 2
                    cya, cyb = (bx[1] + bx[4]) / 2, (b2[1] + b2[4]) / 2
                    push = ((ox + 0.5) * (1 if cxa >= cxb else -1), 0.0) if ox <= oy else (0.0, (oy + 0.5) * (1 if cya >= cyb else -1))
                    break
            if push and math.hypot(p[0] + push[0] - r['p'][0], p[1] + push[1] - r['p'][1]) <= 12:
                last_xy = (p[0], p[1], p[2])
                p[0] += push[0]
                p[1] += push[1]
                if 'apart' not in counted:
                    rep['apart'] += 1
                    counted.add('apart')
                moved = True
                continue
            break
        if dz is None and not moved:
            rep['left'] += 1
        if moved and (abs(p[0] - r['p'][0]) > 0.05 or abs(p[1] - r['p'][1]) > 0.05 or abs(p[2] - r['p'][2]) > 0.05):
            moves.append({'cell': cell, 'ref': r['k'], 'p': [round(v, 2) if i < 3 else v for i, v in enumerate(p)], 's': r.get('s') or 1.0})
        # (what is settled now holds what comes after it)
        sc.add_model(own_tris, p, r.get('s') or 1.0)
        done.append((_box(r, p), r))
    rep['moved'] = len(moves)
    rep['hung'] = [r['k'] for r in hung]
    return {'moves': moves, 'report': rep}


def _verts(own_tris, p, s):
    """The model's corners in the world, as it stands (each once)."""
    me = seethrough.Scene()
    me.add_model(own_tris, p, s)
    seen, out = set(), []
    for x0, y0, z0, ax, ay, az, bx, by, bz in me.tris:
        for v in ((x0, y0, z0), (x0 + ax, y0 + ay, z0 + az), (x0 + bx, y0 + by, z0 + bz)):
            k = (round(v[0], 1), round(v[1], 1), round(v[2], 1))
            if k not in seen:
                seen.add(k)
                out.append(v)
    return out


def _drop(sc, own_tris, r, p, max_drop, land, may_rise=True):
    """How far it falls (negative) or rises (positive) to rest: from its own mesh's lowest corners (a chair's
    feet, a bowl's rim, a book's edge), each against the first surface under it (or, at the start, a floor
    or a board's top it is sunk under, within half its height). (dz or None, contact spots, its weight's
    middle, weight over air)."""
    verts = _verts(own_tris, p, r.get('s') or 1.0)
    if not verts:
        return None, [], None, False
    zb = min(v[2] for v in verts)
    zt = max(v[2] for v in verts)
    h = max(1.0, zt - zb)
    # (its very bottom: a chair's feet, a bowl's foot ring, a book's lower edge; not corners further up, or a
    # book sunk a little into a board it stands on reads as half sunk and falls through to the board below)
    low = sorted((v for v in verts if v[2] <= zb + max(1.5, 0.06 * h)), key=lambda v: v[2])[:240]
    gaps = []
    # sunk only when most of its low corners are under a floor or a board's top: a crate's back corners
    # poking into the wall's base (the user's hut: lifted 29 onto the skirting) are the wall, not a floor
    if may_rise:
        sunk = 0
        for x, y, z in low:
            z_ = z + 0.5
            for _ in range(3):
                up = sc.nearest_any((x, y, z_), (0.0, 0.0, 1.0), z + 0.55 * h - z_)
                if up is None:
                    break
                if _up_facing(sc, up[1]):
                    sunk += 1
                    break
                z_ += up[0] + 0.3
        may_rise = sunk > 0.6 * len(low)
        if may_rise:
            # (and under its middle too: a book's front corners in a shelf's lip are not a book sunk in the board)
            mx = sum(v[0] for v in low) / len(low)
            my = sum(v[1] for v in low) / len(low)
            z_, mid = zb + 0.5, False
            for _ in range(3):
                up = sc.nearest_any((mx, my, z_), (0.0, 0.0, 1.0), zb + 0.55 * h - z_)
                if up is None:
                    break
                if _up_facing(sc, up[1]):
                    mid = True
                    break
                z_ += up[0] + 0.3
            may_rise = mid
    for x, y, z in low:
        sz = None
        if may_rise:
            # (past a slab's underside to its top: the floor a crate is sunk into is met from below first)
            z_ = z + 0.5
            for _ in range(3):
                up = sc.nearest_any((x, y, z_), (0.0, 0.0, 1.0), z + 0.55 * h - z_)
                if up is None:
                    break
                if _up_facing(sc, up[1]):
                    sz = z_ + up[0]
                    break
                z_ += up[0] + 0.3
        if sz is None:
            # (a corner just under a board's top rests in that board: it never falls through a board
            # drawn only from above to the one under it)
            near = sc.nearest_any((x, y, z + 0.5), (0.0, 0.0, 1.0), 6.0)
            if near is not None and _up_facing(sc, near[1]):
                sz = z
        if sz is None:
            dn = sc.nearest_any((x, y, z + 0.5), (0.0, 0.0, -1.0), max_drop + 1.0)
            sz = z + 0.5 - dn[0] if dn is not None else None
        if land is not None:
            lz = land(x, y)
            if lz is not None and (sz is None or lz > sz) and z - lz <= max_drop and (lz - z <= 0.55 * h if may_rise else lz <= z + 0.5):
                sz = lz
        if sz is not None:
            gaps.append((x, y, z - sz))
    if not gaps:
        return None, [], None, False
    rest = min(g for _x, _y, g in gaps)          # (it rests on its highest contact)
    if rest < -0.3:
        # (rising only with room over it for the whole lift: a book stood in a shelf's front lip would
        # otherwise come up into the board over it)
        tops = sorted((v for v in verts if v[2] >= zt - max(1.0, 0.04 * h)), key=lambda v: -v[2])[:12]
        for x, y, z in tops:
            hit = sc.nearest_any((x, y, z - 0.5), (0.0, 0.0, 1.0), -rest + 1.0)
            if hit is not None:
                rest = 0.0
                gaps = [(x_, y_, max(0.0, g)) for x_, y_, g in gaps]
                break
    contacts = [(x, y) for x, y, g in gaps if g - rest < 1.5]
    # (its weight's middle, from the whole model; over air when outside what holds it)
    centre = (sum(v[0] for v in verts) / len(verts), sum(v[1] for v in verts) / len(verts))
    cx0, cx1 = min(c[0] for c in contacts) - 2, max(c[0] for c in contacts) + 2
    cy0, cy1 = min(c[1] for c in contacts) - 2, max(c[1] for c in contacts) + 2
    over_air = not (cx0 <= centre[0] <= cx1 and cy0 <= centre[1] <= cy1)
    return -rest, contacts, centre, over_air


def _land_at(db):
    """The land's height at a spot outdoors (None where there is no land)."""
    import landscape
    cache = {}

    def at(x, y):
        gx, gy = int(math.floor(x / 8192.0)), int(math.floor(y / 8192.0))
        if (gx, gy) not in cache:
            L = mapdata.land(db, gx, gy)
            cache[(gx, gy)] = L.get('h') if L.get('exists') else None
        h = cache[(gx, gy)]
        return landscape._height_at(h, gx, gy, x, y) if h else None
    return at
