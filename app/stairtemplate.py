"""How the game's own, hand-made interiors arrange the pieces round a staircase: for a style's stair
piece, which floor piece stands at each tile round it, and how it is turned relative to the stair
(Indoril's Room_Stair_H_01 has a Hall_Corner on either side, turned to face each other, a Room_Side
below and Room_Corners at the far corners). "Build from pieces" lays the same pieces round its stairs
where the room allows, so the curved rims and corners come out mirrored the way the game has them."""
import math
from collections import Counter

import kits
from mapdata import ref_info

_cache = {}


def survey(db, style, stair_id, limit=40):
    """{(ix, iy, iz): [(piece id, quarter turns relative to the stair, count)]} in the stair's own frame:
    ix across, iy along (negative = below its low end), iz storeys, in tiles. Only the style's own floor
    pieces, from the game's cells."""
    key = (style, stair_id.lower())
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    kp = kits.kit_pieces(db, style)
    T = kp['tile'] if kp else 256
    ids = {p['id'].lower(): p['id'] for p in (kp['pieces'] if kp else [])}
    low = stair_id.lower()
    cells = sorted({db.recs[ci][7] for ci in db.used_in.get(low, ()) if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7])})
    around = {}
    for ck in cells[:limit]:
        refs, _h = db.cell_refs(ck)
        items = []
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if not dead and pos and (rid.lower() in ids or rid.lower() == low):
                items.append((rid.lower(), pos))
        for sid, sp in items:
            if sid != low:
                continue
            c, s = math.cos(sp[5]), math.sin(sp[5])
            for rid, p in items:
                if rid == low or p is sp:
                    continue
                dx, dy, dz = p[0] - sp[0], p[1] - sp[1], p[2] - sp[2]
                if abs(dx) > T * 2.5 or abs(dy) > T * 2.5 or abs(dz) > T * 1.2:
                    continue
                lx, ly = dx * c - dy * s, dx * s + dy * c
                ix, iy, iz = round(lx / T), round(ly / T), round(dz / T)
                if abs(lx / T - ix) > 0.2 or abs(ly / T - iy) > 0.2:
                    continue                      # (not on the grid: not a piece in a tile)
                dq = int(round(((p[5] - sp[5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                around.setdefault((ix, iy, iz), Counter())[(ids[rid], dq)] += 1
    out = {k: [(pid, dq, n) for (pid, dq), n in v.most_common()] for k, v in around.items()}
    _cache[key] = (db.recs, out)
    return out


def template(db, style, stair_id):
    """The piece and turn the game (mostly) uses at each tile round this stair: {(ix, iy, iz): (id, dq)},
    only where seen at least 3 times and in at least 4 cases in 10 at that spot."""
    out = {}
    for k, lst in survey(db, style, stair_id).items():
        total = sum(n for _p, _q, n in lst)
        pid, dq, n = lst[0]
        if n >= 3 and n >= 0.4 * total:
            out[k] = (pid, dq)
    return out


def world_tile(stair_xy, q, ix, iy, T):
    """The world tile centre for a template offset, for a stair turned q quarter turns."""
    rz = q * math.pi / 2
    c, s = math.cos(rz), math.sin(rz)
    lx, ly = ix * T, iy * T
    return stair_xy[0] + lx * c + ly * s, stair_xy[1] - lx * s + ly * c
