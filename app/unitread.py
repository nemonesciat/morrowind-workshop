"""Particle effects made with UnitParticles (a Blender add-on that copies Unity's particle system) read from a .blend,
as the game's one cone emitter, like blendread.particles reads Blender's own particles.

The add-on keeps its settings on each object, and most of them as Unity's curves and gradients in node trees of
its own, with only what was changed written to the file. So the file is read the way the add-on reads it: by
Blender, headless, with the add-on asked for each emitter's values (its own extract and curve evaluators). Blender
runs with a private copy of the add-on and its libraries and an empty settings folder: a Blender started where an
add-on is switched off removes that add-on's libraries from the shared extensions folder (seen 2026-11-18), so
the user's own extensions folder is never what it runs from."""
import json
import math
import os
import re
import shutil
import subprocess
import tempfile

from editing import EditError

MARK = b'unit_particles'          # the add-on's settings on an object, by name in the file

# (what Blender runs: each emitter's settings, sampled with the add-on's own evaluators, as JSON)
SCRIPT = r'''
import bpy, addon_utils, importlib, json, sys
out_path = sys.argv[sys.argv.index('--') + 1]
names = [m.__name__ for m in addon_utils.modules() if m.__name__.endswith('.unit_particles')]
res = {'systems': [], 'error': None, 'outputs': []}
try:
    if not names:
        raise RuntimeError('no add-on')
    bpy.ops.preferences.addon_enable(module=names[0])
    ex = importlib.import_module(names[0] + '.extract')
    mat_mod = importlib.import_module(names[0] + '.material')
    scene = bpy.context.scene
    g = tuple(scene.gravity) if scene.use_gravity else (0.0, 0.0, 0.0)
    T = [i / 10.0 for i in range(11)]
    def ev(c, t=0.0, r=0.5):
        try:
            v = c(t, r)
        except TypeError:
            v = c(t)
        try:
            return [float(x) for x in v.reshape(-1)]
        except AttributeError:
            return [float(v)]
    for ob in scene.objects:
        sp = getattr(ob, 'unit_particles', None)
        if not sp or not sp.is_emitter:
            continue
        for o in (sp.output_object, sp.trail_object):
            if o is not None:
                res['outputs'].append(o.name)
        S, _sig, _deps = ex.extract(ob, scene)
        m, e, sh = S.main, S.emission, S.shape
        mods = {}
        for mid in ('velocity_over_lifetime', 'limit_velocity_over_lifetime', 'inherit_velocity', 'lifetime_by_emitter_speed',
                    'color_by_speed', 'size_by_speed', 'rotation_over_lifetime', 'rotation_by_speed', 'external_forces', 'noise',
                    'collision', 'triggers', 'sub_emitters', 'texture_sheet_animation', 'lights', 'trails', 'custom_data'):
            mods[mid] = bool(getattr(getattr(S, mid, None), 'enabled', False))
        d = {'name': ob.name, 'matrix': [list(r) for r in ob.matrix_world], 'gravity': list(g), 'fps': S.fps,
             'duration': m.duration, 'looping': bool(m.looping),
             'life': [ev(m.start_lifetime, 0, 0)[0], ev(m.start_lifetime, 0, 1)[0]],
             'speed': [ev(m.start_speed, 0, 0)[0], ev(m.start_speed, 0, 1)[0]],
             'size': [ev(m.start_size, 0, 0)[0], ev(m.start_size, 0, 1)[0]],
             'color': ev(m.start_color, 0.0)[:4], 'gravity_modifier': ev(m.gravity_modifier, 0.0)[0],
             'max_particles': int(m.max_particles), 'space': str(m.simulation_space),
             'emission': bool(e.enabled), 'rate': sum(ev(e.rate_over_time, t)[0] for t in T) / len(T),
             'bursts': [[b.time, ev(b.count, 0.0)[0], b.cycles, b.interval, b.probability] for b in (e.bursts or [])],
             'shape_on': bool(sh.enabled), 'shape': str(sh.shape), 'angle': sh.angle, 'radius': sh.radius,
             'arc': sh.arc, 'box': list(sh.scale), 'shape_position': list(sh.position), 'shape_rotation': list(sh.rotation),
             'randomize': sh.randomize_direction, 'spherize': sh.spherize_direction,
             'colour_over_life': [ev(S.color_over_lifetime.color, t)[:4] for t in T] if S.color_over_lifetime.enabled else None,
             'size_over_life': [ev(S.size_over_lifetime.size, t)[0] for t in T] if S.size_over_lifetime.enabled else None,
             'force': ev(S.force_over_lifetime.force, 0.5) if S.force_over_lifetime.enabled else None,
             'force_space': str(getattr(S.force_over_lifetime, 'space', 'LOCAL')),
             'render_mode': str(S.renderer.render_mode), 'material': S.renderer.material,
             'material_params': mat_mod.get_params(bpy.data.materials.get(S.renderer.material)) if S.renderer.material else None,
             'others': [k for k, v in mods.items() if v]}
        res['systems'].append(d)
    for coll in bpy.data.collections:
        if coll.name.startswith('UnitParticles Output'):
            res['outputs'] += [o.name for o in coll.all_objects]
except Exception as x:
    import traceback
    res['error'] = '%s: %s' % (type(x).__name__, x)
    res['trace'] = traceback.format_exc()[-1500:]
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(res, f, default=str)
'''

_cache = {}


def uses(raw):
    return MARK in raw


def _user_dirs():
    """Blender's per-user folders, newest version first (Windows: %APPDATA%; Linux: ~/.config/blender)."""
    roots = [os.path.join(os.environ.get('APPDATA', ''), 'Blender Foundation', 'Blender'),
             os.path.join(os.path.expanduser('~'), '.config', 'blender')]
    out = []
    for root in roots:
        if os.path.isdir(root):
            vs = [v for v in os.listdir(root) if re.fullmatch(r'\d+\.\d+', v)]
            vs.sort(key=lambda v: tuple(int(x) for x in v.split('.')), reverse=True)
            out += [os.path.join(root, v) for v in vs]
    return out


def _addon_dir():
    """The user's copy of the add-on (it is copied, never run, from there)."""
    for base in _user_dirs():
        for repo in ('user_default', 'blender_org'):
            p = os.path.join(base, 'extensions', repo, 'unit_particles')
            if os.path.isfile(os.path.join(p, 'blender_manifest.toml')):
                return p
    return None


def read(path):
    """The add-on's settings for each emitter of a .blend: {'systems', 'outputs'}, cached by the file's size and time.
    {'systems': [], 'note': why} when Blender or the add-on can't be found."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if key in _cache:
        return _cache[key]
    import assets
    exe = assets.blender()
    src = _addon_dir()
    if not exe or not src:
        return {'systems': [], 'outputs': [], 'note': 'Its particles were made with UnitParticles, which the Workshop reads '
                'through Blender with the add-on installed; %s.' % ('Blender was not found' if not exe else 'the add-on was not found')}
    work = tempfile.mkdtemp(prefix='ws_unitparticles_')
    try:
        ext = os.path.join(work, 'extensions', 'user_default')
        os.makedirs(ext)
        shutil.copytree(src, os.path.join(ext, 'unit_particles'), ignore=shutil.ignore_patterns('__pycache__'))
        conf = os.path.join(work, 'config')
        os.makedirs(conf)
        script = os.path.join(work, 'read.py')
        with open(script, 'w', encoding='utf-8') as f:
            f.write(SCRIPT)
        out = os.path.join(work, 'out.json')
        env = dict(os.environ, BLENDER_USER_EXTENSIONS=os.path.join(work, 'extensions'), BLENDER_USER_CONFIG=conf)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            # (the file first: Blender runs --python before opening a file named after it)
            subprocess.run([exe, '-b', os.path.abspath(path), '--python', script, '--', out], cwd=work, env=env, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        except subprocess.TimeoutExpired:
            raise EditError('Blender took too long reading the UnitParticles effects.')
        if not os.path.isfile(out):
            raise EditError('Blender could not read the UnitParticles effects in this file.')
        with open(out, encoding='utf-8') as f:
            res = json.load(f)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if res.get('error'):
        raise EditError('The UnitParticles effects could not be read: %s' % res['error'])
    _cache[key] = res
    return res


# ----- Unity's settings as the game's emitter ---------------------------------------------------------------------
def _norm(v):
    L = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / L for x in v]


def _unity(v):
    """A vector in Unity's axes (Y up, Z forward) in Blender's (Z up, Y forward), as the add-on swaps them."""
    return [v[0], v[2], v[1]]


def systems(path, bl=None):
    """The file's UnitParticles emitters as blendread.particles gives Blender's own (metres, Blender's axes), and the
    names of what the add-on makes for them (its particle meshes), which are not parts of the model. ({systems},
    outputs, note)"""
    import blendread
    res = read(path)
    if bl is None:
        bl = blendread.Blend(open(path, 'rb').read())
    folder = os.path.dirname(os.path.abspath(path))
    mats = {bl.name_of(b['at']): b['at'] for b in bl.blocks if b['code'][:2] == b'MA'}
    out = []
    for d in res.get('systems', []):
        left = []
        M = d['matrix']
        R, sc = blendread._axes(M)
        # (the cone leaves along the emitter's forward, which in Blender is its local Y: turned so it is the game
        # emitter's Z, the cone's middle there)
        Rx = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]          # (the game emitter's Z is the object's local Y)
        Re = [[sum(R[i][k] * Rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        s_mean = (sc[0] + sc[1] + sc[2]) / 3
        at = [M[i][3] for i in range(3)]
        sp_off = _unity(d.get('shape_position') or [0, 0, 0])
        if any(abs(x) > 1e-6 for x in sp_off):
            at = [at[i] + sum(R[i][k] * sp_off[k] * sc[k] for k in range(3)) for i in range(3)]
        if any(abs(x) > 1e-6 for x in d.get('shape_rotation') or []):
            left.append('the shape\'s own turn')
        shape = d['shape'] if d['shape_on'] else 'POINT'
        r = d['radius'] * s_mean
        v_dir, v_angle, h_dir, h_angle = 0.0, 0.0, 0.0, math.pi
        box = [0.0, 0.0, 0.0]
        if shape == 'CONE':
            v_angle, box = math.radians(d['angle']), [2 * r, 2 * r, 0.0]
        elif shape in ('SPHERE', 'HEMISPHERE'):
            v_angle, box = (math.pi if shape == 'SPHERE' else math.pi / 2), [2 * r] * 3
        elif shape == 'BOX':
            b = d['box']
            box = [b[0] * sc[0], b[1] * sc[2], b[2] * sc[1]]
        elif shape == 'CIRCLE':
            v_dir, box = math.pi / 2, [2 * r, 2 * r, 0.0]      # (out round the ring, flat)
            if d['arc'] < 359:
                left.append('an arc short of a full circle')
        elif shape != 'POINT':
            left.append('the %s shape (a point is used)' % shape.lower().replace('_', ' '))
        v_angle = min(math.pi, v_angle + math.pi * max(d.get('randomize') or 0, d.get('spherize') or 0))
        life_a, life_b = sorted(d['life'])
        sp_a, sp_b = sorted(d['speed'])
        sz_a, sz_b = sorted(d['size'])
        # (rate: the rate over time, with bursts spread over the duration)
        dur = max(0.05, d['duration'])
        rate = d['rate'] if d['emission'] else 0.0
        burst = sum(b[1] * max(1, b[2] or 1) for b in d['bursts']) if d['emission'] else 0.0
        if burst:
            rate += burst / dur
            left.append('bursts (spread over the duration)')
        if not d['looping']:
            left.append('playing once (the game plays it over and over)')
        life_mid = (life_a + life_b) / 2
        if rate * life_mid > d['max_particles'] > 0:
            rate = d['max_particles'] / max(1e-3, life_mid)
        if rate <= 0:
            continue
        # size: Unity's is a particle's full width; the game's a half width. Size over life: its peak, grown to and
        # faded from as the game's grow and fade do
        size = (sz_a + sz_b) / 4 * s_mean
        grow = fade = 0.0
        sol = d.get('size_over_life')
        if sol:
            peak = max(sol) or 1.0
            size *= peak
            t_up = next((i / 10 for i, v in enumerate(sol) if v >= 0.9 * peak), 0.0)
            t_dn = next((1 - i / 10 for i, v in reversed(list(enumerate(sol))) if v >= 0.9 * peak), 0.0)
            if sol[0] < 0.6 * peak:
                grow = t_up * life_mid
            if sol[-1] < 0.6 * peak:
                fade = t_dn * life_mid
        # pulls: gravity by its modifier, a force over lifetime (in the emitter's turn if local)
        accel = [x * d['gravity_modifier'] for x in d['gravity']]
        if d.get('force'):
            f = _unity(d['force'][:3])
            if d.get('force_space', 'LOCAL') == 'LOCAL':
                f = [sum(R[i][k] * f[k] for k in range(3)) for i in range(3)]
            accel = [accel[i] + f[i] for i in range(3)]
        # colours: the start colour times the colour over lifetime
        base = d['color'] if len(d['color']) == 4 else [1, 1, 1, 1]
        params = d.get('material_params') or {}
        bc = params.get('base_color')
        if isinstance(bc, (list, tuple)) and len(bc) >= 3:
            base = [base[k] * (bc[k] if k < len(bc) else 1.0) for k in range(4)]
        col = d.get('colour_over_life')
        # (the add-on's evaluators give linear colours, as Blender keeps them; the game's are sRGB)
        rgb = lambda c: [blendread._srgb(c[0]), blendread._srgb(c[1]), blendread._srgb(c[2]), max(0.0, min(1.0, c[3]))]
        colors = [[i / 10] + rgb([base[k] * c[k] for k in range(4)]) for i, c in enumerate(col)] if col else []
        base = rgb(base)
        glow = str(params.get('blending', '')).upper() in ('ADDITIVE', 'PREMULTIPLY')
        mat = mats.get(d.get('material') or '')
        pic = blendread._picture(bl, mat, folder) if mat is not None else None
        if d.get('render_mode') not in ('BILLBOARD', None):
            left.append('the %s render mode (drawn as sprites)' % str(d['render_mode']).lower().replace('_', ' '))
        left += [x.replace('_', ' ') for x in d.get('others') or []]
        s = {'name': d['name'], 'object': d['name'], 'at': at, 'R': Re, 'box': box,
             'speed': (sp_a + sp_b) / 2 * s_mean, 'speed_random': (sp_b - sp_a) * s_mean,
             'v_dir': v_dir, 'v_angle': v_angle, 'h_dir': h_dir, 'h_angle': h_angle,
             'rate': rate, 'duration': dur, 'life': life_a, 'life_random': life_b - life_a,
             'size': size, 'accel': accel, 'colors': colors, 'color': base,
             'glow': glow, 'picture': pic, 'left': left, 'grow': grow, 'fade': fade, 'unit': True}
        s['picture_key'] = blendread._key(pic['raw'] if isinstance(pic, dict) else open(pic, 'rb').read() if pic else b'')
        out.append(s)
    return out, set(res.get('outputs') or []), res.get('note')
