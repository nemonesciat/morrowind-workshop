"""The pack shelf: packs shared by other people, from places you choose, to look through and add in
one click.

A place is a folder (one on this PC, a Dropbox or Google Drive folder that syncs, a USB stick) or a
link: to one pack, to a web page or folder listing that links to packs, or to a small list (a
packs.json: {"packs": [{"name", "url", "picture", "description", "author"}]}) that anyone can put up
anywhere. Packs from links are downloaded the first time they are looked at closely, and kept."""
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile

import pack
import project
from editing import EditError

MAX = 400 * 1024 * 1024
CACHE = os.path.join(project.APP_DIR, 'cache', 'packs')
SHARED = os.path.join(project.APP_DIR, 'shared packs')     # made at first: a place to start with
PICTURES = ('preview.png', 'preview.jpg', 'preview.jpeg')


def sources():
    s = project.load_settings().get('pack_sources')
    if s is None:
        os.makedirs(SHARED, exist_ok=True)
        s = [{'kind': 'folder', 'where': SHARED, 'name': 'My shared packs folder'}]
    return s


def save_sources(lst):
    out = []
    for x in lst or []:
        where = str(x.get('where') or '').strip().strip('"')
        if not where:
            continue
        kind = 'link' if re.match(r'https?://', where, re.I) else 'folder'
        if kind == 'folder' and not os.path.isdir(where):
            raise EditError('There is no folder "%s" on this PC.' % where)
        out.append({'kind': kind, 'where': where, 'name': str(x.get('name') or '').strip()[:60]})
    s = project.load_settings()
    s['pack_sources'] = out
    project.save_settings(s)
    return out


def _direct(url):
    """A share link turned into one that gives the file itself (Dropbox, Google Drive, OneDrive)."""
    u = url.strip()
    if 'dropbox.com' in u:
        u = re.sub(r'([?&])dl=0', r'\1dl=1', u)
        if 'dl=1' not in u and 'raw=1' not in u:
            u += ('&' if '?' in u else '?') + 'dl=1'
    m = re.search(r'drive\.google\.com/file/d/([^/?#]+)', u)
    if m:
        u = 'https://drive.google.com/uc?export=download&id=' + m.group(1)
    if '1drv.ms' in u or 'onedrive.live.com' in u:
        u = u.replace('redir?', 'download?')
    return u


def _fetch(url, limit=MAX):
    req = urllib.request.Request(_direct(url), headers={'User-Agent': 'Morrowind Workshop'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(limit + 1)
            ctype = r.headers.get('Content-Type', '')
    except Exception as e:
        raise EditError('Couldn\'t get %s (%s).' % (url, getattr(e, 'reason', e)))
    if len(data) > limit:
        raise EditError('That is too big (over %d MB).' % (limit // (1024 * 1024)))
    return data, ctype


def _cached(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode('utf-8')).hexdigest()[:20] + '.wspack')


def _info(raw_or_path):
    """What a pack holds, from its pack.json: {name, author, description, made, prefabs, brushes,
    library, models, sounds, pictures, has_picture} or None if it isn't a pack."""
    try:
        z = zipfile.ZipFile(raw_or_path if isinstance(raw_or_path, str) else io.BytesIO(raw_or_path))
        man = json.loads(z.read('pack.json').decode('utf-8'))
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return None
    if man.get('format') != pack.FORMAT:
        return None
    lib = man.get('library', [])
    names = set(z.namelist())
    return {'name': man.get('name') or 'A pack', 'author': man.get('author', ''), 'description': man.get('description', ''),
            'made': man.get('made', ''), 'prefabs': [p.get('name') for p in man.get('prefabs', [])][:12],
            'brushes': [b.get('name') for b in man.get('brushes', [])][:12],
            'models': sum(1 for e in lib if e.get('type') == 'model'), 'sounds': sum(1 for e in lib if e.get('type') == 'sound'),
            'pictures': sum(1 for e in lib if e.get('type') not in ('model', 'sound')),
            'has_picture': any(p in names for p in PICTURES) or any(n.startswith('files/icons/') for n in names),
            'key': '%s|%s' % (man.get('name', ''), man.get('made', ''))}


def _installed():
    return project.load_settings().get('packs_added', {})


def browse():
    """Every pack in every place: {'sources': [...], 'packs': [{source, ref, file, size, ...info,
    added (when it was added here, if it was)}], 'problems': [...]}."""
    srcs = sources()
    added = _installed()
    out, problems = [], []
    for n, s in enumerate(srcs):
        if s['kind'] == 'folder':
            if not os.path.isdir(s['where']):
                problems.append('The folder "%s" isn\'t there any more.' % s['where'])
                continue
            for d, _ds, fs in os.walk(s['where']):
                if d[len(s['where']):].count(os.sep) > 2:
                    continue
                for f in sorted(fs):
                    if not f.lower().endswith('.wspack'):
                        continue
                    full = os.path.join(d, f)
                    info = _info(full)
                    if info:
                        out.append(dict(info, source=n, ref=full, file=f, size=os.path.getsize(full), local=True))
        else:
            try:
                out += _from_link(n, s['where'])
            except EditError as e:
                problems.append(str(e))
    for p in out:
        p['added'] = added.get(p.get('key', ''))
    return {'sources': srcs, 'packs': out, 'problems': problems, 'shared_folder': SHARED}


def _from_link(n, url):
    """The packs a link leads to (a pack itself, a list, or a page linking to packs)."""
    if url.lower().split('?')[0].endswith('.wspack'):
        return [_link_pack(n, url, {})]
    data, ctype = _fetch(url, 5 * 1024 * 1024 if not url.lower().endswith('.zip') else MAX)
    if data[:2] == b'PK':
        os.makedirs(CACHE, exist_ok=True)
        with open(_cached(url), 'wb') as f:
            f.write(data)
        return [_link_pack(n, url, {})]
    text = data.decode('utf-8', 'replace')
    try:
        lst = json.loads(text)
    except ValueError:
        lst = None
    out = []
    if isinstance(lst, dict) and isinstance(lst.get('packs'), list):
        for e in lst['packs'][:200]:
            if isinstance(e, dict) and e.get('url'):
                out.append(_link_pack(n, urllib.parse.urljoin(url, e['url']), e))
        return out
    # a web page or folder listing: every link to a .wspack on it
    for href in dict.fromkeys(re.findall(r'href=["\']([^"\']+\.wspack[^"\']*)["\']', text, re.I)):
        out.append(_link_pack(n, urllib.parse.urljoin(url, href.replace('&amp;', '&')), {}))
    if not out:
        raise EditError('No packs at %s (it needs to lead to a .wspack file, a page linking to some, or a packs.json list).' % url)
    return out


def _link_pack(n, url, listed):
    """A pack from a link: what the list says about it, and what the pack itself says once it has
    been downloaded."""
    path = _cached(url)
    info = _info(path) if os.path.exists(path) else None
    name = urllib.parse.unquote(url.split('?')[0].rsplit('/', 1)[-1])
    p = {'source': n, 'ref': url, 'file': name, 'local': bool(info), 'size': os.path.getsize(path) if info else None,
         'name': listed.get('name') or (os.path.splitext(name)[0] if name.lower().endswith('.wspack') else 'A pack'),
         'author': listed.get('author', ''), 'description': listed.get('description', ''), 'picture_url': listed.get('picture'),
         'key': None}
    if info:
        p.update({k: v for k, v in info.items() if v or k not in p})
    return p


def _raw(source, ref):
    srcs = sources()
    try:
        s = srcs[int(source)]
    except (ValueError, IndexError):
        raise EditError('That place isn\'t in the list any more.')
    if s['kind'] == 'folder':
        full = os.path.abspath(ref)
        if not full.lower().startswith(os.path.abspath(s['where']).lower()) or not os.path.isfile(full):
            raise EditError('That pack isn\'t there any more.')
        with open(full, 'rb') as f:
            return f.read()
    path = _cached(ref)
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    data, _c = _fetch(ref)
    if data[:2] != b'PK':
        raise EditError('That link didn\'t give a pack.')
    os.makedirs(CACHE, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return data


def look(source, ref):
    """A pack looked at closely (downloaded first if it comes from a link)."""
    raw = _raw(source, ref)
    info = _info(raw)
    if not info:
        raise EditError('That isn\'t a Workshop pack.')
    info['added'] = _installed().get(info['key'])
    info['size'] = len(raw)
    return info


def picture(source, ref):
    """The pack's picture (its own, or the icon of the first model in it): (bytes, type) or None."""
    raw = _raw(source, ref)
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None
    names = z.namelist()
    for p in PICTURES:
        if p in names:
            return z.read(p), 'image/png' if p.endswith('png') else 'image/jpeg'
    icons = sorted(n for n in names if n.startswith('files/icons/') and n.lower().endswith(('.png', '.tga', '.dds')))
    for n in icons:
        if n.lower().endswith('.png'):
            return z.read(n), 'image/png'
    return None


def add(db, source, ref):
    """Bring a pack in (as opening the file would), and remember that it was."""
    raw = _raw(source, ref)
    res = pack.open_pack(db, raw)
    info = _info(raw)
    if info:
        s = project.load_settings()
        s.setdefault('packs_added', {})[info['key']] = time.strftime('%Y-%m-%d')
        project.save_settings(s)
    return res


def share(data, file_name, source=None):
    """Put a pack you made straight into one of your folders (a synced one: everyone who has it sees
    it). Returns where it went."""
    srcs = [s for s in sources() if s['kind'] == 'folder']
    if not srcs:
        raise EditError('Add a folder to share into first (Browse packs → Places).')
    s = srcs[int(source or 0)] if str(source or '0').isdigit() and int(source or 0) < len(srcs) else srcs[0]
    name = re.sub(r'[^\w\- ]+', '_', file_name).strip() or 'My pack'
    dest = os.path.join(s['where'], name + '.wspack')
    k = 2
    while os.path.exists(dest):
        dest = os.path.join(s['where'], '%s (%d).wspack' % (name, k))
        k += 1
    with open(dest, 'wb') as f:
        f.write(data)
    return dest
