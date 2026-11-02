"""A room's theme, and two things the game does with it (2026-11-02, packaging/nexus/pt-showcases-study.md
section 7, from the user's pictures of a scholar's corner and a Dwemer repair bench).

- The theme on the wall: in a fifth of the game's themed rooms (arms, scholar, Dwemer...) a thing of the theme
  hangs on a wall: a sword, a shield, a map. Auto-furnish hung one in 3% of its own. This learns, for each
  theme, the pieces the game hangs, how high, how far off the wall and turned how against the wall, and how
  often a themed room has one.
- The spill round a smith's work: round 38% of the game's anvils the smith's things lie on the floor within
  200 (tongs, ingots, a broken piece), three or four times as thick as elsewhere in the room; Auto-furnish's
  smithies kept their floors clean (6%). This learns what lies there, how far out, how it lies, and how many.

A room's theme is the theme of three or more of its small things (theme_of). The game keeps a theme
together, on fewer levels than chance would (1.65 against 2.23 of floor, table, shelf and wall), so this
never spreads a theme about; it adds the wall piece at the game's rate, and the spill.

Kept in the cache folder once done (taste.cache_file, by load order); ready() runs it in the background."""
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

V = 'v2'
PLACES = 600
SMALL = ('MISC', 'INGR', 'ALCH', 'BOOK', 'APPA', 'LIGH', 'CLOT', 'WEAP', 'ARMO', 'REPA', 'PROB', 'LOCK')
THEMES = [
    ('dwemer', re.compile(r'dwrv|dwemer|dwe_|_dwe\d|cog|centurion|dw_')),
    ('scholar', re.compile(r'^bk_|^t_bk|book|scroll|paper|quill|ink|journal|ledger|^sc_|parchment|map_|astrolab|orrery|globe')),
    ('arms', re.compile(r'sword|axe|mace|dagger|spear|bow|shield|helm|cuirass|pauldron|greave|gauntlet|boots|armor|armour|weapon|blade|halberd|club')),
    ('smithing', re.compile(r'anvil|tongs|hammer|ingot|ore_|_ore|repair|forge|bellows|smith')),
    ('religious', re.compile(r'shrine|altar|tribunal|temple|incense|ancestor|_saint|idol|statue')),
    ('daedric', re.compile(r'daedr|azura|boethia|mephala|malacath|molag|sheogorath|vaermina|hircine')),
    ('nautical', re.compile(r'anchor|rope|net_|_net|oar|ship|boat|sail|fishing')),
]
# (what a smith's floor holds round the anvil: tools, stock, the work; not the room's food or tableware)
SMITH_THING = re.compile(r'tongs|hammer|prongs|ingot|ore|repair|metal|iron_|steel_|nail|coal|cog|dwrv|chain|bar_|plate_?armor|'
                         r'shield|helm|cuirass|pauldron|greave|gauntlet|boot|blade|sword|axe|dagger|mace|spear|scrap|piece')
ANVIL = re.compile(r'anvil|forge|grindstone')    # (the smith's work places; one counted where they stand together)
# (what hangs on a wall as a room's theme: a weapon, a shield, a map or a note pinned up; a book or a quill up
# there stands on a built-in shelf, a lantern is a light)
WALL_THING = re.compile(r'sc_paper|map|chart|note|notice|poster|scroll')
SPILL_REACH = 200            # (the floor within this of the anvil)
WALL_REACH = 30              # (a thing's back within this of a wall face: on the wall)
_cache = {}
_thread = {}


def theme_of(rid, tag):
    """The theme a small thing belongs to, or None: arms by record (a weapon, an armour piece), smithing for
    repair tools, else by name. (Alchemy is left out: every ingredient is one, the room's food included.)"""
    low = (rid or '').lower()
    if tag == 'LIGH':
        return None
    if tag in ('WEAP', 'ARMO'):
        return 'arms'
    if tag == 'REPA':
        return 'smithing'
    for name, rx in THEMES:
        if rx.search(low):
            return name
    return None


def room_theme(items):
    """The theme of three or more of these [(id, tag)], the commonest; None when none has three."""
    th = Counter(theme_of(rid, tag) for rid, tag in items)
    th.pop(None, None)
    if not th:
        return None
    t, n = th.most_common(1)[0]
    return t if n >= 3 else None


def _disk(db):
    import taste
    return taste.cache_file('themesurvey_%s_%d_%s' % (taste.sig(db), PLACES, V))


def ready(db):
    """The survey when it's to hand (in memory or on disk); else None, with it started in the background."""
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    try:
        if os.path.isfile(_disk(db)):
            return survey(db)
    except Exception:
        return None
    if _thread.get('t') is None or not _thread['t'].is_alive():
        import background
        _thread['t'] = background.start('the themes on the game\'s walls and round its anvils', lambda: survey(db),
                                        task=('themesurvey', 'survey', []))
    return None


def survey(db):
    if 'survey' in _cache and _cache['survey'][0] is db.recs:
        return _cache['survey'][1]
    path = None
    try:
        path = _disk(db)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                out = json.load(f)
            _cache['survey'] = (db.recs, out)
            return out
    except Exception:
        pass
    out = _survey(db)
    _cache['survey'] = (db.recs, out)
    if path:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


def wall_frame(inward):
    """The turn of a wall's own frame: its +y points into the room (shelfsurvey.to_world(0, 1, r) == inward)."""
    return math.atan2(inward[0], inward[1])


def _survey(db):
    import background
    import furnish
    import placecheck
    import planfrom
    import shelfsurvey
    places = list(planfrom.places(db))
    random.Random(11).shuffle(places)
    rooms_with = Counter()
    rooms_n = Counter()
    pieces = defaultdict(list)
    anvils = []
    n = 0
    for i, p in enumerate(places):
        if n >= PLACES:
            break
        background.progress(n, PLACES, 'places')
        try:
            info = furnish.rooms(db, p['key'])
        except Exception:
            continue
        if not info.get('rooms'):
            continue
        n += 1
        T = info['tile']
        try:
            refs, _arch, _sc = placecheck._things(db, info)
        except Exception:
            continue
        furn = [x for x in refs if x['_box'] and x['type'] in ('STAT', 'ACTI', 'CONT') and x['_fam']]
        small = [x for x in refs if x['_box'] and x['type'] in SMALL]
        for rm in info['rooms']:
            fl = rm['floor']

            def inside(x, rm=rm, fl=fl):
                return any(abs(x['p'][0] - tl['x']) <= T / 2 and abs(x['p'][1] - tl['y']) <= T / 2 for tl in rm['_tiles']) \
                    and fl - 40 <= x['_box'][2] <= fl + 260
            its = [x for x in small if inside(x)]
            th = room_theme([(x['id'], x['type']) for x in its]) if len(its) >= 6 else None
            if th:
                rooms_n[th] += 1
                faces = placecheck._faces(rm, T)
                got = False
                for x in its:
                    if theme_of(x['id'], x['type']) != th:
                        continue
                    bx = x['_box']
                    if bx[2] < fl + 90 or placecheck._under(x, furn, pad=4, above=45):
                        continue
                    if x['type'] not in ('WEAP', 'ARMO') and not WALL_THING.search(x['id'].lower()):
                        continue                  # (on the floor, or on a table, a shelf, a rack: not on the wall)
                    near = []
                    for s, face, tx, ty in faces:
                        if s in 'NS' and bx[0] < tx + T / 2 and bx[3] > tx - T / 2:
                            near.append((abs(face - (bx[4] if s == 'N' else bx[1])), s))
                        if s in 'EW' and bx[1] < ty + T / 2 and bx[4] > ty - T / 2:
                            near.append((abs(face - (bx[3] if s == 'E' else bx[0])), s))
                    if not near:
                        continue
                    gap, s = min(near)
                    if gap > WALL_REACH:
                        continue
                    got = True
                    inward = (-furnish.STEP[s][0], -furnish.STEP[s][1])
                    lrx, lry, lrz = shelfsurvey.local_rot(x['p'][3], x['p'][4], x['p'][5], wall_frame(inward))
                    pieces[th].append({'id': x['id'].lower(), 'type': x['type'], 'h': round(bx[2] - fl, 1), 'gap': round(gap, 1),
                                       'rx': round(lrx, 3), 'ry': round(lry, 3), 'rz': round(lrz, 3), 's': x.get('s') or 1.0})
                if got:
                    rooms_with[th] += 1
            # the anvils of this room, and what lies on the floor round them
            seen_ = []
            for a in [x for x in refs if x['_box'] and x['type'] in ('STAT', 'ACTI', 'CONT') and ANVIL.search(x['id'].lower()) and inside(x)]:
                ax, ay = a['p'][0], a['p'][1]
                if any(math.hypot(ax - sx, ay - sy) < 250 for sx, sy in seen_):
                    continue          # (a forge and its anvil: one work place)
                seen_.append((ax, ay))
                lying = []
                for x in its:
                    bx = x['_box']
                    if bx[2] >= fl + 25 or placecheck._under(x, furn, pad=4, above=45):
                        continue
                    if not (SMITH_THING.search(x['id'].lower()) or x['type'] in ('REPA', 'WEAP', 'ARMO')):
                        continue
                    d = math.hypot(x['p'][0] - ax, x['p'][1] - ay)
                    if d <= SPILL_REACH:
                        lying.append({'id': x['id'].lower(), 'type': x['type'], 'd': round(d, 1), 'rx': round(x['p'][3], 3),
                                      'ry': round(x['p'][4], 3), 'dz': round(x['p'][2] - fl, 1), 's': x.get('s') or 1.0})
                anvils.append(lying)
    wall = {}
    for th, n_rooms in rooms_n.items():
        if n_rooms < 5:
            continue
        wall[th] = {'rooms': n_rooms, 'rate': round(rooms_with[th] / float(n_rooms), 3), 'pieces': pieces[th][:400]}
    with_ = [a for a in anvils if a]
    spill = {'anvils': len(anvils), 'rate': round(len(with_) / float(len(anvils)), 3) if anvils else 0.0,
             'counts': sorted(len(a) for a in with_), 'items': [it for a in with_ for it in a][:600]}
    return {'places': n, 'wall': wall, 'spill': spill}


def wall_piece(db, theme, rng, ok=None):
    """One of the game's wall pieces of this theme, with how it hangs, at the game's rate for themed rooms:
    {'id', 'type', 'h', 'gap', 'rx', 'ry', 'rz', 's'} or None (the dice, no survey yet, nothing usable).
    ok(id): whether the house may have it (the band's cap, the culture)."""
    S = ready(db)
    W = ((S or {}).get('wall') or {}).get(theme)
    if not W or not W['pieces'] or rng.random() >= W['rate']:
        return None
    pool = [p for p in W['pieces'] if db.resolve_id(p['id']) is not None and (ok is None or ok(p['id']))]
    return dict(rng.choice(pool)) if pool else None


def spill(db, rng, ok=None):
    """What lies on the floor round this anvil, drawn as the game's anvils hold it: [items as the survey keeps
    them] (empty as often as the game's are), or None until surveyed."""
    S = ready(db)
    sp = (S or {}).get('spill')
    if not sp:
        return None
    if not sp['counts'] or rng.random() >= sp['rate']:
        return []
    want = rng.choice(sp['counts'])
    pool = [it for it in sp['items'] if db.resolve_id(it['id']) is not None and (ok is None or ok(it['id']))]
    if not pool:
        return []
    return [dict(rng.choice(pool)) for _ in range(min(want, 8))]
