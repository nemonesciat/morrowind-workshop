"""Rock over a land plan (packaging/landscaping-plan.md, the rock stage): layers of hard and soft rock, and crags.

  layers   bands of rock by height, each hard or soft, tilted by a dip and wavering a little. Hard rock stands
           steep and the water cuts it slowly; soft rock slides back to a scree slope and wears fast. Worked by
           the passes the plan already has: settle (landpasses) takes each point's own angle, so a slope through
           the bands steps into cliffs and ledges with scree at their feet; the valleys (landwater) cut narrow
           through the hard bands and open out in the soft
  crags    ridged noise (1 - |n|, each finer layer weighted by the one above: a "ridged multifractal"), its
           sample point pushed about by another noise (domain warping), so a range's crest breaks into sharp
           arêtes and spurs, not the round lumps plain noise gives"""
import math

import landrange

# a hard band stands at this at least (the record's 128-unit grid gives about 80 at the steepest), a soft one
# slides back towards the angle of loose rock (scree rests at 33-38 degrees)
HARD = 76.0
SCREE = 36.0


def _band_hard(n, seed, share):
    """Whether band n is hard: a fixed hash, so a band keeps its rock as the land is shaped again."""
    h = (n * 2654435761 + seed * 40503) & 0xFFFFFFFF
    h = ((h ^ (h >> 15)) * 2246822519) & 0xFFFFFFFF
    return (h % 1000) < share * 1000


def hardness(F, inside, P, seed=1):
    """0-1 at each point of F (inside the plan; 0 elsewhere): how hard the rock is there, by the band its height
    falls in. P: thick (a band's height), dip and dir (degrees: the layers' tilt and the way they dip), share
    (of the bands, the hard ones)."""
    thick = max(64.0, float(P.get('thick', 384.0)))
    dip = math.tan(math.radians(max(0.0, min(60.0, float(P.get('dip', 0.0))))))
    d = math.radians(float(P.get('dir', 0.0)))
    cx, cy = math.cos(d) * dip, math.sin(d) * dip
    share = max(0.0, min(1.0, float(P.get('share', 0.45))))
    edge = 0.18                                  # (of a band, the part either side where it turns from one to the next)
    out = [0.0] * len(F.z)
    for i in range(len(F.z)):
        if not inside[i] or F.z[i] <= 0:
            continue
        x, y = F.world(i)
        # (the bands waver a little, a fifth of a band, so their edges aren't contour lines)
        t = (F.z[i] + x * cx + y * cy) / thick + 0.2 * landrange._value(x / 3072.0, y / 3072.0, seed + 811)
        n = math.floor(t)
        f = t - n
        a = 1.0 if _band_hard(n, seed, share) else 0.0
        if f < edge:
            b = 1.0 if _band_hard(n - 1, seed, share) else 0.0
            k = 0.5 + 0.5 * (f / edge)
            out[i] = b + (a - b) * (k * k * (3 - 2 * k))
        elif f > 1 - edge:
            b = 1.0 if _band_hard(n + 1, seed, share) else 0.0
            k = 0.5 + 0.5 * ((1 - f) / edge)
            out[i] = b + (a - b) * (k * k * (3 - 2 * k))
        else:
            out[i] = a
    return out


def stratify(F, inside, P, weight, strength=1.0, seed=1):
    """The plan's slopes stepped by the layers: in a hard band the ground rises fast at its foot (the cliff) and
    levels off on top (the ledge of the caprock); a soft band keeps its slope, for settle to wear back to scree.
    A height remap within each band, so flat ground (a plateau top, the sea) is left as it is and a slope through
    the bands is what steps. weight: 0-1 a point (how far the plan made that ground). Returns the points changed."""
    thick = max(64.0, float(P.get('thick', 384.0)))
    dip = math.tan(math.radians(max(0.0, min(60.0, float(P.get('dip', 0.0))))))
    d = math.radians(float(P.get('dir', 0.0)))
    cx, cy = math.cos(d) * dip, math.sin(d) * dip
    share = max(0.0, min(1.0, float(P.get('share', 0.45))))
    p = 1.0 + 5.0 * max(0.0, min(1.0, strength))
    n_changed = 0
    for i in range(len(F.z)):
        z = F.z[i]
        if not inside[i] or z <= 0 or not weight[i]:
            continue
        x, y = F.world(i)
        off = x * cx + y * cy
        wav = 0.2 * landrange._value(x / 3072.0, y / 3072.0, seed + 811)
        t = (z + off) / thick + wav
        n = math.floor(t)
        f = t - n
        if not _band_hard(n, seed, share):
            continue
        g = 1.0 - (1.0 - f) ** p
        nz = (n + g - wav) * thick - off
        F.z[i] = z + (nz - z) * weight[i]
        n_changed += 1
    return n_changed


def angles(base, hard, inside, strength=1.0, where=None):
    """Each point's settling angle with the rock: from its region's (base, one or a list) towards a cliff's in
    hard rock (the region's own steepest and 12 degrees, 76 at most) and towards scree in soft, by strength (0-1)
    and by where (0-1 a point: the layers' own ground; elsewhere the region's angle stands, so soft rock doesn't
    wear back the game's land or a region left out)."""
    out = []
    for i, h in enumerate(hard):
        b = base if isinstance(base, (int, float)) else base[i]
        s = max(0.0, min(1.0, strength)) * (1.0 if where is None else where[i])
        if not inside[i] or not s:
            out.append(b)
            continue
        # (hard rock stands steeper than the region's own steepest ground, but by 12 degrees at most: at 76 everywhere
        # the Grazelands, 52 of their own, got the Ashlands' cliffs)
        hi, lo = max(b, min(HARD, b + 12.0)), min(b, SCREE + (b - SCREE) * 0.25)
        out.append(b + ((lo + (hi - lo) * h) - b) * s)
    return out


def ridged(x, y, seed, warp=1.0):
    """Ridged multifractal noise at a world point, 0-1 (sharp crests near 1), its sample point warped."""
    if warp:
        wx = landrange._value(x / 4096.0, y / 4096.0, seed + 71) * 1200.0 * warp
        wy = landrange._value(x / 4096.0, y / 4096.0, seed + 72) * 1200.0 * warp
        x, y = x + wx, y + wy
    total, norm, weight = 0.0, 0.0, 1.0
    amp = 1.0
    # (3072 down to 384 across: the broader ones made a range lumpy, not craggy, lab 2026-10-28)
    for lam in (3072.0, 1536.0, 768.0, 384.0):
        n = 1.0 - abs(landrange._value(x / lam, y / lam, seed + int(lam)))
        n *= n
        n *= weight
        weight = max(0.0, min(1.0, n * 1.6))
        total += n * amp
        norm += amp
        amp *= 0.55
    return total / norm
