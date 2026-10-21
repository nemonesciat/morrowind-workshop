"""How the game's own, hand-made interiors close the spaces round a staircase, style by style: what
stands over a stair's tile at every height, beside it on both floors, under the upper flight; and
what the game puts in a tile left without a floor piece (a stairwell, a double-height hall). The
pieces of the whole family count (a Common stone house climbs with the plain set's stairwell), as do
posts, walls and other statics named for the family. Read-only: a report for deciding how "Build from
pieces" should close its own stairwells, and the arrangement the builder copies (see column())."""
import math
import re
from collections import Counter, defaultdict

import kits
import mapdata
from mapdata import ref_info

_cache = {}
STEP = 64                 # heights are kept to the nearest 64


def _family(prefix):
    parts = prefix.lower().split('_')
    return '_'.join(parts[:-1]) if len(parts) >= 3 else prefix.lower()


def _cells_of(db, k, limit):
    cells = set()
    for ri in k['ris']:
        for ci in db.used_in.get(db.recs[ri][1].lower(), ()):
            if db.recs[ci][0] == 'CELL' and kits.game_made(db, db.recs[ci][7]):
                cells.add(db.recs[ci][7])
    cells = sorted(cells)
    if limit and len(cells) > limit:
        cells = cells[::max(1, len(cells) // limit)][:limit]
    return cells


def _bounds(db, cache, rid):
    low = rid.lower()
    if low not in cache:
        ri = db.resolve_id(rid)
        cache[low] = mapdata.object_bounds(db, ri) if ri is not None else None
    return cache[low]


def survey(db, prefix, limit=60):
    """For one style: {'cells': n, 'stairs': {stair id: {'n': instances, 'column': {(ix, iy, dz): Counter((id, dq))},
    'storey': the height the stair climbs (from what sits at its head)}}, 'holes': {'n': tiles without a
    floor piece inside a floor's footprint, 'filled': Counter(what stands in them), 'sides': Counter(what
    closes their outer sides)}}. ix across the stair, iy along its climb (in tiles), dz in units (to 64)."""
    key = (prefix, limit)
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    k = kits.kit_pieces(db, prefix)
    if not k:
        return None
    T = k['tile']
    fam = _family(prefix)
    own = {p['id'].lower() for p in k['pieces']}
    bcache = {}
    st_info = kits.stairs(db, prefix) or {'pieces': []}
    stair_ids = {p['id'].lower() for p in st_info['pieces']}
    out = {'cells': 0, 'stairs': {s: {'n': 0, 'column': defaultdict(Counter), 'storey': Counter()} for s in stair_ids},
           'holes': {'n': 0, 'filled': Counter(), 'sides': Counter(), 'levels': Counter()}, 'tile': T}
    for ck in _cells_of(db, k, limit):
        try:
            refs, _h = db.cell_refs(ck)
        except Exception:
            continue
        out['cells'] += 1
        items = []
        for ref in refs.values():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead or not pos:
                continue
            low = rid.lower()
            if low.startswith(fam + '_') or low in stair_ids or re.search(r'post|pillar|column', low):
                items.append((low, pos))
        # the floor pieces of the family on the grid, per level
        floor = {}
        for low, pos in items:
            kp = low in own or (kits.kit_prefix(low) and kits.kit_prefix(low).startswith(fam + '_') and
                                (kits.kit_pieces(db, kits.kit_prefix(low)) or {}).get('tile') == T and
                                any(p['id'].lower() == low for p in (kits.kit_pieces(db, kits.kit_prefix(low)) or {}).get('pieces', [])))
            if kp:
                floor[(round(pos[0] / T), round(pos[1] / T), round(pos[2] / STEP))] = low
        # --- round each stair, in its frame
        for low, sp in items:
            if low not in stair_ids:
                continue
            rec = out['stairs'][low]
            rec['n'] += 1
            c, s = math.cos(sp[5]), math.sin(sp[5])
            for low2, p in items:
                if p is sp:
                    continue
                dx, dy, dz = p[0] - sp[0], p[1] - sp[1], p[2] - sp[2]
                if abs(dx) > T * 1.6 or abs(dy) > T * 2.6 or abs(dz) > T * 2.2:
                    continue
                lx, ly = dx * c - dy * s, dx * s + dy * c
                ix, iy = round(lx / T), round(ly / T)
                if abs(lx / T - ix) > 0.3 or abs(ly / T - iy) > 0.3:
                    continue
                dq = int(round(((p[5] - sp[5]) % (2 * math.pi)) / (math.pi / 2))) % 4
                rec['column'][(ix, iy, int(round(dz / STEP)) * STEP)][(low2, dq)] += 1
                if (ix, iy) == (0, 1) and low2 in floor.values() and dz > 0:
                    rec['storey'][int(round(dz / STEP)) * STEP] += 1
        # --- tiles without a floor piece inside the footprint of a level
        levels = defaultdict(set)
        for (gx, gy, gz), low in floor.items():
            levels[gz].add((gx, gy))
        for gz, tiles in levels.items():
            if len(tiles) < 4:
                continue
            xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
            for gx in range(min(xs), max(xs) + 1):
                for gy in range(min(ys), max(ys) + 1):
                    if (gx, gy) in tiles:
                        continue
                    beside = sum(1 for d in ((1, 0), (-1, 0), (0, 1), (0, -1)) if (gx + d[0], gy + d[1]) in tiles)
                    if beside < 2:
                        continue
                    out['holes']['n'] += 1
                    out['holes']['levels'][gz * STEP] += 1
                    # what stands in the tile at about that level (any static of the family or a stair)
                    found = []
                    for low2, p in items:
                        if abs(p[0] - gx * T) < T * 0.4 and abs(p[1] - gy * T) < T * 0.4 and -T * 1.2 < p[2] - gz * STEP < T * 0.6:
                            found.append(low2 + ('@%+d' % (int(round((p[2] - gz * STEP) / STEP)) * STEP)))
                    out['holes']['filled'][tuple(sorted(set(found))) or ('nothing',)] += 1
                    # its sides that face no tile of this level: what stands there
                    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if (gx + d[0], gy + d[1]) in tiles:
                            continue
                        ex, ey = (gx + d[0] * 0.5) * T, (gy + d[1] * 0.5) * T
                        side = [low2 for low2, p in items if abs(p[0] - ex) < T * 0.3 and abs(p[1] - ey) < T * 0.3
                                and -T * 1.2 < p[2] - gz * STEP < T * 0.6 and low2 not in floor.values()]
                        out['holes']['sides'][tuple(sorted(set(side))) or ('nothing',)] += 1
    _cache[key] = (db.recs, out)
    return out


def column(db, prefix, stair_id):
    """The game's usual arrangement over and beside this stair, for the builder: {(ix, iy, dz): (id, dq)}
    where one answer holds in at least 4 cases in 10 and 3 cases at all."""
    s = survey(db, prefix)
    rec = (s or {}).get('stairs', {}).get(stair_id.lower())
    if not rec:
        return {}
    out = {}
    for spot, cnt in rec['column'].items():
        (pid, dq), n = cnt.most_common(1)[0]
        if n >= 3 and n >= 0.4 * rec['n']:
            out[spot] = (pid, dq)
    return out


def report(db, prefixes=None, limit=60):
    """The findings in words, style by style."""
    lines = []
    for prefix in sorted(prefixes or kits.kits(db)):
        s = survey(db, prefix, limit)
        if not s or not s['cells']:
            continue
        T = s['tile']
        lines.append('== %s (%s): %d places' % (prefix, kits.friendly(prefix), s['cells']))
        for sid, rec in sorted(s['stairs'].items(), key=lambda kv: -kv[1]['n']):
            if not rec['n']:
                continue
            lines.append('  stair %s: %d, climbs %s' % (sid, rec['n'], dict(rec['storey'].most_common(3))))
            for spot in sorted(rec['column'], key=lambda k_: (k_[2], k_[1], k_[0])):
                cnt = rec['column'][spot]
                top = cnt.most_common(3)
                if top[0][1] < max(2, 0.2 * rec['n']):
                    continue
                where = 'over it' if spot[:2] == (0, 0) else ('ahead %d' % spot[1] if spot[0] == 0 else ('beside %+d' % spot[0] + (' ahead %d' % spot[1] if spot[1] else '')))
                lines.append('     %-18s dz %+5d: %s' % (where, spot[2], ', '.join('%s q%d x%d' % (p, q, n) for (p, q), n in top)))
        h = s['holes']
        if h['n']:
            lines.append('  tiles without a floor piece inside a floor: %d; what stands in them: %s' % (
                h['n'], '; '.join('%s x%d' % ('+'.join(k_), n) for k_, n in h['filled'].most_common(6))))
            lines.append('     their outer sides closed by: %s' % '; '.join('%s x%d' % ('+'.join(k_), n) for k_, n in h['sides'].most_common(6)))
    return '\n'.join(lines)
