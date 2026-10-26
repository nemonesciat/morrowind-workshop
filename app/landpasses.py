"""The natural passes over a land plan (packaging/terrain-shaping-proposal.md, stage 3), run on landshapes' working
grid after its shapes and rolling ground and before the fade at the marked cells' edge, so the edges never move:

  settle    slope settling (thermal erosion): ground slides from a point to a lower neighbour while the slope
            between them is over the settling angle; by default the region's own 99th-percentile slope from the
            land survey (landsurvey 'slope'), so the plan keeps no more cliff than the region has
  gullies   rain gullies (a light hydraulic erosion): raindrops start on the land, run downhill, pick up ground
            where they speed up and drop it where they slow or reach the water: gullies down the slopes and fans
            at their feet; the strength scales how many drops and how much each carries
  terraces  steps on the slopes over an angle (the Ashlands and Molag Amur look): heights are drawn to steps of
            the step height, sharper or softer

Each works in the grid's own spacing (a point every 128 units at apply, 512 in the preview), with rates scaled
so the preview looks like what apply makes. Nothing here touches points outside the marked cells."""
import math
import random

DEG = math.pi / 180


def settle(F, inside, angle, rounds=24, rate=0.5):
    """Thermal erosion: the steepest steps eased down to the angle. Returns how many steps were over it at first."""
    w, h, z = F.w, F.h, F.z
    T = math.tan(angle * DEG) * F.step
    Td = T * math.sqrt(2)
    pairs = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not inside[i]:
                continue
            if x + 1 < w and inside[i + 1]:
                pairs.append((i, i + 1, T))
            if y + 1 < h and inside[i + w]:
                pairs.append((i, i + w, T))
            if x + 1 < w and y + 1 < h and inside[i + w + 1]:
                pairs.append((i, i + w + 1, Td))
            if x > 0 and y + 1 < h and inside[i + w - 1]:
                pairs.append((i, i + w - 1, Td))
    first = sum(1 for a, b, t in pairs if abs(z[a] - z[b]) > t)
    # Each round goes through the pairs in order, as a sweep over all of them would, but only the pairs one of whose
    # points has moved since that pair was last looked at: any other is as it was, under the angle, and would be
    # passed over. The same moves in the same order as the full sweep (the same heights to the last digit), a
    # fraction of the work once the first round is done (2026-10-26: 24 rounds over 920,000 pairs before).
    import heapq
    adj = {}
    for p, (a, b, _t) in enumerate(pairs):
        adj.setdefault(a, []).append(p)
        adj.setdefault(b, []).append(p)
    todo = list(range(len(pairs)))
    for _ in range(rounds):
        if not todo:
            break
        heapq.heapify(todo)
        queued = set(todo)
        nxt = set()
        while todo:
            p = heapq.heappop(todo)
            a, b, t = pairs[p]
            d = z[a] - z[b]
            if d > t:
                m = (d - t) * rate * 0.5
                z[a] -= m
                z[b] += m
            elif d < -t:
                m = (-d - t) * rate * 0.5
                z[a] += m
                z[b] -= m
            else:
                continue
            # (a and b moved: their pairs later in this round are looked at in it, the rest next round)
            for q in adj[a] + adj[b]:
                if q > p:
                    if q not in queued:
                        queued.add(q)
                        heapq.heappush(todo, q)
                else:
                    nxt.add(q)
        todo = sorted(nxt)
    return first


def _rms(F, inside, lag, mask=None):
    """RMS height difference `lag` points apart along the rows, over the land (above the water) inside."""
    w, z = F.w, F.z
    a, n = 0.0, 0
    for i in range(len(z)):
        if not inside[i] or z[i] <= 0 or (mask is not None and not mask[i]):
            continue
        j = i + lag
        if (i % w) + lag < w and inside[j] and z[j] > 0:
            d = z[j] - z[i]
            a += d * d
            n += 1
    return math.sqrt(a / n) if n else 0.0


def match_roughness(F, inside, mask, target, seed=1, rounds=3, target128=None):
    """match_roughness_once, again while the land is still short of the target by more than 5% (the guards near the
    water take some of each round away), and no further once it is as rough close up as the region (target128, the
    figure 128 apart that goes with its slopes: the detail is rougher close up than the game's land, and topping
    up 1024 apart past it made the Ashlands 32% steep against the game's 23%). Returns the amplitudes, summed."""
    total = 0.0
    for k in range(rounds):
        a = match_roughness_once(F, inside, mask, target, seed + 31 * k)
        if a <= 0:
            return total + a if not total else total
        total += a
        lag = max(1, int(round(1024 / F.step)))
        if _rms(F, inside, lag, mask) >= target * 0.95:
            break
        if target128 and F.step <= 128 and _rms(F, inside, 1, mask) >= target128 * 0.95:
            break
        if F.step > 128 and k >= 0:
            break                       # (the preview's grid can't see 128 apart: one round, as the first of apply's)
    return total


def match_roughness_once(F, inside, mask, target, seed=1):
    """Rolling detail added to the plan's land (mask: the points the plan made) until its roughness 1024 units apart
    is the region's (target, landsurvey 'rough' '1024'): layers 4096 down to 512 across, each smaller one fainter
    by the game's exponent (0.78). Never takes dry land under the water. Returns the amplitude used."""
    import landrange
    lag = max(1, int(round(1024 / F.step)))
    have = _rms(F, inside, lag, mask)
    if have > target * 1.1:
        return -_smooth_to(F, inside, mask, lag, target)
    need = math.sqrt(max(0.0, target * target - have * have))
    if need < 8:
        return 0.0
    # (the detail's own roughness at that distance, at amplitude 1, measured on this grid)
    probe = [0.0] * len(F.z)
    idx = [i for i in range(len(F.z)) if inside[i] and mask[i] and F.z[i] > 0]
    if len(idx) < 50:
        return 0.0
    for i in idx:
        x, y = F.world(i)
        probe[i] = _detail(x, y, seed)
    a, n = 0.0, 0
    w = F.w
    for i in idx:
        if (i % w) + lag < w and mask[i + lag] and inside[i + lag]:
            d = probe[i + lag] - probe[i]
            a += d * d
            n += 1
    unit = math.sqrt(a / n) if n else 1.0
    amp = need / max(1e-6, unit)
    for i in idx:
        z = F.z[i]
        v = z + probe[i] * amp * min(1.0, z / 400.0)
        F.z[i] = max(v, 32 + 0.5 * (z - 32) if z > 32 else z)
    return amp


def _smooth_to(F, inside, mask, lag, target):
    """The plan's land softened towards a blur as wide as the distance measured (lag points), by just enough that its
    roughness there comes down to the target, a softer region's (the Bitter Coast's 300 against the shapes' 340).
    Dry land stays dry. Returns how far towards the blur it went, in hundredths."""
    w, h, z = F.w, F.h, F.z
    r = max(1, lag // 2)
    src = list(z)
    # (a box blur, rows then columns)
    tmp = [0.0] * len(z)
    for y in range(h):
        row = y * w
        for x in range(w):
            a, b = max(0, x - r), min(w - 1, x + r)
            tmp[row + x] = sum(src[row + a:row + b + 1]) / (b - a + 1)
    blur = [0.0] * len(z)
    for x in range(w):
        for y in range(h):
            a, b = max(0, y - r), min(h - 1, y + r)
            blur[y * w + x] = sum(tmp[k * w + x] for k in range(a, b + 1)) / (b - a + 1)
    idx = [i for i in range(len(z)) if inside[i] and mask[i] and src[i] > 0]

    def at(t):
        for i in idx:
            v = src[i] + (blur[i] - src[i]) * t
            z[i] = v if v > 16 else max(16.0, min(src[i], v)) if src[i] > 16 else src[i]
        return _rms(F, inside, lag, mask)
    lo, hi = 0.0, 1.0
    for _ in range(8):
        mid = (lo + hi) / 2
        if at(mid) > target:
            lo = mid
        else:
            hi = mid
    at(hi)
    return int(round(hi * 100))


def _detail(x, y, seed):
    import landrange
    out, lam = 0.0, 4096.0
    while lam >= 512:
        out += landrange._value(x / lam, y / lam, seed + 977 + int(lam)) * (lam / 4096.0) ** 0.78
        lam /= 2
    return out


def gullies(F, inside, strength=1.0, seed=1):
    """Raindrops (a light hydraulic erosion). Returns how many drops ran."""
    if strength <= 0:
        return 0
    w, h, z = F.w, F.h, F.z
    s = F.step
    land = [i for i in range(w * h) if inside[i] and z[i] > 16]
    if not land:
        return 0
    rng = random.Random(seed * 7919 + 13)
    # (as many drops as a third of the land's points, more with strength: the same density at any spacing)
    drops = int(len(land) * 0.35 * strength)
    inertia, cap_k, dep_k, ero_k, evap, grav, steps = 0.1, 6.0, 0.25, 0.35 * strength, 0.03, 4.0, 48

    # (the height and slope lookups written out in the loop, the same sums in the same order: a third of the time
    # went on the calls, 2026-10-26)
    hypot, sqrt, rand, rrange, nland = math.hypot, math.sqrt, rng.random, rng.randrange, len(land)
    w1, h1, keep = w - 1, h - 1, 1 - inertia
    for _ in range(drops):
        i0 = land[rrange(nland)]
        x, y = (i0 % w) + rand() * 0.9, (i0 // w) + rand() * 0.9
        dx = dy = 0.0
        speed, water, sed = 1.0, 1.0, 0.0
        for _step in range(steps):
            if not (0 <= x < w1 and 0 <= y < h1):
                break
            ix, iy = int(x), int(y)
            ci = iy * w + ix
            if not inside[ci]:
                break
            fx, fy = x - ix, y - iy
            a, b, c, d = z[ci], z[ci + 1], z[ci + w], z[ci + w + 1]
            gx = ((b - a) * (1 - fy) + (d - c) * fy) / s
            gy = ((c - a) * (1 - fx) + (d - b) * fx) / s
            hz = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
            dx = dx * inertia - gx * keep
            dy = dy * inertia - gy * keep
            ln = hypot(dx, dy)
            if ln < 1e-9:
                break
            dx, dy = dx / ln, dy / ln
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w1 and 0 <= ny < h1):
                break
            jx, jy = int(nx), int(ny)
            qx, qy = nx - jx, ny - jy
            j = jy * w + jx
            nh = (z[j] * (1 - qx) + z[j + 1] * qx) * (1 - qy) + (z[j + w] * (1 - qx) + z[j + w + 1] * qx) * qy
            dh = (nh - hz) / s                          # (rise over the step, in steps: 1 is 45 degrees)
            # (what it can carry, in game units of ground: steeper, faster and wetter carries more)
            cap = max(-dh, 0.01) * speed * water * cap_k * s * 0.25
            if nh < 0:
                break                                   # (into the water: what it carries is washed away, so
                #                                         rivers, lakes and the shore keep their beds)
            # (the four points round it and their shares, written out: the same updates in the same order)
            k1, k2, k3 = ci + 1, ci + w, ci + w + 1
            w0, w1_, w2, w3 = (1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy
            if sed > cap or dh > 0:
                # (slower or uphill: drop some of what it carries, into the hollow it stands in)
                put = min(dh * s, sed) if dh > 0 else (sed - cap) * dep_k
                put = max(0.0, put)
                sed -= put
                if inside[ci]:
                    z[ci] += put * w0
                if inside[k1]:
                    z[k1] += put * w1_
                if inside[k2]:
                    z[k2] += put * w2
                if inside[k3]:
                    z[k3] += put * w3
            else:
                take = min((cap - sed) * ero_k, -dh * s * 0.5)
                # (a gully stays dry ground: no puddles cut under the water)
                if inside[ci] and z[ci] > 0:
                    z[ci] = max(8.0, z[ci] - take * w0)
                if inside[k1] and z[k1] > 0:
                    z[k1] = max(8.0, z[k1] - take * w1_)
                if inside[k2] and z[k2] > 0:
                    z[k2] = max(8.0, z[k2] - take * w2)
                if inside[k3] and z[k3] > 0:
                    z[k3] = max(8.0, z[k3] - take * w3)
                sed += take
            speed = sqrt(max(0.0, speed * speed + dh * grav))
            water *= (1 - evap)
            x, y = nx, ny
    return drops


def terraces(F, inside, step=256.0, sharp=0.6, min_slope=20.0):
    """Steps of the step height on slopes over min_slope degrees; 0 sharp: soft benches, 1: hard steps."""
    w, h, z = F.w, F.h, F.z
    if step < 32:
        return 0
    src = list(z)
    lo = math.tan(max(0.0, min_slope - 8) * DEG) * F.step
    hi = math.tan(min_slope * DEG) * F.step
    n = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            v = src[i]
            if not inside[i] or v <= 0:
                continue
            g = math.hypot(src[i + 1] - src[i - 1], src[i + w] - src[i - w]) / 2
            if g <= lo:
                continue
            k = 1.0 if g >= hi else (g - lo) / (hi - lo)
            t = v / step
            f = t - math.floor(t)
            p = 1.0 / max(0.05, 1 - sharp)              # (how much of each step is riser)
            f2 = min(1.0, max(0.0, (f - 0.5) * p + 0.5))
            f2 = f2 * f2 * (3 - 2 * f2)
            z[i] = v + ((math.floor(t) + f2) * step - v) * k
            n += 1
    return n
