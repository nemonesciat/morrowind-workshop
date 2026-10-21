"""All the ways a project can change: field edits, templates, reverts and
placing/moving/removing objects in cells. Every change is saved immediately."""
import os
import re
import struct

from esm import ENC, iter_subrecords, zstr
from project import b64, join_subs, ref_info, set_ref_pos, state_diff, zs

PLACEABLE = {'STAT', 'ACTI', 'DOOR', 'CONT', 'LIGH', 'NPC_', 'CREA', 'LEVC', 'WEAP', 'ARMO', 'CLOT', 'MISC',
             'BOOK', 'ALCH', 'INGR', 'APPA', 'LOCK', 'PROB', 'REPA'}
NOT_COPYABLE = {'CELL', 'INFO', 'DIAL', 'LAND', 'PGRD', 'GMST', 'SKIL', 'MGEF', 'LTEX'}
INT_RANGES = {'b': (-128, 127), 'B': (0, 255), 'h': (-32768, 32767), 'H': (0, 65535),
              'i': (-2 ** 31, 2 ** 31 - 1), 'I': (0, 2 ** 32 - 1)}


class EditError(Exception):
    pass


def plugin_path(db):
    d = os.environ.get('WORKSHOP_PLUGIN_DIR') or db.config.get('data_local') or os.path.join(db.config['userdir'], 'data')
    return os.path.join(d, db.project.plugin)


def build(db):
    """Write the mod (with its Lua files) and its grass file, if it has grass."""
    db.project.build(db.proj_masters, plugin_path(db))
    try:
        import grass
        grass.write(db)
    except Exception as e:                  # grass must never stop the mod itself being saved
        print('could not write the grass file:', e)


def grass_file(db):
    """The mod's groundcover plugin name, when it has grass."""
    p = db.project
    if not p or not getattr(p, 'grass', None):
        return None
    import grass
    return grass.file_name(p)


def lua_content(db):
    """The mod's .omwscripts file name, when it has Lua scripts (it goes in the load order too)."""
    p = db.project
    if not p or not getattr(p, 'lua', None):
        return None
    return p.lua_omwscripts()


def commit(db, note=None, reverts=None):
    p = db.project
    before = getattr(p, 'last_state', None)
    after = p.state()
    entry = None
    if note:
        entry = p.note(note, state_diff(before, after) if before is not None else None)
        if reverts:
            entry['reverts'] = reverts
    if before is not None:
        stack = p.__dict__.setdefault('undo_stack', [])
        stack.append((before, note or 'change', entry['id'] if entry else None))
        del stack[:-100]
        # big projects (lots of grass) make big undo steps: keep the history within ~300 MB
        total = sum(len(s[0]) for s in stack)
        while len(stack) > 5 and total > 300_000_000:
            total -= len(stack.pop(0)[0])
    p.last_state = after
    db.sync_project()
    p.save()
    build(db)
    _notify(db)
    try:
        import together
        if together.active():
            together.on_commit(db, before, after, note)       # (building together: to everyone else)
    except Exception as e:                  # sharing must never break editing
        print('building together:', e)
    return entry


def _notify(db):
    cb = getattr(db, 'on_project_change', None)
    if cb:
        try:
            cb()
        except Exception as e:      # the live link must never break editing
            print('live link update failed:', e)


def undo_depth(db):
    return len(getattr(db.project, 'undo_stack', [])) if db.project else 0


def undo(db, to_depth=None):
    """Undo the last change, or every change back to a recorded depth."""
    _require_project(db)
    p = db.project
    try:
        import together
        if together.active() and to_depth is None:
            # building together: your own last change only (putting the whole mod back would take
            # other people's work with it)
            e = together.own_last(p)
            if not e:
                raise EditError('Nothing of yours to undo.')
            undo_entry(db, e['id'])
            return [e['text']]
    except ImportError:
        pass
    stack = getattr(p, 'undo_stack', [])
    if not stack:
        raise EditError('Nothing to undo.')
    target = len(stack) - 1 if to_depth is None else max(0, int(to_depth))
    undone, ids = [], []
    before = p.last_state
    while len(stack) > target:
        item = stack.pop()
        state, note = item[0], item[1]
        p.restore(state)
        undone.append(note)
        if len(item) > 2 and item[2]:
            ids.append(item[2])
    for i in ids:
        _set_active(p, i, False)
    after = p.state()
    entry = p.note('Undid: ' + '; '.join(undone[:5]) + (' (+%d more)' % (len(undone) - 5) if len(undone) > 5 else ''),
                   state_diff(before, after))
    entry['reverts'] = ids
    p.last_state = after
    db.sync_project()
    p.save()
    build(db)
    _notify(db)
    return undone


def _set_active(p, entry_id, active, depth=0):
    """Mark a logged change as in effect or undone. An "Undid ..." entry being
    in effect means the changes it reverted are not, and the other way round."""
    if depth > 50:
        return
    e = next((x for x in p.log if x.get('id') == entry_id), None)
    if not e:
        return
    e['undone'] = not active
    for r in e.get('reverts', []):
        _set_active(p, r, not active, depth + 1)


def _footprint(db, e):
    """What a logged change touched and created, for working out which later changes build on it."""
    import base64
    d = e.get('diff') or {}
    f = {'keys': set(), 'cells': set(), 'new_cells': set(), 'new_ids': set(), 'names': set(), 'dials': set(),
         'new_dials': set()}
    for k, (b, a) in d.get('r', {}).items():
        f['keys'].add(('r', k))
        tag, key = k.split('|', 1)
        if tag == 'INFO':
            f['dials'].add(key.split('|', 1)[0])
        elif tag == 'DIAL':
            f['dials'].add(key)
            if b is None:
                f['new_dials'].add(key)
        elif tag == 'PGRD':
            f['cells'].add(key)                 # walking paths belong to their place
        elif b is None:
            f['new_ids'].add(key)
    for ck, cd in d.get('c', {}).items():
        f['cells'].add(ck)
        made = cd.get('meta', {}).get('new')
        if made is None and db is not None:
            # older entries: a place only this mod has, whose objects all appeared in this change
            versions = [v for v in db.by_key.get(('CELL', ck), []) if v not in db.dead]
            made = all(db.recs[v][3] == db.proj_pidx for v in versions) and all(b is None for b, _a in cd['refs'].values())
        if made:
            f['new_cells'].add(ck)
        for rk, (b, a) in cd['refs'].items():
            f['keys'].add(('c', ck, rk))
            for side in (a, b):
                if side:
                    for t, v in side.get('subs', []):
                        if t == 'NAME':
                            f['names'].add(zstr(base64.b64decode(v)).lower())
                            break
    return f


def _live(p):
    """Real changes still in effect. "Undid"/"Redid" entries are bookkeeping: their effect is already
    told by the original changes being marked undone or not."""
    return [e for e in p.log if e.get('diff') and not e.get('undone') and not e.get('reverts')]


def _builds_on(later, earlier):
    return bool(later['keys'] & earlier['keys'] or later['cells'] & earlier['new_cells'] or
                later['names'] & earlier['new_ids'] or later['dials'] & earlier['new_dials'])


def activity(db):
    """For each change in the log: the change it builds on (parent) and how many later changes build
    on it, directly or through others (inside). Only changes still in effect count."""
    p = db.project
    live = _live(p)
    fps = {e['id']: _footprint(db, e) for e in live}
    parent, kids = {}, {}
    for n, e in enumerate(live):
        for prev in reversed(live[:n]):
            if _builds_on(fps[e['id']], fps[prev['id']]):
                parent[e['id']] = prev['id']
                kids.setdefault(prev['id'], []).append(e['id'])
                break
    return parent, kids, fps


def branch_sizes(db):
    """For each change still in effect: how many later changes Undo would take back with it."""
    live = _live(db.project)
    fps = {e['id']: _footprint(db, e) for e in live}
    out = {}
    for n, e in enumerate(live):
        group = [e['id']]
        for later in live[n + 1:]:
            if any(_builds_on(fps[later['id']], fps[g]) for g in group):
                group.append(later['id'])
        out[e['id']] = len(group) - 1
    return out


def _dependents(db, entry_id):
    """Every later change still in effect that builds on this one, directly or through another."""
    p = db.project
    live = _live(p)
    fps = {e['id']: _footprint(db, e) for e in live}
    group = [entry_id]
    for e in live:
        if e['id'] <= entry_id:
            continue
        if any(_builds_on(fps[e['id']], fps[g]) for g in group if g in fps):
            group.append(e['id'])
    return group[1:]


def _revert_diff(p, d):
    """Put back the "before" side of a change."""
    for k, (b, _a) in d['r'].items():
        if b is None:
            p.records.pop(k, None)
        else:
            p.records[k] = b
    for ck, cd in d['c'].items():
        c = p.cells.get(ck)
        if c is None:
            c = p.cells[ck] = {'flags': cd['meta']['flags'], 'header': cd['meta']['header'], 'refs': {}}
            if cd['meta'].get('plan'):
                c['plan'] = cd['meta']['plan']
        for rk, (b, _a) in cd['refs'].items():
            if b is None:
                c['refs'].pop(rk, None)
            else:
                c['refs'][rk] = b
        if not c['refs']:
            p.cells.pop(ck, None)


def undo_branch(db, entry_id):
    """Take back a change and every later change built on it (newest first), as one step."""
    _require_project(db)
    p = db.project
    entry = next((e for e in p.log if e.get('id') == entry_id), None)
    if not entry:
        raise EditError('That change is no longer in the list.')
    if entry.get('undone'):
        raise EditError('That change has already been undone.')
    if not entry.get('diff'):
        raise EditError('This change was made before per-change undo existed, so it can\'t be undone on its own.')
    deps = _dependents(db, entry_id)
    if not deps:
        return undo_entry(db, entry_id)
    by_id = {e['id']: e for e in p.log}
    for i in sorted([entry_id] + deps, reverse=True):
        _revert_diff(p, by_id[i]['diff'])
    for i in [entry_id] + deps:
        _set_active(p, i, False)
    text = entry['text']
    label = ('Redid: ' + text[len('Undid: '):]) if text.startswith('Undid: ') else 'Undid: ' + text
    return commit(db, '%s (and %d change%s made on top of it)' % (label, len(deps), '' if len(deps) == 1 else 's'),
                  reverts=[entry_id] + deps)


def undo_entry(db, entry_id):
    """Take back one change from the activity list, leaving later changes alone."""
    _require_project(db)
    p = db.project
    entry = next((e for e in p.log if e.get('id') == entry_id), None)
    if not entry:
        raise EditError('That change is no longer in the list.')
    if entry.get('undone'):
        raise EditError('That change has already been undone.')
    d = entry.get('diff')
    if not d:
        raise EditError('This change was made before per-change undo existed, so it can\'t be undone on its own.')
    # anything changed again since then?
    clashes = []
    for k, (_b, a) in d['r'].items():
        if p.records.get(k) != a:
            clashes.append(('r', k))
    for ck, cd in d['c'].items():
        cur = (p.cells.get(ck) or {}).get('refs', {})
        for rk, (_b, a) in cd['refs'].items():
            if cur.get(rk) != a:
                clashes.append(('c', ck, rk))
    if clashes:
        later = None
        for e in p.log:
            if e.get('id', 0) <= entry_id or e.get('undone') or not e.get('diff'):
                continue
            ed = e['diff']
            for c in clashes:
                hit = c[1] in ed['r'] if c[0] == 'r' else c[2] in ed['c'].get(c[1], {}).get('refs', {})
                if hit:
                    later = e
                    break
            if later:
                break
        if later:
            raise EditError('A later change also affects this: "%s" (%s). Undo that one first.' % (later['text'], later['t']))
        raise EditError('Something here has changed again since then, so it can\'t be undone on its own.')
    _revert_diff(p, d)
    _set_active(p, entry_id, False)
    text = entry['text']
    if text.startswith('Undid: '):
        new = commit(db, 'Redid: ' + text[len('Undid: '):], reverts=[entry_id])
    else:
        new = commit(db, 'Undid: ' + text, reverts=[entry_id])
    return new


def _encode_str(orig, value):
    enc = value.replace('\r\n', '\n').replace('\n', '\r\n').encode(ENC, 'replace')
    nul = orig.find(b'\0')
    if 0 <= nul < len(orig) - 1:          # fixed-size buffer: keep its length
        return enc[:len(orig) - 1].ljust(len(orig), b'\0')
    if orig.endswith(b'\0') or not orig:
        return enc + b'\0'
    return enc


def apply_changes(data, changes):
    subs = [[t, bytearray(d)] for t, d in iter_subrecords(data)]
    for ch in changes:
        n = int(ch['s'])
        if n >= len(subs) or subs[n][0] != ch['t']:
            raise EditError('The record changed underneath this edit. Reload it and try again.')
        d = subs[n][1]
        if ch['k'] == 'num':
            c, v = ch['c'], ch['value']
            try:
                v = float(v) if c in 'fd' else int(round(float(v)))
            except (TypeError, ValueError):
                raise EditError('"%s" is not a number.' % v)
            if c in INT_RANGES:
                lo, hi = INT_RANGES[c]
                if not lo <= v <= hi:
                    raise EditError('%s is out of range (%d to %d).' % (v, lo, hi))
            struct.pack_into('<' + c, d, int(ch['o']), v)
        else:
            subs[n][1] = bytearray(_encode_str(bytes(d), str(ch['value'])))
    return join_subs([(t, bytes(d)) for t, d in subs])


def _require_project(db):
    if not db.project:
        raise EditError('Create a mod project first.')


def _ensure_dial_copy(db, info_i):
    """INFO lines live under their topic, so the topic travels with them."""
    d = db.info_dial.get(info_i)
    if d is None:
        raise EditError('Could not find the topic this line belongs to.')
    dkey = db.recs[d][7]
    if 'DIAL|' + dkey in db.project.records:
        return
    dl = db.by_key[('DIAL', dkey)]
    w = [v for v in dl if v not in db.dead][-1]
    tag, flags, data = db.files[db.recs[w][3]].record_at(db.recs[w][4])
    db.project.set_record('DIAL', dkey, flags, data)


def edit_record(db, i, changes):
    _require_project(db)
    r = db.recs[i]
    tag, key, flags = r[0], r[7], r[6]
    if tag in ('CELL', 'LAND', 'PGRD'):
        raise EditError('Cells are edited on the World map.')
    _t, _f, data = db.files[r[3]].record_at(r[4])
    new = apply_changes(data, changes)
    if tag == 'INFO':
        _ensure_dial_copy(db, i)
    db.project.set_record(tag, key, flags, new)
    commit(db, 'Edited %s "%s"' % (tag, r[2] or r[1]))
    return db.overlay[(tag, key)]


def duplicate_record(db, i, new_id):
    _require_project(db)
    new_id = new_id.strip()
    r = db.recs[i]
    tag = r[0]
    if tag in NOT_COPYABLE:
        raise EditError('This kind of record cannot be used as a template yet.')
    if not new_id:
        raise EditError('Give the new record an ID.')
    if len(new_id.encode(ENC, 'replace')) > 31:
        raise EditError('IDs can be at most 31 characters.')
    if db.by_key.get((tag, new_id.lower())):
        raise EditError('Something with the ID "%s" already exists.' % new_id)
    _t, flags, data = db.files[r[3]].record_at(r[4])
    subs = []
    done = False
    for t, d in iter_subrecords(data):
        if t == 'NAME' and not done and tag != 'SCPT':
            d = zs(new_id)
            done = True
        elif t == 'SCHD' and tag == 'SCPT':
            d = new_id.encode(ENC, 'replace')[:31].ljust(32, b'\0') + bytes(d[32:])
        elif t == 'SCTX' and tag == 'SCPT':
            txt = bytes(d).decode(ENC, 'replace')
            txt = re.sub(r'(?im)^(\s*begin\s+)("?)[^\s"]+("?)', lambda m: m.group(1) + m.group(2) + new_id + m.group(3), txt, count=1)
            d = txt.encode(ENC, 'replace')
        subs.append((t, bytes(d)))
    db.project.set_record(tag, new_id.lower(), flags & ~0x20, join_subs(subs), created=True)
    commit(db, 'Created %s "%s" from template "%s"' % (tag, new_id, r[1]))
    return db.overlay[(tag, new_id.lower())]


def revert_record(db, i):
    _require_project(db)
    r = db.recs[i]
    tag, key = r[0], r[7]
    if tag == 'CELL':
        db.project.cells.pop(key, None)
    else:
        db.project.remove_record(tag, key)
        if tag == 'INFO':
            dk = key.split('|', 1)[0]
            if not any(k.startswith('INFO|' + dk + '|') for k in db.project.records):
                d = db.project.records.get('DIAL|' + dk)
                if d and not d.get('created'):
                    db.project.records.pop('DIAL|' + dk)
    commit(db, 'Undid changes to %s "%s"' % (tag, r[2] or r[1]))
    lst = db.by_key.get((tag, key))
    return lst[-1] if lst else None


# ---------------- cells ----------------
def _cell(db, cell_key):
    _require_project(db)
    refs, header = db.cell_refs(cell_key)
    if header is None:
        if cell_key in db.project.cells:          # a place that exists only in this mod
            return db.project.cells[cell_key], refs
        raise EditError('That cell does not exist in your load order.')
    c = db.project.cell(cell_key, header[0], header[1] & ~0x20)
    return c, refs


def _store(c, refkey, origin, idx, subs, deleted=False):
    c['refs'][refkey] = {'origin': origin, 'idx': idx, 'subs': [[t, b64(d)] for t, d in subs], 'deleted': deleted}


def move_ref(db, cell_key, refkey, pos, scale=None):
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    if len(pos) < 6:
        pos = list(pos) + list(ref_info(ref['subs'])[1][len(pos):])
    _store(c, refkey, ref['origin'], ref['idx'], set_ref_pos(ref['subs'], tuple(pos[:6]), scale))
    rid = ref_info(ref['subs'])[0]
    commit(db, 'Moved "%s" in %s' % (rid, cell_label(db, cell_key)))
    return refkey


def delete_ref(db, cell_key, refkey):
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    rid = ref_info(ref['subs'])[0]
    if ref['origin'] == db.project.plugin.lower():
        c['refs'].pop(refkey, None)      # something you placed: just remove it
    else:
        _store(c, refkey, ref['origin'], ref['idx'], ref['subs'], deleted=True)
    _drop_empty(db, cell_key)
    commit(db, 'Removed "%s" from %s' % (rid, cell_label(db, cell_key)))


def place_ref(db, cell_key, obj_id, pos, scale=1.0, cut=None, extra_subs=None, note=None):
    import mapdata
    ri = db.resolve_id(obj_id)
    if ri is None:
        raise EditError('No object called "%s".' % obj_id)
    if db.recs[ri][0] not in PLACEABLE:
        raise EditError('"%s" is a %s, which cannot be placed in the world.' % (obj_id, db.recs[ri][0]))
    pos = (list(pos) + [0.0] * 6)[:6]
    pos = [0.0 if (v is None and n > 2) else v for n, v in enumerate(pos)]
    if pos[2] is None:
        m = mapdata.cellmap(db, cell_key)
        if not m.get('exists'):
            raise EditError('There is no cell at that spot.')
        pos[2] = mapdata.surface_z(db, m['refs'], m['interior'], pos[0], pos[1],
                                   mapdata.object_bounds(db, ri), scale or 1.0, db.recs[ri][0], cut)
    c, _refs = _cell(db, cell_key)
    rk = db.project.new_ref_key()
    origin, idx = rk.rsplit('|', 1)
    subs = [('NAME', zs(obj_id))] + list(extra_subs or [])
    subs = set_ref_pos(subs, tuple(pos), scale)
    _store(c, rk, origin, int(idx), subs)
    commit(db, note or 'Placed "%s" in %s' % (obj_id, cell_label(db, cell_key)))
    return rk


def swap_ref(db, cell_key, refkey, new_id):
    """Replace a placed object with a different one, keeping its spot, turn, scale and door link."""
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    ri = db.resolve_id(new_id)
    if ri is None:
        raise EditError('No object called "%s".' % new_id)
    if db.recs[ri][0] not in PLACEABLE:
        raise EditError('"%s" can\'t be placed in the world.' % new_id)
    old = ref_info(ref['subs'])[0]
    subs = [(t, zs(db.recs[ri][1]) if t == 'NAME' else d) for t, d in ref['subs']]
    if db.recs[ri][0] != 'DOOR':
        subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
    _store(c, refkey, ref['origin'], ref['idx'], subs)
    commit(db, 'Swapped "%s" for "%s" in %s' % (old, db.recs[ri][1], cell_label(db, cell_key)))
    return refkey


def secret_ref(db, cell_key, refkey, kind='door', save=True, sound=None):
    """Turn a placed piece of scenery (a wall, a bookcase) into a hidden door or an activator that looks
    just the same: a new DOOR or ACTI record in your mod with the piece's own model, and the placed
    piece swapped for it, keeping its spot and turn. A door can then be made to lead somewhere (or just
    swing open on its hinge); an activator is for a script. One record per model is reused.
    save=False leaves the commit to the caller (one change made of several steps: mechanism.py)."""
    _require_project(db)
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    old = ref_info(ref['subs'])[0]
    ri = db.resolve_id(old)
    if ri is None:
        raise EditError('No object called "%s".' % old)
    r = db.recs[ri]
    tag = 'ACTI' if kind == 'activator' else 'DOOR'
    if r[0] == tag:
        raise EditError('It already is %s.' % ('an activator' if tag == 'ACTI' else 'a door'))
    if r[0] not in ('STAT', 'ACTI', 'DOOR', 'CONT'):
        raise EditError('Only scenery (a wall, a bookcase, a rock) can be made into one.')
    _t, _f, data = db.files[r[3]].record_at(r[4])
    model = next((zstr(d) for t, d in iter_subrecords(data) if t == 'MODL'), None)
    if not model:
        raise EditError('"%s" has no model.' % r[1])
    name = next((zstr(d) for t, d in iter_subrecords(data) if t == 'FNAM'), None) or (r[2] or '').strip()
    if not name:
        import mechanism
        name = mechanism.nice_name(r[1]) or 'Wall'
    # (one made before, for the same model and kind, is used again)
    suffix = '_hidden' if tag == 'DOOR' else '_acti'
    base = re.sub(r'_(hidden|acti)(_\d+)?$', '', r[1])          # (a door made this way, turned into an activator)
    stem = base[:31 - len(suffix)] + suffix
    new_id = db.recs[db.by_key[(tag, stem.lower())][-1]][1] if db.by_key.get((tag, stem.lower())) else None
    if new_id is None:
        from library import DOOR_SOUNDS
        new_id, n = stem, 2
        while db.resolve_id(new_id) is not None:
            new_id = '%s_%d' % (stem[:31 - 2 - len(str(n))], n)
            n += 1
        subs = [('NAME', zs(new_id)), ('MODL', zs(model)), ('FNAM', zs(name[:31]))]
        if tag == 'DOOR':
            snd = sound if sound in DOOR_SOUNDS else 'wood' if re.search(r'wood|plank|thatch', model, re.I) else 'stone'
            for sub, sid in zip(('SNAM', 'ANAM'), DOOR_SOUNDS[snd]):
                if db.resolve_id(sid) is not None:
                    subs.append((sub, zs(sid)))
        db.project.set_record(tag, new_id.lower(), 0, join_subs(subs), created=True)
        db.sync_project()
    ni = db.resolve_id(new_id)
    subs = [(t, zs(db.recs[ni][1]) if t == 'NAME' else d) for t, d in ref['subs']]
    if tag != 'DOOR':
        subs = [(t, d) for t, d in subs if t not in ('DODT', 'DNAM')]
    _store(c, refkey, ref['origin'], ref['idx'], subs)
    if save:
        commit(db, 'Made "%s" into %s "%s" in %s' % (old, 'the activator' if tag == 'ACTI' else 'the hidden door',
                                                     new_id, cell_label(db, cell_key)))
    return {'id': new_id, 'type': tag, 'ref': refkey}


def restore_ref(db, cell_key, refkey):
    _require_project(db)
    c = db.project.cells.get(cell_key)
    if c:
        c['refs'].pop(refkey, None)
    _drop_empty(db, cell_key)
    commit(db, 'Restored an object in %s' % cell_label(db, cell_key))


def _drop_empty(db, cell_key):
    c = db.project.cells.get(cell_key)
    if c is not None and not c['refs']:
        db.project.cells.pop(cell_key)


def cell_label(db, cell_key):
    lst = db.by_key.get(('CELL', cell_key))
    return db.recs[lst[-1]][1] if lst else cell_key
