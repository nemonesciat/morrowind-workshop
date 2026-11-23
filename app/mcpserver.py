"""The Workshop as an MCP server: coding agents (Claude Code, Codex, Cursor, opencode, Continue... any that speaks the
Model Context Protocol) use the Workshop's own tools on the mod that is open (the tools in ai.py).

Streamable HTTP at /mcp on the Workshop's own port (127.0.0.1 only): JSON-RPC 2.0, answered as JSON (no event
stream). Off until Settings > AI > Coding agents turns it on; every request carries the key shown there
(?key=... in the address, or Authorization: Bearer ...), and a request from a web page (an Origin header that isn't
the Workshop's own) is refused. mcp_stdio.py is the same for agents that only start a command.

Every change goes through the same functions as the buttons: the same checks, a line in My changes marked with the
agent's name, and Undo. Lua is written with lua_write_script, never into the files in the data folder (the Workshop
writes those from the mod and would write over them). A tester asked for coding agents beside the API, 2026-11-21."""
import contextlib
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
import project as _projmod
from project import load_settings, save_settings

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
SERVER_NAME = 'morrowind-workshop'
STATE = {'sessions': {}, 'clients': {}, 'lock': threading.Lock(),
         'acts': [], 'act_n': 0, 'busy': None}      # (what agents did, for the Workshop window to show: activity())
MARK = '\U0001F916 '          # (an agent's change in My changes: "🤖 claude-code: Made the Lua script ...")

INSTRUCTIONS = """Morrowind Workshop is an editor for OpenMW mods (Morrowind). These tools act on the mod the user has \
open in the Workshop: every change is saved into it straight away, shows in the user's My changes marked as yours, \
and can be undone. While the user has unsaved changes of their own (workshop_status: mod.unsaved) your changes are \
refused until they save or throw theirs away: wait and try again, never work around it. Work the way the Workshop's buttons do; never edit the mod's files on disk (the Workshop writes \
them from the mod and would write over your changes).

The user watches your work in the Workshop's own window: it goes by itself to the place you open or change and selects what you place or move, with a line saying what you did. Never control the screen, mouse or keyboard to work the Workshop or the game: these tools are the only way in.

Beyond the tools here, workshop_actions finds every action of the Workshop's own buttons (towns, castles, dungeons, land, furnishing, populating, grass, regions, sounds, items, NPCs, quests, the release zip...) and workshop_action runs one; show_user moves the user's window: a place, the map or 3D, the camera on a spot or things.

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

# the Workshop's tools (ai.TOOLS), with what an agent needs said differently
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
    {'name': 'show_user', 'title': 'Show the user', 'annotations': dict(READ, title='Show the user'),
     'description': 'Move the user\'s own Workshop window: open a place, switch between the map and the 3D view, point the '
                    'camera at a spot or at things, and select things. The window already follows your changes by itself; '
                    'use this to show something on purpose ("here is the shrine"). Never control the screen for this.',
     'inputSchema': _schema({'place': {'type': 'string', 'description': 'A place key (find_places); default: the place you have open'},
                             'look_at': {'type': 'array', 'items': N, 'description': '[x, y] or [x, y, z]: the spot to centre the camera on'},
                             'refs': {'type': 'array', 'items': S, 'description': 'Ref keys to select and frame (look_around gives them)'},
                             'view': {'type': 'string', 'enum': ['map', '3d'], 'description': 'The flat map or the 3D view; default: as it is'}})},
    {'name': 'workshop_actions', 'title': 'Find Workshop actions', 'annotations': dict(READ, title='Find Workshop actions'),
     'description': 'Everything the Workshop\'s own buttons can do, as actions to run with workshop_action: building interiors, '
                    'towns, castles, dungeons and land, furnishing, populating, grass, regions, sounds, items, NPCs, '
                    'dialogue, quests, scripts, magic, the Library, the release zip and more. Search by a word ("furnish", '
                    '"town", "grass"); with no word, the areas and how many actions each has. Each action comes with GET or '
                    'POST, what it does, the arguments the Workshop reads and how it reads them.',
     'inputSchema': _schema({'search': {'type': 'string'}})},
    {'name': 'workshop_action', 'title': 'Run a Workshop action', 'annotations': dict(WRITE, title='Run a Workshop action'),
     'description': 'Run one action from workshop_actions, as the Workshop\'s page does: the same checks, every change in My '
                    'changes as yours, and Undo. args are the arguments it reads (a JSON object). Read the place or record '
                    'first (look_around, get_record, or a GET action) so the arguments are right. Some actions are kept from '
                    'agents: switching or deleting mods, backups and files, starting the game, opening windows on the '
                    'user\'s screen, the user\'s settings and load order, and undoing the user\'s own changes.',
     'inputSchema': _schema({'action': {'type': 'string', 'description': 'Its path, e.g. /api/furnish/room'},
                             'args': {'type': 'object', 'description': 'The arguments it reads'},
                             'method': {'type': 'string', 'enum': ['GET', 'POST'], 'description': 'Only for an action that is both'}}, ['action'])},
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
    """One connected agent: its name, and the place it has open (the Workshop's tools, its own context)."""
    def __init__(self, db, name):
        self.db = db
        self.name = name or 'agent'
        self.helper = ai.Assistant(db)

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
                          'lua_scripts': [s['name'] for s in p.lua], 'changes': len(p.log),
                          'unsaved': bool(editing.unsaved(db))}
            if out['mod']['unsaved']:
                out['mod']['unsaved_note'] = editing.REFUSED
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
    # ----- the user's window, and every action of the Workshop's own
    def x_show_user(self, place=None, look_at=None, refs=None, view=None):
        import mapdata
        db = self.db
        key = (place or '').strip() or self.helper.ctx.get('cell')
        if key and ('CELL', key) not in db.by_key and ('CELL', key.lower()) in db.by_key:
            key = key.lower()
        if not key or not mapdata.cell_info(db, key):
            raise EditError('Say which place to show: find_places gives the keys, or open_place first.')
        look = [float(v) for v in (look_at or [])][:3] or None
        if look is not None and len(look) < 2:
            raise EditError('look_at is [x, y] or [x, y, z].')
        _note({'agent': self.name, 'tool': 'show_user', 'title': 'Show', 'text': 'Showing you %s' % (
            (mapdata.cell_info(db, key) or {}).get('id') or key), 'cell': key, 'refs': [str(r) for r in refs or []][:60],
            'look': look, 'view': view if view in ('map', '3d') else None, 'show': True, 'changed': False, 'error': None})
        return {'shown': key, 'note': 'The user\'s window goes there within a second or two.'}

    def x_workshop_actions(self, search=None):
        cat = catalogue()
        if not search:
            areas = {}
            for a in cat.values():
                areas[a['area']] = areas.get(a['area'], 0) + 1
            return {'actions': len(cat), 'areas': dict(sorted(areas.items())),
                    'hint': 'Search by a word for the actions themselves, e.g. "furnish" or "town".'}
        words = [w for w in re.split(r'\W+', search.lower()) if w]
        hits = [a for a in cat.values() if all(w in (a['path'] + ' ' + a['what'] + ' ' + ' '.join(a['args'])).lower() for w in words)]
        return {'found': [{k: a[k] for k in ('path', 'method', 'what', 'args', 'reads')} for a in hits[:40]],
                'more': max(0, len(hits) - 40)}

    def x_workshop_action(self, action, args=None, method=None):
        import urllib.error
        import urllib.request
        path = '/' + (action or '').strip().lstrip('/')
        if not path.startswith('/api/'):
            path = '/api/' + path[1:]
        both = [a for a in catalogue().values() if a['path'] == path]
        if not both:
            raise EditError('There is no Workshop action %s: workshop_actions finds them.' % path)
        m = (method or '').upper()
        a = next((x for x in both if x['method'] == m), None) if m else (both[0] if len(both) == 1 else None)
        if a is None:
            raise EditError('%s is both GET (to read) and POST (to change): say which with method.' % path)
        if a.get('kept'):
            raise EditError('%s is kept for the user (%s).' % (path, a['kept']))
        port = STATE.get('port')
        if not port:
            raise EditError('The Workshop\'s address isn\'t known yet: try again.')
        args = args if isinstance(args, dict) else {}
        url = 'http://127.0.0.1:%d%s' % (port, path)
        if a['method'] == 'GET':
            from urllib.parse import urlencode
            req = urllib.request.Request(url + ('?' + urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in args.items()}) if args else ''))
        else:
            req = urllib.request.Request(url, data=json.dumps(args).encode('utf-8'), method='POST',
                                         headers={'Content-Type': 'application/json', 'X-Workshop-Window': 'agent'})
        try:
            with urllib.request.urlopen(req, timeout=3600) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get('error')
            except Exception:
                msg = None
            raise EditError('%s: %s' % (path, msg or 'the Workshop answered %s' % e.code))
        try:
            out = json.loads(raw)
        except ValueError:
            return {'ok': True, 'bytes': len(raw), 'note': 'Not JSON (a picture or a file).'}
        text = json.dumps(out, ensure_ascii=False, default=str)
        if len(text) > 60000:
            return {'cut_short': True, 'size': len(text), 'start': text[:60000],
                    'note': 'Too long to give whole: ask for less (a smaller place, a narrower search).'}
        return out

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
        with STATE['lock']:
            STATE['busy'] = {'agent': agent.name, 'tool': tool, 'since': time.time(), 'title': _title(tool) if tool != 'workshop_action'
                             else 'Running %s' % str((args or {}).get('action') or '').replace('/api/', '')}
        steps0 = len(agent.helper.steps)
        try:
            # (a Workshop action goes through the Workshop's own address, whose handlers take the lock themselves)
            with (contextlib.nullcontext() if tool == 'workshop_action' else lock):
                p = db.project
                before = len(p.log) if p else 0
                editing.ORIGIN.window = 'agent'
                _projmod.EXTERNAL.on = True          # (refused while the user has unsaved changes: editing.commit)
                try:
                    out = agent.call(tool, args)
                finally:
                    editing.ORIGIN.window = None
                    _projmod.EXTERNAL.on = False
                if db.project is p and p is not None:
                    _mark_new(p, before, agent.name)
                _act(agent, tool, out, steps0, p.log[before:] if (p is not None and db.project is p) else [], args=args)
            return _result(mid, {'content': [{'type': 'text', 'text': json.dumps(out, ensure_ascii=False, indent=1, default=str)}],
                                 'isError': False})
        except (EditError, ai.ToolError, TypeError, ValueError, KeyError) as e:
            msg_ = str(e) if not isinstance(e, (TypeError, KeyError)) else 'Wrong arguments for %s: %s' % (tool, e)
            _act(agent, tool, None, steps0, [], error=msg_, args=args)
            return _result(mid, {'content': [{'type': 'text', 'text': msg_}], 'isError': True})
        finally:
            with STATE['lock']:
                STATE['busy'] = None
    return _error(mid, -32601, 'Method not found: %s' % method)


# ------------------------------------------------------------------ every action of the Workshop's own, for agents
# (the user, 2026-11-22: "make sure the Workshop has ALL the tools an agent could need". 440-odd actions behind the
# page's buttons, read from workshop.py itself: each with its method, its comments, the arguments it reads and how.
# Run through the Workshop's own address, so each goes through the same checks, My changes and Undo as a click.)
KEPT = [
    (r'^/api/(mcp|together|settings$|quit$|clienterror$)', 'the Workshop\'s own settings'),
    (r'^/api/project/(new|open|adopt|merge|saveas|enable)$|^/api/adopt/pick$', 'switching the user\'s mod'),
    (r'^/api/(mods/delete|backups/(clear|remove|restore)|revert)$', 'deleting or putting back files'),
    (r'^/api/(undo|redo|undo_entry|undo_group)$', 'the user\'s own Undo (undo_last_change takes back yours)'),
    (r'^/api/(launch|play|openmw/start|release/clean_test|test/|link/|saves/use$)', 'starting or driving the game'),
    (r'^/api/(adopt/pick|openmw/pick|openmw/settings/open|assets/(open|showfile|blender)|anim/blender|release/open)$', 'opening windows on the user\'s screen'),
    (r'^/api/(loadorder/save|openmw/settings$|grass/enable$|packs/sources$)', 'the user\'s OpenMW set-up and load order'),
    (r'^/api/(library/(upload|icon)|release/dds|pack/open)$', 'files sent as they are'),
    (r'^/api/ai/', 'the writer on the user\'s PC'),
]
_CAT = {}


def catalogue():
    """{path: {'path', 'method', 'area', 'what', 'args', 'reads', 'kept'}} from workshop.py, read once."""
    if _CAT:
        return _CAT
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workshop.py'), encoding='utf-8').read().split('\n')
    get0 = next(i for i, l in enumerate(src) if l.startswith('    def do_GET'))
    post0 = next(i for i, l in enumerate(src) if l.startswith('    def do_POST'))
    end = next((i for i, l in enumerate(src) if i > post0 + 1 and re.match(r'^(    def |def |class |[A-Za-z@])', l)), len(src))
    starts = [i for i in range(get0, end) if 'u.path' in src[i] and re.search(r"'/api/", src[i])]
    for n, i in enumerate(starts):
        method = 'GET' if i < post0 else 'POST'
        stop = min([j for j in starts if j > i] + [post0 if i < post0 else end])
        block = src[i:stop]
        var = 'q' if method == 'GET' else 'body'
        args = []
        for m in re.finditer(r"\b%s(?:\.get\(|\[)'(\w+)'" % var, '\n'.join(block)):
            if m.group(1) not in args:
                args.append(m.group(1))
        notes = [l.strip().lstrip('#').strip() for l in block[1:8] if l.strip().startswith('#')]
        inline = src[i].split('#', 1)[1].strip() if '#' in src[i] and "'#" not in src[i] else ''
        reads = [l.strip() for l in block if re.search(r'\b%s(\.get\(|\[)' % var, l) and not l.strip().startswith('#')][:3]
        for path in re.findall(r"'(/api/[^']+)'", src[i]):
            if path.endswith('/') or (method + ' ' + path) in _CAT:
                continue
            kept = next((why for pat, why in KEPT if re.search(pat, path)), None)
            _CAT[method + ' ' + path] = {'path': path, 'method': method, 'area': path.split('/')[2],
                          'what': ' '.join(x for x in [inline] + notes if x)[:400] or path,
                          'args': args, 'reads': [r[:220] for r in reads], 'kept': kept}
    return _CAT


# ------------------------------------------------------------------ what agents did, shown in the Workshop window
# (the user, 2026-11-22: an agent added daedra to Seyda Neen and nothing in the Workshop said so or showed them; it
# offered to take over the screen to open the place. Each call is noted here; the page asks with /api/changes and
# follows: it opens the place, selects what was placed or moved, and says what was done.)
def _title(tool):
    t = next((x for x in TOOLS if x['name'] == tool), None)
    return (t or {}).get('title') or tool


def _act(agent, tool, out, steps0, entries, error=None, args=None):
    refs = []
    if isinstance(out, dict):
        pl = out.get('placed')         # (a list of {'ref'} from place_objects; other actions give a count or a key)
        refs = [d.get('ref') for d in pl if isinstance(d, dict) and d.get('ref')] if isinstance(pl, list) else []
        if tool == 'move_object' and isinstance(out.get('ref'), str):
            refs.append(out['ref'])
    texts = [s.get('text') for s in agent.helper.steps[steps0:] if s.get('text')]
    if not texts:
        texts = [_unmarked(e.get('text'), agent.name) for e in entries if e.get('text')]
    for s in agent.helper.steps[steps0:]:
        refs += [r for r in s.get('refs') or [] if r not in refs]
    del agent.helper.steps[:-50]             # (the list a long-running agent keeps: only the last few)
    cell = agent.helper.ctx.get('cell')
    if tool == 'show_user':
        return                                  # (its own note: x_show_user)
    if tool == 'workshop_action' and isinstance(out, dict) and isinstance(out.get('placed'), str):
        refs.append(out['placed'])
    if tool == 'workshop_action' and not texts and entries:
        texts = [_unmarked(e.get('text'), agent.name) for e in entries]
    if tool == 'workshop_action':
        # (the place a Workshop action worked on, from its arguments: the window follows it there)
        aa = (args or {}).get('args') if isinstance((args or {}).get('args'), dict) else {}
        c = aa.get('cell') or aa.get('key') or (out.get('key') if isinstance(out, dict) else None)    # (or the place it made)
        cell = c if isinstance(c, str) and c and (('CELL', c) in agent.db.by_key or c.startswith('#')) else None
    a = {'agent': agent.name, 'tool': tool, 'title': _title(tool), 'changed': bool(entries),
         'text': '; '.join(texts)[:300], 'cell': cell, 'refs': refs[:60], 'error': (error or '')[:300] or None,
         'focus': agent.helper.ctx.get('focus')}
    if tool == 'workshop_action':
        a['title'] = str((args or {}).get('action') or 'a Workshop action').replace('/api/', '')
    _note(a)


def _unmarked(t, name):
    t = str(t or '')
    return t[len('%s%s: ' % (MARK, name)):] if t.startswith('%s%s: ' % (MARK, name)) else t


def _note(a):
    a['t'] = time.time()
    with STATE['lock']:
        STATE['act_n'] += 1
        a['n'] = STATE['act_n']
        STATE['acts'] = (STATE['acts'] + [a])[-40:]


def activity_head():
    """For /api/changes: the newest note's number and what an agent is doing now."""
    with STATE['lock']:
        b = STATE['busy']
        return {'n': STATE['act_n'], 'busy': dict(b, secs=round(time.time() - b['since'])) if b else None}


def activity(since):
    with STATE['lock']:
        return {'n': STATE['act_n'], 'acts': [a for a in STATE['acts'] if a['n'] > since]}


# ------------------------------------------------------------------ HTTP (Streamable HTTP, answered as JSON)
def http(handler, db, lock, method):
    """Answer GET/POST/DELETE /mcp for the Workshop's request handler."""
    from urllib.parse import parse_qs, urlparse
    st = settings()
    STATE['port'] = handler.server.server_address[1]        # (workshop_action runs through this address)

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


# ------------------------------------------------------------------ Claude Code, connected from Settings
# (one button instead of a command to paste in a terminal: the user, 2026-11-22, after `claude` wasn't found and
# npm was blocked by PowerShell's script policy: "IT NEVER WORKS FOR ME". Claude Code keeps the servers it uses for
# every folder in ~/.claude.json, mcpServers; its own command writes them, and without one (Claude Code only inside
# the Claude app) the file is written here, whole, and swapped in.)
def _claude_json():
    # (CLAUDE_CONFIG_DIR, when set, moves Claude Code's settings there)
    return os.path.join(os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~'), '.claude.json')


def claude_cli():
    """The claude command on this PC, or None."""
    import shutil
    found = shutil.which('claude')
    if found:
        return found
    home = os.path.expanduser('~')
    for p in (os.path.join(os.environ.get('APPDATA') or '', 'npm', 'claude.cmd'), os.path.join(home, '.local', 'bin', 'claude.exe'),
              os.path.join(home, '.local', 'bin', 'claude'), os.path.join(home, '.npm-global', 'bin', 'claude')):
        if os.path.isabs(p) and os.path.isfile(p):
            return p
    return None


def claude_code(addr):
    """Claude Code on this PC and the Workshop in it: {'here': bool, 'connected': 'yes' | 'old' (another address,
    an earlier key) | 'no'}."""
    url = None
    try:
        with open(_claude_json(), encoding='utf-8') as f:
            url = ((json.load(f).get('mcpServers') or {}).get(SERVER_NAME) or {}).get('url')
    except (OSError, ValueError, AttributeError):
        pass
    here = bool(claude_cli() or os.path.isfile(_claude_json()))
    return {'here': here, 'connected': 'no' if not url else 'yes' if url == addr else 'old'}


def connect_claude_code(addr):
    """Give Claude Code the Workshop's address, for every folder (Settings › AI › Connect Claude Code)."""
    if not addr:
        raise EditError('Tick "Let coding agents connect" first.')
    cli = claude_cli()
    if cli:
        import subprocess
        import osplat

        def run(*a):
            return subprocess.run([cli] + list(a), capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
                                  creationflags=osplat.NO_WINDOW)
        run('mcp', 'remove', '--scope', 'user', SERVER_NAME)          # (an earlier address: none is fine)
        r = run('mcp', 'add', '--scope', 'user', '--transport', 'http', SERVER_NAME, addr)
        if r.returncode != 0:
            raise EditError('Claude Code said: ' + ((r.stderr or '') + (r.stdout or '')).strip()[:300])
    elif os.path.isfile(_claude_json()):
        p = _claude_json()
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            raise EditError('Claude Code\'s settings file couldn\'t be read (%s): nothing was changed.' % e)
        if not isinstance(d, dict):
            raise EditError('Claude Code\'s settings file isn\'t as expected: nothing was changed.')
        servers = d.get('mcpServers') if isinstance(d.get('mcpServers'), dict) else {}
        servers[SERVER_NAME] = {'type': 'http', 'url': addr}
        d['mcpServers'] = servers
        tmp = p + '.workshop-new'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    else:
        raise EditError('Claude Code isn\'t on this PC yet.')
    st = claude_code(addr)
    if st['connected'] != 'yes':
        raise EditError('Claude Code took it, but its settings don\'t show the Workshop. Nothing else was changed.')
    return st
