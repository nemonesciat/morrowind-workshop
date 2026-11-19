"""Small changes to a model's particle effects without Blender (particles from Blender, stage 4): the sliders in
Model & textures. Each change is made to the model's own blocks, in place (partnif reads and writes them whole), so
everything not changed stays as it was, byte for byte:

- how many a second, how long they live, how fast they leave, how big they are, how hard they are pulled: factors;
- a colour: each colour over life keeps its brightness in the colour picked, and the texture becomes a grey copy
  of itself, so an orange flame can turn blue (a texture's own colour would otherwise tint what is picked).

A block another effect shares is not changed under it: colours get new data, a grey texture a new property."""
import math

import partnif

MAX_AT_ONCE = 1500


def lum(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def recolour(key, colour):
    """A colour key (t, r, g, b, a) in the colour picked, as bright as it was."""
    m = max(colour) or 1.0
    L = lum(*key[1:4])
    return (key[0],) + tuple(min(1.0, L * c / m) for c in colour) + (key[4],)


def _resize(B, ci, n):
    """The controller's particles, and its particle data, to n."""
    c = B[ci][1]
    old = c['nparts']
    if n <= old:
        return
    c['parts'] = list(c['parts']) + [{'p': (0.0,) * 9 + (0, i)} for i in range(old, n)]
    c['nparts'] = n
    d = B[B[c['target']][1]['data']][1]
    nv = d['nv']
    if nv >= n:
        return
    grow = n - nv
    d['nv'] = n
    if d.get('hasv'):
        d['verts'] = tuple(d['verts']) + tuple(d['center']) * grow
    if d.get('hasn'):
        d['norms'] = tuple(d['norms']) + (0.0, 0.0, 1.0) * grow
    if d.get('hasc'):
        d['colors'] = tuple(d['colors']) + (1.0, 1.0, 1.0, 1.0) * grow
    if d.get('hasuv'):
        d['uv'] = tuple(d['uv']) + (0.0, 0.0) * grow * d['nuv']
    d['nparts'] = n
    if d.get('hassizes'):
        d['sizes'] = tuple(d['sizes']) + (d['pradius'],) * grow
    if d.get('hasrot'):
        d['rots'] = tuple(d['rots']) + (1.0, 0.0, 0.0, 0.0) * grow


def _chain(B, c):
    out, m, seen = [], c['modifier'], set()
    while 0 <= m < len(B) and m not in seen:
        seen.add(m)
        out.append(m)
        m = B[m][1].get('next', -1)
    return out


def _number(x, lo=0.05, hi=20.0):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 1.0
    return max(lo, min(hi, x)) if math.isfinite(x) else 1.0


def apply(data, edits, grey_texture=None):
    """The model's bytes with its effects changed. edits: [{'n': effect number (partnif.effects' order) or -1 for
    all, 'rate', 'life', 'speed', 'size', 'pull': factors, 'colour': [r, g, b] 0..1 or None}]. grey_texture(name)
    gives the name of a grey copy of a texture (or None to leave it). Returns (bytes, what changed)."""
    f = partnif.read(data)
    B = f['blocks']
    fx = partnif.effects(data)
    said = []
    for ed in edits or []:
        n = ed.get('n', -1)
        which = range(len(fx)) if n is None or int(n) < 0 else [int(n)] if 0 <= int(n) < len(fx) else []
        rate, life, speed, size, pull = (_number(ed.get(k, 1.0)) for k in ('rate', 'life', 'speed', 'size', 'pull'))
        colour = ed.get('colour')
        for i in which:
            e = fx[i]
            ci = e['ctrl_i']
            c = B[ci][1]
            if speed != 1.0:
                c['speed'] *= speed
                c['speed_random'] *= speed
            if size != 1.0:
                c['size'] *= size
                d = B[B[c['target']][1]['data']][1]
                d['pradius'] *= size
                if d.get('hassizes'):
                    d['sizes'] = tuple(x * size for x in d['sizes'])
            if rate != 1.0 or life != 1.0:
                # (as many a second as asked, set outright: the game's "keep it full" rate would change with the life)
                per_second = e['per_second'] * rate
                c['life'] *= life
                c['life_random'] *= life
                c['emit_flags'] |= 1
                c['rate'] = per_second
                _resize(B, ci, min(MAX_AT_ONCE, int(math.ceil(per_second * (c['life'] + c['life_random']))) + 2))
            if pull != 1.0:
                for m in _chain(B, c):
                    if B[m][0] == b'NiGravity':
                        B[m][1]['force'] *= pull
            if colour:
                col = tuple(max(0.0, min(1.0, float(x))) for x in colour[:3])
                mods = _chain(B, c)
                cm = next((m for m in mods if B[m][0] == b'NiParticleColorModifier'), None)
                if cm is not None and 0 <= B[cm][1]['data'] < len(B) and B[B[cm][1]['data']][0] == b'NiColorData':
                    old = B[B[cm][1]['data']][1]['keys']
                    keys = [list(k['k']) for k in old.get('keys', [])]
                    kind = old.get('kind', 1)
                    # (the key's value only: tangents of a curved key are dropped, as a straight line between keys)
                    new = [recolour(k[:5], col) for k in keys]
                else:
                    a = c['color'][3]
                    new = [recolour((0.0,) + tuple(c['color'][:3]) + (a,), col), recolour((1.0,) + tuple(c['color'][:3]) + (a,), col)]
                    kind = 1
                B.append((b'NiColorData', {'keys': {'n': len(new), 'kind': 1, 'keys': [{'k': tuple(k)} for k in new]}}))
                if cm is not None:
                    # (a new modifier too, should another effect share this one)
                    B.append((b'NiParticleColorModifier', dict(B[cm][1], data=len(B) - 1)))
                    _relink(B, c, cm, len(B) - 1)
                else:
                    B.append((b'NiParticleColorModifier', {'next': c['modifier'], 'ctrl': ci, 'data': len(B) - 1}))
                    c['modifier'] = len(B) - 1
                c['color'] = tuple(new[0][1:5])
                if grey_texture:
                    _grey(B, e, grey_texture)
                _colours_shown(B, e)
            said.append(i)
    return partnif.write(f), sorted(set(said))


def _relink(B, c, old, new):
    """The controller's chain with block old replaced by new (new keeps old's next)."""
    if c['modifier'] == old:
        c['modifier'] = new
        return
    for m in _chain(B, c):
        if B[m][1].get('next') == old:
            B[m][1]['next'] = new
            return


def _colours_shown(B, e):
    """Colours over life drawn: many of the game's particles hold a vertex colour property that ignores them (vertex
    mode 0), so the game drew none (seen 2026-11-18: a torch's flame turned blue came out grey). The particles get one
    of their own that takes them, lit as before."""
    # (and a glow of the material's own, emissive, washes any colour white: then the colours are made the glow, as a
    # glow from Blender is written. Seen 2026-11-18: the torch's flame, emissive 1, turned blue came out white)
    vc = e.get('vc')
    glows = sum(e.get('emissive') or (0, 0, 0)) > 0.05
    if glows:
        mode = (vc[0] if vc else 0, 1, 0)
    elif vc and vc[1] == 0:
        mode = (vc[0], 2, vc[2])
    else:
        return
    shape = B[e['ctrl_i']][1]['target']
    B.append((b'NiVertexColorProperty', {'name': b'', 'extra': -1, 'ctrl': -1, 'flags': mode[0], 'vmode': mode[1], 'lmode': mode[2]}))
    sp = B[shape][1]
    props = [p for p in sp['props'] if not (0 <= p < len(B) and B[p][0] == b'NiVertexColorProperty')]
    sp['props'] = tuple([len(B) - 1] + props)
    sp['nprops'] = len(sp['props'])


def _grey(B, e, grey_texture):
    """The particles' texture as a grey copy of itself, on a texturing property of the particles' own."""
    shape = B[e['ctrl_i']][1]['target']
    tp_i = next((p for p in e['props_of'] if 0 <= p < len(B) and B[p][0] == b'NiTexturingProperty'), None)
    if tp_i is None or not B[tp_i][1].get('has_base'):
        return
    tp = B[tp_i][1]
    src = tp['base'][0]
    if not (0 <= src < len(B) and B[src][0] == b'NiSourceTexture' and B[src][1].get('external')):
        return
    grey = grey_texture(B[src][1]['file'].decode('cp1252', 'replace'))
    if not grey:
        return
    B.append((b'NiSourceTexture', dict(B[src][1], file=grey.encode('cp1252', 'replace'))))
    B.append((b'NiTexturingProperty', dict(tp, base=(len(B) - 1,) + tuple(tp['base'][1:]))))
    sp = B[shape][1]
    props = [p for p in sp['props'] if not (0 <= p < len(B) and B[p][0] == b'NiTexturingProperty')]
    sp['props'] = tuple([len(B) - 1] + props)
    sp['nprops'] = len(sp['props'])
