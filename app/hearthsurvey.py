"""How the game builds its hearths, ovens and fireplaces as sets (2026-10-23): a convincing hearth is never
one piece. The game's own stand the hearth static (a kit's fireplace in the wall, a free-standing fireplace,
a stove, an oven, a kiln) with its fire (the log pile light or the coals inside it), firewood, a cauldron or
a pot, the tools (shovel, broom, hook, poker, bellows) and often a counter, a shelf or a table beside it.
Auto-furnish laid loose fire tools with no hearth (the user's Rich Imperial Manor: Tamriel Data's fireplace
tool stand counted as "a fireplace" by its name), two fires in a kitchen and camp fires indoors.

This survey walks the game-made interiors that stand a hearth and reads, for each hearth:
- the set: everything within reach in the hearth's own frame (offsets, turns, scales) and each member's role
  (fire, wood, cookware, tool, grate, furniture), the culture of the house (its kit);
- how it stands at the wall: which side of the model is its back, how far its back stands off the wall;
- whether the fire burns in it (a light or coals inside its box) or the model shows its own fire;
- how many hearths a kitchen holds;
and for every fire accessory (the tools, the fire lights, the coals, the cauldrons), the share of its game
uses within reach of a hearth: the ones the game never sets apart from one are what Auto-furnish never lays
alone and what Check this place reports when they stand alone ("fire things with no hearth").

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import math
import os
import re
from collections import Counter, defaultdict

V = 'v2'                    # (v2: house hearths only, 15 places a model, the wall test on the pieces near it: 270 s -> 70 s)
CAP = 15                    # (a hearth model is read in this many places at most; a rarer one in all of its)
EXAMPLES = 40               # (a model's whole sets kept, at most)
REACH = 170                 # (a member is within this of the hearth's box, in the floor plan)
# the hearth itself: what holds the fire (a fireplace, a stove, an oven, a kiln, a pit)
BEARER = re.compile(r'fireplace|hearth|stove|oven|kiln|firepit|fire_pit|pitfire|cookingfire|campfire')
NOT_BEARER = re.compile(r'stand|tool|shovel|broom|hook|poker|tong|tapestr|banner|sign|_x_|chimney|smoke|marker|sound|bellows|'
                        r'grate|cup|basin|brazier|light_fire|burnedout|_off')
PIT = re.compile(r'pit|campfire|cookingfire|cookfire|bonfire')
# what burns: a log pile light, a fire light, a flame, coals
FIRE = re.compile(r'logpile|light_fire|fire_nosmoke|flame|coal|ember|orange_fire|pitfire|firepit_f')
WOOD = re.compile(r'(^|_)log(s|pile|stand)?(_|\d|$)|logs|firewood|kindling|woodpile')
COOK = re.compile(r'cauldron|kettle|(^|_)pot(_|\d|$)|ironpot|frypan|fry_pan|skillet|_pan(_|\d|$)|pan_|stewpot|souppot|wok')
TOOL = re.compile(r'fireplace(stand|hook|shovel|broom|tool|poker|set)|poker|bellows|fireholder|firedog|andiron')      # (a house broom, a farm shovel: not the hearth's)
GRATE = re.compile(r'firegrate|fire_grate|(^|_)spit(_|\d|$)|grill|trivet|griddle')     # (not a sewer's grate)
_cache = {}
_thread = {}


def _disk(db):
    import taste
    return taste.cache_file('hearthsurvey_%s_%d_%s' % (taste.sig(db), CAP, V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    import taste
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('the game\'s hearths', lambda: survey(db), task=('hearthsurvey', 'survey', []))
    return taste.stale(_cache, key, db.recs, _disk(db))


def survey(db):
    key = 'survey'
    if key in _cache and _cache[key][0] is db.recs:
        return _cache[key][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache[key] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache[key] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def named_bearer(low):
    """A model whose name says it holds a fire (a fireplace, a stove, an oven, a kiln, a pit), not a tool
    stand, a grate, a chimney or a brazier."""
    return bool(BEARER.search(low)) and not NOT_BEARER.search(low)


def role(low, tag):
    """What a thing does at a hearth: 'fire', 'wood', 'cook', 'tool', 'grate' or None."""
    if tag == 'LIGH' and FIRE.search(low) and not re.search(r'brazier|candle|lantern|lamp|sconce|torch|chandelier', low):
        return 'fire'
    if tag in ('STAT', 'ACTI') and re.search(r'coal|ember', low) and 'ore' not in low:
        return 'fire'
    if TOOL.search(low):
        return 'tool'
    if GRATE.search(low) and not re.search(r'grater|dng|sewer|minercave', low) and tag != 'DOOR':
        return 'grate'
    if COOK.search(low) and not re.search(r'plant|flower|pot_01$|redware|planter|urn|chamber', low):
        return 'cook'
    if WOOD.search(low) and not re.search(r'flora|tree|terrace|_set_log(?!s)|dwelling|wall|bridge|raft', low):
        return 'wood'
    return None


def culture_of_kit(prefix):
    """The house's culture by its building kit: 'goldcoast', 'imperial', 'common', 'hlaalu', 'redoran',
    'nord', 'dunmer' (Velothi, Indoril, Telvanni, Dres...) or 'other'."""
    p = (prefix or '').lower()
    if p.startswith('t_imp_setgc'):
        return 'goldcoast'
    if p.startswith(('in_c_', 'in_common', 'in_imp_')):
        return 'common'
    if p.startswith(('t_imp_', 't_cyr_', 't_bre_', 't_rga_', 't_he_', 't_rea_')):
        return 'imperial'
    if p.startswith(('in_hlaalu', 'in_h_', 't_de_sethla')):
        return 'hlaalu'
    if p.startswith(('in_redoran', 'in_r_', 't_de_setred')):
        return 'redoran'
    if p.startswith(('in_nord', 't_nor_', 't_sky_')):
        return 'nord'
    if p.startswith(('in_t_', 'in_tel', 't_de_settel')):
        return 'telvanni'
    if p.startswith(('in_v_', 'in_vivec', 'in_velothi', 't_de_', 'in_de_', 'in_dae', 'in_strong')):
        return 'dunmer'
    return 'other'


def _cells(db, bearers):
    keys = Counter()
    for low in bearers:
        for ci in db.used_in.get(low, ()):
            if db.recs[ci][0] == 'CELL':
                keys[db.recs[ci][7]] += 1
    import kits
    import mapdata
    out = []
    for k in keys:
        if not k or k.startswith('#') or not kits.game_made(db, k):
            continue
        ci = mapdata.cell_info(db, k)
        if ci and ci.get('interior'):
            out.append(k)
    return sorted(out)


def _bearer_models(db):
    import kits
    import mapdata
    out = {}
    for (tag, k), lst in db.by_key.items():
        if tag not in ('STAT', 'ACTI', 'LIGH') or not lst or lst[-1] in db.dead or not named_bearer(k):
            continue
        if kits.game_uses(db, k) < 2:
            continue
        b = mapdata.object_bounds(db, lst[-1])
        if not b or max(b[3] - b[0], b[4] - b[1]) < 60 or (b[5] - b[2]) < 30:
            continue                      # (a hearth is big: the tool stand and the hook are not one)
        out[k] = b
    return out


def _local(dx, dy, rz):
    c, s = math.cos(rz), math.sin(rz)
    return dx * c - dy * s, dx * s + dy * c


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _survey(db):
    import furnish
    import fixit
    import kits
    import roomsurvey
    import seethrough
    import taste
    bearers = _bearer_models(db)
    # the places with a house's hearth (a cave's or a camp's pit is never laid in a house), in the taste order,
    # each taken while one of its hearth models has been read in fewer than CAP places: the commonest model in
    # 15 places, a rare one in all of its own (the first round walked 500 places, two in three of them caves
    # and camps, and took 270 s of a fresh install's learning)
    house = [k for k in bearers if not PIT.search(k)]
    holds = defaultdict(set)
    for low in house:
        for ci in db.used_in.get(low, ()):
            if db.recs[ci][0] == 'CELL':
                holds[db.recs[ci][7]].add(low)
    seen_n = Counter()
    cells = []
    for ck in taste.order(_cells(db, house)):
        if any(seen_n[m] < CAP for m in holds.get(ck, ())):
            cells.append(ck)
            seen_n.update(holds.get(ck, ()))
    M = defaultdict(lambda: {'n': 0, 'cultures': Counter(), 'kinds': Counter(), 'fire_in': 0, 'back': Counter(), 'gap': [], 'walled': 0,
                             'roles': Counter(), 'members': Counter(), 'sets': [], 'arch': 0, 'floating': 0})
    acc = defaultdict(lambda: [0, 0])          # id -> [uses seen in these cells, within reach of a hearth]
    kitchens = Counter()                       # hearths in a kitchen -> how many kitchens
    rooms_fires = Counter()                    # (room kind, hearths) -> rooms
    seen = 0
    for ck in cells:
        try:
            info = furnish.rooms(db, ck, trace=True)
        except Exception:
            continue
        refs = [r for r in info['refs'] if r.get('b') and r['type'] not in ('NPC_', 'CREA', 'LEVC', 'DOOR')]
        if not refs:
            continue
        seen += 1
        kit_ = Counter(kits.kit_prefix(r['id']) for r in info['refs'] if r.get('arch') and kits.kit_prefix(r['id']))
        culture = culture_of_kit(kit_.most_common(1)[0][0] if kit_ else '')
        for r in refs:
            r['_low'] = r['id'].lower()
            r['_box'] = fixit._world_box(r)
            r['_role'] = role(r['_low'], r['type'])
        hs = [r for r in refs if r['_low'] in bearers and r['_box']]
        sc = None
        # every accessory in these cells: near a hearth or not
        for r in refs:
            if r['_role'] and r['_low'] not in bearers and r['_box']:
                near = any(_dist_box(r, h) <= REACH + 30 and -60 <= r['p'][2] - h['_box'][2] <= (h['_box'][5] - h['_box'][2]) + 80 for h in hs)
                acc[r['_low']][0] += 1
                acc[r['_low']][1] += 1 if near else 0
        # hearths per room, by the room's kind
        for rm in info['rooms']:
            fl = rm['floor']
            inside = [r for r in refs if r['_box'] and rm['x_min'] - 20 <= r['p'][0] <= rm['x_max'] + 20 and rm['y_min'] - 20 <= r['p'][1] <= rm['y_max'] + 20
                      and fl - 60 <= r['_box'][2] <= fl + 300]
            for r in inside:
                r['_fam'] = roomsurvey.family_of(db, r['id'], r['type'])
            counts = Counter(r['_fam'] for r in inside if r['_fam'] in roomsurvey.FLOOR_KINDS)
            here = [h for h in hs if h in inside]
            counts['fire'] = len(here)
            kind = roomsurvey.room_kind(counts)
            rooms_fires[(kind, min(len(here), 3))] += 1
            if kind == 'kitchen':
                kitchens[min(len(here), 3)] += 1
            for h in here:
                h['_kind'] = kind
        for h in hs:
            A = M[h['_low']]
            A['n'] += 1
            A['cultures'][culture] += 1
            A['kinds'][h.get('_kind') or 'none'] += 1
            A['arch'] += 1 if h.get('arch') else 0
            hb = h['_box']
            hs_ = h.get('s') or 1.0
            # the set: what stands within reach of the hearth's box (not another hearth)
            mem = []
            fire_in = False
            for o in refs:
                if o is h or o['_low'] in bearers or not o['_box']:
                    continue
                if _dist_box(o, h) > REACH or not (-60 <= o['p'][2] - hb[2] <= (hb[5] - hb[2]) + 80):
                    continue
                ob = o['_box']
                fam_ = roomsurvey.family_of(db, o['id'], o['type'])
                big = max(ob[3] - ob[0], ob[4] - ob[1]) > 130
                if o.get('arch') and not o['_role']:
                    continue
                if big and fam_ not in ('table', 'counter', 'shelf', 'cupboard', 'bench', 'chair', 'barrel', 'crate', 'sack', 'chest'):
                    continue
                inbox = hb[0] - 4 <= o['p'][0] <= hb[3] + 4 and hb[1] - 4 <= o['p'][1] <= hb[4] + 4
                rl = o['_role'] or (fam_ if fam_ in ('table', 'counter', 'shelf', 'cupboard', 'bench', 'chair', 'barrel', 'crate', 'sack', 'chest', 'urn') else
                                    'thing')
                if rl == 'fire' and inbox:
                    fire_in = True
                lx, ly = _local(o['p'][0] - h['p'][0], o['p'][1] - h['p'][1], h['p'][5])
                mem.append({'id': o['id'], 'x': round(lx / hs_, 1), 'y': round(ly / hs_, 1), 'z': round((o['p'][2] - h['p'][2]) / hs_, 1),
                            'rz': round((o['p'][5] - h['p'][5]) % (2 * math.pi), 3), 's': round(o.get('s') or 1.0, 3), 'type': o['type'],
                            'role': rl, 'in': inbox})
            A['fire_in'] += 1 if fire_in else 0
            A['roles'].update(set(m['role'] for m in mem))
            A['members'].update(set(m['id'].lower() for m in mem))
            # the back: the side of the model nearest the building's surfaces (rays from its middle, the
            # hearth's own triangles left out), and how far its box stands off them
            # (only the building pieces whose boxes come within the rays' reach of it: the whole building's
            # geometry for every place was a third of the survey's time)
            if sc is None:
                sc = [r for r in info['refs'] if r.get('arch') and r.get('ri') is not None and r.get('b')]
                for r in sc:
                    r.setdefault('_box', fixit._world_box(r))
            near_ = [r for r in sc if r['_box'] and r['_box'][0] < hb[3] + 300 and r['_box'][3] > hb[0] - 300
                     and r['_box'][1] < hb[4] + 300 and r['_box'][4] > hb[1] - 300 and r['_box'][2] < hb[5] and r['_box'][5] > hb[2]]
            hsc = seethrough.place_scene(db, {'refs': near_})
            skip = set(range(*hsc.of_ref[h['k']])) if h.get('k') in hsc.of_ref else set()
            zm = (hb[2] + hb[5]) / 2.0 if (hb[5] - hb[2]) < 200 else hb[2] + 100
            best = None
            for side, (lx_, ly_) in (('+x', (1, 0)), ('-x', (-1, 0)), ('+y', (0, 1)), ('-y', (0, -1))):
                # (the model's local axis, turned as it stands: the game's z turn is clockwise)
                c_, s_ = math.cos(h['p'][5]), math.sin(h['p'][5])
                wx, wy = lx_ * c_ + ly_ * s_, -lx_ * s_ + ly_ * c_
                half = ((h['b'][3] - h['b'][0]) if lx_ else (h['b'][4] - h['b'][1])) * hs_ / 2.0
                cx = (h['b'][0] + h['b'][3]) / 2.0 * hs_
                cy = (h['b'][1] + h['b'][4]) / 2.0 * hs_
                ox = h['p'][0] + cx * c_ + cy * s_
                oy = h['p'][1] - cx * s_ + cy * c_
                hit = hsc._hits((ox, oy, zm), (wx, wy, 0.0), half + 120, skip, True) if hsc.tris else None
                if hit is not None:
                    edge = (h['b'][3] if lx_ > 0 else h['b'][0]) if lx_ else (h['b'][4] if ly_ > 0 else h['b'][1])
                    centre = cx if lx_ else cy
                    gap = hit[0] - abs(edge * hs_ - centre)
                    if best is None or gap < best[1]:
                        best = (side, gap)
            if best is not None and best[1] <= 60:
                A['walled'] += 1
                A['back'][best[0]] += 1
                A['gap'].append(round(best[1]))
            if len(A['sets']) < EXAMPLES:
                A['sets'].append({'cell': ck, 'culture': culture, 'kind': h.get('_kind'), 'fire_in': fire_in, 'arch': bool(h.get('arch')),
                                  'back': best[0] if best and best[1] <= 60 else None, 'gap': round(best[1]) if best else None,
                                  's': round(hs_, 3), 'members': mem})
    out = {'cells': seen, 'models': {}, 'accessories': {}, 'kitchens': {str(k): v for k, v in sorted(kitchens.items())},
           'rooms_fires': {'%s|%d' % k: v for k, v in sorted(rooms_fires.items())}}
    for k, A in M.items():
        b = bearers[k]
        out['models'][k] = {'n': A['n'], 'cultures': dict(A['cultures'].most_common()), 'kinds': dict(A['kinds'].most_common()),
                            'fire_in': round(A['fire_in'] / float(A['n'] or 1), 3), 'walled': round(A['walled'] / float(A['n'] or 1), 3),
                            'back': A['back'].most_common(1)[0][0] if A['back'] else None, 'gap': _med(A['gap']),
                            'roles': {r: round(c / float(A['n'] or 1), 3) for r, c in A['roles'].most_common()},
                            'members': {m: round(c / float(A['n'] or 1), 3) for m, c in A['members'].most_common(24)},
                            'arch': round(A['arch'] / float(A['n'] or 1), 3), 'pit': bool(PIT.search(k)),
                            'size': [round(b[3] - b[0]), round(b[4] - b[1]), round(b[5] - b[2])], 'sets': A['sets']}
    for k, (n, near) in acc.items():
        if n >= 3:
            out['accessories'][k] = {'n': n, 'near': round(near / float(n), 3), 'role': role(k, _tag(db, k))}
    return out


def _tag(db, low):
    ri = db.resolve_id(low)
    return db.recs[ri][0] if ri is not None else ''


def _dist_box(o, h):
    """How far o's origin stands outside h's box in the floor plan (0 inside it)."""
    hb = h['_box']
    dx = max(hb[0] - o['p'][0], 0, o['p'][0] - hb[3])
    dy = max(hb[1] - o['p'][1], 0, o['p'][1] - hb[4])
    return math.hypot(dx, dy)


# ---------------------------------------------------------------- what Auto-furnish and the check go by

def is_bearer(db, rid):
    """A hearth: a model that holds a fire (by the survey when it has seen it; else by its name and size)."""
    low = rid.lower()
    s = ready(db)
    if s and low in s['models']:
        return True
    if not named_bearer(low):
        return False
    import mapdata
    ri = db.resolve_id(rid)
    b = mapdata.object_bounds(db, ri) if ri is not None else None
    return bool(b) and max(b[3] - b[0], b[4] - b[1]) >= 60 and (b[5] - b[2]) >= 30


def tethered(db, rid, tag=None):
    """A fire accessory the game keeps at a hearth: its fire light or coals, the fire tools, the tool stand,
    the spit and the grate; True when the game stands it within reach of a hearth in 85% or more of its
    uses (seen 8 times at least), or when the survey never saw it and its role is the fire or a fire tool.
    Firewood and cookware are not: the game stacks logs in sheds and keeps pots on shelves."""
    low = rid.lower()
    if tag is None:
        tag = _tag(db, low)
    rl = role(low, tag)
    if rl not in ('fire', 'tool', 'grate'):
        return False
    if re.search(r'bellows', low):
        return False                  # (a smith's bellows stand at his forge, which is not a hearth)
    s = ready(db)
    a = ((s or {}).get('accessories') or {}).get(low)
    if a and a['n'] >= 8:
        return a['near'] >= 0.85
    return rl in ('fire', 'tool')


def models(db, culture, pits=False):
    """The hearths the game's houses of this culture stand, with their figures, most used first:
    [(id, figures)]; the culture's own first, then any culture's seen at a wall in 60% or more of uses."""
    s = ready(db)
    if not s:
        return []
    own, rest = [], []
    for k, F in s['models'].items():
        if F['pit'] and not pits:
            continue
        if db.resolve_id(k) is None or F['n'] < 3:
            continue
        n_c = F['cultures'].get(culture, 0)
        (own if n_c >= 2 else rest).append((k, F, n_c))
    own.sort(key=lambda t: -t[2])
    rest.sort(key=lambda t: -t[1]['n'])
    return [(k, F) for k, F, _n in own] + [(k, F) for k, F, _n in rest if F['walled'] >= 0.6 or pits]


# the game stands its fireplaces on the floor with the chimney breast up through the storey above: Gold
# Coast's 521 over the floor under a ceiling of 227 to 236, the Common grand fireplace 506, Gold Coast's
# poor fireplace 626 (measured in 40 game places, 2026-10-23)
TALL = 700
KIT_PIECE = re.compile(r'^t_[a-z]+_set[a-z]*_[a-z]_')     # (a Tamriel Data kit's built piece: t_imp_setgc_i_fireplace_01, t_rea_set_f_...)
def built_piece(low):
    """A hearth that is a building piece (a kit's fireplace, an in_ fireplace): the game seats these into the
    wall; a free-standing stove or kiln stands at it."""
    low = low.lower()
    return named_bearer(low) and bool(KIT_PIECE.match(low) or low.startswith('in_'))


BROAD = {'goldcoast': 'imperial', 'common': 'imperial', 'imperial': 'imperial', 'hlaalu': 'dunmer', 'redoran': 'dunmer', 'dunmer': 'dunmer',
         'telvanni': 'dunmer', 'nord': 'nordic'}


def _family(kit):
    """A kit's family by its name: t_imp_setgc_i and t_imp_setgcpoor_i are both 't_imp_setgc'."""
    p = (kit or '').lower()
    m = re.match(r'^(t_[a-z]+_set[a-z]+?)(poor|rich)?_', p)
    if m:
        return m.group(1)
    return '_'.join(p.split('_')[:2]) + '_' if p else ''


def choices(db, kit, band=None, height=None):
    """The hearths a room of a house built of this kit takes, best first: [(id, figures)], or None until
    surveyed. The kit's own fireplace first (Gold Coast's t_imp_setgc_i_fireplace_01, 84 of its 86 game uses
    in Gold Coast houses), then the models the houses of its culture stand (two uses at least), then those of
    its broad culture (Imperial, Dunmer, Nordic; three at least); never another kit's built piece, never a pit
    or a camp fire, never a Redoran kiln outside a Redoran house, and only models the game burns its fire
    inside (40% of uses at least) or that its culture's own houses stand ten times. height: the storey; a
    two-storey chimney breast is left out. band: a poor house takes a poor kit's fireplace when its kit has one,
    a rich one never does."""
    s = ready(db)
    if not s:
        return None
    culture = culture_of_kit(kit)
    broad = BROAD.get(culture)
    fam = _family(kit)
    out = []
    for k, F in s['models'].items():
        if F['pit'] or db.resolve_id(k) is None:
            continue
        if F['size'][2] > max(TALL, 3 * (height or 0)):
            continue                  # (a chimney breast of three storeys: Gold Coast's fireplace_02, 888 tall)
        own = F['cultures'].get(culture, 0)
        if F['fire_in'] < 0.4 and own < 10:
            continue
        if ('redoran' in k and culture != 'redoran') or (k.startswith('furn_t_') and culture != 'telvanni'):
            continue                  # (a Great House's own hearth stays in its houses: the Redoran kiln, the Telvanni fireplace)
        kp = KIT_PIECE.match(k)
        mine = bool(fam) and k.startswith(fam)
        if kp and not mine:
            continue                  # (another kit's built piece: a Skyrim fireplace is not a Gold Coast house's)
        same = sum(n for c, n in F['cultures'].items() if BROAD.get(c) == broad) if broad else 0
        if mine:
            rank = 0
        elif own >= 2:
            rank = 1
        elif same >= 3:
            rank = 2
        else:
            continue
        poor = 'poor' in k
        if poor and band not in ('poor', 'modest'):
            rank += 3
        elif not poor and band == 'poor' and any('poor' in k2 and k2.startswith(fam) for k2 in s['models']):
            rank += 0.5
        out.append((rank, -own, -F['n'], k, F))
    out.sort(key=lambda t: t[:3])
    return [(k, F) for _r, _o, _n, k, F in out]


# (pinned at v1's readings, the rates 2.3.9 shipped with: v2 walks fewer places, and its ~60 "tavern" rooms read
# 47% where v1's ~60 read 28%; both samples come from places with a hearth, so neither is the game's whole rate)
PINNED_RATE = {'tavern': 0.279, 'living': 0.2}
ROOM_KIND = {'dining': 'tavern', 'tavern': 'tavern', 'mess': 'tavern', 'living': 'living', 'bedroom': 'bedroom', 'study': 'study', 'shop': 'shop'}


def room_rate(db, purpose):
    """The share of the game's rooms of this kind with a hearth in them (rooms read by roomsurvey.room_kind:
    a dining room is a "tavern" there, a table with four seats); 1.0 for a kitchen, which always takes its
    hearth (the user's wish; the game's own kitchens have one in 64%, none in 25%); None when unknown."""
    if purpose == 'kitchen':
        return 1.0
    kind = ROOM_KIND.get(purpose)
    if kind in PINNED_RATE:
        return PINNED_RATE[kind]
    s = ready(db)
    if not s or not kind:
        return None
    rf = s.get('rooms_fires') or {}
    n = sum(v for k, v in rf.items() if k.split('|')[0] == kind)
    w = sum(v for k, v in rf.items() if k.split('|')[0] == kind and k.split('|')[1] != '0')
    return round(w / float(n), 3) if n >= 20 else None


def whole_set(db, rid, rng, culture=None, kind=None):
    """One of the game's own whole sets of this hearth model: [member dicts in the hearth's frame], those
    with the fire in it first when the model takes its fire inside (most do); one from a house of the same
    culture or a room of the same kind when there are any. None when the survey has none for it."""
    s = ready(db)
    F = ((s or {}).get('models') or {}).get(rid.lower())
    if not F or not F['sets']:
        return None
    pool = F['sets']
    if F['fire_in'] >= 0.5:
        pool = [d for d in pool if d['fire_in']] or pool
    for key, val in (('culture', culture), ('kind', kind)):
        if val:
            sub = [d for d in pool if d.get(key) == val]
            if len(sub) >= 2:
                pool = sub
    pool = [d for d in pool if len(d['members']) >= 2] or pool
    return rng.choice(pool)


def report(db):
    """For people: the survey in words."""
    s = survey(db)
    out = ['%d game places with a hearth walked' % s['cells'], 'kitchens by hearths in them: %s' % s['kitchens'],
           'rooms by kind and hearths: %s' % s['rooms_fires']]
    for k, F in sorted(s['models'].items(), key=lambda kv: -kv[1]['n']):
        out.append('%-34s n %3d %s fire in %3.0f%% at a wall %3.0f%% (back %s, gap %s) kinds %s roles %s'
                   % (k, F['n'], F['cultures'], 100 * F['fire_in'], 100 * F['walled'], F['back'], F['gap'], dict(list(F['kinds'].items())[:4]),
                      F['roles']))
        out.append('      members: %s' % dict(list(F['members'].items())[:12]))
    out.append('accessories (n, share by a hearth):')
    for k, A in sorted(s['accessories'].items(), key=lambda kv: -kv[1]['n']):
        out.append('   %-34s %4d %5.0f%% %s' % (k, A['n'], 100 * A['near'], A['role']))
    return out
