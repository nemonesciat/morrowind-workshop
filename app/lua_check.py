"""A checker for OpenMW Lua scripts, in plain words: unfinished blocks and brackets, strings and
comments that never end, keywords that are missing (then, do, end), and the OpenMW side of
things: which openmw.* modules a kind of script may use, and engine handler names that are
misspelt (so they would silently never run)."""
import re

KEYWORDS = {'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'goto', 'if', 'in', 'local',
            'nil', 'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while'}
# openmw.* modules and the kinds of script that may use them (None: any)
MODULES = {
    'openmw.core': None, 'openmw.util': None, 'openmw.async': None, 'openmw.storage': None, 'openmw.types': None,
    'openmw.interfaces': None, 'openmw.vfs': None, 'openmw.markup': None, 'openmw.debug': None,
    'openmw.world': {'GLOBAL'},
    'openmw.self': {'PLAYER', 'LOCAL'}, 'openmw.nearby': {'PLAYER', 'LOCAL'}, 'openmw.animation': {'PLAYER', 'LOCAL'},
    'openmw.ui': {'PLAYER', 'MENU'}, 'openmw.input': {'PLAYER', 'MENU'}, 'openmw.camera': {'PLAYER'},
    'openmw.ambient': {'PLAYER', 'MENU'}, 'openmw.postprocessing': {'PLAYER'}, 'openmw.menu': {'MENU'},
    'openmw.content': {'LOAD'},             # (OpenMW 0.50: records made or changed as the game loads)
}
HANDLERS = {
    'any': {'onInit', 'onLoad', 'onSave', 'onUpdate', 'onInterfaceOverride'},
    'GLOBAL': {'onNewGame', 'onPlayerAdded', 'onObjectActive', 'onActorActive', 'onItemActive', 'onActivate', 'onNewExterior'},
    'LOCAL': {'onActive', 'onInactive', 'onActivated', 'onTeleported', 'onConsume'},
    'PLAYER': {'onActive', 'onInactive', 'onTeleported', 'onConsume', 'onKeyPress', 'onKeyRelease', 'onControllerButtonPress',
               'onControllerButtonRelease', 'onInputAction', 'onTouchPress', 'onTouchRelease', 'onTouchMove', 'onFrame',
               'onMouseButtonPress', 'onMouseButtonRelease', 'onMouseWheel', 'onQuestUpdate', 'onConsoleCommand'},
    'MENU': {'onFrame', 'onStateChanged', 'onKeyPress', 'onKeyRelease', 'onInputAction', 'onConsoleCommand'},
    'LOAD': {'onContentFilesLoaded'},
}
KIND_GROUP = {'GLOBAL': 'GLOBAL', 'PLAYER': 'PLAYER', 'MENU': 'MENU', 'LOAD': 'LOAD'}       # everything else runs on one object (local)

_TOK = re.compile(r'''
    (?P<ws>[ \t\r]+) | (?P<nl>\n) |
    (?P<lcom>--\[(?P<leq>=*)\[) | (?P<com>--[^\n]*) |
    (?P<lstr>\[(?P<seq>=*)\[) |
    (?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*') | (?P<badstr>["']) |
    (?P<num>0[xX][0-9a-fA-F.]+(?:[pP][+-]?\d+)?|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?) |
    (?P<name>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<op>\.\.\.|\.\.|==|~=|<=|>=|::|//|<<|>>|[-+*/%^#&~|<>=(){}\[\];:,.])
''', re.X)


def tokens(text):
    """[(kind, value, line)] and problems with strings or comments that never end."""
    out, probs, i, line = [], [], 0, 1
    n = len(text)
    while i < n:
        m = _TOK.match(text, i)
        if not m:
            if text[i] != '!':                    # (! is explained below, with the != it usually is)
                probs.append((line, 'A character Lua does not understand here: %r.' % text[i]))
            i += 1
            continue
        kind = m.lastgroup
        if kind in ('leq', 'seq'):
            kind = 'lcom' if m.group('lcom') else 'lstr'
        if kind == 'nl':
            line += 1
        elif kind in ('lcom', 'lstr'):
            eq = m.group('leq') if kind == 'lcom' else m.group('seq')
            close = ']' + eq + ']'
            j = text.find(close, m.end())
            if j < 0:
                probs.append((line, 'A %s that starts here never ends (it needs %s).' % (
                    'long comment' if kind == 'lcom' else 'long string', close)))
                return out, probs
            if kind == 'lstr':
                out.append(('str', text[m.end():j], line))
            line += text.count('\n', i, j + len(close))
            i = j + len(close)
            continue
        elif kind == 'badstr':
            probs.append((line, 'A text in quotes that is never closed on this line.'))
        elif kind not in ('ws', 'com'):
            out.append((kind, m.group(0), line))
        i = m.end()
    return out, probs


def check(text, kind='GLOBAL'):
    """[{line, level: error|warning, text}] for a script of this kind (GLOBAL, PLAYER, NPC, ...)."""
    group = KIND_GROUP.get(kind, 'LOCAL')
    toks, probs = tokens(text)
    out = [{'line': l, 'level': 'error', 'text': t} for l, t in probs]
    # ---- blocks: function/if/for/while/do ... end, repeat ... until, brackets
    stack = []
    pending = []                  # an if waiting for then, a for/while waiting for do
    pairs = {'(': ')', '[': ']', '{': '}'}
    for n, (k, v, line) in enumerate(toks):
        if k == 'name' and v in KEYWORDS:
            if v in ('function', 'repeat'):
                stack.append((v, line))
            elif v == 'if':
                stack.append(('if', line))
                pending.append(('then', line, len(stack)))
            elif v in ('for', 'while'):
                stack.append((v, line))
                pending.append(('do', line, len(stack)))
            elif v == 'elseif':
                if not stack or stack[-1][0] != 'if':
                    out.append({'line': line, 'level': 'error', 'text': '"elseif" without an "if" before it.'})
                pending.append(('then', line, len(stack)))
            elif v == 'else':
                if not stack or stack[-1][0] != 'if':
                    out.append({'line': line, 'level': 'error', 'text': '"else" without an "if" before it.'})
            elif v == 'then':
                if pending and pending[-1][0] == 'then':
                    pending.pop()
                else:
                    out.append({'line': line, 'level': 'error', 'text': '"then" here does not belong to an "if".'})
            elif v == 'do':
                if pending and pending[-1][0] == 'do':
                    pending.pop()
                else:
                    stack.append(('do', line))
            elif v == 'end':
                # (an "if" can hold a whole function in its condition: only the block being closed counts)
                if pending and pending[-1][2] == len(stack):
                    w, pl, _d = pending.pop()
                    out.append({'line': pl, 'level': 'error', 'text': 'Missing "%s" after this %s.' % (w, 'if' if w == 'then' else 'loop')})
                while stack and stack[-1][0] in ('(', '[', '{'):
                    b, bl = stack.pop()
                    out.append({'line': bl, 'level': 'error', 'text': 'A "%s" opened here is never closed with "%s".' % (b, pairs[b])})
                if not stack or stack[-1][0] == 'repeat':
                    out.append({'line': line, 'level': 'error', 'text': 'An "end" with nothing to end (one too many?).'})
                else:
                    stack.pop()
            elif v == 'until':
                if not stack or stack[-1][0] != 'repeat':
                    out.append({'line': line, 'level': 'error', 'text': '"until" without a "repeat".'})
                else:
                    stack.pop()
        elif k == 'op' and v in pairs:
            stack.append((v, line))
        elif k == 'op' and v in (')', ']', '}'):
            if stack and stack[-1][0] in pairs and pairs[stack[-1][0]] == v:
                stack.pop()
            else:
                out.append({'line': line, 'level': 'error', 'text': 'A "%s" with no matching opening bracket.' % v})
    for w, pl, _d in pending:
        out.append({'line': pl, 'level': 'error', 'text': 'Missing "%s" after this %s.' % (w, 'if' if w == 'then' else 'loop')})
    for b, bl in stack:
        what = {'(': 'bracket "("', '[': 'bracket "["', '{': 'brace "{"'}.get(b, '"%s"' % b)
        need = {'(': ')', '[': ']', '{': '}', 'repeat': 'until'}.get(b, 'end')
        out.append({'line': bl, 'level': 'error', 'text': 'The %s that starts here is never closed (it needs "%s").' % (what, need)})
    # ---- common slips from other languages
    text_ops = re.finditer(r'!=|&&|\|\|', _strip(text))
    for m in text_ops:
        line = text.count('\n', 0, m.start()) + 1
        out.append({'line': line, 'level': 'error', 'text': {'!=': 'Lua writes "not equal" as ~= (not !=).',
                                                             '&&': 'Lua writes "and" instead of &&.',
                                                             '||': 'Lua writes "or" instead of ||.'}[m.group(0)]})
    # ---- OpenMW: modules this kind of script may use
    for n, (k, v, line) in enumerate(toks):
        if k == 'name' and v == 'require' and n + 1 < len(toks):
            nx = toks[n + 1] if toks[n + 1][0] == 'str' else (toks[n + 2] if n + 2 < len(toks) and toks[n + 1][1] == '(' else None)
            if not nx or nx[0] != 'str':
                continue
            mod = nx[1].strip('\'"')
            if mod.startswith('openmw.') or mod.startswith('openmw_aux.'):
                if mod in MODULES:
                    allowed = MODULES[mod]
                    if allowed and group not in allowed:
                        where = ', '.join(sorted({'GLOBAL': 'global', 'PLAYER': 'player', 'LOCAL': 'object (NPC, creature, item...)',
                                                  'MENU': 'menu', 'LOAD': 'load (as the game loads)'}[a] for a in allowed))
                        out.append({'line': line, 'level': 'error',
                                    'text': '%s only works in %s scripts; this is a%s %s script.' % (
                                        mod, where, 'n' if group in ('LOCAL',) else '', {'GLOBAL': 'global', 'PLAYER': 'player',
                                                                                          'LOCAL': 'object', 'MENU': 'menu',
                                                                                          'LOAD': 'load'}[group])})
                elif not mod.startswith('openmw_aux.'):
                    out.append({'line': line, 'level': 'warning', 'text': 'OpenMW has no module called %s (spelling?).' % mod})
    # ---- engine handlers: names the engine calls (a typo means it never runs)
    known = HANDLERS['any'] | HANDLERS.get(group, set())
    every = set().union(*HANDLERS.values())
    names = []
    for n in range(len(toks) - 2):
        if not (toks[n][1] == 'engineHandlers' and toks[n + 1][1] == '=' and toks[n + 2][1] == '{'):
            continue
        # the keys at the top level of that table (not names used inside the handlers' own code)
        braces, blocks, j = 1, 0, n + 3
        while j < len(toks) and braces:
            k, v, line = toks[j]
            if k == 'op' and v in '({[':
                braces += 1
            elif k == 'op' and v in ')}]':
                braces -= 1
            elif k == 'name' and v in ('function', 'if', 'do', 'repeat'):
                blocks += 1
            elif k == 'name' and v in ('end', 'until'):
                blocks -= 1
            elif (k == 'name' and braces == 1 and blocks == 0 and j + 1 < len(toks) and toks[j + 1][1] == '='
                  and toks[j - 1][1] in ('{', ',', ';')):
                names.append((v, line))
            j += 1
    if names:
        for nm, line in names:
            if nm in known:
                continue
            if nm in every:
                out.append({'line': line, 'level': 'warning', 'text': '%s is not called for this kind of script, so it would never run here.' % nm})
            else:
                close = [h for h in every if h.lower() == nm.lower() or _near(h, nm)]
                out.append({'line': line, 'level': 'error', 'text': 'The engine has no handler called %s%s.' % (
                    nm, (' (did you mean %s?)' % close[0]) if close else '')})
    if toks and not any(k == 'name' and v == 'return' for k, v, _l in toks):
        out.append({'line': toks[-1][2], 'level': 'warning', 'text': 'The script never returns a table, so OpenMW has nothing to run '
                                                                     '(end it with: return { engineHandlers = { ... } }).'})
    out.sort(key=lambda p: (p['line'], p['level'] != 'error'))
    seen, uniq = set(), []
    for p in out:
        k = (p['line'], p['text'])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def _strip(text):
    """The text with comments and strings blanked out (same length, same lines)."""
    out = list(text)
    toks_re = re.compile(r'--\[(=*)\[.*?\]\1\]|--[^\n]*|\[(=*)\[.*?\]\2\]|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', re.S)
    for m in toks_re.finditer(text):
        for k in range(m.start(), m.end()):
            if out[k] != '\n':
                out[k] = ' '
    return ''.join(out)


def _near(a, b):
    """Spelt nearly the same (one letter more, less or different)."""
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [k for k, (x, y) in enumerate(zip(a, b)) if x != y]
        # one letter wrong, or two side by side swapped round
        return len(diff) <= 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if len(a) > len(b):
        a, b = b, a
    return any(b[:k] + b[k + 1:] == a for k in range(len(b)))
