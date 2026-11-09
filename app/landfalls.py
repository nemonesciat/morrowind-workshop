"""Waterfalls on the streams of shaped land (docs/terrain-tools-research-2026-11.md, P3), the way the game lays them
above sea level: the region pass's last step.

The game's water above sea level is meshes (lab a10, 2026-11-08: 2,904 pieces of the stream kit, four fifths of
them TR's). A fall stands where a stream drops over steep ground (median 13-25 degrees round it, 1,546 of drop within
1,024 where about half a cell drains), its +y turned uphill and its sheet pouring away from it; mist at its foot
(1.6 mist pieces a fall, about 100 from it) and a sound beside it. Most of the game's stream beds have no water in
them; where there is, it lies in flat pieces at one level (tarns, plunge pools) or rapids ribbons 256 wide along
the flow, tilted to it.

  find     on the land as written: the rain's way down at every 512 units (landwater.flow_map); a stream draining
           FALL_AREA or more, followed down at every 64 units, falls where it drops FALL_DROP or more over steep ground
           (the steepest stretch is the face: its lip where it steepens past LIP_DEG, its foot where it eases under
           FOOT_DEG), the falls kept FALL_GAP apart, the tallest first, at most FALL_CELL a cell
  pool     the plunge pool dug at the foot (a bowl under a flat pool piece, a rim of ground round it at least as high
           as the water, so no edge stands in the air)
  pieces   the fall (t_glb_terrwater_waterfall_03, its sheet 458 tall, scaled to the drop; _01, wider, for a big
           stream), the pool, two mists and the sound; rapids up and down the bed (RAPIDS, off for now)"""
import math

FALL_AREA = 128.0               # (points of the 512 grid draining through: half a cell)
BIG_AREA = 1024.0               # (... four cells: a wide fall)
FALL_DROP = 200.0
FALL_GAP = 1536.0
FALL_CELL = 0.6
LIP_DEG = 35.0
FOOT_DEG = 20.0
RAPID_DEG = 12.0                # (rapids on a bed no steeper than this)
RAPIDS = 0                      # (512-long pieces above the lip and below the pool, at most. Off: laid straight down the
                                # 512 grid's way a stream bends off, they lay across its valley side with ground through
                                # them, seen in the 3D view 2026-11-08; and TR leaves most beds dry, 50 rapids in all)
STEP = 64.0

FALL = {'id': 't_glb_terrwater_waterfall_03', 'top': 220.0, 'bottom': -238.0, 'back': -70.0, 'front': -242.0}
FALL_WIDE = {'id': 't_glb_terrwater_waterfall_01', 'top': 112.0, 'bottom': -329.0, 'back': 80.0, 'front': -88.0}
POOL = {'id': 't_glb_terrwater_circle512_01', 'r': 256.0}        # (512 across: its surface under a NiCollisionSwitch)
RAPID = {'id': 't_glb_terrwater_rectrpd256_03', 'len': 512.0, 'half': 128.0}
MIST = 'ex_waterfall_mist_01'
SOUND, SOUND_BIG = 't_glb_sound_waterfall_small', 't_glb_sound_large_waterfall'
KIT = [FALL['id'], FALL_WIDE['id'], POOL['id'], RAPID['id'], MIST, SOUND, SOUND_BIG]


def kit_ready(db):
    """Whether the load order has the pieces (Tamriel_Data's stream kit and Morrowind's mist)."""
    return all(db.resolve_id(i) is not None for i in KIT)


def _h(F, x, y):
    import cliffrocks
    return cliffrocks._height(F, x, y)


def _slope_along(F, x, y, dx, dy):
    a, b = _h(F, x - dx * 32, y - dy * 32), _h(F, x + dx * 32, y + dy * 32)
    if a is None or b is None:
        return None
    return math.degrees(math.atan(max(0.0, a - b) / 64.0))


def _index(F, x, y):
    ix, iy = int(round((x - F.ox) / F.step)), int(round((y - F.oy) / F.step))
    return iy * F.w + ix if 0 <= ix < F.w and 0 <= iy < F.h else -1


def find(F, inside, hold=None, seed=1, amount=1.0):
    """The falls on F's streams: [{x, y, lip, foot (world points with heights), dx, dy (downstream), drop, area}]."""
    import landwater
    C, A, rec = landwater.flow_map(F, inside, seed)
    w = C.w
    cand = []
    for i, r in enumerate(rec):
        if r < 0 or A[i] < FALL_AREA or not C.inside[i]:
            continue
        rr = rec[r] if rec[r] >= 0 else r
        (x0, y0), (x1, y1) = C.world(i), C.world(rr)
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1:
            continue
        dx, dy = (x1 - x0) / L, (y1 - y0) / L
        # (down the stream at every 64: the face is the stretch steeper than LIP_DEG, its foot where it eases)
        prof = []
        t = 0.0
        while t <= L:
            x, y = x0 + dx * t, y0 + dy * t
            prof.append((t, x, y, _h(F, x, y), _slope_along(F, x, y, dx, dy)))
            t += STEP
        if any(p[3] is None or p[4] is None for p in prof):
            continue
        k = max(range(len(prof)), key=lambda n: prof[n][4])
        if prof[k][4] < LIP_DEG:
            continue
        a = k
        while a > 0 and prof[a - 1][4] >= FOOT_DEG:
            a -= 1
        b = k
        while b < len(prof) - 1 and prof[b + 1][4] >= FOOT_DEG:
            b += 1
        lip, foot = prof[a], prof[min(len(prof) - 1, b + 1)]
        drop = lip[3] - foot[3]
        if drop < FALL_DROP or foot[3] <= 48:
            continue
        if hold is not None and any(0 <= j and hold[j] >= 0.5 for j in (_index(F, lip[1], lip[2]), _index(F, foot[1], foot[2]))):
            continue
        if not all(0 <= j and inside[j] for j in (_index(F, lip[1], lip[2]), _index(F, foot[1], foot[2]))):
            continue
        cand.append({'x': (lip[1] + foot[1]) / 2, 'y': (lip[2] + foot[2]) / 2, 'lip': [lip[1], lip[2], lip[3]],
                     'foot': [foot[1], foot[2], foot[3]], 'dx': dx, 'dy': dy, 'drop': drop, 'area': A[i], 'node': i})
    cand.sort(key=lambda c: -c['drop'] * math.sqrt(c['area']))
    n_cells = sum(1 for i in range(len(inside)) if inside[i]) * F.step * F.step / (8192.0 * 8192.0)
    cap = max(1, int(round(FALL_CELL * n_cells * amount)))
    out = []
    for c in cand:
        if len(out) >= cap:
            break
        if any(math.hypot(c['x'] - o['x'], c['y'] - o['y']) < FALL_GAP for o in out):
            continue
        out.append(c)
    return out, (C, A, rec)


def _dig_pool(F, cx, cy, r, level):
    """A bowl under the pool (40 deep at its middle) and a rim round it no lower than the water: no pool edge in the
    air on the downhill side."""
    for i in F.near(cx - r - 192, cy - r - 192, cx + r + 192, cy + r + 192):
        x, y = F.world(i)
        d = math.hypot(x - cx, y - cy)
        z = F.z[i]
        if d <= r:
            F.z[i] = min(z, level - 40.0 * (1 - (d / r) ** 2) - 8.0)
        elif d <= r + 192:
            t = (d - r) / 192.0
            F.z[i] = max(z, (level + 12.0) * (1 - t) + z * t) if z < level + 12.0 else z


def _bed(F, x0, y0, x1, y1, z0, z1, half):
    """A bed cut for a rapids piece: the ground along it no higher than the piece less 12, within half its width."""
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    pad = half + 64
    for i in F.near(min(x0, x1) - pad, min(y0, y1) - pad, max(x0, x1) + pad, max(y0, y1) + pad):
        x, y = F.world(i)
        t = ((x - x0) * ux + (y - y0) * uy) / L
        if not (0 <= t <= 1):
            continue
        side = abs(-(x - x0) * uy + (y - y0) * ux)
        if side > pad:
            continue
        want = z0 + (z1 - z0) * t - 12.0
        k = 1.0 if side <= half else 1.0 - (side - half) / 64.0
        if F.z[i] > want:
            F.z[i] = F.z[i] + (want - F.z[i]) * k


def lay(F, inside, falls, flow, seed=1):
    """The pieces for the falls ([{id, x, y, z, rx, ry, rz, s}], for cliffrocks.place), digging their pools and beds
    into F. Morrowind turns a piece clockwise by rz: its +y heads pi/2 - rz."""
    import random
    rng = random.Random(seed * 2903 + 5)
    C, A, rec = flow
    ups = {}
    for i, r in enumerate(rec):
        if r >= 0 and (r not in ups or A[i] > A[ups[r]]):
            ups[r] = i
    out = []
    for f in falls:
        dx, dy = f['dx'], f['dy']
        lx, ly, lz = f['lip']
        fz = f['foot'][2]
        M = FALL_WIDE if f['area'] >= BIG_AREA else FALL
        s = max(0.5, min(3.0, (lz - fz + 40.0) / (M['top'] - M['bottom'])))
        # (+y uphill: the stream comes from +y and pours away towards -y)
        rz = math.pi / 2 - math.atan2(-dy, -dx)
        # the back of the sheet (local y = back) at the lip, its top 8 over the lip
        ox, oy = lx + dx * M['back'] * s, ly + dy * M['back'] * s
        oz = lz + 8.0 - M['top'] * s
        out.append({'id': M['id'], 'x': ox, 'y': oy, 'z': oz, 'rx': 0.0, 'ry': 0.0, 'rz': rz, 's': round(s, 3)})
        # the pool where the sheet lands, its water over the sheet's foot
        land = (M['back'] - M['front']) * s
        px, py = lx + dx * (land + 96.0), ly + dy * (land + 96.0)
        g = _h(F, px, py)
        if g is None:
            continue
        level = min(g, oz + M['bottom'] * s + 24.0)
        ps = 0.7 if M is FALL else 1.0
        _dig_pool(F, px, py, POOL['r'] * ps, level)
        out.append({'id': POOL['id'], 'x': px, 'y': py, 'z': level, 'rx': 0.0, 'ry': 0.0, 'rz': rng.uniform(0, 2 * math.pi), 's': ps})
        for _ in range(2):
            a, r = rng.uniform(0, 2 * math.pi), rng.uniform(40, 120)
            out.append({'id': MIST, 'x': px + math.cos(a) * r, 'y': py + math.sin(a) * r, 'z': level + 4.0, 'rx': 0.0, 'ry': 0.0, 'rz': 0.0, 's': 1.0})
        out.append({'id': SOUND_BIG if f['drop'] >= 600 else SOUND, 'x': px, 'y': py, 'z': level + 60.0, 'rx': 0.0, 'ry': 0.0, 'rz': 0.0, 's': 1.0})
        # rapids: up the bed from the lip, and on down from the pool, where it runs gentle enough
        out += _rapids(F, inside, lx - dx * 16, ly - dy * 16, -dx, -dy, uphill=True)
        out += _rapids(F, inside, px + dx * (POOL['r'] * ps + 32), py + dy * (POOL['r'] * ps + 32), dx, dy, uphill=False)
    return out


def _rapids(F, inside, x, y, ux, uy, uphill):
    """Up to RAPIDS pieces along a straight bed from (x, y) heading (ux, uy), each where the bed is no steeper than
    RAPID_DEG, cut into it. The piece runs along its y, the water flowing towards +y, tilted to the bed (rx)."""
    out = []
    for _ in range(RAPIDS):
        x1, y1 = x + ux * RAPID['len'], y + uy * RAPID['len']
        a, b = _h(F, x, y), _h(F, x1, y1)
        j = _index(F, x1, y1)
        if a is None or b is None or j < 0 or not inside[j] or min(a, b) <= 48:
            break
        hi, lo = (a, b) if uphill is False else (b, a)
        drop = (a - b) if not uphill else (b - a)
        if drop < -16 or math.degrees(math.atan(max(0.0, drop) / RAPID['len'])) > RAPID_DEG:
            break
        # (the bed: a straight cut from one end to the other, the piece 4 over it at its middle)
        za, zb = min(a, (a + b) / 2 + 24), min(b, (a + b) / 2 + 24)
        _bed(F, x, y, x1, y1, za + 4, zb + 4, RAPID['half'])
        # downstream: flowing from the higher end to the lower
        if uphill:
            fx, fy, tz = -ux, -uy, (zb - za)
        else:
            fx, fy, tz = ux, uy, (zb - za)
        rz = math.pi / 2 - math.atan2(fy, fx)
        # (tilted so its downstream end is the lower: a positive rx raises the +y end in the game, seen in the 3D
        # view 2026-11-08, so the drop over its length goes in negative)
        rx = -math.atan2((za - zb) if not uphill else (zb - za), RAPID['len'])
        out.append({'id': RAPID['id'], 'x': (x + x1) / 2, 'y': (y + y1) / 2, 'z': (za + zb) / 2 + 4.0,
                    'rx': round(rx, 4), 'ry': 0.0, 'rz': rz, 's': 1.0})
        x, y = x1, y1
    return out


def wet_mask(F, pieces):
    """A bytearray over F: the ground round the falls, pools and rapids (nothing else is set there: no cliff piece in
    front of a fall, no plant in a pool)."""
    out = bytearray(F.w * F.h)
    for pc in pieces:
        i = pc['id']
        r = 340.0 if i in (FALL['id'], FALL_WIDE['id']) else 420.0 if i == POOL['id'] else 320.0 if i == RAPID['id'] else 0.0
        if not r:
            continue
        for j in F.near(pc['x'] - r, pc['y'] - r, pc['x'] + r, pc['y'] + r):
            x, y = F.world(j)
            if (x - pc['x']) ** 2 + (y - pc['y']) ** 2 <= r * r:
                out[j] = 1
    return out
