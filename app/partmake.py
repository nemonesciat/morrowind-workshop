"""Particle effects made into the game's own kind of particle model (stage 2 of particles from Blender).

Each system (blendread.particles: Blender's space, metres) becomes what the game's own models hold, laid out
as they are: an emitter node where it emits from, and under the root a NiBSParticleNode holding NiRotatingParticles
with its NiParticleSystemController, modifiers (a pull, the colours over life, grow and fade), texture, blend and
material. Written through partnif, so what is written is what partnif reads back. Flags and the fixed fields are
the game's most common ones (counted over its 272 particle models)."""
import math

import partnif

MAX_AT_ONCE = 1500            # particles alive in one system at most
ADD, MIX = 13, 237            # NiAlphaProperty: src alpha + one (glow), src alpha + one minus src alpha
GRAVITY_MAGIC = 1.6           # OpenMW pulls particles 1.6 times a NiGravity's force


def _id3():
    return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _av(name, flags, trans=(0.0, 0.0, 0.0), rot=None, props=(), extra=-1, ctrl=-1):
    return {'name': name.encode('cp1252', 'replace')[:64], 'extra': extra, 'ctrl': ctrl, 'flags': flags,
            'trans': tuple(float(x) for x in trans), 'rot': tuple(float(x) for x in (rot or _id3())), 'scale': 1.0,
            'vel': (0.0, 0.0, 0.0), 'nprops': len(props), 'props': tuple(props), 'hasbb': 0}


def _node(name, flags, kids=(), **kw):
    d = _av(name, flags, **kw)
    d.update({'nkids': len(kids), 'kids': tuple(kids), 'neffects': 0, 'effects': ()})
    return d


def root(name):
    """A file holding only a root node, for an effect with no model of its own."""
    return {'blocks': [(b'NiNode', _node(name, 10))], 'roots': (0,)}


def _keep(n):
    return max(4, min(MAX_AT_ONCE, int(n)))


def plan(s, k):
    """The game's numbers for one system, scaled to game units (k a metre): what is written, and said."""
    life, life_r = max(0.02, s['life']), max(0.0, s['life_random'])
    rate = max(0.01, s['rate'])
    want = math.ceil(rate * (life + life_r)) + 2
    n = _keep(want)
    capped = want > n
    if capped:
        rate = n / (life + life_r / 2)
    a = s['accel']
    al = math.sqrt(sum(x * x for x in a))
    return {'n': n, 'rate': rate, 'capped': capped, 'life': life, 'life_random': life_r,
            'speed': s['speed'] * k, 'speed_random': s['speed_random'] * k, 'size': max(0.01, s['size'] * k),
            'box': [b * k for b in s['box']], 'force': al * k / GRAVITY_MAGIC, 'dir': [x / al for x in a] if al > 1e-6 else None}


# What a system is written from: the game's own numbers, in game units and the model's own frame (the particle node
# sits at the root, unturned). Made from Blender's values (spec), or kept as the game had them, group by group: a group
# left as it was in Blender keeps the game's exact numbers (stage 3, the round trip).
GROUPS = {
    'time': ('flags', 'freq', 'phase', 'start', 'stop', 'emit_start', 'emit_stop', 'rate', 'life', 'life_random',
             'emit_flags', 'nparts'),
    'motion': ('speed', 'speed_random', 'v_dir', 'v_angle', 'h_dir', 'h_angle'),
    'place': ('at', 'R', 'box'),
    'size': ('size',),
    'pull': ('gravity',),
    'colors': ('colors', 'color'),
    'picture': ('texture',),
    'blend': ('alpha_flags', 'alpha_threshold', 'emissive', 'diffuse', 'alpha', 'vc', 'zwrite'),
    'always': ('grow', 'fade', 'spin'),          # (Blender has no place for these: the game's are always kept)
}


def spec(s, k, shift, texture):
    """The game's numbers for a system read from Blender (blendread.particles), then its s['keep'] over them."""
    p = plan(s, k)
    keys = s['colors'] or [(0.0,) + tuple(s['color']), (1.0,) + tuple(s['color'])]
    at = tuple((s['at'][i] - shift[i]) * k for i in range(3))
    out = {'flags': 8, 'freq': 1.0, 'phase': 0.0, 'start': 0.0, 'stop': float(s['duration']), 'emit_start': 0.0,
           'emit_stop': float(s['duration']), 'rate': p['rate'], 'life': p['life'], 'life_random': p['life_random'],
           'emit_flags': 1, 'nparts': p['n'],
           'speed': p['speed'], 'speed_random': p['speed_random'], 'v_dir': s['v_dir'], 'v_angle': s['v_angle'],
           'h_dir': s['h_dir'], 'h_angle': s['h_angle'],
           'at': at, 'R': s['R'], 'box': tuple(p['box']), 'size': p['size'],
           'gravity': [{'type': 0, 'force': p['force'], 'decay': 0.0, 'pos': at, 'dir': tuple(p['dir'])}] if p['dir'] else [],
           'colors': [tuple(float(x) for x in kk[:5]) for kk in keys], 'color': tuple(float(x) for x in keys[0][1:5]),
           'texture': texture or '',
           'alpha_flags': ADD if s['glow'] else MIX, 'alpha_threshold': 0, 'emissive': (0.0, 0.0, 0.0),
           'diffuse': (1.0, 1.0, 1.0), 'alpha': 1.0, 'vc': (0, 1, 0) if s['glow'] else None, 'zwrite': False,
           'grow': float(s.get('grow') or 0.0), 'fade': float(s.get('fade') or 0.0), 'spin': None}
    for group, vals in (s.get('keep') or {}).items():
        for name in GROUPS.get(group, ()):
            if name in vals:
                out[name] = vals[name]
    # (colours changed in Blender are to be seen: a game model's "ignore vertex colours" would hide them, and its
    # material's own glow wash them white; then the colours are made the glow, as fxedit does)
    if 'colors' not in (s.get('keep') or {'colors': 1}):
        if sum(out['emissive']) > 0.05:
            out['vc'] = (out['vc'][0] if out['vc'] else 0, 1, 0)
        elif out['vc'] and out['vc'][1] == 0:
            out['vc'] = None
    if out['nparts'] > MAX_AT_ONCE and not (s.get('keep') or {}).get('time'):
        out['nparts'] = MAX_AT_ONCE
    return out


def add(f, s, k, shift, texture):
    """Add one system to a partnif file dict, under its root. k: game units a metre; shift: the (x, y, z) taken
    off Blender's positions before scaling (the model's own recentring); texture: its path for the game
    ('wslib\\x.png') or ''. Returns the plan written."""
    return write_spec(f, spec(s, k, shift, texture), s.get('object') or s.get('name') or 'Particles', plan(s, k))


def write_spec(f, w, nm, p=None):
    """Write one system from its game numbers (spec) under the file's root, laid out as the game's own models are."""
    B = f['blocks']
    top = B[f['roots'][0]][1]
    at, R = tuple(float(x) for x in w['at']), w['R']
    rot = tuple(float(R[r][c]) for r in range(3) for c in range(3))
    base = len(B)
    i_em, i_pnode, i_zbuf, i_parts, i_ctrl = base, base + 1, base + 2, base + 3, base + 4
    mods = []
    nxt = base + 5
    for g in w['gravity']:
        mods.append(('grav', nxt, g)); nxt += 1
    if w['spin']:
        mods.append(('spin', nxt, w['spin'])); nxt += 1
    i_cdata = -1
    if w['colors']:                              # (a game model without colours over life has no colour modifier)
        mods.append(('color', nxt, None)); nxt += 1
    mods.append(('growfade', nxt, None)); nxt += 1
    if w['colors']:
        i_cdata = nxt; nxt += 1
    i_tex = i_src = -1
    if w['texture']:
        i_tex, i_src = nxt, nxt + 1
        nxt += 2
    i_alpha = nxt if w['alpha_flags'] is not None else -1
    nxt += 1 if i_alpha >= 0 else 0
    i_mat, i_data = nxt, nxt + 1
    # (a glow, Emission in Blender: the particles' own colours are their light, lamp or no lamp. The game lights
    # particles like anything else; seen in it 2026-11-18, sparks were dim dots in a dim hall, and a white emissive
    # instead turned a flame white: vertex colours as emissive keep its colours over life)
    i_vc = i_data + 1 if w['vc'] else -1
    B.append((b'NiNode', _node(nm + ' Emitter', 2, trans=at, rot=rot)))
    B.append((b'NiBSParticleNode', _node(nm, 170, kids=(i_parts,), props=(i_zbuf,))))
    B.append((b'NiZBufferProperty', {'name': b'', 'extra': -1, 'ctrl': -1, 'flags': 3 if w['zwrite'] else 1}))
    props = tuple(x for x in (i_tex, i_alpha, i_mat, i_vc) if x >= 0)
    g = _av(nm, 2, props=props, ctrl=i_ctrl)
    g.update({'data': i_data, 'skin': -1})
    B.append((b'NiRotatingParticles', g))
    n = int(w['nparts'])
    size = float(w['size'])
    B.append((b'NiParticleSystemController', {
        'next': -1, 'flags': int(w['flags']), 'freq': float(w['freq']), 'phase': float(w['phase']), 'start': float(w['start']),
        'stop': float(w['stop']), 'target': i_parts,
        'speed': float(w['speed']), 'speed_random': float(w['speed_random']), 'v_dir': float(w['v_dir']),
        'v_angle': float(w['v_angle']), 'h_dir': float(w['h_dir']), 'h_angle': float(w['h_angle']), 'normal': (1.0, 0.0, 0.0),
        'color': tuple(float(x) for x in w['color']), 'size': size, 'emit_start': float(w['emit_start']),
        'emit_stop': float(w['emit_stop']), 'unknown_byte': 0, 'rate': float(w['rate']), 'life': float(w['life']),
        'life_random': float(w['life_random']), 'emit_flags': int(w['emit_flags']), 'box': tuple(float(x) for x in w['box']),
        'emitter': i_em, 'unknown': (0, 1.0, 1, 0, 0), 'nparts': n, 'nvalid': 0,
        'parts': [{'p': (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, i)} for i in range(n)],
        'link': -1, 'modifier': mods[0][1], 'link2': -1, 'trailer': 0}))
    for j, (kind, idx, v) in enumerate(mods):
        after = mods[j + 1][1] if j + 1 < len(mods) else -1
        if kind == 'grav':
            B.append((b'NiGravity', {'next': after, 'ctrl': i_ctrl, 'decay': float(v['decay']), 'force': float(v['force']),
                                     'type': int(v['type']), 'pos': tuple(float(x) for x in v['pos']),
                                     'dir': tuple(float(x) for x in v['dir'])}))
        elif kind == 'spin':
            B.append((b'NiParticleRotation', {'next': after, 'ctrl': i_ctrl, 'random_axis': int(bool(v['random'])),
                                              'axis': tuple(float(x) for x in v['axis']), 'speed': float(v['speed'])}))
        elif kind == 'color':
            B.append((b'NiParticleColorModifier', {'next': after, 'ctrl': i_ctrl, 'data': i_cdata}))
        else:
            B.append((b'NiParticleGrowFade', {'next': after, 'ctrl': i_ctrl, 'grow': float(w['grow']), 'fade': float(w['fade'])}))
    if w['colors']:
        B.append((b'NiColorData', {'keys': {'n': len(w['colors']), 'kind': 1,
                                            'keys': [{'k': tuple(float(x) for x in kk[:5])} for kk in w['colors']]}}))
    if w['texture']:
        B.append((b'NiTexturingProperty', {'name': b'', 'extra': -1, 'ctrl': -1, 'flags': 0, 'apply': 2, 'count': 7,
                                           'has_base': 1, 'base': (i_src, 3, 2, 0, 0, -75, 0), 'has_dark': 0,
                                           'has_detail': 0, 'has_gloss': 0, 'has_glow': 0, 'has_bump': 0, 'has_decal0': 0}))
        B.append((b'NiSourceTexture', {'name': b'', 'extra': -1, 'ctrl': -1, 'external': 1,
                                       'file': w['texture'].encode('cp1252', 'replace'), 'format': (5, 1, 3, 1)}))
    if i_alpha >= 0:
        B.append((b'NiAlphaProperty', {'name': b'', 'extra': -1, 'ctrl': -1, 'flags': int(w['alpha_flags']),
                                       'threshold': int(w['alpha_threshold'])}))
    B.append((b'NiMaterialProperty', {'name': b'', 'extra': -1, 'ctrl': -1, 'flags': 1, 'ambient': (1.0, 1.0, 1.0),
                                      'diffuse': tuple(float(x) for x in w['diffuse']), 'specular': (0.0, 0.0, 0.0),
                                      'emissive': tuple(float(x) for x in w['emissive']), 'gloss': 0.0, 'alpha': float(w['alpha'])}))
    life = float(w['life']) + float(w['life_random'])
    force = sum(abs(float(g_['force'])) for g_ in w['gravity'])
    reach = max(w['box']) / 2 + (abs(float(w['speed'])) + abs(float(w['speed_random']))) * life + \
        0.5 * force * GRAVITY_MAGIC * life ** 2
    B.append((b'NiRotatingParticlesData', {
        'nv': n, 'hasv': 1, 'verts': at * n, 'hasn': 0, 'center': at, 'radius': float(min(1e5, reach + size)),
        'hasc': 1, 'colors': (1.0, 1.0, 1.0, 1.0) * n, 'nuv': 0, 'hasuv': 0, 'nparts': n, 'pradius': size,
        'nactive': 0, 'hassizes': 1, 'sizes': (size,) * n, 'hasrot': 1, 'rots': (1.0, 0.0, 0.0, 0.0) * n}))
    if i_vc >= 0:
        vf, vm, vl = w['vc']
        B.append((b'NiVertexColorProperty', {'name': b'', 'extra': -1, 'ctrl': -1, 'flags': int(vf), 'vmode': int(vm), 'lmode': int(vl)}))
    assert len(B) == max(i_data, i_vc) + 1
    top['kids'] = tuple(top['kids']) + (i_em, i_pnode)
    top['nkids'] = len(top['kids'])
    return p


# ----- the way out: a game emitter as Blender's classic particle settings (assets.export_glb, BLENDER_SCRIPT) -----
def _mv(R, v):
    return [sum(R[i][j] * v[j] for j in range(3)) for i in range(3)]


def _linear(c):
    c = max(0.0, min(1.0, float(c)))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def game_spec(e):
    """A game emitter (partnif.effects) as its exact numbers in the model's own frame: what write_spec writes, and
    what is kept of it through Blender."""
    pR, pt, ps = e['pR'], e['pt'], e.get('ps', 1.0) or 1.0
    grav = []
    for g in e['gravity']:
        d = _mv(pR, g['dir'])
        pos = _mv(pR, [x * ps for x in g['pos']])
        grav.append({'type': g['type'], 'force': g['force'] * ps, 'decay': g['decay'], 'dir': tuple(d),
                     'pos': tuple(pos[i] + pt[i] for i in range(3))})
    spin = e.get('spin')
    return {'flags': e['flags'], 'freq': e['freq'], 'phase': e['phase'], 'start': e['start'], 'stop': e['stop'],
            'emit_start': e['emit_start'], 'emit_stop': e['emit_stop'], 'rate': e['rate'], 'life': e['life'],
            'life_random': e['life_random'], 'emit_flags': e['emit_flags'], 'nparts': e['nparts'],
            'speed': e['speed'] * ps, 'speed_random': e['speed_random'] * ps, 'v_dir': e['v_dir'], 'v_angle': e['v_angle'],
            'h_dir': e['h_dir'], 'h_angle': e['h_angle'],
            'at': tuple(e['at']), 'R': [list(r) for r in e['R']], 'box': tuple(b * (e.get('s') or 1.0) for b in e['box']),
            'size': e['size'] * ps, 'gravity': grav,
            'colors': [tuple(c) for c in e['colors']], 'color': tuple(e['color']), 'texture': e.get('tex_game', ''),
            'alpha_flags': e.get('alpha_flags'), 'alpha_threshold': e.get('alpha_threshold', 0), 'emissive': tuple(e['emissive']),
            'diffuse': tuple(e['diffuse']), 'alpha': e['alpha'], 'vc': tuple(e['vc']) if e.get('vc') else None,
            'zwrite': e.get('zwrite', False), 'grow': e['grow'], 'fade': e['fade'],
            'spin': {'random': spin['random'], 'axis': tuple(spin['axis']), 'speed': spin['speed']} if spin else None}


def to_blender(e, k, fps=24.0):
    """A game emitter as the settings a Blender script sets on a classic particle system (metres, Blender's axes =
    the game's, as the .glb export has them): the emitter object, count and frames, push and spread, size, a wind
    of its own for its pulls, and the look (colour ramp, picture, glow)."""
    w = game_spec(e)
    v, h = w['v_dir'], w['h_dir']
    d = (math.cos(h) * math.sin(v), math.sin(h) * math.sin(v), math.cos(v))
    sp = w['speed'] / k
    # (Blender pushes along the object's own axes; the spread comes from its random speed, which blendread reads
    # back as atan(0.6 x random / speed). A cone wider than about 80 degrees is only kept as the game had it)
    rnd = max(w['speed_random'] / k, math.tan(min(w['v_angle'], 1.4)) * abs(sp) / 0.6)
    life = max(0.02, w['life'] + w['life_random'])
    span = w['emit_stop'] - w['emit_start']
    if span <= 0:
        span = (w['stop'] - w['start']) or 1.0
    span = max(1.0 / fps, min(600.0, span))
    per_second = e.get('per_second') or w['rate']
    pull = [0.0, 0.0, 0.0]
    for g in w['gravity']:
        if g['type'] == 0:
            for i in range(3):
                pull[i] += g['dir'][i] * g['force'] * GRAVITY_MAGIC / k
    strength = math.sqrt(sum(x * x for x in pull))
    blend_add = w['alpha_flags'] is not None and bool(w['alpha_flags'] & 1) and not (w['alpha_flags'] >> 5) & 15
    return {'name': e.get('name') or 'Particles',
            'at': [x / k for x in w['at']], 'R': w['R'], 'box': [b / k for b in w['box']],
            'count': max(1, int(round(per_second * span))), 'frame_start': 1.0, 'frame_end': 1.0 + span * fps,
            'lifetime': life * fps, 'lifetime_random': max(0.0, min(1.0, w['life_random'] / life)),
            'object_align': [x * sp for x in d], 'factor_random': rnd, 'size': max(1e-4, w['size'] / k),
            'wind': {'dir': [x / strength for x in pull], 'strength': strength} if strength > 1e-6 else None,
            'ramp': [[c[0], _linear(c[1]), _linear(c[2]), _linear(c[3]), max(0.0, min(1.0, c[4]))] for c in w['colors']],
            'color': [_linear(w['color'][0]), _linear(w['color'][1]), _linear(w['color'][2]), w['color'][3]],
            'glow': blend_add or bool(w['vc'] and w['vc'][1] == 1), 'game': w}


def say(s, p):
    """One system in a few plain words, with what the game could not take."""
    words = ['about %g a second' % round(p['rate'], 1 if p['rate'] < 10 else 0), 'live %g s' % round(p['life'] + p['life_random'] / 2, 2)]
    if p['capped']:
        words.append('kept to %d at once' % p['n'])
    if s['glow']:
        words.append('glowing')
    if s['colors']:
        words.append('changing colour')
    return ', '.join(words)


# ----- the way back: which groups were left as they were in Blender --------------------------------------------
# (each group of Blender's values, as blendread.particles reads them, against the file as it was first built)
SAME_BY = {'time': ('rate', 'duration', 'life', 'life_random'),
           'motion': ('speed', 'speed_random', 'v_dir', 'v_angle', 'h_dir', 'h_angle'),
           'place': ('at', 'R', 'box'), 'size': ('size',), 'pull': ('accel',), 'colors': ('colors', 'color'),
           'picture': ('picture_key',), 'blend': ('glow',)}


def _close(a, b):
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        return isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b) and \
            all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-5 * max(1.0, abs(a), abs(b))
    return a == b


def unchanged(s, s0, game):
    """The game's numbers to keep for a system come back from Blender: every group whose Blender values are as they
    were when it was sent (s0), and what Blender has no place for. {'group': {name: value}}; changed() says which
    were changed."""
    keep = {'always': {k: game[k] for k in GROUPS['always']}}
    for group, names in SAME_BY.items():
        if all(_close(s.get(n), s0.get(n)) for n in names):
            keep[group] = {k: game[k] for k in GROUPS[group]}
    return keep


def changed(keep):
    return [g for g in SAME_BY if g not in keep]
