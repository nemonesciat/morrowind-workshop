"""Packs: prefabs, brushes and Library models and sounds in one file to share (a .wspack, which is a zip).

A pack holds what it needs: the Library models its prefabs and brushes use (with their pictures)
come along, so someone else can place them in their own mod. Objects from the game or from other
mods are named by their IDs; when opening a pack, anything the load order doesn't have is left out
and counted."""
import io
import json
import os
import re
import time
import zipfile

import groups
import library
import nifwrite
import scatter
from editing import EditError

FORMAT = 'Morrowind Workshop pack'


def _lib_textures(db, e):
    """The Library pictures a Library model uses: [(file in the data folder, texture name)]."""
    out = []
    if e.get('type') != 'model':
        return out
    raw = db.meshes.read(e['file'])
    for t in nifwrite.textures_in(raw) if raw else []:
        low = t.lower().replace('/', '\\')
        if low.startswith(library.SUB + '\\'):
            out.append(('textures/' + low.replace('\\', '/'), t))
    return out


def export(db, name, prefab_files=(), brush_ids=(), lib_ids=(), description='', author='', picture=None):
    """The bytes of a pack with these prefabs, brushes and Library entries (and every Library entry
    they use), and what it's about, who made it and a picture (png or jpeg bytes) for the pack shelf."""
    pfs = [p for p in groups.prefabs() if p['file'] in set(prefab_files)]
    brs = [b for b in scatter.load_brushes() if b['id'] in set(brush_ids)]
    want = set(lib_ids)
    for p in pfs:
        want |= {it['lib'] for it in p['items'] if it.get('lib')}
        for it in p['items']:
            e = library.entry_for_record(it['id'], db)
            if e:
                it['lib'] = e['id']
                want.add(e['id'])
    for b in brs:
        for it in b.get('items', []):
            e = library.entry(it.get('lib', '')) or library.entry_for_record(it['id'], db)
            if e:
                it['lib'] = e['id']
                want.add(e['id'])
    entries = [library.entry(i) for i in want]
    entries = [e for e in entries if e]
    if not (pfs or brs or entries):
        raise EditError('Choose something to put in the pack.')
    base = library.data_dir(db)
    buf = io.BytesIO()
    files = set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        lib_out = []
        for e in entries:
            icon = ['icons/' + e['icon'].replace('\\', '/')] if e.get('icon') else []
            for rel in [e['file']] + [r for r, _t in _lib_textures(db, e)] + icon:
                full = os.path.join(base, *rel.split('/'))
                if rel not in files and os.path.isfile(full):
                    z.write(full, 'files/' + rel)
                    files.add(rel)
            lib_out.append({k: e[k] for k in ('id', 'name', 'type', 'file', 'model', 'texture', 'sound', 'icon', 'size', 'kind',
                                               'from', 'light', 'door_sound', 'volume', 'reach') if k in e})
        if picture:
            z.writestr('preview.jpg' if picture[:2] == b'\xff\xd8' else 'preview.png', picture)
        manifest = {'format': FORMAT, 'version': 1, 'name': (name or 'My pack').strip()[:60], 'made': time.strftime('%Y-%m-%d %H:%M'),
                    'description': (description or '').strip()[:600], 'author': (author or '').strip()[:60],
                    'prefabs': [{'name': p['name'], 'items': p['items']} for p in pfs],
                    'brushes': [{'name': b['name'], 'items': b.get('items', [])} for b in brs],
                    'library': lib_out}
        z.writestr('pack.json', json.dumps(manifest, indent=1))
    return buf.getvalue()


def open_pack(db, raw):
    """Bring a pack in: its Library models and pictures, prefabs and brushes. Returns what was added
    and what had to be left out."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        man = json.loads(z.read('pack.json').decode('utf-8'))
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise EditError('That file isn\'t a Workshop pack.')
    if man.get('format') != FORMAT:
        raise EditError('That file isn\'t a Workshop pack.')
    base = library.data_dir(db)
    # 1. files, into the Library's folders under new names where a name is taken; models then point
    #    at the pictures' new names
    renamed = {}                                 # old rel path -> new rel path
    names = [n for n in z.namelist() if n.startswith('files/') and not n.endswith('/')]
    for n in sorted(names, key=lambda n: not n.startswith('files/textures/')):     # pictures first
        rel = n[len('files/'):]
        parts = rel.split('/')
        if len(parts) < 3 or parts[0] not in ('meshes', 'textures', 'sound', 'icons') or parts[1] != library.SUB or '..' in parts:
            continue
        folder = os.path.join(base, parts[0], library.SUB)
        os.makedirs(folder, exist_ok=True)
        stem, ext = os.path.splitext(parts[-1])
        stem = re.sub(r'[^a-z0-9_]+', '_', stem.lower()) or 'item'
        data = z.read(n)
        dest = os.path.join(folder, stem + ext)
        if os.path.exists(dest):
            with open(dest, 'rb') as f:
                same = f.read() == data
            if not same:
                stem = library._free_name(folder, stem, ext)
                dest = os.path.join(folder, stem + ext)
        new_rel = '%s/%s/%s%s' % (parts[0], library.SUB, stem, ext)
        if ext.lower() == '.nif':
            mapping = {}
            for old, new in renamed.items():
                if old.startswith('textures/'):
                    mapping[old[len('textures/'):].replace('/', '\\')] = new[len('textures/'):].replace('/', '\\')
            if mapping:
                data, _n = nifwrite.retexture(data, mapping)
        with open(dest, 'wb') as f:
            f.write(data)
        library._register(db, new_rel, dest)
        renamed[rel] = new_rel
    # 2. Library entries, with new ids where needed
    items = library._index()
    have = {i['id'] for i in items}
    lib_map, added_lib = {}, []
    for e in man.get('library', []):
        new_file = renamed.get(e.get('file', ''))
        if not new_file:
            continue
        nid, n = e['id'], 2
        while nid in have:
            nid = '%s_%d' % (e['id'], n)
            n += 1
        have.add(nid)
        ne = dict(e, id=nid, file=new_file, added=time.time(), **{'from': 'pack "%s"' % man.get('name', '')})
        ne.pop('records', None)
        if ne.get('type') == 'model':
            ne['model'] = new_file[len('meshes/'):].replace('/', '\\')
            if e.get('icon'):
                ic = renamed.get('icons/' + e['icon'].replace('\\', '/'))
                if ic:
                    ne['icon'] = ic[len('icons/'):].replace('/', '\\')
                else:
                    ne.pop('icon', None)
        elif ne.get('type') == 'sound':
            ne['sound'] = new_file[len('sound/'):].replace('/', '\\')
        else:
            ne['texture'] = new_file[len('textures/'):].replace('/', '\\')
        items.append(ne)
        lib_map[e['id']] = nid
        added_lib.append(ne['name'])
    library._save_index(items)
    # 3. prefabs and brushes: Library pieces point at the new entries; other objects must exist here
    missing = set()

    def fix(its):
        out = []
        for it in its:
            it = dict(it)
            if it.get('lib') in lib_map:
                it['lib'] = lib_map[it['lib']]
                out.append(it)
            elif db.resolve_id(it.get('id', '')) is not None:
                it.pop('lib', None)
                out.append(it)
            else:
                missing.add(it.get('id', '?'))
        return out
    added_pf = []
    existing = {p['name'].lower() for p in groups.prefabs()}
    for p in man.get('prefabs', []):
        its = fix(p.get('items', []))
        if not its:
            continue
        nm, n = p['name'], 2
        while nm.lower() in existing:
            nm = '%s (%d)' % (p['name'], n)
            n += 1
        existing.add(nm.lower())
        groups.save_prefab(db, nm, its, 'pack "%s"' % man.get('name', ''))
        added_pf.append(nm)
    brushes = [dict(b, items=fix(b.get('items', []))) for b in man.get('brushes', [])]
    brushes = [b for b in brushes if b['items']]
    nb, _skipped = scatter.import_brushes(db, {'brushes': brushes}) if brushes else (0, 0)
    return {'name': man.get('name', ''), 'library': added_lib, 'prefabs': added_pf, 'brushes': nb,
            'missing': sorted(missing)[:20], 'missing_count': len(missing)}
