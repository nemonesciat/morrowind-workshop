"""Secret entrances: turn a placed object into a door (to a place, or one that swings on an edge) or a
sliding panel driven by a script, and a door back into an ordinary object. Each is one change in the
activity list, so one Undo takes it back.

The scripts follow the game's own secret-door scripts (shrineGnisisSecret, BarDoor, GG_OpenGate1,
nchulfetingthRight): a local state and timer, "Move <axis> <units per second>" while the timer runs,
SetAtStart to put the panel back exactly, PlaySound3D on activation, and "id"->Move from a lever."""
import math
import os
import re
import struct

import doors
import editing
import mapdata
from editing import EditError
from esm import ENC, iter_subrecords, zstr
from project import join_subs, ref_info, set_ref_pos, zs

SECS = 1.5                                  # how long a panel takes to slide
HINGES = ('left', 'right', 'centre')
WAYS = ('left', 'right', 'up', 'down', 'back', 'forward')
WAY_WORDS = {'left': 'to the left', 'right': 'to the right', 'up': 'upwards', 'down': 'down into the floor',
             'back': 'back into the wall', 'forward': 'forward into the room'}


# ------------------------------------------------------------------ records and refs
def _record(db, ri):
    r = db.recs[ri]
    _t, flags, data = db.files[r[3]].record_at(r[4])
    return r, flags, [(t, bytes(d)) for t, d in iter_subrecords(data)]


def nice_name(rid):
    """A name for a piece of scenery that has none, from its ID: T_Imp_FurnM_Bookshelf_04 -> Bookshelf,
    in_hlaalu_wall_02 -> Wall, furn_de_closet_01 -> Closet."""
    skip = {'in', 'ex', 'furn', 'de', 'com', 'imp', 'set', 'stat', 'act', 'misc', 'con', 'cont', 'light', 'hla', 'red', 'tel',
            'nord', 'dwrv', 'daed', 'velothi', 'hlaalu', 'redoran', 'telvanni', 'common', 'small', 'large', 'big', 'rich', 'poor', 'mid',
            'ind', 'dres', 'cyr', 'sky', 'gc', 'mh', 'om', 'pc', 'tr', 'tdm', 'furnm', 'furnr', 'furnp', 'i', 'x', 'r', 't', 'v', 'c', 'm', 'p'}
    words = [w for w in re.split(r'[^A-Za-z]+', _base_id(rid)) if w and w.lower() not in skip]
    words = [w for w in words if not re.fullmatch(r'(seth|setr|sett|setv|setgc|setmh|setom|setanv|setstr)\w*', w.lower())]
    if not words:
        return ''
    w = words[-1]
    return w[0].upper() + w[1:]


def _model_and_name(db, ri, subs=None):
    if subs is None:
        _r, _f, subs = _record(db, ri)
    d = dict(subs)
    model = zstr(d['MODL']) if 'MODL' in d else None
    name = zstr(d['FNAM']) if 'FNAM' in d else ''
    return model, (name or (db.recs[ri][2] or '') or nice_name(db.recs[ri][1])).strip()


def _placed(db, cell_key, refkey):
    """The project's copy of the cell, all its refs, the placed object and its record index."""
    c, refs = editing._cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    rid = ref_info(ref['subs'])[0]
    ri = db.resolve_id(rid)
    if ri is None:
        raise EditError('No object called "%s".' % rid)
    return c, refs, ref, rid, ri


def _free_id(db, stem, keep=None):
    """stem, or stem_2, stem_3… until nothing has that ID (31 characters at most)."""
    stem = stem[:31]
    cand, n = stem, 2
    while db.resolve_id(cand) is not None and cand.lower() != (keep or '').lower():
        cand = '%s_%d' % (stem[:31 - 1 - len(str(n))], n)
        n += 1
    return cand


def _base_id(rid):
    """The object's ID without any suffix an earlier conversion gave it."""
    return re.sub(r'_(hidden|acti|plain|swing_[lrc]|slide|trig)(_\d+)?$', '', rid, flags=re.I)


def _script_slot(subs):
    """Where SCRI goes in a record: after the name, model and stats, before lists and the like."""
    return next((n for n, (t, _d) in enumerate(subs) if t in ('NPCO', 'NPCS', 'AIDT', 'AI_W', 'DODT', 'INDX', 'XSCL')), len(subs))


def _new_record(db, src_ri, new_id, tag, script=None, model=None, sounds=None):
    """A record of kind `tag` made from another: same model and name. When the kind stays the same
    everything else comes along too (a lamp keeps its light, a book its text)."""
    r, flags, subs = _record(db, src_ri)
    if tag == r[0]:
        out = [(t, d) for t, d in subs if t != 'SCRI']
        out = [(t, zs(new_id) if t == 'NAME' else d) for t, d in out]
    else:
        mdl, name = _model_and_name(db, src_ri, subs)
        out = [('NAME', zs(new_id)), ('MODL', zs(model or mdl)), ('FNAM', zs((name or 'Wall')[:31]))]
        if tag == 'DOOR':
            for sub, sid in zip(('SNAM', 'ANAM'), sounds or ()):
                if db.resolve_id(sid) is not None:
                    out.append((sub, zs(sid)))
    if model and tag == r[0]:
        out = [(t, zs(model) if t == 'MODL' else d) for t, d in out]
    if script:
        out.insert(_script_slot(out), ('SCRI', zs(script)))
        if tag == 'LIGH':
            # a candle that works a mechanism is not for picking up (the script stops that anyway)
            out = [(t, bytes(d[:20]) + struct.pack('<i', struct.unpack_from('<i', d, 20)[0] & ~0x2) + bytes(d[24:]) if t == 'LHDT' and len(d) >= 24 else d)
                   for t, d in out]
    db.project.set_record(tag, new_id.lower(), 0 if tag != r[0] else (flags & ~0x20), join_subs(out), created=True)
    db.sync_project()
    return db.resolve_id(new_id)


def _reuse(db, stem, tag):
    """An ID made before for this stem and kind (same model, same purpose), to use again."""
    for cand in (stem, ) + tuple('%s_%d' % (stem[:31 - 1 - len(str(n))], n) for n in range(2, 6)):
        lst = db.by_key.get((tag, cand.lower()))
        if lst and lst[-1] not in db.dead and db.recs[lst[-1]][3] == db.proj_pidx:
            return db.recs[lst[-1]][1]
    return None


def _swap(c, ref, refkey, new_id, link=None, pos=None):
    """The placed object swapped for another record, keeping its spot and turn (and, for a door, where it
    leads unless `link` says otherwise: None keeps, (name, pos6) sets, False drops)."""
    subs = [(t, zs(new_id) if t == 'NAME' else d) for t, d in ref['subs']]
    if link is False:
        subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
    elif link:
        subs = doors._set_link(subs, link[0], link[1])
    if pos is not None:
        subs = set_ref_pos(subs, tuple(pos))
    editing._store(c, refkey, ref['origin'], ref['idx'], subs)


def _door_sounds(db, choice, model):
    from library import DOOR_SOUNDS
    if choice not in DOOR_SOUNDS:
        choice = 'wood' if re.search(r'wood|plank|thatch|shelf|book|ward|cup|chest|crate|barrel', model or '', re.I) else 'stone'
    return DOOR_SOUNDS[choice], choice


# ------------------------------------------------------------------ which way a thing faces
def _front(db, rid, bounds):
    """(fx, fy): the direction the object's front points in its own coordinates, learnt from the game's
    rooms when it can be; else the thinner side, facing -Y (the way the game's doors and shelves do)."""
    try:
        import furnish
        f = furnish.front_of(db, rid)
        if f:
            return (float(f[0]), float(f[1])), True
    except Exception:
        pass
    if bounds and (bounds[3] - bounds[0]) < (bounds[4] - bounds[1]):
        return (-1.0, 0.0), False
    return (0.0, -1.0), False


def _way(front, way):
    """A direction in the object's own coordinates for a word said from where you stand in the room
    looking at it: left, right (your left and right), up, down, back (into the wall), forward."""
    fx, fy = front
    return {'left': (fy, -fx, 0.0), 'right': (-fy, fx, 0.0), 'up': (0.0, 0.0, 1.0), 'down': (0.0, 0.0, -1.0),
            'back': (-fx, -fy, 0.0), 'forward': (fx, fy, 0.0)}[way]


def _axis(v):
    """The object's own axis a direction mostly points along, and its sign."""
    a = max(range(3), key=lambda k: abs(v[k]))
    return 'XYZ'[a], 1 if v[a] >= 0 else -1


def _extent(bounds, v):
    """How far the object reaches along a direction (its width across that way)."""
    a = max(range(3), key=lambda k: abs(v[k]))
    return bounds[a + 3] - bounds[a]


def _rot2(dx, dy, angle):
    """Turn a horizontal offset the way the game turns objects (clockwise for positive angles)."""
    c, s = math.cos(angle), math.sin(angle)
    return dx * c + dy * s, -dx * s + dy * c


def describe(db, cell_key, refkey):
    """What the dialogs need to know about a placed object: its size, which way it faces (and whether
    that was learnt or guessed), the sounds a door can make, and a name for the scripts."""
    _c, _refs, ref, rid, ri = _placed(db, cell_key, refkey)
    from library import DOOR_SOUNDS
    import create
    r = db.recs[ri]
    model, name = _model_and_name(db, ri)
    b = db.meshes.bounds(model) if model else None
    front, learnt = _front(db, rid, b)
    pos = ref_info(ref['subs'])[1]
    out = {'id': rid, 'name': name or rid, 'type': r[0], 'model': model, 'bounds': b, 'front': front, 'front_learnt': learnt,
           'scale': ref_info(ref['subs'])[2], 'yaw': pos[5], 'mine': ref['pidx'] == db.proj_pidx,
           'sounds': list(DOOR_SOUNDS), 'sound': _door_sounds(db, None, model)[1],
           'prefix': create._prefix(db) if db.project else 'mod', 'to': doors.link_of(ref['subs'])}
    if b:
        out['size'] = {w: round(_extent(b, _way(front, w)), 1) for w in WAYS}
        out['axes'] = {w: '%s%s' % ('+' if s > 0 else '-', a) for w in WAYS for a, s in [_axis(_way(front, w))]}
    return out


# ------------------------------------------------------------------ 1. a door to somewhere
def _door_model_for(db, m2):
    """A door to put at the far end: the kind that place already uses, else a load door of its style."""
    ids = {}
    for r in m2['refs']:
        if r['type'] == 'DOOR' and 'load' in r['id'].lower():
            ids[r['id']] = ids.get(r['id'], 0) + 1
    if not ids:
        for r in m2['refs']:
            if r['type'] == 'DOOR':
                ids[r['id']] = ids.get(r['id'], 0) + 1
    if ids:
        return max(ids, key=ids.get)
    styles = {}
    for r in m2['refs']:
        if r.get('arch'):
            s = mapdata.style_of(r['id'])
            if s:
                styles[s] = styles.get(s, 0) + 1
    style = max(styles, key=styles.get).lower() if styles else ''
    for k, lst in db.by_key.items():
        if k[0] == 'DOOR' and 'loaddoor' in k[1] and style and style[:3] in k[1] and lst and lst[-1] not in db.dead:
            return db.recs[lst[-1]][1]
    for cand in ('in_hlaalu_loaddoor_01', 'ex_common_door_01'):
        if db.resolve_id(cand) is not None:
            return cand
    raise EditError('No door model to put at the other end.')


def _link_here(db, c, ref, refkey, cell_key, target):
    """Make the placed door lead into `target`, arriving just inside its door back here (that door is
    pointed at this one; one is placed when the place has none). No commit."""
    info = mapdata.cell_info(db, target)
    if not info:
        raise EditError('There is no place called "%s".' % target)
    if target == cell_key:
        raise EditError('A door can\'t lead into the place it stands in.')
    m2 = mapdata.cellmap(db, target)
    pos, back = doors.arrival(db, target, cell_key)
    if back is None:
        loose = [r for r in m2['refs'] if r['type'] == 'DOOR' and not r.get('to')]
        if loose:
            back = min(loose, key=lambda r: math.hypot(r['p'][0] - pos[0], r['p'][1] - pos[1]))
            pos = doors._in_front(m2, back)
    made = None
    c2, refs2 = editing._cell(db, target)
    here = next((r for r in mapdata.cellmap(db, cell_key)['refs'] if r['k'] == refkey), None)
    src = mapdata.cell_info(db, cell_key)
    back_pos = doors._in_front(mapdata.cellmap(db, cell_key), here) if here else None
    back_link = (src['name'] if src['interior'] else '', back_pos)
    if back is None:
        # nothing to come back through: a door of the place's own kind, a step behind where you arrive
        did = _door_model_for(db, m2)
        b = mapdata.object_bounds(db, db.resolve_id(did)) or [0, 0, 0, 0, 0, 0]
        yaw = pos[5]
        dx, dy = math.sin(yaw), math.cos(yaw)
        dpos = (pos[0] - dx * 110, pos[1] - dy * 110, pos[2] - 12 - b[2], 0.0, 0.0, (yaw + math.pi) % (2 * math.pi))
        nk = db.project.new_ref_key()
        subs = set_ref_pos([('NAME', zs(did))], dpos)
        if back_pos:
            subs = doors._set_link(subs, back_link[0], back_link[1])
        editing._store(c2, nk, db.project.plugin.lower(), int(nk.rsplit('|', 1)[1]), subs)
        made = did
    else:
        r2 = refs2.get(back['k'])
        if r2 and back_pos and not doors._leads_to(db, back.get('to'), cell_key):
            editing._store(c2, back['k'], r2['origin'], r2['idx'], doors._set_link(r2['subs'], back_link[0], back_link[1]))
    dest_name = info['name'] if info['interior'] else ''
    _swap(c, ref, refkey, ref_info(ref['subs'])[0], link=(dest_name, pos))
    return {'arrive': [round(v, 1) for v in pos], 'back': made or (back and back['id']), 'made_back': bool(made),
            'target': target, 'target_name': info['name'] or info['id']}


def make_door(db, cell_key, refkey, target=None, new=None, sound=None):
    """Any placed scenery becomes a door that looks the same and leads somewhere: `target` an existing
    place (cell key), or `new` {template, name, contents} a place made now from one of the game's."""
    editing._require_project(db)
    c, refs, ref, rid, ri = _placed(db, cell_key, refkey)
    r = db.recs[ri]
    if r[0] not in ('STAT', 'ACTI', 'CONT', 'DOOR'):
        raise EditError('Only scenery (a bookcase, a wall, a wardrobe) or a door can be made into a door.')
    if new:
        import create
        target = create.create_interior(db, new.get('template'), new.get('name'), new.get('contents') or 'furnished', None, save=False)
        db.sync_project()
    if not target:
        raise EditError('Pick where the door should lead.')
    made = None
    if r[0] != 'DOOR':
        made = editing.secret_ref(db, cell_key, refkey, 'door', save=False, sound=sound)
        db.sync_project()                       # (the swapped ref is read back from the overlay)
        c, refs, ref, rid, ri = _placed(db, cell_key, refkey)
    out = _link_here(db, c, ref, refkey, cell_key, target)
    out['id'] = rid
    note = 'Made "%s" a door to %s in %s' % (made['id'] if made else rid, out['target_name'], editing.cell_label(db, cell_key))
    if new:
        note += ' (a new place copied from %s)' % new.get('template')
    editing.commit(db, note)
    return out


def adopt(db, cell_key, refkey, target):
    """After Build from pieces put its own outside door on the hidden door's spot: the hidden door takes
    over where it led, and the spare door goes."""
    editing._require_project(db)
    c, refs, ref, rid, ri = _placed(db, cell_key, refkey)
    if db.recs[ri][0] != 'DOOR':
        raise EditError('"%s" is not a door.' % rid)
    p = ref_info(ref['subs'])[1]
    spare = None
    for k, other in refs.items():
        if k == refkey or other['origin'] != db.project.plugin.lower():
            continue
        oid, op, _s, dele = ref_info(other['subs'])
        if dele or math.hypot(op[0] - p[0], op[1] - p[1]) > 24:
            continue
        oi = db.resolve_id(oid)
        link = doors.link_of(other['subs'])
        if oi is not None and db.recs[oi][0] == 'DOOR' and link and link['key'] == target:
            spare = (k, other, link)
            break
    if spare:
        k, other, link = spare
        d = dict(other['subs'])
        arr = struct.unpack_from('<6f', d['DODT'])
        _swap(c, ref, refkey, rid, link=(zstr(d['DNAM']) if 'DNAM' in d else '', arr))
        c['refs'].pop(k, None)
        out = {'arrive': [round(v, 1) for v in arr], 'target': target, 'spare': True}
    else:
        out = _link_here(db, c, ref, refkey, cell_key, target)
    info = mapdata.cell_info(db, target)
    editing.commit(db, 'The hidden door "%s" in %s now leads to %s' % (rid, editing.cell_label(db, cell_key), info['name'] if info else target))
    return out


# ------------------------------------------------------------------ 2. an ordinary object again
def make_plain(db, cell_key, refkey):
    """A placed door (the game's or yours) becomes a static of the same model; its link goes. The door at
    the other end is left alone, but named."""
    editing._require_project(db)
    c, refs, ref, rid, ri = _placed(db, cell_key, refkey)
    r = db.recs[ri]
    if r[0] == 'STAT':
        raise EditError('It already is an ordinary object.')
    if r[0] not in ('DOOR', 'ACTI'):
        raise EditError('Only a door or an activator can be made an ordinary object.')
    model, name = _model_and_name(db, ri)
    if not model:
        raise EditError('"%s" has no model.' % rid)
    far = []
    to = doors.link_of(ref['subs'])
    if to:
        try:
            for d in mapdata.cellmap(db, to['key'])['refs']:
                if d['type'] == 'DOOR' and doors._leads_to(db, d.get('to'), cell_key):
                    far.append(d['name'] or d['id'])
        except Exception:
            far = []
    stem = (_base_id(rid)[:31 - 6] + '_plain')
    new_id = _reuse(db, stem, 'STAT')
    if new_id is None:
        new_id = _free_id(db, stem)
        _new_record(db, ri, new_id, 'STAT')
    _swap(c, ref, refkey, new_id, link=False)
    # (an object the Workshop's own script moved: its script record stays, harmless, for Undo)
    editing.commit(db, 'Made "%s" an ordinary object ("%s") in %s' % (rid, new_id, editing.cell_label(db, cell_key)))
    return {'id': new_id, 'was': rid, 'far': far, 'to': to}


# ------------------------------------------------------------------ 3. a rotating panel
def _hinged_model(db, model, h, tag):
    """A copy of the model with its origin moved to the hinge point (the game turns a door round its
    origin), written into the Library's folder. Returns the model path for a record."""
    import library
    import nif
    raw = db.meshes.read('meshes/' + model.lower().replace('\\', '/'))
    if not raw:
        raise EditError('Could not find the model %s.' % model)
    blocks = nif._blocks(raw)
    if not blocks or blocks[0][0] not in nif.NODE_TYPES:
        raise EditError('This model can\'t be re-seated (its file is not one the Workshop can rewrite).')
    p = blocks[0][1]
    nlen = struct.unpack_from('<I', raw, p)[0]
    tpos = p + 4 + nlen + 8 + 2
    t = struct.unpack_from('<3f', raw, tpos)
    new = bytearray(raw)
    struct.pack_into('<3f', new, tpos, t[0] - h[0], t[1] - h[1], t[2] - h[2])
    folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
    os.makedirs(folder, exist_ok=True)
    stem = library._free_name(folder, library._slug(os.path.basename(model)) + '_hinge_' + tag, '.nif')
    dest = os.path.join(folder, stem + '.nif')
    with open(dest, 'wb') as f:
        f.write(bytes(new))
    library._register(db, 'meshes/%s/%s.nif' % (library.SUB, stem), dest)
    try:
        import time
        items = library._index()
        items.append({'id': stem, 'name': os.path.basename(model) + ' (hinged)', 'type': 'model',
                      'file': 'meshes/%s/%s.nif' % (library.SUB, stem), 'model': '%s\\%s.nif' % (library.SUB, stem),
                      'added': time.time(), 'from': 'hinged copy of ' + model, 'records': {}, 'kind': 'door'})
        library._save_index(items)
    except Exception:
        pass
    return '%s\\%s.nif' % (library.SUB, stem)


def make_swing(db, cell_key, refkey, hinge='left', sound=None):
    """The object becomes a door that leads nowhere and swings open when used, on the edge you choose
    (your left or right as you look at it from the room, at the wall side; or round its own middle).
    The game turns a door round the model's origin, so a copy of the model with its origin at the hinge
    is made, and the piece is re-seated so nothing looks to have moved."""
    editing._require_project(db)
    if hinge not in HINGES:
        raise EditError('The hinge goes on the left, the right or in the centre.')
    c, refs, ref, rid, ri = _placed(db, cell_key, refkey)
    r = db.recs[ri]
    if r[0] not in ('STAT', 'ACTI', 'CONT', 'DOOR'):
        raise EditError('Only scenery or a door can be made a rotating panel.')
    model, name = _model_and_name(db, ri)
    if not model:
        raise EditError('"%s" has no model.' % rid)
    b = db.meshes.bounds(model)
    if not b:
        raise EditError('The size of "%s" could not be read, so the hinge can\'t be placed.' % rid)
    pos, scale = ref_info(ref['subs'])[1], ref_info(ref['subs'])[2]
    tagc = hinge[0]
    stem = _base_id(rid)[:31 - 8] + '_swing_' + tagc
    sounds, choice = _door_sounds(db, sound, model)
    new_id = _reuse(db, stem, 'DOOR')
    if new_id is not None:
        nri = db.resolve_id(new_id)
        hmodel = _model_and_name(db, nri)[0]
        # (where the origin went, from the copy's own bounds against the original's)
        hb = db.meshes.bounds(hmodel) or b
        h = (b[0] - hb[0], b[1] - hb[1], 0.0)
    else:
        front, _learnt = _front(db, rid, b)
        if hinge == 'centre':
            h = ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, 0.0)
        else:
            side, back = _way(front, hinge), _way(front, 'back')
            h = [0.0, 0.0, 0.0]
            for a in range(2):
                k = side[a] + back[a]
                h[a] = b[a + 3] if k > 1e-6 else b[a] if k < -1e-6 else (b[a] + b[a + 3]) / 2
            h = tuple(h)
        hmodel = _hinged_model(db, model, h, tagc)
        new_id = _free_id(db, stem)
        _new_record(db, ri, new_id, 'DOOR', model=hmodel, sounds=sounds)
    # the piece stays where it looks to be: its origin moves to the hinge point in the world
    wx, wy = _rot2(h[0] * scale, h[1] * scale, pos[5])
    npos = (pos[0] + wx, pos[1] + wy, pos[2] + h[2] * scale, pos[3], pos[4], pos[5])
    _swap(c, ref, refkey, new_id, link=False, pos=npos)
    editing.commit(db, 'Made "%s" a rotating panel ("%s", hinge %s) in %s' % (rid, new_id, hinge, editing.cell_label(db, cell_key)))
    return {'id': new_id, 'was': rid, 'hinge': hinge, 'moved': [round(wx, 1), round(wy, 1)], 'sound': choice}


# ------------------------------------------------------------------ 4. a sliding panel
SLIDE_SCRIPT = '''begin {id}

; Made by Morrowind Workshop: {what} slides {where} {dist} units when used, and back when used again.
; (The way the game's own secret doors do it: a timer, Move so many units a second, SetAtStart to close.)
short state
float timer

if ( MenuMode == 1 )
\treturn
endif

if ( OnActivate == 1 )
\tif ( state == 0 )
\t\tset state to 1
\t\tset timer to 0
\t\t{obj}PlaySound3D "{sound}"
\telseif ( state == 2 )
\t\tset state to 3
\t\tset timer to 0
\t\t{obj}PlaySound3D "{sound}"
\tendif
endif

if ( state == 1 )
\tset timer to ( timer + GetSecondsPassed )
\tif ( timer < {secs} )
\t\t{obj}Move {axis} {rate}
\telse
\t\tset state to 2
\tendif
elseif ( state == 3 )
\tset timer to ( timer + GetSecondsPassed )
\tif ( timer < {secs} )
\t\t{obj}Move {axis} {back}
\telse
\t\t{obj}SetAtStart
\t\tset state to 0
\tendif
endif

end
'''


def slide_script(sid, what, where, dist, axis, sign, sound, panel_id=None, secs=SECS):
    rate = sign * float(dist) / secs
    obj = '"%s"->' % panel_id if panel_id else ''
    return SLIDE_SCRIPT.format(id=sid, what=what, where=WAY_WORDS.get(where, where), dist='%g' % float(dist), obj=obj,
                               sound=sound, secs='%g' % secs, axis=axis, rate='%.1f' % rate, back='%.1f' % -rate)


def make_slide(db, cell_key, refkey, way='back', distance=None, sound=None, trigger=None):
    """The object becomes an activator that slides `distance` units `way` (left, right, up, down, back,
    forward as you look at it) over a second and a half when used, and back when used again. With
    `trigger` {cell, ref} another placed object (a lever, a candle, a book) is what you use instead: it
    carries the script and moves the panel. The script is attached and shown in the Scripts editor."""
    editing._require_project(db)
    import mwscript
    if way not in WAYS:
        raise EditError('Which way? left, right, up, down, back or forward.')
    c, refs, ref, rid, ri = _placed(db, cell_key, refkey)
    r = db.recs[ri]
    if r[0] not in ('STAT', 'ACTI', 'CONT', 'DOOR'):
        raise EditError('Only scenery or a door can be made a sliding panel.')
    model, name = _model_and_name(db, ri)
    if not model:
        raise EditError('"%s" has no model.' % rid)
    b = db.meshes.bounds(model)
    front, _learnt = _front(db, rid, b)
    v = _way(front, way)
    axis, sign = _axis(v)
    if distance is None:
        distance = _extent(b, v) if b else 128.0
    distance = float(distance)
    if not 1 <= distance <= 4096:
        raise EditError('The distance should be between 1 and 4096 units.')
    from library import DOOR_SOUNDS
    snd = DOOR_SOUNDS[_door_sounds(db, sound, model)[1]][0]
    import create
    prefix = create._prefix(db)
    # the panel: its own record (the script, or the lever's script, speaks to it by ID)
    stem = _base_id(rid)[:31 - 6] + '_slide'
    panel_id = _free_id(db, stem)
    slug = re.sub(r'[^a-z0-9]+', '', _base_id(rid).lower())[:14]
    sid = mwscript_free(db, '%s_%s_slide' % (prefix, slug))
    trig = None
    if trigger and trigger.get('ref'):
        tcell = trigger.get('cell') or cell_key
        tc, trefs, tref, trid, tri = _placed(db, tcell, trigger['ref'])
        if trigger['ref'] == refkey and tcell == cell_key:
            raise EditError('The panel can\'t be its own trigger: pick another object, or leave the trigger out.')
        tr = db.recs[tri]
        ttag = 'ACTI' if tr[0] == 'STAT' else tr[0]
        if ttag not in mwscript.SCRIPTABLE:
            raise EditError('A %s can\'t carry a script. Pick a lever, a candle, a book, a button or any scenery.' % tr[0])
        text = slide_script(sid, name or rid, way, distance, axis, sign, snd, panel_id)
        mwscript.save(db, sid, text, create=True, save=False)
        _new_record(db, ri, panel_id, 'ACTI')
        tid = _free_id(db, _base_id(trid)[:31 - 5] + '_trig')
        _new_record(db, tri, tid, ttag, script=sid)
        _swap(tc, tref, trigger['ref'], tid, link=False)
        trig = {'id': tid, 'was': trid, 'cell': tcell, 'ref': trigger['ref']}
    else:
        text = slide_script(sid, name or rid, way, distance, axis, sign, snd)
        mwscript.save(db, sid, text, create=True, save=False)
        _new_record(db, ri, panel_id, 'ACTI', script=sid)
    _swap(c, ref, refkey, panel_id, link=False)
    chk = mwscript.check(db, text, sid)
    editing.commit(db, 'Made "%s" a sliding panel ("%s", %s %g units%s) in %s' % (
        rid, panel_id, WAY_WORDS.get(way, way), distance, ' pulled by ' + trig['id'] if trig else '', editing.cell_label(db, cell_key)))
    return {'id': panel_id, 'was': rid, 'script': sid, 'trigger': trig, 'axis': axis, 'sign': sign, 'distance': distance,
            'sound': snd, 'check': chk}


def mwscript_free(db, stem):
    stem = re.sub(r'[^A-Za-z0-9_]', '', stem)[:31]
    cand, n = stem, 2
    while db.by_key.get(('SCPT', cand.lower())) or db.resolve_id(cand) is not None:
        cand = '%s_%d' % (stem[:31 - 1 - len(str(n))], n)
        n += 1
    return cand


# ------------------------------------------------------------------ the web API
def api(db, path, body):
    what = path.rsplit('/', 1)[-1]
    if what == 'info':
        return describe(db, body['cell'], body['ref'])
    if what == 'door':
        out = make_door(db, body['cell'], body['ref'], body.get('target'), body.get('new'), body.get('sound'))
    elif what == 'adopt':
        out = adopt(db, body['cell'], body['ref'], body['target'])
    elif what == 'plain':
        out = make_plain(db, body['cell'], body['ref'])
    elif what == 'swing':
        out = make_swing(db, body['cell'], body['ref'], body.get('hinge') or 'left', body.get('sound'))
    elif what == 'slide':
        out = make_slide(db, body['cell'], body['ref'], body.get('way') or 'back', body.get('distance'), body.get('sound'),
                         body.get('trigger'))
    else:
        raise EditError('Unknown secret-entrance action.')
    m = mapdata.cellmap(db, body['cell'])
    m['made'] = out
    return m
