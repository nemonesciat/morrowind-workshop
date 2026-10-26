"""The game's light through the day, for the 3D view's time-of-day preview: each weather's sky, fog,
ambient and sun colours at sunrise, by day, at sunset and by night, and when the sun rises and sets, as
Morrowind.ini has them and OpenMW keeps them (openmw.cfg's fallback=Weather_... lines)."""
import esm

# (the 3D view's weather list, in its order, by the names Morrowind.ini gives them)
KINDS = ('Clear', 'Cloudy', 'Foggy', 'Overcast', 'Rain', 'Thunderstorm', 'Ashstorm', 'Blight', 'Snow', 'Blizzard')
PARTS = ('Sky', 'Fog', 'Ambient', 'Sun')
TIMES = ('Sunrise', 'Day', 'Sunset', 'Night')

# Morrowind.ini's own values for clear weather, for when openmw.cfg has none (a setup without the
# imported ini): sky, fog, ambient and sun at sunrise, day, sunset and night
CLEAR = {'Sky': [[117, 141, 164], [95, 135, 203], [56, 89, 129], [9, 10, 11]],
         'Fog': [[255, 189, 157], [206, 227, 255], [255, 189, 157], [9, 10, 11]],
         'Ambient': [[47, 66, 96], [137, 140, 160], [68, 75, 96], [13, 14, 18]],
         'Sun': [[242, 159, 119], [255, 252, 238], [255, 114, 79], [30, 38, 55]]}


def _rgb(s):
    try:
        v = [int(float(x)) for x in s.split(',')[:3]]
        return v if len(v) == 3 else None
    except ValueError:
        return None


def _num(s, d):
    try:
        return float(s)
    except (TypeError, ValueError):
        return d


def table():
    """{'sunrise': hour, 'sunrise_len': hours, 'sunset': hour, 'sunset_len': hours, 'from': 'openmw.cfg' or
    'built in', 'kinds': {name: {'Sky': [[r,g,b] x4], 'Fog': ..., 'Ambient': ..., 'Sun': ...}}}"""
    fb = esm.read_openmw_config().get('fallback') or {}
    out = {'sunrise': _num(fb.get('Weather_Sunrise_Time'), 6.0), 'sunrise_len': _num(fb.get('Weather_Sunrise_Duration'), 2.0),
           'sunset': _num(fb.get('Weather_Sunset_Time'), 18.0), 'sunset_len': _num(fb.get('Weather_Sunset_Duration'), 2.0),
           'from': 'openmw.cfg' if any(k.startswith('Weather_') for k in fb) else 'built in', 'kinds': {}}
    for kind in KINDS:
        got = {}
        for part in PARTS:
            row = [_rgb(fb.get('Weather_%s_%s_%s_Color' % (kind, part, t), '')) for t in TIMES]
            if all(row):
                got[part] = row
        # (a weather the setup lacks, e.g. without Bloodmoon's snow, falls back to clear weather's colours)
        out['kinds'][kind] = got if len(got) == len(PARTS) else dict(CLEAR)
    return out


# Morrowind.ini's own cloud pictures, cloud speeds and how much of the sun shows through, for a setup
# without the imported ini
CLOUDS = {'Clear': ('Tx_Sky_Clear.tga', 1.25, 1), 'Cloudy': ('Tx_Sky_Cloudy.tga', 2, 1), 'Foggy': ('Tx_Sky_Foggy.tga', 1.25, 0.25),
          'Overcast': ('Tx_Sky_Overcast.tga', 1.5, 0), 'Rain': ('Tx_Sky_Rainy.tga', 2, 0), 'Thunderstorm': ('Tx_Sky_Thunder.tga', 3, 0),
          'Ashstorm': ('Tx_Sky_Ashstorm.tga', 7, 0), 'Blight': ('Tx_Sky_Blight.tga', 9, 0), 'Snow': ('Tx_BM_Sky_Snow.tga', 1.5, 0),
          'Blizzard': ('Tx_BM_Sky_Blizzard.tga', 7.5, 0)}


def sky(db):
    """The game's own sky for the 3D view: each weather's cloud picture (a path the Workshop can serve, or
    None), cloud speed and sun glare; the cloud dome and the night sky from the game's meshes (shapes as
    nif.mesh_from_nif gives them), and the sun's and moons' pictures. Anything missing is None, and the
    view keeps its plain colour for it."""
    from nif import mesh_from_nif
    fb = esm.read_openmw_config().get('fallback') or {}
    tex = db.meshes.texture_path
    out = {'kinds': {}, 'sun': tex('tx_sun_05.dds'), 'masser': tex('tx_masser_full.dds'), 'secunda': tex('tx_secunda_full.dds'),
           'stars_from': _num(fb.get('Weather_Stars_Post-Sunset_Start'), 1), 'stars_to': _num(fb.get('Weather_Stars_Pre-Sunrise_Finish'), 2),
           'stars_fade': _num(fb.get('Weather_Stars_Fading_Duration'), 2),
           'masser_size': _num(fb.get('Moons_Masser_Size'), 94), 'secunda_size': _num(fb.get('Moons_Secunda_Size'), 40)}
    for kind in KINDS:
        name, speed, glare = CLOUDS[kind]
        out['kinds'][kind] = {'clouds': tex(fb.get('Weather_%s_Cloud_Texture' % kind) or name) or tex(name),
                              'speed': _num(fb.get('Weather_%s_Cloud_Speed' % kind), speed),
                              'glare': _num(fb.get('Weather_%s_Glare_View' % kind), glare),
                              'disc': _rgb(fb.get('Weather_%s_Sun_Disc_Sunset_Color' % kind, '')) or [128, 128, 128]}
    for key, model in (('dome', 'sky_clouds_01.nif'), ('night', 'sky_night_01.nif')):
        raw = db.meshes.read('meshes/' + model)
        try:
            shapes = mesh_from_nif(raw) if raw else None
        except Exception:
            shapes = None
        for s in shapes or []:
            s['tex'] = tex(s['tex'])
        out[key] = shapes or None
    return out
