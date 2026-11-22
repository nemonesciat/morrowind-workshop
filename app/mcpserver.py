"""The Workshop as an MCP server: coding agents (Claude Code, Codex, Cursor, opencode, Continue... any that speaks the
Model Context Protocol) use the Workshop's own tools on the mod that is open, as the built-in assistant does.

Streamable HTTP at /mcp on the Workshop's own port (127.0.0.1 only): JSON-RPC 2.0, answered as JSON (no event
stream). Off until Settings > AI > Coding agents turns it on; every request carries the key shown there
(?key=... in the address, or Authorization: Bearer ...), and a request from a web page (an Origin header that isn't
the Workshop's own) is refused. mcp_stdio.py is the same for agents that only start a command.

Every change goes through the same functions as the buttons: the same checks, a line in My changes marked with the
agent's name, and Undo. Lua is written with lua_write_script, never into the files in the data folder (the Workshop
writes those from the mod and would write over them). A tester asked for coding agents beside the API, 2026-11-21."""
import json
import os
import re
import secrets
import threading
import time
import uuid

import ai
import editing
from editing import EditError
from project import load_settings, save_settings

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
SERVER_NAME = 'morrowind-workshop'
STATE = {'sessions': {}, 'clients': {}, 'lock': threading.Lock()}
MARK = '\U0001F916 '          # (an agent's change in My changes: "🤖 claude-code: Made the Lua script ...")

INSTRUCTIONS = """Morrowind Workshop is an editor for OpenMW mods (Morrowind). These tools act on the mod the user has \
open in the Workshop: every change is saved into it straight away, shows in the user's My changes marked as yours, \
and can be undone. Work the way the Workshop's buttons do; never edit the mod's files on disk (the Workshop writes \
them from the mod and would write over your changes).

Start with workshop_status: which mod is open, whether it can hold Lua (an .omwaddon can, a plain .esp can't), \
where OpenMW is installed.

Places: find_places, then open_place, before look_around, place_objects, move_object or delete_objects. Positions are \
game units (a person ~128 tall); X east, Y north, Z up; an exterior cell is 8192 square; interiors have their own \
coordinates. z = null sets a thing down on the surface below it.

Records: search_objects and get_record to find and read; create_record copies an existing record under a new ID \
(prefix new IDs with something short and the mod's own), edit_record changes fields by the labels get_record shows.

OpenMW Lua (lua_* tools): a script's kind is where it runs: GLOBAL (once for the whole game; the only kind that may \
change the world: teleport anyone, create objects, give items), PLAYER (on the player; ui works only here), NPC, \
CREATURE, ACTIVATOR, CONTAINER, DOOR (on every such object near the player), CUSTOM (on the objects listed in \
attach), LOAD (as the game loads content), MENU. A script returns { engineHandlers = {...}, eventHandlers = {...} }; \
a local script asks the global one with core.sendGlobalEvent(name, data). When an actor dies its own scripts get the \
event Died. A teleport needs a position (obj:teleport(cellName or '' outdoors, util.vector3(x, y, z))). Scripts on \
many objects must not do work every frame (no onUpdate there: use events or async timers).
- Patterns that work in the game:
  when the player uses an object: a CUSTOM script with attach = [the object's record ID] and \
engineHandlers.onActivated(actor) that calls core.sendGlobalEvent('YourEvent', {actor = actor}); a GLOBAL script \
whose eventHandlers.YourEvent(data) does the world change (data.actor:teleport(cell, util.vector3(x, y, z))).
  The player: world.players[1] in a GLOBAL script, self in a PLAYER script, nearby.players[1] near an object; \
is something the player: types.Player.objectIsInstance(obj). Engine handlers get exactly the arguments OpenMW gives \
(onActivated(actor), not (self, actor)).
  when an NPC dies: an NPC (or CUSTOM) script with eventHandlers.Died. A new game: GLOBAL engineHandlers.onNewGame. \
A quest stage: PLAYER engineHandlers.onQuestUpdate(questId, stage). A message to the player from any script: \
player:sendEvent('ShowMessage', {message = text}) (near an object the player is nearby.players[1]).
- Before using a function you aren't sure of, openmw_lua_api: OpenMW's own list of its Lua, from the user's install. \
lookup_names turns names of places, people and items into real IDs, and places into a spot to arrive at.
- lua_write_script checks the script (shape, the kind's rules, every function against OpenMW's list) and refuses one \
with errors: fix what it says and write again. Warnings are saved and returned.
- After the user tries the mod in the game, lua_game_errors gives the Lua errors OpenMW logged for a script.
- Something that happens when a spell is cast is a magic effect of the mod's own, not a script: magic_effects_info, \
save_magic_effect (steps such as teleport, summon, push, or lua of your own), then create_spell.

Dialogue and quests: read_dialogue first. The game uses the first line, top to bottom, whose conditions match. \
Journal text is first person, past tense. Speech keeps Morrowind's voice and %PCName, %PCRace, %PCClass, %Name.

Finish with a short summary in plain words of what you changed. The user can try it in the game (reloadlua in the \
console loads Lua changes) and Undo anything; undo_last_change takes back your own last change."""


# ------------------------------------------------------------------ settings
def settings():
    s = load_settings()
    return {'on': bool(s.get('mcp_on')), 'key': s.get('mcp_key') or ''}


def turn(on):
    """Agents allowed or not; a key is made the first time."""
    s = load_settings()
    s['mcp_on'] = bool(on)
    if on and not s.get('mcp_key'):
        s['mcp_key'] = secrets.token_urlsafe(18)
    save_settings(s)
    return status()


def new_key():
    s = load_settings()
    s['mcp_key'] = secrets.token_urlsafe(18)
    save_settings(s)
    return status()


def status():
    st = settings()
    now = time.time()
    with STATE['lock']:
        clients = [{'name': n, 'last': round(now - c['last']), 'calls': c['calls'], 'last_tool': c.get('tool')}
                   for n, c in sorted(STATE['clients'].items(), key=lambda kv: -kv[1]['last'])]
    return {'on': st['on'], 'key': st['key'] if st['on'] else '', 'clients': clients[:6]}


# ------------------------------------------------------------------ the tools
def _schema(props, required=(), **kw):
    return dict({'type': 'object', 'properties': props, 'required': list(required), 'additionalProperties': False}, **kw)


S = {'type': 'string'}
N = {'type': 'number'}
READ = {'readOnlyHint': True, 'openWorldHint': False}
WRITE = {'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False}
DESTROY = {'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False}

# the built-in assistant's tools (ai.TOOLS), with what an agent needs said differently
ASSISTANT = {
    'look_around': ('Look around', READ, 'Describe the place opened with open_place around its focus point: its style, room '
                    'bounds, floor height, and the objects near by with their ref key, id, name, type, position, rotation '
                    'and size; also objects that typically appear in places like it. Call it before building.'),
    'search_objects': ('Search objects', READ, None),
    'place_objects': ('Place objects', WRITE, 'Place one or more objects in the place opened with open_place. z = null sets '
                      'each one down on the surface below it.'),
    'move_object': ('Move an object', WRITE, None),
    'delete_objects': ('Delete objects', DESTROY, None),
    'get_record': ('Read a record', READ, None),
    'create_record': ('Create a record', WRITE, None),
    'edit_record': ('Edit a record', WRITE, None),
    'list_building_styles': ('List building styles', READ, None),
    'build_interior': ('Build an interior', WRITE, None),
    'auto_furnish': ('Furnish an interior', WRITE, None),
    'read_dialogue': ('Read dialogue', READ, None),
    'save_quest': ('Save a quest', WRITE, None),
    'add_dialogue_line': ('Add a dialogue line', WRITE, None),
    'write_script': ('Write an MWScript', WRITE, 'Write a Morrowind script (MWScript, the game\'s own scripting language, not '
                     'Lua) and check it; fix any problems it reports and try again. A script runs only when attached to '
                     'something, started with the game, or started by StartScript. For OpenMW Lua use lua_write_script.'),
    'edit_character': ('Edit a character', WRITE, None),
}

TOOLS = []
for t in ai.TOOLS:
    if t['name'] in ASSISTANT:
        title, ann, desc = ASSISTANT[t['name']]
        TOOLS.append({'name': t['name'], 'title': title, 'description': desc or t['description'],
                      'inputSchema': t['input_schema'], 'annotations': dict(ann, title=title)})

TOOLS += [
    {'name': 'workshop_status', 'title': 'Workshop status', 'annotations': dict(READ, title='Workshop status'),
     'description': 'The mod open in the Workshop (its file, whether it can hold Lua), the game data loaded, the OpenMW '
                    'install, the place you have open, and the mod\'s Lua scripts. Start here.',
     'inputSchema': _schema({})},
    {'name': 'find_places', 'title': 'Find places', 'annotations': dict(READ, title='Find places'),
     'description': 'Find interiors and exterior cells by words in their name (e.g. "Balmora Guild", "Seyda Neen"). '
                    'Returns each place\'s key for open_place.',
     'inputSchema': _schema({'query': S, 'limit': {'type': 'integer', 'description': 'At most this many (default 20).'}}, ['query'])},
    {'name': 'open_place', 'title': 'Open a place', 'annotations': dict(READ, title='Open a place'),
     'description': 'Work in this place from now on (look_around, place_objects, move_object, delete_objects): a key from '
                    'find_places, an interior\'s name, or "#x,y" for an exterior cell. x and y set the focus point; without '
                    'them, a spot in front of a door (interiors) or the cell\'s middle.',
     'inputSchema': _schema({'place': S, 'x': N, 'y': N}, ['place'])},
    {'name': 'lookup_names', 'title': 'Look up names', 'annotations': dict(READ, title='Look up names'),
     'description': 'What names mean in the user\'s game: places get a spot to arrive at (for teleports), people and '
                    'things their record IDs; IDs the game doesn\'t have are pointed out.',
     'inputSchema': _schema({'names': {'type': 'array', 'items': S, 'description': 'Names or IDs, e.g. ["Balmora, Guild '
                                                                                     'of Mages", "Caius Cosades", "p_restore_health_s"].'}}, ['names'])},
    {'name': 'lua_list_scripts', 'title': 'List Lua scripts', 'annotations': dict(READ, title='List Lua scripts'),
     'description': 'The mod\'s OpenMW Lua scripts (name, kind, attach, lines, errors and warnings), and the kinds a script '
                    'can be.',
     'inputSchema': _schema({})},
    {'name': 'lua_read_script', 'title': 'Read a Lua script', 'annotations': dict(READ, title='Read a Lua script'),
     'description': 'A Lua script of the mod: its text, kind, attach and what the checker finds.',
     'inputSchema': _schema({'name': S}, ['name'])},
    {'name': 'lua_write_script', 'title': 'Write a Lua script', 'annotations': dict(WRITE, title='Write a Lua script'),
     'description': 'Create or replace a Lua script of the mod (the whole text). It is checked first: its shape, the rules '
                    'for its kind, and every OpenMW function and field against OpenMW\'s own list. A script with errors, or '
                    'with a name OpenMW\'s list doesn\'t have, is not saved: fix what it says and write again. Missing '
                    'require lines are put in (and listed in "added"). Warnings are saved and returned: read them, they '
                    'include events that nothing sends or handles. kind: GLOBAL, PLAYER, NPC, CREATURE, ACTIVATOR, '
                    'CONTAINER, DOOR, CUSTOM (with attach: the record IDs it runs on), LOAD or MENU.',
     'inputSchema': _schema({'name': {'type': 'string', 'description': 'Letters, numbers, spaces, - and _.'},
                             'text': S, 'kind': S,
                             'attach': {'type': 'array', 'items': S, 'description': 'For CUSTOM: record IDs of the objects, '
                                                                                    'NPCs or creatures it runs on.'},
                             'allow_unknown_names': {'type': 'boolean', 'description': 'Save even with names OpenMW\'s list '
                                                     'doesn\'t have (only when sure they exist: the list now and then trails '
                                                     'the game).'}},
                            ['name', 'text', 'kind'])},
    {'name': 'lua_delete_script', 'title': 'Remove a Lua script', 'annotations': dict(DESTROY, title='Remove a Lua script'),
     'description': 'Remove a Lua script from the mod (Undo brings it back).',
     'inputSchema': _schema({'name': S}, ['name'])},
    {'name': 'lua_check', 'title': 'Check Lua', 'annotations': dict(READ, title='Check Lua'),
     'description': 'Check Lua text without saving it, as lua_write_script would: shape, the rules for the kind, OpenMW\'s '
                    'own list of functions.',
     'inputSchema': _schema({'text': S, 'kind': S}, ['text', 'kind'])},
    {'name': 'lua_game_errors', 'title': 'Lua errors from the game', 'annotations': dict(READ, title='Lua errors from the game'),
     'description': 'The Lua errors OpenMW wrote in its log (openmw.log) about one of the mod\'s scripts, or all of them '
                    'without a name, the last time the game ran.',
     'inputSchema': _schema({'name': S})},
    {'name': 'openmw_lua_api', 'title': 'OpenMW Lua API', 'annotations': dict(READ, title='OpenMW Lua API'),
     'description': 'OpenMW\'s own list of its Lua, read from the user\'s OpenMW install. name: a module ("openmw.world", '
                    '"world"), a type ("GameObject", "Actor", "core#Cell") or a path ("types.Actor", "types.Actor.stats"): '
                    'its functions and fields with what they do. search: a word, for every function or field with it in '
                    'its name, across the whole list.',
     'inputSchema': _schema({'name': S, 'search': S})},
    {'name': 'magic_effects_info', 'title': 'Magic effect parts', 'annotations': dict(READ, title='Magic effect parts'),
     'description': 'What a magic effect of the mod\'s own is made of: the steps it can do (kind, what it does), when they '
                    'run, whom they touch, and the game\'s effects it can look like (template index). Also the mod\'s own '
                    'effects so far.',
     'inputSchema': _schema({})},
    {'name': 'save_magic_effect', 'title': 'Save a magic effect', 'annotations': dict(WRITE, title='Save a magic effect'),
     'description': 'Make or change a magic effect of the mod\'s own (OpenMW 0.50+). effect: {name, id (letters, digits, _; '
                    'not starting with T_), template (index of the game\'s effect it looks like), cost, magnitude (bool), '
                    'duration (bool), description, does: [steps]}. A step is {kind, when: land|second|end, ...the kind\'s '
                    'fields}, e.g. {kind: "teleport", cell: "" (outdoors) or a cell name, x, y, z}, {kind: "summon", id, count}, '
                    '{kind: "health", sign: -1}, {kind: "lua", code, brief}. old_id: the effect\'s ID when renaming it.',
     'inputSchema': _schema({'effect': {'type': 'object'}, 'old_id': S}, ['effect'])},
    {'name': 'create_spell', 'title': 'Create a spell', 'annotations': dict(WRITE, title='Create a spell'),
     'description': 'Create a spell record. effects: [{effect (the game\'s effect index, or the ID of the mod\'s own effect), '
                    'range (0 self, 1 touch, 2 target), area, duration, min, max}]. type: 0 spell, 1 ability, 2 blight, '
                    '3 disease, 4 curse, 5 power. give_to: an NPC ID who knows it (the player starts with it with '
                    'player_starts).',
     'inputSchema': _schema({'id': S, 'name': S, 'type': {'type': 'integer'}, 'effects': {'type': 'array', 'items': {'type': 'object'}},
                             'always_succeeds': {'type': 'boolean'}, 'player_starts': {'type': 'boolean'}, 'give_to': S},
                            ['id', 'name', 'effects'])},
    {'name': 'list_changes', 'title': 'Recent changes', 'annotations': dict(READ, title='Recent changes'),
     'description': 'The mod\'s most recent changes, newest last, as My changes shows them (yours are marked).',
     'inputSchema': _schema({'limit': {'type': 'integer'}})},
    {'name': 'undo_last_change', 'title': 'Undo your last change', 'annotations': dict(DESTROY, title='Undo your last change'),
     'description': 'Take back the mod\'s last change, if it was yours (an agent\'s). The user\'s own changes are theirs to undo.',
     'inputSchema': _schema({})},
]

PROMPTS = [
    {'name': 'write_lua_script', 'title': 'Write a Lua script',
     'description': 'Write an OpenMW Lua script for the open mod, checked against OpenMW\'s own list.',
     'arguments': [{'name': 'what', 'description': 'What the script should do', 'required': True},
                   {'name': 'runs', 'description': 'Where it runs: the whole game, the player, every NPC, chosen objects...',
                    'required': False}]},
    {'name': 'fix_lua_script', 'title': 'Fix a Lua script',
     'description': 'Fix one of the mod\'s Lua scripts from the checker and the game\'s own errors.',
     'arguments': [{'name': 'name', 'description': 'The script\'s name', 'required': True},
                   {'name': 'problem', 'description': 'What goes wrong in the game, if anything', 'required': False}]},
    {'name': 'make_spell', 'title': 'Make a spell',
     'description': 'A spell with a magic effect of the mod\'s own (teleport, summon, Lua of your own...).',
     'arguments': [{'name': 'what', 'description': 'What the spell does', 'required': True}]},
]


def _prompt(name, args):
    a = args or {}
    if name == 'write_lua_script':
        text = ('Write an OpenMW Lua script for my mod, open in Morrowind Workshop: %s%s\n\n'
                'Call workshop_status first. Look up the places, people and items it names with lookup_names, and any OpenMW '
                'function you aren\'t sure of with openmw_lua_api. Save it with lua_write_script and fix whatever it reports. '
                'If it runs on objects but must change the world, write the GLOBAL part that does it too. Then tell me in a few '
                'words what it does and how to try it in the game.' % (a.get('what', ''), ('\nWhere it runs: ' + a['runs']) if a.get('runs') else ''))
    elif name == 'fix_lua_script':
        text = ('Fix the Lua script "%s" of my mod, open in Morrowind Workshop.%s\n\nRead it with lua_read_script and the game\'s '
                'errors for it with lua_game_errors; check functions with openmw_lua_api; save the fixed script with '
                'lua_write_script. Tell me what was wrong.' % (a.get('name', ''), (' In the game: ' + a['problem']) if a.get('problem') else ''))
    elif name == 'make_spell':
        text = ('Make a spell for my mod, open in Morrowind Workshop: %s\n\nUse a magic effect of the mod\'s own: magic_effects_info '
                'for its parts, save_magic_effect, then create_spell (give it to the player or a seller if I said so). Use '
                'lookup_names for places and things. Tell me how to get the spell in the game.' % a.get('what', ''))
    else:
        raise KeyError(name)
    return {'description': next(p['description'] for p in PROMPTS if p['name'] == name),
            'messages': [{'role': 'user', 'content': {'type': 'text', 'text': text}}]}


# ------------------------------------------------------------------ doing them
class Agent:
    """One connected agent: its name, and the place it has open (the built-in assistant's tools, its own context)."""
    def __init__(self, db, name):
        self.db = db
        self.name = name or 'agent'
        self.helper = ai.Assistant(db, lambda: None)

    def call(self, tool, args):
        db = self.db
        if getattr(db, 'state', '') == 'loading':
            raise EditError('The Workshop is reading the game data; try again in a moment.')
        fn = getattr(self, 'x_' + tool, None)
        if fn:
            return fn(**args)
        if tool in ASSISTANT:
            if not db.project and tool not in ('search_objects', 'get_record', 'list_building_styles', 'read_dialogue'):
                raise EditError('No mod is open in the Workshop: the user opens or starts one first.')
            if tool in ('look_around', 'place_objects', 'move_object', 'delete_objects') and not self.helper.ctx.get('cell'):
                raise EditError('No place is open: call open_place first (find_places gives the keys).')
            return self.helper.run_tool(tool, args)
        raise EditError('There is no tool called %s.' % tool)

    # ----- the mod and the places
    def x_workshop_status(self):
        db = self.db
        p = db.project
        out = {'game_data': {'state': getattr(db, 'state', ''), 'records': len(getattr(db, 'recs', []) or []),
                             'plugins': len(getattr(db, 'plugins', []) or [])},
               'openmw': {'install': (db.config or {}).get('install')},
               'mod': None, 'place_open': self.helper.ctx.get('cell')}
        if p:
            out['mod'] = {'name': p.name, 'file': p.plugin, 'can_hold_lua': p.lua_allowed(),
                          'lua_scripts': [s['name'] for s in p.lua], 'changes': len(p.log)}
            if not p.lua_allowed():
                out['mod']['note'] = 'A plain .esp can\'t hold Lua: File > Save as... in the Workshop makes an .omwaddon of it.'
        else:
            out['note'] = 'No mod is open: the user opens or starts one in the Workshop.'
        import luaapi
        out['openmw']['lua_api_list'] = bool(luaapi.load(None))
        return out

    def x_find_places(self, query, limit=20):
        db = self.db
        rows = db.search(query, types=('CELL',), limit=max(1, min(60, int(limit or 20))))['rows']
        out = []
        for r in rows:
            key = db.key_of(r['i'])[1]
            out.append({'key': key, 'name': r.get('name') or r['id'], 'interior': not key.startswith('#')})
        return {'places': out}

    def x_open_place(self, place, x=None, y=None):
        import mapdata
        db = self.db
        key = (place or '').strip()
        if ('CELL', key) not in db.by_key and ('CELL', key.lower()) in db.by_key:
            key = key.lower()
        info = mapdata.cell_info(db, key)
        if not info:
            raise EditError('There is no place "%s": find_places gives the keys.' % place)
        if x is None or y is None:
            try:
                import doors
                pos, _d = doors.arrival(db, key)
                x, y = pos[0], pos[1]
            except Exception:
                m = re.match(r'^#(-?\d+),(-?\d+)$', key)
                x, y = ((int(m.group(1)) + 0.5) * 8192, (int(m.group(2)) + 0.5) * 8192) if m else (0.0, 0.0)
        self.helper.ctx = {'cell': key, 'focus': [float(x), float(y)], 'sel': None}
        return {'opened': key, 'name': info.get('id') or key, 'interior': bool(info.get('interior')), 'focus': [round(x), round(y)]}

    def x_lookup_names(self, names):
        brief = ' '.join('"%s"' % n.replace('"', '') for n in names or [])
        return {'found': self.helper._facts(brief) or 'Nothing found for those names.'}

    # ----- Lua
    def _lua(self):
        p = self.db.project
        if not p:
            raise EditError('No mod is open in the Workshop: the user opens or starts one first.')
        return p

    def x_lua_list_scripts(self):
        import luascripts
        self._lua()
        r = luascripts.listing(self.db)
        return {'scripts': r['scripts'], 'kinds': [{'kind': k[0], 'label': k[1], 'what': k[2]} for k in r['kinds']],
                'can_hold_lua': self.db.project.lua_allowed()}

    def x_lua_read_script(self, name):
        import luascripts
        self._lua()
        r = luascripts.read(self.db, name)
        return {k: r[k] for k in ('name', 'kind', 'attach', 'text', 'path', 'problems')}

    def x_lua_write_script(self, name, text, kind, attach=None, allow_unknown_names=False):
        import lua_check
        import luascripts
        p = self._lua()
        if not p.lua_allowed():
            raise EditError('The open mod is a plain .esp, which can\'t hold Lua: in the Workshop, File > Save as... makes an '
                            '.omwaddon of it.')
        kind = (kind or 'GLOBAL').upper()
        if kind not in luascripts.KIND_IDS:
            raise EditError('Unknown kind %s: one of %s.' % (kind, ', '.join(sorted(luascripts.KIND_IDS))))
        text = (text or '').replace('\r\n', '\n')
        mark = '-- Written by %s (a coding agent). Read it over and try it in the game.\n' % self.name
        m = re.match(r'^\s*(-- Written by [^\n]*\n)', text)
        if m:
            mark, text = m.group(1), text[m.end():]
        # (core, util, world... used without their require line: put in, and said so; an agent's script did, 2026-11-21)
        body = ai.add_requires(text)
        added = [l for l in body.splitlines()[:len(body.splitlines()) - len(text.splitlines())] if 'require(' in l]
        text = mark + body
        probs = lua_check.check(text, kind)
        errors = [q for q in probs if q['level'] == 'error' or (q.get('api') and not allow_unknown_names)]
        if errors:
            raise EditError('Not saved: ' + '; '.join('line %d: %s' % (q['line'], q['text']) for q in errors[:10]) + (
                ' (A name OpenMW\'s list doesn\'t have is nearly always a mistake: check it with openmw_lua_api. If you are '
                'sure it exists in the game, write again with allow_unknown_names.)' if any(q.get('api') for q in errors) else ''))
        key = luascripts._check_name(name)
        if not any(s['name'] == key for s in p.lua):
            luascripts.create(self.db, name, 'blank')
        r = luascripts.save(self.db, key, {'kind': kind, 'attach': attach or [], 'text': text})
        warnings = [q for q in r['problems'] if q['level'] != 'error'] + _event_notes(p, key, text, kind)
        if kind == 'CUSTOM' and not (attach or []):
            warnings.append({'line': 1, 'level': 'warning', 'text': 'A CUSTOM script runs only on the objects in attach, and it '
                                                                    'has none: it runs nowhere yet.'})
        out = {'saved': r['name'], 'kind': r['kind'], 'attach': r['attach'], 'file': r['path'], 'warnings': warnings}
        if added:
            out['added'] = added
        return out

    def x_lua_delete_script(self, name):
        import luascripts
        self._lua()
        return luascripts.delete(self.db, name)

    def x_lua_check(self, text, kind):
        import lua_check
        return {'problems': lua_check.check(text or '', (kind or 'GLOBAL').upper())}

    def x_lua_game_errors(self, name=None):
        import luascripts
        p = self._lua()
        if name:
            return luascripts.game_errors(self.db, name)
        out = {}
        for s in p.lua:
            e = luascripts.game_errors(self.db, s['name'])['errors']
            if e:
                out[s['name']] = e
        return {'errors': out or 'None of the mod\'s Lua scripts has errors in the game\'s log.'}

    def x_openmw_lua_api(self, name=None, search=None):
        import luaapi
        api = luaapi.load(None)
        if not api:
            raise EditError('OpenMW\'s own list of its Lua isn\'t found in the OpenMW install the Workshop uses.')
        if search:
            w = search.lower()
            hits = []
            for key, t in sorted(api['types'].items()):
                for m, info in sorted(t['members'].items()):
                    if w in m.lower():
                        owner = key.split('#', 1)[1]
                        sig = '%s%s%s(%s)' % (owner, ':' if info.get('method') else '.', m, ', '.join(info.get('params') or [])) \
                            if info['kind'] == 'function' else '%s.%s' % (owner, m)
                        hits.append('%s  [%s]  -- %s' % (sig, key, info.get('doc') or ''))
            return {'found': hits[:60] or 'Nothing with "%s" in its name.' % search}
        if not name:
            return {'modules': sorted(api['modules']), 'hint': 'Ask for one by name, or search for a word.'}
        key = self._api_key(api, name)
        if not key:
            raise EditError('"%s" is not a module or type in OpenMW\'s list: try search.' % name)
        return {'of': key, 'members': luaapi.excerpt(None, [key], most=200).split('\n')}

    @staticmethod
    def _api_key(api, name):
        import luaapi
        n = name.strip()
        if n in api['modules']:
            return api['modules'][n]
        if 'openmw.' + n in api['modules']:
            return api['modules']['openmw.' + n]
        if n in api['types']:
            return n
        parts = n.split('.')
        if len(parts) > 1 and ('openmw.' + parts[0]) in api['modules']:
            key = api['modules']['openmw.' + parts[0]]
            for part in parts[1:]:
                info = luaapi.members(api, key).get(part)
                key = info['type'] if info and isinstance(info.get('type'), str) else None
                if not key:
                    return None
            return key
        same = [k for k in api['types'] if k.split('#', 1)[1].lower() == n.lower()]
        return same[0] if same else None

    # ----- magic effects and spells
    def x_magic_effects_info(self):
        import myeffects
        self._lua()
        r = myeffects.read(self.db)
        return {'step_kinds': r['does'], 'whens': r['whens'], 'only': r['only'],
                'templates': [{'index': t['index'], 'name': t['name'], 'school': t['school']} for t in r['templates']],
                'own_effects': r['effects']}

    def x_save_magic_effect(self, effect, old_id=None):
        import myeffects
        self._lua()
        return myeffects.save(self.db, effect or {}, old_id)

    def x_create_spell(self, **d):
        import items
        self._lua()
        return items.create_spell(self.db, d)

    # ----- changes
    def x_list_changes(self, limit=15):
        p = self._lua()
        n = max(1, min(60, int(limit or 15)))
        return {'changes': [{'id': e.get('id'), 'text': editing.note_label(p, e.get('text'), e.get('id')),
                             'undone': bool(e.get('undone'))} for e in p.log[-n:]]}

    def x_undo_last_change(self):
        p = self._lua()
        last = next((e for e in reversed(p.log) if not e.get('undone')), None)
        if not last or not (last.get('text') or '').startswith(MARK):
            raise EditError('The last change is the user\'s, not an agent\'s: it is theirs to undo.')
        undone = editing.undo(self.db)
        return {'undone': [editing.note_label(p, t) for t in undone]}


# events OpenMW itself sends to scripts, and those its own scripts answer
ENGINE_SENDS = {'Died'}
ENGINE_HEARS = {'ShowMessage', 'StartAIPackage', 'RemoveAIPackages', 'AddUiMode', 'SetUiMode', 'Pause', 'Unpause'}


def _handled(text):
    """The event names a script's eventHandlers table answers."""
    import lua_check
    toks = [t for t in lua_check.tokens(text)[0] if t[0] not in ('ws', 'nl', 'com', 'lcom')]
    out = set()
    for i in range(len(toks) - 2):
        if toks[i][1] == 'eventHandlers' and toks[i + 1][1] == '=' and toks[i + 2][1] == '{':
            depth, j = 0, i + 2
            while j < len(toks):
                v = toks[j][1]
                if depth == 1 and v == '[' and j + 3 < len(toks) and toks[j + 2][1] == ']' and toks[j + 3][1] == '=':
                    out.add(toks[j + 1][1].strip('\'"'))          # (['Name'] = function ...)
                if v in ('{', '(', '['):
                    depth += 1
                elif v in ('}', ')', ']'):
                    depth -= 1
                    if depth == 0:
                        break
                elif depth == 1 and toks[j][0] == 'name' and j + 1 < len(toks) and toks[j + 1][1] == '=' and toks[j - 1][1] in ('{', ','):
                    out.add(v)
                j += 1
    return out


def _event_notes(p, name, text, kind):
    """What an agent's script handles that nothing sends, and what it sends that nothing handles: a script can be
    right in every line and still never run (an agent's "Used" event, 2026-11-21)."""
    sent_any, global_heard, heard_any = set(), set(), set()
    for s in p.lua:
        t = text if s['name'] == name else (s.get('text') or '')
        sent_any |= set(re.findall(r'send(?:Global)?Event\(\s*[\'"](\w+)[\'"]', t))
        h = _handled(t)
        heard_any |= h
        if (s.get('kind') or '').upper() == 'GLOBAL' or (s['name'] == name and kind == 'GLOBAL'):
            global_heard |= h
    notes = []
    for ev in sorted(_handled(text)):
        if ev not in sent_any and ev not in ENGINE_SENDS:
            notes.append('It handles the event %s, but no script of the mod sends it and OpenMW itself doesn\'t: unless another '
                         'mod does, that handler never runs (an engine handler such as onActivated may be what is meant).' % ev)
    for ev in sorted(set(re.findall(r'sendGlobalEvent\(\s*[\'"](\w+)[\'"]', text))):
        if ev not in global_heard and ev not in ENGINE_HEARS:
            notes.append('It sends the global event %s, which no GLOBAL script of the mod handles yet: write one (kind GLOBAL) '
                         'with eventHandlers.%s.' % (ev, ev))
    for ev in sorted(set(re.findall(r':sendEvent\(\s*[\'"](\w+)[\'"]', text))):
        if ev not in heard_any and ev not in ENGINE_HEARS:
            notes.append('It sends the event %s to an object, but no script of the mod handles it.' % ev)
    return [{'line': 1, 'level': 'warning', 'text': t} for t in notes]


def _mark_new(p, before, name):
    """The mod's new entries in My changes, marked as this agent's."""
    for e in p.log[before:]:
        t = e.get('text') or ''
        if t and not t.startswith(MARK):
            e['text'] = '%s%s: %s' % (MARK, name, t)


# ------------------------------------------------------------------ JSON-RPC
def _result(mid, result):
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def _error(mid, code, message):
    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': message}}


def handle(db, lock, msg, session):
    """One JSON-RPC message -> its answer (None for a notification)."""
    if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0':
        return _error(None, -32600, 'Not a JSON-RPC 2.0 message.')
    mid, method, params = msg.get('id'), msg.get('method'), msg.get('params') or {}
    if method is None:
        return None                                  # (a response or something else to us: nothing to say)
    if mid is None:
        return None                                  # (notifications: initialized, cancelled... nothing to answer)
    sess = STATE['sessions'].get(session) if session else None
    if method == 'initialize':
        want = params.get('protocolVersion')
        info = params.get('clientInfo') or {}
        name = re.sub(r'[^\w .()-]', '', str(info.get('name') or 'agent'))[:40] or 'agent'
        sid = session or uuid.uuid4().hex
        with STATE['lock']:
            STATE['sessions'][sid] = {'agent': Agent(db, name), 'name': name}
        import helpinfo
        return _result(mid, {'protocolVersion': want if want in PROTOCOLS else PROTOCOLS[0],
                             'capabilities': {'tools': {'listChanged': False}, 'prompts': {'listChanged': False}},
                             'serverInfo': {'name': SERVER_NAME, 'title': 'Morrowind Workshop', 'version': helpinfo.version()},
                             'instructions': INSTRUCTIONS}), sid
    if method == 'ping':
        return _result(mid, {})
    if method == 'tools/list':
        return _result(mid, {'tools': TOOLS})
    if method == 'prompts/list':
        return _result(mid, {'prompts': PROMPTS})
    if method == 'prompts/get':
        try:
            return _result(mid, _prompt(params.get('name'), params.get('arguments')))
        except KeyError:
            return _error(mid, -32602, 'No prompt called %s.' % params.get('name'))
    if method in ('resources/list', 'resources/templates/list'):
        return _result(mid, {'resources': [], 'resourceTemplates': []})
    if method == 'tools/call':
        if sess is None:
            # (an agent that doesn't keep the session: one agent per name, made on the spot)
            with STATE['lock']:
                sess = STATE['sessions'].setdefault(session or 'default', {'agent': Agent(db, 'agent'), 'name': 'agent'})
        agent = sess['agent']
        tool, args = params.get('name'), params.get('arguments') or {}
        if tool not in {t['name'] for t in TOOLS}:
            return _error(mid, -32602, 'There is no tool called %s.' % tool)
        with STATE['lock']:
            c = STATE['clients'].setdefault(agent.name, {'calls': 0, 'last': 0})
            c['calls'] += 1
            c['last'] = time.time()
            c['tool'] = tool
        try:
            with lock:
                p = db.project
                before = len(p.log) if p else 0
                editing.ORIGIN.window = 'agent'
                try:
                    out = agent.call(tool, args)
                finally:
                    editing.ORIGIN.window = None
                if db.project is p and p is not None:
                    _mark_new(p, before, agent.name)
            return _result(mid, {'content': [{'type': 'text', 'text': json.dumps(out, ensure_ascii=False, indent=1, default=str)}],
                                 'isError': False})
        except (EditError, ai.ToolError, TypeError, ValueError, KeyError) as e:
            msg_ = str(e) if not isinstance(e, (TypeError, KeyError)) else 'Wrong arguments for %s: %s' % (tool, e)
            return _result(mid, {'content': [{'type': 'text', 'text': msg_}], 'isError': True})
    return _error(mid, -32601, 'Method not found: %s' % method)


# ------------------------------------------------------------------ HTTP (Streamable HTTP, answered as JSON)
def http(handler, db, lock, method):
    """Answer GET/POST/DELETE /mcp for the Workshop's request handler."""
    from urllib.parse import parse_qs, urlparse
    st = settings()

    def send(code, obj=None, extra=None):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8') if obj is not None else b''
        handler.send_response(code)
        if obj is not None:
            handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(body)))
        handler.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            handler.send_header(k, v)
        handler.end_headers()
        if body:
            handler.wfile.write(body)

    origin = handler.headers.get('Origin')
    if origin and not re.match(r'^https?://(127\.0\.0\.1|localhost)(:\d+)?$', origin):
        return send(403, _error(None, -32000, 'Requests from web pages are refused.'))
    if not st['on']:
        return send(403, _error(None, -32000, 'Coding agents are switched off: in Morrowind Workshop, Settings > AI > '
                                              'Coding agents.'))
    q = parse_qs(urlparse(handler.path).query)
    given = (q.get('key') or [''])[0] or re.sub(r'^Bearer\s+', '', handler.headers.get('Authorization') or '')
    if not st['key'] or not secrets.compare_digest(given, st['key']):
        return send(401, _error(None, -32000, 'Wrong or missing key: copy the address from Settings > AI > Coding agents.'))
    if method == 'GET':
        return send(405, None, {'Allow': 'POST, DELETE'})        # (no event stream: every answer comes back as JSON)
    session = handler.headers.get('Mcp-Session-Id')
    if method == 'DELETE':
        with STATE['lock']:
            STATE['sessions'].pop(session, None)
        return send(200, None)
    n = int(handler.headers.get('Content-Length') or 0)
    try:
        msg = json.loads(handler.rfile.read(n).decode('utf-8') or 'null')
    except ValueError:
        return send(400, _error(None, -32700, 'Parse error.'))
    if isinstance(msg, list):
        out = [r for r in (handle(db, lock, m, session) for m in msg) if r is not None]
        out = [r[0] if isinstance(r, tuple) else r for r in out]
        return send(200, out) if out else send(202, None)
    r = handle(db, lock, msg, session)
    if r is None:
        return send(202, None)
    if isinstance(r, tuple):
        r, sid = r
        return send(200, r, {'Mcp-Session-Id': sid})
    return send(200, r)


def address(port):
    st = settings()
    return 'http://127.0.0.1:%d/mcp?key=%s' % (port, st['key']) if st['on'] and st['key'] else ''
