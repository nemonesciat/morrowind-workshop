"""The Workshop's AI assistant: Claude, given tools that act on your mod project.

Every change goes through the same editing functions as the buttons in the app,
so it lands in your plugin, shows up in "My mod", and can be undone."""
import json
import math
import re
import threading

import editing
import mapdata
from database import TYPE_NAMES

MODEL = 'claude-opus-5-5'
MAX_STEPS = 30

SYSTEM = """You are the building assistant inside Morrowind Workshop, an editor for OpenMW mods. \
The user is a Morrowind modder working on their own mod. They talk to you in plain language and \
you make the changes with your tools; everything you do is saved into their mod plugin and can be \
undone with one click, so act rather than asking for confirmation on ordinary building requests.

How the world works:
- Positions are in game units (about 1.4 cm each; a person is ~128 tall, a doorway ~150 wide).
  X is east, Y is north, Z is up. An exterior cell is 8192 x 8192 units.
- Interiors are separate cells with their own coordinates.
- "rotation_deg" turns an object around the vertical axis, clockwise seen from above.
- Each object has a size (width along X, depth along Y, height) from its 3D model, at rotation 0.
- When you place something with z = null, the Workshop sets it down on the floor/ground, or on top of \
a table or shelf for small items. Prefer z = null unless you need something specific (e.g. on a wall).

Working style:
- Start by calling look_around to see the space and what kind of place it is, then search for \
fitting objects. Prefer objects that match the place's style (Hlaalu, Redoran, Imperial, common...) \
and the suggestions look_around gives.
- Lay things out sensibly: furniture against walls or around tables, clear walkways and doors, \
items on tables and shelves, nothing overlapping walls. Use the room bounds and existing objects.
- Use only IDs that exist (from search or look_around). Keep to the Morrowind setting.
- When creating new items/NPCs/books, copy a similar existing record with create_record, then \
change its fields. Use IDs prefixed with something short and unique to the mod.
- Finish with a short plain-language summary of what you changed. Don't list raw coordinates.

New interiors:
- To make a new place, call list_building_styles, pick the style that fits the request (e.g. Hlaalu for a \
Balmora house, Velothi for a tomb or a poor dwelling, Imperial for a fort, Dwemer for a ruin), plan the rooms \
on the tile grid and call build_interior. Keep the plan simple and believable: rooms sharing edges, doors \
between rooms that connect, one way out. Name rooms by use (Bedroom, Kitchen, Storeroom, Study...). Then \
call auto_furnish for a quick, sensible base, and add the specific touches the user asked for with \
look_around and place_objects.
- If the user has an outdoor spot open on the World map and wants the place reachable from there, use \
entrance_at_focus.

Dialogue and quests:
- A topic is a word the player clicks in conversation; greetings ("Greeting 0".."Greeting 9") are what \
people say first. The game uses the FIRST line, top to bottom, whose conditions all match, so new lines \
for a specific character go at the top (the default) and more specific lines above general ones.
- Quests are journal topics with numbered stages (10, 20, ... 100). The journal text is written by the \
player character in first person, past tense, like the base game ("Fenas asked me to find her ring.").
- Lines check quest progress with journal conditions (e.g. stage < 10 before the quest starts, = 20 after \
a step) and move it on with result script lines such as: Journal "quest_id" 20, AddTopic "topic", \
Player->AddItem "gold_001" 100, Player->RemoveItem "item_id" 1, Goodbye, \
Choice "Yes" 1 "No" 2 (choice answers are lines with the condition Function Choice = n, placed ABOVE \
the line that offers the choice).
- Speech uses Morrowind's voice and the game's text variables: %PCName, %PCRace, %PCClass, %Name.
- Mentioning a topic word in a line makes it appear in the player's list; use AddTopic otherwise.
- Use read_dialogue first to see what a character already says or what a quest contains.

Characters and scripts:
- edit_character changes an NPC's looks, stats, behaviour, services, travel, inventory and spells.
- write_script writes MWScript and checks it; fix any problems it reports and try again. A script does \
nothing until something runs it: attach_to an object or character, start_with_game, or StartScript from a \
dialogue result."""

TOOLS = [
    {
        'name': 'look_around',
        'description': 'Describe the current cell around the user\'s focus point: style of the place, '
                       'room bounds, floor height, and the objects nearby with their ref key, id, name, '
                       'type, position, rotation and size. Also returns objects that typically appear in '
                       'similar places. Call this before building.',
        'input_schema': {'type': 'object', 'properties': {
            'radius': {'type': 'number', 'description': 'How far around the focus point to list objects, '
                                                        'in game units. Default 1500.'}},
            'required': [], 'additionalProperties': False},
    },
    {
        'name': 'search_objects',
        'description': 'Search every object in the load order by words in its name or ID (e.g. '
                       '"hlaalu chair", "bottle", "candle", "bookshelf"). Returns id, name, type and size.',
        'input_schema': {'type': 'object', 'properties': {
            'query': {'type': 'string'},
            'types': {'type': 'array', 'items': {'type': 'string', 'enum': sorted(editing.PLACEABLE)},
                      'description': 'Optional record types to limit to, e.g. ["STAT","CONT"].'}},
            'required': ['query'], 'additionalProperties': False},
    },
    {
        'name': 'place_objects',
        'description': 'Place one or more objects in the world. z = null sets each one down on the '
                       'surface below it automatically.',
        'input_schema': {'type': 'object', 'properties': {
            'objects': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'id': {'type': 'string'},
                'x': {'type': 'number'}, 'y': {'type': 'number'},
                'z': {'type': ['number', 'null']},
                'rotation_deg': {'type': 'number'},
                'scale': {'type': 'number'}},
                'required': ['id', 'x', 'y', 'z', 'rotation_deg', 'scale'], 'additionalProperties': False}}},
            'required': ['objects'], 'additionalProperties': False},
    },
    {
        'name': 'move_object',
        'description': 'Move, turn or rescale an object already in the cell, by its ref key from '
                       'look_around. Pass null for anything that should stay the same.',
        'input_schema': {'type': 'object', 'properties': {
            'ref': {'type': 'string'},
            'x': {'type': ['number', 'null']}, 'y': {'type': ['number', 'null']},
            'z': {'type': ['number', 'null']}, 'rotation_deg': {'type': ['number', 'null']},
            'scale': {'type': ['number', 'null']}},
            'required': ['ref', 'x', 'y', 'z', 'rotation_deg', 'scale'], 'additionalProperties': False},
    },
    {
        'name': 'delete_objects',
        'description': 'Remove objects from the cell by ref key.',
        'input_schema': {'type': 'object', 'properties': {
            'refs': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['refs'], 'additionalProperties': False},
    },
    {
        'name': 'get_record',
        'description': 'Show the editable fields of a record (item, NPC, container, book, spell...) by ID.',
        'input_schema': {'type': 'object', 'properties': {'id': {'type': 'string'}},
                         'required': ['id'], 'additionalProperties': False},
    },
    {
        'name': 'create_record',
        'description': 'Create a new record by copying an existing one (the template) under a new ID, '
                       'then optionally change fields by their label as shown by get_record (e.g. '
                       '"Name", "Value", "Weight", "Text", "Level").',
        'input_schema': {'type': 'object', 'properties': {
            'template_id': {'type': 'string'},
            'new_id': {'type': 'string', 'description': 'At most 31 characters.'},
            'changes': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'field': {'type': 'string'}, 'value': {'type': 'string'}},
                'required': ['field', 'value'], 'additionalProperties': False}}},
            'required': ['template_id', 'new_id', 'changes'], 'additionalProperties': False},
    },
    {
        'name': 'edit_record',
        'description': 'Change fields of an existing record by field label (see get_record). For '
                       'drop-down fields give the option name; for flags give a comma-separated list of '
                       'the flags that should be on.',
        'input_schema': {'type': 'object', 'properties': {
            'id': {'type': 'string'},
            'changes': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'field': {'type': 'string'}, 'value': {'type': 'string'}},
                'required': ['field', 'value'], 'additionalProperties': False}}},
            'required': ['id', 'changes'], 'additionalProperties': False},
    },
    {
        'name': 'list_building_styles',
        'description': 'The interior building styles (kits of modular room pieces) available in the load '
                       'order, most used first, with their tile size. Call before build_interior.',
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False},
    },
    {
        'name': 'build_interior',
        'description': 'Build a brand-new interior from scratch out of a style\'s modular pieces: floors, '
                       'walls, ceilings, doorways between rooms, a way out with a load door, and basic lights. '
                       'Rooms are rectangles on a grid of tiles (one tile = the style\'s tile size, usually 256 '
                       'units, about 3.5 m): x grows east, y grows north. A cosy single room is about 3x3 tiles, '
                       'a big hall 5x8; corridors are 1 tile wide. Rooms that should connect must share an edge '
                       'and be listed in doors. Rooms can be on several floors (floor 1 = upstairs, -1 = cellar) '
                       'when the style has stairs (list_building_styles says so); each floor is laid out on the '
                       'same grid and stairs are added between floors by themselves, so keep floors at least 3 '
                       'tiles deep. Afterwards the new place becomes the current cell, so look_around and '
                       'place_objects work in it: furnish it next.',
        'input_schema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Name of the place, e.g. "Balmora, Fenas\' House".'},
            'style': {'type': 'string', 'description': 'Style id from list_building_styles.'},
            'rooms': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'name': {'type': 'string'}, 'x': {'type': 'integer'}, 'y': {'type': 'integer'},
                'w': {'type': 'integer', 'description': 'width in tiles (east-west)'},
                'h': {'type': 'integer', 'description': 'depth in tiles (north-south)'},
                'floor': {'type': 'integer', 'description': '0 ground floor (default), 1 upstairs, -1 cellar'}},
                'required': ['name', 'x', 'y', 'w', 'h'], 'additionalProperties': False}},
            'doors': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'rooms': {'type': 'array', 'items': {'type': 'string'}, 'description': 'the two room names'}},
                'required': ['rooms'], 'additionalProperties': False}},
            'exit': {'type': 'object', 'properties': {
                'room': {'type': 'string'}, 'side': {'type': 'string', 'enum': ['N', 'E', 'S', 'W']}},
                'required': ['room', 'side'], 'additionalProperties': False},
            'entrance_at_focus': {'type': 'boolean', 'description': 'Also put a matching door outside, at the '
                                  'focus point of the cell the user has open, linked both ways.'},
            'outside_building': {'type': 'string', 'enum': ['none', 'N', 'E', 'S', 'W'],
                                 'description': 'With entrance_at_focus outdoors: also put up a whole building in the '
                                 'style there (copied from a game house about the size of the rooms), its front door facing '
                                 'this way, instead of just a door. "none" for only a door.'},
            'lighting': {'type': 'string', 'enum': ['dark', 'dim', 'normal', 'bright']}},
            'required': ['name', 'style', 'rooms', 'doors', 'exit', 'entrance_at_focus', 'lighting'],
            'additionalProperties': False},
    },
    {
        'name': 'auto_furnish',
        'description': 'Quickly furnish the rooms of the current interior with fitting furniture and clutter '
                       'from similar places (beds against walls, tables with chairs, things on tables). Works in '
                       'places built from modular room pieces. Give a purpose per room, or none to let it guess '
                       'from the room names and sizes. Afterwards use look_around and place_objects to add the '
                       'special touches the user asked for.',
        'input_schema': {'type': 'object', 'properties': {
            'rooms': {'type': ['array', 'null'], 'items': {'type': 'object', 'properties': {
                'room': {'type': 'string', 'description': 'room name (as build_interior named it) or number'},
                'purpose': {'type': 'string', 'enum': ['bedroom', 'living', 'kitchen', 'storage', 'study', 'shop',
                                                       'shrine', 'hall', 'tavern', 'none']}},
                'required': ['room', 'purpose'], 'additionalProperties': False}}},
            'required': ['rooms'], 'additionalProperties': False},
    },
    {
        'name': 'read_dialogue',
        'description': 'Read dialogue: what a character says (by NPC id), the lines of a topic or greeting '
                       '(by topic name), or a quest\'s title and stages (by quest id). Give one of them.',
        'input_schema': {'type': 'object', 'properties': {
            'character': {'type': ['string', 'null']}, 'topic': {'type': ['string', 'null']},
            'quest': {'type': ['string', 'null']}},
            'required': ['character', 'topic', 'quest'], 'additionalProperties': False},
    },
    {
        'name': 'save_quest',
        'description': 'Create a quest, or replace the stages of one in this mod. Stages are numbered '
                       '(e.g. 10, 20, 100); mark the last one finished.',
        'input_schema': {'type': 'object', 'properties': {
            'id': {'type': 'string', 'description': 'Quest ID, at most 31 characters, e.g. "MyMod_LostRing".'},
            'title': {'type': 'string', 'description': 'Name shown in the journal.'},
            'stages': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'index': {'type': 'integer'}, 'text': {'type': 'string'}, 'finished': {'type': 'boolean'}},
                'required': ['index', 'text', 'finished'], 'additionalProperties': False}}},
            'required': ['id', 'title', 'stages'], 'additionalProperties': False},
    },
    {
        'name': 'add_dialogue_line',
        'description': 'Add a line to a topic or greeting (created first if it does not exist; greetings are '
                       '"Greeting 0".."Greeting 9", use "Greeting 5" for ordinary characters). Conditions all '
                       'have to match for the line to be used.',
        'input_schema': {'type': 'object', 'properties': {
            'topic': {'type': 'string'},
            'speaker': {'type': ['string', 'null'], 'description': 'NPC id who says it, or null for anyone'},
            'text': {'type': 'string', 'description': 'At most 1023 characters.'},
            'conditions': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'kind': {'type': 'string', 'enum': ['journal', 'item', 'dead', 'global', 'choice']},
                'name': {'type': ['string', 'null'], 'description': 'quest id, item id, NPC id or global name; null for choice'},
                'op': {'type': 'string', 'enum': ['=', '!=', '>', '>=', '<', '<=']},
                'value': {'type': 'number'}},
                'required': ['kind', 'name', 'op', 'value'], 'additionalProperties': False}},
            'result': {'type': ['string', 'null'], 'description': 'Result script lines, run after the line is said.'},
            'position': {'type': 'string', 'enum': ['top', 'bottom'],
                         'description': 'top (default) wins over existing lines.'}},
            'required': ['topic', 'speaker', 'text', 'conditions', 'result', 'position'], 'additionalProperties': False},
    },
    {
        'name': 'write_script',
        'description': 'Create or replace an MWScript (begin <id> ... end). The script is checked first; if it has '
                       'errors nothing is saved and the problems come back to fix. Optionally put it on an object or '
                       'character (attach_to = their ID) or make it run from the start of the game. Object scripts '
                       'usually begin with: if ( MenuMode == 1 ) return endif. Declare every variable (short/long/'
                       'float) at the top. Use OnActivate / OnPCAdd / OnDeath to react, Journal / GetJournalIndex for '
                       'quests, Enable/Disable to show and hide things.',
        'input_schema': {'type': 'object', 'properties': {
            'id': {'type': 'string', 'description': 'Script ID: letters, numbers and _ only, at most 31 characters.'},
            'text': {'type': 'string', 'description': 'The whole script text.'},
            'attach_to': {'type': ['string', 'null'], 'description': 'ID of an object/character to run it on, or null.'},
            'start_with_game': {'type': 'boolean', 'description': 'Run as a global script from the start of the game.'}},
            'required': ['id', 'text', 'attach_to', 'start_with_game'], 'additionalProperties': False},
    },
    {
        'name': 'edit_character',
        'description': 'Change an NPC: any of name, race, cls (class ID), faction, rank, level, female, essential, '
                       'respawn, auto (stats worked out from race/class/level), attributes (8 numbers), skills (27), '
                       'health, magicka, fatigue, disposition, reputation, gold, hello, fight, flee, alarm (0-100), '
                       'services (bit flags: weapons 1, armor 2, clothing 4, books 8, ingredients 16, picks 32, '
                       'probes 64, lights 128, apparatus 256, repair items 512, misc 1024, spells 2048, magic items '
                       '4096, potions 8192, training 16384, spellmaking 32768, enchanting 65536, repairs 131072; '
                       'with auto stats the class decides services instead), script, head, hair, scale, '
                       'ai (list of {kind: wander, distance, duration, idle: [8 numbers], repeat}), travel (list of '
                       '{p: [x,y,z,rx,ry,rz], cell}); plus add_items [{id, count, restock}], remove_items [ids], '
                       'add_spells [ids], remove_spells [ids]. Read first with get_record if unsure.',
        'input_schema': {'type': 'object', 'properties': {
            'id': {'type': 'string', 'description': 'NPC ID.'},
            'changes': {'type': 'object', 'description': 'Only the fields to change.'}},
            'required': ['id', 'changes']},
    },
]


class ToolError(Exception):
    pass


class Assistant:
    def __init__(self, db, get_key):
        self.db = db
        self.get_key = get_key
        self.messages = []
        self.lock = threading.Lock()
        self.ctx = {}
        self.steps = []
        self.status = ''

    def reset(self):
        self.messages = []

    def usage_add(self, resp):
        """Add up what a request used (tokens are what Anthropic bills by)."""
        u = getattr(resp, 'usage', None)
        if u is None:
            return
        t = self.__dict__.setdefault('usage', {'requests': 0, 'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0})
        t['requests'] += 1
        t['input'] += getattr(u, 'input_tokens', 0) or 0
        t['output'] += getattr(u, 'output_tokens', 0) or 0
        t['cache_read'] += getattr(u, 'cache_read_input_tokens', 0) or 0
        t['cache_write'] += getattr(u, 'cache_creation_input_tokens', 0) or 0

    def _client(self):
        try:
            import anthropic
        except ImportError:
            raise ToolError('The "anthropic" Python package is missing. Close the Workshop and start it '
                            'again with Start Morrowind Workshop.bat so it can be installed.')
        key = self.get_key()
        opts = dict(
            # Only ask for gzip replies: an old "Brotli" package (e.g. Anaconda's 1.0.9) makes the
            # client crash while unpacking brotli replies, after the request was already billed.
            default_headers={'Accept-Encoding': 'gzip, deflate'},
            # A retry re-sends (and re-bills) the whole request, so allow at most one.
            max_retries=1,
        )
        return anthropic.Anthropic(api_key=key, **opts) if key else anthropic.Anthropic(**opts)

    @staticmethod
    def _api_error(e):
        """A plain-language message for a failed request, with the real cause."""
        import anthropic
        if isinstance(e, anthropic.AuthenticationError):
            return 'The API key was not accepted. Check it under AI settings.'
        if isinstance(e, anthropic.PermissionDeniedError):
            return 'This API key is not allowed to use the model.'
        if isinstance(e, anthropic.RateLimitError):
            return 'Too many requests right now. Wait a minute and try again.'
        if isinstance(e, anthropic.APITimeoutError):
            return 'The Claude API took too long to answer. Try again, or ask for a smaller step.'
        if isinstance(e, anthropic.APIConnectionError):
            cause = e.__cause__ or e.__context__
            if cause is None or type(cause).__name__ in ('ConnectError', 'ConnectTimeout', 'gaierror', 'OSError'):
                return 'Could not reach the Claude API. Check your internet connection.'
            return ('The answer from the Claude API could not be read on this PC (%s: %s). The request may '
                    'still have been billed. Please tell Claude Code about this message.' % (type(cause).__name__, cause))
        if isinstance(e, anthropic.APIStatusError):
            return 'The Claude API returned an error (%s): %s' % (e.status_code, e.message)
        return 'Could not use the Claude API: %s' % e

    # ------------------------------------------------------------------ chat
    def chat(self, text, ctx):
        """Run one user request to completion. Returns reply text and the list of steps."""
        import anthropic
        with self.lock:
            self.ctx = ctx
            self.steps = []
            self.usage = {'requests': 0, 'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0}
            self.opened = None
            client = self._client()
            depth_before = editing.undo_depth(self.db)
            info = self._context_line()
            self.messages.append({'role': 'user', 'content': '[%s]\n\n%s' % (info, text)})
            reply = ''
            try:
                for _ in range(MAX_STEPS):
                    self.status = 'Thinking…'
                    resp = client.beta.messages.create(
                        model=MODEL,
                        max_tokens=16000,
                        system=SYSTEM,
                        tools=TOOLS,
                        messages=self.messages,
                        output_config={'effort': 'medium'},
                        cache_control={'type': 'ephemeral'},   # each step re-reads the conversation cheaply
                        betas=['server-side-fallback-2026-07-01'],
                        fallbacks='default',
                    )
                    self.usage_add(resp)
                    self.messages.append({'role': 'assistant', 'content': resp.content})
                    texts = [b.text for b in resp.content if b.type == 'text']
                    if texts:
                        reply = '\n\n'.join(texts)
                    if resp.stop_reason == 'refusal':
                        reply = reply or 'Sorry, I can\'t help with that request.'
                        break
                    uses = [b for b in resp.content if b.type == 'tool_use']
                    if not uses:
                        break
                    results = []
                    for u in uses:
                        try:
                            out = self.run_tool(u.name, u.input or {})
                            results.append({'type': 'tool_result', 'tool_use_id': u.id,
                                            'content': json.dumps(out, ensure_ascii=False)})
                        except (ToolError, editing.EditError) as e:
                            results.append({'type': 'tool_result', 'tool_use_id': u.id,
                                            'content': 'Error: %s' % e, 'is_error': True})
                            self.steps.append({'tool': u.name, 'text': 'Problem: %s' % e, 'error': True})
                    self.messages.append({'role': 'user', 'content': results})
                else:
                    reply = (reply + '\n\n' if reply else '') + '(Stopped after %d steps.)' % MAX_STEPS
            except anthropic.AnthropicError as e:
                self._drop_unfinished()
                msg = self._api_error(e)
                done = [s['text'] for s in self.steps if not s.get('error')]
                if done:
                    # earlier steps already changed the mod: say so (they can be undone as usual)
                    msg += ' Before that, the assistant had already done this (see My mod to undo): ' + '; '.join(done[:8])
                raise ToolError(msg)
            finally:
                self.status = ''
            changed = editing.undo_depth(self.db) > depth_before
            return {'reply': reply, 'steps': self.steps, 'changed': changed, 'undo_to': depth_before, 'usage': self.usage,
                    'open_cell': self.opened}

    def _drop_unfinished(self):
        # keep history valid: remove the trailing turn that never got an answer
        while self.messages and self.messages[-1]['role'] == 'user':
            self.messages.pop()
            if self.messages and self.messages[-1]['role'] == 'assistant':
                self.messages.pop()

    def _context_line(self):
        c = self.ctx
        talk = []
        if c.get('npc'):
            talk.append('the user is editing what the character "%s" says' % c['npc'])
        if c.get('quest'):
            talk.append('the user has the quest "%s" open' % c['quest'])
        if c.get('topic'):
            talk.append('the user has the topic "%s" open' % c['topic'])
        info = mapdata.cell_info(self.db, c.get('cell')) if c.get('cell') else None
        if not info:
            return '; '.join(talk + ['The user has no cell open on the World map.'])
        parts = talk + ['Current cell: %s (%s)' % (info['id'], 'interior' if info['interior'] else 'exterior')]
        if c.get('focus'):
            parts.append('focus point x=%.0f y=%.0f' % tuple(c['focus'][:2]))
        if c.get('sel'):
            parts.append('selected object ref=%s' % c['sel'])
        if c.get('cut') is not None:
            parts.append('looking at the floor below height %.0f' % c['cut'])
        return '; '.join(parts)

    # ------------------------------------------------------------------ tools
    def run_tool(self, name, args):
        fn = getattr(self, 't_' + name, None)
        if not fn:
            raise ToolError('Unknown tool %s' % name)
        return fn(**args)

    # ----- building interiors from scratch
    def t_list_building_styles(self):
        import builder
        return {'styles': [{'id': s['id'], 'name': s['name'], 'tile': s['tile'], 'door_frames': s['doorways'],
                            'one_tile_rooms_ok': s['small_rooms']} for s in builder.styles(self.db)[:40]],
                'note': 'Styles without one_tile_rooms_ok need rooms and corridors at least 2 tiles wide, ending in rooms.'}

    def t_build_interior(self, name, style, rooms, doors, exit, entrance_at_focus=False, lighting='normal',
                         outside_building='none'):
        import builder
        entrance = None
        if entrance_at_focus:
            c = self.ctx
            if not c.get('cell') or not (c.get('focus') or c.get('sel')):
                raise ToolError('No place is open on the World map to put the outside door in. Build it without '
                                'an entrance, or ask the user to open the spot first.')
            fx, fy = (c.get('focus') or [None, None])[:2]
            if fx is None:
                _k, m = self._cellmap()
                r = next((r for r in m['refs'] if r['k'] == c['sel']), None)
                fx, fy = (r['p'][0], r['p'][1]) if r else (0, 0)
            entrance = {'cell': c['cell'], 'x': fx, 'y': fy, 'z': None, 'rz': 0}
            if outside_building in ('N', 'E', 'S', 'W') and str(c['cell']).startswith('#'):
                import math
                import outside
                T = 256
                shells = outside.for_rooms(self.db, style,
                                           (max(r['x'] + r['w'] for r in rooms) - min(r['x'] for r in rooms)) * T,
                                           (max(r['y'] + r['h'] for r in rooms) - min(r['y'] for r in rooms)) * T)
                if not shells:
                    raise ToolError('No outside buildings in the game lead into the %s style; build it with just a door.' % style)
                entrance.update(building=shells[0]['id'], facing={'N': 0, 'E': math.pi / 2, 'S': math.pi, 'W': 3 * math.pi / 2}[outside_building])
        out = builder.build_house(self.db, name, style, rooms, doors, exit, entrance, lighting)
        # from now on, work inside the new place
        r0 = out['rooms'][0]
        self.ctx = dict(self.ctx, cell=out['key'], focus=[(r0['x_min'] + r0['x_max']) / 2, (r0['y_min'] + r0['y_max']) / 2], sel=None)
        self.opened = out['key']
        self.steps.append({'tool': 'build_interior', 'text': 'Built "%s" (%s, %d rooms)' % (name, out['style'], len(rooms))})
        out['note'] = ('The new place is now the current cell. Furnish each room using its x/y range '
                       'and its floor_z (0 on the ground floor). Keep furniture inside the ranges and away from the '
                       'way out and the stairs.')
        return out

    def t_auto_furnish(self, rooms=None):
        import furnish
        key, _m = self._cellmap()
        info = furnish.rooms(self.db, key)
        plan = None
        if rooms:
            plan = []
            for want in rooms:
                ref = str(want['room']).strip().lower()
                r = next((x for x in info['rooms'] if x['name'].lower() == ref or str(x['id'] + 1) == ref
                          or str(x['id']) == ref), None)
                if r:
                    plan.append({'id': r['id'], 'purpose': want['purpose']})
            for r in info['rooms']:                      # rooms not mentioned: their guessed purpose
                if not any(p['id'] == r['id'] for p in plan):
                    plan.append({'id': r['id'], 'purpose': r['purpose']})
        out = furnish.furnish(self.db, key, plan)
        self.steps.append({'tool': 'auto_furnish', 'text': 'Furnished %d rooms (%d things)' % (len(out['rooms']), out['placed'])})
        out['rooms_found'] = [{'name': r['name'], 'purpose': r['purpose'], 'x_min': r['x_min'], 'x_max': r['x_max'],
                               'y_min': r['y_min'], 'y_max': r['y_max']} for r in info['rooms']]
        return out

    # ----- dialogue
    def t_read_dialogue(self, character=None, topic=None, quest=None):
        import dialogue
        brief = lambda ln: {'id': ln['inam'], 'speaker': ln['actor'] or None, 'text': ln['text'],
                            'conditions': [self._cond_text(c) for c in ln['conds']], 'result': ln['result'] or None,
                            'mine': ln['mine']}
        try:
            if character:
                c = dialogue.character(self.db, character)
                return {'character': c['id'], 'name': c['name'], 'race': c.get('race'), 'class': c.get('cls'),
                        'faction': c.get('faction'),
                        'topics': [{'topic': t['id'], 'lines': [brief(x) for x in t['lines']][:30]} for t in c['topics']][:40]}
            if quest:
                return dialogue.quest(self.db, quest)
            if topic:
                t = dialogue.topic(self.db, topic)
                return {'topic': t['id'], 'type': dialogue.TYPES[t['type']], 'lines_total': len(t['lines']),
                        'first_lines': [brief(x) for x in t['lines'][:40]]}
        except editing.EditError as e:
            raise ToolError(str(e))
        raise ToolError('Give a character, topic or quest.')

    @staticmethod
    def _cond_text(c):
        import dialogue
        if c['kind'] == 'function':
            name = dialogue.FUNCTIONS[c['func']] if 0 <= c.get('func', -1) < len(dialogue.FUNCTIONS) else 'function'
        else:
            name = '%s %s' % (c['kind'], c['name'])
        return '%s %s %s' % (name, c['op'], c['value'])

    def t_save_quest(self, id, title, stages):
        import dialogue
        key = dialogue.save_quest(self.db, id, title, [dict(s) for s in stages])
        self.steps.append({'tool': 'save_quest', 'text': 'Saved quest "%s" (%d stages)' % (title, len(stages))})
        return dialogue.quest(self.db, key)

    def t_add_dialogue_line(self, topic, speaker, text, conditions, result, position='top'):
        import dialogue
        key = topic.strip().lower()
        if not self.db.by_key.get(('DIAL', key)) or all(v in self.db.dead for v in self.db.by_key[('DIAL', key)]):
            kind = 2 if key.startswith('greeting ') else 0
            dialogue.create_topic(self.db, topic.strip(), kind)
        conds = []
        for c in conditions:
            if c['kind'] == 'choice':
                conds.append({'kind': 'function', 'func': dialogue.CHOICE, 'op': c['op'], 'value': c['value']})
            else:
                conds.append({'kind': c['kind'], 'name': c.get('name') or '', 'op': c['op'], 'value': c['value']})
        inam = dialogue.save_line(self.db, key, {'actor': speaker or '', 'text': text, 'conds': conds,
                                                 'result': result or ''},
                                  where={'bottom': True} if position == 'bottom' else {'top': True})
        self.steps.append({'tool': 'add_dialogue_line', 'text': 'Added a line to "%s"%s' % (
            topic, (' for ' + speaker) if speaker else '')})
        return {'ok': True, 'line_id': inam}

    def t_write_script(self, id, text, attach_to=None, start_with_game=False):
        import mwscript
        exists = mwscript._winner(self.db, id) is not None
        res = mwscript.check(self.db, text, id)
        if res['errors']:
            # don't save a script the game would refuse; hand the problems back to fix
            return {'saved': False, 'problems': res['messages']}
        out = mwscript.save(self.db, id, text, create=not exists)
        if attach_to:
            out = mwscript.attach(self.db, id, attach_to)
        if start_with_game:
            out = mwscript.attach(self.db, id, '*start*')
        self.steps.append({'tool': 'write_script', 'text': '%s script "%s"%s' % (
            'Changed' if exists else 'Wrote', id, (' on ' + attach_to) if attach_to else '')})
        return {'saved': True, 'warnings': [m for m in out['check']['messages'] if m['sev'] != 'info'],
                'used_by': [u['label'] for u in out['used_by']]}

    def t_edit_character(self, id, changes):
        import npc
        o = npc.read(self.db, id)
        for k, v in changes.items():
            if k in ('add_items', 'remove_items', 'add_spells', 'remove_spells'):
                continue
            if k not in o or k in ('id', 'i', 'placed', 'calc', 'src', 'mine', 'created'):
                raise ToolError('Unknown character field "%s".' % k)
            o[k] = v
        for it in changes.get('add_items') or []:
            o['items'].append({'id': it.get('id'), 'count': it.get('count') or 1, 'restock': bool(it.get('restock'))})
        rm = {x.lower() for x in changes.get('remove_items') or []}
        o['items'] = [x for x in o['items'] if x['id'].lower() not in rm]
        o['spells'] += [{'id': s} for s in changes.get('add_spells') or []]
        rs = {x.lower() for x in changes.get('remove_spells') or []}
        o['spells'] = [x for x in o['spells'] if x['id'].lower() not in rs]
        r = npc.save(self.db, id, o)
        self.steps.append({'tool': 'edit_character', 'text': 'Changed character "%s"' % r['name']})
        return {k: r[k] for k in ('id', 'name', 'race', 'cls', 'level', 'auto', 'essential', 'fight', 'alarm',
                                  'services', 'gold', 'script', 'ai', 'travel') if k in r} | {
            'items': [i['id'] + ' x' + str(i['count']) for i in r['items']], 'spells': [s['id'] for s in r['spells']]}

    def draft(self, req):
        """A few suggestions for one line of dialogue or journal text (nothing is saved)."""
        import dialogue
        client = self._client()
        parts = ['Write %s for a Morrowind mod.' % {
            'journal': 'a journal entry (first person, past tense, one or two sentences, like the base game)',
            'greeting': 'a greeting (what the character says when the player starts talking to them)',
            'topic': 'a dialogue line for the topic "%s"' % (req.get('topic') or ''),
            'title': 'a short quest title for the journal'}.get(req.get('kind'), 'a dialogue line')]
        if req.get('npc'):
            try:
                c = dialogue.character(self.db, req['npc'])
                parts.append('Speaker: %s, %s %s%s.' % (c['name'] or c['id'], c.get('race') or '', c.get('cls') or '',
                                                        (', member of ' + c['faction']) if c.get('faction') else ''))
                said = [x['text'] for t in c['topics'] for x in t['lines']][:8]
                if said:
                    parts.append('Things they already say: ' + ' | '.join(said))
            except editing.EditError:
                pass
        if req.get('quest'):
            try:
                q = dialogue.quest(self.db, req['quest'])
                parts.append('Quest "%s": ' % q['title'] + ' | '.join('%d: %s' % (s['index'], s['text']) for s in q['stages']))
            except editing.EditError:
                pass
        if req.get('brief'):
            parts.append('What it should say or do: ' + req['brief'])
        if req.get('current'):
            parts.append('Current draft to improve: ' + req['current'])
        parts.append('Keep it in Morrowind\'s voice and lore. You may use %PCName, %PCRace, %PCClass. '
                     'Give exactly three different versions, each on its own line starting with "- ". No other text.')
        import anthropic
        try:
            resp = client.messages.create(model=MODEL, max_tokens=1500, messages=[{'role': 'user', 'content': '\n'.join(parts)}])
        except anthropic.AnthropicError as e:
            raise ToolError(self._api_error(e))
        self.usage_add(resp)
        text = '\n'.join(b.text for b in resp.content if b.type == 'text')
        opts = [l.strip()[2:].strip() for l in text.splitlines() if l.strip().startswith('- ')]
        u = resp.usage
        return {'options': opts[:3] or [text.strip()],
                'usage': {'requests': 1, 'input': u.input_tokens, 'output': u.output_tokens, 'cache_read': 0, 'cache_write': 0}}

    def effect_lua(self, req):
        """The Lua for one step of one of the user's own magic effects (Create > New magic effect), from a plain
        description: the body of a function(ctx), run as the effect lands, each second or as it ends, with the
        helpers myeffects.ACTOR_LUA gives it. Nothing is saved; the maker shows it for the user to keep."""
        client = self._client()
        phase = {'land': 'once, as the effect lands on them', 'second': 'once a second while the effect lasts',
                 'end': 'once, as the effect ends'}.get(req.get('when'), 'once, as the effect lands on them')
        prompt = '\n'.join([
            'Write OpenMW Lua (OpenMW 0.51, Lua 5.1 / LuaJIT) for a custom Morrowind magic effect.',
            'The code is the BODY of a function(ctx) in a local script attached to the actor the effect is on. It runs %s.' % phase,
            'Effect: %s. %s' % (req.get('name') or 'a custom effect', req.get('description') or ''),
            'What this step should do: ' + (req.get('brief') or ''),
            'ctx has: ctx.self (openmw.self, the actor it is on), ctx.caster (GameObject or nil), ctx.magnitude (number),',
            'ctx.dt (seconds since last call), ctx.phase ("land"|"second"|"end"), ctx.state (a table kept for this cast),',
            'the modules ctx.core, ctx.types, ctx.util, ctx.nearby (openmw.nearby: nearby.actors, nearby.castRay),',
            'and helpers: ctx.change(stat, amount) with stat "health"|"magicka"|"fatigue" (on the actor itself);',
            'ctx.push(feet) away from the caster; ctx.pull(feet) towards the caster; ctx.launch(feet) up; ctx.dash(feet) forward;',
            'ctx.scale(factor) (restored when it ends); ctx.weather(name) with name one of %s;' % ', '.join(__import__('myeffects').WEATHERS),
            'ctx.cast(spellId) casts a spell record on them; ctx.message(text) shows the player a message;',
            'ctx.world(kind, data) for the global script: kinds "teleport" {cell,x,y,z}, "spawn" {id}, "global" {name,value}.',
            'To affect OTHER actors, send them an event: other:sendEvent("WS_MyEffectStat", {stat = "health", amount = -5}).',
            'A local script may only change ITSELF; it can read others. Use only these and standard OpenMW Lua APIs; no require().',
            'One foot is about 22 game units. Keep it short and safe (check ctx.caster for nil and :isValid()).',
            'Answer with the code only, no explanation, no ``` fences.'])
        import anthropic
        try:
            resp = client.messages.create(model=MODEL, max_tokens=1500, messages=[{'role': 'user', 'content': prompt}])
        except anthropic.AnthropicError as e:
            raise ToolError(self._api_error(e))
        self.usage_add(resp)
        code = '\n'.join(b.text for b in resp.content if b.type == 'text').strip()
        code = re.sub(r'^```\w*\n|\n?```$', '', code).strip()
        import lua_check
        probs = [p for p in lua_check.check('local function f(ctx)\n%s\nend\nreturn {}' % code, 'NPC') if p['level'] == 'error']
        u = resp.usage
        return {'code': code, 'problems': [{'line': max(1, p['line'] - 1), 'text': p['text']} for p in probs],
                'usage': {'requests': 1, 'input': u.input_tokens, 'output': u.output_tokens, 'cache_read': 0, 'cache_write': 0}}

    def _cellmap(self):
        key = self.ctx.get('cell')
        if not key:
            raise ToolError('No cell is open. Ask the user to open a place on the World map first.')
        m = mapdata.cellmap(self.db, key)
        if not m.get('exists'):
            raise ToolError('The open cell does not exist.')
        return key, m

    @staticmethod
    def _size(b, s=1.0):
        return [round((b[3] - b[0]) * s), round((b[4] - b[1]) * s), round((b[5] - b[2]) * s)] if b else None

    def t_look_around(self, radius=1500):
        key, m = self._cellmap()
        focus = self.ctx.get('focus')
        sel = self.ctx.get('sel')
        refs = m['refs']
        if sel:
            sr = next((r for r in refs if r['k'] == sel), None)
            if sr:
                focus = sr['p'][:2]
        if not focus:
            xs = [r['p'][0] for r in refs] or [0]
            ys = [r['p'][1] for r in refs] or [0]
            focus = [sum(xs) / len(xs), sum(ys) / len(ys)]
        fx, fy = focus[0], focus[1]
        radius = max(200, min(float(radius or 1500), 6000))
        near = [r for r in refs if math.hypot(r['p'][0] - fx, r['p'][1] - fy) <= radius]
        cut = self.ctx.get('cut')
        if cut is not None:
            near = [r for r in near if r['p'][2] <= cut]
        near.sort(key=lambda r: math.hypot(r['p'][0] - fx, r['p'][1] - fy))
        arch = [r for r in near if r.get('arch')]
        if arch:
            xs = [r['p'][0] + v * (r['s'] or 1) for r in arch if r['b'] for v in (r['b'][0], r['b'][3])]
            ys = [r['p'][1] + v * (r['s'] or 1) for r in arch if r['b'] for v in (r['b'][1], r['b'][4])]
            bounds = {'x_min': round(min(xs)), 'x_max': round(max(xs)), 'y_min': round(min(ys)),
                      'y_max': round(max(ys))} if xs else None
        else:
            bounds = None
        floor = mapdata.surface_z(self.db, refs, m['interior'], fx, fy, None, 1.0, 'STAT', cut)
        pal = mapdata.palette(self.db, key, limit=12)

        def row(r):
            d = {'ref': r['k'], 'id': r['id'], 'name': r['name'], 'type': TYPE_NAMES.get(r['type'], r['type']),
                 'x': round(r['p'][0]), 'y': round(r['p'][1]), 'z': round(r['p'][2]),
                 'rotation_deg': round(math.degrees(r['p'][5])) % 360, 'size': self._size(r['b'], r['s'] or 1)}
            if r.get('arch'):
                d['structure'] = True
            if r['mine']:
                d['added_by_this_mod'] = True
            return d
        rows = [row(r) for r in near[:150]]
        return {
            'cell': m['id'], 'interior': m['interior'], 'style': pal['style'] or 'unknown',
            'focus': {'x': round(fx), 'y': round(fy)}, 'floor_z_at_focus': floor,
            'structure_bounds_nearby': bounds,
            'objects_nearby': rows, 'objects_listed': len(rows), 'objects_in_cell': len(refs),
            'typical_for_places_like_this': {g['name']: [{'id': i['id'], 'name': i['name'], 'size': i['size']}
                                                          for i in g['items']] for g in pal['groups']},
        }

    def t_search_objects(self, query, types=None):
        types = [t for t in (types or []) if t in editing.PLACEABLE] or sorted(editing.PLACEABLE)
        r = self.db.search(query, types, None, 0, 25)
        out = []
        for row in r['rows']:
            b = mapdata.object_bounds(self.db, row['i'])
            out.append({'id': row['id'], 'name': row['name'], 'type': TYPE_NAMES.get(row['type'], row['type']),
                        'size': self._size(b), 'from': row['plugin']})
        self.steps.append({'tool': 'search', 'text': 'Searched for "%s" (%d found)' % (query, r['total'])})
        return {'total_matches': r['total'], 'results': out}

    def t_place_objects(self, objects):
        key, m = self._cellmap()
        done = []
        for o in objects[:60]:
            x, y = float(o['x']), float(o['y'])
            ck = key if m['interior'] else '#%d,%d' % (math.floor(x / 8192), math.floor(y / 8192))
            z = o.get('z')
            rot = math.radians(float(o.get('rotation_deg') or 0))
            s = float(o.get('scale') or 1.0)
            rk = editing.place_ref(self.db, ck, o['id'], [x, y, None if z is None else float(z), 0, 0, rot], s,
                                   self.ctx.get('cut'))
            done.append({'id': o['id'], 'ref': rk})
        names = ', '.join(sorted({d['id'] for d in done}))
        self.steps.append({'tool': 'place', 'text': 'Placed %d object%s: %s' % (len(done), '' if len(done) == 1 else 's', names),
                           'refs': [d['ref'] for d in done]})
        return {'placed': done}

    def _find_ref(self, refkey):
        key, m = self._cellmap()
        if not m['interior']:
            # the ref may live in a neighbouring exterior cell
            for dx in (0, -1, 1):
                for dy in (0, -1, 1):
                    ck = '#%d,%d' % (m['gx'] + dx, m['gy'] + dy)
                    mm = m if (dx, dy) == (0, 0) else mapdata.cellmap(self.db, ck)
                    r = next((r for r in mm.get('refs', []) if r['k'] == refkey), None)
                    if r:
                        return ck, r
        r = next((r for r in m['refs'] if r['k'] == refkey), None)
        if not r:
            raise ToolError('No object with ref %s in this cell. Use look_around to get ref keys.' % refkey)
        return key, r

    def t_move_object(self, ref, x=None, y=None, z=None, rotation_deg=None, scale=None):
        ck, r = self._find_ref(ref)
        p = list(r['p'])
        if x is not None:
            p[0] = float(x)
        if y is not None:
            p[1] = float(y)
        if z is not None:
            p[2] = float(z)
        if rotation_deg is not None:
            p[5] = math.radians(float(rotation_deg))
        editing.move_ref(self.db, ck, ref, p, float(scale) if scale is not None else None)
        self.steps.append({'tool': 'move', 'text': 'Moved %s' % (r['name'] or r['id']), 'refs': [ref]})
        return {'ok': True}

    def t_delete_objects(self, refs):
        names = []
        for rk in refs[:60]:
            ck, r = self._find_ref(rk)
            editing.delete_ref(self.db, ck, rk)
            names.append(r['name'] or r['id'])
        self.steps.append({'tool': 'delete', 'text': 'Removed %s' % ', '.join(names)})
        return {'removed': len(names)}

    def _record_index(self, rid, prefer=None):
        lst = self.db.by_id.get(rid.lower())
        if not lst:
            raise ToolError('No record with ID "%s".' % rid)
        live = [i for i in lst if self.db.winner[i] and self.db.recs[i][0] not in ('INFO', 'CELL', 'DIAL')]
        if not live:
            raise ToolError('No editable record with ID "%s".' % rid)
        return live[-1]

    def _fields(self, i):
        d = self.db.record(i)
        out = []
        for f in d['fields']:
            e = f.get('edit')
            item = {'field': f['label'], 'value': f['value']}
            if e and e.get('opts'):
                item['options'] = e['opts']
            if e and e.get('bits'):
                item['flags'] = [n for _b, n in e['bits']]
            if not e:
                item['read_only'] = True
            out.append(item)
        if d.get('script') is not None:
            out.append({'field': 'Script', 'value': d['script'][:4000]})
        return d, out

    def t_get_record(self, id):
        i = self._record_index(id)
        d, fields = self._fields(i)
        return {'id': d['id'], 'type': d['type_label'], 'from': d['plugin'], 'fields': fields}

    def _apply_named(self, i, changes):
        d = self.db.record(i)
        edits = []
        for ch in changes:
            label = ch['field'].strip().lower()
            if label == 'script' and d.get('script_edit'):
                edits.append(dict(d['script_edit'], value=ch['value']))
                continue
            f = next((f for f in d['fields'] if f['label'].lower() == label and f.get('edit')), None)
            if not f:
                valid = sorted({f['label'] for f in d['fields'] if f.get('edit')})
                raise ToolError('No editable field "%s". Editable fields: %s' % (ch['field'], ', '.join(valid)))
            e, v = f['edit'], ch['value']
            if e.get('opts'):
                low = [o.lower() for o in e['opts']]
                if str(v).lower() in low:
                    v = low.index(str(v).lower())
                elif str(v).lower() == 'none':
                    v = -1
                else:
                    try:
                        v = int(v)
                    except ValueError:
                        raise ToolError('"%s" must be one of: %s' % (f['label'], ', '.join(e['opts'])))
            elif e.get('bits'):
                want = {w.strip().lower() for w in str(v).split(',') if w.strip()}
                known = 0
                v = 0
                for bit, n in e['bits']:
                    known |= bit
                    if n.lower() in want:
                        v |= bit
                v |= (e.get('raw') or 0) & ~known
            edits.append(dict(e, value=v))
        if edits:
            return editing.edit_record(self.db, i, edits)
        return i

    def t_create_record(self, template_id, new_id, changes):
        i = self._record_index(template_id)
        ni = editing.duplicate_record(self.db, i, new_id)
        ni = self._apply_named(ni, changes or [])
        r = self.db.recs[ni]
        self.steps.append({'tool': 'create', 'text': 'Created %s "%s" (%s)' % (TYPE_NAMES.get(r[0], r[0]), r[2] or r[1], r[1]),
                           'record': ni})
        return {'created': r[1], 'name': r[2], 'type': TYPE_NAMES.get(r[0], r[0])}

    def t_edit_record(self, id, changes):
        i = self._record_index(id)
        ni = self._apply_named(i, changes)
        r = self.db.recs[ni]
        self.steps.append({'tool': 'edit', 'text': 'Edited %s "%s"' % (TYPE_NAMES.get(r[0], r[0]), r[2] or r[1]),
                           'record': ni})
        return {'ok': True}
