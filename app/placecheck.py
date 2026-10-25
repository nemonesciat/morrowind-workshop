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
  nohearth  a hearth's fire, coals, tools or tool stand with no hearth within reach (hearthsurvey.tethered;
            not in caves, camps and ruins, whose log fires burn on their own)
  smithfire an anvil or a smith's standing bellows with no forge, coals, hearth or fire within the reach the
            game's smiths keep them at (tradesurvey.REACH: 200, 60; not in caves, camps and ruins)
and, with the gap finder's findings, the building's naked edges (edges.py: an end of a building piece
that nothing meets, caps or rests on, beyond the game's own rate for the kit).

Each issue: {kind, text, id, ref, x, y, z, room, fixes: [{label, ops}], n}; ops are fixit.apply's
(move, delete, swap, place), so one route fixes them all. Nothing here edits a place: the fixes are
offered, and applied only when asked for (POST /api/fixit/apply)."""
import math
import re
from collections import Counter

import arrangesurvey
import fixit
import furnish
import hangsurvey
import hearthsurvey
import kits
import mapdata
import seethrough
import shelfsurvey
import tradesurvey
from editing import EditError

# what hangs or lies rather than stands: never "floating", never "through a wall"
HUNG = re.compile(r'tapestr|banner|painting|picture|portrait|sconce|hook|rope|window|chandelier|candelabra|lantern|lamp|'
                  r'pillow|cushion|rug|carpet|shelf|weaponrack|armorrack|troph|rack|shackle|manacle|chain')
IN_WALL_OK = re.compile(r'tapestr|banner|painting|sconce|rack|shelf|hook|rope|window|chandelier')
FLAT_HANGING = re.compile(r'tapestr|banner|painting|picture|portrait')
HANG_LIGHT = re.compile(r'chandelier|candelabra|lantern|hanging')
TALL_OK = re.compile(r'tapestr|banner|painting|sconce|hook|rope|chandelier|shelf|rack')
THING_TYPES = ('STAT', 'CONT', 'ACTI', 'MISC', 'BOOK', 'INGR', 'ALCH', 'WEAP', 'ARMO', 'CLOT', 'LIGH', 'APPA')
BUILT_HEARTH = re.compile(r'alcove|niche|chimney|fireplace|hearth|oven|stove|kiln')     # (a building piece a fire burns in)
ROUGH_STYLES = ('Cave', 'Ashlander', 'Mine', 'Dwemer', 'Daedric', 'Ruin')     # (furnish's rough places: a log fire there is a camp's)
SEAT_ROOMS = ('hall', 'corridor', 'entry', 'landing', 'guardroom', 'bath', 'study', 'mess', 'barracks')   # (a mess's chairs: 60% at a wall in the game)

# the kinds, in the order the list shows them, with what each looks for (for the panel's headings)
KINDS = [
    ('wall', 'Through a wall', 'Furniture standing through a wall face.'),
    ('floating', 'Floating', 'Things in the air, with nothing under them.'),
    ('chair', 'Chairs with nothing to sit at', 'A chair with no table, desk, counter or bath within reach.'),
    ('nowall', 'Hung on nothing', 'A shelf, bookshelf, cupboard or tapestry with no wall behind it.'),
    ('light', 'Lights hung from nothing', 'A hanging light with no ceiling piece above it.'),
    ('hung', 'Hanging things hung from nothing', 'Something the game hangs from a ceiling or a beam (an anchor, a planter on its chain, a sign) hanging in the air well below anything to hang from.'),
    ('water', 'Water with no bath', 'A bath\'s water sheet (or a flame) with nothing it belongs in under it.'),
    ('nohearth', 'Fire things with no hearth', 'A log fire, coals, fire tools or a tool stand with no hearth, fireplace or oven within reach.'),
    ('smithfire', 'Smith\'s tools with no forge', 'An anvil or a smith\'s bellows with no forge, coals or fire within reach to heat the metal.'),
    ('planter', 'Planters half empty', 'A planter with fewer things growing in it than the game usually gives that model.'),
    ('rider', 'Dressings with no base', 'Things laid on or round a piece that is no longer here.'),
    ('floor', 'Clutter on the floor', 'Tableware, a book, food or a tool lying on a bare floor with nothing under it.'),
    ('window', 'Hangings over windows', 'A tapestry, banner, shelf, rack or sconce on the wall of a window piece.'),
    ('lonepot', 'Lone pots in the open', 'A planter standing alone at a plain wall or out in the room, with nothing it belongs with.'),
    ('tall', 'Taller than the room', 'A thing standing on the floor with its top through the ceiling.'),
    ('hallblock', 'Halls you can\'t walk through', 'Furniture standing across a hall, corridor or landing so there is no way past it from one doorway to the next.'),
    ('counter', 'Counters into tapestries', 'A counter end meeting a wall hanging.'),
    ('book', 'Books leaning on nothing', 'A leaning book with no support on the side it leans to.'),
    ('gap', 'Gaps', 'An open side looking out onto nothing.'),
    ('doorway', 'Doorways to nowhere', 'A doorway that leads nowhere, or a stairwell landing boxed in with no doorway out of it.'),
    ('stairend', 'Stairs with a closed end', 'The foot or head of a staircase meets a wall, or comes out onto nothing.'),
    ('sunk', 'Posts inside walls', 'A post or column standing more than half inside a wall piece or a door frame.'),
    ('ceiling', 'Missing ceilings', 'No ceiling over this spot.'),
    ('jambend', 'Door frames with bare ends', 'A door jamb whose end meets the wall with no post over the join (the style covers it with one).'),
    ('post', 'Posts', 'A corner where the style stands a post.'),
    ('joint', 'Not what the game stands here', 'An edge where the game\'s own places of the style stand something else (a walled side with its addon and pillar, a doorway, an open side), with the game\'s piece as the fix.'),
    ('naked', 'Naked edges', 'An edge of a building piece that nothing meets, caps or rests on (a wall face or floor sheet ending in the open), more often than in the game\'s own places of the style.'),
    # Project Tamriel's interior rules (packaging/nexus/pt-interior-guidelines.md; _rule_issues below)
    ('mixed', 'Mixed sets', 'Dunmer and Imperial furniture, or poor and rich makes, in one room; containers of two provinces in one place.'),
    ('hangkinds', 'Too many kinds of hanging', 'More than two tapestry or banner models in one room (the game keeps to one or two).'),
    ('ware', 'Tableware above its station', 'Fine tableware in a plain house beyond a piece or two, or ebonyware anywhere.'),
    ('books', 'Books as decoration', 'Two copies of a book, a whole series, or more than three common books in a home outside its study.'),
    ('bowls', 'Bowls sunk unevenly', 'Pointy-bottomed bowls on one surface bled into it by different amounts.'),
    ('hole', 'See-through holes', 'A slit between pieces you can see through.'),
    ('backwall', 'Walls seen from behind', 'The back of a one-sided wall, which the game doesn\'t draw: the next room shows through. The game stands its walls back to back, a face for each room.'),
    ('clip', 'Clips', 'A building piece cutting into another, more often than the game\'s own places.'),
    ('zfight', 'Flicker', 'Two faces in one plane that flicker in the game, more often than the game\'s own places.'),
]
LABEL = {k: lab for k, lab, _w in KINDS}
ORDER = {k: n for n, (k, _l, _w) in enumerate(KINDS)}


def _things(db, info):
    """The furniture and clutter of the place (not the building, people or doors), with its family and
    world box, and the building as a ray scene."""
    # (the big rugs, planters, trees and kiln hearths the map reader calls architecture are furniture here:
    # a plant stands in such a planter, a log fire in such a hearth; redoransurvey.is_thing names them)
    import redoransurvey
    refs = [x for x in info['refs'] if x.get('b') and x['type'] not in ('NPC_', 'CREA', 'DOOR', 'LEVC') and (not x.get('arch') or redoransurvey.is_thing(x))]
    big_ids = {id(x) for x in refs if x.get('arch')}
    arch = [x for x in info['refs'] if x.get('arch') and x.get('ri') is not None and id(x) not in big_ids]
    for x in refs:
        x['_fam'] = arrangesurvey.family(db, x['id'], x['type']) or redoransurvey.family(db, x)
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


def _touches_wall(sc, bx):
    """A flat thing's back against the building, by its real surfaces: from its middle at its middle height, a
    ray across its thin side reaches a face within its half depth and a hand (a traced place's tile faces are
    measured at waist height, a cave's rock bulges and falls away above it)."""
    if not sc.tris:
        return True
    cx, cy, zm = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, (bx[2] + bx[5]) / 2
    thin_x = (bx[3] - bx[0]) <= (bx[4] - bx[1])
    half = ((bx[3] - bx[0]) if thin_x else (bx[4] - bx[1])) / 2
    for d in (((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)) if thin_x else ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0))):
        if sc.nearest_any((cx, cy, zm), d, half + 24) is not None:
            return True
    return False


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


def _hearth_near(x, hearths, fl=None):
    """A hearth (built in or furniture) on this floor whose box reaches within the hearth survey's reach of
    this thing (a log fire upstairs is not the kiln's below it)."""
    bx = x['_box']
    for h in hearths:
        hb = h.get('_hbox')
        if not hb or not (hb[2] - 40 <= bx[2] <= hb[5] + 20):
            continue
        if fl is not None and not (fl - 150 <= hb[2] <= fl + 120):     # (a pit or a kiln sunk into the floor; never the storey below)
            continue
        if math.hypot(max(hb[0] - x['p'][0], 0, x['p'][0] - hb[3]), max(hb[1] - x['p'][1], 0, x['p'][1] - hb[4])) <= hearthsurvey.REACH + 30:
            return True
    return False


def _smith_issues(db, info, room, refs, heats, rough=False):
    """An anvil or a smith's standing bellows in this room with no forge, coals, hearth or fire light on its
    floor within the reach the game's smiths keep them at (tradesurvey.REACH: 27 of 30 anvils in the game's smiths'
    rooms within 166 of their fire, every bellows within 10). The game's own: 0 of 100 places; 30 of the 162
    places with a smith's tool, nearly all forts', guard towers' and mines' repair anvils and shops whose forge
    is out in the yard (2026-10-23). Not in caves, camps and ruins. Grindstones stand anywhere."""
    if rough:
        return []
    T = info['tile']
    fl = room['floor']
    out = []
    for x in refs:
        bx = x['_box']
        tool = tradesurvey.tool_of(x['id'], x['type'])
        if tool not in ('anvil', 'bellows') or not bx or not (fl - 30 <= bx[2] <= fl + 200):
            continue
        if not any(abs(x['p'][0] - tl['x']) <= T / 2 and abs(x['p'][1] - tl['y']) <= T / 2 for tl in room['_tiles']):
            continue
        reach = tradesurvey.REACH[tool] + 30
        if any(h['_hbox'] and fl - 150 <= h['_hbox'][2] <= fl + 150 and math.hypot(max(h['_hbox'][0] - x['p'][0], 0, x['p'][0] - h['_hbox'][3]),
                                                                                  max(h['_hbox'][1] - x['p'][1], 0, x['p'][1] - h['_hbox'][4])) <= reach
               for h in heats):
            continue
        out.append(_issue('smithfire', x, '%s stands with no forge or fire within %d to heat the metal' % (x.get('name') or x['id'], reach - 30),
                          room, [_remove(x)]))
    return out


def _in_hearth(x, hearths, above=30):
    """This thing stands in or on a hearth's box (built in or furniture): a fire in the firebox, a pot on the
    mantel (the map reader calls a kit's fireplace the building, so it is not among the furniture)."""
    bx = x['_box']
    cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
    return any(h.get('_hbox') and h['_hbox'][0] - 12 <= cx <= h['_hbox'][3] + 12 and h['_hbox'][1] - 12 <= cy <= h['_hbox'][4] + 12
               and h['_hbox'][2] - 12 <= bx[2] <= h['_hbox'][5] + above for h in hearths)


def _room_issues(db, info, room, refs, arch, sc, storey, hearths=(), rough=False):
    """The faults in one room."""
    T = info['tile']
    fl = room['floor']
    inside = [x for x in refs if x['_box'] and any(abs(x['p'][0] - tl['x']) <= T / 2 and abs(x['p'][1] - tl['y']) <= T / 2 for tl in room['_tiles'])
              and fl - 30 <= x['_box'][2] <= fl + (400 if x['type'] == 'LIGH' else 200)]
    faces = _faces(room, T)
    out = []
    # (what holds a thing up, or what a chair is drawn up to, may stand just off a traced room's tiles: on a doorway's
    # strip, which is in no room, or a tile the floor only half covers. A kit room's tiles are all its floor. On the
    # game's own places as they are, read by floortrace: a cup's table, a chair's table "missing", 2026-10-24)
    around = inside if not info.get('traced') else [
        x for x in refs if x['_box'] and room['x_min'] - T <= x['p'][0] <= room['x_max'] + T and room['y_min'] - T <= x['p'][1] <= room['y_max'] + T
        and fl - 60 <= x['_box'][2] <= fl + 400]
    tables = [x for x in around if x['_fam'] in ('table', 'counter')]
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
        # (a kit's fireplace stands into the wall, as the game seats its own: Gold Coast's 31 in)
        if big and not candle and fam not in ('shelf', 'rug', 'plant') and not IN_WALL_OK.search(low) and not hearthsurvey.built_piece(low):
            for s, face, tx, ty in faces:
                if s in 'NS' and not (bx[0] < tx + T / 2 - 8 and bx[3] > tx - T / 2 + 8 and abs(x['p'][1] - ty) < T / 2 + 8):
                    continue
                if s in 'EW' and not (bx[1] < ty + T / 2 - 8 and bx[4] > ty - T / 2 + 8 and abs(x['p'][0] - tx) < T / 2 + 8):
                    continue
                over = {'N': bx[4] - face, 'S': face - bx[1], 'E': bx[3] - face, 'W': face - bx[0]}[s]
                if over > 6 and info.get('traced') and sc.tris:
                    # (a traced room's face is measured at waist height across its tile: a cave's rock
                    # overhangs a low firepit, falls away by a tall bed. The building's own faces say whether
                    # one runs through the thing: rays from its middle out to its sides, low and high)
                    dx, dy = furnish.STEP[s]
                    cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
                    half = (bx[3] - bx[0]) / 2 if dx else (bx[4] - bx[1]) / 2
                    if not any(sc.nearest_any((cx + ox, cy + oy, bx[2] + (bx[5] - bx[2]) * fz), (float(dx), float(dy), 0.0), half - 6) is not None
                               for fz in (0.3, 0.7) for ox, oy in (((0, 0), (0, (bx[4] - bx[1]) / 4), (0, -(bx[4] - bx[1]) / 4)) if dx
                                                                   else ((0, 0), ((bx[3] - bx[0]) / 4, 0), (-(bx[3] - bx[0]) / 4, 0)))):
                        continue
                if over > 6:
                    dx, dy = furnish.STEP[s]
                    out.append(_issue('wall', x, '%s stands %.0f into the %s wall' % (x.get('name') or x['id'], over, {'N': 'north', 'S': 'south', 'E': 'east', 'W': 'west'}[s]),
                                      room, [_move(x, -dx * (over + 2), -dy * (over + 2), 0, 'Pull it out of the wall'), _remove(x)]))
                    break
        # --- floating: a thing in the air, a standing light afloat, a chair raised off the floor
        # (a plant growing in a planter is not afloat, whatever its model's box says of its roots: the game's
        # own gardens stand their ferns and flowers on the soil and on one another)
        in_planter = x.get('_on_planter') or fam != 'planter' and shelfsurvey.GARDEN.search(low) and any(
            o is not x and o['_box'] and o['_fam'] == 'planter' and o['_box'][0] - 12 <= x['p'][0] <= o['_box'][3] + 12
            and o['_box'][1] - 12 <= x['p'][1] <= o['_box'][4] + 12 and o['_box'][2] - 30 <= bottom <= o['_box'][5] + 160 for o in inside)
        hung_model = x['type'] in THING_TYPES and not x.get('arch') and hangsurvey.hangs(db, hangsurvey.model_of(db, x), x['id'])
        if not candle and x['type'] in THING_TYPES and not in_planter:
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            # (a thing the game hangs is not "floating": an anchor or a sign in the air is hung; whether from
            # anything is the 'hung' check's)
            if not HUNG.search(low) and not hung_model:
                h = sc.nearest((cx, cy, bottom + 8), (0.0, 0.0, -1.0), 400)
                drop = (h[0] - 8) if h is not None else None
                # (a hearth's mantel and its shelves stand well over its box top: the pot or the broom the
                # dressing stood on the fireplace's own mesh is on it, by the ray that laid it)
                on_hearth = any(o['_fam'] == 'fire' for o in _under(x, around, above=140)) or _in_hearth(x, hearths, above=140)
                # (a flat thing well up a wall, its back at the wall face, hangs there whatever its name)
                on_wall = x['type'] in ('STAT', 'ACTI') and bottom > fl + 50 and min(bx[3] - bx[0], bx[4] - bx[1]) <= 44 and (
                    _wall_dist(bx, faces, T) <= 24 or (info.get('traced') and _touches_wall(sc, bx)))
                if drop is not None and drop > 24 and not _under(x, around) and not on_hearth and not on_wall:
                    out.append(_issue('floating', x, '%s floats %.0f above what\'s under it' % (x.get('name') or x['id'], drop), room,
                                      [_move(x, 0, 0, -drop, 'Set it down'), _remove(x)]))
                elif fam == 'chair' and bottom > fl + 10 and (h is None or h[0] - 8 > 10):
                    out.append(_issue('floating', x, '%s is raised %.0f off the floor' % (x.get('name') or x['id'], bottom - fl), room,
                                      [_move(x, 0, 0, -(h[0] - 8 if h is not None else bottom - fl), 'Set it down'), _remove(x)]))
            elif x['type'] == 'LIGH' and not HANG_LIGHT.search(low) and 'sconce' not in low:
                h = sc.nearest((cx, cy, bottom + 8), (0.0, 0.0, -1.0), 300)
                under = [o for o in around if o is not x and o['_box'] and o['_box'][0] - 12 <= x['p'][0] <= o['_box'][3] + 12
                         and o['_box'][1] - 12 <= x['p'][1] <= o['_box'][4] + 12 and abs(o['_box'][5] - bottom) < 30]
                # (a log fire inside a hearth: within the hearth's own box, below its top)
                under += [o for o in _under(x, around) if o['_fam'] == 'fire']
                if (h is None or h[0] - 8 > 24) and not under and not _in_hearth(x, hearths):     # (a kit's fireplace is the building: its fire hovers in it)
                    drop = (h[0] - 8) if h is not None else 0
                    out.append(_issue('floating', x, '%s stands on nothing' % (x.get('name') or x['id']), room,
                                      ([_move(x, 0, 0, -drop, 'Set it down')] if drop else []) + [_remove(x)]))
        # --- a hanging light with no ceiling above it (a lantern or a candelabra that STANDS, on a table,
        #     a shelf or the floor, is not hung: the game's travel lanterns on its tables)
        if x['type'] == 'LIGH' and HANG_LIGHT.search(low):
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            # (45: a table's or a chest's mesh top may stand 35 to 40 over its box top, and the dressing's own
            # ray test put the lantern on the mesh)
            rests = [o for o in around if o is not x and o['_box'] and o['_box'][0] - 12 <= x['p'][0] <= o['_box'][3] + 12
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
                else:
                    # (hung well below where the game hangs this model: its chain or hook short of the ceiling,
                    # the user's "chandeliers fail to come up to the ceiling"; hanggap.py)
                    import hanggap
                    gap = up[0] + 2
                    # (under 200: in a two-storey hall the game hangs its lights a storey down on purpose,
                    # 254 to 524 below the roof in 5 of 100 game places)
                    if gap < 200 and hanggap.short_by(db, x['id'], gap) > 0:
                        raise_ = gap - hanggap.usual_gap(db, x['id'])
                        out.append(_issue('light', x, '%s hangs %.0f below the ceiling: its chain doesn\'t reach' % (x.get('name') or x['id'], gap),
                                          room, [_move(x, 0, 0, raise_, 'Raise it to the ceiling'), _remove(x)]))
        # --- hanging decor hung from nothing (hangsurvey.py): a model the game hangs from a ceiling or a beam,
        #     hanging here in the air far below anything to hang from (the user's anchor, "isn't attached to the
        #     ceiling"); raised to the surface over it, at the gap the game hangs that model
        # (not a wall's things: a shelf, a sconce, a rack, a banner hangs on its wall, the ceiling over it by chance)
        # (nor what spans or climbs: ivy and vines up a wall, a clothes line strung wall to wall, a web, a mist;
        # 27 in 100 of the game's own places before these were left out)
        on_its_wall = fam in ('shelf', 'bookshelf', 'cupboard') or re.search(
            r'sconce|shelf|rack|hook|tapestr|banner|painting|picture|portrait|sign|flora|ivy|vine|moss|root|mist|fog|smoke|web|rope|line|cloth', low)
        # (nor armour, weapons, clothes: shown on their pegs and stands)
        cg = hangsurvey.ceiling_gap(db, hangsurvey.model_of(db, x), x['id']) if hung_model and not on_its_wall and x['type'] not in ('ARMO', 'WEAP', 'CLOT') \
            and not (x['type'] == 'LIGH' and HANG_LIGHT.search(low)) else None
        if cg:
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            down = sc.nearest((cx, cy, bottom + 8), (0.0, 0.0, -1.0), 400)
            if down is None or down[0] - 8 > 24:            # (hung, not set down on something)
                up = sc.nearest((cx, cy, bx[5] + 2), (0.0, 0.0, 1.0), 800)
                gap = (up[0] + 2) if up is not None else None
                p50, p90 = cg
                if gap is None:
                    out.append(_issue('hung', x, '%s hangs from nothing (nothing over it to hang from)' % (x.get('name') or x['id']), room, [_remove(x)]))
                elif gap > max(p90, p50 + 12) and gap < 400:
                    out.append(_issue('hung', x, '%s hangs %.0f below the ceiling, from nothing (the game hangs it %.0f below)' % (x.get('name') or x['id'], gap, p50),
                                      room, [_move(x, 0, 0, gap - p50, 'Hang it from the beam above'), _remove(x)]))
        # --- a chair with nothing to sit at
        if fam == 'chair':
            # (a stool at the hearth is sat on too: the game's fire scenes, a stool either side of the fireplace)
            sit_at = tables + ([o for o in around if o['_fam'] == 'bath'] if room['purpose'] == 'bath' else []) + [o for o in around if o['_fam'] == 'fire']
            near = [t for t in sit_at if _gap(t['_box'], bx) < (200 if t['_fam'] == 'counter' else 70)]
            if not near and room['purpose'] in SEAT_ROOMS and _wall_dist(bx, faces, T) <= 40:
                near = [x]                                      # (a hall's chair against the wall)
            if not near:
                out.append(_issue('chair', x, '%s has nothing to sit at' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- hung on nothing
        # (a traced room's faces are measured, not laid: the wall at the piece's back by the building's real faces)
        traced = info.get('traced')
        if traced and fam in ('bookshelf', 'cupboard', 'shelf') and x['id'].lower() not in _front:
            _front[x['id'].lower()] = furnish.front_of(db, x['id']) or (0.0, -1.0)
        if fam in ('bookshelf', 'cupboard', 'shelf') and bottom < fl + 30 and \
                not (_wall_ray(sc, x) if traced else
                     furnish.wall_behind(x['b'], x['p'][5], x['p'][0], x['p'][1], room, T, furnish.front_of(db, x['id']), x.get('s') or 1.0, reach=30)):
            out.append(_issue('nowall', x, '%s stands with no wall behind it' % (x.get('name') or x['id']), room, [_remove(x)]))
        elif fam == 'shelf' and bottom > fl + 30 and ((_wall_dist(bx, faces, T) > 24 and not traced) or not _wall_ray(sc, x)):
            out.append(_issue('nowall', x, '%s hangs %s' % (x.get('name') or x['id'], ('%.0f off the nearest wall' % _wall_dist(bx, faces, T)) if _wall_dist(bx, faces, T) > 24 else 'with no wall at its back (a doorway or a post there)'), room, [_remove(x)]))
        # --- a planter alone at a plain wall or in the open (the game stands its planters at a post, a
        #     window, a doorway, a seat or a stair, or with a vase, a lamp or another planter beside)
        is_bed = fam == 'planter' and max(bx[3] - bx[0], bx[4] - bx[1]) >= 150 and sum(
            1 for o in inside if o is not x and o['_box'] and shelfsurvey.GARDEN.search(o['id'].lower()) and not shelfsurvey.PLANTER.search(o['id'].lower())
            and bx[0] - 12 <= o['p'][0] <= bx[3] + 12 and bx[1] - 12 <= o['p'][1] <= bx[4] + 12 and bx[2] - 30 <= o['_box'][2] <= bx[5] + 160) >= 2
        if fam == 'planter' and x['type'] in ('STAT', 'ACTI', 'CONT') and bottom < fl + 60 and not is_bed:
            # (a garden bed, 150 wide or more with three things growing in it, is its own company: the game's
            # beds stand in the middle of its halls and gardens; a lone pot is a pot)
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
        if x['type'] in ('MISC', 'BOOK', 'INGR', 'ALCH', 'APPA', 'PROB', 'REPA', 'LOCK') and bottom < fl + 12 and not _under(x, around, above=60) \
                and not re.search(r'basket|sack|bundle_|rug|mat_|cushion|pillow|log|firewood|bucket|pail|crate|barrel|urn|pot_0|skull|bone', low):
            out.append(_issue('floor', x, '%s lies on the floor with nothing under it' % (x.get('name') or x['id']), room, [_remove(x)]))
        elif FLAT_HANGING.search(low) and x['type'] == 'STAT' and _wall_dist(bx, faces, T) > 24 and not (traced and _touches_wall(sc, bx)):
            out.append(_issue('nowall', x, '%s hangs %.0f off the nearest wall' % (x.get('name') or x['id'], _wall_dist(bx, faces, T)), room, [_remove(x)]))
        # --- a bath's water sheet with no tub under it (a piece that exists only inside another)
        if furnish.RIDER_ONLY.search(low) and x['type'] in ('STAT', 'ACTI'):
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            host = [o for o in inside if o is not x and o['_box'] and o['_fam'] in ('bath', 'fire', 'planter', 'urn')
                    and o['_box'][0] - 8 <= cx <= o['_box'][3] + 8 and o['_box'][1] - 8 <= cy <= o['_box'][4] + 8
                    and o['_box'][2] - 20 <= bottom <= o['_box'][5] + 20]
            if not host:
                out.append(_issue('water', x, '%s lies on the floor with no bath under it' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- a hearth's fire, tools or tool stand with no hearth within reach (hearthsurvey.tethered: what the
        #     game stands by a hearth in 85% or more of its uses; a cave's or a camp's log fire is its own)
        if x['type'] in ('LIGH', 'STAT', 'ACTI', 'MISC') and not rough and bottom <= fl + 200 and hearthsurvey.tethered(db, x['id'], x['type']) \
                and not hearthsurvey.is_bearer(db, x['id']) and not _hearth_near(x, hearths, fl):
            rl = hearthsurvey.role(low, x['type'])
            # (the game's fires with no hearth model: in a Hlaalu kit's alcove piece, Atrius Manor's and the
            # Vendicci servants' log fires; coals under a soup pot, Emaroc's bakery; and a fire tool put away
            # on a table or a shelf, the Bal Foyen guard tower's broom)
            cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
            built = rl == 'fire' and any(BUILT_HEARTH.search(a['id'].lower()) and a.get('b') and _gap(fixit._world_box(a), bx) <= 30 for a in arch)
            cooking = rl == 'fire' and any(o is not x and o['_box'] and hearthsurvey.role(o['id'].lower(), o['type']) == 'cook'
                                           and o['_box'][0] - 20 <= cx <= o['_box'][3] + 20 and o['_box'][1] - 20 <= cy <= o['_box'][4] + 20
                                           and 0 <= o['_box'][2] - bottom <= 60 for o in inside)
            stored = rl == 'tool' and any(o['_fam'] in ('table', 'shelf', 'counter', 'crate', 'chest', 'cupboard', 'bookshelf') for o in _under(x, around, above=60))
            if not (built or cooking or stored):
                out.append(_issue('nohearth', x, '%s stands with no hearth it belongs to' % (x.get('name') or x['id']), room, [_remove(x)]))
        # --- a planter with fewer things in it than the game's usual for the model (its dressings' median)
        if fam == 'planter' and x['type'] in ('STAT', 'ACTI', 'CONT'):
            usual = _planter_usual(db, x['id'])
            if usual is not None:
                n_in = sum(1 for o in inside if o is not x and o['_box'] and shelfsurvey.GARDEN.search(o['id'].lower()) and not shelfsurvey.PLANTER.search(o['id'].lower())
                           and bx[0] - 12 <= o['p'][0] <= bx[3] + 12 and bx[1] - 12 <= o['p'][1] <= bx[4] + 12 and bx[2] - 30 <= o['_box'][2] <= bx[5] + 120)
                if n_in < usual:
                    out.append(_issue('planter', x, '%s holds %d thing%s; the game\'s usually hold %d' % (x.get('name') or x['id'], n_in, '' if n_in == 1 else 's', usual), room, []))
        # --- taller than the room
        # (a hearth's chimney breast runs up through the storey above, as the game's own do: Gold Coast's 521 tall;
        # a forge's chimney the same, tradesurvey)
        if storey and x['type'] in ('STAT', 'ACTI', 'CONT') and bottom < fl + 60 and bx[5] > fl + storey - 20 and not TALL_OK.search(low) \
                and not ((hearthsurvey.is_bearer(db, low) or tradesurvey.piece_of(low, x['type']) == 'forge') and bx[5] <= fl + hearthsurvey.TALL):
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
            # (the garden survey first: it reads the big beds the map reader calls architecture, which the
            # shelf dressings never saw; the model's usual count over every planted one of it in the game)
            import gardensurvey
            n = gardensurvey.usual(db, rid)
        except Exception:
            n = None
        if n is not None:
            _usual[low] = n
            return n
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


# ------------------------------------------------------------------ Project Tamriel's interior rules
# (packaging/nexus/pt-interior-guidelines.md: the rules the reviewers of Tamriel Rebuilt and Project
# Tamriel hold interiors to, as far as a check can tell them)
RULE_SETS = ('bed', 'table', 'chair', 'bench', 'bookshelf', 'shelf', 'cupboard', 'chest', 'desk', 'counter')
BOOK_ROOMS = ('study', 'shop')                    # (libraries and booksellers: books by the shelfful there)
REAL_BOOK = re.compile(r'(^|_)bk_|_book')
NOT_BOOK = re.compile(r'scroll|note|paper|ledger|regist|letter|journal|bellman|list|recipe|contract|deed|writ|map|sign')
SERIES = re.compile(r'^(.*?)[ _]?(\d+|i{1,3}|iv|v)$')


def _series_stem(rid):
    m = SERIES.match(rid.lower())
    return m.group(1) if m and len(m.group(1)) >= 6 else None


def place_band(db, refs):
    """The household's band, guessed from its furniture's makes: 'rich' when most set pieces are of the
    rich make, 'poor' when of the poor, else 'comfortable'."""
    import wealthsurvey
    tiers = Counter(wealthsurvey.set_tier(x['id']) for x in refs if x['type'] in ('STAT', 'ACTI', 'CONT'))
    tiers.pop(None, None)
    if not tiers:
        return 'comfortable'
    top, n = tiers.most_common(1)[0]
    if n * 2 < sum(tiers.values()):
        return 'comfortable'
    return {'rich': 'rich', 'poor': 'poor'}.get(top, 'comfortable')


def _rule_issues(db, info, refs, cell_key=None):
    """The rule faults of a place, room by room and place-wide."""
    import wealthsurvey
    T = info['tile']
    place_name = ((mapdata.cell_info(db, cell_key) or {}).get('name') if cell_key else '') or ''
    out = []
    rooms = info['rooms']

    def room_of(x):
        return next((r for r in rooms if any(abs(x['p'][0] - tl['x']) <= T / 2 and abs(x['p'][1] - tl['y']) <= T / 2 for tl in r['_tiles'])
                     and r['floor'] - 30 <= x['_box'][2] <= r['floor'] + 200), None)

    by_room = {}
    for x in refs:
        if not x['_box']:
            continue
        r = room_of(x)
        if r is not None:
            by_room.setdefault(r['name'], (r, []))[1].append(x)
    for name, (room, inside) in by_room.items():
        # (the furniture sets proper: beds, tables, seats, shelves, cupboards and chests; the game lays its
        # rugs, mats, screens and trays across the cultures freely)
        furn = [x for x in inside if x['type'] in ('STAT', 'ACTI', 'CONT') and 'furn' in x['id'].lower() and x['_fam'] in RULE_SETS]
        # --- Dunmer and Imperial sets in one room; the poor and the rich make in one room
        cul = Counter(wealthsurvey.culture_of(x['id']) for x in furn)
        cul.pop(None, None)
        cul.pop('nordic', None)                     # (the Nord houses of the game take Imperial furniture)
        if len(cul) >= 2:
            order = sorted(cul, key=lambda k: (cul[k], k))
            minority, majority = order[0], order[-1]
            if cul[minority] < cul[majority] and cul[majority] >= 2:
                for x in [x for x in furn if wealthsurvey.culture_of(x['id']) == minority][:3]:
                    out.append(_issue('mixed', x, '%s is %s furniture in a room of %s pieces (the game never mixes the two)' % (
                        x.get('name') or x['id'], minority.capitalize(), majority.capitalize()), room, [_remove(x)]))
        tiers = Counter(wealthsurvey.set_tier(x['id']) for x in furn)
        if tiers.get('poor') and tiers.get('rich') and tiers['poor'] != tiers['rich']:
            minority = 'poor' if tiers['poor'] < tiers['rich'] else 'rich'
            for x in [x for x in furn if wealthsurvey.set_tier(x['id']) == minority][:3]:
                out.append(_issue('mixed', x, '%s is of the %s make in a room of the %s make' % (
                    x.get('name') or x['id'], minority, 'rich' if minority == 'poor' else 'poor'), room, [_remove(x)]))
        # --- more than two tapestry or banner models in a room (a hall of twelve tiles or more may)
        cloth = [x for x in inside if x['type'] == 'STAT' and re.search(r'tapestr|banner', x['id'].lower()) and x['_box'][2] > room['floor'] + 30]
        kinds = Counter(x['id'].lower() for x in cloth)
        if len(kinds) > 2 and room['tiles'] < 12:
            rare = [k for k, _n in sorted(kinds.items(), key=lambda kv: kv[1])][:len(kinds) - 2]
            for x in [x for x in cloth if x['id'].lower() in rare][:3]:
                out.append(_issue('hangkinds', x, '%s is the %s kind of hanging in this room (the game keeps to one or two)' % (
                    x.get('name') or x['id'], {3: 'third', 4: 'fourth'}.get(len(kinds), '%dth' % len(kinds))), room, [_remove(x)]))
        # (furniture half on a rug is not faulted: the game itself stands a table partly on a rug in
        # nearly half its places; Auto-furnish keeps to Project Tamriel's rule when it lays one)
        # --- pointy-bottomed bowls on one surface, bled by different amounts (bowls at the same level
        #     of the same piece: their bottoms within a bleed's reach of each other, yet not alike)
        bowls = [x for x in inside if x['type'] == 'MISC' and 'bowl' in x['id'].lower()]
        if len(bowls) >= 2:
            on = {}
            for x in bowls:
                u = _under(x, inside, above=60)
                if u:
                    host = max(u, key=lambda o: o['_box'][5])
                    on.setdefault(host['k'], []).append((x, x['_box'][2]))
            for host_k, lst in on.items():
                lst.sort(key=lambda t: t[1])
                for a, b in zip(lst, lst[1:]):
                    if 3 < b[1] - a[1] <= 12:
                        out.append(_issue('bowls', b[0], 'bowls on one surface are sunk unevenly (%s sits %.0f higher than %s)' % (
                            b[0].get('name') or b[0]['id'], b[1] - a[1], a[0].get('name') or a[0]['id']), room, []))
                        break
    # --- place-wide: tableware above the household's station; books as decoration; containers of two provinces
    band = place_band(db, refs)
    over = [(x, wealthsurvey.ware_over(band, wealthsurvey.ware_class(x['id']))) for x in refs if x['type'] == 'MISC' and x['_box']]
    over = [(x, n) for x, n in over if n]
    ebony = [x for x, n in over if n >= 9]
    fine = [x for x, n in over if 0 < n < 9]
    for x in ebony[:3]:
        r = room_of(x) or {'name': ''}
        out.append(_issue('ware', x, '%s is ebonyware, which the game and the provinces keep for the very few' % (x.get('name') or x['id']), r, [_remove(x)]))
    if len(fine) > 2:
        for x in fine[2:5]:
            r = room_of(x) or {'name': ''}
            n_ = fine.index(x) + 1
            out.append(_issue('ware', x, '%s is finer tableware than a %s household keeps (a piece or two would pass; this is the %d%s)' % (
                x.get('name') or x['id'], band, n_, {1: 'st', 2: 'nd', 3: 'rd'}.get(n_ if n_ < 20 else n_ % 10, 'th')), r, [_remove(x)]))
    # (books proper: not the notes, scrolls, ledgers, registers and newspapers the game files as books)
    books = [x for x in refs if x['type'] == 'BOOK' and x['_box'] and REAL_BOOK.search(x['id'].lower()) and not NOT_BOOK.search(x['id'].lower())]
    if books:
        import roomsurvey
        theme = roomsurvey.theme_of(place_name)
        bookish = {r['name'] for r in rooms if r['purpose'] in BOOK_ROOMS + tuple(furnish.TRADE_ROOMS) or re.search(r'librar|book', r['name'].lower())}
        # (a bookseller's or a guild's whole place is its library)
        loose = [] if theme in ('shop', 'guild') and re.search(r'book|librar|guild|college|school|archive', place_name.lower()) else \
            [x for x in books if (room_of(x) or {}).get('name') not in bookish]
        seen = Counter()
        for x in loose:
            seen[x['id'].lower()] += 1
            if seen[x['id'].lower()] == 2:
                r = room_of(x) or {'name': ''}
                out.append(_issue('books', x, 'a second copy of %s (books are content, not decoration: one copy outside a library or a bookshop)' % (x.get('name') or x['id']), r, [_remove(x)]))
        stems = Counter(_series_stem(x['id']) for x in loose)
        stems.pop(None, None)
        for stem, n in stems.items():
            if n >= 3:
                x = next(x for x in loose if _series_stem(x['id']) == stem)
                r = room_of(x) or {'name': ''}
                out.append(_issue('books', x, 'a series of %d volumes (%s…) outside a library' % (n, x.get('name') or x['id']), r, []))
        # (Project Tamriel's homes hold one to three; the game's own hold more in a third of them, so the
        # check speaks up at twice that; Auto-furnish itself keeps to three)
        if theme == 'house' and len(loose) > 6:
            x = loose[6]
            r = room_of(x) or {'name': ''}
            out.append(_issue('books', x, '%d common books about the home outside its study (Project Tamriel gives a home one to three)' % len(loose), r, []))
    # (containers proper: crates, barrels, sacks, chests, urns and baskets; a plant is a container to the
    # game but travels with the garden, not the province's crates)
    conts = [x for x in refs if x['type'] == 'CONT' and x['_box'] and not shelfsurvey.GARDEN.search(x['id'].lower()) and 'flora' not in x['id'].lower()
             and re.search(r'crate|barrel|sack|chest|urn|basket|box|bag|pack', x['id'].lower())]
    provs = Counter(wealthsurvey.province_of(x['id']) for x in conts)
    provs.pop(None, None)
    if len(provs) >= 2:
        order = sorted(provs, key=lambda k: (provs[k], k))
        minority, majority = order[0], order[-1]
        for x in [x for x in conts if wealthsurvey.province_of(x['id']) == minority][:3]:
            r = room_of(x) or {'name': ''}
            out.append(_issue('mixed', x, '%s is a %s container among %s ones' % (x.get('name') or x['id'], minority, majority), r, [_remove(x)]))
    return out


def _hall_blocks(info, refs):
    """Halls one can't walk through (hallsurvey.blocked): a tile of a hall, corridor or landing with no
    way round what stands on its floor from one of its ways in to another. In 100 of the game's places, 3
    of 421 hall tiles in 2 places (a one-wide store room of crates, a shop counter run across a short
    passage), 2026-10-23."""
    import hallsurvey
    T = info['tile']
    out = []
    if not T:
        return out
    for room in info['rooms']:
        if room['purpose'] not in furnish.HALL_PURPOSES:
            continue
        obs = hallsurvey.obstacles(refs, room['floor'])
        if info.get('traced'):
            # (a traced hall's tiles are half a kit tile: one walks round a chest through the next tile over, so
            # the way through is looked for over the whole hall, from each way in to every other)
            x = _traced_hall_block(room, T, obs)
            if x is not None:
                out.append(_issue('hallblock', x, '%s stands across the %s: there is no way past it' % (
                    x.get('name') or x['id'], room['name']), room, [_remove(x)]))
            continue
        for t in room['_tiles']:
            near = [o for o in obs if o[0] < t['x'] + T / 2 + 30 and o[2] > t['x'] - T / 2 - 30 and o[1] < t['y'] + T / 2 + 30 and o[3] > t['y'] - T / 2 - 30]
            if not near or not hallsurvey.blocked(t, T, [o[:4] for o in near]):
                continue
            # (the thing standing nearest the tile's middle is the one in the way)
            x = min(near, key=lambda o: math.hypot(max(o[0] - t['x'], 0, t['x'] - o[2]), max(o[1] - t['y'], 0, t['y'] - o[3])))[4]
            out.append(_issue('hallblock', x, '%s stands across the %s: there is no way past it' % (
                x.get('name') or x['id'], room['name']), room, [_remove(x)]))
    return out


def _traced_hall_block(room, T, obs):
    """The thing that cuts a traced hall's ways in off from each other (the nearest to the cut), or None when one
    can walk from every way into the hall to every other round what stands in it."""
    import hallsurvey
    G, BODY = hallsurvey.STEP_G, hallsurvey.BODY
    n = int(T // G)
    tiles = {(round(t['x'] / T * 2), round(t['y'] / T * 2)): t for t in room['_tiles']}
    near = [o for o in obs if o[0] < room['x_max'] and o[2] > room['x_min'] and o[1] < room['y_max'] and o[3] > room['y_min']]
    if not near:
        return None
    free, ways = set(), []
    for t in room['_tiles']:
        x0, y0 = t['x'] - T / 2, t['y'] - T / 2
        pat = t['pat']
        walls = {s: (pat.get('offset') or {}).get(s, T / 2 - 16) for s in 'NESW' if pat.get(s) == 'wall'}
        for i in range(n):
            for j in range(n):
                px, py = x0 + (i + 0.5) * G, y0 + (j + 0.5) * G
                dx, dy = px - t['x'], py - t['y']
                if ('E' in walls and dx > walls['E'] - BODY) or ('W' in walls and -dx > walls['W'] - BODY) \
                        or ('N' in walls and dy > walls['N'] - BODY) or ('S' in walls and -dy > walls['S'] - BODY):
                    continue
                if any(b[0] - BODY <= px <= b[2] + BODY and b[1] - BODY <= py <= b[3] + BODY for b in near):
                    continue
                free.add((int(math.floor(px / G)), int(math.floor(py / G))))
        # (a way in: an open side or a doorway onto a tile of no other part of this hall)
        for s, (sx, sy) in furnish.STEP.items():
            if pat.get(s) not in ('open', 'door'):
                continue
            if (round(t['x'] / T * 2) + 2 * sx, round(t['y'] / T * 2) + 2 * sy) in tiles:
                continue
            cells = []
            for k in range(n):
                px = x0 + ((n - 1 if sx > 0 else 0 if sx < 0 else k) + 0.5) * G
                py = y0 + ((n - 1 if sy > 0 else 0 if sy < 0 else k) + 0.5) * G
                cells.append((int(math.floor(px / G)), int(math.floor(py / G))))
            ways.append(cells)
    if len(ways) < 2:
        return None
    start = [c for c in ways[0] if c in free]
    seen, todo = set(start), list(start)
    while todo:
        i, j = todo.pop()
        for c in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if c in free and c not in seen:
                seen.add(c)
                todo.append(c)
    cut = [w for w in ways[1:] if not any(c in seen for c in w)]
    if not start or cut:
        w = (cut[0] if cut else ways[0])[len((cut[0] if cut else ways[0])) // 2]
        px, py = (w[0] + 0.5) * G, (w[1] + 0.5) * G
        return min(near, key=lambda o: math.hypot(max(o[0] - px, 0, px - o[2]), max(o[1] - py, 0, py - o[3])))[4]
    return None


def faults(db, cell_key):
    """The furnishing faults of a place: (issues, rooms looked at, things looked at)."""
    info = furnish.rooms(db, cell_key)
    if not info['rooms']:
        return [], 0, 0
    refs, arch, sc = _things(db, info)
    storey = _storey(db, info)
    # (what Auto-furnish laid on or in a planter, by its 'on' tag: a plant in a bed is never afloat, whatever
    # its model's box says of its roots)
    c = (db.project.cells or {}).get(cell_key) if db.project else None
    if c:
        planters = {x['k'] for x in info['refs'] if x.get('k') and shelfsurvey.PLANTER.search(x['id'].lower())}
        for x in refs:
            v = c['refs'].get(x.get('k')) or {}
            x['_on_planter'] = v.get('on') in planters
    # the hearths here, built in or furniture (a kit's fireplace is the building to the map reader), and
    # whether the place is a cave, a camp or a ruin, whose log fires burn on their own
    # (a forge holds its coals and its fire as a hearth does: tradesurvey's sets)
    hearths = [x for x in info['refs'] if x.get('b') and (hearthsurvey.is_bearer(db, x['id']) or tradesurvey.piece_of(x['id'], x['type']) == 'forge')]
    for h in hearths:
        h['_hbox'] = fixit._world_box(h)
    shell = Counter(mapdata.style_of(r['id']) for r in info['refs'] if r.get('arch') and mapdata.style_of(r['id']))
    rough = bool(shell) and shell.most_common(1)[0][0] in ROUGH_STYLES
    # (and what a smith heats his metal at: a forge, coals, a hearth, a fire light)
    heats = [x for x in info['refs'] if x.get('b') and tradesurvey.heat_of(db, x['id'], x['type'])]
    for h in heats:
        h['_hbox'] = h.get('_hbox') or fixit._world_box(h)
    out = []
    for room in info['rooms']:
        out += _room_issues(db, info, room, refs, arch, sc, storey, hearths, rough)
        out += _smith_issues(db, info, room, refs, heats, rough)
    out += _orphan_riders(db, cell_key, refs, info)
    try:
        out += _hall_blocks(info, refs)
    except Exception as e:                       # (a check must never stop the list)
        print('place check, halls:', e)
    try:
        out += _rule_issues(db, info, refs, cell_key)
    except Exception as e:                       # (a rule must never stop the check)
        print('place check, rules:', e)
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
        # the naked edges (edges.py): ends of building pieces nothing meets, caps or rests on, when the
        # place has more of them than twice the game's own places of its kit
        try:
            import edges
            found, _hidden = edges.issues(db, cell_key, m)
            issues += found
        except Exception as e:
            print('place check, edges:', e)
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
