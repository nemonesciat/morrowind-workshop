"""Getting a mod ready to share: checks (with safe fixes), a readme, a Nexus description and a zip.

Also works out which master files the mod really needs, so players without every big mod you have
installed can still use it."""
import os
import re
import struct
import time
import zipfile

import editing
from editing import EditError, commit, _require_project
from esm import ENC, iter_subrecords, zstr
from project import APP_DIR, PROJECTS_DIR, b64, set_ref_pos, ref_info, unb64

BASE_ARCHIVES = {'morrowind.bsa', 'tribunal.bsa', 'bloodmoon.bsa'}
BASE_PLUGINS = {'morrowind.esm', 'tribunal.esm', 'bloodmoon.esm'}
FRIENDLY = {'morrowind.esm': 'Morrowind', 'tribunal.esm': 'Tribunal', 'bloodmoon.esm': 'Bloodmoon',
            'tamriel_data.esm': 'Tamriel Data', 'tr_mainland.esm': 'Tamriel Rebuilt',
            'sky_main.esm': 'Skyrim: Home of the Nords', 'cyr_main.esm': 'Project Cyrodiil',
            'oaab_data.esm': 'OAAB Data'}
# subrecords that hold the ID of something else (by record type; '*' = any)
ID_FIELDS = {'NPCO': '*', 'NPCS': '*', 'SCRI': '*', 'XSOL': '*', 'ONAM': ('INFO',), 'INAM': ('LEVI',),
             'CNAM': ('LEVC', 'NPC_', 'INFO'), 'RNAM': ('NPC_', 'INFO'), 'ANAM': ('NPC_',),
             'BNAM': ('NPC_',), 'KNAM': ('NPC_',), 'ENAM': ('WEAP', 'ARMO', 'CLOT', 'BOOK'),
             'SNAM': ('DOOR', 'LIGH', 'REGN'), 'NAME': ('SSCR',)}


def _own_pidx(db):
    p = db.project
    return {i for i, pl in enumerate(db.plugins) if pl.get('project') or pl['name'].lower() == p.plugin.lower()}


def _versions(db, tag, key, own):
    return [v for v in db.by_key.get((tag, key), []) if v not in db.dead and db.recs[v][3] not in own]


def _definer(db, tag, key, own):
    vs = _versions(db, tag, key, own)
    return db.recs[vs[0]][3] if vs else None


def _data(db, v):
    r = db.recs[v]
    return db.files[r[3]].record_at(r[4])[2]


def _strings_in(tag, data):
    """IDs this record mentions (fields that hold IDs, plus words in script text)."""
    out = []
    for t, d in iter_subrecords(data):
        f = ID_FIELDS.get(t)
        if f and (f == '*' or tag in f):
            s = zstr(d[4:36]) if t == 'NPCO' else zstr(d[:32]) if t == 'XSOL' else zstr(d)
            if s:
                out.append(s)
        elif t == 'SCVR' and len(d) > 5:
            out.append(bytes(d[5:]).decode(ENC, 'replace'))
        elif t in ('SCTX',) or (t == 'BNAM' and tag == 'INFO'):
            out += _script_ids(bytes(d).decode(ENC, 'replace'))
    return out


def _script_ids(text):
    """IDs a script mentions: text in quotes, the thing before "->" or "." and bare words given to a command."""
    import mwscript
    out = []
    for line in text.replace('\r', '').split('\n'):
        toks = mwscript._tokens(mwscript._strip_comment(line))
        for n, (kind, val, _pos) in enumerate(toks):
            if kind == 'str':
                out.append(val.strip('"'))
            elif kind == 'word':
                low = val.lower()
                if low in mwscript.F or low in mwscript.KEYWORDS:
                    continue
                nxt = toks[n + 1][1] if n + 1 < len(toks) else ''
                prev = toks[n - 1][1].lower() if n else ''
                if nxt in ('->', '.') or (prev in mwscript.F and any(c in mwscript.F[prev]['args'] for c in 'iqSfp')):
                    out.append(val)
    return out


def _ref_id(subs):
    for t, d in subs:
        if t == 'NAME':
            return zstr(unb64(d) if isinstance(d, str) else d)
    return ''


# ------------------------------------------------------------------ masters
def lean_masters(db, with_reasons=False):
    """The masters the mod really needs: whose objects it moves or removes, whose records it changes
    (the file that first made them) and whose things it uses. Plus those files' own masters."""
    p = db.project
    own = _own_pidx(db)
    need = {}

    def add(pi, why):
        if pi is None or pi in own:
            return
        need.setdefault(pi, [])
        if with_reasons and why not in need[pi] and len(need[pi]) < 6:
            need[pi].append(why)

    seen_ids = {}

    def uses(rid, why):
        low = rid.lower()
        if low in seen_ids:
            if seen_ids[low] is not None:
                add(seen_ids[low], why)
            return
        ri = db.resolve_id(rid)
        pi = None
        if ri is not None:
            r = db.recs[ri]
            pi = _definer(db, r[0], r[7], own)
        seen_ids[low] = pi
        if pi is not None:
            add(pi, why)

    for rec in p.records.values():
        tag, key = rec['tag'], rec['key']
        label = '%s "%s"' % (tag, key.split('|')[0])
        if not rec.get('created') and tag != 'LTEX':      # (ground texture entries stand on their own)
            add(_definer(db, tag, key, own), 'you change ' + label)
        if tag == 'INFO':
            add(_definer(db, 'DIAL', key.split('|', 1)[0], own), 'you add lines to topic "%s"' % key.split('|', 1)[0])
        for s in _strings_in(tag, unb64(rec['data'])):
            uses(s, label + ' uses "%s"' % s)
    for ck, c in p.cells.items():
        if not c['refs'] and not c.get('props'):
            continue
        add(_definer(db, 'CELL', ck, own), 'you change the place "%s"' % ck)
        for r in c['refs'].values():
            if r['origin'] != p.plugin.lower():
                add(db.plugin_index(r['origin']), 'you move or remove objects in "%s"' % ck)
            else:
                rid = _ref_id(r['subs'])
                if rid:
                    uses(rid, 'you place "%s"' % rid)
    # masters of masters
    stack = list(need)
    while stack:
        pi = stack.pop()
        for m in db.plugins[pi]['header'].get('masters', []):
            mi = db.plugin_index(m.lower())
            if mi is not None and mi not in need and mi not in own:
                need[mi] = ['%s needs it' % db.plugins[pi]['name']] if with_reasons else []
                stack.append(mi)
    out = []
    for i in sorted(need):
        pl = db.plugins[i]
        size = pl['size'] or (os.path.getsize(pl['path']) if pl.get('path') else 0)
        out.append((pl['name'], size, need[i]) if with_reasons else (pl['name'], size))
    return out


# ------------------------------------------------------------------ the checks
def _project_versions(db):
    """(tag, key) -> data of the version your mod builds on (the best one not from your mod)."""
    own = _own_pidx(db)
    out = {}
    for rec in db.project.records.values():
        vs = _versions(db, rec['tag'], rec['key'], own)
        out[(rec['tag'], rec['key'])] = (vs[-1] if vs else None)
    return out, own


def _identical(db):
    base, _own = _project_versions(db)
    out = []
    for k, rec in db.project.records.items():
        if rec.get('created'):
            continue
        v = base.get((rec['tag'], rec['key']))
        if v is None:
            continue
        if bytes(_data(db, v)) == unb64(rec['data']) and (db.recs[v][6] & ~0x20) == (rec['flags'] & ~0x20):
            out.append(k)
    return out


def _tiny_moves(db):
    """Objects from other files that your mod 'changes' by almost nothing."""
    p = db.project
    out = []
    for ck, c in p.cells.items():
        orig = None
        for rk, r in c['refs'].items():
            if r['origin'] == p.plugin.lower() or r.get('deleted'):
                continue
            if orig is None:
                orig, _h = db.cell_refs(ck, without_project=True)
            o = orig.get(rk)
            if not o:
                continue
            mine = [(t, unb64(d)) for t, d in r['subs']]
            theirs = [(t, bytes(d)) for t, d in o['subs']]
            if mine == theirs:
                out.append((ck, rk, 'unchanged'))
                continue
            a, b = ref_info(mine), ref_info(theirs)
            if a[0].lower() != b[0].lower() or abs(a[2] - b[2]) > 1e-4:
                continue
            if [x for x in mine if x[0] != 'DATA'] != [x for x in theirs if x[0] != 'DATA']:
                continue
            if all(abs(a[1][n] - b[1][n]) < 0.5 for n in range(3)) and all(abs(a[1][n] - b[1][n]) < 0.002 for n in range(3, 6)):
                out.append((ck, rk, 'nudged'))
    return out


def _deleted(db):
    p = db.project
    return [(ck, rk) for ck, c in p.cells.items() for rk, r in c['refs'].items()
            if r.get('deleted') and r['origin'] != p.plugin.lower()]


def _cell_label(db, ck):
    import mapdata
    i = mapdata.cell_info(db, ck)
    if not i:
        return ck
    if i['interior']:
        return i['name'] or ck
    return '%s (%d, %d)' % (i['name'] or i['region'] or 'Outdoors', i['gx'], i['gy'])


def _missing_links(db):
    p = db.project
    out = []
    for k, rec in p.records.items():
        tag = rec['tag']
        data = unb64(rec['data'])
        for t, d in iter_subrecords(data):
            f = ID_FIELDS.get(t)
            if not f or t in ('NAME', 'SNAM') or not (f == '*' or tag in f):
                continue
            s = zstr(d[4:36]) if t == 'NPCO' else zstr(d)
            if s and db.resolve_id(s) is None and s.lower() != 'player':
                out.append({'label': '%s "%s" mentions "%s", which doesn\'t exist' % (tag, rec['key'], s)})
    for ck, c in p.cells.items():
        for rk, r in c['refs'].items():
            if r.get('deleted'):
                continue
            subs = [(t, unb64(d)) for t, d in r['subs']]
            rid = _ref_id(subs)
            if r['origin'] == p.plugin.lower() and rid and db.resolve_id(rid) is None:
                out.append({'label': 'An object in %s is "%s", which doesn\'t exist' % (_cell_label(db, ck), rid), 'cell': ck})
            for t, d in subs:
                if t == 'DNAM':
                    dest = zstr(d)
                    if dest and not db.by_key.get(('CELL', dest.lower())):
                        out.append({'label': 'A door in %s leads to "%s", which doesn\'t exist' % (_cell_label(db, ck), dest), 'cell': ck})
    return out


def _script_problems(db):
    import mwscript
    out = []
    for k, rec in db.project.records.items():
        if rec['tag'] != 'SCPT':
            continue
        text = ''
        for t, d in iter_subrecords(unb64(rec['data'])):
            if t == 'SCTX':
                text = bytes(d).decode(ENC, 'replace')
        res = mwscript.check(db, text, rec['key'])
        errs = [m for m in res['messages'] if m['sev'] == 'error']
        if errs:
            out.append({'label': 'Script "%s": %s (line %d)%s' % (rec['key'], errs[0]['text'], errs[0]['line'],
                                                                  ' and %d more' % (len(errs) - 1) if len(errs) > 1 else ''),
                        'script': rec['key']})
    return out


def _all_my_script_text(db):
    """Text of every script and dialogue result in your mod (lowercase)."""
    parts = []
    for rec in db.project.records.values():
        if rec['tag'] in ('SCPT', 'INFO'):
            for t, d in iter_subrecords(unb64(rec['data'])):
                if t == 'SCTX' or (t == 'BNAM' and rec['tag'] == 'INFO'):
                    parts.append(bytes(d).decode(ENC, 'replace').lower())
    return '\n'.join(parts)


def _quest_gaps(db):
    import dialogue
    out, topics = [], []
    text = _all_my_script_text(db)
    for rec in db.project.records.values():
        if rec['tag'] != 'DIAL' or not rec.get('created'):
            continue
        data = unb64(rec['data'])
        kind = next((d[0] for t, d in iter_subrecords(data) if t == 'DATA' and len(d)), 0)
        if kind == 4:
            try:
                q = dialogue.quest(db, rec['key'])
            except EditError:
                continue
            qid = re.escape(q['id'].lower())
            set_to = {int(m) for m in re.findall(r'(?:journal|setjournalindex)[\s,]+"?' + qid + r'"?[\s,]+(\d+)', text)}
            missing = [s['index'] for s in q['stages'] if s['index'] not in set_to]
            if missing:
                out.append({'label': 'Quest "%s": nothing in your mod moves it to stage %s' % (
                    q['title'] or q['id'], ', '.join(str(m) for m in missing[:8])), 'quest': rec['key']})
        elif kind == 0:
            word = rec['key']
            if not ('addtopic' in text and re.search(r'addtopic[\s,]+"?' + re.escape(word) + r'"?', text)):
                topics.append(word)
    # a topic shows up once any line the player hears mentions it: one pass over all dialogue text
    if topics:
        left = {t: t.encode(ENC, 'replace') for t in topics}
        for k, lst in db.by_key.items():
            if not left:
                break
            if k[0] != 'INFO' or lst[-1] in db.dead:
                continue
            low = bytes(_data(db, lst[-1])).lower()
            for t in [t for t, w in left.items() if w in low]:
                # the line's own topic doesn't count
                if not k[1].startswith(t + '|'):
                    left.pop(t)
        for t in left:
            out.append({'label': 'Topic "%s": no line mentions it and nothing adds it, so players can never ask about it' % t,
                        'topic': t})
    return out


# ----- assets
def _asset_refs(db):
    """Files your mod's own records use: (folder/rel path, what uses it)."""
    out = []
    for rec in db.project.records.values():
        tag = rec['tag']
        data = unb64(rec['data'])
        for t, d in iter_subrecords(data):
            s = zstr(d) if t in ('MODL', 'ITEX', 'FNAM', 'DATA', 'TEXT') else ''
            if t == 'MODL' and s:
                out.append(('meshes/' + s, '%s "%s"' % (tag, rec['key'])))
            elif t == 'ITEX' and s:
                out.append(('icons/' + s, '%s "%s"' % (tag, rec['key'])))
            elif t == 'FNAM' and tag == 'SOUN' and s:
                out.append(('sound/' + s, 'sound "%s"' % rec['key']))
            elif t == 'DATA' and tag == 'LTEX' and s:
                out.append(('textures/' + s, 'ground texture "%s"' % rec['key']))
            elif t == 'TEXT' and tag == 'BOOK':
                for m in re.finditer(r'(?i)<img[^>]*src="([^"]+)"', bytes(d).decode(ENC, 'replace')):
                    out.append(('bookart/' + m.group(1), 'book "%s"' % rec['key']))
    return out


_archive_cache = None


def _archive_index(db):
    """file -> archive it's in (the last archive wins, like the game)."""
    global _archive_cache
    if _archive_cache is not None and _archive_cache[0] == tuple(db.config['archives']):
        return _archive_cache[1]
    from esm import bsa_entries
    idx = {}
    for a in db.config['archives']:
        path = db._find_file(a)
        if not path:
            continue
        try:
            for name, _o, _s in bsa_entries(path):
                idx[name] = path
        except Exception:
            pass
    _archive_cache = (tuple(db.config['archives']), idx)
    return idx


def _locate(db, rel):
    """Where a file comes from: ('archive', bsa path, None, name) or ('loose', folder, full path, name), or None.
    Archives are checked first: a loose copy of a file that's also in an archive is just a replacer."""
    rel = rel.replace('\\', '/').lower()
    cands = [rel]
    base, ext = os.path.splitext(rel)
    if ext in ('.tga', '.bmp') or rel.startswith(('textures/', 'icons/', 'bookart/')):
        cands = [base + '.dds', rel, base + '.tga']
    arch = _archive_index(db)
    for c in cands:
        if c in arch:
            return ('archive', arch[c], None, c)
    for c in cands:
        for d in reversed(db.config['data']):
            fp = os.path.join(d, *c.split('/'))
            if os.path.isfile(fp):
                return ('loose', d, fp, c)
    return None


_folder_cache = {}


def _folder_has(folder, names):
    if folder not in _folder_cache:
        try:
            _folder_cache[folder] = {f.lower() for f in os.listdir(folder)}
        except OSError:
            _folder_cache[folder] = set()
    return bool(_folder_cache[folder] & names)


def _mine_dir(db):
    return os.path.dirname(editing.plugin_path(db))


def extra_dir(db):
    return os.path.join(PROJECTS_DIR, db.project.name + ' files')


def assets(db, masters=None):
    """Every file your records use, sorted into: yours (gets packed), base game, from a master, from another mod, missing."""
    masters = masters if masters is not None else [m[0].lower() for m in lean_masters(db)]
    stems = {os.path.splitext(m)[0] for m in masters}
    mine = os.path.normcase(os.path.abspath(_mine_dir(db)))
    res = {'yours': {}, 'base': 0, 'master': 0, 'other': [], 'missing': []}
    todo = list(_asset_refs(db))
    seen = set()
    while todo:
        rel, why = todo.pop()
        key = rel.lower().replace('\\', '/')
        if key in seen:
            continue
        seen.add(key)
        loc = _locate(db, key)
        if loc is None:
            res['missing'].append({'file': rel, 'by': why})
            continue
        kind, where, full, real = loc
        if kind == 'loose' and os.path.normcase(os.path.abspath(where)) == mine:
            res['yours'][real] = full
        elif kind == 'loose' and _folder_has(where, set(masters)):
            res['master'] += 1          # comes with one of the mod's masters (e.g. Tamriel Data's folder)
        elif kind == 'archive':
            stem = os.path.splitext(os.path.basename(where).lower())[0]
            if os.path.basename(where).lower() in BASE_ARCHIVES:
                res['base'] += 1
            elif any(stem == s or stem.startswith(s) or s.startswith(stem) for s in stems):
                res['master'] += 1
            else:
                res['other'].append({'file': real, 'by': why, 'from': os.path.basename(where)})
        else:
            res['other'].append({'file': real, 'by': why, 'from': where})
        # a model's textures come along too
        if real.endswith('.nif'):
            try:
                from nif import mesh_from_nif
                raw = db.meshes.read(real)
                for s in (mesh_from_nif(raw) or []) if raw else []:
                    if s.get('tex'):
                        todo.append(('textures/' + s['tex'].lower().replace('\\', '/').split('textures/')[-1], 'model ' + real))
            except Exception:
                pass
    ex = extra_dir(db)
    res['extra'] = []
    if os.path.isdir(ex):
        for root, _d, files in os.walk(ex):
            for fn in files:
                full = os.path.join(root, fn)
                res['extra'].append(os.path.relpath(full, ex).replace('\\', '/'))
    return res


def _conflicts(db, masters):
    """Other plugins in the load order (not your masters) that change the same things as your mod."""
    p = db.project
    own = _own_pidx(db)
    mset = {m.lower() for m in masters}
    by_plugin = {}

    def note(pi, what):
        name = db.plugins[pi]['name']
        if name.lower() in mset:
            return
        e = by_plugin.setdefault(name, {'plugin': name, 'count': 0, 'land': 0, 'examples': []})
        e['count'] += 1
        if what.startswith('the ground'):
            e['land'] += 1
        if len(e['examples']) < 4:
            e['examples'].append(what)

    for rec in p.records.values():
        if rec.get('created') or rec['tag'] in ('INFO', 'LTEX'):     # ground texture entries are per mod, never a clash
            continue
        for v in _versions(db, rec['tag'], rec['key'], own):
            what = ('the ground at %s' % rec['key']) if rec['tag'] == 'LAND' else '%s "%s"' % (rec['tag'], rec['key'])
            note(db.recs[v][3], what)
    for ck, c in p.cells.items():
        moved = {rk for rk, r in c['refs'].items() if r['origin'] != p.plugin.lower()}
        if not moved:
            continue
        for v in _versions(db, 'CELL', ck, own):
            pi = db.recs[v][3]
            if db.plugins[pi]['name'].lower() in mset:
                continue
            from project import split_cell
            _h, lst = split_cell(_data(db, v))
            theirs = {'%s|%d' % (db.ref_origin(pi, ref['frmr']), ref['frmr'] & 0xFFFFFF) for ref in lst}
            both = moved & theirs
            if both:
                note(pi, '%d of the same objects in %s' % (len(both), _cell_label(db, ck)))
    out = sorted(by_plugin.values(), key=lambda e: -e['count'])
    for i, e in enumerate(out):
        pi = db.plugin_index(e['plugin'].lower())
        e['after'] = pi is not None and db.proj_pidx is not None and pi > db.proj_pidx
    return out


def checks(db):
    _require_project(db)
    p = db.project
    out = []
    if not p.records and not any(c['refs'] for c in p.cells.values()) and not p.lua:
        out.append({'id': 'empty', 'sev': 'error', 'title': 'Your mod is empty', 'detail': 'Make something first.', 'items': []})
        return {'checks': out, 'masters': [], 'assets': None, 'conflicts': []}
    ms = lean_masters(db, with_reasons=True)
    names = [m[0] for m in ms]
    out.append({'id': 'masters', 'sev': 'ok', 'title': 'Needs %d other file%s to work' % (len(ms), '' if len(ms) == 1 else 's'),
                'detail': 'Only the files your mod really uses are listed as its masters. Players need these (and nothing else) installed.',
                'items': [{'label': '%s%s' % (m[0], (' (%s)' % FRIENDLY[m[0].lower()]) if m[0].lower() in FRIENDLY else ''),
                           'why': m[2][:3]} for m in ms]})
    ident = _identical(db)
    tiny = _tiny_moves(db)
    if ident or tiny:
        items = [{'label': '%s "%s" (saved but not changed)' % tuple(k.split('|', 1))} for k in ident[:30]]
        items += [{'label': 'An object in %s (%s)' % (_cell_label(db, ck), 'not changed' if why == 'unchanged' else 'moved by less than half a unit')}
                  for ck, rk, why in tiny[:30]]
        out.append({'id': 'dirty', 'sev': 'warning', 'title': '%d accidental change%s' % (len(ident) + len(tiny), '' if len(ident) + len(tiny) == 1 else 's'),
                    'detail': 'Things your mod includes without really changing them. They make your mod clash with other mods for no reason.',
                    'items': items, 'fix': {'action': 'clean', 'label': 'Remove them'}})
    else:
        out.append({'id': 'dirty', 'sev': 'ok', 'title': 'No accidental changes', 'detail': '', 'items': []})
    dl = _deleted(db)
    if dl:
        out.append({'id': 'deleted', 'sev': 'warning', 'title': '%d object%s from other files deleted' % (len(dl), '' if len(dl) == 1 else 's'),
                    'detail': 'Deleting objects that came with the game or other mods can break saved games and mods that use them. '
                              'Hiding them underground does the same for players and is safe.',
                    'items': [{'label': 'In %s' % _cell_label(db, ck), 'cell': ck} for ck, rk in dl[:30]],
                    'fix': {'action': 'hide_deleted', 'label': 'Hide them underground instead'}})
    miss = _missing_links(db)
    out.append({'id': 'links', 'sev': 'error' if miss else 'ok',
                'title': ('%d thing%s point%s to something missing' % (len(miss), '' if len(miss) == 1 else 's', 's' if len(miss) == 1 else '')) if miss else 'Everything points to things that exist',
                'detail': 'Fix these before you share the mod: the game shows errors or leaves things out.' if miss else '', 'items': miss[:40]})
    sp = _script_problems(db)
    if sp or any(r['tag'] == 'SCPT' for r in p.records.values()):
        out.append({'id': 'scripts', 'sev': 'error' if sp else 'ok', 'title': ('%d script%s with problems' % (len(sp), '' if len(sp) == 1 else 's')) if sp else 'Scripts look fine',
                    'detail': 'Open them on the Scripts page to see the details.' if sp else '', 'items': sp})
    if p.lua:
        import lua_check
        lp = []
        for s in p.lua:
            errs = [x for x in lua_check.check(s.get('text') or '', s.get('kind') or 'GLOBAL') if x['level'] == 'error']
            if errs:
                lp.append({'label': '%s: line %d, %s' % (s['name'], errs[0]['line'], errs[0]['text']) +
                           (' (+%d more)' % (len(errs) - 1) if len(errs) > 1 else '')})
            if s.get('kind') == 'CUSTOM' and not s.get('attach'):
                lp.append({'label': '%s: set to run on chosen objects, but none are chosen (it never runs)' % s['name']})
        out.append({'id': 'lua', 'sev': 'error' if lp else 'ok',
                    'title': ('%d Lua problem%s' % (len(lp), '' if len(lp) == 1 else 's')) if lp else '%d Lua script%s look fine' % (len(p.lua), '' if len(p.lua) == 1 else 's'),
                    'detail': 'Open them on the Scripts page (Lua scripts) to see the details.' if lp else
                              'They are packed with the mod, with %s listing them for the game.' % p.lua_omwscripts(), 'items': lp})
    qg = _quest_gaps(db)
    if qg:
        out.append({'id': 'quests', 'sev': 'warning', 'title': 'Quest stages and topics nobody can reach',
                    'detail': 'Maybe fine (another mod or the console might do it), but usually a missing step.', 'items': qg})
    a = assets(db, [n.lower() for n in names])
    if a['missing']:
        out.append({'id': 'missing_files', 'sev': 'error', 'title': '%d file%s missing' % (len(a['missing']), '' if len(a['missing']) == 1 else 's'),
                    'detail': 'Models, icons or textures your mod uses that aren\'t installed anywhere. Players would see a yellow "missing model" sign or nothing at all.',
                    'items': [{'label': '%s (used by %s)' % (x['file'], x['by'])} for x in a['missing'][:30]]})
    if a['other']:
        out.append({'id': 'other_files', 'sev': 'warning', 'title': '%d file%s from other mods' % (len(a['other']), '' if len(a['other']) == 1 else 's'),
                    'detail': 'Your mod uses these files, but they come from another mod that isn\'t one of its masters. '
                              'Either tell players to install that mod (the readme lists it), or include the files if their author allows it '
                              '(copy them into your mod\'s extra files folder).',
                    'items': [{'label': '%s (from %s)' % (x['file'], x['from'])} for x in a['other'][:30]]})
    nf = len(a['yours']) + len(a['extra'])
    out.append({'id': 'files', 'sev': 'ok', 'title': ('%d file%s of your own will be packed' % (nf, '' if nf == 1 else 's')) if nf else 'No files of your own to pack (the mod only uses files players already have)',
                'detail': 'Files your mod uses that are in your own data folder (%s), plus anything in your extra files folder.' % _mine_dir(db),
                'items': [{'label': f} for f in sorted(a['yours'])[:40]] + [{'label': f + ' (extra)'} for f in a['extra'][:40]]})
    cf = _conflicts(db, names)
    if cf:
        out.append({'id': 'conflicts', 'sev': 'info', 'title': 'Shares %d thing%s with %d other mod%s' % (sum(c['count'] for c in cf), '' if sum(c['count'] for c in cf) == 1 else 's', len(cf), '' if len(cf) == 1 else 's'),
                    'detail': 'If players use these together, whichever loads last wins for the shared things. Your mod should usually load after them. The readme mentions them.',
                    'items': [{'label': '%s: %s' % (c['plugin'], '; '.join(c['examples'])) + (' (loads after yours now)' if c['after'] else '')} for c in cf[:20]]})
    if not p.author or not p.description:
        out.append({'id': 'about', 'sev': 'warning', 'title': 'No ' + ('author or description' if not p.author and not p.description else 'author' if not p.author else 'description'),
                    'detail': 'Fill them in below; they go into the mod file and the readme.', 'items': []})
    return {'checks': out, 'masters': [{'name': m[0], 'why': m[2]} for m in ms], 'conflicts': cf,
            'assets': {'yours': sorted(a['yours']), 'extra': a['extra'], 'other': a['other'], 'missing': a['missing']},
            'extra_dir': extra_dir(db)}


# ------------------------------------------------------------------ fixes
def fix(db, action):
    _require_project(db)
    p = db.project
    if action == 'clean':
        ident = _identical(db)
        tiny = _tiny_moves(db)
        for k in ident:
            p.records.pop(k, None)
        for ck, rk, _w in tiny:
            p.cells[ck]['refs'].pop(rk, None)
        db.sync_project()
        commit(db, 'Release check: removed %d accidental change%s' % (len(ident) + len(tiny), '' if len(ident) + len(tiny) == 1 else 's'))
        return {'fixed': len(ident) + len(tiny)}
    if action == 'hide_deleted':
        dl = _deleted(db)
        for ck, rk in dl:
            r = p.cells[ck]['refs'][rk]
            orig, _h = db.cell_refs(ck, without_project=True)
            o = orig.get(rk)
            subs = [(t, bytes(d)) for t, d in o['subs']] if o else [(t, unb64(d)) for t, d in r['subs'] if t != 'DELE']
            rid, pos, scale, _dead = ref_info(subs)
            pos = list(pos)
            pos[2] -= 20000                      # far below the ground or floor, out of reach
            r['subs'] = [[t, b64(d)] for t, d in set_ref_pos(subs, tuple(pos))]
            r['deleted'] = False
        db.sync_project()
        commit(db, 'Release check: hid %d deleted object%s underground instead' % (len(dl), '' if len(dl) == 1 else 's'))
        return {'fixed': len(dl)}
    raise EditError('Unknown fix.')


# ------------------------------------------------------------------ what the mod adds (for the readme)
def summary(db):
    p = db.project
    own = _own_pidx(db)
    made = {}
    changed, changed_names = 0, []
    for rec in p.records.values():
        if rec['tag'] in ('INFO', 'LTEX', 'PGRD', 'DIAL', 'LAND', 'SSCR'):
            continue
        name = ''
        for t, d in iter_subrecords(unb64(rec['data'])):
            if t == 'FNAM':
                name = zstr(d)
                break
        if rec.get('created'):
            made.setdefault(rec['tag'], []).append(name or rec['key'])
        else:
            changed += 1
            if name and len(changed_names) < 10:
                changed_names.append(name)
    quests = []
    import dialogue
    for rec in p.records.values():
        if rec['tag'] == 'DIAL' and rec.get('created'):
            kind = next((d[0] for t, d in iter_subrecords(unb64(rec['data'])) if t == 'DATA' and len(d)), 0)
            if kind == 4:
                try:
                    q = dialogue.quest(db, rec['key'])
                    quests.append(q['title'] or q['id'])
                except EditError:
                    pass
    lines = sum(1 for r in p.records.values() if r['tag'] == 'INFO')
    places, new_places, entrances = [], [], []
    for ck, c in p.cells.items():
        if not c['refs']:
            continue
        is_new = not _versions(db, 'CELL', ck, own)
        (new_places if is_new else places).append(_cell_label(db, ck))
    newset = {ck for ck in p.cells if not _versions(db, 'CELL', ck, own)}
    for ck, c in p.cells.items():
        if ck in newset:
            continue
        for rk, r in c['refs'].items():
            for t, d in r['subs']:
                if t == 'DNAM':
                    dest = zstr(unb64(d))
                    if dest.lower() in newset:
                        entrances.append('%s: the door is in %s' % (dest, _cell_label(db, ck)))
    land = sum(1 for r in p.records.values() if r['tag'] == 'LAND')
    return {'made': made, 'changed': changed, 'changed_names': changed_names, 'quests': quests, 'lines': lines, 'places': places,
            'new_places': new_places, 'entrances': entrances, 'land': land}


KIND_WORDS = {'NPC_': ('character', 'characters'), 'CREA': ('creature', 'creatures'), 'WEAP': ('weapon', 'weapons'),
              'ARMO': ('piece of armor', 'pieces of armor'), 'CLOT': ('piece of clothing', 'pieces of clothing'),
              'BOOK': ('book or note', 'books and notes'), 'ALCH': ('potion', 'potions'), 'MISC': ('item', 'items'),
              'SPEL': ('spell', 'spells'), 'ENCH': None, 'CONT': ('container', 'containers'), 'SCPT': ('script', 'scripts'),
              'DOOR': None, 'STAT': None, 'DIAL': None, 'SSCR': None, 'ACTI': ('activator', 'activators'),
              'LIGH': ('light', 'lights'), 'INGR': ('ingredient', 'ingredients'), 'CELL': None}


def _adds_lines(db, s):
    out = []
    if s['new_places']:
        out.append('New places: ' + ', '.join(s['new_places'][:12]) + (' and more' if len(s['new_places']) > 12 else ''))
    for tag, names in sorted(s['made'].items()):
        w = KIND_WORDS.get(tag, ('new ' + tag, 'new ' + tag))
        if not w:
            continue
        n = len(names)
        show = [x for x in names if x][:8]
        out.append('%d new %s%s' % (n, w[0] if n == 1 else w[1], (': ' + ', '.join(show) + (' …' if n > 8 else '')) if tag in ('NPC_', 'WEAP', 'ARMO', 'CLOT', 'BOOK', 'SPEL', 'ALCH', 'MISC') else ''))
    if s['quests']:
        out.append('Quest%s: %s' % ('' if len(s['quests']) == 1 else 's', ', '.join(s['quests'])))
    if s['lines']:
        out.append('%d line%s of dialogue' % (s['lines'], '' if s['lines'] == 1 else 's'))
    if s['changed']:
        out.append('Changes %d existing thing%s%s' % (s['changed'], '' if s['changed'] == 1 else 's',
                                                    (': ' + ', '.join(s['changed_names']) + (' …' if s['changed'] > len(s['changed_names']) else '')) if s['changed_names'] else ''))
    if s['places']:
        out.append('Changes to ' + ', '.join(s['places'][:10]) + (' and more' if len(s['places']) > 10 else ''))
    if s['land']:
        out.append('Reshaped or repainted ground in %d outdoor cell%s' % (s['land'], '' if s['land'] == 1 else 's'))
    return out


def readme(db, bbcode=False):
    p = db.project
    rel = p.release
    ms = lean_masters(db)
    s = summary(db)
    cf = _conflicts(db, [m[0] for m in ms])
    ver = rel.get('version') or '1.0'
    H = (lambda t: '[size=4][b]%s[/b][/size]' % t) if bbcode else (lambda t: '== %s ==' % t)
    L = (lambda items: '[list]\n' + '\n'.join('[*]' + i for i in items) + '\n[/list]') if bbcode else (lambda items: '\n'.join('- ' + i for i in items))
    out = []
    out.append(('[size=6][b]%s[/b][/size]  version %s' if bbcode else '%s  (version %s)') % (p.name, ver))
    if p.author:
        out.append('by ' + p.author)
    out.append('')
    if p.description:
        out += [p.description, '']
    out += [H('What it adds'), L(_adds_lines(db, s) or ['(nothing yet)']), '']
    start = (rel.get('start') or '').strip()
    if start or s['entrances']:
        out += [H('Where to start'), start if start else L(s['entrances'][:8]), '']
    out += [H('Requirements'), L(['OpenMW 0.48 or newer. This mod is made for OpenMW and does not work in the original Morrowind engine.'] +
                                  ['%s%s' % (m[0], (' (%s)' % FRIENDLY[m[0].lower()]) if m[0].lower() in FRIENDLY else '') for m in ms]), '']
    plug = p.plugin
    lua = editing.lua_content(db)
    both = ('%s and %s' % (plug, lua)) if lua else plug
    out += [H('Installation'),
            L(['With Mod Organizer 2: Install a new mod from archive, pick this zip, then tick %s in the right-hand list.' % both,
               'By hand (OpenMW): unzip into its own folder, e.g. "Mods\\%s". In the OpenMW Launcher, go to Data Files > Directories, '
               'add that folder, then tick %s on the Content Files tab.' % (p.name, both),
               ('Or add these lines to openmw.cfg: data="<the folder>", content=%s (after its masters) and content=%s.' % (plug, lua)) if lua else
               'Or add these two lines to openmw.cfg: data="<the folder>" and content=%s (after its masters).' % plug]), '']
    gf = editing.grass_file(db)
    if gf:
        out += [H('Grass'),
                L(['The grass is in %s, a groundcover file: load it with groundcover=%s in openmw.cfg (not as content=), '
                   'or tick it as groundcover in your mod manager.' % (gf, gf),
                   'Groundcover must be switched on: OpenMW Launcher > Settings > Visuals > Groundcover (or in settings.cfg: '
                   '[Groundcover] enabled = true).',
                   'Without it the mod works just the same, only without the extra grass.']), '']
    out += [H('Load order'), 'Load %s after %s.' % (plug, ', '.join(m[0] for m in ms) or 'the base game')]
    if cf:
        out += ['', 'Shares some things with these mods; if you use them together, load this one after them:' if not bbcode else
                'Shares some things with these mods; if you use them together, load this one after them:',
                L(['%s (%s)' % (c['plugin'], '; '.join(c['examples'][:2])) for c in cf[:10]])]
    out.append('')
    changes = rel.get('changelog') or []
    if changes:
        out += [H('Changes'), L(['%s (%s): %s' % (c['version'], c.get('date', ''), c['notes']) for c in reversed(changes)]), '']
    if rel.get('credits'):
        out += [H('Credits'), rel['credits'], '']
    out += [H('Permissions'), rel.get('permissions') or 'Ask me before uploading this mod elsewhere or using its parts in your own mods.', '']
    out.append('Made with Morrowind Workshop.')
    return '\n'.join(out).replace('\n\n\n', '\n\n')


def save_info(db, o):
    _require_project(db)
    p = db.project
    if 'author' in o:
        p.author = (o.get('author') or '').strip()[:31]
    if 'description' in o:
        p.description = (o.get('description') or '').strip()[:255]
    for k in ('version', 'start', 'credits', 'permissions'):
        if k in o:
            p.release[k] = (o.get(k) or '').strip()
    if 'notes' in o:
        p.release['notes'] = (o.get('notes') or '').strip()
    p.save()
    if db.proj_pidx is not None:
        db.plugins[db.proj_pidx]['header'].update({'author': p.author, 'description': p.description})
    return info(db)


def info(db):
    p = db.project
    r = p.release
    return {'name': p.name, 'plugin': p.plugin, 'author': p.author, 'description': p.description,
            'version': r.get('version') or '1.0', 'start': r.get('start', ''), 'credits': r.get('credits', ''),
            'permissions': r.get('permissions', ''), 'notes': r.get('notes', ''), 'changelog': r.get('changelog', []),
            'releases': releases(db), 'extra_dir': extra_dir(db)}


def releases_dir():
    return os.path.join(APP_DIR, 'releases')


def releases(db):
    d = releases_dir()
    if not os.path.isdir(d):
        return []
    stem = db.project.name.lower()
    out = []
    for fn in sorted(os.listdir(d), key=lambda f: -os.path.getmtime(os.path.join(d, f))):
        if fn.lower().startswith(stem + '-') and fn.lower().endswith('.zip'):
            out.append({'file': fn, 'size': os.path.getsize(os.path.join(d, fn)),
                        't': time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(os.path.join(d, fn))))})
    return out


def package(db):
    """Build the plugin, then zip it with your own files and the readme."""
    _require_project(db)
    p = db.project
    ver = (p.release.get('version') or '1.0').strip()
    if not re.match(r'^[\w.\-]{1,20}$', ver):
        raise EditError('Use a simple version like 1.0 or 1.2.3.')
    res = checks(db)
    errors = [c for c in res['checks'] if c['sev'] == 'error']
    plugin = editing.plugin_path(db)
    editing.build(db)
    if getattr(p, 'pending_write', None):
        raise EditError('Your mod file is in use (is the game running?). Close the game and try again.')
    a = assets(db)
    os.makedirs(releases_dir(), exist_ok=True)
    zname = '%s-%s.zip' % (re.sub(r'[^\w\-]+', '_', p.name), ver)
    zpath = os.path.join(releases_dir(), zname)
    # this version's notes go into the changelog
    notes = (p.release.get('notes') or '').strip()
    log = [c for c in p.release.get('changelog', []) if c.get('version') != ver]
    log.append({'version': ver, 'date': time.strftime('%Y-%m-%d'), 'notes': notes or 'First release.' if not log else notes or 'Updates.'})
    p.release['changelog'] = log
    p.save()
    text = readme(db)
    tmp = zpath + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(plugin, p.plugin)
        # Lua scripts and their .omwscripts list, as the game needs them
        for rel, body in p.lua_outputs().items():
            z.writestr(rel, body)
        gf = editing.grass_file(db)
        if gf:
            import grass
            gp = grass.file_path(db)
            if os.path.isfile(gp):
                z.write(gp, gf)
        for rel, full in sorted(a['yours'].items()):
            z.write(full, rel)
        ex = extra_dir(db)
        for rel in a['extra']:
            z.write(os.path.join(ex, *rel.split('/')), rel)
        z.writestr('%s Readme.txt' % p.name, text.replace('\n', '\r\n'))
    os.replace(tmp, zpath)
    return {'zip': zpath, 'file': zname, 'size': os.path.getsize(zpath), 'files': 2 + len(a['yours']) + len(a['extra']),
            'errors': [c['title'] for c in errors], 'readme': text, 'bbcode': readme(db, bbcode=True)}


# ------------------------------------------------------------------ clean test
def clean_launch_args(db, start):
    """Arguments for OpenMW that load only the base game, your mod's masters and your mod."""
    ms = [m[0] for m in lean_masters(db)]
    want = {m.lower() for m in ms} | {db.project.plugin.lower()}
    dirs = []
    for d in db.config['data']:
        try:
            names = {f.lower() for f in os.listdir(d)}
        except OSError:
            continue
        if names & want or 'morrowind.esm' in names:
            dirs.append(d)
    mine = _mine_dir(db)
    if mine not in dirs:
        dirs.append(mine)
    archives = []
    for a in db.config['archives']:
        for d in dirs:
            if os.path.isfile(os.path.join(d, a)):
                archives.append(a)
                break
    args = ['--skip-menu', '--start', start, '--replace', 'data']
    for d in dirs:
        args += ['--data', d]
    args += ['--replace', 'fallback-archive']
    for a in archives:
        args += ['--fallback-archive', a]
    args += ['--replace', 'content']
    lc = editing.lua_content(db)
    for c in ms + [db.project.plugin] + ([lc] if lc else []):
        args += ['--content', c]
    # only the mod's own grass, none from other groundcover mods
    args += ['--replace', 'groundcover']
    gf = editing.grass_file(db)
    if gf:
        args += ['--groundcover', gf]
    return args, {'masters': ms, 'folders': dirs, 'archives': archives}
