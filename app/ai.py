"""The Workshop's AI parts: the tools a coding agent uses on your mod (mcpserver.py), and the writers of Lua and
dialogue lines, run by a model on this PC (Settings > AI).

Every change goes through the same editing functions as the buttons in the app,
so it lands in your plugin, shows up in "My mod", and can be undone. (The built-in chat on an Anthropic API key was
taken out 2026-11-22: people would rather use their own model, or their own coding agent.)"""
import json
import math
import re

import editing
import mapdata
from database import TYPE_NAMES

# a model on this PC for the writers of Lua and dialogue lines (Settings > AI): any app with the common chat
# address, Ollama's here by default (LM Studio's is http://127.0.0.1:1234/v1). A tester asked for it, 2026-11-21.
LOCAL_URL = 'http://127.0.0.1:11434/v1'
QUOTED = r'"([^"\n]{2,60})"|\u201c([^\u201d\n]{2,60})\u201d'      # (a name the request puts in quotes)

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
                       'float) at the top. Use OnActivate / OnPCAdd (declare short OnPCAdd first) / OnDeath to react, Journal / GetJournalIndex for '
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


def _code_of(text):
    """The code from a model's answer: inside ``` fences when it used them, else all of it."""
    m = re.search(r'```[\w]*\n(.*?)```', text or '', re.S)
    return (m.group(1) if m else (text or '')).strip()


# what OpenMW hands each engine handler (lua_check.HANDLERS names them), for the Lua writer
HANDLER_ARGS = {'onUpdate': 'dt', 'onFrame': 'dt', 'onInit': 'initData', 'onSave': '', 'onLoad': 'savedData, initData',
                'onActive': '', 'onInactive': '', 'onActivated': 'actor', 'onActivate': 'object, actor', 'onTeleported': '',
                'onConsume': 'item', 'onKeyPress': 'key: key.symbol, key.code', 'onKeyRelease': 'key',
                'onQuestUpdate': 'questId, stage', 'onNewGame': '', 'onPlayerAdded': 'player', 'onObjectActive': 'object',
                'onActorActive': 'actor', 'onItemActive': 'item', 'onInputAction': 'id',
                'onConsoleCommand': 'mode, command, selectedObject', 'onContentFilesLoaded': ''}

# the names scripts give OpenMW's modules, as the Workshop's own scripts and examples do
MODULE_NAMES = {'core': 'openmw.core', 'types': 'openmw.types', 'util': 'openmw.util', 'async': 'openmw.async',
                'storage': 'openmw.storage', 'I': 'openmw.interfaces', 'world': 'openmw.world', 'self': 'openmw.self',
                'nearby': 'openmw.nearby', 'ui': 'openmw.ui', 'input': 'openmw.input', 'ambient': 'openmw.ambient',
                'animation': 'openmw.animation', 'content': 'openmw.content', 'camera': 'openmw.camera'}


def add_requires(code):
    """The require() lines a written script forgot, put at the top: small models use world. or types. without them,
    which only fails in the game. openmw.x written out in full (openmw.ui.showMessage) becomes require('openmw.x').
    A module the kind of script may not use then shows in the checker (lua_check), and goes back to be put right."""
    known = {v.split('.', 1)[1] for v in MODULE_NAMES.values()}
    code = re.sub(r'(?<![\'"\w.])openmw\.(\w+)\b(?!\s*[\'"])',
                  lambda m: "require('openmw.%s')" % m.group(1) if m.group(1) in known else m.group(0), code)
    have = set()
    for names in re.findall(r'\blocal\s+([\w\s,]+?)\s*=', code):          # local a, b = ...
        have |= set(re.findall(r'\w+', names))
    for names in re.findall(r'\bfunction\s*[\w.:]*\s*\(([^)]*)\)', code):  # function(a, b)
        have |= set(re.findall(r'\w+', names))
    bare =re.sub(r'--\[(=*)\[.*?\]\1\]|--[^\n]*|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', '', code, flags=re.S)
    need = [n for n in MODULE_NAMES if n not in have and re.search(r'(?<![\w.:])%s\s*[.:\[]' % re.escape(n), bare)]
    if not need:
        return code
    return '\n'.join("local %s = require('%s')" % (n, MODULE_NAMES[n]) for n in need) + '\n' + code


class Assistant:
    def __init__(self, db, get_writer=None):
        self.db = db
        self.get_writer = get_writer or (lambda: {})     # {'url', 'model'}: the model on this PC
        self.ctx = {}
        self.steps = []

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

    def _write(self, prompt, max_tokens=1500):
        """One request and its text back, from the model on this PC Settings > AI name: what the writers of Lua and
        dialogue lines use. (text, usage, the model's name)"""
        return self._write_local(prompt, self.get_writer() or {}, max_tokens)

    @staticmethod
    def _local(url, path, body=None, timeout=600):
        import urllib.error
        import urllib.request
        url = (url or LOCAL_URL).strip().rstrip('/')
        if not re.match(r'^https?://', url):
            raise ToolError('The address of the model on this PC starts with http://, e.g. ' + LOCAL_URL)
        req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json'}, method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            said = e.read()[:300].decode('utf-8', 'replace')
            # (the app running it broke down partway, not a refusal: LM Studio answers {"error":"terminated"} after
            # its GPU runtime crashed, Ollama 500 "llama runner process has terminated"; a tester's Gemma, 2026-11-22)
            if e.code >= 500 or re.search(r'terminated|channel error|crash|exit status|cuda|out of memory', said, re.I):
                raise ToolError('The model on this PC stopped partway: the app running it ran into trouble (its own '
                                'log says what). Try again, or another model. (%s: %s)' % (e.code, said[:120]))
            raise ToolError('The model on this PC said no (%s): %s' % (e.code, said))
        except (urllib.error.URLError, OSError, ValueError):
            raise ToolError('Nothing answered at %s. Start Ollama, or LM Studio\'s server (Settings > AI).' % url)

    @classmethod
    def local_models(cls, url):
        """The models the app at this address offers (its /models list)."""
        d = cls._local(url, '/models', timeout=10)
        return sorted({m.get('id') for m in d.get('data') or [] if m.get('id')}, key=str.lower)

    def _write_local(self, prompt, w, max_tokens):
        model = (w.get('model') or '').strip()
        if not model:
            raise ToolError('Pick a model on this PC in Settings > AI first: it writes the Lua and the lines, free.')
        body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.2, 'max_tokens': max_tokens, 'stream': False}
        use = {'requests': 0, 'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0, 'local': True}
        thought = ''
        for again in (False, True):
            if again:
                # (a thinking model, e.g. Gemma 4 under llama.cpp, can spend all its room thinking and answer nothing; a
                # tester's empty script, 2026-11-22: asked once more with its thinking off, where the app takes that,
                # and more room; apps that don't know the switch pass it by)
                body = dict(body, max_tokens=max_tokens * 2, chat_template_kwargs={'enable_thinking': False}, think=False)
            try:
                d = self._local(w.get('url'), '/chat/completions', body)
            except ToolError:
                if not again:
                    raise
                break       # (an app that refuses the switch: what the first answer showed is said below)
            try:
                c = d['choices'][0]
                m = c['message']
            except (KeyError, IndexError, TypeError):
                raise ToolError('The model on this PC gave no answer.')
            u = d.get('usage') or {}
            use['requests'] += 1
            use['input'] += u.get('prompt_tokens', 0)
            use['output'] += u.get('completion_tokens', 0)
            raw = m.get('content') or ''
            # (thinking models put their working first: in <think>, cut short when the room ran out, or apart in
            # reasoning_content (llama.cpp, LM Studio) or reasoning (Ollama))
            inline = ''.join(re.findall(r'(?s)<think>(.*?)(?:</think>|$)', raw))
            text = re.sub(r'(?s)<think>.*?(?:</think>|$)', '', raw).strip()
            thought = (m.get('reasoning_content') or m.get('reasoning') or '') + inline
            if text:
                return text, use, model
            if not thought.strip() and c.get('finish_reason') != 'length':
                break
        # (it may have worked the answer out in its thinking: the last fenced block there, which the checks then read)
        found = re.findall(r'```[\w]*\n(.*?)```', thought, re.S)
        if found and found[-1].strip():
            return found[-1].strip(), use, model
        if thought.strip():
            raise ToolError('The model on this PC used all its room thinking and wrote nothing. Try again, give it more '
                            'room (context length) in the app running it, or try a model that answers straight away.')
        raise ToolError('The model on this PC answered with nothing. Try again, or another model.')

    def draft(self, req):
        """A few suggestions for one line of dialogue or journal text (nothing is saved)."""
        import dialogue
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
        text, usage, by = self._write('\n'.join(parts))
        # (Morrowind's placeholders are %PCName, never %PCName%: a model on this PC writes the second)
        text = re.sub(r'(%(?:PCName|PCRace|PCClass|PCRank|PCNextRank|PCCrimeLevel|Name|Race|Class|Faction|Rank|NextRank|Cell))%',
                      r'\1', text)
        opts = [l.strip()[2:].strip() for l in text.splitlines() if l.strip().startswith('- ')]
        return {'options': opts[:3] or [text.strip()], 'usage': usage, 'by': by}

    def effect_lua(self, req):
        """The Lua for one step of one of the user's own magic effects (Create > New magic effect), from a plain
        description: the body of a function(ctx), run as the effect lands, each second or as it ends, with the
        helpers myeffects.ACTOR_LUA gives it. Nothing is saved; the maker shows it for the user to keep."""
        phase = {'land': 'once, as the effect lands on them', 'second': 'once a second while the effect lasts',
                 'end': 'once, as the effect ends'}.get(req.get('when'), 'once, as the effect lands on them')
        prompt = '\n'.join([
            'Write OpenMW Lua (OpenMW 0.51, Lua 5.1 / LuaJIT) for a custom Morrowind magic effect. Do not use goto.',
            'The code is the BODY of a function(ctx) in a local script attached to the actor the effect is on. It runs %s.' % phase,
            'Effect: %s. %s' % (req.get('name') or 'a custom effect', req.get('description') or ''),
            'What this step should do: ' + (req.get('brief') or ''),
            'ctx has: ctx.self (openmw.self, the actor it is on), ctx.caster (GameObject or nil), ctx.magnitude (number),',
            'to read a stat: ctx.types.Actor.stats.dynamic.health(ctx.self).current (.base is its most; magicka, fatigue the same),',
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
        text, usage, by = self._write(prompt)
        code = re.sub(r'^-- Written by [^\n]*\n', '', _code_of(text) + '\n').strip()
        import lua_check
        import luaapi

        def faults(c):
            # (the checker's errors, and names OpenMW doesn't have: ctx.types, ctx.core... are the modules themselves)
            body = 'local function f(ctx)\n%s\nend\nreturn {}' % c
            out = [dict(p, line=max(1, p['line'] - 1)) for p in lua_check.check(body, 'NPC') if p['level'] == 'error']
            plain = re.sub(r'\bctx\.(types|core|util|nearby|self)\b', r'\1', c)
            out += [{'line': l, 'text': t, 'api': True} for l, t in luaapi.check(plain, {
                'types': 'openmw.types', 'core': 'openmw.core', 'util': 'openmw.util', 'nearby': 'openmw.nearby', 'self': 'openmw.self'})]
            return out
        probs = faults(code)
        tries = 1
        while probs and tries < 3:
            text2, usage2, by = self._write('\n'.join(x for x in [
                prompt, 'Your code:\n' + code,
                'Problems found: ' + '; '.join('line %d: %s' % (p['line'], p['text']) for p in probs[:8]),
                self._api_detail(re.sub(r'\bctx\.', '', code), [dict(p, text=re.sub(r'^ctx\.', '', p['text'])) for p in probs]),
                'Answer with the corrected code only.'] if x))
            tries += 1
            for k in ('requests', 'input', 'output'):
                usage[k] = usage.get(k, 0) + usage2.get(k, 0)
            usage['largest'] = max(usage.get('largest', usage.get('input', 0)), usage2.get('largest', usage2.get('input', 0)))
            code2 = re.sub(r'^-- Written by [^\n]*\n', '', _code_of(text2) + '\n').strip()
            p2 = faults(code2)
            if len(p2) <= len(probs):
                code, probs = code2, p2
        mark = '-- Written by %s from: "%s". Try it in the game.\n' % (
            by + ' (a model on this PC)', re.sub(r'\s+', ' ', req.get('brief') or '')[:120])
        return {'code': mark + code, 'problems': [{'line': p['line'] + 1, 'text': p['text']} for p in probs], 'usage': usage,
                'by': by, 'tries': tries}

    def lua_script(self, req):
        """A whole OpenMW Lua script for the Lua editor (Scripts > a Lua script > Write with AI), from a plain description.
        The model is given the kind of script, what OpenMW lets that kind use, a short guide, one of the Workshop's own
        working examples and the names in OpenMW's own list of its Lua (luaapi, from the install: what a small model on
        this PC needs not to make functions up). What it writes is checked, names OpenMW doesn't have among it, and
        anything found goes back twice to be put right, with the real API of what it got wrong. A script on objects that
        asks the global script for something nobody does gets that global script written too. Nothing is saved: the
        editor shows it, to keep or not, marked with who wrote it."""
        import lua_check
        import luascripts
        kind = (req.get('kind') or 'GLOBAL').upper()
        brief = (req.get('brief') or '').strip()
        if not brief:
            raise ToolError('Say what the script should do.')
        group = lua_check.KIND_GROUP.get(kind, 'LOCAL')
        common = ('openmw.core', 'openmw.types', 'openmw.util', 'openmw.async', 'openmw.storage', 'openmw.interfaces',
                  'openmw.world', 'openmw.self', 'openmw.nearby', 'openmw.ui', 'openmw.input', 'openmw.ambient', 'openmw.animation',
                  'openmw.content')
        mods = [m for m in common if lua_check.MODULES.get(m, ()) is None or group in (lua_check.MODULES.get(m) or ())]
        handlers = sorted(lua_check.HANDLERS['any'] | lua_check.HANDLERS.get(group, set()))
        runs = {'GLOBAL': 'the GLOBAL script: one copy for the whole game. It may change the world: create, move (teleport) '
                          'and remove objects, give items.',
                'PLAYER': 'a PLAYER script: it runs on the player. It may show messages and read keys; it changes only the player.',
                'LOAD': 'a LOAD script: it runs once as the game loads its content (openmw.content), to make or change records.',
                'MENU': 'a MENU script: it runs in the main menu.'}.get(group) or (
            'a local script on %s near the player. It changes only the object it runs on (openmw.self); it may read '
            'others and send them events. Many copies run at once, one per object, so it must not do work every frame: no '
            'onUpdate; use onActive, onActivated, events or a timer (async:newUnsavableSimulationTimer).' % {
                'NPC': 'every NPC', 'CREATURE': 'every creature', 'CUSTOM': 'each object the user chose'}.get(kind, 'each object'))
        ex = next((t for t in luascripts.TEMPLATES if t['kind'] == kind and t['id'] != 'blank'), None) or \
            next((t for t in luascripts.TEMPLATES if t['kind'] == {'PLAYER': 'PLAYER', 'LOCAL': 'CUSTOM'}.get(group, 'GLOBAL')
                  and t['id'] != 'blank'))
        cur = (req.get('current') or '').strip()
        cur = re.sub(r'^-- Written by [^\n]*\n', '', cur + '\n').strip()     # (its own mark, not passed on)
        rules = '\n'.join([
            'It is ' + runs,
            'It may require() only these modules: ' + ', '.join(mods) + '.',
            'Its engineHandlers may be: ' + ', '.join(handlers) + '. Misspelt names never run.',
            'Start with a local line for every module it uses, e.g. local types = require(\'openmw.types\').',
            'The file returns { engineHandlers = { ... }, eventHandlers = { EventName = function(data) ... end } }.',
            'In a PLAYER or local script, self = require(\'openmw.self\') IS the object it runs on: self.recordId, self.position, '
            'self.cell, types.Actor.isDead(self), and self.object where a function wants the object itself. Fields can\'t be '
            'added to self: keep your own values in local variables.',
            'Only a GLOBAL script may change the world (teleport anyone, create objects, give items); a PLAYER or local script asks '
            'one with core.sendGlobalEvent(\'SomeName\', data), and its eventHandlers.SomeName does it. ui only works in a PLAYER script; '
            'others send the player an event to show a message.',
            'Keep what must last in local tables: onSave() returns a table and onLoad(data) gets it back.',
            'Handlers get: ' + ', '.join('%s(%s)' % (h, HANDLER_ARGS[h]) for h in handlers if h in HANDLER_ARGS) + '.',
            'To show the player a message from a script that is not a PLAYER script: player:sendEvent(\'ShowMessage\', '
            '{ message = text }) (the game\'s own player script shows it); near an object the player is nearby.players[1].',
            'Reading: types.Actor.stats.dynamic.health(actor).current (.base is its most; magicka, fatigue the same); '
            'types.Actor.isDead(actor); types.NPC.record(npc).name; types.Actor.inventory(actor):countOf(recordId); '
            'is it the player: types.Player.objectIsInstance(obj); '
            'when an NPC or creature dies, its own scripts get the event Died: eventHandlers = { Died = function() ... end }; '
            'core.getGameTime() and core.getSimulationTime() in seconds; util.vector3(x, y, z).',
            'In GLOBAL: world.players[1], world.activeActors, world.createObject(recordId, count), '
            'obj:teleport(cellName or \'\', util.vector3(x, y, z)), obj:moveInto(types.Actor.inventory(actor)), obj:remove().',
            'A teleport always needs the position: use the spot given below for the place.',
            '"Every N seconds" means real seconds (a timer: async:newUnsavableSimulationTimer(N, fn), or core.getRealTime()) unless '
            'game time is asked for; game time runs 30 times faster.'])
        api_map = self._api_map(mods)
        facts = self._facts(brief)
        prompt = '\n'.join(x for x in [
            'Write an OpenMW Lua script (OpenMW 0.50 or newer, Lua 5.1 / LuaJIT) for a Morrowind mod. Do not use goto.',
            'What it should do: ' + brief,
            facts,
            ('The script as it is now (change it as asked, keep the rest):\n' + cur) if cur else '',
            rules,
            ('OpenMW\'s Lua has only these (from its own list; anything else does not exist):\n' + api_map) if api_map else '',
            'An example of a correct script (%s):\n%s' % (ex['label'], ex['text'].strip()),
            'Short comments in plain words. Answer with the whole script only, no explanation, no ``` fences.'] if x)
        text, usage, by = self._write(prompt, max_tokens=2500)
        usage['largest'] = usage.get('input', 0)      # (the biggest single request: a small model's room)
        code = add_requires(_code_of(text))
        faults = lambda c: [p for p in lua_check.check(c, kind) if p['level'] == 'error' or p.get('api')]    # noqa: E731
        probs = faults(code)
        tries = 1
        while probs and tries < 3:
            # (again, with the checker's words and the real API of what it got wrong: small models slip on an end, a
            # bracket, or a function they made up; the request kept short, a model on this PC has little room)
            fix = '\n'.join(x for x in [
                'Put right this OpenMW Lua script (OpenMW 0.50 or newer) for a Morrowind mod.',
                'What it should do: ' + brief, facts, rules, 'The script:\n' + code,
                'Problems found: ' + '; '.join('line %d: %s' % (p['line'], p['text']) for p in probs[:8]),
                self._api_detail(code, probs),
                'Answer with the corrected whole script only, no explanation, no ``` fences.'] if x)
            text2, usage2, by = self._write(fix, max_tokens=2500)
            code2 = add_requires(_code_of(text2))
            tries += 1
            for k in ('requests', 'input', 'output'):
                usage[k] = usage.get(k, 0) + usage2.get(k, 0)
            usage['largest'] = max(usage.get('largest', usage.get('input', 0)), usage2.get('largest', usage2.get('input', 0)))
            p2 = faults(code2)
            if len(p2) <= len(probs):
                code, probs = code2, p2
        # what it asks the global script to do that none of the mod's Lua scripts listens for (a script on an object
        # may not change the world itself: the writer sends the job on, and someone has to take it): written too
        sent = sorted(set(re.findall(r'sendGlobalEvent\(\s*[\'"](\w+)[\'"]', code))) if group != 'GLOBAL' else []
        heard = set()
        for sc in (getattr(self.db.project, 'lua', None) or []) if self.db.project else []:
            if (sc.get('kind') or '').upper() == 'GLOBAL':
                heard |= set(re.findall(r'\b(\w+)\s*=\s*function', sc.get('text') or ''))
        unheard = [e for e in sent if e not in heard]
        companion = None
        if unheard and not req.get('_inner'):
            r2 = self.lua_script({'kind': 'GLOBAL', '_inner': True, 'brief': (
                'Handle the event%s %s, sent by the script below with core.sendGlobalEvent, in eventHandlers: do what it asks '
                '(the whole task: %s). The script that sends %s:\n%s' % (
                    '' if len(unheard) == 1 else 's', ', '.join(unheard), brief, 'it' if len(unheard) == 1 else 'them', code))})
            for k in ('requests', 'input', 'output'):
                usage[k] = usage.get(k, 0) + r2['usage'].get(k, 0)
            usage['largest'] = max(usage.get('largest', 0), r2['usage'].get('largest', 0))
            handled = set(re.findall(r'\b(\w+)\s*=\s*function', r2['code']))
            companion = {'code': r2['code'], 'problems': r2['problems'], 'events': unheard,
                         'missing': [e for e in unheard if e not in handled]}
        mark = '-- Written by %s from: "%s". Read it over and try it in the game.\n' % (
            by + ' (a model on this PC)', re.sub(r'\s+', ' ', brief)[:160])
        if companion:
            companion['code'] = re.sub(r'^-- Written by [^\n]*\n', '', companion['code'])
            companion['code'] = mark.replace(' from: "', ' (the whole-game part) from: "', 1) + companion['code']
            companion['problems'] = [dict(p, line=p['line'] + 1) for p in companion['problems']]
        return {'code': (mark if not req.get('_inner') else '') + code + '\n',
                'problems': [{'line': p['line'] + (0 if req.get('_inner') else 1), 'text': p['text']} for p in probs],
                'usage': usage, 'by': by, 'tries': tries, 'unheard': unheard, 'companion': companion}

    ONE = {'NPC_': 'a person', 'CREA': 'a creature', 'MISC': 'an item', 'WEAP': 'a weapon', 'ARMO': 'armour',
           'CLOT': 'clothing', 'BOOK': 'a book', 'ALCH': 'a potion', 'INGR': 'an ingredient', 'LIGH': 'a light',
           'ACTI': 'an activator', 'CONT': 'a container', 'DOOR': 'a door', 'SPEL': 'a spell', 'APPA': 'an apparatus',
           'LOCK': 'a lockpick', 'PROB': 'a probe', 'REPA': 'a repair tool', 'LEVI': 'a levelled list',
           'LEVC': 'a levelled list'}          # (what the Write with AI window says a name is: names())
    THING_TYPES = ('NPC_', 'CREA', 'MISC', 'ALCH', 'WEAP', 'ARMO', 'CLOT', 'BOOK', 'INGR', 'LIGH', 'ACTI', 'CONT', 'DOOR',
                   'SPEL', 'APPA', 'LOCK', 'PROB', 'REPA', 'LEVI', 'LEVC')

    def _facts(self, brief):
        """What the request names, as the player's own game has it: the Workshop knows every record and place, a model
        doesn't. A place in quotes gets a spot to arrive at inside it (doors.arrival: in front of a door), a thing or
        person in quotes its real ID, and an ID the game doesn't have is said to be missing. (The game test: a teleport
        with no spot failed, one with a door's spot worked.) A few lines at most."""
        db = self.db
        if not getattr(db, 'recs', None) or getattr(db, 'state', '') != 'ready':
            return ''
        out = []
        phrases = [a or b for a, b in re.findall(QUOTED, brief)]
        for ph in phrases[:6]:
            ph = ph.strip()
            f = self._lookup(ph)
            if not f:
                continue
            pos = f.get('pos')
            if f['kind'] == 'place':
                out.append('The place "%s": a spot inside it to arrive at is util.vector3(%.0f, %.0f, %.0f).' % (ph, pos[0], pos[1], pos[2]))
            elif f['kind'] == 'outdoors':
                out.append('The place "%s" is outdoors: teleport there with obj:teleport(\'\', util.vector3(%.0f, %.0f, %.0f)).' % (
                    ph, pos[0], pos[1], pos[2]))
            else:
                out.append('"%s" in this game: %s.' % (ph, '; '.join('ID %s (%s: "%s")' % (
                    r['id'], TYPE_NAMES.get(r['type'], r['type']), r.get('name') or r['id']) for r in f['rows'])))
        for rid in dict.fromkeys(re.findall(r'\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b', brief)):
            if rid.startswith(('openmw', 'ctx')) or any(rid in o for o in out):
                continue
            if db.resolve_id(rid) is None:
                out.append('There is nothing called %s in this game: don\'t use that ID.' % rid)
        return ('In this player\'s game:\n' + '\n'.join(out[:8])) if out else ''

    def _lookup(self, ph):
        """One name the request puts in quotes, as this game has it: {'kind': 'place', 'pos'} (a spot inside it, in
        front of a door), {'kind': 'outdoors', 'pos'}, {'kind': 'things', 'rows', 'exact'} (up to three records), or
        None when the game has nothing like it."""
        db = self.db
        try:
            import doors
            if ('CELL', ph.lower()) in db.by_key:          # (places are kept by their name in lower case)
                pos, _door = doors.arrival(db, ph.lower())
                return {'kind': 'place', 'pos': pos}
        except Exception:
            pass
        try:
            # (a named stretch of the outdoors, Seyda Neen: a spot in one of its cells; outdoors a teleport takes '')
            cells = [r for r in db.search(ph, types=('CELL',), limit=40)['rows']
                     if (r.get('name') or r['id'] or '').lower().split(' (')[0] == ph.lower() and db.key_of(r['i'])[1].startswith('#')]
            if cells:
                import doors
                pos, _door = doors.arrival(db, db.key_of(cells[len(cells) // 2]['i'])[1])
                return {'kind': 'outdoors', 'pos': pos}
        except Exception:
            pass
        try:
            rows = db.search(ph, types=self.THING_TYPES, limit=12)['rows']
        except Exception:
            rows = []
        same = [r for r in rows if (r.get('name') or '').lower() == ph.lower() or r['id'].lower() == ph.lower()]
        pick = (same or rows)[:3]
        return {'kind': 'things', 'rows': pick, 'exact': bool(same)} if pick else None

    def names(self, brief):
        """What the Write with AI window shows under the request as it is typed: each name in quotes, found or not
        (the same look-up the writer is given: _facts)."""
        db = self.db
        if not getattr(db, 'recs', None) or getattr(db, 'state', '') != 'ready':
            return {'names': [], 'ready': False}
        out = []
        for a, b in re.findall(QUOTED, brief or '')[:6]:
            ph = (a or b).strip()
            f = self._lookup(ph)
            if not f:
                out.append({'name': ph, 'found': False, 'what': 'nothing in your game by that name'})
            elif f['kind'] == 'place':
                out.append({'name': ph, 'found': True, 'what': 'a place'})
            elif f['kind'] == 'outdoors':
                out.append({'name': ph, 'found': True, 'what': 'a place outdoors'})
            else:
                r = f['rows'][0]
                what = '%s, ID %s' % (self.ONE.get(r['type'], r['type']), r['id'])
                out.append({'name': ph, 'found': f['exact'], 'what': what if f['exact'] else 'not exactly; nearest: %s "%s"' % (
                    what, r.get('name') or r['id'])})
        return {'names': out, 'ready': True}

    @staticmethod
    def _api_map(mods):
        """The names in OpenMW's own list of its Lua for these modules, a line each, with objects' and actors' own:
        enough for a model to pick real ones, short enough for a small one (luaapi; '' when the install has none)."""
        import luaapi
        api = luaapi.load(None)
        if not api:
            return ''
        out = []

        def names(key, owner):
            ms = luaapi.members(api, key)
            if ms:
                out.append('%s: %s' % (owner, ', '.join(
                    ('%s(%s)' % (n, ', '.join(ms[n].get('params') or [])) if ms[n]['kind'] == 'function' else n)
                    for n in sorted(ms) if not n.startswith('ESM4'))))       # (other games' records: no use here)
        for m in mods:
            if m in ('openmw.interfaces', 'openmw.content'):
                continue
            names(api['modules'].get(m), m.split('.', 1)[1])
        names('core#GameObject', 'any object (obj.x, obj:x())')
        names('types#Actor', 'types.Actor')
        return '\n'.join(out)

    @staticmethod
    def _api_detail(code, probs):
        """The real functions and fields, with what they do, of what the script got wrong (luaapi)."""
        import luaapi
        api = luaapi.load(None)
        if not api:
            return ''
        keys = []
        for p in probs:
            m = re.match(r'^(\S+?)[.:](\w+) is not in', p['text']) if p.get('api') else None
            if not m:
                continue
            parts = [x.replace('(…)', '').replace('[…]', '') for x in re.split(r'[.:]', m.group(1))]
            key = api['modules'].get('openmw.' + parts[0])
            for part in parts[1:]:
                info = luaapi.members(api, key).get(part) if key else None
                key = info['type'] if info and isinstance(info.get('type'), str) else None
            if key and key not in keys:
                keys.append(key)
        text = luaapi.excerpt(None, keys[:3], most=40)
        # (kept short: a small model on this PC has room for about 4,000 tokens a request, all told)
        return ('What those have, from OpenMW\'s own list:\n' + text[:1500]) if text else ''

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
