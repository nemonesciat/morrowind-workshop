"""How the game mixes a style's piece variants (two or three versions of a side or corner piece: plain,
with a niche, with an arch), and what it hangs from each floor piece's ceiling (a lantern under a hall
piece, a chandelier under a room centre), learned from its own hand-made interiors.

variants(db, style): for each pattern (the walls a piece has), the variants the game uses, their shares,
and how often two of the same kind side by side are the same variant (a run) rather than mixed.
hangings(db, style): for each floor piece, what hangs from it, where (in the piece's own frame) and
how often an instance of the piece has one."""
import math
from collections import Counter, defaultdict

import kits
from mapdata import ref_info, object_bounds

_cache = {}
SIDES = 'NESW'


def _canon(pattern):
    """A pattern as a string, the same for every turn of the piece."""
    return min(''.join(kits.rotate(pattern, q)[s][0].upper() for s in SIDES) for q in range(4))


def _walk(db, style, limit=60):
    """The game's cells built with this style: [(cell, [(id, pos)] of its pieces, [(id, pos, bottom, top)] of
    everything else)]."""
    key = ('walk', style, limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    kp = kits.kit_pieces(db, style)
    ids = {p['id'].lower(): p for p in kp['pieces']} if kp else {}
    counts = Counter()
    for low in ids:
        for ci in db.used_in.get(low, ()):
            r = db.recs[ci]
            if r[0] == 'CELL' and kits.game_made(db, r[7]):
                counts[r[7]] += 1
    out = []
    bnd = {}
    for ck, _n in counts.most_common(limit):
        refs, _h = db.cell_refs(ck)
        pieces, others = [], []
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead or not pos:
                continue
            low = rid.lower()
            if low in ids:
                pieces.append((low, pos))
            else:
                if low not in bnd:
                    ri = db.resolve_id(rid)
                    bnd[low] = (object_bounds(db, ri), db.recs[ri][0]) if ri is not None else (None, '')
                b, tag = bnd[low]
                if b:
                    others.append((low, pos, pos[2] + b[2] * (sc or 1), pos[2] + b[5] * (sc or 1), tag))
        out.append((ck, pieces, others))
    _cache[key] = (db.recs, out)
    return out


def variants(db, style):
    key = ('variants', style)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    kp = kits.kit_pieces(db, style)
    if not kp:
        return {}
    T = kp['tile']
    ids = {p['id'].lower(): p for p in kp['pieces']}
    shape = {low: _canon(p['pattern']) for low, p in ids.items()}
    use = defaultdict(Counter)
    same = defaultdict(lambda: [0, 0])          # shape -> [neighbours of the same shape, of them the same variant]
    for ck, pieces, _o in _walk(db, style):
        at = {}
        for low, pos in pieces:
            at[(round(pos[0] / T), round(pos[1] / T), round(pos[2] / 64))] = low
            use[shape[low]][low] += 1
        for (x, y, z), low in at.items():
            for dx, dy in ((1, 0), (0, 1)):
                o = at.get((x + dx, y + dy, z))
                if o and shape[o] == shape[low]:
                    same[shape[low]][0] += 1
                    same[shape[low]][1] += (o == low)
    out = {}
    for sh, c in use.items():
        n = sum(c.values())
        if len(c) < 2 or n < 10:
            continue
        pairs, alike = same[sh]
        out[sh] = {'n': n, 'variants': [(ids[low]['id'], round(k / n, 2)) for low, k in c.most_common()],
                   'run': round(alike / pairs, 2) if pairs else None}
    _cache[key] = (db.recs, out)
    return out


def hangings(db, style):
    """What hangs from each floor piece (lights and chandeliers well above the floor, inside the tile):
    {piece id: {'n': instances, 'with': [(id, share, (lx, ly, dz) median)]}}."""
    key = ('hangings', style)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    kp = kits.kit_pieces(db, style)
    if not kp:
        return {}
    T, H = kp['tile'], kp['height']
    ids = {p['id'].lower(): p for p in kp['pieces']}
    n_inst = Counter()
    found = defaultdict(lambda: defaultdict(list))
    for ck, pieces, others in _walk(db, style):
        for low, pos in pieces:
            n_inst[low] += 1
            floor = pos[2] + ids[low]['zmin']
            c, s = math.cos(pos[5]), math.sin(pos[5])
            got = set()
            for oid, op, bot, top, tag in others:
                if abs(op[0] - pos[0]) > T / 2 or abs(op[1] - pos[1]) > T / 2:
                    continue
                if not (floor + H * 0.55 < top <= floor + H + 40 and bot > floor + 60):
                    continue                           # (hangs, high up: not on the floor or a table)
                if tag not in ('LIGH', 'STAT', 'ACTI') or oid in got:
                    continue
                got.add(oid)
                dx, dy = op[0] - pos[0], op[1] - pos[1]
                lx, ly = dx * c - dy * s, dx * s + dy * c
                found[low][oid].append((round(lx), round(ly), round(op[2] - floor)))
    out = {}
    for low, d in found.items():
        n = n_inst[low]
        lst = []
        for oid, offs in sorted(d.items(), key=lambda kv: -len(kv[1])):
            if len(offs) < 3 or len(offs) < 0.08 * n:
                continue
            med = tuple(sorted(o[i] for o in offs)[len(offs) // 2] for i in range(3))
            lst.append((db.recs[db.resolve_id(oid)][1], round(len(offs) / n, 2), med))
        if lst:
            out[ids[low]['id']] = {'n': n, 'with': lst[:5]}
    _cache[key] = (db.recs, out)
    return out
