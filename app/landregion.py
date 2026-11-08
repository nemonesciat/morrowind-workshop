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

import landrange

LAG_KEYS = ('128', '512', '2048')
OCTAVES = (4096.0, 2048.0, 1024.0, 512.0, 256.0)
RANGE_WAVE = 9600.0                     # (the game's crest spacing, VV 9,216, TR 9,728, research 2.8)
HANDMADE_128 = 40.0                     # (a region whose land is this rough 128 apart was made by hand; heightmaps 10-30)
DEFAULTS = {'on': False, 'like': '', 'relief': 1.0, 'ranges': 1.0, 'valleys': 1.0, 'paint': False}
VALLEY_K = 0.02
SHORE = 400.0                           # (the detail fades out below this height, as match_roughness's)
RIDGE_MEAN = 0.0


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


def plan_for(db, region, want=''):
    """What the pass does to a region's land: {'like', 'amps' (one a layer), 'ranges' (amplitude), 'slope99'}."""
    S = _survey(db)
    R = S.get(region) or {}
    lk = like_for(db, region, want)
    T = S.get(lk) or {}
    have = {L: _fig(R, L) for L in LAG_KEYS}
    tgt = {L: _fig(T, L) for L in LAG_KEYS}
    if not all(tgt.values()) or not all(have.values()):
        amps = [0.0] * len(OCTAVES)
    else:
        amps = layer_amps(have, tgt)
    h8, t8 = _fig(R, '8192'), _fig(T, '8192')
    need8 = math.sqrt(max(0.0, t8 * t8 - h8 * h8))
    # (laid on only where the land stands over its floors, about half of a mountain region's points: twice the
    # variance there for the same over all)
    rng = need8 / math.sqrt(max(1e-6, _probes()[('ranges', '8192')])) / math.sqrt(0.5) if need8 > 32 else 0.0
    try:
        s99 = float((T.get('slope') or {}).get('99') or 62.0)
    except (TypeError, ValueError):
        s99 = 62.0
    return {'like': lk, 'amps': amps, 'ranges': rng, 'slope99': s99, 'have': have, 'want': tgt, 'h8192': h8, 't8192': t8,
            'r2048': have['2048'] or 1.0}


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
    plans = {r: plan_for(db, r, T['like']) for r in here}
    info = {'like': {r: p['like'] for r, p in plans.items()}, 'regions': {}}
    pts = [i for i in range(len(F.z)) if inside[i]]
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
            ref = 0.0
            for r, wr in wts:
                a = wr[i]
                if not a:
                    continue
                p = plans[r]
                rng += a * p['ranges']
                ref += a * p['r2048']
                for o, v in enumerate(p['amps']):
                    amps[o] += a * v
            up = _up(F, k, w, h, over, i)
            loc = _up(F, k, w, h, lr, i)
            shore = min(1.0, z0 / SHORE)
            add = 0.0
            if rs > 0 and rng > 0:
                # (only on land standing 300+ over its floors, fully from 1,500)
                m = _smooth((up - 300.0) / 1200.0)
                if m:
                    add += rs * rng * m * _ranges_noise(x, y, seed)
            if ra > 0:
                # (rougher where the land already rises: 0.35 to 2 times, by its roughness round it against the region's)
                rel = max(0.35, min(2.0, math.sqrt(max(0.0, loc) / max(1.0, ref)))) if ref else 1.0
                crag = max(0.0, min(0.7, (rel - 0.8) * 0.7))
                s = 0.0
                for o, lam in enumerate(OCTAVES):
                    if oct_on[o] and amps[o]:
                        s += amps[o] * _octave(x, y, lam, seed, crag)
                add += ra * rel * s
            v = z0 + add * shore
            # (never taking dry land under the water: half its height over 32 at most)
            z[i] = max(v, 32 + 0.5 * (z0 - 32) if z0 > 32 else z0)
    if T['valleys'] > 0:
        import landwater
        say('Carving the valleys', 0.22)
        wgt = [1.0 if inside[i] else 0.0 for i in range(len(F.z))]
        _A, _w, deep = landwater.valleys(F, inside, wgt, T['valleys'], seed, None, K=VALLEY_K)
        info['valleys'] = round(deep)
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
    info['too_steep'] = landpasses.settle(F, inside, ang)
    say('Rounding the corners', 0.55)
    info['corners'] = landpasses.corners(F, inside)
    return info


def match_edges(F, inside, computed_ring, actual_ring, fade):
    """Where the marked cells meet cells the mod already changed (the ring): the pass was worked out over the ring
    too, from the land under the mod (computed_ring {point: height}); the difference from what the ring holds
    (actual_ring) is carried into the marked cells, fading over `fade`, so the two meet with no step and no band of
    the game's land between them. Returns the largest difference."""
    if not computed_ring:
        return 0.0
    d = {i: actual_ring[i] - computed_ring[i] for i in computed_ring}
    w, h = F.w, F.h
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
