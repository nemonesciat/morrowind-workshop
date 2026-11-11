"""The region pass (docs/terrain-tools-research-2026-11.md, P1 + P6 + P2): the land that is already there made as
rough, as mountainous and as cut by valleys as a hand-made region's, with no shapes drawn. Run by landshapes._work
when the plan's 'terrain' is on, on the marked cells, before the fade and the held ground.

  ranges   secondary crests and spurs in the mountains (ridged noise about 9,600 across, warped), as tall as the
           target region's roughness 8,192 apart asks for, and only where the land already stands over its valley
           floors: plains stay plains. Tamriel.esm's crests are 26,600 apart where the game's are 9,500
  relief   rolling detail 4,096 down to 256 across, each layer's height fitted (a power law over the layers) so the
           land's roughness 128, 512 and 2,048 apart becomes the target region's: Tamriel.esm has 27-29% of TR's.
           Rougher where the land already rises, gentle on the flats, fading out near the water
  valleys  the rain's valleys on the result (landwater.valleys, stream power at every 512 units)
  settle   the steepest steps eased to the target region's 99th-percentile slope; creases rounded

Everything but the valleys is a fixed function of the world position, the land under the mod and each region's
survey figures (not of the marked cells measured as a whole), so two runs side by side make the same ground where
they meet; edges shared with cells the mod already changed are matched to them (match_edges) instead of faded back
to the game's land."""
import math
import re

import landrange

LAG_KEYS = ('128', '512', '2048')
OCTAVES = (4096.0, 2048.0, 1024.0, 512.0, 256.0)
RANGE_WAVE = 9600.0                     # (the game's crest spacing, VV 9,216, TR 9,728, research 2.8)
HANDMADE_128 = 40.0                     # (a region whose land is this rough 128 apart was made by hand; heightmaps 10-30)
DEFAULTS = {'on': False, 'like': '', 'relief': 1.0, 'ranges': 1.0, 'valleys': 1.0, 'cliffs': 1.0, 'rocks': True, 'rockfrom': '', 'trees': True,
            'borders': True, 'plants': True, 'falls': True,
            'paint': False, 'trees_k': 1.0, 'plants_k': 1.0}
# (trees_k, plants_k: the Land stage's Trees and Plants sliders, 0 to 2, on what the pass and Clear first lay; the user,
# 2026-11-09, "maybe there should be a slider or some ability to choose density of what is laid down")
VALLEY_K = 0.02
SHORE = 400.0                           # (the detail fades out below this height, as match_roughness's)
RIDGE_MEAN = 0.0
# escarpments: hard rock bands (landrock) stepped into cliffs where the game has its steep ground. TR's 45-degree
# ground (lab 2026-11-08, research 2.2): 1% of the land 100 over its valley floors (4,096 round), 5% at 400-700,
# 13% at 1,000-1,500, 19-31% from 2,000; 0.4% where the land is a quarter as rough as its region round it, 13% at
# its own, 40% at twice; mid- to upper-slope (17% between 0.4 and 0.8 of the way from floor to top, 3% on the floor),
# and not at the streams (3% within 512 of one draining a cell). Faces tall: half the steep ground in patches
# spanning 2,048 or more
CLIFF_THICK = 960.0
CLIFF_SHARE = 0.5
CLIFF_OVER = (100.0, 1500.0)            # (the mask rises from 0 to 1 over this height over the floors)
CLIFF_F = (0.2, 0.8)                    # (... and over this roughness round it, a share of the target region's 2,048 figure:
                                        # the windowed measure runs at about 0.65 of the region's own)
CLIFF_STEP = 1.0                        # (landrock.stratify's strength: how sharply a hard band rises at its foot)
CLIFF_ANGLE = 0.3                       # (landrock.angles' strength: how far over the region's own steepest a hard band may stand)
CLIFF_KEEP = 0.4                        # (the share of the land's own shape a band keeps: its ledge isn't planed flat)
CLIFF_45 = 0.035                        # (the target's share over 45 degrees for the full strength)


def clean(opts):
    o = dict(DEFAULTS)
    for k, v in (opts or {}).items():
        if k not in DEFAULTS:
            continue
        if isinstance(DEFAULTS[k], bool):
            o[k] = bool(v)
        elif isinstance(DEFAULTS[k], float):
            try:
                o[k] = max(0.0, min(2.0, float(v)))
            except (TypeError, ValueError):
                pass
        else:
            o[k] = str(v or '').lower()[:64]
    return o


def _survey(db):
    import landsurvey
    return (landsurvey.ready(db) or {}).get('regions') or {}


def handmade(db):
    """{region: its roughness figures} for the regions whose land was made by hand (128 apart at least HANDMADE_128),
    the only ones worth taking after: a heightmap region taught its own smoothness back."""
    out = {}
    for r, R in _survey(db).items():
        rough = R.get('rough') or {}
        try:
            if float(rough.get('128') or 0) >= HANDMADE_128 and int(R.get('cells') or 0) >= 20 and r not in ('', '(none)'):
                out[r] = R
        except (TypeError, ValueError):
            continue
    return out


def like_for(db, region, want=''):
    """The hand-made region a region's land takes after: the one asked for, its own if it is hand-made, else the
    hand-made region nearest it in roughness 8,192 apart (a heightmap's plains take after gentle land, its
    mountains after mountains)."""
    hm = handmade(db)
    if want and want in _survey(db):
        return want
    if region in hm:
        return region
    R = _survey(db).get(region) or {}
    mine = float((R.get('rough') or {}).get('8192') or 0)
    if not hm:
        return region
    if mine <= 0:
        return sorted(hm)[0]
    return min(hm, key=lambda r: (abs(math.log(max(1.0, float(hm[r]['rough'].get('8192') or 1)) / mine)), r))


def _fig(R, key, default=0.0):
    try:
        return float((R.get('rough') or {}).get(key) or default)
    except (TypeError, ValueError):
        return default


# ---------- the noise layers and what each does to the roughness ----------

def _octave(x, y, lam, seed, crag):
    """One layer of the detail, about -1..1: value noise, turned towards ridged (sharp crests) by crag 0-1."""
    v = landrange._value(x / lam, y / lam, seed + 7919 + int(lam))
    if crag:
        v = v * (1.0 - crag) + (1.0 - 2.0 * abs(v)) * crag
    return v


def _ranges_noise(x, y, seed):
    """Ridged noise for crests and spurs about RANGE_WAVE apart, warped so they branch; about -0.5..0.5."""
    wx = landrange._value(x / 7000.0, y / 7000.0, seed + 5101) * 2600.0
    wy = landrange._value(x / 7000.0, y / 7000.0, seed + 5102) * 2600.0
    x, y = x + wx, y + wy
    total, weight, amp, norm = 0.0, 1.0, 1.0, 0.0
    for lam in (RANGE_WAVE, RANGE_WAVE / 2):
        n = 1.0 - abs(landrange._value(x / lam, y / lam, seed + 6007 + int(lam)))
        n *= n * weight
        weight = max(0.0, min(1.0, n * 1.5))
        total += n * amp
        norm += amp
        amp *= 0.5
    return total / norm - _RMEAN[0]


_PROBE = {}
_RMEAN = [0.0]


def _probes():
    """The RMS difference a unit layer makes at each lag (LAG_KEYS, and 8,192 for the ranges), sampled once."""
    if _PROBE:
        return _PROBE
    import random
    rnd = random.Random(12345)
    pts = [(rnd.uniform(-4e5, 4e5), rnd.uniform(-4e5, 4e5)) for _ in range(2500)]
    s = 0.0
    for x, y in pts:
        s += _ranges_noise(x, y, 1)
    _RMEAN[0] = s / len(pts)
    for lam in OCTAVES:
        for L in LAG_KEYS:
            d = float(L)
            a = 0.0
            for x, y in pts:
                q = _octave(x + d, y, lam, 1, 0.0) - _octave(x, y, lam, 1, 0.0)
                a += q * q
            _PROBE[(lam, L)] = a / len(pts)
    a = 0.0
    for x, y in pts:
        q = _ranges_noise(x + 8192.0, y, 1) - _ranges_noise(x, y, 1)
        a += q * q
    _PROBE[('ranges', '8192')] = a / len(pts)
    return _PROBE


def layer_amps(have, want):
    """Each layer's height (OCTAVES) so the roughness at LAG_KEYS goes from have to want: the layers follow a power
    law (A x (size / 4,096)^b), b and A fitted to the shortfall (variances add)."""
    P = _probes()
    need = {L: max(0.0, want[L] ** 2 - have[L] ** 2) for L in LAG_KEYS}
    if max(need.values()) < 64.0:
        return [0.0] * len(OCTAVES)
    best = None
    for k in range(0, 25):
        b = 0.3 + 0.05 * k
        S = {L: sum((lam / 4096.0) ** (2 * b) * P[(lam, L)] for lam in OCTAVES) for L in LAG_KEYS}
        wts = {L: 1.0 / max(1.0, want[L] ** 2) ** 2 for L in LAG_KEYS}
        num = sum(S[L] * need[L] * wts[L] for L in LAG_KEYS)
        den = sum(S[L] * S[L] * wts[L] for L in LAG_KEYS)
        A2 = max(0.0, num / den) if den else 0.0
        err = sum(((A2 * S[L] - need[L]) ** 2) * wts[L] for L in LAG_KEYS)
        if best is None or err < best[0]:
            best = (err, b, A2)
    _e, b, A2 = best
    A = math.sqrt(A2)
    return [A * (lam / 4096.0) ** b for lam in OCTAVES]


# Each point's own ground against its region's: how rough the land round it already is 2,048 apart (f, the local
# figure over the region's), in these steps. A smooth patch of a rough region is short of more than the region as
# a whole, a rough patch of less; the target follows the patch too, by f^CONTRAST, so mountains stay rougher than
# the flats beside them (lab 2026-11-08: one figure for the region left a smooth block at 336 against 435 at 2,048)
F_BINS = tuple(0.2 * (1.25 ** n) for n in range(14))         # (0.2 .. 3.6)
CONTRAST = 0.5


def plan_for(db, region, want=''):
    """What the pass does to a region's land: {'like', 'table' (the layers' heights at each step of F_BINS),
    'ranges' (amplitude), 'slope99'}."""
    S = _survey(db)
    R = S.get(region) or {}
    lk = like_for(db, region, want)
    T = S.get(lk) or {}
    have = {L: _fig(R, L) for L in LAG_KEYS}
    tgt = {L: _fig(T, L) for L in LAG_KEYS}
    if not all(tgt.values()) or not all(have.values()):
        table = [[0.0] * len(OCTAVES) for _ in F_BINS]
    else:
        table = [layer_amps({L: have[L] * f for L in LAG_KEYS}, {L: tgt[L] * f ** CONTRAST for L in LAG_KEYS}) for f in F_BINS]
    amps = table[F_BINS.index(min(F_BINS, key=lambda f: abs(f - 1.0)))]
    h8, t8 = _fig(R, '8192'), _fig(T, '8192')
    need8 = math.sqrt(max(0.0, t8 * t8 - h8 * h8))
    # (laid on only where the land stands over its floors, about half of a mountain region's points: twice the
    # variance there for the same over all)
    rng = need8 / math.sqrt(max(1e-6, _probes()[('ranges', '8192')])) / math.sqrt(0.5) if need8 > 32 else 0.0
    try:
        s99 = float((T.get('slope') or {}).get('99') or 62.0)
    except (TypeError, ValueError):
        s99 = 62.0
    try:
        s45 = float((T.get('steep') or {}).get('45') or 0.0)
    except (TypeError, ValueError):
        s45 = 0.0
    return {'like': lk, 'amps': amps, 'table': table, 'ranges': rng, 'slope99': s99, 'steep45': s45, 'have': have, 'want': tgt,
            'h8192': h8, 't8192': t8, 'r2048': have['2048'] or 1.0}


# ---------- whose rock clads the cliffs ----------

ROCK_STEEP = 60                         # (pieces the game set on a region's 30-degree ground for it to clad its own ...)
ROCK_COVER = 0.25                       # (... covering this share of it: Tamriel.esm's boulders cover 4-7%, cliff pieces 40-90%)
ROCK_FAR = 150.0                        # (cells apart that count as much as weather wholly unlike)
# (and how the ground looks: a region's rock goes with its ground, so the rock is taken from a region whose ground is
# the colour of this one's. By weather and the map alone the dark olive Aunike Ridge took Shipal-Shin's red sandstone
# and its red cliff texture, the user's 2026-11-08 "the red rocks and backdrops of Narsis do not fit here": its ground
# (57, 54, 37) against Shipal-Shin's (117, 69, 48), the Ascadian Isles' (57, 60, 40). The difference in hue, the
# shares of red and green in the colour, counts LOOK_HUE times; in brightness, the log of the ratio, LOOK_LIGHT)
LOOK_HUE = 6.0
LOOK_LIGHT = 0.6
# (only past these: ground nearly alike is as good as alike, and the weather and the map choose among them; without
# them a shade's difference took Skyrim's Vorndgad rock for Aunike Ridge over the Ascadian Isles' next door)
LOOK_HUE_OK = 0.05
LOOK_LIGHT_OK = 0.25
# (rocks that stay at home: Narsis's red mesa sandstone is Shipal-Shin's alone, never borrowed for other land; the
# user, 2026-11-09, "none of the other materials in the game fit with the desert mesa look there. Keep those rocks over
# there exclusively")
HOME_ROCKS = (('shipal-shin', re.compile(r'^t_mw_terrrocksh', re.I)),)


def _base(region):
    return re.sub(r'\s+region$', '', (region or '').lower().strip())


def home_rock_ok(rid, region):
    """May this rock model stand in this region? Not a home region's own rock outside it."""
    b = _base(region)
    return not any(rx.search(rid or '') and b != home for home, rx in HOME_ROCKS)


def home_region(region):
    """Is this a region whose rocks stay at home (lent to no other)?"""
    return _base(region) in {h for h, _rx in HOME_ROCKS}


_ROCKS = {}
_CENTRES = {}


_WEATHER = {}


def _weather(db, region):
    """A region's weather chances (a share each), from its record alone (regions.read lists its cells too: a pass
    over every cell a region, seconds for them all)."""
    import cliffsurvey
    import regions
    key = (cliffsurvey._sig(db), region)
    if key not in _WEATHER:
        w = None
        try:
            ri = regions._find(db, region)
            if ri is not None:
                subs, _f = regions._subs(db, ri)
                for t, d in subs:
                    if t == 'WEAT':
                        w = [d[n] if n < len(d) else 0 for n in range(10)]
        except Exception:
            w = None
        _WEATHER[key] = [v / (float(sum(w)) or 1.0) for v in w] if w else None
    return _WEATHER[key]


def _centres(db):
    """{region: (mean gx, mean gy)} of its outdoor cells."""
    import cliffsurvey
    sig = cliffsurvey._sig(db)
    if sig not in _CENTRES:
        import regions
        acc = {}
        for k, r in regions.region_map(db).items():
            try:
                gx, gy = map(int, k.split(','))
            except ValueError:
                continue
            a = acc.setdefault(r, [0.0, 0.0, 0])
            a[0] += gx
            a[1] += gy
            a[2] += 1
        _CENTRES.clear()
        _CENTRES[sig] = {r: (a[0] / a[2], a[1] / a[2]) for r, a in acc.items()}
    return _CENTRES[sig]


_TEXRGB = {}
_GROUND = {}


def _tex_rgb(db, f):
    """A texture file's mean colour (its smallest mip), or None."""
    if f not in _TEXRGB:
        rgb = None
        try:
            import assets
            path = db.meshes.texture_path(f)
            raw = db.meshes.read(path) if path else None
            d = assets._decode(raw, want=16) if raw else None
            if d:
                w, h, px = d
                n = w * h
                if n:
                    rgb = (sum(px[i * 4] for i in range(n)) / n, sum(px[i * 4 + 1] for i in range(n)) / n, sum(px[i * 4 + 2] for i in range(n)) / n)
        except Exception:
            rgb = None
        _TEXRGB[f] = rgb
    return _TEXRGB[f]


def ground_colour(db, region):
    """The mean colour of a region's own ground: its textures as the survey finds them laid, each by the ground it
    covers; None where the survey has none."""
    import cliffsurvey
    key = (cliffsurvey._sig(db), region)
    if key not in _GROUND:
        got = None
        try:
            import landdress
            _t3, t2 = landdress._tables(db, region)
            ns = ((_survey(db).get(region) or {}).get('textures')) or {}
            acc, tot = [0.0, 0.0, 0.0], 0.0
            for (sb, hb), lst in t2.items():
                n = (ns.get('%d,%d' % (sb, hb)) or {}).get('n', 0)
                for _rid, f, sh in lst:
                    c = _tex_rgb(db, f)
                    if c:
                        wv = sh * n
                        acc = [a + v * wv for a, v in zip(acc, c)]
                        tot += wv
            got = tuple(a / tot for a in acc) if tot else None
        except Exception:
            got = None
        _GROUND[key] = got
    return _GROUND[key]


def look_apart(a, b):
    """How unlike two ground colours are, past what counts as alike: hue (the shares of red and green) LOOK_HUE times,
    brightness LOOK_LIGHT."""
    if not a or not b:
        return 0.0
    sa, sb = sum(a) or 1.0, sum(b) or 1.0
    hue = abs(a[0] / sa - b[0] / sb) + abs(a[1] / sa - b[1] / sb)
    return LOOK_HUE * max(0.0, hue - LOOK_HUE_OK) + LOOK_LIGHT * max(0.0, abs(math.log(sa / sb)) - LOOK_LIGHT_OK)


def _clads(R):
    """Whether a region's survey shows its steep ground clad in cliff pieces."""
    bands = (R.get('bands') or [])[2:]
    n = sum(b.get('n', 0) for b in bands)
    area = sum(b.get('area', 0) for b in bands) or 1.0
    cover = sum((b.get('cover') or 0.0) * b.get('area', 0) for b in bands) / area
    return n >= ROCK_STEEP and cover >= ROCK_COVER


def clad_regions(db):
    """The regions whose steep ground the game clad in cliff pieces (the choices for Rocks from)."""
    import cliffsurvey
    S = cliffsurvey.ready(db)
    return sorted(r for r, R in ((S or {}).get('regions') or {}).items() if _clads(R))


def rock_region(db, region, like=''):
    """The region whose cliff pieces clad a region's steep ground (rockface.clad): its own where the game clad its
    own steep ground; else (Tamriel.esm sets only boulders 200-450 across, covering 4-7% of its steep ground) the
    region with cliff pieces nearest in weather and on the map, snow with snow, a province with its neighbours (the
    Gold Coast's Cyrodiil rock for the Heartlands), and whose ground looks like this one's (ground_colour: no red
    sandstone on dark olive land), the Like region first among equals."""
    import cliffsurvey
    S = cliffsurvey.ready(db)
    if S is None:
        return region
    key = (cliffsurvey._sig(db), region, like)
    if key in _ROCKS:
        return _ROCKS[key]
    regs = S.get('regions') or {}
    if _clads(regs.get(region) or {}):
        _ROCKS[key] = region
        return region
    # (a region named for a hand-made one is that one's land: Tamriel.esm's coarse "Shipal-Shin" is TR's Shipal-Shin
    # Region, red sandstone, though its own generic ground is olive)
    base = re.sub(r'\s+region$', '', region)
    for r in regs:
        if r != region and re.sub(r'\s+region$', '', r) == base and _clads(regs[r]):
            _ROCKS[key] = r
            return r
    mine = _weather(db, region)
    C = _centres(db)
    here = C.get(region)
    look = ground_colour(db, region)
    best, bd = like or region, None
    for r, R in regs.items():
        if not _clads(R) or (home_region(r) and _base(r) != _base(region)):
            continue
        w = _weather(db, r)
        if mine is None or w is None:
            continue
        d = sum(abs(a - b) for a, b in zip(mine, w)) - (0.1 if r == like else 0.0)
        if here and C.get(r):
            d += math.hypot(here[0] - C[r][0], here[1] - C[r][1]) / ROCK_FAR
        d += look_apart(look, ground_colour(db, r))
        if bd is None or d < bd:
            best, bd = r, d
    _ROCKS[key] = best
    return best


# ---------- the land's own trees, thinned as the game's stand ----------

# TR's trees a million square units by the slope under them, against its flat ground (research 2.4: .32 .35 .27 .11
# .035 at 0-10 / 10-20 / 20-30 / 30-45 / 45+): ten times fewer on cliffs. Tamriel.esm stands its trees evenly on
# any slope (.34 .36 .32 .21 .11) and the region pass moves the slopes under them, so each tree is kept by the
# slope it stands on now, at the band's middle
TREE_SLOPE = ((5.0, 1.0), (15.0, 1.0), (25.0, 0.84), (37.5, 0.34), (60.0, 0.11))
# ... and gathered into groves: Tamriel.esm's trees stand evenly (Clark-Evans R 1.13 in a cell), the game's in
# groves (TR 0.72, Vvardenfell 0.49). A tree is kept by a grove field, value noise 2,048 and 768 across
GROVE = ((2048.0, 0.7), (768.0, 0.3))
GROVE_CUT = -0.2                        # (the field's value under which the ground is open, ...)
GROVE_SOFT = 0.6                        # (... rising to full grove over this much)
TREE_OPEN = 0.25                        # (a tree in the open is kept at this share of a grove's)
TREE_GROW = 1.2                         # (new trees round each kept in a full grove, on average)
TREE_SPACE = 260.0                      # (no tree nearer another than this)
TREE_REACH = 700.0                      # (a new tree this far from the one it grows round at most)


def _slope_keep(deg):
    T = TREE_SLOPE
    if deg <= T[0][0]:
        return T[0][1]
    for (a, va), (b, vb) in zip(T, T[1:]):
        if deg <= b:
            return va + (vb - va) * (deg - a) / (b - a)
    return T[-1][1]


def _grove(x, y, seed):
    n = sum(w * landrange._value(x / lam, y / lam, seed + 907 + int(lam)) for lam, w in GROVE)
    return _smooth((n - GROVE_CUT) / GROVE_SOFT)


def _draw(rk):
    """A tree's own fixed draw, 0-1: the same tree is kept or thinned at every press."""
    h = 2166136261
    for ch in rk:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return (h % 100000) / 100000.0


def thin_trees(db, keys, F, hold=None, seed=1, amount=1.0):
    """The land's own trees (another plugin's, never the mod's) stood as the game's: taken out on steep ground
    (TREE_SLOPE) and more of them in the open between groves (TREE_OPEN), and the ones kept in a grove joined by a
    few of their own kind round them (TREE_GROW), so the trees gather in groves at about the land's own number.
    Never under a held building's ground or in the water. F: the field as written. Returns ({(gx, gy): [ref keys
    taken out]}, [new trees for cliffrocks.place]); restore_trees puts the first back, the second are the press's
    own (taken out again with its rocks)."""
    import random
    import cliffrocks
    import editing
    import landdecor
    from project import ref_info
    mine = db.project.plugin.lower()
    out, grown = {}, []
    kept = []                                   # (x, y, id, z over the ground, rx, ry, scale, grove)
    spots = {}                                  # (a 256 grid of the trees standing, for the spacing)

    def held(x, y):
        if hold is None:
            return False
        ix, iy = int(round((x - F.ox) / F.step)), int(round((y - F.oy) / F.step))
        return 0 <= ix < F.w and 0 <= iy < F.h and hold[iy * F.w + ix] >= 0.5

    def taken(x, y):
        gx, gy = int(x // 256), int(y // 256)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (px, py) in spots.get((gx + dx, gy + dy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < TREE_SPACE * TREE_SPACE:
                        return True
        return False

    def stand(x, y):
        spots.setdefault((int(x // 256), int(y // 256)), []).append((x, y))
    for k in keys:
        ck = '#%d,%d' % k
        try:
            refs, _hdr = db.cell_refs(ck)
        except Exception:
            continue
        c = None
        for rk, ref in refs.items():
            rid, pos, sc, dead = ref_info(ref['subs'])
            if dead or not rid or landdecor.kind_of(rid.lower()) != 'trees':
                continue
            x, y = pos[0], pos[1]
            if not (k[0] * 8192.0 <= x < (k[0] + 1) * 8192.0 and k[1] * 8192.0 <= y < (k[1] + 1) * 8192.0):
                continue
            if ref.get('origin') == mine or held(x, y):
                stand(x, y)
                continue
            sl = cliffrocks._slope_at(F, x, y)
            g = cliffrocks._height(F, x, y)
            if sl is None or g is None:
                stand(x, y)
                continue
            gr = _grove(x, y, seed)
            keep = _slope_keep(sl) * (TREE_OPEN + (1.0 - TREE_OPEN) * gr)
            keep = 1.0 - amount * (1.0 - keep)
            if _draw(ck + rk) < keep:
                stand(x, y)
                kept.append((x, y, rid, pos[2] - g, pos[3], pos[4], sc or 1.0, gr))
                continue
            if c is None:
                c, _r = editing._cell(db, ck)
            editing._store(c, rk, ref['origin'], ref['idx'], ref['subs'], deleted=True)
            out.setdefault(k, []).append(rk)
    # the groves filled in round the trees kept in them, each new one a tree of its neighbour's kind
    rng = random.Random(seed * 7349 + 3)
    inkeys = set(keys)
    for x, y, rid, over, rx, ry, sc, gr in kept:
        want = amount * TREE_GROW * gr
        n = int(want) + (1 if rng.random() < want - int(want) else 0)
        for _ in range(n):
            for _try in range(4):
                a = rng.uniform(0, 2 * math.pi)
                r = rng.uniform(TREE_SPACE, TREE_REACH)
                nx, ny = x + math.cos(a) * r, y + math.sin(a) * r
                if (math.floor(nx / 8192.0), math.floor(ny / 8192.0)) not in inkeys or held(nx, ny) or taken(nx, ny):
                    continue
                sl = cliffrocks._slope_at(F, nx, ny)
                g = cliffrocks._height(F, nx, ny)
                if sl is None or g is None or g <= 48 or rng.random() >= _slope_keep(sl) * _grove(nx, ny, seed):
                    continue
                stand(nx, ny)
                grown.append({'id': rid, 'x': nx, 'y': ny, 'z': g + over, 'rx': rx, 'ry': ry, 'rz': rng.uniform(0, 2 * math.pi),
                              's': round(sc * rng.uniform(0.85, 1.15), 3)})
                break
    return out, grown


def restore_trees(db, thinned):
    """The trees a press took out ({'gx,gy': [ref keys]}) put back, before the cells are shaped again."""
    n = 0
    for ck, rks in (thinned or {}).items():
        c = db.project.cells.get('#' + ck)
        for rk in rks:
            ref = c and c['refs'].get(rk)
            if ref and ref.get('deleted'):
                ref['deleted'] = False
                n += 1
    return n


# ---------- the cliffs' ground texture ----------

# Molagreahd's own patches (512 across) under its rock texture by their slope (lab 2026-11-08): 11% under 20 degrees,
# 34% at 20-35, 57% at 35-45, 75% at 45 and over. Tamriel.esm's regions have no rock texture where they are steep
# (none of their land was); the region pass's new cliffs came out grass, the Jerall Mountains' 45-degree patches
# 64% grass with Texture it too
ROCKY = re.compile(r'rock|cliff|scree|stone|crag|boulder|gravel', re.I)
CLIFF_TEX = (25.0, 50.0, 0.8)           # (a patch's chance of the cliff texture rises from 0 at the first slope to the third at the second)
_CLIFFTEX = {}


def _steep_texture(db, region):
    """(LTEX id, file) of the rock texture a region lays on its steep ground (30 degrees and over) far more than on
    the rest, or None."""
    import landdress
    _t3, t2 = landdress._tables(db, region)
    steep, every, ids = {}, {}, {}
    ns = ((_survey(db).get(region) or {}).get('textures')) or {}
    for (sb, hb), lst in t2.items():
        n = (ns.get('%d,%d' % (sb, hb)) or {}).get('n', 0)
        for rid, f, sh in lst:
            ids[f] = rid
            every[f] = every.get(f, 0.0) + sh * n
            if sb >= 3:
                steep[f] = steep.get(f, 0.0) + sh * n
    tot, tst = sum(every.values()), sum(steep.values())
    if not tot or tst < 50:
        return None
    best = None
    for f, v in steep.items():
        if not ROCKY.search(f) or 'road' in f:
            continue
        share = v / tst
        lift = share / max(1e-6, every[f] / tot)
        if share >= 0.08 and lift >= 1.3 and (best is None or share > best[0]):
            best = (share, ids[f], f)
    return best[1:] if best else None


def cliff_texture(db, region, like='', rockfrom=''):
    """(LTEX id, file) the pass's cliffs in a region are painted with: the region's own rock texture of its steep
    ground, else the rock region's (rock_region, whose cliff pieces clad it: snowy rock under snowy rock), else the
    Like region's; None if none of them has one."""
    key = (id(db.recs), region, like, rockfrom)
    if key not in _CLIFFTEX:
        got = None
        for r in [region, rockfrom or rock_region(db, region, like), like]:
            if r:
                got = _steep_texture(db, r)
                if got:
                    break
        _CLIFFTEX[key] = got
    return _CLIFFTEX[key]


def paint_cliffs(db, keys, heights, ids, reg, likes, rockfrom='', seed=1):
    """The new steep patches of the cells painted with their region's cliff texture (cliff_texture), by the chance
    CLIFF_TEX gives their slope, a fixed draw a patch. heights: {(gx, gy): 65 x 65}; ids: {(gx, gy): 256 LTEX ids},
    the cells' own read in where missing (so only the cliffs change). Returns the patches painted."""
    import landscape
    n = 0
    for k in keys:
        tex = cliff_texture(db, reg.get(k, ''), likes.get(reg.get(k, ''), ''), rockfrom)
        H = heights.get(k)
        if not tex or not H:
            continue
        T = ids.get(k)
        if T is None:
            T = list(landscape.read(db, k[0], k[1]).get('t') or [''] * 256)
        for py in range(16):
            for px in range(16):
                x0, y0 = px * 4, py * 4
                a, b = H[y0 * 65 + x0], H[y0 * 65 + x0 + 4]
                c, d = H[(y0 + 4) * 65 + x0], H[(y0 + 4) * 65 + x0 + 4]
                if min(a, b, c, d) <= 16:
                    continue
                sl = math.degrees(math.atan(math.hypot((b - a + d - c) / 2.0, (c - a + d - b) / 2.0) / 512.0))
                p = CLIFF_TEX[2] * _smooth((sl - CLIFF_TEX[0]) / (CLIFF_TEX[1] - CLIFF_TEX[0]))
                if p and _draw('%d,%d,%d,%d,%d' % (k[0], k[1], px, py, seed)) < p and T[py * 16 + px] != tex[0]:
                    T[py * 16 + px] = tex[0]
                    n += 1
        ids[k] = T
    return n


# ---------- plants ----------

# TR sets 19.5 plants a land cell, Tamriel.esm none (research 2.4). Its regions' own land has none to copy, so the
# plants come from the nearest region in weather and on the map that has its own (the Gold Coast's Cyrodiil shrubs
# 81 a cell, Druadach Highlands' and Vorndgad Forest's Skyrim herbs 16 and 50, from Cyr_Main and Sky_Main), laid
# square by square as landdecor lays them, thinned to PLANTS_CELL a cell at most
PLANTS_MIN = 5.0                        # (plants a cell a region needs to lend its own)
PLANTS_CELL = 24.0
PLANT_TRIES = 12                        # (regions learnt at most looking for one, nearest first: two seconds each)
_PLANTS = {}


def plants_a_cell(db, region):
    """The plants a cell the region's own wild land has (landdecor's squares)."""
    import landdecor
    try:
        L = landdecor.learn(db, region)
    except Exception:
        return 0.0
    sq = [q for v in (L.get('squares') or {}).values() for q in v]
    if not sq:
        return 0.0
    n = sum(1 for q in sq for it in q if landdecor.kind_of(it[0].lower()) == 'plants')
    return n / len(sq) * (8192.0 / landdecor.SQUARE) ** 2


def plant_region(db, region, like=''):
    """The region whose plants grow on a region's land: its own where it has PLANTS_MIN a cell, else the nearest in
    weather and on the map that has (the Like region first among equals); '' if none is found."""
    import cliffsurvey
    key = (cliffsurvey._sig(db), region, like)
    if key in _PLANTS:
        return _PLANTS[key]
    if plants_a_cell(db, region) >= PLANTS_MIN:
        _PLANTS[key] = region
        return region
    mine = _weather(db, region)
    C = _centres(db)
    here = C.get(region)
    ranked = []
    # (among the regions with hand-made land or clad cliffs, where the plants are: nearest first over every region,
    # twelve of Tamriel.esm's bare ones were learnt and none found, 30 s, lab 2026-11-08)
    for r in set(handmade(db)) | set(clad_regions(db)):
        if r == region:
            continue
        w = _weather(db, r)
        if mine is None or w is None or not C.get(r):
            continue
        d = sum(abs(a - b) for a, b in zip(mine, w)) - (0.1 if r == like else 0.0)
        if here:
            d += math.hypot(here[0] - C[r][0], here[1] - C[r][1]) / ROCK_FAR
        ranked.append((d, r))
    best = ''
    for _d, r in sorted(ranked)[:PLANT_TRIES]:
        if plants_a_cell(db, r) >= PLANTS_MIN:
            best = r
            break
    _PLANTS[key] = best
    return best


def grow_plants(db, keys, F, inside, hold, reg, likes, seed=1, k=1.0):
    """The plants for the cells (for cliffrocks.place): each cell's plant region's own squares of the same ground
    (landdecor.plan_growth), its plants only, thinned to PLANTS_CELL a cell. Returns (plants, {region: from})."""
    import random
    import landdecor
    src = {k: plant_region(db, reg.get(k, ''), likes.get(reg.get(k, ''), '')) for k in keys}
    if not any(src.values()):
        return [], {}
    dens = {r: plants_a_cell(db, r) for r in set(src.values()) if r}
    region_of = lambda x, y: src.get((math.floor(x / 8192.0), math.floor(y / 8192.0)), '') or ''
    items = landdecor.plan_growth(db, F, inside, hold, region_of, max(1.0, k), seed)
    rng = random.Random(seed * 3571 + 9)
    out = []
    for it in items:
        if landdecor.kind_of(it['id'].lower()) != 'plants':
            continue
        r = region_of(it['x'], it['y'])
        if not r:
            continue
        if rng.random() < min(1.0, k * PLANTS_CELL / max(1.0, dens.get(r, 1.0))):
            out.append(it)
    return out, {reg.get(k, ''): v for k, v in src.items() if v}


# ---------- region borders blended ----------

# TR's patches (512 across) near another region's land that carry that region's textures and hardly their own
# (lab a09, 2026-11-08): 19% within 1,024, 14% at 1,024-2,048, 7% at 2-4 km, 2% at 4-8 km, none past; Vvardenfell
# 23 / 18 / 10 / 2%. Tamriel.esm's own textures already mix there (they follow height across the region lines: 18% at
# the Gjerde Hills border, 44% at Gorvigh Ridge); the land the Workshop repaints region by region switches at the
# cell edge (7% at every distance). So repainted land only: a patch near the border takes the texture of the patch
# as far again over it (the other region's own layout, mirrored), by this chance at its distance in patches
BLEND0 = 0.9                            # (strong: the mirrored texture is often one both regions have, so at 0.28 a
                                        # repainted border's foreign share near it rose 7.6% -> 9.3%, at 0.9 to 16%; TR 19%)
BLEND_L = 6.0                           # (patches: the chance falls by e over this)
BLEND_MAX = 24                          # (patches: no blend past this)


def _chamfer(seed_mask, w, h, reach):
    """Each grid point's nearest seed (index) within reach (in points), by a two-pass chamfer; -1 where none."""
    INF = 1e9
    d = [0.0 if m else INF for m in seed_mask]
    near = [i if m else -1 for i, m in enumerate(seed_mask)]
    D2 = 1.4142
    for pas in (0, 1):
        ys = range(h) if pas == 0 else range(h - 1, -1, -1)
        xs = (range(w), ((-1, 0, 1.0), (0, -1, 1.0), (-1, -1, D2), (1, -1, D2))) if pas == 0 else \
             (range(w - 1, -1, -1), ((1, 0, 1.0), (0, 1, 1.0), (1, 1, D2), (-1, 1, D2)))
        for y in ys:
            for x in xs[0]:
                i = y * w + x
                for dx, dy, c in xs[1]:
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and 0 <= yy < h:
                        j = yy * w + xx
                        if d[j] + c < d[i]:
                            d[i] = d[j] + c
                            near[i] = near[j]
    return [n if dd <= reach else -1 for n, dd in zip(near, d)]


def blend_borders(db, keys, heights, ids, reg, seed=1):
    """Textures across the region borders the cells touch, as the game blends them: a patch within BLEND_MAX of
    another region's land takes, by the chance BLEND0 * e^(-d / BLEND_L) and a blotchy field, the texture of the
    patch as far again over the border. heights / ids: the cells' new heights and LTEX ids (read in where missing;
    the cells round them read as they are). Returns the patches changed."""
    import landscape
    import mapdata
    if not keys:
        return 0
    R = (BLEND_MAX + 15) // 16 + 1               # (cells round the marked ones read for their textures)
    xs, ys = [k[0] for k in keys], [k[1] for k in keys]
    X0, Y0, X1, Y1 = min(xs) - R, min(ys) - R, max(xs) + R, max(ys) + R
    w, h = (X1 - X0 + 1) * 16, (Y1 - Y0 + 1) * 16
    tex = [''] * (w * h)
    code = [-1] * (w * h)
    names = {}
    mine = set(keys)
    for cx in range(X0, X1 + 1):
        for cy in range(Y0, Y1 + 1):
            k = (cx, cy)
            r = reg.get(k)
            if r is None:
                ci = mapdata.cell_info(db, '#%d,%d' % k)
                r = (ci or {}).get('region', '').lower() if ci else ''
            if not r:
                continue
            H = heights.get(k) if k in mine else None
            T = ids.get(k) if k in mine else None
            if H is None or T is None:
                Lr = landscape.read(db, cx, cy)
                if not Lr.get('exists'):
                    continue
                H = H or Lr['h']
                T = T if T is not None else list(Lr.get('t') or [''] * 256)
            c = names.setdefault(r, len(names))
            for py in range(16):
                for px in range(16):
                    x0, y0 = px * 4 + 2, py * 4 + 2
                    if H[y0 * 65 + x0] <= 0:
                        continue
                    i = ((cy - Y0) * 16 + py) * w + (cx - X0) * 16 + px
                    tex[i] = T[py * 16 + px]
                    code[i] = c
    if len(names) < 2:
        return 0
    n = 0
    for r, c in names.items():
        if not any(reg.get(k) == r for k in keys):
            continue
        near = _chamfer([cc >= 0 and cc != c for cc in code], w, h, BLEND_MAX)
        for k in keys:
            if reg.get(k) != r or k not in ids and heights.get(k) is None:
                continue
            T = ids.get(k)
            if T is None:
                T = ids[k] = list(landscape.read(db, k[0], k[1]).get('t') or [''] * 256)
            for py in range(16):
                for px in range(16):
                    gx, gy = (k[0] - X0) * 16 + px, (k[1] - Y0) * 16 + py
                    i = gy * w + gx
                    q = near[i]
                    if q < 0 or code[i] != c:
                        continue
                    qx, qy = q % w, q // w
                    d = math.hypot(qx - gx, qy - gy)
                    p = BLEND0 * math.exp(-d / BLEND_L)
                    wx, wy = (k[0] * 16 + px) * 512.0, (k[1] * 16 + py) * 512.0
                    u = 0.5 + 0.45 * landrange._value(wx / 1536.0, wy / 1536.0, seed + 313) + 0.25 * (_draw('%d,%d,%d' % (gx, gy, seed)) - 0.5)
                    if u >= p:
                        continue
                    # (as far again over the border: the other region's own layout; else the nearest patch of it)
                    mx, my = 2 * qx - gx, 2 * qy - gy
                    j = my * w + mx if 0 <= mx < w and 0 <= my < h else -1
                    t = tex[j] if j >= 0 and code[j] == code[q] and tex[j] else tex[q]
                    if t and T[py * 16 + px] != t:
                        T[py * 16 + px] = t
                        n += 1
    return n


# ---------- the field helpers (on the plan's every-512 grid) ----------

def _coarse(F):
    k = max(1, int(round(512.0 / F.step)))
    w, h = (F.w - 1) // k + 1, (F.h - 1) // k + 1
    z = [F.z[(y * k) * F.w + x * k] for y in range(h) for x in range(w)]
    return k, w, h, z


def _slide(vals, w, h, r, fn):
    """A sliding min or max over a (2r+1) square, rows then columns."""
    tmp = [0.0] * (w * h)
    for y in range(h):
        row = vals[y * w:(y + 1) * w]
        for x in range(w):
            tmp[y * w + x] = fn(row[max(0, x - r):x + r + 1])
    out = [0.0] * (w * h)
    for x in range(w):
        col = tmp[x::w]
        for y in range(h):
            out[y * w + x] = fn(col[max(0, y - r):y + r + 1])
    return out


def _local_rough(z, w, h, lag=4, r=4):
    """RMS height difference `lag` coarse points apart (2,048 at 512), averaged over a (2r+1) square round each point."""
    sq = [0.0] * (w * h)
    n = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if z[i] <= 0:
                continue
            for j, ok in ((i + lag, x + lag < w), (i + lag * w, y + lag < h)):
                if ok and z[j] > 0:
                    d = z[j] - z[i]
                    sq[i] += d * d
                    n[i] += 1
    # (box sums by rows then columns)
    def box(a):
        t = [0.0] * (w * h)
        for y in range(h):
            row = a[y * w:(y + 1) * w]
            for x in range(w):
                t[y * w + x] = sum(row[max(0, x - r):x + r + 1])
        o = [0.0] * (w * h)
        for x in range(w):
            col = t[x::w]
            for y in range(h):
                o[y * w + x] = sum(col[max(0, y - r):y + r + 1])
        return o
    S, N = box(sq), box([float(v) for v in n])
    return [math.sqrt(S[i] / N[i]) if N[i] else 0.0 for i in range(w * h)]


def _up(F, k, w, h, vals, i):
    """A coarse grid's value at a point of F, bilinear."""
    x, y = i % F.w, i // F.w
    cx, tx = divmod(x, k)
    cy, ty = divmod(y, k)
    tx /= k
    ty /= k
    cx1, cy1 = min(cx + 1, w - 1), min(cy + 1, h - 1)
    return ((vals[cy * w + cx] * (1 - tx) + vals[cy * w + cx1] * tx) * (1 - ty)
            + (vals[cy1 * w + cx] * (1 - tx) + vals[cy1 * w + cx1] * tx) * ty)


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# ---------- the pass ----------

def run(db, F, inside, opts, seed, here, say=None):
    """The pass on F's points inside (0/1 a point), in place. here: {region: weight a point} (where each point is,
    landshapes._region_weights). Returns the info for the note: per region what it took after and did."""
    T = clean(opts)
    say = say or (lambda what, frac: None)
    pts = [i for i in range(len(F.z)) if inside[i]]
    # (only the regions with weight on the points worked: the grid's ring reaches into the next region's cells)
    here = {r: w for r, w in here.items() if any(w[i] for i in pts)}
    plans = {r: plan_for(db, r, T['like']) for r in here}
    # (said for the regions the marked land is mostly in; a neighbour's blends in over the edge cells' outer halves)
    info = {'like': {r: p['like'] for r, p in plans.items() if any(here[r][i] >= 0.5 for i in pts)}, 'regions': {}}
    if T['rocks'] and T['cliffs'] > 0:
        # (whose cliff pieces the steep ground will be clad in when it is shaped, landshapes._apply)
        info['rocks'] = {r: T['rockfrom'] or rock_region(db, r, l) for r, l in info['like'].items()}
    if T['plants']:
        info['plants'] = {r: plant_region(db, r, l) for r, l in info['like'].items()}
    if not pts:
        return info
    k, w, h, cz = _coarse(F)
    # how far each point stands over its valley floors (4,096 round), and how rough the land round it already is
    if T['ranges'] > 0 or T['relief'] > 0:
        say('Reading the land', 0.08)
        floor = _slide(cz, w, h, max(1, int(round(4096 / 512.0))), min)
        over = [max(0.0, a - b) for a, b in zip(cz, floor)]
        lr = _local_rough(cz, w, h)
    step = F.step
    cut = 2.0 * step                     # (layers finer than two points of the grid can't show: the preview skips them)
    oct_on = [lam >= cut for lam in OCTAVES]
    wts = list(here.items())
    for r, p in plans.items():
        info['regions'][r] = {'like': p['like'], 'have': p['have'], 'want': p['want'],
                              'layers': [round(a) for a in p['amps']], 'ranges': round(p['ranges'])}
    rs, ra = T['ranges'], T['relief']
    if rs > 0 or ra > 0:
        say('Raising the ranges and the rolling ground', 0.12)
        z = F.z
        for i in pts:
            z0 = z[i]
            if z0 <= 0:
                continue
            x, y = F.world(i)
            amps = [0.0] * len(OCTAVES)
            rng = 0.0
            fsum = 0.0
            loc = _up(F, k, w, h, lr, i)
            for r, wr in wts:
                a = wr[i]
                if not a:
                    continue
                p = plans[r]
                rng += a * p['ranges']
                # (the step of F_BINS this point's own roughness falls in, between two steps linearly)
                f = max(F_BINS[0], min(F_BINS[-1], loc / max(1.0, p['r2048'])))
                fsum += a * f
                b = min(len(F_BINS) - 2, int(math.log(f / F_BINS[0]) / math.log(1.25)))
                t = (f - F_BINS[b]) / (F_BINS[b + 1] - F_BINS[b])
                lo, hi = p['table'][b], p['table'][b + 1]
                for o in range(len(OCTAVES)):
                    amps[o] += a * (lo[o] + (hi[o] - lo[o]) * t)
            up = _up(F, k, w, h, over, i)
            shore = min(1.0, z0 / SHORE)
            add = 0.0
            if rs > 0 and rng > 0:
                # (only on land standing 300+ over its floors, fully from 1,500)
                m = _smooth((up - 300.0) / 1200.0)
                if m:
                    add += rs * rng * m * _ranges_noise(x, y, seed)
            if ra > 0:
                # (craggier, sharp crests, where the land round it is rougher than its region's)
                crag = max(0.0, min(0.7, (math.sqrt(fsum) - 0.8) * 0.7))
                s = 0.0
                for o, lam in enumerate(OCTAVES):
                    if oct_on[o] and amps[o]:
                        s += amps[o] * _octave(x, y, lam, seed, crag)
                add += ra * s
            v = z0 + add * shore
            # (never taking dry land under the water: half its height over 32 at most)
            z[i] = max(v, 32 + 0.5 * (z0 - 32) if z0 > 32 else z0)
    # where the escarpments go, on the land as the relief left it (a fixed function of it, as the rest)
    esc, hard, RP = None, None, None
    if T['cliffs'] > 0:
        import landrock
        say('Finding the escarpments', 0.2)
        k, w, h, cz = _coarse(F)
        floor = _slide(cz, w, h, max(1, int(round(4096 / 512.0))), min)
        over = [max(0.0, a - b) for a, b in zip(cz, floor)]
        lr = _local_rough(cz, w, h)
        esc = [0.0] * len(F.z)
        for i in pts:
            if F.z[i] <= SHORE:
                continue
            amt = ref = 0.0
            for r, wr in wts:
                if wr[i]:
                    p = plans[r]
                    amt += wr[i] * min(1.5, p['steep45'] / CLIFF_45)
                    ref += wr[i] * max(1.0, p['want']['2048'] or p['r2048'])
            if amt <= 0:
                continue
            m_over = _smooth((_up(F, k, w, h, over, i) - CLIFF_OVER[0]) / (CLIFF_OVER[1] - CLIFF_OVER[0]))
            m_f = _smooth((_up(F, k, w, h, lr, i) / max(1.0, ref) - CLIFF_F[0]) / (CLIFF_F[1] - CLIFF_F[0]))
            esc[i] = min(1.0, T['cliffs'] * amt * math.sqrt(m_over * m_f))
        # (the layers dip a few degrees one way, the same for the whole world at a seed: two runs side by side meet)
        RP = {'thick': CLIFF_THICK, 'share': CLIFF_SHARE, 'dip': 3.0 + (seed * 7919 % 9), 'dir': seed * 104729 % 360}
        raw = landrock.hardness(F, inside, RP, seed)
        hard = [a * b for a, b in zip(raw, esc)]
        info['escarpment'] = round(sum(1 for i in pts if esc[i] >= 0.5) / max(1, len(pts)), 3)
    if T['valleys'] > 0:
        import landwater
        say('Carving the valleys', 0.22)
        wgt = [1.0 if inside[i] else 0.0 for i in range(len(F.z))]
        _A, _w, deep = landwater.valleys(F, inside, wgt, T['valleys'], seed, hard, K=VALLEY_K)
        info['valleys'] = round(deep)
    if esc is not None:
        say('Stepping the hard rock into cliffs', 0.40)
        info['stepped'] = landrock.stratify(F, inside, RP, [e * (1.0 - CLIFF_KEEP) for e in esc], CLIFF_STEP, seed)
    import landpasses
    say('Settling the steepest slopes', 0.45)
    ang = [0.0] * len(F.z)
    for r, wr in wts:
        s99 = plans[r]['slope99']
        for i in pts:
            if wr[i]:
                ang[i] += wr[i] * s99
    for i in range(len(ang)):
        if not ang[i]:
            ang[i] = 62.0
    if esc is not None:
        # (hard bands stand as cliffs, soft ones slide back to scree; elsewhere the region's own angle)
        ang = landrock.angles(ang, raw, inside, CLIFF_ANGLE, esc)
        info['too_steep'] = landpasses.settle(F, inside, ang, rounds=60)
    else:
        info['too_steep'] = landpasses.settle(F, inside, ang)
    # (no corner rounding: TR's own land has kinks at 9% of its points, VV 8%; rounded, the pass left 1-5%)
    return info


MATCH_RAMP = 4.0
MATCH_MAX = 8192.0


def match_edges(F, inside, computed_ring, actual_ring, fade):
    """Where the marked cells meet cells the mod already changed (the ring): the pass was worked out over the ring
    too, from the land under the mod (computed_ring {point: height}); the difference from what the ring holds
    (actual_ring) is carried into the marked cells, fading over `fade`, so the two meet with no step and no band of
    the game's land between them. Returns the largest difference."""
    if not computed_ring:
        return 0.0
    d = {i: actual_ring[i] - computed_ring[i] for i in computed_ring}
    w, h = F.w, F.h
    # (carried over at least MATCH_RAMP times the difference, so it adds no slope steeper than about 14 degrees: the
    # cliffs make the two runs differ by up to 1,700 at the join where their grids saw different land round them,
    # and over the 1,024 of the fade that stood as a crease along it, lab 2026-11-08)
    big = sorted(abs(v) for v in d.values())
    p90 = big[int(0.9 * (len(big) - 1))] if big else 0.0
    fade = min(MATCH_MAX, max(fade, MATCH_RAMP * p90))
    reach = max(1, int(round(fade / F.step)))
    # (each point inside takes the difference at the nearest ring point along its row and column, within reach,
    # weighted by closeness; the edge rows themselves are the ring's)
    acc = {}
    for i in range(len(F.z)):
        if not inside[i]:
            continue
        x, y = i % w, i // w
        num = den = top = 0.0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for s in range(1, reach + 1):
                xx, yy = x + dx * s, y + dy * s
                if not (0 <= xx < w and 0 <= yy < h):
                    break
                j = yy * w + xx
                if j in d:
                    t = 1.0 - _smooth((s - 1) / float(reach))
                    num += d[j] * t
                    den += t
                    top = max(top, t)
                    break
                if not inside[j]:
                    break
        if den:
            # (the nearest side's closeness, shared between the sides by theirs: at a corner both sides' mean)
            acc[i] = num * top / den
    for i, v in acc.items():
        F.z[i] += v
    return max((abs(v) for v in d.values()), default=0.0)
