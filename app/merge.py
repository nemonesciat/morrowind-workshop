"""Merge another mod project into the open one, as one undoable change.

The other project's file is only read. Merging clears the open mod's Undo history (a backup of the
state before is made first, listed under Backups). Its records, places, scripts and grass are added to the open
mod: a record (or a script) only the other mod has is copied; one both have alike is skipped; one both
have differently is a conflict, settled per item ("mine" or "theirs", mine unless asked). A place only
the other mod has comes whole, its own objects re-keyed to this mod's plugin (the plan and the furnish
tags kept); a place both have gets the other's objects added, and a game object both mods edit is a
conflict settled the same way. Objects of the other mod that this mod had already moved or removed
(the other mod was in the load order as a master) become this mod's own, as edited here."""
import os
import shutil

from esm import iter_subrecords, zstr
from editing import EditError, cell_label, commit
from project import PROJECTS_DIR, unb64

LIB = 'wslib'


def _other_path(name):
    return os.path.join(PROJECTS_DIR, os.path.basename(name) + '.json')


def load_other(db, name):
    """The other project's JSON (read only), checked to be another mod of this install."""
    import json
    if not db.project:
        raise EditError('Open a mod first: the other mod is merged into it.')
    path = _other_path(name)
    if not os.path.isfile(path):
        raise EditError('There is no mod called "%s".' % name)
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(db.project.path)):
        raise EditError('That is the mod that is open: pick another one.')
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    d.setdefault('records', {})
    d.setdefault('cells', {})
    d.setdefault('lua', [])
    d.setdefault('grass', {})
    return d


def _same_record(a, b):
    return a.get('data') == b.get('data') and (a.get('flags', 0) & ~0x20) == (b.get('flags', 0) & ~0x20)


def _same_ref(a, b):
    return a.get('subs') == b.get('subs') and bool(a.get('deleted')) == bool(b.get('deleted'))


def _subs_key(r):
    return tuple((t, d) for t, d in (r.get('subs') or []))


def _ref_id(r):
    for t, d in r.get('subs') or []:
        if t == 'NAME':
            return zstr(unb64(d))
    return ''


def _record_name(db, tag, key):
    lst = db.by_key.get((tag, key)) or []
    for v in reversed(lst):
        if v not in db.dead and db.recs[v][2]:
            return db.recs[v][2]
    return ''


def _lib_files(other):
    """Library files (under the wslib folders) the other mod's records use: relative paths."""
    out = []
    for rec in other['records'].values():
        tag = rec['tag']
        try:
            data = unb64(rec['data'])
        except Exception:
            continue
        for t, d in iter_subrecords(data):
            if t not in ('MODL', 'ITEX', 'FNAM', 'DATA'):
                continue
            s = zstr(d)
            if LIB not in s.lower():
                continue
            folder = {'MODL': 'meshes', 'ITEX': 'icons'}.get(t)
            if t == 'FNAM' and tag == 'SOUN':
                folder = 'sound'
            elif t == 'DATA' and tag == 'LTEX':
                folder = 'textures'
            if folder:
                out.append(folder + '/' + s.replace('\\', '/').lstrip('/'))
    return sorted(set(out), key=str.lower)


def plan(db, other):
    """Everything the merge would do, and what has to be decided first."""
    p = db.project
    mine_pl, other_pl = p.plugin.lower(), other['plugin'].lower()
    out = {'name': other['name'], 'plugin': other['plugin'], 'missing_masters': [], 'orphans': [],
           'records': {'add': 0, 'same': 0, 'conflicts': []},
           'cells': {'new': [], 'shared': [], 'objects': 0, 'same': 0, 'conflicts': [], 'edited_here': 0, 'stale': 0},
           'lua': {'add': 0, 'same': 0, 'conflicts': []},
           'grass': {'cells': 0, 'items': 0}, 'files': {'present': [], 'missing': [], 'extra': []}}
    ops = {'records': {}, 'rconf': {}, 'cells': {}, 'lua': [], 'lconf': {}, 'grass': {}}

    # ----- records
    for k, r in other['records'].items():
        m = p.records.get(k)
        if m is None:
            ops['records'][k] = r
            out['records']['add'] += 1
            if not r.get('created') and not any(v not in db.dead for v in db.by_key.get((r['tag'], r['key']), [])):
                out['orphans'].append('%s "%s"' % (r['tag'], r['key'].split('|')[0]))
        elif _same_record(m, r):
            out['records']['same'] += 1
        else:
            ops['rconf'][k] = r
            out['records']['conflicts'].append({'key': 'r:' + k, 'tag': r['tag'], 'id': r['key'].split('|')[0],
                                                'name': _record_name(db, r['tag'], r['key'])})

    # ----- places
    next_ref = p.next_ref
    missing = set()
    for ck, oc in other['cells'].items():
        mc = p.cells.get(ck)
        keymap = {}                                  # the other's own refkeys -> this mod's new ones
        add, conf = {}, {}
        # the other mod's objects this mod already holds as its own, from an earlier merge of it:
        # the same object at the same place, so a second merge adds nothing twice
        # (matched by where it came from, 'src', which a merge writes on each copy; or, for copies made
        # before that was written, by the same object at the same place)
        had, had_src = {}, {}
        gone = set((mc or {}).get('gone') or [])     # merged copies this mod removed since (see merge())
        for mk, m in (mc or {}).get('refs', {}).items():
            if m.get('origin') == mine_pl:
                if m.get('src'):
                    had_src.setdefault(m['src'], mk)
                if not m.get('deleted'):
                    had.setdefault(_subs_key(m), mk)
        for rk, r in oc.get('refs', {}).items():
            origin = r['origin']
            if origin == other_pl:
                if r.get('deleted'):
                    continue                         # its own object it removed again: nothing to bring over
                src = '%s|%s' % (other_pl, rk)
                mk = had_src.get(src) or had.get(_subs_key(r))
                if mk or src in gone:
                    if mk:
                        keymap[rk] = mk
                    out['cells']['same'] += 1
                    continue
                tk = '%s|%d' % (mine_pl, next_ref)
                next_ref += 1
                keymap[rk] = tk
                add[tk] = dict(r, origin=mine_pl, idx=int(tk.rsplit('|', 1)[1]), src=src)
                continue
            if origin != mine_pl and db.plugin_index(origin) is None:
                missing.add(r['origin'])
            m = (mc or {}).get('refs', {}).get(rk)
            if m is None:
                add[rk] = r
            elif _same_ref(m, r):
                out['cells']['same'] += 1
            else:
                conf[rk] = r
                out['cells']['conflicts'].append({'key': 'c:%s|%s' % (ck, rk), 'cell': cell_label(db, ck), 'id': _ref_id(r),
                                                  'theirs': 'removed' if r.get('deleted') else 'moved',
                                                  'mine': 'removed' if m.get('deleted') else 'moved'})
        for r in add.values():
            if r.get('on') in keymap:
                r['on'] = keymap[r['on']]
        # objects of the other mod that this mod had already moved or removed: this mod's edit, on the copy;
        # and things this mod laid on the other mod's furniture follow it to its new key
        edits, retag = {}, {}
        if mc:
            for rk, m in mc['refs'].items():
                if m['origin'] == other_pl:
                    edits[rk] = keymap.get(rk)
                    if keymap.get(rk):
                        out['cells']['edited_here'] += 1
                    else:
                        out['cells']['stale'] += 1
                elif m.get('on') in keymap:
                    retag[rk] = keymap[m['on']]
        if add or conf or edits:
            ops['cells'][ck] = {'add': add, 'conf': conf, 'edits': edits, 'retag': retag, 'other': oc}
            (out['cells']['shared'] if mc else out['cells']['new']).append(cell_label(db, ck))
            out['cells']['objects'] += len(add)
        if not mc and not any(v not in db.dead for v in db.by_key.get(('CELL', ck), [])) and not oc.get('header'):
            out['orphans'].append('the place "%s"' % ck)
    out['missing_masters'] = sorted(missing)
    # the other mod switched on in the game's load order too: the game would then show its places twice
    # (its own copy and the merged one), so the merge offers to switch it off
    content = getattr(db, 'cfg_content_all', None) or (db.config or {}).get('content', [])
    out['in_load_order'] = other_pl in [c.lower() for c in content]

    # ----- scripts and grass
    mine_lua = {s.get('name'): s for s in p.lua}
    for s in other['lua']:
        m = mine_lua.get(s.get('name'))
        if m is None:
            ops['lua'].append(s)
            out['lua']['add'] += 1
        elif (m.get('text'), m.get('kind'), m.get('attach')) == (s.get('text'), s.get('kind'), s.get('attach')):
            out['lua']['same'] += 1
        else:
            ops['lconf'][s['name']] = s
            out['lua']['conflicts'].append({'key': 'l:' + s['name'], 'name': s['name']})
    for ck, items in other['grass'].items():
        have = p.grass.get(ck) or []
        new = [g for g in items if g not in have]
        if new:
            ops['grass'][ck] = new
            out['grass']['cells'] += 1
            out['grass']['items'] += len(new)

    # ----- Library files and the other mod's extra files
    import library
    data_dir = library.data_dir(db)
    for rel in _lib_files(other):
        (out['files']['present'] if os.path.isfile(os.path.join(data_dir, *rel.split('/'))) else out['files']['missing']).append(rel)
    ex_other = os.path.join(PROJECTS_DIR, other['name'] + ' files')
    ex_mine = os.path.join(PROJECTS_DIR, p.name + ' files')
    if os.path.isdir(ex_other):
        for root, _d, files in os.walk(ex_other):
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), ex_other).replace('\\', '/')
                if not os.path.isfile(os.path.join(ex_mine, *rel.split('/'))):
                    out['files']['extra'].append(rel)
    out['conflicts'] = len(out['records']['conflicts']) + len(out['cells']['conflicts']) + len(out['lua']['conflicts'])
    out['_ops'] = ops
    out['_next_ref'] = next_ref
    return out


def preview(db, name):
    pl = plan(db, load_other(db, name))
    pl.pop('_ops')
    pl.pop('_next_ref')
    return pl


def merge(db, name, resolve=None):
    """Do it: one change, one Undo. resolve: {conflict key: 'mine' | 'theirs'} (mine where not said)."""
    other = load_other(db, name)
    pl = plan(db, other)
    if pl['missing_masters']:
        raise EditError('"%s" needs %s, which is not in your load order. Add it under Load order first.' %
                        (other['name'], ', '.join(pl['missing_masters'])))
    resolve = resolve or {}
    theirs = lambda key: resolve.get(key) == 'theirs'    # noqa: E731
    p = db.project
    # the merge clears this mod's Undo history (the user's choice: simpler than carrying both mods'
    # histories), so the state before it is kept as a backup first, listed under Backups
    import editing
    editing.flush(db)
    import backups
    backups.maybe_backup(p, force=True, why='before merge')
    ops = pl['_ops']
    n_rec = n_obj = 0
    for k, r in ops['records'].items():
        p.records[k] = dict(r)
        n_rec += 1
    for k, r in ops['rconf'].items():
        if theirs('r:' + k):
            p.records[k] = dict(r, created=bool(r.get('created') or p.records[k].get('created')))
            n_rec += 1
    places = []
    for ck, o in ops['cells'].items():
        oc = o['other']
        c = p.cells.get(ck)
        if c is None:
            c = p.cells[ck] = {k: v for k, v in oc.items() if k != 'refs'}
            c['refs'] = {}
        else:
            for k in ('plan', 'props'):
                if oc.get(k) and not c.get(k):
                    c[k] = oc[k]
        for rk, r in o['add'].items():
            c['refs'][rk] = r
            n_obj += 1
        for rk, r in o['conf'].items():
            if theirs('c:%s|%s' % (ck, rk)):
                c['refs'][rk] = r
                n_obj += 1
        for rk, nk in o['retag'].items():
            if rk in c['refs']:
                c['refs'][rk] = dict(c['refs'][rk], on=nk)
        for rk, nk in o['edits'].items():
            m = c['refs'].pop(rk, None)
            if not m or not nk or nk not in c['refs']:
                continue
            if m.get('deleted'):
                gone_ = c['refs'].pop(nk, None)
                n_obj -= 1
                if gone_ and gone_.get('src'):
                    # remembered, so a later merge of the same mod doesn't bring the object back
                    c.setdefault('gone', []).append(gone_['src'])
            else:
                c['refs'][nk].update({'subs': m['subs'], 'deleted': False})
        if not c['refs'] and not c.get('props'):
            p.cells.pop(ck, None)
        else:
            places.append(ck)
    p.next_ref = max(p.next_ref, pl['_next_ref'])
    n_lua = 0
    for s in ops['lua']:
        p.lua.append(dict(s))
        n_lua += 1
    for name_, s in ops['lconf'].items():
        if theirs('l:' + name_):
            p.lua = [dict(s) if x.get('name') == name_ else x for x in p.lua]
            n_lua += 1
    n_grass = 0
    for ck, items in ops['grass'].items():
        p.grass.setdefault(ck, []).extend(items)
        n_grass += len(items)
    # the other mod's extra files (readme pictures and the like): what this mod lacks
    copied = []
    ex_other = os.path.join(PROJECTS_DIR, other['name'] + ' files')
    ex_mine = os.path.join(PROJECTS_DIR, p.name + ' files')
    for rel in pl['files']['extra']:
        try:
            dst = os.path.join(ex_mine, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(ex_other, *rel.split('/')), dst)
            copied.append(rel)
        except OSError as e:
            print('could not copy', rel, e)
    bits = ['{:,} record{}'.format(n_rec, '' if n_rec == 1 else 's'),
            '{:,} place{}'.format(len(places), '' if len(places) == 1 else 's'),
            '{:,} object{}'.format(n_obj, '' if n_obj == 1 else 's')]
    if n_lua:
        bits.append('%d script%s' % (n_lua, '' if n_lua == 1 else 's'))
    if n_grass:
        bits.append('grass in %d place%s' % (len(ops['grass']), '' if len(ops['grass']) == 1 else 's'))
    note = 'Merged %s into %s: %s' % (other['name'], p.name, ', '.join(bits))
    commit(db, note)
    p.undo_stack = []                      # (Undo starts afresh after a merge; the backup holds the state before)
    for e in p.log:
        e.pop('diff', None)                # (and the per-change undo of earlier changes goes with it)
    return {'ok': True, 'note': note, 'plugin': other['plugin'], 'in_load_order': pl['in_load_order'],
            'records': n_rec, 'places': len(places), 'objects': n_obj, 'lua': n_lua,
            'grass': n_grass, 'copied': copied, 'missing_files': pl['files']['missing'],
            'stale': pl['cells']['stale'], 'edited_here': pl['cells']['edited_here']}
