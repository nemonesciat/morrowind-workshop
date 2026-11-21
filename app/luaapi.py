"""OpenMW's own description of its Lua API, as the OpenMW install carries it (resources/lua_api/openmw/*.lua: every
module, type, field and function of the version installed, written for the LDT editor). Read here, never shipped:

- check(code, aliases): every chain such as types.Actor.inventory(a):countOf or world.players[1]:teleport is followed
  link by link through those files, and a name OpenMW does not have is reported (lua_check, as a warning; the AI
  writer as a fault to put right: small models make up storage.save or self.player).
- excerpt(keys): the real functions and fields of some modules or types, with their parameters and first line of
  description, to give a model writing Lua (ai.Assistant.lua_script).

A tester asked for local models writing Lua, 2026-11-21; these files make what they write checkable."""
import os
import re

INSTALL = [None]          # the OpenMW install, set as the game data is read (database.Database._load)
PRIMITIVE = {'number', 'string', 'boolean', 'table', 'function', 'userdata', 'nil', 'any', 'bool', 'int', 'float'}
_cache = {}


def api_dir(install):
    """The folder of OpenMW's API files under an install (None when it has none: an older OpenMW, or not found)."""
    for d in ((install or ''),):
        p = os.path.join(d, 'resources', 'lua_api', 'openmw')
        if d and os.path.isdir(p):
            return p
    return None


def _ref(raw, here):
    """A type as the files write it -> 'file#Type', ('list', 'file#Type'), or None for a plain value."""
    raw = (raw or '').strip().rstrip('.,')
    m = re.match(r'^#?list<\s*(.+?)\s*>$', raw)
    if m:
        inner = _ref(m.group(1), here)
        return ('list', inner) if isinstance(inner, str) else None
    if '#' not in raw:
        return None
    mod, _, name = raw.partition('#')
    name = re.sub(r'[^\w].*$', '', name)
    if not name or name in PRIMITIVE:
        return None
    mod = mod.replace('openmw.', '') if mod else here
    return '%s#%s' % (mod, name)


def load(install):
    """{'types': {key: {'members': {name: {'kind', 'type', 'params', 'doc'}}, 'extends': [key], 'list': key}},
    'modules': {'openmw.x': key}} for this install, read once."""
    d = api_dir(install or INSTALL[0])
    if not d:
        return None
    if _cache.get('dir') == d:
        return _cache['api']
    types, modules = {}, {}

    def T(key):
        return types.setdefault(key, {'members': {}, 'extends': [], 'list': None})

    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.lua'):
            continue
        here = fn[:-4]
        try:
            text = open(os.path.join(d, fn), encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        # comment blocks: each starts at a line of three dashes
        for block in re.split(r'\n(?=---)', text):
            lines = [l[2:].strip() for l in block.splitlines() if l.startswith('--')]
            whole = ' '.join(lines)
            only = 'global' if re.search(r'Can be called only from a global script|Only available from global scripts', whole) else \
                'local' if re.search(r'Can be called only from a local script', whole) else None
            doc = next((l.lstrip('-').strip() for l in lines if l.lstrip('-').strip() and not l.lstrip('-').strip().startswith('@')), '')
            cur = None
            fn_name = fn_parent = None
            params, ret, method = [], None, False
            for l in lines:
                l = l.lstrip('-').strip()
                m = re.match(r'^@module\s+(\w+)', l)
                if m:
                    cur = '%s#%s' % (here, m.group(1))
                    T(cur)
                    modules['openmw.' + here] = cur
                    continue
                m = re.match(r'^@type\s+(\w+)', l)
                if m:
                    cur = '%s#%s' % (here, m.group(1))
                    T(cur)
                    continue
                m = re.match(r'^@extends\s+(\S+)', l)
                if m and cur:
                    e = _ref(m.group(1) if '#' in m.group(1) else '#' + m.group(1), here)
                    if isinstance(e, str):
                        T(cur)['extends'].append(e)
                    continue
                m = re.match(r'^@list\s+<\s*(\S+?)\s*>', l)
                if m and cur:
                    T(cur)['list'] = _ref(m.group(1), here)
                    continue
                # (the type is left out now and then: "@field FREE The cursor can move...")
                m = re.match(r'^@field\s+(?:\[parent=#(\w+)\]\s+)?(?:(\S*#\S+|list<\S+>)\s+)?(\w+)\s*(.*)$', l)
                if m:
                    parent = '%s#%s' % (here, m.group(1)) if m.group(1) else cur
                    if parent:
                        T(parent)['members'][m.group(3)] = {'kind': 'field', 'type': _ref(m.group(2), here),
                                                             'doc': (m.group(4) or doc)[:140]}
                    continue
                m = re.match(r'^@function\s+\[parent=#(\w+)\]\s+(\w+)', l)
                if m:
                    fn_parent, fn_name = '%s#%s' % (here, m.group(1)), m.group(2)
                    continue
                m = re.match(r'^@param\s+(?:#\S+\s+)?(\w+)', l)
                if m and fn_name:
                    if m.group(1) == 'self':
                        method = True
                    else:
                        params.append(m.group(1))
                    continue
                m = re.match(r'^@return\s+(\S+)', l)
                if m and fn_name and ret is None:
                    ret = _ref(m.group(1), here)
            if fn_name:
                T(fn_parent)['members'][fn_name] = {'kind': 'function', 'type': ret, 'params': params, 'doc': doc[:140],
                                                     'method': method, 'only': only}
    api = {'types': types, 'modules': modules}
    _cache.update(dir=d, api=api)
    return api


def members(api, key, _seen=None):
    """A type's members with those of the types it extends."""
    t = api['types'].get(key)
    if not t:
        return {}
    _seen = _seen or set()
    if key in _seen:
        return {}
    _seen.add(key)
    out = {}
    for e in t['extends']:
        out.update(members(api, e, _seen))
    out.update(t['members'])
    return out


# (module tables the files leave open: other scripts' interfaces, and the debug module's switches)
OPEN = {'openmw.interfaces', 'openmw.debug'}


def check(code, aliases, install=None, group=None):
    """[(line, text)] for names OpenMW's own files don't have, following each chain from a module's local name, and,
    given the kind of script (lua_check's group: GLOBAL, PLAYER, LOCAL...), functions its files say only a global (or
    only a local) script may call. aliases: {local name: 'openmw.x'}."""
    api = load(install)
    if not api:
        return []
    import lua_check
    toks, _probs = lua_check.tokens(code)
    toks = [t for t in toks if t[0] not in ('ws', 'nl', 'com', 'lcom')]
    out, seen = [], set()
    i = 0
    while i < len(toks):
        kind, val, line = toks[i][0], toks[i][1], toks[i][2]
        prev = toks[i - 1][1] if i else ''
        mod = aliases.get(val) if kind == 'name' and prev not in ('.', ':') else None
        if mod == 'openmw.interfaces' and i + 2 < len(toks) and toks[i + 1][1] == '.' and toks[i + 2][0] == 'name' \
                and toks[i + 2][1][:1].islower():
            # (other scripts' interfaces, the game's and mods': I.Camera, I.UI, I.Activation, always capitalised)
            msg = '%s.%s is not an interface: they are other scripts\' (I.Camera, I.UI, I.Activation...).' % (val, toks[i + 2][1])
            if (line, msg) not in seen:
                seen.add((line, msg))
                out.append((toks[i + 2][2], msg))
        start = None if not mod or mod in OPEN else (api['modules'].get(mod) or (mod if mod in api['types'] else None))
        if not start:
            i += 1
            continue
        t, chain, j = start, val, i + 1
        while j + 1 < len(toks):
            op = toks[j][1]
            if op in ('.', ':') and toks[j + 1][0] == 'name':
                name = toks[j + 1][1]
                ms = members(api, t) if isinstance(t, str) else {}
                if not ms:
                    break
                if name not in ms and isinstance(t, str) and '%s#%s' % (t.split('#')[0], name) in api['types']:
                    # (a type of the module the files forget to list under it: nearby.FIND_PATH_STATUS)
                    ms = dict(ms, **{name: {'kind': 'field', 'type': '%s#%s' % (t.split('#')[0], name)}})
                if name not in ms:
                    msg = '%s%s%s is not in OpenMW\'s Lua (its own list of functions and fields).' % (chain, op, name)
                    if (line, msg) not in seen:
                        seen.add((line, msg))
                        out.append((toks[j + 1][2], msg))
                    break
                info = ms[name]
                only = info.get('only')
                if group and only and ((only == 'global') != (group == 'GLOBAL')):
                    msg = '%s%s%s can be called only from a %s script (OpenMW\'s own list says so).' % (
                        chain, op, name, 'global' if only == 'global' else 'local')
                    if (line, msg) not in seen:
                        seen.add((line, msg))
                        out.append((toks[j + 1][2], msg))
                chain += op + name
                j += 2
                if info['kind'] == 'function':
                    if j < len(toks) and toks[j][1] == '(':
                        depth = 0
                        while j < len(toks):
                            if toks[j][1] == '(':
                                depth += 1
                            elif toks[j][1] == ')':
                                depth -= 1
                                if depth == 0:
                                    break
                            j += 1
                        j += 1
                        chain += '(…)'
                        t = info['type']
                        continue
                    break
                t = info['type']
                continue
            if op == '[':
                lst = t[1] if isinstance(t, tuple) else (api['types'].get(t, {}).get('list') if isinstance(t, str) else None)
                if not lst:
                    break
                depth = 0
                while j < len(toks):
                    if toks[j][1] == '[':
                        depth += 1
                    elif toks[j][1] == ']':
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                j += 1
                chain += '[…]'
                t = lst
                continue
            break
        i += 1          # (not past the chain: calls inside its arguments, ui.showMessage(self:getName()), are chains too)
    return out


# the engine handlers whose arguments are game objects (onActivated(actor), onActivate(object, actor)...)
OBJECT_ARGS = {'onActivated': 1, 'onActivate': 2, 'onConsume': 1, 'onPlayerAdded': 1, 'onObjectActive': 1,
               'onActorActive': 1, 'onItemActive': 1}


def aliases_of(code):
    """{local name: 'openmw.x'} from the script's require() lines, and {argument: 'core#GameObject'} for the engine
    handlers that are given game objects, so actor:teleport(...) in an object script is followed too."""
    out = {n: m for n, m in re.findall(r'\blocal\s+(\w+)\s*=\s*require\s*\(?\s*[\'"](openmw\.\w+)[\'"]', code)}
    for h, args in re.findall(r'\b(on\w+)\s*=\s*function\s*\(([^)]*)\)', code):
        for a in re.findall(r'\w+', args)[:OBJECT_ARGS.get(h, 0)]:
            out.setdefault(a, 'core#GameObject')
    return out


def excerpt(install, keys, most=60):
    install = install or INSTALL[0]
    """The real API of some modules ('openmw.x') or types ('file#Type'): one line each member, the most first."""
    api = load(install)
    if not api:
        return ''
    out = []
    for k in keys:
        key = api['modules'].get(k, k)
        owner = k.split('.', 1)[1] if k.startswith('openmw.') else key.split('#', 1)[1]
        ms = members(api, key)
        for n in sorted(ms)[:most]:
            info = ms[n]
            if info['kind'] == 'function':
                out.append('%s%s%s(%s)%s' % (owner, ':' if info.get('method') else '.', n, ', '.join(info.get('params') or []),
                                              ('  -- ' + info['doc']) if info.get('doc') else ''))
            else:
                out.append('%s.%s%s' % (owner, n, ('  -- ' + info['doc']) if info.get('doc') else ''))
    return '\n'.join(out)
