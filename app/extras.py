"""The small things the game hangs from or stands against its room pieces (a rope and lantern under a
Hlaalu side piece, a sconce on an Imperial hall piece, a skirting along a Gold Coast wall, a chandelier
under a Common room centre), learned from its own interiors (variantsurvey.hangings). "Build from
pieces" adds them after the floor pieces, as often as the game does, at the game's own offsets."""
import math
import random

import variantsurvey

MAX_SHARE = 0.6            # (never on every piece: the game's own rooms aren't that regular)
SKIP = ('arch', 'jamb', 'door', 'railing', 'rail_', 'stair', 'floortiles', 'ceil', 'story', 'wall')   # (doorways, railings, ceilings and walls are built elsewhere)


def for_piece(db, style, piece_id, q, x, y, floor_z, rng, chance=1.0):
    """[(id, (x, y, z, 0, 0, rz))] to add to one placed floor piece, turned q quarter turns at (x, y)
    with its floor at floor_z. rng decides, piece by piece, with the game's own share."""
    h = variantsurvey.hangings(db, style).get(piece_id)
    if not h:
        return []
    out = []
    rz = q * math.pi / 2
    c, s = math.cos(rz), math.sin(rz)
    for oid, share, (lx, ly, dz) in h['with']:
        low = oid.lower()
        if any(w in low for w in SKIP):
            continue
        if rng.random() > min(MAX_SHARE, share) * chance:
            continue
        wx, wy = x + lx * c + ly * s, y - lx * s + ly * c
        out.append((oid, (wx, wy, floor_z + dz, 0, 0, rz)))
    return out


def seeded(key):
    return random.Random(key)
