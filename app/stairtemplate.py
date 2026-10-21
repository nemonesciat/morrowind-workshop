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
    out = {}
    for (ix, iy, dz), lst in _raw(db, style, stair_id, limit)[0].items():
        c = out.setdefault((ix, iy, round(dz / _tile(db, style))), Counter())
        for pid, dq, n in lst:
            c[(pid, dq)] += n
    return {k: [(pid, dq, n) for (pid, dq), n in v.most_common()] for k, v in out.items()}


def _tile(db, style):
    kp = kits.kit_pieces(db, style)
    return kp['tile'] if kp else 256


def _raw(db, style, stair_id, limit=40):
    """The survey by exact height: ({(ix, iy, dz to 16 units): [(piece id, dq, count)]}, how many of
    the stair were looked at). A style's stair may have its origin half way up (Hlaalu's hall_stairsl
    sits 128 over the lower floor and 128 under the upper), so the floors show here as dz -128 and
    +128, not as storeys."""
    key = (style, stair_id.lower())
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    cases = 0
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
            cases += 1
            c, s = math.cos(sp[5]), math.sin(sp[5])
            for rid, p in items:
                if rid == low or p is sp:
                    continue
                dx, dy, dz = p[0] - sp[0], p[1] - sp[1], p[2] - sp[2]
                if abs(dx) > T * 2.5 or abs(dy) > T * 2.5 or abs(dz) > T * 1.2:
                    continue
                lx, ly = dx * c - dy * s, dx * s + dy * c
                ix, iy = round(lx / T), round(ly / T)
                if abs(lx / T - ix) > 0.2 or abs(ly / T - iy) > 0.2:
                    continue                      # (not on the grid: not a piece in a tile)
                dq = int(round(((p[5] - sp[5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                around.setdefault((ix, iy, int(round(dz / 16.0)) * 16), Counter())[(ids[rid], dq)] += 1
    out = ({k: [(pid, dq, n) for (pid, dq), n in v.most_common()] for k, v in around.items()}, cases)
    _cache[key] = (db.recs, out)
    return out


def _usual(lists, least=0):
    """{spot: (id, dq)} where one answer holds in at least 4 cases in 10 of what stands at that spot,
    and at least 3 (or `least`) cases at all."""
    out = {}
    for k, lst in lists.items():
        total = sum(n for _p, _q, n in lst)
        pid, dq, n = lst[0]
        if n >= max(3, least) and n >= 0.4 * total:
            out[k] = (pid, dq)
    return out


def template(db, style, stair_id):
    """The piece and turn the game (mostly) uses at each tile round this stair: {(ix, iy, iz): (id, dq)},
    only where seen at least 3 times and in at least 4 cases in 10 at that spot."""
    return _usual(survey(db, style, stair_id))


def floors(db, style, stair_id, z_low, rise):
    """The same, by the floor each piece stands on: {(ix, iy, level): (id, dq)}, level 0 the floor the
    stair climbs from (its floor pieces' origins z_low from the stair's, see kits.stairs) and 1 the
    floor it comes out on (rise higher). Pieces standing at neither height (a cap over the stairwell,
    the next flight of a stacked stairwell) are left out, and so is a spot where fewer than 4 in 10
    of the stair's cases have that piece (a spot that only a few cases fill at all says nothing).
    This is what the builder lays round a stair: the game's own arrangement, floor by floor, for any
    style whose places show one."""
    out = {}
    raw, cases = _raw(db, style, stair_id)
    for (ix, iy, dz), lst in raw.items():
        lv = (dz - z_low) / float(rise or 1)
        if abs(lv - round(lv)) > 0.25 or round(lv) not in (0, 1):
            continue
        c = out.setdefault((ix, iy, int(round(lv))), Counter())
        for pid, dq, n in lst:
            c[(pid, dq)] += n
    return _usual({k: [(pid, dq, n) for (pid, dq), n in v.most_common()] for k, v in out.items()}, 0.4 * cases)


def voids(db, style, stair_id, z_low, rise, share=0.3):
    """The spots round this stair where the game's places mostly have no floor piece at all, by floor
    (as in `floors`): {(ix, iy, level)} for the spots within two tiles where fewer than `share` of the
    cases have one. Hlaalu's stairwell is such a column: nothing over the lower landing and nothing
    under the upper one, the stair climbs through."""
    raw, cases = _raw(db, style, stair_id)
    have = Counter()
    for (ix, iy, dz), lst in raw.items():
        lv = (dz - z_low) / float(rise or 1)
        if abs(lv - round(lv)) > 0.25 or round(lv) not in (0, 1):
            continue
        have[(ix, iy, int(round(lv)))] += sum(n for _p, _q, n in lst)
    out = set()
    for ix in range(-2, 3):
        for iy in range(-2, 3):
            for lv in (0, 1):
                if (ix, iy) != (0, 0) and have[(ix, iy, lv)] < share * cases:
                    out.add((ix, iy, lv))
    return out


def world_tile(stair_xy, q, ix, iy, T):
    """The world tile centre for a template offset, for a stair turned q quarter turns."""
    rz = q * math.pi / 2
    c, s = math.cos(rz), math.sin(rz)
    lx, ly = ix * T, iy * T
    return stair_xy[0] + lx * c + ly * s, stair_xy[1] - lx * s + ly * c
