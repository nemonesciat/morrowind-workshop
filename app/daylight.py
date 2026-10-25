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
