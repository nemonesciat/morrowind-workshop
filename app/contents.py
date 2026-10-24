"""What stands on a placed piece of furniture: the books on a bookshelf, the dishes on a table, the wares
on a counter, a stack of crates on a chest. Found from the geometry alone (the same box test the shelf
survey uses to read the game's dressings), so it works for things the game placed, things you placed and
things Auto-furnish placed alike. For "Select it with everything on it" on the right-click menu.
What stands on those comes too: the plants in a pot on a table, a candle on a book on a shelf."""
import mapdata
import shelfsurvey

EDGE = 12          # (a thing may overhang the furniture's edge by this much and still count as on it)
ABOVE = 48         # (how far above the furniture's top a thing's bottom may be and still be on it: a stack on a
                   # crate; more and a wall shelf would claim what stands on the shelf above it)
RAISED = 20        # (a thing whose bottom is this far above the piece's bottom rests on it, not beside it, so its
                   # middle being over the piece is enough: a flower spreading past its pot, a pillow off a bed's edge)
DEPTH = 3          # (how many layers deep: table, pot, plant)


def _box(r):
    p = r['p']
    ob = shelfsurvey.box_turned(r['b'], p[3], p[4], p[5], r.get('s') or 1.0)
    return [p[0] + ob[0], p[1] + ob[1], p[2] + ob[2], p[0] + ob[3], p[1] + ob[4], p[2] + ob[5]]


def _on(base, refs, taken):
    fb = _box(base)
    bottom, top = fb[2], fb[5]
    out = []
    for r in refs:
        if r is base or r.get('arch') or not r.get('b') or r.get('k') is None or r['k'] in taken:
            continue
        if r['type'] in ('NPC_', 'CREA', 'DOOR', 'LEVC'):
            continue
        ob = _box(r)
        # standing on it: its bottom between the piece's bottom and a way above its top (the shelves
        # inside a bookshelf are above its bottom; a stack on a crate is above its top)
        low = ob[2]
        if low < bottom - 8 or low > top + ABOVE:
            continue
        # its whole footprint inside the piece's, a little overhang allowed
        inside = not (ob[0] < fb[0] - EDGE or ob[3] > fb[3] + EDGE or ob[1] < fb[1] - EDGE or ob[4] > fb[4] + EDGE)
        if not inside:
            # or resting on it, wider than it: its middle over the piece, and the piece the nearest thing
            # under it (not a chair or a sack under the table it stands on)
            cx, cy = (ob[0] + ob[3]) / 2, (ob[1] + ob[4]) / 2
            if low <= bottom + RAISED or not (fb[0] - EDGE <= cx <= fb[3] + EDGE and fb[1] - EDGE <= cy <= fb[4] + EDGE):
                continue
            if _under(r, ob, cx, cy, refs) is not base:
                continue
        out.append(r)
    return out


def _under(r, ob, cx, cy, refs):
    """The thing whose top is nearest below this one's bottom, under its middle."""
    best, bz = None, None
    for u in refs:
        if u is r or not u.get('b') or u['type'] in ('NPC_', 'CREA', 'LEVC'):
            continue
        ub = _box(u)
        if not (ub[0] <= cx <= ub[3] and ub[1] <= cy <= ub[4]) or ub[5] > ob[2] + 6 or ub[2] >= ob[2]:
            continue
        if bz is None or ub[5] > bz:
            best, bz = u, ub[5]
    return best


def on_piece(db, cell_key, refkey):
    """{'piece': refkey, 'on': [refkeys of the things standing on it, and on those], 'n': count}."""
    m = mapdata.cellmap(db, cell_key)
    base = next((r for r in m['refs'] if r.get('k') == refkey), None)
    if not base or not base.get('b'):
        return {'piece': refkey, 'on': [], 'n': 0}
    taken = {refkey}
    out, layer = [], [base]
    for _ in range(DEPTH):
        nxt = []
        for b in layer:
            for r in _on(b, m['refs'], taken):
                taken.add(r['k'])
                out.append(r['k'])
                nxt.append(r)
        layer = nxt
        if not layer:
            break
    return {'piece': refkey, 'on': out, 'n': len(out)}
