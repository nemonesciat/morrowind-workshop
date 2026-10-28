"""How a Forge piece looks (the Forge's "Looks like", 2026-10-27): any weapon or armour piece in the load order to take
the look from, your own model from the Library, and a skin (its pictures swapped) over a piece or a whole set.

The Forge took its looks only from the game's plain pieces whose name says their material, nearest the material's
median (18 at most), and a set the plainest piece a slot: Tamriel Data's Imperial ebony and the like never came up.
Here every piece of the slot counts, from every plugin, enchanted or not (only its look is taken).

A piece's look is three things:
- its model (MODL): on the ground and in the inventory, and for a weapon in the hand too;
- its icon (ITEX);
- for armour, the parts worn on the body: each INDX (where on the body) names a BODY record for men (BNAM) and
  women (CNAM), and the BODY's MODL is the mesh worn there, made for that bone.
Taking a piece's look copies all three. Your own model replaces the first; a worn part can be your own model too
(made for its bone, as the game's are: the Workshop doesn't move it onto the body). A skin swaps textures in every
one of them: new copies of the meshes in the Library's folder and new BODY records, the game's left as they are."""
import os

import nifwrite
from esm import iter_subrecords, zstr
from project import join_subs, zs

# where on the body an armour's part is worn (the INDX of ARMO and CLOT)
PARTS = ['Head', 'Hair', 'Neck', 'Chest', 'Groin', 'Skirt', 'Right hand', 'Left hand', 'Right wrist', 'Left wrist', 'Shield',
         'Right forearm', 'Left forearm', 'Right upper arm', 'Left upper arm', 'Right foot', 'Left foot', 'Right ankle',
         'Left ankle', 'Right knee', 'Left knee', 'Right leg', 'Left leg', 'Right pauldron', 'Left pauldron', 'Weapon', 'Tail']
BASE = ('morrowind.esm', 'tribunal.esm', 'bloodmoon.esm')
_cache = {}


def _subs(db, ri):
    r = db.recs[ri]
    return [(t, bytes(d)) for t, d in iter_subrecords(db.files[r[3]].record_at(r[4])[2])]


def _all(db):
    """Every weapon and armour piece in the load order, its last version: [gearsurvey._read + src]."""
    import gearsurvey
    if _cache.get('recs') is db.recs:
        return _cache['all']
    out = []
    for (tag, _k), lst in db.by_key.items():
        if tag not in ('WEAP', 'ARMO'):
            continue
        live = [v for v in lst if v not in db.dead]
        if not live:
            continue
        it = gearsurvey._read(db, live[-1])
        if not it:
            continue
        r = db.recs[live[-1]]
        it['src'] = db.plugins[r[3]]['name']
        # (made by the base game, whatever later mod changes it: first in the list)
        it['base'] = any(db.plugins[db.recs[v][3]]['name'].lower() in BASE for v in live)
        it.pop('stats', None)
        out.append(it)
    _cache.update(recs=db.recs, all=out)
    return out


def looks(db, kind, ty, q='', limit=60):
    """The pieces of this kind and type (an armour slot, a weapon type) a Forge piece can look like, from every
    plugin: {'looks': [{'i', 'id', 'name', 'src', 'mat', 'enchanted'}], 'n'}. q: words all found in the name, ID,
    model or plugin. The base game's first, then by name."""
    words = [w for w in (q or '').lower().split() if w]
    hits = []
    for it in _all(db):
        if it['kind'] != kind or it['type'] != ty:
            continue
        hay = ' '.join((it['name'], it['id'], it['model'], it['src'])).lower()
        if all(w in hay for w in words):
            hits.append(it)
    hits.sort(key=lambda it: (0 if it['base'] else 1, (it['name'] or it['id']).lower()))
    return {'n': len(hits), 'looks': [{k: it[k] for k in ('i', 'id', 'name', 'src', 'mat', 'enchanted', 'model')} for it in hits[:limit]]}


def worn(db, ri):
    """An armour piece's parts worn on the body: [{'part', 'label', 'male', 'female', 'model'}] (model: the men's
    mesh, else the women's)."""
    out, cur = [], None
    for t, d in _subs(db, ri):
        if t == 'INDX' and d:
            cur = {'part': d[0], 'label': PARTS[d[0]] if d[0] < len(PARTS) else 'Part %d' % d[0], 'male': '', 'female': ''}
            out.append(cur)
        elif t == 'BNAM' and cur is not None:
            cur['male'] = zstr(d)
        elif t == 'CNAM' and cur is not None:
            cur['female'] = zstr(d)
    for p in out:
        p['model'] = _body_model(db, p['male']) or _body_model(db, p['female'])
    return out


def _body_model(db, bid):
    bi = db.resolve_id(bid) if bid else None
    if bi is None or db.recs[bi][0] != 'BODY':
        return ''
    return next((zstr(d) for t, d in _subs(db, bi) if t == 'MODL'), '')


def _model_of(db, ri):
    return next((zstr(d) for t, d in _subs(db, ri) if t == 'MODL'), '')


def _nif(db, model):
    return db.meshes.read('meshes/' + model.lower().replace('\\', '/')) if model else None


def textures(db, recs):
    """The pictures the pieces' models and worn parts use, for a skin: [{'name', 'path', 'n'}], n: how many of
    the pieces use it (a set's shared ones first)."""
    seen = {}
    for ri in recs:
        ri = int(ri)
        models = {_model_of(db, ri)} | {p['model'] for p in worn(db, ri)} | {_body_model(db, p['female']) for p in worn(db, ri)}
        mine = set()
        for m in models:
            raw = _nif(db, m)
            if raw:
                mine.update(t.lower().replace('/', '\\') for t in nifwrite.textures_in(raw))
        for t in mine:
            seen[t] = seen.get(t, 0) + 1
    return [{'name': t, 'path': db.meshes.texture_path(t), 'n': n} for t, n in sorted(seen.items(), key=lambda x: (-x[1], x[0]))]


def _new_nif(db, raw, stem):
    import library
    folder = os.path.join(library.data_dir(db), 'meshes', library.SUB)
    os.makedirs(folder, exist_ok=True)
    stem = library._free_name(folder, library._slug(stem), '.nif')
    full = os.path.join(folder, stem + '.nif')
    with open(full, 'wb') as f:
        f.write(raw)
    library._register(db, 'meshes/%s/%s.nif' % (library.SUB, stem), full)
    return '%s\\%s.nif' % (library.SUB, stem)


def _skinned(db, model, mapping, stem):
    """The model with its pictures swapped (a new copy in the Library's folder), or None when it has none of them."""
    raw = _nif(db, model)
    if not raw or not mapping:
        return None
    new, n = nifwrite.retexture(raw, mapping)
    return _new_nif(db, new, stem) if n else None


def _new_body(db, bid, model, new_id):
    """A copy of a BODY record with another mesh: its id."""
    import create
    bi = db.resolve_id(bid)
    r = db.recs[bi]
    _t, flags, _data = db.files[r[3]].record_at(r[4])
    rid = create.suggest_id(db, '', new_id)[:31]
    subs = [(t, zs(rid) if t == 'NAME' else zs(model) if t == 'MODL' else d) for t, d in _subs(db, bi)]
    db.project.set_record('BODY', rid.lower(), flags & ~0x20, join_subs(subs), created=True)
    db.sync_project()
    return rid


def restyle(db, item_id, own=None, worn_own=None, skin=None, icon=None):
    """A forged piece's look changed in your mod: own, a Library model for its model (and its icon, when the Library
    has one); worn_own {part (INDX): Library model} for the parts worn on the body; skin {texture: new texture}
    swapped in all of them; icon, an icon path. Saves the record (no commit: the caller folds it in). How many
    records it made or changed."""
    import library
    ri = db.resolve_id(item_id)
    if ri is None or db.recs[ri][0] not in ('WEAP', 'ARMO'):
        raise ValueError('That is not a weapon or an armour piece: %s' % item_id)
    r = db.recs[ri]
    tag, rid = r[0], r[1]
    _t, flags, _d = db.files[r[3]].record_at(r[4])
    subs = _subs(db, ri)
    mapping = {k.lower().replace('/', '\\'): v for k, v in (skin or {}).items() if v}
    n = 0
    lib = {e['id']: e for e in library._index() if e.get('type') == 'model'}
    if own:
        e = lib.get(own)
        if not e:
            raise ValueError('That model is not in the Library.')
        subs = [(t, zs(e['model']) if t == 'MODL' else d) for t, d in subs]
        if e.get('icon') and not icon:
            icon = e['icon']
    if icon:
        subs = [(t, d) for t, d in subs if t != 'ITEX']
        at = max(n_ + 1 for n_, (t, _x) in enumerate(subs) if t in ('NAME', 'MODL', 'FNAM', 'SCRI'))
        subs.insert(at, ('ITEX', zs(icon)))
    if mapping:
        m = next((zstr(d) for t, d in subs if t == 'MODL'), '')
        nm = _skinned(db, m, mapping, rid + '_gnd')
        if nm:
            subs = [(t, zs(nm) if t == 'MODL' else d) for t, d in subs]
            n += 1
    if tag == 'ARMO' and (worn_own or mapping):
        out, part, made = [], None, {}
        for t, d in subs:
            if t == 'INDX' and d:
                part = d[0]
            elif t in ('BNAM', 'CNAM') and part is not None and zstr(d):
                bid = zstr(d)
                key = (bid.lower(), part)
                if key not in made:
                    model = None
                    want = (worn_own or {}).get(str(part)) or (worn_own or {}).get(part)
                    if want:
                        e = lib.get(want)
                        if not e:
                            raise ValueError('That model is not in the Library.')
                        model = e['model']
                        if mapping:
                            model = _skinned(db, model, mapping, '%s_%d' % (rid, part)) or model
                    elif mapping:
                        model = _skinned(db, _body_model(db, bid), mapping, '%s_%d%s' % (rid, part, 'f' if t == 'CNAM' else ''))
                    made[key] = _new_body(db, bid, model, '%s_%d%s' % (rid, part, 'f' if t == 'CNAM' else '')) if model else bid
                    n += 1 if model else 0
                d = zs(made[key])
            out.append((t, d))
        subs = out
    db.project.set_record(tag, rid.lower(), flags & ~0x20, join_subs(subs), created=bool(
        db.project.records.get(tag + '|' + rid.lower(), {}).get('created')))
    db.sync_project()
    return n + 1
