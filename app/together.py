"""Building together: one mod, built live by several people from wherever they are.

One person hosts. Their Workshop runs a small session server of its own (not the Workshop itself:
it gives out only this mod and the Library files it uses, and only to someone with the invite code).
Others join with that code. Their Workshop gets a copy of the mod and from then on every change
anyone makes goes to the host and on to everyone: within a second or so it is in each person's
Workshop and, through the live link, in each person's game.

The host's copy is the one that counts. Changes are what the Workshop already records for its undo
(records and placed objects, before and after), plus a place's own settings, Lua scripts and grass.
Two people changing the same object at once: the one the host gets last stays, for everyone. Each
person's new objects are numbered from their own block, so no two can get the same number. Undo
takes back your own last change only, not other people's.

It keeps going by itself: the invite code stays the same for a mod (until a new one is made), the
host's Workshop goes back to hosting when it starts again, and someone who joined reconnects (and
catches up) when either Workshop restarts or the connection drops. Changes made meanwhile wait and go.

Reaching the host from anywhere: the invite holds every address the host's PC has, Tailscale's,
Hamachi's or ZeroTier's first, then the home network's, and the home's public address when the
router could be asked to let people in (UPnP)."""
import base64
import json
import os
import queue
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import editing
import project
from editing import EditError

PORT = 8790
BLOCK = 2_000_000                 # numbers for placed objects per person (the game counts to 16.7 million)
LIB = ('meshes', 'textures', 'icons', 'sound')
SAFE_FILE = re.compile(r'^(meshes|textures|icons|sound)/wslib/[A-Za-z0-9_ ./()-]+$')
PROTOCOL = 2                      # (Workshops that build together must speak the same)
FEED = 30

S = {'role': None, 'applying': False, 'error': '', 'members': {}, 'seq': 0, 'feed': []}


def active():
    return S['role'] is not None


def app_version():
    try:
        import helpinfo
        return helpinfo.version()
    except Exception:
        return '?'


def _feed(who, text):
    S['feed'].append({'who': who, 'text': text, 't': time.time(), 'n': len(S['feed']) and S['feed'][-1]['n'] + 1 or 1})
    del S['feed'][:-FEED]


# ------------------------------------------------------------------ changes
def delta(before, after):
    """What a change did, to send to the others: the undo's record and object changes, and a place's
    own settings, the Lua scripts and grass when those changed. None when nothing did."""
    d = project.state_diff(before, after) or {'r': {}, 'c': {}}
    b, a = json.loads(before), json.loads(after)
    for ck in set(b['cells']) | set(a['cells']):
        bc, ac = b['cells'].get(ck), a['cells'].get(ck)
        if bc == ac:
            continue
        ent = d['c'].setdefault(ck, {'meta': {}, 'refs': {}})
        if ac is None:
            ent['gone'] = True
        else:
            ent['meta'] = {k: v for k, v in ac.items() if k != 'refs'}
    if b.get('lua', []) != a.get('lua', []):
        d['lua'] = a.get('lua', [])
    bg, ag = b.get('grass', {}), a.get('grass', {})
    g = {ck: ag.get(ck) for ck in set(bg) | set(ag) if bg.get(ck) != ag.get(ck)}
    if g:
        d['grass'] = g
    return d if (d['r'] or d['c'] or 'lua' in d or 'grass' in d) else None


def keys(d):
    """Everything a change touches."""
    out = {('r', k) for k in d.get('r', {})}
    for ck, cd in d.get('c', {}).items():
        out |= {('c', ck, rk) for rk in cd.get('refs', {})}
        out.add(('m', ck))
    if 'lua' in d:
        out.add(('lua',))
    out |= {('g', ck) for ck in d.get('grass', {})}
    return out


def apply(p, d, skip=frozenset()):
    """Make someone else's change in this copy (leaving out what's in skip: things this person has
    changed since, which the host will have last)."""
    for k, (_b, a) in d.get('r', {}).items():
        if ('r', k) in skip:
            continue
        if a is None:
            p.records.pop(k, None)
        else:
            p.records[k] = a
    for ck, cd in d.get('c', {}).items():
        if cd.get('gone'):
            if ('m', ck) not in skip:
                p.cells.pop(ck, None)
            continue
        c = p.cells.get(ck)
        if c is None:
            c = p.cells[ck] = {'flags': 0, 'header': [], 'refs': {}}
        if ('m', ck) not in skip:
            for k, v in (cd.get('meta') or {}).items():
                if k not in ('refs', 'new'):
                    c[k] = v
        for rk, (_b, a) in cd.get('refs', {}).items():
            if ('c', ck, rk) in skip:
                continue
            if a is None:
                c['refs'].pop(rk, None)
            else:
                c['refs'][rk] = a
    if 'lua' in d and ('lua',) not in skip:
        p.lua = d['lua']
    for ck, v in d.get('grass', {}).items():
        if ('g', ck) in skip:
            continue
        if v is None:
            p.grass.pop(ck, None)
        else:
            p.grass[ck] = v


def _land(db, who, text):
    """Save a change that came from someone else as a step of its own (named after them), without
    sending it back out."""
    S['applying'] = True
    try:
        entry = editing.commit(db, '%s: %s' % (who, text))
        if entry is not None:
            entry['remote'] = who
    finally:
        S['applying'] = False
    _feed(who, text)


def on_commit(db, before, after, note):
    """Called by every change made here (editing.commit)."""
    if not S['role'] or S['applying'] or before is None:
        return
    d = delta(before, after)
    if not d:
        return
    text = note or 'a change'
    if S['role'] == 'host':
        _record(S['name'], 0, text, d)
    else:
        own = [None, keys(d), d]
        S['own'].append(own)
        S['outbox'].put((text, d, own))


def own_last(p):
    """The last change made here (not someone else's, not taken back): for Undo while together."""
    for e in reversed(p.log):
        # (not an "Undid ..." step itself: Undo again goes on back, as it always has)
        if e.get('diff') and not e.get('undone') and not e.get('remote') and not e.get('reverts'):
            return e
    return None


# ------------------------------------------------------------------ Library files and entries
def manifest(db):
    import library
    base = library.data_dir(db)
    out = {}
    for top in LIB:
        root = os.path.join(base, top, 'wslib')
        for d, _ds, fs in os.walk(root):
            for f in fs:
                full = os.path.join(d, f)
                rel = os.path.relpath(full, base).replace('\\', '/')
                if SAFE_FILE.match(rel) and '..' not in rel:
                    out[rel] = os.path.getsize(full)
    return out


def _file_path(db, rel):
    import library
    rel = (rel or '').replace('\\', '/')
    if not SAFE_FILE.match(rel) or '..' in rel:
        raise EditError('Not a Library file.')
    return os.path.join(library.data_dir(db), *rel.split('/'))


def _store_file(db, rel, data):
    import library
    full = _file_path(db, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as f:
        f.write(data)
    try:
        library._register(db, rel, full)
    except Exception as e:
        print('building together: file', rel, e)


def _entries():
    """This side's Library entries (what's on the Library page: names, kinds, settings)."""
    import library
    return [e for e in library._index() if e.get('file')]


def _merge_entries(theirs):
    """Library entries from the other side, for files this side now has: they show on the Library
    page here too (and can be placed and used like your own)."""
    import library
    items = library._index()
    have_files = {e.get('file') for e in items}
    have_ids = {e.get('id') for e in items}
    added = 0
    for e in theirs or []:
        if not isinstance(e, dict) or not e.get('file') or e['file'] in have_files:
            continue
        e = dict(e)
        nid, n = e.get('id') or 'item', 2
        while nid in have_ids:
            nid = '%s_%d' % (e.get('id') or 'item', n)
            n += 1
        e['id'] = nid
        e['from'] = 'building together'
        items.append(e)
        have_files.add(e['file'])
        have_ids.add(nid)
        added += 1
    if added:
        library._save_index(items)
    return added


# ------------------------------------------------------------------ hosting
def addresses():
    """The addresses this PC can be reached at: a private network's first (Tailscale 100.x, Hamachi
    25.x, ZeroTier: reachable from anywhere), then the home network's. (Listening on one address
    only: that one.)"""
    bind = os.environ.get('WORKSHOP_COOP_BIND', '0.0.0.0')
    if bind != '0.0.0.0':
        return [bind]
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))           # (no packet is sent: it only picks the way out)
        found.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    found = {a for a in found if not a.startswith(('0.', '127.', '169.254.'))}

    def rank(a):
        b = [int(x) for x in a.split('.')]
        if b[0] == 100 and 64 <= b[1] <= 127:
            return 0                                  # Tailscale
        if b[0] in (25, 5):
            return 1                                  # Hamachi
        if a.startswith(('192.168.', '10.')) or (b[0] == 172 and 16 <= b[1] <= 31):
            return 3                                  # home network (or ZeroTier, which uses these too)
        return 2
    return sorted(found, key=lambda a: (rank(a), a))


def _host_saved(plugin):
    return (project.load_settings().get('together_host') or {}).get(plugin.lower()) or {}


def _host_save(plugin, **kw):
    s = project.load_settings()
    h = s.setdefault('together_host', {}).setdefault(plugin.lower(), {})
    h.update(kw)
    project.save_settings(s)


def invite():
    if S['role'] != 'host':
        return None
    addrs = list(dict.fromkeys(([S['public']] if S.get('public') else []) + ([S['router_ip']] if S.get('router_ip') else []) + addresses()))
    raw = json.dumps({'a': addrs, 'p': S['port'], 'k': S['secret'], 'm': S['db'].project.name, 'v': PROTOCOL})
    return 'WS-' + base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')


def _record(who, slot, text, d):
    with S['cond']:
        S['seq'] += 1
        S['changes'].append({'seq': S['seq'], 'who': who, 'slot': slot, 'text': text, 'd': d})
        if len(S['changes']) > 3000:
            del S['changes'][:-3000]
        S['cond'].notify_all()
        return S['seq']


def host(db, lock, name, port=None, public='', new_code=False):
    """Start sharing the open mod (with the same invite code as last time, unless new_code). Returns
    the status (with the invite code)."""
    if S['role']:
        raise EditError('Already building together: stop first.')
    editing._require_project(db)
    if db.state != 'ready':
        raise EditError('Wait for the Workshop to finish loading first.')
    p = db.project
    if p.name.endswith('(together)'):
        raise EditError('This is a copy of someone else\'s mod: rejoin them instead (👥 Build together → Rejoin).')
    if p.next_ref >= BLOCK:
        raise EditError('This mod has too many placed objects to share this way.')
    saved = _host_saved(p.plugin)
    secret = secrets.token_urlsafe(12) if new_code or not saved.get('secret') else saved['secret']
    S.update(role='host', db=db, lock=lock, name=(name or saved.get('name') or 'Host').strip()[:30] or 'Host', secret=secret,
             session=secrets.token_hex(6), seq=0, changes=[], members={}, slots=dict(saved.get('slots') or {}),
             high=dict(saved.get('high') or {}),
             cond=threading.Condition(), error='', public=(public if public is not None else saved.get('public', '')).strip(),
             router='asking', router_ip=None, feed=[])
    bind = os.environ.get('WORKSHOP_COOP_BIND', '0.0.0.0')
    want = int(port or saved.get('port') or PORT)
    try:
        srv = ThreadingHTTPServer((bind, want), _Handler)
    except OSError:
        srv = ThreadingHTTPServer((bind, 0), _Handler)       # (that port is taken: any free one)
    srv.daemon_threads = True
    S['server'], S['port'] = srv, srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _host_save(p.plugin, secret=secret, port=S['port'], name=S['name'], public=S['public'], slots=S['slots'])
    s = project.load_settings()
    s['together_hosting'] = {'plugin': p.plugin}
    project.save_settings(s)
    if bind == '0.0.0.0' and not os.environ.get('WORKSHOP_COOP_NO_ROUTER'):
        threading.Thread(target=_ask_router, daemon=True).start()
    else:
        S['router'] = 'off'
    return status()


def _ask_router():
    """Ask the home router to let people in on the port (UPnP), and for the home's public address."""
    try:
        import upnp
        upnp.open_port(S['port'])
        S['router_ip'] = upnp.public_address()
        S['router'] = 'open' if S['router_ip'] else 'open, but no public address (the internet provider shares it)'
        S['router_port'] = S['port']
    except Exception as e:
        S['router'] = 'no (%s)' % e


def stop(db=None, keep_auto=False):
    if S['role'] == 'host':
        try:
            S['server'].shutdown()
            S['server'].server_close()
        except Exception:
            pass
        with S['cond']:
            S['cond'].notify_all()
        if S.get('router_port'):
            try:
                import upnp
                upnp.close_port(S['router_port'])
            except Exception:
                pass
        if not keep_auto:
            s = project.load_settings()
            s.pop('together_hosting', None)
            project.save_settings(s)
    elif S['role'] == 'join':
        S['stopping'] = True
        try:
            _call('POST', '/together/leave', {'slot': S['slot']}, timeout=4)
        except Exception:
            pass
        if not keep_auto:
            s = project.load_settings()
            (s.get('together_joined') or {})['auto'] = False
            project.save_settings(s)
    S.update(role=None, members={}, error='')
    return status()


def status():
    out = {'role': S['role'], 'error': S.get('error', ''), 'seq': S.get('seq', 0), 'feed': S.get('feed', [])[-8:]}
    now = time.time()
    if S['role'] == 'host':
        out.update(invite=invite(), port=S['port'], addresses=addresses(), public=S.get('public', ''), name=S['name'],
                   router=S.get('router'), router_ip=S.get('router_ip'),
                   members=[{'name': m['name'], 'here': now - m['seen'] < 45} for k, m in sorted(S['members'].items())])
    elif S['role'] == 'join':
        out.update(name=S['name'], host=S.get('host_name', ''), mod=S.get('mod', ''), connected=now - S.get('heard', 0) < 45,
                   members=S.get('members', []), sending=S['outbox'].qsize() + S.get('inflight', 0), missing=S.get('missing', []),
                   versions=S.get('versions'))
    saved = project.load_settings().get('together_joined') or {}
    if not S['role'] and saved.get('code'):
        out['can_rejoin'] = {'mod': saved.get('mod'), 'name': saved.get('name')}
    return out


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, raw=None, ctype='application/json'):
        body = raw if raw is not None else json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ok(self):
        if S['role'] != 'host' or not secrets.compare_digest(self.headers.get('X-Together', ''), S['secret']):
            self._send({'error': 'That invite code doesn\'t work any more: ask the host for the current one.'}, 403)
            return False
        return True

    def _q(self):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}

    def do_GET(self):
        if not self._ok():
            return
        path, q = self._q()
        db = S['db']
        try:
            if path == '/together/hello':
                return self._send({'mod': db.project.name, 'v': PROTOCOL, 'app': app_version(), 'host': S['name'], 'session': S['session']})
            if path == '/together/changes':
                return self._send(_changes(int(q.get('since', 0)), int(q.get('slot', -1))))
            if path == '/together/files':
                return self._send({'files': manifest(db), 'entries': _entries()})
            if path == '/together/file':
                with open(_file_path(db, q.get('path')), 'rb') as f:
                    return self._send(None, raw=f.read(), ctype='application/octet-stream')
        except (EditError, OSError, ValueError) as e:
            return self._send({'error': str(e)}, 400)
        self._send({'error': 'No such thing.'}, 404)

    def do_POST(self):
        if not self._ok():
            return
        path, q = self._q()
        n = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(n) if n else b''
        db = S['db']
        try:
            if path == '/together/file':
                if len(raw) > 200 * 1024 * 1024:
                    raise EditError('Too big.')
                with S['lock']:
                    _store_file(db, q.get('path'), raw)
                return self._send({'ok': True})
            body = json.loads(raw or b'{}')
            if path == '/together/join':
                return self._send(_welcome(body))
            if path == '/together/push':
                return self._send(_take(body))
            if path == '/together/entries':
                return self._send({'added': _merge_entries(body.get('entries'))})
            if path == '/together/leave':
                S['members'].pop(int(body.get('slot', -1)), None)
                return self._send({'ok': True})
        except (EditError, ValueError, KeyError) as e:
            return self._send({'error': str(e)}, 400)
        self._send({'error': 'No such thing.'}, 404)


def _welcome(body):
    """Someone joining (or back again): their own number block (the same one every time, by name),
    and the mod as it is now."""
    db = S['db']
    name = (str(body.get('name') or 'Builder')).strip()[:30] or 'Builder'
    if name.lower() == S['name'].lower():
        name += ' (2)'
    slot = S['slots'].get(name)
    if slot is None:
        used = set(S['slots'].values())
        slot = next((k for k in range(1, 8) if k not in used), None)
        if slot is None:
            raise EditError('This session has had 7 people besides the host already; ask the host to make a new invite.')
        S['slots'][name] = slot
        _host_save(db.project.plugin, slots=S['slots'])
    S['members'][slot] = {'name': name, 'seen': time.time()}
    with S['lock']:
        p = db.project
        return {'slot': slot, 'you': name, 'host': S['name'], 'name': p.name, 'plugin': p.plugin, 'author': p.author,
                'description': p.description, 'state': p.state(), 'seq': S['seq'], 'session': S['session'],
                'masters': [m[0] for m in (db.proj_masters or [])], 'files': manifest(db), 'entries': _entries(),
                'block': BLOCK, 'app': app_version(), 'v': PROTOCOL, 'high': S['high'].get(str(slot), 0)}


def _take(body):
    """A change from someone who joined: made in the host's copy, then passed on to everyone."""
    db = S['db']
    slot = int(body.get('slot', -1))
    m = S['members'].get(slot)
    if not m or body.get('session') != S['session']:
        raise EditError('join again')
    m['seen'] = time.time()
    d, text = body.get('d'), str(body.get('text') or 'a change')[:200]
    with S['lock']:
        apply(db.project, d)
        _land(db, m['name'], text)
        seq = _record(m['name'], slot, text, d)
    # (the highest number this person has used, so coming back never reuses one, even of something deleted since)
    pre = db.project.plugin.lower() + '|'
    top = S['high'].get(str(slot), 0)
    for cd in (d or {}).get('c', {}).values():
        for rk in cd.get('refs', {}):
            if rk.startswith(pre) and rk[len(pre):].isdigit():
                n = int(rk[len(pre):])
                if slot * BLOCK <= n < (slot + 1) * BLOCK:
                    top = max(top, n)
    if top != S['high'].get(str(slot), 0):
        S['high'][str(slot)] = top
        _host_save(db.project.plugin, high=S['high'])
    return {'seq': seq}


def _changes(since, slot):
    """What changed since a step, waiting a while for something new (so others see it at once)."""
    if slot in S['members']:
        S['members'][slot]['seen'] = time.time()
    oldest = S['changes'][0]['seq'] if S['changes'] else S['seq'] + 1
    with S['cond']:
        if S['seq'] <= since and S['role'] == 'host':
            S['cond'].wait(20)
    now = time.time()
    members = [{'name': S['name'], 'host': True, 'here': True}] + \
              [{'name': m['name'], 'here': now - m['seen'] < 45} for k, m in sorted(S['members'].items())]
    return {'seq': S['seq'], 'session': S['session'], 'changes': [c for c in S['changes'] if c['seq'] > since], 'members': members,
            'resync': since + 1 < oldest and since < S['seq'], 'files': len(manifest(S['db'])), 'known': slot in S['members']}


# ------------------------------------------------------------------ joining
def read_invite(code):
    code = re.sub(r'\s+', '', code or '')
    if code.upper().startswith('WS-'):
        code = code[3:]
    try:
        raw = base64.urlsafe_b64decode(code + '=' * (-len(code) % 4))
        inv = json.loads(raw.decode('utf-8'))
        assert inv['a'] and inv['p'] and inv['k']
        return inv
    except Exception:
        raise EditError('That isn\'t an invite code (it starts with WS-). Copy all of it.')


def _call(method, path, body=None, timeout=30, raw=None, base=None, secret=None):
    url = (base or S['base']) + path
    data = raw if raw is not None else (json.dumps(body).encode('utf-8') if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method, headers={'X-Together': secret or S['secret'],
                                                                           'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            got = r.read()
            return got if r.headers.get('Content-Type', '').startswith('application/octet') else json.loads(got or b'{}')
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get('error')
        except Exception:
            msg = str(e)
        raise EditError(msg or str(e))
    except (urllib.error.URLError, OSError) as e:
        raise ConnectionError(str(getattr(e, 'reason', e)))


def _reach(inv):
    """The first of the invite's addresses that answers: (base url, hello) or an error saying why not."""
    why = []
    for a in inv['a']:
        b = 'http://%s:%d' % (a, inv['p'])
        try:
            return b, _call('GET', '/together/hello', timeout=5, base=b, secret=inv['k'])
        except ConnectionError as e:
            why.append('%s: %s' % (a, e))
    raise EditError('Couldn\'t reach the host. Check that they are hosting right now (👥 shows "Hosting"). From another '
                    'network, the easy way is for both of you to install Tailscale and sign in, then the host copies the '
                    'invite code again. (Tried %s.)' % '; '.join(why[:4]))


def join(db, lock, code, name, opened, quiet=False):
    """Join someone's session: a copy of their mod (opened here as its own mod), their Library files,
    then live from here on. opened(path) opens the mod file (and reloads)."""
    if S['role']:
        raise EditError('Already building together: stop first.')
    if db.state != 'ready':
        raise EditError('Wait for the Workshop to finish loading first.')
    inv = read_invite(code)
    if inv.get('v', 1) != PROTOCOL:
        raise EditError('The host has a different Workshop version (this one can\'t build together with it). Both of you: update to the newest Workshop.')
    base, hello = _reach(inv)
    if hello.get('v') != PROTOCOL:
        raise EditError('The host has a different Workshop version (%s; this is %s). Both of you: update to the newest Workshop.' % (hello.get('app'), app_version()))
    w = _call('POST', '/together/join', {'name': name}, base=base, secret=inv['k'], timeout=120)
    # their Library files this side hasn't got (or has a different one of), and their Library entries
    mine = manifest(db)
    for rel, size in w['files'].items():
        if mine.get(rel) != size:
            _store_file(db, rel, _call('GET', '/together/file?path=' + urllib.request.quote(rel), base=base, secret=inv['k'], timeout=300))
    _merge_entries(w.get('entries'))
    # the mod, as its own mod here (same file name in the game, so everyone's objects match up)
    for f in os.listdir(project.PROJECTS_DIR) if os.path.isdir(project.PROJECTS_DIR) else []:
        if not f.endswith('.json'):
            continue
        try:
            with open(os.path.join(project.PROJECTS_DIR, f), encoding='utf-8') as fh:
                other = json.load(fh)
        except (OSError, ValueError):
            continue
        if other.get('plugin', '').lower() == w['plugin'].lower() and not other.get('name', '').endswith('(together)'):
            raise EditError('You have a mod of your own called "%s" with the same file name (%s). Rename yours first, or ask the host to.'
                            % (other.get('name'), w['plugin']))
    st = json.loads(w['state'])
    nxt = max(_next_in_block(st, w['plugin'], w['slot'], w['block']), int(w.get('high') or 0) + 1)
    path = os.path.join(project.PROJECTS_DIR, project.safe_name(w['name'] + ' together') + '.json')
    os.makedirs(project.PROJECTS_DIR, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'name': w['name'] + ' (together)', 'plugin': w['plugin'], 'author': w['author'], 'description': w['description'],
                   'records': st['records'], 'cells': st['cells'], 'next_ref': nxt,
                   'lua': st.get('lua', []), 'grass': st.get('grass', {})}, f)
    os.replace(tmp, path)
    have = {pl['name'].lower() for pl in db.plugins}
    S.update(role='join', db=db, lock=lock, base=base, inv=inv, secret=inv['k'], slot=w['slot'], name=w.get('you') or name,
             host_name=w['host'], mod=w['name'], seq=w['seq'], session=w['session'], own=[], outbox=queue.Queue(), stopping=False,
             heard=time.time(), members=[], error='', missing=[m for m in w['masters'] if m.lower() not in have], block=w['block'],
             versions=None if w.get('app') == app_version() else {'host': w.get('app'), 'you': app_version()}, feed=[], opened=opened)
    s = project.load_settings()
    s['together_joined'] = {'code': code, 'name': name, 'mod': w['name'], 'path': path, 'auto': True}
    project.save_settings(s)
    opened(path)
    threading.Thread(target=_sender, daemon=True).start()
    threading.Thread(target=_poller, daemon=True).start()
    return status()


def _next_in_block(st, plugin, slot, block):
    """The next number for this person's new objects: after the highest of theirs already in the mod
    (coming back must never reuse one: that would replace what they placed before)."""
    lo, hi, top = slot * block, (slot + 1) * block, slot * block
    pre = plugin.lower() + '|'
    for c in st.get('cells', {}).values():
        for rk in c.get('refs', {}):
            if rk.startswith(pre):
                try:
                    n = int(rk[len(pre):])
                except ValueError:
                    continue
                if lo <= n < hi:
                    top = max(top, n)
    return top + 1


def _ready():
    db = S['db']
    while not S['stopping'] and (db.state != 'ready' or not db.project):
        time.sleep(0.5)
    p = db.project
    if p:
        nxt = _next_in_block({'cells': p.cells}, p.plugin, S['slot'], S['block'])
        if not (S['slot'] * S['block'] < p.next_ref < (S['slot'] + 1) * S['block']) or p.next_ref < nxt:
            p.next_ref = nxt                         # (in its own block, after what's there)


def _rejoin():
    """Back in after the host's Workshop restarted or the connection was lost a long while: the mod
    as the host has it now, with this side's changes that haven't got there yet made again on top."""
    db = S['db']
    base, _hello = _reach(S['inv'])
    S['base'] = base
    w = _call('POST', '/together/join', {'name': S['name']}, timeout=120)
    st = json.loads(w['state'])
    with S['lock']:
        p = db.project
        p.records, p.cells, p.lua, p.grass = st['records'], st['cells'], st.get('lua', []), st.get('grass', {})
        for seq, _k, d in S['own']:
            if seq is None:
                apply(p, d)                    # (still on its way: it stays here, and the host gets it next)
        _land(db, w['host'], 'everything since the connection came back')
    S.update(seq=w['seq'], slot=w['slot'], session=w['session'], heard=time.time())
    S['own'] = [o for o in S['own'] if o[0] is None]
    with S['lock']:
        p = db.project
        p.next_ref = max(p.next_ref, _next_in_block({'cells': p.cells}, p.plugin, S['slot'], S['block']), int(w.get('high') or 0) + 1)
    _merge_entries(w.get('entries'))


def _sender():
    """Send this side's changes to the host, in order, again and again until they get there."""
    _ready()
    while not S['stopping'] and S['role'] == 'join':
        try:
            text, d, own = S['outbox'].get(timeout=1)
        except queue.Empty:
            continue
        wait = 1
        S['inflight'] = 1
        while not S['stopping']:
            try:
                r = _call('POST', '/together/push', {'slot': S['slot'], 'session': S['session'], 'text': text, 'd': d})
                own[0] = r['seq']
                S['error'] = ''
                break
            except EditError as e:
                if 'join again' in str(e):
                    try:
                        _rejoin()
                        continue                       # (and send it again)
                    except (EditError, ConnectionError) as e2:
                        S['error'] = str(e2)
                        time.sleep(3)
                        continue
                S['error'] = 'The host didn\'t take a change: %s' % e
                break
            except ConnectionError as e:
                S['error'] = 'Can\'t reach the host right now (%s). Your changes wait and go when it\'s back.' % e
                time.sleep(wait)
                wait = min(wait * 2, 15)
        S['inflight'] = 0


def _poller():
    """Take everyone else's changes, as the host has them."""
    _ready()
    db = S['db']
    files = None
    while not S['stopping'] and S['role'] == 'join':
        try:
            r = _call('GET', '/together/changes?since=%d&slot=%d' % (S['seq'], S['slot']), timeout=40)
        except (ConnectionError, EditError) as e:
            S['error'] = 'Can\'t reach the host right now (%s). Trying again…' % e
            time.sleep(3)
            # (the host may have restarted at another address of theirs)
            try:
                S['base'], _h = _reach(S['inv'])
            except EditError:
                pass
            continue
        S['heard'] = time.time()
        S['members'] = r.get('members', [])
        if r.get('session') != S['session'] or r.get('resync') or not r.get('known', True):
            try:
                _rejoin()
            except (EditError, ConnectionError) as e:
                S['error'] = str(e)
                time.sleep(3)
            continue
        if not S['outbox'].qsize():
            S['error'] = ''
        for c in r['changes']:
            if c['seq'] <= S['seq']:
                continue
            if c['slot'] != S['slot']:
                # (what this side has changed since, the host has later: leave that as it is here)
                skip = set()
                for seq, ks, _d in S['own']:
                    if seq is None or seq > c['seq']:
                        skip |= ks
                with S['lock']:
                    apply(db.project, c['d'], skip)
                    _land(db, c['who'], c['text'])
            S['seq'] = c['seq']
        S['own'] = [o for o in S['own'] if o[0] is None or o[0] > S['seq']]
        S['seq'] = max(S['seq'], r['seq'])
        # (new Library files on either side: the host's count, or this side's own)
        now = (r.get('files'), len(manifest(db)))
        if now != files:
            _sync_files()
            files = (r.get('files'), len(manifest(db)))


def _sync_files():
    """Library files and entries: what the host has and this side hasn't comes here, and the other
    way round."""
    db = S['db']
    try:
        got = _call('GET', '/together/files')
        theirs = got['files']
        mine = manifest(db)
        for rel in theirs:
            if rel not in mine:
                _store_file(db, rel, _call('GET', '/together/file?path=' + urllib.request.quote(rel), timeout=300))
        for rel in mine:
            if rel not in theirs:
                with open(_file_path(db, rel), 'rb') as f:
                    _call('POST', '/together/file?path=' + urllib.request.quote(rel), raw=f.read(), timeout=300)
        _merge_entries(got.get('entries'))
        theirs_files = {e.get('file') for e in got.get('entries') or []}
        mine_new = [e for e in _entries() if e.get('file') not in theirs_files]
        if mine_new:
            _call('POST', '/together/entries', {'entries': mine_new})
    except (ConnectionError, EditError, OSError) as e:
        print('building together: files', e)


# ------------------------------------------------------------------ starting again by itself
def autostart(db, lock, opened):
    """When the Workshop starts: back to hosting the mod that was being hosted, or back into the
    session that was joined (when its copy is the mod open)."""
    def run():
        while db.state != 'ready' or not db.project:
            if db.state == 'error':
                return
            time.sleep(1)
        s = project.load_settings()
        try:
            h = s.get('together_hosting') or {}
            if h.get('plugin', '').lower() == db.project.plugin.lower() and not db.project.name.endswith('(together)'):
                host(db, lock, None, public=None)
                return
            j = s.get('together_joined') or {}
            if j.get('auto') and j.get('code') and os.path.normcase(j.get('path', '')) == os.path.normcase(db.project.path):
                join(db, lock, j['code'], j.get('name') or 'Builder', opened, quiet=True)
        except Exception as e:
            S['error'] = 'Couldn\'t go back to building together: %s' % e
            print('building together:', e)
    threading.Thread(target=run, daemon=True).start()
