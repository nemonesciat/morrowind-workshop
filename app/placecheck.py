"""Health check for a furnished place ("Check this place" in the Place panel): the faults Auto-furnish's
own lab tests look for, found in any interior (built by the Workshop or by hand) and listed with markers
and fixes, the way Find gaps does. The gap finder's own findings come in the same list (fixit.scan:
gaps, doorways that lead nowhere, missing ceilings, posts, see-through holes, and clips and z-fights
between building pieces beyond the game's own rate).

What it looks for, room by room (furnish.rooms):
  wall      furniture standing through a wall face (its box over the tile's measured face by > 6)
  chair     a chair with nothing to sit at: no table, desk, counter or bath within reach (70; a counter
            200), and not a hall's, study's or guardroom's chair against the wall, as the game stands them
  floating  a thing in the air: its bottom more than 24 above the building under it (by mesh ray) with
            nothing of the furniture under it either; a standing light the same; a chair raised off the
            floor by more than 10
  nowall    hung on nothing: a wall shelf more than 24 off any wall; a bookshelf, cupboard or dresser
            on the floor with floor behind its back (furnish.wall_behind); a tapestry, banner or
            painting more than 24 off any wall
  book      a leaning book with nothing on the side it leans to (shelfsurvey.book_pose)
  counter   a counter end meeting a tapestry: a flat hanging whose box overlaps a counter segment's
            and reaches below the counter's top
  light     a hanging light (chandelier, candelabra, lantern) with no ceiling piece above it, or hung
            under 100 off the floor
  tall      a thing taller than the room: standing on the floor, its top above the storey's beams

Each issue: {kind, text, id, ref, x, y, z, room, fixes: [{label, ops}], n}; ops are fixit.apply's
(move, delete, swap, place), so one route fixes them all. Nothing here edits a place: the fixes are
offered, and applied only when asked for (POST /api/fixit/apply)."""
import math
import re
from collections import Counter

import arrangesurvey
import fixit
import furnish
import kits
import mapdata
import seethrough
import shelfsurvey
from editing import EditError

# what hangs or lies rather than stands: never "floating", never "through a wall"
HUNG = re.compile(r'tapestr|banner|painting|picture|portrait|sconce|hook|rope|window|chandelier|candelabra|lantern|lamp|'
                  r'pillow|cushion|rug|carpet|shelf|weaponrack|armorrack|troph|rack')
IN_WALL_OK = re.compile(r'tapestr|banner|painting|sconce|rack|shelf|hook|rope|window|chandelier')
FLAT_HANGING = re.compile(r'tapestr|banner|painting|picture|portrait')
HANG_LIGHT = re.compile(r'chandelier|candelabra|lantern|hanging')
TALL_OK = re.compile(r'tapestr|banner|painting|sconce|hook|rope|chandelier|shelf|rack')
THING_TYPES = ('STAT', 'CONT', 'ACTI', 'MISC', 'BOOK', 'INGR', 'ALCH', 'WEAP', 'ARMO', 'CLOT', 'LIGH', 'APPA')
SEAT_ROOMS = ('hall', 'corridor', 'entry', 'landing', 'guardroom', 'bath', 'study', 'mess', 'barracks')   # (a mess's chairs: 60% at a wall in the game)

# the kinds, in the order the list shows them, with what each looks for (for the panel's headings)
KINDS = [
    ('wall', 'Through a wall', 'Furniture standing through a wall face.'),
    ('floating', 'Floating', 'Things in the air, with nothing under them.'),
    ('chair', 'Chairs with nothing to sit at', 'A chair with no table, desk, counter or bath within reach.'),
    ('nowall', 'Hung on nothing', 'A shelf, bookshelf, cupboard or tapestry with no wall behind it.'),
    ('light', 'Lights hung from nothing', 'A hanging light with no ceiling piece above it.'),
    ('water', 'Water with no bath', 'A bath\'s water sheet (or a flame) with nothing it belongs in under it.'),
    ('planter', 'Planters half empty', 'A planter with fewer things growing in it than the game usually gives that model.'),
    ('rider', 'Dressings with no base', 'Things laid on or round a piece that is no longer here.'),
    ('floor', 'Clutter on the floor', 'Tableware, a book, food or a tool lying on a bare floor with nothing under it.'),
    ('window', 'Hangings over windows', 'A tapestry, banner, shelf, rack or sconce on the wall of a window piece.'),
    ('lonepot', 'Lone pots in the open', 'A planter standing alone at a plain wall or out in the room, with nothing it belongs with.'),
    ('tall', 'Taller than the room', 'A thing standing on the floor with its top through the ceiling.'),
    ('counter', 'Counters into tapestries', 'A counter end meeting a wall hanging.'),
    ('book', 'Books leaning on nothing', 'A leaning book with no support on the side it leans to.'),
    ('gap', 'Gaps', 'An open side looking out onto nothing.'),
    ('doorway', 'Doorways to nowhere', 'A doorway that leads nowhere.'),
    ('ceiling', 'Missing ceilings', 'No ceiling over this spot.'),
    ('post', 'Posts', 'A corner where the style stands a post.'),
    ('joint', 'Not what the game stands here', 'An edge where the game\'s own places of the style stand something else (a walled side with its addon and pillar, a doorway, an open side), with the game\'s piece as the fix.'),
    ('hole', 'See-through holes', 'A slit between pieces you can see through.'),
    ('clip', 'Clips', 'A building piece cutting into another, more often than the game\'s own places.'),
    ('zfight', 'Flicker', 'Two faces in one plane that flicker in the game, more often than the game\'s own places.'),
]
LABEL = {k: lab for k, lab, _w in KINDS}
ORDER = {k: n for n, (k, _l, _w) in enumerate(KINDS)}


def _things(db, info):
    """The furniture and clutter of the place (not the building, people or doors), with its family and
    world box, and the building as a ray scene."""
    refs = [x for x in info['refs'] if x.get('b') and not x.get('arch') and x['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC')]
    arch = [x for x in info['refs'] if x.get('arch') and x.get('ri') is not None]
    for x in refs:
        x['_fam'] = arrangesurvey.family(db, x['id'], x['type'])
        x['_box'] = fixit._world_box(x)
        if x['_fam'] == 'shelf' and x['id'].lower() not in _front:
            _front[x['id'].lower()] = furnish.front_of(db, x['id']) or (0.0, -1.0)
    sc = seethrough.place_scene(db, {'refs': arch})
    return refs, arch, sc


def _storey(db, info):
    """The storey height of the place's main building style, or None."""
    styles = Counter(kits.kit_prefix(r['id']) for r in info['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
    if not styles:
        return None
    pre = styles.most_common(1)[0][0]
    kp = kits.kit_pieces(db, pre) if pre in kits.kits(db) else None
    return (kp or {}).get('height') or None


def _faces(room, T):
    """The room's wall faces: [(side, face coordinate, tile x, tile y)]."""
    out = []
    for tl in room['_tiles']:
        for s in [s for s in furnish.STEP if tl['pat'][s] == 'wall']:
            off = tl['pat'].get('offset', {}).get(s, T / 2 - 16)
            out.append((s, (tl['x'] + furnish.STEP[s][0] * off) if s in 'EW' else (tl['y'] + furnish.STEP[s][1] * off), tl['x'], tl['y']))
    return out


def _wall_dist(bx, faces, T):
    """How far a box stands from the nearest wall face it lies against (along its tile's row)."""
    best = 9999
    for s, face, tx, ty in faces:
        if s in 'NS' and bx[0] < tx + T / 2 and bx[3] > tx - T / 2:
            best = min(best, abs(face - (bx[4] if s == 'N' else bx[1])))
        if s in 'EW' and bx[1] < ty + T / 2 and bx[4] > ty - T / 2:
            best = min(best, abs(face - (bx[3] if s == 'E' else bx[0])))
    return best


def _wall_ray(sc, x):
    """A wall behind a hung shelf by the building's real surfaces: a ray from just inside its back, at its
    middle height, out through the back hits the building within 40 (the tile patterns call a kit
    piece's doorway side a wall; the shelf hung there hangs on nothing)."""
    if not sc.tris:
        return True
    bx = x['_box']
    rot = x['p'][5]
    fr = _front.get(x['id'].lower())
    if fr is None:
        return True
    c_, s_ = math.cos(rot), math.sin(rot)
    fx, fy = fr[0] * c_ + fr[1] * s_, -fr[0] * s_ + fr[1] * c_
    depth = (bx[4] - bx[1]) if abs(fy) > abs(fx) else (bx[3] - bx[0])
    cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
    px, py = cx - fx * (depth / 2 - 6), cy - fy * (depth / 2 - 6)
    zm = (bx[2] + bx[5]) / 2
    return sc.nearest((px, py, zm), (-fx, -fy, 0.0), 40) is not None


_front = {}


def _gap(a, b):
    """The gap between two boxes on the floor plan (0 when they overlap)."""
    return max(a[0] - b[3], b[0] - a[3], a[1] - b[4], b[1] - a[4], 0)


def _under(x, inside, pad=12, above=30):
    """Something of the furniture under this thing's middle (its bottom within the other's height)."""
    bx = x['_box']
    cx, cy, bottom = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, bx[2]
    return [o for o in inside if o is not x and o['_box'] and o['_box'][0] - pad <= cx <= o['_box'][3] + pad
            and o['_box'][1] - pad <= cy <= o['_box'][4] + pad and o['_box'][2] - pad <= bottom <= o['_box'][5] + above]


def _issue(kind, x, text, room, fixes=(), at=None):
    bx = x['_box']
    return {'kind': kind, 'text': text, 'id': x['id'], 'name': x.get('name') or '', 'ref': x['k'], 'room': room['name'],
            'x': at[0] if at else (bx[0] + bx[3]) / 2, 'y': at[1] if at else (bx[1] + bx[4]) / 2,
            'z': at[2] if at else min(bx[2] + 40, (bx[2] + bx[5]) / 2), 'fixes': list(fixes)}


def _remove(x, label='Remove it'):
    return {'label': label, 'ops': [{'op': 'delete', 'ref': x['k']}]}


def _move(x, dx=0.0, dy=0.0, dz=0.0, label='Move it'):
    p = list(x['p'][:6])
    p[0], p[1], p[2] = round(p[0] + dx, 2), round(p[1] + dy, 2), round(p[2] + dz, 2)
    return {'label': label, 'ops': [{'op': 'move', 'ref': x['k'], 'p': p}]}


def _room_issues(db, info, room, refs, arch, sc, storey):
    """The faults in one room."""
    T = info['tile']
    fl = room['floor']
    inside = [x for x in refs if x['_box'] and any(abs(x['p'][0] - tl['x']) <= T / 2 and abs(x['p'][1] - tl['y']) <= T / 2 for tl in room['_tiles'])
              and fl - 30 <= x['_box'][2] <= fl + (400 if x['type'] == 'LIGH' else 200)]
    faces = _faces(room, T)
    out = []
    tables = [x for x in inside if x['_fam'] in ('table', 'counter')]
    win_tiles = furnish.window_tiles(room, info['refs'], T)
    counters = [x for x in inside if x['_fam'] == 'counter' and x['_box'][2] < fl + 60]
    for x in inside:
        bx = x['_box']
        low = x['id'].lower()
        bottom = bx[2]
        fam = x['_fam']
        big = (bx[3] - bx[0]) * (bx[4] - bx[1]) > 30 * 30
        candle = x['type'] == 'LIGH' and 'candle' in low and not re.search(r'candelabra|chandelier', low)
        # --- through a wall face of its own tile
        if big and not candle and fam not in ('shelf', 'rug', 'plant') and not IN_WALL_OK.search(low):
            for s, face, tx, ty in faces:
                if s in 'NS' and not (bx[0] < tx + T / 2 - 8 and bx[3] > tx - T / 2 + 8 and abs(x['p'][1] - ty) < T / 2 + 8):
                    continue
                if s in 'EW' and not (bx[1] < ty + T / 2 - 8 and bx[4] > ty - T / 2 + 8 and abs(x['p'][0] - tx) < T / 2 + 8):
                    continue
                over = {'N': bx[4] - face, 'S': face - bx[1], 'E': bx[3] - face, 'W': face - bx[0]}[s]
                if over > 6:
                    dx, dy = furnish.STEP[s]
                    out.append(_issue('wall', x, '%s stands %.0f into the %s wall' % (x.get('name') or x['id'], over, {'N': 'north', 'S': 'south', 'E': 'east', 'W': 'west'}[s]),
                                      room, [_move(x, -dx * (over + 2), -dy * (over + 2), 0, 'Pull it out of the wall'), _remove(x)]))
                    break
        # --- floating: a thing in the air, a standing light afloat, a chair raised off the floor
        if not candle and x['type'] in THING_TYPES:
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            if not HUNG.search(low):
                h = sc.nearest((cx, cy, bottom + 8), (0.0, 0.0, -1.0), 400)
                drop = (h[0] - 8) if h is not None else None
                if drop is not None and drop > 24 and not _under(x, inside):
                    out.append(_issue('floating', x, '%s floats %.0f above what\'s under it' % (x.get('name') or x['id'], drop), room,
                                      [_move(x, 0, 0, -drop, 'Set it down'), _remove(x)]))
                elif fam == 'chair' and bottom > fl + 10 and (h is None or h[0] - 8 > 10):
                    out.append(_issue('floating', x, '%s is raised %.0f off the floor' % (x.get('name') or x['id'], bottom - fl), room,
                                      [_move(x, 0, 0, -(h[0] - 8 if h is not None else bottom - fl), 'Set it down'), _remove(x)]))
            elif x['type'] == 'LIGH' and not HANG_LIGHT.search(low) and 'sconce' not in low:
                h = sc.nearest((cx, cy, bottom + 8), (0.0, 0.0, -1.0), 300)
                under = [o for o in inside if o is not x and o['_box'] and o['_box'][0] - 12 <= x['p'][0] <= o['_box'][3] + 12
                         and o['_box'][1] - 12 <= x['p'][1] <= o['_box'][4] + 12 and abs(o['_box'][5] - bottom) < 30]
                if (h is None or h[0] - 8 > 24) and not under:
                    drop = (h[0] - 8) if h is not None else 0
                    out.append(_issue('floating', x, '%s stands on nothing' % (x.get('name') or x['id']), room,
                                      ([_move(x, 0, 0, -drop, 'Set it down')] if drop else []) + [_remove(x)]))
        # --- a hanging light with no ceiling above it (a lantern or a candelabra that STANDS, on a table,
        #     a shelf or the floor, is not hung: the game's travel lanterns on its tables)
        if x['type'] == 'LIGH' and HANG_LIGHT.search(low):
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            # (45: a table's or a chest's mesh top may stand 35 to 40 over its box top, and the dressing's own
            # ray test put the lantern on the mesh)
            rests = [o for o in inside if o is not x and o['_box'] and o['_box'][0] - 12 <= x['p'][0] <= o['_box'][3] + 12
                     and o['_box'][1] - 12 <= x['p'][1] <= o['_box'][4] + 12 and abs(o['_box'][5] - bottom) < 45]
            down = sc.nearest((cx, cy, bottom + 8), (0.0, 0.0, -1.0), 60) if not rests else None
            stands = bool(rests) or (down is not None and down[0] - 8 <= 24)
            if stands and bottom < fl + 100:
                pass                                        # (a lantern set down on a table or the floor)
            else:
                up = sc.nearest((cx, cy, bx[5] + 2), (0.0, 0.0, 1.0), 600)
                if up is None or bottom < fl + 100:
                    out.append(_issue('light', x, '%s hangs from nothing%s' % (x.get('name') or x['id'], '' if up is not None else ' (no ceiling piece above it)'),
                                      room, [_remove(x)]))
        # --- a chair with nothing to sit at
        if fam == 'chair':
            sit_at = tables + ([o for o in inside if o['_fam'] == 'bath'] if room['purpose'] == 'bath' else [])
            near = [t for t in sit_at if _gap(t['_box'], bx) < (200 if t['_fam'] == 'counter' else 70)]
            if not near and room['purpose'] in SEAT_ROOMS and _wall_dist(bx, faces, T) <= 40:
                near = [x]                                      # (a hall's chair against the wall)
            if not near:
                out.append(_issue('chair', x, '%s has nothing to sit at' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- hung on nothing
        if fam in ('bookshelf', 'cupboard', 'shelf') and bottom < fl + 30 and \
                not furnish.wall_behind(x['b'], x['p'][5], x['p'][0], x['p'][1], room, T, furnish.front_of(db, x['id']), x.get('s') or 1.0, reach=30):
            out.append(_issue('nowall', x, '%s stands with no wall behind it' % (x.get('name') or x['id']), room, [_remove(x)]))
        elif fam == 'shelf' and bottom > fl + 30 and (_wall_dist(bx, faces, T) > 24 or not _wall_ray(sc, x)):
            out.append(_issue('nowall', x, '%s hangs %s' % (x.get('name') or x['id'], ('%.0f off the nearest wall' % _wall_dist(bx, faces, T)) if _wall_dist(bx, faces, T) > 24 else 'with no wall at its back (a doorway or a post there)'), room, [_remove(x)]))
        # --- a planter alone at a plain wall or in the open (the game stands its planters at a post, a
        #     window, a doorway, a seat or a stair, or with a vase, a lamp or another planter beside)
        if fam == 'planter' and x['type'] in ('STAT', 'ACTI', 'CONT') and bottom < fl + 60:
            px, py = x['p'][0], x['p'][1]
            company = any(o is not x and o['_box'] and (o['_fam'] in ('planter', 'urn', 'bench', 'table', 'chair', 'basket') or (o['type'] == 'LIGH' and o['_box'][2] < fl + 40))
                          and math.hypot(o['p'][0] - px, o['p'][1] - py) < 130 for o in inside)
            import wallsurvey2 as _w2
            spot = company or any(abs(a['p'][2] - fl) < 300 and math.hypot(a['p'][0] - px, a['p'][1] - py) < (T * 0.55 if re.search(r'win(dow)?(_|$|\d)', a['id'].lower()) else T * 1.2 if re.search(r'stair|ramp', a['id'].lower()) else 0)
                                  for a in arch) \
                or any(abs(a['p'][2] - fl) < 300 and re.search(r'pillar|column|post|colum', a['id'].lower()) and _w2.at_post(a, px, py) for a in arch) \
                or any(o['type'] == 'DOOR' or 'jamb' in o['id'].lower() for o in info['refs'] if abs(o['p'][2] - fl) < 200 and math.hypot(o['p'][0] - px, o['p'][1] - py) < 200)
            if not spot:
                out.append(_issue('lonepot', x, '%s stands alone with nothing it belongs with' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- a hanging on a window piece's wall, over the window
        if win_tiles and bottom > fl + 30 and (FLAT_HANGING.search(low) or fam in ('shelf', 'rack') or 'sconce' in low or 'rack' in low) \
                and _wall_dist(bx, faces, T) <= 24 and furnish._tile_of(x['p'][0], x['p'][1], room, T) in win_tiles:
            out.append(_issue('window', x, '%s hangs over the window' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- tableware, a book, food or a tool on a bare floor
        if x['type'] in ('MISC', 'BOOK', 'INGR', 'ALCH', 'APPA', 'PROB', 'REPA', 'LOCK') and bottom < fl + 12 and not _under(x, inside, above=60) \
                and not re.search(r'basket|sack|bundle_|rug|mat_|cushion|pillow|log|firewood|bucket|pail|crate|barrel|urn|pot_0|skull|bone', low):
            out.append(_issue('floor', x, '%s lies on the floor with nothing under it' % (x.get('name') or x['id']), room, [_remove(x)]))
        elif FLAT_HANGING.search(low) and x['type'] == 'STAT' and _wall_dist(bx, faces, T) > 24:
            out.append(_issue('nowall', x, '%s hangs %.0f off the nearest wall' % (x.get('name') or x['id'], _wall_dist(bx, faces, T)), room, [_remove(x)]))
        # --- a bath's water sheet with no tub under it (a piece that exists only inside another)
        if furnish.RIDER_ONLY.search(low) and x['type'] in ('STAT', 'ACTI'):
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            host = [o for o in inside if o is not x and o['_box'] and o['_fam'] in ('bath', 'fire', 'planter', 'urn')
                    and o['_box'][0] - 8 <= cx <= o['_box'][3] + 8 and o['_box'][1] - 8 <= cy <= o['_box'][4] + 8
                    and o['_box'][2] - 20 <= bottom <= o['_box'][5] + 20]
            if not host:
                out.append(_issue('water', x, '%s lies on the floor with no bath under it' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- a planter with fewer things in it than the game's usual for the model (its dressings' median)
        if fam == 'planter' and x['type'] in ('STAT', 'ACTI', 'CONT'):
            usual = _planter_usual(db, x['id'])
            if usual is not None:
                n_in = sum(1 for o in inside if o is not x and o['_box'] and shelfsurvey.GARDEN.search(o['id'].lower()) and not shelfsurvey.PLANTER.search(o['id'].lower())
                           and bx[0] - 12 <= o['p'][0] <= bx[3] + 12 and bx[1] - 12 <= o['p'][1] <= bx[4] + 12 and bx[2] - 30 <= o['_box'][2] <= bx[5] + 120)
                if n_in < usual:
                    out.append(_issue('planter', x, '%s holds %d thing%s; the game\'s usually hold %d' % (x.get('name') or x['id'], n_in, '' if n_in == 1 else 's', usual), room, []))
        # --- taller than the room
        if storey and x['type'] in ('STAT', 'ACTI', 'CONT') and bottom < fl + 60 and bx[5] > fl + storey - 20 and not TALL_OK.search(low):
            out.append(_issue('tall', x, '%s is taller than the room (its top is %.0f through the ceiling)' % (x.get('name') or x['id'], bx[5] - fl - storey + 20),
                              room, [_remove(x)]))
        # --- a counter end meeting a tapestry
        if FLAT_HANGING.search(low) and counters:
            for c in counters:
                b = c['_box']
                if bx[0] < b[3] and b[0] < bx[3] and bx[1] < b[4] and b[1] < bx[4] and bx[2] < b[5] + 16:
                    out.append(_issue('counter', x, '%s hangs into the counter (%s)' % (x.get('name') or x['id'], c.get('name') or c['id']), room,
                                      [_remove(x, 'Remove the hanging')]))
                    break
        # --- a leaning book with nothing on the side it leans to
        if x['type'] == 'BOOK':
            pose, d = shelfsurvey.book_pose(db, {}, {'id': x['id'], 'rx': x['p'][3], 'ry': x['p'][4], 'rz': x['p'][5]})
            if pose == 'lean' and _lean_unsupported(x, d, inside):
                out.append(_issue('book', x, '%s leans on nothing' % (x.get('name') or x['id']), room, [_remove(x)]))
    return out


def _orphan_riders(db, cell_key, refs, info):
    """Riders whose base is gone: a dressing's things, a plant, a hearth's tools, a crate's top, laid on or
    round a piece (tagged 'on' by Auto-furnish) that is no longer in the place. One issue per lost base,
    with "Remove them" taking every rider of it away as one fix."""
    c = (db.project.cells or {}).get(cell_key) if db.project else None
    if not c:
        return []
    live = {k for k, v in c['refs'].items() if not v.get('deleted')}
    by_base = {}
    for x in refs:
        v = c['refs'].get(x.get('k')) or {}
        base = v.get('on')
        if base and not v.get('deleted') and base not in live:
            by_base.setdefault(base, []).append(x)
    out = []
    for base, lst in by_base.items():
        x = lst[0]
        rm = next((r for r in info['rooms'] if any(abs(x['p'][0] - tl['x']) <= info['tile'] / 2 and abs(x['p'][1] - tl['y']) <= info['tile'] / 2 for tl in r['_tiles'])), None)
        room = rm or {'name': ''}
        names = sorted(set((o.get('name') or o['id']) for o in lst))
        out.append(_issue('rider', x, '%s laid on or round a piece that is no longer here (%d thing%s)' % (', '.join(names[:4]) + (' and more' if len(names) > 4 else ''), len(lst), '' if len(lst) == 1 else 's'),
                          room, [{'label': 'Remove them', 'ops': [{'op': 'delete', 'ref': o['k']} for o in lst]}]))
    return out


_usual = {}


def _planter_usual(db, rid):
    """How many things the game usually grows in this planter model: the median over its non-empty
    dressings (shelfsurvey), when it has five or more and the median is two or more; else None."""
    low = rid.lower()
    if low not in _usual:
        n = None
        try:
            s = shelfsurvey.survey(db, rid)
            sizes = sorted(len(d['objects']) for d in s['dressings'] if d['objects'])
            if len(sizes) >= 5:
                med = sizes[len(sizes) // 2]
                n = med if med >= 2 else None
        except Exception:
            n = None
        _usual[low] = n
    return _usual[low]


def _lean_unsupported(x, d, inside):
    """A book tipped along its row with nothing standing against the side it leans to (one tipped back
    against the shelf's board, across the row, leans on the board)."""
    bx = x['_box']
    under = [o for o in inside if o is not x and o['_fam'] in ('bookshelf', 'shelf', 'table', 'counter', 'cupboard') and o['_box']
             and o['_box'][0] - 4 <= x['p'][0] <= o['_box'][3] + 4 and o['_box'][1] - 4 <= x['p'][1] <= o['_box'][4] + 4]
    vx, vy = d if isinstance(d, (tuple, list)) else (d, 0)
    if under:
        ub = under[0]['_box']
        along_x = (ub[3] - ub[0]) >= (ub[4] - ub[1])
        along = abs(vx) if along_x else abs(vy)
    else:
        along_x = abs(vx) >= abs(vy)
        along = max(abs(vx), abs(vy))
    if along < 0.15:
        return False
    mid = (bx[2] + bx[5]) / 2
    for o in inside:
        ob = o['_box']
        if o is x or not ob or ob[5] <= mid or ob[2] >= bx[5]:
            continue
        if along_x:
            if not (ob[1] < bx[4] and ob[4] > bx[1]):
                continue
            edge = bx[3] if vx > 0 else bx[0]
            if (vx > 0 and ob[3] > edge and ob[0] - edge <= 4) or (vx < 0 and ob[0] < edge and edge - ob[3] <= 4):
                return False
        else:
            if not (ob[0] < bx[3] and ob[3] > bx[0]):
                continue
            edge = bx[4] if vy > 0 else bx[1]
            if (vy > 0 and ob[4] > edge and ob[1] - edge <= 4) or (vy < 0 and ob[1] < edge and edge - ob[4] <= 4):
                return False
    return True


def faults(db, cell_key):
    """The furnishing faults of a place: (issues, rooms looked at, things looked at)."""
    info = furnish.rooms(db, cell_key)
    if not info['rooms']:
        return [], 0, 0
    refs, arch, sc = _things(db, info)
    storey = _storey(db, info)
    out = []
    for room in info['rooms']:
        out += _room_issues(db, info, room, refs, arch, sc, storey)
    out += _orphan_riders(db, cell_key, refs, info)
    # (a thing in two rooms' tile lists, or faulted twice: once)
    seen, uniq = set(), []
    for i in out:
        key = (i['kind'], i['ref'])
        if key not in seen:
            seen.add(key)
            uniq.append(i)
    return uniq, len(info['rooms']), len(refs)


def check(db, cell_key, gaps=True):
    """Everything wrong with a place: {'issues': [...], 'counts': [{kind, label, what, n}], 'rooms',
    'things', 'style', 'gaps': the gap finder's figures (tiles, rate, typical, hidden,
    clashes_like_the_game) or None, 'note'}."""
    m = mapdata.cellmap(db, cell_key)
    if not m.get('exists') or not m.get('interior'):
        raise EditError('The health check works in interiors.')
    issues, n_rooms, n_things = faults(db, cell_key)
    style, gap_info, note = None, None, None
    if gaps:
        try:
            res = fixit.scan(db, cell_key, clashes=True)
            style = res.get('style')
            gap_info = {k: res.get(k) for k in ('tiles', 'rate', 'typical', 'hidden', 'hidden_kinds', 'clashes_like_the_game', 'posts')}
            for i in res['issues']:
                i.pop('n', None)
                i.setdefault('room', '')
                issues.append(i)
            if res.get('note') and not n_rooms:
                note = res['note']
        except EditError as e:
            note = str(e)
        except Exception as e:                       # (a survey still running, say: the rest of the list stands)
            print('place check, gaps:', e)
    if not n_rooms and not note:
        note = 'No rooms were found here (the place isn\'t laid in a style\'s floor pieces), so only the building was checked.'
    issues.sort(key=lambda i: (ORDER.get(i['kind'], 99), i.get('room', ''), i['id'].lower()))
    for n, i in enumerate(issues):
        i['n'] = n
    counts = Counter(i['kind'] for i in issues)
    return {'issues': issues, 'rooms': n_rooms, 'things': n_things, 'style': style, 'gaps': gap_info, 'note': note,
            'counts': [{'kind': k, 'label': lab, 'what': what, 'n': counts[k]} for k, lab, what in KINDS if counts[k]]}


def summary(db, cell_key):
    """Faults per kind for a lab table: {kind: n}, with 'rooms' and 'things'."""
    r = check(db, cell_key)
    out = {k: 0 for k, _l, _w in KINDS}
    for c in r['counts']:
        out[c['kind']] = c['n']
    out['rooms'], out['things'] = r['rooms'], r['things']
    return out
