"""What stands on a placed piece of furniture: the books on a bookshelf, the dishes on a table, the wares
on a counter, a stack of crates on a chest. Found from the geometry alone (the same box test the shelf
survey uses to read the game's dressings), so it works for things the game placed, things you placed and
things Auto-furnish placed alike. For "Select it with everything on it" on the right-click menu."""
import mapdata
import shelfsurvey

EDGE = 12          # (a thing may overhang the furniture's edge by this much and still count as on it)
ABOVE = 48         # (how far above the furniture's top a thing's bottom may be and still be on it: a stack on a
                   # crate; more and a wall shelf would claim what stands on the shelf above it)


def on_piece(db, cell_key, refkey):
    """{'piece': refkey, 'on': [refkeys of the things standing on it], 'n': count}."""
    m = mapdata.cellmap(db, cell_key)
    base = next((r for r in m['refs'] if r.get('k') == refkey), None)
    if not base or not base.get('b'):
        return {'piece': refkey, 'on': [], 'n': 0}
    bx, by, bz, brx, bry, brz = base['p']
    bs = base.get('s') or 1.0
    fb = shelfsurvey.box_turned(base['b'], brx, bry, brz, bs)      # (the piece's box, turned as it stands)
    top = bz + fb[5]
    bottom = bz + fb[2]
    out = []
    for r in m['refs']:
        if r is base or r.get('arch') or not r.get('b') or r.get('k') is None:
            continue
        if r['type'] in ('NPC_', 'CREA', 'DOOR', 'LEVC'):
            continue
        p = r['p']
        s = r.get('s') or 1.0
        ob = shelfsurvey.box_turned(r['b'], p[3], p[4], p[5], s)
        # its footprint inside the piece's footprint (a little overhang allowed)
        if p[0] + ob[0] < bx + fb[0] - EDGE or p[0] + ob[3] > bx + fb[3] + EDGE:
            continue
        if p[1] + ob[1] < by + fb[1] - EDGE or p[1] + ob[4] > by + fb[4] + EDGE:
            continue
        # standing on it: its bottom between the piece's bottom and a way above its top (the shelves
        # inside a bookshelf are above its bottom; a stack on a crate is above its top)
        low = p[2] + ob[2]
        if low < bottom - 8 or low > top + ABOVE:
            continue
        out.append(r['k'])
    return {'piece': refkey, 'on': out, 'n': len(out)}
