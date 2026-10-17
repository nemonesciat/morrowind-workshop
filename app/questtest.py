"""Quest testing through the live link: what the game should report back (quest stages,
global variables, item counts) and where to find the people a quest involves.

The commands themselves (set a stage, give an item...) travel in the live link's state
file as 'cmd' lines; the game answers with [WSLINK] lines that link.py collects."""
import math
import struct

import dialogue
import mapdata
import npc
from esm import iter_subrecords, zstr


def _project_infos(db):
    """Parsed lines (INFO) of this mod."""
    out = []
    for ri, r in enumerate(db.recs):
        if r is None or r[0] != 'INFO' or r[3] != db.proj_pidx or ri in db.dead:
            continue
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
            out.append(dialogue.parse_info(data))
        except Exception:
            continue
    return out


def watch_list(db):
    """Global variables and items the game should keep the Workshop told about:
    the mod's own globals, and whatever its lines check."""
    globs, items = set(), set()
    if not db.project:
        return globs, items
    for (tag, key), ri in getattr(db, 'overlay', {}).items():
        if tag == 'GLOB':
            globs.add(db.recs[ri][1])
    for d in _project_infos(db):
        for c in d['conds']:
            if c['kind'] == 'global' and c['name']:
                globs.add(c['name'])
            elif c['kind'] == 'item' and c['name']:
                items.add(c['name'])
    return globs, items


def globals_info(db, names):
    """name -> {'type': s/l/f, 'start': value} for global variables the game knows of."""
    out = {}
    for n in names:
        lst = [v for v in db.by_key.get(('GLOB', n.lower()), []) if v not in db.dead]
        if not lst:
            continue
        r = db.recs[lst[-1]]
        _t, _f, data = db.files[r[3]].record_at(r[4])
        kind, val = 's', 0.0
        for st, sd in iter_subrecords(data):
            if st == 'FNAM' and sd:
                kind = chr(sd[0])
            elif st == 'FLTV' and len(sd) >= 4:
                val = struct.unpack_from('<f', bytes(sd))[0]
        out[r[1]] = {'type': kind, 'start': val, 'mine': r[3] == db.proj_pidx}
    return out


def find_person(db, npc_id):
    """Where a character stands: (cell key, cell name, [x, y, z, rx, ry, rz]) or None."""
    low = npc_id.lower()
    for pl in npc.placements(db, npc_id):
        for r in mapdata.cellmap(db, pl['key']).get('refs', []):
            if r['id'].lower() == low:
                return pl['key'], pl['name'], r['p']
    return None


def spot_in_front(p, dist=110.0):
    """A spot just in front of someone standing at p, facing them (x, y, z, yaw)."""
    rz = p[5] if len(p) > 5 else 0.0
    x = p[0] + math.sin(rz) * dist
    y = p[1] + math.cos(rz) * dist
    return x, y, p[2] + 10.0, rz + math.pi


def quest_ids(db):
    """The quests in this mod (new or changed), for the test panel."""
    out = []
    for (tag, key), ri in getattr(db, 'overlay', {}).items():
        if tag != 'DIAL':
            continue
        r = db.recs[ri]
        try:
            _t, _f, data = db.files[r[3]].record_at(r[4])
        except Exception:
            continue
        typ = None
        name = r[1]
        for st, sd in iter_subrecords(data):
            if st == 'DATA' and sd:
                typ = sd[0]
            elif st == 'NAME':
                name = zstr(bytes(sd))
        if typ == 4:
            out.append({'key': key, 'id': name})
    return sorted(out, key=lambda q: q['id'].lower())
