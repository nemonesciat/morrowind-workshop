"""Sky art the game doesn't have, made for your own weathers (Create > Weather, and the examples): an aurora's glowing
curtains high round the player, a storm's violet sparks. OpenMW draws a weather's "particles" model round the player,
so a model of long glowing ribbons stands in the sky wherever they go. Written beside the mod, in meshes\\wslib and
textures\\wslib, with nothing but the standard library (the textures are PNGs, which OpenMW reads).
The user (2026-11-02): "some that create aurora, or other kinds of mystical weathers you can see in Skyrim or elsewhere"."""
import math
import os
import random
import struct
import zlib

import library
import nifwrite


def _png(w, h, px):
    """PNG bytes of an RGBA picture: px(x, y) -> (r, g, b, a) 0..255, y from the top."""
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            rows.extend(max(0, min(255, int(c))) for c in px(x, y))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))


def _write(db, rel, data):
    full = os.path.join(library.data_dir(db), *rel.split('/'))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as f:
        f.write(data)
    library._register(db, rel, full)
    return full


def _aurora_texture(colours):
    """Curtain light: bright at its lower edge, fading upward through the second colour, in streaks that tile."""
    (r0, g0, b0), (r1, g1, b1) = colours
    W, H = 256, 128

    def px(x, y):
        v = 1.0 - y / (H - 1.0)                  # 0 at the bottom of the curtain, 1 at its top
        edge = min(1.0, v / 0.06)
        a = edge * math.exp(-2.6 * v)
        u = x / float(W) * 2 * math.pi
        streak = 0.55 + 0.25 * math.sin(3 * u) + 0.15 * math.sin(11 * u + 1.3) + 0.08 * math.sin(29 * u + 0.4)
        a *= max(0.0, min(1.0, streak))
        t = min(1.0, v * 1.8)
        return (r0 + (r1 - r0) * t, g0 + (g1 - g0) * t, b0 + (b1 - b0) * t, 255 * a)
    return _png(W, H, px)


def _aurora_model(tex, glow, seed=7):
    """Five long, folded curtains round the player, 3,000-5,000 up, 6,000-9,000 out; both sides drawn, nothing to
    bump into, glowing (lit from within, as at night)."""
    rng = random.Random(seed)
    parts = []
    for n in range(5):
        a0 = rng.uniform(0, 2 * math.pi)
        span = rng.uniform(1.0, 1.9)
        R, z0, hgt = rng.uniform(6000, 9000), rng.uniform(3000, 4200), rng.uniform(1800, 3000)
        ph1, ph2 = rng.uniform(0, 6.3), rng.uniform(0, 6.3)
        seg = 56
        verts, uvs, tris = [], [], []
        for i in range(seg + 1):
            t = i / float(seg)
            ang = a0 + span * t
            r = R + 650 * math.sin(3.2 * t * 2 * math.pi + ph1) + 260 * math.sin(7.7 * t * 2 * math.pi + ph2)
            lift = 350 * math.sin(t * math.pi)                 # (the ends sag a little)
            x, y = r * math.cos(ang), r * math.sin(ang)
            verts += [(x, y, z0 + lift), (x * 1.04, y * 1.04, z0 + lift + hgt)]
            uvs += [(t * 3.0, 1.0), (t * 3.0, 0.0)]
            if i:
                b = 2 * i
                tris += [(b - 2, b - 1, b), (b - 1, b + 1, b)]
        parts.append({'name': 'Aurora %d' % n, 'verts': verts, 'uvs': uvs, 'tris': tris, 'texture': tex,
                      'alpha': True, 'double': True, 'glow': glow, 'color': (1.0, 1.0, 1.0)})
    return nifwrite.write_nif(parts, 'Aurora', collision='none')


AURORAS = {'green': ((70, 255, 150), (150, 70, 255)), 'red': ((255, 70, 90), (255, 160, 60)), 'blue': ((80, 170, 255), (190, 90, 255))}


def make_aurora(db, kind='green'):
    """The aurora's model and texture beside the mod. Returns the model as a weather names it (meshes\\...)."""
    cols = AURORAS.get(kind) or AURORAS['green']
    name = 'ws_aurora_%s' % kind
    _write(db, 'textures/%s/%s.png' % (library.SUB, name), _aurora_texture(cols))
    glow = tuple(c / 255.0 for c in cols[0])
    _write(db, 'meshes/%s/%s.nif' % (library.SUB, name), _aurora_model('%s\\%s.png' % (library.SUB, name), glow))
    return 'meshes\\%s\\%s.nif' % (library.SUB, name)


def _spark_texture(rgb):
    W = 32

    def px(x, y):
        d = math.hypot(x - 15.5, y - 15.5) / 15.5
        a = max(0.0, 1.0 - d) ** 2.2
        core = max(0.0, 1.0 - d * 3)
        return (rgb[0] + (255 - rgb[0]) * core, rgb[1] + (255 - rgb[1]) * core, rgb[2] + (255 - rgb[2]) * core, 255 * a)
    return _png(W, W, px)


def make_sparks(db, rgb=(190, 90, 255), like='meshes/snow.nif', name='ws_arcane_sparks'):
    """The game's snow (or another weather's particles) falling as glowing sparks: its model copied with every
    texture swapped for a soft spark. Returns the model as a weather names it."""
    raw = db.meshes.read(like)
    if not raw:
        raise ValueError('The game\'s %s is not in your load order.' % like)
    _write(db, 'textures/%s/%s.png' % (library.SUB, name), _spark_texture(rgb))
    mapping = {t.lower().replace('/', '\\'): '%s\\%s.png' % (library.SUB, name) for t in nifwrite.textures_in(raw)}
    new, n = nifwrite.retexture(raw, mapping)
    if not n:
        raise ValueError('%s has no texture to swap.' % like)
    _write(db, 'meshes/%s/%s.nif' % (library.SUB, name), new)
    return 'meshes\\%s\\%s.nif' % (library.SUB, name)
