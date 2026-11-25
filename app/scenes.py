"""The scene player: the mod's cutscenes (openmw-scene/1, kept in the mod by bridge.py) played in OpenMW by Lua the
Workshop writes beside the mod (project.lua_outputs), with the rest of its Lua.

Files, under scripts/<mod>/scene/:
  data.lua     every scene of the mod, as a Lua table (the scene files as they were sent, the trigger included)
  global.lua   the clock; actors found and set on their marks; clips, voices and the end; triggers; save and load
  player.lua   the camera (fixed and aimed shots, moves), fades and letterbox, music, controls, skip
  actor.lua    on each actor while a scene plays: its AI held, its clips, its effects

Played from outside with global events (any program, or the OpenMW Suite's live link for a preview):
  WsScene_Play {scene=id, t=0[, data=<a scene table>, mod=<this mod's slug>]}   WsScene_Pause / WsScene_Resume
  WsScene_Seek {t}   WsScene_Stop   WsScene_Skip      and the interface I.WorkshopScenes_<slug>
It says WsScene_Started {scene, mod} and WsScene_Ended {scene, mod, how}, and claims the camera with
CameraClaim {name} / CameraRelease {name} (another program's claim makes it let go until released).

Agreed rules (the Suite's authors and the user, 2026-11-25): the end always runs (finishing, skip, a save loaded
mid-scene, a missing actor); offsets are in the aimed actor's own frame (x right, y ahead, z up), at its aim height;
fixed shots are world positions with a compass yaw (0 north, clockwise) and a pitch (below 0 looks down)."""
import json
import re

VERSION = '1'


def lua_value(v, ind=''):
    """A JSON value as Lua source."""
    if v is None:
        return 'nil'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'
    nxt = ind + '  '
    if isinstance(v, (list, tuple)):
        if not v:
            return '{}'
        if all(isinstance(x, (int, float, str, bool)) for x in v):
            return '{' + ', '.join(lua_value(x) for x in v) + '}'
        return '{\n' + ',\n'.join(nxt + lua_value(x, nxt) for x in v) + '\n' + ind + '}'
    if isinstance(v, dict):
        if not v:
            return '{}'
        parts = []
        for k, x in v.items():
            k = str(k)
            key = k if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', k) and k not in LUA_WORDS else '[' + lua_value(k) + ']'
            parts.append('%s%s = %s' % (nxt, key, lua_value(x, nxt)))
        return '{\n' + ',\n'.join(parts) + '\n' + ind + '}'
    return lua_value(str(v))


LUA_WORDS = {'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'goto', 'if', 'in', 'local',
             'nil', 'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while'}


def movie_ids(slug):
    """The global variable and MWScript that play the mod's movies (PlayBink can't be called from Lua)."""
    base = 'ws' + slug[:24]
    return base + '_mv', base + '_mvs'


def movies(scenes):
    """Every movie file the scenes play, in a fixed order (its number is what the scene player sets)."""
    out = []
    for _k, sc in sorted((scenes or {}).items()):
        for c in (sc.get('screen') or []) if isinstance(sc, dict) else []:
            f = isinstance(c, dict) and c.get('movie')
            if isinstance(f, str) and f.strip():
                f = re.sub(r'^(?i:video)/', '', f.strip().replace('\\', '/'))
                if f not in out:
                    out.append(f)
    return out


def movie_records(db):
    """Keep the mod's movie global, its MWScript and start script in step with the scenes (called before the
    scene change is committed, so one Undo takes both back). A mod whose scenes play no movie has none of them."""
    import struct
    import mwscript
    from project import join_subs, zs
    p = db.project
    gv, sid = movie_ids(p.lua_slug())
    files = movies(p.scenes)
    if not files:
        for tag, key in (('SSCR', sid.lower()), ('SCPT', sid.lower()), ('GLOB', gv.lower())):
            if (p.records.get(tag + '|' + key) or {}).get('created'):
                p.remove_record(tag, key)
        db.sync_project()
        return
    p.set_record('GLOB', gv.lower(), 0, join_subs([('NAME', zs(gv)), ('FNAM', b's'), ('FLTV', struct.pack('<f', 0.0))]),
                 created=True)
    db.sync_project()
    branches = '\n'.join('%s ( n == %d )\n  PlayBink "%s" 1' % ('if' if i == 0 else 'elseif', i + 1, f.replace('"', ''))
                         for i, f in enumerate(files))
    text = ('; Made by Morrowind Workshop: plays the movies of this mod\'s scenes when the scene player asks.\n'
            'Begin %s\nshort n\nset n to %s\nif ( n == 0 )\n  return\nendif\nset %s to 0\n%s\nendif\nEnd\n'
            % (sid, gv, gv, branches))
    mwscript.save(db, sid, text, create=mwscript._winner(db, sid) is None, save=False)
    p.set_record('SSCR', sid.lower(), 0, join_subs([('DATA', zs(sid.lower())), ('NAME', zs(sid))]), created=True)
    db.sync_project()


# ------------------------------------------------------------------ for the scene maker and coding agents
_GROUPS = {}


def anim_groups(db, rec_i):
    """The animation groups an actor can play, by name with their length in seconds: a person's from the game's
    layers (xbase_anim, beast or female, their own), a creature's from its own .kf."""
    import nifanim
    r = db.recs[rec_i]
    key = (r[0], r[1].lower(), (r[5] or '').lower())
    if key in _GROUPS:
        return _GROUPS[key]
    files = []
    try:
        if r[0] == 'NPC_':
            files = [s['file'] for s in nifanim.layers(db, nifanim._person(db, rec_i), None)]
        elif r[5]:
            kf = nifanim.files_for(db, r[5]).get('kf')
            files = [kf] if kf else []
            # (a creature on the person skeleton, such as a Dremora or a Golden Saint: its walk, cast and attacks
            #  come from the game's base animations, its own file adds what it has of its own)
            base = 'meshes/xbase_anim.kf'
            if kf and base not in files:
                try:
                    own = nifanim.groups(nifanim.text_keys(db.meshes.read(kf) or b'')[0])
                except Exception:
                    own = []
                if len(own) < 10 and db.meshes.read(base):
                    files.insert(0, base)
    except Exception as e:
        print('scene maker: no animation for', r[1], e)
    out = {}
    for f in files:
        raw = db.meshes.read(f)
        if not raw:
            continue
        for g in nifanim.groups(nifanim.text_keys(raw)[0]):
            out[g['name'].lower()] = {'group': g['name'], 'length': round(max(0.0, g['stop'] - g['start']), 2)}
    _GROUPS[key] = sorted(out.values(), key=lambda g: g['group'].lower())
    return _GROUPS[key]


def sound_length(db, path):
    """A sound file's length in seconds (WAV from its header; MP3 from its frames' bit rate, or its Xing count), or
    None when it can't be read. path: as the game has it, "Sound/Vo/..." (case and slashes as you like)."""
    import struct
    p = (path or '').replace('\\', '/').lower().lstrip('/')
    if not p.startswith('sound/') and not p.startswith('music/'):
        p = 'sound/' + p
    try:
        raw = db.meshes.read(p)
    except Exception:
        raw = None
    if not raw:
        return None
    if raw[:4] == b'RIFF' and raw[8:12] == b'WAVE':
        i, rate, size = 12, None, None
        while i + 8 <= len(raw):
            tag, n = raw[i:i + 4], struct.unpack_from('<I', raw, i + 4)[0]
            if tag == b'fmt ':
                rate = struct.unpack_from('<I', raw, i + 16)[0]            # (bytes a second)
            elif tag == b'data':
                size = n
                break
            i += 8 + n + (n & 1)
        return round(size / rate, 2) if rate and size else None
    i = 0
    if raw[:3] == b'ID3' and len(raw) > 10:
        i = 10 + ((raw[6] & 0x7f) << 21 | (raw[7] & 0x7f) << 14 | (raw[8] & 0x7f) << 7 | (raw[9] & 0x7f))
    while i + 4 < len(raw) and not (raw[i] == 0xFF and (raw[i + 1] & 0xE0) == 0xE0):
        i += 1
    if i + 4 >= len(raw):
        return None
    h = struct.unpack('>I', raw[i:i + 4])[0]
    ver, layer, bri, sri = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3
    rates = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}.get(ver)
    if not rates or sri == 3 or layer != 1:
        return None
    sr = rates[sri]
    br1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    br2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    kbps = (br1 if ver == 3 else br2)[bri]
    spf = 1152 if ver == 3 else 576
    xi = raw.find(b'Xing', i, i + 200)
    if xi < 0:
        xi = raw.find(b'Info', i, i + 200)
    if xi >= 0 and struct.unpack_from('>I', raw, xi + 4)[0] & 1:
        frames = struct.unpack_from('>I', raw, xi + 8)[0]
        return round(frames * spf / sr, 2)
    return round((len(raw) - i) * 8 / (kbps * 1000), 2) if kbps else None


def _plugin_names(db):
    names = {}
    for p in getattr(db, 'plugins', None) or []:
        n = p.get('name') if isinstance(p, dict) else None
        if n:
            names[n.lower()] = n
    if db.project is not None:
        names[db.project.plugin.lower()] = db.project.plugin
    return names


def place_actors(db, cell_key):
    """The people and creatures standing in a place, for a scene: [{'ref': {file, index}, 'id', 'name', 'type',
    'pos': [x, y, z], 'yaw'}] (the plugin file as the game knows it, so the scene player finds them)."""
    import math
    from project import ref_info
    refs, _h = db.cell_refs(cell_key)
    names = _plugin_names(db)
    out = []
    for rk, ref in refs.items():
        if ref.get('deleted'):
            continue
        rid, pos, scale, gone = ref_info(ref['subs'])
        if gone:
            continue
        ri = db.resolve_id(rid)
        if ri is None or db.recs[ri][0] not in ('NPC_', 'CREA'):
            continue
        origin = str(ref.get('origin') or rk.rsplit('|', 1)[0])
        out.append({'ref': {'file': names.get(origin.lower(), origin), 'index': int(ref.get('idx') if ref.get('idx') is not None else rk.rsplit('|', 1)[1])},
                    'k': rk, 'ri': ri,
                    'id': db.recs[ri][1], 'name': db.recs[ri][2] or db.recs[ri][1], 'type': 'npc' if db.recs[ri][0] == 'NPC_' else 'creature',
                    'pos': [round(pos[0]), round(pos[1]), round(pos[2])], 'yaw': round(math.degrees(pos[5]), 1)})
    return sorted(out, key=lambda a: a['name'].lower())


OBJECT_KINDS = {'DOOR': 'door', 'LIGH': 'light', 'ACTI': 'activator', 'CONT': 'container'}


def place_objects(db, cell_key):
    """The doors, lights, activators and containers of a place, for a scene's world cues: [{'ref', 'id', 'name',
    'type': 'door'|'light'|'activator'|'container', 'pos', 'teleport'}] (teleport: a door to another place)."""
    from project import ref_info
    refs, _h = db.cell_refs(cell_key)
    names = _plugin_names(db)
    out = []
    for rk, ref in refs.items():
        if ref.get('deleted'):
            continue
        rid, pos, scale, gone = ref_info(ref['subs'])
        if gone:
            continue
        ri = db.resolve_id(rid)
        if ri is None or db.recs[ri][0] not in OBJECT_KINDS:
            continue
        origin = str(ref.get('origin') or rk.rsplit('|', 1)[0])
        tele = any(t == 'DODT' for t, _d in ref['subs']) if db.recs[ri][0] == 'DOOR' else False
        out.append({'ref': {'file': names.get(origin.lower(), origin), 'index': int(ref.get('idx') if ref.get('idx') is not None else rk.rsplit('|', 1)[1])},
                    'id': db.recs[ri][1], 'name': db.recs[ri][2] or db.recs[ri][1], 'type': OBJECT_KINDS[db.recs[ri][0]],
                    'pos': [round(pos[0]), round(pos[1]), round(pos[2])], 'teleport': tele})
    return sorted(out, key=lambda a: (a['type'], a['name'].lower()))


def effect_models(db):
    """Effects a scene can show, from the game's magic effects (their cast, hit, area and bolt looks) and every VFX
    static, then the mod's own particle effects: [{'model': 'meshes/...', 'name', 'group'}]."""
    seen, out = set(), []

    def add(model, name, group):
        m = (model or '').replace('\\', '/').strip()
        if not m:
            return
        if not m.lower().startswith('meshes/'):
            m = 'meshes/' + m
        if m.lower() in seen:
            for e in out:
                if e['model'].lower() == m.lower() and group == 'Magic' and name not in e['name']:
                    e['name'] += ' / ' + name
            return
        seen.add(m.lower())
        out.append({'model': m, 'name': name, 'group': group})
    for i, r in enumerate(db.recs):
        if r[0] == 'STAT' and r[1].lower().startswith('vfx_'):
            nm = re.sub(r'^vfx_', '', r[1], flags=re.I).replace('_', ' ')
            nm = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', nm)
            add(r[5], nm[:1].upper() + nm[1:], 'Magic')
    for i, r in enumerate(db.recs):
        if r[0] == 'LIGH' and r[5] and re.search(r'fire|flame|brazier', r[1], re.I):
            nm = re.sub(r'^(light|furn)[ _]', '', r[1], flags=re.I).replace('_', ' ').strip()
            add(r[5], nm[:1].upper() + nm[1:], 'Fire')
    import os
    import editing
    try:
        folder = os.path.dirname(editing.plugin_path(db)) if db.project is not None else None
    except Exception:
        folder = None
    if folder and os.path.isdir(os.path.join(folder, 'meshes')):
        # (the mod's own effects: its models with particles in them, such as the particle maker's)
        for root, _d, files in os.walk(os.path.join(folder, 'meshes')):
            for f in sorted(files):
                if f.lower().endswith('.nif'):
                    try:
                        raw = open(os.path.join(root, f), 'rb').read()
                    except OSError:
                        continue
                    if b'NiParticle' in raw or b'NiBSParticle' in raw:
                        add(os.path.relpath(os.path.join(root, f), folder).replace(os.sep, '/'), f[:-4], 'This mod')
    return out


WEATHERS = ['Clear', 'Cloudy', 'Foggy', 'Overcast', 'Rain', 'Thunderstorm', 'Ashstorm', 'Blight', 'Snow', 'Blizzard']


FORMAT = """openmw-scene/1, a JSON object:
format "openmw-scene/1"; scene (id: letters, numbers, _); name; cell ([x, y] outdoors, or an interior's name);
length (seconds).
player {controls: "off"|"on", sheathe: true, mark: "A"}.
marks {"A": [x, y, z, yaw]} world positions, yaw in degrees as the game turns things.
actors [{key, ref: {file, index}} or {key, id, pick: "nearest"}, mark: "B", clips: [{at, group, loop, speed,
keys: {"<text key>": "vfx:<id>"}}]] (group: one of the actor's own animation groups).
shots [{at, name, pos: [x, y, z], yaw, pitch, fov}] fixed (yaw: compass degrees, 0 north, clockwise; pitch below 0
looks down; fov vertical degrees), or [{at, aim: {actor, at: "head"|"chest"|"feet"}, offset: [right, ahead, up] in
the aimed actor's own frame from its aim height, fov}] or [{at, aim: {actor}, from: {actor: "player", shoulder:
"right"|"left"}}]; never pos and aim in one shot. move: {to: {offset or pos}, ease: "in"|"out"|"inOut"|"linear",
dur}. The shot showing is the last whose at has passed.
Actors also: spawn: true (made by the scene from id, at its mark; removed at the end unless stay: true); back: true (put back
where they stood once the scene ends);
appear: {at, vfx: model} (not there until at; a spawned one is made then); moves: [{at, to: "C" or ["C", "D"],
run}] (walks along the marks, turning to the last mark's yaw); leave: {at, how: "die"|"vanish", vfx: model}.
A skip or early end settles them as the scene would have (appeared, dead, gone).
lines [{at, who, text, voice: "Sound/Vo/..." (full data path; lips move)}].
sound [{at, music: "Music/..."}, {at, sound: "Sound/..." or a sound ID, on: actor key or ref: {file, index}}]
(on/ref: heard from there).
vfx [{id, on, bone, model, dur, at, loop}] on an actor, or [{at, mark: "X" or pos: [x, y, z], model, dur, loop,
scale}] at a spot (model: "meshes/...", such as a magic effect's cast, hit or area static).
world [{at, ref: {file, index}, do: "open"|"close"|"activate"|"hide"|"show"}, {at, weather: "thunderstorm", back:
true}, {at, hour: 21}] (doors, levers and activators, lights or any object shown or hidden; the weather; the time).
screen [{at, fade: "in"|"out", dur}, {at, letterbox: "2.39"}, {at, movie: "file.bik"}, {at, shake: 0-1, dur}].
Shots also take cut: "dip" | "white" and cutdur (seconds, 0.6): a dip to black or white around the cut.
end {do: [{controls: "on"}, {quest, stage}, {global, value}, {event, data}, {talk: actor key} (the conversation
opens with them again: for a scene started from a line of dialogue)], onSkip: "end"|"none",
onMissingActor: "end"}. The end always runs: finishing, skip, a save loaded mid-scene, a missing actor.
Typical close-up: offset [40, 90, 0] (in front, a little to her right), fov 35; over the shoulder: from the player's
right shoulder aiming at the speaker; wide: a fixed shot 600-1200 units away, pitch -10."""


# Post-processing in scenes: three small shaders of the Workshop's own (hidden from the player's shader menu, switched
# on by the scene player only while a scene uses them). The player needs post-processing on in OpenMW's settings;
# without it the cues do nothing and the scene plays the same.
PP_KEYS = ('exposure', 'temperature', 'saturation', 'vignette', 'focus', 'blur', 'motionblur')

SHADERS = {
    'shaders/ws_scene_grade.omwfx': r"""uniform_float uExposure { default = 0.0; min = -4.0; max = 4.0; step = 0.01; static = false; }
uniform_float uTemperature { default = 0.0; min = -100.0; max = 100.0; step = 1.0; static = false; }
uniform_float uSaturation { default = 1.0; min = 0.0; max = 2.0; step = 0.01; static = false; }
uniform_float uVignette { default = 0.0; min = 0.0; max = 1.0; step = 0.01; static = false; }

fragment main {
    omw_In vec2 omw_TexCoord;

    void main()
    {
        vec4 c = omw_GetLastShader(omw_TexCoord);
        c.rgb *= exp2(uExposure);
        float t = uTemperature / 100.0;
        c.rgb *= vec3(1.0 + 0.14 * t, 1.0 + 0.03 * t, 1.0 - 0.14 * t);
        float l = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
        c.rgb = mix(vec3(l), c.rgb, uSaturation);
        float d = distance(omw_TexCoord, vec2(0.5));
        c.rgb *= 1.0 - uVignette * smoothstep(0.25, 0.75, d);
        omw_FragColor = c;
    }
}

technique {
    description = "Morrowind Workshop scene colour";
    version = "1.0";
    author = "Morrowind Workshop";
    passes = main;
    flags = hidden;
    dynamic = true;
}
""",
    'shaders/ws_scene_dof.omwfx': r"""uniform_float uFocus { default = 300.0; min = 1.0; max = 100000.0; step = 1.0; static = false; }
uniform_float uRange { default = 250.0; min = 1.0; max = 100000.0; step = 1.0; static = false; }
uniform_float uStrength { default = 0.0; min = 0.0; max = 1.0; step = 0.01; static = false; }

fragment main {
    omw_In vec2 omw_TexCoord;

    float soft(vec2 uv)
    {
        return clamp(abs(omw_GetLinearDepth(uv) - uFocus) / uRange, 0.0, 1.0);
    }

    void main()
    {
        vec4 base = omw_GetLastShader(omw_TexCoord);
        float c = soft(omw_TexCoord) * uStrength;
        if (c < 0.01) {
            omw_FragColor = base;
            return;
        }
        vec2 r = omw.rcpResolution * 10.0 * c;
        vec3 sum = base.rgb;
        float w = 1.0;
        for (int i = 0; i < 24; i++) {
            float a = float(i) * 2.39996;
            float rr = sqrt((float(i) + 0.5) / 24.0);
            vec2 uv = omw_TexCoord + vec2(cos(a), sin(a)) * rr * r;
            float ww = max(soft(uv), 0.15);
            sum += omw_GetLastShader(uv).rgb * ww;
            w += ww;
        }
        omw_FragColor = vec4(sum / w, base.a);
    }
}

technique {
    description = "Morrowind Workshop scene depth of field";
    version = "1.0";
    author = "Morrowind Workshop";
    passes = main;
    flags = hidden;
    dynamic = true;
}
""",
    'shaders/ws_scene_motion.omwfx': r"""uniform_float uStrength { default = 0.0; min = 0.0; max = 1.0; step = 0.01; static = false; }

fragment main {
    omw_In vec2 omw_TexCoord;

    void main()
    {
        vec4 base = omw_GetLastShader(omw_TexCoord);
        if (uStrength < 0.01) {
            omw_FragColor = base;
            return;
        }
        vec4 world = vec4(omw_GetWorldPosFromUV(omw_TexCoord), 1.0);
        vec4 now = omw.projectionMatrix * omw.viewMatrix * world;
        vec4 before = omw.projectionMatrix * omw.prevViewMatrix * world;
        vec2 v = (now.xy / now.w - before.xy / before.w) * 0.5 * uStrength;
        float n = length(v);
        if (n > 0.04) v *= 0.04 / n;
        vec3 sum = base.rgb;
        for (int i = 1; i < 10; i++) {
            sum += omw_GetLastShader(omw_TexCoord - v * (float(i) / 9.0)).rgb;
        }
        omw_FragColor = vec4(sum / 10.0, base.a);
    }
}

technique {
    description = "Morrowind Workshop scene motion blur";
    version = "1.0";
    author = "Morrowind Workshop";
    passes = main;
    flags = hidden;
    dynamic = true;
}
""",
}


def uses_pp(scenes):
    return any(isinstance(c, dict) and any(k in c for k in PP_KEYS)
               for sc in (scenes or {}).values() if isinstance(sc, dict) for c in (sc.get('screen') or []))


def outputs(slug, scenes):
    """{relative path: text} and the .omwscripts lines for a mod's scenes ({} and [] when it has none)."""
    if not scenes:
        return {}, []
    base = 'scripts/%s/scene/' % slug
    data = '-- Made by Morrowind Workshop: the scenes of this mod (openmw-scene/1).\nreturn ' + lua_value(
        {k: v for k, v in sorted(scenes.items())}) + '\n'
    mv = movies(scenes)
    sub = lambda t: (t.replace('%SLUG%', slug).replace('%VERSION%', VERSION).replace('%MOVIEVAR%', movie_ids(slug)[0])
                     .replace('%MOVIES%', lua_value({f: i + 1 for i, f in enumerate(mv)})))
    out = {base + 'data.lua': data, base + 'global.lua': sub(GLOBAL), base + 'player.lua': sub(PLAYER),
           base + 'actor.lua': sub(ACTOR)}
    if uses_pp(scenes):
        out.update(SHADERS)
    lines = ['GLOBAL: ' + base + 'global.lua', 'PLAYER: ' + base + 'player.lua', 'CUSTOM: ' + base + 'actor.lua']
    return out, lines


GLOBAL = r'''-- Made by Morrowind Workshop: plays this mod's scenes (scene player %VERSION%, openmw-scene/1).
local world = require('openmw.world')
local core = require('openmw.core')
local types = require('openmw.types')
local util = require('openmw.util')
local vfs = require('openmw.vfs')

local SLUG = '%SLUG%'
local okData, SCENES = pcall(require, 'scripts.%SLUG%.scene.data')
if not okData then print('[WsScene] ' .. SLUG .. ': no scene data: ' .. tostring(SCENES)); SCENES = {} end
local ACTOR = 'scripts/%SLUG%/scene/actor.lua'
local EV = 'WsScene_' .. SLUG .. '_'
local NAME = 'scene:' .. SLUG
local MOVIEVAR = '%MOVIEVAR%'
local MOVIES = %MOVIES%     -- movie file -> its number for the MWScript that plays it (PlayBink isn't in Lua)

local cur = nil            -- the scene playing: {id, sc, t, paused, actors, fired, preview}
local played = {}          -- scenes whose trigger said once and that have run (kept in the save)
local pendingEnd = nil     -- a scene that was playing when the game was saved: its end runs once play resumes
local held = {}            -- other programs holding the camera
local checkT = 0

local function say(...) print('[WsScene] ' .. string.format(...)) end
local function player() return world.players[1] end
local function deg(v) return (tonumber(v) or 0) * math.pi / 180 end
local function v3(p) return util.vector3(tonumber(p[1]) or 0, tonumber(p[2]) or 0, tonumber(p[3]) or 0) end

local function cellName(sc)
  if type(sc.cell) == 'string' then return sc.cell end
  return ''                                            -- (outdoors: the position says where)
end

local function findRef(ref)
  if type(ref) ~= 'table' or not ref.file or not ref.index then return nil end
  local ok, id = pcall(core.getFormId, ref.file, tonumber(ref.index))
  if ok and id then
    local ok2, obj = pcall(world.getObjectByFormId, id)
    if ok2 and obj and obj:isValid() then return obj end
  end
  return nil
end

local function findActor(a, near)
  if type(a.ref) == 'table' and a.ref.file and a.ref.index then return findRef(a.ref) end
  if a.id then
    local best, bd = nil, math.huge
    local ok, list = pcall(world.getObjectsByRecordId, string.lower(a.id))
    if ok and list then
      for _, o in ipairs(list) do
        if o:isValid() and o.count > 0 and o.cell then
          local d = near and (o.position - near):length() or 0
          if d < bd then best, bd = o, d end
        end
      end
    end
    return best
  end
  return nil
end

local function missing(obj)
  if not obj or not obj:isValid() or obj.count == 0 then return true end
  local ok, dead = pcall(types.Actor.isDead, obj)
  return ok and dead
end

local function markAt(sc, name)
  local marks = type(sc.marks) == 'table' and sc.marks or {}
  return name and marks[name] or nil
end

local function hereCell()
  local p = player()
  return (p and p.cell and not p.cell.isExterior) and p.cell.name or ''
end

local function spotVfx(model, pos, opts)
  if not model or model == '' or not pos then return end
  local ok, err = pcall(world.vfx.spawn, model, pos, opts or {})
  if not ok then say('effect %s: %s', tostring(model), tostring(err)) end
end

local function sendPlayer(name, data)
  local p = player()
  if p then p:sendEvent(EV .. name, data or {}) end
end

local spawnActor, leaveActor, appearActor

-- skipped or ended early: who appears, dies or goes still does, so the world is as the scene leaves it
local function settle()
  for _, a in ipairs(type(cur.sc.actors) == 'table' and cur.sc.actors or {}) do
    local k = a.key
    if k and cur.waiting[k] and (a.stay or type(a.leave) ~= 'table') then spawnActor(a, true) end
    if k and cur.hidden[k] then appearActor(a, true) end
    if k and type(a.leave) == 'table' and not cur.gone[k] and cur.actors[k] then leaveActor(a, true) end
  end
end

local function finish(how)
  if not cur then return end
  if how ~= 'finish' and how ~= 'load' then pcall(settle) end
  local sc, actors = cur.sc, cur.actors
  local id, made, spots, back, home = cur.id, cur.made, cur.spots, cur.weatherBack, cur.home
  cur = nil
  for key, h in pairs(home or {}) do
    local obj = actors[key]
    if obj and obj:isValid() then
      pcall(function() obj.enabled = true end)
      pcall(function() obj:teleport(h.cell, h.pos, {rotation = h.rot}) end)
    end
  end
  for key, m in pairs(made or {}) do
    -- (made by the scene: gone again at the end, unless it stays)
    local obj = actors[key]
    if not m.stay and obj and obj:isValid() then
      local ok, err = pcall(function() obj:remove() end)
      if not ok then say('%s: could not remove %s: %s', tostring(id), key, tostring(err)); pcall(function() obj.enabled = false end) end
      actors[key] = nil
    end
  end
  for vid in pairs(spots or {}) do pcall(world.vfx.remove, vid) end
  if back then
    local p0 = player()
    pcall(function() core.weather.changeWeather(p0.cell.region, back) end)
  end
  local p = player()
  local endv = type(sc['end']) == 'table' and sc['end'] or {}
  local talkTo = nil
  for _, d in ipairs(type(endv['do']) == 'table' and endv['do'] or {}) do
    local ok, err = pcall(function()
      if d.quest and p then
        local q = types.Player.quests(p)[string.lower(d.quest)]
        if q.addJournalEntry then q:addJournalEntry(tonumber(d.stage) or 0) else q.stage = tonumber(d.stage) or 0 end
      elseif d.global and p then
        world.mwscript.getGlobalVariables(p)[d.global] = tonumber(d.value) or 0
      elseif d.event then
        core.sendGlobalEvent(d.event, type(d.data) == 'table' and d.data or {})
      elseif d.talk then
        talkTo = actors[d.talk]                       -- (the conversation goes on with them once the camera is back)
      end
    end)
    if not ok then say('%s: an end step failed: %s', id, tostring(err)) end
  end
  for _, obj in pairs(actors or {}) do
    if obj:isValid() and obj ~= p then obj:sendEvent(EV .. 'End', {}) end
  end
  sendPlayer('End', {how = how, controls = true})
  if talkTo and talkTo:isValid() then sendPlayer('Talk', {who = talkTo}) end
  core.sendGlobalEvent('CameraRelease', {name = NAME})
  core.sendGlobalEvent('WsScene_Ended', {scene = id, mod = SLUG, how = how})
  say('%s ended (%s)', id, how)
end

local function onMissing(key)
  local endv = type(cur.sc['end']) == 'table' and cur.sc['end'] or {}
  if (endv.onMissingActor or 'end') == 'end' then
    say('%s: actor %s is missing or dead: ending', cur.id, tostring(key)); finish('actor_missing'); return true
  end
  return false
end

local function place(obj, mark)
  if not mark or not obj then return end
  local rot = util.transform.rotateZ(deg(mark[4]))
  local cn = (obj.cell and not obj.cell.isExterior) and obj.cell.name or ''
  pcall(function() obj:teleport(cn, v3(mark), {rotation = rot, onGround = true}) end)
end

local function start(id, t, data)
  if cur then finish('replaced') end
  local sc = data or SCENES[id]
  if type(sc) ~= 'table' then say('no scene %s', tostring(id)); return end
  local p = player()
  if not p then return end
  local actors, keys = {player = p}, {}
  local marks = type(sc.marks) == 'table' and sc.marks or {}
  cur = {id = id, sc = sc, t = 0, paused = false, actors = actors, fired = {}, preview = data ~= nil,
         gone = {}, made = {}, waiting = {}, hidden = {}, begun = {}, grace = {}, spots = {}, spotEnd = {}, home = {}}
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    if a.key then
      local appearAt = type(a.appear) == 'table' and (tonumber(a.appear.at) or 0) or 0
      if a.spawn and a.id then
        cur.waiting[a.key] = true                       -- (made when its time comes)
      else
        local obj = findActor(a, p.position)
        if missing(obj) then
          if onMissing(a.key) then return end
        else
          actors[a.key] = obj
          keys[#keys + 1] = a.key
          if not obj:hasScript(ACTOR) then obj:addScript(ACTOR) end
          obj:sendEvent(EV .. 'Begin', {vfx = sc.vfx})
          cur.begun[a.key] = obj
          if a.back then
            -- (back where they were once the scene ends)
            cur.home[a.key] = {cell = (obj.cell and not obj.cell.isExterior) and obj.cell.name or '', pos = obj.position, rot = obj.rotation}
          end
          if a.mark and marks[a.mark] then place(obj, marks[a.mark]) end
          if appearAt > 0 then pcall(function() obj.enabled = false end); cur.hidden[a.key] = true end
        end
      end
    end
  end
  local pl = type(sc.player) == 'table' and sc.player or {}
  if pl.mark and marks[pl.mark] then
    local m = marks[pl.mark]
    pcall(function() p:teleport(cellName(sc), v3(m), {rotation = util.transform.rotateZ(deg(m[4])), onGround = true}) end)
  end
  core.sendGlobalEvent('CameraClaim', {name = NAME})
  sendPlayer('Begin', {id = id, sc = sc, actors = actors, held = next(held) ~= nil})
  core.sendGlobalEvent('WsScene_Started', {scene = id, mod = SLUG})
  say('%s started with %d actors', id, #keys)
  if t and t > 0 then cur.t = t; sendPlayer('Seek', {t = t}) end
end

local function lineSay(ln)
  local who = cur.actors[ln.who or ln.actor or '']
  if who and ln.voice and vfs.fileExists(ln.voice) then
    local ok, err = pcall(core.sound.say, ln.voice, who)
    if not ok then say('%s: voice %s failed: %s', cur.id, tostring(ln.voice), tostring(err)) end
  end
  if ln.text and ln.text ~= '' then
    -- (on screen until the next line, or for as long as it takes to read)
    local dur = tonumber(ln.dur) or (1.6 + #ln.text * 0.055)
    for _, o in ipairs(type(cur.sc.lines) == 'table' and cur.sc.lines or {}) do
      local d = (tonumber(o.at) or 0) - (tonumber(ln.at) or 0)
      if d > 0.05 and d < dur then dur = d end
    end
    sendPlayer('Text', {text = ln.text, dur = dur})
  end
end

-- an actor made by the scene (spawn), shown (appear), walked (moves), killed or sent away (leave)
spawnActor = function(a, quiet)
  cur.waiting[a.key] = nil
  local p = player()
  local m = markAt(cur.sc, a.mark) or (p and {p.position.x, p.position.y + 150, p.position.z, 0})
  local ok, obj = pcall(world.createObject, string.lower(a.id), 1)
  if not ok or not obj then say('%s: could not make %s: %s', cur.id, tostring(a.id), tostring(obj)); cur.gone[a.key] = true; return end
  pcall(function() obj:addScript(ACTOR) end)
  pcall(function() obj:teleport(hereCell(), v3(m), {rotation = util.transform.rotateZ(deg(m[4])), onGround = true}) end)
  cur.made[a.key] = {near = v3(m), stay = a.stay and true or false}
  cur.actors[a.key] = obj
  cur.grace[a.key] = cur.t + 1.5
  local fx = type(a.appear) == 'table' and a.appear.vfx
  if fx and not quiet then spotVfx(fx, v3(m)) end
  sendPlayer('Actors', {actors = cur.actors})
end

appearActor = function(a, quiet)
  cur.hidden[a.key] = nil
  local obj = cur.actors[a.key]
  if not obj or not obj:isValid() then return end
  pcall(function() obj.enabled = true end)
  local fx = type(a.appear) == 'table' and a.appear.vfx
  if fx and not quiet then spotVfx(fx, obj.position) end
end

leaveActor = function(a, quiet)
  local obj = cur.actors[a.key]
  cur.gone[a.key] = true
  if not obj or not obj:isValid() then return end
  local how = a.leave.how or 'vanish'
  if a.leave.vfx and not quiet then spotVfx(a.leave.vfx, obj.position) end
  if how == 'die' then
    obj:sendEvent(EV .. 'Die', {})                 -- (health is set by their own script: only it may)
  else
    local ok, err = pcall(function() obj.enabled = false end)
    if not ok then say('%s: %s could not be hidden: %s', cur.id, a.key, tostring(err)) end
  end
end

local function walkActor(a, mv)
  local obj = cur.actors[a.key]
  if not obj or not obj:isValid() then return end
  local to = type(mv.to) == 'table' and mv.to or {mv.to}
  local pts, face = {}, nil
  for _, name in ipairs(to) do
    local m = markAt(cur.sc, name)
    if m then pts[#pts + 1] = v3(m); face = m[4] and deg(m[4]) or nil end
  end
  if #pts > 0 then obj:sendEvent(EV .. 'Walk', {points = pts, run = mv.run and true or false, face = face}) end
end

local function worldCue(w)
  local p = player()
  if w.ref then
    local obj = findRef(w.ref)
    if not obj then say('%s: no object %s|%s for a world cue', cur.id, tostring(w.ref.file), tostring(w.ref.index)); return end
    local d = w['do'] or 'activate'
    if d == 'open' or d == 'close' then pcall(types.Door.activateDoor, obj, d == 'open')
    elseif d == 'hide' then pcall(function() obj.enabled = false end)
    elseif d == 'show' then pcall(function() obj.enabled = true end)
    elseif p then pcall(function() obj:activateBy(p) end) end
  end
  if w.weather and p and p.cell then
    local rec = core.weather.records[w.weather] or core.weather.records[string.lower(w.weather)]
    if not rec then
      for _, r in pairs(core.weather.records) do
        if string.lower(r.recordId or '') == string.lower(w.weather) or string.lower(r.name or '') == string.lower(w.weather) then rec = r end
      end
    end
    if rec then
      if w.back and not cur.weatherBack then cur.weatherBack = core.weather.getCurrent(p.cell) end
      local ok, err = pcall(core.weather.changeWeather, p.cell.region or '', rec)
      if not ok then say('%s: weather: %s', cur.id, tostring(err)) end
    else say('%s: no weather %s', cur.id, tostring(w.weather)) end
  end
  if w.hour then
    local now = (world.getGameTime() / 3600) % 24
    local h = ((tonumber(w.hour) or now) - now) % 24
    if h > 0.01 then pcall(world.advanceTime, h) end
  end
end

local function sound3d(c)
  local obj = (c.on and cur.actors[c.on]) or (c.ref and findRef(c.ref))
  if not obj or not c.sound then return end
  local opts = {volume = tonumber(c.volume) or 1}
  local file = string.find(c.sound, '[/\\.]') ~= nil
  local ok, err = pcall(file and core.sound.playSoundFile3d or core.sound.playSound3d, c.sound, obj, opts)
  if not ok then say('%s: sound %s: %s', cur.id, tostring(c.sound), tostring(err)) end
end

local function cueTimes(t, run)
  -- (every timed cue that isn't the actors' clips or lines: run = false marks those before t as done, for a seek)
  local sc = cur.sc
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    if a.key then
      if cur.waiting[a.key] then
        local at = type(a.appear) == 'table' and (tonumber(a.appear.at) or 0) or 0
        if at <= t then spawnActor(a, not run) end
      end
      if cur.hidden[a.key] and type(a.appear) == 'table' and (tonumber(a.appear.at) or 0) <= t then appearActor(a, not run) end
      for i, mv in ipairs(type(a.moves) == 'table' and a.moves or {}) do
        local k = 'move:' .. a.key .. ':' .. i
        if not cur.fired[k] and (tonumber(mv.at) or 0) <= t then cur.fired[k] = true; if run then walkActor(a, mv) end end
      end
      if type(a.leave) == 'table' and not cur.gone[a.key] and (tonumber(a.leave.at) or 0) <= t then
        if cur.actors[a.key] then leaveActor(a, not run) end
      end
    end
  end
  for i, w in ipairs(type(sc.world) == 'table' and sc.world or {}) do
    local k = 'world:' .. i
    if not cur.fired[k] and (tonumber(w.at) or 0) <= t then cur.fired[k] = true; if run or w.weather then worldCue(w) end end
  end
  for i, c in ipairs(type(sc.sound) == 'table' and sc.sound or {}) do
    local k = 'snd3:' .. i
    if (c.on or c.ref) and not cur.fired[k] and (tonumber(c.at) or 0) <= t then cur.fired[k] = true; if run then sound3d(c) end end
  end
  for i, v in ipairs(type(sc.vfx) == 'table' and sc.vfx or {}) do
    local k = 'vfx:' .. i
    if not v.on and (v.mark or v.pos) and not cur.fired[k] and (tonumber(v.at) or 0) <= t then
      cur.fired[k] = true
      local m = v.pos or markAt(sc, v.mark)
      if run and m then
        local vid = 'wsscene_' .. SLUG .. '_' .. i
        spotVfx(v.model, v3(m), {vfxId = vid, loop = v.loop and true or false, scale = tonumber(v.scale) or 1})
        cur.spots[vid] = true
        if v.dur then cur.spotEnd[vid] = (tonumber(v.at) or 0) + (tonumber(v.dur) or 1) end
      end
    end
  end
  for vid, te in pairs(cur.spotEnd) do
    if t >= te then cur.spotEnd[vid] = nil; cur.spots[vid] = nil; pcall(world.vfx.remove, vid) end
  end
end

local function seek(t)
  if not cur then return end
  cur.t = math.max(0, tonumber(t) or 0)
  cur.fired = {}
  local sc = cur.sc
  -- clips: each actor's latest clip at or before t plays from its start; lines and effects before t are passed
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    local last, li = nil, nil
    for i, c in ipairs(type(a.clips) == 'table' and a.clips or {}) do
      if (tonumber(c.at) or 0) <= cur.t then last, li = c, i; cur.fired['clip:' .. a.key .. ':' .. i] = true end
    end
    if last and cur.actors[a.key] then cur.actors[a.key]:sendEvent(EV .. 'Clip', {clip = last}) end
  end
  for i, ln in ipairs(type(sc.lines) == 'table' and sc.lines or {}) do
    if (tonumber(ln.at) or 0) <= cur.t then cur.fired['line:' .. i] = true end
  end
  for i, v in ipairs(type(sc.vfx) == 'table' and sc.vfx or {}) do
    if v.at and (tonumber(v.at) or 0) <= cur.t then cur.fired['vfx:' .. i] = true end
  end
  for i, c in ipairs(type(sc.screen) == 'table' and sc.screen or {}) do
    if c.movie and (tonumber(c.at) or 0) <= cur.t then cur.fired['movie:' .. i] = true end
  end
  cueTimes(cur.t, false)
  sendPlayer('Seek', {t = cur.t})
end

local function step(dt)
  if not cur or cur.paused then return end
  cur.t = cur.t + dt
  local sc, t = cur.sc, cur.t
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    local obj = cur.actors[a.key]
    if obj and (not obj:isValid() or obj.count == 0) then
      -- (moved to their mark, the game hands out a fresh object for them: found again, the camera told)
      local made = cur.made[a.key]
      local again = findActor(made and {id = a.id} or a, made and made.near or (player() and player().position))
      if again and again:isValid() and again.count > 0 then
        obj = again; cur.actors[a.key] = again
        sendPlayer('Actors', {actors = cur.actors})
      elseif cur.t < math.max(1.5, cur.grace[a.key] or 0) then
        obj = nil                                       -- (a moment's grace while a move settles)
      end
    end
    if obj and not cur.begun[a.key] and obj:isValid() and obj.count > 0 then
      -- (made by the scene: its script started once the game has it in the cell)
      if not obj:hasScript(ACTOR) then pcall(function() obj:addScript(ACTOR) end) end
      obj:sendEvent(EV .. 'Begin', {vfx = sc.vfx})
      cur.begun[a.key] = obj
      if cur.made[a.key] and not a.hostile then obj:sendEvent(EV .. 'Calm', {}) end
    end
    if obj and cur.gone[a.key] then obj = nil end      -- (killed or sent away by the scene: not missing)
    if obj then
      if missing(obj) then
        cur.actors[a.key] = nil
        if onMissing(a.key) then return end
      else
        for i, c in ipairs(type(a.clips) == 'table' and a.clips or {}) do
          local k = 'clip:' .. a.key .. ':' .. i
          if not cur.fired[k] and (tonumber(c.at) or 0) <= t then
            cur.fired[k] = true
            obj:sendEvent(EV .. 'Clip', {clip = c})
          end
        end
      end
    end
  end
  for i, ln in ipairs(type(sc.lines) == 'table' and sc.lines or {}) do
    if not cur.fired['line:' .. i] and (tonumber(ln.at) or 0) <= t then cur.fired['line:' .. i] = true; lineSay(ln) end
  end
  for i, c in ipairs(type(sc.screen) == 'table' and sc.screen or {}) do
    if c.movie and not cur.fired['movie:' .. i] and (tonumber(c.at) or 0) <= t then
      cur.fired['movie:' .. i] = true
      local f = string.gsub(string.gsub(c.movie, '\\', '/'), '^[Vv][Ii][Dd][Ee][Oo]/', '')
      local n = MOVIES[f]
      local p = player()
      if n and p then
        local ok, err = pcall(function() world.mwscript.getGlobalVariables(p)[MOVIEVAR] = n end)
        if not ok then say('%s: movie %s: %s', cur.id, f, tostring(err)) end
      else
        say("%s: movie %s is not in this mod's list (a preview plays only movies of saved scenes)", cur.id, f)
      end
    end
  end
  for i, v in ipairs(type(sc.vfx) == 'table' and sc.vfx or {}) do
    if v.on and v.at and not cur.fired['vfx:' .. i] and (tonumber(v.at) or 0) <= t then
      cur.fired['vfx:' .. i] = true
      local obj = cur.actors[v.on or '']
      if obj then obj:sendEvent(EV .. 'Vfx', {vfx = v}) end
    end
  end
  cueTimes(t, true)
  if not cur then return end
  if t >= (tonumber(sc.length) or 0) then finish('finish') end
end

-- triggers: what starts a scene (the Workshop sets them; the scene file leaves them out)
local function triggers()
  local p = player()
  if not p then return end
  for id, sc in pairs(SCENES) do
    local tr = type(sc) == 'table' and sc.trigger or nil
    if type(tr) == 'table' and not (tr.once ~= false and played[id]) then
      local go = false
      if tr.kind == 'area' and tr.center then
        local inCell = (type(tr.cell) ~= 'string') or (p.cell and string.lower(p.cell.name or '') == string.lower(tr.cell))
        local outdoor = type(tr.cell) ~= 'string' and p.cell and p.cell.isExterior
        if (inCell or outdoor) and (p.position - v3(tr.center)):length() <= (tonumber(tr.radius) or 300) then go = true end
      elseif tr.kind == 'quest' and tr.quest then
        local ok, q = pcall(function() return types.Player.quests(p)[string.lower(tr.quest)] end)
        if ok and q and (q.stage or 0) >= (tonumber(tr.stage) or 0) and (tonumber(tr.stage) or 0) > 0 then go = true end
      elseif tr.kind == 'global' and tr.name then
        local ok, g = pcall(function() return world.mwscript.getGlobalVariables(p)[tr.name] end)
        if ok and g and g == (tonumber(tr.value) or 1) then
          go = true
          pcall(function() world.mwscript.getGlobalVariables(p)[tr.name] = 0 end)
        end
      end
      if go then
        played[id] = true
        start(id, 0)
        return
      end
    end
  end
end

local function onUpdate(dt)
  if pendingEnd then
    local id = pendingEnd
    pendingEnd = nil
    local sc = SCENES[id]
    if sc then cur = {id = id, sc = sc, t = 0, actors = {}, fired = {}}; finish('load')
    else sendPlayer('End', {how = 'load', controls = true}) end
  end
  if cur then step(dt); return end
  checkT = checkT + dt
  if checkT >= 0.5 then checkT = 0; triggers() end
end

local api = {
  version = '%VERSION%',
  scenes = function() local l = {}; for k in pairs(SCENES) do l[#l + 1] = k end; table.sort(l); return l end,
  play = function(id, t, data) start(id, t or 0, data) end,
  pause = function() if cur then cur.paused = true; sendPlayer('Pause', {}) end end,
  resume = function() if cur then cur.paused = false; sendPlayer('Resume', {}) end end,
  seek = seek,
  stop = function() finish('stop') end,
  state = function() return cur and {scene = cur.id, t = cur.t, paused = cur.paused, length = cur.sc.length} or nil end,
}

return {
  interfaceName = 'WorkshopScenes_' .. SLUG,
  interface = api,
  engineHandlers = {
    onUpdate = onUpdate,
    onSave = function() return {played = played, playing = cur and not cur.preview and cur.id or nil} end,
    onLoad = function(data)
      played = (data and data.played) or {}
      if data and data.playing then pendingEnd = data.playing end
    end,
  },
  eventHandlers = {
    WsScene_Play = function(e)
      if e.data and e.mod ~= SLUG then return end              -- (a preview is for the mod it names)
      if not e.data and not SCENES[e.scene or ''] then return end
      start(e.scene or (e.data and e.data.scene) or 'preview', tonumber(e.t) or 0, e.data)
    end,
    WsScene_Pause = function() api.pause() end,
    WsScene_Resume = function() api.resume() end,
    WsScene_Seek = function(e) seek(e.t) end,
    WsScene_Stop = function() finish('stop') end,
    WsScene_Skip = function()
      if not cur then return end
      local endv = type(cur.sc['end']) == 'table' and cur.sc['end'] or {}
      if endv.onSkip == 'none' then return end
      finish('skip')
    end,
    CameraClaim = function(e)
      if e.name and e.name ~= NAME then held[e.name] = true; sendPlayer('Hold', {on = true}) end
    end,
    CameraRelease = function(e)
      if e.name and e.name ~= NAME then
        held[e.name] = nil
        if next(held) == nil then sendPlayer('Hold', {on = false}) end
      end
    end,
  },
}
'''

PLAYER = r'''-- Made by Morrowind Workshop: the camera, screen and controls of this mod's scenes (scene player %VERSION%).
local camera = require('openmw.camera')
local core = require('openmw.core')
local self = require('openmw.self')
local types = require('openmw.types')
local ui = require('openmw.ui')
local util = require('openmw.util')
local input = require('openmw.input')
local vfs = require('openmw.vfs')
local okA, ambient = pcall(require, 'openmw.ambient')
local okP, pp = pcall(require, 'openmw.postprocessing')
local I = require('openmw.interfaces')

local EV = 'WsScene_%SLUG%_'
local S = nil              -- {sc, actors, t, paused, mode, switches, bars, fade, music}
local LAYER = 'WsScene'    -- (the scene's own screen layer: bars, fades and subtitles above the game, the HUD hidden)
pcall(function() if not ui.layers.indexOf(LAYER) then ui.layers.insertAfter('HUD', LAYER, {interactive = false}) end end)
local function layer() local ok, i = pcall(ui.layers.indexOf, LAYER); return (ok and i) and LAYER or 'HUD' end
local function hud(on) pcall(function() I.UI.setHudVisibility(on) end) end
local hold = false
local SWITCHES = {'Controls', 'Fighting', 'Jumping', 'Looking', 'Magic', 'ViewMode', 'VanityMode'}

local function deg(v) return (tonumber(v) or 0) * math.pi / 180 end
local function v3(p) return util.vector3(tonumber(p[1]) or 0, tonumber(p[2]) or 0, tonumber(p[3]) or 0) end

local function setControls(on, keep)
  local P = types.Player
  for _, n in ipairs(SWITCHES) do
    local sw = P.CONTROL_SWITCH[n]
    if sw then
      if not on and keep then keep[n] = P.getControlSwitch(self, sw) end
      local want = on
      if on and keep and keep[n] ~= nil then want = keep[n] end
      pcall(P.setControlSwitch, self, sw, want)
    end
  end
end

-- where an actor's aim point is: its feet, chest or head (from its bounds, so race and scale count)
local function aimPoint(obj, at)
  local p = obj.position
  local ok, box = pcall(function() return obj:getBoundingBox() end)
  local top, mid = p.z + 110 * (obj.scale or 1), p.z + 70 * (obj.scale or 1)
  if ok and box then top = box.center.z + box.halfSize.z * 0.86; mid = box.center.z + box.halfSize.z * 0.25 end
  if at == 'feet' then return util.vector3(p.x, p.y, p.z + 5) end
  if at == 'chest' then return util.vector3(p.x, p.y, mid) end
  return util.vector3(p.x, p.y, top)               -- 'head'
end

local function markOf(who)
  -- (where someone's scene spot is: [x, y, z, yaw] or nil)
  local sc = S and S.sc or {}
  local marks = type(sc.marks) == 'table' and sc.marks or {}
  if who == 'player' then return sc.player and sc.player.mark and marks[sc.player.mark] end
  for _, a in ipairs(type(sc.actors) == 'table' and sc.actors or {}) do
    if a.key == who and a.mark then return marks[a.mark] end
  end
  return nil
end

local function frame(obj)
  local yaw = obj.rotation:getYaw()
  local fwd = util.vector3(math.sin(yaw), math.cos(yaw), 0)
  local right = util.vector3(math.cos(yaw), -math.sin(yaw), 0)
  return fwd, right
end

local function ease(x, kind)
  x = math.max(0, math.min(1, x))
  if kind == 'in' then return x * x end
  if kind == 'out' then return 1 - (1 - x) * (1 - x) end
  if kind == 'linear' then return x end
  return x * x * (3 - 2 * x)                       -- inOut
end

local function lerp(a, b, f) return a + (b - a) * f end

local function shotNow()
  local cur, nxt = nil, nil
  for _, s in ipairs(type(S.sc.shots) == 'table' and S.sc.shots or {}) do
    if (tonumber(s.at) or 0) <= S.t then cur = s end
  end
  return cur
end

local function offsetAt(s)
  local o = s.offset or {0, -150, 0}
  local mv = s.move
  if type(mv) == 'table' and type(mv.to) == 'table' and mv.to.offset then
    local f = ease((S.t - (tonumber(s.at) or 0)) / math.max(0.01, tonumber(mv.dur) or 1), mv.ease)
    o = {lerp(o[1] or 0, mv.to.offset[1] or 0, f), lerp(o[2] or 0, mv.to.offset[2] or 0, f), lerp(o[3] or 0, mv.to.offset[3] or 0, f)}
  end
  return o
end

local function look(from, to)
  local d = to - from
  local yaw = math.atan2(d.x, d.y)
  local pitch = -math.atan2(d.z, math.sqrt(d.x * d.x + d.y * d.y))     -- (the camera's pitch: above 0 looks down)
  return yaw, pitch
end

local function placeCamera()
  local s = shotNow()
  if not s then return end
  local pos, yaw, pitch
  if s.pos then
    pos = v3(s.pos)
    local mv = s.move
    if type(mv) == 'table' and type(mv.to) == 'table' and mv.to.pos then
      local f = ease((S.t - (tonumber(s.at) or 0)) / math.max(0.01, tonumber(mv.dur) or 1), mv.ease)
      pos = pos + (v3(mv.to.pos) - pos) * f
    end
    yaw, pitch = deg(s.yaw), -deg(s.pitch)
  else
    local aim = type(s.aim) == 'table' and s.aim or {}
    local target = S.actors[aim.actor or '']
    if not target or not target:isValid() then return end
    local P = aimPoint(target, aim.at or 'head')
    if type(s.from) == 'table' then
      local f = S.actors[s.from.actor or 'player'] or self.object
      local fwd, right = frame(f)
      local who = s.from.actor or 'player'
      local mk = markOf(who)
      if mk and mk[4] then
        -- (on a spot: the spot's facing, as the game may not have turned them yet)
        local y = (tonumber(mk[4]) or 0) * math.pi / 180
        fwd, right = util.vector3(math.sin(y), math.cos(y), 0), util.vector3(math.cos(y), -math.sin(y), 0)
      end
      local side = (s.from.shoulder == 'left') and -1 or 1
      pos = aimPoint(f, 'head') + right * (28 * side) - fwd * 45 + util.vector3(0, 0, 6)
    else
      local fwd, right = frame(target)
      local o = offsetAt(s)
      local base = util.vector3(target.position.x, target.position.y, P.z)
      pos = base + right * (o[1] or 0) + fwd * (o[2] or 0) + util.vector3(0, 0, o[3] or 0)
    end
    yaw, pitch = look(pos, P)
  end
  if S.shake then
    -- (a shake: strongest at its start, gone by its end)
    local f = (S.t - S.shake.t0) / math.max(0.05, S.shake.dur)
    if f >= 1 then S.shake = nil
    else
      local a = S.shake.amp * (1 - f)
      pos = pos + util.vector3(math.random() - 0.5, math.random() - 0.5, math.random() - 0.5) * (14 * a)
      yaw = yaw + (math.random() - 0.5) * 0.03 * a
      pitch = pitch + (math.random() - 0.5) * 0.03 * a
    end
  end
  camera.setStaticPosition(pos)
  camera.setYaw(yaw)
  camera.setPitch(pitch)
  if s.fov then camera.setFieldOfView(deg(s.fov)) end
end

local function black(alpha, y, h, white)
  local c = white and 1 or 0
  return ui.create({layer = layer(), type = ui.TYPE.Image, props = {
    resource = ui.texture({path = 'white'}), color = util.color.rgb(c, c, c), alpha = alpha,
    relativePosition = util.vector2(0, y), relativeSize = util.vector2(1, h)}})
end

local function subtitle(text, dur)
  if S.sub then S.sub:destroy(); S.sub = nil end
  local sz = ui.screenSize()
  local bar = S.barH or 0
  local y = bar > 0.04 and (1 - bar / 2) or 0.86
  S.sub = ui.create({layer = layer(), type = ui.TYPE.Text, props = {
    relativePosition = util.vector2(0.5, y), anchor = util.vector2(0.5, 0.5), size = util.vector2(sz.x * 0.8, sz.y * 0.1),
    autoSize = false, multiline = true, wordWrap = true, text = text, textSize = math.max(16, math.floor(sz.y / 32)),
    textColor = util.color.rgb(0.93, 0.9, 0.82), textShadow = true, textShadowColor = util.color.rgb(0, 0, 0),
    textAlignH = ui.ALIGNMENT.Center, textAlignV = ui.ALIGNMENT.Center}})
  S.subEnd = S.t + (tonumber(dur) or 3)
end

local function clearScreen()
  if S and S.bars then for _, e in ipairs(S.bars) do e:destroy() end; S.bars = nil end
  if S and S.fade then S.fade.el:destroy(); S.fade = nil end
  if S and S.dip then S.dip.el:destroy(); S.dip = nil end
  if S and S.sub then S.sub:destroy(); S.sub = nil end
  if S then S.shake = nil end
end

-- a dip to black (or white) around a cut that asks for one: dark at the moment the camera changes
local function dips()
  local a, white = 0, false
  for _, s in ipairs(type(S.sc.shots) == 'table' and S.sc.shots or {}) do
    if s.cut == 'dip' or s.cut == 'white' then
      local half = math.max(0.05, (tonumber(s.cutdur) or 0.6) / 2)
      local d = math.abs(S.t - (tonumber(s.at) or 0))
      if d < half and 1 - d / half > a then a, white = 1 - d / half, s.cut == 'white' end
    end
  end
  if a > 0.001 then
    if S.dip and S.dip.white ~= white then S.dip.el:destroy(); S.dip = nil end
    if not S.dip then S.dip = {el = black(a, 0, 1, white), white = white} end
    S.dip.el.layout.props.alpha = a
    S.dip.el:update()
  elseif S.dip then S.dip.el:destroy(); S.dip = nil end
end

local function screenCues()
  for i, c in ipairs(type(S.sc.screen) == 'table' and S.sc.screen or {}) do
    if not S.fired[i] and (tonumber(c.at) or 0) <= S.t then
      S.fired[i] = true
      if c.letterbox and not S.bars then
        local ratio = tonumber(c.letterbox) or 2.39
        local sz = ui.screenSize()
        local bar = (1 - (sz.x / sz.y) / ratio) / 2
        if bar > 0.005 then S.bars = {black(1, 0, bar), black(1, 1 - bar, bar)}; S.barH = bar end
      elseif c.letterbox == false and S.bars then
        for _, e in ipairs(S.bars) do e:destroy() end; S.bars = nil; S.barH = nil
      end
      if c.shake then S.shake = {t0 = tonumber(c.at) or S.t, amp = math.max(0, math.min(1, tonumber(c.shake) or 0.5)), dur = tonumber(c.dur) or 1} end
      if c.fade == 'in' or c.fade == 'out' then
        if S.fade then S.fade.el:destroy() end
        S.fade = {el = black(c.fade == 'in' and 1 or 0, 0, 1), from = (c.fade == 'in') and 1 or 0,
                  to = (c.fade == 'in') and 0 or 1, t0 = S.t, dur = tonumber(c.dur) or 1}
      end
    end
  end
  if S.fade then
    local f = math.max(0, math.min(1, (S.t - S.fade.t0) / S.fade.dur))
    S.fade.el.layout.props.alpha = S.fade.from + (S.fade.to - S.fade.from) * f
    S.fade.el:update()
    if f >= 1 and S.fade.to == 0 then S.fade.el:destroy(); S.fade = nil end
  end
  for i, c in ipairs(type(S.sc.sound) == 'table' and S.sc.sound or {}) do
    local k = 's' .. i
    if not S.fired[k] and (tonumber(c.at) or 0) <= S.t then
      S.fired[k] = true
      if c.music and okA and vfs.fileExists(c.music) then pcall(ambient.streamMusic, c.music); S.music = true end
      if c.sound and okA and not c.on and not c.ref then
        if string.find(c.sound, '[/\\.]') then
          if vfs.fileExists(c.sound) then pcall(ambient.playSoundFile, c.sound, {volume = tonumber(c.volume) or 1}) end
        else pcall(ambient.playSound, c.sound, {volume = tonumber(c.volume) or 1}) end
      end
    end
  end
end

-- post-processing: the scene's colour, depth of field and motion blur (the Workshop's own shaders, hidden from the
-- player's menu). A cue's values blend from what they were over its dur; they hold until the next cue changes them.
local PP = {
  exposure = {'grade', 'uExposure', 0}, temperature = {'grade', 'uTemperature', 0}, saturation = {'grade', 'uSaturation', 1},
  vignette = {'grade', 'uVignette', 0}, blur = {'dof', 'uStrength', 0}, range = {'dof', 'uRange', 250},
  motionblur = {'motion', 'uStrength', 0},
}
local PPFILE = {grade = 'ws_scene_grade', dof = 'ws_scene_dof', motion = 'ws_scene_motion'}

local function ppShader(kind)
  if not okP then return nil end
  S.shaders = S.shaders or {}
  if S.shaders[kind] == nil then
    local ok, sh = pcall(pp.load, PPFILE[kind])
    S.shaders[kind] = ok and sh or false
    if ok and sh then pcall(function() sh:enable() end) end
  end
  return S.shaders[kind] or nil
end

local function ppCues()
  S.pp = S.pp or {}
  for i, c in ipairs(type(S.sc.screen) == 'table' and S.sc.screen or {}) do
    local k = 'pp' .. i
    if not S.fired[k] and (tonumber(c.at) or 0) <= S.t then
      for name, d in pairs(PP) do
        if c[name] ~= nil and tonumber(c[name]) then
          local cur = S.pp[name] and S.pp[name].now or d[3]
          S.pp[name] = {from = cur, to = tonumber(c[name]), t0 = tonumber(c.at) or S.t, dur = tonumber(c.dur) or 0, now = cur}
        end
      end
      if c.focus ~= nil then S.focus = c.focus end
      S.fired[k] = true
    end
  end
  for name, v in pairs(S.pp) do
    local f = v.dur > 0 and math.max(0, math.min(1, (S.t - v.t0) / v.dur)) or 1
    v.now = v.from + (v.to - v.from) * f
    local d = PP[name]
    local sh = ppShader(d[1])
    if sh then pcall(function() sh:setFloat(d[2], v.now) end) end
  end
end

-- the depth of field's focus: on someone (their distance from the camera, every frame) or at a distance
local function ppFocus()
  if not S or not S.pp or not S.pp.blur or S.focus == nil then return end
  local sh = S.shaders and S.shaders.dof
  if not sh then return end
  local dist = tonumber(S.focus)
  if not dist and type(S.focus) == 'table' then
    local who = S.actors[S.focus.actor or ''] or (S.focus.actor == 'player' and self.object)
    if who and who:isValid() then dist = (aimPoint(who, S.focus.at or 'head') - camera.getPosition()):length() end
  end
  if dist then pcall(function() sh:setFloat('uFocus', dist) end) end
end

local function ppOff()
  for kind, sh in pairs(S and S.shaders or {}) do
    if sh then pcall(function() sh:disable() end) end
  end
end

local function finish(how)
  if not S then return end
  ppOff()
  clearScreen()
  hud(true)
  pcall(function() camera.setFieldOfView(camera.getBaseFieldOfView()) end)
  pcall(camera.setMode, S.mode or camera.MODE.ThirdPerson, true)
  setControls(true, S.switches)
  if S.music and okA then pcall(ambient.stopMusic) end
  S = nil
end

return {
  engineHandlers = {
    onUpdate = function(dt)
      if not S or S.paused then return end
      S.t = S.t + dt
      screenCues()
      dips()
      ppCues()
      if S.sub and S.t >= (S.subEnd or 0) then S.sub:destroy(); S.sub = nil end
    end,
    onFrame = function()
      if S and S.face then
        -- (the player turned to face as their spot says: moving them there doesn't turn them)
        local d = S.face - self.rotation:getYaw()
        d = (d + math.pi) % (2 * math.pi) - math.pi
        if math.abs(d) < 0.01 or S.faceTries > 20 then S.face = nil else self.controls.yawChange = d; S.faceTries = S.faceTries + 1 end
      end
      if S and not hold then placeCamera() end
      if S then ppFocus() end
    end,
    onKeyPress = function(key)
      if S and (key.code == input.KEY.Space or key.code == input.KEY.Enter) then core.sendGlobalEvent('WsScene_Skip', {}) end
    end,
    onSave = function() return S and {active = true, switches = S.switches, mode = S.mode} or nil end,
    onLoad = function(data)
      -- (saved in the middle of a scene: the player gets the controls and camera back; the scene's end runs too)
      if data and data.active then setControls(true, data.switches); pcall(camera.setMode, data.mode or camera.MODE.ThirdPerson, true); hud(true) end
    end,
  },
  eventHandlers = {
    [EV .. 'Begin'] = function(e)
      finish('replaced')
      S = {sc = e.sc, actors = e.actors or {}, t = 0, paused = false, fired = {}, switches = {}, mode = camera.getMode(), faceTries = 0}
      local pm = markOf('player')
      if pm and pm[4] then S.face = (tonumber(pm[4]) or 0) * math.pi / 180 end
      hold = e.held or false
      local pl = type(e.sc.player) == 'table' and e.sc.player or {}
      if pl.controls ~= 'on' then setControls(false, S.switches) end
      if pl.sheathe then pcall(function() types.Actor.setStance(self, types.Actor.STANCE.Nothing) end) end
      camera.setMode(camera.MODE.Static, true)
      hud(false)
      screenCues()
      ppCues()
    end,
    [EV .. 'Seek'] = function(e)
      if S then S.t = tonumber(e.t) or 0; S.fired = {}; clearScreen(); S.pp = {}; S.focus = nil; screenCues(); ppCues() end
    end,
    [EV .. 'Pause'] = function() if S then S.paused = true end end,
    [EV .. 'Resume'] = function() if S then S.paused = false end end,
    [EV .. 'Text'] = function(e)
      if not e.text then return end
      if S then subtitle(e.text, e.dur) else ui.showMessage(e.text) end
    end,
    [EV .. 'Hold'] = function(e) hold = e.on and true or false end,
    [EV .. 'Talk'] = function(e)
      if e.who and e.who:isValid() then pcall(function() I.UI.setMode('Dialogue', {target = e.who}) end) end
    end,
    [EV .. 'Actors'] = function(e) if S and e.actors then S.actors = e.actors end end,
    [EV .. 'End'] = function(e)
      if S then finish(e.how) elseif e.controls then setControls(true) end
    end,
  },
}
'''

ACTOR = r'''-- Made by Morrowind Workshop: an actor in one of this mod's scenes (scene player %VERSION%).
local self = require('openmw.self')
local anim = require('openmw.animation')
local async = require('openmw.async')
local types = require('openmw.types')
local I = require('openmw.interfaces')

local EV = 'WsScene_%SLUG%_'
local active, last, keys, vfx = false, nil, {}, {}
local hooked = {}
local walk = nil           -- {pts, i, run, face}: walking along the scene's marks

local function turnTo(want, dt)
  local d = (want - self.rotation:getYaw() + math.pi) % (2 * math.pi) - math.pi
  self.controls.yawChange = math.max(-5 * dt, math.min(5 * dt, d))
  return d
end

local function walking(dt)
  if not walk or dt <= 0 then return end
  local p = walk.pts[walk.i]
  if p then
    local dx, dy = p.x - self.position.x, p.y - self.position.y
    local dist = math.sqrt(dx * dx + dy * dy)
    if dist < (walk.i < #walk.pts and 60 or 28) then walk.i = walk.i + 1; walk.best = nil; return end
    -- (someone or something in the way: no nearer for a while, and close, or long stuck: they stop there)
    if not walk.best or dist < walk.best - 5 then walk.best, walk.since = dist, 0 else walk.since = walk.since + dt end
    if (walk.since > 0.6 and dist < 140) or walk.since > 2.5 then walk.i = walk.i + 1; walk.best = nil; return end
    local d = turnTo(math.atan2(dx, dy), dt)
    self.controls.movement = math.abs(d) < 1.0 and 1 or 0
    self.controls.run = walk.run
    walk.left = (walk.left or 30) - dt
    if walk.left < 0 then walk.pts = {} end                   -- (stuck: given up after half a minute)
  else
    self.controls.movement = 0
    if walk.face and math.abs(turnTo(walk.face, dt)) > 0.03 then return end
    self.controls.yawChange = 0
    walk = nil
  end
end

local function addVfx(v)
  if not v or not v.model then return end
  local id = 'wsscene_' .. tostring(v.id or v.model)
  pcall(anim.addVfx, self, v.model, {boneName = v.bone or '', vfxId = id, loop = v.loop and true or false})
  if v.dur then
    async:newUnsavableSimulationTimer(tonumber(v.dur) or 1, function() pcall(anim.removeVfx, self, id) end)
  end
end

local function onKey(group, key)
  local what = active and keys[string.lower(group)] and keys[string.lower(group)][string.lower(key)]
  if type(what) == 'string' and what:sub(1, 4) == 'vfx:' then
    local id = what:sub(5)
    for _, v in ipairs(vfx) do if v.id == id then addVfx(v) end end
  end
end

return {
  eventHandlers = {
    [EV .. 'Begin'] = function(e)
      active, vfx = true, (type(e.vfx) == 'table' and e.vfx) or {}
      pcall(function() self:enableAI(false) end)
    end,
    [EV .. 'Clip'] = function(e)
      local c = e.clip or {}
      if not c.group then return end
      local g = string.lower(c.group)            -- (OpenMW knows groups in lower case; the files may write Idle2)
      if not anim.hasGroup(self, g) then
        print('[WsScene] ' .. tostring(self.recordId) .. ' has no animation group ' .. tostring(c.group))
        return
      end
      if last and last ~= g then pcall(anim.cancel, self, last) end
      anim.clearAnimationQueue(self, false)
      local opts = {speed = tonumber(c.speed) or 1}
      if not c.loop then opts.loops = 0 end
      anim.playQueued(self, g, opts)
      last = g
      if type(c.keys) == 'table' then
        keys[g] = {}
        for k, v in pairs(c.keys) do keys[g][string.lower(k)] = v end
        if not hooked[g] and I.AnimationController then
          hooked[g] = true
          I.AnimationController.addTextKeyHandler(g, onKey)
        end
      end
    end,
    [EV .. 'Vfx'] = function(e) addVfx(e.vfx) end,
    [EV .. 'Walk'] = function(e)
      if last then pcall(anim.cancel, self, last); last = nil end
      walk = {pts = e.points or {}, i = 1, run = e.run and true or false, face = e.face}
    end,
    [EV .. 'Die'] = function()
      walk = nil
      if last then pcall(anim.cancel, self, last); last = nil end
      pcall(function() self:enableAI(true) end)
      local ok, err = pcall(function() types.Actor.stats.dynamic.health(self).current = 0 end)
      print('[WsScene] ' .. tostring(self.recordId) .. (ok and ' dies' or (' could not die: ' .. tostring(err))))
    end,
    [EV .. 'Calm'] = function()
      -- (made for the scene: a Dremora stays calm, so guards and townsfolk don't fall on it)
      local ok, err = pcall(function() types.Actor.stats.ai.fight(self).base = 0 end)
      if not ok then print('[WsScene] ' .. tostring(self.recordId) .. ' stays hostile: ' .. tostring(err)) end
    end,
    [EV .. 'End'] = function()
      active = false
      if walk then self.controls.movement = 0; walk = nil end
      if last then pcall(anim.cancel, self, last); last = nil end
      pcall(function() self:enableAI(true) end)
    end,
  },
  engineHandlers = {
    onUpdate = walking,
    onSave = function() return {active = active} end,
    onLoad = function(data)
      -- (saved during a scene: the actor walks again)
      if data and data.active then pcall(function() self:enableAI(true) end) end
    end,
  },
}
'''
